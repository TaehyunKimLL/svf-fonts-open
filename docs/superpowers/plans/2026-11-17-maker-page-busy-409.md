# Maker page: retry or explain the busy / being-prepared 409s - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close card t_39c9fb52: every 409 that t_d1aba4b8 (97f7ce3) added ("job X is busy; try again", "a run of job X
is being prepared[; try again]", "job X is busy: a preview is being made; try again", "the job changed while the run was
being prepared: run again"), plus "job X: the previous run is finishing; try again in a moment", gets a page behaviour -
a bounded automatic retry, an explicit "Try again" control, or a reload - covered by a page test; every other error
stays as today.

**Architecture:** The server tags the retryable answers with one machine-readable field, `"busy": "<kind>"`
(`lock` | `preparing` | `preview`), through one helper `_busy()`, and the "changed" answer with `"stale": true`; the
English texts are unchanged. The page decides from those fields only: one pure policy function in `pagelib.js`, used by
`api()` (JSON calls: retry line in `#notice`, then a "Try again" button) and by one `fetchBusy()` helper for the preview
GETs that do not go through `api()` (silent bounded retry). A retry only ever repeats the one request that got a busy
answer, never the whole action, never after a network error (no answer = outcome unknown), and never after the user has
started anything else (a notice epoch cancels a sleeping retry).

**Tech Stack:** Python 3 `unittest` (`maker/server.py`, `maker/test/test_local_bounds.py`, `test_local.py`), ES module
page (`maker/static/maker.js`, `pagelib.js`, `index.html`, `style.css`), headless Chrome via `maker/test/pagedrive.mjs`
(`--preload` fetch stub), node for `test_pagelib.py`.

