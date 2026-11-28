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
  5. The initial of a context no source syllable shows is placed by where its ink sits for that (vowel, final): an
     additive model of the initial's box, fitted to the syllables the source has (the final is known even where the
     source never draws the pair), gives the context the group whose pieces sit nearest. Only the initial is modelled:
     the same model for the medial was measured and cost more than it gained, and the final does better from its own
     cell. With --fill (on by default, --fill none turns it off) a cross-font ranker decides first: it scores every
     candidate group of such a context from the face's own pieces and geometry, and picks the group it expects to match
     the font's true piece best (a 60-64-64-1 float32 MLP, tools/models/jamofill-v1.npz; ~1.5 ms per context). It can
     only choose a group the face already stores, so bytes, pieces, sets and gates do not change; the baseline order
     below stays the fallback where there are fewer than two candidates. Where the model is unidentified or has
     nothing to say the context joins the group the other lead classes (vowels, tail classes) most often put it with,
     else that of the nearest context that has syllables (by how alike the vowels and classes are); a (group, jamo)
     pair without syllables takes the piece of the nearest group that has one. A jamo no syllable of its problem shows
     at all (no syllable with that initial, vowel or final in the class) has no piece and draws blank; the summary
     warns and the report lists it (blank_jamo).

  python3 tools/jamohybrid.py --from-svf FACE.SVF -o OUT.SVF [--max-bytes N | --min-iou X | --limits NI,NM,NF]
                              [--tol PX] [--classes LC,TC] [--fill [MODEL.npz]]
  python3 tools/jamohybrid.py --from-ttf FONT --size N [--cell WxH] [--baseline R] -o OUT.SVF ...
  options: --big (BIG limits; default off), --rule derived|structural, --model PATH, --fill [PATH|none],
           --report OUT.json, --check, --jset-version 1|2|auto, --pylib DIR (a directory holding numpy, also $JAMOSET_PYLIB)

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
DEFAULT_FILL = os.path.join(HERE, "models", "jamofill-v1.npz")
FILL_FEATURES, FILL_HIDDEN = 60, (64, 64)     # the --fill ranker: 60-64-64-1, float32, numpy only
MAX_FILL_FILE = 1 << 20                        # a weights file larger than this is refused before loading
MAX_FILL_PARAMS = 65536                        # and one with more parameters
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
TOL_UNIT = 1.0               # default merge tolerance: pixels per syllable at a 12 px cell, scaled with the cell


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


def sibling_votes(problems):
    """Per slot, how the problems that show two contexts group them: votes[slot][(x, y)] = [together, both shown].
    A context one lead class (vowel, tail class) lacks is placed where its siblings put it."""
    votes = [defaultdict(lambda: [0, 0]) for _ in range(3)]
    for p in problems:
        if not len(p.full):
            continue
        gof = {}
        for g, a in enumerate(np.nonzero(p.alive)[0]):
            for item in p.mem[a]:
                gof[p.ctx[item]] = g
        shown = sorted(gof)
        v = votes[p.slot]
        for i, x in enumerate(shown):
            for y in shown[i + 1:]:
                e = v[(x, y)]
                e[0] += gof[x] == gof[y]
                e[1] += 1
    return votes


def ink_box(a):
    """(top, left, bottom, right) of the ink in @p a, or None when it is blank."""
    ys, xs = np.nonzero(a)
    return np.array([ys.min(), xs.min(), ys.max(), xs.max()], np.float64) if len(ys) else None


