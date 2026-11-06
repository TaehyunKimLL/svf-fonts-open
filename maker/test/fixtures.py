#!/usr/bin/env python3
"""Synthetic fixtures for the SVF maker's tests.

write_fixtures(dst) lays out a small font tree under @p dst (a temp directory in every test) and returns
{key: absolute path} for the files the maker's later tasks need. The tree copies a few real faces out of this checkout
and makes the rest: a composite-glyph TTF (jamovec master --components), a CFF OTF, ISO10646 / KS X 1001 / johab /
ISO8859 BDFs, an HBF, a DOS 8x4x4 raw font with its `.ENG`, a Windows FNT and a list file. Every licence text sits
inside its own font folder, so nolic/, fnt/, hbf/ and pcf/ have no licence candidate and those fonts start unselected.

  python3 maker/test/fixtures.py DST
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import shutil
import struct

import jamoset  # noqa: E402

PCF_SRC = "/usr/share/fonts/X11/misc/18x18ko.pcf.gz"
HAS_PCF = os.path.isfile(PCF_SRC)

SIL_LICENCE = "SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007\n\nPermission is hereby granted, free of charge.\n"
ANY_LICENCE = "Copyright (c) 2026 the fixture authors.\nReleased under the SIL Open Font License.\n"


# ---- the tree --------------------------------------------------------------------------------------------------

# 2026-01-01 00:00 UTC in head-table time (seconds since 1904); a 0 makes fontTools warn on every load
HEAD_TIME = 3850070400

def write_fixtures(dst):
    """Write the fixture tree under @p dst and return {key: absolute path} for its files."""
    dst = os.path.abspath(dst)
    # a fresh tree only: leftovers would change licence detection, and a symlink would write elsewhere
    if os.path.islink(dst) or (os.path.exists(dst) and os.listdir(dst)):
        raise ValueError("fixtures: %s must be a new or empty directory, not a symlink" % dst)
    out = {}

    def put(*parts):
        p = os.path.join(dst, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def text(p, s):
        with open(p, "w", encoding="utf-8") as f:
            f.write(s)
        return p

    def copy(p, src):
        shutil.copyfile(src, p)
        return p

    nanum_ttf = os.path.join(REPO_DIR, "ttf", "nanumgothic", "NanumGothic-Bold.ttf")
    out["ttf"] = copy(put("nanum", "NanumGothic-Bold.ttf"), nanum_ttf)
    out["ttf_licence"] = _nanum_licence(put("nanum", "OFL.txt"))

    out["composite"] = _composite_ttf(put("composite", "Composite.ttf"))
    out["composite_licence"] = text(put("composite", "LICENSE.txt"), SIL_LICENCE)

    out["otf"] = _cff_otf(put("otf", "Cff.otf"))
    out["otf_licence"] = text(put("otf", "LICENSE.txt"), ANY_LICENCE)

    out["svf_pre"] = copy(put("svf", "NEODG16.SVF"), os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF"))
    out["svf_pre_licence"] = copy(put("svf", "NEODGM.TXT"), os.path.join(REPO_DIR, "svf", "dos", "NEODGM.TXT"))
    out["svf_jamo"] = copy(put("svf", "JAMO6J.SVF"), os.path.join(REPO_DIR, "svf", "dos", "NEODG16G.SVF"))
    out["svf_jamo_licence"] = copy(put("svf", "LICENSE-OFL.txt"),
                                   os.path.join(REPO_DIR, "svf", "dos", "OFL.TXT"))

    _bdf(put("bdf", "iso.bdf"), _iso_glyphs(), 16, 13, 3, "ISO10646", (16, 16))
    out["bdf_iso"] = os.path.join(dst, "bdf", "iso.bdf")
    _bdf(put("bdf", "ksc.bdf"), _ksc_glyphs(), 24, 19, 5, "KSX1001.1998", (24, 24))
    out["bdf_ksc"] = os.path.join(dst, "bdf", "ksc.bdf")
    _bdf(put("bdf", "johab.bdf"), _johab_glyphs(), 16, 13, 3, "johab", (16, 16))
    out["bdf_johab"] = os.path.join(dst, "bdf", "johab.bdf")
    _bdf(put("bdf", "latin.bdf"), _latin_glyphs(), 16, 13, 3, "ISO8859", (8, 16))
    out["bdf_latin"] = os.path.join(dst, "bdf", "latin.bdf")
    out["bdf_licence"] = text(put("bdf", "COPYING"), ANY_LICENCE)

    _hbf(put("hbf", "ascii.hbf"), "ascii.bin", {code: [0xFF] * 16 for code in range(0x41, 0x5B)})
    out["hbf"] = os.path.join(dst, "hbf", "ascii.hbf")

    _dos_raw(put("dos", "HAN.FNT"))
    out["dos_raw"] = os.path.join(dst, "dos", "HAN.FNT")
    _eng(put("dos", "ENG.FNT"))
    out["dos_eng"] = os.path.join(dst, "dos", "ENG.FNT")
    out["dos_licence"] = text(put("dos", "LICENSE.txt"), ANY_LICENCE)

    _fnt(put("fnt", "win.fnt"))
    out["fnt"] = os.path.join(dst, "fnt", "win.fnt")

    out["nolic"] = copy(put("nolic", "NoLicence.ttf"), nanum_ttf)

    out["list"] = text(put("list.txt"), "가나다\nABC\n")

    if HAS_PCF:
        out["pcf"] = copy(put("pcf", "18x18ko.pcf.gz"), PCF_SRC)

    return out


def _jset1_face(name):
    with open(os.path.join(REPO_DIR, "tools", "testdata", "jset1", name), "rb") as f:
        return f.read()


def jset1_face():
    """dos/NEODG16G.SVF with its small v1 JSET block (653 B)."""
    return _jset1_face("NEODG16G.SVF")


def jset1_big_face():
    """NSQRB16.SVF with its 12x12 v1 JSET block (11681 B)."""
    return _jset1_face("NSQRB16.SVF")


def v2_face(data):
    """The v3 face @p data written back as SVFN v2 (the layout svf-maker shipped before v3, read only by
    tools/svf2to3.py): header, code points, JSET, metrics, then full cells in code point order. The tests use it for
    a v2 upload; svf2to3.py --check of it against @p data holds."""
    import svf2to3
    f = jamoset.parse_svfn(data)
    cps = sorted(f.glyphs)
    stride = ((f.cell_w * f.bpp + 7) // 8) * f.cell_h
    cmap = b"".join(struct.pack("<II", cp, i) for i, cp in enumerate(cps))
    jset = f.jset or b""
    metrics = b"".join(struct.pack("<BbBb", *f.metrics[cp], f.dy.get(cp, 0)) for cp in cps) if f.metrics_ok else b""
    cmap_off = svf2to3.V2_HEADER_SIZE
    metrics_off = cmap_off + len(cmap) + len(jset) if metrics else 0
    data_off = cmap_off + len(cmap) + len(jset) + len(metrics)
    head = struct.pack(svf2to3.V2_HEADER, jamoset.MAGIC, svf2to3.V2_VERSION, f.flags, f.bpp, 0, 0, len(cps),
                       f.cell_w, f.cell_h, f.ascent, f.dy_min & 0xFF, f.dy_max & 0xFF, metrics_off, data_off,
                       stride * len(cps))
    return head + struct.pack("<I", cmap_off) + cmap + jset + metrics + b"".join(bytes(f.glyphs[cp]) for cp in cps)


def _nanum_licence(path):
    """REPO_DIR/ttf/nanumgothic's OFL.txt (or its first *.txt) copied whole; else the first 4 KB of
    svf/dos/OFLNANUM.TXT (the 4 KB cut is only for that fallback)."""
    src_dir = os.path.join(REPO_DIR, "ttf", "nanumgothic")
    names = sorted(n for n in os.listdir(src_dir) if n.lower().endswith(".txt"))
    names.sort(key=lambda n: n.lower() != "ofl.txt")  # OFL.txt first when present
    if names:
        shutil.copyfile(os.path.join(src_dir, names[0]), path)
        return path
    with open(os.path.join(REPO_DIR, "svf", "dos", "OFLNANUM.TXT"), "rb") as f:
        head = f.read(4096)
    with open(path, "wb") as f:
        f.write(head)
    return path


# ---- the composite TTF -----------------------------------------------------------------------------------------

# Slots in the 1000 unit em: the initial's rectangle sits in the top-left (x offset 10*i), the medial's in the right
# half (y offset 10*j) and the final's in the bottom strip (x offset 10*k). All three regions are disjoint and the
# 10 unit spacing keeps the slots of one family from touching, so every piece is its own blob for jamovec master
# --components (which reads the syllable composites' glyf components). The rectangles are large enough to carry ink at
# 16 px (the pieces must survive jamovec render and mkfont), and every coordinate stays inside the em and the hhea
# ascent 800 / descent -200.

def _composite_ttf(path, n_syllables=None):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent

    def empty():
        return TTGlyphPen(None).glyph()

    def rect(x0, y0, x1, y1):
        pen = TTGlyphPen(None)
        pen.moveTo((x0, y0))
        pen.lineTo((x1, y0))
        pen.lineTo((x1, y1))
        pen.lineTo((x0, y1))
        pen.closePath()
        return pen.glyph()

    def frame():
        """A hollow 1 unit frame around the em: mkfont drops a glyph whose image equals .notdef's."""
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((1000, 0))
        pen.lineTo((1000, 1000))
        pen.lineTo((0, 1000))
        pen.closePath()
        pen.moveTo((1, 1))
        pen.lineTo((1, 999))
        pen.lineTo((999, 999))
        pen.lineTo((999, 1))
        pen.closePath()
        return pen.glyph()

    def composite(names):
        g = Glyph()
        g.numberOfContours = -1
        g.components = []
        for name in names:
            c = GlyphComponent()
            c.glyphName = name
            c.x = 0
            c.y = 0
            c.flags = 0
            g.components.append(c)
        return g

    def syl_name(cp):
        return "uni%04X" % cp

    letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    glyphs = {".notdef": frame(), "space": empty()}
    for n, ch in enumerate(letters):
        glyphs[ch] = rect(100, 0, 200 + 20 * n, 700)

    components = {}
    for i in range(19):
        components["ini_%d" % i] = rect(10 * i, 450, 10 * i + 300, 750)
    for j in range(21):
        components["med_%d" % j] = rect(600, 50 + 10 * j, 900, 350 + 10 * j)
    for k in range(1, 28):
        components["fin_%d" % k] = rect(10 * k, -150, 10 * k + 400, 0)
    glyphs.update(components)

    # 0xAC00 + (i*21 + 0)*28: initial i, medial 0, no final; 0xAC00 + (0*21 + j)*28: initial 0, medial j
    # (가 is both i=0 and j=0); 0xAC00 + k for k in 1..27: initial 0, medial 0, final k. 66 distinct code points.
    spec = {}
    for i in range(19):
        spec[0xAC00 + i * 588] = ["ini_%d" % i, "med_0"]
    for j in range(1, 21):
        spec[0xAC00 + j * 28] = ["ini_0", "med_%d" % j]
    for k in range(1, 28):
        spec[0xAC00 + k] = ["ini_0", "med_0", "fin_%d" % k]
    if n_syllables is not None:                 # a big font: the first n_syllables Hangul syllables, each a composite
        spec = {}
        for cp in range(0xAC00, 0xAC00 + n_syllables):
            i, rest = divmod(cp - 0xAC00, 588)
            j, k = divmod(rest, 28)
            spec[cp] = ["ini_%d" % i, "med_%d" % j] + (["fin_%d" % k] if k else [])
    for cp, names in spec.items():
        glyphs[syl_name(cp)] = composite(names)

    order = [".notdef", "space"] + letters + list(components) + [syl_name(cp) for cp in sorted(spec)]
    cmap = {0x20: "space"}
    cmap.update({0x41 + n: ch for n, ch in enumerate(letters)})
    cmap.update({cp: syl_name(cp) for cp in spec})

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (1000, 0) for name in order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Composite", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.setupHead(created=HEAD_TIME, modified=HEAD_TIME)   # deterministic bytes: a fixed build timestamp
    fb.font.recalcTimestamp = False
    fb.save(path)
    return path


