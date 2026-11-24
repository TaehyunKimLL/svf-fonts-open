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

import http.client
import json
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

import jobs
import localfx
import toolreg
import toolrun
import wincompat

NEODG = os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF")


def alive(pid):
    if os.name == "nt":                               # no /proc: the process handle (oscompat.process_alive)
        return toolrun.alive(pid)
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


class JobFixture(unittest.TestCase):
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


@wincompat.posix_only("SIGTERM and SIGINT to the server (WindowsStopTest covers the Windows stop)")
class SignalTest(JobFixture):
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


@unittest.skipUnless(wincompat.WIN, "Windows only: the stop by the end of stdin and the parent's process handle")
class WindowsStopTest(JobFixture):
    """Windows has no SIGTERM: the shell closes the server's stdin (`--stop-on-eof`), and a dead parent is seen through
    its process handle (`--exit-with-parent`). Either way the running tool and its child go (their Job Object)."""

    def start(self, extra_args=(), stdin=subprocess.PIPE):
        tmp = tempfile.mkdtemp(prefix="svf-winstop-")
        self.addCleanup(shutil.rmtree, tmp, True)
        pidfile = os.path.join(tmp, "pids")
        jid = self.long_job(os.path.join(tmp, "data"), pidfile)
        env = dict(os.environ, SVF_MAKER_REPO=REPO_DIR, SVF_MAKER_DATA=os.path.join(tmp, "data"),
                   SVF_MAKER_BIND="127.0.0.1:0")
        return tmp, pidfile, jid, env

    def wait_tools(self, pidfile):
        self.assertTrue(wait_until(lambda: os.path.exists(pidfile) and len(open(pidfile).read().split()) == 2),
                        "the step never started")
        pids = [int(v) for v in open(pidfile).read().split()]
        for pid in pids:
            self.addCleanup(lambda p=pid: wincompat.kill_group(p) if alive(p) else None)
        self.assertTrue(all(alive(p) for p in pids))
        return pids

    def test_end_of_stdin_stops_the_server_the_tool_and_its_child(self):
        tmp, pidfile, jid, env = self.start()
        log = os.path.join(tmp, "server.err")                 # a file: a pipe nobody reads could block the server
        with open(log, "wb") as err_file:
            proc = subprocess.Popen([sys.executable, "-P", SERVER, "--stop-on-eof"], env=env, stdin=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL, stderr=err_file)
        self.addCleanup(proc.kill)
        try:
            pids = self.wait_tools(pidfile)
        except AssertionError:
            with open(log, "rb") as f:
                raise AssertionError("the step never started; server stderr: %r" % f.read()[-2000:])
        proc.stdin.close()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.fail("the server did not stop at the end of stdin")
        with open(log, "rb") as f:
            err = f.read()
        self.assertNotIn(b"Traceback", err)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(wait_until(lambda: not any(alive(p) for p in pids), 20), "a tool outlived the server")
        job = jobs.Store(os.path.join(tmp, "data")).load(jid)
        self.assertEqual((job["state"], job["error"]), ("failed", "interrupted"))

    def test_a_dead_parent_stops_the_server_and_its_tools(self):
        tmp, pidfile, jid, env = self.start()
        out = os.path.join(tmp, "server.pid")
        helper = ("import subprocess, sys, time, os\n"
                  "p = subprocess.Popen([sys.executable, '-P', %r, '--exit-with-parent=%%d' %% os.getpid()],\n"
                  "                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                  "open(%r, 'w').write(str(p.pid))\ntime.sleep(300)\n" % (SERVER, out))
        parent = subprocess.Popen([sys.executable, "-c", helper], env=env)
        self.addCleanup(lambda: (parent.kill(), parent.wait()))
        self.assertTrue(wait_until(lambda: os.path.exists(out) and open(out).read().strip()))
        server_pid = int(open(out).read())
        self.addCleanup(lambda: wincompat.kill_group(server_pid) if alive(server_pid) else None)
        pids = self.wait_tools(pidfile)
        parent.kill()
        parent.wait()
        self.assertTrue(wait_until(lambda: not alive(server_pid), 30), "the server outlived its parent")
        self.assertTrue(wait_until(lambda: not any(alive(p) for p in pids), 20), "a tool outlived the server")
        job = jobs.Store(os.path.join(tmp, "data")).load(jid)
        self.assertEqual((job["state"], job["error"]), ("failed", "interrupted"))

    def test_a_killed_server_takes_its_tools_with_it(self):
        """TerminateProcess of the server (the shell's escalation): the tools' Job Objects close with it."""
        tmp, pidfile, jid, env = self.start()
        proc = subprocess.Popen([sys.executable, "-P", SERVER], env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(proc.kill)
        pids = self.wait_tools(pidfile)
        proc.kill()
        proc.wait(30)
        self.assertTrue(wait_until(lambda: not any(alive(p) for p in pids), 20), "a tool outlived the killed server")


HARNESS = os.path.join(TEST_DIR, "parent_harness.py")
SERVER = os.path.join(MAKER_DIR, "server.py")


class ArgvTest(unittest.TestCase):
    def test_main_refuses_unknown_option(self):
        out = subprocess.run([sys.executable, "-P", SERVER, "--nope"], capture_output=True, timeout=30,
                             env=dict(os.environ, SVF_MAKER_BIND="127.0.0.1:0"))
        self.assertEqual(out.returncode, 2)
        self.assertEqual(out.stdout, b"")


@unittest.skipUnless(sys.platform.startswith("linux"), "needs /proc, PR_SET_PDEATHSIG and a subreaper")
class ExitWithParentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-ewp-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.data)
        self.out_json = os.path.join(self.tmp, "h.json")

    def env(self, **extra):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/"), "LANG": "C.UTF-8",
               "SVF_MAKER_REPO": REPO_DIR, "SVF_MAKER_DATA": self.data, "SVF_MAKER_BIND": "127.0.0.1:0",
               "SVF_MAKER_TOKEN": localfx.TOKEN}
        env.update(extra)
        return env

    def start_harness(self, **extra):
        self.harness = subprocess.Popen([sys.executable, "-P", HARNESS, self.out_json, "--", sys.executable, "-P",
                                         SERVER], env=self.env(**extra), stdin=subprocess.DEVNULL)
        self.addCleanup(self.harness.kill)
        self.assertTrue(wait_until(lambda: os.path.exists(self.out_json), 20), "the harness never started the server")
        self.ids = json.load(open(self.out_json))
        self.addCleanup(lambda: os.kill(self.ids["server"], signal.SIGKILL) if alive(self.ids["server"]) else None)

    def relayed(self):
        try:
            return open(self.out_json + ".lines").read().splitlines()
        except OSError:
            return []

    def port(self):
        self.assertTrue(wait_until(lambda: any("listening on" in l for l in self.relayed()), 30), self.relayed())
        line = next(l for l in self.relayed() if "listening on" in l)
        return int(line.rsplit(":", 1)[1])

    def kill_helper(self):
        open(self.out_json + ".kill", "w").close()
        self.assertEqual(self.harness.wait(30), 0)
        return json.load(open(self.out_json))

    def make_local_job(self, port):
        tree = localfx.local_tree(os.path.join(self.tmp, "tree"))

        def call(method, path, obj=None):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
            conn.request(method, path, body=None if obj is None else json.dumps(obj),
                         headers={"X-Maker-Token": localfx.TOKEN})
            resp = conn.getresponse()
            body = json.loads(resp.read())
            conn.close()
            self.assertEqual(resp.status, 200, body)
            return body
        jid = call("POST", "/api/jobs", {"source": "local", "output_dir": tree["out"]})["id"]
        call("PUT", "/api/jobs/%s/sources" % jid, {"paths": tree["roots"]})
        call("POST", "/api/jobs/%s/detect" % jid)
        return os.path.join(tree["out"], ".svf-maker-" + jid)

    def test_reap_before_cleanup(self):
        sleeper = subprocess.Popen(["sleep", "60"], start_new_session=True)
        self.addCleanup(lambda: (alive(sleeper.pid) and os.killpg(sleeper.pid, signal.SIGKILL), sleeper.wait()))
        with open(os.path.join(self.data, "tools.pids"), "w") as f:
            f.write("%d %d %s sleep\n" % (sleeper.pid, sleeper.pid, toolreg.start_time(sleeper.pid)))
        proc = subprocess.Popen([sys.executable, "-P", SERVER], env=self.env(), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        self.addCleanup(proc.kill)
        self.assertIn("listening on", proc.stdout.readline())
        sleeper.wait(10)                                           # the server's reap killed it; reaped here
        self.assertFalse(toolrun.alive(sleeper.pid))
        self.assertEqual(open(os.path.join(self.data, "tools.pids")).read(), "")
        proc.send_signal(signal.SIGTERM)
        proc.wait(30)

    def exit_with_parent(self, **extra):
        self.start_harness(**extra)
        port = self.port()
        files_dir = self.make_local_job(port)
        self.assertTrue(os.path.isdir(files_dir), files_dir)
        result = self.kill_helper()
        self.assertEqual(result["status"], 0, result)
        self.assertLess(result["seconds"], 5, result)
        self.assertFalse(os.path.exists(files_dir), "the job's files directory outlived the server")

    def test_dead_parent_exits_0(self):
        gone = subprocess.Popen(["true"])
        gone.wait()
        for _ in range(3):
            proc = subprocess.run([sys.executable, "-P", SERVER, "--exit-with-parent=%d" % gone.pid], env=self.env(),
                                  capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("listening", proc.stdout)

    def test_parent_dying_during_startup_exits_0(self):
        open(self.out_json + ".kill", "w").close()               # the harness kills the helper as soon as it knows the server
        self.harness = subprocess.Popen([sys.executable, "-P", HARNESS, self.out_json, "--", sys.executable, "-P",
                                         SERVER], env=self.env(), stdin=subprocess.DEVNULL)
        self.addCleanup(self.harness.kill)
        self.assertEqual(self.harness.wait(60), 0)
        result = json.load(open(self.out_json))
        self.assertEqual(result["status"], 0, result)

    def test_sigkill_during_the_probe_then_restart_reaps_it(self):
        extra, pidfile = self.stub_probe()
        proc = subprocess.Popen([sys.executable, "-P", SERVER], env=self.env(**extra), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        self.addCleanup(proc.kill)
        self.assertTrue(wait_until(lambda: os.path.exists(pidfile) and open(pidfile).read().strip(), 20))
        stub_pid = int(open(pidfile).read())
        self.addCleanup(lambda: os.kill(stub_pid, signal.SIGKILL) if alive(stub_pid) else None)
        self.assertIn(str(stub_pid), open(os.path.join(self.data, "tools.pids")).read())
        proc.kill()
        proc.wait()
        self.assertTrue(alive(stub_pid), "the probe should outlive a SIGKILLed server (that is the case to reap)")
        again = subprocess.Popen([sys.executable, "-P", SERVER], env=self.env(), stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        self.addCleanup(again.kill)
        self.assertIn("listening on", again.stdout.readline())
        self.assertTrue(wait_until(lambda: not alive(stub_pid), 5), "the restart did not reap the old probe")
        again.send_signal(signal.SIGTERM)
        again.wait(30)

    def test_exit_with_parent_pdeathsig(self):
        self.exit_with_parent()

    def test_exit_with_parent_poll(self):
        self.exit_with_parent(SVF_MAKER_NO_PDEATHSIG="1")

    def stub_probe(self):
        """A recogniser dir and an interpreter that records its pid and sleeps: the start-up probe blocks."""
        recog = os.path.join(self.tmp, "recog")
        os.makedirs(recog)
        open(os.path.join(recog, "recog.py"), "w").close()
        pidfile = os.path.join(self.tmp, "stub.pid")
        stub = os.path.join(self.tmp, "stub-py")
        with open(stub, "w") as f:
            f.write("#!/bin/sh\necho $$ > %s\nexec sleep 60\n" % pidfile)
        os.chmod(stub, 0o755)
        return {"SVF_RECOG_DIR": recog, "SVF_RECOG_PYTHON": stub}, pidfile

    def test_exit_with_parent_during_startup(self):
        extra, pidfile = self.stub_probe()
        self.start_harness(**extra)
        self.assertTrue(wait_until(lambda: os.path.exists(pidfile) and open(pidfile).read().strip(), 20))
        stub_pid = int(open(pidfile).read())
        self.addCleanup(lambda: os.kill(stub_pid, signal.SIGKILL) if alive(stub_pid) else None)
        time.sleep(1)
        result = self.kill_helper()
        self.assertEqual(result["status"], 0, result)
        self.assertLess(result["seconds"], 5, result)
        self.assertFalse([l for l in result["lines"] if "listening" in l], result)
        self.assertTrue(wait_until(lambda: not alive(stub_pid), 5), "the probe's interpreter outlived the server")

    def test_sigterm_during_startup_cleanup(self):
        extra, pidfile = self.stub_probe()
        proc = subprocess.Popen([sys.executable, "-P", SERVER], env=self.env(**extra), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        self.addCleanup(proc.kill)
        self.assertTrue(wait_until(lambda: os.path.exists(pidfile) and open(pidfile).read().strip(), 20))
        stub_pid = int(open(pidfile).read())
        self.addCleanup(lambda: os.kill(stub_pid, signal.SIGKILL) if alive(stub_pid) else None)
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 0, err)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("listening", out)
        self.assertTrue(wait_until(lambda: not alive(stub_pid), 5))


if __name__ == "__main__":
    unittest.main()
