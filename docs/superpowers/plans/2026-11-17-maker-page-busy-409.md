# Maker page: retry or explain the busy / being-prepared 409s - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close card t_39c9fb52: every 409 that t_d1aba4b8 (97f7ce3) added ("job X is busy; try again", "a run of job X
is being prepared[; try again]", "job X is busy: a preview is being made; try again") gets a page behaviour - a bounded
automatic retry or an explicit "Try again" control - covered by a page test; every other error stays as today.

**Architecture:** The server tags each of these answers with one machine-readable field, `"busy": "<kind>"`
(`lock` | `preparing` | `preview`), through one helper `_busy()`; the English text is unchanged. The page decides from
that field only: one pure policy function in `pagelib.js`, used by `api()` (JSON calls, with notice + "Try again"
button) and by one `fetchBusy()` helper for the preview GETs that do not go through `api()` (silent bounded retry).
A retry only ever repeats the one request that got a busy answer, never the whole action, and never after a network
error (no answer = outcome unknown).

**Tech Stack:** Python 3 `unittest` (`maker/server.py`, `maker/test/test_local_bounds.py`), ES module page
(`maker/static/maker.js`, `pagelib.js`, `index.html`, `style.css`), headless Chrome via `maker/test/pagedrive.mjs`
(`--preload` fetch stub), node for `test_pagelib.py`.

**Spec:** card t_39c9fb52; `docs/maker-audit.md` section 8, bullet "Client-visible changes (accepted)" (it says "automatic
retry of these 409s is a separate card": this one); `maker/server.py` at 084ca27 for the exact texts.

## Global Constraints

- Planner output only; the implementer changes `maker/server.py`, `maker/static/{maker.js,pagelib.js,index.html,style.css}`,
  tests and docs. Nothing under `c/`, `tools/`, `desktop/`.
- The 409 texts stay byte-identical (existing tests `assertIn` them; users may have seen them). Only a body key is added.
- No other status, text or body changes. Non-busy errors (400, 404, other 409s such as "output folder is in use",
  "cleanup pending ...", "job X is queued", "the job changed while the run was being prepared: run again") keep today's
  page behaviour exactly: one notice line, no button, no retry.
- The CSP allows no inline style (`test_sync_caveat_is_shown` asserts no ` style="` in `index.html`): the button is
  styled in `style.css`.
- Scratch only under `$HOME/work/tmp`: `export TMPDIR=$HOME/work/tmp/svf-busy409` (`mkdir -p` it) for every command.
- Commit messages end with `(t_39c9fb52)` and `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push.

### Gates (end of every task)

- **G1** `git diff --exit-code 587dfb5 -- c/src c/include` - exit 0.
- **G2** `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_*.py'`
  - `OK`; at 084ca27 `Ran 1103 ... OK (skipped=25)`. Expected after Task 1: 1104; after Task 2: 1104 + 2 (pagelib) + 6
  (page) = 1112; after Task 3: 1112 + 2 = 1114; skipped stays 25 (on a host with Chrome, node and the built module).
- **G3** `python3 -m unittest discover -s maker/test -p test_server.py -k test_page_js_tables_match_python` - `OK`.
- **Desktop.** The shell itself calls none of the affected routes (only `GET /api/jobs/<id>` in `maker:open-output`,
  `GET /api/caps`; neither answers busy) and `desktop/lib/budget.js` is untouched, so G4 (`desktop/test/unit.test.js`)
  is not needed. The e2e drives the page's `api()` through detect-local and run, so **G5 runs once, in Task 3**:
  `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy bash desktop/test/run-e2e.sh` -> both passes green.

## Decision table (per answer, per route)

`kind` is the new body field. "Auto" = `api()`/`fetchBusy()` repeats the identical request after 500, 1000, 2000 ms
(at most 3 repeats, 4 sends), and starts no repeat once 15 s have passed since the first send. Every busy answer below
is raised before the request changed anything (checked in `server.py`: `Busy` means the job lock / record was not
taken, the transition did not run, the run was not queued, the preparing marker was cleared), so repeating it cannot
double-submit.

| Answer (kind) | Route (handler) | Safe to repeat? | Page behaviour |
|---|---|---|---|
| "job X is busy; try again" (`lock`) | `DELETE /api/jobs/X` (`_job_delete`; record not saved, job stays) | yes: idempotent, job still there | Auto; then "Try again" |
| same (`lock`) | `POST /api/jobs` local create: takeover holder busy (`_claim_folder`, keeps `"job"`), ensure busy, cleanup of a failed create busy | yes: nothing was answered/created (see open question 2 for the orphan) | Auto; then "Try again" |
| same (`lock`) | `PUT sources`, `POST detect` (`_activate` / `_files_dir_ready` / `_update(timeout)`) | yes: transition not applied; both replace state wholesale | Auto; then "Try again" |
| same (`lock`) | `POST run` (prepare ensure, commit `_update(timeout)`) | yes: not queued, marker cleared | Auto; then "Try again" |
| same (`lock`) | `GET preview/<f>/source.png`, `GET source/<f>.svf`, `GET probe/...` (`_preview_dir` -> `_ensure_dir`) | yes: GET | Auto, silent (`fetchBusy`); exhausted = today's failure display |
| "job X is busy: a preview is being made; try again" (`preview`) | `POST run` (`_run_prepare`, bake holds a preview lock past `LOCKED_IO_S`) | yes: nothing done | Auto; then "Try again" |
| "a run of job X is being prepared; try again" (`preparing`) | the three preview GETs (`_preview_dir`) | yes: GET | Auto, silent; exhausted = today's failure display |
| "a run of job X is being prepared" (`preparing`) | `POST run` (`_run_prepare`, a second run while one is prepared) | technically yes, but pointless: another run of this job is in flight (other tab, double click) | **No auto retry.** Notice + "Try again" at once, and the page reloads the job (`reload()`; polls if it became `queued`/`running`) so the other run shows |

Rule in one line (the pure policy): retry automatically unless `kind === "preparing"` and the method is not `GET`.

**"Try again" control** (`#notice-retry`, a `<button>` right after `#notice`): shown with the usual notice text when the
bound is exhausted or the policy says no auto retry. Clicking it re-sends the identical request (same method, path, body;
a `Blob` body is re-sendable) with a fresh bound; on success the awaiting caller continues as if the first send had
succeeded (so `detectLocal` goes on to `PUT sources` and `detect`, never re-creating). Any other `notice()` /
`clearNotice()` (every action starts with `clearNotice()`) hides the button and rejects the awaiting call with the
original error, so the caller's existing `catch` returns as today. One button: a second exhausted call replaces (and
rejects) the first.

