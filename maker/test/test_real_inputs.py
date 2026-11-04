#!/usr/bin/env python3
"""Real-file runs of the maker's new input kinds, each skipped unless its environment variable names a file.

No real Apple, HWP or other proprietary file is in the repository: these tests exist for the user to run on their own
copies (SVF_MAKER_REAL_TTC [+ SVF_MAKER_REAL_TTC_FACE, default 1], SVF_MAKER_REAL_VF, SVF_MAKER_REAL_MACTTF,
SVF_MAKER_REAL_DFONT, SVF_MAKER_REAL_PCF_KSC, SVF_MAKER_REAL_PFT, SVF_MAKER_REAL_EBDT).

  SVF_MAKER_REAL_TTC=/path/F.ttc python3 -m unittest discover -s maker/test -p 'test_real_inputs.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import shutil
import tempfile
import unittest

import inputkinds
import inputfx  # noqa: F401
import jamofit
from inputkinds import fid_of, select


def real(var):
    return unittest.skipUnless(os.environ.get(var) and os.path.isfile(os.environ.get(var, "")), "%s names no file" % var)


class RealInputsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="real-inputs-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def run_file(self, var, choose, name=None):
        path = os.environ[var]
        with open(path, "rb") as fh:
            data = fh.read()
        rel = "r/" + (name or os.path.basename(path))
        job, z = inputkinds.run_batch(self, os.path.join(self.tmp, "job"), {rel: data}, lambda f, s: choose(f, s, rel))
        self.assertEqual(job["state"], "done", job.get("error"))
        inputkinds.assert_facecheck(self, z)
        return job, z

    @real("SVF_MAKER_REAL_TTC")
    def test_real_ttc(self):
        face = int(os.environ.get("SVF_MAKER_REAL_TTC_FACE", "1"))
        self.run_file("SVF_MAKER_REAL_TTC", lambda f, s, rel: select(
            s, fid_of(f, face=face, path=rel), kinds=["precomposed"], sizes=[16]))

    @real("SVF_MAKER_REAL_MACTTF")
    def test_real_macttf(self):
        self.run_file("SVF_MAKER_REAL_MACTTF", lambda f, s, rel: select(
            s, fid_of(f, face=0, path=rel), kinds=["precomposed"], sizes=[16]))

    @real("SVF_MAKER_REAL_DFONT")
    def test_real_dfont(self):
        self.run_file("SVF_MAKER_REAL_DFONT", lambda f, s, rel: select(
            s, fid_of(f, face=0, path=rel), kinds=["precomposed"], sizes=[16]))

    @real("SVF_MAKER_REAL_VF")
    def test_real_vf(self):
        def choose(fonts, s, rel):
            fid = fid_of(fonts, face=0, path=rel)
            font = [f for f in fonts if f["id"] == fid][0]
            self.assertIsNotNone(font.get("variable"), "the file is not a variable font")
            first = font["variable"]["instances"][0]["coords"] if font["variable"]["instances"] else {}
            select(s, fid, kinds=["precomposed"], sizes=[16], instance=first)
        self.run_file("SVF_MAKER_REAL_VF", choose)

    @real("SVF_MAKER_REAL_PCF_KSC")
    def test_real_pcf_ksc(self):
        path = os.environ["SVF_MAKER_REAL_PCF_KSC"]
        with open(path, "rb") as fh:
            data = fh.read()
        latin = inputfx.latin_bdf_from_neodg(os.path.join(self.tmp, "latin.bdf"))
        with open(latin, "rb") as fh:
            latin_data = fh.read()
        job, z = inputkinds.run_batch(
            self, os.path.join(self.tmp, "job"),
            {"r/" + os.path.basename(path): data, "r/latin.bdf": latin_data},
            lambda f, s: select(s, fid_of(f, kind="bdf-ksc5601"), range="2350"))
        self.assertEqual(job["state"], "done", job.get("error"))
        inputkinds.assert_facecheck(self, z)

    @real("SVF_MAKER_REAL_PFT")
    def test_real_pft(self):
        with open(os.environ["SVF_MAKER_REAL_PFT"], "rb") as fh:
            pft = fh.read()
        job, z = inputkinds.run_batch(
            self, os.path.join(self.tmp, "job"), {"r/HAN24.FNT": inputfx.dos844_24(), "r/ASCII.PFT": pft},
            lambda f, s: select(s, fid_of(f, kind="dos-raw"), kinds=["jamo"], dos_layout="844"))
        self.assertEqual(job["state"], "done", job.get("error"))
        inputkinds.assert_facecheck(self, z)

    @real("SVF_MAKER_REAL_EBDT")
    def test_real_ebdt(self):
        def choose(fonts, s, rel):
            fid = fid_of(fonts, face=0, path=rel)
            font = [f for f in fonts if f["id"] == fid][0]
            select(s, fid, kinds=["precomposed"], sizes=[font["sizes"][0]])
        self.run_file("SVF_MAKER_REAL_EBDT", choose)

    @unittest.skipUnless(jamofit.libs_available(os.environ.get("JAMOSET_PYLIB")), "freetype-py/uharfbuzz absent")
    def test_mask_fit(self):
        """neodgm (GSUB conjoining jamo): the mask fit's argv holds --mask-font and --no-clean, the fit does not fall back
        to the free fit, and its face differs from the experimental fit's at the same size."""
        path = os.path.join(REPO_DIR, "ttf", "neodgm", "neodgm.ttf")
        with open(path, "rb") as fh:
            data = fh.read()
        faces = {}
        for route in ("mask fit", "experimental fit"):
            job, z = inputkinds.run_batch(self, os.path.join(self.tmp, route.replace(" ", "-")), {"n/neodgm.ttf": data},
                                          lambda f, s: select(s, inputkinds.only_font(f), kinds=["jamo"], experimental=True,
                                                              jamo_route=route, layout="844"),
                                          caps={"mask_libs": True}, pylib=os.environ.get("JAMOSET_PYLIB") or None)
            self.assertEqual(job["state"], "done", job.get("error"))
            step = job["steps"][0]
            if route == "mask fit":
                self.assertIn("--mask-font", step["argv"][0])
                self.assertIn("--no-clean", step["argv"][0])
                self.assertNotIn("fitting without the mask font", step["stderr_tail"])
            faces[route] = inputkinds.zip_face(z).glyphs
        self.assertNotEqual(faces["mask fit"], faces["experimental fit"])

    @unittest.skipUnless(os.environ.get("SVF_MAKER_REAL_VECTOR"), "set SVF_MAKER_REAL_VECTOR to a TTF")
    def test_real_vector(self):
        """A vector fit of a real font; the seconds are printed (ruling D7: minutes per font)."""
        import time
        path = os.environ["SVF_MAKER_REAL_VECTOR"]
        with open(path, "rb") as fh:
            data = fh.read()
        started = time.monotonic()
        job, z = inputkinds.run_batch(self, os.path.join(self.tmp, "vector"), {"v/" + os.path.basename(path): data},
                                      lambda f, s: select(s, inputkinds.only_font(f), kinds=["jamo"], experimental=True,
                                                          jamo_route="vector fit", layout="844"))
        print("real vector fit: %.1f s" % (time.monotonic() - started))
        self.assertEqual(job["state"], "done", job.get("error"))
        inputkinds.assert_facecheck(self, z)


if __name__ == "__main__":
    unittest.main()
