#!/usr/bin/env python3
"""Detection of the maker's new input kinds (t_f3ef3189): TTC faces, variable fonts, Mac cmaps, strikes, Mac
containers, KSC/johab PCF, 12x24 English companions. Every file is built inside the test (inputfx.py).

  python3 -m unittest discover -s maker/test -p 'test_detect_inputs.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import struct
import tempfile
import unittest

import detect
import fixtures
import inputfx
import routes

BOX1 = (50, 0, 950, 800)
BOX2 = (300, 0, 700, 400)


class DirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name

    def path(self, rel):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def put(self, rel, data):
        p = self.path(rel)
        with open(p, "wb") as fh:
            fh.write(data)
        return p

    def dir(self, rel):
        return os.path.join(self.root, rel)


class SfntDetectTest(DirCase):
    def test_ttc_face_1_is_an_outline_with_a_ttc_face_op(self):
        out = detect.detect_file(self.put("two.ttc", inputfx.ttc([inputfx.ttf("One", BOX1),
                                                                    inputfx.ttf("Two", BOX2)])), "two.ttc")
        self.assertEqual([(e["face_index"], e["label"], e["source_kind"], e["family"], e.get("prep")) for e in out],
                         [(0, "TTC face 0", "outline", "One", None),
                          (1, "TTC face 1", "outline", "Two", [{"op": "ttc-face", "index": 1}])])

    def test_variable_font_carries_axes_and_instances(self):
        e = detect.detect_file(self.put("Vary.ttf", inputfx.variable_ttf()), "Vary.ttf")[0]
        self.assertEqual(e["label"], "TTF; variable (wght 100..900)")
        self.assertEqual([i["name"] for i in e["variable"]["instances"]], ["Regular", "Bold"])
        self.assertNotIn("prep", e)

    def test_mac_cmap_font_gets_the_op_and_composed_coverage(self):
        self.put("mac/Mac.ttf", inputfx.mac_cmap_ttf())
        e = detect.scan(self.dir("mac"))[0]
        self.assertEqual((e["label"], e["prep"]), ("TTF; Mac Korean cmap", [{"op": "mac-cmap"}]))
        self.assertEqual((e["coverage"]["ascii"], e["coverage"]["all"]), (1, 1))

    def test_a_font_with_both_cmaps_gets_no_mac_cmap_op(self):
        e = detect.detect_file(self.put("Both.ttf", inputfx.both_cmaps_ttf()), "Both.ttf")[0]
        self.assertNotIn("prep", e)

    def test_strikes_are_listed(self):
        e = detect.detect_file(self.put("S.ttf", inputfx.eblc_ttf((12, 16))), "S.ttf")[0]
        self.assertEqual((e["source_kind"], e["strikes"], e["sizes_fixed"]), ("outline", [12, 16], False))
        self.assertTrue(e["label"].endswith("; bitmap strikes 12, 16"))

    def test_bitmap_only_sfnt_is_a_bitmap_at_its_strikes(self):
        self.put("b/B.ttf", inputfx.bitmap_only_ttf((12, 16)))
        e = detect.scan(self.dir("b"))[0]
        self.assertEqual((e["source_kind"], e["sizes"], e["sizes_fixed"]), ("bitmap", [12, 16], True))
        self.assertEqual(e["coverage"]["ascii"], 1)                # coverage_cmap, not the picture test
        self.assertTrue(e["label"].startswith("TTF bitmap-only"))

    def test_an_sfnt_with_neither_outlines_nor_strikes_is_other(self):
        from fontTools.ttLib import TTFont
        import io
        font = TTFont(io.BytesIO(inputfx.bitmap_only_ttf((12,))), recalcBBoxes=False)
        del font["EBLC"], font["EBDT"]
        buf = io.BytesIO()
        font.save(buf)
        e = detect.detect_file(self.put("N.ttf", buf.getvalue()), "N.ttf")[0]
        self.assertEqual(e["source_kind"], "other")
        self.assertIn("no outlines, no bitmap strikes", e["label"])

    def test_ttc_face_1_coverage_and_composite_use_the_face(self):
        comp = fixtures._composite_ttf(self.path("c/Composite.ttf"))
        with open(comp, "rb") as fh:
            comp_bytes = fh.read()
        os.remove(comp)
        self.put("t/two.ttc", inputfx.ttc([inputfx.ttf("One", BOX1), comp_bytes]))
        out = detect.scan(self.dir("t"))
        self.assertEqual([(e["face_index"], e["source_kind"]) for e in out],
                         [(0, "outline"), (1, "outline-composite")])
        self.assertEqual(out[0]["coverage"]["all"], 1)
        self.assertEqual(out[1]["coverage"]["all"], 66)

    def test_an_otc_cff_face_1_is_an_outline_with_a_ttc_face_op(self):
        out = detect.detect_file(self.put("o.otc", inputfx.ttc([inputfx.otf("One", BOX1), inputfx.otf("Two", BOX2)])),
                                 "o.otc")
        self.assertEqual([(e["source_kind"], e.get("prep")) for e in out],
                         [("outline", None), ("outline", [{"op": "ttc-face", "index": 1}])])

    def test_a_prepped_font_offers_no_route_yet(self):
        e = detect.detect_file(self.put("Mac.ttf", inputfx.mac_cmap_ttf()), "Mac.ttf")[0]
        self.assertEqual(routes.routes(e), [])


class MacContainerTest(DirCase):
    def test_each_wrapper_lists_its_sfnts(self):
        fk = inputfx.fork([(b"FOND", 128, "Synth", bytes(52)), (b"sfnt", 128, "Synth", inputfx.mac_cmap_ttf()),
                           (b"sfnt", 129, "", inputfx.ttf("Plain", BOX1))])
        for name, blob, container in (("F.dfont", fk, "resource fork"), ("._F", inputfx.appledouble(fk), "AppleDouble"),
                                      ("F.bin", inputfx.macbinary(fk), "MacBinary")):
            out = detect.detect_file(self.put(name, blob), name)
            self.assertEqual([(e["format"], e["face_index"], e["label"], e["source_kind"], e["prep"]) for e in out],
                             [("mac-rsrc", 0, container + ": sfnt 128; Mac Korean cmap", "outline",
                               [{"op": "rsrc-sfnt", "id": 128}, {"op": "mac-cmap"}]),
                              ("mac-rsrc", 1, container + ": sfnt 129", "outline", [{"op": "rsrc-sfnt", "id": 129}])])

    def test_sniff_tags(self):
        fk = inputfx.fork([(b"sfnt", 128, "", inputfx.ttf("P", BOX1))])
        self.assertEqual(detect.sniff(fk[:512], len(fk)), "mac-rsrc")
        self.assertEqual(detect.sniff(bytes(512), 11520), "dos-raw")     # a blank-led DOS raw font is not a fork

    def test_a_fork_with_only_bitmap_fonts_is_other(self):
        e, = detect.detect_file(self.put("B.dfont", inputfx.fork([(b"NFNT", 200, "", bytes(26))])), "B.dfont")
        self.assertEqual((e["source_kind"], e["label"]),
                         ("other", "Mac bitmap font (NFNT/fbit): not converted here (local-only mode)"))

    def test_a_corrupt_fork_is_one_unknown_entry(self):
        fk = bytearray(inputfx.fork([(b"sfnt", 128, "", inputfx.ttf("P", BOX1))]))
        struct.pack_into(">H", fk, struct.unpack_from(">I", fk, 4)[0] + 24, 0xFFF0)   # type list offset past the map
        e, = detect.detect_file(self.put("C.dfont", bytes(fk)), "C.dfont")
        self.assertEqual(e["format"], "unknown")
        self.assertTrue(e["label"].startswith("unknown (Mac resource fork: "))

    def test_a_mac_sfnt_coverage_is_read_through_the_ops(self):
        self.put("m/F.dfont", inputfx.fork([(b"sfnt", 128, "Synth", inputfx.mac_cmap_ttf())]))
        e, = detect.scan(self.dir("m"))
        self.assertEqual(e["coverage"]["all"], 1)

    def test_a_gz_dfont_is_read_through_its_decompressed_bytes(self):
        import gzip
        fk = inputfx.fork([(b"sfnt", 128, "Synth", inputfx.mac_cmap_ttf())])
        self.put("g/F.dfont.gz", gzip.compress(fk))
        e, = detect.scan(self.dir("g"))
        self.assertEqual((e["format"], e["gzip"], e["coverage"]["all"]), ("mac-rsrc", True, 1))


if __name__ == "__main__":
    unittest.main()