**While retrying**, `#notice` shows `METHOD path: HTTP 409: <server text> (retrying N/3)`. On a successful retry `api()`
clears the notice only if it still shows that retry line (another message set meanwhile stays).

## Review Focus

1. A network error or non-JSON 409 during a retry: no further retry (outcome unknown), today's message. Test:
   `test_busy_policy_*` covers "no kind -> null"; Task 2 `api()` must only read `kind` from a parsed JSON body.
2. A user action started while a retry is sleeping (e.g. Save during a DELETE retry): the sleeping retry must not fire
   afterwards. Test `test_another_action_drops_the_try_again_control` (Task 2) asserts no later DELETE is sent.
3. Two concurrent busy calls (renderJobs + an action): only one button; the replaced one rejects. Covered by the
   "one button" rule; reviewer checks `api()` keeps one `busyWait` slot.
4. A `POST run` "being prepared" answer must never be repeated automatically: `test_a_run_being_prepared_is_not_retried`.
5. Upload mode: the server never sends `busy` there; nothing changes (existing `PageDomTest` stay green in G2).

---

### Task 1: Server: tag every busy answer with `"busy": kind`

**Files:**
- Modify: `maker/server.py` (add `_busy` beside `_HttpError` ~line 164; replace the busy raises at ~847, 947, 949,
  1001, 1049, 1074, 1089, 1176, 1592, 1601, 1619)
- Test: `maker/test/test_local_bounds.py` (amend 8 existing tests, add 1)

**Interfaces:**
- Produces: `_busy(kind: str, message: str, extra: dict | None = None) -> _HttpError` returning
  `_HttpError(409, message, dict(extra or {}, busy=kind))`; `kind` in `("lock", "preparing", "preview")`. Callers
  `raise _busy(...)`. Body on the wire: `{"error": <unchanged text>, "busy": kind[, "job": id]}`.

