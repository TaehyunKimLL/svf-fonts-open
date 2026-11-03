#!/usr/bin/env python3
"""srcprep.py tests: the reading helpers and the PCF reader, on fixtures built in inputfx.py.

  python3 -m unittest discover -s maker/test -p 'test_srcprep.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gzip
import io
import subprocess
import tempfile
import unittest

import bdfface
import fixtures
import inputfx
import srcprep
from PIL import ImageFont
from fontTools.ttLib import TTFont


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def write(self, name, data):
        p = os.path.join(self.dir, name)
        with open(p, "wb") as fh:
            fh.write(data)
        return p


class SrcprepTest(TmpCase):
    def test_ttc_face_bytes_saves_face_1(self):
        data = inputfx.ttc([inputfx.ttf("One", (50, 0, 950, 800)), inputfx.ttf("Two", (300, 0, 700, 400))])
        face = TTFont(io.BytesIO(srcprep.ttc_face_bytes(data, 1)))
        self.assertEqual(face["name"].getDebugName(1), "Two")
        with self.assertRaises(srcprep.PrepError):
            srcprep.ttc_face_bytes(data, 2)

    def test_variable_info(self):
        info = srcprep.variable_info(TTFont(io.BytesIO(inputfx.variable_ttf())))
        self.assertEqual(info["axes"], [{"tag": "wght", "min": 100, "default": 400, "max": 900}])
        self.assertEqual(info["instances"], [{"name": "Regular", "coords": {"wght": 400}},
                                             {"name": "Bold", "coords": {"wght": 700}}])
        self.assertIsNone(srcprep.variable_info(TTFont(io.BytesIO(inputfx.ttf("S", (0, 0, 9, 9))))))

    def test_embedded_strikes_and_outlines(self):
        self.assertEqual(srcprep.embedded_strikes(TTFont(io.BytesIO(inputfx.eblc_ttf((16, 12, 16))))), [12, 16])
        self.assertEqual(srcprep.embedded_strikes(TTFont(io.BytesIO(inputfx.ttf("S", (0, 0, 9, 9))))), [])
        self.assertFalse(srcprep.has_outlines(TTFont(io.BytesIO(inputfx.bitmap_only_ttf()))))
        self.assertTrue(srcprep.has_outlines(TTFont(io.BytesIO(inputfx.otf("C", (0, 0, 9, 9))))))

    def test_mac_cmap_only(self):
        self.assertTrue(srcprep.mac_cmap_only(TTFont(io.BytesIO(inputfx.mac_cmap_ttf()))))
        self.assertFalse(srcprep.mac_cmap_only(TTFont(io.BytesIO(inputfx.both_cmaps_ttf()))))
        self.assertFalse(srcprep.mac_cmap_only(TTFont(io.BytesIO(inputfx.ttf("S", (0, 0, 9, 9))))))

    def test_mac_resources_names_the_container(self):
        fk = inputfx.fork([(b"sfnt", 128, "Synth", inputfx.mac_cmap_ttf()), (b"NFNT", 200, "", bytes(26))])
        for blob, name in ((fk, "resource fork"), (inputfx.appledouble(fk), "AppleDouble"),
                           (inputfx.macbinary(fk), "MacBinary")):
            container, res = srcprep.mac_resources(blob)
            self.assertEqual((container, [(t, i) for t, i, _, _ in res]), (name, [(b"sfnt", 128), (b"NFNT", 200)]))
        with self.assertRaises(srcprep.PrepError):
            srcprep.mac_resources(fk[:40])

    def test_prepared_bytes_chains_ops(self):
        fk = inputfx.fork([(b"sfnt", 129, "", inputfx.mac_cmap_ttf())])
        out = TTFont(io.BytesIO(srcprep.prepared_bytes(inputfx.appledouble(fk),
                                                        [{"op": "rsrc-sfnt", "id": 129}, {"op": "mac-cmap"}])))
        self.assertEqual(out.getBestCmap()[0xAC00], "ga")
        with self.assertRaises(srcprep.PrepError):
            srcprep.prepared_bytes(b"", [{"op": "instance", "coords": {}}])

    def test_cli_ttc_face(self):
        src = self.write("two.ttc", inputfx.ttc([inputfx.ttf("One", (50, 0, 950, 800)),
                                                 inputfx.ttf("Two", (300, 0, 700, 400))]))
        out = os.path.join(self.dir, "face.ttf")
        tool = os.path.join(MAKER_DIR, "srcprep.py")
        r = subprocess.run([sys.executable, "-P", tool, "ttc-face", src, out, "--index", "1"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(TTFont(out)["name"].getDebugName(1), "Two")
        r = subprocess.run([sys.executable, "-P", tool, "ttc-face", src, out, "--index", "5"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("face", r.stderr)


GLYPHS = [(0x3021, [0x8001 | (y << 3) for y in range(16)], 16),
          (0x3022, [0xFFFF if y == 8 else 0 for y in range(16)], 16)]


class PcfTest(TmpCase):
    def test_properties_and_gzip(self):
        data = inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2)
        for blob in (data, gzip.compress(data)):
            p = srcprep.pcf_properties(blob)
            self.assertEqual((p["CHARSET_REGISTRY"], p["CHARSET_ENCODING"], p["PIXEL_SIZE"]),
                             ("KSC5601.1987", "0", 16))

    def test_pcf_to_bdf_round_trips_through_bdfface(self):
        bdf = srcprep.pcf_to_bdf(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2))
        path = self.write("k.bdf", bdf)
        glyphs = bdfface.read_bdf(path)[1]
        self.assertEqual(sorted(glyphs), [0xAC00, 0xAC01])        # bdfface reads KSC GL codes 0x3021/0x3022 as U+AC00/AC01
        self.assertEqual(glyphs[0xAC01][4][8], 0xFFFF)            # bdfface's row ints, row 8
        self.assertEqual(glyphs[0xAC00][4], GLYPHS[0][1])
        raw = bdfface.read_bdf(path, unicode_enc=True)[1]
        self.assertEqual(sorted(raw), [0x3021, 0x3022])
        self.assertIn(b"FONTBOUNDINGBOX 16 16 0 -2", bdf)

    def test_lsbit_and_lsbyte_tables_read_the_same(self):
        want = srcprep.pcf_to_bdf(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2))
        for fmt in (0x00000010 | 0x1,            # LSByte, LSBit, pad 2, scan unit 2
                    0x00000004 | 0x10 | 0x1,     # MSByte, LSBit, pad 2, scan unit 2: the bytes swap inside a unit
                    0x00000008 | 0x2 | 0x20):    # LSByte, MSBit, pad 4, scan unit 4
            with self.subTest(fmt=fmt):
                got = srcprep.pcf_to_bdf(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2, fmt=fmt))
                self.assertEqual(got, want)

    def test_pillow_opens_the_fixture_pcf(self):
        data = inputfx.pcf([(0x41, [0x8001] * 16, 16)], "ISO10646", "1", 16, 14, 2)
        font = ImageFont.truetype(self.write("a.pcf", data), 16)
        self.assertIsNotNone(font.getmask("A").getbbox())

    def test_truncated_pcf_is_a_prep_error(self):
        with self.assertRaises(srcprep.PrepError):
            srcprep.pcf_to_bdf(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2)[:200])
        with self.assertRaises(srcprep.PrepError):
            srcprep.pcf_to_bdf(b"not a pcf at all")

    def test_the_pcf_bdf_op_and_cli(self):
        data = inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2)
        self.assertEqual(srcprep.prepared_bytes(data, [{"op": "pcf-bdf"}]), srcprep.pcf_to_bdf(data))
        out = os.path.join(self.dir, "o.bdf")
        r = subprocess.run([sys.executable, "-P", os.path.join(MAKER_DIR, "srcprep.py"), "pcf-bdf",
                            self.write("k.pcf.gz", gzip.compress(data)), out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, "rb") as fh:
            self.assertEqual(fh.read(), srcprep.pcf_to_bdf(data))

    @unittest.skipUnless(os.path.isfile(fixtures.PCF_SRC), "no 18x18ko.pcf.gz on this host")
    def test_the_host_pcf_converts(self):
        with open(fixtures.PCF_SRC, "rb") as fh:
            raw = fh.read()
        glyphs = bdfface.read_bdf(self.write("h.bdf", srcprep.pcf_to_bdf(raw)), unicode_enc=True)[1]
        self.assertGreater(len([cp for cp in glyphs if 0xAC00 <= cp <= 0xD7A3]), 2000)


if __name__ == "__main__":
    unittest.main()