def fit_boxes(obs, nu, nv, rounds=6):
    """Additive fit (median polish) of box ~ mu + a[u] + b[v] over {(u, v): box}, or None when the observations do not
    identify it: both axes need two observed levels, and the observed cells must form one connected bipartite graph
    between them -- a single cell, or cells that do not link the levels, leave a[u] + b[v] at an unobserved cell
    undetermined, and the prediction would then collapse to the global box. Each coordinate of the box is a sum of a
    term of the first axis and one of the second."""
    us, vs = {k[0] for k in obs}, {k[1] for k in obs}
    if len(us) < 2 or len(vs) < 2:
        return None
    adj = defaultdict(set)
    for u, v in obs:
        adj[("u", u)].add(("v", v))
        adj[("v", v)].add(("u", u))
    start, seen, stack = next(iter(adj)), set(), [next(iter(adj))]
    seen.add(start)
    while stack:
        for k in adj[stack.pop()]:
            if k not in seen:
                seen.add(k)
                stack.append(k)
    if len(seen) != len(adj):
        return None
    mu = np.median(np.array(list(obs.values())), axis=0)
    a, b = np.zeros((nu, 4)), np.zeros((nv, 4))
    for _ in range(rounds):
        for u in range(nu):
            r = [x - mu - b[k[1]] for k, x in obs.items() if k[0] == u]
            if r:
                a[u] = np.median(np.array(r), axis=0)
        for v in range(nv):
            r = [x - mu - a[k[0]] for k, x in obs.items() if k[1] == v]
            if r:
                b[v] = np.median(np.array(r), axis=0)
    return mu, a, b


def box_model(prop, jamo):
    """Where the initial's ink sits, as an additive model keyed by the syllable's own (vowel, final): the final's shape
    sets how much room the initial gets, and the pair is known even where the source never draws it. Only the initial
    is fitted. The medial was measured with the same model and loses more at the default class cap than it gains
    (Galmuri11 12 px: initial +0.03, medial -0.03), and the final's own cell is better served by the sibling vote.
    None when the source's cells cannot identify the model (see fit_boxes)."""
    obs = defaultdict(list)
    for i in range(len(jamo)):
        b = ink_box(prop[i, 0])
        if b is not None:
            obs[(int(jamo[i, 1]), int(jamo[i, 2]))].append(b)
    return fit_boxes({k: np.median(np.array(v), axis=0) for k, v in obs.items()}, 21, 28)


def box_placement(c, model, tail, boxes_of):
    """The group whose pieces sit nearest the box the model predicts for context @p c (a (vowel, tail class)), or None
    without candidates. Ties go to the group holding more pieces, then to the lower group index, so the choice never
    depends on dict order. @p model: (mu, a, b) of the initial; @p boxes_of: group -> the boxes of its pieces."""
    mu, a, b = model
    ts = [0] if c[1] == 0 else [T for T in range(1, 28) if tail[T] == c[1]]
    pred = np.median([mu + a[c[0]] + b[T] for T in ts], axis=0)
    cands = [(float(np.mean([np.abs(x - pred).sum() for x in bs])), -len(bs), g)
             for g, bs in boxes_of.items() if bs]
    return min(cands)[2] if cands else None


# ---- the cross-font group ranker (--fill) --------------------------------------------------------------------------
#
# A context no source syllable shows takes the group the baseline order (box model, sibling votes, nearest context)
# puts it with. `--fill` asks a cross-font ranker first: for each candidate group, one row of 60 scale-free numbers
# computed from the face's own pieces (the layout prediction, the class mean boxes, and the group's distance, box,
# sibling vote and nearest-neighbour shares); the ranker is a 60-64-64-1 float32 MLP that scores the mean IoU the
# group's piece would have with the piece the font actually draws there. It can only pick a group the face already
# stores, so grouping, bytes, pieces, sets and every identity gate stay as they are; a context with fewer than two
# candidates, an invalid answer or an unusable model falls back to the baseline. Weights: tools/models/jamofill-v1.npz.

