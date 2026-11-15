# Maker local mode: bounded lifecycle (start-up, stop, activation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** No filesystem call on an output or input volume can hold the maker's start-up, its stop, or the store-wide
lifecycle lock for longer than a stated bound, and an abandoned call can never act on a later generation of a files
directory. Card t_d1aba4b8.

**Closing measurement (card, verbatim):** "start-up sweep_trash, os.rename under locks, pending-lock waits and
pending-file fsync all take the shared absolute Deadline and never hang start-up/stop on a hung mount; ensure_files_dir
and POST run's pre-queue reads (input stats, licence hashing, planning, range copies) happen outside the lifecycle lock
or are bounded, with tests on a hung volume while a job in a healthy folder is created; maker suite green".

**Architecture:** Three changes, in this order. (1) New primitives in `maker/jobs.py`: a bounded rename that leaves a
*fence* on its path while it is still running, read-only bounded calls that share one in-flight call per path, and one
writer thread through which every read and write of `pending-sweeps.json` goes, so a caller waits for it only until its
`Deadline` (plus a short floor). (2) Every sweep path (stop, start-up, idle, delete) uses them with the caller's single
`Deadline`; start-up `sweep_trash` becomes deadline-bound; every removal is handled on its own. (3) Every filesystem call
under the lifecycle lock is bounded per section (`LOCKED_IO_S`), every job-lock wait under it is bounded, `PUT settings`
no longer waits for a preview lock while it holds the job lock, and a local `POST run` does its reads and planning
*outside* the lifecycle lock, between a short "prepare" section and a "commit" whose job checks run inside the job
lock.

**Tech Stack:** Python 3 stdlib, unittest, `unittest.mock`. No new dependency (`queue`, `threading` are already
imported by `jobs.py`; `functools` is stdlib).

**Origin:** SOL review of the maker local mode, findings H3 and M5
(`/home/thkim/work/scratch/review-lanes/maker-local-final-r4-sol/out.md`; its line numbers are of an older commit).
Known-limits text: `docs/maker-audit.md` section 8, "Known limits of the cleanup (follow-up card t_d1aba4b8)" and
"Accepted trade-off (lifecycle lock)". Lifecycle design: `docs/superpowers/specs/2026-11-04-maker-local-mode-design.md`
8.3 and the lock order at `Store.__init__` (`maker/jobs.py:439-443`). Plan reviews (Opus, agy Argon) and their
dispositions: section "Review dispositions" at the end.

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
  (equivalent, but not the shared object).

### H3b still holds: rename and pending persistence are not bounded

- J:745 `os.rename(files, trash)` is synchronous, under the lifecycle lock (held by the caller, J:795-803) **and** the
  job's preview locks (J:730-743). A mount that answers `stat` and hangs on `rename` holds start-up (via `sweep_files`,
  S:557), stop (`Worker.sweep_local_files`, J:1098-1112) and every request that wants the lifecycle lock.
- J:847 and J:850 (`sweep_orphans`): **raw `os.path.islink`/`isdir` and raw `os.rename`** under the lifecycle lock,
  which it holds across **all** known folders (J:830-855). Not named by the review; same defect.
- J:623 `Store.delete` calls `_rename_away(job, None, ...)`: with no deadline every stat is `STAT_TIMEOUT_S` and the
  rename is unbounded, under the lifecycle lock (request path: DELETE, `retain`, `_claim_folder` takeover).
- Pending persistence: `_finish_sweep` (J:755-777) calls `_add_pending` (J:774) **after** the deadline may have
  expired; `_add_pending` waits on `_pending_lock` with no timeout (J:688) and its merge (J:686-696) writes + `fsync`s
  the file and its directory synchronously (`_write_pending`, J:665-680). `retry_pending_sweeps` (J:894, J:958, J:977)
  and `sweep_orphans` (J:823) also wait on `_pending_lock` without a bound.

### M5 still holds: the lifecycle lock is held across unbounded I/O

- J:473-498 `ensure_files_dir` runs under the lifecycle lock (J:485) and `_make_files_dir` (J:500-518) does **raw
  `stat_id(output_dir)`** (J:502), **raw `os.lstat` / `os.mkdir` / `os.chmod`** per level (J:510-513) and a raw
  `stat_id(files)` (J:517). Callers under the lock: `_job_create` (S:899), `_preview_dir` -> `_ensure_dir` (S:984-990,
  S:1013), `_files_dir_ready` for detect (S:1025, S:1131), `_check_local_run` (S:1487).
- Local `POST run`: `_job_run` (S:1443-1479) runs its whole `transition` through `_activate` (S:1473 -> S:916-923),
  i.e. under the lifecycle lock **and** the job lock: `_check_local_run` (S:1481-1507: `ensure_files_dir`, `check_path`
  of every root, `os.lstat` of every input in `_check_unchanged` S:1537-1547, `shutil.disk_usage` S:1503),
  `settings.run_ready` (S:1460; licence hashing `settings._licence_sha`, settings.py:1120-1166, reached through
  `_licence_present_ok` settings.py:1171-1191 and `_clash_errors` settings.py:1228), `settings.plan_steps` (S:1465;
  `os.makedirs` into the files directory, range-list copy `shutil.copyfile` settings.py:1510), `_check_steps` /
  `_check_notes` (S:1468-1469; `Sources.abs_of` resolves real paths on the input volume).
