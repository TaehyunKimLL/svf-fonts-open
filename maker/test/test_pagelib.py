#!/usr/bin/env python3
"""pagelib.js (the page's pure helpers) under node: the dy key rule is settings._dy_key's, which is svfdy.json_dy's.

  python3 -m unittest discover -s maker/test -p test_pagelib.py
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import settings  # noqa: E402

PAGELIB = os.path.join(MAKER_DIR, "static", "pagelib.js")


def node(body, *args):
    script = "const L = await import(%s);\n%s" % (json.dumps("file://" + PAGELIB), body)
    r = subprocess.run(["node", "--input-type=module", "-e", script, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


@unittest.skipUnless(shutil.which("node"), "no node")
class PagelibTest(unittest.TestCase):
    KEYS = ["5", "65", "0x41", "g", "-5", "0x110000", "zz", "", "12ab", "010", "0b11", "0o17", "0", "00", "가", "10"]

    def test_dy_key_is_the_settings_rule(self):
        got = node("console.log(JSON.stringify(JSON.parse(process.argv[1]).map(k => L.dyKey(k))));", json.dumps(self.KEYS))
        self.assertEqual(got, [settings._dy_key(k) for k in self.KEYS])

    def test_parse_dy_text(self):
        got = node("console.log(JSON.stringify(JSON.parse(process.argv[1]).map(t => L.parseDyText(t))));",
                   json.dumps(["5=1", "U+0041=1 g=-1 0x67=2", "010=1", "g=200", "g=x", "", "=1", "a b", "==3"]))
        self.assertEqual(got, [{"53": 1}, {"65": 1, "103": 2}, None, None, None, {}, None, None, {"61": 3}])

    def test_step_sig_changes_with_the_step(self):
        step = {"id": "s01", "state": "done", "seconds": 1.5, "kind": "precomposed", "size": 16, "bpp": 1, "name": "A.SVF",
                "output": "work/s01/A.SVF"}
        got = node("""const a = JSON.parse(process.argv[1]);
const same = L.stepSig(a, null) === L.stepSig({...a}, null);
const rerun = L.stepSig(a, null) !== L.stepSig({...a, seconds: 1.6}, null);
const mate = L.stepSig(a, null) !== L.stepSig(a, {...a, id: "s02"});
const ident = L.stepSig(a, null) !== L.stepSig({...a, identity: {available: true, identity: "pass"}}, null);
console.log(JSON.stringify([same, rerun, mate, ident]));""", json.dumps(step))
        self.assertEqual(got, [True, True, True, True])


    def test_busy_policy_retries_lock_and_preview_then_stops(self):
        got = node("""const out = [];
for (const [m, k] of [["DELETE", "lock"], ["POST", "preview"], ["GET", "preparing"]]) {
  out.push([0, 1, 2, 3].map((r) => L.busyRetryDelay(m, k, r, 0)));
  out.push(L.busyRetryDelay(m, k, 0, 15000));
}
console.log(JSON.stringify(out));""")
        self.assertEqual(got, [[500, 1000, 2000, None], None] * 3)

    def test_busy_policy_never_retries_a_preparing_post_or_an_untagged_answer(self):
        got = node("""const out = [L.busyRetryDelay("POST", "preparing", 0, 0)];
for (const k of [undefined, "", "other", true]) for (const m of ["GET", "POST", "PUT", "DELETE"]) out.push(L.busyRetryDelay(m, k, 0, 0));
console.log(JSON.stringify(out));""")
        self.assertEqual(got, [None] * 17)


if __name__ == "__main__":
    unittest.main()
