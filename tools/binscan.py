#!/usr/bin/env python3
"""Look for bitmap fonts inside any file (a DOS driver, a .COM/.EXE, a ROM dump, an archive member) and draw what is
at an offset, so a person (or Claude) can see where a font starts and what layout it has.

Nothing here runs or decodes the file's code: it reads bytes. Run it with `python3 -I` on untrusted downloads.

  binscan.py info FILE                         size, kind (MZ, COM, ARJ, ZIP...), entropy map, size signatures
  binscan.py runs FILE --glyph 16x16           runs of glyph-like windows (start offset, length in glyphs)
  binscan.py sets FILE --sets 8,4,4            offsets where every set's fill slot 0 is blank (raw jamo-piece fonts)
  binscan.py ascii FILE [--height 16]          8xH ASCII fonts: space blank, '_' low, '-' in the middle, A-Z inked
  binscan.py render FILE --offset 0x60 --glyph 16x16 --count 40 [--png OUT.png]   draw glyphs as text or a PNG

Glyph geometry (render, runs): `--glyph WxH`; `--stride B` bytes from one glyph to the next (default: the glyph's
bytes); `--order rows` (row-major, ceil(W/8) bytes a row; the default), `strips` (8-pixel-wide strips one after
the other, H bytes each: the left half's rows, then the right half's; the Korean VGA font ROMs, and the 6x2x1 fonts,
jamoset.py's g_bytecols), `cols` (column-major: H/8 bytes a column, MSB at the top: the Dokkaebi printer layout),
`bytecols` (8-row bands, each W bytes, one byte a column of 8 rows; bit 7 is the band's top row, or bit 0 with
--lsb: the layout of 8-dot-column printer and some character-ROM dumps); `--lsb` puts bit 0 at the left (rows,
strips) or the top (cols, bytecols); `--invert` reads the 0 bits as ink (ROMs drawn as paper, such as the Samsung
SPC-1500's). Multi-bit tiles (arcade sprite and tile ROMs): `--gfx LAYOUT` with a preset `WxHxN_packed_lsb` /
`WxHxN_packed_msb` (N bits a pixel, row after row; _lsb: the first pixel of a byte in its low bits) or the four lists of
the driver's MAME gfx_layout, `planes=..;x=..;y=..;inc=N` (bit offsets from the tile's start, bit 0 the MSB of its first
byte, plane 0 the pen's high bit; `STEP2` .. `STEP1024(start,step)`, their `_INV` forms and `RGN_FRAC(a,b)` = a/b of the file as in the driver,
without the braces and C comments; the file is
the ROM region, which `rawcarve.py region` assembles from the ROM files); a pixel is ink when its pen is not `--bg`
(default 0), or, with `--fg PEN[,PEN...]`, when its pen is one of those (the body of an outlined glyph without its
outline pen); `--invert` then makes the other pens the ink. Offsets accept 0x hex. `render --cols N` sets glyphs per row of the picture, `--scale S` the PNG pixel
size; the text form marks ink `#` and paper `.`, and labels every glyph with its index and file offset.

The size signatures (`info`) are the byte counts of the layouts the repository reads (docs/recipes/dos-fonts.md, "Other DOS-era
Korean fonts") and of whole-syllable dumps: 8x4x4 = 360 glyphs (11,520 at 16 px, 25,920 at 24, 72,000 at 40,
103,680 at 48; 15,584 for Dokkaebi's 8x4x4 + 127 symbols), 10x4x4 = 12,800, 6x2x1 = 6,144, KS X 1001 syllables =
2,350 x the glyph's bytes (75,200 at 16x16, 169,200 at 24x24), a full KS X 1001 94 x 94 table = 8,836 x the glyph's
bytes, an 8x16 English font = 2,048 or 4,096.
"""

import argparse
import math
import os
import re
import struct
import sys
import zlib

SIGNATURES = [
    (11520, "8x4x4 jamo set, 16x16 (360 x 32 B)"),
    (11522, "8x4x4 jamo set, 16x16 with a 2-byte header"),
    (15584, "Dokkaebi 8x4x4 + 127 symbols, 16x16"),
    (25920, "8x4x4 jamo set, 24x24 (360 x 72 B)"),
    (72000, "8x4x4 jamo set, 40x40 (360 x 200 B)"),
    (103680, "8x4x4 jamo set, 48x48 (360 x 288 B)"),
    (12800, "10x4x4 jamo set (san), 16x16 (400 x 32 B)"),
    (6144, "6x2x1 jamo set, 16x16 byte columns (192 x 32 B)"),
    (243900, "HBIOS / Taebaek 24x30 (2,710 x 90 B: 360 pieces + 2,350 syllables)"),
    (75200, "KS X 1001 syllables, 16x16 (2,350 x 32 B)"),
    (169200, "KS X 1001 syllables, 24x24 (2,350 x 72 B)"),
    (470000, "KS X 1001 syllables, 40x40 (2,350 x 200 B)"),
    (676800, "KS X 1001 syllables, 48x48 (2,350 x 288 B)"),
    (282752, "KS X 1001 94x94 table, 16x16 (8,836 x 32 B)"),
    (2048, "8x16 English font, 128 glyphs"),
    (4096, "8x16 English font, 256 glyphs (or 8x8 x 512)"),
    (3584, "8x14 English font, 256 glyphs"),
    (12288, "12x24 English font, 256 x 48 B (Taebaek PFT)"),
    (15360, "12x24 English font in a 16x30 cell (HBIOS), or Dokkaebi 7x2x2 printer 16 px"),
]


