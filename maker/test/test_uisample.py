#!/usr/bin/env python3
"""Tests of `uisample.py` (t_30b843b8): the sample set of the desktop UI test, run through the HTTP API in-process (the
ground truth for its expected tree), and every check proved by a mutation."""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import copy
import json
import shutil
import struct
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import e2efx
import inputkinds
import jamoset
import localfx
import uisample
import wincompat

BASE = os.path.join(os.path.expanduser("~"), "work", "tmp", "svf-uisample-test-%d" % os.getpid())
UISAMPLE = os.path.join(TEST_DIR, "uisample.py")

# The 14 steps of the API run: (step kind, font path, tools of every argv of the step), sorted.
STEPS = sorted([
    ("precomposed", "neodgm.ttf", ["mkfont.py", "svf2to3.py"]),
    ("precomposed", "NanumGothic-Bold.ttf", ["mkfont.py", "svf2to3.py"]),
    ("precomposed", "GowunBatang-Bold.ttf", ["mkfont.py", "svf2to3.py"]),
    ("source", "Caveat-VF.ttf", ["-m fontTools.varLib.instancer"]),
    ("precomposed", "Caveat-VF.ttf", ["mkfont.py", "svf2to3.py"]),
    ("source", "Seoul12.rsrc", ["macfbit3.py"]),
    ("source", "InputBackSupport.rsrc", ["srcprep.py mac-htbl"]),
    ("jamo", "Seoul12.rsrc", ["macfbit_svf.py"]),
    ("jamo", "HAN24.FNT", ["jamoset.py"]),
    ("jamo", "johab.bdf", ["jamoset.py"]),
    ("precomposed", "ksc.bdf", ["bdfface.py"]),
    ("export", "ksc.bdf", ["svf2ttf.py"]),
    ("export", "ksc.bdf", ["svf2ttf.py"]),
    ("export", "johab.bdf", ["svf2ttf.py"]),
    ("jamo", "Munjo16.rsrc", ["jamoset.py"]),
    ("source", "Synth.dfont", ["macsfnt.py extract", "macsfnt.py unicode"]),
    ("precomposed", "Synth.dfont", ["mkfont.py", "svf2to3.py"]),
])


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def _write(path, data):
    with open(path, "wb") as fh:
        fh.write(data)


def _snapshot(*dirs):
    """{path: st_mtime_ns} of every file under @p dirs: a rewritten file shows as a change, not only a new name."""
    out = {}
    for top in dirs:
        for dirpath, _dirs, names in os.walk(top):
            for name in names:
                path = os.path.join(dirpath, name)
                out[path] = os.stat(path).st_mtime_ns
    return out


