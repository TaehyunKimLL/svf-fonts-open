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
import copy
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

import detect
import naming
import preview
import quality
import routes
import settings
import toolreg
import toolrun
import zipout
from sources import OutputGone, Sources, stat_id

STAT_TIMEOUT_S = 5.0          # a stat of a recorded output folder that takes longer counts as unreachable (hung mount)
PREVIEW_TRY_S = 0.5            # how long a sweep waits for a job's preview locks while holding the lifecycle lock
REMOVE_BOUND_S = 30.0          # one removal of a files directory is waited for this long (a dead mount)
RETRY_DEADLINE_S = 30.0       # one pending-sweep pass ends after this long; unfinished entries are kept
IN_USE_STATES = ("queued", "running", "uploading", "detected")   # a job in these states uses its files directory
STOP_SWEEP_TOTAL_S = 8.0      # shutdown: all the sweeps together
STOP_STAT_TIMEOUT_S = 1.0     # the same at stop, so shutdown is not held by a mount
PENDING_FLOOR_S = 0.5         # a pending record is waited for at least this long (a healthy disk lands it in ms)
PENDING_IDLE_S = 2.0          # the pending writer thread exits after this long without work


class Deadline:
    """One absolute monotonic deadline, handed down through every wait of a pass (lock acquisitions, filesystem checks,
    the per-job loop) so that a pass takes at most the seconds it was given in all, never per step."""

    def __init__(self, seconds):
        self.end = time.monotonic() + seconds

    def remaining(self):
        return max(0.0, self.end - time.monotonic())

    def expired(self):
        return time.monotonic() >= self.end

    def capped(self, seconds):
        """A new `Deadline` ending at the earlier of this one and @p seconds from now."""
        other = Deadline(seconds)
        other.end = min(self.end, other.end)
        return other


def tombstone_of(files):
    """A name no later generation of @p files can have: `<files>.trash-<8 hex>`, in the same parent."""
    return "%s.trash-%s" % (files, secrets.token_hex(4))


def _run_bounded(fn, timeout):
    """Run @p fn in a daemon thread and wait @p timeout seconds: True when it returned, False when it is still running
    (it is left behind), the exception it raised otherwise re-raised."""
    box = []

    def run():
        try:
            fn()
            box.append(None)
        except BaseException as exc:
            box.append(exc)
    thread = threading.Thread(target=run, daemon=True, name="svf-maker-bounded")
    thread.start()
    thread.join(timeout)
    if not box:
        return False
    if box[0] is not None:
        raise box[0]
    return True


def remove_tree_bounded(path, timeout):
    """`shutil.rmtree(path)` waited for @p timeout seconds: True when it finished, False when it is still running (left
    behind; it can only ever touch @p path, a tombstone nobody else uses)."""
    return _run_bounded(lambda: shutil.rmtree(path), timeout)


class CallPending(OSError):
    """A bounded filesystem call did not return in time, or one with the same key is still running (an `OSError`, so
    every existing `except OSError` keeps working)."""


MUTATING_OPS = ("rename", "mkdir", "chmod")    # calls that change the volume: never run twice, and they fence their path
_CALLS_IN_FLIGHT = {}         # key -> (Event done, list box, {'abandoned'}): one daemon thread per key, however often asked
_CALLS_LOCK = threading.Lock()


def bounded_call(key, fn, timeout):
    """`fn()`, but `CallPending` (an `OSError`) when it does not return within @p timeout seconds (it runs in a daemon
    thread that is left behind). @p key is `(op, path)`. While a call with the same key is still running (a hung mount)
    no second thread starts: a read-only call (@p op not in `MUTATING_OPS`) waits for the first one within its own
    timeout and returns or raises the first call's result, unless a waiter already gave up on that call (then it raises
    at once, so N callers on one hung path do not cost N timeouts); a mutating call raises at once (never runs twice)."""
    with _CALLS_LOCK:
        running = _CALLS_IN_FLIGHT.get(key)
        if running is None:
            done, box, state = threading.Event(), [], {"abandoned": False}
            _CALLS_IN_FLIGHT[key] = (done, box, state)
        elif key[0] in MUTATING_OPS or running[2]["abandoned"]:
            raise CallPending("call still pending: %s" % (key,))      # never twice / a waiter already gave up on it
    if running is not None:
        done, box, state = running
        if not done.wait(timeout):
            with _CALLS_LOCK:
                state["abandoned"] = True
            raise CallPending("call still pending: %s" % (key,))
    else:
        def run():
            try:
                box.append(("ok", fn()))
            except BaseException as exc:
                box.append(("err", exc))
            finally:
                with _CALLS_LOCK:
                    _CALLS_IN_FLIGHT.pop(key, None)
                done.set()
        try:
            threading.Thread(target=run, daemon=True, name="svf-maker-stat").start()
        except BaseException:
            with _CALLS_LOCK:
                _CALLS_IN_FLIGHT.pop(key, None)
            box.append(("err", CallPending("call could not start: %s" % (key,))))
            done.set()
            raise
        if not done.wait(timeout):
            with _CALLS_LOCK:
                state["abandoned"] = True
            raise CallPending("call timed out: %s" % (key,))
    kind, value = box[0]
    if kind == "err":
        raise value
    return value


