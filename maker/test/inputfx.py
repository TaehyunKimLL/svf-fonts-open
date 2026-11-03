#!/usr/bin/env python3
"""Synthetic fixture builders for the maker's new input kinds (t_f3ef3189).

Every builder returns bytes and is built here from fontTools or by hand: no proprietary data, no network. The
maker's own tests import this module; it puts `maker/` and `tools/` on sys.path like fixtures.py does.
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import io
import struct

import fixtures
import test_macsfnt
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

HEAD_TIME = fixtures.HEAD_TIME


def _save(font):
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


def _box(x0, y0, x1, y1):
    pen = TTGlyphPen(None)
    pen.moveTo((x0, y0)); pen.lineTo((x0, y1)); pen.lineTo((x1, y1)); pen.lineTo((x1, y0)); pen.closePath()
    return pen.glyph()


def _finish(fb, family):
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.setupHead(created=HEAD_TIME, modified=HEAD_TIME)
    fb.font.recalcTimestamp = False


def ttf(family, ga_box, a_box=(100, 0, 400, 700)):
    """Glyphs .notdef, A, ga (U+0041, U+AC00), a Unicode cmap."""
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A", "ga"])
    fb.setupCharacterMap({0x41: "A", 0xAC00: "ga"})
    fb.setupGlyf({".notdef": _box(0, 0, 10, 10), "A": _box(*a_box), "ga": _box(*ga_box)})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 100), "ga": (1000, 50)})
    _finish(fb, family)
    return _save(fb.font)


def otf(family, ga_box):
    """The same as CFF."""
    def cs(box):
        pen = T2CharStringPen(1000, None)
        x0, y0, x1, y1 = box
        pen.moveTo((x0, y0)); pen.lineTo((x1, y0)); pen.lineTo((x1, y1)); pen.lineTo((x0, y1)); pen.closePath()
        return pen.getCharString()

    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder([".notdef", "A", "ga"])
    fb.setupCharacterMap({0x41: "A", 0xAC00: "ga"})
    fb.setupCFF(family + "-Regular", {"FullName": family + " Regular", "FamilyName": family, "Weight": "Regular"},
                {".notdef": cs((0, 0, 10, 10)), "A": cs((100, 0, 400, 700)), "ga": cs(ga_box)}, {})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 100), "ga": (1000, 50)})
    _finish(fb, family)
    return _save(fb.font)


def ttc(fonts):
    """A TTCollection of the given font files."""
    coll = TTCollection()
    coll.fonts = [TTFont(io.BytesIO(b)) for b in fonts]
    buf = io.BytesIO()
    coll.save(buf)
    return buf.getvalue()


def variable_ttf():
    """Family Vary, axis wght 100/400/900, instances Regular 400 and Bold 700, a gvar delta on ga's right edge."""
    from fontTools.ttLib.tables.TupleVariation import TupleVariation
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A", "ga"])
    fb.setupCharacterMap({0x41: "A", 0xAC00: "ga"})
    fb.setupGlyf({".notdef": _box(0, 0, 10, 10), "A": _box(100, 0, 400, 700), "ga": _box(50, -100, 950, 800)})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 100), "ga": (1000, 50)})
    _finish(fb, "Vary")
    fb.setupFvar([("wght", 100, 400, 900, "Weight")],
                 [{"location": {"wght": 400}, "stylename": "Regular"}, {"location": {"wght": 700}, "stylename": "Bold"}])
    # ga has 4 points (x0,y0) (x0,y1) (x1,y1) (x1,y0) plus 4 phantom points; the right edge moves by -40 at the axis max
    deltas = [(0, 0), (0, 0), (-40, 0), (-40, 0), (0, 0), (0, 0), (0, 0), (0, 0)]
    fb.setupGvar({"ga": [TupleVariation({"wght": (0.0, 1.0, 1.0)}, deltas)]})
    return _save(fb.font)


def mac_cmap_ttf():
    return test_macsfnt.mac_korean_font()


