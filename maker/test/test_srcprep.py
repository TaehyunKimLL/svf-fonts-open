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


if __name__ == "__main__":
    unittest.main()
