# WASM font picker: design (card t_fe9f6c30)

A static page under `web/` that draws every face in `svf/` with the C renderer compiled to WebAssembly, lets the user
compose a face chain (Latin face + Hangul face), size, target and sample text, and exports picker choices as JSON in the
shape `tools/pairing2svf.py` reads (`scummvm-ko-font-pairing/1`). No server-side code; hosting is out of scope.

## Page structure (`web/`)

- Sources, committed: `index.html`, `picker.js` (one ES module, no framework, no external script), `style.css`,
  `mkindex.py` (index generator), `LICENCES.tsv` (face glob -> licence files), `build.sh`, `test/` (below), `README.md`.
- Built output, not committed (`.gitignore`): `web/dist/` = the sources copied + `svf.js` + `svf.wasm` + `faces.json` +
  `faces/<group>/<FILE>.SVF` and `licences/<group>/<FILE>.TXT` copied from `svf/`. The page fetches only from its own
  directory, so `dist/` is self-contained (about 21 MB; faces are fetched lazily, so a visit costs the index + the faces
  looked at). `python3 -m http.server -d web/dist` serves it for a look; the test harness serves it the same way.
- `faces.json` (`svf-fonts-web-index/1`): one entry per `svf/**/*.SVF|svf` (153 today): `key` (`svf/dos/PAPLG18.SVF`,
  the repository path, also the picker's face key), `url` (`faces/dos/PAPLG18.SVF`), `group` (dos, jamo-extra, iolo,
  games/lb1), `label` (FACES.TSV family for jamo-extra, else the licence note's first line without its parenthesis, else
  the stem), `cell` [w, h], `px` (cell h), `bpp`, `ascent`, `glyphs`, `jamo` (valid JSET), `flags`, `bytes`,
  `licences` [urls]. Values come from `tools/jamoset.parse_svfn` + `unpack`, so they agree with the renderer's view.
