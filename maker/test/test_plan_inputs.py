#!/usr/bin/env python3
"""Planning and end-to-end runs of the maker's new input kinds (t_f3ef3189): the `source` step, TTC faces, Mac cmap
fonts and containers, variable-font instances, KSC and johab PCF, the johab844 route, 12x24 English companions.

  python3 -m unittest discover -s maker/test -p 'test_plan_inputs.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import glob
import gzip
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest import mock

import detect
import fixtures
import inputfx
import inputkinds
import jamoset
import localfx
import mkfont
import routes
import settings
import toolrun
import zipout
from inputkinds import fid_of, select

BOX1 = (50, 0, 950, 800)
BOX2 = (300, 0, 700, 400)


def ga(zip_path):
    """The rows of U+AC00 in the zip's face."""
    return inputkinds.zip_face(zip_path).glyphs[0xAC00]


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="plan-inputs-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.n = 0

    def run_batch(self, files, choose):
        self.n += 1
        return inputkinds.run_batch(self, os.path.join(self.tmp, "j%d" % self.n), files, choose)

    def plan(self, files, **per):
        """The planned steps of the one font in @p files (a dict, or the bytes of one TTF) selected with @p per; the
        job directory is left in self.job_dir."""
        self.n += 1
        if isinstance(files, bytes):
            files = {"d/d.ttf": files}
        store, job = inputkinds.plan_batch(self, os.path.join(self.tmp, "j%d" % self.n), files,
                                           lambda f, st: select(st, inputkinds.only_font(f), **per))
        self.job_dir = store.path(job["id"])
        return job["steps"]


class SourceCommandsTest(unittest.TestCase):
    def test_ops_chain_through_numbered_files(self):
        argvs, out = routes.source_commands([{"op": "rsrc-sfnt", "id": 128}, {"op": "mac-cmap"}], "/u/F.dfont", "/w", "/T")
        self.assertEqual(argvs, [toolrun.tool("macsfnt", "/T") + ["extract", "/u/F.dfont", "/w/source-1.ttf", "--id", "128"],
                                 toolrun.tool("macsfnt", "/T") + ["unicode", "/w/source-1.ttf", "/w/source.ttf"]])
        self.assertEqual(out, "/w/source.ttf")

    def test_instance_pins_every_axis(self):
        argvs, _ = routes.source_commands([{"op": "instance", "coords": {"wght": 700, "wdth": 87.5}}], "/u/V.ttf", "/w", "/T")
        self.assertEqual(argvs[0][2:], ["-m", "fontTools.varLib.instancer", "/u/V.ttf", "wdth=87.5", "wght=700", "-o",
                                        "/w/source.ttf"])

    def test_ttc_face_uses_srcprep(self):
        argvs, out = routes.source_commands([{"op": "ttc-face", "index": 1}], "/u/t.ttc", "/w", "/T")
        self.assertEqual(argvs, [toolrun.maker_script("srcprep") + ["ttc-face", "/u/t.ttc", "/w/source.ttf", "--index", "1"]])

    def test_instance_values_are_not_rounded(self):
        argvs, _ = routes.source_commands([{"op": "instance", "coords": {"XHGT": 123456.7, "wght": 899.99999}}],
                                          "/u/V.ttf", "/w", "/T")
        self.assertEqual(argvs[0][5:7], ["XHGT=123456.7", "wght=899.99999"])

    def test_a_cff_face_is_saved_as_otf(self):
        argvs, out = routes.source_commands([{"op": "ttc-face", "index": 1}], "/u/c.otc", "/w", "/T", "otf")
        self.assertEqual(out, "/w/source.otf")

    def test_pcf_bdf_writes_a_bdf(self):
        argvs, out = routes.source_commands([{"op": "pcf-bdf"}], "/u/k.pcf.gz", "/w", "/T")
        self.assertEqual(argvs, [toolrun.maker_script("srcprep") + ["pcf-bdf", "/u/k.pcf.gz", "/w/source.bdf"]])
        self.assertEqual(out, "/w/source.bdf")

    def test_no_ops_no_argv(self):
        self.assertEqual(routes.source_commands([], "/u/a.ttf", "/w", "/T"), ([], "/u/a.ttf"))


def _two():
    return inputfx.ttc([inputfx.ttf("One", BOX1), inputfx.ttf("Two", BOX2)])


class SourceStepE2ETest(Case):
    def face_1(self, fonts, s):
        select(s, fid_of(fonts, face=1))

    def test_ttc_face_1_converts(self):
        job, z = self.run_batch({"t/two.ttc": _two()}, self.face_1)
        self.assertEqual(inputkinds.step_tools(job["steps"]), [["srcprep.py ttc-face"], ["mkfont.py"]])
        self.assertEqual([st["state"] for st in job["steps"]], ["done", "done"])
        inputkinds.assert_facecheck(self, z)
        _, alone = self.run_batch({"a/two.ttf": inputfx.ttf("Two", BOX2)}, lambda f, s: select(s, inputkinds.only_font(f)))
        self.assertEqual(ga(z), ga(alone))                          # face 1's 가, not face 0's
        _, one = self.run_batch({"b/one.ttf": inputfx.ttf("One", BOX1)}, lambda f, s: select(s, inputkinds.only_font(f)))
        self.assertNotEqual(ga(z), ga(one))

    def test_ttc_face_0_with_a_mac_cmap_converts(self):
        job, z = self.run_batch({"t/m.ttc": inputfx.ttc([inputfx.mac_cmap_ttf(), inputfx.ttf("Two", BOX2)])},
                                lambda f, s: select(s, fid_of(f, face=0, path="t/m.ttc")))
        self.assertEqual(inputkinds.step_tools(job["steps"]),
                         [["srcprep.py ttc-face", "macsfnt.py unicode"], ["mkfont.py"]])
        inputkinds.assert_facecheck(self, z)
        self.assertTrue(any(ga(z)))

    def test_a_gz_ttc_face_1_converts(self):
        job, z = self.run_batch({"t/two.ttc.gz": gzip.compress(_two())}, self.face_1)
        self.assertEqual(inputkinds.step_tools(job["steps"]), [["srcprep.py ttc-face"], ["mkfont.py"]])
        self.assertEqual([st["state"] for st in job["steps"]], ["done", "done"])
        inputkinds.assert_facecheck(self, z)

    def test_otc_cff_face_1_converts(self):
        job, z = self.run_batch({"t/c.otc": inputfx.ttc([inputfx.ttf("One", BOX1), inputfx.otf("Cff", BOX2)])},
                                self.face_1)
        self.assertEqual(inputkinds.step_tools(job["steps"]), [["srcprep.py ttc-face"], ["mkfont.py"]])
        self.assertEqual([st["state"] for st in job["steps"]], ["done", "done"])
        self.assertTrue(job["steps"][0]["output"].endswith("/source.otf"))
        inputkinds.assert_facecheck(self, z)

    def test_mac_cmap_ttf_converts(self):
        job, z = self.run_batch({"m/Mac.ttf": inputfx.mac_cmap_ttf()}, lambda f, s: select(s, inputkinds.only_font(f)))
        self.assertEqual(inputkinds.step_tools(job["steps"]), [["macsfnt.py unicode"], ["mkfont.py"]])
        inputkinds.assert_facecheck(self, z)
        self.assertTrue(any(ga(z)))

    def test_each_mac_container_converts(self):
        fk = inputfx.fork([(b"sfnt", 128, "Synth", inputfx.mac_cmap_ttf())])
        for name, blob in (("F.dfont", fk), ("._F", inputfx.appledouble(fk)), ("F.bin", inputfx.macbinary(fk))):
            with self.subTest(wrapper=name):
                job, z = self.run_batch({"m/" + name: blob}, lambda f, s: select(s, inputkinds.only_font(f)))
                self.assertEqual(inputkinds.step_tools(job["steps"]),
                                 [["macsfnt.py extract", "macsfnt.py unicode"], ["mkfont.py"]])
                self.assertEqual([st["state"] for st in job["steps"]], ["done", "done"])
                inputkinds.assert_facecheck(self, z)
                self.assertTrue(any(ga(z)))

    def test_composite_face_1_runs_its_master_on_the_source(self):
        comp = fixtures._composite_ttf(os.path.join(self.tmp, "Composite.ttf"))
        with open(comp, "rb") as fh:
            comp_bytes = fh.read()
        job, z = self.run_batch({"t/two.ttc": inputfx.ttc([inputfx.ttf("One", BOX1), comp_bytes])},
                                lambda f, s: select(s, fid_of(f, face=1), kinds=["jamo"], layout="844",
                                                    experimental=False))
        self.assertEqual([st["kind"] for st in job["steps"]], ["source", "prepare", "jamo"])
        self.assertTrue(any(a.endswith("/source.ttf") for a in job["steps"][1]["argv"][0]))
        self.assertEqual([st["state"] for st in job["steps"]], ["done", "done", "done"])
        self.assertEqual(job["steps"][2]["quality"]["compared"], 66)     # the converted face 1; the raw TTC gives 1

    def test_a_failed_source_step_fails_the_font(self):
        self.n += 1
        tmp = os.path.join(self.tmp, "j%d" % self.n)

        def corrupt_after_detection(fonts, s):
            select(s, fid_of(fonts, face=1, path="t/two.ttc"))
            select(s, fid_of(fonts, path="m/Mac.ttf"))
            for root, _d, names in os.walk(tmp):
                for name in names:
                    if name == "two.ttc":
                        path = os.path.join(root, name)
                        with open(path, "rb") as fh:
                            data = fh.read()
                        with open(path, "wb") as fh:
                            fh.write(data[:40])
        job, z = inputkinds.run_batch(self, tmp, {"t/two.ttc": _two(), "m/Mac.ttf": inputfx.mac_cmap_ttf()},
                                      corrupt_after_detection)
        by_font = {}
        for st in job["steps"]:
            by_font.setdefault(st["font"], []).append(st)
        broken = [sts for sts in by_font.values() if sts[0]["state"] == "failed"]
        fine = [sts for sts in by_font.values() if sts[0]["state"] == "done"]
        self.assertEqual((len(broken), len(fine)), (1, 1))
        self.assertEqual([st["state"] for st in broken[0]], ["failed", "failed"])
        self.assertEqual(broken[0][1]["error"], "source failed")
        self.assertEqual([st["state"] for st in fine[0]], ["done", "done"])      # the other font is untouched
        self.assertEqual(job["state"], "done")


