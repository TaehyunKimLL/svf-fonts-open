#!/usr/bin/env python3
"""The pixel figures of docs/jamo-sets.md and docs/jamo-sets.ko.md (card t_6c1f4069).

  python3 -I tools/doc_figures_jamo.py [--out DIR] [--check]

Reads two SIL OFL 1.1 faces of svf/ and nothing else: svf/dos/NEODG16A.SVF (Neo Dunggeunmo, a 16x16 1 bpp jamo set in
the 8x4x4 layout, JSET version 1) and svf/dos/NEODG16.SVF (the same font precomposed, 16x16 1 bpp, ASCII and
KS X 1001 without Hanja). Every label is drawn with NEODG16's own glyphs, so no system font is read. No Apple or ROM
data is read: the figures may be published with the faces' OFL notes (svf/dos/NEODGM.TXT, svf/dos/OFL.TXT).

Writes into DIR (default docs/images/jamo-sets/):
  compose.png       syllables split into their initial / medial / final pieces, colour-coded, and composed
  sets.png          the initial ㄱ in its 8 sets, the medials ㅏ and ㅗ in their 4 sets, the final ㄱ in its 4 sets
  precomposed.png   the precomposed face, the jamo set and their difference, syllable by syllable
  lookup.png        the JSET version 1 lookup of 한: class tables, the three set tables, the piece numbers

--check renders in memory and compares with the files in DIR byte for byte (exit 1 on a difference or a missing file).
Prints the comparison of the two faces over the 2,350 KS X 1001 syllables (exact count, mean IoU). The output is a
function of the two faces: the same bytes on every run (indexed PNG, fixed palette, no metadata).
Needs Pillow.
"""

import argparse
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import jamoset as J  # noqa: E402

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = ImageDraw = None

JAMO_FACE = "svf/dos/NEODG16A.SVF"
PRE_FACE = "svf/dos/NEODG16.SVF"
ALLOWED = (JAMO_FACE, PRE_FACE)  # OFL faces only (web/LICENCES.tsv: dos/NEODG*)

LEADS = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
VOWELS = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
TAILS = "-ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"

# Fixed palette (index: colour). Piece colours: a colour-blind safe trio (vermillion, blue, bluish green).
PALETTE = [
    (255, 255, 255),  # 0 background
    (34, 34, 34),     # 1 ink / text
    (213, 94, 0),     # 2 initial
    (0, 114, 178),    # 3 medial
    (0, 158, 115),    # 4 final
    (214, 214, 214),  # 5 grid
    (246, 246, 246),  # 6 empty pixel
    (255, 236, 160),  # 7 highlight fill
    (140, 140, 140),  # 8 grey text / both
    (230, 159, 0),    # 9 only precomposed (orange)
    (86, 180, 233),   # 10 only jamo (sky blue)
    (200, 30, 30),    # 11 highlight frame
]
BG, INK, C_INI, C_MED, C_FIN, GRID, EMPTY, HIL, GREY, ONLY_PRE, ONLY_JAMO, FRAME = range(12)


def load(rel):
    if rel not in ALLOWED:
        raise SystemExit(f"doc_figures_jamo: refusing {rel}: only the OFL faces {ALLOWED} are read")
    with open(os.path.join(ROOT, rel), "rb") as fh:
        return J.parse_svfn(fh.read())


class Faces:
    def __init__(self):
        self.jamo = load(JAMO_FACE)
        self.pre = load(PRE_FACE)
        self.t = J.unpack(self.jamo.jset)
        self.w, self.h = self.jamo.cell_w, self.jamo.cell_h
        self.pitch = (self.w + 7) // 8

    def piece(self, n):
        return self.jamo.glyphs.get(J.PIECE_BASE + n) if n != J.BLANK else None

    def composed(self, cp):
        out = bytearray(self.pitch * self.h)
        for n in J.pieces_of(self.t, cp) or []:
            g = self.piece(n)
            if g:
                for i, b in enumerate(g):
                    out[i] |= b
        return bytes(out)

    def bit(self, cell, x, y):
        return (cell[y * self.pitch + (x >> 3)] >> (7 - (x & 7))) & 1 if cell else 0

    def label_cell(self, cp):
        """A glyph for the label renderer: the precomposed face, else a syllable composed from the jamo set."""
        if cp in self.pre.glyphs:
            adv = self.pre.metrics.get(cp, (self.pre.cell_w,))[0] if self.pre.metrics_ok else self.pre.cell_w
            return self.pre.glyphs[cp], adv
        if 0xAC00 <= cp <= 0xD7A3:
            return self.composed(cp), self.w
        raise SystemExit(f"doc_figures_jamo: no glyph for U+{cp:04X} in the label faces")


# ---- drawing ------------------------------------------------------------------------------------------------------

