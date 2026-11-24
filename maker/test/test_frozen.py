#!/usr/bin/env python3
"""The frozen sidecar (spec 10.2): selfcheck, run-tool under `env -i`, byte-equal tool output against the pinned wheels,
the served maker, jobs equal to a source-mode run, process lifecycle, the optional recogniser.

Needs the build: SVF_MAKER_SIDECAR (the executable); the byte-equal and job classes also SVF_MAKER_REF_SITE (the pinned
wheels' directory, absolute). SVF_MAKER_STAGED_REPO (the staged repo/ tree) is the frozen server's repo, else the
checkout. A missing variable skips its class naming it, unless SVF_MAKER_FROZEN_REQUIRED=1, which makes it a failure
(maker/build-sidecar.sh sets it, so a required class can never pass by skipping).

  maker/build-sidecar.sh   (builds, then runs this file)
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools"), TEST_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hashlib
import http.client
import json
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

import caps
import fixtures
import inputfx
import jobs
import localfx
import server
import sidecar
import test_recog_score
import toolreg
import toolrun
import wincompat

SIDECAR = os.environ.get("SVF_MAKER_SIDECAR")
REF_SITE = os.environ.get("SVF_MAKER_REF_SITE")
STAGED = os.environ.get("SVF_MAKER_STAGED_REPO")
REQUIRED = os.environ.get("SVF_MAKER_FROZEN_REQUIRED") == "1"
PY3 = sys.executable if os.name == "nt" else (shutil.which("python3") or "/usr/bin/python3")   # Windows: no python3
REPO = STAGED or REPO_DIR


def alive(pid):
    return toolrun.alive(pid)


def wait_until(cond, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


class Needs(unittest.TestCase):
    """setUpClass: every variable in NEEDS names an existing path, else skip (or fail when required)."""

    NEEDS = ("SVF_MAKER_SIDECAR",)

    @classmethod
    def setUpClass(cls):
        for name in cls.NEEDS:
            value = os.environ.get(name)
            if not (value and os.path.exists(value)):
                if REQUIRED:
                    raise AssertionError("%s is required (SVF_MAKER_FROZEN_REQUIRED=1) and is not set to an existing path"
                                         % name)
                raise unittest.SkipTest("%s is not set (the frozen sidecar is not built)" % name)
        super().setUpClass()


def isolated_env(tmp):
    """The environment of the isolation tests: an empty PATH directory and a PYTHONPATH holding a json.py that raises."""
    empty, planted = os.path.join(tmp, "empty"), os.path.join(tmp, "planted")
    os.makedirs(empty, exist_ok=True)
    os.makedirs(planted, exist_ok=True)
    with open(os.path.join(planted, "json.py"), "w") as f:
        f.write("raise RuntimeError('planted json.py was imported')\n")
    env = {"PATH": empty, "HOME": os.environ.get("HOME", "/"), "LANG": "C.UTF-8", "PYTHONPATH": planted}
    return dict(env, **WIN_ENV)


# Windows: the keys any process there is started with (SYSTEMROOT, the temp folders); POSIX: none (`env -i`)
WIN_ENV = {k: os.environ[k] for k in toolrun.WINDOWS_KEYS if os.environ.get(k)} if os.name == "nt" else {}


class FrozenSelfcheckTest(Needs):
    def test_selfcheck(self):
        tmp = tempfile.mkdtemp(prefix="svf-frz-")
        self.addCleanup(shutil.rmtree, tmp, True)
        out = subprocess.run([SIDECAR, "selfcheck"], env=isolated_env(tmp), capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        info = json.loads(out.stdout)
        self.assertIs(info["frozen"], True)
        self.assertEqual(info["flags"], {"isolated": True, "ignore_environment": True, "safe_path": True, "no_site": True})
        home = os.path.dirname(os.path.realpath(SIDECAR))
        for entry in info["path"]:
            self.assertTrue(os.path.realpath(entry).startswith(home), entry)
        self.assertEqual(info["tools"], sorted(sidecar.TOOLS))
        self.assertEqual(set(info["modules"]), set(sidecar.GRAPH_MODULES))
        self.assertEqual({k: v for k, v in info["modules"].items() if v is not None}, {})
        import recipe
        self.assertEqual(info["recipes"], sorted(recipe.library()))        # bundled as <_internal>/recipes
        self.assertEqual(len(info["recipes"]), 7)
        self.assertEqual(info["budget"], {"startup_cleanup_s": server.STARTUP_CLEANUP_S, "stop_timeout_s": 30,
                                          "stop_sweep_s": jobs.STOP_SWEEP_TOTAL_S, "reap_total_s": toolreg.REAP_TOTAL_S,
                                          "recog_probe_s": caps.RECOG_PROBE_S})


@wincompat.posix_only("fork and PR_SET_PDEATHSIG (on Windows the tool's Job Object closes with the sidecar: "
                      "FrozenJobTest.test_sigkill_sidecar_kills_tool)")
class FrozenForkRaceTest(Needs):
    def test_tool_whose_sidecar_died_before_the_prctl_exits(self):
        """A stand-in sidecar starts `run-tool` with its own pid in the environment and dies at once: the tool must not
        outlive it (the getppid-after-prctl guard; the plain PDEATHSIG signal never comes in that window)."""
        tmp = tempfile.mkdtemp(prefix="svf-frz-")
        self.addCleanup(shutil.rmtree, tmp, True)
        big = os.path.join(tmp, "Big.ttf")
        with open(big, "wb") as f:
            f.write(inputfx.big_composite_ttf(11172))
        script = (
            "import ctypes, os, subprocess, sys, time\n"
            "ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)\n"                 # this process is the subreaper
            "r, w = os.pipe()\n"
            "pid = os.fork()\n"
            "if pid == 0:\n"                                             # the stand-in sidecar
            "    env = dict(os.environ, SVF_MAKER_SIDECAR_PID=str(os.getpid()))\n"
            "    p = subprocess.Popen([sys.argv[1], 'run-tool', 'jamovec', 'master', sys.argv[2], '-o', sys.argv[3], '--components'],\n"
            "                         env=env, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            "    os.write(w, str(p.pid).encode())\n"
            "    os._exit(0)\n"
            "os.waitpid(pid, 0)\n"
            "tool = int(os.read(r, 32))\n"
            "time.sleep(2.5)\n"
            "try:\n"
            "    st = open('/proc/%d/stat' % tool).read().rsplit(')', 1)[1].split()[0]\n"
            "except OSError:\n"
            "    st = 'gone'\n"
            "print(tool, st)\n"
            "try:\n"
            "    os.killpg(tool, 9)\n"
            "except OSError:\n"
            "    pass\n")
        env = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/"), "LANG": "C.UTF-8"}
        for i in range(4):
            out = subprocess.run([PY3, "-I", "-c", script, SIDECAR, big, os.path.join(tmp, "m%d.json" % i)], env=env,
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn(out.stdout.split()[1], ("Z", "X", "gone"), "run %d: the tool outlived its parent: %s" % (i, out.stdout))


class FrozenRunToolTest(Needs):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-frz-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = isolated_env(self.tmp)
        self.cwd = os.path.join(self.tmp, "cwd")
        os.makedirs(self.cwd)
        for name in ("jamoset", "mkfont", "json"):               # a planted module in the cwd must never be imported
            with open(os.path.join(self.cwd, name + ".py"), "w") as f:
                f.write("raise RuntimeError('planted %s.py was imported')\n" % name)

    def test_every_tool_smoke_isolated(self):
        for name, (args, code, stream, prefix) in sorted(sidecar.SMOKE.items()):
            out = subprocess.run([SIDECAR, "run-tool", name] + args, env=self.env, cwd=self.cwd, capture_output=True,
                                 text=True, timeout=60)
            self.assertEqual(out.returncode, code, (name, out.stderr[-300:]))
            text = out.stdout if stream == "stdout" else out.stderr
            self.assertTrue(text.startswith(prefix), (name, text[:120]))
            self.assertNotIn("planted", out.stderr)

    def test_unknown_and_traceback(self):
        out = subprocess.run([SIDECAR, "run-tool", "nosuch"], env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 2)
        self.assertIn("run-tool: unknown tool 'nosuch'", out.stderr)
        out = subprocess.run([SIDECAR, "run-tool", "johab844", os.path.join(self.tmp, "none"), "b", "o"], env=self.env,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 1)
        self.assertIn("Traceback", out.stderr)
        self.assertNotIn("[PYI-", out.stderr)


class FrozenByteEqualTest(Needs):
    """The frozen tool's output equals the reference: the same tool source under the pinned wheels (python3 -S)."""

    NEEDS = ("SVF_MAKER_SIDECAR", "SVF_MAKER_REF_SITE")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-frz-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # SOURCE_DATE_EPOCH: fontTools stamps head.modified with the wall clock otherwise, and two runs a second apart differ
        self.env = dict(isolated_env(self.tmp), SOURCE_DATE_EPOCH="1700000000")
        self.ref_env = dict({"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/"), "LANG": "C.UTF-8",
                             "PYTHONPATH": REF_SITE, "SOURCE_DATE_EPOCH": "1700000000"}, **WIN_ENV)
        if os.name == "nt":
            self.ref_env["PYTHONUTF8"] = "1"            # as the frozen tool (UTF-8 mode) and a maker-launched tool

    def path(self, *parts):
        p = os.path.join(self.tmp, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def frozen(self, name, args):
        return subprocess.run([SIDECAR, "run-tool", name] + args, env=self.env, cwd=self.tmp, capture_output=True,
                              text=True, timeout=300)

    def reference(self, name, args):
        if name == "instancer":
            prefix = [PY3, "-S", "-P", "-m", "fontTools.varLib.instancer"]
        elif name == "srcprep":
            prefix = [PY3, "-S", "-P", os.path.join(REPO_DIR, "maker", "srcprep.py")]
        else:
            prefix = [PY3, "-S", "-P", os.path.join(REPO_DIR, "tools", name + ".py")]
        return subprocess.run(prefix + args, env=self.ref_env, cwd=self.tmp, capture_output=True, text=True, timeout=300)

    def same(self, name, make_args, outs=("out",)):
        """Run the tool both ways (make_args(tag) -> args, writing into <tag>/); the outputs must be cmp-equal."""
        a_args, b_args = make_args("frozen"), make_args("ref")
        a, b = self.frozen(name, a_args), self.reference(name, b_args)
        self.assertEqual((a.returncode, b.returncode), (0, 0), (a.stderr[-400:], b.stderr[-400:]))
        for out in outs:
            with open(self.path("frozen", out), "rb") as f, open(self.path("ref", out), "rb") as g:
                da, db = f.read(), g.read()
            self.assertEqual(hashlib.sha256(da).hexdigest(), hashlib.sha256(db).hexdigest(), (name, out, len(da), len(db)))
        return len(da)

    def test_svf2ttf_bdf(self):
        face = os.path.join(REPO_DIR, "svf", "dos", "NEODG16G.SVF")
        n = self.same("svf2ttf", lambda t: ["bdf", face, self.path(t, "out"), "--licence", "none"])
        self.assertGreater(n, 100000)

    def test_rawcarve_region_and_bdf(self):
        a, b = self.path("in", "a,1.bin"), self.path("in", "b.bin")          # a comma in a name: --group
        os.makedirs(os.path.dirname(a), exist_ok=True)
        with open(a, "wb") as f:
            f.write(bytes(range(256)) * 64)
        with open(b, "wb") as f:
            f.write(bytes(reversed(range(256))) * 64)
        self.same("rawcarve", lambda t: ["region", "--group", a, b, "-o", self.path(t, "out")])
        self.same("rawcarve", lambda t: ["bdf", a, "--glyph", "8x16", "--chars", "ascii", "-o", self.path(t, "out")])

    def test_mkfont_neodgm_16_1(self):
        src = os.path.join(REPO_DIR, "ttf", "neodgm", "neodgm.ttf")
        n = self.same("mkfont", lambda t: [src, self.path(t, "out"), "--size", "16", "--bpp", "1", "--unicode",
                                           "ascii,ksx1001-hangul"])
        self.assertGreater(n, 100000)

    def test_mkfont_nanumgothic_17_2(self):
        src = os.path.join(REPO_DIR, "ttf", "nanumgothic", "NanumGothic-Bold.ttf")
        n = self.same("mkfont", lambda t: [src, self.path(t, "out"), "--size", "17", "--bpp", "2", "--unicode",
                                           "ascii,ksx1001-hangul"])
        self.assertGreater(n, 100000)

    def test_jamoset_dos_844(self):
        han = self.path("in", "HAN.FNT")
        fixtures._dos_raw(han)
        self.same("jamoset", lambda t: [han, "--layout", "844", "--check", "-o", self.path(t, "out")])

    def test_jamoset_from_ttf_adaptive(self):
        ttf = fixtures._composite_ttf(self.path("in", "C.ttf"))
        self.same("jamoset", lambda t: ["--layout", "adaptive", "--from-ttf", ttf, "--size", "16", "--binarize",
                                        "threshold", "--check", "-o", self.path(t, "out")])

    def test_srcprep_ttc_face(self):
        coll = self.path("in", "t.ttc")
        with open(coll, "wb") as f:
            f.write(inputfx.ttc([inputfx.ttf("One", (50, 0, 950, 800)), inputfx.ttf("Two", (60, 0, 940, 790))]))
        self.same("srcprep", lambda t: ["ttc-face", coll, self.path(t, "out"), "--index", "1"])

    def test_instancer_real_op(self):
        var = self.path("in", "V.ttf")
        with open(var, "wb") as f:
            f.write(inputfx.variable_ttf())
        self.same("instancer", lambda t: [var, "wght=400", "-o", self.path(t, "out")])

    def test_macsfnt_extract_unicode(self):
        fk = self.path("in", "S.dfont")
        with open(fk, "wb") as f:
            f.write(inputfx.fork([(b"sfnt", 128, "Synth", inputfx.mac_cmap_ttf())]))
        self.same("macsfnt", lambda t: ["extract", fk, self.path(t, "out"), "--id", "128"])
        self.same("macsfnt", lambda t: ["unicode", self.path(t, "out"), self.path(t, "out2")], outs=("out2",))

    def test_johab844(self):
        han = self.path("in", "HAN.FNT")
        fixtures._dos_raw(han)
        eng = self.path("in", "ENG.FNT")
        fixtures._eng(eng)
        base = os.path.join(REPO, "svf", "dos", "NEODG16.SVF")
        self.same("johab844", lambda t: [han, base, self.path(t, "out"), "--eng", eng])

    def test_debian_pillow_informational(self):
        src = os.path.join(REPO_DIR, "ttf", "neodgm", "neodgm.ttf")
        args = [src, self.path("plain", "out"), "--size", "16", "--bpp", "1", "--unicode", "ascii,ksx1001-hangul"]
        frozen = self.frozen("mkfont", [src, self.path("frozen", "out")] + args[2:])
        plain = subprocess.run([PY3, "-P", os.path.join(REPO_DIR, "tools", "mkfont.py")] + args,
                               env=dict({"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/")}, **WIN_ENV), capture_output=True,
                               text=True, timeout=300)
        self.assertEqual(frozen.returncode, 0, frozen.stderr)
        if plain.returncode != 0:
            print("\ndebian pillow: plain python3 failed (%d)" % plain.returncode)
            return
        with open(self.path("frozen", "out"), "rb") as f, open(self.path("plain", "out"), "rb") as g:
            da, db = f.read(), g.read()
        print("\ndebian pillow: %s" % ("equal" if da == db else "differs: %d vs %d bytes" % (len(da), len(db))))