class StrikeRouteTest(Case):
    def test_bitmap_only_sfnt_plans_mkfont_at_its_strikes(self):

        def choose(fonts, s):
            select(s, inputkinds.only_font(fonts), sizes=[12])
        import jobs
        tmp = os.path.join(self.tmp, "strike")
        store = jobs.Store(tmp)
        job = store.create()
        upload = os.path.join(store.path(job["id"]), "upload")
        with open(os.path.join(upload, "B.ttf"), "wb") as fh:
            fh.write(inputfx.bitmap_only_ttf((12, 16)))
        with open(os.path.join(upload, "LICENSE.txt"), "w") as fh:
            fh.write(inputkinds.LICENCE)
        fonts = detect.scan(upload)
        st = settings.defaults(fonts)
        choose(fonts, st)
        job.update(fonts=fonts, settings=st)
        steps = settings.plan_steps(job, store.path(job["id"]), inputkinds.TOOLS, upload)
        self.assertEqual(inputkinds.step_tools(steps), [["mkfont.py"]])
        argv = steps[0]["argv"][0]
        self.assertEqual((argv[argv.index("--size") + 1], argv[argv.index("--bpp") + 1]), ("12", "1"))


class InstanceSettingsTest(Case):
    def scan(self, data, name="Vary.ttf"):
        d = os.path.join(self.tmp, "scan%d" % self.n)
        self.n += 1
        os.makedirs(d)
        for rel, blob in ((name, data), ("LICENSE.txt", inputkinds.LICENCE.encode())):
            with open(os.path.join(d, rel), "wb") as fh:
                fh.write(blob)
        return detect.scan(d)

    def font_id(self, fonts):
        return inputkinds.only_font(fonts)

    def test_instance_rules(self):
        fonts = self.scan(inputfx.variable_ttf())
        s = settings.defaults(fonts)
        fid = self.font_id(fonts)
        for value, msg in (({"wght": 950}, "%s: instance wght=950 is outside 100..900" % fid),
                           ({"opsz": 12}, "%s: instance axis opsz is not in the font" % fid),
                           ("Bold", "%s: instance is not an object of axis values" % fid),
                           ({"wght": True}, "%s: instance is not an object of axis values" % fid)):
            s["fonts"][fid].update(selected=True, instance=value)
            self.assertIn(msg, settings.validate(fonts, s))
        s["fonts"][fid]["instance"] = {"wght": 700}
        self.assertEqual(settings.validate(fonts, s), [])

    def test_instance_on_a_static_font_is_refused(self):
        fonts = self.scan(inputfx.ttf("S", BOX1), "S.ttf")
        s = settings.defaults(fonts)
        fid = self.font_id(fonts)
        s["fonts"][fid].update(selected=True, instance={"wght": 400})
        self.assertIn("%s: instance needs a variable font" % fid, settings.validate(fonts, s))

    def test_defaults_carry_instance_none(self):
        fonts = self.scan(inputfx.variable_ttf())
        self.assertIsNone(settings.defaults(fonts)["fonts"][self.font_id(fonts)]["instance"])
        self.assertIn("instance", settings.FONT_ONLY_KEYS)

    def test_instance_coords_overlay_the_axis_defaults(self):
        font = {"variable": {"axes": [{"tag": "wght", "min": 100, "default": 400, "max": 900},
                                      {"tag": "wdth", "min": 75, "default": 100, "max": 100}]}}
        self.assertEqual(settings.instance_coords(font, {"wght": 700}), {"wght": 700, "wdth": 100})


class InstanceE2ETest(Case):
    def test_bold_instance_differs_from_the_default(self):
        files = {"v/Vary.ttf": inputfx.variable_ttf()}
        reg, z1 = self.run_batch(files, lambda f, s: select(s, inputkinds.only_font(f), sizes=[24], bpp=[1]))
        bold, z2 = self.run_batch(files, lambda f, s: select(s, inputkinds.only_font(f), sizes=[24], bpp=[1],
                                                             instance={"wght": 700}))
        self.assertEqual(inputkinds.step_tools(reg["steps"]), [["mkfont.py"]])
        self.assertEqual(inputkinds.step_tools(bold["steps"]), [["-m fontTools.varLib.instancer"], ["mkfont.py"]])
        self.assertEqual([st["state"] for st in bold["steps"]], ["done", "done"])
        inputkinds.assert_facecheck(self, z2)
        self.assertNotEqual(ga(z1), ga(z2))


PCF_JOHAB = [(code, rows, 16) for code, _w, _h, _x, _y, rows in fixtures._johab_glyphs()]


