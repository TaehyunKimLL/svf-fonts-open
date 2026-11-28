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
        self.assertEqual(JH.parse_limits(ap, "128,128,64", True), (128, 128, 64))
        for text, big in (("8,4,4", False), ("40,24,16", False), ("129,24,16", True), ("32,24", False), ("a,b,c", False)):
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
        self.assertEqual(JH.LADDER[False][-1], (32, 24, 16))


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


if __name__ == "__main__":
    unittest.main()
