#!/usr/bin/env python3
"""detect.py tests: format sniffing, metadata, sizes and DOS raw candidates.

  python3 -m unittest discover -s maker/test -p 'test_*.py'
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
import tempfile
import time
import unittest
from unittest import mock

import bdfface
import detect
import fixtures
import jamoset

ROOT = None
F = {}


def head(path, n=-1):
    with open(path, "rb") as f:
        return f.read(n)


def entry(key):  # the single entry of a fixture
    out = detect.detect_file(F[key], os.path.relpath(F[key], ROOT))
    assert len(out) == 1, out
    return out[0]


def small_ttf(path, family="Ttc"):
    """A tiny TTF (`name` table family @p family) for wrapping in a TTC."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.ttLib.tables._g_l_y_f import Glyph
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({0x41: "A"})
    fb.setupGlyf({".notdef": Glyph(), "A": Glyph()})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.save(path)
    return path


def ttc(path, faces):
    """A TTC holding @p faces copies of a tiny TTF."""
    from fontTools.ttLib import TTCollection, TTFont
    src = small_ttf(path + ".src.ttf")
    coll = TTCollection()
    coll.fonts = [TTFont(src, lazy=True) for _ in range(faces)]
    coll.save(path)
    for font in coll.fonts:
        font.close()
    return path