class PcfE2ETest(Case):
    def latin(self):
        path = inputfx.latin_bdf_from_neodg(os.path.join(self.tmp, "latin.bdf"))
        with open(path, "rb") as fh:
            return fh.read()

    def files(self, name):
        pcf = inputfx.pcf(inputfx.ksc_glyphs_from_neodg(limit=10), "KSC5601.1987", "0", 16, 14, 2)
        return {"k/" + name: gzip.compress(pcf) if name.endswith(".gz") else pcf, "k/latin.bdf": self.latin(),
                "k/chars.txt": "가각간\n".encode()}

    def check(self, name):
        job, z = self.run_batch(self.files(name), lambda f, s: select(
            s, fid_of(f, kind="bdf-ksc5601"), range="k/chars.txt"))
        self.assertEqual(inputkinds.step_tools(job["steps"]), [["srcprep.py pcf-bdf"], ["bdfface.py"]])
        self.assertEqual([st["state"] for st in job["steps"]], ["done", "done"])
        inputkinds.assert_facecheck(self, z)
        self.assertEqual(sorted(cp for cp in inputkinds.zip_face(z).glyphs if cp >= 0xAC00), [0xAC00, 0xAC01, 0xAC04])

    def test_ksc_pcf_precomposed(self):
        self.check("ksc.pcf")

    def test_a_gz_ksc_pcf_converts(self):
        self.check("ksc.pcf.gz")

    def test_johab_pcf_jamo(self):
        job, z = self.run_batch({"j/johab.pcf": inputfx.pcf(PCF_JOHAB, "johab", "1", 16, 13, 3)},
                                lambda f, s: select(s, fid_of(f, kind="bdf-johab")))
        self.assertEqual(inputkinds.step_tools(job["steps"]), [["srcprep.py pcf-bdf"], ["jamoset.py"]])
        argv = job["steps"][1]["argv"][0]
        self.assertEqual(argv[argv.index("--layout") + 1], "hanterm-johab")
        self.assertIn(True, [a.endswith("/source.bdf") for a in argv])
        self.assertEqual([st["state"] for st in job["steps"]], ["done", "done"])
        inputkinds.assert_facecheck(self, z)


FONT_KSC = {"source_kind": "bdf-ksc5601", "face_index": 0, "sizes": [16], "bdf": {"box": [16, 16]}}
PATHS = {"tools": "/T", "src": "/u/k.bdf", "out": "/w/OUT.SVF", "work": "/w", "eng": None, "latin": "/u/l.bdf",
         "master": None, "range_file": "/w/range.txt"}


class KscJamoTest(Case):
    def test_route_and_argv(self):
        self.assertEqual([r.label for r in routes.routes(FONT_KSC)], ["bdfface", "bdfface + from-svf fit"])
        argvs = routes.route_for(FONT_KSC, "jamo", True).commands(FONT_KSC, 24, 1, "844", ("file", "/u/c.txt"),
                                                                  PATHS, [])
        self.assertEqual([a[2].rsplit("/", 1)[1] for a in argvs], ["bdfface.py", "jamoset.py"])
        self.assertEqual(argvs[1][argvs[1].index("--from-svf") + 1], "/w/precomposed.svf")
        self.assertEqual(argvs[0][argvs[0].index("-o") + 1], "/w/precomposed.svf")
        self.assertEqual(argvs[1][-2:], ["-o", "/w/OUT.SVF"])
        self.assertIsNone(routes.route_for(FONT_KSC, "jamo", False))
        self.assertEqual(routes.route_for(FONT_KSC, "precomposed", False).label, "bdfface")

    def test_extra_flags_reach_the_jamoset_command_only(self):
        argvs = routes.route_for(FONT_KSC, "jamo", True).commands(FONT_KSC, 16, 1, "844", ("file", "/u/c.txt"),
                                                                  PATHS, [[], ["--jset-version", "2"]])
        self.assertNotIn("--jset-version", argvs[0])
        self.assertIn("--jset-version", argvs[1])

    def test_ksc_bdf_jamo_set_end_to_end(self):
        bdf = os.path.join(self.tmp, "ksc.bdf")
        fixtures._bdf(bdf, [(gl, 16, 16, 0, -2, rows) for gl, rows, _w in inputfx.ksc_glyphs_from_neodg()],
                      16, 14, 2, "KSC5601.1987", (16, 16))
        with open(bdf, "rb") as fh:
            ksc = fh.read()
        latin = inputfx.latin_bdf_from_neodg(os.path.join(self.tmp, "latin.bdf"))
        with open(latin, "rb") as fh:
            latin_data = fh.read()
        job, z = self.run_batch({"k/ksc.bdf": ksc, "k/latin.bdf": latin_data},
                                lambda f, s: select(s, fid_of(f, kind="bdf-ksc5601"), kinds=["jamo"],
                                                    experimental=True, layout="844", range="2350"))
        self.assertEqual(inputkinds.step_tools(job["steps"]), [["bdfface.py", "jamoset.py"]])
        self.assertEqual([st["state"] for st in job["steps"]], ["done"])
        inputkinds.assert_facecheck(self, z)
        self.assertIsNotNone(inputkinds.zip_face(z).jset)


FONT_DOS = {"source_kind": "dos-raw", "face_index": 0, "sizes": [16], "dos": {"candidates": ["844"]}}


class Johab844Test(Case):
    def put_dos(self, folder, eng=None, eng_name="ASCII.PFT"):
        raw = os.path.join(self.tmp, "HAN.FNT")
        fixtures._dos_raw(raw)
        with open(raw, "rb") as fh:
            files = {folder + "/HAN.FNT": fh.read()}
        if eng is not None:
            files[folder + "/" + eng_name] = eng
        return files

    def test_offered_only_for_11520_bytes(self):
        self.assertEqual([r.label for r in routes.routes(dict(FONT_DOS, dos_bytes=11520))], ["johab844", "dos raw"])
        self.assertEqual([r.label for r in routes.routes(dict(FONT_DOS, dos_bytes=25920))], ["dos raw"])
        self.assertEqual([r.label for r in routes.routes(FONT_DOS)], ["dos raw"])

    def test_layout_and_eng_rules(self):
        d = os.path.join(self.tmp, "d")
        os.makedirs(d)
        for name, data in self.put_dos("", inputfx.pft_eng()).items():
            with open(os.path.join(d, name.lstrip("/")), "wb") as fh:
                fh.write(data)
        with open(os.path.join(d, "LICENSE.txt"), "w") as fh:
            fh.write(inputkinds.LICENCE)
        fonts = detect.scan(d)
        fid = fid_of(fonts, kind="dos-raw")
        s = settings.defaults(fonts)
        s["fonts"][fid].update(selected=True, kinds=["precomposed"], dos_layout="844-ihnm", bpp=[1])
        self.assertIn("%s: johab844 needs layout 844" % fid, settings.validate(fonts, s))
        s["fonts"][fid]["dos_layout"] = "844"
        errors = settings.validate(fonts, s)
        self.assertIn("%s: johab844 takes an 8x16 English font" % fid, errors)
        self.assertNotIn("%s: a 12x24 English font needs a face of 24 px or more" % fid, errors)   # no double message

    def test_johab844_end_to_end(self):
        import johab844
        eng = os.path.join(self.tmp, "ENG.FNT")
        fixtures._eng(eng)
        with open(eng, "rb") as fh:
            eng_data = fh.read()
        files = self.put_dos("h", eng_data, "ENG.FNT")
        job, z = self.run_batch(files, lambda f, s: select(s, fid_of(f, kind="dos-raw"), kinds=["precomposed"],
                                                           dos_layout="844"))
        self.assertEqual(inputkinds.step_tools(job["steps"]), [["johab844.py"]])
        argv = job["steps"][0]["argv"][0]
        self.assertTrue(argv[4].endswith("svf/dos/NEODG16.SVF"))
        self.assertIn("--eng", argv)
        self.assertEqual([st["state"] for st in job["steps"]], ["done"])
        inputkinds.assert_facecheck(self, z)
        raw = files["h/HAN.FNT"]
        self.assertEqual(bytes(inputkinds.zip_face(z).glyphs[0xAC00]), johab844.compose(raw, 0xAC00))
        import zipfile
        with zipfile.ZipFile(z) as zf:
            notes = [zf.read(n).decode() for n in zf.namelist() if n.lower().endswith(".txt") and "LIC" not in n.upper()]
        self.assertTrue(any("svf/dos/NEODG16.SVF" in n and "range is ignored" in n and "ENG.FNT" in n for n in notes), notes)


