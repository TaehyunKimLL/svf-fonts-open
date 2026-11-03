#!/usr/bin/env python3
"""sdl_check.py DUMP --kind K --lines FILE --faces DIR [--threshold N] [--diff PNG] [--shot BMP]

The headless check of the SDL example: DUMP is what `svfsdl --dump` wrote (the surface's bytes after drawing the lines
file); the checker rebuilds the same bytes with tools/svfline.py at the dump's pitch and compares every byte.

K is one of xrgb8888 argb8888 rgb565 rgb555 bgr24 index8 gray alpha. gray_bits (the header's bits per pixel) and the
bit order (flags bit 2) come from the dump header; --threshold (default 128) is the mono / INDEX8 / GRAY threshold the
port ran with. Exit 0 identical (`sdl-check: OK <kind> <w>x<h> pitch=<p> sdl<major> sum=<fnv1a, 8 hex>`), 1 a byte
differs (`sdl-check: DIFF <kind> byte <i> pixel (<x>,<y>) got <g> want <w>`, and the diff PNG, default
DUMP + ".diff.png": the expected bytes as grey, pitch x h, the differing bytes red), 2 an input that cannot be used (a
bad dump, a header that contradicts --kind or the host byte order, a bad option or lines file, a missing face).

A DIFF in a padding byte (or padding pixel of a sub-byte row) prints `byte <i> padding row <y>` in place of
`pixel (<x>,<y>)` (an accepted deviation: a padding byte has no pixel). An OK run removes the diff PNG it would have
written (DUMP + ".diff.png" or --diff), so a picture of an earlier failure is never left next to a passing dump.

--shot BMP (index8 and gray only): the window shot `svfsdl --present surface --shot` saved (an SDL_SaveBMP of 24 or 32
bits) is compared pixel by pixel with palette[dump index], the palette computed here independently of the C code
(palette_for: index8 tools/vesa_lines.palette, gray entry k = (bg * (n - k) + 255 * k + n / 2) / n per channel,
n = 2^bits - 1, bg the background's rgb888). A mismatch prints `sdl-check: DIFF palette <kind> pixel (<x>,<y>) index <i>
got #RRGGBB want #RRGGBB` and exits 1; the OK line then reads `... sdl<major> shot=ok sum=<fnv1a>` (the sum is last).

The dump format (the one reference of the C writer; all u16 little-endian): a 16-byte header, then pitch * h bytes.

  offset  field
  0-7     b"SVFSDL1 "
  8-9     w
  10-11   h
  12-13   pitch (bytes a row, >= the row's pixels; the padding bytes are 0)
  14      bits per pixel: 32 (xrgb8888, argb8888), 24 (bgr24), 16 (rgb565, rgb555), 8 (index8, alpha, gray at 8), or
          4, 2, 1 (gray)
  15      flags: bit 0 SVF_TF_RGB16_BIGENDIAN was set (rgb565, rgb555 only); bit 1 palettised (index8 and gray, set
          there, clear elsewhere); bit 2 LSB first (gray only); bit 3 alpha-demo coverage buffer (alpha only);
          bits 4-5 SDL major - 2 (0 SDL2, 1 SDL3); bits 6-7 zero

The `svfsdl:` line of an --alpha-demo run is the one exception to "pitch is the dumped buffer's": its `pitch` is the BGRA32
surface's (>= 4 w) and `covpitch` (after it) the dumped GRAY8 buffer's (= w); every other run prints `pitch` only.

`alpha` is the --alpha-demo GRAY8 coverage buffer: expected() draws the first line of the table only, on a gray8 target
of stride = the header pitch (decided: the C writer, Task 7, must write pitch = w, bits per pixel 8 and {BPP} = 8 in the
text, flags bit 3 and bit 1 clear).

The header names the layout, not the kind: 8-bit gray and index8 share one (bpp 8, palettised flag), xrgb8888 and
argb8888 one (bpp 32), rgb565 and rgb555 one (bpp 16). The kind comes from --kind; a mislabelled dump is a byte DIFF
(exit 1), not exit 2 (decided: no extra header bit).

Byte order: the 32 and 24 bit kinds are memory order B G R [X] on every host (the port asks SDL for the array-order
formats), so nothing in the dump depends on the host. The 16 bit kinds follow the big-endian flag; a dump whose flag
disagrees with this host's byte order is refused (exit 2), so the checker only runs where the dump was made.
"""

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "tools"))
import svfline  # noqa: E402
import vesa_lines  # noqa: E402
from vesa_lines import _face_path, fnv1a, parse, substitute  # noqa: E402

