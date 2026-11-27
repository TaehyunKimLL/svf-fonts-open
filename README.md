**English** | [한국어](README.ko.md)

# svf-fonts

A bitmap font environment: the SVF (SVFN) format, the fonts in it, and the tools that make and check them.
It started as the font side of the ScummVM Korean hi-res text work; ScummVM is one user of it (as a git submodule),
and it is meant to serve others, such as embedded targets (ESP32, Raspberry Pi Pico, Arduino), where a jamo-set face draws
all 11,172 Hangul syllables from a few kilobytes of pieces (the Arduino Uno example's face, `svf/dos/NEODG16G.SVF`, is 10,124 B in the `mcu-strict` layout, `c/cross/SIZES.md`).
Development status: [docs/STATUS.md](docs/STATUS.md).

## Licence

The code, the specification and the documentation are MIT ([LICENSE](LICENSE)). The fonts and the faces made from them
are all under the SIL Open Font License 1.1, each with its licence text beside it; [NOTICE.md](NOTICE.md) lists them
and how this repository reads their Reserved Font Names. [docs/recipes.md](docs/recipes.md) says how every face is made from its
upstream font, and how to convert other kinds of Korean fonts (TrueType/OpenType outlines, X11 BDF/PCF, DOS johab, classic
Mac) to SVF, by input kind.

## Rules

- This repository is the master of the fonts. Faces are made, changed and checked only here; users take them as they are.
- Tools write only to a path given as an argument. No script writes into another repository.
- Every face travels with its licence text.

## Layout

| Path | What |
| --- | --- |
| `spec/SVF.md` | the SVFN v3 format (header, layout bytes, tables, glyph records, profiles, jamo sets JSET v1/v2, BIG, JMAP and LIST, per-glyph dy; v1 and v2 retired) |
| `docs/STATUS.md` | development status: components, timeline, open cards, decisions, known gaps |
| `docs/tools.md` | every tool: its purpose, inputs, outputs and options, and the gaps that remain; the recipes are in `docs/recipes.md` |
| `docs/desktop-app.md` | the SVF maker desktop app: Quick start (build from a checkout, first conversion), how to use it, messages, recovery and uninstall, privacy and security, limits |
| `docs/c-renderer-guide.md` | integration guide for the C renderer: build, open faces, draw lines, targets, scaling, Hangul, memory, troubleshooting |
| [docs/web-renderer-guide.md](docs/web-renderer-guide.md) | web renderer guide: emsdk build, WASM loading, canvas and Node examples, colours, measurement, memory, picker API |
| `docs/jamo-sets.md` | johab (조합형) explained: the character set, the font technique and its set systems (8x4x4 and others), SVF's JSET v1/v2/BIG/JMAP/LIST with a worked example, and the constraints on MCUs |
| `docs/recipes.md` | the recipes chapter: a quick start by input kind (outline, bitmap, DOS raw, classic Mac, existing SVF), each recipe re-run with its numbers, the maker's route table (route to command line), and how each face of `svf/` is made |
| `docs/superpowers/specs/`, `docs/superpowers/plans/` | design documents and implementation plans, one pair per feature, named by date; they are the working record and still name faces, tools and paths of the original working repository that this one leaves out |
| `svf/dos/` | precomposed and jamo-set faces (first made for the ScummVM Korean maps), with their licence `.TXT` files |
| `svf/jamo-extra/` | extra jamo-set faces from composite-glyph fonts (`FACES.TSV`) |
| `ttf/<family>/` | TrueType faces the maps use (`FONTS.md`) |
| `c/` | the portable C renderer ([c/README.md](c/README.md): API, switches, gates), its tests (`make -C c check`), the port examples `c/ports/{pico,esp32,arduino,ch582,dos,web,sdl}` with their host checks `c/ports/check`, and the emulated benches `c/bench` |
| `maker/` | the SVF maker: a small web service that bakes faces from an uploaded font with the tools below (`maker/server.py`) |
| `desktop/` | the SVF maker desktop app: an Electron shell around the maker and the build of its Linux AppImage (`docs/desktop-app.md`, `docs/maker-desktop.md`) |
| `web/` | the WASM font picker page, its face index and tests ([web/README.md](web/README.md)) |
| `tools/` | font tools and their tests (`python3 -m unittest discover -s tools -p 'test_*.py'`); the SVF maker's tests: `python3 -m unittest discover -s maker/test -p 'test_*.py'`; `facecheck.py` checks faces against a manifest and maps; `macfbit3.py`, `macfbit_svf.py` and `macsfnt.py` convert classic Mac fonts the user supplies (no such font is distributed) |
| `tools/build/` | `build_faces.py` and its recipe table `faces.tsv`: rebuild the faces of `svf/` from the fonts in `ttf/` and compare |
| `manifest/` | the sha256 baseline of every face (`facecheck.py verify`) |

Game-side checks that read a game's translation bundle (`facecoverage.py`, `bake-supplements.py`, `charsetchars.py`)
stay with the games (ScummVM `tools/korean`) and import these tools from the submodule.

The examples of the C renderer (Pico, ESP32-C3, ESP32-S3 in colour, grey and mono profiles, the Arduino Uno and Mega,
the WCH CH582M with an SH1106 OLED, DOS, WASM and SDL2/SDL3) build with `sh c/cross/build-all.sh --ports`, which also runs
their host checks and emulated screens; the original ESP32 has size rows only. Sizes are in `c/cross/SIZES.md`, speeds
in `c/bench/MEASUREMENTS.md`.
