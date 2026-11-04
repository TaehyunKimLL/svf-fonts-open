#!/usr/bin/env python3
"""svfview.js: the page's drawing layer parses and touches no DOM at import (the pixel tests are in
tools/test_web_picker.py TestModule, which has the built module).

  python3 -m unittest discover -s maker/test -p test_svfview.py
"""

import json
import os
import shutil
import subprocess
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
SVFVIEW_JS = os.path.join(MAKER_DIR, "static", "svfview.js")

EXPORTS = ["NOTICE", "init", "load", "openChain", "setScale", "S", "drawLineInto", "drawGlyphsInto", "drawLine",
           "drawGlyphs", "glyphCell", "pieces", "drawPiece", "codePoints", "syllables", "has", "metrics", "lineBox", "cellBox", "decodeRGBA", "isCodePoint"]


@unittest.skipUnless(shutil.which("node"), "no node: svfview.js is not checked")
class SvfviewTest(unittest.TestCase):
    def test_module_parses_and_has_no_dom_at_import(self):
        self.assertEqual(subprocess.run(["node", "--check", SVFVIEW_JS]).returncode, 0)
        script = ("const m = await import(%s); console.log(JSON.stringify(Object.keys(m)));"
                  % json.dumps("file://" + SVFVIEW_JS))
        r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(set(EXPORTS) - set(json.loads(r.stdout))), [])

    def test_scale_rounding_and_notice(self):
        script = ("const m = await import(%s);"
                  "try { m.openChain([]); } catch (e) { console.log(e.message); }"
                  "console.log(m.S(-5), m.S(5));" % json.dumps("file://" + SVFVIEW_JS))
        r = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["preview module not built: run maker/build-wasm.sh", "-5 5"])


if __name__ == "__main__":
    unittest.main()
