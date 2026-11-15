# Maker local mode: bounded lifecycle (start-up, stop, activation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** No filesystem call on an output or input volume can hold the maker's start-up, its stop, or the store-wide
lifecycle lock for longer than a stated bound, and an abandoned call can never act on a later generation of a files
directory. Card t_d1aba4b8.

**Closing measurement (card, verbatim):** "start-up sweep_trash, os.rename under locks, pending-lock waits and
pending-file fsync all take the shared absolute Deadline and never hang start-up/stop on a hung mount; ensure_files_dir
and POST run's pre-queue reads (input stats, licence hashing, planning, range copies) happen outside the lifecycle lock
or are bounded, with tests on a hung volume while a job in a healthy folder is created; maker suite green".

**Architecture:** Three changes, in this order. (1) Two new primitives in `maker/jobs.py`: a bounded rename that leaves a
*fence* on its path while it is still running, and one daemon writer thread through which every read and write of
`pending-sweeps.json` goes, so a caller waits for it only until its `Deadline`. (2) Every sweep path (stop, start-up,
idle, delete) uses them with the caller's single `Deadline`; start-up `sweep_trash` becomes deadline-bound like the
others. (3) Every filesystem call under the lifecycle lock is bounded (`LOCKED_IO_S`), every job-lock wait under it is
bounded, and a local `POST run` does its reads and planning *outside* the lifecycle lock, between a short "prepare"
section and a short "commit" section that revalidates the job and the directory's identity.

**Tech Stack:** Python 3 stdlib, unittest, `unittest.mock`. No new dependency (`queue`, `threading` are already
imported by `jobs.py`).

**Origin:** SOL review of the maker local mode, findings H3 and M5
(`/home/thkim/work/scratch/review-lanes/maker-local-final-r4-sol/out.md`; its line numbers are of an older commit).
Known-limits text: `docs/maker-audit.md` section 8, "Known limits of the cleanup (follow-up card t_d1aba4b8)" and
"Accepted trade-off (lifecycle lock)". Lifecycle design: `docs/superpowers/specs/2026-11-04-maker-local-mode-design.md`
8.3 and the lock order at `Store.__init__` (`maker/jobs.py:448-456`).

All commands run from the worktree root `/home/thkim/work/svf-fonts-open-wt/fu-lifecycle` (branch `fu-lifecycle`, base
`004a449`). No push.

---

## 1. Current-code findings (at 004a449)

Line numbers are `maker/jobs.py` (J) and `maker/server.py` (S) at `004a449`.

### Already fixed (not in scope)

- **H1** (completion cleanup vs re-enqueue): `_activate` refuses a `done`/`failed` job the worker still owns
  (S:919-920 "the previous run is finishing"); `_finish_local` keeps ownership (commit 94011ff).
- **H2** (renamed directory left untracked when a removal raises): `retry_pending_sweeps` saves the
  original-to-tombstone replacement before any removal and handles each removal on its own (J:956-976).
- **M4** (preview check-then-act): `_preview_dir` makes and persists the directory under the lifecycle lock and the
  preview lock and keeps the preview lock for the bake (S:967-1001).
- Already bounded: the lifecycle-lock wait of `sweep_files`/`sweep_orphans`/`retry_pending_sweeps` when a deadline is
  given (J:797, J:830, J:930); the preview try-lock (J:730); the output-folder stat and the `lexists/islink/isdir`
  checks in `_rename_away` (J:733-743); `rmtree` of a tombstone (`remove_tree_bounded`, J:96); `sweep_orphans`'s stat and
  `listdir` (J:837-839).

### H3a still holds: start-up `sweep_trash` is outside the shared deadline

- S:541-563 `startup_cleanup` makes `Deadline(STARTUP_CLEANUP_S)` and passes it to `sweep_files` and `sweep_orphans`,
  but calls `store.sweep_trash(job)` (S:559) with no deadline.
- J:860-876 `sweep_trash`: `stat_id_bounded(out)` with the default `STAT_TIMEOUT_S` (J:867), **raw `os.listdir(out)`**
  (J:869), **raw `os.path.islink`/`os.path.isdir`** per entry (J:875), and **`REMOVE_BOUND_S` (30 s) per tombstone**
  (J:876). A hung `listdir` blocks `make_server` for ever; N hung tombstones cost N x 30 s.
- S:547 `retry_pending_sweeps(deadline_s=deadline.remaining())` builds a second `Deadline` from the remaining seconds
  (equivalent, but not the shared object; tidy-up only).

### H3b still holds: rename and pending persistence are not bounded

- J:745 `os.rename(files, trash)` is synchronous, under the lifecycle lock (held by the caller, J:795-803) **and** the
  job's preview locks (J:730-743). A mount that answers `stat` and hangs on `rename` holds start-up (via `sweep_files`,
  S:557), stop (`Worker.sweep_local_files`, J:1098-1112) and every request that wants the lifecycle lock.
- J:847 and J:850 (`sweep_orphans`): **raw `os.path.islink`/`isdir` and raw `os.rename`** under the lifecycle lock
  (not named by the review; same defect).
- J:623 `Store.delete` calls `_rename_away(job, None, ...)`: with no deadline every stat is `STAT_TIMEOUT_S` and the
  rename is unbounded, under the lifecycle lock (request path: DELETE, `retain`, `_claim_folder` takeover).
- Pending persistence: `_finish_sweep` (J:755-777) calls `_add_pending` (J:682) **after** the deadline may have
  expired; `_add_pending` waits on `_pending_lock` with no timeout (J:688) and writes + `fsync`s the file and its
  directory synchronously (`_write_pending`, J:665-680). `retry_pending_sweeps` (J:894, J:958, J:977) and
  `sweep_orphans` (J:823) also wait on `_pending_lock` without a bound.

### M5 still holds: the lifecycle lock is held across unbounded I/O

- J:473-498 `ensure_files_dir` runs under the lifecycle lock (J:485) and `_make_files_dir` (J:500-518) does **raw
  `stat_id(output_dir)`** (J:502), **raw `os.lstat` / `os.mkdir` / `os.chmod`** per level (J:510-513) and a raw
  `stat_id(files)` (J:517). Callers under the lock: `_job_create` (S:899), `_preview_dir` -> `_ensure_dir` (S:984-990,
  S:1013), `_files_dir_ready` for detect (S:1025, S:1131), `_check_local_run` (S:1487).