def both_cmaps_ttf():
    """mac_cmap_ttf() plus a (3,1) format 4 subtable."""
    font = TTFont(io.BytesIO(mac_cmap_ttf()))
    st = CmapSubtable.newSubtable(4)
    st.platformID, st.platEncID, st.language, st.cmap = 3, 1, 0, {0x41: "A", 0xAC00: "ga"}
    font["cmap"].tables.append(st)
    return _save(font)


def fork(entries):
    return test_macsfnt.resource_fork(entries)


def appledouble(fk):
    dbl = bytearray(struct.pack(">II", 0x00051607, 0x00020000) + bytes(16) + struct.pack(">H", 1))
    dbl += struct.pack(">III", 2, len(dbl) + 12, len(fk)) + fk
    return bytes(dbl)


def macbinary(fk, name=b"Synth"):
    mb = bytearray(128)
    mb[1] = len(name)
    mb[2:2 + len(name)] = name
    struct.pack_into(">II", mb, 83, 0, len(fk))
    mb += fk
    return bytes(mb)


def eblc_ttf(ppems=(12, 16)):
    """ttf("Strike", ...) plus a raw EBLC (one 48-byte record per size, ppemX = ppemY) and a 4-byte EBDT."""
    font = TTFont(io.BytesIO(ttf("Strike", (50, -100, 950, 800))))
    rec = bytearray()
    for p in ppems:
        r = bytearray(48)
        r[44] = p
        r[45] = p
        r[46] = 1
        rec += r
    eblc = DefaultTable("EBLC")
    eblc.data = struct.pack(">II", 0x00020000, len(ppems)) + bytes(rec)
    ebdt = DefaultTable("EBDT")
    ebdt.data = struct.pack(">I", 0x00020000)
    font["EBLC"] = eblc
    font["EBDT"] = ebdt
    return _save(font)


def bitmap_only_ttf(ppems=(12, 16)):
    """eblc_ttf without glyf/loca (maxp 0.5), saved without bbox recalculation."""
    font = TTFont(io.BytesIO(eblc_ttf(ppems)), recalcBBoxes=False)
    del font["glyf"]
    del font["loca"]
    font["maxp"].tableVersion = 0x00005000
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


