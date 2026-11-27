#!/usr/bin/env python3
"""The sample images of the "IBM PC DOS 한글 (HBIOS V3.0)" section of docs/recipes/dos-fonts.md and .ko.md.

  python3 -I tools/doc_figures_hbios.py --disk DIR [--out DIR] [--check]

--disk is the folder holding the files of an IBM Korea HBIOS V3.0 disk under their own names ($KGOZN16.FNT,
$KMYZN16.FNT, $KMYZN24.FNT, $KSAHN16.FNT, $KROHN16.FNT, $KROHN24.FNT, $KSPHJ16.FNT, $KSPHJ24.FNT); no path is written
in the script, and an image is drawn only when its files are there. Each face is built in a temporary directory with
the commands of the recipe, run as subprocesses with `python3 -I` (the font files are read as data; HBIOS.EXE and the
drivers are never read or run):

  hbios-gothic16.png     jamoset.py --layout 844 $KGOZN16.FNT --eng $KSAHN16.FNT --symbols
  hbios-myeongjo16.png   jamoset.py --layout 844 $KMYZN16.FNT --eng $KROHN16.FNT --symbols
  hbios-myeongjo24.png   jamoset.py --layout 844-hbios24 $KMYZN24.FNT --eng $KROHN24.FNT --symbols
  hbios-myeongjo24-precomposed.png
                         the 2,350 precomposed syllables of the same file (rawcarve.py bdf --offset 32409 --stride 90
                         --chars ks-hangul --dense --ascent 22) with the ASCII of $KROHN24.FNT (rawcarve.py bdf
                         --offset 6 --stride 60 --ascent 22), baked by bdfface.py --cell 24x24

and the symbols of the sample from $KSPHJ16.FNT / $KSPHJ24.FNT (rawcarve.py bdf --chars map with the slot map of
`tbmfont.py map --blocks symbols`, then mkfont.py --only-listed), drawn ahead of the jamo set (whose --symbols box is
U+25A1, one of the sample's symbols).

The lines, the drawing (svfline.py, black on white, x2, 8-bit grey PNG without metadata) and --check are those of
tools/doc_figures_windows.py. Needs Pillow (mkfont.py, for the symbol faces).
"""

import argparse
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:  # python -I drops the script's directory
    sys.path.insert(0, HERE)
import doc_figures_windows as W  # noqa: E402

# image: (layout, jamo file, English file, symbol file, size, symbol offset, symbol stride); the symbols stand on
# ASCENT[size], the English baseline (the row under the ink of 'H') that jamoset.py also takes from --eng
FACES = (
    ("hbios-gothic16.png", "844", "$KGOZN16.FNT", "$KSAHN16.FNT", "$KSPHJ16.FNT", 16, 0, 32),
    ("hbios-myeongjo16.png", "844", "$KMYZN16.FNT", "$KROHN16.FNT", "$KSPHJ16.FNT", 16, 0, 32),
    ("hbios-myeongjo24.png", "844-hbios24", "$KMYZN24.FNT", "$KROHN24.FNT", "$KSPHJ24.FNT", 24, 9, 90),
)
PRE24_PNG = "hbios-myeongjo24-precomposed.png"
ASCENT = {16: 14, 24: 22}


def faces(disk, layout, jamo, eng, sym, size, soff, stride, tmp):
    """[symbol face, jamo set] by the recipe's commands."""
    smap = os.path.join(tmp, "symbols.map")
    syms = os.path.join(tmp, "symbols.txt")
    with open(syms, "w", encoding="utf-8") as fh:
        fh.write(W.SYMBOLS)
    W.tool("tbmfont.py", "map", "--blocks", "symbols", "-o", smap)
    W.tool("rawcarve.py", "bdf", os.path.join(disk, sym), "--offset", soff, "--glyph", f"{size}x{size}", "--stride",
           stride, "--chars", "map", "--map", smap, "--ascent", ASCENT[size], "-o", os.path.join(tmp, "symbols.bdf"))
    sface = os.path.join(tmp, "symbols.svf")
    W.tool("mkfont.py", os.path.join(tmp, "symbols.bdf"), sface, "--size", size, "--bpp", 1,
           "--unicode", "file:" + syms, "--only-listed")
    jface = os.path.join(tmp, "jamo.svf")
    W.tool("jamoset.py", "--layout", layout, os.path.join(disk, jamo), "--eng", os.path.join(disk, eng), "--symbols",
           "--check", "-o", jface)
    return [sface, jface]


def precomposed24(disk, tmp):
    """[symbol face, precomposed face] of the 2,350 syllables after the jamo half of $KMYZN24.FNT."""
    sface = faces(disk, "844-hbios24", "$KMYZN24.FNT", "$KROHN24.FNT", "$KSPHJ24.FNT", 24, 9, 90, tmp)[0]
    sample = os.path.join(tmp, "sample.txt")
    with open(sample, "w", encoding="utf-8") as fh:
        fh.write("".join(W.LINES))
    W.tool("rawcarve.py", "bdf", os.path.join(disk, "$KMYZN24.FNT"), "--offset", PRE24_OFFSET, "--glyph", "24x24",
           "--stride", 90, "--chars", "ks-hangul", "--dense", "--ascent", 22, "-o", os.path.join(tmp, "hangul.bdf"))
    W.tool("rawcarve.py", "bdf", os.path.join(disk, "$KROHN24.FNT"), "--offset", 6, "--glyph", "12x24", "--stride", 60,
           "--chars", "ascii", "--count", 128, "--ascent", 22, "-o", os.path.join(tmp, "ascii.bdf"))
    face = os.path.join(tmp, "pre.svf")
    W.tool("bdfface.py", "--hangul", os.path.join(tmp, "hangul.bdf"), "--ascii", os.path.join(tmp, "ascii.bdf"),
           "--cell", "24x24", "--chars-from", sample, "-o", face)
    return [sface, face]


PRE24_OFFSET = 360 * 90 + 3 * 3   # after the 360 jamo glyphs of 90 bytes, rows 3-26 of the 30-row cell


def render(disk):
    out = {}
    if all(os.path.isfile(os.path.join(disk, f)) for f in ("$KMYZN24.FNT", "$KROHN24.FNT", "$KSPHJ24.FNT")):
        with tempfile.TemporaryDirectory() as tmp:
            out[PRE24_PNG] = W.draw(precomposed24(disk, tmp))
        print(f"{PRE24_PNG}: the 2,350 syllables of $KMYZN24.FNT + $KROHN24.FNT + $KSPHJ24.FNT, 24 px, "
              f"{len(out[PRE24_PNG])} bytes")
    for png, layout, jamo, eng, sym, size, soff, stride in FACES:
        if not all(os.path.isfile(os.path.join(disk, f)) for f in (jamo, eng, sym)):
            print(f"{png}: skipped (needs {jamo}, {eng}, {sym})")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            out[png] = W.draw(faces(disk, layout, jamo, eng, sym, size, soff, stride, tmp))
        print(f"{png}: {jamo} + {eng} + {sym}, {size} px, {len(out[png])} bytes")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--disk", required=True, help="the folder with the HBIOS disk's font files (read as data)")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "images", "recipes", "dos"))
    ap.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing")
    args = ap.parse_args(argv)
    images = render(args.disk)
    if not images:
        ap.error("no face could be built from --disk")
    return W.write_or_check(images, args.out, args.check)


if __name__ == "__main__":
    sys.exit(main())
