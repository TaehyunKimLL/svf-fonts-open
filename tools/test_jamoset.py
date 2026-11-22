#!/usr/bin/env python3
"""jamoset.py tests: every layout's tables against the research tools' selection rules, the written file read back.

  python3 tools/test_jamoset.py

The reference selectors below are copied from the johab-fonts research tools' kfont.py (sel_*) and dkb_fnt.py (parts),
the independent implementation the layouts were checked against; they return the source font's glyph index.
"""

import os
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jamoset  # noqa: E402
import johab844  # noqa: E402

# The reference tables are literals typed from the research doc / kfont.py / dkb_fnt.py, not imported from jamoset,
# so a wrong entry in jamoset cannot also change the reference. Vowel order ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅗ ㅘ ㅙ ㅚ ㅛ ㅜ ㅝ ㅞ ㅟ ㅠ ㅡ ㅢ ㅣ.
KK = (0, 15)
JUNG_FIELD = (3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 22, 23, 26, 27, 28, 29)
I844_NOFIN = (0, 0, 0, 0, 0, 0, 0, 0, 1, 3, 3, 3, 1, 2, 4, 4, 4, 2, 1, 3, 0)
I844_FIN = (5, 5, 5, 5, 5, 5, 5, 5, 6, 7, 7, 7, 6, 6, 7, 7, 7, 6, 6, 7, 5)
F844 = (0, 2, 0, 2, 1, 2, 1, 2, 3, 0, 2, 1, 3, 3, 1, 2, 1, 3, 3, 1, 1)
R621_NOFIN = (0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 2, 2, 1, 1, 2, 2, 2, 1, 1, 2, 0)
R621_FIN = (3, 3, 3, 3, 3, 3, 3, 3, 4, 5, 5, 5, 4, 4, 5, 5, 5, 4, 4, 5, 3)
R_FCON1 = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 3, 3, 0, 0, 3, 1, 2, 4, 4, 4, 0, 0, 2, 1, 3, 0)
R_FCON2 = (0, 0, 5, 5, 5, 5, 5, 5, 0, 0, 5, 5, 5, 6, 8, 8, 0, 0, 8, 6, 7, 9, 9, 9, 0, 0, 7, 6, 8, 5)
R_VBASE = (0, 0, 0, 311, 314, 317, 320, 323, 0, 0, 326, 329, 332, 335, 339, 343, 0, 0, 347, 351, 355, 358, 361, 364,
           0, 0, 367, 370, 374, 378)
R_VKIND = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0)
# hanterm final variant by medial value: lcon_map[] of hanterm's own source (hfont.c in hanterm-xf 2.0.0 / 2.0.6,
# hangul.c in hanterm 3.1-3.3.1p18 - the same 30 numbers in all seven). It is NOT the 8x4x4 final table: wae, oe, we
# and ui (values 15, 18, 22, 28) are 0, 0, 1, 0 there, not 2, 1, 2, 1.
R_LMAP = (0, 0, 0, 0, 2, 0, 2, 1, 0, 0, 2, 1, 2, 3, 0, 0, 0, 0, 0, 3, 3, 1, 1, 1, 0, 0, 3, 3, 0, 1)
R_P16_INIT0 = (0, 0, 0, 0, 0, 0, 0, 0, 1, 3, 3, 3, 1, 2, 3, 3, 3, 2, 1, 3, 0)
R_P16_INIT1 = (4, 4, 4, 4, 4, 4, 4, 4, 5, 6, 6, 6, 5, 5, 6, 6, 6, 5, 5, 6, 4)
R_P16_FIN = (0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0)
R_P40 = (0, 1, 0, 1, 0, 1, 0, 1, 2, 4, 5, 4, 2, 3, 4, 5, 4, 3, 2, 4, 0)


# Research data outside this repository (the tests that need it skip without it): JOHAB_FONTS names its root.
JOHAB_FONTS = os.environ.get("JOHAB_FONTS", os.path.join(HERE, "no-johab-fonts"))
HANTERM_BDF = os.path.join(JOHAB_FONTS, "x11-unix/extracted/hanterm-font-3.1/hanterm-font/10-6-6/johabm16.bdf")

# A straight port of hanterm-xf hfont.c: convert_johab_to_3() and convert_3_to_johabfont() (hanterm-xf 2.0.0-167).
# The tables are typed from the C source, indexed by the 5-bit Johab value like the original.
C_FCON_MAP1 = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 3, 3, 0, 0, 3, 1, 2, 4, 4, 4, 0, 0, 2, 1, 3, 0)
C_FCON_MAP2 = (0, 0, 5, 5, 5, 5, 5, 5, 0, 0, 5, 5, 5, 6, 8, 8, 0, 0, 8, 6, 7, 9, 9, 9, 0, 0, 7, 6, 8, 5)
C_VOW_BASE = (0, 0, 0, 311, 314, 317, 320, 323, 0, 0, 326, 329, 332, 335, 339, 343, 0, 0, 347, 351, 355, 358, 361, 364,
              0, 0, 367, 370, 374, 378)
