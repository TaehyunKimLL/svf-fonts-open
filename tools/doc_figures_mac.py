#!/usr/bin/env python3
"""The sample images of docs/recipes/classic-mac.md and docs/recipes/classic-mac.ko.md.

  python3 -I tools/doc_figures_mac.py [--ht10 DIR] [--ht712 DIR --htbl FILE] [--kh753 DIR] [--kh85 DIR]
      [--out DIR] [--check]

The fonts are Apple Korea / Elex Computer's and are not in the repository: give the folder of each system you have; an
image is drawn for every face whose files are there and the others are skipped. Resource forks are files of their own,
named as a Mac volume extractor writes them (`Name.rsrc`, `Name[TYPE].rsrc`, `Name[TYPE].data`):

  --ht10 DIR    the System Folder of the HangulTalk 1.0 System Disk (Korean System 4.1, 1988): Gotic12.rsrc and
                Munjo24.rsrc, the fonts' resource forks
  --ht712 DIR   the More Additions font folder of the HangulTalk 7.1.2 CD (1994): Seoul12[splt].data,
                AppleGothic12[splt].data, AppleMyungjo24[splt].data and the family suitcases Seoul[FFIL].rsrc,
                AppleGothic[FFIL].rsrc, AppleMyungjo[FFIL].rsrc (their NFNT strikes give the Latin letters)
  --htbl FILE   InputBackSupport[INIT].rsrc of the same 7.1.2 CD (the HTBL 1 composition table); needed by --ht712
  --kh753 DIR   the "Bitmap 서체 설치" (bitmap font install) folder of the Korean System 7.5.3 CD (1996):
                NAME/NAME[FFIL].rsrc for AppleGothic, AppleMyungjo, Seoul, #신명조 and #궁서체, bitmap-only TrueType
                ('bloc'/'bdat' strikes, no outlines)
  --kh85 DIR    the font folder (자형 폴더) of the Mac OS 8.5 Korean CD (1998): 한강체[FFIL].rsrc (Hangang, outlines and
                'bloc'/'bdat' strikes)

Each face is built in a temporary directory with the commands of the recipes, run as subprocesses with `python3 -I`
(the font files are read as data, nothing in them is run):

  HangulTalk 1.0 'fbit':    jamoset.py --layout mac-fbit-45sets FORK --check (without --symbols: its U+2026 and U+25A1
                            are drawn by jamoset, not by the font). The fonts hold Hangul only: their images have the
                            two Korean lines.
  HangulTalk 7.1.2 'fbit':  srcprep.py mac-htbl, macfbit3.py unpack + fbit, macfbit_svf.py build --latin FFIL (direct)
                            and macfbit_svf.py verify
  'bloc'/'bdat' strikes:    macsfnt.py extract (+ macsfnt.py unicode when the font has only the Mac Korean cmap), then
                            mkfont.py FONT --size N --bpp 1 --unicode file:SAMPLE; N must be one of the font's strikes
                            (read from its 'bloc' / 'EBLC' table here), so FreeType draws the strike's pixels

macsfnt.py unicode and mkfont.py need fontTools (mkfont.py takes a bitmap-only font's advances from it); `python3 -I`
hides a user-site install, so the tools are started with a short bootstrap (BOOT) that adds two folders to their path:
the tool's own folder and the user site-packages folder, which this script computes (site.getusersitepackages(); it
follows PYTHONUSERBASE and the home folder, so it comes from the caller's environment) and passes in as an argument.
It is appended last, and only when it is a folder; the working directory is never on the path.

Writes into DIR (default docs/images/recipes/mac/), one PNG per face: four lines (two Korean pangrams, an English line,
ASCII symbols and the KS X 1001 symbols of doc_figures_x11.SYMBOLS) drawn with svfline.py as doc_figures_x11 draws
them, black on white, every pixel doubled. A character the face does not have is left out of its line, and a line left
empty is dropped; the tool prints which. A face without U+0020 (the HangulTalk 1.0 jamo sets) advances half a cell at
a space (svfline's missing_advance), so the words stay apart; nothing is drawn there. One more image,
kh753-seoul-sizes.png, draws "<ppem> SIZE_LINE" once per strike of 7.5.3 Seoul (SIZES), each line on that strike's face.
8-bit grey PNG, no metadata, written by binscan.png_bytes.

--check draws in memory and compares with the files in DIR byte for byte (exit 1 on a difference or a missing file, and
when a face was skipped because its option was not given or its file is not there: it says which). The 'fbit' images
are a function of the font files alone; the strike images of the font, Pillow and the FreeType it links (printed).
"""

import argparse
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:  # python -I drops the script's directory
    sys.path.insert(0, HERE)
