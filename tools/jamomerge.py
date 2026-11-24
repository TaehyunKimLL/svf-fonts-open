#!/usr/bin/env python3
"""Shrink a jamo-set face by merging its variants: pieces, sets, lead and tail classes (card t_83912a1b).

A many-variant jamo-set face (spec/SVF.md, "Jamo-set fonts") - e.g. one with 13 initial sets by vowel class and final
and many medial runs - is too large for an MCU budget. This tool
keeps every piece *as drawn* (no re-hinting, no new bitmaps) and only makes the face use fewer of them:

  * tie      every slot of one jamo that draws bitmap x draws bitmap y (another variant of that jamo) instead;
  * set      two sets of one kind become one; per jamo the merged slot keeps the variant the objective prefers;
  * class    two lead (or tail) classes become one; per (vowel, other class) cell the merged class keeps the initial,
             medial and final set of either side, whichever the objective prefers.

Greedy: each round every move is scored by the pixel objective (reference = the unmerged face's own composition:
MISS per lost reference pixel, 1 per extra pixel, OVERLAP per pixel two pieces share; KS X 1001 syllables weight 1.0,
the others OTHER_WEIGHT) per byte saved; the best RECOG_TOP of them are re-scored by an optional recogniser
(``scorer``: weighted top-1 errors + RECOG_NLL x log-loss over the syllables the move changes) and the best per byte
is applied. Hard gates refuse a move outright:

  * tick     a ㅗ/ㅛ/ㅜ/ㅠ/ㅡ-type medial loses its tick (missing, or covered by another piece) in any syllable;
  * medial   two KS syllables of one medial group (same initial and final) end up closer than min(2, reference
             distance) pixels (ㅗ ㅜ ㅡ kept apart);
  * stroke   a KS syllable has fewer horizontal or vertical runs (2+ px) than its reference (a dropped stroke);
  * leak     a KS syllable has an extra pixel touching another jamo's reference ink (needs the reference planes);
  * recog    (with a scorer) a changed slot's neutral syllable, read correctly before, is misread on that jamo.

Each gate is per syllable and only refuses what the move makes worse: a syllable that failed in the unmerged face may
keep failing.

  python3 tools/jamomerge.py baseline --face SEOUL12J.SVF [--planes PLANES.json] [-o REPORT.json]
  python3 tools/jamomerge.py merge --face SEOUL12J.SVF --planes PLANES.json --points 8192 7168 6144 5120 -o OUTDIR

``--planes`` is a JSON {"ks": {syllable index: [initial, medial, final] plane bitmaps as ints (bit y*w+x)}} of the
reference's own jamo split (for the leak gate); macref.py writes it from the Mac fbit + HTBL. Pure Python but for the
optional recogniser (``--recog``, numpy + torch + recog.py of research/hinting).
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jamoset as J  # noqa: E402
import jamofill as F  # noqa: E402

NSYL = 11172
KINDS = (("i", 19, 0), ("m", 21, 0), ("f", 27, 1))
KN = {"i": 19, "m": 21, "f": 27}
OTHER_WEIGHT = float(os.environ.get("JAMOMERGE_OTHER", "0.1"))
MISS = 2.0
OVERLAP = 1.0
SOFT_PENALTY = float(os.environ.get("JAMOMERGE_SOFT", "40"))   # per KS stroke / leak flag once soft
NONKS_FLAG = 20.0             # per stroke / leak flag of a non-KS syllable (soft; x OTHER_WEIGHT)
MEDIAL_SOFT = 30.0            # per medial-pair violation of non-KS syllables (soft)
TICK_ABOVE, TICK_BELOW = F.TICK_ABOVE, F.TICK_BELOW
RECOG_TOP = int(os.environ.get("JAMOMERGE_RECOG_TOP", "16"))
RECOG_NLL = 0.2
PROFILE = "mcu-strict"
MEDIAL_GROUPS = F.MEDIAL_GROUPS

G_TICK, G_STROKE, G_LEAK = 1, 2, 4


def pop(x):
    return x.bit_count()


# ---- the face ------------------------------------------------------------------------------------------------------

class Face:
    """A jamo-set face as merge state: classes and set tables (lists), slot bitmaps ``sb[(kind, set, jamo)]`` (final
    jamo 1..27), and the fixed rest (ASCII glyphs with metrics and dy)."""

    def __init__(self, w, h, ascent, lead_class, tail_class, lc, tc, iset, mset, fset, sb, ascii_glyphs, advance=0):
        self.w, self.h, self.ascent = w, h, ascent
        self.lead_class, self.tail_class = list(lead_class), list(tail_class)
        self.lc, self.tc = lc, tc
        self.iset, self.mset, self.fset = list(iset), list(mset), list(fset)
        self.sb = dict(sb)
        self.ascii = ascii_glyphs
        self.advance = advance

    def copy(self):
        return Face(self.w, self.h, self.ascent, self.lead_class, self.tail_class, self.lc, self.tc, self.iset,
                    self.mset, self.fset, self.sb, self.ascii, self.advance)

    def cell(self, L, V, T):
        return (self.lead_class[L] * 21 + V) * self.tc + self.tail_class[T]

    def slots(self, s):
        L, V, T = s // 588, (s // 28) % 21, s % 28
        c = self.cell(L, V, T)
        out = [("i", self.iset[c], L), ("m", self.mset[c], V)]
        if T:
            out.append(("f", self.fset[c], T))
        return out

    def triple(self, s):
        sl = self.slots(s)
        sb = self.sb
        return (sb[sl[0]], sb[sl[1]], sb[sl[2]] if len(sl) > 2 else 0)

    def comp(self, s):
        a, b, c = self.triple(s)
        return a | b | c

    def nsets(self, k):
        return 1 + max((s for (kk, s, _) in self.sb if kk == k), default=0)

    def bitmaps(self):
        return set(self.sb.values())

    def users(self):
        u = {}
        for s in range(NSYL):
            for sl in self.slots(s):
                u.setdefault(sl, []).append(s)
        return u


def _cell_to_int(cell, w, h):
    pitch = (w + 7) // 8
    b = 0
    for y in range(h):
        for x in range(w):
            if cell[y * pitch + x // 8] >> (7 - x % 8) & 1:
                b |= 1 << (y * w + x)
    return b


def int_to_cell(b, w, h):
    pitch = (w + 7) // 8
    out = bytearray()
    for y in range(h):
        row = 0
        for x in range(w):
            if b >> (y * w + x) & 1:
                row |= 1 << (pitch * 8 - 1 - x)
        out += row.to_bytes(pitch, "big")
    return bytes(out)


def read_face(path):
    """A Face from a jamo-set SVF (JSET version 1 or 2; a version 3 JMAP or LIST face is refused); ASCII U+0020..U+007E kept as stored."""
    with open(path, "rb") as fi:
        data = fi.read()
    f = J.parse_svfn(data)
    t = J.unpack(f.jset)
    if isinstance(t, J.Jmap):
        raise ValueError(f"{path}: a JMAP or LIST face (JSET version 3) has no set tables; jamomerge reads set-table faces")
    w, h = f.cell_w, f.cell_h
    pieces = {cp - J.PIECE_BASE: _cell_to_int(c, w, h) for cp, c in f.glyphs.items() if cp >= J.PIECE_BASE}
    sb = {}
    for k, n, off in KINDS:
        lst = {"i": t.init_piece, "m": t.med_piece, "f": t.fin_piece}[k]
        for idx, p in enumerate(lst):
            if p != J.BLANK:
                s, j = divmod(idx, n)
                sb[(k, s, j + off)] = pieces[p]
    asc = []
    for cp in range(0x20, 0x7F):
        if cp in f.glyphs:
            m = f.metrics.get(cp, (w, 0, w))
            asc.append((cp, f.glyphs[cp], m[0], m[1], m[2], f.dy.get(cp, 0)))
    fc = Face(w, h, f.ascent, t.lead_class, t.tail_class, t.lc, t.tc, t.init_set, t.med_set, t.fin_set, sb, asc,
              t.advance)
    used = set()
    for s in range(NSYL):
        used.update(fc.slots(s))
    fc.sb = {sl: b for sl, b in sb.items() if sl in used}
    normalize(fc)
    return fc


# ---- normalisation (free merges) and size --------------------------------------------------------------------------

def normalize(fc):
    """Drop unused slots and sets, merge sets that agree wherever both are defined, then lead / tail classes whose
    rows are equal. In place; returns fc."""
    while True:
        used = set()
        for s in range(NSYL):
            used.update(fc.slots(s))
        fc.sb = {sl: b for sl, b in fc.sb.items() if sl in used}
        changed = False
        for k, n, off in KINDS:
            rows = {}
            for (kk, s, j), b in fc.sb.items():
                if kk == k:
                    rows.setdefault(s, {})[j] = b
            order = sorted(rows)
            m, groups = {}, []
            for s in order:
                r = rows[s]
                for gi, g in enumerate(groups):
                    if all(g.get(j, b) == b for j, b in r.items()):
                        g.update(r)
                        m[s] = gi
                        break
                else:
                    m[s] = len(groups)
                    groups.append(dict(r))
            if any(m[s] != s for s in order) or len(groups) != len(order):
                changed = True
            lst = {"i": fc.iset, "m": fc.mset, "f": fc.fset}[k]
            for c in range(len(lst)):
                lst[c] = m.get(lst[c], 0)
            fc.sb = {sl: b for sl, b in fc.sb.items() if sl[0] != k}
            for gi, g in enumerate(groups):
                for j, b in g.items():
                    fc.sb[(k, gi, j)] = b
        # classes
        if _merge_equal_classes(fc):
            changed = True
        if not changed:
            return fc


def _merge_equal_classes(fc):
    tails_used = sorted(set(fc.tail_class))
    real_tails = {fc.tail_class[T] for T in range(1, 28)}
    leads_used = sorted(set(fc.lead_class))

    def lrow(a):
        return tuple((fc.iset[(a * 21 + v) * fc.tc + b], fc.mset[(a * 21 + v) * fc.tc + b],
                      fc.fset[(a * 21 + v) * fc.tc + b] if b in real_tails else -1)
                     for v in range(21) for b in tails_used)

    def tcol(b):
        return tuple((fc.iset[(a * 21 + v) * fc.tc + b], fc.mset[(a * 21 + v) * fc.tc + b],
                      fc.fset[(a * 21 + v) * fc.tc + b] if b in real_tails else -1)
                     for a in leads_used for v in range(21))
    lmap, lkeys = {}, []
    for a in leads_used:
        r = lrow(a)
        if r in lkeys:
            lmap[a] = lkeys.index(r)
        else:
            lmap[a] = len(lkeys)
            lkeys.append(r)
    tmap, tkeys = {}, []
    for b in tails_used:
        c = tcol(b)
        # a no-final class (0) and a final class are never one: their fset rows differ (-1 vs a set)
        if c in tkeys:
            tmap[b] = tkeys.index(c)
        else:
            tmap[b] = len(tkeys)
            tkeys.append(c)
    if len(lkeys) == fc.lc and len(tkeys) == fc.tc and all(lmap[a] == a for a in leads_used) \
            and all(tmap[b] == b for b in tails_used):
        return False
    lc, tc = len(lkeys), len(tkeys)
    n = lc * 21 * tc
    iset, mset, fset = [0] * n, [0] * n, [0] * n
    for a in leads_used:
        for v in range(21):
            for b in tails_used:
                c0 = (a * 21 + v) * fc.tc + b
                c = (lmap[a] * 21 + v) * tc + tmap[b]
                iset[c], mset[c] = fc.iset[c0], fc.mset[c0]
                fset[c] = fc.fset[c0] if b in real_tails else 0
    fc.lead_class = [lmap[x] for x in fc.lead_class]
    fc.tail_class = [tmap[x] for x in fc.tail_class]
    fc.lc, fc.tc, fc.iset, fc.mset, fc.fset = lc, tc, iset, mset, fset
    return True


class Sizer:
    """Bytes of the face as build() writes it (mcu-strict, JSET v1), from the parts."""

    def __init__(self, w, h):
        self.w, self.h = w, h
        self.pr = J.profile_of(PROFILE)
        self.pitch = (w + 7) // 8
        self._pb = {}

    def piece_bytes(self, b):
        v = self._pb.get(b)
        if v is None:
            cell = int_to_cell(b, self.w, self.h)
            v = self._pb[b] = 8 + 4 + 2 + len(J.encode_record(cell, self.pitch, self.h, self.pr.box, self.pr.rec,
                                                              self.pr.row))
        return v

    def ascii_bytes(self, fc):
        return sum(8 + 4 + 2 + len(J.encode_record(c, self.pitch, self.h, self.pr.box, self.pr.rec, self.pr.row))
                   for _, c, *_ in fc.ascii)

    def jset(self, fc):
        return J._jset_size_v1(fc.lc, fc.tc, fc.nsets("i"), fc.nsets("m"), fc.nsets("f"))

    def size(self, fc, ascii_bytes=None):
        if ascii_bytes is None:
            ascii_bytes = self.ascii_bytes(fc)
        bms = fc.bitmaps()
        n = len(fc.ascii) + len(bms)
        js = self.jset(fc)
        return 48 + ascii_bytes + sum(self.piece_bytes(b) for b in bms) + (-js % 4) + js + (-(2 * (n + 1)) % 4) + 2


def tables_of(fc):
    """(J.Tables, [bitmaps in piece order]) of a Face."""
    order = {}
    for sl in sorted(fc.sb):
        order.setdefault(fc.sb[sl], len(order))
    ni, nm, nf = fc.nsets("i"), fc.nsets("m"), fc.nsets("f")
    t = J.Tables(fc.lc, fc.tc, ni, nm, nf, fc.advance)
    t.lead_class, t.tail_class = list(fc.lead_class), list(fc.tail_class)
    t.init_set, t.med_set, t.fin_set = list(fc.iset), list(fc.mset), list(fc.fset)
    real_tails = {fc.tail_class[T] for T in range(1, 28)}
    for c in range(len(t.fin_set)):
        if c % fc.tc not in real_tails:
            t.fin_set[c] = 0
    for (k, s, j), b in fc.sb.items():
        lst, n, off = {"i": (t.init_piece, 19, 0), "m": (t.med_piece, 21, 0), "f": (t.fin_piece, 27, 1)}[k]
        lst[s * n + j - off] = order[b]
    for idx, (kind, i) in enumerate(J.COMPAT):
        k, n, off = {"i": ("i", 19, 0), "v": ("m", 21, 0), "f": ("f", 27, 1)}[kind]
        lst, cnt = {"i": (t.init_piece, ni), "m": (t.med_piece, nm), "f": (t.fin_piece, nf)}[k]
        t.compat[idx] = next((lst[s * n + i - off] for s in range(cnt) if lst[s * n + i - off] != J.BLANK), J.BLANK)
    return t, list(order)


def build(fc):
    """The SVFN v3 face bytes (mcu-strict, JSET v1)."""
    t, bms = tables_of(fc)
    glyphs = [(cp, c, adv, ix, iw) for cp, c, adv, ix, iw, _ in fc.ascii]
    dy = {cp: d for cp, *_, d in fc.ascii if d}
    for n, b in enumerate(bms):
        xs = [x for x in range(fc.w) for y in range(fc.h) if b >> (y * fc.w + x) & 1]
        glyphs.append((J.PIECE_BASE + n, int_to_cell(b, fc.w, fc.h), fc.w, min(xs) if xs else 0,
                       max(xs) - min(xs) + 1 if xs else 0))
    try:
        block = J.pack_v1(t)
    except ValueError as e:      # jamomerge has no --jset-big: it writes the standard JSET only
        raise ValueError(f"{e}; jamomerge writes JSET within the standard limits only") from e
    return J.write_svfn(fc.w, fc.h, fc.ascent, glyphs, block, dy=dy, profile=PROFILE)


def verify(fc, data):
    """Every syllable of the written face composes to fc's composition (read back with jamoset)."""
    f = J.parse_svfn(data)
    t = J.unpack(f.jset)
    bad = []
    for s in range(NSYL):
        g = 0
        for n in J.pieces_of(t, 0xAC00 + s):
            if n == J.BLANK:
                bad.append(s)
                break
            g |= _cell_to_int(f.glyphs[J.PIECE_BASE + n], fc.w, fc.h)
        else:
            if g != fc.comp(s):
                bad.append(s)
    return bad


