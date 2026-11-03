# WASM font picker: face selection by size, family and variant (card t_fe9f6c30)

Supplements `2026-10-20-wasm-picker-design.md` (the page, the per-run chain, the export) and changes its "Layout" and
"Controls / Chain" paragraphs and the plan's Tasks 5-6. Everything the earlier design says about the module, the
renderer, the targets, the scale control, presets, the licence pane and the test harness stays. Decisions the user made
on 2026-10-20 are marked **(user)**; the rest are the controller's calls, marked **(my call)**, open to review.

## Revision 4 (2026-10-20, test precision, after the re-reviews of revision 3)

(1) "case select during eviction" sequences its releases: after P is released the test waits until P's row and chip
show the grey "?" skip mark, and only then releases Y, so P's `makeRoom` always runs while the selection is still
pending; a build without `state.pending` (or one whose copy waits on `selectIdle`) now fails deterministically. (2)
"case prefetch errors" bounds that hold for a correct Chromium build: `bytes - lastChunk <= limit` and `cancelled ===
1` on the client; the server paces the chunked body and reports that it never completed; a one-huge-chunk response
(6 MB in one enqueue) is added, with the rule that `readBounded` never appends a chunk that crosses the limit (it is
dropped and the reader cancelled, so retained memory stays under the limit); the reader-to-URL mapping is specified
(wrap `fetch` to tag the Response, the `body` getter to tag the stream, `getReader` to tag the reader, `WeakMap`s), and
`readBounded` stays on `getReader()` / `read()`. (3) a new "case scan during select" forces a `markLacking` scan to
overlap a selection held on a route and asserts the slot contents, the reset/open order and the pixels, so a scan run
outside the heap-lock chain fails. (4) Minors: the no-stream step of the errors case runs on a fresh page with only the
two oversized routes bad ({fetched 42, failed 2}, `arrayBuffer === 0` for those two URLs only); a selection whose Hangul
size is the pressed size is not a chip move (said once in the protocol paragraph); `?latin=` without `hangul=` puts the
default in the Hangul slot; a licence test over a face with three licence files (HGKEY6J). Numbers touched were
re-checked (nothing changed: 20,497 / 20,541 limits, 2,296,637, 0 / 1 / 43, 26 / 1).
Plan sync (Task 5): the cases were written against the build: "case select during eviction" awaits P's request before
the select and asserts the row only; "case scan during select" holds P as listed there; the failed-open step runs on a
fresh `?manual` page with `setFaceBudget(130000)`; the load's prefetch summary counts faces in memory (fetched + held), so
the budget case reads "3 of 44 ... 41 over the face budget"; `setSize` of the size already shown does not rebuild the
list (a pick starts a prefetch of the shown size and focus and scroll must survive). Fix round 1: one in-flight fetch per face, `makeRoom` refuses without evicting when the evictable bytes cannot make room, `BudgetError.name`, `prefetchRun` survives a rejected loop.

## Revision 3 (2026-10-20, test specification and two behaviour gaps, after the re-reviews of revision 2)

The protocol of revision 2 stands; the test cases that exercise it are rewritten so that they can run and fail without
the fix: (1) "case select during eviction" now selects a 24 px Latin face (HWPHG24, 38,097 B, outside the prefetched
size, so only `state.pending` protects it) with a 16 px Hangul face (WCOMM6J, 12,921 B, so the chip stays on 16 and the
loop is not stopped) under a 52,000 B budget, holds both the first prefetched face (AD248J, 20,453 B) and the Hangul
face on routes to force the interleaving, and asserts `skipped >= 1`, the Latin key still in `faceMemory().keys`, and
pixels equal to a fresh page; the paragraph says why a build without `state.pending` fails it. (2) the priority case
picks a 24 px face during the 24 px prefetch (no chip move, no stop) and checks residency and pixels after the loop.
(3) the oversized-response case counts the bytes the page's stream readers delivered and the cancels, and the
`arrayBuffer` calls, per URL (an `arrayBuffer()` implementation fails it); the server reports bytes written. (4) `setSize`
awaits the pending coalesced scan on the heap-lock chain before resolving; nothing runs outside the lock. (5) URL
`hangul=` and `latin=` accept non-subset faces only, and `hangul=` refuses Latin-only faces too: fallback to the default
with a notice, added to case url; a driver's `select` that puts a Latin-only face in the Hangul slot gets the hidden-face
treatment. Minors: `setSize` calls chain on `state.prefetchRun` stored synchronously (Opus m1); the loop calls the
internal `fetchFace`, `picker.prefetch` stays on the select queue (Opus m2); the errors case asserts the exact face
memory and names five default-variant faces of five families (Opus m3, agy); `MAX_FIELD` is named as picker.js's
constant (256). Every number a test asserts was re-checked against the appendix order and the file sizes under `svf/`.

## Revision 2 (2026-10-20, after the re-reviews of revision 1)

Fixed: (Opus N1, SOL critical) `makeRoom` can no longer free a face a selection has fetched but not yet opened, nor the
chain a selection has just installed: every `makeRoom` protects, at call time, the current chain plus `state.pending`
(the keys of the selection in progress), whatever keep list the caller passed; the prefetch loop re-reads the chain
before each copy; a check.mjs case interleaves a prefetch eviction with a slow select and renders afterwards. (Opus N2)
the budget case's numbers now follow the doc's own row order (fetched 2 / held 1 / skipped 41) and are derived in the
test as well. (SOL) prefetch fetches go through the same `fetchFace` as selections: `redirect: 'error'`, `readBounded`
with the index's byte count as the exact length, no `arrayBuffer()` path without a counted `Content-Length`; the error
case adds a redirect and oversized declared / chunked responses. (agy 1, Opus n2) a Latin-only face in the Latin slot has
a defined preview state: plain text under the select, no chip, no button. (agy 2) `defaultVariant`, `families(px)`, the
Hangul select, rows and chips rank and offer left-list faces only (`!subset && !latin_only`); `pick` refuses a key that is
not a left-list face. Minors: prefetch and its keep set are over left-list faces (Opus n1); any chip move bumps
`prefetchGen` (Opus n3); case D presses chip 18 first (Opus n4); `setSize` flushes the coalesced `markLacking` before
resolving (agy 3); the squareness tier is asserted on GBATB23 (agy 4); "also at N px" names chip sizes only (agy 5);
the hidden-face state is defined per slot, with both mixed cases tested (SOL minor).

## Revision 1 (2026-10-20, after three reviews and the user's answers)

User answers to the three open questions of the first version:
1. The two Latin-only faces (COUSB24, PAPLG16) are listed as Latin-only families: offered in the preview's Latin selector
   only, not in the left list (which sets both slots), and not counted as subsets. The rule and the index mark are in
   "The index".
2. The default on first open is one face in both slots: NGOTB16.
3. The family names stand as proposed (iolo faces: English name + Korean in parentheses; "san 1.0" and "san 8x4x4" apart;
   "Dokkaebi printer" and "Dokkaebi (도깨비) 8x4x4" apart; three Mac families).

Review findings fixed (Opus I1-I9, m1-m12; SOL 1-5, minors; agy 1-8): one canonical FAMILIES.tsv key (the index key,
`svf/<rel>`) and how mkindex maps it to `SVF_DIR`; `--families TSV` so fixture tests bring their own table, and the check
order; the full table for every listed face (appendix), re-checked for collisions, GBATB17B / GBATB23A tagged; only UI
actions, `setSize` and the non-manual load start a prefetch, a driver `select` never does; prefetch error classes (budget
vs HTTP / size / redirect / bad face), `setSize` never rejects; selection takes priority over a running prefetch
(protocol and test); the UI state of a hidden face in the chain; the variant group outside the listbox (valid ARIA) and
chip clicks that do not bubble; the "= list" badge iff `latin === hangul`; a separate `#notice` element; the budget test
with its chain and picked face fixed; the full bpp ranking; index validation (format string, canonical key / url, `px ==
cell[1]`, group, the family fields, size cap) with malformed-index tests; URL and localStorage values bounded and
validated with fallbacks, reload and malformed-state tests; the hidden-face breakdown corrected; the keep set of a prefetch
passed explicitly; `defaultVariant` asserted in the browser over every tier; case prefetch on its own page; one card when
both slots hold one face; `markLacking` scans the shown size and the chain only; the removed per-row buttons said.

## Intent

The face list is a flat list of 153 rows named by provenance (`label` is the licence note's title: "Paperlogy and
MaruBuri faces 20 px" holds two typefaces, "Taebaek 24 dot faces" a gothic and a myungjo, "iolo ... jamo-set faces"
eighteen typefaces). Choosing a face means reading 153 rows and remembering which letter suffix means what. The user
wants to choose the way a typographer thinks: the **size** first (the face file's own pixel size `px`, not the scaled
height; scaling stays a separate control), then the **family** at that size, then a **variant** (bit depth, composition,
cell width). Subset files, which exist only because one game needed a subset and are generated when needed, are not
offered at all. Choosing in the list sets both faces of the chain; the preview keeps separate Latin / Hangul selectors for
the cases where the two should differ.

## Goals and non-goals

Goals:
- A size -> family -> variant choice over the listed faces; at most a dozen size chips, 33 family rows at 16 px, one to
  four variant chips per family and size.
- Every face file keeps its identity: the key stays the repository path, the card and the export name the file.
- Family names that are typefaces, kept in a reviewed table in the repository, enforced by the index build.
- Missing-glyph marks on every family of the chosen size, not only on faces that happened to be fetched.
- No change to the renderer, the module glue or the pixels drawn; no change to the per-run rule.

