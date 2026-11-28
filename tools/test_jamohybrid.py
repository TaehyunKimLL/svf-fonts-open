#!/usr/bin/env python3
"""Tests of jamonet.py (numpy forward pass) and jamohybrid.py (the learned split builder). Synthetic data and the
repository's open faces only. numpy is needed (found on sys.path or in $JAMOSET_PYLIB); the tests skip without it."""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
for _d in os.environ.get("JAMOSET_PYLIB", "").split(os.pathsep):
    if _d and _d not in sys.path:
        sys.path.append(_d)
try:
    import numpy as np
except ImportError:
    np = None
import jamoset as J  # noqa: E402

MODEL = os.path.join(HERE, "models", "jamohybrid-v1.npz")
FILL = os.path.join(HERE, "models", "jamofill-v1.npz")
PARITY = os.path.join(HERE, "testdata", "jamofill-parity.json")
SANS = os.path.join(ROOT, "svf", "iolo", "SANS8J.SVF")


def tiny_model(path, base=4, cdim=3, seed=0):
    """A random jamonet-1 weights file (base 4) in the export format."""
    rng = np.random.default_rng(seed)
    sd = {}
    chans = {"e1": (1 + cdim, base), "e2": (base, 2 * base), "e3": (2 * base, 4 * base), "b": (4 * base, 8 * base),
             "d3": (8 * base, 4 * base), "d2": (4 * base, 2 * base), "d1": (2 * base, base)}
    for name, (cin, cout) in chans.items():
        sd[f"{name}.0.w"] = rng.normal(0, 0.3, (cout, cin, 3, 3))
        sd[f"{name}.0.b"] = rng.normal(0, 0.1, cout)
        sd[f"{name}.1.w"] = rng.normal(0, 0.3, (cout, cout, 3, 3))
        sd[f"{name}.1.b"] = rng.normal(0, 0.1, cout)
    for name, (cin, cout) in {"u3": (8 * base, 4 * base), "u2": (4 * base, 2 * base), "u1": (2 * base, base)}.items():
        sd[f"{name}.w"] = rng.normal(0, 0.3, (cin, cout, 2, 2))
        sd[f"{name}.b"] = rng.normal(0, 0.1, cout)
    sd["out.w"] = rng.normal(0, 0.3, (3, base, 1, 1))
    sd["out.b"] = rng.normal(0, 0.1, 3)
    for name, n in (("eL", 19), ("eV", 21), ("eT", 28)):
        sd[name] = rng.normal(0, 0.3, (n, cdim))
    sd["bott.w"] = rng.normal(0, 0.3, (8 * base, cdim))
    sd["bott.b"] = rng.normal(0, 0.1, 8 * base)
    meta = dict(format="jamonet-1", base=base, cdim=cdim, cond=True, canvas=32)
    np.savez_compressed(path, meta=np.array(json.dumps(meta)), **{k: v.astype(np.float16) for k, v in sd.items()})


@unittest.skipIf(np is None, "numpy not available")
class TestLayers(unittest.TestCase):
    def setUp(self):
        import jamonet
        jamonet._np()
        self.M = jamonet.Model

    def test_conv3_matches_loops(self):
        rng = np.random.default_rng(1)
        x = rng.normal(size=(2, 3, 5, 6)).astype(np.float32)
        w = rng.normal(size=(4, 3, 3, 3)).astype(np.float32)
        b = rng.normal(size=4).astype(np.float32)
        y = self.M.conv3(x, w, b)
        xp = np.pad(x, ((0, 0), (0, 0), (1, 1), (1, 1)))
        ref = np.zeros((2, 4, 5, 6), np.float32)
        for n in range(2):
            for o in range(4):
                for i in range(5):
                    for j in range(6):
                        ref[n, o, i, j] = (xp[n, :, i:i + 3, j:j + 3] * w[o]).sum() + b[o]
        self.assertTrue(np.allclose(y, ref, atol=1e-4))

    def test_pool_and_up(self):
        rng = np.random.default_rng(2)
        x = rng.normal(size=(1, 2, 4, 4)).astype(np.float32)
        p = self.M.pool(x)
        self.assertEqual(p.shape, (1, 2, 2, 2))
        self.assertEqual(p[0, 1, 1, 0], x[0, 1, 2:4, 0:2].max())
        w = rng.normal(size=(2, 3, 2, 2)).astype(np.float32)
        b = rng.normal(size=3).astype(np.float32)
        u = self.M.up(p, w, b)
        self.assertEqual(u.shape, (1, 3, 4, 4))
        ref = (p[0, :, 1, 0][:, None] * w[:, :, 1, 1]).sum(0) + b
        self.assertTrue(np.allclose(u[0, :, 3, 1], ref, atol=1e-5))


@unittest.skipIf(np is None, "numpy not available")
class TestForward(unittest.TestCase):
    def test_tiny_model_shapes_and_determinism(self):
        import jamonet
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tiny.npz")
            tiny_model(path)
            m = jamonet.Model(path)
            rng = np.random.default_rng(3)
            pre = (rng.random((5, 12, 12)) > 0.6).astype(np.uint8)
            jamo = np.array([[0, 0, 0], [3, 8, 4], [18, 20, 27], [9, 13, 0], [11, 1, 8]])
            p1, q1 = jamonet.predict(m, pre, jamo)
            p2, _ = jamonet.predict(m, pre, jamo)
            self.assertEqual(p1.shape, (5, 3, 12, 12))
            self.assertTrue((p1 == p2).all())
            self.assertTrue(((q1.max(axis=1) > 0) == (pre > 0)).all())    # every ink pixel gets a slot, nothing else
            self.assertEqual(int(q1[[0, 3], 2].sum()), 0)                   # no final plane without a final
            self.assertEqual(float(p1[[0, 3], 2].max()), 0.0)

    def test_weights_validated(self):
        import jamonet
        with tempfile.TemporaryDirectory() as d:
            good = os.path.join(d, "tiny.npz")
            tiny_model(good)
            with np.load(good) as z:
                arrays = {k: z[k] for k in z.files}
            for name, change in (("missing", lambda a: a.pop("out.b")),
                                 ("shape", lambda a: a.__setitem__("e1.0.w", np.zeros((5, 4, 3, 3), np.float16))),
                                 ("dtype", lambda a: a.__setitem__("e1.0.b", np.zeros(4, np.int32)))):
                bad = dict(arrays)
                change(bad)
                path = os.path.join(d, name + ".npz")
                np.savez(path, **bad)
                with self.assertRaises(ValueError, msg=name):
                    jamonet.Model(path)

    def test_canvas_geometry(self):
        import jamonet
        self.assertEqual(jamonet.canvas_geometry(12, 12), (2, 32, 4, 4))
        self.assertEqual(jamonet.canvas_geometry(10, 10), (3, 32, 1, 1))
        self.assertEqual(jamonet.canvas_geometry(54, 46)[1], 56)