**Spec:** card t_39c9fb52; `docs/maker-audit.md` section 8, bullet "Client-visible changes (accepted)" (it says "automatic
retry of these 409s is a separate card": this one); `maker/server.py` at 084ca27 for the exact texts; the controller's
answers of 2026-11-17 (recorded under "Decisions taken" at the end).

## Global Constraints

- The implementer changes `maker/server.py`, `maker/static/{maker.js,pagelib.js,index.html,style.css}`, tests and docs.
  Nothing under `c/`, `tools/`, `desktop/`, `maker/jobs.py`.
- The 409 texts stay byte-identical (existing tests `assertIn` them). Only body keys are added (`busy`, `stale`).
- Non-busy, non-stale errors (400, 404, other 409s such as "output folder is in use", "cleanup pending ...", "job X is
  queued", "an upload is in flight", the create-path busy answers of `_job_create` ~940-949) keep today's page behaviour
  exactly: one notice line `METHOD path: HTTP status: error`, no button, no retry, no reload.
- The CSP allows no inline style (`test_sync_caveat_is_shown` asserts no ` style="` in `index.html`): the button is
  styled in `style.css`.
- Scratch only under `$HOME/work/tmp`: `export TMPDIR=$HOME/work/tmp/svf-busy409` (`mkdir -p` it) for every command.
- Commit messages end with `(t_39c9fb52)` and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push.

### Gates (end of every task)

- **G1** `git diff --exit-code 587dfb5 -- c/src c/include` - exit 0.
- **G2** `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'`
  - `OK`; at 084ca27 `Ran 1103 ... OK (skipped=25)`. Expected: after Task 1 1104; after Task 2 1104 + 2 (pagelib) + 8
  (page) = 1114; after Task 3 1114 + 2 = 1116; skipped stays 25 (host with Chrome, node and the built module).
- **G3** `python3 -m unittest discover -s maker/test -p test_server.py -k test_page_js_tables_match_python` - `OK`.
- **Desktop.** The shell itself calls none of the affected routes (only `GET /api/jobs/<id>` in `maker:open-output` and
  `GET /api/caps`; neither answers busy) and `desktop/lib/budget.js` is untouched, so G4 (`desktop/test/unit.test.js`)
  is not needed. The e2e drives the page's `api()` through detect-local and run, so **G5 runs once, in Task 3**:
  `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy bash desktop/test/run-e2e.sh` -> both passes green.

## Decision table (per answer, per route)

"Auto" = `api()`/`fetchBusy()` repeats the identical request after 500, 1000, 2000 ms (at most 3 repeats, 4 sends) and
starts no repeat once 15 s have passed since the first send, nor once the notice epoch has moved (below).

| Answer (body field) | Route (handler) | Page behaviour |
|---|---|---|
| "job X is busy; try again" (`busy: lock`) | `DELETE /api/jobs/X` (`_job_delete`) | Auto; then "Try again" |
| same (`busy: lock`) | local `POST /api/jobs`: holder busy in `_claim_folder` (keeps `"job"`) | Auto; then "Try again" |
| same, **untagged** | local `POST /api/jobs`: ensure busy / cleanup of the just-created job busy (`_job_create` ~945-949) | As today (no field): text only |
| same (`busy: lock`) | `PUT sources`, `POST detect` (`_activate`, `_files_dir_ready`, `_update(timeout)`) | Auto; then "Try again" |
| "job X: the previous run is finishing; try again in a moment" (`busy: lock`) | `PUT sources`, `POST detect` (`_activate` ~969) | Auto; then "Try again" |
| "job X is busy; try again" (`busy: lock`) | `POST run` (prepare ensure ~1601, commit `_update(timeout)`) | Auto; then "Try again" |
| same (`busy: lock`) | `GET preview/<f>/source.png`, `GET source/<f>.svf`, `GET probe/...` (`_preview_dir` -> `_ensure_dir`) | Auto, silent (`fetchBusy`); exhausted = today's failure display |
| "job X is busy: a preview is being made; try again" (`busy: preview`) | `POST run` (`_run_prepare` ~1619) | Auto; then "Try again" |
| "a run of job X is being prepared; try again" (`busy: preparing`) | the three preview GETs (`_preview_dir` ~1049) | Auto, silent; exhausted = today's failure display |
| "a run of job X is being prepared" (`busy: preparing`) | `POST run` (`_run_prepare` ~1592) | **No auto retry.** Notice + "Try again" at once, and the page follows the other run: `GET` the job every 1 s for up to 15 s until its state leaves `detected`, then render it and `startPolling()` when `queued`/`running` |
| "the job changed while the run was being prepared: run again" (`stale: true`) | `POST run` (`_commit_run` ~1651) | No retry, no button; today's notice, then `reload()` so the page shows the settings that changed |

Rule in one line (the pure policy): retry automatically unless `kind === "preparing"` and the method is not `GET`.

**What a busy answer leaves behind (precision).** Nothing is *submitted* twice: no busy answer is raised after its
request queued a run, answered a job id, or saved settings/sources, and the page repeats a request only on a busy
answer. But some busy answers come after the request already changed state, and a repeat sees that state:
- `DELETE`: `jobs.py` ~793-798 - `_rename_away` has moved the files directory away before the cleanup record fails
  (`Busy`); the job stays, and the repeat finishes the delete.
- `POST detect`: `_stamp_local` appends the detection-error notes to `log.md` before `_activate`; a repeated detect
  appends them again (duplicate log lines, nothing else).
- `PUT sources` / `POST detect` / takeover create: `_claim_folder` may already have deleted an *idle* competing job
  (taken over) before a later holder or `_update` answers busy; the takeover of an idle job is allowed anyway and a
  repeat finds the folder already free.
- Local create with ensure / cleanup busy (`_job_create` ~945-949): the request created a job (and may leave it as an
  orphan, accepted in the audit). **Not retryable: untagged**, shown as today.

**"Try again" control** (`#notice-retry`, a `<button>` right after `#notice`): shown with the usual notice text when the
bound is exhausted or the policy says no auto retry. It re-sends only the identical request (same method, path, body; a
`Blob` body is re-sendable) with a fresh bound; on success the awaiting caller continues as if the first send had
succeeded (so `detectLocal` goes on to `PUT sources` and `detect`, never re-creating). Click handler order:
`const w = busyWait; busyWait = null; hide the button; setNoticeQuiet(""); w.resolve(api(method, path, body, opts));`
so the re-entered call's own retry line does not reject itself and the old "HTTP 409" text is gone once it succeeds.
One button: a second exhausted call replaces (and rejects) the first.

**Cancellation (notice epoch).** Module state `noticeEpoch` (integer). The public `notice()` and `clearNotice()` bump
it, hide the button and reject a waiting `busyWait` with its original error. `api()` writes its own lines (retry line,
exhausted message) through an internal `setNoticeQuiet(text)` that does not bump. `api()` records `noticeEpoch` when it
writes its first retry line; after every sleep and before every resend, if the epoch moved, it rejects with the
original error and sends nothing. Every action starts with `clearNotice()`, so Save, a second Detect click or Delete
during a sleeping retry cancels it. (A background `notice()`, e.g. from `renderJobs`, cancels it too; accepted: the
user then sees that other message and acts again.)

**While retrying**, `#notice` shows `METHOD path: HTTP 409: <server text> (retrying N/3)`. On a successful retry `api()`
clears the notice (quietly) only if the epoch has not moved.

## Review Focus

1. A network error or non-JSON 409 during a retry: no further retry (outcome unknown), today's message. Covered by
   `test_busy_policy_never_retries_...` ("no kind -> null"); `api()` reads `kind` only from a parsed JSON body.
2. An action started while a retry sleeps must cancel it: `test_an_action_during_a_sleeping_retry_cancels_it`.
3. Two concurrent busy calls: one `busyWait` slot; the replaced call rejects.
4. `POST run` "being prepared" never repeated automatically, and the page follows the other run:
   `test_a_run_being_prepared_is_not_retried_and_follows_the_other_run`.
5. Upload mode: the server never sends `busy`/`stale` there; existing `PageDomTest` stay green in G2.

---

### Task 1: Server: tag the retryable answers with `"busy": kind`, the changed run with `"stale": true`

**Files:**
- Modify: `maker/server.py` (add `_busy` beside `_HttpError` ~line 164; replace the raises at ~847, 969, 1001, 1049,
  1074, 1089, 1176, 1592, 1601, 1619; add `{"stale": True}` at ~1651; leave ~947 and ~949 as they are)
- Test: `maker/test/test_local_bounds.py` (amend 10 tests, add 1), `maker/test/test_local.py` (amend 1)

**Interfaces:**
- Produces: `_busy(kind: str, message: str, extra: dict | None = None) -> _HttpError` returning
  `_HttpError(409, message, dict(extra or {}, busy=kind))`; `kind` in `("lock", "preparing", "preview")`. Callers
  `raise _busy(...)`. Wire bodies: `{"error": <unchanged>, "busy": kind[, "job": id]}`;
  `{"error": "the job changed while the run was being prepared: run again", "stale": true}`.

- [ ] **Step 1: Write the failing assertions.**
  `test_local_bounds.py` - assert `body.get("busy") == K`:
  `test_a_delete_whose_cleanup_record_cannot_be_saved_keeps_the_job` (`lock`),
  `test_a_takeover_with_a_busy_holder_answers_busy_naming_it` (`lock`; `job` still the holder),
  `test_ensure_with_a_held_job_lock_is_busy_and_makes_nothing` (detect answer `body2`: `lock`),
  `test_a_second_run_during_preparation_is_refused` (`preparing`),
  `test_a_preview_waits_a_bounded_time_for_a_run_being_prepared` (`preparing`),
  `test_a_run_waits_a_bounded_time_for_a_preview_lock` (`preview`).
  Assert `"busy" not in body` (create path stays untagged):
  `test_a_failed_takeover_that_cannot_record_answers_409_busy_and_keeps_the_job`,
  `test_a_create_whose_ensure_is_busy_answers_busy_not_400`.
  Assert `body.get("stale") is True`: `test_a_run_whose_job_changed_while_preparing_is_refused`,
  `test_a_job_changed_after_the_preview_locks_went_is_refused_inside_the_job_lock`.
  `test_local.py` `test_a_rerun_request_in_the_completion_window_is_refused_and_the_next_run_keeps_its_directory`
  (~1489): `self.assertEqual(answer.get("busy"), "lock")` for both detect and sources.
  New, in `test_local_bounds.py`, class `BusyFieldTest(unittest.TestCase)`,
  `test_every_busy_409_goes_through_busy_helper`: reading `server.py` line by line, every line matching
  `r'_HttpError\(409,\s*"(?:[^"]*is busy|a run of job|job %s: the previous run is finishing)'` must carry the comment
  marker `# untagged: a job was created` and there are exactly 2 such lines (~947, ~949); `raise _busy(` occurs at
  least 12 times.
- [ ] **Step 2: Run, expect FAIL**
  `python3 -m unittest discover -s maker/test -p 'test_local*.py'` -> the 7 tagged-field and 2 stale assertions fail
  (`None != 'lock'`, `None is not True`), `test_local` fails on `None != 'lock'`, `BusyFieldTest` fails on the
  unmarked lines; the 2 untagged assertions already pass.
- [ ] **Step 3: Implement** `_busy` and switch the raises: `_update`'s `jobs.Busy`, `_activate`'s "previous run is
  finishing", `_claim_folder` (keeping `{"job": ...}`), `_ensure_dir`, `_files_dir_ready`, `_job_delete`,
  `_run_prepare`'s ensure `jobs.Busy` -> `lock`; `_preview_dir` and `_run_prepare`'s marker check -> `preparing`;
  `_run_prepare`'s preview-lock timeout -> `preview`; `_commit_run`'s fingerprint check -> `{"stale": True}`. Add the
  marker comment to ~947 and ~949. Do **not** tag: "cleanup pending" (waits for the idle sweeper, minutes), "an upload
  is in flight", "in use by job", "the sources changed while detecting", and `str(OutputGone)` at ~1599 ("the files
  directory is still being moved or made on a slow or hung volume; ... try again later": a hung rename/mkdir keeps the
  directory fenced until the process restarts, so a bounded retry cannot help).
- [ ] **Step 4: Run, expect PASS** the same command; then G1, G2 (1104), G3.
- [ ] **Step 5: Commit** `maker: busy 409s carry a "busy" kind, a changed run "stale" (t_39c9fb52)` + trailer.

### Task 2: Page: `api()` retries busy answers within a bound, else offers "Try again"; stale and preparing runs

**Files:**
- Modify: `maker/static/pagelib.js` (new exports), `maker/static/maker.js` (`api()` ~442, `notice()`/`clearNotice()`
  ~259, `run()` ~2167, wiring), `maker/static/index.html` (button after `#notice`, line 38), `maker/static/style.css`
- Test: `maker/test/test_pagelib.py`, `maker/test/test_page_dom.py` (`LocalPageTest`)

**Interfaces:**
- Produces (pagelib.js): `export const BUSY_RETRY_MS = [500, 1000, 2000]; export const BUSY_RETRY_TOTAL_MS = 15000;`
  `export function busyRetryDelay(method: string, kind: unknown, repeats: number, elapsedMs: number): number | null` -
  `null` when `kind` is not one of `lock|preparing|preview`, when `kind === "preparing" && method !== "GET"`, when
  `repeats >= BUSY_RETRY_MS.length` or `elapsedMs >= BUSY_RETRY_TOTAL_MS`; else `BUSY_RETRY_MS[repeats]`.
- Produces (maker.js): `api(method, path, body, opts = {})` keeps its resolve/throw contract; the thrown `Error` carries
  `err.body` (the parsed error body, or `null`); `opts.onWait(kind)` (optional) is called once when the button is shown
  for this call. Module state `noticeEpoch`, `busyWait = null | {resolve, reject}`; internal `setNoticeQuiet(text)`;
  `followOtherRun(id)`: every 1000 ms for up to 15000 ms `GET` the job (stop early if `jobId !== id`), and once its state
  is not `detected` assign `job`, `renderAll()` and `startPolling()` when `queued`/`running`.
- Consumes: Task 1's `busy` and `stale` fields.

- [ ] **Step 1: Write the failing tests.**
  `test_pagelib.py`: `test_busy_policy_retries_lock_and_preview_then_stops` - for `("DELETE","lock")`,
  `("POST","preview")`, `("GET","preparing")`: repeats 0,1,2 -> 500, 1000, 2000; repeats 3 -> null; repeats 0 with
  elapsed 15000 -> null. `test_busy_policy_never_retries_a_preparing_post_or_an_untagged_answer` -
  `("POST","preparing",0,0)` -> null; kinds `undefined`, `""`, `"other"`, `true` -> null for every method.

  `test_page_dom.py`, class `LocalPageTest`: a class constant `BUSY_STUB` (preload JS) wrapping `window.fetch`:
  `window.__stub = {rules: [], sent: [], passed: [], realFetch}`; each call pushes `method + " " + pathname` to `sent`;
  the first rule whose `method` equals, whose `path` regex matches and whose `times > 0` is decremented and answers
  `new Response(JSON.stringify(rule.body), {status: 409, headers: {"Content-Type": "application/json"}})`; otherwise the
  real fetch, and `{m, path, status}` of its answer is pushed to `passed`. A script fragment `NOTICES` records every
  `#notice` text via `MutationObserver`. A helper `ready_job()` = `self.local_job()` with the TTF selected as
  `done_job()` sets it, not run. Each test drives `query="?job=" + jid, preload=self.BUSY_STUB`:
  - `test_a_busy_delete_is_retried_and_succeeds` - DELETE `/api/jobs/<jid>$` busy `lock` x2; click `#delete-job`; wait
    `#state` = `no job`. Assert DELETE sent 3 times, recorded notices include `(retrying 1/3)` and `(retrying 2/3)`,
    `#notice` and `#notice-retry` hidden at the end, server `GET` -> 404.
  - `test_a_busy_run_past_the_bound_offers_try_again_and_runs_once` - `ready_job()`; POST `/run$` busy `preview` x4,
    text `"job <jid> is busy: a preview is being made; try again"`. Click `#run`; wait `#notice-retry` visible. Assert
    POST run sent 4 times, `#notice` text equals `"POST /api/jobs/<jid>/run: HTTP 409: job <jid> is busy: a preview is
    being made; try again"`. Click `#notice-retry`; wait `#state` contains `written to`. Assert POST run in `sent` 5
    times and in `passed` exactly once (status 200), `#notice` hidden, `#notice-retry` hidden.
  - `test_a_run_being_prepared_is_not_retried_and_follows_the_other_run` - `ready_job()`; POST `/run$` busy
    `preparing` x1, text `"a run of job <jid> is being prepared"`. Click `#run`; wait `#notice-retry` visible; the
    script then sleeps 2000 ms and sends the "other tab's" run itself with `__stub.realFetch('/api/jobs/<jid>/run',
    {method: 'POST'})` (not in `sent`); wait `#state` contains `written to` (60 s cap). Assert POST run in `sent` once,
    `GET /api/jobs/<jid>` in `sent` at least twice after the POST (the follow), and the number of those GETs <= 16.
  - `test_busy_create_sources_and_detect_are_each_retried_once` - typed-path flow (`typed_script`); POST `/api/jobs$`
    busy `lock` x1 (a holder-busy answer, with `"job": "x"`), PUT `/sources$` x1, POST `/detect$` x1; `detectOnce()`.
    Assert counts 2/2/2, rows >= 5, server `store.list()` has exactly one job.
  - `test_other_409s_are_unchanged` - POST `/run$` x1 `{"error": "job <jid> is queued"}`; second click
    `{"error": "cleanup pending: ...", "job": "<jid>"}`; third click POST `/api/jobs$` (typed detect) `{"error": "job y
    is busy; try again"}` with no `busy` (the untagged create path). Each time: sent once, `#notice` equals today's
    `"<METHOD> <path>: HTTP 409: <error>"`, `#notice-retry` hidden, no `retrying` notice recorded.
  - `test_another_action_drops_the_try_again_control` - DELETE busy `lock` x4; click `#delete-job`; wait button
    visible; click `#save`; sleep 3000. Assert `#notice-retry` hidden, DELETE sent exactly 4 times, job on the server.
  - `test_an_action_during_a_sleeping_retry_cancels_it` - DELETE busy `lock` x4; click `#delete-job`; sleep 700; record
    `n0` = DELETE count; click `#save`; sleep 4000. Assert DELETE count - `n0` <= 1, job on the server, no `retrying`
    text in `#notice` at the end, `#notice-retry` hidden.
  - `test_a_stale_run_reloads_the_job_without_retry` - `ready_job()`; POST `/run$` x1 `{"error": "the job changed
    while the run was being prepared: run again", "stale": true}`. Click `#run`; sleep 1500. Assert POST run sent once,
    a `GET /api/jobs/<jid>` after it, `#notice-retry` hidden, `#notice` equals today's format.
- [ ] **Step 2: Run, expect FAIL**
  `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_page*.py' -k busy -k try_again -k other_409 -k being_prepared -k sleeping -k stale`
  -> pagelib: import error `busyRetryDelay`; page: DELETE sent once, no `#notice-retry`, no GET after a stale run.
- [ ] **Step 3: Implement.** `busyRetryDelay` in `pagelib.js`. In `api()`: a send loop; on a non-ok answer parse the JSON
  once (as today) and keep it as `err.body`; `kind = response.status === 409 ? data.busy : undefined`; `delay =
  busyRetryDelay(method, kind, repeats, now - start)`; if `delay !== null`: write the retry line quietly, record the
  epoch on the first one, sleep, check the epoch (moved -> reject, no send), send again. If `kind` is a valid busy kind
  and `delay === null`: write the usual message quietly, show `#notice-retry`, call `opts.onWait(kind)`, and return the
  `busyWait` promise (button handler as in "Try again control"). Every other answer: exactly today's path (public
  `notice`). In `run()`: the `POST run` call passes `{onWait: (kind) => { if (kind === "preparing")
  followOtherRun(jobId); }}`; its `catch` calls `reload()` when `err.body && err.body.stale === true`. Button:
  `<button id="notice-retry" type="button" class="notice-retry" hidden>Try again</button>`; style in `style.css`.
