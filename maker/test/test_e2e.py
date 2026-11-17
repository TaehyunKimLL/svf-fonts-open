#!/usr/bin/env python3
"""End-to-end tests (t_e073891a): the mixed test folder through the real HTTP server in upload mode and in local mode,
checked with facecheck, the owner's merge + `mkindex --check`, and svfline draws."""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hashlib
import shutil
import tempfile
import time
import unittest
import urllib.parse
import zipfile

import detect
import e2efx
import inputkinds
import localfx
import zipout


def _scratch(prefix):
    return os.path.realpath(tempfile.mkdtemp(prefix=prefix))

FACE_NAMES = ["svf/dos/ISO16.SVF", "svf/dos/NANUM20.SVF", "svf/jamo-extra/FIXT16J.SVF", "svf/jamo-extra/HAN16J.SVF"]


def _need(ok, what):
    """A setup check that survives `python -O` (a bare `assert` does not)."""
    if not ok:
        raise AssertionError(what)


def assert_roles(test, job, role_of, shipped):
    """Every planned step done, no failed step, one output step per role with the pinned tool sequences."""
    test.assertEqual(job["state"], "done", job.get("error"))
    test.assertEqual(job["result"]["failed_steps"], [])
    test.assertTrue(job["steps"])
    test.assertTrue(all(s["state"] == "done" for s in job["steps"]), [(s["kind"], s["state"]) for s in job["steps"]])
    out = {}                                              # role -> [(kind, tools of that step)], in step order
    for s in job["steps"]:
        if s["kind"] in ("precomposed", "jamo"):
            out.setdefault(role_of[s["font"]], []).append((s["kind"], inputkinds.step_tools([s])[0]))
    want = {"ttf": ["precomposed"], "bdf": ["precomposed"], "pcf": ["jamo"], "dos": ["jamo"]}
    if shipped:
        want["shipped"] = ["precomposed"]
    test.assertEqual({r: [k for k, _ in v] for r, v in out.items()}, want)      # exactly one output step per role
    # the landed tool sequences (t_df773bf5: a mkfont face ends with svf2to3); the copy of a shipped face runs none
    test.assertEqual(out["ttf"][0][1], ["mkfont.py", "svf2to3.py"])
    test.assertEqual(out["bdf"][0][1], ["mkfont.py", "svf2to3.py"])
    test.assertEqual(out["dos"][0][1], ["jamoset.py"])
    test.assertEqual(out["pcf"][0][1], ["jamoset.py"])     # its `srcprep.py pcf-bdf` is a separate source step
    if shipped:
        test.assertEqual(out["shipped"][0][1], [])
    sources = [s for s in job["steps"] if s["kind"] == "source"]
    test.assertEqual([inputkinds.step_tools([s])[0] for s in sources], [["srcprep.py pcf-bdf"]])
    test.assertEqual(role_of[sources[0]["font"]], "pcf")


