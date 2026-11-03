#!/usr/bin/env python3
"""sdl_shots.py BMP DUMP --kind K --png OUT [--lines FILE]     one window shot against its dump
   sdl_shots.py compare A.png B.png                           differing pixels of two pictures
   sdl_shots.py overview DIR OUT.png                          the 2 x 5 labelled grid of DIR/sdl{2,3}-*.png

The first form is the check of shots.sh. BMP is what `svfsdl --present surface --shot` saved (the window's pixels), DUMP
the back buffer the same run wrote with --dump, K one of xrgb8888 argb8888 rgb565 rgb555 bgr24 index8 gray. The BMP is
converted to OUT (PNG), must be as large as the dump and have at least 1 % of its pixels off its background (its most
common colour), and is compared with the dump expanded the way SDL shows it: 32 and 24 bit exact; 16 bit `exact`
(v * 0x21 >> 2 for 5 bits, v * 0x41 >> 4 for 6), else `shl` (v << 3 / v << 2), else `tolerance` (within 1 of exact);
index8 and gray through the palette sdl_check.palette_for computes from the lines file (8 bit rgb: exact only). It prints
`sdl-shots: K WxH <rule> differs=<pixels off the exact expansion> maxdev=<largest channel difference from it> ink=<percent>`;
a rule other than exact is information, not a failure. `tolerance` is at most 1 level of the 8 bit result per channel
(what SDL2's own 5 / 6 bit expansion does, measured); anything further off, and every difference of an 8 bit kind, is a DIFF. Exit 0 ok, 1 a wrong size, a blank picture or a pixel no rule explains (`DIFF`), 2 an input that cannot be
used (a bad option, an unreadable BMP, dump or lines file, a kind the dump contradicts).

sdl_check.py is the shared reference of the SDL port: read_bmp, read_dump, palette_for and parse are imported from it on
purpose (one BMP reader, one palette rule); do not replace them with local copies."""

import collections
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))   # python3 -I leaves the script's directory out
import sdl_check  # noqa: E402
from sdl_check import DumpError, read_bmp, read_dump, palette_for  # noqa: E402

KINDS = ("xrgb8888", "argb8888", "rgb565", "rgb555", "bgr24", "index8", "gray")
BPP = {"xrgb8888": (32,), "argb8888": (32,), "rgb565": (16,), "rgb555": (16,), "bgr24": (24,), "index8": (8,),
       "gray": (1, 2, 4, 8)}
# (name, 5-bit, 6-bit, tolerance 5-bit, tolerance 6-bit) of the 16-bit expansions
EXACT = {5: lambda v: v * 0x21 >> 2, 6: lambda v: v * 0x41 >> 4}
SHL = {5: lambda v: v << 3, 6: lambda v: v << 2}
TOLERANCE = 1   # levels of the 8 bit result: SDL2's 565 -> 888 table is at most one off the exact expansion (measured)


