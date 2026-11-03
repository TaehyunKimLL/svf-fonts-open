# Face Selection by Size, Family and Variant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the picker's flat 153-row face list with a size -> family -> variant choice over the listed faces, prefetch
every face of the chosen size so each family row carries its missing-glyph mark, and make face memory safe against a
prefetch that overlaps a selection; card t_fe9f6c30.

**Architecture:** `web/mkindex.py` derives Hangul coverage (`hangul`, `latin_only`, `subset`) per face and joins a reviewed
`web/FAMILIES.tsv` (`family`, `style`, `variant`), failing the build on a listed face without a row or a collision.
`web/picker.js` validates the new fields in `checkIndex`, groups listed faces per size in a `Map`, and gains a prefetch loop
that fetches over the network outside any lock and copies into the heap under one heap-lock promise chain shared with
`select` and the `markLacking` scan; `makeRoom` always protects the open chain and `state.pending`. The left panel becomes
size chips, a family listbox and a variant radiogroup; the preview selectors gain size groups, "= list" badges and per-slot
notes; the URL carries the chain and scale. `web/test/check.mjs` gains the spec's cases with their numbers verbatim.

**Tech Stack:** as the wasm-picker plan: C99 glue unchanged, plain ES2022 (`picker.js` the only module), Python 3 unittest,
node 24 + playwright-core 1.62.1 driving Chrome (`channel: "chrome"`).

**Spec:** `docs/superpowers/specs/2026-10-20-face-selection-design.md` at `84a6c80` (read it first; the appendix is the
`FAMILIES.tsv` content). It supplements `docs/superpowers/specs/2026-10-20-wasm-picker-design.md`; the page it changes is
the one `docs/superpowers/plans/2026-10-20-wasm-picker.md` built in Tasks 1-4 (+4b). This plan runs before that plan's
Tasks 5-6 (see the last section). Current code: `web/picker.js` (`readBounded`, `fetchFace`, `makeRoom`, `selectNow`,
`lacking`, `markLacking`, `checkIndex`, `buildList`, `filterList`, `buildControls`), `web/mkindex.py`, `web/test/check.mjs`
(cases A, supplement, B, fetch-once, C, D, marks, bad face, transport, index, no stream, surrogates, budget, runs, dom, E),
`web/test/serve.mjs` (`startServer(dir, opts)`), `tools/test_web_picker.py` (`TestIndex`, `TestModule`, `TestCopyFaces`,
`TestPage`; `checked_out()` runs check.mjs once per run and `TestPage.test_cases` asserts case names in `cases.txt`).

## Global Constraints

- Everything in the wasm-picker plan's Global Constraints still holds: no change under `c/` (`make -C c check` stays
  green), no code outside `web/`'s own directory at run time, `index.html` has no inline script, generated files never
  committed, JS never draws text, every face's licence reachable, export `format` exactly `scummvm-ko-font-pairing/1`.
- No change to the renderer, the module glue or the pixels drawn; no change to the per-run rule (a Hangul run draws from
  [Hangul, Latin], a Latin run from [Latin, Hangul]).
- `faces.json` stays `svf-fonts-web-index/1`; every existing field (including `label`) keeps its meaning; a subset face is
  hidden, never dropped: `faces()` and check.mjs case A keep all 153 faces.
- Rules copied from the spec: `KS = {0xAC00 + n for n in jamoset.ks_x_1001_syllables()}` (2,350 code points); ASCII present
  = every U+0021..U+007E (94) in the cmap; `latin_only = not jamo and hangul == 0 and ASCII present`; `subset = not jamo
  and not latin_only and hangul < 2350`; "left-list face" = `!subset && !latin_only`; `MAX_FIELD` 256; `MAX_TOTAL_FACE_BYTES`
  64 MiB; `DEFAULT_HANGUL = 'svf/dos/NGOTB16.SVF'` (one default fills both slots).
- `FAMILIES.tsv` keys are exact index keys (`svf/<rel>`), no globs; the committed file is the spec's appendix verbatim
  (header + 120 rows, tabs between cells, a trailing empty `variant` written as nothing after the last tab).
- Families are grouped by `JSON.stringify([family, style])` in a `Map`; names reach the DOM only through `textContent` and
  `title` (`el()`); URL and stored keys are only ever `byKey` lookups, never fetch URLs.
- No `AbortController`; the face in flight when a loop stops is kept. No pointer handed to `svfw_open`, and no pointer a
  slot holds, is ever freed.
- The three check.mjs residuals the user's approval carries (progress.md, design-rereview4-opus.md,
  select-rev4-{sol,agy}) are implemented as written in Tasks 5 and 6, and the owning task edits the spec's case text to
  match (the ruling: the doc lags the plan until that task updates it).
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A family or style named `__proto__` / `constructor` (or one containing `|`, `,` or `"`): it must be its own row, with
   no page error and no collision with another family — Task 2 `case default variant`, synthetic index step.
2. A keystroke in the sample text while faces of two sizes are in the heap: the rescan must open only the shown size's
   faces plus the chain, not every fetched face — Task 5 `case prefetch`, the `opens <= 44` step.
3. A selection whose Hangul face fails to open while a prefetch loop runs: `state.pending` must be cleared in `finally`,
   or that face is protected from eviction forever — Task 5 `case select during eviction`, the failed-open step.
4. `?manual` combined with `hangul=`/`latin=`/`scale=`: manual wins (no chain, no face request); a URL fault on a manual
   page is still a notice — Task 7 `case url`, the manual step.
5. Two faces whose axes are identical and whose `variant` tags are both empty (a collision `mkindex.py` would refuse but
   a hand-edited index lets through): the page builds, and the two chips are told apart by file name — Task 3 `case
   sizes`, synthetic index step.

---

## File structure

```
web/FAMILIES.tsv              the reviewed family table, the spec's appendix verbatim (Task 1)
web/mkindex.py                coverage fields, --families, family checks, the counts line (Task 1)
web/picker.js                 checkIndex, families model (Task 2); left panel + notice + view (Task 3); selectors, notes,
                              cards (Task 4); heap lock, pending, prefetch loop, setSize, marks (Task 5); readBounded
                              drop rule, BudgetError vs other errors (Task 6); URL state (Task 7)
web/index.html, web/style.css the new left panel, notice, notes, badges (Tasks 3, 4)
web/test/serve.mjs            paced chunked bodies, big bodies, per-URL status, stats() (Task 6)
web/test/check.mjs            rewritten C, D, marks, bad face, budget, dom, index; new cases per task
tools/test_web_picker.py      TestIndex additions and fixtures (Task 1); TestPage.test_cases names (Tasks 2-7)
docs/superpowers/specs/2026-10-20-face-selection-design.md   the two case paragraphs the residuals change (Tasks 5, 6)
```

Test commands: `python3 -m unittest tools.test_web_picker -v` (one class: `-k TestIndex`, `-k TestPage`),
`python3 -m unittest discover -s tools -p 'test_*.py'` (the gate), `bash web/build.sh` (OUT default `web/dist`), `make -C c
check`. check.mjs runs only through `TestPage` (`checked_out()`); to iterate on one case run
`~/opt/node-v24.13.0-linux-x64/bin/node web/test/check.mjs web/dist web/test/out` after `bash web/build.sh` and read the
`FAIL <case>:` lines. Every check.mjs case that opens its own page follows the existing pattern: `ctx.newPage()`,
`pageerror` collected into `probs`, `?manual`, `await window.picker.ready`, `counts.push('case NAME: ...')` only when
`nfailed === n0`, `fail('case NAME', why)` otherwise, `page.close()`.

