# WASM font picker (card t_fe9f6c30)

A static page that draws text with SVF faces through the C renderer compiled to WebAssembly (`c/ports/web/svf_web.c`,
see `c/ports/web/README.md`). Pick a size, a family and a variant, set a Latin and a Hangul face, scale and render
target, then record the choice for a game font and export it as `selection.json` (a font-pairing selection; the tool that
turned it into game maps belonged to the game side and is not in this repository).

## Build and serve

    bash web/build.sh [OUT]                    # default web/dist; needs emsdk ($EMSDK, default ~/opt/emsdk)
    python3 -m http.server -d web/dist         # then open http://localhost:8000/

`build.sh` writes svf.wasm and svf.js, `faces.json` (`web/mkindex.py`), `faces/<group>/<FILE>.SVF` and
`licences/<group>/<FILE>` (`web/copyfaces.py`) and copies index.html, picker.js and style.css. It writes only under OUT and
prints `svf.wasm N bytes, svf.js N bytes, F faces, N MB copied`.

**`web/dist` is for local use.** It bundles faces whose licence is not stated or whose source is proprietary (see the notes in
`LICENCES.tsv`), and converted OFL faces under their Reserved Font Names. Do not publish it as is.

Committed: `index.html`, `picker.js`, `style.css`, `build.sh`, `mkindex.py`, `copyfaces.py`, `LICENCES.tsv`, `FAMILIES.tsv`,
`test/` (without `node_modules` and `out`). Generated, never committed: `web/dist/`, `web/test/out/`,
`web/test/node_modules/`.

## The face index (`mkindex.py`)

    python3 web/mkindex.py svf OUT_JSON [--licences TSV] [--families TSV]
    python3 web/mkindex.py svf --check                  # every check, nothing written

One entry per `svf/**/*.SVF`. Besides the header values it holds `hangul` (how many of the 2,350 KS X 1001 syllables the face
draws), `latin_only`, `subset`, and `family`, `style`, `variant`.

- **Subset rule:** a face that is not a jamo set, is not Latin-only and draws fewer than 2,350 syllables is `subset`. Subset
  faces (per-game supplements) are in the index but hidden: no chip, row or select entry, and a URL naming one is refused.
- **Latin-only rule:** not a jamo set, `hangul == 0` and every printable ASCII character U+0021..U+007E in the cmap (space excluded). These faces are offered
  in the Latin select only, never as a Hangul face or in the family list.
- **Counts line**, the last line `mkindex.py` prints: `153 faces, 120 listed (2 latin-only), 33 subset, 0 unmapped`. Listed =
  not subset (Latin-only included).

### FAMILIES.tsv

Tab-separated, `#` and blank lines skipped. The header row names the columns; `file` and `family` are required, `style` and
`variant` optional, other columns ignored. One row per listed face; `file` is the index key `svf/<rel>`. Empty style or
variant is allowed; a row shorter than the header is padded with empty cells. Subset faces need no row.

`mkindex.py` exits 2, names `FAMILIES.tsv:<line>` or the face, and writes nothing when:

- the header lacks `file` or `family`, or repeats a column name, or there is no header;
- a row has more cells than the header, an empty `file`, a `file` not starting with `svf/`, or a file already on an earlier line;
- a family, style or variant is over 256 characters;
- a listed face has no row, or its row has an empty family;
- a row names a file that is no face (a stale row);
- two listed faces share family, style, px, bpp, composition (jamo), cell size and variant (a collision: give one a `variant`).

The licence check runs first, so a tree with both an unmapped face and a missing family row reports the licence error.
`--families` names another table (tests use fixtures).

**Adding a face:** put the `.SVF` under `svf/`, add one row to `web/LICENCES.tsv` (glob to licence files) and one row to
`web/FAMILIES.tsv` (file, family, style, variant), then `python3 web/mkindex.py svf --check`.

## Page behaviour worth knowing

URL parameters (read at load; every fault is a notice and a default, never an exception):

| parameter | value | fallback |
| --- | --- | --- |
| `hangul` | key of a listed (left-list) face | absent: the default NGOTB16 opens, no notice; empty, unknown, hidden subset or Latin-only: the default opens, with a notice |
| `latin` | key of a face that is not subset, or empty for none | absent: the Hangul face's own; unknown or subset: none, with a notice; empty: none |
| `scale` | `n/d`, each 1..16 | 1/1, with a notice |
| `manual` | present | nothing is opened (no default, no prefetch); `scale` is still read; a bad face is still a notice |