class UiSampleTest(wincompat.SlashEqual, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shutil.rmtree(BASE, ignore_errors=True)
        os.makedirs(BASE)
        cls.server = None
        try:
            cls._run()
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def _run(cls):
        cls.dir = os.path.join(BASE, "class")
        cls.sample = uisample.make(cls.dir)
        cls.out = cls.sample["output"]
        cls.server = e2efx.Server(os.path.join(BASE, "data"), token=localfx.TOKEN)
        api = cls.server.api

        def need(ok, what):
            if not ok:
                raise AssertionError(what)
        status, body = api("POST", "/api/jobs", {"source": "local", "output_dir": cls.out})
        need(status == 200, body)
        cls.jid = jid = body["id"]
        status, body = api("PUT", "/api/jobs/%s/sources" % jid, {"paths": [e["path"] for e in cls.sample["dialog"]]})
        need(status == 200, body)
        status, body = api("POST", "/api/jobs/%s/detect" % jid)
        need(status == 200, body)
        status, job = api("GET", "/api/jobs/%s" % jid)
        need(status == 200, job)
        status, body = api("PUT", "/api/jobs/%s/settings" % jid, uisample.apply_ui(job))
        need(status == 200, body)
        status, body = api("POST", "/api/jobs/%s/run" % jid)
        need(status == 200, body)
        cls.job = cls.server.wait_done(jid)
        deadline = time.monotonic() + 10                  # the end-of-run sweep of `.svf-maker-<id>/`, bounded
        while time.monotonic() < deadline:
            if not any(p.startswith(".svf-maker-") for p in uisample._walk_rel(cls.out)):
                break
            time.sleep(0.1)
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server", None):
            cls.server.stop()
        shutil.rmtree(BASE, ignore_errors=True)

    # ---- helpers -----------------------------------------------------------------------------------------------

    def mutated(self, mutate, job=None, same_as=None, notes=None):
        """Check a copy of the class run's output after @p mutate(out_dir); returns the failure lines."""
        type(self).n += 1
        d = os.path.join(BASE, "m%d" % self.n)
        out = os.path.join(d, "out")
        shutil.copytree(self.out, out)
        mutate(out)
        return uisample.check(self.sample, out, job or self.job, same_as=same_as, notes=notes)

    def assertNames(self, lines, *needles):
        for needle in needles:
            self.assertTrue(any(needle in ln for ln in lines), "no failure line names %s: %s" % (needle, lines))

    # ---- tests -------------------------------------------------------------------------------------------------

    def test_make_builds_the_synthetic_tree(self):
        s = self.sample
        base = os.path.join(self.dir, "in")
        sizes = {"mac/Seoul12.rsrc": None, "mac/InputBackSupport.rsrc": None, "mac/Suitcase.rsrc": None,
                 "mac/LICENSE.txt": None, "v1/Munjo16.rsrc": None, "v1/LICENSE.txt": None, "dfont/Synth.dfont": None,
                 "hwp/HAN24.FNT": 25920, "hwp/ASCII.PFT": None, "hwp/HANGUL24.PFT": 40000, "hwp/LICENSE.txt": None,
                 "bdf/ksc.bdf": None, "bdf/latin.bdf": None, "bdf/johab.bdf": None, "bdf/LICENSE.txt": None}
        self.assertEqual(uisample._walk_rel(base), set(sizes))
        for rel, size in sizes.items():
            path = os.path.join(base, rel)
            self.assertGreater(os.path.getsize(path), 0, rel)
            if size is not None:
                self.assertEqual(os.path.getsize(path), size, rel)
        self.assertEqual(_read(os.path.join(base, "mac", "LICENSE.txt")).decode(), uisample.fixtures.SIL_LICENCE)
        self.assertEqual(json.loads(_read(os.path.join(self.dir, "sample.json"))), s)
        self.assertEqual([(e["button"], os.path.relpath(e["path"], self.dir) if e["path"].startswith(self.dir)
                           else os.path.relpath(e["path"], uisample.REPO)) for e in s["dialog"]],
                         [("choose-folder", "ttf/neodgm"), ("choose-folder", "ttf/nanumgothic"),
                          ("choose-folder", "ttf/gowunbatang"), ("choose-folder", "ttf/caveat"),
                          ("choose-folder", "in/mac"), ("choose-folder", "in/v1"), ("choose-folder", "in/hwp"),
                          ("choose-folder", "in/bdf"), ("choose-files", "in/dfont/Synth.dfont")])
        self.assertEqual(len(s["dialog"]), 9)
        for e in s["dialog"]:
            self.assertTrue(os.path.isabs(e["path"]) and os.path.exists(e["path"]), e)
        for e in s["dialog"][:4]:
            self.assertTrue(e["path"].startswith(os.path.join(uisample.REPO, "ttf") + os.sep), e)
        self.assertEqual(s["output"], os.path.join(self.dir, "out"))
        self.assertEqual(s["faces"], 10)
        self.assertEqual(sorted(s["fonts"]), sorted(uisample.FACES))
        self.assertEqual(s["untick"], ["NanumGothic-Regular.ttf", "latin.bdf"])
        self.assertEqual(s["not_read"], ["HANGUL24.PFT"])
        self.assertEqual(s["inputs"], uisample.hashes([e["path"] for e in s["dialog"]]))
        with self.assertRaises(FileExistsError):                 # a non-empty directory is refused
            uisample.make(self.dir)
        self.assertEqual(json.loads(_read(os.path.join(self.dir, "sample.json"))), s)

    def test_api_run_writes_exactly_the_expected_tree(self):
        self.maxDiff = None
        self.assertEqual(len(uisample.EXPECTED), 36)
        self.assertEqual(len(uisample.FACES), 10)
        self.assertEqual(self.job["state"], "done", self.job.get("error"))
        self.assertEqual(self.job["result"]["failed_steps"], [])
        notes = []
        self.assertEqual(uisample.check(self.sample, self.out, self.job, notes=notes), [])
        self.assertEqual(notes, [])
        self.assertEqual(uisample._walk_rel(self.out), uisample.expected_files(self.jid))
        path_of = {f["id"]: f["path"] for f in self.job["fonts"]}
        steps = sorted((s["kind"], path_of[s["font"]], t)
                       for s, t in zip(self.job["steps"], inputkinds.step_tools(self.job["steps"])))
        self.assertEqual(len(steps), 17)
        self.assertEqual([s["name"] for s in self.job["steps"] if s.get("composite")], ["JOHA16J.ttf"])
        self.assertEqual(steps, STEPS)
        self.assertTrue(all(s["state"] == "done" for s in self.job["steps"]))
        self.assertEqual(sorted(s["written"] for s in self.job["steps"] if s.get("written")),
                         sorted(list(uisample.FACES.values()) + [e for _f, e in uisample.EXPORTS.values()]))

    def test_check_flags_a_missing_face(self):
        gone = ("svf/jamo-extra/MUNJ16J.SVF", "svf/jamo-extra/MUNJO.TXT", "svf/jamo-extra/OFLMUNJO.TXT")

        def mutate(out):
            for rel in gone:
                os.remove(os.path.join(out, rel))
        lines = self.mutated(mutate)
        for rel in gone:
            self.assertIn("files: missing " + rel, lines)

    def test_check_flags_an_extra_file(self):
        def mutate(out):
            shutil.copyfile(os.path.join(out, "svf/dos/NEODU16.SVF"), os.path.join(out, "svf/dos/STRAY.SVF"))
        self.assertIn("files: unexpected svf/dos/STRAY.SVF", self.mutated(mutate))

    def test_check_flags_a_leftover_work_dir(self):
        def mutate(out):
            os.makedirs(os.path.join(out, ".svf-maker-%s" % self.jid))
            _write(os.path.join(out, ".svf-maker-%s" % self.jid, "x"), b"x")
        self.assertIn("files: work folder not swept: .svf-maker-%s" % self.jid, self.mutated(mutate))

    def test_check_flags_an_empty_leftover_work_dir(self):
        def mutate(out):
            os.makedirs(os.path.join(out, ".svf-maker-%s" % self.jid))       # a directory, no file in it
        lines = self.mutated(mutate)
        self.assertIn("files: work folder not swept: .svf-maker-%s" % self.jid, lines)

    def test_check_flags_a_changed_input(self):
        d = os.path.join(BASE, "second")
        sample = uisample.make(d)
        target = os.path.join(d, "in", "hwp", "ASCII.PFT")
        with open(target, "ab") as fh:
            fh.write(b"\0")
        shutil.copytree(self.out, os.path.join(BASE, "m-input", "out"))
        lines = uisample.check(sample, os.path.join(BASE, "m-input", "out"), self.job)
        self.assertNames(lines, "ASCII.PFT")
        self.assertEqual([ln for ln in lines if not ln.startswith("inputs:")], [])

    def test_check_flags_a_corrupt_face(self):
        def mutate(out):
            path = os.path.join(out, "svf/dos/KSC16.SVF")
            _write(path, _read(path)[:100])
        lines = self.mutated(mutate)
        self.assertTrue(any(ln.startswith("parse: svf/dos/KSC16.SVF") for ln in lines), lines)
        self.assertTrue(any(ln.startswith("facecheck:") for ln in lines), lines)
        # each check catches it alone: with the parse check disabled the facecheck line is still there
        with mock.patch.object(uisample, "_check_parse", lambda out, fails: None):
            lines = self.mutated(mutate)
        self.assertFalse(any(ln.startswith("parse:") for ln in lines), lines)
        self.assertTrue(any(ln.startswith("facecheck:") for ln in lines), lines)
        # and with the facecheck disabled the parse line is still there
        with mock.patch.object(uisample, "_check_facecheck", lambda out, scratch: None):
            lines = self.mutated(mutate)
        self.assertFalse(any(ln.startswith("facecheck:") for ln in lines), lines)
        self.assertTrue(any(ln.startswith("parse: svf/dos/KSC16.SVF") for ln in lines), lines)

    def test_check_flags_a_step_that_wrote_nothing(self):
        job = copy.deepcopy(self.job)
        hit = [s for s in job["steps"] if s.get("written") == "svf/dos/KSC16.SVF"]
        self.assertEqual(len(hit), 1)
        del hit[0]["written"]
        lines = self.mutated(lambda out: None, job=job)
        self.assertIn("files: no step wrote svf/dos/KSC16.SVF", lines)

    def test_check_flags_a_job_files_list_that_disagrees_with_the_disk(self):
        job = copy.deepcopy(self.job)
        job["result"]["files"].remove("svf/dos/KSC.TXT")
        job["result"]["files"].append("svf/dos/BOGUS.SVF")
        lines = self.mutated(lambda out: None, job=job)
        self.assertIn("files: on disk but not reported by the job: svf/dos/KSC.TXT", lines)
        self.assertIn("files: reported by the job but not on disk: svf/dos/BOGUS.SVF", lines)

    def test_check_flags_an_export_that_misses_a_glyph(self):
        def mutate(out):
            path = os.path.join(out, "svf/dos/KSC16.bdf")
            text = _read(path).decode("utf-8")
            start = text.index("STARTCHAR uniAC00")
            _write(path, (text[:start] + text[text.index("ENDCHAR", start) + 8:]).encode("utf-8"))
        self.assertTrue(any(ln.startswith("export: svf/dos/KSC16.bdf") for ln in self.mutated(mutate)))

    def test_same_as_ignores_ttf_timestamps_only(self):
        other = tempfile.mkdtemp(prefix="uisample-other-", dir=os.path.dirname(self.out))
        self.addCleanup(shutil.rmtree, other, True)
        shutil.copytree(self.out, other, dirs_exist_ok=True)
        from fontTools.ttLib import TTFont
        ttf = os.path.join(other, "svf/dos/KSC16.ttf")
        with TTFont(ttf, recalcTimestamp=False) as font:
            font["head"].created += 1000
            font.save(ttf + ".new")
        os.replace(ttf + ".new", ttf)
        self.assertEqual([ln for ln in self.mutated(lambda out: None, same_as=other) if "KSC16" in ln], [])
        with TTFont(ttf, recalcTimestamp=False) as font:
            font["head"].fontRevision = 2.0
            font.save(ttf + ".new")
        os.replace(ttf + ".new", ttf)
        self.assertIn("same-as: svf/dos/KSC16.ttf differs from %s (beyond its timestamps)" % os.path.realpath(other),
                      self.mutated(lambda out: None, same_as=other))

    def test_check_flags_a_job_that_is_not_done(self):
        lines = self.mutated(lambda out: None, job=dict(self.job, state="failed"))
        self.assertIn("files: job state is failed, not done", lines)

    def test_check_flags_a_blank_latin_only_face(self):
        def mutate(out):
            path = os.path.join(out, "svf/dos/CAVEA16.SVF")
            data = bytearray(_read(path))
            h = struct.unpack_from(jamoset.HEADER3, data)
            data[h[15]:h[15] + h[16]] = bytes(h[16])
            _write(path, bytes(data))
            self.assertEqual(jamoset.parse_svfn(_read(path)).version, 3)
            self.assertFalse(jamoset.parse_svfn(_read(path)).glyphs.get(0xAC00))      # Latin only: the `A` branch
        lines = self.mutated(mutate)
        self.assertIn("ink: svf/dos/CAVEA16.SVF draws a blank U+0041", lines)

    def test_check_flags_a_gbatb17_mismatch(self):
        def mutate(out):
            path = os.path.join(out, "svf/dos/GOWUN17A.SVF")
            data = bytearray(_read(path))
            data[200] ^= 0x01                                  # past the 48 byte header
            _write(path, bytes(data))
        self.assertNames(self.mutated(mutate), "GBATB17")

    def test_check_flags_a_blank_face(self):
        def mutate(out):
            path = os.path.join(out, "svf/jamo-extra/JOHA16J.SVF")
            data = bytearray(_read(path))
            h = struct.unpack_from(jamoset.HEADER3, data)
            data_off, data_size = h[15], h[16]
            self.assertGreater(data_size, 0)
            data[data_off:data_off + data_size] = bytes(data_size)
            _write(path, bytes(data))
            self.assertEqual(jamoset.parse_svfn(_read(path)).version, 3)       # still a v3 face
        lines = self.mutated(mutate)
        self.assertTrue(any("JOHA16J.SVF" in ln and "blank" in ln for ln in lines), lines)

    def test_check_flags_a_missing_faces_row(self):
        def mutate(out):
            path = os.path.join(out, "build-%s" % self.jid, "FACES.TSV.lines")
            kept = [ln for ln in _read(path).decode().splitlines() if "JOHA16J.SVF" not in ln]
            self.assertEqual(len(kept), len(_read(path).decode().splitlines()) - 1)
            _write(path, ("\n".join(kept) + "\n").encode())
        lines = self.mutated(mutate)
        self.assertTrue(any(ln.startswith("mkindex:") and "JOHA16J.SVF" in ln for ln in lines), lines)

    def test_cli_make_and_check(self):
        py = [sys.executable, "-B", "-P", UISAMPLE]
        repo = uisample.REPO
        before = _snapshot(os.path.join(repo, "maker"), os.path.join(repo, "tools"), os.path.join(repo, "web"),
                           os.path.join(repo, "ttf"))
        d = os.path.join(BASE, "cli")
        r = subprocess.run(py + ["make", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        made = json.loads(r.stdout)
        self.assertEqual(set(made), {"dialog", "output", "fonts", "untick", "not_read", "faces", "inputs"})
        self.assertEqual(len(made["dialog"]), 9)
        self.assertEqual(made["output"], os.path.join(d, "out"))
        self.assertEqual(os.listdir(made["output"]), [])
        self.assertEqual(json.loads(_read(os.path.join(d, "sample.json"))), made)
        # the class run's tree, checked through the CLI against the CLI's own directory
        shutil.rmtree(os.path.join(d, "out"))
        shutil.copytree(self.out, os.path.join(d, "out"))
        job_json = os.path.join(d, "job.json")
        _write(job_json, json.dumps(self.job).encode())
        r = subprocess.run(py + ["check", d, job_json], capture_output=True, text=True)
        self.assertEqual((r.returncode, json.loads(r.stdout)), (0, {"ok": True, "notes": []}), r.stderr)
        self.assertEqual(os.listdir(d).count("check"), 0)                 # the scratch is gone
        # a mutated copy
        os.remove(os.path.join(d, "out", "svf", "dos", "KSC16.SVF"))
        r = subprocess.run(py + ["check", d, job_json], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stderr)
        body = json.loads(r.stdout)
        self.assertFalse(body["ok"])
        self.assertTrue(any("KSC16.SVF" in ln for ln in body["failures"]), body)
        # a job without a result: no traceback, `job has no result` plus the missing files
        shutil.rmtree(os.path.join(d, "out"))
        os.makedirs(os.path.join(d, "out"))
        bare = dict(self.job, result=None)
        _write(job_json, json.dumps(bare).encode())
        r = subprocess.run(py + ["check", d, job_json], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        body = json.loads(r.stdout)
        self.assertTrue(any("job has no result" in ln for ln in body["failures"]), body)
        self.assertTrue(any("missing svf/dos/CAVEA16.SVF" in ln for ln in body["failures"]), body)
        # --same-as: JOHA16J differs -> exit 1; NEODU16 differs -> exit 0 with a note naming it
        shutil.rmtree(os.path.join(d, "out"))
        shutil.copytree(self.out, os.path.join(d, "out"))
        _write(job_json, json.dumps(self.job).encode())
        other = os.path.join(BASE, "other")
        shutil.copytree(self.out, other)
        r = subprocess.run(py + ["check", d, job_json, "--same-as", other], capture_output=True, text=True)
        self.assertEqual((r.returncode, json.loads(r.stdout)), (0, {"ok": True, "notes": []}), r.stderr)
        for rel, ok in (("svf/jamo-extra/JOHA16J.SVF", False), ("svf/dos/NEODU16.SVF", True)):
            path = os.path.join(other, rel)
            data = bytearray(_read(path))
            data[-1] ^= 0xFF
            _write(path, bytes(data))
            r = subprocess.run(py + ["check", d, job_json, "--same-as", other], capture_output=True, text=True)
            body = json.loads(r.stdout)
            if ok:
                self.assertEqual(r.returncode, 0, r.stdout)
                self.assertTrue(any("NEODU16.SVF" in n for n in body["notes"]), body)
            else:
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertTrue(any("JOHA16J.SVF" in ln for ln in body["failures"]), body)
                shutil.copyfile(os.path.join(self.out, rel), path)
        # the refusal: a directory under /tmp, nothing created (the TMP_DIR rule of the POSIX hosts; Windows has no /tmp)
        refused = "/tmp/uisample-refused-%d" % os.getpid()
        if not wincompat.WIN:
            self.assertFalse(os.path.exists(refused))
            r = subprocess.run(py + ["make", refused], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertIn("refusing a directory under /tmp", r.stderr)
            self.assertFalse(os.path.exists(refused))
        # nothing written outside DIR by the subprocesses (no `__pycache__` either)
        after = _snapshot(os.path.join(repo, "maker"), os.path.join(repo, "tools"), os.path.join(repo, "web"),
                          os.path.join(repo, "ttf"))
        self.assertEqual(sorted(set(after) - set(before)), [])                 # no new file (no `__pycache__`)
        self.assertEqual(sorted(p for p in before if after.get(p) != before[p]), [])     # none rewritten either

    def test_cli_check_refuses_unreadable_input(self):
        py = [sys.executable, "-B", "-P", UISAMPLE]
        d = os.path.join(BASE, "cli-bad")
        r = subprocess.run(py + ["make", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        job_json = os.path.join(d, "job.json")

        def run(*extra):
            r = subprocess.run(py + ["check", d, job_json] + list(extra), capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, (r.stdout, r.stderr))
            self.assertNotIn("Traceback", r.stderr)
            self.assertEqual(r.stdout, "")
            self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
            return r.stderr
        self.assertIn("cannot read", run())                                   # no job JSON
        _write(job_json, b"{not json")
        self.assertIn("cannot read", run())                                   # invalid JSON
        _write(job_json, b"[1]")
        self.assertIn("cannot read", run())                                   # not an object
        _write(job_json, json.dumps(self.job).encode())
        os.rename(os.path.join(d, "sample.json"), os.path.join(d, "sample.json.bak"))
        self.assertIn("cannot read", run())                                   # no sample.json
        _write(os.path.join(d, "sample.json"), b"")
        self.assertIn("cannot read", run())                                   # empty sample.json
        # sample.json that names another output folder: refused, the other folder is never read
        sample = json.loads(_read(os.path.join(d, "sample.json.bak")))
        sample["output"] = self.out
        _write(os.path.join(d, "sample.json"), json.dumps(sample).encode())
        self.assertIn("other than DIR/out", run())
        sample["output"] = os.path.join(d, "out")                             # the right one passes the guard
        _write(os.path.join(d, "sample.json"), json.dumps(sample).encode())
        r = subprocess.run(py + ["check", d, job_json], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, (r.stdout, r.stderr))               # an empty out: failures, not a refusal


if __name__ == "__main__":
    unittest.main()
