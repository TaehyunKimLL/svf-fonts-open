#!/usr/bin/env python3
"""bdfface.py tests: a tiny KS X 1001 BDF and an HBF made on the spot, the written SVF read back.

  python3 tools/test_bdfface.py
"""

import gzip
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bdfface  # noqa: E402
import jamoset  # noqa: E402

KS_GA = 0x3021	# 가 (U+AC00): KS X 1001 row 0x30, cell 0x21
KS_GAK = 0x3022	# 각 (U+AC01)


def bdf(path, glyphs, ascent=19, descent=5, registry="KSX1001.1998"):
    """glyphs: [(ENCODING, bw, bh, bx, by, [row ints])] with rows as ints (MSB left)."""
    out = ["STARTFONT 2.1", "FONT -test-x", "SIZE 24 75 75", "FONTBOUNDINGBOX 24 24 0 -5", "STARTPROPERTIES 3",
           f"FONT_ASCENT {ascent}", f"FONT_DESCENT {descent}", f'CHARSET_REGISTRY "{registry}"', "ENDPROPERTIES",
           f"CHARS {len(glyphs)}"]
    for enc, bw, bh, bx, by, rows in glyphs:
        nb = (bw + 7) // 8
        out += ["STARTCHAR g", f"ENCODING {enc}", "SWIDTH 960 0", "DWIDTH 24 0", f"BBX {bw} {bh} {bx} {by}", "BITMAP"]
        out += [format(r << (nb * 8 - bw), "0%dX" % (nb * 2)) for r in rows]
        out += ["ENDCHAR"]
    out += ["ENDFONT", ""]
    with open(path, "w") as f:
        f.write("\n".join(out))


def hbf(path, binname, glyphs, w=12, h=24, ascent=22, descent=2, gz=False):
    """glyphs: {code: rows}; the bitmap file holds codes 1..max in order."""
    top = max(glyphs)
    nb = (w + 7) // 8
    data = bytearray()
    for code in range(1, top + 1):
        rows = glyphs.get(code, [0] * h)
        for r in rows:
            data += (r << (nb * 8 - w)).to_bytes(nb, "big")
    text = ["HBF_START_FONT 1.0", f"HBF_BITMAP_BOUNDING_BOX {w} {h} 0 -{descent}",
            f"FONTBOUNDINGBOX {w} {h} 0 -{descent}", f"FONT_ASCENT {ascent}", f"FONT_DESCENT {descent}",
            f"HBF_CODE_RANGE 0x0001-0x{top:04X} {binname} 0", "HBF_END_FONT", ""]
    with open(path, "w") as f:
        f.write("\n".join(text))
    p = os.path.join(os.path.dirname(path), binname)
    if gz:
        with gzip.open(p + ".gz", "wb") as f:
            f.write(bytes(data))
    else:
        with open(p, "wb") as f:
            f.write(bytes(data))


class BdfFaceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.dir, name)

    def make(self, gz=False):
        # 가: a 3 row x 4 col block drawn from y offset -5 up (bottom row on the descent), 각 a single pixel
        bdf(self.path("h.bdf"), [(KS_GA, 4, 3, 2, -5, [0b1111, 0b1001, 0b1111]), (KS_GAK, 1, 1, 0, 0, [1])])
        hbf(self.path("a.hbf"), "a.bin", {0x41: [0xFFF] * 24, 0x20: [0] * 24}, gz=gz)

    def build(self, chars, **kw):
        hangul = bdfface.read_face(self.path("h.bdf"))
        ascii_face = bdfface.read_face(self.path("a.hbf"), unicode_enc=True)
        return bdfface.build(hangul, ascii_face, 24, 24, ascii_face[0].ascent, chars, **kw)

    def rows(self, f, cp):
        g = f.glyphs[cp]
        nb = (f.cell_w + 7) // 8
        return [int.from_bytes(g[y * nb:(y + 1) * nb], "big") >> (nb * 8 - f.cell_w) for y in range(f.cell_h)]

    def test_hangul_placed_by_its_bbx(self):
        self.make()
        data, info = self.build({0xAC00, 0xAC01})
        f = jamoset.parse_svfn(data)
        # baseline row 19: top = 19 - (by + bh) = 19 - (-5 + 3) = 21, x from bx = 2
        rows = self.rows(f, 0xAC00)
        self.assertEqual(rows[21:24], [0b1111 << 18, 0b1001 << 18, 0b1111 << 18])
        self.assertEqual(sum(1 for r in rows if r), 3)
        self.assertEqual(f.metrics[0xAC00], (24, 2, 4))
        self.assertEqual(info["syllables"], 2)
        # 각: one pixel on the baseline row, origin column 0
        self.assertEqual(self.rows(f, 0xAC01)[18], 1 << 23)

    def test_header_matches_the_other_l_faces(self):
        self.make()
        data, _ = self.build({0xAC00})
        f = jamoset.parse_svfn(data)
        self.assertEqual((f.flags, f.bpp, f.version), (5, 1, 3))
        self.assertEqual((f.cell_w, f.cell_h, f.ascent), (24, 24, 22))
        self.assertIsNone(f.jset)

    def test_writes_v3_default(self):
        self.make()
        data, _ = self.build({0xAC00})
        self.assertEqual(data[4:6], b"\x03\x00")
        f = jamoset.parse_svfn(data)
        self.assertEqual(f.layout, (2, 0, 2, True))

    def test_profile_dos(self):
        self.make()
        a, _ = self.build({0xAC00})
        b, _ = self.build({0xAC00}, profile="dos")
        self.assertEqual(b[9], 0)
        fa, fb = jamoset.parse_svfn(a), jamoset.parse_svfn(b)
        self.assertEqual(fb.glyphs, fa.glyphs)
        self.assertEqual(fb.metrics, fa.metrics)

    def test_box_full(self):
        self.make()
        a, _ = self.build({0xAC00})
        b, _ = self.build({0xAC00}, profile=jamoset.profile_of("default", "full"))
        fa, fb = jamoset.parse_svfn(a), jamoset.parse_svfn(b)
        self.assertEqual(fb.glyphs, fa.glyphs)
        inked = [x for x in jamoset.record_boxes(b) if x[2]]
        self.assertTrue(inked and all(x[2] == 3 and x[3] == 24 for x in inked))
        self.assertTrue(any(x[3] < 24 for x in jamoset.record_boxes(a) if x[2]))
        self.assertGreater(len(b), len(a))

    def test_the_command_takes_profile(self):
        import subprocess
        self.make()
        chars = self.path("chars.txt")
        with open(chars, "w", encoding="utf-8") as fh:
            fh.write("\uac00")
        out = self.path("o.svf")
        r = subprocess.run([sys.executable, bdfface.__file__, "--hangul", self.path("h.bdf"), "--ascii", self.path("a.hbf"),
                            "--chars-from", chars, "--profile", "dos", "--box", "full", "-o", out],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, "rb") as fh:
            data = fh.read()
        self.assertEqual(data[9], 0)
        self.assertEqual(jamoset.parse_svfn(data).glyphs[0xAC00],
                         jamoset.parse_svfn(self.build({0xAC00})[0]).glyphs[0xAC00])

    def test_ascii_from_a_gzipped_hbf_on_the_ascii_baseline(self):
        self.make(gz=True)
        data, _ = self.build({0xAC00})
        f = jamoset.parse_svfn(data)
        # 'A' fills 24 rows from HBF y offset -2 with baseline 22: top = 22 - (-2 + 24) = 0
        self.assertEqual(self.rows(f, 0x41), [0xFFF << 12] * 24)
        self.assertEqual(f.metrics[0x41][0], 12)
        self.assertEqual(f.metrics[0x20][0], 12)
        self.assertNotIn(0x42, f.glyphs)

    def test_ellipsis_and_box_are_drawn_on_the_baseline(self):
        self.make()
        data, _ = self.build({0xAC00})
        f = jamoset.parse_svfn(data)
        dots = self.rows(f, 0x2026)
        self.assertEqual([y for y, r in enumerate(dots) if r], [19, 20, 21])
        self.assertEqual(f.metrics[0x2026][2], 11)
        box = self.rows(f, 0x25A1)
        self.assertEqual([y for y, r in enumerate(box) if r], list(range(6, 22)))
        self.assertTrue(box[6] and box[21])

    def test_an_unencoded_glyph_is_skipped(self):
        # ENCODING -1 (an unencoded glyph, as kaist-newmj18.bdf has) and a code past two bytes are not KS X 1001 codes
        bdf(self.path("h.bdf"), [(-1, 1, 1, 0, 0, [1]), (0x12345, 1, 1, 0, 0, [1]),
                                 (KS_GA, 4, 3, 2, -5, [0b1111, 0b1001, 0b1111])])
        _, glyphs = bdfface.read_bdf(self.path("h.bdf"))
        self.assertEqual(sorted(glyphs), [0xAC00])

    def test_symbols_come_from_the_hangul_face_only_when_asked(self):
        # KS X 1001 0x2158 is U+203B (reference mark), 0x2160 U+25A1 (white square), 0x2421 U+3131 (compatibility g)
        bdf(self.path("h.bdf"), [(KS_GA, 4, 3, 2, -5, [0b1111, 0b1001, 0b1111]), (0x2158, 2, 2, 1, 0, [0b11, 0b01]),
                                 (0x2160, 3, 1, 0, 1, [0b101]), (0x2421, 1, 1, 0, 0, [1])])
        hbf(self.path("a.hbf"), "a.bin", {0x41: [0xFFF] * 24, 0x20: [0] * 24})
        chars = {0xAC00, 0x203B, 0x25A1, 0x3131}
        data, info = self.build(chars)
        f = jamoset.parse_svfn(data)
        self.assertNotIn(0x203B, f.glyphs)
        self.assertNotIn(0x3131, f.glyphs)
        self.assertEqual(len([r for r in self.rows(f, 0x25A1) if r]), 16)	# the drawn box
        data, info = self.build(chars, symbols=True)
        f = jamoset.parse_svfn(data)
        self.assertEqual(info["symbols"], 3)
        # on the Hangul baseline (row 19), 2 rows tall from y offset 0: rows 17-18, x from bx = 1
        self.assertEqual(self.rows(f, 0x203B)[17:19], [0b11 << 21, 0b01 << 21])
        self.assertEqual(f.metrics[0x203B][0], 24)	# the glyph's own DWIDTH
        self.assertEqual([r for r in self.rows(f, 0x25A1) if r], [0b101 << 21])	# the face's square, not the box
        self.assertIn(0x3131, f.glyphs)

    def test_requested_syllable_the_face_lacks_is_reported(self):
        self.make()
        data, info = self.build({0xAC00, 0xB098})
        f = jamoset.parse_svfn(data)
        self.assertNotIn(0xB098, f.glyphs)
        self.assertEqual((info["missing_syllables"], info["filled"]), (1, 0))

    def test_fill_composes_the_absent_syllable_from_fitted_pieces(self):
        # a handful of syllables with real strokes so the fit has pieces to take
        glyphs = []
        # the BDF is Unicode-encoded here; KS X 1001 codes of these syllables are not consecutive
        syl = (0xAC00, 0xAC01, 0xB098, 0xB099, 0xB2E4, 0xB2E5)
        for k, cp in enumerate(syl):
            glyphs.append((cp, 24, 24, 0, -5, [((1 << 24) - 1) if y % (k + 2) == 0 else (1 << (k + 3)) for y in range(24)]))
        bdf(self.path("h.bdf"), glyphs, registry="ISO10646-1")
        hbf(self.path("a.hbf"), "a.bin", {0x41: [0xFFF] * 24})
        hangul = bdfface.read_face(self.path("h.bdf"))
        ascii_face = bdfface.read_face(self.path("a.hbf"), unicode_enc=True)
        absent = 0xB098 + 28 * 3		# 낡-ish: any syllable the BDF lacks
        data, info = bdfface.build(hangul, ascii_face, 24, 24, 22, {0xAC00, absent}, fill=True)
        f = jamoset.parse_svfn(data)
        self.assertEqual((info["missing_syllables"], info["filled"]), (0, 1))
        self.assertTrue(any(self.rows(f, absent)))
        # the syllables the face has are the face's own bits
        self.assertEqual(self.rows(f, 0xAC00)[0], (1 << 24) - 1)

    def test_not_a_bdf_is_an_error(self):
        with open(self.path("x.bdf"), "w") as f:
            f.write("nope")
        with self.assertRaises(bdfface.FaceError):
            bdfface.read_face(self.path("x.bdf"))


class SmallCellSymbols(unittest.TestCase):
    def test_dots_and_box_in_narrow_and_short_cells(self):
        for cell_w, cell_h, ascent, adv in ((8, 8, 6, 8), (8, 16, 13, 4), (6, 8, 2, 6), (4, 4, 3, 4), (24, 24, 21, 12)):
            for rows in (bdfface.dots(cell_w, cell_h, ascent, adv), bdfface.box(cell_w, cell_h, ascent)):
                self.assertEqual(len(rows), cell_h)
                self.assertTrue(all(0 <= r < 1 << cell_w for r in rows), (cell_w, cell_h, ascent))

    def test_dots_clip_at_the_cell_and_do_not_wrap_to_the_bottom(self):
        rows = bdfface.dots(8, 8, 6, 8)
        self.assertEqual([y for y, r in enumerate(rows) if r], [3, 4, 5])
        self.assertEqual(rows[5], 0b10111011)		# the 11 px run overhangs 2 px each side: columns 0, 2-4, 6-7
        rows = bdfface.dots(8, 8, 2, 8)		# ascent 2: only rows 0-1 exist above the baseline
        self.assertEqual([y for y, r in enumerate(rows) if r], [0, 1])


if __name__ == "__main__":
    unittest.main()