def fon_bytes(pixh=13):
    """A one-face Windows FON: an NE resource table wrapping a small Windows FNT of @p pixh rows.

    FreeType reads a 148 byte header frame from an FNT offset, so the FNT blob carries a little slack past its data.
    """
    width, first, last = 8, 32, 32
    chartab = struct.pack("<H", width)
    face = b"Fixture\x00"
    face_off = 118 + len(chartab)
    bits_off = face_off + len(face)
    h = bytearray()
    h += struct.pack("<H", 0x0200) + struct.pack("<I", 0) + b" " * 60 + struct.pack("<H", 0)
    h += struct.pack("<HHHHHH", 10, 96, 96, 11, 2, 0)
    h += struct.pack("<BBB", 0, 0, 0) + struct.pack("<H", 400) + struct.pack("<B", 0)
    h += struct.pack("<HH", 0, pixh) + struct.pack("<B", 0x11) + struct.pack("<HH", width, width)
    h += struct.pack("<BBBB", first, last, 96, 0x20) + struct.pack("<H", 2)
    h += struct.pack("<I", 0) + struct.pack("<I", face_off) + struct.pack("<I", 0) + struct.pack("<I", bits_off)
    h += struct.pack("<B", 0)
    assert len(h) == 118
    fnt = bytes(h) + chartab + face + b"\xff" * pixh + b"\0" * 32
    fnt = fnt[:2] + struct.pack("<I", len(fnt)) + fnt[6:]
    shift, fnt_off, rsrctab = 4, 0xA0, 0x40
    res = struct.pack("<H", shift) + struct.pack("<HHI", 0x8008, 1, 0)
    res += struct.pack("<HHHHHH", fnt_off >> shift, (len(fnt) + 15) // 16, 0x1c30, 0x8001, 0, 0) + struct.pack("<H", 0)
    mz = bytearray(0x40)
    mz[0:2] = b"MZ"
    struct.pack_into("<I", mz, 0x3C, 0x40)
    ne = bytearray(0x40)
    ne[0:2] = b"NE"
    ne[2], ne[3] = 5, 1
    struct.pack_into("<H", ne, 0x22, 0x40)          # segtab (cseg 0)
    struct.pack_into("<H", ne, 0x24, rsrctab)
    struct.pack_into("<H", ne, 0x26, rsrctab + len(res))
    struct.pack_into("<H", ne, 0x32, shift)
    struct.pack_into("<H", ne, 0x34, 1)
    out = bytes(mz) + bytes(ne) + res
    out += b"\0" * (fnt_off - len(out))
    out += fnt
    if len(out) % (1 << shift):
        out += b"\0" * ((1 << shift) - len(out) % (1 << shift))
    return out


def gzip_file(path, src):
    """@p src gzipped to @p path."""
    import gzip
    with open(src, "rb") as f:
        data = f.read()
    with gzip.open(path, "wb") as g:
        g.write(data)
    return path


def ttc_claiming(path, faces):
    """A TTC with @p faces offsets, all pointing at one real face.

    The single face's table directory offsets are shifted to the new start, so face 0 (and the header count) is real
    while no other face is built.
    """
    src = ttc(path, 1)
    with open(src, "rb") as f:
        old = f.read()
    old_start = struct.unpack_from(">I", old, 12)[0]
    sfnt = bytearray(old[old_start:])
    new_start = 12 + 4 * faces
    delta = new_start - old_start
    for i in range(struct.unpack_from(">H", sfnt, 4)[0]):        # shift every table record's absolute offset
        at = 12 + 16 * i + 8
        struct.pack_into(">I", sfnt, at, struct.unpack_from(">I", sfnt, at)[0] + delta)
    head = b"ttcf" + old[4:8] + struct.pack(">I", faces)          # tag, version, numFonts
    head += struct.pack(">I", new_start) * faces
    with open(path, "wb") as f:
        f.write(head + bytes(sfnt))
    return path


def nameless_ttf(path):
    """A tiny TTF whose `name` table holds nothing, so read_name falls back to the file stem."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.ttLib.tables._g_l_y_f import Glyph
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({0x41: "A"})
    fb.setupGlyf({".notdef": Glyph(), "A": Glyph()})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 0)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": "Temp", "styleName": "Temp"})
    fb.font["name"].names = []
    fb.save(path)
    return path


def pcf_properties(value):
    """A PCF header + a properties table naming PIXEL_SIZE @p value, LSB-first.

    The strings sit after padding to 4 bytes and a u32 `string_size`; @p value is picked so that string_size's low
    byte is printable (0x2A), which is what a "first printable byte" scan would mistake for the strings' start.
    """
    strings = b"PIXEL_SIZE\0" + b"X" * 31                  # 42 bytes = 0x2A
    props = 24
    table = struct.pack("<II", 0, 1) + struct.pack("<IBI", 0, 0, value)   # format, count, one record
    table += bytes((-len(table)) % 4)                     # pad to the 4 byte boundary
    table += struct.pack("<I", len(strings)) + strings    # string_size, then the inline strings
    head = b"\x01fcp" + struct.pack("<I", 1) + struct.pack("<IIII", 1, 0, 0, props)
    return head + table


class FixtureCase(unittest.TestCase):
    """One setUpClass writes the fixture tree into this class's temp dir; entry() reads the module globals."""

    @classmethod
    def setUpClass(cls):
        global ROOT, F
        cls.tmp = tempfile.mkdtemp(prefix="svf-maker-detect-")
        ROOT = cls.tmp
        F = fixtures.write_fixtures(ROOT)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


class SniffTest(FixtureCase):
    def test_magic(self):
        self.assertEqual(detect.sniff(head(F["ttf"], 64)), "ttf")
        self.assertEqual(detect.sniff(head(F["otf"], 64)), "otf")
        self.assertEqual(detect.sniff(head(F["svf_pre"], 64)), "svf")
        self.assertEqual(detect.sniff(b"SVFN\x01\x00" + b"\0" * 58), "svf1")
        self.assertEqual(detect.sniff(b"SVFN\x03\x00" + b"\0" * 58), "svf")      # v3: the maker's own format
        self.assertEqual(detect.sniff(b"SVFN\x02\x00" + b"\0" * 58), "svf2")     # v2: converted by svf2to3.py
        self.assertEqual(detect.sniff(b"SVFN\x04\x00" + b"\0" * 58), "unknown")
        self.assertEqual(detect.sniff(b"SVFN"), "svf1")
        self.assertEqual(detect.sniff(b"STARTFONT 2.1\n"), "bdf")
        self.assertEqual(detect.sniff(b"PK\x03\x04" + b"\0" * 60), "archive")
        self.assertEqual(detect.sniff(b"\xfd7zXZ\x00" + b"\0" * 60), "archive")
        self.assertEqual(detect.sniff(head(F["fnt"])), "fnt")
        self.assertEqual(detect.sniff(head(F["dos_raw"], 512), 11520), "dos-raw")
        self.assertEqual(detect.sniff(bytes(2048)), "eng")
        self.assertEqual(detect.sniff(bytes(512), 2048), "eng")
        self.assertEqual(detect.sniff(b"\x1f\x8b" + b"\0" * 60), "gzip")
        self.assertEqual(detect.sniff(b"hello"), "unknown")

    def test_gzip_is_undone_one_level(self):
        import gzip
        p = os.path.join(ROOT, "a.bdf.gz")
        with gzip.open(p, "wb") as f:
            f.write(b"STARTFONT 2.1\nFONT -t\nSIZE 16 75 75\nFONTBOUNDINGBOX 16 16 0 -3\nCHARS 0\nENDFONT\n")
        head, size = detect.gunzip_head(p)
        self.assertTrue(head.startswith(b"STARTFONT"))
        self.assertGreater(size, 60)
        self.assertEqual(detect.detect_file(p, "a.bdf.gz")[0]["format"], "bdf")
        q = os.path.join(ROOT, "e.fnt.gz")
        with gzip.open(q, "wb") as f:
            f.write(bytes(2048))
        self.assertEqual(detect.detect_file(q, "e.fnt.gz")[0]["format"], "eng")


class DetectFileTest(FixtureCase):
    def test_ttf(self):
        e = entry("ttf")
        self.assertEqual((e["format"], e["source_kind"], e["family"], e["style"]), ("ttf", "outline", "NanumGothic", "Bold"))
        self.assertEqual((e["sizes"], e["sizes_fixed"], e["face_index"]), ([16], False, 0))

    def test_otf(self):
        self.assertEqual(entry("otf")["format"], "otf")

    def test_svf(self):
        pre, jam = entry("svf_pre"), entry("svf_jamo")
        self.assertEqual((pre["source_kind"], pre["sizes"], pre["svf"]["bpp"]), ("svf-precomposed", [16], 1))
        self.assertEqual((jam["source_kind"], jam["family"]), ("svf-jamo", "JAMO6J"))

    def test_bdf_kinds(self):
        self.assertEqual(entry("bdf_iso")["source_kind"], "bdf-iso10646")
        self.assertEqual(entry("bdf_ksc")["source_kind"], "bdf-ksc5601")
        self.assertEqual(entry("bdf_johab")["source_kind"], "bdf-johab")
        self.assertEqual(entry("bdf_latin")["source_kind"], "bdf-iso8859")
        self.assertEqual(entry("bdf_iso")["bdf"]["box"], [16, 16])
        p = os.path.join(ROOT, "jis.bdf")
        with open(p, "w") as f:
            f.write(head(F["bdf_latin"]).decode().replace("ISO8859", "JISX0208.1990"))
        e = detect.detect_file(p, "jis.bdf")[0]
        self.assertEqual((e["source_kind"], e["label"]), ("other", "BDF (jisx0208.1990): not convertible"))

    def test_bdf_sizes_are_probed_not_computed(self):
        def bdf(path, props, size_line):   # 18x21 box, one glyph "A" of 21 rows, registry ISO10646
            out = ["STARTFONT 2.1", "FONT -t", size_line, "FONTBOUNDINGBOX 18 21 0 -4", "STARTPROPERTIES %d" % (len(props) + 3),
                   "FONT_ASCENT 17", "FONT_DESCENT 4", 'CHARSET_REGISTRY "ISO10646"'] + props + ["ENDPROPERTIES", "CHARS 1", "STARTCHAR A",
                   "ENCODING 65", "SWIDTH 500 0", "DWIDTH 18 0", "BBX 18 21 0 -4", "BITMAP"] + ["FFFFC0"] * 21 + ["ENDCHAR", "ENDFONT", ""]
            with open(path, "w") as f:
                f.write("\n".join(out))
        p = os.path.join(ROOT, "nopx.bdf")
        bdf(p, ["POINT_SIZE 120"], "SIZE 12 75 75")      # no PIXEL_SIZE: FreeType opens 12, not the box's 21
        e = detect.detect_file(p, "nopx.bdf")[0]
        self.assertEqual((e["sizes"], e["sizes_fixed"]), ([12], True))
        self.assertEqual(e["sizes"], detect.bitmap_strikes(p))
        q = os.path.join(ROOT, "huge.bdf")
        bdf(q, ["PIXEL_SIZE 200"], "SIZE 200 75 75")     # opens only at 200: outside 4..96
        e = detect.detect_file(q, "huge.bdf")[0]
        self.assertEqual(e["sizes"], [])
        self.assertEqual(e["label"], "BDF (iso10646); no openable size")
        self.assertEqual(e["source_kind"], "bdf-iso10646")

    def test_read_name_falls_back_to_the_stem(self):
        from fontTools.fontBuilder import FontBuilder
        fb = FontBuilder(1000, isTTF=True)
        fb.setupGlyphOrder([".notdef", "A"])
        fb.setupCharacterMap({0x41: "A"})
        from fontTools.ttLib.tables._g_l_y_f import Glyph
        fb.setupGlyf({".notdef": Glyph(), "A": Glyph()})
        fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 0)})
        fb.setupHorizontalHeader(ascent=800, descent=-200)
        fb.setupOS2()
        fb.setupPost()
        fb.setupNameTable({"familyName": "나눔고딕", "styleName": "굵게"}, mac=False)
        p = os.path.join(ROOT, "Korean-Name.ttf")
        fb.save(p)
        self.assertEqual(detect.read_name(p)[:2], ("나눔고딕", "굵게"))     # non-ASCII names are kept as they are
        q = os.path.join(ROOT, "No-Name.ttf")
        fb.font["name"].names = []
        fb.save(q)
        self.assertEqual(detect.read_name(q)[:2], ("No-Name", ""))          # no usable name: the stem, style ""

    def test_dos_raw_is_probable_with_candidates(self):
        e = entry("dos_raw")
        self.assertEqual(e["label"], "probable DOS Johab (844, 844-ihnm)")
        self.assertEqual(e["dos"], {"candidates": ["844", "844-ihnm"], "faces": [0]})
        self.assertEqual(e["sizes"], [16])

    def test_eng_and_fnt_and_unknown(self):
        self.assertEqual(entry("dos_eng")["format"], "eng")
        self.assertEqual(entry("fnt")["format"], "fnt")
        p = os.path.join(ROOT, "junk.bin")
        with open(p, "wb") as f:
            f.write(b"hello")
        self.assertEqual(detect.detect_file(p, "junk.bin")[0]["label"], "unknown (68656c6c6f)")

    def test_txt_is_never_a_font(self):
        self.assertEqual(entry("list")["format"], "list")
        self.assertEqual(entry("ttf_licence")["format"], "licence")

    def test_unreadable_does_not_raise(self):
        p = os.path.join(ROOT, "bad.ttf")
        with open(p, "wb") as f:
            f.write(b"\x00\x01\x00\x00" + b"\xff" * 40)
        e = detect.detect_file(p, "bad.ttf")[0]
        self.assertEqual(e["format"], "unreadable")
        self.assertTrue(e["label"].startswith("unreadable: "))

    @unittest.skipUnless(fixtures.HAS_PCF, "no /usr/share/fonts/X11/misc/18x18ko.pcf.gz on this host")
    def test_pcf_strikes_through_gzip(self):
        e = entry("pcf")                                   # the .pcf.gz as uploaded: gzip undone for sniffing, FreeType reads it
        self.assertEqual((e["format"], e["sizes"], e["sizes_fixed"]), ("pcf", [18], True))
        self.assertTrue(e["path"].endswith("18x18ko.pcf.gz"))