def _mutations_under(path):
    """The ops of the mutating calls in flight whose key path is @p path or below it."""
    prefix = path.rstrip(os.sep) + os.sep
    with _CALLS_LOCK:
        return [key[0] for key in _CALLS_IN_FLIGHT
                if key[0] in MUTATING_OPS and (key[1] == path or key[1].startswith(prefix))]


def mutation_pending(path):
    """True while a mutating call (`MUTATING_OPS`) on @p path or below it is still in flight."""
    return bool(_mutations_under(path))


def mutation_kind(path):
    """The op of such a call (`"rename"` wins over the others), or None."""
    ops = _mutations_under(path)
    if not ops:
        return None
    return "rename" if "rename" in ops else ops[0]


def rename_bounded(src, dst, timeout):
    """`os.rename(src, dst)` within @p timeout seconds. `CallPending` when it did not return: the rename is then still
    in flight and fences @p src (`mutation_pending`)."""
    bounded_call(("rename", src), lambda: os.rename(src, dst), timeout)


def stat_id_bounded(path, timeout=STAT_TIMEOUT_S):
    """`stat_id(path)` within @p timeout seconds (`CallPending`, an `OSError`, otherwise)."""
    return bounded_call(("stat", path), lambda: stat_id(path), timeout)


def fs_bounded(op, path, timeout):
    """`os.path.<op>(path)` (lexists, islink, isdir) within @p timeout seconds (`OSError` otherwise)."""
    return bounded_call((op, path), lambda: getattr(os.path, op)(path), timeout)



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
ENV = toolrun.base_env(os.environ)

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


