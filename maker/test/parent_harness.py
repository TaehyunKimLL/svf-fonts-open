#!/usr/bin/env python3
"""parent_harness.py OUT.json -- CMD...: run a server under a helper process, then kill the helper (a shell dying).

The harness makes itself a child subreaper (so a server whose parent dies is re-parented to it, not to init, and its
exit status can be read), forks a HELPER that starts CMD with stdout/stderr piped to the helper and
`--exit-with-parent=<helper pid>` appended, relays the server's lines to the harness, and sleeps. The harness
  - writes `OUT.json` = {"helper": pid, "server": pid} as soon as both exist,
  - appends every relayed line to `OUT.json.lines` (the test polls it for the port line),
  - waits for the file `OUT.json.kill` to exist, SIGKILLs the helper, waits for the re-parented server (at most 10 s) and
    rewrites `OUT.json` = {"helper", "server", "status": <exit code or -signal>, "seconds", "lines": [...]}.
The subreaper flag lives here, never in the unittest process. Linux only.
"""

import ctypes
import json
import os
import signal
import subprocess
import sys
import time

PR_SET_CHILD_SUBREAPER = 36


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def helper(cmd, wfd):
    """In the forked helper: start the server, relay its lines to the harness, sleep."""
    me = os.getpid()
    proc = subprocess.Popen(cmd + ["--exit-with-parent=%d" % me], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    os.write(wfd, ("server %d\n" % proc.pid).encode())
    for line in proc.stdout:                         # until the helper is killed (or the server ends)
        os.write(wfd, ("line " + line).encode())
    os.write(wfd, b"eof\n")
    time.sleep(3600)


def main():
    out = sys.argv[1]
    cmd = sys.argv[sys.argv.index("--") + 1:]
    ctypes.CDLL(None, use_errno=True).prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0)
    rfd, wfd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(rfd)
        helper(cmd, wfd)
        os._exit(0)
    os.close(wfd)
    server = None
    lines = []
    kill = out + ".kill"
    os.set_blocking(rfd, False)
    buf = ""
    started = time.monotonic()
    killed_at = None
    while True:
        try:
            chunk = os.read(rfd, 65536).decode("utf-8", "replace")
        except BlockingIOError:
            chunk = None
        if chunk:
            buf += chunk
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                if line.startswith("server "):
                    server = int(line.split()[1])
                    write_json(out, {"helper": pid, "server": server})
                elif line.startswith("line "):
                    lines.append(line[5:])
                    with open(out + ".lines", "a") as f:
                        f.write(line[5:] + "\n")
        if killed_at is None and os.path.exists(kill) and server is not None:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            killed_at = time.monotonic()
            break
        time.sleep(0.02)
    status = None
    deadline = killed_at + 10
    while time.monotonic() < deadline:
        try:
            done, st = os.waitpid(server, os.WNOHANG)
        except ChildProcessError:
            break
        if done:
            status = os.waitstatus_to_exitcode(st)
            break
        time.sleep(0.02)
    write_json(out, {"helper": pid, "server": server, "status": status, "seconds": round(time.monotonic() - killed_at, 3),
                     "lines": lines})


if __name__ == "__main__":
    main()
