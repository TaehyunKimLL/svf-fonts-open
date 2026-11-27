#!/usr/bin/env python3
"""jamohybrid.py - a jamo-set face from a precomposed one by a learned split (docs/jamo-split.md, the learned split).

Like `jamoset.py --from-svf` / `--from-ttf`, it builds a jamo set (JSET) whose composed syllables follow a precomposed
face. Unlike the pixel fit it also gets the split right: which pixels are the initial, the medial and the final.

  1. Proposals. A per-pixel model (tools/jamonet.py, weights tools/models/jamohybrid-v1.npz) gives every syllable's
     initial / medial / final planes, conditioned on the syllable's jamo.
  2. Sets, top-down. Structural sets: initial = vowel group x final present, medial = initial class x final kind, final =
     vowel group. Then greedy splits by one initial, vowel or final while the set and class limits allow (standard JSET:
     32 / 24 / 16 sets, 12 x 12 classes; --big: 64 / 48 / 32, 19 x 28).
  3. Pieces, bottom-up. A (set, jamo) piece is the per-pixel majority of its syllables' proposals weighted by the model's
     probabilities. Pieces of one jamo merge (inside a coarse class) when the merged piece passes the identity gates and
     no syllable's error grows past max(1, cell / 12) px. Then jamofit re-fits the pieces to the precomposed syllables,
     each pixel only in a slot the model gave it.
  4. Identity gates (hard): enough ink and extent; holes (ㅁ ㅂ ㅇ ㅎ ㅃ have one, ㄱ ㄴ ㄷ ㄹ ㅅ ㅈ ㅋ none); the ticks of
     ㅏ ㅑ ㅓ ㅕ ㅣ and the stubs of ㅗ ㅛ ㅜ ㅠ ㅡ, with a serif tolerance; ㅅ and ㅈ slant. Each check is on where at least
     90 % of the face's own proposals pass it. A failing vote is replaced by the nearest proposal that passes, a merge
     that would fail is not made, a failing re-fit keeps the vote.
  5. Contexts no source syllable shows take the piece of the structurally nearest set (same vowel class and final kind
     first, then vowel group, then the nearest initial), gated like the others.

  python3 tools/jamohybrid.py --from-svf FACE.SVF -o OUT.SVF [--max-bytes N | --min-iou X | --limits NI,NM,NF]
  python3 tools/jamohybrid.py --from-ttf FONT --size N [--cell WxH] [--baseline R] -o OUT.SVF ...
  options: --big (BIG limits; default off), --rule derived|structural, --model PATH, --report OUT.json, --check,
           --jset-version 1|2|auto, --pylib DIR (a directory holding numpy, also $JAMOSET_PYLIB)

Without --max-bytes / --min-iou / --limits the standard face at 32 / 24 / 16 is built. --max-bytes and --min-iou walk a
ladder of set limits (standard: 16/21/8 ... 32/24/16; --big: 40/30/20 ... 96/72/48) and keep the most accurate face within
the bytes, or the smallest that reaches the composed IoU. Needs numpy (and freetype-py for --from-ttf); not torch.
"""

import argparse
import json
import os
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
V_VERT, V_HORZ = set("ㅏㅐㅑㅒㅓㅔㅕㅖㅣ"), set("ㅗㅛㅜㅠㅡ")
VG8 = ["ㅏㅑㅓㅕㅣ", "ㅐㅒㅔㅖ", "ㅗㅛㅡ", "ㅜㅠ", "ㅘㅚㅢ", "ㅙ", "ㅝㅟ", "ㅞ"]
LEAD7 = ["ㄱㄲㅋ", "ㄴㄷㅅ", "ㄸㄹㅌ", "ㅁㅂㅇㅈ", "ㅃㅆㅉ", "ㅊㅎ", "ㅍ"]
COMPLEX = set("ㄳㄵㄶㄺㄻㄼㄽㄾㄿㅀㅄ")
LIMITS = {False: ((32, 24, 16), (12, 12)), True: ((64, 48, 32), (19, 28))}
LADDER = {False: [(16, 21, 8), (20, 22, 10), (24, 22, 12), (28, 23, 14), (32, 24, 16)],
          True: [(40, 30, 20), (48, 36, 24), (64, 48, 32), (80, 60, 40), (96, 72, 48)]}
AXES = ("initial", "vowel", "final")


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


def vclass(V):
    c = VOWELS[V]
    return "vert" if c in V_VERT else "horz" if c in V_HORZ else "mix"


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
    bg = np.pad(1 - a, 1).astype(bool)
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