class FrozenServeTest(Needs, localfx.SubprocessLocalBase):
    repo = REPO

    def test_port_line_fast(self):
        self.assertLess(self.port_seconds, 2.0)

    def test_http_basics(self):
        status, headers, body = self.raw("GET", "/", token=False)
        self.assertEqual(status, 200)
        status, headers, body = self.raw("GET", "/static/wasm/svf.wasm", token=False)
        self.assertEqual((status, headers.get("Content-Type")), (200, "application/wasm"))
        self.assertEqual(self.raw("GET", "/api/caps", token=False)[0], 403)
        status, body = self.api("GET", "/api/caps")
        self.assertEqual((status, body), (200, {"wasm": True, "mask_libs": False, "recog": False, "local": True}))

    def test_stale_files_swept_before_port(self):
        jid = self.local_job()
        files = self.files_dir(jid)
        self.assertTrue(os.path.isdir(files))
        orphan = os.path.join(self.out, ".svf-maker-aaaaaaaaaaaa")
        os.makedirs(orphan)
        self.proc.kill()                                  # no stop sweep: the next start must clean up
        self.proc.wait()
        self.assertTrue(os.path.isdir(files))
        self.start_server()
        self.assertFalse(os.path.exists(files), "the dead run's files directory outlived the next start-up")
        self.assertFalse(os.path.exists(orphan))


