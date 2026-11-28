#!/usr/bin/env python3
"""jamohybrid.py - a jamo-set face from a precomposed one by a learned split (docs/jamo-split.md, the learned split).

Like `jamoset.py --from-svf` / `--from-ttf`, it builds a jamo set (JSET) whose composed syllables follow a precomposed
face. Unlike the pixel fit it also gets the split right: which pixels are the initial, the medial and the final.

  1. Proposals. A per-pixel model (tools/jamonet.py, weights tools/models/jamohybrid-v1.npz) gives every syllable's
     initial / medial / final planes, conditioned on the syllable's jamo. Every syllable the source holds is used.
  2. Classes. Lead classes (of the 19 initials) and tail classes (of the 28 finals; no final alone) by Ward clustering
     of what the other slots show with each initial / final (--rule derived), or fixed ones (--rule structural).
  3. Groups, bottom-up, inside the exact JSET structure. The tables read a syllable as cell = (lead class, vowel, tail
     class), so the set limits hold per lead class for the initial, per vowel for the medial and per tail class for the
     final (standard JSET: 32 / 24 / 16 sets, 12 x 12 classes; --big: 64 / 48 / 32, 19 x 28). In each of these the
     contexts start apart and the cheapest pair merges - cost = the pixels that then disagree with the group's
     majority piece - first down to the set limit, then on while a merge adds at most --tol pixels per syllable of its
     smaller group (default cell height / 12 px): such merges remove prediction noise, not designs.
  4. Identity gates (hard): enough ink and extent; holes (ㅁ ㅂ ㅇ ㅎ ㅃ have one, ㄱ ㄴ ㄷ ㄹ ㅅ ㅈ ㅋ none); the ticks of
     ㅏ ㅑ ㅓ ㅕ ㅣ and the stubs of ㅗ ㅛ ㅜ ㅠ ㅡ, with a serif tolerance; ㅅ and ㅈ slant. Each check is on where at least
     90 % of the face's own proposals pass it. A merge that would turn a passing piece into a failing one is not made
     (unless the set limit leaves no other). A group's piece is the majority weighted by the model's probabilities;
     where it fails a gate, the member proposal nearest to it that passes; where none does, the nearest passing piece
     of that jamo in another group. Then jamofit re-fits the pieces to the precomposed syllables, each pixel only in a
     slot the model gave it; a failing re-fit keeps the piece.
  5. A context no source syllable shows joins the group of the nearest context that has syllables (by how alike the
     vowels and classes are); a (group, jamo) pair without syllables takes the piece of the nearest group that has one.

  python3 tools/jamohybrid.py --from-svf FACE.SVF -o OUT.SVF [--max-bytes N | --min-iou X | --limits NI,NM,NF] [--tol PX]
                              [--classes LC,TC]
  python3 tools/jamohybrid.py --from-ttf FONT --size N [--cell WxH] [--baseline R] -o OUT.SVF ...
  options: --big (BIG limits; default off), --rule derived|structural, --model PATH, --report OUT.json, --check,
           --jset-version 1|2|auto, --pylib DIR (a directory holding numpy, also $JAMOSET_PYLIB)

Stopping rule. A (lead class, tail class) pair costs 63 table bytes and a stored piece its bitmap, so the face is kept
small in two ways: the merge tolerance above, and the class caps. Without --max-bytes / --min-iou the face is built at
the standard limits and the default tolerance for the class caps 12x12, 12x6, 8x8, 6x6 and 4x4, and the smallest within
0.005 composed IoU of the most accurate is kept (--classes fixes the cap). --max-bytes and --min-iou walk a ladder -
every class cap at 6 ... 0.5 times the default tolerance; with --big also BIG points - and keep the most accurate face
within the bytes, or the smallest that reaches the composed IoU. The report gives the composed IoU over
every source syllable and over the KS X 1001 ones. Needs numpy (and freetype-py for --from-ttf); not torch.
"""

import argparse
import json
import os
import struct
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import jamoset as J  # noqa: E402

np = None
DEFAULT_MODEL = os.path.join(HERE, "models", "jamohybrid-v1.npz")
LEADS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
VOWELS = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
TAILS = "-ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
NAMES = (LEADS, VOWELS, TAILS)
SLOTS = ("initial", "medial", "final")
LEAD7 = ["ㄱㄲㅋ", "ㄴㄷㅅ", "ㄸㄹㅌ", "ㅁㅂㅇㅈ", "ㅃㅆㅉ", "ㅊㅎ", "ㅍ"]
COMPLEX = set("ㄳㄵㄶㄺㄻㄼㄽㄾㄿㅀㅄ")
LIMITS = {False: ((32, 24, 16), (12, 12)), True: ((64, 48, 32), (19, 28))}
# The class caps tried (lead, tail): a (lead class, tail class) pair costs 63 table bytes, so fewer classes can pay.
CLASS_GRID = {False: ((12, 12), (12, 6), (8, 8), (6, 6), (4, 4)), True: ((19, 28), (19, 14), (12, 12))}
SLACK = 0.005                # the default face: the smallest within this composed IoU of the most accurate class cap
# the --max-bytes / --min-iou ladder: every class cap at these merge tolerances (multiples of the default)
TOL_LADDER = (6.0, 4.0, 3.0, 2.0, 1.0, 0.5)
BIG_TOL_LADDER = (2.0, 1.0, 0.5)
TOL_UNIT = 1.0               # default merge tolerance: this many pixels per syllable at a 12 px cell, scaled with the cell


def load_numpy(pylib=None):
    global np
    if np is None:
        for d in (pylib, os.environ.get("JAMOSET_PYLIB")):
            for part in (d or "").split(os.pathsep):
                if part and part not in sys.path:
                    sys.path.append(part)
        try:
            import numpy
        except ImportError:
            raise SystemExit("jamohybrid: numpy is needed (pip install numpy, or --pylib DIR / $JAMOSET_PYLIB)")
        np = numpy
    return np


def lvt(s):
    return s // 588, (s // 28) % 21, s % 28


# ---- identity checks ---------------------------------------------------------------------------------------------

HOLE1, HOLE0 = set("ㅁㅂㅇㅎㅃ"), set("ㄱㄴㄷㄹㅅㅈㅋ")
VT = {"ㅏ": (0, 1), "ㅑ": (0, 2), "ㅓ": (1, 0), "ㅕ": (2, 0), "ㅣ": (0, 0)}    # (left, right) ticks
HT = {"ㅗ": (1, 0), "ㅛ": (2, 0), "ㅜ": (0, 1), "ㅠ": (0, 2), "ㅡ": (0, 0)}    # (up, down) stubs
FRACS = (0.0, 0.15, 0.2, 0.25)


