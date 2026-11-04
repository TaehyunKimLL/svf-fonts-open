#!/usr/bin/env python3
"""Helpers for the end-to-end tests of the maker's new input kinds (t_f3ef3189).

`run_batch` runs the maker's own path in-process (store, upload, detect.scan, settings, plan_steps, Worker.run_job, no
thread) on files built inside the test; `assert_facecheck` is the plan's definition of "the output zip passes
facecheck.py" (facecheck.py has no zip mode).
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import subprocess
import tempfile
import zipfile

import detect
import fixtures
import jamoset
import jobs
import naming
import settings

SVF = os.path.join(REPO_DIR, "svf")
TOOLS = os.path.join(REPO_DIR, "tools")
LICENCE = fixtures.SIL_LICENCE


def fid_of(fonts, face=None, path=None, kind=None):
    """The id of the one font entry with that face index / path / source kind (an AssertionError for none or many)."""
    hits = [f["id"] for f in fonts if (face is None or f["face_index"] == face)
            and (path is None or f["path"] == path) and (kind is None or f["source_kind"] == kind)]
    assert len(hits) == 1, (face, path, kind, hits)
    return hits[0]


def only_font(fonts):
    """The id of the one font entry that is not a licence or list file (an AssertionError for none or many)."""
    hits = [f["id"] for f in fonts if f["format"] not in ("licence", "list")]
    assert len(hits) == 1, hits
    return hits[0]


def select(settings_, fid, dest="new/inputs", bpp=(1,), **per):
    """Select font @p fid for @p dest at @p bpp (a list); the other keys of @p per are set as given."""
    settings_["fonts"][fid].update(selected=True, dest=dest, bpp=list(bpp), **per)


def plan_batch(test, tmp, files, choose, caps=None, pylib=None):
    """The first half of `run_batch`: upload, scan, choose, validate and plan; returns (store, job) with the steps
    planned (state `queued`) and nothing run."""
    store = jobs.Store(tmp)
    job = store.create()
    job_dir = store.path(job["id"])
    upload = os.path.join(job_dir, "upload")
    files = dict(files)
    for folder in {os.path.dirname(rel) for rel in files}:
        files.setdefault(os.path.join(folder, "LICENSE.txt") if folder else "LICENSE.txt", LICENCE.encode())
    for rel, data in files.items():
        path = os.path.join(upload, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data if isinstance(data, bytes) else data.encode())
    fonts = detect.scan(upload)
    for font in fonts:                               # the server stamps this on every read of the fonts
        if (caps or {}).get("mask_libs") and font.get("source_kind") in ("outline", "outline-composite"):
            font["mask_ok"] = True
    st = settings.defaults(fonts)
    for per in st["fonts"].values():                 # a batch plans only what its test chooses
        per["selected"] = False
    choose(fonts, st)
    test.assertEqual(settings.validate(fonts, st, upload), [])
    test.assertEqual(settings.run_ready(fonts, st, naming.RepoIndex(SVF), upload), [])
    job.update(state="queued", fonts=fonts, settings=st)
    job["steps"] = settings.plan_steps(job, job_dir, TOOLS, upload, pylib=pylib)
    store.save(job)
    return store, job


def run_batch(test, tmp, files, choose):
    """Upload @p files (rel path -> bytes) under a job in @p tmp, scan, choose, plan and run; (job, zip path or None).

    Every font starts unselected. A `LICENSE.txt` is put beside the fonts of every folder that has none. `choose(fonts, settings)` edits the
    settings in place; the result must validate and be run-ready. The worker runs `run_job` on the calling thread.
    """
    store, job = plan_batch(test, tmp, files, choose)
    jobs.Worker(store, REPO_DIR, SVF, TOOLS).run_job(job["id"])
    job = store.load(job["id"])
    result = job.get("result")
    return job, (store.path(job["id"], result["zip"]) if result else None)


def step_tools(steps):
    """Per step, per argv: the script's base name (plus the subcommand for srcprep.py / macsfnt.py), or `-m module`."""
    out = []
    for step in steps:
        names = []
        for argv in step["argv"]:
            if argv[2] == "-m":
                names.append("-m " + argv[3])
            elif os.path.basename(argv[2]) in ("srcprep.py", "macsfnt.py"):
                names.append("%s %s" % (os.path.basename(argv[2]), argv[3]))
            else:
                names.append(os.path.basename(argv[2]))
        out.append(names)
    return out


def zip_faces(zip_path):
    """{zip entry name: bytes} of every `svf/**/*.SVF` in the zip."""
    with zipfile.ZipFile(zip_path) as zf:
        return {n: zf.read(n) for n in zf.namelist() if n.startswith("svf/") and n.lower().endswith(".svf")}


def zip_face(zip_path):
    """The parsed single face of the zip."""
    faces = zip_faces(zip_path)
    assert len(faces) == 1, sorted(faces)
    return jamoset.parse_svfn(next(iter(faces.values())))


def assert_facecheck(test, zip_path):
    """The zip passes facecheck.py: extract, commit, `manifest` and `verify` exit 0, every SVF parses as version 3."""
    test.assertIsNotNone(zip_path)
    with tempfile.TemporaryDirectory(prefix="inputkinds-fc-") as d:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(d)
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
        for argv in (["git", "init", "-q"], ["git", "add", "-A"], git + ["commit", "-q", "-m", "x"]):
            r = subprocess.run(argv, cwd=d, capture_output=True, text=True)
            test.assertEqual(r.returncode, 0, r.stderr)
        facecheck = os.path.join(TOOLS, "facecheck.py")
        manifest = os.path.join(d, "..", os.path.basename(d) + ".tsv")
        r = subprocess.run([sys.executable, "-I", facecheck, "manifest", "--git", d, "--rev", "HEAD", "--path", "svf",
                            "-o", manifest], capture_output=True, text=True)
        test.assertEqual(r.returncode, 0, r.stderr)
        with open(manifest) as fh:
            test.assertGreaterEqual(len([line for line in fh if line.strip()]), 1)
        r = subprocess.run([sys.executable, "-I", facecheck, "verify", manifest], cwd=d, capture_output=True, text=True)
        os.remove(manifest)
        test.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        faces = 0
        for root, _dirs, names in os.walk(os.path.join(d, "svf")):
            for name in names:
                if name.lower().endswith(".svf"):
                    with open(os.path.join(root, name), "rb") as fh:
                        test.assertEqual(jamoset.parse_svfn(fh.read()).version, 3)
                    faces += 1
        test.assertGreaterEqual(faces, 1)
