#!/usr/bin/env python3
"""jamonet.py - the per-pixel jamo split model of jamohybrid.py, as a numpy forward pass.

The model (docs/jamo-split.md, the learned split) reads a precomposed 1 bpp syllable and gives, per pixel, the
probability that the initial, the medial and the final own it (three sigmoid planes, so a joint pixel may belong to two).
The syllable's jamo (L, V, T) are known and condition it. It is a small U-Net: three 2 x 2 max-pool steps down, three
2 x 2 stride-2 transposed convolutions up with skip connections, two 3 x 3 convolutions + ReLU per level, BatchNorm folded
into the convolutions at export (tools/train_jamohybrid.py writes the weights; torch is needed only there).

Weights file (`.npz`, arrays fp16, computed in float32):
  meta              JSON: {"format": "jamonet-1", "base": B, "cdim": C, "cond": bool, "canvas": 32, ...}
  <block>.<i>.w/.b  3 x 3 convolutions (out, in, 3, 3) of blocks e1 e2 e3 b d3 d2 d1, i = 0, 1
  u3/u2/u1.w/.b     transposed convolutions (in, out, 2, 2)
  out.w/.b          1 x 1 output convolution (3, B, 1, 1)
  eL eV eT          embeddings (19 / 21 / 28, C); bott.w/.b the bottleneck projection (8B, C)

Inputs are placed on a canvas whose side is a multiple of 8: scaled by the largest whole factor k with k * cell <= 32
(12 px -> x2, 9 / 10 px -> x3, 24 px -> x1), centred; a cell larger than 32 is placed unscaled on the next multiple of 8.
Predictions are averaged back over each k x k block. Needs numpy only.
"""

import json
import os

np = None
MAX_FILE = 64 << 20          # a weights file larger than this is refused before loading
MAX_PARAMS = 20_000_000       # and one with more parameters


def expected_shapes(base, cdim, cond):
    """{array name: shape} of a jamonet-1 weights file (BatchNorm folded)."""
    cin = 1 + (cdim if cond else 0)
    out = {}
    for name, (i, o) in {"e1": (cin, base), "e2": (base, 2 * base), "e3": (2 * base, 4 * base), "b": (4 * base, 8 * base),
                         "d3": (8 * base, 4 * base), "d2": (4 * base, 2 * base), "d1": (2 * base, base)}.items():
        out[f"{name}.0.w"], out[f"{name}.0.b"] = (o, i, 3, 3), (o,)
        out[f"{name}.1.w"], out[f"{name}.1.b"] = (o, o, 3, 3), (o,)
    for name, (i, o) in {"u3": (8 * base, 4 * base), "u2": (4 * base, 2 * base), "u1": (2 * base, base)}.items():
        out[f"{name}.w"], out[f"{name}.b"] = (i, o, 2, 2), (o,)
    out["out.w"], out["out.b"] = (3, base, 1, 1), (3,)
    if cond:
        out["eL"], out["eV"], out["eT"] = (19, cdim), (21, cdim), (28, cdim)
        out["bott.w"], out["bott.b"] = (8 * base, cdim), (8 * base,)
    return out


def _np():
    global np
    if np is None:
        import numpy
        np = numpy
    return np


