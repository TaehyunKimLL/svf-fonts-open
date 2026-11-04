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
    def test_gsub_jamo_fact(self):
        e = detect.detect_file(self.put("G.ttf", inputfx.gsub_jamo_ttf()), "G.ttf")[0]
        self.assertTrue(e["gsub_jamo"])
        self.assertTrue(e["label"].endswith("; conjoining jamo (GSUB)"), e["label"])
        e = detect.detect_file(self.put("L.ttf", inputfx.gsub_jamo_ttf(("ljmo",))), "L.ttf")[0]
        self.assertNotIn("gsub_jamo", e)
        e = detect.detect_file(self.put("P.ttf", inputfx.ttf("Plain", BOX1)), "P.ttf")[0]
        self.assertNotIn("gsub_jamo", e)

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

    def test_ttc_face_0_with_a_mac_cmap_gets_a_ttc_face_op(self):
        self.put("t/m.ttc", inputfx.ttc([inputfx.mac_cmap_ttf(), inputfx.mac_cmap_ttf()]))
        out = detect.scan(self.dir("t"))
        self.assertEqual([e["prep"] for e in out],
                         [[{"op": "ttc-face", "index": 0}, {"op": "mac-cmap"}],
                          [{"op": "ttc-face", "index": 1}, {"op": "mac-cmap"}]])
        self.assertEqual([e["coverage"]["all"] for e in out], [1, 1])

    def test_a_damaged_mac_cmap_font_does_not_take_the_scan_down(self):
        bad = inputfx.damaged_mac_cmap_ttf()
        self.put("u/Good.ttf", inputfx.ttf("Good", BOX1))
        self.put("u/Bad.ttf", bad)
        out = detect.scan(self.dir("u"))
        self.assertEqual(len(out), 2)
        bad_e = [e for e in out if e["path"] == "Bad.ttf"][0]
        self.assertIn("cannot prepare", bad_e["label"])
        self.assertIsNone(bad_e["coverage"])

    def test_a_prepped_font_offers_the_routes_of_its_kind(self):
        e = detect.detect_file(self.put("Mac.ttf", inputfx.mac_cmap_ttf()), "Mac.ttf")[0]
        self.assertEqual([r.label for r in routes.routes(e)], ["mkfont", "experimental fit", "vector fit"])
        two = detect.detect_file(self.put("t.ttc", inputfx.ttc([inputfx.ttf("One", BOX1), inputfx.ttf("Two", BOX2)])),
                                 "t.ttc")
        self.assertEqual([len(routes.routes(e)) for e in two], [3, 3])       # face 1 has prep: a source like face 0


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

    def test_more_sfnts_than_the_cap_say_so(self):
        small = inputfx.ttf("P", BOX1)
        fk = inputfx.fork([(b"sfnt", 100 + i, "", small) for i in range(detect._FACE_CAP + 2)])
        out = detect.detect_file(self.put("M.dfont", fk), "M.dfont")
        self.assertEqual(len(out), detect._FACE_CAP)
        self.assertTrue(out[-1]["label"].endswith("; more faces not listed"))
        self.assertNotIn("more faces", out[-2]["label"])

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


PCF_KSC_GLYPHS = [(0x3021, [0x8001 | (y << 3) for y in range(16)], 16),
                  (0x3022, [0xFFFF if y == 8 else 0 for y in range(16)], 16)]
JOHAB_529 = [(code, rows, 16) for code, _w, _h, _x, _y, rows in fixtures._johab_glyphs()]


