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

    @real("SVF_MAKER_REAL_EBDT")
    def test_real_ebdt(self):
        def choose(fonts, s, rel):
            fid = fid_of(fonts, face=0, path=rel)
            font = [f for f in fonts if f["id"] == fid][0]
            select(s, fid, kinds=["precomposed"], sizes=[font["sizes"][0]])
        self.run_file("SVF_MAKER_REAL_EBDT", choose)


if __name__ == "__main__":
    unittest.main()