class FrozenStartTest(Needs):
    def run_sidecar(self, env, *args):
        tmp = tempfile.mkdtemp(prefix="svf-frz-")
        self.addCleanup(shutil.rmtree, tmp, True)
        full = dict({"PATH": tmp, "HOME": tmp, "LANG": "C.UTF-8", "SVF_MAKER_DATA": os.path.join(tmp, "d"),
                     "SVF_MAKER_REPO": REPO, "SVF_MAKER_BIND": "127.0.0.1:0"}, **WIN_ENV)
        full.update(env)
        return subprocess.run([SIDECAR, "serve"] + list(args), env=full, capture_output=True, text=True, timeout=60)

    def test_bad_token_and_bind(self):
        out = self.run_sidecar({"SVF_MAKER_TOKEN": "xyz"})
        self.assertEqual(out.returncode, 2)
        self.assertIn("SVF_MAKER_TOKEN: 32 hex characters", out.stderr)
        self.assertEqual(out.stdout, "")
        out = self.run_sidecar({"SVF_MAKER_TOKEN": localfx.TOKEN, "SVF_MAKER_BIND": "0.0.0.0:0"})
        self.assertEqual(out.returncode, 2)
        self.assertIn("local mode binds 127.0.0.1 or ::1 only", out.stderr)
        self.assertEqual(out.stdout, "")


