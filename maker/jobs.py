#!/usr/bin/env python3
"""The job store, the FIFO worker thread and the subprocess runner.

`Store` is the job directory's disk layout: `<data_root>/jobs/<id>/job.json` plus `upload/`, `work/` and `out/`, with
one `threading.Lock` per job so two HTTP handlers never write one `job.json` together (the tmp file and `os.replace`
make every reader see a whole file). `Worker` runs one job at a time off a `queue.Queue`, checks the cancel event
between steps and runs every tool through `run_command`, which reads a tool's stdout and stderr through pipes into the
step's own work directory and stops the tool's whole process group on the step timeout, on the cancel event, and the
moment either stream passes `OUTPUT_CAP` — the cap is hard: only the last `OUTPUT_CAP` bytes are kept, so a runaway
tool's gigabytes never reach memory, `log.md` or the zip.

`run_job` is the job's state machine: state `running`, the build log's header, then the steps in order (`settings
.plan_steps` built them). A failing step is not a failing job: the other steps still run and `zipout.write_zip` writes
what was produced; only a job with no `done` face (or a cancel, a name clash or a refused note) is `failed`.
`recover` runs once before `start` (a service restarted mid-job) and `retain` deletes old jobs after each one.

The library assumes `maker/` and `tools/` are on sys.path (the entry points set it).
"""

import contextlib
import json
import os
import queue
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import traceback
import zlib

import caps
import detect
import naming
import preview
import quality
import routes
import settings
import zipout
from sources import OutputGone, Sources, stat_id

STAT_TIMEOUT_S = 5.0          # a stat of a recorded output folder that takes longer counts as unreachable (hung mount)
STOP_STAT_TIMEOUT_S = 1.0     # the same at stop, so shutdown is not held by a mount


def stat_id_bounded(path, timeout=STAT_TIMEOUT_S):
    """`stat_id(path)`, but `OSError` when it does not return within @p timeout seconds (the stat runs in a daemon
    thread that is left behind)."""
    box = []

    def run():
        try:
            box.append(("ok", stat_id(path)))
        except BaseException as exc:
            box.append(("err", exc))
    thread = threading.Thread(target=run, daemon=True, name="svf-maker-stat")
    thread.start()
    thread.join(timeout)
    if not box:
        raise OSError("stat timed out: %s" % path)
    kind, value = box[0]
    if kind == "err":
        raise value
    return value

# The Global Constraints limits, verbatim.
STEP_TIMEOUT = 600
RECOG_TIMEOUT = 180                      # the identity scoring of one jamo step (maker/recog_score.py)
RECOG_ARRAYS = "numpy"                  # recog_score's input builder; a test with a stub recogniser says "lists"
JOB_TIMEOUT = 14400
OUTPUT_CAP = 4194304
KILL_GRACE = 5.0
MAX_JOBS = 20
MAX_AGE = 7 * 86400

# How often the runner looks at the child (the Task 12 brief's 0.5 s; the page's own poll is 2 s, Global Constraints).
POLL_S = 0.5

def exc_text(exc, local):
    """An exception as the text a job keeps (a step's `error`, a job's `error`). An upload job keeps the message. A local
    job never does: a parser's message may quote the bytes of the input it choked on, and job.json and log.md are
    persistent. It keeps the type, and the system's own `strerror` of an `OSError`."""
    if not local:
        return str(exc) or exc.__class__.__name__
    if isinstance(exc, OSError) and exc.strerror:
        return "%s: %s" % (type(exc).__name__, exc.strerror)
    return type(exc).__name__


# The one verdict line the tools print (jamoset.check / jamovec): fixed words and numbers only. A line that merely
# starts with "check" is not kept: its tail could be input text.
_TOOL_VERDICT = re.compile(
    r"^check: composed \d+ syllables from \d+ glyphs, JSET \d+ bytes"
    r"(; dy -?\d+\.\.-?\d+ on \d+ glyphs)?"
    r"(; tables are the adaptive layout's \(\d+/\d+/\d+ sets, \d+x\d+ classes\))?"
    r"(; identical to johab844\.py)?$")

# Set by make_server in local mode: what reaches stderr is the exception's type and frames, never its message.
SAFE_DIAGNOSTICS = False


def print_exc():
    """`traceback.print_exc()`; in local mode only the types and frames (`detect.safe_trace`)."""
    exc = sys.exc_info()[1]
    if SAFE_DIAGNOSTICS and exc is not None:
        print(detect.safe_trace(exc), file=sys.stderr, flush=True)
    else:
        traceback.print_exc()


def tool_text(text, local):
    """A tool's stdout or stderr as a local job keeps it: only the tools' own verdict lines (`check: ...`,
    `verify ...`), which carry numbers and fixed words; every other line may quote input bytes (a family name, a bad
    value) and is replaced by a count. An upload job keeps everything."""
    if not local:
        return text
    kept, dropped = [], 0
    for line in (text or "").splitlines():
        if _TOOL_VERDICT.match(line):
            kept.append(line)
        elif line.strip():
            dropped += 1
    if dropped:
        kept.append("[%d line(s) not kept: the tool's output may quote input bytes]" % dropped)
    return "\n".join(kept)


# A failed step's `stderr_tail` is the last 2000 characters of its stderr (Shared data shapes).
STDERR_TAIL = 2000

# The states `enqueue` accepts: a job `detect` just finished (`detected`), a `failed` job the owner re-runs, and a
# `queued` job `recover` puts back after a restart. Every other state is refused.
ENQUEUEABLE_STATES = ("detected", "failed", "queued")

# A job id is `secrets.token_hex(6)`: 12 lower-case hex digits, the only directory name `Store` accepts.
_ID_RE = re.compile(r"\A[0-9a-f]{12}\Z")

# The states `retain` may delete a job in; a `queued` or `running` job belongs to the worker.
RETAINED_STATES = ("done", "failed", "detected", "uploading")

# The Global Constraints subprocess form: an explicit environment, no shell, the step's work directory as cwd.
ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/"), "LANG": "C.UTF-8"}

# The errors reading a font's source can raise: a missing or unreadable file, and the decompression failures a
# `.gz` source's `preview.materialize` reports (preview's own list).
_SOURCE_ERRORS = (OSError, ValueError, EOFError, zlib.error, detect.TooLarge)


def _read_bytes(path):
    """@p path's bytes, or `None` when it cannot be read (the step then has no output)."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


# ---- the subprocess runner -------------------------------------------------------------------------------------

class _Capture:
    """One of a child's two pipes read by its own thread: a bounded tail of its bytes and a `over` flag past the cap.

    The thread reads 64 KiB chunks and keeps at most `cap` bytes in memory, so a runaway tool cannot fill the worker.
    Once more than `cap` bytes have come out it sets `over` and stops reading: the child then blocks on a full pipe,
    so what it writes past the cap is at most one pipe buffer (the caller kills it a poll later).
    """

    def __init__(self, stream, cap):
        self.stream = stream
        self.cap = cap
        self.data = bytearray()
        self.total = 0
        self.over = False
        self._thread = threading.Thread(target=self._drain, daemon=True)

    def start(self):
        self._thread.start()

    def join(self, timeout=None):
        """Wait for the reader; True when it finished (a descendant that left the group can hold the pipe open)."""
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _drain(self):
        try:
            while True:
                chunk = self.stream.read(1 << 16)
                if not chunk:
                    break
                self.total += len(chunk)
                self.data += chunk
                if len(self.data) > self.cap:       # keep only the last `cap` bytes
                    del self.data[:len(self.data) - self.cap]
                if self.total > self.cap:
                    self.over = True
                    break
        except (OSError, ValueError):
            return

    def write(self, path):
        """Write the kept tail to @p path, so a file behind the cap holds at most `cap` bytes."""
        with open(path, "wb") as f:
            f.write(self.data)

    def text(self):
        """The kept tail as UTF-8 text, undecodable bytes replaced."""
        return self.data.decode("utf-8", "replace")


def _signal_group(proc, sig):
    """Send @p sig to @p proc's process group, falling back to the process alone if the group is gone."""
    try:
        os.killpg(proc.pid, sig)
    except OSError:
        try:
            proc.send_signal(sig)
        except OSError:
            pass