def crop(a):
    ys, xs = np.nonzero(a)
    return a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def longest_runs(a):
    """Longest run of ink in each column of @p a."""
    best = np.zeros(a.shape[1], int)
    cur = np.zeros(a.shape[1], int)
    for row in a:
        cur = np.where(row > 0, cur + 1, 0)
        best = np.maximum(best, cur)
    return best


def runs_of(v):
    v = np.asarray(v, bool)
    return int(v[0]) + int((v[1:] & ~v[:-1]).sum()) if len(v) else 0


def ticks(a, vertical, end_frac):
    """(before, after) tick counts beside the main stroke (left / right of a vertical, above / below a bar); side ink
    within @p end_frac of the main stroke's length at either end is a serif, not a tick."""
    b = a if vertical else a.T
    h, w = b.shape
    main = np.nonzero(longest_runs(b) >= 0.6 * h)[0]
    if not len(main):
        return None
    c0, c1 = main.min(), main.max()
    left = b[:, c0 - 1].copy() if c0 > 0 else np.zeros(h, b.dtype)
    right = b[:, c1 + 1].copy() if c1 + 1 < w else np.zeros(h, b.dtype)
    if end_frac:
        rows = np.nonzero(b[:, c0:c1 + 1].any(axis=1))[0]
        top, bot = rows.min(), rows.max()
        cut = int(np.floor(end_frac * (bot - top + 1)))
        if cut:
            for side in (left, right):
                side[:top + cut] = 0
                side[bot - cut + 1:] = 0
    return runs_of(left), runs_of(right)


def holes(a):
    """Closed counters: 4-connected background components that do not touch the border."""
    bg = np.pad(1 - a, 1, constant_values=1).astype(bool)   # the border is background
    h, w = bg.shape
    seen = np.zeros_like(bg)
    n = 0
    for y0 in range(h):
        for x0 in range(w):
            if bg[y0, x0] and not seen[y0, x0]:
                n += 1
                stack = [(y0, x0)]
                seen[y0, x0] = True
                while stack:
                    y, x = stack.pop()
                    for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                        if 0 <= yy < h and 0 <= xx < w and bg[yy, xx] and not seen[yy, xx]:
                            seen[yy, xx] = True
                            stack.append((yy, xx))
    return n - 1


def span(rows):
    xs = np.nonzero(rows.any(axis=0))[0]
    return int(xs.max() - xs.min() + 1) if len(xs) else 0