@unittest.skipIf(np is None, "numpy not available")
class TestChecks(unittest.TestCase):
    def setUp(self):
        import jamohybrid as JH
        JH.np = np
        self.JH = JH

    def test_holes(self):
        holes = self.JH.holes
        bar = np.ones((1, 5), np.uint8)
        ring = np.ones((4, 4), np.uint8)
        ring[1:3, 1:3] = 0
        giyeok = np.array([[1, 1, 1], [0, 0, 1], [0, 0, 1]], np.uint8)
        dot = np.ones((1, 1), np.uint8)
        two = np.ones((5, 4), np.uint8)
        two[1, 1:3] = two[3, 1:3] = 0
        self.assertEqual([holes(bar), holes(ring), holes(giyeok), holes(dot), holes(two)], [0, 1, 0, 0, 2])

    def test_hole_checks(self):
        ring = np.zeros((8, 8), np.uint8)
        ring[1:7, 1:7] = 1
        ring[3:5, 3:5] = 0
        self.assertTrue(self.JH.check("ㅁ", 0, ring, 0)["holes"])
        self.assertFalse(self.JH.check("ㄱ", 0, ring, 0)["holes"])
        giyeok = np.zeros((8, 8), np.uint8)
        giyeok[1, 1:6] = 1
        giyeok[1:7, 5] = 1
        self.assertTrue(self.JH.check("ㄱ", 0, giyeok, 0)["holes"])

    def test_ticks_with_serif(self):
        a = np.zeros((10, 4), np.uint8)
        a[:, 1] = 1                 # ㅏ: the main vertical
        a[5, 2:4] = 1               # its tick to the right
        self.assertTrue(self.JH.check("ㅏ", 1, a, 0)["ticks"])
        a[0, 0] = 1                 # a serif hook at the top left
        self.assertFalse(self.JH.check("ㅏ", 1, a, 0)["ticks"])
        self.assertTrue(self.JH.check("ㅏ", 1, a, 0.2)["ticks"])
        a[5, 2:4] = 0               # the tick gone: caught with the serif tolerance too
        self.assertFalse(self.JH.check("ㅏ", 1, a, 0.2)["ticks"])


@unittest.skipIf(np is None, "numpy not available")
class TestChoice(unittest.TestCase):
    def test_choose_point(self):
        import jamohybrid as JH
        pts = [dict(bytes=10000, comp_iou=0.90), dict(bytes=14000, comp_iou=0.93), dict(bytes=18000, comp_iou=0.95)]
        self.assertEqual(JH.choose_point(pts, max_bytes=15000)[0], 1)
        self.assertEqual(JH.choose_point(pts, max_bytes=5000)[0], 0)
        self.assertEqual(JH.choose_point(pts, min_iou=0.92)[0], 1)
        self.assertEqual(JH.choose_point(pts, min_iou=0.99)[0], 2)

    def test_limits_checked(self):
        import argparse
        import jamohybrid as JH
        ap = argparse.ArgumentParser()
        self.assertEqual(JH.parse_limits(ap, "24,22,12", False), (24, 22, 12))
        self.assertEqual(JH.parse_limits(ap, "8,4,4", False), (8, 4, 4))        # v2 has no structural floor
        self.assertEqual(JH.parse_limits(ap, "128,128,64", True), (128, 128, 64))
        for text, big in (("0,4,4", False), ("40,24,16", False), ("129,24,16", True), ("32,24", False), ("a,b,c", False)):
            with self.assertRaises(SystemExit, msg=text):
                with open(os.devnull, "w") as null:
                    old, sys.stderr = sys.stderr, null
                    try:
                        JH.parse_limits(ap, text, big)
                    finally:
                        sys.stderr = old

    def test_input_caps(self):
        import jamohybrid as JH
        JH.np = np
        with tempfile.TemporaryDirectory() as d:
            junk = os.path.join(d, "junk.SVF")
            with open(junk, "wb") as fh:
                fh.write(b"\0" * 100)
            with self.assertRaises(SystemExit):
                JH.from_svf(junk)
            with self.assertRaises(SystemExit):           # a jamo-set face, not a precomposed one
                JH.from_svf(SANS)
            big = os.path.join(d, "big.SVF")             # a header claiming a 200 x 200 cell
            head = bytearray(b"\0" * 48)
            head[:4] = b"SVFN"
            import struct
            struct.pack_into("<H", head, 4, 3)
            head[14], head[15] = 200, 200
            with open(big, "wb") as fh:
                fh.write(bytes(head))
            with self.assertRaises(SystemExit) as cm:
                JH.from_svf(big)
            self.assertIn("larger than", str(cm.exception))

    def test_standard_limits_by_default(self):
        import jamohybrid as JH
        self.assertEqual(JH.LIMITS[False], ((32, 24, 16), (12, 12)))
        self.assertEqual(JH.LIMITS[True], ((64, 48, 32), (19, 28)))
        self.assertEqual(list(JH.TOL_LADDER), sorted(JH.TOL_LADDER, reverse=True))   # small faces first
        self.assertIn(1.0, JH.TOL_LADDER)                                            # the default face is on the ladder
        self.assertEqual(JH.default_tol(12), 1.0)
        self.assertEqual(JH.default_tol(24), 2.0)
        self.assertEqual(JH.CLASS_GRID[False][0], (12, 12))
        import argparse
        ap = argparse.ArgumentParser()
        self.assertEqual(JH.parse_classes(ap, "8,6", False), (8, 6))
        self.assertEqual(JH.parse_classes(ap, "19,28", True), (19, 28))
        self.assertEqual(JH.parse_classes(ap, "13,20", True), (13, 20))     # beyond the standard row with --big
        for text in ("13,12", "8", "8,1", "x,y"):
            with self.assertRaises(SystemExit, msg=text):
                with open(os.devnull, "w") as null:
                    old, sys.stderr = sys.stderr, null
                    try:
                        JH.parse_classes(ap, text, False)
                    finally:
                        sys.stderr = old