def parse_int(s):
    return int(s, 0)


def parse_glyph(s):
    try:
        w, h = (int(v) for v in s.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError("glyph is WxH, e.g. 16x16")
    if not (1 <= w <= 1024 and 1 <= h <= 1024):
        raise argparse.ArgumentTypeError("glyph width and height are 1..1024")
    return w, h


def counts(s):
    try:
        v = tuple(int(x) for x in s.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{s}: three numbers, e.g. 8,4,4")
    if len(v) != 3 or min(v) < 1:
        raise argparse.ArgumentTypeError(f"{s}: three numbers of 1 or more")
    return v


def bounded(top):
    def f(s):
        v = parse_int(s)
        if not 1 <= v <= top:
            raise argparse.ArgumentTypeError(f"{s}: must be 1..{top}")
        return v
    return f


def positive(s):
    v = parse_int(s)
    if v < 1:
        raise argparse.ArgumentTypeError(f"{s}: must be 1 or more")
    return v


def pens(s):
    try:
        v = [int(x, 0) for x in s.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(f"{s}: pen numbers, e.g. 1 or 1,2")
    if not v or min(v) < 0:
        raise argparse.ArgumentTypeError(f"{s}: pen numbers of 0 or more")
    return v


def nonneg(s):
    v = parse_int(s)
    if v < 0:
        raise argparse.ArgumentTypeError(f"{s}: must be 0 or more")
    return v


MAX_SCAN = 16 << 20  # runs / sets / ascii scan every offset: past this, name a window with --start / --length


def window(a):
    """(bytes, base): the scanned window of the file and its file offset."""
    size = os.path.getsize(a.file)
    start = a.start
    length = a.length if a.length is not None else size - start
    if start > size:
        raise SystemExit(f"binscan.py: --start {start:#x} is past the end of the file ({size} bytes)")
    length = min(length, size - start)
    if length > MAX_SCAN:
        raise SystemExit(f"binscan.py: {length} bytes to scan; more than {MAX_SCAN}: give --start and --length "
                         f"(windows overlap by a font's size to be safe)")
    with open(a.file, "rb") as fh:
        fh.seek(start)
        data = fh.read(length)
    if getattr(a, "invert", False) and getattr(a, "gfx", None) is None:
        data = bytes(b ^ 0xFF for b in data)  # ink is the 0 bits: scan the complement
    return data, start


def resolve_geometry(a, ap):
    """After parsing: build a.gfx from --gfx (a Gfx, for the file's size) and take --glyph from it; refuse a --glyph
    that disagrees. A command without --gfx keeps a.gfx = None."""
    spec = getattr(a, "gfx", None)
    if getattr(a, "bg", None) is not None and getattr(a, "fg", None) is not None:
        ap.error("--bg and --fg are two ink rules: give one")
    if spec is None:
        if getattr(a, "fg", None) is not None or getattr(a, "bg", None) is not None:
            ap.error("--bg and --fg go with --gfx")
        if getattr(a, "glyph", None) is None:
            ap.error("--glyph WxH is required (or --gfx)")
        return
    try:
        a.gfx = parse_gfx(spec, os.path.getsize(a.file), a.bg or 0, a.fg)
    except (GfxError, OSError) as e:
        ap.error(f"--gfx: {e}")
    if a.glyph is not None and tuple(a.glyph) != (a.gfx.w, a.gfx.h):
        ap.error(f"--glyph {a.glyph[0]}x{a.glyph[1]} is not the --gfx tile's {a.gfx.w}x{a.gfx.h}")
    a.glyph = (a.gfx.w, a.gfx.h)
    if a.stride is None:
        a.stride = a.gfx.stride


class GfxError(ValueError):
    pass


class Gfx:
    """A multi-bit tile layout as MAME's gfx_layout gives it, and the ink rule that reduces a tile to 1 bpp.

    All offsets are in bits from the tile's start (tile n starts at bit n * inc of the region), bit 0 being the MSB of
    the first byte (MAME's readbit). planes[0] is the pen's most significant bit. A pixel is ink when its pen is not
    @p bg (the background pen: 0 for most sprite and tile layers, 15 where the background is the last pen), or, when
    @p fg is given, when its pen is one of @p fg (the body of an outlined glyph without its outline pen)."""

    def __init__(self, w, h, planes, xoffs, yoffs, inc, bg=0, fg=None):
        if len(xoffs) != w or len(yoffs) != h:
            raise GfxError(f"{len(xoffs)} x offsets and {len(yoffs)} y offsets for a {w}x{h} tile")
        if not 1 <= len(planes) <= 8:
            raise GfxError(f"{len(planes)} planes: 1..8")
        if not (1 <= w <= 1024 and 1 <= h <= 1024):
            raise GfxError("tile width and height are 1..1024")
        if inc < 8 or inc % 8:
            raise GfxError(f"inc {inc}: a whole number of bytes (a multiple of 8 bits, 8 or more)")
        if not 0 <= bg < (1 << len(planes)):
            raise GfxError(f"background pen {bg} is outside 0..{(1 << len(planes)) - 1}")
        if fg is not None and (not fg or any(not 0 <= p < (1 << len(planes)) for p in fg)):
            raise GfxError(f"ink pens {sorted(fg)} must be in 0..{(1 << len(planes)) - 1}")
        self.fg = frozenset(fg) if fg is not None else None
        if min(list(planes) + list(xoffs) + list(yoffs)) < 0:
            raise GfxError("negative bit offset")
        if max(list(planes) + list(xoffs) + list(yoffs) + [inc]) > MAX_BIT:
            raise GfxError(f"a bit offset or inc past {MAX_BIT}")
        self.w, self.h, self.planes, self.x, self.y, self.inc, self.bg = w, h, list(planes), list(xoffs), list(yoffs), inc, bg
        self.stride = inc // 8
        self.foot = (max(planes) + max(xoffs) + max(yoffs)) // 8 + 1  # the bytes a tile's bits reach

    def decode(self, data, off):
        """The tile whose bit 0 is byte @p off, as h rows of w ints (1 = ink). Bytes past the end read as 0."""
        base = off * 8
        n = len(data)
        nplanes = len(self.planes)
        rows = []
        for yo in self.y:
            row = []
            for xo in self.x:
                pen = 0
                for k, po in enumerate(self.planes):
                    b = base + po + yo + xo
                    i = b >> 3
                    if i < n and data[i] & (0x80 >> (b & 7)):
                        pen |= 1 << (nplanes - 1 - k)
                row.append((1 if pen in self.fg else 0) if self.fg is not None else (1 if pen != self.bg else 0))
            rows.append(row)
        return rows


NUMBER = re.compile(r"0[xX][0-9a-fA-F]+|[1-9][0-9]*|0")  # ASCII digits only: no 08, 1e3, ² or 1_000
MAX_NUMBER_CHARS = 12
MAX_OFFSETS = 1024  # offsets in one list (MAME's tiles are at most 1024 wide or high; planes at most 8)
MAX_DEPTH = 32  # nesting of parentheses and function arguments
MAX_BIT = 1 << 36  # the largest bit offset or inc (8 GiB): past any region the tools read
STEPS = {2 ** k for k in range(1, 11)}  # STEP2 .. STEP1024 (MAME's STEP2048 would pass the 1,024-offset cap); any
# STEPn_INV is the same offsets reversed (MAME defines STEP2_INV and STEP4_INV; the larger ones are accepted too)


def _gfx_tokens(s):
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c.isspace():
            i += 1
        elif c.isdigit():
            j = i
            while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                j += 1
            tok = s[i:j]
            if len(tok) > MAX_NUMBER_CHARS or not NUMBER.fullmatch(tok):
                raise GfxError(f"bad number {tok[:MAX_NUMBER_CHARS + 1]!r} in a gfx layout (decimal without a leading 0, "
                               f"or 0x hex; at most {MAX_NUMBER_CHARS} characters)")
            out.append(("num", int(tok, 0)))
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < len(s) and (s[j].isalnum() or s[j] == "_"):
                j += 1
            out.append(("name", s[i:j].upper()))
            i = j
        elif c in "+-*/(),":
            out.append((c, c))
            i += 1
        else:
            raise GfxError(f"unexpected {c!r} in {s!r}")
    return out


def _gfx_list(s, region_bits):
    """A MAME offset list: comma-separated integers, RGN_FRAC(a,b) (a/b of the region, in bits), STEPn(start,step)
    (n offsets start, start + step, ...), with + - * and parentheses."""
    toks = _gfx_tokens(s)
    pos = [0]

    def peek():
        return toks[pos[0]][0] if pos[0] < len(toks) else None

    def take(kind=None):
        if pos[0] >= len(toks) or (kind and toks[pos[0]][0] != kind):
            raise GfxError(f"{s!r}: expected {kind or 'more'} at token {pos[0]}")
        pos[0] += 1
        return toks[pos[0] - 1]

    depth = [0]

    def nest():
        depth[0] += 1
        if depth[0] > MAX_DEPTH:
            raise GfxError(f"{s[:40]!r}...: nested more than {MAX_DEPTH} deep")

    def args(n):
        nest()
        take("(")
        v = [expr()]
        while peek() == ",":
            take(",")
            v.append(expr())
        take(")")
        depth[0] -= 1
        if len(v) != n:
            raise GfxError(f"{s!r}: {n} arguments expected")
        return v

    def factor():
        k = peek()
        if k == "num":
            return take()[1]
        if k == "-":
            take("-")
            nest()
            v = -factor()
            depth[0] -= 1
            return v
        if k == "(":
            nest()
            take("(")
            v = expr()
            take(")")
            depth[0] -= 1
            return v
        if k == "name":
            name = take()[1]
            if name == "RGN_FRAC":
                a, b = args(2)
                if b <= 0:
                    raise GfxError("RGN_FRAC(a, b) needs b > 0")
                return region_bits * a // b
            raise GfxError(f"{s!r}: unknown name {name} (RGN_FRAC and STEPn only)")
        raise GfxError(f"{s!r}: a number, RGN_FRAC or STEPn expected")

    def term():
        v = factor()
        while peek() in ("*", "/"):
            op = take()[0]
            r = factor()
            if op == "/" and r == 0:
                raise GfxError("division by 0")
            v = v * r if op == "*" else v // r
            if abs(v) > MAX_BIT:
                raise GfxError(f"{s[:40]!r}: a value past {MAX_BIT}")
        return v

    def expr():
        v = term()
        while peek() in ("+", "-"):
            op = take()[0]
            r = term()
            v = v + r if op == "+" else v - r
            if abs(v) > MAX_BIT:
                raise GfxError(f"{s[:40]!r}: a value past {MAX_BIT}")
        return v

    out = []
    while True:
        m = re.fullmatch(r"STEP([0-9]+)(_INV)?", toks[pos[0]][1]) if peek() == "name" else None
        if m:
            take()
            n = int(m.group(1)) if len(m.group(1)) <= 4 else 0
            if n not in STEPS:
                raise GfxError(f"{m.group(0)}: STEP2, STEP4 .. STEP1024 (and their _INV forms); a list holds at most "
                               f"{MAX_OFFSETS} offsets")
            if len(out) + n > MAX_OFFSETS:
                raise GfxError(f"more than {MAX_OFFSETS} offsets in one list")
            start, step = args(2)
            seq = [start + i * step for i in range(n)]
            out += seq[::-1] if m.group(2) else seq
        else:
            if len(out) + 1 > MAX_OFFSETS:
                raise GfxError(f"more than {MAX_OFFSETS} offsets in one list")
            out.append(expr())
        if peek() is None:
            return out
        take(",")


PACKED = re.compile(r"([0-9]+)x([0-9]+)x([0-9]+)_packed_(lsb|msb)")


def packed_layout(w, h, bpp, lsb):
    """MAME's gfx_WxHxN_packed_msb / _lsb: N bits a pixel, W * N bits a row; _lsb puts the first pixel of a byte in its
    low bits (the first pixel of a 4 bpp byte is its low nibble)."""
    if bpp not in (1, 2, 4, 8):
        raise GfxError("packed layouts are 1, 2, 4 or 8 bpp")
    per = 8 // bpp
    if not (1 <= w <= 1024 and 1 <= h <= 1024):
        raise GfxError("tile width and height are 1..1024")
    if w % per:
        raise GfxError(f"a {bpp} bpp packed row of {w} pixels does not end on a byte ({per} pixels a byte)")
    xs = []
    for x in range(w):
        slot = x % per
        xs.append((x // per) * 8 + ((per - 1 - slot) if lsb else slot) * bpp)
    return list(range(bpp)), xs, [y * w * bpp for y in range(h)], w * h * bpp


def parse_gfx(spec, region_bytes, bg=0, fg=None):
    """A Gfx from @p spec: a preset `WxHxN_packed_lsb` / `WxHxN_packed_msb`, or the four lists of a MAME gfx_layout as
    `planes=...;x=...;y=...;inc=N` (the driver's numbers; RGN_FRAC(a,b) is a/b of @p region_bytes, in bits)."""
    m = PACKED.fullmatch(spec.strip())
    if m:
        if any(len(v) > 5 for v in m.groups()[:3]):
            raise GfxError("tile width and height are 1..1024")
        w, h, bpp = (int(v) for v in m.groups()[:3])
        planes, xs, ys, inc = packed_layout(w, h, bpp, m.group(4) == "lsb")
        return Gfx(w, h, planes, xs, ys, inc, bg, fg)
    parts = {}
    for item in spec.split(";"):
        if not item.strip():
            continue
        if "=" not in item:
            raise GfxError(f"{item!r}: key=value (planes, x, y, inc)")
        k, v = item.split("=", 1)
        k = k.strip().lower()
        if k not in ("planes", "x", "y", "inc") or k in parts:
            raise GfxError(f"{k!r}: the keys are planes, x, y and inc, once each")
        parts[k] = _gfx_list(v, region_bytes * 8)
    if set(parts) != {"planes", "x", "y", "inc"}:
        raise GfxError("a gfx layout needs planes=, x=, y= and inc= (or a preset such as 16x16x4_packed_lsb)")
    if len(parts["inc"]) != 1:
        raise GfxError("inc is one number")
    return Gfx(len(parts["x"]), len(parts["y"]), parts["planes"], parts["x"], parts["y"], parts["inc"][0], bg, fg)


def glyph_bytes(w, h, order, gfx=None):
    if gfx is not None:
        return gfx.stride
    if order in ("rows", "strips"):
        return ((w + 7) // 8) * h
    return w * ((h + 7) // 8)


def footprint(w, h, order, gfx=None):
    """The bytes one glyph's bits reach from its offset (a multi-plane tile may reach past its stride)."""
    return gfx.foot if gfx is not None else glyph_bytes(w, h, order)


def decode(data, off, w, h, order="rows", lsb=False, invert=False, gfx=None):
    """The glyph at @p off as a list of h rows of w ints (0/1). Bytes past the end read as 0 (as ink, with @p invert).
    @p invert: ink is the 0 bits (or, with @p gfx, the pixels the pen rule calls background). @p gfx: a Gfx tile layout
    (then @p w, @p h are its size and @p order, @p lsb are not used)."""
    if gfx is not None:
        rows = gfx.decode(data, off)
        return [[1 - v for v in r] for r in rows] if invert else rows
    rows = _decode1(data, off, w, h, order, lsb)
    return [[1 - v for v in r] for r in rows] if invert else rows


def _decode1(data, off, w, h, order, lsb):
    def byte(i):
        return data[i] if 0 <= i < len(data) else 0

    def bit(b, k):
        return (b >> k) & 1 if lsb else (b >> (7 - k)) & 1
    rows = [[0] * w for _ in range(h)]
    if order == "rows":
        rb = (w + 7) // 8
        for y in range(h):
            for x in range(w):
                rows[y][x] = bit(byte(off + y * rb + x // 8), x % 8)
    elif order == "cols":
        cb = (h + 7) // 8
        for x in range(w):
            for y in range(h):
                rows[y][x] = bit(byte(off + x * cb + y // 8), y % 8)
    elif order == "strips":
        for x in range(w):
            for y in range(h):
                rows[y][x] = bit(byte(off + (x // 8) * h + y), x % 8)
    elif order == "bytecols":
        for band in range((h + 7) // 8):
            for x in range(w):
                b = byte(off + band * w + x)
                for k in range(8):
                    y = band * 8 + k
                    if y < h:
                        rows[y][x] = bit(b, k)
    else:
        raise ValueError("order is rows, strips, cols or bytecols")
    return rows


def entropy(block):
    if not block:
        return 0.0
    n = [0] * 256
    for b in block:
        n[b] += 1
    t = len(block)
    return -sum(c / t * math.log2(c / t) for c in n if c)


def kind_of(data, path):
    """The file's kind from its first bytes (@p data: the first 0x60, or all of a shorter file)."""
    if data[:2] in (b"MZ", b"ZM"):
        if len(data) >= 0x1C:
            last, pages, _, hdr = struct.unpack_from("<HHHH", data, 2)
            image = pages * 512 - (512 - last if last else 0)
            hdr16 = hdr * 16
            extra = ""
            if b"LZ91" in data[0x1C:0x20] or b"LZ09" in data[0x1C:0x20]:
                extra = ", LZEXE packed: unpack it before scanning"
            elif b"PKLITE" in data[:0x60]:
                extra = ", PKLITE packed: unpack it before scanning"
            return f"DOS MZ executable, header {hdr16} B, load image {hdr16}..{image}{extra}"
        return "DOS MZ executable"
    if data[:2] == b"\x60\xea":
        return "ARJ archive (members may be stored or packed: list them with 7z l)"
    if data[:4] == b"PK\x03\x04":
        return "ZIP archive"
    if data[:2] == b"\x55\xaa":
        return f"option ROM (55 AA), {data[2] * 512} B declared" if len(data) > 2 else "option ROM (55 AA), no size byte"
    if path.lower().endswith(".com"):
        return "DOS .COM image (loads at offset 0x100: a file offset F is address F + 0x100)"
    return "raw data"


def cmd_info(a):
    n = os.path.getsize(a.file)
    with open(a.file, "rb") as fh:
        head = fh.read(0x60)
    print(f"{a.file}: {n} bytes; {kind_of(head, a.file)}")
    for size, what in SIGNATURES:
        if n == size:
            print(f"  size matches: {what}")
    for size, what in SIGNATURES:
        if size >= 6144 and n % size == 0 and n != size and n // size <= 8:
            print(f"  size is {n // size} x {size}: {what}")
    for gb in (32, 72, 128, 200, 288):
        for count, name in ((2350, "KS X 1001 syllables"), (8836, "a 94x94 KS table"), (8192, "8,192 slots"),
                            (16384, "16,384 slots")):
            if n == gb * count:
                print(f"  size = {count} x {gb} B: {name}")
    blk = a.block
    print(f"  entropy per {blk} B (bits a byte; packed or compressed data stays near 8, fonts and tables lower):")
    line = []
    with open(a.file, "rb") as fh:  # a block at a time
        for off in range(0, n, blk):
            e = entropy(fh.read(blk))
            line.append(f"{off:#07x}:{e:4.2f}")
            if len(line) == 6:
                print("   ", "  ".join(line))
                line = []
    if line:
        print("   ", "  ".join(line))


def glyph_like(rows):
    """(ink fraction, mean changed pixels between rows): a font glyph has some ink and rows that change little."""
    h, w = len(rows), len(rows[0])
    ink = sum(map(sum, rows))
    change = sum(sum(1 for x in range(w) if rows[y][x] != rows[y + 1][x]) for y in range(h - 1))
    return ink / (w * h), change / max(1, h - 1)


def cmd_runs(a):
    data, base = window(a)
    w, h = a.glyph
    gb = a.stride or glyph_bytes(w, h, a.order, a.gfx)
    lo, hi = 0, len(data)
    if a.gfx is not None:  # a tile's planes may lie anywhere in the region: read it all, scan the window
        if os.path.getsize(a.file) > MAX_SCAN:
            raise SystemExit(f"binscan.py: --gfx reads the whole file; more than {MAX_SCAN} bytes")
        with open(a.file, "rb") as fh:
            data = fh.read()
        lo, hi, base = base, base + len(data[base:base + (a.length or len(data))]), 0
    found = []
    foot = footprint(w, h, a.order, a.gfx)
    # the last start: its whole footprint in the file, and its bytes (up to a stride) in the window
    last = min(hi - min(gb, foot), len(data) - foot)
    # window() has complemented 1 bpp bytes already: decode inverts only the pens of --gfx tiles
    invert = a.invert and a.gfx is not None
    for phase in range(0, gb, a.step):
        run_start, run_n, blanks = None, 0, 0
        for off in range(lo + phase, last + 1, gb):
            rows = decode(data, off, w, h, a.order, a.lsb, invert, a.gfx)
            ink, change = glyph_like(rows)
            blank = ink == 0
            ok = blank or (0.02 <= ink <= 0.6 and change <= a.max_change * w / 8)
            if ok:
                if run_start is None:
                    run_start, run_n, blanks = off, 0, 0
                run_n += 1
                blanks += blank
            if not ok or off + gb > last:
                if run_start is not None and run_n - blanks >= a.min:
                    found.append((run_start, run_n, blanks))
                run_start = None
    # keep the best phase of overlapping runs: the longest inked one
    found.sort(key=lambda r: (-(r[1] - r[2]), r[0]))
    kept = []
    for s, n, b in found:
        e = s + n * gb
        if any(not (e <= ks or s >= ks + kn * gb) for ks, kn, _ in kept):
            continue
        kept.append((s, n, b))
    kept.sort()
    kind = f"--gfx {a.gfx.w}x{a.gfx.h}x{len(a.gfx.planes)}" if a.gfx else a.order
    print(f"{a.file}: {hi - lo} bytes; glyph {w}x{h} {kind}{' inverted' if a.invert else ''}, {gb} B a glyph; "
          f"runs of >= {a.min} inked glyphs")
    for s, n, b in kept:
        print(f"  offset {base + s:#x} ({base + s}): {n} glyphs ({b} blank), ends {base + s + n * gb:#x}")
    if not kept:
        print("  none")


def cmd_sets(a):
    if a.gfx is not None:
        raise SystemExit("binscan.py: sets reads 1 bpp bytes; write the tiles' ink map with rawcarve.py ink first")
    data, base = window(a)
    ni, nm, nf = a.sets
    si, sm, sf = a.slots
    w, h = a.glyph
    gb = a.stride or glyph_bytes(w, h, a.order)
    fill = ([s * si for s in range(ni)] + [ni * si + s * sm for s in range(nm)]
            + [ni * si + nm * sm + s * sf for s in range(nf)])
    total = ni * si + nm * sm + nf * sf
    span = total * gb
    fills = set(fill)
    hits = []
    zero = bytes(gb)
    for off in range(0, len(data) - span + 1):
        if any(data[off + i * gb:off + (i + 1) * gb] != zero for i in fill):
            continue
        inked = sum(1 for i in range(total) if i not in fills and data[off + i * gb:off + (i + 1) * gb] != zero)
        if inked >= a.min_inked * (total - len(fill)):
            hits.append((off, inked))
    # a font shifted by a byte passes too (its blank slots stay blank): of each cluster of nearby hits keep the
    # offsets whose strokes run across the byte seams of a row (x = 7 and 8, 15 and 16 ...) most often (a misaligned
    # read pairs the right half of one row with the left half of the next, and its seams rarely meet); reads a whole
    # row apart score the same and are listed together, unranked
    def seam(off):
        both = either = 0
        for i in range(total):
            if i in fills:
                continue
            for r in decode(data, off + i * gb, w, h, a.order, a.lsb):
                for x in range(8, w, 8):
                    both += r[x - 1] & r[x]
                    either += r[x - 1] | r[x]
        return both / either if either else 0.0

    clusters = []
    for off, inked in hits:
        if clusters and off - clusters[-1][-1][0] < gb:
            clusters[-1].append((off, inked))
        else:
            clusters.append([(off, inked)])
    best = []
    for c in clusters:
        scored = [(round(seam(off), 3), off, inked) for off, inked in c]
        top = max(r for r, _, _ in scored)
        ties = [(off, inked) for r, off, inked in scored if r == top]
        best.append((ties, top, len(c)))
    print(f"{a.file}: {ni}x{nm}x{nf} sets of {si}/{sm}/{sf} slots, {gb} B a glyph, {total} glyphs = {span} B; "
          f"offsets whose {len(fill)} fill slots are blank and >= {a.min_inked:.0%} of the others inked:")
    for ties, r, n in best[:a.limit]:
        if len(ties) == 1:
            off, inked = ties[0]
            print(f"  offset {base + off:#x} ({base + off}): {inked} of {total - len(fill)} pieces inked, seam {r:.2f}, "
                  f"ends {base + off + span:#x}; {n} nearby reads pass")
        else:
            print(f"  offsets {', '.join(f'{base + o:#x}' for o, _ in ties)} tie (seam {r:.2f}, {n} nearby reads pass): "
                  f"the same font read a whole row apart; the bytes cannot tell which is right: decide from the "
                  f"driver's code (the address it draws from) or by cmp with a loose copy of the font")
    if not best:
        print("  none")
    elif len(best) > a.limit:
        print(f"  ... {len(best) - a.limit} more")


def cmd_ascii(a):
    data, base = window(a)
    h = a.height
    hits = []
    for at in range(0, len(data) - 128 * h + 1):
        sp = data[at + 0x20 * h:at + 0x21 * h]
        if any(sp):
            continue
        under = data[at + 0x5F * h:at + 0x60 * h]
        dash = data[at + 0x2D * h:at + 0x2E * h]
        if not any(under) or not any(dash):
            continue
        uy = [y for y in range(h) if under[y]]
        dy = [y for y in range(h) if dash[y]]
        if min(uy) < h * 2 // 3 or max(dy) > h * 3 // 4 or min(dy) < h // 4:
            continue
        if not all(any(data[at + c * h:at + (c + 1) * h]) for c in range(0x21, 0x7F)):
            continue
        hits.append(at)
    # a font shifted by a byte or two passes the tests too: keep, of each cluster of nearby hits, the alignment whose
    # glyphs least often have ink in their first or last row (a real font keeps those rows for spacing)
    best = []
    for at in hits:
        edge = sum(1 for c in range(0x21, 0x7F) if data[at + c * h] or data[at + c * h + h - 1])
        if best and at - best[-1][2] <= h:
            if edge < best[-1][1]:
                best[-1] = [at, edge, at]
            else:
                best[-1][2] = at
        else:
            best.append([at, edge, at])
    print(f"{a.file}: 8x{h} ASCII candidates (glyph 0 at the offset; 0x41 'A' is at offset + {0x41 * h:#x}; "
          f"edge = glyphs with ink in the first or last row):")
    for at, edge, _ in best[:a.limit]:
        n256 = at + 256 * h <= len(data)
        print(f"  offset {at + base:#x} ({at + base}), edge {edge}{'' if n256 else ' (fewer than 256 glyphs left in the file)'}")
    if not best:
        print("  none")


def png_bytes(pixels, width, height):
    """A grey PNG from rows of 0..255 values."""
    raw = b"".join(b"\x00" + bytes(r) for r in pixels)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def cmd_render(a):
    w, h = a.glyph
    gb = a.stride or glyph_bytes(w, h, a.order, a.gfx)
    size = os.path.getsize(a.file)
    count = a.count
    if count is None:
        foot = footprint(w, h, a.order, a.gfx)
        count = max(0, min(64, (size - a.offset - foot) // gb + 1)) if size - a.offset >= foot else 0
    with open(a.file, "rb") as fh:  # only the bytes drawn
        fh.seek(a.offset)
        data = fh.read((count - 1) * gb + footprint(w, h, a.order, a.gfx) if count else 0)  # through the last glyph
    glyphs = [decode(data, i * gb, w, h, a.order, a.lsb, a.invert, a.gfx) for i in range(count)]
    cols = a.cols or (8 if w > 12 else 16)
    if a.png:
        s, gap = a.scale, 1
        cw, ch = w * s + gap, h * s + gap
        nrow = (count + cols - 1) // cols
        W, H = cols * cw + gap, nrow * ch + gap
        pix = [[128] * W for _ in range(H)]
        for i, g in enumerate(glyphs):
            ox, oy = gap + (i % cols) * cw, gap + (i // cols) * ch
            for y in range(h):
                for x in range(w):
                    v = 0 if g[y][x] else 255
                    for yy in range(s):
                        row = pix[oy + y * s + yy]
                        for xx in range(s):
                            row[ox + x * s + xx] = v
        with open(a.png, "wb") as fh:
            fh.write(png_bytes(pix, W, H))
        print(f"wrote {a.png}: {count} glyphs of {w}x{h} from {a.offset:#x}, stride {gb}, {cols} a row, scale {s}")
        return
    for start in range(0, count, cols):
        part = glyphs[start:start + cols]
        print("  ".join(f"{start + i:<{w}d}"[:w] for i in range(len(part))))
        print("  ".join(f"{a.offset + (start + i) * gb:<#{w}x}"[:w] for i in range(len(part))))
        for y in range(h):
            print("  ".join("".join("#" if v else "." for v in g[y]) for g in part))
        print()


def tile_args(p):
    """--invert, --gfx and --bg: the options every glyph geometry takes (binscan.py and rawcarve.py)."""
    p.add_argument("--invert", action="store_true", help="ink is the 0 bits (or the background pens, with --gfx)")
    p.add_argument("--gfx", default=None, metavar="LAYOUT",
                   help="multi-bit tiles: a preset WxHxN_packed_lsb|msb or a MAME gfx_layout 'planes=..;x=..;y=..;inc=N' "
                   "(bit offsets; STEPn(a,b), RGN_FRAC(a,b) of the file); ink = pen != --bg (or in --fg)")
    p.add_argument("--bg", type=nonneg, default=None, metavar="PEN", help="--gfx: the background pen (0)")
    p.add_argument("--fg", type=pens, default=None, metavar="PEN[,PEN...]",
                   help="--gfx: ink is these pens only (instead of every pen but --bg; e.g. a glyph's body without its outline)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def scan_window(p):
        p.add_argument("--start", type=nonneg, default=0, help="scan from this file offset (0)")
        p.add_argument("--length", type=positive, default=None,
                       help=f"scan this many bytes (default: to the end; at most {MAX_SCAN})")

    def geometry(p, need_glyph=True):
        p.add_argument("--glyph", type=parse_glyph, default=None if need_glyph else (16, 16), metavar="WxH")
        p.add_argument("--stride", type=positive, default=None, metavar="B")
        p.add_argument("--order", choices=("rows", "strips", "cols", "bytecols"), default="rows")
        p.add_argument("--lsb", action="store_true", help="bit 0 is the left (or top) pixel")
        tile_args(p)

    p = sub.add_parser("info", help="size, kind, entropy, size signatures")
    p.add_argument("file")
    p.add_argument("--block", type=positive, default=4096)
    p.set_defaults(fn=cmd_info)

    p = sub.add_parser("runs", help="runs of glyph-like windows (--order strips for the Korean VGA font ROMs)")
    p.add_argument("file")
    geometry(p)
    p.add_argument("--min", type=positive, default=32, help="inked glyphs a run needs (32)")
    p.add_argument("--step", type=positive, default=None, help="phases tried within a glyph (default: one a row)")
    p.add_argument("--max-change", type=float, default=2.5,
                   help="mean pixels that change from row to row, per 8 columns (2.5)")
    scan_window(p)
    p.set_defaults(fn=cmd_runs)

    p = sub.add_parser("sets", help="raw jamo-piece fonts: offsets with blank fill slots")
    p.add_argument("file")
    p.add_argument("--sets", type=counts, default=(8, 4, 4), metavar="NI,NM,NF")
    p.add_argument("--slots", type=counts, default=(20, 22, 28),
                   metavar="SI,SM,SF", help="slots a set (20,22,28: slot 0 blank, then the 19/21/27 jamo)")
    geometry(p, need_glyph=False)
    p.add_argument("--min-inked", type=float, default=0.8)
    p.add_argument("--limit", type=positive, default=20)
    scan_window(p)
    p.set_defaults(fn=cmd_sets)

    p = sub.add_parser("ascii", help="8xH ASCII fonts")
    p.add_argument("file")
    p.add_argument("--invert", action="store_true", help="ink is the 0 bits")
    p.add_argument("--height", type=positive, default=16)
    p.add_argument("--limit", type=positive, default=20)
    scan_window(p)
    p.set_defaults(fn=cmd_ascii)

    p = sub.add_parser("render", help="draw glyphs at an offset")
    p.add_argument("file")
    p.add_argument("--offset", type=nonneg, default=0)
    geometry(p)
    p.add_argument("--count", type=bounded(4096), default=None, help="glyphs to draw (1..4096; default up to 64)")
    p.add_argument("--cols", type=bounded(64), default=None, help="glyphs a row of the picture (1..64)")
    p.add_argument("--png", default=None)
    p.add_argument("--scale", type=bounded(32), default=3, help="PNG pixels a glyph pixel (1..32)")
    p.set_defaults(fn=cmd_render)

    a = ap.parse_args(argv)
    if a.cmd == "sets" and (a.gfx is not None or a.bg is not None or a.fg is not None):
        ap.error("sets reads 1 bpp bytes: write the tiles' ink map with rawcarve.py ink first (no --gfx, --bg, --fg)")
    if a.cmd in ("runs", "render", "sets"):
        resolve_geometry(a, ap)
    if a.cmd == "runs" and a.step is None and a.gfx is not None:
        a.step = a.stride
    elif a.cmd == "runs" and a.step is None:
        a.step = (a.glyph[0] + 7) // 8 if a.order == "rows" else max(1, (a.glyph[1] + 7) // 8)
    a.fn(a)


if __name__ == "__main__":
    main()