def pcf(glyphs, registry, encoding, px, ascent, descent, family="Fixture", fmt=0x0000000C):
    """A PCF with tables properties (1), accelerators (2), metrics (4, uncompressed), bitmaps (8) and BDF encodings
    (0x20). @p glyphs is [(code, rows, width)], every glyph @p px high (rows are ints, MSB left); @p fmt is the format
    word of the bitmaps table (default MSByte, MSBit, glyph pad 1, scan unit 1), the other tables use 0x0000000C."""
    std = 0x0000000C

    def en_of(f):
        return ">" if f & 4 else "<"

    def table(f, body):
        return struct.pack("<I", f) + body

    props = [("FONT", "-fixture-%s-medium-r-normal--%d-%s-%s" % (family, px, registry, encoding)),
             ("FAMILY_NAME", family), ("PIXEL_SIZE", px), ("FONT_ASCENT", ascent), ("FONT_DESCENT", descent),
             ("CHARSET_REGISTRY", registry), ("CHARSET_ENCODING", encoding)]
    strings = bytearray()
    recs = bytearray()
    e = en_of(std)

    def add(s):
        o = len(strings)
        strings.extend(s.encode("latin-1") + b"\0")
        return o

    for k, v in props:
        if isinstance(v, str):
            recs += struct.pack(e + "IBI", add(k), 1, add(v))
        else:
            recs += struct.pack(e + "IBi", add(k), 0, v)
    recs += bytes((-len(recs)) % 4)
    t_props = table(std, struct.pack(e + "I", len(props)) + bytes(recs) + struct.pack(e + "I", len(strings)) +
                    bytes(strings) + bytes((-len(strings)) % 4))

    def metric(w):
        return struct.pack(e + "6h", 0, w, w, ascent, descent, 0)

    wmax = max(w for _c, _r, w in glyphs)
    t_acc = table(std, bytes([0, 1, 0, 1, 0, 0, 0, 0]) + struct.pack(e + "3i", ascent, descent, 0) +
                  metric(0) + metric(wmax))
    t_met = table(std, struct.pack(e + "I", len(glyphs)) + b"".join(metric(w) for _c, _r, w in glyphs))

    eb = en_of(fmt)
    pad = 1 << (fmt & 3)
    unit = 1 << ((fmt >> 4) & 3)
    rev = bytes(int("{:08b}".format(b)[::-1], 2) for b in range(256))
    datas = []
    for _c, rows, w in glyphs:
        nb = (w + 7) // 8
        d = bytearray()
        for r in rows:
            d += r.to_bytes(nb, "big") if w % 8 == 0 else (r << (nb * 8 - w)).to_bytes(nb, "big")
            d += bytes((-nb) % pad)
        datas.append(d)
    body = bytearray()
    offsets = []
    for d in datas:
        offsets.append(len(body))
        body += d
    body += bytes((-len(body)) % max(pad, unit))
    if not fmt & 8:
        body = bytearray(bytes(body).translate(rev))
    if bool(fmt & 4) != bool(fmt & 8) and unit > 1:
        for i in range(0, len(body) - unit + 1, unit):
            body[i:i + unit] = body[i:i + unit][::-1]
    sizes = [len(body)] * 4
    t_bmp = table(fmt, struct.pack(eb + "I", len(glyphs)) + struct.pack(eb + "%dI" % len(glyphs), *offsets) +
                  struct.pack(eb + "4I", *sizes) + bytes(body))

    codes = sorted(c for c, _r, _w in glyphs)
    min1, max1 = min(c >> 8 for c in codes), max(c >> 8 for c in codes)
    min2, max2 = min(c & 0xFF for c in codes), max(c & 0xFF for c in codes)
    index = {c: i for i, (c, _r, _w) in enumerate(glyphs)}
    arr = [index.get((b1 << 8) | b2, 0xFFFF) for b1 in range(min1, max1 + 1) for b2 in range(min2, max2 + 1)]
    t_enc = table(std, struct.pack(e + "5h", min2, max2, min1, max1, 0) + struct.pack(e + "%dH" % len(arr), *arr))

    tables = [(1, std, t_props), (2, std, t_acc), (4, std, t_met), (8, fmt, t_bmp), (0x20, std, t_enc)]
    toc = struct.pack("<4sI", b"\x01fcp", len(tables))
    off = 8 + 16 * len(tables)
    blobs = b""
    for typ, f, t in tables:
        toc += struct.pack("<IIII", typ, f, len(t), off + len(blobs))
        blobs += t
        blobs += bytes((-len(blobs)) % 4)
    return toc + blobs


def pft_eng():
    """12,288 bytes: 256 glyphs of 12x24 (48 bytes), row 12 of each 0xFF 0xF0 (an HWP ASCII.PFT)."""
    data = bytearray(12288)
    for g in range(256):
        data[g * 48 + 12 * 2:g * 48 + 12 * 2 + 2] = b"\xFF\xF0"
    return bytes(data)


def hbios_eng():
    """15,360 bytes: 256 glyphs of 12x24 in a 16x30 cell (60 bytes), row 14 of each 0xFF 0xF0, margins blank."""
    data = bytearray(15360)
    for g in range(256):
        data[g * 60 + 14 * 2:g * 60 + 14 * 2 + 2] = b"\xFF\xF0"
    return bytes(data)


def dkb_like():
    """15,360 bytes with byte 0 of every 60-byte block 0xFF: ink in an HBIOS margin row, so a Dokkaebi 7x2x2 face."""
    data = bytearray(15360)
    for g in range(256):
        data[g * 60] = 0xFF
    return bytes(data)