- [ ] **Step 4: Run, expect PASS** the Step 2 command; then G1, G2 (1114), G3.
- [ ] **Step 5: Commit** `maker page: bounded retry of busy 409s, a Try again control, stale and preparing runs (t_39c9fb52)` + trailer.

### Task 3: Page: preview GETs retry busy answers; docs; desktop e2e

**Files:**
- Modify: `maker/static/maker.js` (`fetchFresh` ~1486, probe `load` ~1316, source `<img>` ~927)
- Modify: `docs/maker-audit.md` section 8 ("Client-visible changes" bullet: replace "The page shows the error text;
  automatic retry of these 409s is a separate card." with the one-line rule, the bound, the button, the stale reload,
  the untagged create path and the precision paragraph above); `maker/README.md` only if it describes page error
  handling (it does not at 084ca27: then no change)
- Test: `maker/test/test_page_dom.py` (`LocalPageTest`)

**Interfaces:**
- Consumes: `busyRetryDelay` (Task 2).
- Produces: `fetchBusy(url: string, init?: RequestInit): Promise<Response>` in `maker.js` - `fetch`, and while the answer
  is a 409 whose JSON body (read from `response.clone()`) has a `busy` kind and `busyRetryDelay("GET", ...)` is not
  null, sleep and fetch again; returns the last `Response`; never touches `#notice`. `fetchFresh` and the probe's two
  fetches call it instead of `fetch`; the probe's failure line shows the server's `error` text for a busy 409 instead
  of "save the settings first". The `<img>` keeps `src = previewSrc(...)` and `loading=lazy`. Its first `onerror`:
  set `image.onerror = hide` (no loop), then `fetchBusy(src, {cache: "no-cache"})` once; ok -> `u =
  URL.createObjectURL(await r.blob()); image.onload = image.onerror = () => URL.revokeObjectURL(u)` (plus hide on
  error); `image.src = u`; any other answer -> hide as today. Cost, accepted: an `<img>` cannot see its status, so a 404
  or failed bake costs one more GET (a failed bake is attempted twice, never more).