- [ ] **Step 1: Write the failing assertions.** Add `self.assertEqual(body.get("busy"), K)` to:
  `test_a_delete_whose_cleanup_record_cannot_be_saved_keeps_the_job` (`lock`),
  `test_a_failed_takeover_that_cannot_record_answers_409_busy_and_keeps_the_job` (`lock`),
  `test_a_takeover_with_a_busy_holder_answers_busy_naming_it` (`lock`, and `job` still the holder),
  `test_a_create_whose_ensure_is_busy_answers_busy_not_400` (`lock`),
  `test_ensure_with_a_held_job_lock_is_busy_and_makes_nothing` (the detect answer `body2`: `lock`),
  `test_a_second_run_during_preparation_is_refused` (`preparing`),
  `test_a_preview_waits_a_bounded_time_for_a_run_being_prepared` (`preparing`),
  `test_a_run_waits_a_bounded_time_for_a_preview_lock` (`preview`).
  Add to the same file, class `BusyFieldTest(unittest.TestCase)`:
  `test_every_busy_409_goes_through_busy_helper` - reads `server.py` source; asserts no match of
  `r'_HttpError\(409,\s*"(?:[^"]*is busy|a run of job)'` (the "changed while the run was being prepared: run again"
  text does not match: it is not busy), and that `raise _busy(` occurs at least 11 times.
- [ ] **Step 2: Run, expect FAIL** `python3 -m unittest discover -s maker/test -p test_local_bounds.py -k busy -k prepar -k takeover`
  -> the 8 amended tests fail on `None != 'lock'` etc.; the new one fails on the regex.
- [ ] **Step 3: Implement** `_busy` and switch every listed raise; `_update`'s `jobs.Busy` branch, `_ensure_dir`,
  `_files_dir_ready`, `_job_delete`, both create branches and `_claim_folder` (keeping `{"job": ...}`) -> `lock`;
  `_preview_dir` and `_run_prepare`'s marker check -> `preparing`; `_run_prepare`'s preview-lock timeout -> `preview`;
  `_run_prepare`'s ensure `jobs.Busy` -> `lock`. Do not tag "cleanup pending", "previous run is finishing", "an upload
  is in flight", "in use by job", "changed while ... run again".
- [ ] **Step 4: Run, expect PASS** the same command; then G1, G2 (1104), G3.
- [ ] **Step 5: Commit** `maker: busy 409s carry a "busy" kind for the page (t_39c9fb52)` + trailer.

### Task 2: Page: `api()` retries busy answers within a bound, else offers "Try again"

**Files:**
- Modify: `maker/static/pagelib.js` (new export), `maker/static/maker.js` (`api()` ~442, `notice()`/`clearNotice()`
  ~259, `run()` ~2167, wiring), `maker/static/index.html` (button after `#notice`, line 38), `maker/static/style.css`
- Test: `maker/test/test_pagelib.py`, `maker/test/test_page_dom.py` (`LocalPageTest`)

**Interfaces:**
- Produces (pagelib.js): `export const BUSY_RETRY_MS = [500, 1000, 2000]; export const BUSY_RETRY_TOTAL_MS = 15000;`
  `export function busyRetryDelay(method: string, kind: unknown, repeats: number, elapsedMs: number): number | null` -
  `null` when `kind` is not one of `lock|preparing|preview`, when `kind === "preparing" && method !== "GET"`, when
  `repeats >= BUSY_RETRY_MS.length` or `elapsedMs >= BUSY_RETRY_TOTAL_MS`; else `BUSY_RETRY_MS[repeats]`.
- Produces (maker.js): `api(method, path, body, opts = {})` keeps its resolve/throw contract; `opts.onWait(kind)` (optional)
  is called once when the "Try again" button is shown for this call; new module state
  `busyWait = null | {reject}`; `notice(message)` and `clearNotice()` hide `#notice-retry` and reject `busyWait` (set to
  null) before writing. `api()` sets `busyWait` only after its own `notice()` call.
- Consumes: Task 1's `busy` body field.

