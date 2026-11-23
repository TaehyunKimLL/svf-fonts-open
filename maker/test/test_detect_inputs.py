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

import shutil
import struct
import tempfile
import unittest
from unittest import mock

import detect
import fixtures
import inputfx
import routes
from sources import Sources

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

    def test_taebaek_40_and_48_px_english_are_eng_companions(self):
        for size, cell in ((30720, "20x40"), (49152, "24x48")):
            e = detect.detect_file(self.put("GASCII.PFT", bytes(size)), "GASCII.PFT")[0]
            self.assertEqual((e["format"], e["label"], e["eng"]),
                             ("eng", "Latin companion (--eng, %s)" % cell, {"bytes": size, "cell": cell}))

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


class LocalKindsTest(DirCase):
    """The Mac rows of the spec's 9.2 table in a local scan (and the one `other` row of an upload scan)."""

    def setUp(self):
        super().setUp()
        import localfx
        self.mac = localfx.mac_tree(os.path.join(self.root, "mac"))

    def test_mac71_entries(self):
        fonts = detect.scan(Sources("local", [self.mac]), local=True)
        by = {f["path"]: f for f in fonts}
        self.assertEqual((by["Seoul12.rsrc"]["source_kind"], by["Seoul12.rsrc"]["prep"], by["Seoul12.rsrc"]["sizes"]),
                         ("mac-fbit3", [{"op": "mac-fbit3"}], [12]))
        self.assertEqual(by["ad/._Seoul12"]["prep"], [{"op": "mac-fork"}, {"op": "mac-fbit3"}])
        self.assertEqual(by["mb/Seoul12.bin"]["prep"], [{"op": "mac-fork"}, {"op": "mac-fbit3"}])
        self.assertEqual(by["jm/Seoul12"]["prep"], [{"op": "mac-fbit3"}])
        self.assertEqual(by["raw/Seoul12.fbit"]["prep"], [{"op": "mac-fbit3"}])
        self.assertEqual(by["raw/Seoul12.htbl1"]["source_kind"], "mac-htbl")
        self.assertNotIn("prep", by["raw/Seoul12.htbl1"])
        self.assertEqual(by["ad/._InputBackSupport"]["prep"], [{"op": "mac-fork"}, {"op": "mac-htbl"}])
        self.assertEqual(by["InputBackSupport.rsrc"]["prep"], [{"op": "mac-htbl"}])
        self.assertEqual((by["Suitcase.rsrc"]["source_kind"], by["Suitcase.rsrc"]["mac"]["strikes"]),
                         ("mac-suitcase", [12]))
        self.assertEqual(by["nfnt/Only.rsrc"]["source_kind"], "other")
        self.assertEqual(by["Seoul12.rsrc"]["coverage"], {"ascii": 0, "ks2350": 2350, "all": 2350, "compat": 51})
        self.assertEqual(sorted(by["Seoul12.rsrc"]["companions"]),
                         sorted(f["id"] for f in fonts if f["source_kind"] == "mac-htbl"))
        self.assertEqual(by["Seoul12.rsrc"]["latin_candidates"], [by["Suitcase.rsrc"]["id"]])
        self.assertTrue(by["gz/Seoul12.rsrc.gz"].get("gzip"))
        self.assertEqual(by["ad/._Seoul12"]["family"], "Seoul12")                 # no `._` in the family
        self.assertEqual(by["mb/Seoul12.bin"]["family"], "Seoul12")

    def test_mac10_entry(self):
        by = {f["path"]: f for f in detect.scan(Sources("local", [self.mac]), local=True)}
        raw = by["v1/Munjo16.rsrc"]
        self.assertEqual((raw["source_kind"], raw["label"], raw["sizes"], raw.get("mac")),
                         ("mac-fbit1", "HangulTalk 1.0 fbit (45 sets), 16 x 16", [16], {"generation": 1, "id": 1}))
        self.assertNotIn("prep", raw)
        self.assertEqual(raw["coverage"], {"ascii": 0, "ks2350": 2350, "all": 11172, "compat": 51})
        self.assertEqual(by["v1/ad/._Munjo16"]["prep"], [{"op": "mac-fork"}])
        self.assertEqual(by["v1/mb/Munjo16.bin"]["prep"], [{"op": "mac-fork"}])
        self.assertEqual(by["v1/ad/._Munjo16"]["family"], "Munjo16")

    def test_mac10_is_decided_by_its_45_sets_not_by_the_generation_word(self):
        """Real HangulTalk 1.0 fonts carry generation 3 at 0x0c (like the 7.1 fonts); the fixture carries both."""
        import macfx, struct
        self.assertEqual(struct.unpack(">H", macfx.fbit1_raw()[0x0c:0x0e])[0], 3)
        by = {f["path"]: f for f in detect.scan(Sources("local", [self.mac]), local=True)}
        for rel in ("v1/Munjo16.rsrc", "v1g0/Munjo16.rsrc"):
            self.assertEqual((by[rel]["source_kind"], by[rel].get("mac")), ("mac-fbit1", {"generation": 1, "id": 1}), rel)
        self.assertEqual(by["Seoul12.rsrc"]["source_kind"], "mac-fbit3")          # a 7.1 font stays type 3

    def test_a_type3_fbit_whose_pixel_word_at_0x54_reads_45_sets_stays_type3(self):
        import macfx, struct
        raw = bytearray(macfx.fbit3_raw(1))
        raw[0x54:0x56] = struct.pack(">H", 0x021C)                 # 540 = 45 * 12: pixel bytes that look like a count
        fork = macfx.test_macfbit3.resource_fork({("fbit", 17408): bytes(raw)})
        out = detect.detect_file(self.put("t3.rsrc", fork), "t3.rsrc", local=True)
        self.assertEqual([e["source_kind"] for e in out], ["mac-fbit3"])

    def test_a_truncated_mac10_fbit_with_its_fdef_is_still_mac10(self):
        import macfx
        fbit = macfx.fbit1_raw()[:0x56 + 45 * 12 + 40]              # cut inside the glyph data
        fork = macfx.test_macfbit3.resource_fork({("fbit", 1): fbit, ("fdef", 3): bytes(0x800)})
        out = detect.detect_file(self.put("tr.rsrc", fork), "tr.rsrc", local=True)
        self.assertEqual([e["source_kind"] for e in out], ["mac-fbit1"])
        self.assertFalse([e for e in out if "unreadable" in e["label"]])
        bare = macfx.test_macfbit3.resource_fork({("fbit", 1): fbit})         # no fdef and a broken table: not 1.0
        out = detect.detect_file(self.put("tb.rsrc", bare), "tb.rsrc", local=True)
        self.assertNotIn("mac-fbit1", [e["source_kind"] for e in out])

    def test_a_mac10_fbit_cut_before_its_first_descriptor_is_not_mac10(self):
        import macfx
        fork = macfx.test_macfbit3.resource_fork({("fbit", 1): macfx.fbit1_raw()[:0x56], ("fdef", 3): bytes(0x800)})
        out = detect.detect_file(self.put("c.rsrc", fork), "c.rsrc", local=True)
        self.assertNotIn("mac-fbit1", [e["source_kind"] for e in out])
        self.assertFalse([e for e in out if "unreadable" in e["label"]], out)

    def test_a_type3_fbit_with_cell_height_0_is_not_unreadable(self):
        import macfx, struct
        raw = bytearray(macfx.fbit3_raw(1))
        raw[0x16:0x18] = struct.pack(">H", 0)
        out = detect.detect_file(self.put("h0.rsrc", macfx.test_macfbit3.resource_fork({("fbit", 17408): bytes(raw)})),
                                 "h0.rsrc", local=True)
        self.assertEqual([e["source_kind"] for e in out if e["source_kind"] in ("mac-fbit3", "mac-fbit1")], [])
        self.assertFalse([e for e in out if "unreadable" in e["label"]], out)

    def test_an_hbf_bitmap_replaced_after_detection_is_a_changed_input(self):
        import server
        from sources import Sources
        d = os.path.join(self.root, "pin")
        os.makedirs(d)
        with open(os.path.join(d, "x.hbf"), "w") as f:
            f.write("HBF_START_FONT 1.0\nHBF_BITMAP_BOUNDING_BOX 8 16 0 -3\nFONT_ASCENT 13\n"
                    "HBF_CODE_RANGE 0x0001-0x005A x.bin 0\n")
        import gzip
        with gzip.open(os.path.join(d, "x.bin.gz"), "wb") as g:
            g.write(b"\xff" * (0x5A * 16))
        sources = Sources("local", [d])
        entry = {f["path"]: f for f in detect.scan(sources, local=True)}["x.hbf"]
        st = os.lstat(os.path.join(d, "x.hbf"))
        entry["file_id"] = [st.st_dev, st.st_ino, st.st_size]
        entry["bitmap_ids"] = server.Handler._bitmap_ids(os.path.join(d, "x.hbf"))
        self.assertEqual([r[0] for r in entry["bitmap_ids"]], ["x.bin.gz"])          # the .gz fallback is what is read
        server.Handler._check_unchanged(entry, sources)                              # unchanged: fine
        with gzip.open(os.path.join(d, "x.bin.gz.new"), "wb") as g:                  # replaced by another file
            g.write(b"\x00" * (0x5A * 16))
        os.replace(os.path.join(d, "x.bin.gz.new"), os.path.join(d, "x.bin.gz"))
        with self.assertRaises(server._HttpError) as cm:
            server.Handler._check_unchanged(entry, sources)
        self.assertEqual(cm.exception.status, 409)
        entry["bitmap_ids"] = server.Handler._bitmap_ids(os.path.join(d, "x.hbf"))      # re-pinned: fine again
        server.Handler._check_unchanged(entry, sources)
        with open(os.path.join(d, "x.bin"), "wb") as f:                              # a plain bitmap appears: read_hbf prefers it
            f.write(b"\x00" * (0x5A * 16))
        with self.assertRaises(server._HttpError) as cm:
            server.Handler._check_unchanged(entry, sources)
        self.assertEqual(cm.exception.status, 409)

    def test_mac10_raw_resource_is_other(self):
        by = {f["path"]: f for f in detect.scan(Sources("local", [self.mac]), local=True)}
        entry = by["v1/raw/Munjo16.fbit"]
        self.assertEqual(entry["source_kind"], "other")
        self.assertEqual(entry["label"], "HangulTalk 1.0 fbit resource without its fdef: choose the font's resource fork")

    HWP_LABEL = (".PFT of an unknown layout: not an HWP 1.x font, an 8x4x4 or a KS X 1001 syllable dump, so not read by "
                 "this repository's tools (recipes.md, HWP 1.x and 2.x fonts)")

    def test_hwp_pft_label(self):
        import macfx
        self.put("hwp/HANGUL24.PFT", macfx.hangul_pft())
        (entry,) = detect.scan(Sources("local", [self.dir("hwp")]), local=True)
        self.assertEqual((entry["format"], entry["source_kind"], entry["label"]), ("hwp-pft", "other", self.HWP_LABEL))
        (up,) = detect.scan(self.dir("hwp"))                                     # an upload keeps today's label
        self.assertEqual((up["format"], up["label"].startswith("unknown (")), ("unknown", True))
        self.put("hwp2/hangul24.pft", macfx.hangul_pft())                          # the name rule is case-insensitive
        (low,) = detect.scan(Sources("local", [self.dir("hwp2")]), local=True)
        self.assertEqual(low["format"], "hwp-pft")

    def test_ascii_pft_from_another_folder(self):
        self.put("hwp/ASCII.PFT", inputfx.pft_eng())
        self.put("dos/HAN24.FNT", inputfx.dos844_24())
        fonts = detect.scan(Sources("local", [self.dir("hwp"), self.dir("dos")]), local=True)
        by = {f["path"]: f for f in fonts}
        self.assertEqual((by["ASCII.PFT"]["format"], by["ASCII.PFT"]["eng"]["cell"]), ("eng", "12x24"))
        self.assertIn(by["ASCII.PFT"]["id"], by["HAN24.FNT"]["companions"])
        up = detect.scan(self.root)                                               # upload: demoted, as today
        pft = next(f for f in up if f["path"].endswith("ASCII.PFT"))
        self.assertEqual(pft["format"], "unknown")
        self.assertIn("no DOS Johab font beside it", pft["label"])

    def test_taebaek_pft_faces_are_dos_faces_with_the_20x40_companion_in_a_local_scan(self):
        self.put("tb/GHANC40.PFT", bytes(72000))
        self.put("tb/GASCII40.PFT", bytes(30720))
        by = {f["path"]: f for f in detect.scan(Sources("local", [self.dir("tb")]), local=True)}
        self.assertEqual((by["GHANC40.PFT"]["format"], by["GHANC40.PFT"]["source_kind"]), ("dos-raw", "dos-raw"))
        self.assertEqual((by["GASCII40.PFT"]["format"], by["GASCII40.PFT"]["eng"]["cell"]), ("eng", "20x40"))
        self.assertEqual(by["GHANC40.PFT"]["companions"], [by["GASCII40.PFT"]["id"]])

    def test_hwp_pft_sizes_stay_hwp(self):
        for name, size in (("HANGUL1.PFT", 70592), ("ASCII.PFT", 41654), ("HANGUL24.PFT", 40000)):
            self.put("hw/" + name, bytes(size))
        by = {f["path"]: f for f in detect.scan(Sources("local", [self.dir("hw")]), local=True)}
        self.assertEqual({k: v["format"] for k, v in by.items()},
                         {"HANGUL1.PFT": "hwp-pft", "ASCII.PFT": "hwp-pft", "HANGUL24.PFT": "hwp-pft"})

    def test_a_20x40_companion_is_offered_across_folders_to_a_40px_face_only(self):
        self.put("tb/GHANC40.PFT", bytes(72000))
        self.put("tb24/HAN24.FNT", inputfx.dos844_24())
        self.put("other/GASCII40.PFT", bytes(30720))
        by = {f["path"]: f for f in detect.scan(Sources("local", [self.dir("tb"), self.dir("tb24"), self.dir("other")]),
                                                local=True)}
        self.assertIn(by["GASCII40.PFT"]["id"], by["GHANC40.PFT"]["companions"])
        self.assertNotIn(by["GASCII40.PFT"]["id"], by["HAN24.FNT"]["companions"])

    def test_8x16_eng_keeps_the_folder_rule(self):
        import fixtures
        fixtures._dos_raw(self.path("dos/HAN.FNT"))
        fixtures._eng(self.path("elsewhere/ENG.FNT"))
        fonts = detect.scan(Sources("local", [self.dir("dos"), self.dir("elsewhere")]), local=True)
        by = {f["path"]: f for f in fonts}
        self.assertEqual(by["ENG.FNT"]["format"], "unknown")
        self.assertEqual(by["HAN.FNT"]["companions"], [])

    def test_a_16_px_dos_font_takes_no_12x24_companion_from_elsewhere(self):
        import fixtures
        fixtures._dos_raw(self.path("dos/HAN.FNT"))
        self.put("hwp/ASCII.PFT", inputfx.pft_eng())
        fonts = detect.scan(Sources("local", [self.dir("hwp"), self.dir("dos")]), local=True)
        by = {f["path"]: f for f in fonts}
        self.assertEqual(by["ASCII.PFT"]["format"], "eng")                          # kept: a DOS font is in the batch
        self.assertEqual(by["HAN.FNT"]["companions"], [])                          # but not offered to a 16 px face

    def test_name_table_strings_are_capped_and_cleaned_in_a_local_scan(self):
        family = "Fam\x07ily" + "x" * 5000
        self.put("r/Long.ttf", inputfx.ttf(family, BOX1))
        (local,) = detect.scan(Sources("local", [self.dir("r")]), local=True)
        self.assertLessEqual(len(local["family"]), 64)
        self.assertNotIn("\x07", local["family"])
        self.assertTrue(local["family"].startswith("Family"))
        (up,) = detect.scan(self.dir("r"))                                       # an upload scan keeps today's strings
        self.assertGreater(len(up["family"]), 1000)

    def test_named_fork_off_elsewhere(self):
        """Off macOS a file with an empty data fork is `unknown` and no `..namedfork` path is opened or even asked for."""
        self.put("empty.bin", b"")
        seen = []
        real_open, real_size = open, os.path.getsize

        def spy_open(path, *a, **k):
            seen.append(str(path))
            return real_open(path, *a, **k)

        def spy_size(path):
            seen.append(str(path))
            return real_size(path)
        with mock.patch("builtins.open", spy_open), mock.patch("os.path.getsize", spy_size):
            fonts = detect.scan(Sources("local", [self.root + "/empty.bin"]), local=True)
        self.assertEqual([(f["source_kind"], f["label"]) for f in fonts], [("other", "unknown")])
        self.assertEqual([p for p in seen if "namedfork" in p], [])

    def test_named_fork_read_where_the_platform_offers_it(self):
        """The macOS branch, with the named fork supplied by a stand-in (this host has none): the entries are the fork's,
        their prep starts with `mac-fork-named`, and the scan prepares them from the named fork's bytes."""
        import macfx
        self.put("Seoul12", b"")
        fork = macfx.fbit3_fork()
        with mock.patch.object(detect, "_named_fork", lambda path: fork):
            fonts = detect.scan(Sources("local", [self.root + "/Seoul12"]), local=True)
        (entry,) = fonts
        self.assertEqual((entry["source_kind"], entry["prep"]),
                         ("mac-fbit3", [{"op": "mac-fork-named"}, {"op": "mac-fbit3"}]))
        self.assertEqual(entry["coverage"], {"ascii": 0, "ks2350": 2350, "all": 2350, "compat": 51})
        self.assertNotIn("cannot prepare", entry["label"])

    def test_mac71_in_upload_mode_is_other(self):
        for f in detect.scan(self.mac):
            self.assertEqual(f["source_kind"], "other", f["path"])
            self.assertNotIn("prep", f)
        by = {f["path"]: f for f in detect.scan(self.mac)}
        for rel in ("Seoul12.rsrc", "ad/._Seoul12", "jm/Seoul12", "raw/Seoul12.fbit", "raw/Seoul12.htbl1"):
            self.assertEqual(by[rel]["label"], "Mac bitmap font (NFNT/fbit): not converted here (local-only mode)", rel)

    def test_mac_tags_before_size_rules(self):
        import macfx
        from test_macfbit3 import jm_archive, lh5_block
        fork = macfx.fbit3_fork()
        payload = lh5_block([("lit", c) for c in fork])
        archive = jm_archive(payload + bytes(11520 - (0x16 + 8 + len(payload))), len(fork))   # padded to a DOS size
        self.assertEqual(len(archive), 11520)
        self.assertEqual(detect.sniff(archive[:512], 11520), "mac-jm")                  # not "dos-raw"
        big = jm_archive(payload, detect.JM_CAP + 1)                                       # over the cap: not tagged
        self.assertNotEqual(detect.sniff(big[:512], len(big)), "mac-jm")
        raw_fbit = macfx.fbit3_raw()
        self.assertEqual(detect.sniff(raw_fbit[:512], len(raw_fbit)), "mac-fbit-raw")
        self.assertEqual(detect.sniff(raw_fbit[:512], 11520), "mac-fbit-raw")          # not a DOS font whatever its size
        self.assertEqual(detect.sniff(macfx.htbl_raw()[:512], 9612), "mac-htbl-raw")
        self.assertEqual(detect.sniff(macfx.htbl_raw_padded()[:512], 9816), "mac-htbl-raw")
        self.assertNotEqual(detect.sniff(macfx.htbl_raw()[:512], 9000), "mac-htbl-raw")


