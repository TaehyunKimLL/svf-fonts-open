#!/usr/bin/env python3
"""Fill a jamo-set skeleton with pieces from a reference strike's jamo library, at the reference's size.

A small jamo-set face (spec/SVF.md, "Jamo-set fonts") is a skeleton - lead and tail classes, the set tables, which
slots share one piece - and the piece bitmaps. This tool keeps a skeleton and takes every piece from a *library* of
hand-drawn jamo variants of a reference bitmap font at the target size (the export ``pieces-NAME.json`` of
``galmuri_jamo.py analyse``: per initial / medial / final jamo the variants the reference draws, each a full-cell
bitmap). Nothing is rescaled or re-drawn: every piece is one of the reference's own jamo, so no stroke is dropped.

What is chosen is which variant each piece (unit) takes. The objective is the reference's own syllables: a syllable
composed from the chosen pieces (pixel OR) is compared with the reference's precomposed syllable (``NAME.npz``, the
bitmap survey strike), weighted 1.0 for the 2,350 KS X 1001 syllables and 0.2 for the rest, summed Hamming distance.
Coordinate descent over the units, each unit trying every variant of its jamo with the other pieces fixed.

Skeletons (``--skeleton``):
  FACE.SVF            the face's classes and set tables, every slot its own unit
  FACE.SVF:tied       the same, and slots whose pieces are one bitmap in FACE stay one unit (the face's sharing)
  111, 224, 621, 844  named structures: 1/1/1; 2/2/4 (initial and medial by final or not, final by the 8x4x4 vowel
                      group); 6x2x1 (jamoset.py's 621); 8x4x4 (jamoset.py's 844)
  fine                a start for ``sweep``: 2 lead (g/k or not) x 3 tail classes (none, single, double or cluster),
                      initial set per (vowel, tail class) (63), medial per (lead, tail class) (6), final per (lead,
                      vowel) (42); over the format's set limits until merged

Size: the face is written in the ``mcu-strict`` profile with a version 1 JSET block (the AVR reader) and the reference
strike's ASCII (95 glyphs, proportional). Identical piece bitmaps are stored once. ``--budget`` ties units of one jamo
(greedily, the smallest objective loss per byte saved) until the file fits.

``sweep`` merges sets greedily from a start (the merge that loses least), and writes a face, its report and its sheets at
each requested (initial, medial, final) set count. ``report`` judges a face: exact syllables, mean distance, and
identity failures - the composed syllable is no nearer its own reference syllable than to one differing in one jamo
(categories: the ㅗㅛㅜㅠㅡ family, initial ㅎ, the final, other) - and final-to-vowel contacts the reference does not
have.

  python3 tools/jamofill.py fill --strike galmuri9-12.npz --pieces pieces-galmuri9-12.json \\
      --skeleton SAM8J.SVF --budget 8192 -o SAM12U.SVF --report SAM12U.json
  python3 tools/jamofill.py sweep --strike ... --pieces ... --skeleton fine --points 8,4,4 2,2,4 1,1,1 -o OUTDIR
  python3 tools/jamofill.py sheet FACE.SVF --strike galmuri9-12.npz -o PREFIX     (PNG sheets, needs Pillow)

Pure Python but for ``sheet``. The output is a function of the inputs.
"""

import argparse
import ast
import json
import os
import struct
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jamoset as J  # noqa: E402

INI = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
MED = "".join(chr(0x314F + i) for i in range(21))
FIN = "ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"     # tail 1..27
KINDS = (("i", "initial", INI, 19), ("m", "medial", MED, 21), ("f", "final", FIN, 27))
NSYL = 11172
KS_WEIGHT, OTHER_WEIGHT = 1.0, 0.2
OUG = {8, 12, 13, 17, 18}            # ㅗ ㅛ ㅜ ㅠ ㅡ
HIEUH = 18
DOUBLE_TAILS = {2, 3, 5, 6, 9, 10, 11, 12, 13, 14, 15, 18, 20}   # ㄲ ㄳ ㄵ ㄶ ㄺ..ㅀ ㅄ ㅆ
PROFILE = "mcu-strict"
MISS = float(os.environ.get("JAMOFILL_MISS", "2"))  # a reference pixel the composition lacks costs this many extra pixels


OVERLAP = float(os.environ.get("JAMOFILL_OVERLAP", "3"))   # per pixel two pieces of a syllable both ink
OWN_GUIDED = os.environ.get("JAMOFILL_OWN", "1") == "1"   # pixel_best: a piece takes only its own jamo's pixels
TOUCH = float(os.environ.get("JAMOFILL_TOUCH", "0.25"))     # per pixel of one piece next to another's


def _bits(x):
    while x:
        low = x & -x
        yield low.bit_length() - 1
        x ^= low


def err(comp, ref):
    """The objective of one syllable: missing reference pixels count MISS, extra ink 1 (overlap is allowed, a dropped
    stroke is not)."""
    return MISS * (ref & ~comp).bit_count() + (comp & ~ref).bit_count()


def is_ks(cp):
    try:
        return len(chr(cp).encode("euc-kr")) == 2     # Python's codec writes the rest as 8-byte jamo sequences
    except UnicodeEncodeError:
        return False


# ---- inputs --------------------------------------------------------------------------------------------------------

def _npy(blob):
    if blob[:6] != b"\x93NUMPY":
        raise ValueError("not an .npy member")
    hl, off = (struct.unpack("<H", blob[8:10])[0], 10) if blob[6] == 1 else (struct.unpack("<I", blob[8:12])[0], 12)
    return ast.literal_eval(blob[off:off + hl].decode("latin1")), blob[off + hl:]


class Strike:
    """A bitmap survey strike: ``syl[n]`` the bitmap (int, bit y*w+x) of U+AC00+n; ``others`` {cp: (bitmap, adv)}."""

    def __init__(self, h, w, ascent, syl, others):
        self.h, self.w, self.ascent, self.syl, self.others = h, w, ascent, syl, others


def read_strike(path):
    """A survey ``.npz`` (``cp`` int32, ``glyphs`` uint8 [n, rows, bytes] MSB first, ``meta`` JSON with ``cell``
    [rows, cols] and ``ascent``, optional ``adv`` float32), without numpy."""
    with zipfile.ZipFile(path) as z:
        m = {n[:-4]: _npy(z.read(n)) for n in z.namelist() if n.endswith(".npy")}
    meta = json.loads(m["meta"][1].decode("utf-32-le").rstrip("\0"))
    h, w = meta["cell"]
    gh, gd = m["glyphs"]
    n, rows, nb = gh["shape"]
    if rows != h or nb != (w + 7) // 8:
        raise ValueError(f"glyphs shape {gh['shape']} does not match the cell {h}x{w}")
    cps = struct.unpack("<%di" % n, m["cp"][1])
    advs = struct.unpack("<%df" % n, m["adv"][1]) if "adv" in m else None
    syl, others = [None] * NSYL, {}
    for i, c in enumerate(cps):
        v = 0
        for y in range(h):
            o = (i * h + y) * nb
            row = int.from_bytes(gd[o:o + nb], "big") >> (nb * 8 - w)
            for x in range(w):
                if row >> (w - 1 - x) & 1:
                    v |= 1 << (y * w + x)
        if 0xAC00 <= c <= 0xD7A3:
            syl[c - 0xAC00] = v
        else:
            others[c] = (v, int(round(advs[i])) if advs else w)
    return Strike(h, w, int(meta.get("ascent", h)), syl, others)


def _npy_bytes(descr, shape, data):
    hdr = "{'descr': '%s', 'fortran_order': False, 'shape': %r, }" % (descr, tuple(shape))
    hdr += " " * (64 - (10 + len(hdr) + 1) % 64) + "\n"
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(hdr)) + hdr.encode("latin1") + data


def write_strike(path, h, w, ascent, glyphs, advances=None):
    """A survey-layout ``.npz`` (cp, glyphs, meta, adv) from {code point: bitmap}; read_strike's inverse, for tests."""
    cps = sorted(glyphs)
    nb = (w + 7) // 8
    data = bytearray()
    for c in cps:
        for y in range(h):
            row = 0
            for x in range(w):
                if glyphs[c] >> (y * w + x) & 1:
                    row |= 1 << (nb * 8 - 1 - x)
            data += row.to_bytes(nb, "big")
    meta = json.dumps({"cell": [h, w], "ascent": ascent, "bpp": 1})
    adv = [float((advances or {}).get(c, w)) for c in cps]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("cp.npy", _npy_bytes("<i4", (len(cps),), struct.pack("<%di" % len(cps), *cps)))
        z.writestr("glyphs.npy", _npy_bytes("|u1", (len(cps), h, nb), bytes(data)))
        z.writestr("meta.npy", _npy_bytes("<U%d" % len(meta), (), meta.encode("utf-32-le")))
        z.writestr("adv.npy", _npy_bytes("<f4", (len(cps),), struct.pack("<%df" % len(cps), *adv)))


def parse_rows(rows):
    v = 0
    for y, r in enumerate(rows):
        for x, ch in enumerate(r):
            if ch == "#":
                v |= 1 << (y * len(r) + x)
    return v


def read_library(path):
    """{(kind, jamo index): [bitmap, ...]} (distinct, the most used first) and the reference's own piece of each
    syllable {(kind, syllable index): bitmap}, from a ``pieces-NAME.json`` export. Jamo index: initial 0..18, vowel
    0..20, tail 1..27."""
    d = json.load(open(path))
    lib, own = {}, {}
    names = {"initial": ("i", INI, 0), "medial": ("m", MED, 0), "final": ("f", FIN, 1)}
    for slot, per in d["slots"].items():
        k, chars, base = names[slot]
        for ch, variants in per.items():
            j = chars.index(ch) + base
            seen = []
            for var in sorted(variants, key=lambda v: -v.get("uses", 0)):
                b = parse_rows(var["rows"])
                if b and b not in seen:             # a blank variant would drop the jamo
                    seen.append(b)
                for s in var.get("syllables", ""):
                    own[(k, ord(s) - 0xAC00)] = b
            lib[(k, j)] = seen
    return lib, own


