#!/usr/bin/env python3
"""The Python reference for the C renderer's line drawing (c/src/svf_draw.c, spec/renderer-design.md "Line drawing").

  svfline.py line W H X Y TEXT FACE...      writes the GRAY8 buffer (W*H bytes, row-major) of TEXT to stdout
  svfline.py measure TEXT FACE...           prints "width=W ascent=A descent=D"

Library use: layout(chain_paths, text, x, y_baseline, w, h) -> bytearray(w*h), measure(chain_paths, text) ->
(width, ascent, descent), and the targets: Target, to_target(gray, target), draw_target(placements, target, clip).
layout, measure and placements take scale=(num, den) (svf_chain.scale_num / scale_den; see "Scaling" below).
TEXT is a str (code points) or bytes (UTF-8, invalid sequences handled as below).

Faces are SVFN v3, read with jamoset.parse_svfn (v2 is read by tools/svf2to3.py only) and the engine's load rules, as the C library loads them: the dy range is used
only when valid (spec/SVF.md "Per-glyph dy", dy 0 outside it), a metrics table only when it fits the file after the
header, a JSET block only when jamoset.unpack takes it and every piece it names has a glyph (else the face is plain).

Line rules (engine-derived):
- UTF-8 is decoded with U+FFFD for each maximal invalid subpart (Python's errors="replace" and the Unicode
  recommendation): overlong forms, surrogates, code points past U+10FFFF and a truncated tail. An invalid subpart draws
  U+FFFD when a face of the chain has it, else it is skipped (no advance).
- Each code point is drawn by the first face of the chain that has it (svf_has: its code point table, or with a valid
  JSET any U+AC00..U+D7A3 and the compat jamo whose piece is not blank).
- A glyph's cell has its left column at the pen and its top row at y_baseline - ascent + dy (the face's ascent, the
  glyph's dy), so every face of the chain stands on one baseline.
- The pen advances by the metrics advance (a composed syllable: the JSET advance, or the cell width when it is 0; a face
  without a metrics table: the cell width).
- A combining mark (is_mark, default U+0300..U+036F) advances 0 and its cell is drawn at anchorX - originX: anchorX is
  the pen after the previous non-mark glyph (engine hires_text.cpp: _anchorX = drawX + originX + own), which in a line
  laid out here is always the current pen (a mark first in the line, or after a code point no face has, draws at the
  current pen too, as the engine's invalid anchor does); originX = min(-bearing_x, cell_w) when the face has flags bit
  2 and bearing_x < 0, else 0 (glyph_source_svfn.cpp).
- A code point no face of the chain has, mark or not, draws nothing and advances missing_advance (default 0).
- The pen saturates at 2**30 (no overflow for any length); measure's width saturates at 32767.
- GRAY8 coverage: 1 bpp ink 255, 2 bpp level k * 85, 8 bpp the byte; each pixel becomes max(existing, coverage), and
  only pixels inside the clip rectangle (default the whole buffer) intersected with [0, w) x [0, h) are written.
- Targets (svf_target, c/include/svf.h): each drawn cell sends its pixels with coverage > 0 inside the clip, row-major,
  to the target (Target.put: gray8 max, mono bits set at coverage >= threshold, rgb565/rgb555/xrgb8888/rgb888 bg/fg
  blend, indexed8 a palette index (index_level, max with the existing byte), gray: levels of gray_bits packed in rows, the
  max rule, cb a plot).
  to_target converts a GRAY8 buffer that way; draw_target draws cells that way, as the C library does.
- measure: width = the pen's travel; ascent / descent = the most rows any drawn cell reaches above / below the
  baseline (ascent - dy and cell_h - ascent + dy, so dy is included), 0 for a line that draws no cell.

Scaling (scale=(num, den), svf_chain.scale_num / scale_den): 0/0 is 1/1; otherwise num and den are each 1..16
(ValueError, the C library's SVF_E_ARG) and the ratio is reduced by their gcd.
- Lengths: S(v) = (v*num + den//2) // den for v >= 0 and -S(-v) for v < 0 (round half up, symmetric). Each advance
  (metrics advance, JSET advance, missing_advance) is S(advance) and the pen adds them, so the pen is in output pixels;
  a mark's origin is S(originX); a cell's top row is y_baseline - S(ascent) + S(dy) (the baseline row of the scaled
  cell is its scaled ascent). x and y_baseline are output pixels, never scaled.
- Cells: the scaled cell is ceil(cell_w*num/den) x ceil(cell_h*num/den) coverage pixels (scale_coverage). A whole
  multiple N (den 1 after reduction) draws each source pixel as an N x N block. Other ratios: output pixel (ox, oy)
  covers the source square [ox*den/num, (ox+1)*den/num) on each axis; its coverage is the area-weighted mean of the
  source coverage over that square (source outside the cell counts 0), in 16.16 fixed point rounded half up:
  ((sum << 16) // den**2 + 0x8000) >> 16, sum = the source coverages weighted by their overlap in 1/num pixel units
  (exact: the same as rounding the exact mean half up). An N x N block is that formula at den 1.
- The scaled cell is then drawn as any cell (8-bit coverage): clipped, its pixels with coverage > 0 sent row-major.
- measure: the width is the scaled pen travel; ascent - dy and cell_h - ascent + dy become S(ascent) - S(dy) and
  ceil(cell_h*num/den) - S(ascent) + S(dy).
"""

