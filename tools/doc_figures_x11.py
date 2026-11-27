#!/usr/bin/env python3
"""The sample images of docs/recipes/x-window.md and docs/recipes/x-window.ko.md.

  python3 -I tools/doc_figures_x11.py --misc DIR [--baekmuk DIR] [--hanterm DIR] [--hanyang DIR] [--newmj FILE]
      [--iyagi FILE] [--philgi FILE] [--out DIR] [--check]

The fonts are not in the repository: give the folder or file of each family you have; an image is drawn for every face
whose files are there and the others are skipped. --misc is the X11 core fonts folder (/usr/share/fonts/X11/misc on a
Debian or Ubuntu host with xfonts-base): it holds the Daewoo fonts (hanglg16.pcf.gz, hanglm16.pcf.gz, hanglm24.pcf.gz)
and the ASCII fonts every face takes its Latin half from (Sony 8x16.pcf.gz and 12x24.pcf.gz, Misc Fixed 6x12.pcf.gz).
--baekmuk is the bdf folder of Baekmuk BDF 2.2, --hanterm the hanterm-font folder of hanterm-font-3.1 (its 8-4-4 and
10-6-6 folders), --hanyang the folder of hanyang-font-pcf; --newmj, --iyagi and --philgi name the KAIST
kaist-newmj16.bdf, ks_iyagi16.bdf and ks_philgi16.bdf. Each face is built in a temporary directory with the commands of
the recipe, run as subprocesses with `python3 -I` (the font files are read as data, nothing in them is run):

  KS C 5601 BDF / PCF:  srcprep.py pcf-bdf (a PCF, gzipped or not) for the Hangul font and the ASCII font, then
                        bdfface.py --symbols (the syllables, ASCII, and the KS X 1001 symbols of the sample)
  hanterm johab BDF:    mkfont.py on 8x16.pcf.gz for the ASCII face, then jamoset.py --layout hanterm-844 (8-4-4) or
                        --layout hanterm-johab (10-6-6) --base that face --check

Writes into DIR (default docs/images/recipes/x-window/), one PNG per face: four lines (two Korean pangrams, an English
line, ASCII symbols and the KS X 1001 symbols of SYMBOLS) drawn with svfline.py (placements, draw_gray8), black on
white like an xterm, every pixel doubled. A character the face does not have is left out of its line (the jamo sets
have no KS X 1001 symbols); the tool prints which. 8-bit grey PNG, no metadata, written by binscan.png_bytes.

--check draws in memory and compares with the files in DIR byte for byte (exit 1 on a difference or a missing file).
The images are a function of the font files alone (mkfont.py reads the ASCII PCF through Pillow's FreeType, whose
strike pixels are the file's).
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

LINES = ("다람쥐 헌 쳇바퀴에 타고파",
         "키스의 고유조건은 입술끼리 만나야 하고",
         "The quick brown fox jumps over 0123",
         "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~ ※☆★○●◎◇◆□■△▲→←↑↓")
SYMBOLS = "※☆★○●◎◇◆□■△▲→←↑↓"
SCALE = 2
PAD = 4          # paper around the text, in font pixels
GAP = 2          # rows between lines, in font pixels
INK, PAPER = 0, 255

# image: (option, file under it, kind, ASCII font of --misc, bdfface --cell, extra bdfface options)
FACES = (
    ("daewoo-gothic16.png", "misc", "hanglg16.pcf.gz", "ks", "8x16.pcf.gz", "16x16", ()),
    ("daewoo-mincho16.png", "misc", "hanglm16.pcf.gz", "ks", "8x16.pcf.gz", "16x16", ()),
    ("daewoo-mincho24.png", "misc", "hanglm24.pcf.gz", "ks", "12x24.pcf.gz", "24x24", ()),
    ("baekmuk-gulim16.png", "baekmuk", "gulim16.bdf", "ks", "8x16.pcf.gz", "16x16", ()),
    ("baekmuk-batang16.png", "baekmuk", "batang16.bdf", "ks", "8x16.pcf.gz", "16x16", ("--hangul-ascent", "13")),
    ("baekmuk-dotum16.png", "baekmuk", "dotum16.bdf", "ks", "8x16.pcf.gz", "16x16", ("--hangul-ascent", "13")),
    ("baekmuk-gulim12.png", "baekmuk", "gulim12.bdf", "ks", "6x12.pcf.gz", "12x12", ()),
    ("hanterm-dkbgoth.png", "hanterm", os.path.join("8-4-4", "dkbgoth.bdf"), "hanterm-844", "8x16.pcf.gz", None, ()),
    ("hanterm-johabm16.png", "hanterm", os.path.join("10-6-6", "johabm16.bdf"), "hanterm-johab", "8x16.pcf.gz", None,
     ()),
    ("hanyang-gothic16.png", "hanyang", "hgm16.pcf", "ks", "8x16.pcf.gz", "16x17",
     ("--ascent", "14", "--hangul-ascent", "15")),
    ("kaist-newmj16.png", "newmj", None, "ks", "8x16.pcf.gz", "16x16", ()),
    ("kaist-iyagi16.png", "iyagi", None, "ks", "8x16.pcf.gz", "16x16", ()),
    ("kaist-philgi16.png", "philgi", None, "ks", "8x16.pcf.gz", "16x16", ()),
)


def tool(*argv):
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, argv[0])] + [str(a) for a in argv[1:]],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"doc_figures_x11: {argv[0]} exit {r.returncode}\n{r.stdout}{r.stderr}")
    return r.stdout


def as_bdf(path, tmp, name):
    """A BDF of @p path: the file itself, or a PCF (gzipped or not) converted by srcprep.py pcf-bdf."""
    if path.endswith(".bdf"):
        return path
    out = os.path.join(tmp, name + ".bdf")
    subprocess.run([sys.executable, "-I", os.path.join(ROOT, "maker", "srcprep.py"), "pcf-bdf", path, out],
                   check=True, capture_output=True)
    return out


def ks_face(src, ascii_font, cell, extra, tmp):
    sample = os.path.join(tmp, "sample.txt")
    out = os.path.join(tmp, "face.svf")
    tool("bdfface.py", "--hangul", as_bdf(src, tmp, "hangul"), "--ascii", as_bdf(ascii_font, tmp, "ascii"),
         "--cell", cell, "--chars-from", sample, "--symbols", *extra, "-o", out)
    return out


def jamo_face(src, layout, ascii_font, tmp):
    base = os.path.join(tmp, "ascii.svf")
    tool("mkfont.py", ascii_font, base, "--size", 16, "--bpp", 1, "--unicode", "ascii")
    out = os.path.join(tmp, "jamo.svf")
    tool("jamoset.py", "--layout", layout, src, "--base", base, "--check", "-o", out)
    return out


def draw(face_path, lines):
    """The PNG bytes of @p lines on the face, black on white, x SCALE."""
    face = svfline.Face(open(face_path, "rb").read())
    line_h = face.cell_h
    widths = [svfline.measure([face_path], s.encode("utf-8"))[0] for s in lines]
    w = max(widths) + 2 * PAD
    h = len(lines) * line_h + (len(lines) - 1) * GAP + 2 * PAD
    places = []
    for i, s in enumerate(lines):
        places += svfline.placements([face], s.encode("utf-8"), PAD, PAD + i * (line_h + GAP) + face.ascent)
    gray = svfline.draw_gray8(places, w, h)
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            row += [INK if gray[y * w + x] >= 128 else PAPER] * SCALE
        rows += [row] * SCALE
    return binscan.png_bytes(rows, w * SCALE, h * SCALE)


def render(args):
    """{image file: PNG bytes} for every face whose source was given and is there."""
    out = {}
    for png, opt, name, kind, ascii_name, cell, extra in FACES:
        given = getattr(args, opt)
        if not given or not args.misc:
            continue
        src = os.path.join(given, name) if name else given
        ascii_font = os.path.join(args.misc, ascii_name)
        if not (os.path.isfile(src) and os.path.isfile(ascii_font)):
            print(f"{png}: skipped, {src if not os.path.isfile(src) else ascii_font} is not there")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "sample.txt"), "w", encoding="utf-8") as fh:
                fh.write("".join(LINES))
            face = (ks_face(src, ascii_font, cell, extra, tmp) if kind == "ks"
                    else jamo_face(src, kind, ascii_font, tmp))
            f = svfline.Face.load(face)
            missing = "".join(sorted(c for c in set("".join(LINES)) - {" "} if not f.has(ord(c))))
            lines = [("".join(c for c in s if c not in missing)).rstrip() for s in LINES]
            out[png] = draw(face, lines)
            print(f"{png}: {name or os.path.basename(src)}, {len(out[png])} bytes"
                  + (f", not in the face (left out): {missing}" if missing else ""))
    return out


def write_or_check(images, out, check):
    """Write {file: PNG bytes} into @p out, or with @p check compare them; returns the exit code (1 on a difference or a
    missing file)."""
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--misc", metavar="DIR", help="X11 core fonts folder (Daewoo fonts; the ASCII fonts of every face)")
    ap.add_argument("--baekmuk", metavar="DIR", help="Baekmuk BDF 2.2 bdf folder")
    ap.add_argument("--hanterm", metavar="DIR", help="hanterm-font-3.1 hanterm-font folder (8-4-4, 10-6-6)")
    ap.add_argument("--hanyang", metavar="DIR", help="hanyang-font-pcf folder")
    ap.add_argument("--newmj", metavar="FILE", help="kaist-newmj16.bdf")
    ap.add_argument("--iyagi", metavar="FILE", help="ks_iyagi16.bdf")
    ap.add_argument("--philgi", metavar="FILE", help="ks_philgi16.bdf")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "images", "recipes", "x-window"))
    ap.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing")
    args = ap.parse_args(argv)
    if not args.misc:
        ap.error("--misc is needed: every face takes its ASCII from the X11 core fonts")
    images = render(args)
    if not images:
        ap.error("no face could be drawn from the folders given")
    return write_or_check(images, args.out, args.check)


if __name__ == "__main__":
    sys.exit(main())
