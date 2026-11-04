#!/usr/bin/env python3
"""server.py tests: the HTTP server and JSON API over the job store.

The server runs in this process on `127.0.0.1:0` (`serve_forever` on a thread) over a temp data root and the
checkout the fixtures already use. The whole fixture tree is uploaded file by file (`upload_tree`); the archive
test uploads it as one zip. Every request is its own `http.client.HTTPConnection` (the server closes each
response's connection).

  python3 -m unittest discover -s maker/test -p 'test_server.py' -v
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import contextlib
import gzip
import importlib.util
import hashlib
import http.client
import inspect
import io
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.parse
import zipfile

import caps as capsmod
import fixtures
import inputfx
import jamoset
import jobs
import presets
import routes
import server
import settings
import zipout

WAIT_S = 180

FIXTURE_ROOT = None
F = {}


def setUpModule():
    """Write the fixture tree once for every test of this module."""
    global FIXTURE_ROOT
    FIXTURE_ROOT = tempfile.mkdtemp(prefix="svf-server-fixtures-")
    F.update(fixtures.write_fixtures(FIXTURE_ROOT))


def tearDownModule():
    if FIXTURE_ROOT:
        shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)


def read(path):
    """A fixture file's bytes (a context manager, so the test leaves no file handle open)."""
    with open(path, "rb") as f:
        return f.read()


def make_zip(root):
    """A zip of every file under @p root, member names relative to @p root (`/` separators)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirs, names in os.walk(root):
            for name in sorted(names):
                full = os.path.join(dirpath, name)
                zf.write(full, os.path.relpath(full, root).replace(os.sep, "/"))
    return buf.getvalue()


def zip_of(members):
    """A zip holding @p members (`[(name, bytes)]`), deflated."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return buf.getvalue()


def js_json_block(js, name):
    """The `const <name> = {...};` block of `maker.js`, parsed as JSON.

    `maker.js` writes its mirrored Python tables as strict JSON (double-quoted keys and strings) so a test can read
    them back without a JS engine.
    """
    match = re.search(r"const\s+%s\s*=\s*([\[{].*?\n[\]}]);" % re.escape(name), js, re.S)
    if not match:
        raise AssertionError("maker.js has no JSON `%s` block" % name)
    return json.loads(match.group(1))


def canonical_fonts():
    """A font entry per source_kind Python knows, able to take every route its kind offers.

    The kinds come from `presets.ALL_SOURCES`, the one list in the code (not a copy here): a source kind added in
    Python is iterated by the drift test without an edit to this file. Every optional entry (`bdf`, `svf`, `dos`) is
    present, so a route that needs one is offered; the SVF kinds get their 1 and 2 bpp variants.
    """
    base = {"face_index": 0, "sizes": [16], "bdf": {"box": [16, 16]}, "dos": {"candidates": ["844"]},
            "svf": {"bpp": 1}, "dos_bytes": 11520}
    fonts = [dict(base, source_kind=kind) for kind in presets.ALL_SOURCES]
    fonts += [dict(base, source_kind=kind, svf={"bpp": 2})
              for kind in ("svf-precomposed", "svf-jamo")]
    # the rules a kind's own rows cannot show: johab844 only for an 11,520 byte raw font, a face after the first only
    # with prep, a 2 bpp-less SVF, a KSC BDF without a box
    prep = [{"op": "ttc-face", "index": 1}]
    fonts += [dict(base, source_kind=kind, gsub_jamo=True, mask_ok=ok)
              for kind in ("outline", "outline-composite") for ok in (True, False)]
    fonts += [dict(base, source_kind="dos-raw", dos_bytes=25920),
              dict(base, source_kind="dos-raw", dos={"candidates": ["844-ihnm"]}),
              dict(base, source_kind="outline", face_index=1),
              dict(base, source_kind="outline", face_index=1, prep=prep),
              dict(base, source_kind="outline-composite", face_index=1, prep=prep),
              dict(base, source_kind="bitmap", face_index=1),
              dict(base, source_kind="bitmap", face_index=1, prep=prep),
              dict(base, source_kind="bdf-ksc5601", bdf={})]
    return fonts


@contextlib.contextmanager
def caps(**values):
    """Run with `server`'s cap constants replaced (restored even when the block raises)."""
    old = {name: getattr(server, name) for name in values}
    try:
        for name, value in values.items():
            setattr(server, name, value)
        yield
    finally:
        for name, value in old.items():
            setattr(server, name, value)


def upload_tree(conn, job_id, root):
    """PUT every file under @p root into @p job_id through @p conn, one file at a time."""
    for dirpath, _dirs, names in os.walk(root):
        for name in sorted(names):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            with open(full, "rb") as f:
                body = f.read()
            conn.request("PUT", "/api/jobs/%s/files?path=%s" % (job_id, urllib.parse.quote(rel, safe="")),
                         body=body)
            resp = conn.getresponse()
            resp.read()
            if resp.status != 200:
                raise AssertionError("upload %s: HTTP %s" % (rel, resp.status))


class Reply:
    """One response read whole: `status`, `read()` and `getheader()`, like an `http.client` response."""

    def __init__(self, status, headers, body):
        self.status = status
        self._headers = headers
        self._body = body

    def read(self):
        return self._body

    def getheader(self, name, default=None):
        return self._headers.get(name, default)


