#!/usr/bin/env python3
"""Read the bitmap fonts of Hangul (HWP) 1.x and 3.0 for DOS and headerless KS X 1001 syllable dumps, and write them as
Unicode BDFs for bdfface.py / mkfont.py. Nothing here runs the files' code: it reads bytes. Run it with `python3 -I`
on downloads.

  hwpfont.py info FILE
      what the file is: family (hwp1, hwp3, ks-raw), kind (hangul, ascii, hanja, other), glyph size and count, faces.
  hwpfont.py bdf FILE [--face N] [--syllables ks|all] [--ascii ENGFILE [--ascii-face N]] [--ascent A] -o OUT.bdf
      the file's glyphs as a Unicode BDF (CHARSET_REGISTRY "ISO10646", PIXEL_SIZE set): the Hangul syllables of a
      Hangul file (the 2,350 of KS X 1001, or all 11,172 with --syllables all for an HWP 1.x face, which composes
      them), U+0020..U+007E of an English file, the 4,888 KS X 1001 hanja of a hanja file. --ascii adds the ASCII of an
      English font (any jamoset.py --eng reads: raw 8x16, HBIOS / Taebaek 12x24, Taebaek 20x40 / 24x48, an HWP 1.x
      ASCII file, an HWP 3.0 ENG*.FNT; centred in height when it is shorter than the Hangul cell); the BDF's ascent is
      --ascent, else that English face's baseline (the row below the ink of 'H'), else 7/8 of the cell.

Formats (from the johab-fonts research notes, notes/hwp1.md and notes/dos.md; HWP.EXE was read as bytes there):

HWP 1.x (1989-1990) *.SFT (screen) and *.PFT (printer): a 32-byte header "HWP Font Editor v1.0" 1A 00.. (the
HANGUL3.PFT of HPFT3.LZH has "FE" 1A 00), BE16 glyph count at 0x1C, (width - 1, height - 1) at 0x1E, then the glyphs,
the file size exactly 32 + count x glyph bytes. Screen fonts (16 rows) are row-major, MSB left, ceil(w/8) bytes a row;
printer fonts (24 rows, a 24-pin head) are column-major, w columns of 3 bytes, MSB at the top.
  HANGUL.SFT (16x16, 1,193 glyphs) and HANGUL1/2/3.PFT (24x24, 980) hold three faces back to back (HWP.EXE's style
  number 0..2; by its menu order Myeongjo, Gothic, Saemmul - not proven). A face is its initial sets, vowel sets and
  final sets, a set holding 31 / 29 / 31 pieces (piece 0 of each class, "none", is not stored):
      SFT  face 0 10/4/4 sets, face 1 7/2/2, face 2 6/2/2     PFT  face 0 7/2/3, face 1 7/2/2, face 2 5/2/2
  A syllable is the OR of three pieces picked by HWP.EXE's tables (copied below as data): the Johab 5-bit fields
  give the piece numbers (L_IDX, V_IDX, T_IDX), the pieces give shape classes (L_CLS: 0 for g and k; V_CLS: the vowel's
  shape; T_CLS: 0 without a final), and per face SEL picks the sets: initial set [has final][vowel class], vowel set
  [has final * 2 + initial class], final set [vowel class].
  ASCII.SFT (8x16) / ASCII.PFT (14x24): 991 glyphs, 109 leading ones (control glyphs and codes 0xB3..0xFF), then six
  faces of 147 (codes 0x20..0xB2; by the menu Myeongjo, Gothic, superscript, subscript, italic, script).
  HANJA.SFT: the 4,888 KS X 1001 hanja (16x16). The other files (SPECIAL*, JAPAN, USER*, SYSTEM.PFT) are symbol sets.

HWP 3.0 (1995) HDR30/FONT/*.FNT: a 72-byte header "FNT" 01, a type byte (0 English, 1 Hangul, 2 hanja), 01, LE16 width
and height at 6 and 8, three LE16 words at 10 that are (8, 4, 4) in a 16 px Hangul font and 0 elsewhere, LE32 glyph count at 0x10, a Johab name at 0x14; then
row-major glyphs (ceil(w/8) bytes a row, MSB left). Hangul: the 2,350 KS X 1001 syllables in code order; HAN16_*.FNT
adds a 360-glyph 8x4x4 jamo set (jamoset.py --layout 844-hwp3); HAN24/HAN40/96MT hold the 2,350 only (HAN24's header
still says 2,710). English: glyph i is code 0x20 + i (147 glyphs; ENG40 stores 96). Hanja: the 4,888 in KS order.

KS raw: a headerless dump of the 2,350 KS X 1001 syllables in code order, row-major: 2,350 x the glyph's bytes
(75,200 at 16x16, 169,200 at 24x24, 300,800 at 32x32, 470,000 at 40x40, 676,800 at 48x48; Taebaek 3.5.1's
GHAN*/MHAN*.PFT, the decoded OS/2 tables).
"""

