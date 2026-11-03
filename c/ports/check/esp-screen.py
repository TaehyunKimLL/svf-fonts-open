#!/usr/bin/env python3
"""Runs a bare ESP32-C3/S3 colour image on Espressif QEMU and captures its esp_rgb panel.

    esp-screen.py QEMU ELF BOARD OUT        (BOARD esp32c3 or esp32s3)

Starts QEMU with a QMP socket (a stale OUT/qmp.sock is unlinked first), reads the guest's stdout line by line until
"screen=ready", then over QMP: qmp_capabilities, screendump (OUT/<board>-colour.ppm; it triggers the device update),
pmemsave of the VRAM (OUT/<board>-colour.fb, 153,600 bytes at 0x20000000) and quit. The PPM becomes
OUT/<board>-colour.png (Pillow). screen_ref.py compares the .fb and the .ppm with the reference.

Prints "ok: <board> screendump + pmemsave" (exit 0) or "fail: <cause>" (exit 1): qemu missing, timeout, qemu exited
<status>, unexpected line: <line> (screen=failed from svf_port_idle included), line too long, output too long, qmp: ...
A missing QEMU or Pillow prints "screen-<board>: SKIPPED (missing: ...)" and exits 0 unless SVF_REQUIRE_SCREENS=1 (then
"fail: ..." and 1). Exit 2 is a usage error. SVF_ESP_TIMEOUT (seconds, default 30) is the wait for screen=ready,
SVF_ESP_QMP_TIMEOUT (default 10; 0 < t <= 600, else "fail: bad SVF_ESP_QMP_TIMEOUT") the wait for each QMP step. A timeout
or QEMU exit adds the last line of OUT/<board>-qemu.err (QEMU's stderr) or its path.
Guest output: one line is at most 4 KiB, stdout in all 64 KiB, QEMU's stderr in all 64 KiB, a QMP reply 1 MiB; either
exceeded kills QEMU and fails. QEMU's stderr goes through a pipe to the .err file, which never holds more than 64 KiB;
QEMU also runs under RLIMIT_FSIZE 64 MiB. SIGTERM, SIGHUP and SIGINT kill QEMU and fail; on Linux QEMU gets
SIGKILL if the runner dies."""
import json
import math
import os
import select
import signal
import socket
import subprocess
import sys
import threading
import time

BOARDS = ("esp32c3", "esp32s3")
# lines a runtime may print before the guest's own output; today none (with -qmp the monitor is off)
KNOWN_LINES = []
LINE_MAX = 4096
TOTAL_MAX = 64 * 1024
ERR_MAX = 64 * 1024
# RLIMIT_FSIZE of QEMU: its 1,920,000-byte memfd "displaysurface" is resized with ftruncate, so QEMU dies with SIGXFSZ
# at a 1 MiB limit (it runs at 2 MiB)
FSIZE_MAX = 64 * 1024 * 1024
QMP_MSG_MAX = 1024 * 1024
READY_TIMEOUT = 30.0
QMP_TIMEOUT = 10.0
VRAM = 0x20000000
VRAM_BYTES = 320 * 240 * 2


class Fail(Exception):
    pass


def _timeout():
    try:
        t = float(os.environ.get("SVF_ESP_TIMEOUT", ""))
        return t if t > 0 else READY_TIMEOUT
    except ValueError:
        return READY_TIMEOUT


def _qmp_timeout():
    """SVF_ESP_QMP_TIMEOUT: unset or empty is the default; else a finite number of seconds, 0 < t <= 600."""
    v = os.environ.get("SVF_ESP_QMP_TIMEOUT", "")
    if not v:
        return QMP_TIMEOUT
    try:
        t = float(v)
    except ValueError:
        raise Fail("bad SVF_ESP_QMP_TIMEOUT")
    if not (math.isfinite(t) and 0 < t <= 600):
        raise Fail("bad SVF_ESP_QMP_TIMEOUT")
    return t


def _err_hint(err_path):
    """" (<last line of QEMU's stderr>)", or " (see <path>)" when it is empty or unreadable; "" without a path."""
    if not err_path:
        return ""
    try:
        with open(err_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 2048))
            lines = [x.strip() for x in f.read().decode("utf-8", "replace").splitlines() if x.strip()]
    except OSError:
        lines = []
    return " (%s)" % lines[-1][:200] if lines else " (see %s)" % err_path