class FakeGates:
    """Gates that fail a piece with fewer than @p need ink pixels (a stand-in for the calibrated identity gates)."""

    def __init__(self, shape, need=0):
        self.shape, self.need = shape, need
        self.frac, self.off = 0.0, []

    def ok(self, k, name, piece):
        return int(piece.sum()) >= self.need


def synthetic(leads=range(19), vowels=(0, 8), tails=(0, 4), noise=None):
    """A 12 x 12 face with a known structure: the initial is a block whose place depends on the vowel (beside ㅏ, above
    ㅗ) and on having a final, plus a bit pattern of L; the medial a bar whose length depends on the final; the final
    a block with a bit pattern of T. Returns (syl, planes (N, 3, 12, 12))."""
    syl, planes = [], []
    for L in leads:
        for V in vowels:
            for T in tails:
                p = np.zeros((3, 12, 12), np.uint8)
                y0 = 0 if T else 2
                x0 = 1 if V == 0 else 3
                p[0, y0:y0 + 3, x0:x0 + 5] = 1
                for b in range(5):
                    p[0, y0 + 3, x0 + b] = (L >> b) & 1
                if V == 0:
                    p[1, 0:(7 if T else 11), 8] = 1
                    p[1, 3, 9] = 1
                else:
                    p[1, 6 if T else 9, 1:11] = 1
                    p[1, (5 if T else 8), 5] = 1
                if T:
                    p[2, 8:11, 2:9] = 1
                    for b in range(5):
                        p[2, 11, 2 + b] = (T >> b) & 1
                syl.append((L * 21 + V) * 28 + T)
                planes.append(p)
    planes = np.array(planes)
    if noise is not None:
        for i in noise:                              # one stray pixel of the initial in these syllables
            planes[i, 0, 5, 0] = 1
    return np.array(syl), planes


def synthetic_source(JH, syl, planes):
    src = JH.Source(syl, planes.max(axis=1), 10)
    src._pred = (planes.astype(np.float32), planes.copy())      # the proposals are the truth
    return src