import argparse
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:  # python -I drops the script's directory
    sys.path.insert(0, HERE)

HWP1_MAGIC = b"HWP Font Editor v1.0"
HWP1_FE = b"FE\x1a\x00"
HWP3_MAGIC = b"FNT\x01"
HWP3_HEADER = 72
MAX_FILE = 16 << 20               # the largest of these files (96MT.FNT) is 2.7 MB

# ---- HWP.EXE 1.20 tables (DS offsets in notes/hwp1.md) -------------------------------------------------------------
# Johab 5-bit field -> piece number within its class (0 = none): DS 0x438a / 0x43aa / 0x43ca
L_IDX = (20, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31)
V_IDX = (0, 0, 0, 1, 2, 3, 4, 5, 22, 23, 6, 7, 8, 9, 10, 11, 24, 25, 12, 13, 14, 15, 16, 17, 26, 27, 18, 19, 20, 21, 28, 29)
T_IDX = (28, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 29, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 30, 31)
# piece number -> shape class: DS 0x43ea / 0x442a / 0x4466
L_CLS = (1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
V_CLS = (1, 1, 4, 1, 4, 2, 5, 2, 5, 6, 9, 10, 11, 6, 8, 13, 14, 15, 8, 7, 12, 3, 9, 10, 11, 13, 14, 15, 7, 12)
T_CLS = (0,) + (1,) * 31
# per face: initial set [T_CLS][V_CLS], vowel set [T_CLS * 2 + L_CLS], final set [V_CLS] (the [L_CLS] rows of HWP.EXE's
# final table are identical); screen DS 0x44a8 + face * 0x44, printer DS 0x4578 + face * 0x44
SEL = {
    "sft": (
        (((0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 3, 3, 3, 4, 4, 4), (5, 5, 5, 5, 5, 5, 6, 6, 7, 8, 8, 8, 8, 9, 9, 9)), (0, 1, 2, 3),
         (0, 0, 1, 1, 2, 2, 3, 3, 3, 0, 2, 1, 1, 1, 2, 1)),
        (((0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 3, 3, 3, 3, 3, 3), (4, 4, 4, 4, 4, 4, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6)), (0, 0, 1, 1),
         (0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0)),
        (((0, 0, 0, 0, 0, 0, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2), (3, 3, 3, 3, 3, 3, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5)), (0, 0, 1, 1),
         (0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0)),
    ),
    "pft": (
        (((0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 3, 3, 3, 3, 3, 3), (4, 4, 4, 4, 4, 4, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6)), (0, 0, 1, 1),
         (0, 0, 1, 1, 1, 1, 2, 2, 2, 0, 1, 1, 1, 1, 1, 1)),
        (((0, 0, 0, 0, 0, 0, 1, 1, 2, 3, 3, 3, 3, 3, 3, 3), (4, 4, 4, 4, 4, 4, 5, 5, 5, 6, 6, 6, 6, 6, 6, 6)), (0, 0, 1, 1),
         (0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0)),
        (((0, 0, 0, 0, 0, 0, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2), (0, 0, 0, 0, 0, 0, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4)), (0, 0, 1, 1),
         (0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0)),
    ),
}
# sets per face (initial, vowel, final): DS 0x4282.. (SFT) and 0x4294.. (PFT)
SETS = {"sft": ((10, 4, 4), (7, 2, 2), (6, 2, 2)), "pft": ((7, 2, 3), (7, 2, 2), (5, 2, 2))}
NL, NV, NT = 31, 29, 31
# (w, h, glyph count) of a Hangul file -> its table set
HANGUL_FILES = {(16, 16, 1193): "sft", (24, 24, 980): "pft"}
FACE_NAMES = ("Myeongjo", "Gothic", "Saemmul")          # HWP.EXE's menu order (not proven)
ASCII_FACES = ("Myeongjo", "Gothic", "superscript", "subscript", "italic", "script")
ASCII_LEAD, ASCII_FACE = 109, 147

JUNG_FIELD = (3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 22, 23, 26, 27, 28, 29)   # V 0..20 -> 5-bit value


class HwpError(Exception):
    pass


def johab_fields(cp):
    """(L, V, T) 5-bit Johab fields of a Unicode syllable (HwpError for any other code point)."""
    if not 0xAC00 <= cp <= 0xD7A3:
        raise HwpError(f"U+{cp:04X} is not a Hangul syllable")
    s = cp - 0xAC00
    L, V, T = s // 588, (s // 28) % 21, s % 28
    return L + 2, JUNG_FIELD[V], T + 1 if T <= 16 else T + 2


def _ks_codes(lo, hi):
    out = []
    for lead in range(lo, hi + 1):
        for trail in range(0xA1, 0xFF):
            try:
                out.append(ord(bytes((lead, trail)).decode("euc_kr")))
            except UnicodeDecodeError:
                pass
    return out


def ks_hangul():
    """The 2,350 KS X 1001 syllables (code points) in code order (B0A1 .. C8FE)."""
    return _ks_codes(0xB0, 0xC8)


def ks_hanja():
    """The 4,888 KS X 1001 hanja (code points) in code order (CAA1 .. FDFE)."""
    return _ks_codes(0xCA, 0xFD)


KS_RAW_PX = (16, 24, 32, 40, 48)


def ks_raw_px(size):
    """The cell of a headerless KS X 1001 syllable dump of @p size bytes (2,350 square glyphs), or None."""
    for px in KS_RAW_PX:
        if size == 2350 * ((px + 7) // 8) * px:
            return px
    return None


# ---- files -------------------------------------------------------------------------------------------------------

class Font:
    """One file: family (hwp1 | hwp3 | ks-raw), kind (hangul | ascii | hanja | other), glyph size, count, glyph(i)
    as rows (ints, bit w-1-x = pixel x)."""

    def __init__(self, family, kind, data, offset, w, h, count, colmajor=False, name="", jamo844=False, table=None):
        self.family, self.kind, self.data, self.offset = family, kind, data, offset
        self.w, self.h, self.count, self.colmajor, self.name = w, h, count, colmajor, name
        self.jamo844 = jamo844             # an HWP 3.0 HAN16: a 360-glyph 8x4x4 set after the 2,350 syllables
        self.table = table                 # an HWP 1.x Hangul file's table set ("sft" | "pft")
        self.gsize = w * (h // 8) if colmajor else (w + 7) // 8 * h

    def glyph(self, i):
        if not 0 <= i < self.count:
            raise HwpError(f"glyph {i} is outside the file's {self.count}")
        o = self.offset + i * self.gsize
        w, h = self.w, self.h
        if self.colmajor:
            cb = h // 8
            rows = [0] * h
            for x in range(w):
                col = int.from_bytes(self.data[o + x * cb:o + (x + 1) * cb], "big")
                for y in range(h):
                    if col >> (h - 1 - y) & 1:
                        rows[y] |= 1 << (w - 1 - x)
            return rows
        bpr = (w + 7) // 8
        sh = bpr * 8 - w
        return [int.from_bytes(self.data[o + y * bpr:o + (y + 1) * bpr], "big") >> sh for y in range(h)]

    def describe(self):
        what = {"hwp1": "HWP 1.x font", "hwp3": "HWP 3.0 FNT", "ks-raw": "KS X 1001 raw dump"}[self.family]
        s = f"{what}: {self.kind}, {self.count} glyphs of {self.w}x{self.h}"
        if self.family == "hwp1":
            s += ", column-major (printer)" if self.colmajor else ", row-major (screen)"
        if self.name:
            s += f", name {self.name!r}"
        if getattr(self, "declared", None) not in (None, self.count):
            s += f" (the header declares {self.declared})"
        if self.table:
            sets = ", ".join(f"face {i} ({FACE_NAMES[i]}) {a}/{b}/{c}" for i, (a, b, c) in enumerate(SETS[self.table]))
            s += f"; three faces of initial/vowel/final sets: {sets}"
        if self.kind == "ascii" and self.family == "hwp1":
            s += "; six faces: " + ", ".join(f"{i} {n}" for i, n in enumerate(ASCII_FACES))
        if self.jamo844:
            s += "; glyphs 2350..2709 are an 8x4x4 jamo set (jamoset.py --layout 844-hwp3)"
        return s


def _hwp1_geometry(head):
    """(count, w, h, column-major, glyph bytes) from an HWP 1.x header (its first 32 bytes at least). The order is taken
    from the height, not the file's extension: the printer fonts are 24 rows (a 24-pin head, column-major), the screen
    fonts 16 (row-major)."""
    if len(head) < 32:
        raise HwpError("shorter than the 32-byte HWP 1.x header")
    count = struct.unpack_from(">H", head, 0x1C)[0]
    if count < 1:
        raise HwpError("an HWP 1.x header with a glyph count of 0")
    w, h = head[0x1E] + 1, head[0x1F] + 1
    col = h == 24
    return count, w, h, col, w * 3 if col else (w + 7) // 8 * h


def _hwp3_geometry(head):
    """(type, w, h, glyph bytes, declared count) from an HWP 3.0 header (its first 72 bytes at least)."""
    if len(head) < HWP3_HEADER:
        raise HwpError("shorter than the 72-byte HWP 3.0 header")
    w, h = struct.unpack_from("<HH", head, 6)
    if not (1 <= w <= 128 and 1 <= h <= 128):
        raise HwpError(f"HWP 3.0 FNT glyph size {w}x{h} is out of range")
    declared = struct.unpack_from("<I", head, 0x10)[0]
    if declared < 1:
        raise HwpError("an HWP 3.0 header with a glyph count of 0")
    return head[4], w, h, (w + 7) // 8 * h, declared


def sniff(head, size):
    """`hwp1`, `hwp3` or `ks-raw` when the first bytes @p head (512 are enough) and the file @p size fit that format's
    header and size rule, else None: a file that merely starts with the magic bytes is not taken."""
    try:
        if head.startswith(HWP1_MAGIC) or head[:4] == HWP1_FE:
            count, _w, _h, _c, gsize = _hwp1_geometry(head)
            return "hwp1" if size == 32 + count * gsize else None
        if head[:4] == HWP3_MAGIC:
            _t, _w, _h, gsize, _n = _hwp3_geometry(head)
            body = size - HWP3_HEADER
            return "hwp3" if body > 0 and body % gsize == 0 else None
    except HwpError:
        return None
    return "ks-raw" if ks_raw_px(size) else None


def _hwp1(data):
    count, w, h, col, gsize = _hwp1_geometry(data)
    if len(data) != 32 + count * gsize:
        raise HwpError(f"size {len(data)} is not 32 + {count} glyphs of {gsize} bytes ({w}x{h})")
    table = HANGUL_FILES.get((w, h, count))
    if table:
        kind = "hangul"
    elif count == ASCII_LEAD + 6 * ASCII_FACE and (w, h) in ((8, 16), (14, 24)):
        kind = "ascii"
    elif count == 4888 and (w, h) == (16, 16):
        kind = "hanja"
    else:
        kind = "other"
    return Font("hwp1", kind, data, 32, w, h, count, col, table=table)


def _hwp3(data):
    typ, w, h, gsize, declared = _hwp3_geometry(data)
    body = len(data) - HWP3_HEADER
    if body <= 0 or body % gsize:
        raise HwpError(f"size {len(data)} is not 72 + whole glyphs of {gsize} bytes ({w}x{h})")
    count = body // gsize
    raw = data[0x14:HWP3_HEADER].split(b"\0", 1)[0]
    try:
        name = raw.decode("johab").strip()
    except UnicodeDecodeError:
        name = ""
    kind = {0: "ascii", 1: "hangul", 2: "hanja"}.get(typ, "other")
    if kind == "hangul" and count not in (2350, 2710):
        raise HwpError(f"an HWP 3.0 Hangul FNT holds 2350 or 2710 glyphs, not {count}")
    if kind == "hanja" and count != 4888:
        kind = "other"
    if kind == "ascii" and count < 95:
        raise HwpError(f"an HWP 3.0 English FNT holds the 95 codes 0x20..0x7E at least, this one {count} "
                       f"(its header declares {declared})")
    f = Font("hwp3", kind, data, HWP3_HEADER, w, h, count, name=name,
             jamo844=kind == "hangul" and count == 2710 and w == h == 16)
    f.declared = declared        # HAN24 declares 2,710 and holds 2,350, ENG40 declares 147 and holds 96: reported, not refused
    return f


def _ks_raw(data):
    px = ks_raw_px(len(data))
    if px is None:
        raise HwpError(f"size {len(data)} is not an HWP font nor 2,350 KS X 1001 syllables of 16..48 px")
    f = Font("ks-raw", "hangul", data, 0, px, px, 2350)
    first, last = f.glyph(0), f.glyph(2349)
    if not any(first) or not any(last) or first == last:
        raise HwpError("not a KS X 1001 syllable dump: the first or last glyph is blank, or they are equal")
    return f


def read(data):
    """A Font from a file's bytes (HwpError when it is none of the three)."""
    if len(data) > MAX_FILE:
        raise HwpError(f"larger than {MAX_FILE} bytes")
    if data.startswith(HWP1_MAGIC) or data.startswith(HWP1_FE):
        return _hwp1(data)
    if data.startswith(HWP3_MAGIC):
        return _hwp3(data)
    if ks_raw_px(len(data)):
        return _ks_raw(data)
    raise HwpError("not an HWP 1.x or 3.0 font nor a KS X 1001 raw dump")


def read_bounded(path, cap=MAX_FILE):
    """The bytes of @p path, refused (HwpError) past @p cap without reading more than cap + 1 of them."""
    with open(path, "rb") as fh:
        data = fh.read(cap + 1)
    if len(data) > cap:
        raise HwpError(f"{path}: larger than {cap} bytes")
    return data


def read_file(path):
    return read(read_bounded(path))


# ---- HWP 1.x composition -----------------------------------------------------------------------------------------

class Hwp1Hangul:
    """Face @p face (0..2) of an HWP 1.x Hangul file: syllables as the OR of three pieces, by HWP.EXE's rule."""

    def __init__(self, font, face=0):
        if font.family != "hwp1" or not font.table:
            raise HwpError("not an HWP 1.x Hangul file (HANGUL.SFT 16x16 x 1193 or HANGUL*.PFT 24x24 x 980)")
        if face not in (0, 1, 2):
            raise HwpError(f"--face is 0, 1 or 2 (three faces), not {face}")
        self.font, self.face, self.table = font, face, font.table
        sets = SETS[self.table]
        base = sum(a * NL + b * NV + c * NT for a, b, c in sets[:face])
        a, b, c = self.nsets = sets[face]
        self.l0, self.v0, self.t0 = base, base + a * NL, base + a * NL + b * NV
        self.sel = SEL[self.table][face]
        self.w, self.h = font.w, font.h

    def pieces(self, cp):
        """The glyph numbers (initial, vowel, final) of syllable @p cp; None where a piece is absent."""
        L, V, T = johab_fields(cp)
        l, v, t = L_IDX[L], V_IDX[V], T_IDX[T]
        lc, vc, tc = L_CLS[l], V_CLS[v], T_CLS[t]
        s_ini, s_vow, s_fin = self.sel
        return (self.l0 + s_ini[tc][vc] * NL + l - 1 if l else None,
                self.v0 + s_vow[tc * 2 + lc] * NV + v - 1 if v else None,
                self.t0 + s_fin[vc] * NT + t - 1 if t else None)

    def syllable(self, cp):
        rows = [0] * self.h
        for i in self.pieces(cp):
            if i is not None:
                rows = [a | b for a, b in zip(rows, self.font.glyph(i))]
        return rows

    # The same rule as JSET set tables (jamoset.py --layout hwp1): Unicode L 0..18, V 0..20, T 0..27.
    def lead_class(self, L):
        return L_CLS[L_IDX[L + 2]]

    def init_set(self, lc, v, tc):
        return self.sel[0][tc][V_CLS[V_IDX[JUNG_FIELD[v]]]]

    def med_set(self, lc, v, tc):
        return self.sel[1][tc * 2 + lc]

    def fin_set(self, lc, v, tc):
        return self.sel[2][V_CLS[V_IDX[JUNG_FIELD[v]]]]

    def init_src(self, s, L):
        return self.l0 + s * NL + L_IDX[L + 2] - 1

    def med_src(self, s, V):
        return self.v0 + s * NV + V_IDX[JUNG_FIELD[V]] - 1

    def fin_src(self, s, T):
        return self.t0 + s * NT + T_IDX[T + 1 if T <= 16 else T + 2] - 1


# ---- what a file holds, by code point ------------------------------------------------------------------------------

def syllables(font, face=0, which="ks"):
    """{code point: rows} of a Hangul file's syllables: the 2,350 of KS X 1001 (@p which "ks"), or all 11,172 ("all";
    an HWP 1.x face composes them, a precomposed file has the 2,350 only)."""
    if font.kind != "hangul":
        raise HwpError(f"not a Hangul font ({font.kind})")
    if font.family == "hwp1":
        h = Hwp1Hangul(font, face)
        cps = ks_hangul() if which == "ks" else range(0xAC00, 0xD7A4)
        return {cp: h.syllable(cp) for cp in cps}
    return {cp: font.glyph(i) for i, cp in enumerate(ks_hangul())}


def ascii_glyphs(font, face=0):
    """{code point: rows} of U+0020..U+007E of an English file (an HWP 1.x ASCII file's face @p face of six)."""
    if font.kind != "ascii":
        raise HwpError(f"not an English font ({font.kind})")
    if font.family == "hwp1":
        if not 0 <= face < 6:
            raise HwpError(f"an HWP 1.x ASCII file has six faces (0..5), not {face}")
        return {cp: font.glyph(ASCII_LEAD + face * ASCII_FACE + cp - 0x20) for cp in range(0x20, 0x7F)}
    return {cp: font.glyph(cp - 0x20) for cp in range(0x20, 0x7F) if cp - 0x20 < font.count}


def hanja_glyphs(font):
    if font.kind != "hanja":
        raise HwpError(f"not a hanja font ({font.kind})")
    return {cp: font.glyph(i) for i, cp in enumerate(ks_hanja())}


def baseline(glyphs):
    """The row below the ink of 'H' (else of any glyph), or None."""
    for rows in ([glyphs.get(0x48)] if glyphs.get(0x48) else []) + list(glyphs.values()):
        used = [y for y, r in enumerate(rows) if r]
        if used:
            return used[-1] + 1
    return None


def place(glyphs, w, h, cell_h):
    """@p glyphs (w x h) centred in height in a @p cell_h row cell; returns (glyphs, top offset)."""
    if h > cell_h:
        raise HwpError(f"the English font is {h} rows, taller than the {cell_h}-row Hangul cell")
    top = (cell_h - h) // 2
    return {cp: [0] * top + rows + [0] * (cell_h - h - top) for cp, rows in glyphs.items()}, top


def english(path, face=0):
    """(glyphs {code point: rows}, glyph width, height, advance) of U+0020..U+007E of any English font jamoset.py --eng
    reads: a raw 8x16 DOS font, HBIOS / Taebaek 12x24, Taebaek 20x40 / 24x48, an HWP 1.x ASCII file (face @p face) or an
    HWP 3.0 ENG*.FNT."""
    import jamoset
    data = read_bounded(path)
    try:
        eng = jamoset.read_eng(data, face)
    except jamoset.SourceError as e:
        raise HwpError(f"{path}: {e}")
    if isinstance(eng, jamoset.EngCell):
        return {cp: list(eng.glyph(cp)) for cp in range(0x20, 0x7F)}, eng.w, eng.h, eng.adv
    return {cp: list(eng[cp * 16:cp * 16 + 16]) for cp in range(0x20, 0x7F)}, 8, 16, 8


# ---- CLI ----------------------------------------------------------------------------------------------------------

def cmd_info(a):
    f = read_file(a.file)
    print(f"{a.file}: {f.describe()}")


def cmd_bdf(a):
    import rawcarve
    f = read_file(a.file)
    glyphs, advance, widths, ascent, what = {}, {}, {}, None, []
    if f.kind == "hangul":
        glyphs = syllables(f, a.face, a.syllables)
        what.append(f"{len(glyphs)} Hangul syllables")
    elif f.kind == "ascii":
        glyphs = ascii_glyphs(f, a.face)
        ascent = baseline(glyphs)
        what.append(f"{len(glyphs)} ASCII")
    elif f.kind == "hanja":
        glyphs = hanja_glyphs(f)
        what.append(f"{len(glyphs)} hanja")
    else:
        raise HwpError(f"{a.file} holds no Hangul, ASCII or hanja to write ({f.describe()})")
    if a.ascii:
        eg, ew, eh, adv = english(a.ascii, a.ascii_face)
        eg, top = place(eg, ew, eh, f.h)
        b = baseline(eg)
        ascent = b if b is not None else ascent
        for cp, rows in eg.items():
            glyphs[cp] = rows
            advance[cp] = adv
            widths[cp] = ew
        what.append(f"{len(eg)} ASCII of {adv}x{eh} from {os.path.basename(a.ascii)}")
    if 0x20 not in glyphs:
        # a blank U+0020 first: FreeType takes a BDF's first glyph as .notdef, and mkfont.py drops every glyph equal to
        # .notdef, so without it the first syllable (U+AC00) would vanish from the face
        glyphs[0x20] = [0] * f.h
        advance[0x20] = widths[0x20] = max(1, f.w // 2)
    if a.ascent is not None:
        ascent = a.ascent
    if ascent is None:
        ascent = rawcarve.default_ascent(f.h)
    bits = {}
    for cp, rows in glyphs.items():
        gw = widths.get(cp, f.w)
        bits[cp] = [[r >> (gw - 1 - x) & 1 for x in range(gw)] for r in rows]
    with open(a.output, "w", encoding="ascii", newline="\n") as fh:
        fh.write(rawcarve.bdf_text(bits, f.w, f.h, ascent, a.name, advance))
    print(f"wrote {a.output}: {', '.join(what)}; cell {f.w}x{f.h}, ascent {ascent}")


def _bdf_name(v):
    if not v or len(v) > 64 or not all(c.isascii() and (c.isalnum() or c in "-_") for c in v):
        raise argparse.ArgumentTypeError("a name of 1-64 ASCII letters, digits, - and _")
    return v


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info")
    p.add_argument("file")
    p.set_defaults(fn=cmd_info)
    p = sub.add_parser("bdf")
    p.add_argument("file")
    p.add_argument("--face", type=int, default=0, help="HWP 1.x: the Hangul face (0..2) or the ASCII face (0..5)")
    p.add_argument("--syllables", choices=("ks", "all"), default="ks",
                   help="Hangul: the 2,350 KS X 1001 syllables (default) or all 11,172 (an HWP 1.x face composes them)")
    p.add_argument("--ascii", help="an English font whose U+0020..U+007E go into the BDF (any jamoset.py --eng reads)")
    p.add_argument("--ascii-face", type=int, default=0, help="--ascii of HWP 1.x: its face (0..5, default 0)")
    p.add_argument("--ascent", type=int, help="the BDF's ascent (default: the English face's baseline, else 7/8)")
    p.add_argument("--name", default="hwp", type=_bdf_name, help="the BDF's family name (ASCII letters, digits, - and _)")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_bdf)
    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (HwpError, OSError) as e:
        print(f"hwpfont.py: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