class Model:
    def __init__(self, path):
        n = _np()
        if os.path.getsize(path) > MAX_FILE:
            raise ValueError(f"{path}: larger than {MAX_FILE} bytes")
        with n.load(path, allow_pickle=False) as z:
            if "meta" not in z.files:
                raise ValueError(f"{path}: not a jamonet-1 weights file (no meta)")
            self.meta = json.loads(str(z["meta"]))
            if self.meta.get("format") != "jamonet-1":
                raise ValueError(f"{path}: not a jamonet-1 weights file")
            base, cdim = int(self.meta.get("base", 0)), int(self.meta.get("cdim", 0))
            self.cond = bool(self.meta.get("cond", True))
            if not (1 <= base <= 64 and 1 <= cdim <= 64):
                raise ValueError(f"{path}: base {base} / cdim {cdim} out of range")
            want = expected_shapes(base, cdim, self.cond)
            if set(z.files) - {"meta"} != set(want):
                raise ValueError(f"{path}: arrays {sorted(set(z.files) ^ (set(want) | {'meta'}))} missing or unexpected")
            total = 0
            self.p = {}
            for k, shape in want.items():
                a = z[k]
                if a.dtype.kind != "f" or a.shape != shape:
                    raise ValueError(f"{path}: {k} is {a.dtype} {a.shape}, want float {shape}")
                total += a.size
                self.p[k] = a.astype(n.float32)
            if total > MAX_PARAMS:
                raise ValueError(f"{path}: {total} parameters, more than {MAX_PARAMS}")
            self.params = total

    # ---- layers ----------------------------------------------------------------------------------------------------
    @staticmethod
    def conv3(x, w, b):
        """3 x 3 convolution, padding 1: x (N, C, H, W), w (O, C, 3, 3) -> (N, O, H, W); nine shifted matrix products."""
        n = np
        N, C, H, W = x.shape
        xp = n.zeros((N, C, H + 2, W + 2), n.float32)
        xp[:, :, 1:-1, 1:-1] = x
        y = n.zeros((N, H, W, w.shape[0]), n.float32)
        for dy in range(3):
            for dx in range(3):
                y += n.tensordot(xp[:, :, dy:dy + H, dx:dx + W], w[:, :, dy, dx], axes=([1], [1]))
        y += b
        return y.transpose(0, 3, 1, 2)

    @staticmethod
    def pool(x):
        N, C, H, W = x.shape
        return x.reshape(N, C, H // 2, 2, W // 2, 2).max(axis=(3, 5))

    @staticmethod
    def up(x, w, b):
        """2 x 2 stride-2 transposed convolution: x (N, C, H, W), w (C, O, 2, 2) -> (N, O, 2H, 2W)."""
        n = np
        N, C, H, W = x.shape
        y = n.tensordot(x, w, axes=([1], [0]))            # (N, H, W, O, 2, 2)
        y = y.transpose(0, 3, 1, 4, 2, 5).reshape(N, w.shape[1], 2 * H, 2 * W)
        return y + b[None, :, None, None]

    def block(self, name, x):
        p = self.p
        x = np.maximum(self.conv3(x, p[f"{name}.0.w"], p[f"{name}.0.b"]), 0)
        return np.maximum(self.conv3(x, p[f"{name}.1.w"], p[f"{name}.1.b"]), 0)

    def forward(self, x, lvt):
        """x (N, 1, S, S) float32 canvas, lvt (N, 3) int -> logits (N, 3, S, S)."""
        n = np
        p = self.p
        if self.cond:
            c = p["eL"][lvt[:, 0]] + p["eV"][lvt[:, 1]] + p["eT"][lvt[:, 2]]          # (N, C)
            x = n.concatenate([x, n.broadcast_to(c[:, :, None, None], (x.shape[0], c.shape[1]) + x.shape[2:])], 1)
        e1 = self.block("e1", x)
        e2 = self.block("e2", self.pool(e1))
        e3 = self.block("e3", self.pool(e2))
        b = self.block("b", self.pool(e3))
        if self.cond:
            b = b + (c @ p["bott.w"].T + p["bott.b"])[:, :, None, None]
        d3 = self.block("d3", n.concatenate([self.up(b, p["u3.w"], p["u3.b"]), e3], 1))
        d2 = self.block("d2", n.concatenate([self.up(d3, p["u2.w"], p["u2.b"]), e2], 1))
        d1 = self.block("d1", n.concatenate([self.up(d2, p["u1.w"], p["u1.b"]), e1], 1))
        return n.tensordot(d1, p["out.w"][:, :, 0, 0], axes=([1], [1])).transpose(0, 3, 1, 2) + p["out.b"][None, :, None, None]


def canvas_geometry(h, w, canvas=32):
    k = max(1, canvas // max(h, w))
    side = max(canvas, -(-k * max(h, w) // 8) * 8)
    return k, side, (side - k * h) // 2, (side - k * w) // 2


def to_canvas(a, canvas=32):
    """(N, h, w) -> (N, side, side) float32, scaled by k and centred; returns (canvas array, geometry)."""
    n = _np()
    h, w = a.shape[-2:]
    k, side, oy, ox = canvas_geometry(h, w, canvas)
    out = n.zeros(a.shape[:-2] + (side, side), n.float32)
    out[..., oy:oy + k * h, ox:ox + k * w] = a.repeat(k, axis=-2).repeat(k, axis=-1)
    return out, (k, oy, ox)


def from_canvas(p, h, w, geom):
    k, oy, ox = geom
    c = p[..., oy:oy + k * h, ox:ox + k * w]
    return c.reshape(c.shape[:-2] + (h, k, w, k)).mean(axis=(-3, -1))


def predict(model, pre, jamo, batch=64):
    """Per-pixel slot probabilities and the proposals of a face: pre (N, h, w) 0/1, jamo (N, 3) L V T ->
    (prob (N, 3, h, w) float32, prop (N, 3, h, w) uint8). A pixel is in plane k when p > 0.5; an ink pixel no plane takes
    goes to the most likely allowed plane; a syllable without a final has no final plane (masked before the choice)."""
    n = _np()
    h, w = pre.shape[1:]
    x, geom = to_canvas(pre.astype(n.float32), model.meta.get("canvas", 32))
    out = []
    for i in range(0, len(x), batch):
        logit = model.forward(x[i:i + batch, None], n.asarray(jamo[i:i + batch], n.int64))
        out.append(1 / (1 + n.exp(-n.clip(logit, -60, 60))))
    prob = from_canvas(n.concatenate(out), h, w, geom).astype(n.float32)
    prob[:, 2] *= (n.asarray(jamo)[:, 2] > 0)[:, None, None]      # no final plane without a final, before any choice
    ink = pre.astype(bool)
    prop = (prob > 0.5) & ink[:, None]
    none = ink & ~prop.any(axis=1)
    am = prob.argmax(axis=1)                                         # over the allowed planes (a masked one is 0)
    for k in range(3):
        prop[:, k] |= none & (am == k)
    return prob, prop.astype(n.uint8)
