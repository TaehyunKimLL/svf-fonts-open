#!/usr/bin/env python3
"""Fixtures and the server base for the local-mode tests (`test_local.py`).

Everything is synthetic and built inside the test: `local_tree` writes five small files, `LocalBase` starts a server
with a per-launch token over a temp data root, and `api` sends the token header the way the Electron shell will.
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gzip
import http.client
import json
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
import unittest

import fixtures
import inputfx
import server

TOKEN = "0123456789abcdef0123456789abcdef"
WAIT_S = 180


def local_tree(tmp, mac=False):
    """`tmp/in/a/` a TTF + OFL.txt, `tmp/in/b/` a DOS raw 844 16 px + an 8x16 eng, `tmp/in/c/hanterm.bdf.gz` (a
    johab BDF gzipped): five files. Returns `{"in", "out" (made), "roots": [a, b, c]}`. With @p mac, `tmp/in/mac/`
    also holds the synthetic Mac files (every wrapping of a 7.1 fbit, an HTBL 1 and a suitcase) and the result has
    `"mac"`: that folder (it is not among `roots`)."""
    tmp = os.path.realpath(tmp)
    a, b, c = (os.path.join(tmp, "in", name) for name in "abc")
    for d in (a, b, c, os.path.join(tmp, "out")):
        os.makedirs(d, exist_ok=True)
    with open(os.path.join(a, "Munjo.ttf"), "wb") as f:
        f.write(inputfx.ttf("Munjo", (50, 0, 950, 800)))
    with open(os.path.join(a, "OFL.txt"), "w", encoding="utf-8") as f:
        f.write("SIL Open Font License, Version 1.1\n")
    fixtures._dos_raw(os.path.join(b, "HAN.FNT"))
    fixtures._eng(os.path.join(b, "ENG.FNT"))
    raw = os.path.join(tmp, "johab.bdf")
    fixtures._bdf(raw, fixtures._johab_glyphs(), 16, 13, 3, "johab", (16, 16))
    with open(raw, "rb") as f, open(os.path.join(c, "hanterm.bdf.gz"), "wb") as g:
        g.write(gzip.compress(f.read(), mtime=0))
    os.remove(raw)
    result = {"in": os.path.join(tmp, "in"), "out": os.path.join(tmp, "out"), "roots": [a, b, c]}
    if mac:
        result["mac"] = mac_tree(os.path.join(tmp, "in", "mac"))
    return result


def mac_tree(root):
    """The synthetic Mac files of the 7.1 tests under @p root; returns @p root."""
    import macfx
    files = {
        "Seoul12.rsrc": macfx.fbit3_fork(1), "InputBackSupport.rsrc": macfx.htbl_fork(1),
        "Suitcase.rsrc": macfx.suitcase(12),
        "ad/._Seoul12": macfx.appledouble(macfx.fbit3_fork(1)),
        "ad/._InputBackSupport": macfx.appledouble(macfx.htbl_fork(1)),
        "mb/Seoul12.bin": macfx.macbinary(macfx.fbit3_fork(1)), "mb/IBS.bin": macfx.macbinary(macfx.htbl_fork(1)),
        "jm/Seoul12": macfx.jm(macfx.fbit3_fork(1)),
        "raw/Seoul12.fbit": macfx.fbit3_raw(1), "raw/Seoul12.htbl1": macfx.htbl_raw(1),
        "nfnt/Only.rsrc": macfx.nfnt_only(),
        "gz/Seoul12.rsrc.gz": gzip.compress(macfx.fbit3_fork(1), mtime=0),
        # HangulTalk 1.0 (the 45-set fbit with its fdef): raw fork, AppleDouble, MacBinary, and the bare resource
        "v1/Munjo16.rsrc": macfx.fbit1_fork(), "v1/ad/._Munjo16": macfx.appledouble(macfx.fbit1_fork()),
        "v1/mb/Munjo16.bin": macfx.macbinary(macfx.fbit1_fork()), "v1/raw/Munjo16.fbit": macfx.fbit1_raw(),
    }
    for rel, data in files.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
    return root


def walk_rel(root, skip_prefix=None):
    """The `/`-separated relative paths of every file under @p root, leaving out a top-level directory whose name starts
    with @p skip_prefix."""
    out = set()
    for dirpath, dirnames, filenames in os.walk(root):
        if skip_prefix and os.path.abspath(dirpath) == os.path.abspath(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(skip_prefix)]
        for name in filenames:
            out.add(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return out


def read_only(test, path):
    """chmod dirs 0o555 and files 0o444 under @p path; a cleanup restores 0o755/0o644."""
    def walk(mode_dir, mode_file):
        for dirpath, dirnames, filenames in os.walk(path, topdown=False):
            for name in filenames:
                os.chmod(os.path.join(dirpath, name), mode_file)
            os.chmod(dirpath, mode_dir)
    walk(0o555, 0o444)
    test.addCleanup(walk, 0o755, 0o644)


class LocalBase(unittest.TestCase):
    """A token server over a temp data root, plus a `local_tree`. Subclasses add the tests."""

    def setUp(self):
        self._umask = os.umask(0o022)
        os.umask(self._umask)
        self.addCleanup(os.umask, self._umask)
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="svf-local-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.data = os.path.join(self.tmp, "data")
        self.tree = local_tree(os.path.join(self.tmp, "tree"))
        self.out = self.tree["out"]
        self.roots = self.tree["roots"]
        self.srv = server.make_server("127.0.0.1", 0, fixtures.REPO_DIR, self.data, token=TOKEN)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)

    def _stop(self):
        deadline = time.monotonic() + 30
        for item in self.srv.store.list():
            while time.monotonic() < deadline and self.srv.worker.cancel(item["id"]) != "not running":
                time.sleep(0.05)
        self.srv.shutdown()
        self.srv.worker.stop()
        self.srv.server_close()
        self.thread.join(30)

    # ---- helpers ------------------------------------------------------------------------------------------

    def raw(self, method, path, body=None, headers=None, token=True):
        head = dict(headers or {})
        if token:
            head.setdefault("X-Maker-Token", TOKEN)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=WAIT_S)
        try:
            conn.request(method, path, body=body, headers=head)
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()

    def api(self, method, path, obj=None, headers=None):
        """`(status, parsed JSON)` of a JSON request."""
        body = None if obj is None else json.dumps(obj).encode("utf-8")
        status, _headers, data = self.raw(method, path, body=body, headers=headers)
        try:
            return status, json.loads(data)
        except ValueError:
            return status, data

    def new_job(self, out=None):
        status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": out or self.out})
        self.assertEqual(status, 200, body)
        return body["id"]

    def local_job(self, roots=None, out=None):
        """Create, put the sources and detect; returns the job id."""
        jid = self.new_job(out)
        status, body = self.api("PUT", "/api/jobs/%s/sources" % jid, {"paths": roots or self.roots})
        self.assertEqual(status, 200, body)
        status, body = self.api("POST", "/api/jobs/%s/detect" % jid)
        self.assertEqual(status, 200, body)
        return jid

    def job(self, jid):
        return self.api("GET", "/api/jobs/%s" % jid)[1]

    def owns(self, jid):
        """The worker still holds the job (its completion cleanup has not run)."""
        return self.srv.worker.owns(jid)

    def wait_done(self, jid):
        deadline = time.monotonic() + WAIT_S
        while time.monotonic() < deadline:
            job = self.job(jid)
            if job["state"] in ("done", "failed") and not self.owns(jid):
                return self.job(jid)                         # the worker has also finished its completion cleanup
            time.sleep(0.1)
        self.fail("job %s did not finish" % jid)

    def run_to_done(self, jid):
        status, body = self.api("POST", "/api/jobs/%s/run" % jid)
        self.assertEqual(status, 200, body)
        return self.wait_done(jid)

    def rerun(self, jid, edit=None):
        """The only path from `done`: detect, `edit(settings)`, `PUT settings`, run, wait."""
        self.assertEqual(self.api("POST", "/api/jobs/%s/detect" % jid)[0], 200)
        st = self.job(jid)["settings"]
        if edit:
            edit(st)
        status, body = self.api("PUT", "/api/jobs/%s/settings" % jid, st)
        self.assertEqual(status, 200, body)
        return self.run_to_done(jid)

    def files_dir(self, jid):
        return os.path.join(self.out, ".svf-maker-" + jid)


class LocalRunBase(LocalBase):
    """Select the TTF of `a` (mkfont 16 px 1 bpp, dest `dos`, its OFL.txt) and the DOS raw font of `b` (844, jamo, dest
    `jamo-extra`, no licence: a local job does not need one), then run."""

    def select(self, jid, edit=None):
        job = self.job(jid)
        st = job["settings"]
        by = {(f["root"], f["path"]): f["id"] for f in job["fonts"]}
        self.ttf, self.dos, self.eng = by[(0, "Munjo.ttf")], by[(1, "HAN.FNT")], by[(1, "ENG.FNT")]
        st["fonts"][self.ttf].update(selected=True, dest="dos", kinds=["precomposed"], sizes=[16], bpp=[1])
        st["fonts"][self.dos].update(selected=True, dest="jamo-extra", kinds=["jamo"], dos_layout="844")
        if edit:
            edit(st)
        status, body = self.api("PUT", "/api/jobs/%s/settings" % jid, st)
        self.assertEqual(status, 200, body)

    def select_johab844(self, jid):
        """`b/HAN.FNT` also as a `precomposed` 16 px 1 bpp face with `b/ENG.FNT` as its English font, dest `dos`: the
        johab844 route (routes.py: a DOS raw 844 font with an 8x16 English font). Call after `select`."""
        job = self.job(jid)
        st = job["settings"]
        st["fonts"][self.dos].update(kinds=["jamo", "precomposed"], sizes=[16], bpp=[1], latin_companion=self.eng)
        status, body = self.api("PUT", "/api/jobs/%s/settings" % jid, st)
        self.assertEqual(status, 200, body)

    def done_job(self, edit=None):
        jid = self.local_job()
        self.select(jid, edit)
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        return jid, job

    def read_out(self, rel):
        with open(os.path.join(self.out, rel), "rb") as f:
            return f.read()


class SubprocessLocalBase(LocalBase):
    """`LocalBase` over a server in a subprocess: `[SVF_MAKER_SIDECAR, "serve"]` (the frozen sidecar) with the scrubbed
    environment a shell would give it. `self.proc`, `self.port`, `self.data`, `self.tmp` as `LocalBase`; no `self.srv`."""

    repo = fixtures.REPO_DIR

    def extra_env(self):
        return {}

    def setUp(self):
        self._umask = os.umask(0o022)
        os.umask(self._umask)
        self.addCleanup(os.umask, self._umask)
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="svf-sub-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.data = os.path.join(self.tmp, "data")
        self.tree = local_tree(os.path.join(self.tmp, "tree"))
        self.out = self.tree["out"]
        self.roots = self.tree["roots"]
        self._final_since = {}
        self.start_server()
        self.addCleanup(self._stop)

    def start_server(self):
        exe = os.environ["SVF_MAKER_SIDECAR"]
        empty = os.path.join(self.tmp, "empty-path")
        os.makedirs(empty, exist_ok=True)
        env = {"PATH": empty, "HOME": os.environ.get("HOME", "/"), "LANG": "C.UTF-8", "SVF_MAKER_TOKEN": TOKEN,
               "SVF_MAKER_BIND": "127.0.0.1:0", "SVF_MAKER_DATA": self.data, "SVF_MAKER_REPO": self.repo}
        env.update(self.extra_env())
        self.out_path = os.path.join(self.tmp, "serve.out")
        self.err_path = os.path.join(self.tmp, "serve.err")
        self.started_at = time.monotonic()
        with open(self.out_path, "wb") as out, open(self.err_path, "wb") as err:
            self.proc = subprocess.Popen([exe, "serve"], env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        self.addCleanup(self._kill)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            text = open(self.out_path, encoding="utf-8", errors="replace").read()
            if "listening on" in text:
                self.port_seconds = time.monotonic() - self.started_at
                self.port = int(text.split("listening on", 1)[1].split()[0].rsplit(":", 1)[1])
                return
            if self.proc.poll() is not None:
                self.fail("the sidecar exited %s: %s" % (self.proc.returncode, open(self.err_path).read()[-500:]))
            time.sleep(0.02)
        self.fail("no port line")

    def _kill(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()

    def _stop(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(60)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

    def owns(self, jid):
        """False once the job's state has been final on two polls 0.2 s apart (the cleanup is done by then)."""
        if self.job(jid)["state"] not in ("done", "failed"):
            self._final_since.pop(jid, None)
            return True
        first = self._final_since.setdefault(jid, time.monotonic())
        return time.monotonic() - first < 0.2


def normalise_job(out_dir, job, repo=None, tmp=None):
    """What two runs of one job must share: the files (job ids replaced), the sha256 of every written face, and each
    step's command as a note shows it (paths of the run's directories replaced)."""
    import hashlib
    import re
    import toolrun
    jid = job["id"]

    def norm(text):
        text = text.replace(jid, "<id>")
        if tmp:
            text = text.replace(os.path.realpath(tmp), "<T>").replace(tmp, "<T>")
        return text
    files = sorted(norm(f) for f in job["result"]["files"])
    faces = {}
    for f in job["result"]["files"]:
        if f.endswith(".SVF"):
            with open(os.path.join(out_dir, f), "rb") as fh:
                faces[norm(f)] = hashlib.sha256(fh.read()).hexdigest()
    commands = []
    for step in job["steps"]:
        for argv in step.get("argv") or []:
            commands.append([norm(t) if isinstance(t, str) else t for t in toolrun.note_argv(argv, repo)])
    return {"files": files, "faces": faces, "commands": commands}


def mode_of(path):
    return stat.S_IMODE(os.stat(path).st_mode)
