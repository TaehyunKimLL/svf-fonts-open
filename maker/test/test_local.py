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

    def done_job(self, edit=None):
        jid = self.local_job()
        self.select(jid, edit)
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        return jid, job

    def read_out(self, rel):
        with open(os.path.join(self.out, rel), "rb") as f:
            return f.read()


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
                mock.patch.object(jobs.caps, "recog_dir", return_value="/nonexistent-recog"), \
                mock.patch.dict(self.srv.worker.caps, {"recog": True}):
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
            server2 = servermod.make_server("127.0.0.1", 0, fixtures.REPO_DIR, self.data, token=localfx.TOKEN)
            server2.startup_sweep.join(10)
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
            if not calls and path == fd:
                calls.append(path)
                raise OSError("busy")
            return real(path, *a, **k)
        with mock.patch.object(shutil, "rmtree", once):
            self.assertEqual(self.api("DELETE", "/api/jobs/%s" % jid)[0], 200)
        pending = os.path.join(self.data, "pending-sweeps.json")
        with open(pending, encoding="utf-8") as f:
            entries = json.load(f)
        self.assertEqual([e["path"] for e in entries], [fd])
        self.assertTrue(os.path.isdir(fd))
        entries.append({"path": "/tmp/x", "output_dir": "/tmp", "output_id": [1, 2], "job": "0123456789ab"})
        with open(pending, "w", encoding="utf-8") as f:
            json.dump(entries, f)
        self.srv.store.retry_pending_sweeps()
        self.assertFalse(os.path.exists(fd))
        with open(pending, encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])

    def test_pending_sweep_of_a_replaced_output_folder(self):
        jid = self.local_job()
        fd = self.files_dir(jid)
        real = shutil.rmtree

        def fail(path, *a, **k):
            if path == fd:
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
            self.assertEqual(json.load(f), [])                                   # the entry is stale: dropped
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

    def files_dir_in(self, out, jid):
        return os.path.join(out, ".svf-maker-" + jid)

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
            self.assertEqual(mode_of(fd), 0o700)
            for dirpath, dirnames, names in os.walk(fd):
                for d in dirnames:
                    self.assertEqual(mode_of(os.path.join(dirpath, d)), 0o700, d)
                for n in names:
                    self.assertEqual(mode_of(os.path.join(dirpath, n)), 0o600, n)
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
                self.assertTrue(rel.startswith("jobs") or n == "pending-sweeps.json", (rel, n))

    def test_final_no_upload_copy(self):
        jid, job = self.done_job()
        self.assertLessEqual(set(os.listdir(self.srv.store.path(jid))), {"job.json", "log.md", "steps"})


if __name__ == "__main__":
    unittest.main()