def _pixels(d, kind, table):
    """The expansion of dump @p d as [(r, g, b)] per pixel; for the 16 bit kinds the raw (r, g, b) channel values and
    their bit widths instead: ((values), (rbits, gbits, bbits))."""
    pal = palette_for(table, kind, d.bpp) if kind in ("index8", "gray") else None
    out = []
    for y in range(d.h):
        row = d.data[y * d.pitch:(y + 1) * d.pitch]
        for x in range(d.w):
            if kind in ("xrgb8888", "argb8888"):
                out.append((row[4 * x + 2], row[4 * x + 1], row[4 * x]))
            elif kind == "bgr24":
                out.append((row[3 * x + 2], row[3 * x + 1], row[3 * x]))
            elif kind in ("rgb565", "rgb555"):
                v = (row[2 * x] << 8 | row[2 * x + 1]) if d.big_endian else (row[2 * x] | row[2 * x + 1] << 8)
                out.append((v >> 11, v >> 5 & 63, v & 31) if kind == "rgb565" else (v >> 10 & 31, v >> 5 & 31, v & 31))
            elif d.bpp == 8:
                out.append(pal[row[x]])
            else:
                bit = x * d.bpp
                sh = bit % 8 if d.lsb_first else 8 - d.bpp - bit % 8
                out.append(pal[row[bit // 8] >> sh & (1 << d.bpp) - 1])
    return out


def _judge(shot, raw, kind):
    """(rule, pixels off the exact expansion, largest channel deviation from it, first bad (index, got, want) or None)."""
    if kind not in ("rgb565", "rgb555"):
        bad = [i for i, (a, b) in enumerate(zip(shot, raw)) if a != b]
        return "exact", len(bad), 0, (bad[0], shot[bad[0]], raw[bad[0]]) if bad else None
    bits = (5, 6, 5) if kind == "rgb565" else (5, 5, 5)
    want = [tuple(EXACT[b](v) for v, b in zip(p, bits)) for p in raw]
    off = sum(1 for a, b in zip(shot, want) if a != b)
    if off == 0:
        return "exact", 0, 0, None
    dev = max(abs(c - e) for a, b in zip(shot, want) for c, e in zip(a, b))
    if all(a == tuple(SHL[b](v) for v, b in zip(p, bits)) for a, p in zip(shot, raw)):
        return "shl", off, dev, None
    if dev > TOLERANCE:
        for i, (a, b) in enumerate(zip(shot, want)):
            if any(abs(c - e) > TOLERANCE for c, e in zip(a, b)):
                return "none", off, dev, (i, a, b)
    return "tolerance", off, dev, None


def check(bmp, dump, kind, lines, png):
    """(exit code, message line)."""
    from PIL import Image
    if kind not in KINDS:
        return 2, "unknown kind %r" % kind
    try:
        d = read_dump(dump)
        w, h, rows = read_bmp(bmp)
        table = sdl_check.parse(lines)
    except (DumpError, sdl_check.vesa_lines.VesaLinesError) as e:
        return 2, str(e)
    if d.bpp not in BPP[kind]:
        return 2, "%s: header says %d bits per pixel, %s has %s" % (dump, d.bpp, kind, "/".join(map(str, BPP[kind])))
    if (w, h) != (d.w, d.h):
        return 1, "DIFF %s shot is %dx%d, the dump %dx%d" % (kind, w, h, d.w, d.h)
    shot = [p for r in rows for p in r]
    im = Image.new("RGB", (w, h))
    im.putdata(shot)
    try:
        im.save(png)
    except OSError as e:
        return 2, "cannot write %s: %s" % (png, e.strerror)
    bgc, n_bg = collections.Counter(shot).most_common(1)[0]
    ink = 100.0 * (len(shot) - n_bg) / len(shot)
    if ink < 1.0:
        tb = table.colours[table.background].rgb888
        note = "" if bgc == (tb >> 16 & 255, tb >> 8 & 255, tb & 255) or kind in ("rgb565", "rgb555") else (
            "; the picture is uniformly #%02X%02X%02X, not the table's background #%06X (a wrong colour)" % (*bgc, tb))
        return 1, "DIFF %s blank picture: %.2f %% of the pixels off the dominant colour #%02X%02X%02X%s" % (
            kind, ink, *bgc, note)
    rule, off, dev, first = _judge(shot, _pixels(d, kind, table), kind)
    if rule == "none":
        i, got, want = first
        return 1, "DIFF %s pixel (%d,%d) got #%02X%02X%02X want #%02X%02X%02X, no expansion rule explains it" % (
            kind, i % w, i // w, *got, *want)
    if first:
        i, got, want = first
        return 1, "DIFF %s pixel (%d,%d) got #%02X%02X%02X want #%02X%02X%02X (%d differ)" % (
            kind, i % w, i // w, *got, *want, off)
    return 0, "%s %dx%d %s differs=%d maxdev=%d ink=%.1f%% sdl%d" % (kind, w, h, rule, off, dev, ink, d.sdl_major)


def differing_pixels(a, b):
    """The number of pixels two same-sized pictures differ in (a different size: every pixel of the larger)."""
    from PIL import Image
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if ia.size != ib.size:
        return max(ia.size[0] * ia.size[1], ib.size[0] * ib.size[1])
    return sum(1 for p, q in zip(ia.getdata(), ib.getdata()) if p != q)


NAMES = ("xrgb8888", "argb8888", "rgb565", "index8", "gray4")


def overview(shots_dir, out):
    """The 2 x 5 grid of shots_dir/sdl{2,3}-{xrgb8888,argb8888,rgb565,index8,gray4}.png, labelled, at half size."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.load_default(size=14)
    except TypeError:
        font = ImageFont.load_default()
    ims = [[Image.open(os.path.join(shots_dir, "sdl%d-%s.png" % (s, n))).convert("RGB") for n in NAMES] for s in (2, 3)]
    cw, ch = ims[0][0].size
    cw, ch = cw // 2, ch // 2
    pad, lab = 8, 22
    sheet = Image.new("RGB", (pad + 5 * (cw + pad), pad + 2 * (lab + ch + pad)), (40, 40, 40))
    dr = ImageDraw.Draw(sheet)
    for r, s in enumerate((2, 3)):
        for c, n in enumerate(NAMES):
            x, y = pad + c * (cw + pad), pad + r * (lab + ch + pad)
            dr.text((x, y + 2), "SDL%d  %s" % (s, n), fill=(255, 255, 255), font=font)
            sheet.paste(ims[r][c].resize((cw, ch), Image.LANCZOS), (x, y + lab))
    sheet.save(out, optimize=True)


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    usage = "usage: sdl_shots.py BMP DUMP --kind K --png OUT [--lines FILE] | compare A B | overview DIR OUT"

    def bad(msg):
        print("sdl-shots: %s" % msg, file=sys.stderr)
        return 2

    try:
        if a[:1] == ["compare"] and len(a) == 3:
            n = differing_pixels(a[1], a[2])
            print("identical" if n == 0 else "%d pixels differ" % n)
            return 0
        if a[:1] == ["overview"] and len(a) == 3:
            overview(a[1], a[2])
            return 0
    except (OSError, ValueError) as e:
        return bad(str(getattr(e, "strerror", None) or e))
    opts = {"--kind": None, "--png": None, "--lines": os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                   "sdl-lines.txt")}
    pos = []
    i = 0
    while i < len(a):
        if a[i] in opts and i + 1 < len(a):
            opts[a[i]] = a[i + 1]
            i += 2
        elif a[i].startswith("--"):
            return bad("%s; %s" % (a[i], usage))
        else:
            pos.append(a[i])
            i += 1
    if len(pos) != 2 or not opts["--kind"] or not opts["--png"]:
        return bad(usage)
    rc, msg = check(pos[0], pos[1], opts["--kind"], opts["--lines"], opts["--png"])
    print("sdl-shots: " + msg, file=sys.stderr if rc == 2 else sys.stdout)
    return rc


if __name__ == "__main__":
    sys.exit(main())