MAGIC = b"SVFSDL1 "
HEADER = 16
F_BIG, F_PAL, F_LSB, F_ALPHA = 1, 2, 4, 8
KINDS = ("xrgb8888", "argb8888", "rgb565", "rgb555", "bgr24", "index8", "gray", "alpha")
SVFLINE_KIND = {"xrgb8888": "xrgb8888", "argb8888": "xrgb8888", "rgb565": "rgb565", "rgb555": "rgb555",
                "bgr24": "rgb888", "index8": "indexed8", "gray": "gray", "alpha": "gray8"}
BITS = {"xrgb8888": (32,), "argb8888": (32,), "rgb565": (16,), "rgb555": (16,), "bgr24": (24,), "index8": (8,),
        "gray": (1, 2, 4, 8), "alpha": (8,)}

Dump = collections.namedtuple("Dump", "w h pitch bpp big_endian palettised lsb_first alpha sdl_major data")


class DumpError(Exception):
    """A dump that cannot be read (exit 2)."""


def header(w, h, pitch, bpp, kind=None, big_endian=False, lsb_first=False, sdl_major=3):
    """The 16 header bytes. @p kind (one of KINDS) sets the palettised flag (index8, gray) and the alpha flag (alpha)."""
    if sdl_major not in (2, 3):
        raise ValueError("sdl_major must be 2 or 3")
    flags = (F_BIG if big_endian else 0) | (F_LSB if lsb_first else 0) | (sdl_major - 2) << 4
    if kind in ("index8", "gray"):
        flags |= F_PAL
    if kind == "alpha":
        flags |= F_ALPHA
    return MAGIC + w.to_bytes(2, "little") + h.to_bytes(2, "little") + pitch.to_bytes(2, "little") + bytes((bpp, flags))


def write_dump(path, w, h, pitch, bpp, data, **kw):
    """Writes header(w, h, pitch, bpp, **kw) + data (exactly pitch * h bytes) to @p path."""
    if len(data) != pitch * h:
        raise ValueError("data is not pitch * h bytes")
    with open(path, "wb") as fh:
        fh.write(header(w, h, pitch, bpp, **kw) + bytes(data))


