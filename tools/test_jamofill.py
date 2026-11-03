#!/usr/bin/env python3
"""jamofill.py tests on a synthetic strike whose syllables are the OR of context-free jamo, so the right answer is known.

  python3 tools/test_jamofill.py
"""

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jamofill as F  # noqa: E402
import jamoset as J  # noqa: E402

W, H = 10, 12


def bits(v, n):
    return [(v >> i) & 1 for i in range(n)]


def jamo(kind, j):
    """A context-free synthetic jamo: initials in rows 0-1 (columns 0-4), vowels in columns 8-9 (rows 2-6), finals in
    rows 9-10 (columns 0-4); each a 5-bit code of its index + 1, drawn twice so every stroke has two pixels."""
    b = 0
    code = bits(j + 1, 5)
    for i, on in enumerate(code):
        if not on:
            continue
        if kind == "i":
            b |= 1 << (0 * W + i) | 1 << (1 * W + i)
        elif kind == "m":
            b |= 1 << ((2 + i) * W + 8) | 1 << ((2 + i) * W + 9)
        else:
            b |= 1 << (9 * W + i) | 1 << (10 * W + i)
    return b


def syllable(s):
    L, V, T = s // 588, (s // 28) % 21, s % 28
    g = jamo("i", L) | jamo("m", V)
    return g | jamo("f", T) if T else g


class Synthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        F.MEDIAL_PENALTY = 0          # the synthetic vowels have no bars or ticks; test_medial_gates covers the gate
        cls.tmp = tempfile.TemporaryDirectory()
        glyphs = {0xAC00 + s: syllable(s) for s in range(F.NSYL)}
        glyphs[0x41] = (1 << (3 * W + 1)) | (1 << (4 * W + 1)) | (1 << (5 * W + 2))
        glyphs[0x20] = 0
        cls.strike = os.path.join(cls.tmp.name, "syn-12.npz")
        F.write_strike(cls.strike, H, W, 11, glyphs, {0x41: 4, 0x20: 3})
        cls.st = F.read_strike(cls.strike)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_strike_round_trip(self):
        self.assertEqual(self.st.syl[123], syllable(123))
        self.assertEqual(self.st.others[0x41][1], 4)

    def test_decompose_recovers_jamo(self):
        lib, own = F.decompose_strike(self.st)
        self.assertEqual(lib[("i", 7)][0], jamo("i", 7))
        self.assertEqual(lib[("m", 13)][0], jamo("m", 13))
        self.assertEqual(lib[("f", 21)][0], jamo("f", 21))
        s = 5 * 588 + 8 * 28 + 4
        self.assertEqual(own[("i", s)] | own[("m", s)] | own[("f", s)], syllable(s))

    def fill(self, name, pixel=False):
        lib, own = F.decompose_strike(self.st)
        prob = F.Problem(self.st, lib, own)
        t, tie = F.skeleton(name)
        f = F.Fill(prob, t, tie, pixel=pixel)
        f.descend()
        return f

    def test_111_is_exact_and_compacts(self):
        f = self.fill("111")
        self.assertEqual(f.cost(), 0)
        data = F.build_face(f)
        self.assertTrue(F.verify(f, data))
        info = F.face_info(data)
        self.assertEqual((info["ni"], info["nm"], info["nf"], info["lc"], info["tc"]), (1, 1, 1, 1, 1))
        self.assertEqual(info["pieces"], 19 + 21 + 27)
        self.assertLessEqual(len(data), F.size_estimate(f))
        rep = F.judge(f)
        self.assertEqual(rep["exact"], F.NSYL)
        self.assertEqual(rep["exact_ks"], 2350)
        self.assertEqual(rep["confuse_total"], 0)

    def test_844_compacts_to_one_set(self):
        f = self.fill("844", pixel=True)
        self.assertEqual(f.cost(), 0)
        t, _ = f.compact()
        self.assertEqual((t.ni, t.nm, t.nf), (1, 1, 1))
        self.assertTrue(F.verify(f, F.build_face(f)))

    def test_budget_ties_until_it_fits(self):
        f = self.fill("844")
        before = len(F.build_face(f))
        f2 = self.fill("844")
        # force distinct pieces per set so ties have something to save: give set 1 of every medial a shifted copy
        for (k, s, j), u in list(f2.slot_unit.items()):
            if k == "m" and s == 1:
                b = f2.bmp[u] >> 1
                f2.p.lib[(k, j)].append(b)
                f2.bmp[u] = b
        bigger = len(F.build_face(f2))
        self.assertGreater(bigger, before)
        F.fit_budget(f2, before)
        self.assertLessEqual(len(F.build_face(f2)), before)

    def test_plain_tables_keep_sets(self):
        f = self.fill("844")
        data = F.build_face(f, compact=False)
        info = F.face_info(data)
        self.assertEqual((info["lc"], info["tc"], info["ni"], info["nm"], info["nf"]), (2, 2, 8, 4, 4))
        self.assertTrue(F.verify(f, data))

    def test_merge_sets(self):
        f = self.fill("844")
        f.merge_sets("i", 0, 1)
        self.assertEqual(f.t.ni, 7)
        self.assertTrue(all(s < 7 for s in f.t.init_set))
        self.assertTrue(F.verify(f, F.build_face(f)))

    def test_tied_skeleton_keeps_sharing(self):
        f = self.fill("111")
        path = os.path.join(self.tmp.name, "T.SVF")
        open(path, "wb").write(F.build_face(f))
        t, tie = F.face_skeleton(path, True)
        self.assertEqual(len(set(tie.values())), 19 + 21 + 27)

    def test_strokes(self):
        self.assertEqual(F.strokes(jamo("i", 0), W, H), (0, 0))        # one 2-pixel column
        self.assertEqual(F.strokes(jamo("i", 30), W, H), (2, 0))       # two 5-pixel rows
        bar = sum(1 << (4 * W + x) for x in range(9))
        self.assertEqual(F.strokes(bar, W, H), (1, 0))

    def test_widths_and_ticks(self):
        bar = lambda y, x0=0, x1=9: sum(1 << (y * W + x) for x in range(x0, x1))
        col = lambda x, y0, y1: sum(1 << (y * W + x) for y in range(y0, y1))
        p_ok = col(1, 2, 7) | col(5, 2, 7)                       # ㅍ-like stems, both 1 px
        p_bad = col(1, 2, 7) | col(5, 2, 7) | col(6, 2, 7)       # one stem 2 px wide
        self.assertFalse(F.width_violation(p_ok, W, H))
        self.assertTrue(F.width_violation(p_bad, W, H))
        o = bar(9) | (1 << (8 * W + 4))                          # ㅗ: tick above the bar
        u = bar(6) | (1 << (7 * W + 4))                          # ㅜ: tick below
        self.assertTrue(F.tick_ok(o, 8, W, H))
        self.assertFalse(F.tick_ok(o, 13, W, H))
        self.assertTrue(F.tick_ok(u, 13, W, H))
        self.assertFalse(F.tick_ok(bar(9), 8, W, H))              # a ㅗ that lost its tick
        self.assertTrue(F.tick_ok(bar(9), 18, W, H))

    def test_cap_ok(self):
        px = lambda pts: sum(1 << (y * W + x) for x, y in pts)
        cap, bar = [(2, 2)], [(x, 3) for x in range(5)]
        ring = [(1, 4), (2, 4), (3, 4), (0, 5), (4, 5), (1, 6), (2, 6), (3, 6)]
        self.assertTrue(F.cap_ok(("i", 18), px(cap + bar + ring), W, H))
        self.assertFalse(F.cap_ok(("i", 18), px(cap + ring), W, H))           # ㅎ without its bar
        self.assertFalse(F.cap_ok(("i", 18), px(bar + ring), W, H))           # ㅎ without its cap
        self.assertTrue(F.cap_ok(("i", 0), px(cap), W, H))                    # not a capped jamo

    def test_completeness_and_split(self):
        px = lambda pts: sum(1 << (y * W + x) for x, y in pts)
        kk_merged = px([(x, 2) for x in range(5)] + [(1, 3), (1, 4), (4, 3), (4, 4)])     # ㄲ: bars run together
        self.assertFalse(F.complete_ok(("i", 1), kk_merged, W, H))
        fixed = F.split_double(("i", 1), kk_merged, W, H)
        self.assertIsNotNone(fixed)
        self.assertTrue(F.complete_ok(("i", 1), fixed, W, H))
        self.assertEqual(kk_merged & ~fixed, 1 << (2 * W + 2))                              # one pixel cut
        k_one_bar = px([(x, 2) for x in range(5)] + [(4, 3), (4, 4)])                       # ㅋ without its middle bar
        self.assertFalse(F.complete_ok(("i", 15), k_one_bar, W, H))
        self.assertTrue(F.complete_ok(("m", 0), 0, W, H))                                    # vowels: other gates

    def test_leak_masks(self):
        lib, own = F.decompose_strike(self.st)
        masks = F.leak_masks(own, W, H)
        allowed, who = masks[("i", 3, 0, 0)]
        self.assertEqual(jamo("i", 3) & ~allowed, 0)          # the jamo's own pixels are never leaks
        self.assertTrue(who)                                   # the vowel's column is someone else's
        self.assertTrue(all(k2 == "m" for k2, _ in who.values()))

    def test_medial_gates(self):
        f = self.fill("111")
        old = F.MEDIAL_PENALTY
        try:
            F.MEDIAL_PENALTY = 30
            # ㅗ (8) and ㅡ (18) drawn the same: every ㅗ/ㅡ pair collapses, and ㅗ has no tick
            uo = f.slot_unit[("m", 0, 8)]
            ue = f.slot_unit[("m", 0, 18)]
            f.bmp[uo] = f.bmp[ue]
            s = 8 * 28                                           # 고-like syllable: ㄱ, ㅗ, no final
            self.assertGreaterEqual(f.medial_violations(s), 2)
            rep = F.judge(f)
            self.assertGreater(rep["medial_violations"], 0)
            self.assertGreater(rep["medial_pairs"][F.MED[8] + F.MED[18]]["violations"], 0)
        finally:
            F.MEDIAL_PENALTY = old

    def test_cli_fill(self):
        out = os.path.join(self.tmp.name, "C.SVF")
        rep = os.path.join(self.tmp.name, "C.json")
        r = subprocess.run([sys.executable, os.path.join(HERE, "jamofill.py"), "fill", "--strike", self.strike,
                            "--skeleton", "621", "--budget", "8192", "-o", out, "--report", rep],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        f = J.parse_svfn(open(out, "rb").read())
        self.assertIsNotNone(f.jset)
        self.assertEqual(J.unpack(f.jset).lc, 1)


if __name__ == "__main__":
    unittest.main()