class ErrCapture:
    """Drains QEMU's stderr pipe into a file in a thread; stops writing at ERR_MAX bytes, kills QEMU and sets .over."""

    def __init__(self, proc, path):
        self.proc, self.path = proc, path
        self.over = threading.Event()
        self.f = open(path, "wb")
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def _run(self):
        fd = self.proc.stderr.fileno()
        total = 0
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            if total + len(chunk) > ERR_MAX:
                self.f.write(chunk[:ERR_MAX - total])
                self.f.flush()
                self.over.set()
                try:
                    self.proc.kill()
                except OSError:
                    pass
                total = ERR_MAX
                continue  # keep draining so the dying QEMU never blocks
            total += len(chunk)
            self.f.write(chunk)
            self.f.flush()

    def check(self):
        """Fails once stderr has passed the cap."""
        if self.over.is_set():
            raise Fail("output too long (stderr over %d bytes)" % ERR_MAX)

    def close(self):
        self.t.join(5)
        self.proc.stderr.close()
        self.f.close()


def wait_ready(proc, timeout, err_path=None, cap=None):
    """Reads proc.stdout until the line "screen=ready"; raises Fail for a timeout, QEMU exiting first, a line over
    4 KiB, more than 64 KiB in all, or any other line not in KNOWN_LINES. Returns None. @p err_path is QEMU's stderr
    file: @p cap (an ErrCapture) is checked every pass, and its last line is added to a timeout or exit failure."""
    fd = proc.stdout.fileno()
    deadline = time.monotonic() + timeout
    buf, total = b"", 0
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise Fail("timeout" + _err_hint(err_path))
        if cap:
            cap.check()
        r, _, _ = select.select([fd], [], [], min(left, 0.5))
        if not r:
            if proc.poll() is not None:
                raise Fail("qemu exited %s%s" % (proc.returncode, _err_hint(err_path)))
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            try:
                proc.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise Fail("timeout (stdout closed, qemu still running)" + _err_hint(err_path))
            raise Fail("qemu exited %s%s" % (proc.returncode, _err_hint(err_path)))
        total += len(chunk)
        if total > TOTAL_MAX:
            raise Fail("output too long")
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            if len(raw) > LINE_MAX:
                raise Fail("line too long")
            line = raw.decode("utf-8", "replace").strip()
            if not line or line in KNOWN_LINES:
                continue
            if line == "screen=ready":
                return None
            raise Fail("unexpected line: %s" % line[:200])
        if len(buf) > LINE_MAX:
            raise Fail("line too long")


class Conn:
    """A QMP connection: a socket and the bytes read past the last full message."""

    def __init__(self, sock):
        self.sock = sock
        self.buf = b""


def _read_msg(conn, deadline):
    while b"\n" not in conn.buf:
        left = deadline - time.monotonic()
        if left <= 0:
            raise Fail("qmp: timeout")
        conn.sock.settimeout(left)
        try:
            chunk = conn.sock.recv(65536)
        except socket.timeout:
            raise Fail("qmp: timeout")
        if not chunk:
            raise Fail("qmp: connection closed")
        conn.buf += chunk
        if len(conn.buf) > QMP_MSG_MAX and b"\n" not in conn.buf:
            raise Fail("qmp: reply too long")
    line, conn.buf = conn.buf.split(b"\n", 1)
    try:
        return json.loads(line)
    except ValueError:
        raise Fail("qmp: bad reply")


def qmp(sock, cmd, args, timeout):
    """Sends one QMP command on @p sock (a Conn) and returns its reply ({"return": ...}); events are skipped. Raises Fail
    on an error reply, a closed connection or no reply within @p timeout seconds."""
    msg = {"execute": cmd}
    if args:
        msg["arguments"] = args
    deadline = time.monotonic() + timeout
    try:
        sock.sock.sendall((json.dumps(msg) + "\n").encode())
    except OSError as e:
        raise Fail("qmp: %s: %s" % (cmd, e.strerror or e))
    while True:
        m = _read_msg(sock, deadline)
        if "error" in m:
            raise Fail("qmp: %s: %s" % (cmd, m["error"].get("desc", m["error"])))
        if "return" in m:
            return m


def _connect(path, proc, err_path=None):
    deadline = time.monotonic() + _qmp_timeout()
    while True:
        s = socket.socket(socket.AF_UNIX)
        try:
            s.settimeout(1)
            s.connect(path)
            break
        except OSError:
            s.close()
            if proc.poll() is not None:
                raise Fail("qemu exited %s%s" % (proc.returncode, _err_hint(err_path)))
            if time.monotonic() > deadline:
                raise Fail("qmp: cannot connect to %s" % path)
            time.sleep(0.05)
    conn = Conn(s)
    try:
        deadline = time.monotonic() + _qmp_timeout()
        while "QMP" not in _read_msg(conn, deadline):
            pass
    except BaseException:
        s.close()
        raise
    return conn


