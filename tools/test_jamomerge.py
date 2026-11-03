"""Tests of jamomerge.py on synthetic faces (no font data)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jamofill as F  # noqa: E402
import jamomerge as M  # noqa: E402

W = H = 12


def bm(cells):
    b = 0
    for x, y in cells:
        b |= 1 << (y * W + x)
    return b


def synthetic(skel="224"):
    """A 2x2-class face: initials top-left (varying by vowel shape), medials right, finals bottom; every jamo has
    two variants so ties, set and class merges all have something to do."""
    t = F.named_skeleton(skel)           # 224: 1 lead class, 2 tail classes, 2/2/4 sets; fine: 2 x 3 classes
    sb = {}
    for s in range(t.ni):
        for L in range(19):
            sb[("i", s, L)] = bm([(1 + (L % 3), 1 + s), (2, 2 + (L % 4)), (1, 3 + s % 2)])
    for s in range(t.nm):
        for V in range(21):
            sb[("m", s, V)] = bm([(8 + s, y) for y in range(1, 8)] + [(9, 2 + (V + s) % 5)])
    for s in range(t.nf):
        for T in range(1, 28):
            sb[("f", s, T)] = bm([(x, 10) for x in range(2, 9)] + [(2 + T % 6, 9 + s % 2)])
    fc = M.Face(W, H, 10, t.lead_class, t.tail_class, t.lc, t.tc, t.init_set, t.med_set, t.fin_set, sb, [])
    used = set()
    for x in range(M.NSYL):
        used.update(fc.slots(x))
    fc.sb = {k: v for k, v in sb.items() if k in used}
    return fc


class FaceTests(unittest.TestCase):
    def test_build_read_roundtrip(self):
        fc = synthetic()
        data = M.build(fc)
        self.assertEqual(M.verify(fc, data), [])
        with tempfile.NamedTemporaryFile(suffix=".SVF", delete=False) as f:
            f.write(data)
        try:
            back = M.read_face(f.name)
        finally:
            os.unlink(f.name)
        for s in range(0, M.NSYL, 7):
            self.assertEqual(back.comp(s), fc.comp(s))
        self.assertEqual(M.Sizer(W, H).size(back), len(M.build(back)))

    def test_normalize_keeps_compositions(self):
        fc = synthetic()
        before = [fc.comp(s) for s in range(M.NSYL)]
        M.normalize(fc)
        self.assertEqual([fc.comp(s) for s in range(M.NSYL)], before)

    def test_moves_compose_as_promised(self):
        fc = synthetic()
        M.normalize(fc)
        ref = M.Ref(W, H, [fc.comp(s) for s in range(M.NSYL)])
        st = M.State(fc, ref)
        sz = M.Sizer(W, H)
        moves = M.all_moves(st, sz)
        kinds = {m.kind for m in moves}
        self.assertTrue({"tie", "set"} <= kinds)
        for m in moves[:: max(1, len(moves) // 25)]:
            nf = m.fc.copy()
            M.normalize(nf)
            for s in range(M.NSYL):
                want = m.newtri.get(s, st.tri[s])
                self.assertEqual(nf.triple(s), want, (m.desc, s))
            self.assertEqual(M.verify(nf, M.build(nf)), [])

    def test_class_moves_compose_as_promised(self):
        fc = synthetic("fine")
        M.normalize(fc)
        ref = M.Ref(W, H, [fc.comp(s) for s in range(M.NSYL)])
        st = M.State(fc, ref)
        moves = M.class_moves(st, M.Sizer(W, H))
        self.assertTrue({"lead", "tail"} <= {m.kind for m in moves})
        for m in moves:
            nf = m.fc.copy()
            M.normalize(nf)
            for s in range(M.NSYL):
                self.assertEqual(nf.triple(s), m.newtri.get(s, st.tri[s]), (m.desc, s))

    def test_step_shrinks(self):
        fc = synthetic()
        M.normalize(fc)
        ref = M.Ref(W, H, [fc.comp(s) for s in range(M.NSYL)])
        st = M.State(fc, ref)
        sz = M.Sizer(W, H)
        s0 = sz.size(st.fc)
        best, _ = M.step(st, sz)
        self.assertIsNotNone(best)
        self.assertLess(sz.size(st.fc), s0)


class GateTests(unittest.TestCase):
    def setUp(self):
        a = bm([(1, y) for y in range(1, 6)])
        b = bm([(3, y) for y in range(1, 6)])
        self.ref = M.Ref(W, H, [a | b] * M.NSYL)
        self.a, self.b = a, b

    def test_leak_is_a_join(self):
        self.assertFalse(self.ref.leaks(0, self.a | self.b))
        self.assertTrue(self.ref.leaks(0, self.a | self.b | bm([(2, 3)])))

    def test_stroke_lost_and_shift(self):
        self.assertFalse(self.ref.stroke_lost(0, self.a | (self.b << 1)))      # shifted by one column: kept
        self.assertTrue(self.ref.stroke_lost(0, self.a))                        # a stem gone

    def test_tick_gate(self):
        s = 11 * 588 + 8 * 28            # 오: ㅗ has its tick above the bar
        bar = bm([(x, 6) for x in range(2, 10)])
        tick = bm([(5, 5)])
        ref = M.Ref(W, H, [bar | tick] * M.NSYL)
        _, ok = ref.local(s, (0, bar | tick, 0))
        _, covered = ref.local(s, (tick, bar | tick, 0))
        self.assertFalse(ok & M.G_TICK)
        self.assertTrue(covered & M.G_TICK)


if __name__ == "__main__":
    unittest.main()