class LongJobMixin:
    """A local job on a big composite font: its `jamovec master` step runs about 20 s; its pid is in tools.pids."""

    def long_job(self):
        big = os.path.join(self.tmp, "bigtree")
        os.makedirs(big)
        with open(os.path.join(big, "Big.ttf"), "wb") as f:
            f.write(inputfx.big_composite_ttf(11172))                # jamovec master --components: 19.8 s measured here
        jid = self.local_job(roots=[big])
        job = self.job(jid)
        fid = job["fonts"][0]["id"]
        st = job["settings"]
        st["fonts"][fid].update(selected=True, dest="dos", kinds=["jamo"], sizes=[16], bpp=[1], experimental=True)
        st["batch"]["layout"] = "adaptive"
        status, body = self.api("PUT", "/api/jobs/%s/settings" % jid, st)
        self.assertEqual(status, 200, body)
        status, body = self.api("POST", "/api/jobs/%s/run" % jid)
        self.assertEqual(status, 200, body)
        pids = os.path.join(self.data, "tools.pids")
        self.assertTrue(wait_until(lambda: os.path.exists(pids) and open(pids).read().strip(), 60), "no tool started")
        pid = int(open(pids).read().split()[1])
        self.addCleanup(lambda: wincompat.kill_group(pid) if alive(pid) else None)
        self.assertTrue(alive(pid))
        return jid, pid