class Eng12x24Test(Case):
    def scan_dos(self, raw, eng):
        d = os.path.join(self.tmp, "dos%d" % self.n)
        self.n += 1
        os.makedirs(d)
        for name, data in (("HAN.FNT", raw), ("ASCII.PFT", eng), ("LICENSE.txt", inputkinds.LICENCE.encode())):
            with open(os.path.join(d, name), "wb") as fh:
                fh.write(data)
        return detect.scan(d)

    def test_a_16px_face_refuses_a_12x24_eng(self):
        raw = os.path.join(self.tmp, "r.fnt")
        fixtures._dos_raw(raw)
        with open(raw, "rb") as fh:
            fonts = self.scan_dos(fh.read(), inputfx.pft_eng())
        fid = fid_of(fonts, kind="dos-raw")
        s = settings.defaults(fonts)
        s["fonts"][fid].update(selected=True, dos_layout="844")
        self.assertIn("%s: a 12x24 English font needs a face of 24 px or more" % fid, settings.validate(fonts, s))

    def test_the_default_companion_is_the_8x16_one_for_a_16px_face(self):
        raw = os.path.join(self.tmp, "r.fnt")
        fixtures._dos_raw(raw)
        eng = os.path.join(self.tmp, "e.fnt")
        fixtures._eng(eng)
        d = os.path.join(self.tmp, "both")
        os.makedirs(d)
        for name, path in (("HAN.FNT", raw), ("ENG.FNT", eng)):
            shutil.copyfile(path, os.path.join(d, name))
        with open(os.path.join(d, "ASCII.PFT"), "wb") as fh:                # sorts before ENG.FNT
            fh.write(inputfx.pft_eng())
        with open(os.path.join(d, "LICENSE.txt"), "w") as fh:
            fh.write(inputkinds.LICENCE)
        fonts = detect.scan(d)
        fid = fid_of(fonts, kind="dos-raw")
        s = settings.defaults(fonts)
        self.assertEqual(s["fonts"][fid]["latin_companion"], fid_of(fonts, path="ENG.FNT"))
        s["fonts"][fid].update(selected=True, dos_layout="844")
        self.assertEqual(settings.validate(fonts, s), [])

    def test_pft_and_hbios_eng_on_a_24px_face(self):
        for name, eng in (("pft", inputfx.pft_eng()), ("hbios", inputfx.hbios_eng())):
            with self.subTest(companion=name):
                files = {"d/HAN24.FNT": inputfx.dos844_24(), "d/ASCII.PFT": eng}
                job, z = self.run_batch(files, lambda f, s: select(s, fid_of(f, kind="dos-raw"), kinds=["jamo"],
                                                                   dos_layout="844"))
                self.assertEqual(inputkinds.step_tools(job["steps"]), [["jamoset.py"]])
                argv = job["steps"][0]["argv"][0]
                self.assertTrue(argv[argv.index("--eng") + 1].endswith("ASCII.PFT"))
                self.assertEqual([st["state"] for st in job["steps"]], ["done"])
                inputkinds.assert_facecheck(self, z)
                self.assertTrue(any(inputkinds.zip_face(z).glyphs[0x41]))


class VariableCollectionTest(Case):
    def vtc(self):
        return inputfx.ttc([inputfx.variable_ttf(), inputfx.ttf("Two", BOX2)])

    def test_face_0_of_a_variable_ttc_needs_a_ttc_face_op_for_an_instance(self):
        job, z = self.run_batch({"v/V.ttc": self.vtc()}, lambda f, s: select(
            s, fid_of(f, face=0, path="v/V.ttc"), sizes=[24], instance={"wght": 700}))
        self.assertEqual(inputkinds.step_tools(job["steps"]),
                         [["srcprep.py ttc-face", "-m fontTools.varLib.instancer"], ["mkfont.py"]])
        self.assertEqual([st["state"] for st in job["steps"]], ["done", "done"])
        inputkinds.assert_facecheck(self, z)
        _, reg = self.run_batch({"v/V.ttc": self.vtc()}, lambda f, s: select(
            s, fid_of(f, face=0, path="v/V.ttc"), sizes=[24]))
        self.assertNotEqual(ga(z), ga(reg))

    def test_the_default_instance_of_face_0_stays_free_of_a_source_step(self):
        job, _z = self.run_batch({"v/V.ttc": self.vtc()}, lambda f, s: select(
            s, fid_of(f, face=0, path="v/V.ttc"), sizes=[24]))
        self.assertEqual(inputkinds.step_tools(job["steps"]), [["mkfont.py"]])


