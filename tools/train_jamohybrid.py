#!/usr/bin/env python3
"""Train the jamohybrid split model (tools/jamonet.py) and export its weights. Training-time only: needs torch and numpy;
the tool and the tests never import this file.

  python3 tools/train_jamohybrid.py --manifest SOURCES.tsv --out DIR [--holdout GROUP ...] [--base 16|32]
      [--epochs N] [--seed N] [--eval GROUP ...] [--sizes 12,16,...]

SOURCES.tsv lists the training data, one source per line (tab separated, '#' comments):
  name  kind  path  group  weight  licence  note
kind:
  svf   a 1 bpp jamo-set SVF (JSET): its composed syllables are the precomposed targets and its pieces the planes
        (the KS X 1001 syllables; 'all' in note: all 11,172)
  npz   arrays cps, jamo (N, 3), pre (N, h, w), planes (N, 3, h, w), optional has_planes (N,) mask: a ground-truth
        set prepared elsewhere (kept outside this repository)
  (further kinds plug in through SOURCES below: a loader gets (path, note, sizes) and returns a list of
   (pre, planes, jamo, mask) arrays, one per size.)
--holdout drops every source of a group from training; --eval measures the trained model on the named groups (all
their syllables with planes) and writes the numbers to DIR/eval.json. DIR/jamohybrid.npz is the exported weights (fp16,
BatchNorm folded); DIR/provenance.json lists every source used with its sha256, size, group, licence and syllables, the
seed, the epochs and this script's arguments. The export is checked against tools/jamonet.py's numpy forward pass
(largest probability difference, DIR/provenance.json "numpy_check").
"""

import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import jamonet  # noqa: E402

KS = None