def _walk_rel(root):
    """The `/`-separated relative paths of every file under @p root, leftovers (`.svf-maker-*`) included."""
    out = set()
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            out.add(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return out


class MixedTreeTest(unittest.TestCase):
    def test_tree_detects_one_font_per_role(self):
        with tempfile.TemporaryDirectory(prefix="e2e-tree-") as d:
            tree = e2efx.mixed_tree(os.path.join(d, "t"), shipped=True)
            kinds = sorted(f["source_kind"] for f in detect.scan(os.path.join(d, "t")) if f["source_kind"] in e2efx.ROLES)
            self.assertEqual(kinds, sorted(e2efx.ROLES))
            self.assertEqual(len(tree["roots"]), 5)


class UploadEndToEndTest(unittest.TestCase):
    """The mixed folder as one zip through `PUT files`, detect, settings, run, `GET zip`."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = _scratch("e2e-upload-")
        try:
            cls._run()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _run(cls):
        cls.tree = e2efx.mixed_tree(os.path.join(cls.scratch, "in"), shipped=True)
        cls.server = e2efx.Server(os.path.join(cls.scratch, "data"))
        api = cls.server.api
        status, body = api("POST", "/api/jobs")
        _need(status == 200, body)
        cls.jid = jid = body["id"]
        status, body = api("PUT", "/api/jobs/%s/files?path=%s" % (jid, urllib.parse.quote("e2e.zip", safe="")),
                           body=e2efx.zip_tree(os.path.join(cls.scratch, "in")))
        _need(status == 200, body)
        status, body = api("POST", "/api/jobs/%s/detect" % jid)
        _need(status == 200, body)
        status, job = api("GET", "/api/jobs/%s" % jid)
        _need(status == 200, job)
        st, ids = e2efx.select_mixed(job)
        cls.role_of = {fid: role for role, fid in ids.items()}
        status, body = api("PUT", "/api/jobs/%s/settings" % jid, st)
        _need(status == 200, body)
        status, body = api("POST", "/api/jobs/%s/run" % jid)
        _need(status == 200, body)
        cls.job = cls.server.wait_done(jid)
        status, _h, data = cls.server.call("GET", "/api/jobs/%s/zip" % jid)
        _need(status == 200, status)
        cls.zip_path = os.path.join(cls.scratch, "out.zip")
        with open(cls.zip_path, "wb") as fh:
            fh.write(data)
        cls.extracted = os.path.join(cls.scratch, "x")
        with zipfile.ZipFile(cls.zip_path) as zf:
            zf.extractall(cls.extracted)
        cls.extracted_svf = os.path.join(cls.extracted, "svf")
        side = "svf-maker-%s/" % jid
        cls.side = {}
        with zipfile.ZipFile(cls.zip_path) as zf:
            for name in ("LICENCES.tsv.lines", "FAMILIES.tsv.lines", "FACES.TSV.lines", "BUILD.md"):
                cls.side[name] = zf.read(side + name)
        cls.duplicate_block = cls.side["BUILD.md"].decode("utf-8").split(zipout.DUPLICATE_HEADING, 1)[1].split("```")[1]
        cls.merge_dir = os.path.join(cls.scratch, "merge")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server", None):
            cls.server.stop()
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def test_every_step_done_with_the_expected_tools(self):
        assert_roles(self, self.job, self.role_of, shipped=True)

    def test_zip_passes_facecheck_and_the_shipped_copy_is_skipped(self):
        inputkinds.assert_facecheck(self, self.zip_path)       # manifest + verify, every SVF is v3
        faces = inputkinds.zip_faces(self.zip_path)
        self.assertEqual(sorted(n.split("/")[1] for n in faces), ["dos", "dos", "jamo-extra", "jamo-extra"])
        skipped = self.job["result"]["skipped"]
        self.assertEqual([s["identical_to"] for s in skipped], ["dos/NEODG16.SVF"])
        self.assertTrue(skipped[0]["name"].endswith("NEODG16.SVF"), skipped)
        self.assertIn("dos/NEODG16.SVF", self.duplicate_block)
        # known, by design today: the skipped face's note still ships as svf/new/e2e/NEODG.TXT (noted on the card)
        self.assertIn("svf/new/e2e/NEODG.TXT", zipfile.ZipFile(self.zip_path).namelist())

    def test_merge_into_the_repository_passes_mkindex(self):
        e2efx.merge_check(self, self.extracted_svf, self.side, base_repo=True, scratch=self.merge_dir)

    def test_every_face_draws(self):
        faces = inputkinds.zip_faces(self.zip_path)
        self.assertEqual(sorted(faces), FACE_NAMES)
        for name in faces:
            with self.subTest(face=name):
                e2efx.assert_draws(self, os.path.join(self.extracted, name))


def _hashes(roots):
    """{path: sha256} of every file under @p roots."""
    out = {}
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                path = os.path.join(dirpath, name)
                with open(path, "rb") as fh:
                    out[path] = hashlib.sha256(fh.read()).hexdigest()
    return out


class LocalEndToEndTest(unittest.TestCase):
    """The mixed folder (without the shipped copy) in local mode: sources by path, an output folder."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = _scratch("e2e-local-")
        try:
            cls._run()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _run(cls):
        cls.tree = e2efx.mixed_tree(os.path.join(cls.scratch, "in"), shipped=False)
        cls.out = os.path.join(cls.scratch, "out")
        os.makedirs(cls.out)
        cls.input_hashes = _hashes(cls.tree["roots"])
        cls.server = e2efx.Server(os.path.join(cls.scratch, "data"), token=localfx.TOKEN)
        api = cls.server.api
        status, body = api("POST", "/api/jobs", {"source": "local", "output_dir": cls.out})
        _need(status == 200, body)
        cls.jid = jid = body["id"]
        status, body = api("PUT", "/api/jobs/%s/sources" % jid, {"paths": cls.tree["roots"]})
        _need(status == 200, body)
        status, body = api("POST", "/api/jobs/%s/detect" % jid)
        _need(status == 200, body)
        status, job = api("GET", "/api/jobs/%s" % jid)
        _need(status == 200, job)
        st, ids = e2efx.select_mixed(job)
        cls.role_of = {fid: role for role, fid in ids.items()}
        status, body = api("PUT", "/api/jobs/%s/settings" % jid, st)
        _need(status == 200, body)
        status, body = api("POST", "/api/jobs/%s/run" % jid)
        _need(status == 200, body)
        cls.job = cls.server.wait_done(jid)
        deadline = time.monotonic() + 10                  # the end-of-run sweep of `.svf-maker-<id>/`, bounded
        while time.monotonic() < deadline:
            cls.disk = _walk_rel(cls.out)
            if not any(p.startswith(".svf-maker-") for p in cls.disk):
                break
            time.sleep(0.1)
        side = os.path.join(cls.out, "build-%s" % jid)
        cls.side = {}
        if os.path.isdir(side):
            for name in ("LICENCES.tsv.lines", "FAMILIES.tsv.lines", "FACES.TSV.lines", "BUILD.md"):
                with open(os.path.join(side, name), "rb") as fh:
                    cls.side[name] = fh.read()
        cls.merge_dir = os.path.join(cls.scratch, "merge")

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server", None):
            cls.server.stop()
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def input_hashes_now(self):
        return _hashes(self.tree["roots"])

    def test_every_step_done_with_the_expected_tools(self):
        assert_roles(self, self.job, self.role_of, shipped=False)

    def test_done_and_only_svf_and_build_written(self):
        self.assertEqual(self.job["state"], "done", self.job.get("error"))
        self.assertNotIn("zip", self.job["result"])
        files = self.job["result"]["files"]
        self.assertEqual(sorted(f for f in files if f.endswith(".SVF")),
                         sorted(s["written"] for s in self.job["steps"] if s.get("written")))
        self.assertEqual(sorted(f for f in files if f.endswith(".SVF")), FACE_NAMES)
        self.assertEqual(self.disk, set(files))             # the folder holds exactly what the result reports
        self.assertTrue(all(f.startswith(("svf/dos/", "svf/jamo-extra/", "build-%s/" % self.jid)) for f in self.disk),
                        sorted(self.disk))
        self.assertEqual([p for p in self.disk if p.startswith(".svf-maker-")], [])
        self.assertEqual(self.input_hashes_now(), self.input_hashes)       # the fonts were read in place, unchanged

    def test_tree_passes_facecheck(self):
        inputkinds.assert_facecheck_tree(self, self.out)

    def test_tree_passes_mkindex_on_its_own(self):
        e2efx.merge_check(self, os.path.join(self.out, "svf"), self.side, base_repo=False, scratch=self.merge_dir)

    def test_every_face_draws(self):
        faces = sorted(p for p in self.disk if p.endswith(".SVF"))        # from the folder (equal to result["files"])
        self.assertEqual(faces, FACE_NAMES)
        for rel in faces:
            with self.subTest(face=rel):
                e2efx.assert_draws(self, os.path.join(self.out, rel))


GBATB17 = os.path.join(REPO_DIR, "svf", "dos", "GBATB17.SVF")
# The exact LICENCES.tsv.lines row of the preset face (zipout.licences_line): the face's note and licence, both in the
# zip as svf/new/acc/GOWUN.TXT, and the licence is the equal file the repository already has, dos/OFLGOWUN.TXT. (web/LICENCES.tsv has the glob `dos/GBATB*.SVF`, which
# covers this face too: the duplicate block alone would list it either way, so it is not what pins the identity.)
GBATB17_ROW = "dos/GBATB17.SVF\tnew/acc/GOWUN.TXT,dos/OFLGOWUN.TXT"


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


class PresetAcceptanceTest(unittest.TestCase):
    """`dos-u-2bpp` at 17 px over GowunBatang-Bold through the full upload job reproduces `svf/dos/GBATB17.SVF` byte
    for byte. This is the only byte-level pin of the `svf2to3.py --profile default` tail of the mkfont route."""

    @classmethod
    def setUpClass(cls):
        cls.scratch = _scratch("e2e-preset-")
        try:
            cls._run()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _run(cls):
        cls.server = e2efx.Server(os.path.join(cls.scratch, "data"))
        api = cls.server.api
        status, body = api("POST", "/api/jobs")
        _need(status == 200, body)
        cls.jid = jid = body["id"]
        src = os.path.join(REPO_DIR, "ttf", "gowunbatang")
        for name, rel in (("GowunBatang-Bold.ttf", "gowun/GowunBatang-Bold.ttf"), ("OFL.txt", "gowun/OFL.txt")):
            status, body = api("PUT", "/api/jobs/%s/files?path=%s" % (jid, urllib.parse.quote(rel, safe="")),
                               body=_read(os.path.join(src, name)))
            _need(status == 200, body)
        status, body = api("POST", "/api/jobs/%s/detect" % jid)
        _need(status == 200, body)
        status, job = api("GET", "/api/jobs/%s" % jid)
        _need(status == 200, job)
        fid = inputkinds.only_font(job["fonts"])
        st = job["settings"]
        for per in st["fonts"].values():
            per["selected"] = False
        inputkinds.select(st, fid, dest="new/acc", bpp=(2,), kinds=["precomposed"], sizes=[17], preset="dos-u-2bpp")
        status, body = api("PUT", "/api/jobs/%s/settings" % jid, st)
        _need(status == 200, body)
        status, body = api("POST", "/api/jobs/%s/run" % jid)
        _need(status == 200, body)
        cls.job = cls.server.wait_done(jid)
        status, _h, data = cls.server.call("GET", "/api/jobs/%s/zip" % jid)
        _need(status == 200, status)
        cls.zip_path = os.path.join(cls.scratch, "out.zip")
        with open(cls.zip_path, "wb") as fh:
            fh.write(data)
        steps = [s for s in cls.job["steps"] if s["kind"] == "precomposed"]
        _need(len(steps) == 1, steps)
        cls.step = steps[0]
        cls.out = cls.server.srv.store.path(jid, cls.step["output"])

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server", None):
            cls.server.stop()
        shutil.rmtree(cls.scratch, ignore_errors=True)

    def test_dos_u_2bpp_over_http_is_identical_to_gbatb17(self):
        self.assertEqual(self.job["state"], "done", self.job.get("error"))
        self.assertEqual(self.step["state"], "done", self.step.get("error"))
        self.assertEqual(inputkinds.step_tools([self.step])[0], ["mkfont.py", "svf2to3.py"])
        self.assertEqual(_read(self.out), _read(GBATB17))
        self.assertEqual(self.step["identical_to"], "dos/GBATB17.SVF")

    def test_zip_skips_the_face_and_lists_its_row(self):
        self.assertEqual(inputkinds.zip_faces(self.zip_path), {})
        self.assertEqual([s["identical_to"] for s in self.job["result"]["skipped"]], ["dos/GBATB17.SVF"])
        side = "svf-maker-%s/" % self.jid
        with zipfile.ZipFile(self.zip_path) as zf:
            names = zf.namelist()
            licences = zf.read(side + "LICENCES.tsv.lines").decode()
            build = zf.read(side + "BUILD.md").decode()
        rows = [r for r in licences.splitlines() if r]
        self.assertEqual(rows, [GBATB17_ROW])                  # exactly one row, exactly this text
        block = build.split(zipout.DUPLICATE_HEADING, 1)[1].split("```")[1]
        self.assertEqual([r for r in block.splitlines() if r], [GBATB17_ROW])
        self.assertIn("identical to dos/GBATB17.SVF", build)
        for path in GBATB17_ROW.split("\t")[1].split(","):        # the row names a file the zip or svf/ holds
            self.assertTrue("svf/" + path in names or os.path.isfile(os.path.join(REPO_DIR, "svf", path)), path)
        self.assertIn("svf/new/acc/GOWUN.TXT", names)


@unittest.skipUnless(os.environ.get("SVF_MAKER_SLOW") == "1", "set SVF_MAKER_SLOW=1 for the 2 bpp fit (about 85 s)")
class SlowFitTest(unittest.TestCase):
    def test_experimental_2bpp_fit_reports_quality(self):
        src = os.path.join(REPO_DIR, "ttf", "nanumgothic")
        files = {"nanum/NanumGothic-Bold.ttf": _read(os.path.join(src, "NanumGothic-Bold.ttf")),
                 "nanum/OFL.txt": _read(os.path.join(src, "OFL.txt"))}

        def choose(fonts, st):
            inputkinds.select(st, inputkinds.only_font(fonts), dest="new/slow", bpp=(2,), kinds=["jamo"],
                              sizes=[16], experimental=True, layout="844")
        with tempfile.TemporaryDirectory(prefix="e2e-slow-") as tmp:
            job, z = inputkinds.run_batch(self, tmp, files, choose)
            self.assertEqual(job["state"], "done", job.get("error"))
            steps = [s for s in job["steps"] if s["kind"] == "jamo"]
            self.assertEqual(len(steps), 1, [(s["kind"], s["state"]) for s in job["steps"]])
            step = steps[0]
            self.assertEqual(step["state"], "done", step.get("error"))
            self.assertEqual(inputkinds.step_tools([step])[0], ["jamoset.py"], inputkinds.step_tools(job["steps"]))
            self.assertIsInstance(step.get("quality"), dict, "the experimental fit reported no quality")
            q = step["quality"]
            print("SLOWFIT quality", q, flush=True)
            self.assertEqual(q["compared"], 11172)
            self.assertGreater(q["all"], 0.0)
            self.assertLess(q["all"], 0.15)          # measured 0.0777 at 004a449 (0 is exact; 2 bpp mean level error)
            self.assertLess(q["ks2350"], 0.15)       # measured 0.0731
            inputkinds.assert_facecheck(self, z)
            self.assertIsNotNone(inputkinds.zip_face(z).jset)


if __name__ == "__main__":
    unittest.main()