---

### Task 1: Index: coverage fields, the family table and its checks

**Files:**
- Create: `web/FAMILIES.tsv`
- Modify: `web/mkindex.py` (`entry`, `main`, new functions), `tools/test_web_picker.py:85-325` (`TestIndex`, fixtures)

**Interfaces:**
- Consumes: `tools/jamoset.py` `ks_x_1001_syllables()`, `parse_svfn(data).glyphs` (the cmap); `tools/svfline.py`
  `Face(data).has(cp)`.
- Produces: `faces.json` entries with `hangul` (int 0..2350), `latin_only` (bool), `subset` (bool), `family`, `style`,
  `variant` (strings, `""` allowed; `family == ""` only for a subset face without a row). CLI: `mkindex.py SVF_DIR
  [OUT_JSON] [--check] [--licences TSV] [--families TSV]` (`--families` default `FAMILIES.tsv` beside the script). Stdout:
  `153 faces, 120 listed (2 latin-only), 33 subset, 0 unmapped`. Exit 2 naming the face or `FAMILIES.tsv:<line>`, nothing
  written. Functions: `read_families(path) -> {key: (family, style, variant)}` (raises `FaceError`),
  `coverage(data, svf, jamo, svfline) -> (hangul, latin_only, subset)`, `check_families(faces, rows, svf_dir)` (raises
  `FaceError`). Check order: tables (licences, then families syntax); per face in sorted key order licence rules then
  header and coverage; then the family rules over all entries (no row / empty family for a listed face; a row whose file is
  not under `SVF_DIR`; two listed faces sharing `(family, style, px, bpp, jamo, cell_w, cell_h, variant)`, both named).

- [ ] **Step 1: Fixture helper and the failing tests.** In `tools/test_web_picker.py` add `iolo_families(tmp)`: writes
  `tmp/FAMILIES.tsv` holding the header and the `svf/iolo/` rows of `web/FAMILIES.tsv`, returns its path; change every
  fixture test that calls `run_mkindex` on an `iolo_tree` (`test_unmapped_face_fails`, `test_piece_missing_is_plain`,
  `test_bad_licence_rows_fail`, `test_licence_urls_normalised`, `test_missing_licence_file_fails`,
  `test_check_writes_nothing`, `test_malformed_faces_tsv_fails`) to pass `"--families", iolo_families(tmp)`. In
  `test_lists_every_face` replace the `"{n} faces, 0 unmapped"` assertion with
  `assertRegex(self.stdout, r"^\d+ faces, \d+ listed \(\d+ latin-only\), \d+ subset, 0 unmapped$")`. Add:
  - `test_hangul_coverage_matches_cmap`: for every entry, `hangul` equals the test's own count (`KS & set(parse_svfn(data).glyphs)`
    for `jamo` false, `sum(Face(data).has(cp) for cp in KS)` for `jamo` true); `latin_only == (not jamo and hangul == 0
    and all(c in cmap for c in range(0x21, 0x7F)))`; `subset == (not jamo and not latin_only and hangul < 2350)`.
  - `test_subset_examples`: `svf/dos/NGOTB14.SVF` subset with `hangul == 1120`; `svf/dos/NGOTB16.SVF` not subset, 2350;
    `svf/iolo/HGKEY6J.SVF` not subset, jamo, 2350; `svf/dos/COUSB24.SVF` and `svf/dos/PAPLG16.SVF` `latin_only`, not subset,
    `hangul == 0`; `svf/dos/GBA14X2.SVF` subset and not `latin_only`; the counts line equals
    `f"{n} faces, {listed} listed ({lo} latin-only), {sub} subset, 0 unmapped"` with the four numbers derived from the
    entries by the rule (today 153, 120, 2, 33).
  - `test_every_listed_face_has_a_family`: `family != ""` for every entry with `subset` false; every `file` of
    `web/FAMILIES.tsv` is an index key.
  - `test_family_examples`: `svf/dos/TBGOB24.SVF` -> `("Taebaek", "Gothic")`, `svf/dos/TBMY24.SVF` -> `("Taebaek",
    "Myungjo")`, `svf/dos/HWPHM24.SVF` style `"Myungjo"`, `svf/iolo/HGKEY6J.SVF` family starts with `"Cheonggyecheon"`,
    `svf/jamo-extra/GOTHB16A.SVF` -> `("Gothic A1", "Bold")`, `svf/dos/COUSB24.SVF` -> `("Coustard", "Bold")`,
    `svf/dos/NGOTB16.SVF` variant `"KS X 1001 symbols"`.
  - `test_missing_family_row_fails` (iolo tree, fixture table without the `HGKEY6J` row: exit 2, `HGKEY6J.SVF` in stderr,
    no `faces.json`); `test_stale_family_row_fails` (a row `svf/iolo/NOPE.SVF`: exit 2, stderr names `FAMILIES.tsv:<line>`
    with the line number of that row); `test_duplicate_family_row_fails` (HGKEY6J twice); `test_family_header_fails`
    (a table without a `family` column; one with `file` twice in the header: both exit 2 naming line 1);
    `test_family_key_without_prefix_fails` (`iolo/HGKEY6J.SVF`: exit 2 naming its line); `test_short_row_is_padded`
    (a two-cell row `svf/iolo/HGKEY6J.SVF<TAB>X`: exit 0, `family == "X"`, `style == ""`, `variant == ""`);
    `test_extra_column_ignored` (header `file family style variant note`, rows with five cells: exit 0);
    `test_licence_error_comes_first` (iolo tree + `ZZZ.SVF` and a fixture table lacking HGKEY6J: stderr names `ZZZ.SVF`,
    not `HGKEY6J`).
  - `test_variant_collision_fails`: iolo tree plus `svf/iolo/COPY6J.SVF` copied from `HGKEY6J.SVF`, both rows with the same
    family and empty variants: exit 2, stderr names both files; the same with `variant` `"copy"` on the COPY6J row: exit 0.
  - `test_real_table_has_no_collision`: `setUpClass` succeeded (assert `self.index["format"] == "svf-fonts-web-index/1"`;
    the method exists so the failure reads right).
- [ ] **Step 2: Run** `python3 -m unittest tools.test_web_picker -k TestIndex` -> FAIL (`--families` unknown, no
  `web/FAMILIES.tsv`).
- [ ] **Step 3: Implement.** Write `web/FAMILIES.tsv` from the spec appendix (copy the block; check with
  `awk -F'\t' 'NF!=4' web/FAMILIES.tsv` that every row has four cells and `wc -l` gives 121). In `web/mkindex.py`: strip a
  leading BOM, accept CRLF, skip `#` and blank lines, trim cells, pad short rows, refuse long rows, duplicate `file`,
  empty `file`, a `file` without `svf/`, a header without `file`/`family` or with a duplicate name (message
  `FAMILIES.tsv:<line>: ...`, the path as given); `coverage` as the rule; `entry` gains the six fields (a hidden face
  without a row: `""` x3); `check_families` after every entry is built; the stdout line.
