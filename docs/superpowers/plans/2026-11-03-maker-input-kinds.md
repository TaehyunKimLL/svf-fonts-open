# Maker input kinds (audit gap 5) Implementation Plan

> **Correction (2026-11-23, t_d4cf7f46).** Where this document calls `ASCII.PFT` a 12x24 English font of 12,288 bytes,
> it means the 12x24 `.PFT` layout of Taebaek 3.5.1 (`GASCII24.PFT` / `MASCII24.PFT`), which the tests build under the
> name `ASCII.PFT`. HWP 1.x's own `ASCII.PFT` is 14x24 (41,654 bytes: a 32-byte header and 991 glyphs); since t_d4cf7f46
> it is read by its header (`tools/hwpfont.py`, docs/recipes.md "HWP 1.x and 2.x fonts").

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The SVF maker detects, plans and converts the input kinds of `docs/maker-audit.md` gap list item 5: a chosen
variable-font instance, TTC/OTC faces after the first, Mac TrueType with only a Mac Korean (1,3) / Wansung (3,5) cmap,
`.dfont` / suitcase / AppleDouble / MacBinary containers, KS X 1001 and johab PCF, a `johab844.py` route, HWP
a 12x24 `.PFT` (`ASCII.PFT` in the tests) and HBIOS 12x24 as `--eng`, a `--from-svf` jamo step after `bdfface.py`, and the embedded-bitmap
(`EBLC`/`bloc`) strike sizes. Card t_f3ef3189.

**Architecture:** Three layers, in this order. (A) Detection: a new maker-side module `maker/srcprep.py` reads the new
containers and tables (TTC face, `fvar`, `EBLC`, Mac cmap, resource forks, PCF), and `detect.py` turns them into font
entries that carry a `prep` list (the source conversions the file needs before any existing tool can read it) and
facts (`variable`, `strikes`, `eng`, `dos_bytes`), without new `source_kind` values. (B) Job planning: one new step
kind `source`, planned once per font before its face steps, runs the `prep` ops (plus the chosen VF instance) into
`work/sNN/source.*`; every later step of that font reads that file. New routes (`johab844`, `bdfface + from-svf
fit`) and the 12x24 `--eng` rules sit on top. (C) UI: `static/maker.js` and `presets.panel_argv` expose the new routes
and the instance choice.

**Tech Stack:** Python 3 stdlib, fontTools 4.66.1 (`fontBuilder`, `ttCollection`, `varLib.instancer`), Pillow 10.2.0
(FreeType), unittest; the page is plain ES module JavaScript (node 22 used only for `node --check`).