class FrozenJobTest(Needs, LongJobMixin, localfx.SubprocessLocalBase, localfx.LocalRunBase):
    NEEDS = ("SVF_MAKER_SIDECAR", "SVF_MAKER_REF_SITE")
    repo = REPO

    def ref_run(self, edit):
        """The same job in-process with the tools run by the pinned wheels (toolrun.PYTHON -> a wrapper)."""
        wrapper = os.path.join(self.tmp, "ref-python")
        if wincompat.WIN:                                 # a batch file there (a tool argv's first word may be one)
            wrapper += ".bat"
            with open(wrapper, "w") as f:
                f.write('@set "PYTHONPATH=%s"\n@"%s" -S %%*\n' % (REF_SITE, PY3))
        else:
            with open(wrapper, "w") as f:
                f.write("#!/bin/sh\nPYTHONPATH=%s exec %s -S \"$@\"\n" % (REF_SITE, PY3))
            os.chmod(wrapper, 0o755)

        class Ref(localfx.LocalRunBase):
            def runTest(self):
                pass
        ref = Ref()
        ref.setUp()
        self.addCleanup(ref.doCleanups)
        with mock.patch.object(toolrun, "PYTHON", wrapper):
            jid = ref.local_job()
            ref.select(jid)
            ref.select_johab844(jid)
            job = ref.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        return ref, jid, job

    def frozen_run(self):
        jid = self.local_job()
        self.select(jid)
        self.select_johab844(jid)
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        return jid, job

    def test_frozen_jobs_match_source(self):
        jid, job = self.frozen_run()
        ref, rjid, rjob = self.ref_run(None)
        got = localfx.normalise_job(self.out, job, REPO, self.tmp)
        want = localfx.normalise_job(ref.out, rjob, REPO_DIR, ref.tmp)
        self.assertEqual(got["files"], want["files"])
        self.assertEqual(got["faces"], want["faces"])
        self.assertTrue(got["faces"])
        self.assertEqual(got["commands"], want["commands"])
        self.assertTrue(any(c[:3] == ["python3", "-P", "tools/johab844.py"] for c in got["commands"]), got["commands"])

    def read_notes(self, out, jid):
        texts = {}
        for rel in walk_files(out):
            if rel.endswith(".TXT") or rel.endswith("BUILD.md"):
                with open(os.path.join(out, rel), encoding="utf-8") as f:
                    text = f.read()
                texts[rel.replace(jid, "<id>")] = text.replace(jid, "<id>")
        return texts

    def test_frozen_notes_equal_source(self):
        jid, _job = self.frozen_run()
        ref, rjid, _ = self.ref_run(None)
        got, want = self.read_notes(self.out, jid), self.read_notes(ref.out, rjid)

        def scrub(text):
            return "\n".join(l for l in text.splitlines()
                             if not re.match(r"^(Date:|repo HEAD|seconds:)", l)).replace(self.tmp, "<T>").replace(ref.tmp, "<T>")
        self.assertEqual(set(got), set(want))
        for rel in got:
            self.assertEqual(scrub(got[rel]), scrub(want[rel]), rel)
        everything = "\n".join(got.values())
        for bad in (os.path.dirname(os.path.realpath(SIDECAR)), REPO, "run-tool"):
            self.assertNotIn(bad, everything)
        self.assertTrue(any("# johab844: Hangul redrawn on the base face svf/dos/NEODG16.SVF" in t for t in got.values()))
        self.assertTrue(any("# johab844:" in t for t in want.values()))

    def test_jamo_adaptive_job(self):
        jid = self.local_job()
        job = self.job(jid)
        ttf = next(f["id"] for f in job["fonts"] if f["path"] == "Munjo.ttf")
        st = job["settings"]
        st["fonts"][ttf].update(selected=True, dest="dos", kinds=["jamo"], sizes=[16], bpp=[1], experimental=True)
        st["batch"]["layout"] = "adaptive"
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))

    def test_sigterm_cancels_tool(self):
        jid, pid = self.long_job()
        time.sleep(0.5)
        self.request_stop()                               # SIGTERM; on Windows the end of stdin
        self.assertEqual(self.proc.wait(60), 0)
        self.assertTrue(wait_until(lambda: not alive(pid), 5), "the tool outlived the sidecar's SIGTERM")
        self.assertFalse(os.path.exists(self.files_dir(jid)))
        self.assertEqual(open(os.path.join(self.data, "tools.pids")).read().strip(), "")

    def test_sigkill_sidecar_kills_tool(self):
        jid, pid = self.long_job()
        time.sleep(1.5)       # past the tool's start-up (bootloader + interpreter): the prctl is set; an earlier kill is the
        self.proc.kill()      # documented window the next start's registry reap covers
        self.proc.wait()
        self.assertTrue(wait_until(lambda: not alive(pid), 3), "PR_SET_PDEATHSIG did not take the tool down")