- [ ] **Step 4: Run** `-k TestIndex` -> PASS; `python3 web/mkindex.py svf /tmp/faces.json` prints
  `153 faces, 120 listed (2 latin-only), 33 subset, 0 unmapped`; `bash web/build.sh` still succeeds (`TestCopyFaces` PASS).
- [ ] **Step 5: Commit** `web: Hangul coverage, Latin-only and subset flags, and the family table in faces.json`.

### Task 2: picker.js: index validation and the families model

**Files:**
- Modify: `web/picker.js` (`checkIndex`, `main`, the `picker` object), `web/test/check.mjs` (case index; new case
  default variant), `tools/test_web_picker.py` (`TestPage.test_cases` names)

**Interfaces:**
- Consumes: Task 1's fields.
- Produces (module-internal, used by Tasks 3-7): `const isLeft = f => !f.subset && !f.latin_only`;
  `const famKey = f => JSON.stringify([f.family, f.style])`; `rankFace(a, b)` comparator (higher `bpp` first, then `!jamo`,
  then `cell[0] === cell[1]`, then more `glyphs`, then the smaller `key`); `state.fams: Map<px, Map<famKey, fam>>` where
  `fam = {family, style, name, faces: [keys in rankFace order], default: faces[0]}` and `name = family + (style ? ' ' +
  style : '')`, built in `main()` over left-list faces, the inner Map's entries sorted by `family` then `style`,
  case-insensitive. Public: `picker.listed()` (entries with `subset` false), `picker.sizes()` (sorted distinct `px` of
  left-list faces), `picker.families(px)` (the fams of that size as an array; `[]` for a size with none),
  `picker.defaultVariant(family, style, px)` (key or `null`), `picker.pick(key)` (rejects `pick: <key> is not a listed
  Hangul face` for a key that is not a left-list face, chain unchanged; else `select({latin: key, hangul: key})`; starts
  no prefetch).
- `checkIndex` additions, with these messages (the test matches them): `faces.json: format must be
  "svf-fonts-web-index/1"`; per face (prefix `face N "key": ` as today) `key must be svf/<rel> (1..6 segments of
  [A-Za-z0-9._-], ending in .SVF or .svf)`, `url must be faces/<rel> for this key`, `group must be the key's directory`,
  `px must equal cell[1]`, `hangul must be an integer 0..2350`, `latin_only must be true or false`, `subset must be true or
  false`, `subset must equal (!jamo && !latin_only && hangul < 2350)`, `latin_only requires jamo false and hangul 0`,
  `family must be a string of 1..256 characters for a listed face`, `family, style and variant must be strings of at most
  256 characters`; after the loop `faces.json: 65 distinct px values, the limit is 64`.

- [ ] **Step 1: Failing cases.** In check.mjs extend `case index`'s `[what, edit, want]` table with one row each:
  `format` deleted; `format` `"svf-fonts-web-index/2"`; `url` of face 1 set to face 2's url; `key` `svf/dos/../x.SVF`;
  `key` `svf/dos/A B.SVF`; `group` `"nope"`; `px` `cell[1] + 1`; `subset` flipped on NGOTB16; `latin_only: true, hangul: 5`
  on COUSB24; `family: ""` on NGOTB16; `hangul: 3000`; 65 distinct `px` (set faces 0..64 to `px` 100..164 with matching
  `cell[1]`). Each: `ready` rejects with the message above, the status line shows it, `#faces li` count 0. Add `case
  default variant` on its own `?manual` page: `defaultVariant` gives `svf/dos/NEODG16.SVF` for `("Neo Dunggeunmo", "", 16)`,
  `svf/jamo-extra/GOTHB16A.SVF` for `("Gothic A1", "Bold", 16)`, `svf/dos/GBATB23.SVF` for `("Gowun Batang", "Bold", 24)`,
  `svf/dos/NGOTB16.SVF` for `("NanumGothic", "Bold", 16)`, `svf/dos/NGOTB17A.SVF` for `("NanumGothic", "Bold", 24)`,
  `svf/dos/PAPER18A.SVF` for `("Paperlogy", "Regular", 18)` (see the note), `null` for `("Coustard", "Bold", 28)`;
  `families(18)` names no `latin_only` key; `sizes()` equals `[16, 18, 20, 22, 24, 32, 36, 40, 48, 54]`;
  `families(16).length === 33`, names unique and sorted case-insensitively; `pick('svf/dos/COUSB24.SVF')` rejects with a
  message containing the key and `chain()` is unchanged. Second page, `faces.json` routed: `svf/jamo-extra/GOTHB16.SVF`
  given `bpp: 8` -> `defaultVariant("Gothic A1", "Bold", 16) === 'svf/jamo-extra/GOTHB16.SVF'`; NGOTB16's family set to
  `"__proto__"` and style to `"constructor"` -> `families(16)` holds a row with that `family` and `name`, the page has no
  `pageerror`, and `families(16).length` is still 33 (NGOTB15 keeps "NanumGothic Bold").
  **Note on PAPER18A:** the spec's example says PAPLG18, but its own rule ranks by glyph count after bpp / composition /
  cell: PAPER18A (2 bpp, jamo, 18x18, 1215 glyphs) beats PAPLG18 (same, 1103). The plan follows the rule; the controller
  reports the discrepancy to the user with the plan. If the user prefers PAPLG18, the rule (not this test) changes.
  Add `'default variant'` to the names `TestPage.test_cases` asserts.
- [ ] **Step 2: Run** `python3 -m unittest tools.test_web_picker -k TestPage` -> FAIL (`case index` rows accepted,
  `defaultVariant` undefined).
- [ ] **Step 3: Implement** `checkIndex` additions, `isLeft`, `famKey`, `rankFace`, `state.fams`, the five public calls.
- [ ] **Step 4: Run** `-k TestPage` -> PASS (every existing case still passes: nothing in the DOM changed yet).
- [ ] **Step 5: Commit** `web: faces.json family fields validated; listed(), sizes(), families(), defaultVariant(), pick()`.

### Task 3: Left panel: size chips, family listbox, variant strip, search, notice, view()

**Files:**
- Modify: `web/index.html` (the list section), `web/style.css`, `web/picker.js` (`buildList`, `filterList`,
  `markSelected`, `markLacking`, `ui.chain`, `start`), `web/test/check.mjs` (rewrite C, D, dom, marks, bad face, budget;
  new cases sizes, keyboard), `tools/test_web_picker.py` (`TestPage.test_cases` names)

