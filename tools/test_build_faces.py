#!/usr/bin/env python3
"""tools/build/faces.tsv and tools/build/build_faces.py: every face of svf/ has exactly one recipe row, the rows are
well formed, and a few small faces rebuild byte for byte from the fonts in ttf/.
  python3 -m unittest tools.test_build_faces
"""
import glob
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "build"))
import build_faces  # noqa: E402


class Table(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = build_faces.read_table()

    def test_every_face_has_one_row(self):
        faces = sorted(os.path.relpath(p, os.path.join(ROOT, "svf")).replace(os.sep, "/")
                       for p in glob.glob(os.path.join(ROOT, "svf", "**", "*.SVF"), recursive=True))
        names = [r["face"] for r in self.rows]
        self.assertEqual(len(names), len(set(names)), "a face with two rows")
        self.assertEqual(sorted(names), faces)

    def test_rows_are_complete(self):
        for r in self.rows:
            with self.subTest(face=r["face"]):
                if r["method"] == "none":
                    self.assertTrue(r["note"])
                    continue
                src = r["source"]
                if not src.startswith("ext:"):
                    self.assertTrue(os.path.isfile(os.path.join(ROOT, src)), src)
                if r["codepoints"].startswith("cps/"):
                    path = os.path.join(HERE, "build", r["codepoints"])
                    self.assertTrue(os.path.isfile(path), path)
                    self.assertTrue(build_faces.codepoints(r["codepoints"]))
                if r["method"] == "jamoset":
                    self.assertIn("|", r["args"])
                if r["expect"] == "differs":
                    self.assertTrue(r["note"], "a differing row says how")

    def test_counts(self):
        methods = [r["method"] for r in self.rows]
        self.assertEqual((methods.count("mkfont"), methods.count("jamoset"), methods.count("none")), (46, 7, 63))


class Rebuild(unittest.TestCase):
    def test_small_faces_are_identical(self):
        with tempfile.TemporaryDirectory() as d:
            for face in ("NEO16BX2", "GBA14X2", "NEODG16G"):
                with self.subTest(face=face):
                    self.assertEqual(build_faces.main(["--out", d, face]), 0)
                    with open(os.path.join(d, "dos", face + ".SVF"), "rb") as a, \
                            open(os.path.join(ROOT, "svf", "dos", face + ".SVF"), "rb") as b:
                        self.assertEqual(a.read(), b.read())

    def test_unknown_face_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(build_faces.main(["--out", d, "NOPE"]), 2)

    def test_ext_row_without_ext_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(build_faces.main(["--out", d, "NGO17X1"]), 0)
            self.assertFalse(os.path.exists(os.path.join(d, "dos", "NGO17X1.SVF")))


if __name__ == "__main__":
    unittest.main()
