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
import subprocess
import tempfile
import unittest
from unittest import mock

import fixtures
import localfx
import preview
import server
from localfx import LocalBase, LocalRunBase, mode_of, walk_rel
import wincompat


class LocalJobTest(LocalBase):
    def test_create_local_job(self):
        status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out})
        self.assertEqual(status, 200)
        jid = body["id"]
        job = self.srv.store.load(jid)
        self.assertEqual((job["source"], job["output_dir"], job["roots"], job["owned"]), ("local", self.out, [], {}))
        self.assertEqual(sorted(os.listdir(self.srv.store.path(jid))), ["job.json"])
        self.assert_mode(self.files_dir(jid), 0o700)
        self.assert_mode(os.path.join(self.files_dir(jid), "work", "tmp"), 0o700)
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

    @wincompat.posix_only("a FIFO and a symlink as picked paths (the Windows refusals are test_oscompat)")
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
        self.assertEqual(status, 409)
        self.assertTrue(body["error"].startswith("output folder is in use by job %s" % a), body["error"])
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
            self.assertIn("  detect.py:", f.read())          # type and frames (file:line:function)

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


class LocalRunTest(LocalRunBase):
    def test_run_writes_the_tree(self):
        jid, job = self.done_job()
        self.assertNotIn("zip", job["result"])
        files = sorted(job["result"]["files"])
        self.assertEqual(files, sorted(walk_rel(self.out, skip_prefix=".svf-maker-")))
        self.assertEqual(set(self.srv.store.load(jid)["owned"]), set(files))
        kinds = sorted(re.sub(r"[A-Z0-9]{1,8}\.", "X.", f) if f.startswith("svf/") else f for f in files)
        self.assertEqual(kinds, sorted([
            "build-%s/BUILD.md" % jid, "build-%s/FACES.TSV.lines" % jid, "build-%s/FAMILIES.tsv.lines" % jid,
            "build-%s/LICENCES.tsv.lines" % jid, "svf/dos/X.SVF", "svf/dos/X.TXT", "svf/dos/X.TXT",
            "svf/jamo-extra/X.SVF", "svf/jamo-extra/X.TXT"]))
        self.assertEqual(self.raw("GET", "/api/jobs/%s/zip" % jid)[0], 404)
        self.assertEqual(job["result"]["output_dir"], self.out)
        done = [s for s in job["steps"] if s["state"] == "done" and s["kind"] in ("precomposed", "jamo")]
        self.assertEqual(sorted(s["written"] for s in done), sorted(f for f in files if f.endswith(".SVF")))
        # no licence for the DOS font: the note and BUILD.md say so; the TTF's OFL.txt was copied
        dos_note = next(f for f in files if f.startswith("svf/jamo-extra/") and f.endswith(".TXT"))
        self.assertIn("Licence: not checked (user's responsibility)", self.read_out(dos_note).decode("utf-8"))
        ttf_texts = [f for f in files if f.startswith("svf/dos/") and f.endswith(".TXT")]
        notes = [f for f in ttf_texts if b"faces (" in self.read_out(f)]
        self.assertEqual(len(notes), 1)
        self.assertNotIn("not checked", self.read_out(notes[0]).decode("utf-8"))
        build = self.read_out("build-%s/BUILD.md" % jid).decode("utf-8")
        self.assertIn("licence: not checked (user's responsibility)", build)

    def test_detect_keeps_owned(self):
        jid, _job = self.done_job()
        owned = self.srv.store.load(jid)["owned"]
        self.assertTrue(owned)
        self.assertEqual(self.api("POST", "/api/jobs/%s/detect" % jid)[0], 200)
        stored = self.srv.store.load(jid)
        self.assertEqual(stored["owned"], owned)
        self.assertIsNone(stored["result"])

    def test_collisions(self):
        jid, first = self.done_job()
        faces = {f: self.read_out(f) for f in first["result"]["files"] if f.endswith(".SVF")}
        build_a = self.read_out("build-%s/BUILD.md" % jid)
        import datetime
        import zipout
        later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        with mock.patch.object(zipout, "_utc_now", lambda: later):
            again = self.rerun(jid)
        self.assertEqual(again["state"], "done", again.get("error"))
        self.assertNotEqual(self.read_out("build-%s/BUILD.md" % jid), build_a)       # the date moved
        self.assertTrue(any(later.date().isoformat() in self.read_out(f).decode("utf-8")
                            for f in again["result"]["files"] if f.startswith("svf/dos/") and f.endswith(".TXT")))
        for f, data in faces.items():
            self.assertEqual(self.read_out(f), data)                              # identical bytes: kept
        # a second job in the same folder, same face name, other bytes: refused by run_ready, synchronously
        import inputfx
        other = os.path.join(self.tmp, "tree", "in", "a2")
        os.makedirs(other)
        with open(os.path.join(other, "Munjo.ttf"), "wb") as f:
            f.write(inputfx.ttf("Munjo", (300, 0, 700, 400)))
        bid = self.local_job([other])
        job = self.job(bid)
        st = job["settings"]
        fid = job["fonts"][0]["id"]
        st["fonts"][fid].update(selected=True, dest="dos", kinds=["precomposed"], sizes=[16], bpp=[1])
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % bid, st)[0], 200)
        status, body = self.api("POST", "/api/jobs/%s/run" % bid)
        self.assertEqual(status, 400)
        self.assertRegex(body["error"], r"^f01: [A-Z0-9]+\.SVF already exists in svf/dos; choose another name$")
        self.assertEqual(self.job(bid)["state"], "detected")
        for f, data in faces.items():
            self.assertEqual(self.read_out(f), data)

    def test_rerun_after_identical_keeps_ownership(self):
        jid, first = self.done_job()
        owned = dict(self.srv.store.load(jid)["owned"])
        again = self.rerun(jid)
        self.assertEqual(again["state"], "done", again.get("error"))
        step = next(s for s in again["steps"] if s["kind"] == "precomposed")
        self.assertTrue(step["identical_to"].startswith("dos/"))
        self.assertIn("svf/" + step["identical_to"], again["result"]["files"])
        self.assertEqual(set(self.srv.store.load(jid)["owned"]) & set(owned), set(owned))
        changed = self.rerun(jid, lambda st: st["fonts"][self.ttf].update(options={"mkfont": {"ascent": 11}}))
        self.assertEqual(changed["state"], "done", changed.get("error"))
        face = next(f for f in changed["result"]["files"] if f.startswith("svf/dos/") and f.endswith(".SVF"))
        self.assertEqual(self.srv.store.load(jid)["owned"][face], hashlib.sha256(self.read_out(face)).hexdigest())
        self.assertNotEqual(owned[face], self.srv.store.load(jid)["owned"][face])

    def test_own_earlier_replaced_only_when_unchanged(self):
        jid, first = self.done_job()
        face = next(f for f in first["result"]["files"] if f.startswith("svf/dos/") and f.endswith(".SVF"))
        with open(os.path.join(self.out, face), "wb") as f:
            f.write(b"someone else's bytes")
        self.assertEqual(self.api("POST", "/api/jobs/%s/detect" % jid)[0], 200)
        st = self.job(jid)["settings"]
        st["fonts"][self.ttf].update(options={"mkfont": {"ascent": 11}})
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        job = self.run_to_done(jid)                                           # POST run passes: the name is owned
        self.assertEqual(job["state"], "failed")
        self.assertEqual(job["error"], "name clash: " + face)
        self.assertEqual(self.read_out(face), b"someone else's bytes")

    def test_write_tree_without_hard_links(self):
        import errno
        with mock.patch("os.link", side_effect=OSError(errno.EPERM, "no links")):
            jid, job = self.done_job()
        files = job["result"]["files"]
        self.assertEqual(sorted(files), sorted(walk_rel(self.out, skip_prefix=".svf-maker-")))
        owned = self.srv.store.load(jid)["owned"]
        for rel in files:
            self.assertEqual(owned[rel], hashlib.sha256(self.read_out(rel)).hexdigest(), rel)
        self.assertEqual([f for f in walk_rel(self.out) if f.endswith(".tmp")], [])

    def test_write_tree_disk_full(self):
        import errno
        real = os.link
        calls = []

        def link(src, dst, *a, **k):
            calls.append(dst)
            if len(calls) == 2:
                raise OSError(errno.ENOSPC, "No space left on device")
            return real(src, dst, *a, **k)
        with mock.patch("os.link", link):
            jid = self.local_job()
            self.select(jid)
            job = self.run_to_done(jid)
        self.assertEqual(job["state"], "failed")
        self.assertTrue(job["error"].startswith("OSError"), job["error"])
        self.assertEqual(len(job["result"]["files"]), 1)
        self.assertEqual([f for f in walk_rel(self.out) if f.endswith(".tmp")], [])

    def test_notes_and_logs(self):
        import uuid
        import inputfx
        unique = "local-notes-%s" % uuid.uuid4().hex
        deep = os.path.join(self.tmp, "tree", unique)
        for i in range(5):
            deep = os.path.join(deep, "d%d" % i + "x" * 48)
        os.makedirs(deep)
        self.assertGreater(len(deep), 250)
        with open(os.path.join(deep, "Munjo.ttf"), "wb") as f:
            f.write(inputfx.ttf("Munjo", (50, 0, 950, 800)))
        jid = self.local_job([deep])
        job = self.job(jid)
        fid = job["fonts"][0]["id"]
        st = job["settings"]
        st["fonts"][fid].update(selected=True, dest="dos", kinds=["precomposed"], sizes=[16], bpp=[1])
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        note = next(f for f in job["result"]["files"] if f.startswith("svf/dos/") and f.endswith(".TXT"))
        text = self.read_out(note).decode("utf-8")
        for line in text.splitlines():
            self.assertLessEqual(len(line.encode("utf-8")), 512)
            self.assertNotIn(unique, line)
            self.assertNotIn(self.tmp, line)
            self.assertNotIn(os.path.expanduser("~"), line)
            for token in line.split():
                self.assertFalse(token.startswith(os.sep), line)
        commands = [l for l in text.splitlines() if l.startswith("python3")]
        self.assertTrue(commands)
        self.assertTrue(all(re.match(r"python3 -P (tools|maker)/", l) for l in commands), commands)
        with open(os.path.join(self.srv.store.path(jid), "log.md"), encoding="utf-8") as f:
            self.assertIn(deep, f.read())                                          # D4: the log names the full path

    def test_a_repo_licence_is_looked_up_in_the_repository_not_the_output_folder(self):
        jid = self.local_job()
        self.assertFalse(os.path.exists(os.path.join(self.out, "svf")))            # the output folder has no svf/ tree

        def pick(st):
            st["fonts"][self.ttf]["licence"] = {"kind": "repo", "path": "dos/OFLMARU.TXT"}
        self.select(jid, pick)
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))

    def test_sources_put_on_a_done_job_keeps_ownership_and_clears_the_answer(self):
        jid, first = self.done_job()
        owned = self.srv.store.load(jid)["owned"]
        self.assertTrue(owned)
        status, body = self.api("PUT", "/api/jobs/%s/sources" % jid, {"paths": self.roots})
        self.assertEqual(status, 200, body)
        job = self.job(jid)
        self.assertEqual((job["state"], job["result"], job["error"]), ("uploading", None, None))
        self.assertEqual(self.srv.store.load(jid)["owned"], owned)
        self.assertEqual(self.api("POST", "/api/jobs/%s/detect" % jid)[0], 200)
        # the same folder under another spelling: the server answers with the job it already has
        status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out + "/", "reuse": jid})
        self.assertEqual((status, body["id"], body["reused"]), (200, jid, True), body)
        self.assertEqual(len(self.srv.store.list()), 1)

    def test_a_finished_job_cannot_reclaim_a_folder_another_job_holds(self):
        jid, first = self.done_job()
        other = self.new_job(self.out)                                          # a done job does not hold the folder
        status, body = self.api("PUT", "/api/jobs/%s/sources" % jid, {"paths": self.roots})
        self.assertEqual(status, 409, body)
        self.assertIn("output folder is in use by job %s" % other, body["error"])
        self.assertEqual(body["job"], other)
        self.assertEqual(self.job(jid)["state"], "done")                        # untouched
        status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out + "/", "reuse": jid})
        self.assertEqual((status, body.get("job")), (409, other), body)
        self.assertEqual(self.api("DELETE", "/api/jobs/%s" % other)[0], 200)    # the delete affordance frees it
        self.assertEqual(self.api("PUT", "/api/jobs/%s/sources" % jid, {"paths": self.roots})[0], 200)

    def test_input_changed_since_detection(self):
        jid = self.local_job()
        self.select(jid)
        for rel_root, name in ((0, "Munjo.ttf"), (1, "ENG.FNT"), (0, "OFL.txt")):
            path = os.path.join(self.roots[rel_root], name)
            with open(path, "rb") as f:
                original = f.read()
            with open(path, "ab") as f:
                f.write(b"x")
            status, body = self.api("POST", "/api/jobs/%s/run" % jid)
            self.assertEqual((status, body["error"]),
                             (409, "%s: the input changed since detection: detect again" % name), name)
            with open(path, "wb") as f:
                f.write(original)
        os.utime(os.path.join(self.roots[0], "Munjo.ttf"))                        # same size, same inode: fine
        self.assertEqual(self.api("POST", "/api/jobs/%s/run" % jid)[0], 200)
        self.wait_done(jid)

    def test_not_enough_free_space(self):
        jid = self.local_job()
        self.select(jid)
        with mock.patch("shutil.disk_usage", return_value=(0, 0, 1)):
            status, body = self.api("POST", "/api/jobs/%s/run" % jid)
        self.assertEqual((status, body["error"]), (409, "not enough free space in %s" % self.out))

    def test_output_gone_at_run(self):
        jid = self.local_job()
        self.select(jid)
        os.rename(self.out, self.out + ".moved")
        os.mkdir(self.out)
        status, body = self.api("POST", "/api/jobs/%s/run" % jid)
        self.assertEqual((status, body["error"]), (409, "output folder is gone or changed"))
        self.assertEqual(os.listdir(self.out), [])

    def test_run_env_has_tmpdir_and_no_bytecode(self):
        import jobs
        seen = []
        real = jobs.run_command

        def spy(argv, cwd, timeout, cancel, env=None):
            seen.append((argv, env))
            return real(argv, cwd, timeout, cancel, env)
        jid = self.local_job()
        self.select(jid)
        fd = self.files_dir(jid)
        with mock.patch.object(jobs, "run_command", spy), \
                mock.patch.dict(self.srv.worker.caps, {"recog": True, "recog_dir": "/nonexistent-recog",
                                                        "recog_python": None}):
            job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        self.assertTrue(seen)
        for argv, env in seen:
            self.assertIsNotNone(env, argv)
            self.assertEqual(env["TMPDIR"], os.path.join(fd, "work", "tmp"))
            self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
        recog = [env for argv, env in seen if any(str(a).endswith("recog_score.py") for a in argv)]
        self.assertTrue(recog)
        self.assertTrue(all(env["SVF_RECOG_DIR"] == "/nonexistent-recog" for env in recog))

    def test_no_licence_is_allowed_for_a_local_job_only(self):
        jid = self.local_job()
        self.select(jid)
        st = self.job(jid)["settings"]
        self.assertIsNone(st["fonts"][self.dos]["licence"])
        status, body = self.api("POST", "/api/jobs/%s/run" % jid)
        self.assertEqual(status, 200, body)
        self.assertEqual(self.wait_done(jid)["state"], "done")

    def test_output_folder_moved_during_the_run(self):
        import jobs
        jid = self.local_job()
        self.select(jid)
        fd = self.files_dir(jid)
        real = jobs.run_command
        moved = []

        def move_then_run(argv, cwd, timeout, cancel, env=None):
            if not moved:
                moved.append(1)
                os.rename(self.out, self.out + ".moved")
                os.mkdir(self.out)
            return real(argv, cwd, timeout, cancel, env)
        with mock.patch.object(jobs, "run_command", move_then_run):
            status, body = self.api("POST", "/api/jobs/%s/run" % jid)
            job = self.wait_done(jid)
        self.assertEqual(job["state"], "failed")
        self.assertEqual(job["error"], "output folder is gone or changed")
        self.assertEqual(os.listdir(self.out), [])                                 # the new folder is untouched
        self.assertTrue(os.path.isdir(os.path.join(self.out + ".moved", ".svf-maker-" + jid)))
        self.assertIn("intermediate files remain", job.get("notice", ""))           # the user is told
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            entries = json.load(f)
        self.assertEqual([e["path"] for e in entries], [fd])
        self.assertEqual(len(entries[0]["files_id"]), 2)
        with open(os.path.join(self.srv.store.path(jid), "log.md"), encoding="utf-8") as f:
            self.assertIn("intermediate files", f.read())

    def test_unchanged_rerun_keeps_notes_and_licence_owned(self):
        jid, first = self.done_job()
        texts = sorted(f for f in first["result"]["files"] if f.endswith(".TXT"))
        self.assertTrue(texts)
        again = self.rerun(jid)
        self.assertEqual(again["state"], "done", again.get("error"))
        self.assertLessEqual(set(texts), set(again["result"]["files"]))
        self.assertLessEqual(set(texts), set(self.srv.store.load(jid)["owned"]))

    def test_written_is_set_only_for_faces_that_landed(self):
        jid, first = self.done_job()
        face = next(f for f in first["result"]["files"] if f.startswith("svf/dos/") and f.endswith(".SVF"))
        with open(os.path.join(self.out, face), "wb") as f:
            f.write(b"someone else's bytes")
        self.assertEqual(self.api("POST", "/api/jobs/%s/detect" % jid)[0], 200)
        st = self.job(jid)["settings"]
        st["fonts"][self.ttf].update(options={"mkfont": {"ascent": 11}})
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "failed")
        ttf_step = next(s for s in job["steps"] if s["kind"] == "precomposed")
        self.assertNotIn("written", ttf_step)

    def test_build_md_has_no_detect_traceback(self):
        d = os.path.join(self.tmp, "tree", "in", "d")
        os.makedirs(d)
        with open(os.path.join(d, "bad.ttf"), "wb") as f:
            f.write(b"\x00\x01\x00\x00" + b"\xff\xfe" * 40)
        jid = self.local_job(self.roots + [d])
        self.select(jid)
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        with open(os.path.join(self.srv.store.path(jid), "log.md"), encoding="utf-8") as f:
            self.assertIn("  detect.py:", f.read())
        build = self.read_out("build-%s/BUILD.md" % jid).decode("utf-8")
        self.assertNotIn("  detect.py:", build)                                       # frames stay in log.md
        self.assertIn("bad.ttf", build)                                            # the type is named, nothing more

    def test_a_stale_job_does_not_block_the_folder_for_ever(self):
        import time
        server_mod = sys.modules["server"]
        a = self.local_job()
        status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out})
        self.assertEqual(status, 409)
        self.assertIn("output folder is in use by job %s" % a, body["error"])
        self.assertIn("idle", body["error"])
        self.srv.touched[a] = time.monotonic() - server_mod.LOCAL_IDLE_SWEEP_S - 10
        path = os.path.join(self.srv.store.path(a), "job.json")
        with open(path, encoding="utf-8") as f:
            stored = json.load(f)
        stored["updated"] = time.time() - server_mod.LOCAL_IDLE_SWEEP_S - 10          # `update` would stamp it now
        with open(path, "w", encoding="utf-8") as f:
            json.dump(stored, f)
        status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.api("GET", "/api/jobs/%s" % a)[0], 404)              # the stale one was taken over

    def test_an_upload_only_server_starts_no_sweepers_and_writes_no_pending_file(self):
        import threading
        before = {t.name for t in threading.enumerate()}
        data = os.path.join(self.tmp, "data-upload-only")
        srv = server.make_server("127.0.0.1", 0, fixtures.REPO_DIR, data)
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.worker.stop)
        new = {t.name for t in threading.enumerate()} - before
        self.assertFalse([n for n in new if "sweep" in n], new)
        self.assertIsNone(srv.startup_sweep)
        self.assertFalse(os.path.exists(os.path.join(data, "pending-sweeps.json")))