class FixRoundOneTest(FixtureCase):
    """The Task 3 fix round 1: caps, keep-every-file, DOS layouts, .gz probes, fewer opens, TTC cap, registry."""

    # item 1: gzip and size caps

    def test_max_decompressed_is_128_mib(self):
        self.assertEqual(detect.MAX_DECOMPRESSED, 128 << 20)
        self.assertEqual(detect._MAX_HEAD, 64 * 1024)

    def test_a_gzip_past_the_cap_is_one_unreadable_entry(self):
        import gzip
        p = os.path.join(ROOT, "bomb.bdf.gz")
        with gzip.open(p, "wb") as f:
            f.write(b"STARTFONT 2.1\n" + bytes(3 << 20))
        with mock.patch.object(detect, "MAX_DECOMPRESSED", 1 << 20):
            out = detect.detect_file(p, "bomb.bdf.gz")
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["format"], out[0]["label"], out[0]["source_kind"]),
                         ("unreadable", "too large (> 1 MiB decompressed)", "other"))

    def test_a_decompressing_read_stops_at_the_cap(self):
        import gzip
        p = os.path.join(ROOT, "big.bin.gz")
        with gzip.open(p, "wb") as f:
            f.write(bytes(200 << 10))
        with mock.patch.object(detect, "MAX_DECOMPRESSED", 100 << 10):
            with self.assertRaises(detect.TooLarge):
                detect._read_bytes(p, True)
            with self.assertRaises(detect.TooLarge):
                detect.gunzip_head(p)
        self.assertEqual(len(detect._read_bytes(p, True)), 200 << 10)     # under the real cap it is read whole

    def test_bdf_metadata_is_read_from_a_bounded_head(self):
        body = "".join("STARTCHAR g%04X\nENCODING %d\nSWIDTH 500 0\nDWIDTH 16 0\nBBX 16 16 0 -3\nBITMAP\n%s\nENDCHAR\n"
                       % (i, i, "FFFF\n" * 16) for i in range(500))
        p = os.path.join(ROOT, "long.bdf")
        with open(p, "w") as f:
            f.write('STARTFONT 2.1\nFONT -t\nSIZE 16 75 75\nFONTBOUNDINGBOX 16 16 0 -3\nSTARTPROPERTIES 5\n'
                    'FONT_ASCENT 13\nFONT_DESCENT 3\nPIXEL_SIZE 16\nCHARSET_REGISTRY "ISO10646"\n'
                    'CHARSET_ENCODING "1"\nENDPROPERTIES\nCHARS 500\n' + body + "ENDFONT\n")
        self.assertGreater(os.path.getsize(p), 64 * 1024)
        head = detect._head_bytes(p, cut=b"STARTCHAR")
        self.assertLess(len(head), os.path.getsize(p))
        self.assertNotIn(b"STARTCHAR", head)
        self.assertIn(b"CHARSET_REGISTRY", head)                 # the properties are in the head ...
        e = detect.detect_file(p, "long.bdf")[0]
        self.assertEqual((e["source_kind"], e["bdf"]["box"]), ("bdf-iso10646", [16, 16]))

    # item 2: every file yields at least one entry

    def test_mz_with_no_openable_face_still_gets_one_entry(self):
        p = os.path.join(ROOT, "junk.exe")
        with open(p, "wb") as f:
            f.write(b"MZ" + bytes(500))
        out = detect.detect_file(p, "junk.exe")
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["format"], out[0]["source_kind"], out[0]["label"]),
                         ("fon", "other", "Windows FON; no openable face"))

    # item 3: a DOS raw entry always has a usable answer

    def test_no_layout_fits_becomes_unknown(self):
        p = os.path.join(ROOT, "nofit.fnt")
        with open(p, "wb") as f:
            f.write(b"\xff" * 11520)          # every glyph row inked: no 844 fit survives
        e = detect.detect_file(p, "nofit.fnt")[0]
        self.assertEqual((e["format"], e["source_kind"]), ("unknown", "other"))
        self.assertEqual(e["label"], "unknown (11520 bytes; no DOS layout fits)")

    def test_only_none_surviving_is_not_convertible(self):
        p = os.path.join(ROOT, "none15360.fnt")
        with open(p, "wb") as f:
            f.write(bytes(15360))
        with mock.patch.object(detect, "dos_candidates", lambda data: ["none"]):
            e = detect.detect_file(p, "none15360.fnt")[0]
        self.assertEqual((e["format"], e["source_kind"], e["label"]),
                         ("dos-raw", "other", "HBIOS 12x24 English font, not convertible"))
        self.assertEqual(e["dos"], {"candidates": ["none"], "faces": [0]})
        self.assertEqual(e["sizes"], [])

    def test_dokkaebi_two_faces_at_15360(self):
        p = os.path.join(ROOT, "HANGUL16.FNT")
        with open(p, "wb") as f:
            f.write(bytes(15360))
        out = detect.detect_file(p, "HANGUL16.FNT")
        self.assertEqual(len(out), 2)
        self.assertEqual([e["face_index"] for e in out], [0, 1])
        self.assertEqual(out[0]["dos"], {"candidates": ["dkb-printer-7x2x2", "none"], "faces": [0, 1]})
        self.assertEqual(out[0]["label"], "probable DOS Johab (dkb-printer-7x2x2, none)")
        self.assertEqual((out[0]["sizes"], out[1]["sizes"]), ([16], [16]))

    def test_dos_raw_behind_gzip(self):
        p = gzip_file(os.path.join(ROOT, "HAN.FNT.gz"), F["dos_raw"])
        e = detect.detect_file(p, "HAN.FNT.gz")[0]
        self.assertEqual((e["format"], e["source_kind"], e["label"]),
                         ("dos-raw", "dos-raw", "probable DOS Johab (844, 844-ihnm)"))
        self.assertEqual(e["sizes"], [16])
        self.assertTrue(e.get("gzip"))
        self.assertTrue(e["path"].endswith("HAN.FNT.gz"))

    # item 4: a non-PCF .gz source is probed on its decompressed bytes

    def test_a_bdf_gz_is_probed_on_its_decompressed_bytes(self):
        p = gzip_file(os.path.join(ROOT, "iso.bdf.gz"), F["bdf_iso"])
        e = detect.detect_file(p, "iso.bdf.gz")[0]
        self.assertEqual((e["format"], e["source_kind"], e["sizes"]),
                         ("bdf", "bdf-iso10646", [16]))          # the plain fixture opens at 16 too
        self.assertTrue(e.get("gzip"))
        self.assertTrue(e["path"].endswith("iso.bdf.gz"))
        self.assertNotIn("no openable size", e["label"])

    def test_a_ttf_gz_is_detected_as_ttf_with_its_name(self):
        p = gzip_file(os.path.join(ROOT, "Nanum.ttf.gz"), F["ttf"])
        e = detect.detect_file(p, "Nanum.ttf.gz")[0]
        self.assertEqual((e["format"], e["family"], e["style"]), ("ttf", "NanumGothic", "Bold"))
        self.assertEqual((e["sizes"], e["sizes_fixed"]), ([16], False))
        self.assertTrue(e.get("gzip"))
        self.assertTrue(e["path"].endswith("Nanum.ttf.gz"))

    def test_a_pcf_gz_stays_compressed(self):
        if not fixtures.HAS_PCF:
            self.skipTest("no 18x18ko.pcf.gz on this host")
        e = entry("pcf")
        self.assertEqual((e["format"], e["sizes"]), ("pcf", [18]))
        self.assertFalse(e.get("gzip", False))                  # FreeType reads .pcf.gz itself

    # item 5: few Pillow opens

    def test_a_bdf_is_opened_once_at_its_header_size(self):
        calls = []
        real = detect._open_font

        def spy(path, size, index=0, data=None):
            calls.append(size)
            return real(path, size, index, data)

        with mock.patch.object(detect, "_open_font", spy):
            e = detect.detect_file(F["bdf_iso"], "bdf/iso.bdf")[0]
        self.assertEqual(e["sizes"], [16])
        self.assertEqual(calls, [16])                            # the PIXEL_SIZE hint verifies first try, no scan

    def test_a_pcf_header_names_its_one_strike(self):
        if not fixtures.HAS_PCF:
            self.skipTest("no 18x18ko.pcf.gz on this host")
        import gzip
        with gzip.open(F["pcf"], "rb") as f:
            head = f.read(detect._MAX_HEAD)
        self.assertEqual(detect._pcf_pixel_hint(head), 18)
        self.assertEqual(detect.bitmap_strikes(F["pcf"], hint=18), [18])

    def test_pillow_name_reuses_the_first_open(self):
        calls = []
        real = detect._open_font

        def spy(path, size, index=0, data=None):
            calls.append(size)
            return real(path, size, index, data)

        with mock.patch.object(detect, "_open_font", spy):
            detect._pillow_name(F["bdf_iso"], 16)
        self.assertEqual(len(calls), 1)                          # one open, no 4..96 re-scan

    # item 6: the TTC face list is capped, like FON

    def test_ttc_two_faces(self):
        p = ttc(os.path.join(ROOT, "two.ttc"), 2)
        out = detect.detect_file(p, "two.ttc")
        self.assertEqual(len(out), 2)
        self.assertEqual((out[0]["format"], out[0]["label"], out[0]["source_kind"], out[0]["family"]),
                         ("ttc", "TTC face 0", "outline", "Ttc"))
        self.assertEqual((out[1]["face_index"], out[1]["source_kind"], out[1]["label"]),
                         (1, "other", "face index 1: not convertible in v1"))

    def test_the_ttc_face_list_is_capped_at_64(self):
        p = ttc(os.path.join(ROOT, "many.ttc"), 70)
        out = detect.detect_file(p, "many.ttc")
        self.assertEqual(len(out), 64)
        self.assertEqual([e["face_index"] for e in out], list(range(64)))
        self.assertTrue(out[-1]["label"].endswith("; more faces not listed"), out[-1]["label"])
        short = detect.detect_file(ttc(os.path.join(ROOT, "two2.ttc"), 2), "two2.ttc")
        self.assertNotIn("more faces not listed", short[-1]["label"])   # a short list says nothing

    # item 9: FON, HBF, an SVF with a bad JSET

    def test_fon_face(self):
        p = os.path.join(ROOT, "fixture.fon")
        with open(p, "wb") as f:
            f.write(fon_bytes())
        e = detect.detect_file(p, "fixture.fon")[0]
        self.assertEqual((e["format"], e["source_kind"], e["label"]), ("fon", "bitmap", "Windows FON face 0"))
        self.assertEqual(e["family"], "Fixture")
        self.assertEqual((e["sizes"], e["sizes_fixed"]), ([13], True))

    def test_hbf(self):
        e = entry("hbf")
        self.assertEqual((e["format"], e["source_kind"], e["sizes"], e["sizes_fixed"]), ("hbf", "hbf", [16], True))

    def test_svf_with_a_bad_jset_falls_back_to_precomposed(self):
        import jamoset
        stride = ((16 * 1 + 7) // 8) * 16
        p = os.path.join(ROOT, "badjset.svf")
        with open(p, "wb") as f:
            f.write(jamoset.write_svfn(16, 16, 12, [(0x41, bytes(stride), 16, 0, 16)], b"\x00" * 8))   # no JSET magic
        e = detect.detect_file(p, "badjset.svf")[0]
        self.assertEqual((e["format"], e["source_kind"], e["svf"]["bpp"]), ("svf", "svf-precomposed", 1))
        self.assertEqual(e["sizes"], [16])

    def test_svf_versions_are_named(self):
        """A v3 SVFN is "SVF v3"; the same faces written as v2 are "svf2" entries the copy route converts."""
        import fixtures
        for key, kind in (("svf_pre", "svf-precomposed"), ("svf_jamo", "svf-jamo")):
            e3 = entry(key)
            self.assertEqual((e3["format"], e3["label"], e3["source_kind"], e3["svf"]["version"]),
                             ("svf", "SVF v3", kind, 3))
            p = os.path.join(ROOT, key + "-v2.svf")
            with open(p, "wb") as f:
                f.write(fixtures.v2_face(head(F[key])))
            e2 = detect.detect_file(p, key + "-v2.svf")[0]
            self.assertEqual((e2["format"], e2["label"], e2["source_kind"], e2["svf"]["version"]),
                             ("svf2", "SVF v2: converted to v3", kind, 2))
            self.assertEqual({k: e2["svf"][k] for k in ("bpp", "cell", "ascent", "glyphs")},
                             {k: e3["svf"][k] for k in ("bpp", "cell", "ascent", "glyphs")})
            cov = detect._coverage_of_entry(p, e2)
            self.assertIsNotNone(cov)
            self.assertEqual(cov, detect._coverage_of_entry(F[key], e3))

    def _svf_bytes(self, name, data):
        p = os.path.join(ROOT, name)
        with open(p, "wb") as f:
            f.write(data)
        return detect.detect_file(p, name)[0]

    def test_svf_jset1_small_kept(self):
        import fixtures
        e = self._svf_bytes("hgkey-j1.svf", fixtures.jset1_face())
        self.assertEqual((e["source_kind"], e["svf"]["jset_version"], e["label"]), ("svf-jamo", 1, "SVF v3"))

    def test_svf_jset1_big_is_kept_too(self):
        # v2 is for memory-constrained targets and asked for explicitly: detect offers no automatic conversion
        import fixtures
        e = self._svf_bytes("nsq-j1.svf", fixtures.jset1_big_face())
        self.assertEqual((e["source_kind"], e["svf"]["jset_version"], e["label"]), ("svf-jamo", 1, "SVF v3"))

    def test_svf_jset2_is_jamo(self):
        import fixtures, svf2to3
        data = svf2to3.convert(fixtures.jset1_big_face(), "default", jset_version=2)
        e = self._svf_bytes("nsq-j2.svf", data)
        self.assertEqual((e["source_kind"], e["svf"]["jset_version"], e["label"]), ("svf-jamo", 2, "SVF v3"))

    def test_svf_jset1_bad_block_is_precomposed(self):
        import fixtures, jamoset
        data = fixtures.jset1_face()
        f = jamoset.parse_svfn(data)
        bad = bytearray(data)
        bad[data.index(f.jset) + 12] = 0xFF      # leadClass[0] beyond the block's lead classes
        e = self._svf_bytes("badlc.svf", bytes(bad))
        self.assertEqual(e["source_kind"], "svf-precomposed")
        self.assertIsNone(e["svf"]["jset_version"])

    def test_svf_jamo_missing_a_piece_glyph_is_not_a_jamo_set(self):
        # tools/svfline.py uses a JSET only when every non-blank piece glyph is present; detect follows it
        import jamoset
        f = jamoset.parse_svfn(head(F["svf_jamo"]))
        t = jamoset.unpack(f.jset)
        piece = next(jamoset.PIECE_BASE + n for n in t.init_piece if n != jamoset.BLANK)
        glyphs = [(cp, g, *f.metrics.get(cp, (f.cell_w, 0, f.cell_w))) for cp, g in f.glyphs.items() if cp != piece]
        p = os.path.join(ROOT, "missingpiece.svf")
        with open(p, "wb") as out:
            out.write(jamoset.write_svfn(f.cell_w, f.cell_h, f.ascent, glyphs, f.jset, bpp=f.bpp))
        e = detect.detect_file(p, "missingpiece.svf")[0]
        self.assertEqual(e["source_kind"], "svf-precomposed")
        cov = detect.coverage_svf(jamoset.parse_svfn(head(p)))
        self.assertLess(cov["all"], 11172)

    # item 7 and 10: registry-encoding, and the FONT name as a fallback

    def test_bdf_registry_carries_its_encoding(self):
        self.assertEqual((entry("bdf_iso")["bdf"]["registry"], entry("bdf_iso")["label"]),
                         ("iso10646-1", "BDF (iso10646)"))
        self.assertEqual(entry("bdf_ksc")["bdf"]["registry"], "ksx1001.1998-1")

    def test_a_bdf_without_a_charset_property_uses_the_font_name(self):
        p = os.path.join(ROOT, "xlfd.bdf")
        with open(p, "w") as f:
            f.write("STARTFONT 2.1\nFONT -misc-fixed-medium-r-normal--16-120-100-100-c-80-iso10646-1\n"
                    "SIZE 16 75 75\nFONTBOUNDINGBOX 16 16 0 -3\nSTARTPROPERTIES 1\nFONT_ASCENT 13\nENDPROPERTIES\n"
                    "CHARS 0\nENDFONT\n")
        e = detect.detect_file(p, "xlfd.bdf")[0]
        self.assertEqual((e["source_kind"], e["bdf"]["registry"]), ("bdf-iso10646", "iso10646-1"))
        self.assertTrue(e["label"].startswith("BDF (iso10646)"))


class FixRoundTwoTest(FixtureCase):
    """Fix round 2 (task-3-fix2.md): O1 TTC header count, O2 .gz stems, O3 short files, O4 HBF fields, O5 PCF strings."""

    # O1: the TTC face count comes from the header, without building a face per count

    def test_the_ttc_count_comes_from_the_header(self):
        p = ttc_claiming(os.path.join(ROOT, "claim.ttc"), 20000)
        started = time.monotonic()
        out = detect.detect_file(p, "claim.ttc")
        elapsed = time.monotonic() - started
        self.assertEqual(len(out), 64)
        self.assertEqual([e["face_index"] for e in out], list(range(64)))
        self.assertEqual((out[0]["format"], out[0]["source_kind"], out[0]["family"]), ("ttc", "outline", "Ttc"))
        self.assertTrue(out[-1]["label"].endswith("; more faces not listed"), out[-1]["label"])
        self.assertLess(elapsed, 1.0)

    def test_a_one_face_ttc_header_lists_one_face(self):
        out = detect.detect_file(ttc_claiming(os.path.join(ROOT, "one.ttc"), 1), "one.ttc")
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0]["format"], out[0]["family"]), ("ttc", "Ttc"))

    def test_a_ttc_claiming_no_faces_still_gets_one_entry(self):
        p = os.path.join(ROOT, "zero.ttc")
        with open(p, "wb") as f:
            f.write(b"ttcf" + struct.pack(">II", 0x00010000, 0))      # a header with no offsets at all
        out = detect.detect_file(p, "zero.ttc")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["format"], "unreadable")

    # O2: one trailing .gz is stripped before the extension

    def test_a_gz_stem_drops_the_inner_extension(self):
        self.assertEqual(detect._stem("fonts/iso.bdf.gz"), "iso")
        self.assertEqual(detect._stem("fonts/iso.bdf"), "iso")
        p = gzip_file(os.path.join(ROOT, "iso.bdf.gz"), F["bdf_iso"])
        self.assertEqual(detect.detect_file(p, "iso.bdf.gz")[0]["family"], "iso")

    def test_read_name_stem_fallback_drops_one_gz(self):
        import gzip
        src = nameless_ttf(os.path.join(ROOT, "Nameless.ttf"))
        p = gzip_file(os.path.join(ROOT, "Nameless.ttf.gz"), src)
        with gzip.open(p, "rb") as f:
            data = f.read()
        self.assertEqual(detect.read_name(p, 0, data)[:1], ("Nameless",))

    # O3: a file shorter than a FNT header is not a FNT

    def test_a_short_file_is_not_a_fnt(self):
        short = b"\x00\x02" + b"abcdefg"                  # 9 bytes: 0x0200 at 0, far short of 66
        self.assertEqual(detect.sniff(short), "unknown")
        p = os.path.join(ROOT, "short.fnt")
        with open(p, "wb") as f:
            f.write(short)
        calls = []

        def spy(*a, **k):
            calls.append(a)
            raise AssertionError("Pillow probed a 9 byte file")

        with mock.patch.object(detect, "_open_font", spy):
            e = detect.detect_file(p, "short.fnt")[0]
        self.assertEqual(e["format"], "unknown")
        self.assertEqual(calls, [])
        at66 = struct.pack("<H", 0x0200) + b" " * 64      # bytes 6..65 all printable: the shortest FNT head
        self.assertEqual(detect.sniff(at66), "fnt")

    # O4: an HBF is only offered when bdfface.read_hbf would accept it

    def test_an_hbf_needs_the_fields_bdfface_reads(self):
        p = os.path.join(ROOT, "nobox.hbf")
        with open(p, "w") as f:
            f.write("HBF_START_FONT 1.0\nFONTBOUNDINGBOX 8 16 0 -3\nFONT_ASCENT 13\n"
                    "HBF_CODE_RANGE 0x0041-0x005A ascii.bin 0\nHBF_END_FONT\n")
        e = detect.detect_file(p, "nobox.hbf")[0]
        self.assertEqual((e["format"], e["source_kind"], e["label"]),
                         ("hbf", "other", "HBF: no HBF_BITMAP_BOUNDING_BOX"))   # no FONTBOUNDINGBOX fallback
        self.assertEqual(e["sizes"], [])
        q = os.path.join(ROOT, "noascent.hbf")
        with open(q, "w") as f:
            f.write("HBF_START_FONT 1.0\nHBF_BITMAP_BOUNDING_BOX 8 16 0 -3\n"
                    "HBF_CODE_RANGE 0x0041-0x005A ascii.bin 0\nHBF_END_FONT\n")
        e = detect.detect_file(q, "noascent.hbf")[0]
        self.assertEqual((e["source_kind"], e["label"]), ("other", "HBF: no FONT_ASCENT"))
        self.assertEqual(entry("hbf")["source_kind"], "hbf")     # the complete fixture still converts

    # O5: the PCF string table is at its layout's offset, not the first printable byte

    def test_a_pcf_hint_uses_the_properties_table_layout(self):
        self.assertEqual(detect._pcf_pixel_hint(pcf_properties(12)), 12)
        self.assertEqual(detect._pcf_pixel_hint(pcf_properties(18)), 18)

    @unittest.skipUnless(fixtures.HAS_PCF, "no /usr/share/fonts/X11/misc/18x18ko.pcf.gz on this host")
    def test_a_pcf_takes_two_opens(self):
        calls = []
        real = detect._open_font

        def spy(path, size, index=0, data=None):
            calls.append(size)
            return real(path, size, index, data)

        with mock.patch.object(detect, "_open_font", spy):
            e = detect.detect_file(F["pcf"], os.path.relpath(F["pcf"], ROOT))[0]
        self.assertEqual(e["sizes"], [18])
        self.assertEqual(calls, [18, 18])                # the verified hint, then the name from that same size