C_VOW_KIND = (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0)
C_LCON_KIND = (0, 0, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
C_LCON_MAP = (0, 0, 0, 0, 2, 0, 2, 1, 0, 0, 2, 1, 2, 3, 0, 0, 0, 0, 0, 3, 3, 1, 1, 1, 0, 0, 3, 3, 0, 1)


def hanterm_c_glyphs(cp):
    src = chr(cp).encode("johab")			# Python's own Johab codec, independent of jamoset
    f = (src[0] >> 2) & 0x1f
    m = ((src[0] << 3) | (src[1] >> 5)) & 0x1f
    l = src[1] & 0x1f
    out = []
    if f != 1:
        out.append(f * 10 + (C_FCON_MAP2[m] if l > 1 else C_FCON_MAP1[m]) - 19)
    if m != 2:
        ind = C_VOW_BASE[m]
        if C_VOW_KIND[m] == 0:
            ind += C_LCON_KIND[l]
        else:
            ind += (0 if (f == 2 or f == 17) else 1) + (2 if l > 1 else 0)
        out.append(ind)
    if l != 1:
        out.append(l * 4 + C_LCON_MAP[m] + (397 if l < 18 else 393))
    return out



# ---- straight ports of other decoders, written from their sources (not from kfont.py / jamoset) ----------------------

def hanterm_844_glyphs(cp):
    """hanterm-xf hfont.c convert_3_to_jo844font(), same johab input as hanterm_c_glyphs()."""
    src = chr(cp).encode("johab")
    f = (src[0] >> 2) & 0x1f
    m = ((src[0] << 3) | (src[1] >> 5)) & 0x1f
    l = src[1] & 0x1f
    index1 = (0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    index2 = (0, 0, 0, 1, 2, 3, 4, 5, 0, 0, 6, 7, 8, 9, 10, 11, 0, 0, 12, 13, 14, 15, 16, 17, 0, 0, 18, 19, 20, 21, 0, 0)
    index3 = (0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 0, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26,
              27, 0, 0)
    type1_no = (0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 3, 3, 3, 1, 2, 4, 4, 4, 2, 1, 3, 0)
    type1_yes = (5, 5, 5, 5, 5, 5, 5, 5, 5, 6, 7, 7, 7, 6, 6, 7, 7, 7, 6, 6, 7, 5)
    type3_t = (0, 0, 2, 0, 2, 1, 2, 1, 2, 3, 0, 2, 1, 3, 3, 1, 2, 1, 3, 3, 1, 1)
    h1, h2, h3 = index1[f], index2[m], index3[l]
    type1 = (type1_yes if h3 else type1_no)[h2]
    type2 = (0 if h1 in (0, 1, 16) else 1) + (2 if h3 else 0)
    type3 = type3_t[h2]
    out = []
    if h1:
        out.append(type1 * 20 + h1)
    if h2:
        out.append(type2 * 22 + h2 + 160)
    if h3:
        out.append(type3 * 28 + h3 + 160 + 88)
    return out


def iolo_glyphs(cp, kinds):
    """iolo 8x4x4-fonts / 6x2x1-fonts generate_hangul_syllables.py: the (cho, jung, jong) kinds of a syllable as the
    index of each piece in the raw font (kind sets in file order, the filler first in the initial and medial sets)."""
    cho, jung, jong = lvt(cp)
    num_cho, num_jung, num_jong = 19, 21, 28
    if kinds == "8x4x4":
        no, yes = (0, 0, 0, 0, 0, 0, 0, 0, 1, 3, 3, 3, 1, 2, 4, 4, 4, 2, 1, 3, 0), (5, 5, 5, 5, 5, 5, 5, 5, 6, 7, 7, 7, 6, 6, 7, 7, 7, 6, 6, 7, 5)
        jong_by_jung = (0, 2, 0, 2, 1, 2, 1, 2, 3, 0, 2, 1, 3, 3, 1, 2, 1, 3, 3, 1, 1)
        if jong == 0:
            cho_kind, jung_kind = no[jung], 0 if cho in (0, 15) else 1
        else:
            cho_kind, jung_kind = yes[jung], 2 if cho in (0, 15) else 3
        jong_kind = jong_by_jung[jung]
        cho_kinds, jung_kinds = 8, 4
    else:
        no, yes = (0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 2, 2, 1, 1, 2, 2, 2, 1, 1, 2, 0), (3, 3, 3, 3, 3, 3, 3, 3, 4, 5, 5, 5, 4, 4, 5, 5, 5, 4, 4, 5, 3)
        cho_kind, jung_kind = (no if jong == 0 else yes)[jung], 0 if jong == 0 else 1
        jong_kind = 0
        cho_kinds, jung_kinds = 6, 2
    pua_jung = (num_cho + 1) * cho_kinds
    pua_jong = pua_jung + (num_jung + 1) * jung_kinds
    out = [(num_cho + 1) * cho_kind + cho + 1, pua_jung + (num_jung + 1) * jung_kind + jung + 1]
    if jong:
        out.append(pua_jong + num_jong * jong_kind + jong)
    return out


def san_10_4_4_glyphs(cp):
    """drypot/san-1.0 HANDRV.C Draw10_4_4(): run the MemCopy/MemOR calls on glyphs that are sets of source pieces,
    then read the syllable's initial+medial glyph from the table it builds; the final comes from the final sets
    (source pieces 288.., set chosen by the medial as in hanterm's _type3)."""
    cho = (0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 3, 3, 3, 1, 2, 4, 4, 4, 2, 1, 3, 0)
    mid = (0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1)
    font = [frozenset([i]) for i in range(400)]
    han = []
    for i in range(22):
        han.append(font[10 * 20 + i])
    for i in range(1, 20):
        han.append(font[i])
        for j in range(1, 22):
            han.append(font[cho[j] * 20 + i] | font[10 * 20 + mid[i] * 22 + j])
    for i in range(22):
        han.append(font[10 * 20 + 2 * 22 + i])
    for i in range(1, 20):
        han.append(font[5 * 20 + i])
        for j in range(1, 22):
            han.append(font[(cho[j] + 5) * 20 + i] | font[10 * 20 + (mid[i] + 2) * 22 + j])
    L, V, T = lvt(cp)
    i, j = L + 1, V + 1
    base = 22 + (i - 1) * 22 if T == 0 else 22 + 19 * 22 + 22 + (i - 1) * 22
    glyph = han[base + j]
    pieces = sorted(glyph)
    if T:
        pieces.append(288 + (0, 2, 0, 2, 1, 2, 1, 2, 3, 0, 2, 1, 3, 3, 1, 2, 1, 3, 3, 1, 1)[V] * 28 + T)
    return pieces


def lvt(cp):
    i = cp - 0xAC00
    return i // 588, (i // 28) % 21, i % 28


def sel_844(L, V, T, kk_first=True):
    kk = (L in KK) == kk_first
    out = [(I844_FIN if T else I844_NOFIN)[V] * 20 + L + 1, 160 + ((0 if kk else 1) + (2 if T else 0)) * 22 + V + 1]
    if T:
        out.append(248 + F844[V] * 28 + T)
    return out


def sel_ihnm(L, V, T):
    return sel_844(L, V, T, kk_first=False)


def sel_1044(L, V, T):
    out = [(I844_NOFIN[V] + (5 if T else 0)) * 20 + L + 1,
           200 + ((0 if L in KK else 1) + (2 if T else 0)) * 22 + V + 1]
    if T:
        out.append(288 + F844[V] * 28 + T)
    return out


def sel_621(L, V, T):
    out = [(R621_FIN if T else R621_NOFIN)[V] * 20 + L + 1, 120 + (22 if T else 0) + V + 1]
    if T:
        out.append(164 + T)
    return out


def sel_kyra(L, V, T):
    out = [1 + 10 * L + 2 * I844_NOFIN[V] + (1 if T else 0),
           191 + 1 + 4 * V + (0 if L in KK else 2) + (1 if T else 0)]
    if T:
        out.append(276 + 1 + 4 * (T - 1) + F844[V])
    return out


def johab_fields(L, V, T):
    return L + 2, JUNG_FIELD[V], (T + 1 if T <= 16 else T + 2)


HT_LKIND = (0, 0, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)


def sel_hanterm(L, V, T):
    f, m, l = johab_fields(L, V, T)
    out = [f * 10 + (R_FCON2 if l > 1 else R_FCON1)[m] - 19]
    ind = R_VBASE[m]
    if R_VKIND[m] == 0:
        ind += HT_LKIND[l]
    else:
        ind += (0 if f in (2, 17) else 1) + (2 if l > 1 else 0)
    out.append(ind)
    if l != 1:
        out.append(l * 4 + R_LMAP[m] + (397 if l < 18 else 393))
    return out


def sel_dkb16(L, V, T):
    f = T > 0
    out = [(R_P16_INIT1 if f else R_P16_INIT0)[V] * 20 + L + 1, 140 + f * 22 + V + 1]
    if f:
        out.append(184 + R_P16_FIN[V] * 28 + T)
    return out


def sel_dkb40(L, V, T):
    f = T > 0
    out = [(R_P40[V] + 6 * f) * 20 + L + 1, 240 + (2 * f + (L not in KK)) * 22 + V + 1]
    if f:
        out.append(328 + F844[V] * 28 + T)
    return out


REFERENCE = {"844": sel_844, "844-ihnm": sel_ihnm, "1044-san": sel_1044, "621": sel_621, "hanterm-johab": sel_hanterm,
             "dkb-printer-7x2x2": sel_dkb16, "dkb-printer-12x4x4": sel_dkb40, "kyra-lok": sel_kyra,
             "844-hbios24": sel_844}

# 가 각 한 의 뷁 흙, by hand from the research doc's formulas (3.2, 3.3, 3.4, 6.1, formats 2.5-2.9).
SAMPLES = (0xAC00, 0xAC01, 0xD55C, 0xC758, 0xBDC1, 0xD759)
HAND = {
    # 844: 각 = initial set 5, medial set 2 (g/k, final), final set 0. 한 = h a n: initial set 5, medial set 1+2.
    # 의 = ieung ui: initial set 3, medial set 1.
    "844": ((1, 161), (101, 205, 249), (119, 227, 252), (72, 202), (148, 242, 313), (139, 245, 341)),
    "844-ihnm": ((1, 183), (101, 227, 249), (119, 205, 252), (72, 180), (148, 220, 313), (139, 223, 341)),
    "1044-san": ((1, 201), (101, 245, 289), (119, 267, 292), (72, 242), (188, 282, 353), (139, 285, 381)),
    "621": ((1, 121), (61, 143, 165), (79, 143, 168), (52, 140), (108, 158, 173), (99, 161, 173)),
    "kyra-lok": ((1, 192), (2, 193, 277), (182, 195, 289), (117, 270), (80, 255, 311), (184, 267, 312)),
    # hanterm: han uses the nieun-final medial variant (2), the others variant 1; bwel final: lcon_map[we] = 1.
    "hanterm-johab": ((1, 311), (6, 312, 405), (186, 313, 417), (114, 375), (80, 362, 438), (187, 373, 440)),
    "dkb-printer-7x2x2": ((1, 141), (81, 163, 185), (99, 163, 188), (72, 160), (128, 178, 221), (119, 181, 221)),
    "dkb-printer-12x4x4": ((1, 241), (121, 285, 329), (139, 307, 332), (92, 282), (228, 322, 393), (179, 325, 421)),
}


def make_source(layout_name, seed=1):
    """Bytes of a synthetic source font of the layout, every piece with its own pixels; blank slots stay blank."""
    rnd = random.Random(seed)
    if layout_name in ("844", "844-ihnm"):
        gb, n, blanks = 32, 360, [s * 20 for s in range(8)] + [160 + s * 22 for s in range(4)] + [248 + s * 28 for s in range(4)]
    elif layout_name == "844-hbios24":
        return DosFace24.hbios(seed)
    elif layout_name == "1044-san":
        gb, n, blanks = 32, 400, [s * 20 for s in range(10)] + [200 + s * 22 for s in range(4)] + [288 + s * 28 for s in range(4)]
    elif layout_name == "621":
        gb, n, blanks = 32, 192, []
    elif layout_name == "kyra-lok":
        gb, n, blanks = 30, 385, []
    elif layout_name == "dkb-printer-7x2x2":
        gb, n, blanks = 32, 480, []
    elif layout_name == "dkb-printer-12x4x4":
        gb, n, blanks = 200, 880, []
    else:
        raise KeyError(layout_name)
    data = bytearray(rnd.randbytes(gb * n))
    for b in blanks:
        data[b * gb:(b + 1) * gb] = bytes(gb)
    if layout_name == "kyra-lok":
        for i in range(n):
            for y in range(15):
                data[i * 30 + y * 2 + 1] &= 0xFE		# 15 columns: the 16th bit is padding
    return bytes(data)


def make_bdf(seed=1):
    """A hanterm-style johab-1 BDF: 529 glyphs 16x16, ENCODING = glyph number, every glyph with its own pixels."""
    rnd = random.Random(seed)
    out = ["STARTFONT 2.1", "FONT -hanterm-test-medium-r-normal--16-160-75-75-c-160-johab-1",
           "FONTBOUNDINGBOX 16 16 0 -2", "STARTPROPERTIES 2", "FONT_ASCENT 14", "FONT_DESCENT 2", "ENDPROPERTIES",
           "CHARS 529"]
    for enc in range(529):
        out += [f"STARTCHAR g{enc}", f"ENCODING {enc}", "SWIDTH 1000 0", "DWIDTH 16 0", "BBX 16 16 0 -2", "BITMAP"]
        out += ["%04X" % (0 if enc == 0 else rnd.getrandbits(16)) for _ in range(16)]
        out.append("ENDCHAR")
    out.append("ENDFONT")
    return ("\n".join(out) + "\n").encode("latin-1")


def raw_piece(name, data, i):
    """Glyph i of a synthetic source as the SVFN 1bpp rows, read straight from the bytes (not through jamoset)."""
    if name in ("844", "844-ihnm", "1044-san"):
        return data[i * 32:(i + 1) * 32]
    if name == "844-hbios24":			# 90 byte glyphs of a 24x30 cell: ink rows 3-26 are the 24 rows
        return data[i * 90 + 9:i * 90 + 81]
    if name == "kyra-lok":			# 15 columns: two bytes a row, the 16th bit is padding (zero in make_source)
        return data[i * 30:(i + 1) * 30]
    if name == "dkb-printer-12x4x4":
        return data[i * 200:(i + 1) * 200]
    if name == "621":				# two columns of sixteen bytes
        g = data[i * 32:(i + 1) * 32]
        return bytes(b for y in range(16) for b in (g[y], g[16 + y]))
    if name == "dkb-printer-7x2x2":		# sixteen columns of two bytes, MSB = top row
        g = data[i * 32:(i + 1) * 32]
        rows = [0] * 16
        for c in range(16):
            col = g[c * 2] << 8 | g[c * 2 + 1]
            for r in range(16):
                rows[r] |= (col >> (15 - r) & 1) << (15 - c)
        return b"".join(r.to_bytes(2, "big") for r in rows)
    if name == "hanterm-johab":			# the glyph's hex rows, top first (BBX 16 16 0 -2, ascent 14)
        text = data.decode("latin-1")
        at = text.index("ENCODING %d\n" % i)
        rows = text[text.index("BITMAP\n", at) + 7:text.index("ENDCHAR", at)].split()
        return b"".join(int(r, 16).to_bytes(2, "big") for r in rows)
    raise KeyError(name)


def source_for(name):
    return make_bdf() if name == "hanterm-johab" else make_source(name)


def src_pieces(layout, data):
    return layout.opener(data, 0, "")


class TablesMatchResearchTools(unittest.TestCase):
    def test_all_syllables_every_layout(self):
        for name, layout in jamoset.LAYOUTS.items():
            t = jamoset.tables_for(layout)
            ref = REFERENCE[name]
            for cp in range(0xAC00, 0xD7A4):
                self.assertEqual(jamoset.pieces_of(t, cp), ref(*lvt(cp)), f"{name} U+{cp:04X}")

    def test_844_and_hbios24_equal_hanterms_own_844_code_and_ioloS_script(self):
        for name in ("844", "844-hbios24"):
            t = jamoset.tables_for(jamoset.LAYOUTS[name])
            for cp in range(0xAC00, 0xD7A4):
                self.assertEqual(jamoset.pieces_of(t, cp), hanterm_844_glyphs(cp), f"{name} U+{cp:04X}")
                self.assertEqual(jamoset.pieces_of(t, cp), iolo_glyphs(cp, "8x4x4"), f"{name} U+{cp:04X}")

    def test_621_equals_ioloS_6x2x1_script(self):
        t = jamoset.tables_for(jamoset.LAYOUTS["621"])
        for cp in range(0xAC00, 0xD7A4):
            self.assertEqual(jamoset.pieces_of(t, cp), iolo_glyphs(cp, "6x2x1"), f"U+{cp:04X}")

    def test_1044_san_equals_the_san_driver_port(self):
        t = jamoset.tables_for(jamoset.LAYOUTS["1044-san"])
        for cp in range(0xAC00, 0xD7A4):
            self.assertEqual(jamoset.pieces_of(t, cp), san_10_4_4_glyphs(cp), f"U+{cp:04X}")


    def test_hand_checked_syllables(self):
        for name, expected in HAND.items():
            t = jamoset.tables_for(jamoset.LAYOUTS[name])
            for cp, want in zip(SAMPLES, expected):
                self.assertEqual(tuple(jamoset.pieces_of(t, cp)), want, f"{name} U+{cp:04X}")

    def test_no_final_syllable_has_two_pieces(self):
        for name, layout in jamoset.LAYOUTS.items():
            t = jamoset.tables_for(layout)
            self.assertEqual(len(jamoset.pieces_of(t, 0xAC00)), 2, name)
            self.assertEqual(len(jamoset.pieces_of(t, 0xAC01)), 3, name)

    def test_844_uses_344_pieces(self):
        t = jamoset.tables_for(jamoset.LAYOUTS["844"])
        used = jamoset.used_pieces(t)
        self.assertEqual(len(used), 344)		# 360 minus the 16 blank fill slots
        self.assertEqual(len(set(used)), 344)

    def test_garbage_final_set_of_the_no_final_class_is_zero(self):
        for layout in jamoset.LAYOUTS.values():
            t = jamoset.tables_for(layout)
            for lc in range(t.lc):
                for v in range(21):
                    cell = (lc * 21 + v) * t.tc + t.tail_class[0]
                    if t.tail_class[0] not in {t.tail_class[k] for k in range(1, 28)}:
                        self.assertEqual(t.fin_set[cell], 0, layout.name)


class CompatJamo(unittest.TestCase):
    def test_844_compat_pieces(self):
        t = jamoset.tables_for(jamoset.LAYOUTS["844"])
        self.assertEqual(t.compat[0], 1)				# U+3131 g: initial set 0
        self.assertEqual(t.compat[3], 3)				# U+3134 n: initial 2 -> 2+1
        self.assertEqual(t.compat[2], 248 + 3)			# U+3133 gs: a final-only consonant, final set 0
        self.assertEqual(t.compat[0x314F - 0x3131], 161)		# U+314F a: medial set 0
        self.assertEqual(t.compat[0x3163 - 0x3131], 160 + 20 + 1)	# U+3163 i
        self.assertEqual(len(t.compat), 51)
        self.assertNotIn(jamoset.BLANK, t.compat)

    def test_every_layout_draws_every_compat_jamo(self):
        for layout in jamoset.LAYOUTS.values():
            t = jamoset.tables_for(layout)
            self.assertNotIn(jamoset.BLANK, t.compat, layout.name)


class WrittenFile(unittest.TestCase):
    def test_844_composes_like_johab844_for_all_syllables(self):
        layout = jamoset.LAYOUTS["844"]
        data = make_source("844")
        eng = bytes(random.Random(5).randbytes(4096))
        out, mapping, src = jamoset.build(layout, data, eng=eng)
        f = jamoset.parse_svfn(out)
        self.assertTrue(f.flags & jamoset.FLAG_JAMO)
        self.assertEqual(len(f.jset), jamoset._jset_size_v1(2, 2, 8, 4, 4))
        t = jamoset.unpack(f.jset)
        self.assertEqual(len(mapping), 344)
        for cp in range(0xAC00, 0xD7A4):
            self.assertEqual(jamoset.compose(f, t, cp), johab844.compose(data, cp), f"U+{cp:04X}")
        msg = jamoset.check(out, layout, data)
        self.assertIn("identical to johab844.py", msg)

    def test_every_layout_composes_the_or_of_its_source_pieces(self):
        for name, layout in jamoset.LAYOUTS.items():
            data = source_for(name)
            src = layout.opener(data, 0, "")
            out, mapping, _ = jamoset.build(layout, data)
            f = jamoset.parse_svfn(out)
            self.assertEqual((f.cell_w, f.cell_h), (src.w, src.h), name)
            t = jamoset.unpack(f.jset)
            ref = REFERENCE[name]
            for cp in range(0xAC00, 0xD7A4):
                want = bytearray(((src.w + 7) // 8) * src.h)
                for i in ref(*lvt(cp)):
                    for k, b in enumerate(raw_piece(name, data, i)):
                        want[k] |= b
                self.assertEqual(jamoset.compose(f, t, cp), bytes(want), f"{name} U+{cp:04X}")

    def test_header_and_block_placement(self):
        layout = jamoset.LAYOUTS["844"]
        out, _, _ = jamoset.build(layout, make_source("844"), eng=bytes(4096))
        (magic, version, flags, bpp, _b9, _b10, _b11, count, cw, ch, ascent, _lo, _hi, _b19, metrics_off, data_off,
         data_size, cmap_off, jset_off, jset_size, tab_off) = struct.unpack_from(jamoset.HEADER3, out)
        self.assertEqual((magic, version, bpp, cw, ch), (b"SVFN", 3, 1, 16, 16))
        self.assertEqual(flags, 3)					# proportional + jamo sets
        self.assertEqual(out[jset_off:jset_off + 4], b"JSET")
        # The block is exactly the length the engine requires; the tables follow each other in file order.
        self.assertEqual(jset_size, jamoset._jset_size_v1(2, 2, 8, 4, 4))
        self.assertEqual(cmap_off, jamoset.HEADER3_SIZE)
        self.assertEqual(jset_off, cmap_off + 8 * count)
        self.assertEqual(metrics_off, (jset_off + jset_size + 3) // 4 * 4)		# each table starts on 2^tab (4)
        self.assertLess(metrics_off, tab_off)
        self.assertLess(tab_off, data_off)
        self.assertEqual(len(out), data_off + data_size)
        self.assertEqual(count, 344 + 95)			# pieces and ASCII 0x20..0x7E

    def test_ascii_from_eng_sits_at_the_left_and_steps_8(self):
        eng = bytearray(4096)
        eng[ord("A") * 16 + 3] = 0xC3
        out, _, _ = jamoset.build(jamoset.LAYOUTS["844"], make_source("844"), eng=bytes(eng))
        f = jamoset.parse_svfn(out)
        self.assertEqual(f.glyphs[ord("A")][3 * 2:3 * 2 + 2], bytes([0xC3, 0]))
        self.assertEqual(f.metrics[ord("A")], (8, 0, 8))
        self.assertEqual(f.metrics[ord(" ")][0], 8)

    def test_kyra_ascii_stays_a_narrow_cell(self):
        out, _, _ = jamoset.build(jamoset.LAYOUTS["kyra-lok"], make_source("kyra-lok"), eng=bytes(4096))
        f = jamoset.parse_svfn(out)
        self.assertEqual(f.cell_w, 15)
        self.assertEqual(f.metrics[ord("A")][0], 7)	# not past half the cell, or it would take two cells
        self.assertEqual(unpack_advance(out), 16)

    def test_base_keeps_non_syllable_glyphs_and_refuses_another_cell(self):
        w = h = 16
        stride = 32
        glyphs = [(ord("A"), bytes(range(32)), 9, 1, 7), (0xAC00, bytes([0xFF] * 32), 16, 0, 16),
                  (0x2605, bytes([0x0F] * 32), 16, 4, 4)]
        base = bytearray(jamoset.write_svfn(w, h, 14, glyphs, b""))
        struct.pack_into("<H", base, 6, 1)		# a plain proportional font: no jamo flag
        out, _, _ = jamoset.build(jamoset.LAYOUTS["844"], make_source("844"), base=bytes(base))
        f = jamoset.parse_svfn(out)
        self.assertEqual(f.glyphs[ord("A")], bytes(range(32)))
        self.assertEqual(f.metrics[ord("A")], (9, 1, 7))
        self.assertEqual(f.glyphs[0x2605], bytes([0x0F] * 32))
        self.assertNotIn(0xAC00, f.glyphs)		# syllables come from pieces only
        self.assertEqual(f.ascent, 14)
        small = jamoset.write_svfn(8, 8, 7, [(65, bytes(8), 8, 0, 0)], b"")
        small = bytearray(small)
        struct.pack_into("<H", small, 6, 1)
        with self.assertRaises(jamoset.SourceError):
            jamoset.build(jamoset.LAYOUTS["844"], make_source("844"), base=bytes(small))

    def test_wrong_source_size_is_refused(self):
        for name in jamoset.LAYOUTS:
            with self.assertRaises(jamoset.SourceError, msg=name):
                jamoset.LAYOUTS[name].opener(b"\0" * 1234, 0, "")

    def test_844_refuses_a_file_whose_fill_slots_are_not_blank(self):
        data = bytearray(make_source("844"))
        for s in (0, 20, 40):
            data[s * 32] = 1
        with self.assertRaises(jamoset.SourceError):
            jamoset.LAYOUTS["844"].opener(bytes(data), 0, "")

    def test_printer_face_selects_the_second_typeface(self):
        data = make_source("dkb-printer-12x4x4")
        layout = jamoset.LAYOUTS["dkb-printer-12x4x4"]
        a = layout.opener(data, 0, "").glyph(1).to_bytes()
        b = layout.opener(data, 1, "").glyph(1).to_bytes()
        self.assertEqual(a, data[200:400])
        self.assertEqual(b, data[440 * 200 + 200:440 * 200 + 400])


def unpack_advance(out):
    return jamoset.unpack(jamoset.parse_svfn(out).jset).advance


class JsetCodec(unittest.TestCase):
    def good(self):
        return jamoset.pack_v1(jamoset.renumber(jamoset.tables_for(jamoset.LAYOUTS["844"]),
                                             {s: s for s in range(360)}))

    def test_round_trip(self):
        t = jamoset.unpack(self.good())
        self.assertEqual(jamoset.pieces_of(t, 0xAC01), [101, 205, 249])

    def test_malformed_blocks_are_refused_like_the_engine_does(self):
        g = self.good()
        cases = {
            "magic": b"X" + g[1:],
            "length": g[:-1],
            "length extra": g + b"\0",
            "lead classes": g[:6] + b"\x14" + g[7:],
            "leadClass": g[:12 + 3] + b"\x02" + g[12 + 4:],
            "initSet": g[:59 + 5] + b"\x08" + g[59 + 6:],
            "tail classes": g[:7] + b"\x1d" + g[8:],
            "initial sets": g[:8] + b"\x81" + g[9:],
            "medial sets": g[:9] + b"\x81" + g[10:],
            "final sets": g[:10] + b"\x41" + g[11:],
        }
        for what, data in cases.items():
            with self.assertRaises(ValueError, msg=what) as cm:
                jamoset.unpack(data)
            self.assertIn(what.split()[0], str(cm.exception))

    @staticmethod
    def limits_table(lc, tc, ni=32, nm=24, nf=16):
        """lc x tc classes at ni/nm/nf sets (32/24/16 by default), every class, set and piece used (the engine test's
        makeLimitsJset)."""
        t = jamoset.Tables(lc, tc, ni, nm, nf)
        t.lead_class = [L % lc for L in range(19)]
        t.tail_class = [0] + [1 + (T - 1) % (tc - 1) for T in range(1, 28)]
        n = lc * 21 * tc
        t.init_set, t.med_set, t.fin_set = [c % ni for c in range(n)], [c % nm for c in range(n)], [c % nf for c in range(n)]
        t.init_piece = [1 + i for i in range(ni * 19)]
        t.med_piece = [1000 + i for i in range(nm * 21)]
        t.fin_piece = [2000 + i for i in range(nf * 27)]
        return t

    def test_12x12_classes_round_trip_and_13_is_refused(self):
        # The class limits are 12 x 12 (8 x 8 before 2026-10): the largest block is 12321 bytes (32/24/16 sets).
        self.assertEqual((jamoset.MAX_LEAD_CLASSES, jamoset.MAX_TAIL_CLASSES), (12, 12))
        for lc, tc in ((12, 12), (8, 8), (12, 4)):
            data = jamoset.pack_v1(self.limits_table(lc, tc))
            self.assertEqual(len(data), jamoset._jset_size_v1(lc, tc, 32, 24, 16))
            t = jamoset.unpack(data)
            self.assertEqual((t.lc, t.tc), (lc, tc))
            for cp in (0xAC00, 0xAC0B, 0xC544, 0xD7A3):
                L, V, T = jamoset.decompose(cp)
                cell = ((L % lc) * 21 + V) * tc + (1 + (T - 1) % (tc - 1) if T else 0)
                want = [1 + cell % 32 * 19 + L, 1000 + cell % 24 * 21 + V] + ([2000 + cell % 16 * 27 + T - 1] if T else [])
                self.assertEqual(jamoset.pieces_of(t, cp), want)
        self.assertEqual(len(jamoset.pack_v1(self.limits_table(12, 12))), 12321)
        for what, lc, tc in (("lead classes", 13, 12), ("tail classes", 12, 13)):
            t = self.limits_table(12, 12)
            t.lc, t.tc = lc, tc
            n = lc * 21 * tc
            t.init_set, t.med_set, t.fin_set = [0] * n, [0] * n, [0] * n
            with self.assertRaises(ValueError) as cm:
                jamoset.unpack(jamoset.pack_v1(t))
            self.assertIn(what, str(cm.exception))
            self.assertIn("1..12", str(cm.exception))

    def test_set_limits_32_24_16_round_trip_compose_and_33_25_17_refused(self):
        # 2026-10 (v3): NI 1..32, NM 1..24, NF 1..16.
        t = self.limits_table(12, 12)
        self.assertEqual((t.ni, t.nm, t.nf), (32, 24, 16))
        glyphs = [(jamoset.PIECE_BASE + n, bytes([n & 0xFF, (n >> 8) | 0x80]) + bytes(6), 8, 0, 8)
                  for n in sorted(set(t.init_piece + t.med_piece + t.fin_piece))]
        data = jamoset.write_svfn(8, 8, 7, glyphs, jamoset.pack_v1(t))
        f = jamoset.parse_svfn(data)
        u = jamoset.unpack(f.jset)
        self.assertEqual((u.ni, u.nm, u.nf), (32, 24, 16))
        self.assertEqual(u.init_piece, t.init_piece)
        self.assertEqual(u.fin_piece, t.fin_piece)
        for cp in range(0xAC00, 0xD7A4, 7):
            want = bytearray(8)
            for n in jamoset.pieces_of(u, cp):
                for i, b in enumerate(f.glyphs[jamoset.PIECE_BASE + n]):
                    want[i] |= b
            self.assertEqual(jamoset.compose(f, u, cp), bytes(want))
        # the initial 31, medial 23 and final 15 sets (the last of each) are used by some syllable
        self.assertEqual(max(t.init_set), 31)
        self.assertEqual(max(t.med_set), 23)
        self.assertEqual(max(t.fin_set), 15)
        for what, args in (("initial sets", (33, 24, 16)), ("medial sets", (32, 25, 16)), ("final sets", (32, 24, 17))):
            with self.assertRaises(ValueError) as cm:
                jamoset.unpack(jamoset.pack_v1(self.limits_table(12, 12, *args)))
            self.assertIn(what, str(cm.exception))
            self.assertIn(f"1..{ {'initial sets': 32, 'medial sets': 24, 'final sets': 16}[what] }", str(cm.exception))


class TestJset2(unittest.TestCase):
    """JSET block version 2 (docs/superpowers/specs/2026-10-23-jset-compact-design.md)."""

    @staticmethod
    def t844():
        return jamoset.renumber(jamoset.tables_for(jamoset.LAYOUTS["844"]), {s: s for s in range(360)})

    def alias_table(self):
        """844 with final set 1 tail 1 = final set 0's piece and medial set 3 vowel 0 = medial set 0's."""
        t = self.t844()
        t.fin_piece[1 * 27 + 0] = t.fin_piece[0]
        t.med_piece[3 * 21 + 0] = t.med_piece[0]
        return t

    @staticmethod
    def odd_table():
        """844 cut to 6/3/3 sets, so each set field can hold a number at its count (rule (4))."""
        t = TestJset2.t844()
        t.ni, t.nm, t.nf = 6, 3, 3
        t.init_set = [s % 6 for s in t.init_set]
        t.med_set = [s % 3 for s in t.med_set]
        t.fin_set = [s % 3 for s in t.fin_set]
        t.init_piece, t.med_piece, t.fin_piece = t.init_piece[:6 * 19], t.med_piece[:3 * 21], t.fin_piece[:3 * 27]
        return t

    def test_sizes(self):
        self.assertEqual(jamoset.jset_size(8, 8, 32, 24, 12), 2818)
        self.assertEqual(jamoset.jset_size(2, 2, 8, 4, 4), 272)
        self.assertEqual(jamoset.jset_size(1, 2, 6, 2, 1), 181)
        self.assertEqual(jamoset.jset_size(12, 12, 32, 24, 16, 1544), 9246)
        self.assertEqual(jamoset.jset_size(12, 12, 32, 24, 16), 5782)
        self.assertEqual((jamoset.JSET_VERSION, jamoset.JSET_HEADER), (2, 16))
        self.assertEqual([jamoset.jset_width(n) for n in (1, 2, 3, 16, 17, 32)], [0, 1, 2, 4, 5, 5])

    def test_compat_constants(self):
        self.assertEqual(len(jamoset.COMPAT_HOME), 51)
        self.assertEqual(jamoset.COMPAT_HOME[0], ("i", 0))
        self.assertEqual(jamoset.COMPAT_HOME[2], ("f", 3))
        self.assertEqual(jamoset.COMPAT_HOME[30], ("m", 0))
        self.assertEqual(len(jamoset.COMPAT_FINAL_ALT), 30)
        alt = {chr(0x3131 + k): v for k, v in enumerate(jamoset.COMPAT_FINAL_ALT) if v is not None}
        self.assertEqual(alt, dict(zip("ㄱㄲㄴㄷㄹㅁㅂㅅㅆㅇㅈㅊㅋㅌㅍㅎ", (1, 2, 4, 7, 8, 16, 17, 19, 20, 21, 22, 23, 24, 25, 26, 27))))

    def test_card_figures(self):
        t = jamoset.Tables(8, 8, 32, 24, 12)
        t.lead_class = [L % 8 for L in range(19)]
        t.tail_class = [0] + [1 + (T - 1) % 7 for T in range(1, 28)]
        n = 8 * 21 * 8
        t.init_set, t.med_set, t.fin_set = [c % 32 for c in range(n)], [c % 24 for c in range(n)], [c % 12 for c in range(n)]
        t.init_piece = list(range(32 * 19))
        t.med_piece = list(range(1000, 1000 + 24 * 21))
        t.fin_piece = list(range(2000, 2000 + 12 * 27))
        t.compat = [t.init_piece[i] if k == "i" else t.med_piece[i] if k == "v" else t.fin_piece[i - 1]
                    for k, i in jamoset.COMPAT]
        self.assertEqual(len(jamoset.pack(t).block), 2818)
        self.assertEqual(len(jamoset.pack(self.t844()).block), 272)

    def test_round_trip_844(self):
        t = self.t844()
        packed = jamoset.pack(t)
        pm = packed.piece_map
        u = jamoset.unpack(packed.block)
        for cp in range(0xAC00, 0xD7A4):
            self.assertEqual(jamoset.pieces_of(u, cp), [pm[p] for p in jamoset.pieces_of(t, cp)], f"U+{cp:04X}")
        self.assertEqual(u.compat, [pm[p] for p in t.compat])
        again = jamoset.pack(u)
        self.assertEqual(again.block, packed.block)
        self.assertEqual(again.piece_map, {n: n for n in again.piece_map})
        self.assertEqual(sorted(again.piece_map), list(range(344)))

    def test_aliases(self):
        t = self.alias_table()
        packed = jamoset.pack(t)
        b = jamoset.decode_jset2(packed.block)
        self.assertEqual(b.na, 2)
        s = (84 * 7 + 7) // 8
        self.assertEqual(len(packed.block), 63 + s + 8 * 10 + 4 * 10 + 4 * 12 + 2 * 2 + 51)		# RI = RM = 10, RF = 12
        self.assertEqual(len(packed.block), jamoset.jset_size(2, 2, 8, 4, 4, 2))
        u = jamoset.unpack(packed.block)
        self.assertEqual(u.med_piece[3 * 21], u.med_piece[0])
        self.assertEqual(u.fin_piece[27], u.fin_piece[0])
        self.assertEqual(u.med_piece[0], packed.piece_map[t.med_piece[0]])
        self.assertEqual(u.fin_piece[0], packed.piece_map[t.fin_piece[0]])
        self.assertEqual(sorted(packed.piece_map.values()), list(range(len(packed.piece_map))))
        self.assertEqual(len(packed.piece_map), 342)
        for cp in range(0xAC00, 0xD7A4, 3):
            self.assertEqual(jamoset.pieces_of(u, cp), [packed.piece_map[p] for p in jamoset.pieces_of(t, cp)])

    def test_encode_refuses_u16_overflow(self):
        """encode_jset2: a row base or abase, or an alias entry, outside 0..0xFFFF is a ValueError naming it."""
        for what in ("base", "abase", "alias"):
            for v in (-1, 0x10000):
                with self.subTest(what=what, value=v):
                    b = jamoset.decode_jset2(jamoset.pack(self.t844()).block)
                    if what == "alias":
                        b.na, b.alias = 1, [v]
                    else:
                        b.rows["m"][1][0 if what == "base" else 1] = v
                    with self.assertRaisesRegex(ValueError, "^JSET .*%s" % what):
                        jamoset.encode_jset2(b)

    def test_bases_not_assumed_cumulative(self):
        b = jamoset.decode_jset2(jamoset.pack(self.t844()).block)
        r = b.rows["i"]
        self.assertEqual((r[0][0], r[1][0]), (0, 19))
        r[0][0], r[1][0] = r[1][0], 7            # out of order, and row 0's range overlaps row 1's
        u = jamoset.unpack(jamoset.encode_jset2(b))
        for s in range(2):
            self.assertEqual(u.init_piece[s * 19:s * 19 + 19], [r[s][0] + j for j in range(19)])
        self.assertEqual(u.init_piece[2 * 19:], list(range(38, 8 * 19)))

    def test_compat_bit7_round_trip(self):
        t = self.t844()
        t.init_piece[0] = jamoset.BLANK
        t.compat[0] = t.fin_piece[0]
        packed = jamoset.pack(t)
        self.assertEqual(jamoset.decode_jset2(packed.block).compat[0], 0x80)
        u = jamoset.unpack(packed.block)
        self.assertEqual(u.compat[0], packed.piece_map[t.fin_piece[0]])
        self.assertEqual(jamoset.pack(u).block, packed.block)
        t.compat[0] = 9999
        with self.assertRaisesRegex(ValueError, r"compat U\+3131: no set holds piece"):
            jamoset.pack(t)

    def test_pack_refuses_tables_over_the_limits(self):
        for attr, v, what in (("lc", 13, "lead classes"), ("tc", 13, "tail classes"), ("ni", 33, "initial sets"),
                              ("nm", 25, "medial sets"), ("nf", 17, "final sets")):
            t = self.t844()
            setattr(t, attr, v)
            with self.assertRaisesRegex(ValueError, "^JSET " + what):
                jamoset.pack(t)

    def test_validation_messages(self):
        def bad(block, prefix):
            with self.subTest(prefix=prefix):
                with self.assertRaises(ValueError) as cm:
                    jamoset.unpack(block)
                self.assertTrue(str(cm.exception).startswith(prefix), str(cm.exception))

        def edit(t, fn):
            b = jamoset.decode_jset2(jamoset.pack(t).block)
            fn(b)
            return jamoset.encode_jset2(b)

        plain, aliased, odd = self.t844(), self.alias_table(), self.odd_table()
        blanked = self.t844()
        blanked.init_piece[0] = jamoset.BLANK
        blanked.compat[0] = blanked.fin_piece[0]
        good = jamoset.pack(plain).block
        # (1) and (2): the header, the counts, NA, the length
        bad(good[:15], "JSET length")
        bad(b"JSEX" + good[4:], "JSET magic")
        bad(good[:4] + struct.pack("<H", 4) + good[6:], "JSET version")
        # a v1 body under version 2: its leadClass bytes 2-3 are the reserved u16, else its length is not v2's
        bad(jamoset.pack_v1(plain)[:4] + struct.pack("<H", 2) + jamoset.pack_v1(plain)[6:],
            ("JSET reserved", "JSET length"))
        with self.assertRaisesRegex(ValueError, r"^JSET version 1 is not a version 2 block"):
            jamoset.decode_jset2(jamoset.pack_v1(plain))
        for attr, v, what in (("lc", 20, "JSET lead classes"), ("tc", 0, "JSET tail classes"),
                              ("ni", 129, "JSET initial sets"), ("nm", 129, "JSET medial sets"),
                              ("nf", 65, "JSET final sets")):
            bad(edit(plain, lambda b: setattr(b, attr, v)), what)
        bad(edit(plain, lambda b: setattr(b, "reserved", 1)), "JSET reserved")

        def na_over(b):
            b.na = 8 * 19 + 4 * 21 + 4 * 27 + 1
            b.alias = [0] * b.na
        bad(edit(plain, na_over), "JSET NA")
        bad(good + b"\0", "JSET length")
        bad(jamoset.pack(aliased).block[:-1], "JSET length")
        # (3) and (4)
        bad(edit(plain, lambda b: b.lead_class.__setitem__(18, 2)), "JSET leadClass[18]")
        bad(edit(plain, lambda b: b.tail_class.__setitem__(27, 2)), "JSET tailClass[27]")
        used = set(odd.tail_class[1:])
        cell = next(c for c in range(len(odd.fin_set)) if c % odd.tc in used)
        bad(edit(odd, lambda b: b.init_set.__setitem__(0, 6)), "JSET initSet[0]")
        bad(edit(odd, lambda b: b.med_set.__setitem__(0, 3)), "JSET medSet[0]")
        bad(edit(odd, lambda b: b.fin_set.__setitem__(cell, 3)), f"JSET finSet[{cell}]")
        unused = [c for c in range(len(odd.fin_set)) if c % odd.tc not in used]
        if unused:                               # an unread cell may hold any number its field fits
            u = jamoset.unpack(edit(odd, lambda b: b.fin_set.__setitem__(unused[0], 3)))
            self.assertEqual(u.fin_set[unused[0]], 3)
        # (5) rows
        bad(edit(plain, lambda b: b.rows["i"][0].__setitem__(2, b.rows["i"][0][2] | 1 << 19)), "JSET initial row 0 padding")
        bad(edit(plain, lambda b: b.rows["m"][2].__setitem__(2, b.rows["m"][2][2] | 1 << 23)), "JSET medial row 2 padding")
        bad(edit(plain, lambda b: b.rows["f"][3].__setitem__(2, b.rows["f"][3][2] | 1 << 31)), "JSET final row 3 padding")
        bad(edit(aliased, lambda b: b.rows["f"][0].__setitem__(3, 1 << 27)), "JSET final row 0 padding")

        def alias_no_presence(b):
            b.rows["i"][0][2] &= ~(1 << 18)
            b.rows["i"][0][3] |= 1 << 18
        bad(edit(aliased, alias_no_presence), "JSET initial row 0 alias bits")
        bad(edit(aliased, lambda b: b.rows["f"][1].__setitem__(1, 2)), "JSET final row 1 abase")
        # (6) pieces
        bad(edit(aliased, lambda b: b.alias.__setitem__(0, 0xFFFF)), "JSET alias[0]")
        bad(edit(plain, lambda b: b.rows["m"][0].__setitem__(0, 0xFFF0)), "JSET piece")
        # (7) compat
        bad(edit(plain, lambda b: b.compat.__setitem__(0, 8)), "JSET compat[0]")
        bad(edit(plain, lambda b: b.compat.__setitem__(30, 4)), "JSET compat[30]")
        bad(edit(plain, lambda b: b.compat.__setitem__(2, 4)), "JSET compat[2]")
        bad(edit(plain, lambda b: b.compat.__setitem__(0, 0x84)), "JSET compat[0]")
        bad(edit(blanked, lambda b: b.compat.__setitem__(0, 0)), "JSET compat[0]")
        bad(edit(plain, lambda b: b.compat.__setitem__(0, 0x20)), "JSET compat[0]")
        bad(edit(plain, lambda b: b.compat.__setitem__(0, 0x40)), "JSET compat[0]")
        self.assertEqual(jamoset.COMPAT[24], ("i", 13))		# ㅉ
        for k in (30, 50, 7, 18, 24, 2):		# a vowel, ㄸ, ㅃ, ㅉ, the cluster ㄳ: no bit 7 form
            bad(edit(plain, lambda b: b.compat.__setitem__(k, 0x80)), f"JSET compat[{k}]")
            with self.assertRaisesRegex(ValueError, "bit 7"):
                jamoset.unpack(edit(plain, lambda b: b.compat.__setitem__(k, 0x80)))
        with self.assertRaisesRegex(ValueError, "no slot"):
            jamoset.unpack(edit(blanked, lambda b: b.compat.__setitem__(0, 0)))
        with self.assertRaisesRegex(ValueError, "set 32 is not below"):
            jamoset.unpack(edit(plain, lambda b: b.compat.__setitem__(0, 0x20)))
        # the bit 7 form on a lead-capable consonant is valid when the final slot is there
        self.assertEqual(jamoset.unpack(edit(plain, lambda b: b.compat.__setitem__(0, 0x81))).compat[0],
                         jamoset.unpack(good).fin_piece[27])

    def test_v1_still_read(self):
        t = self.t844()
        self.assertEqual(vars(jamoset.unpack(jamoset.pack_v1(t))), vars(t))

    def test_renumber_glyphs(self):
        P = jamoset.PIECE_BASE
        self.assertEqual(jamoset.renumber_glyphs({0x41: "a", P + 5: "b", P + 9: "c"}, {5: 0}),
                         {0x41: "a", P + 0: "b", P + 1: "c"})
        lst = [(P + 9, b"c", 8, 0, 8), (0x41, b"a", 8, 0, 8), (P + 5, b"b", 8, 0, 8), (P + 7, b"d", 8, 0, 8)]
        self.assertEqual(jamoset.renumber_glyphs(lst, {5: 0, 9: 1}),
                         [(P + 1, b"c", 8, 0, 8), (0x41, b"a", 8, 0, 8), (P + 0, b"b", 8, 0, 8), (P + 2, b"d", 8, 0, 8)])

    def test_face_with_aliases_survives_parse_svfn(self):
        packed = jamoset.pack(self.alias_table())
        self.assertGreater(jamoset.decode_jset2(packed.block).na, 0)
        glyphs = jamoset.renumber_glyphs([(jamoset.PIECE_BASE + p, bytes([p & 0xFF]) + bytes(7), 8, 0, 8)
                                          for p in sorted(packed.piece_map)], packed.piece_map)
        f = jamoset.parse_svfn(jamoset.write_svfn(8, 8, 7, glyphs, packed.block))
        self.assertFalse(f.jset_bad)
        self.assertEqual(f.jset, packed.block)


class TestJsetChoice(unittest.TestCase):
    """pack_jset / choose_jset_version: auto writes v2 when the v1 block is >= JSET_V2_MIN_SAVING bytes larger."""

    @staticmethod
    def t844():
        return jamoset.renumber(jamoset.tables_for(jamoset.LAYOUTS["844"]), {s: s for s in range(360)})

    @staticmethod
    def nsqrb16():
        with open(os.path.join(HERE, "testdata", "jset1", "NSQRB16.SVF"), "rb") as fh:
            return jamoset.unpack(jamoset.parse_svfn(fh.read()).jset)

    def test_constant(self):
        self.assertEqual(jamoset.JSET_V2_MIN_SAVING, 1024)

    def test_auto_threshold(self):
        t = self.t844()
        diff = len(jamoset.pack_v1(t)) - len(jamoset.pack(t).block)
        self.assertEqual(diff, 1101 - 272)
        # the constant read at call time: a difference equal to it picks 2, one byte short of it picks 1
        with mock.patch.object(jamoset, "JSET_V2_MIN_SAVING", diff):
            self.assertEqual(jamoset.choose_jset_version(t), 2)
            self.assertEqual(jamoset.pack_jset(t, "auto"), jamoset.pack(t))
        with mock.patch.object(jamoset, "JSET_V2_MIN_SAVING", diff + 1):
            self.assertEqual(jamoset.choose_jset_version(t), 1)
            self.assertEqual(jamoset.pack_jset(t, "auto").block, jamoset.pack_v1(t))

    def test_auto_844_and_12x12(self):
        for name in ("844", "844-ihnm", "844-hbios24"):
            self.assertEqual(jamoset.choose_jset_version(
                jamoset.renumber(jamoset.tables_for(jamoset.LAYOUTS[name]), {s: s for s in range(400)})), 1, name)
        t = self.nsqrb16()
        self.assertEqual((t.lc, t.tc, t.ni, t.nm, t.nf), (12, 12, 24, 16, 16))
        self.assertEqual(jamoset.choose_jset_version(t), 2)

    def test_auto_stays_v1_when_v2_refuses(self):
        # ruling T5-C1: a compat entry no set holds (R4) keeps the face v1 under auto, not a failure
        t = self.nsqrb16()
        self.assertEqual(jamoset.choose_jset_version(t), 2)
        t.compat[0] = 9999
        with self.assertRaisesRegex(ValueError, "no set holds piece"):
            jamoset.pack(t)
        self.assertEqual(jamoset.choose_jset_version(t), 1)
        self.assertEqual(jamoset.pack_jset(t, "auto").block, jamoset.pack_v1(t))

    def test_pack_jset_versions(self):
        t = self.t844()
        p1 = jamoset.pack_jset(t, 1)
        self.assertEqual(p1.block, jamoset.pack_v1(t))
        self.assertIsInstance(p1.piece_map, jamoset.IdentityMap)
        self.assertEqual((p1.piece_map[7], p1.piece_map.get(5000)), (7, 5000))
        glyphs = {jamoset.PIECE_BASE + 300: b"a", jamoset.PIECE_BASE + 2: b"b", 0x41: b"c"}
        self.assertEqual(jamoset.renumber_glyphs(glyphs, p1.piece_map), glyphs)
        self.assertEqual(jamoset.pack_jset(t, 2), jamoset.pack(t))
        for bad in (0, 3, "2", None):
            with self.assertRaisesRegex(ValueError, "is not 1, 2 or auto"):
                jamoset.pack_jset(t, bad)

    def test_explicit_v2_refusal_propagates(self):
        # v2 asked for explicitly still fails; auto falls back to v1 (T5-C1)
        t = self.t844()
        t.compat[30] = t.init_piece[0]          # U+314F names a piece no medial set holds
        jamoset.pack_v1(t)
        with self.assertRaisesRegex(ValueError, "compat U\\+314F"):
            jamoset.pack_jset(t, 2)
        self.assertEqual(jamoset.pack_jset(t, "auto").block, jamoset.pack_v1(t))


    def test_writers_choose(self):
        layout = jamoset.LAYOUTS["844"]
        data = make_source("844")
        out, mapping, _ = jamoset.build_from_source(layout, layout.opener(data, 0, ""))
        f1 = jamoset.parse_svfn(out)
        t1 = jamoset.unpack(f1.jset)
        self.assertEqual(f1.jset[4:6], b"\x01\x00")
        self.assertEqual(f1.jset, jamoset.pack_v1(t1))          # what the writer wrote before this task
        out2, _, _ = jamoset.build_from_source(layout, layout.opener(data, 0, ""), jset_version=2)
        f2 = jamoset.parse_svfn(out2)
        self.assertEqual((f2.jset[4:6], len(f2.jset)), (b"\x02\x00", 272))
        outa, _, _ = jamoset.build_from_source(layout, layout.opener(data, 0, ""), jset_version="auto")
        self.assertEqual(outa, out)
        t2 = jamoset.unpack(f2.jset)
        for cp in range(0xAC00, 0xD7A4, 53):
            self.assertEqual(jamoset.compose(f2, t2, cp), jamoset.compose(f1, t1, cp), hex(cp))
        # kyra-lok: version 2 numbers the pieces differently, so the glyphs must follow the piece map (T5-C2)
        kl = jamoset.LAYOUTS["kyra-lok"]
        ksrc = make_source("kyra-lok")
        k1, _, _ = jamoset.build_from_source(kl, kl.opener(ksrc, 0, ""))
        k2, _, _ = jamoset.build_from_source(kl, kl.opener(ksrc, 0, ""), jset_version=2)
        g1, g2 = jamoset.parse_svfn(k1), jamoset.parse_svfn(k2)
        self.assertEqual(g2.jset[4:6], b"\x02\x00")
        u1, u2 = jamoset.unpack(g1.jset), jamoset.unpack(g2.jset)
        self.assertTrue(g1.glyphs != g2.glyphs)
        for cp in range(0xAC00, 0xD7A4, 41):
            self.assertEqual(jamoset.compose(g2, u2, cp), jamoset.compose(g1, u1, cp), hex(cp))
        # blank_whole_compat keeps the input's version
        self.assertEqual(jamoset.parse_svfn(jamoset.blank_whole_compat(out)).jset[4:6], b"\x01\x00")
        self.assertEqual(jamoset.parse_svfn(jamoset.blank_whole_compat(out2)).jset[4:6], b"\x02\x00")
        self.assertEqual(jamoset.parse_svfn(jamoset.blank_whole_compat(out, jset_version=2)).jset[4:6], b"\x02\x00")
        # 844 at 16 x 16 checks in both versions
        src16 = make_source("844")
        for v in (1, 2):
            o, _, _ = jamoset.build_from_source(layout, layout.opener(src16, 0, ""), jset_version=v)
            jamoset.check(o, layout, src16)

    def test_blank_whole_compat_follows_the_piece_map(self):
        # v1 -> v2 -> v1 on kyra-lok (v2 numbers its pieces differently): composed pixels, glyphs and a dy on a piece
        # (written by write_svfn, which allows it; check_dy would refuse the face) must follow their piece
        kl = jamoset.LAYOUTS["kyra-lok"]
        k1, _, _ = jamoset.build_from_source(kl, kl.opener(make_source("kyra-lok"), 0, ""))
        f1 = jamoset.parse_svfn(k1)
        t1 = jamoset.unpack(f1.jset)
        pm = jamoset.pack(t1).piece_map
        moved = next(p for p in sorted(pm) if pm[p] != p and jamoset.PIECE_BASE + p in f1.glyphs)
        glyph = f1.glyphs[jamoset.PIECE_BASE + moved]
        self.assertEqual(sum(1 for cp, g in f1.glyphs.items() if cp >= jamoset.PIECE_BASE and g == glyph), 1)
        src = jamoset.write_svfn(f1.cell_w, f1.cell_h, f1.ascent,
                                 [(cp, g) + tuple(f1.metrics[cp]) for cp, g in sorted(f1.glyphs.items())], f1.jset,
                                 dy={jamoset.PIECE_BASE + moved: 2})

        def composed(data):
            f = jamoset.parse_svfn(data)
            t = jamoset.unpack(f.jset)
            return [jamoset.compose(f, t, cp) for cp in range(0xAC00, 0xD7A4, 19)]

        def dy_glyphs(data):
            f = jamoset.parse_svfn(data)
            return [f.glyphs[cp] for cp, d in f.dy.items() if d == 2 and cp >= jamoset.PIECE_BASE]

        v2 = jamoset.blank_whole_compat(src, jset_version=2)
        self.assertEqual(jamoset.parse_svfn(v2).jset[4:6], b"\x02\x00")
        self.assertEqual(composed(v2), composed(src))
        self.assertEqual(dy_glyphs(v2), [glyph])
        back = jamoset.blank_whole_compat(v2, jset_version=1)
        self.assertEqual(jamoset.parse_svfn(back).jset[4:6], b"\x01\x00")
        self.assertEqual(composed(back), composed(src))
        self.assertEqual(dy_glyphs(back), [glyph])

    def test_writers_cli(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "s.fnt")
            with open(src, "wb") as fh:
                fh.write(make_source("844"))
            base = [sys.executable, "-I", os.path.join(HERE, "jamoset.py"), "--layout", "844", src]
            r = subprocess.run(base + ["--jset-version", "3", "-o", os.path.join(d, "x.svf")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            for args, want, line in (([], b"\x01\x00", "jset=v1 v1=1101 v2=272"),
                                     (["--jset-version", "2"], b"\x02\x00", "jset=v2 v1=1101 v2=272"),
                                     (["--jset-version", "auto"], b"\x01\x00", "jset=v1 v1=1101 v2=272")):
                op = os.path.join(d, "o.svf")
                r = subprocess.run(base + args + ["--check", "-o", op], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn(line, r.stdout)
                with open(op, "rb") as fh:
                    self.assertEqual(jamoset.parse_svfn(fh.read()).jset[4:6], want)


class ReviewFixes(unittest.TestCase):
    def test_ihnm_accepts_trailing_glyphs_and_reads_the_first_360(self):
        # SOL-1: the IHNM file is the 360 jamo glyphs and then other glyphs; only the jamo are read.
        layout = jamoset.LAYOUTS["844-ihnm"]
        base = make_source("844")
        data = base + random.Random(9).randbytes(126 * 32)
        self.assertEqual(len(data), 15552)
        out, mapping, src = jamoset.build(layout, data)
        out0, _, _ = jamoset.build(layout, base)
        self.assertEqual(out, out0)
        with self.assertRaises(jamoset.SourceError):
            layout.opener(base[:-1], 0, "")
        # the plain 8x4x4 layout keeps its exact-size whitelist
        with self.assertRaises(jamoset.SourceError):
            jamoset.LAYOUTS["844"].opener(data, 0, "")

    def test_base_keeps_the_marks_at_origin_flag(self):
        # SOL-2: flag bit 2 of the base survives, with the negative-bearing mark it governs.
        mark = (0x0301, bytes([0x0F] * 32), 0, -3, 4)
        for flags, want in ((1 | 4, 7), (1, 3)):
            base = bytearray(jamoset.write_svfn(16, 16, 14, [mark], b""))
            struct.pack_into("<H", base, 6, flags)
            out, _, _ = jamoset.build(jamoset.LAYOUTS["844"], make_source("844"), base=bytes(base))
            f = jamoset.parse_svfn(out)
            self.assertEqual(f.flags, want)
            self.assertEqual(f.metrics[0x0301], (0, -3, 4))
            self.assertEqual(f.glyphs[0x0301], bytes([0x0F] * 32))

    def test_bdf_without_a_required_encoding_is_refused(self):
        text = make_bdf().decode("latin-1")
        cut = text.replace("ENCODING 311\n", "ENCODING 9999\n")
        self.assertNotEqual(cut, text)
        with self.assertRaises(jamoset.SourceError) as cm:
            jamoset.open_bdf_glyphs(cut.encode("latin-1"))
        self.assertIn("311", str(cm.exception))
        nolines = text.replace("ENCODING 311\n", "")
        with self.assertRaises(jamoset.SourceError):
            jamoset.open_bdf_glyphs(nolines.encode("latin-1"))

    def test_bdf_with_a_truncated_bitmap_is_refused(self):
        text = make_bdf().decode("latin-1")
        start = text.index("ENCODING 311\n")
        bm = text.index("BITMAP\n", start) + 7
        first_row_end = text.index("\n", bm) + 1
        cut = text[:first_row_end] + text[text.index("ENDCHAR", start):]
        with self.assertRaises(jamoset.SourceError) as cm:
            jamoset.open_bdf_glyphs(cut.encode("latin-1"))
        self.assertIn("311", str(cm.exception))

    def test_an_explicitly_present_blank_glyph_stays_valid(self):
        src = jamoset.open_bdf_glyphs(make_bdf())
        self.assertEqual(src.glyph(0).rows, [0] * 16)
        self.assertEqual(src.count, 529)

    def test_hanterm_final_variant_of_wae_oe_we_ui_follows_hantermS_lcon_map(self):
        # hanterm's lcon_map[] (hfont.c convert_3_to_johabfont): wae 0, oe 0, we 1, ui 0 - not the 8x4x4 table
        t = jamoset.tables_for(jamoset.LAYOUTS["hanterm-johab"])
        def fin(L, V, T):
            return jamoset.pieces_of(t, 0xAC00 + (L * 21 + V) * 28 + T)[2]
        # gwaen (L0 wae V10 T4 nieun), goen (V11), gwen (V15), gui (V19): final glyph 405 + 4*(T-1) + variant
        self.assertEqual(fin(0, 10, 4), 405 + 12 + 0)
        self.assertEqual(fin(0, 11, 4), 405 + 12 + 0)
        self.assertEqual(fin(0, 15, 4), 405 + 12 + 1)
        self.assertEqual(fin(0, 19, 4), 405 + 12 + 0)

    def test_hanterm_literal_lcon_map(self):
        self.assertEqual(jamoset.HT_LMAP, (0, 0, 0, 0, 2, 0, 2, 1, 0, 0, 2, 1, 2, 3, 0, 0, 0, 0, 0, 3, 3, 1, 1, 1,
                                           0, 0, 3, 3, 0, 1))

    def test_all_11172_syllables_equal_a_straight_port_of_hanterm_c(self):
        t = jamoset.tables_for(jamoset.LAYOUTS["hanterm-johab"])
        for cp in range(0xAC00, 0xD7A4):
            self.assertEqual(jamoset.pieces_of(t, cp), hanterm_c_glyphs(cp), f"U+{cp:04X}")

    def test_composed_pixels_of_a_real_hanterm_font_equal_the_port(self):
        path = HANTERM_BDF
        if not os.path.exists(path):
            self.skipTest("johabm16.bdf not collected here")
        with open(path, "rb") as fh:
            data = fh.read()
        layout = jamoset.LAYOUTS["hanterm-johab"]
        src = layout.opener(data, 0, "")
        out, _, _ = jamoset.build(layout, data)
        f = jamoset.parse_svfn(out)
        t = jamoset.unpack(f.jset)
        for cp in range(0xAC00, 0xD7A4):
            want = bytearray(((src.w + 7) // 8) * src.h)
            for n in hanterm_c_glyphs(cp):
                for k, b in enumerate(src.glyph(n).to_bytes()):
                    want[k] |= b
            self.assertEqual(jamoset.compose(f, t, cp), bytes(want), f"U+{cp:04X}")


class CommandLine(unittest.TestCase):
    def run_tool(self, *args):
        return subprocess.run([sys.executable, "-I", os.path.join(HERE, "jamoset.py")] + list(args),
                              capture_output=True, text=True)

    def test_build_and_check(self):
        with tempfile.TemporaryDirectory() as d:
            src, eng, out = (os.path.join(d, n) for n in ("GAM.KOR", "SAN.ENG", "OUT.SVF"))
            open(src, "wb").write(make_source("844"))
            open(eng, "wb").write(bytes(4096))
            r = self.run_tool("--layout", "844", src, "--eng", eng, "-o", out, "--check")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("identical to johab844.py", r.stdout)
            self.assertIn("344 pieces", r.stdout)
            self.assertTrue(os.path.getsize(out) < 24000)

    def test_wrong_file_exits_with_a_message(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "X.KOR")
            open(src, "wb").write(b"\0" * 100)
            r = self.run_tool("--layout", "844", src, "-o", os.path.join(d, "o.svf"))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("not an 8x4x4 size", r.stderr)


# ---- fitting pieces to precomposed faces (jamofit.py, --from-svf / --from-ttf) -------------------------------------

import jamofit  # noqa: E402

NOTO = jamoset.default_mask_font()
LIBS = jamofit.libs_available()
PYLIB = []
if LIBS:		# the tool runs under python -I, which ignores PYTHONPATH: hand it the directory
    import freetype
    PYLIB = ["--pylib", os.path.dirname(os.path.dirname(os.path.abspath(freetype.__file__)))]


def ks2350():
    out = []
    for hi in range(0xB0, 0xC9):
        for lo in range(0xA1, 0xFF):
            out.append(ord(bytes([hi, lo]).decode("cp949")) - 0xAC00)
    return sorted(out)


def region_source(seed=3, cell=16):
    """A raw 8x4x4 source whose pieces keep to separate regions (initial top left, medial right, final bottom), every
    piece with its own random pixels, so some zero-error decomposition of the OR of any three exists."""
    rnd = random.Random(seed)
    assert cell == 16
    data = bytearray(360 * 32)
    for i in range(360):
        if i < 160:
            if i % 20 == 0:
                continue
            xs, ys = range(0, 9), range(0, 10)
        elif i < 248:
            if (i - 160) % 22 == 0:
                continue
            xs, ys = range(9, 16), range(0, 11)
        else:
            if (i - 248) % 28 == 0:
                continue
            xs, ys = range(0, 16), range(11, 16)
        for y in ys:
            row = 0
            for x in xs:
                if rnd.random() < 0.4:
                    row |= 0x8000 >> x
            data[i * 32 + y * 2:i * 32 + y * 2 + 2] = row.to_bytes(2, "big")
    return bytes(data)


ASCII_METRICS = {cp: (8 + cp % 3, cp % 2, 5 + cp % 4) for cp in range(0x20, 0x7F)}


def make_face(syllables, w=16, h=16, ascent=12, flags=5, seed=9):
    """A plain 1 bpp SVFN v3 face (default profile): ASCII with random glyphs and metrics, @p syllables {index: packed
    glyph}, one compatibility jamo. Returns (bytes, {cp: glyph bytes})."""
    rnd = random.Random(seed)
    nb = (w + 7) // 8
    glyphs = {cp: rnd.randbytes(nb * h) for cp in ASCII_METRICS}
    glyphs[0x3131] = rnd.randbytes(nb * h)
    for s, g in syllables.items():
        glyphs[0xAC00 + s] = g
    cps = sorted(glyphs)
    metrics = [(*ASCII_METRICS.get(cp, (w, 0, w)), 0) for cp in cps]
    out = jamoset.pack_svfn(w, h, ascent, 1, flags, [glyphs[cp] for cp in cps], [(cp, i) for i, cp in enumerate(cps)],
                            metrics, None, (0, 0), "default")
    return out, glyphs


def composed_face(present, blank=(), seed=3):
    """(face bytes, source bytes, {syllable: target glyph}) of the 844 pieces of region_source over @p present."""
    src = region_source(seed)
    target = {s: (bytes(32) if s in blank else johab844.compose(src, 0xAC00 + s)) for s in present}
    face, _ = make_face(target)
    return face, src, target


class FitFromFace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.present = ks2350()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = cls.tmp.name
        cls.face, cls.src, cls.target = composed_face(cls.present)
        cls.path = os.path.join(cls.dir, "FACE.SVF")
        open(cls.path, "wb").write(cls.face)
        cls.out = os.path.join(cls.dir, "OUT.SVF")
        cls.r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "jamoset.py"), "--layout", "844",
                                "--from-svf", cls.path, "--mask", "none", "-o", cls.out, "--check",
                                "--report", os.path.join(cls.dir, "r.json")], capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_ran(self):
        self.assertEqual(self.r.returncode, 0, self.r.stderr)
        self.assertIn("composed 11172 syllables", self.r.stdout)

    def test_composition_equals_the_target_for_every_present_syllable(self):
        out = open(self.out, "rb").read()
        f = jamoset.parse_svfn(out)
        t = jamoset.unpack(f.jset)
        for s in self.present:
            self.assertEqual(jamoset.compose(f, t, 0xAC00 + s), self.target[s], f"U+{0xAC00 + s:04X}")

    def test_report_is_perfect(self):
        import json
        q = json.load(open(os.path.join(self.dir, "r.json")))["quality"]
        self.assertEqual(q["present"], 2350)
        self.assertEqual((q["iou_mean"], q["iou_p5"], q["f1_tol1_mean"], q["exact"]), (1.0, 1.0, 1.0, 2350))
        self.assertEqual((q["blob_merged"], q["blob_split"]), (0, 0))
        self.assertIn("IoU 1.000", self.r.stdout)

    def test_parses_back_as_a_jamo_set_font(self):
        f = jamoset.parse_svfn(open(self.out, "rb").read())
        self.assertTrue(f.flags & jamoset.FLAG_JAMO)
        t = jamoset.unpack(f.jset)
        self.assertEqual((t.lc, t.tc, t.ni, t.nm, t.nf), (2, 2, 8, 4, 4))
        self.assertTrue(all(0xAC00 + s not in f.glyphs for s in self.present))
        self.assertTrue(any(cp >= jamoset.PIECE_BASE for cp in f.glyphs))

    def test_keeps_non_hangul_glyphs_cell_baseline_metrics_and_flags(self):
        _, want = make_face({})
        f = jamoset.parse_svfn(open(self.out, "rb").read())
        for cp, g in want.items():
            self.assertEqual(f.glyphs[cp], g, f"U+{cp:04X}")
        for cp, m in ASCII_METRICS.items():
            self.assertEqual(f.metrics[cp], m, f"U+{cp:04X}")
        self.assertEqual((f.cell_w, f.cell_h, f.ascent, f.bpp), (16, 16, 12, 1))
        self.assertEqual((f.version, f.flags & ~jamoset.FLAG_JAMO), (3, 5))
        self.assertTrue(f.flags & jamoset.FLAG_JAMO)

    def test_deterministic(self):
        out2 = os.path.join(self.dir, "OUT2.SVF")
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "jamoset.py"), "--layout", "844", "--from-svf",
                            self.path, "--mask", "none", "-o", out2], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(open(out2, "rb").read(), open(self.out, "rb").read())


class FitPresentOnly(unittest.TestCase):
    def test_blank_syllables_do_not_pull_pieces_toward_empty(self):
        present = ks2350()
        rnd = random.Random(11)
        blank = set(rnd.sample(present, 1600))		# 68 % blank: every pixel's majority would be off
        face, src, target = composed_face(present, blank)
        layout = jamoset.LAYOUTS["844"]
        targets = jamoset.svf_targets(jamoset.parse_svfn(face))
        self.assertEqual(sorted(targets), sorted(set(present) - blank))
        out, info = jamoset.fit_font(layout, targets, 16, 16, 12, base=face, keep_header=True)
        f = jamoset.parse_svfn(out)
        t = jamoset.unpack(f.jset)
        for s in targets:
            self.assertEqual(jamoset.compose(f, t, 0xAC00 + s), target[s], f"U+{0xAC00 + s:04X}")
        q = jamoset.fit_report(out, targets, 16, 16)
        self.assertEqual((q["present"], q["iou_mean"]), (750, 1.0))

    def test_unseen_pieces_borrow_a_sibling_not_blank(self):
        present = ks2350()[:600]
        face, src, target = composed_face(present)
        targets = jamoset.svf_targets(jamoset.parse_svfn(face))
        out, info = jamoset.fit_font(jamoset.LAYOUTS["844"], targets, 16, 16, 12, base=face, keep_header=True)
        self.assertGreater(info["unseen_pieces"]["sibling"], 0)
        f = jamoset.parse_svfn(out)
        t = jamoset.unpack(f.jset)
        seen = [set(), set(), set()]
        for s in present:
            for k, v in enumerate(jamoset.decompose(0xAC00 + s)):
                seen[k].add(v)
        checked = 0
        for cp in range(0xAC00, 0xD7A4):		# a syllable made of jamo the face draws never loses a piece
            if all(v in seen[k] for k, v in enumerate(jamoset.decompose(cp))):
                checked += 1
                for p in jamoset.pieces_of(t, cp):
                    self.assertTrue(any(f.glyphs[jamoset.PIECE_BASE + p]), f"U+{cp:04X} piece {p}")
        self.assertGreater(checked, 1000)


class SyllableAdvance(unittest.TestCase):
    """--from-svf keeps the step of the face's syllables (a 16 px glyph in a 26 px cell steps 16, and the engine
    centres what steps less than the game cell); without metrics the JSET advance stays 0, the cell width."""

    def face(self, advance, w=24):
        present = ks2350()[:30]
        glyphs = {s: bytes([0xFF] * (((w + 7) // 8) * 16)) for s in present}
        out, _ = make_face(glyphs, w=w)
        f = jamoset.parse_svfn(out)
        # one more syllable at the odd step, the rest at @p advance
        for cp in f.glyphs:
            if 0xAC00 <= cp <= 0xD7A3:
                f.metrics[cp] = (advance, 1, advance - 2)
        f.metrics[0xAC00 + present[0]] = (advance + 4, 0, 4)
        return f

    def test_modal_advance_of_the_drawn_syllables(self):
        self.assertEqual(jamoset.svf_advance(self.face(16)), 16)

    def test_no_metrics_or_too_wide_gives_none(self):
        f = self.face(16)
        f.metrics = {}
        self.assertIsNone(jamoset.svf_advance(f))
        self.assertIsNone(jamoset.svf_advance(self.face(300)))

    def test_written_into_the_jset_block(self):
        present = ks2350()
        face, _, _ = composed_face(present)
        targets = jamoset.svf_targets(jamoset.parse_svfn(face))
        out, _ = jamoset.fit_font(jamoset.LAYOUTS["844"], targets, 16, 16, 12, base=face, keep_header=True, advance=12)
        self.assertEqual(unpack_advance(out), 12)
        out, _ = jamoset.fit_font(jamoset.LAYOUTS["844"], targets, 16, 16, 12, base=face, keep_header=True)
        self.assertEqual(unpack_advance(out), 0)


class Metrics(unittest.TestCase):
    W = H = 8

    def g(self, *rows):
        return jamofit.from_rows([int(r, 2) for r in rows] + [0] * (self.H - len(rows)), self.W)

    def test_rows_round_trip(self):
        g = self.g("10000001", "01100110", "00000001")
        self.assertEqual(jamofit.to_rows(g, 8, 8)[:3], [0x81, 0x66, 0x01])
        self.assertEqual(g & 1, 1)				# top left pixel is bit 0

    def test_components_are_eight_connected(self):
        full = jamofit.full_mask(8, 8)
        self.assertEqual(jamofit.components(self.g("11000000", "00110000", "00001100"), 8, full), 1)
        self.assertEqual(jamofit.components(self.g("10000001", "00000000", "10000001"), 8, full), 4)
        self.assertEqual(jamofit.components(0, 8, full), 0)
        self.assertEqual(jamofit.components(self.g("10000001"), 8, full), 2)	# no wrap from the last column to the next row

    def test_iou_and_f1(self):
        full = jamofit.full_mask(8, 8)
        a, b = self.g("11110000"), self.g("00111100")
        self.assertAlmostEqual(jamofit.iou(a, b), 2 / 6)
        self.assertEqual(jamofit.iou(0, 0), 1.0)
        self.assertEqual(jamofit.f1_tol1(a, a, 8, full), 1.0)
        shifted = self.g("01111000")
        self.assertEqual(jamofit.f1_tol1(a, shifted, 8, full), 1.0)		# one pixel off is within tolerance
        self.assertLess(jamofit.f1_tol1(a, self.g("00000000", "00000000", "11110000"), 8, full), 1.0)

    def test_blob_metric_counts_merged_strokes(self):
        two = self.g("10001000", "10001000")
        one = self.g("11111000", "10001000")
        same = self.g("10001000", "10001000")
        q = jamofit.quality_report({0: two, 1: two, 2: one}, {0: one, 1: same, 2: one}, 8, 8)
        self.assertEqual((q["blob_merged"], q["blob_split"], q["present"]), (1, 0, 3))
        q = jamofit.quality_report({0: one}, {0: two}, 8, 8)
        self.assertEqual((q["blob_merged"], q["blob_split"]), (0, 1))

    def test_percentile(self):
        self.assertEqual(jamofit.percentile([1, 2, 3, 4, 5], 50), 3)
        self.assertAlmostEqual(jamofit.percentile(list(range(101)), 5), 5)


class FitErrors(unittest.TestCase):
    def run_tool(self, *args, env=None):
        e = dict(os.environ)
        e.pop("JAMOSET_PYLIB", None)
        e.update(env or {})
        return subprocess.run([sys.executable, "-I", os.path.join(HERE, "jamoset.py")] + list(args),
                              capture_output=True, text=True, env=e)

    def test_one_mode_only(self):
        r = self.run_tool("--layout", "844", "-o", "/dev/null")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("exactly one", r.stderr)

    def test_already_jamo_set_face_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "G.KOR"), os.path.join(d, "J.SVF")
            open(src, "wb").write(make_source("844"))
            self.assertEqual(self.run_tool("--layout", "844", src, "-o", out).returncode, 0)
            r = self.run_tool("--layout", "844", "--from-svf", out, "--mask", "none", "-o", os.path.join(d, "x.svf"))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("already a jamo-set", r.stderr)

    @unittest.skipIf(LIBS, "freetype and uharfbuzz are importable here")
    def test_missing_libraries_say_what_to_install(self):
        r = self.run_tool("--layout", "844", "--from-ttf", "/nonexistent.ttf", "--size", "16", "-o", "/dev/null")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("pip install freetype-py uharfbuzz", r.stderr)
        self.assertIn("JAMOSET_PYLIB", r.stderr)


@unittest.skipUnless(LIBS and NOTO, "needs freetype-py, uharfbuzz and the NotoSansKR mask font")
class FitFromOutlineFont(unittest.TestCase):
    def test_from_ttf_with_noto_masks(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            out, rep = os.path.join(d, "N.SVF"), os.path.join(d, "r.json")
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "jamoset.py"), "--layout", "844",
                                "--from-ttf", NOTO, "--size", "16", "--present-only", "-o", out, "--check",
                                "--report", rep] + PYLIB, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            f = jamoset.parse_svfn(open(out, "rb").read())
            self.assertTrue(f.flags & jamoset.FLAG_JAMO)
            self.assertEqual((f.cell_w, f.cell_h), (16, 16))
            self.assertIn(0x41, f.glyphs)					# ASCII from the font
            q = json.load(open(rep))
            self.assertGreater(q["quality"]["present"], 11000)
            self.assertGreater(q["quality"]["f1_tol1_mean"], 0.9)
            self.assertEqual(q["mask_font"], os.path.basename(NOTO))

    def test_present_only_skips_notdef(self):
        jf = jamoset._jamofit()
        # Noto has all syllables, so a font with none of them (U+AC00 range empty) is simulated by the flag alone
        targets, w, h, ascent, info, _ = jamoset.ttf_targets(NOTO, 16, None, None, True)
        self.assertEqual(len(targets), info["fitted"])
        self.assertTrue(all(targets.values()))


class DosFace24(unittest.TestCase):
    """The HBIOS 24x30 jamo half, the 12x24 ASCII faces, --advance/--ascent/--embolden/--symbols."""

    @staticmethod
    def hbios(seed=3):
        """243,900 bytes: 2,710 glyphs of 90 bytes; the first 360 an 8x4x4 set (ink in rows 3-26), blank slots blank."""
        rnd = random.Random(seed)
        data = bytearray(90 * 2710)
        for i in range(360):
            if i in [s * 20 for s in range(8)] + [160 + s * 22 for s in range(4)] + [248 + s * 28 for s in range(4)]:
                continue
            for y in range(3, 27):
                data[i * 90 + y * 3:i * 90 + y * 3 + 3] = rnd.randbytes(3)
        return bytes(data)

    def test_hbios_pieces_are_the_cropped_rows(self):
        data = self.hbios()
        src = jamoset.open_hbios24(data)
        self.assertEqual((src.w, src.h, src.count), (24, 24, 360))
        g = src.glyph(1)
        self.assertEqual(g.rows[0], int.from_bytes(data[90 + 9:90 + 12], "big"))		# file row 3 is cell row 0
        self.assertEqual(g.rows[23], int.from_bytes(data[90 + 26 * 3:90 + 27 * 3], "big"))

    def test_hbios_refuses_other_sizes(self):
        with self.assertRaises(jamoset.SourceError):
            jamoset.open_hbios24(bytes(243899))

    def test_layout_composes_like_844(self):
        data = self.hbios()
        out, _, _ = jamoset.build_from_source(jamoset.LAYOUTS["844-hbios24"], jamoset.open_hbios24(data))
        f = jamoset.parse_svfn(out)
        t = jamoset.unpack(f.jset)
        ref = jamoset.LAYOUTS["844"]
        self.assertEqual(jamoset.tables_for(jamoset.LAYOUTS["844-hbios24"]).init_set, jamoset.tables_for(ref).init_set)
        self.assertEqual(len(jamoset.compose(f, t, 0xD55C)), 72)

    def test_12x24_eng_faces(self):
        pft = bytearray(12288)
        pft[ord("H") * 48 + 2 * 20] = 0xFF		# row 20, columns 0-7 (12 wide, left aligned in 2 bytes)
        e = jamoset.read_eng(bytes(pft))
        self.assertEqual((e.w, e.h, e.adv, e.baseline), (16, 24, 12, 21))		# 16 bit rows, steps 12
        hb = bytearray(15360)
        hb[ord("H") * 60 + (3 + 5) * 2] = 0xFF		# cell row 5 (file row 8) of a 16x30 cell
        e = jamoset.read_eng(bytes(hb))
        self.assertEqual(e.baseline, 6)
        self.assertEqual(e.glyph(ord("H"))[5], 0xFF00)

    def test_eng_goes_at_the_left_steps_12_and_sets_the_ascent(self):
        pft = bytearray(12288)
        pft[ord("A") * 48 + 2 * 20] = 0xC0
        pft[ord("H") * 48 + 2 * 20] = 0xC0
        e = jamoset.read_eng(bytes(pft))
        out, _, _ = jamoset.build_from_source(jamoset.LAYOUTS["844-hbios24"], jamoset.open_hbios24(self.hbios()), e,
                                              advance=24)
        f = jamoset.parse_svfn(out)
        self.assertEqual(f.ascent, 21)
        self.assertEqual(f.metrics[ord("A")][0], 12)
        self.assertEqual(jamoset.unpack(f.jset).advance, 24)
        nb = 3
        row = int.from_bytes(f.glyphs[ord("A")][20 * nb:21 * nb], "big")
        self.assertEqual(row, 0xC00 << 12)

    def test_embolden_ors_each_piece_and_ascii_with_itself_shifted_right(self):
        data = self.hbios()
        plain = jamoset.build_from_source(jamoset.LAYOUTS["844-hbios24"], jamoset.open_hbios24(data))[0]
        bold = jamoset.build_from_source(jamoset.LAYOUTS["844-hbios24"], jamoset.open_hbios24(data), bold=True)[0]
        a, b = jamoset.parse_svfn(plain), jamoset.parse_svfn(bold)
        n = jamoset.PIECE_BASE + 5
        pa = int.from_bytes(a.glyphs[n][:3], "big")
        self.assertEqual(int.from_bytes(b.glyphs[n][:3], "big"), pa | (pa >> 1))

    def test_symbols_are_drawn_unless_the_base_has_them(self):
        out, _, _ = jamoset.build_from_source(jamoset.LAYOUTS["844-hbios24"], jamoset.open_hbios24(self.hbios()),
                                              ascent=21, symbols=True)
        f = jamoset.parse_svfn(out)
        rows = [int.from_bytes(f.glyphs[0x2026][y * 3:y * 3 + 3], "big") for y in range(24)]
        self.assertEqual([y for y, r in enumerate(rows) if r], [18, 19, 20])
        self.assertIn(0x25A1, f.glyphs)

    def test_command_line(self):
        with tempfile.TemporaryDirectory() as d:
            src, eng, out = (os.path.join(d, n) for n in ("GOTHIC24.FNT", "GASCII24.PFT", "O.SVF"))
            pft = bytearray(12288)
            pft[ord("H") * 48 + 40] = 0xFF
            for path, blob in ((src, self.hbios()), (eng, bytes(pft))):
                with open(path, "wb") as fh:
                    fh.write(blob)
            r = subprocess.run([sys.executable, os.path.join(HERE, "jamoset.py"), "--layout", "844-hbios24", src, "--eng",
                                eng, "--advance", "24", "--symbols", "--embolden", "--check", "-o", out],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("composed 11172", r.stdout)
            with open(out, "rb") as fh:
                self.assertEqual(jamoset.parse_svfn(fh.read()).ascent, 21)


class FakeOutline:
    """Stands in for jamofit.OutlineFont (no FreeType needed): a font that draws every 100th syllable and ASCII, and a box for
    .notdef (gid 0), so a fit that includes .notdef targets shows up as 11,172 targets instead of 112."""

    def __init__(self, path, px, pylib=None):
        self.px = px

    @staticmethod
    def drawn(cp):
        return 0x20 <= cp < 0x7F or (0xAC00 <= cp <= 0xD7A3 and (cp - 0xAC00) % 100 == 0)

    def gid(self, cp):
        return cp if self.drawn(cp) else 0

    def raw(self, gid, dx=0.0, dy=0.0):
        if gid == 0:
            return [0xFF] * 10, 8, 1, 12
        return [((gid * 2654435761 >> r) & 0xFF) | 0x18 for r in range(10)], 8, 1, 12

    def advance(self, gid):
        return 8.0


def run_main(argv):
    """jamoset.main() in this process with FakeOutline in place of FreeType; returns (exit code or None, stdout)."""
    import contextlib
    import io
    jf = jamoset._jamofit()
    old_argv, old_font = sys.argv, jf.OutlineFont
    sys.argv, jf.OutlineFont = ["jamoset.py"] + argv, FakeOutline
    out = io.StringIO()
    code = None
    try:
        with contextlib.redirect_stdout(out):
            jamoset.main()
    except SystemExit as e:
        code = e.code
    finally:
        sys.argv, jf.OutlineFont = old_argv, old_font
    return code, out.getvalue()


def whole_glyph_face(layout_name="844", cps=(0x3131, 0x3134)):
    """(plain jamo-set face, the same with a whole glyph for each of @p cps added behind the tool's back, the source): the
    second is what the tool wrote before compat jamo the base has were left to the base."""
    layout = jamoset.LAYOUTS[layout_name]
    src = region_source()
    plain = jamoset.build_from_source(layout, layout.opener(src, 0, ""))[0]
    f = jamoset.parse_svfn(plain)
    glyphs = [(cp, f.glyphs[cp], *f.metrics[cp]) if cp in f.metrics else (cp, f.glyphs[cp], 16, 0, 16) for cp in f.glyphs]
    for k, cp in enumerate(cps):
        glyphs.append((cp, bytes([k + 1]) * 32, 16, 0, 16))
    old = jamoset.write_svfn(f.cell_w, f.cell_h, f.ascent, glyphs, f.jset, f.flags & 4)
    return plain, old, src


class WholeCompatJamo(unittest.TestCase):
    """A compat jamo the base face draws whole must not also map to pieces: the engine looks at the piece table first."""

    def test_base_glyph_blanks_the_compat_piece(self):
        layout = jamoset.LAYOUTS["844"]
        face, _ = make_face({})		# has U+3131 as a whole glyph
        out = jamoset.build_from_source(layout, layout.opener(region_source(), 0, ""), base=face)[0]
        t = jamoset.unpack(jamoset.parse_svfn(out).jset)
        self.assertEqual(t.compat[0], jamoset.BLANK)			# U+3131 is the base's
        self.assertNotEqual(t.compat[1], jamoset.BLANK)			# U+3132 still comes from pieces
        self.assertIn(0x3131, jamoset.parse_svfn(out).glyphs)
        self.assertEqual(jamoset.parse_svfn(out).glyphs[0x3131], jamoset.parse_svfn(face).glyphs[0x3131])

    def test_a_blank_base_glyph_does_not_count(self):
        layout = jamoset.LAYOUTS["844"]
        face, _ = make_face({})
        f = jamoset.parse_svfn(face)
        glyphs = [(cp, bytes(32) if cp == 0x3131 else g, *f.metrics[cp]) for cp, g in f.glyphs.items()]
        blank = jamoset.write_svfn(16, 16, 12, glyphs, b"", 0)
        # write_svfn of a jamo-less face: build the base by hand through the flag-free path
        out = jamoset.build_from_source(layout, layout.opener(region_source(), 0, ""), base=blank)[0]
        t = jamoset.unpack(jamoset.parse_svfn(out).jset)
        self.assertNotEqual(t.compat[0], jamoset.BLANK)

    def test_no_piece_glyph_is_left_unreferenced(self):
        layout = jamoset.LAYOUTS["844"]
        face, _ = make_face({})
        f = jamoset.parse_svfn(jamoset.build_from_source(layout, layout.opener(region_source(), 0, ""), base=face)[0])
        t = jamoset.unpack(f.jset)
        used = {jamoset.PIECE_BASE + p for lst in (t.init_piece, t.med_piece, t.fin_piece, t.compat) for p in lst
                if p != jamoset.BLANK}
        used |= {jamoset.PIECE_BASE + p for cp in range(0xAC00, 0xD7A4) for p in jamoset.pieces_of(t, cp)
                 if p != jamoset.BLANK}
        self.assertEqual({cp for cp in f.glyphs if cp >= jamoset.PIECE_BASE}, used)

    def test_blank_whole_compat_repairs_an_old_face(self):
        plain, old, src = whole_glyph_face()
        before = jamoset.unpack(jamoset.parse_svfn(old).jset)
        self.assertNotEqual(before.compat[0], jamoset.BLANK)
        fixed = jamoset.blank_whole_compat(old)
        f = jamoset.parse_svfn(fixed)
        t = jamoset.unpack(f.jset)
        self.assertEqual((t.compat[0], t.compat[3]), (jamoset.BLANK, jamoset.BLANK))	# U+3131, U+3134
        self.assertEqual(t.compat[1:3] + t.compat[4:], before.compat[1:3] + before.compat[4:])
        self.assertEqual(f.glyphs[0x3131], bytes([1]) * 32)
        o = jamoset.parse_svfn(old)
        for cp in range(0xAC00, 0xD7A4):		# syllables compose as before
            self.assertEqual(jamoset.compose(f, t, cp), jamoset.compose(o, before, cp))
        self.assertEqual((f.cell_w, f.cell_h, f.ascent, f.flags), (o.cell_w, o.cell_h, o.ascent, o.flags))
        self.assertEqual(jamoset.blank_whole_compat(fixed), fixed)		# idempotent

    def test_blank_whole_compat_command(self):
        plain, old, src = whole_glyph_face()
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "A.SVF"), os.path.join(d, "B.SVF")
            open(a, "wb").write(old)
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "jamoset.py"), "--layout", "844",
                                "--blank-compat", a, "-o", b], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(open(b, "rb").read(), jamoset.blank_whole_compat(old))


class WholeCompatFromSvf(unittest.TestCase):
    def test_from_svf_leaves_compat_jamo_the_face_has_to_the_face(self):
        with tempfile.TemporaryDirectory() as d:
            face, _, _ = composed_face(ks2350())
            a, b = os.path.join(d, "F.SVF"), os.path.join(d, "O.SVF")
            open(a, "wb").write(face)
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "jamoset.py"), "--layout", "844", "--from-svf", a,
                                "--mask", "none", "-o", b], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            t = jamoset.unpack(jamoset.parse_svfn(open(b, "rb").read()).jset)
            self.assertEqual(t.compat[0], jamoset.BLANK)			# make_face draws U+3131 whole
            self.assertNotEqual(t.compat[1], jamoset.BLANK)


class Eng40x48(unittest.TestCase):
    """Taebaek 3.5.1 GASCII40 / GASCII48 .PFT: 256 glyphs, 40 rows x 3 bytes (20 px ink) / 48 rows x 4 bytes (24 px ink)."""

    def test_40_reads_and_steps_20(self):
        pft = bytearray(30720)
        pft[ord("H") * 120 + 3 * 33] = 0x1F		# row 33 (the baseline row), columns 3-7
        pft[ord("H") * 120 + 3 * 33 + 2] = 0x01		# column 23
        e = jamoset.read_eng(bytes(pft))
        self.assertEqual((e.w, e.h, e.adv, e.baseline), (24, 40, 20, 34))
        self.assertEqual(e.glyph(ord("H"))[33], 0x1F0001)

    def test_48_reads_and_steps_24(self):
        pft = bytearray(49152)
        pft[ord("H") * 192 + 4 * 40] = 0x30
        pft[ord("H") * 192 + 4 * 40 + 3] = 0x01
        e = jamoset.read_eng(bytes(pft))
        self.assertEqual((e.w, e.h, e.adv, e.baseline), (32, 48, 24, 41))
        self.assertEqual(e.glyph(ord("H"))[40], 0x30000001)

    def test_glyph_in_a_40_cell_keeps_rows_and_steps_20(self):
        pft = bytearray(30720)
        pft[ord("H") * 120 + 3 * 33] = 0x1F
        e = jamoset.read_eng(bytes(pft))
        g, adv = jamoset.eng_glyph(e, ord("H"), 40, 40)
        self.assertEqual(adv, 20)
        self.assertEqual(g.rows[33], 0x1F << 32)		# 24 bit file row at the left of a 40 bit cell

    def test_other_sizes_still_refused(self):
        with self.assertRaises(jamoset.SourceError):
            jamoset.read_eng(bytes(30000))


class Eng12x24(unittest.TestCase):
    """The 12x24 faces' 16 bit rows: MASCII24's right serifs sit in columns 12-15 and must survive; the step stays 12."""

    def pft(self):
        pft = bytearray(12288)
        pft[ord("H") * 48 + 2 * 20] = 0x80			# row 20, column 0 (the baseline row)
        pft[ord("H") * 48 + 2 * 20 + 1] = 0x08		# row 20, column 12: a right serif
        pft[ord("I") * 48 + 2 * 5 + 1] = 0x01		# row 5, column 15
        return jamoset.read_eng(bytes(pft))

    def test_pft_keeps_columns_12_to_15(self):
        e = self.pft()
        self.assertEqual(e.glyph(ord("H"))[20], 0x8008)
        self.assertEqual(e.glyph(ord("I"))[5], 0x0001)
        self.assertEqual(e.adv, 12)

    def test_hbios_keeps_columns_12_to_15(self):
        hb = bytearray(15360)
        hb[ord("H") * 60 + (3 + 5) * 2 + 1] = 0x04		# cell row 5, column 13
        e = jamoset.read_eng(bytes(hb))
        self.assertEqual(e.glyph(ord("H"))[5], 0x0004)
        self.assertEqual(e.adv, 12)

    def test_written_ascii_has_the_serif_and_steps_12(self):
        e = self.pft()
        out, _, _ = jamoset.build_from_source(jamoset.LAYOUTS["844-hbios24"], jamoset.open_hbios24(DosFace24.hbios()), e,
                                              advance=24)
        f = jamoset.parse_svfn(out)
        self.assertEqual(f.metrics[ord("H")][0], 12)
        row = int.from_bytes(f.glyphs[ord("H")][20 * 3:21 * 3], "big")
        self.assertEqual(row, 0x8008 << 8)				# 24 bit cell, glyph at the left
        self.assertEqual(f.metrics[ord("H")][2], 13)			# ink width runs to column 12

    def test_embolden_widens_before_it_shifts(self):
        e = self.pft()
        out, _, _ = jamoset.build_from_source(jamoset.LAYOUTS["844-hbios24"], jamoset.open_hbios24(DosFace24.hbios()), e,
                                              advance=24, bold=True)
        f = jamoset.parse_svfn(out)
        row = int.from_bytes(f.glyphs[ord("I")][5 * 3:6 * 3], "big")
        self.assertEqual(row, (0x0001 << 8) | (0x0001 << 7))		# column 15 and its copy in column 16
        h = int.from_bytes(f.glyphs[ord("H")][20 * 3:21 * 3], "big")
        self.assertEqual(h, 0x8008 << 8 | 0x4004 << 8)


class SmallCellSymbols(unittest.TestCase):
    def check(self, w, h, ascent, adv):
        for cp, (packed, a, ix, iw) in jamoset.symbol_glyphs(w, h, ascent, adv).items():
            nb = (w + 7) // 8
            self.assertEqual(len(packed), nb * h, (cp, w, h))
            for y in range(h):
                v = int.from_bytes(packed[y * nb:(y + 1) * nb], "big") >> (nb * 8 - w)
                self.assertLess(v, 1 << w)
            self.assertLessEqual(ix + iw, w)

    def test_narrow_and_short_cells_do_not_raise_or_spill(self):
        for w, h, ascent, adv in ((8, 8, 6, 8), (8, 16, 13, 4), (6, 8, 2, 6), (16, 16, 12, 8), (24, 24, 21, 12), (4, 4, 3, 4)):
            self.check(w, h, ascent, adv)

    def test_dots_are_clipped_not_shifted_wrong(self):
        packed = jamoset.symbol_glyphs(8, 8, 6, 8)[0x2026][0]
        rows = [packed[y] for y in range(8)]
        self.assertEqual([y for y, r in enumerate(rows) if r], [3, 4, 5])
        # centred in an 8 px advance the 11 px run overhangs by 2 px each side: dots at columns 0, 2-4 and 6-7
        self.assertEqual(rows[5], 0b10111011)


class MeanIouEmpty(unittest.TestCase):
    def test_no_targets_scores_zero(self):
        self.assertEqual(jamofit.mean_iou({}, {}, {}), 0.0)


class InkClipped(unittest.TestCase):
    def test_bottom_row_on_the_cell_edge_is_clipped(self):
        # baseline row oy, ink down to pen-relative bottom: the lowest ink row is oy - bottom
        self.assertTrue(jamoset.ink_clipped(10, 10, 16, 16, oy=16, top=12, bottom=0))		# row 16 is outside 0..15
        self.assertFalse(jamoset.ink_clipped(10, 10, 16, 16, oy=15, top=12, bottom=0))		# row 15 is the last
        self.assertTrue(jamoset.ink_clipped(10, 10, 16, 16, oy=3, top=12, bottom=0))		# top row -9
        self.assertFalse(jamoset.ink_clipped(10, 10, 16, 16, oy=12, top=12, bottom=0))
        self.assertTrue(jamoset.ink_clipped(17, 10, 16, 16, oy=12, top=12, bottom=0))		# wider than the cell


class TtfDefaults(unittest.TestCase):
    def test_present_only_is_the_default_and_can_be_turned_off(self):
        ap = jamoset.make_parser()
        a = ap.parse_args(["--layout", "844", "--from-ttf", "x.ttf", "--size", "16", "-o", "o"])
        self.assertTrue(a.present_only)
        a = ap.parse_args(["--layout", "844", "--from-ttf", "x.ttf", "--size", "16", "--no-present-only", "-o", "o"])
        self.assertFalse(a.present_only)
        a = ap.parse_args(["--layout", "844", "--from-ttf", "x.ttf", "--size", "16", "--present-only", "-o", "o"])
        self.assertTrue(a.present_only)

    def test_a_font_without_most_syllables_is_fitted_to_the_ones_it_draws(self):
        with tempfile.TemporaryDirectory() as d:
            rep = os.path.join(d, "r.json")
            code, out = run_main(["--layout", "844", "--from-ttf", "fake.ttf", "--size", "16", "--mask", "none",
                                  "-o", os.path.join(d, "o.svf"), "--report", rep])
            self.assertIsNone(code)
            import json
            info = json.load(open(rep))
            self.assertEqual(info["source"]["fitted"], 112)		# not 11,172 (.notdef boxes)
            self.assertEqual(info["quality"]["present"], 112)

    def test_off_fits_every_syllable_to_notdef(self):
        targets, w, h, ascent, info, _ = jamoset.ttf_targets("fake.ttf", 16, None, None, False, None) \
            if self.patched() else (None,) * 6
        self.assertEqual(info["fitted"], 11172)

    def patched(self):
        jf = jamoset._jamofit()
        self._old = jf.OutlineFont
        jf.OutlineFont = FakeOutline
        self.addCleanup(setattr, jf, "OutlineFont", self._old)
        return True

    def test_advance_is_honoured_by_from_ttf(self):
        with tempfile.TemporaryDirectory() as d:
            for extra, want in (([], 0), (["--advance", "20"], 20)):
                o = os.path.join(d, "o.svf")
                code, out = run_main(["--layout", "844", "--from-ttf", "fake.ttf", "--size", "16", "--mask", "none",
                                      "-o", o] + extra)
                self.assertIsNone(code)
                self.assertEqual(jamoset.unpack(jamoset.parse_svfn(open(o, "rb").read()).jset).advance, want, extra)


class FromSvfAdvance(unittest.TestCase):
    def test_explicit_advance_overrides_the_faces_own(self):
        with tempfile.TemporaryDirectory() as d:
            face, _, _ = composed_face(list(range(0, 11172, 40)))
            a = os.path.join(d, "F.SVF")
            open(a, "wb").write(face)
            for extra, want in (([], 16), (["--advance", "20"], 20)):
                o = os.path.join(d, "o.svf")
                code, out = run_main(["--layout", "844", "--from-svf", a, "--mask", "none", "-o", o] + extra)
                self.assertIsNone(code, out)
                self.assertEqual(jamoset.unpack(jamoset.parse_svfn(open(o, "rb").read()).jset).advance, want, extra)

MAC_SYSTEM = os.path.join(JOHAB_FONTS, "mac/extracted/kh10_system_disk/System Folder")
MAC_MUNJO24 = os.path.join(MAC_SYSTEM, "Munjo24.rsrc")
MAC_TOOLS = os.path.join(JOHAB_FONTS, "tools")
MAC_FBIT_FONTS = ("Gotic12", "Munjo12", "Munjo16", "Munjo24")
GOTIC12_JSET_V1 = 3783


def mac_fbit_faces(tmp):
    """{name: (face path, jamoset CompletedProcess, mac_kfont.HfntFont, cell w, cell h)} for the HangulTalk 1.0 fonts whose
    .rsrc is collected under MAC_SYSTEM; {} when mac_kfont.py is missing. No font byte is written outside @p tmp."""
    out = {}
    if not os.path.isdir(MAC_TOOLS):
        return out
    if MAC_TOOLS not in sys.path:
        sys.path.insert(0, MAC_TOOLS)
    import mac_kfont
    for name in MAC_FBIT_FONTS:
        src = os.path.join(MAC_SYSTEM, name + ".rsrc")
        if not os.path.exists(src):
            continue
        face = os.path.join(tmp, name.upper() + ".SVF")
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "jamoset.py"), "--layout", "mac-fbit-45sets",
                            src, "--symbols", "--check", "-o", face], capture_output=True, text=True)
        rs = mac_kfont.parse_rsrc(open(src, "rb").read())
        ref = mac_kfont.HfntFont(name, list(rs[b"fbit"].values())[0][1], rs[b"fdef"][3][1])
        out[name] = (face, r, ref, ref.px, ref.sets[0][2])
    return out


class MacFbit45Sets(unittest.TestCase):
    """--layout mac-fbit-45sets: HangulTalk 1.0 'fbit' Munjo/Gotic (45 glyph sets, planes chosen by the 'fdef' rules).

    The reference is the research tool mac_kfont.py (a literal transliteration of the 68k driver), which is outside
    this repository: the tests skip where $JOHAB_FONTS is not collected, per font (the skip names the missing
    path). The Mac composition needs 8 lead classes and 20 initial sets (JSET took 4 and 16 until this layout), and
    every one of the 11,172 syllables of each of Gotic12, Munjo12, Munjo16 and Munjo24 must compose to the Mac
    rendering bit for bit."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.faces = mac_fbit_faces(cls.tmp.name)
        cls.kfont = None
        if cls.faces:
            import kfont
            cls.kfont = kfont

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def fonts(self):
        """[(name, face, run, ref, w, h)] per font present, each to run under `with self.subTest(font=name)`. Skips (naming
        the missing path) when mac_kfont.py is absent or no font is collected."""
        if not os.path.isdir(MAC_TOOLS):
            self.skipTest(f"mac_kfont.py not collected: {MAC_TOOLS} is missing")
        missing = [os.path.join(MAC_SYSTEM, n + ".rsrc") for n in MAC_FBIT_FONTS if n not in self.faces]
        if len(missing) == len(MAC_FBIT_FONTS):
            self.skipTest("no HangulTalk font collected: " + ", ".join(missing))
        for path in missing:                 # a font absent from a partial collection is skipped by name, the rest run
            with self.subTest(font=os.path.basename(path)):
                self.skipTest("font absent: " + path)
        return [(n,) + self.faces[n] for n in MAC_FBIT_FONTS if n in self.faces]

    def mac_glyph(self, ref, w, h, s):
        a, b, c = self.kfont.johab_fields(s // 588, (s // 28) % 21, s % 28)
        g = ref.johab(0x8000 | a << 10 | b << 5 | c)
        return jamoset.glyph_gint(jamoset.Glyph(w, h, g.rows).to_bytes(), w, h)

    def test_ran_and_every_syllable_is_identical(self):
        for name, face, run, ref, w, h in self.fonts():
            with self.subTest(font=name):
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn("composed 11172 syllables", run.stdout)
                self.assertIn("differing syllables: 0", run.stdout)

    def test_every_syllable_is_the_mac_rendering_of_the_reference_port(self):
        for name, face, run, ref, w, h in self.fonts():
            with self.subTest(font=name):
                f = jamoset.parse_svfn(open(face, "rb").read())
                t = jamoset.unpack(f.jset)
                self.assertEqual((f.cell_w, f.cell_h, f.ascent, f.bpp), (w, h, h, 1))
                for s in range(11172):
                    got = jamoset.glyph_gint(jamoset.compose(f, t, 0xAC00 + s), w, h)
                    self.assertEqual(got, self.mac_glyph(ref, w, h, s), f"{name} U+{0xAC00 + s:04X}")

    def test_the_tables_are_what_the_rule_needs(self):
        for name, face, run, ref, w, h in self.fonts():
            with self.subTest(font=name):
                f = jamoset.parse_svfn(open(face, "rb").read())
                t = jamoset.unpack(f.jset)
                print(f"\n  mac-fbit-45sets {name}: (lc, tc, ni, nm, nf) = {(t.lc, t.tc, t.ni, t.nm, t.nf)}, "
                      f"JSET {len(f.jset)} B, cell {w}x{h}", file=sys.stderr)
                self.assertEqual(struct.unpack("<H", f.jset[4:6])[0], 1)
                self.assertEqual((t.lc, t.tc, t.ni, t.nf), (8, 4, 20, 4))
                self.assertLessEqual(t.nm, 16)
                if name == "Gotic12":
                    self.assertEqual(len(f.jset), GOTIC12_JSET_V1)

    def test_symbols_and_no_ascii(self):
        for name, face, run, ref, w, h in self.fonts():
            with self.subTest(font=name):
                f = jamoset.parse_svfn(open(face, "rb").read())
                self.assertIn(0x2026, f.glyphs)
                self.assertIn(0x25A1, f.glyphs)
                self.assertNotIn(0x41, f.glyphs)

    def test_layout_is_not_a_source_layout(self):
        self.assertNotIn("mac-fbit-45sets", jamoset.LAYOUTS)
        self.assertEqual(jamoset.make_parser().parse_args(["--layout", "mac-fbit-45sets", "-o", "x"]).layout,
                         "mac-fbit-45sets")

    def test_wrong_file_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "x")
            open(f, "wb").write(b"\0" * 64)
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "jamoset.py"), "--layout", "mac-fbit-45sets", f,
                                "-o", os.path.join(d, "o")], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertNotIn("Traceback", r.stderr)


MAC_DISK = MAC_SYSTEM + "/"


class MacGolden(unittest.TestCase):
    """The golden fixture of the Mac renderings (testdata/mac-fbit-golden.json) is not part of this repository."""

    def test_no_golden_without_the_fixture(self):
        self.assertIsNone(jamoset.mac_golden("Munjo24.rsrc"))
        self.assertIsNone(jamoset.mac_golden("Other.rsrc"))

    @staticmethod
    def synthetic_entry(data):
        """A golden entry in the fixture's shape, made here from a jamo face of svf/ (no Apple data)."""
        import hashlib
        f = jamoset.parse_svfn(data)
        t = jamoset.unpack(f.jset)
        cells = [jamoset.compose(f, t, 0xAC00 + s) for s in jamoset.ks_x_1001_syllables()]
        samples = {"%04X" % (0xAC00 + s): jamoset.compose(f, t, 0xAC00 + s).hex()
                   for s in list(jamoset.ks_x_1001_syllables())[::47]}
        return {"w": f.cell_w, "h": f.cell_h, "count": len(cells), "sha256": hashlib.sha256(b"".join(cells)).hexdigest(),
                "samples": samples}

    def test_golden_problems_on_a_synthetic_entry(self):
        data = open(os.path.join(HERE, "..", "svf", "dos", "NEODG16A.SVF"), "rb").read()
        entry = self.synthetic_entry(data)
        self.assertEqual(entry["count"], 2350)
        self.assertEqual(jamoset.mac_golden_problems(data, entry), [])
        f = jamoset.parse_svfn(data)
        t = jamoset.unpack(f.jset)
        n = next(p for p in t.init_piece if p != jamoset.BLANK)
        glyphs = [(cp, bytes(b ^ 0xFF for b in g) if cp == jamoset.PIECE_BASE + n else g, *f.metrics.get(cp, (16, 0, 16)))
                  for cp, g in f.glyphs.items()]
        bad = jamoset.write_svfn(f.cell_w, f.cell_h, f.ascent, glyphs, f.jset, f.flags & 4)
        probs = jamoset.mac_golden_problems(bad, entry)
        self.assertIn("sha256", " ".join(probs))
        self.assertEqual(jamoset.mac_golden_problems(data, dict(entry, w=entry["w"] + 1))[0][:4], "cell")


class MacFbitValidation(unittest.TestCase):
    """MacFbit refuses a damaged font instead of raising struct.error or reading short."""

    def fake(self, fbit, fdef_len=0x716):
        old = jamoset.mac_resources
        jamoset.mac_resources = lambda d: {b"fbit": {1: fbit}, b"fdef": {3: bytes(fdef_len)}}
        self.addCleanup(setattr, jamoset, "mac_resources", old)
        return jamoset.MacFbit(b"x")

    def header(self, nset=45):
        h = bytearray(0x56)
        h[2:6] = b"fbit"
        h[0x54:0x56] = (nset * 12).to_bytes(2, "big")
        return h

    def sets(self, w0=6, hi=0, off=0, h=24, n=45):
        return b"".join(w0.to_bytes(2, "big") + hi.to_bytes(2, "big") + off.to_bytes(2, "big") + h.to_bytes(2, "big") + bytes(4)
                        for _ in range(n))

    def test_short_fbit(self):
        with self.assertRaises(jamoset.SourceError):
            self.fake(bytes(self.header()) + bytes(10))

    def test_zero_dimensions(self):
        for kw in ({"w0": 0}, {"h": 0}):
            with self.assertRaises(jamoset.SourceError, msg=str(kw)):
                self.fake(bytes(self.header()) + self.sets(**kw) + bytes(200))

    def test_set_offset_beyond_the_resource(self):
        with self.assertRaises(jamoset.SourceError):
            self.fake(bytes(self.header()) + self.sets(off=60000) + bytes(200))

    def test_good_header_is_accepted(self):
        m = self.fake(bytes(self.header()) + self.sets() + bytes(200))
        self.assertEqual((m.w, m.h), (24, 24))


class MacCommandLine(unittest.TestCase):
    def run_tool(self, *argv):
        return subprocess.run([sys.executable, "-I", os.path.join(HERE, "jamoset.py"), "--layout", "mac-fbit-45sets", *argv],
                              capture_output=True, text=True)

    def test_missing_source_is_an_error_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_tool(os.path.join(d, "nope.rsrc"), "-o", os.path.join(d, "o"))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("nope.rsrc", r.stderr)

    @unittest.skipUnless(os.path.exists(MAC_DISK + "Munjo24.rsrc"), "Munjo24.rsrc not collected here")
    def test_check_without_a_golden_and_embolden_skips_the_mac_comparison(self):
        # this repository carries no golden fixture (testdata/mac-fbit-golden.json): --check says so and still passes
        with tempfile.TemporaryDirectory() as d:
            o = os.path.join(d, "o.svf")
            r = self.run_tool(MAC_DISK + "Munjo24.rsrc", "--check", "-o", o)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("golden: none for this font", r.stdout)
            r = self.run_tool(MAC_DISK + "Munjo24.rsrc", "--check", "--embolden", "-o", o)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("skipped", r.stdout)
            self.assertNotIn("differing syllables", r.stdout)


class GlyphDy(unittest.TestCase):
    """The per-glyph dy (header bytes 17/18, metrics byte 3; graphics/hires_text/README.md "Per-glyph dy")."""

    GLYPHS = [(ord("a"), bytes(range(32)), 9, 1, 7), (ord("p"), bytes([0x30] * 32), 9, 2, 5),
              (ord("t"), bytes([0x18] * 32), 6, 1, 3)]

    def test_no_dy_writes_zeros_as_before(self):
        out = jamoset.write_svfn(16, 16, 14, self.GLYPHS, b"")
        self.assertEqual(out[17:20], b"\0\0\0")
        self.assertEqual(out, jamoset.write_svfn(16, 16, 14, self.GLYPHS, b"", dy={}))
        f = jamoset.parse_svfn(out)
        self.assertEqual((f.dy_min, f.dy_max, f.dy), (0, 0, {}))
        self.assertEqual(f.metrics[ord("p")], (9, 2, 5))

    def test_dy_round_trips_with_its_range(self):
        out = jamoset.write_svfn(16, 16, 14, self.GLYPHS, b"", dy={ord("p"): 3, ord("t"): -2, ord("a"): 0})
        self.assertEqual(struct.unpack_from("<bbB", out, 17), (-2, 3, 0))
        f = jamoset.parse_svfn(out)
        self.assertEqual((f.dy_min, f.dy_max), (-2, 3))
        self.assertEqual(f.dy, {ord("p"): 3, ord("t"): -2})
        self.assertEqual(f.metrics[ord("t")], (6, 1, 3))
        jamoset.check_dy(f)
        with self.assertRaises(ValueError):
            jamoset.write_svfn(16, 16, 14, self.GLYPHS, b"", dy={ord("p"): 17})

    def test_check_refuses_a_dy_out_of_range_or_on_a_piece(self):
        out = bytearray(jamoset.write_svfn(16, 16, 14, self.GLYPHS, b"", dy={ord("p"): 3}))
        out[18] = 2		# the range no longer holds p's 3
        with self.assertRaises(ValueError):
            jamoset.check_dy(jamoset.parse_svfn(bytes(out)))
        piece = self.GLYPHS + [(jamoset.PIECE_BASE + 1, bytes(32), 16, 0, 16)]
        out = jamoset.write_svfn(16, 16, 14, piece, b"", dy={jamoset.PIECE_BASE + 1: 1})
        with self.assertRaises(ValueError):
            jamoset.check_dy(jamoset.parse_svfn(out))

    def test_rebuilding_keeps_the_dy_of_kept_glyphs(self):
        base = bytearray(jamoset.write_svfn(16, 16, 14, self.GLYPHS, b"", dy={ord("p"): 3}))
        struct.pack_into("<H", base, 6, 1)		# a plain proportional font: no jamo flag
        out, _, _ = jamoset.build(jamoset.LAYOUTS["844"], make_source("844"), base=bytes(base))
        f = jamoset.parse_svfn(out)
        self.assertEqual(f.dy, {ord("p"): 3})
        self.assertEqual((f.dy_min, f.dy_max), (0, 3))
        msg = jamoset.check(out, jamoset.LAYOUTS["844"], None)
        self.assertIn("dy 0..3 on 1 glyphs", msg)
        self.assertEqual(jamoset.parse_svfn(jamoset.blank_whole_compat(out)).dy, {ord("p"): 3})


class V3Writer(unittest.TestCase):
    """jamoset.py writes SVFN v3 through pack_svfn: build / the command, --profile and --box."""

    def test_writes_v3_default(self):
        out, _, _ = jamoset.build(jamoset.LAYOUTS["844"], make_source("844"), eng=bytes(4096))
        self.assertEqual(out[4:6], b"\x03\x00")
        f = jamoset.parse_svfn(out)
        self.assertEqual(f.layout, (2, 0, 2, True))
        self.assertIsNotNone(f.jset)

    def test_profile_dos(self):
        layout = jamoset.LAYOUTS["844"]
        a = jamoset.build_from_source(layout, layout.opener(make_source("844"), 0, ""))[0]
        b = jamoset.build_from_source(layout, layout.opener(make_source("844"), 0, ""), profile="dos")[0]
        self.assertEqual(b[9], 0)
        fa, fb = jamoset.parse_svfn(a), jamoset.parse_svfn(b)
        self.assertEqual(fb.glyphs, fa.glyphs)
        self.assertEqual(fb.jset, fa.jset)
        self.assertEqual(fb.metrics, fa.metrics)

    def test_command_takes_profile_and_box(self):
        with tempfile.TemporaryDirectory() as d:
            src, a, b = (os.path.join(d, n) for n in ("src.bin", "a.svf", "b.svf"))
            open(src, "wb").write(make_source("844"))
            for out, extra in ((a, []), (b, ["--profile", "dos", "--box", "full"])):
                r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "jamoset.py"), "--layout", "844", src,
                                    "-o", out] + extra, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
            da, db = open(a, "rb").read(), open(b, "rb").read()
            self.assertEqual((da[4:6], da[9], db[9]), (b"\x03\x00", 2, 0))
            self.assertEqual(jamoset.parse_svfn(db).glyphs, jamoset.parse_svfn(da).glyphs)
            fa = jamoset.parse_svfn(da)
            pitch = (fa.cell_w + 7) // 8
            inked = [x for x in jamoset.record_boxes(db) if x[2]]
            self.assertTrue(all(x[2] == pitch and x[3] == fa.cell_h for x in inked))
            self.assertTrue(inked)		# (the synthetic pieces are inked edge to edge, so no size difference to assert)
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "jamoset.py"), "--layout", "844", src,
                                "-o", a, "--profile", "nope"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)