class FillModel:
    """The --fill weights: mu / sd / med (60) and three float32 matrices W0 (60, 64), W1 (64, 64), W2 (64, 1) with
    their biases, read with allow_pickle=False and checked by name, shape and dtype before use."""

    def __init__(self, path):
        n = np
        try:
            size = os.path.getsize(path)
        except OSError as e:
            raise ValueError(f"{path}: {e.strerror}")
        if size > MAX_FILL_FILE:
            raise ValueError(f"{path}: {size} bytes, more than {MAX_FILL_FILE}")
        with n.load(path, allow_pickle=False) as z:
            files = set(z.files)
            self.meta = {}
            if "meta" in files:
                try:
                    self.meta = json.loads(str(z["meta"]))
                except ValueError:
                    raise ValueError(f"{path}: meta is not JSON")
                if self.meta.get("format") != "jamofill-1":
                    raise ValueError(f"{path}: not a jamofill-1 weights file")
            want = {"mu": (FILL_FEATURES,), "sd": (FILL_FEATURES,), "med": (FILL_FEATURES,),
                    "W0": (FILL_FEATURES, FILL_HIDDEN[0]), "b0": (FILL_HIDDEN[0],),
                    "W1": (FILL_HIDDEN[0], FILL_HIDDEN[1]), "b1": (FILL_HIDDEN[1],),
                    "W2": (FILL_HIDDEN[1], 1), "b2": (1,)}
            if files - {"meta"} != set(want):
                raise ValueError(f"{path}: arrays {sorted(files ^ (set(want) | {'meta'}))} missing or unexpected")
            total = 0
            self.p = {}
            for k, shape in want.items():
                a = z[k]
                if a.dtype.kind != "f" or a.shape != shape:
                    raise ValueError(f"{path}: {k} is {a.dtype} {a.shape}, want float {shape}")
                with n.errstate(over="ignore", invalid="ignore"):
                    a = a.astype(n.float32)         # check after the conversion: a large float64 overflows here
                if not n.all(n.isfinite(a)):
                    raise ValueError(f"{path}: {k} holds NaN or infinite values (as float32)")
                if k == "sd" and not n.all(a > 0):
                    raise ValueError(f"{path}: sd must be positive")
                total += a.size
                self.p[k] = a
            if total > MAX_FILL_PARAMS:
                raise ValueError(f"{path}: {total} parameters, more than {MAX_FILL_PARAMS}")
            self.params, self.path = total, path

    def score(self, X):
        """The model's score for rows X (N, 60): one float per row, higher is the better group."""
        n = np
        p = self.p
        Z = n.asarray(X, n.float32)
        Z = (n.where(n.isnan(Z), p["med"], Z) - p["mu"]) / p["sd"]
        Z = n.maximum(Z @ p["W0"] + p["b0"], 0)
        Z = n.maximum(Z @ p["W1"] + p["b1"], 0)
        return (Z @ p["W2"] + p["b2"])[:, 0]


def fill_boxes(prop, jamo, lead, tail):
    """An additive ink-box model per slot as the ranker's features see it (initial and medial by (vowel, final), final
    by (lead class, vowel)), fitted to the pieces the source has. A slot without observations gets a zero model."""
    h = prop.shape[2]
    dims = ((21, 28), (21, 28), (max(lead) + 1, 21))
    obs = [[{} for _ in range(dims[s][0])] for s in range(3)]
    for i in range(len(jamo)):
        L, V, T = int(jamo[i, 0]), int(jamo[i, 1]), int(jamo[i, 2])
        for slot in (0, 1):
            b = ink_box(prop[i, slot])
            if b is not None:
                obs[slot][V].setdefault(T, []).append(b)
        if T:
            b = ink_box(prop[i, 2])
            if b is not None:
                obs[2][int(lead[L])].setdefault(V, []).append(b)
    out = []
    for s in range(3):
        o = {}
        for u, col in enumerate(obs[s]):
            for v, bs in col.items():
                o[(u, v)] = np.median(np.array(bs), axis=0)
        out.append(fit_boxes(o, *dims[s]) if o else
                   (np.zeros(4), np.zeros((dims[s][0], 4)), np.zeros((dims[s][1], 4))))
    return out


def fill_pred_box(p, c, tail, boxes):
    """The ranker's layout prediction for context @p c of problem @p p, from the per-slot additive models @p boxes."""
    model = boxes[p.slot]
    if model is None:
        return np.zeros(4)
    mu, a, b = model
    if p.slot == 2:
        return mu + a[c[0]] + b[c[1]]
    u = c[0] if p.slot == 0 else p.key
    ts = [0] if c[1] == 0 else [T for T in range(1, 28) if tail[T] == c[1]]
    return np.median([mu + a[u] + b[T] for T in ts], axis=0)


def group_boxes(p, reps, shape):
    """group -> the ink boxes of its pieces (one per jamo the group shows), for the ranker's candidate features."""
    out = {}
    for g, a in enumerate(reps):
        v = vote_of(p.s[a], p.n[a])
        out[g] = [b for b in (ink_box(v[ji].reshape(shape)) for ji in range(len(p.jamo)) if p.n[a, ji] > 0)
                  if b is not None]
    return out


