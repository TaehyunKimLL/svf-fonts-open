"""Tests for esp-screen.py (the QEMU esp_rgb screen runner) against a fake QEMU, one behaviour per FAKE_MODE."""
import importlib.util
import json
import os
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "esp-screen.py")

# The fake QEMU: parses -qmp unix:PATH,server,nowait from argv, binds it, and behaves per FAKE_MODE.
FAKE = r"""#!/usr/bin/env python3
import json, os, socket, sys, time
mode = os.environ.get("FAKE_MODE", "serve")
if os.environ.get("FAKE_PIDFILE"):
    open(os.environ["FAKE_PIDFILE"], "w").write(str(os.getpid()))
path = None
a = sys.argv[1:]
for i, x in enumerate(a):
    if x == "-qmp":
        path = a[i + 1][len("unix:"):].split(",")[0]
def err(s):
    sys.stderr.write(s); sys.stderr.flush()
if mode == "exit3":
    err("fake: bad machine\n")
    sys.exit(3)
srv = None
if path and mode != "nosock":
    srv = socket.socket(socket.AF_UNIX)
    srv.bind(path)  # fails on a stale file: the runner must have unlinked it
    srv.listen(1)
def out(s):
    sys.stdout.write(s); sys.stdout.flush()
if mode == "banner":
    out("hello\nscreen=ready\n")
elif mode == "failed":
    out("screen=failed\n")
elif mode == "longline":
    out("x" * 5000 + "\n")
elif mode == "flood":
    for _ in range(70 * 1024 // 2):
        out("\r\n")  # empty lines are ignored, so only the 64 KiB total stops this
    out("screen=ready\n")
elif mode == "floodready":
    out("\n" * (64 * 1024 + 100) + "screen=ready\n")  # screen=ready arrives in the chunk that crosses the cap
elif mode == "silent":
    err("fake: waiting\n")
    time.sleep(60)
elif mode == "hang":
    time.sleep(60)
elif mode == "closeout":
    os.close(1)  # stdout at EOF but the process lives on
    time.sleep(60)
elif mode == "bigfile":
    with open(path + ".big", "wb") as bf:
        bf.seek(100 << 20)
        bf.write(b"x")  # past RLIMIT_FSIZE: EFBIG
    out("screen=ready\n")
elif mode == "errnonstop":
    while True:
        err("e" * 65536)
elif mode == "stderrflood":
    err("e" * 200000)
    time.sleep(60)
else:
    out("screen=ready\n")
if mode == "nosock":
    time.sleep(60)
c, _ = srv.accept()
f = c.makefile("rwb")
def send(o):
    f.write((json.dumps(o) + "\n").encode()); f.flush()
send({"QMP": {"version": {}, "capabilities": []}})
log = open(os.environ["FAKE_LOG"], "a") if os.environ.get("FAKE_LOG") else None
while True:
    line = f.readline()
    if not line:
        break
    m = json.loads(line)
    cmd, args = m["execute"], m.get("arguments", {})
    if log:
        log.write(json.dumps([cmd, {k: v for k, v in args.items() if k != "filename"}]) + "\n"); log.flush()
    if mode == "errduring" and cmd == "screendump":
        while True:
            err("e" * 65536)
    if mode == "errquit" and cmd == "quit":
        send({"return": {}})
        for _ in range(160):
            err("e" * 65536)
        sys.exit(0)
    if mode == "qmpsilent":
        time.sleep(60)
    if mode == "qmpclose":
        sys.exit(0)
    if mode == "qmpbad":
        f.write(b"this is not json\n"); f.flush(); continue
    if mode == "qmplong":
        f.write(b"x" * (2 << 20)); f.flush(); time.sleep(60)
    if mode == "qmperr" and cmd == "screendump":
        send({"error": {"class": "GenericError", "desc": "no display"}})
        continue
    if cmd == "screendump":
        if mode == "badppm":
            open(args["filename"], "wb").write(b"P6\n100 100\n255\n" + bytes(30000))
        elif mode == "bigppm":
            open(args["filename"], "wb").write(b"P6\n9000 9000\n255\n" + bytes(30))
        elif mode == "bombppm":
            open(args["filename"], "wb").write(b"P6\n30000 30000\n255\n")
        elif mode == "grayppm":
            open(args["filename"], "wb").write(b"P5\n320 240\n255\n" + bytes(320 * 240))
        elif mode == "junkppm":
            open(args["filename"], "wb").write(b"junk")
        else:
            px = bytes((x * 7 + y * 3 + k) & 255 for y in range(240) for x in range(320) for k in range(3))
            open(args["filename"], "wb").write(b"P6\n320 240\n255\n" + px)
    elif cmd == "pmemsave":
        n = args["size"] - 1 if mode == "shortfb" else args["size"]
        open(args["filename"], "wb").write(bytes(i & 255 for i in range(n)))
    send({"event": "X", "timestamp": {}})  # an event between replies must be skipped
    send({"return": {}})
    if cmd == "quit":
        if mode == "noquit":
            time.sleep(60)
        break
sys.exit(0)
"""


