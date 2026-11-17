#!/usr/bin/env python3
"""Fixtures and checks for the end-to-end tests (t_e073891a): the mixed test folder (TTF + BDF + johab PCF + DOS raw
844 + one shipped SVF), a thread server with an HTTP helper, the role-based selection, and the three checks (the
owner's merge + `mkindex --check`, svfline draws; facecheck is `inputkinds.assert_facecheck(_tree)`).

Everything is synthetic or copied from `ttf/` and `svf/` of this repository (OFL only).
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import http.client
import json
import shutil
import subprocess
import threading
import time
import zipfile

import fixtures
import inputfx
import server
import svfline
import zipout

E2E_WAIT_S = 300

ROLES = {"outline": "ttf", "bdf-iso10646": "bdf", "bdf-johab": "pcf", "dos-raw": "dos", "svf-precomposed": "shipped"}


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def _copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)


def mixed_tree(root, shipped=False):
    """The mixed folder under @p root (new or empty); returns `{"roots": [...], "ttf", "bdf", "pcf", "dos_raw",
    "dos_eng"}` (+ `"shipped"` with @p shipped)."""
    root = os.path.realpath(root)
    os.makedirs(root, exist_ok=True)
    assert not os.listdir(root), root
    d = {name: os.path.join(root, name) for name in ("nanum", "bdf", "pcf", "dos", "shipped")}
    out = {"roots": [d["nanum"], d["bdf"], d["pcf"], d["dos"]]}
    nanum = os.path.join(REPO_DIR, "ttf", "nanumgothic")
    out["ttf"] = os.path.join(d["nanum"], "NanumGothic-Bold.ttf")
    _copy(os.path.join(nanum, "NanumGothic-Bold.ttf"), out["ttf"])
    _copy(os.path.join(nanum, "OFL.txt"), os.path.join(d["nanum"], "OFL.txt"))
    os.makedirs(d["bdf"])
    out["bdf"] = os.path.join(d["bdf"], "iso.bdf")
    fixtures._bdf(out["bdf"], fixtures._iso_glyphs(), 16, 13, 3, "ISO10646", (16, 16))
    out["pcf"] = os.path.join(d["pcf"], "johab.pcf")
    _write(out["pcf"], inputfx.pcf([(c, rows, 16) for c, _w, _h, _x, _y, rows in fixtures._johab_glyphs()],
                                   "johab", "1", 16, 13, 3))
    os.makedirs(d["dos"])
    out["dos_raw"] = os.path.join(d["dos"], "HAN.FNT")
    out["dos_eng"] = os.path.join(d["dos"], "ENG.FNT")
    fixtures._dos_raw(out["dos_raw"])
    fixtures._eng(out["dos_eng"])
    for name in ("bdf", "pcf", "dos"):
        _write(os.path.join(d[name], "LICENSE.txt"), fixtures.SIL_LICENCE)
    if shipped:
        for name in ("NEODG16.SVF", "NEODGM.TXT", "OFL.TXT"):
            _copy(os.path.join(REPO_DIR, "svf", "dos", name), os.path.join(d["shipped"], name))
        out["shipped"] = os.path.join(d["shipped"], "NEODG16.SVF")
        out["roots"].append(d["shipped"])
    return out


def zip_tree(root):
    """A deflated zip (bytes) of every file under @p root, members relative to @p root."""
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for name in sorted(filenames):
                path = os.path.join(dirpath, name)
                zf.write(path, os.path.relpath(path, root).replace(os.sep, "/"))
    return buf.getvalue()


def select_mixed(job):
    """`(settings, {role: font id})` for a detected @p job: every font unselected, then one choice per role."""
    st = job["settings"]
    by_role = {}
    for font in job["fonts"]:
        role = ROLES.get(font["source_kind"])
        if role:
            by_role.setdefault(role, []).append(font["id"])
    want = {"ttf", "bdf", "pcf", "dos"} | ({"shipped"} if "shipped" in by_role else set())
    assert set(by_role) == want, by_role
    for role, ids in by_role.items():
        assert len(ids) == 1, (role, ids)
    ids = {role: v[0] for role, v in by_role.items()}
    for per in st["fonts"].values():
        per["selected"] = False
    st["fonts"][ids["ttf"]].update(selected=True, kinds=["precomposed"], sizes=[20], bpp=[1], range="2350", dest="dos")
    st["fonts"][ids["bdf"]].update(selected=True, kinds=["precomposed"], sizes=[16], bpp=[1], dest="dos")
    st["fonts"][ids["pcf"]].update(selected=True, kinds=["jamo"], bpp=[1], dest="jamo-extra")
    st["fonts"][ids["dos"]].update(selected=True, kinds=["jamo"], dos_layout="844", bpp=[1], dest="jamo-extra")
    if "shipped" in ids:
        st["fonts"][ids["shipped"]].update(selected=True, kinds=["precomposed"], bpp=[1], dest="new/e2e")
    return st, ids


class Server:
    """A thread server over @p data_dir (local mode with a @p token), with an HTTP helper."""

    def __init__(self, data_dir, token=None):
        self.token = token
        self.srv = server.make_server("127.0.0.1", 0, REPO_DIR, data_dir, token=token)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def call(self, method, path, obj=None, body=None):
        if obj is not None:
            body = json.dumps(obj).encode("utf-8")
        headers = {"X-Maker-Token": self.token} if self.token else {}
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=E2E_WAIT_S)
        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()

    def api(self, method, path, obj=None, body=None):
        status, _h, data = self.call(method, path, obj, body)
        try:
            return status, json.loads(data)
        except ValueError:
            return status, data

    def wait_done(self, jid, timeout=E2E_WAIT_S):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _s, job = self.api("GET", "/api/jobs/%s" % jid)
            if job["state"] in ("done", "failed") and not self.srv.worker.owns(jid):
                return job
            if job["state"] not in ("queued", "running", "done", "failed"):
                raise AssertionError("job %s is in state %r" % (jid, job["state"]))
            time.sleep(0.1)
        raise AssertionError("job %s did not finish in %s s" % (jid, timeout))

    def stop(self):
        deadline = time.monotonic() + 30
        for item in self.srv.store.list():
            while time.monotonic() < deadline and self.srv.worker.cancel(item["id"]) != "not running":
                time.sleep(0.05)
        self.srv.shutdown()
        self.srv.worker.stop()
        self.srv.server_close()
        self.thread.join(30)


def _tsv_lines(data):
    return [ln for ln in data.decode("utf-8").splitlines() if ln.strip()]


def merge_check(test, svf_dir, lines, base_repo, scratch):
    """The owner's merge of a run, then `web/mkindex.py --check`. See the plan (Task 1) for the exact steps."""
    scratch = os.path.realpath(scratch)
    os.makedirs(scratch, exist_ok=True)
    merged = os.path.join(scratch, "svf")
    repo_svf = os.path.join(REPO_DIR, "svf")
    if base_repo:
        shutil.copytree(repo_svf, merged)
        for dirpath, _dirs, files in os.walk(svf_dir):
            for name in files:
                src = os.path.join(dirpath, name)
                dst = os.path.join(merged, os.path.relpath(src, svf_dir))
                test.assertFalse(os.path.exists(dst), "the run would overwrite %s" % dst)
                _copy(src, dst)
    else:
        shutil.copytree(svf_dir, merged)
    block = lines["BUILD.md"].decode("utf-8").split(zipout.DUPLICATE_HEADING, 1)[1].split("```")[1]
    drop = {ln for ln in block.splitlines() if ln.strip()}
    kept = [ln for ln in _tsv_lines(lines["LICENCES.tsv.lines"]) if ln not in drop]
    with open(os.path.join(REPO_DIR, "web", "LICENCES.tsv"), encoding="utf-8") as fh:
        base_lic = fh.read()
    with open(os.path.join(REPO_DIR, "web", "FAMILIES.tsv"), encoding="utf-8") as fh:
        base_fam = fh.read()
    lic = (base_lic if base_repo else "") + ("" if not base_repo or base_lic.endswith("\n") else "\n") \
        + "".join(ln + "\n" for ln in kept)
    fam_head = base_fam if base_repo else base_fam.splitlines()[0] + "\n"
    fam = fam_head + ("" if fam_head.endswith("\n") else "\n") \
        + "".join(ln + "\n" for ln in _tsv_lines(lines["FAMILIES.tsv.lines"]))
    lic_path, fam_path = os.path.join(scratch, "LICENCES.tsv"), os.path.join(scratch, "FAMILIES.tsv")
    _write(lic_path, lic)
    _write(fam_path, fam)
    faces_path = os.path.join(merged, "jamo-extra", "FACES.TSV")
    with open(os.path.join(repo_svf, "jamo-extra", "FACES.TSV"), encoding="utf-8") as fh:
        repo_faces = fh.read().splitlines(True)
    if base_repo:
        faces = "".join(repo_faces)
    else:
        head = [ln for ln in repo_faces if ln.startswith("#")]
        head.append(next(ln for ln in repo_faces if not ln.startswith("#")))     # the column header row
        faces = "".join(head)
    if faces and not faces.endswith("\n"):
        faces += "\n"
    faces += "".join(ln + "\n" for ln in _tsv_lines(lines["FACES.TSV.lines"]))
    _write(faces_path, faces)
    r = subprocess.run([sys.executable, "-I", os.path.join(REPO_DIR, "web", "mkindex.py"), merged, "--check",
                        "--licences", lic_path, "--families", fam_path], capture_output=True, text=True)
    test.assertEqual(r.returncode, 0, "mkindex --check: %s" % r.stderr[-2000:])
    # mkindex only reads FACES.TSV for labels, so check here that every jamo face of the run has its row
    import importlib.util
    spec = importlib.util.spec_from_file_location("e2e_mkindex", os.path.join(REPO_DIR, "web", "mkindex.py"))
    mk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mk)
    rows = mk.read_faces_tsv(faces_path)
    jamo_dir = os.path.join(svf_dir, "jamo-extra")
    mine = sorted(n for n in (os.listdir(jamo_dir) if os.path.isdir(jamo_dir) else []) if n.endswith(".SVF"))
    test.assertTrue(set(mine) <= set(rows), "FACES.TSV has no row for %s" % sorted(set(mine) - set(rows)))


def assert_draws(test, face_path):
    """U+AC00 alone draws ink; U+0041 too, where the face has it."""
    face = svfline.Face.load(face_path)

    def draws(text):
        width, ascent, descent = svfline.measure([face_path], text)
        buf = svfline.layout([face_path], text, 1, ascent + 1, width + 2, ascent + descent + 2)
        return any(buf)
    test.assertTrue(draws("가"), "%s draws a blank U+AC00" % os.path.basename(face_path))
    if face.has(0x41):
        test.assertTrue(draws("A"), "%s draws a blank U+0041" % os.path.basename(face_path))