class SourcesScanTest(DirCase):
    def test_scan_two_roots_keeps_folders_apart(self):
        for sub in ("a", "b"):
            self.put(sub + "/Munjo.ttf", inputfx.ttf("Munjo", BOX1))
            self.put(sub + "/OFL.txt", b"SIL Open Font License, Version 1.1\n")
        a, b = self.dir("a"), self.dir("b")
        fonts = detect.scan(Sources("local", [a, b]))
        ttfs = [f for f in fonts if f["format"] == "ttf"]
        self.assertEqual([f["root"] for f in ttfs], [0, 1])
        for f in ttfs:
            self.assertEqual([(l["root"], l["path"]) for l in f["licences"]], [(f["root"], "OFL.txt")])
        self.assertTrue(all("root" in f for f in fonts))
        self.assertEqual([f["id"] for f in fonts], ["f%02d" % i for i in range(1, len(fonts) + 1)])

    def test_file_roots_in_one_folder_pair_up(self):
        fonts_dir = self.dir("fonts")
        self.put("fonts/Munjo.ttf", inputfx.ttf("Munjo", BOX1))
        self.put("fonts/OFL.txt", b"SIL Open Font License, Version 1.1\n")
        self.put("fonts/NOTES.txt", b"This font is licensed under the SIL Open Font License.\n")
        with mock.patch("builtins.open", wraps=open) as spy:
            fonts = detect.scan(Sources("local", [fonts_dir + "/Munjo.ttf", fonts_dir + "/OFL.txt"]))
        ttf = next(f for f in fonts if f["format"] == "ttf")
        self.assertEqual(ttf["licences"], [{"root": 1, "path": "OFL.txt", "first_line": mock.ANY}])
        self.assertNotIn(fonts_dir + "/NOTES.txt", [c.args[0] for c in spy.call_args_list])   # never opened
        fonts = detect.scan(Sources("local", [fonts_dir + "/Munjo.ttf"]))
        self.assertEqual(fonts[0]["licences"], [])                         # alone: no licence found

    def test_upload_scan_matches_the_base_implementation_on_the_fixture_tree(self):
        """The upload scan of the standard fixture tree, as the implementation at ce976f8 (before `Sources`) produced it:
        ids, paths, formats, kinds, labels, sizes, licences and companions. The expected rows were generated from that
        commit and are written out here, so a change in the new code can fail this test."""
        fx = os.path.join(self.root, "fx")
        fixtures.write_fixtures(fx)
        got = [(f["id"], f["path"], f["format"], f["source_kind"], f["label"], f["sizes"],
                [l["path"] for l in f["licences"]], f["companions"]) for f in detect.scan(fx)]
        want = [
            ('f01', 'bdf/COPYING', 'unknown', 'other', 'unknown (436f707972696768)', [], [], []),
            ('f02', 'bdf/iso.bdf', 'bdf', 'bdf-iso10646', 'BDF (iso10646)', [16], ['bdf/COPYING'], []),
            ('f03', 'bdf/johab.bdf', 'bdf', 'bdf-johab', 'BDF (johab)', [16], ['bdf/COPYING'], []),
            ('f04', 'bdf/ksc.bdf', 'bdf', 'bdf-ksc5601', 'BDF (ksx1001.1998)', [24], ['bdf/COPYING'],
             ['f02', 'f05', 'f13']),
            ('f05', 'bdf/latin.bdf', 'bdf', 'bdf-iso8859', 'BDF (iso8859)', [16], ['bdf/COPYING'], []),
            ('f06', 'composite/Composite.ttf', 'ttf', 'outline-composite', 'TTF', [16], ['composite/LICENSE.txt'], []),
            ('f07', 'composite/LICENSE.txt', 'licence', 'other', 'licence text', [], [], []),
            ('f08', 'dos/ENG.FNT', 'eng', 'other', 'Latin companion (--eng)', [], ['dos/LICENSE.txt'], []),
            ('f09', 'dos/HAN.FNT', 'dos-raw', 'dos-raw', 'probable DOS Johab (844, 844-ihnm)', [16],
             ['dos/LICENSE.txt'], ['f08']),
            ('f10', 'dos/LICENSE.txt', 'licence', 'other', 'licence text', [], [], []),
            ('f11', 'fnt/win.fnt', 'fnt', 'bitmap', 'Windows FNT; no openable size', [], [], []),
            ('f12', 'hbf/ascii.bin', 'unknown', 'other', 'unknown (0000000000000000)', [], [], []),
            ('f13', 'hbf/ascii.hbf', 'hbf', 'hbf', 'HBF', [16], [], []),
            ('f14', 'list.txt', 'list', 'other', 'list file', [], [], []),
            ('f15', 'nanum/NanumGothic-Bold.ttf', 'ttf', 'outline', 'TTF', [16], ['nanum/OFL.txt'], []),
            ('f16', 'nanum/OFL.txt', 'licence', 'other', 'licence text', [], [], []),
            ('f17', 'nolic/NoLicence.ttf', 'ttf', 'outline', 'TTF', [16], [], []),
            ('f18', 'otf/Cff.otf', 'otf', 'outline', 'OTF', [16], ['otf/LICENSE.txt'], []),
            ('f19', 'otf/LICENSE.txt', 'licence', 'other', 'licence text', [], [], []),
            ('f20', 'pcf/18x18ko.pcf.gz', 'pcf', 'bitmap', 'PCF', [18], [], []),
            ('f21', 'svf/JAMO6J.SVF', 'svf', 'svf-jamo', 'SVF v3', [16], ['svf/LICENSE-OFL.txt', 'svf/NEODGM.TXT'], []),
            ('f22', 'svf/LICENSE-OFL.txt', 'licence', 'other', 'licence text', [], ['svf/NEODGM.TXT'], []),
            ('f23', 'svf/NEODG16.SVF', 'svf', 'svf-precomposed', 'SVF v3', [16],
             ['svf/LICENSE-OFL.txt', 'svf/NEODGM.TXT'], []),
            ('f24', 'svf/NEODGM.TXT', 'licence', 'other', 'licence text', [], ['svf/LICENSE-OFL.txt'], []),
        ]
        if not fixtures.HAS_PCF:
            self.skipTest("the PCF fixture is missing here: the ids would shift")
        self.assertEqual(got, want)
        for f in detect.scan(Sources("upload", [fx])):
            self.assertNotIn("root", f)

    def test_a_too_large_licence_file_is_not_read_or_attached(self):
        """SOL: a file refused as "too large, skipped" is no licence: it is not opened, hashed or attached."""
        import sources
        self.put("r/Munjo.ttf", inputfx.ttf("Munjo", BOX1))
        self.put("r/OFL.txt", b"SIL Open Font License, Version 1.1\n" + b"x" * 200)
        real_open = open
        opened = []

        def spy(path, *a, **k):
            opened.append(str(path))
            return real_open(path, *a, **k)
        with mock.patch.object(sources, "LOCAL_FILE_CAP", 100), mock.patch("builtins.open", spy):
            fonts = detect.scan(Sources("local", [self.dir("r")]), local=True)
        by = {f["path"]: f for f in fonts}
        self.assertEqual(by["OFL.txt"]["label"], "too large, skipped")
        self.assertEqual(by["Munjo.ttf"]["licences"], [])
        self.assertEqual(by["OFL.txt"]["licences"], [])
        self.assertEqual([p for p in opened if p.endswith("OFL.txt")], [])

    def test_upload_scan_entries(self):
        """The upload scan's shape, spelled out: no root key, root-relative paths, today's symlink entry."""
        self.put("a/Munjo.ttf", inputfx.ttf("Munjo", BOX1))
        self.put("a/OFL.txt", b"SIL Open Font License, Version 1.1\n")
        os.symlink("Munjo.ttf", self.dir("a") + "/link.ttf")
        for src in (self.root, Sources("upload", [self.root])):
            fonts = detect.scan(src)
            self.assertEqual([(f["id"], f["path"], f["format"]) for f in fonts],
                             [("f01", "a/Munjo.ttf", "ttf"), ("f02", "a/OFL.txt", "licence"),
                              ("f03", "a/link.ttf", "unknown")])
            by_path = {f["path"]: f for f in fonts}
            self.assertEqual(sorted(by_path), ["a/Munjo.ttf", "a/OFL.txt", "a/link.ttf"])
            self.assertTrue(all("root" not in f for f in fonts))
            self.assertEqual(by_path["a/link.ttf"]["label"], "symlink, skipped")
            self.assertEqual(by_path["a/Munjo.ttf"]["licences"],
                             [{"path": "a/OFL.txt", "first_line": "SIL Open Font License, Version 1.1"}])

    def test_scan_temp_copies_stay_in_tmp_dir(self):
        sentinel = tempfile.mkdtemp()
        tmpd = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, sentinel, ignore_errors=True)
        self.addCleanup(shutil.rmtree, tmpd, ignore_errors=True)
        import gzip
        fixtures._bdf(self.path("k/ksc.bdf"), fixtures._ksc_glyphs(), 24, 19, 5, "KSX1001.1998", (24, 24))
        with open(self.dir("k/ksc.bdf"), "rb") as f:
            data = f.read()
        os.remove(self.dir("k/ksc.bdf"))
        self.put("k/ksc.bdf.gz", gzip.compress(data, mtime=0))
        with mock.patch.object(tempfile, "tempdir", sentinel):
            fonts = detect.scan(Sources("local", [self.dir("k")], tmp_dir=tmpd), local=True)
        self.assertIsNotNone(fonts[0]["coverage"])
        self.assertEqual(os.listdir(sentinel), [])
        self.assertEqual(os.listdir(tmpd), [])

    def test_local_labels_name_no_input_bytes(self):
        self.put("r/x.bin", bytes(range(1, 65)))
        self.put("r/bad.ttf", b"\x00\x01\x00\x00" + b"\xff\xfe" * 40)
        self.put("r/z.zip", b"PK\x03\x04" + bytes(40))
        fonts = {f["path"]: f for f in detect.scan(Sources("local", [self.dir("r")]), local=True)}
        self.assertEqual(fonts["x.bin"]["label"], "unknown")
        self.assertRegex(fonts["bad.ttf"]["label"], r"^unreadable: [A-Za-z_]+$")
        self.assertEqual(fonts["bad.ttf"]["error_type"], fonts["bad.ttf"]["label"].split(": ")[1])
        self.assertIn("  detect.py:", fonts["bad.ttf"]["error"])          # type and frames, no message
        self.assertNotIn("Traceback", fonts["bad.ttf"]["error"])
        self.assertEqual(fonts["z.zip"]["format"], "archive")
        self.assertEqual(fonts["z.zip"]["label"], "archive: extract it first, then choose the folder")
        up = {f["path"]: f for f in detect.scan(self.dir("r"))}                 # an upload keeps today's labels
        self.assertRegex(up["x.bin"]["label"], r"^unknown \([0-9a-f]+\)$")
        self.assertNotIn("z.zip", up)

    def test_overlapping_roots_list_each_file_once_with_its_own_licence(self):
        self.put("r/Munjo.ttf", inputfx.ttf("Munjo", BOX1))
        self.put("r/OFL.txt", b"SIL Open Font License, Version 1.1\n")
        self.put("r/sub/Other.ttf", inputfx.ttf("Other", BOX2))
        r = self.dir("r")
        for roots in ([r, r], [r, r + "/sub"], [r + "/Munjo.ttf", r]):
            fonts = detect.scan(Sources("local", roots))
            ttfs = [f for f in fonts if f["format"] == "ttf"]
            self.assertEqual(sorted(f["path"].split("/")[-1] for f in ttfs), ["Munjo.ttf", "Other.ttf"], roots)
            munjo = next(f for f in ttfs if f["path"].endswith("Munjo.ttf"))
            self.assertLessEqual(len(munjo["licences"]), 1, roots)
            for l in munjo["licences"]:                      # a licence names a file that exists under its own root
                base = Sources("local", roots).roots[l["root"]]
                self.assertTrue(os.path.isfile(os.path.join(base, l["path"])), (roots, l))

    def test_unreadable_folder_is_an_other_entry(self):
        if os.geteuid() == 0:
            self.skipTest("root reads every folder")
        self.put("r/ok.ttf", inputfx.ttf("Ok", BOX1))
        self.put("r/locked/x.ttf", inputfx.ttf("X", BOX2))
        os.chmod(self.dir("r/locked"), 0)
        self.addCleanup(os.chmod, self.dir("r/locked"), 0o755)
        fonts = detect.scan(Sources("local", [self.dir("r")]))
        self.assertIn(("locked", "unknown", "unreadable, skipped"),
                      [(f["path"], f["format"], f["label"]) for f in fonts])


if __name__ == "__main__":
    unittest.main()
