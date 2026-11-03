#!/usr/bin/env python3
"""Mac HangulTalk 7.1.x type-3 'fbit' jamo-plane fonts -> SVF v3 jamo-set (조합형) faces (card t_1dc5bd99).

The fonts (Seoul12, AppleGothic12/24, AppleMyungjo12/24) hold 482 glyph slots (2 banks x 241) and no rules: every
KS X 1001 syllable has a 4-byte entry [bank][g1][g2][g3] in InputBackSupport 'HTBL' 1 (glyph = (bank-1)*241 + g - 0x0f,
g 0x00 / 0x0e = no plane; the planes are OR-ed). Only the 2,350 KS syllables and the 51 compatibility jamo exist.
Format notes: johab-fonts notes/mac.md, "HangulTalk 7.1.x jamo-plane fbit (type 3)". No Apple byte is in this
repository; the tool reads the user's own decoded copies.

What a JSET block can express (spec/SVF.md, "Jamo-set fonts"): the initial piece is a function of (initial, vowel,
tail class), the medial of (vowel, lead class, tail class), the final of (tail, lead class, vowel), with at most 12
lead and 12 tail classes and 32 / 24 / 16 sets. The Mac table picks its medial (and the ㄱ ㄹ ㅇ finals) by the
initial too finely for 12 lead classes when every Mac slot is one piece (``slot_conflicts``), so the pieces are built
from the Mac planes with residual transfer (``Model``):

  * medial piece of a cell (V, lc, tc) = AND of the Mac medial glyphs of the cell's KS syllables;
  * final piece of a cell (T, lc, V)   = AND of the Mac final glyphs of the cell's KS syllables;
  * initial piece of a cell (L, V, tc) = OR over the cell's syllables of (syllable - medial piece - final piece),
    i.e. the Mac initial plus what the shared medial / final pieces leave out (the lead-specific vowel strokes).
    A syllable is exact when that OR stays inside every syllable of the cell; ``search_classes`` looks for lead and
    tail classes (<= 12 each) under which all 2,350 are exact, recomposition being the only test.

Syllables outside KS X 1001 (8,822) are extrapolated, never presented as Mac output (``extrapolate``):
  * regular: every one of its three cells holds a KS syllable, so each piece is the one those cells already use;
  * guess: some cell holds no KS syllable; that slot is filled from the nearest observed context with *plain* Mac
    glyphs (initial: the same initial with the most similar vowel; medial: the same vowel in the most similar lead
    class; final: the same tail with the most similar vowel, then the most similar lead class), and the syllable is
    listed as a guess. A slot with no candidate at all stays blank (counted).

  python3 tools/macfbit_svf.py analyse FBIT.bin HTBL1.bin [-o OUT.json]
  python3 tools/macfbit_svf.py build FBIT.bin HTBL1.bin -o FACE.SVF [--latin FONT.bin] [--jset-version 1|2|auto]
  python3 tools/macfbit_svf.py verify FACE.SVF FBIT.bin HTBL1.bin

Pure Python; the output is a function of the input bytes.
"""

import argparse
import itertools
import json
import os
import struct
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jamoset as J  # noqa: E402
import macfbit3 as M3  # noqa: E402

LEADS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
VOWELS = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
TAILS = "-ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
N = 11172
BANK = 241
CLASS_LIMIT = 12
SET_LIMITS = (32, 24, 16)


def syl(n):
    return n // 588, (n // 28) % 21, n % 28


# ---- Mac input ---------------------------------------------------------------------------------------------------

class Fbit3:
    """A type-3 'fbit' resource: ``h`` (cell = h x h), ``glyphs[i]`` an int of h*h bits, row-major, MSB first
    (bit (h*h - 1 - (y*h + x)) is pixel (x, y))."""

    def __init__(self, data):
        if data[2:6] != b"fbit":
            raise ValueError("not an 'fbit' resource")
        if struct.unpack(">H", data[0x0c:0x0e])[0] != 3:
            raise ValueError("not a type-3 (jamo-plane lookup) fbit")
        self.h = struct.unpack(">H", data[0x16:0x18])[0]
        self.gb = (self.h * self.h + 7) // 8
        base = 0x4e + 6 * struct.unpack(">H", data[0x4c:0x4e])[0]
        n = (len(data) - base) // self.gb
        pad = self.gb * 8 - self.h * self.h
        self.glyphs = [int.from_bytes(data[base + i * self.gb:base + (i + 1) * self.gb], "big") >> pad
                       for i in range(n)]