def walk_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".svf-maker-")]
        for name in filenames:
            yield os.path.relpath(os.path.join(dirpath, name), root)


@wincompat.posix_only("the PR_SET_PDEATHSIG knob (on Windows a tool cannot outlive its sidecar: its Job Object closes "
                      "with it; the reap is test_toolreg's)")
class FrozenNoPdeathsigTest(Needs, LongJobMixin, localfx.SubprocessLocalBase):
    repo = REPO

    def extra_env(self):
        return {"SVF_MAKER_NO_PDEATHSIG": "1"}                 # reaches the tool through base_env

    def test_sigkill_without_pdeathsig_reaped_on_restart(self):
        jid, pid = self.long_job()
        self.proc.kill()
        self.proc.wait()
        time.sleep(1)
        self.assertTrue(alive(pid), "the knob did not disable PR_SET_PDEATHSIG in the tool")
        self.assertIn(str(pid), open(os.path.join(self.data, "tools.pids")).read())
        self.assertTrue(os.path.isdir(self.files_dir(jid)))
        self.start_server()
        self.assertFalse(alive(pid), "the new sidecar did not reap the old tool before its port line")
        self.assertFalse(os.path.exists(self.files_dir(jid)))
        job = self.job(jid)
        self.assertEqual((job["state"], job["error"]), ("failed", "interrupted"))


