#!/usr/bin/env python3
"""The pixel figures of docs/jamo-split.md and docs/jamo-split.ko.md.

  python3 -I tools/doc_figures_split.py [--out DIR] [--check]

Reads only OFL-licensed fonts of this repository (ALLOWED below; their licence texts sit beside them):
  ttf/nanumgothic/NanumGothic-Regular.ttf  the outline font: baked to 1 bpp precomposed cells by tools/mkfont.py's
                                           render() (the --clip-cell bake) and fitted to 8x4x4 by jamoset.fit_font,
                                           the function `jamoset.py --from-svf` runs (OFL.txt)
  svf/dos/NEODG16.SVF                      Neo Dunggeunmo 16 px precomposed: the comparison and the labels (OFL.TXT)
  svf/dos/NEODG16A.SVF                     its 8x4x4 jamo set, made by `jamoset.py --from-svf` (OFL.TXT)
  svf/jamo-extra/NDGPR16.SVF               Neo Dunggeunmo Pro 16 px jamo set, for the medial ㅡ (OFLNDGPR.TXT)
No Apple, ROM or proprietary data is read: any other path is refused.

Writes into DIR (default docs/images/jamo-split/):
  split.png     precomposed syllables of the outline font at 16 px, the fitted 8x4x4 pieces, the recomposition, the diff
  exact.png     an exact case (NEODG16 against its jamo set NEODG16A) beside an approximate one (the fit of split.png)
  blank.png     the medial ㅡ of NEODG16A: the bar sits in the initial pieces and the medial piece is blank, so the
                compatibility jamo ㅡ, which the face draws from that piece, is blank; NDGPR16 for comparison
  touch.png     the outline font at 12, 16 and 24 px as mkfont.py bakes it: FreeType's grey rendering cut at 128 (the
                default) and its monochrome renderer (--mono-hint), with the 8-connected ink components of each cell
                (touching strokes merge components)

--check renders in memory and compares with the files in DIR byte for byte (exit 1 on a difference or a missing file).
It also prints the measurements the document quotes (fit IoU and exact counts over the KS X 1001 syllables, the blank
medial pieces, the component counts). The output is a function of the fonts, Pillow's PNG writer and the FreeType that
Pillow links (printed; the files were made with FreeType 2.13.2 and Pillow 10.2.0). Indexed PNG, fixed palette, no
metadata. Needs Pillow.
"""

import argparse
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:  # python -I drops the script's directory
    sys.path.insert(0, HERE)
import jamoset as J  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFont, features
except ImportError:  # pragma: no cover
    Image = None

TTF = "ttf/nanumgothic/NanumGothic-Regular.ttf"
NEO_PRE, NEO_JAMO, NDGPR = "svf/dos/NEODG16.SVF", "svf/dos/NEODG16A.SVF", "svf/jamo-extra/NDGPR16.SVF"
ALLOWED = (TTF, NEO_PRE, NEO_JAMO, NDGPR)

FIT_SIZE = 16           # the size of the outline fit (split.png, exact.png)
SPLIT_SYLLABLES = "한글읽꽃됐"
EXACT_SYLLABLES = "한글읽꽃됐의"
TOUCH_SYLLABLES = "빼뿐꿇됐흙"
TOUCH_SIZES = (12, 16, 24)

PALETTE = [
    (255, 255, 255),  # 0 background
    (34, 34, 34),     # 1 ink / text
    (213, 94, 0),     # 2 initial (vermillion)
    (0, 114, 178),    # 3 medial (blue)
    (0, 158, 115),    # 4 final (bluish green)
    (214, 214, 214),  # 5 grid
    (246, 246, 246),  # 6 empty pixel
    (140, 140, 140),  # 7 grey text / both
    (230, 159, 0),    # 8 only precomposed (orange)
    (86, 180, 233),   # 9 only composed (sky blue)
    (200, 30, 30),    # 10 frame / warning
]
BG, INK, C_INI, C_MED, C_FIN, GRID, EMPTY, GREY, ONLY_PRE, ONLY_JAMO, FRAME = range(11)


def path_of(rel):
    if rel not in ALLOWED:
        raise SystemExit(f"doc_figures_split: refusing {rel}: only the OFL fonts {ALLOWED} are read")
    return os.path.join(ROOT, rel)


def load(rel):
    with open(path_of(rel), "rb") as fh:
        return J.parse_svfn(fh.read())


# ---- cells: 1 bpp row-major bytes ---------------------------------------------------------------------------------

