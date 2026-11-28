---
name: svf-fonts-recipes
description: Use when a font of some format must become an SVF face and you need the recipe document and section for that source.
---

# Which recipe for which source

A router from "what do I hold" to the one recipe document and section that carries the commands, the measured results
and the checks. Commands stay in the documents: read the section, then run it. The index
[`docs/recipes.md`](../../docs/recipes.md) holds the quick-start table this skill mirrors, the shared checks and the
KS X 1001 and encoding reference.

## When to use

- You have a font file (or a ROM, a disk image, a program) and must make an SVF face from it.
- You know the face kind you want but not the route for this source.
- A recipe command and the current tools disagree: find which side is stale, fix it, and say which in the commit.
- No row matches the source: start from [A font inside a program, driver or data file](../../docs/recipes/programs-and-drivers.md#finding-a-font-inside-a-program-or-data-file-with-claude)
  and record the route you find as a document change.

## Two decisions first

1. **Precomposed or jamo set.** A jamo set is about a sixth of the size and composes from pieces; the precomposed face
   is exact per syllable. See [Quick start: by input kind](../../docs/recipes.md#quick-start-by-input-kind) and
   [Choosing the number of sets (벌 수)](../../docs/recipes/sets.md#choosing-the-number-of-sets).
2. **Which source row.** Find the file below; the row names the document and section.

## Outline and bitmap sources

| You hold | Read |
|---|---|
| TTF or OTF with a Unicode cmap | [Outline fonts](../../docs/recipes/outline-fonts.md#outline-fonts); precomposed in [Precomposed faces (`mkfont.py`)](../../docs/recipes/outline-fonts.md#precomposed-faces-mkfontpy), jamo set in [Jamo sets from TrueType and OpenType fonts](../../docs/recipes/outline-fonts.md#jamo-sets-from-truetype-and-opentype-fonts) |
| TTC or OTC | [TTC and OTC](../../docs/recipes/outline-fonts.md#ttc-and-otc) |
| Variable font | [Variable fonts](../../docs/recipes/outline-fonts.md#variable-fonts) |
| Mac TrueType (`.dfont`, suitcase, Korean-only cmap) | [Mac-format TrueType](../../docs/recipes/outline-fonts.md#mac-format-truetype) |
| Outline font with embedded strikes (`EBDT`, `bdat`) | [Embedded bitmap strikes](../../docs/recipes/bitmap-fonts.md#embedded-bitmap-strikes) |
| TTF that already carries jamo (composites, PUA pieces, GSUB) | [TrueType fonts that already carry jamo](../../docs/recipes/outline-fonts.md#truetype-fonts-that-already-carry-jamo) |
| 2 bpp anti-aliased face wanted | [2 bpp anti-aliased faces from a TrueType/OpenType font](../../docs/recipes/outline-fonts.md#2-bpp-anti-aliased-faces-from-a-truetypeopentype-font) |
| Baseline, vertical shift or clipping questions | [Baseline, vertical shift and clipping](../../docs/recipes/outline-fonts.md#baseline-vertical-shift-and-clipping) |
| BDF or PCF in Unicode (ISO 10646) | [ISO 10646 BDF and PCF](../../docs/recipes/bitmap-fonts.md#iso-10646-bdf-and-pcf) |
| BDF or PCF in KS C 5601 / KS X 1001 | [KS C 5601 BDF and PCF](../../docs/recipes/bitmap-fonts.md#ks-c-5601-bdf-and-pcf); family by family in [Korean fonts from X Window and Unix](../../docs/recipes/x-window.md#korean-fonts-from-x-window-and-unix) |
| hanterm johab BDF | [hanterm johab fonts](../../docs/recipes/x-window.md#hanterm) |
| HBF | [HBF](../../docs/recipes/bitmap-fonts.md#hbf) |
| Windows `.FNT` / `.FON` | [Windows FNT and FON](../../docs/recipes/bitmap-fonts.md#windows-fnt-and-fon) |
| 24-48 px bitmap face wanted at 16 px or 2 bpp | [A low-resolution face from a high-resolution bitmap font](../../docs/recipes/bitmap-fonts.md#a-low-resolution-face-from-a-high-resolution-bitmap-font) |

## DOS-era, ROM and machine sources

| You hold | Read |
|---|---|
| DOS raw jamo-piece font (8x4x4, san, Dokkaebi, Kyra) | [DOS-era raw fonts](../../docs/recipes/dos-fonts.md#dos-era-raw-fonts) |
| IBM PC DOS 한글 HBIOS V3.0 fonts | [IBM PC DOS 한글 (HBIOS V3.0)](../../docs/recipes/dos-fonts.md#ibm-pc-dos-한글-hbios-v30) |
| HWP 1.x / 2.x `.SFT` / `.PFT` | [HWP 1.x and 2.x fonts](../../docs/recipes/dos-fonts.md#hwp-1x-and-2x-fonts) |
| HWP 3.0 `.FNT` | [HWP 3.0 FNT fonts](../../docs/recipes/dos-fonts.md#hwp-30-fnt-fonts) |
| KS X 1001 raw dump | [KS X 1001 raw dumps](../../docs/recipes/dos-fonts.md#ks-x-1001-raw-dumps) |
| A font inside a program, driver or data file | [Finding a font inside a program or data file, with Claude](../../docs/recipes/programs-and-drivers.md#finding-a-font-inside-a-program-or-data-file-with-claude); the brief in [The prompt](../../docs/recipes/programs-and-drivers.md#the-prompt) |
| Korean VGA font ROMs (86Box) | [Korean VGA font ROMs (86Box)](../../docs/recipes/rom-86box.md#korean-vga-font-roms-86box) |
| Korean MSX ROMs (MSX2, MSX1) | [Korean MSX fonts (MSX2 and MSX1)](../../docs/recipes/rom-msx.md#korean-msx-fonts-msx2-and-msx1); an agent-driven route in [With a coding agent (recommended)](../../docs/recipes/rom-msx.md#with-a-coding-agent-recommended) |
| ROMs in a MAME set | [Korean font ROMs in MAME sets](../../docs/recipes/rom-mame.md#korean-font-roms-in-mame-sets) |
| OS/2 System DBCS font (완성형) | [OS/2 Korean fonts (완성형)](../../docs/recipes/os2.md#os2-korean-fonts-완성형-to-a-precomposed-face-and-a-jamo-set) |
| Windows 3.1 / 95 `.TBM` font | [TBM fonts (Windows 3.1 and 95)](../../docs/recipes/windows.md#windows-tbm-fonts-31-and-95) |
| Windows 95 / XP `gulim.ttc`, `batang.ttc` strikes | [TrueType embedded strikes (Windows 95 and XP)](../../docs/recipes/windows.md#windows-truetype-embedded-strikes-95-and-xp) |
| Mac HangulTalk 1.0 `fbit` | [Classic Mac Korean bitmap fonts](../../docs/recipes/classic-mac.md#classic-mac-korean-bitmap-fonts) |
| Mac HangulTalk 7.1.x type-3 `fbit` | [HangulTalk 7.1.x type-3 `fbit` fonts](../../docs/recipes/classic-mac.md#classic-mac-hangultalk-71) |

## Existing faces and the repository's own faces

| You hold | Read |
|---|---|
| An SVF face to edit (dy, re-layout, re-bake as a jamo set) | [An existing SVF](../../docs/recipes/svf-and-ttf.md#an-existing-svf) |
| A face wanted back as TTF or BDF | [An SVF face back to a TTF bitmap font](../../docs/recipes/svf-and-ttf.md#an-svf-face-back-to-a-ttf-bitmap-font); shared pieces in [Composite glyphs (`--composite`)](../../docs/recipes/svf-and-ttf.md#composite-glyphs---composite) |
| A face to add to `svf/`, or to rebuild | [Faces of svf/](../../docs/recipes/svf-faces.md#faces-of-svf); [Adding a face to svf/](../../docs/recipes/svf-faces.md#adding-a-face-to-svf) |
| A maker route (GUI or desktop app) | [Desktop app and maker routes](../../docs/recipes/desktop-routes.md#desktop-app-and-maker-routes) |

## Jamo-set design

- Background, case by case, and what fits poorly: [`docs/jamo-split.md`](../../docs/jamo-split.md).
- A hands-on walkthrough with three OFL fonts, commands and measured output:
  [`docs/jamo-split-guide.md`](../../docs/jamo-split-guide.md).
- How many sets to use and what each costs: [Choosing the number of sets (벌 수)](../../docs/recipes/sets.md#choosing-the-number-of-sets).

## Rules

- Run commands from the repository root; the documents set an output directory first.
- Read a recipe's "Before you start" and its tables: the numbers are measured for the named inputs and settings.
- Every face ends with [Checking a face](../../docs/recipes.md#checking-a-face); a jamo set also with its builder's
  `--check` and the IoU line.
- Note a stale command in the card and fix the document in the same change; do not carry a private workaround.