# ---- rules -------------------------------------------------------------------------------------------------------

def structural_rule():
    vg = [next(g for g, s in enumerate(VG8) if v in s) for v in VOWELS]
    lc = [next(g for g, s in enumerate(LEAD7) if c in s) for c in LEADS]
    tk = [0] + [1 if t in "ㄴㅅ" else 3 if t in COMPLEX else 2 for t in TAILS[1:]]
    return vg, lc, tk


def cluster(profiles, n):
    """Average-linkage clustering (L1) of a few profiles into @p n groups, numbered by first appearance."""
    m = len(profiles)
    groups = [[i] for i in range(m)]
    d = np.abs(profiles[:, None, :] - profiles[None, :, :]).sum(axis=2)
    while len(groups) > n:
        best = None
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                v = d[np.ix_(groups[a], groups[b])].mean()
                if best is None or v < best[0]:
                    best = (v, a, b)
        _, a, b = best
        groups[a] += groups[b]
        del groups[b]
    lab = [0] * m
    for g, mem in enumerate(groups):
        for i in mem:
            lab[i] = g
    ids = {}
    return [ids.setdefault(x, len(ids)) for x in lab]


def derived_rule(jamo, prob):
    """Vowel groups (8), initial classes (7), final kinds (none + 3) from the face's own proposals."""
    n, _, h, w = prob.shape

    def means(key_a, key_b, slot, na, nb):
        out = np.zeros((nb, na, h * w))
        cnt = np.zeros((nb, na))
        for i in range(n):
            out[jamo[i, key_b], jamo[i, key_a]] += prob[i, slot].reshape(-1)
            cnt[jamo[i, key_b], jamo[i, key_a]] += 1
        mm = out / np.maximum(cnt, 1)[..., None]
        for a in range(na):
            have = cnt[:, a] > 0
            if have.any():
                mm[~have, a] = mm[have, a].mean(axis=0)
        return mm.reshape(nb, -1)
    vg = cluster(means(0, 1, 0, 19, 21), 8)
    lc = cluster(means(1, 0, 1, 21, 19), 7)
    out = np.zeros((28, 21, 2 * h * w))
    cnt = np.zeros((28, 21))
    for i in range(n):
        out[jamo[i, 2], jamo[i, 1]] += prob[i, :2].reshape(-1)
        cnt[jamo[i, 2], jamo[i, 1]] += 1
    mm = out / np.maximum(cnt, 1)[..., None]
    for v in range(21):
        have = cnt[1:, v] > 0
        if have.any():
            mm[1:][~have, v] = mm[1:][have, v].mean(axis=0)
    tk = [0] + [c + 1 for c in cluster(mm[1:].reshape(27, -1), 3)]
    return vg, lc, tk


class Rule:
    """Sets per raw context: aset[k][(L, V, T)] -> set (k = 2 only T > 0); coarse[k][set] the class merges stay in."""

    def __init__(self, vg, lc, tk):
        self.vg, self.lc7, self.tk = vg, lc, tk
        mk = sorted(set(min(t, 2) for t in tk))
        mk_of = {t: mk.index(min(t, 2)) for t in set(tk)}
        self.aset = [{}, {}, {}]
        self.coarse = [{}, {}, {}]
        for L in range(19):
            for V in range(21):
                for T in range(28):
                    i = vg[V] * 2 + (T > 0)
                    m = lc[L] * len(mk) + mk_of[tk[T]]
                    self.aset[0][(L, V, T)] = i
                    self.aset[1][(L, V, T)] = m
                    self.coarse[0].setdefault(i, (vclass(V), T > 0))
                    self.coarse[1].setdefault(m, T > 0)
                    if T:
                        self.aset[2][(L, V, T)] = vg[V]
                        self.coarse[2].setdefault(vg[V], vclass(V))
        self.splits = []

    def sets(self, L, V, T):
        k = (L, V, T)
        return (self.aset[0][k], self.aset[1][k], self.aset[2][k] if T else -1)

    def counts(self):
        return tuple(len(set(a.values())) for a in self.aset)

    def classes(self):
        sigL = [tuple(self.aset[k][(L, V, T)] for k in range(3) for V in range(21) for T in range(28) if k < 2 or T)
                for L in range(19)]
        sigT = [(T == 0,) + tuple(self.aset[k][(L, V, T)] for k in range(3) for L in range(19) for V in range(21)
                                  if k < 2 or T) for T in range(28)]
        ids, idt = {}, {}
        lc = [ids.setdefault(s, len(ids)) for s in sigL]
        tc = [idt.setdefault(s, len(idt)) for s in sigT]
        return lc, len(ids), tc, len(idt)

    def renumber(self):
        for k in range(3):
            ids = {}
            for key in sorted(self.aset[k]):
                ids.setdefault(self.aset[k][key], len(ids))
            self.aset[k] = {key: ids[v] for key, v in self.aset[k].items()}
            self.coarse[k] = {ids[v]: c for v, c in self.coarse[k].items() if v in ids}