def load():
    spec = importlib.util.spec_from_file_location("esp_screen", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.qemu = os.path.join(self.tmp.name, "fake-qemu")
        with open(self.qemu, "w") as f:
            f.write(FAKE)
        os.chmod(self.qemu, os.stat(self.qemu).st_mode | stat.S_IXUSR)
        self.out = os.path.join(self.tmp.name, "out")
        os.makedirs(self.out)
        self.elf = os.path.join(self.tmp.name, "x.elf")

    def env(self, mode, **env):
        self.pidfile = os.path.join(self.tmp.name, "fake.pid")
        self.log = os.path.join(self.tmp.name, "fake.log")
        return dict(os.environ, FAKE_MODE=mode, SVF_REQUIRE_SCREENS="1", FAKE_PIDFILE=self.pidfile, FAKE_LOG=self.log,
                    **env)

    def fake_pid(self):
        try:
            with open(self.pidfile) as f:
                return int(f.read())
        except (OSError, ValueError):
            return None

    def alive(self, pid):
        try:
            with open("/proc/%d/stat" % pid) as f:
                return f.read().rsplit(")", 1)[1].split()[0] != "Z"
        except OSError:
            return False

    def run_es(self, mode, board="esp32c3", **env):
        if not HAVE_PIL:
            self.skipTest("Pillow missing (the runner skips without it)")
        e = self.env(mode, **env)
        self.addCleanup(self.kill_fake)
        return subprocess.run([sys.executable, "-I", SCRIPT, self.qemu, self.elf, board, self.out],
                              capture_output=True, text=True, env=e, timeout=120)

    def kill_fake(self):
        pid = self.fake_pid()
        if pid and self.alive(pid):
            os.kill(pid, signal.SIGKILL)

    def commands(self):
        with open(self.log) as f:
            return [json.loads(x) for x in f]

    def path(self, name):
        return os.path.join(self.out, name)


class TestEspScreen(Base):
    def test_ok(self):
        r = self.run_es("serve")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "ok: esp32c3 screendump + pmemsave")
        self.assertEqual(os.path.getsize(os.path.join(self.out, "esp32c3-colour.fb")), 153600)
        self.assertTrue(os.path.exists(os.path.join(self.out, "esp32c3-colour.ppm")))
        from PIL import Image
        with Image.open(os.path.join(self.out, "esp32c3-colour.png")) as im:
            self.assertEqual(im.size, (320, 240))
        self.assertEqual(self.commands(), [["qmp_capabilities", {}], ["screendump", {}],
                                           ["pmemsave", {"val": 0x20000000, "size": 153600}], ["quit", {}]])
        self.assertFalse(os.path.exists(self.path("qmp.sock")))  # the runner removes the socket file

    def test_s3_board(self):
        r = self.run_es("serve", board="esp32s3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.out, "esp32s3-colour.png")))

    def test_stale_sock(self):
        with open(os.path.join(self.out, "qmp.sock"), "w") as f:
            f.write("stale")
        r = self.run_es("serve")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_banner(self):
        r = self.run_es("banner")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: unexpected line: hello", r.stdout)

    def test_screen_failed(self):
        r = self.run_es("failed")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: unexpected line: screen=failed", r.stdout)

    def test_long_line(self):
        r = self.run_es("longline")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: line too long", r.stdout)

    def test_flood(self):
        r = self.run_es("flood")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: output too long", r.stdout)

    def test_timeout(self):
        r = self.run_es("silent", SVF_ESP_TIMEOUT="1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: timeout", r.stdout)
        self.assertIn("fake: waiting", r.stdout)  # the last line of <board>-qemu.err

    def test_qemu_exits(self):
        r = self.run_es("exit3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: qemu exited 3", r.stdout)
        self.assertIn("fake: bad machine", r.stdout)

    def test_qmp_error(self):
        r = self.run_es("qmperr")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: qmp: screendump", r.stdout)
        self.assertIn("no display", r.stdout)

    def test_missing_qemu(self):
        self.qemu = os.path.join(self.tmp.name, "nope")
        r = self.run_es("serve")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: qemu missing", r.stdout)

    def test_missing_qemu_skips_without_require(self):
        self.qemu = os.path.join(self.tmp.name, "nope")
        e = {k: v for k, v in os.environ.items() if k != "SVF_REQUIRE_SCREENS"}
        r = subprocess.run([sys.executable, "-I", SCRIPT, self.qemu, self.elf, "esp32c3", self.out],
                           capture_output=True, text=True, env=e)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("screen-esp32c3: SKIPPED (missing: "), r.stdout)

    def test_usage(self):
        r = subprocess.run([sys.executable, "-I", SCRIPT, "a", "b"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        r = subprocess.run([sys.executable, "-I", SCRIPT, self.qemu, self.elf, "esp32", self.out],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_qmp_error_removes_sock_and_png(self):
        with open(self.path("esp32c3-colour.png"), "w") as f:
            f.write("old")
        r = self.run_es("qmperr")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(self.path("qmp.sock")))
        self.assertFalse(os.path.exists(self.path("esp32c3-colour.png")))

    def test_stale_png_removed_on_failure(self):
        for n in ("esp32c3-colour.png", "esp32c3-colour.ppm", "esp32c3-colour.fb"):
            with open(self.path(n), "w") as f:
                f.write("old")
        r = self.run_es("banner")
        self.assertEqual(r.returncode, 1)
        for n in ("esp32c3-colour.png", "esp32c3-colour.ppm", "esp32c3-colour.fb"):
            self.assertFalse(os.path.exists(self.path(n)), n)

    def test_flood_with_ready_in_last_chunk(self):
        r = self.run_es("floodready")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("fail: output too long", r.stdout)

    def test_stderr_flood(self):
        t = time.monotonic()
        r = self.run_es("stderrflood", SVF_ESP_TIMEOUT="20")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("fail: output too long", r.stdout)
        self.assertLess(time.monotonic() - t, 10)  # not the 20 s timeout
        self.assertFalse(self.alive(self.fake_pid()))

    def test_exec_format_error(self):
        with open(self.qemu, "w") as f:
            f.write("not a program\n")
        r = self.run_es("serve")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("fail: qemu: "), r.stdout)
        self.assertNotIn("Traceback", r.stderr)

    def test_eof_then_alive(self):
        r = self.run_es("closeout", SVF_ESP_TIMEOUT="1")  # old code waited for the exit forever
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("fail: timeout", r.stdout)

    def _signalled(self, sig):
        e = self.env("hang", SVF_ESP_TIMEOUT="60")
        p = subprocess.Popen([sys.executable, "-I", SCRIPT, self.qemu, self.elf, "esp32c3", self.out],
                             stdout=subprocess.PIPE, text=True, env=e)
        self.addCleanup(p.stdout.close)
        self.addCleanup(self.kill_fake)
        deadline = time.monotonic() + 10
        while not self.fake_pid() and time.monotonic() < deadline:
            time.sleep(0.05)
        pid = self.fake_pid()
        self.assertTrue(pid and self.alive(pid))
        time.sleep(0.3)  # the runner is in its wait loop
        p.send_signal(sig)
        p.wait(timeout=10)
        deadline = time.monotonic() + 5
        while self.alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(self.alive(pid), "the fake QEMU outlived the runner")
        return p

    def test_sigterm_kills_qemu(self):
        p = self._signalled(signal.SIGTERM)
        self.assertEqual(p.returncode, 1)
        self.assertIn("fail: ", p.stdout.read())

    def test_sighup_kills_qemu(self):
        p = self._signalled(signal.SIGHUP)
        self.assertEqual(p.returncode, 1)

    def test_sigint_kills_qemu(self):
        p = self._signalled(signal.SIGINT)
        self.assertEqual(p.returncode, 1)
        self.assertIn("fail: killed by signal 2", p.stdout.read())

    @unittest.skipUnless(sys.platform.startswith("linux"), "PR_SET_PDEATHSIG is Linux-only")
    def test_sigkill_kills_qemu(self):
        self._signalled(signal.SIGKILL)  # PR_SET_PDEATHSIG

    def _capped(self, mode, **env):
        t = time.monotonic()
        # a 60 s QMP timeout: only the reader thread's proc.kill() ends errduring (the fake never answers screendump)
        # in under 5 s; without it the run waits out the QMP timeout (12x margin for a slow host)
        env.setdefault("SVF_ESP_QMP_TIMEOUT", "60")
        r = self.run_es(mode, SVF_ESP_TIMEOUT="20", **env)
        self.assertLess(time.monotonic() - t, 5, "the stderr cap did not stop QEMU promptly")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(r.stdout.strip().split(" (")[0], "fail: output too long")
        n = os.path.getsize(self.path("esp32c3-qemu.err"))
        self.assertLessEqual(n, 64 * 1024 + 4096)
        self.assertFalse(self.alive(self.fake_pid()))

    def test_stderr_nonstop(self):
        self._capped("errnonstop")

    def test_stderr_nonstop_during_qmp(self):
        self._capped("errduring")

    def test_stderr_on_quit(self):
        self._capped("errquit")

    def test_fsize_limit(self):
        r = self.run_es("bigfile")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("File too large", r.stdout)  # Python ignores SIGXFSZ: its write fails with EFBIG

    def test_bad_qmp_timeout(self):
        for v in ("inf", "nan", "0", "-1", "601", "1e300", "abc"):
            r = self.run_es("serve", SVF_ESP_QMP_TIMEOUT=v)
            self.assertEqual((r.returncode, r.stdout.strip()), (1, "fail: bad SVF_ESP_QMP_TIMEOUT"),
                             (v, r.stdout, r.stderr))
        r = self.run_es("serve", SVF_ESP_QMP_TIMEOUT="600")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_orphan_check_after_prctl(self):
        mod = load()
        pid = os.fork()
        if pid == 0:
            try:
                mod._die_with_parent(1 << 22)  # not our parent: must not return
                os._exit(0)
            except BaseException:
                os._exit(2)
        _, status = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 1)

    def test_qmp_timeout(self):
        r = self.run_es("qmpsilent", SVF_ESP_QMP_TIMEOUT="1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: qmp: timeout", r.stdout)

    def test_qmp_closed(self):
        r = self.run_es("qmpclose")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: qmp: connection closed", r.stdout)

    def test_qmp_bad_reply(self):
        r = self.run_es("qmpbad")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: qmp: bad reply", r.stdout)

    def test_qmp_reply_too_long(self):
        r = self.run_es("qmplong", SVF_ESP_QMP_TIMEOUT="5")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: qmp: reply too long", r.stdout)

    def test_qmp_no_socket(self):
        r = self.run_es("nosock", SVF_ESP_QMP_TIMEOUT="1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: qmp: cannot connect", r.stdout)

    def test_quit_ignored(self):
        r = self.run_es("noquit", SVF_ESP_QMP_TIMEOUT="1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: qmp: quit: qemu did not exit", r.stdout)
        self.assertFalse(self.alive(self.fake_pid()))

    def test_short_fb(self):
        r = self.run_es("shortfb")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: qmp: pmemsave wrote no 153600-byte file", r.stdout)

    def test_ppm_wrong_size(self):
        r = self.run_es("badppm")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: qmp: screendump is RGB 100 x 100, not RGB 320 x 240", r.stdout)

    def test_ppm_wrong_size_checked_before_load(self):
        r = self.run_es("bigppm")  # truncated pixel data: only a size check before load() names the size
        self.assertEqual(r.returncode, 1)
        self.assertIn("RGB 9000 x 9000, not RGB 320 x 240", r.stdout)

    def test_ppm_decompression_bomb(self):
        r = self.run_es("bombppm")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("fail: qmp: screendump"), r.stdout)
        self.assertNotIn("Traceback", r.stderr)

    def test_ppm_not_rgb(self):
        r = self.run_es("grayppm")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("fail: qmp: screendump", r.stdout)

    def test_ppm_junk(self):
        r = self.run_es("junkppm")
        self.assertEqual(r.returncode, 1)
        self.assertIn("fail: qmp: screendump wrote no readable PPM", r.stdout)

    def test_pillow_import_failure(self):
        mod = load()
        saved = sys.modules.get("PIL")
        sys.modules["PIL"] = None  # import PIL raises ImportError
        try:
            with self.assertRaises(mod.Fail) as cm:
                mod.run(self.qemu, self.elf, "esp32c3", self.out)
        finally:
            if saved is None:
                del sys.modules["PIL"]
            else:
                sys.modules["PIL"] = saved
        self.assertTrue(str(cm.exception).startswith("Pillow: "), str(cm.exception))

    def test_qmp_socket_closed_on_failure(self):
        if not HAVE_PIL:
            self.skipTest("Pillow missing (mod.run needs it)")
        mod = load()
        seen = []
        orig = mod._connect
        mod._connect = lambda *a: seen.append(orig(*a)) or seen[-1]
        self.addCleanup(self.kill_fake)
        with mock.patch.dict(os.environ, self.env("qmperr")):
            with self.assertRaises(mod.Fail):
                mod.run(self.qemu, self.elf, "esp32c3", self.out)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].sock.fileno(), -1)