@unittest.skipIf(np is None, "numpy not available")
class TestGrouping(unittest.TestCase):
    def setUp(self):
        import jamohybrid as JH
        JH.np = np
        self.JH = JH

    def test_ward(self):
        pts = np.array([0.0, 0.1, 0.2, 5.0, 5.1, 9.0])
        d2 = (pts[:, None] - pts[None, :]) ** 2
        self.assertEqual(self.JH.ward(d2, 3), [0, 0, 0, 1, 1, 2])
        self.assertEqual(self.JH.ward(d2, 6), [0, 1, 2, 3, 4, 5])
        self.assertEqual(self.JH.ward(d2, 1), [0] * 6)

    def test_classes(self):
        JH = self.JH
        lead, tail = JH.structural_classes()
        self.assertEqual((len(lead), max(lead) + 1, len(tail), max(tail) + 1), (19, 7, 28, 4))
        self.assertEqual(tail.count(0), 1)                       # no final is alone in its class
        syl, planes = synthetic()
        jamo = np.array([JH.lvt(int(s)) for s in syl])
        dist = JH.axis_distances(jamo, planes)
        self.assertEqual([d.shape for d in dist], [(19, 19), (21, 21), (28, 28)])
        lead, tail = JH.derived_classes(dist, (12, 12))
        self.assertEqual((len(lead), len(tail), tail[0], tail.count(0)), (19, 28, 0, 1))
        self.assertLessEqual(max(lead) + 1, 12)
        self.assertLessEqual(max(tail) + 1, 12)

    def problems(self, syl, planes, lead=None, tail=None):
        JH = self.JH
        jamo = np.array([JH.lvt(int(s)) for s in syl])
        lead = lead or [0] * 19
        tail = tail or [0] + [1] * 27
        return JH.make_problems(jamo, planes.astype(np.float32), planes.max(axis=1), lead, tail), jamo

    def test_limits_hold_per_class_vowel_and_tail_class(self):
        """One problem per lead class (initial), per vowel (medial), per tail class (final); each merges down to its
        slot's limit on its own, so two vowels may both keep `limit` medial groups."""
        JH = self.JH
        syl, planes = synthetic()
        lead = [0] * 10 + [1] * 9
        probs, _ = self.problems(syl, planes, lead)
        self.assertEqual([p.slot for p in probs].count(0), 2)
        self.assertEqual([p.slot for p in probs].count(1), 21)
        self.assertEqual([p.slot for p in probs].count(2), 1)
        stats = __import__("collections").Counter()
        JH.group(probs, (2, 2, 1), 0, FakeGates((12, 12)), stats)
        med = [p for p in probs if p.slot == 1 and len(p.full)]
        self.assertEqual(len(med), 2)                            # ㅏ and ㅗ
        self.assertEqual([p.groups() for p in med], [2, 2])      # 2 medial groups each: 4 in the slot, limit 2
        for p in probs:
            if len(p.full):
                self.assertLessEqual(p.groups(), (2, 2, 1)[p.slot])

    def test_tolerance_merges_noise_only(self):
        """Contexts that differ by one stray pixel in one of ten syllables merge under the default tolerance and stay
        apart at 0; contexts with different designs stay apart under it."""
        JH = self.JH
        syl, planes = synthetic(tails=(0, 4, 8))                 # finals ㄴ and ㄹ: the same initial and medial design
        jamo = np.array([JH.lvt(int(s)) for s in syl])
        noisy = [i for i, (L, V, T) in enumerate(jamo) if T == 8 and V == 0 and L == 3]
        syl, planes = synthetic(tails=(0, 4, 8), noise=noisy)
        tail = [0] + [1 if T == 4 else 2 for T in range(1, 28)]
        for tol, want in ((0, 6), (1.0, 4)):
            probs, _ = self.problems(syl, planes, tail=tail)
            JH.group(probs, (32, 24, 16), tol, FakeGates((12, 12)), __import__("collections").Counter())
            init = next(p for p in probs if p.slot == 0)
            self.assertEqual(init.groups(), want, tol)           # (V, no final / ㄴ / ㄹ): 6 contexts, 4 designs

    def test_merge_that_breaks_a_gate_is_refused_unless_forced(self):
        JH = self.JH
        syl, planes = synthetic(leads=(0,), vowels=(8,), tails=(0, 4))
        # the two medial bars of ㅗ (row 9 without a final, row 6 with one): their majority has too little ink
        Counter = __import__("collections").Counter
        probs, _ = self.problems(syl, planes)
        med = next(p for p in probs if p.slot == 1 and len(p.full))
        stats = Counter()
        JH.group([med], (32, 24, 16), 100.0, FakeGates((12, 12), need=5), stats)
        self.assertEqual(med.groups(), 2)                        # any tolerance: the merge would break the gate
        self.assertGreaterEqual(stats["merge_refused_by_gate"], 1)
        stats = Counter()
        JH.group([med], (32, 1, 16), 0, FakeGates((12, 12), need=5), stats)
        self.assertEqual(med.groups(), 1)                        # the set limit is hard
        self.assertEqual(stats["merges_forced_through_a_gate"], 1)

    def test_face_from_true_proposals_is_exact(self):
        """The synthetic face is inside the structure: built from its own planes it composes every source syllable
        exactly, passes the jamoset check, and the stored groups stay within the limits."""
        JH = self.JH
        syl, planes = synthetic()
        src = synthetic_source(JH, syl, planes)
        out, layout, info = JH.build_face(src, None, "derived", (32, 24, 16), (12, 12), False, 1)
        self.assertEqual(info["comp_exact"], len(syl))
        self.assertEqual(info["comp_iou"], 1.0)
        self.assertIn("composed 11172 syllables", J.check(out, layout, None))
        self.assertTrue(all(a <= b for a, b in zip(info["sets"], (32, 24, 16))))
        self.assertLessEqual(info["classes"][0], 12)
        self.assertLessEqual(info["classes"][1], 12)
        # tighter limits still build a valid face, less exact
        out2, layout2, info2 = JH.build_face(src, None, "structural", (1, 1, 1), (12, 12), False, 1)
        self.assertEqual(info2["sets"], [1, 1, 1])
        self.assertLess(info2["comp_iou"], 1.0)
        self.assertIn("composed 11172 syllables", J.check(out2, layout2, None))

    def test_contexts_without_syllables(self):
        """A source with holes, as a KS-only face has: the syllables of ㅏ with a final are missing for half the
        initials. The face still composes all 11,172; the missing syllables are drawn with pieces of their own jamo
        borrowed from the nearest group (the design of the missing context itself cannot be known)."""
        JH = self.JH
        syl, planes = synthetic()
        jamo = np.array([JH.lvt(int(s)) for s in syl])
        keep = ~((jamo[:, 1] == 0) & (jamo[:, 2] == 4) & (jamo[:, 0] % 2 == 1))
        for rule in ("structural", "derived"):
            src = synthetic_source(JH, syl[keep], planes[keep])
            out, layout, info = JH.build_face(src, None, rule, (32, 24, 16), (12, 12), False, 1)
            self.assertEqual(info["comp_iou"], 1.0, rule)
            self.assertIn("composed 11172 syllables", J.check(out, layout, None))
            st = info["stats"]
            self.assertGreater(st.get("pieces_borrowed", 0) + st.get("contexts_without_syllables", 0), 0, rule)
            f = J.parse_svfn(out)
            t = J.unpack(f.jset)
            for i in np.nonzero(~keep)[0]:
                c = J.compose(f, t, 0xAC00 + int(syl[i]))
                a = np.unpackbits(np.frombuffer(bytes(c), np.uint8).reshape(12, 2), axis=1)[:, :12].astype(bool)
                b = planes[i].max(axis=0).astype(bool)
                self.assertGreater((a & b).sum() / (a | b).sum(), 0.4, (rule, int(syl[i])))
                nums = J.pieces_of(t, 0xAC00 + int(syl[i]))
                self.assertNotIn(J.BLANK, nums)                  # initial, medial and final are all drawn
                # the initial piece is one this initial has in the source (its bit row identifies it)
                g = f.glyphs[J.PIECE_BASE + nums[0]]
                own = {planes[k, 0].tobytes() for k in np.nonzero(keep & (jamo[:, 0] == jamo[i, 0]))[0]}
                bits = np.unpackbits(np.frombuffer(bytes(g), np.uint8).reshape(12, 2), axis=1)[:, :12]
                self.assertIn(bits.astype(np.uint8).tobytes(), own, (rule, int(syl[i])))

    def test_missing_context_is_placed_as_the_sibling_classes_group_it(self):
        """Finals ㄴ and ㄹ share every design here but sit in two tail classes. One lead class has no syllable of ㅏ with
        ㄹ: the other lead class groups (ㅏ, ㄹ) with (ㅏ, ㄴ), so the missing context joins that group and the missing
        syllables compose exactly."""
        JH = self.JH
        Counter = __import__("collections").Counter
        syl, planes = synthetic(tails=(0, 4, 8))
        jamo = np.array([JH.lvt(int(s)) for s in syl])
        lead = [0] * 10 + [1] * 9
        tail = [0] + [1 if T == 4 else 2 for T in range(1, 28)]
        keep = ~((jamo[:, 0] >= 10) & (jamo[:, 1] == 0) & (jamo[:, 2] == 8))
        probs = JH.make_problems(jamo[keep], planes[keep].astype(np.float32), planes[keep].max(axis=1), lead, tail)
        gates, stats = FakeGates((12, 12)), Counter()
        JH.group(probs, (32, 24, 16), 1.0, gates, stats)
        dist = JH.axis_distances(jamo[keep], planes[keep])
        piece, users, group_of, borrowed = JH.pieces_of_groups(probs, planes[keep], gates, dist, lead, tail, stats)
        self.assertGreater(stats["contexts_placed_by_siblings"], 0)
        g1 = group_of[(0, 1)]                                    # the initial groups of the lead class with the hole
        self.assertEqual(g1[(0, 2)], g1[(0, 1)])                 # (ㅏ, ㄹ) with (ㅏ, ㄴ)
        self.assertNotEqual(g1[(0, 2)], g1[(0, 0)])              # not with (ㅏ, no final)
        self.assertNotEqual(g1[(0, 2)], g1[(8, 2)])              # nor with (ㅗ, ㄹ)
        for i in np.nonzero(~keep)[0]:
            L, V, T = (int(x) for x in jamo[i])
            c, t = lead[L], tail[T]
            got = [piece[borrowed.get(k, k)] for k in ((0, c, group_of[(0, c)][(V, t)], L),
                                                       (1, V, group_of[(1, V)][(c, t)], V),
                                                       (2, t, group_of[(2, t)][(c, V)], T))]
            self.assertTrue((np.array(got) == planes[i]).all(), (L, V, T))

    def test_default_keeps_the_smallest_class_cap_within_the_slack(self):
        JH = self.JH
        syl, planes = synthetic()
        src = synthetic_source(JH, syl, planes)
        out, layout, info = JH.build_default(src, None, "derived", (32, 24, 16), False, 1)
        tried = info["choice"]["tried"]
        self.assertEqual([tuple(t["max_classes"]) for t in tried], list(JH.CLASS_GRID[False]))
        top = max(t["comp_iou"] for t in tried)
        ok = [t for t in tried if t["comp_iou"] >= top - JH.SLACK]
        self.assertEqual(info["bytes"], min(t["bytes"] for t in ok))
        self.assertIn("composed 11172 syllables", J.check(out, layout, None))
        fixed = JH.build_default(src, None, "derived", (32, 24, 16), False, 1, classes=(12, 12))[2]
        self.assertEqual(fixed["choice"]["rule"], "fixed limits")
        self.assertEqual(len(JH.build_default(src, None, "structural", (32, 24, 16), False, 1)[2]["choice"]["tried"]), 1)

    def test_ladder_and_ks_score(self):
        JH = self.JH
        syl, planes = synthetic(noise=range(0, 76, 7))
        src = synthetic_source(JH, syl, planes)
        out, layout, info = JH.build_ladder(src, None, "derived", False, 1, max_bytes=10 ** 9)
        lad = info["choice"]["ladder"]
        self.assertEqual(len(lad), len(JH.TOL_LADDER) * len(JH.CLASS_GRID[False]))
        sizes = [p["bytes"] for p in lad]
        for c in range(len(JH.CLASS_GRID[False])):               # within a class cap a smaller tolerance never
            part = sizes[c * len(JH.TOL_LADDER):(c + 1) * len(JH.TOL_LADDER)]     # gives a smaller face
            self.assertEqual(part, sorted(part))
        self.assertEqual(info["comp_iou"], max(p["comp_iou"] for p in info["choice"]["ladder"]))
        small = JH.build_ladder(src, None, "derived", False, 1, max_bytes=1)[2]
        self.assertEqual(small["bytes"], min(sizes))
        one = JH.build_ladder(src, None, "derived", False, 1, max_bytes=10 ** 9, classes=(6, 6))[2]
        self.assertEqual(len(one["choice"]["ladder"]), len(JH.TOL_LADDER))
        self.assertIn("comp_iou_ks", info)
        self.assertEqual(info["ks_syllables"], int(np.isin(syl, JH.ks_syllables()).sum()))
        self.assertEqual(src.__dict__.get("_prep"), {})          # cached problems are freed after each class cap

    def test_big_ladder_keeps_the_given_class_cap(self):
        """--big --classes LC,TC: the standard half of the ladder uses the cap too, clamped to the standard row."""
        JH = self.JH
        syl, planes = synthetic()
        src = synthetic_source(JH, syl, planes)
        info = JH.build_ladder(src, None, "derived", True, 1, max_bytes=10 ** 9, classes=(19, 6))[2]
        lad = info["choice"]["ladder"]
        self.assertEqual(len(lad), len(JH.TOL_LADDER) + len(JH.BIG_TOL_LADDER))
        self.assertEqual({tuple(p["max_classes"]) for p in lad if not p["big"]}, {(12, 6)})
        self.assertEqual({tuple(p["max_classes"]) for p in lad if p["big"]}, {(19, 6)})

    def test_big_face(self):
        JH = self.JH
        syl, planes = synthetic()
        src = synthetic_source(JH, syl, planes)
        out, layout, info = JH.build_face(src, None, "derived", (64, 48, 32), (19, 28), True, 1)
        self.assertTrue(info["big"])
        self.assertEqual(info["comp_exact"], len(syl))
        self.assertIn("composed 11172 syllables", J.check(out, layout, None))
        self.assertTrue(all(a <= b for a, b in zip(info["sets"], (64, 48, 32))))
        self.assertLessEqual(info["classes"][0], 19)
        self.assertLessEqual(info["classes"][1], 28)

    def test_blank_jamo_reported(self):
        """The synthetic face has only the vowels ㅏ ㅗ and the final ㄴ: the other 19 vowels and 26 finals have no
        piece and are reported; every initial has one."""
        JH = self.JH
        syl, planes = synthetic()
        src = synthetic_source(JH, syl, planes)
        info = JH.build_face(src, None, "derived", (32, 24, 16), (12, 12), False, 1)[2]
        blank = info["blank_jamo"]
        self.assertEqual(len([b for b in blank if b.startswith("medial ")]), 19)
        self.assertEqual(len([b for b in blank if b.startswith("final ")]), 26)
        self.assertEqual(len(blank), 45)
        self.assertIn("medial ㅐ", blank)
        self.assertNotIn("medial ㅏ", blank)
        self.assertNotIn("final ㄴ", blank)
        self.assertEqual(info["stats"]["pieces_blank"], 45)