import binscan  # noqa: E402
import doc_figures_x11  # noqa: E402
import svfline  # noqa: E402

LINES = doc_figures_x11.LINES
SIZES = (9, 10, 12, 14, 16, 18, 20, 24)     # the strikes of the 7.5.3 fonts, one line each in the sizes image
SIZE_LINE = "다람쥐 헌 쳇바퀴에 타고파 ABC 123"
SCALE, PAD, GAP, INK, PAPER = (doc_figures_x11.SCALE, doc_figures_x11.PAD, doc_figures_x11.GAP, doc_figures_x11.INK,
                               doc_figures_x11.PAPER)

# image: (option, files under it, kind, pixel size)
#   fbit1: (fork,); fbit3: (splt archive, family suitcase); sfnt: (suitcase,)
FACES = (
    ("ht10-gotic12.png", "ht10", ("Gotic12.rsrc",), "fbit1", 12),
    ("ht10-munjo24.png", "ht10", ("Munjo24.rsrc",), "fbit1", 24),
    ("ht712-seoul12.png", "ht712", ("Seoul12[splt].data", "Seoul[FFIL].rsrc"), "fbit3", 12),
    ("ht712-applegothic12.png", "ht712", ("AppleGothic12[splt].data", "AppleGothic[FFIL].rsrc"), "fbit3", 12),
    ("ht712-applemyungjo24.png", "ht712", ("AppleMyungjo24[splt].data", "AppleMyungjo[FFIL].rsrc"), "fbit3", 24),
    ("kh753-applegothic12.png", "kh753", (os.path.join("AppleGothic", "AppleGothic[FFIL].rsrc"),), "sfnt", 12),
    ("kh753-applegothic16.png", "kh753", (os.path.join("AppleGothic", "AppleGothic[FFIL].rsrc"),), "sfnt", 16),
    ("kh753-applemyungjo16.png", "kh753", (os.path.join("AppleMyungjo", "AppleMyungjo[FFIL].rsrc"),), "sfnt", 16),
    ("kh753-applemyungjo24.png", "kh753", (os.path.join("AppleMyungjo", "AppleMyungjo[FFIL].rsrc"),), "sfnt", 24),
    ("kh753-seoul12.png", "kh753", (os.path.join("Seoul", "Seoul[FFIL].rsrc"),), "sfnt", 12),
    ("kh753-seoul16.png", "kh753", (os.path.join("Seoul", "Seoul[FFIL].rsrc"),), "sfnt", 16),
    ("kh753-shinmyungjo16.png", "kh753", (os.path.join("#신명조", "#신명조[FFIL].rsrc"),), "sfnt", 16),
    ("kh753-gungseo16.png", "kh753", (os.path.join("#궁서체", "#궁서체[FFIL].rsrc"),), "sfnt", 16),
    ("kh85-hangang16.png", "kh85", ("한강체[FFIL].rsrc",), "sfnt", 16),
    ("kh753-seoul-sizes.png", "kh753", (os.path.join("Seoul", "Seoul[FFIL].rsrc"),), "sizes", SIZES),
)

# Started as `python3 -I -c BOOT USERSITE TOOL ARGS...`: -I keeps the working directory and PYTHONPATH out of the
# path; the tool's own folder goes first, USERSITE (fontTools may be installed there; "" for none) last when it is a
# folder.
BOOT = ("import os, runpy, sys; u, t = sys.argv[1], sys.argv[2]; sys.argv = sys.argv[2:]; "
        "sys.path.insert(0, os.path.dirname(t)); "
        "u and os.path.isdir(u) and u not in sys.path and sys.path.append(u); "
        "runpy.run_path(t, run_name='__main__')")


def user_site():
    """The user site-packages folder as this Python reports it (from PYTHONUSERBASE or the home folder), or ""."""
    import site
    u = site.getusersitepackages()
    return u if isinstance(u, str) else ""


def tool(script, *args):
    r = subprocess.run([sys.executable, "-I", "-c", BOOT, user_site(), os.path.join(ROOT, script)]
                       + [str(a) for a in args],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"doc_figures_mac: {script} exit {r.returncode}\n{r.stdout}{r.stderr}")
    return r.stdout


def sfnt_strikes(path):
    """Sorted ppemY of the 'bloc' (else 'EBLC') strikes of the sfnt file @p path; [] when it has none. Bounds-checked:
    a table that does not fit the file reads as none."""
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 12:
        return []
    n = struct.unpack_from(">H", data, 4)[0]
    if 12 + 16 * n > len(data):
        return []
    tables = {}
    for i in range(n):
        tag, _, off, ln = struct.unpack_from(">4sIII", data, 12 + 16 * i)
        if off + ln <= len(data):
            tables[tag] = data[off:off + ln]
    for tag in (b"bloc", b"EBLC"):
        raw = tables.get(tag)
        if raw is None:
            continue
        if len(raw) < 8:
            return []
        count = struct.unpack_from(">I", raw, 4)[0]
        if 8 + 48 * count > len(raw):
            return []
        return sorted({raw[8 + 48 * i + 45] for i in range(count)} - {0})
    return []