class RewriteTools(unittest.TestCase):
    """johab844.py, fontmetrics.py: the tools that read a face with parse_svfn and write it with pack_svfn."""

    def johab_run(self, d, base_data, *extra):
        base, jam, out = (os.path.join(d, n) for n in ("b.svf", "j.kor", "o.svf"))
        open(base, "wb").write(base_data)
        rnd = random.Random(1)
        blob = bytearray(rnd.randbytes(360 * 32))
        for i in [s * 20 for s in range(8)] + [160 + s * 22 for s in range(4)] + [248 + s * 28 for s in range(4)]:
            blob[i * 32:(i + 1) * 32] = bytes(32)
        open(jam, "wb").write(bytes(blob))
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "johab844.py"), jam, base, out, *extra],
                           capture_output=True, text=True)
        return r, out

    def base_face(self, profile="default", **kw):
        rnd = random.Random(2)
        g = [(cp, rnd.randbytes(32), 10, 0, 8) for cp in list(range(0x21, 0x28)) + [0xAC00, 0xAC01, 0x2026]]
        return jamoset.write_svfn(16, 16, 13, g, b"", dy={0x25: 1}, profile=profile, **kw), g

    def test_johab844_with_and_without_eng(self):
        base, g = self.base_face()
        with tempfile.TemporaryDirectory() as d:
            r, out = self.johab_run(d, base)
            self.assertEqual(r.returncode, 0, r.stderr)
            f = jamoset.parse_svfn(open(out, "rb").read())
            b = jamoset.parse_svfn(base)
            self.assertEqual((f.version, f.layout, f.dy), (3, b.layout, b.dy))
            self.assertEqual(f.glyphs[0x21], b.glyphs[0x21])			# ASCII is the base's
            self.assertNotEqual(f.glyphs[0xAC00], b.glyphs[0xAC00])		# the syllable is redrawn
            self.assertEqual(f.glyphs[0xAC00], johab844.compose(open(os.path.join(d, "j.kor"), "rb").read(), 0xAC00))
            self.assertEqual(f.metrics[0xAC00][0], 10)				# its advance is kept
            eng = os.path.join(d, "e.eng")
            open(eng, "wb").write(random.Random(3).randbytes(4096))
            r, out = self.johab_run(d, base, "--eng", eng)
            self.assertEqual(r.returncode, 0, r.stderr)
            f = jamoset.parse_svfn(open(out, "rb").read())
            self.assertNotEqual(f.glyphs[0x21], b.glyphs[0x21])
            self.assertEqual(f.metrics[0x21][0], 8)
            self.assertEqual(f.glyphs[0x21][0::2], open(eng, "rb").read()[0x21 * 16:0x21 * 16 + 16])
            self.assertEqual(f.metrics[0x2026], b.metrics[0x2026])

    def test_johab844_and_svfdy_keep_the_input_layout(self):
        import svfdy
        base, _ = self.base_face("dos")
        self.assertEqual(base[9], 0)
        with tempfile.TemporaryDirectory() as d:
            r, out = self.johab_run(d, base)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(open(out, "rb").read()[9], 0)
            r, out = self.johab_run(d, base, "--profile", "default")
            self.assertEqual(open(out, "rb").read()[9], 2)
        self.assertEqual(svfdy.apply(base, {0x21: 1})[0][9], 0)
        self.assertEqual(svfdy.apply(base, {0x21: 1}, profile="default")[0][9], 2)
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.svf"), os.path.join(d, "b.svf")
            open(a, "wb").write(base)
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "svfdy.py"), a, b, "--set", "0x21=1"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(open(b, "rb").read()[9], 0)

    def test_a_truncated_base_is_a_one_line_error(self):
        base, _ = self.base_face()
        for cut in (3, 20, 47, len(base) // 2):
            with tempfile.TemporaryDirectory() as d:
                r, _out = self.johab_run(d, base[:cut])
                self.assertEqual(r.returncode, 2, (cut, r.stderr))
                self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
                a = os.path.join(d, "t.svf")
                open(a, "wb").write(base[:cut])
                r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "svfdy.py"), a, os.path.join(d, "x"),
                                    "--set", "0x21=1"], capture_output=True, text=True)
                self.assertEqual(r.returncode, 2, (cut, r.stderr))
                self.assertNotIn("Traceback", r.stderr)

    def test_fontmetrics_reads_v3(self):
        import fontmetrics
        import io
        import contextlib
        g = [(0x41, bytes([0xFF] * 32), 8, 0, 8), (0x42, bytes([0xFF] * 32), 4, 0, 12), (0x43, bytes(32), 8, 0, 0)]
        face = jamoset.write_svfn(16, 16, 13, g, b"")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.svf")
            open(p, "wb").write(face)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                fontmetrics.report(p)
            text = buf.getvalue()
        self.assertIn("version 3  cell 16x16  bpp=1  glyphs=3", text)
        self.assertIn("1 of 3 glyphs reach past their advance", text)
        self.assertIn("000042", text)