@unittest.skipIf(np is None, "numpy not available")
class TestSparsePlacement(unittest.TestCase):
    """A source with holes (what a face of the 2,350 KS syllables is): a context no syllable shows is placed by where
    the slot's ink sits for that (vowel, final) pair, learned from the syllables the source does have."""

    def setUp(self):
        import jamohybrid as JH
        JH.np = np
        self.JH = JH

    def test_ink_box_and_additive_fit(self):
        JH = self.JH
        a = np.zeros((8, 9), np.uint8)
        a[1:4, 2:6] = 1
        self.assertEqual(list(JH.ink_box(a)), [1, 2, 3, 5])
        self.assertIsNone(JH.ink_box(np.zeros((4, 4), np.uint8)))
        obs = {(u, v): np.array([u, v, u + 2, v + 3], float) for u in range(3) for v in range(4)}
        m = JH.fit_boxes(obs, 3, 4)
        self.assertIsNotNone(m)
        mu, av, bv = m
        for (u, v), b in obs.items():
            self.assertTrue(np.allclose(mu + av[u] + bv[v], b), (u, v))
        # underdetermined: one cell, one observed level on an axis, or levels no cell links -> no model
        self.assertIsNone(JH.fit_boxes({(0, 0): obs[(0, 0)]}, 3, 4))
        self.assertIsNone(JH.fit_boxes({(0, 0): obs[(0, 0)], (0, 1): obs[(0, 1)]}, 3, 4))
        self.assertIsNone(JH.fit_boxes({(0, 0): obs[(0, 0)], (1, 1): obs[(1, 1)]}, 3, 4))
        self.assertIsNotNone(JH.fit_boxes({(0, 0): obs[(0, 0)], (0, 1): obs[(0, 1)], (1, 0): obs[(1, 0)]}, 3, 4))

    def test_box_placement_breaks_ties_deterministically(self):
        """Equal distance: the group with more pieces wins, then the lower group index; dict order never decides."""
        JH = self.JH
        tail = [0] + [1] * 27
        model = (np.zeros(4), np.zeros((21, 4)), np.zeros((28, 4)))
        z = np.zeros(4)
        far = np.full(4, 5.0)
        self.assertEqual(JH.box_placement((0, 1), model, tail, {0: [far], 1: [z, z]}), 1)
        self.assertEqual(JH.box_placement((0, 1), model, tail, {3: [z], 2: [z]}), 2)
        self.assertIsNone(JH.box_placement((0, 1), model, tail, {0: []}))

    def test_box_model_is_none_when_unidentified(self):
        """A source with one vowel cannot separate the vowel from the final term: no model, and the face falls back to
        the sibling vote without placing anything by box."""
        JH = self.JH
        syl, planes = synthetic(vowels=(0,), tails=(0, 4))
        jamo = np.array([JH.lvt(int(s)) for s in syl])
        self.assertIsNone(JH.box_model(planes.astype(np.float32), jamo))
        src = synthetic_source(JH, syl, planes)
        info = JH.build_face(src, None, "derived", (32, 24, 16), (12, 12), False, 1)[2]
        self.assertEqual(info["stats"].get("contexts_placed_by_box", 0), 0)
        self.assertEqual(info["comp_iou"], 1.0)

    def test_box_model_predicts_a_missing_cell(self):
        """The initial's box for a (vowel, final) pair the source lacks is predicted from the pairs it has."""
        JH = self.JH
        syl, planes = synthetic(vowels=(0, 4, 8, 12), tails=(0, 4, 8))
        jamo = np.array([JH.lvt(int(s)) for s in syl])
        lead, tail = [0] * 19, [0] + [1 if T == 4 else 2 for T in range(1, 28)]
        keep = ~((jamo[:, 1] == 8) & (jamo[:, 2] == 8))
        model = JH.box_model(planes[keep].astype(np.float32), jamo[keep])
        self.assertIsNotNone(model)
        mu, av, bv = model
        held = np.nonzero((jamo[:, 1] == 8) & (jamo[:, 2] == 8))[0]
        for i in held:
            want = JH.ink_box(planes[i, 0])
            self.assertLessEqual(np.abs(mu + av[8] + bv[8] - want).sum(), 1.0, int(syl[i]))

    def test_sparse_source_places_by_the_box(self):
        """One (vowel, final) cell removed: its syllables compose exactly, and the report says the contexts were placed
        by the layout model."""
        JH = self.JH
        syl, planes = synthetic(vowels=(0, 4, 8, 12), tails=(0, 4, 8))
        jamo = np.array([JH.lvt(int(s)) for s in syl])
        keep = ~((jamo[:, 1] == 8) & (jamo[:, 2] == 8))
        src = synthetic_source(JH, syl[keep], planes[keep])
        out, layout, info = JH.build_face(src, None, "derived", (32, 24, 16), (12, 12), False, 1)
        self.assertEqual(info["comp_iou"], 1.0)
        st = info["stats"]
        self.assertGreater(st["contexts_placed_by_box"], 0)
        self.assertLessEqual(st["contexts_placed_by_box"] + st.get("contexts_placed_by_siblings", 0),
                             st["contexts_without_syllables"])
        self.assertIn("composed 11172 syllables", J.check(out, layout, None))
        f = J.parse_svfn(out)
        t = J.unpack(f.jset)
        for i in np.nonzero(~keep)[0]:
            c = J.compose(f, t, 0xAC00 + int(syl[i]))
            a = np.unpackbits(np.frombuffer(bytes(c), np.uint8).reshape(12, 2), axis=1)[:, :12].astype(bool)
            b = planes[i].max(axis=0).astype(bool)
            self.assertEqual((a != b).sum(), 0, int(syl[i]))

    def test_box_placement_leaves_a_shown_context_alone(self):
        """Every context the source shows keeps its evidence group: the box model only fills contexts that have none,
        and it never exceeds them."""
        JH = self.JH
        syl, planes = synthetic(vowels=(0, 4, 8), tails=(0, 4))
        src = synthetic_source(JH, syl, planes)
        info = JH.build_face(src, None, "derived", (32, 24, 16), (12, 12), False, 1)[2]
        st = info["stats"]
        self.assertLessEqual(st.get("contexts_placed_by_box", 0), st["contexts_without_syllables"])
        self.assertEqual(info["comp_iou"], 1.0)