- Not named by the review, same class: under the lifecycle lock the job lock is waited for **without a bound**
  (`Store.delete` J:618, `_activate` -> `store.update` S:923, `ensure_files_dir`'s persist J:495).
- **A real deadlock today (lock-order inversion):** `_preview_dir` holds the lifecycle lock and a preview lock
  (S:984-990) and then waits for the job lock in `ensure_files_dir`'s persist (J:495); `_job_settings` holds the job
  lock (inside `_update`, S:1440) and waits for that preview lock (S:1436-1438). The documented order
  (J:439-443: lifecycle -> job -> preview) is broken by both. `_remove_preview` there also touches the output volume
  under the job lock.

---

## 2. Design

### 2.1 Bounded calls: mutating calls fence, read-only calls share

`bounded_call` (J:106-132) today runs one daemon thread per key and raises at once when a call with that key is still
running (J:113), and on timeout (J:128).

- New `class CallPending(OSError)`; both raises become `CallPending` (same messages). Every existing `except OSError`
  is unchanged.
- `_CALLS_IN_FLIGHT` becomes a dict `key -> (threading.Event done, list box)`. A second **read-only** call with the same
  key (op not in `MUTATING_OPS`) does not start a thread and does not fail at once: it waits on the first call's
  `done` within its **own** timeout and returns / raises the first call's result; `CallPending` if it is still running
  at the end of that timeout. So a healthy concurrent caller (idle retry and a create stating the same folder) never
  fails just because another caller is in flight, and a hung path still costs one thread.
- New `MUTATING_OPS = ("rename", "mkdir", "chmod")`. A second mutating call with the same key raises `CallPending` at
  once (never runs twice). New `mutation_pending(path) -> bool`: True while a call whose op is in `MUTATING_OPS` and
  whose key path is @p path or below it is still in flight; new `mutation_kind(path) -> str | None` returns that op
  (`"rename"` wins over the others).
- New `rename_bounded(src, dst, timeout) -> None`: `bounded_call(("rename", src), lambda: os.rename(src, dst),
  timeout)`; `CallPending` when it did not return (the rename is then in flight and fences `src`).
- New `Deadline.capped(seconds) -> Deadline`: a new `Deadline` ending at the earlier of `self.end` and
  `now + seconds`.

### 2.2 The fence (how an abandoned rename never touches a later generation)

`os.rename` acts on a *name*. A rename that is abandoned can complete later and move whatever then sits at that name.
The only way to make that safe is to keep anything new from appearing at the name while the call is in flight.

- `ensure_files_dir` is the only creator of a files directory (previews, probes, detect, run all go through it). Under
  the lifecycle lock it raises `OutputGone("the files directory is still being moved or made on a slow or hung volume;
  try again later")` while `mutation_pending(files)`. While an abandoned rename of `<out>/.svf-maker-<id>` is in
  flight no new generation can be made at that name; when it lands it can only move the generation it was issued for.
- `_rename_away` returns `failed` with reason `"busy (a filesystem call is still pending)"` when
  `mutation_pending(files)` before it starts, and tells `_finish_sweep` which kind it was:
  - pending **`mkdir` or `chmod`**: "a generation of unknown identity is being made". The record is made with
    `making=True`: its `files_id` becomes **None, replacing any recorded id** (`job.json`'s `files_id`, and an older
    entry's, are of an earlier, swept generation; keeping them would make a retry drop the entry as "a newer
    generation" once the late `mkdir` lands, and the directory would leak);
  - pending **`rename`**: the record keeps whatever `files_id` the existing entry has (the abandoned rename recorded
    the generation it was issued for).
- `_add_pending(..., making=False)` merge rule: `making=True` -> the entry's `files_id` is set to None (and
  `"making": true` is stored, for the log and the reader); otherwise a None `files_id` never overwrites a recorded
  non-None one, and a non-None one replaces a different non-None one (today's "newer generation" rule). A retry treats
  `files_id None` as today: any generation at that path is removed once the job is not in use.
- **Tracking an abandoned rename:** `_rename_away` gets a new status `abandoned` (`CallPending` from the rename).
  `_finish_sweep` records two entries in one pending operation: the original path with the generation it read
  (`files_id`), and the tombstone `{"path": trash, "from": files, "files_id": None, ...}`.
- `retry_pending_sweeps`:
  - a tombstone entry whose path does not exist is **kept and skipped at once** (`continue`, before any
    `islink`/`isdir`) while `mutation_pending(entry.get("from") or path)`;
  - a tombstone produced by status `abandoned` in this pass is persisted but **not** put on this pass's removal list
    (it may not exist yet; a `FileNotFoundError` from it would otherwise be counted as "removed" and drop the entry);
  - only `renamed` tombstones of this pass and existing tombstone entries are removed in this pass.
- After a restart there is no in-flight rename in the new process: a tombstone that landed is found by its entry, by
  `sweep_trash` (known job) or by `sweep_orphans` (any job, 2.4).
- A dead hard mount that never returns keeps that one path fenced for the process's life: the job's previews answer
  404 with the sentence above; a restart clears it. Accepted (controller), documented in the audit (Task 6).

### 2.3 The pending writer (bounded pending-lock waits and fsync)

- New `Store._pending_op(fn, deadline=None) -> (bool, object)`: puts `fn` on a FIFO served by **one** daemon thread per
  store (`name="svf-maker-pending"`). The thread runs `with self._pending_lock: entries = self._read_pending(); new,
  result = fn(entries); if new is not None and new != entries: self._write_pending(new)` and marks the request done. The
  caller waits until `deadline` (default `Deadline(STAT_TIMEOUT_S)`), **but at least `PENDING_FLOOR_S = 0.5` s** (a
  healthy disk then always lands the record even when the caller's deadline has run out), and gets `(True, result)` or
  `(False, None)`. An operation not waited for **still runs later, in order**: every operation is a read-modify-write
  under one lock, so no update is lost and the submission order is kept.
- **No floor while the writer is stalled:** the store keeps `self._pending_unfinished` (count of submitted operations
  not yet done, under `_pending_thread_lock`). A caller whose own operation has another unfinished one ahead of it waits
  only until its deadline, **without** the floor: the writer is stuck (hung fsync, held lock), and N records must not
  cost N x 0.5 s. The floor applies only when the queue was empty when the caller submitted.
- **One record per sweep call:** `sweep_trash` and `sweep_orphans` collect every tombstone they could not remove and
  record them in **one** `_pending_op` at the end of the call (not one per tombstone).
- The thread is started lazily and **exits when idle**: it waits on the queue with `timeout=PENDING_IDLE_S = 2.0`.
  The race between exit and a new submission is closed by one lock: `_pending_op` **enqueues and checks/starts the
  thread inside `_pending_thread_lock`** (start a new thread when `_pending_thread is None`); the thread, after a
  `queue.Empty` timeout, takes `_pending_thread_lock`, **re-checks `self._pending_q.empty()`**, and only then sets
  `_pending_thread = None` and returns (otherwise it goes on serving). So a test suite with many stores does not
  accumulate threads, and no request is ever left on a queue without a thread.
- New `Store.flush_pending(deadline) -> bool`: `_pending_op(lambda e: (None, None), deadline)` (same floor). Called
  at the end of `Worker.sweep_local_files` and of `startup_cleanup`, so a process that exits right after stop or
  start-up does not lose records on a healthy disk.
- Every access to `pending-sweeps.json` goes through it: `_add_pending`, `retry_pending_sweeps` (read, the "replacement
  before removal" write, the "removed" write), `sweep_orphans` (read). The H2 rule is kept: a retry removes tombstones
  only after its replacement operation returned `True`.
- `_pending_lock` stays (only the writer takes it); tests hold it to simulate contention. `_write_pending` and
  `_read_pending` are unchanged.
- Stop and start-up budgets: on a healthy disk a floor wait ends as soon as the write lands (milliseconds); on a
  stalled writer no floor is waited after the first unfinished operation. So a pass overruns its deadline by at most
  one floor (0.5 s) plus the flush's floor (0.5 s), whatever the number of jobs or tombstones. `desktop/lib/budget.js`
  has 45 - (30 + 1 + 8) = 6 s of stop margin and 75 - 60 = 15 s of handshake margin.

### 2.4 One deadline through every sweep step; every removal on its own

- `_rename_away(job, deadline, ...)`: its locked step uses `dl = (deadline or Deadline(LOCKED_IO_S))`, **capped at
  `LOCKED_IO_S`** for request and idle callers (`dl.capped(LOCKED_IO_S)`); start-up and stop pass their own deadline
  uncapped (they are the only work then, see 2.5). The rename uses `rename_bounded(files, trash, left())`.
- `_finish_sweep(job, step, deadline)` and `_add_pending(..., deadline=None)` pass the same deadline to `_pending_op`.
- `sweep_orphans(deadline)`:
  - pending read through `_pending_op(..., dl)`; not done -> only the jobs' folders are visited;
  - the lifecycle lock is taken **per folder** (`acquire(timeout=dl.remaining())`), each section capped
    `dl.capped(LOCKED_IO_S)`, not across all folders;
  - names: `^\.svf-maker-([0-9a-f]{12})(\.trash-[0-9a-f]{8})?$`; the job id is group 1 (never
    `name[len(FILES_DIR_PREFIX):]`, which keeps the `.trash-` suffix). A plain name is an orphan only when
    `<jobs>/<id>/job.json` does not exist (as today). **A tombstone is dead by name: it is removed whatever its job**
    (no `job.json` check);
  - `fs_bounded("islink"/"isdir")` and `rename_bounded` with `left()`; a name with `mutation_pending` is skipped;
  - **each removal on its own** (outside the lifecycle lock): `FileNotFoundError` = removed; any other exception or an
    unfinished removal -> logged by type only and the tombstone is collected; the loop goes on with the next one. At the
    end, the collected tombstones are recorded in **one** `_pending_op` (new `Store._add_pending_many(entries,
    deadline)`); nothing escapes `sweep_orphans`.
- `sweep_trash(job, deadline=None) -> bool` (True when no tombstone of the job is left; `None` -> one
  `Deadline(REMOVE_BOUND_S)` for the call): stat with `min(STAT_TIMEOUT_S, remaining)`,
  `bounded_call(("listdir", out), ...)` (the key `sweep_orphans` uses), then **per tombstone, inside one `try`**:
  `fs_bounded("islink")`/`fs_bounded("isdir")`, removal `min(REMOVE_BOUND_S, remaining)`; `FileNotFoundError` =
  removed; an `OSError` (timeout included) or an unfinished removal collects that tombstone and the loop goes on; once
  `dl.expired()` every remaining matching name is collected without being touched. The collected tombstones are
  recorded in one `_add_pending_many(..., dl)` at the end. Nothing escapes.
- `retry_pending_sweeps(stat_timeout=None, deadline_s=None, deadline=None)`: a given `deadline` is used as is (start-up
  passes its own); `deadline_s` keeps working. Its per-call timeout loses today's 50 ms floor (J:905, `max(0.05,
  ...)`): `left = lambda: min(STAT_TIMEOUT_S if stat_timeout is None else stat_timeout, dl.remaining())`, and the entry
  loop checks `dl.expired()` **before each filesystem call** (helper `step(op, path)` that raises a private `_OutOfTime`
  when expired; the entry is then kept and the loop ends), so no call starts after the deadline.
- `sweep_files(job, stat_timeout=None, bound=None, deadline=None, own_run=False)`: with neither `bound` nor `deadline`
  it now makes `Deadline(REMOVE_BOUND_S)` **before** taking the lifecycle lock and takes that lock with
  `acquire(timeout=deadline.remaining())` (today J:795-796 waits with no timeout); the locked step is capped at
  `LOCKED_IO_S` as above. Callers without a deadline: `_finish_local` (worker) and `_sweep_idle`.
- `_sweep_idle(server, now=None)` makes one `Deadline(RETRY_DEADLINE_S)` per pass, passes it to every `sweep_files`
  call of the pass and to `retry_pending_sweeps(deadline=...)`, stops when it has expired, and skips any job in
  `server.preparing` (2.7).
- `server.startup_cleanup` passes `deadline` to `retry_pending_sweeps`, `sweep_files`, `sweep_trash`, `sweep_orphans`;
  `sweep_trash` and `sweep_orphans` each in their own `try/except Exception: jobs.print_exc()`; a `sweep_trash` result
  never adds the job to `cleanup_pending` (tombstones are inert; the live name is what `cleanup_pending` guards).
  `Worker.sweep_local_files` wraps `sweep_orphans` the same way. Both end with `store.flush_pending(deadline)`.
- `STARTUP_CLEANUP_S` (30.0) and `STOP_SWEEP_TOTAL_S` (8.0) keep their values: `desktop/test/unit.test.js` pins them
  against `desktop/lib/budget.js` (HANDSHAKE_S 75, STOP_WAIT_S 45).

### 2.5 What `LOCKED_IO_S` bounds (the corrected claim)

`LOCKED_IO_S = 5.0` (jobs.py) is the bound **per lifecycle section** of a request or of the idle sweeper: one
`Deadline` covers every bounded call of that section together (the ~11 calls of `_make_files_dir`, the stats and the
rename of `_rename_away`, the pending record a local `delete` writes before it removes the metadata (2.6), the commit
check of a run), not each call. A hung volume can therefore stall other requests
for at most `LOCKED_IO_S` per section, plus at most one `PREVIEW_TRY_S` try-lock and one bounded job-lock wait
(`LOCKED_IO_S`) where a section takes them; a second request on the same hung path shares the in-flight call (2.1)
inside its own section's bound. **Exception:** start-up cleanup (before the server exists) and stop (after requests are
refused, `worker._stopping`) hold the lifecycle lock within their own deadlines (`STARTUP_CLEANUP_S`,
`STOP_SWEEP_TOTAL_S`) and are not capped at `LOCKED_IO_S`; `sweep_orphans` is capped per folder even there. The
data root (`job.json`, `Store.list`, `log.md`) is assumed to be a local disk and is not bounded (as today).

### 2.6 No unbounded wait under the lifecycle lock; the lock order restored

- New `class Busy(TimeoutError)` and `Store.update(job_id, fn, timeout=None)`, `Store.delete(job_id, locked=False,
  timeout=None)`: with a timeout the job lock is acquired with `acquire(timeout=...)` and `Busy("job %s is busy")` is
  raised when it is not. Every call made while the lifecycle lock is held passes `timeout=LOCKED_IO_S`: `_activate`'s
  `_update`, `_claim_folder`'s and `_job_delete`'s `delete`, `retain`'s `delete`.
- `ensure_files_dir(job, locked=False, persist=True, deadline=None)`: after the fence check it **takes the job lock
  first** (bounded, `timeout=dl.remaining()`, `Busy` when not) and holds it while making the directory and saving
  `files_id` (`load` + set + `_write` under that one acquisition; no second `update`). So `Busy` always means *nothing
  was made*. `_make_files_dir(job, dl)`: every call bounded and keyed: `stat_id_bounded(out)`, `bounded_call(("lstat",
  p))`, `("mkdir", p)`, `("chmod", p)`, `stat_id_bounded(files)`; `dl` is the caller's deadline capped at
  `LOCKED_IO_S`.
- Handler mapping: `jobs.Busy` is caught **before** `OSError` everywhere a store call can raise it (`_ensure_dir`,
  `_files_dir_ready`, `_update`, `_job_delete`, Prepare) and answered `409 "job <id> is busy; try again"`;
  `CallPending` and other `OSError`s keep today's mapping (`_ensure_dir`/`_files_dir_ready` 404, run 409).
- **`_job_settings` no longer waits for a preview lock inside the job lock:** the transition only computes the changed
  font ids (into a list in the closure) and saves the settings; the removal of their previews happens after `_update`
  returns, each under its preview lock, outside every store lock - the pattern `_job_detect` and `_job_sources` already
  use (`_clear_previews`, "Y6"). This removes today's deadlock and restores lifecycle -> job -> preview. W2 still holds
  in the sense its tests check (the PNG of a changed font is gone when the PUT answers); a bake that starts in the
  instant between the save and the removal draws from the new settings (it reloads the job), and the removal then only
  drops a fresh PNG, which is redrawn on the next GET.
- **`_preview_dir` in the documented order** (it took the preview try-lock and then, inside `ensure_files_dir`, the job
  lock): under the lifecycle lock it now does, in this order: 503 stopping; `_refuse_cleanup_pending`; **the
  `server.preparing` check** (2.7: when set, release the lifecycle lock, wait on the Event outside every lock, loop);
  `files = self._ensure_dir(current)` (takes and releases the job lock, bounded); **then** the preview try-lock (busy:
  release the lifecycle lock, wait for the preview lock outside, loop; the directory made in this round stays, it is
  persisted). No sweep can rename the directory between the ensure and the try-lock: both happen under the lifecycle
  lock. Prepare (2.7) uses the same order. After this, every path takes the locks in the order lifecycle -> job ->
  preview -> pending, or holds fewer.
- **A local job's `delete` records before it forgets.** Today the pending record of a deleted local job's directory is
  written after the metadata is gone (`_finish_sweep` after J:625), and on a stalled writer it can be lost at exit; if
  that job was the only one using its output folder, nothing would point at the tombstone again (`sweep_orphans` only
  visits folders known from live jobs or pending entries, J:815-827). New order inside `delete` (lifecycle and job lock
  held, `timeout` as above): `_rename_away` -> **a pending record of what remains** (status `renamed` or `abandoned`:
  the tombstone; `failed`: the directory, with the 2.2 `files_id` rule; `gone`: nothing) written with
  `_pending_op(..., Deadline(LOCKED_IO_S))` -> only when that record landed (or nothing remains) the metadata
  directory is removed; when it did not land, `Busy("job %s is busy: its cleanup record could not be saved")` is
  raised, the job stays (its `job.json` still names the folder; the tombstone is found by `sweep_trash` at the next
  start) and DELETE answers 409 busy. After every lock is released the tombstone is removed (bounded) and a second
  `_pending_op` drops the entry when the removal finished. `_finish_sweep` is not called a second time for that
  record.
- A takeover in `_job_create` whose `ensure_files_dir` fails with `CallPending` (an abandoned `mkdir`) deletes the job
  through `store.delete(job["id"], locked=True, ...)` as today; `delete`'s `_rename_away` sees `mutation_pending` and
  records the path pending with `making=True` before the metadata goes (above), so the late `mkdir` is tracked. The
  Task 4 mkdir test pins it.

### 2.7 `POST run` of a local job: prepare, read and plan, commit

Upload jobs keep today's path unchanged. A local job:

1. **Prepare** (`Handler._run_prepare(job)`, a context manager): loop, like `_preview_dir`:
   - take the lifecycle lock; 503 when `worker._stopping`; `_refuse_cleanup_pending`; **409 `"a run of job %s is
     being prepared"` when `job in self.server.preparing`**; `current = self._load(job)`; 409 `"job %s is %s"` unless
     `detected`;
   - `files = store.ensure_files_dir(current, locked=True)` mapped as `_check_local_run` maps it today: `OutputGone` ->
     409 `str(exc)` ("output folder is gone or changed"), `Busy` -> 409 busy, other `OSError` -> 409 `"output folder:
     <reason>"` (**not** `_ensure_dir`'s 404: `test_local.py:477-484, 1760-1768` pin 409);
   - try every preview lock of the job with `_sweep_locks(current, 0.0)` (non-blocking). `TimeoutError(font_id)` means a
     bake holds it: release the lifecycle lock, wait for that font's lock outside, release it, loop;
   - `self.server.preparing[job] = threading.Event()`; `self.server.touched[job] = time.monotonic()` (as `_ensure_dir`
     does today; with `_sweep_idle` also skipping jobs in `server.preparing`, no idle sweep renames the directory
     between the preview locks' release and Commit); release the lifecycle lock; yield `(current, files)`, keeping the
     preview locks; the preview locks are released when the block ends.
   - **Marker lifetime, in code terms:** `_run_prepare` is `try: yield ... except BaseException: pop the marker, set its
     Event; raise` (it pops **only on an exception**; a normal exit leaves the marker for Commit). `_job_run` calls
     `_commit_run` right after the `with`; `_commit_run`'s body is one `try: ... finally: pop the marker, set its
     Event`, and that `try` starts **before** it takes the lifecycle lock, so a failure anywhere in Commit (the lock wait
     included) clears it.
   - Why the preview locks: `plan_steps` writes into the files directory (`os.makedirs(work_root)`, range copies). A
     sweep needs the preview locks to rename it, so none can move it mid-plan and let `makedirs` re-create an untracked
     directory. Every lifecycle-lock holder takes preview locks only by try-lock.
   - Why the marker: it keeps a second `POST run` and a preview bake out of the gap between the preview locks' release
     and the end of Commit (they would rewrite `work/` files the queued run reads). `_preview_dir`, under the lifecycle
     lock and **before** its ensure and its preview try-lock (2.6), treats `job in server.preparing` like a held preview
     lock: it releases the lifecycle lock, waits on that Event (outside every lock) and loops.
2. **Read and plan** (inside the `with`, no store lock): `_check_local_inputs(j, fonts, sources)` (the part of today's
   `_check_local_run` that reads volumes: `check_path` of every root, `_check_unchanged` of every input, free space),
   `settings.run_ready` (licence hashing), `settings.plan_steps` (planning, range copies), `_check_steps`,
   `_check_notes`. Same errors and statuses as today.
3. **Commit** (`Handler._commit_run(job, fingerprint, steps)`; the preview locks are released before it, the marker is
   still set; lifecycle lock held):
   - 503 stopping; `_refuse_cleanup_pending`; 409 `"output folder is gone or changed"` unless
     `store.files_current(self._load(job), Deadline(LOCKED_IO_S))`; 409 `"output folder is in use by job %s"` from the
     store-list check (moved here from `_check_local_run`);
   - then `self._update(job, commit, timeout=LOCKED_IO_S)` where **`commit(j)` runs under the job lock** and raises
     `_HttpError(409, "job %s is %s")` unless `j["state"] == "detected"`, and `_HttpError(409, "the job changed while
     the run was being prepared: run again")` when `_run_fingerprint(j) != fingerprint`; only then removes
     `<meta>/steps` and sets `state="queued", error=None, steps=steps, result=None`. (Checking against the `job.json`
     read under the job lock is what makes a concurrent `PUT settings` either land before - refused here - or after -
     refused by its own `detected` check - never be overwritten.)
   - `finally`: pop the marker and set its Event. Then `worker.enqueue` as today.
- `_run_fingerprint(j) -> str`: `json.dumps({k: j.get(k) for k in ("state", "roots", "scan_roots", "fonts",
  "settings", "output_dir", "output_id", "files_id")}, sort_keys=True)`. Taken from `current` right after Prepare.
- `Store.files_current(job, deadline) -> bool`: False while `mutation_pending(files)`; else `stat_id_bounded(output_dir)
  == output_id` and the bounded `lstat` of the files directory is a real directory whose `[st_dev, st_ino] ==
  files_id`; False on any `OSError`.
- `server.preparing = {}` is made in `make_server` beside `cleanup_pending`.
- The planned `work/` stays in the files directory when Commit refuses; it is the job's own and is swept with it.

---

## Global Constraints

- **`c/src` and `c/include` are unchanged.** G1 at the end of every task.
- **Gates at the end of every task, before its commit, in this order:**
  - G1 `git diff --exit-code 004a449 -- c/src c/include` -> exit 0, no output.
  - G2 `export TMP_DIR=$HOME/work/tmp/svf-fu-lifecycle; mkdir -p "$TMP_DIR"; TMPDIR=$TMP_DIR flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'`
    -> `OK (skipped=24)` and `Ran N tests`. **Before Task 1, run G2 once on `004a449` and record the observed base
    count B** (the card's logs say 997; a review counted 1023 by discovery). Each task states its expected N as B + the
    tests it adds; write the observed N in the commit body, with the reason when it differs. If a test fails only
    because of `TMPDIR`, rerun that test without it, and report it to the controller. Do not change it.
  - G3 `python3 -m unittest discover -s maker/test -p test_server.py -k test_page_js_tables_match_python` -> `OK`.
- **Scratch only under `$HOME/work/tmp`** (`TMP_DIR` above), never `/tmp`.
- **Hung-volume tests are deterministic and fast.** No real hung mount. Use the existing technique
  (`maker/test/test_local.py:1019-1047`, `:1058-1078`): patch the one call with a `Hang` wrapper that, **only for the
  path under test**, sets `entered` and waits on `release` (`release.wait(20)`), calling the real function otherwise.
  Register `self.addCleanup(release.set)` **before** starting anything. Shrink bounds with `mock.patch.object`
  (`jobs.LOCKED_IO_S`, `jobs.STOP_SWEEP_TOTAL_S`, `server.STARTUP_CLEANUP_S`, `jobs.REMOVE_BOUND_S`,
  `jobs.PENDING_FLOOR_S`). **Any call that can hang today runs on a daemon thread joined with a timeout** (also in tests
  whose "today" failure is a hang: never on the test thread). Each new test takes under 3 s.
- **Reading `pending-sweeps.json` in a test always polls** (helper `poll_pending(self, data_root, pred, timeout=2.0)`,
  0.05 s steps, returns the entries or fails with them), never reads once.
- **Counting threads:** count threads whose name is `svf-maker-stat` (or `svf-maker-pending`), never
  `threading.active_count()`.
- **Upload jobs behave exactly as before.** Every test that exists at `004a449` passes unmodified.
- **Constants keep their values:** `STARTUP_CLEANUP_S = 30.0` (server.py), `STOP_SWEEP_TOTAL_S = 8.0`,
  `STAT_TIMEOUT_S = 5.0`, `REMOVE_BOUND_S = 30.0`, `PREVIEW_TRY_S = 0.5` (jobs.py). `desktop/test/unit.test.js` reads the
  first two with `^NAME = ` regexes: keep them at column 0 in that form. New: `LOCKED_IO_S = 5.0`, `PENDING_FLOOR_S =
  0.5`, `PENDING_IDLE_S = 2.0`.
- **Lock order** lifecycle -> job lock -> preview locks -> pending lock, with no exception after Task 4. Any lock taken
  while the lifecycle lock is held is taken with a timeout (job lock) or a try-lock (preview).
- **Serialization:** tasks run in plan order; all touch `maker/jobs.py` and/or `maker/server.py`.
- **New tests go in a new file** `maker/test/test_local_bounds.py` (same header and `sys.path` block as
  `test_local.py:1-31`; `import functools`, `import jobs`, `import server`, `import settings`, `import localfx`,
  `import fixtures`). Helpers defined once at the top:
  - `class Hang`: `Hang(real, when)`; `__call__(*args, **kw)`: when `when(*args)` -> `self.entered.set();
    self.release.wait(20)`; then `return real(*args, **kw)`. `__get__(self, obj, objtype=None)`: `self if obj is None
    else functools.partial(self, obj)` (so it can replace a method such as `jobs.Store._read_pending`; `when` then gets
    the instance as its first argument). Attributes `entered`, `release` (`threading.Event`s).
  - `poll_pending(...)` above; `on_thread(fn) -> (thread, box)`: a daemon thread appending `fn()`'s result (or the
    exception) to `box`.
- **No bare `git stash`.** WIP commits only.

## Review Focus

1. **A slow but healthy network volume** (stat or mkdir taking 1-4 s) must still work: `LOCKED_IO_S` is 5 s per
   section. Expected: create, preview and run succeed. Covered by the default constant (tests shrink it only inside
   their own `mock.patch`); the reviewer checks no task lowers the default.
2. **Two requests on one hung folder** must not cost two threads, and a healthy concurrent caller must not fail just
   because another is in flight. Tests `test_a_second_request_on_a_hung_output_folder_shares_the_call` (Task 4) and
   `test_a_read_only_call_waits_for_the_one_in_flight` (Task 1).
3. **PUT settings racing POST run** must not queue a run planned from old settings: Commit's checks under the job lock.
   Test `test_a_run_whose_job_changed_while_preparing_is_refused` (Task 5).
4. **The process exits right after stop or start-up**: records reach the file on a healthy disk (floor + flush), and
   tombstones a lost record named are found at the next start. Tests
   `test_stop_lands_its_pending_records_before_returning` and
   `test_an_orphan_tombstone_is_swept_at_start_up` (Task 2).
5. **A rename that never returns** keeps the job usable for everything but its files directory, with a clear sentence
   and no new generation. Test `test_an_abandoned_rename_never_moves_a_later_generation` (Task 2).

---

### Task 0: Base count

- [ ] **Step 1:** Run G2 on `004a449` (clean worktree). Record `Ran B tests ... OK (skipped=24)` and send B to the
  controller. No commit.

### Task 1: The bounded primitives

**Files:**
- Modify: `maker/jobs.py:56-67` (`Deadline.capped`), `:102-143` (`_CALLS_IN_FLIGHT`, `bounded_call`, new helpers),
  `:426-446` (`Store.__init__`), `:639-704` (pending helpers; today's merge at J:686-696)
- Create: `maker/test/test_local_bounds.py` (header, helpers, class `BoundedPrimitivesTest(unittest.TestCase)` over a
  plain `jobs.Store(<tempfile.mkdtemp() under TMPDIR>)`)

**Interfaces:**
- Produces: `jobs.CallPending(OSError)`; `jobs.MUTATING_OPS`; `jobs.mutation_pending(path) -> bool`;
  `jobs.mutation_kind(path) -> str | None`; `jobs.rename_bounded(src, dst, timeout) -> None`;
  `jobs.Deadline.capped(seconds) -> Deadline`; `jobs.PENDING_FLOOR_S = 0.5`; `jobs.PENDING_IDLE_S = 2.0`;
  `jobs.Store._pending_op(fn, deadline=None) -> tuple[bool, object]` with `fn(entries: list[dict]) -> (new_entries |
  None, result)`; `jobs.Store.flush_pending(deadline=None) -> bool`;
  `jobs.Store._add_pending(job, files, reason, trash=None, generation=None, deadline=None, origin=None, making=False)
  -> bool` (`origin` stored as `"from"`; True when written in time; the merge rule of 2.2);
  `jobs.Store._add_pending_many(entries: list[dict], deadline=None) -> bool` (one `_pending_op` merging each entry with
  the same rule; the `log.md` lines as `_add_pending` writes them).

- [ ] **Step 1: Write the failing tests** in `BoundedPrimitivesTest`:
  - `test_rename_bounded_abandons_a_hung_rename_and_fences_the_path`: `Hang(os.rename, lambda s, d: s == src)` as
    `os.rename`; `with self.assertRaises(jobs.CallPending): jobs.rename_bounded(src, dst, 0.2)` in < 0.6 s;
    `assertTrue(jobs.mutation_pending(src))`, `assertEqual(jobs.mutation_kind(src), "rename")`,
    `assertTrue(jobs.mutation_pending(os.path.dirname(src)))`, `assertFalse(jobs.mutation_pending(src + "-other"))`;
    a second `rename_bounded(src, dst, 5)` raises `CallPending` in < 0.2 s; after `release.set()` and a poll (<= 2 s)
    `mutation_pending(src)` is False and `os.path.isdir(dst)`.
  - `test_a_read_only_call_waits_for_the_one_in_flight`: `jobs.stat_id` patched with a wrapper that sleeps 0.4 s for
    `p == d`; caller A `stat_id_bounded(d, 2)` on a thread, then (0.05 s later) caller B `stat_id_bounded(d, 2)` on the
    test thread returns the real id (today: `OSError` "call still pending" at once); the number of threads named
    `svf-maker-stat` grew by at most 1 over the count taken at the start of the test (measured while both wait).
  - `test_pending_op_returns_by_the_deadline_while_the_pending_lock_is_held`: hold `store._pending_lock`;
    `PENDING_FLOOR_S` patched to 0.1; `done, _ = store._pending_op(lambda e: (e + [{"path": "x"}], None),
    jobs.Deadline(0.3))`; `done is False`, elapsed < 0.8; release; `poll_pending` until `[{"path": "x"}]`.
  - `test_pending_op_returns_by_the_deadline_while_fsync_hangs`: `Hang(os.fsync, lambda fd: True)`; same shape.
  - `test_pending_op_with_an_expired_deadline_still_lands_on_a_healthy_disk`: `done, _ =
    store._pending_op(append_x, jobs.Deadline(0))` returns `True` (the floor) and the file holds the entry when it
    returns (read once: this is the one test that must not poll).
  - `test_pending_ops_keep_their_order_after_an_abandoned_one`: with the lock held, submit A (append `a`, deadline
    0.1) then B (append `b`, deadline 0.1); release; `poll_pending` until `[{"path": "a"}, {"path": "b"}]`.
  - `test_the_pending_writer_exits_when_idle_and_restarts`: `PENDING_IDLE_S` patched to 0.2; one op; after 0.6 s no
    `svf-maker-pending` thread; a second op succeeds.
  - `test_a_pending_rename_keeps_and_a_pending_mkdir_clears_the_recorded_generation`: `_add_pending(job, f, "x",
    generation=[1, 2])`; then `_add_pending(job, f, "y", generation=None)` with `job["files_id"] = None`: the entry's
    `files_id` is still `[1, 2]`; then `_add_pending(job, f, "z", making=True)`: the entry's `files_id` is None and
    `"making"` is true.
  - `test_records_after_a_stalled_one_do_not_wait_the_floor`: `Hang(os.fsync, lambda fd: True)`; `PENDING_FLOOR_S`
    0.5; three `_pending_op` calls with `jobs.Deadline(0)` in a row take < 0.8 s in all (only the first waits the
    floor); after release, `poll_pending` shows all three in order.
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_local_bounds.py -v`.
  Expected: errors `AttributeError: module 'jobs' has no attribute 'rename_bounded'` / `'CallPending'` / `'Store'
  object has no attribute '_pending_op'`; the read-only test FAILS with `OSError: call still pending`.
- [ ] **Step 3: Implement** per 2.1 and 2.3 in `maker/jobs.py`. `bounded_call`: the in-flight dict, read-only sharing,
  mutating at-once refusal, `CallPending` for both raises (J:113, J:128). In `Store.__init__`: `_pending_q`,
  `_pending_thread`, `_pending_thread_lock`, `_pending_unfinished`. `_pending_op`: request `(fn, Event, box)`;
  **under `_pending_thread_lock`**: note whether `_pending_unfinished` was 0 (the floor applies only then), increment
  it, `put` the request, and start a thread when `_pending_thread is None`. The thread: `get(timeout=PENDING_IDLE_S)`;
  on `queue.Empty` take `_pending_thread_lock`, return with `_pending_thread = None` only if the queue is still empty;
  after each request, decrement `_pending_unfinished` under the lock and set the Event. An exception in `fn` or the
  write is stored in the box and re-raised to a caller that waited (`print_exc()` otherwise). Rewrite `_add_pending`
  as a `_pending_op` whose `fn` does today's merge (J:686-696) plus the 2.2 rule and returns `(entries_or_None,
  fresh)`; the `log.md` line is written by the caller when `done and fresh`. `_add_pending_many` is the same merge
  over a list in one operation. Do **not** convert
  `retry_pending_sweeps`/`sweep_orphans` yet (Task 2).
- [ ] **Step 4: Run** Step 2's command. Expected: `Ran 9 tests ... OK`.
- [ ] **Step 5: Gates** G1, G2 (N = B + 9), G3.
- [ ] **Step 6: Commit** `git add maker/jobs.py maker/test/test_local_bounds.py && git commit` with message
  `maker local: bounded rename with a fence, shared read-only calls, one pending writer bounded by the caller's
  deadline (t_d1aba4b8)` and the `Co-Authored-By` trailer.

### Task 2: One deadline through rename, pending records, orphans and retries (H3b)

**Files:**
- Modify: `maker/jobs.py:473-498` (fence check only), `:605-637` (`delete`: capped deadline, record before forget,
  2.6), `:706-777` (`_rename_away`, `_finish_sweep`), `:779-807` (`sweep_files`: default deadline before the lifecycle
  lock), `:809-858` (`sweep_orphans`), `:878-984` (`retry_pending_sweeps`, no 50 ms floor), `:1098-1112`
  (`sweep_local_files`: try around `sweep_orphans`, `flush_pending`)
- Modify: `maker/server.py:101-118` (`_sweep_idle`: one deadline per pass, skips `server.preparing`; make
  `server.preparing = {}` in `make_server` here already, S:533), `:541-563` (`startup_cleanup`: `deadline=` to
  `retry_pending_sweeps`, try around `sweep_orphans`, `flush_pending(deadline)` at the end), `:1110-1118`
  (`_job_delete`: `jobs.Busy` -> 409 before its other handlers)
- Test: `maker/test/test_local_bounds.py`, class `SweepBoundsTest(localfx.LocalRunBase)`

**Interfaces:**
- Consumes: Task 1's primitives.
- Produces: `_rename_away` status `"abandoned"` (tuple shape unchanged: `(status, trash, reason, generation, files)`);
  `Store.retry_pending_sweeps(stat_timeout=None, deadline_s=None, deadline=None)`; `Store.sweep_orphans(deadline=None)`;
  `ensure_files_dir` raises `OutputGone` while `mutation_pending(files)`; `jobs.LOCKED_IO_S = 5.0`;
  `jobs.Busy(TimeoutError)` (raised here by `delete` when its record does not land; Task 4 adds the job-lock uses);
  `Store.sweep_files` with a default `Deadline(REMOVE_BOUND_S)`.

- [ ] **Step 1: Write the failing tests** (`fd = self.files_dir(jid)` of a `local_job()`; every call that can hang
  today runs through `on_thread` and is joined with a timeout):
  - `test_stop_returns_by_the_deadline_although_a_rename_hangs`: `Hang(os.rename, lambda s, d: s == fd)`;
    `STOP_SWEEP_TOTAL_S` 1.0; `sweep_local_files()` on a thread, `join(3)`; `assertFalse(t.is_alive())` (fails today:
    the rename blocks under the lifecycle lock); elapsed < 2.5; `poll_pending`: an entry with `path == fd` and one with
    `path.startswith(fd + ".trash-")` and `"from" == fd`.
  - `test_startup_returns_by_the_deadline_although_a_rename_hangs`: same hang; `self.release_lock()`;
    `server.STARTUP_CLEANUP_S` 1.0; `make_server(..., token=localfx.TOKEN)` on a thread, `join(4)`; a server was made,
    elapsed < 3.0, `jid in made[0].cleanup_pending`; stop it (`worker.stop()`, `server_close()`).
  - `test_an_abandoned_rename_never_moves_a_later_generation`: hang the rename; `store.sweep_files(job, bound=0.5)` on a
    thread is False within 2 s; `with self.assertRaises(jobs.OutputGone) as cm:
    store.ensure_files_dir(store.load(jid))`, `"still being moved or made"` in `str(cm.exception)`; `GET
    /api/jobs/<jid>/probe/<ttf>/16/1.json` answers 404 and `os.stat(fd).st_ino` is unchanged; `release.set()`; poll
    until `not jobs.mutation_pending(fd)`; `store.retry_pending_sweeps()`; no `.svf-maker-<jid>.trash-*` left in
    `self.out`; `ensure_files_dir` now makes a new directory whose identity is saved in `job.json`, and it still exists
    after a second `retry_pending_sweeps()`.
  - `test_retry_keeps_a_tombstone_entry_whose_rename_is_in_flight`: hang the rename, `sweep_files(job, bound=0.5)` on
    a thread; then `retry_pending_sweeps(deadline_s=1)` on a thread while it hangs (join 3): `poll_pending` shows both
    entries still there (today the tombstone entry is dropped as "confirmed gone").
  - `test_a_retry_whose_own_rename_is_abandoned_keeps_the_tombstone`: set the job not in use with `store.update(jid,
    lambda j: j.update(state="failed"))`; write a pending entry for `fd` with its recorded `files_id`; hang the rename;
    `retry_pending_sweeps(deadline_s=1.5)` on a thread (join 3); `poll_pending`: the `fd` entry and a tombstone entry
    with `"from" == fd` are both there (guards against counting a not-yet-landed tombstone as removed).
  - `test_stop_returns_by_the_deadline_while_the_pending_lock_is_held`: `shutil.rmtree` hangs for `fd + ".trash-"`
    paths (as `test_local.py:1030`), `store._pending_lock` held by the test; `STOP_SWEEP_TOTAL_S` 1.0,
    `PENDING_FLOOR_S` 0.1; `sweep_local_files()` thread `join(3)` not alive (fails today at J:688), elapsed < 2.5; after
    releasing both, `poll_pending` finds the tombstone entry.
  - `test_stop_returns_by_the_deadline_while_fsync_hangs`: `Hang(os.fsync, lambda fd_: True)` plus the hanging
    `rmtree`; same assertions.
  - `test_stop_lands_its_pending_records_before_returning`: hanging `rmtree` only, `STOP_SWEEP_TOTAL_S` 1.0: right after
    `sweep_local_files()` returns, a **single** read of the file holds the tombstone entry (the floor and the flush).
  - `test_orphan_sweep_returns_by_the_deadline_although_a_rename_hangs`: a done job makes `self.out` known; make
    `<out>/.svf-maker-0123456789ab`; hang `os.rename` for it; `store.sweep_orphans(jobs.Deadline(1.0))` on a thread,
    `join(3)` not alive (fails today at J:850).
  - `test_an_orphan_tombstone_is_swept_at_start_up`: a done job; make `<out>/.svf-maker-0123456789ab.trash-0badf00d/x`
    and `<out>/.svf-maker-<jid>.trash-0badf00e/x`; `release_lock()`; `make_server`; both tombstones are gone (today:
    the deleted job's one stays).
  - `test_an_orphan_removal_error_does_not_stop_the_sweep`: two orphan tombstones; `shutil.rmtree` raises
    `PermissionError` for the first only; `store.sweep_orphans(jobs.Deadline(2))` returns normally; the second is gone;
    `poll_pending` names the first.
  - `test_a_delete_whose_cleanup_record_cannot_be_saved_keeps_the_job`: A detected in `out2` (its only job);
    `Hang(os.fsync, lambda fd_: True)`; `LOCKED_IO_S` 0.3, `PENDING_FLOOR_S` 0.1; `DELETE /api/jobs/A` on a thread
    answers 409 with `"busy"` within 1.5 s (today: blocks in the synchronous fsync); `<data>/jobs/A/job.json` still
    exists; release; poll until the writer is idle; `DELETE` again answers 200.
  - `test_the_only_job_of_a_folder_leaves_a_findable_tombstone_when_deleted`: A done in `out2` (its only job), its
    directory re-made by a GET; `shutil.rmtree` hangs for `fd2 + ".trash-"` paths; `REMOVE_BOUND_S` 0.3; `DELETE` answers
    200; `poll_pending` names the tombstone with `output_dir == out2`; `release_lock()`; release the hang; a new
    `make_server` on the same data root leaves no `.svf-maker-A*` in `out2`. (Pins the record-before-forget order; it
    may pass today on a healthy disk.)
  - `test_an_idle_sweep_does_not_wait_beyond_its_deadline_for_the_lifecycle_lock`: A detected and idle; the test holds
    `store.lifecycle`; `RETRY_DEADLINE_S` 0.5; `server._sweep_idle(self.srv, now=time.monotonic() +
    server.LOCAL_IDLE_SWEEP_S + 5)` on a thread, `join(2)` not alive (today: `sweep_files` waits on the lock with no
    timeout, J:795-796).
  - `test_a_retry_starts_no_filesystem_call_after_its_deadline`: one pending entry for `fd` (job `failed`); a fake
    deadline object `Fake` with `over = False`, `remaining() -> 0.0 if over else 1.0`, `expired() -> over`; `jobs.stat_id`
    wrapped so that the call for `self.out` sets `fake.over = True` and returns the real id; `jobs.bounded_call` wrapped
    to record `fake.over` at each call's start; `store.retry_pending_sweeps(deadline=fake)`; `assertNotIn(True, starts)`
    (today: `left()`'s 50 ms floor lets the `lexists` call start after the deadline, J:905).
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_local_bounds.py -k SweepBoundsTest -v`.
  Expected: the hang tests FAIL on `assertFalse(t.is_alive())`; the in-flight-retry tests FAIL on the entry list; the
  orphan tests FAIL on `assertFalse(os.path.exists(tomb))` or the raised `PermissionError`; the "lands" test FAILS only
  if today's synchronous write is missing (it may pass today: keep it, it pins the floor).
- [ ] **Step 3: Implement** per 2.2-2.4:
  - `_rename_away`: locked deadline as in 2.4; `mutation_pending(files)` -> `failed` with `generation = None` when
    `mutation_kind(files) in ("mkdir", "chmod")`; rename via `rename_bounded`; `CallPending` -> `abandoned`.
  - `_finish_sweep`: `abandoned` -> one `_pending_op` that adds both entries; every `_add_pending` gets `deadline`.
  - `delete`: `_rename_away(job, Deadline(LOCKED_IO_S), check_active=False)`, then the record-before-forget order of
    2.6 (record with the same deadline; `Busy` and the metadata kept when it did not land), then after the locks the
    bounded removal and the dropping `_pending_op`.
  - `sweep_files`: the default deadline and the bounded lifecycle wait of 2.4; `_sweep_idle` as 2.4 says.
  - `retry_pending_sweeps`: no 50 ms floor; `dl.expired()` checked before each filesystem call (2.4).
  - `sweep_orphans` and `retry_pending_sweeps` exactly as 2.2 and 2.4 say (per-folder lifecycle sections, group-1 job
    id, tombstones dead by name, each removal on its own; skip-and-keep a missing tombstone whose rename is pending;
    `abandoned` tombstones are persisted but not removed in the same pass).
  - `ensure_files_dir`: the fence of 2.2 under the lifecycle lock, before `_make_files_dir`.
  - `sweep_local_files` and `startup_cleanup`: try around `sweep_orphans`, then `flush_pending(deadline)`.
- [ ] **Step 4: Run** Step 2's command, then `python3 -m unittest discover -s maker/test -p test_local.py -k Sweep`.
  Expected: OK for both (`test_local.py:1019-1048` reads the file once after `sweep_local_files`: the flush keeps it
  green).
- [ ] **Step 5: Gates** G1, G2 (N = B + 24), G3.
- [ ] **Step 6: Commit** `maker local: rename, pending records, orphan sweep and retries within the caller's deadline;
  an abandoned rename fences its path (t_d1aba4b8)` + trailer.

### Task 3: Start-up `sweep_trash` within the shared deadline (H3a)

**Files:**
- Modify: `maker/jobs.py:860-876` (`sweep_trash`), `maker/server.py:541-563` (`startup_cleanup`)
- Test: `maker/test/test_local_bounds.py`, class `StartupBoundsTest(localfx.LocalRunBase)`

**Interfaces:**
- Consumes: Task 1's `_add_pending(..., deadline)`, `bounded_call`, `fs_bounded`, `remove_tree_bounded`.
- Produces: `Store.sweep_trash(job, deadline: Deadline | None = None) -> bool`.

- [ ] **Step 1: Write the failing tests** (a `done_job()`; tombstones `fd + ".trash-%08x" % n` with one file each;
  `self.release_lock()`; `make_server` on a thread):
  - `test_startup_with_several_hung_tombstones_returns_by_the_single_deadline`: three tombstones, `shutil.rmtree`
    hangs for them, `REMOVE_BOUND_S` 0.8, `STARTUP_CLEANUP_S` 1.0; `join(5)`; server made; elapsed < 2.0 (today:
    about 2.4 s, one 0.8 s allowance per tombstone); `jid not in made[0].cleanup_pending`.
  - `test_startup_returns_by_the_deadline_although_listdir_hangs`: `Hang(os.listdir, lambda p: p == self.out)`;
    `STARTUP_CLEANUP_S` 1.0; `join(4)`; `assertFalse(t.is_alive())` (today: blocks at J:869); elapsed < 3.0.
  - `test_unfinished_tombstone_removals_at_start_up_are_all_recorded_pending`: three hung tombstones,
    `STARTUP_CLEANUP_S` 1.0, `REMOVE_BOUND_S` 0.8: `poll_pending` on the data root names all three (`files_id`
    None), including those never tried after the deadline; `jid not in made[0].cleanup_pending`; after `release.set()`
    the new server's `store.retry_pending_sweeps()` removes them and empties the file.
  - `test_a_tombstone_check_that_times_out_does_not_stop_the_others`: two tombstones; `Hang(os.path.islink, lambda p:
    p == first)` patched as `os.path.islink`; `LOCKED_IO_S`/`STAT_TIMEOUT_S` patched to 0.2;
    `store.sweep_trash(store.load(jid), jobs.Deadline(2))` on a thread returns within 3 s; the second is gone; the first
    is recorded pending.
  - `test_startup_returns_by_the_deadline_while_the_pending_file_hangs`: write one pending entry; patch
    `jobs.Store._read_pending` with `Hang(jobs.Store._read_pending, lambda self_: True)` (the `__get__` of the helper);
    `STARTUP_CLEANUP_S` 1.0, `PENDING_FLOOR_S` 0.1; `join(4)` not alive; elapsed < 3.0.
  - `test_startup_with_hung_tombstones_and_a_stalled_writer_returns_by_the_deadline`: three hung tombstones,
    `Hang(os.fsync, lambda fd_: True)`, `STARTUP_CLEANUP_S` 1.0, `REMOVE_BOUND_S` 0.3, `PENDING_FLOOR_S` left at 0.5:
    `join(4)` not alive and elapsed < 2.2 (`STARTUP_CLEANUP_S` + one floor + the flush's floor at most; a record per
    tombstone with a floor each would take longer, and today the fsync blocks for ever); after release, `poll_pending`
    names all three.
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_local_bounds.py -k StartupBoundsTest -v`.
  Expected: the first FAILS on the elapsed assertion, the second, fifth and sixth on `is_alive()`, the third on the
  missing entries, the fourth on `is_alive()`.
- [ ] **Step 3: Implement** `sweep_trash` per 2.4 (one `_add_pending_many` per call) and its call in
  `startup_cleanup`: `store.sweep_trash(job, deadline)` in its own `try`; its result never touches `cleanup_pending`.
- [ ] **Step 4: Run** Step 2's command. Expected: OK.
- [ ] **Step 5: Gates** G1, G2 (N = B + 30), G3.
- [ ] **Step 6: Commit** `maker local: start-up tombstone sweep within the start-up deadline, each tombstone on its
  own, unfinished removals recorded (t_d1aba4b8)` + trailer.

### Task 4: Bounded `ensure_files_dir`, bounded job-lock waits, the lock order restored (M5, part 1)

**Files:**
- Modify: `maker/jobs.py:473-518` (`ensure_files_dir`, `_make_files_dir`), `:573-579` (`update`), `:605-637`
  (`delete`), `Worker.retain` (J:1136-1155: `delete(..., timeout=LOCKED_IO_S)`)
- Modify: `maker/server.py:799-804` (`_update` gains `timeout`, maps `jobs.Busy`), `:909-926` (`_activate`), `:935-955`
  (`_claim_folder`), `:967-1001` (`_preview_dir`: ensure before the preview try-lock, 2.6), `:1010-1032`
  (`_ensure_dir`, `_files_dir_ready`: `Busy` before `OSError`), `:1422-1441` (`_job_settings`: previews cleared after
  `_update`, outside the job lock)
- Test: `maker/test/test_local_bounds.py`, class `LockedIoBoundsTest(localfx.LocalRunBase)`

**Interfaces:**
- Consumes: Task 2's `LOCKED_IO_S`, fence; Task 1's `Deadline.capped`.
- Produces (`jobs.Busy` comes from Task 2): `Store.update(job_id, fn, timeout=None)`; `Store.delete(job_id, locked=False,
  timeout=None)`; `Store.ensure_files_dir(job, locked=False, persist=True, deadline=None)` (job lock taken first,
  bounded); `Handler._update(job_id, fn, timeout=None)`.

- [ ] **Step 1: Write the failing tests.** Job A uses `self.out`; the healthy folder is `os.path.join(self.tmp,
  "healthy")` (made in the test). `LOCKED_IO_S` patched to 0.3 in each. "Create is quick" = `POST /api/jobs {"source":
  "local", "output_dir": healthy}` through `on_thread`, `join(2)`, not alive, status 200, elapsed < 1.0. Every request
  that can hang today goes through `on_thread`.
  - `test_a_create_is_not_held_by_a_hung_output_stat_in_ensure`: A is a done job (files directory swept);
    `Hang(jobs.stat_id, lambda p: p == self.out)` patched as `jobs.stat_id` **after** A is done; `GET
    /api/jobs/A/source/<dos>.svf` on a thread; wait `entered`; create is quick (today: blocks behind the lifecycle
    lock); the GET answers 404 within 1.0 s.
  - `test_a_create_is_not_held_by_a_hung_mkdir`: A is a done job; `Hang(os.mkdir, lambda p, *a: p == fd)`; the GET
    on a thread; wait `entered`; create is quick; the GET answers 404; **while the mkdir still hangs**:
    `store.sweep_files(store.load(A), bound=0.5)` (on a thread) is False, `poll_pending` shows an entry for `fd` with
    `files_id` None (although `job.json` still holds the swept run's `files_id`), `"making": true` and a busy reason,
    and `DELETE /api/jobs/A` answers 200; then `release.set()`; poll until
    `os.path.isdir(fd)` (the late mkdir landed) and `not jobs.mutation_pending(fd)`; `store.retry_pending_sweeps()`;
    no `.svf-maker-A*` is left (today: hang; and with the stale `files_id` the entry would be dropped as "newer
    generation" and the directory would leak).
  - `test_a_second_request_on_a_hung_output_folder_shares_the_call`: with the stat hang of the first test, two GETs on
    threads: both answer 404 within 1.0 s, and the threads named `svf-maker-stat` grew by at most 1 over the count
    taken before the first GET.
  - `test_a_lifecycle_holder_does_not_wait_for_a_held_job_lock`: A detected; the test holds `store.lock(A)`;
    `DELETE /api/jobs/A` answers 409 with `"busy"` in the error within 1.0 s (today: blocks); create is quick meanwhile.
  - `test_a_preview_and_a_settings_change_of_one_font_do_not_deadlock`: today's deadlock needs the preview GET to
    *make* a directory (only then does `ensure_files_dir` persist under the job lock). A detected and selected; sweep
    A's files directory first (`store.sweep_files(store.load(A), bound=2)` is True). Gate `server._changed_preview_fonts`
    with a `Hang(server._changed_preview_fonts, lambda *a: True)` (the PUT pauses inside its transition, holding A's job
    lock, before it would take a preview lock). Start `PUT settings` with the TTF's sizes `[16, 24]` on a thread; wait
    `entered`. Start `GET /api/jobs/A/preview/<ttf>/source.png` on a thread (it takes the lifecycle lock, makes the
    directory and wants the job lock); give it 0.3 s; release the gate. Expected after the fix: within 3 s no thread is
    alive, the PUT answers 200 and the GET answers 200 or 409 with `"busy"`. (Today: the GET holds the lifecycle lock and
    the preview lock and waits for the job lock; the PUT holds the job lock and waits for the preview lock: both threads
    stay alive.)
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_local_bounds.py -k LockedIoBoundsTest -v`.
  Expected: FAIL on the create's `assertFalse(t.is_alive())` / elapsed, on the DELETE thread still alive, on the
  deadlock test's alive threads, and on the mkdir test's leftover directory.
- [ ] **Step 3: Implement** per 2.6. `_make_files_dir(job, dl)` with `left = lambda: min(STAT_TIMEOUT_S,
  dl.remaining())`; `FileNotFoundError` from the bounded `lstat` still means "make it"; `CallPending` propagates as
  an `OSError`. `update`/`delete` with a timeout: `lock.acquire(timeout=...)` + `try/finally release`, `Busy` on
  failure. `_update(job_id, fn, timeout=None)` and `_job_delete` catch `jobs.Busy` -> `_HttpError(409, "job %s is busy;
  try again" % job_id)` before their other handlers; `_ensure_dir` / `_files_dir_ready` catch `jobs.Busy` before
  `OSError` the same way. `_preview_dir` in the order of 2.6 (stopping, cleanup pending, the `server.preparing` check -
  `server.preparing` exists since Task 2 and is filled from Task 5 on -, ensure, then the preview try-lock). `_job_settings`: the transition appends the changed font ids to a list; after `_update`
  returns, `for font_id in changed: with _preview_lock(job, font_id): _remove_preview(store, self._load(job),
  font_id)` (a 404 from `_load` - the job deleted meanwhile - ends the loop quietly).
- [ ] **Step 4: Run** Step 2's command, then `python3 -m unittest discover -s maker/test -p test_local.py` and
  `python3 -m unittest discover -s maker/test -p test_server.py` (W2 tests at `test_server.py:451-480` must stay
  green). Expected: OK for all three.
- [ ] **Step 5: Gates** G1, G2 (N = B + 35), G3.
- [ ] **Step 6: Commit** `maker local: files directory made with bounded calls under the job lock; no unbounded wait
  under the lifecycle lock; PUT settings clears previews outside the job lock (t_d1aba4b8)` + trailer.

### Task 5: Local `POST run` reads and plans outside the lifecycle lock (M5, part 2)

**Files:**
- Modify: `maker/server.py:1443-1507` (`_job_run` local branch, `_check_local_run` split), new `_run_prepare`,
  `_commit_run`, `_run_fingerprint` beside `_preview_dir` (S:966ff)
- Modify: `maker/jobs.py` (`Store.files_current`)
- Test: `maker/test/test_local_bounds.py`, class `RunPrepareTest(localfx.LocalRunBase)`

**Interfaces:**
- Consumes: Task 4's bounded `ensure_files_dir`, `Busy`, `_update(..., timeout)`, `LOCKED_IO_S`;
  `server._sweep_locks(job, timeout)` (exists, S:83).
- Produces: `Handler._run_prepare(job: str)` (context manager yielding `(current: dict, files_dir: str)`),
  `Handler._check_local_inputs(j, fonts, sources) -> None`, `Handler._commit_run(job: str, fingerprint: str, steps:
  list) -> dict`, `server._run_fingerprint(j: dict) -> str`, `server.preparing: dict[str, threading.Event]`,
  `jobs.Store.files_current(job: dict, deadline: Deadline) -> bool`. `_check_local_run` is removed.

- [ ] **Step 1: Write the failing tests.** A = `local_job()` + `self.select(A)`; healthy folder and "create is quick"
  as in Task 4. Helper `_run_on_thread(A)` = `on_thread` of `POST /api/jobs/A/run`.
  - `test_a_create_is_not_held_by_a_run_reading_a_hung_input`: `Hang(os.lstat, lambda p, *a: p ==
    os.path.join(self.roots[0], "Munjo.ttf"))` patched as `os.lstat` only after `select`; start the run; wait
    `entered`; create is quick (today: blocked behind the lifecycle lock); release; the run answers 200 and the job
    reaches `done` (`wait_done`).
  - `test_a_create_is_not_held_by_a_run_hashing_a_hung_licence`: make `_licence_sha` reachable: read the TTF's
    effective `licence_name` (`settings.effective(job["fonts"], job["settings"], self.ttf)["licence_name"]`) and write
    `<out>/svf/dos/<licence_name>` with the bytes of `<roots[0]>/OFL.txt` (equal bytes: `_licence_present_ok` hashes the
    chosen licence and the run is still allowed); `Hang(settings._licence_sha, lambda *a: True)` patched as
    `settings._licence_sha`; start the run; `assertTrue(hang.entered.wait(5))` (proves the call is reached); create is
    quick; release; the run answers 200.
  - `test_a_create_is_not_held_by_a_run_planning_on_a_hung_volume`: `Hang(settings.plan_steps, lambda *a, **k:
    True)` patched as `settings.plan_steps` (covers planning and the range copies `plan_steps` makes); same assertions.
  - `test_run_preparation_holds_no_lifecycle_lock`: the `plan_steps` hang; at `entered`,
    `assertFalse(self.srv.store.lifecycle.locked())`, every preview lock of A is held
    (`server._preview_lock(A, fid).locked()` for each font), `A in self.srv.preparing`, and
    `self.srv.touched[A]` was set after the run started.
  - `test_an_idle_sweep_skips_a_job_being_prepared`: the `plan_steps` hang; at `entered`, `server._sweep_idle(self.srv,
    now=time.monotonic() + server.LOCAL_IDLE_SWEEP_S + 5)` on a thread (join 3); `fd` still exists with the same
    `st_ino` and no pending entry names it; release; the run answers 200.
  - `test_a_run_whose_job_changed_while_preparing_is_refused`: the `plan_steps` hang; at `entered`, `PUT settings`
    with `st["fonts"][self.ttf]["sizes"] = [16, 24]` on a thread; poll `GET /api/jobs/A` (<= 2 s) until the TTF's sizes
    are `[16, 24]` (the PUT has saved; it may still wait for a preview lock to clear previews); release; the run answers
    409 with `"changed while the run was being prepared"`; the PUT answers 200; `job(A)["state"] == "detected"`; a
    second `POST run` answers 200.
  - `test_a_second_run_during_preparation_is_refused`: the `plan_steps` hang; at `entered`, a second `POST run`
    answers 409 `"being prepared"` within 1 s; release; the first answers 200.
  - `test_a_run_whose_files_directory_was_replaced_while_preparing_is_refused`: the `plan_steps` hang; at `entered`,
    `os.rename(fd, fd + "-moved")` and `os.mkdir(fd)`; release; the run answers 409 `"output folder is gone or
    changed"`; state `detected`.
  - `test_a_delete_during_run_preparation_leaves_no_files_directory`: the `plan_steps` hang; at `entered`, `DELETE
    /api/jobs/A` answers 200 (its rename is refused: preview locks busy, recorded pending); release; the run answers
    404 or 409; `store.retry_pending_sweeps()`; no `.svf-maker-A*` in `self.out`.
  - `test_a_run_on_a_gone_output_folder_still_answers_409`: remove `self.out` after `select`; `POST run` answers 409
    `"output folder is gone or changed"` (pins today's status through Prepare).
- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p test_local_bounds.py -k RunPrepareTest -v`.
  Expected: the three "create is quick" tests and `..._holds_no_lifecycle_lock` FAIL (thread alive / `locked()` True /
  `AttributeError: preparing`); the changed-job test FAILS (today the PUT cannot save while the run holds the job lock;
  the poll times out); the second-run test FAILS (today 409 `"job ... is queued"` arrives only after the first; the 1 s
  bound fails). The replaced-directory, delete and gone-folder tests may pass today: keep them, they pin the new
  sections. Record in the commit body which failed first.
- [ ] **Step 3: Implement** per 2.7. `_job_run`: upload branch unchanged; local branch:
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
  The marker's lifetime exactly as 2.7 says: `_run_prepare` pops it only in `except BaseException` (then re-raises);
  `_commit_run` wraps its whole body, the lifecycle-lock wait included, in `try/finally` that pops it and sets its
  Event. Same error texts and statuses as today for every check that moved.
- [ ] **Step 4: Run** Step 2's command, then `python3 -m unittest discover -s maker/test -p test_local.py` and
  `python3 -m unittest discover -s maker/test -p test_server.py`. Expected: OK for all three.
- [ ] **Step 5: Gates** G1, G2 (N = B + 45), G3.
- [ ] **Step 6: Commit** `maker local: POST run prepares outside the lifecycle lock under the job's preview locks and
  commits under the job lock after revalidating the job and its files directory (t_d1aba4b8)` + trailer.

### Task 6: Documents, desktop gates, closing

**Files:**
- Modify: `docs/maker-audit.md` section 8 ("Accepted trade-off (lifecycle lock)" and "Known limits of the cleanup"):
  replace both with "Bounded lifecycle (t_d1aba4b8)": the bounds as 2.5 states them (per section, with the start-up /
  stop exception and the data-root assumption), the fence rule and its accepted limit (a never-returning rename keeps
  that one directory unavailable until restart), the pending floor and flush, the run's three sections, the restored
  lock order (`PUT settings` clears previews outside the job lock), and the test names of Tasks 1-5 as evidence rows.
- Modify: `maker/jobs.py` `Store.__init__` comment (J:439-443): the lifecycle lock is never held across a read of an
  input, planning or an unbounded call; every lock taken under it is taken with a timeout or a try-lock; no job-lock
  holder waits for a preview lock.
- Modify: `docs/superpowers/specs/2026-11-04-maker-local-mode-design.md` 8.3: one added paragraph after the lifecycle
  list pointing to the audit section (the spec's sentence "the start-up sweep runs on a thread after the bind" is
  already historical; say so there, do not rewrite the list).

- [ ] **Step 1: Write the document changes** above.
- [ ] **Step 2: Gates** G1, G2 (N = B + 45), G3, and the desktop ones (the sidecar's local mode changed in its run
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
really end within `STARTUP_CLEANUP_S` / `STOP_SWEEP_TOTAL_S` plus the pending floor and flush (at most about 1.5 s),
inside the margins of `desktop/lib/budget.js` (HANDSHAKE_S 75 s, STOP_WAIT_S 45 s): no budget change; (b) `POST run`
can answer new 409s ("the job changed while the run was being prepared: run again", "a run of job ... is being
prepared", "job ... is busy; try again") and previews a new 404 sentence while a fenced rename is in flight; the page
shows any 409/404 error text generically; automatic retry is a separate card (controller); (c) one pending-writer
thread per server while it has work. The frozen sidecar needs no spec change (no new third-party import). G4 and G5
run once, in Task 6.

## Self-review notes

- Card coverage: sweep_trash deadline (Task 3), rename under locks (Tasks 1-2), pending-lock waits and fsync (Tasks
  1-2, start-up variant Task 3), ensure_files_dir bounded (Task 4), run's input stats / licence hashing / planning /
  range copies outside the lock (Task 5; range copies are inside `plan_steps`, so the planning test covers them),
  "hung volume while a job in a healthy folder is created" (Tasks 4 and 5), suite green (G2 every task).
- Not covered on purpose: the data root itself on a hung volume (`job.json`, `Store.list`, `log.md`): the app's own
  directory on the local disk; the pending file's writes are bounded for callers anyway.

---

## Review dispositions (plan reviews of fb273ab)

Opus (Claude) and agy Argon, both APPROVE WITH CHANGES. Argon's summary item 1 (`DESKTOP_READY_BUDGET_MS`) refers to
another plan and does not apply here.

| Finding | Disposition |
|---|---|
| Opus H1 / Argon F3: Commit checks outside the job lock; PUT settings overwritten | Fixed: 2.7 step 3 (state and fingerprint checked inside the `_update` transition; files and in-use checks under the lifecycle lock); Task 5 test rewritten to wait until the PUT has saved |
| Opus H2: expired deadline waits 0 s; records lost at exit; tests read without polling | Fixed: 2.3 (`PENDING_FLOOR_S` 0.5 s floor, `flush_pending` at the end of stop and start-up); Global Constraints (tests poll); tests `..._still_lands_on_a_healthy_disk` (Task 1), `test_stop_lands_its_pending_records_before_returning` (Task 2) |
| Opus H3 / Argon F4: stale `files_id` recorded while a mkdir is pending; an abandoned rename's `files_id` overwritten by None | Fixed: 2.2 (`generation None` for a pending mkdir/chmod; None never overwrites a recorded id), 2.6 (`ensure_files_dir` takes the job lock first, so `Busy` means nothing was made); tests `test_a_none_files_id_never_overwrites_a_recorded_generation` (Task 1), `test_a_create_is_not_held_by_a_hung_mkdir` reordered as Argon asks (DELETE before release) (Task 4) |
| Opus M1: Prepare would answer 404 where run answers 409 today | Fixed: 2.7 step 1 maps as `_check_local_run` does; test `test_a_run_on_a_gone_output_folder_still_answers_409` (Task 5) |
| Opus M2: the licence-hash test never reaches `_licence_sha` | Fixed: Task 5 test pre-writes `<out>/svf/dos/<licence_name>` with equal bytes and asserts `entered` |
| Opus M3: `Hang` over `Store._read_pending` is not a method | Fixed: `Hang.__get__` (Global Constraints) |
| Opus M4 / Argon F2: lock-order inversion (`_preview_dir` vs `_job_settings`), `Busy` mapped to 404 | Fixed: 2.6 (`_job_settings` clears previews after `_update`, outside the job lock; `Busy` caught before `OSError` -> 409); test `test_a_preview_and_a_settings_change_of_one_font_do_not_deadlock` (Task 4) |
| Opus M5 / Argon F3.6: second run or a bake in the gap before Commit | Fixed: 2.7 (`server.preparing` marker: a second Prepare answers 409, `_preview_dir` waits on it); test `test_a_second_run_during_preparation_is_refused` (Task 5) |
| Opus M6: removal errors escape the widened sweeps | Fixed: 2.4 (each removal on its own in `sweep_orphans` and `sweep_trash`; both wrapped in `startup_cleanup` and `sweep_local_files`); test `test_an_orphan_removal_error_does_not_stop_the_sweep` (Task 2) |
| Opus M7: `LOCKED_IO_S` claim | Fixed: 2.5 states it per section with the start-up/stop exception; `_rename_away` capped at `LOCKED_IO_S` for request/idle callers; `sweep_orphans` takes the lifecycle lock per folder (2.4); audit wording in Task 6 |
| Opus L1: in-flight key makes healthy callers fail at once | Fixed: 2.1 (read-only calls share the in-flight call within their own timeout; mutating ones still refuse at once); test `test_a_read_only_call_waits_for_the_one_in_flight` (Task 1); Task 4 test renamed `..._shares_the_call` |
| Opus L2: Commit's check while a mutation is pending | Fixed: `files_current` is False while `mutation_pending(files)` (2.7) |
| Opus L3: count threads by name | Fixed: Global Constraints and the thread-count tests |
| Opus L4: check "live job's tombstone untouched by sweep_orphans" directly | Superseded by Argon F6 (controller: fold in): tombstones are dead by name and `sweep_orphans` removes them whatever the job; `test_an_orphan_tombstone_is_swept_at_start_up` asserts both the deleted and the live job's tombstone go |
| Opus L5: pending writer threads accumulate | Fixed: 2.3 (exits when idle, restarts lazily); test `test_the_pending_writer_exits_when_idle_and_restarts` |
| Opus L6: "fails today" tests on the test thread block 20 s | Fixed: Global Constraints (every call that can hang today runs on a thread with a join); tests updated |
| Opus L7: PUT settings change not exact | Fixed: TTF `sizes = [16, 24]` (Tasks 4 and 5) |
| Opus: Task 1 line refs wrong | Fixed: `bounded_call` J:106, raises J:113/J:128, merge J:686-696, lock-order comment J:439-443 |
| Opus: base count 1023 vs 997 | Fixed: Task 0 records the observed base B; every N is B + added tests |
| Argon F1: a just-abandoned tombstone removed in the same pass; a missing tombstone with a pending rename falls through to `isdir` | Fixed: 2.2 (skip-and-keep before `islink`/`isdir`; `abandoned` tombstones not removed in the same pass); test `test_a_retry_whose_own_rename_is_abandoned_keeps_the_tombstone` (Task 2) |
| Argon F2.6: `_job_create` deletes after a `CallPending` and leaves the mkdir unrecorded | Fixed differently: `delete`'s own `_rename_away` sees `mutation_pending` and records the path pending with `files_id None` (2.6 last bullet); no separate `sweep_files` call needed; the mkdir test (Task 4) covers the record |
| Argon F2 (option: ensure before taking preview locks) | Not taken: the inversion is removed at its other end (`_job_settings`), which restores the documented order everywhere |
| Argon F5: `sweep_trash` checks outside the per-entry `try`; done job marked `cleanup_pending` | Fixed: 2.4 (per-tombstone `try`, remaining names recorded after expiry, result never touches `cleanup_pending`); tests `test_a_tombstone_check_that_times_out_does_not_stop_the_others`, `..._are_all_recorded_pending` (Task 3) |
| Argon F6: wrong job-id slice for tombstone names; tombstones dead without the `job.json` check | Fixed: 2.4 (regex group 1; tombstones removed whatever the job) |

## Review dispositions, round 2 (re-reviews of d410d53; SOL's review of fb273ab checked against d410d53)

agy Argon: APPROVE. Opus: APPROVE WITH CHANGES (N1-N9). SOL (reviewed the old plan fb273ab): REJECT; each item
re-checked against d410d53.

| Finding | Disposition |
|---|---|
| Opus N1: a stalled writer makes every record wait the floor; N tombstones cost N x 0.5 s | Fixed: 2.3 (no floor while an earlier operation is unfinished, `_pending_unfinished`; one `_add_pending_many` per `sweep_trash` / `sweep_orphans` call; budget text corrected); tests `test_records_after_a_stalled_one_do_not_wait_the_floor` (Task 1), `test_startup_with_hung_tombstones_and_a_stalled_writer_returns_by_the_deadline` (Task 3) |
| Opus N2: the deadlock test passes today and expects the wrong result | Fixed: Task 4 test rewritten as described (directory swept first, PUT paused inside its transition on `_changed_preview_fonts`, GET makes the directory; after the fix no thread alive, PUT 200, GET 200 or 409 busy) |
| Opus N3: "None never overwrites" brings back the H3 leak when an old entry is pending and a new mkdir is abandoned | Fixed: 2.2 (`making=True` for a pending mkdir/chmod replaces the recorded id with None and marks `"making"`; a pending rename keeps it); Task 1 test renamed `test_a_pending_rename_keeps_and_a_pending_mkdir_clears_the_recorded_generation`; Task 4 mkdir test asserts None although `job.json` holds the swept run's id |
| Opus N4: writer idle-exit race | Fixed: 2.3 and Task 1 Step 3 (enqueue and check/start under `_pending_thread_lock`; the exiting thread re-checks the queue under the same lock before clearing `_pending_thread`) |
| Opus N5: `_preview_dir` still takes preview then job lock | Fixed: 2.6 (`_preview_dir` reordered: preparing check, ensure, then the preview try-lock, all under the lifecycle lock); 2.7 states the marker check comes before the try-lock; Task 4 Files/Step 3 |
| Opus N6: Prepare does not refresh `touched`; idle sweep can rename in the gap | Fixed: 2.7 (Prepare sets `server.touched[job]`) and 2.4 (`_sweep_idle` skips `server.preparing`); tests in `test_run_preparation_holds_no_lifecycle_lock` and new `test_an_idle_sweep_skips_a_job_being_prepared` (Task 5) |
| Opus N7: marker lifetime in code terms | Fixed: 2.7 and Task 5 Step 3 (`_run_prepare` pops only in `except BaseException`; `_commit_run`'s `try/finally` covers the lifecycle-lock wait) |
| Opus N8: thread count "for d" impossible | Fixed: count the delta of `svf-maker-stat` threads from before the test (Tasks 1 and 4) |
| Opus N9: a shared read-only answer may predate the waiter's section | Accepted, no change: a stat answer a few ms old is as good as one taken under the lock was before; the commit and rename steps re-check identities |
| SOL High: a deleted job's tombstone is unrecoverable when the pending record is lost and the job was the folder's only user | Fixed: 2.6 "record before forget" (`delete` writes the pending record within its bound before removing the metadata; when it does not land, the job stays and DELETE answers 409 busy); tests `test_a_delete_whose_cleanup_record_cannot_be_saved_keeps_the_job` and `test_the_only_job_of_a_folder_leaves_a_findable_tombstone_when_deleted` (Task 2), the latter with the deleted job as the folder's only user |
| SOL Medium: Prepare preview-then-job vs settings job-then-preview | Already fixed in d410d53 (`_job_settings` clears previews outside the job lock, 2.6); round 2 also reorders `_preview_dir` and keeps Prepare's ensure before its try-locks, so no path inverts the order |
| SOL Medium: idle `sweep_files` has no deadline and waits for the lifecycle lock without a timeout | Still held in d410d53 (the cap bounded only the locked step). Fixed: 2.4 (`sweep_files` makes its default `Deadline(REMOVE_BOUND_S)` before the lock and waits with a timeout; `_sweep_idle` passes one `Deadline(RETRY_DEADLINE_S)` per pass); test `test_an_idle_sweep_does_not_wait_beyond_its_deadline_for_the_lifecycle_lock` (Task 2) |
| SOL Low: the retry's 50 ms floor lets calls run past the deadline | Still held in d410d53. Fixed: 2.4 (no floor; `dl.expired()` checked before each filesystem call); test `test_a_retry_starts_no_filesystem_call_after_its_deadline` with a scripted deadline object (Task 2) |

Test counts after round 2: Task 1 +9, Task 2 +15, Task 3 +6, Task 4 +5, Task 5 +10: N = B + 45 at the end.