def fbit1_face(files, size, tmp, args):
    out = os.path.join(tmp, "face.svf")
    log = tool("tools/jamoset.py", "--layout", "mac-fbit-45sets", files[0], "--check", "-o", out)
    if "exact 11172" not in log:
        raise SystemExit(f"doc_figures_mac: jamoset.py --check did not compose all syllables\n{log}")
    return out


def fbit3_face(files, size, tmp, args):
    htbl = os.path.join(tmp, "HTBL1.bin")
    tool("maker/srcprep.py", "mac-htbl", args.htbl, htbl)
    fork = os.path.join(tmp, "font.rsrc")
    fbit = os.path.join(tmp, "font.fbit")
    out = os.path.join(tmp, "face.svf")
    tool("tools/macfbit3.py", "unpack", files[0], fork)
    tool("tools/macfbit3.py", "fbit", fork, fbit)
    tool("tools/macfbit_svf.py", "build", fbit, htbl, "--latin", files[1], "-o", out)
    v = tool("tools/macfbit_svf.py", "verify", out, fbit, htbl)
    if '"ks_bad": 0, "compat_bad": 0' not in v:
        raise SystemExit(f"doc_figures_mac: macfbit_svf.py verify: {v}")
    return out


def sfnt_face(files, size, tmp, args):
    font = os.path.join(tmp, "font.ttf")
    tool("tools/macsfnt.py", "extract", files[0], font)
    strikes = sfnt_strikes(font)
    if size not in strikes:
        raise SystemExit(f"doc_figures_mac: {files[0]}: no {size} px strike (strikes {strikes})")
    if not any(line.startswith("platform=3 encoding=1 ") or line.startswith("platform=0 ")
               for line in tool("tools/macsfnt.py", "cmap", font).splitlines()):
        uni = os.path.join(tmp, "fontU.ttf")
        tool("tools/macsfnt.py", "unicode", font, uni)
        font = uni
    out = os.path.join(tmp, "face.svf")
    tool("tools/mkfont.py", font, out, "--size", size, "--bpp", 1, "--unicode",
         "file:" + os.path.join(tmp, "sample.txt"))
    return out


BUILD = {"fbit1": fbit1_face, "fbit3": fbit3_face, "sfnt": sfnt_face}


def draw(face_path, lines, space=0):
    """The PNG bytes of @p lines on the face, black on white, x SCALE: doc_figures_x11.draw, with @p space the advance
    of a code point the face does not have (svfline's missing_advance; only U+0020 is left in the lines)."""
    face = svfline.Face.load(face_path)
    line_h = face.cell_h
    widths = [svfline.measure([face_path], s.encode("utf-8"), missing_advance=space)[0] for s in lines]
    w = max(widths) + 2 * PAD
    h = len(lines) * line_h + (len(lines) - 1) * GAP + 2 * PAD
    places = []
    for i, s in enumerate(lines):
        places += svfline.placements([face], s.encode("utf-8"), PAD, PAD + i * (line_h + GAP) + face.ascent,
                                     missing_advance=space)
    gray = svfline.draw_gray8(places, w, h)
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            row += [INK if gray[y * w + x] >= 128 else PAPER] * SCALE
        rows += [row] * SCALE
    return binscan.png_bytes(rows, w * SCALE, h * SCALE)


def draw_sizes(faces):
    """The PNG bytes of one line per (ppem, face path): "<ppem> SIZE_LINE" on that face, black on white, x SCALE."""
    lines = [(f"{ppem} {SIZE_LINE}".encode("utf-8"), svfline.Face.load(p), p) for ppem, p in faces]
    w = max(svfline.measure([p], t)[0] for t, _, p in lines) + 2 * PAD
    h = sum(f.cell_h for _, f, _ in lines) + (len(lines) - 1) * GAP + 2 * PAD
    places, top = [], PAD
    for t, f, _ in lines:
        places += svfline.placements([f], t, PAD, top + f.ascent)
        top += f.cell_h + GAP
    gray = svfline.draw_gray8(places, w, h)
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            row += [INK if gray[y * w + x] >= 128 else PAPER] * SCALE
        rows += [row] * SCALE
    return binscan.png_bytes(rows, w * SCALE, h * SCALE)