Non-goals:
- Generating subset faces from the page (they are hidden, not built).
- A family notion inside the SVF file (the faces carry no name; the table is the source).
- Sorting by quality or a "similar faces" view.
- Changing what `tools/pairing2svf.py` reads: new export keys are extras it ignores.

## The index (`web/mkindex.py`, `faces.json` stays `svf-fonts-web-index/1`)

Every entry keeps today's fields (`label` included: it stays the provenance line on the card) and gains:

| field        | type                | meaning                                                                                    |
|--------------|---------------------|--------------------------------------------------------------------------------------------|
| `hangul`     | int 0..2350         | how many of the 2,350 KS X 1001 syllables the face draws (below)                           |
| `latin_only` | bool                | **(user)** `not jamo and hangul == 0 and ASCII present`: a Latin face, Latin selector only  |
| `subset`     | bool                | `not jamo and not latin_only and hangul < 2350` **(user rule)**: hidden everywhere          |
| `family`     | string              | the typeface, from `web/FAMILIES.tsv`; `""` only for a subset face without a row            |
| `style`      | string, may be `""` | the weight / design within the typeface (`Bold`, `Regular`, `Myungjo`, `Gam`)               |
| `variant`    | string, may be `""` | a short tag that tells apart faces of one family, size, bpp, composition and cell (below)   |

"Listed" below means `subset: false` (120 faces today: 118 in the left list + 2 Latin-only).

Hangul coverage **(user: from the cmap, not the glyph count)**: `KS = {0xAC00 + n for n in jamoset.ks_x_1001_syllables()}`
(2,350 code points, `tools/jamoset.py`); for a precomposed face `hangul = len(KS & set(svf.glyphs))` where `svf.glyphs` is
the cmap `parse_svfn` read. For a jamo-set face the cmap holds pieces, not syllables, so the count goes through the
renderer's rule: `hangul = sum(face.has(cp) for cp in KS)` with `svfline.Face(data)` (a valid JSET composes every
syllable, so this is 2,350; a jamo face whose JSET does not load is already `jamo: false` and is then counted from its
cmap like a precomposed one) **(my call)**.

ASCII present means every printable ASCII code point U+0021..U+007E (94) is in the cmap **(my call: the rule the user
asked for, made exact; both Latin-only faces have all 94, every supplement has none)**. `latin_only` and `subset` are
derived from `jamo`, `hangul` and the cmap only; a jamo face is never either.

Hidden, not dropped **(my call; the user left "flag or exclusion" open)**: a subset face stays in `faces.json`, in
`dist/faces/` and in `picker.faces()`, with `subset: true`. Reasons: the card's close criterion is "the page renders
every face" and check.mjs case A keeps running over all 153; a saved choice or URL that names a subset face still opens
(`select` by key works for any face); nothing has to be rebuilt when a face gains coverage. The left list, the size
chips, the family rows and the two preview selectors never offer a subset face; a Latin-only face is offered by the
Latin selector only. Measured on the tree of 2026-10-20: **153 faces, 120 listed (2 Latin-only), 33 hidden**: the 15
`*X?` supplements (0 Hangul, no ASCII), 16 one-game subsets with 682..1120 of the syllables (BHSAN28 among them), and the
2 outline faces GBATB17O / NEODG16O (1135). The user's first estimate was about 111; the difference is the count, not
the rule.

Left-list sizes and counts (faces / family rows): 16 px 44 / 33, 18 px 17, 20 px 14, 22 px 2, 24 px 27, 32 px 1,
36 px 8, 40 px 2, 48 px 1, 54 px 2 (PAPLG16, Latin-only, 18 px, and COUSB24, 28 px, are not in these). The 16 px faces
together are 2.4 MB, 24 px 4.5 MB, every listed face 17 MB: all of one size always fits the 64 MiB face budget today;
the design still says what happens when it does not.