def fill_candidates(p, c, reps, pboxes, pred, cd, gof, vs, h):
    """One record per candidate group of problem p for context c: the group's piece box against the predicted box,
    the context distance, the sibling vote and structural flags; dmin_rel, boxd_rel and sib_rel are relative to the
    candidate set, and knn1 / knn3 / knn8 are the nearest-neighbour shares."""
    out = []
    sibv = {}                                   # group -> [sum of vote shares, count], one pass over the shown contexts
    for x in gof:
        e = vs.get((c, x) if c < x else (x, c))
        if e and e[1]:
            v = sibv.setdefault(gof[x], [0.0, 0])
            v[0] += e[0] / e[1]
            v[1] += 1
    for g, a in enumerate(reps):
        members = [p.ctx[item] for item in p.mem[a]]
        dmin = min(cd(c, x) for x in members)
        dmean = float(np.mean([cd(c, x) for x in members]))
        bs = pboxes.get(g, [])
        if bs:
            box = np.mean(bs, axis=0)
            bd = float(np.abs(box - pred).sum())
        else:
            box, bd = np.zeros(4), np.nan
        sc, tot = sibv.get(g, [0.0, 0])
        sib = sc / tot if tot else 0.0
        same = 0
        if p.slot == 0:
            same = max((x[0] == c[0]) for x in members)
        elif p.slot == 2:
            same = max((x[1] == c[1]) for x in members)
        out.append(dict(g=g, a=a, n=len(members), dmin=float(dmin), dmean=dmean, box=box, boxd=bd, sib=sib,
                        same=float(same),
                        area=float(sum(b[2] - b[0] + 1 for b in bs) / max(h, 1)) if bs else 0.0))
    if out:
        mean_box = np.mean([o["box"] for o in out], axis=0)
        allmem = sorted((float(cd(c, p.ctx[i])), g) for g, a in enumerate(reps) for i in p.mem[a])
        for o in out:
            o["box_rel"] = o["box"] - mean_box
            for k in (1, 3, 8):
                o["knn%d" % k] = sum(1 for _, gg in allmem[:k] if gg == o["g"]) / float(min(k, len(allmem)))
        dm = np.array([o["dmin"] for o in out])
        l1 = np.array([o["boxd"] for o in out])
        sb = np.array([o["sib"] for o in out])
        for o, x, y, z in zip(out, dm, l1, sb):
            o["dmin_rel"] = float((x - dm.min()) / (dm.max() - dm.min() + 1e-9))
            o["boxd_rel"] = float((y - np.nanmin(l1)) / (np.nanmax(l1) - np.nanmin(l1) + 1e-9)) \
                if np.isfinite(y) else 1.0
            o["sib_rel"] = float(z / (sb.max() + 1e-9))
    return out


def fill_lead_tail(prop, jamo, lead, tail):
    """Per lead class and per tail class, the mean ink box of the source's pieces of the initial / final, normalised
    by the cell side; and the share of syllables without a final."""
    h = prop.shape[2]
    ol = [[] for _ in range(max(lead) + 1)]
    ot = [[] for _ in range(max(tail) + 1)]
    for i in range(len(jamo)):
        b = ink_box(prop[i, 0])
        if b is not None:
            ol[int(lead[int(jamo[i, 0])])].append([(b[3] - b[1] + 1) / h, (b[2] - b[0] + 1) / h,
                                                   (b[3] - b[1] + 1) * (b[2] - b[0] + 1) / h ** 2, b[2] / h])
        T = int(jamo[i, 2])
        b = ink_box(prop[i, 2]) if T else None
        # the width term below is the research code's (b[2] - b[1], not b[3] - b[1]); the ranker was trained with it
        ot[int(tail[T])].append([0, 0, 0, 0] if b is None else
                                [(b[3] - b[1] + 1) / h, (b[2] - b[1] + 1) / h,
                                 (b[3] - b[1] + 1) * (b[2] - b[1] + 1) / h ** 2, b[2] / h])
    mk = lambda v: np.array(v).mean(axis=0) if v else np.zeros(4)  # noqa: E731
    return [mk(v) for v in ol], [mk(v) for v in ot], \
        [float(np.mean([int(jamo[i, 2]) == 0 for i in range(len(jamo))]))]


