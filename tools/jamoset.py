#!/usr/bin/env python3
"""Build a jamo-set SVF (SVFN flag bit 1 + JSET block) from a DOS Johab font.

A DOS Hangul system held no syllables, only positional jamo pieces (initial,
medial, final) in sets, and drew a syllable as the OR of two or three of them.
This tool writes such a font for the engine (graphics/hires_text/README.md,
"Jamo-set fonts"): the pieces become glyphs at U+F0000 + n and a JSET block
says, per syllable, which pieces to take. Every set system the research
documents is a named layout (docs/johab/2026-10-14-johab-font-research.md
section 3, docs/johab/2026-10-14-johab-font-formats.md section 2):

  844              8x4x4, the DOS standard (iolo, san, HMJ, $K*ZN16; 16/24/40/48 px)
  844-ihnm         8x4x4 with medial sets 1/3 for initials g and k (SAGA IHNM)
  844-hbios24      the jamo half of a 24x30 HBIOS / Taebaek 3.5 face ($KMYZN24, GOTHIC24, MY24, PILGI24; 243,900 bytes)
  1044-san         10x4x4 of san-1.0 (12,800 bytes)
  621              6x2x1, Apple II (6,144 bytes, byte-column glyphs)
  hanterm-johab    hanterm johab-1 BDF, 10x(3|4)x4
  dkb-printer-7x2x2    Dokkaebi printer HANGUL16/24.FNT (--face 0|1)
  dkb-printer-12x4x4   Dokkaebi printer HANGUL40/48.FNT (--face 0|1)
  kyra-lok         Kyra LoK MK15.BIT, jamo-major 10x4x4, 15x15

  python3 jamoset.py --layout 844 GAM.KOR --eng SAN.ENG -o KOGAMJ.SVF --check
  python3 jamoset.py --layout dkb-printer-12x4x4 --face 1 HANGUL48.FNT -o DKB48J.SVF

Only pieces some syllable (or compatibility jamo) uses are written, numbered
in source order. ASCII comes from --eng (a raw 8x16 DOS English font, row
major, 2048 or 4096 bytes; scaled by whole numbers to the cell) and/or --base
(an SVFN whose glyphs, other than syllables, are kept). Compatibility jamo
U+3131..U+3163 are drawn by piece: an initial's set-0 piece, a vowel's set-0
medial, a final-only consonant's set-0 final.

The raw-file readers and the selection tables come from the research tools in
the johab-fonts research tools' kfont.py (g_rowmajor, g_bytecols, g_bitcols, open_*,
sel_*) and dkb_fnt.py, copied here as data and small functions.
"""

import argparse
import collections
import os
import re
import struct
import sys
import time

# ---- SVFN / JSET constants (graphics/hires_text/README.md) -------------------

MAGIC = b"SVFN"
VERSION = 3
# v3 (docs/superpowers/specs/2026-10-21-svf-v3-design.md): 48 bytes, bytes 9/10 are the layout bytes, 11 reserved.
HEADER3 = "<4sHHBBBBHBBBbbBIIIIIII"
HEADER3_SIZE = 48
FLAG_VARIABLE = 1 << 0
FLAG_JAMO = 1 << 1
FLAG_MARKS_AT_ORIGIN = 1 << 2
PIECE_BASE = 0xF0000
BLANK = 0xFFFF
JSET_HEADER = 16
# The engine's JSET class limits (graphics/hires_text/jamo_set.h; 8 and 8 before 2026-10, and engines built then
# reject a block with more), and its set limits.
MAX_LEAD_CLASSES = 12
MAX_TAIL_CLASSES = 12
# The JSET count limits (lead classes, tail classes, initial / medial / final sets): the standard row, and the BIG row
# (SVF_JSET_BIG, PR-16: unpack reads both always, writers refuse BIG counts unless --jset-big / big=True).
JSET_LIMITS = {"std": (12, 12, 32, 24, 16), "big": (19, 28, 128, 128, 64)}

# ---- Johab jamo helpers (kfont.py) -------------------------------------------

JUNG_FIELD = (3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 22, 23, 26, 27, 28, 29)  # V -> 5-bit value
KK = (0, 15)  # initials g and k; gg is NOT in the group

# Initial set by vowel (ㅏ..ㅣ) without and with a final; final set by vowel (research doc 3.2).
I844_NOFIN = (0, 0, 0, 0, 0, 0, 0, 0, 1, 3, 3, 3, 1, 2, 4, 4, 4, 2, 1, 3, 0)
I844_FIN = (5, 5, 5, 5, 5, 5, 5, 5, 6, 7, 7, 7, 6, 6, 7, 7, 7, 6, 6, 7, 5)
F844 = (0, 2, 0, 2, 1, 2, 1, 2, 3, 0, 2, 1, 3, 3, 1, 2, 1, 3, 3, 1, 1)
# iolo 6x2x1-fonts generate_hangul_syllables.py
I621_NOFIN = (0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 2, 2, 1, 1, 2, 2, 2, 1, 1, 2, 0)
I621_FIN = (3, 3, 3, 3, 3, 3, 3, 3, 4, 5, 5, 5, 4, 4, 5, 5, 5, 4, 4, 5, 3)
# hanterm-xf hfont.c convert_3_to_johabfont(): tables indexed by the 5-bit Johab medial / final value
HT_FCON1 = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 3, 3, 0, 0, 3, 1, 2, 4, 4, 4, 0, 0, 2, 1, 3, 0)
HT_FCON2 = (0, 0, 5, 5, 5, 5, 5, 5, 0, 0, 5, 5, 5, 6, 8, 8, 0, 0, 8, 6, 7, 9, 9, 9, 0, 0, 7, 6, 8, 5)
HT_VBASE = (0, 0, 0, 311, 314, 317, 320, 323, 0, 0, 326, 329, 332, 335, 339, 343, 0, 0, 347, 351, 355, 358, 361, 364,
            0, 0, 367, 370, 374, 378)
HT_VKIND = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0)
# Final variant by medial value: lcon_map[] of hanterm's own source (hfont.c in hanterm-xf 2.0.0/2.0.6, hangul.c in
# hanterm 3.1-3.3.1p18: identical in all seven). It is not the 8x4x4 final table F844: wae, oe, we, ui (15, 18, 22, 28)
# are 0, 0, 1, 0 here.
HT_LMAP = (0, 0, 0, 0, 2, 0, 2, 1, 0, 0, 2, 1, 2, 3, 0, 0, 0, 0, 0, 3, 3, 1, 1, 1, 0, 0, 3, 3, 0, 1)
# Dokkaebi printer fonts (dkb_fnt.py, from DP09/DP24/DP40/DP48.COM)
P16_INIT0 = [0] * 8 + [1, 3, 3, 3, 1, 2, 3, 3, 3, 2, 1, 3, 0]
P16_INIT1 = [4] * 8 + [5, 6, 6, 6, 5, 5, 6, 6, 6, 5, 5, 6, 4]
P16_FIN = [0] * 8 + [1] * 12 + [0]
P40_CLASS = [0, 1, 0, 1, 0, 1, 0, 1, 2, 4, 5, 4, 2, 3, 4, 5, 4, 3, 2, 4, 0]

# Compatibility jamo U+3131.. : (kind, index) with kind i = initial L, v = vowel V, f = final-only T.
COMPAT = ([("i", 0), ("i", 1), ("f", 3), ("i", 2), ("f", 5), ("f", 6), ("i", 3), ("i", 4), ("i", 5),
           ("f", 9), ("f", 10), ("f", 11), ("f", 12), ("f", 13), ("f", 14), ("f", 15), ("i", 6), ("i", 7),
           ("i", 8), ("f", 18), ("i", 9), ("i", 10), ("i", 11), ("i", 12), ("i", 13), ("i", 14), ("i", 15),
           ("i", 16), ("i", 17), ("i", 18)]
          + [("v", v) for v in range(21)])


# ---- glyph bitmaps: rows are ints, bit (w-1-x) is pixel x (MSB = left) ----------

class Glyph:
    __slots__ = ("w", "h", "rows")

    def __init__(self, w, h, rows):
        self.w, self.h, self.rows = w, h, rows

    def to_bytes(self):
        """Rows packed MSB first, padded to a byte: the SVFN 1bpp layout."""
        nb = (self.w + 7) // 8
        return b"".join((r << (nb * 8 - self.w)).to_bytes(nb, "big") for r in self.rows)

    def ink(self):
        cols = 0
        for r in self.rows:
            cols |= r
        used = [x for x in range(self.w) if cols >> (self.w - 1 - x) & 1]
        return (used[0], used[-1] - used[0] + 1) if used else (0, 0)


def g_rowmajor(d, off, w, h, bpr=None):
    bpr = bpr or (w + 7) // 8
    sh = bpr * 8 - w
    return Glyph(w, h, [int.from_bytes(d[off + y * bpr:off + (y + 1) * bpr], "big") >> sh for y in range(h)])


def g_bytecols(d, off, w, h):
    """Column-of-bytes order (iolo 6x2x1, Apple II)."""
    nb = (w + 7) // 8
    rows = [0] * h
    for x in range(nb):
        for y in range(h):
            rows[y] |= d[off + x * h + y] << (8 * (nb - 1 - x))
    return Glyph(w, h, [r >> (nb * 8 - w) for r in rows])


def g_bitcols(d, off, px):
    """Column-major, MSB = top (Dokkaebi HANGUL16/24 printer fonts)."""
    bpc = (px + 7) // 8
    rows = [0] * px
    for c in range(px):
        v = int.from_bytes(d[off + c * bpc:off + (c + 1) * bpc], "big")
        for r in range(px):
            if v >> (bpc * 8 - 1 - r) & 1:
                rows[r] |= 1 << (px - 1 - c)
    return Glyph(px, px, rows)


class SourceError(Exception):
    pass


class Source:
    """A source font's pieces: cell size and glyph(i) by the file's own piece index."""

    def __init__(self, w, h, count, getter):
        self.w, self.h, self.count, self._get = w, h, count, getter

    def glyph(self, i):
        if not 0 <= i < self.count:
            raise SourceError(f"piece {i} is outside the source's {self.count} glyphs")
        return self._get(i)


def check_blank_slots(d, off, gb, slots):
    bad = [i for i in slots if any(d[off + i * gb:off + (i + 1) * gb])]
    if len(bad) > 2:
        raise SourceError(f"not this layout: fill slots {bad[:4]} are not blank")


def slots_of(nini, nmed, nfin, med0, fin0):
    return ([s * 20 for s in range(nini)] + [med0 + s * 22 for s in range(nmed)]
            + [fin0 + s * 28 for s in range(nfin)])