import codecs
import functools
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jamoset  # noqa: E402

PEN_MAX = 1 << 30
WIDTH_MAX = 32767
_INVALID_MARK = "\udfff"   # a lone surrogate: never the result of decoding valid UTF-8

codecs.register_error("svfline-invalid", lambda e: (_INVALID_MARK, e.end))


def is_mark_default(cp):
    return 0x300 <= cp <= 0x36F


def decode(text):
    """The code points of @p text (str, or bytes as UTF-8); None for each maximal invalid subpart of bytes."""
    if isinstance(text, str):
        return [ord(c) for c in text]
    return [None if c == _INVALID_MARK else ord(c) for c in bytes(text).decode("utf-8", "svfline-invalid")]


class Face:
    """One SVFN face as the C library loads it (see the module docstring)."""

    def __init__(self, data):
        self._init(jamoset.parse_svfn(data))

    @classmethod
    def from_svfn(cls, f, tables=None):
        """The face of a parsed SVFN (jamoset.Svfn); v2 input is parsed by tools/svf2to3.py only. @p tables: the
        jamoset.unpack of f.jset when the caller already has it (else it is unpacked here); the usable rule applies to
        either."""
        self = cls.__new__(cls)
        self._init(f, tables)
        return self

    def _init(self, f, tables=None):
        cw, ch, bpp = f.cell_w, f.cell_h, f.bpp
        self.flags, self.bpp, self.cell_w, self.cell_h, self.ascent = f.flags, bpp, cw, ch, f.ascent
        self.glyphs = f.glyphs
        self.has_metrics = f.metrics_ok
        self.raw_metrics, self.raw_dy = f.metrics, f.dy
        lo, hi = f.dy_min, f.dy_max
        if (lo or hi) and (not self.has_metrics or lo > 0 or hi < 0 or -lo > ch or hi > ch):
            lo = hi = 0
        self.dy_min, self.dy_max = lo, hi
        self.tables = None
        if f.jset is not None:
            t = tables
            if t is None:
                try:
                    t = jamoset.unpack(f.jset)
                except ValueError:
                    t = None
            if t and all(n == jamoset.BLANK or jamoset.PIECE_BASE + n in f.glyphs
                         for n in t.init_piece + t.med_piece + t.fin_piece + t.compat):
                self.tables = t
        self.pitch = (cw * bpp + 7) // 8

    @staticmethod
    @functools.lru_cache(maxsize=None)
    def load(path):
        with open(path, "rb") as fh:
            return Face(fh.read())

    def compat_piece(self, cp):
        if self.tables and 0x3131 <= cp <= 0x3163 and self.tables.compat[cp - 0x3131] != jamoset.BLANK:
            return self.tables.compat[cp - 0x3131]
        return None

    def composed(self, cp):
        if not self.tables:
            return False
        if 0xAC00 <= cp <= 0xD7A3:      # a JMAP-only miss is not composed (PR-5): the cmap glyph or none, as a plain face
            return jamoset.pieces_of(self.tables, cp) is not None
        return self.compat_piece(cp) is not None

    def has(self, cp):
        return self.composed(cp) or cp in self.glyphs

    def metrics(self, cp):
        """(advance, bearing_x, ink_w, dy) as svf_metrics_of."""
        if self.composed(cp):
            return (self.tables.advance or self.cell_w, 0, self.cell_w, 0)
        if not self.has_metrics:
            return (self.cell_w, 0, self.cell_w, 0)
        adv, bx, iw = self.raw_metrics[cp]
        dy = self.raw_dy.get(cp, 0)
        return (adv, bx, iw, dy if self.dy_min <= dy <= self.dy_max else 0)

    def cell(self, cp):
        if 0xAC00 <= cp <= 0xD7A3 and self.composed(cp):
            return jamoset.compose(self, self.tables, cp)
        piece = self.compat_piece(cp)
        if piece is not None:
            return self.glyphs[jamoset.PIECE_BASE + piece]
        return self.glyphs[cp]

    def coverage(self, cp):
        """The cell of @p cp as rows of coverage 0..255."""
        cell, p = self.cell(cp), self.pitch
        rows = []
        for y in range(self.cell_h):
            row = cell[y * p:(y + 1) * p]
            if self.bpp == 1:
                rows.append([255 if row[x >> 3] >> (7 - (x & 7)) & 1 else 0 for x in range(self.cell_w)])
            elif self.bpp == 2:
                rows.append([(row[x >> 2] >> (6 - 2 * (x & 3)) & 3) * 85 for x in range(self.cell_w)])
            else:
                rows.append(list(row[:self.cell_w]))
        return rows