**Interfaces:**
- Consumes: Task 2.
- Produces: DOM: `#f-name` (kept), `#count`, `#sizes` (`role="radiogroup"`, `aria-label="Size (face file height)"`, one
  `<button role="radio" aria-checked data-px>` per size, `title` `"33 families, 44 faces"`), `#faces` (`<ul role="listbox"
  aria-label="Families">`, one `<li role="option" id="fam-<n>" data-fam=famKey data-key=<picked face key>>` per family of
  the shown size: `.name`, `.count` badge (`· 4`, `title` `"1 precomposed, 3 jamo sets"`) when more than one variant,
  `.lack` mark, `.tags` role tags; no interactive child), `#variants` (`role="radiogroup"`, `aria-labelledby` the selected
  row's name element, `hidden` when no row of the shown size is selected; one `<button role="radio" data-key>` per face in
  `fam.faces` order with the differing axes in its label and the file name in `<small>`; `#variants-sub` the subtitle "all
  1 bpp jamo sets, 16x16"), `#also` (the "also at 22 px, 24 px" line of buttons, hidden when empty), `#notice` (`<p
  role="status">` under the header). State: `state.px` (the pressed size or `null`), `state.selRow` (famKey of the
  selected row or `null`). Module functions: `showSize(px)` (presses the chip, rebuilds `#faces` and `#variants`, no
  prefetch), `followChain()` (after any select: if the Hangul face is a left-list face, `showSize(f.px)` when `f.px !==
  state.px`, select its row and chip; else keep `state.px`, deselect the row, hide the strip), `setNotice(text)`,
  `rowMark(fam)`. Public: `picker.setSize(px)` -> `Promise<{px, fetched: 0, held: 0, skipped: 0, failed: 0, stopped:
  false}>` in this task (rejects `setSize: no faces of <px> px` for a px not in `sizes()`; Task 5 adds the loop and the real
  counts), `picker.view()` -> `{px, family, style, variant, hangul, latin, same, listed}` (`same = latin === hangul &&
  listed`; `listed` = the Hangul face is a left-list face; family/style/variant of the Hangul face when listed, else
  `""`), `picker.notice()` -> `#notice` text. Default: `DEFAULT_HANGUL = 'svf/dos/NGOTB16.SVF'` (one default fills both slots).
  Mark text per face: `-n`, `!` (failed to open), and Task 5's `?`; a row's mark is its picked face's (`data-key`), its
  `title` lists `FILE -n` / `FILE !` / `FILE ?` per variant (`"NGOTB16.SVF -0, NGOTB15.SVF -3"`). Chip labels: `2 bpp` /
  `1 bpp`, `precomposed` / `jamo set`, the cell as `18x24` when not square or when cells differ, the `variant` tag; an axis
  equal across the family's chips goes to `#variants-sub` instead. Chip click handlers call `stopPropagation()`.
  Keyboard: size and variant groups Left/Right/Up/Down move and apply, Home/End; listbox `aria-activedescendant` with
  Up/Down/Home/End, Enter/Space picks, letters type-ahead; focusing the listbox activates the selected row, else the first
  visible row. The search filters the shown size's rows by family, style,
  variant and file name; `#count` shows `33 families · 44 faces` or `2 of 33`.

- [ ] **Step 1: Failing cases.** Rewrite in check.mjs: `case C` (non-manual page: after `ready`, `chain()` is
  `{latin: 'svf/dos/NGOTB16.SVF', hangul: 'svf/dos/NGOTB16.SVF'}`, chip 16 `aria-checked="true"`, the selected row's
  `.name` is `NanumGothic Bold`, the pressed variant chip's `data-key` is NGOTB16, `view().same === true`; a later select
  is kept); `case D` (press chip 18, type `PAPLG18` in `#f-name`: exactly one visible row, name `Paperlogy Regular`; click
  it: `#variants` shown and holds a chip whose text contains `PAPLG18.SVF`; clear the search, press chip 16, type
  `PAPLG18`: no visible row and `#also` shows a button `18 px` whose click presses chip 18 and shows that row again; then
  the MONO / RGB565 colour steps as today); `case dom` (replace the per-row button steps: click row `NanumGothic Bold` ->
  chain NGOTB16 x2, row `aria-selected`, chip pressed; click chip `NGOTB15.SVF` -> chain NGOTB15 x2, row still selected;
  the rows map asserts `data-role` and tags only; the rest of the case unchanged); `case marks` (chain via
  `select({latin: NGOTB16, hangul: PAPLG18})`: the shown size is 18 and every row's `.lack` equals `lacking()` of its
  `data-key` (absent when 0); `prefetch` of one more 18 px face adds that face's row mark); `case bad face` (the bad face
  is `svf/dos/NEODG16.SVF`, zeroed header on its route; chain `pick('svf/dos/NGOTB16.SVF')`; after `prefetch(NEODG16)` and
  a render, row `Neo Dunggeunmo` shows `!`; the length set is `{218916, 127856}`; the other assertions as today); `case
  budget` (A = PAPLG18, B = NGOTB16, C = `svf/dos/PAPLB18A.SVF`, all left-list; same assertions). New `case sizes`
  (`?manual`): `#sizes` chips' `data-px` equal `sizes()`; no `subset` key appears in any `#faces li[data-key]`, `#latin
  option` or `#hangul option` (selectors are Task 4: assert the list only here, the selectors there); after `setSize(16)`
  `#faces li` count is 33 and the names are unique and sorted; `setSize(16)` resolves `{px: 16, fetched: 0, held: 0,
  skipped: 0, failed: 0, stopped: false}`; synthetic step on a second page with `faces.json` routed so NGOTB15's `cell`,
  `glyphs`, `variant` equal NGOTB16's: the page loads, row `NanumGothic Bold` has two chips whose texts contain
  `NGOTB15.SVF` and `NGOTB16.SVF`. New `case keyboard`: focus the first size chip, `ArrowRight` presses chip 18 and
  `#faces li` count changes; focus `#faces`, `ArrowDown` moves `aria-activedescendant` without changing `chain()`, `Enter`
  picks that row (`chain().hangul === families(18)[1].default`); `End` then `Home` on the listbox move the active row to
  the last and first option; in `#variants` `ArrowRight` applies the next chip; typing `pa` on the listbox moves the active
  row to the first family whose name starts with `Pa`. Add `'sizes'`, `'keyboard'` to `test_cases`.
- [ ] **Step 2: Run** `-k TestPage` -> FAIL (no `#sizes`).
- [ ] **Step 3: Implement** the HTML (remove `#f-group`, `#f-px`, `#f-bpp`, `#f-jamo`; add `#sizes`, `#variants`,
  `#variants-sub`, `#also`, `#notice`), the CSS (chips as `.chips button[aria-checked="true"]`, option rows without the
  `.use` column), and picker.js: `buildList` -> `showSize`, `filterList` over the shown size with `#also`, `followChain`
  called from `ui.chain`, `markLacking` over rows and chips, `setSize`, `view`, `notice`, the keyboard handlers,
  `DEFAULT_HANGUL`. `start()` opens the default pair and calls `showSize(16)` through `followChain`.
- [ ] **Step 4: Run** `-k TestPage` -> PASS; `-k TestIndex` PASS.
- [ ] **Step 5: Commit** `web: size chips, family listbox and variant strip replace the flat face list; default NGOTB16 in both slots`.

### Task 4: Preview selectors, "= list" badges, per-slot notes, hidden faces, cards

**Files:**
- Modify: `web/index.html` (the chain row, the card), `web/style.css`, `web/picker.js` (`buildControls`, `ui.chain`,
  `faceCard`, `showCards`), `web/test/check.mjs` (new cases pick, hidden in chain; case B licence step),
  `tools/test_web_picker.py` (`test_cases` names)