def read_dump(src):
    """The Dump of @p src (bytes, or a path); DumpError for a short or long file, a wrong magic, a zero size or a pitch
    below the row, or a bits-per-pixel / reserved-bit value no kind uses. The kind is not checked here."""
    if isinstance(src, (bytes, bytearray)):
        raw = bytes(src)
    else:
        try:
            with open(src, "rb") as fh:
                raw = fh.read()
        except OSError as e:
            raise DumpError("cannot read %s: %s" % (src, e.strerror)) from None
    if len(raw) < HEADER:
        raise DumpError("shorter than the 16-byte header")
    if raw[:8] != MAGIC:
        raise DumpError("bad magic")
    w, h, pitch = (int.from_bytes(raw[i:i + 2], "little") for i in (8, 10, 12))
    bpp, flags = raw[14], raw[15]
    if bpp not in (1, 2, 4, 8, 16, 24, 32):
        raise DumpError("bits per pixel %d" % bpp)
    if flags & 0xC0 or (flags >> 4 & 3) > 1:
        raise DumpError("reserved flag bits set (flags 0x%02X)" % flags)
    if not (w and h):
        raise DumpError("zero size")
    if pitch < (w * bpp + 7) // 8:
        raise DumpError("pitch %d below the %d bytes of a row" % (pitch, (w * bpp + 7) // 8))
    if len(raw) != HEADER + pitch * h:
        raise DumpError("%d bytes, the header says %d" % (len(raw), HEADER + pitch * h))
    return Dump(w, h, pitch, bpp, bool(flags & F_BIG), bool(flags & F_PAL), bool(flags & F_LSB), bool(flags & F_ALPHA),
                2 + (flags >> 4 & 3), raw[HEADER:])


def palette_for(table, kind, bits=8):
    """The expected palette of an index8 or gray surface: [(r, g, b)], 256 entries for index8, 2^bits for gray."""
    if kind == "index8":
        return [(r, g, b) for (b, g, r, _) in vesa_lines.palette(table, 8)]
    if kind != "gray":
        raise ValueError("no palette for %r" % kind)
    bg = table.colours[table.background].rgb888
    bgc = (bg >> 16 & 255, bg >> 8 & 255, bg & 255)
    n = (1 << bits) - 1
    return [tuple((bgc[c] * (n - k) + 255 * k + n // 2) // n for c in range(3)) for k in range(n + 1)]


def read_bmp(path):
    """(w, h, rows) of an uncompressed 24 or 32 bit BMP (or a 32 bit BI_BITFIELDS one with whole-byte masks):
    rows[y][x] = (r, g, b), top row first. DumpError otherwise (also for pixel data inside the headers)."""
    try:
        with open(path, "rb") as fh:
            b = fh.read()
    except OSError as e:
        raise DumpError("cannot read %s: %s" % (path, e.strerror)) from None
    if len(b) < 54 or b[:2] != b"BM":
        raise DumpError("%s is not a BMP" % path)
    off, hdr = int.from_bytes(b[10:14], "little"), int.from_bytes(b[14:18], "little")
    w, h = (int.from_bytes(b[o:o + 4], "little", signed=True) for o in (18, 22))
    bpp, comp = int.from_bytes(b[28:30], "little"), int.from_bytes(b[30:34], "little")
    if hdr < 40 or comp not in (0, 3) or bpp not in (24, 32) or w <= 0 or h == 0 or (comp == 3 and bpp != 32):
        raise DumpError("%s: BMP header %d bytes, %d bits, compression %d is not supported" % (path, hdr, bpp, comp))
    if off < 14 + hdr:
        raise DumpError("%s: BMP pixel data at %d lies inside the %d byte headers" % (path, off, 14 + hdr))
    # compression 3 (BI_BITFIELDS, what SDL3 writes for a 32 bit surface): the colour masks follow the 40 byte header;
    # only whole-byte masks are read
    shifts = (16, 8, 0)
    if comp == 3:
        masks = [int.from_bytes(b[o:o + 4], "little") for o in (54, 58, 62)] if len(b) >= 66 else []
        if len(masks) != 3 or any(m not in (0xFF, 0xFF00, 0xFF0000, 0xFF000000) for m in masks) or len(set(masks)) != 3:
            raise DumpError("%s: BMP colour masks %s are not supported" % (path, [hex(m) for m in masks]))
        shifts = tuple(m.bit_length() - 8 for m in masks)
    top_down, h = h < 0, abs(h)
    stride = (w * bpp // 8 + 3) & ~3
    if len(b) < off + stride * h:
        raise DumpError("%s: BMP shorter than its header says" % path)
    rows = []
    for y in range(h):
        row = b[off + (y if top_down else h - 1 - y) * stride:][:stride]
        step = bpp // 8
        if comp == 3:   # decode each pixel once
            px = [int.from_bytes(row[x * 4:x * 4 + 4], "little") for x in range(w)]
            rows.append([(v >> shifts[0] & 255, v >> shifts[1] & 255, v >> shifts[2] & 255) for v in px])
        else:
            rows.append([(row[x * step + 2], row[x * step + 1], row[x * step]) for x in range(w)])
    return w, h, rows


def shot_diff(d, kind, table, bmp):
    """None when every pixel of the shot @p bmp is palette[index of the dump @p d]; else the message of the first
    mismatch. Only for the palettised kinds index8 and gray."""
    w, h, rows = read_bmp(bmp)
    if (w, h) != (d.w, d.h):
        return "shot is %dx%d, the dump %dx%d" % (w, h, d.w, d.h)
    pal = palette_for(table, kind, d.bpp)
    mask = (1 << d.bpp) - 1
    for y in range(h):
        row = d.data[y * d.pitch:(y + 1) * d.pitch]
        for x in range(w):
            bit = x * d.bpp
            if d.bpp == 8:
                v = row[x]
            elif d.lsb_first:
                v = row[bit // 8] >> (bit % 8) & mask
            else:
                v = row[bit // 8] >> (8 - d.bpp - bit % 8) & mask
            if rows[y][x] != pal[v]:
                return "palette %s pixel (%d,%d) index %d got #%02X%02X%02X want #%02X%02X%02X" % (
                    kind, x, y, v, *rows[y][x], *pal[v])
    return None


def _clear_pixel(table, kind, big_endian):
    bg = table.colours[table.background]
    if kind in ("xrgb8888", "argb8888", "bgr24"):
        px = bytes((bg.rgb888 & 255, bg.rgb888 >> 8 & 255, bg.rgb888 >> 16 & 255))
        return px + bytes((0xFF if kind == "argb8888" else 0,)) if kind != "bgr24" else px
    if kind in ("rgb565", "rgb555"):
        return (bg.rgb565 if kind == "rgb565" else bg.rgb555).to_bytes(2, "big" if big_endian else "little")
    if kind == "index8":
        return bytes((bg.index_base,))
    return b"\0"  # gray, alpha: zero bytes


def expected(table, faces_dir, kind, w, h, pitch, threshold=128, gray_bits=8, lsb_first=False, big_endian=False):
    """The bytes (pitch * h) the port's surface holds after drawing @p table: each row cleared to the background pixel
    over its w pixels (gray, alpha: 0), the padding 0, then each line drawn as tools/vesa_lines.py expected_buffer does
    but at stride @p pitch. For gray the bits per pixel are @p gray_bits and the colours are ignored; for alpha only the
    first line is drawn, on a gray8 target. VesaLinesError for a face that cannot be read."""
    if kind not in KINDS:
        raise ValueError("unknown kind %r" % kind)
    bg = table.colours[table.background]
    bpp = {"xrgb8888": 32, "argb8888": 32, "rgb565": 16, "rgb555": 16, "bgr24": 24, "index8": 8, "alpha": 8,
           "gray": gray_bits}[kind]
    row = (_clear_pixel(table, kind, big_endian) * w if kind not in ("gray", "alpha") else bytes((w * bpp + 7) // 8))
    if len(row) > pitch:
        raise ValueError("pitch below the row")
    buf = bytearray((row + bytes(pitch - len(row))) * h)
    cache = {}
    for l in table.lines[:1] if kind == "alpha" else table.lines:
        chain = []
        for name in l.faces:
            path = _face_path(faces_dir, name, l.src_line)
            if path not in cache:
                try:
                    cache[path] = svfline.Face.load(path)
                except (OSError, ValueError):
                    raise vesa_lines.VesaLinesError(l.src_line, "cannot read face %s" % name) from None
            chain.append(cache[path])
        c = table.colours[l.colour]
        s565 = kind == "rgb555"
        t = svfline.Target(SVFLINE_KIND[kind], w, h, stride=pitch, buf=buf,
                           fg565=c.rgb555 if s565 else c.rgb565, bg565=bg.rgb555 if s565 else bg.rgb565,
                           threshold=threshold, big_endian=big_endian, index_base=c.index_base,
                           index_levels=c.index_levels,
                           fg888=c.rgb888 | (0xFF000000 if kind == "argb8888" else 0), bg888=bg.rgb888,
                           gray_bits=gray_bits if kind == "gray" else 8, lsb_first=lsb_first)
        places = svfline.placements(chain, substitute(l.text, w, h, bpp).encode("utf-8"), l.x, l.baseline,
                                    scale=(l.num, l.den))
        svfline.draw_target(places, t)
    return bytes(buf)


def _contradiction(d, kind):
    """The reason the header of @p d contradicts @p kind or the host, or None."""
    if d.bpp not in BITS[kind]:
        return "header says %d bits per pixel, %s has %s" % (d.bpp, kind, "/".join(map(str, BITS[kind])))
    if d.palettised != (kind in ("index8", "gray")):
        return "palettised flag %s for %s" % ("set" if d.palettised else "clear", kind)
    if d.lsb_first and kind != "gray":
        return "LSB-first flag on %s" % kind
    if d.alpha != (kind == "alpha"):
        return "alpha-demo flag %s for %s" % ("set" if d.alpha else "clear", kind)
    if kind == "alpha" and d.pitch != d.w:
        return "alpha pitch %d, must be the width %d (the writer writes pitch = w)" % (d.pitch, d.w)
    if d.big_endian and kind not in ("rgb565", "rgb555"):
        return "big-endian flag on %s" % kind
    if d.big_endian and sys.byteorder == "little":
        return "big-endian flag on a little-endian host"
    if not d.big_endian and kind in ("rgb565", "rgb555") and sys.byteorder == "big":
        return "little-endian dump on a big-endian host"
    return None


def _diff_png(path, want, got, pitch, h):
    from PIL import Image
    im = Image.new("RGB", (pitch, h))
    px = [(v, v, v) for v in want]
    for i, (a, b) in enumerate(zip(want, got)):
        if a != b:
            px[i] = (255, 0, 0)
    im.putdata(px)
    im.save(path)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sdl_check.py", description="Checks a svfsdl --dump against tools/svfline.py.")
    ap.add_argument("dump")
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--lines", required=True)
    ap.add_argument("--faces", required=True)
    ap.add_argument("--threshold", type=int, default=128)
    ap.add_argument("--diff")
    ap.add_argument("--shot")
    try:
        a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as e:
        return 2 if e.code else 0
    kind = a.kind

    def bad(msg):
        print("sdl-check: %s" % msg, file=sys.stderr)
        return 2

    if not 0 <= a.threshold <= 255:
        return bad("--threshold %d out of 0..255" % a.threshold)
    if not os.path.isdir(a.faces):
        return bad("--faces %s is not a directory" % a.faces)
    try:
        d = read_dump(a.dump)
    except DumpError as e:
        return bad("%s: %s" % (a.dump, e))
    why = _contradiction(d, kind)
    if why:
        return bad("%s: %s" % (a.dump, why))
    if a.shot and kind not in ("index8", "gray"):
        return bad("--shot is for index8 and gray only")
    try:
        table = parse(a.lines)
        want = expected(table, a.faces, kind, d.w, d.h, d.pitch, threshold=a.threshold, gray_bits=d.bpp,
                        lsb_first=d.lsb_first, big_endian=d.big_endian)
    except vesa_lines.VesaLinesError as e:
        return bad("%s: %s" % (a.lines, e))
    got = d.data
    if len(want) != len(got):   # zip below would stop at the shorter and call a truncated reference identical
        return bad("%s: the reference is %d bytes, the dump holds %d" % (a.dump, len(want), len(got)))
    for i, (x, y) in enumerate(zip(want, got)):
        if x != y:
            break
    else:
        png = a.diff or a.dump + ".diff.png"
        if os.path.exists(png):   # a diff picture of an earlier failing run is stale now
            try:
                os.remove(png)
            except OSError:
                pass
        if a.shot:
            try:
                why = shot_diff(d, kind, table, a.shot)
            except DumpError as e:
                return bad(str(e))
            if why:
                print("sdl-check: DIFF %s" % why)
                return 1
        print("sdl-check: OK %s %dx%d pitch=%d sdl%d%s sum=%08x" % (kind, d.w, d.h, d.pitch, d.sdl_major,
                                                                   " shot=ok" if a.shot else "", fnv1a(got)))
        return 0
    row, col = divmod(i, d.pitch)
    rowbytes = (d.w * d.bpp + 7) // 8
    x = col * 8 // d.bpp
    if d.bpp < 8:   # the first differing pixel inside the byte (bit order of the header)
        ppb, mask = 8 // d.bpp, (1 << d.bpp) - 1
        for p in range(ppb):
            sh = d.bpp * p if d.lsb_first else 8 - d.bpp * (p + 1)
            if (got[i] ^ want[i]) >> sh & mask:
                x = col * ppb + p
                break
    where = "padding row %d" % row if col >= rowbytes or x >= d.w else "pixel (%d,%d)" % (x, row)
    print("sdl-check: DIFF %s byte %d %s got 0x%02X want 0x%02X" % (kind, i, where, got[i], want[i]))
    png = a.diff or a.dump + ".diff.png"
    try:
        _diff_png(png, want, got, d.pitch, d.h)
    except (OSError, ValueError, ImportError) as e:
        print("sdl-check: cannot write %s: %s" % (png, getattr(e, "strerror", None) or e), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