class TestFunctions(Base):
    def test_known_lines_empty_and_wait_ready_raises(self):
        mod = load()
        self.assertEqual(mod.KNOWN_LINES, [])
        p = subprocess.Popen([sys.executable, "-c", "print('boot'); print('screen=ready')"], stdout=subprocess.PIPE)
        try:
            with self.assertRaises(mod.Fail) as cm:
                mod.wait_ready(p, 5)
            self.assertIn("unexpected line: boot", str(cm.exception))
        finally:
            p.kill()
            p.wait()
            p.stdout.close()

    def test_known_line_is_ignored(self):
        mod = load()
        mod.KNOWN_LINES = ["boot"]
        p = subprocess.Popen([sys.executable, "-c", "print('boot'); print(' screen=ready\\r')"], stdout=subprocess.PIPE)
        try:
            self.assertIsNone(mod.wait_ready(p, 5))
        finally:
            p.kill()
            p.wait()
            p.stdout.close()

    def test_qmp_skips_events(self):
        mod = load()
        a, b = socket.socketpair()
        b.sendall(b'{"event":"E"}\n{"return":{"x":1}}\n')
        self.assertEqual(mod.qmp(mod.Conn(a), "ping", {}, 2), {"return": {"x": 1}})
        a.close()
        b.close()


if __name__ == "__main__":
    unittest.main()
