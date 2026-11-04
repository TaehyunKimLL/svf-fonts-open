#!/usr/bin/env python3
"""recog_score.py tests: the identity scoring CLI, run against a stub recogniser (the real one is not in the
repository). The stub reads every syllable correctly except the ones listed in bad.json.

  python3 -m unittest discover -s maker/test -p 'test_recog_score.py'
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import jamoset
import mkfont
import recog_score

SCRIPT = os.path.join(MAKER_DIR, "recog_score.py")
SVF = os.path.join(REPO_DIR, "svf")

STUB = '''
import json, os

_HERE = os.path.dirname(os.path.abspath(__file__))
_rows = [0]


def load(model):
    if os.path.exists(os.path.join(_HERE, "raise.flag")):
        raise RuntimeError("no weights")
    if os.path.exists(os.path.join(_HERE, "sleep.txt")):
        import time
        time.sleep(float(open(os.path.join(_HERE, "sleep.txt")).read()))
    return "net"


def split(idx):
    idx = [int(i) for i in idx]
    return [i // 588 for i in idx], [(i // 28) % 21 for i in idx], [i % 28 for i in idx]


def _heads(net, arr):
    bad = json.load(open(os.path.join(_HERE, "bad.json")))
    bad_syl, k = set(bad["syllables"]), bad["k"]
    out = ([], [], [])
    sizes = (19, 21, 28)
    for _ in range(len(arr)):
        s = _rows[0]
        _rows[0] += 1
        right = (s // 588, (s // 28) % 21, s % 28)
        for h in range(3):
            row = [-20.0] * sizes[h]
            row[(right[h] + 1) % sizes[h] if (s in bad_syl and h == k) else right[h]] = 0.0
            if os.path.exists(os.path.join(_HERE, "allnan.flag")):
                row = [float("nan")] * sizes[h]
            if os.path.exists(os.path.join(_HERE, "nonfinite.flag")):
                if s == 0 and h == 1:
                    row = [float("nan")] * sizes[h]
                if s == 1 and h == 0:
                    row[right[h]] = float("-inf")
            out[h].append(row)
    return out
'''


def write_stub(directory, bad=(), k=1, sleep=0):
    """A stub recogniser in @p directory (recog.py, bad.json): every syllable is read right except the syllable indices
    in @p bad on head @p k; load() sleeps @p sleep seconds. Used by the worker and server tests too."""
    with open(os.path.join(directory, "recog.py"), "w") as f:
        f.write(STUB)
    with open(os.path.join(directory, "bad.json"), "w") as f:
        json.dump({"syllables": list(bad), "k": k}, f)
    if sleep:
        with open(os.path.join(directory, "sleep.txt"), "w") as f:
            f.write(str(sleep))


def face_path(rel):
    return os.path.join(SVF, rel)


def read(path):
    with open(path, "rb") as f:
        return f.read()


class RecogScoreTest(unittest.TestCase):
    FACE = "dos/NEODG16A.SVF"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.recog_dir = os.path.join(self.tmp.name, "recog")
        os.mkdir(self.recog_dir)
        with open(os.path.join(self.recog_dir, "recog.py"), "w") as f:
            f.write(STUB)
        face = jamoset.parse_svfn(read(face_path(self.FACE)))
        t = jamoset.unpack(face.jset)
        # the syllables whose slot-k piece is 161 in NEODG16A, and k
        self.slot = "m"
        k = 1
        self.bad = [s for s in range(11172) if jamoset.pieces_of(t, 0xAC00 + s)[k] == 161]
        self.assertTrue(self.bad)
        with open(os.path.join(self.recog_dir, "bad.json"), "w") as f:
            json.dump({"syllables": self.bad, "k": k}, f)

    def run_raw(self, face, *flags, env=None, out_name="out.json"):
        out = os.path.join(self.tmp.name, out_name)
        e = {k: v for k, v in os.environ.items() if k != "SVF_RECOG_DIR"}
        e["SVF_RECOG_DIR"] = self.recog_dir
        e.update(env or {})
        e = {k: v for k, v in e.items() if v is not None}
        r = subprocess.run([sys.executable, "-P", SCRIPT, face, "-o", out, *flags], capture_output=True, text=True,
                           env=e)
        return r, out

    def run_cli(self, face, *flags):
        r, out = self.run_raw(face, *flags)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            return json.load(f)

    def test_piece_161_fails_every_other_passes(self):
        out = self.run_cli(face_path(self.FACE), "--arrays", "lists")
        flags = {(p["slot"], p["piece"]): p["flag"] for p in out["pieces"]}
        self.assertEqual(flags[(self.slot, 161)], "fail")
        self.assertEqual({f for key, f in flags.items() if key != (self.slot, 161)} - {"unused"}, {"pass"})
        self.assertEqual(out["face"]["identity"], "fail")

    def test_face_summary_and_json_shape(self):
        out = self.run_cli(face_path(self.FACE), "--arrays", "lists")
        ks = set(cp - 0xAC00 for cp in mkfont.NAMED_RANGES["ksx1001-hangul"]())
        self.assertAlmostEqual(out["face"]["recog_ks"], 1 - len(ks & set(self.bad)) / 2350)
        self.assertAlmostEqual(out["face"]["recog_all"], 1 - len(self.bad) / 11172)
        self.assertEqual((out["model"], out["thresholds"], out["bpp_note"]), ("11-12", {"pass": 0.95, "warn": 0.80}, None))
        self.assertEqual((out["available"], out["applicable"]), (True, True))
        self.assertEqual(sorted(out["pieces"][0]),
                         ["flag", "jamo", "nll", "piece", "read", "set", "slot", "users", "worst"])
        self.assertLessEqual(len(out["pieces"][0]["worst"]), 5)
        counts = out["face"]["pieces"]
        by_flag = {}
        for p in out["pieces"]:
            by_flag[p["flag"]] = by_flag.get(p["flag"], 0) + 1
        self.assertEqual(counts, {k: by_flag.get(k, 0) for k in ("pass", "warn", "fail", "unscored", "unused")})
        self.assertEqual(out["face"]["unscored"], 0)
        # sorted fail, warn, pass, unused
        order = {"fail": 0, "warn": 1, "pass": 2, "unscored": 3, "unused": 4}
        self.assertEqual([order[p["flag"]] for p in out["pieces"]], sorted(order[p["flag"]] for p in out["pieces"]))
        bad161 = out["pieces"][0]
        self.assertEqual((bad161["piece"], bad161["slot"], bad161["users"], bad161["read"]), (161, "m", len(self.bad), 0.0))
        self.assertEqual(sorted(w["cp"] for w in bad161["worst"]), [0xAC00 + s for s in self.bad])
        self.assertTrue(all(w["got"] for w in bad161["worst"]))

    def test_non_finite_rows_are_unscored_and_the_json_is_strict(self):
        open(os.path.join(self.recog_dir, "nonfinite.flag"), "w").close()
        r, out = self.run_raw(face_path(self.FACE), "--arrays", "lists")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as fh:
            text = fh.read()

        def refuse(name):
            raise ValueError("non-standard JSON constant " + name)
        data = json.loads(text, parse_constant=refuse)          # what the browser's JSON.parse does
        self.assertEqual(data["face"]["unscored"], 2)
        self.assertNotEqual(data["face"]["identity"], "pass")
        self.assertLess(data["face"]["recog_all"], 1.0)

    def test_every_syllable_unscored_is_an_error_not_a_warning(self):
        open(os.path.join(self.recog_dir, "allnan.flag"), "w").close()
        r, out = self.run_raw(face_path(self.FACE), "--arrays", "lists")
        self.assertEqual(r.returncode, 1)
        self.assertIn("recog: every syllable was unscored", r.stderr)
        self.assertFalse(os.path.exists(out))

    def test_threads_below_one_exit_2(self):
        r, out = self.run_raw(face_path(self.FACE), "--arrays", "lists", "--threads", "0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("recog: --threads must be >= 1", r.stderr)
        self.assertFalse(os.path.exists(out))

    def test_a_failure_outside_the_recogniser_is_not_labelled_recog(self):
        # an unreadable --arrays numpy without numpy would say "No module named numpy"; a bug in the scorer likewise
        r, out = self.run_raw(face_path(self.FACE), "--arrays", "numpy",
                              env={"PYTHONPATH": os.path.join(self.tmp.name, "nonexistent")})
        if importlib.util.find_spec("numpy"):
            self.skipTest("numpy is installed")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stderr.startswith("recog_score:"), r.stderr)

    def test_a_raising_recogniser_exits_1(self):
        open(os.path.join(self.recog_dir, "raise.flag"), "w").close()
        r, out = self.run_raw(face_path(self.FACE), "--arrays", "lists")
        self.assertEqual(r.returncode, 1)
        self.assertIn("recog: no weights", r.stderr)
        self.assertFalse(os.path.exists(out))

    def test_no_recog_dir_exits_2(self):
        r, out = self.run_raw(face_path(self.FACE), "--arrays", "lists", env={"SVF_RECOG_DIR": None})
        self.assertEqual(r.returncode, 2)
        self.assertIn("SVF_RECOG_DIR is not a directory with recog.py", r.stderr)
        empty = os.path.join(self.tmp.name, "empty")
        os.mkdir(empty)
        r, out = self.run_raw(face_path(self.FACE), "--arrays", "lists", env={"SVF_RECOG_DIR": empty})
        self.assertEqual(r.returncode, 2)
        self.assertIn("SVF_RECOG_DIR is not a directory with recog.py", r.stderr)
        self.assertFalse(os.path.exists(out))

    def test_lists_array_bpp(self):
        one = recog_score.lists_array([bytes([0b10100000, 0b01000000])], 2, 3, 1)
        self.assertEqual(one, [[[True, False, True], [False, True, False]]])
        two = recog_score.lists_array([bytes([0b01101100])], 1, 3, 2)     # levels 1, 2, 3
        self.assertEqual(two, [[[False, True, True]]])

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "numpy is not installed: the numpy path is unverified")
    def test_numpy_path(self):
        lists = self.run_cli(face_path(self.FACE), "--arrays", "lists")
        # the stub's rows are counted per process, so the second run starts again
        numpy_out = self.run_cli(face_path(self.FACE), "--arrays", "numpy")
        self.assertEqual(numpy_out, lists)


if __name__ == "__main__":
    unittest.main()
