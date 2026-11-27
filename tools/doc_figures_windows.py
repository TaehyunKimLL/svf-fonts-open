#!/usr/bin/env python3
"""The sample images of docs/recipes/windows.md and docs/recipes/windows.ko.md.

  python3 -I tools/doc_figures_windows.py [--bt16 BT16.TBM] [--bt20 BT20.TBM] [--gulim16 GULIM16.TBM]
      [--gulim12 GULIM12.TBM] [--win95-gulim gulim.ttc] [--xp-gulim gulim.ttc] [--xp-batang batang.ttc]
      [--out DIR] [--check]

The fonts are Microsoft's and are not in the repository: give the path of each one you have; an image is drawn for
every font given and the others are skipped. Each face is built in a temporary directory with the commands of the
recipe, run as subprocesses with `python3 -I` (the font files are read as data, nothing in them is run):

  TBM (Windows 3.1 / 95):  tbmfont.py info (the block offsets), rawcarve.py bdf --invert (ASCII, the 2,350 syllables
                           --dense, the KS X 1001 symbols --chars map), bdfface.py (syllables + ASCII), and mkfont.py
                           on the symbol BDF for the sample's symbols (a second face, drawn first: bdfface.py puts
                           its own missing-glyph box at U+25A1, which is also one of the sample's symbols)
  TTC (Windows 95 / XP):   mkfont.py FONT --size N --bpp 1 --unicode file:SAMPLE (face 0 of the collection; at a
                           strike's size FreeType draws the strike's pixels)

Writes into DIR (default docs/images/recipes/windows/), one PNG per face: four lines (two Korean pangrams, an English
line, ASCII symbols and the KS X 1001 symbols of SYMBOLS) drawn with svfline.py (placements, draw_gray8), black on
white, every pixel doubled. 8-bit grey PNG, no metadata, written by binscan.png_bytes (zlib level 9).

--check draws in memory and compares with the files in DIR byte for byte (exit 1 on a difference or a missing file).
The TTC images are a function of the font, Pillow and the FreeType it links (printed); the TBM images of the font
alone. Needs Pillow for the TTC faces and the symbol faces.
"""

import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:  # python -I drops the script's directory
    sys.path.insert(0, HERE)
import binscan  # noqa: E402
import svfline  # noqa: E402
import tbmfont  # noqa: E402

LINES = ("다람쥐 헌 쳇바퀴에 타고파",
         "키스의 고유조건은 입술끼리 만나야 하고",
         "The quick brown fox jumps over 0123",
         "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~ ※☆★○●◎◇◆□■△▲→←↑↓")
SYMBOLS = "※☆★○●◎◇◆□■△▲→←↑↓"
SCALE = 2
PAD = 4          # paper around the text, in font pixels
GAP = 2          # rows between lines, in font pixels
INK, PAPER = 0, 255

# name: (option, kind, size, image file)
FACES = (
    ("bt16", "--bt16", "tbm", 16, "bt16.png"),
    ("bt20", "--bt20", "tbm", 20, "bt20.png"),
    ("gulim16", "--gulim16", "tbm", 16, "gulim16-tbm.png"),
    ("gulim12", "--gulim12", "tbm", 12, "gulim12-tbm.png"),
    ("win95_gulim16", "--win95-gulim", "ttc", 16, "win95-gulim16.png"),
    ("win95_gulim12", "--win95-gulim", "ttc", 12, "win95-gulim12.png"),
    ("xp_gulim12", "--xp-gulim", "ttc", 12, "xp-gulim12.png"),
    ("xp_batang16", "--xp-batang", "ttc", 16, "xp-batang16.png"),
)


def tool(*argv):
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, argv[0])] + [str(a) for a in argv[1:]],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"doc_figures_windows: {argv[0]} exit {r.returncode}\n{r.stdout}{r.stderr}")
    return r.stdout


