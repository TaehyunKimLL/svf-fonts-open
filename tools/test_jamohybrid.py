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

    def test_canvas_geometry(self):
        import jamonet
        self.assertEqual(jamonet.canvas_geometry(12, 12), (2, 32, 4, 4))
        self.assertEqual(jamonet.canvas_geometry(10, 10), (3, 32, 1, 1))
        self.assertEqual(jamonet.canvas_geometry(54, 46)[1], 56)


@unittest.skipIf(np is None, "numpy not available")
class TestChoice(unittest.TestCase):
    def test_choose_point(self):
        import jamohybrid as JH
        pts = [dict(bytes=10000, comp_iou=0.90), dict(bytes=14000, comp_iou=0.93), dict(bytes=18000, comp_iou=0.95)]
        self.assertEqual(JH.choose_point(pts, max_bytes=15000)[0], 1)
        self.assertEqual(JH.choose_point(pts, max_bytes=5000)[0], 0)
        self.assertEqual(JH.choose_point(pts, min_iou=0.92)[0], 1)
        self.assertEqual(JH.choose_point(pts, min_iou=0.99)[0], 2)

    def test_standard_limits_by_default(self):
        import jamohybrid as JH
        self.assertEqual(JH.LIMITS[False], ((32, 24, 16), (12, 12)))
        self.assertEqual(JH.LIMITS[True], ((64, 48, 32), (19, 28)))
        self.assertEqual(JH.LADDER[False][-1], (32, 24, 16))


@unittest.skipIf(np is None or not os.path.exists(MODEL), "numpy or the shipped weights not available")
class TestEndToEnd(unittest.TestCase):
    def test_sans8j_subset(self):
        """300 KS syllables composed from SANS8J's own pieces, split again: the face builds, composes all 11,172, and
        the model puts the pixels in SANS8J's slots (a smoke threshold: SANS8J is in the training data)."""
        import jamohybrid as JH
        import jamonet
        JH.np = np
        f = J.parse_svfn(open(SANS, "rb").read())
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
        sha = hashlib.sha256(open(MODEL, "rb").read()).hexdigest()
        notes = open(os.path.join(HERE, "models", "jamohybrid-v1.md"), encoding="utf-8").read()
        self.assertIn(sha, notes)
        for notice in ("NOTICE.md", "NOTICE.ko.md"):
            self.assertIn("tools/models/jamohybrid-v1.npz", open(os.path.join(ROOT, notice), encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
