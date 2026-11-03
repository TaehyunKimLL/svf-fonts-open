#!/usr/bin/env python3
"""quality.py tests: the facts read back from a face and its quality numbers.

  python3 -m unittest discover -s maker/test -p 'test_*.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import unittest

import jamoaa
import jamoset
import quality

SVF = os.path.join(REPO_DIR, "svf")


def read(path):
    """A file's bytes (a context manager, so a test leaves no file handle open)."""
    with open(path, "rb") as f:
        return f.read()


def jamo_face(face, jset, pieces=True):
    """An SVFN v3 face (jamoset.write_svfn, so pack_svfn) with @p face's geometry and glyph bytes and @p jset as its JSET block; with @p pieces False it
    carries no glyph for any piece code point."""
    glyphs = [(cp, g, 0, 0, 0) for cp, g in face.glyphs.items() if pieces or cp < jamoset.PIECE_BASE]
    return jamoset.write_svfn(face.cell_w, face.cell_h, face.ascent, glyphs, jset)


class FactsTest(unittest.TestCase):
    def test_list_face_facts(self):
        import subprocess
        import tempfile
        for variant in ("list1", "list_compat"):
            with self.subTest(variant=variant):
                with tempfile.TemporaryDirectory(prefix="quality-list-") as d:
                    out = os.path.join(d, "L.SVF")
                    r = subprocess.run([sys.executable, os.path.join(REPO_DIR, "tools", "svf_synth.py"), "--jmap-variant",
                                        variant, "--from", os.path.join(SVF, "dos", "NEODG16G.SVF"), out],
                                       capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    data = read(out)
                t = jamoset.unpack(jamoset.parse_svfn(data).jset)
                named = {n for e in t.entries.values() for n in e if n != jamoset.BLANK}
                comp = {n for n in t.block_compat if n != jamoset.BLANK}
                if variant == "list_compat":
                    self.assertTrue(comp - named, "the variant names a compat piece beyond the entries")
                facts = quality.face_facts(data)["jset"]
                self.assertEqual(facts, {"sets": None, "classes": None, "pieces": None, "jmap": True, "jmap_mode": "list",
                                         "pool": len(named | comp)})
                self.assertGreater(facts["pool"], 0)

    def test_precomposed_and_jamo_facts(self):
        pre = quality.face_facts(read(os.path.join(SVF, "dos", "NEODG16.SVF")))
        self.assertEqual((pre["version"], pre["bpp"], pre["cell"], pre["jamo"]), (3, 1, [16, 16], False))
        jam = quality.face_facts(read(os.path.join(SVF, "dos", "NEODG16G.SVF")))
        self.assertTrue(jam["jamo"]); self.assertEqual(jam["jset"]["classes"], [1, 2]); self.assertEqual(jam["jset"]["sets"], [6, 2, 1])
        self.assertEqual((jam["cell"], jam["ascent"], jam["glyphs"]), ([16, 16], 12, 279))
        with self.assertRaises(ValueError): quality.face_facts(b"SVFN\x01\x00" + bytes(60))

    def test_a_v2_face_is_not_a_maker_output(self):
        """The maker writes v3 only (jamoset.pack_svfn): the same face as v2 is refused, its v3 conversion is not."""
        import fixtures
        import svf2to3
        v2 = fixtures.v2_face(read(os.path.join(SVF, "dos", "NEODG16.SVF")))
        with self.assertRaisesRegex(ValueError, "not an SVFN v3 font"):
            quality.face_facts(v2)
        self.assertEqual(quality.face_facts(svf2to3.convert(v2, "default"))["version"], 3)


class BrokenFaceTest(unittest.TestCase):
    """A structurally damaged face is not an SVFN v3 the page may report: ValueError, never struct.error."""

    def test_truncated_by_half(self):
        data = read(os.path.join(SVF, "dos", "NEODG16G.SVF"))
        with self.assertRaises(ValueError):
            quality.face_facts(data[:len(data) // 2])

    def test_one_byte_short(self):
        data = read(os.path.join(SVF, "dos", "NEODG16G.SVF"))
        with self.assertRaises(ValueError):
            quality.face_facts(data[:-1])

    def test_bpp_zero(self):
        data = bytearray(read(os.path.join(SVF, "dos", "NEODG16G.SVF")))
        data[8] = 0  # header byte 8 is the bpp
        with self.assertRaises(ValueError):
            quality.face_facts(bytes(data))

    def test_short_header(self):
        with self.assertRaises(ValueError):
            quality.face_facts(b"SVFN")


class UnusableJsetTest(unittest.TestCase):
    """A JSET the renderer would not use makes the face a plain precomposed SVFN (spec/SVF.md), not an error."""

    @classmethod
    def setUpClass(cls):
        cls.jam = jamoset.parse_svfn(read(os.path.join(SVF, "dos", "NEODG16G.SVF")))
        cls.pre = os.path.join(SVF, "dos", "NEODG16.SVF")

    def _assert_precomposed(self, data):
        self.assertIsNone(quality.face_facts(data)["jset"])
        self.assertIsNone(quality.measure(data, "svf", self.pre, None))

    def test_bad_length_jset(self):
        self._assert_precomposed(jamo_face(self.jam, self.jam.jset + b"\x00"))

    def test_empty_jset(self):
        self._assert_precomposed(jamo_face(self.jam, b""))

    def test_piece_without_a_glyph(self):
        self._assert_precomposed(jamo_face(self.jam, self.jam.jset, pieces=False))


class CompareTest(unittest.TestCase):
    def test_own_composition_scores_one(self):
        face = jamoset.parse_svfn(read(os.path.join(SVF, "dos", "NEODG16G.SVF")))
        own = {s: jamoset.glyph_gint(g, face.cell_w, face.cell_h) for s, g in quality.composed_syllables(face).items() if any(g)}
        q = quality.compare(face, own)
        self.assertEqual((q["all"], q["ks2350"]), (1.0, 1.0)); self.assertEqual(q["compared"], len(own))
    def test_two_bpp_own_levels_score_zero(self):
        p = os.path.join(SVF, "jamo-extra", "GOTHA16A.SVF")
        face = jamoset.parse_svfn(read(p))
        own = {s: jamoaa.unpack_levels(g, 16, 16, 2) for s, g in list(quality.composed_syllables(face).items())[:200]}
        self.assertEqual(quality.compare(face, own)["all"], 0.0)
    def test_empty_targets(self):
        face = jamoset.parse_svfn(read(os.path.join(SVF, "dos", "NEODG16G.SVF")))
        self.assertEqual(quality.compare(face, {}), {"all": None, "ks2350": None, "compared": 0})
    def test_measure_without_reference(self):
        self.assertIsNone(quality.measure(read(os.path.join(SVF, "dos", "NEODG16G.SVF")), None, None, None))


class ReferencePathTest(unittest.TestCase):
    """The reference the maker really scores against: the tools' own targets on the repo's own faces."""

    @classmethod
    def setUpClass(cls):
        cls.pre = os.path.join(SVF, "dos", "NEODG16.SVF")
        cls.jam_bytes = read(os.path.join(SVF, "dos", "NEODG16G.SVF"))
        cls.jam = jamoset.parse_svfn(cls.jam_bytes)

    def test_svf_reference_is_the_file_syllables(self):
        targets = quality.reference_targets("svf", self.pre, None, self.jam)
        self.assertEqual(len(targets), 2357)
        self.assertTrue(all(0 <= s <= 11171 for s in targets))

    def test_measure_against_the_svf_reference(self):
        q = quality.measure(self.jam_bytes, "svf", self.pre, None)
        self.assertEqual(q["compared"], 2357)
        self.assertLess(0, q["all"]); self.assertLess(q["all"], 1)

    def test_one_pixel_off_scores_below_one(self):
        comp = quality.composed_syllables(self.jam)
        s = next(s for s, g in comp.items() if any(g))
        targets = {s: jamoset.glyph_gint(comp[s], 16, 16) ^ 1}
        self.assertLess(quality.compare(self.jam, targets)["all"], 1.0)

    def test_one_level_off_scores_above_zero(self):
        face = jamoset.parse_svfn(read(os.path.join(SVF, "jamo-extra", "GOTHA16A.SVF")))
        comp = quality.composed_syllables(face)
        s = next(s for s, g in comp.items() if any(g))
        levels = jamoaa.unpack_levels(comp[s], 16, 16, 2)
        levels[0] = (levels[0] + 1) % 4  # 2 bpp levels are 0..3
        self.assertGreater(quality.compare(face, {s: levels})["all"], 0.0)

    def test_measure_precomposed_is_none(self):
        self.assertIsNone(quality.measure(read(self.pre), "svf", self.pre, None))

    def test_svf_reference_refuses_a_two_bpp_face(self):
        data = read(os.path.join(SVF, "jamo-extra", "GOTHA16A.SVF"))
        with self.assertRaisesRegex(ValueError, "an SVF reference scores 1 bpp faces only"):
            quality.measure(data, "svf", self.pre, None)

    def test_compare_refuses_a_face_without_a_usable_jset(self):
        with self.assertRaisesRegex(ValueError, "the face has no usable jamo set"):
            quality.compare(jamoset.parse_svfn(read(self.pre)), {0: [0]})
        with self.assertRaisesRegex(ValueError, "the face has no usable jamo set"):
            quality.composed_syllables(jamoset.parse_svfn(read(self.pre)))

    def test_unknown_reference(self):
        with self.assertRaises(ValueError):
            quality.reference_targets("nope", self.pre, None, self.jam)