def tiny_fill_model(path, seed=0):
    """A random jamofill-1 weights file in the shipped format (60-64-64-1 float32)."""
    rng = np.random.default_rng(seed)
    sd = {"mu": rng.normal(0, 0.2, 60), "sd": np.full(60, 1.5), "med": rng.normal(0, 0.1, 60),
          "W0": rng.normal(0, 0.2, (60, 64)), "b0": rng.normal(0, 0.1, 64),
          "W1": rng.normal(0, 0.2, (64, 64)), "b1": rng.normal(0, 0.1, 64),
          "W2": rng.normal(0, 0.2, (64, 1)), "b2": rng.normal(0, 0.1, 1)}
    meta = dict(format="jamofill-1", features=60, hidden=[64, 64])
    np.savez(path, meta=np.array(json.dumps(meta)), **{k: v.astype(np.float32) for k, v in sd.items()})


@unittest.skipIf(np is None, "numpy not available")
class TestFillRanker(unittest.TestCase):
    """The --fill cross-font group ranker: weight loading, the 60 features (against the research code's fixture), the
    choice, the fallback, and the promise that only unseen contexts change."""

    def setUp(self):
        import jamohybrid as JH
        JH.np = np
        self.JH = JH

    def face(self, full=False):
        """The synthetic face of the parity fixture, or one with every context shown (all 21 vowels, a final of each
        structural tail class: 19 x 21 x 4 syllables, no unseen context)."""
        JH = self.JH
        if full:
            syl, planes = synthetic(vowels=range(21), tails=(0, 4, 8, 12))
            return synthetic_source(JH, syl, planes)
        syl, planes = synthetic(vowels=(0, 4, 8, 12), tails=(0, 4, 8))
        jamo = np.array([JH.lvt(int(s)) for s in syl])
        keep = (jamo[:, 1] != 12) & ~((jamo[:, 1] == 8) & (jamo[:, 2] == 8))
        return synthetic_source(JH, syl[keep], planes[keep])

    def grouped(self, full=False):
        JH = self.JH
        P = JH.prepare(self.face(full), None, "derived", (12, 12))
        JH.group(P["problems"], (32, 24, 16), 0.0 if not full else None, P["gates"], JH.Counter(), True)
        return P

    def test_weights_validated(self):
        JH = self.JH
        with tempfile.TemporaryDirectory() as d:
            good = os.path.join(d, "good.npz")
            tiny_fill_model(good)
            m = JH.FillModel(good)
            self.assertEqual(m.params, 8309)
            self.assertEqual(m.score(np.zeros((3, 60), np.float32)).shape, (3,))
            with np.load(good, allow_pickle=False) as z:
                arrays = {k: z[k] for k in z.files}
            for name, change in (
                    ("missing", lambda a: a.pop("W2")),
                    ("shape", lambda a: a.__setitem__("W0", np.zeros((59, 64), np.float32))),
                    ("dtype", lambda a: a.__setitem__("b0", np.zeros(64, np.int32))),
                    ("meta", lambda a: a.__setitem__("meta", np.array('{"format": "other"}')))):
                bad = dict(arrays)
                change(bad)
                path = os.path.join(d, name + ".npz")
                np.savez(path, **bad)
                with self.assertRaises(ValueError, msg=name):
                    JH.FillModel(path)
            big = os.path.join(d, "big.npz")
            with open(big, "wb") as fh:
                fh.truncate(JH.MAX_FILL_FILE + 1)
            with self.assertRaises(ValueError):
                JH.FillModel(big)

    def test_shipped_weights(self):
        if not os.path.exists(FILL):
            self.skipTest("no shipped fill weights")
        m = self.JH.FillModel(FILL)
        self.assertEqual(m.meta.get("format"), "jamofill-1")
        self.assertEqual(m.params, 8309)
        self.assertLessEqual(os.path.getsize(FILL), self.JH.MAX_FILL_FILE)

    def test_features_match_the_research_fixture(self):
        """The 60 numbers per (context, candidate) equal the research fill.Feats rows; the fixture holds rows and keys
        only, no glyph bitmap."""
        JH = self.JH
        if not os.path.exists(PARITY):
            self.skipTest("no parity fixture")
        with open(PARITY, encoding="utf-8") as fh:
            fixture = json.load(fh)
        P = self.grouped()
        F = JH.FillFeatures(P, P["prop"])

        class Recorder:
            def __init__(self):
                self.rows = {}

            def features(self):
                return F

            def choose(self, p, c, cands):
                if len(cands) >= 2:
                    for o in cands:
                        self.rows[(int(p.slot), int(c[0]), int(c[1]), int(o["g"]))] = F.row(p, c, o)
                return None

        rec = Recorder()
        JH.pieces_of_groups(P["problems"], P["prop"], P["gates"], P["dist"], P["lead"], P["tail"], JH.Counter(),
                            P["boxes"], rec)
        self.assertEqual(fixture["features"], 60)
        self.assertEqual({k[0] for k in fixture["keys"]}, {0, 1, 2})
        for key, row in zip(fixture["keys"], fixture["rows"]):
            k = tuple(key)
            self.assertIn(k, rec.rows, k)
            np.testing.assert_allclose(rec.rows[k], np.array(row), rtol=0, atol=1e-6, err_msg=str(k))

    def test_choice_and_fallback(self):
        """The best score wins; fewer than two candidates, an unusable model or an invalid group falls back to the
        baseline order, unchanged."""
        JH = self.JH
        P = self.grouped()

        class Last:
            def score(self, X):
                return np.arange(len(X), dtype=float)

        class F:
            def row(self, p, c, o):
                return [0.0] * 60

        fill = JH.Fill(Last(), P, P["prop"])
        fill._F = F()
        cands = [{"g": 2}, {"g": 5}, {"g": 3}]
        self.assertEqual(fill.choose(None, None, cands), 3)
        self.assertIsNone(fill.choose(None, None, cands[:1]))

        base = JH.pieces_of_groups(P["problems"], P["prop"], P["gates"], P["dist"], P["lead"], P["tail"],
                                   JH.Counter(), P["boxes"])[2]

        class Bad:
            def features(self):
                return JH.FillFeatures(P, P["prop"])

            def choose(self, p, c, cands):
                return 999

        stats = JH.Counter()
        bad = JH.pieces_of_groups(P["problems"], P["prop"], P["gates"], P["dist"], P["lead"], P["tail"], stats,
                                  P["boxes"], Bad())[2]
        self.assertEqual(bad, base)
        self.assertEqual(stats.get("contexts_placed_by_fill", 0), 0)

        class First:
            def features(self):
                return JH.FillFeatures(P, P["prop"])

            def choose(self, p, c, cands):
                return cands[0]["g"] if cands else None

        stats = JH.Counter()
        first = JH.pieces_of_groups(P["problems"], P["prop"], P["gates"], P["dist"], P["lead"], P["tail"], stats,
                                    P["boxes"], First())[2]
        self.assertGreater(stats["contexts_placed_by_fill"], 0)
        self.assertNotEqual(first, base)                       # at least one unseen context moved

    def test_bytes_ks_and_gates_unchanged(self):
        """A KS-only face with and without --fill: same bytes, sets, pieces and gates; every source syllable composes
        to the same bitmap; only unseen contexts changed."""
        JH = self.JH
        if not os.path.exists(FILL):
            self.skipTest("no shipped fill weights")
        src = self.face()
        off, _, info0 = JH.build_face(src, None, "derived", (32, 24, 16), (12, 12), False, 1, fill=None)
        on, _, info1 = JH.build_face(src, None, "derived", (32, 24, 16), (12, 12), False, 1,
                                     fill=JH.FillModel(FILL))
        self.assertEqual(len(on), len(off))
        for k in ("sets", "pieces", "gates_failing", "comp_iou"):
            self.assertEqual(info1[k], info0[k], k)
        self.assertGreater(info1["fill"]["contexts_placed_by_fill"], 0)
        f0, t0 = J.parse_svfn(off), J.unpack(J.parse_svfn(off).jset)
        f1, t1 = J.parse_svfn(on), J.unpack(J.parse_svfn(on).jset)
        for s in src.syl:
            self.assertEqual(J.compose(f0, t0, 0xAC00 + int(s)), J.compose(f1, t1, 0xAC00 + int(s)), int(s))

    def test_all_syllable_build_is_byte_identical(self):
        """Every context shown: the fill has nothing to decide and the face is bit-identical."""
        JH = self.JH
        if not os.path.exists(FILL):
            self.skipTest("no shipped fill weights")
        src = self.face(full=True)
        off, _, _ = JH.build_face(src, None, "structural", (32, 24, 16), (12, 12), False, 1, fill=None)
        on, _, info = JH.build_face(src, None, "structural", (32, 24, 16), (12, 12), False, 1,
                                    fill=JH.FillModel(FILL))
        self.assertEqual(on, off)
        self.assertEqual(info["fill"]["contexts_placed_by_fill"], 0)