def ks2350():
    global KS
    if KS is None:
        KS = [ord(bytes([0xB0 + i // 94, 0xA1 + i % 94]).decode("euc_kr")) - 0xAC00 for i in range(2350)]
    return KS


def lvt(n):
    return n // 588, (n // 28) % 21, n % 28


# ---- sources ---------------------------------------------------------------------------------------------------

def load_svf(path, note, sizes):
    import jamoset as J
    f = J.parse_svfn(open(path, "rb").read())
    if not f.flags & J.FLAG_JAMO or f.bpp != 1:
        raise ValueError(f"{path}: not a 1 bpp jamo-set face")
    t = J.unpack(f.jset)
    w, h = f.cell_w, f.cell_h
    nb = (w + 7) // 8
    syl = list(range(11172)) if "all" in note.split(",") else ks2350()
    planes = np.zeros((len(syl), 3, h, w), np.uint8)
    cache = {}
    for i, s in enumerate(syl):
        for k, p in enumerate(J.pieces_of(t, 0xAC00 + s)):
            if p == J.BLANK:
                continue
            if p not in cache:
                g = f.glyphs[J.PIECE_BASE + p]
                rows = [int.from_bytes(g[y * nb:(y + 1) * nb], "big") >> (nb * 8 - w) for y in range(h)]
                cache[p] = np.array([[(r >> (w - 1 - x)) & 1 for x in range(w)] for r in rows], np.uint8)
            planes[i, k] = cache[p]
    jamo = np.array([lvt(s) for s in syl], np.int64)
    return [(planes.max(axis=1), planes, jamo, np.ones(len(syl), bool))]


def load_npz(path, note, sizes):
    z = np.load(path, allow_pickle=False)
    mask = z["has_planes"].astype(bool) if "has_planes" in z.files else np.ones(len(z["cps"]), bool)
    if "gt_exact" in z.files:
        mask &= z["gt_exact"].astype(bool)
    return [(z["pre"].astype(np.uint8), z["planes"].astype(np.uint8), z["jamo"].astype(np.int64), mask)]


SOURCES = {"svf": load_svf, "npz": load_npz}


def read_manifest(path):
    out = []
    for line in open(path, encoding="utf-8"):
        if not line.strip() or line.startswith("#"):
            continue
        f = line.rstrip("\n").split("\t")
        f += [""] * (7 - len(f))
        name, kind, p, group, weight, licence, note = f[:7]
        out.append(dict(name=name, kind=kind, path=os.path.expanduser(p), group=group, weight=float(weight or 1),
                        licence=licence, note=note))
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ---- model (torch) ------------------------------------------------------------------------------------------------

def make_model(base, cdim, cond):
    import torch.nn as nn
    import torch
    import torch.nn.functional as F

    def block(cin, cout):
        return nn.Sequential(nn.Conv2d(cin, cout, 3, padding=1), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                             nn.Conv2d(cout, cout, 3, padding=1), nn.BatchNorm2d(cout), nn.ReLU(inplace=True))

    class UNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.cond = cond
            cin = 1 + (cdim if cond else 0)
            if cond:
                self.eL, self.eV, self.eT = nn.Embedding(19, cdim), nn.Embedding(21, cdim), nn.Embedding(28, cdim)
                self.bott = nn.Linear(cdim, base * 8)
            self.e1, self.e2, self.e3 = block(cin, base), block(base, base * 2), block(base * 2, base * 4)
            self.b = block(base * 4, base * 8)
            self.u3, self.d3 = nn.ConvTranspose2d(base * 8, base * 4, 2, 2), block(base * 8, base * 4)
            self.u2, self.d2 = nn.ConvTranspose2d(base * 4, base * 2, 2, 2), block(base * 4, base * 2)
            self.u1, self.d1 = nn.ConvTranspose2d(base * 2, base, 2, 2), block(base * 2, base)
            self.out = nn.Conv2d(base, 3, 1)

        def forward(self, x, lvt):
            if self.cond:
                c = self.eL(lvt[:, 0]) + self.eV(lvt[:, 1]) + self.eT(lvt[:, 2])
                x = torch.cat([x, c[:, :, None, None].expand(-1, -1, x.shape[2], x.shape[3])], 1)
            e1 = self.e1(x)
            e2 = self.e2(F.max_pool2d(e1, 2))
            e3 = self.e3(F.max_pool2d(e2, 2))
            b = self.b(F.max_pool2d(e3, 2))
            if self.cond:
                b = b + self.bott(c)[:, :, None, None]
            d3 = self.d3(torch.cat([self.u3(b), e3], 1))
            d2 = self.d2(torch.cat([self.u2(d3), e2], 1))
            d1 = self.d1(torch.cat([self.u1(d2), e1], 1))
            return self.out(d1)
    return UNet()


def export(model, base, cdim, cond, path, extra):
    """Fold BatchNorm into the convolutions and write the jamonet-1 weights (fp16)."""
    import torch
    sd = {}
    m = model.eval()
    for name in ("e1", "e2", "e3", "b", "d3", "d2", "d1"):
        seq = getattr(m, name)
        for i, (ci, bi) in enumerate(((0, 1), (3, 4))):
            conv, bn = seq[ci], seq[bi]
            s = bn.weight / torch.sqrt(bn.running_var + bn.eps)
            sd[f"{name}.{i}.w"] = (conv.weight * s[:, None, None, None]).detach().cpu().numpy()
            sd[f"{name}.{i}.b"] = ((conv.bias - bn.running_mean) * s + bn.bias).detach().cpu().numpy()
    for name in ("u3", "u2", "u1", "out"):
        layer = getattr(m, name)
        sd[f"{name}.w"] = layer.weight.detach().cpu().numpy()
        sd[f"{name}.b"] = layer.bias.detach().cpu().numpy()
    if cond:
        for name in ("eL", "eV", "eT"):
            sd[name] = getattr(m, name).weight.detach().cpu().numpy()
        sd["bott.w"] = m.bott.weight.detach().cpu().numpy()
        sd["bott.b"] = m.bott.bias.detach().cpu().numpy()
    meta = dict(format="jamonet-1", base=base, cdim=cdim, cond=cond, canvas=32, **extra)
    np.savez_compressed(path, meta=np.array(json.dumps(meta)), **{k: v.astype(np.float16) for k, v in sd.items()})


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--holdout", nargs="*", default=[])
    ap.add_argument("--eval", nargs="*", default=[])
    ap.add_argument("--base", type=int, default=32)
    ap.add_argument("--cdim", type=int, default=16)
    ap.add_argument("--no-cond", action="store_true")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--sizes", default="", help="pixel sizes for sources that render (passed to the loaders)")
    a = ap.parse_args()
    import torch
    import torch.nn.functional as F
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    sizes = [int(x) for x in a.sizes.split(",") if x]
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    srcs = read_manifest(a.manifest)
    groups, prov = [], []
    evalsets = {}
    for s in srcs:
        use = s["group"] not in a.holdout
        want_eval = s["group"] in a.eval
        if not use and not want_eval:
            continue
        parts = SOURCES[s["kind"]](s["path"], s["note"], sizes)
        n_syl = 0
        for pre, planes, jamo, mask in parts:
            pre, planes, jamo = pre[mask], planes[mask], jamo[mask]
            n_syl += len(pre)
            if want_eval:
                evalsets.setdefault(s["group"], []).append((s["name"], pre, planes, jamo))
            if use:
                x, geom = jamonet.to_canvas(pre.astype(np.float32))
                y, _ = jamonet.to_canvas(planes.astype(np.float32))
                groups.append(dict(name=s["name"], k=geom[0], x=torch.from_numpy(x[:, None]), y=torch.from_numpy(y),
                                   lvt=torch.from_numpy(jamo), w=s["weight"]))
        if use:
            prov.append(dict(name=s["name"], kind=s["kind"], file=os.path.basename(s["path"]), sha256=sha256(s["path"]),
                             bytes=os.path.getsize(s["path"]), group=s["group"], weight=s["weight"],
                             licence=s["licence"], note=s["note"], syllables=n_syl))
    model = make_model(a.base, a.cdim, not a.no_cond).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    total = sum(len(g["x"]) for g in groups)
    per_epoch = max(1, total // a.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, a.lr, total_steps=a.epochs * per_epoch)
    probs = np.array([len(g["x"]) * g["w"] for g in groups], float)
    probs /= probs.sum()
    if dev == "cuda":
        torch.cuda.reset_peak_memory_stats()
    losses = []
    for ep in range(a.epochs):
        model.train()
        tot = 0.0
        for _ in range(per_epoch):
            g = groups[np.random.choice(len(groups), p=probs)]
            idx = torch.randint(0, len(g["x"]), (a.batch,))
            xb, yb = g["x"][idx], g["y"][idx]
            dy, dx = (np.random.randint(-1, 2, 2) * g["k"]).tolist()
            xb, yb = torch.roll(xb, (dy, dx), (2, 3)), torch.roll(yb, (dy, dx), (2, 3))
            xb, yb, lv = xb.to(dev), yb.to(dev), g["lvt"][idx].to(dev)
            logit = model(xb, lv)
            m = (xb > 0).expand_as(logit).float()
            loss = (F.binary_cross_entropy_with_logits(logit, yb, reduction="none") * m).sum() / m.sum()
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            tot += loss.item()
        losses.append(round(tot / per_epoch, 5))
        print(f"epoch {ep + 1}/{a.epochs} loss {losses[-1]}", flush=True)
    train_s = time.time() - t0
    wpath = os.path.join(a.out, "jamohybrid.npz")
    export(model, a.base, a.cdim, not a.no_cond, wpath,
           dict(seed=a.seed, epochs=a.epochs, holdout=a.holdout, trained=time.strftime("%Y-%m-%d")))
    # numpy check and evaluation
    net = jamonet.Model(wpath)
    model.eval()
    res = {}
    worst = 0.0
    for gname, items in evalsets.items():
        rows = []
        for name, pre, planes, jamo in items:
            prob, prop = jamonet.predict(net, pre, jamo)
            with torch.no_grad():
                x, geom = jamonet.to_canvas(pre[:256].astype(np.float32))
                tl = model(torch.from_numpy(x[:, None]).to(dev), torch.from_numpy(jamo[:256]).to(dev))
                tp = jamonet.from_canvas(torch.sigmoid(tl).cpu().numpy(), pre.shape[1], pre.shape[2], geom)
            worst = max(worst, float(np.abs(tp - prob[:256]).max()))
            ink = pre.astype(bool)
            ok = ((prop.astype(bool) == planes.astype(bool)).all(axis=1) & ink).sum() / ink.sum()
            exact = int(((prop.astype(bool) & ink[:, None]) == planes.astype(bool)).all(axis=(1, 2, 3)).sum())
            rows.append(dict(face=name, syllables=len(pre), label_acc=round(float(ok), 4), exact=exact))
        res[gname] = rows
        print(gname, rows, flush=True)
    info = dict(sources=prov, holdout=a.holdout, seed=a.seed, epochs=a.epochs, base=a.base, cdim=a.cdim,
                cond=not a.no_cond, params=int(sum(p.numel() for p in model.parameters())), train_seconds=round(train_s, 1),
                device=torch.cuda.get_device_name(0) if dev == "cuda" else "cpu",
                gpu_peak_mib=round(torch.cuda.max_memory_allocated() / 2 ** 20) if dev == "cuda" else None,
                loss=losses, numpy_check=dict(max_abs_prob_diff=worst), weights_sha256=sha256(wpath),
                weights_bytes=os.path.getsize(wpath), argv=sys.argv[1:])
    json.dump(info, open(os.path.join(a.out, "provenance.json"), "w"), indent=1)
    json.dump(res, open(os.path.join(a.out, "eval.json"), "w"), indent=1)
    print("done", a.out, info["params"], "params", info["train_seconds"], "s, numpy diff", worst, flush=True)


if __name__ == "__main__":
    main()