class Cells:
    """A w x h 1 bpp cell geometry with the bit helpers the figures need."""

    def __init__(self, w, h):
        self.w, self.h, self.pitch = w, h, (w + 7) // 8

    def bit(self, cell, x, y):
        return (cell[y * self.pitch + (x >> 3)] >> (7 - (x & 7))) & 1 if cell else 0

    def blank(self):
        return bytes(self.pitch * self.h)


def pop(cell):
    return sum(bin(b).count("1") for b in cell)


def iou(a, b):
    inter = sum(bin(x & y).count("1") for x, y in zip(a, b))
    union = sum(bin(x | y).count("1") for x, y in zip(a, b))
    return inter / union if union else 1.0


def components(geo, cell):
    """Number of 8-connected ink components of @p cell."""
    seen = set()
    n = 0
    for y in range(geo.h):
        for x in range(geo.w):
            if (x, y) in seen or not geo.bit(cell, x, y):
                continue
            n += 1
            stack = [(x, y)]
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < geo.w and 0 <= ny < geo.h and (nx, ny) not in seen and geo.bit(cell, nx, ny):
                            seen.add((nx, ny))
                            stack.append((nx, ny))
    return n


# ---- faces --------------------------------------------------------------------------------------------------------

class JamoFace:
    """A parsed jamo-set SVFN: pieces of a syllable and the composition the engine draws (jamoset.compose)."""

    def __init__(self, f):
        self.f = f
        self.t = J.unpack(f.jset)
        self.geo = Cells(f.cell_w, f.cell_h)

    def piece(self, n):
        return self.f.glyphs.get(J.PIECE_BASE + n) if n != J.BLANK else None

    def pieces(self, cp):
        """[(slot, piece number, cell or None)] of the syllable: slot 0 initial, 1 medial, 2 final."""
        return [(i, n, self.piece(n)) for i, n in enumerate(J.pieces_of(self.t, cp))]

    def composed(self, cp):
        return J.compose(self.f, self.t, cp)


def bake(size, ch, mono=False):
    """@p ch of NanumGothic Regular drawn by mkfont.render into a @p size px square cell with the font's ascent rule
    (mkfont.choose_ascent) and no nudge (--clip-cell), packed to 1 bpp by mkfont.pack_glyph. @p mono: FreeType's
    monochrome hinting (mkfont --mono-hint)."""
    import mkfont
    font = ImageFont.truetype(path_of(TTF), size)
    ascent = mkfont.choose_ascent(font, size)
    old = mkfont.MONO_HINT
    mkfont.MONO_HINT = mono
    try:
        img, _, _ = mkfont.render(font, ch, size, size, ascent, 1, nudge=False)
    finally:
        mkfont.MONO_HINT = old
    return mkfont.pack_glyph(img, size, size, 1), ascent


class OutlineFit:
    """The KS X 1001 syllables of the outline font baked at FIT_SIZE and fitted to 8x4x4 (jamoset.fit_font, free
    pieces, no mask: what `jamoset.py --layout 844 --from-svf BAKED.SVF --mask-font none` does)."""

    def __init__(self):
        size = FIT_SIZE
        self.pre = {}
        targets = {}
        ascent = 0
        for s in J.ks_x_1001_syllables():
            cell, ascent = bake(size, chr(0xAC00 + s))
            if any(cell):
                self.pre[0xAC00 + s] = cell
                targets[s] = J.glyph_gint(cell, size, size)
        out, info = J.fit_font(J.LAYOUTS["844"], targets, size, size, ascent)
        self.info = info
        self.bytes = len(out)
        self.jamo = JamoFace(J.parse_svfn(out))
        self.geo = self.jamo.geo


def compare(pre, jamo, cps):
    """(n, exact, mean IoU) of @p jamo's composition against the precomposed cells {cp: cell}."""
    n = exact = 0
    total = 0.0
    for cp in cps:
        a = pre.get(cp)
        if a is None:
            continue
        b = jamo.composed(cp)
        n += 1
        exact += a == b
        total += iou(a, b)
    return n, exact, total / n if n else 0.0


# ---- drawing ------------------------------------------------------------------------------------------------------

def new(w, h):
    im = Image.new("P", (w, h), BG)
    flat = [c for rgb in PALETTE for c in rgb]
    im.putpalette(flat + [0] * (768 - len(flat)))
    return im, ImageDraw.Draw(im)