def check(name, slot, a, end_frac):
    """{check: bool} for a piece of jamo @p name in @p slot (0, 1, 2)."""
    if not a.any():
        return {"present": False}
    out = {"present": True}
    c = crop(a).astype(np.uint8)
    h, w = c.shape
    if slot != 1:
        if name in HOLE1:
            out["holes"] = holes(c) >= 1
        elif name in HOLE0:
            out["holes"] = holes(c) == 0
        if name == "ㅅ" and h >= 3:
            t = max(1, h // 3)
            out["slant"] = bool(span(c[h - t:]) > span(c[:t]) and longest_runs(c[:max(1, h // 2)].T).max() < 0.6 * w)
        if name == "ㅈ" and h >= 3:
            t = max(1, h // 3)
            mid = c[t:h - t] if h - 2 * t > 0 else c[t:t + 1]
            out["bar+slant"] = bool(longest_runs(c[:t].T).max() >= 0.5 * w and span(c[h - t:]) > span(mid))
    elif name in VT:
        out["ticks"] = ticks(c, True, end_frac) == VT[name]
    elif name in HT:
        out["ticks"] = ticks(c, False, end_frac) == HT[name]
    return out


class Gates:
    """The identity gates of a face, calibrated on its own proposals."""

    def __init__(self, jamo, prop):
        self.shape = prop.shape[2:]
        self.frac = FRACS[-1]
        for f in FRACS:                     # serif tolerance: the smallest share under which the ticks pass (95 %)
            ok = True
            for v, want in {**VT, **HT}.items():
                idx = np.nonzero((jamo[:, 1] == VOWELS.index(v)) & prop[:, 1].any(axis=(1, 2)))[0]
                res = [check(v, 1, prop[i, 1], f).get("ticks", True) for i in idx]
                if res and np.mean(res) < 0.95:
                    ok = False
                    break
            if ok:
                self.frac = f
                break
        stat = defaultdict(lambda: [0, 0])
        self.mass, self.extent = {}, {}
        for k in range(3):
            for j in range(len(NAMES[k])):
                if k == 2 and j == 0:
                    continue
                idx = np.nonzero((jamo[:, k] == j) & prop[:, k].any(axis=(1, 2)))[0]
                if not len(idx):
                    continue
                name = NAMES[k][j]
                self.mass[(k, name)] = float(np.median(prop[idx, k].sum(axis=(1, 2))))
                hs, ws = [], []
                for i in idx:
                    ys, xs = np.nonzero(prop[i, k])
                    hs.append(ys.max() - ys.min() + 1)
                    ws.append(xs.max() - xs.min() + 1)
                    for ck, ok in check(name, k, prop[i, k], self.frac).items():
                        stat[(k, name, ck)][0] += 1
                        stat[(k, name, ck)][1] += ok
                self.extent[(k, name)] = (float(np.median(hs)), float(np.median(ws)))
        self.on = defaultdict(set)
        self.off = []
        for (k, name, ck), (n, p) in stat.items():
            if p >= 0.9 * n:
                self.on[(k, name)].add(ck)
            else:
                self.off.append(f"{SLOTS[k]} {name} {ck} ({p}/{n})")

    def ok(self, k, name, piece):
        m = self.mass.get((k, name))
        if m is not None and piece.sum() < 0.5 * m:
            return False
        ext = self.extent.get((k, name))
        if ext is not None:
            ys, xs = np.nonzero(piece)
            if not len(ys) or ys.max() - ys.min() + 1 < 0.6 * ext[0] or xs.max() - xs.min() + 1 < 0.6 * ext[1]:
                return False
        want = self.on.get((k, name), ())
        if want:
            r = check(name, k, piece, self.frac)
            return all(r.get(c, True) for c in want)
        return True


# ---- classes -------------------------------------------------------------------------------------------------------

def structural_classes():
    """Fixed lead classes (7) and tail classes (none, ㄴ ㅅ, the other single finals, the double finals)."""
    lead = [next(g for g, s in enumerate(LEAD7) if c in s) for c in LEADS]
    tail = [0] + [1 if t in "ㄴㅅ" else 3 if t in COMPLEX else 2 for t in TAILS[1:]]
    return lead, tail


def ward(d2, k):
    """Ward clustering from squared distances into at most @p k groups, numbered by first appearance."""
    n = len(d2)
    d = np.array(d2, np.float64)
    np.fill_diagonal(d, np.inf)
    size = np.ones(n)
    label = list(range(n))
    alive = list(range(n))
    while len(alive) > k:
        sub = d[np.ix_(alive, alive)]
        a, b = np.unravel_index(int(np.argmin(sub)), sub.shape)
        i, j = alive[a], alive[b]
        for m in alive:
            if m != i and m != j:
                v = ((size[i] + size[m]) * d[i, m] + (size[j] + size[m]) * d[j, m] - size[m] * d[i, j]) / \
                    (size[i] + size[j] + size[m])
                d[i, m] = d[m, i] = v
        size[i] += size[j]
        label = [i if x == j else x for x in label]
        alive.remove(j)
    ids = {}
    return [ids.setdefault(x, len(ids)) for x in label]


def axis_distances(jamo, prop):
    """Squared distances between the initials, the vowels and the finals by what the *other* slots show with each:
    initials by the medial and final proposals over every (V, T), vowels by the initial and final over (L, T), finals
    by the initial and medial over (L, V). A syllable the source lacks takes the mean of the others in its place. Each
    matrix is divided by its median (0 on the diagonal). Large cells are pooled to at most 24 px a side first."""
    n, _, h, w = prop.shape
    f = max(1, -(-max(h, w) // 24))
    hp, wp = -(-h // f) * f, -(-w // f) * f
    p = np.zeros((n, 3, hp, wp), np.float32)
    p[:, :, :h, :w] = prop
    p = p.reshape(n, 3, hp // f, f, wp // f, f).mean(axis=(3, 5)).reshape(n, 3, -1)
    idx = np.full((19, 21, 28), -1)
    idx[jamo[:, 0], jamo[:, 1], jamo[:, 2]] = np.arange(n)
    out = []
    for axis, slots in ((0, (1, 2)), (1, (0, 2)), (2, (0, 1))):
        m = (19, 21, 28)[axis]
        ix = np.moveaxis(idx, axis, 0).reshape(m, -1)
        d = np.zeros((m, m))
        for col in range(ix.shape[1]):
            rows = ix[:, col]
            have = rows >= 0
            if have.sum() < 2:
                continue
            x = p[rows[have]][:, slots].reshape(int(have.sum()), -1)
            full = np.repeat(x.mean(axis=0)[None], m, axis=0)
            full[have] = x
            g = full @ full.T
            q = np.diag(g)
            d += q[:, None] + q[None, :] - 2 * g
        d = np.maximum(d, 0)
        off = d[np.triu_indices(m, 1)]
        med = float(np.median(off[off > 0])) if (off > 0).any() else 1.0
        out.append(d / med)
    return out


def derived_classes(dist, max_classes):
    """Lead and tail classes by Ward clustering of the axis distances; no final is its own tail class."""
    lead = ward(dist[0], max_classes[0])
    tail = [0] + [c + 1 for c in ward(dist[2][1:, 1:], max_classes[1] - 1)]
    return lead, tail


# ---- grouping inside the JSET structure ----------------------------------------------------------------------------
#
# The tables read a syllable as cell = (lead class of L, V, tail class of T); initial = init_piece[init_set[cell]][L],
# medial = med_piece[med_set[cell]][V], final = fin_piece[fin_set[cell]][T]. A set number is therefore only ever read
# for the jamo of the cell's own class, and the set limits hold
#     per lead class for the initial   (contexts (V, tail class); a group holds one piece per initial of the class),
#     per vowel for the medial         (contexts (lead class, tail class); one piece),
#     per tail class for the final     (contexts (lead class, V); one piece per final of the class).
# A Problem is one of these: its contexts are merged bottom-up into at most `limit` groups.

def vote_of(s, n):
    """The piece of summed weighted votes: a pixel is on when its ink-weighted probability outweighs the rest."""
    return (2 * s > n[..., None]).astype(np.uint8)


class Problem:
    def __init__(self, slot, key, jamo, ctx, s, n, users):
        self.slot, self.key, self.jamo, self.ctx = slot, key, jamo, ctx      # ctx: the context of each item
        self.s0, self.n0 = s, n                                              # (items, jamo, px), (items, jamo)
        self.users0 = users                                                  # [item][jamo index] -> syllable rows
        self.full = np.nonzero(n.sum(axis=1) > 0)[0]                         # items some syllable shows
        self.d0 = None                                                       # the unmerged cost matrix, kept

    def start(self):
        """A fresh merge state over the items that have syllables."""
        self.s = self.s0[self.full].copy()
        self.n = self.n0[self.full].copy()
        m = len(self.full)
        self.mem = [[int(i)] for i in self.full]
        self.alive = np.ones(m, bool)
        self.cost = self.c(self.s, self.n)
        self.tot = self.n.sum(axis=1)
        self.gate = [None] * m                                               # per group: {jamo index: vote passes}
        self.d = np.full((m, m), np.inf, np.float32)
        if self.d0 is None:
            for a in range(m):
                self.row(a)
            self.d0 = self.d.copy()
        else:
            self.d = self.d0.copy()
        return self

    @staticmethod
    def c(s, n):
        return np.minimum(s, n[..., None] - s).sum(axis=(-1, -2))

    def row(self, a):
        idx = np.nonzero(self.alive)[0]
        idx = idx[idx != a]
        self.d[a, :] = np.inf
        self.d[:, a] = np.inf
        if len(idx):
            r = self.c(self.s[idx] + self.s[a], self.n[idx] + self.n[a]) - self.cost[idx] - self.cost[a]
            self.d[a, idx] = r
            self.d[idx, a] = r

    def groups(self):
        return int(self.alive.sum())

    def gates_of(self, g, gates):
        if self.gate[g] is None:
            v = vote_of(self.s[g], self.n[g])
            self.gate[g] = {ji: gates.ok(self.slot, NAMES[self.slot][j], v[ji].reshape(gates.shape))
                            for ji, j in enumerate(self.jamo) if self.n[g, ji] > 0}
        return self.gate[g]

    def best(self, tol=None):
        """(cost, a, b) of the cheapest merge; with @p tol only among the merges whose added disagreement is at most
        tol pixels per syllable of the smaller group."""
        d = self.d
        if tol is not None:
            small = np.minimum(self.tot[:, None], self.tot[None, :])
            d = np.where(d <= tol * small, d, np.inf)
        k = int(np.argmin(d))
        a, b = divmod(k, d.shape[1])
        return float(d[a, b]), a, b

    def breaks_gate(self, a, b, gates):
        """Would merging a and b turn a piece that passes its identity gates into one that fails?"""
        ga, gb = self.gates_of(a, gates), self.gates_of(b, gates)
        s, n = self.s[a] + self.s[b], self.n[a] + self.n[b]
        v = vote_of(s, n)
        merged = {}
        for ji, j in enumerate(self.jamo):
            if n[ji] > 0:
                merged[ji] = gates.ok(self.slot, NAMES[self.slot][j], v[ji].reshape(gates.shape))
                if not merged[ji] and (ga.get(ji) or gb.get(ji)):
                    return True, None
        return False, merged

    def merge(self, a, b, merged_gate=None):
        self.s[a] += self.s[b]
        self.n[a] += self.n[b]
        self.tot[a] += self.tot[b]
        self.cost[a] = self.c(self.s[a], self.n[a])
        self.mem[a] += self.mem[b]
        self.alive[b] = False
        self.gate[a] = merged_gate
        self.d[b, :] = np.inf
        self.d[:, b] = np.inf
        self.row(a)


def make_problems(jamo, prob, ink, lead, tail):
    """The Problems of a face for the given classes, with S = the ink-weighted probabilities summed per context."""
    n_syl, _, h, w = prob.shape
    px = h * w
    nlc, ntc = max(lead) + 1, max(tail) + 1
    lc = np.asarray(lead)[jamo[:, 0]]
    tc = np.asarray(tail)[jamo[:, 2]]
    wv = (prob * ink[:, None]).reshape(n_syl, 3, px).astype(np.float32)
    out = []

    def add(slot, key, members, ctx, sel, item_of, jamo_of):
        pos = {c: i for i, c in enumerate(ctx)}
        jpos = {j: i for i, j in enumerate(members)}
        s = np.zeros((len(ctx), len(members), px), np.float32)
        n = np.zeros((len(ctx), len(members)), np.float32)
        users = [[[] for _ in members] for _ in ctx]
        if len(sel):
            it = np.array([pos[item_of(i)] for i in sel])
            jj = np.array([jpos[jamo_of(i)] for i in sel])
            np.add.at(s, (it, jj), wv[sel, slot])
            np.add.at(n, (it, jj), 1)
            for i, a, b in zip(sel, it, jj):
                users[a][b].append(int(i))
        out.append(Problem(slot, key, members, ctx, s, n, users))
    for c in range(nlc):
        add(0, c, [L for L in range(19) if lead[L] == c], [(V, t) for V in range(21) for t in range(ntc)],
            np.nonzero(lc == c)[0], lambda i: (int(jamo[i, 1]), int(tc[i])), lambda i: int(jamo[i, 0]))
    for V in range(21):
        add(1, V, [V], [(c, t) for c in range(nlc) for t in range(ntc)],
            np.nonzero(jamo[:, 1] == V)[0], lambda i: (int(lc[i]), int(tc[i])), lambda i: V)
    for t in range(1, ntc):
        add(2, t, [T for T in range(1, 28) if tail[T] == t], [(c, V) for c in range(nlc) for V in range(21)],
            np.nonzero(tc == t)[0], lambda i: (int(lc[i]), int(jamo[i, 1])), lambda i: int(jamo[i, 2]))
    return out


def group(problems, limits, tol, gates, stats, gate_merges=True):
    """Merge every problem's contexts: first down to the slot's set limit (the cheapest merge that breaks no identity
    gate; a forced one when only gate-breaking merges are left), then on while a merge adds at most @p tol pixels of
    disagreement per syllable of its smaller group (those merges remove prediction noise, not designs)."""
    for p in problems:
        p.start()
        refused = set()

        def take(tol_):
            while True:
                cost, a, b = p.best(tol_)
                if not np.isfinite(cost):
                    return False
                if gate_merges:
                    bad, mg = p.breaks_gate(a, b, gates)
                    if bad:
                        refused.add((a, b))
                        p.d[a, b] = p.d[b, a] = np.inf
                        stats["merge_refused_by_gate"] += 1
                        continue
                else:
                    mg = None
                p.merge(a, b, mg)
                stats["merges"] += 1
                return True
        while p.groups() > limits[p.slot]:
            if not take(None):
                # only gate-breaking merges are left: the limit is hard, so the cheapest of them is made
                for a, b in refused:
                    if p.alive[a] and p.alive[b]:
                        p.d[a, b] = p.d[b, a] = p.c(p.s[a] + p.s[b], p.n[a] + p.n[b]) - p.cost[a] - p.cost[b]
                refused.clear()
                cost, a, b = p.best(None)
                if not np.isfinite(cost):
                    break
                p.merge(a, b, None)
                stats["merges_forced_through_a_gate"] += 1
        if tol is not None and tol > 0:
            while p.groups() > 1 and take(tol):
                pass


def context_distance(p, dist, lead, tail):
    """A function d(ctx, ctx') between two contexts of a problem from the axis distances (class distances are the
    mean over the classes' members)."""
    nlc, ntc = max(lead) + 1, max(tail) + 1

    def classd(d, lab, k):
        mem = [[i for i, x in enumerate(lab) if x == c] for c in range(k)]
        return np.array([[float(d[np.ix_(a, b)].mean()) if a and b else 0.0 for b in mem] for a in mem])
    dl, dt, dv = classd(dist[0], lead, nlc), classd(dist[2], tail, ntc), dist[1]
    if p.slot == 0:
        return lambda x, y: dv[x[0], y[0]] + dt[x[1], y[1]]
    if p.slot == 1:
        return lambda x, y: dl[x[0], y[0]] + dt[x[1], y[1]]
    return lambda x, y: dl[x[0], y[0]] + dv[x[1], y[1]]


def pieces_of_groups(problems, prop, gates, dist, lead, tail, stats):
    """Per problem: the group of every context (a context no syllable shows joins the group of the nearest context
    that has one), and a piece for every (group, jamo): the vote; where the vote fails a gate, the member proposal
    nearest to it that passes, else the nearest passing piece of the same jamo in another group; where no syllable
    shows the jamo in the group, the piece of the nearest group that has it (a gate-passing one first). Returns piece {(slot, problem key, group, jamo): bitmap}, users (same keys ->
    syllable rows) and group_of {(slot, problem key): {context: group}}."""
    shape = gates.shape
    piece, users, group_of, borrowed = {}, {}, {}, {}
    for p in problems:
        reps = [int(a) for a in np.nonzero(p.alive)[0]] if len(p.full) else []
        cd = context_distance(p, dist, lead, tail)
        gof = {}
        for g, a in enumerate(reps):
            for item in p.mem[a]:
                gof[p.ctx[item]] = g
        have = list(gof)
        for c in p.ctx:
            if c not in gof:
                gof[c] = gof[min(have, key=lambda x: (cd(c, x), x))] if have else 0
                stats["contexts_without_syllables"] += 1
        group_of[(p.slot, p.key)] = gof
        name = NAMES[p.slot]
        failing = []
        for g, a in enumerate(reps):
            v = vote_of(p.s[a], p.n[a])
            for ji, j in enumerate(p.jamo):
                if p.n[a, ji] <= 0:
                    continue
                us = np.array([i for item in p.mem[a] for i in p.users0[item][ji]])
                b = v[ji].reshape(shape)
                if not gates.ok(p.slot, name[j], b):
                    stats["vote_gate_fail"] += 1
                    e = err(b, prop[us, p.slot])
                    for i in np.argsort(e, kind="stable"):
                        if gates.ok(p.slot, name[j], prop[us[i], p.slot]):
                            b = prop[us[i], p.slot].copy()
                            stats["vote_replaced_by_proposal"] += 1
                            break
                    else:
                        failing.append((g, ji, j))
                piece[(p.slot, p.key, g, j)] = b
                users[(p.slot, p.key, g, j)] = us
        # a piece that still fails (no member proposal passes): the group draws this jamo with the nearest piece
        # of the same jamo that passes, and its syllables join that piece's
        for g, ji, j in failing:
            own = piece[(p.slot, p.key, g, j)]
            cands = sorted((int((piece[(p.slot, p.key, g2, j)] != own).sum()), g2) for g2 in range(len(reps))
                           if g2 != g and (p.slot, p.key, g2, j) in piece and (g2, ji, j) not in failing)
            if cands:
                donor = (p.slot, p.key, cands[0][1], j)
                borrowed[(p.slot, p.key, g, j)] = donor
                users[donor] = np.concatenate([users[donor], users.pop((p.slot, p.key, g, j))])
                del piece[(p.slot, p.key, g, j)]
                stats["gate_fail_took_nearest_passing_piece"] += 1
            else:
                stats["vote_gate_fail_kept"] += 1
        # (group, jamo) pairs no syllable shows: borrowed from the nearest group that has the jamo
        ctx_of = defaultdict(list)
        for c, g in gof.items():
            ctx_of[g].append(c)
        ngroups = max(len(reps), 1)
        for g in range(ngroups):
            for ji, j in enumerate(p.jamo):
                if (p.slot, p.key, g, j) in piece or (p.slot, p.key, g, j) in borrowed:
                    continue
                cands = []
                for g2, a2 in enumerate(reps):
                    if (p.slot, p.key, g2, j) in piece:
                        near = min(cd(x, p.ctx[item]) for x in ctx_of[g] for item in p.mem[a2] if p.n0[item, ji] > 0)
                        cands.append((near, g2))
                cands.sort()
                pick = next((g2 for _, g2 in cands if gates.ok(p.slot, name[j], piece[(p.slot, p.key, g2, j)])),
                            cands[0][1] if cands else None)
                if pick is not None:
                    borrowed[(p.slot, p.key, g, j)] = (p.slot, p.key, pick, j)
                    stats["pieces_borrowed"] += 1
    return piece, users, group_of, borrowed


# ---- re-fit --------------------------------------------------------------------------------------------------------

def err(piece, props):
    return (piece[None] != props).sum(axis=(1, 2))


def refit(piece, users, prop, ink, gates, stats, passes=12):
    """Re-fit the grouped pieces to the precomposed syllables (jamofit.fit_pieces), each piece confined to the pixels
    its users' proposals or its vote give that slot. Keys are (slot, ..., jamo); pieces with equal bitmaps of one
    jamo are fitted as one."""
    import jamofit as JF
    h, w = ink.shape[1:]
    weights = 1 << np.arange(w - 1, -1, -1, dtype=object)

    def to_g(a):
        return JF.from_rows([int((a[y].astype(object) * weights).sum()) for y in range(h)], w)
    keyid, members = {}, defaultdict(list)
    for key, a in piece.items():
        kid = (key[0], key[-1], a.tobytes())
        keyid[key] = kid
        members[kid].append(key)
    syl = {}
    for key, us in users.items():
        for i in us:
            syl.setdefault(int(i), [None, None, None])[key[0]] = keyid[key]
    masks = {}
    for kid, keys in members.items():
        us = np.array([i for key in keys for i in users[key]])
        masks[kid] = to_g(prop[us, kid[0]].max(axis=0) | piece[keys[0]])
    targets = {i: to_g(ink[i]) for i in syl}
    P, _ = JF.fit_pieces({i: tuple(v) for i, v in syl.items()}, targets, w, h, masks, passes, True)
    kept = 0
    for kid, keys in members.items():
        if kid not in P:
            continue
        rows = JF.to_rows(P[kid], w, h)
        a = np.array([[(r >> (w - 1 - x)) & 1 for x in range(w)] for r in rows], np.uint8)
        if not a.any() or not gates.ok(kid[0], NAMES[kid[0]][kid[1]], a):
            kept += 1
            continue
        for key in keys:
            piece[key] = a
    stats["refit_kept_vote"] = kept


# ---- one face ------------------------------------------------------------------------------------------------------

class Source:
    """The precomposed syllables: syl (N,) indices, pre (N, h, w), plus what the written face keeps (base, extra)."""

    def __init__(self, syl, pre, ascent, base=None, extra=None, advance=None, info=None):
        self.syl, self.pre, self.ascent = syl, pre, ascent
        self.base, self.extra, self.advance, self.info = base, extra, advance, info or {}


# Limits on an input face (the face is untrusted data): checked before it is parsed or any array is built.
MAX_FILE = 16 << 20
MAX_CELL = 64
MAX_GLYPHS = 70000
MAX_PIXELS = 11172 * 64 * 64


def from_svf(path):
    try:
        size = os.path.getsize(path)
    except OSError as e:
        raise SystemExit(f"{path}: {e.strerror}")
    if size > MAX_FILE:
        raise SystemExit(f"{path}: {size} bytes, more than {MAX_FILE}")
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < J.HEADER3_SIZE or data[:4] != J.MAGIC:
        raise SystemExit(f"{path}: not an SVFN face")
    head = struct.unpack_from(J.HEADER3, data)
    version, count, cw, ch = head[1], head[7], head[8], head[9]
    if version != J.VERSION:
        raise SystemExit(f"{path}: SVFN version {version}; convert it with tools/svf2to3.py first")
    if cw > MAX_CELL or ch > MAX_CELL:
        raise SystemExit(f"{path}: cell {cw}x{ch} is larger than {MAX_CELL}x{MAX_CELL}")
    if count > MAX_GLYPHS:
        raise SystemExit(f"{path}: {count} glyphs, more than {MAX_GLYPHS}")
    try:
        f = J.parse_svfn(data)
    except ValueError as e:
        raise SystemExit(f"{path}: {e}")
    if f.bpp != 1 or f.flags & J.FLAG_JAMO:
        raise SystemExit(f"{path}: not a 1 bpp precomposed face")
    n_syl = sum(1 for cp in f.glyphs if 0xAC00 <= cp <= 0xD7A3)
    if not n_syl:
        raise SystemExit(f"{path}: no Hangul syllables")
    if n_syl * cw * ch > MAX_PIXELS:
        raise SystemExit(f"{path}: {n_syl} syllables of {cw}x{ch} are more than {MAX_PIXELS} pixels")
    w, h = f.cell_w, f.cell_h
    nb = (w + 7) // 8
    syl, pre = [], []
    for cp in sorted(f.glyphs):
        if 0xAC00 <= cp <= 0xD7A3 and any(f.glyphs[cp]):
            g = f.glyphs[cp]
            rows = [int.from_bytes(g[y * nb:(y + 1) * nb], "big") >> (nb * 8 - w) for y in range(h)]
            pre.append([[(r >> (w - 1 - x)) & 1 for x in range(w)] for r in rows])
            syl.append(cp - 0xAC00)
    if not syl:
        raise SystemExit(f"{path}: every Hangul syllable is blank")
    return Source(np.array(syl), np.array(pre, np.uint8), f.ascent, base=data, advance=J.svf_advance(f),
                  info=dict(face=os.path.basename(path), cell=[w, h]))


def from_ttf(path, size, cell, baseline, pylib):
    import jamofit as JF
    targets, w, h, ascent, tinfo, ascii_glyphs = J.ttf_targets(path, size, cell, baseline, True, pylib)
    syl = sorted(targets)
    pre = []
    for s in syl:
        rows = JF.to_rows(targets[s], w, h)
        pre.append([[(r >> (w - 1 - x)) & 1 for x in range(w)] for r in rows])
    return Source(np.array(syl), np.array(pre, np.uint8), ascent, extra=ascii_glyphs, info=tinfo)


def default_tol(h):
    """The default merge tolerance: pixels of added disagreement per syllable of the smaller group."""
    return TOL_UNIT * h / 12.0


def prepare(src, model, rule_name, max_classes):
    """Proposals, gates, classes and the unmerged problems of a source; kept on it for the ladder's other points."""
    import jamonet
    cache = src.__dict__.setdefault("_prep", {})
    key = (rule_name, tuple(max_classes))
    if key not in cache:
        jamo = np.array([lvt(int(s)) for s in src.syl], np.int64)
        if not hasattr(src, "_pred"):
            src._pred = jamonet.predict(model, src.pre, jamo)
        prob, prop = src._pred
        ink = src.pre.astype(np.uint8)
        if "gates" not in src.__dict__:
            src.gates = Gates(jamo, prop)
            src.dist = axis_distances(jamo, prop)
        lead, tail = structural_classes() if rule_name == "structural" else derived_classes(src.dist, max_classes)
        cache[key] = dict(jamo=jamo, prob=prob, prop=prop, ink=ink, gates=src.gates, dist=src.dist, lead=lead, tail=tail,
                          problems=make_problems(jamo, prob, ink, lead, tail))
    return cache[key]


def build_face(src, model, rule_name, limits, max_classes, big, jset_version, log=None, tol=None, gate_merges=True):
    """Build one face; returns (bytes, layout, info). @p tol: the merge tolerance in pixels per syllable (None: the
    default for the cell; 0: no merging beyond the set limits)."""
    t0 = time.time()
    P = prepare(src, model, rule_name, max_classes)
    jamo, prop, ink, gates, lead, tail = P["jamo"], P["prop"], P["ink"], P["gates"], P["lead"], P["tail"]
    h, w = ink.shape[1:]
    if tol is None:
        tol = default_tol(h)
    stats = Counter()
    group(P["problems"], limits, tol, gates, stats, gate_merges)
    piece, users, group_of, borrowed = pieces_of_groups(P["problems"], prop, gates, P["dist"], lead, tail, stats)
    refit(piece, users, prop, ink, gates, stats)
    nlc, ntc = max(lead) + 1, max(tail) + 1
    count = [1, 1, 1]
    for (slot, _), gof in group_of.items():
        count[slot] = max(count[slot], max(gof.values()) + 1)
    ni, nm, nf = count
    bitmaps, index = [], {}

    def idx(a):
        key = a.tobytes()
        if key not in index:
            index[key] = len(bitmaps)
            bitmaps.append(a)
        return index[key]

    def srcp(key):
        a = piece.get(borrowed.get(key, key))
        return None if a is None else idx(a)
    init_src = {(s, L): srcp((0, lead[L], s, L)) for s in range(ni) for L in range(19)}
    med_src = {(s, V): srcp((1, V, s, V)) for s in range(nm) for V in range(21)}
    fin_src = {(s, T): srcp((2, tail[T], s, T)) for s in range(nf) for T in range(1, 28)}
    layout = J.Layout("hybrid", None, nlc, ntc, ni, nm, nf, lambda L: lead[L], lambda T: tail[T],
                      lambda c, V, t: group_of[(0, c)][(V, t)], lambda c, V, t: group_of[(1, V)][(c, t)],
                      lambda c, V, t: group_of[(2, t)][(c, V)] if t else 0,
                      lambda s, L: init_src[(s, L)], lambda s, V: med_src[(s, V)], lambda s, T: fin_src[(s, T)])

    class Pieces:
        def __init__(self):
            self.w, self.h, self.count = w, h, len(bitmaps)

        def glyph(self, i):
            return J.Glyph(w, h, [int("".join("1" if x else "0" for x in r), 2) for r in bitmaps[i]])
    out, _, _ = J.build_from_source(layout, Pieces(), None, src.base, src.ascent, src.extra, src.base is not None,
                                    src.advance, jset_version=jset_version, jset_big=big)
    # quality of the written face against the source: every source syllable, and the KS X 1001 ones among them
    f = J.parse_svfn(out)
    t = J.unpack(f.jset)
    nb = (w + 7) // 8
    ious = np.zeros(len(src.syl))
    exact = 0
    for i, s in enumerate(src.syl):
        c = J.compose(f, t, 0xAC00 + int(s))
        a = np.unpackbits(np.frombuffer(bytes(c), np.uint8).reshape(h, nb), axis=1)[:, :w].astype(bool)
        b = ink[i].astype(bool)
        u = (a | b).sum()
        ious[i] = (a & b).sum() / u if u else 1.0
        exact += bool((a == b).all())
    ks = np.isin(src.syl, ks_syllables())
    failing = sum(1 for (slot, j, _), a in {(k[0], k[-1], a.tobytes()): a for k, a in piece.items()}.items()
                  if not gates.ok(slot, NAMES[slot][j], a))
    info = dict(limits=list(limits), max_classes=list(max_classes), big=big, rule=rule_name, sets=[ni, nm, nf],
                classes=[nlc, ntc], bytes=len(out), comp_iou=round(float(ious.mean()), 4), comp_exact=int(exact),
                syllables=len(src.syl), ks_syllables=int(ks.sum()),
                comp_iou_ks=round(float(ious[ks].mean()), 4) if ks.any() else None,
                merge_tolerance_px=round(float(tol), 3), pieces=len(bitmaps), gates_failing=failing,
                serif_tolerance=gates.frac, gates_off=gates.off,
                lead_classes=["".join(LEADS[L] for L in range(19) if lead[L] == c) for c in range(nlc)],
                tail_classes=["".join(TAILS[T] for T in range(28) if tail[T] == c) for c in range(ntc)],
                stats=dict(stats), seconds=round(time.time() - t0, 1))
    if log:
        log(f"limits {tuple(limits)}, tolerance {tol:.2f} px: {len(out)} bytes, IoU {info['comp_iou']}, "
            f"{len(bitmaps)} pieces, sets {ni}/{nm}/{nf}, classes {nlc}x{ntc}")
    return out, layout, info


_KS = None


def ks_syllables():
    """The 2,350 KS X 1001 syllables as indices from U+AC00."""
    global _KS
    if _KS is None:
        _KS = np.array([ord(bytes([0xB0 + i // 94, 0xA1 + i % 94]).decode("euc_kr")) - 0xAC00 for i in range(2350)])
    return _KS


FLOOR = (1, 1, 1)            # the grouping needs no minimum; a set limit is at least one group
FORMAT_ROW = {False: (32, 24, 16), True: (128, 128, 64)}


def parse_limits(ap, text, big):
    """--limits NI,NM,NF checked against the format's standard (or BIG) row."""
    try:
        lim = tuple(int(x) for x in text.split(","))
    except ValueError:
        ap.error(f"--limits {text!r}: three whole numbers NI,NM,NF")
    if len(lim) != 3:
        ap.error(f"--limits {text!r}: three whole numbers NI,NM,NF")
    row = FORMAT_ROW[big]
    for name, v, lo, hi in zip(("NI", "NM", "NF"), lim, FLOOR, row):
        if not lo <= v <= hi:
            ap.error(f"--limits: {name} {v} is outside {lo}..{hi} ("
                     f"{'BIG' if big else 'standard'} row {row}{'' if big else '; --big for more'})")
    return lim


def choose_point(infos, max_bytes=None, min_iou=None):
    """Index of the ladder point to keep and why: the most accurate within @p max_bytes (else the smallest), or the
    smallest whose composed IoU reaches @p min_iou (else the most accurate)."""
    idx = range(len(infos))
    if max_bytes is not None:
        ok = [i for i in idx if infos[i]["bytes"] <= max_bytes]
        if ok:
            return max(ok, key=lambda i: (infos[i]["comp_iou"], -infos[i]["bytes"])), f"most accurate within {max_bytes} B"
        return min(idx, key=lambda i: infos[i]["bytes"]), f"none within {max_bytes} B: the smallest"
    ok = [i for i in idx if infos[i]["comp_iou"] >= min_iou]
    if ok:
        return min(ok, key=lambda i: infos[i]["bytes"]), f"smallest with IoU >= {min_iou}"
    return max(idx, key=lambda i: infos[i]["comp_iou"]), f"none reaches IoU {min_iou}: the most accurate"


def class_caps(rule_name, big, classes=None):
    """The class caps to try: the given one, the single fixed pair of --rule structural, else CLASS_GRID."""
    if classes is not None:
        return (tuple(classes),)
    return (LIMITS[big][1],) if rule_name == "structural" else CLASS_GRID[big]


def build_default(src, model, rule_name, limits, big, jset_version, log=None, tol=None, classes=None):
    """The face at @p limits and one merge tolerance: built for every class cap, the smallest within SLACK composed
    IoU of the most accurate is kept. Returns (bytes, layout, info) with info["choice"]."""
    pts = [build_face(src, model, rule_name, limits, mc, big, jset_version, log, tol=tol)
           for mc in class_caps(rule_name, big, classes)]
    top = max(p[2]["comp_iou"] for p in pts)
    out, layout, info = min((p for p in pts if p[2]["comp_iou"] >= top - SLACK), key=lambda p: p[2]["bytes"])
    info["choice"] = dict(rule="fixed limits" if len(pts) == 1 else
                          f"the smallest class cap within {SLACK} IoU of the most accurate",
                          tried=[dict(max_classes=p[2]["max_classes"], classes=p[2]["classes"], bytes=p[2]["bytes"],
                                      comp_iou=p[2]["comp_iou"]) for p in pts])
    return out, layout, info


def build_ladder(src, model, rule_name, big, jset_version, max_bytes=None, min_iou=None, log=None, classes=None):
    """The --max-bytes / --min-iou ladder: the standard limits at every class cap and every merge tolerance of
    TOL_LADDER (fewer classes and a larger tolerance = a smaller face), and with @p big the BIG limits likewise; the
    point choose_point keeps. Returns (bytes, layout, info) with info["choice"]."""
    h = src.pre.shape[1]
    pts = [build_face(src, model, rule_name, LIMITS[False][0], mc, False, jset_version, log, tol=m * default_tol(h))
           for mc in class_caps(rule_name, False, None if big else classes) for m in TOL_LADDER]
    if big:
        pts += [build_face(src, model, rule_name, LIMITS[True][0], mc, True, jset_version, log, tol=m * default_tol(h))
                for mc in class_caps(rule_name, True, classes) for m in BIG_TOL_LADDER]
    pick, why = choose_point([p[2] for p in pts], max_bytes, min_iou)
    out, layout, info = pts[pick]
    info["choice"] = dict(rule=why, ladder=[dict(limits=p[2]["limits"], big=p[2]["big"], max_classes=p[2]["max_classes"],
                                                 merge_tolerance_px=p[2]["merge_tolerance_px"], bytes=p[2]["bytes"],
                                                 comp_iou=p[2]["comp_iou"]) for p in pts])
    return out, layout, info


def parse_classes(ap, text, big):
    """--classes LC,TC: the lead / tail class caps, at least 1 lead and 2 tail classes, within the format's row."""
    try:
        c = tuple(int(x) for x in text.split(","))
    except ValueError:
        c = ()
    hi = LIMITS[big][1] if not big else (19, 28)
    if len(c) != 2 or not (1 <= c[0] <= hi[0] and 2 <= c[1] <= hi[1]):
        ap.error(f"--classes {text!r}: LC,TC with LC 1..{hi[0]} and TC 2..{hi[1]}"
                 f"{'' if big else ' (--big for more)'}")
    return c


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src_g = ap.add_mutually_exclusive_group(required=True)
    src_g.add_argument("--from-svf", metavar="FACE.SVF", help="a 1 bpp precomposed SVF face (every syllable it holds is used)")
    src_g.add_argument("--from-ttf", metavar="FONT", help="an outline font rendered at --size (as jamoset.py; every "
                       "syllable the font draws is used)")
    ap.add_argument("--size", type=int, help="--from-ttf: pixel size")
    ap.add_argument("--cell", help="--from-ttf: cell WxH (default SIZExSIZE)")
    ap.add_argument("--baseline", type=int, help="--from-ttf: baseline row")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--rule", choices=("derived", "structural"), default="derived",
                    help="the lead / tail classes: derived (default) clusters them from the face's own proposals; "
                    "structural uses fixed classes (7 lead, 4 tail)")
    lim = ap.add_mutually_exclusive_group()
    lim.add_argument("--limits", help="set limits NI,NM,NF (default 32,24,16; with --big 64,48,32)")
    lim.add_argument("--max-bytes", type=int, help="the most accurate face of the tolerance ladder within this many bytes")
    lim.add_argument("--min-iou", type=float, help="the smallest face of the tolerance ladder whose composed IoU reaches this")
    ap.add_argument("--tol", type=float, metavar="PX", help="merge tolerance: groups merge while that adds at most PX "
                    "pixels of disagreement per syllable of the smaller group (default cell height / 12; 0 keeps every "
                    "group the set limits allow). Not with --max-bytes / --min-iou, which walk a ladder of tolerances")
    ap.add_argument("--classes", metavar="LC,TC", help="the caps on lead and tail classes (standard: up to 12,12; "
                    "--big: 19,28). Default: several caps are built and the smallest face within 0.005 composed IoU "
                    "of the most accurate is kept (a class pair costs 63 table bytes)")
    ap.add_argument("--big", action="store_true", help="JSET BIG: the tool's default limits become 64/48/32 sets and 19 x 28 "
                    "classes (the format's BIG row allows up to 128/128/64; the --max-bytes / --min-iou ladder adds "
                    "BIG points to the standard ones); engines built with SVF_JSET_BIG read it. The standard face is "
                    "the default")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="weights (.npz, tools/jamonet.py format)")
    ap.add_argument("--report", metavar="OUT.json", help="write the chosen point, the ladder and the build details")
    ap.add_argument("--check", action="store_true", help="compose all 11,172 syllables of the output (jamoset check)")
    ap.add_argument("--jset-version", default="1", choices=("1", "2", "auto"))
    ap.add_argument("--pylib", help="directory holding numpy (also $JAMOSET_PYLIB)")
    a = ap.parse_args(argv)
    load_numpy(a.pylib)
    import jamonet
    jamonet.np = np
    if a.from_ttf and not a.size:
        ap.error("--from-ttf needs --size")
    if a.size is not None and not 4 <= a.size <= MAX_CELL:
        ap.error(f"--size {a.size}: 4..{MAX_CELL}")
    if a.tol is not None and (a.max_bytes is not None or a.min_iou is not None):
        ap.error("--tol: not with --max-bytes / --min-iou")
    if a.tol is not None and not 0 <= a.tol <= MAX_CELL:
        ap.error(f"--tol {a.tol}: 0..{MAX_CELL}")
    if a.limits:
        parse_limits(ap, a.limits, a.big)          # before any work
    classes = parse_classes(ap, a.classes, a.big) if a.classes else None
    model = jamonet.Model(a.model)
    if a.from_svf:
        src = from_svf(a.from_svf)
    else:
        try:
            cell = tuple(int(x) for x in a.cell.lower().split("x")) if a.cell else None
        except ValueError:
            cell = ()
        if cell is not None and not (len(cell) == 2 and all(4 <= v <= MAX_CELL for v in cell)):
            ap.error(f"--cell {a.cell}: WxH, each 4..{MAX_CELL}")
        src = from_ttf(a.from_ttf, a.size, cell, a.baseline, a.pylib)
    jv = a.jset_version if a.jset_version == "auto" else int(a.jset_version)
    log = lambda m: print(m, file=sys.stderr)  # noqa: E731
    if a.max_bytes is None and a.min_iou is None:
        limits = parse_limits(ap, a.limits, a.big) if a.limits else LIMITS[a.big][0]
        out, layout, info = build_default(src, model, a.rule, limits, a.big, jv, log, a.tol, classes)
    else:
        out, layout, info = build_ladder(src, model, a.rule, a.big, jv, a.max_bytes, a.min_iou, log, classes)
    choice = info["choice"]
    info["source"] = src.info
    info["model"] = dict(file=os.path.basename(a.model), **{k: model.meta.get(k) for k in ("base", "trained")})
    with open(a.output, "wb") as fh:
        fh.write(out)
    ks = f", KS {info['comp_iou_ks']}" if info.get("comp_iou_ks") is not None and info["ks_syllables"] != info["syllables"] else ""
    print(f"{a.output}: {info['bytes']} bytes, composed IoU {info['comp_iou']}{ks} ({info['comp_exact']} of "
          f"{info['syllables']} exact), {info['pieces']} pieces, sets {info['sets'][0]}/{info['sets'][1]}/{info['sets'][2]}, "
          f"classes {info['classes'][0]}x{info['classes'][1]}{', BIG' if info['big'] else ''}, "
          f"{info['gates_failing']} pieces fail a gate; {choice['rule']}")
    if a.check:
        print("check:", J.check(out, layout, None))
    if a.report:
        with open(a.report, "w") as fh:
            json.dump(info, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