class EngTest(DirCase):
    def test_pft_is_a_12x24_eng(self):
        e = detect.detect_file(self.put("ASCII.PFT", inputfx.pft_eng()), "ASCII.PFT")[0]
        self.assertEqual((e["format"], e["label"], e["eng"]), ("eng", "Latin companion (--eng, 12x24)",
                                                               {"bytes": 12288, "cell": "12x24"}))

    def test_the_8x16_eng_label_is_unchanged_and_carries_its_size(self):
        e = detect.detect_file(self.put("ENG.FNT", bytes(2048)), "ENG.FNT")[0]
        self.assertEqual((e["label"], e["eng"]), ("Latin companion (--eng)", {"bytes": 2048, "cell": "8x16"}))

    def test_hbios_english_is_an_eng_not_a_dokkaebi_face(self):
        e, = detect.detect_file(self.put("ROMAN24.FNT", inputfx.hbios_eng()), "ROMAN24.FNT")
        self.assertEqual((e["format"], e["source_kind"], e["label"]), ("eng", "other", "HBIOS 12x24 English (--eng)"))
        self.assertEqual(e["eng"], {"bytes": 15360, "cell": "12x24"})

    def test_a_dokkaebi_face_with_margin_ink_stays_dos_raw(self):
        out = detect.detect_file(self.put("HANGUL16.FNT", inputfx.dkb_like()), "HANGUL16.FNT")
        self.assertEqual([e["source_kind"] for e in out], ["dos-raw", "dos-raw"])
        self.assertTrue(all(e["dos_bytes"] == 15360 for e in out))

    def test_a_dokkaebi_face_with_ink_in_a_right_hand_nibble_stays_dos_raw(self):
        data = bytearray(inputfx.hbios_eng())
        for g in range(256):
            data[g * 60 + 14 * 2 + 1] |= 0x01            # column 15 of the row: outside a 12 px cell
        self.assertFalse(detect.hbios_eng_like(bytes(data)))
        out = detect.detect_file(self.put("HANGUL16.FNT", bytes(data)), "HANGUL16.FNT")
        self.assertEqual([e["source_kind"] for e in out], ["dos-raw", "dos-raw"])

    def test_a_12x24_eng_is_a_companion_of_a_dos_font_beside_it(self):
        fixtures._dos_raw(self.path("d/HAN.FNT"))                 # 11,520 bytes, 8x4x4
        self.put("d/ASCII.PFT", inputfx.pft_eng())
        fonts = detect.scan(self.dir("d"))
        dos = [e for e in fonts if e["source_kind"] == "dos-raw"][0]
        self.assertEqual((dos["dos_bytes"], len(dos["companions"])), (11520, 1))

    def test_a_12x24_eng_alone_is_unknown(self):
        self.put("e/ASCII.PFT", inputfx.pft_eng())
        e, = detect.scan(self.dir("e"))
        self.assertEqual(e["format"], "unknown")

    def test_an_all_zero_15360_file_is_not_hbios_eng(self):
        self.assertFalse(detect.hbios_eng_like(bytes(15360)))
        self.assertFalse(detect.hbios_eng_like(bytes(15359)))
        self.assertTrue(detect.hbios_eng_like(inputfx.hbios_eng()))


class PcfDetectTest(DirCase):
    def test_ksc_pcf_is_a_ksc_bdf_source(self):
        self.put("p/k.pcf", inputfx.pcf(PCF_KSC_GLYPHS, "KSC5601.1987", "0", 16, 14, 2))
        e = detect.scan(self.dir("p"))[0]
        self.assertEqual((e["format"], e["source_kind"], e["bdf"], e["sizes"], e["prep"]),
                         ("pcf", "bdf-ksc5601", {"registry": "ksc5601.1987-0", "box": [16, 16]}, [16],
                          [{"op": "pcf-bdf"}]))
        self.assertEqual(e["label"], "PCF (ksc5601.1987)")
        self.assertEqual(e["coverage"]["ks2350"], 2)

    def test_a_gz_ksc_pcf_is_read_through_its_decompressed_bytes(self):
        import gzip
        self.put("g/k.pcf.gz", gzip.compress(inputfx.pcf(PCF_KSC_GLYPHS, "KSC5601.1987", "0", 16, 14, 2)))
        e, = detect.scan(self.dir("g"))
        self.assertEqual((e["source_kind"], e["prep"], e["coverage"]["ks2350"]), ("bdf-ksc5601", [{"op": "pcf-bdf"}], 2))
        self.assertNotIn("gzip", e)

    def test_johab_pcf_is_a_hanterm_source(self):
        e = detect.detect_file(self.put("j.pcf", inputfx.pcf(JOHAB_529, "johab", "1", 16, 13, 3)), "j.pcf")[0]
        self.assertEqual((e["source_kind"], e["prep"]), ("bdf-johab", [{"op": "pcf-bdf"}]))

    def test_an_iso10646_pcf_stays_bitmap(self):
        e = detect.detect_file(self.put("u.pcf", inputfx.pcf([(0x41, [0x8001] * 16, 16)], "ISO10646", "1", 16, 14, 2)),
                               "u.pcf")[0]
        self.assertEqual((e["source_kind"], e.get("prep")), ("bitmap", None))

    def test_a_damaged_gz_pcf_falls_back_to_the_bitmap_path(self):
        import gzip
        blob = gzip.compress(inputfx.pcf(PCF_KSC_GLYPHS, "KSC5601.1987", "0", 16, 14, 2)[:200])
        e, = detect.detect_file(self.put("c.pcf.gz", blob), "c.pcf.gz")
        self.assertEqual((e["format"], e["label"]), ("pcf", "PCF; no openable size"))
        self.assertNotIn("prep", e)

    def test_a_truncated_pcf_still_gets_one_entry(self):
        data = inputfx.pcf(PCF_KSC_GLYPHS, "KSC5601.1987", "0", 16, 14, 2)[:200]
        out = detect.detect_file(self.put("t.pcf", data), "t.pcf")
        self.assertEqual(len(out), 1)
        self.assertNotIn("prep", out[0])


if __name__ == "__main__":
    unittest.main()
