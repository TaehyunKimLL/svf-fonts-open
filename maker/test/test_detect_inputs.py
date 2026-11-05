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

    def test_mac10_raw_resource_is_other(self):
        by = {f["path"]: f for f in detect.scan(Sources("local", [self.mac]), local=True)}
        entry = by["v1/raw/Munjo16.fbit"]
        self.assertEqual(entry["source_kind"], "other")
        self.assertEqual(entry["label"], "HangulTalk 1.0 fbit resource without its fdef: choose the font's resource fork")

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
