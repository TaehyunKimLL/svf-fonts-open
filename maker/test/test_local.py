#!/usr/bin/env python3
"""Local mode: path-checked sources and output folder, the files directory, the scan over roots, the run that writes
a folder tree, the sweeps. Every file is built inside the test.

  python3 -m unittest discover -s maker/test -p 'test_local.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hashlib
import json
import re
import shutil
import tempfile
import unittest
from unittest import mock

import fixtures
import localfx
import preview
import server
from localfx import LocalBase, mode_of, walk_rel


class LocalJobTest(LocalBase):
    def test_create_local_job(self):
        status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out})
        self.assertEqual(status, 200)
        jid = body["id"]
        job = self.srv.store.load(jid)
        self.assertEqual((job["source"], job["output_dir"], job["roots"], job["owned"]), ("local", self.out, [], {}))
        self.assertEqual(sorted(os.listdir(self.srv.store.path(jid))), ["job.json"])
        self.assertEqual(mode_of(self.files_dir(jid)), 0o700)
        self.assertEqual(mode_of(os.path.join(self.files_dir(jid), "work", "tmp")), 0o700)
        self.assertEqual(self.srv.store.list()[0]["source"], "local")
        self.assertEqual(self.srv.store.list()[0]["output_id"], job["output_id"])

    def test_local_mode_is_off_without_the_token(self):
        data = os.path.join(self.tmp, "data2")
        srv = server.make_server("127.0.0.1", 0, fixtures.REPO_DIR, data)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.worker.stop)
        import threading
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=30)
        conn.request("POST", "/api/jobs", body=json.dumps({"source": "local", "output_dir": self.out}).encode())
        resp = conn.getresponse()
        self.assertEqual((resp.status, json.loads(resp.read())["error"]), (403, "local mode is off"))

    def put_sources(self, jid, paths):
        return self.api("PUT", "/api/jobs/%s/sources" % jid, {"paths": paths})

    def refused_reasons(self, body):
        return {os.path.basename(item["path"]) or item["path"]: item["reason"] for item in body["refused"]}

    def test_path_rules(self):
        jid = self.new_job()
        a, b = self.roots[0], self.roots[1]
        os.symlink(a, os.path.join(self.tmp, "ln"))
        os.mkfifo(os.path.join(self.tmp, "fifo"))
        sub = os.path.join(self.out, "sub")
        os.makedirs(sub)
        cases = [("in/a", "not an absolute path"),
                 (os.path.join(self.tmp, "ln"), "the path is a symlink"),
                 (os.path.join(self.data, "jobs"), "the data folder cannot be chosen"),
                 (self.tmp, "the data folder cannot be chosen"),
                 (sub, "the output folder must not overlap an input"),
                 (self.out, "the output folder must not overlap an input"),
                 ("/", "/ cannot be chosen"),
                 (os.path.join(self.tmp, "nope"), "no such file or folder"),
                 (os.path.join(self.tmp, "fifo"), "not a regular file or folder"),
                 ("/" + "x" * 5000, "path too long"),
                 (a + "\0x", "NUL in path")]
        for path, reason in cases:
            status, body = self.put_sources(jid, [path])
            self.assertEqual(status, 200, path)
            self.assertEqual([item["reason"] for item in body["refused"]], [reason], path)
            self.assertEqual(body["roots"], [], path)
        # two inputs that overlap: the second is refused
        status, body = self.put_sources(jid, [a, os.path.join(a, "Munjo.ttf")])
        self.assertEqual([r["reason"] for r in body["refused"]], ["overlaps another input"])
        self.assertEqual([r["path"] for r in body["roots"]], [a])
        # SVF_MAKER_ROOTS
        with mock.patch.dict(os.environ, {"SVF_MAKER_ROOTS": a}):
            status, body = self.put_sources(jid, [a, b])
            self.assertEqual([r["reason"] for r in body["refused"]], ["outside SVF_MAKER_ROOTS"])
            self.assertEqual([r["path"] for r in body["roots"]], [a])
            status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": os.path.join(self.tmp, "tree", "in")})
            self.assertEqual((status, body["error"]), (400, "output folder: outside SVF_MAKER_ROOTS"))
        # a bad output folder
        status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": os.path.join(self.tmp, "nope")})
        self.assertEqual((status, body["error"]), (400, "output folder: no such file or folder"))
        status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": os.path.join(a, "Munjo.ttf")})
        self.assertEqual((status, body["error"]), (400, "output folder: not a folder"))
        # PUT files on a local job, PUT sources on an upload job
        status, body = self.raw("PUT", "/api/jobs/%s/files?path=x.ttf" % jid, body=b"x")[0::2]
        self.assertEqual((status, json.loads(body)["error"]), (409, "job %s is a local job" % jid))
        up = self.api("POST", "/api/jobs")[1]["id"]
        status, body = self.put_sources(up, [a])
        self.assertEqual((status, body["error"]), (409, "job %s is an upload job" % up))

    def test_path_rules_overlap_by_inode(self):
        alias = os.path.join(self.tmp, "alias")
        os.symlink(self.tmp, alias)
        src = os.path.join(self.tmp, "tree", "in")
        out = os.path.join(alias, "tree", "in", "out")
        os.makedirs(out)
        jid = self.new_job(out)                                   # the output itself is a fine folder
        status, body = self.put_sources(jid, [src])
        self.assertEqual([r["reason"] for r in body["refused"]], ["the output folder must not overlap an input"])
        self.assertEqual(body["roots"], [])

    def test_one_job_per_output_folder_at_create(self):
        a = self.local_job()
        status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out})
        self.assertEqual((status, body["error"]), (409, "output folder is in use by job %s" % a))
        self.api("DELETE", "/api/jobs/%s" % a)
        self.assertEqual(self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out})[0], 200)

    def test_put_sources_and_detect(self):
        jid = self.new_job()
        status, body = self.put_sources(jid, self.roots)
        self.assertEqual(status, 200)
        self.assertEqual([(r["path"], r["kind"], r["name"]) for r in body["roots"]],
                         [(p, "dir", os.path.basename(p)) for p in self.roots])
        self.assertEqual((body["files"], body["refused"]), (5, []))
        self.assertGreater(body["bytes"], 0)
        job = self.api("POST", "/api/jobs/%s/detect" % jid)[1]
        self.assertEqual(job["state"], "detected")
        fonts = job["fonts"]
        self.assertEqual([f["id"] for f in fonts], ["f%02d" % i for i in range(1, len(fonts) + 1)])
        self.assertEqual([(f["root"], f["path"]) for f in fonts],
                         sorted((f["root"], f["path"]) for f in fonts))
        self.assertTrue(all("error" not in f for f in job["fonts"]))
        got = {(f["root"], f["path"]): f for f in fonts}
        self.assertIn((0, "Munjo.ttf"), got)
        self.assertEqual(len(got[(0, "Munjo.ttf")]["file_id"]), 3)
        self.assertEqual(self.job(jid)["roots"][0]["name"], "a")

    def test_unreadable_label_names_the_type_only(self):
        d = os.path.join(self.tmp, "tree", "in", "d")
        os.makedirs(d)
        with open(os.path.join(d, "bad.ttf"), "wb") as f:
            f.write(b"\x00\x01\x00\x00" + b"\xff\xfe" * 40)
        junk = os.urandom(64)
        with open(os.path.join(d, "x.bin"), "wb") as f:
            f.write(junk)
        import zipfile
        with zipfile.ZipFile(os.path.join(d, "z.zip"), "w") as z:
            z.writestr("a.txt", "x")
        jid = self.local_job([d])
        job = self.job(jid)
        labels = {f["path"]: f["label"] for f in job["fonts"]}
        self.assertRegex(labels["bad.ttf"], r"^unreadable: [A-Za-z_]+$")
        self.assertEqual(labels["x.bin"], "unknown")
        self.assertEqual(labels["z.zip"], "archive: extract it first, then choose the folder")
        text = json.dumps(self.api("GET", "/api/jobs/%s" % jid)[1], ensure_ascii=False)
        self.assertNotIn(junk[:8].hex(), text)
        stored = self.srv.store.load(jid)
        bad = next(f for f in stored["fonts"] if f["path"] == "bad.ttf")
        self.assertNotIn("error", bad)
        self.assertRegex(bad["error_type"], r"^[A-Za-z_]+$")
        with open(os.path.join(self.srv.store.path(jid), "log.md"), encoding="utf-8") as f:
            self.assertIn("Traceback", f.read())

    def test_local_font_without_a_licence_has_none_and_is_not_selected(self):
        jid = self.local_job()
        job = self.job(jid)
        by = {(f["root"], f["path"]): f for f in job["fonts"]}
        dos = by[(1, "HAN.FNT")]["id"]
        self.assertIsNone(job["settings"]["fonts"][dos]["licence"])
        self.assertFalse(job["settings"]["fonts"][dos]["selected"])
        ttf = by[(0, "Munjo.ttf")]["id"]
        self.assertEqual(job["settings"]["fonts"][ttf]["licence"], {"kind": "upload", "root": 0, "path": "OFL.txt"})
        self.assertEqual(self.api("GET", "/api/caps")[1]["local"], True)

    def test_previews_of_a_local_job_stay_in_files_dir(self):
        jid = self.local_job()
        job = self.job(jid)
        by = {(f["root"], f["path"]): f["id"] for f in job["fonts"]}
        ttf, dos = by[(0, "Munjo.ttf")], by[(1, "HAN.FNT")]
        st = job["settings"]
        st["fonts"][dos]["dos_layout"] = "844"
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        fd = self.files_dir(jid)
        seen = []
        real = preview.run_bounded

        def spy(argv, cwd, timeout, env=None):
            seen.append((cwd, env))
            return real(argv, cwd, timeout, env)
        with mock.patch.object(preview, "run_bounded", spy):
            self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, ttf))[0], 200)
            eff = st["fonts"][ttf]
            size = st["fonts"][ttf].get("sizes") or st["batch"]["sizes"]
            r = self.raw("GET", "/api/jobs/%s/probe/%s/%d/1.json" % (jid, ttf, size[0]))
            self.assertEqual(r[0], 200)
            self.assertEqual(self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, dos))[0], 200)
        self.assertTrue(seen)                                     # the probe and the DOS bake both started tools
        for cwd, env in seen:
            self.assertTrue(cwd.startswith(fd), cwd)
            self.assertIsNotNone(env)
            self.assertEqual(env["TMPDIR"], os.path.join(fd, "work", "tmp"))
            self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
            self.assertEqual(env["HOME"], os.environ.get("HOME", "/"))

    def test_no_upload_copy(self):
        jid = self.local_job()
        job = self.job(jid)
        ttf = next(f["id"] for f in job["fonts"] if f["path"] == "Munjo.ttf")
        self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, ttf))[0], 200)
        self.assertLessEqual(set(os.listdir(self.srv.store.path(jid))), {"job.json", "log.md"})
        digests = set()
        for root in self.roots:
            for rel in walk_rel(root):
                with open(os.path.join(root, rel), "rb") as f:
                    data = f.read()
                digests.add(hashlib.sha256(data).hexdigest())
        for dirpath, _d, names in os.walk(self.data):
            for name in names:
                with open(os.path.join(dirpath, name), "rb") as f:
                    self.assertNotIn(hashlib.sha256(f.read()).hexdigest(), digests, name)
        with open(os.path.join(self.srv.store.path(jid), "job.json"), encoding="utf-8") as f:
            text = f.read()
        for root in self.roots:
            for rel in walk_rel(root):
                with open(os.path.join(root, rel), "rb") as f:
                    head = f.read(16)
                self.assertNotIn(head.hex(), text)

    def test_files_dir_gone_is_404_not_recreated(self):
        jid = self.local_job()
        ttf = next(f["id"] for f in self.job(jid)["fonts"] if f["path"] == "Munjo.ttf")
        moved = self.out + ".moved"
        os.rename(self.out, moved)
        os.mkdir(self.out)
        r = self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, ttf))
        self.assertEqual(r[0], 404)
        self.assertEqual(json.loads(r[2])["error"], "output folder is gone or changed")
        self.assertEqual(os.listdir(self.out), [])


if __name__ == "__main__":
    unittest.main()