- [ ] **Step 1: Write the failing tests.**
  `test_pagelib.py`: `test_busy_policy_retries_lock_and_preview_then_stops` - for `("DELETE","lock")`,
  `("POST","preview")`, `("GET","preparing")`: repeats 0,1,2 -> 500, 1000, 2000; repeats 3 -> null; repeats 0 with
  elapsed 15000 -> null. `test_busy_policy_never_retries_a_preparing_post_or_an_untagged_answer` -
  `("POST","preparing",0,0)` -> null; kinds `undefined`, `""`, `"other"`, `true` -> null for every method.
  `test_page_dom.py`, class `LocalPageTest`: a class constant `BUSY_STUB` (preload JS) that wraps `window.fetch`:
  `window.__stub = {rules: [], sent: []}`; each call pushes `method + " " + pathname` to `sent`; the first rule whose
  `method` equals and whose `path` regex matches with `times > 0` is decremented and answers
  `new Response(JSON.stringify(rule.body), {status: 409, headers: {"Content-Type": "application/json"}})`; else the
  real fetch. Rules are set by the test script before it clicks. A helper `notices` script fragment records every
  `#notice` text via `MutationObserver`. Tests (each uses `self.local_job()` / `self.done_job()` and
  `drive(..., query="?job=" + jid, preload=self.BUSY_STUB)`):
  - `test_a_busy_delete_is_retried_and_succeeds` - rule DELETE `/api/jobs/<jid>$` busy `lock` x2; click
    `#delete-job`; wait `#state` = `no job`. Assert DELETE sent 3 times, some recorded notice contains
    `(retrying 1/3)` and `(retrying 2/3)`, `#notice` hidden at the end, `#notice-retry` hidden, server `GET` -> 404.
  - `test_a_busy_run_past_the_bound_offers_try_again_and_runs_once` - job: `self.local_job()` with the TTF selected
    (as `done_job` sets it, without running). Rule POST `/run$` busy `preview` x4, text
    `"job <jid> is busy: a preview is being made; try again"`. Click `#run`; wait `#notice-retry` visible. Assert POST
    run sent 4 times, `#notice` text equals `"POST /api/jobs/<jid>/run: HTTP 409: job <jid> is busy: a preview is being
    made; try again"`. Click `#notice-retry`; wait `#state` contains `written to`. Assert POST run sent 5 times in all,
    `#notice-retry` hidden, server job `done` and exactly one run happened (the job's `steps` list is the single-run
    plan: compare `len(steps)` with a direct run of an identical fresh job, or assert `log.md` has one run header).
  - `test_a_run_being_prepared_is_not_retried` - rule POST `/run$` busy `preparing` x1, text
    `"a run of job <jid> is being prepared"`. Click `#run`; wait `#notice-retry` visible; `sleep(4000)` (past the whole
    delay schedule). Assert POST run sent once, a `GET /api/jobs/<jid>` was sent after it (the reload).
  - `test_busy_create_sources_and_detect_are_each_retried_once` - typed-path flow (`typed_script`), rules POST
    `/api/jobs$` busy `lock` x1, PUT `/sources$` x1, POST `/detect$` x1. `detectOnce()`. Assert counts 2/2/2, rows >= 5,
    server `store.list()` has exactly one job.
  - `test_other_409s_are_unchanged` - rule POST `/run$` x1 with body `{"error": "job <jid> is queued"}` (no `busy`) and,
    in a second click, `{"error": "cleanup pending: ...", "job": "<jid>"}`. Each time: sent once, `#notice` text equals
    the today's format `"POST /api/jobs/<jid>/run: HTTP 409: <error>"`, `#notice-retry` hidden, no `retrying` notice.
  - `test_another_action_drops_the_try_again_control` - rule DELETE busy `lock` x4; click `#delete-job`; wait button
    visible; click `#save`; `sleep(3000)`. Assert `#notice-retry` hidden, DELETE sent exactly 4 times, job still on the
    server.
- [ ] **Step 2: Run, expect FAIL**
  `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p 'test_page*.py' -k busy -k try_again -k other_409`
  -> pagelib: import error `busyRetryDelay`; page: DELETE sent once / no `#notice-retry` element.
- [ ] **Step 3: Implement.** `busyRetryDelay` in `pagelib.js`. In `api()`: wrap the send in a loop; on a non-ok answer
  parse the JSON once (as today); `kind = response.status === 409 ? data.busy : undefined`; `delay =
  busyRetryDelay(method, kind, repeats, now - start)`; if `delay !== null`: notice the retry line, sleep, send again.
  If `kind` is a valid busy kind and `delay === null`: notice the usual message, show `#notice-retry`, and return a
  promise that the button's click resolves by re-entering `api(method, path, body)` (fresh bound) and that
  `notice()/clearNotice()` rejects with the original `Error(message)`. Every other answer: exactly today's code path.
  In `run()`: the `POST run` call passes `{onWait: (kind) => { if (kind === "preparing") reload().then(() => {
  if (job && (job.state === "queued" || job.state === "running")) startPolling(); }); }}` so the other run shows at
  once while the button waits (`reload()` never calls `notice`, so the button stays). Button: `<button id="notice-retry" type="button" class="notice-retry"
  hidden>Try again</button>`; style in `style.css` (same max-width/margin as `.notice`).
- [ ] **Step 4: Run, expect PASS** the Step 2 command; then G1, G2 (1112), G3.
- [ ] **Step 5: Commit** `maker page: bounded retry of busy 409s and a Try again control (t_39c9fb52)` + trailer.