# ---- the reference and the objective -------------------------------------------------------------------------------

def is_ks(s):
    return F.is_ks(0xAC00 + s)


class Ref:
    """Reference syllables (``syl``), weights, KS flags, optional reference planes {s: (i, m, f)} (KS), and the
    gate state of the reference itself."""

    def __init__(self, w, h, syl, planes=None):
        self.w, self.h = w, h
        self.syl = syl
        self.ks = [is_ks(s) for s in range(NSYL)]
        self.wt = [1.0 if k else OTHER_WEIGHT for k in self.ks]
        self.planes = planes or {}
        self.full = (1 << (w * h)) - 1
        self.left = sum(1 << (y * w) for y in range(h)) * ((1 << (w - 1)) - 1)
        grp = {V: g for g in MEDIAL_GROUPS for V in g}
        self.partners = []
        for s in range(NSYL):
            L, V, T = s // 588, (s // 28) % 21, s % 28
            self.partners.append([(s2, min(2, pop(syl[s] ^ syl[s2])))
                                  for s2 in (L * 588 + V2 * 28 + T for V2 in grp[V] if V2 != V)])
        self.soft = 0          # gates (G_STROKE / G_LEAK) turned into SOFT_PENALTY costs past the gated floor
        self._tick = {}
        self._lines = {}
        self.ref_runs = [self.runs(b) for b in syl]
        self.ref_comps = [self.components(b) for b in syl]

    def dilate(self, b):
        w = self.w
        d = b | (b << 1 & self.left << 1) | (b >> 1 & self.left)
        return d | (d << w & self.full) | (d >> w)

    def components(self, b):
        """The 8-connected components of bitmap @p b, as bitmaps."""
        out = []
        while b:
            c = b & -b
            while True:
                n = self.dilate(c) & b
                if n == c:
                    break
                c = n
            out.append(c)
            b &= ~c
        return out

    def lines(self, b):
        """(rows, columns) of bitmap @p b as ints (row y: bit x; column x: bit y)."""
        v = self._lines.get(b)
        if v is None:
            w, h = self.w, self.h
            rows = [b >> (y * w) & ((1 << w) - 1) for y in range(h)]
            cols = [sum(1 << y for y in range(h) if rows[y] >> x & 1) for x in range(w)]
            v = self._lines[b] = (rows, cols)
        return v

    def runs(self, b, min_len=2):
        """[(horizontal?, line, mask)] of the runs of at least @p min_len pixels along rows and columns."""
        rows, cols = self.lines(b)
        out = []
        for horiz, ls in ((True, rows), (False, cols)):
            for a, m in enumerate(ls):
                x = 0
                while m >> x:
                    if m >> x & 1:
                        x0 = x
                        while m >> x & 1:
                            x += 1
                        if x - x0 >= min_len:
                            out.append((horiz, a, ((1 << (x - x0)) - 1) << x0))
                    else:
                        x += 1
        return out

    def stroke_lost(self, s, c):
        """True when a reference run of syllable s (2+ px) has no counterpart in @p c: a run on the same line or a
        neighbouring one covering all but one of its pixels."""
        rows, cols = self.lines(c)
        for horiz, a, m in self.ref_runs[s]:
            ls = rows if horiz else cols
            need = max(1, m.bit_count() - 1)
            if not any(0 <= a2 < len(ls) and (ls[a2] & m).bit_count() >= need for a2 in (a, a - 1, a + 1)):
                return True
        return False

    def leaks(self, s, c):
        """True when a component of @p c joins two components of the reference syllable (ink bridging a gap)."""
        rc = self.ref_comps[s]
        if len(rc) < 2:
            return False
        for comp in self.components(c):
            n = 0
            for r in rc:
                if comp & r:
                    n += 1
                    if n > 1:
                        return True
        return False

    def tick(self, b, V):
        key = (b, V)
        t = self._tick.get(key)
        if t is None:
            _, above, below = F.bar_and_tick(b, self.w, self.h)
            t = self._tick[key] = above if V in TICK_ABOVE else below if V in TICK_BELOW else 0
        return t

    def local(self, s, tri):
        """(objective, gate flags) of syllable s drawn from the bitmaps tri = (initial, medial, final or 0). The
        stroke and leak flags of a non-KS syllable only cost NONKS_FLAG each."""
        pi, pm, pf = tri
        c = pi | pm | pf
        r = self.syl[s]
        e = MISS * pop(r & ~c) + pop(c & ~r) + OVERLAP * (pop(pi & pm) + pop(pi & pf) + pop(pm & pf))
        flags = 0
        V = (s // 28) % 21
        if V in TICK_ABOVE or V in TICK_BELOW:
            t = self.tick(pm, V)
            if not t or not (t & ~(pi | pf)):
                flags |= G_TICK
        if c != r:
            if self.stroke_lost(s, c):
                flags |= G_STROKE
            if self.leaks(s, c):
                flags |= G_LEAK
            if not self.ks[s]:
                e += NONKS_FLAG * (bool(flags & G_STROKE) + bool(flags & G_LEAK))
            elif flags & self.soft:
                e += SOFT_PENALTY * (bool(flags & self.soft & G_STROKE) + bool(flags & self.soft & G_LEAK))
        return self.wt[s] * e, flags

    def refuses(self, s, new, old):
        """The gate a change of syllable s's flags from @p old to @p new trips, or None."""
        worse = new & ~old & ~self.soft
        if not self.ks[s]:
            worse &= G_TICK
        if not worse:
            return None
        return "tick" if worse & G_TICK else "stroke" if worse & G_STROKE else "leak"

    def pair_bad(self, s, s2, need, c, c2):
        return pop(c ^ c2) < need


class State:
    """A Face with its cached per-syllable triples, objective terms, gate flags and medial-pair violations."""

    def __init__(self, fc, ref):
        self.fc, self.ref = fc, ref
        self.refresh()

    def refresh(self):
        fc, ref = self.fc, self.ref
        self.tri = [fc.triple(s) for s in range(NSYL)]
        self.comp = [a | b | c for a, b, c in self.tri]
        loc = [ref.local(s, self.tri[s]) for s in range(NSYL)]
        self.cost = [x[0] for x in loc]
        self.flags = [x[1] for x in loc]
        self.users = fc.users()

    def pair_terms(self, s, comp_of):
        """[(partner, violated)] of syllable s with compositions from comp_of."""
        c = comp_of(s)
        return [(s2, pop(c ^ comp_of(s2)) < need) for s2, need in self.ref.partners[s]]

    def total(self):
        p = 0.0
        for s in range(NSYL):
            for s2, need in self.ref.partners[s]:
                if s2 > s and pop(self.comp[s] ^ self.comp[s2]) < need:
                    p += self._pair_pen(s, s2)
        return sum(self.cost) + p

    def _pair_pen(self, s, s2):
        return 1e6 if (self.ref.ks[s] or self.ref.ks[s2]) else MEDIAL_SOFT

    def evaluate(self, newtri):
        """(objective delta, refused reason or None) of replacing the triples of the syllables in @p newtri."""
        ref = self.ref
        d = 0.0
        for s, tri in newtri.items():
            v, fl = ref.local(s, tri)
            d += v - self.cost[s]
            why = ref.refuses(s, fl, self.flags[s])
            if why:
                return d, why
        newc = {s: a | b | c for s, (a, b, c) in newtri.items()}
        get = lambda x: newc.get(x, self.comp[x])
        seen = set()
        for s in newc:
            for s2, need in ref.partners[s]:
                key = (min(s, s2), max(s, s2))
                if key in seen:
                    continue
                seen.add(key)
                old = pop(self.comp[s] ^ self.comp[s2]) < need
                new = pop(get(s) ^ get(s2)) < need
                if new and not old:
                    if ref.ks[s] or ref.ks[s2]:
                        return d, "medial"
                    d += MEDIAL_SOFT
                elif old and not new:
                    d -= self._pair_pen(*key) if not (ref.ks[s] or ref.ks[s2]) else 0
        return d, None


# ---- moves ---------------------------------------------------------------------------------------------------------

class Move:
    def __init__(self, kind, desc, fc, newtri, saved):
        self.kind, self.desc, self.fc, self.newtri, self.saved = kind, desc, fc, newtri, saved
        self.dpix = None
        self.refused = None
        self.drec = 0.0


def tie_moves(st, sizer):
    """Every 'jamo (k, j): bitmap x -> bitmap y' with x and y both drawn by that jamo."""
    fc = st.fc
    byj = {}
    for (k, s, j), b in fc.sb.items():
        byj.setdefault((k, j), {}).setdefault(b, []).append((k, s, j))
    used_by = {}
    for (k, s, j), b in fc.sb.items():
        used_by.setdefault(b, set()).add((k, j))
    pos = {"i": 0, "m": 1, "f": 2}
    out = []
    for (k, j), bm in byj.items():
        if len(bm) < 2:
            continue
        for x, xslots in bm.items():
            if len(used_by[x]) > 1:
                continue
            saved = sizer.piece_bytes(x)
            aff = set()
            for sl in xslots:
                aff.update(st.users.get(sl, ()))
            for y in bm:
                if y == x:
                    continue
                newtri = {}
                p = pos[k]
                for s in aff:
                    t = list(st.tri[s])
                    t[p] = y
                    newtri[s] = tuple(t)
                nf = fc.copy()
                for sl in xslots:
                    nf.sb[sl] = y
                mv = Move("tie", f"{k}{_jname(k, j)} {_bid(x)}->{_bid(y)}", nf, newtri, saved)
                mv.slot_change = {sl: y for sl in xslots}
                mv.jamo = (k, j)
                out.append(mv)
    return out


def _jname(k, j):
    return {"i": F.INI, "m": F.MED, "f": F.FIN}[k][j - (1 if k == "f" else 0)]


def _bid(b):
    return "%06x" % (b % 16777213)


def set_moves(st, sizer):
    """Every merge of two sets of one kind; per jamo both draw, the variant with the least objective over the users
    of both slots."""
    fc = st.fc
    out = []
    pos = {"i": 0, "m": 1, "f": 2}
    for k, n, off in KINDS:
        rows = {}
        for (kk, s, j), b in fc.sb.items():
            if kk == k:
                rows.setdefault(s, {})[j] = b
        sets = sorted(rows)
        p = pos[k]
        pools = {}
        for (kk, _, j), bm in fc.sb.items():
            if kk == k and bm not in pools.setdefault(j, []):
                pools[j].append(bm)
        for ia, a in enumerate(sets):
            for b in sets[ia + 1:]:
                nf = fc.copy()
                newtri = {}
                for j in set(rows[a]) | set(rows[b]):
                    xa, xb = rows[a].get(j), rows[b].get(j)
                    ua, ub = st.users.get((k, a, j), []), st.users.get((k, b, j), [])
                    if xa is None or xb is None or xa == xb:
                        x = xa if xa is not None else xb
                    else:
                        best = None
                        pool = [xa, xb] + [x for x in pools[j] if x not in (xa, xb)]
                        for x0 in pool:
                            v = 0.0
                            bad = 0
                            for s in ua + ub:
                                t = list(st.tri[s])
                                t[p] = x0
                                c, fl = st.ref.local(s, tuple(t))
                                v += c
                                bad += st.ref.refuses(s, fl, st.flags[s]) is not None
                            v += 1e6 * bad
                            if best is None or v < best[0]:
                                best = (v, x0)
                        x = best[1]
                    nf.sb[(k, a, j)] = x
                    nf.sb.pop((k, b, j), None)
                    for s in ua + ub:
                        if st.tri[s][p] != x:
                            t = list(st.tri[s])
                            t[p] = x
                            newtri[s] = tuple(t)
                lst = {"i": nf.iset, "m": nf.mset, "f": nf.fset}[k]
                for c in range(len(lst)):
                    if lst[c] == b:
                        lst[c] = a
                nf2 = nf.copy()
                normalize(nf2)
                saved = sizer.size(fc) - sizer.size(nf2)
                out.append(Move("set", f"{k} set {a}+{b}", nf, newtri, saved))
    return out


def _freed(fc, nf, sizer):
    before, after = fc.bitmaps(), set(nf.sb.values())
    return sum(sizer.piece_bytes(b) for b in before - after) - sum(sizer.piece_bytes(b) for b in after - before)


def class_moves(st, sizer):
    """Every merge of two lead classes (or two tail classes): per (vowel, other class) cell and kind, the set of
    either side with the least objective over the cell's syllables of both classes; a slot the chosen set lacks for
    a jamo of the other class is filled with that syllable's present bitmap."""
    fc = st.fc
    out = []
    real_tails = {fc.tail_class[T] for T in range(1, 28)}
    for lead in (True, False):
        ncls = fc.lc if lead else fc.tc
        members = {}
        for x, c in enumerate(fc.lead_class if lead else fc.tail_class):
            members.setdefault(c, []).append(x)
        for a in range(ncls):
            for b in range(a + 1, ncls):
                if not lead and ((a in real_tails) != (b in real_tails)):
                    continue                      # a no-final class never merges with a final class
                if a not in members or b not in members:
                    continue
                mv = _class_merge(st, sizer, lead, a, b, members, real_tails)
                if mv is not None:
                    out.append(mv)
    return out


def _class_merge(st, sizer, lead, a, b, members, real_tails):
    fc = st.fc
    nf = fc.copy()
    newtri = {}
    others = range(fc.tc) if lead else range(fc.lc)
    lists = (("i", 0, nf.iset), ("m", 1, nf.mset), ("f", 2, nf.fset))
    unions = {}
    for v in range(21):
        for o in others:
            ca = (a * 21 + v) * fc.tc + o if lead else (o * 21 + v) * fc.tc + a
            cb = (b * 21 + v) * fc.tc + o if lead else (o * 21 + v) * fc.tc + b
            # syllables of the cell, both classes
            syls = []
            for x in members[a] + members[b]:
                if lead:
                    for T in range(28):
                        if fc.tail_class[T] == o:
                            syls.append(x * 588 + v * 28 + T)
                else:
                    for L in range(19):
                        if fc.lead_class[L] == o:
                            syls.append(L * 588 + v * 28 + x)
            if not syls:
                continue
            cur = {s: list(newtri.get(s, st.tri[s])) for s in syls}
            for k, p, lst in lists:
                if k == "f" and ((o if lead else a) not in real_tails):
                    continue
                sa, sbb = lst[ca], lst[cb]
                if sa == sbb:
                    continue
                union_ok = (k == "i") if lead else (k == "f")
                best = None
                for cand in (sa, sbb) + (("U",) if union_ok else ()):
                    v_, bad = 0.0, 0
                    trial = {}
                    for s in syls:
                        L, V, T = s // 588, (s // 28) % 21, s % 28
                        if k == "f" and not T:
                            continue
                        j = (L, V, T)[p]
                        bm = None if cand == "U" else nf.sb.get((k, cand, j))
                        if bm is None:
                            bm = cur[s][p]
                        t = list(cur[s])
                        t[p] = bm
                        c, fl = st.ref.local(s, tuple(t))
                        v_ += c
                        bad += st.ref.refuses(s, fl, st.flags[s]) is not None
                        trial[s] = bm
                    v_ += 1e6 * bad
                    if best is None or v_ < best[0]:
                        best = (v_, cand, trial)
                _, cand, trial = best
                if cand == "U":
                    key = (k, sa, sbb)
                    if key not in unions:
                        unions[key] = nf.nsets(k)
                        for (kk, ss, jj), bm in list(nf.sb.items()):
                            if kk == k and ss == sa and jj in members[a]:
                                nf.sb[(k, unions[key], jj)] = bm
                            if kk == k and ss == sbb and jj in members[b]:
                                nf.sb[(k, unions[key], jj)] = bm
                    cand = unions[key]
                lst[ca] = lst[cb] = cand
                for s, bm in trial.items():
                    L, V, T = s // 588, (s // 28) % 21, s % 28
                    j = (L, V, T)[p]
                    nf.sb.setdefault((k, cand, j), bm)
                    cur[s][p] = nf.sb[(k, cand, j)]
            for s in syls:
                t = tuple(cur[s])
                if t != st.tri[s]:
                    newtri[s] = t
    # point class b at a
    if lead:
        nf.lead_class = [a if c == b else c for c in nf.lead_class]
    else:
        nf.tail_class = [a if c == b else c for c in nf.tail_class]
    # the triples must be what the new tables say (holes filled above)
    for s in list(newtri):
        if nf.triple(s) != newtri[s]:
            newtri[s] = nf.triple(s)
    for s in range(NSYL):
        L, V, T = s // 588, (s // 28) % 21, s % 28
        if (fc.lead_class[L] == b if lead else fc.tail_class[T] == b) and s not in newtri:
            t = nf.triple(s)
            if t != st.tri[s]:
                newtri[s] = t
    _compress_classes(nf, lead, b)
    nf2 = nf.copy()
    normalize(nf2)
    saved = sizer.size(fc) - sizer.size(nf2)
    return Move("lead" if lead else "tail", f"{'lead' if lead else 'tail'} class {a}+{b}", nf2, newtri, saved)


def _compress_classes(fc, lead, gone):
    """Remove class @p gone (no member points at it any more) and renumber."""
    lc, tc = fc.lc, fc.tc
    if lead:
        keep = [a for a in range(lc) if a != gone]
        rm = {a: i for i, a in enumerate(keep)}
        n = (lc - 1) * 21 * tc
        lists = [[0] * n for _ in range(3)]
        for a in keep:
            for v in range(21):
                for b in range(tc):
                    for L, src in zip(lists, (fc.iset, fc.mset, fc.fset)):
                        L[(rm[a] * 21 + v) * tc + b] = src[(a * 21 + v) * tc + b]
        fc.lead_class = [rm[x] for x in fc.lead_class]
        fc.lc = lc - 1
    else:
        keep = [b for b in range(tc) if b != gone]
        rm = {b: i for i, b in enumerate(keep)}
        n = lc * 21 * (tc - 1)
        lists = [[0] * n for _ in range(3)]
        for a in range(lc):
            for v in range(21):
                for b in keep:
                    for L, src in zip(lists, (fc.iset, fc.mset, fc.fset)):
                        L[(a * 21 + v) * (tc - 1) + rm[b]] = src[(a * 21 + v) * tc + b]
        fc.tail_class = [rm[x] for x in fc.tail_class]
        fc.tc = tc - 1
    fc.iset, fc.mset, fc.fset = lists


# ---- the greedy loop -----------------------------------------------------------------------------------------------

def all_moves(st, sizer):
    return tie_moves(st, sizer) + set_moves(st, sizer) + class_moves(st, sizer)


def step(st, sizer, scorer=None, log=None, top=RECOG_TOP, batch=1):
    """Apply the best move; returns it, or None when every move is refused or saves nothing."""
    moves = [m for m in all_moves(st, sizer) if m.saved > 0]
    ok = []
    refused = {}
    for m in moves:
        m.dpix, m.refused = st.evaluate(m.newtri)
        if m.refused:
            refused[m.refused] = refused.get(m.refused, 0) + 1
        else:
            ok.append(m)
    if not ok:
        return None, refused
    ok.sort(key=lambda m: max(m.dpix, 0.0) / m.saved)
    if scorer is not None:
        cand = ok[:top]
        keep = []
        for m in cand:
            r = scorer.delta(st, m)
            if r is None:
                m.refused = "recog"
                refused["recog"] = refused.get("recog", 0) + 1
                continue
            m.drec = r
            keep.append(m)
        if not keep:
            return None, refused
        best = min(keep, key=lambda m: (max(m.drec, 0.0) + 0.01 * max(m.dpix, 0.0)) / m.saved)
    else:
        best = ok[0]
    extra = []
    if batch > 1 and best.kind == "tie" and scorer is None:
        taken_j, taken_s = {best.jamo}, set(best.newtri)
        for m in ok:
            if len(extra) + 1 >= batch:
                break
            if m is best or m.kind != "tie" or m.jamo in taken_j or taken_s & set(m.newtri):
                continue
            extra.append(m)
            taken_j.add(m.jamo)
            taken_s.update(m.newtri)
    old_tri, old_fc = st.tri, st.fc
    old_bad = gate_counts(st) if extra else None
    st.fc = best.fc
    for m in extra:
        st.fc.sb.update(m.slot_change)
    normalize(st.fc)
    st.refresh()
    if extra:
        g = gate_counts(st)
        if any(g[k] > old_bad[k] for k in ("tick_all", "stroke_ks", "leak_ks", "medial_pairs_ks")):
            # the batch broke a gate together: the best move alone
            nf = old_fc.copy()
            nf.sb.update(best.slot_change)
            st.fc = normalize(nf)
            st.refresh()
            extra = []
    best.batch = len(extra) + 1
    if scorer is not None:
        changed = [s for s in range(NSYL) if st.tri[s] != old_tri[s]]
        scorer.update(st, changed)
    return best, refused


# ---- recogniser (optional) -----------------------------------------------------------------------------------------

class Scorer:
    """recog-11-12 terms per syllable: weight x (top-1 wrong + RECOG_NLL x -log p). ``delta`` of a move (None when
    a changed slot's neutral syllable, read correctly before, is misread on that jamo)."""

    def __init__(self, st, recog_dir=None, threads=1):
        import numpy as np
        import torch
        torch.set_num_threads(threads)
        sys.path.insert(0, os.path.expanduser(recog_dir or os.environ.get("SVF_RECOG_DIR", ".")))
        import recog as R
        self.np, self.R = np, R
        self.net = R.load("11-12")
        self.w, self.h = st.ref.w, st.ref.h
        self.syl = np.arange(NSYL)
        self.L, self.V, self.T = R.split(self.syl)
        self.wt = np.array(st.ref.wt)
        self.term = np.zeros(NSYL)
        self.ok = np.zeros(NSYL, bool)
        self.heads_ok = np.zeros((NSYL, 3), bool)
        self.update(st, list(range(NSYL)))
        self.base_ok = self.ok.copy()

    def arr(self, bms):
        np = self.np
        w, h = self.w, self.h
        out = np.zeros((len(bms), h, w), bool)
        for i, b in enumerate(bms):
            for y in range(h):
                row = b >> (y * w) & ((1 << w) - 1)
                if row:
                    for x in range(w):
                        if row >> x & 1:
                            out[i, y, x] = True
        return out

    def run(self, syls, bms):
        np = self.np
        if not len(syls):
            return np.zeros(0), np.zeros(0, bool), np.zeros((0, 3), bool)
        lL, lV, lT = self.R._heads(self.net, self.arr(bms))
        s = np.asarray(syls)
        i = np.arange(len(s))
        L, V, T = self.L[s], self.V[s], self.T[s]
        hk = np.stack([lL.argmax(1) == L, lV.argmax(1) == V, lT.argmax(1) == T], 1)
        ok = hk.all(1)
        nll = -(lL[i, L] + lV[i, V] + lT[i, T])
        term = self.wt[s] * ((~ok).astype(float) + RECOG_NLL * np.minimum(nll, 20.0))
        return term, ok, hk

    def update(self, st, syls):
        if not syls:
            return
        term, ok, hk = self.run(syls, [st.comp[s] for s in syls])
        self.term[syls] = term
        self.ok[syls] = ok
        self.heads_ok[syls] = hk

    def delta(self, st, m):
        syls = list(m.newtri)
        if not syls:
            return 0.0
        bms = [a | b | c for a, b, c in m.newtri.values()]
        term, ok, hk = self.run(syls, bms)
        # neutral-syllable gate per changed slot: the most neutral syllable of each (kind, jamo, new bitmap)
        seen = {}
        for idx, s in enumerate(syls):
            ljt = (s // 588, (s // 28) % 21, s % 28)
            for k, p in (("i", 0), ("m", 1), ("f", 2)):
                if (k == "f" and not ljt[2]) or m.newtri[s][p] == st.tri[s][p]:
                    continue
                key = (k, ljt[p], m.newtri[s][p])
                nk = _neutral_key(k, *ljt)
                if key not in seen or nk < seen[key][0]:
                    seen[key] = (nk, idx, p)
        for key, (_, idx, p) in seen.items():
            s = syls[idx]
            if self.heads_ok[s, p] and not hk[idx, p]:
                return None
        return float(term.sum() - self.term[syls].sum())


def _neutral_key(k, L, V, T):
    if k == "i":
        return ({0: 0, 8: 1, 9: 2}.get(V, 3), 0 if T == 0 else (1 if T == 21 else 2))
    if k == "m":
        return (0 if L == 11 else 1, 0 if T == 0 else (1 if T == 21 else 2))
    return (0 if L == 11 else 1, 0 if V == 0 else 1)


# ---- reports -------------------------------------------------------------------------------------------------------

def size_parts(fc, sizer):
    a = sizer.ascii_bytes(fc)
    bms = fc.bitmaps()
    js = sizer.jset(fc)
    return {"header": 48, "ascii": a, "ascii_glyphs": len(fc.ascii), "pieces": sum(sizer.piece_bytes(b) for b in bms),
            "n_pieces": len(bms), "jset": js, "total": sizer.size(fc, a),
            "lc": fc.lc, "tc": fc.tc, "ni": fc.nsets("i"), "nm": fc.nsets("m"), "nf": fc.nsets("f")}


def gate_counts(st):
    ks = st.ref.ks
    r = {"tick_ks": 0, "tick_all": 0, "stroke_ks": 0, "leak_ks": 0, "medial_pairs_ks": 0, "medial_pairs_all": 0,
         "exact_ks": 0, "dist_ks": 0}
    for s in range(NSYL):
        f = st.flags[s]
        r["tick_all"] += bool(f & G_TICK)
        if ks[s]:
            r["tick_ks"] += bool(f & G_TICK)
            r["stroke_ks"] += bool(f & G_STROKE)
            r["leak_ks"] += bool(f & G_LEAK)
            r["exact_ks"] += st.comp[s] == st.ref.syl[s]
            r["dist_ks"] += pop(st.comp[s] ^ st.ref.syl[s])
        for s2, need in st.ref.partners[s]:
            if s2 > s and pop(st.comp[s] ^ st.comp[s2]) < need:
                r["medial_pairs_all"] += 1
                r["medial_pairs_ks"] += ks[s] or ks[s2]
    return r


def stem_widths(fc):
    """{kind+jamo: {width: count}} of the vertical and horizontal stroke widths of the stored pieces, as drawn."""
    out = {}
    for (k, s, j), b in sorted(fc.sb.items()):
        key = k + _jname(k, j)
        e = out.setdefault(key, {"v": {}, "h": {}})
        for hv, horiz in (("v", False), ("h", True)):
            for x in F.stroke_widths(b, fc.w, fc.h, horiz):
                e[hv][str(x)] = e[hv].get(str(x), 0) + 1
    return out


def baseline_report(fc, sizer):
    p = size_parts(fc, sizer)
    js_min = J._jset_size_v1(1, 2, 1, 1, 1)
    p["fixed"] = {"header": 48, "ascii": p["ascii"], "jset_min_1x2_111": js_min,
                  "fixed_total": 48 + p["ascii"] + js_min}
    p["over_8192"] = p["total"] - 8192
    return p


# ---- CLI -----------------------------------------------------------------------------------------------------------

def load_ref(fc, planes_path=None, ref_face=None):
    syl = [fc.comp(s) for s in range(NSYL)]
    planes = None
    if planes_path:
        d = json.load(open(planes_path))
        planes = {int(s): tuple(v) for s, v in d["ks"].items()}
        for s, v in planes.items():
            syl[s] = v[0] | v[1] | v[2]
    return Ref(fc.w, fc.h, syl, planes)


def mac_planes(fbit, htbl, w=None):
    """{syllable index: (initial, medial, final) plane bitmaps (bit y*w+x)} of the KS X 1001 syllables of a Mac
    HangulTalk 7.1.x type-3 'fbit' resource and its 'HTBL' 1 (glyph =
    (bank-1)*241 + g - 0x0f, g 0x00/0x0e = no plane; planes in the entry order initial, medial, final)."""
    import struct
    h = struct.unpack(">H", fbit[0x16:0x18])[0]
    w = w or h
    gb = (h * h + 7) // 8
    base = 0x4e + 6 * struct.unpack(">H", fbit[0x4c:0x4e])[0]
    pad = gb * 8 - h * h

    def glyph(i):
        v = int.from_bytes(fbit[base + i * gb:base + (i + 1) * gb], "big") >> pad
        b = 0
        for y in range(h):
            for x in range(h):
                if v >> (h * h - 1 - (y * h + x)) & 1:
                    b |= 1 << (y * w + x)
        return b
    l1 = struct.unpack(">I", htbl[:4])[0]
    t2 = htbl[8 + l1:]
    out = {}
    for s in range(NSYL):
        ch = chr(0xAC00 + s)
        if not is_ks(s):
            continue
        hi, lo = ch.encode("euc-kr")
        i = (hi - 0xB0) * 94 + lo - 0xA1
        e = t2[i * 4:i * 4 + 4]
        gs = [(e[0] - 1) * 241 + g - 0x0F if g not in (0, 0x0E) else None for g in e[1:]]
        out[s] = tuple(glyph(g) if g is not None else 0 for g in gs)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baseline")
    b.add_argument("--face", required=True)
    b.add_argument("--planes")
    b.add_argument("-o", "--out")
    m = sub.add_parser("merge")
    m.add_argument("--face", required=True)
    m.add_argument("--planes")
    m.add_argument("--points", nargs="+", type=int, required=True, help="byte budgets to write a face at")
    m.add_argument("--recog", action="store_true", help="re-rank the best moves with recog-11-12 (torch)")
    m.add_argument("--threads", type=int, default=1)
    m.add_argument("--ref", help="reference face (default: --face itself); continue from a merged face with the "
                   "unmerged one as reference")
    m.add_argument("--batch", action="store_true", help="far over the next point, apply several disjoint ties a step "
                   "(pixel objective only)")
    m.add_argument("--start-soft", action="store_true", help="start with the stroke and leak gates soft")
    m.add_argument("--prefix", default="SM")
    m.add_argument("--soft", action="store_true",
                   help="past the gated floor, turn the stroke and leak gates into costs (tick and medial stay hard)")
    m.add_argument("-o", "--outdir", required=True)
    pl = sub.add_parser("planes", help="write the reference planes JSON from a Mac type-3 fbit + HTBL 1")
    pl.add_argument("fbit")
    pl.add_argument("htbl")
    pl.add_argument("-o", "--out", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "planes":
        d = mac_planes(open(args.fbit, "rb").read(), open(args.htbl, "rb").read())
        json.dump({"ks": {str(s): list(v) for s, v in d.items()}}, open(args.out, "w", newline="\n"))
        return 0
    log = lambda s: print(time.strftime("%H:%M:%S"), s, file=sys.stderr, flush=True)
    fc = read_face(args.face)
    sizer = Sizer(fc.w, fc.h)
    if args.cmd == "baseline":
        ref = load_ref(fc, args.planes)
        st = State(fc, ref)
        rep = baseline_report(fc, sizer)
        data = build(fc)
        rep["built_bytes"] = len(data)
        rep["verify_bad"] = len(verify(fc, data))
        rep["gates"] = gate_counts(st)
        rep["stem_widths"] = stem_widths(fc)
        txt = json.dumps(rep, ensure_ascii=False, indent=1)
        if args.out:
            open(args.out, "w", newline="\n").write(txt)
        print(txt)
        return 0
    os.makedirs(args.outdir, exist_ok=True)
    ref = load_ref(read_face(args.ref) if args.ref else fc, args.planes)
    if args.start_soft:
        ref.soft = G_STROKE | G_LEAK
    st = State(fc, ref)
    scorer = Scorer(st, threads=args.threads) if args.recog else None
    points = sorted(args.points, reverse=True)
    curve = []
    nstep = 0
    while points:
        size = sizer.size(st.fc)
        while points and size <= points[0]:
            pt = points.pop(0)
            name = f"{args.prefix}{pt // 1024}K"
            data = build(st.fc)
            bad = verify(st.fc, data)
            open(os.path.join(args.outdir, name + ".SVF"), "wb").write(data)
            rep = {"name": name, "budget": pt, "bytes": len(data), "soft_gates": bool(ref.soft), "verify_bad": len(bad), "steps": nstep,
                   **size_parts(st.fc, sizer), "gates": gate_counts(st), "stem_widths": stem_widths(st.fc)}
            if scorer is not None:
                rep["recog_weighted"] = float((scorer.ok * scorer.wt).sum() / scorer.wt.sum())
                rep["recog_ks"] = float(scorer.ok[ref.ks].mean())
            json.dump(rep, open(os.path.join(args.outdir, name + ".json"), "w"), ensure_ascii=False, indent=1)
            log(f"point {name}: {len(data)} B, pieces {rep['n_pieces']}, sets {rep['ni']}/{rep['nm']}/{rep['nf']}, "
                f"classes {rep['lc']}x{rep['tc']}, verify bad {len(bad)}")
        if not points:
            break
        batch = max(1, (size - points[0]) // 400) if args.batch else 1
        best, refused = step(st, sizer, scorer, batch=batch)
        if best is None and args.soft and not ref.soft:
            log(f"gated floor at {size} B; refused {refused}; stroke and leak gates become costs")
            data = build(st.fc)
            open(os.path.join(args.outdir, args.prefix + "-floor.SVF"), "wb").write(data)
            json.dump({"bytes": len(data), "steps": nstep, **size_parts(st.fc, sizer), "gates": gate_counts(st),
                       "refused": refused}, open(os.path.join(args.outdir, args.prefix + "-floor.json"), "w"), indent=1)
            ref.soft = G_STROKE | G_LEAK
            st.refresh()
            continue
        if best is None:
            log(f"no move left at {size} B; refused {refused}")
            data = build(st.fc)
            open(os.path.join(args.outdir, args.prefix + "-stop.SVF"), "wb").write(data)
            json.dump({"bytes": len(data), "steps": nstep, **size_parts(st.fc, sizer), "gates": gate_counts(st),
                       "refused": refused}, open(os.path.join(args.outdir, args.prefix + "-stop.json"), "w"), indent=1)
            break
        nstep += 1
        e = {"step": nstep, "soft": bool(ref.soft), "move": best.kind, "desc": best.desc, "saved": best.saved, "dpix": round(best.dpix, 2),
             "drec": round(best.drec, 4), "bytes": sizer.size(st.fc), "changed": sorted(best.newtri),
             "refused": refused}
        if scorer is not None:
            e["recog_weighted"] = round(float((scorer.ok * scorer.wt).sum() / scorer.wt.sum()), 5)
        curve.append(e)
        log(f"step {nstep}: {best.desc} saved {best.saved} dpix {best.dpix:.1f} drec {best.drec:.3f} -> {e['bytes']} B"
            f" refused {refused}")
        with open(os.path.join(args.outdir, args.prefix + "-steps.json"), "w") as fo:
            json.dump(curve, fo, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