class Htbl1:
    """InputBackSupport 'HTBL' 1: ``compat[k]`` (U+3131 + k) and ``syllables[n]`` (U+AC00 + n, KS only) as lists of
    glyph numbers per plane (None = no plane), plane order initial, medial, final."""

    def __init__(self, data):
        l1 = struct.unpack(">I", data[:4])[0]
        t1, t2 = data[4:4 + l1], data[8 + l1:]

        def entry(t, i):
            e = t[i * 4:i * 4 + 4]
            return tuple(None if g in (0, 0x0e) else (e[0] - 1) * BANK + g - 0x0f for g in e[1:])
        self.compat = {}
        for k in range(51):
            ch = bytes([0xa4, 0xa1 + k]).decode("euc_kr")
            self.compat[ord(ch) - 0x3131] = entry(t1, k)
        self.syllables = {}
        for i in range(2350):
            ch = bytes([0xb0 + i // 94, 0xa1 + i % 94]).decode("euc_kr")
            self.syllables[ord(ch) - 0xAC00] = entry(t2, i)


def mac_compose(fb, planes):
    out = 0
    for g in planes:
        if g is not None:
            out |= fb.glyphs[g]
    return out


def mac_planes(fb, ht):
    """{n: (I, M, F)} Mac plane bitmaps (0 for no plane) of the KS syllables."""
    return {n: tuple(0 if g is None else fb.glyphs[g] for g in e) for n, e in ht.syllables.items()}


# ---- slot-exact test (every Mac slot one piece) -------------------------------------------------------------------

def slot_conflicts(fb, ht):
    """Lead pairs that cannot share a lead class when every distinct Mac glyph bitmap is one piece: same vowel and
    tail, different medial or final bitmap. Returns {(a, b): count}; with all 171 pairs present no lead classes can be
    merged at all (19 > 12)."""
    S = {syl(n): tuple(fb.glyphs[g] if g is not None else None for g in e) for n, e in ht.syllables.items()}
    conf = Counter()
    for V in range(21):
        for T in range(28):
            ls = [L for L in range(19) if (L, V, T) in S]
            for a, b in itertools.combinations(ls, 2):
                A, B = S[a, V, T], S[b, V, T]
                if A[1] != B[1] or (T and A[2] != B[2]):
                    conf[a, b] += 1
    return conf


# ---- cell model with residual transfer ----------------------------------------------------------------------------

class Model:
    """Pieces of the KS syllables under lead classes @p lc and tail classes @p tc (see the module doc)."""

    def __init__(self, planes, lc, tc):
        self.planes, self.lc, self.tc = planes, list(lc), list(tc)
        full = -1
        mi, fi = defaultdict(lambda: full), defaultdict(lambda: full)
        for n, (I, M, F) in planes.items():
            L, V, T = syl(n)
            mi[self.mkey(L, V, T)] &= M
            if T:
                fi[self.fkey(L, V, T)] &= F
        self.med, self.fin = dict(mi), dict(fi)
        ini, cap = defaultdict(int), defaultdict(lambda: full)
        for n, (I, M, F) in planes.items():
            L, V, T = syl(n)
            s = I | M | F
            k = self.ikey(L, V, T)
            ini[k] |= s & ~self.med[self.mkey(L, V, T)] & ~(self.fin[self.fkey(L, V, T)] if T else 0)
            cap[k] &= s
        self.ini = dict(ini)
        self.bad = sorted(n for n, (I, M, F) in planes.items() if self.ini[self.ikey(*syl(n))] & ~cap[self.ikey(*syl(n))])

    def ikey(self, L, V, T):
        return (L, V, self.tc[T])

    def mkey(self, L, V, T):
        return (V, self.lc[L], self.tc[T])

    def fkey(self, L, V, T):
        return (T, self.lc[L], V)

    def compose(self, n):
        L, V, T = syl(n)
        return (self.ini[self.ikey(L, V, T)] | self.med[self.mkey(L, V, T)]
                | (self.fin[self.fkey(L, V, T)] if T else 0))

    def residual(self):
        """Pixels the initial pieces carry beyond the Mac initial planes (summed over cells)."""
        tot = 0
        for n, (I, M, F) in self.planes.items():
            tot += bin(self.ini[self.ikey(*syl(n))] & ~I).count("1")
        return tot


def _renumber(p):
    m = {}
    return [m.setdefault(c, len(m)) for c in p]


def search_classes(planes, log=None, max_lc=CLASS_LIMIT, max_tc=CLASS_LIMIT):
    """Agglomerative: start from 19 lead and 28 tail classes (every KS syllable exact), merge the pair that keeps
    the most syllables exact (ties: the fewest residual pixels, then the fewest distinct pieces) while a merge loses
    nothing (no syllable, no residual pixel) or a class count is above its limit. Returns (lc, tc)."""
    lc, tc = list(range(19)), list(range(28))

    def score(lc_, tc_):
        m = Model(planes, lc_, tc_)
        return (len(m.bad), m.residual(), len(set(m.ini.values())) + len(set(m.med.values())) + len(set(m.fin.values())))
    cur = score(lc, tc)
    while True:
        cands = []
        for kind, P in (("lc", lc), ("tc", tc)):
            ids = sorted(set(P))
            for a, b in itertools.combinations(ids, 2):
                if kind == "tc" and 0 in (a, b) and P[0] in (a, b):
                    continue                      # "no tail" stays its own class
                Q = _renumber([a if x == b else x for x in P])
                s = score(Q, tc) if kind == "lc" else score(lc, Q)
                cands.append((s, kind, Q))
        if not cands:
            break
        over = [c for c in cands if (c[1] == "lc" and max(lc) + 1 > max_lc) or (c[1] == "tc" and max(tc) + 1 > max_tc)]
        pool = over if over else [c for c in cands if c[0][:2] <= cur[:2]]
        if not pool:
            break
        s, kind, Q = min(pool, key=lambda c: c[0])
        if kind == "lc":
            lc = Q
        else:
            tc = Q
        cur = s
        if log:
            log("merge %s -> %d lead x %d tail classes, %d not exact, residual %d px, %d pieces" % (
                kind, max(lc) + 1, max(tc) + 1, s[0], s[1], s[2]))
    return lc, tc


def set_demand(m, limits=SET_LIMITS):
    """Sets the observed rows of Model @p m need per table (as Build clusters them): (NI, NM, NF)."""
    I_obs, M_obs, F_obs = (defaultdict(lambda: defaultdict(dict)) for _ in range(3))
    for (L, V, b), p in m.ini.items():
        I_obs[m.lc[L]][m.lc[L], V, b][L] = p
    for (V, a, b), p in m.med.items():
        M_obs[V][a, V, b][V] = p
    for (T, a, V), p in m.fin.items():
        F_obs[m.tc[T]][a, V, m.tc[T]][T] = p
    return tuple(max([len(cluster(d, lim)[1]) for d in obs.values()] or [1])
                 for obs, lim in ((I_obs, limits[0]), (M_obs, limits[1]), (F_obs, limits[2])))


def fit_limits(planes, lc, tc, limits=SET_LIMITS, log=None, max_rounds=40):
    """Local search after search_classes when a table needs more sets than its limit: move one initial or one tail
    to another class (lead classes stay <= 12, "no tail" stays alone) and keep the move with the smallest
    (syllables not exact, sets over the limits, residual pixels) until nothing is over. Returns (lc, tc, demand)."""
    def cost(lc_, tc_):
        m = Model(planes, lc_, tc_)
        if m.bad:
            return (len(m.bad), 0, 0), None
        d = set_demand(m, limits)
        return (0, sum(max(0, x - l) for x, l in zip(d, limits)), m.residual()), d
    cur, dem = cost(lc, tc)
    for _ in range(max_rounds):
        if cur[1] == 0:
            break
        best = None
        for kind, P in (("lc", lc), ("tc", tc)):
            for e in range(len(P)):
                if kind == "tc" and e == 0:
                    continue
                for k in sorted(set(P)):
                    if k == P[e] or (kind == "tc" and k == P[0]):
                        continue
                    Q = list(P)
                    Q[e] = k
                    Q = _renumber(Q)
                    c, d = cost(Q, tc) if kind == "lc" else cost(lc, Q)
                    if best is None or c < best[0]:
                        best = (c, d, kind, Q)
        if best is None or best[0] >= cur:
            break
        cur, dem, kind, Q = best
        if kind == "lc":
            lc = Q
        else:
            tc = Q
        if log:
            log("fit: %s -> %d x %d classes, sets %s, cost %s" % (kind, max(lc) + 1, max(tc) + 1, dem, cur))
    return lc, tc, dem


def class_names(p, names):
    out = defaultdict(str)
    for e, c in enumerate(p):
        out[c] += names[e]
    return [out[c] for c in sorted(out)]


# ---- extrapolation and the JSET tables ----------------------------------------------------------------------------

def cluster(rows, limit):
    """@p rows {cell: {col: piece}} (observed entries) -> ({cell: set index}, [merged partial rows], [member cells per
    set], within @p limit). Rows that agree wherever both are defined merge, the pair with the most common entries
    first; then, while over @p limit, the compatible pair with the fewest member cells."""
    cl = [(dict(r), [c]) for c, r in sorted(rows.items(), key=lambda kv: (-len(kv[1]), kv[0]))]

    def agree(x, y):
        common = x.keys() & y.keys()
        if any(x[k] != y[k] for k in common):
            return -1
        return len(common)
    while True:
        best = None
        for i, j in itertools.combinations(range(len(cl)), 2):
            g = agree(cl[i][0], cl[j][0])
            if g > 0 and (best is None or g > best[0]):
                best = (g, i, j)
        if best is None:
            break
        _, i, j = best
        cl[i][0].update(cl[j][0])
        cl[i][1].extend(cl[j][1])
        del cl[j]
    while len(cl) > limit:                 # forced: the compatible pair with the fewest member cells
        best = None
        for i, j in itertools.combinations(range(len(cl)), 2):
            if agree(cl[i][0], cl[j][0]) >= 0:
                k = (len(cl[i][1]) + len(cl[j][1]), i, j)
                if best is None or k < best:
                    best = k
        if best is None:
            break
        _, i, j = best
        cl[i][0].update(cl[j][0])
        cl[i][1].extend(cl[j][1])
        del cl[j]
    where = {c: k for k, (_, cs) in enumerate(cl) for c in cs}
    return where, [r for r, _ in cl], [cs for _, cs in cl], len(cl) <= limit


class Build:
    """The full 11,172-syllable assignment of a font under (lc, tc), and its JSET tables.

    Sets per domain (initial: a lead class; medial: a vowel; final: a tail class): a cell (lead class, vowel, tail
    class) brings the pieces its KS syllables fix (a partial row); rows that agree wherever both are defined merge,
    the pair with the most agreeing entries first (``_cluster``); rows with no common entry merge only while the
    domain is over its set limit. A cell with no KS syllable joins the set of its nearest observed cell (initial: the
    same lead and tail class with the most similar vowel; medial: the same vowel and tail class with the most similar
    lead class; final: the same lead and tail class with the most similar vowel). An entry no merged row defines is
    filled once per set with plain Mac glyphs from the nearest observed context (``_guess_*``).

    Per syllable ``status``: "ks" (Mac table); "regular" (each of its cells - its class combination per slot - holds
    KS syllables, so its set is the observed one, and the set fixes its jamo from KS data: the selector applied as a
    function of (lead class, vowel, tail class) and the piece as a function of the jamo within the set); "guess" (a
    cell no KS syllable reaches, so the nearest cell's set, or a jamo the set had to be filled with). ``strict``
    counts the regular syllables whose three pieces each come from a KS syllable of the very same cell."""

    def __init__(self, fb, ht, lc, tc, limits=SET_LIMITS):
        self.fb, self.ht, self.h, self.limits = fb, ht, fb.h, limits
        self.planes = mac_planes(fb, ht)
        self.m = m = Model(self.planes, lc, tc)
        self.lc, self.tc = m.lc, m.tc
        self.nlc, self.ntc = max(lc) + 1, max(tc) + 1
        self.t0 = self.tc[0]
        self.leads_of = [[L for L in range(19) if self.lc[L] == a] for a in range(self.nlc)]
        self.tails_of = [[T for T in range(1, 28) if self.tc[T] == b] for b in range(self.ntc)]
        macI, cM, cF = {}, defaultdict(Counter), defaultdict(Counter)
        for n, (I, M, F) in self.planes.items():
            L, V, T = syl(n)
            macI[L, V, T > 0] = I
            cM[m.mkey(L, V, T)][M] += 1
            if T:
                cF[m.fkey(L, V, T)][F] += 1
        self.macI, self.cM, self.cF = macI, cM, cF
        self.simVI = self._sim([((L, tp), V, I) for (L, V, tp), I in macI.items()])
        self.simAM = self._sim([((V, b), a, p) for (V, a, b), p in m.med.items()])
        self.simVF = self._sim([((T, a), V, p) for (T, a, V), p in m.fin.items()])
        self.over = []
        self._sets()
        self._assign()

    @staticmethod
    def _sim(items):
        by = defaultdict(dict)
        for ctx, k, v in items:
            by[ctx][k] = v
        sim = Counter()
        for d in by.values():
            for a, b in itertools.permutations(d, 2):
                sim[a, b] += 1 if d[a] == d[b] else -1
        return sim

    # -- sets --

    def _cluster(self, rows, limit, name):
        where, merged, cells, ok = cluster(rows, limit)
        if not ok:
            self.over.append(name)
        return where, merged, cells

    def _sets(self):
        m = self.m
        I_obs, M_obs, F_obs = (defaultdict(lambda: defaultdict(dict)) for _ in range(3))
        for (L, V, b), p in m.ini.items():
            I_obs[self.lc[L]][self.lc[L], V, b][L] = p
        for (V, a, b), p in m.med.items():
            M_obs[V][a, V, b][V] = p
        for (T, a, V), p in m.fin.items():
            F_obs[self.tc[T]][a, V, self.tc[T]][T] = p
        self.obs = {"i": I_obs, "m": M_obs, "f": F_obs}
        self.iset, self.irows, self.icells = {}, {}, {}
        self.mset, self.mrows, self.mcells = {}, {}, {}
        self.fset, self.frows, self.fcells = {}, {}, {}
        for a in range(self.nlc):
            self.iset[a], self.irows[a], self.icells[a] = self._cluster(I_obs[a], self.limits[0], "initial %d" % a)
        for V in range(21):
            self.mset[V], self.mrows[V], self.mcells[V] = self._cluster(M_obs[V], self.limits[1], "medial %d" % V)
        for b in range(self.ntc):
            if self.tails_of[b]:
                self.fset[b], self.frows[b], self.fcells[b] = self._cluster(F_obs[b], self.limits[2], "final %d" % b)
        self.guessed = {"i": 0, "m": 0, "f": 0}
        self.near = {"i": 0, "m": 0, "f": 0}
        self.filled = set()
        # entries no merged row defines: filled per set from the set's largest member cell
        for a in range(self.nlc):
            for s, row in enumerate(self.irows[a]):
                a_, V, b = self.icells[a][s][0]
                for L in self.leads_of[a]:
                    if L not in row:
                        row[L] = self._guess_i(L, V, b)
                        self.guessed["i"] += 1
                        self.filled.add(("i", a, s, L))
        for b, rows in self.frows.items():
            for s, row in enumerate(rows):
                a, V, b_ = self.fcells[b][s][0]
                for T in self.tails_of[b]:
                    if T not in row:
                        row[T] = self._guess_f(T, a, V)
                        self.guessed["f"] += 1
                        self.filled.add(("f", b, s, T))

    def _guess_i(self, L, V, b):
        tp = b != self.t0
        cands = [V2 for V2 in range(21) if (L, V2, tp) in self.macI]
        if not cands:
            return 0
        V2 = min(cands, key=lambda x: (-self.simVI[V, x], abs(V - x), x))
        g = self.macI[L, V2, tp]
        mk = (V, self.lc[L], b)
        if mk in self.m.med:                       # complete the shared medial piece to a whole Mac medial glyph
            g |= self.cM[mk].most_common(1)[0][0] & ~self.m.med[mk]
        return g

    def _guess_f(self, T, a, V):
        c = [(-self.simVF[V, V2], abs(V - V2), 0, (T, a, V2)) for V2 in range(21) if (T, a, V2) in self.cF]
        c += [(1 << 20, abs(a - a2), 0, (T, a2, V)) for a2 in range(self.nlc) if (T, a2, V) in self.cF]
        c += [(1 << 21, 0, -sum(cnt.values()), kk) for kk, cnt in self.cF.items() if kk[0] == T]
        return self.cF[min(c)[3]].most_common(1)[0][0] if c else 0

    def _near(self, kind, a, V, b):
        """The set of a cell no KS syllable fixes: that of the nearest observed cell."""
        tp = b != self.t0
        if kind == "i":
            w = self.iset[a]
            c = [(0, -self.simVI[V, V2], abs(V - V2), (a, V2, b)) for V2 in range(21) if (a, V2, b) in w]
            c += [(1, -self.simVI[V, V2], abs(V - V2), (a, V2, b2)) for V2 in range(21) for b2 in range(self.ntc)
                  if (a, V2, b2) in w and (b2 != self.t0) == tp]
        elif kind == "m":
            w = self.mset[V]
            c = [(0, -self.simAM[a, a2], abs(a - a2), (a2, V, b)) for a2 in range(self.nlc) if (a2, V, b) in w]
            c += [(1, 0, abs(b - b2), (a, V, b2)) for b2 in range(self.ntc) if (a, V, b2) in w and (b2 != self.t0) == tp]
            c += [(2, 0, 0, k) for k in w]
        else:
            w = self.fset[b]
            c = [(0, -self.simVF[V, V2], abs(V - V2), (a, V2, b)) for V2 in range(21) if (a, V2, b) in w]
            c += [(1, -self.simVF[V, V2], abs(a - a2), (a2, V2, b)) for a2 in range(self.nlc) for V2 in range(21)
                  if (a2, V2, b) in w]
        return w[min(c)[3]] if c else 0

    def set_of(self, kind, a, V, b):
        w = {"i": self.iset[a] if kind == "i" else None, "m": self.mset[V] if kind == "m" else None,
             "f": self.fset.get(b) if kind == "f" else None}[kind]
        if (a, V, b) in w:
            return w[a, V, b], True
        key = (kind, a, V, b)
        if key not in self._nearc:
            self._nearc[key] = self._near(kind, a, V, b)
            self.near[kind] += 1
        return self._nearc[key], False

    # -- per syllable --

    def _assign(self):
        self._nearc = {}
        self.pieces, self.status = [None] * N, [None] * N
        self.strict = 0
        for n in range(N):
            L, V, T = syl(n)
            a, b = self.lc[L], self.tc[T]
            si, oi = self.set_of("i", a, V, b)
            sm, om = self.set_of("m", a, V, b)
            i = self.irows[a][si][L]
            mm = self.mrows[V][sm][V]
            reg = oi and om and ("i", a, si, L) not in self.filled
            strict = (L, V, b) in self.m.ini and (V, a, b) in self.m.med
            f = 0
            if T:
                sf, of = self.set_of("f", a, V, b)
                f = self.frows[b][sf][T]
                reg = reg and of and ("f", b, sf, T) not in self.filled
                strict = strict and (T, a, V) in self.m.fin
            self.pieces[n] = (i, mm, f)
            if n in self.planes:
                self.status[n] = "ks"
            else:
                self.status[n] = "regular" if reg else "guess"
                self.strict += strict

    def composed(self, n):
        i, m, f = self.pieces[n]
        return i | m | f

    def tables(self):
        """(jamoset.Tables with piece numbers, [piece bitmaps by number])."""
        ni = max(len(r) for r in self.irows.values())
        nm = max(len(r) for r in self.mrows.values())
        nf = max([len(r) for r in self.frows.values()] or [1])
        t = J.Tables(self.nlc, self.ntc, ni, nm, nf)
        t.lead_class, t.tail_class = list(self.lc), list(self.tc)
        images, num = [], {}

        def piece(img):
            if not img:
                return J.BLANK
            if img not in num:
                num[img] = len(images)
                images.append(img)
            return num[img]
        for a in range(self.nlc):
            for V in range(21):
                for b in range(self.ntc):
                    cell = (a * 21 + V) * self.ntc + b
                    t.init_set[cell] = self.set_of("i", a, V, b)[0]
                    t.med_set[cell] = self.set_of("m", a, V, b)[0]
                    t.fin_set[cell] = self.set_of("f", a, V, b)[0] if self.tails_of[b] else 0
        for a, rows in self.irows.items():
            for s, row in enumerate(rows):
                for L in self.leads_of[a]:
                    t.init_piece[s * 19 + L] = piece(row[L])
        for V, rows in self.mrows.items():
            for s, row in enumerate(rows):
                t.med_piece[s * 21 + V] = piece(row[V])
        for b, rows in self.frows.items():
            for s, row in enumerate(rows):
                for T in self.tails_of[b]:
                    t.fin_piece[s * 27 + T - 1] = piece(row[T])
        self.sets = (ni, nm, nf)
        return t, images

    def counts(self):
        c = Counter(self.status)
        return {"ks": c["ks"], "regular": c["regular"], "regular_strict": self.strict, "guess": c["guess"],
                "filled_entries": dict(self.guessed),
                "cells_from_nearest": dict(self.near), "over_limit_domains": list(self.over)}


# ---- compatibility jamo -------------------------------------------------------------------------------------------

def compat_assign(t, images, compat_bitmaps):
    """Point t.compat at a piece where the Mac compatibility glyph is a piece its natural table holds for that jamo
    (v1 and v2 both read it then); returns {k: bitmap} of the ones stored whole."""
    num = {img: i for i, img in enumerate(images)}
    whole = {}
    for k, img in compat_bitmaps.items():
        p = num.get(img)
        ok = False
        if p is not None:
            kind, j = J.COMPAT[k]
            if kind == "i":
                ok = any(t.init_piece[s * 19 + j] == p for s in range(t.ni))
                alt = J.COMPAT_FINAL_ALT[k]
                ok = ok or (alt is not None and any(t.fin_piece[s * 27 + alt - 1] == p for s in range(t.nf)))
            elif kind == "v":
                ok = any(t.med_piece[s * 21 + j] == p for s in range(t.nm))
            else:
                ok = any(t.fin_piece[s * 27 + j - 1] == p for s in range(t.nf))
        if ok:
            t.compat[k] = p
        else:
            t.compat[k] = J.BLANK
            whole[k] = img
    return whole


# ---- Latin from the family's 'NFNT' strike ------------------------------------------------------------------------

def resource_fork(data):
    """{(type, id): bytes} of a Macintosh resource fork."""
    doff, moff, _, mlen = struct.unpack(">IIII", data[:16])
    m = data[moff:moff + mlen]
    tl = struct.unpack(">H", m[24:26])[0]
    nt = struct.unpack(">H", m[tl:tl + 2])[0] + 1
    out = {}
    for i in range(nt):
        typ, cnt, ro = struct.unpack(">4sHH", m[tl + 2 + i * 8:tl + 10 + i * 8])
        for j in range(cnt + 1):
            rid, _, attr_off = struct.unpack(">hHI", m[tl + ro + j * 12:tl + ro + j * 12 + 8])
            off = doff + (attr_off & 0xFFFFFF)
            ln = struct.unpack(">I", data[off:off + 4])[0]
            out[typ.decode("mac_roman"), rid] = data[off + 4:off + 4 + ln]
    return out


def nfnt_for_size(fork, size):
    """The 'NFNT' (or 'FONT') bytes the family's 'FOND' associates with point size @p size (plain style)."""
    for (typ, _), b in fork.items():
        if typ != "FOND":
            continue
        n = struct.unpack(">H", b[52:54])[0] + 1
        for i in range(n):
            sz, style, rid = struct.unpack(">HHH", b[54 + i * 6:60 + i * 6])
            if sz == size and style == 0:
                for t in ("NFNT", "FONT"):
                    if (t, rid) in fork:
                        return fork[t, rid]
    raise ValueError("no plain %d point strike in the family" % size)


def nfnt_glyphs(b, chars=range(0x20, 0x7F)):
    """{cp: (pen_x, advance, ascent, rows)} of a Mac bitmap font record: rows (strike height) of pixel lists,
    pen_x the column of the first pixel relative to the pen."""
    (_, first, last, _, kern, _, _, frh, _, asc, _, _, rw) = struct.unpack(">HHHHhhHHHHHHH", b[:26])
    img = b[26:26 + rw * 2 * frh]
    nloc = last - first + 3
    lo = 26 + rw * 2 * frh
    loc = struct.unpack(">%dH" % nloc, b[lo:lo + 2 * nloc])
    ow = struct.unpack(">%dH" % nloc, b[lo + 2 * nloc:lo + 4 * nloc])
    out = {}
    for c in chars:
        if not first <= c <= last or ow[c - first] == 0xFFFF:
            continue
        i = c - first
        x0, x1 = loc[i], loc[i + 1]
        rows = []
        for y in range(frh):
            r = int.from_bytes(img[y * rw * 2:(y + 1) * rw * 2], "big")
            rows.append([(r >> (rw * 16 - 1 - x)) & 1 for x in range(x0, x1)])
        out[c] = ((ow[i] >> 8) + kern, ow[i] & 0xFF, asc, rows)
    return out


def latin_cells(glyphs, cell, ascent):
    """Place each strike glyph in a cell x cell box with its baseline at row @p ascent, moved by a per-glyph dy when
    its ink would leave the cell. Returns ({cp: (bitmap int, advance, dy)}, notes): a glyph wider than the cell or
    starting left of the pen is shifted into it (noted); a glyph taller than the cell is clipped (noted)."""
    out, notes = {}, []
    for cp, (pen_x, adv, asc, rows) in sorted(glyphs.items()):
        pix = [(pen_x + x, y - asc) for y, r in enumerate(rows) for x, p in enumerate(r) if p]  # y rel. baseline
        if not pix:
            out[cp] = (0, min(adv, 255), 0)
            continue
        xs, ys = [p[0] for p in pix], [p[1] for p in pix]
        dx = 0
        if min(xs) < 0:
            dx = -min(xs)
        elif max(xs) >= cell:
            dx = max(cell - 1 - max(xs), -min(xs))
        if dx:
            notes.append("U+%04X %r shifted %+d px" % (cp, chr(cp), dx))
        top, bot = ascent + min(ys), ascent + max(ys)        # rows in the cell at dy 0
        dy = 0
        if bot > cell - 1:
            dy = bot - (cell - 1)                    # stored higher, drawn lower
        elif top < 0:
            dy = top                                 # stored lower, drawn higher
        if bot - top + 1 > cell:
            notes.append("U+%04X %r clipped (%d rows)" % (cp, chr(cp), bot - top + 1))
        v = 0
        for x, y in pix:
            X, Y = x + dx, ascent + y - dy
            if 0 <= X < cell and 0 <= Y < cell:
                v |= 1 << (cell * cell - 1 - (Y * cell + X))
        out[cp] = (v, adv, dy)
    return out, notes


# ---- the face -----------------------------------------------------------------------------------------------------

def cell_bytes(v, h):
    """A cell-sized h*h bitmap int (MSB first) as SVF rows: ceil(h/8) bytes per row, MSB first."""
    nb = (h + 7) // 8
    out = bytearray()
    for y in range(h):
        row = (v >> (h * h - (y + 1) * h)) & ((1 << h) - 1)
        out += (row << (nb * 8 - h)).to_bytes(nb, "big")
    return bytes(out)


def _ink(v, h):
    cols = [x for x in range(h) if any(v >> (h * h - 1 - (y * h + x)) & 1 for y in range(h))]
    return (cols[0], cols[-1] - cols[0] + 1) if cols else (0, 0)


def default_ascent(h):
    """Baseline row of the face: 10 of 12 (20 of 24); the Hangul cell keeps 1/6 of its height below the baseline."""
    return h - h // 6


def face_glyphs(build, latin=None, jset_version=1, jset_big=False):
    """(rows for jamoset.write_svfn, jset block, dy {cp: dy}, parts {name: [cp]}, tables)."""
    h = build.h
    t, images = build.tables()
    compat_bm = {k: mac_compose(build.fb, e) for k, e in build.ht.compat.items()}
    whole = compat_assign(t, images, compat_bm)
    packed = J.pack_jset(t, jset_version, jset_big)
    glyphs, dy, parts = {}, {}, {"pieces": [], "compat": [], "latin": []}
    for i, img in enumerate(images):
        ix, iw = _ink(img, h)
        glyphs[J.PIECE_BASE + i] = (cell_bytes(img, h), h, ix, iw)
        parts["pieces"].append(J.PIECE_BASE + i)
    for k, img in whole.items():
        ix, iw = _ink(img, h)
        glyphs[0x3131 + k] = (cell_bytes(img, h), h, ix, iw)
        parts["compat"].append(0x3131 + k)
    for cp, (v, adv, d) in (latin or {}).items():
        ix, iw = _ink(v, h)
        glyphs[cp] = (cell_bytes(v, h), adv, ix, iw)
        parts["latin"].append(cp)
        if d:
            dy[cp] = d
    rows = [(cp, g[0], g[1], g[2], g[3]) for cp, g in sorted(glyphs.items())]
    rows = sorted(J.renumber_glyphs(rows, packed.piece_map))
    return rows, packed.block, dy, parts, t


def write_face(build, latin=None, jset_version=1, ascent=None, jset_big=False):
    rows, block, dy, parts, t = face_glyphs(build, latin, jset_version, jset_big)
    data = J.write_svfn(build.h, build.h, default_ascent(build.h) if ascent is None else ascent, rows, block, dy=dy)
    return data, parts


def size_table(data):
    """Bytes of the face by part: header, cmap, jset, metrics, offset table, glyph records of the pieces / the
    compatibility jamo stored whole / the rest (Latin), padding."""
    hdr = struct.unpack_from(J.HEADER3, data)
    count, data_off, data_size, cmap_off, jset_off, jset_size, tab_off = (hdr[7], hdr[15], hdr[16], hdr[17], hdr[18],
                                                                           hdr[19], hdr[20])
    met_off = hdr[14]
    f = J._parse_v3(data)
    rec, off32 = f.layout[0], f.layout[3]
    offs = struct.unpack_from("<%d%s" % (count + 1, "I" if off32 else "H"), data, tab_off)
    shift = 0 if off32 else rec
    cps = sorted(struct.unpack_from("<II", data, cmap_off + 8 * i) for i in range(count))
    by = Counter()
    for cp, gi in cps:
        sz = (offs[gi + 1] - offs[gi]) << shift
        by["pieces" if cp >= J.PIECE_BASE else ("compat" if 0x3131 <= cp <= 0x3163 else "latin")] += sz
    out = {"total": len(data), "header": J.HEADER3_SIZE, "cmap": 8 * count, "jset": jset_size,
           "metrics": 4 * count if met_off else 0, "offsets": (count + 1) * (4 if off32 else 2),
           "pieces": by["pieces"], "compat": by["compat"], "latin": by["latin"], "glyph_data": data_size,
           "n_pieces": sum(1 for cp, _ in cps if cp >= J.PIECE_BASE)}
    out["padding"] = out["total"] - sum(out[k] for k in ("header", "cmap", "jset", "metrics", "offsets", "pieces",
                                                         "compat", "latin"))
    return out


def verify(data, build):
    """Compose every syllable from the face (jamoset.compose, the engine's rule) and compare: KS syllables with the Mac
    composition, all 11,172 with the build's own assignment. Returns {"ks_bad": [...], "all_bad": [...],
    "compat_bad": [...]}."""
    f = J.parse_svfn(data)
    t = J.unpack(f.jset)
    h = build.h
    ks_bad, all_bad = [], []
    for n in range(N):
        got = J.compose(f, t, 0xAC00 + n)
        if n in build.planes and got != cell_bytes(mac_compose(build.fb, build.ht.syllables[n]), h):
            ks_bad.append(n)
        if got != cell_bytes(build.composed(n), h):
            all_bad.append(n)
    compat_bad = []
    for k, e in build.ht.compat.items():
        want = cell_bytes(mac_compose(build.fb, e), h)
        p = t.compat[k]
        got = f.glyphs.get(J.PIECE_BASE + p) if p != J.BLANK else f.glyphs.get(0x3131 + k)
        if got != want:
            compat_bad.append(k)
    return {"ks_bad": ks_bad, "all_bad": all_bad, "compat_bad": compat_bad}


def cverify(face_path, build, svfdump):
    """The C renderer's view (c/tests/svfdump.c "syllables": U+AC00..U+D7A3 then U+3131..U+3163, then one byte
    svf_is_jamo) against the Mac composition (KS) and the build (all). {"ks_bad", "all_bad", "compat_bad", "is_jamo"}."""
    import subprocess
    out = subprocess.run([svfdump, face_path, "syllables"], capture_output=True, check=True).stdout
    h = build.h
    st = ((h + 7) // 8) * h
    if len(out) != (N + 51) * st + 1:
        raise ValueError("svfdump syllables: %d bytes, expected %d" % (len(out), (N + 51) * st + 1))
    ks_bad, all_bad, compat_bad = [], [], []
    for n in range(N):
        got = out[n * st:(n + 1) * st]
        if n in build.planes and got != cell_bytes(mac_compose(build.fb, build.ht.syllables[n]), h):
            ks_bad.append(n)
        if got != cell_bytes(build.composed(n), h):
            all_bad.append(n)
    for k, e in build.ht.compat.items():
        if out[(N + k) * st:(N + k + 1) * st] != cell_bytes(mac_compose(build.fb, e), h):
            compat_bad.append(k)
    return {"ks_bad": ks_bad, "all_bad": all_bad, "compat_bad": compat_bad, "is_jamo": out[-1]}


# ---- direct mode: the Mac structure as a JMAP block (JSET version 3) ----------------------------------------------

_KIND_PLANE = {"i": 0, "v": 1, "f": 2}


def direct_jmap(fb, ht, dedup=True):
    """The JMAP block's content for the Mac planes: pieces per plane in slot order (initial, medial, final; a slot
    belongs to the plane its syllables reference it in; one slot in two planes is a ValueError), byte-identical bitmaps of
    one plane folded when @p dedup (PR-8; never across planes), entries for the 2,350 KS syllables (field = piece index
    in the plane + 1, 0 = no plane; kept literally, PR-9), compat per PR-10: an entry with one plane is a piece of the
    plane of its jamo's kind (copied there when the plane does not hold it), more than one plane (or none) leaves the
    block entry blank (the caller stores the OR whole at U+3131 + k). Returns (Jmap, {piece number: slot})."""
    used = [set(), set(), set()]
    for n, e in ht.syllables.items():
        for p, g in enumerate(e):
            if g is not None:
                used[p].add(g)
    for k, e in ht.compat.items():                # a one-plane compat jamo sits in its kind's plane
        gs = [g for g in e if g is not None]
        if len(gs) == 1:
            used[_KIND_PLANE[J.COMPAT[k][0]]].add(gs[0])
    for a in range(3):
        for b in range(a + 1, 3):
            both = used[a] & used[b]
            if both:
                raise ValueError("Mac slot %d is referenced in plane %d and plane %d: not a plane-disjoint font"
                                 % (min(both), a, b))
    pieces = [[], [], []]            # per plane: slot of each piece
    where = [{}, {}, {}]             # per plane: slot -> piece index
    folded = [{}, {}, {}]            # per plane: bitmap -> piece index (dedup)

    def add(plane, g):
        if g in where[plane]:
            return where[plane][g]
        key = fb.glyphs[g]
        if dedup and key in folded[plane]:
            where[plane][g] = folded[plane][key]
            return where[plane][g]
        where[plane][g] = len(pieces[plane])
        folded[plane].setdefault(key, len(pieces[plane]))
        pieces[plane].append(g)
        return where[plane][g]

    for plane in range(3):
        for g in sorted(used[plane]):
            add(plane, g)
    entries = {n: tuple(0 if g is None else add(p, g) + 1 for p, g in enumerate(e))
               for n, e in sorted(ht.syllables.items())}
    single = {}
    for k, e in ht.compat.items():
        gs = [g for g in e if g is not None]
        if len(gs) == 1:
            single[k] = add(_KIND_PLANE[J.COMPAT[k][0]], gs[0])
    pi, pm, pf = (len(x) for x in pieces)
    offs = (0, pi, pi + pm)
    block_compat = [J.BLANK] * 51
    for k, idx in single.items():
        block_compat[k] = offs[_KIND_PLANE[J.COMPAT[k][0]]] + idx
    jm = J.Jmap(fb.h, pi, pm, pf, {n: e for n, e in entries.items()}, block_compat)
    return jm, {offs[p] + i: g for p in range(3) for i, g in enumerate(pieces[p])}


def write_direct(fb, ht, latin=None, dedup=True, with_jset=None, ascent=None, jset_version=1, jset_big=False):
    """The face of the Mac structure itself: a JMAP block (JSET version 3) over the Mac slots as pieces; no extrapolation
    (the other 8,822 syllables are not composed) unless @p with_jset, a derived ``Build``, whose JSET (@p jset_version 1
    or 2) is the fallback, its pieces numbered above the JMAP's (shift_pieces + pack_fallback) and its compat entries
    blank. Returns (face bytes, {"pieces": [cp], "compat": [cp], "latin": [cp], "slots": {piece: slot}, "jmap": bytes,
    "fallback": bytes or None})."""
    h = fb.h
    jm, slots = direct_jmap(fb, ht, dedup)
    total = jm.pi + jm.pm + jm.pf
    glyphs, dy = {}, {}
    parts = {"pieces": [], "compat": [], "latin": []}
    for piece, slot in slots.items():
        img = fb.glyphs[slot]
        ix, iw = _ink(img, h)
        glyphs[J.PIECE_BASE + piece] = (cell_bytes(img, h), h, ix, iw)
        parts["pieces"].append(J.PIECE_BASE + piece)
    for k, e in ht.compat.items():
        if jm.block_compat[k] == J.BLANK:
            img = mac_compose(fb, e)
            ix, iw = _ink(img, h)
            glyphs[0x3131 + k] = (cell_bytes(img, h), h, ix, iw)
            parts["compat"].append(0x3131 + k)
    for cp, (v, adv, d) in (latin or {}).items():
        ix, iw = _ink(v, h)
        glyphs[cp] = (cell_bytes(v, h), adv, ix, iw)
        parts["latin"].append(cp)
        if d:
            dy[cp] = d
    fallback = None
    if with_jset is not None:
        t, images = with_jset.tables()
        t = J.shift_pieces(t, total)
        t.compat = [J.BLANK] * 51                      # the Mac compat is the JMAP's own or stored whole
        t.advance = jm.advance
        if jset_version == "auto":
            jset_version = J.choose_jset_version(t, jset_big)
        fallback = J.pack_fallback(t, jset_version, big=jset_big)
        named = {p for lst in (t.init_piece, t.med_piece, t.fin_piece) for p in lst if p != J.BLANK}
        for p in sorted(named):
            img = images[p - total]
            ix, iw = _ink(img, h)
            glyphs.setdefault(J.PIECE_BASE + p, (cell_bytes(img, h), h, ix, iw))
            parts["pieces"].append(J.PIECE_BASE + p)
    block = J.pack_jmap(jm, fallback)
    rows = sorted((cp, g[0], g[1], g[2], g[3]) for cp, g in glyphs.items())
    data = J.write_svfn(h, h, default_ascent(h) if ascent is None else ascent, rows, block, dy=dy)
    return data, dict(parts, slots=slots, jmap=block, fallback=fallback)


def _mac_cells(fbit, htbl):
    """{cp: cell bytes} of every code macfbit3's composer knows (the 51 compat jamo, the 2,350 KS syllables)."""
    m3 = M3.Fbit3(fbit, htbl)
    nb = (m3.h + 7) // 8
    out = {}
    for hi, lo in m3.codes():
        rows = m3.compose(hi, lo)
        out[ord(bytes([hi, lo]).decode("euc_kr"))] = b"".join(
            (r << (nb * 8 - m3.h)).to_bytes(nb, "big") for r in rows)
    return out


def verify_direct(data, fb_bytes, htbl_bytes):
    """Every code of ``macfbit3.Fbit3(fbit, htbl).compose`` (2,350 KS + 51 compat) against the face composed the engine's
    way (jamoset.compose of the JMAP; a compat entry's piece, else its whole glyph). {"ks_bad": [cp], "compat_bad": [cp],
    "non_ks_present": syllables outside KS the face has pieces for (a JMAP entry or a fallback hit; the C report's
    "non_ks_ink" counts the ones that draw ink instead)}."""
    f = J.parse_svfn(data)
    jm = J.unpack(f.jset)
    if not isinstance(jm, J.Jmap):
        raise ValueError("not a JMAP (version 3) face")
    if jm.list_mode:
        raise ValueError("verify: a LIST face (JSET version 3 flag 0x08) is not a direct-mode face")
    want = _mac_cells(fb_bytes, htbl_bytes)
    ks_bad, compat_bad = [], []
    for cp, w in want.items():
        if cp < 0xAC00:
            p = jm.compat[cp - 0x3131]
            got = f.glyphs.get(J.PIECE_BASE + p) if p != J.BLANK else f.glyphs.get(cp)
            if got != w:
                compat_bad.append(cp)
        elif J.compose(f, jm, cp) != w:
            ks_bad.append(cp)
    ks = {cp for cp in want if cp >= 0xAC00}
    present = sum(1 for cp in range(0xAC00, 0xD7A4) if cp not in ks and jm.pieces(cp) is not None)
    return {"ks_bad": ks_bad, "compat_bad": compat_bad, "non_ks_present": present}


def cverify_direct(face_path, fb_bytes, htbl_bytes, svfdump, opts=()):
    """The same through the C reader (svfdump "syllables", built with -DSVF_JMAP=1; @p opts e.g. ("--stream=4:512",)).
    {"ks_bad", "compat_bad", "non_ks_ink" (non-KS syllables whose cell has ink; python's "non_ks_present" counts pieces), "is_jamo"}."""
    import subprocess
    want = _mac_cells(fb_bytes, htbl_bytes)
    h = struct.unpack(">H", fb_bytes[0x16:0x18])[0]
    st = ((h + 7) // 8) * h
    out = subprocess.run([svfdump] + list(opts) + [face_path, "syllables"], capture_output=True, check=True).stdout
    if len(out) != (N + 51) * st + 1:
        raise ValueError("svfdump syllables: %d bytes, expected %d" % (len(out), (N + 51) * st + 1))
    ks_bad, compat_bad, present = [], [], 0
    for n in range(N):
        cp = 0xAC00 + n
        got = out[n * st:(n + 1) * st]
        if cp in want:
            if got != want[cp]:
                ks_bad.append(cp)
        elif any(got):
            present += 1
    for k in range(51):
        if out[(N + k) * st:(N + k + 1) * st] != want[0x3131 + k]:
            compat_bad.append(0x3131 + k)
    return {"ks_bad": ks_bad, "compat_bad": compat_bad, "non_ks_ink": present, "is_jamo": out[-1]}


# ---- sheets (PIL, only for the sheet command) ---------------------------------------------------------------------

def _img(bitmaps, h, cols, scale, gap=1, colors=None):
    from PIL import Image
    rows = (len(bitmaps) + cols - 1) // cols
    cw = h * scale + gap
    im = Image.new("RGB", (cols * cw + gap, rows * cw + gap), (255, 255, 255))
    px = im.load()
    for i, v in enumerate(bitmaps):
        X, Y = gap + (i % cols) * cw, gap + (i // cols) * cw
        col = (colors[i] if colors else None) or (0, 0, 0)
        for y in range(h):
            for x in range(h):
                if v is not None and v >> (h * h - 1 - (y * h + x)) & 1:
                    for a in range(scale):
                        for b in range(scale):
                            px[X + x * scale + a, Y + y * scale + b] = col
    return im


def _side(ims, gap=12):
    from PIL import Image
    w = sum(i.width for i in ims) + gap * (len(ims) - 1)
    out = Image.new("RGB", (w, max(i.height for i in ims)), (255, 255, 255))
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.width + gap
    return out


def sheets(data, build, outdir, name, sample=200):
    """PNG sheets: KS 2,350 from the face at 1x and 3x; Mac composition | face | diff (red) at 3x for the first 470;
    a sample of extrapolated syllables (guess and regular) at 3x; the pieces at 3x. Returns {file: description}."""
    f = J.parse_svfn(data)
    t = J.unpack(f.jset)
    h = build.h
    ks = sorted(build.planes)

    def face_bm(n):
        return _bm(J.compose(f, t, 0xAC00 + n), h)
    out = {}
    fb = [face_bm(n) for n in ks]
    mac = [mac_compose(build.fb, build.ht.syllables[n]) for n in ks]
    for sc in (1, 3):
        p = "%s_ks2350_x%d.png" % (name, sc)
        _img(fb, h, 50 if sc == 1 else 47, sc).save(os.path.join(outdir, p))
        out[p] = "KS X 1001 2,350 syllables composed from the SVF face, %dx" % sc
    diff = [a ^ b for a, b in zip(fb, mac)]
    p = "%s_mac_vs_svf_x3.png" % name
    _side([_img(mac, h, 47, 3), _img(fb, h, 47, 3), _img(diff, h, 47, 3, colors=[(220, 0, 0)] * len(diff))]).save(
        os.path.join(outdir, p))
    out[p] = "left: mac_fbit3 composition (Mac HTBL 1), middle: SVF face, right: XOR (red; empty = exact), all 2,350"
    guess = [n for n in range(N) if build.status[n] == "guess"]
    reg = [n for n in range(N) if build.status[n] == "regular"]
    step_g = max(1, len(guess) // sample)
    step_r = max(1, len(reg) // sample)
    gs, rs = guess[::step_g][:sample], reg[::step_r][:sample]
    for lst, kind in ((gs, "guess"), (rs, "regular")):
        if not lst:
            continue
        p = "%s_extrap_%s_x3.png" % (name, kind)
        _img([face_bm(n) for n in lst], h, 20, 3).save(os.path.join(outdir, p))
        out[p] = "%d of the %d extrapolated (%s) syllables, every %d-th, U+AC00 order: %s" % (
            len(lst), len(guess if kind == "guess" else reg), kind, step_g if kind == "guess" else step_r,
            "".join(chr(0xAC00 + n) for n in lst))
    pcs = sorted(cp for cp in f.glyphs if cp >= J.PIECE_BASE)
    p = "%s_pieces_x3.png" % name
    _img([_bm(f.glyphs[cp], h) for cp in pcs], h, 30, 3).save(os.path.join(outdir, p))
    out[p] = "the %d pieces (U+F0000 + n) in piece order" % len(pcs)
    return out


def _bm(cell, h):
    nb = (h + 7) // 8
    v = 0
    for y in range(h):
        row = int.from_bytes(cell[y * nb:(y + 1) * nb], "big") >> (nb * 8 - h)
        v = (v << h) | row
    return v


# ---- command line -------------------------------------------------------------------------------------------------

def load(fbit_path, htbl_path):
    return Fbit3(open(fbit_path, "rb").read()), Htbl1(open(htbl_path, "rb").read())


def analyse(fb, ht, log=None, big=False):
    """@p big: search up to the BIG limits (19 x 28 classes, 128/128/64 sets; --jset-big) instead of the standard ones."""
    planes = mac_planes(fb, ht)
    conf = slot_conflicts(fb, ht)
    if big:
        lc, tc = search_classes(planes, log=log, max_lc=19, max_tc=28)
        lc, tc, _ = fit_limits(planes, lc, tc, limits=(128, 128, 64), log=log)
        b = Build(fb, ht, lc, tc, limits=(128, 128, 64))
    else:
        lc, tc = search_classes(planes, log=log)
        lc, tc, _ = fit_limits(planes, lc, tc, log=log)
        b = Build(fb, ht, lc, tc)
    b.tables()
    m = b.m
    return b, {
        "cell": fb.h, "slot_conflict_pairs": len(conf),
        "lead_classes": class_names(lc, LEADS), "tail_classes": class_names(tc, TAILS), "lc": lc, "tc": tc,
        "ks_not_exact": len(m.bad), "residual_px": m.residual(),
        "sets": {"initial": b.sets[0], "medial": b.sets[1], "final": b.sets[2]},
        "within_v1_limits": b.sets[0] <= 32 and b.sets[1] <= 24 and b.sets[2] <= 16 and max(lc) < 12 and max(tc) < 12,   # the STANDARD row, whatever --jset-big says
        "within_big_limits": b.sets[0] <= 128 and b.sets[1] <= 128 and b.sets[2] <= 64 and max(lc) < 19 and max(tc) < 28,
        "jset_big": bool(big),
        "syllables": b.counts(),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyse", help="class search, sets, extrapolation counts (JSON)")
    a.add_argument("fbit")
    a.add_argument("htbl")
    a.add_argument("-o", "--out")
    b = sub.add_parser("build", help="write the jamo-set face")
    b.add_argument("fbit")
    b.add_argument("htbl")
    b.add_argument("-o", "--out", required=True)
    b.add_argument("--mode", choices=("direct", "derived"), default="direct",
                   help="direct (default): the Mac structure as a JMAP block, KS syllables only, no extrapolation; "
                        "derived: the extrapolated jamo-set (JSET version 1/2) face of all 11,172 syllables")
    b.add_argument("--no-dedup", action="store_true",
                   help="direct: one piece per Mac slot (default: byte-identical bitmaps of one plane share a piece)")
    b.add_argument("--with-jset", action="store_true",
                   help="direct: also derive the extrapolated JSET (as --mode derived would) and store it as the JMAP "
                        "fallback, so the other 8,822 syllables compose too; needs --classes or runs the class search")
    b.add_argument("--classes", help="analyse JSON to take lc / tc from (skips the search; derived and --with-jset)")
    b.add_argument("--latin", help="the family's suitcase resource fork (FOND + NFNT) for ASCII")
    b.add_argument("--latin-size", type=int, help="point size of the Latin strike (default: the cell)")
    b.add_argument("--report", help="write the build report (JSON) here")
    b.add_argument("--sheets", help="write PNG sheets into this directory")
    b.add_argument("--name", help="sheet file prefix (default: the output name)")
    J.add_jset_version_arg(b)
    v = sub.add_parser("verify", help="compose the face and compare with the Mac table")
    v.add_argument("face")
    v.add_argument("fbit")
    v.add_argument("htbl")
    v.add_argument("--classes", help="analyse JSON (lc / tc): needed for a derived face, not for a direct (JMAP) one")
    v.add_argument("--svfdump", action="append", default=[],
                   help="also check with this c/ svfdump build (repeatable: e.g. the default and a -DSVF_JSET_V2=0 one)")
    args = ap.parse_args(argv)
    log = lambda s: print(s, file=sys.stderr)
    if args.cmd == "analyse":
        fb, ht = load(args.fbit, args.htbl)
        _, rep = analyse(fb, ht, log)
        s = json.dumps(rep, ensure_ascii=False, indent=1)
        if args.out:
            open(args.out, "w").write(s + "\n")
        print(s)
        return 0
    fb, ht = load(args.fbit, args.htbl)
    fbit_bytes, htbl_bytes = open(args.fbit, "rb").read(), open(args.htbl, "rb").read()
    jmap_face = False
    if args.cmd == "verify":
        raw = open(args.face, "rb").read()
        f = J.parse_svfn(raw)
        if f.jset is not None:
            jmap_face = len(f.jset) >= 6 and struct.unpack_from("<H", f.jset, 4)[0] == 3
        elif f.jset_bad:
            ap.error("verify: the face has a JSET flag but its jamo-set block is unusable (a named piece has no glyph, "
                     "or the block is damaged): not a face this tool wrote intact")
    if jmap_face:
        try:
            r = verify_direct(open(args.face, "rb").read(), fbit_bytes, htbl_bytes)
        except ValueError as e:
            print(f"macfbit_svf: {args.face}: {e}", file=sys.stderr)
            return 1
        res = {"mode": "direct", "python": {k: (len(x) if isinstance(x, list) else x) for k, x in r.items()}}
        bad = bool(r["ks_bad"] or r["compat_bad"])
        for exe in args.svfdump:
            c = cverify_direct(args.face, fbit_bytes, htbl_bytes, exe)
            res[exe] = {k: (len(x) if isinstance(x, list) else x) for k, x in c.items()}
            bad = bad or c["ks_bad"] or c["compat_bad"] or c["is_jamo"] != 1
        print(json.dumps(res))
        return 1 if bad else 0
    if args.cmd == "verify":
        if not args.classes:
            ap.error("verify of a derived face needs --classes")
        c = json.load(open(args.classes))
        try:                   # a BIG face (counts over the standard row) is verified against the BIG set limits
            ft = J.unpack(J.parse_svfn(open(args.face, "rb").read()).jset)
            big = isinstance(ft, J.Tables) and J.needs_big(ft)
        except (ValueError, TypeError):
            big = False
        bld = Build(fb, ht, c["lc"], c["tc"], limits=(128, 128, 64) if big else SET_LIMITS)
        r = verify(open(args.face, "rb").read(), bld)
        res = {"python": {k: len(x) for k, x in r.items()}}
        bad = any(r.values())
        for exe in args.svfdump:
            c = cverify(args.face, bld, exe)
            res[exe] = {k: (len(x) if isinstance(x, list) else x) for k, x in c.items()}
            bad = bad or c["ks_bad"] or c["all_bad"] or c["compat_bad"] or c["is_jamo"] != 1
        print(json.dumps(res))
        return 1 if bad else 0
    latin, notes = None, []
    if args.latin:
        fork = resource_fork(open(args.latin, "rb").read())
        latin, notes = latin_cells(nfnt_glyphs(nfnt_for_size(fork, args.latin_size or fb.h)), fb.h,
                                   default_ascent(fb.h))
    if args.mode == "direct" and (args.sheets or args.name):
        ap.error("--sheets draws a derived face: use --mode derived (--name goes with it)")
    if args.mode == "direct" and not args.with_jset:
        bld, rep = None, {}
    elif args.classes:
        c = json.load(open(args.classes))
        bld = Build(fb, ht, c["lc"], c["tc"], limits=(128, 128, 64) if args.jset_big else SET_LIMITS)
        rep = dict(c)
    else:
        bld, rep = analyse(fb, ht, log, args.jset_big)
    if args.mode == "direct":
        jv = args.jset_version
        data, parts = write_direct(fb, ht, latin, not args.no_dedup, bld, jset_version=jv, jset_big=args.jset_big)
        open(args.out, "wb").write(data)
        r = verify_direct(data, fbit_bytes, htbl_bytes)
        nslots = len({(p, g) for e in ht.syllables.values() for p, g in enumerate(e) if g is not None}
                     | {(_KIND_PLANE[J.COMPAT[k][0]], g) for k, e in ht.compat.items()
                        for g in e if g is not None and sum(x is not None for x in e) == 1})
        rep.update({"face": args.out, "mode": "direct", "dedup": not args.no_dedup, "with_jset": bld is not None,
                    "jset_version": (struct.unpack_from("<H", parts["fallback"], 4)[0] if bld is not None else None), "sizes": size_table(data),
                    "latin_notes": notes, "jmap": len(parts["jmap"]), "fallback": len(parts["fallback"] or b""),
                    "pieces": len(parts["slots"]), "fallback_pieces": len(parts["pieces"]) - len(parts["slots"]),
                    "pieces_as_slots": len(parts["slots"]) == nslots,
                    "compat_whole": len(parts["compat"]),
                    "verify": {k: (len(x) if isinstance(x, list) else x) for k, x in r.items()}})
        s = json.dumps(rep, ensure_ascii=False, indent=1)
        if args.report:
            open(args.report, "w").write(s + "\n")
        print(s)
        return 0 if not (r["ks_bad"] or r["compat_bad"]) else 1
    data, parts = write_face(bld, latin, args.jset_version, jset_big=args.jset_big)
    open(args.out, "wb").write(data)
    r = verify(data, bld)
    rep.update({"face": args.out, "mode": "derived", "jset_version": args.jset_version, "sizes": size_table(data),
                "latin_notes": notes, "compat_whole": len(parts["compat"]),
                "verify": {k: len(x) for k, x in r.items()}, "syllables": bld.counts(),
                "sets": {"initial": bld.sets[0], "medial": bld.sets[1], "final": bld.sets[2]},
                "classes": "%d x %d" % (bld.nlc, bld.ntc), "ks_not_exact": len(bld.m.bad),
                "residual_px": bld.m.residual()})
    for ver in (1, 2):
        d2, _ = write_face(bld, latin, ver, jset_big=args.jset_big)
        rep["size_v%d" % ver] = size_table(d2)
    if args.sheets:
        os.makedirs(args.sheets, exist_ok=True)
        rep["sheets"] = sheets(data, bld, args.sheets, args.name or os.path.splitext(os.path.basename(args.out))[0])
    s = json.dumps(rep, ensure_ascii=False, indent=1)
    if args.report:
        open(args.report, "w").write(s + "\n")
    print(s)
    return 0 if not any(r.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