def render_sizes(png, files, sizes, args):
    """One strike face per size of @p sizes (the sfnt route), drawn by draw_sizes."""
    with tempfile.TemporaryDirectory() as root:
        faces = []
        for ppem in sizes:
            tmp = os.path.join(root, str(ppem))
            os.mkdir(tmp)
            with open(os.path.join(tmp, "sample.txt"), "w", encoding="utf-8") as fh:
                fh.write(f"0123456789 {SIZE_LINE}")
            faces.append((ppem, sfnt_face(files, ppem, tmp, args)))
        missing = sorted({c for ppem, p in faces for c in set(f"{ppem} {SIZE_LINE}") - {" "}
                          if not svfline.Face.load(p).has(ord(c))})
        if missing:
            raise SystemExit(f"doc_figures_mac: {png}: not in the face: {''.join(missing)}")
        data = draw_sizes(faces)
        print(f"{png}: {files[0].rsplit(os.sep, 1)[-1]}, strikes {', '.join(map(str, sizes))} px, "
              f"image {len(data)} bytes")
        return data


def render(args):
    """({image file: PNG bytes} for every face whose files are there, [image files skipped])."""
    out, skipped = {}, []
    for png, opt, names, kind, size in FACES:
        given = getattr(args, opt)
        if not given or (kind == "fbit3" and not args.htbl):
            print(f"{png}: skipped, --{opt if not given else 'htbl'} not given")
            skipped.append(png)
            continue
        files = [os.path.join(given, n) for n in names]
        absent = [f for f in files + ([args.htbl] if kind == "fbit3" else []) if not os.path.isfile(f)]
        if absent:
            print(f"{png}: skipped, {absent[0]} is not there")
            skipped.append(png)
            continue
        if kind == "sizes":
            out[png] = render_sizes(png, files, size, args)
            continue
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "sample.txt"), "w", encoding="utf-8") as fh:
                fh.write("".join(LINES))
            face = BUILD[kind](files, size, tmp, args)
            f = svfline.Face.load(face)
            missing = "".join(sorted(c for c in set("".join(LINES)) - {" "} if not f.has(ord(c))))
            lines = [s for s in (("".join(c for c in s if c not in missing)).strip() for s in LINES) if s]
            space = 0 if f.has(0x20) else f.cell_w // 2
            out[png] = draw(face, lines, space)
            w, a, d = svfline.measure([face], LINES[0].encode("utf-8"), missing_advance=space)
            print(f"{png}: {names[0]}, {size} px, cell {f.cell_w}x{f.cell_h}, face {os.path.getsize(face)} bytes, "
                  f"first line width={w} ascent={a} descent={d}, image {len(out[png])} bytes"
                  + (f", not in the face (left out): {missing}" if missing else "")
                  + (f"; no U+0020: a space advances {space} px" if space else ""))
    return out, skipped


def write_or_check(images, out, check, skipped=()):
    """Write {file: PNG bytes} into @p out, or with @p check compare them; returns the exit code (1 on a difference or a
    missing file, and with @p check also when a face was @p skipped)."""
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
        problems = []
        if bad:
            problems.append(f"{bad} image(s) differ or are missing")
        if skipped:
            problems.append(f"{len(skipped)} face(s) skipped, not checked: {', '.join(skipped)}")
        print(f"check: {len(images) - bad} of {len(FACES)} images equal" + ("; " + "; ".join(problems) if problems
                                                                             else "; ok"))
        return 1 if problems else 0
    if skipped:
        print(f"wrote {len(images)} of {len(FACES)} images; skipped: {', '.join(skipped)}")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ht10", metavar="DIR", help="HangulTalk 1.0 System Folder (Gotic12.rsrc, Munjo24.rsrc)")
    ap.add_argument("--ht712", metavar="DIR", help="HangulTalk 7.1.2 More Additions font folder ([splt], [FFIL])")
    ap.add_argument("--htbl", metavar="FILE", help="InputBackSupport[INIT].rsrc of the 7.1.2 CD")
    ap.add_argument("--kh753", metavar="DIR", help="7.5.3 CD 'Bitmap 서체 설치' folder")
    ap.add_argument("--kh85", metavar="DIR", help="Mac OS 8.5 Korean CD font folder (한강체[FFIL].rsrc)")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "images", "recipes", "mac"))
    ap.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing")
    args = ap.parse_args(argv)
    try:
        import PIL
        from PIL import features
        print(f"Pillow {PIL.__version__}, FreeType {features.version('freetype2')}")
    except ImportError:
        print("Pillow not found: the strike faces need it")
    images, skipped = render(args)
    if not images:
        ap.error("no face could be drawn from the folders given")
    return write_or_check(images, args.out, args.check, skipped)


if __name__ == "__main__":
    sys.exit(main())