class FillFeatures:
    """The 60 features of one (context, candidate group) pair, in the fixed research layout: 3 slot one-hot, 21 vowel
    one-hot, 4 predicted box, 4 lead-class stats, 4 tail-class stats, 1 empty-final share, 23 candidate features."""

    def __init__(self, P, prop, boxes=None):
        self.P, self.h = P, prop.shape[2]
        self.boxes = boxes if boxes is not None else fill_boxes(prop, P["jamo"], P["lead"], P["tail"])
        self.ls, self.ts, self.empty = fill_lead_tail(prop, P["jamo"], P["lead"], P["tail"])

    def row(self, p, c, o):
        h = self.h
        V = c[0] if p.slot in (0, 1) else c[1]
        lc = c[0] if p.slot in (1, 2) else max(self.P["lead"])
        tc = c[1] if p.slot in (0, 1) else p.key
        pb = fill_pred_box(p, c, self.P["tail"], self.boxes)
        f = list(np.eye(3)[p.slot]) + [0.0] * 21
        f[3 + V] = 1.0
        f += [pb[0] / h, (pb[2] - pb[0] + 1) / h, (pb[3] - pb[1] + 1) / h, pb[1] / h]
        f += list(self.ls[lc]) + list(self.ts[tc])
        f.append(self.empty[0] if p.slot == 0 else 0.0)
        bx = o["box"]
        f += [o["n"] / 20.0, o["dmin"], o["dmin_rel"], o["dmean"], o["boxd"] / h, o["boxd_rel"], o["sib_rel"],
              o["same"], (bx[0] - pb[0]) / h, (bx[1] - pb[1]) / h, (bx[2] - pb[2]) / h, (bx[3] - pb[3]) / h,
              bx[0] / h, (bx[2] - bx[0] + 1) / h, (bx[3] - bx[1] + 1) / h,
              (bx[3] - bx[1] + 1) * (bx[3] - bx[1] + 1) / h ** 2]
        f += [o["box_rel"][0] / h, o["box_rel"][1] / h, o["box_rel"][2] / h, o["box_rel"][3] / h,
              o["knn1"], o["knn3"], o["knn8"]]
        return f


class Fill:
    """The ranker for one prepared face: `choose(p, c, cands)` returns the group with the highest score, or None when
    the baseline must decide (fewer than two candidates). The feature tables are built on first use, so a face with no
    unseen context (every syllable built) never computes them."""

    def __init__(self, model, P, prop):
        self.model, self.P, self.prop = model, P, prop
        self._F = None

    def features(self):
        if self._F is None:
            self._F = FillFeatures(self.P, self.prop)
        return self._F

    def choose(self, p, c, cands):
        if len(cands) < 2:
            return None
        F = self.features()
        X = np.array([F.row(p, c, o) for o in cands], np.float32)
        return int(cands[int(np.argmax(self.model.score(X)))]["g"])