class FrozenRecogTest(Needs, localfx.SubprocessLocalBase, localfx.LocalRunBase):
    repo = REPO

    def jamo_job(self):
        jid = self.local_job()
        self.select(jid)
        job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        return next(s for s in job["steps"] if s["kind"] == "jamo")

    def test_recog_unconfigured(self):
        self.assertEqual(self.api("GET", "/api/caps")[1]["recog"], False)
        self.assertEqual(self.jamo_job()["identity"]["available"], False)


class FrozenRecogStubTest(FrozenRecogTest):
    def extra_env(self):
        recog = os.path.join(self.tmp, "recog")
        os.makedirs(recog, exist_ok=True)
        test_recog_score.write_stub(recog)
        stub = wincompat.interpreter_stub(
            os.path.join(self.tmp, "stub-python"),
            "[ \"$1\" = -P ] && [ \"$2\" = -c ] && exit 0      # the 7.7 probe\n"
            "for a; do [ \"$a\" = numpy ] && a=lists; set -- \"$@\" \"$a\"; shift; done\n"
            "exec %s \"$@\"" % PY3,
            "import subprocess, sys\nargs = sys.argv[1:]\nif args[:2] == ['-P', '-c']:\n    sys.exit(0)\n"
            "sys.exit(subprocess.call([%r] + ['lists' if a == 'numpy' else a for a in args]))" % PY3)
        return {"SVF_RECOG_DIR": recog, "SVF_RECOG_PYTHON": stub}

    def test_recog_unconfigured(self):
        pass

    def test_recog_external_stub(self):
        self.assertEqual(self.api("GET", "/api/caps")[1]["recog"], True)
        step = self.jamo_job()
        self.assertTrue(step["identity"]["available"], step["identity"])


if __name__ == "__main__":
    unittest.main()
