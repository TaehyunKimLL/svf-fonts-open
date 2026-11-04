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
import tempfile
import unittest

import detect
import fixtures
import inputfx
import inputkinds
import jamoset
import mkfont
import routes
import settings
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
        self.assertEqual(argvs, [routes.PY + ["/T/macsfnt.py", "extract", "/u/F.dfont", "/w/source-1.ttf", "--id", "128"],
                                 routes.PY + ["/T/macsfnt.py", "unicode", "/w/source-1.ttf", "/w/source.ttf"]])
        self.assertEqual(out, "/w/source.ttf")

    def test_instance_pins_every_axis(self):
        argvs, _ = routes.source_commands([{"op": "instance", "coords": {"wght": 700, "wdth": 87.5}}], "/u/V.ttf", "/w", "/T")
        self.assertEqual(argvs[0][2:], ["-m", "fontTools.varLib.instancer", "/u/V.ttf", "wdth=87.5", "wght=700", "-o",
                                        "/w/source.ttf"])

    def test_ttc_face_uses_srcprep(self):
        argvs, out = routes.source_commands([{"op": "ttc-face", "index": 1}], "/u/t.ttc", "/w", "/T")
        self.assertEqual(argvs, [routes.PY + [routes.SRCPREP, "ttc-face", "/u/t.ttc", "/w/source.ttf", "--index", "1"]])

    def test_instance_values_are_not_rounded(self):
        argvs, _ = routes.source_commands([{"op": "instance", "coords": {"XHGT": 123456.7, "wght": 899.99999}}],
                                          "/u/V.ttf", "/w", "/T")
        self.assertEqual(argvs[0][5:7], ["XHGT=123456.7", "wght=899.99999"])

    def test_a_cff_face_is_saved_as_otf(self):
        argvs, out = routes.source_commands([{"op": "ttc-face", "index": 1}], "/u/c.otc", "/w", "/T", "otf")
        self.assertEqual(out, "/w/source.otf")

    def test_pcf_bdf_writes_a_bdf(self):
        argvs, out = routes.source_commands([{"op": "pcf-bdf"}], "/u/k.pcf.gz", "/w", "/T")
        self.assertEqual(argvs, [routes.PY + [routes.SRCPREP, "pcf-bdf", "/u/k.pcf.gz", "/w/source.bdf"]])
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
        self.assertEqual(got, [routes.PY + ["/T/mkfont.py", "/u/a.ttf", "/w/O.SVF", "--size", "16",
                                            "--cell", "16", "--bpp", "1", "--unicode",
                                            "ascii,ksx1001-nohanja,AC37,B2CF,B584,C125,C2BA,D14A,D59D",
                                            "--ascent", "12", "--report", "/w/report.json"]])


class ProbeArgvTest(unittest.TestCase):
    MKFONT = routes.PY + ["/T/mkfont.py", "/u/in.ttf", "/w/OUT.SVF"]

    def probe(self, flags, size=16):
        return settings.probe_argv(self.MKFONT + flags, "/u/in.ttf", "/w/p.svf", "/w/p.json", size)

    def test_dos_u_2bpp_keeps_the_presets_list_and_drops_the_cell_flags(self):
        import presets
        merged = routes.apply_flags(routes.PY + ["/T/mkfont.py", "/u/in.ttf", "/w/OUT.SVF", "--size", "17", "--bpp", "2",
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


if __name__ == "__main__":
    unittest.main()