- [ ] **Step 1: Write the failing tests** (real server answers: the in-process server's `preparing` marker; jobs with
  `self.local_job(roots=[self.roots[0]])`, so the TTF is the only entry with a preview):
  - `test_a_source_preview_being_prepared_is_retried_and_shown` - a `threading.Event` subclass `ReleaseOnWait(n)` whose
    `wait(timeout)` counts calls and, on call `n`, pops `self.srv.preparing[jid]` and `set()`s itself before
    `super().wait(timeout)`; install `ReleaseOnWait(3)` as `self.srv.preparing[jid]` (call 1: the `<img>` load, 409;
    call 2: the fallback fetch, 409; call 3: its first repeat, released). Within
    `mock.patch.object(jobs, "LOCKED_IO_S", 0.3)` drive with `BUSY_STUB` (no rules); wait for the TTF row's
    `img.preview` with `naturalWidth > 0` (90 s cap). Assert visible, and `passed` for `/preview/<ttf>/source.png` shows
    a 409 followed by a 200.
  - `test_a_source_preview_busy_past_the_bound_is_hidden_as_before` - a plain `Event` marker never released (popped in
    `addCleanup`); same patch; wait until the img is hidden (30 s cap). Assert the `sent` entries for
    `GET /api/jobs/<jid>/preview/<ttf>/source.png` number a positive multiple of 4 (1 + 3 repeats per table build) and
    `#notice` is hidden.
- [ ] **Step 2: Run, expect FAIL** `... -p test_page_dom.py -k source_preview` -> the first times out (img hidden after
  one 409, no fallback); the second counts 0 fallback GETs.
- [ ] **Step 3: Implement** `fetchBusy` and its three uses as in Interfaces; write the audit paragraph.
- [ ] **Step 4: Run, expect PASS**; then G1, G2 (1116), G3, and G5 (announce `START G5 t_39c9fb52` / `FINISH G5 ...`
  to the controller): `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy bash desktop/test/run-e2e.sh` -> both
  passes green.
- [ ] **Step 5: Commit** `maker page: preview fetches retry busy answers; audit (t_39c9fb52)` + trailer.

## Decisions taken (controller, 2026-11-17)

1. "the previous run is finishing; try again in a moment" is tagged `lock` (Task 1).
2. The orphan job a failed create may leave stays as today (accepted in the audit); the create-path ensure / cleanup
   busy answers are untagged and not retried (Task 1).
3. After "the job changed while the run was being prepared: run again" the page reloads the job (`stale: true`, Task 2).
4. Bounds 500/1000/2000 ms, 15 s total.