**Interfaces:**
- Consumes: Task 3 (`followChain`, `view`, `setNotice`).
- Produces: `#latin` / `#hangul` options in `<optgroup label="16 px">` per size, option text `Family Style · 2 bpp
  precomposed 16x16 · FILE` (the chip words; `#latin` also offers Latin-only faces in their size groups suffixed `Latin
  only`, and keeps `(none: the Hangul face's own ASCII)`); `#latin-badge` / `#hangul-badge` (`<span class="badge
  same">= list</span>`, both shown iff `view().same`); `#latin-note` / `#hangul-note` (one element each; states: "Latin:
  NanumGothic Bold 16 px (list shows 18 px)" with a button that calls `showSize(16)` without changing the chain; "Latin:
  Coustard Bold 28 px is a Latin-only face: not in the list" plain; "Latin: NGOTB14 14 px is a hidden subset face: not in
  the list" plain; "Hangul: COUSB24 28 px is a Latin-only face: not in the list"; "Hangul: NGOTB14 14 px is a hidden
  subset face: not in the list"; empty otherwise); a transient option `FILE (hidden: subset face)` / `FILE (Latin-only
  face)` added to the slot's select while a non-offered face is in that slot, removed when the slot changes. Cards: `<dl>`
  gains `family`, `style`, `variant` (the tag or `-`) rows at the top; one card titled `Latin and Hangul` with one licence
  pane when `latin === hangul`. Selector changes call `select({latin: new, hangul: current})` as today and start a prefetch
  only through Task 5's hook (`ui.afterPick`, a no-op until then).

- [ ] **Step 1: Failing cases.** `case pick` (`?manual`, `setSize(16)` first): click row `Neo Dunggeunmo` -> `chain()`
  `{latin: 'svf/dos/NEODG16.SVF', hangul: 'svf/dos/NEODG16.SVF'}`, both selects' `value` that key, both badges visible,
  `view().same === true`; click chip `NEODG16C.SVF` -> chain NEODG16C x2 (not NEODG16: the row handler did not fire);
  `selectOption('#latin', 'svf/dos/NGOTB16.SVF')` -> `chain().latin` NGOTB16, hangul NEODG16C, no badge, row and chip still
  NEODG16C; `selectOption('#latin', 'svf/dos/COUSB24.SVF')` -> `#latin-note` text `Latin: Coustard Bold 28 px is a
  Latin-only face: not in the list`, no `button` inside it, chip 16 still pressed, the only new face request is COUSB24;
  `setSize(18)` then `selectOption('#latin', 'svf/dos/PAPLG16.SVF')` -> `#latin-note` `Latin: Paperlogy Regular 18 px is a
  Latin-only face: not in the list`; `selectOption('#latin', 'svf/dos/NGOTB16.SVF')` with the list on 18 -> `#latin-note`
  `Latin: NanumGothic Bold 16 px (list shows 18 px)` with a button whose click presses chip 16 and leaves `chain()`
  unchanged; a row click sets both again. `case hidden in chain` exactly as the spec: `select({latin: null, hangul:
  'svf/dos/NGOTB14.SVF'})` -> `#hangul` has an option `NGOTB14.SVF (hidden: subset face)` and that value, `#hangul-note`
  `Hangul: NGOTB14 14 px is a hidden subset face: not in the list`, no chip `aria-checked="true"`, no row selected,
  `#variants` hidden, `view().listed === false`, no face request other than NGOTB14; then `select({latin:
  'svf/dos/NGOTB14.SVF', hangul: 'svf/dos/PAPLG18.SVF'})` -> chip 18, row `Paperlogy Regular`, chip PAPLG18, `#latin` shows
  the transient option, `#latin-note` the hidden text with no button, no badges; then `select({latin:
  'svf/dos/PAPLG18.SVF', hangul: 'svf/dos/NGOTB14.SVF'})` -> no row selected, chip 18 still pressed, `#hangul-note` the
  hidden text; `select({latin: null, hangul: 'svf/dos/COUSB24.SVF'})` -> `#hangul` option `COUSB24.SVF (Latin-only face)`,
  `#hangul-note` `Hangul: COUSB24 28 px is a Latin-only face: not in the list`, `view().listed === false`; then
  `pick('svf/dos/NGOTB16.SVF')` removes every transient option from both selects. `case sizes` gains: no `subset` key in
  `#latin option` / `#hangul option`; `svf/dos/COUSB24.SVF` and `svf/dos/PAPLG16.SVF` are `#latin` options and not `#hangul`
  options. Case B licence step: after `select({latin: null, hangul: 'svf/iolo/HGKEY6J.SVF'})` the card shows exactly three
  `details` with summaries `IOLO.TXT`, `LICENSE-MIT.txt`, `LICENSE-OFL.txt` in that order, each `pre` starting with
  `iolo 6x2x1 / 8x4x4 jamo-set faces`, `The MIT License (MIT)`, `Copyright (c) 2025 Dongsu Jang` (`startsWith`; the OFL line
  continues `<iolo@kakao.com>`), none `loading...`; with `latin === hangul` there is one `.facecard` titled `Latin and
  Hangul` and its `dl` starts with `family`, `style`, `variant`. Add `'pick'`, `'hidden in chain'` to `test_cases`.
- [ ] **Step 2: Run** `-k TestPage` -> FAIL (no optgroups, no notes).
- [ ] **Step 3: Implement** `buildControls` (optgroups, Latin-only in `#latin` only), `ui.chain` (badges, notes,
  transient options, `followChain`), `faceCard` / `showCards`.
- [ ] **Step 4: Run** `-k TestPage` -> PASS.
- [ ] **Step 5: Commit** `web: preview selectors by size, "= list" badges, Latin/Hangul notes, hidden faces in a slot, family rows on the card`.

### Task 5: Prefetch protocol: heap lock, pending, keep set, the loop, setSize, coalesced scan, marks