class ApiBase(unittest.TestCase):
    """The server fixture and helpers; a subclass adds the tests (this class has none, so it runs nothing)."""

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="svf-server-data-")
        self.srv = server.make_server("127.0.0.1", 0, fixtures.REPO_DIR, self.data)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        # stop whatever the worker may be running (a queued `run` job), then the server; leave no process behind
        deadline = time.monotonic() + WAIT_S
        for item in self.srv.store.list():
            while time.monotonic() < deadline and self.srv.worker.cancel(item["id"]) != "not running":
                time.sleep(0.05)
        self.srv.shutdown()
        self.srv.server_close()
        self.thread.join(WAIT_S)
        shutil.rmtree(self.data, ignore_errors=True)

    # ---- helpers ----------------------------------------------------------------------------------------------

    def raw(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=WAIT_S)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            resp = conn.getresponse()
            return Reply(resp.status, dict(resp.getheaders()), resp.read())
        finally:
            conn.close()

    def get(self, path):
        return json.loads(self.raw("GET", path).read())

    def post(self, path, body=None, headers=None):
        return json.loads(self.raw("POST", path, body=body, headers=headers).read())

    def put_file(self, job_id, rel, data):
        url = "/api/jobs/%s/files?path=%s" % (job_id, urllib.parse.quote(rel, safe=""))
        return self.raw("PUT", url, body=data)

    def detected_job(self):
        """A job with the whole fixture tree uploaded and `detect` run on it."""
        jid = self.post("/api/jobs")["id"]
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=WAIT_S)
        try:
            upload_tree(conn, jid, FIXTURE_ROOT)
        finally:
            conn.close()
        self.post("/api/jobs/%s/detect" % jid)
        return jid

    def minimal_job(self):
        """A detected job with one TTF and its licence, selected into `new/fixture`: ready to run in a few seconds."""
        jid = self.post("/api/jobs")["id"]
        self.put_file(jid, "nanum/NanumGothic-Bold.ttf", read(F["ttf"]))
        self.put_file(jid, "nanum/OFL.txt", read(F["ttf_licence"]))
        self.post("/api/jobs/%s/detect" % jid)
        s = self.get("/api/jobs/%s" % jid)["settings"]
        for fid in s["fonts"]:
            s["fonts"][fid]["dest"] = "new/fixture"
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 200)
        return jid

    def run_to_done(self, jid):
        """`POST run` and wait for the job to finish; returns the final job."""
        job = self.post("/api/jobs/%s/run" % jid)
        self.assertIn(job["state"], ("queued", "running"))
        deadline = time.monotonic() + WAIT_S
        while time.monotonic() < deadline:
            job = self.get("/api/jobs/%s" % jid)
            if job["state"] in ("done", "failed"):
                return job
            time.sleep(0.1)
        self.fail("job %s did not finish" % jid)

    def open_put(self, job_id, rel, length):
        """A raw connection whose `PUT files` headers are sent and whose body is not: the caller streams it."""
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=WAIT_S)
        head = ("PUT /api/jobs/%s/files?path=%s HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nContent-Length: %d\r\n\r\n"
                % (job_id, urllib.parse.quote(rel, safe=""), self.port, length))
        sock.sendall(head.encode("ascii"))
        return sock

    @staticmethod
    def read_status(sock):
        """The status code of the reply on @p sock, once its header block has arrived."""
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return int(data.split(b" ", 2)[1]) if data else None

    def wait_reserved(self, job_id, timeout=WAIT_S):
        """Wait until the server holds an upload reservation for @p job_id (a PUT whose body is still arriving)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            held = self.srv.reserved.get(job_id)
            if held and (held.get("bytes") or held.get("files")):
                return held
            time.sleep(0.01)
        self.fail("no upload reservation for %s" % job_id)


class ApiTest(ApiBase):
    # ---- tests ------------------------------------------------------------------------------------------------

    def test_lifecycle_to_detected(self):
        jid = self.post("/api/jobs")["id"]
        self.assertEqual(len(jid), 12)
        r = self.put_file(jid, "nanum/NanumGothic-Bold.ttf", read(F["ttf"]))
        self.assertEqual(r.status, 200)
        r = self.put_file(jid, "nanum/NanumGothic-Bold.ttf", read(F["ttf"]))  # overwrite
        self.assertEqual(r.status, 200)
        self.put_file(jid, "nanum/OFL.txt", read(F["ttf_licence"]))
        job = self.post("/api/jobs/%s/detect" % jid)
        self.assertEqual(job["state"], "detected")
        self.assertEqual(job["upload"]["files"], 2)
        self.assertEqual([f["path"] for f in job["fonts"]], ["nanum/NanumGothic-Bold.ttf", "nanum/OFL.txt"])
        self.assertEqual(self.get("/api/jobs/%s" % jid)["settings"]["batch"]["range"], "2350")

    def test_upload_refusals(self):
        jid = self.post("/api/jobs")["id"]
        # http.client adds Content-Length: 0 for body=None, so build the request by hand
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=WAIT_S)
        c.putrequest("PUT", "/api/jobs/%s/files?path=a.ttf" % jid)
        c.endheaders()
        self.assertEqual(c.getresponse().status, 411)
        c.close()
        big = {"Content-Length": str(server.BODY_CAP + 1)}
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/files?path=a.ttf" % jid, headers=big).status, 413)
        self.assertEqual(self.put_file(jid, "../x", b"1").status, 400)
        self.assertEqual(self.put_file(jid, "a\\b", b"1").status, 400)
        self.assertEqual(json.loads(self.put_file(jid, "/abs", b"1").read())["error"], "absolute path")

    def test_archive_upload_is_unpacked(self):
        jid = self.post("/api/jobs")["id"]
        self.put_file(jid, "fix.zip", make_zip(FIXTURE_ROOT))
        job = self.post("/api/jobs/%s/detect" % jid)
        paths = [f["path"] for f in job["fonts"]]
        self.assertIn("fix.zip.d/nanum/NanumGothic-Bold.ttf", paths)
        self.assertNotIn("fix.zip", paths)

    def test_settings_validation_and_unknown_keys(self):
        jid = self.detected_job()
        r = self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps({"batch": {}, "fonts": {"f99": {}}}).encode())
        self.assertEqual(r.status, 400)
        self.assertIn("unknown font id f99", json.loads(r.read())["error"])
        job = self.get("/api/jobs/%s" % jid)
        self.assertNotIn("f99", job["settings"]["fonts"])
        s = job["settings"]
        f = next(iter(s["fonts"]))
        # the stored per-font `names` is {} by default: build the bad names from the effective ones the page shows
        s["fonts"][f]["names"] = {k: "toolongname.svf" for k in job["effective_names"][f]}
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 400)

    def test_run_refused_without_licence_then_queued(self):
        jid = self.detected_job()
        job = self.get("/api/jobs/%s" % jid)
        s = job["settings"]
        for f in job["fonts"]:                                   # the SVF fixtures' names exist in svf/dos
            if f["path"].endswith((".SVF",)):
                s["fonts"][f["id"]]["dest"] = "new/fixture"
        nolic = [f["id"] for f in job["fonts"] if f["path"].startswith("nolic/")][0]
        s["fonts"][nolic]["selected"] = True
        # a selected font must carry a valid licence_name to pass `validate` (Task 7); the licence itself stays None,
        # so only `run_ready`'s "no licence" rule can refuse the run
        s["fonts"][nolic]["licence_name"] = "NOLIC.TXT"
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 200)
        r = self.raw("POST", "/api/jobs/%s/run" % jid)
        self.assertEqual(r.status, 400)
        self.assertIn(nolic + ": no licence", json.loads(r.read())["error"])
        s["fonts"][nolic]["selected"] = False
        self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode())
        job = self.post("/api/jobs/%s/run" % jid)
        self.assertIn(job["state"], ("queued", "running"))
        self.assertTrue(job["steps"])
        self.assertEqual(self.raw("GET", "/api/jobs/%s/zip" % jid).status, 409)
        self.assertEqual(self.raw("DELETE", "/api/jobs/%s" % jid).status, 409)
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=b"{}").status, 409)
        self.post("/api/jobs/%s/cancel" % jid)

    def test_previews_repo_and_static(self):
        jid = self.detected_job()
        fonts = self.get("/api/jobs/%s" % jid)["fonts"]
        ttf = [f["id"] for f in fonts if f["path"].endswith("NanumGothic-Bold.ttf")][0]
        r = self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, ttf))
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "image/png"))
        dos = [f["id"] for f in fonts if f["path"].endswith("HAN.FNT")][0]
        self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, dos)).status, 409)
        repo = self.get("/api/repo")
        self.assertIn("dos", repo["folders"])
        self.assertIn("NEODG16.SVF", repo["names"]["dos"])
        self.assertEqual(self.raw("GET", "/").status, 200)
        self.assertEqual(self.raw("GET", "/static/../server.py").status, 404)
        self.assertEqual(self.raw("GET", "/api/jobs/zzz").status, 404)

    def test_run_refuses_a_note_that_does_not_fit(self):
        """A long upload path pushes a real command line past the note's byte limit: `POST /run` is a 400, not a job
        that fails at the zip step (the Task 12 note check)."""
        jid = self.post("/api/jobs")["id"]
        folder = ("d" * 200) + "/" + ("e" * 200)             # inside check_rel_path's 255-byte component cap
        self.put_file(jid, "%s/NanumGothic-Bold.ttf" % folder, read(F["ttf"]))
        self.put_file(jid, "%s/OFL.txt" % folder, read(F["ttf_licence"]))
        self.post("/api/jobs/%s/detect" % jid)
        job = self.get("/api/jobs/%s" % jid)
        s = job["settings"]
        for fid in s["fonts"]:                               # a fresh destination: no suggested name clashes
            s["fonts"][fid]["dest"] = "new/fixture"
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 200)
        r = self.raw("POST", "/api/jobs/%s/run" % jid)
        self.assertEqual(r.status, 400)
        self.assertIn("note for", json.loads(r.read())["error"])
        self.assertEqual(self.raw("GET", "/api/jobs/%s" % jid).status, 200)   # the job is still `detected`

    def test_jobs_list_and_delete(self):
        jid = self.post("/api/jobs")["id"]
        self.assertIn(jid, [item["id"] for item in self.get("/api/jobs")["jobs"]])
        self.assertEqual(self.raw("GET", "/api/jobs/%s" % ("0" * 12)).status, 404)
        r = self.raw("DELETE", "/api/jobs/%s" % jid)
        self.assertEqual(r.status, 200)
        self.assertEqual(json.loads(r.read()), {"deleted": jid})
        self.assertEqual(self.raw("GET", "/api/jobs/%s" % jid).status, 404)

    # ---- fix round 1: S1 and W1-W14 ---------------------------------------------------------------

    def test_detect_accepts_a_failed_job_and_keeps_its_settings(self):
        """S1: the owner re-runs a failed job: detect resets it to `detected` with the settings kept by font id."""
        jid = self.minimal_job()
        fid = self.get("/api/jobs/%s" % jid)["fonts"][0]["id"]
        self.srv.store.update(jid, lambda j: j.update(state="failed", error="interrupted"))
        job = self.post("/api/jobs/%s/detect" % jid)
        self.assertEqual(job["state"], "detected")
        self.assertIsNone(job["error"])
        self.assertEqual(job["steps"], [])
        self.assertEqual(job["settings"]["fonts"][fid]["dest"], "new/fixture")   # the owner's edit survives
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid,
                                  body=json.dumps(job["settings"]).encode()).status, 200)
        job = self.post("/api/jobs/%s/run" % jid)
        self.assertIn(job["state"], ("queued", "running"))

    def test_a_slow_upload_cannot_take_back_a_running_job(self):
        """W1: the body streams while `POST run` takes the job; the upload is refused and its file discarded."""
        jid = self.minimal_job()
        sock = self.open_put(jid, "late.txt", 4)
        try:
            sock.sendall(b"la")
            job = self.post("/api/jobs/%s/run" % jid)
            self.assertIn(job["state"], ("queued", "running"))
            sock.sendall(b"te")
            self.assertEqual(self.read_status(sock), 409)
        finally:
            sock.close()
        job = self.get("/api/jobs/%s" % jid)
        self.assertNotEqual(job["state"], "uploading")
        self.assertFalse(os.path.exists(self.srv.store.path(jid, "upload", "late.txt")))
        self.assertFalse(os.path.exists(self.srv.store.path(jid, "upload", "late.txt.tmp")))

    def test_delete_racing_a_run_returns_409(self):
        """W1: a queued/running job is never deleted under the worker (cancel first)."""
        jid = self.minimal_job()
        self.post("/api/jobs/%s/run" % jid)
        self.assertEqual(self.raw("DELETE", "/api/jobs/%s" % jid).status, 409)

    def test_previews_follow_a_redetect(self):
        """W2: `detect` clears the previews, so a moved font id cannot serve the earlier font's PNG."""
        jid = self.post("/api/jobs")["id"]
        self.put_file(jid, "z/N.ttf", read(F["ttf"]))
        job = self.post("/api/jobs/%s/detect" % jid)
        self.assertEqual(job["fonts"][0]["path"], "z/N.ttf")
        first = self.raw("GET", "/api/jobs/%s/preview/f01/source.png" % jid)
        self.assertEqual(first.status, 200)
        self.put_file(jid, "a/O.otf", read(F["otf"]))
        job = self.post("/api/jobs/%s/detect" % jid)
        self.assertEqual(job["fonts"][0]["path"], "a/O.otf")
        second = self.raw("GET", "/api/jobs/%s/preview/f01/source.png" % jid)
        self.assertEqual(second.status, 200)
        self.assertNotEqual(hashlib.sha256(first.read()).hexdigest(), hashlib.sha256(second.read()).hexdigest())

    def test_a_settings_change_clears_the_font_preview(self):
        """W2: a change to the preview inputs drops the cached PNG of that font."""
        jid = self.minimal_job()
        job = self.get("/api/jobs/%s" % jid)
        fid = job["fonts"][0]["id"]
        self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, fid)).status, 200)
        cached = self.srv.store.path(jid, "work", "preview", "%s.png" % fid)
        self.assertTrue(os.path.isfile(cached))
        s = job["settings"]
        s["fonts"][fid]["sizes"] = [20]
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 200)
        self.assertFalse(os.path.exists(cached))
        self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, fid)).status, 200)

    def test_job_and_file_caps_refuse_before_the_body(self):
        """W13/W14: the 413s, and an overwrite neither adds a file nor its replaced bytes."""
        with caps(JOB_CAP=1000):
            jid = self.post("/api/jobs")["id"]
            self.assertEqual(self.put_file(jid, "a.ttf", b"x" * 600).status, 200)
            self.assertEqual(self.put_file(jid, "b.ttf", b"x" * 500).status, 413)
            self.assertEqual(self.get("/api/jobs/%s" % jid)["upload"]["bytes"], 600)
            self.assertEqual(self.put_file(jid, "a.ttf", b"x" * 600).status, 200)    # an overwrite fits
            self.assertEqual(self.put_file(jid, "a.ttf", b"x" * 900).status, 200)    # 900 - 600 + 900 = 900
            self.assertEqual(self.put_file(jid, "b.ttf", b"x" * 200).status, 413)
        with caps(FILE_CAP=1):
            jid = self.post("/api/jobs")["id"]
            self.assertEqual(self.put_file(jid, "a.ttf", b"x").status, 200)
            self.assertEqual(self.put_file(jid, "b.ttf", b"x").status, 413)
            self.assertEqual(self.put_file(jid, "a.ttf", b"x").status, 200)          # an overwrite adds no file
            self.assertEqual(self.get("/api/jobs/%s" % jid)["upload"]["files"], 1)

    def test_parallel_uploads_reserve_the_file_cap(self):
        """W4: the cap is reserved under the job lock, so parallel PUTs cannot pass it."""
        with caps(FILE_CAP=2):
            jid = self.post("/api/jobs")["id"]
            self.assertEqual(self.put_file(jid, "a.ttf", b"x").status, 200)
            results = []
            threads = [threading.Thread(target=lambda i=i: results.append(
                self.put_file(jid, "p%d.ttf" % i, b"x").status)) for i in range(3)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(WAIT_S)
            self.assertEqual(sorted(results), [200, 413, 413])

    def test_the_archive_allowance_stops_at_the_job_cap(self):
        """W3: an archive's unpack allowance is `JOB_CAP - upload.bytes`, so one archive cannot pass it."""
        with caps(JOB_CAP=4096):
            jid = self.post("/api/jobs")["id"]
            body = zip_of([("big.bin", b"\0" * 8192)])
            r = self.put_file(jid, "big.zip", body)
            self.assertEqual(r.status, 200)
            self.assertIn("total over", json.loads(r.read())["unpacked"]["stopped"])
            job = self.get("/api/jobs/%s" % jid)
            self.assertLessEqual(job["upload"]["bytes"], 4096)

    def test_state_conflicts_are_409(self):
        """W14: `PUT files`, `detect`, `cancel` and `DELETE` refuse a job another transition owns."""
        jid = self.post("/api/jobs")["id"]
        self.srv.store.update(jid, lambda j: j.update(state="running"))
        self.assertEqual(self.put_file(jid, "a.ttf", b"x").status, 409)
        self.assertEqual(self.raw("POST", "/api/jobs/%s/detect" % jid).status, 409)
        self.assertEqual(self.raw("POST", "/api/jobs/%s/cancel" % jid).status, 409)
        self.assertEqual(self.raw("DELETE", "/api/jobs/%s" % jid).status, 409)
        jid = self.post("/api/jobs")["id"]
        self.assertEqual(self.raw("POST", "/api/jobs/%s/cancel" % jid).status, 409)

    def test_malformed_inputs_are_400_not_500(self):
        """W5: a file where a folder goes, empty path components, a too-long archive name and deep JSON."""
        jid = self.post("/api/jobs")["id"]
        self.assertEqual(self.put_file(jid, "a", b"x").status, 200)
        self.assertEqual(self.put_file(jid, "a/c", b"x").status, 400)
        self.assertEqual(self.put_file(jid, "d/c", b"x").status, 200)
        self.assertEqual(self.put_file(jid, "d", b"x").status, 400)
        self.assertEqual(self.put_file(jid, "a//b", b"x").status, 400)
        self.assertEqual(self.put_file(jid, "a/b/", b"x").status, 400)
        name = "y" * 251 + ".zip"
        self.assertEqual(self.put_file(jid, name, zip_of([("one.txt", b"x")])).status, 400)
        self.assertFalse(os.path.exists(self.srv.store.path(jid, "upload", name)))
        jid = self.minimal_job()
        r = self.raw("PUT", "/api/jobs/%s/settings" % jid, body=b"[" * 100000)
        self.assertEqual(r.status, 400)

    def test_stalled_upload_is_closed_and_its_reservation_released(self):
        """W8: a body that stops arriving is timed out, and the bytes it reserved are freed again."""
        old = server.Handler.timeout
        server.Handler.timeout = 0.3
        try:
            with caps(JOB_CAP=1000):
                jid = self.post("/api/jobs")["id"]
                sock = self.open_put(jid, "stalled.ttf", 900)
                try:
                    sock.sendall(b"x" * 10)
                    time.sleep(1.0)                       # the handler's read times out and it releases the bytes
                finally:
                    sock.close()
                self.assertEqual(self.put_file(jid, "fits.ttf", b"x" * 900).status, 200)
        finally:
            server.Handler.timeout = old

    def test_host_and_origin_checks_on_state_changes(self):
        """W9: a state-changing request must come from the served host, and its Origin must match."""
        self.assertEqual(self.raw("POST", "/api/jobs", headers={"Host": "evil.example"}).status, 403)
        self.assertEqual(self.raw("POST", "/api/jobs", headers={"Origin": "http://evil.example"}).status, 403)
        self.assertEqual(self.raw("POST", "/api/jobs",
                                  headers={"Origin": "http://127.0.0.1:%d" % self.port}).status, 200)
        self.assertEqual(self.raw("GET", "/api/jobs", headers={"Host": "evil.example"}).status, 200)

    def test_every_response_carries_nosniff(self):
        """W10: `X-Content-Type-Options: nosniff` on a file, a JSON answer and an error."""
        for path in ("/", "/api/jobs", "/api/jobs/zzz"):
            self.assertEqual(self.raw("GET", path).getheader("X-Content-Type-Options"), "nosniff", path)

    def test_bind_host_defaults_to_localhost_and_drops_brackets(self):
        """W11: no host in the bind string is 127.0.0.1, and an IPv6 host loses its brackets."""
        self.assertEqual(server._bind(":8766"), ("127.0.0.1", 8766))
        self.assertEqual(server._bind("[::1]:8766"), ("::1", 8766))
        self.assertEqual(server._bind("192.0.2.10:8766"), ("192.0.2.10", 8766))

    def test_the_step_png_route_is_gone(self):
        """The worker writes no result PNG: a step's PNG is a 404 for its own font; the source PNG still works."""
        jid = self.minimal_job()
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done")
        step = job["steps"][0]
        self.assertNotIn("preview", step)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/%s/%s.png" % (jid, step["font"], step["id"])).status, 404)
        r = self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, step["font"]))
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "image/png"))

    def test_zip_headers_on_a_done_job(self):
        """W14: the zip of a done job, and a done job can be detected again (S1)."""
        jid = self.minimal_job()
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done")
        r = self.raw("GET", "/api/jobs/%s/zip" % jid)
        self.assertEqual(r.status, 200)
        self.assertEqual(r.getheader("Content-Type"), "application/zip")
        self.assertEqual(r.getheader("Content-Disposition"), 'attachment; filename="svf-maker-%s.zip"' % jid)
        self.assertTrue(r.read().startswith(b"PK\x03\x04"))
        self.assertEqual(self.post("/api/jobs/%s/detect" % jid)["state"], "detected")

    def test_unpack_stop_reason_lands_in_upload_refused(self):
        """W14: a refused archive is recorded as `<rel>: <reason>`."""
        with caps(FILE_CAP=1):
            jid = self.post("/api/jobs")["id"]
            r = self.put_file(jid, "fix.zip", zip_of([("one.txt", b"1"), ("two.txt", b"2")]))
            self.assertEqual(r.status, 200)
            self.assertIn("more than 1 files", json.loads(r.read())["unpacked"]["stopped"])
            self.assertIn("fix.zip: more than 1 files", self.get("/api/jobs/%s" % jid)["upload"]["refused"])

    def test_a_gz_source_preview_decompresses_under_its_font(self):
        """W7: a `.gz` member's decompressed copy lives under `work/preview/<font id>/`, never a shared name."""
        jid = self.post("/api/jobs")["id"]
        gz = gzip.compress(read(F["ttf"]))
        self.put_file(jid, "fonts.zip", zip_of([("a/x.ttf.gz", gz), ("b/x.ttf.gz", gz)]))
        job = self.post("/api/jobs/%s/detect" % jid)
        fonts = [font for font in job["fonts"] if font["path"].endswith("x.ttf.gz")]
        self.assertEqual(len(fonts), 2)
        self.assertTrue(all(font.get("gzip") for font in fonts))
        fid = fonts[0]["id"]
        r = self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, fid))
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "image/png"))
        self.assertTrue(os.path.isfile(self.srv.store.path(jid, "work", "preview", fid, "x.ttf")))
        self.assertFalse(os.path.exists(self.srv.store.path(jid, "work", "preview", "x.ttf")))

    def test_the_note_check_uses_zipouts_helpers(self):
        """W12: `POST /run` builds the note's command lines with `zipout.note_commands`, so they cannot drift."""
        seen = []
        original = zipout.note_commands

        def spy(steps, font):
            seen.append(steps)
            return original(steps, font)

        zipout.note_commands = spy
        try:
            jid = self.minimal_job()
            job = self.post("/api/jobs/%s/run" % jid)
            self.assertIn(job["state"], ("queued", "running"))
            self.assertTrue(seen)
            self.assertTrue(all(isinstance(step.get("argv"), list) for steps in seen for step in steps))
        finally:
            zipout.note_commands = original

    def test_retain_and_delete_drop_the_preview_locks(self):
        """W13: a job `retain` removes or `DELETE` deletes leaves no per-font lock behind."""
        jid = self.minimal_job()
        fid = self.get("/api/jobs/%s" % jid)["fonts"][0]["id"]
        self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, fid)).status, 200)
        self.assertTrue(any(key[0] == jid for key in server._PREVIEW_LOCKS))
        self.srv.store.update(jid, lambda j: j.update(created=time.time() - jobs.MAX_AGE - 60))
        self.srv.worker.retain()
        self.assertFalse(os.path.exists(self.srv.store.path(jid)))
        self.assertFalse(any(key[0] == jid for key in server._PREVIEW_LOCKS))
        jid = self.minimal_job()
        fid = self.get("/api/jobs/%s" % jid)["fonts"][0]["id"]
        self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, fid)).status, 200)
        self.assertEqual(self.raw("DELETE", "/api/jobs/%s" % jid).status, 200)
        self.assertFalse(any(key[0] == jid for key in server._PREVIEW_LOCKS))

    # ---- fix round 2: Y1-Y7 ----------------------------------------------------------------------

    def test_an_archive_allowance_counts_the_other_uploads_files(self):
        """Y1: a 4-member zip cannot pass FILE_CAP while a slow PUT holds a file reservation."""
        with caps(FILE_CAP=5):
            jid = self.post("/api/jobs")["id"]
            self.assertEqual(self.put_file(jid, "one.txt", b"1").status, 200)
            sock = self.open_put(jid, "slow.txt", 4)
            try:
                sock.sendall(b"sl")
                self.wait_reserved(jid)
                body = zip_of([("a.txt", b"1"), ("b.txt", b"2"), ("c.txt", b"3"), ("d.txt", b"4")])
                r = self.put_file(jid, "four.zip", body)
                self.assertEqual(r.status, 200)
                # one.txt and the zip are on disk, the slow PUT holds the third: only 3 members fit
                stopped = (json.loads(r.read())["unpacked"] or {}).get("stopped") or ""
                self.assertIn("more than 3 files", stopped)
                sock.sendall(b"ow")
                self.assertEqual(self.read_status(sock), 200)
            finally:
                sock.close()
            job = self.get("/api/jobs/%s" % jid)
            self.assertLessEqual(job["upload"]["files"], 5)
            self.assertLessEqual(job["upload"]["files"], server.FILE_CAP)

    def test_an_archive_allowance_counts_the_other_uploads_bytes(self):
        """Y1: a zip expanding past `JOB_CAP - upload.bytes - reserved bytes` is stopped, and the job stays under."""
        with caps(JOB_CAP=10000):
            jid = self.post("/api/jobs")["id"]
            self.assertEqual(self.put_file(jid, "base.bin", b"x" * 1000).status, 200)
            sock = self.open_put(jid, "slow.bin", 4000)
            try:
                sock.sendall(b"x" * 10)
                self.wait_reserved(jid)
                # 8192 bytes of a 256-byte pattern deflate to ~460 bytes: the PUT itself fits the cap
                body = zip_of([("big.bin", bytes(range(256)) * 32)])
                r = self.put_file(jid, "big.zip", body)
                self.assertEqual(r.status, 200)
                stopped = (json.loads(r.read())["unpacked"] or {}).get("stopped") or ""
                self.assertIn("total over", stopped)
                sock.sendall(b"x" * (4000 - 10))
                self.assertEqual(self.read_status(sock), 200)
            finally:
                sock.close()
            job = self.get("/api/jobs/%s" % jid)
            self.assertLessEqual(job["upload"]["bytes"], 10000)

    def test_redetect_keeps_settings_on_the_same_font_path(self):
        """Y2: a re-detect remaps the owner's per-font settings by path, so an earlier-sorting font takes no edit."""
        jid = self.minimal_job()
        job = self.get("/api/jobs/%s" % jid)
        ttf = [font for font in job["fonts"] if font["path"].endswith("NanumGothic-Bold.ttf")][0]
        old_id = ttf["id"]
        name_key = next(iter(job["effective_names"][old_id]))
        s = job["settings"]
        s["fonts"][old_id].update(selected=True, dest="new/fixture",
                                  names={name_key: "KEEPME16.SVF"}, note_name="KEEPME.TXT")
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 200)
        self.assertEqual(self.put_file(jid, "a/O.otf", read(F["otf"])).status, 200)
        job = self.post("/api/jobs/%s/detect" % jid)
        by_path = {font["path"]: font["id"] for font in job["fonts"]}
        new_id = by_path["nanum/NanumGothic-Bold.ttf"]
        otf_id = by_path["a/O.otf"]
        self.assertEqual(otf_id, "f01")                     # the earlier-sorting OTF took the first id
        self.assertEqual(new_id, "f02")
        kept = job["settings"]["fonts"][new_id]
        self.assertEqual((kept["selected"], kept["dest"], kept["names"], kept["note_name"]),
                         (True, "new/fixture", {name_key: "KEEPME16.SVF"}, "KEEPME.TXT"))
        otf_entry = next(font for font in job["fonts"] if font["id"] == otf_id)
        self.assertEqual(job["settings"]["fonts"][otf_id], settings.defaults([otf_entry])["fonts"][otf_id])

    def test_detect_refuses_while_an_upload_is_in_flight(self):
        """Y3: a scan must not see a body in flight (and its temp file), so `detect` is a 409 until it lands."""
        jid = self.post("/api/jobs")["id"]
        self.assertEqual(self.put_file(jid, "a/x.ttf", read(F["ttf"])).status, 200)
        sock = self.open_put(jid, "b/slow.ttf", 4)
        try:
            sock.sendall(b"sl")
            self.wait_reserved(jid)
            r = self.raw("POST", "/api/jobs/%s/detect" % jid)
            self.assertEqual(r.status, 409)
            self.assertIn("upload", json.loads(r.read())["error"])
            sock.sendall(b"ow")
            self.assertEqual(self.read_status(sock), 200)
        finally:
            sock.close()
        job = self.post("/api/jobs/%s/detect" % jid)
        self.assertEqual(job["state"], "detected")
        self.assertEqual([font["path"] for font in job["fonts"]], ["a/x.ttf", "b/slow.ttf"])

    def test_detect_ignores_an_upload_temp_file(self):
        """Y3: `_receive`'s `.upload-*` temp files are never listed as fonts."""
        jid = self.post("/api/jobs")["id"]
        self.assertEqual(self.put_file(jid, "a/x.ttf", read(F["ttf"])).status, 200)
        tmp = self.srv.store.path(jid, "upload", ".upload-abc123")
        with open(tmp, "wb") as f:
            f.write(b"half a body")
        job = self.post("/api/jobs/%s/detect" % jid)
        self.assertEqual([font["path"] for font in job["fonts"]], ["a/x.ttf"])

    def test_make_server_binds_an_ipv6_host(self):
        """Y4: a host with a colon binds through an AF_INET6 server class (`::1` works, not `gaierror`)."""
        if not socket.has_ipv6:
            self.skipTest("this host has no IPv6")
        probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            probe.bind(("::1", 0))
        except OSError as exc:
            self.skipTest("::1 is not bindable here: %s" % exc)
        finally:
            probe.close()
        data = tempfile.mkdtemp(prefix="svf-server-v6-")
        srv = None
        try:
            srv = server.make_server("::1", 0, fixtures.REPO_DIR, data)
            self.assertEqual(srv.address_family, socket.AF_INET6)
            self.assertEqual(srv.server_address[0], "::1")
            self.assertGreater(srv.server_address[1], 0)
        finally:
            if srv is not None:
                srv.server_close()
            shutil.rmtree(data, ignore_errors=True)

    def test_a_put_to_an_unknown_or_busy_job_makes_no_folder(self):
        """Y5: the job and its state are checked before any `upload/` folder is made."""
        unknown = "0" * 12
        self.assertEqual(self.put_file(unknown, "x/y.ttf", b"1").status, 404)
        self.assertFalse(os.path.exists(os.path.join(self.data, "jobs", unknown)))
        jid = self.post("/api/jobs")["id"]
        self.srv.store.update(jid, lambda j: j.update(state="running"))
        self.assertEqual(self.put_file(jid, "newdir/sub.ttf", b"1").status, 409)
        self.assertFalse(os.path.exists(self.srv.store.path(jid, "upload", "newdir")))

    def test_detect_does_not_hold_the_job_lock_for_a_preview(self):
        """Y6: `detect` commits its transition and frees the job lock before it waits for a preview bake."""
        jid = self.minimal_job()
        fid = self.get("/api/jobs/%s" % jid)["fonts"][0]["id"]
        self.srv.store.update(jid, lambda j: j.update(state="failed", error="interrupted"))
        lock = server._preview_lock(jid, fid)               # stand in for a bake a request is holding
        lock.acquire()
        replies = {}
        thread = threading.Thread(target=lambda: replies.update(r=self.raw("POST", "/api/jobs/%s/detect" % jid)))
        committed = False
        try:
            thread.start()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if self.get("/api/jobs/%s" % jid)["state"] == "detected":
                    committed = True
                    break
                time.sleep(0.02)
            if committed:                                   # the job lock is free: a PUT is answered at once
                started = time.monotonic()
                self.assertEqual(self.put_file(jid, "late.txt", b"x").status, 200)
                self.assertLess(time.monotonic() - started, 5)
        finally:
            lock.release()
            thread.join(WAIT_S)
        self.assertTrue(committed, "detect held the job lock while it waited for the preview lock")
        self.assertEqual(replies["r"].status, 200)

    def test_clearing_one_fonts_previews_leaves_a_longer_id_alone(self):
        """Y7: clearing f10's previews matches f10 (f10, f10.*, f10/), never f100."""
        jid = self.post("/api/jobs")["id"]
        body = zip_of([("d/f%03d.ttf" % i, read(F["composite"])) for i in range(100)])
        self.assertEqual(self.put_file(jid, "many.zip", body).status, 200)
        job = self.post("/api/jobs/%s/detect" % jid)
        ids = [font["id"] for font in job["fonts"]]
        self.assertEqual(ids[:2], ["f01", "f02"])
        self.assertIn("f10", ids)
        self.assertIn("f100", ids)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/f10/source.png" % jid).status, 200)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/f100/source.png" % jid).status, 200)
        preview = self.srv.store.path(jid, "work", "preview")
        self.assertTrue(os.path.isfile(os.path.join(preview, "f10.png")))
        self.assertTrue(os.path.isfile(os.path.join(preview, "f100.png")))
        s = job["settings"]
        s["fonts"]["f10"]["sizes"] = [20]
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 200)
        self.assertFalse(os.path.exists(os.path.join(preview, "f10.png")))
        self.assertTrue(os.path.isfile(os.path.join(preview, "f100.png")))

    def test_page_has_the_controls(self):
        html = self.raw("GET", "/").read().decode()
        for i in ("files", "folder", "upload", "detect", "state", "notice", "refused", "fonts", "settings",
                  "advanced", "save", "run", "cancel", "download", "steps", "jobs", "position"):
            self.assertIn('id="%s"' % i, html, i)
        self.assertIn('type="module"', html); self.assertEqual(self.raw("GET", "/static/maker.js").getheader("Content-Type"), "text/javascript")
        self.assertEqual(self.raw("GET", "/static/style.css").status, 200)

    def test_advanced_panel_has_the_jset_version_control(self):
        html = self.raw("GET", "/").read().decode()
        self.assertIn('data-option="jset_version" data-group="jamoset"', html)
        js = self.raw("GET", "/static/maker.js").read().decode()
        self.assertIn('{key: "jset_version", group: "jamoset", label: "JSET version"}', js)
        self.assertEqual(server.Handler._bake_flags({"options": {"jamoset": {"jset_version": 2}}}, "svf-jamo"),
                         ["--jset-version", "2"])
        self.assertEqual(server.Handler._bake_flags({"options": {"jamoset": {"jset_version": None}}}, "svf-jamo"), [])
        self.assertEqual(server.Handler._bake_flags({}, "dos-raw"), [])

    def test_page_shows_variable_width_and_spans_the_width(self):
        html = self.raw("GET", "/").read().decode()
        self.assertIn("variable width (v3)", html)           # M4: next to the precomposed kind
        css = self.raw("GET", "/static/style.css").read().decode().replace(" ", "")
        self.assertIn("grid-column:1/-1", css)               # I6: the fonts table spans the full layout width

    def test_page_js_tables_match_python(self):
        with open(os.path.join(MAKER_DIR, "static", "maker.js"), encoding="utf-8") as f:
            js = f.read()

        presets_js = js_json_block(js, "PRESETS")
        self.assertEqual([row[0] for row in presets_js], list(presets.PRESETS))
        for name, reproduces in presets_js:
            self.assertEqual(reproduces, presets.PRESETS[name]["reproduces"], name)

        expected = {}
        for font in canonical_fonts():
            for route in routes.routes(font):
                rows = expected.setdefault(font["source_kind"], [])
                same = [row for row in rows if row[:3] == [route.kind, route.label, route.native]]
                if same:
                    same[0][3] = sorted(set(same[0][3]) | set(route.bpps))
                else:
                    rows.append([route.kind, route.label, route.native, sorted(route.bpps)])
        for rows in expected.values():
            rows.sort()
        routes_js = js_json_block(js, "ROUTES")
        got = {kind: sorted([row["kind"], row["label"], row["native"], sorted(row["bpps"])] for row in rows)
               for kind, rows in routes_js.items()}
        self.assertEqual(got, expected)

        # `offeredRoutes` itself, run by node on every canonical font: the same routes as Python's, in order. The
        # ROUTES table above is only the page's catalogue; the rules that pick from it are in this function.
        if shutil.which("node"):
            fonts = canonical_fonts()
            table = re.search(r"const\s+ROUTES\s*=\s*([\[{].*?\n[\]}]);", js, re.S).group(1)
            func = re.search(r"function offeredRoutes\(font\) \{.*?\n\}\n", js, re.S).group(0)
            script = ("const ROUTES = %s;\n%s\nconst fonts = JSON.parse(process.argv[1]);\n"
                      "console.log(JSON.stringify(fonts.map((f) => offeredRoutes(f).map((r) => [r.kind, r.label, r.native, r.bpps]))));\n"
                      % (table, func))
            out = subprocess.run(["node", "-e", script, json.dumps(fonts)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            got_js = json.loads(out.stdout)
            want_py = [[[r.kind, r.label, r.native, r.bpps] for r in routes.routes(f)] for f in fonts]
            for font, got, want in zip(fonts, got_js, want_py):
                self.assertEqual(got, want, font)

        # The advanced panel's visibility (the page's `OPTION_VISIBLE`) is which flags `presets.panel_argv` emits for
        # a route label and bpp: every option carries a value that emits its flag, so the emitted flags name the keys
        # the page must show for that route and bpp. A new route label or a changed panel rule fails here.
        # A flag names a key by the label's tool (TOOL_OF_LABEL): --ascent is the mkfont `ascent`, the jamoset
        # `jamo_ascent` or the bdfface `latin_ascent`; every other flag is one key.
        flags = {"--cell": "cell", "--width": "width", "--space-advance": "space_advance",
                 "--mono-hint": "mono_hint", "--clip-cell": "clip_cell", "--fit-cell": "fit_cell", "--latin": "latin",
                 "--embolden": "embolden", "--symbols": "symbols", "--jset-version": "jset_version",
                 "--baseline": "fit_baseline", "--binarize": "binarize", "--aa-refine": "aa_refine",
                 "--no-clean": "clean", "--hangul-ascent": "hangul_ascent"}
        TOOL_OF_LABEL = {"mkfont": "ascent", "dos raw": "jamo_ascent", "hanterm": "jamo_ascent",
                         "bdfface": "latin_ascent", "bdfface + from-svf fit": "latin_ascent"}
        every = {"mkfont": {"cell": 18, "ascent": 12, "width": 18, "mono_hint": True, "clip_cell": True,
                            "fit_cell": False, "latin": True, "space_advance": 5},
                 "jamoset": {"embolden": True, "symbols": True, "jset_version": 2, "jamo_ascent": 12,
                             "fit_baseline": 12, "aa_refine": 3, "clean": False, "binarize": "ridge"},
                 "bdfface": {"latin_ascent": 12, "hangul_ascent": 13}}
        # clip_cell and fit_cell are exclusive in a real run: two passes, the union per (label, bpp)
        passes = [every, dict(every, mkfont=dict(every["mkfont"], clip_cell=False, fit_cell=True))]
        want = {}
        for font in canonical_fonts():
            for route in routes.routes(font):
                for bpp in route.bpps:
                    for opts in passes:
                        argv = [token for fragment in presets.panel_argv(opts, route.kind, route.label, bpp)
                                for token in fragment]
                        keys = [flags[token] if token != "--ascent" else TOOL_OF_LABEL[route.label]
                                for token in argv if token in flags or token == "--ascent"]
                        self.assertEqual(len(set(keys)), len(keys), (route.label, bpp, argv))     # one flag per key
                        want.setdefault(route.label, {}).setdefault(str(bpp), set()).update(keys)
        visible_js = js_json_block(js, "OPTION_VISIBLE")
        self.assertEqual(sorted(visible_js), sorted(want))                    # every route label, and no other
        for label, by_bpp in want.items():
            self.assertEqual(sorted(visible_js.get(label) or {}), sorted(by_bpp), label)
            for bpp, keys in by_bpp.items():
                self.assertEqual(sorted(visible_js[label][bpp]), sorted(keys), (label, bpp))

        # The preview kinds: every source kind Python knows is classified, `bake` is the branch
        # `server._make_source_preview` bakes first (read out of its code), and a kind the page promises to draw
        # must have a route. `none` is a Latin-only BDF, a BDF FreeType gives no Unicode charmap (`preview`
        # refuses those), an HBF or a kind with no face at all.
        preview_js = js_json_block(js, "PREVIEW_KINDS")
        self.assertEqual(sorted(preview_js), sorted(presets.ALL_SOURCES))
        source = inspect.getsource(server.Handler._make_source_preview)
        baked = set(re.findall(r'source_kind\s*==\s*"([a-z-]+)"', source))
        for group in re.findall(r'source_kind\s+in\s+\(([^)]*)\)', source):
            baked.update(re.findall(r'"([a-z-]+)"', group))
        self.assertEqual(sorted(k for k, how in preview_js.items() if how == "bake"), sorted(baked))
        drawn = sorted(k for k, how in preview_js.items() if how == "draw")
        self.assertEqual(drawn, ["bdf-iso10646", "bitmap", "outline", "outline-composite"])
        self.assertEqual(sorted(k for k, how in preview_js.items() if how not in ("draw", "bake", "none")), [])
        for kind in drawn:
            self.assertTrue(routes.routes(dict(canonical_fonts()[0], source_kind=kind, svf={"bpp": 1})), kind)

        # The validator's source words (settings._SOURCE_WORDS / _SOURCE_ARTICLES) are what the page prints.
        self.assertEqual(js_json_block(js, "SOURCE_WORDS"), settings._SOURCE_WORDS)
        self.assertEqual(js_json_block(js, "SOURCE_ARTICLES"), settings._SOURCE_ARTICLES)

    def test_page_advanced_lists_the_new_keys(self):
        with open(os.path.join(MAKER_DIR, "static", "maker.js"), encoding="utf-8") as f:
            js = f.read()
        for key in ("width", "fit_cell", "latin", "jamo_ascent", "fit_baseline", "aa_refine", "clean", "binarize",
                    "latin_ascent", "hangul_ascent"):
            self.assertRegex(js, r'\{key: "%s", group: "(mkfont|jamoset|bdfface)"' % key)
        self.assertIn('const CHOICE_KEYS = {"binarize": ["threshold", "ridge", "mono"]}', js)
        with open(os.path.join(MAKER_DIR, "static", "index.html"), encoding="utf-8") as f:
            html = f.read()
        for key in ("width", "fit_cell", "latin", "jamo_ascent", "fit_baseline", "aa_refine", "clean", "binarize",
                    "latin_ascent", "hangul_ascent"):
            self.assertIn('data-field="%s"' % key, html)
        if shutil.which("node"):
            self.assertEqual(subprocess.run(["node", "--check", os.path.join(MAKER_DIR, "static", "maker.js")]).returncode, 0)


MAKER_JS = os.path.join(MAKER_DIR, "static", "maker.js")
SVFVIEW_JS = os.path.join(MAKER_DIR, "static", "svfview.js")


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class PreviewWiringTest(unittest.TestCase):
    def test_page_wires_the_preview(self):
        js = read_text(MAKER_JS)
        self.assertIn('import * as svfview from "./svfview.js"', js)
        self.assertNotIn("preview.png", js)
        self.assertIn('"/face/"', js)
        self.assertIn('"/api/repo/face/dos/NEODG16.SVF"', js)
        self.assertIn('/static/wasm/svf.js', read_text(SVFVIEW_JS))
        if shutil.which("node"):
            for path in (MAKER_JS, SVFVIEW_JS):
                self.assertEqual(subprocess.run(["node", "--check", path]).returncode, 0, path)

    def test_page_report_text(self):
        js = read_text(MAKER_JS)
        func = re.search(r"function reportText\(report\) \{.*?\n\}\n", js, re.S).group(0)
        cases = [{"mode": "clip", "counts": {"cut": 2300, "top": 368, "bottom": 2299, "gone": 0}},
                 {"mode": "clip", "counts": {"cut": 4, "top": 1, "bottom": 3, "gone": 2}},
                 {"mode": "nudge", "nudged": ["0x41", "0x42", "0x43"], "counts": {}},
                 {"mode": "fit", "size": 14, "counts": {}}]
        if shutil.which("node"):
            script = "%s\nconsole.log(JSON.stringify(JSON.parse(process.argv[1]).map(reportText)));" % func
            out = subprocess.run(["node", "-e", script, json.dumps(cases)], capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertEqual(json.loads(out.stdout), ["cut 2,300 (368 top, 2,299 bottom)",
                                                      "cut 4 (1 top, 3 bottom), 2 dropped", "nudged 3", "fit at 14 px"])

    def test_page_pieces_panel(self):
        js = read_text(MAKER_JS)
        self.assertIn("identity check unavailable (set SVF_RECOG_DIR to a folder with recog.py and its weights; "
                      "numpy and torch needed)", js)
        self.assertIn('"/identity/"', js)
        self.assertIn("svfview.drawPiece", js)

    def test_page_sample_text_is_detects(self):
        import detect
        m = re.search(r'const SAMPLE_TEXT = "([^"]*)"', read_text(MAKER_JS))
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), detect.SAMPLE_TEXT)

    def test_no_code_but_the_oracle_helpers_writes_preview_png(self):
        for name in ("server.py", "jobs.py", "settings.py", "zipout.py"):
            self.assertNotIn("preview.png", read_text(os.path.join(MAKER_DIR, name)), name)

VF_ENTRY = {"id": "f01", "path": "v/Vary.ttf", "face_index": 0, "source_kind": "outline",
            "variable": {"axes": [{"tag": "wght", "min": 100, "default": 400, "max": 900}],
                         "instances": [{"name": "Bold", "coords": {"wght": 700}}]},
            "licences": [{"path": "v/LICENSE.txt", "first_line": "x"}], "companions": [], "sizes": [16],
            "sizes_fixed": False}


class InstancePageTest(unittest.TestCase):
    def test_page_offers_the_instance_select_and_source_rows(self):
        with open(MAKER_JS, encoding="utf-8") as f:
            js = f.read()
        self.assertIn('el("select", {"data-field": "instance"', js)     # the row builder's exact call
        self.assertIn('step.kind === "source"', js)                     # the steps table's branch
        if shutil.which("node"):
            self.assertEqual(subprocess.run(["node", "--check", MAKER_JS]).returncode, 0)

    def test_kept_settings_keeps_a_valid_instance(self):
        old = {"batch": settings.defaults([VF_ENTRY])["batch"], "fonts": {"f01": {"selected": True, "instance": {"wght": 700}}}}
        kept = server._kept_settings(old, [VF_ENTRY], [VF_ENTRY])
        self.assertEqual(kept["fonts"]["f01"]["instance"], {"wght": 700})
        static = dict(VF_ENTRY)
        del static["variable"]
        kept = server._kept_settings(old, [static], [VF_ENTRY])
        self.assertIsNone(kept["fonts"]["f01"]["instance"])
        other_axis = dict(VF_ENTRY, variable={"axes": [{"tag": "wdth", "min": 75, "default": 100, "max": 100}],
                                              "instances": []})
        self.assertIsNone(server._kept_settings(old, [other_axis], [VF_ENTRY])["fonts"]["f01"]["instance"])
        narrower = dict(VF_ENTRY, variable={"axes": [{"tag": "wght", "min": 100, "default": 400, "max": 600}],
                                            "instances": []})
        self.assertIsNone(server._kept_settings(old, [narrower], [VF_ENTRY])["fonts"]["f01"]["instance"])   # 700 > 600
        for bad in ({"wght": True}, {"wght": "700"}, {"wght": float("nan")}):
            old_bad = {"batch": old["batch"], "fonts": {"f01": {"selected": True, "instance": bad}}}
            self.assertIsNone(server._kept_settings(old_bad, [VF_ENTRY], [VF_ENTRY])["fonts"]["f01"]["instance"], bad)

    def test_changed_preview_fonts_sees_an_instance_change(self):
        before = settings.defaults([VF_ENTRY])
        after = settings.defaults([VF_ENTRY])
        after["fonts"]["f01"]["instance"] = {"wght": 700}
        self.assertEqual(server._changed_preview_fonts([VF_ENTRY], before, after), ["f01"])
        self.assertEqual(server._changed_preview_fonts([VF_ENTRY], before, before), [])


REPO = os.path.dirname(MAKER_DIR)


class FaceBytesTest(ApiBase):
    """Task 6: the byte-serving GETs, /api/caps, the host check on them, the preview keys and mask_ok."""

    def face_url(self, jid, step):
        return "/api/jobs/%s/face/%s.svf" % (jid, step["id"])

    def test_face_bytes_and_etag(self):
        jid = self.minimal_job()
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        step = job["steps"][0]
        r = self.raw("GET", self.face_url(jid, step))
        self.assertEqual((r.status, r.getheader("Content-Type"), r.getheader("Cache-Control")),
                         (200, "application/octet-stream", "no-cache"))
        self.assertEqual(r.read(), read(self.srv.store.path(jid, step["output"])))
        again = self.raw("GET", self.face_url(jid, step), headers={"If-None-Match": r.getheader("ETag")})
        self.assertEqual((again.status, again.read()), (304, b""))

    def test_face_404s(self):
        jid = self.minimal_job()
        job = self.run_to_done(jid)
        step = job["steps"][0]
        other = self.minimal_job()
        self.assertEqual(self.raw("GET", "/api/jobs/%s/face/%s.svf" % (other, step["id"])).status, 404)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/face/s99.svf" % jid).status, 404)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/face/..%%2F%s.svf" % (jid, step["id"])).status, 404)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/face/../%s.svf" % (jid, step["id"])).status, 404)

        def force_prepare(j):
            j["steps"][0]["kind"] = "prepare"
        self.srv.store.update(jid, force_prepare)
        self.assertEqual(self.raw("GET", self.face_url(jid, step)).status, 404)

    def test_face_404_while_the_step_is_not_done(self):
        jid = self.minimal_job()
        job = self.run_to_done(jid)
        step = job["steps"][0]
        self.assertEqual(self.raw("GET", self.face_url(jid, step)).status, 200)

        def rerunning(j):
            j["steps"][0]["state"] = "running"
        self.srv.store.update(jid, rerunning)
        self.assertTrue(os.path.isfile(self.srv.store.path(jid, step["output"])))      # the old file is still there
        self.assertEqual(self.raw("GET", self.face_url(jid, step)).status, 404)

    def test_new_gets_check_host(self):
        jid = self.minimal_job()
        job = self.run_to_done(jid)
        step = job["steps"][0]
        fid = step["font"]
        evil = {"Host": "evil.example"}
        self.assertEqual(self.raw("GET", self.face_url(jid, step), headers=evil).status, 403)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, fid), headers=evil).status, 403)
        self.assertEqual(self.raw("GET", "/api/repo/face/dos/NEODG16.SVF", headers=evil).status, 403)
        self.assertEqual(self.raw("GET", "/api/caps", headers=evil).status, 200)
        self.assertEqual(self.raw("GET", "/static/maker.js", headers=evil).status, 200)

    def test_job_gets_check_host(self):
        jid = self.minimal_job()
        job = self.run_to_done(jid)
        evil = {"Host": "evil.example"}
        for path in ("/api/jobs/%s/zip" % jid, "/api/jobs/%s" % jid,
                     "/api/jobs/%s/preview/%s/source.png" % (jid, job["steps"][0]["font"])):
            self.assertEqual(self.raw("GET", path, headers=evil).status, 403, path)
            self.assertEqual(self.raw("GET", path).status, 200, path)
        self.assertEqual(self.raw("GET", "/", headers=evil).status, 200)

    def test_source_face_of_an_unconfirmed_dos_layout_is_a_404(self):
        jid = self.detected_job()
        job = self.get("/api/jobs/%s" % jid)
        dos = [f["id"] for f in job["fonts"] if f["path"].endswith("HAN.FNT")][0]
        r = self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, dos))
        self.assertEqual(r.status, 404)
        self.assertIn("confirm the DOS Johab layout", r.read().decode())

    def test_identity_endpoint(self):
        jid = self.minimal_job()
        job = self.run_to_done(jid)
        step = job["steps"][0]
        url = "/api/jobs/%s/identity/%s.json" % (jid, step["id"])
        self.assertEqual(self.raw("GET", url).status, 404)                      # a precomposed step: none
        self.assertEqual(self.raw("GET", "/api/jobs/%s/identity/s99.json" % jid).status, 404)

        def as_jamo(j):
            j["steps"][0]["kind"] = "jamo"
        self.srv.store.update(jid, as_jamo)
        with open(self.srv.store.path(jid, "work", step["id"], "identity.json"), "w") as f:
            f.write('{"available": true}')
        r = self.raw("GET", url)
        self.assertEqual((r.status, r.getheader("Content-Type"), r.read()), (200, "application/json", b'{"available": true}'))
        self.assertEqual(self.raw("GET", url, headers={"Host": "evil.example"}).status, 403)

        def running(j):
            j["steps"][0]["state"] = "running"
        self.srv.store.update(jid, running)
        self.assertEqual(self.raw("GET", url).status, 404)

    def test_report_endpoint(self):
        jid = self.minimal_job()
        job = self.run_to_done(jid)
        step = job["steps"][0]
        self.assertTrue(step["report"])
        r = self.raw("GET", "/api/jobs/%s/report/%s.json" % (jid, step["id"]))
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "application/json"))
        self.assertEqual(r.read(), read(self.srv.store.path(jid, step["report"])))
        self.assertEqual(self.raw("GET", "/api/jobs/%s/report/s99.json" % jid).status, 404)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/report/%s.json" % (jid, step["id"]),
                                  headers={"Host": "evil.example"}).status, 403)

        def running(j):
            j["steps"][0]["state"] = "running"
        self.srv.store.update(jid, running)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/report/%s.json" % (jid, step["id"])).status, 404)

        def jamo(j):
            j["steps"][0]["state"] = "done"
            j["steps"][0]["report"] = None
        self.srv.store.update(jid, jamo)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/report/%s.json" % (jid, step["id"])).status, 404)

    def test_repo_face(self):
        self.assertEqual(self.raw("GET", "/api/repo/face/dos/NEODG16.SVF").read(),
                         read(os.path.join(REPO, "svf/dos/NEODG16.SVF")))
        for bad in ("/api/repo/face/dos/neodg16.svf", "/api/repo/face/../NEODG16.SVF", "/api/repo/face/dos/NOPE.SVF",
                    "/api/repo/face/dos/..%2F..%2FREADME.SVF"):
            self.assertEqual(self.raw("GET", bad).status, 404, bad)

    def test_caps_are_booleans_and_follow_the_environment(self):
        self.assertEqual({k: type(v) for k, v in self.get("/api/caps").items()},
                         {"wasm": bool, "mask_libs": bool, "recog": bool})
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "recog.py"), "w").close()
            self.assertEqual(capsmod.recog_dir({"SVF_RECOG_DIR": d}),
                             d if importlib.util.find_spec("numpy") and importlib.util.find_spec("torch") else None)
            self.assertIsNone(capsmod.recog_dir({"SVF_RECOG_DIR": os.path.join(d, "nope")}))
        self.assertIsNone(capsmod.recog_dir({}))
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(capsmod.wasm_built(d))
            os.makedirs(os.path.join(d, "wasm"))
            for name in ("svf.js", "svf.wasm"):
                open(os.path.join(d, "wasm", name), "w").close()
            self.assertTrue(capsmod.wasm_built(d))
        self.assertEqual(capsmod.mask_libs({}), capsmod.mask_libs({"JAMOSET_PYLIB": ""}))

    def test_source_face_served_for_a_dos_raw_font(self):
        jid = self.detected_job()
        job = self.get("/api/jobs/%s" % jid)
        dos = [f["id"] for f in job["fonts"] if f["path"].endswith("HAN.FNT")][0]
        ttf = [f["id"] for f in job["fonts"] if f["path"].endswith("NanumGothic-Bold.ttf")][0]
        s = job["settings"]
        s["fonts"][dos]["dos_layout"] = "844"
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 200)
        r = self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, dos))
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "application/octet-stream"))
        face = jamoset.parse_svfn(r.read())
        self.assertIsNotNone(face.jset)                       # a jamo face
        self.assertEqual(self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, ttf)).status, 404)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/source/f99.svf" % jid).status, 404)

    def test_mask_ok_stamped_on_every_load(self):
        jid = self.minimal_job()
        with mock.patch.dict(self.srv.caps, {"mask_libs": True}):
            fonts = self.get("/api/jobs/%s" % jid)["fonts"]
            self.assertTrue(all(f["mask_ok"] for f in fonts if f["source_kind"].startswith("outline")))
        with mock.patch.dict(self.srv.caps, {"mask_libs": False}):
            self.assertFalse(any(f.get("mask_ok") for f in self.get("/api/jobs/%s" % jid)["fonts"]))

    def mono_settings(self, jid):
        s = self.get("/api/jobs/%s" % jid)["settings"]
        for per in s["fonts"].values():
            per.update(experimental=True, kinds=["jamo"], bpp=[1], options={"jamoset": {"binarize": "mono"}})
        return json.dumps(s).encode()

    def test_mask_ok_reaches_the_settings_put_and_the_run(self):
        """A binarize mono PUT is refused without the mask libraries and accepted with them (the stamp is live)."""
        jid = self.minimal_job()
        body = self.mono_settings(jid)
        with mock.patch.dict(self.srv.caps, {"mask_libs": False}):
            r = self.raw("PUT", "/api/jobs/%s/settings" % jid, body=body)
            self.assertEqual(r.status, 400)
            self.assertIn("binarize mono needs freetype-py", r.read().decode())
        with mock.patch.dict(self.srv.caps, {"mask_libs": True}):
            self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=body).status, 200)
            stored = self.srv.store.load(jid)
            self.assertFalse(any("mask_ok" in f for f in stored["fonts"]))
        # the run re-checks with the live caps: the saved mono choice is refused once the libraries are gone
        with mock.patch.dict(self.srv.caps, {"mask_libs": False}):
            r = self.raw("POST", "/api/jobs/%s/run" % jid)
            self.assertEqual(r.status, 400)
            self.assertIn("binarize mono needs freetype-py", r.read().decode())

    def test_source_preview_draws_the_prepared_font(self):
        jid = self.post("/api/jobs")["id"]
        self.put_file(jid, "v/Vary.ttf", inputfx.variable_ttf())
        self.put_file(jid, "v/OFL.txt", read(F["ttf_licence"]))
        detected = self.post("/api/jobs/%s/detect" % jid)
        fid = next(f["id"] for f in detected["fonts"] if f["source_kind"] == "outline")
        url = "/api/jobs/%s/preview/%s/source.png" % (jid, fid)
        first = self.raw("GET", url)
        self.assertEqual(first.status, 200)
        prepared = self.srv.store.path(jid, "work", "preview", fid, "source.ttf")
        self.assertFalse(os.path.exists(prepared))                    # no ops: the plain source
        s = detected["settings"]
        s["fonts"][fid]["instance"] = {"wght": 900}
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 200)
        second = self.raw("GET", url)
        self.assertEqual(second.status, 200)
        self.assertTrue(os.path.isfile(prepared))                     # the converted copy the build would read
        from fontTools.ttLib import TTFont
        self.assertNotIn("fvar", TTFont(prepared))
        s["fonts"][fid]["instance"] = None
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 200)
        self.assertFalse(os.path.exists(prepared))

    def test_source_preview_of_a_mac_cmap_font(self):
        jid = self.post("/api/jobs")["id"]
        self.put_file(jid, "m/Mac.ttf", inputfx.mac_cmap_ttf())
        self.put_file(jid, "m/OFL.txt", read(F["ttf_licence"]))
        detected = self.post("/api/jobs/%s/detect" % jid)
        fid = next(f["id"] for f in detected["fonts"] if f["source_kind"] == "outline")
        r = self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, fid))
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "image/png"))

    def test_a_saved_mask_route_is_refused_at_the_run_once_the_libraries_are_gone(self):
        jid = self.post("/api/jobs")["id"]
        self.put_file(jid, "g/G.ttf", inputfx.gsub_jamo_ttf())
        self.put_file(jid, "g/OFL.txt", read(F["ttf_licence"]))
        self.post("/api/jobs/%s/detect" % jid)
        s = self.get("/api/jobs/%s" % jid)["settings"]
        for per in s["fonts"].values():
            per.update(dest="new/fixture", experimental=True, kinds=["jamo"], bpp=[1], jamo_route="mask fit", layout="844")
        body = json.dumps(s).encode()
        with mock.patch.dict(self.srv.caps, {"mask_libs": False}):
            r = self.raw("PUT", "/api/jobs/%s/settings" % jid, body=body)       # not offered without the libraries
            self.assertEqual(r.status, 400)
            self.assertIn("mask fit", r.read().decode())
        with mock.patch.dict(self.srv.caps, {"mask_libs": True}):
            self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=body).status, 200)
        with mock.patch.dict(self.srv.caps, {"mask_libs": False}):
            r = self.raw("POST", "/api/jobs/%s/run" % jid)
            self.assertEqual(r.status, 400)
            self.assertIn("mask fit needs freetype-py and uharfbuzz (JAMOSET_PYLIB)", r.read().decode())

    def test_mask_ok_is_not_saved(self):
        jid = self.minimal_job()
        with mock.patch.dict(self.srv.caps, {"mask_libs": True}):
            self.get("/api/jobs/%s" % jid)
        stored = self.srv.store.load(jid)
        self.assertFalse(any("mask_ok" in f for f in stored["fonts"]))

    def test_changed_preview_fonts_new_keys(self):
        font = {"id": "f01", "path": "a.ttf", "face_index": 0, "source_kind": "outline", "sizes": [16],
                "sizes_fixed": False, "licences": [], "companions": []}

        def pair(mutate):
            before = settings.defaults([font])
            after = settings.defaults([font])
            mutate(after["fonts"]["f01"], after["batch"])
            return server._changed_preview_fonts([font], before, after)

        keyed = {"bpp": lambda p, b: p.update(bpp=[2]), "range": lambda p, b: p.update(range="11172"),
                 "preset": lambda p, b: p.update(preset="dos-l-1bpp"),
                 "experimental": lambda p, b: p.update(experimental=True),
                 "jamo_route": lambda p, b: p.update(jamo_route="experimental fit"),
                 "width": lambda p, b: p.update(options={"mkfont": {"width": 20}}),
                 "jamo_ascent": lambda p, b: p.update(options={"jamoset": {"jamo_ascent": 12}}),
                 "batch bpp": lambda p, b: b.update(bpp=[2])}
        for name, mutate in keyed.items():
            self.assertEqual(pair(mutate), ["f01"], name)
        free = {"ascent": lambda p, b: p.update(options={"mkfont": {"ascent": 12}}),
                "clip_cell": lambda p, b: p.update(options={"mkfont": {"clip_cell": True}}),
                "fit_cell": lambda p, b: p.update(options={"mkfont": {"fit_cell": True}}),
                "dy": lambda p, b: p.update(dy={"0x41": 1}),
                "aa_refine": lambda p, b: p.update(options={"jamoset": {"aa_refine": 3}}),
                "latin_ascent": lambda p, b: p.update(options={"bdfface": {"latin_ascent": 12}})}
        for name, mutate in free.items():
            self.assertEqual(pair(mutate), [], name)

    def test_bake_flags(self):
        eff = {"options": {"jamoset": {"jset_version": 2, "jamo_ascent": 13, "embolden": True, "symbols": True}}}
        self.assertEqual(server.Handler._bake_flags(eff, "dos-raw"),
                         ["--jset-version", "2", "--ascent", "13", "--embolden", "--symbols"])
        self.assertEqual(server.Handler._bake_flags(eff, "svf-jamo"), ["--jset-version", "2"])
        self.assertEqual(server.Handler._bake_flags({"options": {}}, "dos-raw"), [])

    def test_static_wasm_type_and_cache(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(os.path.join(MAKER_DIR, "static"), os.path.join(d, "static"), ignore=shutil.ignore_patterns("wasm"))
            os.makedirs(os.path.join(d, "static", "wasm"))
            with open(os.path.join(d, "static", "wasm", "svf.wasm"), "wb") as f:
                f.write(b"\0asm\1\0\0\0")
            self.srv.static_dir = os.path.join(d, "static")
            r = self.raw("GET", "/static/wasm/svf.wasm")
            self.assertEqual((r.status, r.getheader("Content-Type"), r.getheader("Cache-Control")),
                             (200, "application/wasm", "no-cache"))
            self.assertTrue(r.getheader("ETag"))
            self.assertEqual(self.raw("GET", "/static/wasm/svf.wasm", headers={"If-None-Match": r.getheader("ETag")}).status, 304)


class ProbeTest(ApiBase):
    """Task 11: the clipping probe, baked once from the step's own argv and dropped by the keyed settings."""

    def tall_job(self, sizes=(16,), span=(-180, 740), **per):
        jid = self.post("/api/jobs")["id"]
        self.put_file(jid, "tall/Tall.ttf", inputfx.tall_ttf(span))
        self.put_file(jid, "tall/OFL.txt", read(F["ttf_licence"]))
        self.post("/api/jobs/%s/detect" % jid)
        s = self.get("/api/jobs/%s" % jid)["settings"]
        for fid in s["fonts"]:
            s["fonts"][fid].update(dest="new/fixture", sizes=list(sizes), bpp=[1], **per)
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 200)
        self.fid = next(iter(s["fonts"]))
        return jid

    def put_settings(self, jid, mutate):
        s = self.get("/api/jobs/%s" % jid)["settings"]
        mutate(s["fonts"][self.fid], s["batch"])
        r = self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode())
        self.assertEqual(r.status, 200, r.read())

    def probe_dir(self, jid):
        return self.srv.store.path(jid, "work", "preview", self.fid, "probe")

    def url(self, jid, size=16, bpp=1, ext="json"):
        return "/api/jobs/%s/probe/%s/%d/%d.%s" % (jid, self.fid, size, bpp, ext)

    def test_probe_bakes_once(self):
        jid = self.tall_job(options={"mkfont": {"width": 16}})
        r1 = self.raw("GET", self.url(jid))
        path = os.path.join(self.probe_dir(jid), "16-1.json")
        m1 = os.stat(path).st_mtime_ns
        self.raw("GET", self.url(jid))
        self.assertEqual((r1.status, os.stat(path).st_mtime_ns), (200, m1))
        rep = json.loads(r1.read())
        self.assertTrue(rep["probe"])
        self.assertIsNone(rep["step_ascent"])
        face = self.raw("GET", self.url(jid, ext="svf"))
        self.assertEqual((face.status, face.getheader("Content-Type")), (200, "application/octet-stream"))
        self.assertEqual(jamoset.parse_svfn(face.read()).cell_h, rep["cell"][1])

    def test_step_ascent_is_the_merged_argvs(self):
        jid = self.tall_job(options={"mkfont": {"ascent": 11, "clip_cell": True}})
        self.assertEqual(json.loads(self.raw("GET", self.url(jid)).read())["step_ascent"], 11)

    def test_the_probe_cell_is_the_effective_one(self):
        jid = self.tall_job(options={"mkfont": {"cell": 12, "width": 16}})
        rep = json.loads(self.raw("GET", self.url(jid)).read())
        # auto_ascent is mkfont's own choice for the user's cell (12), not the tall probe cell
        boxes = {int(k, 16): v for k, v in rep["boxes"].items()}
        import mkfont
        from PIL import ImageFont
        font = ImageFont.truetype(os.path.join(self.srv.store.path(jid, "upload"), "tall", "Tall.ttf"), 16)
        self.assertEqual(rep["auto_ascent"], mkfont.fit_ascent(boxes, 12, mkfont.choose_ascent(font, 12, False))[0])

    def test_keyed_put_drops_the_probe(self):
        jid = self.tall_job()
        keyed = {"width": lambda p, b: p.update(options={"mkfont": {"width": 20}}),
                 "cell": lambda p, b: p.update(options={"mkfont": {"cell": 12}}),
                 "latin": lambda p, b: p.update(options={"mkfont": {"latin": True}}),
                 "mono_hint": lambda p, b: p.update(options={"mkfont": {"mono_hint": True}}),
                 "space_advance": lambda p, b: p.update(options={"mkfont": {"space_advance": 5}}),
                 "range": lambda p, b: p.update(range="11172"),
                 "preset": lambda p, b: p.update(preset="dos-l-1bpp")}
        for name, mutate in keyed.items():
            self.put_settings(jid, lambda p, b: p.update(options={}, range="2350", preset="plain"))
            self.assertEqual(self.raw("GET", self.url(jid)).status, 200, name)
            self.assertTrue(os.path.isdir(self.probe_dir(jid)), name)
            self.put_settings(jid, mutate)
            self.assertFalse(os.path.exists(self.probe_dir(jid)), name)

    def test_ascent_put_keeps_the_probe(self):
        jid = self.tall_job()
        self.assertEqual(self.raw("GET", self.url(jid)).status, 200)
        for mutate in (lambda p, b: p.update(options={"mkfont": {"ascent": 10}}),
                       lambda p, b: p.update(options={"mkfont": {"ascent": 10, "clip_cell": True}}),
                       lambda p, b: p.update(options={"mkfont": {"fit_cell": True}})):
            self.put_settings(jid, mutate)
            self.assertTrue(os.path.isfile(os.path.join(self.probe_dir(jid), "16-1.json")))

    def test_probe_without_face(self):
        # glyphs 30 em tall: at 96 px the ink spans past 255 rows, the largest size a font may be set to is 96
        jid = self.tall_job(sizes=(96,), span=(-15000, 15000))
        r = self.raw("GET", self.url(jid, size=96))
        self.assertEqual(r.status, 200)
        self.assertIs(json.loads(r.read())["probe_face"], False)
        self.assertEqual(self.raw("GET", self.url(jid, size=96, ext="svf")).status, 404)

    def test_the_probe_reports_the_steps_own_cell(self):
        """A preset's --cell (dos-u-2bpp 16, latin-18cell-2bpp 18) is the cell the build cuts at: the JSON says so."""
        for preset, size, bpp, cell in (("dos-u-2bpp", 17, 2, 16), ("latin-18cell-2bpp", 16, 2, 18), ("plain", 16, 1, 16),
                                        ("dos-l-1bpp", 20, 1, 16)):
            with self.subTest(preset=preset):
                jid = self.post("/api/jobs")["id"]
                self.put_file(jid, "tall/Tall.ttf", inputfx.tall_ttf())
                self.put_file(jid, "tall/OFL.txt", read(F["ttf_licence"]))
                self.post("/api/jobs/%s/detect" % jid)
                s = self.get("/api/jobs/%s" % jid)["settings"]
                fid = next(iter(s["fonts"]))
                s["fonts"][fid].update(dest="new/fixture", sizes=[size], bpp=[bpp], preset=preset)
                self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 200)
                rep = json.loads(self.raw("GET", "/api/jobs/%s/probe/%s/%d/%d.json" % (jid, fid, size, bpp)).read())
                self.assertEqual(rep["step_cell"], cell)
        jid = self.tall_job(options={"mkfont": {"cell": 12}})
        self.assertEqual(json.loads(self.raw("GET", self.url(jid)).read())["step_cell"], 12)

    def test_a_cached_probe_get_writes_no_range_files(self):
        jid = self.tall_job()
        self.assertEqual(self.raw("GET", self.url(jid)).status, 200)
        self.assertEqual(sorted(os.listdir(self.probe_dir(jid))), ["16-1.json", "16-1.svf"])
        self.assertEqual(self.raw("GET", self.url(jid)).status, 200)
        self.assertEqual(sorted(os.listdir(self.probe_dir(jid))), ["16-1.json", "16-1.svf"])

    def test_the_probe_url_takes_no_leading_zeros(self):
        jid = self.tall_job()
        self.assertEqual(self.raw("GET", "/api/jobs/%s/probe/%s/016/1.json" % (jid, self.fid)).status, 404)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/probe/%s/16/01.json" % (jid, self.fid)).status, 404)

    def font_job(self, files, pick, **per):
        """A detected job over @p files (rel -> bytes) with the font entry chosen by @p pick selected into new/fixture."""
        jid = self.post("/api/jobs")["id"]
        for rel, data in files.items():
            self.put_file(jid, rel, data)
        self.put_file(jid, os.path.dirname(next(iter(files))) + "/OFL.txt", read(F["ttf_licence"]))
        detected = self.post("/api/jobs/%s/detect" % jid)
        fid = next(f["id"] for f in detected["fonts"] if pick(f))
        s = detected["settings"]
        for k, p in s["fonts"].items():
            p["selected"] = k == fid
        s["fonts"][fid].update(dest="new/fixture", sizes=[16], bpp=[1], **per)
        self.assertEqual(self.raw("PUT", "/api/jobs/%s/settings" % jid, body=json.dumps(s).encode()).status, 200)
        self.fid = fid
        return jid

    def boxes_probe_vs_build(self, jid):
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        step = next(st for st in job["steps"] if st["kind"] == "precomposed")
        built = json.loads(self.raw("GET", "/api/jobs/%s/report/%s.json" % (jid, step["id"])).read())["boxes"]
        probed = json.loads(self.raw("GET", self.url(jid)).read())["boxes"]
        return built, probed

    def test_the_probe_measures_the_prepared_source(self):
        """The probe reads the file the build reads: a variable instance, a TTC face, a Mac cmap font."""
        two = inputfx.ttc([inputfx.ttf("One", (50, 0, 950, 800)), inputfx.ttf("Two", (300, 0, 700, 400))])
        cases = (("instance", {"v/Vary.ttf": inputfx.variable_ttf(-600)}, lambda f: f["source_kind"] == "outline",
                  {"instance": {"wght": 900}}),
                 ("ttc face 1", {"t/two.ttc": two}, lambda f: f["face_index"] == 1, {}),
                 ("mac cmap", {"m/Mac.ttf": inputfx.mac_cmap_ttf()}, lambda f: f["source_kind"] == "outline", {}))
        for name, files, pick, per in cases:
            with self.subTest(name):
                jid = self.font_job(files, pick, **per)
                built, probed = self.boxes_probe_vs_build(jid)
                self.assertTrue(built)
                self.assertEqual(probed, built)
        # and the instance changes what is measured
        plain = json.loads(self.raw("GET", self.url(self.font_job({"v/Vary.ttf": inputfx.variable_ttf(-600)}, lambda f: f["source_kind"] == "outline",
                                                                   instance={"wght": 100}))).read())["boxes"]
        wide = json.loads(self.raw("GET", self.url(self.font_job({"v/Vary.ttf": inputfx.variable_ttf(-600)}, lambda f: f["source_kind"] == "outline",
                                                                 instance={"wght": 900}))).read())["boxes"]
        self.assertNotEqual(plain, wide)

    def test_the_instance_is_applied_in_a_bounded_subprocess(self):
        """The prepared source of a variable instance runs the build's instancer command with the preview time limit; one
        that runs out of time is 'no preview' and leaves no half-made copy."""
        jid = self.font_job({"v/Vary.ttf": inputfx.variable_ttf(-600)}, lambda f: f["source_kind"] == "outline",
                            instance={"wght": 900})
        with mock.patch.object(server.preview, "TIMEOUT_S", 0.01):
            self.assertEqual(self.raw("GET", self.url(jid)).status, 404)
            r = self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, self.fid))
            self.assertEqual(r.status, 404)
        self.assertEqual([n for n in os.listdir(os.path.join(self.srv.store.path(jid, "work", "preview", self.fid)))
                          if n.startswith("source")], [])
        self.assertEqual(self.raw("GET", self.url(jid)).status, 200)                # and with the time it takes

    def test_probe_404s(self):
        jid = self.tall_job()
        self.assertEqual(self.raw("GET", self.url(jid, size=17)).status, 404)          # a size not selected
        self.assertEqual(self.raw("GET", self.url(jid, bpp=2)).status, 404)            # a bpp not selected
        self.assertEqual(self.raw("GET", self.url(jid, bpp=3)).status, 404)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/probe/f99/16/1.json" % jid).status, 404)
        self.assertEqual(self.raw("GET", self.url(jid), headers={"Host": "evil.example"}).status, 403)

    def test_probe_404_for_a_dos_raw_font(self):
        jid = self.detected_job()
        dos = [f["id"] for f in self.get("/api/jobs/%s" % jid)["fonts"] if f["path"].endswith("HAN.FNT")][0]
        self.assertEqual(self.raw("GET", "/api/jobs/%s/probe/%s/16/1.json" % (jid, dos)).status, 404)

    def test_probe_face_draws_with_nothing_cut(self):
        """The probe face is the full ink: every box row lies inside it, so no row the cell could want is missing."""
        jid = self.tall_job(options={"mkfont": {"width": 16}})
        rep = json.loads(self.raw("GET", self.url(jid)).read())
        face = jamoset.parse_svfn(self.raw("GET", self.url(jid, ext="svf")).read())
        import mkfont
        boxes = {int(k, 16): v for k, v in rep["boxes"].items()}
        self.assertEqual(mkfont.fit_counts(boxes, face.cell_w, face.cell_h, face.ascent), ([], [], []))
        for cp, (left, top, right, bottom) in boxes.items():
            rows = [i for i in range(face.cell_h) if any(face.glyphs[cp][i * ((face.cell_w + 7) // 8):(i + 1) * ((face.cell_w + 7) // 8)])]
            self.assertEqual((rows[0] - face.ascent, rows[-1] + 1 - face.ascent), (top, bottom), hex(cp))


if __name__ == "__main__":
    unittest.main()


class KeptCompanionTest(unittest.TestCase):
    """Z1: a kept latin_companion is an id too, so a renumbering re-detect remaps it by the companion's path."""

    def _fonts(self, paths, ksc="k/ksc.bdf"):
        fonts = []
        for i, p in enumerate(sorted(paths + [ksc])):
            fonts.append({"id": "f%02d" % (i + 1), "path": p, "face_index": 0})
        latin = [f["id"] for f in fonts if f["path"] != ksc]
        for f in fonts:
            f["companions"] = latin if f["path"] == ksc else []
        return fonts

    def test_companion_follows_its_path(self):
        import server, settings
        old_fonts = self._fonts(["z/iso3.bdf", "y/iso.bdf"])
        ksc_old = next(f for f in old_fonts if f["path"] == "k/ksc.bdf")
        pick = next(f["id"] for f in old_fonts if f["path"] == "z/iso3.bdf")
        orig_defaults = settings.defaults
        settings.defaults = lambda fonts: {"batch": {}, "fonts": {f["id"]: {"latin_companion": (f["companions"] or [None])[0]} for f in fonts}}
        try:
            old = {"batch": {}, "fonts": {ksc_old["id"]: {"latin_companion": pick, "selected": True}}}
            new_fonts = self._fonts(["z/iso3.bdf", "y/iso.bdf", "a/1.bdf", "a/2.bdf"])
            kept = server._kept_settings(old, new_fonts, old_fonts)
            ksc_new = next(f for f in new_fonts if f["path"] == "k/ksc.bdf")
            want = next(f["id"] for f in new_fonts if f["path"] == "z/iso3.bdf")
            self.assertEqual(kept["fonts"][ksc_new["id"]]["latin_companion"], want)
            self.assertTrue(kept["fonts"][ksc_new["id"]]["selected"])
            new_fonts2 = self._fonts(["y/iso.bdf", "a/1.bdf"])     # the picked companion is gone: fall back to default
            kept2 = server._kept_settings(old, new_fonts2, old_fonts)
            ksc2 = next(f for f in new_fonts2 if f["path"] == "k/ksc.bdf")
            self.assertEqual(kept2["fonts"][ksc2["id"]]["latin_companion"], ksc2["companions"][0])
        finally:
            settings.defaults = orig_defaults