def pieces_of_groups(problems, prop, gates, dist, lead, tail, stats, boxes=None, fill=None):
    """Per problem: the group of every context (a context no syllable shows takes, when @p fill gives the cross-font
    ranker, the group its model scores highest; else, when @p boxes gives the initial's layout model, the group whose
    pieces sit nearest the box that model predicts; else it joins the group its sibling problems most often put it
    with, else that of the nearest context that has syllables), and a piece for every (group, jamo):
    the vote; where the vote fails a gate, the member proposal nearest to it that passes, else the nearest passing
    piece of the same jamo in another group; where no syllable shows the jamo in the group, the piece of the nearest
    group that has it (a gate-passing one first); where no syllable of the problem shows the jamo at all, none (the
    jamo draws blank; stats["pieces_blank"]). Returns piece {(slot, problem key, group, jamo): bitmap}, users (same
    keys -> syllable rows), group_of {(slot, problem key): {context: group}} and borrowed {key: donor key}."""
    shape = gates.shape
    piece, users, group_of, borrowed = {}, {}, {}, {}
    votes = sibling_votes(problems)
    for p in problems:
        reps = [int(a) for a in np.nonzero(p.alive)[0]] if len(p.full) else []
        cd = context_distance(p, dist, lead, tail)
        gof = {}
        for g, a in enumerate(reps):
            for item in p.mem[a]:
                gof[p.ctx[item]] = g
        have = list(gof)
        vs = votes[p.slot]
        unseen = [c for c in p.ctx if c not in gof]
        pboxes = {}
        if (boxes is not None and p.slot == 0) or (fill is not None and unseen):
            pboxes = group_boxes(p, reps, shape)
        for c in p.ctx:
            if c not in gof:
                stats["contexts_without_syllables"] += 1
                # the cross-font ranker first: it can only choose among the groups the face already stores
                g = None
                if fill is not None and len(reps) >= 2:
                    cands = fill_candidates(p, c, reps, pboxes,
                                            fill_pred_box(p, c, tail, fill.features().boxes), cd, gof, vs, shape[0])
                    g = fill.choose(p, c, cands)
                    if g is not None and not 0 <= g < len(reps):
                        g = None
                if g is not None:
                    gof[c] = g
                    stats["contexts_placed_by_fill"] += 1
                    continue
                # else the baseline: where the slot's ink should sit for this context, from the source's own
                # syllables; the final of the context is known, so the design is not guesswork even when the pair was
                # never drawn
                g = box_placement(c, boxes, tail, pboxes) if boxes is not None and p.slot == 0 else None
                if g is not None:
                    gof[c] = g
                    stats["contexts_placed_by_box"] += 1
                    continue
                # else the group whose contexts the sibling problems most often put this context with (the problem's
                # own grouping is not counted: it does not show the context); then the nearest context
                score = defaultdict(lambda: [0.0, 0])
                for x in have:
                    e = vs.get((c, x) if c < x else (x, c))
                    if e and e[1]:
                        sc = score[gof[x]]
                        sc[0] += e[0] / e[1]
                        sc[1] += 1
                best = max(score.items(), key=lambda kv: (kv[1][0] / kv[1][1], -kv[0])) if score else None
                if best and best[1][0] > 0:
                    gof[c] = best[0]
                    stats["contexts_placed_by_siblings"] += 1
                else:
                    gof[c] = gof[min(have, key=lambda x: (cd(c, x), x))] if have else 0
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
                else:
                    stats["pieces_blank"] += 1      # no syllable of the problem shows this jamo
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
        cache[key] = dict(jamo=jamo, prob=prob, prop=prop, ink=ink, gates=src.gates, dist=src.dist, lead=lead,
                          tail=tail, problems=make_problems(jamo, prob, ink, lead, tail),
                          boxes=box_model(prop, jamo))
    return cache[key]


def drop_prepared(src, rule_name, max_classes):
    """Free the cached problems of one class cap once its builds are done (they dominate memory at large cells)."""
    src.__dict__.get("_prep", {}).pop((rule_name, tuple(max_classes)), None)


def build_face(src, model, rule_name, limits, max_classes, big, jset_version, log=None, tol=None, gate_merges=True,
               fill=None):
    """Build one face; returns (bytes, layout, info). @p tol: the merge tolerance in pixels per syllable (None: the
    default for the cell; 0: no merging beyond the set limits). @p fill: the cross-font group ranker (None: off)."""
    t0 = time.time()
    P = prepare(src, model, rule_name, max_classes)
    jamo, prop, ink, gates, lead, tail = P["jamo"], P["prop"], P["ink"], P["gates"], P["lead"], P["tail"]
    h, w = ink.shape[1:]
    if tol is None:
        tol = default_tol(h)
    stats = Counter()
    group(P["problems"], limits, tol, gates, stats, gate_merges)
    piece, users, group_of, borrowed = pieces_of_groups(P["problems"], prop, gates, P["dist"], lead, tail, stats,
                                                        P["boxes"], Fill(fill, P, prop) if fill is not None else None)
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
    # jamo without a piece in a group their problem uses: no source syllable shows them, so they draw blank
    blank = set()
    for slot, srcs, cls in ((0, init_src, lead), (1, med_src, list(range(21))), (2, fin_src, tail)):
        used = {k: set(group_of[(slot, k)].values()) for k in set(cls) if (slot, k) in group_of}
        for (s, j), v in srcs.items():
            if v is None and s in used.get(cls[j], ()):
                blank.add((slot, j))
    blank = [f"{SLOTS[slot]} {NAMES[slot][j]}" for slot, j in sorted(blank)]
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
                blank_jamo=blank,
                serif_tolerance=gates.frac, gates_off=gates.off,
                lead_classes=["".join(LEADS[L] for L in range(19) if lead[L] == c) for c in range(nlc)],
                tail_classes=["".join(TAILS[T] for T in range(28) if tail[T] == c) for c in range(ntc)],
                stats=dict(stats), seconds=round(time.time() - t0, 1))
    if fill is not None:
        info["fill"] = dict(file=os.path.basename(fill.path), features=FILL_FEATURES, parameters=fill.params,
                            contexts_placed_by_fill=int(stats.get("contexts_placed_by_fill", 0)))
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
            best = max(ok, key=lambda i: (infos[i]["comp_iou"], -infos[i]["bytes"]))
            return best, f"most accurate within {max_bytes} B"
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