def tool_names(step):
    return [os.path.basename(argv[2]) for argv in step["argv"]]


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class DyStepTest(Case):
    def test_mkfont_step_ends_with_svfdy(self):
        step = self.plan(inputfx.ttf("D", BOX1), dy={"0x41": 1})[0]
        self.assertEqual(tool_names(step), ["mkfont.py", "svfdy.py"])
        out = os.path.join(self.job_dir, step["output"])
        dy_json = os.path.join(self.job_dir, "work", step["id"], "dy.json")
        self.assertEqual(step["argv"][-1][3:], [out, out, "--json", dy_json])
        self.assertEqual(read_json(dy_json), {"0x41": 1})

    def test_dy_json_is_sorted_hex_whatever_the_keys_were(self):
        step = self.plan(inputfx.ttf("D", BOX1), dy={"g": -1, "65": 2, "0x20": 1})[0]
        dy_json = step["argv"][-1][-1]
        with open(dy_json, encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(json.loads(text), {"0x20": 1, "0x41": 2, "0x67": -1})
        self.assertEqual(list(json.loads(text)), ["0x20", "0x41", "0x67"])

    def test_no_dy_no_svfdy_and_jamo_steps_never_get_one(self):
        self.assertEqual(tool_names(self.plan(inputfx.ttf("D", BOX1))[0]), ["mkfont.py"])
        self.assertEqual(tool_names(self.plan(inputfx.ttf("D", BOX1), dy={})[0]), ["mkfont.py"])

    def test_copy_step_reads_the_upload(self):
        with open(os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF"), "rb") as fh:
            data = fh.read()
        step = self.plan({"s/NEODG16.SVF": data}, dy={"0x41": 1})[0]
        self.assertEqual(len(step["argv"]), 1)
        argv = step["argv"][0]
        self.assertEqual(os.path.basename(argv[2]), "svfdy.py")
        self.assertEqual(argv[3:], [os.path.join(self.job_dir, "upload", "s", "NEODG16.SVF"),
                                    os.path.join(self.job_dir, step["output"]), "--json",
                                    os.path.join(self.job_dir, "work", step["id"], "dy.json")])

    def test_dy_end_to_end(self):
        with open(os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF"), "rb") as fh:
            svf = fh.read()
        for name, files in (("mkfont", {"d/d.ttf": inputfx.ttf("D", BOX1)}), ("copy", {"s/NEODG16.SVF": svf})):
            with self.subTest(route=name):
                job, z = self.run_batch(files, lambda f, st: select(st, inputkinds.only_font(f), dy={"0x41": 1}))
                self.assertEqual([st["state"] for st in job["steps"]], ["done"], job["steps"])
                face = inputkinds.zip_face(z)
                self.assertEqual(face.dy.get(0x41), 1)
                inputkinds.assert_facecheck(self, z)

    def test_dy_on_a_face_without_metrics_fails_with_the_tool_message(self):
        cell = bytes(16 * 2)
        data = jamoset.pack_svfn(16, 16, 12, 1, 0, [cell], [(0x41, 0)], None, None, (0, 0), "default")
        job, z = self.run_batch({"s/NOMETRIC.SVF": data}, lambda f, st: select(st, inputkinds.only_font(f), dy={"0x41": 1}))
        step = job["steps"][0]
        self.assertEqual(step["state"], "failed", step)
        self.assertIn("no metrics table", step["stderr_tail"] + (step["error"] or ""))
        self.assertIsNone(z and next(iter(inputkinds.zip_faces(z)), None))


class ReportStepTest(Case):
    def test_mkfont_argv_and_step_carry_the_report(self):
        step = self.plan(inputfx.ttf("R", BOX1))[0]
        self.assertEqual(step["report"], "work/%s/report.json" % step["id"])
        argv = step["argv"][0]
        self.assertEqual(argv[argv.index("--report") + 1], os.path.join(self.job_dir, step["report"]))

    def test_the_report_comes_before_the_dy_argv_and_only_mkfont_has_one(self):
        step = self.plan(inputfx.ttf("R", BOX1), dy={"0x41": 1})[0]
        self.assertIn("--report", step["argv"][0])
        self.assertNotIn("--report", step["argv"][1])
        with open(os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF"), "rb") as fh:
            copy = self.plan({"s/NEODG16.SVF": fh.read()})[0]
        self.assertIsNone(copy["report"])

    def test_fit_cell_report_mode_fit(self):
        job, z = self.run_batch({"d/d.ttf": inputfx.ttf("R", BOX1)},
                                lambda f, st: select(st, inputkinds.only_font(f),
                                                     options={"mkfont": {"cell": 12, "fit_cell": True}}))
        hits = glob.glob(os.path.join(self.tmp, "j%d" % self.n, "**", job["steps"][0]["report"]), recursive=True)
        self.assertEqual(len(hits), 1, hits)
        rep = read_json(hits[0])
        self.assertEqual(rep["mode"], "fit")


class FaceArgvTest(Case):
    def test_face_argv_equals_plan_steps(self):
        # Limit: this covers the mkfont route only; the jamo fits' commands need the composite master and companions.
        """face_argv builds the commands plan_steps plans (the probe is built from it, never from the options)."""
        self.n += 1
        files = {"d/d.ttf": inputfx.ttf("F", BOX1)}
        store, job = inputkinds.plan_batch(self, os.path.join(self.tmp, "j%d" % self.n), files,
                                           lambda f, st: select(st, inputkinds.only_font(f), bpp=(1, 2), sizes=[16, 17],
                                                                options={"mkfont": {"width": 20, "latin": True}}))
        job_dir = store.path(job["id"])
        font = next(f for f in job["fonts"] if f["id"] == inputkinds.only_font(job["fonts"]))
        eff = settings.effective(job["fonts"], job["settings"], font["id"])
        checked = 0
        for step in job["steps"]:
            if step["kind"] not in ("precomposed", "jamo"):
                continue
            route = routes.route_for(font, step["kind"], True)
            paths = {"tools": os.path.join(REPO_DIR, "tools"), "src": os.path.join(job_dir, "upload", font["path"]),
                     "out": os.path.join(job_dir, step["output"]), "work": os.path.join(job_dir, "work", step["id"]),
                     "eng": None, "latin": None, "master": None,
                     "range_file": None, "base": os.path.join(REPO_DIR, "svf", routes.JOHAB844_BASE)}
            paths["range_file"] = settings.write_range_files(os.path.join(job_dir, "work"))["2350"]
            if step["report"]:
                paths["report"] = os.path.join(job_dir, step["report"])
            got = settings.face_argv(font, eff, route, step["kind"], step["size"], step["bpp"], None, ("2350", None), paths)
            self.assertEqual(got, step["argv"])
            checked += 1
        self.assertEqual(checked, 4)

    def test_face_argv_is_the_literal_command(self):
        """An expectation written out by hand (the equality test above calls the same function as plan_steps)."""
        font = {"id": "f01", "path": "a.ttf", "face_index": 0, "source_kind": "outline", "sizes": [16],
                "sizes_fixed": False, "licences": [], "companions": []}
        st = settings.defaults([font])
        st["fonts"]["f01"].update(preset="dos-l-1bpp", options={"mkfont": {"ascent": 12}})
        eff = settings.effective([font], st, "f01")
        paths = {"tools": "/T", "src": "/u/a.ttf", "out": "/w/O.SVF", "work": "/w", "eng": None, "latin": None,
                 "master": None, "range_file": "/w/range-2350.txt", "report": "/w/report.json"}
        got = settings.face_argv(font, eff, routes.route_for(font, "precomposed", False), "precomposed", 16, 1, None,
                                 ("2350", None), paths)
        self.assertEqual(got, [toolrun.tool("mkfont", "/T") + ["/u/a.ttf", "/w/O.SVF", "--size", "16",
                                            "--cell", "16", "--bpp", "1", "--unicode",
                                            "ascii,ksx1001-nohanja,AC37,B2CF,B584,C125,C2BA,D14A,D59D",
                                            "--ascent", "12", "--report", "/w/report.json"]])


class ProbeArgvTest(unittest.TestCase):
    MKFONT = toolrun.tool("mkfont", "/T") + ["/u/in.ttf", "/w/OUT.SVF"]

    def probe(self, flags, size=16):
        return settings.probe_argv(self.MKFONT + flags, "/u/in.ttf", "/w/p.svf", "/w/p.json", size)

    def test_dos_u_2bpp_keeps_the_presets_list_and_drops_the_cell_flags(self):
        import presets
        merged = routes.apply_flags(toolrun.tool("mkfont", "/T") + ["/u/in.ttf", "/w/OUT.SVF", "--size", "17", "--bpp", "2",
                                                 "--unicode", "ascii,ksx1001-hangul"],
                                    presets.argv_for("dos-u-2bpp", "precomposed", 17) + ["--report", "/w/report.json"])
        got = settings.probe_argv(merged, "/u/in.ttf", "/w/p.svf", "/w/p.json", 17)
        self.assertEqual(got[2:5], ["/T/mkfont.py", "/u/in.ttf", "/w/p.svf"])
        for gone in ("--clip-cell", "--ascent", "--cell", "--fit-cell"):
            self.assertNotIn(gone, got)
        self.assertEqual(got[got.index("--report") + 1], "/w/p.json")
        self.assertEqual(got[got.index("--width") + 1], "16")
        self.assertEqual(got[got.index("--probe-cell") + 1], "16")
        self.assertEqual(got[got.index("--unicode") + 1], "ascii,ksx1001-nohanja,AC37,B2CF,B584,C125,C2BA,D14A,D59D")
        self.assertEqual((got[got.index("--size") + 1], got[got.index("--bpp") + 1]), ("17", "2"))
        self.assertIn("--probe", got)

    def test_width_cell_and_size_defaults(self):
        got = self.probe(["--size", "16", "--bpp", "1", "--unicode", "ascii,ksx1001-hangul", "--width", "20", "--cell", "18"])
        self.assertEqual((got[got.index("--width") + 1], got[got.index("--probe-cell") + 1]), ("20", "18"))
        got = self.probe(["--size", "16", "--bpp", "1", "--unicode", "u", "--cell", "18"])
        self.assertEqual((got[got.index("--width") + 1], got[got.index("--probe-cell") + 1]), ("18", "18"))
        got = self.probe(["--size", "16", "--bpp", "1", "--unicode", "u"])
        self.assertEqual((got[got.index("--width") + 1], got[got.index("--probe-cell") + 1]), ("16", "16"))

    def test_kept_flags(self):
        got = self.probe(["--size", "16", "--bpp", "1", "--unicode", "u", "--latin", "--mono-hint", "--only-listed",
                          "--space-advance", "6", "--punct-extra", "1", "--clip-cell", "--ascent", "9"])
        for flag in ("--latin", "--mono-hint", "--only-listed"):
            self.assertIn(flag, got)
        self.assertEqual((got[got.index("--space-advance") + 1], got[got.index("--punct-extra") + 1]), ("6", "1"))
        self.assertNotIn("9", got)


class SourceOpsTest(Case):
    def test_source_ops_shared_with_plan_steps(self):
        two = inputfx.ttc([inputfx.ttf("One", BOX1), inputfx.ttf("Two", BOX2)])
        for name, files, pick, per in (
                ("ttc face 0 with an instance", {"t/v.ttc": inputfx.ttc([inputfx.variable_ttf(), inputfx.ttf("Two", BOX2)])},
                 dict(face=0, path="t/v.ttc"), {"instance": {"wght": 700}}),
                ("mac cmap", {"m/Mac.ttf": inputfx.mac_cmap_ttf()}, dict(), {}),
                ("ttc face 1", {"t/two.ttc": two}, dict(face=1, path="t/two.ttc"), {})):
            with self.subTest(name):
                self.n += 1
                store, job = inputkinds.plan_batch(self, os.path.join(self.tmp, "j%d" % self.n), files,
                                                   lambda f, st: select(st, inputkinds.fid_of(f, **pick) if pick
                                                                        else inputkinds.only_font(f), **per))
                font = next(f for f in job["fonts"] if f["id"] == next(s["font"] for s in job["steps"]))
                eff = settings.effective(job["fonts"], job["settings"], font["id"])
                ops = settings.source_ops(font, eff)
                self.assertTrue(ops)
                job_dir = store.path(job["id"])
                step = job["steps"][0]
                self.assertEqual(step["kind"], "source")
                want, _ = routes.source_commands(ops, os.path.join(job_dir, "upload", font["path"]),
                                                 os.path.join(job_dir, "work", step["id"]), os.path.join(REPO_DIR, "tools"),
                                                 "otf" if font.get("cff") else "ttf")
                self.assertEqual(step["argv"], want)


class VectorFitTest(Case):
    def test_vector_fit_end_to_end(self):
        job, z = self.run_batch({"v/F.ttf": inputfx.flat_composite_ttf()},
                                lambda f, st: select(st, inputkinds.only_font(f), kinds=["jamo"], experimental=True,
                                                     jamo_route="vector fit", layout="844"))
        self.assertEqual(job["state"], "done", [(s["id"], s["state"], s["stderr_tail"][-300:]) for s in job["steps"]])
        self.assertEqual([s["kind"] for s in job["steps"]], ["prepare", "jamo"])
        self.assertNotIn("--components", job["steps"][0]["argv"][0])
        inputkinds.assert_facecheck(self, z)
        self.assertIsNotNone(job["steps"][1]["quality"])

    def test_mask_fit_plans_pylib(self):
        self.n += 1
        files = {"g/G.ttf": inputfx.gsub_jamo_ttf()}
        store, job = inputkinds.plan_batch(
            self, os.path.join(self.tmp, "j%d" % self.n), files,
            lambda f, st: select(st, inputkinds.only_font(f), kinds=["jamo"], experimental=True, jamo_route="mask fit",
                                 layout="844"), caps={"mask_libs": True}, pylib="/opt/py")
        argv = job["steps"][0]["argv"][0]
        self.assertEqual(argv[-2:], ["--pylib", "/opt/py"])
        self.assertIn("--mask-font", argv)


class NamedRangeTest(Case):
    def test_seven_named_ranges(self):
        paths = settings.write_range_files(self.tmp)
        self.assertEqual(sorted(paths), sorted(settings.NAMED_RANGE_NAMES))
        self.assertEqual(len(settings.NAMED_RANGE_NAMES), 7)
        for name, named in settings.RANGE_FILES:
            with open(paths[name], encoding="utf-8") as fh:
                chars = fh.read().replace("\n", "")
            self.assertEqual([ord(c) for c in chars], mkfont.NAMED_RANGES[named]())

    def test_named_range_reaches_mkfont(self):
        for name in settings.NAMED_RANGE_NAMES:
            step = self.plan(inputfx.ttf("D", BOX1), range=name)[0]
            argv = step["argv"][0]
            want = {"11172": "ascii,hangul", "2350": "ascii,ksx1001-hangul"}.get(name, "ascii," + name)
            self.assertEqual(argv[argv.index("--unicode") + 1], want, name)

    def test_range_messages_name_the_seven(self):
        self.n += 1
        fonts = [{"id": "f01", "path": "a.ttf", "face_index": 0, "source_kind": "outline", "sizes": [16],
                  "sizes_fixed": False, "licences": [], "companions": []}]
        st = settings.defaults(fonts)
        st["batch"]["range"] = "nope"
        msg = [e for e in settings.validate(fonts, st, None) if "range" in e]
        self.assertEqual(msg, ["batch: range nope is not a named range (11172, 2350, ksx1001-nohanja, ksx1001-symbols, "
                               "ksx1001, jamo, cp949) or a list file in the batch"])

    def test_width_and_latin_end_to_end(self):
        def faces(**opts):
            job, z = self.run_batch({"d/d.ttf": inputfx.ttf("D", BOX1)},
                                    lambda f, st: select(st, inputkinds.only_font(f), options={"mkfont": opts}))
            return inputkinds.zip_face(z)
        self.assertEqual(faces(width=20).cell_w, 20)
        plain, latin = faces(cell=10, latin=False), faces(cell=10, latin=True)
        self.assertNotEqual(plain.ascent, latin.ascent)


class ZipoutSourceTitleTest(unittest.TestCase):
    def test_source_step_title(self):
        self.assertEqual(zipout._step_title({"id": "s01", "font": "f02", "kind": "source"}), "## s01 f02 source")


class MacEndToEndTest(localfx.LocalBase):
    """Mac 7.1 type-3 fbit fonts through a local job over HTTP: every wrapping, the companions' source steps, the three
    routes. Synthetic files only (maker/test/macfx.py)."""

    def setUp(self):
        super().setUp()
        self.mac = localfx.mac_tree(os.path.join(self.tmp, "tree", "in", "mac"))

    def p(self, *parts):
        return os.path.join(self.mac, *parts)

    def mac_job(self, roots, fbit_path, name="X", extra=None):
        """A detected job over @p roots with the 12 px fbit at @p fbit_path selected (jamo, direct)."""
        jid = self.local_job(roots)
        job = self.job(jid)
        fonts = {(f["root"], f["path"]): f for f in job["fonts"]}
        font = next(f for f in job["fonts"] if f["path"] == fbit_path)
        st = job["settings"]
        per = st["fonts"][font["id"]]
        per.update(selected=True, dest="jamo-extra", kinds=["jamo"], names={"jamo/12/1": "%s12J.SVF" % name})
        if extra:
            per.update(extra)
        status, body = self.api("PUT", "/api/jobs/%s/settings" % jid, st)
        self.assertEqual(status, 200, body)
        return jid, font

    def done(self, jid):
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error") or [s.get("error") for s in job["steps"]])
        return job

    def face_of(self, job):
        rel = next(f for f in job["result"]["files"] if f.endswith(".SVF"))
        with open(os.path.join(self.out, rel), "rb") as fh:
            return rel, fh.read()

    def test_mac71_direct_written_and_verified(self):
        jid, font = self.mac_job([self.p("Seoul12.rsrc"), self.p("InputBackSupport.rsrc")], "Seoul12.rsrc")
        job = self.done(jid)
        rel, data = self.face_of(job)
        self.assertEqual(jamoset.parse_svfn(data).version, 3)
        check = os.path.join(self.tmp, "check")
        os.makedirs(check)
        import macfx
        for name, blob in (("face.svf", data), ("fbit.bin", macfx.fbit3_raw()), ("htbl.bin", macfx.htbl_raw())):
            with open(os.path.join(check, name), "wb") as f:
                f.write(blob)
        r = subprocess.run([sys.executable, "-P", os.path.join(REPO_DIR, "tools", "macfbit_svf.py"), "verify",
                            os.path.join(check, "face.svf"), os.path.join(check, "fbit.bin"),
                            os.path.join(check, "htbl.bin")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        inputkinds.assert_facecheck_tree(self, self.out)

    def tools_of(self, job):
        return {s["font"] + ":" + s["kind"]: inputkinds.step_tools([s])[0] for s in job["steps"]}

    def test_mac71_wrapped_and_jm(self):
        cases = [([self.p("ad")], "ad/._Seoul12", ["srcprep.py mac-fork", "macfbit3.py"],
                  ["srcprep.py mac-fork", "srcprep.py mac-htbl"]),
                 ([self.p("mb")], "mb/Seoul12.bin", ["srcprep.py mac-fork", "macfbit3.py"],
                  ["srcprep.py mac-fork", "srcprep.py mac-htbl"]),
                 ([self.p("jm", "Seoul12"), self.p("raw", "Seoul12.htbl1")], "Seoul12", ["macfbit3.py"], None)]
        for n, (roots, path, own, other) in enumerate(cases):
            with self.subTest(path=path):
                out = os.path.join(self.tmp, "out%d" % n)
                os.makedirs(out)
                jid = self.local_job(roots, out)
                job = self.job(jid)
                font = next(f for f in job["fonts"] if f["source_kind"] == "mac-fbit3")
                st = job["settings"]
                st["fonts"][font["id"]].update(selected=True, dest="jamo-extra", kinds=["jamo"])
                self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
                done = self.done(jid)
                tools = self.tools_of(done)
                self.assertEqual(tools[font["id"] + ":source"], own)
                htbl = next(f for f in job["fonts"] if f["source_kind"] == "mac-htbl")
                if other:
                    self.assertEqual(tools[htbl["id"] + ":source"], other)
                else:
                    self.assertNotIn(htbl["id"] + ":source", tools)               # a raw table needs no source step
                self.assertEqual(tools[font["id"] + ":jamo"], ["macfbit_svf.py"])

    def test_companion_failure_cascades(self):
        jid = self.local_job([self.p("Seoul12.rsrc"), self.p("raw", "Seoul12.fbit"), self.p("ad", "._InputBackSupport")])
        job = self.job(jid)
        st = job["settings"]
        fbits = [f for f in job["fonts"] if f["source_kind"] == "mac-fbit3"]
        self.assertEqual(len(fbits), 2)
        for i, f in enumerate(fbits):
            st["fonts"][f["id"]].update(selected=True, dest="jamo-extra", kinds=["jamo"],
                                        names={"jamo/12/1": "C%d12J.SVF" % i}, note_name="C%d.TXT" % i)
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        htbl = next(f for f in job["fonts"] if f["source_kind"] == "mac-htbl")
        path = self.p("ad", "._InputBackSupport")
        with open(path, "rb") as f:
            data = bytearray(f.read())
        data[38 + 4:38 + 8] = b"\xff\xff\xff\xff"                  # the fork's map offset: past the end, same size
        with open(path, "wb") as f:
            f.write(bytes(data))
        st2 = os.lstat(path)

        def refresh(j):
            for entry in j["fonts"]:
                if entry["id"] == htbl["id"]:
                    entry["file_id"] = [st2.st_dev, st2.st_ino, st2.st_size]
        self.srv.store.update(jid, refresh)
        job = self.run_to_done(jid)
        by_kind = {}
        for step in job["steps"]:
            by_kind.setdefault((step["font"] == htbl["id"], step["kind"]), []).append(step)
        self.assertEqual([s["state"] for s in by_kind[(True, "source")]], ["failed"])
        faces = by_kind[(False, "jamo")]
        self.assertEqual(len(faces), 2)
        for face in faces:
            self.assertEqual((face["state"], face["error"], face["exit"]), ("failed", "companion source failed", None))
        self.assertEqual(job["state"], "failed")

    def test_mac71_derived_and_bdf_mkfont(self):
        jid, font = self.mac_job([self.p("Seoul12.rsrc"), self.p("InputBackSupport.rsrc")], "Seoul12.rsrc",
                                 extra={"experimental": True, "jamo_route": "mac fbit 7.1 derived"})
        job = self.done(jid)
        rel, data = self.face_of(job)
        face = jamoset.parse_svfn(data)
        self.assertEqual(face.version, 3)
        self.assertIsNotNone(face.jset)                                            # derived: a JSET face, not a JMAP
        out2 = os.path.join(self.tmp, "out2")
        os.makedirs(out2)
        jid = self.local_job([self.p("Seoul12.rsrc"), self.p("InputBackSupport.rsrc")], out2)
        job = self.job(jid)
        font = next(f for f in job["fonts"] if f["source_kind"] == "mac-fbit3")
        st = job["settings"]
        st["fonts"][font["id"]].update(selected=True, dest="dos", kinds=["precomposed"], names={"precomposed/12/1": "BDF12.SVF"},
                                       note_name="BDF.TXT")
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        job = self.done(jid)
        with open(os.path.join(out2, "svf", "dos", "BDF12.SVF"), "rb") as f:
            face = jamoset.parse_svfn(f.read())
        self.assertEqual(face.version, 3)
        chars = set(face.glyphs)
        self.assertEqual(len([c for c in chars if 0xAC00 <= c <= 0xD7A3]), 2350)    # the KS syllables
        self.assertGreaterEqual(len([c for c in chars if 0x3131 <= c <= 0x318E]), 50)  # and the compat jamo (the blank one is omitted)
        self.assertNotIn(0x41, chars)                                              # the BDF holds no ASCII

    def test_mac10_end_to_end_and_prepared_name(self):
        for n, (root, path) in enumerate([(self.p("v1"), "Munjo16.rsrc"), (self.p("v1", "ad"), "._Munjo16"),
                                          (self.p("v1", "mb"), "Munjo16.bin")]):
            with self.subTest(path=path):
                out = os.path.join(self.tmp, "o%d" % n)
                os.makedirs(out)
                jid = self.local_job([root], out)
                job = self.job(jid)
                font = next(f for f in job["fonts"] if f["source_kind"] == "mac-fbit1")
                st = job["settings"]
                st["fonts"][font["id"]].update(selected=True, dest="jamo-extra", kinds=["jamo"])
                self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
                done = self.done(jid)
                face = next(s for s in done["steps"] if s["kind"] == "jamo")
                self.assertEqual(face["name"], "MUNJ16J.SVF")
                self.assertEqual(face["state"], "done")
                if path != "Munjo16.rsrc":                                          # wrapped: a source step first
                    src = next(s for s in done["steps"] if s["kind"] == "source")
                    self.assertTrue(src["output"].endswith("/Munjo16.rsrc"), src["output"])
                with open(os.path.join(self.srv.store.path(jid), "log.md"), encoding="utf-8") as f:
                    self.assertIn("check: composed 11172 syllables", f.read())       # jamoset's own verdict line
                rel = next(f for f in done["result"]["files"] if f.endswith(".SVF"))
                with open(os.path.join(out, rel), "rb") as fh:
                    self.assertEqual(jamoset.parse_svfn(fh.read()).version, 3)

    def test_mac71_source_face_uses_the_chosen_suitcase(self):
        """A suitcase picked as the Latin companion reaches the preview bake: the baked source face then carries ASCII."""
        roots = [self.p("Seoul12.rsrc"), self.p("InputBackSupport.rsrc"), self.p("Suitcase.rsrc")]
        jid, font = self.mac_job(roots, "Seoul12.rsrc")
        r = self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, font["id"]))
        self.assertEqual(r[0], 200)
        self.assertNotIn(0x41, jamoset.parse_svfn(r[2]).glyphs)                    # no suitcase chosen: no ASCII
        suit = next(f["id"] for f in self.job(jid)["fonts"] if f["source_kind"] == "mac-suitcase")
        st = self.job(jid)["settings"]
        st["fonts"][font["id"]]["latin_companion"] = suit
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        r = self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, font["id"]))
        self.assertEqual(r[0], 200)
        self.assertIn(0x41, jamoset.parse_svfn(r[2]).glyphs)

    def test_mac71_gz_fork(self):
        jid, font = self.mac_job([self.p("gz"), self.p("InputBackSupport.rsrc")], "Seoul12.rsrc.gz")
        job = self.done(jid)
        src = next(s for s in job["steps"] if s["font"] == font["id"] and s["kind"] == "source")
        self.assertIn("/work/%s/Seoul12.rsrc" % font["id"], src["argv"][0][4])    # the decompressed copy under work/<fid>/
        self.assertIn(".svf-maker-%s" % jid, src["argv"][0][4])

    def test_mac71_source_face(self):
        jid, font = self.mac_job([self.p("Seoul12.rsrc"), self.p("InputBackSupport.rsrc")], "Seoul12.rsrc")
        r = self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, font["id"]))
        self.assertEqual(r[0], 200)
        self.assertEqual(jamoset.parse_svfn(r[2]).version, 3)
        st = self.job(jid)["settings"]
        st["fonts"][font["id"]]["htbl_companion"] = None
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        r = self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, font["id"]))
        self.assertEqual((r[0], json.loads(r[2])["error"]), (404, "choose the HTBL table"))

    def test_a_changed_htbl_companion_refuses_the_run(self):
        """The pre-run check covers the HTBL table too (replaced, removed, or its size changed)."""
        jid, font = self.mac_job([self.p("Seoul12.rsrc"), self.p("InputBackSupport.rsrc")], "Seoul12.rsrc")
        path = self.p("InputBackSupport.rsrc")
        with open(path, "rb") as f:
            original = f.read()
        message = "InputBackSupport.rsrc: the input changed since detection: detect again"
        with open(path, "ab") as f:
            f.write(b"x")                                                      # size changed
        self.assertEqual(self.api("POST", "/api/jobs/%s/run" % jid)[1:], ({"error": message},))
        with open(path, "wb") as f:
            f.write(original)
        os.rename(path, path + ".old")                                         # replaced: same bytes, new inode
        with open(path, "wb") as f:
            f.write(original)
        self.assertEqual(self.api("POST", "/api/jobs/%s/run" % jid)[0], 409)
        os.remove(path)                                                        # removed
        self.assertEqual(self.api("POST", "/api/jobs/%s/run" % jid)[0], 409)
        os.rename(path + ".old", path)                                         # the detected file is back
        self.assertEqual(self.api("POST", "/api/jobs/%s/run" % jid)[0], 200)
        self.assertEqual(self.wait_done(jid)["state"], "done")

    def test_a_gz_source_leaves_no_decompressed_copy_after_a_bake(self):
        jid, font = self.mac_job([self.p("gz"), self.p("InputBackSupport.rsrc")], "Seoul12.rsrc.gz")
        self.assertEqual(self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, font["id"]))[0], 200)
        left = []
        for dirpath, _d, names in os.walk(os.path.join(self.files_dir(jid), "work", "preview")):
            left += [os.path.join(dirpath, n) for n in names if "probe" not in dirpath and not n.endswith((".svf", ".png"))]
        self.assertEqual(left, [])

    def test_two_fonts_sharing_companions_bake_with_their_own_copies(self):
        import preview
        roots = [self.p("ad/._Seoul12"), self.p("mb/Seoul12.bin"), self.p("InputBackSupport.rsrc"),
                 self.p("Suitcase.rsrc")]
        jid = self.local_job(roots)
        job = self.job(jid)
        fbits = [f for f in job["fonts"] if f["source_kind"] == "mac-fbit3"]
        self.assertEqual(len(fbits), 2)
        htbl = next(f["id"] for f in job["fonts"] if f["source_kind"] == "mac-htbl")
        suit = next(f["id"] for f in job["fonts"] if f["source_kind"] == "mac-suitcase")
        st = job["settings"]
        for f in fbits:
            st["fonts"][f["id"]].update(htbl_companion=htbl, latin_companion=suit)
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        seen, gate = {}, threading.Barrier(2, timeout=20)
        real = preview.bake_source_face

        def spy(font, abs_src, layout, eng, out_svf, tools, flags, **kw):
            seen[font["id"]] = (kw.get("htbl_abs"), kw.get("latin_abs"))
            self.assertTrue(os.path.isfile(kw["htbl_abs"]))
            gate.wait()                                   # both bakes hold their companions at the same time
            ok = real(font, abs_src, layout, eng, out_svf, tools, flags, **kw)
            self.assertTrue(os.path.isfile(kw["htbl_abs"]))
            return ok
        answers = []
        with mock.patch.object(preview, "bake_source_face", spy):
            threads = [threading.Thread(target=lambda i=f["id"]: answers.append(
                self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, i))[0])) for f in fbits]
            for t in threads:
                t.start()
            for t in threads:
                t.join(60)
        self.assertEqual(answers, [200, 200])
        self.assertEqual(len({v[0] for v in seen.values()}), 2, seen)           # not one shared file

    def test_a_hangultalk1_preview_uses_the_plans_stem_name(self):
        import preview
        import settings as settingsmod
        jid = self.local_job([self.p("v1/ad")])
        font = next(f for f in self.job(jid)["fonts"] if f["source_kind"] == "mac-fbit1")
        st = self.job(jid)["settings"]
        st["fonts"][font["id"]].update(selected=True, dest="jamo-extra", kinds=["jamo"])
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        names = []
        real = preview.bake_source_face

        def spy(font_, abs_src, *a, **k):
            names.append(os.path.basename(abs_src))
            return real(font_, abs_src, *a, **k)
        with mock.patch.object(preview, "bake_source_face", spy):
            self.assertEqual(self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, font["id"]))[0], 200)
        self.assertEqual(names, [settingsmod.prepared_name(font)])
        self.assertTrue(names[0].endswith(".rsrc") and not names[0].startswith("source"), names)


if __name__ == "__main__":
    unittest.main()
