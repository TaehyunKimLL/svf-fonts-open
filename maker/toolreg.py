#!/usr/bin/env python3
"""toolreg: the registry of running tool process groups, `<data_root>/tools.pids` (spec 7.10).

The two runners (`jobs.run_command`, `preview.run_bounded`) register each child right after `Popen` and unregister it
when it is reaped. A tool outlives the sidecar only if the sidecar dies without stopping it, and the next start reaps
the file first (`Registry.reap`), before any sweep, so a sweep never races a tool of the previous run.

A line is `"<pgid> <pid> <start time> <basename of argv0>"`. A child is identified by pid + start time (the start time
guards against pid reuse); argv0 is informational and never decides a kill (an external recogniser interpreter, a
source-mode python3 and a frozen tool of an AppImage mounted elsewhere all differ). Nothing is active at import: unit
tests that call the runners directly register nothing.
"""

import errno
import os
import subprocess
import sys
import time

import oscompat
import toolrun

REAP_EACH_S = 5.0
REAP_TOTAL_S = 10.0

_active = None


def squeeze(text):
    """@p text (`ps -o lstart=`: "Thu Nov  6 10:00:00 2026") as one token without spaces, or None when empty. macOS only;
    UNVERIFIED there (no macOS host)."""
    return "_".join(text.split()) or None


def start_time(pid):
    """The process start time as text: `/proc/<pid>/stat` field 22 (Linux), `ps -o lstart=` (macOS), the creation
    FILETIME (Windows), else None."""
    if oscompat.WINDOWS:
        return oscompat.process_start_time(pid)
    try:
        with open("/proc/%d/stat" % pid, "rb") as f:
            return f.read().rsplit(b")", 1)[1].split()[19].decode()
    except (OSError, IndexError):
        pass
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, timeout=5).stdout
            return squeeze(out.decode("utf-8", "replace"))
        except (OSError, subprocess.SubprocessError):
            return None
    return None


class Registry:
    def __init__(self, path):
        self.path = path
        self.lock_path = path + ".lock"

    def _locked(self):
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            oscompat.lock(fd)
        except BaseException:
            os.close(fd)
            raise
        return fd

    @staticmethod
    def _unlock(fd):
        try:
            oscompat.unlock(fd)
        finally:
            os.close(fd)

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return [line for line in f.read().splitlines() if line.strip()]
        except FileNotFoundError:
            return []

    def _write(self, rows):
        """Replace the file with @p rows, atomically (a temp file beside it, fsynced, then `os.replace`): a SIGKILL
        between the two steps leaves the old rows, never an empty file that forgets a live tool. Under the lock."""
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(row + "\n" for row in rows))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    @staticmethod
    def _report(exc):
        print("toolreg: %s" % errno.errorcode.get(exc.errno, "EIO"), file=sys.stderr, flush=True)

    def register(self, proc):
        """Append @p proc's line (pgid = pid: the runners start a new session) and remember this registry on it."""
        try:
            argv0 = proc.args[0] if isinstance(proc.args, (list, tuple)) and proc.args else proc.args
            row = "%d %d %s %s" % (proc.pid, proc.pid, start_time(proc.pid) or "0",
                                   os.path.basename(str(argv0)).replace(" ", "_"))
            fd = self._locked()
            try:
                with open(self.path, "a", encoding="utf-8", newline="\n") as f:
                    f.write(row + "\n")
            finally:
                self._unlock(fd)
            proc._svf_registry = self
        except OSError as exc:
            self._report(exc)

    def unregister(self, proc):
        """Remove @p proc's line from this registry."""
        try:
            fd = self._locked()
            try:
                mine = "%d %d " % (proc.pid, proc.pid)
                rows = self._read()
                kept = [row for row in rows if not row.startswith(mine)]
                if kept != rows:
                    self._write(kept)
            finally:
                self._unlock(fd)
        except OSError as exc:
            self._report(exc)

    def reap(self):
        """Kill every group a previous run left (pid alive and the same start time), bounded, then truncate the file.
        Returns `{"killed": n, "stale": n, "stuck": n}`; `stuck` entries are logged and the start proceeds."""
        result = {"killed": 0, "stale": 0, "stuck": 0}
        if not os.path.isdir(os.path.dirname(os.path.abspath(self.path))):
            return result                                  # a fresh data root: nothing was ever registered
        try:
            fd = self._locked()
        except OSError as exc:
            self._report(exc)
            return result
        try:
            started = time.monotonic()
            for row in self._read():
                parts = row.split()
                try:
                    pgid, pid, start = int(parts[0]), int(parts[1]), parts[2]
                except (IndexError, ValueError):
                    result["stale"] += 1
                    continue
                # register writes pgid = pid (a new session): a line that says otherwise is damaged, never killed
                if pgid != pid or not (toolrun.alive(pid) and start_time(pid) == start):
                    result["stale"] += 1
                    continue
                try:
                    oscompat.kill_registered(pgid)
                except OSError:
                    pass
                limit = started + REAP_TOTAL_S
                end = min(time.monotonic() + REAP_EACH_S, limit)
                while toolrun.alive(pid) and time.monotonic() < end:
                    time.sleep(0.02)
                if toolrun.alive(pid):
                    result["stuck"] += 1
                    print("toolreg: a tool group did not exit after SIGKILL", file=sys.stderr, flush=True)
                else:
                    result["killed"] += 1
            try:
                self._write([])
            except OSError as exc:
                self._report(exc)
        finally:
            self._unlock(fd)
        return result


def activate(reg):
    global _active
    _active = reg


def deactivate(reg):
    """Clear the active registry only when it is @p reg."""
    global _active
    if reg is not None and _active is reg:
        _active = None


def active():
    return _active


def register(proc):
    if _active is not None:
        _active.register(proc)


def unregister(proc):
    reg = getattr(proc, "_svf_registry", None)
    if reg is not None:
        reg.unregister(proc)