def _refuse_constant(name):
    """`json.load`'s hook for NaN / Infinity: the page's JSON.parse rejects them, so a scorer's output may not hold one."""
    raise ValueError("non-finite number %s" % name)


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
    toolreg.register(proc)                          # a no-op unless a server activated a registry
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
        toolreg.unregister(proc)
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
        # The lifecycle lock. LOCK ORDER (always in this order, never the other way): lifecycle lock -> a job's own lock
        # (`lock(id)`) -> the job's preview locks (`on_sweep`) -> the pending-sweeps lock. It is held for every local state
        # change into an active state (create, reuse, PUT sources and detect on a finished job, run), including reading
        # the state the decision uses, and for the "state check + rename to a tombstone" step of every sweep. It is never
        # held across a removal, a scan or a tool run, and nothing here re-enters it.
        self.lifecycle = threading.Lock()
        self._pending_lock = threading.Lock()
        self._retry_lock = threading.Lock()
        # The pending writer: every operation on pending-sweeps.json runs on one daemon thread (see `_pending_op`).
        self._pending_q = queue.Queue()
        self._pending_thread = None
        self._pending_thread_lock = threading.Lock()
        self._pending_unfinished = 0                  # test support: lets a test wait until the writer is idle
        self._pending_stalled = False

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

    def ensure_files_dir(self, job, locked=False, persist=True):
        """Make a local job's files directory (`work/tmp` inside, all 0700) and return it.

        The output folder must still be the folder picked at create time (`output_id`), else `OutputGone`: nothing is
        made in a replaced folder. Only the levels made here are chmod'ed, never the output folder itself.

        The directory is made under the lifecycle lock (@p locked: the caller holds it), so a sweep's rename and this
        creation never interleave, and the new generation's identity is saved to `job.json` (@p persist; False where the
        caller saves the job itself) so a pending entry always names the generation it sweeps.
        """
        if job.get("source") != "local":
            return self.files_dir(job)
        with (contextlib.nullcontext() if locked else self.lifecycle):
            try:
                self.load(job["id"])                          # a deleted job (or one being deleted: delete holds this
            except KeyError:                                  # lock) never gets a directory made for it
                raise OutputGone("job %s no longer exists" % job["id"])
            before = job.get("files_id")
            files = self._make_files_dir(job)
            if persist and job.get("files_id") != before:
                gen = job["files_id"]
                try:
                    self.update(job["id"], lambda j: j.update(files_id=gen))
                except KeyError:
                    pass
            return files

    def _make_files_dir(self, job):
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

    def delete(self, job_id, locked=False):
        """Remove the job's directory; `ValueError` for a `queued` or `running` job (the worker owns it).

        The state check and the removal hold the job's own lock (W1): a `POST /run` that turns an `uploading` job
        `queued` in the same instant is either seen by the check or waits for the removal, never lost between them.
        A local job's files directory is renamed away under the lifecycle lock (with the state check) and removed after
        every lock is released. With @p locked the caller already holds the lifecycle lock and gets the finishing step
        back as a callable to run once it has released it; otherwise it is run here.
        `on_delete` is called once the directory is gone (the caller's per-job bookkeeping).
        """
        finish = None
        with (contextlib.nullcontext() if locked else self.lifecycle):
            lock = self.lock(job_id)
            with lock:
                job = self.load(job_id)
                if job.get("state") in ("queued", "running"):
                    raise ValueError("job %s is %s" % (job_id, job.get("state")))
                if job.get("source") == "local":
                    step = self._rename_away(job, None, check_active=False)     # a failure is kept as pending
                    finish = lambda: self._finish_sweep(job, step, None)
                shutil.rmtree(self.path(job_id))
            with self._locks_guard:
                if self._locks.get(job_id) is lock:         # never drop a lock a later caller already made
                    self._locks.pop(job_id, None)
            if self.on_delete is not None:
                self.on_delete(job_id)
        if locked:
            return finish or (lambda: True)
        if finish is not None:
            finish()


    # ---- the sweeps of a local job's files directory (`<output_dir>/.svf-maker-<id>/`) --------------------------

    def _pending_path(self):
        return os.path.join(self.data_root, "pending-sweeps.json")

    def _read_pending(self):
        try:
            with open(self._pending_path(), encoding="utf-8") as f:
                data = json.load(f)
        except OSError:
            return []                                     # no file (or unreadable): nothing recorded
        except ValueError as exc:
            self._set_bad_aside(type(exc).__name__)       # corrupt: keep it for a person, never overwrite it
            return []
        if not isinstance(data, list):
            self._set_bad_aside("NotAList")
            return []
        return [e for e in data if isinstance(e, dict)]

    def _set_bad_aside(self, kind):
        bad = "%s.bad-%d" % (self._pending_path(), int(time.time()))
        try:
            os.replace(self._pending_path(), bad)
            print("sweep: pending-sweeps.json is unreadable (%s); kept as %s" % (kind, os.path.basename(bad)),
                  file=sys.stderr)
        except OSError:
            pass

    def _write_pending(self, entries):
        os.makedirs(self.data_root, exist_ok=True)
        tmp = self._pending_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._pending_path())
        try:
            fd = os.open(self.data_root, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass

    def _pending_run(self):
        """The pending writer thread: serves `_pending_q` in order, exits when idle (see `_pending_op`)."""
        while True:
            try:
                req = self._pending_q.get(timeout=PENDING_IDLE_S)
            except queue.Empty:
                with self._pending_thread_lock:
                    if self._pending_q.empty():
                        self._pending_thread = None
                        return
                continue
            fn, event, box, state, after = req
            try:
                with self._pending_lock:
                    entries = self._read_pending()
                    before = copy.deepcopy(entries)
                    new, result = fn(entries)
                    if new is not None and new != before:
                        self._write_pending(new)
                if after is not None:
                    after(result)                         # e.g. the log.md lines: written even if nobody waits any more
                box.append(("ok", result))
            except BaseException as exc:
                box.append(("err", exc))
            with self._pending_thread_lock:
                self._pending_unfinished -= 1
                self._pending_stalled = False
                abandoned = state["abandoned"]
                event.set()
            if abandoned and box[0][0] == "err":
                try:
                    raise box[0][1]
                except BaseException:
                    print_exc()

    def _pending_op(self, fn, deadline=None, always_floor=False, after=None):
        """Run @p fn(entries) -> (new entries or None, result) on the one pending writer thread, as a read-modify-write
        of pending-sweeps.json under `_pending_lock`. Waits until @p deadline (default `Deadline(STAT_TIMEOUT_S)`) but at
        least `PENDING_FLOOR_S`, and returns `(True, result)`, or `(False, None)` when it is not done by then; an
        operation not waited for still runs later, in order. The floor is not waited while the writer is stalled (a
        caller already gave up on an unfinished operation; cleared when the writer completes one) unless @p always_floor.
        An exception of @p fn is re-raised to a caller that waited (printed otherwise). @p after(result), when given,
        runs on the writer thread once the write is done, whether or not the caller still waits."""
        dl = deadline if deadline is not None else Deadline(STAT_TIMEOUT_S)
        event, box, state = threading.Event(), [], {"abandoned": False}
        with self._pending_thread_lock:
            floor = always_floor or not self._pending_stalled
            if self._pending_thread is None:
                thread = threading.Thread(target=self._pending_run, daemon=True, name="svf-maker-pending")
                thread.start()                            # a failed start leaves nothing queued and no thread recorded
                self._pending_thread = thread
            self._pending_unfinished += 1
            self._pending_q.put((fn, event, box, state, after))
        wait = max(dl.remaining(), PENDING_FLOOR_S) if floor else dl.remaining()
        if not event.wait(wait):
            with self._pending_thread_lock:
                if not event.is_set():
                    state["abandoned"] = True
                    self._pending_stalled = True
                    return False, None
        kind, value = box[0]
        if kind == "err":
            raise value
        return True, value

    def flush_pending(self, deadline=None):
        """True when every pending operation submitted so far has run (waits at least `PENDING_FLOOR_S`, always)."""
        return self._pending_op(lambda entries: (None, None), deadline, always_floor=True)[0]

    @staticmethod
    def _merge_pending(entries, entry):
        """Add @p entry to @p entries, or merge it into the entry with the same path; True when it was new. A `making`
        entry (a generation of unknown identity is being made there) sets the recorded `files_id` to None; otherwise a
        None `files_id` never overwrites a recorded one, and a different non-None one replaces it (a newer generation)."""
        same = [e for e in entries if e.get("path") == entry["path"]]
        if not same:
            entries.append(entry)
            return True
        old = same[0]
        if entry.get("making"):
            old.update(entry)
        elif entry["files_id"] is not None and entry["files_id"] != old.get("files_id"):
            old.update(entry)
            old.pop("making", None)
        if entry.get("from") and not old.get("from"):
            old["from"] = entry["from"]
        return False

    def _add_pending_many(self, entries, deadline=None):
        """Record @p entries (dicts with `path`, `output_dir`, `output_id`, `job`, `files_id`, `reason`, optionally `from`
        and `making`) in ONE pending operation; True when it was written in time. The `log.md` line of each new one is
        written by the writer thread when the operation is done (also when the caller stopped waiting)."""
        entries = [dict(e) for e in entries]
        reasons = [(e["job"], e["path"], e.pop("reason", "")) for e in entries]

        def merge(current):
            return current, [self._merge_pending(current, dict(e)) for e in entries]

        def log(fresh):
            for new, (job_id, path, reason) in zip(fresh, reasons):
                if not new:
                    continue                              # logged when first recorded: once per directory, not per sweep
                try:
                    zipout.append_log(self.path(job_id), "\nsweep: %s: %s; intermediate files may remain there\n"
                                      % (path, reason))
                except (OSError, KeyError):
                    pass                                  # the metadata directory is already gone
        return self._pending_op(merge, deadline, after=log)[0]

    def _add_pending(self, job, files, reason, trash=None, generation=None, deadline=None, origin=None, making=False):
        """Record @p files (or, when its removal was started and not finished, the tombstone @p trash it was renamed to)
        as still to be removed; True when written in time. @p origin is stored as `from` (the directory a tombstone was
        renamed from); @p making: a generation of unknown identity is being made at @p files (its `files_id` is cleared)."""
        entry = {"path": trash or files, "output_dir": job.get("output_dir"), "output_id": job.get("output_id"),
                 "job": job["id"], "files_id": None if trash or making else (generation or job.get("files_id")),
                 "reason": reason}
        if origin:
            entry["from"] = origin
        if making:
            entry["making"] = True
        return self._add_pending_many([entry], deadline)

    def _rename_away(self, job, deadline, check_active=True, own_run=False, stat_timeout=None):
        """The step of a sweep that needs the lifecycle lock (the caller holds it): look at the job's state as it is now,
        then rename its files directory to a unique tombstone. Returns `(status, trash, reason, generation, files)`:
        status `gone` (nothing there), `skipped` (the job is in use), `renamed` (@p trash is to be removed outside the
        locks) or `failed` (@p reason; to be recorded as pending). @p generation is the identity of the directory
        actually renamed. Every filesystem check on the output folder is bounded by @p deadline (a `Deadline`) or, without
        one, by `STAT_TIMEOUT_S`; the preview locks are taken in the order the server defines, within the same deadline."""
        files = self.files_dir(job)
        left = (lambda: STAT_TIMEOUT_S) if deadline is None else (lambda: min(STAT_TIMEOUT_S, deadline.remaining()))
        if stat_timeout is not None:
            base = left
            left = lambda: min(base(), stat_timeout)
        try:
            fresh = self.load(job["id"])
        except KeyError:
            fresh = job
        if check_active and not own_run and fresh.get("state") in ("queued", "running"):
            return ("skipped", None, None, None, files)
        try:
            if self.on_sweep is None:
                hold = contextlib.nullcontext()
            else:
                # a try-lock: a bake holding the preview lock is not waited for under the lifecycle lock; the sweep is
                # recorded as pending (busy) and retried later
                hold = self.on_sweep(job, PREVIEW_TRY_S if deadline is None else min(PREVIEW_TRY_S, deadline.remaining()))
            with hold:
                try:
                    same = stat_id_bounded(job["output_dir"], left()) == tuple(job.get("output_id") or ())
                except OSError:
                    same = False                                  # unmounted, removed: nothing can be said about the path
                if not same:
                    return ("failed", None, "output folder is gone or changed", None, files)
                if not fs_bounded("lexists", files, left()):
                    return ("gone", None, None, None, files)
                try:
                    if fs_bounded("islink", files, left()) or not fs_bounded("isdir", files, left()):
                        raise OSError("not a real directory")
                    generation = list(stat_id_bounded(files, left()))
                    trash = tombstone_of(files)
                    os.rename(files, trash)                       # under the locks: the name is free for a later generation
                    return ("renamed", trash, None, generation, files)
                except Exception as exc:
                    return ("failed", None, exc_text(exc, True) if type(exc) is not OutputGone else str(exc), None, files)
        except TimeoutError:
            return ("failed", None, "busy (a preview holds it)", None, files)
        except Exception:
            print_exc()
            return ("failed", None, "sweep failed", None, files)

    def _finish_sweep(self, job, step, deadline):
        """After the lifecycle lock is released: remove the tombstone (bounded), or record what is left as pending.
        True when the directory is gone."""
        status, trash, reason, generation, files = step
        if status in ("gone",):
            return True
        if status == "skipped":
            return False
        try:
            if status == "renamed":
                bound = REMOVE_BOUND_S if deadline is None else min(REMOVE_BOUND_S, deadline.remaining())
                if remove_tree_bounded(trash, bound):
                    return True
                reason = "removal did not finish in time"
        except FileNotFoundError:
            return True                                           # already removed by a bounded removal that finished
        except Exception as exc:
            reason = exc_text(exc, True)
        try:
            self._add_pending(job, files, reason, trash, generation)       # outside every lock but the pending one
        except Exception:
            print_exc()
        return False

    def sweep_files(self, job, stat_timeout=None, bound=None, deadline=None, own_run=False):
        """Remove a local job's files directory; True when it is gone. Never raises.

        Under the lifecycle lock, from the job's state as it is now: a job that is queued or running is left alone (the
        worker's own end-of-run sweep passes @p own_run); the directory is renamed to a tombstone, the lock is released,
        and the tombstone is removed outside every lock. A failure (busy, changed folder, removal not finished) is
        recorded in `pending-sweeps.json` with the folder's identity and the generation actually swept, and logged to
        `log.md`; `retry_pending_sweeps` takes it up later.

        With @p bound (seconds) or a @p deadline (a `Deadline`) every wait of the call - the lifecycle lock, the preview
        locks, the filesystem checks, the removal - counts against that one deadline."""
        if job.get("source") != "local":
            return True
        if deadline is None and bound is not None:
            deadline = Deadline(bound)
        try:
            if deadline is None:
                self.lifecycle.acquire()
            elif not self.lifecycle.acquire(timeout=deadline.remaining()):
                step = ("failed", None, "busy (lifecycle)", None, self.files_dir(job))
                return self._finish_sweep(job, step, deadline)
            try:
                step = self._rename_away(job, deadline, own_run=own_run, stat_timeout=stat_timeout)
            finally:
                self.lifecycle.release()
        except Exception:
            print_exc()
            return False
        return self._finish_sweep(job, step, deadline)

    def sweep_orphans(self, deadline=None):
        """Remove every `.svf-maker-<id>` directory beside a known output folder (one a local job or a pending entry
        records, same device and inode) whose job no longer exists in the store: nothing tracks it. Start-up and stop. The
        rename to a tombstone is under the lifecycle lock; the removal is outside it. A folder shared with another
        running maker would lose that maker's live directories: one maker per output folder is the rule."""
        dl = deadline or Deadline(STOP_SWEEP_TOTAL_S)
        folders = {}
        try:
            for item in self.list():
                if item.get("source") == "local":
                    job = self.load(item["id"])
                    folders[job.get("output_dir")] = tuple(job.get("output_id") or ())
        except KeyError:
            pass
        with self._pending_lock:
            for entry in self._read_pending():
                try:
                    folders.setdefault(entry["output_dir"], tuple(entry["output_id"]))
                except (KeyError, TypeError):
                    continue
        trash = []
        if not self.lifecycle.acquire(timeout=dl.remaining()):
            return
        try:
            for out, oid in folders.items():
                if dl.expired():
                    break
                try:
                    if stat_id_bounded(out, min(STAT_TIMEOUT_S, dl.remaining())) != oid:
                        continue
                    names = bounded_call(("listdir", out), lambda: os.listdir(out), min(STAT_TIMEOUT_S, dl.remaining()))
                except (OSError, TypeError):
                    continue
                for name in names:
                    if not re.match(r"^\.svf-maker-[0-9a-f]{12}$", name) or os.path.exists(self.path(name[len(FILES_DIR_PREFIX):], "job.json")):
                        continue
                    path = os.path.join(out, name)
                    try:
                        if os.path.islink(path) or not os.path.isdir(path):
                            continue
                        tomb = tombstone_of(path)
                        os.rename(path, tomb)
                        trash.append(tomb)
                    except OSError:
                        continue
        finally:
            self.lifecycle.release()
        for tomb in trash:
            if dl.expired() or not remove_tree_bounded(tomb, min(REMOVE_BOUND_S, dl.remaining())):
                break

    def sweep_trash(self, job):
        """Remove the leftover tombstones (`.svf-maker-<id>.trash-*`) of a local job beside its output folder's
        identity (start-up only). Each removal is bounded; nothing else in the folder is touched."""
        if job.get("source") != "local":
            return
        out, prefix = job.get("output_dir"), FILES_DIR_PREFIX + job["id"] + ".trash-"
        try:
            if stat_id_bounded(out) != tuple(job.get("output_id") or ()):
                return
            names = os.listdir(out)
        except (OSError, TypeError):
            return
        for name in names:
            path = os.path.join(out, name)
            if (re.match(r"^\.svf-maker-[0-9a-f]{12}\.trash-[0-9a-f]{8}$", name) and name.startswith(prefix)
                    and not os.path.islink(path) and os.path.isdir(path)):
                remove_tree_bounded(path, REMOVE_BOUND_S)

    def retry_pending_sweeps(self, stat_timeout=None, deadline_s=None):
        """Retry each pending sweep; it removes only a real `.svf-maker-<job id>` directory directly inside the output
        folder it was recorded for, when that folder is still the same one and the directory is still the generation
        that was recorded (`files_id`).

        An entry is dropped when the directory is gone, was replaced by a newer generation, or the removal finished. It
        is KEPT, untouched, when the folder cannot be reached or another folder is mounted there (the original may come
        back), when its job is queued, running, uploading or detected (the directory is in use), when a lock or the
        removal does not finish, and when the overall deadline @p deadline_s (`RETRY_DEADLINE_S`) has passed.

        The state check and the rename to a tombstone happen together under the lifecycle lock, so a job cannot become
        active between them; the tombstone is removed after every lock is released. Every wait counts against one
        `Deadline`. Callers: the idle sweeper (and the start-up cleanup). One retry runs at a time; a second returns."""
        if not self._retry_lock.acquire(blocking=False):
            return
        try:
            with self._pending_lock:
                entries = self._read_pending()
            if not entries:
                return                                            # nothing to retry: no file is written
            dl = Deadline(RETRY_DEADLINE_S if deadline_s is None else deadline_s)
            dropped = []
            tombs = []
            new_tombs = []
            for entry in entries:
                if dl.expired():
                    break                                         # out of time: the rest stays for the next pass
                left = lambda: max(0.05, min(STAT_TIMEOUT_S if stat_timeout is None else stat_timeout, dl.remaining()))
                try:
                    path, job_id = entry["path"], entry["job"]
                    out, oid = entry["output_dir"], tuple(entry["output_id"])
                    name = ".svf-maker-" + job_id
                    base = os.path.basename(path)
                    try:
                        mounted = stat_id_bounded(out, left()) == oid
                    except OSError:
                        continue                                  # the folder cannot be reached (unmounted): keep it
                    if not mounted:
                        continue                                  # another folder is mounted there: wait for the original
                    if not fs_bounded("lexists", path, left()):
                        dropped.append((path, entry.get("files_id")))             # confirmed gone
                        continue
                    if os.path.dirname(path) != out or not re.match(r"^\.svf-maker-[0-9a-f]{12}(\.trash-[0-9a-f]{8})?$", base) \
                            or not (base == name or base.startswith(name + ".trash-")) \
                            or fs_bounded("islink", path, left()) or not fs_bounded("isdir", path, left()):
                        print("sweep: %s: not the directory this job made; left alone" % path, file=sys.stderr)
                        dropped.append((path, entry.get("files_id")))
                        continue
                    if base != name:                              # a tombstone: dead by name, no state to look at
                        tombs.append((path, entry.get("files_id")))
                        continue
                    recorded = entry.get("files_id")
                    if not self.lifecycle.acquire(timeout=dl.remaining()):
                        break                                     # the lifecycle lock is busy: the rest waits
                    try:
                        if recorded is not None and list(stat_id_bounded(path, left())) != list(recorded):
                            dropped.append((path, recorded))      # a newer generation of the directory: not this entry's
                            continue
                        try:
                            job = self.load(job_id)
                        except KeyError:
                            job = {"id": job_id, "source": "local", "fonts": [], "output_dir": out, "output_id": list(oid)}
                        if job.get("state") in IN_USE_STATES:
                            continue                              # a rerun or an open job uses it: keep the entry
                        step = self._rename_away(job, dl, check_active=False, stat_timeout=stat_timeout)
                    finally:
                        self.lifecycle.release()
                    status, trash = step[0], step[1]
                    if status == "gone":
                        dropped.append((path, recorded))
                    elif status == "renamed":
                        dropped.append((path, recorded))
                        new_tombs.append({"path": trash, "output_dir": out, "output_id": list(oid), "job": job_id,
                                          "files_id": None})
                except TimeoutError:
                    continue                                      # a preview lock is held: kept
                except Exception as exc:
                    print("sweep: %s: %s" % (entry.get("path"), type(exc).__name__), file=sys.stderr)
            # The replacement of each renamed directory by its tombstone is saved BEFORE anything is removed: a removal
            # that raises or is cut short can then never leave a directory that no entry names.
            with self._pending_lock:
                current = self._read_pending()
                kept = [e for e in current if (e.get("path"), e.get("files_id")) not in dropped]
                known = {e.get("path") for e in kept}
                kept += [t for t in new_tombs if t["path"] not in known]
                if kept != current:
                    self._write_pending(kept)
            removed = []
            for trash in [t for t, _g in tombs] + [t["path"] for t in new_tombs]:
                if dl.expired():
                    break
                try:                                              # each removal on its own: one failure stops no other
                    if remove_tree_bounded(trash, min(REMOVE_BOUND_S, dl.remaining())):
                        removed.append(trash)
                except FileNotFoundError:
                    removed.append(trash)                         # already removed (a bounded removal finished first)
                except Exception as exc:
                    print("sweep: %s: %s" % (trash, type(exc).__name__), file=sys.stderr)    # kept: type only
            if removed:
                with self._pending_lock:
                    current = self._read_pending()
                    kept = [e for e in current if e.get("path") not in removed]
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
        self._stopped = False                   # a `stop` completed: later calls return its result at once
        self._stop_result = True
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

    def owns(self, job_id):
        """True while the worker still holds @p job_id: it is queued, or its run (including the completion cleanup that
        follows the terminal state) has not been released yet. A job it owns cannot be activated again."""
        with self._lock:
            return job_id in self._queued or self._current == job_id

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
        running. A second call after a completed stop returns the first result without a second sweep."""
        with self._lock:
            if self._stopped:
                return self._stop_result
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
        self._stop_result, self._stopped = idle, True
        return idle

    def sweep_local_files(self):
        """Sweep the files directory of every local job at stop, with no pending retry. One `Deadline`
        (`STOP_SWEEP_TOTAL_S`) bounds every wait of every job together - the lifecycle lock, the preview locks, the
        filesystem checks, the removals; a sweep that does not finish is recorded as pending and left, and the next start
        cleans up what remains."""
        deadline = Deadline(STOP_SWEEP_TOTAL_S)
        for item in self.store.list():
            if item.get("source") == "local":
                if deadline.expired():
                    break
                try:
                    self.store.sweep_files(self.store.load(item["id"]), STOP_STAT_TIMEOUT_S, deadline=deadline)
                except KeyError:
                    continue
        self.store.sweep_orphans(deadline)

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
                if not self.store.sweep_files(self.store.load(job_id), own_run=True):
                    self.store.update(job_id, lambda j: j.update(
                        notice="intermediate files remain in %s inside the output folder (moved, removed or busy); "
                               "they are swept when the folder is back" % (FILES_DIR_PREFIX + job_id)))
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
                self.store.ensure_files_dir(job, persist=False)
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
        zipout.append_log(job_dir, zipout.log_step(step, tool_text(stdout, local), tool_text(stderr, local), self.repo_dir))
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
        try:
            os.remove(os.path.join(cwd, routes.MKFONT_TMP))      # build_faces.py removes it too: no second copy of the face
        except OSError:
            pass
        if not os.path.exists(out_abs):
            return "".join(stdout), "".join(stderr), "no output"
        return "".join(stdout), "".join(stderr), None

    @staticmethod
    def _clear_outputs(cwd, out_abs, step):
        """Remove what an earlier run left where this step writes: a tool that exits 0 without writing must fail "no
        output", not pass on the old file (a re-detected job reuses `work/sNN/`)."""
        stale = [out_abs, os.path.join(cwd, "report.json"),      # a failed re-run must not show the last run's report
                 os.path.join(cwd, "identity.json")]            # nor serve the last build's piece scores
        stale += [os.path.join(cwd, name) for name in (routes.MKFONT_TMP,) + routes.MAC_BDFS]   # a route's temp files
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
        prefix = toolrun.recog_argv(self.caps, self.repo_dir)
        recog = self.caps.get("recog_dir")
        if prefix is None or not recog:
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
        argv = prefix + [
            os.path.join(files_dir, step.get("output") or ""), "-o", out_json, "--threads", "2",
            "--arrays", RECOG_ARRAYS]
        try:
            result = run_command(argv, work, RECOG_TIMEOUT, cancel, dict(env or ENV, SVF_RECOG_DIR=recog))
        except OSError:                                 # the interpreter vanished since start-up: scoring is optional
            return {"available": False, "error": "the recogniser interpreter could not be started"}
        if result["error"] is not None or result["exit"] != 0:
            tail = (result["stderr"] or "").strip().splitlines()
            reason = "timed out" if result["error"] == "timeout" else (
                result["error"] or (tail[-1] if tail and not local else "exit %s" % result["exit"]))
            return {"available": False, "error": reason}
        try:
            with open(out_json, encoding="utf-8") as f:
                data = json.load(f, parse_constant=_refuse_constant)
            if not isinstance(data, dict) or not isinstance(data.get("face") or {}, dict):
                raise ValueError("not an identity object")
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
        zipout.append_log(job_dir, zipout.log_step(step, "", "", self.repo_dir))
        self.store.save(job)

    def _fail_steps(self, job, job_dir, steps, error):
        """Fail every step in @p steps with @p error; a step already failed keeps its own error."""
        for step in steps:
            if step.get("state") != "failed":
                self._fail_step(job, job_dir, step, error)
