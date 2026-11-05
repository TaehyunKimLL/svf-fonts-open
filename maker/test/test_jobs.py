#!/usr/bin/env python3
"""jobs.py tests: the job store, the worker thread and the subprocess runner.

Every step a test runs is a fake `python -c` script (the `argv` of a hand-built Step dict), so no tool runs here: the
script writes the step's output file, or fails, or sleeps. The upload is a copy of the repository's own
`svf/dos/NEODG16.SVF` (the shipped face a produced face is compared with), or a gzipped source for the F-gz tests.

  python3 -m unittest discover -s maker/test -p 'test_*.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gzip
import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock

import caps
import jobs
import quality
import test_recog_score
from sources import Sources

REPO = REPO_DIR
SVF = os.path.join(REPO, "svf")
TOOLS = os.path.join(REPO, "tools")
NEODG = os.path.join(SVF, "dos", "NEODG16.SVF")
HGKEY = os.path.join(SVF, "dos", "NEODG16G.SVF")

# A minimal ISO10646 BDF: the gzip tests only need the bytes a `.gz` source decompresses to.
BDF_TEXT = (b"STARTFONT 2.1\nFONT -test-iso-medium-r-normal--16-160-75-75-c-80-iso10646-1\nSIZE 16 75 75\n"
            b"FONTBOUNDINGBOX 16 16 0 -3\nCHARS 0\nENDFONT\n")

WAIT_S = 60


def read(path):
    """A file's bytes (a context manager, so a test leaves no file handle open)."""
    with open(path, "rb") as f:
        return f.read()


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def wait_until(cond, timeout=WAIT_S):
    """Wait for @p cond (a step's or a job's state) to become true, or fail the test."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met within %s s" % timeout)


def alive(pid):
    """Whether @p pid is a live (non-zombie) process, read from `/proc` (False once it is gone or reaped)."""
    try:
        with open("/proc/%d/stat" % pid, "rb") as f:
            fields = f.read().rsplit(b") ", 1)[1].split()
    except (OSError, IndexError):
        return False
    return fields[0] not in (b"Z", b"X", b"x")


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="svf-jobs-store-")
        self.store = jobs.Store(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_files_dir_and_sources_of_an_upload_job(self):
        job = self.store.create()
        self.assertEqual(self.store.files_dir(job), self.store.path(job["id"]))
        self.assertEqual(self.store.meta_dir(job["id"]), self.store.path(job["id"]))
        src = self.store.sources(job)
        self.assertEqual((src.kind, src.roots), ("upload", [self.store.path(job["id"], "upload")]))

    def test_materialized_argv_takes_sources(self):
        a, b = os.path.join(self.root, "A"), os.path.join(self.root, "B")
        for d in (a, b):
            os.makedirs(d)
        with open(os.path.join(b, "x.bdf.gz"), "wb") as f:
            f.write(gzip.compress(b"x"))
        s = Sources("local", [a, b])
        argv = jobs.materialized_argv([{"font": "f02", "argv": [["t", b + "/x.bdf.gz"]]}], s, "/w")
        self.assertEqual(argv, [["t", "/w/f02/x.bdf"]])

    def test_create_load_save_list_delete(self):
        j = self.store.create()
        self.assertEqual(len(j["id"]), 12)
        self.assertEqual(j["state"], "uploading")
        self.assertEqual(os.path.dirname(self.store.path(j["id"])), self.store.jobs_dir)
        for part in ("upload", "work", "out"):
            self.assertTrue(os.path.isdir(self.store.path(j["id"], part)), part)
        self.assertTrue(os.path.isfile(self.store.path(j["id"], "job.json")))
        j["state"] = "detected"
        self.store.save(j)
        loaded = self.store.load(j["id"])
        self.assertEqual(loaded["state"], "detected")
        self.assertFalse(os.path.exists(self.store.path(j["id"], "job.json.tmp")))
        self.assertGreaterEqual(loaded["updated"], loaded["created"])
        self.assertEqual([x["id"] for x in self.store.list()], [j["id"]])
        self.assertEqual(self.store.list()[0]["fonts"], 0)
        with self.assertRaises(KeyError):
            self.store.load("nothere")
        with self.assertRaises(KeyError):
            self.store.load("../../etc")
        with self.assertRaises(KeyError):
            self.store.load("0" * 12)
        self.store.delete(j["id"])
        self.assertEqual(self.store.list(), [])
        self.assertFalse(os.path.isdir(self.store.path(j["id"])))

    def test_list_is_newest_first_and_counts_fonts(self):
        first = self.store.create()
        second = self.store.create()
        self.store.update(second["id"], lambda job: job.update(fonts=[{"id": "f01"}, {"id": "f02"}]))
        self.assertEqual([x["id"] for x in self.store.list()], [second["id"], first["id"]])
        self.assertEqual(self.store.list()[0]["fonts"], 2)
        self.assertEqual(self.store.list()[1]["fonts"], 0)

    def test_delete_refuses_a_queued_or_running_job(self):
        j = self.store.create()
        for state in ("queued", "running"):
            self.store.update(j["id"], lambda job, state=state: job.update(state=state))
            with self.assertRaises(ValueError):
                self.store.delete(j["id"])
        self.store.update(j["id"], lambda job: job.update(state="done"))
        self.store.delete(j["id"])
        self.assertEqual(self.store.list(), [])


class RunCommandTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="svf-jobs-run-")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_exit_and_capture(self):
        r = jobs.run_command([sys.executable, "-c", "import sys; print('o'); sys.stderr.write('e'); sys.exit(3)"],
                             self.d, 10, threading.Event())
        self.assertEqual((r["exit"], r["stdout"].strip(), r["stderr"], r["error"]), (3, "o", "e", None))
        self.assertGreaterEqual(r["seconds"], 0.0)
        self.assertEqual(sorted(os.listdir(self.d)), ["stderr.txt", "stdout.txt"])

    def test_exit_zero(self):
        r = jobs.run_command([sys.executable, "-c", "print('ok')"], self.d, 10, threading.Event())
        self.assertEqual((r["exit"], r["stdout"].strip(), r["error"]), (0, "ok", None))

    def test_timeout_and_cancel_and_cap(self):
        r = jobs.run_command([sys.executable, "-c", "import time; time.sleep(30)"], self.d, 1, threading.Event())
        self.assertEqual(r["error"], "timeout")
        self.assertIsNone(r["exit"])
        self.assertLess(r["seconds"], 10)
        ev = threading.Event()
        ev.set()
        r = jobs.run_command([sys.executable, "-c", "import time; time.sleep(30)"], self.d, 30, ev)
        self.assertEqual(r["error"], "cancelled")
        self.assertLess(r["seconds"], 10)
        # the brief's flood: the child writes until the runner stops it, so the cap must be hard (I1). The run stops
        # within a poll of the cap being passed and the two files hold at most OUTPUT_CAP (+ one pipe buffer).
        big = jobs.run_command([sys.executable, "-c", "import sys\nwhile True:\n sys.stdout.write('x' * 65536)"],
                               self.d, 30, threading.Event())
        self.assertEqual(big["error"], "output over 4 MB")
        self.assertIsNone(big["exit"])
        self.assertLess(big["seconds"], 5.0)
        for name in ("stdout.txt", "stderr.txt"):
            size = os.path.getsize(os.path.join(self.d, name))
            self.assertLessEqual(size, jobs.OUTPUT_CAP + (64 << 10), name)
        self.assertGreaterEqual(os.path.getsize(os.path.join(self.d, "stdout.txt")), jobs.OUTPUT_CAP)
        self.assertLessEqual(len(big["stdout"].encode("utf-8")), jobs.OUTPUT_CAP)

    def test_a_timeout_kills_the_whole_process_group(self):
        script = ("import subprocess, sys, time\n"
                  "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
                  "print(p.pid, flush=True)\n"
                  "time.sleep(30)\n")
        r = jobs.run_command([sys.executable, "-c", script], self.d, 1, threading.Event())
        self.assertEqual(r["error"], "timeout")
        pid = int(r["stdout"].split()[0])
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and alive(pid):
            time.sleep(0.05)
        self.assertFalse(alive(pid), "the grandchild %s survived the timeout" % pid)

    def test_a_cap_stop_kills_a_grandchild_that_ignores_sigterm(self):
        script = ("import signal, subprocess, sys\n"
                  "p = subprocess.Popen([sys.executable, '-c', 'import signal, time; "
                  "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])\n"
                  "sys.stderr.write('%d\\n' % p.pid); sys.stderr.flush()\n"
                  "while True:\n sys.stdout.write('x' * 65536)\n")
        t0 = time.monotonic()
        r = jobs.run_command([sys.executable, "-c", script], self.d, 30, threading.Event())
        self.assertEqual(r["error"], "output over 4 MB")
        self.assertLess(time.monotonic() - t0, 15)
        pid = int(r["stderr"].split()[0])
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and alive(pid):
            time.sleep(0.05)
        self.assertFalse(alive(pid), "the grandchild %s survived the cap stop" % pid)

    def test_a_tool_past_the_cap_that_exits_leaves_no_grandchild_holding_a_pipe(self):
        script = ("import subprocess, sys\n"
                  "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                  "sys.stdout.write('x' * (%d + 70000)); sys.stdout.flush()\n" % jobs.OUTPUT_CAP)
        t0 = time.monotonic()
        r = jobs.run_command([sys.executable, "-c", script], self.d, 30, threading.Event())
        self.assertLess(time.monotonic() - t0, 15)            # the readers were not held by the sleeping grandchild
        self.assertIsNotNone(r)


class WorkerTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="svf-jobs-worker-")
        self.store = jobs.Store(self.root)
        self.worker = jobs.Worker(self.store, REPO, SVF, TOOLS)
        self.worker.start()

    def tearDown(self):
        for item in self.store.list():                      # leave nothing running behind the test
            if item["state"] in ("queued", "running"):
                try:
                    self.worker.cancel(item["id"])
                except KeyError:
                    pass
        self.worker.queue.join()
        self.worker.stop(timeout=30)
        self.worker.join(30)
        shutil.rmtree(self.root, ignore_errors=True)

    def job_with_steps(self, scripts, kinds=None, dest="new/fixture", source="NEODG16.SVF", src_bytes=None,
                       entry=None, extra_argv=None, family="Neo", style=""):
        """A job whose upload is @p source and whose `steps` are hand-built: one fake step per script.

        `kinds[i]` (default `precomposed`) is the step's kind. A `prepare` step writes `work/s0N/master.json`, every
        other one writes `work/s0N/NEWONE.SVF`; a `None` script makes the step a copy (`argv == []`). A script's
        `argv` is `[python, -c, <script>, <the output's absolute path>, *extra_argv]`, with `NEODG`/`HGKEY` in the
        script text replaced by the two repository paths, so `sys.argv[1]` is the output. @p entry overrides the one
        font entry's fields. The settings select the font with @p dest, the two names and a `text` licence.
        """
        kinds = list(kinds or ["precomposed"] * len(scripts))
        self.assertEqual(len(kinds), len(scripts))
        j = self.store.create()
        job_dir = self.store.path(j["id"])
        upload = os.path.join(job_dir, "upload")
        os.makedirs(upload, exist_ok=True)
        with open(os.path.join(upload, source), "wb") as f:
            f.write(src_bytes if src_bytes is not None else read(NEODG))
        font = {"id": "f01", "path": source, "face_index": 0, "format": "svf", "label": "SVF",
                "source_kind": "svf-precomposed", "family": family, "style": style, "version": "1.0",
                "sizes": [16], "sizes_fixed": False,
                "coverage": {"ascii": 95, "ks2350": 2350, "all": 11172, "compat": 51}, "jamo": "none",
                "dos": None, "bdf": None,
                "svf": {"version": 2, "flags": 1, "bpp": 1, "cell": [16, 16], "ascent": 12, "glyphs": 2905},
                "licences": [], "companions": [], "error": None}
        font.update(entry or {})
        steps = []
        for i, (script, kind) in enumerate(zip(scripts, kinds), 1):
            sid = "s%02d" % i
            os.makedirs(os.path.join(job_dir, "work", sid), exist_ok=True)
            if kind == "prepare":
                output, name, layout = "work/%s/master.json" % sid, None, "844"
            else:
                output, name = "work/%s/NEWONE.SVF" % sid, "NEWONE.SVF"
                layout = "844" if kind == "jamo" else None
            if script is None:
                argv = []
            else:
                # a `python -c` script has no implicit `sys`; the plan's scripts use `sys.argv[1]`, so import it
                text = ("import sys\n" + script).replace("NEODG", repr(NEODG)).replace("HGKEY", repr(HGKEY))
                argv = [[sys.executable, "-c", text, os.path.join(job_dir, output)] + list(extra_argv or [])]
            steps.append({"id": sid, "font": "f01", "kind": kind,
                          "size": None if kind == "prepare" else 16, "bpp": None if kind == "prepare" else 1,
                          "layout": layout, "name": name, "argv": argv, "output": output, "state": "pending",
                          "exit": None, "seconds": None, "error": None, "stderr_tail": "", "facts": None,
                          "quality": None, "identical_to": None, "report": None,
                          "identity": None})
        eff = {"selected": True, "experimental": True, "dos_layout": None, "latin_companion": None,
               "licence": {"kind": "text", "text": "x"}, "licence_name": "LICNEO.TXT", "note_name": "NEO.TXT",
               "names": {"precomposed/16/1": "NEWONE.SVF", "jamo/16/1": "NEWONE.SVF"}, "dest": dest,
               "kinds": ["precomposed", "jamo"], "sizes": [16], "bpp": [1]}
        j.update(state="detected",                        # detection is done: the job is ready to be enqueued
                 fonts=[font],
                 settings={"batch": {"dest": "dos", "kinds": ["precomposed"], "layout": "844", "sizes": [16],
                                     "bpp": [1, 2], "range": "2350", "preset": "plain",
                                     "options": {"mkfont": {"cell": None, "ascent": None, "mono_hint": False,
                                                            "clip_cell": False, "space_advance": None},
                                                 "jamoset": {"embolden": False, "symbols": False}}},
                           "fonts": {"f01": eff}},
                 steps=steps)
        self.store.save(j)
        return self.store.load(j["id"])

    def wait_for(self, job_id):
        wait_until(lambda: self.store.load(job_id)["state"] in ("done", "failed"))
        return self.store.load(job_id)

    def test_a_tool_that_writes_nothing_does_not_pass_on_an_old_output(self):
        j = self.job_with_steps(["pass"])
        old = self.store.path(j["id"], "work", "s01", "NEWONE.SVF")
        with open(old, "wb") as fh:
            fh.write(read(NEODG))                           # what an earlier run of this job left behind
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertEqual(j["steps"][0]["state"], "failed")
        self.assertEqual(j["steps"][0]["error"], "no output")

    def test_runs_fifo_fails_step_not_job_and_zips(self):
        j = self.job_with_steps(["open(sys.argv[1],'wb').write(open(NEODG,'rb').read()[:-1]+b'\\x01')",
                                 "sys.exit(2)"])
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertEqual(j["state"], "done")
        self.assertEqual([s["state"] for s in j["steps"]], ["done", "failed"])
        self.assertEqual(j["result"]["failed_steps"], [j["steps"][1]["id"]])
        self.assertTrue(os.path.isfile(self.store.path(j["id"], j["result"]["zip"])))
        self.assertIsNotNone(j["steps"][0]["facts"])
        self.assertNotIn("preview", j["steps"][0])                  # the page draws the face itself (WASM)
        self.assertIsNotNone(quality.face_facts(read_bytes(self.store.path(j["id"], j["steps"][0]["output"]))))
        self.assertFalse(os.path.exists(self.store.path(j["id"], "work", j["steps"][0]["id"], "preview.png")))
        self.assertIn("## s01", read_text(self.store.path(j["id"], "log.md")))
        self.assertIn("## s02", read_text(self.store.path(j["id"], "log.md")))
        self.assertEqual(j["steps"][1]["error"], "exit 2")
        self.assertEqual(j["steps"][1]["stderr_tail"], "")

    def test_runs_jobs_in_fifo_order(self):
        order = os.path.join(self.root, "order.txt")
        script = "import sys; open(%r,'a').write(sys.argv[2]); open(sys.argv[1],'wb').write(open(NEODG,'rb').read())"
        first = self.job_with_steps([script % order], extra_argv=["1"])
        second = self.job_with_steps([script % order], extra_argv=["2"])
        self.worker.enqueue(first["id"])
        self.worker.enqueue(second["id"])
        self.wait_for(second["id"])
        self.assertEqual(read_text(order), "12")
        self.assertEqual([self.store.load(first["id"])["state"], self.store.load(second["id"])["state"]],
                         ["done", "done"])

    def test_a_stale_report_is_removed_before_a_rerun(self):
        j = self.job_with_steps(["sys.exit(1)"])
        stale = self.store.path(j["id"], "work", "s01", "report.json")
        with open(stale, "w") as fh:
            fh.write("{}")
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertEqual(j["steps"][0]["state"], "failed")
        self.assertFalse(os.path.exists(stale))

    def test_prepare_and_copy_steps(self):
        j = self.job_with_steps(["open(sys.argv[1],'w').write('{}')", None], kinds=["prepare", "precomposed"])
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertEqual([s["state"] for s in j["steps"]], ["done", "done"])
        self.assertIsNone(j["steps"][0]["facts"])
        self.assertNotIn("preview", j["steps"][0])
        self.assertIsNone(j["steps"][0]["quality"])
        self.assertIsNotNone(j["steps"][1]["facts"])
        self.assertEqual(j["steps"][1]["identical_to"], "dos/NEODG16.SVF")
        self.assertEqual(j["result"]["written"], [])
        self.assertEqual(j["result"]["skipped"],
                         [{"name": "svf/new/fixture/NEWONE.SVF", "identical_to": "dos/NEODG16.SVF"}])
        self.assertIn("prepare", read_text(self.store.path(j["id"], "log.md")))

    def test_failed_prepare_fails_its_renders(self):
        j = self.job_with_steps(["sys.exit(1)", "pass"], kinds=["prepare", "jamo"])
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertEqual([s["state"] for s in j["steps"]], ["failed", "failed"])
        self.assertEqual(j["steps"][0]["error"], "exit 1")
        self.assertEqual(j["steps"][1]["error"], "master failed")
        self.assertEqual((j["state"], j["error"]), ("failed", "no successful step"))

    def test_all_failed_is_failed(self):
        j = self.job_with_steps(["sys.exit(1)"])
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertEqual((j["state"], j["error"]), ("failed", "no successful step"))
        self.assertEqual(j["steps"][0]["state"], "failed")

    def test_a_step_with_no_output_fails(self):
        j = self.job_with_steps(["pass"])
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertEqual((j["steps"][0]["state"], j["steps"][0]["error"]), ("failed", "no output"))
        self.assertEqual((j["state"], j["error"]), ("failed", "no successful step"))

    def test_bytes_that_are_not_a_face_fail_the_step(self):
        j = self.job_with_steps(["open(sys.argv[1],'wb').write(b'nope')"])
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertEqual(j["steps"][0]["state"], "failed")
        self.assertIn("not an SVFN v3 font", j["steps"][0]["error"])
        self.assertNotIn("preview", j["steps"][0])
        self.assertIn("error: ", read_text(self.store.path(j["id"], "log.md")))

    def test_a_name_clash_fails_the_job_with_the_path(self):
        j = self.job_with_steps(["open(sys.argv[1],'wb').write(open(NEODG,'rb').read()[:-1]+b'\\x01')"], dest="dos")
        j["steps"][0]["name"] = "NEODG16.SVF"               # the face the checkout already holds, with other bytes
        self.store.save(j)
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertEqual((j["state"], j["error"]), ("failed", "name clash: dos/NEODG16.SVF"))

    def test_a_refused_note_fails_the_job_with_the_message(self):
        j = self.job_with_steps(["open(sys.argv[1],'wb').write(open(NEODG,'rb').read()[:-1]+b'\\x01')"],
                                style="x" * 600)
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertEqual(j["state"], "failed")
        self.assertEqual(j["error"], "note for f01: note_text: style has a line longer than 512 bytes")
        self.assertIn("note for f01", read_text(self.store.path(j["id"], "log.md")))

    def test_job_timeout_fails_the_remaining_steps(self):
        j = self.job_with_steps(["pass", "pass"])
        with mock.patch.object(jobs, "JOB_TIMEOUT", 0.0):
            self.worker.enqueue(j["id"])
            j = self.wait_for(j["id"])
        self.assertEqual([s["error"] for s in j["steps"]], ["job timeout", "job timeout"])
        self.assertEqual([s["state"] for s in j["steps"]], ["failed", "failed"])
        self.assertEqual((j["state"], j["error"]), ("failed", "no successful step"))

    def test_cancel_queued_and_running(self):
        slow = self.job_with_steps(["import time; time.sleep(20)"])
        q = self.job_with_steps(["pass"])
        self.worker.enqueue(slow["id"])
        self.worker.enqueue(q["id"])
        wait_until(lambda: self.store.load(slow["id"])["state"] == "running")
        self.assertEqual(self.worker.position(q["id"]), 1)
        self.assertEqual(self.worker.cancel(q["id"]), "cancelled")
        self.assertEqual(self.store.load(q["id"])["error"], "cancelled")
        self.assertIsNone(self.worker.position(q["id"]))
        self.assertEqual(self.worker.cancel(q["id"]), "not running")
        self.assertEqual(self.worker.cancel(slow["id"]), "signalled")
        wait_until(lambda: self.store.load(slow["id"])["state"] == "failed")
        j = self.store.load(slow["id"])
        self.assertEqual(j["error"], "cancelled")
        self.assertEqual(j["steps"][0]["error"], "cancelled")
        self.assertIsNone(j["result"])

    def test_cancel_of_a_queued_job_is_atomic_with_its_dequeue(self):
        release, entered = threading.Event(), threading.Event()
        original = jobs.Worker._claim

        def slow_claim(worker_self, job_id):
            entered.set()                       # the pop is done; hold the worker until the test cancels
            release.wait(WAIT_S)
            return original(worker_self, job_id)

        ran = []
        with mock.patch.object(jobs.Worker, "_claim", slow_claim), \
                mock.patch.object(jobs.Worker, "run_job", lambda worker_self, jid: ran.append(jid)):
            for _ in range(30):
                j = self.job_with_steps(["pass"])
                entered.clear()
                release.clear()
                self.worker.enqueue(j["id"])
                self.assertTrue(entered.wait(WAIT_S), "the worker never dequeued the job")
                self.assertEqual(self.worker.cancel(j["id"]), "cancelled")
                release.set()
                wait_until(lambda: self.worker.queue.unfinished_tasks == 0)
                self.assertEqual(self.store.load(j["id"])["state"], "failed")
        self.assertEqual(ran, [], "a cancelled queued job ran")

    def test_a_missing_tool_fails_the_job_not_the_worker(self):
        j = self.job_with_steps(["pass"])
        j["steps"][0]["argv"] = [["/nonexistent/svf-tool-xyz", "a"]]     # Popen raises FileNotFoundError
        self.store.save(j)
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertEqual(j["state"], "failed")
        self.assertIn("FileNotFoundError", j["error"])
        self.assertEqual(j["steps"][0]["state"], "failed")               # never left running
        self.assertTrue(self.worker.is_alive())

    def test_a_write_zip_oserror_fails_the_job_not_the_worker(self):
        j = self.job_with_steps(["open(sys.argv[1],'wb').write(open(NEODG,'rb').read())"])

        def full(*args, **kwargs):
            raise OSError(28, "No space left on device")

        with mock.patch.object(jobs.zipout, "write_zip", full):
            self.worker.enqueue(j["id"])
            j = self.wait_for(j["id"])
        self.assertEqual(j["state"], "failed")
        self.assertIn("OSError", j["error"])
        self.assertIn("No space left on device", j["error"])
        self.assertTrue(self.worker.is_alive())

    def test_a_retain_failure_does_not_kill_the_worker(self):
        script = "open(sys.argv[1],'wb').write(open(NEODG,'rb').read())"
        with mock.patch.object(jobs.Worker, "retain", side_effect=OSError("housekeeping")):
            first = self.job_with_steps([script])
            self.worker.enqueue(first["id"])
            self.assertEqual(self.wait_for(first["id"])["state"], "done")
            self.assertTrue(self.worker.is_alive(), "an exception from retain() killed the worker")
            second = self.job_with_steps([script])
            self.worker.enqueue(second["id"])
            self.assertEqual(self.wait_for(second["id"])["state"], "done")

    def test_a_zip_failure_keeps_its_own_message_over_a_job_timeout(self):
        message = "zipout: the licence of f01 cannot be read"

        def value_error(job, job_dir, *args, **kwargs):
            raise ValueError(message)

        def note_refused(job, job_dir, *args, **kwargs):
            job["error"] = "note for f01: %s" % message      # what zipout sets before raising NoteRefused
            raise jobs.zipout.NoteRefused(message)

        for refuse in (value_error, note_refused):
            j = self.job_with_steps(["pass", "pass"])
            with mock.patch.object(jobs.zipout, "write_zip", refuse), \
                    mock.patch.object(jobs, "JOB_TIMEOUT", 0.0):
                self.worker.enqueue(j["id"])
                j = self.wait_for(j["id"])
            self.assertEqual(j["state"], "failed")
            self.assertEqual(j["error"], message)

    def test_tool_text_keeps_only_the_exact_verdict_format(self):
        verdict = "check: composed 11172 syllables from 5 glyphs, JSET 501 bytes"
        text = "\n".join([verdict, "check: QZMARKERQZ", "verify QZMARKERQZ", "check: composed 11172 syllables from 5 glyphs, "
                           "JSET 501 bytes QZMARKERQZ", "font QZMARKERQZ"])
        kept = jobs.tool_text(text, True)
        self.assertIn(verdict, kept)
        self.assertNotIn("QZMARKERQZ", kept)
        self.assertIn("4 line(s) not kept", kept)
        self.assertEqual(jobs.tool_text(verdict + "; identical to johab844.py", True), verdict + "; identical to johab844.py")
        self.assertEqual(jobs.tool_text(text, False), text)                       # an upload job keeps it all

    def test_needs_cascade(self):
        j = self.job_with_steps(["sys.exit(3)", "open(sys.argv[1],'wb').write(open(NEODG,'rb').read())"],
                                kinds=["source", "jamo"])

        def edit(job):
            job["steps"][0]["font"] = "f02"                 # a companion's source step, not f01's own
            job["steps"][1]["needs"] = ["s01"]
        self.store.update(j["id"], edit)
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        first, second = j["steps"]
        self.assertEqual(first["state"], "failed")
        self.assertEqual((second["state"], second["error"]), ("failed", "companion source failed"))
        self.assertFalse(os.path.exists(self.store.path(j["id"], "work", "s02", "NEWONE.SVF")))   # its argv never ran

    def test_check_steps_refuses_a_later_needs(self):
        import server
        steps = [{"id": "s01", "output": "work/s01/x.svf", "font": "f01", "needs": ["s02"]},
                 {"id": "s02", "output": "work/s02/x.svf", "font": "f01", "needs": []}]
        fd = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, fd, ignore_errors=True)
        with self.assertRaises(ValueError):
            server.Handler._check_steps(None, fd, Sources("upload", [fd]), [], steps)
        steps[0]["needs"] = []
        steps[1]["needs"] = ["s01"]
        server.Handler._check_steps(None, fd, Sources("upload", [fd]), [], steps)         # earlier: fine

    def test_stop_ends_the_thread(self):
        self.assertTrue(self.worker.is_alive())
        self.assertTrue(self.worker.stop(timeout=10))
        self.worker.join(10)
        self.assertFalse(self.worker.is_alive())
        self.assertTrue(self.worker.stop(timeout=10))           # idempotent, also on a dead thread

    def test_stop_with_a_queued_job_does_not_run_it(self):
        j = self.job_with_steps(["import time; time.sleep(30)", "pass"])
        self.worker.enqueue(j["id"])
        wait_until(lambda: self.store.load(j["id"])["state"] == "running")
        self.worker.stop(timeout=20)
        self.worker.join(10)
        self.assertFalse(self.worker.is_alive())

    def test_enqueue_refuses_a_job_that_is_not_ready(self):
        j = self.job_with_steps(["pass"])
        for state in ("uploading", "running", "done"):
            self.store.update(j["id"], lambda job, state=state: job.update(state=state))
            with self.assertRaises(ValueError):
                self.worker.enqueue(j["id"])
        self.assertIsNone(self.worker.position(j["id"]))

    def test_enqueue_is_idempotent_for_a_queued_job(self):
        slow = self.job_with_steps(["import time; time.sleep(20)"])
        j = self.job_with_steps(["pass"])
        self.worker.enqueue(slow["id"])
        wait_until(lambda: self.store.load(slow["id"])["state"] == "running")
        self.worker.enqueue(j["id"])
        self.worker.enqueue(j["id"])                        # a double POST /run must not add a second entry
        self.assertEqual(self.worker.position(j["id"]), 1)
        self.assertEqual(self.worker._queued.count(j["id"]), 1)
        self.assertEqual(self.store.load(j["id"])["state"], "queued")

    def test_enqueue_returns_the_real_queue_position(self):
        """W13: `enqueue` answers with the position it gave the job (1 for the next to run)."""
        slow = self.job_with_steps(["import time; time.sleep(20)"])
        a = self.job_with_steps(["pass"])
        b = self.job_with_steps(["pass"])
        self.assertEqual(self.worker.enqueue(slow["id"]), 1)
        wait_until(lambda: self.store.load(slow["id"])["state"] == "running")
        self.assertEqual(self.worker.enqueue(a["id"]), 1)
        self.assertEqual(self.worker.enqueue(b["id"]), 2)
        self.assertEqual(self.worker.enqueue(a["id"]), 1)   # a repeat keeps its own place

    def test_recover_marks_running_interrupted_and_requeues(self):
        a = self.job_with_steps(["pass"])
        b = self.job_with_steps(["pass"])
        self.store.update(a["id"], lambda j: j.update(state="running"))
        self.store.update(b["id"], lambda j: j.update(state="queued"))
        w = jobs.Worker(self.store, REPO, SVF, TOOLS)
        w.recover()
        self.assertEqual(self.store.load(a["id"])["state"], "failed")
        self.assertEqual(self.store.load(a["id"])["error"], "interrupted")
        self.assertEqual(w.position(b["id"]), 1)

    def test_retention(self):
        ids = [self.store.create()["id"] for _ in range(22)]
        for i in ids[:21]:
            self.store.update(i, lambda j: j.update(state="done"))
        self.store.update(ids[21], lambda j: j.update(state="queued"))
        self.worker.retain()
        left = {x["id"] for x in self.store.list()}
        self.assertEqual(len(left), 20)
        self.assertIn(ids[21], left)
        self.assertNotIn(ids[0], left)
        self.assertNotIn(ids[1], left)

    def test_retention_keeps_a_job_older_than_max_age_when_it_is_not_the_oldest(self):
        old = self.store.create()
        self.store.update(old["id"], lambda j: j.update(state="done", created=time.time() - jobs.MAX_AGE - 60))
        self.worker.retain()
        self.assertEqual(self.store.list(), [])

    def run_identity(self, caps_value, stub_kwargs=None, recog_timeout=None, arrays="lists", flags=(), steps=None):
        """A jamo step run with the stub recogniser (a directory of its own) under @p caps_value."""
        stub = tempfile.mkdtemp(prefix="svf-recog-stub-")
        self.addCleanup(shutil.rmtree, stub, True)
        test_recog_score.write_stub(stub, **(stub_kwargs or {}))
        for flag in flags:
            open(os.path.join(stub, flag), "w").close()
        patches = [mock.patch.dict(os.environ, {"SVF_RECOG_DIR": stub}),
                   mock.patch.object(caps, "recog_dir", return_value=stub),
                   mock.patch.object(jobs, "RECOG_ARRAYS", arrays)]
        if recog_timeout is not None:
            patches.append(mock.patch.object(jobs, "RECOG_TIMEOUT", recog_timeout))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.worker.caps = caps_value
        j = self.job_with_steps(["open(sys.argv[1],'wb').write(open(HGKEY,'rb').read())"], kinds=["jamo"],
                                **(steps or {}))
        self.worker.enqueue(j["id"])
        return self.wait_for(j["id"])

    def test_stop_kills_the_previews_bakes_and_marks_the_job_interrupted(self):
        calls = []
        with mock.patch.object(jobs.preview, "kill_all", side_effect=lambda: calls.append(1) or 0):
            j = self.job_with_steps(["import time; time.sleep(60)"])
            self.worker.enqueue(j["id"])
            wait_until(lambda: self.store.load(j["id"])["steps"][0]["state"] == "running")
            self.assertTrue(self.worker.stop(30))
        self.assertTrue(calls)
        j = self.store.load(j["id"])
        self.assertEqual((j["state"], j["error"]), ("failed", "interrupted"))
        self.assertEqual(j["steps"][0]["error"], "interrupted")

    def test_a_copy_route_rerun_without_the_recogniser_drops_the_old_scores(self):
        """A copy step (an uploaded SVF jamo set) returns before any tool runs: its stale scores go too."""
        copy = {"scripts": None}
        stub = tempfile.mkdtemp(prefix="svf-recog-stub-")
        self.addCleanup(shutil.rmtree, stub, True)
        test_recog_score.write_stub(stub)
        for p in (mock.patch.dict(os.environ, {"SVF_RECOG_DIR": stub}), mock.patch.object(caps, "recog_dir", return_value=stub),
                  mock.patch.object(jobs, "RECOG_ARRAYS", "lists")):
            p.start()
            self.addCleanup(p.stop)
        self.worker.caps = {"recog": True}
        j = self.job_with_steps([None], kinds=["jamo"], src_bytes=read(HGKEY))
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        step = j["steps"][0]
        path = self.store.path(j["id"], "work", step["id"], "identity.json")
        self.assertTrue(step["identity"]["available"], step)
        self.assertTrue(os.path.isfile(path))
        self.worker.caps = {"recog": False}
        self.store.update(j["id"], lambda job: job.update(state="detected"))
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertFalse(j["steps"][0]["identity"]["available"])
        self.assertFalse(os.path.exists(path))

    def test_identity_written_for_jamo_steps(self):
        j = self.run_identity({"wasm": False, "mask_libs": False, "recog": True})
        step = j["steps"][0]
        self.assertEqual(step["state"], "done", step)
        self.assertEqual(step["identity"]["identity"], "pass")
        self.assertTrue(step["identity"]["available"])
        self.assertTrue(os.path.isfile(self.store.path(j["id"], "work", step["id"], "identity.json")))
        self.assertIn("identity: pass", read_text(self.store.path(j["id"], "log.md")))

    def test_identity_timeout_keeps_the_step_done(self):
        j = self.run_identity({"recog": True}, stub_kwargs={"sleep": 5}, recog_timeout=1)
        step = j["steps"][0]
        self.assertEqual(step["state"], "done")
        self.assertFalse(step["identity"]["available"])
        self.assertIn("timed out", step["identity"]["error"])
        self.assertIn("identity: error", read_text(self.store.path(j["id"], "log.md")))

    def test_identity_where_every_syllable_is_unscored_is_an_error(self):
        j = self.run_identity({"recog": True}, flags=("allnan.flag",))
        step = j["steps"][0]
        self.assertEqual(step["state"], "done")
        self.assertFalse(step["identity"]["available"])
        self.assertIn("unscored", step["identity"]["error"])
        self.assertNotIn("identity", step["identity"])               # no verdict, not 'warn'
        self.assertIn("identity: error", read_text(self.store.path(j["id"], "log.md")))

    def test_a_rerun_without_the_recogniser_drops_the_old_scores(self):
        j = self.run_identity({"recog": True})
        step = j["steps"][0]
        path = self.store.path(j["id"], "work", step["id"], "identity.json")
        self.assertTrue(os.path.isfile(path))
        self.assertTrue(step["identity"]["available"])
        self.worker.caps = {"recog": False}
        self.store.update(j["id"], lambda job: job.update(state="detected"))
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        step = j["steps"][0]
        self.assertEqual(step["state"], "done")
        self.assertFalse(step["identity"]["available"])
        self.assertFalse(os.path.exists(path))                       # nothing of the previous build's scores is left

    def test_identity_unavailable_without_recog(self):
        j = self.run_identity({"recog": False})
        step = j["steps"][0]
        self.assertEqual(step["state"], "done")
        self.assertFalse(step["identity"]["available"])
        self.assertIn("structural", step["identity"])
        self.assertFalse(os.path.exists(self.store.path(j["id"], "work", step["id"], "identity.json")))
        self.assertIn("identity check unavailable", read_text(self.store.path(j["id"], "log.md")))

    def test_a_precomposed_step_has_no_identity(self):
        j = self.job_with_steps(["open(sys.argv[1],'wb').write(open(NEODG,'rb').read())"])
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertIsNone(j["steps"][0]["identity"])

    def test_jamo_step_measures_against_its_reference(self):
        j = self.job_with_steps(["open(sys.argv[1],'wb').write(open(HGKEY,'rb').read())"], kinds=["jamo"])
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        step = j["steps"][0]
        self.assertEqual(step["state"], "done")
        self.assertEqual(step["facts"]["jset"]["sets"], [6, 2, 1])
        self.assertEqual(step["quality"]["compared"], 2357)       # the source SVF's own precomposed syllables
        self.assertLess(0, step["quality"]["all"])
        self.assertLess(step["quality"]["all"], 1)
        self.assertNotIn("preview", step)
        self.assertIsNotNone(quality.face_facts(read_bytes(self.store.path(j["id"], step["output"]))))

    def test_a_face_with_no_usable_jamo_set_is_not_measured(self):
        j = self.job_with_steps(["open(sys.argv[1],'wb').write(open(NEODG,'rb').read()[:-1]+b'\\x01')"],
                                kinds=["jamo"])
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        self.assertEqual(j["steps"][0]["state"], "done")
        self.assertIsNone(j["steps"][0]["quality"])               # no usable jamo set: scored as precomposed
        self.assertEqual(j["steps"][0]["facts"]["jset"], None)

    # ---- F-gz: a `.gz` source is decompressed before any tool reads it ------------------------------------------

    def test_gzip_copy_step_copies_the_decompressed_source(self):
        gz_bytes = gzip.compress(BDF_TEXT)
        j = self.job_with_steps([None], kinds=["prepare"], source="iso.bdf.gz", src_bytes=gz_bytes,
                                entry={"gzip": True, "format": "bdf", "label": "BDF", "source_kind": "bdf-iso10646",
                                       "sizes_fixed": True, "svf": None})
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        step = j["steps"][0]
        self.assertEqual(step["state"], "done")
        self.assertEqual(read(self.store.path(j["id"], step["output"])), BDF_TEXT)
        self.assertEqual(read(self.store.path(j["id"], "work", "f01", "iso.bdf")), BDF_TEXT)
        self.assertEqual(read(self.store.path(j["id"], "upload", "iso.bdf.gz")), gz_bytes)   # the upload is untouched

    def test_gzip_source_paths_are_rewritten_for_the_tools(self):
        marker = os.path.join(self.root, "src-path.txt")
        script = ("import sys; open(%r,'w').write(sys.argv[2]); "
                  "open(sys.argv[1],'wb').write(open(NEODG,'rb').read())" % marker)
        j = self.job_with_steps([script], source="iso.bdf.gz", src_bytes=gzip.compress(BDF_TEXT),
                                entry={"gzip": True, "format": "bdf", "label": "BDF", "source_kind": "bdf-iso10646",
                                       "sizes_fixed": True, "svf": None})
        # the argv is built by hand: the upload's `.gz` path is what `settings.plan_steps` passes to a tool
        step = j["steps"][0]
        upload_gz = self.store.path(j["id"], "upload", "iso.bdf.gz")
        step["argv"] = [[sys.executable, "-c", script.replace("NEODG", repr(NEODG)),
                         self.store.path(j["id"], step["output"]), upload_gz]]
        self.store.save(j)
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        step = j["steps"][0]
        self.assertEqual(step["state"], "done")
        self.assertNotIn(upload_gz, step["argv"][0])              # the argv the log names is the real one
        self.assertIn(self.store.path(j["id"], "work", "f01", "iso.bdf"), step["argv"][0])
        plain = read_text(marker)
        self.assertEqual(plain, self.store.path(j["id"], "work", "f01", "iso.bdf"))
        self.assertEqual(read(plain), BDF_TEXT)

    def test_a_gz_source_is_rewritten_through_a_symlinked_upload_path(self):
        marker = os.path.join(self.root, "src-path.txt")
        script = ("import sys; open(%r,'w').write(sys.argv[2]); "
                  "open(sys.argv[1],'wb').write(open(NEODG,'rb').read())" % marker)
        j = self.job_with_steps([script], source="iso.bdf.gz", src_bytes=gzip.compress(BDF_TEXT),
                                entry={"gzip": True, "format": "bdf", "label": "BDF", "source_kind": "bdf-iso10646",
                                       "sizes_fixed": True, "svf": None})
        link = os.path.join(self.root, "linked-upload")
        os.symlink(self.store.path(j["id"], "upload"), link)
        step = j["steps"][0]
        # a differently spelled but equivalent upload path: `settings.plan_steps` was built from a symlinked dir here
        step["argv"] = [[sys.executable, "-c", script.replace("NEODG", repr(NEODG)),
                         self.store.path(j["id"], step["output"]), os.path.join(link, "iso.bdf.gz")]]
        self.store.save(j)
        self.worker.enqueue(j["id"])
        j = self.wait_for(j["id"])
        step = j["steps"][0]
        self.assertEqual(step["state"], "done")
        self.assertNotIn("iso.bdf.gz", step["argv"][0])
        self.assertIn(self.store.path(j["id"], "work", "f01", "iso.bdf"), step["argv"][0])
        self.assertEqual(read_text(marker), self.store.path(j["id"], "work", "f01", "iso.bdf"))
        self.assertEqual(read(read_text(marker)), BDF_TEXT)

    def test_materialized_argv_rewrites_a_gz_source_spelled_differently(self):
        upload = self.store.path("0" * 12, "upload")
        work = self.store.path("0" * 12, "work")
        steps = [{"font": "f01", "argv": [["tool", upload + "//iso.bdf.gz"], ["tool", "other.bdf"]]},
                 {"font": "f02", "argv": [["tool", "plain.bdf"]]},
                 {"font": "f01", "argv": []}]
        self.assertEqual(jobs.materialized_argv(steps, upload + "/", work),
                         [["tool", os.path.join(work, "f01", "iso.bdf")], ["tool", "other.bdf"],
                          ["tool", "plain.bdf"]])

    def test_materialized_argv_leaves_a_pcf_gz_source_alone(self):
        upload = self.store.path("0" * 12, "upload")
        work = self.store.path("0" * 12, "work")
        steps = [{"font": "f01", "argv": [["tool", os.path.join(upload, "x.pcf.gz")]]}]
        self.assertEqual(jobs.materialized_argv(steps, upload, work),
                         [["tool", os.path.join(upload, "x.pcf.gz")]])


if __name__ == "__main__":
    unittest.main()