def new(w, h):
    im = Image.new("P", (w, h), BG)
    flat = [c for rgb in PALETTE for c in rgb]
    im.putpalette(flat + [0] * (768 - len(flat)))
    return im, ImageDraw.Draw(im)


def text(fc, d, x, y, s, colour=INK, scale=1):
    """Draws @p s with NEODG16 glyphs (16 rows a line) at (x, y) top-left; returns the width."""
    x0 = x
    for ch in s:
        if ch == " ":
            x += 8 * scale
            continue
        cell, adv = fc.label_cell(ord(ch))
        pitch = (fc.pre.cell_w + 7) // 8
        for yy in range(fc.pre.cell_h):
            for xx in range(fc.pre.cell_w):
                if (cell[yy * pitch + (xx >> 3)] >> (7 - (xx & 7))) & 1:
                    d.rectangle([x + xx * scale, y + yy * scale, x + (xx + 1) * scale - 1, y + (yy + 1) * scale - 1],
                                fill=colour)
        x += adv * scale
    return x - x0


def text_width(fc, s, scale=1):
    w = 0
    for ch in s:
        w += 8 * scale if ch == " " else fc.label_cell(ord(ch))[1] * scale
    return w


def text_c(fc, d, cx, y, s, colour=INK, scale=1):
    text(fc, d, cx - text_width(fc, s, scale) // 2, y, s, colour, scale)


def bitmap(fc, d, x, y, layers, scale, grid=True):
    """Draws a cell at (x, y), @p scale px a pixel. @p layers: [(cell bytes, colour)]; a pixel in two or more layers
    is drawn INK. Grid lines between pixels when @p grid."""
    for yy in range(fc.h):
        for xx in range(fc.w):
            hits = [c for cell, c in layers if fc.bit(cell, xx, yy)]
            col = EMPTY if not hits else (hits[0] if len(hits) == 1 else INK)
            d.rectangle([x + xx * scale, y + yy * scale, x + (xx + 1) * scale - 1, y + (yy + 1) * scale - 1], fill=col)
    if grid:
        for i in range(fc.w + 1):
            d.line([x + i * scale, y, x + i * scale, y + fc.h * scale], fill=GRID)
        for i in range(fc.h + 1):
            d.line([x, y + i * scale, x + fc.w * scale, y + i * scale], fill=GRID)


def to_png(im):
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def sets_of(fc, cp):
    t = fc.t
    L, V, T = J.decompose(cp)
    cell = (t.lead_class[L] * 21 + V) * t.tc + t.tail_class[T]
    return L, V, T, cell, t.init_set[cell], t.med_set[cell], (t.fin_set[cell] if T else None)


# ---- (a) compose.png -----------------------------------------------------------------------------------------------

def fig_compose(fc):
    sylls = "가각고곡한흙"
    sc, gap, left, top = 7, 18, 92, 40
    cw = fc.w * sc
    cols = ["초성 piece", "중성 piece", "종성 piece", "조합 (색)", "조합"]
    row_h = fc.h * sc + 40
    W = left + len(cols) * (cw + gap)
    H = top + len(sylls) * row_h + 4
    im, d = new(W, H)
    for i, c in enumerate(cols):
        text_c(fc, d, left + i * (cw + gap) + cw // 2, 10, c)
    for r, ch in enumerate(sylls):
        y = top + r * row_h
        cp = ord(ch)
        L, V, T, cell, si, sm, sf = sets_of(fc, cp)
        pcs = J.pieces_of(fc.t, cp)
        text(fc, d, 8, y + 20, ch, scale=3)
        text(fc, d, 8, y + 74, f"U+{cp:04X}", GREY)
        layers = [(fc.piece(pcs[0]), C_INI), (fc.piece(pcs[1]), C_MED)]
        if T:
            layers.append((fc.piece(pcs[2]), C_FIN))
        labels = [f"벌 {si}  #{pcs[0]}", f"벌 {sm}  #{pcs[1]}", f"벌 {sf}  #{pcs[2]}" if T else "(종성 없음)"]
        for i in range(3):
            x = left + i * (cw + gap)
            if i < len(layers):
                bitmap(fc, d, x, y, [layers[i]], sc)
            else:
                bitmap(fc, d, x, y, [], sc)
            text_c(fc, d, x + cw // 2, y + fc.h * sc + 6, labels[i], GREY)
        x = left + 3 * (cw + gap)
        bitmap(fc, d, x, y, layers, sc)
        x = left + 4 * (cw + gap)
        bitmap(fc, d, x, y, [(fc.composed(cp), INK)], sc)
        text_c(fc, d, x + cw // 2, y + fc.h * sc + 6, "OR", GREY)
    return im


# ---- (b) sets.png --------------------------------------------------------------------------------------------------

def fig_sets(fc):
    t = fc.t
    sc, gap, left = 5, 14, 150
    cw = fc.w * sc
    # (title, colour, [(set, piece number, example syllable)])
    rows = [
        ("초성 ㄱ", C_INI, [(s, t.init_piece[s * 19 + 0], ex) for s, ex in enumerate("가고구과궈각곡곽")]),
        ("중성 ㅏ", C_MED, [(s, t.med_piece[s * 21 + 0], ex) for s, ex in enumerate("가나각낙")]),
        ("중성 ㅗ", C_MED, [(s, t.med_piece[s * 21 + 8], ex) for s, ex in enumerate("고노곡녹")]),
        ("종성 ㄱ", C_FIN, [(s, t.fin_piece[s * 27 + 0], ex) for s, ex in enumerate("악억액옥")]),
    ]
    row_h = fc.h * sc + 64
    top = 12
    W = left + 8 * (cw + gap)
    H = top + len(rows) * row_h
    im, d = new(W, H)
    for r, (title, col, items) in enumerate(rows):
        y = top + r * row_h
        text(fc, d, 8, y + 24, title, scale=2)
        for i, (s, n, ex) in enumerate(items):
            # the example must really use this set: checked, not assumed
            L, V, T, cell, si, sm, sf = sets_of(fc, ord(ex))
            got = {C_INI: si, C_MED: sm, C_FIN: sf}[col]
            if got != s:
                raise SystemExit(f"doc_figures_jamo: {ex} uses set {got}, not {s}")
            x = left + i * (cw + gap)
            bitmap(fc, d, x, y, [(fc.piece(n), col)], sc)
            text(fc, d, x, y + fc.h * sc + 6, f"벌 {s}", GREY)
            ex_cell = fc.composed(ord(ex))
            bitmap(fc, d, x + cw - fc.w * 2, y + fc.h * sc + 6, [(ex_cell, INK)], 2, grid=False)
            text(fc, d, x, y + fc.h * sc + 26, f"#{n}", GREY)
    return im


# ---- (c) precomposed.png -------------------------------------------------------------------------------------------

def compare(fc):
    """(exact, mean IoU) of the jamo set against the precomposed face over the KS X 1001 syllables both draw."""
    exact, ious, n = 0, 0.0, 0
    for s in J.ks_x_1001_syllables():
        cp = 0xAC00 + s
        a, b = fc.pre.glyphs.get(cp), fc.composed(cp)
        if a is None:
            continue
        n += 1
        inter = sum(bin(x & y).count("1") for x, y in zip(a, b))
        union = sum(bin(x | y).count("1") for x, y in zip(a, b))
        exact += a == b
        ious += inter / union if union else 1.0
    return n, exact, ious / n


def fig_precomposed(fc):
    sylls = "가각고곡한흙뷔를의괌"  # KS X 1001 syllables only: NEODG16 has no other
    sc, gap, left, top = 4, 10, 150, 10
    cw = fc.w * sc
    rows = [("완성형", "NEODG16"), ("8x4x4 조합형", "NEODG16A"), ("차이", "")]
    row_h = fc.h * sc + 26
    W = left + len(sylls) * (cw + gap)
    H = top + len(rows) * row_h + 28
    im, d = new(W, H)
    for r, (title, sub) in enumerate(rows):
        y = top + r * row_h
        text(fc, d, 8, y + 8, title)
        if sub:
            text(fc, d, 8, y + 28, sub, GREY)
        for i, ch in enumerate(sylls):
            cp = ord(ch)
            x = left + i * (cw + gap)
            a, b = fc.pre.glyphs[cp], fc.composed(cp)
            if r == 0:
                bitmap(fc, d, x, y, [(a, INK)], sc)
            elif r == 1:
                bitmap(fc, d, x, y, [(b, INK)], sc)
            else:
                both = bytes(p & q for p, q in zip(a, b))
                only_a = bytes(p & ~q & 0xFF for p, q in zip(a, b))
                only_b = bytes(q & ~p & 0xFF for p, q in zip(a, b))
                bitmap(fc, d, x, y, [(both, GREY), (only_a, ONLY_PRE), (only_b, ONLY_JAMO)], sc)
                diff = sum(bin(p ^ q).count("1") for p, q in zip(a, b))
                text_c(fc, d, x + cw // 2, y + fc.h * sc + 4, f"{diff}px", GREY)
    y = top + len(rows) * row_h + 4
    x = 8
    for col, label in ((GREY, "둘 다"), (ONLY_PRE, "완성형에만"), (ONLY_JAMO, "조합형에만")):
        d.rectangle([x, y + 3, x + 11, y + 14], fill=col)
        x += 16 + text(fc, d, x + 16, y, label, GREY) + 18
    return im


# ---- (d) lookup.png ------------------------------------------------------------------------------------------------

def fig_lookup(fc):
    t = fc.t
    ch = "한"
    cp = ord(ch)
    L, V, T, cell, si, sm, sf = sets_of(fc, cp)
    lc, tc = t.lead_class[L], t.tail_class[T]
    pcs = J.pieces_of(t, cp)
    cw, ch_h, left = 24, 20, 150
    W = left + 28 * cw + 10
    im, d = new(W, 900)
    y = 8
    text(fc, d, 8, y, f"{ch} U+{cp:04X} = U+AC00 + ({L}x21 + {V})x28 + {T}:  초성 {LEADS[L]}={L}, 중성 {VOWELS[V]}={V}, "
         f"종성 {TAILS[T]}={T}")
    y += 30

    def strip(label, keys, values, hi, y):
        text(fc, d, 8, y + 12, label)
        for i, (k, v) in enumerate(zip(keys, values)):
            x = left + i * cw
            text_c(fc, d, x + cw // 2, y, k, GREY)
            fill = HIL if i == hi else BG
            d.rectangle([x, y + 18, x + cw - 1, y + 18 + ch_h - 1], fill=fill, outline=GRID)
            text_c(fc, d, x + cw // 2, y + 20, str(v))
        x = left + hi * cw
        d.rectangle([x, y + 18, x + cw - 1, y + 18 + ch_h - 1], outline=FRAME)
        return y + 18 + ch_h + 10

    y = strip("leadClass[19]", list(LEADS), t.lead_class, L, y)
    y = strip("tailClass[28]", list(TAILS), t.tail_class, T, y)
    text(fc, d, 8, y, f"셀 = (leadClass x 21 + 중성) x TC + tailClass = ({lc}x21 + {V})x{t.tc} + {tc} = {cell}")
    y += 28

    def table(label, arr, colour, y):
        text(fc, d, 8, y, label, colour)
        for v in range(21):
            text_c(fc, d, left + v * cw + cw // 2, y, VOWELS[v], GREY)
        y += 18
        for a in range(t.lc):
            for b in range(t.tc):
                text(fc, d, 8, y + 2, f"lc{a} tc{b}", GREY)
                for v in range(21):
                    c = (a * 21 + v) * t.tc + b
                    x = left + v * cw
                    fill = HIL if c == cell else BG
                    d.rectangle([x, y, x + cw - 1, y + ch_h - 1], fill=fill, outline=GRID)
                    text_c(fc, d, x + cw // 2, y + 2, str(arr[c]))
                    if c == cell:
                        hx, hy = x, y
                y += ch_h
        d.rectangle([hx, hy, hx + cw - 1, hy + ch_h - 1], outline=FRAME)
        return y + 10

    y = table("initSet", t.init_set, C_INI, y)
    y = table("medSet", t.med_set, C_MED, y)
    y = table("finSet", t.fin_set, C_FIN, y)
    rows = [
        (f"initPiece[{si}x19+{L}]", C_INI, pcs[0]),
        (f"medPiece[{sm}x21+{V}]", C_MED, pcs[1]),
        (f"finPiece[{sf}x27+{T}-1]", C_FIN, pcs[2]),
    ]
    sc = 4
    x = 8
    y += 4
    for label, col, n in rows:
        text(fc, d, x, y, label, col)
        text(fc, d, x, y + 18, f"= {n}  U+{J.PIECE_BASE + n:05X}", GREY)
        bitmap(fc, d, x, y + 40, [(fc.piece(n), col)], sc)
        x += 200
    text(fc, d, x, y, "OR", INK)
    bitmap(fc, d, x, y + 40, [(fc.piece(n), c) for _, c, n in rows], sc)
    y += 40 + fc.h * sc + 8
    return im.crop((0, 0, W, y))


FIGURES = (("compose.png", fig_compose), ("sets.png", fig_sets), ("precomposed.png", fig_precomposed),
           ("lookup.png", fig_lookup))


def render_all():
    fc = Faces()
    return fc, {name: to_png(fn(fc)) for name, fn in FIGURES}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "images", "jamo-sets"))
    ap.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing")
    a = ap.parse_args(argv)
    if Image is None:
        print("doc_figures_jamo: needs Pillow", file=sys.stderr)
        return 2
    fc, out = render_all()
    n, exact, iou = compare(fc)
    print(f"KS X 1001 syllables {n}: NEODG16A composes {exact} exactly like NEODG16, mean IoU {iou:.4f}")
    bad = 0
    for name, data in out.items():
        path = os.path.join(a.out, name)
        if a.check:
            try:
                with open(path, "rb") as fh:
                    same = fh.read() == data
            except OSError:
                same = False
            print(f"{name}: {'same' if same else 'DIFFERS'} ({len(data)} bytes)")
            bad += not same
        else:
            os.makedirs(a.out, exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(data)
            print(f"{name}: {len(data)} bytes")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
