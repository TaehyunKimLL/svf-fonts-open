#!/usr/bin/env python3
"""SVF -> TTF / BDF export (card t_97acecf9): the `options.export` setting, the `export` steps (tools/svf2ttf.py after
each face step), the `svf2ttf` route of an SVF source, their read-back and the files a local job writes.

  python3 -m unittest discover -s maker/test -p 'test_export.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools"), TEST_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import copy
import shutil
import subprocess
import tempfile
import unittest

import detect
import fixtures
import naming
import quality
import routes
import settings
import toolrun
from localfx import LocalBase, LocalRunBase, walk_rel
from test_routes import FONT_SVF_JAMO, FONT_SVF_PRE, FONT_TTF

NEODG16 = os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF")      # precomposed 1 bpp, OFL
NEODG16G = os.path.join(REPO_DIR, "svf", "dos", "NEODG16G.SVF")    # a small jamo set


class ExportRoutesTest(unittest.TestCase):
    def test_export_name(self):
        self.assertEqual(routes.export_name("NANUM16.SVF", "ttf"), "NANUM16.ttf")
        self.assertEqual(routes.export_name("NANU16JA.SVF", "bdf"), "NANU16JA.bdf")
        self.assertTrue(naming.EXPORT_RE.match("NANUM16.ttf"))
        self.assertFalse(naming.EXPORT_RE.match("NANUM16.TTF"))
        with self.assertRaises(ValueError):
            routes.export_name("NANUM16.SVF", "otf")

    def test_export_commands(self):
        self.assertEqual(routes.export_commands("ttf", "/w/s01/A16.SVF", "/w/s02/A16.ttf", "/T"),
                         [toolrun.tool("svf2ttf", "/T") + ["ttf", "/w/s01/A16.SVF", "/w/s02/A16.ttf"]])
        self.assertEqual(routes.export_commands("bdf", "/f.SVF", "/o.bdf", "/T", licence="/u/OFL.txt")[0][-2:],
                         ["--licence", "/u/OFL.txt"])

    def test_composite_is_a_ttf_flag(self):
        """t_baf48b58's `svf2ttf.py --composite`: a jamo set's TTF only."""
        self.assertEqual(routes.export_commands("ttf", "/f.SVF", "/o.ttf", "/T", composite=True)[0][-1], "--composite")
        self.assertNotIn("--composite", routes.export_commands("bdf", "/f.SVF", "/o.bdf", "/T", composite=True)[0])
        self.assertNotIn("--composite", routes.export_commands("ttf", "/f.SVF", "/o.ttf", "/T")[0])

    def test_svf2ttf_route_of_an_svf_source(self):
        pre = [r for r in routes.routes(FONT_SVF_PRE) if r.label == "svf2ttf"]
        jamo = [r for r in routes.routes(FONT_SVF_JAMO) if r.label == "svf2ttf"]
        self.assertEqual([(r.kind, r.native, r.export_only) for r in pre], [("precomposed", True, True)])
        self.assertEqual([(r.kind, r.native, r.export_only) for r in jamo], [("jamo", True, True)])
        self.assertFalse(any(r.label == "svf2ttf" for r in routes.routes(FONT_TTF)))
        # the default stays the copy; the label picks svf2ttf for either kind
        self.assertEqual(routes.route_for(FONT_SVF_PRE, "precomposed", False).label, "copy")
        self.assertEqual(routes.route_for(FONT_SVF_PRE, "precomposed", False, None, "svf2ttf").label, "svf2ttf")
        self.assertEqual(routes.route_for(FONT_SVF_JAMO, "jamo", False, "svf2ttf").label, "svf2ttf")
        self.assertIsNone(routes.route_for(FONT_TTF, "precomposed", False, None, "svf2ttf"))
        # the face is used as it is (a v3 SVF: the worker's copy)
        self.assertEqual(pre[0].commands(FONT_SVF_PRE, 16, 1, None, ("2350", None),
                                         {"tools": "/T", "src": "/u/A.SVF", "out": "/w/A.SVF"}, []), [])


class ExportSettingsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="svf-export-settings-")
        cls.addClassCleanup(shutil.rmtree, cls.root, True)
        fixtures.write_fixtures(cls.root)
        cls.fonts = detect.scan(cls.root)

    def fid(self, path):
        return next(f["id"] for f in self.fonts if f["path"] == path)

    def only(self, path, **over):
        s = settings.defaults(self.fonts)
        for per in s["fonts"].values():
            per["selected"] = False
        s["fonts"][self.fid(path)].update(selected=True, **over)
        return s

    def test_default_is_no_export(self):
        s = settings.defaults(self.fonts)
        self.assertEqual(s["batch"]["options"]["export"], {"ttf": False, "bdf": False, "composite": False})
        self.assertEqual(settings.validate(self.fonts, s, self.root), [])

    def test_export_values_must_be_booleans(self):
        s = self.only("nanum/NanumGothic-Bold.ttf")
        s["batch"]["options"]["export"] = {"ttf": 1, "pdf": True}
        errors = settings.validate(self.fonts, s, self.root)
        self.assertIn("batch: option export.ttf is not true or false", errors)
        self.assertIn("batch: unknown option key export.pdf", errors)

    def test_plan_has_export_steps_after_each_face(self):
        with tempfile.TemporaryDirectory() as jd:
            nan = self.fid("nanum/NanumGothic-Bold.ttf")
            s = self.only("nanum/NanumGothic-Bold.ttf", bpp=[1, 2], options={"export": {"ttf": True, "bdf": True}})
            self.assertEqual(settings.validate(self.fonts, s, self.root), [])
            steps = settings.plan_steps({"fonts": self.fonts, "settings": s}, jd, "/T", self.root)
            self.assertEqual([(st["kind"], st["bpp"], st["name"]) for st in steps],
                             [("precomposed", 1, "NANUM16.SVF"), ("export", 1, "NANUM16.ttf"), ("export", 1, "NANUM16.bdf"),
                              ("precomposed", 2, "NANUM16A.SVF"), ("export", 2, "NANUM16A.ttf"),
                              ("export", 2, "NANUM16A.bdf")])
            face, ttf, bdf = steps[0], steps[1], steps[2]
            self.assertEqual((ttf["needs"], ttf["format"], bdf["format"]), ([face["id"]], "ttf", "bdf"))
            self.assertEqual(ttf["output"], "work/%s/NANUM16.ttf" % ttf["id"])
            licence = os.path.join(jd, "work", nan, "licence", "OFL.txt")   # staged, not the input itself
            with open(os.path.join(self.root, "nanum", "OFL.txt"), "rb") as a, open(licence, "rb") as b:
                self.assertEqual(a.read(), b.read())
            self.assertEqual(ttf["argv"], [toolrun.tool("svf2ttf", "/T") + [
                "ttf", os.path.join(jd, face["output"]), os.path.join(jd, ttf["output"]), "--licence", licence]])
            self.assertEqual(bdf["argv"][0][3:6], ["bdf", os.path.join(jd, face["output"]), os.path.join(jd, bdf["output"])])
            self.assertNotIn("export_only", face)
            self.assertEqual(len({st["id"] for st in steps}), len(steps))
            self.assertTrue(all(st["font"] == nan for st in steps))

    def test_composite_reaches_a_jamo_sets_ttf_only(self):
        with tempfile.TemporaryDirectory() as jd:
            dos = self.fid("dos/HAN.FNT")
            s = self.only("dos/HAN.FNT", dos_layout="844", options={"export": {"ttf": True, "bdf": True, "composite": True}})
            self.assertEqual(settings.validate(self.fonts, s, self.root), [])
            steps = settings.plan_steps({"fonts": self.fonts, "settings": s}, jd, "/T", self.root)
            got = [(st["kind"], st.get("format"), st.get("composite"), "--composite" in st["argv"][0]) for st in steps]
            self.assertEqual(got, [("jamo", None, None, False), ("export", "ttf", True, True),
                                   ("export", "bdf", None, False)])
            s = self.only("nanum/NanumGothic-Bold.ttf", bpp=[1], options={"export": {"ttf": True, "composite": True}})
            steps = settings.plan_steps({"fonts": self.fonts, "settings": s}, jd, "/T", self.root)
            self.assertNotIn("--composite", steps[1]["argv"][0])           # a precomposed face: the plain TTF
        s = self.only("nanum/NanumGothic-Bold.ttf", options={"export": {"bdf": True, "composite": True}})
        self.assertIn("%s: composite is a TTF option: tick \"also write TTF\"" % self.fid("nanum/NanumGothic-Bold.ttf"),
                      settings.validate(self.fonts, s, self.root))

    def test_a_typed_licence_is_written_for_svf2ttf(self):
        with tempfile.TemporaryDirectory() as jd:
            nan = self.fid("nanum/NanumGothic-Bold.ttf")
            s = self.only("nanum/NanumGothic-Bold.ttf", bpp=[1], options={"export": {"ttf": True}},
                          licence={"kind": "text", "text": "Copyright X\n\nmy licence"})
            steps = settings.plan_steps({"fonts": self.fonts, "settings": s}, jd, "/T", self.root)
            path = os.path.join(jd, "work", nan, "licence", "licence.txt")
            self.assertEqual(steps[1]["argv"][0][-2:], ["--licence", path])
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "Copyright X\n\nmy licence")

    def test_a_per_font_export_overrides_the_batch(self):
        with tempfile.TemporaryDirectory() as jd:
            s = self.only("nanum/NanumGothic-Bold.ttf", bpp=[1], options={"export": {"bdf": False}})
            s["batch"]["options"]["export"] = {"ttf": True, "bdf": True}
            steps = settings.plan_steps({"fonts": self.fonts, "settings": s}, jd, "/T", self.root)
            self.assertEqual([st["name"] for st in steps], ["NANUM16.SVF", "NANUM16.ttf"])

    def test_svf2ttf_route(self):
        svf = "svf/NEODG16.SVF"
        s = self.only(svf, precomposed_route="svf2ttf")
        self.assertIn("%s: svf2ttf writes a TTF or a BDF only: tick \"also write TTF\" or \"also write BDF\""
                      % self.fid(svf), settings.validate(self.fonts, s, self.root))
        s = self.only(svf, precomposed_route="svf2ttf", options={"export": {"ttf": True}})
        self.assertEqual(settings.validate(self.fonts, s, self.root), [])
        with tempfile.TemporaryDirectory() as jd:
            steps = settings.plan_steps({"fonts": self.fonts, "settings": s}, jd, "/T", self.root)
            self.assertEqual([(st["kind"], st["name"], st.get("export_only")) for st in steps],
                             [("precomposed", "NEODG16.SVF", True), ("export", "NEODG16.ttf", None)])
            self.assertEqual(steps[0]["argv"], [])                # the v3 face is copied as it is
        eff = settings.effective(self.fonts, s, self.fid(svf))
        self.assertEqual(settings.written_names(next(f for f in self.fonts if f["path"] == svf), eff),
                         [("NEODG16.ttf", "export")])

    def test_route_labels_are_checked(self):
        svf = "svf/NEODG16.SVF"
        f = self.fid(svf)
        s = self.only(svf, precomposed_route="mkfont")
        self.assertIn("%s: precomposed_route mkfont is not offered" % f, settings.validate(self.fonts, s, self.root))
        s = self.only(svf, precomposed_route=3)
        self.assertIn("%s: precomposed_route 3 is not a route label" % f, settings.validate(self.fonts, s, self.root))

    def test_run_ready_refuses_an_existing_export_name(self):
        out = tempfile.mkdtemp(prefix="svf-export-out-")
        self.addCleanup(shutil.rmtree, out, True)
        os.makedirs(os.path.join(out, "dos"))
        with open(os.path.join(out, "dos", "NANUM16.ttf"), "wb") as f:
            f.write(b"someone else's")
        s = self.only("nanum/NanumGothic-Bold.ttf", bpp=[1], options={"export": {"ttf": True}})
        fid = self.fid("nanum/NanumGothic-Bold.ttf")
        errors = settings.run_ready(self.fonts, s, naming.RepoIndex(out), self.root)
        self.assertIn("%s: NANUM16.ttf already exists in svf/dos; choose another name" % fid, errors)
        self.assertEqual([e for e in settings.run_ready(self.fonts, s, naming.RepoIndex(out), self.root,
                                                        own_earlier={"dos/NANUM16.ttf"}) if "NANUM16.ttf" in e], [])


class ExportLicenceStagingTest(unittest.TestCase):
    """svf2ttf.py --licence follows the .TXT files a note names: the maker stages the licence and only the named files
    the batch holds (through Sources), as UTF-8, so a link out of the root or an unpicked file is never embedded."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="svf-export-lic-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        import inputfx
        self.a = os.path.join(self.tmp, "in", "a")
        os.makedirs(self.a)
        os.makedirs(os.path.join(self.tmp, "outside"))
        with open(os.path.join(self.a, "Munjo.ttf"), "wb") as f:
            f.write(inputfx.ttf("Munjo", (50, 0, 950, 800)))
        with open(os.path.join(self.a, "LICENSE.txt"), "wb") as f:      # CP949, naming three files
            f.write("문조 글꼴 Copyright 2026. See NOTICE.TXT, OTHER.TXT and FRIEND.TXT.\n".encode("cp949"))
        with open(os.path.join(self.tmp, "outside", "secret.txt"), "w") as f:
            f.write("SECRET outside the picked root\n")
        os.symlink(os.path.join(self.tmp, "outside", "secret.txt"), os.path.join(self.a, "NOTICE.TXT"))
        with open(os.path.join(self.a, "OTHER.TXT"), "w") as f:
            f.write("OTHER: beside the font, not picked\n")
        with open(os.path.join(self.a, "FRIEND.TXT"), "w") as f:
            f.write("FRIEND: picked too\n")

    def plan(self, roots, **over):
        from sources import Sources
        sources = Sources("local", roots)
        fonts = detect.scan(sources, local=True)
        s = settings.defaults(fonts, local=True)
        fid = next(f["id"] for f in fonts if f["path"] == "Munjo.ttf")
        lic = next(f for f in fonts if f["path"] == "LICENSE.txt")
        s["fonts"][fid].update(selected=True, bpp=[1], options={"export": {"ttf": True}},
                               licence={"kind": "upload", "path": "LICENSE.txt", "root": lic["root"]}, **over)
        jd = tempfile.mkdtemp(prefix="svf-export-lic-job-", dir=self.tmp)
        steps = settings.plan_steps({"fonts": fonts, "settings": s}, jd, os.path.join(REPO_DIR, "tools"), sources)
        argv = steps[1]["argv"][0]
        staged = argv[argv.index("--licence") + 1]
        return staged, sorted(os.listdir(os.path.dirname(staged)))

    def test_single_files_picked(self):
        staged, names = self.plan([os.path.join(self.a, n) for n in ("Munjo.ttf", "LICENSE.txt", "FRIEND.TXT")])
        self.assertEqual(names, ["FRIEND.TXT", "LICENSE.txt"])        # no link out of the root, no unpicked file
        with open(staged, encoding="utf-8") as f:
            self.assertIn("문조 글꼴 Copyright 2026", f.read())            # CP949 read as CP949: the Hangul kept
        out = os.path.join(self.tmp, "x.ttf")
        r = subprocess.run([sys.executable, "-P", os.path.join(REPO_DIR, "tools", "svf2ttf.py"), "ttf", NEODG16, out,
                            "--licence", staged], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr)
        from fontTools.ttLib import TTFont
        with TTFont(out) as font:
            desc = font["name"].getDebugName(13)
        self.assertIn("FRIEND: picked too", desc)
        self.assertIn("문조 글꼴", desc)
        self.assertNotIn("SECRET", desc)
        self.assertNotIn("beside the font, not picked", desc)

    def test_folder_picked(self):
        _staged, names = self.plan([self.a])
        self.assertEqual(names, ["FRIEND.TXT", "LICENSE.txt", "OTHER.TXT"])   # the link is still refused

    def export_only_plan(self, roots):
        from sources import Sources
        sources = Sources("local", roots)
        fonts = detect.scan(sources, local=True)
        s = settings.defaults(fonts, local=True)
        fid = next(f["id"] for f in fonts if f["path"] == "NEODG16.SVF")
        s["fonts"][fid].update(selected=True, licence=None, precomposed_route="svf2ttf", options={"export": {"ttf": True}})
        jd = tempfile.mkdtemp(prefix="svf-export-lic-job-", dir=self.tmp)
        import builtins
        from unittest import mock
        real_open, self.opened = builtins.open, []

        def spy(path, *args, **kwargs):                       # every file the plan opens
            self.opened.append(os.path.realpath(path) if isinstance(path, str) else path)
            return real_open(path, *args, **kwargs)
        with mock.patch("builtins.open", spy):
            steps = settings.plan_steps({"fonts": fonts, "settings": s}, jd, os.path.join(REPO_DIR, "tools"), sources)
        argv = steps[1]["argv"][0]
        staged = argv[argv.index("--licence") + 1] if "--licence" in argv else None
        return staged, (sorted(os.listdir(os.path.dirname(staged))) if staged else [])

    def test_export_only_discovery_opens_batch_files_only(self):
        """No licence chosen: the note found beside the SVF is one the batch holds. An unpicked note that sorts first and
        names the face, and a note that links out of the folder, are never opened (both unreadable here: opening one
        would fail the plan) and do not hide the picked note."""
        d = os.path.join(self.tmp, "svfin")
        os.makedirs(d)
        shutil.copyfile(NEODG16, os.path.join(d, "NEODG16.SVF"))
        title = "Neo faces (NEODG*.SVF)\n\nnote text; see OFL.TXT\n"
        for name in ("A_NOTE.TXT", "B_NOTE.TXT"):
            with open(os.path.join(d, name), "w") as f:
                f.write(title.replace("note text", name))
        shutil.copyfile(os.path.join(REPO_DIR, "svf", "dos", "OFL.TXT"), os.path.join(d, "OFL.TXT"))
        outside = os.path.join(self.tmp, "outside", "AA_LINK.txt")
        with open(outside, "w") as f:
            f.write(title)
        os.symlink(outside, os.path.join(d, "AA_LINK.TXT"))
        for path in (outside, os.path.join(d, "A_NOTE.TXT")):
            os.chmod(path, 0)
        self.addCleanup(os.chmod, outside, 0o644)
        self.addCleanup(os.chmod, os.path.join(d, "A_NOTE.TXT"), 0o644)
        staged, names = self.export_only_plan([os.path.join(d, n) for n in ("NEODG16.SVF", "B_NOTE.TXT", "OFL.TXT")])
        self.assertEqual((os.path.basename(staged), names), ("B_NOTE.TXT", ["B_NOTE.TXT", "OFL.TXT"]))
        never = {os.path.realpath(outside), os.path.realpath(os.path.join(d, "A_NOTE.TXT"))}
        self.assertEqual(never & set(self.opened), set())
        staged, names = self.export_only_plan([os.path.join(d, n) for n in ("NEODG16.SVF", "B_NOTE.TXT")])
        self.assertEqual(names, ["B_NOTE.TXT"])                   # OFL.TXT not picked: not followed
        staged, names = self.export_only_plan([os.path.join(d, "NEODG16.SVF")])
        self.assertIsNone(staged)                                 # nothing picked: svf2ttf says the source's applies
        f2 = os.path.join(self.tmp, "svfin2")                    # a folder pick: the link is in the folder, refused
        os.makedirs(f2)
        for name in ("NEODG16.SVF", "B_NOTE.TXT", "OFL.TXT"):
            shutil.copyfile(os.path.join(d, name), os.path.join(f2, name))
        os.symlink(outside, os.path.join(f2, "AA_LINK.TXT"))
        staged, names = self.export_only_plan([f2])
        self.assertEqual((os.path.basename(staged), names), ("B_NOTE.TXT", ["B_NOTE.TXT", "OFL.TXT"]))
        self.assertNotIn(os.path.realpath(outside), self.opened)

    def test_svf2ttf_route_takes_the_sources_note(self):
        """An SVF read only for its exports, no licence chosen: the note beside it (and the OFL it names), as svf2ttf.py
        would find them beside the source, staged through the batch."""
        d = os.path.join(self.tmp, "svfin")
        os.makedirs(d)
        for name in ("NEODG16.SVF", "NEODGM.TXT", "OFL.TXT"):
            shutil.copyfile(os.path.join(REPO_DIR, "svf", "dos", name), os.path.join(d, name))
        from sources import Sources
        sources = Sources("local", [d])
        fonts = detect.scan(sources, local=True)
        s = settings.defaults(fonts, local=True)
        fid = next(f["id"] for f in fonts if f["path"] == "NEODG16.SVF")
        s["fonts"][fid].update(selected=True, licence=None, precomposed_route="svf2ttf", options={"export": {"ttf": True}})
        jd = tempfile.mkdtemp(prefix="svf-export-lic-job-", dir=self.tmp)
        steps = settings.plan_steps({"fonts": fonts, "settings": s}, jd, os.path.join(REPO_DIR, "tools"), sources)
        argv = steps[1]["argv"][0]
        staged = argv[argv.index("--licence") + 1]
        self.assertEqual((os.path.basename(staged), sorted(os.listdir(os.path.dirname(staged)))),
                         ("NEODGM.TXT", ["NEODGM.TXT", "OFL.TXT"]))


class ExportFactsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-export-facts-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def svf2ttf(self, *args):
        out = subprocess.run([sys.executable, "-P", os.path.join(REPO_DIR, "tools", "svf2ttf.py")] + list(args),
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_ttf_and_bdf_of_a_precomposed_and_a_jamo_face(self):
        for face, glyphs in ((NEODG16, 2905), (NEODG16G, None)):
            for fmt in ("ttf", "bdf"):
                path = os.path.join(self.tmp, "x." + fmt)
                self.svf2ttf(fmt, face, path, "--licence", "none")
                facts = quality.export_facts(path, fmt, face)
                self.assertEqual((facts["format"], facts["bytes"]), (fmt, os.path.getsize(path)))
                if glyphs:
                    self.assertEqual(facts["glyphs"], glyphs)
                else:
                    self.assertGreater(facts["glyphs"], 11172)     # a jamo set exports every syllable it composes

    def test_a_composite_ttf_holds_the_pieces_too(self):
        path = os.path.join(self.tmp, "c.ttf")
        self.svf2ttf("ttf", NEODG16G, path, "--licence", "none", "--composite")
        with self.assertRaisesRegex(ValueError, "glyphs for"):
            quality.export_facts(path, "ttf", NEODG16G)                   # more glyphs than characters
        self.assertGreater(quality.export_facts(path, "ttf", NEODG16G, composite=True)["glyphs"], 11172)

    def test_a_file_that_misses_a_glyph_is_refused(self):
        path = os.path.join(self.tmp, "x.bdf")
        self.svf2ttf("bdf", NEODG16, path, "--licence", "none")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        start = text.index("STARTCHAR uniAC00")
        end = text.index("ENDCHAR", start) + len("ENDCHAR\n")
        cut = text[:start] + text[end:]
        with open(path, "w", encoding="utf-8") as f:
            f.write(cut)
        with self.assertRaisesRegex(ValueError, "CHARS"):
            quality.export_facts(path, "bdf", NEODG16)
        with open(path, "w", encoding="utf-8") as f:
            f.write(cut.replace("CHARS 2905", "CHARS 2904"))
        with self.assertRaisesRegex(ValueError, "1 missing"):
            quality.export_facts(path, "bdf", NEODG16)
        ttf = os.path.join(self.tmp, "x.ttf")
        self.svf2ttf("ttf", NEODG16G, ttf, "--licence", "none")
        with self.assertRaisesRegex(ValueError, "missing"):
            quality.export_facts(ttf, "ttf", NEODG16)                # another face's TTF
        with open(ttf, "wb") as f:
            f.write(b"not a font")
        with self.assertRaises(Exception):
            quality.export_facts(ttf, "ttf", NEODG16)


class ExportLocalJobTest(LocalRunBase):
    """A local job writes the exports beside the faces, reads them back and lists them in BUILD.md (no rows)."""

    def test_ttf_and_bdf_beside_the_faces(self):
        def edit(st):
            st["batch"]["options"]["export"] = {"ttf": True, "bdf": True, "composite": True}
        jid, job = self.done_job(edit)
        files = sorted(job["result"]["files"])
        self.assertEqual(files, sorted(walk_rel(self.out, skip_prefix=".svf-maker-")))
        faces = [f for f in files if f.endswith(".SVF")]
        self.assertEqual(len(faces), 2)
        for face in faces:
            stem = face[:-len(".SVF")]
            self.assertIn(stem + ".ttf", files)
            self.assertIn(stem + ".bdf", files)
        exports = [s for s in job["steps"] if s["kind"] == "export"]
        self.assertEqual(len(exports), 4)
        for step in exports:
            self.assertEqual(step["state"], "done", step.get("error"))
            self.assertEqual(step["facts"]["format"], step["format"])
            self.assertGreater(step["facts"]["glyphs"], 0)
            self.assertTrue(step["written"].endswith(step["name"]))
        self.assertEqual(sorted(s["kind"] for s in job["steps"] if s.get("composite")), ["export"])   # the jamo set's TTF
        build = self.read_out("build-%s/BUILD.md" % jid).decode("utf-8")
        self.assertIn("python3 -P tools/svf2ttf.py ttf", build)
        self.assertRegex(build, r"svf2ttf\.py ttf \S+HAN16J\.SVF \S+ --composite\n")
        self.assertRegex(build, r"svf2ttf\.py ttf \S+ \S+ --licence \S+/licence/OFL\.txt\n")   # the TTF font's own, staged
        for f in files:
            if f.endswith((".ttf", ".bdf")):
                self.assertIn("- written: %s" % f, build)
        for lines in ("LICENCES.tsv.lines", "FAMILIES.tsv.lines", "FACES.TSV.lines"):
            text = self.read_out("build-%s/%s" % (jid, lines)).decode("utf-8")
            self.assertNotIn(".ttf", text)
            self.assertNotIn(".bdf", text)
        for note in (f for f in files if f.endswith(".TXT") and b"faces (" in self.read_out(f)):
            self.assertNotIn(b"svf2ttf", self.read_out(note))       # the note is the faces' provenance
        # the DOS font has no licence: svf2ttf says the source font's licence applies
        from fontTools.ttLib import TTFont
        dos_ttf = next(f for f in files if f.startswith("svf/jamo-extra/") and f.endswith(".ttf"))
        with TTFont(os.path.join(self.out, dos_ttf)) as font:
            self.assertIn("the licence of the font it was made from applies", font["name"].getDebugName(13))
        ttf_ttf = next(f for f in files if f.startswith("svf/dos/") and f.endswith(".ttf"))
        with TTFont(os.path.join(self.out, ttf_ttf)) as font:
            self.assertIn("SIL Open Font License", font["name"].getDebugName(13))

    def test_an_export_name_someone_else_holds_is_refused_before_the_run(self):
        jid = self.local_job()

        def edit(st):
            st["batch"]["options"]["export"] = {"ttf": True}
        self.select(jid, edit)
        name = next(n for n in self.job(jid)["effective_names"][self.ttf].values())
        os.makedirs(os.path.join(self.out, "svf", "dos"))
        with open(os.path.join(self.out, "svf", "dos", routes.export_name(name, "ttf")), "wb") as f:
            f.write(b"mine")
        status, body = self.api("POST", "/api/jobs/%s/run" % jid)
        self.assertEqual(status, 400, body)
        self.assertIn("%s already exists in svf/dos" % routes.export_name(name, "ttf"), str(body))

    def test_a_failed_face_fails_its_exports(self):
        jid = self.local_job()

        def edit(st):
            st["batch"]["options"]["export"] = {"ttf": True}
        self.select(jid, edit)
        job = self.srv.store.load(jid)
        import jobs as jobsmod
        real = jobsmod.run_command

        def failing(argv, cwd, timeout, cancel, env=None):
            if any("mkfont" in str(token) for token in argv[:3]):
                return {"exit": 1, "stdout": "", "stderr": "", "seconds": 0.0, "error": None}
            return real(argv, cwd, timeout, cancel, env)
        from unittest import mock
        with mock.patch.object(jobsmod, "run_command", failing):
            job = self.run_to_done(jid)
        exports = {s["needs"][0]: s for s in job["steps"] if s["kind"] == "export"}
        for step in job["steps"]:
            if step["id"] in exports and step["state"] == "failed":
                self.assertEqual(exports[step["id"]]["error"], "face step failed")
        self.assertTrue(any(s["state"] == "failed" for s in exports.values()))


class SvfToTtfLocalJobTest(LocalBase):
    """The `svf2ttf` route: an SVF the user picks becomes a TTF and a BDF only (no SVF, no note, no rows)."""

    def test_an_svf_to_ttf_only(self):
        src = os.path.join(self.tmp, "svfin")
        os.makedirs(src)
        shutil.copyfile(NEODG16, os.path.join(src, "NEODG16.SVF"))
        jid = self.local_job(roots=[src])
        job = self.job(jid)
        st = job["settings"]
        fid = next(f["id"] for f in job["fonts"] if f["path"] == "NEODG16.SVF")
        self.assertEqual(next(f for f in job["fonts"] if f["id"] == fid)["source_kind"], "svf-precomposed")
        st["fonts"][fid].update(selected=True, precomposed_route="svf2ttf",
                                options={"export": {"ttf": True, "bdf": True}})
        status, body = self.api("PUT", "/api/jobs/%s/settings" % jid, st)
        self.assertEqual(status, 200, body)
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        files = sorted(job["result"]["files"])
        self.assertEqual([f for f in files if f.startswith("svf/")], ["svf/dos/NEODG16.bdf", "svf/dos/NEODG16.ttf"])
        self.assertEqual(sorted(walk_rel(self.out, skip_prefix=".svf-maker-")), files)
        self.assertEqual(self.read_lines(jid, "LICENCES.tsv.lines"), "")
        face = next(s for s in job["steps"] if s["kind"] == "precomposed")
        self.assertTrue(face["export_only"])
        self.assertNotIn("written", face)
        ttf = next(s for s in job["steps"] if s.get("format") == "ttf")
        self.assertEqual(ttf["facts"]["glyphs"], 2905)

    def svf_job(self, note_in_out=False):
        src = os.path.join(self.tmp, "svfin")
        os.makedirs(src, exist_ok=True)
        shutil.copyfile(NEODG16, os.path.join(src, "NEODG16.SVF"))
        jid = self.local_job(roots=[src])
        job = self.job(jid)
        st = job["settings"]
        fid = next(f["id"] for f in job["fonts"] if f["path"] == "NEODG16.SVF")
        st["fonts"][fid].update(selected=True, precomposed_route="svf2ttf", options={"export": {"ttf": True}})
        status, body = self.api("PUT", "/api/jobs/%s/settings" % jid, st)
        self.assertEqual(status, 200, body)
        return jid, st["fonts"][fid]

    def test_failed_exports_fail_an_export_only_job(self):
        jid, _per = self.svf_job()
        import jobs as jobsmod
        real = jobsmod.run_command

        def failing(argv, cwd, timeout, cancel, env=None):
            if any("svf2ttf" in str(token) for token in argv[:3]):
                return {"exit": 1, "stdout": "", "stderr": "", "seconds": 0.0, "error": None}
            return real(argv, cwd, timeout, cancel, env)
        from unittest import mock
        with mock.patch.object(jobsmod, "run_command", failing):
            job = self.run_to_done(jid)
        self.assertEqual((job["state"], job["error"]), ("failed", "no successful step"))
        self.assertEqual([s["state"] for s in job["steps"]], ["done", "failed"])     # the copy, the export

    def test_note_and_licence_names_do_not_block_exports_only(self):
        """svf2ttf writes no note or licence text: names of those already in svf/<dest>/ do not refuse the run."""
        jid, per = self.svf_job()
        os.makedirs(os.path.join(self.out, "svf", "dos"))
        for name in (per["note_name"] or "NEODG.TXT", per["licence_name"] or "OFLNEODG.TXT"):
            with open(os.path.join(self.out, "svf", "dos", name), "w") as f:
                f.write("someone else's\n")
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        self.assertIsNone(next(s for s in job["steps"] if s["kind"] == "precomposed")["layout"])

    def read_lines(self, jid, name):
        with open(os.path.join(self.out, "build-%s" % jid, name), encoding="utf-8") as f:
            return f.read()


if __name__ == "__main__":
    unittest.main()
