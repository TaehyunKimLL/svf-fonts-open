#!/usr/bin/env python3
"""The maker's mkfont routes write the canonical file build_faces.py writes (card t_df773bf5): mkfont, then
`svf2to3.py TMP OUT --profile default`.

GowunBatang-Bold at 17 px 2 bpp through preset dos-u-2bpp is byte-equal to svf/dos/GBATB17.SVF and the step reports
`identical_to`; canonicalising changes the encoding of a face, never its pixels.

  python3 -m unittest discover -s maker/test -p 'test_canonical_mkfont.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import glob
import shutil
import subprocess
import tempfile
import unittest

import inputkinds
import wincompat
from inputkinds import select

TTF = os.path.join(REPO_DIR, "ttf", "gowunbatang", "GowunBatang-Bold.ttf")
SHIPPED = os.path.join(REPO_DIR, "svf", "dos", "GBATB17.SVF")


class CanonicalMkfontTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="canon-mkfont-")
        with open(TTF, "rb") as f:
            data = f.read()

        def choose(fonts, st):
            select(st, inputkinds.only_font(fonts), bpp=(2,), preset="dos-u-2bpp", sizes=[17])
        cls.store, cls.job, _ = None, None, None
        cls.job, cls.zip = inputkinds.run_batch(unittest.TestCase(), os.path.join(cls.tmp, "j"),
                                                {"g/GowunBatang-Bold.ttf": data}, choose)
        step = cls.job["steps"][0]
        hits = glob.glob(os.path.join(cls.tmp, "j", "**", step["output"]), recursive=True)
        assert len(hits) == 1, hits
        cls.out = hits[0]
        with open(cls.out, "rb") as f:
            cls.bytes = f.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_step_commands_are_mkfont_then_svf2to3(self):
        self.assertEqual(inputkinds.step_tools(self.job["steps"]), [["mkfont.py", "svf2to3.py"]])

    def test_gowun_bold_17_2bpp_equals_the_shipped_face(self):
        self.assertEqual(self.job["steps"][0]["state"], "done")
        with open(SHIPPED, "rb") as g:
            shipped = g.read()
        if wincompat.render_matches(self.bytes, shipped, "GBATB17.SVF"):
            return                                     # byte-equal (Windows: but for the pinned glyph, wincompat)
        if self.bytes != shipped:                      # say which characters differ, not only that the bytes do
            import jamoset
            a, b = jamoset.parse_svfn(self.bytes), jamoset.parse_svfn(shipped)
            only_a = sorted(set(a.glyphs) - set(b.glyphs))
            only_b = sorted(set(b.glyphs) - set(a.glyphs))
            differ = sorted(cp for cp in set(a.glyphs) & set(b.glyphs) if a.glyphs[cp] != b.glyphs[cp])
            self.fail("made %d glyphs, shipped %d; only made %s; only shipped %s; %d differ %s" % (
                len(a.glyphs), len(b.glyphs), [hex(c) for c in only_a[:20]], [hex(c) for c in only_b[:20]],
                len(differ), [hex(c) for c in differ[:20]]))

    def test_the_step_is_recognised_as_the_shipped_face(self):
        with open(SHIPPED, "rb") as g:
            same = self.bytes == g.read()
        # Windows: not the shipped bytes (the pinned glyph, wincompat), so rightly not recognised as the shipped face
        self.assertEqual(self.job["steps"][0]["identical_to"], "dos/GBATB17.SVF" if same or not wincompat.WIN else None)

    def test_a_face_that_is_not_shipped_keeps_its_pixels(self):
        """Another size (no shipped face): the output differs from mkfont's own file in encoding only."""
        import svf2to3
        with open(TTF, "rb") as f:
            data = f.read()

        def choose(fonts, st):
            select(st, inputkinds.only_font(fonts), bpp=(1,), preset="dos-l-1bpp", sizes=[15])
        job, _ = inputkinds.run_batch(unittest.TestCase(), os.path.join(self.tmp, "k"), {"g/GowunBatang-Bold.ttf": data}, choose)
        step = job["steps"][0]
        self.assertIsNone(step["identical_to"])
        out = glob.glob(os.path.join(self.tmp, "k", "**", step["output"]), recursive=True)[0]
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(out), "mkfont.tmp")))   # the temp is removed
        raw = os.path.join(self.tmp, "raw.svf")
        argv = list(step["argv"][0])
        argv[argv.index(next(t for t in argv if t.endswith("mkfont.tmp")))] = raw
        subprocess.run(argv, check=True, capture_output=True, cwd=self.tmp)
        with open(raw, "rb") as f, open(out, "rb") as g:
            raw_data, out_data = f.read(), g.read()
        self.assertNotEqual(raw_data, out_data)               # re-laid out (the default profile)
        svf2to3.check(raw_data, out_data)                     # same glyphs, metrics and cells

    def test_a_rerun_never_converts_the_last_runs_temp(self):
        """A mkfont that exits 0 without writing must fail "no output", not canonicalise an old mkfont.tmp."""
        import jobs
        step_dir = os.path.join(self.tmp, "stale")
        os.makedirs(step_dir)
        names = ("mkfont.tmp", "mac.bdf", "mac-sized.bdf", "OUT.SVF")
        for name in names:
            with open(os.path.join(step_dir, name), "wb") as f:
                f.write(b"old")
        jobs.Worker._clear_outputs(step_dir, os.path.join(step_dir, "OUT.SVF"), {"kind": "precomposed"})
        self.assertEqual([n for n in names if os.path.exists(os.path.join(step_dir, n))], [])

    def test_the_temp_name_can_never_be_a_face_name(self):
        """On a case-insensitive filesystem a face named MKFONT.SVF would be the temp file itself (and be removed)."""
        import naming
        import routes
        self.assertIsNone(naming.NAME_RE.match(routes.MKFONT_TMP))
        self.assertIsNone(naming.NAME_RE.match(routes.MKFONT_TMP.upper()))
        for name in routes.MAC_BDFS:
            self.assertIsNone(naming.NAME_RE.match(name.upper()))

    def test_the_final_command_writes_the_step_output(self):
        last = self.job["steps"][0]["argv"][-1]
        self.assertEqual(os.path.basename(last[-4]), "mkfont.tmp")
        self.assertEqual(os.path.basename(last[-3]), os.path.basename(self.out))
        self.assertEqual(last[-2:], ["--profile", "default"])


if __name__ == "__main__":
    unittest.main()
