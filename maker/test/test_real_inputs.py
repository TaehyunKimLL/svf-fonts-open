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
import subprocess
import tempfile
import unittest

import inputkinds
import inputfx  # noqa: F401
import jamofit
from inputkinds import fid_of, select


def real(var):
    return unittest.skipUnless(os.environ.get(var) and os.path.isfile(os.environ.get(var, "")), "%s names no file" % var)


@unittest.skipUnless(sys.platform == "darwin" and os.path.isfile(os.environ.get("SVF_MAKER_REAL_NAMEDFORK", "")),
                     "SVF_MAKER_REAL_NAMEDFORK names no file (and this is not macOS)")
class NamedForkTest(unittest.TestCase):
    """A macOS file whose fonts live in its native resource fork: a local job over it lists their entries and runs the
    first one that needs no companion. Unverifiable off macOS; the stand-in tests are in test_detect_inputs."""

    def test_named_fork(self):
        import localfx
        import time

        class Case(localfx.LocalBase):
            def runTest(self):
                path = os.environ["SVF_MAKER_REAL_NAMEDFORK"]
                jid = self.local_job([path])
                job = self.job(jid)
                named = [f for f in job["fonts"] if (f.get("prep") or [{}])[0].get("op") == "mac-fork-named"]
                self.assertTrue(named, "no entry came from the named fork")
                font = next((f for f in named if f["source_kind"] in ("mac-fbit1", "outline", "outline-composite")), None)
                if font is None:
                    return                                              # a 7.1 fbit needs its HTBL: detection is the check
                st = job["settings"]
                st["fonts"][font["id"]].update(selected=True, dest="new/named")
                self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
                self.assertEqual(self.run_to_done(jid)["state"], "done")
        case = Case()
        result = unittest.TestResult()
        case.run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)


def _real_dir_case(var, body):
    """A LocalBase test case body run only when @p var names the user's own file."""
    import localfx

    class Case(localfx.LocalBase):
        def runTest(self):
            body(self, os.environ[var])
    return Case


@unittest.skipUnless(os.path.isfile(os.environ.get("SVF_MAKER_REAL_MAC1", "")),
                     "SVF_MAKER_REAL_MAC1 names no file (a HangulTalk 1.0 font's resource fork, e.g. Munjo24.rsrc)")
class RealMac1Test(unittest.TestCase):
    """A real HangulTalk 1.0 font through a local job: done, jamoset's own check line, the golden when one exists, and the
    input's folder untouched."""

    def test_real_mac1(self):
        import hashlib

        def snapshot(folder):
            out = {}
            for dirpath, _d, names in os.walk(folder):
                for n in names:
                    p = os.path.join(dirpath, n)
                    with open(p, "rb") as f:
                        out[p] = (os.stat(p).st_size, os.stat(p).st_mtime_ns, hashlib.sha256(f.read()).hexdigest())
            return out

        def body(case, path):
            before = snapshot(os.path.dirname(path))
            jid = case.local_job([path])
            job = case.job(jid)
            font = next(f for f in job["fonts"] if f["source_kind"] == "mac-fbit1")
            st = job["settings"]
            st["fonts"][font["id"]].update(selected=True, dest="jamo-extra", kinds=["jamo"])
            case.assertEqual(case.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
            done = case.run_to_done(jid)
            case.assertEqual(done["state"], "done", done.get("error"))
            with open(os.path.join(case.srv.store.path(jid), "log.md"), encoding="utf-8") as f:
                case.assertIn("check: composed 11172 syllables", f.read())
            case.assertEqual(snapshot(os.path.dirname(path)), before)
            golden = os.path.join(REPO_DIR, "tools", "testdata", "mac-fbit-golden.json")
            if os.path.isfile(golden):
                r = subprocess.run([sys.executable, "-P", os.path.join(REPO_DIR, "tools", "jamoset.py"), "--layout",
                                    "mac-fbit-45sets", path, "--check", "-o", os.path.join(case.tmp, "g.svf")],
                                   capture_output=True, text=True)
                case.assertEqual(r.returncode, 0, r.stderr)
                case.assertIn("golden: ok", r.stdout)
        case = _real_dir_case("SVF_MAKER_REAL_MAC1", body)()
        result = unittest.TestResult()
        case.run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)


@unittest.skipUnless(os.path.isdir(os.environ.get("SVF_MAKER_REAL_MAC3", "")),
                     "SVF_MAKER_REAL_MAC3 names no folder (a 7.1 font file or its splt, and the HTBL 1 table)")
class RealMac3Test(unittest.TestCase):
    """A real HangulTalk 7.1 font and its HTBL 1 through a local job: done, macfbit_svf.py verify exits 0, facecheck passes,
    and the raw table is 9,612 or 9,816 bytes."""

    def test_real_mac3(self):
        import macfbit3

        def body(case, folder):
            jid = case.local_job([folder])
            job = case.job(jid)
            fbit = next(f for f in job["fonts"] if f["source_kind"] == "mac-fbit3")
            htbl = next(f for f in job["fonts"] if f["source_kind"] == "mac-htbl")
            st = job["settings"]
            st["fonts"][fbit["id"]].update(selected=True, dest="jamo-extra", kinds=["jamo"], htbl_companion=htbl["id"])
            case.assertEqual(case.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
            done = case.run_to_done(jid)
            case.assertEqual(done["state"], "done", done.get("error"))
            roots = {i: r["path"] for i, r in enumerate(job["roots"])}
            with open(os.path.join(roots[fbit["root"]], fbit["path"]) if os.path.isdir(roots[fbit["root"]])
                      else roots[fbit["root"]], "rb") as f:
                raw_fbit = macfbit3.load_fbit(f.read())
            with open(os.path.join(roots[htbl["root"]], htbl["path"]) if os.path.isdir(roots[htbl["root"]])
                      else roots[htbl["root"]], "rb") as f:
                raw_htbl = macfbit3.load_htbl1(f.read())
            case.assertIn(len(raw_htbl), (9612, 9816))
            check = os.path.join(case.tmp, "check")
            os.makedirs(check)
            for name, blob in (("fbit.bin", raw_fbit), ("htbl.bin", raw_htbl)):
                with open(os.path.join(check, name), "wb") as f:
                    f.write(blob)
            face = os.path.join(case.out, next(f for f in done["result"]["files"] if f.endswith(".SVF")))
            r = subprocess.run([sys.executable, "-P", os.path.join(REPO_DIR, "tools", "macfbit_svf.py"), "verify", face,
                                os.path.join(check, "fbit.bin"), os.path.join(check, "htbl.bin")],
                               capture_output=True, text=True)
            case.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            inputkinds.assert_facecheck_tree(case, case.out)
        case = _real_dir_case("SVF_MAKER_REAL_MAC3", body)()
        result = unittest.TestResult()
        case.run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)


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
