#!/usr/bin/env python3
"""toolrun.py tests: the launcher shapes in both modes, the note text, the scrubbed environment, and that every
launch site goes through toolrun.

  python3 -m unittest discover -s maker/test -p 'test_toolrun.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools"), TEST_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import glob
import json
import subprocess
import tempfile
import re
import unittest
from unittest import mock

import jobs
import preview
import routes
import settings
import toolrun

PATHS = {"tools": "/T", "src": "/u/in.ttf", "out": "/w/OUT.SVF", "work": "/w", "eng": None, "latin": None,
         "master": "/w/master.json", "range_file": "/w/range-2350.txt", "base": "/R/svf/dos/NEODG16.SVF",
         "htbl": "/w/htbl.htbl1", "pylib": None,
         "recipe_files": {"font": "/u/font.rom", "bios": "/u/bios.bin"}}   # a known set (86Box)
PATHS_ALT = dict(PATHS, eng="/u/eng.fnt", latin="/u/latin.bdf", pylib="/lib")


class ShapesTest(unittest.TestCase):
    def test_source_shapes(self):
        self.assertEqual(toolrun.tool("mkfont", "/T"), [sys.executable, "-P", "/T/mkfont.py"])
        self.assertEqual(toolrun.maker_script("srcprep"), [sys.executable, "-P", os.path.join(toolrun.MAKER_DIR, "srcprep.py")])
        self.assertEqual(toolrun.module("fontTools.varLib.instancer"), [sys.executable, "-P", "-m", "fontTools.varLib.instancer"])

    def test_python_seam(self):
        with mock.patch.object(toolrun, "PYTHON", "/w/ref-python"):
            self.assertEqual(toolrun.tool("mkfont", "/T")[0], "/w/ref-python")

    def test_frozen_shapes(self):
        with mock.patch.object(toolrun, "FROZEN", True):
            self.assertEqual(toolrun.tool("mkfont", "/T"), [sys.executable, "run-tool", "mkfont"])
            self.assertEqual(toolrun.maker_script("srcprep"), [sys.executable, "run-tool", "srcprep"])
            self.assertEqual(toolrun.module("fontTools.varLib.instancer"), [sys.executable, "run-tool", "instancer"])

    def test_split_prefix_all_shapes_either_mode(self):
        for frozen in (False, True):
            with mock.patch.object(toolrun, "FROZEN", frozen):
                self.assertEqual(toolrun.split_prefix(["/p", "-P", "/T/mkfont.py", "a", "b"]),
                                 (["/p", "-P", "/T/mkfont.py"], ["a", "b"]))
                self.assertEqual(toolrun.split_prefix(["/p", "-P", "-m", "fontTools.varLib.instancer", "x"])[1], ["x"])
                self.assertEqual(toolrun.split_prefix(["/s", "run-tool", "mkfont", "a"]),
                                 (["/s", "run-tool", "mkfont"], ["a"]))
        for bad in ([], ["/p"], ["/p", "-c", "print(1)"], ["/p", "-P"], ["/p", "-P", "notpy"], ["/s", "run-tool"]):
            with self.assertRaises(ValueError):
                toolrun.split_prefix(bad)

    def test_note_prefix_same_text_both_modes(self):
        cases = [(lambda: toolrun.tool("mkfont", "/T"), ["python3", "-P", "tools/mkfont.py"]),
                 (lambda: toolrun.maker_script("srcprep"), ["python3", "-P", "maker/srcprep.py"]),
                 (lambda: toolrun.module("fontTools.varLib.instancer"),
                  ["python3", "-P", "-m", "fontTools.varLib.instancer"])]
        for make, want in cases:
            for frozen in (False, True):
                with mock.patch.object(toolrun, "FROZEN", frozen):
                    self.assertEqual(toolrun.note_prefix(make() + ["a"]), (want, ["a"]))

    def test_note_prefix_passes_non_launchers(self):
        argv = [sys.executable, "-c", "print(1)", "/w/out"]
        self.assertEqual(toolrun.note_prefix(argv), ([], argv))

    def test_note_argv_repo_relative(self):
        a = toolrun.tool("johab844", "/R1/tools") + ["/u/H.FNT", "/R1/svf/dos/NEODG16.SVF", "/w/O.SVF"]
        with mock.patch.object(toolrun, "FROZEN", True):
            b = toolrun.tool("johab844", "/mnt/X/resources/repo/tools") + [
                "/u/H.FNT", "/mnt/X/resources/repo/svf/dos/NEODG16.SVF", "/w/O.SVF"]
        self.assertEqual(toolrun.note_argv(a, "/R1"), toolrun.note_argv(b, "/mnt/X/resources/repo"))
        self.assertEqual(toolrun.note_argv(a, "/R1")[4], "svf/dos/NEODG16.SVF")

    def test_base_env(self):
        self.assertEqual(toolrun.base_env({"PATH": "/b", "HOME": "/h", "SVF_MAKER_TOKEN": "x" * 32, "PYTHONPATH": "/e",
                                           "SVF_MAKER_NO_PDEATHSIG": "yes"}),
                         {"PATH": "/b", "HOME": "/h", "LANG": "C.UTF-8"})
        self.assertEqual(toolrun.base_env({"JAMOSET_PYLIB": "/lib"})["JAMOSET_PYLIB"], "/lib")
        self.assertEqual(toolrun.base_env({"JAMOSET_MASK_FONT": "/f.ttf"})["JAMOSET_MASK_FONT"], "/f.ttf")
        self.assertNotIn("JAMOSET_PYLIB", toolrun.base_env({"JAMOSET_PYLIB": ""}))
        self.assertEqual(toolrun.base_env({"SVF_MAKER_NO_PDEATHSIG": "1"})["SVF_MAKER_NO_PDEATHSIG"], "1")

    def test_tool_env_has_no_maker_keys(self):
        # the token, the bind, the data root and every PYTHON* key never reach a tool; the one SVF_ key ever allowed is
        # the test knob, and only as "1"
        for env in (jobs.ENV, preview.ENV,
                    toolrun.base_env({**os.environ, "SVF_MAKER_TOKEN": "a" * 32, "PYTHONHOME": "/x"})):
            self.assertEqual([k for k in env if k.startswith("PYTHON")], [])
            self.assertEqual([k for k in env if k.startswith("SVF_") and k not in toolrun.TEST_KEYS], [])   # unfrozen
            self.assertIn(env.get("SVF_MAKER_NO_PDEATHSIG", "1"), ("1",))

    def test_sidecar_pid_only_when_frozen(self):
        self.assertNotIn(toolrun.SIDECAR_PID_KEY, toolrun.base_env({}))
        with mock.patch.object(toolrun, "FROZEN", True):
            env = toolrun.base_env({"SVF_MAKER_TOKEN": "t" * 32, "SVF_MAKER_SIDECAR_PID": "7"})
        self.assertEqual(env[toolrun.SIDECAR_PID_KEY], str(os.getpid()))           # its own pid, never the inherited value
        self.assertEqual([k for k in env if k.startswith("SVF_") and k not in toolrun.TEST_KEYS + (toolrun.SIDECAR_PID_KEY,)], [])

    def test_modules_read_base_env_at_import(self):
        # a fresh interpreter, so the module-level ENV of jobs and preview is built under these variables
        env = dict(os.environ, JAMOSET_PYLIB="/l", JAMOSET_MASK_FONT="/f", SVF_MAKER_TOKEN="t" * 32)
        code = "import json, jobs, preview; print(json.dumps([jobs.ENV, preview.ENV]))"
        out = subprocess.run([sys.executable, "-c", code], env=dict(env, PYTHONPATH=os.pathsep.join(
            [MAKER_DIR, os.path.join(REPO_DIR, "tools")])), capture_output=True, text=True, cwd=TEST_DIR)
        self.assertEqual(out.returncode, 0, out.stderr)
        for got in json.loads(out.stdout):
            self.assertEqual(got["JAMOSET_PYLIB"], "/l")
            self.assertEqual(got["JAMOSET_MASK_FONT"], "/f")
            self.assertNotIn("SVF_MAKER_TOKEN", got)

    def test_note_text_removes_repo_prefix(self):
        a = toolrun.note_text("base /R1/svf/dos/N.SVF and /R1/tools/x.py", "/R1")
        b = toolrun.note_text("base /mnt/X/repo/svf/dos/N.SVF and /mnt/X/repo/tools/x.py", "/mnt/X/repo")
        self.assertEqual(a.replace("/R1", ""), a)
        self.assertEqual(a, b)
        self.assertEqual(a, "base svf/dos/N.SVF and tools/x.py")
        self.assertEqual(toolrun.note_text("x", None), "x")

    def test_new_files_use_no_bare_tmp(self):
        # the TMP_DIR rule: no new file hard-codes /tmp
        pattern = re.compile(r"""['"]/tmp""")
        files = [os.path.join(MAKER_DIR, n) for n in ("toolrun.py", "toolreg.py", "sidecar.py", "build-sidecar.sh")]
        files += [os.path.join(TEST_DIR, n) for n in ("test_toolrun.py", "test_toolreg.py", "test_sidecar.py",
                                                       "test_frozen.py", "parent_harness.py",
                                                       "test_sidecar_imports.py")]
        for ext in ("js", "mjs", "sh", "py"):
            files += glob.glob(os.path.join(REPO_DIR, "desktop", "**", "*." + ext), recursive=True)
        files = [f for f in files if os.path.isfile(f) and os.sep + "spike" + os.sep not in f
                 and os.sep + "node_modules" + os.sep not in f]
        for path in files:
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if os.path.basename(path) == "test_toolrun.py" and "pattern" in line:
                        continue
                    self.assertIsNone(pattern.search(line), "%s:%d" % (path, n))


def _commands_of_all_kinds():  # noqa
    """Every argv the builders make, for the drift test's fonts and one op of each source kind."""
    import test_server
    argvs = []
    for font in test_server.canonical_fonts():
        for route in routes.routes(font):
            layout = route.layouts[0] if route.layouts else None
            for paths in (PATHS, PATHS_ALT):
                argvs += list(route.prepare_commands(font, layout, dict(paths)))
                for bpp in route.bpps:
                    size = 16 if route.sizes is None else route.sizes[0]
                    try:
                        argvs += list(route.commands(font, size, bpp, layout, ("2350", None), dict(paths), []))
                    except ValueError as exc:               # the one refusal: bdfface without its Latin companion
                        if "Latin companion" not in str(exc):
                            raise
        for svf in ({"bpp": 1, "version": 2}, {"bpp": 2, "version": 3, "jset_version": 2}):
            argvs += routes.svf_commands(dict(font, svf=svf), dict(PATHS), [])
            argvs += routes.svf_commands(dict(font, svf=svf), dict(PATHS), ["--jset-version", "1"])
    ops = [{"op": "rsrc-sfnt", "id": 128}, {"op": "ttc-face", "index": 1}, {"op": "mac-cmap"},
           {"op": "instance", "coords": {"wght": 700}}, {"op": "pcf-bdf"}, {"op": "mac-fork"},
           {"op": "mac-fbit3"}, {"op": "mac-htbl"}, {"op": "mac-fork-named"}]
    for op in ops:
        got, _ = routes.source_commands([op], "/u/s", "/w", "/T")
        argvs += got
    argvs.append(settings._dy_argv({"0x41": 1}, "precomposed", True, "/u/s", "/w/o", tempfile.gettempdir(), "/T"))
    return [a for a in argvs if a]


class BuildersTest(unittest.TestCase):
    def test_every_builder_uses_toolrun_both_modes(self):
        import tempfile
        for frozen in (False, True):
            with mock.patch.object(toolrun, "FROZEN", frozen), tempfile.TemporaryDirectory() as tmp:
                with mock.patch.dict(os.environ, {"TMPDIR": tmp}):
                    argvs = _commands_of_all_kinds()
                    mk = toolrun.tool("mkfont", "/T") + ["/u/a.ttf", "/w/O.SVF", "--size", "16", "--cell", "18"]
                    argvs.append(settings.probe_argv(mk, "/u/a.ttf", "/w/p.svf", "/w/p.json", 16))
                self.assertGreater(len(argvs), 40)
                seen = set()
                for argv in argvs:
                    prefix, _ = toolrun.split_prefix(argv)
                    self.assertEqual(prefix[1], "run-tool" if frozen else "-P", argv)
                    seen.add(toolrun.prefix_name(prefix))
                self.assertTrue({"mkfont", "jamoset", "jamovec", "srcprep", "macsfnt", "macfbit3", "instancer",
                                 "svf2to3", "svfdy", "johab844", "bdfface", "macfbit_svf"} <= seen, seen)

    def test_probe_argv_keeps_prefix_and_flags_frozen(self):
        with mock.patch.object(toolrun, "FROZEN", True):
            mk = toolrun.tool("mkfont", "/T") + ["/u/a.ttf", "/w/O.SVF", "--size", "16", "--bpp", "2",
                                                 "--unicode", "ascii", "--cell", "18"]
            got = settings.probe_argv(mk, "/u/a.ttf", "/w/p.svf", "/w/p.json", 16)
        self.assertEqual(got[:3], [sys.executable, "run-tool", "mkfont"])
        self.assertEqual(got[3:5], ["/u/a.ttf", "/w/p.svf"])
        self.assertIn("--probe-cell", got)
        self.assertEqual(got[got.index("--probe-cell") + 1], "18")

    def test_no_stray_launcher(self):
        for path in sorted(glob.glob(os.path.join(MAKER_DIR, "*.py"))):
            name = os.path.basename(path)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if name not in ("toolrun.py", "zipout.py"):
                self.assertNotIn("sys.executable", text, name)
            self.assertIsNone(re.search(r"^(PY|SRCPREP)\s*=", text, re.M), name)
            if name in ("routes.py", "settings.py", "jobs.py"):
                self.assertIsNone(re.search(r'"[a-z0-9_]+\.py"', text), name)


class LifecycleHelpersTest(unittest.TestCase):
    def test_set_pdeathsig_knob(self):
        with mock.patch.dict(os.environ, {"SVF_MAKER_NO_PDEATHSIG": "1"}):
            self.assertIs(toolrun.set_pdeathsig(15), False)


class RecogArgvTest(unittest.TestCase):
    def test_recog_argv(self):
        self.assertIsNone(toolrun.recog_argv({"recog": False}, "/R"))
        self.assertEqual(toolrun.recog_argv({"recog": True, "recog_python": "/py"}, "/R"),
                         ["/py", "-P", "/R/maker/recog_score.py"])
        self.assertEqual(toolrun.recog_argv({"recog": True, "recog_python": None}, "/R"),
                         toolrun.maker_script("recog_score"))


if __name__ == "__main__":
    unittest.main()