VOWEL_SHAPE = (0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 2, 2, 1, 1, 2, 2, 2, 1, 1, 2, 0)   # vertical, horizontal, mixed


def _and(bs):
    a = -1
    for b in bs:
        a &= b
    return a


# decompose_strike: the bar of a horizontal vowel spans the syllable (Galmuri9: 9 of 10 columns, from row 4); a mixed
# vowel's stops at its stem (6 columns, from row 5); an initial's bottom stroke is at most 5 there
BARS = {1: (9, 4), 2: (6, 5)}


def _long_runs(b, w, h, n, y0):
    out = 0
    for y in range(y0, h):
        x = 0
        while x < w:
            if b >> (y * w + x) & 1:
                x1 = x
                while x1 < w and b >> (y * w + x1) & 1:
                    x1 += 1
                if x1 - x >= n:
                    for i in range(x, x1):
                        out |= 1 << (y * w + i)
                x = x1
            else:
                x += 1
    return out


def decompose_strike(st, min_uses=3):
    """A jamo library from the strike's own syllables: each syllable's pixels split into initial, medial and final.

    Cores first: the pixels a jamo always has in a context, less what the context's other jamo always have. Initial L
    in (vowel shape group, final group): the AND over those syllables, less the AND of the same over all initials;
    vowel V in a final group: the AND over all initials and those finals, less the AND over all vowels, and for a
    horizontal or mixed vowel every horizontal run of at least BARS' length from its row down (the vowel's bar,
    whose row follows the initial's height); final T in a
    vowel shape group: the AND over all initials and those vowels, less the AND over all finals. (Vowel shape groups:
    vertical, horizontal, mixed; final groups: none, single, double or cluster. An empty core falls back to the core
    over all groups.) Then each inked pixel of a syllable goes to the jamo whose core pixel (of this syllable's three)
    it reaches first walking over inked 8-neighbours (all three grow at once, ties to initial, medial, final in that
    order); a pixel no core reaches goes to the nearest core pixel. The three pieces OR back to the syllable.

    Returns ({(kind, jamo): [bitmap, ...]} by use, most used first; {(kind, syllable): bitmap})."""
    w, h, syl = st.w, st.h, st.syl
    tg = lambda T: 0 if T == 0 else (2 if T in DOUBLE_TAILS else 1)
    groups_t = {g: [T for T in range(28) if tg(T) == g] for g in range(3)}
    groups_v = {g: [V for V in range(21) if VOWEL_SHAPE[V] == g] for g in range(3)}
    S = lambda L, V, T: syl[L * 588 + V * 28 + T]
    core_i, core_m, core_f = {}, {}, {}
    for gv in range(3):
        for gt in range(3):
            a = {L: _and(S(L, V, T) for V in groups_v[gv] for T in groups_t[gt]) for L in range(19)}
            common = _and(a.values())
            for L in range(19):
                core_i[(L, gv, gt)] = a[L] & ~common
    for gt in range(3):
        a = {V: _and(S(L, V, T) for L in range(19) for T in groups_t[gt]) for V in range(21)}
        common = _and(a.values())
        for V in range(21):
            core_m[(V, gt)] = a[V] & ~common
    for gv in range(3):
        a = {T: _and(S(L, V, T) for L in range(19) for V in groups_v[gv]) for T in range(1, 28)}
        common = _and(a.values())
        for T in range(1, 28):
            core_f[(T, gv)] = a[T] & ~common
    # fallbacks over all groups
    fb_i = {L: _and(S(L, V, T) for V in range(21) for T in range(28)) for L in range(19)}
    fb_m = {V: _and(S(L, V, T) for L in range(19) for T in range(28)) for V in range(21)}
    fb_f = {T: _and(S(L, V, T) for L in range(19) for V in range(21)) for T in range(1, 28)}
    nb = [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy]
    count, dirty, own = {}, {}, {}
    for s in range(NSYL):
        L, V, T = s // 588, (s // 28) % 21, s % 28
        g = syl[s]
        bars = 0
        if VOWEL_SHAPE[V]:
            bars = _long_runs(g, w, h, *BARS[VOWEL_SHAPE[V]])
        seeds = [("i", (core_i[(L, VOWEL_SHAPE[V], tg(T))] or fb_i[L]) & ~bars),
                 ("m", (core_m[(V, tg(T))] | bars) or fb_m[V])]
        if T:
            seeds.append(("f", core_f[(T, VOWEL_SHAPE[V])] or fb_f[T]))
        lab = {}
        front = []
        for k, c in seeds:
            for i in range(w * h):
                if c >> i & 1 and g >> i & 1 and i not in lab:
                    lab[i] = k
                    front.append(i)
        while front:
            nxt = []
            for i in front:
                x, y = i % w, i // w
                for dx, dy in nb:
                    if 0 <= x + dx < w and 0 <= y + dy < h:
                        q = (y + dy) * w + x + dx
                        if g >> q & 1 and q not in lab:
                            lab[q] = lab[i]
                            nxt.append(q)
            front = nxt
        if lab:
            for i in range(w * h):
                if g >> i & 1 and i not in lab:
                    x, y = i % w, i // w
                    lab[i] = min((abs(x - q % w) + abs(y - q // w), "imf".index(k), k)
                                 for q, k in list(lab.items()))[2]
        # clean: a jamo whose pixels all lie in components holding only its own seed (no touching neighbour)
        seedk = {}
        for k, c in seeds:
            for i in range(w * h):
                if c >> i & 1 and g >> i & 1:
                    seedk.setdefault(i, set()).add(k)
        mixed = set()
        seen = set()
        for i0 in lab:
            if i0 in seen:
                continue
            comp, stack = [], [i0]
            seen.add(i0)
            while stack:
                i = stack.pop()
                comp.append(i)
                x, y = i % w, i // w
                for dx, dy in nb:
                    q = (y + dy) * w + x + dx
                    if 0 <= x + dx < w and 0 <= y + dy < h and q in lab and q not in seen:
                        seen.add(q)
                        stack.append(q)
            ks_ = {lab[i] for i in comp}
            if len(ks_) > 1:
                mixed |= ks_
        parts = {"i": 0, "m": 0, "f": 0}
        for i, k in lab.items():
            parts[k] |= 1 << i
        for k, j in (("i", L), ("m", V), ("f", T)):
            if k == "f" and not T:
                continue
            own[(k, s)] = parts[k]
            cc = (count if k not in mixed else dirty).setdefault((k, j), {})
            cc[parts[k]] = cc.get(parts[k], 0) + 1
    lib = {}
    for kj in set(count) | set(dirty):
        clean = [b for b, n in sorted(count.get(kj, {}).items(), key=lambda x: -x[1]) if b and n >= min_uses]
        both = {}
        for cc in (count.get(kj, {}), dirty.get(kj, {})):
            for b, n in cc.items():
                both[b] = both.get(b, 0) + n
        rest = [b for b, n in sorted(both.items(), key=lambda x: -x[1]) if b and b not in clean and n >= min_uses]
        lib[kj] = (clean + rest) or [b for b, _ in sorted(both.items(), key=lambda x: -x[1]) if b]
    return lib, own


def strokes(b, w, h, min_len=3):
    """(horizontal, vertical) stroke counts of a bitmap: maximal runs of at least @p min_len pixels in a row / column."""
    out = []
    for horiz in (True, False):
        n = 0
        for a in range(h if horiz else w):
            run = 0
            for c in range(w if horiz else h):
                x, y = (c, a) if horiz else (a, c)
                if b >> (y * w + x) & 1:
                    run += 1
                else:
                    n += run >= min_len
                    run = 0
            n += run >= min_len
        out.append(n)
    return tuple(out)


def stroke_filter(lib, st):
    """Keep the variants strokes_ok accepts (against the strike's own compatibility jamo U+3131..U+3163). A jamo whose
    every variant fails, or that has no compatibility glyph, keeps its variants."""
    out = {}
    for (k, j), vs in lib.items():
        ch = {"i": INI, "m": MED, "f": FIN}[k][j - (1 if k == "f" else 0)]
        ref = st.others.get(ord(ch))
        if ref is None:
            out[(k, j)] = vs
            continue
        keep = [b for b in vs if strokes_ok((k, j), b, st)]
        out[(k, j)] = keep or vs
    return out


def strokes_ok(kj, b, st):
    """No more horizontal strokes than the strike's compatibility jamo and at most one more vertical (a neighbour's
    stroke taken in; in a syllable a cap, bar and ring can stack into a short vertical run), and
    a capped consonant (ㅊ ㅎ) keeps cap, bar and body (cap_ok)."""
    k, j = kj
    ch = {"i": INI, "m": MED, "f": FIN}[k][j - (1 if k == "f" else 0)]
    ref = st.others.get(ord(ch))
    if ref is None:
        return True
    rh, rv = strokes(ref[0], st.w, st.h)
    hh, vv = strokes(b, st.w, st.h)
    return hh <= rh and vv <= rv + 1 and cap_ok(kj, b, st.w, st.h)


CAPPED = {("i", 14), ("i", 18), ("f", 23), ("f", 27)}      # ㅊ ㅎ as initial and final


def cap_ok(kj, b, w, h):
    """ㅊ / ㅎ: the bar (the longest horizontal run, the topmost of equals) has ink above it (the cap) and below it (the
    legs or the ring), and nothing below it is wider than it: a ㅎ that lost its bar reads as its ring under a dot."""
    if kj not in CAPPED:
        return True
    rs = _runs(b, w, h, True)
    if not rs:
        return False
    y, x0, x1 = max(rs, key=lambda r: (r[2] - r[1], -r[0]))
    above = b & ((1 << (y * w)) - 1)
    below = b >> ((y + 1) * w)
    if not above or not below:
        return False
    xs = [x for x in range(w) for yy in range(h - y - 1) if below >> (yy * w + x) & 1]
    return max(xs) - min(xs) + 1 <= x1 - x0


MEDIAL_GROUPS = ((8, 12, 13, 17, 18), (0, 2, 4, 6, 20), (1, 3, 5, 7), (9, 10, 11, 14, 15, 16, 19))
TICK_ABOVE = {8, 12, 9, 10, 11}         # ㅗ ㅛ ㅘ ㅙ ㅚ: the tick stands on the bar
TICK_BELOW = {13, 17, 14, 15, 16}       # ㅜ ㅠ ㅝ ㅞ ㅟ: the tick hangs below it
TICK_TOUCH = 0.2                        # a tick that touches another jamo, as a share of a violation
MEDIAL_PENALTY = float(os.environ.get("JAMOFILL_MEDIAL_PENALTY", "30"))   # per medial-distinctness violation


def _runs(b, w, h, horiz, min_len=3):
    """[(line, start, end)] of the runs of at least @p min_len inked pixels along rows (@p horiz) or columns."""
    out = []
    for a in range(h if horiz else w):
        n = w if horiz else h
        c = 0
        while c < n:
            if b >> ((a * w + c) if horiz else (c * w + a)) & 1:
                c0 = c
                while c < n and b >> ((a * w + c) if horiz else (c * w + a)) & 1:
                    c += 1
                if c - c0 >= min_len:
                    out.append((a, c0, c))
            else:
                c += 1
    return out


def stroke_widths(b, w, h, horiz):
    """Widths of the strokes along rows (@p horiz: horizontal strokes) or columns: runs of 3+ pixels on neighbouring
    lines that cover each other (overlap at least 3/4 of the shorter, lengths within 1) are one stroke, its width the
    number of lines."""
    groups = []
    for r in _runs(b, w, h, horiz):
        for g in groups:
            if any(abs(r[0] - q[0]) == 1 and min(r[2], q[2]) - max(r[1], q[1]) >= 0.75 * min(r[2] - r[1], q[2] - q[1])
                   and abs((r[2] - r[1]) - (q[2] - q[1])) <= 1 for q in g):
                g.append(r)
                break
        else:
            groups.append([r])
    return [len({q[0] for q in g}) for g in groups]


def width_violation(b, w, h):
    """True when parallel strokes of the piece differ in width (horizontal strokes among themselves, vertical among
    themselves): ㅍ with one 1 px and one 2 px stem, a crushed ㅃ whose bars run together."""
    return any(len(set(stroke_widths(b, w, h, horiz))) > 1 for horiz in (True, False))


def bar_and_tick(b, w, h):
    """(bar row, tick bitmap) of a medial with a horizontal bar: the longest horizontal run, and the piece's pixels in
    the rows just above and below it inside its span, as (above, below)."""
    rs = _runs(b, w, h, True)
    if not rs:
        return None, 0, 0
    y, x0, x1 = max(rs, key=lambda r: (r[2] - r[1], r[0]))
    span = sum(1 << x for x in range(x0, x1))
    above = (b >> ((y - 1) * w) & span) << ((y - 1) * w) if y > 0 else 0
    below = (b >> ((y + 1) * w) & span) << ((y + 1) * w) if y + 1 < h else 0
    return y, above, below


def tick_ok(b, V, w, h):
    """A ㅗ-type medial has a tick above its bar and none below; a ㅜ-type the other way round; ㅡ neither."""
    if V not in TICK_ABOVE and V not in TICK_BELOW and V != 18:
        return True
    _, above, below = bar_and_tick(b, w, h)
    if V == 18:
        return not above and not below
    return bool(above) and not below if V in TICK_ABOVE else bool(below) and not above


# Stroke completeness of single consonants (initial and final), by compatibility jamo: the horizontal and vertical
# strokes (runs of 2+ pixels) a piece must keep, and for the doubled ones the rows that must hold two separate bars
# ("top": the topmost ink row, "bottom": the lowest). ㅇ, ㅅ, ㅈ and the clusters are left to the recogniser gate.
COMPLETE = {"ㄱ": (1, 1, ()), "ㄲ": (2, 2, ("top",)), "ㄴ": (1, 1, ()), "ㄷ": (2, 1, ()),
            "ㄸ": (4, 2, ("top", "bottom")), "ㄹ": (3, 2, ()), "ㅁ": (2, 2, ()), "ㅂ": (1, 2, ()),
            "ㅃ": (2, 4, ("bottom",)), "ㅊ": (1, 0, ()), "ㅋ": (2, 1, ()), "ㅌ": (3, 1, ()), "ㅍ": (2, 2, ()),
            "ㅎ": (1, 0, ())}


def _row_runs(b, w, y, n=2):
    row = [b >> (y * w + x) & 1 for x in range(w)] + [0]
    runs, c = 0, 0
    for v in row:
        if v:
            c += 1
        else:
            runs += c >= n
            c = 0
    return runs


def complete_ok(kj, b, w, h):
    """Stroke completeness (COMPLETE): a consonant keeps its horizontal and vertical strokes of 2+ pixels, and ㄲ ㄸ ㅃ
    keep two separate bars (2+ pixels each) in their top / bottom ink rows. Vowels and clusters always pass."""
    if kj[0] == "m":
        return True
    ch = (INI if kj[0] == "i" else FIN)[kj[1] - (1 if kj[0] == "f" else 0)]
    rule = COMPLETE.get(ch)
    if rule is None:
        return True
    rh, rv, rows = rule
    hh, vv = strokes(b, w, h, 2)
    if hh < rh or vv < rv:
        return False
    ys = [y for y in range(h) if b >> (y * w) & ((1 << w) - 1)]
    if not ys:
        return False
    for which in rows:
        if _row_runs(b, w, ys[0] if which == "top" else ys[-1]) < 2:
            return False
    return True


def split_double(kj, b, w, h):
    """A ㄲ / ㄸ / ㅃ whose two bars in a required row run together: the same piece with the run cut in its middle
    (one pixel cleared), or None when nothing to cut. The repaired piece is offered as an extra candidate."""
    if kj[0] == "m":
        return None
    ch = (INI if kj[0] == "i" else FIN)[kj[1] - (1 if kj[0] == "f" else 0)]
    rule = COMPLETE.get(ch)
    if not rule or not rule[2]:
        return None
    ys = [y for y in range(h) if b >> (y * w) & ((1 << w) - 1)]
    if not ys:
        return None
    out = b
    for which in rule[2]:
        y = ys[0] if which == "top" else ys[-1]
        if _row_runs(out, w, y) >= 2:
            continue
        xs = [x for x in range(w) if out >> (y * w + x) & 1]
        if len(xs) < 5:
            return None
        mid = (xs[0] + xs[-1] + 1) // 2
        out &= ~(1 << (y * w + mid))
    return out if out != b else None


def piece_ok(kj, b, w, h):
    """The piece-level hard gates: parallel strokes of one width; a medial's tick on the right side of its bar; a
    consonant's strokes complete (complete_ok)."""
    if width_violation(b, w, h) or not complete_ok(kj, b, w, h):
        return False
    return kj[0] != "m" or tick_ok(b, kj[1], w, h)


def shape_filter(lib, st):
    """lib with ㄲ ㄸ ㅃ pieces whose bars run together repaired (split_double, added beside them), less the variants
    piece_ok refuses; a jamo whose every variant fails keeps them (reported by judge)."""
    out = {}
    for kj, vs in lib.items():
        vs = list(vs)
        for b in list(vs):
            r = split_double(kj, b, st.w, st.h)
            if r is not None and r not in vs:
                vs.append(r)
        keep = [b for b in vs if piece_ok(kj, b, st.w, st.h)]
        out[kj] = keep or vs
    return out


LEAK_PENALTY = float(os.environ.get("JAMOFILL_LEAK_PENALTY", "40"))   # per leaked pixel per user syllable


def leak_masks(own, w, h, mine=0.05, theirs=0.3):
    """{(kind, jamo, vowel shape, final group): (allowed mask, {pixel: neighbour (kind, jamo)})} from the reference
    split: in that context a pixel the jamo inks in fewer than @p mine of its syllables while another jamo of the same
    syllables inks it in at least @p theirs is a leak (outside the allowed mask); the neighbour is the jamo that inks
    it most there."""
    tg = lambda T: 0 if T == 0 else (2 if T in DOUBLE_TAILS else 1)
    groups = {}
    for (k, s), b in own.items():
        L, V, T = s // 588, (s // 28) % 21, s % 28
        j = {"i": L, "m": V, "f": T}[k]
        groups.setdefault((k, j, VOWEL_SHAPE[V], tg(T)), []).append(s)
    out = {}
    n = w * h
    for key, ss in groups.items():
        k = key[0]
        mine_c = [0] * n
        theirs_c = {}
        for s in ss:
            for i in _bits(own[(k, s)]):
                mine_c[i] += 1
            L, V, T = s // 588, (s // 28) % 21, s % 28
            for k2, j2 in (("i", L), ("m", V), ("f", T)):
                if k2 == k or (k2 == "f" and not T):
                    continue
                for i in _bits(own.get((k2, s), 0)):
                    d = theirs_c.setdefault(i, {})
                    d[(k2, j2)] = d.get((k2, j2), 0) + 1
        allowed, who = 0, {}
        for i in range(n):
            tot = sum(theirs_c.get(i, {}).values())
            if mine_c[i] < mine * len(ss) and tot >= theirs * len(ss):
                d = theirs_c[i]
                who[i] = max(sorted(d), key=d.get)
            else:
                allowed |= 1 << i
        out[key] = (allowed, who)
    return out


def consensus_library(own, share=0.5):
    """Prototype pieces: for each jamo and each context grouping, the pixels at least @p share of the syllables of the
    group give that jamo (``own``, decompose_strike's split). A rare misassignment (a neighbour's stroke taken in, a
    stroke given away) is outvoted. Groupings: initial by (vowel, final group), (vowel shape, final group), vowel;
    medial by (initial, final group), final group, (initial, final); final by vowel, vowel shape, (initial, vowel
    shape). The prototypes of a jamo are ordered by how many syllables they stand for."""
    tg = lambda T: 0 if T == 0 else (2 if T in DOUBLE_TAILS else 1)
    keys = {
        "i": [lambda L, V, T: (V, tg(T)), lambda L, V, T: (VOWEL_SHAPE[V], tg(T)), lambda L, V, T: V],
        "m": [lambda L, V, T: (L, tg(T)), lambda L, V, T: tg(T), lambda L, V, T: (L, T)],
        "f": [lambda L, V, T: V, lambda L, V, T: VOWEL_SHAPE[V], lambda L, V, T: (L, VOWEL_SHAPE[V])],
    }
    groups = {}
    for (k, s), b in own.items():
        L, V, T = s // 588, (s // 28) % 21, s % 28
        j = {"i": L, "m": V, "f": T}[k]
        for gi, f in enumerate(keys[k]):
            groups.setdefault((k, j, gi, f(L, V, T)), []).append(b)
    weight = {}
    for (k, j, _, _), bs in groups.items():
        n = len(bs)
        cnt = {}
        for b in bs:
            while b:
                low = b & -b
                cnt[low] = cnt.get(low, 0) + 1
                b ^= low
        proto = 0
        for bit, c in cnt.items():
            if c >= share * n and c * 2 > 0:
                proto |= bit
        if proto:
            d = weight.setdefault((k, j), {})
            d[proto] = d.get(proto, 0) + n
    return {kj: [b for b, _ in sorted(d.items(), key=lambda x: -x[1])] for kj, d in weight.items()}


def merge_libraries(libs, per_jamo):
    """One library from several (lib, own) pairs: per jamo the first @p per_jamo variants of each, in order, without
    repeats; ``own`` from the first."""
    lib = {}
    for lb, _ in libs:
        for kj, vs in lb.items():
            out = lib.setdefault(kj, [])
            for b in vs[:per_jamo]:
                if b not in out:
                    out.append(b)
    return lib, libs[0][1] if libs else {}


# ---- skeletons -----------------------------------------------------------------------------------------------------

def _table(lc, tc, ni, nm, nf, lead, tail, iset, mset, fset):
    t = J.Tables(lc, tc, ni, nm, nf)
    t.lead_class = [lead(L) for L in range(19)]
    t.tail_class = [tail(T) for T in range(28)]
    tails = {t.tail_class[T] for T in range(1, 28)}
    for a in range(lc):
        for v in range(21):
            for b in range(tc):
                c = (a * 21 + v) * tc + b
                t.init_set[c], t.med_set[c] = iset(a, v, b), mset(a, v, b)
                t.fin_set[c] = fset(a, v, b) if b in tails else 0
    return t


def named_skeleton(name):
    if name in ("844", "621"):
        return J.tables_for(J.LAYOUTS[name])
    has = lambda T: 1 if T else 0
    if name == "111":
        return _table(1, 1, 1, 1, 1, lambda L: 0, lambda T: 0, lambda a, v, b: 0, lambda a, v, b: 0,
                      lambda a, v, b: 0)
    if name == "224":
        return _table(1, 2, 2, 2, 4, lambda L: 0, has, lambda a, v, b: b, lambda a, v, b: b,
                      lambda a, v, b: J.F844[v])
    if name == "fine":
        return _table(2, 3, 63, 6, 42, J._kk_class,
                      lambda T: 0 if T == 0 else (2 if T in DOUBLE_TAILS else 1),
                      lambda a, v, b: v * 3 + b, lambda a, v, b: a * 3 + b, lambda a, v, b: a * 21 + v)
    raise ValueError(f"unknown skeleton {name!r}")


def face_skeleton(path, tied):
    """The classes and set tables of a jamo-set face, and (``tied``) a unit per distinct piece bitmap."""
    f = J.parse_svfn(open(path, "rb").read())
    if f.jset is None:
        raise ValueError(f"{path}: no usable JSET block")
    t = J.unpack(f.jset)
    if isinstance(t, J.Jmap):
        raise ValueError(f"{path}: a JMAP or LIST face (JSET version 3) has no set tables; jamofill reads set-table faces")
    tie = None
    if tied:
        tie, ids = {}, {}
        for k, _, _, n in KINDS:
            lst = {"i": t.init_piece, "m": t.med_piece, "f": t.fin_piece}[k]
            for idx, p in enumerate(lst):
                if p != J.BLANK:
                    s, j = divmod(idx, n)
                    g = f.glyphs[J.PIECE_BASE + p]
                    tie[(k, s, j + (1 if k == "f" else 0))] = ("g", ids.setdefault(g, len(ids)))
    return t, tie


def skeleton(spec):
    if spec.lower().endswith(":tied"):
        return face_skeleton(spec[:-5], True)
    if spec.lower().endswith(".svf"):
        return face_skeleton(spec, False)
    return named_skeleton(spec), None


def syl_slots(t, s):
    """The slots (kind, set, jamo) syllable index @p s draws from."""
    L, V, T = s // 588, (s // 28) % 21, s % 28
    c = (t.lead_class[L] * 21 + V) * t.tc + t.tail_class[T]
    out = [("i", t.init_set[c], L), ("m", t.med_set[c], V)]
    if T:
        out.append(("f", t.fin_set[c], T))
    return out


# ---- the fill ------------------------------------------------------------------------------------------------------

class Problem:
    def __init__(self, strike, lib, own=None):
        if any(g is None for g in strike.syl):
            raise ValueError("the strike lacks syllables")
        self.st, self.lib, self.own = strike, lib, own or {}
        self.tgt = strike.syl
        self.wt = [KS_WEIGHT if is_ks(0xAC00 + s) else OTHER_WEIGHT for s in range(NSYL)]
        self.pitch = (strike.w + 7) // 8
        self._pb = {}
        self._dil = {}
        w, h = strike.w, strike.h
        self._full = (1 << (w * h)) - 1
        self._left = sum(1 << (y * w) for y in range(h)) * ((1 << (w - 1)) - 1)
        # medial distinctness: each syllable's partners (same initial and final, another vowel of its group) and the
        # pixel distance the pair must keep: min(2, the reference pair's distance)
        grp = {V: g for g in MEDIAL_GROUPS for V in g}
        self.partners = []
        for s in range(NSYL):
            L, V, T = s // 588, (s // 28) % 21, s % 28
            self.partners.append([(s2, min(2, (self.tgt[s] ^ self.tgt[s2]).bit_count()))
                                  for s2 in (L * 588 + V2 * 28 + T for V2 in grp[V] if V2 != V)])
        self._tick = {}
        self.leaks = leak_masks(self.own, w, h) if self.own else {}

    def tick(self, b, V):
        """The tick pixels of medial bitmap @p b of vowel @p V on its proper side (0 when V has none)."""
        key = (b, V)
        t = self._tick.get(key)
        if t is None:
            _, above, below = bar_and_tick(b, self.st.w, self.st.h)
            t = above if V in TICK_ABOVE else below if V in TICK_BELOW else 0
            self._tick[key] = t
        return t

    def dilate4(self, b):
        w = self.st.w
        return b | (b << 1 & self._left << 1) | (b >> 1 & self._left) | (b << w & self._full) | (b >> w)

    def dilate(self, b):
        """@p b grown by one pixel in the 8-neighbourhood (inside the cell)."""
        d = self._dil.get(b)
        if d is None:
            w = self.st.w
            d = b | (b << 1 & self._left << 1) | (b >> 1 & self._left)
            d = d | (d << w & self._full) | (d >> w)
            self._dil[b] = d
        return d

    def cell(self, b):
        """Packed cell bytes (rows MSB first, ``pitch`` bytes a row) of a bitmap."""
        w, out = self.st.w, bytearray()
        for y in range(self.st.h):
            row = 0
            for x in range(w):
                if b >> (y * w + x) & 1:
                    row |= 1 << (self.pitch * 8 - 1 - x)
            out += row.to_bytes(self.pitch, "big")
        return bytes(out)

    def piece_bytes(self, b):
        """File bytes one stored piece costs in mcu-strict: code point entry, metrics, u16 offset, record."""
        if b in self._pb:
            return self._pb[b]
        pr = J.profile_of(PROFILE)
        self._pb[b] = v = 8 + 4 + 2 + len(J.encode_record(self.cell(b), self.pitch, self.st.h, pr.box, pr.rec, pr.row))
        return v


class Fill:
    """Units (a tie of slots) with one bitmap each; unit ``u`` is drawn by syllables ``users[u]``."""

    def __init__(self, prob, t, tie=None, pixel=False):
        self.p, self.t, self.pixel = prob, t, pixel
        self.slot_unit = {}
        self.users = {}
        self.syl_units = []
        for s in range(NSYL):
            us = []
            for sl in syl_slots(t, s):
                u = tie.get(sl, sl) if tie else sl
                self.slot_unit[sl] = u
                self.users.setdefault(u, []).append(s)
                us.append(u)
            self.syl_units.append(us)
        self.jamo = {}
        for sl, u in self.slot_unit.items():
            kj = (sl[0], sl[2])
            if self.jamo.setdefault(u, kj) != kj:
                raise ValueError(f"unit {u} ties slots of two jamo: {self.jamo[u]} and {kj}")
        for u, kj in self.jamo.items():
            if not prob.lib.get(kj):
                raise ValueError(f"the library has no {kj} variant")
        self.bmp = {}
        for u in self.users:
            self.bmp[u] = self.cands(u)[self._best0(u)]

    def cands(self, u):
        return self.p.lib[self.jamo[u]]

    def _best0(self, u):
        tgt, wt = self.p.tgt, self.p.wt
        best, bi = None, 0
        for i, c in enumerate(self.cands(u)):
            v = sum(wt[s] * err(c, tgt[s]) for s in self.users[u])
            if best is None or v < best:
                best, bi = v, i
        return bi

    def rest(self, s, u):
        r = 0
        for x in self.syl_units[s]:
            if x != u:
                r |= self.bmp[x]
        return r

    def comp_with(self, s, u, c):
        """Syllable @p s composed with unit @p u drawn as @p c."""
        r = 0
        for x in self.syl_units[s]:
            r |= c if x == u else self.bmp[x]
        return r

    def medial_violations(self, s, u=None, c=None):
        """Medial-distinctness violations of syllable @p s (unit @p u drawn as @p c when given): partners closer than
        they must stay, plus 1 when its tick (ㅗ/ㅜ types) is merged: every tick pixel inked or 4-touched by the other
        pieces."""
        p = self.p
        g = self.comp_with(s, u, c)
        n = sum(1 for s2, need in p.partners[s] if (g ^ self.comp_with(s2, u, c)).bit_count() < need)
        V = (s // 28) % 21
        if V in TICK_ABOVE or V in TICK_BELOW:
            us = self.syl_units[s]
            m = c if us[1] == u else self.bmp[us[1]]
            o = 0
            for x in (us[0],) + tuple(us[2:]):
                o |= c if x == u else self.bmp[x]
            t = p.tick(m, V)
            if not t or not (t & ~o):
                n += 1                                  # tick missing or covered: a hard violation
            elif not (t & ~p.dilate4(o)):
                n += TICK_TOUCH                         # tick only touching another jamo: a soft one
        return n

    def leak_mask(self, u):
        """The pixels unit @p u may ink: the AND of the allowed masks (leak_masks) over its users' contexts weighted by
        how many users each context has; a pixel allowed in the contexts of at least half the users is allowed."""
        m = self._leakmask.get(u) if hasattr(self, "_leakmask") else None
        if m is not None:
            return m
        if not hasattr(self, "_leakmask"):
            self._leakmask = {}
        tg = lambda T: 0 if T == 0 else (2 if T in DOUBLE_TAILS else 1)
        k, j = self.jamo[u]
        cnt = {}
        for s in self.users[u]:
            V, T = (s // 28) % 21, s % 28
            key = (k, j, VOWEL_SHAPE[V], tg(T))
            cnt[key] = cnt.get(key, 0) + 1
        n = self.p.st.w * self.p.st.h
        votes = [0] * n
        total = sum(cnt.values())
        for key, c in cnt.items():
            allowed = self.p.leaks.get(key, ((1 << n) - 1, {}))[0]
            for i in _bits(allowed):
                votes[i] += c
        m = 0
        for i, v in enumerate(votes):
            if v * 2 >= total:
                m |= 1 << i
        self._leakmask[u] = m
        return m

    def costvec(self, u):
        """Objective over the users of @p u for each candidate, the other pieces fixed: err against the reference,
        OVERLAP per pixel the candidate shares with the other pieces, TOUCH per pixel of theirs it touches,
        MEDIAL_PENALTY per medial-distinctness violation (medial_violations; unweighted: a hard gate), LEAK_PENALTY per
        leaked pixel (outside leak_mask) per user, and a banned candidate (``banned``, set by the recogniser loop)
        never wins."""
        tgt, wt = self.p.tgt, self.p.wt
        rs = [(s, self.rest(s, u), tgt[s], wt[s]) for s in self.users[u]]
        dil = self.p.dilate
        out = []
        lm = self.leak_mask(u) if self.p.leaks and LEAK_PENALTY else None
        ban = getattr(self, "banned", {}).get(u, ())
        for c in self.cands(u):
            if c in ban:
                out.append(1e18)
                continue
            v = sum(w * (err(r | c, g) + OVERLAP * (c & r).bit_count() + TOUCH * (dil(c) & r & ~c).bit_count())
                    for _, r, g, w in rs)
            if lm is not None:
                v += LEAK_PENALTY * (c & ~lm).bit_count() * len(rs)
            if MEDIAL_PENALTY:
                v += MEDIAL_PENALTY * sum(self.medial_violations(s, u, c) for s, _, _, _ in rs)
            out.append(v)
        return out

    def pixel_best(self, u):
        """The bitmap for unit @p u that is best pixel by pixel with the other pieces fixed (err and OVERLAP; TOUCH is
        left to the candidate choice): a pixel is inked when the weight of the users whose reference has it and whose
        other pieces lack it, times MISS, outweighs the weight of those whose reference lacks it (extra ink) plus
        OVERLAP times the weight of those whose other pieces have it."""
        n = self.p.st.w * self.p.st.h
        gain = [0.0] * n
        k = self.jamo[u][0]
        own = self.p.own if OWN_GUIDED else None
        for s in self.users[u]:
            r, g, w = self.rest(s, u), self.p.tgt[s], self.p.wt[s]
            want = g & ~r
            if own is not None and (k, s) in own:
                want &= own[(k, s)]          # only the pixels the reference split gives this jamo
            extra = ~g & ~r
            for i in _bits(want):
                gain[i] += MISS * w
            for i in _bits(extra & ((1 << n) - 1)):
                gain[i] -= w
            for i in _bits(r):
                gain[i] -= OVERLAP * w
        b = 0
        for i, v in enumerate(gain):
            if v > 0:
                b |= 1 << i
        return b

    def descend(self, units=None, sweeps=20):
        units = list(units if units is not None else self.users)
        for _ in range(sweeps):
            changed = 0
            for u in units:
                if self.pixel:
                    b = self.pixel_best(u)
                    pool = self.cands(u)
                    if (b and b not in pool and piece_ok(self.jamo[u], b, self.p.st.w, self.p.st.h)
                            and strokes_ok(self.jamo[u], b, self.p.st)):
                        pool.append(b)
                    r2 = split_double(self.jamo[u], b, self.p.st.w, self.p.st.h) if b else None
                    if r2 is not None and r2 not in pool and piece_ok(self.jamo[u], r2, self.p.st.w, self.p.st.h):
                        pool.append(r2)
                cv = self.costvec(u)
                bi = min(range(len(cv)), key=cv.__getitem__)
                c = self.cands(u)[bi]
                if c != self.bmp[u]:
                    self.bmp[u] = c
                    changed += 1
            if not changed:
                break

    def comp(self, s):
        r = 0
        for u in self.syl_units[s]:
            r |= self.bmp[u]
        return r

    def cost(self):
        tgt, wt, dil = self.p.tgt, self.p.wt, self.p.dilate
        total = 0.0
        for s in range(NSYL):
            ps = [self.bmp[u] for u in self.syl_units[s]]
            c = sum(OVERLAP * (a & b).bit_count() + TOUCH * ((dil(a) & b & ~a).bit_count() + (dil(b) & a & ~b).bit_count()) / 2
                    for i, a in enumerate(ps) for b in ps[i + 1:])
            total += wt[s] * (err(self.comp(s), tgt[s]) + c) + MEDIAL_PENALTY * self.medial_violations(s)
        return total

    # -- ties and merges --

    def tie(self, a, b, bitmap=None):
        """Make unit @p b part of unit @p a (one bitmap, chosen best for both unless given)."""
        if a == b:
            return
        if bitmap is None:
            ca, cb = self.costvec(a), self.costvec(b)
            bi = min(range(len(ca)), key=lambda i: ca[i] + cb[i])
            bitmap = self.cands(a)[bi]
        for sl, u in self.slot_unit.items():
            if u == b:
                self.slot_unit[sl] = a
        self.users[a] = sorted(self.users[a] + self.users.pop(b))
        for s in range(NSYL):
            us = self.syl_units[s]
            if b in us:
                self.syl_units[s] = [a if x == b else x for x in us]
        self.bmp[a] = bitmap
        del self.bmp[b]
        del self.jamo[b]

    def merge_sets(self, kind, a, b):
        """Merge set @p b of table @p kind into set @p a: tie their units jamo by jamo, point the set table at a and
        renumber the sets above b."""
        units = {}
        for (k, s, j), u in self.slot_unit.items():
            if k == kind and s in (a, b):
                units.setdefault(j, {})[s] = u
        for j, m in units.items():
            if a in m and b in m:
                self.tie(m[a], m[b])
        new = {}
        for (k, s, j), u in self.slot_unit.items():
            if k == kind and s >= b:
                s2 = a if s == b else s - 1
                new[(k, s2, j)] = u
            else:
                new[(k, s, j)] = u
        self.slot_unit = new
        lst = {"i": self.t.init_set, "m": self.t.med_set, "f": self.t.fin_set}[kind]
        for c, s in enumerate(lst):
            lst[c] = a if s == b else (s - 1 if s > b else s)
        if kind == "i":
            self.t.ni -= 1
        elif kind == "m":
            self.t.nm -= 1
        else:
            self.t.nf -= 1

    def set_merge_deltas(self):
        """[(objective delta, kind, a, b)] of every set merge, from the cost vectors of the present state."""
        cv = {u: self.costvec(u) for u in self.users}
        cur = {u: cv[u][self.cands(u).index(self.bmp[u])] for u in self.users}
        per = {}
        for (k, s, j), u in self.slot_unit.items():
            per.setdefault((k, s), {})[j] = u
        out = []
        for k, _, _, _ in KINDS:
            sets = sorted(s for (kk, s) in per if kk == k)
            for i, a in enumerate(sets):
                for b in sets[i + 1:]:
                    d = 0.0
                    for j, ua in per[(k, a)].items():
                        ub = per[(k, b)].get(j)
                        if ub is None or ub == ua:
                            continue
                        va, vb = cv[ua], cv[ub]
                        d += min(x + y for x, y in zip(va, vb)) - cur[ua] - cur[ub]
                    out.append((d, k, a, b))
        return out

    # -- the face --

    def pieces(self):
        """The distinct bitmaps in first-use order (initial, medial, final slots) and {bitmap: piece number}."""
        order = {}
        for sl in sorted(self.slot_unit):
            b = self.bmp[self.slot_unit[sl]]
            order.setdefault(b, len(order))
        return list(order), order

    def compact(self):
        """A Tables with the sets merged where every jamo they both draw has one bitmap, then lead and tail classes
        merged where the set tables agree; piece numbers by ``pieces``. Returns (Tables, {bitmap: piece})."""
        _, num = self.pieces()
        t0 = self.t
        slot_b = {sl: self.bmp[u] for sl, u in self.slot_unit.items()}
        lists = {"i": t0.init_set, "m": t0.med_set, "f": t0.fin_set}
        counts = {"i": t0.ni, "m": t0.nm, "f": t0.nf}
        remap = {}
        rows = {}
        for k, _, _, n in KINDS:
            groups = []                     # [(new set, {jamo: bitmap})]
            m = {}
            used = sorted({s for (kk, s, _) in slot_b if kk == k})
            for s in used:
                row = {j: b for (kk, ss, j), b in slot_b.items() if kk == k and ss == s}
                for gi, g in enumerate(groups):
                    if all(g.get(j, b) == b for j, b in row.items()):
                        g.update(row)
                        m[s] = gi
                        break
                else:
                    m[s] = len(groups)
                    groups.append(dict(row))
            for s in range(counts[k]):
                m.setdefault(s, 0)
            remap[k], rows[k] = m, groups
        lc0, tc0 = t0.lc, t0.tc
        tails = {t0.tail_class[T] for T in range(1, 28)}

        def key_lead(a):
            return tuple((remap["i"][t0.init_set[(a * 21 + v) * tc0 + b]], remap["m"][t0.med_set[(a * 21 + v) * tc0 + b]],
                          remap["f"][t0.fin_set[(a * 21 + v) * tc0 + b]] if b in tails else None)
                         for v in range(21) for b in range(tc0))
        used_leads = sorted({t0.lead_class[L] for L in range(19)})
        lmap, lkeys = {}, []
        for a in used_leads:
            k_ = key_lead(a)
            if k_ in lkeys:
                lmap[a] = lkeys.index(k_)
            else:
                lmap[a] = len(lkeys)
                lkeys.append(k_)

        def col(b):
            return [(remap["i"][t0.init_set[(a * 21 + v) * tc0 + b]], remap["m"][t0.med_set[(a * 21 + v) * tc0 + b]],
                     remap["f"][t0.fin_set[(a * 21 + v) * tc0 + b]] if b in tails else None)
                    for a in used_leads for v in range(21)]
        used_tails = sorted({t0.tail_class[T] for T in range(28)})
        tmap, tcols = {}, []
        for b in used_tails:
            c = col(b)
            for i, (bs, cc) in enumerate(tcols):
                if all(x[:2] == y[:2] and (x[2] is None or y[2] is None or x[2] == y[2]) for x, y in zip(c, cc)):
                    tmap[b] = i
                    tcols[i] = (bs + [b], [y if y[2] is not None else x for x, y in zip(c, cc)])
                    break
            else:
                tmap[b] = len(tcols)
                tcols.append(([b], c))
        lc, tc = len(lkeys), len(tcols)
        ni, nm, nf = (max(1, len(rows[k])) for k in "imf")
        t = J.Tables(lc, tc, ni, nm, nf)
        t.lead_class = [lmap[t0.lead_class[L]] for L in range(19)]
        t.tail_class = [tmap[t0.tail_class[T]] for T in range(28)]
        new_tails = {t.tail_class[T] for T in range(1, 28)}
        for a in used_leads:
            for v in range(21):
                for b in used_tails:
                    c0 = (a * 21 + v) * tc0 + b
                    c = (lmap[a] * 21 + v) * tc + tmap[b]
                    t.init_set[c] = remap["i"][t0.init_set[c0]]
                    t.med_set[c] = remap["m"][t0.med_set[c0]]
                    if tmap[b] in new_tails and b in tails:
                        t.fin_set[c] = remap["f"][t0.fin_set[c0]]
        for k, _, _, n in KINDS:
            lst = {"i": t.init_piece, "m": t.med_piece, "f": t.fin_piece}[k]
            off = 1 if k == "f" else 0
            for s, g in enumerate(rows[k]):
                for j, b in g.items():
                    lst[s * n + j - off] = num[b]
        for idx, (kind, i) in enumerate(J.COMPAT):
            k, n, off = {"i": ("i", 19, 0), "v": ("m", 21, 0), "f": ("f", 27, 1)}[kind]
            lst = {"i": t.init_piece, "m": t.med_piece, "f": t.fin_piece}[k]
            t.compat[idx] = next((lst[s * n + i - off] for s in range(len(rows[k]))
                                  if lst[s * n + i - off] != J.BLANK), J.BLANK)
        return t, num


def ascii_glyphs(prob):
    """[(cp, bitmap, advance, bearing, ink width)] of the strike's printable ASCII."""
    out = []
    w = prob.st.w
    for cp in range(0x20, 0x7F):
        if cp not in prob.st.others:
            continue
        b, adv = prob.st.others[cp]
        xs = [x for x in range(w) for y in range(prob.st.h) if b >> (y * w + x) & 1]
        out.append((cp, b, adv, min(xs) if xs else 0, max(xs) - min(xs) + 1 if xs else 0))
    return out


def plain_tables(fill):
    """The fill's own tables, sets and classes as they are (no compaction: sets whose pieces agree stay apart), with
    piece numbers by ``pieces``; a set slot no syllable draws is blank. Returns (Tables, {bitmap: piece})."""
    _, num = fill.pieces()
    t0 = fill.t
    t = J.Tables(t0.lc, t0.tc, t0.ni, t0.nm, t0.nf, t0.advance)
    t.lead_class, t.tail_class = list(t0.lead_class), list(t0.tail_class)
    t.init_set, t.med_set, t.fin_set = list(t0.init_set), list(t0.med_set), list(t0.fin_set)
    tails = {t.tail_class[T] for T in range(1, 28)}
    for c in range(len(t.fin_set)):
        if c % t.tc not in tails:
            t.fin_set[c] = 0
    for (k, s, j), u in fill.slot_unit.items():
        lst, n, off = {"i": (t.init_piece, 19, 0), "m": (t.med_piece, 21, 0), "f": (t.fin_piece, 27, 1)}[k]
        lst[s * n + j - off] = num[fill.bmp[u]]
    for idx, (kind, i) in enumerate(J.COMPAT):
        k, n, off = {"i": ("i", 19, 0), "v": ("m", 21, 0), "f": ("f", 27, 1)}[kind]
        lst, cnt = {"i": (t.init_piece, t.ni), "m": (t.med_piece, t.nm), "f": (t.fin_piece, t.nf)}[k]
        t.compat[idx] = next((lst[s * n + i - off] for s in range(cnt) if lst[s * n + i - off] != J.BLANK), J.BLANK)
    return t, num


def build_face(fill, compact=True):
    """The SVFN v3 face (mcu-strict, JSET v1) of a fill: the strike's ASCII and the distinct pieces. @p compact False
    keeps the fill's sets and classes as they are (plain_tables)."""
    p = fill.p
    t, num = fill.compact() if compact else plain_tables(fill)
    glyphs = [(cp, p.cell(b), adv, bx, iw) for cp, b, adv, bx, iw in ascii_glyphs(p)]
    w = p.st.w
    for b, n in sorted(num.items(), key=lambda x: x[1]):
        xs = [x for x in range(w) for y in range(p.st.h) if b >> (y * w + x) & 1]
        glyphs.append((J.PIECE_BASE + n, p.cell(b), w, min(xs), max(xs) - min(xs) + 1))
    try:
        block = J.pack_v1(t)
    except ValueError as e:      # jamofill has no --jset-big: it writes the standard JSET only
        raise ValueError(f"{e}; jamofill writes JSET within the standard limits only") from e
    return J.write_svfn(w, p.st.h, p.st.ascent, glyphs, block, profile=PROFILE)


def size_estimate(fill, ascii_bytes=None):
    """Bytes of build_face's file without writing it (the JSET block of the compacted tables)."""
    p = fill.p
    t, _ = fill.compact()
    bitmaps, _ = fill.pieces()
    if ascii_bytes is None:
        ascii_bytes = sum(p.piece_bytes(b) for _, b, *_ in ascii_glyphs(p))
    n = len(ascii_glyphs(p)) + len(bitmaps)
    js = J._jset_size_v1(t.lc, t.tc, t.ni, t.nm, t.nf)
    return 48 + ascii_bytes + sum(p.piece_bytes(b) for b in bitmaps) + (-js % 4) + js + (-(2 * (n + 1)) % 4) + 2


def fit_budget(fill, budget, log=None):
    """Tie units of one jamo until the face fits @p budget bytes: each step the tie with the least objective loss per
    byte saved. Returns the number of ties."""
    p = fill.p
    abytes = sum(p.piece_bytes(b) for _, b, *_ in ascii_glyphs(p))
    pb = {}
    n = 0
    while True:
        size = size_estimate(fill, abytes)
        if size <= budget:
            return n
        cv = {u: fill.costvec(u) for u in fill.users}
        cur = {u: cv[u][fill.cands(u).index(fill.bmp[u])] for u in fill.users}
        uses = {}
        for u, b in fill.bmp.items():
            uses[b] = uses.get(b, 0) + 1
        found = []
        byj = {}
        for u, kj in fill.jamo.items():
            byj.setdefault(kj, []).append(u)
        for kj, us in byj.items():
            for i, a in enumerate(us):
                for b in us[i + 1:]:
                    va, vb = cv[a], cv[b]
                    bi = min(range(len(va)), key=lambda x: va[x] + vb[x])
                    c = fill.cands(a)[bi]
                    d = va[bi] + vb[bi] - cur[a] - cur[b]
                    after = dict(uses)
                    for x in (fill.bmp[a], fill.bmp[b]):
                        after[x] -= 1
                    after[c] = after.get(c, 0) + 1
                    saved = sum(pb.setdefault(x, p.piece_bytes(x)) for x in uses if after.get(x, 0) == 0) \
                        - (pb.setdefault(c, p.piece_bytes(c)) if uses.get(c, 0) == 0 else 0)
                    if saved <= 0:
                        continue
                    found.append((d / saved, a, b, c))
        if not found:
            raise ValueError(f"cannot fit {budget} bytes: {size} bytes and no tie saves any")
        # several ties a round when far over the budget (units disjoint, so their estimates stay independent)
        batch = max(1, (size - budget) // 300)
        used = set()
        done = 0
        for _, a, b, c in sorted(found, key=lambda x: x[0]):
            if a in used or b in used:
                continue
            fill.tie(a, b, c)
            used.update((a, b))
            n += 1
            done += 1
            if done >= batch:
                break
        fill.descend(sweeps=1)
        if log:
            log(f"tie {n}: {size} bytes")


# ---- judging -------------------------------------------------------------------------------------------------------

def _touch(a, b, w, h):
    """True when bitmaps @p a and @p b overlap or touch (8-neighbourhood)."""
    full = (1 << (w * h)) - 1
    left = sum(1 << (y * w) for y in range(h)) * ((1 << (w - 1)) - 1)       # columns 0..w-2
    right = left << 1                                                          # columns 1..w-1
    d = a | (a << 1 & right) | (a >> 1 & left)
    d = d | (d << w & full) | (d >> w)
    return bool(d & b)


def _pair_cat(s, s2):
    L, V, T = s // 588, (s // 28) % 21, s % 28
    L2, V2, T2 = s2 // 588, (s2 // 28) % 21, s2 % 28
    if V != V2:
        return "oug" if V in OUG and V2 in OUG else "vowel"
    if L != L2:
        return "hieuh" if HIEUH in (L, L2) else "initial"
    return "final"


CONFUSE = 2       # two syllables whose glyphs differ in at most this many pixels are confusable


def judge(fill):
    """The report of a fill. ``exact``: syllables equal to the reference; ``mean_dist``: mean Hamming distance to it;
    ``missing3``: syllables lacking 3 or more reference pixels (a stroke likely dropped). ``confuse``: syllables whose
    glyph differs in at most CONFUSE pixels from a syllable one jamo away (where the reference's two differ more), by
    the jamo that differs: ``oug`` (ㅗ ㅛ ㅜ ㅠ ㅡ against each other), ``hieuh`` (initial ㅎ against another initial),
    ``final``, ``initial``, ``vowel``. ``overlap`` / ``touch``: syllables whose final piece shares pixels with, or
    touches, the medial piece. Each figure for all 11,172 and (``_ks``) the 2,350 of KS X 1001, with KS examples."""
    p = fill.p
    w, h = p.st.w, p.st.h
    comp = [fill.comp(s) for s in range(NSYL)]
    ks = [is_ks(0xAC00 + s) for s in range(NSYL)]
    r = {k: 0 for k in ("exact", "exact_ks", "dist", "dist_ks", "missing3", "missing3_ks", "overlap", "overlap_ks",
                        "touch", "touch_ks", "confuse_total", "confuse_total_ks", "extra4", "extra4_ks")}
    r.update(confuse={}, confuse_ks={}, confuse_list={}, overlap_list=[], missing3_list=[])
    for s in range(NSYL):
        g, ref = comp[s], p.tgt[s]
        d = (g ^ ref).bit_count()
        r["dist"] += d
        r["dist_ks"] += d if ks[s] else 0
        if d == 0:
            r["exact"] += 1
            r["exact_ks"] += ks[s]
        if (g & ~ref).bit_count() >= 4:
            r["extra4"] += 1
            r["extra4_ks"] += ks[s]
        if (ref & ~g).bit_count() >= 3:
            r["missing3"] += 1
            if ks[s]:
                r["missing3_ks"] += 1
                r["missing3_list"].append(chr(0xAC00 + s))
        L, V, T = s // 588, (s // 28) % 21, s % 28
        others = ([L2 * 588 + V * 28 + T for L2 in range(19) if L2 != L]
                  + [L * 588 + V2 * 28 + T for V2 in range(21) if V2 != V]
                  + [L * 588 + V * 28 + T2 for T2 in range(28) if T2 != T])
        cats = set()
        worst = None
        for s2 in others:
            e = (g ^ comp[s2]).bit_count()
            if e <= CONFUSE and e < (ref ^ p.tgt[s2]).bit_count():
                c = _pair_cat(s, s2)
                cats.add(c)
                if worst is None or e < worst[0]:
                    worst = (e, s2, c)
        if cats:
            r["confuse_total"] += 1
            r["confuse_total_ks"] += ks[s]
            for c in cats:
                r["confuse"][c] = r["confuse"].get(c, 0) + 1
                if ks[s]:
                    r["confuse_ks"][c] = r["confuse_ks"].get(c, 0) + 1
            if ks[s]:
                r["confuse_list"].setdefault(worst[2], []).append(chr(0xAC00 + s) + "~" + chr(0xAC00 + worst[1]))
        if T:
            ui, um, uf = fill.syl_units[s]
            fb, mb = fill.bmp[uf], fill.bmp[um]
            if fb & mb:
                r["overlap"] += 1
                if ks[s]:
                    r["overlap_ks"] += 1
                    r["overlap_list"].append(chr(0xAC00 + s))
            if _touch(fb, mb, w, h):
                r["touch"] += 1
                r["touch_ks"] += ks[s]
    # medial distinctness (hard gate): pairs of one group, same initial and final
    names = MED
    pairs = {}
    tick_merged = tick_merged_ks = viol = viol_ks = tick_touch = tick_touch_ks = 0
    tick_list = []
    for s in range(NSYL):
        L, V, T = s // 588, (s // 28) % 21, s % 28
        bad = False
        for s2, need in p.partners[s]:
            if s2 < s:
                continue
            d = (comp[s] ^ comp[s2]).bit_count()
            V2 = (s2 // 28) % 21
            k = names[V] + names[V2]
            e = pairs.setdefault(k, {"contexts": 0, "violations": 0, "violations_ks": 0, "min_dist": 99, "worst": []})
            e["contexts"] += 1
            e["min_dist"] = min(e["min_dist"], d)
            if d < need:
                e["violations"] += 1
                e["violations_ks"] += ks[s] or ks[s2]
                if len(e["worst"]) < 12:
                    e["worst"].append(chr(0xAC00 + s) + chr(0xAC00 + s2) + ":%d" % d)
                bad = True
        if V in TICK_ABOVE or V in TICK_BELOW:
            us = fill.syl_units[s]
            o = 0
            for x in (us[0],) + tuple(us[2:]):
                o |= fill.bmp[x]
            t = p.tick(fill.bmp[us[1]], V)
            if not t or not (t & ~o):
                tick_merged += 1
                tick_merged_ks += ks[s]
                if ks[s] and len(tick_list) < 60:
                    tick_list.append(chr(0xAC00 + s))
                bad = True
            elif not (t & ~p.dilate4(o)):
                tick_touch += 1
                tick_touch_ks += ks[s]
        viol += bad
        viol_ks += bad and ks[s]
    r["medial_pairs"] = pairs
    r["medial_violations"], r["medial_violations_ks"] = viol, viol_ks
    r["tick_merged"], r["tick_merged_ks"], r["tick_merged_list"] = tick_merged, tick_merged_ks, tick_list
    r["tick_touch"], r["tick_touch_ks"] = tick_touch, tick_touch_ks
    # stroke widths of the stored pieces
    wv, stems = [], {}
    for (k, _, j), u in sorted(fill.slot_unit.items()):
        b = fill.bmp[u]
        ch = {"i": INI, "m": MED, "f": FIN}[k][j - (1 if k == "f" else 0)]
        if width_violation(b, w, h):
            wv.append(k + ch)
        for x in stroke_widths(b, w, h, False):
            stems.setdefault(k + ch, {}).setdefault(str(x), 0)
            stems[k + ch][str(x)] += 1
    r["width_violations"] = sorted(set(wv))
    r["width_violation_count"] = len({fill.slot_unit[sl] for sl in fill.slot_unit
                                      if width_violation(fill.bmp[fill.slot_unit[sl]], w, h)})
    r["stem_widths"] = stems
    # stroke completeness and leaks of the stored pieces, unit by unit
    inc, leak_pairs, leak_units = [], {}, 0
    tg = lambda T: 0 if T == 0 else (2 if T in DOUBLE_TAILS else 1)
    for u, (k, j) in sorted(fill.jamo.items(), key=lambda x: str(x)):
        b = fill.bmp[u]
        ch = {"i": INI, "m": MED, "f": FIN}[k][j - (1 if k == "f" else 0)]
        if not complete_ok((k, j), b, w, h):
            inc.append(k + ch)
        if p.leaks:
            bad = b & ~fill.leak_mask(u)
            if bad:
                leak_units += 1
                s0 = fill.users[u][0]
                key = (k, j, VOWEL_SHAPE[(s0 // 28) % 21], tg(s0 % 28))
                who = p.leaks.get(key, (0, {}))[1]
                for i in _bits(bad):
                    n2 = who.get(i)
                    nb = "?" if n2 is None else n2[0] + {"i": INI, "m": MED, "f": FIN}[n2[0]][n2[1] - (1 if n2[0] == "f" else 0)]
                    pk = k + ch + ">" + nb
                    leak_pairs[pk] = leak_pairs.get(pk, 0) + 1
    r["incomplete_pieces"] = sorted(inc, key=lambda x: (x[1] != "ㄲ", x))
    r["incomplete_count"] = len(inc)
    r["leak_units"] = leak_units
    r["leak_pairs"] = dict(sorted(leak_pairs.items(), key=lambda x: -x[1]))
    nks = max(1, sum(ks))
    r["mean_dist_ks"] = round(r["dist_ks"] / nks, 3)
    r["mean_dist"] = round(r["dist"] / NSYL, 3)
    r["objective"] = round(fill.cost(), 1)
    return r


def face_info(data):
    f = J.parse_svfn(data)
    t = J.unpack(f.jset)
    pieces = sum(1 for cp in f.glyphs if cp >= J.PIECE_BASE)
    return {"bytes": len(data), "glyphs": f.count, "pieces": pieces, "jset_bytes": len(f.jset),
            "lc": t.lc, "tc": t.tc, "ni": t.ni, "nm": t.nm, "nf": t.nf}


def verify(fill, data):
    """Every syllable of the written face composes to the fill's bitmap (read back with jamoset)."""
    f = J.parse_svfn(data)
    if f.jset is None:
        raise ValueError("the written face has no usable JSET")
    t = J.unpack(f.jset)
    p = fill.p
    for s in range(NSYL):
        g = bytearray(p.pitch * p.st.h)
        for n in J.pieces_of(t, 0xAC00 + s):
            if n == J.BLANK:
                raise ValueError(f"U+{0xAC00 + s:04X}: a blank piece")
            g = bytearray(a | b for a, b in zip(g, f.glyphs[J.PIECE_BASE + n]))
        if bytes(g) != p.cell(fill.comp(s)):
            raise ValueError(f"U+{0xAC00 + s:04X} does not compose to the fill's bitmap")
    return True


# ---- sheets (Pillow) -----------------------------------------------------------------------------------------------

def face_bitmaps(data):
    """(w, h, ascent, glyph(cp) -> (bitmap rows as lists of 0/1, advance) or None), syllables composed."""
    f = J.parse_svfn(data)
    t = J.unpack(f.jset) if f.jset else None
    if isinstance(t, J.Jmap):
        raise ValueError("a JMAP or LIST face (JSET version 3) has no set tables; jamofill sheet reads set-table faces")
    w, h, pitch = f.cell_w, f.cell_h, (f.cell_w + 7) // 8

    def rows(cell):
        return [[cell[y * pitch + x // 8] >> (7 - x % 8) & 1 for x in range(w)] for y in range(h)]

    def glyph(cp):
        if t is not None and 0xAC00 <= cp <= 0xD7A3:
            g = bytearray(pitch * h)
            for n in J.pieces_of(t, cp):
                g = bytearray(a | b for a, b in zip(g, f.glyphs[J.PIECE_BASE + n]))
            return rows(g), t.advance or w
        if cp in f.glyphs:
            return rows(f.glyphs[cp]), f.metrics.get(cp, (w,))[0]
        return None
    return w, h, f.ascent, glyph


def strike_bitmaps(st):
    def rows(b):
        return [[b >> (y * st.w + x) & 1 for x in range(st.w)] for y in range(st.h)]

    def glyph(cp):
        if 0xAC00 <= cp <= 0xD7A3:
            return rows(st.syl[cp - 0xAC00]), st.w
        if cp in st.others:
            return rows(st.others[cp][0]), st.others[cp][1]
        return None
    return st.w, st.h, st.ascent, glyph


def render_lines(glyph, h, lines, gap=2, margin=2, scale=1):
    from PIL import Image
    width = 0
    placed = []
    for li, text in enumerate(lines):
        x = margin
        for ch in text:
            g = glyph(ord(ch))
            if g is None:
                x += h // 2
                continue
            placed.append((x, margin + li * (h + gap), g[0]))
            x += g[1]
        width = max(width, x + margin)
    H = margin * 2 + len(lines) * (h + gap)
    img = Image.new("L", (max(1, width), H), 255)
    px = img.load()
    for x0, y0, rows in placed:
        for y, row in enumerate(rows):
            for x, v in enumerate(row):
                if v and 0 <= x0 + x < width:
                    px[x0 + x, y0 + y] = 0
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    return img


KS_PER_ROW = 50


def ks_lines():
    ks = [chr(cp) for cp in range(0xAC00, 0xD7A4) if is_ks(cp)]
    return ["".join(ks[i:i + KS_PER_ROW]) for i in range(0, len(ks), KS_PER_ROW)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fill", "sweep"):
        s = sub.add_parser(name)
        s.add_argument("--strike", required=True, help="reference survey strike (.npz)")
        s.add_argument("--pieces", nargs="*", default=[], help="jamo libraries (pieces-NAME.json exports) to add")
        s.add_argument("--no-decompose", action="store_true",
                       help="do not add the strike's own decomposition (decompose_strike) to the library")
        s.add_argument("--pixel", action="store_true",
                       help="also let each piece take its pixel-by-pixel best bitmap (Fill.pixel_best), added to the pool")
        s.add_argument("--raw-variants", action="store_true",
                       help="add the decomposition's own variants beside its prototypes (consensus_library)")
        s.add_argument("--no-stroke-filter", action="store_true", help="keep variants stroke_filter would drop")
        s.add_argument("--per-jamo", type=int, default=40, help="variants kept per jamo and library, most used first")
        s.add_argument("--skeleton", required=True, help="FACE.SVF, FACE.SVF:tied, 111, 224, 621, 844 or fine")
        s.add_argument("--budget", type=int, default=0, help="largest file in bytes (0: no limit)")
        if name == "fill":
            s.add_argument("-o", "--out", required=True)
            s.add_argument("--report", help="write the judge report (JSON) here")
        else:
            s.add_argument("--points", nargs="+", required=True, metavar="NI,NM,NF")
            s.add_argument("--prefix", default="SWP")
            s.add_argument("-o", "--outdir", required=True)
    s = sub.add_parser("sheet")
    s.add_argument("face")
    s.add_argument("--strike", help="reference strike: also write a side-by-side sheet")
    s.add_argument("--text", help="UTF-8 file of sample lines (default: a built-in sample)")
    s.add_argument("-o", "--prefix", required=True)
    args = ap.parse_args(argv)
    log = lambda m: print(m, file=sys.stderr, flush=True)

    if args.cmd == "sheet":
        data = open(args.face, "rb").read()
        try:
            w, h, _, glyph = face_bitmaps(data)
        except ValueError as e:
            print(f"jamofill: {args.face}: {e}", file=sys.stderr)
            return 1
        text = open(args.text, encoding="utf-8").read().splitlines() if args.text else SAMPLE
        for sc in (1, 4):
            render_lines(glyph, h, ks_lines(), scale=sc).save(f"{args.prefix}-ks-{sc}x.png")
            render_lines(glyph, h, text, scale=sc).save(f"{args.prefix}-text-{sc}x.png")
        if args.strike:
            _, _, _, ref = strike_bitmaps(read_strike(args.strike))
            a = render_lines(glyph, h, [COMMON20], scale=4)
            b = render_lines(ref, h, [COMMON20], scale=4)
            from PIL import Image
            img = Image.new("L", (max(a.width, b.width), a.height + b.height), 255)
            img.paste(a, (0, 0))
            img.paste(b, (0, a.height))
            img.save(f"{args.prefix}-vs-ref-4x.png")
        return 0

    st = read_strike(args.strike)
    libs = []
    if not args.no_decompose:
        dl, down = decompose_strike(st)
        libs = [(dl, down), (consensus_library(down), down)] if args.raw_variants else [(dl, down)]
    libs += [read_library(p) for p in args.pieces]
    lib, own = merge_libraries(libs, args.per_jamo)
    if not args.no_stroke_filter:
        lib = stroke_filter(lib, st)
    lib = shape_filter(lib, st)
    prob = Problem(st, lib, own)
    t, tie = skeleton(args.skeleton)
    fill = Fill(prob, t, tie, pixel=args.pixel)
    fill.descend()
    log(f"filled: objective {fill.cost():.1f}, {len(fill.pieces()[0])} distinct pieces")

    def finish(fl, path, report_path):
        if args.budget:
            n = fit_budget(fl, args.budget, log)
            fl.descend(sweeps=3)
            data = build_face(fl)
            if len(data) > args.budget:         # the estimate came out low: aim lower by the difference
                n += fit_budget(fl, 2 * args.budget - len(data), log)
            log(f"budget: {n} ties")
        data = build_face(fl)
        verify(fl, data)
        open(path, "wb").write(data)
        rep = {"face": os.path.basename(path), "skeleton": args.skeleton, **face_info(data), **judge(fl)}
        if report_path:
            json.dump(rep, open(report_path, "w"), ensure_ascii=False, indent=1)
        log(f"{path}: {rep['bytes']} bytes, {rep['pieces']} pieces, sets {rep['ni']}/{rep['nm']}/{rep['nf']}, "
            f"classes {rep['lc']}x{rep['tc']}, exact KS {rep['exact_ks']}, mean dist KS {rep['mean_dist_ks']}, "
            f"confusable KS {rep['confuse_total_ks']} {rep['confuse_ks']}, missing3 KS {rep['missing3_ks']}, extra4 KS {rep['extra4_ks']}, medial violations KS "
            f"{rep['medial_violations_ks']} (tick missing/covered {rep['tick_merged_ks']}, touching {rep['tick_touch_ks']}), width violations {rep['width_violation_count']}, incomplete {rep['incomplete_count']}, "
            f"leaking pieces {rep['leak_units']}")
        return rep

    if args.cmd == "fill":
        finish(fill, args.out, args.report)
        return 0

    import copy
    want = [tuple(int(v) for v in p.split(",")) for p in args.points]
    os.makedirs(args.outdir, exist_ok=True)
    curve = []
    done = set()
    while True:
        t_c, _ = fill.compact()
        state = (t_c.ni, t_c.nm, t_c.nf)
        curve.append({"sets": state, "objective": round(fill.cost(), 1), "pieces": len(fill.pieces()[0])})
        log(f"sweep: sets {state}, objective {curve[-1]['objective']}")
        for wnt in want:
            if wnt not in done and all(a <= b for a, b in zip(state, wnt)):
                done.add(wnt)
                name = f"{args.prefix}{''.join('%02d' % v for v in state)}"
                fl = copy.deepcopy(fill)
                rep = finish(fl, os.path.join(args.outdir, name + ".SVF"), os.path.join(args.outdir, name + ".json"))
                rep["requested"] = list(wnt)
        if state == (1, 1, 1) or len(done) == len(want):
            break
        ds = fill.set_merge_deltas()
        if not ds:
            break
        d, k, a, b = min(ds)
        fill.merge_sets(k, a, b)
        fill.descend(sweeps=3)
    json.dump(curve, open(os.path.join(args.outdir, args.prefix + "-curve.json"), "w"), indent=1)
    return 0


COMMON20 = "한국어의가다를이는하고에서있사람것수우리"
SAMPLE = [
    "다람쥐 헌 쳇바퀴에 타고파.",
    "키스의 고유조건은 입술끼리 만나야 하고",
    "특별한 기술은 필요치 않다. 0123456789",
    "훈민정음 뒤뜰 꽃밭 흙 읊다 앉다 닭 값 삶",
    "구 그 고 누 느 노 두 드 도 후 흐 호",
    "굴 글 골 눈 는 논 둘 들 돌 훈 흔 혼",
    "하 허 호 후 흐 히 해 화 훼 홍 형 흘",
    "The quick brown fox jumps over the lazy dog!",
]


if __name__ == "__main__":
    sys.exit(main())