- Local `POST run`: `_job_run` (S:1443-1479) runs its whole `transition` through `_activate` (S:1473 -> S:916-923),
  i.e. under the lifecycle lock **and** the job lock: `_check_local_run` (S:1481-1507: `ensure_files_dir`, `check_path`
  of every root, `os.lstat` of every input in `_check_unchanged` S:1537-1547, `shutil.disk_usage` S:1503),
  `settings.run_ready` (S:1460; licence hashing `settings._licence_sha`, settings.py:1157-1166), `settings.plan_steps`
  (S:1465; `os.makedirs` into the files directory, range-list copy `shutil.copyfile` settings.py:1510),
  `_check_steps`/`_check_notes` (S:1468-1469; `Sources.abs_of` resolves real paths on the input volume).
- Not named by the review, same class: under the lifecycle lock the job lock is waited for **without a bound**
  (`Store.delete` J:618, `_activate` -> `store.update` S:923, `ensure_files_dir`'s persist J:495). A job-lock holder can
  itself wait on a preview lock (`_job_settings` S:1437) or on output-volume I/O (`_finish_local`'s `update(move)`,
  J:1240ff), so one hung volume can still stall the lifecycle lock through a job lock.

---

## 2. Design

### 2.1 Bounded rename with a fence (how an abandoned rename never touches a later generation)

`os.rename` acts on a *name*. A rename that is abandoned (still running when its wait ends) can complete later and move
whatever then sits at that name. The only way to make that safe is to keep anything new from appearing at the name
while the call is in flight.

- `bounded_call` (J:77) already runs one daemon thread per key and keeps the key in `_CALLS_IN_FLIGHT` until the call
  returns. New: `class CallPending(OSError)`, raised by `bounded_call` both on "timed out" and on "a call with this key
  is still pending" (a subclass, so every existing `except OSError` is unchanged).
- New `MUTATING_OPS = ("rename", "mkdir", "chmod")` and `mutation_pending(path) -> bool`: True while a bounded call
  whose op is in `MUTATING_OPS` and whose key path is @p path or below it is still in flight.
- New `rename_bounded(src, dst, timeout) -> None`: `bounded_call(("rename", src), lambda: os.rename(src, dst),
  timeout)`; `CallPending` when it did not return (the rename is then in flight and fences `src`).
- **The fence:** `ensure_files_dir` is the only creator of a files directory (previews, probes, detect, run all go
  through it). Under the lifecycle lock it raises `OutputGone("the files directory is still being moved or made on a
  slow or hung volume; try again later")` while `mutation_pending(files)`. `_rename_away` returns `failed`/"busy (a
  filesystem call is still pending)" when `mutation_pending(files)` before it starts. So while an abandoned rename of
  `<out>/.svf-maker-<id>` is in flight no new generation can be made at that name; when it lands it can only move the
  generation it was issued for.
- **Tracking:** `_rename_away` gets a new status `abandoned` (`CallPending` from the rename). `_finish_sweep` records
  two entries in one pending operation: the original path with the generation it read (`files_id`), and the tombstone
  `{"path": trash, "from": files, "files_id": None, ...}`. `retry_pending_sweeps` keeps (does not drop) a tombstone
  entry that does not exist yet while `mutation_pending(entry["from"])`; once the rename has landed the tombstone exists
  and is removed as usual, and the original-path entry is dropped as "gone". After a restart there is no in-flight
  rename in the new process: a tombstone that landed is found by the entry, by `sweep_trash` (known job) or by
  `sweep_orphans` (deleted job, see 2.3).
- A dead hard mount that never returns keeps that one path fenced for the process's life: the job's previews answer
  404 with the sentence above; a restart clears it. Accepted and stated in the audit (Task 6).

### 2.2 The pending writer (bounded pending-lock waits and fsync)

- New `Store._pending_op(fn, deadline=None) -> (bool, object)`: puts `fn` on a FIFO served by **one** daemon thread per
  store (`name="svf-maker-pending"`, started lazily). The thread runs `with self._pending_lock: entries =
  self._read_pending(); new, result = fn(entries); if new is not None and new != entries: self._write_pending(new)` and
  then marks the request done. The caller waits until `deadline` (default `Deadline(STAT_TIMEOUT_S)`) and gets
  `(True, result)` or `(False, None)`. An operation that is not waited for **still runs later, in order**: every
  operation is a read-modify-write under one lock, so no update is lost and the order of submission is kept.