class Terminated(Fail):
    pass


def _on_signal(signum, frame):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    raise Terminated("killed by signal %d" % signum)


def _die_with_parent(parent):
    """preexec_fn of the QEMU child: SIGKILL it when the runner dies, even by SIGKILL (Linux only); exits at once when
    @p parent (the runner's pid, taken before the fork) is already gone. Also caps the size of any file QEMU writes."""
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_FSIZE, (FSIZE_MAX, FSIZE_MAX))
    except Exception:
        pass
    try:
        import ctypes
        ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
    except Exception:
        return
    if os.getppid() != parent:
        os._exit(1)


def run(qemu, elf, board, out):
    try:
        from PIL import Image
    except ImportError as e:
        raise Fail("Pillow: %s" % e)
    sock_path = os.path.abspath(os.path.join(out, "qmp.sock"))
    ppm = os.path.abspath(os.path.join(out, "%s-colour.ppm" % board))
    fb = os.path.abspath(os.path.join(out, "%s-colour.fb" % board))
    png = os.path.join(out, "%s-colour.png" % board)
    err_path = os.path.join(out, "%s-qemu.err" % board)
    for p in (sock_path, ppm, fb, png):
        try:
            os.unlink(p)
        except FileNotFoundError:
            pass
    qt = _qmp_timeout()
    cap = proc = conn = None
    parent = os.getpid()
    try:
        try:
            proc = subprocess.Popen([qemu, "-M", board, "-display", "none", "-nographic", "-serial", "none",
                                     "-semihosting", "-qmp", "unix:%s,server,nowait" % sock_path,
                                     "-icount", "shift=0,sleep=off", "-kernel", elf], stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                    preexec_fn=lambda: _die_with_parent(parent))
        except OSError as e:
            raise Fail("qemu: %s" % (e.strerror or e))
        cap = ErrCapture(proc, err_path)
        wait_ready(proc, _timeout(), err_path, cap)
        conn = _connect(sock_path, proc, err_path)
        for cmd, args in (("qmp_capabilities", None), ("screendump", {"filename": ppm}),
                          ("pmemsave", {"val": VRAM, "size": VRAM_BYTES, "filename": fb}), ("quit", None)):
            cap.check()
            qmp(conn, cmd, args, qt)
        try:
            proc.wait(timeout=qt)
        except subprocess.TimeoutExpired:
            raise Fail("qmp: quit: qemu did not exit")
        cap.close()
        cap.check()
    except Fail:
        if cap is not None:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            cap.close()
            cap.check()  # QEMU killed for its stderr: that is the cause, whatever the symptom was
        raise
    finally:
        if conn is not None:
            conn.sock.close()
        if proc is not None:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdout.close()
        if cap is not None:
            cap.close()
        try:
            os.unlink(sock_path)
        except FileNotFoundError:
            pass
    if not os.path.exists(fb) or os.path.getsize(fb) != VRAM_BYTES:
        raise Fail("qmp: pmemsave wrote no %d-byte file" % VRAM_BYTES)
    try:
        with Image.open(ppm) as img:
            if img.mode != "RGB" or img.size != (320, 240):  # before load(): a header can claim any size
                raise Fail("qmp: screendump is %s %d x %d, not RGB 320 x 240" % ((img.mode,) + img.size))
            img.load()
            img.save(png)
    except (OSError, ValueError, Image.DecompressionBombError) as e:
        raise Fail("qmp: screendump wrote no readable PPM: %s" % e)


def main(argv):
    if len(argv) != 4 or argv[2] not in BOARDS:
        print(__doc__, file=sys.stderr)
        return 2
    qemu, elf, board, out = argv
    missing = []
    if not (os.path.isfile(qemu) and os.access(qemu, os.X_OK)):
        missing.append("qemu")
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("Pillow")
    if missing:
        if os.environ.get("SVF_REQUIRE_SCREENS") == "1":
            print("fail: %s missing" % " and ".join(missing))
            return 1
        print("screen-%s: SKIPPED (missing: %s)" % (board, ", ".join(missing)))
        return 0
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGHUP, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    try:
        os.makedirs(out, exist_ok=True)
        run(qemu, elf, board, out)
    except Fail as e:
        print("fail: %s" % e)
        return 1
    print("ok: %s screendump + pmemsave" % board)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