### Task 3: Page: preview GETs retry busy answers; docs; desktop e2e

**Files:**
- Modify: `maker/static/maker.js` (`fetchFresh` ~1486, probe `load` ~1316, source `<img>` ~927)
- Modify: `docs/maker-audit.md` section 8 ("Client-visible changes" bullet: replace "The page shows the error text;
  automatic retry of these 409s is a separate card." with the decision table's one-line rule, the bound and the button);
  `maker/README.md` only if it describes page error handling (it does not at 084ca27: then no change)
- Test: `maker/test/test_page_dom.py` (`LocalPageTest`)

**Interfaces:**
- Consumes: `busyRetryDelay`, `BUSY_RETRY_MS` (Task 2).
- Produces: `fetchBusy(url: string, init?: RequestInit): Promise<Response>` in `maker.js` - `fetch`, and while the answer
  is a 409 whose JSON body (read from `response.clone()`) has a `busy` kind and `busyRetryDelay("GET", ...)` is not
  null, sleep and fetch again; returns the last `Response` (never touches `#notice`). `fetchFresh` and the probe's two
  fetches call it instead of `fetch`. The `<img>` keeps `src = previewSrc(...)` and `loading=lazy`; its `onerror` calls
  `fetchBusy(src, {cache: "no-cache"})` once: ok -> `image.src = URL.createObjectURL(await r.blob())`; otherwise hide as
  today. The probe's failure line shows the server's `error` text for a busy 409 instead of "save the settings first".

- [ ] **Step 1: Write the failing tests** (real server answers, no stub: the in-process server's `preparing` marker):
  - `test_a_source_preview_being_prepared_is_retried_and_shown` - `jid = self.local_job()`; `ev = threading.Event();
    self.srv.preparing[jid] = ev`; a `threading.Timer(1.5, release)` where `release` pops the marker and sets `ev`;
    within `mock.patch.object(jobs, "LOCKED_IO_S", 0.3)` drive `?job=jid` with a fetch-counting preload (reuse
    `BUSY_STUB` with no rules); wait for the `Munjo.ttf` row's `img.preview` to have `naturalWidth > 0` (90 s cap).
    Assert visible, and the stub's `sent` has >= 2 GETs of `/preview/<ttf>/source.png` (the `onerror` fallback retried).
  - `test_a_source_preview_busy_past_the_bound_is_hidden_as_before` - marker set and never released (released in
    `addCleanup`); same patch; wait until the img is hidden (30 s cap). Assert the fallback sent exactly 4 GETs
    (1 + 3 repeats) and `#notice` is hidden (silent).
- [ ] **Step 2: Run, expect FAIL** `... -p test_page_dom.py -k source_preview` -> the first test times out with the
  img hidden after one 409; the second counts 1 fallback GET.
- [ ] **Step 3: Implement** `fetchBusy` and its three uses as in Interfaces; write the audit paragraph.
- [ ] **Step 4: Run, expect PASS**; then G1, G2 (1114), G3, and G5 (announce `START G5 t_39c9fb52` / `FINISH G5 ...`
  to the controller): `flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy bash desktop/test/run-e2e.sh` -> both
  passes green.
- [ ] **Step 5: Commit** `maker page: preview fetches retry busy answers; audit (t_39c9fb52)` + trailer.

## Open questions

1. **"job X: the previous run is finishing; try again in a moment"** (`_activate`, older than t_d1aba4b8) and
   **"cleanup pending: ... try again later"** are also transient. This plan leaves them untagged (card scope: the new
   answers). Tagging the first as `lock` is one line in Task 1 if wanted; "cleanup pending" waits for the idle sweeper
   (minutes) and should stay an explicit message.
2. **A failed create whose own cleanup was busy** leaves an orphan `uploading` job holding the folder (accepted in the
   audit, swept when idle). The automatic retry of that create then gets "output folder is in use by job <orphan>"
   (non-busy, shown as today). Adding `{"job": id}` to that busy answer would let the page reuse the orphan via
   `reuse`; not done here.
3. **"the job changed while the run was being prepared: run again"** is not busy and stays as today; a `reload()` after
   it would show the settings that changed. Out of scope unless asked.
4. The bound (500/1000/2000 ms, 15 s cap) is a judgement: a busy section is bounded server-side by `LOCKED_IO_S` = 5 s,
   so 3 repeats cover one more full section of contention. Change the two constants in `pagelib.js` if review prefers.
