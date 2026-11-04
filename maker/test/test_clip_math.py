#!/usr/bin/env python3
"""clip.js (the clipping panel's cut-row math) against mkfont.fit_counts, under `node --test`.

  python3 -m unittest discover -s maker/test -p test_clip_math.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import inputfx  # noqa: E402
import mkfont  # noqa: E402


@unittest.skipUnless(shutil.which("node"), "no node")
class ClipMathTest(unittest.TestCase):
    def test_node_clip_math(self):
        with tempfile.TemporaryDirectory() as d:
            ttf, out, rep = (os.path.join(d, n) for n in ("t.ttf", "o.svf", "r.json"))
            with open(ttf, "wb") as f:
                f.write(inputfx.tall_ttf())
            r = subprocess.run([sys.executable, "-P", os.path.join(REPO_DIR, "tools", "mkfont.py"), ttf, out, "--size", "16",
                                "--bpp", "1", "--width", "16", "--unicode", "ascii,AC00", "--probe", "--report", rep],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(rep, encoding="utf-8") as f:
                report = json.load(f)
            boxes = {int(k, 16): v for k, v in report["boxes"].items()}
            self.assertTrue(boxes)
            cases = []
            for ascent in range(6, 17):
                top, bottom, wide = mkfont.fit_counts(boxes, 16, 15, ascent)
                cases.append({"ascent": ascent, "cellH": 15, "cellW": 16, "top": len(top), "bottom": len(bottom),
                              "wide": len(wide), "cut": len(set(top) | set(bottom))})
            self.assertTrue(any(c["cut"] for c in cases) and any(not c["cut"] for c in cases))
            path = os.path.join(d, "cases.json")
            with open(path, "w") as f:
                json.dump({"report": report, "cases": cases}, f)
            r = subprocess.run(["node", "--test", os.path.join(TEST_DIR, "test_clip_math.mjs")], capture_output=True,
                               text=True, env=dict(os.environ, CLIP_CASES=path))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