**Files:**
- Modify: `web/picker.js` (`state`, `makeRoom`, `fetchFace`, `selectNow`, `select`, `lacking`, `markLacking`, `setSize`,
  `prefetch`, new `heapJob`, `prefetchSize`, `queueScan`), `web/test/check.mjs` (cases prefetch, prefetch priority, prefetch
  budget, select during eviction, scan during select; case C's prefetch assertion), `tools/test_web_picker.py`
  (`test_cases` names), `docs/superpowers/specs/2026-10-20-face-selection-design.md` (the two case paragraphs)

**Interfaces:**
- Consumes: Tasks 3-4 (`showSize`, `rowMark`, `setNotice`, `ui.afterPick`).
- Produces: `class BudgetError extends Error` with `code = 'budget'` (thrown by `makeRoom` instead of `fail`; message
  unchanged); `makeRoom(need, keep)` protects, at call time, `state.latin`, `state.hangul`, every key of `state.pending`
  and `keep`; `state.pending` (array of keys or `null`): `selectNow` sets it as its first statement, clears it in `finally`;
  `state.heap` (promise chain) and `heapJob(fn)` (`const run = state.heap.then(fn); state.heap = run.catch(() => {});
  return run;`): `fetchFace` does `makeRoom` + `alloc` + copy inside `heapJob` after the network read, re-reading the chain
  and `pending` there; `selectNow`'s reset + opens run inside one `heapJob`; `state.selectIdle` (a promise resolved while
  the select queue is empty; `select()` and `pick()` count in and out); `state.prefetchGen` (bumped by every chip move:
  `showSize` of another px, whatever the cause), `state.prefetchRun` (`state.prefetchRun = state.prefetchRun.then(() =>
  prefetchSize(px, gen))`, assigned synchronously inside `setSize`); `prefetchSize(px, gen)` -> `{px, fetched, held,
  skipped, failed, stopped}`: over `families(px)` rows top to bottom, `fam.faces` order; a face in `state.files` counts
  `held`; before each other face `await state.selectIdle`, re-check `gen`, `fetchFace(key, keepKeys)` with `keepKeys` =
  every left-list key of `px`; `BudgetError` -> `skipped` + mark `?` (`title` `not fetched: the 64 MiB face budget is
  full`), any other error -> `failed` + mark `!` (`title` the message); each copied face calls `queueScan()`; never
  rejects; the summary `16 px: 41 of 44 faces fetched, 3 over the face budget, 0 failed` goes to `setNotice`.
  `picker.setSize(px)`: `showSize(px)`, the loop, then `await state.heap` (the pending scan) before resolving.
  `queueScan()`: one pending `heapJob(() => markLacking())` at a time (`state.scanQueued` flag); `ui.paint` calls
  `queueScan()` instead of `markLacking()` directly. `lacking(text = state.text, keys)`: with `keys` scans only those plus
  the chain; `markLacking` passes the shown size's left-list keys plus the chain; the scan reads `state.latin` /
  `state.hangul` when it runs (the rule: **the scan reads the chain at run time**; nothing is captured when the job is
  queued), and stays synchronous from its first `svfw_reset` to its restore. `picker.prefetch(key, keep = [])` keeps the
  select queue. `ui.afterPick` (Task 4's hook) becomes "start the prefetch of the shown size": a chip press, a row or chip
  pick, a selector change, the "list shows" button and the non-manual page load call `setSize(state.px)` (a driver's
  `select` / `pick` never does). A `select` of another size's face can evict shown-size faces: their marks become `?` with
  `title` `evicted: pick the size again to fetch`. Test hooks: `picker.prefetching()` -> `state.prefetchRun`,
  `picker.idle()` -> a promise that resolves when the heap chain is empty (marks are painted by a queued job now, so
  every case that reads a mark right after `render()` — marks, bad face, pick, and the new ones — awaits `idle()` first).
  Mark storage: `state.marks: Map<key, {mark: '?' | '!', title}>`, cleared for a key when it is fetched.

- [ ] **Step 1: Failing cases** (each its own `?manual` page unless said; byte numbers also derived in the test from
  `faces()` and asserted equal to the literals):
  - `case prefetch`: `page.on('request')` from a blank page; `setSize(16)` resolves `{px: 16, fetched: 44, held: 0, skipped:
    0, failed: 0, stopped: false}`; every left-list 16 px key is in `faceMemory().keys`; every row's and chip's mark equals
    `lacking()` for its face (absent when 0); each 16 px file requested once; `setSize(24)` then `setSize(16)` request no
    new 16 px file and the second resolves `held: 44`; `setSize(16)` issued while `setSize(24)` runs: the 24 call resolves
    `stopped: true`, no `pageerror`; then `pick('svf/dos/NGOTB16.SVF')`, `await idle()`, wrap `_svfw_open`,
    `setText('Hero 나'); render(); await idle()`: between 1 and 46 opens (44 shown-size scans + 2 restores; without the
    key filter the 27 faces of 24 px would be scanned too).
  - `case prefetch priority`: fresh page, default budget; `setSize(24)` not awaited; `pick('svf/dos/TBMY24.SVF')`
    (38,181 B, last of the 24 px order): the chip stays 24; `faceMemory().keys.length` grows by at most 2 between the pick's
    call and its resolution; the pick resolves before `setSize`; `setSize` resolves `{fetched: 26, held: 1, skipped: 0,
    failed: 0, stopped: false}`; a pangram render has err 0, ink > 0; `faceMemory().keys` holds TBMY24; `pixels()` equals
    TBMY24 x2 rendered on a fresh page.
  - `case prefetch budget`: `pick('svf/iolo/HGKEY6J.SVF')` (12,921 B); `setFaceBudget(51694)` (= 12921 + 3 * 12921 + 10);
    `setSize(16)` resolves `{fetched: 2, held: 1, skipped: 41, failed: 0}` (AD248J 20,453 -> 33,374 held; HLINK6J 12,921 ->
    46,295; the test replays the loop over `families(16)` and asserts the same three numbers); skipped rows show `?`;
    `notice()` matches `/2 of 44 .* 41 over the face budget/`; `pick('svf/iolo/ROMAX6J.SVF')` succeeds, AD248J leaves
    `faceMemory().keys`, ROMAX6J's row mark appears and row `AD24` shows `?` with `title` `evicted: pick the size again to
    fetch`; `pick('svf/dos/NGOTB16.SVF')` (218,916 B) rejects with `face memory`, `chain()` stays ROMAX6J x2.
  - `case select during eviction`: X = `svf/dos/HWPHG24.SVF` (38,097), Y = `svf/iolo/WCOMM6J.SVF` (12,921), P =
    `svf/iolo/AD248J.SVF` (20,453); `setFaceBudget(52000)` (X + Y = 51,018 fits, X + P = 58,550 does not); routes for P and
    Y each hold until a promise the test resolves. Steps: `setSize(16)` not awaited; **await P's request at the route
    before calling select** (the residual: in one tick the loop would wait on `selectIdle` behind a select whose Y is held);
    `select({latin: X, hangul: Y})` not awaited; poll until `faceMemory().keys` includes X and Y's request arrived; release
    P; poll (5 s) until **P's family row (`AD24`)** shows `?` (the variant strip is hidden while no row is selected, so the
    chip is not in the DOM: assert the row only); release Y; await the select, then `setSize`. Assert: the select resolved;
    `chain()` `{latin: X, hangul: Y}`; `faceMemory().keys` includes X and Y, not P; `setSize` resolved `{fetched: 0, held: 1,
    skipped: 43, failed: 0}`; a pangram render err 0 with `pixels()` equal to the same chain on a fresh default-budget page;
    no `pageerror`. Failed-open step (Review Focus 3), same page: route `svf/dos/NEODG16.SVF` with a zeroed header;
    `setFaceBudget(127856 + 12921 + 10)`; `select({latin: null, hangul: 'svf/dos/NEODG16.SVF'})` rejects (`svfw_open`);
    then `prefetch('svf/iolo/HGKEY6J.SVF', [])` resolves and `faceMemory().keys` lacks NEODG16 (pending was cleared, so the
    failed face could be evicted).
  - `case scan during select` (the residual, replacing the spec's step list): `pick('svf/dos/NEODG16C.SVF')` (24,809 B),
    pangram text; wrap `module()._svfw_reset` / `_svfw_open` logging `['reset']` / `['open', slot, len]`; routes held: P =
    `svf/iolo/AD248J.SVF` (20,453, the first 16 px face) and Y2 = `svf/jamo-extra/NDGPR16.SVF` (32,791); X =
    `svf/dos/HWPHG24.SVF` (38,097). Steps: `setSize(16)` not awaited; await P's request; `select({latin: X, hangul: Y2})`
    not awaited; poll until `faceMemory().keys` includes X; record `log.length` as `at`; release P; poll until the log after
    `at` contains, in order, `reset`, `open(0, 20453)`, `reset`, `open(0, 24809)`, `open(1, 24809)` (P's scan, then the
    restore of both NEODG16C slots; P is identified as the face in flight, not by its length, which nine iolo faces share);
    release Y2; await the select, then `setSize`. Assert: `chain()` `{latin: X, hangul: Y2}`; `_svfw_info(0)` cell 24x24,
    `_svfw_info(1)` 16x16; from the select's `reset`, `open(0, 38097)`, `open(1, 32791)` onward every restore opens 38,097
    then 32,791 and 24,809 never appears; no scan `open` between the select's `reset` and its last `open`; render err 0 and
    `pixels()` equal to the chain on a fresh page; marks equal `lacking()`; `setSize` resolved `{fetched: 42, held: 2,
    skipped: 0, failed: 0}`. Rationale (write it as the case comment): the scan and the select's reset/opens are both
    synchronous, so they cannot interleave; the case catches a scan job that read the chain (or `keys`) when it was
    queued rather than when it ran, which would restore NEODG16C after the select; the rule is "the scan reads the chain
    at run time"; the lock placement is defence in depth for any future asynchronous step inside the scan.
  - `case C` gains: `await picker.prefetching()` resolves `fetched: 43, held: 1` and 44 keys are in `faceMemory()`.
  - Cases marks, bad face and pick: insert `await P.idle()` after each `render()` whose marks are read next.
  - Add `'prefetch'`, `'prefetch priority'`, `'prefetch budget'`, `'select during eviction'`, `'scan during select'` to
    `test_cases`.
- [ ] **Step 2: Run** `-k TestPage` -> FAIL (`setSize` fetches nothing).
- [ ] **Step 3: Implement** the Interfaces block. Keep `fetchFace`'s pre-network `makeRoom` (it now protects `pending`).
- [ ] **Step 4: Run** `-k TestPage` -> PASS; run check.mjs three times in a row by hand (`node web/test/check.mjs web/dist
  web/test/out`) and confirm the five new cases pass each time (they are timing-sensitive by design).
- [ ] **Step 5: Spec sync.** Edit the spec's "case select during eviction" (await P's request before `select`; the row,
  not the chip, shows `?`) and "case scan during select" (the hold-P step list, `open(1, 24809)` in the restore, the
  rationale above) to match the cases; add a line to the Revision 4 paragraph: "Plan sync (Task 5): ...".
- [ ] **Step 6: Commit** `web: prefetch a whole size under a heap lock; makeRoom protects the chain and the pending selection; marks on every family row`.

### Task 6: Bounded reads and the prefetch error classes

**Files:**
- Modify: `web/picker.js` (`readBounded`, `fetchFace` error messages), `web/test/serve.mjs` (`startServer` opts),
  `web/test/check.mjs` (case prefetch errors; the no-stream step), `tools/test_web_picker.py` (`test_cases`),
  `docs/superpowers/specs/2026-10-20-face-selection-design.md` (the one-huge-chunk sentences)

**Interfaces:**
- Consumes: Task 5 (`prefetchSize`, marks, `BudgetError`).
- Produces: `readBounded(r, limit, what, exact)`: a chunk that would take the running total over `limit` is **not**
  pushed (not even its first bytes); `reader.cancel()` is called at once and `${what}: more than ${limit} bytes` thrown;
  everything else as today (header reject, exact length, no `arrayBuffer()` when a stream exists). `serve.mjs` opts:
  `chunked: [paths]` now writes the body **paced** (16 KiB per 5 ms, each write awaiting `drain`) without `Content-Length`;
  `big: {path: {bytes, declared}}` sends a zero-filled body of `bytes` (declared: with `Content-Length`; else chunked and
  paced); `status: {path: code}` answers that status with an empty body; the returned object gains `stats()` ->
  `{[path]: {written, completed}}`. check.mjs init script (`readerTaps`): wraps `window.fetch` (tags the returned
  `Response` with the request URL in a `WeakMap`, and, for the one-huge-chunk URL, substitutes and tags the replacement
  Response), `Response.prototype.clone` (the clone inherits the URL), the `Response.prototype.body` getter (tags the
  stream), `ReadableStream.prototype.getReader` (tags the reader), `ReadableStreamDefaultReader.prototype.read` /
  `.cancel` and `Response.prototype.arrayBuffer`, crediting `window.__reads[url] = {bytes, lastChunk, chunks, cancelled,
  arrayBuffer}`.

- [ ] **Step 1: Failing case** `case prefetch errors` on a server with `status: {'/faces/iolo/AD248J.SVF': 404}`,
  `redirect: {'/faces/dos/NEODG16.SVF': '/faces/dos/NEODG16.SVF?r'}`, `big: {'/faces/dos/SANGAM16.SVF': {bytes: 9000000,
  declared: true}, '/faces/dos/TBTHG16.SVF': {bytes: 9000000, declared: false}}`, and a page route for
  `**/faces/dos/HTERM16.SVF` fulfilling the body minus its last byte with a matching `Content-Length`; the init script
  above with the huge-chunk URL `faces/dos/TBMY24.SVF` (one 6,000,000-byte `Uint8Array` enqueued, then close; same
  `content-type`, no `Content-Length`). `setSize(16)` resolves `{fetched: 39, held: 0, skipped: 0, failed: 5}`; rows
  `AD24`, `hanterm`, `Neo Dunggeunmo`, `san 1.0 Gam`, `Taebaek Gothic` show `!` with `title` containing `HTTP 404`, `the
  index says`, `redirect`, `over the limit`, `more than 20497 bytes` respectively; the other rows carry marks equal to
  `lacking()`; `notice()` contains `5 failed`; `faceMemory().bytes === 2296637` (the test sums the 39 good faces' `bytes`
  and asserts equality with the literal) and no failed key in `faceMemory().keys`; `__reads` for SANGAM16: `bytes === 0`,
  `chunks === 0`; for TBTHG16: `bytes - lastChunk <= 20497`, `cancelled === 1`; `arrayBuffer === 0` for every face URL;
  `chunks > 0` for every good face; `stats()['/faces/dos/TBTHG16.SVF']` has `completed === false` and `written <
  9000000`. One-huge-chunk (deterministic, the residual): record `faceMemory()` and `module().HEAPU8.byteLength`;
  `prefetch('svf/dos/TBMY24.SVF', [])` rejects with `more than 38181 bytes`; `__reads` for it: `chunks === 1`, `bytes -
  lastChunk === 0`, `cancelled === 1`; `faceMemory()` (bytes and keys) and `HEAPU8.byteLength` unchanged (no
  `measureUserAgentSpecificMemory`: serve.mjs sends no COOP/COEP, so it would always be skipped). No-stream step: a
  **fresh** `?manual` page with `Response.prototype.body` hidden (as case no stream) on a server with only the two `big`
  routes: `setSize(16)` resolves `{fetched: 42, held: 0, skipped: 0, failed: 2}`, the two `title`s say unbounded (chunked) /
  over the limit (declared), `arrayBuffer === 0` for those two URLs only. No `pageerror` anywhere. Add `'prefetch errors'`
  to `test_cases`.
- [ ] **Step 2: Run** `-k TestPage` -> FAIL (`big` unknown; the huge chunk is pushed before the check).
- [ ] **Step 3: Implement** serve.mjs options and `stats()`, the `readBounded` drop rule, the init script.
- [ ] **Step 4: Run** `-k TestPage` -> PASS; the existing `case no stream` and `case transport` still pass with the
  paced `chunked`.
- [ ] **Step 5: Spec sync.** In the spec's "case prefetch errors" replace the `measureUserAgentSpecificMemory` sentence by
  the heap-length assertion and add that the fetch wrapper tags the substituted Response and `Response.clone()` results.
- [ ] **Step 6: Commit** `web: readBounded drops the chunk that crosses the limit; paced and oversized bodies in serve.mjs; the prefetch errors case`.

### Task 7: URL state

**Files:**
- Modify: `web/picker.js` (`start`, new `readUrl`, `writeUrl`), `web/test/check.mjs` (case url),
  `tools/test_web_picker.py` (`test_cases`)

**Interfaces:**
- Consumes: Tasks 3-5 (`select`, `setScale`, `setNotice`, `setSize`).
- Produces: `readUrl() -> {latin, hangul, num, den, notices: [string]}` over `location.search`: the whole query over 2048
  characters or any value over 256 -> everything ignored, notice `URL ignored: too long`; `hangul`: a `byKey` hit that is a
  left-list face, else the default with `URL: no face <key>; the default opened` / `URL: <key> is a Latin-only face; the
  default opened` / `URL: <key> is a hidden subset face; the default opened`; `latin`: absent -> same as hangul; present
  without `hangul` -> hangul default; empty -> `null`; a `byKey` hit that is not subset -> that key; else `null` with `URL:
  no face <key>; Latin none` / `URL: <key> is a hidden subset face; Latin none`; `scale`: `/^\d{1,2}\/\d{1,2}$/` both 1..16,
  else 1/1 with `URL: scale <value> ignored`. `writeUrl()` after every successful select or scale change:
  `history.replaceState` with `hangul`, `latin` (empty for none), `scale=N/D`, every other parameter (`manual` included)
  kept. `?manual`: no default, no URL chain, no prefetch. `ready` never rejects for a URL fault; notices are joined with
  `; ` into `#notice`.

- [ ] **Step 1: Failing case** `case url` (each query its own page, non-manual unless said): `?hangul=svf/dos/TBMY24.SVF&latin=&scale=2/1`
  -> `chain()` `{latin: null, hangul: TBMY24}`, `settings()` num 2 den 1, chip 24 pressed; `?hangul=svf/dos/TBMY24.SVF` ->
  latin TBMY24; `?latin=svf/dos/HWPHG24.SVF` -> hangul NGOTB16, latin HWPHG24, chip 16; `?hangul=svf/dos/NOPE.SVF` ->
  default, `notice()` contains `svf/dos/NOPE.SVF`; `scale=bad`, `scale=0/0`, `scale=17/1` -> 1/1 and a notice containing
  `scale`; a query of 3,000 characters -> default chain, `notice()` `URL ignored: too long`; `?hangul=svf/dos/COUSB24.SVF`
  and `?hangul=svf/dos/NGOTB14.SVF` -> NGOTB16 x2, notice names the key as `Latin-only` / `hidden subset`, no request for
  that file; `?hangul=svf/dos/TBMY24.SVF&latin=svf/dos/COUSB24.SVF` -> latin COUSB24; `?latin=svf/dos/NGOTB14.SVF` -> latin
  `null` with a notice; after `pick('svf/dos/NEODG16.SVF')` `location.search` contains `hangul=svf%2Fdos%2FNEODG16.SVF` (or
  the unescaped form: compare with `new URLSearchParams(location.search).get('hangul')`) and `scale=1%2F1`; `page.reload()`
  restores the same `chain()` and scale; `?manual&hangul=svf/dos/TBMY24.SVF&scale=bad` -> `chain()` `{latin: null, hangul:
  null}`, no `.SVF` request, `notice()` contains `scale` (Review Focus 4). Add `'url'` to `test_cases`.
- [ ] **Step 2: Run** `-k TestPage` -> FAIL (no URL read).
- [ ] **Step 3: Implement** `readUrl`, `writeUrl`, the `start()` flow (URL -> `select` -> `followChain` -> prefetch unless
  manual).
- [ ] **Step 4: Run** `-k TestPage` -> PASS.
- [ ] **Step 5: Commit** `web: the URL carries the chain and scale; bounded, validated, every fault a notice`.

### Task 8: Rebuild, look at the page, the whole gate

**Files:**
- Modify: `web/test/check.mjs` (only if a screenshot name is added), `.superpowers/sdd/2026-10-20-face-selection/progress.md`
  (one line), nothing else.

- [ ] **Step 1: Build and look.** `bash web/build.sh` -> prints `... 153 faces ...`; run check.mjs by hand; open
  `web/test/out/page.png` and `page-ui.png` with the Read tool and confirm: the size chips with 16 pressed, the 33 family
  rows, the variant strip under `NanumGothic Bold` with two chips, both `= list` badges, the `#notice` prefetch summary
  `16 px: 44 of 44 faces fetched, 0 over the face budget, 0 failed`, and no row of the old flat list. Note what was seen in
  the commit message.
- [ ] **Step 2: Gate.** `python3 -m unittest discover -s tools -p 'test_*.py'` -> every test PASS, none of
  `TestIndex` / `TestModule` / `TestPage` skipped on this host; `make -C c check` -> OK; `git status` shows nothing under
  `web/dist`, `web/test/out`, `web/test/node_modules`; `git diff --stat 84a6c80 -- c/` is empty.
- [ ] **Step 3: Commit** `web: face selection complete: gate green (TestIndex N, TestModule 11, TestCopyFaces 3, TestPage N)`
  with the counts from the run; append to progress.md: `Plan 2026-10-20-face-selection executed: <sha>; gate green;
  wasm-picker plan Tasks 5-6 next with the changes below.`

---

## What changes for the wasm-picker plan's Tasks 5-6 (not re-planned here)

Task 5 (choices and export), per the spec's "Task 5 and Task 6" section:
- The export gains top-level `"order": "per-run"` beside `format` / `created` / `source`; `korean` gains `family`, `style`,
  `variant` from the index entry beside `label` (pairing2svf ignores both); `TestPage::test_export_shape` adds
  `sel["order"] == "per-run"` and the three keys; `TestExportShape` is unchanged.
- The choices table shows `Family Style · variant words` with the file name in small type instead of `label`.
- Stored choices (`svfpicker.choices`) are validated on load (a JSON array of at most 256 objects, strings at most 256
  characters, finite numbers; an unknown `korean.key` kept with a "not in this index" mark; anything else ignored with the
  notice `stored choices unreadable: starting empty`); a storage exception is a notice. check.mjs `case storage` as the
  spec writes it (`'{nope'`, a 300-entry array, a valid list with an unknown key).
- Case C's default is now NGOTB16 in both slots; the export case still selects PAPLG18 over NGOTB16 and GBATB47 by key.

Task 6 (README and gate): `web/README.md` also documents `FAMILIES.tsv` (format, failure rules, `--families`, adding a face
= one `LICENCES.tsv` row + one `FAMILIES.tsv` row), the subset / Latin-only rules and the `mkindex.py` counts line, the
URL parameters and their fallbacks, `#notice`, and the new `window.picker` calls (`listed`, `sizes`, `families`,
`defaultVariant`, `pick`, `setSize`, `view`, `notice`, `prefetch(key, keep)`, `lacking(text, keys)`, `prefetching`). The
card's evidence line adds the `mkindex.py` counts (`153 faces, 120 listed (2 latin-only), 33 subset, 0 unmapped`).
