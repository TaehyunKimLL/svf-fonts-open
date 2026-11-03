#!/usr/bin/env python3
"""vesa_check.py PNG DUMP.RAW W H BPP --dac 6|8 --palette-from vesa-lines.txt [--faces DIR] [--diff FILE]

The capture check of vesa-shots.sh. PNG is the DOSBox-X capture of a VBE mode, DUMP.RAW the back buffer svfvesa wrote.

1. With --faces DIR the dump is compared byte for byte with tools/vesa_lines.py's expected_buffer; on a difference the
   first differing pixel (x, y, kind) is printed and a diff image is written (--diff, default PNG + ".diff.png").
2. The PNG must be W x H and at least 1 % of its pixels must differ from the PNG's background (its most common colour).
3. The dump is converted to RGB (32 and 24 bpp exact; 16 and 15 bpp by v * 0x21 >> 2 for a 5-bit and v * 0x41 >> 4 for a
   6-bit channel; 8 bpp through the intended palette at the DAC width given by --dac) and compared with the PNG.
   One expansion rule must explain all three channels: the first of `exact`, `shl` (v << (8 - bits): the low bits
   zero) and `scale255` (v * 255 // (2**bits - 1)) that reproduces every pixel of every channel, printed as
   `rule=<name>`. A channel the pixels do not pin down (every rule fits it) follows the others. If a rule fits some
   channel but no rule fits all of them the check fails ("one rule"). Only when every channel fits no rule at all
   is a tolerance tried (a channel every rule fits does not count): every channel within +-8 (5-bit) or +-4 (6-bit)
   of `exact` (8-bit channels: none), printed
   as `tolerance=yes` and `rule=tolerance`.

Exit 0 when all hold, 1 when a check fails, 2 when an input cannot be used (a bad option or --dac, a missing,
truncated or wrong-size dump, a file that is not a PNG, an unreadable table): a message on stderr, never a traceback.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "tools"))
import vesa_lines  # noqa: E402
from PIL import Image  # noqa: E402

BYTES_PP = vesa_lines.BYTES_PP
KINDS = vesa_lines.KINDS


class CheckError(Exception):
    """A check failed (exit 1)."""


class InputError(Exception):
    """An input cannot be used (exit 2)."""


# rules: name -> {channel bits: function}; "exact" is the reference conversion
FAMILIES = {
    "exact": {5: lambda v: v * 0x21 >> 2, 6: lambda v: v * 0x41 >> 4, 8: lambda v: v},
    "shl": {5: lambda v: v << 3, 6: lambda v: v << 2, 8: lambda v: v},
    "scale255": {5: lambda v: v * 255 // 31, 6: lambda v: v * 255 // 63, 8: lambda v: v},
}
TOLERANCE = {5: 8, 6: 4, 8: 0}


def pixel_values(dump, w, h, bpp, pal):
    """([(r, g, b)] per pixel as the raw channel values, (rbits, gbits, bbits)). @p pal: [(b, g, r, 0)] for 8 bpp."""
    n = w * h
    if bpp == 32:
        return [(dump[i + 2], dump[i + 1], dump[i]) for i in range(0, 4 * n, 4)], (8, 8, 8)
    if bpp == 24:
        return [(dump[i + 2], dump[i + 1], dump[i]) for i in range(0, 3 * n, 3)], (8, 8, 8)
    if bpp == 16:
        words = [dump[i] | dump[i + 1] << 8 for i in range(0, 2 * n, 2)]
        return [(v >> 11, v >> 5 & 63, v & 31) for v in words], (5, 6, 5)
    if bpp == 15:
        words = [dump[i] | dump[i + 1] << 8 for i in range(0, 2 * n, 2)]
        return [(v >> 10 & 31, v >> 5 & 31, v & 31) for v in words], (5, 5, 5)
    return [(pal[i][2], pal[i][1], pal[i][0]) for i in dump[:n]], None  # 8 bpp: the caller knows the DAC width


def first_diff(a, b, w):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i % w, i // w
    return None


def write_diff(path, w, h, a, b):
    im = Image.new("RGB", (w, h), (0, 0, 0))
    px = im.load()
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            px[i % w, i // w] = (255, 0, 0)
    im.save(path)


def check_dump(dump, w, h, bpp, table, faces, diff_path):
    exp = vesa_lines.expected_buffer(table, faces, w, h, bpp)
    if dump == exp:
        return
    bp = BYTES_PP[bpp]
    pa = [dump[i:i + bp] for i in range(0, len(dump), bp)]
    pb = [exp[i:i + bp] for i in range(0, len(exp), bp)]
    x, y = first_diff(pa, pb, w)
    write_diff(diff_path, w, h, pa, pb)
    raise CheckError("dump differs from the expected buffer: first differing pixel x=%d y=%d kind=%s (dump %s, "
                     "expected %s); diff image %s" % (x, y, KINDS[bpp], pa[y * w + x].hex(), pb[y * w + x].hex(),
                                                      diff_path))


def main(argv):
    if len(argv) < 5:
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    png_path, dump_path = argv[0], argv[1]
    try:
        w, h, bpp = (int(v) for v in argv[2:5])
    except ValueError:
        print("vesa_check: W H BPP are numbers", file=sys.stderr)
        return 2
    opts, rest = {}, argv[5:]
    while rest:
        if rest[0] in ("--dac", "--palette-from", "--faces", "--diff") and len(rest) >= 2:
            opts[rest[0]] = rest[1]
            rest = rest[2:]
        else:
            print("vesa_check: bad option %s" % rest[0], file=sys.stderr)
            return 2
    try:
        return run(png_path, dump_path, w, h, bpp, opts)
    except CheckError as e:
        print("vesa_check: FAIL: %s" % e, file=sys.stderr)
        return 1
    except vesa_lines.VesaLinesError as e:
        print("vesa_check: cannot use the table or faces: %s" % e, file=sys.stderr)
        return 2
    except InputError as e:
        print("vesa_check: %s" % e, file=sys.stderr)
        return 2
    except (OSError, ValueError, MemoryError, Image.DecompressionBombError) as e:
        print("vesa_check: cannot read an input: %s" % e, file=sys.stderr)
        return 2


def run(png_path, dump_path, w, h, bpp, opts):
    if bpp not in BYTES_PP or not (1 <= w <= 4096 and 1 <= h <= 4096):
        raise InputError("bad W H BPP: %d %d %d" % (w, h, bpp))
    dac = opts.get("--dac")
    if dac not in (None, "6", "8"):
        raise InputError("--dac is 6 or 8, not %s" % dac)
    if bpp == 8 and dac is None:
        raise InputError("8 bpp needs --dac")
    table = vesa_lines.parse(opts["--palette-from"]) if "--palette-from" in opts else None
    with open(dump_path, "rb") as fh:
        dump = fh.read()
    if len(dump) != w * h * BYTES_PP[bpp]:
        raise InputError("dump is %d bytes, a %dx%d %d bpp buffer is %d" % (len(dump), w, h, bpp,
                                                                           w * h * BYTES_PP[bpp]))
    pal = None
    if bpp == 8:
        if table is None:
            raise InputError("8 bpp needs --palette-from")
        pal = vesa_lines.palette(table, int(dac))
    if "--faces" in opts:
        if table is None:
            raise InputError("--faces needs --palette-from")
        check_dump(dump, w, h, bpp, table, opts["--faces"], opts.get("--diff", png_path + ".diff.png"))
    vals, bits = pixel_values(dump, w, h, bpp, pal)
    if bits is None:
        bits = (int(dac) if dac == "6" else 8,) * 3
    im = Image.open(png_path)
    im.load()
    im = im.convert("RGB")
    if im.size != (w, h):
        raise CheckError("PNG is %dx%d, expected %dx%d" % (im.size[0], im.size[1], w, h))
    got = list(im.getdata())
    n = w * h

    # the PNG's own background is its most common colour; at least 1 % of the frame must differ from it
    counts = {}
    for g in got:
        counts[g] = counts.get(g, 0) + 1
    png_bg = max(counts, key=counts.get)
    ink = n - counts[png_bg]
    if ink * 100 < n:
        raise CheckError("only %d of %d PNG pixels are not the background (< 1 %%)" % (ink, n))

    fits, within = [], []  # per channel: the rules that reproduce it exactly; whether it is within tolerance of exact
    for ch in range(3):
        b = bits[ch]
        pairs = {}
        for v, g in zip(vals, got):
            pairs.setdefault(v[ch], set()).add(g[ch])
        fits.append([name for name, fns in FAMILIES.items() if all(s == {fns[b](k)} for k, s in pairs.items())])
        ex = FAMILIES["exact"][b]
        within.append(all(abs(g - ex(k)) <= TOLERANCE[b] for k, s in pairs.items() for g in s))
    common = [name for name in FAMILIES if all(name in f for f in fits)]
    if common:
        print("rule=%s" % common[0])
        return 0
    # a channel that every rule fits (a constant 0, say) does not pin a rule down: it does not block the tolerance
    if all(not f for f in fits if len(f) < len(FAMILIES)) and all(within):
        print("tolerance=yes")
        print("rule=tolerance")
        return 0
    detail = ", ".join("%s: %s" % ("rgb"[i], "/".join(f) or ("tolerance" if within[i] else "none"))
                       for i, f in enumerate(fits))
    raise CheckError("no one rule explains all three channels (%s)" % detail)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
