#!/usr/bin/env python3
"""toolreg.py tests: the <data_root>/tools.pids registry the two runners write, and its reap at start-up.

  python3 -m unittest discover -s maker/test -p 'test_toolreg.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import glob
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

import fixtures
import jobs
import preview
import server
import toolreg
import toolrun


def wait_until(cond, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def lines(reg):
    try:
        with open(reg.path) as f:
            return [l for l in f.read().splitlines() if l]
    except OSError:
        return []


class RegBase(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: self.assertIsNone(toolreg.active()))      # registered first: runs after the others
        self.tmp = tempfile.mkdtemp(prefix="svf-toolreg-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.reg = toolreg.Registry(os.path.join(self.tmp, "tools.pids"))
        self.addCleanup(toolreg.deactivate, self.reg)

    def sleeper(self, code="import time; time.sleep(60)", argv0=None):
        """A python child in its own session; killed in cleanup and waited."""
        argv = [sys.executable, "-c", code]
        proc = subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL)

        def cleanup():
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
        self.addCleanup(cleanup)
        return proc

    def line_for(self, proc, start=None, argv0="python3"):
        start = toolreg.start_time(proc.pid) if start is None else start
        return "%d %d %s %s" % (proc.pid, proc.pid, start, argv0)

    def put(self, *entries):
        with open(self.reg.path, "w") as f:
            f.write("".join(e + "\n" for e in entries))


class RegistryTest(RegBase):
    def test_line_while_running_none_after(self):
        toolreg.activate(self.reg)
        cancel = threading.Event()
        out = []
        t = threading.Thread(target=lambda: out.append(jobs.run_command(
            [sys.executable, "-c", "import time; time.sleep(2)"], self.tmp, 30, cancel)))
        t.start()
        self.assertTrue(wait_until(lambda: len(lines(self.reg)) == 1))
        pid = int(lines(self.reg)[0].split()[1])
        self.assertTrue(toolrun.alive(pid))
        t.join(20)
        self.assertEqual(out[0]["exit"], 0)
        self.assertEqual(lines(self.reg), [])

    def test_run_bounded_registers(self):
        toolreg.activate(self.reg)
        t = threading.Thread(target=lambda: preview.run_bounded(
            [sys.executable, "-c", "import time; time.sleep(2)"], self.tmp, 30))
        t.start()
        self.assertTrue(wait_until(lambda: len(lines(self.reg)) == 1))
        t.join(20)
        self.assertEqual(lines(self.reg), [])

    def test_inactive_is_noop(self):
        res = jobs.run_command([sys.executable, "-c", "pass"], self.tmp, 30, threading.Event())
        self.assertEqual(res["exit"], 0)
        self.assertFalse(os.path.exists(self.reg.path))
        self.assertEqual(glob.glob(os.path.join(self.tmp, "**", "tools.pids"), recursive=True), [])

    def test_unregister_uses_the_registering_registry(self):
        other = toolreg.Registry(os.path.join(self.tmp, "other.pids"))
        self.addCleanup(toolreg.deactivate, other)
        proc = self.sleeper()
        toolreg.activate(self.reg)
        toolreg.register(proc)
        self.assertEqual(len(lines(self.reg)), 1)
        toolreg.activate(other)
        other.register(self.sleeper())
        toolreg.unregister(proc)
        self.assertEqual(lines(self.reg), [])
        self.assertEqual(len(lines(other)), 1)

    def test_oserror_is_one_line_and_ignored(self):
        proc = self.sleeper()
        bad = toolreg.Registry(os.path.join(self.tmp, "no-such-dir", "tools.pids"))
        err = mock.patch("sys.stderr")
        with err as e:
            bad.register(proc)
        self.assertTrue(any("toolreg: ENOENT" in str(c) for c in e.write.call_args_list))

    def test_alive_zombie(self):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        self.addCleanup(proc.wait)
        self.assertTrue(wait_until(lambda: not toolrun.alive(proc.pid)))
        self.assertTrue(os.path.exists("/proc/%d" % proc.pid))           # still there (unreaped), but not alive


class ReapTest(RegBase):
    def test_reap_kills_matching_group(self):
        pidfile = os.path.join(self.tmp, "grandchild")
        proc = self.sleeper("import subprocess, sys, time\n"
                            "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                            "open(%r, 'w').write(str(g.pid))\ntime.sleep(60)" % pidfile)
        self.assertTrue(wait_until(lambda: os.path.exists(pidfile) and open(pidfile).read()))
        grandchild = int(open(pidfile).read())
        self.put(self.line_for(proc))
        got = self.reg.reap()
        proc.wait()
        self.assertEqual((got["killed"], got["stuck"]), (1, 0))
        self.assertTrue(wait_until(lambda: not toolrun.alive(grandchild)))
        self.assertEqual(lines(self.reg), [])

    def test_reap_ignores_argv0(self):
        for argv0 in ("python3-external", "/mnt/.mount_old/resources/sidecar/svf-maker-sidecar"):
            proc = self.sleeper()
            self.put(self.line_for(proc, argv0=argv0))
            got = self.reg.reap()
            proc.wait()
            self.assertEqual(got["killed"], 1, argv0)

    def test_reap_external_interpreter(self):
        stub = os.path.join(self.tmp, "py")
        with open(stub, "w") as f:
            f.write("#!/bin/sh\nexec sleep 60\n")
        os.chmod(stub, 0o755)
        toolreg.activate(self.reg)
        t = threading.Thread(target=lambda: jobs.run_command([stub], self.tmp, 60, threading.Event()), daemon=True)
        t.start()
        self.assertTrue(wait_until(lambda: len(lines(self.reg)) == 1))
        pid = int(lines(self.reg)[0].split()[1])
        self.addCleanup(lambda: os.killpg(pid, signal.SIGKILL) if toolrun.alive(pid) else None)
        got = toolreg.Registry(self.reg.path).reap()
        self.assertEqual(got["killed"], 1)
        t.join(20)
        self.assertFalse(toolrun.alive(pid))

    def test_reap_leaves_stale_line(self):
        proc = self.sleeper()
        self.put(self.line_for(proc, start="1"))
        got = self.reg.reap()
        self.assertEqual((got["stale"], got["killed"]), (1, 0))
        self.assertTrue(toolrun.alive(proc.pid))
        self.assertEqual(lines(self.reg), [])

    def test_reap_bounded(self):
        """Three stuck groups: their per-entry allowances (3 x 1 s) exceed the patched overall bound (1.5 s)."""
        procs = [self.sleeper() for _ in range(3)]
        self.put(*[self.line_for(p) for p in procs])
        with mock.patch.object(toolreg.os, "killpg"), mock.patch.object(toolreg, "REAP_EACH_S", 1.0), \
                mock.patch.object(toolreg, "REAP_TOTAL_S", 1.5):
            started = time.monotonic()
            got = self.reg.reap()
            elapsed = time.monotonic() - started
            total = toolreg.REAP_TOTAL_S
        self.assertLess(elapsed, total + 1.0, elapsed)          # against the patched total: 3 x 1 s would be 3 s
        self.assertEqual(got["stuck"], 3)

    def test_reap_pgid_must_equal_pid(self):
        """A damaged row naming an unrelated live group as pgid and a live pid: nothing is killed (L5)."""
        victim, other = self.sleeper(), self.sleeper()
        self.put("%d %d %s python3" % (victim.pid, other.pid, toolreg.start_time(other.pid)))
        got = self.reg.reap()
        self.assertEqual((got["killed"], got["stale"]), (0, 1))
        self.assertTrue(toolrun.alive(victim.pid) and toolrun.alive(other.pid))

    def test_reap_silent_without_a_data_dir(self):
        reg = toolreg.Registry(os.path.join(self.tmp, "nodir", "tools.pids"))
        with mock.patch("sys.stderr") as err:
            got = reg.reap()
        self.assertEqual(got, {"killed": 0, "stale": 0, "stuck": 0})
        self.assertFalse(err.write.called)


class AtomicityTest(RegBase):
    def test_a_crash_before_the_replace_keeps_both_records(self):
        """Crash injection: the rewrite dies after the temp file and before os.replace; both live tools stay recorded."""
        a, b = self.sleeper(), self.sleeper()
        toolreg.activate(self.reg)
        toolreg.register(a)
        toolreg.register(b)

        class Crash(BaseException):
            pass
        with mock.patch.object(toolreg.os, "replace", side_effect=Crash):
            with self.assertRaises(Crash):
                toolreg.unregister(a)
        rows = lines(self.reg)
        self.assertEqual(sorted(int(r.split()[1]) for r in rows), sorted([a.pid, b.pid]))

    def test_sigkill_during_rewrites_never_empties_the_file(self):
        """A process registers a live victim, then churns register/unregister and is SIGKILLed at random instants."""
        import random
        victim = self.sleeper()
        script = ("import sys, subprocess, itertools\nsys.path.insert(0, %r)\nimport toolreg\n"
                  "reg = toolreg.Registry(%r)\nv = subprocess.Popen(['sleep', '60'])\n"
                  "open(%r, 'w').write(str(v.pid))\n"
                  "reg.register(v)\nclass P:\n    pid = 999999\n    args = ['x']\n"
                  "for i in itertools.count():\n    reg.register(P)\n    reg.unregister(P)\n"
                  % (MAKER_DIR, self.reg.path, os.path.join(self.tmp, "v.pid")))
        rng = random.Random(7)
        for round_ in range(25):
            if os.path.exists(self.reg.path):
                os.remove(self.reg.path)
            proc = subprocess.Popen([sys.executable, "-c", script])
            try:
                self.assertTrue(wait_until(lambda: os.path.exists(os.path.join(self.tmp, "v.pid")), 10))
                time.sleep(rng.uniform(0.02, 0.15))
            finally:
                proc.kill()
                proc.wait()
            vpid = int(open(os.path.join(self.tmp, "v.pid")).read())
            os.remove(os.path.join(self.tmp, "v.pid"))
            try:
                self.assertIn(str(vpid), " ".join(r.split()[1] for r in lines(self.reg)), "round %d" % round_)
            finally:
                try:
                    os.kill(vpid, signal.SIGKILL)
                except OSError:
                    pass


class StartTimeTest(unittest.TestCase):
    def test_squeeze_has_no_spaces(self):
        self.assertEqual(toolreg.squeeze("Thu Nov  6 10:00:00 2026\n"), "Thu_Nov_6_10:00:00_2026")
        self.assertIsNone(toolreg.squeeze("  \n"))

    def test_darwin_start_time_round_trips_through_a_row(self):
        fake = mock.Mock(stdout=b"Thu Nov  6 10:00:00 2026\n")
        with mock.patch.object(toolreg.sys, "platform", "darwin"), mock.patch.object(toolreg.subprocess, "run", return_value=fake), \
                mock.patch("builtins.open", side_effect=OSError):
            start = toolreg.start_time(os.getpid())
        self.assertNotIn(" ", start)
        row = "%d %d %s python3" % (os.getpid(), os.getpid(), start)
        self.assertEqual(row.split()[2], start)


class ServerRegistryTest(unittest.TestCase):
    def test_server_close_deactivates(self):
        tmp = tempfile.mkdtemp(prefix="svf-toolreg-srv-")
        self.addCleanup(shutil.rmtree, tmp, True)
        srv = server.make_server("127.0.0.1", 0, fixtures.REPO_DIR, tmp)
        self.assertIsNotNone(toolreg.active())
        srv.worker.stop()
        srv.server_close()
        self.assertIsNone(toolreg.active())


if __name__ == "__main__":
    unittest.main()