- Every access to `pending-sweeps.json` goes through it: `_add_pending`, `retry_pending_sweeps` (read, the "replacement
  before removal" write, the "removed" write), `sweep_orphans` (read). The "replacement before removal" rule of H2 is
  kept: a retry removes tombstones only after its replacement operation returned `True`.
- `_pending_lock` stays (only the writer takes it); tests hold it to simulate contention. `_write_pending` and
  `_read_pending` are unchanged.
- Thread exits with the process (daemon). An operation still queued at exit is lost; what it would have named is found
  at the next start by `sweep_trash` / `sweep_orphans` (2.3).

### 2.3 One deadline through every sweep step

- `_rename_away(job, deadline, ...)`: `deadline=None` now means `Deadline(LOCKED_IO_S)` (no more per-call
  `STAT_TIMEOUT_S` chains); the rename uses `rename_bounded(files, trash, left())`.
- `_finish_sweep(job, step, deadline)` and `_add_pending(..., deadline=None)` pass the same deadline to `_pending_op`;
  an expired deadline still *submits* the record (it lands when the writer gets to it) and waits 0 s.
- `sweep_orphans(deadline)`: `fs_bounded("islink"/"isdir")` and `rename_bounded` with `left()`; skips a name with
  `mutation_pending`; **also** renames-and-removes orphan tombstones `^\.svf-maker-[0-9a-f]{12}\.trash-[0-9a-f]{8}$`
  whose job has no `job.json` (tombstones are dead by name; this closes the "entry lost at exit" hole of 2.2). Its
  pending read is `_pending_op(..., dl)`; not done in time -> only the jobs' folders are visited.
- `sweep_trash(job, deadline=None) -> bool` (True when nothing is left): stat with `min(STAT_TIMEOUT_S, remaining)`,
  `bounded_call(("listdir", out), ...)` (the same key `sweep_orphans` uses, so a hung `listdir` costs one thread),
  `fs_bounded` for `islink`/`isdir`, each removal `min(REMOVE_BOUND_S, remaining)`, stop when expired; a removal that
  did not finish is recorded as a tombstone pending entry (`_add_pending(..., trash=path, deadline=dl)`).
- `retry_pending_sweeps(stat_timeout=None, deadline_s=None, deadline=None)`: a given `deadline` is used as is (start-up
  passes its own); `deadline_s` keeps working for the idle sweeper.
- `server.startup_cleanup` passes `deadline` to `retry_pending_sweeps`, `sweep_files`, `sweep_trash`, `sweep_orphans`.
- `STARTUP_CLEANUP_S` (30.0) and `STOP_SWEEP_TOTAL_S` (8.0) keep their values: `desktop/test/unit.test.js` pins them
  against `desktop/lib/budget.js` (HANDSHAKE_S 75, STOP_WAIT_S 45). This card makes those budgets true.

### 2.4 Nothing under the lifecycle lock waits without a bound

- New `LOCKED_IO_S = 5.0` in `jobs.py`: one `Deadline` for all filesystem work on an output volume in one lifecycle
  section (`ensure_files_dir`, the rename step of a delete or idle sweep, the run's commit check). 5 s = the existing
  "a stat longer than this is unreachable" rule.
- `ensure_files_dir(job, locked=False, persist=True, deadline=None)`: fence check (2.1), then `_make_files_dir(job,
  dl)` with every call bounded and keyed: `stat_id_bounded(out)`, `bounded_call(("lstat", p))`, `("mkdir", p)`,
  `("chmod", p)`, `stat_id_bounded(files)`. An abandoned `mkdir`/`chmod` fences the path (`mutation_pending`) so a
  sweep records "busy" instead of renaming a directory that is still being made.
- New `class Busy(TimeoutError)` and `Store.update(job_id, fn, timeout=None)`, `Store.delete(job_id, locked=False,
  timeout=None)`: with a timeout the job lock is acquired with `acquire(timeout=...)` and `Busy("job %s is busy")` is
  raised when it is not. Every call made while the lifecycle lock is held passes `timeout=LOCKED_IO_S`: `_activate`'s
  `_update`, `ensure_files_dir`'s persist, `_claim_folder`'s and `_job_delete`'s `delete`, `retain`'s `delete`.
  `Handler._update(job_id, fn, timeout=None)` maps `Busy` to `409 "job <id> is busy; try again"`. (`Busy` is an
  `OSError`, so `retain`'s and `_claim_folder`'s existing `except OSError` already skip it.)

### 2.5 `POST run` of a local job in three sections (reads outside the lifecycle lock)

Upload jobs keep today's path unchanged. A local job:

1. **Prepare** (`Handler._run_prepare(job)`, context manager; lifecycle lock held only inside): loop, like
   `_preview_dir`: take the lifecycle lock; 503 when `worker._stopping`; `_refuse_cleanup_pending`; `current =
   self._load(job)`; 409 `"job %s is %s"` unless `detected`; try to take every preview lock of the job with
   `_sweep_locks(current, 0.0)` (non-blocking; `TimeoutError(font_id)` means a bake holds it: release the lifecycle lock,
   wait for that font's lock outside, release it, loop); `files = self._ensure_dir(current)` (bounded, persists
   `files_id`). Release the lifecycle lock, keep the preview locks, yield `(current, files)`; the preview locks are
   released when the block ends.
   Why the preview locks: `plan_steps` writes into the files directory (`os.makedirs(work_root)`, range copies). A sweep
   needs the preview locks to rename it, so none can move it away mid-plan and let `makedirs` re-create an untracked
   directory. Every lifecycle-lock holder takes preview locks only by try-lock, so no lifecycle wait depends on this.
2. **Read and plan** (inside the `with`, no store lock): `_check_local_inputs(j, fonts, sources)` (the part of today's
   `_check_local_run` that reads volumes: `check_path` of every root, `_check_unchanged` of every input, free space),
   `settings.run_ready` (licence hashing), `settings.plan_steps` (planning, range copies), `_check_steps`,
   `_check_notes`. Same errors and statuses as today.
3. **Commit** (`Handler._commit_run(job, fingerprint, steps)`, after the preview locks are released, lifecycle lock
   held): 503 stopping; `_refuse_cleanup_pending`; `fresh = self._load(job)`; 409 `"the job changed while the run was
   being prepared: run again"` when `_run_fingerprint(fresh) != fingerprint`; 409 `"job %s is %s"` unless `detected`;
   409 `"output folder is gone or changed"` unless `store.files_current(fresh, Deadline(LOCKED_IO_S))`; 409 `"output
   folder is in use by job %s"` from the store-list check (moved here from `_check_local_run`); then remove
   `<meta>/steps` and `_update(job, lambda j: j.update(state="queued", error=None, steps=steps, result=None),
   timeout=LOCKED_IO_S)`. Then `worker.enqueue` as today.

- `_run_fingerprint(j) -> str`: `json.dumps({k: j.get(k) for k in ("state", "roots", "scan_roots", "fonts",
  "settings", "output_dir", "output_id", "files_id")}, sort_keys=True)`. Taken from `current` right after Prepare
  (after `ensure_files_dir` set `files_id`).
- `Store.files_current(job, deadline) -> bool`: `stat_id_bounded(output_dir) == output_id` and the bounded `lstat` of the
  files directory is a real directory whose `[st_dev, st_ino] == files_id`; False on any `OSError`.
- The planned `work/` stays in the files directory when Commit refuses; it is the job's own and is swept with it.

---

## Global Constraints

- **`c/src` and `c/include` are unchanged.** G1 at the end of every task.
- **Gates at the end of every task, before its commit, in this order:**
  - G1 `git diff --exit-code 004a449 -- c/src c/include` -> exit 0, no output.
  - G2 `export TMP_DIR=$HOME/work/tmp/svf-fu-lifecycle; mkdir -p "$TMP_DIR"; TMPDIR=$TMP_DIR flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'`
    -> `OK (skipped=24)` and `Ran N tests`, N as the task states (997 at `004a449`). A stated N is a plan estimate; if
    the observed N differs, write the observed N and why in the commit body. If a test fails only because of
    `TMPDIR`, rerun that test without it, and report it to the controller. Do not change it.
  - G3 `python3 -m unittest discover -s maker/test -p test_server.py -k test_page_js_tables_match_python` -> `OK`.
- **Scratch only under `$HOME/work/tmp`** (`TMP_DIR` above), never `/tmp`.
- **Hung-volume tests are deterministic and fast.** No real hung mount. Use the existing technique
  (`maker/test/test_local.py:1019-1047`, `:1058-1078`): patch the one call (`os.rename`, `os.listdir`, `os.lstat`,
  `os.mkdir`, `os.fsync`, `shutil.rmtree`, `jobs.stat_id`, `jobs.Store._read_pending`, `settings._licence_sha`,
  `settings.plan_steps`) with a wrapper that, **only for the path under test**, sets an `entered` Event and waits on a
  `release` Event (`release.wait(20)`), calling the real function otherwise. Register `self.addCleanup(release.set)`
  **before** starting anything. Shrink the bounds with `mock.patch.object` (`jobs.LOCKED_IO_S`, `jobs.STOP_SWEEP_TOTAL_S`,
  `server.STARTUP_CLEANUP_S`, `jobs.REMOVE_BOUND_S`). A call that may hang runs on a daemon thread joined with a timeout;
  the test asserts the thread is no longer alive. Each new test takes under 3 s.
- **Upload jobs behave exactly as before.** Every test that exists at `004a449` passes unmodified.
- **Constants keep their values:** `STARTUP_CLEANUP_S = 30.0` (server.py), `STOP_SWEEP_TOTAL_S = 8.0`,
  `STAT_TIMEOUT_S = 5.0`, `REMOVE_BOUND_S = 30.0`, `PREVIEW_TRY_S = 0.5` (jobs.py). `desktop/test/unit.test.js` reads the
  first two from the source with `^NAME = ` regexes: keep them at column 0 in that form.
- **Lock order stays** lifecycle -> job lock -> preview locks -> pending lock. Any lock taken while the lifecycle lock
  is held is taken with a timeout or a try-lock (preview), never blocking.
- **Serialization:** tasks run in plan order; all touch `maker/jobs.py` and/or `maker/server.py`.
- **New tests go in a new file** `maker/test/test_local_bounds.py` (same header and `sys.path` block as
  `test_local.py:1-31`; `import jobs`, `import server`, `import settings`, `import localfx`, `import fixtures`). Shared
  test helper defined once at the top of that file:
  `class Hang` — `Hang(real, when)`: callable; `when(*args)` true -> `self.entered.set(); self.release.wait(20)`, then
  calls `real(*args, **kw)`. Attributes `entered`, `release` (`threading.Event`s).
- **No bare `git stash`.** WIP commits only.

## Review Focus

1. **A slow but healthy network volume** (stat or mkdir taking 1-4 s) must still work: `LOCKED_IO_S` is 5 s in all per
   section. Expected: create, preview and run succeed. Covered by the default constant (tests shrink it only inside
   their own `mock.patch`); reviewer checks no task lowers the default.
2. **Two requests on one hung folder** must not cost two threads or two waits under the lock: the second gets
   `CallPending` at once from the in-flight key. Test `test_a_second_request_on_a_hung_output_folder_fails_at_once`
   (Task 4).
3. **PUT settings racing POST run** must not queue a run planned from old settings: Commit's fingerprint. Test
   `test_a_run_whose_job_changed_while_preparing_is_refused` (Task 5).
4. **The process exits with pending records still queued** (stop deadline reached): the tombstones they named are
   found at the next start. Test `test_an_orphan_tombstone_of_a_deleted_job_is_swept_at_start_up` (Task 2).
5. **A rename that never returns** keeps the job usable for everything but its files directory, with a clear sentence
   and no new generation. Test `test_an_abandoned_rename_never_moves_a_later_generation` (Task 2).

---

### Task 1: The bounded primitives: `CallPending`, `mutation_pending`, `rename_bounded`, the pending writer

**Files:**
- Modify: `maker/jobs.py:73-113` (bounded helpers), `maker/jobs.py:426-458` (`Store.__init__`), `maker/jobs.py:639-704`
  (pending helpers)
- Create: `maker/test/test_local_bounds.py` (header, `Hang`, class `BoundedPrimitivesTest(unittest.TestCase)` over a
  plain `jobs.Store(<tempdir under TMPDIR>)`)

**Interfaces:**
- Produces: `jobs.CallPending(OSError)`; `jobs.MUTATING_OPS = ("rename", "mkdir", "chmod")`;
  `jobs.mutation_pending(path: str) -> bool`; `jobs.rename_bounded(src: str, dst: str, timeout: float) -> None`
  (raises `CallPending`, or the rename's own `OSError`); `jobs.Store._pending_op(fn, deadline: Deadline | None = None)
  -> tuple[bool, object]` where `fn(entries: list[dict]) -> (new_entries: list | None, result)`;
  `jobs.Store._add_pending(job, files, reason, trash=None, generation=None, deadline=None, origin=None) -> bool`
  (`origin` = the original path for a tombstone of an abandoned rename, stored as `"from"`; returns whether the record
  was written in time).

- [ ] **Step 1: Write the failing tests** in `BoundedPrimitivesTest`:
  - `test_rename_bounded_abandons_a_hung_rename_and_fences_the_path`: `Hang(os.rename, lambda s, d: s == src)` patched
    as `os.rename`; `with self.assertRaises(jobs.CallPending): jobs.rename_bounded(src, dst, 0.2)` takes < 0.6 s;
    `self.assertTrue(jobs.mutation_pending(src))`, `self.assertTrue(jobs.mutation_pending(os.path.dirname(src)))`
    (a parent is fenced too), `self.assertFalse(jobs.mutation_pending(src + "-other"))`; a second
    `rename_bounded(src, dst, 5)` raises `CallPending` in < 0.2 s; after `release.set()` and a poll (<= 2 s),
    `mutation_pending(src)` is False and `os.path.isdir(dst)`.
  - `test_pending_op_returns_by_the_deadline_while_the_pending_lock_is_held`: hold `store._pending_lock`;
    `done, _ = store._pending_op(lambda e: (e + [{"path": "x"}], None), jobs.Deadline(0.3))`; assert `done is False`
    and elapsed < 0.8; release the lock; poll <= 2 s until the file holds `[{"path": "x"}]`.
  - `test_pending_op_returns_by_the_deadline_while_fsync_hangs`: `Hang(os.fsync, lambda fd: True)`; same shape;
    `done is False`, elapsed < 0.8; after release the entry is in the file.
  - `test_pending_ops_keep_their_order_after_an_abandoned_one`: with the lock held, submit A (append `a`, deadline
    0.1) then B (append `b`, deadline 0.1); release; poll; the file is `[{"path": "a"}, {"path": "b"}]`.
  - `test_one_pending_writer_thread_however_many_ops_wait`: with the lock held, 20 ops with `Deadline(0.01)`;
    `threading.active_count()` grew by at most 1.
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_local_bounds.py -v`.
  Expected: 5 errors, `AttributeError: module 'jobs' has no attribute 'rename_bounded'` / `'CallPending'` /
  `'Store' object has no attribute '_pending_op'`.
- [ ] **Step 3: Implement** in `maker/jobs.py`: `CallPending`; make `bounded_call` raise it in both of its "pending"
  cases (J:84 and J:99) keeping the messages; `MUTATING_OPS`, `mutation_pending` (scan `_CALLS_IN_FLIGHT` under
  `_CALLS_LOCK`: `op in MUTATING_OPS and (p == path or p.startswith(path + os.sep))`); `rename_bounded`. In `Store`:
  `self._pending_q = queue.Queue()`, `self._pending_thread = None` and a `_pending_thread_lock`; `_pending_op` starts the
  daemon thread on first use; each request is `(fn, threading.Event, box)`; an exception in `fn` or the write is
  stored in the box and re-raised to a caller that waited (printed with `print_exc()` otherwise). Rewrite
  `_add_pending` as a `_pending_op` whose `fn` does today's merge (J:400-409) and returns `(entries_or_None, fresh)`;
  the `log.md` line is written by the caller after `done` and `fresh`. A tombstone entry gets `"from": origin` when
  `origin` is given. Do **not** convert `retry_pending_sweeps`/`sweep_orphans` yet (Task 2).
- [ ] **Step 4: Run** Step 2's command. Expected: `Ran 5 tests ... OK`.
- [ ] **Step 5: Gates** G1, G2 (expected N = 1002, `skipped=24`), G3.
- [ ] **Step 6: Commit** `git add maker/jobs.py maker/test/test_local_bounds.py && git commit` with message
  `maker local: bounded rename with a fence, one pending writer bounded by the caller's deadline (t_d1aba4b8)` and the
  `Co-Authored-By` trailer.

### Task 2: One deadline through rename, pending records, orphans and retries (H3b)

**Files:**
- Modify: `maker/jobs.py:473-498` (fence check only), `:605-637` (`delete` passes a deadline), `:706-777`
  (`_rename_away`, `_finish_sweep`), `:809-858` (`sweep_orphans`), `:878-984` (`retry_pending_sweeps`)
- Modify: `maker/server.py:541-563` (`startup_cleanup` passes `deadline=` to `retry_pending_sweeps`)
- Test: `maker/test/test_local_bounds.py`, class `SweepBoundsTest(localfx.LocalRunBase)`

**Interfaces:**
- Consumes: Task 1's `rename_bounded`, `CallPending`, `mutation_pending`, `_pending_op`, `_add_pending(..., deadline,
  origin)`.
- Produces: `_rename_away` status `"abandoned"` (tuple shape unchanged: `(status, trash, reason, generation, files)`);
  `Store.retry_pending_sweeps(stat_timeout=None, deadline_s=None, deadline=None)`; `Store.sweep_orphans(deadline=None)`
  (unchanged signature); `ensure_files_dir` raises `OutputGone` while `mutation_pending(files)`; `jobs.LOCKED_IO_S =
  5.0` (defined here: `_rename_away`'s default deadline).

- [ ] **Step 1: Write the failing tests** (`fd = self.files_dir(jid)` of a `local_job()`):
  - `test_stop_returns_by_the_deadline_although_a_rename_hangs`: `Hang(os.rename, lambda s, d: s == fd)`;
    `STOP_SWEEP_TOTAL_S` 1.0; `sweep_local_files()` on a thread, `join(3)`; `assertFalse(t.is_alive())` (fails today:
    the rename blocks under the lifecycle lock); elapsed < 2.0; the pending file has an entry with `path == fd` and one
    with `path.startswith(fd + ".trash-")` and `"from" == fd`.
  - `test_startup_returns_by_the_deadline_although_a_rename_hangs`: same hang; `self.release_lock()`;
    `server.STARTUP_CLEANUP_S` 1.0; `make_server(..., token=localfx.TOKEN)` on a thread, `join(4)`; a server was made,
    elapsed < 3.0, `jid in made[0].cleanup_pending`; stop it (`worker.stop()`, `server_close()`).
  - `test_an_abandoned_rename_never_moves_a_later_generation`: hang the rename; `store.sweep_files(job, bound=0.5)` is
    False in < 1.5 s; `with self.assertRaises(jobs.OutputGone): store.ensure_files_dir(store.load(jid))` and the
    message contains `"still being moved or made"`; `GET /api/jobs/<jid>/probe/...` answers 404 and `os.path.isdir(fd)`
    is still the old generation (same `st_ino` as before); `release.set()`; poll until `not mutation_pending(fd)`;
    `store.retry_pending_sweeps()`; no `.svf-maker-<jid>.trash-*` left in `self.out`; `ensure_files_dir` now makes a new
    directory whose identity is saved in `job.json`, and it is still there after `retry_pending_sweeps()` again.
  - `test_retry_keeps_a_tombstone_entry_whose_rename_is_in_flight`: hang the rename, `sweep_files(job, bound=0.5)`,
    then `retry_pending_sweeps(deadline_s=1)` while it hangs: both entries are still in the file (today: the tombstone
    entry is dropped as "confirmed gone").
  - `test_stop_returns_by_the_deadline_while_the_pending_lock_is_held`: `shutil.rmtree` hangs for `fd + ".trash-"`
    paths (as `test_local.py:1030`), `store._pending_lock` held by the test; `STOP_SWEEP_TOTAL_S` 1.0;
    `sweep_local_files()` thread `join(3)` not alive (fails today at J:688), elapsed < 2.0; after releasing both, poll:
    the tombstone entry reaches the file.
  - `test_stop_returns_by_the_deadline_while_fsync_hangs`: `Hang(os.fsync, lambda fd_: True)` plus the hanging
    `rmtree`; same assertions.
  - `test_orphan_sweep_returns_by_the_deadline_although_a_rename_hangs`: a done job makes `self.out` known; make
    `<out>/.svf-maker-0123456789ab`; hang `os.rename` for it; `store.sweep_orphans(jobs.Deadline(1.0))` on a thread,
    `join(3)` not alive (fails today at J:850).
  - `test_an_orphan_tombstone_of_a_deleted_job_is_swept_at_start_up`: a done job; make
    `<out>/.svf-maker-0123456789ab.trash-0badf00d/x`; `release_lock()`; `make_server`; the tombstone is gone; a
    `.svf-maker-<jid>.trash-...` of the live job is not touched by `sweep_orphans` (it is `sweep_trash`'s).
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_local_bounds.py -k SweepBoundsTest -v`.
  Expected: the hang tests FAIL on `assertFalse(t.is_alive())`; the in-flight-retry test FAILS on the entry count; the
  orphan-tombstone test FAILS on `assertFalse(os.path.exists(tomb))`.
- [ ] **Step 3: Implement** per design 2.1-2.3:
  - `_rename_away`: `dl = deadline or Deadline(LOCKED_IO_S)`; first `if mutation_pending(files): return ("failed",
    None, "busy (a filesystem call is still pending)", None, files)`; the rename is `rename_bounded(files, trash,
    left())`; `except CallPending: return ("abandoned", trash, "rename did not finish in time", generation, files)`.
  - `_finish_sweep`: `abandoned` -> one `_pending_op` that adds both entries (original with `generation`, tombstone
    with `origin=files`); every `_add_pending` call gets `deadline`.
  - `delete`: `_rename_away(job, Deadline(LOCKED_IO_S), check_active=False)` and `_finish_sweep(job, step, None)`.
  - `sweep_orphans`: `_pending_op` read with `dl`; `fs_bounded` + `rename_bounded` with `min(STAT_TIMEOUT_S,
    dl.remaining())`; skip names with `mutation_pending`; orphan tombstones (job without `job.json`) are collected and
    removed with the same deadline (no rename needed: already dead by name).
  - `retry_pending_sweeps`: `dl = deadline or Deadline(...)`; the three `_pending_lock` blocks become `_pending_op`
    calls with `dl` (read not done -> return; replacement not done -> return without removing anything); a tombstone
    entry that does not exist is kept while `mutation_pending(entry.get("from") or path)`; status `abandoned` from
    `_rename_away` -> keep the original entry and add the tombstone entry with `"from"`.
  - `ensure_files_dir`: under the lifecycle lock, before `_make_files_dir`, the fence of 2.1.
  - `server.startup_cleanup`: `store.retry_pending_sweeps(deadline=deadline)`.
- [ ] **Step 4: Run** Step 2's command, then `python3 -m unittest discover -s maker/test -p test_local.py -k Sweep`.
  Expected: OK for both.
- [ ] **Step 5: Gates** G1, G2 (N = 1010), G3.
- [ ] **Step 6: Commit** `maker local: rename, pending records, orphan sweep and retries within the caller's deadline;
  an abandoned rename fences its path (t_d1aba4b8)` + trailer.

### Task 3: Start-up `sweep_trash` within the shared deadline (H3a)

**Files:**
- Modify: `maker/jobs.py:860-876` (`sweep_trash`), `maker/server.py:541-563` (`startup_cleanup`)
- Test: `maker/test/test_local_bounds.py`, class `StartupBoundsTest(localfx.LocalRunBase)`

**Interfaces:**
- Consumes: Task 1's `_add_pending(..., deadline)`, `bounded_call`, `fs_bounded`, `remove_tree_bounded`.
- Produces: `Store.sweep_trash(job, deadline: Deadline | None = None) -> bool` (True when no tombstone of the job is
  left; `deadline=None` means one `Deadline(REMOVE_BOUND_S)` for the whole call).

- [ ] **Step 1: Write the failing tests** (a `done_job()`; tombstones made as `fd + ".trash-%08x" % n` with one file
  each; `self.release_lock()`; `make_server` on a thread):
  - `test_startup_with_several_hung_tombstones_returns_by_the_single_deadline`: three tombstones, `shutil.rmtree`
    hangs for them, `REMOVE_BOUND_S` 0.8, `STARTUP_CLEANUP_S` 1.0; `join(5)`; server made; elapsed < 2.0 (today:
    about 2.4 s, one 0.8 s allowance per tombstone).
  - `test_startup_returns_by_the_deadline_although_listdir_hangs`: `Hang(os.listdir, lambda p: p == self.out)`;
    `STARTUP_CLEANUP_S` 1.0; `join(4)`; `assertFalse(t.is_alive())` (today: blocks at J:869); elapsed < 3.0.
  - `test_unfinished_tombstone_removal_at_start_up_is_recorded_pending`: one hung tombstone, `STARTUP_CLEANUP_S` 1.0;
    after the start the pending file of the new server's data root names it (`files_id` None); after `release.set()`
    the new server's `store.retry_pending_sweeps()` removes it and empties the file.
  - `test_startup_returns_by_the_deadline_while_the_pending_file_hangs`: write one pending entry; patch
    `jobs.Store._read_pending` with a `Hang(..., lambda self_: True)`; `STARTUP_CLEANUP_S` 1.0; `join(4)` not alive;
    elapsed < 3.0.
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_local_bounds.py -k StartupBoundsTest -v`.
  Expected: the first FAILS on the elapsed assertion, the second and fourth on `is_alive()`, the third on the missing
  entry.
- [ ] **Step 3: Implement** `sweep_trash` per 2.3; in `startup_cleanup`: `store.sweep_trash(job, deadline)` and skip
  it when `deadline.expired()` (the job is then already in `cleanup_pending` or done; tombstones are inert and are
  found again at the next start).
- [ ] **Step 4: Run** Step 2's command. Expected: OK.
- [ ] **Step 5: Gates** G1, G2 (N = 1014), G3.
- [ ] **Step 6: Commit** `maker local: start-up tombstone sweep within the start-up deadline, unfinished removals
  recorded (t_d1aba4b8)` + trailer.

### Task 4: Bounded `ensure_files_dir` and bounded job-lock waits under the lifecycle lock (M5, part 1)

**Files:**
- Modify: `maker/jobs.py:473-518` (`ensure_files_dir`, `_make_files_dir`), `:573-579` (`update`), `:605-637`
  (`delete`), `Worker.retain` (J:1136-1155: `delete(..., timeout=LOCKED_IO_S)`)
- Modify: `maker/server.py:799-804` (`_update` gains `timeout`, maps `jobs.Busy` to 409), `:909-926` (`_activate`
  passes `timeout=jobs.LOCKED_IO_S`), `:935-955` (`_claim_folder`'s `delete`), `_job_delete` (S:1110-1118)
- Test: `maker/test/test_local_bounds.py`, class `LockedIoBoundsTest(localfx.LocalRunBase)`

**Interfaces:**
- Consumes: Task 2's `LOCKED_IO_S`, fence in `ensure_files_dir`.
- Produces: `jobs.Busy(TimeoutError)`; `Store.update(job_id, fn, timeout=None)`; `Store.delete(job_id, locked=False,
  timeout=None)`; `Store.ensure_files_dir(job, locked=False, persist=True, deadline=None)`;
  `Handler._update(job_id, fn, timeout=None)`.

- [ ] **Step 1: Write the failing tests.** Job A uses `self.out`; the healthy folder is `os.path.join(self.tmp,
  "healthy")` (made in the test). `LOCKED_IO_S` patched to 0.3 in each. "Create is quick" = `POST /api/jobs {"source":
  "local", "output_dir": healthy}` on a thread, `join(2)`, not alive, status 200, elapsed < 1.0.
  - `test_a_create_is_not_held_by_a_hung_output_stat_in_ensure`: A is a done job (files directory swept);
    `Hang(jobs.stat_id, lambda p: p == self.out)` patched as `jobs.stat_id` **after** A is done; `GET
    /api/jobs/A/source/<dos>.svf` on a thread; wait `entered`; create is quick (today: blocks behind the lifecycle
    lock); the GET answers 404 within 1.0 s.
  - `test_a_create_is_not_held_by_a_hung_mkdir`: as above with `Hang(os.mkdir, lambda p, *a: p == fd)`; create is
    quick; the GET answers 404; while the mkdir hangs, `store.sweep_files(store.load(A), bound=0.5)` is False and the
    pending entry's reason says busy; `os.path.exists(fd)` is unchanged by the sweep; after release and
    `retry_pending_sweeps()` (A deleted first via DELETE) no `.svf-maker-A*` is left.
  - `test_a_second_request_on_a_hung_output_folder_fails_at_once`: with the stat hang of the first test, a first GET
    is answered 404; a second GET is answered 404 in < 0.2 s (the in-flight key) and `threading.active_count()` grew
    by at most 1 over both.
  - `test_a_lifecycle_holder_does_not_wait_for_a_held_job_lock`: A detected; the test holds `store.lock(A)`;
    `DELETE /api/jobs/A` answers 409 with `"busy"` in the error within 1.0 s (today: blocks); create is quick meanwhile.
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_local_bounds.py -k LockedIoBoundsTest -v`.
  Expected: FAIL on the create's `assertFalse(t.is_alive())` / elapsed, and on the DELETE thread still alive.
- [ ] **Step 3: Implement** per 2.4. `_make_files_dir(job, dl)` bounded calls with `left = lambda: min(STAT_TIMEOUT_S,
  dl.remaining())`; `FileNotFoundError` from the bounded `lstat` still means "make it"; `CallPending` propagates as an
  `OSError` (the handlers already map `OSError` to 404/409/400 with `_os_reason`). `update`/`delete` with a timeout use
  `lock.acquire(timeout=...)` + `try/finally release`, `Busy` on failure. `_update(job_id, fn, timeout=None)` catches
  `jobs.Busy` -> `_HttpError(409, "job %s is busy; try again" % job_id)`. `_job_delete` maps `jobs.Busy` the same way.
- [ ] **Step 4: Run** Step 2's command, then `python3 -m unittest discover -s maker/test -p test_local.py`.
  Expected: OK for both.
- [ ] **Step 5: Gates** G1, G2 (N = 1018), G3.
- [ ] **Step 6: Commit** `maker local: files directory made with bounded calls; no unbounded job-lock wait under the
  lifecycle lock (t_d1aba4b8)` + trailer.

### Task 5: Local `POST run` reads and plans outside the lifecycle lock (M5, part 2)

**Files:**
- Modify: `maker/server.py:1443-1507` (`_job_run` local branch, `_check_local_run` split), new `_run_prepare`,
  `_commit_run`, `_run_fingerprint` beside `_preview_dir` (S:966ff)
- Modify: `maker/jobs.py` (`Store.files_current`)
- Test: `maker/test/test_local_bounds.py`, class `RunPrepareTest(localfx.LocalRunBase)`

**Interfaces:**
- Consumes: Task 4's bounded `ensure_files_dir` (via `_ensure_dir`), `_update(..., timeout)`, `LOCKED_IO_S`;
  `server._sweep_locks(job, timeout)` (exists, S:83).
- Produces: `Handler._run_prepare(job: str)` (context manager yielding `(current: dict, files_dir: str)`),
  `Handler._check_local_inputs(j, fonts, sources) -> None`, `Handler._commit_run(job: str, fingerprint: str, steps:
  list) -> dict`, `server._run_fingerprint(j: dict) -> str`, `jobs.Store.files_current(job: dict, deadline: Deadline)
  -> bool`. `_check_local_run` is removed (its parts live in `_ensure_dir`, `_check_local_inputs` and `_commit_run`).

- [ ] **Step 1: Write the failing tests.** A = `local_job()` + `self.select(A)`; healthy folder and "create is quick"
  as in Task 4. Helper `_run_on_thread(A)` -> thread + result list for `POST /api/jobs/A/run`.
  - `test_a_create_is_not_held_by_a_run_reading_a_hung_input`: `Hang(os.lstat, lambda p, *a: p ==
    os.path.join(self.roots[0], "Munjo.ttf"))` patched as `os.lstat` only after `select`; start the run; wait
    `entered`; create is quick (today: blocked behind the lifecycle lock); release; the run answers 200 and the job
    reaches `done` (`wait_done`).
  - `test_a_create_is_not_held_by_a_run_hashing_a_hung_licence`: `Hang(settings._licence_sha, lambda *a: True)`
    patched as `settings._licence_sha`; same assertions.
  - `test_a_create_is_not_held_by_a_run_planning_on_a_hung_volume`: `Hang(settings.plan_steps, lambda *a, **k:
    True)` patched as `settings.plan_steps` (covers planning and the range copies `plan_steps` makes); same assertions.
  - `test_run_preparation_holds_no_lifecycle_lock`: the `plan_steps` hang; at `entered`,
    `assertFalse(self.srv.store.lifecycle.locked())` and every preview lock of A is held
    (`server._preview_lock(A, fid).locked()` for each font).
  - `test_a_run_whose_job_changed_while_preparing_is_refused`: the `plan_steps` hang; at `entered`, a `PUT settings`
    with A's batch sizes changed is sent on a thread (it waits for the preview locks; that is expected); release; the
    run answers 409 with `"changed while the run was being prepared"`; the PUT answers 200; `job(A)["state"] ==
    "detected"`; a second `POST run` answers 200.
  - `test_a_run_whose_files_directory_was_replaced_while_preparing_is_refused`: the `plan_steps` hang; at `entered`,
    `os.rename(fd, fd + "-moved")` and `os.mkdir(fd)`; release; the run answers 409 `"output folder is gone or
    changed"`; state `detected`.
  - `test_a_delete_during_run_preparation_leaves_no_files_directory`: the `plan_steps` hang; at `entered`, `DELETE
    /api/jobs/A` answers 200 (its rename is refused: preview locks busy, recorded pending); release; the run answers
    404; `store.retry_pending_sweeps()`; no `.svf-maker-A*` in `self.out`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_local_bounds.py -k RunPrepareTest -v`.
  Expected: the three "create is quick" tests and `..._holds_no_lifecycle_lock` FAIL (thread alive / `locked()` True);
  the changed-job test FAILS on 200 instead of 409 (today the PUT waits for the job lock and the run wins);
  the replaced-directory test passes or fails depending on where the hang sits today — record which in the commit
  body; the delete test may pass today (keep it: it pins the new interleaving).
- [ ] **Step 3: Implement** per 2.5. `_job_run`: upload branch unchanged; local branch:
  ```
  with self._run_prepare(job) as (current, files_dir):
      fingerprint = _run_fingerprint(current)
      fonts, sources = self._stamped(current.get("fonts") or []), store.sources(current)
      self._check_local_inputs(current, fonts, sources)
      errors = settings.run_ready(...)          # as today, with own_earlier/repo_index
      steps = settings.plan_steps(...)          # as today; ValueError -> 400
      self._check_steps(...); self._check_notes(...)
  current = self._commit_run(job, fingerprint, steps)
  ```
  Same error texts and statuses as today for every check that moved. `_commit_run` order as in 2.5; the
  `shutil.rmtree(<meta>/steps)` stays inside it.
- [ ] **Step 4: Run** Step 2's command, then `python3 -m unittest discover -s maker/test -p test_local.py` and
  `python3 -m unittest discover -s maker/test -p test_server.py`. Expected: OK for all three.
- [ ] **Step 5: Gates** G1, G2 (N = 1025), G3.
- [ ] **Step 6: Commit** `maker local: POST run prepares outside the lifecycle lock under the job's preview locks and
  commits after revalidating the job and its files directory (t_d1aba4b8)` + trailer.

### Task 6: Documents, desktop gates, closing

**Files:**
- Modify: `docs/maker-audit.md` section 8 ("Accepted trade-off (lifecycle lock)" and "Known limits of the cleanup"):
  replace both with "Bounded lifecycle (t_d1aba4b8)": the bounds (start-up `STARTUP_CLEANUP_S`, stop
  `STOP_SWEEP_TOTAL_S`, each lifecycle section `LOCKED_IO_S`), the fence rule and its accepted limit (a never-returning
  rename keeps that one directory unavailable until restart), the run's three sections, and the test names of Tasks
  1-5 as evidence rows.
- Modify: `maker/jobs.py` `Store.__init__` comment (J:448-456): the lifecycle lock is never held across a read of an
  input, planning or an unbounded call; every lock taken under it is taken with a timeout or a try-lock.
- Modify: `docs/superpowers/specs/2026-11-04-maker-local-mode-design.md` 8.3: one added paragraph after the lifecycle
  list pointing to the audit section (the spec's own sentence "the start-up sweep runs on a thread after the bind" is
  already historical; say so in that paragraph, do not rewrite the list).

- [ ] **Step 1: Write the document changes** above.
- [ ] **Step 2: Gates** G1, G2 (N = 1025), G3, and the desktop ones (the sidecar's local mode changed in its run
  path and its start-up/stop):
  - G4 `cd desktop && TMPDIR=$TMP_DIR node --test test/unit.test.js` -> all pass (pins `STARTUP_CLEANUP_S` and
    `STOP_SWEEP_TOTAL_S` against `desktop/lib/budget.js`).
  - G5, announced to the controller (`START G5 task6` / `FINISH G5 task6 <result>`):
    `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy bash desktop/test/run-e2e.sh` and
    `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy node --test desktop/test/lifecycle.test.js`
    -> both pass (the e2e `flow` converts a sample through `POST run`; `lifecycle` checks the quit sequence).
- [ ] **Step 3: Commit** `docs: bounded lifecycle of the maker local mode; audit rows (t_d1aba4b8)` + trailer.

---

## Desktop app risk

`desktop/` runs the sidecar's local mode (`maker/sidecar.py serve`). What changes for it: (a) start-up and stop now
really end within `STARTUP_CLEANUP_S` / `STOP_SWEEP_TOTAL_S`, which `desktop/lib/budget.js` already assumes (HANDSHAKE_S
75 s, STOP_WAIT_S 45 s): no budget change; (b) `POST run` can answer a new 409 ("the job changed while the run was
being prepared: run again", "job <id> is busy; try again") and previews a new 404 sentence while a fenced rename is
in flight; the page shows any 409/404 error text generically, no page change is planned; (c) one extra daemon thread
(`svf-maker-pending`) per server. The frozen sidecar needs no spec change (no new import). G4 and G5 run once, in
Task 6. If the controller wants the page to retry the new 409 automatically, that is a separate card.

## Self-review notes

- Card coverage: sweep_trash deadline (Task 3), rename under locks (Tasks 1-2), pending-lock waits and fsync (Tasks
  1-2, start-up variant Task 3), ensure_files_dir bounded (Task 4), run's input stats / licence hashing / planning /
  range copies outside the lock (Task 5; range copies are inside `plan_steps`, so the planning test covers them),
  "hung volume while a job in a healthy folder is created" (Tasks 4 and 5), suite green (G2 every task).
- Not covered on purpose: the data root itself on a hung volume (`job.json`, `Store.list`, `log.md`): the data root is
  the app's own directory on the local disk; the pending file's writes are bounded for callers anyway.