def _stop(proc):
    """Stop @p proc's whole process group: `SIGTERM`, then `SIGKILL` after `KILL_GRACE` seconds (Global Constraints).

    `run_command` starts the child in its own session (`start_new_session=True`), so `proc.pid` is the group's leader
    and `killpg` reaches the grandchildren a tool may have spawned.
    """
    _signal_group(proc, signal.SIGTERM)
    try:
        proc.wait(KILL_GRACE)
    except subprocess.TimeoutExpired:
        pass
    _signal_group(proc, signal.SIGKILL)                 # always: a grandchild may outlive the reaped tool
    proc.wait()


def run_command(argv, cwd, timeout, cancel, env=None):
    """Run @p argv in @p cwd with stdout and stderr captured to files there; return the result dict.

    The child gets `env` (default `ENV`), no shell and no stdin, and runs in its own process group. `stdout.txt` and `stderr.txt` are
    truncated first and hold at most `OUTPUT_CAP` bytes each: the two pipes are read on their own threads into a
    bounded tail, and the moment either stream passes `OUTPUT_CAP` the whole group is stopped. The loop polls every
    `POLL_S` seconds for the exit, the timeout, the cancel event and the two readers' overflow; a stop leaves `exit`
    None and `error` the reason (`"timeout"`, `"cancelled"` or `"output over 4 MB"`). `stdout` and `stderr` are the
    kept tails as text (undecodable bytes replaced), so even a stopped runaway tool's tail is at hand for the log.
    """
    stdout_path = os.path.join(cwd, "stdout.txt")
    stderr_path = os.path.join(cwd, "stderr.txt")
    for path in (stdout_path, stderr_path):         # this run's files only, even if `Popen` fails
        with open(path, "wb"):
            pass
    started = time.monotonic()
    error = None
    proc = subprocess.Popen(argv, cwd=cwd, env=ENV if env is None else env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    out, err = _Capture(proc.stdout, OUTPUT_CAP), _Capture(proc.stderr, OUTPUT_CAP)
    out.start()
    err.start()
    try:
        while True:
            try:                                    # a blocking wait, so an exit is seen at once, not a poll late
                proc.wait(POLL_S)
            except subprocess.TimeoutExpired:
                pass
            if proc.poll() is not None:
                break
            if cancel.is_set():
                error = "cancelled"
            elif time.monotonic() - started > timeout:
                error = "timeout"
            elif out.over or err.over:
                error = "output over 4 MB"
            if error is not None:
                _stop(proc)
                break
    finally:
        if proc.poll() is None:                     # an exception in the loop must not leave the child running
            _stop(proc)
        _signal_group(proc, signal.SIGKILL)         # every path: no straggler of the group may hold a pipe open
        held = not (out.join(KILL_GRACE) and err.join(KILL_GRACE))
        if held and error is None:                  # a descendant that left the group (setsid) still holds a pipe
            error = "a descendant kept the output open"
        proc.stdout.close()
        proc.stderr.close()
    out.write(stdout_path)
    err.write(stderr_path)
    return {"exit": None if error is not None else proc.returncode, "seconds": round(time.monotonic() - started, 3),
            "stdout": out.text(), "stderr": err.text(), "error": error}


# ---- the F-gz rewrite ------------------------------------------------------------------------------------------

def _materialized_token(token, sources, work_dir, font_id):
    """@p token, or the decompressed path when it names a non-PCF `.gz` source under a root of @p sources.

    The source is matched by `os.path.realpath` (`Sources.inside`), so a trailing slash, a `..` or a symlinked upload directory is
    rewritten too (M3). The decompressed copy is `<work_dir>/<font id>/<name without .gz>`: the path
    `preview.materialize` writes and the worker passes on (`_plain_source`). A `.pcf.gz` source stays compressed
    (FreeType reads it), so it is left alone.
    """
    if not isinstance(token, str):
        return token
    if not sources.inside(token):
        return token
    resolved = os.path.realpath(token)
    name = os.path.basename(resolved)
    if not name.endswith(".gz") or name.endswith(".pcf.gz"):
        return token
    return os.path.join(work_dir, font_id, name[:-3])


def materialized_argv(steps, sources, work_dir):
    """The command argvs @p steps run with, in run order, each `.gz` upload replaced by its decompressed path.

    `POST /run`'s note check (Task 13) builds its steps with `settings.plan_steps` and calls this to see the command
    lines the tools really get, so a note it accepts is not refused later at the zip step (the Task 9 note). Each
    returned item is one command's argv (a list of tokens); `zipout`'s `shlex.join` form is the note's command line.
    A step with no argv (a copy) contributes nothing. @p sources (a `Sources` or an upload directory string) is compared by realpath (see
    `_materialized_token`) and @p work_dir is the job's `work/` directory.
    """
    sources = Sources.coerce(sources)
    out = []
    for step in steps:
        for argv in step.get("argv") or []:
            out.append([_materialized_token(token, sources, work_dir, step.get("font") or "f") for token in argv])
    return out


def own_earlier(job):
    """The `<dest>/<NAME>` paths (relative to `svf/`) a local job wrote on an earlier run, from its top-level `owned`
    record (which `POST detect` and `POST run` never reset)."""
    return frozenset(rel[len("svf/"):] for rel in (job.get("owned") or {}) if rel.startswith("svf/"))


# ---- the store -------------------------------------------------------------------------------------------------

FILES_DIR_PREFIX = ".svf-maker-"


class Store:
    """The job directories under `data_root`: `create`, `load`, `save`, `update`, `list`, `delete`, `path`."""

    def __init__(self, data_root):
        self.data_root = os.path.abspath(data_root)
        self.jobs_dir = os.path.join(self.data_root, "jobs")
        self._locks = {}
        self._locks_guard = threading.Lock()
        # Called with the job id after `delete` removed its directory (the server drops its per-font preview locks).
        self.on_delete = None
        # Called with a local job (a dict with `id` and `fonts`) -> a context manager that holds its preview locks while
        # its files directory is swept, so a preview GET cannot re-make the directory under `rmtree`.
        self.on_sweep = None
        self._pending_lock = threading.Lock()
        self._retry_lock = threading.Lock()

    def lock(self, job_id):
        """The `threading.Lock` of @p job_id, made once: two handlers never write one job's file together."""
        with self._locks_guard:
            lock = self._locks.get(job_id)
            if lock is None:
                lock = self._locks[job_id] = threading.Lock()
            return lock

    def path(self, job_id, *parts):
        """`<jobs_dir>/<id>/<parts...>`; a `KeyError` for an id that is not 12 hex digits (never a path escape)."""
        if not isinstance(job_id, str) or not _ID_RE.match(job_id):
            raise KeyError(job_id)
        return os.path.join(self.jobs_dir, job_id, *parts)

    def meta_dir(self, job_id):
        """The job's metadata directory (`job.json`, `log.md`, `steps/`): `path(job_id)`."""
        return self.path(job_id)

    def files_dir(self, job):
        """Where the job's `work/` and `out/` live: its own directory for an upload job, `<output_dir>/.svf-maker-<id>`
        for a local one."""
        if job.get("source") == "local":
            return os.path.join(job["output_dir"], FILES_DIR_PREFIX + job["id"])
        return self.path(job["id"])

    def ensure_files_dir(self, job):
        """Make a local job's files directory (`work/tmp` inside, all 0700) and return it.

        The output folder must still be the folder picked at create time (`output_id`), else `OutputGone`: nothing is
        made in a replaced folder. Only the levels made here are chmod'ed, never the output folder itself.
        """
        if job.get("source") != "local":
            return self.files_dir(job)
        try:
            same = stat_id(job["output_dir"]) == tuple(job.get("output_id") or ())
        except OSError:
            same = False
        if not same:
            raise OutputGone("output folder is gone or changed")
        files = self.files_dir(job)
        for path in (files, os.path.join(files, "work"), os.path.join(files, "work", "tmp")):
            try:
                mode = os.lstat(path).st_mode
            except FileNotFoundError:
                os.mkdir(path, 0o700)
                os.chmod(path, 0o700)
                continue
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):    # a link planted at the name would lead elsewhere
                raise OutputGone("the files directory is a link or not a folder: refusing to use it")
        job["files_id"] = list(stat_id(files))          # the directory's own identity (a run saves it and checks it per step)
        return files

    def sources(self, job):
        """The `Sources` the job reads its inputs from: its `upload/` directory, or a local job's picked roots."""
        if job.get("source") == "local":
            roots = job.get("roots") or []
            return Sources("local", [r["path"] for r in roots],
                           tmp_dir=os.path.join(self.files_dir(job), "work", "tmp"),
                           kinds=[r.get("kind", "dir") for r in roots])
        return Sources("upload", [self.path(job["id"], "upload")])

    def create(self, source="upload", output_dir=None, output_id=None):
        """A Job in state `uploading` (Shared data shapes). An upload job gets its directory with `upload/ work/ out/`.

        A local job (@p source `"local"`) gets only its metadata directory and a `job.json` that carries `source`,
        `output_dir`, `output_id` (the folder's `[st_dev, st_ino]`), `roots`, and `owned` (output-relative path ->
        sha256 of the bytes this job wrote there). `owned` is top-level on purpose: `POST detect` and `POST run`
        reset `result`, and must not forget what the job owns.
        """
        job = {"id": secrets.token_hex(6), "state": "uploading", "created": time.time(), "updated": time.time(),
               "error": None, "upload": {"files": 0, "bytes": 0, "refused": []}, "fonts": [],
               "settings": {"batch": {}, "fonts": {}}, "steps": [], "queue_position": None, "result": None}
        if source == "local":
            job.update(source="local", output_dir=output_dir, output_id=list(output_id), roots=[], owned={})
            os.makedirs(self.path(job["id"]), exist_ok=True)
        else:
            for part in ("upload", "work", "out"):
                os.makedirs(self.path(job["id"], part), exist_ok=True)
        self.save(job)
        return job

    def load(self, job_id):
        """The job of @p job_id; `KeyError` when the id is not 12 hex digits or its `job.json` cannot be read."""
        try:
            with open(os.path.join(self.path(job_id), "job.json"), encoding="utf-8") as f:
                job = json.load(f)
        except (OSError, UnicodeDecodeError, ValueError):
            raise KeyError(job_id)
        if not isinstance(job, dict) or job.get("id") != job_id:
            raise KeyError(job_id)
        return job

    def save(self, job):
        """Write @p job's `job.json` through `job.json.tmp` and `os.replace`, under the job's own lock."""
        with self.lock(job["id"]):
            self._write(job)

    def _write(self, job):
        """`save`'s body: the caller holds the job's lock (`update` holds it across load, `fn` and this write)."""
        job["updated"] = time.time()
        tmp = self.path(job["id"], "job.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2, sort_keys=True, ensure_ascii=False)
        os.replace(tmp, self.path(job["id"], "job.json"))

    def update(self, job_id, fn):
        """Load @p job_id, call `fn(job)`, save it and return it, all under the job's lock."""
        with self.lock(job_id):
            job = self.load(job_id)
            fn(job)
            self._write(job)
            return job

    def list(self):
        """One dict per job, newest first: `{"id", "state", "created", "fonts"}`, the last the font count.

        A directory that is not a job (a name that is not 12 hex digits, no readable `job.json`) is skipped, so one
        broken job never hides the others.
        """
        try:
            names = os.listdir(self.jobs_dir)
        except OSError:
            return []
        out = []
        for name in names:
            if not _ID_RE.match(name):
                continue
            try:
                job = self.load(name)
            except KeyError:
                continue
            out.append({"id": name, "state": job.get("state"), "created": job.get("created") or 0.0,
                        "fonts": len(job.get("fonts") or []), "source": job.get("source", "upload"),
                        "output_id": job.get("output_id")})
        out.sort(key=lambda item: (item["created"], item["id"]), reverse=True)
        return out

    def delete(self, job_id):
        """Remove the job's directory; `ValueError` for a `queued` or `running` job (the worker owns it).

        The state check and the removal hold the job's own lock (W1): a `POST /run` that turns an `uploading` job
        `queued` in the same instant is either seen by the check or waits for the removal, never lost between them.
        `on_delete` is called once the directory is gone (the caller's per-job bookkeeping).
        """
        lock = self.lock(job_id)
        with lock:
            job = self.load(job_id)
            if job.get("state") in ("queued", "running"):
                raise ValueError("job %s is %s" % (job_id, job.get("state")))
            if job.get("source") == "local":
                self.sweep_files(job)                     # before the metadata goes: a failure is kept as pending
            shutil.rmtree(self.path(job_id))
        with self._locks_guard:
            if self._locks.get(job_id) is lock:         # never drop a lock a later caller already made
                self._locks.pop(job_id, None)
        if self.on_delete is not None:
            self.on_delete(job_id)
        self.retry_pending_sweeps()                       # a folder that came back since the last sweep point


    # ---- the sweeps of a local job's files directory (`<output_dir>/.svf-maker-<id>/`) --------------------------

    def _pending_path(self):
        return os.path.join(self.data_root, "pending-sweeps.json")

    def _read_pending(self):
        try:
            with open(self._pending_path(), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []

    def _write_pending(self, entries):
        os.makedirs(self.data_root, exist_ok=True)
        tmp = self._pending_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
        os.replace(tmp, self._pending_path())

    def _add_pending(self, job, files, reason):
        entry = {"path": files, "output_dir": job.get("output_dir"), "output_id": job.get("output_id"),
                 "job": job["id"], "files_id": job.get("files_id")}
        with self._pending_lock:
            entries = self._read_pending()
            fresh = not any(e.get("path") == files for e in entries)
            if fresh:
                entries.append(entry)
                self._write_pending(entries)
        if not fresh:
            return                                        # logged when first recorded: once per directory, not per sweep
        try:
            zipout.append_log(self.path(job["id"]), "\nsweep: %s: %s; intermediate files may remain there\n"
                              % (files, reason))
        except OSError:
            pass                                          # the metadata directory is already gone

    def sweep_files(self, job, stat_timeout=None):
        """Remove a local job's files directory; True when it is gone. Never raises.

        Only when the output folder is still the one picked (`output_id`) and the path is a real directory. A failure
        (busy, changed folder) is recorded in `pending-sweeps.json` with the folder's identity and logged to `log.md`;
        `retry_pending_sweeps` takes it up later. The job's preview locks are held meanwhile (`on_sweep`).

        Lock order (one for the whole store): the preview locks, then nothing else; the pending-sweeps lock is taken only
        after they are released, and `retry_pending_sweeps` never holds it across the filesystem work."""
        if job.get("source") != "local":
            return True
        files = self.files_dir(job)
        reason = None
        try:
            hold = self.on_sweep(job) if self.on_sweep is not None else contextlib.nullcontext()
            with hold:
                try:
                    same = stat_id_bounded(job["output_dir"], STAT_TIMEOUT_S if stat_timeout is None else stat_timeout) == tuple(job.get("output_id") or ())
                except OSError:
                    same = False                                  # unmounted, removed: nothing can be said about the path
                if not same:
                    reason = "output folder is gone or changed"
                elif not os.path.lexists(files):
                    return True                                   # the folder is the one picked and the directory is gone
                else:
                    try:
                        if os.path.islink(files) or not os.path.isdir(files):
                            raise OSError("not a real directory")
                        shutil.rmtree(files)
                        return True
                    except Exception as exc:
                        reason = exc_text(exc, True) if type(exc) is not OutputGone else str(exc)
        except Exception:
            print_exc()
            return False
        try:
            self._add_pending(job, files, reason)                 # outside the preview locks
        except Exception:
            print_exc()
        return False

    def retry_pending_sweeps(self, stat_timeout=None):
        """Retry each pending sweep; it deletes only a real `.svf-maker-<job id>` directory directly inside the output
        folder it was recorded for, when that folder is still the same one. An entry is dropped when the directory is
        gone, when the retry succeeds, or when a check on the directory fails. While another folder (or none) is
        mounted at the path the entry stays: it is taken up when the ORIGINAL identity returns.

        The pending lock is held only to read the list and to write the result; the stats and the removal run outside it,
        under the job's preview locks (the order `sweep_files` uses). One retry runs at a time; a second caller returns.
        @p stat_timeout bounds each stat of a recorded folder (a hung mount counts as unreachable)."""
        if not self._retry_lock.acquire(blocking=False):
            return
        try:
            with self._pending_lock:
                entries = self._read_pending()
            if not entries:
                return                                            # nothing to retry: no file is written
            timeout = STAT_TIMEOUT_S if stat_timeout is None else stat_timeout
            dropped = []
            for entry in entries:
                try:
                    path, job_id = entry["path"], entry["job"]
                    out, oid = entry["output_dir"], tuple(entry["output_id"])
                    name = ".svf-maker-" + job_id
                    try:
                        mounted = stat_id_bounded(out, timeout) == oid
                    except OSError:
                        continue                                  # the folder cannot be reached (unmounted): keep it
                    if not mounted:
                        continue                                  # another folder is mounted there: wait for the original
                    if not os.path.lexists(path):
                        dropped.append(path)                      # confirmed gone
                        continue
                    if (not re.match(r"^\.svf-maker-[0-9a-f]{12}$", name)
                            or os.path.basename(path) != name or os.path.dirname(path) != out
                            or os.path.islink(path) or not os.path.isdir(path)):
                        print("sweep: %s: not the directory this job made; left alone" % path, file=sys.stderr)
                        dropped.append(path)
                        continue
                    try:
                        job = self.load(job_id)
                    except KeyError:
                        job = {"id": job_id, "fonts": []}
                    hold = self.on_sweep(job) if self.on_sweep is not None else contextlib.nullcontext()
                    with hold:
                        shutil.rmtree(path)
                    dropped.append(path)
                except Exception as exc:
                    print("sweep: %s: %s" % (entry.get("path"), exc), file=sys.stderr)
            if dropped:
                with self._pending_lock:                          # entries added meanwhile are kept
                    current = self._read_pending()
                    kept = [e for e in current if e.get("path") not in dropped]
                    if kept != current:
                        self._write_pending(kept)
        finally:
            self._retry_lock.release()


# ---- the worker ------------------------------------------------------------------------------------------------

class Worker(threading.Thread):
    """One job at a time off a FIFO queue: `enqueue`, `position`, `cancel`, `recover`, `retain`, `run_job`."""

    def __init__(self, store, repo_dir, svf_dir, tools_dir, caps=None):
        super().__init__(daemon=True, name="svf-maker-worker")
        self.caps = caps if caps is not None else {}      # the server's capabilities (maker/caps.py)
        self.store = store
        self.repo_dir = repo_dir
        self.svf_dir = svf_dir
        self.tools_dir = tools_dir
        self.queue = queue.Queue()
        self.cancels = {}                       # job id -> threading.Event, one per enqueued job
        self._queued = []                       # the ids in the queue, in order (only `position` needs them)
        self._current = None                    # the id `run_job` is running, or None
        self._stopping = False                  # `stop` was called: no job starts any more
        self._lock = threading.Lock()

    def enqueue(self, job_id):
        """Put @p job_id at the back of the queue after marking it `queued`; return its queue position (W13).

        Only a `detected`, `failed` (the owner re-runs it) or `queued` (a restart's `recover` puts it back) job is
        accepted; an `uploading`, `running` or `done` job raises `ValueError` (M5). A job already in the queue or
        running is a no-op, so a double `POST /run` cannot duplicate a queue entry or replace a running job's cancel
        event; its current position (or `None` when it is running) is still returned. The position is read under the
        queue's own lock, so `POST /run` reports the place the job really got, not what the queue holds a moment later.
        """
        with self._lock:
            if job_id in self._queued or self._current == job_id:
                return self._position_locked(job_id)
        job = self.store.load(job_id)
        if job.get("state") not in ENQUEUEABLE_STATES:
            raise ValueError("job %s is %s" % (job_id, job.get("state")))
        event = threading.Event()
        self.store.update(job_id, lambda job: job.update(state="queued", error=None))
        with self._lock:
            if job_id in self._queued:              # another enqueue won the race
                return self._position_locked(job_id)
            self.cancels[job_id] = event
            self._queued.append(job_id)
            position = len(self._queued)
        self.queue.put(job_id)
        return position

    def _position_locked(self, job_id):
        """The position of @p job_id with `self._lock` already held (`position`'s body)."""
        if job_id in self._queued:
            return self._queued.index(job_id) + 1
        return None

    def position(self, job_id):
        """1 for the next job to run, 2 for the one after it, ...; `None` when it is not queued."""
        with self._lock:
            return self._position_locked(job_id)

    def cancel(self, job_id):
        """`"cancelled"` (a queued job, failed at once), `"signalled"` (the running one), else `"not running"`.

        The queued case is atomic with the worker's dequeue (M1): the state check, the `job.json` write and the queue
        bookkeeping all happen under `self._lock`, the same lock `_claim` holds when it re-reads the job's state, so a
        job `cancel` reports `"cancelled"` never runs.
        """
        with self._lock:
            if job_id in self._queued:
                self._queued.remove(job_id)
                self.cancels.pop(job_id, None)
                self.store.update(job_id, lambda job: job.update(state="failed", error="cancelled"))
                return "cancelled"
            if self._current == job_id:
                event = self.cancels.get(job_id)
                if event is not None:
                    event.set()
                return "signalled"
            return "not running"

    def stop(self, timeout=30):
        """Stop for good: no job starts any more, the running one is cancelled through the usual group kill (every tool
        child runs in its own session and would outlive this process), and the call waits up to @p timeout seconds for it
        to end, then ends the worker thread (a sentinel on the queue, joined). Idempotent; True when nothing was left
        running."""
        with self._lock:
            self._stopping = True
            for event in self.cancels.values():
                event.set()
        preview.kill_all()                          # an in-flight bake or probe of a request thread has its own session too
        deadline = time.monotonic() + timeout
        idle = False
        while time.monotonic() < deadline:
            with self._lock:
                if self._current is None:
                    idle = True
                    break
            time.sleep(0.05)
        if self.is_alive():
            self.queue.put(None)                    # end the thread: it would block in queue.get() for ever
            if idle and threading.current_thread() is not self:
                self.join(max(0.0, deadline - time.monotonic()) + 1.0)
        self.sweep_local_files()                    # whatever a GET re-made, and the running job's leftovers
        return idle

    def sweep_local_files(self):
        """Sweep the files directory of every local job (at stop; the start-up thread does the same). The stats are
        bounded by `STOP_STAT_TIMEOUT_S`: a hung mount must not hold shutdown."""
        self.store.retry_pending_sweeps(STOP_STAT_TIMEOUT_S)
        for item in self.store.list():
            if item.get("source") == "local":
                try:
                    self.store.sweep_files(self.store.load(item["id"]), STOP_STAT_TIMEOUT_S)
                except KeyError:
                    continue

    def recover(self):
        """Called once before `start()`: a `running` job is `failed`/`interrupted`, a `queued` one re-enqueued.

        A job the service was running when it stopped has a half-written `work/` and no zip worth offering: it is
        marked `failed` with `error = "interrupted"`. The `queued` jobs are put back in their creation order, so the
        owner's oldest job runs first.
        """
        jobs = self.store.list()
        for item in jobs:
            # a local job that was queued is not re-enqueued either: its files directory is gone with the process
            if item["state"] == "running" or (item["state"] == "queued" and item.get("source") == "local"):
                try:
                    self.store.update(item["id"], lambda job: job.update(state="failed", error="interrupted"))
                except KeyError:
                    continue
        for item in sorted(jobs, key=lambda item: item["created"]):
            if item["state"] == "queued" and item.get("source") != "local":
                try:
                    self.enqueue(item["id"])
                except KeyError:
                    continue

    def retain(self):
        """Delete the oldest finished jobs while the store holds more than `MAX_JOBS`, and any past `MAX_AGE`.

        Only `done`/`failed`/`detected`/`uploading` jobs are candidates, never a `queued` or `running` one. The
        candidates are sorted oldest first, so the first job inside both limits ends the pass; a job the worker
        enqueued since the walk is refused by `delete` and left for the next pass, and a job whose directory cannot be
        removed (an `OSError`, e.g. a file a handler has open) is skipped rather than raising (I3).
        """
        jobs = self.store.list()
        total = len(jobs)
        candidates = sorted((item for item in jobs if item["state"] in RETAINED_STATES),
                            key=lambda item: (item["created"], item["id"]))
        for item in candidates:
            if total <= MAX_JOBS and time.time() - item["created"] <= MAX_AGE:
                break
            try:
                self.store.delete(item["id"])
            except (ValueError, KeyError, OSError):
                continue
            total -= 1

    def _claim(self, job_id):
        """Take @p job_id off the queue under `self._lock` and return the state it held (`None` when it is gone).

        The state is read under the same lock `cancel` writes it, so a queued job cancelled in this window is seen as
        `failed` here and skipped, never run (M1).
        """
        with self._lock:
            if job_id in self._queued:
                self._queued.remove(job_id)
            self._current = job_id
            try:
                return self.store.load(job_id).get("state")
            except KeyError:
                return None

    def run(self):
        """The thread's loop: one job at a time; a job cancelled while it was queued is skipped, never run.

        No exception ends the loop: a job that raises is handled by `run_job`, and a housekeeping (`retain`) failure is
        logged and skipped (V3), so every later job still runs.
        """
        while True:
            job_id = self.queue.get()
            if job_id is None:                      # `stop` posted the sentinel: the thread ends
                self.queue.task_done()
                return
            try:
                if self._stopping:                  # the server is going down: a queued job stays queued for the next start
                    continue
                if self._claim(job_id) == "queued":
                    self.run_job(job_id)
            except Exception:                       # one broken job must not stop the worker for the others
                self._log_failure(job_id, self._trace_text(job_id))
            finally:
                with self._lock:
                    if self._current == job_id:
                        self._current = None
                    self.cancels.pop(job_id, None)
                self.queue.task_done()
                try:
                    self.retain()
                except Exception:                   # housekeeping must not kill the worker either
                    self._log_failure(job_id, self._trace_text(job_id))

    @staticmethod
    def _output_same(job):
        """True while a local job's output folder is still the folder that was picked, and its files directory (when
        the job has made one) is still the directory it made: not replaced, not turned into a link."""
        try:
            if stat_id(job["output_dir"]) != tuple(job.get("output_id") or ()):
                return False
            known = job.get("files_id")
            if known:
                files = os.path.join(job["output_dir"], FILES_DIR_PREFIX + job["id"])
                st = os.lstat(files)
                if stat.S_ISLNK(st.st_mode) or [st.st_dev, st.st_ino] != list(known):
                    return False
            return True
        except OSError:
            return False

    def _finish_local(self, job_id):
        """After a local job: its reports and identity scores move to `<metadata>/steps/` (the files directory is about
        to go), then the files directory is swept. The sweep does not depend on the move: it runs in a `finally`, so a
        report that cannot be kept (steps/ unwritable, disk full, the save failing) never leaves the intermediates
        behind. A kept file of an earlier run whose step produced none this time is removed: it is not this run's.
        Never raises."""
        def move(j):
            meta, files = self.store.meta_dir(j["id"]), self.store.files_dir(j)
            os.makedirs(os.path.join(meta, "steps"), exist_ok=True)
            for step in j.get("steps") or []:
                sid = step.get("id")
                for kind in ("report", "identity"):
                    src = os.path.join(files, "work", sid or "", kind + ".json")
                    dst = os.path.join(meta, "steps", "%s.%s.json" % (sid, kind))
                    if sid and os.path.isfile(src):
                        shutil.copyfile(src, dst)
                        if kind == "report" and step.get("report"):
                            step["report"] = "steps/%s.report.json" % sid
                    elif sid and os.path.isfile(dst):
                        os.remove(dst)
        try:
            try:
                self.store.update(job_id, move)
            except Exception:
                self._log_failure(job_id, self._trace_text(job_id))
        finally:
            try:
                if not self.store.sweep_files(self.store.load(job_id)):
                    self.store.update(job_id, lambda j: j.update(
                        notice="intermediate files remain in %s inside the output folder (moved, removed or busy); "
                               "they are swept when the folder is back" % (FILES_DIR_PREFIX + job_id)))
                self.store.retry_pending_sweeps()
            except Exception:
                self._log_failure(job_id, self._trace_text(job_id))

    def _job_env(self, job):
        """A local job's tool environment: `TMPDIR` inside its files directory, no bytecode beside the tools. None
        (the default `ENV`) for an upload job."""
        if job.get("source") != "local":
            return None
        return dict(ENV, TMPDIR=os.path.join(self.store.files_dir(job), "work", "tmp"), PYTHONDONTWRITEBYTECODE="1")

    def _trace_text(self, job_id):
        """The traceback of the exception being handled, as text safe to keep: a local job's has no messages."""
        try:
            local = self.store.load(job_id).get("source") == "local"
        except Exception:
            local = False
        return detect.safe_trace(sys.exc_info()[1]) if local else traceback.format_exc()

    def _log_failure(self, job_id, text):
        """Put @p text in @p job_id's `log.md` when its directory is still there, else on stderr (V3)."""
        try:
            zipout.append_log(self.store.path(job_id), "\nworker: %s\n" % text)
        except Exception:
            print_exc()

    # ---- one job -----------------------------------------------------------------------------------------------

    def run_job(self, job_id):
        """Run every step of @p job_id in order, then write the zip: the Job's state machine.

        The header is logged once; a `prepare` failure marks every later step of that font and layout `master failed`;
        the cancel event is checked between steps (the rest fail `"cancelled"`, the job is `failed`/`"cancelled"`) and
        so is `JOB_TIMEOUT` (the rest fail `"job timeout"`). A step's own failure never stops the others. Any other
        exception is caught here, so the job is left `failed` with `"<ExcType>: <message>"`, never `running` (I2).
        """
        job = self.store.load(job_id)
        job_dir = self.store.path(job_id)
        files_dir = self.store.files_dir(job)
        sources = self.store.sources(job)
        cancel = self.cancels.get(job_id)
        if cancel is None:                          # a direct caller has no event yet
            cancel = threading.Event()
        job["state"] = "running"
        job["error"] = None
        self.store.save(job)
        try:
            if job.get("source") == "local":
                self.store.ensure_files_dir(job)
                files_id = job.get("files_id")
                self.store.update(job_id, lambda j: j.update(files_id=files_id))
            self._run_steps(job, job_dir, files_dir, sources, cancel)
        except OutputGone as exc:
            self._job_failed(job_id, job_dir, exc)
        except Exception as exc:
            if job.get("source") == "local" and not self._output_same(job):
                exc = OutputGone("output folder is gone or changed")     # the folder went away under a step
            self._job_failed(job_id, job_dir, exc)
        finally:
            if job.get("source") == "local":
                self._finish_local(job_id)

    def _run_steps(self, job, job_dir, files_dir, sources, cancel):
        """`run_job`'s body, once the job is `running` and its cancel event is settled."""
        zipout.append_log(job_dir, zipout.log_header(job, zipout.repo_head(self.repo_dir)))
        fonts = job.get("fonts") or []
        fonts_by_id = {font["id"]: font for font in fonts}
        gz_upload = {}                              # the realpath of a `.gz` upload -> its font (the M3 rewrite)
        for font in fonts:
            if font.get("gzip"):
                try:
                    gz_upload[os.path.realpath(sources.abs_of(font.get("root", 0), font.get("path")))] = font
                except ValueError:
                    pass                                # a path outside the roots is refused when its step is planned
        plain = {}                                  # font id -> the decompressed copy of a .gz source
        started = time.monotonic()
        steps = job.get("steps") or []
        steps_by_id = {step.get("id"): step for step in steps}
        for index, step in enumerate(steps):
            if step.get("state") == "failed":       # a later step an earlier failure already stopped
                continue
            if cancel.is_set():
                reason = "interrupted" if self._stopping else "cancelled"
                self._fail_steps(job, job_dir, steps[index:], reason)
                job["state"] = "failed"
                job["error"] = reason
                self.store.save(job)
                return
            if time.monotonic() - started > JOB_TIMEOUT:
                self._fail_steps(job, job_dir, steps[index:], "job timeout")
                job["error"] = job.get("error") or "job timeout"   # the first error wins (M4/V7)
                break
            if job.get("source") == "local" and not self._output_same(job):
                raise OutputGone("output folder is gone or changed")
            failed_need = next((n for n in step.get("needs") or []
                                if (steps_by_id.get(n) or {}).get("state") == "failed"), None)
            if failed_need is not None:                 # a companion's source step failed: this one cannot read it
                self._fail_step(job, job_dir, step, "companion source failed")
                continue
            self._run_step(job, job_dir, files_dir, sources, gz_upload, plain, fonts_by_id, step, cancel)
            if step.get("state") == "failed" and step.get("kind") == "source":
                for later in steps[index + 1:]:
                    if later.get("state") != "failed" and later.get("font") == step.get("font"):
                        self._fail_step(job, job_dir, later, "source failed")
            if step.get("state") == "failed" and step.get("kind") == "prepare":
                for later in steps[index + 1:]:
                    if (later.get("state") != "failed" and later.get("font") == step.get("font")
                            and later.get("layout") == step.get("layout")):
                        self._fail_step(job, job_dir, later, "master failed")
        if cancel.is_set():                         # cancelled while the last step ran
            job["state"] = "failed"
            job["error"] = "interrupted" if self._stopping else "cancelled"
            self.store.save(job)
            return
        self._write_output(job, job_dir, files_dir, sources, fonts, fonts_by_id, steps)

    def _job_failed(self, job_id, job_dir, exc):
        """A job whose body raised: `failed` with `"<ExcType>: <message>"`, its unfinished steps failed with it (I2).

        The job is never left `running`: an exception the state machine does not model (a `Popen` `OSError`, a
        `write_zip` `OSError`, a disk-full `save`) is turned into a `failed` job under the job's own lock, so the page
        and `delete`/`cancel` see a finished job. The stack goes to the job's `log.md`; a second failure while
        recording the first is printed, not raised.
        """
        full = traceback.format_exc()
        safe = detect.safe_trace(exc)

        def fail(job):
            if job.get("source") == "local":                     # no exception message in a local job's records
                message = str(exc) if isinstance(exc, OutputGone) else exc_text(exc, True)
                self._fail_job(job, job_dir, message, safe)
            else:
                self._fail_job(job, job_dir, str(exc) if isinstance(exc, OutputGone)
                               else "%s: %s" % (type(exc).__name__, exc), full)
        try:
            self.store.update(job_id, fail)
        except Exception:
            print_exc()

    def _fail_job(self, job, job_dir, message, detail=None):
        """Mark @p job `failed` with @p message and fail its `running`/`pending` steps; the caller holds the job lock."""
        job["state"] = "failed"
        job["error"] = message
        for step in job.get("steps") or []:
            if step.get("state") in ("running", "pending"):
                step["state"] = "failed"
                step["error"] = message
        try:
            zipout.append_log(job_dir, "\n%s\n%s\n" % (message, detail or ""))
        except Exception:
            print_exc()

    def _run_step(self, job, job_dir, files_dir, sources, gz_upload, plain, fonts_by_id, step, cancel):
        """Run one step: `running`, its commands (or its copy), its facts, its preview, its log block and a save."""
        step["state"] = "running"
        step["identity"] = None                     # the scores of an earlier run are not this build's
        self.store.save(job)
        font = fonts_by_id.get(step.get("font")) or {}
        stdout, stderr, error = self._execute(files_dir, sources, gz_upload, plain, step, font, cancel,
                                                  self._job_env(job))
        if error == "cancelled" and self._stopping:
            error = "interrupted"                   # the server stopped, not the owner
        if error is None and step.get("kind") not in ("prepare", "source"):
            error = self._read_back(job, files_dir, sources, plain, step, font, cancel, stdout)
        if error is not None:
            step["state"] = "failed"
            step["error"] = error
        else:
            step["state"] = "done"
        local = sources.kind == "local"
        step["stderr_tail"] = tool_text(stderr, local)[-STDERR_TAIL:]
        zipout.append_log(job_dir, zipout.log_step(step, tool_text(stdout, local), tool_text(stderr, local)))
        self.store.save(job)

    def _execute(self, files_dir, sources, gz_upload, plain, step, font, cancel, env=None):
        """Run the step's commands (or its copy); return `(stdout, stderr, the error or None)`.

        A step with no argv is the maker's own copy of its font's source (a route that ships the face as it is), not a
        subprocess. Every other step runs each argv in the output's own work directory with `STEP_TIMEOUT`; the first
        stop or non-zero exit ends the step, and an output the tool never wrote fails it too. A `.gz` source is
        replaced by its decompressed copy in the argv the log then names (the F-gz ruling).
        """
        argvs = step.get("argv") or []
        out_abs = os.path.join(files_dir, step.get("output") or "")
        self._clear_outputs(os.path.dirname(out_abs), out_abs, step)      # a copy step too: no stale report or scores
        if not argvs:
            try:
                source = self._plain_source(font, files_dir, sources, plain)
                os.makedirs(os.path.dirname(out_abs), exist_ok=True)
                shutil.copyfile(source, out_abs)
            except _SOURCE_ERRORS as exc:
                return "", "", exc_text(exc, sources.kind == "local")
            step["exit"] = 0
            step["seconds"] = 0.0
            return "", "", None
        try:
            step["argv"] = [[self._plain_token(token, files_dir, sources, gz_upload, plain) for token in argv]
                            for argv in argvs]
        except _SOURCE_ERRORS as exc:
            return "", "", exc_text(exc, sources.kind == "local")
        stdout, stderr, seconds = [], [], 0.0
        cwd = os.path.dirname(out_abs)
        for argv in step["argv"]:
            result = run_command(argv, cwd, STEP_TIMEOUT, cancel, env)
            stdout.append(result["stdout"])
            stderr.append(result["stderr"])
            seconds += result["seconds"]
            step["exit"] = result["exit"]
            step["seconds"] = round(seconds, 3)
            if result["error"] is not None:
                return "".join(stdout), "".join(stderr), result["error"]
            if result["exit"] != 0:
                return "".join(stdout), "".join(stderr), "exit %s" % result["exit"]
        if not os.path.exists(out_abs):
            return "".join(stdout), "".join(stderr), "no output"
        return "".join(stdout), "".join(stderr), None

    @staticmethod
    def _clear_outputs(cwd, out_abs, step):
        """Remove what an earlier run left where this step writes: a tool that exits 0 without writing must fail "no
        output", not pass on the old file (a re-detected job reuses `work/sNN/`)."""
        stale = [out_abs, os.path.join(cwd, "report.json"),      # a failed re-run must not show the last run's report
                 os.path.join(cwd, "identity.json")]            # nor serve the last build's piece scores
        if step.get("kind") == "source":
            stale += [os.path.join(cwd, name) for name in os.listdir(cwd) if name.startswith("source-")] \
                if os.path.isdir(cwd) else []
        for path in stale:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except OSError:
                shutil.rmtree(path, ignore_errors=True)

    def _read_back(self, job, files_dir, sources, plain, step, font, cancel=None, stdout=""):
        """Read a produced face back: its facts and its quality numbers; return an error or None.

        `quality.face_facts` comes first and `quality.measure` only when it succeeded (measure does not re-validate
        the bytes), and a ValueError from either fails the step with its message (the Task 8 ruling). A `jamo` step
        whose route names a reference is scored against it. The page draws the face itself (WASM); no picture is written.
        """
        out_abs = os.path.join(files_dir, step.get("output") or "")
        data = _read_bytes(out_abs)
        if data is None:
            return "no output"
        try:
            step["facts"] = quality.face_facts(data)
            reference = self._reference(job, font, step)
            if step.get("kind") == "jamo" and reference:
                source = (self._prepared_source(job, files_dir, step.get("font"))
                          or self._plain_source(font, files_dir, sources, plain))
                step["quality"] = quality.measure(data, reference, source, step.get("size"))
        except ValueError as exc:
            return exc_text(exc, sources.kind == "local")
        except _SOURCE_ERRORS as exc:
            return exc_text(exc, sources.kind == "local")
        if step.get("kind") == "jamo":
            step["identity"] = self._identity(files_dir, step, cancel or threading.Event(), stdout, self._job_env(job))
        return None

    def _identity(self, files_dir, step, cancel, stdout, env=None):
        """The identity check of a `jamo` step (spec 9.3): `maker/recog_score.py` run as a subprocess with the recogniser's
        folder in its environment, `RECOG_TIMEOUT` and the job's cancel. Never fails the step: the result is
        `{"available": true, ...the face summary}`, `{"available": false, "error": ...}` (a non-zero exit, a timeout, an
        unreadable JSON), or without the capability `{"available": false, "structural": <the `check:` line>}`. The
        scorer's full JSON stays in `work/sNN/identity.json`."""
        local = env is not None                         # only a local job has a tool environment of its own
        recog = caps.recog_dir(os.environ) if self.caps.get("recog") else None
        if recog is None:
            line = next((l for l in (stdout or "").splitlines() if _TOOL_VERDICT.match(l)), "")
            return {"available": False, "structural": line}
        step_dir = os.path.join(files_dir, "work", step.get("id") or "")
        out_json = os.path.join(step_dir, "identity.json")
        work = os.path.join(step_dir, "identity")
        try:
            os.remove(out_json)
        except OSError:
            pass
        os.makedirs(work, exist_ok=True)
        argv = routes.PY + [os.path.join(os.path.dirname(os.path.abspath(__file__)), "recog_score.py"),
                            os.path.join(files_dir, step.get("output") or ""), "-o", out_json, "--threads", "2",
                            "--arrays", RECOG_ARRAYS]
        result = run_command(argv, work, RECOG_TIMEOUT, cancel, dict(env or ENV, SVF_RECOG_DIR=recog))
        if result["error"] is not None or result["exit"] != 0:
            tail = (result["stderr"] or "").strip().splitlines()
            reason = "timed out" if result["error"] == "timeout" else (
                result["error"] or (tail[-1] if tail and not local else "exit %s" % result["exit"]))
            return {"available": False, "error": reason}
        try:
            with open(out_json, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            return {"available": False, "error": "unreadable identity.json: %s" % exc_text(exc, local)}
        if not data.get("applicable", True):
            return {"available": True, "applicable": False, "reason": data.get("reason", "")}
        return dict(data.get("face") or {}, available=True)

    @staticmethod
    def _reference(job, font, step):
        """The source a `jamo` step's numbers are scored against: its route's `reference`, or `None`.

        The route is looked up the way the page does (`routes.route_for` with the font's own `experimental`): a
        source kind with no jamo route, and a non-experimental fit, simply score nothing. A malformed font entry or
        settings dict is read as no reference rather than failing the step.
        """
        if not isinstance(font, dict):
            return None
        try:
            eff = settings.effective(job.get("fonts") or [], job.get("settings") or {}, step.get("font"))
            route = routes.route_for(font, "jamo", bool(eff.get("experimental")), eff.get("jamo_route"))
        except (KeyError, TypeError, ValueError):
            return None
        return route.reference if route is not None else None

    @staticmethod
    def _prepared_source(job, files_dir, font_id):
        """The file a `done` `source` step of @p font_id wrote (the font as the tools read it), else `None`."""
        for step in job.get("steps") or []:
            if step.get("font") == font_id and step.get("kind") == "source" and step.get("state") == "done":
                return os.path.join(files_dir, step.get("output") or "")
        return None

    def _plain_source(self, font, files_dir, sources, plain):
        """The path a tool must read for @p font: its upload file, or the decompressed copy of a `.gz` source.

        The F-gz ruling: a non-PCF `.gz` source (its entry carries `"gzip": true`) is decompressed once into
        `work/<font id>/<name without .gz>` and that path is passed on. `preview.materialize` holds the copy to
        `detect.MAX_DECOMPRESSED` and replaces an earlier one atomically; a PCF entry carries no `gzip` flag
        (FreeType reads a `.pcf.gz` itself), so it keeps its own path.
        """
        source = sources.abs_of(font.get("root", 0), font.get("path"))
        if not font.get("gzip"):
            return source
        font_id = font.get("id") or "f"
        if font_id not in plain:
            work = os.path.join(files_dir, "work", font_id)
            os.makedirs(work, exist_ok=True)
            plain[font_id] = preview.materialize(source, work)
        return plain[font_id]

    def _plain_token(self, token, files_dir, sources, gz_upload, plain):
        """@p token, or the decompressed path when it names a `.gz` source (`settings.plan_steps`' argv form).

        The token is matched by `os.path.realpath` against the `.gz` uploads' realpaths, so an equivalent but
        differently spelled upload directory still gets the rewrite (M3).
        """
        font = gz_upload.get(os.path.realpath(token)) if isinstance(token, str) else None
        if font is None:
            return token
        return self._plain_source(font, files_dir, sources, plain)

    def _write_output(self, job, job_dir, files_dir, sources, fonts, fonts_by_id, steps):
        """`zipout.write_zip` for @p job and the Job's final state; a refusal fails the job with its message.

        `write_zip` never returns None: it raises `NameClash` (the job's error names the path), `NoteRefused` (it set
        `job["error"]` itself) or another `ValueError`. A `NoteRefused`/`ValueError` message is kept even when the job
        timed out first, so the real cause replaces `"job timeout"` (M4/V7). On success `write_zip` has set
        `identical_to` on the steps, so the result and the state are saved together in one write. A local job writes
        a folder tree instead (`_write_tree`).
        """
        if job.get("source") == "local":
            self._write_tree(job, job_dir, files_dir, sources, fonts, fonts_by_id, steps)
            return

        def effective(font_id):
            # a step whose font is no longer in the job reads no destination and fails as `write_zip` sees fit
            if font_id not in fonts_by_id:
                return {}
            return settings.effective(fonts, job.get("settings") or {}, font_id)

        try:
            result = zipout.write_zip(job, job_dir, naming.RepoIndex(self.svf_dir), fonts_by_id, effective,
                                      self.repo_dir, files_dir=files_dir, sources=sources)
        except zipout.NameClash as exc:
            job["state"] = "failed"
            job["error"] = "name clash: %s" % exc.path
        except (zipout.NoteRefused, ValueError) as exc:
            job["state"] = "failed"
            job["error"] = str(exc)
        else:
            job["result"] = result
            if any(step.get("state") == "done" and step.get("kind") in ("precomposed", "jamo") for step in steps):
                job["state"] = "done"
            else:
                job["state"] = "failed"
                job["error"] = "no successful step"
        self.store.save(job)

    def _write_tree(self, job, job_dir, files_dir, sources, fonts, fonts_by_id, steps):
        """A local job's output: `svf/<dest>/` and `build-<id>/` written into the output folder (no zip).

        The job's `owned` record (path -> sha256) is filled as each file lands, so a failure half-way still leaves the
        landed files owned. A clash with a file the job no longer owns, or a gone output folder, fails the job."""

        def effective(font_id):
            if font_id not in fonts_by_id:
                return {}
            return settings.effective(fonts, job.get("settings") or {}, font_id)

        output_dir = job["output_dir"]
        landed = []

        written_at = {}                                         # output path -> the steps that wrote that face

        def on_landed(rel, digest):
            job.setdefault("owned", {})[rel] = digest
            landed.append(rel)
            for step in written_at.get(rel, ()):
                step["written"] = rel                           # only a face that really landed is "written"
            self.store.save(job)

        try:
            index = naming.RepoIndex(os.path.join(output_dir, "svf"))
            entries, sidecar, result, faces = zipout.collect(
                job, job_dir, files_dir, index, fonts_by_id, effective, self.repo_dir, sources,
                own_earlier(job), self.tools_dir)
            for face in faces:                                  # where each done face goes once it lands
                if face["identical_to"] is None:
                    written_at.setdefault("svf/" + face["row_path"], []).append(face["step"])
            zipout.write_tree(job, entries, sidecar, output_dir, job["output_id"], job.setdefault("owned", {}),
                              on_landed)
        except zipout.NameClash as exc:
            job["state"] = "failed"
            job["error"] = "name clash: %s" % exc.path
        except (OutputGone, zipout.NoteRefused, zipout.TreeRefused) as exc:        # messages the maker wrote itself
            job["state"] = "failed"
            job["error"] = str(exc)
        except (ValueError, OSError) as exc:                                       # anything else: the type, no message
            job["state"] = "failed"
            job["error"] = exc_text(exc, True)
        else:
            kept = ["svf/" + item["identical_to"] for item in result["skipped"]] + [
                "svf/" + rel for rel in result.pop("kept_texts", ())]
            kept = [rel for rel in kept if rel in job.get("owned", {})]
            result["files"] = landed + [rel for rel in kept if rel not in landed]
            result["output_dir"] = output_dir
            job["result"] = result
            if any(step.get("state") == "done" and step.get("kind") in ("precomposed", "jamo") for step in steps):
                job["state"] = "done"
            else:
                job["state"] = "failed"
                job["error"] = "no successful step"
        if job.get("state") == "failed" and job.get("result") is None:
            job["result"] = {"files": list(landed), "written": [], "skipped": [], "failed_steps": [],
                             "output_dir": output_dir}
        self.store.save(job)

    def _fail_step(self, job, job_dir, step, error):
        """Fail one step the worker never ran (a cancel, the job timeout, or a failed prepare); log and save it."""
        step["state"] = "failed"
        step["error"] = error
        zipout.append_log(job_dir, zipout.log_step(step, "", ""))
        self.store.save(job)

    def _fail_steps(self, job, job_dir, steps, error):
        """Fail every step in @p steps with @p error; a step already failed keeps its own error."""
        for step in steps:
            if step.get("state") != "failed":
                self._fail_step(job, job_dir, step, error)
