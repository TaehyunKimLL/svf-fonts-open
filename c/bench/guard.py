#!/usr/bin/env python3
"""guard.py SECONDS OUT ERR -- COMMAND [ARGS...] - runs an emulator for the bench scripts so that none survives them.

stdout goes to OUT (at most 1 MiB) and stderr to ERR (at most 64 KiB); more than that, or more than SECONDS seconds,
kills the emulator and fails. SIGTERM, SIGINT and SIGHUP to guard.py kill the emulator's process group and fail; on
Linux the emulator also gets SIGKILL when guard.py itself dies (PR_SET_PDEATHSIG, as c/ports/check/esp-screen.py
does) and runs under RLIMIT_FSIZE 64 MiB. Exit status: the emulator's own, or 124 (time), 125 (output too large),
143 (a signal), 127 (cannot run). Run as `python3 -I guard.py ...`.
"""
import os
import select
import signal
import subprocess
import sys
import time

OUT_MAX = 1024 * 1024
ERR_MAX = 64 * 1024
FSIZE_MAX = 64 * 1024 * 1024


class Stop(Exception):
    def __init__(self, status, why):
        Exception.__init__(self, why)
        self.status = status


def _on_signal(signum, frame):
    for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(s, signal.SIG_IGN)
    raise Stop(143, "killed by signal %d" % signum)


def _child_setup(parent):
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


def main(argv):
    if len(argv) < 6 or argv[4] != "--":
        print("usage: guard.py SECONDS OUT ERR -- COMMAND [ARGS...]", file=sys.stderr)
        return 2
    seconds, out_path, err_path, cmd = float(argv[1]), argv[2], argv[3], argv[5:]
    for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(s, _on_signal)
    parent = os.getpid()
    try:  # if the script that started guard.py dies, this is a SIGTERM: the emulator is killed on the way out
        import ctypes
        ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM)
    except Exception:
        pass
    proc = None
    status = None
    bufs = {"out": bytearray(), "err": bytearray()}
    caps = {"out": OUT_MAX, "err": ERR_MAX}
    try:
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    start_new_session=True, preexec_fn=lambda: _child_setup(parent))
        except OSError as e:
            print("guard: cannot run %s: %s" % (cmd[0], e), file=sys.stderr)
            return 127
        fds = {proc.stdout.fileno(): "out", proc.stderr.fileno(): "err"}
        deadline = time.monotonic() + seconds
        while fds:
            left = deadline - time.monotonic()
            if left <= 0:
                raise Stop(124, "no end after %g s" % seconds)
            ready, _, _ = select.select(list(fds), [], [], min(left, 1.0))
            for fd in ready:
                data = os.read(fd, 65536)
                if not data:
                    del fds[fd]
                    continue
                k = fds[fd]
                bufs[k] += data
                if len(bufs[k]) > caps[k]:
                    raise Stop(125, "%s of %s over %d bytes" % (k, cmd[0], caps[k]))
        status = proc.wait(timeout=max(deadline - time.monotonic(), 0.1))
    except subprocess.TimeoutExpired:
        status = 124
        print("guard: no exit after %g s" % seconds, file=sys.stderr)
    except Stop as e:
        status = e.status
        print("guard: %s" % e, file=sys.stderr)
    finally:
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
        with open(out_path, "wb") as fh:
            fh.write(bufs["out"][:OUT_MAX])
        with open(err_path, "wb") as fh:
            fh.write(bufs["err"][:ERR_MAX])
    if status is not None and status < 0:
        status = 128 - status
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv))