# ---- the CFF OTF ----------------------------------------------------------------------------------------------

def _cff_otf(path):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen

    def draw_rect(pen, x0, y0, x1, y1):
        pen.moveTo((x0, y0))
        pen.lineTo((x1, y0))
        pen.lineTo((x1, y1))
        pen.lineTo((x0, y1))
        pen.closePath()

    def draw_frame(pen):
        pen.moveTo((0, 0))
        pen.lineTo((1000, 0))
        pen.lineTo((1000, 1000))
        pen.lineTo((0, 1000))
        pen.closePath()
        pen.moveTo((1, 1))
        pen.lineTo((1, 999))
        pen.lineTo((999, 999))
        pen.lineTo((999, 1))
        pen.closePath()

    def charstring(width, draw):
        pen = T2CharStringPen(width, None)
        draw(pen)
        return pen.getCharString()

    order = [".notdef", "space", "A", "uniAC00"]
    charstrings = {
        ".notdef": charstring(1000, draw_frame),
        "space": charstring(500, lambda pen: None),
        "A": charstring(1000, lambda pen: draw_rect(pen, 100, 100, 900, 900)),
        "uniAC00": charstring(1000, lambda pen: draw_rect(pen, 200, 200, 800, 600)),
    }
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0x20: "space", 0x41: "A", 0xAC00: "uniAC00"})
    fb.setupCFF("Cff-Regular", {"FullName": "Cff Regular", "FamilyName": "Cff", "Weight": "Regular"}, charstrings, {})
    fb.setupHorizontalMetrics({name: (500 if name == "space" else 1000, 0) for name in order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Cff", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.setupHead(created=HEAD_TIME, modified=HEAD_TIME)   # deterministic bytes: a fixed build timestamp
    fb.font.recalcTimestamp = False
    fb.save(path)
    return path


# ---- BDF, HBF -------------------------------------------------------------------------------------------------

def _block(bw, bh, row):
    """A filled rectangle of @p bw x @p bh with every row @p row (MSB left), as a _bdf glyph tuple."""
    return (bw, bh, 0, 0, [row] * bh)


def _iso_glyphs():
    """Every glyph a distinct bitmap: mkfont drops a glyph drawn like .notdef, so identical solid blocks bake none."""
    cps = list(range(0x41, 0x5B)) + [0xAC00, 0xAC01]
    return [(cp, 16, 8, 0, 0, [((cp * 7 + y * 31) & 0xFFFF) | 1 for y in range(8)]) for cp in cps]


def _ksc_glyphs():
    return [(0x3021,) + _block(24, 8, 0xFFFFFF), (0x3022,) + _block(24, 8, 0xFFFFFF)]


def _latin_glyphs():
    return [(cp,) + _block(8, 8, 0xFF) for cp in range(0x41, 0x5B)]


def _johab_glyphs():
    """529 johab-1 glyphs at ENCODING 0..528 (jamoset's hanterm-johab opener demands all 529), one row set each."""
    return [(code, 16, 16, 0, -3, [0xFFFF if y == 8 else 0 for y in range(16)]) for code in range(529)]


def _bdf(path, glyphs, px, ascent, descent, registry, box):
    """glyphs: [(ENCODING, bw, bh, bx, by, [row ints])] with rows as ints (MSB left)."""
    w, h = box
    out = ["STARTFONT 2.1", "FONT -fixture-%s" % registry.lower(), "SIZE %d 75 75" % px,
           "FONTBOUNDINGBOX %d %d 0 %d" % (w, h, -descent), "STARTPROPERTIES 5",
           "FONT_ASCENT %d" % ascent, "FONT_DESCENT %d" % descent, "PIXEL_SIZE %d" % px,
           'CHARSET_REGISTRY "%s"' % registry, 'CHARSET_ENCODING "1"', "ENDPROPERTIES", "CHARS %d" % len(glyphs)]
    for enc, bw, bh, bx, by, rows in glyphs:
        nb = (bw + 7) // 8
        out += ["STARTCHAR g%04X" % enc, "ENCODING %d" % enc, "SWIDTH %d 0" % round(bw * 72000 / (px * 75)), "DWIDTH %d 0" % bw,
                "BBX %d %d %d %d" % (bw, bh, bx, by), "BITMAP"]
        out += [format(r << (nb * 8 - bw), "0%dX" % (nb * 2)) for r in rows]
        out += ["ENDCHAR"]
    out += ["ENDFONT", ""]
    with open(path, "w") as f:
        f.write("\n".join(out))


def _hbf(path, binname, glyphs, w=8, h=16, ascent=13, descent=3):
    """glyphs: {code: rows}; the bitmap file holds codes 1..max in order."""
    top = max(glyphs)
    nb = (w + 7) // 8
    data = bytearray()
    for code in range(1, top + 1):
        rows = glyphs.get(code, [0] * h)
        for r in rows:
            data += (r << (nb * 8 - w)).to_bytes(nb, "big")
    text = ["HBF_START_FONT 1.0", "HBF_BITMAP_BOUNDING_BOX %d %d 0 -%d" % (w, h, descent),
            "FONTBOUNDINGBOX %d %d 0 -%d" % (w, h, descent), "FONT_ASCENT %d" % ascent, "FONT_DESCENT %d" % descent,
            "HBF_CODE_RANGE 0x0001-0x%04X %s 0" % (top, binname), "HBF_END_FONT", ""]
    with open(path, "w") as f:
        f.write("\n".join(text))
    p = os.path.join(os.path.dirname(path), binname)
    with open(p, "wb") as f:
        f.write(bytes(data))


# ---- DOS raw, DOS .ENG, Windows FNT ---------------------------------------------------------------------------

def _dos_raw(path):
    """11520 bytes of 360 16x16 glyphs: the 8x4x4 fill slots blank, every other glyph's first row 0xFF 0xFF."""
    count, gb = 360, 32
    fill = set(jamoset.slots_of(8, 4, 4, 160, 248))
    data = bytearray(count * gb)
    for i in range(count):
        if i not in fill:
            data[i * gb] = 0xFF
            data[i * gb + 1] = 0xFF
    with open(path, "wb") as f:
        f.write(bytes(data))


def _eng(path):
    """2048 bytes of 128 8x16 glyphs, each with row 8 set to 0xFF."""
    data = bytearray(2048)
    for i in range(2048 // 16):
        data[i * 16 + 8] = 0xFF
    with open(path, "wb") as f:
        f.write(bytes(data))


def _fnt(path):
    """A 128 byte Windows FNT header: u16 0x0200 at 0, bytes 6..65 the face name, the rest zero."""
    data = bytearray(128)
    data[0:2] = struct.pack("<H", 0x0200)
    data[6:66] = b"(c) test".ljust(60)   # the brief's space padding (bytes 6..65 of a 128 byte FNT)
    with open(path, "wb") as f:
        f.write(bytes(data))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: fixtures.py DST")
    for key in sorted(write_fixtures(sys.argv[1])):
        print(key)