class Labels:
    """Text drawn with the glyphs of NEODG16 (16 rows a line), so no system font is read."""

    def __init__(self):
        self.f = load(NEO_PRE)
        self.geo = Cells(self.f.cell_w, self.f.cell_h)

    def glyph(self, cp):
        g = self.f.glyphs.get(cp)
        if g is None:
            raise SystemExit(f"doc_figures_split: no label glyph for U+{cp:04X}")
        adv = self.f.metrics.get(cp, (self.f.cell_w,))[0] if self.f.metrics_ok else self.f.cell_w
        return g, adv

    def width(self, s, scale=1):
        return sum(8 * scale if ch == " " else self.glyph(ord(ch))[1] * scale for ch in s)

    def draw(self, d, x, y, s, colour=INK, scale=1):
        x0 = x
        for ch in s:
            if ch == " ":
                x += 8 * scale
                continue
            g, adv = self.glyph(ord(ch))
            for yy in range(self.geo.h):
                for xx in range(self.geo.w):
                    if self.geo.bit(g, xx, yy):
                        d.rectangle([x + xx * scale, y + yy * scale, x + (xx + 1) * scale - 1,
                                     y + (yy + 1) * scale - 1], fill=colour)
            x += adv * scale
        return x - x0

    def centre(self, d, cx, y, s, colour=INK, scale=1):
        self.draw(d, cx - self.width(s, scale) // 2, y, s, colour, scale)


def bitmap(d, geo, x, y, layers, scale, grid=True):
    """A cell at (x, y), @p scale px a pixel. @p layers: [(cell bytes, colour)]; a pixel in two or more layers is
    drawn INK."""
    for yy in range(geo.h):
        for xx in range(geo.w):
            hits = [c for cell, c in layers if geo.bit(cell, xx, yy)]
            col = EMPTY if not hits else (hits[0] if len(hits) == 1 else INK)
            d.rectangle([x + xx * scale, y + yy * scale, x + (xx + 1) * scale - 1, y + (yy + 1) * scale - 1], fill=col)
    if grid:
        for i in range(geo.w + 1):
            d.line([x + i * scale, y, x + i * scale, y + geo.h * scale], fill=GRID)
        for i in range(geo.h + 1):
            d.line([x, y + i * scale, x + geo.w * scale, y + i * scale], fill=GRID)


def diff_layers(a, b):
    both = bytes(p & q for p, q in zip(a, b))
    only_a = bytes(p & ~q & 0xFF for p, q in zip(a, b))
    only_b = bytes(q & ~p & 0xFF for p, q in zip(a, b))
    return [(both, GREY), (only_a, ONLY_PRE), (only_b, ONLY_JAMO)]


def legend(lab, d, x, y, items):
    for col, text in items:
        d.rectangle([x, y + 3, x + 11, y + 14], fill=col)
        x += 16 + lab.draw(d, x + 16, y, text, GREY) + 18


def to_png(im):
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---- (a) split.png ------------------------------------------------------------------------------------------------

def fig_split(lab, fit):
    geo, jamo = fit.geo, fit.jamo
    sc, gap, left, top = 6, 14, 70, 30
    cw = geo.w * sc
    cols = ["완성형", "초성 조각", "중성 조각", "종성 조각", "조합 (색)", "차이"]
    row_h = geo.h * sc + 30
    W = left + len(cols) * (cw + gap)
    H = top + len(SPLIT_SYLLABLES) * row_h + 26
    im, d = new(W, H)
    for i, c in enumerate(cols):
        lab.centre(d, left + i * (cw + gap) + cw // 2, 6, c)
    for r, ch in enumerate(SPLIT_SYLLABLES):
        cp = ord(ch)
        y = top + r * row_h
        lab.draw(d, 8, y + 30, ch, scale=2)
        pre = fit.pre[cp]
        comp = jamo.composed(cp)
        bitmap(d, geo, left, y, [(pre, INK)], sc)
        lab.centre(d, left + cw // 2, y + geo.h * sc + 4, f"{pop(pre)} px", GREY)
        layers = []
        for slot, n, cell in jamo.pieces(cp):
            colour = (C_INI, C_MED, C_FIN)[slot]
            x = left + (1 + slot) * (cw + gap)
            bitmap(d, geo, x, y, [(cell, colour)] if cell else [], sc)
            lab.centre(d, x + cw // 2, y + geo.h * sc + 4, f"#{n}", GREY)
            if cell:
                layers.append((cell, colour))
        if len(jamo.pieces(cp)) < 3:
            x = left + 3 * (cw + gap)
            bitmap(d, geo, x, y, [], sc)
            lab.centre(d, x + cw // 2, y + geo.h * sc + 4, "-", GREY)
        x = left + 4 * (cw + gap)
        bitmap(d, geo, x, y, layers, sc)
        lab.centre(d, x + cw // 2, y + geo.h * sc + 4, "OR", GREY)
        x = left + 5 * (cw + gap)
        bitmap(d, geo, x, y, diff_layers(pre, comp), sc)
        lab.centre(d, x + cw // 2, y + geo.h * sc + 4, f"IoU {iou(pre, comp):.3f}", GREY)
    legend(lab, d, 8, H - 22, ((GREY, "둘 다"), (ONLY_PRE, "완성형에만"), (ONLY_JAMO, "조합에만"),
                               (INK, "조각 겹침")))
    return im


# ---- (b) exact.png ------------------------------------------------------------------------------------------------

def fig_exact(lab, fit, neo_pre, neo_jamo):
    sc, gap, top = 4, 8, 52
    panels = [("NEODG16 / NEODG16A (조각으로 그린 글꼴)", neo_pre, neo_jamo),
              (f"NanumGothic {FIT_SIZE} px / 8x4x4 맞춤", fit.pre, fit.jamo)]
    geo = fit.geo
    cw = geo.w * sc
    panel_w = len(EXACT_SYLLABLES) * (cw + gap) + 20
    left = 74
    rows = ("완성형", "조합", "차이")
    row_h = geo.h * sc + 24
    W = left + 2 * panel_w
    H = top + len(rows) * row_h + 30
    im, d = new(W, H)
    for r, name in enumerate(rows):
        lab.draw(d, 8, top + r * row_h + 20, name)
    for p, (title, pre, jamo) in enumerate(panels):
        x0 = left + p * panel_w
        n, exact, mean = compare(pre, jamo, [0xAC00 + s for s in J.ks_x_1001_syllables()])
        lab.draw(d, x0, 6, title)
        lab.draw(d, x0, 26, f"KS {n}: exact {exact}, IoU {mean:.3f}", GREY)
        for i, ch in enumerate(EXACT_SYLLABLES):
            cp = ord(ch)
            x = x0 + i * (cw + gap)
            a, b = pre[cp], jamo.composed(cp)
            bitmap(d, geo, x, top, [(a, INK)], sc)
            bitmap(d, geo, x, top + row_h, [(b, INK)], sc)
            bitmap(d, geo, x, top + 2 * row_h, diff_layers(a, b), sc)
            lab.centre(d, x + cw // 2, top + 2 * row_h + geo.h * sc + 4, f"{iou(a, b):.2f}", GREY)
    legend(lab, d, 8, H - 22, ((GREY, "둘 다"), (ONLY_PRE, "완성형에만"), (ONLY_JAMO, "조합에만")))
    return im


# ---- (c) blank.png ------------------------------------------------------------------------------------------------

BLANK_SYLLABLES = "그글으고"


def fig_blank(lab, neo, pro):
    sc, gap, left, top = 5, 12, 120, 30
    geo = neo.geo
    cw = geo.w * sc
    cols = ["초성 조각", "중성 조각", "종성 조각", "조합"]
    group_w = len(cols) * (cw + gap) + 24
    faces = (("NEODG16A", neo), ("NDGPR16", pro))
    row_h = geo.h * sc + 26
    W = left + 2 * group_w
    H = top + 30 + (len(BLANK_SYLLABLES) + 1) * row_h + 4
    im, d = new(W, H)
    for g, (name, face) in enumerate(faces):
        x0 = left + g * group_w
        lab.draw(d, x0, 4, name)
        for i, c in enumerate(cols):
            lab.centre(d, x0 + i * (cw + gap) + cw // 2, top, c, GREY)
    for r, ch in enumerate(BLANK_SYLLABLES + "ㅡ"):
        cp = ord(ch)
        y = top + 24 + r * row_h
        lab.draw(d, 8, y + 20, ch, scale=2)
        if ch == "ㅡ":
            lab.draw(d, 50, y + 30, "U+3161", GREY)
        for g, (name, face) in enumerate(faces):
            x0 = left + g * group_w
            if ch == "ㅡ":
                n = face.t.compat[cp - 0x3131]
                parts = [(1, n, face.piece(n))]
            else:
                parts = face.pieces(cp)
            layers = []
            for slot, n, cell in parts:
                colour = (C_INI, C_MED, C_FIN)[slot]
                x = x0 + slot * (cw + gap)
                bitmap(d, face.geo, x, y, [(cell, colour)] if cell else [], sc)
                note = f"#{n}" + ("" if cell and any(cell) else " 빈 조각")
                lab.centre(d, x + cw // 2, y + geo.h * sc + 4, note, FRAME if not (cell and any(cell)) else GREY)
                if cell:
                    layers.append((cell, colour))
            if len(parts) < 3:
                x = x0 + 2 * (cw + gap)
                bitmap(d, face.geo, x, y, [], sc)
            x = x0 + 3 * (cw + gap)
            bitmap(d, face.geo, x, y, layers, sc)
    return im


def blank_medials(face):
    """(syllables with medial ㅡ, how many of them use an inkless medial piece, compat ㅡ's piece ink)."""
    total = blank = 0
    for cp in range(0xAC00, 0xD7A4):
        if J.decompose(cp)[1] != 18:
            continue
        total += 1
        n = J.pieces_of(face.t, cp)[1]
        cell = face.piece(n)
        blank += not (cell and any(cell))
    n = face.t.compat[0x3161 - 0x3131]
    cell = face.piece(n)
    return total, blank, pop(cell) if cell else 0


# ---- (d) touch.png ------------------------------------------------------------------------------------------------

def fig_touch(lab):
    sc = 4
    gap, left, top = 10, 150, 30
    rows = [(size, mono) for size in TOUCH_SIZES for mono in (False, True)]
    biggest = max(TOUCH_SIZES)
    cw = biggest * sc
    W = left + len(TOUCH_SYLLABLES) * (cw + gap)
    H = top + sum(max(size * sc, 40) + 26 for size, _ in rows) + 4
    im, d = new(W, H)
    for i, ch in enumerate(TOUCH_SYLLABLES):
        lab.centre(d, left + i * (cw + gap) + cw // 2, 6, ch)
    stats = {}
    y = top
    for size, mono in rows:
        lab.draw(d, 8, y + 10, f"{size} px")
        lab.draw(d, 8, y + 30, "--mono-hint" if mono else "회색조 >= 128", GREY)
        geo = Cells(size, size)
        for i, ch in enumerate(TOUCH_SYLLABLES):
            cell, _ = bake(size, ch, mono)
            n = components(geo, cell)
            stats[(size, mono, ch)] = n
            x = left + i * (cw + gap)
            bitmap(d, geo, x, y, [(cell, INK)], sc)
            lab.draw(d, x, y + size * sc + 4, f"{n} 덩어리", GREY)
        y += max(size * sc, 40) + 26
    return im, stats


def render_all():
    lab = Labels()
    fit = OutlineFit()
    neo_pre_f = load(NEO_PRE)
    neo_pre = {cp: g for cp, g in neo_pre_f.glyphs.items() if 0xAC00 <= cp <= 0xD7A3}
    neo = JamoFace(load(NEO_JAMO))
    pro = JamoFace(load(NDGPR))
    touch, stats = fig_touch(lab)
    out = {
        "split.png": to_png(fig_split(lab, fit)),
        "exact.png": to_png(fig_exact(lab, fit, neo_pre, neo)),
        "blank.png": to_png(fig_blank(lab, neo, pro)),
        "touch.png": to_png(touch),
    }
    ks = [0xAC00 + s for s in J.ks_x_1001_syllables()]
    lines = []
    n, exact, mean = compare(fit.pre, fit.jamo, ks)
    lines.append(f"NanumGothic Regular {FIT_SIZE} px baked, 8x4x4 fit: {fit.bytes} bytes, {fit.info['pieces']} pieces, "
                 f"KS {n}: exact {exact}, mean IoU {mean:.4f}")
    n, exact, mean = compare(neo_pre, neo, ks)
    lines.append(f"NEODG16A against NEODG16: KS {n}: exact {exact}, mean IoU {mean:.4f}")
    for name, face in (("NEODG16A", neo), ("NDGPR16", pro)):
        total, blank, ink = blank_medials(face)
        lines.append(f"{name}: {blank} of {total} syllables with medial ㅡ use an inkless medial piece; "
                     f"compat ㅡ piece ink {ink} px")
    for size in TOUCH_SIZES:
        for mono in (False, True):
            lines.append(f"{size} px {'--mono-hint' if mono else 'grey >= 128'}: components " +
                         " ".join(f"{ch}={stats[(size, mono, ch)]}" for ch in TOUCH_SYLLABLES))
    return out, lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "images", "jamo-split"))
    ap.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing")
    a = ap.parse_args(argv)
    if Image is None:
        print("doc_figures_split: needs Pillow", file=sys.stderr)
        return 2
    print(f"Pillow {Image.__version__}, FreeType {features.version_module('freetype2')}")
    out, lines = render_all()
    for line in lines:
        print(line)
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