A query over 2,048 characters, or a key or value over 256, is ignored ("URL ignored: too long"). A pick, a select and
`setScale` rewrite the URL (no history entry) and keep other parameters; a reload restores the chain.

The **notice element** (`#notice`, `role="status"`, hidden when empty) shows URL faults, an unreadable stored-choices value
("stored choices unreadable: starting empty", or "N stored choices skipped: not valid"), a failed save, and the summary of the
size prefetch. A URL notice is kept and the prefetch summary is appended to it ("; "); a later action clears it.

A game and id are one choice: `addChoice` refuses a repeat (after trimming), and the loader keeps the first of a repeat and says so in the notice. `korean.scale` is the raw ratio as entered. A stored choice whose key is no longer in the index is kept, marked and exported.

Saved choices are in `localStorage` (`svfpicker.choices`), at most 256, each held to `addChoice`'s rules (names without control
characters, C1 included, and no `|` in game and id; `lineh` absent or 1..65535; game and id trimmed).

## Export

`window.picker.exportJSON()` (the Download button, `selection.json`) writes `scummvm-ko-font-pairing/1`: `format`, `created`,
`order` (`"per-run"`), `source`, and `games[{game, fonts[...]}]`; a font entry has `id`, `picked`, an optional `lineh` and the `korean` block. Each `korean` block has `key`, `file`, `label` (the index
label), `family`, `style`, `variant`, `latin`, `scale`, `w`, `h`, `bpp`, `ascent`. Game and id hold no control
character and no `|` (the picker refuses both, in `addChoice` and in stored choices), so a consumer can write them into
line-oriented maps and Markdown tables as they are.

## window.picker

Face selection: `listed()` (faces with `subset` false, Latin-only included), `sizes()` (the chip px list), `families(px)` ->
`[{family, style, name, faces, default}]` (Latin-only excluded), `defaultVariant(family, style, px)` -> key or `null`,
`pick(key)` (= `select({latin: key, hangul: key})`, no prefetch; rejects a key that is not a left-list face),
`setSize(px)` (shows the chip, prefetches the size, resolves `{px, fetched, held, skipped, failed, stopped}`; rejects for a px with no faces),
`view()` -> `{px, family, style, variant, hangul, latin, same, listed}`, `notice()` (the text of `#notice`).

Older calls: `presets`, `faces()`, `select({latin, hangul})`, `prefetch(key, keep)`, `lacking(text)`, `faceMemory()`, `setFaceBudget(n)`,
`setText`, `setScale`, `setTarget`, `render`, `chain()`, `addChoice({game, id, lineh})`, `choices()`, `removeChoice(i)`,
`exportJSON()`; `ready` resolves when the module, the index and the default pair are loaded. Test hooks: `setNotice`,
`holdHeap`, `pendingKeys`, `prefetching`, `idle`, `module`, `spyAfterPick`, `licence`, `runs`, `pixels`, `settings`, `covers`.

## Tests

    python3 -m unittest discover -s tools -p 'test_*.py'

- **TestIndex** (no browser): `mkindex.py` over `svf/` and fixture trees. Needs only Python.
- **TestCopyFaces** (no browser): `web/copyfaces.py` keeps every path `faces.json` names under `svf/` and OUT. Needs only Python.
- **TestModule**: builds the module with `build.sh` into a temp dir and draws with `web/test/render.mjs` under node; every
  buffer must equal `tools/svfline.py`. Skips when emcc (`$EMSDK`, default `~/opt/emsdk`) or node (`$NODE`,
  `~/opt/node-v24.13.0-linux-x64/bin/node`, then PATH) is missing.
- **TestPage** and **TestExportShape**: run `web/test/check.mjs DIST OUT` once (playwright-core, Chrome, the built dist) and
  check its output in `web/test/out/` (`faces-report.tsv`, PNGs, `cases.txt`, `selection.json`). Skip when `web/test/node_modules`
  is missing (`cd web/test && npm ci`), when no Chrome launches (`PICKER_BROWSER=/path/to/chrome` names one) or when emcc/node is missing.

Run it by hand: `node web/test/check.mjs web/dist web/test/out` (exit 0 ok, 1 a case failed, 2 cannot run).
The C renderer's own tests: `make -C c check`.