- Licence mapping: `svf/dos` notes name their faces in their first line, some by glob (`GBATB*.SVF`), and a face may have
  two texts (`PAPLG.TXT` note + `OFLPAPLG.TXT` licence); 4 families (BHSAN, COUSB, GOTHB, NSQR*) are named by no note.
  So the mapping is explicit: `web/LICENCES.tsv` rows `glob<TAB>licence[,licence]` relative to `svf/` (jamo-extra rows
  from FACES.TSV's `licence` column, iolo -> `iolo/IOLO.TXT` + the two LICENSE files, games/lb1 -> `dos/DKBHG.TXT`).
  `mkindex.py` fails (exit 2, naming the face) when a face matches no row or a named file is missing: no face ships
  without its licence text, and a new face added to `svf/` breaks the build until a row covers it.
- Layout: left, the face list (filter by group / px / bpp / jamo, search by name) with each row's px, bpp and bytes;
  centre, the preview canvas and controls; right, the face card (header values, status bits, licence text in a scrolling
  `<pre>`, loaded from `licences/`) and the choices table with the export box. Dark and light follow the system.
  Rendering is on the main thread (a 40 code point line draws in under 1 ms, c/bench/MEASUREMENTS.md); a face is
  fetched once and kept in the module heap (`Map` key -> pointer), GBATB47 (1.6 MB) included.

## The WASM module (`c/ports/web/svf_web.c`, extended; `web/build.sh`)

The existing glue is kept (its five functions and README stay valid; `c/cross/build-all.sh --ports` still builds it) and
gains, all `EMSCRIPTEN_KEEPALIVE`, each returning `svf_err` unless said:
- `svfw_reset()` closes every slot (chain count 0) so the page can rebuild the chain in a new order.
- `svfw_order(first)` puts slot `first` first in the chain (the other slots keep their order); `svfw_order(0)` is slot
  order again. No face is reopened (the per-run order of the Chain control below).
- `svfw_info(slot, out)`: `out[0..7]` (int32) = bpp, cell_w, cell_h, ascent, flags, status, glyph count, is_jamo.
- `svfw_has(slot, cp)` -> `svf_has` (the face list marks which of the sample's code points a face lacks).
- `svfw_target2(kind, buf, buf_len, w, h, stride, fg565, bg565, threshold, flags)`: any `svf_target_kind` but the
  callback (GRAY8, MONO_PAGE, MONO_ROW, RGB565), replacing `svfw_target` for the page.
- Scratch: `svf_chain_scratch_bytes` can exceed the 64 KB static buffer (GBATB47, a 46 x 54 cell at 2 bpp, needs about
  637 KB at 16/1), so the glue
  grows its scratch with `malloc` on demand (the glue is a port, not `c/src/`; the no-malloc gate covers `c/src/` only).
- `web/build.sh [OUT]` (default `web/dist`): the emcc line of build-all.sh (`-std=c99 -Wall -Wextra -Werror -O2`,
  `-sMODULARIZE -sEXPORT_ES6 -sEXPORT_NAME=SvfModule -sALLOW_MEMORY_GROWTH`, exported runtime methods `HEAPU8`,
  `HEAP16`, `HEAP32`), run from `~/opt/emsdk` (emcc 6.0.13, as `c/cross/install-toolchains.sh` installs it; `EMSDK`
  overrides the path), then `mkindex.py`, then the copies. It writes only under OUT and prints the output sizes.

## Controls

- Chain: Latin face select (any face, or none) + Hangul face select. The page splits each line into runs by character
  class (user decision 2026-10-20: the Hangul face must draw the Hangul even when the Latin face has Hangul too; the C
  renderer is unchanged):
  - Hangul class: U+1100-11FF, U+3130-318F, U+A960-A97F, U+AC00-D7A3, U+D7B0-D7FF. A combining mark (the renderer's
    `svf_is_mark_default`) joins the run of the character before it; a mark that starts a line has none before it
    and is the Latin class. A lone surrogate is U+FFFD (as the UTF-8 encoder writes it), the Latin class. Everything
    else (ASCII, space, punctuation, other) is the Latin class.
  - A Hangul-class run is drawn with the order [Hangul, Latin]; a Latin-class run with [Latin, Hangul] (the other face
    is the fallback for a missing glyph; within a run the first face with the code point wins). With no Latin face
    chosen the chain is [Hangul] for every run, so a Hangul face's own ASCII shows.
  - Runs sit on one shared baseline per line; x advances by each run's measured width. A line's ascent/descent is the
    max over its runs; the canvas size and the status line's measure come from these totals.
  The face list's "use as Latin" / "use as Hangul" buttons set them. The card shows each face's bpp, cell, ascent, glyph count and jamo flag.
- Size: a scale ratio `num/den` (each 1..16) from a select of common ratios (1/2, 2/3, 1, 3/2, 2, 3, 4, 6, 8) plus two
  number inputs; the resulting px height (`ceil(cell_h * num / den)`) is shown next to it. A separate view zoom (1-8,
  nearest neighbour, optional pixel grid) enlarges the canvas without changing the pixels drawn.
- Sample text: a textarea with presets: pangram `다람쥐 헌 쳇바퀴에 타고파`, boundary clash `국궉귁개객게각`, rare
  `뛔횰쓿긹`, double finals `삶닭값읊핥`, ASCII (`!"#$%&'()*+,-./0-9:;<=>?@A-Z[\]^_\`a-z{|}~`), mixed game line
  `King's Quest IV: 로제라의 모험 (1988)`, compat jamo `ㄱㄴㄷㄹㅁㅂㅅ ㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ`, marks `é à`.
  Multi-line text draws one line per `\n`; each line is its own measured ascent + descent + 2 high, the lines stacked;
  an empty line gets the chain's line (max scaled ascent + max scaled descent over the open faces + 2), so blank lines
  keep paragraph spacing; the status line shows the maxima of the measured lines.
- Target: GRAY8 (ink colour over paper colour, coverage as alpha), MONO (row target, threshold 1..255 slider, black on
  white), RGB565 (fg/bg colour pickers quantised to 5/6/5, blend done by the renderer, pixels expanded to 8-bit for
  display). The canvas is the widest line + 2 wide and the sum of the line heights high (each line its own ascent +
  descent + 2, an empty line the chain's line height); the renderer draws, JS only converts.
- Status line: the measure (width, ascent, descent), draw time, `svf_err` names on failure, ink pixel count.

## A picker choice and the export

A choice = one original game font paired with the current chain and scale: the user fills game (datalist of the 24 names
`pairing2svf.TEMPLATES` knows, free text allowed), font id (free text, e.g. `cs3`, `300`), original line height
(number, optional) and presses "Add choice". Choices sit in a table (remove, re-render) and in `localStorage` (prefs and
choices only, in try/catch). Export writes the JSON to a textarea, "Copy" and "Download selection.json" (a Blob URL):

```json
{"format": "scummvm-ko-font-pairing/1", "created": "2026-10-20T12:00:00Z", "order": "per-run", "source": "svf-fonts web picker",
 "games": [{"game": "KQ4", "fonts": [{"id": "300", "lineh": 12, "picked": true,
   "korean": {"key": "svf/dos/PAPLG18.SVF", "label": "Paperlogy faces 18 px", "family": "Paperlogy", "style": "Regular",
              "variant": "first build, no Latin", "w": 18, "h": 18, "bpp": 2, "ascent": 17,
              "file": "svf/dos/PAPLG18.SVF", "latin": "svf/dos/NGOTB16.SVF", "scale": [1, 1]}}]}]}
```

`games[].game`, `fonts[].id`, `fonts[].lineh`, `fonts[].picked`, `korean.key/label/w/h/bpp` are what pairing2svf
reads (`w`, `h`, `ascent` are the scaled cell, so `h / lineh` is the multiplier it computes); `file`, `latin`, `scale`,
`order` (how the Latin and Hangul faces were combined: per run), `family`, `style`, `variant` and `source` are extra keys it ignores
(added by the face-selection redesign). The key is the repository path, so a later `pairing2svf --data` that reads SVF
files directly (not this card) resolves it; today's `korean*.json` lookup will not find it, which the README says.

## Test plan

- `tools/test_web_picker.py` (runs under the existing gate `python3 -m unittest discover -s tools -p 'test_*.py'`;
  each class skips with a message when its tool is missing):
  - `TestIndex`: `mkindex.py` over `svf/` lists all 153 faces, every entry's header fields equal `parse_svfn`, every
    `licences` url exists, a face no row covers makes it exit 2.
  - `TestModule` (emsdk + node): `web/test/render.mjs` (node, `-sENVIRONMENT=web,node` build) draws a chain, text,
    scale and target kind to stdout; byte-identical with `tools/svfline.py` `layout` / `to_target` for PAPLG16+PAPLG18
    at 1/1, 2/1 and 3/2, HGKEY6J (iolo jamo), GOTHA24A (2 bpp), GBATB47 (the largest face) in GRAY8, MONO_ROW (threshold
    128 and 1) and RGB565 (two colour pairs).
  - `TestPage` (node + `web/test/node_modules/playwright-core` + a Chrome): runs `web/test/check.mjs` and asserts its
    report: every face of the index rendered the pangram + ASCII preset with `svf_err` 0 and ink > 0; three screenshots
    (PAPLG18 over NGOTB16 at 2/1 GRAY8, HGKEY6J at 3/1 MONO, GBATB47 at 1/2 RGB565) and the export screenshot exist and
    are non-trivial PNGs; `selection.json` has the format string and passes pairing2svf's reading of `games[].fonts[]
    .korean.key`; the licence pane shows the first line of each shown face's licence text.
- Browser: `playwright-core` 1.62.1 pinned in `web/test/package.json` (installed by `npm ci` there, `node_modules`
  ignored); it drives the system Google Chrome 152 (`channel: "chrome"`, `/opt/google/chrome/chrome`), `PICKER_BROWSER`
  overriding the executable. The cached Playwright Chromium 1217 (Chrome 147) belongs to an older Playwright and is not
  used. node is `~/opt/node-v24.13.0-linux-x64/bin/node` (`NODE` overrides). Artifacts go to `web/test/out/` (ignored):
  the PNGs, `selection.json`, `faces-report.tsv` (face, err, ink, ms) and `browser.txt` (the versions used).
- The page exposes `window.picker` (the same functions the UI calls: `ready`, `select`, `setText`, `setScale`,
  `setTarget`, `render`, `addChoice`, `exportJSON`) so the check drives it without CSS selectors beyond screenshots.
