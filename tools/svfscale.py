#!/usr/bin/env python3
"""Draw a face at a smaller pixel size: a 40 or 48 px DOS or printer face, or a 24 px BDF, down to 16 px, 1 or 2 bpp.

  svfscale.py SRC --size 16 [--bpp 1|2] [--threshold 0.5] [--chars ks|face|all|FILE] -o OUT.SVF

SRC is an SVF face (precomposed or a jamo set: every glyph is drawn through svfline.py, so a jamo set's syllables are
composed first) or a BDF (any encoding bdfface.py reads). Each glyph is drawn in its source cell and box-filtered to the
new cell: an output pixel is the exact share of the source area it covers that is inked (cell height H to `--size` h,
the width by the same factor, rounded). 1 bpp keeps a pixel whose share is at least `--threshold` (0.5); 2 bpp stores
the share as four levels, (share x 255 x 3 + 127) // 255, mkfont.py's rule. The ascent, every advance and every
per-glyph dy are scaled and rounded (round(v * h / H)); a glyph is resampled from its own cell, so ink a dy shifts
below the cell is kept, not clipped; the output is a precomposed SVFN v3 face (flag 5, variable width), in `--profile` (default).

--chars: `ks` (the default) = ASCII 0x20-0x7E, the KS X 1001 2,350 syllables and whatever else the source has outside
U+AC00-D7A3 and outside plane 15 (where a jamo set keeps its pieces); `face` = the code points the source lists
(a jamo set lists no syllables); `all` = `face` and all 11,172
syllables; or a file of characters (mkfont.py --chars-from rules: any text).

--compare FACE.SVF prints, after writing a 1 bpp result, its overlap with another 1 bpp face: the mean IoU of the KS
X 1001 syllables both draw, both faces on one baseline, at the best common shift within 2 pixels (how far a resample is from a face drawn at that
size; not a quality score).

This is a resampling, not a redrawing: thin strokes of a large face become grey or vanish at 1 bpp, and a 16 px face
drawn by hand (or fitted to an outline at 16 px) is usually crisper. Fit a jamo set to the result with
`jamoset.py --from-svf` (1 bpp results only).
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:  # python -I drops the script's directory
    sys.path.insert(0, HERE)
import jamoset  # noqa: E402
import svfline  # noqa: E402


class ScaleError(Exception):
    pass


class Source:
    """cell_w, cell_h, ascent, cps, draw(cp) -> (rows of 0/1 over the glyph's own cell, advance, dy) or None. The cell
    is drawn without its dy (the per-glyph shift at draw time); the dy is scaled and kept."""


def svf_source(path):
    with open(path, "rb") as fh:
        f = jamoset.parse_svfn(fh.read())
    if f.bpp != 1:
        raise ScaleError(f"{path}: {f.bpp} bpp; the source must be 1 bpp")
    s = Source()
    s.cell_w, s.cell_h, s.ascent = f.cell_w, f.cell_h, f.ascent
    s.cps = sorted(f.glyphs)
    chain = svfline.load_chain([path])
    w, h = f.cell_w, f.cell_h

    def draw(cp):
        face = chain[0]
        if not face.has(cp):
            return None
        adv, _, _, dy = face.metrics(cp)
        # the baseline at ascent - dy puts the cell's top row at row 0, whatever the glyph's dy
        pl = list(svfline.placements(chain, chr(cp), 0, f.ascent - dy))
        buf = svfline.draw_gray8(pl, w, h, None)
        return [[1 if buf[y * w + x] else 0 for x in range(w)] for y in range(h)], adv, dy
    s.draw = draw
    return s


def bdf_source(path):
    import bdfface
    face, glyphs = bdfface.read_bdf(path)
    s = Source()
    s.cell_w, s.cell_h, s.ascent = face.box_w, face.box_h, face.ascent
    s.cps = sorted(glyphs)

    def draw(cp):
        g = glyphs.get(cp)
        if g is None:
            return None
        bw, bh, bx, by, rows, adv = g
        cell = [[0] * s.cell_w for _ in range(s.cell_h)]
        top = s.ascent - (by + bh)
        for y, r in enumerate(rows):
            for x in range(bw):
                if r >> (bw - 1 - x) & 1:
                    cx, cy = bx + x, top + y
                    if 0 <= cx < s.cell_w and 0 <= cy < s.cell_h:
                        cell[cy][cx] = 1
        return cell, adv, 0
    s.draw = draw
    return s


def shares(rows, W, H, w, h):
    """The inked share (0..1) of every output pixel: the exact overlap of each source pixel with the output pixel's
    footprint (output pixel x covers source x * W / w .. (x + 1) * W / w)."""
    def spans(n_out, n_in):
        out = []
        for i in range(n_out):
            a, b = i * n_in / n_out, (i + 1) * n_in / n_out
            part = []
            j = int(a)
            while j < b and j < n_in:
                ov = min(b, j + 1) - max(a, j)
                if ov > 1e-9:
                    part.append((j, ov))
                j += 1
            out.append(part)
        return out
    xs, ys = spans(w, W), spans(h, H)
    area = (W / w) * (H / h)
    res = []
    for y in range(h):
        line = []
        for x in range(w):
            t = 0.0
            for sy, wy in ys[y]:
                r = rows[sy]
                for sx, wx in xs[x]:
                    if r[sx]:
                        t += wy * wx
            line.append(t / area)
        res.append(line)
    return res


def pack(levels, w, bpp):
    """Rows of levels (0/1 or 0..3) as SVFN cell bytes."""
    out = bytearray()
    for r in levels:
        v, n = 0, 0
        for lv in r:
            v = (v << bpp) | lv
            n += bpp
        pad = (-n) % 8
        out += (v << pad).to_bytes((n + pad) // 8, "big")
    return bytes(out)


def chars_of(spec, src):
    ks = [0xAC00 + s for s in jamoset.ks_x_1001_syllables()]
    # a jamo set's pieces sit in plane 15 (U+F0000..): they are not characters and are not drawn alone
    base = [cp for cp in src.cps if not 0xAC00 <= cp <= 0xD7A3 and cp < 0xF0000]
    if spec == "face":
        return [cp for cp in src.cps if cp < 0xF0000]
    if spec == "ks":
        return sorted(set(base) | set(range(0x20, 0x7F)) | set(ks))
    if spec == "all":
        return sorted(set(base) | set(range(0xAC00, 0xD7A4)))
    with open(spec, encoding="utf-8", errors="replace") as fh:
        return sorted({ord(c) for c in fh.read() if c.isprintable() or c == " "})


def scale(src, size, bpp=1, threshold=0.5, chars="ks"):
    """[(cp, packed, advance, ink_x, ink_w)], cell_w, cell_h, ascent, {cp: dy} of the scaled face. Lengths (ascent,
    advance, dy) scale as round(v * h / H)."""
    H, W = src.cell_h, src.cell_w
    h = size
    w = max(1, round(W * h / H))
    asc = round(src.ascent * h / H)
    out, dys = [], {}
    for cp in chars_of(chars, src):
        got = src.draw(cp)
        if got is None:
            continue
        rows, adv, dy = got
        if dy:
            dys[cp] = round(dy * h / H)
        sh = shares(rows, W, H, w, h)
        if bpp == 1:
            lv = [[1 if v >= threshold - 1e-9 else 0 for v in r] for r in sh]
        else:
            lv = [[(int(round(v * 255)) * 3 + 127) // 255 for v in r] for r in sh]
        cols = [x for x in range(w) if any(r[x] for r in lv)]
        ink_x, ink_w = (cols[0], cols[-1] - cols[0] + 1) if cols else (0, 0)
        a = max(0, min(255, round(adv * h / H)))
        if cp == 0x20 and a == 0:
            a = max(1, w // 2)
        out.append((cp, pack(lv, w, bpp), a, ink_x, ink_w))
    return out, w, h, asc, dys


def overlap(path_a, path_b, reach=2):
    """(mean IoU, dx, dy, exact, syllables) of the KS X 1001 syllables two 1 bpp faces both draw, both on one baseline,
    at the best common shift of face a within @p reach pixels."""
    ca, cb = svfline.load_chain([path_a]), svfline.load_chain([path_b])
    fa, fb = ca[0], cb[0]
    m = reach
    up = max(fa.ascent, fb.ascent)
    down = max(fa.cell_h - fa.ascent, fb.cell_h - fb.ascent)
    w, h = max(fa.cell_w, fb.cell_w) + 2 * m, up + down + 2 * m
    base = m + up
    pairs = []
    for s in jamoset.ks_x_1001_syllables():
        cp = 0xAC00 + s
        if not (fa.has(cp) and fb.has(cp)):
            continue
        ga = svfline.draw_gray8(list(svfline.placements(ca, chr(cp), m, base)), w, h)
        gb = svfline.draw_gray8(list(svfline.placements(cb, chr(cp), m, base)), w, h)
        pairs.append(([(i // w, i % w) for i, v in enumerate(ga) if v], {(i // w, i % w) for i, v in enumerate(gb) if v}))
    if not pairs:
        raise ScaleError("the two faces draw no common KS X 1001 syllable")
    best = None
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            tot = exact = 0
            for a, b in pairs:
                a2 = {(y + dy, x + dx) for y, x in a}
                u = len(a2 | b)
                tot += len(a2 & b) / u if u else 1.0
                exact += a2 == b
            if best is None or tot > best[0]:
                best = (tot, dx, dy, exact)
    return best[0] / len(pairs), best[1], best[2], best[3], len(pairs)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="an SVF face (1 bpp) or a BDF")
    ap.add_argument("--size", type=int, required=True, help="the new cell height in pixels")
    ap.add_argument("--bpp", type=int, choices=(1, 2), default=1)
    ap.add_argument("--threshold", type=float, default=0.5, help="1 bpp: the inked share that keeps a pixel (0.5)")
    ap.add_argument("--chars", default="ks", help="ks (default), face, all, or a file of characters")
    ap.add_argument("--compare", metavar="FACE.SVF", help="after writing, print the overlap of the 1 bpp result with "
                    "another 1 bpp face (mean IoU of the KS syllables both draw, at the best shift within 2 px)")
    jamoset.add_profile_args(ap)
    ap.add_argument("-o", "--output", required=True)
    a = ap.parse_args(argv)
    try:
        src = bdf_source(a.source) if a.source.lower().endswith(".bdf") else svf_source(a.source)
        if a.size < 1:
            raise ScaleError(f"--size {a.size}: the new cell height must be at least 1")
        if a.compare and a.bpp != 1:
            raise ScaleError("--compare needs --bpp 1")
        if a.size >= src.cell_h:
            raise ScaleError(f"--size {a.size} is not below the source's cell height {src.cell_h}")
        glyphs, w, h, asc, dys = scale(src, a.size, a.bpp, a.threshold, a.chars)
        if not glyphs:
            raise ScaleError("no glyph to write")
        data = jamoset.write_svfn(w, h, asc, glyphs, b"", jamoset.FLAG_MARKS_AT_ORIGIN, bpp=a.bpp, dy=dys,
                                  profile=jamoset.profile_arg(ap, a))
        with open(a.output, "wb") as fh:
            fh.write(data)
        syl = sum(1 for g in glyphs if 0xAC00 <= g[0] <= 0xD7A3)
        print(f"{a.output}: {len(data)} bytes, {len(glyphs)} glyphs ({syl} syllables), {src.cell_w}x{src.cell_h} -> "
              f"{w}x{h}, ascent {asc}, {a.bpp} bpp")
        if a.compare:
            iou, dx, dy, exact, n = overlap(a.output, a.compare)
            print(f"overlap with {a.compare}: {n} syllables, mean IoU {iou:.3f} at shift dx={dx} dy={dy}, "
                  f"exact {exact}")
    except (ScaleError, ValueError, OSError) as e:
        print(f"svfscale.py: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
