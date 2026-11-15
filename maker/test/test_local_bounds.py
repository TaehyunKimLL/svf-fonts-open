#!/usr/bin/env python3
"""Bounded lifecycle of the maker local mode (card t_d1aba4b8): the bounded primitives of `jobs.py`.

  python3 -m unittest discover -s maker/test -p 'test_local_bounds.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import functools
import io
import json
import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock

import fixtures
import jobs
import localfx
import server
import settings


class Hang:
    """A wrapper for one filesystem call: for the calls @p when accepts it sets `entered` and waits on `release`
    (20 s at most), then calls the real function. Works as a method replacement too (`__get__`)."""

    def __init__(self, real, when):
        self.real = real
        self.when = when
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, *args, **kw):
        if self.when(*args):
            self.entered.set()
            self.release.wait(20)
        return self.real(*args, **kw)

    def __get__(self, obj, objtype=None):
        return self if obj is None else functools.partial(self, obj)


def poll_pending(test, data_root, pred, timeout=2.0):
    """The entries of `pending-sweeps.json` once @p pred accepts them (polled, never read once), else a failure."""
    path = os.path.join(data_root, "pending-sweeps.json")
    end = time.monotonic() + timeout
    entries = None
    while time.monotonic() < end:
        try:
            with open(path, encoding="utf-8") as f:
                entries = json.load(f)
        except (OSError, ValueError):
            entries = None
        if entries is not None and pred(entries):
            return entries
        time.sleep(0.05)
    test.fail("pending-sweeps.json never matched; last read: %r" % (entries,))


def on_thread(fn):
    """Run @p fn on a daemon thread: `(thread, box)`; `box` gets its result, or the exception it raised."""
    box = []

    def run():
        try:
            box.append(fn())
        except BaseException as exc:
            box.append(exc)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, box


def thread_count(name):
    return sum(1 for t in threading.enumerate() if t.name == name)


def append(path):
    return lambda entries: (entries + [{"path": path}], None)


class BoundedPrimitivesTest(unittest.TestCase):
    def setUp(self):
        tmp_root = os.environ.get("TMPDIR") or tempfile.gettempdir()
        self.tmp = tempfile.mkdtemp(prefix="svf-bounds-", dir=tmp_root)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = os.path.join(self.tmp, "data")
        self.store = jobs.Store(self.data)

    def hang(self, target, name, real, when):
        hang = Hang(real, when)
        self.addCleanup(hang.release.set)
        patcher = mock.patch(target, hang) if name is None else mock.patch.object(target, name, hang)
        patcher.start()
        self.addCleanup(patcher.stop)
        return hang

    def wait_idle(self):
        end = time.monotonic() + 3
        while time.monotonic() < end and self.store._pending_unfinished:
            time.sleep(0.02)

    def test_rename_bounded_abandons_a_hung_rename_and_fences_the_path(self):
        src = os.path.join(self.tmp, "files")
        dst = os.path.join(self.tmp, "files.trash-00000001")
        os.mkdir(src)
        hang = self.hang(os, "rename", os.rename, lambda s, d: s == src)
        t0 = time.monotonic()
        with self.assertRaises(jobs.CallPending):
            jobs.rename_bounded(src, dst, 0.2)
        self.assertLess(time.monotonic() - t0, 0.6)
        self.assertTrue(jobs.mutation_pending(src))
        self.assertEqual(jobs.mutation_kind(src), "rename")
        self.assertTrue(jobs.mutation_pending(os.path.dirname(src)))
        self.assertFalse(jobs.mutation_pending(src + "-other"))
        t0 = time.monotonic()
        with self.assertRaises(jobs.CallPending):
            jobs.rename_bounded(src, dst, 5)
        self.assertLess(time.monotonic() - t0, 0.2)
        hang.release.set()
        end = time.monotonic() + 2
        while jobs.mutation_pending(src) and time.monotonic() < end:
            time.sleep(0.02)
        self.assertFalse(jobs.mutation_pending(src))
        self.assertTrue(os.path.isdir(dst))

    def test_a_read_only_call_waits_for_the_one_in_flight(self):
        d = os.path.join(self.tmp, "d")
        os.mkdir(d)
        real = jobs.stat_id

        def slow(p):
            if p == d:
                time.sleep(0.4)
            return real(p)
        base = thread_count("svf-maker-stat")
        with mock.patch.object(jobs, "stat_id", slow):
            a, box_a = on_thread(lambda: jobs.stat_id_bounded(d, 2))
            time.sleep(0.05)
            peak = [0]

            def sample():
                while a.is_alive():
                    peak[0] = max(peak[0], thread_count("svf-maker-stat"))
                    time.sleep(0.01)
            sampler, _ = on_thread(sample)
            got = jobs.stat_id_bounded(d, 2)
            a.join(2)
            sampler.join(2)
        self.assertEqual(got, real(d))
        self.assertEqual(box_a, [real(d)])
        self.assertLessEqual(peak[0] - base, 1)

    def test_pending_op_returns_by_the_deadline_while_the_pending_lock_is_held(self):
        with mock.patch.object(jobs, "PENDING_FLOOR_S", 0.1):
            self.store._pending_lock.acquire()
            released = [False]

            def release():
                if not released[0]:
                    released[0] = True
                    self.store._pending_lock.release()
            self.addCleanup(release)
            t0 = time.monotonic()
            done, _ = self.store._pending_op(append("x"), jobs.Deadline(0.3))
            self.assertFalse(done)
            self.assertLess(time.monotonic() - t0, 0.8)
            release()
            poll_pending(self, self.data, lambda e: e == [{"path": "x"}])

    def test_pending_op_returns_by_the_deadline_while_fsync_hangs(self):
        hang = self.hang(os, "fsync", os.fsync, lambda fd: True)
        with mock.patch.object(jobs, "PENDING_FLOOR_S", 0.1):
            t0 = time.monotonic()
            done, _ = self.store._pending_op(append("x"), jobs.Deadline(0.3))
            self.assertFalse(done)
            self.assertLess(time.monotonic() - t0, 0.8)
        hang.release.set()
        poll_pending(self, self.data, lambda e: e == [{"path": "x"}])

    def test_pending_op_with_an_expired_deadline_still_lands_on_a_healthy_disk(self):
        done, _ = self.store._pending_op(append("x"), jobs.Deadline(0))
        self.assertTrue(done)
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), [{"path": "x"}])

    def test_pending_ops_keep_their_order_after_an_abandoned_one(self):
        with mock.patch.object(jobs, "PENDING_FLOOR_S", 0.1):
            self.store._pending_lock.acquire()
            released = [False]

            def release():
                if not released[0]:
                    released[0] = True
                    self.store._pending_lock.release()
            self.addCleanup(release)
            self.assertFalse(self.store._pending_op(append("a"), jobs.Deadline(0.1))[0])
            self.assertFalse(self.store._pending_op(append("b"), jobs.Deadline(0.1))[0])
            release()
            poll_pending(self, self.data, lambda e: e == [{"path": "a"}, {"path": "b"}])

    def test_the_pending_writer_exits_when_idle_and_restarts(self):
        with mock.patch.object(jobs, "PENDING_IDLE_S", 0.2):
            self.assertTrue(self.store._pending_op(append("a"))[0])
            first = self.store._pending_thread
            self.assertEqual(first.name, "svf-maker-pending")
            first.join(3)
            self.assertFalse(first.is_alive())             # this store's writer (earlier tests' may still be winding down)
            self.assertIsNone(self.store._pending_thread)
            self.assertTrue(self.store._pending_op(append("b"))[0])
            self.assertIsNot(self.store._pending_thread, first)
        poll_pending(self, self.data, lambda e: e == [{"path": "a"}, {"path": "b"}])

    def test_a_pending_rename_keeps_and_a_pending_mkdir_clears_the_recorded_generation(self):
        files = os.path.join(self.tmp, ".svf-maker-0123456789ab")
        job = {"id": "0123456789ab", "output_dir": self.tmp, "output_id": [1, 1], "files_id": None}
        self.assertTrue(self.store._add_pending(job, files, "x", generation=[1, 2]))
        self.assertEqual(poll_pending(self, self.data, lambda e: len(e) == 1)[0]["files_id"], [1, 2])
        self.store._add_pending(job, files, "y", generation=None)
        entry = poll_pending(self, self.data, lambda e: len(e) == 1)[0]
        self.assertEqual(entry["files_id"], [1, 2])
        self.store._add_pending(job, files, "z", making=True)
        entry = poll_pending(self, self.data, lambda e: len(e) == 1 and e[0].get("making"))[0]
        self.assertIsNone(entry["files_id"])
        self.assertTrue(entry["making"])

    def test_records_after_a_stalled_one_do_not_wait_the_floor(self):
        hang = self.hang(os, "fsync", os.fsync, lambda fd: True)
        with mock.patch.object(jobs, "PENDING_FLOOR_S", 0.5):
            t0 = time.monotonic()
            for name in ("a", "b", "c"):
                self.assertFalse(self.store._pending_op(append(name), jobs.Deadline(0))[0])
            self.assertLess(time.monotonic() - t0, 0.8)
        hang.release.set()
        poll_pending(self, self.data, lambda e: e == [{"path": "a"}, {"path": "b"}, {"path": "c"}])

    def test_a_busy_but_healthy_writer_still_gives_later_records_the_floor(self):
        started = threading.Event()

        def slow(entries):
            started.set()
            time.sleep(0.3)
            return entries + [{"path": "a"}], None
        with mock.patch.object(jobs, "PENDING_FLOOR_S", 0.5):
            first, box = on_thread(lambda: self.store._pending_op(slow, jobs.Deadline(2)))
            self.assertTrue(started.wait(2))
            t0 = time.monotonic()
            done, _ = self.store._pending_op(append("b"), jobs.Deadline(0))
            elapsed = time.monotonic() - t0
            first.join(2)
        self.assertTrue(done)
        self.assertGreater(elapsed, 0.15)
        self.assertEqual(box, [(True, None)])
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), [{"path": "a"}, {"path": "b"}])

    def test_flush_waits_the_floor_after_a_stall_and_the_stall_clears_when_the_writer_finishes(self):
        hang = self.hang(os, "fsync", os.fsync, lambda fd: True)
        with mock.patch.object(jobs, "PENDING_FLOOR_S", 0.4):
            self.assertFalse(self.store._pending_op(append("a"), jobs.Deadline(0))[0])     # gave up: stalled
            t0 = time.monotonic()
            self.assertFalse(self.store.flush_pending(jobs.Deadline(0)))
            self.assertGreater(time.monotonic() - t0, 0.3)                                 # flush always waits it
            hang.release.set()
            self.wait_idle()
            t0 = time.monotonic()
            done, _ = self.store._pending_op(append("b"), jobs.Deadline(0))                # stall cleared
            self.assertTrue(done)
        poll_pending(self, self.data, lambda e: e == [{"path": "a"}, {"path": "b"}])

    def test_a_read_only_waiter_on_a_call_in_flight_too_long_fails_at_once(self):
        d = os.path.join(self.tmp, "d")
        os.mkdir(d)
        self.hang(jobs, "stat_id", jobs.stat_id, lambda p: p == d)
        with mock.patch.object(jobs, "STAT_TIMEOUT_S", 0.3):
            with self.assertRaises(jobs.CallPending):
                jobs.stat_id_bounded(d, 0.35)               # in flight for 0.35 s: a hung mount by STAT_TIMEOUT_S
            t0 = time.monotonic()
            with self.assertRaises(jobs.CallPending):
                jobs.stat_id_bounded(d, 5)
            self.assertLess(time.monotonic() - t0, 0.2)

    def test_callers_on_a_hung_path_cost_one_stat_timeout_in_all(self):
        d = os.path.join(self.tmp, "d")
        os.mkdir(d)
        hang = self.hang(jobs, "stat_id", jobs.stat_id, lambda p: p == d)
        with mock.patch.object(jobs, "STAT_TIMEOUT_S", 0.3):
            t0 = time.monotonic()
            threads = [on_thread(lambda: jobs.stat_id_bounded(d, 0.3))]       # the one that starts the call
            self.assertTrue(hang.entered.wait(2))
            threads += [on_thread(lambda: jobs.stat_id_bounded(d, 5)) for _ in range(3)]
            for thread, box in threads:
                thread.join(3)
            self.assertLess(time.monotonic() - t0, 1.0)
            self.assertTrue(all(isinstance(box[0], jobs.CallPending) for _, box in threads))

    def test_a_caller_with_a_tiny_budget_does_not_make_a_healthy_call_look_hung(self):
        d = os.path.join(self.tmp, "d")
        os.mkdir(d)
        real = jobs.stat_id
        started = threading.Event()

        def slow(p):
            if p == d:
                started.set()
                time.sleep(0.8)
            return real(p)
        with mock.patch.object(jobs, "stat_id", slow):
            a, box_a = on_thread(lambda: jobs.stat_id_bounded(d, 5))
            self.assertTrue(started.wait(2))
            with self.assertRaises(jobs.CallPending):
                jobs.stat_id_bounded(d, 0.05)               # B gives up early
            self.assertEqual(jobs.stat_id_bounded(d, 5), real(d))     # C still shares the healthy call
            a.join(3)
        self.assertEqual(box_a, [real(d)])

    def test_a_failing_after_callback_does_not_fail_a_written_record(self):
        err = io.StringIO()

        def after(result):
            raise ValueError("boom")
        with mock.patch.object(sys, "stderr", err):
            done, _ = self.store._pending_op(append("x"), jobs.Deadline(1), after=after)
        self.assertTrue(done)
        self.assertIn("ValueError", err.getvalue())
        poll_pending(self, self.data, lambda e: e == [{"path": "x"}])

    def test_an_abandoned_pending_op_that_fails_prints_its_exception(self):
        err = io.StringIO()
        with mock.patch.object(jobs, "PENDING_FLOOR_S", 0.1), mock.patch.object(sys, "stderr", err):
            self.store._pending_lock.acquire()
            self.assertFalse(self.store._pending_op(lambda e: 1 / 0, jobs.Deadline(0.1))[0])
            self.store._pending_lock.release()
            end = time.monotonic() + 2
            while "ZeroDivisionError" not in err.getvalue() and time.monotonic() < end:
                time.sleep(0.02)
            text = err.getvalue()
        self.assertIn("ZeroDivisionError", text)
        self.assertNotIn("NoneType: None", text)

    def test_a_thread_that_fails_to_start_leaves_nothing_fenced_or_queued(self):
        real = threading.Thread.start
        fail = [True]

        def start(thread):
            if fail[0]:
                fail[0] = False
                raise RuntimeError("can't start new thread")
            return real(thread)
        key = os.path.join(self.tmp, "x")
        with mock.patch.object(threading.Thread, "start", start):
            with self.assertRaises(RuntimeError):
                jobs.rename_bounded(key, key + "2", 1)
        self.assertFalse(jobs.mutation_pending(key))
        fail[0] = True
        with mock.patch.object(threading.Thread, "start", start):
            with self.assertRaises(RuntimeError):
                self.store._pending_op(append("x"))
        self.assertIsNone(self.store._pending_thread)
        self.assertTrue(self.store._pending_op(append("y"))[0])

    def test_a_record_that_lands_late_still_gets_its_log_line(self):
        job = self.store.create(source="local", output_dir=self.tmp, output_id=[1, 1])
        hang = self.hang(os, "fsync", os.fsync, lambda fd: True)
        with mock.patch.object(jobs, "PENDING_FLOOR_S", 0.1):
            self.assertFalse(self.store._add_pending(job, os.path.join(self.tmp, ".svf-maker-x"), "late",
                                                     deadline=jobs.Deadline(0)))
        hang.release.set()
        log = self.store.path(job["id"], "log.md")
        end = time.monotonic() + 2
        while time.monotonic() < end and not (os.path.exists(log) and "late" in open(log).read()):
            time.sleep(0.05)
        self.assertIn("late", open(log).read())


def entries_have(path_pred):
    return lambda entries: any(path_pred(e) for e in entries)


class SweepBoundsTest(localfx.LocalRunBase):
    """Task 2: one deadline through rename, pending records, orphans and retries (H3b)."""

    def setUp(self):
        super().setUp()
        self.store = self.srv.store

    def hang(self, target, name, real, when):
        hang = Hang(real, when)
        self.addCleanup(hang.release.set)
        patcher = mock.patch(target, hang) if name is None else mock.patch.object(target, name, hang)
        patcher.start()
        self.addCleanup(patcher.stop)
        return hang

    def hang_rename(self, path):
        return self.hang(os, "rename", os.rename, lambda s, d: s == path)

    def hang_tomb_rmtree(self, fd):
        return self.hang(shutil, "rmtree", shutil.rmtree, lambda p, *a, **k: str(p).startswith(fd + ".trash-"))

    def hold_pending_lock(self):
        self.store._pending_lock.acquire()
        released = []

        def release():
            if not released:
                released.append(1)
                self.store._pending_lock.release()
        self.addCleanup(release)
        return release

    def entry_for(self, jid, files_id=None):
        job = self.store.load(jid)
        return {"path": self.files_dir(jid), "output_dir": job["output_dir"], "output_id": job["output_id"],
                "job": jid, "files_id": files_id, "reason": "test"}

    def write_pending(self, entries):
        with open(os.path.join(self.data, "pending-sweeps.json"), "w", encoding="utf-8") as f:
            json.dump(entries, f)

    def wait_writer_idle(self):
        end = time.monotonic() + 3
        while time.monotonic() < end and self.store._pending_unfinished:
            time.sleep(0.02)
        self.assertEqual(self.store._pending_unfinished, 0)

    def make_orphan(self, name, out=None):
        path = os.path.join(out or self.out, name)
        os.makedirs(path)
        with open(os.path.join(path, "x"), "w") as f:
            f.write("x")
        return path

    def test_stop_returns_by_the_deadline_although_a_rename_hangs(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        self.hang_rename(fd)
        with mock.patch.object(jobs, "STOP_SWEEP_TOTAL_S", 1.0):
            t0 = time.monotonic()
            t, box = on_thread(self.srv.worker.sweep_local_files)
            t.join(3)
            self.assertFalse(t.is_alive())
            self.assertLess(time.monotonic() - t0, 2.5)
        poll_pending(self, self.data, lambda es: any(e["path"] == fd for e in es)
                     and any(e["path"].startswith(fd + ".trash-") and e.get("from") == fd for e in es))

    def test_startup_returns_by_the_deadline_although_a_rename_hangs(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        self.hang_rename(fd)
        self.release_lock()
        with mock.patch.object(server, "STARTUP_CLEANUP_S", 1.0):
            t0 = time.monotonic()
            t, box = on_thread(lambda: server.make_server("127.0.0.1", 0, fixtures.REPO_DIR, self.data,
                                                          token=localfx.TOKEN))
            t.join(4)
            self.assertFalse(t.is_alive())
        self.assertEqual(len(box), 1)
        srv2 = box[0]
        self.assertNotIsInstance(srv2, BaseException)
        try:
            self.assertLess(time.monotonic() - t0, 3.0)
            self.assertIn(jid, srv2.cleanup_pending)
        finally:
            srv2.worker.stop()
            srv2.server_close()

    def test_an_abandoned_rename_never_moves_a_later_generation(self):
        jid = self.local_job()
        self.select(jid)
        fd = self.files_dir(jid)
        ino = os.stat(fd).st_ino
        hang = self.hang_rename(fd)
        t, box = on_thread(lambda: self.store.sweep_files(self.store.load(jid), bound=0.5))
        t.join(2)
        self.assertFalse(t.is_alive())
        self.assertEqual(box, [False])
        with self.assertRaises(jobs.OutputGone) as cm:
            self.store.ensure_files_dir(self.store.load(jid))
        self.assertIn("still being moved or made", str(cm.exception))
        status = self.raw("GET", "/api/jobs/%s/probe/%s/16/1.json" % (jid, self.ttf))[0]
        self.assertEqual(status, 404)
        self.assertEqual(os.stat(fd).st_ino, ino)
        hang.release.set()
        end = time.monotonic() + 2
        while time.monotonic() < end and jobs.mutation_pending(fd):
            time.sleep(0.02)
        self.assertFalse(jobs.mutation_pending(fd))
        self.store.retry_pending_sweeps()
        self.assertEqual([n for n in os.listdir(self.out) if n.startswith(".svf-maker-%s.trash-" % jid)], [])
        job = self.store.load(jid)
        self.store.ensure_files_dir(job)
        self.assertEqual(self.store.load(jid)["files_id"], list(jobs.stat_id(fd)))
        self.store.retry_pending_sweeps()
        self.assertTrue(os.path.isdir(fd))

    def test_retry_keeps_a_tombstone_entry_whose_rename_is_in_flight(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        self.hang_rename(fd)
        t, box = on_thread(lambda: self.store.sweep_files(self.store.load(jid), bound=0.5))
        t.join(2)
        self.assertFalse(t.is_alive())
        poll_pending(self, self.data, lambda es: len(es) == 2)
        t2, box2 = on_thread(lambda: self.store.retry_pending_sweeps(deadline_s=1))
        t2.join(3)
        self.assertFalse(t2.is_alive())
        entries = poll_pending(self, self.data, lambda es: len(es) == 2)
        self.assertTrue(any(e["path"].startswith(fd + ".trash-") for e in entries), entries)
        self.assertTrue(any(e["path"] == fd for e in entries), entries)

    def test_a_retry_whose_own_rename_is_abandoned_keeps_the_tombstone(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        self.store.update(jid, lambda j: j.update(state="failed"))
        job = self.store.load(jid)
        self.write_pending([self.entry_for(jid, files_id=job["files_id"])])
        self.hang_rename(fd)
        t, box = on_thread(lambda: self.store.retry_pending_sweeps(stat_timeout=0.3, deadline_s=2.5))
        t.join(4)
        self.assertFalse(t.is_alive())
        self.assertTrue(self.store.flush_pending())
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:      # one read, after the pass
            entries = json.load(f)
        self.assertTrue(any(e["path"] == fd for e in entries), entries)
        self.assertTrue(any(e["path"].startswith(fd + ".trash-") and e.get("from") == fd for e in entries), entries)

    def test_stop_returns_by_the_deadline_while_the_pending_lock_is_held(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        hang = self.hang_tomb_rmtree(fd)
        release = self.hold_pending_lock()
        with mock.patch.object(jobs, "STOP_SWEEP_TOTAL_S", 1.0), mock.patch.object(jobs, "PENDING_FLOOR_S", 0.1):
            t0 = time.monotonic()
            t, box = on_thread(self.srv.worker.sweep_local_files)
            t.join(3)
            self.assertFalse(t.is_alive())
            self.assertLess(time.monotonic() - t0, 2.5)
        release()
        hang.release.set()
        poll_pending(self, self.data, entries_have(lambda e: e["path"].startswith(fd + ".trash-")))

    def test_stop_returns_by_the_deadline_while_fsync_hangs(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        hang = self.hang_tomb_rmtree(fd)
        fsync = self.hang(os, "fsync", os.fsync, lambda fd_: True)
        with mock.patch.object(jobs, "STOP_SWEEP_TOTAL_S", 1.0), mock.patch.object(jobs, "PENDING_FLOOR_S", 0.1):
            t0 = time.monotonic()
            t, box = on_thread(self.srv.worker.sweep_local_files)
            t.join(3)
            self.assertFalse(t.is_alive())
            self.assertLess(time.monotonic() - t0, 2.5)
        fsync.release.set()
        hang.release.set()
        poll_pending(self, self.data, entries_have(lambda e: e["path"].startswith(fd + ".trash-")))

    def test_stop_lands_its_pending_records_before_returning(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        self.hang_tomb_rmtree(fd)
        with mock.patch.object(jobs, "STOP_SWEEP_TOTAL_S", 1.0):
            self.srv.worker.sweep_local_files()
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:      # one read, no poll
            entries = json.load(f)
        self.assertTrue(any(e["path"].startswith(fd + ".trash-") for e in entries), entries)

    def test_orphan_sweep_returns_by_the_deadline_although_a_rename_hangs(self):
        self.local_job()                                       # makes self.out a known folder
        orphan = self.make_orphan(".svf-maker-0123456789ab")
        self.hang_rename(orphan)
        t, box = on_thread(lambda: self.store.sweep_orphans(jobs.Deadline(1.0)))
        t.join(3)
        self.assertFalse(t.is_alive())

    def test_an_orphan_tombstone_is_swept_at_start_up(self):
        jid = self.local_job()
        dead = self.make_orphan(".svf-maker-0123456789ab.trash-0badf00d")
        live = self.make_orphan(".svf-maker-%s.trash-0badf00e" % jid)
        self.release_lock()
        srv2 = server.make_server("127.0.0.1", 0, fixtures.REPO_DIR, self.data, token=localfx.TOKEN)
        try:
            self.assertFalse(os.path.exists(dead))
            self.assertFalse(os.path.exists(live))
        finally:
            srv2.worker.stop()
            srv2.server_close()

    def test_an_orphan_removal_error_does_not_stop_the_sweep(self):
        self.local_job()
        first = self.make_orphan(".svf-maker-0123456789ab.trash-0badf00d")
        second = self.make_orphan(".svf-maker-0123456789ac.trash-0badf00e")
        real = shutil.rmtree

        def rmtree(path, *a, **k):
            if str(path) == first:
                raise PermissionError("denied")
            return real(path, *a, **k)
        with mock.patch.object(shutil, "rmtree", rmtree):
            self.store.sweep_orphans(jobs.Deadline(2))
        self.assertFalse(os.path.exists(second))
        poll_pending(self, self.data, entries_have(lambda e: e["path"] == first))

    def test_a_delete_whose_cleanup_record_cannot_be_saved_keeps_the_job(self):
        out2 = os.path.join(self.tmp, "out2")
        os.mkdir(out2)
        jid = self.local_job(out=out2)
        fsync = self.hang(os, "fsync", os.fsync, lambda fd_: True)
        with mock.patch.object(jobs, "LOCKED_IO_S", 0.3), mock.patch.object(jobs, "PENDING_FLOOR_S", 0.1):
            t0 = time.monotonic()
            t, box = on_thread(lambda: self.api("DELETE", "/api/jobs/%s" % jid))
            t.join(3)
            self.assertFalse(t.is_alive())
            self.assertLess(time.monotonic() - t0, 1.5)
        status, body = box[0]
        self.assertEqual(status, 409, body)
        self.assertIn("busy", json.dumps(body))
        self.assertTrue(os.path.exists(os.path.join(self.data, "jobs", jid, "job.json")))
        fsync.release.set()
        self.wait_writer_idle()
        self.assertEqual(self.api("DELETE", "/api/jobs/%s" % jid)[0], 200)

    def test_the_only_job_of_a_folder_leaves_a_findable_tombstone_when_deleted(self):
        out2 = os.path.join(self.tmp, "out2")
        os.mkdir(out2)
        jid = self.local_job(out=out2)
        self.select(jid)
        self.assertEqual(self.run_to_done(jid)["state"], "done")
        fd2 = os.path.join(out2, ".svf-maker-" + jid)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, self.dos))[0], 200)
        self.assertTrue(os.path.isdir(fd2))
        hang = self.hang_tomb_rmtree(fd2)
        with mock.patch.object(jobs, "REMOVE_BOUND_S", 0.3):
            self.assertEqual(self.api("DELETE", "/api/jobs/%s" % jid)[0], 200)
        entries = poll_pending(self, self.data, entries_have(lambda e: e["path"].startswith(fd2 + ".trash-")))
        self.assertEqual([e["output_dir"] for e in entries if e["path"].startswith(fd2 + ".trash-")], [out2])
        self.release_lock()
        hang.release.set()
        srv2 = server.make_server("127.0.0.1", 0, fixtures.REPO_DIR, self.data, token=localfx.TOKEN)
        try:
            self.assertEqual([n for n in os.listdir(out2) if n.startswith(".svf-maker-" + jid)], [])
        finally:
            srv2.worker.stop()
            srv2.server_close()

    def test_an_idle_sweep_does_not_wait_beyond_its_deadline_for_the_lifecycle_lock(self):
        self.local_job()
        self.store.lifecycle.acquire()
        held = [True]

        def unlock():
            if held:
                held.clear()
                self.store.lifecycle.release()
        self.addCleanup(unlock)
        with mock.patch.object(jobs, "RETRY_DEADLINE_S", 0.5):
            t, box = on_thread(lambda: server._sweep_idle(self.srv, now=time.monotonic()
                                                          + server.LOCAL_IDLE_SWEEP_S + 5))
            t.join(2)
            self.assertFalse(t.is_alive())
        unlock()

    def test_a_retry_starts_no_filesystem_call_after_its_deadline(self):
        jid = self.local_job()
        self.store.update(jid, lambda j: j.update(state="failed"))
        job = self.store.load(jid)
        self.write_pending([self.entry_for(jid, files_id=job["files_id"])])

        class Fake:
            over = False

            def remaining(self):
                return 0.0 if self.over else 1.0

            def expired(self):
                return self.over

            def capped(self, seconds):
                return self
        fake = Fake()
        real_stat, real_call = jobs.stat_id, jobs.bounded_call
        starts = []

        def stat(path):
            result = real_stat(path)
            if path == job["output_dir"]:
                fake.over = True
            return result

        def call(key, fn, timeout):
            starts.append(fake.over)
            return real_call(key, fn, timeout)
        with mock.patch.object(jobs, "stat_id", stat), mock.patch.object(jobs, "bounded_call", call):
            self.store.retry_pending_sweeps(deadline=fake)
        self.assertTrue(starts)
        self.assertNotIn(True, starts)

    def test_a_retry_whose_lock_wait_used_the_deadline_starts_no_stat_or_rename(self):
        jid = self.local_job()
        self.store.update(jid, lambda j: j.update(state="failed"))
        job = self.store.load(jid)
        self.write_pending([self.entry_for(jid, files_id=None)])
        fd = self.files_dir(jid)

        class Fake:
            over = False

            def remaining(self):
                return 0.0 if self.over else 1.0

            def expired(self):
                return self.over

            def capped(self, seconds):
                return self
        fake = Fake()

        class Lifecycle:                                    # taking it uses up the deadline
            def __init__(self, real):
                self.real = real

            def acquire(self, *a, **k):
                got = self.real.acquire(*a, **k)
                fake.over = True
                return got

            def release(self):
                self.real.release()
        real_call, starts = jobs.bounded_call, []

        def call(key, fn, timeout):
            starts.append((key[0], fake.over))
            return real_call(key, fn, timeout)
        with mock.patch.object(jobs, "bounded_call", call), \
                mock.patch.object(self.store, "lifecycle", Lifecycle(self.store.lifecycle)):
            self.store.retry_pending_sweeps(deadline=fake)
        self.assertTrue(starts)
        self.assertNotIn(True, [over for _op, over in starts], starts)
        self.assertTrue(os.path.isdir(fd))

    def test_nothing_is_started_with_no_time_left(self):
        ran = []
        for op in ("rename", "stat"):
            with self.assertRaises(jobs.CallPending):
                jobs.bounded_call((op, "/x"), lambda: ran.append(op), 0)
        self.assertEqual(ran, [])
        self.assertFalse(jobs.mutation_pending("/x"))
        jid = self.local_job()
        fd = self.files_dir(jid)
        calls = []
        real_call = jobs.bounded_call

        def call(key, fn, timeout):
            calls.append(key[0])
            return real_call(key, fn, timeout)
        with mock.patch.object(jobs, "bounded_call", call):
            step = self.store._rename_away(self.store.load(jid), jobs.Deadline(0))
        self.assertEqual(step[0], "failed")
        self.assertEqual(calls, [])
        self.assertTrue(os.path.isdir(fd))

    def test_a_rename_that_never_started_for_want_of_time_records_no_tombstone(self):
        jid = self.local_job()
        fd = self.files_dir(jid)

        class Fake:
            over = False

            def remaining(self):
                return 0.0 if self.over else 1.0

            def expired(self):
                return self.over

            def capped(self, seconds):
                return self
        fake = Fake()
        real = jobs.stat_id

        def stat(path):
            result = real(path)
            if path == fd:
                fake.over = True                              # the stats used up the deadline, just before the rename
            return result
        job = self.store.load(jid)
        with mock.patch.object(jobs, "stat_id", stat):
            step = self.store._rename_away(job, fake, check_active=False)
        self.assertEqual(step[0], "failed")
        self.assertEqual([e["path"] for e in self.store._step_entries(job, step)], [fd])
        self.assertTrue(os.path.isdir(fd))

    def test_a_tombstone_of_a_live_job_is_removed_by_the_orphan_sweep_alone(self):
        jid = self.local_job()
        live = self.make_orphan(".svf-maker-%s.trash-0badf00e" % jid)
        self.store.sweep_orphans(jobs.Deadline(2))
        self.assertFalse(os.path.exists(live))
        self.assertTrue(os.path.isdir(self.files_dir(jid)))      # its live directory is untouched

    def test_a_failed_takeover_that_cannot_record_answers_409_busy_and_keeps_the_job(self):
        real = os.mkdir

        def mkdir(path, *a, **k):
            if os.path.basename(str(path)) == "work" and ".svf-maker-" in str(path):
                raise OSError(5, "I/O error")
            return real(path, *a, **k)
        fsync = self.hang(os, "fsync", os.fsync, lambda fd_: True)
        with mock.patch.object(os, "mkdir", mkdir), mock.patch.object(jobs, "LOCKED_IO_S", 0.3), \
                mock.patch.object(jobs, "PENDING_FLOOR_S", 0.1):
            t, box = on_thread(lambda: self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out}))
            t.join(3)
            self.assertFalse(t.is_alive())
        status, body = box[0]
        self.assertEqual(status, 409, body)
        self.assertIn("busy", json.dumps(body))
        left = [i for i in self.store.list()]
        self.assertEqual([i["state"] for i in left], ["uploading"])
        fsync.release.set()
        self.wait_writer_idle()

    def test_a_tombstone_removal_error_after_a_delete_never_reaches_the_answer(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        real = shutil.rmtree

        def rmtree(path, *a, **k):
            if str(path).startswith(fd + ".trash-"):
                raise PermissionError("denied")
            return real(path, *a, **k)
        with mock.patch.object(shutil, "rmtree", rmtree):
            self.assertEqual(self.api("DELETE", "/api/jobs/%s" % jid)[0], 200)
        poll_pending(self, self.data, entries_have(lambda e: e["path"].startswith(fd + ".trash-")))

    def test_a_tombstone_already_gone_after_a_delete_drops_its_entry(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        real = shutil.rmtree

        def rmtree(path, *a, **k):
            if str(path).startswith(fd + ".trash-"):
                real(path, *a, **k)
                raise FileNotFoundError(2, "gone")
            return real(path, *a, **k)
        with mock.patch.object(shutil, "rmtree", rmtree):
            self.assertEqual(self.api("DELETE", "/api/jobs/%s" % jid)[0], 200)
        poll_pending(self, self.data, lambda es: not any(e["path"].startswith(fd + ".trash-") for e in es))


class StartupBoundsTest(localfx.LocalRunBase):
    """Task 3: the start-up tombstone sweep within the shared deadline (H3a)."""

    def setUp(self):
        super().setUp()
        self.store = self.srv.store

    def hang(self, target, name, real, when):
        hang = Hang(real, when)
        self.addCleanup(hang.release.set)
        patcher = mock.patch(target, hang) if name is None else mock.patch.object(target, name, hang)
        patcher.start()
        self.addCleanup(patcher.stop)
        return hang

    def tombstones(self, jid, count):
        fd = self.files_dir(jid)
        paths = []
        for n in range(count):
            path = "%s.trash-%08x" % (fd, 0x0badf00d + n)
            os.makedirs(path)
            with open(os.path.join(path, "x"), "w") as f:
                f.write("x")
            paths.append(path)
        return paths

    def hang_tomb_rmtree(self, jid):
        prefix = self.files_dir(jid) + ".trash-"
        return self.hang(shutil, "rmtree", shutil.rmtree, lambda p, *a, **k: str(p).startswith(prefix))

    def start_server(self):
        """A second server on the same data root, made on a thread: `(thread, box, t0)`."""
        t0 = time.monotonic()
        t, box = on_thread(lambda: server.make_server("127.0.0.1", 0, fixtures.REPO_DIR, self.data,
                                                      token=localfx.TOKEN))

        def close():
            t.join(25)
            if box and not isinstance(box[0], BaseException):
                box[0].worker.stop()
                box[0].server_close()
        self.addCleanup(close)
        return t, box, t0

    def test_startup_with_several_hung_tombstones_returns_by_the_single_deadline(self):
        jid, _ = self.done_job()
        self.tombstones(jid, 3)
        self.hang_tomb_rmtree(jid)
        self.release_lock()
        with mock.patch.object(jobs, "REMOVE_BOUND_S", 0.8), mock.patch.object(server, "STARTUP_CLEANUP_S", 1.0):
            t, box, t0 = self.start_server()
            t.join(5)
            self.assertFalse(t.is_alive())
            elapsed = time.monotonic() - t0
        self.assertNotIsInstance(box[0], BaseException)
        self.assertLess(elapsed, 2.0)
        self.assertNotIn(jid, box[0].cleanup_pending)

    def test_startup_returns_by_the_deadline_although_listdir_hangs(self):
        jid, _ = self.done_job()
        self.hang(os, "listdir", os.listdir, lambda p: p == self.out)
        self.release_lock()
        with mock.patch.object(server, "STARTUP_CLEANUP_S", 1.0):
            t, box, t0 = self.start_server()
            t.join(4)
            self.assertFalse(t.is_alive())
        self.assertLess(time.monotonic() - t0, 3.0)

    def test_unfinished_tombstone_removals_at_start_up_are_all_recorded_pending(self):
        jid, _ = self.done_job()
        tombs = self.tombstones(jid, 3)
        hang = self.hang_tomb_rmtree(jid)
        self.release_lock()
        with mock.patch.object(jobs, "REMOVE_BOUND_S", 0.8), mock.patch.object(server, "STARTUP_CLEANUP_S", 1.0):
            t, box, t0 = self.start_server()
            t.join(5)
            self.assertFalse(t.is_alive())
        poll_pending(self, self.data, lambda es: all(any(e["path"] == p and e["files_id"] is None for e in es)
                                                     for p in tombs))
        self.assertNotIn(jid, box[0].cleanup_pending)
        hang.release.set()
        end = time.monotonic() + 3
        while time.monotonic() < end and any(os.path.exists(p) for p in tombs):
            box[0].store.retry_pending_sweeps(deadline_s=2)
            time.sleep(0.05)
        self.assertFalse(any(os.path.exists(p) for p in tombs))
        self.assertTrue(box[0].store.flush_pending())
        poll_pending(self, self.data, lambda es: not any(e["path"] in tombs for e in es))

    def test_a_tombstone_check_that_times_out_does_not_stop_the_others(self):
        jid, _ = self.done_job()
        first, second = self.tombstones(jid, 2)
        self.hang(os.path, "islink", os.path.islink, lambda p: p == first)
        job = self.store.load(jid)
        with mock.patch.object(jobs, "LOCKED_IO_S", 0.2), mock.patch.object(jobs, "STAT_TIMEOUT_S", 0.2):
            t, box = on_thread(lambda: self.store.sweep_trash(job, jobs.Deadline(2)))
            t.join(3)
            self.assertFalse(t.is_alive())
        self.assertFalse(os.path.exists(second))
        self.assertIs(box[0], False)
        poll_pending(self, self.data, lambda es: any(e["path"] == first for e in es))

    def test_startup_returns_by_the_deadline_while_the_pending_file_hangs(self):
        jid, _ = self.done_job()
        with open(os.path.join(self.data, "pending-sweeps.json"), "w", encoding="utf-8") as f:
            json.dump([{"path": self.files_dir(jid) + ".trash-0badf00d", "output_dir": self.out,
                        "output_id": self.store.load(jid)["output_id"], "job": jid, "files_id": None,
                        "reason": "test"}], f)
        self.hang(jobs.Store, "_read_pending", jobs.Store._read_pending, lambda self_: True)
        self.release_lock()
        with mock.patch.object(server, "STARTUP_CLEANUP_S", 1.0), mock.patch.object(jobs, "PENDING_FLOOR_S", 0.1):
            t, box, t0 = self.start_server()
            t.join(4)
            self.assertFalse(t.is_alive())
        self.assertLess(time.monotonic() - t0, 3.0)

    def test_startup_with_hung_tombstones_and_a_stalled_writer_returns_by_the_deadline(self):
        jid, _ = self.done_job()
        tombs = self.tombstones(jid, 4)      # 4 x 0.3 s is more than the deadline: the orphan sweep never gets a turn
        self.hang_tomb_rmtree(jid)
        fsync = self.hang(os, "fsync", os.fsync,       # only the pending writer's: the tool registry's own writes go on
                          lambda fd_: threading.current_thread().name == "svf-maker-pending")
        self.release_lock()
        with mock.patch.object(jobs, "REMOVE_BOUND_S", 0.3), mock.patch.object(server, "STARTUP_CLEANUP_S", 1.0):
            t, box, t0 = self.start_server()
            t.join(4)
            self.assertFalse(t.is_alive())
            elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 2.6)     # deadline 1.0 + one floor + the flush floor + load slack; a floor per record would be 3.0+
        fsync.release.set()
        poll_pending(self, self.data, lambda es: all(any(e["path"] == p for e in es) for p in tombs), timeout=5)


class RetryRaceTest(unittest.TestCase):
    def test_a_rename_that_lands_between_the_look_and_the_fence_check_keeps_the_entry(self):
        tmp = tempfile.mkdtemp(prefix="svf-bounds-", dir=os.environ.get("TMPDIR") or tempfile.gettempdir())
        self.addCleanup(shutil.rmtree, tmp, True)
        store = jobs.Store(os.path.join(tmp, "data"))
        out = os.path.join(tmp, "out")
        os.mkdir(out)
        jid = "0123456789ab"
        fd = os.path.join(out, ".svf-maker-" + jid)
        tomb = fd + ".trash-0badf00d"
        os.mkdir(fd)
        hang = Hang(os.rename, lambda src, dst: src == fd)
        self.addCleanup(hang.release.set)
        with mock.patch.object(os, "rename", hang):
            with self.assertRaises(jobs.CallPending):
                jobs.rename_bounded(fd, tomb, 0.2)
            self.assertTrue(store._add_pending_many([{
                "path": tomb, "output_dir": out, "output_id": list(jobs.stat_id(out)), "job": jid, "files_id": None,
                "reason": "x", "from": fd}]))
            real = jobs.fs_bounded

            def look(op, path, timeout):
                answer = real(op, path, timeout)
                if op == "lexists" and path == tomb:         # the rename lands right after the look
                    hang.release.set()
                    end = time.monotonic() + 2
                    while time.monotonic() < end and jobs.mutation_pending(fd):
                        time.sleep(0.01)
                return answer
            with mock.patch.object(jobs, "fs_bounded", look):
                store.retry_pending_sweeps(deadline_s=3)
        self.assertTrue(os.path.isdir(tomb))
        self.assertTrue(store.flush_pending())
        with open(os.path.join(tmp, "data", "pending-sweeps.json"), encoding="utf-8") as f:
            entries = json.load(f)
        self.assertTrue(any(e["path"] == tomb for e in entries), entries)


if __name__ == "__main__":
    unittest.main()
