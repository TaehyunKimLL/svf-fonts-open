#!/usr/bin/env python3
"""The sidecar stops cleanly: SIGTERM (or SIGINT) cancels the running job through the worker's group-kill path, so no
tool child (each runs in its own session) outlives the server.

  python3 -m unittest discover -s maker/test -p test_server_signals.py
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import shutil
import signal
import subprocess
import tempfile
import time
import unittest

import jobs

NEODG = os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF")


def alive(pid):
    try:
        with open("/proc/%d/stat" % pid, "rb") as f:
            return f.read().rsplit(b") ", 1)[1].split()[0] not in (b"Z", b"X", b"x")
    except (OSError, IndexError):
        return False


def wait_until(cond, timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


class SignalTest(unittest.TestCase):
    def long_job(self, root, pidfile):
        """A queued job whose one step starts a grandchild and then sleeps; the server's recover() runs it."""
        store = jobs.Store(root)
        j = store.create()
        job_dir = store.path(j["id"])
        os.makedirs(os.path.join(job_dir, "upload"), exist_ok=True)
        shutil.copyfile(NEODG, os.path.join(job_dir, "upload", "NEODG16.SVF"))
        os.makedirs(os.path.join(job_dir, "work", "s01"), exist_ok=True)
        script = ("import subprocess, sys, time\n"
                  "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                  "open(%r, 'w').write('%%d %%d' %% (__import__('os').getpid(), p.pid))\n"
                  "time.sleep(120)\n" % pidfile)
        font = {"id": "f01", "path": "NEODG16.SVF", "face_index": 0, "format": "svf", "label": "SVF",
                "source_kind": "svf-precomposed", "family": "Neo", "style": "", "version": "1.0", "sizes": [16],
                "sizes_fixed": False, "coverage": {"ascii": 95, "ks2350": 2350, "all": 11172, "compat": 51},
                "jamo": "none", "dos": None, "bdf": None,
                "svf": {"version": 3, "flags": 1, "bpp": 1, "cell": [16, 16], "ascent": 12, "glyphs": 2905},
                "licences": [], "companions": [], "error": None}
        step = {"id": "s01", "font": "f01", "kind": "precomposed", "size": 16, "bpp": 1, "layout": None,
                "name": "NEWONE.SVF", "argv": [[sys.executable, "-c", script]], "output": "work/s01/NEWONE.SVF",
                "state": "pending", "exit": None, "seconds": None, "error": None, "stderr_tail": "", "facts": None,
                "quality": None, "identical_to": None, "report": None, "identity": None}
        eff = {"selected": True, "experimental": True, "dos_layout": None, "latin_companion": None,
               "licence": {"kind": "text", "text": "x"}, "licence_name": "LIC.TXT", "note_name": "NEO.TXT",
               "names": {"precomposed/16/1": "NEWONE.SVF"}, "dest": "new/fixture", "kinds": ["precomposed"],
               "sizes": [16], "bpp": [1]}
        j.update(state="queued", fonts=[font], steps=[step],
                 settings={"batch": {"dest": "dos", "kinds": ["precomposed"], "layout": "844", "sizes": [16],
                                     "bpp": [1, 2], "range": "2350", "preset": "plain", "options": {}},
                           "fonts": {"f01": eff}})
        store.save(j)
        return j["id"]

    def run_signal(self, sig):
        tmp = tempfile.mkdtemp(prefix="svf-signal-")
        self.addCleanup(shutil.rmtree, tmp, True)
        pidfile = os.path.join(tmp, "pids")
        self.long_job(os.path.join(tmp, "data"), pidfile)
        env = dict(os.environ, SVF_MAKER_REPO=REPO_DIR, SVF_MAKER_DATA=os.path.join(tmp, "data"),
                   SVF_MAKER_BIND="127.0.0.1:0")
        proc = subprocess.Popen([sys.executable, "-P", os.path.join(MAKER_DIR, "server.py")], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(proc.kill)
        self.assertTrue(wait_until(lambda: os.path.exists(pidfile) and len(open(pidfile).read().split()) == 2),
                        "the step never started")
        tool, grandchild = (int(v) for v in open(pidfile).read().split())
        for pid in (tool, grandchild):                 # whatever a failing run leaves must not sleep for two minutes
            self.addCleanup(lambda p=pid: os.kill(p, signal.SIGKILL) if alive(p) else None)
        self.assertTrue(alive(tool) and alive(grandchild))
        proc.send_signal(sig)
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            self.fail("the server did not stop on %s" % sig)
        self.assertTrue(wait_until(lambda: not alive(tool) and not alive(grandchild), 20),
                        "a tool child outlived the server (tool %s grandchild %s)" % (alive(tool), alive(grandchild)))
        return tmp

    def test_sigterm_stops_the_running_tool_and_its_children(self):
        self.run_signal(signal.SIGTERM)

    def test_a_second_signal_is_quiet_and_the_job_is_marked_interrupted(self):
        tmp = tempfile.mkdtemp(prefix="svf-signal-")
        self.addCleanup(shutil.rmtree, tmp, True)
        pidfile = os.path.join(tmp, "pids")
        jid = self.long_job(os.path.join(tmp, "data"), pidfile)
        env = dict(os.environ, SVF_MAKER_REPO=REPO_DIR, SVF_MAKER_DATA=os.path.join(tmp, "data"), SVF_MAKER_BIND="127.0.0.1:0")
        proc = subprocess.Popen([sys.executable, "-P", os.path.join(MAKER_DIR, "server.py")], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(proc.kill)
        self.assertTrue(wait_until(lambda: os.path.exists(pidfile) and len(open(pidfile).read().split()) == 2))
        for pid in (int(v) for v in open(pidfile).read().split()):
            self.addCleanup(lambda p=pid: os.kill(p, signal.SIGKILL) if alive(p) else None)
        proc.send_signal(signal.SIGTERM)
        proc.send_signal(signal.SIGTERM)
        proc.send_signal(signal.SIGINT)
        try:
            _out, err = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            self.fail("the server did not stop")
        self.assertNotIn(b"Traceback", err)
        self.assertEqual(proc.returncode, 0)
        job = jobs.Store(os.path.join(tmp, "data")).load(jid)
        self.assertEqual((job["state"], job["error"]), ("failed", "interrupted"))

    def test_sigint_does_the_same(self):
        self.run_signal(signal.SIGINT)


if __name__ == "__main__":
    unittest.main()
