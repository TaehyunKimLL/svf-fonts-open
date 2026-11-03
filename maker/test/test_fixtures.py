#!/usr/bin/env python3
"""fixtures.py tests: the tree it writes, the composite TTF's syllable glyphs, the johab BDF and the DOS raw font.

  python3 -m unittest discover -s maker/test -p 'test_*.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import subprocess
import tempfile
import time
import unittest

import fixtures


class FixturesTest(unittest.TestCase):
    def test_tree_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            got = fixtures.write_fixtures(d)
            for key in ("ttf", "composite", "otf", "svf_pre", "svf_jamo", "bdf_iso", "bdf_ksc", "bdf_johab",
                        "bdf_latin", "hbf", "dos_raw", "dos_eng", "fnt", "nolic", "list"):
                self.assertTrue(os.path.isfile(got[key]), key)
            self.assertEqual(os.path.getsize(got["dos_raw"]), 11520)
            self.assertEqual(os.path.getsize(got["dos_eng"]), 2048)
            with open(got["fnt"], "rb") as f:
                self.assertEqual(f.read(2), b"\x00\x02")
            self.assertEqual(sorted(os.listdir(os.path.join(d, "nolic"))), ["NoLicence.ttf"])

    def test_composite_syllables_are_composites(self):
        from fontTools.ttLib import TTFont
        with tempfile.TemporaryDirectory() as d:
            f = TTFont(fixtures.write_fixtures(d)["composite"])
            glyf, cmap = f["glyf"], f.getBestCmap()
            self.assertTrue(glyf[cmap[0xAC00]].isComposite())
            self.assertEqual(len(glyf[cmap[0xAC01]].components), 3)
            self.assertEqual(len(glyf[cmap[0xAC00]].components), 2)
            self.assertEqual(sum(1 for cp in cmap if 0xAC00 <= cp <= 0xD7A3), 66)
            self.assertFalse(glyf[cmap[0x41]].isComposite())
            self.assertNotEqual(glyf[cmap[0x41]].getCoordinates(glyf), glyf[".notdef"].getCoordinates(glyf))
            self.assertFalse(os.path.exists(os.path.join(d, "LICENSE.txt")))   # no licence at the root

    def test_johab_bdf_opens_as_hanterm(self):
        import jamoset
        with tempfile.TemporaryDirectory() as d:
            with open(fixtures.write_fixtures(d)["bdf_johab"], "rb") as f:
                data = f.read()
            self.assertEqual(jamoset.LAYOUTS["hanterm-johab"].opener(data).count, 529)

    def test_dos_raw_passes_844_blank_check(self):
        import jamoset
        with tempfile.TemporaryDirectory() as d:
            with open(fixtures.write_fixtures(d)["dos_raw"], "rb") as f:
                data = f.read()
            jamoset.LAYOUTS["844"].opener(data)   # raises SourceError when the fill slots are not blank

    def test_composite_hangul_has_ink(self):
        """The composite jamo pieces must carry ink at a practical size, and mkfont must keep the syllables."""
        import jamovec, jamoset
        with tempfile.TemporaryDirectory() as d:
            path = fixtures.write_fixtures(d)["composite"]
            master = jamovec.build_master(path, components=True)
            svf, _ = jamovec.render(master, 16, bpp=2)
            f = jamoset.parse_svfn(svf)
            t = jamoset.unpack(f.jset)
            for cp in (0xAC00, 0xAC01):    # 가, and 각: a syllable that ends in a final
                self.assertTrue(any(jamoset.compose(f, t, cp)), "U+%04X draws no ink at 16 px" % cp)
            out = os.path.join(d, "composite.svf")
            subprocess.run([sys.executable, "-P", os.path.join(fixtures.REPO_DIR, "tools", "mkfont.py"),
                            path, out, "--size", "16", "--bpp", "2", "--unicode", "ascii,hangul"],
                           check=True, capture_output=True)
            with open(out, "rb") as fh:
                kept = jamoset.parse_svfn(fh.read()).glyphs
            self.assertEqual(sum(1 for cp in kept if 0xAC00 <= cp <= 0xD7A3), 66)

    def test_tree_is_deterministic(self):
        """Two runs must write the same bytes: no build timestamp may leak into the tree."""
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first = fixtures.write_fixtures(a)
            time.sleep(1.1)   # a second apart, as two real runs: a leaked `created` timestamp shows up here
            second = fixtures.write_fixtures(b)
            self.assertEqual(sorted(first), sorted(second))
            for key in sorted(first):
                with open(first[key], "rb") as fa, open(second[key], "rb") as fb:
                    self.assertEqual(fa.read(), fb.read(), key)


if __name__ == "__main__":
    unittest.main()


class FixtureDestinationTest(unittest.TestCase):
    def test_refuses_a_non_empty_destination(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "LICENSE.txt"), "w").close()
            with self.assertRaises(ValueError):
                fixtures.write_fixtures(d)

    def test_refuses_a_symlinked_destination(self):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "real"))
            os.symlink(os.path.join(d, "real"), os.path.join(d, "link"))
            with self.assertRaises(ValueError):
                fixtures.write_fixtures(os.path.join(d, "link"))