# ---- votes, splits, merges ---------------------------------------------------------------------------------------

def vote(users, ink, prob, k):
    pk = prob[users, k]
    ik = ink[users].astype(np.float32)
    return ((ik * pk).sum(0) > ((1 - ik) + ik * (1 - pk)).sum(0)).astype(np.uint8)


def err(piece, props):
    return (piece[None] != props).sum(axis=(1, 2))


def refine(rule, jamo, prop, prob, ink, limits, max_classes):
    """Top-down splits within the limits; returns the best split the budget refused per slot."""
    keys = [tuple(int(v) for v in x) for x in jamo]
    cache, refused = {}, {}

    def cost(k, idx):
        byj = defaultdict(list)
        for i in idx:
            byj[keys[i][k]].append(i)
        tot = 0
        for j, us in byj.items():
            ck = (k, j, tuple(us))
            if ck not in cache:
                u = np.array(us)
                cache[ck] = int(err(vote(u, ink, prob, k), prop[u, k]).sum())
            tot += cache[ck]
        return tot

    def members_of(k):
        m = defaultdict(list)
        for i, key in enumerate(keys):
            if not (k == 2 and key[2] == 0):
                m[rule.aset[k][key]].append(i)
        return m

    def candidates(k, members):
        out = []
        for sid, idx in members.items():
            base = cost(k, idx)
            if base == 0:
                continue
            for ax in range(3):
                vals = sorted({keys[i][ax] for i in idx})
                if len(vals) < 2:
                    continue
                for v in vals:
                    A = [i for i in idx if keys[i][ax] == v]
                    B = [i for i in idx if keys[i][ax] != v]
                    gain = base - cost(k, A) - cost(k, B)
                    if gain > 0:
                        out.append((gain, k, sid, ax, v))
        return out

    while True:
        cands = []
        for k in range(3):
            if rule.counts()[k] < limits[k]:
                cands += candidates(k, members_of(k))
        if not cands:
            break
        cands.sort(reverse=True)
        applied = False
        for gain, k, sid, ax, v in cands:
            new = max(rule.aset[k].values()) + 1
            moved = [key for key, s in rule.aset[k].items() if s == sid and key[ax] == v]
            for key in moved:
                rule.aset[k][key] = new
            _, nl, _, nt = rule.classes()
            if nl > max_classes[0] or nt > max_classes[1]:
                for key in moved:
                    rule.aset[k][key] = sid
                refused.setdefault("classes", dict(gain_px=gain, slot=SLOTS[k], axis=AXES[ax], value=NAMES[ax][v]))
                continue
            rule.coarse[k][new] = rule.coarse[k][sid]
            rule.splits.append((SLOTS[k], AXES[ax], NAMES[ax][v], int(gain)))
            applied = True
            break
        if not applied:
            break
    for k in range(3):
        if rule.counts()[k] >= limits[k]:
            c = candidates(k, members_of(k))
            if c:
                g = max(c)
                refused[SLOTS[k]] = dict(gain_px=int(g[0]), axis=AXES[g[3]], value=NAMES[g[3]][g[4]])
    rule.renumber()
    return refused


