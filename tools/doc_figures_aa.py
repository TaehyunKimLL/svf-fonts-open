#!/usr/bin/env python3
"""The pixel figures of docs/anti-aliasing.md and docs/anti-aliasing.ko.md.

  python3 -I tools/doc_figures_aa.py [--out DIR] [--check]

Reads only OFL-licensed fonts of this repository (ALLOWED below; their licence texts sit beside them):
  svf/jamo-extra/GOTHA16.SVF, GOTHA16A.SVF   Gothic A1 Regular 16 px jamo sets, 1 and 2 bpp (OFLGOTHA.TXT)
  svf/jamo-extra/SGDAY16A.SVF               Single Day 16 px jamo set, 2 bpp (OFLSGDAY.TXT)
  svf/dos/NSQRR36.SVF                       Nanum Square Round Regular 36 px jamo set, 1 bpp (OFLNSQR.TXT)
  svf/jamo-extra/NSQRR16.SVF, svf/dos/NSQRR16A.SVF   the same family drawn at 16 px, 1 and 2 bpp
  svf/dos/PAPLG16.SVF, PAPLG18.SVF          Paperlogy, 2 bpp, the faces of the colour and grey ports (OFLPAPLG.TXT)
  svf/dos/NEODG16.SVF                       Neo Dunggeunmo 16 px, 1 bpp: the labels and the 1 bpp line (OFL.TXT)
  ttf/nanumgothic/NanumGothic-Regular.ttf   the outline of figures bpp.png and outline.png (OFL.txt)
No Apple or ROM data is read: any other path is refused.

Every pixel of a glyph goes through the project's code: faces are read by tools/svfline.py (Face, the C library's load
rules; jamo syllables composed by jamoset.compose, the per-pixel maximum), lines are laid out by svfline.placements and
converted by svfline.Target (the svf_target rules of c/include/svf.h: blend565, blend888, the mono threshold, the GRAY
levels). The outline figures draw the glyph with tools/mkfont.py's render() (Pillow's FreeType, the 2 bpp quantiser
quantize2) and pack it with jamoset.pack_svfn into an in-memory face read back through svfline.Face, so the cells are
what `mkfont.py --bpp N` stores. The downscale figure uses tools/svfscale.py's shares() and level rule.

Writes into DIR (default docs/images/anti-aliasing/):
  bpp.png        one syllable at 1, 2 and 8 bpp, magnified with a pixel grid and at actual size
  levels.png     the 2 bpp levels 0..3 as coverage, blended on light and dark backgrounds, in RGB565, MONO, GRAY 2 bits
  compose.png    a 2 bpp jamo syllable: its pieces, the maximum (what SVF draws), the bitwise OR (wrong), the difference
  outline.png    outline -> 8-bit coverage -> 4 levels (and the 1 bpp threshold) for one glyph
  downscale.png  a 36 px 1 bpp face box-filtered to 16 px at 1 and 2 bpp, against the faces drawn at 16 px
  targets.png    one line on MONO_ROW, GRAY (2 bits), GRAY8, RGB565 and XRGB8888 targets

--check renders in memory and compares with the files in DIR byte for byte (exit 1 on a difference or a missing file).
The output is a function of the fonts, Pillow's PNG writer and, for bpp.png and outline.png, the FreeType that Pillow
links (printed; the files were made with FreeType 2.13.2 and Pillow 10.2.0). No metadata is written. Needs Pillow.
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
import svfline  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFont, features
except ImportError:  # pragma: no cover
    Image = None

GOTHA1, GOTHA2 = "svf/jamo-extra/GOTHA16.SVF", "svf/jamo-extra/GOTHA16A.SVF"
SGDAY2 = "svf/jamo-extra/SGDAY16A.SVF"
NSQR36, NSQR16, NSQR16A = "svf/dos/NSQRR36.SVF", "svf/jamo-extra/NSQRR16.SVF", "svf/dos/NSQRR16A.SVF"
PAP16, PAP18 = "svf/dos/PAPLG16.SVF", "svf/dos/PAPLG18.SVF"
LABEL = "svf/dos/NEODG16.SVF"
TTF = "ttf/nanumgothic/NanumGothic-Regular.ttf"
ALLOWED = (GOTHA1, GOTHA2, SGDAY2, NSQR36, NSQR16, NSQR16A, PAP16, PAP18, LABEL, TTF)

# colours (RGB)
WHITE, INK, GREY, GRID, EMPTY = (255, 255, 255), (34, 34, 34), (120, 120, 120), (200, 200, 200), (246, 246, 246)
C_INI, C_MED, C_FIN = (213, 94, 0), (0, 114, 178), (0, 158, 115)   # colour-blind safe trio
ONLY_OR, FRAME = (230, 159, 0), (200, 30, 30)
NAVY565, YELLOW565 = 0x0010, 0xFFE0                                 # the bench's colours (c/bench/MEASUREMENTS.md set B)


def path_of(rel):
    if rel not in ALLOWED:
        raise SystemExit(f"doc_figures_aa: refusing {rel}: only the OFL fonts {ALLOWED} are read")
    return os.path.join(ROOT, rel)


def face(rel):
    with open(path_of(rel), "rb") as fh:
        return svfline.Face(fh.read())


def rgb565_to_888(c):
    """An RGB565 pixel shown on a 24-bit screen: each channel scaled to 0..255, rounded half up."""
    r, g, b = c >> 11 & 31, c >> 5 & 63, c & 31
    return ((r * 255 + 15) // 31, (g * 255 + 31) // 63, (b * 255 + 15) // 31)


def int888(c):
    return (c >> 16 & 255, c >> 8 & 255, c & 255)


# ---- labels: NEODG16 glyphs, so no system font is read -----------------------------------------------------------

class Labels:
    def __init__(self):
        self.f = face(LABEL)

    def width(self, s, scale=1):
        return sum(8 * scale if ch == " " else self.f.metrics(ord(ch))[0] * scale for ch in s)

    def draw(self, d, x, y, s, colour=INK, scale=1):
        for ch in s:
            if ch == " ":
                x += 8 * scale
                continue
            cp = ord(ch)
            if not self.f.has(cp):
                raise SystemExit(f"doc_figures_aa: label glyph U+{cp:04X} missing")
            for yy, row in enumerate(self.f.coverage(cp)):
                for xx, v in enumerate(row):
                    if v:
                        d.rectangle([x + xx * scale, y + yy * scale, x + (xx + 1) * scale - 1,
                                     y + (yy + 1) * scale - 1], fill=colour)
            x += self.f.metrics(cp)[0] * scale
        return x

    def centre(self, d, cx, y, s, colour=INK, scale=1):
        self.draw(d, cx - self.width(s, scale) // 2, y, s, colour, scale)


def new(w, h, bg=WHITE):
    im = Image.new("RGB", (w, h), bg)
    return im, ImageDraw.Draw(im)


def grey(v):
    """Coverage 0..255 shown as ink on paper: blend888 of white paper and INK."""
    c = svfline.blend888(0x222222, 0xFFFFFF, v)
    return int888(c)


def cells(d, x, y, rows, sc, colour_of=grey, grid=True, empty=EMPTY):
    """Draws rows of values at (x, y), @p sc px a pixel; colour_of(v) gives the colour of a non-zero value."""
    h, w = len(rows), len(rows[0])
    for yy in range(h):
        for xx in range(w):
            v = rows[yy][xx]
            d.rectangle([x + xx * sc, y + yy * sc, x + (xx + 1) * sc - 1, y + (yy + 1) * sc - 1],
                        fill=colour_of(v) if v else empty)
    if grid:
        for i in range(w + 1):
            d.line([x + i * sc, y, x + i * sc, y + h * sc], fill=GRID)
        for i in range(h + 1):
            d.line([x, y + i * sc, x + w * sc, y + i * sc], fill=GRID)
    return w * sc, h * sc


def to_png(im):
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---- faces baked from the outline, as mkfont.py bakes them ---------------------------------------------------------

def baked(ch, size, bpp, cell=None):
    """(svfline.Face, cp): @p ch of NanumGothic Regular drawn by mkfont.render at @p size px in a @p cell px square cell
    (the font's ascent rule, mkfont.choose_ascent), packed by mkfont.pack_glyph and jamoset.pack_svfn, read back."""
    import mkfont
    cell = cell or size
    font = ImageFont.truetype(path_of(TTF), size)
    ascent = mkfont.choose_ascent(font, cell)
    img, ink_x, ink_w = mkfont.render(font, ch, cell, cell, ascent, bpp)
    data = J.pack_svfn(cell, cell, ascent, bpp, 0, [mkfont.pack_glyph(img, cell, cell, bpp)], [(ord(ch), 0)])
    return svfline.Face(data), ord(ch)


def raw_coverage(ch, size, cell, oversample=1):
    """The 8-bit coverage mkfont.render starts from (FreeType's anti-aliased renderer), before any quantising; with
    @p oversample > 1 the glyph drawn that many times larger (the outline as a fine raster)."""
    import mkfont
    font = ImageFont.truetype(path_of(TTF), size)
    ascent = mkfont.choose_ascent(font, cell)
    if oversample == 1:
        img, _, _ = mkfont.render(font, ch, cell, cell, ascent, 8)
    else:
        big = ImageFont.truetype(path_of(TTF), size * oversample)
        img = Image.new("L", (cell * oversample, cell * oversample), 0)
        # the same pen position as render() at 1x (no nudge: this glyph's ink is inside the cell), scaled
        left, top, right, bottom = font.getbbox(ch, anchor="ls")
        dx = -min(0, left)
        ImageDraw.Draw(img).text((dx * oversample, ascent * oversample), ch, font=big, fill=255, anchor="ls")
    w, h = img.size
    px = img.load()
    return [[px[x, y] for x in range(w)] for y in range(h)]


# ---- (a) bpp.png ---------------------------------------------------------------------------------------------------

def fig_bpp(lab):
    ch = "한"
    sc, gap, left, top = 10, 26, 150, 34
    rows = []
    for bpp in (1, 2, 8):
        f, cp = baked(ch, 16, bpp)
        rows.append((f"{bpp} bpp", f"mkfont {bpp}", f.coverage(cp), f.pitch * f.cell_h))
    g1, g2 = face(GOTHA1), face(GOTHA2)
    shipped = [("1 bpp", "GOTHA16", g1.coverage(ord(ch)), g1.pitch * g1.cell_h),
               ("2 bpp", "GOTHA16A", g2.coverage(ord(ch)), g2.pitch * g2.cell_h)]
    cw = 16 * sc
    W = left + 3 * (cw + gap) + 120
    H = top + 2 * (cw + 64) + 10
    im, d = new(W, H)
    lab.draw(d, 8, 8, "NanumGothic Regular 16 px (mkfont.py), Gothic A1 16 px (svf/jamo-extra)", GREY)
    for r, (title, items) in enumerate((("TTF", rows), ("SVF", shipped))):
        y = top + r * (cw + 64)
        lab.draw(d, 8, y + 10, title, scale=2)
        for i, (name, sub, cov, nbytes) in enumerate(items):
            x = left + i * (cw + gap)
            cells(d, x, y, cov, sc)
            lab.draw(d, x, y + cw + 6, f"{name}  {sub}", INK)
            lab.draw(d, x, y + cw + 26, f"셀 {nbytes} B", GREY)
        # actual size of each at 1:1 and 2:1, right column
        ax = left + 3 * (cw + gap)
        for i, (name, sub, cov, _) in enumerate(items):
            cells(d, ax + i * 36, y + 20, cov, 1, grid=False, empty=WHITE)
            cells(d, ax + i * 36, y + 50, cov, 2, grid=False, empty=WHITE)
        lab.draw(d, ax, y + 96, "1:1, 2:1", GREY)
    return im


# ---- (b) levels.png ------------------------------------------------------------------------------------------------

def fig_levels(lab):
    sw, gap, left, top = 64, 10, 230, 44
    W = left + 4 * (sw + gap) + 10
    rows = [
        ("검정 글자, 흰 바탕", "XRGB8888 000000/FFFFFF",
         lambda k: int888(svfline.blend888(0x000000, 0xFFFFFF, 85 * k))),
        ("흰 글자, 검정 바탕", "XRGB8888 FFFFFF/000000",
         lambda k: int888(svfline.blend888(0xFFFFFF, 0x000000, 85 * k))),
        ("RGB565", "fg FFE0, bg 0010",
         lambda k: rgb565_to_888(svfline.blend565(YELLOW565, NAVY565, 85 * k))),
        ("GRAY 2 bits", "(cov x 3 + 127) / 255",
         lambda k: int888(svfline.blend888(0x000000, 0xFFFFFF, svfline.index_level(85 * k, 3, 128) * 85))),
        ("MONO, 임계값 128", "cov >= 128",
         lambda k: (0, 0, 0) if 85 * k >= 128 else (255, 255, 255)),
    ]
    rh = 52
    H = top + len(rows) * rh + 56
    im, d = new(W, H)
    lab.draw(d, 8, 10, "2 bpp 단계", scale=1)
    for k in range(4):
        x = left + k * (sw + gap)
        lab.centre(d, x + sw // 2, 6, f"단계 {k}")
        lab.centre(d, x + sw // 2, 24, f"cov {85 * k}", GREY)
    for r, (title, sub, colour) in enumerate(rows):
        y = top + r * rh
        lab.draw(d, 8, y + 4, title)
        lab.draw(d, 8, y + 22, sub, GREY)
        for k in range(4):
            x = left + k * (sw + gap)
            c = colour(k)
            d.rectangle([x, y, x + sw - 1, y + rh - 10], fill=c, outline=GRID)
            hexs = "%02X%02X%02X" % c
            tc = (0, 0, 0) if sum(c) > 380 else (255, 255, 255)
            lab.centre(d, x + sw // 2, y + 14, hexs, tc)
    y = top + len(rows) * rh + 6
    lab.draw(d, 8, y, "blend: (bg x (255 - cov) + fg x cov + 127) / 255, 채널마다", GREY)
    lab.draw(d, 8, y + 20, "RGB565 화면 표시: c x 255 / 31 (G: / 63), 반올림", GREY)
    return im


# ---- (c) compose.png -----------------------------------------------------------------------------------------------

def or_compose(f, cp):
    """The wrong composition: the pieces' stored bytes ORed (2-bit fields 01 | 10 give 11)."""
    n = f.pitch * f.cell_h
    out = bytearray(n)
    for p in J.pieces_of(f.tables, cp):
        if p != J.BLANK:
            for i, b in enumerate(f.glyphs[J.PIECE_BASE + p]):
                out[i] |= b
    return bytes(out)


def unpack2(f, cell):
    return [[(cell[y * f.pitch + (x >> 2)] >> (6 - 2 * (x & 3)) & 3) * 85 for x in range(f.cell_w)]
            for y in range(f.cell_h)]


def fig_compose(lab):
    sc, gap, left, top = 8, 14, 120, 34
    cols = ["초성", "중성", "종성", "최댓값 (SVF)", "OR (틀림)", "차이"]
    cases = [(GOTHA2, "흴", "GOTHA16A"), (SGDAY2, "홈", "SGDAY16A")]
    cw = 16 * sc
    rh = cw + 52
    W = left + len(cols) * (cw + gap)
    H = top + len(cases) * rh + 30
    im, d = new(W, H)
    for i, c in enumerate(cols):
        lab.centre(d, left + i * (cw + gap) + cw // 2, 8, c)
    for r, (rel, ch, name) in enumerate(cases):
        f, cp = face(rel), ord(ch)
        y = top + r * rh
        lab.draw(d, 8, y + 16, ch, scale=3)
        lab.draw(d, 8, y + 70, name, GREY)
        pcs = J.pieces_of(f.tables, cp)
        for i, (p, col) in enumerate(zip(pcs, (C_INI, C_MED, C_FIN))):
            x = left + i * (cw + gap)
            if p == J.BLANK:
                cells(d, x, y, [[0] * 16 for _ in range(16)], sc)
                continue
            cov = unpack2(f, f.glyphs[J.PIECE_BASE + p])

            def shade(v, col=col):
                a = v / 255
                return tuple(round(255 - (255 - c) * a) for c in col)
            cells(d, x, y, cov, sc, shade)
            lab.centre(d, x + cw // 2, y + cw + 6, f"#{p}", GREY)
        mx = f.coverage(cp)                       # svfline: jamoset.compose, the per-pixel maximum
        bad = unpack2(f, or_compose(f, cp))
        x = left + 3 * (cw + gap)
        cells(d, x, y, mx, sc)
        x = left + 4 * (cw + gap)
        cells(d, x, y, bad, sc)
        diff = [[1 if a != b else 0 for a, b in zip(ra, rb)] for ra, rb in zip(mx, bad)]
        n = sum(map(sum, diff))
        x = left + 5 * (cw + gap)
        cells(d, x, y, [[(170 if v else 0) for v in row] for row in mx], sc,
              lambda v: (225, 225, 225))
        for yy in range(16):
            for xx in range(16):
                if diff[yy][xx]:
                    d.rectangle([x + xx * sc, y + yy * sc, x + (xx + 1) * sc - 1, y + (yy + 1) * sc - 1], fill=ONLY_OR)
        lab.centre(d, x + cw // 2, y + cw + 6, f"{n} px", GREY)
    lab.draw(d, 8, top + len(cases) * rh + 4, "OR: 단계 1 (01) | 단계 2 (10) = 단계 3 (11): 겹친 회색이 검정이 된다", GREY)
    return im


# ---- (d) outline.png -----------------------------------------------------------------------------------------------

def fig_outline(lab):
    ch, size = "가", 16
    os_ = 8                                       # the outline drawn 8 times larger: one cell pixel = 8 x 8
    sc, gap, left, top = 10, 22, 8, 34
    fine = raw_coverage(ch, size, size, os_)
    cov8 = raw_coverage(ch, size, size)           # what mkfont.render draws before quantising (8 bpp)
    f2, cp = baked(ch, size, 2)
    f1, _ = baked(ch, size, 1)
    lv = f2.coverage(cp)
    mono = f1.coverage(cp)
    cw = size * sc
    W = left + 4 * (cw + gap)
    H = top + cw + 70
    im, d = new(W, H)
    titles = ["윤곽 (x8)", "coverage 8 bpp", "4 단계 (2 bpp)", "임계값 128 (1 bpp)"]
    for i, t in enumerate(titles):
        lab.centre(d, left + i * (cw + gap) + cw // 2, 8, t)
    # 1: the fine raster, each fine pixel sc / os_ ... draw at 10 / 8: use a 1.25 px step via resize
    x = left
    fimg = Image.new("L", (size * os_, size * os_))
    fimg.putdata([v for row in fine for v in row])
    fimg = fimg.resize((cw, cw), Image.NEAREST).point(lambda v: 255 - (255 - 34) * v // 255)
    im.paste(Image.merge("RGB", (fimg, fimg, fimg)), (x, top))
    for i in range(size + 1):
        d.line([x + i * sc, top, x + i * sc, top + cw], fill=(240, 120, 120))
        d.line([x, top + i * sc, x + cw, top + i * sc], fill=(240, 120, 120))
    cells(d, left + 1 * (cw + gap), top, cov8, sc)
    cells(d, left + 2 * (cw + gap), top, lv, sc)
    cells(d, left + 3 * (cw + gap), top, mono, sc)
    hist = [0, 0, 0, 0]
    for row in lv:
        for v in row:
            hist[v // 85] += 1
    lab.draw(d, left + 2 * (cw + gap), top + cw + 6, f"1/2/3: {hist[1]}/{hist[2]}/{hist[3]} px", GREY)
    distinct = len({v for row in cov8 for v in row if v})
    lab.draw(d, left + 1 * (cw + gap), top + cw + 6, f"{distinct} 가지 값", GREY)
    lab.draw(d, left + 3 * (cw + gap), top + cw + 6, f"{sum(1 for row in mono for v in row if v)} px", GREY)
    lab.draw(d, 8, top + cw + 32, "단계 = (cov x 3 + 127) // 255 (mkfont.quantize2), 읽을 때 단계 x 85", GREY)
    return im


# ---- (e) downscale.png ---------------------------------------------------------------------------------------------

def fig_downscale(lab):
    import svfscale
    ch = "봄"
    big, d16, d16a = face(NSQR36), face(NSQR16), face(NSQR16A)
    cp = ord(ch)
    src = [[1 if v else 0 for v in r] for r in big.coverage(cp)]
    W0, H0 = big.cell_w, big.cell_h
    sh = svfscale.shares(src, W0, H0, 16, 16)
    one = [[255 if v >= 0.5 - 1e-9 else 0 for v in r] for r in sh]
    two = [[((int(round(v * 255)) * 3 + 127) // 255) * 85 for v in r] for r in sh]
    # the renderer's draw-time scale 4/9 (36 -> 16), its 8-bit coverage
    scaled = svfline.Scaled(big, 4, 9).coverage(cp)
    q = [[svfline.index_level(v, 3, 128) * 85 for v in r] for r in scaled]
    same = q == two
    panels = [("36 px 1 bpp", "NSQRR36", big.coverage(cp), 4),
              ("16 px 1 bpp", "몫 >= 0.5", one, 9),
              ("16 px 2 bpp", "svfscale", two, 9),
              ("배율 4/9", "그릴 때 GRAY8", scaled, 9),
              ("16 px 1 bpp", "NSQRR16", d16.coverage(cp), 9),
              ("16 px 2 bpp", "NSQRR16A", d16a.coverage(cp), 9)]
    gap, left, top = 18, 8, 30
    W = left + sum(len(p[2][0]) * p[3] + gap for p in panels)
    H = top + 144 + 80
    im, d = new(W, H)
    x = left
    lab.draw(d, left, 6, "축소 (svfscale.py)", INK)
    lab.draw(d, left + 3 * (144 + gap) + 144 + gap + 4, 6, "16 px 로 그린 페이스", INK)
    for title, sub, cov, sc in panels:
        cells(d, x, top, cov, sc, grid=sc > 4)
        lab.draw(d, x, top + 150, title)
        lab.draw(d, x, top + 170, sub, GREY)
        x += len(cov[0]) * sc + gap
    lab.draw(d, left, top + 194,
             "2 bpp 결과 = 그릴 때 배율 4/9 를 4 단계로 양자화한 것: " + ("같다" if same else "다르다"), GREY)
    return im, same


# ---- (f) targets.png -----------------------------------------------------------------------------------------------

LINE = "SVF 2 bpp 안티앨리어싱 글꼴"


def fig_targets(lab):
    chain = [face(PAP16), face(PAP18)]
    width, ascent, descent = svfline.measure([path_of(PAP16), path_of(PAP18)], LINE)
    w, h, base = width + 4, ascent + descent + 2, ascent + 1
    places = svfline.placements(chain, LINE, 2, base)
    mono1 = svfline.placements([face(LABEL)], LINE, 2, base)

    def show_mono(t):
        return [[(0, 0, 0) if t.buf[y * t.stride + (x >> 3)] & (0x80 >> (x & 7)) else (255, 255, 255)
                 for x in range(w)] for y in range(h)]

    rows = []
    t = svfline.draw_target(mono1, svfline.Target("mono-row", w, h))
    rows.append(("MONO_ROW", "1 bpp NEODG16", show_mono(t)))
    t = svfline.draw_target(places, svfline.Target("mono-row", w, h, threshold=128))
    rows.append(("MONO_ROW", "2 bpp, 임계값 128", show_mono(t)))
    t = svfline.draw_target(places, svfline.Target("gray", w, h, gray_bits=2))
    rows.append(("GRAY 2 bits", "SSD1327 같은 회색", [[int888(svfline.blend888(0, 0xFFFFFF, (
        t.buf[y * t.stride + (x >> 2)] >> (6 - 2 * (x & 3)) & 3) * 85)) for x in range(w)] for y in range(h)]))
    t = svfline.draw_target(places, svfline.Target("gray8", w, h))
    rows.append(("GRAY8", "coverage 0..255", [[int888(svfline.blend888(0, 0xFFFFFF, t.buf[y * w + x]))
                                               for x in range(w)] for y in range(h)]))
    buf = bytearray(NAVY565.to_bytes(2, "little") * (w * h))
    t = svfline.draw_target(places, svfline.Target("rgb565", w, h, buf=buf, fg565=YELLOW565, bg565=NAVY565))
    rows.append(("RGB565", "fg FFE0, bg 0010", [[rgb565_to_888(int.from_bytes(t.buf[y * t.stride + 2 * x:
                                                                                    y * t.stride + 2 * x + 2], "little"))
                                                  for x in range(w)] for y in range(h)]))
    buf = bytearray(bytes((0xF0, 0xF8, 0xFF, 0)) * (w * h))
    t = svfline.draw_target(places, svfline.Target("xrgb8888", w, h, buf=buf, fg888=0x202060, bg888=0xFFF8F0))
    rows.append(("XRGB8888", "fg 202060, bg FFF8F0", [[(t.buf[(y * w + x) * 4 + 2], t.buf[(y * w + x) * 4 + 1],
                                                       t.buf[(y * w + x) * 4]) for x in range(w)] for y in range(h)]))
    sc, left, top = 3, 190, 8
    rh = h * sc + 14
    W = left + w * sc + 16 + w + 8
    H = top + len(rows) * rh
    im, d = new(W, H)
    for r, (title, sub, px) in enumerate(rows):
        y = top + r * rh
        lab.draw(d, 8, y + 12, title)
        lab.draw(d, 8, y + 32, sub, GREY)
        for yy in range(h):
            for xx in range(w):
                c = px[yy][xx]
                d.rectangle([left + xx * sc, y + yy * sc, left + (xx + 1) * sc - 1, y + (yy + 1) * sc - 1], fill=c)
                im.putpixel((left + w * sc + 16 + xx, y + yy), c)
    return im


def render_all():
    lab = Labels()
    down, same = fig_downscale(lab)
    figs = {"bpp.png": fig_bpp(lab), "levels.png": fig_levels(lab), "compose.png": fig_compose(lab),
            "outline.png": fig_outline(lab), "downscale.png": down, "targets.png": fig_targets(lab)}
    return {k: to_png(v) for k, v in figs.items()}, same


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "images", "anti-aliasing"))
    ap.add_argument("--check", action="store_true", help="compare with the files in --out instead of writing")
    a = ap.parse_args(argv)
    if Image is None:
        print("doc_figures_aa: needs Pillow", file=sys.stderr)
        return 2
    print(f"Pillow {Image.__version__ if hasattr(Image, '__version__') else '?'}, "
          f"FreeType {features.version('freetype2')}")
    out, same = render_all()
    print(f"downscale: the 2 bpp resample of NSQRR36 equals the draw-time 4/9 scale quantised to 4 levels: {same}")
    bad = 0
    total = 0
    for name, data in out.items():
        total += len(data)
        path = os.path.join(a.out, name)
        if a.check:
            try:
                with open(path, "rb") as fh:
                    ok = fh.read() == data
            except OSError:
                ok = False
            print(f"{name}: {'same' if ok else 'DIFFERS'} ({len(data)} bytes)")
            bad += not ok
        else:
            os.makedirs(a.out, exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(data)
            print(f"{name}: {len(data)} bytes")
    print(f"total {total} bytes")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
