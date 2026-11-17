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
        assert status == 200, body
        cls.jid = jid = body["id"]
        status, body = api("PUT", "/api/jobs/%s/files?path=%s" % (jid, urllib.parse.quote("e2e.zip", safe="")),
                           body=e2efx.zip_tree(os.path.join(cls.scratch, "in")))
        assert status == 200, body
        status, body = api("POST", "/api/jobs/%s/detect" % jid)
        assert status == 200, body
        status, job = api("GET", "/api/jobs/%s" % jid)
        assert status == 200, job
        st, ids = e2efx.select_mixed(job)
        cls.role_of = {fid: role for role, fid in ids.items()}
        status, body = api("PUT", "/api/jobs/%s/settings" % jid, st)
        assert status == 200, body
        status, body = api("POST", "/api/jobs/%s/run" % jid)
        assert status == 200, body
        cls.job = cls.server.wait_done(jid)
        status, _h, data = cls.server.call("GET", "/api/jobs/%s/zip" % jid)
        assert status == 200, status
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
        self.assertEqual(self.job["state"], "done", self.job.get("error"))
        self.assertEqual(self.job["result"]["failed_steps"], [])
        self.assertTrue(all(s["state"] == "done" for s in self.job["steps"]))
        out = {}                                              # role -> [(kind, tools of that step)], in step order
        for s in self.job["steps"]:
            if s["kind"] in ("precomposed", "jamo"):
                out.setdefault(self.role_of[s["font"]], []).append((s["kind"], inputkinds.step_tools([s])[0]))
        self.assertEqual({r: [k for k, _ in v] for r, v in out.items()},
                         {"ttf": ["precomposed"], "bdf": ["precomposed"], "pcf": ["jamo"], "dos": ["jamo"],
                          "shipped": ["precomposed"]})          # exactly one output step per role
        # the landed tool sequences (t_df773bf5: a mkfont face ends with svf2to3); the copy of a shipped face runs none
        self.assertEqual(out["ttf"][0][1], ["mkfont.py", "svf2to3.py"])
        self.assertEqual(out["bdf"][0][1], ["mkfont.py", "svf2to3.py"])
        self.assertEqual(out["dos"][0][1], ["jamoset.py"])
        self.assertEqual(out["pcf"][0][1], ["jamoset.py"])     # its `srcprep.py pcf-bdf` is a separate source step
        self.assertEqual(out["shipped"][0][1], [])
        sources = [s for s in self.job["steps"] if s["kind"] == "source"]
        self.assertEqual([inputkinds.step_tools([s])[0] for s in sources], [["srcprep.py pcf-bdf"]])
        self.assertEqual(self.role_of[sources[0]["font"]], "pcf")

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
        for name in inputkinds.zip_faces(self.zip_path):
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
        assert status == 200, body
        cls.jid = jid = body["id"]
        status, body = api("PUT", "/api/jobs/%s/sources" % jid, {"paths": cls.tree["roots"]})
        assert status == 200, body
        status, body = api("POST", "/api/jobs/%s/detect" % jid)
        assert status == 200, body
        status, job = api("GET", "/api/jobs/%s" % jid)
        assert status == 200, job
        st, _ids = e2efx.select_mixed(job)
        status, body = api("PUT", "/api/jobs/%s/settings" % jid, st)
        assert status == 200, body
        status, body = api("POST", "/api/jobs/%s/run" % jid)
        assert status == 200, body
        cls.job = cls.server.wait_done(jid)
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

    def test_done_and_only_svf_and_build_written(self):
        self.assertEqual(self.job["state"], "done", self.job.get("error"))
        self.assertNotIn("zip", self.job["result"])
        files = self.job["result"]["files"]
        self.assertEqual(sorted(f for f in files if f.endswith(".SVF")),
                         sorted(s["written"] for s in self.job["steps"] if s.get("written")))
        self.assertEqual(len([f for f in files if f.endswith(".SVF")]), 4)
        self.assertTrue(all(f.startswith(("svf/dos/", "svf/jamo-extra/", "build-%s/" % self.jid)) for f in files))
        self.assertEqual(self.input_hashes_now(), self.input_hashes)       # the fonts were read in place, unchanged

    def test_tree_passes_facecheck(self):
        inputkinds.assert_facecheck_tree(self, self.out)

    def test_tree_passes_mkindex_on_its_own(self):
        e2efx.merge_check(self, os.path.join(self.out, "svf"), self.side, base_repo=False, scratch=self.merge_dir)

    def test_every_face_draws(self):
        for rel in (f for f in self.job["result"]["files"] if f.endswith(".SVF")):
            with self.subTest(face=rel):
                e2efx.assert_draws(self, os.path.join(self.out, rel))


if __name__ == "__main__":
    unittest.main()