class LocalPrivacyTest(LocalRunBase):
    """No exception message and no tool output line (which may quote the bytes of an input) reaches a persistent
    artifact of a local job: job.json, log.md, BUILD.md, notes, the output tree, the API answers."""

    MARK = "QZMARKERQZ"

    def assert_no_marker(self, *answers):
        for answer in answers:
            self.assertNotIn(self.MARK, json.dumps(answer) if not isinstance(answer, (str, bytes)) else str(answer))
        needle = self.MARK.encode("ascii")
        for dirpath, _d, names in os.walk(self.tmp):
            for name in names:
                path = os.path.join(dirpath, name)
                with open(path, "rb") as f:
                    self.assertNotIn(needle, f.read(), path)

    def test_a_detection_error_keeps_the_type_and_frames_only(self):
        import detect
        real = detect._detect_file

        def boom(abs_path, rel, local=False):
            if rel == "Munjo.ttf":
                raise ValueError("bad table " + self.MARK)
            return real(abs_path, rel, local)
        with mock.patch.object(detect, "_detect_file", boom):
            jid = self.local_job()
        job = self.job(jid)
        entry = next(f for f in job["fonts"] if f["path"] == "Munjo.ttf")
        self.assertEqual(entry["label"], "unreadable: ValueError")
        with open(os.path.join(self.srv.store.path(jid), "log.md"), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("ValueError", log)
        self.assertRegex(log, r"  test_local\.py:\d+:boom")                    # frames as file:line:function
        self.assertNotIn("Traceback", log)
        self.assert_no_marker(job)

    def test_a_charset_registry_never_reaches_a_label(self):
        d = os.path.join(self.tmp, "tree", "in", "reg")
        os.makedirs(d)
        for name, reg in (("a.bdf", self.MARK.lower()), ("b.bdf", "ksc5601-%s" % self.MARK.lower()),
                          ("c.bdf", "iso10646-%s" % self.MARK.lower())):
            with open(os.path.join(d, name), "w", encoding="latin-1") as f:
                f.write("STARTFONT 2.1\nFONT -x-fixed-medium-r-normal--16-160-75-75-c-80-%s-1\nSIZE 16 75 75\n"
                        "FONTBOUNDINGBOX 8 16 0 -2\nCHARSET_REGISTRY \"%s\"\nCHARSET_ENCODING \"1\"\n"
                        "STARTPROPERTIES 0\nENDPROPERTIES\nCHARS 0\nENDFONT\n" % (reg, reg))
        jid = self.local_job(self.roots + [d])
        job = self.job(jid)
        labels = {f["path"].rsplit("/", 1)[-1]: f["label"] for f in job["fonts"]}
        self.assertEqual(labels["a.bdf"], "BDF (unrecognized charset): not convertible")
        self.assertTrue(labels["b.bdf"].startswith("BDF (ksc5601)"), labels)
        self.assertTrue(labels["c.bdf"].startswith("BDF (iso10646)"), labels)
        self.assertNotIn(self.MARK.lower(), json.dumps(job).lower())
        for dirpath, _d, names in os.walk(self.srv.store.root if hasattr(self.srv.store, "root") else self.tmp):
            for n in names:
                if n.endswith(".bdf"):
                    continue
                with open(os.path.join(dirpath, n), "rb") as f:
                    self.assertNotIn(self.MARK.lower().encode(), f.read().lower(), n)

    def test_tool_output_and_step_errors_are_not_kept(self):
        import jobs
        real = jobs.run_command

        def noisy(argv, cwd, timeout, cancel, env=None):
            if any("HAN.FNT" in str(a) for a in argv):
                return {"exit": 1, "seconds": 0.0, "error": None, "stdout": "check: composed 11172 syllables from 5 glyphs, JSET 501 bytes\nfont " + self.MARK + "\n",
                        "stderr": "error: " + self.MARK + "\n"}
            return real(argv, cwd, timeout, cancel, env)
        jid = self.local_job()
        self.select(jid)
        with mock.patch.object(jobs, "run_command", noisy):
            job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        bad = next(s for s in job["steps"] if s["font"] == self.dos)
        self.assertEqual(bad["state"], "failed")
        self.assertNotIn(self.MARK, bad["stderr_tail"])
        self.assertIn("not kept", bad["stderr_tail"])
        with open(os.path.join(self.srv.store.path(jid), "log.md"), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("check: composed 11172 syllables from 5 glyphs, JSET 501 bytes", log)   # the tools' own verdict line stays
        self.assert_no_marker(job, self.job(jid))

    def test_a_check_line_with_input_text_is_not_kept(self):
        import jobs
        real = jobs.run_command

        def noisy(argv, cwd, timeout, cancel, env=None):
            if any("HAN.FNT" in str(a) for a in argv):
                return {"exit": 1, "seconds": 0.0, "error": None,
                        "stdout": "check: " + self.MARK + "\nverify " + self.MARK + "\n",
                        "stderr": "check: composed 11172 syllables from 5 glyphs, JSET 501 bytes " + self.MARK + "\n"}
            return real(argv, cwd, timeout, cancel, env)
        jid = self.local_job()
        self.select(jid)
        with mock.patch.object(jobs, "run_command", noisy):
            job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        self.assert_no_marker(job, self.job(jid))

    def test_write_tree_errors_are_sanitized_in_the_job_error(self):
        import zipout
        cases = [(ValueError("bad \x07 " + self.MARK), "ValueError"),
                 (OSError(5, "Input/output error", "/secret/" + self.MARK), "OSError: Input/output error"),
                 (RuntimeError(self.MARK), "RuntimeError")]
        for exc, want in cases:
            with self.subTest(exc=type(exc).__name__):
                out = os.path.join(self.tmp, "o%s" % type(exc).__name__)
                os.makedirs(out)
                jid = self.local_job(out=out)
                self.select(jid)
                with mock.patch.object(zipout, "write_tree", side_effect=exc):
                    job = self.run_to_done(jid)
                self.assertEqual((job["state"], job["error"]), ("failed", want))
                self.assert_no_marker(job)

    def test_a_refused_note_names_no_character(self):
        """POST run checks the notes (run_ready and the note check of the planned steps): neither answer quotes the
        control character or the input's text that made naming.note_text refuse."""
        import naming
        jid = self.new_detected()
        message = "note_text: family carries the control character '\\x07' " + self.MARK
        real = naming.note_text

        def refuse_commands(*args, **kwargs):
            if args[6]:                                                 # the note check of the planned steps
                raise ValueError(message)
            return real(*args, **kwargs)
        for patch in (mock.patch.object(naming, "note_text", refuse_commands),
                      mock.patch.object(naming, "note_text", side_effect=ValueError(message))):   # run_ready's own check
            with patch:
                status, body = self.api("POST", "/api/jobs/%s/run" % jid)
            self.assertEqual(status, 400, body)
            self.assertNotIn("x07", json.dumps(body))
            self.assertNotIn(self.MARK, json.dumps(body))

    def new_detected(self):
        out = os.path.join(self.tmp, "o-refused")
        os.makedirs(out, exist_ok=True)
        jid = self.local_job(out=out)
        self.select(jid)
        return jid

    def test_stderr_gets_type_and_frames_only_with_the_token(self):
        import contextlib
        import detect
        import io
        jid = self.new_job()
        self.assertEqual(self.api("PUT", "/api/jobs/%s/sources" % jid, {"paths": self.roots})[0], 200)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), mock.patch.object(detect, "scan", side_effect=RuntimeError("boom " + self.MARK)):
            status, body = self.api("POST", "/api/jobs/%s/detect" % jid)
        self.assertEqual(status, 500)
        self.assertIn("RuntimeError", err.getvalue())
        self.assertNotIn(self.MARK, err.getvalue())

    def test_source_and_readback_errors_are_the_type_only(self):
        import jobs
        import quality
        import preview
        jid = self.local_job()
        gz = next(f["id"] for f in self.job(jid)["fonts"] if f["path"] == "hanterm.bdf.gz")
        self.select(jid, lambda st: st["fonts"][gz].update(selected=True, dest="jamo-extra", kinds=["jamo"]))
        with mock.patch.object(preview, "materialize", side_effect=ValueError("bad gzip " + self.MARK)), \
                mock.patch.object(quality, "face_facts", side_effect=ValueError("bad face " + self.MARK)):
            job = self.run_to_done(jid)
        errors = {s["error"] for s in job["steps"] if s["state"] == "failed"}
        self.assertTrue(errors <= {"ValueError"}, errors)
        self.assertTrue(errors)
        self.assert_no_marker(job)

    def test_a_job_level_exception_is_the_type_only(self):
        import zipout
        jid = self.local_job()
        self.select(jid)
        with mock.patch.object(zipout, "collect", side_effect=RuntimeError("boom " + self.MARK)):
            job = self.run_to_done(jid)
        self.assertEqual((job["state"], job["error"]), ("failed", "RuntimeError"))
        self.assert_no_marker(job)

    def test_a_500_answer_names_the_type_only_with_the_token(self):
        import detect
        jid = self.new_job()
        self.assertEqual(self.api("PUT", "/api/jobs/%s/sources" % jid, {"paths": self.roots})[0], 200)
        with mock.patch.object(detect, "scan", side_effect=RuntimeError("boom " + self.MARK)):
            status, body = self.api("POST", "/api/jobs/%s/detect" % jid)
        self.assertEqual((status, body["error"]), (500, "RuntimeError"))
        self.assert_no_marker(body)


class LocalSweepTest(LocalRunBase):
    def probe(self, jid, fid):
        eff_sizes = self.job(jid)["settings"]["fonts"][fid].get("sizes") or self.job(jid)["settings"]["batch"]["sizes"]
        return self.raw("GET", "/api/jobs/%s/probe/%s/%d/1.json" % (jid, fid, eff_sizes[0]))

    def test_sweep_points(self):
        jid = self.local_job()
        self.select(jid)
        fd = self.files_dir(jid)
        self.assertTrue(os.path.isdir(fd))                                      # made at create
        self.assertEqual(self.probe(jid, self.ttf)[0], 200)
        self.assertTrue(os.path.isdir(os.path.join(fd, "work", "preview", self.ttf, "probe")))
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        self.assertFalse(os.path.exists(fd))                                    # gone after the run ends
        self.assertEqual(self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, self.dos))[0], 200)
        self.assertTrue(os.path.isdir(fd))                                      # re-made by a GET on the done job
        r = self.api("DELETE", "/api/jobs/%s" % jid)
        self.assertEqual(r[0], 200)
        self.assertFalse(os.path.exists(fd))                                    # gone after DELETE
        # a second server over the same data root sweeps what a crashed one left (start-up thread)
        out2 = os.path.join(self.tmp, "out2")
        os.makedirs(out2)
        jid2 = self.local_job(out=out2)
        self.select(jid2)
        self.assertEqual(self.run_to_done(jid2)["state"], "done")
        planted = os.path.join(out2, ".svf-maker-" + jid2)
        os.makedirs(os.path.join(planted, "work", "preview"))
        server2 = None
        try:
            import server as servermod
            self.release_lock()
            server2 = servermod.make_server("127.0.0.1", 0, fixtures.REPO_DIR, self.data, token=localfx.TOKEN)
            self.assertIsNone(server2.startup_sweep)                         # the cleanup is synchronous: done by now
            self.assertFalse(os.path.exists(planted))
        finally:
            if server2 is not None:
                server2.worker.stop()
                server2.server_close()
        # Worker.stop() removes one a GET re-made
        self.assertEqual(self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid2, self.dos))[0], 200)
        self.assertTrue(os.path.isdir(planted))
        self.srv.worker.stop()
        self.assertFalse(os.path.exists(planted))

    def test_pending_sweeps_retried(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        real = shutil.rmtree
        calls = []

        def once(path, *a, **k):
            if str(path).startswith(fd):
                calls.append(path)
                raise OSError("busy")
            return real(path, *a, **k)
        with mock.patch.object(shutil, "rmtree", once):
            self.assertEqual(self.api("DELETE", "/api/jobs/%s" % jid)[0], 200)
        pending = os.path.join(self.data, "pending-sweeps.json")
        with open(pending, encoding="utf-8") as f:
            entries = json.load(f)
        trash = entries[0]["path"]
        self.assertTrue(trash.startswith(fd + ".trash-"), trash)                 # the directory was renamed, then failed
        self.assertTrue(os.path.isdir(trash) and not os.path.exists(fd))
        entries.append({"path": "/tmp/x", "output_dir": "/tmp", "output_id": [1, 2], "job": "0123456789ab"})
        with open(pending, "w", encoding="utf-8") as f:
            json.dump(entries, f)
        self.srv.store.retry_pending_sweeps()
        self.assertFalse(os.path.exists(trash))
        with open(pending, encoding="utf-8") as f:
            left = json.load(f)
        self.assertEqual([e["path"] for e in left], ["/tmp/x"])                  # another folder at /tmp: kept, not dropped

    def test_pending_sweep_of_a_replaced_output_folder(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        real = shutil.rmtree

        def fail(path, *a, **k):
            if str(path).startswith(fd):
                raise OSError("busy")
            return real(path, *a, **k)
        with mock.patch.object(shutil, "rmtree", fail):
            self.api("DELETE", "/api/jobs/%s" % jid)
        os.rename(self.out, self.out + ".old")
        os.makedirs(os.path.join(self.out, ".svf-maker-" + jid))
        keep = os.path.join(self.out, ".svf-maker-" + jid, "keep.txt")
        with open(keep, "w") as f:
            f.write("mine")
        self.srv.store.retry_pending_sweeps()
        self.assertTrue(os.path.exists(keep))                                    # a replaced folder is never touched
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)), 1)                               # kept until the original returns
        shutil.rmtree(self.out)
        os.rename(self.out + ".old", self.out)                                   # the original is back
        self.srv.store.retry_pending_sweeps()
        self.assertFalse(os.path.exists(fd))
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])
        os.rename(self.out, self.out + ".old")
        os.makedirs(self.out)
        # the same with the output folder replaced by a symlink to a folder that holds that name
        with mock.patch.object(shutil, "rmtree", fail):
            jid2 = self.new_job(self.out + ".old")
            fd2 = self.files_dir_in(self.out + ".old", jid2)
            self.api("DELETE", "/api/jobs/%s" % jid2)
        other = os.path.join(self.tmp, "other")
        os.makedirs(os.path.join(other, ".svf-maker-" + jid2))
        os.rename(self.out + ".old", self.out + ".older")
        os.symlink(other, self.out + ".old")
        self.srv.store.retry_pending_sweeps()
        self.assertTrue(os.path.isdir(os.path.join(other, ".svf-maker-" + jid2)))

    def test_a_pending_sweep_is_retried_only_by_the_idle_sweeper_and_start_up(self):
        a = self.local_job()
        fa = self.files_dir(a)
        os.rename(self.out, self.out + ".away")                                    # unmounted
        self.assertEqual(self.api("DELETE", "/api/jobs/%s" % a)[0], 200)
        self.assertTrue(os.path.isdir(os.path.join(self.out + ".away", ".svf-maker-" + a)))
        os.rename(self.out + ".away", self.out)                                    # the folder is back
        b = self.local_job()
        self.assertEqual(self.api("DELETE", "/api/jobs/%s" % b)[0], 200)           # a delete does not retry
        self.assertTrue(os.path.isdir(fa))
        self.srv.sweep_idle()                                                      # the idle sweep point, no restart
        self.assertFalse(os.path.exists(fa))
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])

    def test_a_retry_leaves_the_directory_of_a_job_that_is_running_again(self):
        import threading
        jobs_mod = sys.modules["jobs"]
        jid = self.local_job()
        self.select(jid)
        fd = self.files_dir(jid)
        job = self.srv.store.load(jid)
        entry = {"path": fd, "output_dir": job["output_dir"], "output_id": job["output_id"], "job": jid,
                 "files_id": job.get("files_id")}                                # an earlier failed cleanup of this directory
        with open(os.path.join(self.data, "pending-sweeps.json"), "w", encoding="utf-8") as f:
            json.dump([entry], f)
        real = jobs_mod.run_command
        inside, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def paused(argv, cwd, timeout, cancel, env=None):
            inside.set()
            release.wait(30)
            return real(argv, cwd, timeout, cancel, env)
        with mock.patch.object(jobs_mod, "run_command", paused):
            self.assertEqual(self.api("POST", "/api/jobs/%s/run" % jid)[0], 200)
            self.assertTrue(inside.wait(20))                                     # the rerun is inside a tool call
            self.srv.store.retry_pending_sweeps()
            self.srv.sweep_idle()
            self.assertTrue(os.path.isdir(fd))                                   # not removed under it
            with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
                self.assertEqual(len(json.load(f)), 1)                           # and the entry is kept
            release.set()
            self.assertEqual(self.wait_done(jid)["state"], "done")
        entry["files_id"] = [1, 2]                                               # another generation of the directory
        os.makedirs(fd, exist_ok=True)
        with open(os.path.join(self.data, "pending-sweeps.json"), "w", encoding="utf-8") as f:
            json.dump([entry], f)
        self.srv.store.update(jid, lambda j: j.update(state="failed"))
        self.srv.store.retry_pending_sweeps()
        self.assertTrue(os.path.isdir(fd))                                       # an obsolete entry never deletes it
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])                                   # and is dropped

    def _pending_job(self):
        """A local job whose delete failed once: its files directory is recorded as pending."""
        jid = self.local_job()
        fd = self.files_dir(jid)
        real = shutil.rmtree

        def fail(path, *a, **k):
            if str(path).startswith(fd):
                raise OSError("busy")
            return real(path, *a, **k)
        with mock.patch.object(shutil, "rmtree", fail):
            self.srv.store.sweep_files(self.srv.store.load(jid))
        return jid, fd

    def test_a_failing_sweep_and_a_concurrent_retry_do_not_deadlock(self):
        import threading
        import time
        jid, fd = self._pending_job()
        job = self.srv.store.load(jid)
        real = shutil.rmtree

        def slow_fail(path, *a, **k):
            if str(path).startswith(fd):
                time.sleep(0.4)
                raise OSError("busy")
            return real(path, *a, **k)
        done = []
        with mock.patch.object(shutil, "rmtree", slow_fail):
            a = threading.Thread(target=lambda: done.append(self.srv.store.sweep_files(job)), daemon=True)
            b = threading.Thread(target=lambda: (time.sleep(0.1), self.srv.store.retry_pending_sweeps()), daemon=True)
            a.start()
            b.start()
            a.join(10)
            b.join(10)
            self.assertFalse(a.is_alive() or b.is_alive(), "sweep and retry deadlocked")
        self.assertEqual(done, [True])                                         # the directory was already renamed away
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            entries = json.load(f)
        self.assertEqual(len(entries), 1)                                       # still pending, once (the tombstone)
        self.assertTrue(entries[0]["path"].startswith(fd + ".trash-"))
        self.srv.store.retry_pending_sweeps()                                   # and a later retry clears it
        self.assertFalse(os.path.exists(entries[0]["path"]))

    def test_stop_returns_although_a_removal_hangs_and_a_preview_lock_is_held(self):
        import threading
        import time
        server_mod = sys.modules["server"]
        a = self.local_job()
        fa = self.files_dir(a)
        font_id = self.srv.store.load(a)["fonts"][0]["id"]
        release = threading.Event()
        self.addCleanup(release.set)
        real = shutil.rmtree

        def hang(path, *args, **kw):
            if str(path).startswith(fa):
                release.wait(20)                                                # a child on a dead mount
            return real(path, *args, **kw)
        lock = server_mod._preview_lock(a, font_id)
        lock.acquire()                                                          # another sweep holds the preview lock
        self.addCleanup(lambda: lock.locked() and lock.release())
        with mock.patch.object(shutil, "rmtree", hang), mock.patch.object(sys.modules["jobs"], "STOP_SWEEP_TOTAL_S", 1.5):
            started = time.monotonic()
            self.srv.worker.sweep_local_files()
            took = time.monotonic() - started
            self.assertLess(took, 4, took)                                      # one deadline for all the waits
            lock.release()
            started = time.monotonic()
            self.srv.worker.sweep_local_files()                                 # now the removal itself hangs
            self.assertLess(time.monotonic() - started, 4)
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            paths = [e["path"] for e in json.load(f)]
        self.assertTrue([p for p in paths if p.startswith(fa + ".trash-")], paths)   # the tombstone is left for the next start
        release.set()

    def test_stop_makes_no_pending_retry(self):
        jobs_mod = sys.modules["jobs"]
        jid, fd = self._pending_job()
        self.srv.store.delete(jid)
        with mock.patch.object(jobs_mod.Store, "retry_pending_sweeps", side_effect=AssertionError("retry at stop")):
            self.srv.worker.stop()

    def test_a_hung_stat_costs_one_thread_per_path_however_often_it_is_asked(self):
        import threading
        import time
        jobs_mod = sys.modules["jobs"]
        gate = threading.Event()
        real = jobs_mod.stat_id
        self.addCleanup(gate.set)

        def hung(path):
            gate.wait(20)
            return real(path)
        before = threading.active_count()
        with mock.patch.object(jobs_mod, "stat_id", hung):
            for _ in range(25):
                with self.assertRaises(OSError):
                    jobs_mod.stat_id_bounded(self.out, 0.05)
            self.assertLessEqual(threading.active_count() - before, 1)
            gate.set()
            time.sleep(0.3)
            self.assertEqual(jobs_mod.stat_id_bounded(self.out, 2), real(self.out))     # and it is usable again
        self.assertLessEqual(threading.active_count() - before, 0)

    def test_a_create_does_not_wait_for_a_slow_pending_stat(self):
        import threading
        import time
        jobs_mod = sys.modules["jobs"]
        away = os.path.join(self.tmp, "away")
        os.makedirs(away)
        jid, fd = self._pending_job()                                          # pending entry for self.out
        self.srv.touched[jid] = time.monotonic() - sys.modules["server"].LOCAL_IDLE_SWEEP_S - 10
        path = os.path.join(self.srv.store.path(jid), "job.json")
        with open(path, encoding="utf-8") as f:
            stored = json.load(f)
        stored["updated"] = time.time() - sys.modules["server"].LOCAL_IDLE_SWEEP_S - 10
        with open(path, "w", encoding="utf-8") as f:
            json.dump(stored, f)
        real = jobs_mod.stat_id
        gate = threading.Event()
        self.addCleanup(gate.set)

        def slow_for_other(p):
            if p == "/nonexistent-mount":
                gate.wait(6)
            return real(p)
        pend = os.path.join(self.data, "pending-sweeps.json")
        with open(pend, encoding="utf-8") as f:
            data = json.load(f)
        data.append({"path": "/nonexistent/.svf-maker-0123456789ab", "output_dir": "/nonexistent-mount", "output_id": [1, 2],
                     "job": "0123456789ab"})
        with open(pend, "w", encoding="utf-8") as f:
            json.dump(data, f)
        with mock.patch.object(jobs_mod, "stat_id", slow_for_other):
            started = time.monotonic()
            status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out})
            took = time.monotonic() - started
        self.assertEqual(status, 200, body)                                    # the idle job was taken over
        self.assertLess(took, 3, took)

    def test_detect_on_a_finished_job_is_refused_while_another_job_holds_the_folder(self):
        jid, first = self.done_job()
        other = self.new_job(self.out)
        status, body = self.api("POST", "/api/jobs/%s/detect" % jid)
        self.assertEqual(status, 409, body)
        self.assertEqual(body.get("job"), other)
        self.assertEqual(self.job(jid)["state"], "done")                       # untouched
        self.assertEqual(self.api("DELETE", "/api/jobs/%s" % other)[0], 200)
        self.assertEqual(self.api("POST", "/api/jobs/%s/detect" % jid)[0], 200)

    def test_concurrent_activation_of_a_finished_job_and_a_create_has_one_winner(self):
        import threading
        jid, first = self.done_job()
        results = {}
        gate = threading.Barrier(2, timeout=20)

        def detect():
            gate.wait()
            results["detect"] = self.api("POST", "/api/jobs/%s/detect" % jid)[0]

        def create():
            gate.wait()
            results["create"] = self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out})[0]
        threads = [threading.Thread(target=detect), threading.Thread(target=create)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        self.assertEqual(sorted(results.values()), [200, 409], results)
        active = [i for i in self.srv.store.list() if i["state"] in ("uploading", "detected")]
        self.assertEqual(len(active), 1, active)

    def test_a_renamed_output_folder_is_a_new_job(self):
        jid, first = self.done_job()
        owned = self.srv.store.load(jid)["owned"]
        renamed = self.out + "-renamed"
        os.rename(self.out, renamed)                                            # same device and inode, other path
        status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": renamed, "reuse": jid})
        self.assertEqual(status, 200, body)
        self.assertNotEqual(body["id"], jid)                                    # not reused
        self.assertNotIn("reused", body)
        self.assertEqual(self.srv.store.load(body["id"])["owned"], {})          # the moved faces are not carried over
        self.assertEqual(self.srv.store.load(jid)["output_dir"], self.out)
        self.assertEqual(self.srv.store.load(jid)["owned"], owned)
        # while another job holds the renamed folder the 409 says what a move means
        status, body = self.api("POST", "/api/jobs", {"source": "local", "output_dir": renamed, "reuse": jid})
        self.assertEqual(status, 409)
        self.assertIn("renamed or moved folder is a new job", body["error"])

    def test_an_abandoned_removal_cannot_delete_a_later_generation(self):
        import threading
        import time
        jobs_mod = sys.modules["jobs"]
        jid = self.local_job()
        fd = self.files_dir(jid)
        job = self.srv.store.load(jid)
        release, started = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        real = shutil.rmtree

        def hang(path, *a, **k):
            if str(path).startswith(fd + ".trash-"):
                started.set()
                release.wait(20)                                                # the dead mount
            return real(path, *a, **k)
        with mock.patch.object(shutil, "rmtree", hang):
            self.assertFalse(self.srv.store.sweep_files(job, None, 0.3))        # deadline missed, locks released
            self.assertTrue(started.wait(5))
            self.assertFalse(os.path.exists(fd))
            self.srv.store.ensure_files_dir(self.srv.store.load(jid))           # a rerun makes the next generation
            live = os.path.join(fd, "work", "LIVE.SVF")
            os.makedirs(os.path.dirname(live), exist_ok=True)
            with open(live, "wb") as f:
                f.write(b"live")
            release.set()                                                       # the abandoned removal now finishes
            time.sleep(1)
        self.assertTrue(os.path.isfile(live))                                   # it only ever touched the tombstone
        left = [n for n in os.listdir(self.out) if ".trash-" in n]
        self.assertEqual(left, [])

    def test_a_blocked_removal_does_not_stop_the_idle_sweeper_or_the_previews(self):
        import threading
        import time
        server_mod = sys.modules["server"]
        jobs_mod = sys.modules["jobs"]
        jid = self.local_job()
        font_id = self.srv.store.load(jid)["fonts"][0]["id"]
        self.srv.touched[jid] = time.monotonic() - server_mod.LOCAL_IDLE_SWEEP_S - 10
        release = threading.Event()
        self.addCleanup(release.set)
        real = shutil.rmtree

        def hang(path, *a, **k):
            if ".trash-" in str(path):
                release.wait(20)
            return real(path, *a, **k)
        with mock.patch.object(shutil, "rmtree", hang), mock.patch.object(jobs_mod, "REMOVE_BOUND_S", 0.5):
            t = threading.Thread(target=self.srv.sweep_idle, daemon=True)
            started = time.monotonic()
            t.start()
            time.sleep(0.2)                                                     # inside the blocked removal
            lock = server_mod._preview_lock(jid, font_id)
            self.assertTrue(lock.acquire(timeout=1))                            # the job's preview locks are free
            lock.release()
            t.join(10)
            self.assertFalse(t.is_alive())                                      # the sweeper thread went on
            self.assertLess(time.monotonic() - started, 8)
        release.set()

    def test_a_corrupt_pending_file_is_kept_aside_and_writes_are_synced(self):
        pend = os.path.join(self.data, "pending-sweeps.json")
        jid, fd = self._pending_job()
        with open(pend, encoding="utf-8") as f:
            good = f.read()
        with open(pend, "w", encoding="utf-8") as f:
            f.write(good[:len(good) // 2])                                      # truncated
        self.assertEqual(self.srv.store._read_pending(), [])
        aside = [n for n in os.listdir(self.data) if n.startswith("pending-sweeps.json.bad-")]
        self.assertEqual(len(aside), 1)
        with open(os.path.join(self.data, aside[0]), encoding="utf-8") as f:
            self.assertEqual(f.read(), good[:len(good) // 2])                   # nothing lost: a person can read it
        self.assertFalse(os.path.exists(pend))                                  # and it is not overwritten blindly
        synced = []
        real = os.fsync
        with mock.patch("os.fsync", lambda fd_: (synced.append(fd_), real(fd_))[1]):
            self.srv.store._write_pending([{"path": "x"}])
        # the file and its directory (Windows cannot open a directory to sync it: the file only)
        self.assertGreaterEqual(len(synced), 1 if wincompat.WIN else 2)

    def test_a_retry_paused_after_its_state_check_cannot_be_overtaken_by_a_reactivation(self):
        import threading
        jid, first = self.done_job()
        store = self.srv.store
        store.ensure_files_dir(store.load(jid))                                 # a preview made the directory again
        fd = self.files_dir(jid)
        job = store.load(jid)
        entry = {"path": fd, "output_dir": job["output_dir"], "output_id": job["output_id"], "job": jid,
                 "files_id": job["files_id"]}
        with open(os.path.join(self.data, "pending-sweeps.json"), "w", encoding="utf-8") as f:
            json.dump([entry], f)
        inside, go = threading.Event(), threading.Event()
        self.addCleanup(go.set)
        real = store.on_sweep

        def paused(j, timeout=None):
            inside.set()                                                        # the state check is behind us
            self.assertTrue(go.wait(20))
            return real(j, timeout)
        store.on_sweep = paused
        self.addCleanup(setattr, store, "on_sweep", real)
        retry = threading.Thread(target=store.retry_pending_sweeps, daemon=True)
        retry.start()
        self.assertTrue(inside.wait(20))
        answers = []
        put = threading.Thread(target=lambda: answers.append(
            self.api("PUT", "/api/jobs/%s/sources" % jid, {"paths": self.roots})[0]), daemon=True)
        put.start()
        put.join(0.5)
        self.assertTrue(put.is_alive())                                         # it waits for the lifecycle lock
        self.assertEqual(self.job(jid)["state"], "done")                        # and has changed nothing
        go.set()
        retry.join(20)
        put.join(20)
        self.assertEqual(answers, [200])                                        # it went ahead after the rename
        self.assertFalse(os.path.exists(fd))                                    # the old generation is gone
        self.assertEqual(self.api("POST", "/api/jobs/%s/detect" % jid)[0], 200)
        self.assertTrue(os.path.isdir(fd))                                      # the active job has a fresh directory
        self.assertEqual([n for n in os.listdir(self.out) if ".trash-" in n], [])

    def test_startup_cleanup_finishes_before_the_server_exists_and_unfinished_jobs_stay_inactive(self):
        import threading
        server_mod = sys.modules["server"]
        jobs_mod = sys.modules["jobs"]
        jid, first = self.done_job()
        job = self.srv.store.load(jid)
        with open(os.path.join(self.data, "pending-sweeps.json"), "w", encoding="utf-8") as f:
            json.dump([{"path": os.path.join(self.out, ".svf-maker-0123456789ab"), "output_dir": self.out,
                        "output_id": job["output_id"], "job": "0123456789ab", "files_id": None}], f)
        inside, go = threading.Event(), threading.Event()
        self.addCleanup(go.set)
        real = jobs_mod.Store.retry_pending_sweeps

        def paused(store, *a, **k):
            inside.set()
            go.wait(20)
            return real(store, *a, **k)
        made = []
        self.release_lock()
        with mock.patch.object(jobs_mod.Store, "retry_pending_sweeps", paused):
            t = threading.Thread(target=lambda: made.append(
                server_mod.make_server("127.0.0.1", 0, fixtures.REPO_DIR, self.data, token=localfx.TOKEN)), daemon=True)
            t.start()
            self.assertTrue(inside.wait(20))                                    # paused on the pending entry
            t.join(0.5)
            self.assertTrue(t.is_alive() and not made)                          # no server object, so no request served
            go.set()
            t.join(30)
        self.assertEqual(len(made), 1)
        made[0].worker.stop()
        made[0].server_close()
        # a job whose cleanup did not finish is inactive: 409 on every way back in
        self.srv.cleanup_pending.add(jid)
        for method, path, body in (("PUT", "/api/jobs/%s/sources" % jid, {"paths": self.roots}),
                                   ("POST", "/api/jobs/%s/detect" % jid, None),
                                   ("POST", "/api/jobs/%s/run" % jid, None),
                                   ("POST", "/api/jobs", {"source": "local", "output_dir": self.out, "reuse": jid})):
            status, answer = self.api(method, path, body)
            self.assertEqual(status, 409, (path, answer))
            self.assertIn("cleanup pending", answer["error"])
        self.assertEqual(self.job(jid)["state"], "done")
        self.srv.cleanup_pending.discard(jid)
        self.assertEqual(self.api("PUT", "/api/jobs/%s/sources" % jid, {"paths": self.roots})[0], 200)

    def test_a_put_that_saw_detected_cannot_activate_a_job_that_finished_meanwhile(self):
        import threading
        server_mod = sys.modules["server"]
        jid = self.local_job()
        self.select(jid)
        inside, go = threading.Event(), threading.Event()
        self.addCleanup(go.set)
        real = server_mod.Handler._json_body

        def paused(handler):
            if handler.command == "PUT" and handler.path.endswith("/sources"):
                inside.set()                                                    # the snapshot said `detected`
                go.wait(20)
            return real(handler)
        answers = []
        with mock.patch.object(server_mod.Handler, "_json_body", paused):
            put = threading.Thread(target=lambda: answers.append(
                self.api("PUT", "/api/jobs/%s/sources" % jid, {"paths": self.roots})), daemon=True)
            put.start()
            self.assertTrue(inside.wait(20))
            self.assertEqual(self.run_to_done(jid)["state"], "done")           # it finishes meanwhile ...
            other = self.new_job(self.out)                                      # ... and another job claims the folder
            go.set()
            put.join(30)
        self.assertEqual(answers[0][0], 409, answers)                           # no activation without a claim
        self.assertEqual(answers[0][1].get("job"), other)
        self.assertEqual(self.job(jid)["state"], "done")

    def test_completion_preview_failed_delete_then_retry_keeps_tracking(self):
        jobs_mod = sys.modules["jobs"]
        jid, first = self.done_job()
        fd = self.files_dir(jid)
        ttf = next(f["id"] for f in self.job(jid)["fonts"] if f["path"] == "Munjo.ttf")
        self.assertFalse(os.path.exists(fd))                                    # swept at the end of the run
        self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, ttf))[0], 200)   # a new generation
        self.assertTrue(os.path.isdir(fd))
        self.assertEqual(self.srv.store.load(jid)["files_id"], [os.stat(fd).st_dev, os.stat(fd).st_ino])   # saved at creation
        real = shutil.rmtree

        def fail(path, *a, **k):
            if str(path).startswith(fd):
                raise OSError("busy")
            return real(path, *a, **k)
        with mock.patch.object(shutil, "rmtree", fail):
            self.assertEqual(self.api("DELETE", "/api/jobs/%s" % jid)[0], 200)
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            entries = json.load(f)
        self.assertEqual(len(entries), 1, entries)                              # tracked although the metadata is gone
        self.assertTrue(entries[0]["path"].startswith(fd + ".trash-"))
        self.srv.store.retry_pending_sweeps()
        self.assertEqual([n for n in os.listdir(self.out) if n.startswith(".svf-maker-")], [])
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])

    def test_stop_with_several_jobs_and_delayed_locks_returns_within_the_single_deadline(self):
        import time
        server_mod = sys.modules["server"]
        jobs_mod = sys.modules["jobs"]
        held = []
        for n in range(3):
            out = os.path.join(self.tmp, "out%d" % n)
            os.makedirs(out)
            jid = self.local_job(out=out)
            for font in self.srv.store.load(jid)["fonts"][:2]:
                lock = server_mod._preview_lock(jid, font["id"])
                lock.acquire()
                held.append(lock)
                self.addCleanup(lambda lk=lock: lk.locked() and lk.release())
        with mock.patch.object(jobs_mod, "STOP_SWEEP_TOTAL_S", 1.0):
            started = time.monotonic()
            self.srv.worker.sweep_local_files()
            took = time.monotonic() - started
        self.assertLess(took, 1.6, took)           # one allowance for all waits; the old per-lock waits took 2 s per job

    def _probe_vs_delete(self, pause_before):
        """A probe request and a DELETE of its job, interleaved at a point the lock order allows: the probe held back
        BEFORE it takes any lock (the job is deleted, then the probe runs), or inside its bake, where it holds the
        font's preview lock (the DELETE's try-lock of it cannot succeed). Nothing here depends on load: the DELETE's
        preview try-lock is bounded (`PREVIEW_TRY_S`), so a bake that outlasts it is a recorded pending sweep, and a
        bake held by the test always does. What must hold either way: no directory of the deleted job stays that
        `pending-sweeps.json` does not name, and `retry_pending_sweeps` then removes it."""
        import threading
        server_mod = sys.modules["server"]
        jid = self.local_job()
        self.select(jid)
        fid = self.ttf
        paused, go = threading.Event(), threading.Event()
        self.addCleanup(go.set)
        name = "_exists" if pause_before else "_prepared_source"
        real = getattr(server_mod.Handler, name)

        def hold(handler, *a, **k):
            if threading.current_thread() is not threading.main_thread() and not paused.is_set() \
                    and (not pause_before or a[:1] == (jid,)):
                paused.set()
                go.wait(60)
            return real(handler, *a, **k)
        res = {}
        pending = os.path.join(self.data, "pending-sweeps.json")

        def recorded():
            if not os.path.exists(pending):
                return []
            with open(pending, encoding="utf-8") as f:
                return json.load(f)
        with mock.patch.object(server_mod.Handler, name, hold):
            t = threading.Thread(target=lambda: res.update(
                probe=self.raw("GET", "/api/jobs/%s/probe/%s/16/1.json" % (jid, fid))[0]), daemon=True)
            t.start()
            self.assertTrue(paused.wait(30))
            res["delete"] = self.api("DELETE", "/api/jobs/%s" % jid)[0]
            if not pause_before:
                # pins today's "busy -> record -> retry" behaviour of DELETE: the bake still holds the preview lock,
                # so the directory stays and is named by a pending entry right now, before the bake is released
                held = [n for n in os.listdir(self.out) if n.startswith(".svf-maker-")]
                self.assertEqual(len(held), 1, held)
                self.assertIn(held[0], {os.path.basename(e["path"]) for e in recorded()}, recorded())
            go.set()
            t.join(120)
        self.assertFalse(t.is_alive())
        self.assertEqual(res["delete"], 200)
        left = [n for n in os.listdir(self.out) if n.startswith(".svf-maker-")]
        named = {os.path.basename(e["path"]) for e in recorded()}
        self.assertLessEqual(set(left), named, (left, recorded()))              # nothing left that is not recorded
        if pause_before:
            self.assertEqual(res["probe"], 404, res)                            # the probe finds no job, makes nothing
        else:
            self.assertIn(res["probe"], (404, 200))
            self.assertTrue(left, "the held bake must have kept the directory for the retry")
        self.srv.store.retry_pending_sweeps()
        self.assertEqual([n for n in os.listdir(self.out) if n.startswith(".svf-maker-")], [])   # no orphan, no tombstone
        self.assertEqual(recorded(), [])
        self.assertFalse(os.path.exists(os.path.join(self.data, "jobs", jid)))

    def test_a_probe_racing_a_delete_leaves_no_files_directory_after_the_check(self):
        self._probe_vs_delete(pause_before=False)

    def test_a_probe_racing_a_delete_cannot_make_the_directory_of_a_deleted_job(self):
        self._probe_vs_delete(pause_before=True)

    def test_an_orphan_files_directory_is_swept_at_stop_and_at_start_up(self):
        import time
        server_mod = sys.modules["server"]
        jid, first = self.done_job()                                            # the folder is known through this job
        for name in ("0123456789ab", "ba9876543210"):
            orphan = os.path.join(self.out, ".svf-maker-" + name, "work", "preview", "f01", "probe")
            os.makedirs(orphan)
            with open(os.path.join(orphan, "16-1.svf"), "wb") as f:
                f.write(b"input-derived")
        keep = os.path.join(self.out, ".svf-maker-" + jid)                      # a live job's name is never touched
        os.makedirs(keep, exist_ok=True)
        self.srv.worker.sweep_local_files()                                     # stop
        self.assertEqual(sorted(n for n in os.listdir(self.out) if n.startswith(".svf-maker-")), [])
        orphan = os.path.join(self.out, ".svf-maker-0123456789ab")
        os.makedirs(orphan)
        self.release_lock()
        srv2 = server_mod.make_server("127.0.0.1", 0, fixtures.REPO_DIR, self.data, token=localfx.TOKEN)   # a restart
        try:
            self.assertFalse(os.path.exists(orphan))
        finally:
            srv2.worker.stop()
            srv2.server_close()

    def test_a_rerun_request_in_the_completion_window_is_refused_and_the_next_run_keeps_its_directory(self):
        import threading
        jobs_mod = sys.modules["jobs"]
        jid = self.local_job()
        self.select(jid)
        real = jobs_mod.Worker._finish_local
        at_finish, go = threading.Event(), threading.Event()
        self.addCleanup(go.set)

        def paused(worker, job_id):
            at_finish.set()                                                     # 'done' is saved, cleanup not yet begun
            go.wait(30)
            return real(worker, job_id)
        with mock.patch.object(jobs_mod.Worker, "_finish_local", paused):
            self.assertEqual(self.api("POST", "/api/jobs/%s/run" % jid)[0], 200)
            self.assertTrue(at_finish.wait(60))
            self.assertEqual(self.job(jid)["state"], "done")                    # the end is already published
            for method, path, body in (("POST", "/api/jobs/%s/detect" % jid, None),
                                       ("PUT", "/api/jobs/%s/sources" % jid, {"paths": self.roots})):
                status, answer = self.api(method, path, body)
                self.assertEqual(status, 409, (path, answer))
                self.assertIn("previous run is finishing", answer["error"])
                self.assertEqual(answer.get("busy"), "lock")
            go.set()
            self.wait_done(jid)                                                 # ... and released by the worker
        self.assertEqual(self.job(jid)["state"], "done")
        st = self.job(jid)["settings"]
        self.assertEqual(self.api("POST", "/api/jobs/%s/detect" % jid)[0], 200)
        self.assertEqual(self.run_to_done(jid)["state"], "done")                # the rerun runs and finishes normally

    def _done_job_with_a_directory(self):
        jid, first = self.done_job()
        store = self.srv.store
        store.ensure_files_dir(store.load(jid))
        fd = self.files_dir(jid)
        job = store.load(jid)
        entry = {"path": fd, "output_dir": job["output_dir"], "output_id": job["output_id"], "job": jid,
                 "files_id": job["files_id"]}
        pend = os.path.join(self.data, "pending-sweeps.json")
        with open(pend, "w", encoding="utf-8") as f:
            json.dump([entry], f)
        return jid, fd, pend

    def test_a_removal_that_raises_after_the_rename_leaves_a_tracked_tombstone(self):
        jid, fd, pend = self._done_job_with_a_directory()
        shutil.rmtree(self.srv.store.path(jid))                                 # the job's metadata is gone
        real = shutil.rmtree

        def deny(path, *a, **k):
            if ".trash-" in str(path):
                raise PermissionError("denied")
            return real(path, *a, **k)
        with mock.patch.object(shutil, "rmtree", deny):
            self.srv.store.retry_pending_sweeps()
        with open(pend, encoding="utf-8") as f:
            entries = json.load(f)
        self.assertEqual(len(entries), 1, entries)
        self.assertTrue(entries[0]["path"].startswith(fd + ".trash-"), entries)  # the original entry became the tombstone's
        self.assertTrue(os.path.isdir(entries[0]["path"]))
        self.srv.store.retry_pending_sweeps()                                   # a later pass removes it
        self.assertEqual([n for n in os.listdir(self.out) if n.startswith(".svf-maker-")], [])
        with open(pend, encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])

    def test_a_tombstone_removed_meanwhile_counts_as_removed(self):
        jid, fd, pend = self._done_job_with_a_directory()
        self.srv.store.update(jid, lambda j: j.update(state="failed"))
        real = shutil.rmtree

        def already(path, *a, **k):
            if ".trash-" in str(path):
                real(path, *a, **k)                                             # another removal got there first
                raise FileNotFoundError(path)
            return real(path, *a, **k)
        with mock.patch.object(shutil, "rmtree", already):
            self.srv.store.retry_pending_sweeps()
        with open(pend, encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])
        self.assertEqual([n for n in os.listdir(self.out) if n.startswith(".svf-maker-")], [])

    def test_a_preview_paused_before_its_directory_is_made_cannot_race_a_sweep(self):
        import threading
        server_mod = sys.modules["server"]
        jid = self.local_job()
        self.select(jid)
        store = self.srv.store
        ttf = self.ttf
        real = server_mod.Handler._preview_dir
        paused, go = threading.Event(), threading.Event()
        self.addCleanup(go.set)

        def slow(handler, job, font):
            paused.set()                                                        # between the handler's load and its locks
            go.wait(20)
            return real(handler, job, font)
        res = {}
        with mock.patch.object(server_mod.Handler, "_preview_dir", slow):
            t = threading.Thread(target=lambda: res.update(
                code=self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, ttf))[0]), daemon=True)
            t.start()
            self.assertTrue(paused.wait(20))
            self.assertTrue(store.sweep_files(store.load(jid)))                 # a sweep completes in between
            self.assertFalse(os.path.exists(self.files_dir(jid)))
            go.set()
            t.join(60)
        self.assertEqual(res["code"], 200)
        fd = self.files_dir(jid)
        self.assertEqual(store.load(jid)["files_id"], [os.stat(fd).st_dev, os.stat(fd).st_ino])   # made and saved together
        # no new previews while the store is stopping or the job's cleanup is pending
        png = os.path.join(fd, "work", "preview", "%s.png" % ttf)
        self.srv.cleanup_pending.add(jid)
        os.remove(png)                                                          # (a cached preview is served without a bake)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, ttf))[0], 409)
        self.srv.cleanup_pending.discard(jid)
        self.srv.worker._stopping = True
        self.addCleanup(setattr, self.srv.worker, "_stopping", False)
        self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, ttf))[0], 503)

    def test_a_failed_tombstone_removal_at_start_up_is_recorded_and_does_not_make_the_job_inactive(self):
        # t_d1aba4b8: a tombstone is inert (the live name is what `cleanup_pending` guards): a removal that fails leaves
        # it pending and never marks the job (before, the error escaping `sweep_trash` did). The entry checked below comes
        # from `retry_pending_sweeps`' own failed removal; this test pins only the "not made inactive" rule.
        import threading
        server_mod = sys.modules["server"]
        jid, fd, pend = self._done_job_with_a_directory()
        real = shutil.rmtree

        def deny(path, *a, **k):
            if ".trash-" in str(path):
                raise PermissionError("denied")
            return real(path, *a, **k)
        self.release_lock()
        with mock.patch.object(shutil, "rmtree", deny):
            srv2 = server_mod.make_server("127.0.0.1", 0, fixtures.REPO_DIR, self.data, token=localfx.TOKEN)
        try:
            self.assertNotIn(jid, srv2.cleanup_pending)                         # the live name is gone
            self.assertEqual(self.job(jid)["state"], "done")
            self.assertTrue(srv2.store.flush_pending())
            with open(pend, encoding="utf-8") as f:
                self.assertTrue(any(".trash-" in e["path"] for e in json.load(f)))   # the tombstone is still tracked
        finally:
            srv2.worker.stop()
            srv2.server_close()

    def files_dir_in(self, out, jid):
        return os.path.join(out, ".svf-maker-" + jid)

    def test_sweep_of_an_unreachable_output_folder_is_kept_pending(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        job = self.srv.store.load(jid)
        os.rename(self.out, self.out + ".away")                                    # "unmounted": stat fails
        self.assertFalse(self.srv.store.sweep_files(job))
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            self.assertEqual([e["path"] for e in json.load(f)], [fd])
        self.srv.store.retry_pending_sweeps()                                      # still away: the entry stays
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            self.assertEqual([e["path"] for e in json.load(f)], [fd])
        os.rename(self.out + ".away", self.out)                                    # mounted again, same folder
        self.srv.store.retry_pending_sweeps()
        self.assertTrue(os.path.isdir(fd))                                         # its job is open (detected): in use
        self.srv.store.update(jid, lambda j: j.update(state="done"))
        self.srv.store.retry_pending_sweeps()
        self.assertFalse(os.path.exists(fd))
        with open(os.path.join(self.data, "pending-sweeps.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])

    def test_idle_sweep_includes_uploading_jobs(self):
        import time
        server_mod = sys.modules["server"]
        jid = self.new_job()                                                       # `uploading`, no sources yet
        fd = self.files_dir(jid)
        self.assertTrue(os.path.isdir(fd))
        self.srv.sweep_idle(now=time.monotonic() + server_mod.LOCAL_IDLE_SWEEP_S + 5)
        self.assertFalse(os.path.exists(fd))

    def test_sweep_still_happens_when_report_preservation_fails(self):
        """SOL: a report that cannot be copied (steps/ unwritable, disk full) must not skip the end-of-job sweep."""
        import jobs
        jid = self.local_job()
        self.select(jid)
        fd = self.files_dir(jid)
        real = shutil.copyfile

        def boom(src, dst, *a, **k):
            if os.sep + "steps" + os.sep in dst:
                raise OSError(28, "No space left on device")
            return real(src, dst, *a, **k)
        with mock.patch.object(shutil, "copyfile", boom):
            job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        self.assertFalse(os.path.exists(fd))

    def test_sweep_still_happens_when_the_metadata_save_fails(self):
        import jobs
        jid = self.local_job()
        self.select(jid)
        fd = self.files_dir(jid)
        real = jobs.Store.update

        def update(store, job_id, fn, timeout=None):                            # Task 4: a lifecycle holder passes a timeout
            if getattr(fn, "__name__", "") == "move":                           # _finish_local's report preservation
                raise OSError(5, "Input/output error")
            return real(store, job_id, fn, timeout=timeout)
        with mock.patch.object(jobs.Store, "update", update):
            job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        self.assertFalse(os.path.exists(fd))

    def test_identity_files_of_a_previous_run_do_not_survive_a_new_run(self):
        """SOL: metadata steps/<id>.identity.json belongs to the run that made it. A rerun whose identity check is
        unavailable must not answer with the earlier run's scores."""
        jid, first = self.done_job()
        step = next(s for s in first["steps"] if s["kind"] == "jamo")
        steps_dir = os.path.join(self.srv.store.path(jid), "steps")
        os.makedirs(steps_dir, exist_ok=True)
        planted = os.path.join(steps_dir, "%s.identity.json" % step["id"])
        with open(planted, "w") as f:
            f.write('{"stale": true}')
        self.assertEqual(self.raw("GET", "/api/jobs/%s/identity/%s.json" % (jid, step["id"]))[0], 200)
        again = self.rerun(jid)
        self.assertEqual(again["state"], "done", again.get("error"))
        self.assertFalse(os.path.exists(planted))
        self.assertEqual(self.raw("GET", "/api/jobs/%s/identity/%s.json" % (jid, step["id"]))[0], 404)

    def test_a_linked_files_directory_is_refused(self):
        jid = self.local_job()
        self.select(jid)
        fd = self.files_dir(jid)
        elsewhere = os.path.join(self.tmp, "elsewhere")
        os.makedirs(elsewhere)
        shutil.rmtree(fd)
        os.symlink(elsewhere, fd)
        ttf = next(f["id"] for f in self.job(jid)["fonts"] if f["path"] == "Munjo.ttf")
        r = self.probe(jid, ttf)
        self.assertEqual(r[0], 404)
        status, body = self.api("POST", "/api/jobs/%s/run" % jid)
        self.assertEqual(status, 409)
        self.assertEqual(os.listdir(elsewhere), [])

    def test_the_files_directory_replaced_during_the_run_fails_the_job(self):
        import jobs
        jid = self.local_job()
        self.select(jid)
        fd = self.files_dir(jid)
        real = jobs.run_command
        done = []

        def swap_then_run(argv, cwd, timeout, cancel, env=None):
            if not done:
                done.append(1)
                os.rename(fd, fd + ".away")
                os.mkdir(fd)
            return real(argv, cwd, timeout, cancel, env)
        with mock.patch.object(jobs, "run_command", swap_then_run):
            self.assertEqual(self.api("POST", "/api/jobs/%s/run" % jid)[0], 200)
            job = self.wait_done(jid)
        self.assertEqual((job["state"], job["error"]), ("failed", "output folder is gone or changed"))

    def test_idle_sweep(self):
        import time
        server_mod = sys.modules["server"]
        jid = self.local_job()
        self.select(jid)
        fd = self.files_dir(jid)
        self.assertEqual(self.probe(jid, self.ttf)[0], 200)
        self.assertTrue(os.path.isdir(fd))
        self.srv.sweep_idle(now=time.monotonic() + server_mod.LOCAL_IDLE_SWEEP_S - 5)
        self.assertTrue(os.path.isdir(fd))                                      # not idle long enough
        self.srv.sweep_idle(now=time.monotonic() + server_mod.LOCAL_IDLE_SWEEP_S + 5)
        self.assertFalse(os.path.exists(fd))
        self.assertEqual(self.probe(jid, self.ttf)[0], 200)                     # re-made on demand
        self.assertTrue(os.path.isdir(fd))

    def test_results_served_from_output(self):
        jid, job = self.done_job()
        step = next(s for s in job["steps"] if s["kind"] == "jamo")
        r = self.raw("GET", "/api/jobs/%s/face/%s.svf" % (jid, step["id"]))
        self.assertEqual(r[0], 200)
        self.assertEqual(r[2], self.read_out(step["written"]))
        self.assertEqual(r[1].get("Cache-Control"), "no-store")
        r = self.raw("GET", "/api/jobs/%s/zip" % jid)
        self.assertEqual((r[0], json.loads(r[2])["error"]), (404, "a local job writes a folder"))
        os.rename(self.out, self.out + ".moved")
        r = self.raw("GET", "/api/jobs/%s/face/%s.svf" % (jid, step["id"]))
        self.assertEqual((r[0], json.loads(r[2])["error"]), (404, "face not in the output folder"))

    def test_reports_moved_to_steps(self):
        jid, job = self.done_job()
        step = next(s for s in job["steps"] if s["kind"] == "precomposed")
        meta = self.srv.store.path(jid)
        self.assertTrue(os.path.isfile(os.path.join(meta, "steps", "%s.report.json" % step["id"])))
        self.assertEqual(step["report"], "steps/%s.report.json" % step["id"])
        r = self.raw("GET", "/api/jobs/%s/report/%s.json" % (jid, step["id"]))
        self.assertEqual(r[0], 200)
        self.assertIsInstance(json.loads(r[2]), dict)
        self.assertEqual([f for f in walk_rel(self.out) if f.endswith("report.json")], [])

    def test_output_folder_gone(self):
        jid = self.local_job()
        self.select(jid)
        os.rename(self.out, self.out + ".moved")
        os.mkdir(self.out)
        r = self.probe(jid, self.ttf)
        self.assertEqual((r[0], json.loads(r[2])["error"]), (404, "output folder is gone or changed"))
        status, body = self.api("POST", "/api/jobs/%s/run" % jid)
        self.assertEqual((status, body["error"]), (409, "output folder is gone or changed"))
        self.assertEqual(os.listdir(self.out), [])
        os.rmdir(self.out)
        os.rename(self.out + ".moved", self.out)
        self.assertEqual(self.run_to_done(jid)["state"], "done")

    def test_no_store_headers(self):
        jid, job = self.done_job()
        step = next(s for s in job["steps"] if s["kind"] == "precomposed")
        urls = ["/api/jobs/%s/face/%s.svf" % (jid, step["id"]),
                "/api/jobs/%s/source/%s.svf" % (jid, self.dos),
                "/api/jobs/%s/probe/%s/16/1.svf" % (jid, self.ttf),
                "/api/jobs/%s/probe/%s/16/1.json" % (jid, self.ttf),
                "/api/jobs/%s/preview/%s/source.png" % (jid, self.ttf),
                "/api/jobs/%s/report/%s.json" % (jid, step["id"])]
        for url in urls:
            r = self.raw("GET", url)
            self.assertEqual(r[0], 200, url)
            self.assertEqual(r[1].get("Cache-Control"), "no-store", url)

    def snapshot(self, root):
        import hashlib
        out = {}
        for dirpath, _d, names in os.walk(root):
            for name in names:
                path = os.path.join(dirpath, name)
                st = os.stat(path)
                with open(path, "rb") as f:
                    out[os.path.relpath(path, root)] = (st.st_size, st.st_mtime_ns, hashlib.sha256(f.read()).hexdigest())
        return out

    def test_no_write_outside_output(self):
        sentinels = {}
        for name in ("HOME", "TMPDIR", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
            d = os.path.join(self.tmp, "sentinel-" + name)
            os.makedirs(d)
            sentinels[name] = d
        import jobs
        import tempfile as tempmod
        before = self.snapshot(os.path.join(self.tmp, "tree", "in"))
        localfx.read_only(self, os.path.join(self.tmp, "tree", "in"))
        with mock.patch.dict(os.environ, sentinels), mock.patch.object(tempmod, "tempdir", sentinels["TMPDIR"]), \
                mock.patch.dict(jobs.ENV, {"HOME": sentinels["HOME"]}), \
                mock.patch.dict(sys.modules["preview"].ENV, {"HOME": sentinels["HOME"]}):
            jid = self.local_job()
            gz = next(f["id"] for f in self.job(jid)["fonts"] if f["path"] == "hanterm.bdf.gz")
            self.select(jid, lambda st: st["fonts"][gz].update(selected=True, dest="jamo-extra", kinds=["jamo"]))
            fd = self.files_dir(jid)
            self.assertEqual(self.probe(jid, self.ttf)[0], 200)                 # while it existed: 0700, files 0600
            self.assert_mode(fd, 0o700)
            for dirpath, dirnames, names in os.walk(fd):
                for d in dirnames:
                    self.assert_mode(os.path.join(dirpath, d), 0o700, d)
                for n in names:
                    self.assert_mode(os.path.join(dirpath, n), 0o600, n)
            job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        self.srv.worker.stop()
        self.assertEqual(self.snapshot(os.path.join(self.tmp, "tree", "in")), before)
        for name, d in sentinels.items():
            self.assertEqual(os.listdir(d), [], name)
        self.assertEqual(sorted(walk_rel(self.out)), sorted(job["result"]["files"]))
        meta = self.srv.store.path(jid)
        self.assertLessEqual({n for n in os.listdir(meta)}, {"job.json", "log.md", "steps"})
        allowed_top = {"tree", "data", "sentinel-HOME", "sentinel-TMPDIR", "sentinel-XDG_CACHE_HOME",
                       "sentinel-XDG_CONFIG_HOME"}
        self.assertEqual(set(os.listdir(self.tmp)), allowed_top)
        for dirpath, _d, names in os.walk(self.data):
            rel = os.path.relpath(dirpath, self.data)
            for n in names:
                self.assertTrue(rel.startswith("jobs") or n in ("pending-sweeps.json", "tools.pids", "tools.pids.lock", "instance.lock"),
                                (rel, n))

    def test_final_no_upload_copy(self):
        jid, job = self.done_job()
        self.assertLessEqual(set(os.listdir(self.srv.store.path(jid))), {"job.json", "log.md", "steps"})


class NoNetworkTest(unittest.TestCase):
    """The maker reaches nothing but its own loopback page. Three proofs: the code imports no network module (static),
    a local job run in this process connects to no address but loopback (a socket guard), and, where the host allows a
    network namespace, the same job in a namespace with no network at all."""

    FORBIDDEN = {"ssl", "smtplib", "ftplib", "requests", "asyncio", "http.client", "urllib.request"}

    @staticmethod
    def sources():
        import glob
        files = glob.glob(os.path.join(MAKER_DIR, "*.py")) + glob.glob(os.path.join(REPO_DIR, "tools", "*.py"))
        return sorted(f for f in files if not os.path.basename(f).startswith("test_"))

    def test_static_no_network_imports(self):
        import ast
        server_py = os.path.join(MAKER_DIR, "server.py")
        found = []
        for path in self.sources():
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), path)
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    base = node.module or ""
                    names = [base] + [base + "." + alias.name for alias in node.names]
                for name in names:
                    top = name.split(".")[0]
                    if name in self.FORBIDDEN or top in self.FORBIDDEN or top == "xmlrpc" \
                            or (top == "socket" and path != server_py):
                        found.append("%s imports %s" % (os.path.relpath(path, REPO_DIR), name))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    owner = node.func.value.id if isinstance(node.func.value, ast.Name) else ""
                    if (owner, node.func.attr) in (("asyncio", "open_connection"), ("socket", "create_connection")):
                        found.append("%s calls %s.%s" % (os.path.relpath(path, REPO_DIR), owner, node.func.attr))
        self.assertEqual(found, [])
        self.assertGreater(len(self.sources()), 20)                              # the scan really saw the code

    def test_network_off_in_process(self):
        import socket
        import ipaddress
        connects, lookups = [], []
        real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
        real_getaddrinfo, real_create = socket.getaddrinfo, socket.create_connection

        def connect(sock, address, *a, **k):
            connects.append(address)
            return real_connect(sock, address, *a, **k)

        def connect_ex(sock, address, *a, **k):
            connects.append(address)
            return real_connect_ex(sock, address, *a, **k)

        def getaddrinfo(host, *a, **k):
            lookups.append(host)
            return real_getaddrinfo(host, *a, **k)

        def create(address, *a, **k):
            lookups.append(address[0])
            return real_create(address, *a, **k)

        class Run(localfx.LocalBase):
            requests = 0

            def raw(self, *a, **k):
                Run.requests += 1
                return super().raw(*a, **k)

            def runTest(self):
                jid = self.local_job()
                job = self.job(jid)
                by = {f["path"]: f["id"] for f in job["fonts"]}
                st = job["settings"]
                st["fonts"][by["Munjo.ttf"]].update(selected=True, dest="dos", kinds=["precomposed"], sizes=[16], bpp=[1])
                self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
                self.assertEqual(self.raw("GET", "/api/jobs/%s/preview/%s/source.png" % (jid, by["Munjo.ttf"]))[0], 200)
                self.assertEqual(self.raw("GET", "/api/jobs/%s/probe/%s/16/1.json" % (jid, by["Munjo.ttf"]))[0], 200)
                done = self.run_to_done(jid)
                self.assertEqual(done["state"], "done", done.get("error"))
                step = next(s for s in done["steps"] if s["kind"] == "precomposed")
                self.assertEqual(self.raw("GET", "/api/jobs/%s/face/%s.svf" % (jid, step["id"]))[0], 200)
        with mock.patch.object(socket.socket, "connect", connect), mock.patch.object(socket.socket, "connect_ex", connect_ex), \
                mock.patch("socket.getaddrinfo", getaddrinfo), mock.patch("socket.create_connection", create):
            case = Run()
            result = unittest.TestResult()
            case.run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        self.assertGreater(len(connects), 5)
        for address in connects:
            self.assertTrue(ipaddress.ip_address(address[0]).is_loopback, address)
        for host in lookups:
            self.assertIn(host, ("127.0.0.1", "localhost"), host)
        self.assertEqual(len(connects), Run.requests)                           # one connection per request, nothing else

    def test_network_off_namespace(self):
        if shutil.which("unshare") is None or subprocess.run(["unshare", "-rn", "true"], capture_output=True).returncode != 0:
            self.skipTest("unshare -rn is not permitted on this host: the static scan and the in-process guard are the gate")
        script = ("ip link set lo up 2>/dev/null; exec %s -P -m unittest discover -s %s -p test_local.py -k LocalJobInNetns"
                  % (sys.executable, os.path.join(MAKER_DIR, "test")))
        r = subprocess.run(["unshare", "-rn", "sh", "-c", script], capture_output=True, text=True, cwd=MAKER_DIR)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class LocalJobInNetns(localfx.LocalBase):
    """The full local job, small: what the namespace test runs inside `unshare -rn` (and plain discovery runs too)."""

    def test_full_local_job(self):
        jid = self.local_job()
        job = self.job(jid)
        ttf = next(f["id"] for f in job["fonts"] if f["path"] == "Munjo.ttf")
        st = job["settings"]
        st["fonts"][ttf].update(selected=True, dest="dos", kinds=["precomposed"], sizes=[16], bpp=[1])
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        self.assertEqual(self.run_to_done(jid)["state"], "done")


if __name__ == "__main__":
    unittest.main()