@unittest.skipIf(np is None, "numpy not available")
class TestUsage(unittest.TestCase):
    """Usage errors of the new options exit before any file is read."""

    def run_main(self, *args):
        import jamohybrid as JH
        with open(os.devnull, "w") as null:
            old, sys.stderr = sys.stderr, null
            try:
                with self.assertRaises(SystemExit) as cm:
                    JH.main(["--from-svf", "missing.SVF", "-o", os.devnull, *args])
            finally:
                sys.stderr = old
        self.assertEqual(cm.exception.code, 2, args)

    def test_usage_errors(self):
        self.run_main("--tol", "-1")
        self.run_main("--tol", "1000")
        self.run_main("--tol", "1", "--max-bytes", "30000")
        self.run_main("--tol", "1", "--min-iou", "0.9")
        self.run_main("--classes", "13,12")                     # above the standard row
        self.run_main("--classes", "20,12", "--big")            # above the BIG row
        self.run_main("--classes", "8", "--big")
        self.run_main("--classes", "8,8", "--rule", "structural")
        self.run_main("--fill", "/nonexistent/jamofill.npz")    # the weights are checked before the source is read


@unittest.skipIf(np is None or not os.path.exists(MODEL), "numpy or the shipped weights not available")
class TestEndToEnd(unittest.TestCase):
    def test_sans8j_subset(self):
        """300 KS syllables composed from SANS8J's own pieces, split again: the face builds, composes all 11,172, and
        the model puts the pixels in SANS8J's slots (a smoke threshold: SANS8J is in the training data)."""
        import jamohybrid as JH
        import jamonet
        JH.np = np
        with open(SANS, "rb") as fh:
            f = J.parse_svfn(fh.read())
        t = J.unpack(f.jset)
        w, h = f.cell_w, f.cell_h
        nb = (w + 7) // 8
        ks = [ord(bytes([0xB0 + i // 94, 0xA1 + i % 94]).decode("euc_kr")) - 0xAC00 for i in range(0, 2350, 8)][:300]
        planes = np.zeros((len(ks), 3, h, w), np.uint8)
        for i, s in enumerate(ks):
            for k, p in enumerate(J.pieces_of(t, 0xAC00 + s)):
                if p != J.BLANK:
                    g = f.glyphs[J.PIECE_BASE + p]
                    for y in range(h):
                        v = int.from_bytes(g[y * nb:(y + 1) * nb], "big") >> (nb * 8 - w)
                        planes[i, k, y] = [(v >> (w - 1 - x)) & 1 for x in range(w)]
        pre = planes.max(axis=1)
        src = JH.Source(np.array(ks), pre, 12)
        model = jamonet.Model(MODEL)
        out, layout, info = JH.build_face(src, model, "derived", (16, 21, 8), (12, 12), False, 1)
        self.assertIn("composed 11172 syllables", J.check(out, layout, None))
        prob, prop = src._pred
        ink = pre.astype(bool)
        acc = ((prop.astype(bool) == planes.astype(bool)).all(axis=1) & ink).sum() / ink.sum()
        self.assertGreaterEqual(acc, 0.9)
        self.assertGreater(info["comp_iou"], 0.9)


class TestProvenance(unittest.TestCase):
    def test_weights_listed(self):
        if not os.path.exists(MODEL):
            self.skipTest("no shipped weights")
        import hashlib
        with open(MODEL, "rb") as fh:
            sha = hashlib.sha256(fh.read()).hexdigest()
        with open(os.path.join(HERE, "models", "jamohybrid-v1.md"), encoding="utf-8") as fh:
            self.assertIn(sha, fh.read())
        for notice in ("NOTICE.md", "NOTICE.ko.md"):
            with open(os.path.join(ROOT, notice), encoding="utf-8") as fh:
                self.assertIn("tools/models/jamohybrid-v1.npz", fh.read())

    def test_fill_weights_listed(self):
        if not os.path.exists(FILL):
            self.skipTest("no shipped fill weights")
        import hashlib
        with open(FILL, "rb") as fh:
            sha = hashlib.sha256(fh.read()).hexdigest()
        with open(os.path.join(HERE, "models", "jamofill-v1.md"), encoding="utf-8") as fh:
            self.assertIn(sha, fh.read())
        for notice in ("NOTICE.md", "NOTICE.ko.md"):
            with open(os.path.join(ROOT, notice), encoding="utf-8") as fh:
                self.assertIn("tools/models/jamofill-v1.npz", fh.read())


if __name__ == "__main__":
    unittest.main()