`mkindex.py` order of checks and failures (exit 2, the face or the table line named, nothing written, as for licences):
1. the tables: `LICENCES.tsv` (today's rules), then `FAMILIES.tsv` syntax (below);
2. per face in sorted key order: the licence rules (today's messages, so `test_unmapped_face_fails` keeps its text),
   then the header fields and coverage;
3. the family rules over all entries: a listed face with no row or an empty `family`; a row whose `file` is not a face
   under `SVF_DIR` (a stale row); two listed faces that share `(family, style, px, bpp, jamo, cell_w, cell_h, variant)`
   (the message names both files; the fix is a `variant` tag on one of them).
A row for a hidden face is allowed (harmless, and ready for the day the face is listed) **(my call)**. `--check` runs
all of it. `--families TSV` names the table (default: `FAMILIES.tsv` beside the script), like `--licences`; the fixture
tests pass a fixture table (an `iolo`-only tree with the real table would fail on stale rows). The stdout line becomes
`153 faces, 120 listed (2 latin-only), 33 subset, 0 unmapped`.

### `checkIndex` in `picker.js` (a hostile `faces.json` is refused before anything reaches the DOM or the heap)

Today's checks stay (types, bounds, `safeUrl`, licences under `licences/`, duplicate keys, 2048 faces, 4 MiB). Added:
- `index.format === "svf-fonts-web-index/1"`.
- Canonical paths: `key` is `svf/` + `rel`, where `rel` is 1..6 segments of `[A-Za-z0-9._-]+` (no `.` or `..` segment),
  the last ending in `.SVF` or `.svf`; `url === "faces/" + rel`; `group === dirname(rel)`. A key that names one file and
  a url that fetches another is refused, so a key always names the bytes drawn and exported.
- `px === cell[1]` (a `px` of 0 would make a "0" chip); at most 64 distinct `px` values.
- `hangul` an integer 0..2350; `latin_only` and `subset` booleans; `subset === (!jamo && !latin_only && hangul < 2350)`;
  `latin_only` implies `!jamo && hangul === 0`; a face with both true is refused.
- `family`, `style`, `variant` strings of at most `MAX_FIELD` characters (picker.js's existing constant, 256, the same
  bound as today's `key` / `url` / `label`); `style` and `variant` may be empty; `family`
  must be non-empty when `subset` is false.
  `mkindex.py` enforces the same bound on the FAMILIES.tsv cells (exit 2 naming the line and column), and refuses a face
  at the root of `svf/` (its `group` would be empty, which `checkIndex` refuses): one rule in both.
Families are grouped in a `Map` keyed by `JSON.stringify([family, style])` (no string joins, no plain-object keys, so
`__proto__` or a family containing the separator cannot collide) **(my call)**. Names reach the DOM only through
`textContent` and `title` (as `el()` does today). A collision the index let through is not a page error: the chips
then also show the file name. URL and stored keys are only ever `byKey` lookups, never fetch URLs.

## The family table (`web/FAMILIES.tsv`)

Tab-separated, UTF-8 (a leading BOM is stripped; LF or CRLF), `#` comment lines and blank lines skipped, one header
row, then one row per face. The key is the canonical index key `svf/<rel>` **(user: keyed by face repo path; SOL 1)**;
`mkindex.py` maps it to `SVF_DIR/<rel>` by stripping the `svf/` prefix, and a row whose `file` does not start with `svf/`
is a syntax error naming the line. The full table is in the appendix; an excerpt:

```
file	family	style	variant
svf/dos/NGOTB16.SVF	NanumGothic	Bold	KS X 1001 symbols
svf/dos/NGOTB15.SVF	NanumGothic	Bold	2,350 syllables
svf/dos/TBGOB24.SVF	Taebaek	Gothic	
svf/dos/TBMY24.SVF	Taebaek	Myungjo	
svf/iolo/HGKEY6J.SVF	Cheonggyecheon Hangul (청계천한글)		
svf/jamo-extra/GOTHB16A.SVF	Gothic A1	Bold	
```

Syntax rules **(my call; Opus m3)**: the header must contain `file` and `family` (`style`, `variant` optional; any other
column is ignored with no error, so the table can grow notes); duplicate header names are an error; cells are trimmed
of spaces; a row with fewer cells than the header is padded with `""` (editors strip the trailing tab of
`TBGOB24<TAB>Taebaek<TAB>Gothic<TAB>`); a row with more cells than the header is an error; the same `file` twice is an
error; an empty `file` is an error. Errors name `FAMILIES.tsv:<line>`.

- `family` is the typeface name as the licence note or `svf/iolo/IOLO.TXT` gives it (Korean name in parentheses when
  that is how the font is known); `style` the weight or design (`Regular`, `Bold`, `SemiBold`, `Gothic`, `Myungjo`,
  `Gam`); `variant` a tag of a few words, empty unless two faces would otherwise collide. Family and style together make
  the row the user sees ("NanumGothic Bold", "Taebaek Myungjo", "Cheonggyecheon Hangul (청계천한글)").
- Exact keys, no globs **(my call)**: the table is reviewed line by line, and a new face under `svf/` must be named
  here (as in `LICENCES.tsv` for its licence) before the build passes. `jamo-extra/FACES.TSV`'s `family` column is not
  reused: it holds the font's full name with version and foundry ("Gothic A1 Regular 2.50 (HanYang I&C)"), which stays
  in `label`.
- The appendix table was generated from the rule and the notes and run through the collision check on 2026-10-20: 120
  rows, no collision. Tags were needed for GBATB14 / GBATB17 (16x16), GBATB17B / GBATB23A (26x24, ascents 19 and 21),
  NGOTB15 / NGOTB16, NEODG16A / B / C, PAPLG18 / PAPER18A and WCOMM16 / WCOMM6J. Hidden faces have no rows.

## The UI

### Left panel: size, family, variant

Replaces the filter selects, the flat list and its per-row "Latin" / "Hangul" buttons (the earlier design's sentence
about those buttons no longer applies; the role tags on rows stay). Order top to bottom: a search box, the size chips,
the family list, and under the list the variant strip of the selected family.

**Size chips** **(user)**: one `<button role="radio">` per distinct `px` among the left-list faces, ascending (16 18 20
22 24 32 36 40 48 54 today), in a `role="radiogroup"` labelled "Size (face file height)". The pressed chip is the size
whose families are listed. Pressing a chip rebuilds the family list and starts that size's prefetch (below); it does not
change the chain. The chip's `title` says "33 families, 44 faces".

**Family list**: `<ul role="listbox">` of the families at that size (Latin-only faces excluded), one `<li role="option">`
per `(family, style)`, sorted by family then style, case-insensitive **(my call)**. A row shows: the name ("Gothic A1
Bold"), a count badge when the family has more than one variant at this size ("· 4", `title` "1 precomposed, 3 jamo
sets"), the lack mark (below) and, while the row is the chain's family, the "Latin" / "Hangul" role tags of today. A row
holds no interactive child (valid ARIA: children of an option are presentational). Clicking a row (or Enter / Space on
it) picks the family's **default variant** and sets **both** the Latin and the Hangul face to it **(user)**:
`select({latin: key, hangul: key})`. The chain is then `[key, key]` and every run draws from the one face; the per-run
rule is unchanged (both slots hold the same file; the module opens it twice, which costs a second slot and no second
fetch) **(my call)**. Clicking the already selected row again re-picks the default variant (intended: a row click is
"this family, as it comes") **(my call; Opus m5)**.

**Default variant** **(user)**: among the family's **left-list** faces at that size (`!subset && !latin_only`; a
Latin-only face is never a candidate, so "Paperlogy Regular" at 18 px ranks PAPLG18 and PAPER18A, never PAPLG16)
**(agy rev1 2)**, prefer the higher bpp (8 over 2 over 1; `checkIndex` allows 8 bpp, so the ranking is total) **(Opus
m4, SOL 3)**, then precomposed over jamo set, then a square cell (`cell_w == cell_h`) over a wide one, in that priority
(lexicographic). Ties after that (the collisions the `variant` tag names) go to the face with more glyphs, then the
smaller key **(my call)**. Examples: Neo Dunggeunmo at 16 px has NEODG16 (1 bpp precomposed) and NEODG16A/B/C (1 bpp
jamo): no 2 bpp face, so precomposed wins: NEODG16. NanumGothic Bold at 16 px: NGOTB15 and NGOTB16 are both 2 bpp
precomposed 16x16: more glyphs wins: NGOTB16. Gothic A1 Bold at 16 px: GOTHB16A (2 bpp) over GOTHB16. Gowun Batang Bold
at 24 px: GBATB23 (24x24) over GBATB17B and GBATB23A (26x24), the square tier. NanumGothic Bold at 24 px: NGOTB17A,
NGOTB19, NGOTB21A are all 2 bpp precomposed, wide, 2446 glyphs: the smaller key wins: NGOTB17A. The rule lives in one
function, `picker.defaultVariant(family, style, px)`, which returns `null` for a family with no left-list face at that
size. Every path that fills the Hangul slot from the UI (row, chip, the Hangul select) draws from the same left-list set;
only a driver's `select` by key can put any face there (case A needs that).

**Variant strip** **(user: a sub-choice after the family, not list rows)**: a `role="radiogroup"` rendered **outside**
the listbox, directly below it, `aria-labelledby` the selected row's name ("Variant of Gothic A1 Bold at 16 px"), hidden
when no row of the shown size is selected **(Opus I6, agy 7)**. One chip per face of the family at this size, in the
default-variant order (the default first), each labelled by what differs from the others: `2 bpp` / `1 bpp`,
`precomposed` / `jamo set`, the cell when it is not square or when cells differ (`18x24`, `20x24`), the `variant` tag
when set, and the file name in small type always (the user knows the files). Axes that are the same for every chip of
the row are left out of the labels and said once in the strip's subtitle ("all 1 bpp jamo sets, 16x16"). Choosing a chip
sets both faces to that file, like a row click. Chip click handlers call `stopPropagation()` (so a chip can never also
trigger a row click, wherever the strip is placed). Keyboard: arrow keys move the pressed chip and apply it (a radio
group), as for the size chips.

**Search** keeps today's `#f-name`: it filters the family rows of the chosen size by family, style, variant tag and file
name (so `PAPLG18` finds "Paperlogy Regular" at 18 px). Group, px, bpp and jamo filters go: size is the chips, bpp and
composition are the variant chips, group is on the card **(my call)**. The counter shows "33 families · 44 faces" for
the size, or "2 of 33" while searching; when the search matches nothing at this size but does at others, a line under the
list says "also at 22 px, 24 px" with each size a button that presses that chip **(my call; Opus m12, cheap)**. The
search runs over left-list faces only, so every size it names has a chip (a Latin-only face such as COUSB24 at 28 px is
never found by it; it is found in the Latin select) **(agy rev1 5)**.

### Preview panel: the Latin / Hangul selectors

The two `<select>`s stay and gain structure: options in `<optgroup>`s by size, each option "Family Style · 2 bpp
precomposed 16x16 · FILE" (the same words as the chips), listed faces only; the Latin select also offers the Latin-only
faces (in their size groups, suffixed "Latin only") **(user)** and keeps "(none: the Hangul face's own ASCII)". Changing
one changes only that slot (`select({latin: new, hangul: current})`), as today. With no Hangul face open (`?manual`
before a select) every option of the Latin select is disabled: a Latin choice needs a Hangul face. Relation to the list **(user: the list
sets both, the selectors change either one)**:
- **"= list" badge, one rule (Opus I7, agy 8)**: both selects carry the badge (`<span class="badge same">`) iff `latin ===
  hangul` and that face is in the left list; otherwise neither (Latin `null` or Latin-only: neither). `view().same` is
  that boolean.
- The list always follows the **Hangul** slot: it highlights the Hangul face's family and variant (`aria-selected`, as
  today) when that face is a left-list face at the shown size; the Latin face's row carries the "Latin" tag when it is a
  left-list face at the shown size. The Latin slot never moves the chips or the selected row.
- **The line under the Latin select** (`#latin-note`, one element, three states) **(my call; agy rev1 1, Opus n2)**:
  - the Latin face is a left-list face at another size: "Latin: NanumGothic Bold 16 px (list shows 18 px)", a button
    that presses chip 16 without changing the chain;
  - the Latin face is Latin-only: plain text, no button, "Latin: Coustard Bold 28 px is a Latin-only face: not in the
    list" (also for PAPLG16 at 18 px while the list shows 18 px: Latin-only faces have no row at any size);
  - otherwise (same size and listed, none, or hidden: see below) the line is empty or the hidden text.
- A row or chip click always sets both again (it is a new choice, not an edit of one slot).
- When a selection arrives from outside the list (a selector, a driver's `select`, the URL, the default) and the Hangul
  face is a left-list face, the pressed chip becomes its `px` and the row and chip follow. Any chip move, whatever its
  cause, bumps `prefetchGen` and so stops a loop running for another size **(Opus n3)**; only a **UI action** starts a
  new one: a chip press, a row or chip pick, a selector change, a click on the "list shows" button, and the non-manual
  page load (default or URL) **(Opus I1)**. A driver's `select` (and `pick`) never starts one, under `?manual` or not;
  `setSize(px)` does.
- **A hidden face in a slot (Opus I3; SOL rev1 minor: per slot)** (URL, a Task 5 saved choice, case A's selects). The
  rules are per slot and compose:
  - the select of that slot gains a transient option "FILE (hidden: subset face)", removed when the slot changes; a
    Latin-only face that a driver's `select` put in the **Hangul** slot (case A does) is treated the same way, with the
    option text "FILE (Latin-only face)" and `#hangul-note` "Hangul: COUSB24 28 px is a Latin-only face: not in the
    list", `view().listed === false` **(Opus rev2 I2)**;
  - Hangul hidden: the size chips keep the last pressed size (16 on a fresh page, as the load presses it), no row is selected, the variant
    strip is hidden, no prefetch starts, `#hangul-note` (the Hangul twin of `#latin-note`) reads "Hangul: NGOTB14 14 px
    is a hidden subset face: not in the list" as plain text; `view()` returns `{px: 14, family: "", style: "",
    listed: false, ...}`;
  - Latin hidden, Hangul listed: the list follows the Hangul face as usual (its row selected, its chip pressed); the
    Latin select shows the transient option and `#latin-note` reads "Latin: NGOTB14 14 px is a hidden subset face: not
    in the list" as plain text; no badges;
  - both hidden: both notes, no row, chips as for Hangul hidden.
  The default-pair fallback is never applied to a hidden face that was selected on purpose.

The face cards (right panel) gain three rows at the top of the `<dl>`: family, style, variant (the tag or "-"), and keep
`label` as the provenance line and the file path. When `latin === hangul` one card titled "Latin and Hangul" is shown,
with one licence pane **(Opus m6)**.

### Keyboard

Tab order: search, size radiogroup, family listbox, variant radiogroup (when shown), then the preview controls. Size and
variant groups: Left/Right (and Up/Down) move and apply; Home/End to the first/last chip. Family listbox: Up/Down move
`aria-activedescendant` without picking, Enter or Space picks, Home/End, and typing letters jumps to the next family
starting with them (type-ahead) **(my call)**. The two selects are native. Every chip is a real `<button>`, the listbox
is one focusable element, so the existing `:focus-visible` outline applies.

### The notice element **(Opus I8)**

`ui.paint` rewrites the status line on every render, so messages that must outlive a paint go to a separate
`<p id="notice" role="status">` under the header: URL faults, storage faults, the prefetch summary ("16 px: 41 of 44
faces fetched, 3 over the face budget, 0 failed"), the hidden-face note. It is cleared by the next URL / size / pick
action, not by a render; a pick or a selector change from the page that fails clears it too (the failure itself is on `#status`). Tests read `#notice`; `#status` keeps the measure.

### What the URL and the stored state remember **(my call; SOL 5, agy 6)**

- URL query, kept current with `history.replaceState` (also under `?manual`: harmless, and the tests read `location`):
  `hangul=KEY`, `latin=KEY` (`latin=` for none), `scale=N/D`. Reading on load, every value bounded and validated:
  - the whole query over 2048 characters (the `?` counts), or any key or value over 256 characters: ignored as a whole,
    notice "URL ignored: too long";
  - `hangul=` (empty) is a notice that says so: "URL: hangul is empty; the default opened". Without a default face in the index the ending is "nothing opened" (as under `?manual`).
  - `hangul`: a `byKey` hit that is a **left-list** face (`!subset && !latin_only`) opens; anything else falls back to
    the default with a notice: "URL: no face svf/dos/NOPE.SVF; the default opened", "URL: svf/dos/COUSB24.SVF is a
    Latin-only face; the default opened", "URL: svf/dos/NGOTB14.SVF is a hidden subset face; the default opened"
    **(Opus rev2 I2; the brief: subset keys refused too)**. Hidden and Latin-only faces reach the Hangul slot only
    through a driver's `select` or a saved choice, never through the URL. The value is never fetched or echoed into
    HTML beyond `textContent`;
  - `latin`: absent -> the same face as `hangul` (the list's own behaviour); given without `hangul` -> the Hangul slot
    gets the default (NGOTB16) and the Latin slot the given face **(Opus rev3 m4)**; empty -> none; a `byKey` hit that is not a
    subset face (left-list or Latin-only) -> that face; anything else -> none with the notice "URL: no face ..." or
    "URL: ... is a hidden subset face; Latin none";
  - `scale`: `^\d{1,2}/\d{1,2}$` with both in 1..16 -> applied; anything else (`bad`, `0/0`, `17/1`) -> 1/1 with the
    notice "URL: scale ... ignored";
  - `ready` never rejects for a URL fault; every fault is a notice and a fallback.
  Text, target and zoom are not in the URL (a URL is for sharing a face choice, and the text can be long).
- `?manual` keeps its meaning: no default, no URL chain, no prefetch until a UI action or `setSize`; check.mjs drives
  from a blank page as today. The faces named in the URL are still checked and a bad one is still a notice, with the
  ending "nothing opened (?manual)" (for `hangul` and for `latin` alike); the scale is read. Whether `manual` is present
  is decided by `URLSearchParams` (a query over 2048 characters is never parsed and is scanned for `manual` instead).
- `writeUrl` writes only what the reader accepts: the chain (`hangul`, `latin`) is written when the Hangul face is a
  left-list face and the Latin face is not a subset face; a chain the reader would refuse (a hidden or Latin-only Hangul
  face, a subset Latin face: a driver's `select`) is omitted and any old `hangul` / `latin` is removed; with no chain open
  only `scale` is written. Other parameters stay except keys or values over 256 characters; a result over 2048 characters
  keeps only `manual`, `hangul`, `latin`, `scale`, so a reload always reads back what the page wrote. Other parameters are kept byte for byte (no re-encoding of a malformed escape).
- `localStorage` keeps only Task 5's choices (`svfpicker.choices`); no preference store in this card. On load the value
  is parsed in `try/catch` and validated (a JSON array of at most 256 objects, every string at most 256 characters,
  numbers finite; a choice whose `korean.key` is not in the index is kept and shown with a "not in this index" mark);
  anything else is ignored with the notice "stored choices unreadable: starting empty" and is overwritten by the next
  save. A storage exception (quota, disabled) is a notice, never a page error.

## Missing-glyph marks and fetching a whole size

Today a face carries "-n" only once it has been fetched (lazy loading). **(user)**: when a size is chosen, every
candidate face of that size is fetched so every family row shows its lack count.

- Prefetch order: the family rows top to bottom, within a row the default variant first, then the other chips
  **(my call)**, so the marks appear in reading order. Faces already in the heap (the chain, earlier visits) are
  skipped and counted as `held`.
- Scope **(Opus n1)**: the prefetch, its keep set and the `held` / `fetched` / `skipped` counts are over the
  **left-list** faces of the chosen size (44 at 16 px); a Latin-only face (PAPLG16 at 18 px) has no row or chip and is
  not prefetched.
- Keep set **(agy 3)**: `picker.prefetch(key, keep = [])` gains the optional `keep` list; the loop passes the left-list
  faces of the chosen size, so a size's faces evict faces of other sizes (oldest fetched first, as today) and never each
  other.
- **What `makeRoom` always protects (Opus N1, SOL rev1 critical)**: whatever `keep` a caller passes, `makeRoom` adds at
  call time `state.latin`, `state.hangul` (the chain open now, not the one when a loop started) and `state.pending`, the
  keys of a selection in progress. `selectNow` sets `state.pending = order` as its first statement and clears it in a
  `finally` after `svfw_open` succeeded or failed. So a prefetch copy that runs between a selection's two fetches, or
  after a selection installed a new chain while a loop started under the old one, can free neither the face the
  selection has already copied nor the new chain. The same holds for the pre-network `makeRoom` in `fetchFace`. This is
  the whole invariant: no pointer handed to `svfw_open`, and no pointer a slot holds, is ever freed.
- **The bytes a prefetch reads (SOL rev1)**: a prefetched face goes through the same `fetchFace` as a selected one:
  `safeUrl` on the index url, `fetch(url, {redirect: 'error'})` (a redirect, same-origin or not, is an error), then
  `readBounded(r, min(bytes, MAX_FACE_BYTES), url, bytes)`: a `Content-Length` over the limit is rejected before the body
  is read; the body is read with `r.body.getReader()` / `read()` (never async iteration, never `arrayBuffer()` on a
  stream); a chunk that would take the running total over the limit is **not** appended to the collected parts (not
  even its first bytes: it is dropped where it arrived), the reader is cancelled at once and the error "more than N
  bytes" is thrown, so the memory the page retains is the parts before that chunk, under the limit, whatever the size
  of the chunk the browser handed over (a hostile server can enqueue megabytes in one chunk; that allocation is the
  browser's and is released with the throw) **(SOL rev3)**; and the decoded length must equal the index's `bytes`
  exactly. There is no plain `arrayBuffer()` path: without a body stream,
  `readBounded` reads only when a counted (not content-encoded) `Content-Length` within the limit exists, and refuses
  otherwise. An oversized declared, oversized chunked or redirected response therefore costs at most the limit in bytes
  and ends as a `failed` face with "!" (never as a skip).
- **Priority of a selection (SOL 2, Opus I1)**: the serialised `state.queue` is split in two. Selections (`select`,
  `pick`) go to the select queue as today. The prefetch loop does not chain onto it: before starting each face it awaits
  `state.selectIdle` (a promise that resolves when the select queue is empty), fetches the face over the network outside
  any lock, then takes the heap lock (one promise chain shared by both paths: `makeRoom`, `alloc`, the copy, the scan)
  for the copy only, re-reading the chain and `state.pending` inside the lock. A `select` issued while a prefetched face
  is in flight therefore waits for at most that one face's copy (the network part does not hold the lock), never for the
  rest of the loop. A chip move is a change of the pressed size: a chip press or `setSize` of another size, or a
  selection from outside the list whose Hangul face is a left-list face of another size; a selection whose Hangul face
  is at the size already pressed (or is hidden / Latin-only, which never moves the chips) is **not** a chip move, does
  not bump the generation and leaves a running loop alone **(Opus rev3 m3)**. Any chip move bumps
  `state.prefetchGen`; the loop checks it before each face and stops (`stopped: true`); the face in flight is kept (it
  was paid for). No `AbortController` (a face is at most 1.6 MB; the simplicity is worth more). Two loops never run at
  once: every `setSize` call chains on the latest loop promise, stored synchronously (`state.prefetchRun =
  state.prefetchRun.then(() => loop(px))`), so three quick calls (24, 16, 18) run one after another; a superseded middle
  loop sees the bumped generation at its first check and resolves `{stopped: true, fetched: 0, ...}` **(Opus m8, rev2
  m1)**. The loop calls the internal `fetchFace(key, keep)` directly; the public `picker.prefetch(key, keep)` stays on
  the select queue as today (a driver's one-off prefetch is a selection-class job) **(Opus rev2 m2)**. `ready` does not
  wait for any prefetch.
- After each copied face a `markLacking()` job is queued on the heap-lock chain, coalesced (one pending job at a time;
  it also runs in a `requestAnimationFrame` only to paint), so counts fill in as they arrive and the scan's
  `svfw_reset` / `svfw_open` never interleaves with a selection's opens; `setSize` awaits the heap-lock chain (and so
  the pending scan) before it resolves, so a caller that awaits it reads final marks; nothing is flushed outside the
  lock **(agy rev1 3, rev2)**. `markLacking` scans only the shown size's faces plus the chain (`lacking(text, keys)`
  gains an optional key filter; without it the API is unchanged), so a keystroke never reopens every face of every
  visited size **(Opus m7)**.
- **Errors (Opus I2, SOL minor 2)**: `makeRoom` throws `BudgetError` (`err.code === 'budget'`), distinct from every
  other failure (`fetch` network error, HTTP status, redirect, a size over the limit or unequal to the index, bad URL,
  `svfw_open` failure). In the loop a `BudgetError` is a skip: the row and chip show a grey "?" with `title` "not
  fetched: the <budget> byte face budget is full" (the budget in force, `setFaceBudget` included); any other error is caught per face: the row and chip show "!" with the
  message in `title`, and the loop goes on. A failed face is retried by the next loop (every UI pick starts one); its `!` stays until it loads. A face that a select asks for while the loop is downloading it is not requested twice: both wait on the one fetch, and the loop counts that face `held` if the select made it resident first. A loop stopped by a newer chip move writes `N px: stopped after k of n faces` to the notice line. `setSize(px)` resolves `{px, fetched, held, skipped, failed, stopped}` and
  never rejects; the loop's promise is always handled (no unhandled rejection, no `pageerror`). The summary goes to
  `#notice`.
- Budget: `MAX_TOTAL_FACE_BYTES` stays 64 MiB. A later `select` of a skipped face behaves as today: `makeRoom` protects
  the old chain and the new chain and evicts the oldest other faces; it succeeds when the bytes held outside the chain
  suffice and is refused with today's "face memory" message otherwise (the chain stays open) **(Opus I9)**. After such
  a select the face's mark appears. A `select` of another size's face can evict prefetched faces of the shown size (its
  keep set is the chain only): their marks go back to "?" with `title` "evicted: pick the size again to fetch"
  **(Opus m10)**. With today's tree no size comes near the budget (24 px, the largest, is 4.5 MB), so the "?" path is
  exercised only through the test hook `setFaceBudget`.
- The mark on a family row is the mark of the face the row would pick (its default variant, or the chosen variant while
  the row is selected); its `title` lists each variant's count ("NGOTB16 -0, NGOTB15 -3"). A variant chip carries its
  own mark. A face that failed to open keeps today's "!" badge.
- The "fetch-once" test case stays true under the default budget: a prefetched face is not fetched again when selected,
  and switching sizes back and forth never refetches while the budget holds.

## Interaction with existing features

- **Per-run chain** **(unchanged)**: a Hangul-class run draws from [Hangul, Latin], a Latin-class run from [Latin,
  Hangul]; with both slots the same file the fallback is the same face. The Chain paragraph of the earlier design and
  its tests (case runs) stand; only the way faces are chosen changes.
- **Scale**: the size chips are file px; the scale select stays beside the preview and the "= N px high" readout stays.
- **Presets, targets, zoom, grid**: untouched. The "supplements" preset stays: it serves check.mjs's supplement case,
  whose faces are hidden but still rendered by key **(Opus m11)**.
- **Licence pane**: unchanged per face; the card gains the family rows; one card when both slots hold one face.
- **Face budget**: as above; the eviction order and the refusal message are today's.
- **Default on first open (user)**: `select({latin: NGOTB16, hangul: NGOTB16})` (one constant, `DEFAULT_HANGUL =
  'svf/dos/NGOTB16.SVF'`, fills both slots); chip 16 pressed, row "NanumGothic Bold", chip NGOTB16, both badges "= list", the 16 px
  prefetch started. check.mjs case C's expectation changes accordingly.
- **`window.picker`** gains, for the UI and check.mjs: `listed()` (faces with `subset` false, Latin-only included),
  `sizes()` (the chip px list), `families(px)` -> `[{family, style, name, faces: [keys in chip order], default: key}]`
  (Latin-only faces excluded), `defaultVariant(family, style, px)` -> key or `null` (left-list faces only), `pick(key)`
  (= `select({latin: key, hangul: key})`, no prefetch; rejects a key that is not a left-list face, since it fills the
  Hangul slot), `setSize(px)` (presses the chip, rebuilds the list only when px is not the size shown, runs the prefetch; resolves as above),
  `view()` -> `{px, family, style, variant, hangul, latin, same, listed}`, `notice()` (the text of `#notice`).
  `faces()`, `select`, `prefetch` (now with `keep`), `lacking` (now with `keys`), `faceMemory`, `setFaceBudget` keep
  their meaning.

## Task 5 and Task 6 (carried requirements)

Task 5 (choices and export):
- The export gains a top-level `"order": "per-run"` next to `format` / `created` / `source` **(user: carried
  requirement)**, saying how the Latin and Hangul faces were combined when the choice was looked at (pairing2svf ignores
  unknown top-level keys, like `source`).
- `korean` gains `family`, `style`, `variant` (extra keys pairing2svf ignores) beside `label`, which stays the index
  label **(my call)**; `key`, `file`, `latin`, `scale`, `w`, `h`, `bpp`, `ascent` as planned.
- The choices table shows "Family Style · variant words" with the file name in small type, instead of the label.
- Stored choices are validated on load as said under "What the URL and the stored state remember".
- `TestPage::test_export_shape` adds `sel["order"] == "per-run"` and the three new keys; `TestExportShape` is unchanged
  (the shape pairing2svf reads is the same).

Task 6 (README and gate): `web/README.md` documents `FAMILIES.tsv` (format, the failure rules, `--families`, how to add
a face: one `LICENCES.tsv` row and one `FAMILIES.tsv` row), the subset and Latin-only rules and the counts line of
`mkindex.py`, the URL parameters and their fallbacks, the notice element, and the new `window.picker` calls. The gate's
evidence line adds the `mkindex.py` counts.

## Tests a builder can write

Python (`tools/test_web_picker.py`, `TestIndex`, no browser; every fixture test passes `--families` with a fixture
table covering its faces):
- `test_hangul_coverage_matches_cmap`: for every entry, `hangul` equals the test's own count (`ks_x_1001_syllables`
  against `parse_svfn(data).glyphs` for `jamo: false`, `svfline.Face(data).has` for `jamo: true`); `latin_only ==
  (not jamo and hangul == 0 and all printable ASCII in the cmap)`; `subset == (not jamo and not latin_only and hangul <
  2350)`.
- `test_subset_examples`: `NGOTB14` hidden with `hangul == 1120`; `NGOTB16` listed, 2350; `HGKEY6J` listed (jamo),
  2350; `COUSB24` and `PAPLG16` `latin_only`, not subset, `hangul == 0`; `GBA14X2` hidden, not `latin_only` (no ASCII);
  the counts line says `120 listed (2 latin-only), 33 subset` with the numbers derived in the test from the rule, not
  hard-coded.
- `test_every_listed_face_has_a_family`: `family` non-empty for every listed face; every row's `file` is an index key.
- `test_family_examples`: `svf/dos/TBGOB24.SVF` -> ("Taebaek", "Gothic"), `svf/dos/TBMY24.SVF` -> ("Taebaek",
  "Myungjo"), `svf/dos/HWPHM24.SVF` style "Myungjo", `svf/iolo/HGKEY6J.SVF` family starts with "Cheonggyecheon",
  `svf/jamo-extra/GOTHB16A.SVF` -> ("Gothic A1", "Bold"), `svf/dos/COUSB24.SVF` -> ("Coustard", "Bold").
- `test_missing_family_row_fails`: the iolo fixture tree with a `FAMILIES.tsv` that lacks `HGKEY6J`: exit 2, the file
  named, nothing written. `test_stale_family_row_fails`: a row for `svf/iolo/NOPE.SVF`: exit 2 naming the line.
  `test_duplicate_family_row_fails`. `test_family_header_fails` (no `family` column; a duplicate header name).
  `test_family_key_without_prefix_fails` (`iolo/HGKEY6J.SVF`). `test_short_row_is_padded` (a row of two cells passes
  with empty style and variant). `test_licence_error_comes_first` (a tree with both an unmapped face and a missing
  family row reports the licence error).
- `test_variant_collision_fails`: two listed faces copied from one file under two names at one family / style with
  empty variants: exit 2 naming both; a `variant` tag on one of them makes it pass.
- `test_real_table_has_no_collision`: the real table over the real tree passes (this is `setUpClass` succeeding, named
  so the failure reads right).

check.mjs (new cases; existing cases C, D, dom, marks, bad face and budget are rewritten for rows that are families, a
default of NGOTB16 in both slots, and listed faces only: case bad face moves from PAPLG16 to a listed face, e.g.
PAPLG18 as the bad one over NGOTB16):
- `case sizes`: the chips equal the sorted distinct `px` of the left-list faces; no hidden face key appears in `#faces`,
  `#latin` or `#hangul`; the Latin-only keys appear in `#latin` only; the family count at 16 px equals
  `families(16).length` (33 today), names unique and sorted.
- `case default variant` **(agy 4)**: `defaultVariant` in the browser gives NEODG16 (composition tier), GOTHB16A (bpp
  tier), GBATB23 for Gowun Batang Bold at 24 px (square tier) **(agy rev1 4)**, NGOTB16 (glyph-count tie), NGOTB17A
  (key tie), PAPER18A for Paperlogy Regular at 18 px (it beats PAPLG18 by glyph count; PAPLG16, Latin-only, is not a candidate) **(agy rev1 2; the rule is normative, the first example was a slip)**, `null`
  for ("Coustard", "Bold", 28), and for a synthetic index routed in with an 8 bpp face beside a 2 bpp one of a family,
  the 8 bpp one. `families(18)` lists no face key that is `latin_only`; `pick('svf/dos/COUSB24.SVF')` rejects with a
  message naming the key, and the chain is unchanged.
- `case pick`: clicking "Neo Dunggeunmo" at 16 px gives `chain() == {latin: NEODG16, hangul: NEODG16}`, both selects
  show it with the badge, `view().same === true`; clicking the `NEODG16C` chip changes both (and the row click handler
  did not fire: the chain is NEODG16C, not NEODG16); `#latin` to `NGOTB16` changes only Latin, removes both badges,
  keeps the row and chip on NEODG16C; `#latin` to COUSB24 (Latin-only) works, `#latin-note` reads "Latin: Coustard Bold
  28 px is a Latin-only face: not in the list" and holds no button, the chips are unchanged (16 pressed) and no request
  other than COUSB24 was made; `#latin` to PAPLG16, then `setSize(18)` (a select moves the list back to the Hangul face's size, so the size is set after it), gives the same kind of text; a row click sets
  both again.
- `case prefetch` (its own page, `?manual`) **(agy 5)**: `page.on('request')` counting from a blank page; after
  `setSize(16)` resolves `{fetched: 44, held: 0, skipped: 0, failed: 0, stopped: false}` (with no chain open), every
  16 px face is in `faceMemory().keys`, every row and chip carries a mark equal to `lacking()` for its face (or none when
  0), each file requested once; `setSize(24)` then `setSize(16)` requests nothing new and reports `held: 44`; a
  `setSize(16)` issued while `setSize(24)` runs makes the first resolve `stopped: true` and no `pageerror` occurs.
- `case prefetch priority` **(SOL 2; rev2: same-size pick)**: on a fresh `?manual` page (default budget) call
  `setSize(24)` and, without awaiting it, `pick('svf/dos/TBMY24.SVF')` (24 px, 38,181 B, the last face of the 24 px
  order, so the loop has not reached it): the chip stays 24, so the loop is not stopped. Record
  `faceMemory().keys.length` before the pick and when it resolves: the difference is at most 2 (TBMY24 itself and the
  one 24 px face that was in flight), and the pick resolves before `setSize` does. Then await `setSize`: it resolves
  `{fetched: 26, held: 1, skipped: 0, failed: 0, stopped: false}` (27 left-list 24 px faces, TBMY24 held); render the
  pangram: err 0, ink > 0, `faceMemory().keys` still holds TBMY24, and `pixels()` equals the render of TBMY24 in both
  slots on a fresh page. Residency under budget pressure is the next case's job.
- `case select during eviction` **(Opus N1; rev2 rewrite)**: a fresh `?manual` page. Faces: Latin X = `svf/dos/HWPHG24.SVF`
  (24 px, 38,097 B: outside the prefetched size, so no keep list but `state.pending` protects it); Hangul Y =
  `svf/iolo/WCOMM6J.SVF` (16 px, 12,921 B, the last face of the 16 px order: a left-list 16 px face keeps the chip on 16,
  so the loop is not stopped); P = `svf/iolo/AD248J.SVF` (20,453 B, the first face of the 16 px order). Budget
  `setFaceBudget(52000)`: X + Y = 51,018 fits; X + P = 58,550 does not, so P's copy must evict to proceed; P alone
  (20,453) fits once X is gone. Routes: P and Y are each held (the route handler awaits a promise the test resolves).
  Steps: `setSize(16)` not awaited (the loop requests P, which is held); **await P's request at the route before calling
  `select`** (in one tick the loop would still be waiting on `selectIdle` behind a select whose Y is held, and P would
  never be requested); `select({latin: X, hangul: Y})` not awaited
  (X is fetched and copied at once; the select then waits for Y, held; `state.selectIdle` is now pending, so the loop
  starts no further face); poll until `faceMemory().keys` includes X and both routes have received their request;
  release P: its copy runs `makeRoom(20453, keep = the 16 px faces ∪ chain (empty) ∪ pending [X, Y])`; **wait** (poll,
  5 s timeout) until **P's family row (`AD24`)** shows the grey "?" skip mark (the variant strip is hidden while no row is
  selected, so the chip is not in the DOM: the row only), which proves P's copy attempt has happened while Y
  is still on the wire and `pending` still holds X **(Opus rev3 I1, agy rev3)**; only then release Y; await the select,
  then `setSize`. The wait is what makes the case deterministic: released together, Y (smaller) could be copied and the
  chain installed before P's copy, and then `state.latin` would protect X in any build. It also catches a build whose
  loop copy waits on `selectIdle` (forbidden by the protocol): P's mark never appears and the wait times out instead of
  the case passing vacuously. Assertions: the select resolves without error; `chain()` is `{latin: X, hangul: Y}`;
  `faceMemory().keys` includes X and Y and not P; `setSize` resolved `{fetched: 0, held: 1, skipped: 43, failed: 0}`
  (P refused by budget, then every other face: 51,018 held by the chain + the smallest face 12,921 > 52,000; Y held);
  `skipped >= 1` proves the pressure was real; a render of the pangram gives err 0 and `pixels()` equals the same
  chain's render on a fresh page with the default budget; no `pageerror`. Why a build without `state.pending` fails
  it: P's `makeRoom` then sees X as the oldest face outside the keep set, frees it and deletes it from the file map, so
  `faceMemory().keys` lacks X after the select (deterministic), and the select later opened a freed pointer (the pixel
  comparison catches the damage when the block was reused). The byte numbers are also derived in the test from the
  index, as in case prefetch budget.
- `case prefetch errors` **(Opus I2, SOL rev1; rev2: bounded reads)**: five faces that are each the default variant of
  a distinct 16 px family, so the family row itself shows "!": `AD248J` (AD24) -> HTTP 404; `HTERM16` (hanterm) -> a
  body one byte short; `NEODG16` (Neo Dunggeunmo) -> a same-origin redirect (`?r`); `SANGAM16` (san 1.0 Gam, 20,541 B)
  -> a declared `Content-Length` of 9,000,000 with a body of that size; `TBTHG16` (Taebaek Gothic, 20,497 B) -> a
  chunked body of 9,000,000 bytes (no `Content-Length`), which `serve.mjs`'s `chunked` option now writes **paced**
  (16 KiB per 5 ms, each write awaiting the socket's drain) instead of one `res.end(body)`, and whose `stats()` reports
  per URL `{written, completed, closed}` plus `error` (the message of a server write error, absent otherwise; a HEAD sets `completed`); a refused answer (`!r.ok`) of a face, `faces.json` or a licence has its body cancelled like an over-long one (case `server and cancel`). Reader-to-URL mapping **(agy rev3, Opus rev3 m2)**: before the page loads an init
  script wraps `window.fetch` (tags the returned `Response` with its request URL in a `WeakMap`), the
  `Response.prototype.body` getter (tags the stream with the response's URL), `ReadableStream.prototype.getReader`
  (tags the reader with the stream's URL), and then `ReadableStreamDefaultReader.prototype.read` / `.cancel` and
  `Response.prototype.arrayBuffer`, which credit `window.__reads = {url: {bytes, lastChunk, chunks, cancelled,
  arrayBuffer}}`; `readBounded` is required to stay on `getReader()` / `read()` (as today), which the `chunks` count
  being non-zero for every good face confirms. `setSize(16)` resolves `{fetched: 39, held: 0, skipped: 0, failed: 5}`;
  the five rows show "!" with the message in `title` (the redirect one names the redirect, the declared one the limit,
  the chunked one "more than 20497 bytes", the short one the index size); the other rows carry marks; no `pageerror`;
  the notice says "5 failed"; `faceMemory().bytes` equals the sum of the 39 good faces' index sizes (2,296,637 today,
  computed in the test) and no failed key is in `faceMemory().keys` **(Opus rev2 m3)**. Bounded reads **(SOL rev2, Opus
  rev3 I2)**: `__reads` for SANGAM16 has `bytes === 0` and `chunks === 0` (rejected on the header, and its body is cancelled: `stats()` shows `closed` and `written` under 1,000,000, polled); for TBTHG16
  `bytes - lastChunk <= 20497` (the reader stopped at the first chunk that crossed the limit; no assumption about a
  chunk's size, which Chromium does not bound) and `cancelled === 1`; `arrayBuffer === 0` for every face URL on this
  page; `stats()` for the TBTHG16 URL says `closed`, `completed === false` and `written < 1000000` (polled) (no figure in chunks: the
  network service and the loopback buffers absorb an unknown amount before the cancel lands). One-huge-chunk **(SOL
  rev3)**: on the same page the `fetch` wrapper replaces, for `svf/dos/TBMY24.SVF` (38,181 B, a 24 px face, so not in
  the heap after `setSize(16)`), the response by a `Response` whose body is a `ReadableStream` that enqueues one
  6,000,000-byte `Uint8Array` and closes (same headers, no `Content-Length`); `prefetch` of that key rejects with "more
  than 38181 bytes", `__reads` for it shows `chunks ===
  1`, `bytes - lastChunk === 0` and `cancelled === 1`, `faceMemory()` (bytes and keys) and `module().HEAPU8.byteLength` are
  unchanged by it. No `performance.measureUserAgentSpecificMemory()` reading: `serve.mjs` sends no COOP/COEP, so the page is
  not cross-origin isolated and the API would always be skipped; the heap-length assertion replaces it. The `fetch` wrapper
  tags the substituted `Response` too, and `Response.prototype.clone` is wrapped so that a clone inherits the URL. No-stream step **(Opus rev3 m1, agy
  rev3)**: a **fresh** `?manual` page with `Response.prototype.body` hidden (as case no stream) and only the two
  oversized routes bad: `setSize(16)` resolves `{fetched: 42, held: 0, skipped: 0, failed: 2}`; both fail as unbounded
  (chunked) or over the limit (declared); `arrayBuffer === 0` is asserted for those two URLs only (the good faces read
  through `arrayBuffer()` here, legitimately, under a counted `Content-Length`).
- `case prefetch budget` **(Opus I9, Opus N2)**: fresh `?manual` page; `pick('svf/iolo/HGKEY6J.SVF')` (12,921 B, the
  smallest 16 px face, one copy for both slots); `setFaceBudget(12921 + 3 * 12921 + 10)` (51,694 B). The loop runs in
  row order (family, then style, case-insensitive) and does not stop at a skip: row "AD24" fetches AD248J (20,453 B;
  33,374 held), every following face until "Hangul Link" is 20,453 B or more and is skipped, HLINK6J (12,921 B) fits
  (46,295 held), and nothing after it fits (5,399 B left, the smallest face is 12,921 B). So `setSize(16)` resolves
  `{fetched: 2, held: 1, skipped: 41, failed: 0}`; the test also derives these numbers from `families(16)` order and
  the index `bytes` and asserts both agree, so a table change moves the numbers without breaking the case. The skipped
  rows show "?", `#notice` says "2 of 44 ... 41 over the face budget". Then `pick('svf/iolo/ROMAX6J.SVF')` (12,921 B,
  skipped) succeeds by evicting AD248J (the oldest face outside the chain) and ROMAX6J's mark appears; then
  `pick('svf/dos/NGOTB16.SVF')` (218,916 B) is refused with the "face memory" message and the chain stays ROMAX6J.
- `case scan during select` **(SOL rev3; the scan is a heap-lock job)**: a fresh `?manual` page, default budget;
  `pick('svf/dos/NEODG16C.SVF')` (24,809 B, the only face of that length) and the pangram as text (a chain is open, so
  every scan ends by restoring a chain); wrap `module()._svfw_reset` and `_svfw_open` as case bad face does, logging
  `(call, slot, len)` in order (lengths identify faces, so every face named here has a length no other face has: 24,809,
  32,791, and 38,097 among 16 px faces); route Y2 = `svf/jamo-extra/NDGPR16.SVF` (32,791 B, 16 px) held; X =
  `svf/dos/HWPHG24.SVF` (38,097 B, 24 px); route P = `svf/iolo/AD248J.SVF` (20,453 B, the first 16 px face) held too.
  Steps: `setSize(16)` not awaited; await P's request; `select({latin: X, hangul: Y2})` not awaited (X copied, the select
  waits for Y2; the loop has P in flight and pauses afterwards); poll until `faceMemory().keys` includes X and record
  `log.length`; release P; poll until the log after that point holds, in order, `reset`, `open(0, 20453)`, `reset`,
  `open(0, 24809)`, `open(1, 24809)` (P's scan, then the restore of both NEODG16C slots; P is identified as the face in
  flight, not by its length, which nine iolo faces share); release Y2; await the select, then `setSize`. Assertions: the select resolves; `chain()` is `{latin: X,
  hangul: Y2}`; `_svfw_info(0)` reports a 24x24 cell and `_svfw_info(1)` a 16x16 cell (slot contents are the selected
  faces); in the log, from the select's own sequence (`reset`, `open(0, 38097)`, `open(1, 32791)`) onward every restore
  opens 38,097 then 32,791 and 24,809 never appears again (no stale NEODG16C restore); no scan `open` sits between the
  select's `reset` and its last `open`; a render gives err 0 and `pixels()` equals the same chain's render on a fresh
  page; the marks equal `lacking()`; `setSize` resolved `{fetched: 42, held: 2, skipped: 0, failed: 0}` (NEODG16C and
  NDGPR16 held, both 16 px left-list faces). Why a build that runs the scan outside the lock chain fails it: such a scan
  can run from the in-flight copy or a paint while the selection is between its fetches and restore the chain it read
  earlier, or interleave its `reset` / `open` with the selection's; the log order and the slot cells then differ, and a
  restore of NEODG16C after the select leaves slot 1 a 16x16 NEODG16C whose pixels differ from NDGPR16's. The scan and
  the select's reset/opens are both synchronous, so they cannot interleave in any case; the rule the case pins is "the scan
  reads the chain at run time" (nothing captured when the job is queued), and the lock placement is defence in depth for any
  future asynchronous step inside the scan. Plan sync (Task 5): a scratch build whose scan captures the chain when it is
  queued still passes this case, because the lock chain runs jobs in the order they were queued (a scan queued before the
  select's job always runs before it); the case pins the observable order, not that implementation choice.
- `case hidden in chain` **(Opus I3, SOL rev1 minor)**: on a `?manual` page, `select({latin: null, hangul:
  'svf/dos/NGOTB14.SVF'})`: `#hangul` shows the transient "(hidden: subset face)" option, `#hangul-note` has the hidden
  text, chip 16 still pressed (the load's), no row selected, the variant strip hidden, `view().listed === false`, no face request other
  than NGOTB14 (no prefetch); then `select({latin: 'svf/dos/NGOTB14.SVF', hangul: 'svf/dos/PAPLG18.SVF'})` (hidden
  Latin, listed Hangul): chip 18 pressed, row "Paperlogy Regular" and chip PAPLG18 selected, `#latin` shows the transient
  option, `#latin-note` has the hidden text and no button, no badges; then `select({latin: 'svf/dos/PAPLG18.SVF',
  hangul: 'svf/dos/NGOTB14.SVF'})` (listed Latin, hidden Hangul): no row selected, chips keep 18, `#latin-note` empty or
  the "list shows" text per its rule, `#hangul-note` the hidden text; a later `pick` removes every transient option.
- `case keyboard`: focus the size group, ArrowRight presses the next chip and the family list changes; in the listbox
  ArrowDown then Enter picks that row; in the variant group ArrowRight applies the next chip; typing "pa" moves the
  active row to the first family starting with "Pa".
- `case url` **(SOL 5, agy 6)**: `?hangul=svf/dos/TBMY24.SVF&latin=&scale=2/1` opens that chain at 2/1 with chip 24
  pressed; `?hangul=svf/dos/TBMY24.SVF` alone gives Latin = TBMY24; `?latin=svf/dos/HWPHG24.SVF` alone gives Hangul =
  NGOTB16 (the default) with Latin HWPHG24 and chip 16 pressed; `?hangul=svf/dos/NOPE.SVF` falls back to the
  default with `#notice` naming the key; `scale=bad`, `scale=0/0` and `scale=17/1` each give 1/1 and a notice; a query
  of 3,000 characters is ignored with a notice; `?hangul=svf/dos/COUSB24.SVF` and `?hangul=svf/dos/NGOTB14.SVF` each
  open the default (NGOTB16 in both slots) with the notice naming the key as Latin-only / hidden, and no request for
  that file is made; `?hangul=svf/dos/TBMY24.SVF&latin=svf/dos/COUSB24.SVF` opens TBMY24 with Latin COUSB24 (Latin-only
  is allowed in the Latin slot) and `?latin=svf/dos/NGOTB14.SVF` gives Latin none with a notice; after a `pick` the URL
  carries the new keys, and a reload of that URL restores the same chain and scale.
- `case storage` (Task 5): `localStorage.svfpicker.choices = '{nope'` and `'[' + '{}'.repeat(...) + ']'` of 300
  entries: the page loads, choices are empty, `#notice` says they were unreadable; a valid list with a key not in the
  index loads with the "not in this index" mark.
- `case index` gains **(SOL 4)**: a missing or wrong `format`; a `url` that does not match the `key`; a `key` with a
  `..` segment or a space; `group` not the key's directory; `px != cell[1]`; `subset` that disagrees with `hangul` /
  `jamo` / `latin_only`; `latin_only` with `hangul: 5`; a listed face with an empty `family`; `hangul: 3000`; 65 distinct
  sizes. Each is refused and named on the status line with no row built.
- `case B licence` gains a face with three licence files **(SOL rev3 minor)**: after `select({latin: null, hangul:
  'svf/iolo/HGKEY6J.SVF'})` the card shows exactly three `details` in index order, `IOLO.TXT`, `LICENSE-MIT.txt`,
  `LICENSE-OFL.txt`, each `summary` the file name and each `pre` starting with that file's first line ("iolo 6x2x1 /
  8x4x4 jamo-set faces", "The MIT License (MIT)", "Copyright (c) 2025 Dongsu Jang") and none still "loading...".
- `case A` and `case fetch-once` keep iterating `faces()` (all 153); case D's filter step first presses chip 18 (the
  default page shows 16 px, and the search covers the shown size only), then types "PAPLG18" and expects one row
  ("Paperlogy Regular") whose chip strip contains `PAPLG18.SVF`; typing "PAPLG18" on 16 px instead expects no row and
  the line "also at 18 px" whose button presses chip 18 **(Opus n4)**.

## Appendix: `web/FAMILIES.tsv` (user-reviewed names, one row per listed face, 120 rows)

Generated 2026-10-20 from the rule and the licence notes; the collision check over it finds none. This is the file's
content (header + rows; the builder commits it verbatim as `web/FAMILIES.tsv`, tabs between cells, a trailing empty
`variant` cell written as nothing after the last tab).

```
file	family	style	variant
svf/dos/AMYJO18.SVF	AppleMyungjo (Mac)		
svf/dos/COUSB24.SVF	Coustard	Bold	
svf/dos/DIPHY36.SVF	Diphylleia	Regular	
svf/dos/DKBHG24.SVF	Dokkaebi printer		
svf/dos/GBATB14.SVF	Gowun Batang	Bold	2,350 syllables, ascent 13
svf/dos/GBATB17.SVF	Gowun Batang	Bold	SCI charset, ascent 15
svf/dos/GBATB17B.SVF	Gowun Batang	Bold	ascent 19
svf/dos/GBATB23.SVF	Gowun Batang	Bold	
svf/dos/GBATB23A.SVF	Gowun Batang	Bold	ascent 21
svf/dos/GBATB35.SVF	Gowun Batang	Bold	
svf/dos/GBATB47.SVF	Gowun Batang	Bold	
svf/dos/GOTHB18A.SVF	Gothic A1	Bold	
svf/dos/HTERM16.SVF	hanterm		
svf/dos/HWPHG24.SVF	HWP 1.20	Gothic	
svf/dos/HWPHM24.SVF	HWP 1.20	Myungjo	
svf/dos/IYAGI16.SVF	san 1.0	Iyagi	
svf/dos/JGODK18.SVF	Jung-Gothic (Mac)		
svf/dos/MARUB20A.SVF	MaruBuri	Bold	
svf/dos/MARUB24A.SVF	MaruBuri	Bold	
svf/dos/MARUS20.SVF	MaruBuri	SemiBold	
svf/dos/MARUS24.SVF	MaruBuri	SemiBold	
svf/dos/MARUS24A.SVF	MaruBuri	SemiBold	
svf/dos/MUNJO24.SVF	Munjo (HangulTalk)		
svf/dos/NEODG16.SVF	Neo Dunggeunmo		
svf/dos/NEODG16A.SVF	Neo Dunggeunmo		base set
svf/dos/NEODG16B.SVF	Neo Dunggeunmo		+ U+2026
svf/dos/NEODG16C.SVF	Neo Dunggeunmo		+ Latin-1, symbols, compat jamo
svf/dos/NEODG16D.SVF	Neo Dunggeunmo		
svf/dos/NEODG16E.SVF	Neo Dunggeunmo		
svf/dos/NEODG16F.SVF	Neo Dunggeunmo		
svf/dos/NEODG32.SVF	Neo Dunggeunmo		
svf/dos/NEODG32A.SVF	Neo Dunggeunmo		
svf/dos/NGOTB15.SVF	NanumGothic	Bold	2,350 syllables
svf/dos/NGOTB16.SVF	NanumGothic	Bold	KS X 1001 symbols
svf/dos/NGOTB16B.SVF	NanumGothic	Bold	
svf/dos/NGOTB17.SVF	NanumGothic	Bold	
svf/dos/NGOTB17A.SVF	NanumGothic	Bold	
svf/dos/NGOTB19.SVF	NanumGothic	Bold	
svf/dos/NGOTB21.SVF	NanumGothic	Bold	
svf/dos/NGOTB21A.SVF	NanumGothic	Bold	
svf/dos/NSQRB36.SVF	NanumSquareRound	Bold	
svf/dos/NSQRB36A.SVF	NanumSquareRound	Bold	
svf/dos/NSQRR16A.SVF	NanumSquareRound	Regular	
svf/dos/NSQRR36.SVF	NanumSquareRound	Regular	
svf/dos/NSQRR36A.SVF	NanumSquareRound	Regular	
svf/dos/PAPER16A.SVF	Paperlogy	Regular	
svf/dos/PAPER18A.SVF	Paperlogy	Regular	own Latin, dy
svf/dos/PAPLB16A.SVF	Paperlogy	Bold	
svf/dos/PAPLB18A.SVF	Paperlogy	Bold	
svf/dos/PAPLB20A.SVF	Paperlogy	Bold	
svf/dos/PAPLG16.SVF	Paperlogy	Regular	Latin companion of PAPLG18
svf/dos/PAPLG18.SVF	Paperlogy	Regular	first build, no Latin
svf/dos/SANGAM16.SVF	san 1.0	Gam	
svf/dos/SMYJO18.SVF	Sinmyungjo (Mac)		
svf/dos/TBGHC48.SVF	Taebaek	Gothic	GHANC48 printer
svf/dos/TBGHN40.SVF	Taebaek	Gothic	GHAN40 printer
svf/dos/TBGOB24.SVF	Taebaek	Gothic	
svf/dos/TBMY24.SVF	Taebaek	Myungjo	
svf/dos/TBTHG16.SVF	Taebaek	Gothic	T-Hangul TBG1
svf/dos/WCOMM16.SVF	Wordcom (워드콤)		8x4x4 fit of han_wcomm.fnt
svf/dos/YOUTH36.SVF	Youth (청춘체)		
svf/games/lb1/DKBHG40.SVF	Dokkaebi printer		
svf/iolo/AD248J.SVF	AD24		
svf/iolo/DKBY8J.SVF	Dokkaebi (도깨비) 8x4x4		
svf/iolo/HANME8J.SVF	Hanme (한메)		
svf/iolo/HGKEY6J.SVF	Cheonggyecheon Hangul (청계천한글)		
svf/iolo/HLINK6J.SVF	Hangul Link (한글링크)		
svf/iolo/JOONG6J.SVF	Mirae Trading Little Star (미래교역 작은별)		
svf/iolo/MR1286J.SVF	Mirae Trading Gothic (미래교역 고딕)		
svf/iolo/PILGI8J.SVF	Pilgi (필기)		
svf/iolo/ROMAX6J.SVF	Royal Computer (로얄컴퓨터)		
svf/iolo/SAM8J.SVF	Saem (샘)		
svf/iolo/SAN8J.SVF	san 8x4x4		
svf/iolo/SANS8J.SVF	Gothic 8x4x4 (고딕)		
svf/iolo/SCRN96J.SVF	Screen9		
svf/iolo/SERIF8J.SVF	Myungjo 8x4x4 (명조)		
svf/iolo/THIN8J.SVF	thin		
svf/iolo/U4K8J.SVF	u4k		
svf/iolo/WCOMM6J.SVF	Wordcom (워드콤)		iolo 6x2x1 build
svf/iolo/WOORI6J.SVF	Woorigeul (우리글)		
svf/jamo-extra/GOTHA16.SVF	Gothic A1	Regular	
svf/jamo-extra/GOTHA16A.SVF	Gothic A1	Regular	
svf/jamo-extra/GOTHA18.SVF	Gothic A1	Regular	
svf/jamo-extra/GOTHA18A.SVF	Gothic A1	Regular	
svf/jamo-extra/GOTHA20.SVF	Gothic A1	Regular	
svf/jamo-extra/GOTHA20A.SVF	Gothic A1	Regular	
svf/jamo-extra/GOTHA24.SVF	Gothic A1	Regular	
svf/jamo-extra/GOTHA24A.SVF	Gothic A1	Regular	
svf/jamo-extra/GOTHB16.SVF	Gothic A1	Bold	
svf/jamo-extra/GOTHB16A.SVF	Gothic A1	Bold	
svf/jamo-extra/GOTHB18.SVF	Gothic A1	Bold	
svf/jamo-extra/GOTHB20.SVF	Gothic A1	Bold	
svf/jamo-extra/GOTHB20A.SVF	Gothic A1	Bold	
svf/jamo-extra/GOTHB24.SVF	Gothic A1	Bold	
svf/jamo-extra/GOTHB24A.SVF	Gothic A1	Bold	
svf/jamo-extra/NDGPR16.SVF	Neo Dunggeunmo Pro		
svf/jamo-extra/NDGPR32.SVF	Neo Dunggeunmo Pro		
svf/jamo-extra/NSQRB16.SVF	NanumSquareRound	Bold	
svf/jamo-extra/NSQRB16A.SVF	NanumSquareRound	Bold	
svf/jamo-extra/NSQRB18.SVF	NanumSquareRound	Bold	
svf/jamo-extra/NSQRB18A.SVF	NanumSquareRound	Bold	
svf/jamo-extra/NSQRB20.SVF	NanumSquareRound	Bold	
svf/jamo-extra/NSQRB20A.SVF	NanumSquareRound	Bold	
svf/jamo-extra/NSQRB24.SVF	NanumSquareRound	Bold	
svf/jamo-extra/NSQRB24A.SVF	NanumSquareRound	Bold	
svf/jamo-extra/NSQRR16.SVF	NanumSquareRound	Regular	
svf/jamo-extra/NSQRR18.SVF	NanumSquareRound	Regular	
svf/jamo-extra/NSQRR18A.SVF	NanumSquareRound	Regular	
svf/jamo-extra/NSQRR20.SVF	NanumSquareRound	Regular	
svf/jamo-extra/NSQRR20A.SVF	NanumSquareRound	Regular	
svf/jamo-extra/NSQRR24.SVF	NanumSquareRound	Regular	
svf/jamo-extra/NSQRR24A.SVF	NanumSquareRound	Regular	
svf/jamo-extra/SGDAY16.SVF	Single Day	Regular	
svf/jamo-extra/SGDAY16A.SVF	Single Day	Regular	
svf/jamo-extra/SGDAY18.SVF	Single Day	Regular	
svf/jamo-extra/SGDAY18A.SVF	Single Day	Regular	
svf/jamo-extra/SGDAY20.SVF	Single Day	Regular	
svf/jamo-extra/SGDAY20A.SVF	Single Day	Regular	
svf/jamo-extra/SGDAY24.SVF	Single Day	Regular	
svf/jamo-extra/SGDAY24A.SVF	Single Day	Regular	
```

## Open questions

None.