def build_default(src, model, rule_name, limits, big, jset_version, log=None, tol=None, classes=None, fill=None):
    """The face at @p limits and one merge tolerance: built for every class cap, the smallest within SLACK composed
    IoU of the most accurate is kept. Returns (bytes, layout, info) with info["choice"]."""
    pts = []
    for mc in class_caps(rule_name, big, classes):
        pts.append(build_face(src, model, rule_name, limits, mc, big, jset_version, log, tol=tol, fill=fill))
        drop_prepared(src, rule_name, mc)
    top = max(p[2]["comp_iou"] for p in pts)
    out, layout, info = min((p for p in pts if p[2]["comp_iou"] >= top - SLACK), key=lambda p: p[2]["bytes"])
    info["choice"] = dict(rule="fixed limits" if len(pts) == 1 else
                          f"the smallest class cap within {SLACK} IoU of the most accurate",
                          tried=[dict(max_classes=p[2]["max_classes"], classes=p[2]["classes"], bytes=p[2]["bytes"],
                                      comp_iou=p[2]["comp_iou"]) for p in pts])
    return out, layout, info


def build_ladder(src, model, rule_name, big, jset_version, max_bytes=None, min_iou=None, log=None, classes=None,
                 fill=None):
    """The --max-bytes / --min-iou ladder: the standard limits at every class cap and every merge tolerance of
    TOL_LADDER (fewer classes and a larger tolerance = a smaller face), and with @p big the BIG limits likewise; the
    point choose_point keeps. @p classes fixes the cap of both halves (clamped to the standard row for the standard
    one). Returns (bytes, layout, info) with info["choice"]."""
    h = src.pre.shape[1]
    std = None if classes is None else tuple(min(c, m) for c, m in zip(classes, LIMITS[False][1]))
    pts = []
    for b, caps, ladder in ((False, class_caps(rule_name, False, std), TOL_LADDER),
                            (True, class_caps(rule_name, True, classes) if big else (), BIG_TOL_LADDER)):
        for mc in caps:
            pts += [build_face(src, model, rule_name, LIMITS[b][0], mc, b, jset_version, log, tol=m * default_tol(h),
                               fill=fill) for m in ladder]
            drop_prepared(src, rule_name, mc)
    pick, why = choose_point([p[2] for p in pts], max_bytes, min_iou)
    out, layout, info = pts[pick]
    info["choice"] = dict(rule=why, ladder=[dict(limits=p[2]["limits"], big=p[2]["big"],
                                                 max_classes=p[2]["max_classes"],
                                                 merge_tolerance_px=p[2]["merge_tolerance_px"], bytes=p[2]["bytes"],
                                                 comp_iou=p[2]["comp_iou"]) for p in pts])
    return out, layout, info