def scale_ratio(scale):
    """(num, den) of @p scale reduced by their gcd; 0/0 is 1/1; ValueError unless num and den are 1..16."""
    num, den = scale
    if (num, den) == (0, 0):
        return 1, 1
    if not (1 <= num <= 16 and 1 <= den <= 16):
        raise ValueError("scale %d/%d: num and den must be 1..16" % (num, den))
    g = math.gcd(num, den)
    return num // g, den // g


def scale_len(v, num, den):
    """A length @p v scaled by num/den: (v*num + den//2) // den, rounded half up, symmetric for negative values."""
    return (v * num + den // 2) // den if v >= 0 else -((-v * num + den // 2) // den)


def scaled_dim(v, num, den):
    """ceil(v * num / den): the scaled cell's width or height."""
    return -(-v * num // den)


def scale_coverage(rows, num, den):
    """The coverage rows @p rows (h rows of w values 0..255) scaled by num/den (see "Scaling" in the module doc)."""
    h, w = len(rows), len(rows[0]) if rows else 0
    sw, sh = scaled_dim(w, num, den), scaled_dim(h, num, den)
    if den == 1:
        return [[rows[oy // num][ox // num] for ox in range(sw)] for oy in range(sh)]

    def spans(o, n):
        # (source index, overlap in 1/num pixel units) of output pixel o over a source axis of n pixels
        lo, hi = o * den, (o + 1) * den
        return [(s, min((s + 1) * num, hi) - max(s * num, lo)) for s in range(lo // num, min((hi - 1) // num + 1, n))]

    out = []
    for oy in range(sh):
        ys = spans(oy, h)
        row = []
        for ox in range(sw):
            total = sum(rows[sy][sx] * wx * wy for sy, wy in ys for sx, wx in spans(ox, w))
            row.append(((total << 16) // (den * den) + 0x8000) >> 16)
        out.append(row)
    return out


class Scaled:
    """A face seen through a scale: cell_w / cell_h / coverage of the scaled cell (what cell_pixels draws)."""

    def __init__(self, face, num, den):
        self.face, self.num, self.den = face, num, den
        self.cell_w, self.cell_h = scaled_dim(face.cell_w, num, den), scaled_dim(face.cell_h, num, den)

    def coverage(self, cp):
        return scale_coverage(self.face.coverage(cp), self.num, self.den)


def load_chain(chain_paths):
    return [Face.load(p) for p in chain_paths]


def _walk(chain, text, is_mark, missing_advance, num=1, den=1):
    """Yields (face, cp, pen offset of the cell's left column, dy) per drawn cell, scaled by num/den (scale_len);
    returns the pen's travel."""
    fffd = any(f.has(0xFFFD) for f in chain)
    pen = 0
    for cp in decode(text):
        if cp is None:
            if not fffd:
                continue
            cp = 0xFFFD
        face = next((f for f in chain if f.has(cp)), None)
        if face is None:
            pen = min(pen + scale_len(missing_advance, num, den), PEN_MAX)
            continue
        adv, bx, _, dy = face.metrics(cp)
        dy = scale_len(dy, num, den)
        if is_mark(cp):
            origin = min(-bx, face.cell_w) if face.flags & jamoset.FLAG_MARKS_AT_ORIGIN and bx < 0 else 0
            yield face, cp, pen - scale_len(origin, num, den), dy
        else:
            yield face, cp, pen, dy
            pen = min(pen + scale_len(adv, num, den), PEN_MAX)
    return pen


def placements(chain, text, x, y_baseline, is_mark=is_mark_default, missing_advance=0, scale=(1, 1)):
    """[(face, cp, cell left x, cell top y)] of @p text on the faces @p chain (Face objects), in drawing order; with a
    scale other than 1/1 each face is a Scaled view of it."""
    num, den = scale_ratio(scale)
    out = []
    for face, cp, dx, dy in _walk(chain, text, is_mark, missing_advance, num, den):
        top = y_baseline - scale_len(face.ascent, num, den) + dy
        out.append((face if (num, den) == (1, 1) else Scaled(face, num, den), cp, x + dx, top))
    return out


def _clip_rect(w, h, clip):
    """The clip rectangle in force: @p clip (x0, y0, x1, y1, half-open) or the whole target, within [0, w) x [0, h)."""
    x0, y0, x1, y1 = clip if clip is not None else (0, 0, w, h)
    return max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)


def cell_pixels(place, w, h, clip=None):
    """The (x, y, coverage) of one placed cell with coverage > 0 inside the clip, row-major: what the cell sends to a
    target."""
    face, cp, cx, top = place
    x0, y0, x1, y1 = _clip_rect(w, h, clip)
    if cx >= x1 or top >= y1 or cx + face.cell_w <= x0 or top + face.cell_h <= y0:
        return
    for r, row in enumerate(face.coverage(cp)):
        y = top + r
        if not y0 <= y < y1:
            continue
        for c, cov in enumerate(row):
            if cov and x0 <= cx + c < x1:
                yield cx + c, y, cov


def draw_gray8(places, w, h, clip=None):
    buf = bytearray(w * h)
    for place in places:
        for x, y, cov in cell_pixels(place, w, h, clip):
            if cov > buf[y * w + x]:
                buf[y * w + x] = cov
    return buf


# ---- targets (svf_target) -------------------------------------------------------------------------------------------

TARGET_KINDS = ("gray8", "mono-page", "mono-row", "rgb565", "cb", "indexed8", "rgb555", "xrgb8888", "rgb888", "gray")
LATER_CELL_KINDS = {"rgb565", "rgb555", "xrgb8888", "rgb888"}   # a later cell's pixel replaces the earlier one
RGB16_KINDS = {"rgb565", "rgb555"}


def target_row_bytes(kind, w, gray_bits=8):
    """The least stride of a target of @p kind, @p w pixels wide (cb: 0, it has no buffer); @p gray_bits only for gray."""
    return {"gray": (w * gray_bits + 7) // 8, "gray8": w, "mono-page": w, "mono-row": (w + 7) // 8, "rgb565": 2 * w, "cb": 0, "indexed8": w,
            "rgb555": 2 * w, "xrgb8888": 4 * w, "rgb888": 3 * w}[kind]


def target_rows(kind, h):
    """The rows of stride bytes a target of @p kind, @p h pixels high, holds (8-row pages for mono-page)."""
    return (h + 7) // 8 if kind == "mono-page" else 0 if kind == "cb" else h


def index_level(cov, levels, threshold):
    """The INDEXED8 ramp level of coverage @p cov: (cov * levels + 127) // 255 for levels >= 2; for levels == 1, 1 when
    cov >= max(threshold, 1) else 0 (the mono rule). levels < 1 is invalid (ValueError; the C library refuses such a
    target with SVF_E_ARG)."""
    if levels < 1:
        raise ValueError("index_levels must be >= 1")
    if levels == 1:
        return 1 if cov >= max(threshold, 1) else 0
    return (cov * levels + 127) // 255


def _blend(fg, bg, cov, channels):
    out = 0
    for shift, mask in channels:
        b, f = bg >> shift & mask, fg >> shift & mask
        out |= (b * (255 - cov) + f * cov + 127) // 255 << shift
    return out


def blend565(fg, bg, cov):
    """bg and fg blended by @p cov per 5/6/5 channel: (c_bg * (255 - cov) + c_fg * cov + 127) // 255."""
    return _blend(fg, bg, cov, ((11, 31), (5, 63), (0, 31)))


def blend555(fg, bg, cov):
    """The low 15 bits of bg and fg (5/5/5) blended by @p cov: blend565's arithmetic on three 5-bit channels."""
    return _blend(fg, bg, cov, ((10, 31), (5, 31), (0, 31)))


def blend888(fg, bg, cov):
    """0xRRGGBB of bg and fg blended by @p cov per 8-bit channel: (c_bg * (255 - cov) + c_fg * cov + 127) // 255."""
    return _blend(fg, bg, cov, ((16, 255), (8, 255), (0, 255)))


class Target:
    """A target as svf_target: @p buf (a bytearray of rows * stride bytes, any content) is changed in place by put;
    a cb target collects (x, y, cov) in plots."""

    def __init__(self, kind, w, h, stride=None, buf=None, fg565=0xFFFF, bg565=0, threshold=128, big_endian=False,
                 index_base=0, index_levels=255, fg888=0xFFFFFF, bg888=0, gray_bits=8, lsb_first=False):
        if gray_bits not in (1, 2, 4, 8):
            raise ValueError("gray_bits must be 1, 2, 4 or 8")
        self.kind, self.w, self.h = kind, w, h
        self.gray_bits, self.lsb_first = gray_bits, lsb_first
        self.stride = target_row_bytes(kind, w, gray_bits) if stride is None else stride
        self.buf = bytearray(target_rows(kind, h) * self.stride) if buf is None else buf
        self.fg565, self.bg565, self.threshold, self.big_endian = fg565, bg565, threshold, big_endian
        self.index_base, self.index_levels, self.fg888, self.bg888 = index_base, index_levels, fg888, bg888
        self.plots = []

    def put(self, x, y, cov):
        """One pixel of coverage @p cov > 0 sent to the target (the conversion rules of svf.h)."""
        k, b = self.kind, self.buf
        if k == "gray8":
            b[y * self.stride + x] = max(b[y * self.stride + x], cov)
        elif k == "mono-page":
            if cov >= self.threshold:
                b[(y >> 3) * self.stride + x] |= 1 << (y & 7)
        elif k == "mono-row":
            if cov >= self.threshold:
                b[y * self.stride + (x >> 3)] |= 0x80 >> (x & 7)
        elif k == "rgb565":
            c = blend565(self.fg565, self.bg565, cov)
            i = y * self.stride + 2 * x
            b[i:i + 2] = c.to_bytes(2, "big" if self.big_endian else "little")
        elif k == "indexed8":
            level = index_level(cov, self.index_levels, self.threshold)
            i = y * self.stride + x
            if level:
                b[i] = max(b[i], self.index_base + level)
        elif k == "gray":
            bits = self.gray_bits
            ppb = 8 // bits
            i = y * self.stride + (x * bits >> 3)
            s = bits * (x % ppb) if self.lsb_first else 8 - bits * (x % ppb + 1)
            mask = (1 << bits) - 1
            level = index_level(cov, mask, self.threshold)
            if level > (b[i] >> s & mask):
                b[i] = b[i] & ~(mask << s) | level << s
        elif k == "rgb555":
            c = (self.fg565 & 0x8000) | blend555(self.fg565 & 0x7FFF, self.bg565 & 0x7FFF, cov)
            i = y * self.stride + 2 * x
            b[i:i + 2] = c.to_bytes(2, "big" if self.big_endian else "little")
        elif k in ("xrgb8888", "rgb888"):
            c = blend888(self.fg888 & 0xFFFFFF, self.bg888 & 0xFFFFFF, cov)
            px = bytes((c & 255, c >> 8 & 255, c >> 16 & 255))
            if k == "xrgb8888":
                i = y * self.stride + 4 * x
                b[i:i + 4] = px + bytes((self.fg888 >> 24 & 255,))
            else:
                i = y * self.stride + 3 * x
                b[i:i + 3] = px
        else:
            self.plots.append((x, y, cov))


def to_target(gray, target):
    """@p gray (a GRAY8 buffer of target.w * target.h coverage bytes) converted onto @p target: every pixel with
    coverage > 0, row-major, through Target.put. Returns the target."""
    w = target.w
    for i, cov in enumerate(gray):
        if cov:
            target.put(i % w, i // w, cov)
    return target


def draw_target(places, target, clip=None):
    """The cells of @p places drawn on @p target as svf_draw_utf8 draws them: each cell in turn sends its pixels
    (cell_pixels: coverage > 0, inside the clip, row-major) to the target. Returns the target. For gray8, gray (the
    max rule on levels) and the mono kinds, and indexed8 (max rule), this is to_target of the line's GRAY8 buffer; for the LATER_CELL_KINDS and cb it is
    too unless two cells give one pixel different coverage (a later cell's pixel replaces the earlier one; cb gets one
    call per cell)."""
    for place in places:
        for x, y, cov in cell_pixels(place, target.w, target.h, clip):
            target.put(x, y, cov)
    return target


def layout(chain_paths, text, x, y_baseline, w, h, is_mark=is_mark_default, missing_advance=0, clip=None,
           scale=(1, 1)):
    """The GRAY8 buffer (w*h bytes, row-major) of @p text drawn from (x, y_baseline) over the faces at @p chain_paths,
    only pixels inside @p clip (x0, y0, x1, y1; default the whole buffer) written."""
    return draw_gray8(placements(load_chain(chain_paths), text, x, y_baseline, is_mark, missing_advance, scale),
                      w, h, clip)


def measure(chain_paths, text, is_mark=is_mark_default, missing_advance=0, scale=(1, 1)):
    """(width, ascent, descent) of @p text as svf_measure_utf8."""
    num, den = scale_ratio(scale)
    it = _walk(load_chain(chain_paths), text, is_mark, missing_advance, num, den)
    ascent = descent = 0
    while True:
        try:
            face, _, _, dy = next(it)
        except StopIteration as stop:
            return min(stop.value, WIDTH_MAX), ascent, descent
        a = scale_len(face.ascent, num, den)
        ascent = max(ascent, a - dy)
        descent = max(descent, scaled_dim(face.cell_h, num, den) - a + dy)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    text = lambda s: os.fsencode(s)  # noqa: E731 - the argument's bytes, invalid UTF-8 included
    if len(argv) >= 7 and argv[0] == "line":
        w, h, x, y = (int(v) for v in argv[1:5])
        sys.stdout.buffer.write(layout(argv[6:], text(argv[5]), x, y, w, h))
        return 0
    if len(argv) >= 3 and argv[0] == "measure":
        print("width=%d ascent=%d descent=%d" % measure(argv[2:], text(argv[1])))
        return 0
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
