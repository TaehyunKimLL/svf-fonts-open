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
            self.wait_idle()
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


if __name__ == "__main__":
    unittest.main()
