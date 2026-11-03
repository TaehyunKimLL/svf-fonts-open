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

import gzip
import shutil
import tempfile
import unittest

import detect
import fixtures
import inputfx
import inputkinds
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
        self.assertIsNotNone(job["steps"][2]["quality"])

    def test_a_failed_source_step_fails_the_font(self):
        self.n += 1
        tmp = os.path.join(self.tmp, "j%d" % self.n)

        def corrupt_after_detection(fonts, s):
            select(s, fid_of(fonts, face=1))
            for root, _d, names in os.walk(tmp):
                for name in names:
                    if name == "two.ttc":
                        path = os.path.join(root, name)
                        with open(path, "rb") as fh:
                            data = fh.read()
                        with open(path, "wb") as fh:
                            fh.write(data[:40])
        job, z = inputkinds.run_batch(self, tmp, {"t/two.ttc": _two()}, corrupt_after_detection)
        self.assertEqual([st["state"] for st in job["steps"]], ["failed", "failed"])
        self.assertEqual(job["steps"][1]["error"], "source failed")
        self.assertEqual(job["state"], "failed")


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
                                                                  PATHS, ["--jset-version", "2"])
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


class ZipoutSourceTitleTest(unittest.TestCase):
    def test_source_step_title(self):
        self.assertEqual(zipout._step_title({"id": "s01", "font": "f02", "kind": "source"}), "## s01 f02 source")


if __name__ == "__main__":
    unittest.main()