**Spec:** `docs/maker-audit.md` (section 1 table rows and section 7 gap list item 5) and `docs/recipes.md` (sections
"Mac-format TrueType", "OpenType CFF, collections and variable fonts", "X Window Korean fonts", "HWP 1.x and 2.x
fonts", "Other DOS-era Korean fonts"). Executors read both. All commands run from the worktree root
`~/work/svf-fonts-open-wt/maker-inputs` (branch `maker-inputs`, base `4ff3a6c`). No push.

## Global Constraints

- No network access in code or tests.
- No proprietary font data in the repository or generated from it: every fixture is built inside the test (fontTools
  fonts, tiny BDF/PCF/raw files, hand-built resource forks) or derived from the repository's OFL faces
  (`svf/dos/NEODG16.SVF`, `ttf/`). Real-file tests skip unless their env var names a file:
  `SVF_MAKER_REAL_TTC`, `SVF_MAKER_REAL_VF`, `SVF_MAKER_REAL_MACTTF`, `SVF_MAKER_REAL_DFONT`, `SVF_MAKER_REAL_PCF_KSC`,
  `SVF_MAKER_REAL_PFT`, `SVF_MAKER_REAL_EBDT` (all in `maker/test/test_real_inputs.py`).
- No new dependency. freetype-py, uharfbuzz and `pcf2bdf` are not installed on this host and **no new route needs
  them**: they serve only the GSUB-mask route (gap 4, out of scope); PCF is read by the maker's own reader.
- Every tool runs as an argv list through the existing worker path (`jobs.run_command`), argv built from
  `routes.PY` (`[sys.executable, "-P"]`) + a script path, or `PY + ["-m", "fontTools.varLib.instancer", ...]`.
- `tools/` stays untouched. Two steps have no tool there: saving TTC face N and PCF -> BDF. Both live in the new
  maker-side CLI `maker/srcprep.py` (subcommands `ttc-face`, `pcf-bdf`), which inserts `maker/` and `tools/` into
  `sys.path` itself (it runs under `-P`, which drops the script directory).
- The existing 431 maker tests stay green at every commit. The only existing expectation that changes is
  `test_detect.DetectTest.test_ttc_two_faces` (face 1 becomes convertible, Task A3). `test_server.canonical_fonts`
  gains `"dos_bytes": 11520` in its base entry (Task B5).
- New font-entry keys are present only when they apply (like `gzip`): `prep` (list of op dicts), `variable`,
  `strikes`, `eng`, `dos_bytes`. No new `source_kind` value; `presets.ALL_SOURCES` and `PREVIEW_KINDS` do not change.
- Prep op dicts, exactly: `{"op": "ttc-face", "index": N}`, `{"op": "rsrc-sfnt", "id": RID}`, `{"op": "mac-cmap"}`,
  `{"op": "pcf-bdf"}`, and (planning only, never in an entry) `{"op": "instance", "coords": {TAG: number}}`.
- New step kind `"source"` (no size, bpp, layout or name); new per-font settings key `"instance"` (None or
  `{tag: number}`).
- Out of scope: source/result preview and controls (t_9acea7ab), local-only mode and Mac `fbit` conversion
  (t_cbd14d61), Electron, packaging.
- Full suite on hpz2 runs through the OOM guard: `~/.local/bin/heavy python3 -m unittest discover -s maker/test -p
  'test_*.py'`. One test: `python3 -m unittest discover -s maker/test -p 'test_X.py' -k NAME`.

## Review Focus

1. **A 15,360-byte file that reads as both a Dokkaebi 7x2x2 face and an HBIOS 12x24 English font.** The Dokkaebi
   opener accepts any 15,360 bytes, so detection decides by `detect.hbios_eng_like`; a Dokkaebi face with ink in an
   HBIOS margin row must stay `dos-raw`. Pinned by `test_detect_inputs.EngTest.test_a_dokkaebi_face_with_margin_ink_stays_dos_raw` (A5).
2. **A Mac container whose resource map is corrupt, or that holds only `NFNT`/`fbit`.** It must become exactly one
   entry (`unknown` with the reason, or `other` "Mac bitmap font"), never vanish and never be an `unreadable`
   traceback. Pinned by `MacContainerTest.test_a_corrupt_fork_is_one_unknown_entry` and
   `test_a_fork_with_only_bitmap_fonts_is_other` (A4).
3. **`.gz`-wrapped new kinds** (`.ttc.gz`, `.dfont.gz`, `.pcf.gz` KSC): the `source` step must read the decompressed
   bytes (`.ttc.gz`, `.dfont.gz` through the worker's F-gz rewrite; a `.pcf.gz` stays compressed and `srcprep.pcf_to_bdf`
   inflates it). Pinned by `SourceStepE2ETest.test_a_gz_ttc_face_1_converts` (B1) and
   `PcfE2ETest.test_a_gz_ksc_pcf_converts` (B3).
4. **An instance value the font cannot take**: an unknown axis tag, a value outside `min..max`, a non-number, or an
   instance on a static font, refused by `validate` with one message each, not at the tool. Pinned in
   `InstanceSettingsTest` (B2).
5. **A Mac-cmap font that also has a Unicode subtable, and an OTC (CFF) face after the first.** The first must get no
   `mac-cmap` op (`macsfnt.py unicode` refuses such a font); the second must convert through the same `ttc-face`
   source step. Pinned by `SfntDetectTest.test_a_font_with_both_cmaps_gets_no_mac_cmap_op` (A3) and
   `SourceStepE2ETest.test_otc_cff_face_1_converts` (B1).

## Verified while planning (fontTools 4.66.1, Pillow 10.2.0, this host)

- A raw `EBLC` table set as `fontTools.ttLib.tables.DefaultTable.DefaultTable("EBLC")` with `.data` saves and reads
  back through `TTFont(...).reader["EBLC"]`; a font with `glyf`/`loca` deleted and `maxp.tableVersion = 0x00005000`
  saves with `TTFont(recalcBBoxes=False)`.
- `python3 -P -m fontTools.varLib.instancer vary.ttf wght=700 -o bold.ttf` exits 0, drops `fvar`, applies `gvar`.
- `TTCollection(path).fonts[1].save(out)` writes a plain sfnt.
- `tools/test_macsfnt.py` exports `mac_korean_font()` (bytes) and `resource_fork(entries)`; maker tests import them.
- `jamoset.read_eng` already takes 12,288 (PFT 12x24) and 15,360 (HBIOS 12x24) bytes; `johab844.py` takes exactly
  11,520 bytes, layout 844, and an 8x16 `--eng` (2,048/4,096 bytes) only.
- `/usr/share/fonts/X11/misc/18x18ko.pcf.gz` (xfonts-base, public domain) is ISO10646, so it stays `bitmap`; it is
  used only as an optional cross-check of the PCF reader (skipped when absent).

Not verified (the named tests verify them): Pillow opening a PCF written by the fixture writer (A2
`test_pillow_opens_the_fixture_pcf`); `jamoset.py --from-svf` on a `bdfface.py` face built from NEODG16's 2,350
syllables passing `--check` (B4); FreeType reading `.dfont` directly (not used: the maker always extracts).

## The output-zip check ("passes facecheck.py")

`facecheck.py` has no zip mode. The plan defines the check once, in `maker/test/inputkinds.py`
`assert_facecheck(test, zip_path)`: extract the zip into a temp dir `D`; `git init` and commit `D` (`-c user.name=t
-c user.email=t@t`); run `python3 tools/facecheck.py manifest --git D --rev HEAD --path svf -o M` (exit 0, at least
one row); run `python3 tools/facecheck.py verify M` with cwd `D` (exit 0, no output); and every `svf/**/*.SVF` in the
zip parses with `jamoset.parse_svfn` as version 3. (Flagged for the user; see the end.)

## File map

| File | Status | Responsibility |
|---|---|---|
| `maker/srcprep.py` | create | Reading helpers (TTC face, `fvar`, strikes, Mac cmap, resource forks, PCF) and the `ttc-face` / `pcf-bdf` CLI |
| `maker/detect.py` | modify | Sniff `mac-rsrc` and 12,288-byte `eng`; entries with `prep`/`variable`/`strikes`/`eng`/`dos_bytes`; coverage on prepared bytes |
| `maker/routes.py` | modify | `source_commands`; prep-aware face-index rule; routes `johab844`, `bdfface + from-svf fit` |
| `maker/settings.py` | modify | `instance` key, its validation, the `source` step, eng/johab844 rules |
| `maker/jobs.py` | modify | Run `source` steps; cascade their failure; quality reference reads the prepared source |
| `maker/zipout.py` | modify | Log heading of a `source` step |
| `maker/presets.py` | modify (C1) | `panel_argv` for the new route labels |
| `maker/static/maker.js` | modify | Mirror tables (B4, B5); instance chooser, source rows, route rules (C1) |
| `maker/server.py` | modify (C1) | `instance` in `_changed_preview_fonts` keys and `_kept_settings` |
| `maker/test/inputfx.py` | create | Synthetic fixture builders for the new kinds |
| `maker/test/inputkinds.py` | create | `run_batch`, `assert_facecheck`, `step_tools` |
| `maker/test/test_srcprep.py` | create | srcprep unit tests |
| `maker/test/test_detect_inputs.py` | create | detection of the new kinds |
| `maker/test/test_plan_inputs.py` | create | planning, settings and end-to-end runs of the new kinds |
| `maker/test/test_real_inputs.py` | create | env-gated real-file runs |

---

# Group A: detection

### Task A1: srcprep reading helpers and the fixture builders

**Files:**
- Create: `maker/srcprep.py`, `maker/test/inputfx.py`, `maker/test/test_srcprep.py`

**Interfaces:**
- Produces (`maker/srcprep.py`):
  - `class PrepError(Exception)`
  - `MAX_BYTES = 128 << 20` (the same cap as `detect.MAX_DECOMPRESSED`; srcprep does not import detect)
  - `ttc_face_bytes(data: bytes, index: int) -> bytes` - face @p index of a TTC/OTC saved as a plain sfnt; `PrepError` when out of range.
  - `variable_info(font: TTFont) -> dict | None` - `{"axes": [{"tag", "min", "default", "max"}], "instances": [{"name": str, "coords": {tag: number}}]}` from `fvar` (instance name = the name table string of `subfamilyNameID`, else `"instance N"`); None without `fvar`.
  - `embedded_strikes(font: TTFont) -> list[int]` - sorted unique `ppemY` of the raw `EBLC` (else `bloc`) table: u32 version, u32 numSizes, then numSizes 48-byte records, ppemY at record byte 45; [] when absent or truncated.
  - `has_outlines(font: TTFont) -> bool` - any of `glyf`, `CFF `, `CFF2` present.
  - `mac_cmap_only(font: TTFont) -> bool` - no Unicode subtable (`st.isUnicode()`) and at least one (1,3) or (3,5) subtable.
  - `mac_resources(data: bytes) -> tuple[str, list]` - `(container, [(type, id, name, body)])`, container one of `"AppleDouble"`, `"MacBinary"`, `"resource fork"`; wraps `macsfnt.resource_fork` + `macsfnt.resources`; `macsfnt.MacError`, `struct.error` and `IndexError` (a map offset past the data) re-raised as `PrepError`.
  - `prepared_bytes(data: bytes, ops: list[dict]) -> bytes` - the ops applied in order in-process: `rsrc-sfnt` (the body of the `sfnt` resource with that id), `ttc-face` (`ttc_face_bytes`), `mac-cmap` (`macsfnt.add_unicode` on a TTFont, saved to bytes), `pcf-bdf` (Task A2). An `instance` op raises `PrepError` (detection never instantiates).
  - CLI `python3 -P maker/srcprep.py ttc-face SRC OUT --index N` (exit 0 and OUT written; exit 2 with the message on `PrepError`).
- Produces (`maker/test/inputfx.py`, every builder returns bytes):
  - `ttf(family: str, ga_box: tuple, a_box=(100, 0, 400, 700)) -> bytes` - glyphs `.notdef`, `A`, `ga` (U+0041, U+AC00), a Unicode cmap.
  - `otf(family: str, ga_box: tuple) -> bytes` - the same as CFF (FontBuilder `isTTF=False`, `setupCFF`).
  - `ttc(fonts: list[bytes]) -> bytes` (TTCollection of the given fonts)
  - `variable_ttf() -> bytes` - family `Vary`, axis `wght` 100/400/900, named instances Regular 400 and Bold 700, a `gvar` delta that moves `ga`'s right edge by -40 at wght max.
  - `mac_cmap_ttf() -> bytes` - `test_macsfnt.mac_korean_font()`.
  - `both_cmaps_ttf() -> bytes` - `mac_cmap_ttf()` plus a (3,1) format 4 subtable.
  - `fork(entries) -> bytes` - `test_macsfnt.resource_fork(entries)`.
  - `appledouble(fork: bytes) -> bytes`, `macbinary(fork: bytes, name=b"Synth") -> bytes` - the wrappers exactly as `tools/test_macsfnt.py test_resources_and_wrappers` builds them.
  - `eblc_ttf(ppems=(12, 16)) -> bytes` - `ttf("Strike", ...)` plus raw `EBLC` (records with ppemX = ppemY) and a 4-byte `EBDT`.
  - `bitmap_only_ttf(ppems=(12, 16)) -> bytes` - `eblc_ttf` with `glyf`/`loca` deleted, `maxp` version `0x00005000`, saved with `recalcBBoxes=False`.

- [ ] **Step 1: Write the failing tests** in `maker/test/test_srcprep.py`, class `SrcprepTest`:

```python
def test_ttc_face_bytes_saves_face_1(self):
    data = inputfx.ttc([inputfx.ttf("One", (50, 0, 950, 800)), inputfx.ttf("Two", (300, 0, 700, 400))])
    face = TTFont(io.BytesIO(srcprep.ttc_face_bytes(data, 1)))
    self.assertEqual(face["name"].getDebugName(1), "Two")
    with self.assertRaises(srcprep.PrepError):
        srcprep.ttc_face_bytes(data, 2)

def test_variable_info(self):
    info = srcprep.variable_info(TTFont(io.BytesIO(inputfx.variable_ttf())))
    self.assertEqual(info["axes"], [{"tag": "wght", "min": 100, "default": 400, "max": 900}])
    self.assertEqual(info["instances"], [{"name": "Regular", "coords": {"wght": 400}},
                                         {"name": "Bold", "coords": {"wght": 700}}])
    self.assertIsNone(srcprep.variable_info(TTFont(io.BytesIO(inputfx.ttf("S", (0, 0, 9, 9))))))

def test_embedded_strikes_and_outlines(self):
    self.assertEqual(srcprep.embedded_strikes(TTFont(io.BytesIO(inputfx.eblc_ttf((16, 12, 16))))), [12, 16])
    self.assertEqual(srcprep.embedded_strikes(TTFont(io.BytesIO(inputfx.ttf("S", (0, 0, 9, 9))))), [])
    self.assertFalse(srcprep.has_outlines(TTFont(io.BytesIO(inputfx.bitmap_only_ttf()))))
    self.assertTrue(srcprep.has_outlines(TTFont(io.BytesIO(inputfx.otf("C", (0, 0, 9, 9))))))

def test_mac_cmap_only(self):
    self.assertTrue(srcprep.mac_cmap_only(TTFont(io.BytesIO(inputfx.mac_cmap_ttf()))))
    self.assertFalse(srcprep.mac_cmap_only(TTFont(io.BytesIO(inputfx.both_cmaps_ttf()))))
    self.assertFalse(srcprep.mac_cmap_only(TTFont(io.BytesIO(inputfx.ttf("S", (0, 0, 9, 9))))))

def test_mac_resources_names_the_container(self):
    fk = inputfx.fork([(b"sfnt", 128, "Synth", inputfx.mac_cmap_ttf()), (b"NFNT", 200, "", bytes(26))])
    for blob, name in ((fk, "resource fork"), (inputfx.appledouble(fk), "AppleDouble"),
                       (inputfx.macbinary(fk), "MacBinary")):
        container, res = srcprep.mac_resources(blob)
        self.assertEqual((container, [(t, i) for t, i, _, _ in res]), (name, [(b"sfnt", 128), (b"NFNT", 200)]))
    with self.assertRaises(srcprep.PrepError):
        srcprep.mac_resources(fk[:40])

def test_prepared_bytes_chains_ops(self):
    fk = inputfx.fork([(b"sfnt", 129, "", inputfx.mac_cmap_ttf())])
    out = TTFont(io.BytesIO(srcprep.prepared_bytes(inputfx.appledouble(fk),
                                                    [{"op": "rsrc-sfnt", "id": 129}, {"op": "mac-cmap"}])))
    self.assertEqual(out.getBestCmap()[0xAC00], "ga")
    with self.assertRaises(srcprep.PrepError):
        srcprep.prepared_bytes(b"", [{"op": "instance", "coords": {}}])

def test_cli_ttc_face(self):
    # writes the TTC to a temp dir, runs [sys.executable, "-P", srcprep.py, "ttc-face", src, out, "--index", "1"]
    # asserts exit 0 and TTFont(out) family "Two"; "--index 5" exits 2 with "face" in stderr
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_srcprep.py'`. Expected: ERROR, `No module named 'srcprep'` / `'inputfx'`.
- [ ] **Step 3: Implement** `maker/test/inputfx.py` and `maker/srcprep.py` to the interfaces above. `inputfx` puts `maker/`, `tools/` on `sys.path` like `fixtures.py` and imports `test_macsfnt` from `tools/`. `HEAD_TIME = fixtures.HEAD_TIME` on every built font's `head.created/modified`.
- [ ] **Step 4: Run** the same command. Expected: `OK`.
- [ ] **Step 5: Commit** `git add maker/srcprep.py maker/test/inputfx.py maker/test/test_srcprep.py && git commit -m "maker: srcprep reading helpers and synthetic input fixtures (t_f3ef3189)"`.

### Task A2: the PCF reader

**Files:**
- Modify: `maker/srcprep.py`, `maker/test/inputfx.py`, `maker/test/test_srcprep.py`

**Interfaces:**
- Consumes: A1 `PrepError`, `MAX_BYTES`, `prepared_bytes`.
- Produces:
  - `srcprep.pcf_properties(data: bytes) -> dict[str, str | int]` - the PCF properties table (type 1); `data` may be gzip (magic `1f 8b`, inflated in 1 MiB chunks up to `MAX_BYTES`, else `PrepError("too large")`).
  - `srcprep.pcf_to_bdf(data: bytes) -> bytes` - a BDF 2.1 text (latin-1) of every encoded glyph; `PrepError` on a non-PCF or a table that runs past the data.
  - `prepared_bytes(..., [{"op": "pcf-bdf"}])` now returns `pcf_to_bdf(data)`.
  - CLI `srcprep.py pcf-bdf SRC OUT`.
  - `inputfx.pcf(glyphs, registry: str, encoding: str, px: int, ascent: int, descent: int, family="Fixture") -> bytes` - glyphs `[(code, rows: list[int], width: int)]` all `px` high; tables properties (1), accelerators (2), metrics (4, uncompressed), bitmaps (8), BDF encodings (0x20); format word `0x0000000C` (MSByte, MSBit, glyph pad 1, scan unit 1) on every table. Properties: `FONT`, `FAMILY_NAME`, `PIXEL_SIZE`, `FONT_ASCENT`, `FONT_DESCENT`, `CHARSET_REGISTRY`, `CHARSET_ENCODING`.

Reader rules (the algorithm the tests do not determine): TOC = `"\x01fcp"`, u32 LE count, then `(type, format, size, offset)` u32 LE records. Each table begins with its own u32 LE format word; bit 2 (`4`) set = big-endian integers in that table; bit 3 (`8`) set = MSBit first; `format & 3` = glyph row pad `1 << n` bytes; `(format >> 4) & 3` = scan unit `1 << n`. Metrics: `0x100` = compressed (u16 count, 5 bytes each, value - 0x80: lsb, rsb, width, ascent, descent), else u32 count of six i16 (lsb, rsb, width, ascent, descent, attributes). Bitmaps: u32 count, count u32 offsets, 4 u32 sizes, then data; a glyph is `ascent + descent` rows of `ceil((rsb - lsb) / 8)` bytes padded to the row pad; reverse the bits of each byte when MSBit is clear; swap bytes inside each scan unit when the byte order differs from the bit order. Encodings: i16 `min_byte2, max_byte2, min_byte1, max_byte1, default_char`, then `(max_byte2 - min_byte2 + 1) * (max_byte1 - min_byte1 + 1)` u16 glyph indices (`0xFFFF` = none), code = `(byte1 << 8) | byte2`. BDF: `FONTBOUNDINGBOX` = the union of ink boxes, `BBX w h lsb -descent`, `DWIDTH width 0`, `SWIDTH round(width * 72000 / (PIXEL_SIZE * 75)) 0`, properties copied (strings quoted), `CHARS` = encoded glyph count, glyphs in code order.

- [ ] **Step 1: Write the failing tests** (class `PcfTest` in `test_srcprep.py`):

```python
GLYPHS = [(0x3021, [0x8001 | (y << 3) for y in range(16)], 16), (0x3022, [0xFFFF if y == 8 else 0 for y in range(16)], 16)]

def test_properties_and_gzip(self):
    data = inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2)
    for blob in (data, gzip.compress(data)):
        p = srcprep.pcf_properties(blob)
        self.assertEqual((p["CHARSET_REGISTRY"], p["CHARSET_ENCODING"], p["PIXEL_SIZE"]), ("KSC5601.1987", "0", 16))

def test_pcf_to_bdf_round_trips_through_bdfface(self):
    bdf = srcprep.pcf_to_bdf(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2))
    path = self.write("k.bdf", bdf)
    glyphs = bdfface.read_bdf(path)[1]
    self.assertEqual(sorted(glyphs), [0x3021, 0x3022])
    self.assertEqual(glyphs[0x3022][4][8], 0xFFFF)            # bdfface's row ints, row 8
    self.assertIn(b"FONTBOUNDINGBOX 16 16 0 -2", bdf)

def test_lsbit_and_lsbyte_tables_read_the_same(self):
    # inputfx.pcf(..., fmt=0x00000000 | 0x10 (scan unit 2) | 0x1 (pad 2)) gives the same BDF glyph rows as the default

def test_pillow_opens_the_fixture_pcf(self):
    data = inputfx.pcf([(0x41, [0x8001] * 16, 16)], "ISO10646", "1", 16, 14, 2)
    font = ImageFont.truetype(self.write("a.pcf", data), 16)
    self.assertIsNotNone(font.getmask("A").getbbox())

def test_truncated_pcf_is_a_prep_error(self):
    with self.assertRaises(srcprep.PrepError):
        srcprep.pcf_to_bdf(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2)[:200])

@unittest.skipUnless(os.path.isfile(fixtures.PCF_SRC), "no 18x18ko.pcf.gz on this host")
def test_the_host_pcf_converts(self):
    glyphs = bdfface.read_bdf(self.write("h.bdf", srcprep.pcf_to_bdf(open(fixtures.PCF_SRC, "rb").read())),
                              unicode_enc=True)[1]
    self.assertGreater(len([cp for cp in glyphs if 0xAC00 <= cp <= 0xD7A3]), 2000)
```

`inputfx.pcf` takes an optional `fmt=0x0000000C` used for the bitmaps table only in `test_lsbit_and_lsbyte_tables_read_the_same`.

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_srcprep.py' -k Pcf`. Expected: ERROR, `module 'inputfx' has no attribute 'pcf'`.
- [ ] **Step 3: Implement** `inputfx.pcf`, `srcprep.pcf_properties`, `srcprep.pcf_to_bdf`, the `pcf-bdf` op and CLI.
- [ ] **Step 4: Run** the same. Expected: `OK` (the host test skips where the file is absent).
- [ ] **Step 5: Commit** `git commit -m "maker: srcprep PCF reader (pcf_properties, pcf_to_bdf, pcf-bdf) (t_f3ef3189)"`.

### Task A3: sfnt-family detection (TTC faces, VF, Mac cmap, strikes, bitmap-only) and prepared coverage

**Files:**
- Modify: `maker/detect.py:346-350` (ttf/otf), `:462-484` (`_ttc_entries`), `:992-1022` (`_coverage_of_entry`), `:1039-1130` (`scan`); `maker/routes.py:253` (temporary guard); `maker/test/test_detect.py:492-500`
- Create: `maker/test/test_detect_inputs.py`

**Interfaces:**
- Consumes: A1 `variable_info`, `embedded_strikes`, `has_outlines`, `mac_cmap_only`, `ttc_face_bytes`, `prepared_bytes`.
- Produces:
  - `detect._sfnt_facts(font: TTFont) -> dict` - `{"variable": ..., "strikes": [...], "mac_cmap": bool, "outlines": bool}`; every sfnt entry (ttf, otf, every TTC face, and the Mac sfnts of A4) is built through `detect._sfnt_entry(rel, face_index, fmt, label, font: TTFont, prep: list, gz: bool) -> dict`.
  - Entry rules: `source_kind` `"outline"` when `outlines`, else `"bitmap"` with `sizes = strikes`, `sizes_fixed = True` (no strikes: `"other"`, label `"... no outlines, no bitmap strikes"`). `prep` = the given ops + `{"op": "mac-cmap"}` when `mac_cmap`; key omitted when empty. `variable` only when not None; `strikes` only when non-empty.
  - Labels: `"TTF"`/`"OTF"`/`"TTC face N"`; then `"; variable (wght 100..900)"` (axes joined by `", "`, numbers `%g`); `"; bitmap strikes 12, 16"`; `"; Mac Korean cmap"`. A bitmap-only face's label starts with `"TTF bitmap-only"`.
  - TTC faces: face 0 keeps `prep` empty (`TTC face 0`); face N > 0 gets `[{"op": "ttc-face", "index": N}]`; the `_FACE_CAP` and "; more faces not listed" rules stay.
  - `detect.coverage_cmap(path, face_index=0, data=None) -> dict` - `coverage_of` over `TTFont(...).getBestCmap()`; used for an sfnt `bitmap` entry (format in `ttf`, `otf`, `ttc`, `mac-rsrc`).
  - `scan`: an entry with `prep` gets `src = srcprep.prepared_bytes(data_or_file_bytes, entry["prep"])` once, and its composite test and coverage run on `src` with face index 0; a `PrepError` leaves coverage None and appends `"; cannot prepare: <reason>"` to the label.
  - `routes.routes`: `if font.get("prep"): return []` with the comment `# until the source step exists (Task B1)` (removed in B1).

- [ ] **Step 1: Write the failing tests** in `maker/test/test_detect_inputs.py`, class `SfntDetectTest` (each writes its bytes under a temp dir and calls `detect.detect_file` / `detect.scan`):

```python
def test_ttc_face_1_is_an_outline_with_a_ttc_face_op(self):
    out = detect.detect_file(self.put("two.ttc", inputfx.ttc([inputfx.ttf("One", BOX1), inputfx.ttf("Two", BOX2)])), "two.ttc")
    self.assertEqual([(e["face_index"], e["label"], e["source_kind"], e["family"], e.get("prep")) for e in out],
                     [(0, "TTC face 0", "outline", "One", None),
                      (1, "TTC face 1", "outline", "Two", [{"op": "ttc-face", "index": 1}])])

def test_variable_font_carries_axes_and_instances(self):
    e = detect.detect_file(self.put("Vary.ttf", inputfx.variable_ttf()), "Vary.ttf")[0]
    self.assertEqual(e["label"], "TTF; variable (wght 100..900)")
    self.assertEqual([i["name"] for i in e["variable"]["instances"]], ["Regular", "Bold"])
    self.assertNotIn("prep", e)

def test_mac_cmap_font_gets_the_op_and_composed_coverage(self):
    self.put("mac/Mac.ttf", inputfx.mac_cmap_ttf())
    e = detect.scan(self.dir("mac"))[0]
    self.assertEqual((e["label"], e["prep"]), ("TTF; Mac Korean cmap", [{"op": "mac-cmap"}]))
    self.assertEqual((e["coverage"]["ascii"], e["coverage"]["all"]), (1, 1))

def test_a_font_with_both_cmaps_gets_no_mac_cmap_op(self):
    e = detect.detect_file(self.put("Both.ttf", inputfx.both_cmaps_ttf()), "Both.ttf")[0]
    self.assertNotIn("prep", e)

def test_strikes_are_listed(self):
    e = detect.detect_file(self.put("S.ttf", inputfx.eblc_ttf((12, 16))), "S.ttf")[0]
    self.assertEqual((e["source_kind"], e["strikes"], e["sizes_fixed"]), ("outline", [12, 16], False))
    self.assertTrue(e["label"].endswith("; bitmap strikes 12, 16"))

def test_bitmap_only_sfnt_is_a_bitmap_at_its_strikes(self):
    self.put("b/B.ttf", inputfx.bitmap_only_ttf((12, 16)))
    e = detect.scan(self.dir("b"))[0]
    self.assertEqual((e["source_kind"], e["sizes"], e["sizes_fixed"]), ("bitmap", [12, 16], True))
    self.assertEqual(e["coverage"]["ascii"], 1)                # coverage_cmap, not the picture test
    self.assertTrue(e["label"].startswith("TTF bitmap-only"))

def test_ttc_face_1_coverage_and_composite_use_the_face(self):
    # scan of a TTC [ttf("One"), fixtures._composite_ttf bytes]: face 1 becomes "outline-composite", face 0 "outline"

def test_a_prepped_font_offers_no_route_yet(self):
    e = detect.detect_file(self.put("Mac.ttf", inputfx.mac_cmap_ttf()), "Mac.ttf")[0]
    self.assertEqual(routes.routes(e), [])
```

  Change `test_detect.DetectTest.test_ttc_two_faces`'s face 1 expectation to `(1, "outline", "TTC face 1")` and assert `out[1]["prep"] == [{"op": "ttc-face", "index": 1}]`.

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_detect_inputs.py'`. Expected: FAIL (face 1 is `other`, no `variable` key, ...).
- [ ] **Step 3: Implement** in `detect.py` and the guard in `routes.py`.
- [ ] **Step 4: Run** `test_detect_inputs.py` and `test_detect.py`. Expected: `OK`.
- [ ] **Step 5: Commit** `git commit -m "maker: detect TTC faces, variable fonts, Mac cmaps and bitmap strikes (t_f3ef3189)"`.

### Task A4: Mac containers (dfont, suitcase / resource fork, AppleDouble, MacBinary)

**Files:**
- Modify: `maker/detect.py:84-117` (`sniff`), `_detect_file`
- Modify: `maker/test/test_detect_inputs.py`

**Interfaces:**
- Consumes: A1 `mac_resources`, A3 `_sfnt_entry`.
- Produces:
  - `detect._mac_head(data: bytes, size: int) -> bool` - True for an AppleDouble head (`00 05 16 07`), a MacBinary head (`data[0] == 0`, `1 <= data[1] <= 63`, `data[74] == 0`, `data[82] == 0`, resource length at 87 non-zero and `128 + pad128(data length at 83) + rlen <= size`), or a raw fork header (`>IIII` data_off, map_off, data_len, map_len with `data_off >= 16`, `data_off + data_len <= map_off`, `map_len >= 30`, `map_off + map_len == size`).
  - `sniff` returns `"mac-rsrc"` from `_mac_head`, checked last, where `"unknown"` was returned (every existing tag keeps its precedence).
  - `_detect_file` for `mac-rsrc`: one entry per `sfnt` resource, `face_index` = its order among the sfnts, `format` `"mac-rsrc"`, label `"<container>: sfnt <id>"` (+ A3 suffixes), `prep` `[{"op": "rsrc-sfnt", "id": RID}]` (+ `mac-cmap`), family from the sfnt's name table. No sfnt but an `NFNT`/`FONT`/`fbit` resource: one `"other"` entry, label `"Mac bitmap font (NFNT/fbit): not converted here (local-only mode)"`. `PrepError` (a corrupt map): one `"unknown"` entry, label `"unknown (Mac resource fork: <reason>)"`.

- [ ] **Step 1: Write the failing tests** (class `MacContainerTest`):

```python
def test_each_wrapper_lists_its_sfnts(self):
    fk = inputfx.fork([(b"FOND", 128, "Synth", bytes(52)), (b"sfnt", 128, "Synth", inputfx.mac_cmap_ttf()),
                       (b"sfnt", 129, "", inputfx.ttf("Plain", BOX1))])
    for name, blob, container in (("F.dfont", fk, "resource fork"), ("._F", inputfx.appledouble(fk), "AppleDouble"),
                                  ("F.bin", inputfx.macbinary(fk), "MacBinary")):
        out = detect.detect_file(self.put(name, blob), name)
        self.assertEqual([(e["format"], e["face_index"], e["label"], e["source_kind"], e["prep"]) for e in out],
                         [("mac-rsrc", 0, container + ": sfnt 128; Mac Korean cmap", "outline",
                           [{"op": "rsrc-sfnt", "id": 128}, {"op": "mac-cmap"}]),
                          ("mac-rsrc", 1, container + ": sfnt 129", "outline", [{"op": "rsrc-sfnt", "id": 129}])])

def test_sniff_tags(self):
    fk = inputfx.fork([(b"sfnt", 128, "", inputfx.ttf("P", BOX1))])
    self.assertEqual(detect.sniff(fk[:512], len(fk)), "mac-rsrc")
    self.assertEqual(detect.sniff(bytes(512), 11520), "dos-raw")     # a blank-led DOS raw font is not a fork

def test_a_fork_with_only_bitmap_fonts_is_other(self):
    e, = detect.detect_file(self.put("B.dfont", inputfx.fork([(b"NFNT", 200, "", bytes(26))])), "B.dfont")
    self.assertEqual((e["source_kind"], e["label"]),
                     ("other", "Mac bitmap font (NFNT/fbit): not converted here (local-only mode)"))

def test_a_corrupt_fork_is_one_unknown_entry(self):
    fk = bytearray(inputfx.fork([(b"sfnt", 128, "", inputfx.ttf("P", BOX1))]))
    struct.pack_into(">H", fk, struct.unpack_from(">I", fk, 4)[0] + 24, 0xFFF0)   # type list offset past the map
    e, = detect.detect_file(self.put("C.dfont", bytes(fk)), "C.dfont")
    self.assertEqual(e["format"], "unknown")
    self.assertTrue(e["label"].startswith("unknown (Mac resource fork: "))

def test_a_mac_sfnt_coverage_is_read_through_the_ops(self):
    # scan of a dir with F.dfont (sfnt 128 = mac_cmap_ttf): entry coverage["all"] == 1
```

- [ ] **Step 2: Run** `-k MacContainer`. Expected: FAIL (`unknown` format).
- [ ] **Step 3: Implement.** In the corrupt-fork case `_mac_head` was true but `mac_resources` raised; catch `srcprep.PrepError` inside the `mac-rsrc` branch (never let it reach `detect_file`'s generic `unreadable`).
- [ ] **Step 4: Run** `test_detect_inputs.py` and `test_detect.py`. Expected: `OK`.
- [ ] **Step 5: Commit** `git commit -m "maker: detect Mac resource-fork, AppleDouble and MacBinary fonts (t_f3ef3189)"`.

### Task A5: KSC/johab PCF, 12x24 English companions, DOS raw byte size

**Files:**
- Modify: `maker/detect.py` (`sniff`, the `pcf`, `dos-raw` and `eng` branches, `_entry` callers), `maker/test/test_detect_inputs.py`, `maker/test/inputfx.py`

**Interfaces:**
- Consumes: A2 `pcf_properties`, `pcf_to_bdf`; A3 prepared coverage in `scan`.
- Produces:
  - `detect.ENG_SIZES = {2048: "8x16", 4096: "8x16", 12288: "12x24", 15360: "12x24"}`; `sniff` returns `"eng"` for 2048/4096/12288 (15,360 stays `dos-raw` first).
  - Every `eng` entry gets `"eng": {"bytes": N, "cell": ENG_SIZES[N]}`; the 12,288 label is `"Latin companion (--eng, 12x24)"`; the 8x16 label is unchanged.
  - `detect.hbios_eng_like(data: bytes) -> bool` - `len(data) == 15360`; for all 256 glyphs of 60 bytes (16x30, 2 bytes a row) rows 0-2 and 27-29 are zero and every row's second byte has `& 0x0F == 0`; and glyph 0x41 has ink. Such a file becomes format `"eng"`, `source_kind` `"other"`, label `"HBIOS 12x24 English (--eng)"`, `eng` `{"bytes": 15360, "cell": "12x24"}` instead of a Dokkaebi `dos-raw` entry.
  - A convertible `dos-raw` entry gets `"dos_bytes": len(data)`.
  - PCF: `reg, enc` = `pcf_properties` `CHARSET_REGISTRY`/`CHARSET_ENCODING` lower-cased; `_bdf_kind(reg)` in (`bdf-ksc5601`, `bdf-johab`) -> format `"pcf"`, that `source_kind`, label `"PCF (<reg>)"`, `bdf` `{"registry": "<reg>-<enc>", "box": FONTBOUNDINGBOX [w, h] of pcf_to_bdf}`, `sizes` `[h]`, `sizes_fixed` True, `prep` `[{"op": "pcf-bdf"}]`. Every other PCF keeps today's `bitmap` path. The KSC companions rule (`latin_ids`) is unchanged.
  - `inputfx.pft_eng() -> bytes` (12,288: 256 glyphs x 48 bytes, row 12 of each = `0xFF 0xF0`), `inputfx.hbios_eng() -> bytes` (15,360: 256 x 60, row 14 of each = `0xFF 0xF0`), `inputfx.dkb_like() -> bytes` (15,360 with byte 0 of every 60-byte block = `0xFF`).

- [ ] **Step 1: Write the failing tests** (classes `EngTest`, `PcfDetectTest`):

```python
def test_pft_is_a_12x24_eng(self):
    e = detect.detect_file(self.put("ASCII.PFT", inputfx.pft_eng()), "ASCII.PFT")[0]
    self.assertEqual((e["format"], e["label"], e["eng"]), ("eng", "Latin companion (--eng, 12x24)",
                                                           {"bytes": 12288, "cell": "12x24"}))

def test_hbios_english_is_an_eng_not_a_dokkaebi_face(self):
    e, = detect.detect_file(self.put("ROMAN24.FNT", inputfx.hbios_eng()), "ROMAN24.FNT")
    self.assertEqual((e["format"], e["source_kind"], e["label"]), ("eng", "other", "HBIOS 12x24 English (--eng)"))

def test_a_dokkaebi_face_with_margin_ink_stays_dos_raw(self):
    out = detect.detect_file(self.put("HANGUL16.FNT", inputfx.dkb_like()), "HANGUL16.FNT")
    self.assertEqual([e["source_kind"] for e in out], ["dos-raw", "dos-raw"])

def test_a_12x24_eng_is_a_companion_of_a_dos_font_beside_it(self):
    fixtures._dos_raw(self.path("d/HAN.FNT"))                 # 11,520 bytes, 8x4x4
    self.put("d/ASCII.PFT", inputfx.pft_eng())
    fonts = detect.scan(self.dir("d"))
    dos = [e for e in fonts if e["source_kind"] == "dos-raw"][0]
    self.assertEqual((dos["dos_bytes"], len(dos["companions"])), (11520, 1))

def test_ksc_pcf_is_a_ksc_bdf_source(self):
    self.put("p/k.pcf", inputfx.pcf(PCF_KSC_GLYPHS, "KSC5601.1987", "0", 16, 14, 2))
    e = detect.scan(self.dir("p"))[0]
    self.assertEqual((e["format"], e["source_kind"], e["bdf"], e["sizes"], e["prep"]),
                     ("pcf", "bdf-ksc5601", {"registry": "ksc5601.1987-0", "box": [16, 16]}, [16], [{"op": "pcf-bdf"}]))
    self.assertEqual(e["coverage"]["ks2350"], 2)

def test_johab_pcf_is_a_hanterm_source(self):
    e = detect.detect_file(self.put("j.pcf", inputfx.pcf(JOHAB_529, "johab", "1", 16, 13, 3)), "j.pcf")[0]
    self.assertEqual((e["source_kind"], e["prep"]), ("bdf-johab", [{"op": "pcf-bdf"}]))

def test_an_iso10646_pcf_stays_bitmap(self):
    e = detect.detect_file(self.put("u.pcf", inputfx.pcf([(0x41, [0x8001] * 16, 16)], "ISO10646", "1", 16, 14, 2)), "u.pcf")[0]
    self.assertEqual((e["source_kind"], e.get("prep")), ("bitmap", None))
```

  `PCF_KSC_GLYPHS` = GL codes 0x3021 (가) and 0x3022 (각) with distinct rows; `JOHAB_529` = `fixtures._johab_glyphs()` mapped to `(code, rows, 16)`.

- [ ] **Step 2: Run** `-k "Eng or PcfDetect"`. Expected: FAIL.
- [ ] **Step 3: Implement.** Keep `test_detect.test_only_none_surviving_is_not_convertible` green: an all-zero 15,360-byte file is not `hbios_eng_like` (no ink in 0x41).
- [ ] **Step 4: Run** `test_detect_inputs.py`, `test_detect.py`, then the full suite through `heavy`. Expected: `OK`, 431 + new tests.
- [ ] **Step 5: Commit** `git commit -m "maker: detect KSC/johab PCF, 12x24 English companions, DOS raw size (t_f3ef3189)"`.

**Group A review gate.** Reviewer checks detection only: no route is offered for a `prep` entry yet, no existing label or entry shape changed except `test_ttc_two_faces`.

---

# Group B: job planning

### Task B1: the `source` step, and TTC / Mac cmap / Mac container conversions end to end

**Files:**
- Modify: `maker/routes.py` (remove the A3 guard; `source_commands`; face-index rules at `:263-276`), `maker/settings.py:1036-1131` (`plan_steps`), `maker/jobs.py:549-586` (`_run_steps`), `:615-625` (`_run_step`), `:675-700` (`_read_back`), `maker/zipout.py:148-153` (`_step_title`)
- Create: `maker/test/inputkinds.py`, `maker/test/test_plan_inputs.py`, `maker/test/test_real_inputs.py`

**Interfaces:**
- Consumes: A3/A4 entries with `prep`.
- Produces:
  - `routes.SRCPREP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "srcprep.py")`
  - `routes.source_commands(ops: list[dict], src: str, work: str, tools_dir: str) -> tuple[list[list[str]], str]` - one argv per op, op i writing `work/source-<i>.<ext>` and the last writing `work/source.<ext>` (`ext` `bdf` after `pcf-bdf`, else `ttf`); returns `(argvs, final path)`. Argvs: `rsrc-sfnt` -> `PY + [tools/macsfnt.py, "extract", IN, OUT, "--id", RID]`; `ttc-face` -> `PY + [SRCPREP, "ttc-face", IN, OUT, "--index", N]`; `mac-cmap` -> `PY + [tools/macsfnt.py, "unicode", IN, OUT]`; `instance` -> `PY + ["-m", "fontTools.varLib.instancer", IN, *sorted("%s=%g" % (tag, v)), "-o", OUT]`; `pcf-bdf` raises `ValueError("pcf-bdf lands in Task B3")` until B3.
  - `routes.routes`: the outline rule becomes `if face_index > 0 and not font.get("prep"): return []`; the `bitmap`/`bdf-iso10646` rule the same.
  - `settings.plan_steps`: for a selected font whose ops (`font["prep"]`, + B2's instance op) are non-empty, the font's first step is `_step(sid, fid, "source", None, None, None, None, argvs, "work/<sid>/source.<ext>")`; every later step of the font (prepare and faces) gets `paths["src"]` = that file's absolute path.
  - `jobs.Worker`: a `source` step is not read back (like `prepare`); a failed `source` step fails every later step of the same font with `"source failed"`; `_read_back`'s quality reference reads `Worker._prepared_source(job, job_dir, font_id) -> str | None` (the done `source` step's output) before `_plain_source`.
  - `zipout._step_title`: `"## sNN fNN source"` for a `source` step.
  - `inputkinds.run_batch(test, tmp: str, files: dict[str, bytes], choose) -> tuple[dict, str | None]` - store under `tmp`, upload `files` (rel path -> bytes), `detect.scan`, `settings.defaults`, `choose(fonts, settings)` edits settings in place, asserts `settings.validate(...) == []` and `settings.run_ready(fonts, settings, naming.RepoIndex(SVF), upload) == []`, `plan_steps`, saves the job `queued` with its steps, calls `jobs.Worker(store, REPO, SVF, TOOLS).run_job(id)` (not started), returns `(store.load(id), absolute zip path or None)`.
  - `inputkinds.select(settings, fid, dest="new/inputs", bpp=(1,), **per)` - sets `selected` True, `dest`, `bpp` (as a list) and the given keys on one font; `sizes` stays the font's default unless passed. Every end-to-end test below therefore plans one face step per kind unless it passes more sizes.
  - `inputkinds.step_tools(steps) -> list[list[str]]` - per step, per argv: `basename(argv[2])` plus `argv[3]` for `srcprep.py`/`macsfnt.py`, or `"-m " + argv[3]`.
  - `inputkinds.assert_facecheck(test, zip_path)` (see "The output-zip check").
  - `inputkinds.LICENCE = fixtures.SIL_LICENCE`; every batch puts `LICENSE.txt` beside its fonts.

- [ ] **Step 1: Write the failing tests** in `test_plan_inputs.py`:

```python
class SourceCommandsTest(unittest.TestCase):
    def test_ops_chain_through_numbered_files(self):
        argvs, out = routes.source_commands([{"op": "rsrc-sfnt", "id": 128}, {"op": "mac-cmap"}], "/u/F.dfont", "/w", "/T")
        self.assertEqual(argvs, [routes.PY + ["/T/macsfnt.py", "extract", "/u/F.dfont", "/w/source-1.ttf", "--id", "128"],
                                 routes.PY + ["/T/macsfnt.py", "unicode", "/w/source-1.ttf", "/w/source.ttf"]])
        self.assertEqual(out, "/w/source.ttf")

    def test_instance_pins_every_axis(self):
        argvs, _ = routes.source_commands([{"op": "instance", "coords": {"wght": 700, "wdth": 87.5}}], "/u/V.ttf", "/w", "/T")
        self.assertEqual(argvs[0][2:], ["-m", "fontTools.varLib.instancer", "/u/V.ttf", "wdth=87.5", "wght=700", "-o", "/w/source.ttf"])

class SourceStepE2ETest(unittest.TestCase):
    def test_ttc_face_1_converts(self):
        job, z = inputkinds.run_batch(self, self.tmp, {"t/two.ttc": TTC, "t/LICENSE.txt": LIC},
                                      lambda fonts, s: inputkinds.select(s, fid_of(fonts, face=1)))
        self.assertEqual(inputkinds.step_tools(job["steps"]), [["srcprep.py ttc-face"], ["mkfont.py"]])
        self.assertEqual([st["state"] for st in job["steps"]], ["done", "done"])
        inputkinds.assert_facecheck(self, z)
        self.assertEqual(ga_rows(z), ga_rows_of_face("Two"))      # face 1's 가, not face 0's

    def test_a_gz_ttc_face_1_converts(self): ...                  # "t/two.ttc.gz": gzip.compress(TTC); same asserts
    def test_otc_cff_face_1_converts(self): ...                   # ttc([ttf("One"), otf("Cff")]) face 1, job done, facecheck
    def test_mac_cmap_ttf_converts(self):
        # "m/Mac.ttf": mac_cmap_ttf(); tools [["macsfnt.py unicode"], ["mkfont.py"]]; the face has a non-blank U+AC00
    def test_each_mac_container_converts(self):
        # subTest per wrapper (dfont, AppleDouble, MacBinary) of fork([sfnt 128 = mac_cmap_ttf()]):
        # tools [["macsfnt.py extract", "macsfnt.py unicode"], ["mkfont.py"]], job done, facecheck, U+AC00 non-blank
    def test_composite_face_1_runs_its_master_on_the_source(self):
        # TTC [ttf("One"), fixtures._composite_ttf bytes] face 1, kinds ["jamo"], layout "844":
        # step kinds ["source", "prepare", "jamo"], the prepare argv reads ".../source.ttf", job done, quality not None
    def test_a_failed_source_step_fails_the_font(self):
        # a TTC whose face 1 bytes are truncated after detection (overwrite the upload before run_job):
        # steps ["failed", "failed"], the second error "source failed", job state "failed"

class StrikeRouteTest(unittest.TestCase):
    def test_bitmap_only_sfnt_plans_mkfont_at_its_strikes(self):
        # scan of B.ttf = inputfx.bitmap_only_ttf((12, 16)) + LICENSE.txt, select sizes [12]: plan_steps gives one
        # mkfont step whose argv has "--size", "12" and "--bpp", "1" (planned, not run: the fixture EBDT has no glyphs)

class ZipoutSourceTitleTest(unittest.TestCase):
    def test_source_step_title(self):
        self.assertEqual(zipout._step_title({"id": "s01", "font": "f02", "kind": "source"}), "## s01 f02 source")
```

  In `test_real_inputs.py`, `RealInputsTest.test_real_ttc` / `test_real_macttf` / `test_real_dfont`, each
  `@unittest.skipUnless(os.environ.get("SVF_MAKER_REAL_..."), ...)`: run_batch the file with face
  `int(os.environ.get("SVF_MAKER_REAL_TTC_FACE", "1"))` (TTC) or face 0, kinds `["precomposed"]`, size 16, bpp `[1]`;
  assert job `done` and `assert_facecheck`. `test_real_ebdt` (`SVF_MAKER_REAL_EBDT`) runs the file at its first
  listed strike, 1 bpp, the same asserts.

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_plan_inputs.py'`. Expected: FAIL / ERROR (`no attribute 'source_commands'`).
- [ ] **Step 3: Implement** the interfaces. In `plan_steps` the source step is built before the kinds loop, so `prepare` paths see the prepared file too.
- [ ] **Step 4: Run** `test_plan_inputs.py`, then the full suite through `heavy`. Expected: `OK`.
- [ ] **Step 5: Commit** `git commit -m "maker: source step; TTC faces, Mac cmap fonts and Mac containers convert (t_f3ef3189)"`.

### Task B2: variable-font instance choice

**Files:**
- Modify: `maker/settings.py` (`FONT_ONLY_KEYS`, `_FONT_ONLY_DEFAULTS`, `_font_defaults`, `_type_errors`, `_route_errors`, `plan_steps`), `maker/test/test_plan_inputs.py`, `maker/test/test_real_inputs.py`

**Interfaces:**
- Consumes: A3 `variable`; B1 source step.
- Produces:
  - `"instance"` appended to `FONT_ONLY_KEYS`; `_FONT_ONLY_DEFAULTS["instance"] = None`; `_font_defaults` sets `"instance": None` (keeps `test_settings` line 77 green).
  - `settings.instance_coords(font: dict, instance: dict) -> dict` - the full `{tag: value}`: every axis's `default` overlaid by @p instance.
  - Messages (exact): type `"%s: instance is not an object of axis values"` (not None and not a dict with str keys and int/float non-bool values); route `"%s: instance needs a variable font"`, `"%s: instance axis %s is not in the font"`, `"%s: instance %s=%g is outside %g..%g"`.
  - `plan_steps`: a non-None `instance` appends `{"op": "instance", "coords": instance_coords(font, instance)}` after the entry's `prep`.

- [ ] **Step 1: Write the failing tests** (`InstanceSettingsTest`, `InstanceE2ETest`):

```python
def test_instance_rules(self):
    fonts = detect.scan(dir with Vary.ttf + LICENSE.txt); s = settings.defaults(fonts); fid = fonts[0]["id"]
    for value, msg in (({"wght": 950}, "f01: instance wght=950 is outside 100..900"),
                       ({"opsz": 12}, "f01: instance axis opsz is not in the font"),
                       ("Bold", "f01: instance is not an object of axis values"),
                       ({"wght": True}, "f01: instance is not an object of axis values")):
        s["fonts"][fid].update(selected=True, instance=value)
        self.assertIn(msg, settings.validate(fonts, s))
    s["fonts"][fid]["instance"] = {"wght": 700}
    self.assertEqual(settings.validate(fonts, s), [])

def test_instance_on_a_static_font_is_refused(self):
    # ttf("S") with instance {"wght": 400}: "f01: instance needs a variable font"

def test_defaults_carry_instance_none(self):
    self.assertIsNone(settings.defaults(fonts)["fonts"]["f01"]["instance"])

def test_bold_instance_differs_from_the_default(self):
    reg, z1 = inputkinds.run_batch(self, ..., {"v/Vary.ttf": VF, "v/LICENSE.txt": LIC}, select(..., sizes=[24], bpp=[1]))
    bold, z2 = inputkinds.run_batch(self, ..., same files, select(..., sizes=[24], bpp=[1], instance={"wght": 700}))
    self.assertEqual(inputkinds.step_tools(reg["steps"]), [["mkfont.py"]])
    self.assertEqual(inputkinds.step_tools(bold["steps"]), [["-m fontTools.varLib.instancer"], ["mkfont.py"]])
    inputkinds.assert_facecheck(self, z2)
    self.assertNotEqual(ga_rows(z1), ga_rows(z2))
```

  `test_real_inputs.test_real_vf`: `SVF_MAKER_REAL_VF` with the first named instance from the entry's `variable`.

- [ ] **Step 2: Run** `-k Instance`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_plan_inputs.py`, `test_settings.py`, `test_server.py`. Expected: `OK`.
- [ ] **Step 5: Commit** `git commit -m "maker: variable-font instance setting and instancer source op (t_f3ef3189)"`.

### Task B3: KSC and johab PCF through the source step

**Files:**
- Modify: `maker/routes.py` (`source_commands` `pcf-bdf`), `maker/test/test_plan_inputs.py`, `maker/test/inputfx.py`, `maker/test/test_real_inputs.py`

**Interfaces:**
- Consumes: A2 CLI `pcf-bdf`; A5 PCF entries; B1 source step.
- Produces: `pcf-bdf` -> `PY + [SRCPREP, "pcf-bdf", IN, OUT]`, `OUT` ending `.bdf`. `inputfx.ksc_glyphs_from_neodg(limit=None) -> list[(gl_code, rows, 16)]` (the 2,350 KS syllables of `svf/dos/NEODG16.SVF`, rows = `int.from_bytes(cell[2y:2y+2], "big")` of `jamoset.parse_svfn(...).glyphs[cp]`, GL code = euc_kr bytes `& 0x7F7F`) and `inputfx.latin_bdf_from_neodg(path)` (an ISO10646 8x16 BDF of U+0021..U+007E: the left byte of each NEODG16 row, via `fixtures._bdf`).

- [ ] **Step 1: Write the failing tests** (`PcfE2ETest`):

```python
def test_ksc_pcf_precomposed(self):
    files = {"k/ksc.pcf": inputfx.pcf(inputfx.ksc_glyphs_from_neodg(limit=10), "KSC5601.1987", "0", 16, 14, 2),
             "k/latin.bdf": LATIN_BDF, "k/LICENSE.txt": LIC, "k/chars.txt": "가각간\n".encode()}
    job, z = inputkinds.run_batch(self, ..., files, lambda f, s: inputkinds.select(s, ksc_id, range="k/chars.txt"))
    self.assertEqual(inputkinds.step_tools(job["steps"]), [["srcprep.py pcf-bdf"], ["bdfface.py"]])
    inputkinds.assert_facecheck(self, z)
    self.assertEqual(sorted(cp for cp in face_cps(z) if cp >= 0xAC00), [0xAC00, 0xAC01, 0xAC04])

def test_a_gz_ksc_pcf_converts(self): ...       # "k/ksc.pcf.gz" = gzip.compress(same pcf); same asserts

def test_johab_pcf_jamo(self):
    # "j/johab.pcf" = pcf(JOHAB_529, "johab", "1", 16, 13, 3): tools [["srcprep.py pcf-bdf"], ["jamoset.py"]],
    # the jamoset argv has "--layout", "hanterm-johab" and reads ".../source.bdf"; job done; facecheck
```

  `test_real_inputs.test_real_pcf_ksc`: `SVF_MAKER_REAL_PCF_KSC` plus `latin_bdf_from_neodg`, range 2350.

- [ ] **Step 2: Run** `-k PcfE2E`. Expected: FAIL (`pcf-bdf lands in Task B3`).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_plan_inputs.py`. Expected: `OK`.
- [ ] **Step 5: Commit** `git commit -m "maker: KSC and johab PCF convert through pcf-bdf (t_f3ef3189)"`.

### Task B4: KS X 1001 jamo set: `bdfface.py` then `jamoset.py --from-svf`

**Files:**
- Modify: `maker/routes.py` (new route for `bdf-ksc5601`), `maker/static/maker.js:36-50` (ROUTES), `:77-86` (OPTION_VISIBLE), `maker/test/test_plan_inputs.py`

**Interfaces:**
- Consumes: B1/B3 (a KSC PCF reaches it through the source step).
- Produces:
  - `Route("jamo", "bdfface + from-svf fit", False, ["844", "adaptive"], [1], sizes, None, None, _bdfface_fit_commands)` appended after the `bdfface` route for `bdf-ksc5601` (same `box` guard).
  - `routes._bdfface_fit_commands(font, size, bpp, layout, range_spec, paths, extra) -> list[list[str]]` - `[bdfface argv with "-o", work/precomposed.svf, PY + [jamoset.py, "--layout", layout, "--from-svf", work/precomposed.svf, "--check", "-o", out]]`, `extra` applied to the last argv; the same `ValueError`s as `_bdfface_commands`.
  - `maker.js`: `ROUTES["bdf-ksc5601"]` gains `{"kind": "jamo", "label": "bdfface + from-svf fit", "native": false, "bpps": [1]}`; `OPTION_VISIBLE["bdfface + from-svf fit"] = {"1": []}` (panel flags come in C1).
  - `settings._font_kinds` unchanged (a KSC source still defaults to precomposed); the jamo route needs `experimental`.

- [ ] **Step 1: Write the failing tests** (`KscJamoTest`):

```python
def test_route_and_argv(self):
    r = [x.label for x in routes.routes(FONT_KSC)]
    self.assertEqual(r, ["bdfface", "bdfface + from-svf fit"])
    argvs = routes.route_for(FONT_KSC, "jamo", True).commands(FONT_KSC, 24, 1, "844", ("file", "/u/c.txt"), P, [])
    self.assertEqual([a[2].rsplit("/", 1)[1] for a in argvs], ["bdfface.py", "jamoset.py"])
    self.assertEqual(argvs[1][argvs[1].index("--from-svf") + 1], "/w/precomposed.svf")
    self.assertIsNone(routes.route_for(FONT_KSC, "jamo", False))

def test_ksc_bdf_jamo_set_end_to_end(self):
    # "k/ksc.bdf" = fixtures._bdf of ksc_glyphs_from_neodg() (2,350 syllables, registry "KSC5601.1987"),
    # LATIN_BDF, LICENSE.txt; select kinds ["jamo"], experimental True, layout "844", range "2350":
    # tools [["bdfface.py", "jamoset.py"]], job done, facecheck, the face's FLAG_JAMO set (jamoset.parse_svfn(...).jset is not None)
```

- [ ] **Step 2: Run** `-k KscJamo`. Expected: FAIL.
- [ ] **Step 3: Implement** (route + the two maker.js mirror rows; `test_server.test_page_js_tables_match_python` must pass).
- [ ] **Step 4: Run** `test_plan_inputs.py`, `test_routes.py`, `test_server.py`. Expected: `OK`.
- [ ] **Step 5: Commit** `git commit -m "maker: KS X 1001 jamo route (bdfface then jamoset --from-svf) (t_f3ef3189)"`.

### Task B5: the `johab844.py` route

**Files:**
- Modify: `maker/routes.py` (dos-raw branch), `maker/settings.py` (`plan_steps` paths, `_route_errors`), `maker/static/maker.js` (ROUTES, OPTION_VISIBLE), `maker/test/test_server.py:109` (canonical base), `maker/test/test_plan_inputs.py`

**Interfaces:**
- Consumes: A5 `dos_bytes`, `eng`.
- Produces:
  - `routes.JOHAB844_BASE = "dos/NEODG16.SVF"` (relative to `svf/`).
  - For `dos-raw` with `font.get("dos_bytes") == 11520` and `"844"` in its candidates: `Route("precomposed", "johab844", True, [], [1], [16], None, None, _johab844_commands)` before the jamo route.
  - `routes._johab844_commands(...)` -> `[PY + [tools/johab844.py, src, paths["base"], out] + (["--eng", eng] if paths.get("eng") else [])]`.
  - `plan_steps` puts `paths["base"] = os.path.join(os.path.dirname(tools_dir), "svf", JOHAB844_BASE)` in every step's paths.
  - `_route_errors` messages: `"%s: johab844 needs layout 844"` (precomposed selected and `dos_layout != "844"`), `"%s: johab844 takes an 8x16 English font"` (the companion's `eng.cell == "12x24"`).
  - `maker.js` `ROUTES["dos-raw"]` gains `{"kind": "precomposed", "label": "johab844", "native": true, "bpps": [1]}`; `OPTION_VISIBLE["johab844"] = {"1": []}`; `canonical_fonts` base gets `"dos_bytes": 11520`.

- [ ] **Step 1: Write the failing tests** (`Johab844Test`):

```python
def test_offered_only_for_11520_bytes(self):
    self.assertEqual([r.label for r in routes.routes(dict(FONT_DOS, dos_bytes=11520))], ["johab844", "dos raw"])
    self.assertEqual([r.label for r in routes.routes(dict(FONT_DOS, dos_bytes=25920))], ["dos raw"])

def test_layout_and_eng_rules(self):
    # scan of fixtures._dos_raw + ASCII.PFT beside it, kinds ["precomposed"], dos_layout "844-ihnm":
    # validate contains "f01: johab844 needs layout 844"; with dos_layout "844": contains "f01: johab844 takes an 8x16 English font"

def test_johab844_end_to_end(self):
    # HAN.FNT (fixtures._dos_raw) + ENG.FNT (fixtures._eng) + LICENSE.txt; kinds ["precomposed"], dos_layout "844":
    # tools [["johab844.py"]], argv[3] ends "svf/dos/NEODG16.SVF", "--eng" present; job done; facecheck;
    # face 가 = OR of raw slots (johab844.compose(raw, 0xAC00)) byte for byte
```

- [ ] **Step 2: Run** `-k Johab844`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_plan_inputs.py`, `test_routes.py`, `test_server.py`, `test_settings.py`. Expected: `OK`.
- [ ] **Step 5: Commit** `git commit -m "maker: johab844 precomposed route for 16 px 8x4x4 DOS fonts (t_f3ef3189)"`.

### Task B6: 12x24 English companions on DOS jamo routes

**Files:**
- Modify: `maker/settings.py` (`_route_errors`), `maker/test/test_plan_inputs.py`, `maker/test/test_real_inputs.py`

**Interfaces:**
- Consumes: A5 eng entries; existing `_dos_commands` (`--eng` already passed).
- Produces: message `"%s: a 12x24 English font needs a face of 24 px or more"` when the chosen companion's `eng.cell == "12x24"` and the DOS face's px (`font["sizes"][0]`) is below 24.

- [ ] **Step 1: Write the failing tests** (`Eng12x24Test`):

```python
def test_a_16px_face_refuses_a_12x24_eng(self):
    # HAN.FNT (11520, 16 px) + ASCII.PFT: validate contains "f01: a 12x24 English font needs a face of 24 px or more"

def test_pft_and_hbios_eng_on_a_24px_face(self):
    # subTest per companion (inputfx.pft_eng(), inputfx.hbios_eng()): a 25,920-byte 844 raw font
    # (inputfx.dos844_24(): 360 24x24 glyphs, fill slots blank, every other glyph row 0 = 0xFF 0xFF 0xFF),
    # kinds ["jamo"], dos_layout "844": the jamoset argv has "--eng" naming the companion; job done; facecheck;
    # the face's U+0041 glyph is non-blank
```

  `inputfx.dos844_24() -> bytes` added here. `test_real_inputs.test_real_pft`: `SVF_MAKER_REAL_PFT` beside a synthetic `dos844_24()`.

- [ ] **Step 2: Run** `-k Eng12x24`. Expected: the first test FAILS (no such message); the second may already pass (A5 made the companion) and stays as the end-to-end proof.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `test_plan_inputs.py`, then the full suite through `heavy`. Expected: `OK`.
- [ ] **Step 5: Commit** `git commit -m "maker: 12x24 English companions (ASCII.PFT, HBIOS) on 24 px DOS faces (t_f3ef3189)"`.

Embedded-bitmap strikes need no planning task of their own: a bitmap-only sfnt is `bitmap` with `sizes = strikes`
(A3) and takes the existing mkfont route at those sizes; B1 holds its planning test (`StrikeRouteTest`) and the
env-gated real run (`test_real_ebdt`).

**Group B review gate.** Reviewer runs the full suite and checks: every new kind has an end-to-end test that runs the
real tools and passes `assert_facecheck`; `source` step failure cascades; no tool path outside `tools/` except
`maker/srcprep.py`; zip notes name the source commands.

---

# Group C: UI exposure

### Task C1: page and panel

**Files:**
- Modify: `maker/static/maker.js` (`offeredRoutes` `:399-423`, the per-font row builder near `:881`, the steps table renderer, `OPTION_VISIBLE`), `maker/presets.py:63-90` (`panel_argv`), `maker/server.py:182-245` (`_changed_preview_fonts`, `_kept_settings`), `maker/test/test_server.py`, `maker/test/test_routes.py`

**Interfaces:**
- Consumes: entries' `prep`, `variable`, `strikes`, `dos_bytes`, `eng`; settings `instance`; step kind `source`.
- Produces:
  - `presets.panel_argv`: `"bdfface + from-svf fit"` joins the `--jset-version` labels; `"johab844"` emits nothing.
  - `OPTION_VISIBLE["bdfface + from-svf fit"] = {"1": ["jset_version"]}`.
  - `offeredRoutes(font)`: outline/bitmap face-index rule `(font.face_index || 0) > 0 && !(font.prep || []).length`; the `johab844` entry only when `font.dos_bytes === 11520` and `(font.dos || {}).candidates` includes `"844"`; `bdfface + from-svf fit` under the same `bdf.box` guard as `bdfface`.
  - Per-font row: `el("select", {"data-field": "instance"}, ...)` built only when `font.variable`: option `""` = "default instance", one option per `font.variable.instances` (value = JSON of its coords, label = its name); `onchange` sets `per.instance` to `null` or the parsed coords and `markDirty()`.
  - Steps table: a branch `if (step.kind === "source")` renders `"source"` in the kind column and empty size/bpp/name cells.
  - `server._changed_preview_fonts` keys add `"instance"`; `_kept_settings` keeps a font's `instance` when the re-detected entry still has `variable` and every tag is still an axis, else `None`.

- [ ] **Step 1: Write the failing tests**:

```python
# test_routes.py
def test_panel_argv_on_the_new_labels(self):
    every = {"mkfont": {}, "jamoset": {"jset_version": 2, "symbols": True, "embolden": True}}
    self.assertEqual(presets.panel_argv(every, "jamo", "bdfface + from-svf fit", 1), ["--jset-version", "2"])
    self.assertEqual(presets.panel_argv(every, "precomposed", "johab844", 1), [])

# test_server.py
def test_page_offers_the_instance_select_and_source_rows(self):
    with open(MAKER_JS, encoding="utf-8") as f:
        js = f.read()
    self.assertIn('el("select", {"data-field": "instance"', js)     # the row builder's exact call
    self.assertIn('step.kind === "source"', js)                     # the steps table's branch
    if shutil.which("node"):
        self.assertEqual(subprocess.run(["node", "--check", MAKER_JS]).returncode, 0)

def test_kept_settings_keeps_a_valid_instance(self):
    # server._kept_settings(old with f01 instance {"wght": 700}, fonts with the same VF entry, old fonts) keeps it;
    # with the re-detected entry lacking "variable" the kept value is None

def test_changed_preview_fonts_sees_an_instance_change(self):
    # server._changed_preview_fonts(fonts, before, after differing only in f01 instance) == ["f01"]
```

  `test_page_js_tables_match_python` (existing) covers the `OPTION_VISIBLE` change.

- [ ] **Step 2: Run** `python3 -m unittest discover -s maker/test -p 'test_server.py' -k "instance or panel_argv or source_rows"` and `test_routes.py -k new_labels`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite through `heavy`. Expected: `OK`. Then by hand: `SVF_MAKER_REPO=$PWD SVF_MAKER_DATA=$(mktemp -d) SVF_MAKER_BIND=127.0.0.1:18766 python3 -P maker/server.py`, upload `inputfx.variable_ttf()` + a licence, see the instance select with Regular/Bold and a `source` row after run (record what was seen in the commit body; this is the only manual step).
- [ ] **Step 5: Commit** `git commit -m "maker: page exposes the new routes, the instance choice and source steps (t_f3ef3189)"`.

**Group C review gate.** Reviewer checks the page against the mirror tables and that no preview code changed
(t_9acea7ab owns it).

---

## Closing measurement (card t_f3ef3189)

- Each added kind has a synthetic-fixture test in `maker/test`: TTC face N (B1), VF instance (B2), Mac cmap TTF (B1),
  dfont/resource fork, AppleDouble, MacBinary (B1), KSC PCF and johab PCF (B3), `johab844` (B5), ASCII.PFT and HBIOS
  12x24 `--eng` (B6), KS X 1001 `--from-svf` jamo (B4), strike listing (A3, B1).
- `python3 -m unittest discover -s maker/test -p 'test_*.py'` green (431 + new).
- Detect picks the recipe: every end-to-end test asserts `inputkinds.step_tools(job["steps"])`.
- The output zip passes `facecheck.py`: every end-to-end test calls `inputkinds.assert_facecheck`.

## Open points for the user

1. "Passes facecheck.py": `facecheck.py` has no zip mode; the plan's check is manifest + verify over the extracted
   zip committed to a temp git repo, plus a v3 parse of every face. Confirm, or name the check you meant.
2. TTC-face save and PCF -> BDF are new code placed in `maker/srcprep.py` to keep `tools/` untouched. If they should be
   tools of their own (recipes.md would then cite them instead of the `python3 -c` one-liner and external `pcf2bdf`),
   say so and A1/A2 move them to `tools/`.
3. One instance per font per job: a second instance of the same VF needs a second job (or a later multi-instance
   setting). The suggested face name does not include the instance style; the owner edits it.
4. HBIOS 12x24 English vs Dokkaebi 15,360-byte files are told apart by a margin heuristic with no override; a
   misjudged file needs a re-upload under another size (no UI to force the kind).