def tbm_faces(path, size, tmp):
    """[main face, symbol face] built from a TBM file by the recipe's commands."""
    try:
        t = tbmfont.load(path)
    except tbmfont.TbmError as e:
        raise SystemExit(f"doc_figures_windows: {e}")
    b = tbmfont.blocks(t)
    if not b or (t["width"], t["height"]) != (size, size):
        raise SystemExit(f"doc_figures_windows: {path}: not a {size}x{size} TBM with the 128 + 8,366 glyph layout")
    half = f"{t['glyphs'][0][1]}x{t['glyphs'][0][2]}"
    full = f"{size}x{size}"
    sample = os.path.join(tmp, "sample.txt")
    syms = os.path.join(tmp, "symbols.txt")
    smap = os.path.join(tmp, "symbols.map")
    tool("tbmfont.py", "map", "--blocks", "symbols", "-o", smap)
    tool("rawcarve.py", "bdf", path, "--offset", b["ascii"][0], "--glyph", half, "--invert", "--chars", "ascii",
         "--count", 128, "-o", os.path.join(tmp, "ascii.bdf"))
    tool("rawcarve.py", "bdf", path, "--offset", b["hangul"][0], "--glyph", full, "--invert", "--chars", "ks-hangul",
         "--dense", "-o", os.path.join(tmp, "hangul.bdf"))
    tool("rawcarve.py", "bdf", path, "--offset", b["symbols"][0], "--glyph", full, "--invert", "--chars", "map",
         "--map", smap, "-o", os.path.join(tmp, "symbols.bdf"))
    main = os.path.join(tmp, "face.svf")
    sym = os.path.join(tmp, "symbols.svf")
    tool("bdfface.py", "--hangul", os.path.join(tmp, "hangul.bdf"), "--ascii", os.path.join(tmp, "ascii.bdf"),
         "--cell", full, "--chars-from", sample, "-o", main)
    tool("mkfont.py", os.path.join(tmp, "symbols.bdf"), sym, "--size", size, "--bpp", 1, "--unicode",
         "file:" + syms, "--only-listed")
    return [sym, main]  # the symbols first: bdfface.py draws its own U+25A1 (the missing-glyph box) into the main face


def ttc_faces(path, size, tmp):
    out = os.path.join(tmp, "face.svf")
    tool("mkfont.py", path, out, "--size", size, "--bpp", 1, "--unicode", "file:" + os.path.join(tmp, "sample.txt"))
    return [out]


def draw(chain_paths):
    """The PNG bytes of LINES on the faces, black on white, x SCALE."""
    chain = [svfline.Face(open(p, "rb").read()) for p in chain_paths]
    line_h = max(f.cell_h for f in chain)
    ascent = max(f.ascent for f in chain)
    widths = [svfline.measure(chain_paths, s.encode("utf-8"))[0] for s in LINES]
    w = max(widths) + 2 * PAD
    h = len(LINES) * line_h + (len(LINES) - 1) * GAP + 2 * PAD
    places = []
    for i, s in enumerate(LINES):
        places += svfline.placements(chain, s.encode("utf-8"), PAD, PAD + i * (line_h + GAP) + ascent)
    gray = svfline.draw_gray8(places, w, h)
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            row += [INK if gray[y * w + x] >= 128 else PAPER] * SCALE
        rows += [row] * SCALE
    return binscan.png_bytes(rows, w * SCALE, h * SCALE)


def render(args):
    """{image file: PNG bytes} for every face whose source was given."""
    out = {}
    for name, opt, kind, size, png in FACES:
        path = getattr(args, opt[2:].replace("-", "_"))
        if not path:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            text = "".join(LINES)
            with open(os.path.join(tmp, "sample.txt"), "w", encoding="utf-8") as fh:
                fh.write(text)
            with open(os.path.join(tmp, "symbols.txt"), "w", encoding="utf-8") as fh:
                fh.write(SYMBOLS)
            faces = (tbm_faces if kind == "tbm" else ttc_faces)(path, size, tmp)
            missing = [c for c in sorted(set(text) - {" "}) if not any(svfline.Face.load(p).has(ord(c)) for p in faces)]
            out[png] = draw(faces)
            print(f"{png}: {name}, {size} px, {len(out[png])} bytes"
                  + (f", not in the face: {''.join(missing)}" if missing else ""))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for opt in dict.fromkeys(f[1] for f in FACES):
        ap.add_argument(opt, metavar="FILE", help="the font file (read as data)")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "images", "recipes", "windows"))
    ap.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing")
    args = ap.parse_args(argv)
    try:
        import PIL
        from PIL import features
        print(f"Pillow {PIL.__version__}, FreeType {features.version('freetype2')}")
    except ImportError:
        print("Pillow not found: the TTC and symbol faces need it")
    images = render(args)
    if not images:
        ap.error("no font given")
    return write_or_check(images, args.out, args.check)


def write_or_check(images, out, check):
    """Write {file: PNG bytes} into @p out, or with @p check compare them; returns the exit code (1 on a difference or a
    missing file). Also used by tools/doc_figures_hbios.py."""
    bad = 0
    if not check:
        os.makedirs(out, exist_ok=True)
    for png, data in images.items():
        dest = os.path.join(out, png)
        if check:
            try:
                with open(dest, "rb") as fh:
                    same = fh.read() == data
            except OSError:
                same = False
            if not same:
                print(f"differs: {dest}")
                bad += 1
        else:
            with open(dest, "wb") as fh:
                fh.write(data)
    if check:
        print("check: " + ("ok" if not bad else f"{bad} image(s) differ or are missing"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