class SvfDy(unittest.TestCase):
    """svfdy.py: reads and rewrites through parse_svfn / pack_svfn."""

    def test_a_face_with_an_unusable_jset_is_refused(self):
        import svfdy
        with tempfile.TemporaryDirectory() as d:
            ok, bad = os.path.join(d, "ok.svf"), os.path.join(d, "bad.svf")
            open(ok, "wb").write(self.face())
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "svf_synth.py"), "--jset-bad", "missing_piece",
                                "--from", ok, bad], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            data = open(bad, "rb").read()
            self.assertTrue(jamoset.parse_svfn(data).jset_bad)
            with self.assertRaises(ValueError):
                svfdy.apply(data, {0x61: 1})
            for args in ([os.path.join(d, "o.svf"), "--set", "0x61=1"], ["--show"]):
                r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "svfdy.py"), bad] + args,
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("JSET", r.stderr)
            self.assertFalse(os.path.exists(os.path.join(d, "o.svf")))

    def test_show_refuses_a_face_without_metrics(self):
        plain = jamoset.pack_svfn(8, 2, 1, 1, 0, [bytes([1, 0])], [(0x41, 0)], None, None, (0, 0), "default")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.svf")
            open(p, "wb").write(plain)
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "svfdy.py"), p, "--show"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("metrics", r.stderr)

    def test_svfdy_round_trip(self):
        import svfdy
        face = self.face()
        out, info = svfdy.apply(face, {ord("p"): 3, ord("t"): -1})
        self.assertEqual(out[4:6], b"\x03\x00")
        f = jamoset.parse_svfn(out)
        self.assertEqual((f.dy, f.dy_min, f.dy_max), ({ord("p"): 3, ord("t"): -1}, -1, 3))
        b = jamoset.parse_svfn(face)
        self.assertEqual(f.glyphs, b.glyphs)
        self.assertEqual((f.metrics, f.jset, f.flags), (b.metrics, b.jset, b.flags))
        out_dos, _ = svfdy.apply(face, {ord("p"): 3, ord("t"): -1}, profile="dos")
        self.assertEqual(out_dos[9], 0)
        self.assertEqual(jamoset.parse_svfn(out_dos).glyphs, f.glyphs)

    def face(self):
        base = bytearray(jamoset.write_svfn(16, 16, 14, GlyphDy.GLYPHS, b""))
        struct.pack_into("<H", base, 6, 1)
        return jamoset.build(jamoset.LAYOUTS["844"], make_source("844"), base=bytes(base))[0]

    def test_apply_changes_only_the_dy_bytes(self):
        import svfdy
        face = self.face()
        out, info = svfdy.apply(face, {ord("p"): 3, ord("t"): -1, 0x41: 2})
        self.assertEqual((info["set"], info["missing"], info["dy_min"], info["dy_max"]), (2, [0x41], -1, 3))
        f = svfdy.verify(face, out)
        self.assertEqual(f.dy, {ord("p"): 3, ord("t"): -1})
        before, after = jamoset.parse_svfn(face), f
        t = jamoset.unpack(after.jset)
        for cp in range(0xAC00, 0xD7A4, 97):
            self.assertEqual(jamoset.compose(before, t, cp), jamoset.compose(after, t, cp))
        cleared, info = svfdy.apply(out, {}, clear=True)
        self.assertEqual(cleared, face)
        with self.assertRaises(ValueError):
            svfdy.apply(face, {jamoset.PIECE_BASE + 1: 1})

    def test_command(self):
        face = self.face()
        with tempfile.TemporaryDirectory() as d:
            a, b, c, j = (os.path.join(d, n) for n in ("a.svf", "b.svf", "c.svf", "dy.json"))
            open(a, "wb").write(face)
            tool = os.path.join(HERE, "svfdy.py")
            r = subprocess.run([sys.executable, tool, a, b, "--range", "0x61-0x7a", "--dy", "2", "--set", "t=-1"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("range -1..2", r.stdout)
            f = jamoset.parse_svfn(open(b, "rb").read())
            self.assertEqual(f.dy, {ord("a"): 2, ord("p"): 2, ord("t"): -1})
            open(j, "w").write('{"0x70": 4}')
            r = subprocess.run([sys.executable, tool, b, c, "--clear", "--json", j], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(jamoset.parse_svfn(open(c, "rb").read()).dy, {ord("p"): 4})
            r = subprocess.run([sys.executable, tool, c, "--show"], capture_output=True, text=True)
            self.assertIn("dy range 0..4, 1 glyphs", r.stdout)


from test_jamoaa import *  # noqa: E402,F401,F403  (the 2 bpp / outline tests run with the rest)


class DefaultMaskFontPath(unittest.TestCase):
    def test_the_mask_font_is_found_beside_a_scummvm_checkout_of_the_submodule(self):
        # svf-fonts as dists/svf-fonts of a ScummVM tree: Noto Sans KR is ScummVM's dists/engine-data/fonts/fonts-cjk
        with tempfile.TemporaryDirectory() as d:
            tools = os.path.join(d, "dists", "svf-fonts", "tools")
            noto = os.path.join(d, "dists", "engine-data", "fonts", "fonts-cjk", "NotoSansKR-Regular.otf")
            os.makedirs(tools)
            os.makedirs(os.path.dirname(noto))
            open(noto, "wb").close()
            self.assertEqual(os.path.realpath(jamoset.mask_font_beside(tools)), os.path.realpath(noto))

    def test_no_mask_font_in_a_standalone_checkout(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "svf-fonts", "tools"))
            self.assertIsNone(jamoset.mask_font_beside(os.path.join(d, "svf-fonts", "tools")))


class TestSvfn3(unittest.TestCase):
    """SVFN v3: profiles, ink-box records, the shared packer, the v3 parser (spec "Glyph record", "Tables")."""

    UNITS = "6,6,6,32"

    @staticmethod
    def face(profile="default", n=2, cw=13, ch=4, bpp=1):
        pitch = (cw * bpp + 7) // 8
        cells = [bytes((i + 1) * (k % 3 == 1) for k in range(pitch * ch)) for i in range(n)]
        cmap = [(0x41 + i, i) for i in range(n)]
        metrics = [(cw, 0, cw, 0)] * n
        return jamoset.pack_svfn(cw, ch, ch - 1, bpp, 0, cells, cmap, metrics, None, (0, 0), profile), cells

    def test_header_bytes(self):
        data, _ = self.face("default")
        self.assertEqual(data[4:6], b"\x03\x00")
        self.assertEqual((data[9], data[10], data[11]), (0x02, 0x0A, 0))
        self.assertEqual(struct.calcsize(jamoset.HEADER3), 48)
        self.assertEqual(jamoset.HEADER3_SIZE, 48)
        for o in (20, 24, 32, 36, 44):
            self.assertEqual(struct.unpack_from("<I", data, o)[0] % 4, 0)
        d, _ = self.face("dos")
        self.assertEqual((d[9], d[10]), (0, 0))
        d, _ = self.face("simd16")
        self.assertEqual((d[9], d[10]), (0x04, 0x0C))

    def test_profile_of(self):
        self.assertEqual(jamoset.profile_of("6,6,6,32"), jamoset.Profile(6, 6, 6, "x", "u32"))
        self.assertEqual(jamoset.profile_of("default", "y").box, "y")
        for bad in ("1,2,0,16", "7,0,0,16", "2,0,2,8"):
            with self.assertRaises(ValueError):
                jamoset.profile_of(bad)

    def test_record_edge_cells(self):
        for name in list(jamoset.PROFILES) + [self.UNITS]:
            pr = jamoset.profile_of(name)
            for cw, ch, bpp, pix in ((13, 5, 1, 0x08), (7, 5, 2, 0x0C), (3, 4, 8, 0xFF)):
                pitch = (cw * bpp + 7) // 8
                n = pitch * ch
                one = bytearray(n)
                one[pitch - 1] = pix              # the last column of the last byte of row 0
                ink = bytes([0xFF]) * n if bpp == 8 else bytes([0xF8] * n)
                for label, c in (("zero", bytes(n)), ("ink", ink), ("last column", bytes(one)),
                                 ("255", bytes([255]) * n)):
                    with self.subTest(profile=name, cell=label, bpp=bpp):
                        rec = jamoset.encode_record(c, pitch, ch, pr.box, pr.rec, pr.row)
                        self.assertEqual(len(rec) % (1 << pr.rec), 0)
                        self.assertEqual(jamoset.decode_record(rec, pitch, ch, pr.rec, pr.row), c)
                        if label == "zero":
                            self.assertEqual(rec, bytes(max(4, 1 << pr.rec)))
                        elif label == "last column" and pr.box == "x":
                            self.assertEqual(tuple(rec[:4]), (pitch - 1, 0, 1, 1))
                        elif label != "last column":
                            self.assertEqual(tuple(rec[:4]), (0, 0, pitch, ch))
        self.assertEqual(jamoset.cell_box(bytes(4), 2, 2, "full"), (0, 0, 0, 0))
        self.assertEqual(jamoset.cell_box(bytes([0, 0, 0, 1]), 2, 2, "y"), (0, 1, 2, 1))
        self.assertEqual(jamoset.cell_box(bytes([0, 0, 0, 1]), 2, 2, "full"), (0, 0, 2, 2))
        self.assertEqual(jamoset.cell_box(bytes([0, 0, 0, 1]), 2, 2, "x"), (1, 1, 1, 1))

    def test_phase(self):
        pitch, ch = 3, 6
        cell = bytearray(pitch * ch)
        cell[3 * pitch] = 1
        cell[5 * pitch + 2] = 2
        cell = bytes(cell)
        rows = cell[9:18]
        rec = jamoset.encode_record(cell, pitch, ch, "y", 2, 0)       # full width, y0 = 3: (9 & 3) = 1
        self.assertEqual(tuple(rec[:4]), (0, 3, 3, 3))
        self.assertEqual(rec[4:5], b"\0")
        self.assertEqual(rec[5:14], rows)
        rec = jamoset.encode_record(cell, pitch, ch, "y", 2, 1)       # ROW 1: no phase, rows of 4
        self.assertEqual(rec[4:16], b"".join(rows[3 * r:3 * r + 3] + b"\0" for r in range(3)))
        rec = jamoset.encode_record(cell, pitch, ch, "y", 1, 0)       # REC 1: no phase
        self.assertEqual(rec[4:13], rows)
        rec = jamoset.encode_record(cell, pitch, ch, "x", 2, 0)       # ink spans the pitch here: still phase
        self.assertEqual(rec[5:14], rows)
        narrow = bytearray(cell)
        narrow[5 * pitch + 2] = 0
        rec = jamoset.encode_record(bytes(narrow), pitch, ch, "x", 2, 0)   # wb < pitch: no phase
        self.assertEqual(tuple(rec[:4]), (0, 3, 1, 1))
        self.assertEqual(rec[4], 1)

    @staticmethod
    def _entries(data):
        n = struct.unpack_from("<H", data, 12)[0]
        off = struct.unpack_from("<I", data, 44)[0]
        wide = data[10] & 8
        return struct.unpack_from("<%d%s" % (n + 1, "I" if wide else "H"), data, off)

    @staticmethod
    def _boundary(profile, ink, blank):
        cells = [b"\x01"] * ink + [b"\0"] * blank       # 1x1 byte cells: an ink record is 5 bytes, a blank one 4
        return jamoset.pack_svfn(8, 1, 1, 1, 0, cells, [(i, i) for i in range(len(cells))], None, None, (0, 0),
                                 profile)

    def test_offset_width_boundary(self):
        size = lambda d: struct.unpack_from("<I", d, 28)[0]
        d = self._boundary("mcu-strict", 32767, 1)                    # 32767 * 8 + 4 = 65535 * 4
        self.assertEqual((size(d), d[10] & 8), (65535 * 4, 0))
        ent = self._entries(d)
        self.assertEqual((ent[1], ent[-1]), (2, 65535))
        self.assertEqual(jamoset.parse_svfn(d).count, 32768)
        d = self._boundary("mcu-strict", 32767, 2)
        self.assertEqual((size(d), d[10] & 8), (65535 * 4 + 4, 8))
        self.assertEqual(self._entries(d)[1], 8)
        self.assertEqual(jamoset.parse_svfn(d).count, 32769)
        d = self._boundary("dos", 13107, 0)
        self.assertEqual((size(d), d[10] & 8), (65535, 0))
        self.assertEqual(self._entries(d)[-1], 65535)
        d = self._boundary("dos", 13104, 4)
        self.assertEqual((size(d), d[10] & 8), (65536, 8))
        self.assertEqual(jamoset.parse_svfn(d).count, 13108)

    def test_round_trip_shipped(self):
        root = os.path.dirname(HERE)
        for rel in ("svf/dos/NEODG16G.SVF", "svf/dos/PAPLG16.SVF", "svf/dos/MARUS24.SVF"):
            with open(os.path.join(root, rel), "rb") as fh:
                data = fh.read()
            a = jamoset.parse_svfn(data)
            for name in list(jamoset.PROFILES) + [self.UNITS]:
                with self.subTest(rel=rel, profile=name):
                    b = jamoset.parse_svfn(jamoset.relayout(data, name))
                    self.assertEqual(b.version, 3)
                    for attr in ("glyphs", "metrics", "dy", "jset", "flags", "cell_w", "cell_h", "ascent", "bpp"):
                        self.assertEqual(getattr(b, attr), getattr(a, attr), attr)
            self.assertEqual(jamoset.parse_svfn(jamoset.relayout(data, "default", "full")).glyphs, a.glyphs)

    def test_write_svfn_profile(self):
        glyphs = [(0x42, bytes([0, 3]), 5, 0, 4), (0x41, bytes([1, 0]), 6, 1, 3)]
        f = jamoset.parse_svfn(jamoset.write_svfn(8, 2, 1, glyphs, b"", bpp=1, dy={0x41: 1}, profile="default"))
        self.assertEqual((f.version, f.layout), (3, (2, 0, 2, True)))
        self.assertEqual(f.glyphs, {0x42: bytes([0, 3]), 0x41: bytes([1, 0])})
        self.assertEqual((f.metrics[0x41], f.dy, f.dy_max), ((6, 1, 3), {0x41: 1}, 1))
        self.assertIsNone(f.jset)

    # ---- the parser's refusals ----

    def _good(self):
        cells = [bytes(8), bytes([0, 1, 0, 0, 0, 0, 0, 0]), bytes([0, 0, 2, 0, 0, 0, 0, 0])]
        return bytearray(jamoset.pack_svfn(8, 8, 7, 1, 0, cells, [(0x41 + i, i) for i in range(3)], None, None,
                                           (0, 0), "default"))

    def _refuses(self, mod, rx, data=None):
        d = bytearray(data if data is not None else self._good())
        mod(d)
        with self.assertRaisesRegex(ValueError, rx):
            jamoset.parse_svfn(bytes(d))

    def test_parse_refuses(self):
        u32 = lambda d, at, v: struct.pack_into("<I", d, at, v)
        self._refuses(lambda d: d.__setitem__(9, 7), "unit log2 past 6")
        self._refuses(lambda d: d.__setitem__(9, 0x08), "ROW 1 is larger than REC 0")
        self._refuses(lambda d: d.__setitem__(9, d[9] | 0x40), "byte 9 bits 6-7")
        self._refuses(lambda d: d.__setitem__(10, d[10] | 0x10), "byte 10 bits 4-7")
        g = self._good()
        tab = struct.unpack_from("<I", g, 44)[0]
        data_off = struct.unpack_from("<I", g, 24)[0]
        size = struct.unpack_from("<I", g, 28)[0]
        self._refuses(lambda d: u32(d, 44, tab + 1), "alignment: glyph offset table")
        self._refuses(lambda d: u32(d, 24, data_off + 2), "alignment: glyph data offset")
        self._refuses(lambda d: u32(d, tab + 4, 2), "alignment: offset entry 1")
        self._refuses(lambda d: u32(d, tab + 8, 0), "offset table decreases")
        self._refuses(lambda d: u32(d, tab + 12, size - 4), "last entry")
        e = struct.unpack_from("<4I", g, tab)
        r1 = data_off + e[1]
        self._refuses(lambda d: d.__setitem__(slice(r1, r1 + 3), bytes((1, 0, 8))), "past the pitch")
        self._refuses(lambda d: d.__setitem__(slice(r1, r1 + 4), bytes((0, 6, 1, 3))), "past the cell height")
        self._refuses(lambda d: d.__setitem__(slice(r1, r1 + 4), bytes((0, 0, 1, 5))), "rows .* are past its")
        # a 3 byte record: byte-tight (dos) file, one 4 byte record cut to 3
        h = bytearray(jamoset.pack_svfn(8, 4, 1, 1, 0, [bytes(4)], [(1, 0)], None, None, (0, 0), "dos"))
        t0 = struct.unpack_from("<I", h, 44)[0]
        del h[-1]
        struct.pack_into("<I", h, 28, 3)
        struct.pack_into("<H", h, t0 + 2, 3)
        with self.assertRaisesRegex(ValueError, "shorter than its 4 byte header"):
            jamoset.parse_svfn(bytes(h))

    def _jset_face(self):
        jset = jamoset.pack_v1(jamoset.renumber(jamoset.tables_for(jamoset.LAYOUTS["844"]), {s: s for s in range(360)}))
        # a piece glyph for every piece number the block names (a block naming a missing glyph is a plain face)
        return jset, jamoset.pack_svfn(8, 4, 1, 1, 0, [bytes(4)] * 360, [(jamoset.PIECE_BASE + i, i) for i in range(360)],
                                       None, jset, (0, 0), "default")

    def test_jset_range_and_size_refused(self):
        jset, data = self._jset_face()
        self.assertEqual(jamoset.parse_svfn(data).jset, jset)
        for label, at, v in (("size one off", 40, len(jset) - 1), ("size 0", 40, 0)):
            with self.subTest(label):                  # spec: fails validation / size 0 -> a plain face, not an error
                d = bytearray(data)
                struct.pack_into("<I", d, at, v)
                f = jamoset.parse_svfn(bytes(d))
                self.assertIsNone(f.jset)
                self.assertTrue(f.jset_bad)
        d = bytearray(data)
        d[jamoset.parse_svfn(data) and struct.unpack_from("<I", data, 36)[0]] ^= 0xFF   # break the JSET magic
        f = jamoset.parse_svfn(bytes(d))
        self.assertIsNone(f.jset)
        self.assertTrue(f.jset_bad)
        for label, at, v, rx in (("past the file", 36, len(data), "outside the file"),
                                 ("in the header", 36, 0, "inside the header")):
            with self.subTest(label):
                d = bytearray(data)
                struct.pack_into("<I", d, at, v)
                with self.assertRaisesRegex(ValueError, rx):
                    jamoset.parse_svfn(bytes(d))
        d = bytearray(data)
        d[6] &= ~2                                     # flag clear: no JSET, the fields are ignored
        self.assertIsNone(jamoset.parse_svfn(bytes(d)).jset)

    def test_empty_jset_writes_none(self):
        for js in (b"", None):
            d = jamoset.pack_svfn(8, 4, 1, 1, 0, [bytes(4)], [(1, 0)], None, js, (0, 0), "default")
            self.assertEqual(struct.unpack_from("<HII", d, 6)[0] & 2, 0)
            self.assertEqual(struct.unpack_from("<II", d, 36), (0, 0))

    def test_zero_cell_size_refused(self):
        for at in (14, 15):
            d = bytearray(self._good())
            d[at] = 0
            with self.assertRaisesRegex(ValueError, "cell width or height is 0"):
                jamoset.parse_svfn(bytes(d))

    def test_row_padding_counted(self):
        # units 3,3,3: one glyph wb 1 h 1 needs 4 + 8 bytes; the record cut to 8 (last row's padding missing) is refused
        d = bytearray(jamoset.pack_svfn(8, 1, 1, 1, 0, [b"\x01"], [(1, 0)], None, None, (0, 0), "3,3,3,32"))
        off = struct.unpack_from("<I", d, 24)[0]
        self.assertEqual(struct.unpack_from("<I", d, 28)[0], 16)   # 4 + 8, padded to the unit 8
        with self.assertRaisesRegex(ValueError, "past its"):
            jamoset.decode_record(bytes(d[off:off + 8]), 1, 1, 3, 3)

    def test_pack_refuses_bad_input(self):
        def pack(cells=None, cmap=None, metrics="ok", cw=8, ascent=1, dr=(0, 0)):
            cells = cells or [bytes(2), bytes(2)]
            m = [(8, 0, 8, 0)] * len(cells) if metrics == "ok" else metrics
            return jamoset.pack_svfn(cw, 2, ascent, 1, 0, cells,
                                     cmap or [(i + 1, i) for i in range(len(cells))], m, None, dr, "default")
        pack()
        for kw, rx in ((dict(metrics=[(8, 200, 8, 0)] * 2), "bearing_x 200"),
                       (dict(metrics=[(8, 0, 8, 128)] * 2), "dy 128"),
                       (dict(metrics=[(256, 0, 8, 0)] * 2), "advance 256"),
                       (dict(metrics=[(8, 0, 256, 0)] * 2), "ink_w 256"),
                       (dict(dr=(0, 200)), "dy_max 200"),
                       (dict(dr=(-129, 0)), "dy_min -129"),
                       (dict(cw=256), "cell width 256"),
                       (dict(cw=0), "cell width 0"),
                       (dict(ascent=256), "ascent 256"),
                       (dict(cmap=[(1, 0), (2, 2)]), "names glyph 2"),
                       (dict(cmap=[(2, 0), (1, 1)]), "strictly ascending"),
                       (dict(cmap=[(1, 0), (1, 1)]), "strictly ascending")):
            with self.subTest(rx), self.assertRaisesRegex(ValueError, rx):
                pack(**kw)

    def test_relayout_every_face(self):
        if not os.environ.get("SVF_ALL_FACES"):
            self.skipTest("set SVF_ALL_FACES=1 for the every-face round trip")
        root = os.path.join(os.path.dirname(HERE), "svf")
        n = 0
        for dp, _, fs in os.walk(root):
            for fn in sorted(fs):
                if not fn.upper().endswith(".SVF"):
                    continue
                with open(os.path.join(dp, fn), "rb") as fh:
                    data = fh.read()
                a = jamoset.parse_svfn(data)
                for name in list(jamoset.PROFILES) + ["6,6,6,32", "5,5,3,32", "1,1,6,32", "3,0,1,32"]:
                    b = jamoset.parse_svfn(jamoset.relayout(data, name))
                    for attr in ("glyphs", "metrics", "dy", "jset", "flags", "cell_w", "cell_h", "ascent", "bpp"):
                        self.assertEqual(getattr(b, attr), getattr(a, attr), (fn, name, attr))
                n += 1
        print("relayout round trip faces:", n)


class ShippedFacesAreJsetV1(unittest.TestCase):
    """Spec amendment 3: svf/ stays JSET version 1 (version 2 is an opt-in format). A writer-default regression that
    regenerated svf/ as version 2 must fail here, not pass every other gate."""

    ROOT = os.path.dirname(HERE)

    @staticmethod
    def jset_version(data):
        f = jamoset.parse_svfn(data)
        return struct.unpack_from("<H", f.jset, 4)[0] if f.jset else None

    def test_every_jamo_face_under_svf_is_version_1(self):
        n, bad = 0, []
        for root, _, names in os.walk(os.path.join(self.ROOT, "svf")):
            for name in names:
                if not name.lower().endswith(".svf"):
                    continue
                path = os.path.join(root, name)
                with open(path, "rb") as fh:
                    v = self.jset_version(fh.read())
                if v is not None:
                    n += 1
                    if v != 1:
                        bad.append((path, v))
        self.assertEqual(bad, [])
        self.assertEqual(n, 66)

    def test_the_check_bites_on_a_version_2_copy(self):
        sys.path.insert(0, HERE)
        import svf_synth
        f, t = svf_synth.load(os.path.join(self.ROOT, "svf", "dos", "NEODG16G.SVF"))
        block, pm = svf_synth.packed(t, 2)
        v2 = svf_synth.rebuild(f, block, piece_map=pm)
        self.assertEqual(self.jset_version(v2), 2)
        with open(os.path.join(self.ROOT, "svf", "dos", "NEODG16G.SVF"), "rb") as fh:
            self.assertEqual(self.jset_version(fh.read()), 1)


class JmapFormat(unittest.TestCase):
    """JSET block version 3 (JMAP): the Python reference every C reader test compares against."""

    ROOT = os.path.dirname(HERE)
    FACE = os.path.join(ROOT, "svf", "dos", "NEODG16G.SVF")

    @classmethod
    def setUpClass(cls):
        with open(cls.FACE, "rb") as fh:
            f = jamoset.parse_svfn(fh.read())
        cls.face = f
        cls.t = jamoset.unpack(f.jset)
        cls.glyphs = {cp - jamoset.PIECE_BASE: g for cp, g in f.glyphs.items() if cp >= jamoset.PIECE_BASE}
        cls.cp_glyphs = {cp: g for cp, g in f.glyphs.items() if cp >= jamoset.PIECE_BASE}
        cls.ks = jamoset.ks_x_1001_syllables()
        cls.all = range(11172)

    def test_pad_guard_keeps_the_plane_tag_clear(self):
        jamoset.jmap_from_tables(self.t, self.ks, self.glyphs, (16383, 0, 0))           # last pad that fits below bit 14
        with self.assertRaisesRegex(ValueError, "pad pieces cannot be made distinct"):
            jamoset.jmap_from_tables(self.t, self.ks, self.glyphs, (16384, 0, 0))

    def build(self, syllables=None, pad=(0, 0, 0)):
        return jamoset.jmap_from_tables(self.t, self.ks if syllables is None else syllables, self.glyphs, pad)[0]

    def fallback(self, jm, version):
        """The face's own JSET as a fallback block of @p jm: version 1 or 2, every piece shifted above the JMAP's."""
        return jamoset.pack_fallback(self.t, version, jm.pi + jm.pm + jm.pf)

    def sparse3(self):
        jm = self.build()
        return jm, bytearray(jamoset.pack_jmap(jm))

    def four_b(self):
        base = self.build(self.all)
        jm = self.build(self.all, (300 - base.pi, 0, 255 - base.pf))
        self.assertEqual((jm.pi, jm.pf), (300, 255))
        return jm, bytearray(jamoset.pack_jmap(jm))

    def test_sizes(self):
        self.assertEqual(jamoset.jmap_size(2350, False, True), 8654)
        self.assertEqual(jamoset.jmap_size(11172, False, False), 33634)
        self.assertEqual(jamoset.jmap_size(11172, True, False), 44806)
        self.assertEqual(jamoset.jmap_size(11172, True, True), 46292)
        self.assertEqual(jamoset.jmap_size(2350, False, True, 100), 8754)

    def test_round_trip(self):
        jm0 = self.build()
        v1, v2 = self.fallback(jm0, 1), self.fallback(jm0, 2)
        cases = {
            "sparse 3B": (self.build(), None),
            "dense 4B": (self.build(self.all, (300 - self.build(self.all).pi, 0, 0)), None),
            "sparse + v1": (self.build(), v1),
            "sparse + v2": (self.build(), v2),
        }
        for name, (jm, fb) in cases.items():
            with self.subTest(name):
                b = jamoset.pack_jmap(jm, fb)
                back = jamoset.unpack_jmap(b)
                self.assertEqual(jamoset.pack_jmap(back, fb), b)
                u = jamoset.unpack(b)
                self.assertIsInstance(u, jamoset.Jmap)
                self.assertEqual(u.entries, jm.entries)
                self.assertEqual(u.version, 3)
                self.assertEqual(u.fallback is None, fb is None)
        self.assertEqual(jamoset.unpack_jmap(jamoset.pack_jmap(cases["dense 4B"][0])).pi, 300)
        # PM and PF over 255 with entries high in every plane: i_hi, m_hi and f_hi are all exercised
        rnd = random.Random(7)
        counts = (1900, 700, 900)
        for sparse in (False, True):
            with self.subTest(sparse=sparse):
                keys = rnd.sample(range(11172), 3000) if sparse else range(11172)
                ent = {s: tuple(rnd.randint(c * 3 // 4, c) for c in counts) for s in keys}
                ent[min(keys)] = counts
                jm = jamoset.Jmap(3, *counts, ent)
                b = jamoset.pack_jmap(jm)
                self.assertEqual(b[6] & 3, 1 | (2 if sparse else 0))
                back = jamoset.unpack_jmap(b)
                self.assertEqual((back.entries, back.advance, back.pm, back.pf), (ent, 3, 700, 900))
                self.assertEqual(jamoset.pack_jmap(back), b)

    def test_4b_entry_bytes(self):
        # b0 = i_hi (bits 0-2) | m_hi (bits 3-5) << 3 | f_hi (bits 6-7) << 6, then i_lo, m_lo, f_lo
        for counts, entry, want in (((257, 257, 257), (257, 257, 257), bytes((0x49, 1, 1, 1))),
                                    ((2047, 3, 1023), (2047, 3, 1023), bytes((0xC7, 255, 3, 255))),
                                    ((1, 1500, 1), (1, 1500, 1), bytes((0x28, 1, 220, 1))),
                                    ((300, 300, 300), (0, 256, 0), bytes((0x08, 0, 0, 0)))):
            with self.subTest(entry=entry):
                b = jamoset.pack_jmap(jamoset.Jmap(0, *counts, {0: entry}))
                self.assertEqual(b[6], 3)                              # 4B | SPARSE
                self.assertEqual(b[1604:1608], want)
                self.assertEqual(jamoset.unpack_jmap(b).entries, {0: entry})
                dense = jamoset.Jmap(0, *counts, {s: entry for s in range(11172)})
                self.assertEqual(jamoset.pack_jmap(dense)[118:122], want)

    def test_pack_chooses_flags(self):
        base = self.build()
        for pi, flag in ((255, 0), (256, 1)):
            jm = self.build(pad=(pi - base.pi, 0, 0))
            self.assertEqual(jm.pi, pi)
            self.assertEqual(jamoset.pack_jmap(jm)[6] & 1, flag)
        self.assertEqual(jamoset.pack_jmap(base)[6] & 2, 2)
        self.assertEqual(jamoset.pack_jmap(self.build(self.all))[6] & 2, 0)

    def test_rules_refused(self):
        jm, b = self.sparse3()
        pi, pm, pf = jm.pi, jm.pm, jm.pf
        F = len(b)
        v1 = bytearray(self.fallback(jm, 1))
        j4, b4 = self.four_b()

        def put16(m, off, v):
            struct.pack_into("<H", m, off, v)
            return m

        def with_(base, fn):
            m = bytearray(base)
            r = fn(m)
            return m if r is None else r

        fb_junk = bytearray(b4)
        fb_junk[6] |= 4
        fb_junk += bytes(65535 - len(fb_junk))
        fbv3 = bytearray(v1)
        fbv3[4] = 3
        fbadv = bytearray(v1)
        fbadv[11] += 1
        e4 = 1604 if b4[6] & 2 else 118                 # b4 is dense: its entries start at 118
        self.assertEqual(e4, 118)
        f256 = bytearray(b4)
        f256[e4] = (f256[e4] & 0x3F) | (1 << 6)       # f_hi = 1 ...
        f256[e4 + 3] = 0                              # ... f_lo = 0: f = 256 = PF + 1
        i_over = bytearray(b)
        i_over[1604] = pi + 1
        rank = bytearray(b)
        put16(rank, 118 + 20, struct.unpack_from("<H", rank, 118 + 20)[0] + 1)
        ns = bytearray(b) + bytes(3)
        put16(ns, 8, 2351)
        cases = [
            ("R1", b[:117]),
            ("R1", with_(b, lambda m: m.__setitem__(6, 0x10))),            # 0x08 is the LIST flag now (JmapList)
            ("R1", with_(b, lambda m: m.__setitem__(0, 0x58))),
            ("R1", with_(b, lambda m: put16(m, 4, 4))),
            ("R2", with_(b, lambda m: put16(m, 10, 256))),
            ("R2", with_(b4, lambda m: put16(m, 10, 2048))),
            ("R2", with_(b4, lambda m: put16(m, 14, 1024))),
            ("R2", with_(b, lambda m: (put16(m, 10, 0), put16(m, 12, 0), put16(m, 14, 0))[0])),
            ("R3", with_(b, lambda m: put16(m, 8, 0))),
            ("R3", with_(b, lambda m: put16(m, 8, 11173))),
            ("R3", with_(jamoset.pack_jmap(self.build(self.all)), lambda m: put16(m, 8, 11171))),
            ("R4", bytes(b) + b"\0"),
            ("R4", bytes(b[:F - 1])),
            ("R4", bytes(jamoset.pack_jmap(self.build(self.all))) + b"\0"),
            ("R4", bytes(jamoset.pack_jmap(self.build(self.all)))[:-1]),
            ("R4", with_(bytes(b) + bytes(11), lambda m: m.__setitem__(6, m[6] | 4))),
            ("R4", with_(bytes(b) + bytes(fbv3), lambda m: m.__setitem__(6, m[6] | 4))),
            ("R4", with_(bytes(b) + bytes(fbadv), lambda m: m.__setitem__(6, m[6] | 4))),
            ("R4", fb_junk),
            ("R5", with_(b, lambda m: put16(m, 16, pi + pm + pf))),
            ("R6", with_(b, lambda m: m.__setitem__(1603, 1))),
            ("R6", with_(b, lambda m: m.__setitem__(206 + 1396, m[206 + 1396] | 0x10))),
            ("R6", rank),
            ("R6", ns),
            ("R7", i_over),
            ("R7", f256),
        ]
        # the dense NS rule and the FALLBACK flag with a valid fallback must still be accepted
        self.assertIsNotNone(jamoset.unpack_jmap(jamoset.pack_jmap(jm, bytes(v1))))
        for rule, blk in cases:
            with self.subTest(rule=rule, n=len(blk)):
                with self.assertRaisesRegex(ValueError, "^JMAP " + rule + " "):
                    jamoset.unpack_jmap(bytes(blk))
        self.assertIn("65534", self.refusal(fb_junk))
        self.assertEqual(self.refusal(f256), "JMAP R7 entry 0 field f = 256 is over 255")

    @staticmethod
    def refusal(blk):
        try:
            jamoset.unpack_jmap(bytes(blk))
        except ValueError as e:
            return str(e)
        return ""

    def test_pieces_and_compose(self):
        jm = self.build()
        for s in self.ks[::37] + self.ks[:5]:
            i, m, f = jm.entries[s]
            want = [jamoset.BLANK if not i else i - 1, jamoset.BLANK if not m else jm.pi + m - 1]
            if f:
                want.append(jm.pi + jm.pm + f - 1)
            self.assertEqual(jamoset.pieces_of(jm, 0xAC00 + s), want)
            self.assertEqual(jm.pieces(0xAC00 + s), want)
        miss = next(s for s in self.all if s not in jm.entries)
        self.assertIsNone(jamoset.pieces_of(jm, 0xAC00 + miss))
        self.assertIsNone(jamoset.pieces_of(jm, 0x41))
        delta = jm.pi + jm.pm + jm.pf
        fb = jamoset.unpack_jmap(jamoset.pack_jmap(jm, self.fallback(jm, 1)))
        self.assertEqual(jamoset.pieces_of(fb, 0xAC00 + miss),
                         [p if p == jamoset.BLANK else p + delta for p in jamoset.pieces_of(self.t, 0xAC00 + miss)])
        self.assertIsNotNone(fb.fallback)
        # entries decide the count and zero fields are blank
        lit = jamoset.Jmap(0, 2, 2, 2, {0: (1, 0, 0), 1: (0, 2, 2), 2: (2, 1, 0)})
        self.assertEqual(lit.pieces(0xAC00), [0, jamoset.BLANK])
        self.assertEqual(lit.pieces(0xAC01), [jamoset.BLANK, 3, 5])
        # advance 0 survives, and so does another
        self.assertEqual(jamoset.unpack_jmap(jamoset.pack_jmap(jm)).advance, 0)
        jm.advance = 9
        self.assertEqual(jamoset.unpack_jmap(jamoset.pack_jmap(jm)).advance, 9)
        # compose draws a JMAP face like a JSET one
        face = self.face
        t2, glyphs2 = jamoset.jmap_from_tables(self.t, self.ks, self.cp_glyphs)     # a face's own glyph dict
        self.assertEqual(glyphs2, jamoset.jmap_from_tables(self.t, self.ks, self.glyphs)[1])
        self.assertTrue(all(cp >= jamoset.PIECE_BASE for cp in glyphs2))

        class F:
            cell_w, cell_h, bpp = face.cell_w, face.cell_h, 1
            glyphs = glyphs2
        for s in self.ks[::101]:
            self.assertEqual(jamoset.compose(F, t2, 0xAC00 + s), jamoset.compose(face, self.t, 0xAC00 + s))

    def test_whole_face_glyph_dict(self):
        # the unfiltered glyph dict of a face has ASCII at 0x20..0x7E: pieces 32..126 must not pick those cells
        self.assertTrue(any(0x20 <= cp < 0x7F for cp in self.face.glyphs))
        jm, out = jamoset.jmap_from_tables(self.t, self.all, self.face.glyphs)
        jm2, out2 = jamoset.jmap_from_tables(self.t, self.all, self.cp_glyphs)
        self.assertEqual((jm.entries, jm.block_compat), (jm2.entries, jm2.block_compat))
        self.assertEqual(out, out2)
        self.assertTrue(all(cp >= jamoset.PIECE_BASE for cp in out))
        jm3, out3 = jamoset.jmap_from_tables(self.t, self.all, self.face.glyphs, (3, 2, 1))
        self.assertEqual(out3, jamoset.jmap_from_tables(self.t, self.all, self.cp_glyphs, (3, 2, 1))[1])

    def test_pack_fallback_keeps_numbers(self):
        for base in (0, 500, 3000):
            shifted = jamoset.shift_pieces(self.t, base)
            for version in (1, 2):
                with self.subTest(base=base, version=version):
                    blk = jamoset.pack_fallback(self.t, version, base)
                    u = jamoset.unpack(blk)
                    for attr in ("init_piece", "med_piece", "fin_piece", "compat"):
                        self.assertEqual(getattr(u, attr), getattr(shifted, attr), attr)
                    self.assertEqual(blk[4], version)
        # scrambled numbers (not contiguous in slot order) and a blank compat survive version 2
        rnd = random.Random(3)
        t = jamoset.shift_pieces(self.t, 0)
        for lst in (t.init_piece, t.med_piece, t.fin_piece):
            for n, p in enumerate(lst):
                if p != jamoset.BLANK:
                    lst[n] = rnd.randrange(0, 60000)
        t.compat = [jamoset.BLANK] * 51
        u = jamoset.unpack(jamoset.pack_fallback(t, 2))
        self.assertEqual((u.init_piece, u.med_piece, u.fin_piece), (t.init_piece, t.med_piece, t.fin_piece))
        with self.assertRaisesRegex(ValueError, "no set tables"):
            jamoset.pack_fallback(self.build(), 1)
        with self.assertRaisesRegex(ValueError, "not 1 or 2"):
            jamoset.pack_fallback(self.t, 3)
        with self.assertRaisesRegex(ValueError, "leaves 0..0xFFFE"):
            jamoset.pack_fallback(self.t, 1, 0xFFF0)
        # the shifted fallback is accepted, the unshifted one refused
        jm = self.build()
        jamoset.pack_jmap(jm, jamoset.pack_fallback(self.t, 2, jm.pi + jm.pm + jm.pf))
        with self.assertRaisesRegex(ValueError, "overlaps"):
            jamoset.pack_jmap(jm, jamoset.pack_fallback(self.t, 2))

    def test_miss_draws_the_fallback_pixels(self):
        jm, glyphs = jamoset.jmap_from_tables(self.t, self.ks, self.glyphs)
        delta = jm.pi + jm.pm + jm.pf
        block = jamoset.pack_jmap(jm, self.fallback(jm, 1))
        merged = dict(glyphs)
        for p, g in self.glyphs.items():
            self.assertNotIn(jamoset.PIECE_BASE + p + delta, merged)       # disjoint: nothing is overwritten
            merged[jamoset.PIECE_BASE + p + delta] = g
        face = self.face

        class F:
            cell_w, cell_h, bpp = face.cell_w, face.cell_h, 1
        F.glyphs = merged
        t3 = jamoset.unpack_jmap(block)
        misses = [s for s in self.all if s not in jm.entries][::331]
        self.assertTrue(misses)
        for s in misses + self.ks[::211]:
            self.assertEqual(jamoset.compose(F, t3, 0xAC00 + s), jamoset.compose(face, self.t, 0xAC00 + s), s)
        # a face holding the block parses (R8 incl. the fallback's pieces) ...
        data = jamoset.write_svfn(face.cell_w, face.cell_h, face.ascent,
                                  [(cp, g, face.cell_w, 0, face.cell_w) for cp, g in sorted(merged.items())], block, 0, 1)
        self.assertIsNotNone(jamoset.parse_svfn(data).jset)
        # ... and loses the jamo part when a fallback piece has no glyph
        del merged[jamoset.PIECE_BASE + max(jamoset.used_pieces(jamoset.shift_pieces(self.t, delta)))]
        data = jamoset.write_svfn(face.cell_w, face.cell_h, face.ascent,
                                  [(cp, g, face.cell_w, 0, face.cell_w) for cp, g in sorted(merged.items())], block, 0, 1)
        self.assertTrue(jamoset.parse_svfn(data).jset_bad)

    def test_fallback_overlap_refused(self):
        jm = self.build()
        for version in (1, 2):
            with self.subTest(version=version):
                with self.assertRaisesRegex(ValueError, r"^JMAP fallback piece \d+ overlaps the plane pieces"):
                    jamoset.pack_jmap(jm, jamoset.pack_v1(self.t) if version == 1 else jamoset.pack(self.t).block)
        # the compat list alone is enough
        t = jamoset.shift_pieces(self.t, jm.pi + jm.pm + jm.pf)
        t.compat[0] = 3
        with self.assertRaisesRegex(ValueError, "overlaps"):
            jamoset.pack_jmap(jm, jamoset.pack_v1(t))

    def test_set_tables_only_functions_refuse_a_jmap(self):
        jm = self.build()
        for fn in (jamoset.renumber, lambda j: jamoset.pack_v1(j), lambda j: jamoset.pack(j),
                   lambda j: jamoset.pack_jset(j, 1), lambda j: jamoset.pack_jset(j, "auto"),
                   lambda j: jamoset.shift_pieces(j, 1)):
            with self.assertRaisesRegex(ValueError, "^a JMAP block has no set tables"):
                fn(jm, {}) if fn is jamoset.renumber else fn(jm)

    def test_blank_compat_on_a_jmap(self):
        jm = self.build()
        k = next(k for k, c in enumerate(jm.block_compat) if c != jamoset.BLANK)
        jamoset.blank_compat(jm, {0x3131 + k})
        self.assertEqual(jm.block_compat[k], jamoset.BLANK)
        self.assertEqual(jm.compat[k], jamoset.BLANK)
        fbj = jamoset.unpack_jmap(jamoset.pack_jmap(self.build(), self.fallback(self.build(), 1)))
        self.assertNotEqual(fbj.fallback.compat[k], jamoset.BLANK)
        jamoset.blank_compat(fbj, {0x3131 + k})
        self.assertEqual((fbj.block_compat[k], fbj.fallback.compat[k], fbj.compat[k]), (jamoset.BLANK,) * 3)
        # the CLI path: a face with a whole glyph for a compat jamo
        glyphs = jamoset.jmap_from_tables(self.t, self.ks, self.glyphs)[1]
        face = self.face
        cells = dict(glyphs)
        cells[0x3131 + k] = bytes([0xFF]) * len(next(iter(glyphs.values())))
        data = jamoset.write_svfn(face.cell_w, face.cell_h, face.ascent,
                                  [(cp, g, face.cell_w, 0, face.cell_w) for cp, g in sorted(cells.items())],
                                  jamoset.pack_jmap(self.build()), 0, 1)
        out = jamoset.blank_whole_compat(data)
        f = jamoset.parse_svfn(out)
        self.assertEqual(jamoset.unpack(f.jset).compat[k], jamoset.BLANK)
        self.assertEqual(f.glyphs, jamoset.parse_svfn(data).glyphs)

    def test_blank_whole_compat_with_a_fallback(self):
        k = next(k for k, c in enumerate(self.t.compat) if c != jamoset.BLANK)
        for version in (1, 2):
            with self.subTest(version=version):
                jm, glyphs = jamoset.jmap_from_tables(self.t, self.ks, self.glyphs)
                delta = jm.pi + jm.pm + jm.pf
                cells = dict(glyphs)
                cells.update({jamoset.PIECE_BASE + p + delta: g for p, g in self.glyphs.items()})
                cells[0x3131 + k] = bytes([0xFF]) * len(next(iter(glyphs.values())))
                face = self.face
                data = jamoset.write_svfn(face.cell_w, face.cell_h, face.ascent,
                                          [(cp, g, face.cell_w, 0, face.cell_w) for cp, g in sorted(cells.items())],
                                          jamoset.pack_jmap(jm, self.fallback(jm, version)), 0, 1)
                before = jamoset.unpack(jamoset.parse_svfn(data).jset)
                self.assertNotEqual(before.compat[k], jamoset.BLANK)
                out = jamoset.parse_svfn(jamoset.blank_whole_compat(data))
                self.assertIsNotNone(out.jset)
                after = jamoset.unpack(out.jset)
                self.assertEqual(after.compat[k], jamoset.BLANK)
                self.assertEqual([c for n, c in enumerate(after.compat) if n != k],
                                 [c for n, c in enumerate(before.compat) if n != k])
                self.assertEqual(after.fallback_version, version)
                self.assertEqual(after.entries, before.entries)
                for cp in range(0xAC00, 0xD7A4, 97):
                    self.assertEqual(after.pieces(cp), before.pieces(cp))

    def test_sparse_with_all_syllables_is_valid(self):
        # PR-21: an exception list may cover everything
        b = bytearray(b"JSET" + struct.pack("<HBBHHHH", 3, 2, 0, 11172, 1, 1, 1))
        b += struct.pack("<51H", *[0xFFFF] * 51)
        b += struct.pack("<44H", *[k * 256 for k in range(44)])
        b += bytes([0xFF]) * 1396 + bytes([0x0F]) + b"\0"
        b += bytes((1, 1, 1)) * 11172
        self.assertEqual(len(b), jamoset.jmap_size(11172, False, True))
        jm = jamoset.unpack_jmap(bytes(b))
        self.assertEqual(len(jm.entries), 11172)
        bad = bytearray(b)
        bad[206 + 1396] = 0x1F
        with self.assertRaisesRegex(ValueError, "^JMAP R6 "):
            jamoset.unpack_jmap(bytes(bad))

    def test_pack_refusals(self):
        one = {0: (1, 1, 1)}
        for name, jm in (("PI over 2047", jamoset.Jmap(0, 2048, 1, 1, one)),
                         ("PM over 2047", jamoset.Jmap(0, 1, 2048, 1, one)),
                         ("PF over 1023", jamoset.Jmap(0, 1, 1, 1024, one)),
                         ("no pieces", jamoset.Jmap(0, 0, 0, 0, {0: (0, 0, 0)})),
                         ("no entries", jamoset.Jmap(0, 1, 1, 1, {})),
                         ("entry over a count", jamoset.Jmap(0, 1, 1, 1, {0: (2, 1, 1)})),
                         ("syllable out of range", jamoset.Jmap(0, 1, 1, 1, {11172: (1, 1, 1)})),
                         ("compat over", jamoset.Jmap(0, 1, 1, 1, one, [3] * 51)),
                         ("compat negative", jamoset.Jmap(0, 1, 1, 1, one, [-1] * 51)),
                         ("dense with a missing syllable", jamoset.Jmap(0, 1, 1, 1, {s: (1, 1, 1) for s in
                                                                                    list(range(11171)) + [11172]}))):
            with self.subTest(name):
                with self.assertRaisesRegex(ValueError, "^JMAP pack"):
                    jamoset.pack_jmap(jm)
        # the 65,534 cap counts the fallback: no narrow v1/v2 block is big enough to reach it, so fake the check
        jm = jamoset.Jmap(0, 300, 1, 1, {s: (1, 1, 1) for s in range(11172)})
        self.assertEqual(len(jamoset.pack_jmap(jm)), 44806)
        junk = bytes(65535 - 44806)
        with mock.patch.object(jamoset, "_jmap_fallback_check", return_value=jamoset.Tables(1, 1, 1, 1, 1)):
            with self.assertRaisesRegex(ValueError, "^JMAP pack: 65535 bytes is over the region limit 65534"):
                jamoset.pack_jmap(jm, junk)
            self.assertEqual(len(jamoset.pack_jmap(jm, junk[:-1])), 65534)

    def test_compat(self):
        jm = self.build()
        self.assertEqual(len(jm.block_compat), 51)
        fb = jamoset.unpack_jmap(jamoset.pack_jmap(jm, self.fallback(jm, 1)))
        fb.block_compat[3] = jamoset.BLANK
        self.assertEqual(fb.compat[3], fb.fallback.compat[3])
        self.assertEqual(fb.compat[4], fb.block_compat[4])
        plain = jamoset.Jmap(0, 1, 1, 1, {0: (1, 1, 0)})
        self.assertEqual(plain.compat, [jamoset.BLANK] * 51)

    def test_used_pieces(self):
        jm = self.build()
        used = jamoset.used_pieces(jm)
        self.assertEqual(used, sorted(set(used)))
        self.assertLess(max(used), jm.pi + jm.pm + jm.pf)

    def test_jset_line_v3(self):
        jm = self.build()
        glyphs = jamoset.jmap_from_tables(self.t, self.ks, self.glyphs)[1]
        face = self.face
        data = jamoset.write_svfn(face.cell_w, face.cell_h, face.ascent,
                                  [(cp, g, face.cell_w, 0, face.cell_w) for cp, g in sorted(glyphs.items())],
                                  jamoset.pack_jmap(jm), 0, face.bpp)
        f = jamoset.parse_svfn(data)
        self.assertIsNotNone(f.jset)
        self.assertEqual(jamoset.jset_line(data), "jset=v3 jmap=8654 ns=2350 fallback=none")
        delta = jm.pi + jm.pm + jm.pf
        both = dict(glyphs)
        both.update({jamoset.PIECE_BASE + p + delta: g for p, g in self.glyphs.items()})
        fbdata = jamoset.write_svfn(face.cell_w, face.cell_h, face.ascent,
                                    [(cp, g, face.cell_w, 0, face.cell_w) for cp, g in sorted(both.items())],
                                    jamoset.pack_jmap(jm, self.fallback(jm, 1)), 0, face.bpp)
        self.assertTrue(jamoset.jset_line(fbdata).endswith("fallback=v1"), jamoset.jset_line(fbdata))


class JmapList(unittest.TestCase):
    """JSET version 3 LIST mode (flag 0x08): NS entries of 8 bytes over a shared piece pool (spec rules R1', L2, L3, R4, L6)."""

    ROOT = os.path.dirname(HERE)
    FACE = os.path.join(ROOT, "svf", "dos", "NEODG16G.SVF")

    @classmethod
    def setUpClass(cls):
        with open(cls.FACE, "rb") as fh:
            f = jamoset.parse_svfn(fh.read())
        cls.face = f
        cls.t = jamoset.unpack(f.jset)
        cls.cells = {cp: g for cp, g in f.glyphs.items() if cp >= jamoset.PIECE_BASE}
        cls.used = jamoset.used_pieces(cls.t)

    def entries(self, ns):
        """ns keys with entries naming the fallback tables' own pieces (those of another syllable): some with a final,
        some without, and piece 0 in the first."""
        keys = [5] if ns == 1 else sorted(random.Random(ns).sample(range(11172), ns))
        out = {}
        for n, s in enumerate(keys):
            p = jamoset.pieces_of(self.t, 0xAC00 + (s * 7 + 3) % 11172)
            out[s] = (p[0], p[1], p[2] if len(p) == 3 and n % 3 else jamoset.BLANK)
        out[keys[0]] = (0, self.used[1], jamoset.BLANK)
        return out

    def make(self, ns, version):
        """(Jmap, block) of a LIST of ns entries; version 0 = no fallback, else the face's tables as the fallback."""
        jm = jamoset.Jmap(self.t.advance, entries=self.entries(ns), list_mode=True)
        k = next(k for k, c in enumerate(self.t.compat) if c != jamoset.BLANK)
        jm.block_compat[k] = self.used[2]
        if version:
            jm.fallback_block = jamoset.pack_fallback(self.t, version, 0)
            jm.fallback = self.t
        return jm, jamoset.pack_jmap(jm)

    def face_bytes(self, block, extra=()):
        face = self.face
        cells = dict(self.cells)
        cells.update(dict(extra))
        return jamoset.write_svfn(face.cell_w, face.cell_h, face.ascent,
                                  [(cp, g, face.cell_w, 0, face.cell_w) for cp, g in sorted(cells.items())], block, 0, 1)

    def test_list_size(self):
        self.assertEqual(jamoset.jmap_size(36, False, False, list_mode=True), 406)
        self.assertEqual(jamoset.jmap_size(255, False, False, 0, True), 2158)
        self.assertEqual(jamoset.jmap_size(1, False, False, 100, True), 226)
        self.assertEqual((jamoset.JMAP_FLAG_LIST, jamoset.JMAP_LIST_MAX, jamoset.JMAP_LIST_ENTRIES,
                          jamoset.JMAP_LIST_ENTRY), (0x08, 255, 118, 8))

    def test_list_round_trip(self):
        for version, ns in ((0, 1), (1, 38), (2, 255)):
            with self.subTest(version=version, ns=ns):
                jm, b = self.make(ns, version)
                back = jamoset.unpack_jmap(b)
                self.assertTrue(back.list_mode)
                self.assertEqual(back.entries, jm.entries)
                self.assertEqual(back.block_compat, jm.block_compat)
                self.assertEqual(jamoset.pack_jmap(back), b)
                self.assertEqual(b[6] & 0x08, 0x08)
                self.assertEqual(bool(b[6] & 0x04), bool(version))
                self.assertEqual(b[6] & 0x03, 0)
                self.assertEqual(b[9], 0)
                self.assertEqual(b[10:16], bytes(6))
                fbl = len(jm.fallback_block) if version else 0
                self.assertEqual(len(b), jamoset.jmap_size(ns, False, False, fbl, True))
                self.assertEqual(jamoset.unpack(b).entries, jm.entries)

    def test_list_pieces(self):
        B = jamoset.BLANK
        fb = self.t
        jm = jamoset.Jmap(self.t.advance, entries={0: (3, 4, B), 1: (3, 4, 5), 2: (3, B, B)}, fallback=fb, list_mode=True)
        self.assertEqual(jm.pieces(0xAC00), [3, 4])
        self.assertEqual(jm.pieces(0xAC01), [3, 4, 5])
        self.assertEqual(jm.pieces(0xAC02), [3, B])
        self.assertEqual(jm.pieces(0xAC03), jamoset.pieces_of(fb, 0xAC03))
        self.assertEqual(jamoset.pieces_of(jm, 0xAC03), jamoset.pieces_of(fb, 0xAC03))
        self.assertIsNone(jm.pieces(0x3131))
        nofb = jamoset.Jmap(self.t.advance, entries={0: (3, 4, B)}, list_mode=True)
        self.assertIsNone(nofb.pieces(0xAC03))
        self.assertEqual(nofb.pieces(0xAC00), [3, 4])
        # PL-8: the property lists are the sorted distinct non-blank fields plus the fallback's own
        self.assertEqual(jm.init_piece, [3] + fb.init_piece)
        self.assertEqual(jm.med_piece, [4] + fb.med_piece)
        self.assertEqual(jm.fin_piece, [5] + fb.fin_piece)
        self.assertEqual(nofb.init_piece, [3])
        self.assertEqual(nofb.fin_piece, [])

    def test_list_compat(self):
        jm, b = self.make(4, 1)
        jm = jamoset.unpack_jmap(b)
        k = next(k for k, c in enumerate(jm.block_compat) if c != jamoset.BLANK)
        self.assertEqual(jm.compat[k], jm.block_compat[k])
        other = next(j for j, c in enumerate(jm.block_compat) if c == jamoset.BLANK and jm.fallback.compat[j] != jamoset.BLANK)
        self.assertEqual(jm.compat[other], jm.fallback.compat[other])
        nofb = jamoset.unpack_jmap(self.make(4, 0)[1])
        self.assertEqual(nofb.compat[other], jamoset.BLANK)

    def test_list_piece_zero(self):
        jm = jamoset.Jmap(0, entries={7: (0, 5, jamoset.BLANK)}, list_mode=True)
        self.assertEqual(jm.pieces(0xAC07), [0, 5])
        self.assertEqual(jamoset.unpack_jmap(jamoset.pack_jmap(jm)).pieces(0xAC07), [0, 5])
        self.assertEqual(jm.init_piece, [0])
        B = jamoset.BLANK
        jm = jamoset.Jmap(0, entries={8: (3, 4, 0), 9: (0, 0, B)}, list_mode=True)
        self.assertEqual((jm.pieces(0xAC08), jm.pieces(0xAC09)), ([3, 4, 0], [0, 0]))
        back = jamoset.unpack_jmap(jamoset.pack_jmap(jm))
        self.assertEqual((back.pieces(0xAC08), back.pieces(0xAC09)), ([3, 4, 0], [0, 0]))

    def test_list_compose_matches(self):
        jm, b = self.make(255, 2)
        jm = jamoset.unpack_jmap(b)
        face = self.face
        for k, c in enumerate(jm.block_compat):
            self.assertEqual(jm.compat[k], c if c != jamoset.BLANK else self.t.compat[k], k)
        for cp in range(0xAC00, 0xD7A4):
            s = cp - 0xAC00
            if s in jm.entries:
                want = bytearray(len(next(iter(self.cells.values()))))
                for n in jm.pieces(cp):
                    if n != jamoset.BLANK:
                        for k, v in enumerate(face.glyphs[jamoset.PIECE_BASE + n]):
                            want[k] |= v
                self.assertEqual(jamoset.compose(face, jm, cp), bytes(want), cp)
            else:
                self.assertEqual(jamoset.compose(face, jm, cp), jamoset.compose(face, self.t, cp), cp)

    def test_list_pack_refusals(self):
        B = jamoset.BLANK
        ok = (1, 2, B)

        def lst(entries, **kw):
            return jamoset.Jmap(0, entries=entries, list_mode=True, **kw)
        with self.assertRaisesRegex(ValueError, r"over 255: use SPARSE \(2372 B"):
            jamoset.pack_jmap(lst({s: ok for s in range(256)}))
        with self.assertRaisesRegex(ValueError, "no entries"):
            jamoset.pack_jmap(lst({}))
        jm = lst({0: ok})
        jm.pi = 1
        with self.assertRaisesRegex(ValueError, "LIST.*planes"):
            jamoset.pack_jmap(jm)
        with self.assertRaisesRegex(ValueError, "11171"):
            jamoset.pack_jmap(lst({11172: ok}))
        with self.assertRaisesRegex(ValueError, "out of range"):
            jamoset.pack_jmap(lst({0: (0x10000, 1, B)}))
        jm = lst({0: ok})
        jm.block_compat[0] = 0x10000
        with self.assertRaisesRegex(ValueError, "out of range"):
            jamoset.pack_jmap(jm)
        # overlap with the fallback's pieces is not refused
        jm = lst({0: (self.used[0], self.used[1], B)}, fallback=self.t)
        jm.fallback_block = jamoset.pack_fallback(self.t, 1, 0)
        self.assertEqual(jamoset.unpack_jmap(jamoset.pack_jmap(jm)).entries, jm.entries)

    def test_list_unpack_rules(self):
        _, nofb = self.make(5, 0)
        _, withfb = self.make(5, 1)
        F = 118 + 8 * 5

        def put16(m, off, v):
            struct.pack_into("<H", m, off, v)
            return bytes(m)

        def key(m, j, v):
            return put16(m, 118 + 8 * j, v)

        def with_(base, fn):
            m = bytearray(base)
            r = fn(m)
            return bytes(m) if r is None else r

        def flags(v):
            return lambda m: m.__setitem__(6, v)
        keys = [struct.unpack_from("<H", withfb, 118 + 8 * j)[0] for j in range(5)]
        cases = [
            ("length 117", nofb[:117], r"^JMAP R1"),
            ("flags 0x0a", with_(nofb, flags(0x0A)), r"^JMAP R1 flags 0x0a set reserved bits"),
            ("flags 0x09", with_(nofb, flags(0x09)), r"^JMAP R1"),
            ("flags 0x18", with_(nofb, flags(0x18)), r"^JMAP R1"),
            ("PI 1", with_(nofb, lambda m: put16(m, 10, 1)), r"^JMAP L2"),
            ("PF 1", with_(nofb, lambda m: put16(m, 14, 1)), r"^JMAP L2"),
            ("NS 0", with_(nofb, lambda m: put16(m, 8, 0)), r"^JMAP L3"),
            ("NS 256", with_(nofb, lambda m: put16(m, 8, 256)), r"^JMAP L3"),
            ("length F+1", nofb + b"\0", r"^JMAP R4"),
            ("region F+11", withfb[:F + 11], r"^JMAP R4"),
            ("fallback v3", with_(withfb, lambda m: put16(m, F + 4, 3)), r"^JMAP R4"),
            ("fallback advance", with_(withfb, lambda m: m.__setitem__(F + 11, m[F + 11] + 1)), r"^JMAP R4"),
            ("equal keys", with_(nofb, lambda m: key(m, 1, keys[0])), r"^JMAP L6"),
            ("descending keys", with_(nofb, lambda m: (key(m, 1, keys[2]), key(m, 2, keys[1]))[-1]), r"^JMAP L6"),
            ("L6 runs after R4", with_(nofb, lambda m: (key(m, 1, keys[2]), key(m, 2, keys[1]))[-1]) + b"\0", r"^JMAP R4"),
            ("last key 11172", with_(nofb, lambda m: key(m, 4, 11172)), r"^JMAP L6"),
        ]
        jamoset.unpack_jmap(nofb)
        jamoset.unpack_jmap(withfb)
        for name, data, rx in cases:
            with self.subTest(name):
                with self.assertRaisesRegex(ValueError, rx):
                    jamoset.unpack_jmap(data)

    def test_list_l3_upper_bound(self):
        """L3 alone refuses NS = 256: a self-consistent block (256 increasing keys, F = 2166, length to match), so R4 passes."""
        B = jamoset.BLANK
        for version in (0, 1):
            with self.subTest(version=version):
                jm = jamoset.Jmap(self.t.advance, entries={s: (1, 2, B) for s in range(255)}, list_mode=True)
                if version:
                    jm.fallback_block = jamoset.pack_fallback(self.t, version, 0)
                    jm.fallback = self.t
                b = jamoset.pack_jmap(jm)
                F = 118 + 8 * 255
                big = bytearray(b[:F]) + struct.pack("<4H", 255, 1, 2, B) + b[F:]
                struct.pack_into("<H", big, 8, 256)
                self.assertEqual(118 + 8 * 256, 2166)
                with self.assertRaisesRegex(ValueError, r"^JMAP L3 NS 256 "):
                    jamoset.unpack_jmap(bytes(big))
                struct.pack_into("<H", big, 8, 255)       # the same bytes with NS 255 are R4's (length), proving the layout
                with self.assertRaisesRegex(ValueError, r"^JMAP R4"):
                    jamoset.unpack_jmap(bytes(big))

    def test_list_usable_rule(self):
        jm, b = self.make(6, 1)
        self.assertIsNotNone(jamoset.parse_svfn(self.face_bytes(b)).jset)
        bad = jamoset.Jmap(self.t.advance, entries={**jm.entries, 11000: (3000, 3001, jamoset.BLANK)}, list_mode=True)
        blk = jamoset.pack_jmap(bad)
        jamoset.unpack_jmap(blk)
        self.assertTrue(jamoset.parse_svfn(self.face_bytes(blk)).jset_bad)
        bad = jamoset.Jmap(self.t.advance, entries=dict(jm.entries), list_mode=True)
        bad.block_compat[0] = 3000
        blk = jamoset.pack_jmap(bad)
        jamoset.unpack_jmap(blk)
        self.assertTrue(jamoset.parse_svfn(self.face_bytes(blk)).jset_bad)

    def test_list_jset_line(self):
        _, b = self.make(36, 0)
        self.assertTrue(jamoset.jset_line(self.face_bytes(b)).startswith("jset=v3 jmap=406 ns=36 list=1 fallback=none"))
        jm, b = self.make(36, 1)
        line = jamoset.jset_line(self.face_bytes(b))
        self.assertTrue(line.startswith(f"jset=v3 jmap={len(b)} ns=36 list=1 fallback=v1"), line)
        self.assertEqual(len(b), 406 + len(jm.fallback_block))

    def test_list_blank_compat(self):
        jm, b = self.make(20, 2)
        jm = jamoset.unpack_jmap(b)
        k = next(k for k, c in enumerate(jm.block_compat) if c != jamoset.BLANK)
        self.assertNotEqual(jm.fallback.compat[k], jamoset.BLANK)
        before = {cp: jamoset.pieces_of(jm, cp) for cp in range(0xAC00, 0xD7A4, 13)}
        old = jm.fallback_block
        jamoset.blank_compat(jm, {0x3131 + k})
        self.assertEqual((jm.block_compat[k], jm.fallback.compat[k], jm.compat[k]), (jamoset.BLANK,) * 3)
        self.assertNotEqual(jm.fallback_block, old)
        fb = jamoset.unpack(jm.fallback_block)
        self.assertEqual(fb.compat[k], jamoset.BLANK)
        self.assertEqual(jm.fallback_version, 2)
        for cp, want in before.items():
            self.assertEqual(jamoset.pieces_of(jm, cp), want)
            self.assertEqual(jamoset.pieces_of(fb, cp), jamoset.pieces_of(self.t, cp))
        self.assertEqual(jamoset.unpack_jmap(jamoset.pack_jmap(jm)).compat[k], jamoset.BLANK)


class JmapListBuild(unittest.TestCase):
    """jamoset.jmap_list: a LIST over the face's own piece pool, the source JSET kept as the fallback (PL-5, PL-9, PL-10)."""

    ROOT = os.path.dirname(HERE)
    FACE = os.path.join(ROOT, "svf", "dos", "NEODG16G.SVF")

    @classmethod
    def setUpClass(cls):
        with open(cls.FACE, "rb") as fh:
            cls.face = jamoset.parse_svfn(fh.read())
        cls.t = jamoset.unpack(cls.face.jset)
        cls.stride = ((cls.face.cell_w * cls.face.bpp + 7) // 8) * cls.face.cell_h

    def cell(self, seed):
        return bytes(random.Random(seed).randrange(256) for _ in range(self.stride))

    def source(self, t, glyphs, block, advance_cells=None):
        """A parsed face with the pieces @p glyphs ({cp: cell}) and the JSET @p block."""
        face = self.face
        cells = {cp: g for cp, g in face.glyphs.items() if cp < jamoset.PIECE_BASE}
        cells.update(glyphs)
        data = jamoset.write_svfn(face.cell_w, face.cell_h, face.ascent,
                                  [(cp, g, face.cell_w, 0, face.cell_w) for cp, g in sorted(cells.items())], block, 0, 1)
        return jamoset.parse_svfn(data)

    def test_jmap_list_numbering(self):
        f = self.face
        top = max(cp for cp in f.glyphs if cp >= jamoset.PIECE_BASE)
        self.assertEqual(top, jamoset.PIECE_BASE + 182)
        c900, c30, ck = self.cell(1), self.cell(2), self.cell(3)
        jm, new = jamoset.jmap_list(f, {900: c900, 30: c30}, compat={3: ck})
        B = jamoset.BLANK
        self.assertEqual(new, {jamoset.PIECE_BASE + 183: c30, jamoset.PIECE_BASE + 184: c900,
                               jamoset.PIECE_BASE + 185: ck})
        self.assertEqual(jm.entries, {30: (183, B, B), 900: (184, B, B)})
        self.assertEqual(jm.block_compat[3], 185)
        self.assertEqual([c for k, c in enumerate(jm.block_compat) if k != 3], [B] * 50)
        self.assertTrue(jm.list_mode)

    def test_jmap_list_unreferenced_top(self):
        f = self.face
        glyphs = {cp: g for cp, g in f.glyphs.items() if cp >= jamoset.PIECE_BASE}
        glyphs[jamoset.PIECE_BASE + 700] = self.cell(4)           # in the cmap, named by no table
        src = self.source(self.t, glyphs, f.jset)
        jm, new = jamoset.jmap_list(src, {7: self.cell(5)})
        self.assertEqual(list(new), [jamoset.PIECE_BASE + 701])
        self.assertEqual(jm.entries[7][0], 701)
        glyphs[0xFFFFE] = self.cell(6)
        src = self.source(self.t, glyphs, f.jset)
        with self.assertRaisesRegex(ValueError, r"^jmap_list: no free piece number above U\+FFFFE$"):
            jamoset.jmap_list(src, {7: self.cell(5)})
        # pieces named by number need no new glyph
        jm, new = jamoset.jmap_list(src, {7: [1, 2]})
        self.assertEqual((new, jm.entries), ({}, {7: (1, 2, jamoset.BLANK)}))

    def test_jmap_list_fallback_verbatim(self):
        t = self.t
        used = jamoset.used_pieces(t)
        glyphs = {cp: g for cp, g in self.face.glyphs.items() if cp >= jamoset.PIECE_BASE}
        for v in (1, 2):
            with self.subTest(version=v):
                block = jamoset.pack_fallback(t, v, 0)
                src = self.source(t, glyphs, block)
                self.assertEqual(src.jset, block)
                jm, _ = jamoset.jmap_list(src, {3: [used[0], used[1]]})
                self.assertEqual(jm.fallback_block, block)
                self.assertEqual(jm.fallback_version, v)
                b = jamoset.pack_jmap(jm, jm.fallback_block)
                self.assertTrue(b.endswith(block))
                self.assertEqual(jamoset.unpack_jmap(b).fallback_block, block)

    def test_jmap_list_advance(self):
        t = jamoset.unpack(self.face.jset)
        t.advance = 16
        glyphs = {cp: g for cp, g in self.face.glyphs.items() if cp >= jamoset.PIECE_BASE}
        src = self.source(t, glyphs, jamoset.pack_v1(t))
        jm, _ = jamoset.jmap_list(src, {3: [0, 1]}, advance=9)         # ignored with a fallback
        b = jamoset.pack_jmap(jm, jm.fallback_block)
        self.assertEqual(b[7], 16)
        self.assertEqual(b[118 + 8 * 1 + 11], 16)
        self.assertEqual(jamoset.pack_jmap(jamoset.jmap_list(self.face, {3: [0, 1]})[0],
                                           self.face.jset)[7], 0)
        jm, _ = jamoset.jmap_list(self.face, {3: [0, 1]}, fallback=False, advance=9)
        self.assertEqual((jm.advance, jm.fallback, jm.fallback_block), (9, None, None))
        self.assertEqual(jamoset.pack_jmap(jm)[7], 9)

    def test_jmap_list_reencode_keeps_numbers(self):
        t1 = self.t
        used = jamoset.used_pieces(t1)
        order = list(range(len(used)))
        random.Random(7).shuffle(order)
        piece_map = {p: n for p, n in zip(used, order)}
        glyphs = {cp: g for cp, g in self.face.glyphs.items() if cp >= jamoset.PIECE_BASE}
        t2 = jamoset.renumber(t1, piece_map)
        g2 = jamoset.renumber_glyphs(glyphs, piece_map)
        self.assertNotEqual(jamoset.used_pieces(t2)[:3], [piece_map[p] for p in used[:3]])
        src = self.source(t2, g2, jamoset.pack_v1(t2))
        own = jamoset.pieces_of(t2, 0xAC00 + 5)
        jm, _ = jamoset.jmap_list(src, {5: own[:2]}, jset_version=2)
        self.assertEqual(jm.fallback_version, 2)
        self.assertEqual(struct.unpack_from("<H", jm.fallback_block, 4)[0], 2)
        self.assertEqual(jm.fallback.compat, t2.compat)
        ref = self.source(t1, glyphs, jamoset.pack_v1(t1))
        self.assertEqual(jm.compat, [p if p == jamoset.BLANK else piece_map[p] for p in t1.compat])
        for cp in range(0xAC00, 0xD7A4):
            if cp != 0xAC05:                         # the one exception (two of its pieces)
                self.assertEqual(jamoset.compose(src, jm, cp), jamoset.compose(ref, t1, cp), cp)

    def test_jmap_list_refusals(self):
        f = self.face
        ok = [1, 2]
        with self.assertRaisesRegex(ValueError, r"256 LIST entries is over 255: use SPARSE \(2372 B"):
            jamoset.jmap_list(f, {s: ok for s in range(256)})
        self.assertEqual(len(jamoset.jmap_list(f, {s: ok for s in range(255)})[0].entries), 255)
        glyphs = {cp: g for cp, g in f.glyphs.items() if cp >= jamoset.PIECE_BASE}
        v3 = jamoset.pack_jmap(jamoset.jmap_list(f, {3: ok})[0], f.jset)
        src = self.source(self.t, glyphs, v3)
        with self.assertRaisesRegex(ValueError, "already has a JSET version 3 block; start from the plain face"):
            jamoset.jmap_list(src, {3: ok})
        plain = self.source(self.t, glyphs, b"")
        self.assertIsNone(plain.jset)
        with self.assertRaisesRegex(ValueError, "no usable JSET block; start from a jamo face whose JSET parses"):
            jamoset.jmap_list(plain, {3: ok})
        jm, _ = jamoset.jmap_list(plain, {3: ok}, fallback=False)
        self.assertEqual((jm.entries, jm.fallback), ({3: (1, 2, jamoset.BLANK)}, None))
        with self.assertRaises(ValueError):
            jamoset.jmap_list(f, {11172: ok})
        with self.assertRaises(ValueError):
            jamoset.jmap_list(f, {3: ok}, compat={51: 1})
        with self.assertRaises(ValueError):
            jamoset.jmap_list(f, {3: b"\0"})                         # not a cell
        with self.assertRaises(ValueError):
            jamoset.jmap_list(f, {3: [1, 2, 3, 4]})
        with self.assertRaises(ValueError):
            jamoset.jmap_list(f, {3: 5})                              # neither a cell nor a list
        with self.assertRaisesRegex(ValueError, "piece 5000 has no glyph U\\+F1388"):
            jamoset.jmap_list(f, {3: [1, 5000]})
        with self.assertRaisesRegex(ValueError, "version 3"):
            jamoset.jmap_list(src, {3: ok}, fallback=False)
        with self.assertRaisesRegex(ValueError, "jset_version needs a fallback"):
            jamoset.jmap_list(f, {3: ok}, jset_version=2, fallback=False)

    def test_jmap_list_truncated_jset(self):
        """A truncated JSET block never reaches jmap_list as f.jset: parse_svfn drops it, and jmap_list says so cleanly."""
        f = self.face
        for blob in (b"JSET", b"JSET\x02\x00", b"JSET\x02\x00\x01\x01", b"JSET\x03\x00\x08" + bytes(5)):
            with self.subTest(blob=blob):
                src = self.source(self.t, {cp: g for cp, g in f.glyphs.items() if cp >= jamoset.PIECE_BASE}, blob)
                self.assertIsNone(src.jset)
                with self.assertRaisesRegex(ValueError, "no usable JSET block"):
                    jamoset.jmap_list(src, {3: [1, 2]})

    def test_jmap_list_blank_fields(self):
        B = jamoset.BLANK
        f = self.face
        jm, new = jamoset.jmap_list(f, {1: [B, 4], 2: [B, B, B], 3: [3, B, 5]}, compat={4: B, 5: 7})
        self.assertEqual(jm.entries, {1: (B, 4, B), 2: (B, B, B), 3: (3, B, 5)})
        self.assertEqual((new, jm.block_compat[4], jm.block_compat[5]), ({}, B, 7))
        jamoset.pack_jmap(jm, jm.fallback_block)


class JsetBig(unittest.TestCase):
    """Task 14: the JSET limit lift (19 x 28 classes, 128/128/64 sets) behind --jset-big (PR-16: readers accept it always,
    writers refuse it without the flag)."""

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    BIG = (19, 28, 128, 128, 64)

    @staticmethod
    def limits_tables(lc, tc, ni, nm, nf):
        """lc x tc classes and ni/nm/nf sets, every class, set and piece used (copy of test_c_renderer.limits_tables)."""
        t = jamoset.Tables(lc, tc, ni, nm, nf)
        t.lead_class = [L % lc for L in range(19)]
        t.tail_class = [0] + [1 + (T - 1) % (tc - 1) for T in range(1, 28)]
        n = lc * 21 * tc
        t.init_set, t.med_set, t.fin_set = [c % ni for c in range(n)], [c % nm for c in range(n)], [c % nf for c in range(n)]
        t.init_piece = [1 + i for i in range(ni * 19)]
        t.med_piece = [1000 + i for i in range(nm * 21)]
        t.fin_piece = [2000 + i for i in range(nf * 27)]
        return t

    def test_big_sizes(self):
        self.assertEqual(jamoset._jset_size_v1(*self.BIG), 47373)
        self.assertEqual(jamoset.jset_size(*self.BIG), 29708)
        self.assertEqual(jamoset.jset_size(*self.BIG, na=6848), 45068)
        self.assertEqual(jamoset.JSET_LIMITS, {"std": (12, 12, 32, 24, 16), "big": (19, 28, 128, 128, 64)})
        self.assertEqual((jamoset.class_limits(False), jamoset.class_limits(True)), ((12, 12), (19, 28)))

    def test_pack_refuses_without_big(self):
        for counts in ((13, 12, 32, 24, 16), (12, 12, 33, 24, 16)):
            t = self.limits_tables(*counts)
            for fn in (jamoset.pack, jamoset.pack_v1):
                with self.assertRaisesRegex(ValueError, "--jset-big"):
                    fn(t)
            self.assertTrue(jamoset.needs_big(t))
            for blk in (jamoset.pack(t, big=True).block, jamoset.pack_v1(t, big=True)):
                u = jamoset.unpack(blk)
                self.assertEqual((u.lc, u.tc, u.ni, u.nm, u.nf), counts)
        self.assertFalse(jamoset.needs_big(self.limits_tables(12, 12, 32, 24, 16)))

    def test_exact_narrow_edge_refused(self):
        for counts in ((13, 12, 32, 24, 16), (12, 13, 32, 24, 16), (12, 12, 33, 24, 16), (12, 12, 32, 25, 16),
                       (12, 12, 32, 24, 17)):
            with self.assertRaisesRegex(ValueError, r"is not 1\.\.\d+ \(--jset-big allows 19 x 28 classes, 128/128/64 sets\)"):
                jamoset.pack_v1(self.limits_tables(*counts))

    def test_big_limits_round_trip_and_compose(self):
        t = self.limits_tables(*self.BIG)
        for version in (1, 2):
            with self.subTest(version=version):
                packed = jamoset.pack_jset(t, version, big=True)
                u = jamoset.unpack(packed.block)
                self.assertEqual(len(packed.block), jamoset._jset_size_v1(*self.BIG) if version == 1
                                 else len(jamoset.pack(t, True).block))
                for cp in range(0xAC00, 0xD7A4):
                    want = [packed.piece_map[p] if version == 2 else p for p in jamoset.pieces_of(t, cp)]
                    self.assertEqual(jamoset.pieces_of(u, cp), want, hex(cp))
                # and really compose, through a face written by write_svfn: contiguous pieces, each a distinct bitmap
                used = jamoset.used_pieces(t)
                tt = jamoset.renumber(t, {p: n for n, p in enumerate(used)})
                pk = jamoset.pack_jset(tt, version, big=True)
                bits = lambda p: bytes([p & 255, p >> 8 & 255, (p * 7) & 255, 1]) + bytes(12)
                glyphs = [(jamoset.PIECE_BASE + n, bits(n), 8, 0, 8) for n in range(len(used))]
                face = jamoset.write_svfn(8, 16, 14, jamoset.renumber_glyphs(glyphs, pk.piece_map), pk.block)
                f = jamoset.parse_svfn(face)
                self.assertIsNotNone(f.jset)
                ft = jamoset.unpack(f.jset)
                for cp in range(0xAC00, 0xD7A4, 97):
                    got = jamoset.compose(f, ft, cp)
                    cell = bytearray(len(got))
                    for n in jamoset.pieces_of(tt, cp):
                        for i, byte in enumerate(bits(n)):
                            cell[i] |= byte
                    self.assertEqual(bytes(got), bytes(cell), hex(cp))

    def test_big_plus_one_refused(self):
        for counts in ((20, 28, 128, 128, 64), (19, 29, 128, 128, 64), (19, 28, 129, 128, 64), (19, 28, 128, 129, 64),
                       (19, 28, 128, 128, 65)):
            with self.assertRaisesRegex(ValueError, r"is not 1\.\."):
                jamoset._check_counts(*counts, big=True)
            self.assertNotIn("--jset-big", self._msg(counts))

    @staticmethod
    def _msg(counts):
        try:
            jamoset._check_counts(*counts, big=True)
        except ValueError as e:
            return str(e)
        return ""

    def test_compat_7bit(self):
        t = self.limits_tables(*self.BIG)
        t.compat = [jamoset.BLANK] * 51
        # compat[0] (ㄱ, a lead consonant): initial slot 0 of set 64 is piece 1 + 64 * 19; compat[30] (ㅏ): medial slot 0
        # of set 64
        t.compat[0] = t.init_piece[64 * 19]
        block = jamoset.pack(t, big=True).block
        b = jamoset.decode_jset2(block)
        self.assertEqual(b.compat[0], 0x40)
        u = jamoset.unpack(block)
        self.assertEqual(u.compat[0], jamoset.pack(t, True).piece_map[t.init_piece[64 * 19]])
        # bit 7 form: the final table's set 63 (0xBF)
        b.compat[0] = 0xBF
        u = jamoset.unpack(jamoset.encode_jset2(b))
        self.assertEqual(u.compat[0], u.fin_piece[63 * 27 + jamoset.COMPAT_FINAL_ALT[0] - 1])
        b.compat[0] = 0xFF
        self.assertEqual(jamoset.unpack(jamoset.encode_jset2(b)).compat[0], jamoset.BLANK)
        b.compat[0] = 0x80 | 64          # final set 64 of 64
        with self.assertRaisesRegex(ValueError, "compat"):
            jamoset.unpack(jamoset.encode_jset2(b))

    def test_narrow_bytes_unchanged(self):
        n = 0
        for dirpath, _, names in os.walk(os.path.join(self.ROOT, "svf")):
            for name in sorted(names):
                if not name.lower().endswith(".svf"):
                    continue
                f = jamoset.parse_svfn(open(os.path.join(dirpath, name), "rb").read())
                if f.jset is None:
                    continue
                t = jamoset.unpack(f.jset)
                if isinstance(t, jamoset.Jmap):
                    continue
                for v in (1, 2):
                    try:
                        a = jamoset.pack_jset(t, v)
                    except ValueError:
                        with self.assertRaises(ValueError):
                            jamoset.pack_jset(t, v, big=True)
                        continue
                    self.assertEqual(jamoset.pack_jset(t, v, big=True), a, name)
                n += 1
        self.assertGreater(n, 50)

    def test_jset_line_big(self):
        def face(t):
            piece = lambda p: (jamoset.PIECE_BASE + p, b"\x01" * 16, 8, 0, 8)
            return jamoset.write_svfn(8, 16, 14, [piece(p) for p in range(len(jamoset.used_pieces(t)))],
                                      jamoset.pack_v1(t, big=True))
        t = self.limits_tables(*self.BIG)
        t = jamoset.renumber(t, {p: n for n, p in enumerate(jamoset.used_pieces(t))})
        self.assertIn(" big=1", jamoset.jset_line(face(t)))
        data = open(os.path.join(self.ROOT, "svf", "dos", "NEODG16G.SVF"), "rb").read()
        self.assertNotIn("big=1", jamoset.jset_line(data))

    def test_jset_line_jmap_big_fallback(self):
        t = self.limits_tables(13, 12, 32, 24, 16)
        sh = jamoset.shift_pieces(t, 2)
        jm = jamoset.Jmap(0, 1, 1, 0)
        jm.entries = {0: (1, 1, 0)}
        jm.fallback, jm.fallback_version = sh, 1
        fb = jamoset.pack_fallback(sh, 1, big=True)
        glyphs = [(jamoset.PIECE_BASE + p, b"\x01" * 16, 8, 0, 8)
                  for p in range(max(sh.init_piece + sh.med_piece + sh.fin_piece) + 1)]
        face = jamoset.write_svfn(8, 16, 14, glyphs, jamoset.pack_jmap(jm, fb))
        self.assertTrue(jamoset.jset_line(face).endswith("fallback=v1 big=1"), jamoset.jset_line(face))

    def test_jamoadapt_tables(self):
        import jamoadapt
        self.assertEqual(jamoadapt.FORMAT_LIMITS["big"], (128, 128, 64))
        self.assertEqual(jamoadapt.FORMAT_LIMITS["std"], (32, 24, 16))
        self.assertEqual(jamoadapt.CLASS_LIMITS["big"], (19, 28))
        self.assertEqual(jamoadapt.CLASS_LIMITS["std"], (12, 12))
        self.assertEqual(jamoadapt.CLASS_LIMIT, 12)
        self.assertEqual(jamoadapt._class_pair(None), (12, 12))
        self.assertEqual(jamoadapt._class_pair(9), (9, 9))
        self.assertEqual(jamoadapt._class_pair((19, 28)), (19, 28))

    def test_blank_compat_keeps_fallback_block_in_step(self):
        # a Jmap with a fallback: blanking a compat entry re-encodes fallback_block; an untouched one keeps its bytes
        t = jamoset.tables_for(jamoset.LAYOUTS["844"])
        t = jamoset.renumber(t, {s: s for s in jamoset.used_pieces(t)})
        t.compat[0] = 5
        jm = jamoset.Jmap(0, 1, 1, 1)
        jm.fallback, jm.fallback_version = t, 1
        jm.fallback_block = jamoset.pack_fallback(t, 1)
        keep = jm.fallback_block
        jamoset.blank_compat(jm, set())
        self.assertIs(jm.fallback_block, keep)
        jamoset.blank_compat(jm, {0x3131})
        self.assertEqual(jm.fallback.compat[0], jamoset.BLANK)
        self.assertEqual(jamoset.unpack(jm.fallback_block).compat[0], jamoset.BLANK)

    def test_blank_compat_big_fallback(self):
        # a BIG fallback (already in the file) is re-encoded as BIG, not refused
        t = self.limits_tables(*self.BIG)
        t.compat = [jamoset.BLANK] * 51
        t.compat[0] = t.init_piece[0]
        for version in (1, 2):
            with self.subTest(version=version):
                jm = jamoset.Jmap(0, 1, 1, 1)
                jm.fallback, jm.fallback_version = t, version
                jm.fallback_block = jamoset.pack_fallback(t, version, big=True)
                jamoset.blank_compat(jm, {0x3131})
                u = jamoset.unpack(jm.fallback_block)
                self.assertEqual((u.lc, u.nf, u.compat[0]), (19, 64, jamoset.BLANK))


class ListCheckDy(unittest.TestCase):
    """Regression guard (Task 8; passes before the consumer change): check_dy sees a LIST face like any other."""

    def test_check_dy_refuses_a_dy_on_a_whole_glyph_piece(self):
        root = os.path.dirname(HERE)
        with tempfile.TemporaryDirectory(prefix="list-dy-") as d:
            out = os.path.join(d, "L.SVF")
            r = subprocess.run([sys.executable, os.path.join(HERE, "svf_synth.py"), "--jmap-variant", "list1", "--from",
                                os.path.join(root, "svf", "dos", "NEODG16G.SVF"), out], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out, "rb") as fh:
                f = jamoset.parse_svfn(fh.read())
        jm = jamoset.unpack(f.jset)
        self.assertTrue(jm.list_mode)
        jamoset.check_dy(f)
        piece = jamoset.PIECE_BASE + sorted(jm.entries.values())[0][0]
        glyphs = [(cp, g, 0, 0, 0) for cp, g in f.glyphs.items()]
        bad = jamoset.parse_svfn(jamoset.write_svfn(f.cell_w, f.cell_h, f.ascent, glyphs, f.jset, dy={piece: 1}))
        with self.assertRaisesRegex(ValueError, "jamo pieces have a dy"):
            jamoset.check_dy(bad)

    def test_set_table_tools_refuse_a_list_face(self):
        import jamofill, jamomerge, jamovec
        root = os.path.dirname(HERE)
        with tempfile.TemporaryDirectory(prefix="list-tools-") as d:
            out = os.path.join(d, "L.SVF")
            r = subprocess.run([sys.executable, os.path.join(HERE, "svf_synth.py"), "--jmap-variant", "list1", "--from",
                                os.path.join(root, "svf", "dos", "NEODG16G.SVF"), out], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out, "rb") as fh:
                jm = jamoset.unpack(jamoset.parse_svfn(fh.read()).jset)
            for fn in (lambda: jamofill.face_skeleton(out, False), lambda: jamomerge.read_face(out),
                       lambda: jamovec.tables_json(jm)):
                with self.assertRaisesRegex(ValueError, "LIST face .*no set tables"):
                    fn()
            import contextlib, io      # jamofill sheet: a clean message and exit 1, no traceback
            with self.assertRaisesRegex(ValueError, "LIST face .*no set tables"):
                jamofill.face_bitmaps(open(out, "rb").read())
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(jamofill.main(["sheet", out, "-o", os.path.join(d, "s")]), 1)
            self.assertIn("no set tables", err.getvalue())


if __name__ == "__main__":
    unittest.main()