class CoverageTest(FixtureCase):
    def test_outline_coverage(self):
        c = detect.coverage_outline(F["ttf"], 0)
        self.assertEqual((c["ascii"], c["ks2350"], c["all"]), (95, 2350, 11172))
    def test_composite(self):
        self.assertEqual(detect.composite_test(F["composite"])[0], True)
        self.assertEqual(detect.composite_test(F["ttf"])[0], False)
        self.assertEqual(detect.composite_test(F["otf"]), (False, 0, 0))        # CFF: no glyf table
        self.assertEqual(detect.composite_test(F["composite"])[1:], (66, 66))
    def test_bdf_and_svf_coverage(self):
        self.assertEqual(detect.coverage_bdf(bdfface.read_bdf(F["bdf_iso"])[1])["all"], 2)
        self.assertEqual(detect.coverage_svf(jamoset.parse_svfn(head(F["svf_jamo"])))["all"], 11172)

class ScanTest(FixtureCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fonts = detect.scan(ROOT)
        cls.by_path = {f["path"]: f for f in cls.fonts}
    def test_ids_and_kinds(self):
        self.assertEqual([f["id"] for f in self.fonts][:3], ["f01", "f02", "f03"])
        self.assertEqual(self.by_path["composite/Composite.ttf"]["source_kind"], "outline-composite")
        self.assertEqual(self.by_path["composite/Composite.ttf"]["jamo"], "native (composite)")
        self.assertEqual(self.by_path["nanum/NanumGothic-Bold.ttf"]["jamo"], "compat 51/51")
    def test_licences(self):
        self.assertEqual([l["path"] for l in self.by_path["nanum/NanumGothic-Bold.ttf"]["licences"]], ["nanum/OFL.txt"])
        self.assertEqual(self.by_path["nolic/NoLicence.ttf"]["licences"], [])
        self.assertEqual([l["path"] for l in self.by_path["bdf/iso.bdf"]["licences"]], ["bdf/COPYING"])
    def test_companions(self):
        self.assertEqual(self.by_path["dos/HAN.FNT"]["companions"], [self.by_path["dos/ENG.FNT"]["id"]])
        self.assertIn(self.by_path["bdf/latin.bdf"]["id"], self.by_path["bdf/ksc.bdf"]["companions"])
        self.assertIn(self.by_path["hbf/ascii.hbf"]["id"], self.by_path["bdf/ksc.bdf"]["companions"])
    def test_txt_entries(self):
        self.assertEqual(self.by_path["list.txt"]["format"], "list")
        self.assertEqual(self.by_path["nanum/OFL.txt"]["format"], "licence")


class _MaskCore:
    """The ImagingCore-shaped object Pillow 10's `getmask` returns: mode, size and bytes()."""

    mode = "1"

    def __init__(self, w, h, data):
        self.size = (w, h)
        self._data = data

    def __bytes__(self):
        return self._data


class _BoxFont:
    """A fake Pillow font: NOTDEF_CHAR and "X" have the same tight 4x4 box mask, but X sits 4 rows higher."""

    size = 16

    def getmetrics(self):
        return (13, 3)

    def getmask(self, ch, mode="1"):
        return _MaskCore(4, 4, b"\xf0\xf0\xf0\xf0")

    def getbbox(self, ch, anchor="ls"):
        return (0, -4, 4, 0) if ch == detect.NOTDEF_CHAR else (0, -8, 4, -4)


def gzip_bytes(path, data):
    """@p data gzipped to @p path (an explicit size, unlike the gzip_file helper)."""
    import gzip
    with gzip.open(path, "wb") as g:
        g.write(data)
    return path


def hbf_naming(path, binname):
    """An HBF whose one code range names @p binname (which may be a hostile path)."""
    with open(path, "w") as f:
        f.write("HBF_START_FONT 1.0\nHBF_BITMAP_BOUNDING_BOX 8 16 0 -3\nFONTBOUNDINGBOX 8 16 0 -3\n"
                "FONT_ASCENT 13\nFONT_DESCENT 3\nHBF_CODE_RANGE 0x0001-0x005A %s 0\nHBF_END_FONT\n" % binname)
    return path


def boundary_ttf(path, composite, simple):
    """A TTF with @p composite composite syllables and @p simple plain ones (drawn = composite + simple).

    Each composite syllable carries the component count its final needs: 2 without one, 3 with (the composite test
    reads that count from `glyf` alone).
    """
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent

    def rect():
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((100, 0))
        pen.lineTo((100, 100))
        pen.closePath()
        return pen.glyph()

    order = [".notdef", "piece"]
    glyphs = {".notdef": Glyph(), "piece": rect()}
    cmap = {}
    for i in range(composite + simple):
        cp = 0xAC00 + i
        name = "uni%04X" % cp
        order.append(name)
        cmap[cp] = name
        if i < composite:
            g = Glyph()
            g.numberOfContours = -1
            g.components = []
            for _ in range(3 if (cp - 0xAC00) % 28 else 2):
                c = GlyphComponent()
                c.glyphName, c.x, c.y, c.flags = "piece", 0, 0, 0
                g.components.append(c)
            glyphs[name] = g
        else:
            glyphs[name] = rect()
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (1000, 0) for n in order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": "Boundary", "styleName": "Regular"})
    fb.save(path)
    return path


def nested_ttf(path, depth):
    """A TTF whose every syllable is 2 or 3 copies of a `depth`-deep chain of composites (the amp.py shape).

    Flattening one syllable walks 2**depth sub-glyphs, so a test that finishes at once proves the composite test
    reads the `glyf` table alone.
    """
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent

    def square():
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((10, 0))
        pen.lineTo((10, 10))
        pen.lineTo((0, 10))
        pen.closePath()
        return pen.glyph()

    def composite(names):
        g = Glyph()
        g.numberOfContours = -1
        g.components = []
        for i, n in enumerate(names):
            c = GlyphComponent()
            c.glyphName, c.x, c.y, c.flags = n, i * 5, 0, 0x4
            g.components.append(c)
        return g

    names = [".notdef", "g0"] + ["g%d" % k for k in range(1, depth + 1)] + ["sylA", "sylB"]
    glyphs = {".notdef": square(), "g0": square()}
    for k in range(1, depth + 1):
        glyphs["g%d" % k] = composite(["g%d" % (k - 1)] * 2)
    top = "g%d" % depth
    glyphs["sylA"] = composite([top, top])
    glyphs["sylB"] = composite([top, top, top])
    for glyph in glyphs.values():                 # the bounds by hand: a composite's own recalc walks every leaf
        if glyph.numberOfContours > 0:
            glyph.recalcBounds(None)
        else:
            glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax = 0, 0, 10, 10
    cmap = {cp: ("sylB" if (cp - 0xAC00) % 28 else "sylA") for cp in range(0xAC00, 0xD7A4)}
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs, calcGlyphBounds=False)
    fb.setupHorizontalMetrics({n: (500, 0) for n in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": "Nested", "styleName": "Regular"})
    fb.font.recalcBBoxes = False     # recalculating them at save time would walk the whole nested chain
    fb.save(path)
    return path


def missing_component_ttf(path):
    """A TTF whose one composite syllable names a glyph index past numGlyphs (fontTools cannot resolve it)."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent
    from fontTools.ttLib import TTFont

    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((10, 0))
    pen.lineTo((10, 10))
    pen.closePath()
    piece = pen.glyph()
    order = [".notdef", "piece", "uniAC00"]
    g = Glyph()
    g.numberOfContours = -1
    g.components = []
    for _ in range(2):
        c = GlyphComponent()
        c.glyphName, c.x, c.y, c.flags = "piece", 0, 0, 0
        g.components.append(c)
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0xAC00: "uniAC00"})
    fb.setupGlyf({".notdef": Glyph(), "piece": piece, "uniAC00": g})
    fb.setupHorizontalMetrics({n: (500, 0) for n in order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": "Missing", "styleName": "Regular"})
    fb.save(path)
    font = TTFont(path)
    base = font.reader.tables["glyf"].offset + font["loca"][2]
    font.close()
    raw = bytearray(head(path))
    struct.pack_into(">H", raw, base + 12, 99)          # the first component's glyph index: past numGlyphs
    with open(path, "wb") as f:
        f.write(bytes(raw))
    return path


class Task4FixOneTest(FixtureCase):
    """Task 4 fix round 1: the HBF reference guard, johab and `.gz` coverage, scan robustness and cost, the picture
    test's placement, the licence walk and the 95 % boundary."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # the extra sources the scan-level tests read, written before the one scan of the tree
        os.makedirs(os.path.join(ROOT, "gz"), exist_ok=True)
        os.makedirs(os.path.join(ROOT, "gzeng"), exist_ok=True)
        cls.gz_composite = gzip_bytes(os.path.join(ROOT, "gz", "Composite.ttf.gz"), head(F["composite"]))
        cls.gz_iso = gzip_bytes(os.path.join(ROOT, "gz", "iso.bdf.gz"), head(F["bdf_iso"]))
        gzip_bytes(os.path.join(ROOT, "gzeng", "ENG.FNT.gz"), head(F["dos_eng"]))
        cls.fonts = detect.scan(ROOT)
        cls.by_path = {f["path"]: f for f in cls.fonts}

    # item 1: an uploaded HBF must not read a file outside its own folder

    def test_hbf_refs_safe_allows_the_fixture(self):
        self.assertTrue(detect.hbf_refs_safe(F["hbf"]))

    def test_hbf_refs_safe_refuses_a_parent_reference(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sub"))
            with open(os.path.join(d, "secret.bin"), "wb") as f:
                f.write(b"\xff" * 32)
            self.assertFalse(detect.hbf_refs_safe(hbf_naming(os.path.join(d, "sub", "x.hbf"), "../secret.bin")))

    def test_hbf_refs_safe_refuses_an_absolute_name(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(detect.hbf_refs_safe(hbf_naming(os.path.join(d, "x.hbf"), "/dev/zero")))

    def test_hbf_refs_safe_refuses_a_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "real.bin"), "wb") as f:
                f.write(b"\xff" * 32)
            os.symlink(os.path.join(d, "real.bin"), os.path.join(d, "link.bin"))
            self.assertFalse(detect.hbf_refs_safe(hbf_naming(os.path.join(d, "x.hbf"), "link.bin")))

    def test_hbf_refs_safe_refuses_an_oversize_bitmap(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "big.bin"), "wb") as f:
                f.write(b"\xff" * 8192)
            p = hbf_naming(os.path.join(d, "x.hbf"), "big.bin")
            with mock.patch.object(detect, "MAX_DECOMPRESSED", 4096):
                self.assertFalse(detect.hbf_refs_safe(p))
            self.assertTrue(detect.hbf_refs_safe(p))          # under the real cap it is fine

    def test_hbf_refs_safe_refuses_a_gz_bitmap(self):
        with tempfile.TemporaryDirectory() as d:
            gzip_bytes(os.path.join(d, "x.bin.gz"), b"\xff" * 32)
            self.assertFalse(detect.hbf_refs_safe(hbf_naming(os.path.join(d, "x.hbf"), "x.bin.gz")))

    def test_an_unsafe_hbf_is_refused_without_reading_any_bitmap(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "secret.bin"), "wb") as f:
                f.write(b"\xff" * 32)
            os.makedirs(os.path.join(d, "sub"))
            hbf_naming(os.path.join(d, "sub", "x.hbf"), "../secret.bin")
            with mock.patch.object(detect.bdfface, "read_hbf") as m:
                fonts = detect.scan(d)
            self.assertFalse(m.called)
        e = {f["path"]: f for f in fonts}["sub/x.hbf"]
        self.assertEqual(e["source_kind"], "hbf")
        self.assertEqual(e["label"], "HBF: unsafe bitmap reference")
        self.assertIsNone(e["coverage"])

    # item 2: bdf-johab draws every syllable from jamo, like DOS raw

    def test_bdf_johab_coverage_is_composed(self):
        e = self.by_path["bdf/johab.bdf"]
        self.assertEqual(e["coverage"], {"ascii": 0, "ks2350": 2350, "all": 11172, "compat": 51})
        self.assertEqual(e["jamo"], "native (hanterm-johab)")

    # item 3: a `.gz` source's decompressed bytes are read once and shared

    def test_a_gz_outline_keeps_its_composite_route(self):
        e = self.by_path["gz/Composite.ttf.gz"]
        self.assertEqual(e["source_kind"], "outline-composite")
        self.assertEqual((e["coverage"]["all"], e["jamo"]), (66, "native (composite)"))
        import gzip
        with gzip.open(self.gz_composite, "rb") as f:
            data = f.read()
        self.assertEqual(detect.composite_test(self.gz_composite, 0, data), (True, 66, 66))
        self.assertEqual(detect.coverage_outline(self.gz_composite, 0, data)["all"], 66)

    def test_a_gz_bdf_has_the_plain_files_coverage(self):
        self.assertEqual(self.by_path["gz/iso.bdf.gz"]["coverage"], self.by_path["bdf/iso.bdf"]["coverage"])
        self.assertEqual(self.by_path["gz/iso.bdf.gz"]["coverage"]["all"], 2)

    # item 4: one unreadable file must not crash the scan

    def test_an_unreadable_file_does_not_crash_the_scan(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copyfile(F["ttf"], os.path.join(d, "font.ttf"))
            p = os.path.join(d, "notes.txt")
            with open(p, "w") as f:
                f.write("hello\n")
            os.chmod(p, 0)
            self.assertFalse(detect.is_licence_text(p))
            self.assertEqual(detect._first_line(p), "")
            fonts = detect.scan(d)
        by = {f["path"]: f for f in fonts}
        self.assertEqual(by["notes.txt"]["format"], "list")
        self.assertEqual(by["font.ttf"]["licences"], [])

    # item 5(a): the licence verdict is decided once per file

    def test_a_scan_of_2000_txt_files_is_linear(self):
        d = tempfile.mkdtemp(prefix="svf-maker-scan-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        for i in range(2000):
            with open(os.path.join(d, "f%04d.txt" % i), "w") as f:
                f.write("plain text, no rights claimed\n")
        started = time.monotonic()
        fonts = detect.scan(d)
        elapsed = time.monotonic() - started
        self.assertEqual(len(fonts), 2000)
        self.assertLess(elapsed, 3.0, "scan of 2000 .txt files took %.2f s" % elapsed)

    # item 5(b) and 9: the 95 % boundary, and no per-glyph check when it is out of reach

    def test_the_composite_threshold_is_95_percent(self):
        p95 = boundary_ttf(os.path.join(ROOT, "b95.ttf"), 95, 5)
        p94 = boundary_ttf(os.path.join(ROOT, "b94.ttf"), 94, 6)
        self.assertEqual(detect.composite_test(p95), (True, 100, 95))
        self.assertEqual(detect.composite_test(p94), (False, 100, 94))
        import jamovec
        with mock.patch.object(jamovec, "composite_parts", side_effect=AssertionError("flattened")):
            self.assertEqual(detect.composite_test(p95), (True, 100, 95))    # nothing is ever flattened
            self.assertEqual(detect.composite_test(p94), (False, 100, 94))

    # item 5(c): a scan-wide coverage budget

    def test_the_coverage_budget_skips_the_rest(self):
        with mock.patch.object(detect, "SCAN_COVERAGE_BUDGET_S", 0):
            fonts = detect.scan(ROOT)
        self.assertTrue(fonts)
        for f in fonts:
            self.assertIsNone(f["coverage"], f["path"])
            self.assertTrue(f["label"].endswith("; coverage skipped (time budget)"), f["label"])

    # item 6: the picture test places glyphs in the cell, it does not compare cropped ink

    def test_the_picture_test_places_glyphs_where_mkfont_does(self):
        font = _BoxFont()
        notdef = detect._bitmap_image(font, detect.NOTDEF_CHAR).tobytes()
        self.assertTrue(detect.notdef_absent(font, detect.NOTDEF_CHAR, notdef))
        self.assertFalse(detect.notdef_absent(font, "X", notdef))      # the same box, four rows higher: present

    # item 7: a symlinked file is skipped

    def test_a_symlink_is_skipped_with_an_entry(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copyfile(F["ttf"], os.path.join(d, "real.ttf"))
            os.symlink(os.path.join(d, "real.ttf"), os.path.join(d, "link.ttf"))
            fonts = detect.scan(d)
        by = {f["path"]: f for f in fonts}
        self.assertEqual((by["link.ttf"]["label"], by["link.ttf"]["source_kind"]), ("symlink, skipped", "other"))
        self.assertEqual(by["real.ttf"]["source_kind"], "outline")     # the target itself is still detected

    # item 8: the unknown label of a `.gz` file prints the decompressed size

    def test_the_unknown_label_of_a_gz_eng_file_shows_the_decompressed_size(self):
        e = self.by_path["gzeng/ENG.FNT.gz"]
        self.assertEqual(e["format"], "unknown")
        self.assertEqual(e["label"], "unknown (2048 bytes decompressed; no DOS Johab font beside it)")

    # item 9: the parent-folder licence walk

    def test_find_licences_walks_up_to_the_nearest_folder(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sub", "deep"))
            copying, licence = os.path.join(d, "COPYING"), os.path.join(d, "sub", "LICENSE")
            for p in (copying, licence):
                with open(p, "w") as f:
                    f.write("x\n")
            font = os.path.join(d, "sub", "deep", "font.ttf")
            with open(font, "wb") as f:
                f.write(b"")
            self.assertEqual(detect.find_licences(font, [copying, licence, font]), [licence])
            self.assertEqual(detect.find_licences(font, [copying, font]), [copying])   # then the parent

    def test_find_licences_returns_every_match_of_the_nearest_folder(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sub"))
            copying, licence = os.path.join(d, "COPYING"), os.path.join(d, "LICENSE")
            for p in (copying, licence):
                with open(p, "w") as f:
                    f.write("x\n")
            other = os.path.join(d, "sub", "other.txt")
            with open(other, "w") as f:
                f.write("x\n")
            font = os.path.join(d, "font.ttf")
            with open(font, "wb") as f:
                f.write(b"")
            self.assertEqual(detect.find_licences(font, [licence, copying, other, font]), [copying, licence])


class Task4FixTwoTest(FixtureCase):
    """Task 4 fix round 2: per-file `.gz` bytes, a table-only composite test, the licence map, SVF compat, BOM, HBF."""

    # R1: a `.gz` source's bytes live for one file only

    def test_gz_bytes_are_released_between_files(self):
        import gzip
        import tracemalloc
        d = tempfile.mkdtemp(prefix="svf-maker-gzmem-")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        one = 8 << 20
        blob = gzip.compress(bytes(one))
        for i in range(12):
            with open(os.path.join(d, "f%02d.bin.gz" % i), "wb") as f:
                f.write(blob)
        tracemalloc.start()
        try:
            fonts = detect.scan(d)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertEqual(len(fonts), 12)
        self.assertLess(peak, 3 * one, "peak %.1f MiB for 12 files of %.0f MiB" % (peak / (1 << 20), one / (1 << 20)))

    # R2: a component naming a glyph the font has not got is not composite, and does not raise

    def test_a_component_naming_a_missing_glyph_is_not_composite(self):
        p = missing_component_ttf(os.path.join(ROOT, "missing.ttf"))
        verdict = detect.composite_test(p)              # must not raise
        self.assertFalse(verdict[0])
        self.assertEqual(verdict[2], 0)

    def test_a_missing_component_name_is_not_composite(self):
        class _Comp:
            def __init__(self, name):
                self.glyphName = name

        class _Glyph:
            def __init__(self, names):
                self.components = [_Comp(n) for n in names]

        self.assertTrue(detect._composite_syllable(_Glyph(["piece", "piece"]), False, {"piece"}))
        self.assertFalse(detect._composite_syllable(_Glyph(["piece", "missing"]), False, {"piece"}))
        self.assertFalse(detect._composite_syllable(_Glyph(["piece"]), False, {"piece"}))          # too few
        self.assertFalse(detect._composite_syllable(_Glyph(["piece", "piece"]), True, {"piece"}))  # a final needs 3

    # R3: a symlinked licence is ignored

    def test_a_symlinked_licence_is_ignored(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
            target = os.path.join(other, "target.txt")
            with open(target, "w") as f:
                f.write("license\n")
            shutil.copyfile(F["ttf"], os.path.join(d, "a.ttf"))
            os.symlink(target, os.path.join(d, "LICENSE.txt"))
            fonts = detect.scan(d)
        by = {f["path"]: f for f in fonts}
        self.assertEqual(by["a.ttf"]["licences"], [])
        self.assertEqual(by["LICENSE.txt"]["label"], "symlink, skipped")

    # R4: the SVF compat count includes whole compatibility jamo glyphs

    def test_svf_compat_counts_whole_compat_glyphs(self):
        p = os.path.join(REPO_DIR, "svf", "dos", "NEODG16C.SVF")
        c = detect.coverage_svf(jamoset.parse_svfn(head(p)))
        self.assertEqual((c["ks2350"], c["all"], c["compat"]), (2350, 11172, 51))
        self.assertEqual(c["ascii"], 95)

    # R5: the first line of a licence strips a leading UTF-8 BOM

    def test_first_line_strips_a_utf8_bom(self):
        p = os.path.join(ROOT, "bom.txt")
        with open(p, "wb") as f:
            f.write("\ufeffCopyright (c) 2026\n".encode("utf-8"))
        self.assertEqual(detect._first_line(p), "Copyright (c) 2026")

    # R7: an HBF with a `.gz` bitmap gets its own label

    def test_an_hbf_with_a_gz_bitmap_gets_its_own_label(self):
        with tempfile.TemporaryDirectory() as d:
            gzip_bytes(os.path.join(d, "x.bin.gz"), b"\xff" * 32)
            hbf_naming(os.path.join(d, "x.hbf"), "x.bin.gz")
            fonts = detect.scan(d)
        e = {f["path"]: f for f in fonts}["x.hbf"]
        self.assertEqual((e["source_kind"], e["label"]), ("hbf", "HBF: .gz bitmap not supported"))
        self.assertIsNone(e["coverage"])


class Task4FixTwoNestedTest(FixtureCase):
    """R2: a deeply nested composite font is decided from `glyf` alone, so it finishes at once."""

    def test_a_nested_composite_font_is_counted_without_flattening(self):
        p = nested_ttf(os.path.join(ROOT, "nested20.ttf"), 20)
        started = time.monotonic()
        verdict = detect.composite_test(p)
        elapsed = time.monotonic() - started
        self.assertEqual(verdict, (True, 11172, 11172))
        self.assertLess(elapsed, 1.0, "composite_test took %.1f s" % elapsed)

class JmapDetect(unittest.TestCase):
    """A JMAP face (JSET version 3) is an svf-jamo face; a block R8 refuses is a plain face."""

    def detect(self, *args):
        d = tempfile.mkdtemp(prefix="detect-jmap-")
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "J.SVF")
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(REPO_DIR, "tools", "svf_synth.py")] + list(args)
                           + ["--from", os.path.join(REPO_DIR, "svf", "dos", "NEODG16G.SVF"), p], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = detect.detect_file(p, "J.SVF")
        self.assertEqual(len(out), 1)
        return out[0], p

    def test_jmap_face_is_svf_jamo_version_3(self):
        for v in ("sparse3", "hybrid2", "dense4"):
            with self.subTest(v=v):
                e, p = self.detect("--jmap-variant", v)
                self.assertEqual(e["source_kind"], "svf-jamo")
                self.assertEqual(e["svf"]["jset_version"], 3)
                cov = detect.coverage_svf(detect.read_svf(head(p)))
                if v == "sparse3":      # a sparse map: only the syllables it maps (the base face has no precomposed ones)
                    self.assertLess(cov["all"], 11172)
                else:
                    self.assertEqual((cov["ks2350"], cov["all"]), (2350, 11172))

    def test_coverage_counts_only_what_a_jmap_face_draws(self):
        # sparse3 maps every 5th syllable and the base face has no precomposed syllable glyphs
        e, p = self.detect("--jmap-variant", "sparse3")
        face = detect.read_svf(head(p))
        t = detect.usable_jset(face)
        want_all = sum(1 for cp in range(0xAC00, 0xD7A4) if t.pieces(cp) is not None or cp in face.glyphs)
        want_ks = sum(1 for n in jamoset.ks_x_1001_syllables() if t.pieces(0xAC00 + n) is not None or 0xAC00 + n in face.glyphs)
        cov = detect.coverage_svf(face)
        self.assertEqual((cov["all"], cov["ks2350"]), (want_all, want_ks))
        self.assertLess(cov["all"], 11172)
        self.assertLess(cov["ks2350"], 2350)

    def test_quality_skips_a_jmap_miss(self):
        import quality
        e, p = self.detect("--jmap-variant", "sparse3")
        face = jamoset.parse_svfn(head(p))
        got = quality.composed_syllables(face)
        t = detect.usable_jset(face)
        self.assertEqual(set(got), {s for s in range(11172) if t.pieces(0xAC00 + s) is not None})
        self.assertEqual(quality.compare(face, {}), {"all": None, "ks2350": None, "compared": 0})
        miss = next(s for s in range(11172) if s not in got)
        r = quality.compare(face, {miss: 0})
        self.assertEqual(r, {"all": None, "ks2350": None, "compared": 0})
        self.assertIsNone(quality.measure(head(p), None, "", 16))
        hit = next(iter(got))
        g = jamoset.glyph_gint(got[hit], face.cell_w, face.cell_h)
        rep = jamoset.fit_report(head(p), {hit: g, miss: g}, face.cell_w, face.cell_h)     # no TypeError on the miss
        self.assertIsNotNone(rep)
        facts = quality.face_facts(head(p))
        self.assertEqual(facts["jset"]["pieces"], [t.pi, t.pm, t.pf])
        self.assertIsNone(facts["jset"]["sets"])

    def test_list_face_reports_its_mode(self):
        e, p = self.detect("--jmap-variant", "list1")
        self.assertEqual(e["source_kind"], "svf-jamo")
        self.assertEqual(e["svf"]["jset_version"], 3)
        self.assertEqual(e["svf"]["jmap_mode"], "list")
        e, _ = self.detect("--jmap-variant", "sparse3")
        self.assertEqual(e["svf"]["jmap_mode"], "sparse")
        e, _ = self.detect("--jmap-variant", "dense4")
        self.assertEqual(e["svf"]["jmap_mode"], "dense")
        e, _ = self.detect("--jmap-variant", "list2")
        self.assertEqual(e["svf"]["jmap_mode"], "list")

    def test_jmap_mode_comes_from_the_flags_not_the_entry_count(self):
        sparse = jamoset.pack_jmap(jamoset.Jmap(0, 1, 1, 0, {0: (1, 1, 0)}))
        self.assertEqual(detect.jmap_mode(sparse), "sparse")
        full = jamoset.Jmap(0, 1, 1, 0, {s: (1, 1, 0) for s in range(11172)})
        self.assertEqual(detect.jmap_mode(jamoset.pack_jmap(full)), "dense")
        e, _ = self.detect("--jmap-variant", "sparse_full")      # the SPARSE flag with NS = 11,172
        self.assertEqual(e["svf"]["jmap_mode"], "sparse")
        self.assertIsNone(detect.jmap_mode(None))

    def test_list_face_piece_counts_and_coverage(self):
        import quality
        # the pieces use at test_quality_skips_a_jmap_miss, list-mode case: a LIST has pi = pm = pf = 0 (L2)
        for v in ("list1", "list_nofb"):
            with self.subTest(v=v):
                e, p = self.detect("--jmap-variant", v)
                face = detect.read_svf(head(p))
                t = detect.usable_jset(face)
                self.assertTrue(t.list_mode)
                self.assertEqual([t.pi, t.pm, t.pf], [0, 0, 0])
                self.assertGreater(len(t.entries), 0)
                if t.fallback is not None:      # the entries decide: they differ from what the fallback would draw
                    self.assertTrue(all(t.pieces(0xAC00 + s) != jamoset.pieces_of(t.fallback, 0xAC00 + s)
                                        for s in t.entries))
                facts = quality.face_facts(head(p))
                self.assertIsNone(facts["jset"]["pieces"])
                self.assertEqual(facts["jset"]["jmap_mode"], "list")
                got = quality.composed_syllables(face)
                self.assertEqual(set(got), {s for s in range(11172) if t.pieces(0xAC00 + s) is not None})

    def test_unusable_jmap_is_precomposed(self):
        e, _ = self.detect("--jmap-bad", "jmap_missing_piece")
        self.assertEqual(e["source_kind"], "svf-precomposed")
        self.assertIsNone(e["svf"]["jset_version"])


if __name__ == "__main__":
    unittest.main()