def open_raw844(d, face=0, path=""):
    """Raw 8x4x4: 11520 (16x16), +2 B header (11522, T-Hangul), 25920 (24), 72000 (40), 103680 (48), 15584 (DKB2)."""
    px = {11520: 16, 11522: 16, 25920: 24, 72000: 40, 103680: 48, 15584: 16}.get(len(d))
    if px is None:
        raise SourceError(f"size {len(d)} is not an 8x4x4 size")
    off = 2 if len(d) == 11522 else 0
    gb = ((px + 7) // 8) * px
    check_blank_slots(d, off, gb, slots_of(8, 4, 4, 160, 248))
    return Source(px, px, 360, lambda i: g_rowmajor(d, off + i * gb, px, px))


def open_hbios24(d, face=0, path=""):
    """The jamo half of an IBM HBIOS / Taebaek 3.5 24 px face ($KMYZN24.FNT, GOTHIC24.FNT, MY24.FNT, PILGI24.FNT, 243,900
    bytes): 2,710 glyphs of 90 bytes (24 wide, 3 bytes a row, a 30 row cell with the ink in rows 3-26), the first 360 an
    8x4x4 set; the 2,350 syllables after them are not read."""
    if len(d) != 243900:
        raise SourceError(f"size {len(d)} is not an HBIOS 24x30 face (243900)")
    check_blank_slots(d, 0, 90, slots_of(8, 4, 4, 160, 248))
    return Source(24, 24, 360, lambda i: Glyph(24, 24, g_rowmajor(d, i * 90, 24, 30).rows[3:27]))


def open_ihnm(d, face=0, path=""):
    """SAGA IHNM's 8x4x4: the 360 jamo glyphs (11,520 bytes, 16x16) may be followed by other glyphs, which are ignored."""
    if len(d) < 360 * 32:
        raise SourceError(f"size {len(d)} is shorter than the 11520 bytes of 360 16x16 jamo glyphs")
    check_blank_slots(d, 0, 32, slots_of(8, 4, 4, 160, 248))
    return Source(16, 16, 360, lambda i: g_rowmajor(d, i * 32, 16, 16))


def open_1044(d, face=0, path=""):
    if len(d) != 12800:
        raise SourceError("10x4x4 san needs 12800 bytes")
    check_blank_slots(d, 0, 32, slots_of(10, 4, 4, 200, 288))
    return Source(16, 16, 400, lambda i: g_rowmajor(d, i * 32, 16, 16))


def open_621(d, face=0, path=""):
    if len(d) != 6144:
        raise SourceError("6x2x1 needs 6144 bytes")
    return Source(16, 16, 192, lambda i: g_bytecols(d, i * 32, 16, 16))


def open_kyra(d, face=0, path=""):
    if len(d) != 11550:
        raise SourceError("MK15.BIT needs 11550 bytes")
    return Source(15, 15, 385, lambda i: g_rowmajor(d, i * 30, 15, 15, 2))


def open_dkb16(d, face=0, path=""):
    """HANGUL16/24.FNT: two faces of 240 glyphs, column-major."""
    px = {15360: 16, 34560: 24}.get(len(d))
    if px is None:
        raise SourceError(f"size {len(d)} is not a Dokkaebi 7x2x2 printer font (15360 or 34560)")
    if face not in (0, 1):
        raise SourceError("--face is 0 or 1")
    gb = ((px + 7) // 8) * px
    return Source(px, px, 240, lambda i: g_bitcols(d, (face * 240 + i) * gb, px))


def open_dkb40(d, face=0, path=""):
    """HANGUL40/48.FNT: two faces of 440 glyphs, row-major."""
    px = {176000: 40, 253440: 48}.get(len(d))
    if px is None:
        raise SourceError(f"size {len(d)} is not a Dokkaebi 12x4x4 printer font (176000 or 253440)")
    if face not in (0, 1):
        raise SourceError("--face is 0 or 1")
    gb = ((px + 7) // 8) * px
    return Source(px, px, 440, lambda i: g_rowmajor(d, (face * 440 + i) * gb, px, px))


def open_bdf_glyphs(d, face=0, path=""):
    """A hanterm BDF whose ENCODING is the glyph number (johab-1); cells are the font's box."""
    t = d.decode("latin-1")
    if not t.startswith("STARTFONT"):
        raise SourceError("not a BDF")
    fb = re.search(r"FONTBOUNDINGBOX\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)", t)
    if not fb:
        raise SourceError("BDF without FONTBOUNDINGBOX")
    w, bh, _, by0 = map(int, fb.groups())
    asc = re.search(r"FONT_ASCENT\s+(\d+)", t)
    desc = re.search(r"FONT_DESCENT\s+(\d+)", t)
    ascent = int(asc.group(1)) if asc else bh + by0
    h = ascent + (int(desc.group(1)) if desc else -by0)
    chars = {}
    for block in t.split("STARTCHAR")[1:]:
        block = block.split("ENDCHAR")[0]
        enc = re.search(r"^ENCODING\s+(-?\d+)", block, re.M)
        if not enc:
            raise SourceError("BDF glyph without ENCODING")
        enc = int(enc.group(1))
        bbx = re.search(r"^BBX\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)", block, re.M)
        bm = re.search(r"^BITMAP[ \t]*\n(.*)", block, re.M | re.S)
        if not bbx or not bm:
            raise SourceError(f"BDF glyph {enc} has no BBX or BITMAP")
        bw, bhh, bx, by = map(int, bbx.groups())
        nb = (bw + 7) // 8
        lines = bm.group(1).split()
        if len(lines) < bhh or any(len(x) < nb * 2 for x in lines[:bhh]):
            raise SourceError(f"BDF glyph {enc}: BITMAP has {len(lines)} of {bhh} rows")
        chars[enc] = (bw, bhh, bx, by, [int(x[:nb * 2], 16) >> (nb * 8 - bw) for x in lines[:bhh]])
    missing = [i for i in range(529) if i not in chars]
    if missing:
        raise SourceError(f"BDF lacks glyph ENCODING {missing[0]} of the 529 johab-1 glyphs ({len(missing)} missing)")

    def get(i):
        c = chars.get(i)
        out = [0] * h
        if c:
            bw, bhh, bx, by, rows = c
            top = ascent - (by + bhh)
            for k, r in enumerate(rows):
                y = top + k
                if 0 <= y < h:
                    sh = w - (bx + bw)
                    out[y] = (r << sh) if sh >= 0 else (r >> -sh)
        return Glyph(w, h, out)

    return Source(w, h, 529, get)


# ---- layouts ----------------------------------------------------------------

class Layout:
    """A set system: classes, set selection per (lead class, vowel, tail class), source glyph per (set, jamo).

    A *_src function returns the source font's own glyph index, or None for a blank piece.
    """

    def __init__(self, name, opener, lc, tc, ni, nm, nf, lead_class, tail_class, init_set, med_set, fin_set,
                 init_src, med_src, fin_src, advance=0):
        self.name, self.opener = name, opener
        self.lc, self.tc, self.ni, self.nm, self.nf = lc, tc, ni, nm, nf
        self.lead_class, self.tail_class = lead_class, tail_class
        self.init_set, self.med_set, self.fin_set = init_set, med_set, fin_set
        self.init_src, self.med_src, self.fin_src = init_src, med_src, fin_src
        self.advance = advance


def _kk_class(L):
    return 0 if L in KK else 1


def _has_tail(T):
    return 1 if T else 0


def _844(name, flip, opener=None):
    """8x4x4; flip=1 swaps the medial sets of initials g/k and the rest (IHNM)."""
    return Layout(name, opener or (open_ihnm if flip else open_raw844), 2, 2, 8, 4, 4, _kk_class, _has_tail,
                  lambda lc, v, tc: (I844_FIN if tc else I844_NOFIN)[v],
                  lambda lc, v, tc: (lc ^ flip) + 2 * tc,
                  lambda lc, v, tc: F844[v] if tc else 0,
                  lambda s, L: s * 20 + L + 1,
                  lambda s, V: 160 + s * 22 + V + 1,
                  lambda s, T: 248 + s * 28 + T)


def _san1044():
    return Layout("1044-san", open_1044, 2, 2, 10, 4, 4, _kk_class, _has_tail,
                  lambda lc, v, tc: I844_NOFIN[v] + (5 if tc else 0),
                  lambda lc, v, tc: lc + 2 * tc,
                  lambda lc, v, tc: F844[v] if tc else 0,
                  lambda s, L: s * 20 + L + 1,
                  lambda s, V: 200 + s * 22 + V + 1,
                  lambda s, T: 288 + s * 28 + T)


def _621():
    return Layout("621", open_621, 1, 2, 6, 2, 1, lambda L: 0, _has_tail,
                  lambda lc, v, tc: (I621_FIN if tc else I621_NOFIN)[v],
                  lambda lc, v, tc: tc,
                  lambda lc, v, tc: 0,
                  lambda s, L: s * 20 + L + 1,
                  lambda s, V: 120 + s * 22 + V + 1,
                  lambda s, T: 164 + T)


def _kyra():
    return Layout("kyra-lok", open_kyra, 2, 2, 10, 4, 4, _kk_class, _has_tail,
                  lambda lc, v, tc: 2 * I844_NOFIN[v] + tc,
                  lambda lc, v, tc: 2 * lc + tc,
                  lambda lc, v, tc: F844[v] if tc else 0,
                  lambda s, L: 1 + 10 * L + s,
                  lambda s, V: 192 + 4 * V + s,
                  lambda s, T: 277 + 4 * (T - 1) + s,
                  advance=16)


def _hanterm():
    def tail_class(T):
        return 0 if T == 0 else (1 if T == 4 else 2)	# none, g-n (the nieun final), other

    def med_set(lc, v, tc):
        m = JUNG_FIELD[v]
        if HT_VKIND[m]:
            return (0 if lc == 0 else 1) + (2 if tc else 0)
        return (0, 2, 1)[tc]			# vertical vowels: none 0, nieun 2, other 1

    def med_src(s, V):
        m = JUNG_FIELD[V]
        if s >= (4 if HT_VKIND[m] else 3):
            return None				# a variant this vowel does not have
        return HT_VBASE[m] + s

    return Layout("hanterm-johab", open_bdf_glyphs, 2, 3, 10, 4, 4, _kk_class, tail_class,
                  lambda lc, v, tc: (HT_FCON2 if tc else HT_FCON1)[JUNG_FIELD[v]],
                  med_set,
                  lambda lc, v, tc: HT_LMAP[JUNG_FIELD[v]] if tc else 0,
                  lambda s, L: 10 * L + 1 + s,
                  med_src,
                  lambda s, T: 405 + 4 * (T - 1) + s)


def _dkb7():
    return Layout("dkb-printer-7x2x2", open_dkb16, 1, 2, 7, 2, 2, lambda L: 0, _has_tail,
                  lambda lc, v, tc: (P16_INIT1 if tc else P16_INIT0)[v],
                  lambda lc, v, tc: tc,
                  lambda lc, v, tc: P16_FIN[v] if tc else 0,
                  lambda s, L: s * 20 + L + 1,
                  lambda s, V: 140 + s * 22 + V + 1,
                  lambda s, T: 184 + 28 * s + T)


def _dkb12():
    return Layout("dkb-printer-12x4x4", open_dkb40, 2, 2, 12, 4, 4, _kk_class, _has_tail,
                  lambda lc, v, tc: P40_CLASS[v] + 6 * tc,
                  lambda lc, v, tc: lc + 2 * tc,
                  lambda lc, v, tc: F844[v] if tc else 0,
                  lambda s, L: s * 20 + L + 1,
                  lambda s, V: 240 + s * 22 + V + 1,
                  lambda s, T: 328 + s * 28 + T)


LAYOUTS = {l.name: l for l in (_844("844", 0), _844("844-ihnm", 1), _844("844-hbios24", 0, open_hbios24), _san1044(), _621(), _hanterm(), _dkb7(),
                               _dkb12(), _kyra())}


# ---- JSET tables -------------------------------------------------------------

class Tables:
    """The JSET block as Python lists (piece lists hold whatever numbering the caller uses)."""

    def __init__(self, lc, tc, ni, nm, nf, advance=0):
        self.lc, self.tc, self.ni, self.nm, self.nf, self.advance = lc, tc, ni, nm, nf, advance
        self.lead_class = [0] * 19
        self.tail_class = [0] * 28
        n = lc * 21 * tc
        self.init_set, self.med_set, self.fin_set = [0] * n, [0] * n, [0] * n
        self.init_piece = [BLANK] * (ni * 19)
        self.med_piece = [BLANK] * (nm * 21)
        self.fin_piece = [BLANK] * (nf * 27)
        self.compat = [BLANK] * 51


def decompose(cp):
    s = cp - 0xAC00
    return s // 588, (s // 28) % 21, s % 28


def pieces_of(t, cp):
    """The piece numbers of a syllable in draw order, as the engine reads them (JamoSetTable::pieces); None if not one."""
    if isinstance(t, Jmap):
        return t.pieces(cp)
    if not 0xAC00 <= cp <= 0xD7A3:
        return None
    L, V, T = decompose(cp)
    cell = (t.lead_class[L] * 21 + V) * t.tc + t.tail_class[T]
    out = [t.init_piece[t.init_set[cell] * 19 + L], t.med_piece[t.med_set[cell] * 21 + V]]
    if T:
        out.append(t.fin_piece[t.fin_set[cell] * 27 + T - 1])
    return out


def tables_for(layout):
    """The layout's tables with the *source* glyph index as piece number (None -> blank)."""
    t = Tables(layout.lc, layout.tc, layout.ni, layout.nm, layout.nf, layout.advance)
    t.lead_class = [layout.lead_class(L) for L in range(19)]
    t.tail_class = [layout.tail_class(T) for T in range(28)]
    # A final set is read only for syllables with a final: for the no-final class it stays 0.
    final_classes = {t.tail_class[T] for T in range(1, 28)}
    for lc in range(layout.lc):
        for v in range(21):
            for tc in range(layout.tc):
                cell = (lc * 21 + v) * layout.tc + tc
                t.init_set[cell] = layout.init_set(lc, v, tc)
                t.med_set[cell] = layout.med_set(lc, v, tc)
                t.fin_set[cell] = layout.fin_set(lc, v, tc) if tc in final_classes else 0
    for s in range(layout.ni):
        for L in range(19):
            src = layout.init_src(s, L)
            t.init_piece[s * 19 + L] = BLANK if src is None else src
    for s in range(layout.nm):
        for V in range(21):
            src = layout.med_src(s, V)
            t.med_piece[s * 21 + V] = BLANK if src is None else src
    for s in range(layout.nf):
        for T in range(1, 28):
            src = layout.fin_src(s, T)
            t.fin_piece[s * 27 + T - 1] = BLANK if src is None else src
    for k, (kind, i) in enumerate(COMPAT):
        if kind == "i":
            t.compat[k] = t.init_piece[0 * 19 + i]
        elif kind == "v":
            t.compat[k] = t.med_piece[0 * 21 + i]
        else:
            t.compat[k] = t.fin_piece[0 * 27 + i - 1]
    return t


def _set_tables_only(t, what):
    """ValueError for a Jmap handed to a function that works on JSET set tables."""
    if isinstance(t, Jmap):
        raise ValueError(f"a JMAP block has no set tables: {what} needs a version 1 or 2 JSET")


def blank_compat(t, have):
    """Leave the compatibility jamo (U+3131..U+3163) in @p have, which the font draws as whole glyphs, to those glyphs: the
    engine reads the piece table first (JamoGlyphSource::piecesOf), so a piece number there would hide them."""
    # A Jmap's effective compat falls to its fallback's, so the fallback's entry goes blank too, and fallback_block is
    # re-encoded (pack_fallback) when that changed it.
    targets = [t.block_compat] + ([t.fallback.compat] if t.fallback is not None else []) if isinstance(t, Jmap) \
        else [t.compat]
    before = list(t.fallback.compat) if isinstance(t, Jmap) and t.fallback is not None else None
    for k in range(51):
        if 0x3131 + k in have:
            for target in targets:
                target[k] = BLANK
    if before is not None and t.fallback.compat != before and t.fallback_version in (1, 2):
        # keep fallback_block in step with the fallback tables (same version and numbering); an unchanged fallback keeps
        # its original bytes. A fallback read with BIG counts stays BIG (it was already in the file).
        t.fallback_block = pack_fallback(t.fallback, t.fallback_version, big=needs_big(t.fallback))


def used_pieces(t):
    """Piece numbers (source indices) any syllable or compatibility jamo can draw, sorted."""
    used = set()
    for cp in range(0xAC00, 0xD7A4):
        used.update(p for p in (pieces_of(t, cp) or ()) if p != BLANK)
    used.update(p for p in t.compat if p != BLANK)
    return sorted(used)


def renumber(t, mapping):
    """A copy of @p t with every piece number passed through @p mapping (BLANK stays)."""
    _set_tables_only(t, "renumber")
    out = Tables(t.lc, t.tc, t.ni, t.nm, t.nf, t.advance)
    out.lead_class, out.tail_class = list(t.lead_class), list(t.tail_class)
    out.init_set, out.med_set, out.fin_set = list(t.init_set), list(t.med_set), list(t.fin_set)
    # a piece no syllable can reach (an adaptive set only some lead classes use) is left blank
    conv = lambda ps: [p if p == BLANK else mapping.get(p, BLANK) for p in ps]
    out.init_piece, out.med_piece, out.fin_piece, out.compat = (conv(t.init_piece), conv(t.med_piece),
                                                                conv(t.fin_piece), conv(t.compat))
    return out


def shift_pieces(t, delta):
    """A copy of the set tables @p t with every piece number raised by @p delta (BLANK stays): a JMAP fallback must
    name pieces at or above PI+PM+PF, so its glyphs are shifted the same way."""
    _set_tables_only(t, "shift_pieces")
    named = {p for lst in (t.init_piece, t.med_piece, t.fin_piece, t.compat) for p in lst if p != BLANK}
    if any(p + delta >= BLANK or p + delta < 0 for p in named):
        raise ValueError(f"shift_pieces: a piece number leaves 0..0xFFFE with delta {delta}")
    return renumber(t, {p: p + delta for p in named})


def pack_fallback(t, version, base=0, big=False):
    """The version 1 or 2 JSET block of the set tables @p t to use as the fallback of a JMAP: unlike pack_jset it keeps
    the piece numbers of @p t (plus @p base, so pack_fallback(t, 2, PI+PM+PF) is the shifted fallback; no renumbering).
    Version 1 stores the lists as they are. Version 2 keeps arbitrary numbers by storing, per set row, the drawn slots that count
    up one by one from the row's first piece as fresh pieces (a greedy walk in slot order, not a longest-run search) and
    every other drawn slot as an alias, so it is larger than pack(t)'s block unless the numbers are contiguous in slot order. ValueError for a Jmap, a piece number
    outside 0..0xFFFE, and whatever pack refuses for version 2 (@p big: counts up to the BIG row, as pack)."""
    _set_tables_only(t, "pack_fallback")
    if version not in (1, 2):
        raise ValueError(f"JSET fallback version {version!r} is not 1 or 2")
    if base:
        t = shift_pieces(t, base)
    for p in t.init_piece + t.med_piece + t.fin_piece + t.compat:
        if p != BLANK and not 0 <= p < BLANK:
            raise ValueError(f"JSET fallback piece {p} is outside 0..0xFFFE")
    if version == 1:
        return pack_v1(t, big)
    b = decode_jset2(pack(t, big).block)
    alias = []
    for key, lst in (("i", t.init_piece), ("m", t.med_piece), ("f", t.fin_piece)):
        slots = _JSET_SLOTS[key]
        for r in range(len(b.rows[key])):
            first, fresh, pres, al, abase = None, 0, 0, 0, len(alias)
            for j, p in enumerate(lst[r * slots:(r + 1) * slots]):
                if p == BLANK:
                    continue
                pres |= 1 << j
                if first is None:
                    first = p
                if p == first + fresh:
                    fresh += 1
                else:
                    al |= 1 << j
                    alias.append(p)
            b.rows[key][r] = [first or 0, abase, pres, al]
    b.alias, b.na = alias, len(alias)
    if not alias:
        for rows in b.rows.values():
            for row in rows:
                row[1] = row[3] = 0
    return encode_jset2(b)


# ---- JSET block version 2 (docs/superpowers/specs/2026-10-23-jset-compact-design.md) ----------------------------

JSET_VERSION = 2
_JSET_SLOTS = {"i": 19, "m": 21, "f": 27}
_JSET_PB = {"i": 3, "m": 3, "f": 4}
_JSET_NAMES = {"i": "initial", "m": "medial", "f": "final"}
_JSET_LIMIT_NAMES = ("lead classes", "tail classes", "initial sets", "medial sets", "final sets")
# compat[k] (U+3131 + k): the home table ("i", "m" or "f") and the jamo index there (lead, vowel or tail index).
COMPAT_HOME = tuple(({"i": "i", "v": "m", "f": "f"}[kind], i) for kind, i in COMPAT)
# The tail index of a lead-capable consonant (the bit 7 form of its compat byte), else None (ㄸ ㅃ ㅉ, the clusters,
# the vowels): lead index -> tail index for ㄱ ㄲ ㄴ ㄷ ㄹ ㅁ ㅂ ㅅ ㅆ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ.
_LEAD_TO_TAIL = {0: 1, 1: 2, 2: 4, 3: 7, 5: 8, 6: 16, 7: 17, 9: 19, 10: 20, 11: 21, 12: 22, 14: 23, 15: 24, 16: 25,
                 17: 26, 18: 27}
COMPAT_FINAL_ALT = tuple(_LEAD_TO_TAIL.get(i) if kind == "i" else None for kind, i in COMPAT[:30])


def jset_width(n):
    """Bits of a set-number field for @p n sets: 0 for one set, else ceil(log2 n)."""
    return 0 if n <= 1 else (n - 1).bit_length()


def jset_size(lc, tc, ni, nm, nf, na=0):
    """Bytes of a version 2 block: 63 + S + NI*RI + NM*RM + NF*RF + 2*NA + 51."""
    w = jset_width(ni) + jset_width(nm) + jset_width(nf)
    ri, rm, rf = (10, 10, 12) if na else (5, 5, 6)
    return 63 + (lc * 21 * tc * w + 7) // 8 + ni * ri + nm * rm + nf * rf + 2 * na + 51


def _popcount(x):
    return bin(x).count("1")


class Jset2:
    """A version 2 block field by field, with no semantic checks (decode_jset2 / encode_jset2). Rows are
    [base, abase, presence, alias] (abase and alias 0 when NA = 0); presence and alias are the PB-byte little-endian
    bitmaps as ints."""

    def __init__(self, lc=1, tc=1, ni=1, nm=1, nf=1, advance=0, na=0, reserved=0):
        self.lc, self.tc, self.ni, self.nm, self.nf, self.advance = lc, tc, ni, nm, nf, advance
        self.na, self.reserved = na, reserved
        self.lead_class = [0] * 19
        self.tail_class = [0] * 28
        n = lc * 21 * tc
        self.init_set, self.med_set, self.fin_set = [0] * n, [0] * n, [0] * n
        self.rows = {"i": [[0, 0, 0, 0] for _ in range(ni)], "m": [[0, 0, 0, 0] for _ in range(nm)],
                     "f": [[0, 0, 0, 0] for _ in range(nf)]}
        self.alias = []
        self.compat = [0xFF] * 51


def encode_jset2(b):
    """The bytes of @p b exactly as given (rows in the NA > 0 form iff b.na > 0). ValueError when a set number does not
    fit its field, or a base, abase or alias entry is not a u16."""
    out = bytearray(b"JSET" + struct.pack("<HBBBBBBHH", JSET_VERSION, b.lc, b.tc, b.ni, b.nm, b.nf, b.advance, b.na,
                                          b.reserved))
    out += bytes(b.lead_class) + bytes(b.tail_class)
    wi, wm, wf = jset_width(b.ni), jset_width(b.nm), jset_width(b.nf)
    w = wi + wm + wf
    bits = 0
    for c, (i, m, f) in enumerate(zip(b.init_set, b.med_set, b.fin_set)):
        if i >> wi or m >> wm or f >> wf:
            raise ValueError(f"JSET cell {c}: sets {i}/{m}/{f} do not fit {wi}/{wm}/{wf} bits")
        bits |= (i | m << wi | f << (wi + wm)) << (c * w)
    out += bits.to_bytes((len(b.init_set) * w + 7) // 8, "little")
    for key in "imf":
        for s, (base, abase, _, _) in enumerate(b.rows[key]):
            for name, v in (("base", base), ("abase", abase)):
                if not 0 <= v <= 0xFFFF:
                    raise ValueError(f"JSET {_JSET_NAMES[key]} row {s} {name} {v} is not 0..0xFFFF")
    for i, a in enumerate(b.alias):
        if not 0 <= a <= 0xFFFF:
            raise ValueError(f"JSET alias[{i}] {a} is not 0..0xFFFF")
    for key in "imf":
        pb = _JSET_PB[key]
        for base, abase, pres, al in b.rows[key]:
            out += struct.pack("<H", base)
            if b.na > 0:
                out += struct.pack("<H", abase)
            out += pres.to_bytes(pb, "little")
            if b.na > 0:
                out += al.to_bytes(pb, "little")
    out += struct.pack("<%dH" % len(b.alias), *b.alias)
    out += bytes(b.compat)
    return bytes(out)


def _check_counts(lc, tc, ni, nm, nf, big=False):
    """ValueError when a count is outside the standard row (@p big False) or the BIG row (JSET_LIMITS)."""
    row = JSET_LIMITS["big" if big else "std"]
    for name, hi, bighi, v in zip(_JSET_LIMIT_NAMES, row, JSET_LIMITS["big"], (lc, tc, ni, nm, nf)):
        if not 1 <= v <= hi:
            hint = (f" (--jset-big allows {JSET_LIMITS['big'][0]} x {JSET_LIMITS['big'][1]} classes, "
                    f"{'/'.join(map(str, JSET_LIMITS['big'][2:]))} sets)") if not big and 1 <= v <= bighi else ""
            raise ValueError(f"JSET {name} {v} is not 1..{hi}{hint}")


def needs_big(t):
    """True when the Tables @p t has a count over the standard row, so only a --jset-big writer may pack it."""
    return any(v > hi for v, hi in zip((t.lc, t.tc, t.ni, t.nm, t.nf), JSET_LIMITS["std"]))


def class_limits(big):
    """(lead, tail) class limit of the standard row, or the BIG row when @p big."""
    return JSET_LIMITS["big" if big else "std"][:2]


def decode_jset2(data):
    """A version 2 block as a Jset2, checking only the spec's rules (1) and (2) (header, counts, NA, length)."""
    data = bytes(data)
    if len(data) < JSET_HEADER:
        raise ValueError(f"JSET length {len(data)} is shorter than its {JSET_HEADER} byte header")
    if data[:4] != b"JSET":
        raise ValueError("JSET magic is wrong")
    version, lc, tc, ni, nm, nf, adv, na, reserved = struct.unpack_from("<HBBBBBBHH", data, 4)
    if version == 1:
        raise ValueError("JSET version 1 is not a version 2 block (jamoset.unpack reads both)")
    if version != JSET_VERSION:
        raise ValueError(f"JSET version {version} is not supported")
    _check_counts(lc, tc, ni, nm, nf, True)        # PR-16: readers accept the BIG counts always
    if reserved:
        raise ValueError(f"JSET reserved {reserved} is not 0")
    slots = ni * 19 + nm * 21 + nf * 27
    if na > slots:
        raise ValueError(f"JSET NA {na} is over the {slots} slots")
    size = jset_size(lc, tc, ni, nm, nf, na)
    if len(data) != size:
        raise ValueError(f"JSET length {len(data)} does not match its counts ({size})")
    b = Jset2(lc, tc, ni, nm, nf, adv, na, reserved)
    b.lead_class = list(data[16:35])
    b.tail_class = list(data[35:63])
    wi, wm, wf = jset_width(ni), jset_width(nm), jset_width(nf)
    w = wi + wm + wf
    n = lc * 21 * tc
    s = (n * w + 7) // 8
    bits = int.from_bytes(data[63:63 + s], "little")
    for c in range(n):
        v = bits >> (c * w)
        b.init_set[c] = v & ((1 << wi) - 1)
        b.med_set[c] = v >> wi & ((1 << wm) - 1)
        b.fin_set[c] = v >> (wi + wm) & ((1 << wf) - 1)
    p = 63 + s
    for key in "imf":
        pb = _JSET_PB[key]
        for row in b.rows[key]:
            row[0] = struct.unpack_from("<H", data, p)[0]
            p += 2
            if na:
                row[1] = struct.unpack_from("<H", data, p)[0]
                p += 2
            row[2] = int.from_bytes(data[p:p + pb], "little")
            p += pb
            if na:
                row[3] = int.from_bytes(data[p:p + pb], "little")
                p += pb
    b.alias = list(struct.unpack_from("<%dH" % na, data, p))
    p += 2 * na
    b.compat = list(data[p:p + 51])
    return b


Packed = collections.namedtuple("Packed", "block piece_map")


def _check_tables(t, big=False):
    _check_counts(t.lc, t.tc, t.ni, t.nm, t.nf, big)
    if not 0 <= t.advance <= 255:
        raise ValueError(f"JSET advance {t.advance} is not 0..255")
    n = t.lc * 21 * t.tc
    for name, lst, want in (("leadClass", t.lead_class, 19), ("tailClass", t.tail_class, 28),
                            ("initSet", t.init_set, n), ("medSet", t.med_set, n), ("finSet", t.fin_set, n),
                            ("initial pieces", t.init_piece, t.ni * 19), ("medial pieces", t.med_piece, t.nm * 21),
                            ("final pieces", t.fin_piece, t.nf * 27), ("compat", t.compat, 51)):
        if len(lst) != want:
            raise ValueError(f"JSET {name}: {len(lst)} entries, not {want}")
    for i, c in enumerate(t.lead_class):
        if not 0 <= c < t.lc:
            raise ValueError(f"JSET leadClass[{i}] = {c} is not below {t.lc}")
    for i, c in enumerate(t.tail_class):
        if not 0 <= c < t.tc:
            raise ValueError(f"JSET tailClass[{i}] = {c} is not below {t.tc}")
    final_classes = set(t.tail_class[1:])
    wf = jset_width(t.nf)
    for name, lst, count in (("initSet", t.init_set, t.ni), ("medSet", t.med_set, t.nm), ("finSet", t.fin_set, t.nf)):
        for c, s in enumerate(lst):
            if name == "finSet" and c % t.tc not in final_classes:
                if not 0 <= s < 1 << wf:        # never read; kept when it fits the field
                    raise ValueError(f"JSET finSet[{c}] = {s} does not fit {wf} bits")
            elif not 0 <= s < count:
                raise ValueError(f"JSET {name}[{c}] = {s} is not below {count}")


def pack(t, big=False):
    """The version 2 block of the Tables @p t and the old-to-new piece map: Packed(block, piece_map). @p big: counts up
    to the BIG row (JSET_LIMITS) are written; otherwise a table over the standard row is refused.

    Walks the initial sets, then the medial, then the final; set by set, jamo by jamo. The first sight of a piece is
    fresh and takes the next number; a later sight is an alias to it. A compat entry names the lowest set of the
    character's home table whose slot holds its piece, else (a lead-capable consonant) the lowest final set in the bit
    7 form; ValueError when no set holds it, and for a table over the limits."""
    _set_tables_only(t, "pack")
    _check_tables(t, big)
    piece_map = {}
    alias = []
    lists = {"i": t.init_piece, "m": t.med_piece, "f": t.fin_piece}
    counts = {"i": t.ni, "m": t.nm, "f": t.nf}
    rows = {}
    for key in "imf":
        slots, lst = _JSET_SLOTS[key], lists[key]
        rows[key] = []
        for s in range(counts[key]):
            base, abase, pres, al = len(piece_map), len(alias), 0, 0
            for j in range(slots):
                p = lst[s * slots + j]
                if p == BLANK:
                    continue
                pres |= 1 << j
                if p in piece_map:
                    al |= 1 << j
                    alias.append(piece_map[p])
                else:
                    piece_map[p] = len(piece_map)
            rows[key].append([base, abase, pres, al])
    if len(piece_map) > 0xFFFF:
        raise ValueError(f"JSET: {len(piece_map)} pieces")
    na = len(alias)
    b = Jset2(t.lc, t.tc, t.ni, t.nm, t.nf, t.advance, na)
    b.lead_class, b.tail_class = list(t.lead_class), list(t.tail_class)
    b.init_set, b.med_set, b.fin_set = list(t.init_set), list(t.med_set), list(t.fin_set)
    b.rows, b.alias = rows, alias

    def lowest(key, idx, p):
        slots = _JSET_SLOTS[key]
        slot = idx - 1 if key == "f" else idx
        return next((s for s in range(counts[key]) if lists[key][s * slots + slot] == p), None)

    for k, p in enumerate(t.compat):
        if p == BLANK:
            b.compat[k] = 0xFF
            continue
        key, idx = COMPAT_HOME[k]
        s = lowest(key, idx, p)
        if s is not None:
            b.compat[k] = s
            continue
        alt = COMPAT_FINAL_ALT[k] if k < 30 else None
        s = None if alt is None else lowest("f", alt, p)
        if s is None:
            raise ValueError(f"compat U+{0x3131 + k:04X}: no set holds piece {p}")
        b.compat[k] = 0x80 | s
    block = encode_jset2(b)
    assert len(block) == jset_size(t.lc, t.tc, t.ni, t.nm, t.nf, na)
    return Packed(block, piece_map)


def unpack(data):
    """Parse a JSET block the way the C reader does; raises ValueError naming the field. Version 3 (JMAP) returns a Jmap
    (unpack_jmap), versions 1 and 2 return Tables. Version 2: the spec's rules
    (1)-(5) and (7), and of (6) the piece < 0xFFFF rule (glyph existence is the caller's). Returns Tables with
    resolved per-slot piece numbers (BLANK for a clear presence bit) and compat as 51 piece numbers (BLANK for 0xFF)."""
    data = bytes(data)
    if len(data) >= 6 and data[:4] == b"JSET" and struct.unpack_from("<H", data, 4)[0] == 3:
        return unpack_jmap(data)
    if len(data) >= 6 and data[:4] == b"JSET" and struct.unpack_from("<H", data, 4)[0] == 1:
        return _unpack_v1(data)
    b = decode_jset2(data)
    lc, tc, ni, nm, nf = b.lc, b.tc, b.ni, b.nm, b.nf
    for i, c in enumerate(b.lead_class):
        if c >= lc:
            raise ValueError(f"JSET leadClass[{i}] = {c} is not below {lc}")
    for i, c in enumerate(b.tail_class):
        if c >= tc:
            raise ValueError(f"JSET tailClass[{i}] = {c} is not below {tc}")
    final_classes = set(b.tail_class[1:])
    for name, lst, count in (("initSet", b.init_set, ni), ("medSet", b.med_set, nm), ("finSet", b.fin_set, nf)):
        for c, s in enumerate(lst):
            if s >= count and not (name == "finSet" and c % tc not in final_classes):
                raise ValueError(f"JSET {name}[{c}] = {s} is not below {count}")
    for key in "imf":
        slots = _JSET_SLOTS[key]
        for s, (base, abase, pres, al) in enumerate(b.rows[key]):
            what = f"JSET {_JSET_NAMES[key]} row {s}"
            if pres >> slots or al >> slots:
                raise ValueError(f"{what} padding: bits at and above {slots} are set")
            if al & ~pres:
                raise ValueError(f"{what} alias bits 0x{al:x} are not inside the presence bits 0x{pres:x}")
            if abase + _popcount(al) > b.na:
                raise ValueError(f"{what} abase {abase} + {_popcount(al)} aliases is over NA {b.na}")
    for i, a in enumerate(b.alias):
        if a == BLANK:
            raise ValueError(f"JSET alias[{i}] = 0xFFFF is not a piece")
    resolved = {}
    for key in "imf":
        slots = _JSET_SLOTS[key]
        out = []
        for s, (base, abase, pres, al) in enumerate(b.rows[key]):
            fresh = rank = 0
            for j in range(slots):
                bit = 1 << j
                if not pres & bit:
                    out.append(BLANK)
                    continue
                if al & bit:
                    piece = b.alias[abase + rank]
                    rank += 1
                else:
                    piece = base + fresh
                    fresh += 1
                if piece >= 0xFFFF:
                    raise ValueError(f"JSET piece {piece} ({_JSET_NAMES[key]} set {s} slot {j}) is not below 0xFFFF")
                out.append(piece)
        resolved[key] = out
    counts = {"i": ni, "m": nm, "f": nf}
    compat = []
    for k, c in enumerate(b.compat):
        if c == 0xFF:
            compat.append(BLANK)
            continue
        what = f"JSET compat[{k}] = 0x{c:02x} (U+{0x3131 + k:04X})"
        key, idx = COMPAT_HOME[k]
        if c & 0x80:
            alt = COMPAT_FINAL_ALT[k] if k < 30 else None
            if alt is None:
                raise ValueError(f"{what}: bit 7 on a jamo with no lead-capable final form")
            key, idx = "f", alt
        s = c & 0x7F
        if s >= counts[key]:
            raise ValueError(f"{what}: set {s} is not below {counts[key]} {_JSET_NAMES[key]} sets")
        slots = _JSET_SLOTS[key]
        piece = resolved[key][s * slots + (idx - 1 if key == "f" else idx)]
        if piece == BLANK:
            raise ValueError(f"{what}: {_JSET_NAMES[key]} set {s} has no slot for it")
        compat.append(piece)
    t = Tables(lc, tc, ni, nm, nf, b.advance)
    t.lead_class, t.tail_class = list(b.lead_class), list(b.tail_class)
    t.init_set, t.med_set, t.fin_set = list(b.init_set), list(b.med_set), list(b.fin_set)
    t.init_piece, t.med_piece, t.fin_piece, t.compat = resolved["i"], resolved["m"], resolved["f"], compat
    return t


class IdentityMap(dict):
    """The piece map of a version 1 block (pack_jset): every piece keeps its number, mapped or not."""

    def __missing__(self, key):
        return key

    def get(self, key, default=None):
        return key

    def __contains__(self, key):
        return True


def renumber_glyphs(glyphs, piece_map):
    """@p glyphs with its plane-15 piece code points (PIECE_BASE + n) renumbered by @p piece_map (pack's old -> new
    map); pieces the map lacks follow after the largest mapped number in their old order. Other code points pass
    through. @p glyphs is a dict {cp: glyph} (a dict comes back) or write_svfn's list [(cp, ...)] (a list comes back,
    in the same order). An IdentityMap (pack_jset's v1 map) changes nothing."""
    is_dict = isinstance(glyphs, dict)
    if isinstance(piece_map, IdentityMap):
        return dict(glyphs) if is_dict else list(glyphs)
    cps = list(glyphs) if is_dict else [g[0] for g in glyphs]
    plane = lambda cp: PIECE_BASE <= cp < PIECE_BASE + 0x10000
    nxt = max(piece_map.values(), default=-1) + 1
    new = {}
    for cp in sorted(cp for cp in cps if plane(cp)):
        n = cp - PIECE_BASE
        if n in piece_map:
            new[cp] = PIECE_BASE + piece_map[n]
        else:
            new[cp] = PIECE_BASE + nxt
            nxt += 1
    if is_dict:
        return {new.get(cp, cp): g for cp, g in glyphs.items()}
    return [(new.get(g[0], g[0]),) + tuple(g[1:]) for g in glyphs]


def _jset_block_size(blob):
    """The length a block's own counts give it, by its version (1 or 2; a version 3 block's is its whole length, which
    unpack_jmap has already checked against its counts)."""
    if struct.unpack_from("<H", blob, 4)[0] == 3:
        return len(blob)                 # unpack_jmap already checked the length against its counts
    if struct.unpack_from("<H", blob, 4)[0] == 1:
        return _jset_size_v1(*blob[6:11])
    return jset_size(*blob[6:11], na=struct.unpack_from("<H", blob, 12)[0])


# ---- JSET block version 1 (spec amendment 2026-10-23: both versions stay; pack_v1 is the v1 writer) ----

_JSET1_HEADER = 12


def _jset_size_v1(lc, tc, ni, nm, nf):
    return _JSET1_HEADER + 19 + 28 + 3 * lc * 21 * tc + 2 * (ni * 19 + nm * 21 + nf * 27 + 51)


def pack_v1(t, big=False):
    """The version 1 block of the Tables @p t; @p big as for pack."""
    _set_tables_only(t, "pack_v1")
    _check_counts(t.lc, t.tc, t.ni, t.nm, t.nf, big)
    out = bytearray(b"JSET" + struct.pack("<HBBBBBB", 1, t.lc, t.tc, t.ni, t.nm, t.nf, t.advance))
    out += bytes(t.lead_class) + bytes(t.tail_class)
    out += bytes(t.init_set) + bytes(t.med_set) + bytes(t.fin_set)
    for lst in (t.init_piece, t.med_piece, t.fin_piece, t.compat):
        out += struct.pack("<%dH" % len(lst), *lst)
    assert len(out) == _jset_size_v1(t.lc, t.tc, t.ni, t.nm, t.nf)
    return bytes(out)


# auto writes v2 when the face's v1 block is at least this many bytes larger than its v2 block: about the v2 reader's
# code cost plus margin (spec amendment 2026-10-23, decision 1).
JSET_V2_MIN_SAVING = 1024
JSET_VERSIONS = (1, 2, "auto")


def choose_jset_version(t, big=False):
    """The version auto writes for the Tables @p t: 2 when len(pack_v1(t)) - len(pack(t).block) >= JSET_V2_MIN_SAVING,
    else 1. When pack refuses with the R4 ValueError (a compat entry no set holds), v2 cannot hold the face: 1
    (ruling T5-C1). Any other ValueError propagates."""
    _set_tables_only(t, "choose_jset_version")
    try:
        v2 = len(pack(t, big).block)
    except ValueError as e:
        if "no set holds piece" in str(e):
            return 1
        raise
    return 2 if len(pack_v1(t, big)) - v2 >= JSET_V2_MIN_SAVING else 1


def pack_jset(t, version, big=False):
    """The block of the Tables @p t in @p version (1, 2 or "auto") and its old-to-new piece map: Packed(block,
    piece_map). Version 1 is pack_v1(t) with an IdentityMap; version 2 is pack(t). @p big: counts up to the BIG row."""
    _set_tables_only(t, "pack_jset")
    if version == "auto":
        version = choose_jset_version(t, big)
    if version == 1:
        return Packed(pack_v1(t, big), IdentityMap())
    if version == 2:
        return pack(t, big)
    raise ValueError(f"JSET version {version!r} is not 1, 2 or auto")


def _unpack_v1(data):
    """Parse a version 1 JSET block the way the engine does (JamoSetTable); raises ValueError naming the field."""
    if len(data) < _JSET1_HEADER:
        raise ValueError("JSET length is shorter than its header")
    if data[:4] != b"JSET":
        raise ValueError("JSET magic is wrong")
    version, lc, tc, ni, nm, nf, adv = struct.unpack_from("<HBBBBBB", data, 4)
    if version != 1:
        raise ValueError(f"JSET version {version} is not supported")
    _check_counts(lc, tc, ni, nm, nf, True)        # PR-16: readers accept the BIG counts always
    if len(data) != _jset_size_v1(lc, tc, ni, nm, nf):
        raise ValueError(f"JSET length {len(data)} does not match its counts")
    t = Tables(lc, tc, ni, nm, nf, adv)
    p = _JSET1_HEADER
    t.lead_class = list(data[p:p + 19])
    p += 19
    t.tail_class = list(data[p:p + 28])
    p += 28
    for i, c in enumerate(t.lead_class):
        if c >= lc:
            raise ValueError(f"JSET leadClass[{i}] = {c} is not below {lc}")
    for i, c in enumerate(t.tail_class):
        if c >= tc:
            raise ValueError(f"JSET tailClass[{i}] = {c} is not below {tc}")
    final_classes = set(t.tail_class[1:])
    n = lc * 21 * tc
    for name, count, attr in (("initSet", ni, "init_set"), ("medSet", nm, "med_set"), ("finSet", nf, "fin_set")):
        vals = list(data[p:p + n])
        p += n
        for i, s in enumerate(vals):
            if s >= count and not (attr == "fin_set" and i % tc not in final_classes):
                raise ValueError(f"JSET {name}[{i}] = {s} is not below {count}")
        setattr(t, attr, vals)
    for attr, cnt in (("init_piece", ni * 19), ("med_piece", nm * 21), ("fin_piece", nf * 27), ("compat", 51)):
        setattr(t, attr, list(struct.unpack_from("<%dH" % cnt, data, p)))
        p += cnt * 2
    return t


# ---- JSET block version 3: JMAP, a syllable mapping table (spec/SVF.md "Version 3: mapping table (JMAP)") ---------

JMAP_VERSION = 3
JMAP_FLAG_4B = 0x01
JMAP_FLAG_SPARSE = 0x02
JMAP_FLAG_FALLBACK = 0x04
JMAP_FLAG_LIST = 0x08
JMAP_LIST_MAX = 255
JMAP_LIST_ENTRIES = 118
JMAP_LIST_ENTRY = 8
JMAP_COMPAT_OFF = 16
JMAP_RANK_OFF = 118
JMAP_BITMAP_OFF = 206
JMAP_PAD_OFF = 1603
JMAP_SPARSE_ENTRIES = 1604
JMAP_DENSE_ENTRIES = 118
JMAP_REGION_MAX = 65534
_JMAP_NSYL = 11172


class Jmap:
    """A JMAP block: syllable index -> plane indices (0 = none, k = the k-th piece of that plane, 1-based). Pieces are
    numbered per plane: initial 0..PI-1, medial PI.., final PI+PM.. (glyph U+F0000 + number). In list mode (flag 0x08)
    PI = PM = PF = 0 and @p entries maps a syllable index to three piece numbers of one shared pool (BLANK = none)."""

    version = JMAP_VERSION

    def __init__(self, advance=0, pi=0, pm=0, pf=0, entries=None, block_compat=None, fallback=None, list_mode=False):
        self.list_mode = list_mode
        self.advance, self.pi, self.pm, self.pf = advance, pi, pm, pf
        self.entries = {} if entries is None else entries
        self.block_compat = [BLANK] * 51 if block_compat is None else block_compat
        self.fallback = fallback            # Tables of the FALLBACK JSET (version 1 or 2), or None
        self.fallback_block = None          # its bytes when read by unpack_jmap
        self.fallback_version = 0

    @property
    def compat(self):
        """The effective compat piece numbers: this block's own entry unless blank, else the fallback's (PR-10)."""
        fb = self.fallback.compat if self.fallback is not None else None
        return [c if c != BLANK or fb is None else fb[k] for k, c in enumerate(self.block_compat)]

    @property
    def init_piece(self):
        """Every piece number this block names, by plane (parse_svfn checks that each has a glyph); a fallback's own
        pieces are included, as they are drawn on a miss. A LIST names the distinct non-blank fields of its entries."""
        if self.list_mode:
            return self._list_pieces(0)
        return list(range(self.pi)) + (self.fallback.init_piece if self.fallback is not None else [])

    @property
    def med_piece(self):
        if self.list_mode:
            return self._list_pieces(1)
        return list(range(self.pi, self.pi + self.pm)) + (self.fallback.med_piece if self.fallback is not None else [])

    @property
    def fin_piece(self):
        if self.list_mode:
            return self._list_pieces(2)
        return (list(range(self.pi + self.pm, self.pi + self.pm + self.pf))
                + (self.fallback.fin_piece if self.fallback is not None else []))

    def _list_pieces(self, n):
        own = sorted({e[n] for e in self.entries.values() if e[n] != BLANK})
        fb = (self.fallback.init_piece, self.fallback.med_piece, self.fallback.fin_piece)[n] \
            if self.fallback is not None else []
        return own + list(fb)

    def pieces(self, cp):
        """The piece numbers of a syllable in draw order (PR-9: the entry decides the count; outside list mode a 0 field is BLANK, in list mode 0 is piece 0 and BLANK is 0xFFFF); a miss
        is the fallback's answer or None."""
        if not 0xAC00 <= cp <= 0xD7A3:
            return None
        e = self.entries.get(cp - 0xAC00)
        if e is None:
            return pieces_of(self.fallback, cp) if self.fallback is not None else None
        i, m, f = e
        if self.list_mode:
            return [i, m] if f == BLANK else [i, m, f]
        out = [BLANK if not i else i - 1, BLANK if not m else self.pi + m - 1]
        if f:
            out.append(self.pi + self.pm + f - 1)
        return out


def jmap_size(ns, four, sparse, fallback_len=0, list_mode=False):
    """The byte length of a JMAP block with @p ns entries."""
    if list_mode:
        return JMAP_LIST_ENTRIES + ns * JMAP_LIST_ENTRY + fallback_len
    return (JMAP_SPARSE_ENTRIES if sparse else JMAP_DENSE_ENTRIES) + ns * (4 if four else 3) + fallback_len


def _jmap_limits(pi, pm, pf, four):
    if four:
        return pi <= 2047 and pm <= 2047 and pf <= 1023
    return max(pi, pm, pf) <= 255


def _jmap_fallback_check(fb, advance, what):
    """Parse a fallback block (version 1 or 2 only, advance equal to the JMAP's); the Tables, or ValueError."""
    if len(fb) < 12 or fb[:4] != b"JSET":
        raise ValueError(f"JMAP {what} fallback is not a JSET block")
    v = struct.unpack_from("<H", fb, 4)[0]
    if v not in (1, 2):
        raise ValueError(f"JMAP {what} fallback is version {v}, not 1 or 2")
    if fb[11] != advance:          # byte 11 is the advance in both headers: compared before the reader is consulted
        raise ValueError(f"JMAP {what} fallback advance {fb[11]} differs from the JMAP advance {advance}")
    try:
        t = unpack(fb)
    except (ValueError, IndexError, struct.error) as e:
        raise ValueError(f"JMAP {what} fallback is malformed: {e}") from None
    if t.advance != advance:
        raise ValueError(f"JMAP {what} fallback advance {t.advance} differs from the JMAP advance {advance}")
    return t


def pack_jmap(jm, fallback_block=None):
    """The JMAP block of @p jm. 4B when any plane count is over 255, SPARSE when it has fewer than 11,172 entries;
    @p fallback_block (a version 1 or 2 JSET block; default jm.fallback_block) sets the FALLBACK flag."""
    if fallback_block is None:
        fallback_block = jm.fallback_block
    if fallback_block is None and jm.fallback is not None:
        raise ValueError("JMAP pack: jm.fallback is set but no fallback block was given")
    for name, v in (("advance", jm.advance), ("PI", jm.pi), ("PM", jm.pm), ("PF", jm.pf)):
        if not 0 <= v <= 0xFFFF or (name == "advance" and v > 255):
            raise ValueError(f"JMAP pack: {name} {v} is out of range")
    if jm.list_mode:
        return _pack_list(jm, fallback_block)
    four = max(jm.pi, jm.pm, jm.pf) > 255
    if not _jmap_limits(jm.pi, jm.pm, jm.pf, four):
        raise ValueError(f"JMAP pack: counts PI {jm.pi} PM {jm.pm} PF {jm.pf} are over the limits")
    total = jm.pi + jm.pm + jm.pf
    if total < 1:
        raise ValueError("JMAP pack: no pieces")
    ns = len(jm.entries)
    sparse = ns < _JMAP_NSYL
    if ns < 1:
        raise ValueError("JMAP pack: no entries")
    if len(jm.block_compat) != 51:
        raise ValueError("JMAP pack: block_compat is not 51 entries")
    for k, c in enumerate(jm.block_compat):
        if c != BLANK and not 0 <= c < total:
            raise ValueError(f"JMAP pack: compat[{k}] = {c} is not below {total}")
    counts = (jm.pi, jm.pm, jm.pf)
    for s, e in jm.entries.items():
        if not 0 <= s < _JMAP_NSYL:
            raise ValueError(f"JMAP pack: syllable {s} is outside 0..11171")
        if len(e) != 3 or any(not 0 <= f <= c for f, c in zip(e, counts)):
            raise ValueError(f"JMAP pack: entry {s} = {e} is over the plane counts {counts}")
    flags = (JMAP_FLAG_4B if four else 0) | (JMAP_FLAG_SPARSE if sparse else 0)
    if fallback_block is not None:
        fbt = _jmap_fallback_check(bytes(fallback_block), jm.advance, "pack")
        for p in fbt.init_piece + fbt.med_piece + fbt.fin_piece + fbt.compat:
            if p != BLANK and p < total:
                raise ValueError(f"JMAP fallback piece {p} overlaps the plane pieces 0..{total - 1}")
        flags |= JMAP_FLAG_FALLBACK
    out = bytearray(b"JSET" + struct.pack("<HBBHHHH", JMAP_VERSION, flags, jm.advance, ns, jm.pi, jm.pm, jm.pf))
    out += struct.pack("<51H", *jm.block_compat)
    order = sorted(jm.entries)
    if sparse:
        bitmap = bytearray(1397)
        for s in order:
            bitmap[s >> 3] |= 1 << (s & 7)
        ranks = [sum(1 for s in order if s < b * 256) for b in range(44)]
        out += struct.pack("<44H", *ranks) + bitmap + b"\0"
    elif order != list(range(_JMAP_NSYL)):
        raise ValueError("JMAP pack: a dense block needs all 11172 syllables")
    for s in order:
        i, m, f = jm.entries[s]
        if four:
            out += bytes((i >> 8 | (m >> 8) << 3 | (f >> 8) << 6, i & 255, m & 255, f & 255))
        else:
            out += bytes((i, m, f))
    if fallback_block is not None:
        out += bytes(fallback_block)
    if len(out) > JMAP_REGION_MAX:
        raise ValueError(f"JMAP pack: {len(out)} bytes is over the region limit {JMAP_REGION_MAX}")
    assert len(out) == jmap_size(ns, four, sparse, len(fallback_block or b""))
    return bytes(out)


def _pack_list(jm, fallback_block):
    """The LIST block (flag 0x08) of the list-mode @p jm: entries sorted by key, fields are pool piece numbers."""
    if (jm.pi, jm.pm, jm.pf) != (0, 0, 0):
        raise ValueError(f"JMAP pack: a LIST has no planes: PI {jm.pi} PM {jm.pm} PF {jm.pf} must be 0")
    ns = len(jm.entries)
    if ns < 1:
        raise ValueError("JMAP pack: no entries")
    if ns > JMAP_LIST_MAX:
        raise ValueError(f"JMAP pack: {ns} LIST entries is over {JMAP_LIST_MAX}: use SPARSE "
                         f"({JMAP_SPARSE_ENTRIES + 3 * ns} B plus plane copies for recombinations)")
    if len(jm.block_compat) != 51:
        raise ValueError("JMAP pack: block_compat is not 51 entries")
    for k, c in enumerate(jm.block_compat):
        if not 0 <= c <= 0xFFFF:
            raise ValueError(f"JMAP pack: compat[{k}] = {c} is out of range: a piece number or BLANK")
    for s, e in jm.entries.items():
        if not 0 <= s < _JMAP_NSYL:
            raise ValueError(f"JMAP pack: syllable {s} is outside 0..11171")
        if len(e) != 3 or any(not 0 <= v <= 0xFFFF for v in e):
            raise ValueError(f"JMAP pack: entry {s} = {e} has a field out of range 0..65535")
    flags = JMAP_FLAG_LIST
    if fallback_block is not None:
        _jmap_fallback_check(bytes(fallback_block), jm.advance, "pack")      # the pool is shared: no overlap refusal
        flags |= JMAP_FLAG_FALLBACK
    out = bytearray(b"JSET" + struct.pack("<HBBHHHH", JMAP_VERSION, flags, jm.advance, ns, 0, 0, 0))
    out += struct.pack("<51H", *jm.block_compat)
    for s in sorted(jm.entries):
        out += struct.pack("<4H", s, *jm.entries[s])
    if fallback_block is not None:
        out += bytes(fallback_block)
    if len(out) > JMAP_REGION_MAX:
        raise ValueError(f"JMAP pack: {len(out)} bytes is over the region limit {JMAP_REGION_MAX}")
    assert len(out) == jmap_size(ns, False, False, len(fallback_block or b""), True)
    return bytes(out)


def unpack_jmap(data):
    """Parse a JMAP block the way the C reader does, rules R1-R7 in this order, each reading only bytes the earlier ones
    bounded; ValueError text starts "JMAP Rn". A LIST (flag 0x08) is read by R1', L2, L3, R4, L6 in that order (text
    starts "JMAP R1", "JMAP L2", "JMAP L3", "JMAP R4", "JMAP L6"). (R8, a glyph for every piece, is the caller's, as for JSET.)"""
    data = bytes(data)
    n = len(data)
    # R1: header
    if n < JMAP_DENSE_ENTRIES:
        raise ValueError(f"JMAP R1 length {n} is shorter than {JMAP_DENSE_ENTRIES}")
    if data[:4] != b"JSET":
        raise ValueError("JMAP R1 magic is wrong")
    version, flags, advance = struct.unpack_from("<HBB", data, 4)
    if version != JMAP_VERSION:
        raise ValueError(f"JMAP R1 version {version} is not 3")
    if flags & 0xF0 or (flags & JMAP_FLAG_LIST and flags & 3):       # R1': a LIST excludes 4B and SPARSE (PL-15 text)
        raise ValueError(f"JMAP R1 flags 0x{flags:02x} set reserved bits")
    if flags & JMAP_FLAG_LIST:
        return _unpack_list(data, advance, bool(flags & JMAP_FLAG_FALLBACK))
    four, sparse, fallback = bool(flags & 1), bool(flags & 2), bool(flags & 4)
    # R2: counts
    ns, pi, pm, pf = struct.unpack_from("<HHHH", data, 8)
    if not _jmap_limits(pi, pm, pf, four):
        raise ValueError(f"JMAP R2 counts PI {pi} PM {pm} PF {pf} are over the {'4B' if four else '3B'} limits")
    if pi + pm + pf < 1:
        raise ValueError("JMAP R2 PI + PM + PF is 0")
    # R3: NS
    if sparse and not 1 <= ns <= _JMAP_NSYL:
        raise ValueError(f"JMAP R3 NS {ns} is not 1..11172")
    if not sparse and ns != _JMAP_NSYL:
        raise ValueError(f"JMAP R3 NS {ns} of a dense block is not 11172")
    # R4: length
    e_off = JMAP_SPARSE_ENTRIES if sparse else JMAP_DENSE_ENTRIES
    f_off = e_off + ns * (4 if four else 3)
    if n > JMAP_REGION_MAX:
        raise ValueError(f"JMAP R4 length {n} is over the region limit {JMAP_REGION_MAX}")
    fb = None
    if not fallback:
        if n != f_off:
            raise ValueError(f"JMAP R4 length {n} is not {f_off}")
    else:
        if n < f_off + 12:
            raise ValueError(f"JMAP R4 length {n} is shorter than {f_off} + 12 for a fallback")
        fb = _jmap_fallback_check(data[f_off:], advance, "R4")
        fb = (fb,)
    # R5: compat
    total = pi + pm + pf
    compat = list(struct.unpack_from("<51H", data, JMAP_COMPAT_OFF))
    for k, c in enumerate(compat):
        if c != BLANK and c >= total:
            raise ValueError(f"JMAP R5 compat[{k}] = {c} is not blank or below {total}")
    # R6: sparse index
    present = None
    if sparse:
        if data[JMAP_PAD_OFF]:
            raise ValueError("JMAP R6 pad byte is not 0")
        bitmap = data[JMAP_BITMAP_OFF:JMAP_PAD_OFF]
        if bitmap[1396] & 0xF0:
            raise ValueError("JMAP R6 bitmap bits 11172..11175 are not 0")
        ranks = struct.unpack_from("<44H", data, JMAP_RANK_OFF)
        present, run = [], 0
        for b in range(44):
            if ranks[b] != run:
                raise ValueError(f"JMAP R6 rank[{b}] = {ranks[b]}, the bitmap has {run} bits below {b * 256}")
            for s in range(b * 256, min(b * 256 + 256, _JMAP_NSYL)):
                if bitmap[s >> 3] >> (s & 7) & 1:
                    present.append(s)
                    run += 1
        if run != ns:
            raise ValueError(f"JMAP R6 NS {ns} but the bitmap has {run} bits")
    else:
        present = range(_JMAP_NSYL)
    # R7: entries
    entries = {}
    for j, s in enumerate(present):
        p = e_off + j * (4 if four else 3)
        if four:
            b0 = data[p]
            e = (b0 & 7) << 8 | data[p + 1], (b0 >> 3 & 7) << 8 | data[p + 2], (b0 >> 6) << 8 | data[p + 3]
        else:
            e = (data[p], data[p + 1], data[p + 2])
        for name, v, c in zip("imf", e, (pi, pm, pf)):
            if v > c:
                raise ValueError(f"JMAP R7 entry {s} field {name} = {v} is over {c}")
        entries[s] = e
    jm = Jmap(advance, pi, pm, pf, entries, compat, fb[0] if fb else None)
    if fb:
        jm.fallback_block = data[f_off:]
        jm.fallback_version = struct.unpack_from("<H", jm.fallback_block, 4)[0]
    return jm


def _unpack_list(data, advance, fallback):
    """The LIST part of unpack_jmap, after R1': L2, L3, R4, L6 (L5 and L7 are the caller's, like R8)."""
    n = len(data)
    ns, pi, pm, pf = struct.unpack_from("<HHHH", data, 8)
    if pi or pm or pf:
        raise ValueError(f"JMAP L2 PI {pi} PM {pm} PF {pf} of a LIST are not 0")
    if not 1 <= ns <= JMAP_LIST_MAX:
        raise ValueError(f"JMAP L3 NS {ns} is not 1..{JMAP_LIST_MAX}")
    f_off = JMAP_LIST_ENTRIES + ns * JMAP_LIST_ENTRY
    if n > JMAP_REGION_MAX:
        raise ValueError(f"JMAP R4 length {n} is over the region limit {JMAP_REGION_MAX}")
    fb = None
    if not fallback:
        if n != f_off:
            raise ValueError(f"JMAP R4 length {n} is not {f_off}")
    else:
        if n < f_off + 12:
            raise ValueError(f"JMAP R4 length {n} is shorter than {f_off} + 12 for a fallback")
        fb = _jmap_fallback_check(data[f_off:], advance, "R4")
    compat = list(struct.unpack_from("<51H", data, JMAP_COMPAT_OFF))
    entries, last = {}, -1
    for j in range(ns):
        key, i, m, f = struct.unpack_from("<4H", data, JMAP_LIST_ENTRIES + j * JMAP_LIST_ENTRY)
        if key <= last or key >= _JMAP_NSYL:
            raise ValueError(f"JMAP L6 key {key} of entry {j} is not above {last} and at most 11171")
        entries[key] = (i, m, f)
        last = key
    jm = Jmap(advance, 0, 0, 0, entries, compat, fb, list_mode=True)
    if fb is not None:
        jm.fallback_block = data[f_off:]
        jm.fallback_version = struct.unpack_from("<H", jm.fallback_block, 4)[0]
    return jm


def jmap_from_tables(t, syllables, glyphs, pad=(0, 0, 0)):
    """A Jmap from the JSET Tables @p t for the syllable indices @p syllables, and its piece glyphs. @p glyphs maps t's
    piece numbers to cell bytes, or, when any key is at or above U+F0000 (a face's whole glyph dict), U+F0000 + piece number
    to cell bytes (the other keys are ignored). Each plane numbers the pieces its syllables (then the compat jamo) use contiguously, in
    order of first use; a glyph used in two planes is copied. @p pad adds that many unused, distinct pieces per plane
    (initial, medial, final). Returns (Jmap, {U+F0000 + number: cell}); the Jmap has no fallback."""
    maps = ({}, {}, {})                              # per plane: t's piece number -> index
    entries = {}

    def index(plane, p):
        if p == BLANK:
            return 0
        return maps[plane].setdefault(p, len(maps[plane])) + 1

    for s in sorted(syllables):
        ps = pieces_of(t, 0xAC00 + s)
        entries[s] = (index(0, ps[0]), index(1, ps[1]), index(2, ps[2]) if len(ps) > 2 else 0)
    compat = []
    for k, p in enumerate(t.compat):
        plane = {"i": 0, "v": 1, "f": 2}[COMPAT[k][0]]
        compat.append((plane, p))
    for plane, p in compat:
        index(plane, p)
    plane15 = any(k >= PIECE_BASE for k in glyphs)       # a face's whole dict: ASCII and the rest sit at the low keys
    glyph = (lambda p: glyphs[PIECE_BASE + p]) if plane15 else (lambda p: glyphs[p])
    base = [(k, g) for k, g in sorted(glyphs.items()) if k >= PIECE_BASE or not plane15][:1]
    for plane in range(3):
        for j in range(pad[plane]):
            if not base:
                raise ValueError("jmap_from_tables: pad needs at least one glyph")
            maps[plane][("pad", j)] = len(maps[plane])
    pi, pm, pf = (len(m) for m in maps)
    offs = (0, pi, pi + pm)
    out = {}
    for plane in range(3):
        for p, idx in maps[plane].items():
            if isinstance(p, tuple):
                g = bytearray(base[0][1])
                if len(g) < 2 or p[1] + 1 >= 1 << 14:      # bits 14-15 carry the plane tag
                    raise ValueError("jmap_from_tables: pad pieces cannot be made distinct")
                v = (p[1] + 1) ^ (plane << 14)
                g[0] ^= v & 255
                g[1] ^= v >> 8
                out[PIECE_BASE + offs[plane] + idx] = bytes(g)
            else:
                out[PIECE_BASE + offs[plane] + idx] = glyph(p)
    block_compat = [BLANK if p == BLANK else offs[plane] + maps[plane][p] for plane, p in compat]
    return Jmap(t.advance, pi, pm, pf, entries, block_compat), out


def jmap_list(f, exceptions, compat=None, jset_version=None, fallback=True, advance=0):
    """A list-mode (LIST) Jmap over the pieces of the parsed face @p f, and the glyphs it adds. @p exceptions maps a
    syllable index s (0..11171) to 1-3 piece numbers (padded with BLANK) or to a whole cell (bytes, packed rows);
    @p compat maps a compat index k (0..50) to one piece number or a whole cell, and a k not given stays BLANK (the
    fallback answers, PR-10). A whole cell becomes a new piece numbered above the highest U+F0000 + n code point of
    @p f (PL-5): syllables in ascending s first, then compat jamo in ascending k. With @p fallback the face's JSET (version
    1 or 2) is the fallback: its bytes are kept verbatim, or re-encoded by pack_fallback when @p jset_version differs
    (numbers kept, PL-9), and the LIST advance is the fallback's (@p advance is ignored); without it the advance is
    @p advance. Returns (Jmap, {cp: cell}); the caller writes pack_jmap(jm, jm.fallback_block). ValueError on a refusal."""
    compat = compat or {}
    if len(exceptions) > JMAP_LIST_MAX:
        raise ValueError(f"jmap_list: {len(exceptions)} LIST entries is over {JMAP_LIST_MAX}: use SPARSE "
                         f"({JMAP_SPARSE_ENTRIES + 3 * len(exceptions)} B plus plane copies for recombinations)")
    for s in exceptions:
        if not 0 <= s < _JMAP_NSYL:
            raise ValueError(f"jmap_list: syllable {s} is outside 0..11171")
    for k in compat:
        if not 0 <= k < 51:
            raise ValueError(f"jmap_list: compat index {k} is outside 0..50")
    bpp = getattr(f, "bpp", 1)
    stride = ((f.cell_w * bpp + 7) // 8) * f.cell_h
    fb_block, fb_tables = None, None
    if f.jset is not None and len(f.jset) >= 6 and struct.unpack_from("<H", f.jset, 4)[0] == 3:
        raise ValueError("jmap_list: the face already has a JSET version 3 block; start from the plain face")
    if jset_version is not None and not fallback:
        raise ValueError("jmap_list: jset_version needs a fallback")
    if fallback:
        if f.jset is None:
            raise ValueError("jmap_list: the face has no usable JSET block; start from a jamo face whose JSET parses")
        src_version = struct.unpack_from("<H", f.jset, 4)[0]
        fb_tables = unpack(f.jset)
        fb_block = bytes(f.jset)
        if jset_version is not None and jset_version != src_version:
            if jset_version not in (1, 2):
                raise ValueError(f"jmap_list: jset_version {jset_version!r} is not 1 or 2")
            fb_block = pack_fallback(fb_tables, jset_version, 0, big=needs_big(fb_tables))
            fb_tables = unpack(fb_block)
        advance = fb_tables.advance
    top = max((cp - PIECE_BASE for cp in f.glyphs if PIECE_BASE <= cp < PIECE_BASE + 0x10000), default=-1)
    nxt = top + 1
    new = {}

    def piece(v, what):
        nonlocal nxt
        if isinstance(v, (bytes, bytearray)):
            if len(v) != stride:
                raise ValueError(f"jmap_list: {what} cell is {len(v)} bytes, not {stride}")
            if nxt >= BLANK:
                raise ValueError(f"jmap_list: no free piece number above U+F{top:04X}")
            new[PIECE_BASE + nxt] = bytes(v)
            nxt += 1
            return nxt - 1
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= BLANK:
            raise ValueError(f"jmap_list: {what} piece {v!r} is not a piece number 0..{BLANK - 1} or BLANK")
        if v == BLANK:
            return v
        if PIECE_BASE + v not in f.glyphs and PIECE_BASE + v not in new:
            raise ValueError(f"jmap_list: {what} piece {v} has no glyph U+F{v:04X} in the face")
        return v

    entries = {}
    for s in sorted(exceptions):
        v = exceptions[s]
        if isinstance(v, (bytes, bytearray)):
            entries[s] = (piece(v, f"syllable {s}"), BLANK, BLANK)
        else:
            if not isinstance(v, (list, tuple)):
                raise ValueError(f"jmap_list: syllable {s} needs a cell (bytes) or a list of 1-3 pieces, not {type(v).__name__}")
            v = list(v)
            if not 1 <= len(v) <= 3:
                raise ValueError(f"jmap_list: syllable {s} has {len(v)} pieces, not 1..3")
            entries[s] = tuple([piece(p, f"syllable {s}") for p in v] + [BLANK] * (3 - len(v)))
    block_compat = [BLANK] * 51
    for k in sorted(compat):
        c = compat[k]
        if c == BLANK and not isinstance(c, (bytes, bytearray)):
            continue                                 # a number BLANK means "not given"
        block_compat[k] = piece(c, f"compat {k}")
    jm = Jmap(advance, 0, 0, 0, entries, block_compat, fb_tables, list_mode=True)
    if fb_block is not None:
        jm.fallback_block = fb_block
        jm.fallback_version = struct.unpack_from("<H", fb_block, 4)[0]
    return jm, new


# ---- SVFN reading and writing ---------------------------------------------------

class Svfn:
    pass


# ---- v3: profiles, ink-box records, the shared packer -------------------------------

# rec, row, tab: log2 of the record, row and table units; box: "x", "y" or "full"; off: "u16", "u32" or "auto"
# (u16 while the glyph data is at most 65535 << rec bytes).
Profile = collections.namedtuple("Profile", "rec row tab box off")
PROFILES = {
    "mcu-strict": Profile(2, 0, 2, "x", "auto"),
    "default": Profile(2, 0, 2, "x", "u32"),
    "dos": Profile(0, 0, 0, "x", "auto"),
    "wasm": Profile(0, 0, 0, "x", "auto"),
    "full": Profile(2, 0, 2, "full", "u32"),
    "simd16": Profile(4, 0, 4, "x", "u32"),
}
BOXES = ("x", "y", "full")


def profile_of(p, box=None):
    """A Profile from a name, a Profile or a units string "REC,ROW,TAB,OFF" (log2 units, OFF 16 or 32, box x);
    @p box replaces the box policy. ValueError on ROW > REC, a unit past 6, a bad box or offset width."""
    if isinstance(p, str):
        if p in PROFILES:
            p = PROFILES[p]
        else:
            try:
                r, w, t, o = (int(v) for v in p.split(","))
            except ValueError:
                raise ValueError(f"unknown profile {p!r}: a name or REC,ROW,TAB,OFF units") from None
            if o not in (16, 32):
                raise ValueError(f"offset width {o} in {p!r} is not 16 or 32")
            p = Profile(r, w, t, "x", "u16" if o == 16 else "u32")
    else:
        p = Profile(*p)
    if box is not None:
        p = p._replace(box=box)
    if not all(isinstance(v, int) and 0 <= v <= 6 for v in p[:3]):
        raise ValueError(f"profile units {p[:3]} are not log2 values 0..6")
    if p.row > p.rec:
        raise ValueError(f"profile row unit 2^{p.row} is larger than its record unit 2^{p.rec}")
    if p.box not in BOXES:
        raise ValueError(f"profile box {p.box!r} is not one of {BOXES}")
    if p.off not in ("u16", "u32", "auto"):
        raise ValueError(f"profile offsets {p.off!r} are not u16, u32 or auto")
    return p


def cell_box(cell, pitch, cell_h, box):
    """(x0, y0, wb, h) of a cell: x0, wb the byte span of the non-zero bytes, y0, h the rows holding one. A blank
    cell is (0, 0, 0, 0) in every policy; "full" gives (0, 0, pitch, cell_h) and "y" (0, y0, pitch, h) otherwise."""
    if box not in BOXES:
        raise ValueError(f"box policy {box!r} is not one of {BOXES}")
    rows = [cell[y * pitch:(y + 1) * pitch] for y in range(cell_h)]
    ys = [y for y, r in enumerate(rows) if any(r)]
    if not ys:
        return 0, 0, 0, 0
    y0, h = ys[0], ys[-1] - ys[0] + 1
    if box == "full":
        return 0, 0, pitch, cell_h
    if box == "y":
        return 0, y0, pitch, h
    xs = [x for y in ys for x in range(pitch) if rows[y][x]]
    return min(xs), y0, max(xs) - min(xs) + 1, h


def _row_bytes(wb, row):
    m = (1 << row) - 1
    return (wb + m) & ~m


def _phase(rec, row, wb, pitch, y0):
    return (y0 * pitch) & 3 if rec >= 2 and row == 0 and wb == pitch else 0


def encode_record(cell, pitch, cell_h, box, rec, row):
    """One glyph record: x0 y0 wb h, the phase bytes, h rows of rp bytes, zero padding to 2^rec."""
    if len(cell) != pitch * cell_h:
        raise ValueError("a glyph is not cell sized")
    x0, y0, wb, h = cell_box(cell, pitch, cell_h, box)
    out = bytearray((x0, y0, wb, h))
    if wb and h:
        rp = _row_bytes(wb, row)
        out += bytes(_phase(rec, row, wb, pitch, y0))
        for r in range(h):
            s = (y0 + r) * pitch + x0
            out += cell[s:s + wb] + bytes(rp - wb)
    unit = 1 << rec
    out += bytes(-len(out) % unit)
    return bytes(out)


def decode_record(buf, pitch, cell_h, rec, row):
    """The full cell of a glyph record; ValueError when the box leaves the cell or the rows leave the record."""
    if len(buf) < 4:
        raise ValueError(f"glyph record of {len(buf)} bytes is shorter than its 4 byte header")
    x0, y0, wb, h = buf[:4]
    if x0 + wb > pitch:
        raise ValueError(f"glyph record box x0 {x0} + wb {wb} is past the pitch {pitch}")
    if y0 + h > cell_h:
        raise ValueError(f"glyph record box y0 {y0} + h {h} is past the cell height {cell_h}")
    cell = bytearray(pitch * cell_h)
    if wb == 0 or h == 0:
        return bytes(cell)
    rp = _row_bytes(wb, row)
    p = 4 + _phase(rec, row, wb, pitch, y0)
    if p + h * rp > len(buf):
        raise ValueError(f"glyph record rows ({h} of {rp} bytes from {p}) are past its {len(buf)} bytes")
    for r in range(h):
        s = (y0 + r) * pitch + x0
        cell[s:s + wb] = buf[p + r * rp:p + r * rp + wb]
    return bytes(cell)


def _align(n, unit):
    return (n + unit - 1) & ~(unit - 1)


def pack_svfn(cell_w, cell_h, ascent, bpp, flags, cells, cmap, metrics=None, jset=None, dy_range=(0, 0),
              profile="default"):
    """The one SVFN v3 packer. @p cells: full cells in glyph index order; @p cmap: [(cp, index)] as written;
    @p metrics: [(advance, bearing_x, ink_w, dy)] by index or None; @p jset: block bytes or None. File order: header,
    code points, JSET, metrics, offset table, glyph data, each start rounded up to 2^tab (the glyph data to
    2^max(tab, rec)). Flag bits 0 and 1 come from @p metrics and @p jset, the others from @p flags."""
    pr = profile_of(profile)
    n = len(cells)
    if not 1 <= n <= 65535:
        raise ValueError(f"{n} glyphs: an SVFN face has 1..65535")
    if len(cmap) != n:
        raise ValueError(f"{len(cmap)} code points for {n} glyphs")
    if metrics is not None and len(metrics) != n:
        raise ValueError(f"{len(metrics)} metrics for {n} glyphs")
    if bpp not in (1, 2, 8):
        raise ValueError(f"bpp {bpp} is not 1, 2 or 8")
    jset = jset or None
    for name, v, lo, hi in (("cell width", cell_w, 1, 255), ("cell height", cell_h, 1, 255),
                            ("ascent", ascent, 0, 255), ("dy_min", dy_range[0], -128, 0),
                            ("dy_max", dy_range[1], 0, 127)):
        if not lo <= v <= hi:
            raise ValueError(f"{name} {v} is outside {lo}..{hi}")
    for i, m in enumerate(metrics or ()):
        for name, v, lo, hi in (("advance", m[0], 0, 255), ("bearing_x", m[1], -128, 127),
                                ("ink_w", m[2], 0, 255), ("dy", m[3], -128, 127)):
            if not lo <= v <= hi:
                raise ValueError(f"metrics[{i}] {name} {v} is outside {lo}..{hi}")
    prev = -1
    for cp, i in cmap:
        if not 0 <= i < n:
            raise ValueError(f"cmap code point {cp:#x} names glyph {i} of {n}")
        if not prev < cp <= 0xFFFFFFFF:
            raise ValueError(f"cmap code points are not strictly ascending at {cp:#x}")
        prev = cp
    pitch = (cell_w * bpp + 7) // 8
    recs = [encode_record(bytes(c), pitch, cell_h, pr.box, pr.rec, pr.row) for c in cells]
    sizes = [len(r) for r in recs]
    total = sum(sizes)
    if pr.off == "u16" and total > 65535 << pr.rec:
        raise ValueError(f"glyph data of {total} bytes does not fit u16 offsets at record unit {1 << pr.rec}")
    off32 = pr.off == "u32" or (pr.off == "auto" and total > 65535 << pr.rec)
    offs, acc = [], 0
    for sz in sizes:
        offs.append(acc)
        acc += sz
    offs.append(acc)
    table = (struct.pack("<%dI" % (n + 1), *offs) if off32
             else struct.pack("<%dH" % (n + 1), *[o >> pr.rec for o in offs]))
    cmap_b = b"".join(struct.pack("<II", cp, i) for cp, i in cmap)
    met_b = None if metrics is None else b"".join(
        struct.pack("<BbBb", a, bx, iw, d) for a, bx, iw, d in metrics)
    unit = 1 << pr.tab
    pos = HEADER3_SIZE
    where = {}
    for name, blob, u in (("cmap", cmap_b, unit), ("jset", jset, unit), ("metrics", met_b, unit),
                          ("table", table, unit), ("data", b"\0" * total, max(unit, 1 << pr.rec))):
        if blob is None:
            where[name] = 0
            continue
        pos = _align(pos, u)
        where[name] = pos
        pos += len(blob)
    fl = (flags & ~(FLAG_VARIABLE | FLAG_JAMO)) | (FLAG_VARIABLE if metrics is not None else 0) \
        | (FLAG_JAMO if jset is not None else 0)
    lo, hi = dy_range
    head = struct.pack(HEADER3, MAGIC, VERSION, fl, bpp, pr.rec | pr.row << 3, pr.tab | (8 if off32 else 0), 0, n,
                       cell_w, cell_h, ascent, lo, hi, 0, where["metrics"], where["data"], total,
                       where["cmap"], where["jset"], len(jset) if jset is not None else 0, where["table"])
    assert len(head) == HEADER3_SIZE
    out = bytearray(head)
    for name, blob in (("cmap", cmap_b), ("jset", jset), ("metrics", met_b), ("table", table),
                       ("data", b"".join(recs))):
        if blob is None:
            continue
        out += bytes(where[name] - len(out)) + blob
    return bytes(out)


def _parse_v3(data):
    if len(data) < HEADER3_SIZE:
        raise ValueError("SVFN v3: file shorter than its 48 byte header")
    (_, _, flags, bpp, b9, b10, _b11, count, cw, ch, ascent, dy_min, dy_max, _b19, met_off, data_off, data_size,
     cmap_off, jset_off, jset_size_h, tab_off) = struct.unpack_from(HEADER3, data)
    if flags & ~(FLAG_VARIABLE | FLAG_JAMO | FLAG_MARKS_AT_ORIGIN):
        raise ValueError(f"SVFN flags 0x{flags:04x}: unknown bits")
    if b9 & 0xC0:
        raise ValueError("SVFN v3 layout: byte 9 bits 6-7 are not zero")
    if b10 & 0xF0:
        raise ValueError("SVFN v3 layout: byte 10 bits 4-7 are not zero")
    rec, row, tab, off32 = b9 & 7, b9 >> 3 & 7, b10 & 7, bool(b10 & 8)
    if rec > 6 or row > 6 or tab > 6:
        raise ValueError(f"SVFN v3 layout: unit log2 past 6 (REC {rec} ROW {row} TAB {tab})")
    if row > rec:
        raise ValueError(f"SVFN v3 layout: ROW {row} is larger than REC {rec}")
    if bpp not in (1, 2, 8):
        raise ValueError(f"SVFN v3: bpp {bpp} is not 1, 2 or 8")
    if count < 1:
        raise ValueError("SVFN v3: no glyphs")
    if not cw or not ch:
        raise ValueError("SVFN v3: cell width or height is 0")
    size = len(data)
    tu, ru = 1 << tab, 1 << rec
    for name, v, u in (("metrics table", met_off, tu), ("glyph data", data_off, max(tu, ru)),
                       ("code point table", cmap_off, tu), ("JSET", jset_off, tu), ("glyph offset table", tab_off, tu)):
        if v % u:
            raise ValueError(f"SVFN v3 alignment: {name} offset {v} is not a multiple of {u}")
    if data_size % ru:
        raise ValueError(f"SVFN v3 alignment: glyph data size {data_size} is not a multiple of {ru}")
    ow = 4 if off32 else 2
    for name, v, n in (("code point table", cmap_off, 8 * count), ("glyph offset table", tab_off, ow * (count + 1)),
                       ("glyph data", data_off, data_size)):
        if v < HEADER3_SIZE or v + n > size:
            raise ValueError(f"SVFN v3 range: {name} {v}..{v + n} is outside the file or inside the header")
    f = Svfn()
    f.version, f.flags, f.bpp, f.cell_w, f.cell_h, f.ascent, f.count = 3, flags, bpp, cw, ch, ascent, count
    f.dy_min, f.dy_max = dy_min, dy_max
    f.layout = (rec, row, tab, off32)
    pitch = (cw * bpp + 7) // 8
    fmt = "<%d%s" % (count + 1, "I" if off32 else "H")
    offs = [o << (0 if off32 else rec) for o in struct.unpack_from(fmt, data, tab_off)]
    for i, o in enumerate(offs):
        if o % ru:
            raise ValueError(f"SVFN v3 alignment: offset entry {i} ({o}) is not a multiple of {ru}")
        if i and o < offs[i - 1]:
            raise ValueError(f"SVFN v3 offset table decreases at entry {i}")
    if offs[-1] != data_size:
        raise ValueError(f"SVFN v3 offset table: last entry {offs[-1]} is not the glyph data size {data_size}")
    cells = []
    for i in range(count):
        try:
            cells.append(decode_record(data[data_off + offs[i]:data_off + offs[i + 1]], pitch, ch, rec, row))
        except ValueError as e:
            raise ValueError(f"glyph {i}: {e}") from None
    f.metrics_ok = bool(flags & FLAG_VARIABLE) and met_off >= HEADER3_SIZE and met_off + 4 * count <= size
    f.glyphs, f.metrics, f.dy = {}, {}, {}
    for k in range(count):
        cp, idx = struct.unpack_from("<II", data, cmap_off + 8 * k)
        if idx >= count:
            raise ValueError(f"SVFN v3: code point {cp:#x} names glyph {idx} of {count}")
        f.glyphs[cp] = cells[idx]
        if f.metrics_ok:
            adv, ix, iw, dy = struct.unpack_from("<BbBb", data, met_off + idx * 4)
            f.metrics[cp] = (adv, ix, iw)
            if dy:
                f.dy[cp] = dy
    f.jset = None
    f.jset_bad = False
    if flags & FLAG_JAMO:
        # Spec (v3 design, JSET): a range outside the file or inside the header is a range error; a block that fails
        # validation, a size that disagrees with its counts, or a size of 0 with the flag set leaves a plain face
        # (SVF_FACE_JSET_BAD in C).
        if jset_size_h and (jset_off < HEADER3_SIZE or jset_off + jset_size_h > size):
            raise ValueError(f"SVFN v3 range: JSET {jset_off}..{jset_off + jset_size_h} is outside the file "
                             "or inside the header")
        blob = data[jset_off:jset_off + jset_size_h] if jset_size_h else b""
        try:
            t = unpack(blob)
            ok = jset_size_h == _jset_block_size(blob)
            # the engine's usable() rule, as the C reader: every piece number the block names has a glyph
            ok = ok and all(n == BLANK or PIECE_BASE + n in f.glyphs
                            for n in t.init_piece + t.med_piece + t.fin_piece + t.compat)
        except (ValueError, IndexError, TypeError):
            ok = False
        if ok:
            f.jset = blob
        else:
            f.jset_bad = True
    return f


def record_boxes(data):
    """[(x0, y0, wb, h)] of the glyph records of the SVFN v3 face @p data, in glyph index order (the 4 byte record
    headers; a blank glyph is (0, 0, 0, 0))."""
    f = _parse_v3(data)
    (_, _, _, _, _, _, _, count, _, _, _, _, _, _, _, data_off, _, _, _, _, tab_off) = struct.unpack_from(HEADER3, data)
    rec, off32 = f.layout[0], f.layout[3]
    offs = struct.unpack_from("<%d%s" % (count + 1, "I" if off32 else "H"), data, tab_off)
    shift = 0 if off32 else rec
    return [tuple(data[data_off + (offs[i] << shift):data_off + (offs[i] << shift) + 4]) for i in range(count)]


def parse_svfn(data):
    """An SVFN v3 file: header fields, glyph cells and metrics by code point, and the JSET block bytes (or None).
    ValueError on anything it cannot read, a truncated file and a version 1 or 2 file included (convert those with
    tools/svf2to3.py)."""
    if len(data) < 6 or data[:4] != MAGIC:
        raise ValueError("not an SVFN font")
    version = struct.unpack_from("<H", data, 4)[0]
    if version != VERSION:
        raise ValueError(f"SVFN version {version}: convert with tools/svf2to3.py")
    try:
        return _parse_v3(data)
    except (struct.error, IndexError) as e:
        raise ValueError(f"truncated or malformed SVFN file ({e})") from None


def add_profile_args(ap, default="default", none_help=None):
    """--profile and --box, the v3 layout options of every writer CLI. @p default None: the tool keeps the layout of
    the face it rewrites (face_profile); @p none_help then replaces the help's "default: default" with that text."""
    ap.add_argument("--profile", default=default, metavar="NAME",
                    help="SVFN v3 layout profile: " + ", ".join(PROFILES) + " or REC,ROW,TAB,OFF log2 units "
                         "(OFF 16 or 32); default: " + (none_help if default is None and none_help else "default"))
    ap.add_argument("--box", choices=BOXES, default=None,
                    help="ink box policy of the glyph records (x: bytes of the ink columns and rows; y: whole rows; "
                         "full: the whole cell); default: the profile's")


def _jset_version_type(v):
    if v == "auto":
        return v
    if v in ("1", "2"):
        return int(v)
    raise argparse.ArgumentTypeError(f"invalid choice: {v!r} (choose from 1, 2, auto)")


def add_jset_version_arg(ap, default=1):
    """--jset-version 1|2|auto and --jset-big of every writer CLI. 1 is the standard; 2 only on request; auto picks per face
    (choose_jset_version). @p default None: the tool decides (blank-compat keeps the input's version)."""
    ap.add_argument("--jset-version", type=_jset_version_type, default=default, metavar="{1,2,auto}",
                    help="JSET block version written: 1 (default, the standard), 2 (compact; only on request) or auto "
                         "(2 when it saves at least JSET_V2_MIN_SAVING bytes)" if default == 1 else
                         "JSET block version written: 1, 2 or auto (default 1; --blank-compat keeps the input's)")
    ap.add_argument("--jset-big", action="store_true",
                    help="allow a JSET over the standard limits (up to 19 x 28 classes, 128/128/64 sets); readers need "
                         "SVF_JSET_BIG. Output within the standard limits is identical with or without it")


def jset_line(data):
    """One line naming the JSET version of the face bytes @p data and both block sizes (v2 '-' when pack refuses)."""
    f = parse_svfn(data)
    t = unpack(f.jset)
    if isinstance(t, Jmap):
        return (f"jset=v3 jmap={len(f.jset)} ns={len(t.entries)} "
                + ("list=1 " if t.list_mode else "")
                + f"fallback={'v%d' % t.fallback_version if t.fallback is not None else 'none'}"
                + (" big=1" if t.fallback is not None and needs_big(t.fallback) else ""))
    try:
        v2 = str(len(pack(t, True).block))
    except ValueError:
        v2 = "-"
    return (f"jset=v{struct.unpack_from('<H', f.jset, 4)[0]} v1={len(pack_v1(t, True))} v2={v2}"
            + (" big=1" if needs_big(t) else ""))


def profile_arg(ap, args):
    """The Profile of @p args (--profile, --box), None when --profile was left unset (add_profile_args default None
    and no --profile), or ap.error (exit 2) when it is not one."""
    if args.profile is None:
        return None
    try:
        return profile_of(args.profile, args.box)
    except ValueError as e:
        ap.error(str(e))


def face_profile(f, profile=None, box=None):
    """@p profile when given, else the layout of the parsed face @p f (units of the v3 face, ink box policy @p box or x)."""
    if profile is not None:
        return profile
    rec, row, tab, off32 = f.layout
    return Profile(rec, row, tab, box or "x", "u32" if off32 else "u16")


def dy_range(dy, cell_h):
    """(dy_min, dy_max) of the per-glyph dy {cp: dy}: dy_min <= 0 <= dy_max, each within the cell's height."""
    vals = [int(v) for v in (dy or {}).values()]
    lo, hi = min([0] + vals), max([0] + vals)
    if -lo > cell_h or hi > cell_h or lo < -128 or hi > 127:
        raise ValueError(f"dy range {lo}..{hi} does not fit a {cell_h} row cell")
    return lo, hi


def write_svfn(cell_w, cell_h, ascent, glyphs, jset, extra_flags=0, bpp=1, dy=None, profile="default"):
    """@p glyphs: [(cp, packed bytes, advance, ink_x, ink_w)]. Written as SVFN v3 through pack_svfn in @p profile (a name,
    units string or Profile; a Profile carries the box policy). @p bpp: 1, 2 or 8 (rows of cell_w * bpp bits, padded to
    a byte). @p dy: {cp: dy} drawn dy rows below the cell position (metrics byte 3), the range in header bytes 17/18;
    None or {} writes 0 everywhere. The glyphs are stored in the order given (glyph index = position); the code point
    table is sorted."""
    glyphs = list(glyphs)
    stride = ((cell_w * bpp + 7) // 8) * cell_h
    if any(len(g[1]) != stride for g in glyphs):
        raise ValueError("a glyph is not cell sized")
    dy = {cp: int(v) for cp, v in (dy or {}).items() if v}
    dy_min, dy_max = dy_range(dy, cell_h)
    return pack_svfn(cell_w, cell_h, min(255, ascent), bpp, extra_flags, [g[1] for g in glyphs],
                     sorted((g[0], i) for i, g in enumerate(glyphs)),
                     [(min(255, g[2]), g[3], g[4], dy.get(g[0], 0)) for g in glyphs], jset or None,
                     (dy_min, dy_max), profile)


def relayout(data, profile, box=None):
    """The face @p data (v3) rewritten in @p profile (box policy @p box when given): same pixels, glyphs in code
    point order, the metrics and dy a reader would use (no table stays no table; dy 0 outside a valid range)."""
    f = parse_svfn(data)
    pr = profile_of(profile, box)
    cps = sorted(f.glyphs)
    cells = [f.glyphs[cp] for cp in cps]
    cmap = [(cp, i) for i, cp in enumerate(cps)]
    lo, hi = f.dy_min, f.dy_max
    dy_ok = f.metrics_ok and lo <= 0 <= hi and -lo <= f.cell_h and hi <= f.cell_h
    if not dy_ok:
        lo = hi = 0
    metrics = None
    if f.metrics_ok:
        metrics = []
        for cp in cps:
            a, bx, iw = f.metrics[cp]
            d = f.dy.get(cp, 0)
            metrics.append((a, bx, iw, d if dy_ok and lo <= d <= hi else 0))
    return pack_svfn(f.cell_w, f.cell_h, f.ascent, f.bpp, f.flags & FLAG_MARKS_AT_ORIGIN, cells, cmap, metrics,
                     f.jset, (lo, hi), pr)


# ---- the font -----------------------------------------------------------------

class EngCell:
    """A 12x24 ASCII face: glyph(cp) -> its rows as 16 bit ints (the file's two bytes, MSB left; MASCII24's right serifs and
    wide glyphs reach columns 12-15), the step @p adv (12) and the baseline row (the row below the ink of 'H')."""

    def __init__(self, w, h, getter, name, adv=None):
        self.w, self.h, self._get, self.name = w, h, getter, name
        self.adv = adv if adv is not None else w
        rows = self._get(ord("H"))
        used = [y for y, r in enumerate(rows) if r]
        self.baseline = used[-1] + 1 if used else h

    def glyph(self, cp):
        return self._get(cp)


def read_eng(d):
    """A raw 8x16 English font (2048 or 4096 bytes, row major) as bytes, or an EngCell for the 12x24 faces: an HBIOS
    $KROHN24 / Taebaek ROMAN24 / SANS24 (15,360 bytes: 256 glyphs of 60 bytes in a 16x30 cell, ink 12x24 in rows 3-26) or a
    Taebaek GASCII24 / MASCII24 .PFT (12,288 bytes: 256 glyphs of 48 bytes, 12x24 in 2 bytes a row)."""
    if len(d) == 15360:
        return EngCell(16, 24, lambda cp: g_rowmajor(d, cp * 60, 16, 30).rows[3:27], "hbios12x24", 12)
    if len(d) == 12288:
        return EngCell(16, 24, lambda cp: g_rowmajor(d, cp * 48, 16, 24).rows, "pft12x24", 12)
    if len(d) == 30720:		# Taebaek 3.5.1 GASCII40 / MASCII40: 256 glyphs, 40 rows of 3 bytes, ink 20 wide
        return EngCell(24, 40, lambda cp: g_rowmajor(d, cp * 120, 24, 40).rows, "pft20x40", 20)
    if len(d) == 49152:		# GASCII48 / MASCII48: 256 glyphs, 48 rows of 4 bytes, ink 24 wide
        return EngCell(32, 48, lambda cp: g_rowmajor(d, cp * 192, 32, 48).rows, "pft24x48", 24)
    if len(d) not in (2048, 4096):
        raise SourceError(f"an English font has 2048 or 4096 bytes (8x16), 15360 (HBIOS 12x24), 12288 (PFT 12x24), "
                          f"30720 (PFT 20x40) or 49152 (PFT 24x48), not {len(d)}")
    return d


def eng_glyph(eng, cp, w, h, bold=False):
    """An ASCII glyph in a w x h cell: an 8x16 one scaled by whole numbers (k = h // 16, at least 1), top left; an EngCell
    one at its own size, centred in height. Returns (Glyph, advance)."""
    if isinstance(eng, EngCell):
        rows = eng.glyph(cp)
        y0 = (h - eng.h) // 2
        out = [0] * h
        for y, r in enumerate(rows):
            if 0 <= y0 + y < h:
                r = (r << (w - eng.w)) if w >= eng.w else (r >> (eng.w - w))
                out[y0 + y] = (r | (r >> 1)) if bold else r		# placed in the cell first: column 15 gains column 16
        return Glyph(w, h, out), eng.adv
    k = max(1, h // 16)
    y0 = (h - 16 * k) // 2 if h > 16 * k else 0
    rows = [0] * h
    for y in range(min(h - y0, 16 * k)):
        src = eng[cp * 16 + y // k]
        r = 0
        for x in range(min(w, 8 * k)):
            r |= (src >> (7 - x // k) & 1) << (w - 1 - x)
        rows[y0 + y] = r
    if bold:
        rows = [r | (r >> 1) for r in rows]
    return Glyph(w, h, rows), 8 * k


def clipped_row(w, spans):
    """A w bit row (MSB left) with the columns of each (x0, x1) span set, clipped to 0..w-1."""
    v = 0
    for x0, x1 in spans:
        for x in range(max(0, x0), min(w, x1 + 1)):
            v |= 1 << (w - 1 - x)
    return v


def symbol_glyphs(w, h, ascent, adv):
    """{cp: (packed, advance, ink x, ink w)} for U+2026 (three 3x3 dots on the baseline, 4 px apart, centred in @p adv) and
    U+25A1 (the missing-glyph box, a 2 px outline up to 16 px square on the baseline), drawn for faces that bring neither.
    Whatever does not fit the cell (a cell narrower than the 11 px run of dots or the 16 px box) is clipped, not wrapped."""
    left = (adv - 11) // 2
    run = clipped_row(w, [(left + k * 4, left + k * 4 + 2) for k in range(3)])
    dots = [0] * h
    for y in range(max(0, ascent - 3), min(h, ascent)):
        dots[y] = run
    n = max(0, min(16, h - 2, w))
    x0 = (w - n) // 2
    box = [0] * h
    for k in range(n):
        y = ascent - n + k
        if 0 <= y < h:
            box[y] = clipped_row(w, [(x0, x0 + n - 1)]) if k in (0, 1, n - 2, n - 1) else \
                clipped_row(w, [(x0, x0 + 1), (x0 + n - 2, x0 + n - 1)])
    out = {}
    for cp, rows, a in ((0x2026, dots, adv), (0x25A1, box, w)):
        g = Glyph(w, h, rows)
        ix, iw = g.ink()
        out[cp] = (g.to_bytes(), a, ix, iw)
    return out


class BoldSource:
    """A Source whose pieces are each ORed with themselves shifted right one pixel (a 1 px horizontal embolden; the OR of
    emboldened pieces is the emboldened syllable, so it stays a jamo set)."""

    def __init__(self, src):
        self.w, self.h, self.count, self._src = src.w, src.h, src.count, src

    def glyph(self, i):
        g = self._src.glyph(i)
        return Glyph(g.w, g.h, [r | (r >> 1) for r in g.rows])


def build(layout, data, face=0, eng=None, base=None, path="", jset_version=1, jset_big=False):
    """The font file's bytes, and the (source index -> piece number) mapping."""
    return build_from_source(layout, layout.opener(data, face, path), eng, base, jset_version=jset_version,
                             jset_big=jset_big)


def build_from_source(layout, src, eng=None, base=None, ascent=None, extra=None, keep_header=False, advance=None,
                      bold=False, symbols=False, profile="default", jset_version=1, jset_big=False):
    """Write the font from @p src's pieces. @p extra: {cp: (packed glyph, advance, ink x, ink w)} added first (the base
    and --eng glyphs override it). @p keep_header: take all of the base's flag bits except the
    two this tool sets, not just MARKS_AT_ORIGIN. @p advance: the JSET advance byte (what a composed syllable steps
    by; 0 means the cell width), instead of the layout's. @p bold: embolden the pieces and the ASCII 1 px to the right.
    @p symbols: add U+2026 and U+25A1 (symbol_glyphs) unless the base or @p extra bring them. @p profile: the v3
    layout profile (write_svfn). @p jset_version: 1 (the standard), 2 or "auto" (pack_jset); @p jset_big: counts up to the BIG row; the returned mapping is
    source index -> the piece number before version 2 renumbers (len = pieces written)."""
    if bold:
        src = BoldSource(src)
    tables = tables_for(layout)
    if advance is not None:
        tables.advance = advance
    parsed = parse_svfn(base) if base is not None else None
    whole = {cp for cp, g in (parsed.glyphs.items() if parsed else ()) if any(g)}
    whole |= {cp for cp, g in (extra or {}).items() if any(g[0])}
    blank_compat(tables, whole)
    used = used_pieces(tables)
    mapping = {s: n for n, s in enumerate(used)}
    pieces = renumber(tables, mapping)
    w, h = src.w, src.h
    if ascent is None and isinstance(eng, EngCell):
        ascent = (h - eng.h) // 2 + eng.baseline
    ascent = ascent or max(1, round(h * 0.875))
    glyphs = {}
    dy = {}
    flags = 0
    for s in used:
        g = src.glyph(s)
        ix, iw = g.ink()
        glyphs[PIECE_BASE + mapping[s]] = (g.to_bytes(), w, ix, iw)
    if extra:
        glyphs.update(extra)
    if base is not None:
        b = parsed
        if (b.bpp, b.cell_w, b.cell_h) != (1, w, h):
            raise SourceError(f"base is {b.cell_w}x{b.cell_h} {b.bpp} bpp, the pieces are {w}x{h} 1 bpp")
        ascent = b.ascent or ascent
        if keep_header:
            flags |= b.flags & ~(FLAG_VARIABLE | FLAG_JAMO)
        else:
            flags |= b.flags & FLAG_MARKS_AT_ORIGIN
        for cp, gbytes in b.glyphs.items():
            if 0xAC00 <= cp <= 0xD7A3 or cp >= PIECE_BASE:
                continue
            m = b.metrics.get(cp)
            glyphs[cp] = (gbytes, m[0] if m else w, m[1] if m else 0, m[2] if m else 0)
            if cp in b.dy:
                dy[cp] = b.dy[cp]
    if eng is not None:
        for cp in range(0x20, 0x7F):
            dy.pop(cp, None)
            g, adv = eng_glyph(eng, cp, w, h, bold)
            ix, iw = g.ink()
            glyphs[cp] = (g.to_bytes(), min(adv, w // 2) if w < 16 else adv, ix, iw)
    if symbols:
        adv = glyphs[0x20][1] if 0x20 in glyphs else w // 2
        for cp, g in symbol_glyphs(w, h, ascent, adv).items():
            glyphs.setdefault(cp, g)
    packed = pack_jset(pieces, jset_version, jset_big)
    glyphs = [(cp, g[0], g[1], g[2], g[3]) for cp, g in sorted(glyphs.items())]
    out = write_svfn(w, h, ascent, sorted(renumber_glyphs(glyphs, packed.piece_map)), packed.block, flags,
                     dy=dy, profile=profile)
    return out, mapping, src


def blank_whole_compat(data, profile="default", jset_version=None, jset_big=False):
    """The jamo-set face @p data with every compat jamo it has a whole glyph for left to that glyph (blank_compat), and the
    pieces nothing draws any more dropped (set tables only: a JMAP keeps every piece and its block stays version 3, its
    own and its fallback's compat entries blanked). For faces written before build_from_source did this. @p jset_big: as
    pack_jset (set tables only). @p jset_version: 1, 2
    or "auto"; None keeps the version of the input's block."""
    f = parse_svfn(data)
    if not f.flags & FLAG_JAMO or f.jset is None:
        raise ValueError("not a jamo-set font (flag bit 1 or the JSET block is missing)")
    if jset_version is None:
        jset_version = struct.unpack_from("<H", f.jset, 4)[0]
    t = unpack(f.jset)
    blank_compat(t, {cp for cp, g in f.glyphs.items() if cp < PIECE_BASE and any(g)})
    if isinstance(t, Jmap):
        # no renumbering of a JMAP's pieces: the block keeps every piece, only its compat entries change
        if jset_version not in (None, 3):
            raise ValueError("a JMAP block has no set tables: it stays version 3")
        glyphs = [(cp, g) + tuple(f.metrics[cp]) for cp, g in f.glyphs.items()]
        return write_svfn(f.cell_w, f.cell_h, f.ascent, glyphs, pack_jmap(t, t.fallback_block),
                          f.flags & ~(FLAG_VARIABLE | FLAG_JAMO), f.bpp, dy=dict(f.dy), profile=profile)
    used = used_pieces(t)
    mapping = {p: n for n, p in enumerate(used)}
    t = renumber(t, mapping)
    glyphs = []
    dy = {}
    for cp, g in f.glyphs.items():
        new = cp
        if cp >= PIECE_BASE:
            if cp - PIECE_BASE not in mapping:
                continue
            new = PIECE_BASE + mapping[cp - PIECE_BASE]
        m = f.metrics[cp]
        glyphs.append((new, g, m[0], m[1], m[2]))
        if cp in f.dy:
            dy[new] = f.dy[cp]
    packed = pack_jset(t, jset_version, jset_big)
    return write_svfn(f.cell_w, f.cell_h, f.ascent, renumber_glyphs(glyphs, packed.piece_map), packed.block,
                      f.flags & ~(FLAG_VARIABLE | FLAG_JAMO), f.bpp, dy=renumber_glyphs(dy, packed.piece_map),
                      profile=profile)


# ---- composing and checking --------------------------------------------------------

def compose(svfn, t, cp):
    """The syllable as the engine draws it: the maximum coverage of its pieces at each pixel, i.e. the OR of their rows
    at 1 bpp (glyph_source_jamo.cpp maxRow). None if not a syllable."""
    nums = pieces_of(t, cp)
    if nums is None:
        return None
    bpp = getattr(svfn, "bpp", 1)
    stride = ((svfn.cell_w * bpp + 7) // 8) * svfn.cell_h
    out = bytearray(stride)
    for n in nums:
        if n == BLANK:
            continue
        piece = svfn.glyphs[PIECE_BASE + n]
        if bpp == 1:
            for k in range(stride):
                out[k] |= piece[k]
        elif bpp == 8:
            for k in range(stride):
                out[k] = max(out[k], piece[k])
        else:
            for k in range(stride):
                a, b = out[k], piece[k]
                if b:
                    v = 0
                    for sh in (6, 4, 2, 0):
                        v |= max((a >> sh) & 3, (b >> sh) & 3) << sh
                    out[k] = v
    return bytes(out)


def check_dy(f):
    """The per-glyph dy of the parsed face @p f: within its header range, the range within the cell, and none on a
    piece (the engine composes a syllable in its cell; a piece moved by a dy would move part of it)."""
    if f.dy_min > 0 or f.dy_max < 0 or -f.dy_min > f.cell_h or f.dy_max > f.cell_h:
        raise ValueError(f"dy range {f.dy_min}..{f.dy_max} is not valid for a {f.cell_h} row cell")
    out = [cp for cp, v in f.dy.items() if not f.dy_min <= v <= f.dy_max]
    if out:
        raise ValueError(f"{len(out)} glyphs have a dy outside {f.dy_min}..{f.dy_max}, first U+{min(out):04X}")
    pieces = [cp for cp in f.dy if cp >= PIECE_BASE]
    if pieces:
        raise ValueError(f"{len(pieces)} jamo pieces have a dy, first U+{min(pieces):04X}")


def check(out_bytes, layout, src_bytes):
    """Parse the written font back and compose all 11,172 syllables with the engine's rule. For layout 844 at
    16x16 the result must equal johab844.py's composition of the source, byte for byte. Returns a message."""
    f = parse_svfn(out_bytes)
    if not f.flags & FLAG_JAMO or f.jset is None:
        raise ValueError("flag bit 1 or the JSET block is missing")
    t = unpack(f.jset)
    for p in [x for lst in (t.init_piece, t.med_piece, t.fin_piece) for x in lst] + t.compat:
        if p != BLANK and PIECE_BASE + p not in f.glyphs:
            raise ValueError(f"piece {p} has no glyph")
    composed = {cp: compose(f, t, cp) for cp in range(0xAC00, 0xD7A4)}
    msg = f"composed 11172 syllables from {len(f.glyphs)} glyphs, JSET {len(f.jset)} bytes"
    check_dy(f)
    if f.dy:
        msg += f"; dy {f.dy_min}..{f.dy_max} on {len(f.dy)} glyphs"
    if layout.name == "adaptive":
        want = tables_for(layout)
        for attr in ("lead_class", "tail_class", "init_set", "med_set", "fin_set"):
            if getattr(t, attr) != getattr(want, attr):
                raise ValueError(f"the written JSET {attr} differs from the adaptive layout")
        msg += f"; tables are the adaptive layout's ({t.ni}/{t.nm}/{t.nf} sets, {t.lc}x{t.tc} classes)"
    if layout.name == "844" and (f.cell_w, f.cell_h) == (16, 16) and src_bytes is not None:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))	# python -I drops the script's directory
        import johab844
        off = 2 if len(src_bytes) == 11522 else 0
        jamo = src_bytes[off:off + 360 * 32]
        bad = [cp for cp in composed if composed[cp] != johab844.compose(jamo, cp)]
        if bad:
            raise ValueError(f"{len(bad)} syllables differ from johab844.py, first U+{bad[0]:04X}")
        msg += "; identical to johab844.py"
    return msg


# ---- fitting pieces to precomposed syllables (--from-ttf, --from-svf) ---------------------------------------

def mask_font_beside(tools_dir):
    """The Noto Sans KR of the ScummVM tree that holds svf-fonts as dists/svf-fonts (its
    dists/engine-data/fonts/fonts-cjk), or None (a standalone svf-fonts checkout has none)."""
    p = os.path.join(tools_dir, "..", "..", "engine-data", "fonts", "fonts-cjk", "NotoSansKR-Regular.otf")
    return p if os.path.exists(p) else None


DEFAULT_MASK_FONT = mask_font_beside(os.path.dirname(os.path.abspath(__file__)))


def _jamoaa():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))	# python -I drops the script's directory
    import jamoaa
    return jamoaa


def _jamofit():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))	# python -I drops the script's directory
    import jamofit
    return jamofit


def default_mask_font():
    """--mask-font's default: $JAMOSET_MASK_FONT, else the NotoSansKR of the ScummVM tree around the submodule."""
    for p in (os.environ.get("JAMOSET_MASK_FONT"), DEFAULT_MASK_FONT):
        if p and os.path.exists(p):
            return p
    return None


def auto_radius(w, h):
    n = max(w, h)
    return 1 if n <= 16 else 2 if n <= 24 else 3


class FittedSource:
    """Pieces as a Source: a glyph per source index, from the fit (blank where nothing fills it)."""

    def __init__(self, w, h, rows_by_piece, count):
        self.w, self.h, self.count = w, h, count
        self._rows = rows_by_piece

    def glyph(self, i):
        return Glyph(self.w, self.h, list(self._rows.get(i) or [0] * self.h))


def piece_roles(layout):
    """{source index: (slot, set, jamo)} for every piece the layout's tables name (slot 0 initial, 1 medial, 2 final)."""
    t = tables_for(layout)
    roles = {}
    for slot, (lst, n) in enumerate(((t.init_piece, 19), (t.med_piece, 21), (t.fin_piece, 27))):
        for i, p in enumerate(lst):
            if p != BLANK:
                roles.setdefault(p, (slot, i // n, i % n))
    return t, roles


def _ancestor_piece(layout, roles, have, slot, st, jm):
    """For a layout with set ancestry (jamoadapt: Layout.fallback), the same jamo's piece in the nearest set this one
    was split from that @p have holds; else None."""
    order = getattr(layout, "fallback", None)
    if order is None or slot is None:
        return None
    for anc in order(slot, st):
        for q, r in roles.items():
            if r == (slot, anc, jm) and q in have:
                return q
    return None


AUTO_EXACT = 0.995		# a free fit this good means the face already is an OR of pieces: nothing for a mask to decide


def fit_font(layout, targets, w, h, ascent=None, eng=None, base=None, extra=None, keep_header=False,
             mask_font=None, radius=None, passes=12, pylib=None, mask_auto=False, advance=None, piece_masks=None,
             speck=0, profile="default", jset_version=1, jset_big=False):
    """Fit the layout's pieces to @p targets ({syllable index: gint}) and write the font.

    With @p mask_auto the free fit comes first; if its mean IoU is at least AUTO_EXACT the face is itself an OR of
    pieces (a DOS face made from a jamo set) and the free pieces are kept, since a mask can only move them away from
    the exact answer; otherwise the masked fit is used. Returns (font bytes, info dict). Pieces no target syllable uses (a (set, jamo) pair the face never draws) take the
    same jamo's piece of another set (the one with most users) and, failing that, the mask font's variant.
    @p piece_masks: {piece: gint} confining the pieces (jamoaa.donor_masks; used instead of a mask font). @p speck:
    then drop components of at most this many pixels that the composed syllables do not need (jamoaa.remove_specks).
    @p profile: the v3 layout profile of the file (write_svfn).
    """
    jf = _jamofit()
    t, roles = piece_roles(layout)
    syl_keys = {}
    for s in range(11172):
        ps = pieces_of(t, 0xAC00 + s)
        syl_keys[s] = tuple(None if p == BLANK else p for p in ps) + (None,) * (3 - len(ps))
    masks, mask_all, info = None, {}, {"mask_font": None}
    full = jf.full_mask(w, h)
    keys = {s: syl_keys[s] for s in targets}
    P = finfo = None
    if piece_masks is not None:
        mask_font = None
        masks = piece_masks
        info["mask_font"] = "donor support"
    if mask_font and mask_auto:
        P, finfo = jf.fit_pieces(keys, targets, w, h, None, passes)
        free_iou = jf.mean_iou(P, keys, targets)
        info["free_fit_iou"] = round(free_iou, 4)
        if free_iou >= AUTO_EXACT:
            info["mask_decision"] = "free fit kept (it already composes the face)"
            mask_font = None
        else:
            info["mask_decision"] = "masked fit (the free fit is not exact)"
            P = None
    if mask_font:
        mask_all, minfo = jf.mask_pieces(mask_font, syl_keys, w, h, targets, pylib)
        r = radius if radius is not None else auto_radius(w, h)
        masks = {k: jf.dilate(g, w, full, r) for k, g in mask_all.items()}
        info.update(minfo, mask_radius=r)
    if P is None:
        P, finfo = jf.fit_pieces(keys, targets, w, h, masks, passes, True if piece_masks is not None else None)
    users = finfo.pop("users")
    info.update(finfo)
    if speck:
        info["specks_removed"] = _jamoaa().remove_specks(P, keys, targets, w, h, speck)
    rows = {k: jf.to_rows(g, w, h) for k, g in P.items()}
    fallback = {"sibling": 0, "mask": 0, "blank": 0}
    for p in sorted(used_pieces(t)):
        if p in P:
            continue
        slot, st, jm = roles.get(p, (None, 0, 0))
        sib = [(users[q], -q) for q, (sl, s2, j2) in roles.items() if sl == slot and j2 == jm and q in P]
        anc = _ancestor_piece(layout, roles, P, slot, st, jm)
        if anc is not None:
            rows[p] = rows[anc]
            fallback["parent"] = fallback.get("parent", 0) + 1
        elif sib:
            rows[p] = rows[-max(sib)[1]]
            fallback["sibling"] += 1
        elif p in mask_all:
            rows[p] = jf.to_rows(mask_all[p], w, h)
            fallback["mask"] += 1
        else:
            fallback["blank"] += 1
    info["unseen_pieces"] = fallback
    count = max(roles) + 1 if roles else 0
    out, mapping, _ = build_from_source(layout, FittedSource(w, h, rows, count), eng, base, ascent, extra, keep_header, advance,
                                       profile=profile, jset_version=jset_version, jset_big=jset_big)
    info["pieces"] = len(mapping)
    return out, info


def glyph_gint(gbytes, w, h):
    nb = (w + 7) // 8
    jf = _jamofit()
    return jf.from_rows([int.from_bytes(gbytes[y * nb:(y + 1) * nb], "big") >> (nb * 8 - w) for y in range(h)], w)


def fit_report(out, targets, w, h):
    """Parse the written font back, compose every target syllable with the engine's rule, score against the targets."""
    jf = _jamofit()
    f = parse_svfn(out)
    if not f.flags & FLAG_JAMO or f.jset is None:
        raise ValueError("flag bit 1 or the JSET block is missing")
    t = unpack(f.jset)
    cells = {s: compose(f, t, 0xAC00 + s) for s in targets}
    # a syllable a JMAP face does not compose (a miss) is left out of the score, not scored as a TypeError
    composed = {s: glyph_gint(c, w, h) for s, c in cells.items() if c is not None}
    return jf.quality_report({s: targets[s] for s in composed}, composed, w, h)


def svf_advance(face):
    """The step of the face's drawn syllables (the most common advance among them), or None for a face with no
    metrics table or one whose advance does not fit the JSET byte.

    A precomposed face keeps a syllable's advance in its metrics (neodgm's 16 in a 26 px cell); a jamo set steps by
    its JSET advance, which is the cell width when 0. Without this the composed syllable would step by the cell and
    the engine, which centres a syllable stepping less than the game cell, would no longer centre it.
    """
    count = {}
    for cp, gb in face.glyphs.items():
        m = face.metrics.get(cp)
        if m and 0xAC00 <= cp <= 0xD7A3 and any(gb):
            count[m[0]] = count.get(m[0], 0) + 1
    if not count:
        return None
    adv = max(count, key=lambda a: (count[a], a))
    return adv if 0 < adv < 256 else None


def svf_targets(face):
    """{syllable index: gint} of the non-blank precomposed syllables of a parsed 1 bpp SVFN face."""
    w, h = face.cell_w, face.cell_h
    out = {}
    for cp, gb in face.glyphs.items():
        if 0xAC00 <= cp <= 0xD7A3 and any(gb):
            out[cp - 0xAC00] = glyph_gint(gb, w, h)
    return out


# ---- Mac HangulTalk 1.0 'fbit' fonts (--layout mac-fbit-45sets) --------------------------------------------------------
#
# Gotic12/16 and Munjo12/16/24 of Korean System 4.1 (resource fork, type 'fbit'): 45 glyph sets of one cell size, a syllable
# is the OR of an initial, a medial and (with a final) a final glyph, picked by the 68k 'fdef' driver from 18 lookup tables
# (from the johab-fonts research notes, not in this repository). The set system is not a fixed table: mac_layout() derives
# the JSET tables from the font's own rule - lead and tail classes are the sets of jamo that no syllable tells apart, the
# initial sets are the distinct columns of initial glyphs, the medial sets are numbered per vowel - and every syllable
# composes to the Mac rendering bit for bit. It needs 8 lead classes, 4 tail classes and 20 initial sets, more than the
# first JSET readers took (4 / 4 / 16): the JSET limits became 8 / 8 / 24 for classes and initial sets (16 medial, 16 final), and in 2026-10 12 / 12 / 24 for
# more class detail in adaptive faces (MAX_LEAD_CLASSES; engines built before then reject more than 8 classes), and in 2026-10 (v3) 32 / 24 / 16 sets.

MAC_PLANE_TABLES = dict(A=(0x524, 32), B=(0x558, 32), C=(0x578, 32), D=(0x598, 32), Gm=(0x5b8, 32), G=(0x5d8, 10),
                        S=(0x5e2, 32), F=(0x602, 32), I=(0x622, 32), H=(0x642, 6), J=(0x648, 32), M=(0x668, 6),
                        O=(0x66e, 32), N=(0x68e, 8), K=(0x696, 32), R=(0x6b6, 32), P=(0x6d6, 32), Q=(0x6f6, 32))
MAC_LAYOUT = "mac-fbit-45sets"
MAC_REMAP = (0, 1, 0x13, 0x14, 0x15, 0x16, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 0x17, 0x18, 0x12)


def mac_resources(d):
    """{type (bytes): {id: data}} of a raw Mac resource fork."""
    dofs, mofs, dlen, mlen = struct.unpack(">4I", d[:16])
    m = d[mofs:mofs + mlen]
    tl, nl, n1 = struct.unpack(">HHH", m[24:30])
    out = {}
    for i in range((n1 + 1) & 0xFFFF):
        typ, cnt1, rofs = struct.unpack(">4sHH", m[tl + 2 + i * 8:tl + 10 + i * 8])
        for j in range(cnt1 + 1):
            rid, _noff, ao = struct.unpack(">hHI", m[tl + rofs + j * 12:tl + rofs + j * 12 + 8])
            doff = dofs + (ao & 0xFFFFFF)
            ln = struct.unpack(">I", d[doff:doff + 4])[0]
            out.setdefault(typ, {})[rid] = d[doff + 4:doff + 4 + ln]
    return out


def mac_compose(tb, L, V, T):
    """Johab 5-bit fields -> [(set, glyph)] of the initial, medial and final planes (the 'fdef' driver of HangulTalk 1.0)."""
    out = []
    if L != 1:
        g = tb["A"][L]
        if T == 1:
            s = tb["B"][V] // 2
        else:
            c = tb["C"][V]
            s = 8 + (c & 0x3f) // 2
            if c & 0xc0:
                if tb["D"][T] & 0x80:
                    s += 1
                if c & 0x40:
                    g = MAC_REMAP[g]
        out.append((s, g))
    if V != 2:
        g = tb["Gm"][V]
        sel = tb["S"][V]
        if sel == 0:
            if T == 1:
                s = 18
            else:
                s = 19 + (1 if tb["D"][T] & 0x80 else 0)
                if tb["F"][L] & 0x80:
                    g = tb["G"][g]
        elif sel == 2:
            if T == 1:
                s = 21
                d0, d4 = tb["H"][g], tb["I"][L]
                mod = True
            else:
                s = 22 + tb["J"][L] // 2
                d0 = tb["K"][T]
                d4 = tb["M"][g] if d0 & 0xc0 else 0
                mod = bool(d0 & 0xc0)
            if mod and (d0 & 0xf0) & (d4 & 0xf0):
                g = (g + ((d0 + d4) & 0xf)) & 0xff
        else:
            s = 26
            if T != 1:
                s = 31
                d4 = tb["K"][T]
                d0 = tb["N"][g]
                if (d0 & 0xf0) & (d4 & 0xf0):
                    s = 36
            s += tb["O"][L] // 2
        out.append((s, g))
    if T != 1:
        s = 41
        d0 = tb["P"][V]
        if d0 & 0x80 and tb["Q"][L] & 0x80:
            s += 1
        s += (d0 & 0x3f) // 2
        out.append((s, tb["R"][T]))
    return out


class MacFbit:
    """A HangulTalk 1.0 'fbit' font file (a raw resource fork): its glyph sets and the 'fdef' lookup tables."""

    def __init__(self, data):
        try:
            res = mac_resources(data)
            self.fbit = next(iter(res[b"fbit"].values()))
            fdef = res[b"fdef"][3]
        except (KeyError, StopIteration, struct.error, IndexError):
            raise SourceError("not a HangulTalk 1.0 'fbit' resource fork (no fbit or fdef 3 resource)")
        if len(self.fbit) < 0x56 or self.fbit[2:6] != b"fbit" or len(fdef) < 0x716:
            raise SourceError("not a HangulTalk 1.0 'fbit' font")
        self.tb = {k: fdef[o:o + n] for k, (o, n) in MAC_PLANE_TABLES.items()}
        nset = struct.unpack(">H", self.fbit[0x54:0x56])[0] // 12
        if nset != 45:
            raise SourceError(f"{nset} glyph sets, not the 45 of mac-fbit-45sets")
        self.base = 0x56 + nset * 12
        if len(self.fbit) < self.base:
            raise SourceError(f"'fbit' resource is {len(self.fbit)} bytes, shorter than its {nset} set descriptors ({self.base})")
        self.sets = []
        for i in range(nset):
            w0, hi, off, h = struct.unpack(">4H", self.fbit[0x56 + i * 12:0x56 + i * 12 + 8])
            if not w0 or not h:
                raise SourceError(f"glyph set {i} has a zero width or height")
            if self.base + ((hi << 16) | off) > len(self.fbit):
                raise SourceError(f"glyph set {i} starts beyond the end of the 'fbit' resource")
            self.sets.append((w0 * 4, (hi << 16) | off, h))
        self.w, self.h = self.sets[0][0], self.sets[0][2]

    def set_glyph(self, s, g):
        bpr, off, h = self.sets[s]
        gb = bpr * h // 8
        o = self.base + off + g * gb
        v = int.from_bytes(self.fbit[o:o + gb], "big")
        return Glyph(bpr, h, [(v >> (gb * 8 - (y + 1) * bpr)) & ((1 << bpr) - 1) for y in range(h)])

    def syllable(self, s):
        """The Mac rendering of syllable index @p s (U+AC00 + s) as a Glyph."""
        L, V, T = s // 588, (s // 28) % 21, s % 28
        r = None
        for st, g in mac_compose(self.tb, L + 2, JUNG_FIELD[V], T + 1 if T <= 16 else T + 2):
            gl = self.set_glyph(st, g)
            r = gl if r is None else Glyph(gl.w, gl.h, [a | b for a, b in zip(r.rows, gl.rows)])
        return r


def ks_x_1001_syllables():
    """Syllable indices (U+AC00 + n) of the 2,350 KS X 1001 Hangul."""
    return sorted(ord(bytes([hi, lo]).decode("cp949")) - 0xAC00 for hi in range(0xB0, 0xC9) for lo in range(0xA1, 0xFF))


class MacSource:
    """The pieces of a MacFbit as a Source: piece n is the glyph numbered n over all 45 sets, in set order."""

    def __init__(self, mac):
        self.w, self.h, self.mac = mac.w, mac.h, mac
        starts = [off for _, off, _ in mac.sets] + [len(mac.fbit) - mac.base]
        self.first, n = [], 0
        for i, (bpr, off, h) in enumerate(mac.sets):
            self.first.append(n)
            n += (starts[i + 1] - off) // (bpr * h // 8)
        self.count = n

    def index(self, s, g):
        return self.first[s] + g

    def glyph(self, i):
        s = max(k for k in range(len(self.first)) if self.first[k] <= i)
        return self.mac.set_glyph(s, i - self.first[s])


def mac_layout(mac):
    """(Layout, MacSource) of a MacFbit, the JSET tables derived from its rule and checked against it by build/check."""
    src = MacSource(mac)
    jam = lambda L, V, T: (L + 2, JUNG_FIELD[V], T + 1 if T <= 16 else T + 2)

    def planes(L, V, T):
        d = {"i": None, "m": None, "f": None}
        for s, g in mac_compose(mac.tb, *jam(L, V, T)):
            d["i" if s <= 17 else "m" if s <= 40 else "f"] = (s, g)
        return d

    def classes(n, sig):
        ids, out = {}, []
        for x in range(n):
            out.append(ids.setdefault(sig(x), len(ids)))
        return out, len(ids)

    lead, lc = classes(19, lambda L: tuple((lambda d: (d["m"], d["f"] and d["f"][0]))(planes(L, V, T))
                                           for V in range(21) for T in range(28)))
    tail, tc = classes(28, lambda T: tuple((lambda d: (d["i"], d["m"], d["f"] and d["f"][0]))(planes(L, V, T))
                                           for L in range(19) for V in range(21)))
    rep_l = {c: lead.index(c) for c in range(lc)}
    rep_t = {c: tail.index(c) for c in range(tc)}
    init_cols, init_id = [], {}
    med_keys = [[] for _ in range(21)]
    fin_keys = []
    cell_init, cell_med, cell_fin = {}, {}, {}
    for c in range(lc):
        for V in range(21):
            for k in range(tc):
                L, T = rep_l[c], rep_t[k]
                col = tuple(planes(x, V, T)["i"] for x in range(19))
                if col not in init_id:
                    init_id[col] = len(init_cols)
                    init_cols.append(col)
                cell_init[c, V, k] = init_id[col]
                d = planes(L, V, T)
                if d["m"] not in med_keys[V]:
                    med_keys[V].append(d["m"])
                cell_med[c, V, k] = med_keys[V].index(d["m"])
                if d["f"] is not None:
                    if d["f"][0] not in fin_keys:
                        fin_keys.append(d["f"][0])
                    cell_fin[c, V, k] = fin_keys.index(d["f"][0])
    final_tc = {tail[T] for T in range(1, 28)}
    ni, nm, nf = len(init_cols), max(len(m) for m in med_keys), max(1, len(fin_keys))

    def init_src(s, L):
        x = init_cols[s][L]
        return None if x is None else src.index(*x)

    def med_src(s, V):
        return src.index(*med_keys[V][s]) if s < len(med_keys[V]) and med_keys[V][s] else None

    def fin_src(s, T):
        return src.index(fin_keys[s] if s < len(fin_keys) else 41, mac.tb["R"][jam(0, 0, T)[2]])

    layout = Layout(MAC_LAYOUT, None, lc, tc, ni, nm, nf, lambda L: lead[L], lambda T: tail[T],
                    lambda c, V, k: cell_init[c, V, k], lambda c, V, k: cell_med[c, V, k],
                    lambda c, V, k: cell_fin.get((c, V, k), 0), init_src, med_src, fin_src, advance=0)
    layout.final_tail_classes = final_tc
    return layout, src


MAC_GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata", "mac-fbit-golden.json")


def mac_golden(source):
    """The golden entry (testdata/mac-fbit-golden.json) for the Mac font file named @p source (Munjo24.rsrc -> "munjo24"), or None.
    The golden bitmaps come from the research renderer mac_kfont.py, not from this file's mac_compose()."""
    import json
    try:
        with open(MAC_GOLDEN) as fh:
            faces = json.load(fh)["faces"]
    except (OSError, ValueError, KeyError):
        return None
    return faces.get(os.path.splitext(os.path.basename(source))[0].lower())


def mac_golden_problems(out, entry):
    """What differs between the font @p out (SVFN bytes) and a golden entry: the 2,350 KS X 1001 syllables composed from the
    font, hashed, and the sampled ones compared one by one. [] when identical."""
    import hashlib
    f = parse_svfn(out)
    t = unpack(f.jset)
    probs = []
    if (f.cell_w, f.cell_h) != (entry["w"], entry["h"]):
        return [f"cell {f.cell_w}x{f.cell_h}, golden is {entry['w']}x{entry['h']}"]
    bits = [compose(f, t, 0xAC00 + s) for s in ks_x_1001_syllables()]
    if hashlib.sha256(b"".join(bits)).hexdigest() != entry["sha256"]:
        probs.append("sha256 of the 2,350 KS X 1001 syllables differs")
    for cp, hexa in entry["samples"].items():
        if compose(f, t, int(cp, 16)).hex() != hexa:
            probs.append(f"U+{cp} differs")
    return probs


def mac_targets(mac):
    """{syllable index: gint} of the Mac rendering of all 11,172 syllables."""
    return {s: glyph_gint(mac.syllable(s).to_bytes(), mac.w, mac.h) for s in range(11172)}


def mac_compare(out, targets, w, h):
    """Compose every syllable of the written font and compare it with the Mac rendering: (quality report, the syllable
    indices that differ)."""
    f = parse_svfn(out)
    t = unpack(f.jset)
    composed = {s: glyph_gint(compose(f, t, 0xAC00 + s), w, h) for s in range(11172)}
    return _jamofit().quality_report(targets, composed, w, h), [s for s in range(11172) if composed[s] != targets[s]]


def ink_clipped(iw, ih, w, h, oy, top, bottom):
    """Whether the union ink box (iw x ih, pen-relative @p top and @p bottom rows) does not fit the w x h cell with the baseline
    at row @p oy: its top row is oy - top and its bottom row oy - bottom, which must be 0..h-1 (so oy - bottom == h is clipped)."""
    return bool(iw > w or ih > h or oy - top < 0 or oy - bottom >= h)


def ttf_targets(path, size, cell, baseline, present_only, pylib=None):
    """Render the font's 11,172 syllables 1 bpp at @p size px into a cell.

    The frame puts the union ink box of the drawn syllables in the middle of the cell (the baseline row may be
    given instead of centred). Returns (targets, w, h, ascent, info, ascii_glyphs).
    """
    jf = _jamofit()
    font = jf.OutlineFont(path, size, pylib)
    w, h = cell or (size, size)
    raws, boxes = {}, []
    for s in range(11172):
        gid = font.gid(0xAC00 + s)
        r = font.raw(gid) if (gid or not present_only) else ([], 0, 0, 0)
        raws[s] = (gid, r)
        b = jf.raw_box(r) if gid else None
        if b:
            boxes.append(b)
    if not boxes:
        raise SourceError(f"{path}: draws none of the Hangul syllables")
    left, top = min(b[0] for b in boxes), max(b[1] for b in boxes)
    right, bottom = max(b[2] for b in boxes), min(b[3] for b in boxes)
    iw, ih = right - left + 1, top - bottom + 1
    ox = -left + (w - iw) // 2
    oy = baseline if baseline is not None else top + (h - ih) // 2
    targets = {}
    for s, (gid, r) in raws.items():
        g = jf.place(r, ox, oy, w, h)
        if g or not present_only:
            targets[s] = g
    info = {"font": os.path.basename(path), "size": size, "cell": [w, h], "baseline": oy, "origin_x": ox,
            "ink_box": [iw, ih], "clipped": ink_clipped(iw, ih, w, h, oy, top, bottom),
            "drawn": sum(1 for s in raws if raws[s][0] and any(raws[s][1][0])), "fitted": len(targets)}
    ascii_glyphs = {}
    for cp in range(0x20, 0x7F):
        gid = font.gid(cp)
        r = font.raw(gid) if gid else ([], 0, 0, 0)
        g = jf.place(r, ox, oy, w, h)
        gl = Glyph(w, h, jf.to_rows(g, w, h))
        ix, iwid = gl.ink()
        ascii_glyphs[cp] = (gl.to_bytes(), min(255, int(round(font.advance(gid))) if gid else w // 2), ix, iwid)
    return targets, w, h, oy, info, ascii_glyphs


def write_report(path, info):
    import json
    with open(path, "w") as fh:
        json.dump(info, fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.write("\n")


def summary_line(label, q):
    return (f"{label}: {q['present']} syllables, IoU {q['iou_mean']:.3f} (p5 {q['iou_p5']:.3f}), "
            f"F1 tol1 {q['f1_tol1_mean']:.3f} (p5 {q['f1_tol1_p5']:.3f}), exact {q['exact']}, "
            f"blobs merged {q['blob_merged']} split {q['blob_split']}")


def _layout_arg(v):
    if v in LAYOUTS or v == MAC_LAYOUT:
        return v
    m = re.fullmatch(r"adaptive(?::(\d+),(\d+),(\d+))?", v)
    if m:
        lim = tuple(int(x) for x in m.groups()) if m.group(1) else (32, 24, 12)
        if not (8 <= lim[0] <= 32 and 4 <= lim[1] <= 24 and 4 <= lim[2] <= 16):
            raise argparse.ArgumentTypeError("adaptive limits are NI 8..32, NM 4..24, NF 4..16 (844 is 8,4,4)")
        return v
    raise argparse.ArgumentTypeError(f"unknown layout {v}")


def adaptive_limits(name):
    """(NI, NM, NF) of an 'adaptive[:NI,NM,NF]' layout argument, or None."""
    if not name.startswith("adaptive"):
        return None
    return tuple(int(x) for x in name.split(":")[1].split(",")) if ":" in name else (32, 24, 12)


def make_parser():
    ap = argparse.ArgumentParser(description="DOS Johab jamo-set font or outline font / precomposed face -> jamo-set SVF")
    ap.add_argument("source", nargs="?", help="the source font file (DOS Johab sources; not with --from-ttf/--from-svf)")
    ap.add_argument("--layout", required=True, type=_layout_arg, metavar="{" + ",".join(sorted(LAYOUTS) + [MAC_LAYOUT]) + ",adaptive[:NI,NM,NF]}",
                    help=f"a set system; {MAC_LAYOUT} takes a HangulTalk 1.0 'fbit' resource fork (see MacFbit); "
                    "adaptive (--from-ttf/--from-svf) starts from 844 and splits sets where the syllables sharing a "
                    "piece disagree, up to NI,NM,NF sets (default 32,24,12, most 32,24,16; jamoadapt.py)")
    ap.add_argument("--face", type=int, default=0, help="typeface of a printer font (0 or 1)")
    ap.add_argument("--eng", help="raw 8x16 English font for ASCII (2048 or 4096 bytes)")
    ap.add_argument("--base", help="SVFN v3 whose non-syllable glyphs are kept (same cell, 1 bpp)")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--advance", type=int, help="the step of a composed syllable (JSET advance byte; default: the layout's, "
                    "0 = the cell width)")
    ap.add_argument("--ascent", type=int, help="the SVF's baseline row (default: the --eng face's baseline for a 12x24 face, "
                    "else 7/8 of the cell)")
    ap.add_argument("--embolden", action="store_true", help="OR every piece and ASCII glyph with itself shifted right 1 px")
    ap.add_argument("--symbols", action="store_true", help="add U+2026 (three baseline dots) and U+25A1 (a box)")
    ap.add_argument("--check", action="store_true", help="compose all 11,172 syllables from the output and verify")
    ap.add_argument("--from-ttf", metavar="FONT", help="fit the pieces to the outline font's syllables at --size")
    ap.add_argument("--from-svf", metavar="FACE.SVF", help="decompose a 1 bpp precomposed SVFN face (its present "
                    "syllables); keeps its other glyphs, cell, baseline, metrics and flags")
    ap.add_argument("--size", type=int, help="--from-ttf: pixel size")
    ap.add_argument("--cell", help="--from-ttf: cell WxH (default SIZExSIZE)")
    ap.add_argument("--baseline", type=int, help="--from-ttf: baseline row from the cell top (default: ink box centred)")
    ap.add_argument("--present-only", action=argparse.BooleanOptionalAction, default=True,
                    help="--from-ttf: fit and score only syllables the font draws (the default; --from-svf always does). "
                    "--no-present-only also fits .notdef for every syllable the font lacks")
    ap.add_argument("--blank-compat", metavar="FACE.SVF", help="rewrite a jamo-set face with every compat jamo it has a whole "
                    "glyph for left to that glyph, and the pieces nothing draws dropped (-o OUT)")
    ap.add_argument("--mask-font", "--mask", dest="mask_font", metavar="FONT|none",
                    help="font with OpenType ljmo/vjmo/tjmo that confines the pieces. Default: $JAMOSET_MASK_FONT or "
                    "the shipped NotoSansKR when freetype/uharfbuzz are importable, used unless a free fit already "
                    "composes the target (IoU >= 0.995); an explicit FONT is always used; 'none' = free pieces")
    ap.add_argument("--mask-radius", type=int, help="mask dilation in pixels (default 1 up to 16 px, 2 up to 24, else 3)")
    ap.add_argument("--passes", type=int, default=12, help="most coordinate-descent passes (default 12)")
    ap.add_argument("--pylib", help="directory holding freetype and uharfbuzz (also $JAMOSET_PYLIB)")
    ap.add_argument("--report", metavar="FILE.json", help="write the quality report (IoU, F1, blobs) as JSON")
    add_profile_args(ap)
    add_jset_version_arg(ap, None)
    ap.add_argument("--bpp", type=int, choices=(1, 2), default=1,
                    help="--from-ttf: 2 = anti-aliased pieces, 4 levels (jamoaa.py: contours assigned to the jamo of a 1 bpp "
                    "region fit, per-pixel median over the syllables, composed by the maximum; needs fontTools)")
    ap.add_argument("--aa-refine", type=int, default=2, metavar="N",
                    help="--bpp 2: passes of the level-error refinement after the median (default 2, 0 = median only)")
    ap.add_argument("--binarize", choices=("mono", "threshold", "ridge"), default="mono",
                    help="--from-ttf 1 bpp targets: mono = FreeType's monochrome renderer (the default); threshold = "
                    "exact-area coverage >= --threshold; ridge = that plus one-pixel ridges of faint strokes (fontTools)")
    ap.add_argument("--threshold", type=float, default=0.5, help="--binarize threshold|ridge: coverage cut (default 0.5)")
    ap.add_argument("--clean", action=argparse.BooleanOptionalAction, default=None,
                    help="noise cleanup (default on for --bpp 2 and --layout adaptive, off otherwise): pieces confined "
                    "to where their jamo's own contours (an outline source) or region (a bitmap source) put ink in at "
                    "least a quarter of the syllables, outlier syllables dropped from the consensus, specks the "
                    "composition does not need removed, faint AA levels only where half the syllables have them")
    return ap


def main_mac(ap, args):
    """--layout mac-fbit-45sets SOURCE.rsrc: the JSET tables from the font's own rule, then compare with the Mac rendering."""
    if not args.source or args.from_ttf or args.from_svf or args.blank_compat or args.eng or args.base:
        ap.error(f"{MAC_LAYOUT} takes the 'fbit' resource fork file as its source (no --from-*, --eng or --base)")
    started = time.time()
    try:
        with open(args.source, "rb") as fh:
            mac = MacFbit(fh.read())
        layout, src = mac_layout(mac)
        out, mapping, _ = build_from_source(layout, src, None, None, args.ascent or mac.h, None, False, args.advance,
                                            args.embolden, args.symbols, profile=profile_arg(ap, args),
                                            jset_version=args.jset_version or 1, jset_big=args.jset_big)
        with open(args.output, "wb") as fh:
            fh.write(out)
        print(f"{args.output}: {len(out)} bytes, {len(mapping)} pieces of {mac.w}x{mac.h} from {args.source}; "
              f"{layout.lc} lead classes, {layout.tc} tail classes, {layout.ni}/{layout.nm}/{layout.nf} sets; "
              + jset_line(out))
        if args.check:
            print("check:", check(out, layout, None))
            if args.embolden:
                print("mac: comparison skipped (--embolden changes the pieces; the Mac rendering is not emboldened)")
            else:
                q, bad = mac_compare(out, mac_targets(mac), mac.w, mac.h)
                print(summary_line("mac (jamoset.py's own copy of the rule, self-consistency only)", q)
                      + f"; differing syllables: {len(bad)}")
                if bad:
                    raise ValueError(f"{len(bad)} syllables differ from the Mac rendering, first U+{0xAC00 + bad[0]:04X}")
                golden = mac_golden(args.source)
                if golden is None:
                    print("golden: none for this font (no independent reference)")
                else:
                    probs = mac_golden_problems(out, golden)
                    if probs:
                        raise ValueError(f"differs from the golden rendering of {golden['key']}: {'; '.join(probs[:4])}")
                    print(f"golden: ok, 2350 KS X 1001 syllables identical to {golden['key']} (research renderer)")
        if args.report:
            write_report(args.report, {"layout": MAC_LAYOUT, "output_bytes": len(out), "pieces": len(mapping),
                                       "seconds": round(time.time() - started, 1)})
    except (SourceError, ValueError, OSError) as e:
        sys.exit(f"{args.source}: {e}")


def main_aa(ap, args, layout, eng, base, started, limits=None, clean=True):
    """--from-ttf FONT --bpp 2: the anti-aliased jamo set (jamoaa.build), its quality against the direct 2 bpp renders."""
    jamoaa = _jamoaa()
    if not args.from_ttf:
        ap.error("--bpp 2 works from an outline font (--from-ttf)")
    if not args.size:
        ap.error("--from-ttf needs --size")
    bad = [o for o, v in (("--eng", eng), ("--base", base), ("--embolden", args.embolden),
                          ("--no-present-only", not args.present_only), ("--binarize", args.binarize != "mono")) if v]
    if bad:
        ap.error(f"--bpp 2 does not take {', '.join(bad)}")
    cell = tuple(int(x) for x in args.cell.lower().split("x")) if args.cell else None
    out, info = jamoaa.build(layout, args.from_ttf, args.size, cell, args.baseline, args.passes, args.aa_refine,
                             args.symbols, args.advance, args.pylib, keep=True, clean=clean, adaptive=limits,
                             profile=profile_arg(ap, args), jset_version=args.jset_version or 1, jset_big=args.jset_big)
    ctx = info.pop("ctx")
    open(args.output, "wb").write(out)
    w, h = ctx["w"], ctx["h"]
    comp = jamoaa.composed_levels(out, ctx["direct"])
    q = jamoaa.aa_quality(ctx["direct"], comp, w, h)
    if limits:
        print(f"adaptive: {info['sets'][0]}/{info['sets'][1]}/{info['sets'][2]} sets, {info['classes'][0]} lead and "
              f"{info['classes'][1]} tail classes")
    info.update(aa_quality=q, join_loss=jamoaa.join_loss(ctx["donors"], ctx["direct"], w, h),
                output_bytes=len(out), seconds=round(time.time() - started, 1))
    print(f"{args.output}: {len(out)} bytes, {info['pieces']} pieces of {w}x{h} at 2 bpp from {args.from_ttf} in "
          f"{info['seconds']} s; {jset_line(out)}")
    print(f"aa: {q['present']} syllables, level error {q['level_mae']:.4f} (ink {q['level_mae_ink']:.3f}), exact ink "
          f"pixels {q['exact_pixels_ink']:.3f}, IoU at level 2 {q['iou_t2_mean']:.3f} (p5 {q['iou_t2_p5']:.3f}), "
          f"exact {q['exact']}; contours {info['contours']}")
    if args.check:
        print("check:", check(out, ctx["layout"], None))
    if args.report:
        write_report(args.report, info)


def fit_prep(layout, targets, w, h, origin, limits, clean, passes, outline=None, pylib=None, log=None, rounds=None):
    """Before a 1 bpp fit with --clean or --layout adaptive: the donors (each syllable's raster per slot: its own
    contours from @p outline (font path, size), placed at the targets' @p origin (ox, oy), when fontTools can read
    it, else the target split by a free region fit), the adaptive layout, and the donor-support masks. Donors depend
    on the region fit they are split by, so for an adaptive layout the regions are fitted again with the layout found
    and the layout made again from the new donors (@p rounds, default 3 from regions, 1 from contours). Returns
    (layout, masks or None, info)."""
    jf = _jamofit()
    aa = _jamoaa()
    info = {}
    face = None
    if outline:
        try:
            face = aa.OutlineFace(outline[0], outline[1], pylib)
        except jf.FitError as e:
            print(f"jamoset: {e}; donors from the 1 bpp regions instead", file=sys.stderr)
    rounds = rounds or (1 if face else 3)
    # contours are given to slots by peers over the region layout; a bitmap's pixels are split by an 844 fit
    region_layout = aa.region_layout() if face else LAYOUTS["844"]
    history = []
    for r in range(rounds if limits else 1):
        keys_r, _, roles_r = aa.syllable_keys(region_layout)
        P_r, _ = jf.fit_pieces({s: keys_r[s] for s in targets}, targets, w, h, None, passes)
        if face:
            donors, cinfo = aa.contour_donors(face, sorted(targets), keys_r, P_r, origin[0], origin[1], w, h, targets,
                                              roles_r)
            info["donors"], info["contours"] = "contours", cinfo
        else:
            donors = aa.pixel_donors(targets, keys_r, P_r, w, h)
            info["donors"] = "regions"
        if not limits:
            break
        import jamoadapt
        region_layout, ainfo = jamoadapt.adapt(donors, 1, limits, log=log)
        history.append(ainfo["sets"])
        info["adaptive"] = {k: v for k, v in ainfo.items() if k != "history"}
    if limits:
        layout = region_layout
        info["adaptive"]["rounds"] = history
    masks = None
    if clean:
        keys, _, _ = aa.syllable_keys(layout)
        masks = aa.donor_masks(keys, donors, w, h, 128, 0.25, 1)
    return layout, masks, info


def main():
    ap = make_parser()
    args = ap.parse_args()
    profile_arg(ap, args)
    if args.layout == MAC_LAYOUT:
        return main_mac(ap, args)
    limits = adaptive_limits(args.layout)
    if limits and not (args.from_ttf or args.from_svf):
        ap.error("--layout adaptive fits pieces: give --from-ttf or --from-svf")
    layout = LAYOUTS["844"] if limits else LAYOUTS[args.layout]
    clean = args.clean if args.clean is not None else bool(limits or args.bpp == 2)
    modes = [m for m in (args.source, args.from_ttf, args.from_svf, args.blank_compat) if m]
    if len(modes) != 1:
        ap.error("give exactly one of: a source font file, --from-ttf, --from-svf, --blank-compat")
    label = modes[0]
    try:
        if args.blank_compat:
            out = blank_whole_compat(open(args.blank_compat, "rb").read(), profile_arg(ap, args), args.jset_version, args.jset_big)
            open(args.output, "wb").write(out)
            print(f"{args.output}: {len(out)} bytes, compat jamo with a whole glyph left to the glyph; {jset_line(out)}")
            return
        eng = read_eng(open(args.eng, "rb").read()) if args.eng else None
        base = open(args.base, "rb").read() if args.base else None
        if args.bpp == 2:
            return main_aa(ap, args, layout, eng, base, time.time(), limits, clean)
        if args.from_ttf or args.from_svf:
            started = time.time()
            jf = _jamofit()
            mask = args.mask_font
            mask_auto = mask is None
            if mask is None:
                mask = default_mask_font()
                if mask and not jf.libs_available(args.pylib):
                    print("jamoset: no freetype/uharfbuzz, fitting without the mask font (" + jf._LIB_HELP + ")",
                          file=sys.stderr)
                    mask = None
            elif mask.lower() == "none":
                mask = None
            elif not os.path.exists(mask):
                raise SourceError(f"mask font {mask} does not exist")
            if args.from_ttf:
                if not args.size:
                    ap.error("--from-ttf needs --size")
                cell = tuple(int(x) for x in args.cell.lower().split("x")) if args.cell else None
                if args.binarize != "mono":
                    if not args.present_only:
                        ap.error("--binarize threshold|ridge fits the drawn syllables only (--present-only)")
                    jamoaa = _jamoaa()
                    targets, w, h, ascent, tinfo, ascii_glyphs = jamoaa.outline_targets(
                        args.from_ttf, args.size, cell, args.baseline, args.binarize, args.threshold, args.pylib)
                else:
                    targets, w, h, ascent, tinfo, ascii_glyphs = ttf_targets(args.from_ttf, args.size, cell,
                                                                              args.baseline, args.present_only,
                                                                              args.pylib)
                extra = None if (eng is not None or base is not None) else ascii_glyphs
                pmasks, pinfo = None, {}
                if clean or limits:
                    layout, pmasks, pinfo = fit_prep(layout, targets, w, h, (tinfo["origin_x"], ascent), limits, clean,
                                                     args.passes, (args.from_ttf, args.size), args.pylib)
                out, info = fit_font(layout, targets, w, h, ascent, eng, base, extra, False, mask, args.mask_radius,
                                     args.passes, args.pylib, mask_auto, args.advance, pmasks,
                                     _jamoaa().speck_size(w, h) if clean else 0, profile_arg(ap, args),
                                     args.jset_version or 1, args.jset_big)
                info.update(pinfo)
                info["source"] = tinfo
            else:
                face = parse_svfn(open(args.from_svf, "rb").read())
                if face.bpp != 1:
                    raise SourceError(f"{args.from_svf} is {face.bpp} bpp, not 1")
                if face.flags & FLAG_JAMO:
                    raise SourceError(f"{args.from_svf} is already a jamo-set font")
                w, h = face.cell_w, face.cell_h
                targets = svf_targets(face)
                if not targets:
                    raise SourceError(f"{args.from_svf} has no non-blank Hangul syllables")
                pmasks, pinfo = None, {}
                if clean or limits:
                    layout, pmasks, pinfo = fit_prep(layout, targets, w, h, None, limits, clean, args.passes)
                out, info = fit_font(layout, targets, w, h, face.ascent, eng, open(args.from_svf, "rb").read(), None,
                                     True, mask, args.mask_radius, args.passes, args.pylib, mask_auto,
                                     args.advance if args.advance is not None else svf_advance(face), pmasks,
                                     _jamoaa().speck_size(w, h) if clean else 0, profile_arg(ap, args),
                                     args.jset_version or 1, args.jset_big)
                info.update(pinfo)
                info["source"] = {"face": os.path.basename(args.from_svf), "cell": [w, h], "ascent": face.ascent,
                                  "size": os.path.getsize(args.from_svf),
                                  "syllable_advance": svf_advance(face)}
            open(args.output, "wb").write(out)
            q = fit_report(out, targets, w, h)
            info.update(quality=q, layout=layout.name, output_bytes=len(out), seconds=round(time.time() - started, 1))
            print(f"{args.output}: {len(out)} bytes, {info['pieces']} pieces of {w}x{h} fitted from {label}"
                  f" in {info['seconds']} s; {jset_line(out)}")
            print(summary_line("fit", q))
            if limits:
                print(f"adaptive: {layout.ni}/{layout.nm}/{layout.nf} sets, {layout.lc} lead and {layout.tc} tail classes")
            if args.check:
                print("check:", check(out, layout, None))
            if args.report:
                write_report(args.report, info)
            return
        out, mapping, src = build_from_source(layout, layout.opener(open(args.source, "rb").read(), args.face, args.source),
                                               eng, base, args.ascent, None, False, args.advance, args.embolden,
                                               args.symbols, profile=profile_arg(ap, args),
                                               jset_version=args.jset_version or 1, jset_big=args.jset_big)
        open(args.output, "wb").write(out)
        print(f"{args.output}: {len(out)} bytes, {len(mapping)} pieces of {src.w}x{src.h} from {args.source}; "
              + jset_line(out))
        if args.check:
            print("check:", check(out, layout, open(args.source, "rb").read()))
    except (SourceError, ValueError, _jamofit().FitError) as e:
        sys.exit(f"{label}: {e}")


if __name__ == "__main__":
    main()