def build_pieces(jamo, prop, prob, ink, rule, gates, tol, stats):
    users = defaultdict(list)
    for i, (L, V, T) in enumerate(jamo):
        for k, s in enumerate(rule.sets(int(L), int(V), int(T))):
            if s >= 0:
                users[(k, s, (int(L), int(V), int(T))[k])].append(i)
    piece = {}
    for key, us in users.items():
        k, s, j = key
        us = np.array(us)
        v = vote(us, ink, prob, k)
        name = NAMES[k][j]
        if not gates.ok(k, name, v):
            stats["vote_gate_fail"] += 1
            e = err(v, prop[us, k])
            for i in np.argsort(e, kind="stable"):
                if gates.ok(k, name, prop[us[i], k]):
                    v = prop[us[i], k].copy()
                    stats["vote_replaced_by_proposal"] += 1
                    break
            else:
                stats["vote_gate_fail_kept"] += 1
        piece[key] = v
    # bottom-up merges inside coarse classes
    groups = defaultdict(list)
    for (k, s, j) in piece:
        groups[(k, j, rule.coarse[k][s])].append(s)

    def users_of(k, sets, j):
        return [i for s in sets for i in users[(k, s, j)]]
    for (k, j, _), sets in groups.items():
        name = NAMES[k][j]
        clusters = {s: [s] for s in sets}
        cur = {s: piece[(k, s, j)] for s in sets}
        bad = set()
        while True:
            reps = list(clusters)
            cands = sorted((int((cur[x] != cur[y]).sum()), x, y) for i, x in enumerate(reps) for y in reps[i + 1:]
                           if (x, y) not in bad)
            if not cands:
                break
            dist, ra, rb = cands[0]
            members = clusters[ra] + clusters[rb]
            us = np.array(users_of(k, members, j))
            merged = cur[ra] if dist == 0 else vote(us, ink, prob, k)
            ok = gates.ok(k, name, merged)
            if ok and dist:
                before = np.concatenate([err(cur[ra], prop[np.array(users_of(k, clusters[ra], j)), k]),
                                         err(cur[rb], prop[np.array(users_of(k, clusters[rb], j)), k])])
                ok = bool((err(merged, prop[us, k]) <= np.maximum(tol, before)).all())
            if not ok:
                bad.add((ra, rb))
                stats["merge_refused"] += 1
                continue
            clusters[ra] = members
            del clusters[rb]
            cur[ra] = merged
            del cur[rb]
            bad = {pr for pr in bad if ra not in pr and rb not in pr}
            stats["merges"] += 1
        for r, mem in clusters.items():
            for s in mem:
                piece[(k, s, j)] = cur[r]
    return piece, users


def refit(piece, users, prop, ink, gates, stats, passes=12):
    """Re-fit the grouped pieces to the precomposed syllables (jamofit.fit_pieces), each piece confined to the pixels
    its users' proposals or its vote give that slot."""
    import jamofit as JF
    h, w = ink.shape[1:]
    weights = 1 << np.arange(w - 1, -1, -1, dtype=object)

    def to_g(a):
        return JF.from_rows([int((a[y].astype(object) * weights).sum()) for y in range(h)], w)
    keyid, members = {}, defaultdict(list)
    for key, a in piece.items():
        kid = (key[0], key[2], a.tobytes())
        keyid[key] = kid
        members[kid].append(key)
    syl = {}
    for (k, s, j), us in users.items():
        for i in us:
            syl.setdefault(i, [None, None, None])[k] = keyid[(k, s, j)]
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


def fallback_piece(rule, piece, gates, lead_prof, k, s, j):
    """The piece of jamo j in slot k for a set no source syllable reaches, from the structurally nearest set."""
    def summary(sid):
        ctx = [key for key, v in rule.aset[k].items() if v == sid and key[k] == j]
        return (set((vclass(V), rule.tk[T]) for L, V, T in ctx), set(rule.vg[V] for _, V, _ in ctx),
                set(L for L, _, _ in ctx))
    tgt = summary(s)
    cands = []
    for (kk, sid, jj), a in piece.items():
        if kk != k or jj != j:
            continue
        c = summary(sid)
        lead_d = min((float(np.abs(lead_prof[x] - lead_prof[y]).sum()) for x in tgt[2] for y in c[2]), default=1e9)
        cands.append(((0 if tgt[0] & c[0] else 1, 0 if tgt[1] & c[1] else 1, round(lead_d, 3), sid), a))
    cands.sort(key=lambda x: x[0])
    for _, a in cands:
        if gates.ok(k, NAMES[k][j], a):
            return a, True
    return (cands[0][1], False) if cands else (None, False)


# ---- one face ------------------------------------------------------------------------------------------------------

class Source:
    """The precomposed syllables: syl (N,) indices, pre (N, h, w), plus what the written face keeps (base, extra)."""

    def __init__(self, syl, pre, ascent, base=None, extra=None, advance=None, info=None):
        self.syl, self.pre, self.ascent = syl, pre, ascent
        self.base, self.extra, self.advance, self.info = base, extra, advance, info or {}


