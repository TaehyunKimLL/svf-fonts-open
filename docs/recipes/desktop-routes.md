**English** | [한국어](desktop-routes.ko.md)

# Recipes: Desktop app and maker routes

The maker's routes (desktop app and server): which route the maker offers for which kind of file, and the command line each route runs, so a result can be reproduced by hand.

**Before you start.** Commands run from the project root with `$OUT` set as in the [index](../recipes.md); every face ends with the checks of [Checking a face](../recipes.md#checking-a-face).

Up: [Recipes index](../recipes.md) · Related: [Maker desktop](../maker-desktop.md), [Desktop app](../desktop-app.md), [Maker server](../../maker/README.md).

<a id="desktop-app-and-maker-routes"></a>

## Desktop app and maker routes

For the UI workflow, see [Maker desktop](../maker-desktop.md); for render previews, see [Desktop app](../desktop-app.md).

The maker ([maker desktop](../maker-desktop.md), [desktop app](../desktop-app.md), [maker server](../../maker/README.md))
detects each file's kind (`maker/detect.py`) and offers the routes of `maker/routes.py` for it; every route is a command
line made of the tools of the recipe documents. A run writes `svf/<dest>/<NAME>.SVF` and `build-<id>/BUILD.md` in the output folder:
BUILD.md lists, for every face, the source steps and the commands that were run, with the real paths, so any result can
be reproduced by hand from this chapter. The routes, by the labels the page shows (`native` = the source is exactly
what the route makes; the others are fits and are marked experimental):

| Route (kind, label) | Source kind | Commands (argv of `routes.py`) | Recipe |
|---|---|---|---|
| precomposed, `mkfont` | outline, outline-composite, bitmap, bdf-iso10646 | `mkfont.py SRC mkfont.tmp --size S --bpp B --unicode R`, then `svf2to3.py mkfont.tmp OUT --profile default` (bitmaps: 1 bpp at their strike sizes) | [Precomposed faces](outline-fonts.md#precomposed-faces-mkfontpy), [ISO 10646 BDF and PCF](bitmap-fonts.md#iso-10646-bdf-and-pcf) |
| jamo, `composite` | outline-composite (a TrueType whose syllables are composites) | `jamovec.py master SRC -o M.json --components [--adaptive]`, then `jamovec.py render M.json --size S --bpp B --binarize threshold --check -o OUT` | [Jamo sets from TrueType and OpenType fonts, way 1: composite glyphs](outline-fonts.md#jamo-sets-from-truetype-and-opentype-fonts) |
| jamo, `experimental fit` | outline (not composite) | 1 bpp: `jamoset.py --layout L --from-ttf SRC --size S --binarize threshold --check -o OUT [--eng E] --mask-font none`; 2 bpp: `jamoset.py ... --bpp 2 --check -o OUT` | [Jamo sets from TrueType and OpenType fonts, way 3: fitting to the precomposed syllables](outline-fonts.md#jamo-sets-from-truetype-and-opentype-fonts) |
| jamo, `mask fit` | outline or outline-composite with GSUB jamo and a usable mask (1 bpp) | `jamoset.py --layout L --from-ttf SRC --size S --binarize threshold --mask-font SRC --no-clean --check -o OUT [--pylib DIR]` | [Jamo sets from TrueType and OpenType fonts, way 2: conjoining-jamo shaping](outline-fonts.md#jamo-sets-from-truetype-and-opentype-fonts) |
| jamo, `vector fit` | outline, outline-composite | `jamovec.py master SRC -o M.json [--adaptive]` (no `--components`), then the same `render` | [Jamo sets from TrueType and OpenType fonts, way 3: fitting to the precomposed syllables](outline-fonts.md#jamo-sets-from-truetype-and-opentype-fonts) (`jamovec.py master` without `--components`) |
| precomposed, `johab844` | dos-raw, exactly 11,520 bytes (16 px 8x4x4) | `johab844.py SRC svf/dos/NEODG16.SVF OUT [--eng E]` (the maker resolves the base under `svf/`) | [Other DOS-era Korean fonts](dos-fonts.md#other-dos-era-korean-fonts) |
| jamo, `dos raw` | dos-raw | `jamoset.py SRC --layout L --check -o OUT [--eng E] [--face 0\|1]` (`--face` for the Dokkaebi printer layouts) | [Other DOS-era Korean fonts](dos-fonts.md#other-dos-era-korean-fonts) |
| jamo, `hanterm` | bdf-johab | `jamoset.py SRC --layout hanterm-johab --check -o OUT [--eng E]` | [hanterm](x-window.md#hanterm) |
| precomposed, `bdfface` | bdf-ksc5601 (a BDF, or a PCF through the `pcf-bdf` step) | `bdfface.py --hangul SRC --ascii LATIN --cell WxH --chars-from LIST -o OUT` (`WxH` = the BDF's box) | [KS C 5601 BDF and PCF](bitmap-fonts.md#ks-c-5601-bdf-and-pcf) |
| jamo, `bdfface + from-svf fit` | bdf-ksc5601 | the `bdfface.py` face, then `jamoset.py --layout L --from-svf precomposed.svf --check -o OUT` | [KS C 5601 BDF and PCF](bitmap-fonts.md#ks-c-5601-bdf-and-pcf) |
| jamo, `mac fbit 1.0` | mac-fbit1 | `jamoset.py --layout mac-fbit-45sets SRC --check -o OUT` | [Classic Mac Korean bitmap fonts](classic-mac.md#classic-mac-korean-bitmap-fonts) |
| jamo, `hwp1` | hwp1 (an HWP 1.x `HANGUL.SFT` / `HANGUL*.PFT` face; local mode) | `jamoset.py SRC --layout hwp1 --face N --check -o OUT [--eng E]` | [HWP 1.x and 2.x fonts](dos-fonts.md#hwp-1x-and-2x-fonts) |
| precomposed, `hwp bdf + mkfont` | hwp1, ks-raw (an HWP 3.0 Hangul FNT, local mode; a headerless KS X 1001 dump) | `hwpfont.py bdf SRC [--face N] [--syllables all] [--ascii E] -o hwp.bdf`, `mkfont.py hwp.bdf mkfont.tmp --size S --bpp 1 --unicode R`, `svf2to3.py mkfont.tmp OUT --profile default` (without `E` the range drops `ascii`) | [HWP 1.x and 2.x fonts](dos-fonts.md#hwp-1x-and-2x-fonts), [KS X 1001 raw dumps](dos-fonts.md#ks-x-1001-raw-dumps) |
| jamo, `hwp3 844` | ks-raw with an 8x4x4 set (an HWP 3.0 `HAN16_*.FNT`) | `jamoset.py SRC --layout 844-hwp3 --check -o OUT [--eng E]` | [HWP 3.0 FNT fonts](dos-fonts.md#hwp-30-fnt-fonts) |
| jamo, `hwp bdf + from-svf fit` | ks-raw | the `hwp bdf + mkfont` face as `precomposed.svf`, then `jamoset.py --layout L --from-svf precomposed.svf --check -o OUT` | [KS X 1001 raw dumps](dos-fonts.md#ks-x-1001-raw-dumps) |
| jamo, `mac fbit 7.1 direct` / `derived` | mac-fbit3 + HTBL 1 | `macfbit_svf.py build FBIT HTBL -o OUT --mode direct\|derived [--latin SUITCASE]` | [HangulTalk 7.1.x type-3 `fbit` fonts](classic-mac.md#classic-mac-hangultalk-71) |
| precomposed, `mac fbit 7.1 bdf + mkfont` | mac-fbit3 + HTBL 1 | `macfbit3.py bdf FBIT HTBL NAME mac.bdf`, `srcprep.py bdf-pixel-size mac.bdf mac-sized.bdf --size S`, `mkfont.py mac-sized.bdf mkfont.tmp --size S --bpp 1 --unicode ...`, `svf2to3.py ... --profile default` | [HangulTalk 7.1.x type-3 `fbit` fonts](classic-mac.md#classic-mac-hangultalk-71) |
| precomposed or jamo, `copy` | svf-precomposed, svf-jamo | none when used as uploaded; `svf2to3.py SRC OUT --jset-version V --check` for a v2 face or a requested JSET change | [An existing SVF](svf-and-ttf.md#an-existing-svf) |
| precomposed or jamo, `svf2ttf` | svf-precomposed, svf-jamo | the face as `copy` reads it, written only as its exports (below): no SVF | [An SVF face back to a TTF bitmap font](svf-and-ttf.md#an-svf-face-back-to-a-ttf-bitmap-font) |
| precomposed, `bdfface`; jamo, `bdfface + from-svf fit` | recipe (a known ROM set of `maker/recipes/`, local mode) | `rawcarve.py bdf` of the recipe's Hangul and English items, `bdfface.py --hangul H --ascii A --cell WxH --chars-from LIST -o OUT`; the fit makes that face as `precomposed.svf`, then `jamoset.py --layout L --from-svf precomposed.svf --mask-font none [--eng E] --check -o OUT`; before them `rawcarve.py region --group ...` of a set's files (each path whole: a comma in a folder name stays), and `rawcarve.py compose` for a composed item or `ink` + `eng` for an English font in tiles | [Korean VGA font ROMs (86Box)](rom-86box.md#korean-vga-font-roms-86box), [Korean font ROMs in MAME sets](rom-mame.md#korean-font-roms-in-mame-sets) |
| jamo, `spec` | recipe (SPC-1500) | `rawcarve.py region ...`, `rawcarve.py eng REGION ...`, `jamoset.py --layout spec --spec spc1500 REGION --eng E --check -o OUT` | [Samsung SPC-1500](rom-mame.md#samsung-spc-1500-a-jamo-set-in-four-inverted-roms-exact) |
| jamo, `dos raw` | recipe (a raw set in a ROM: X Se Dae Quiz) | `rawcarve.py region`, `ink`, `cut` (the raw font), `ink` + `eng` (the English font), `jamoset.py RAW --layout L --eng E --check -o OUT` | [X Se Dae Quiz](rom-mame.md#x-se-dae-quiz-taebaek-gothic16-in-the-sprites-a-cross-check) |
| jamo, `from-svf fit` | svf-precomposed, 1 bpp | `[svf2to3.py ... source-v3.svf]`, then `jamoset.py --layout L --from-svf SRC --check -o OUT [--eng E]` | [An existing SVF](svf-and-ttf.md#an-existing-svf) |

`L` is `844` or `adaptive` for the fits and the layout the source kind names otherwise; `[--eng E]` is the English
companion the page paired with the font.

With "also write TTF / BDF" (`options.export`) every face step is followed by one `export` step a format:
`svf2ttf.py ttf|bdf FACE OUT [--licence FILE]`, `OUT` the face's name with `.ttf` / `.bdf`, written beside the face;
`FILE` is the licence the job knows for the font (none: svf2ttf.py says the source font's licence applies); "TTF as
composites" adds `--composite` to a jamo set's TTF.

Some sources need a conversion first; BUILD.md lists these steps before the route's commands (each reads the file the
step before it wrote):

| Step | Command |
|---|---|
| `rsrc-sfnt` | `macsfnt.py extract SRC OUT --id N` |
| `mac-cmap` | `macsfnt.py unicode SRC OUT` |
| `ttc-face` | `srcprep.py ttc-face SRC OUT --index N` |
| `instance` | `python3 -m fontTools.varLib.instancer SRC AXIS=VALUE ... -o OUT` |
| `pcf-bdf` | `srcprep.py pcf-bdf SRC OUT` |
| `mac-fork`, `mac-fork-named` (macOS only), `mac-htbl` | `srcprep.py mac-fork SRC OUT` etc.: the resource fork of an AppleDouble / MacBinary file, the native fork, the HTBL 1 table |
| `mac-fbit3` | `macfbit3.py fbit SRC OUT` |

Verified: the route labels and kinds of this table were read from `routes.py` and checked by running `detect.scan` and
`routes.routes` on a folder of copies of fonts of this host: NanumGothic Bold, Caveat-VF and each of the ten faces of Noto Sans CJK Regular (index 0-9) are `outline` and get the route `mkfont` (Caveat, NanumGothic and each Noto CJK face also `experimental fit` and `vector fit`); neodgm.ttf is `outline-composite` with `mkfont`, `composite` (native) and `vector fit`; `wqy_12pt.bdf` (kind `bdf-iso10646`) and `18x18ko.pcf.gz` (`bitmap`, sizes [18]) get `mkfont` only; `hanglm16.pcf.gz` is `bdf-ksc5601` with `bdfface` and `bdfface + from-svf fit`; NEODG16.SVF (`svf-precomposed`) gets `copy` and `from-svf fit`, NEODG16A.SVF (`svf-jamo`) `copy`.

The same check on copies of the proprietary sources of the recipe documents (2026-11-22; details in each recipe): raw DOS fonts
are `dos-raw` with `dos raw` (11,520-byte ones also `johab844`); `johabm16.bdf` is `bdf-johab` with `hanterm`; `batang24.bdf`
is `bdf-ksc5601` with `bdfface` and `bdfface + from-svf fit`; Gulim and Mac Seoul with strikes are `outline-composite` / `outline`
with `mkfont` (the bitmap-only Seoul `bitmap`, `mkfont` only); Windows FONs labelled with no route ("no Unicode character map, mkfont cannot read it");
the HWP 1.x, HWP 3.0 and KS X 1001 dump files as in their recipes (2026-11-23: `hwp1` three entries a Hangul file with `hwp1` and `hwp bdf + mkfont`, `ks-raw` with `hwp bdf + mkfont`, `hwp3 844` for the 16 px HWP 3.0 FNTs, and the experimental `hwp bdf + from-svf fit`; a `.PFT` of no layout read here, such as Taebaek's `HANJA24.PFT`, `hwp-pft` "other"); the Mac fonts in local mode as above (the 1.0 fonts as `mac-fbit1` with `mac fbit 1.0`). The `mask fit` row appears for neodgm.ttf, Noto Sans CJK KR and Malgun Gothic once `mask_ok` is set (the server sets it
when `freetype-py` and `uharfbuzz` import).

[Recipes index](../recipes.md) · [Tool reference](../tools.md)
