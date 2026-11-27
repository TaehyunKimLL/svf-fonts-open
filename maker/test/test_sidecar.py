#!/usr/bin/env python3
"""maker/sidecar.py in source mode (`python3 -P maker/sidecar.py ...`): the tool table, run-tool, selfcheck, --version.
The frozen build is exercised by test_frozen.py.

  python3 -m unittest discover -s maker/test -p 'test_sidecar.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import filecmp
import json
import re
import shutil
import subprocess
import tempfile
import unittest

import sidecar

SIDECAR = os.path.join(MAKER_DIR, "sidecar.py")
SMALL = os.path.join(REPO_DIR, "ttf", "neodgm", "neodgm.ttf")
ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/"), "LANG": "C.UTF-8"}
if os.name == "nt":                     # what a tool gets there (toolrun.base_env): SYSTEMROOT, the temp folders, UTF-8
    import toolrun
    ENV = toolrun.base_env(os.environ)


def run(*args, cwd=None, timeout=120):
    return subprocess.run([sys.executable, "-P", SIDECAR] + list(args), capture_output=True, text=True, cwd=cwd,
                          env=ENV, timeout=timeout)


class SidecarTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-sidecar-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_table_is_the_spec_table(self):
        self.assertEqual(sorted(sidecar.TOOLS), ["bdfface", "hwpfont", "instancer", "jamoset", "jamovec", "johab844",
                                                 "macfbit3", "macfbit_svf", "macsfnt", "mkfont", "rawcarve", "srcprep",
                                                 "svf2to3", "svf2ttf", "svfdy", "svfline"])
        self.assertEqual(sidecar.TOOLS["instancer"], ("module", "args"))
        self.assertEqual(sidecar.TOOLS["srcprep"], ("maker", "exit"))
        self.assertEqual({sidecar.TOOLS[n] for n in ("jamoset", "jamovec", "mkfont", "bdfface", "johab844", "hwpfont",
                                                    "rawcarve")},
                         {("tools", "bare")})
        self.assertEqual({sidecar.TOOLS[n] for n in ("macfbit_svf", "macfbit3", "macsfnt", "svf2to3", "svfdy",
                                                    "svfline", "svf2ttf")}, {("tools", "exit")})

    def test_every_tool_smoke(self):
        for name, (args, code, stream, prefix) in sorted(sidecar.SMOKE.items()):
            out = run("run-tool", name, *args)
            self.assertEqual(out.returncode, code, (name, out.stderr[-300:]))
            text = out.stdout if stream == "stdout" else out.stderr
            self.assertTrue(text.startswith(prefix), (name, text[:100]))
        self.assertEqual(set(sidecar.SMOKE), set(sidecar.TOOLS))

    def test_unknown_tool(self):
        out = run("run-tool", "nosuch")
        self.assertEqual(out.returncode, 2)
        self.assertIn("run-tool: unknown tool 'nosuch'", out.stderr)

    def test_traceback_exit_1(self):
        # mkfont catches an unreadable input itself (exit 1, no traceback); johab844 lets the FileNotFoundError escape
        out = run("run-tool", "johab844", os.path.join(self.tmp, "none"), os.path.join(self.tmp, "base"),
                  os.path.join(self.tmp, "O.SVF"))
        self.assertEqual(out.returncode, 1, out.stderr)
        self.assertIn("Traceback", out.stderr)
        self.assertNotIn("[PYI-", out.stderr)

    def test_bare_main_exit_code(self):
        a, b = os.path.join(self.tmp, "a.svf"), os.path.join(self.tmp, "b.svf")
        args = ["--size", "16", "--bpp", "1", "--unicode", "ascii"]
        out = run("run-tool", "mkfont", SMALL, a, *args)
        self.assertEqual(out.returncode, 0, out.stderr)
        ref = subprocess.run([sys.executable, "-P", os.path.join(REPO_DIR, "tools", "mkfont.py"), SMALL, b] + args,
                             capture_output=True, text=True, env=ENV)
        self.assertEqual(ref.returncode, 0, ref.stderr)
        self.assertTrue(filecmp.cmp(a, b, shallow=False))

    def test_selfcheck_source(self):
        out = run("selfcheck")
        self.assertEqual(out.returncode, 0, out.stderr)
        info = json.loads(out.stdout)
        self.assertIs(info["frozen"], False)
        self.assertEqual(len(info["recipes"]), 7)
        self.assertEqual(info["tools"], sorted(sidecar.TOOLS))
        self.assertEqual(set(info["modules"]), set(sidecar.GRAPH_MODULES))
        self.assertEqual([v for v in info["modules"].values() if v is not None], [])
        self.assertEqual(info["budget"], {"startup_cleanup_s": 30.0, "stop_timeout_s": 30, "stop_sweep_s": 8.0,
                                          "reap_total_s": 10.0, "recog_probe_s": 20})
        self.assertEqual(set(info["flags"]), {"isolated", "ignore_environment", "safe_path", "no_site"})

    def test_version(self):
        out = run("--version")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertRegex(out.stdout.strip(), r"^svf-maker-sidecar 0\.1\.0 .+ python 3\.\d+\.\d+$")

    def test_serve_passes_args(self):
        out = run("serve", "--nope")
        self.assertEqual(out.returncode, 2)

    def test_usage(self):
        for args in ([], ["nosuch"], ["run-tool"]):
            out = run(*args)
            self.assertEqual(out.returncode, 2, args)
            self.assertIn("usage", out.stderr)


if __name__ == "__main__":
    unittest.main()