def from_svf(path):
    data = open(path, "rb").read()
    f = J.parse_svfn(data)
    if f.bpp != 1 or f.flags & J.FLAG_JAMO:
        raise SystemExit(f"{path}: not a 1 bpp precomposed face")
    w, h = f.cell_w, f.cell_h
    nb = (w + 7) // 8
    syl, pre = [], []
    for cp in sorted(f.glyphs):
        if 0xAC00 <= cp <= 0xD7A3 and any(f.glyphs[cp]):
            g = f.glyphs[cp]
            rows = [int.from_bytes(g[y * nb:(y + 1) * nb], "big") >> (nb * 8 - w) for y in range(h)]
            pre.append([[(r >> (w - 1 - x)) & 1 for x in range(w)] for r in rows])
            syl.append(cp - 0xAC00)
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


def build_face(src, model, rule_name, limits, max_classes, big, jset_version, log=None):
    """Build one face; returns (bytes, layout, info)."""
    import jamonet
    t0 = time.time()
    jamo = np.array([lvt(int(s)) for s in src.syl], np.int64)
    if not hasattr(src, "_pred"):
        src._pred = jamonet.predict(model, src.pre, jamo)
    prob, prop = src._pred
    ink = src.pre.astype(np.uint8)
    h, w = ink.shape[1:]
    tol = max(1, round(h / 12))
    gates = Gates(jamo, prop)
    rule = Rule(*(structural_rule() if rule_name == "structural" else derived_rule(jamo, prob)))
    stats = Counter()
    refused = refine(rule, jamo, prop, prob, ink, limits, max_classes)
    piece, users = build_pieces(jamo, prop, prob, ink, rule, gates, tol, stats)
    refit(piece, users, prop, ink, gates, stats)
    lead_prof = np.zeros((19, h * w))
    for L in range(19):
        sel = jamo[:, 0] == L
        if sel.any():
            lead_prof[L] = prop[sel, 0].reshape(int(sel.sum()), -1).mean(axis=0)
    lc, nlc, tc, ntc = rule.classes()
    ni, nm, nf = rule.counts()
    bitmaps, index, memo, fb = [], {}, {}, Counter()

    def idx(a):
        key = a.tobytes()
        if key not in index:
            index[key] = len(bitmaps)
            bitmaps.append(a)
        return index[key]

    def srcp(k, s, j):
        if (k, s, j) in piece:
            return idx(piece[(k, s, j)])
        if (k, s, j) not in memo:
            if not any(v == s and key[k] == j for key, v in rule.aset[k].items()):
                memo[(k, s, j)] = None
            else:
                a, ok = fallback_piece(rule, piece, gates, lead_prof, k, s, j)
                fb["gated" if ok else "gate_failed"] += 1
                memo[(k, s, j)] = None if a is None else idx(a)
        return memo[(k, s, j)]
    repL = {c: lc.index(c) for c in range(nlc)}
    repT = {c: tc.index(c) for c in range(ntc)}
    init_src = {(s, L): srcp(0, s, L) for s in range(ni) for L in range(19)}
    med_src = {(s, V): srcp(1, s, V) for s in range(nm) for V in range(21)}
    fin_src = {(s, T): srcp(2, s, T) for s in range(nf) for T in range(1, 28)}
    layout = J.Layout("hybrid", None, nlc, ntc, ni, nm, nf, lambda L: lc[L], lambda T: tc[T],
                      lambda c, V, t: rule.aset[0][(repL[c], V, repT[t])],
                      lambda c, V, t: rule.aset[1][(repL[c], V, repT[t])],
                      lambda c, V, t: rule.aset[2][(repL[c], V, repT[t])] if repT[t] else 0,
                      lambda s, L: init_src[(s, L)], lambda s, V: med_src[(s, V)], lambda s, T: fin_src[(s, T)])

    class Pieces:
        def __init__(self):
            self.w, self.h, self.count = w, h, len(bitmaps)

        def glyph(self, i):
            return J.Glyph(w, h, [int("".join("1" if x else "0" for x in r), 2) for r in bitmaps[i]])
    out, _, _ = J.build_from_source(layout, Pieces(), None, src.base, src.ascent, src.extra, src.base is not None,
                                    src.advance, jset_version=jset_version, jset_big=big)
    # quality of the written face against the source
    f = J.parse_svfn(out)
    t = J.unpack(f.jset)
    nb = (w + 7) // 8
    inter = union = exact = 0
    ious = []
    for i, s in enumerate(src.syl):
        c = J.compose(f, t, 0xAC00 + int(s))
        a = np.array([[(int.from_bytes(c[y * nb:(y + 1) * nb], "big") >> (nb * 8 - 1 - x)) & 1 for x in range(w)]
                      for y in range(h)], bool)
        b = ink[i].astype(bool)
        u = (a | b).sum()
        ious.append((a & b).sum() / u if u else 1.0)
        exact += bool((a == b).all())
    info = dict(limits=list(limits), max_classes=list(max_classes), big=big, rule=rule_name, sets=[ni, nm, nf],
                classes=[nlc, ntc], bytes=len(out), comp_iou=round(float(np.mean(ious)), 4), comp_exact=int(exact),
                syllables=len(src.syl), serif_tolerance=gates.frac, gates_off=gates.off, splits=len(rule.splits),
                refused_by_budget=refused, fallback=dict(fb), stats=dict(stats), seconds=round(time.time() - t0, 1))
    if log:
        log(f"limits {limits}: {len(out)} bytes, IoU {info['comp_iou']}, sets {ni}/{nm}/{nf}, classes {nlc}x{ntc}")
    return out, layout, info


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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src_g = ap.add_mutually_exclusive_group(required=True)
    src_g.add_argument("--from-svf", metavar="FACE.SVF", help="a 1 bpp precomposed SVF face")
    src_g.add_argument("--from-ttf", metavar="FONT", help="an outline font rendered at --size (as jamoset.py)")
    ap.add_argument("--size", type=int, help="--from-ttf: pixel size")
    ap.add_argument("--cell", help="--from-ttf: cell WxH (default SIZExSIZE)")
    ap.add_argument("--baseline", type=int, help="--from-ttf: baseline row")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--rule", choices=("derived", "structural"), default="derived",
                    help="derived (default): groups learned from the face's own proposals; structural: fixed groups")
    lim = ap.add_mutually_exclusive_group()
    lim.add_argument("--limits", help="set limits NI,NM,NF (default 32,24,16; with --big 64,48,32)")
    lim.add_argument("--max-bytes", type=int, help="the most accurate face of the limit ladder within this many bytes")
    lim.add_argument("--min-iou", type=float, help="the smallest face of the limit ladder whose composed IoU reaches this")
    ap.add_argument("--big", action="store_true", help="JSET BIG limits (64/48/32 sets, 19 x 28 classes; engines with "
                    "SVF_JSET_BIG); the standard face is the default")
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
    model = jamonet.Model(a.model)
    if a.from_svf:
        src = from_svf(a.from_svf)
    else:
        cell = tuple(int(x) for x in a.cell.lower().split("x")) if a.cell else None
        src = from_ttf(a.from_ttf, a.size, cell, a.baseline, a.pylib)
    max_classes = LIMITS[a.big][1]
    jv = a.jset_version if a.jset_version == "auto" else int(a.jset_version)
    log = lambda m: print(m, file=sys.stderr)  # noqa: E731
    if a.max_bytes is None and a.min_iou is None:
        limits = tuple(int(x) for x in a.limits.split(",")) if a.limits else LIMITS[a.big][0]
        out, layout, info = build_face(src, model, a.rule, limits, max_classes, a.big, jv, log)
        choice = dict(rule="fixed limits")
    else:
        pts = [build_face(src, model, a.rule, lim_, max_classes, a.big, jv, log) for lim_ in LADDER[a.big]]
        pick, why = choose_point([p[2] for p in pts], a.max_bytes, a.min_iou)
        out, layout, info = pts[pick]
        choice = dict(rule=why, ladder=[dict(limits=p[2]["limits"], bytes=p[2]["bytes"], comp_iou=p[2]["comp_iou"])
                                        for p in pts])
    info["choice"] = choice
    info["source"] = src.info
    info["model"] = dict(file=os.path.basename(a.model), **{k: model.meta.get(k) for k in ("base", "trained")})
    with open(a.output, "wb") as fh:
        fh.write(out)
    print(f"{a.output}: {info['bytes']} bytes, composed IoU {info['comp_iou']} ({info['comp_exact']} of "
          f"{info['syllables']} exact), sets {info['sets'][0]}/{info['sets'][1]}/{info['sets'][2]}, classes "
          f"{info['classes'][0]}x{info['classes'][1]}{', BIG' if a.big else ''}; {choice['rule']}")
    if a.check:
        print("check:", J.check(out, layout, None))
    if a.report:
        with open(a.report, "w") as fh:
            json.dump(info, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