def parse_classes(ap, text, big):
    """--classes LC,TC: the lead / tail class caps, at least 1 lead and 2 tail classes, within the format's row."""
    try:
        c = tuple(int(x) for x in text.split(","))
    except ValueError:
        c = ()
    hi = LIMITS[big][1]
    if len(c) != 2 or not (1 <= c[0] <= hi[0] and 2 <= c[1] <= hi[1]):
        ap.error(f"--classes {text!r}: LC,TC with LC 1..{hi[0]} and TC 2..{hi[1]}"
                 f"{'' if big else ' (--big for more)'}")
    return c


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src_g = ap.add_mutually_exclusive_group(required=True)
    src_g.add_argument("--from-svf", metavar="FACE.SVF",
                       help="a 1 bpp precomposed SVF face (every syllable it holds is used)")
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
    lim.add_argument("--max-bytes", type=int,
                     help="the most accurate face of the tolerance ladder within this many bytes")
    lim.add_argument("--min-iou", type=float,
                     help="the smallest face of the tolerance ladder whose composed IoU reaches this")
    ap.add_argument("--tol", type=float, metavar="PX", help="merge tolerance: groups merge while that adds at most PX "
                    "pixels of disagreement per syllable of the smaller group (default cell height / 12; 0 keeps every "
                    "group the set limits allow). Not with --max-bytes / --min-iou, which walk a ladder of tolerances")
    ap.add_argument("--classes", metavar="LC,TC", help="the caps on lead and tail classes (standard: up to 12,12; "
                    "--big: 19,28; the standard points of a --big ladder take at most 12,12). Default: several caps "
                    "are built and the smallest face within 0.005 composed IoU of the most accurate is kept (a class "
                    "pair costs 63 table bytes). Not with --rule structural")
    ap.add_argument("--big", action="store_true", help="JSET BIG: the tool's default limits become 64/48/32 sets and "
                    "19 x 28 classes (the format's BIG row allows up to 128/128/64; the --max-bytes / --min-iou "
                    "ladder adds BIG points to the standard ones); engines built with SVF_JSET_BIG read it. The "
                    "standard face is the default")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="weights (.npz, tools/jamonet.py format)")
    ap.add_argument("--fill", nargs="?", const=DEFAULT_FILL, default=DEFAULT_FILL, metavar="MODEL.npz",
                    help="choose the group of a context the source never draws with the cross-font ranker "
                    "(tools/models/jamofill-v1.npz by default; 'none' turns it off). It only changes which stored group "
                    "an unseen context joins: bytes, pieces, sets and gates are unchanged")
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
    if a.classes and a.rule == "structural":
        ap.error("--classes: not with --rule structural (its classes are fixed: 7 lead, 4 tail)")
    classes = parse_classes(ap, a.classes, a.big) if a.classes else None
    model = jamonet.Model(a.model)
    fill = None
    if a.fill and a.fill != "none":
        try:
            fill = FillModel(a.fill)
        except (OSError, ValueError) as e:
            ap.error(f"--fill {a.fill}: {e}")
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
        out, layout, info = build_default(src, model, a.rule, limits, a.big, jv, log, a.tol, classes, fill)
    else:
        out, layout, info = build_ladder(src, model, a.rule, a.big, jv, a.max_bytes, a.min_iou, log, classes, fill)
    choice = info["choice"]
    info["source"] = src.info
    info["model"] = dict(file=os.path.basename(a.model), **{k: model.meta.get(k) for k in ("base", "trained")})
    with open(a.output, "wb") as fh:
        fh.write(out)
    ks = (f", KS {info['comp_iou_ks']}" if info.get("comp_iou_ks") is not None
          and info["ks_syllables"] != info["syllables"] else "")
    sets = "/".join(str(x) for x in info["sets"])
    print(f"{a.output}: {info['bytes']} bytes, composed IoU {info['comp_iou']}{ks} ({info['comp_exact']} of "
          f"{info['syllables']} exact), {info['pieces']} pieces, sets {sets}, "
          f"classes {info['classes'][0]}x{info['classes'][1]}{', BIG' if info['big'] else ''}, "
          f"{info['gates_failing']} pieces fail a gate; {choice['rule']}")
    if info["blank_jamo"]:
        print(f"warning: no source syllable shows {', '.join(info['blank_jamo'])}: drawn blank where the face "
              "uses them", file=sys.stderr)
    if a.check:
        print("check:", J.check(out, layout, None))
    if a.report:
        with open(a.report, "w") as fh:
            json.dump(info, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
