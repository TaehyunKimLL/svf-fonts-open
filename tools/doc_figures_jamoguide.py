#!/usr/bin/env python3
"""The sample and piece figures of docs/jamo-split-guide.md and docs/jamo-split-guide.ko.md.

  OMP_NUM_THREADS=4 python3 -I tools/doc_figures_jamoguide.py \
      --nanumgothic /path/to/NanumGothic.ttf \
      --galmuri11 /path/to/Galmuri11.ttf \
      [--neodg svf/dos/NEODG16.SVF] [--pylib DIR] [--out DIR] [--check]

Reads only OFL-licensed fonts supplied by the caller (no private font path is written in the script;
--neodg defaults to the repository's svf/dos/NEODG16.SVF). Each face is built in a temporary directory
by the guide's commands, run as subprocesses with `-I`:

  case1-neodg16-sample.png     NEODG16.SVF precomposed vs jamohybrid.py vs jamoset.py (844, adaptive), x2
  case1-neodg16-pieces.png     initial / medial / final pieces of 왜, 앉, 그 (jamohybrid vs 844)
  case2-nanumgothic-sample.png NanumGothic 12 px (default, --min-iou 0.90) and 16 px (default,
                               --min-iou 0.90, --max-bytes 24576), x2
  case2-nanumgothic-pieces.png initial / medial / final pieces of 쀍, 왜, 앉 (NanumGothic 16 px default)
  case3-galmuri11-sample.png   Galmuri11 12 px: precomposed (11,172) vs --from-ttf (11,172) vs
                               --from-svf (KS 2,350 only) on KS and non-KS syllables, x2
  case3-galmuri11-pieces.png   initial / medial / final pieces of 쀍, 왜, 앉 (all 11,172 vs KS 2,350 only)

Sample images are black on white at x2 pixel scale; piece sheets colour initial (vermillion), medial
(blue) and final (bluish green) pieces on a white background with labels drawn from NEODG16.SVF (no
system font is read). Indexed PNG, fixed palette, no metadata.

--check renders in memory and compares with the files in DIR byte for byte (exit 1 on a difference,
a missing file, or any skipped face; skipped faces are listed so a partial run never reports ok).
"""

import argparse
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if HERE not in sys.path:  # python -I drops the script's directory
    sys.path.insert(0, HERE)
import jamoset as J  # noqa: E402
import svfline  # noqa: E402

try:
    from PIL import Image, ImageDraw, features
except ImportError:  # pragma: no cover
    Image = None

DEFAULT_NEODG = os.path.join(ROOT, "svf", "dos", "NEODG16.SVF")
DEFAULT_OUT = os.path.join(ROOT, "docs", "images", "jamo-split-guide")

SCALE_SAMPLE = 2
SCALE_PIECE = 4
PAD = 6
GAP = 3

KS_LINE = "다람쥐 헌 쳇바퀴에 타고파"
NONKS_LINE = "똠 뷁 쀍 햏 펲 꺆 놔둬"
TEST_SYLLABLES = "쀍 왜 앉"

PALETTE = [
    (255, 255, 255),  # 0 background (white)
    (0, 0, 0),        # 1 black ink / overlap
    (213, 94, 0),     # 2 initial (vermillion)
    (0, 114, 178),    # 3 medial (blue)
    (0, 158, 115),    # 4 final (bluish green)
    (214, 214, 214),  # 5 grid
    (246, 246, 246),  # 6 empty cell pixel
    (110, 110, 110),  # 7 grey label / separator
]
BG, INK, C_INI, C_MED, C_FIN, GRID, EMPTY, GREY = range(8)


def new_im(w, h):
    im = Image.new("P", (w, h), BG)
    flat = [c for rgb in PALETTE for c in rgb]
    im.putpalette(flat + [0] * (768 - len(flat)))
    return im, ImageDraw.Draw(im)


def to_png(im):
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


class Cells:
    def __init__(self, w, h):
        self.w, self.h, self.pitch = w, h, (w + 7) // 8

    def bit(self, cell, x, y):
        return (cell[y * self.pitch + (x >> 3)] >> (7 - (x & 7))) & 1 if cell else 0


class Labels:
    """Text drawn with NEODG16.SVF glyphs (16 px), so no system font is read."""

    def __init__(self, neodg_path):
        with open(neodg_path, "rb") as fh:
            self.f = J.parse_svfn(fh.read())
        self.geo = Cells(self.f.cell_w, self.f.cell_h)

    def glyph(self, cp):
        g = self.f.glyphs.get(cp)
        if g is None:
            raise SystemExit(f"doc_figures_jamoguide: no label glyph for U+{cp:04X}")
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
                        d.rectangle([x + xx * scale, y + yy * scale,
                                     x + (xx + 1) * scale - 1, y + (yy + 1) * scale - 1], fill=colour)
            x += adv * scale
        return x - x0

    def centre(self, d, cx, y, s, colour=INK, scale=1):
        self.draw(d, cx - self.width(s, scale) // 2, y, s, colour, scale)


def run_tool(script, argv, pylib=None):
    cmd = [sys.executable, "-I", os.path.join(HERE, script)] + [str(a) for a in argv]
    if pylib and script in ("jamohybrid.py", "jamoset.py"):
        cmd += ["--pylib", pylib]
    env = os.environ.copy()
    env.setdefault("OMP_NUM_THREADS", "4")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f"doc_figures_jamoguide: {script} exit {r.returncode}\n{r.stdout}{r.stderr}")
    return r.stdout


def load_jamo(path):
    with open(path, "rb") as fh:
        f = J.parse_svfn(fh.read())
    return f, J.unpack(f.jset), Cells(f.cell_w, f.cell_h)


def draw_sample_rows(lab, rows):
    """Draw [(label, face_path, [lines...])] black on white at SCALE_SAMPLE."""
    # Pre-load faces and measure widths.
    parsed = []
    max_label_w = 0
    max_text_w = 0
    for label, face_path, lines in rows:
        face = svfline.Face.load(face_path)
        lw = lab.width(label, 1)
        max_label_w = max(max_label_w, lw)
        line_widths = [svfline.measure([face_path], s.encode("utf-8"))[0] for s in lines]
        max_text_w = max(max_text_w, max(line_widths) * SCALE_SAMPLE)
        parsed.append((label, face, list(zip(lines, line_widths))))

    label_col = max_label_w + 16
    w = PAD + label_col + max_text_w + PAD
    block_gap = 10
    row_heights = []
    for _, face, line_pairs in parsed:
        lh = face.cell_h * SCALE_SAMPLE
        bh = len(line_pairs) * lh + (len(line_pairs) - 1) * (GAP * SCALE_SAMPLE)
        row_heights.append(max(bh, 16))
    h = PAD + sum(row_heights) + block_gap * (len(parsed) - 1) + PAD

    im, d = new_im(w, h)
    y = PAD
    for idx, ((label, face, line_pairs), bh) in enumerate(zip(parsed, row_heights)):
        if idx > 0:
            d.line([PAD, y - block_gap // 2, w - PAD, y - block_gap // 2], fill=GRID)
        lab.draw(d, PAD, y + (bh - 16) // 2, label, GREY, 1)
        ly = y
        for s, tw in line_pairs:
            if tw <= 0:
                ly += (face.cell_h + GAP) * SCALE_SAMPLE
                continue
            places = svfline.placements([face], s.encode("utf-8"), 0, face.ascent)
            gray = svfline.draw_gray8(places, tw, face.cell_h)
            x0 = PAD + label_col
            for py in range(face.cell_h):
                for px in range(tw):
                    if gray[py * tw + px] >= 128:
                        d.rectangle([x0 + px * SCALE_SAMPLE, ly + py * SCALE_SAMPLE,
                                     x0 + (px + 1) * SCALE_SAMPLE - 1,
                                     ly + (py + 1) * SCALE_SAMPLE - 1], fill=INK)
            ly += (face.cell_h + GAP) * SCALE_SAMPLE
        y += bh + block_gap
    return to_png(im)


def draw_cell_layers(d, geo, x, y, layers, scale, grid=True):
    for yy in range(geo.h):
        for xx in range(geo.w):
            hits = [c for cell, c in layers if cell and geo.bit(cell, xx, yy)]
            col = EMPTY if not hits else (hits[0] if len(hits) == 1 else INK)
            d.rectangle([x + xx * scale, y + yy * scale,
                         x + (xx + 1) * scale - 1, y + (yy + 1) * scale - 1], fill=col)
    if grid:
        for i in range(geo.w + 1):
            d.line([x + i * scale, y, x + i * scale, y + geo.h * scale], fill=GRID)
        for i in range(geo.h + 1):
            d.line([x, y + i * scale, x + geo.w * scale, y + i * scale], fill=GRID)


def draw_pieces_sheet(lab, sections):
    """Draw [(title, face_path, syllables)] with columns: initial, medial, final, colour overlay, composed."""
    scale = SCALE_PIECE
    # Determine max cell size across sections.
    loaded = []
    max_cw = max_ch = 0
    for title, path, sylls in sections:
        f, t, geo = load_jamo(path)
        max_cw = max(max_cw, geo.w)
        max_ch = max(max_ch, geo.h)
        loaded.append((title, f, t, geo, sylls))

    box_w = max_cw * scale
    box_h = max_ch * scale
    col_gap = 12
    row_gap = 10
    left_w = 40
    cols = ("초성", "중성", "종성", "조합(색)", "조합")
    col_step = box_w + col_gap
    w = PAD + left_w + len(cols) * col_step - col_gap + PAD

    # Height calculation
    hdr_h = 20
    sec_hdr_h = 22
    leg_h = 24
    total_h = PAD + leg_h
    for _, _, _, _, sylls in loaded:
        total_h += sec_hdr_h + hdr_h + len(sylls) * (box_h + 16 + row_gap) + 6
    total_h += PAD

    im, d = new_im(w, total_h)
    y = PAD
    # Legend
    lx = PAD
    for col, text in ((C_INI, "초성"), (C_MED, "중성"), (C_FIN, "종성"), (INK, "겹침/조합")):
        d.rectangle([lx, y + 3, lx + 11, y + 14], fill=col)
        lx += 16 + lab.draw(d, lx + 16, y, text, GREY) + 14
    y += leg_h

    for sidx, (title, f, t, geo, sylls) in enumerate(loaded):
        if sidx > 0:
            d.line([PAD, y - 4, w - PAD, y - 4], fill=GRID)
        lab.draw(d, PAD, y, title, INK)
        y += sec_hdr_h
        for ci, cname in enumerate(cols):
            cx = PAD + left_w + ci * col_step + (geo.w * scale) // 2
            lab.centre(d, cx, y, cname, GREY)
        y += hdr_h

        for ch in sylls:
            cp = ord(ch)
            pnums = list(J.pieces_of(t, cp))
            while len(pnums) < 3:
                pnums.append(J.BLANK)
            pcells = [f.glyphs.get(J.PIECE_BASE + n) if n != J.BLANK else None for n in pnums]
            comp = J.compose(f, t, cp)
            # Label on left: the syllable itself from NEODG16, or its 1x composed glyph if non-KS
            if cp in lab.f.glyphs:
                lab.draw(d, PAD, y + (geo.h * scale - 16) // 2, ch, INK)
            else:
                draw_cell_layers(d, geo, PAD, y + (geo.h * scale - geo.h) // 2, [(comp, INK)], 1, grid=False)
            col_layers = [
                [(pcells[0], C_INI)],
                [(pcells[1], C_MED)],
                [(pcells[2], C_FIN)],
                [(pcells[0], C_INI), (pcells[1], C_MED), (pcells[2], C_FIN)],
                [(comp, INK)],
            ]
            sub_labels = [
                f"#{pnums[0]}" if pnums[0] != J.BLANK and pcells[0] and any(pcells[0]) else "빈 조각",
                f"#{pnums[1]}" if pnums[1] != J.BLANK and pcells[1] and any(pcells[1]) else "빈 조각",
                (f"#{pnums[2]}" if pnums[2] != J.BLANK and pcells[2] and any(pcells[2]) else "-")
                if (cp - 0xAC00) % 28 else "-",
                "",
                "",
            ]
            for ci, (layers, sub) in enumerate(zip(col_layers, sub_labels)):
                bx = PAD + left_w + ci * col_step
                draw_cell_layers(d, geo, bx, y, layers, scale, grid=(ci < 4))
                if sub:
                    lab.centre(d, bx + (geo.w * scale) // 2, y + geo.h * scale + 2, sub, GREY)
            y += box_h + 16 + row_gap
        y += 6
    return to_png(im)


def render(args):
    """Return ({png_name: bytes}, [skipped_png_names])."""
    out, skipped = {}, []
    neodg = args.neodg
    if not os.path.isfile(neodg):
        raise SystemExit(f"doc_figures_jamoguide: missing NEODG16 face: {neodg}")
    lab = Labels(neodg)

    # ---- Case 1: NEODG16.SVF ------------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        hyb = os.path.join(tmp, "neodg16-hybrid.svf")
        f844 = os.path.join(tmp, "neodg16-844.svf")
        fadp = os.path.join(tmp, "neodg16-adapt.svf")
        run_tool("jamohybrid.py", ["--from-svf", neodg, "-o", hyb, "--check"], args.pylib)
        run_tool("jamoset.py", ["--layout", "844", "--from-svf", neodg, "--mask-font", "none",
                                "--check", "-o", f844], args.pylib)
        run_tool("jamoset.py", ["--layout", "adaptive", "--from-svf", neodg, "--mask-font", "none",
                                "--check", "-o", fadp], args.pylib)
        out["case1-neodg16-sample.png"] = draw_sample_rows(lab, [
            ("원본 (NEODG16)", neodg, [KS_LINE, "왜 앉 그 글 ㅡ"]),
            ("jamohybrid", hyb, [KS_LINE, f"{TEST_SYLLABLES} 그 글 ㅡ"]),
            ("jamoset 844", f844, [KS_LINE, f"{TEST_SYLLABLES} 그 글 ㅡ"]),
            ("jamoset adaptive", fadp, [KS_LINE, f"{TEST_SYLLABLES} 그 글 ㅡ"]),
        ])
        out["case1-neodg16-pieces.png"] = draw_pieces_sheet(lab, [
            ("NEODG16: jamohybrid (31,828 B, IoU 0.9914)", hyb, "왜앉그"),
            ("NEODG16: jamoset 844 (34,332 B, IoU 1.000)", f844, "왜앉그"),
        ])
        for k in ("case1-neodg16-sample.png", "case1-neodg16-pieces.png"):
            print(f"{k}: {len(out[k])} bytes")

    # ---- Case 2: NanumGothic.ttf --------------------------------------------
    if not args.nanumgothic or not os.path.isfile(args.nanumgothic):
        reason = "--nanumgothic not given" if not args.nanumgothic else f"{args.nanumgothic} is not there"
        for k in ("case2-nanumgothic-sample.png", "case2-nanumgothic-pieces.png"):
            print(f"{k}: skipped, {reason}")
            skipped.append(k)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            ng12 = os.path.join(tmp, "ng12-default.svf")
            ng12_90 = os.path.join(tmp, "ng12-iou90.svf")
            ng16 = os.path.join(tmp, "ng16-default.svf")
            ng16_90 = os.path.join(tmp, "ng16-iou90.svf")
            ng16_24k = os.path.join(tmp, "ng16-24k.svf")
            run_tool("jamohybrid.py", ["--from-ttf", args.nanumgothic, "--size", "12",
                                       "-o", ng12, "--check"], args.pylib)
            run_tool("jamohybrid.py", ["--from-ttf", args.nanumgothic, "--size", "12",
                                       "--min-iou", "0.90", "-o", ng12_90, "--check"], args.pylib)
            run_tool("jamohybrid.py", ["--from-ttf", args.nanumgothic, "--size", "16",
                                       "-o", ng16, "--check"], args.pylib)
            run_tool("jamohybrid.py", ["--from-ttf", args.nanumgothic, "--size", "16",
                                       "--min-iou", "0.90", "-o", ng16_90, "--check"], args.pylib)
            run_tool("jamohybrid.py", ["--from-ttf", args.nanumgothic, "--size", "16",
                                       "--max-bytes", "24576", "-o", ng16_24k, "--check"], args.pylib)
            out["case2-nanumgothic-sample.png"] = draw_sample_rows(lab, [
                ("12 px 기본", ng12, [KS_LINE, f"{TEST_SYLLABLES} ABC 123"]),
                ("12 px min-iou 0.90", ng12_90, [KS_LINE, f"{TEST_SYLLABLES} ABC 123"]),
                ("16 px 기본", ng16, [KS_LINE, f"{TEST_SYLLABLES} ABC 123"]),
                ("16 px min-iou 0.90", ng16_90, [KS_LINE, f"{TEST_SYLLABLES} ABC 123"]),
                ("16 px max-bytes 24K", ng16_24k, [KS_LINE, f"{TEST_SYLLABLES} ABC 123"]),
            ])
            out["case2-nanumgothic-pieces.png"] = draw_pieces_sheet(lab, [
                ("NanumGothic 16 px 기본 (54,980 B, IoU 0.9799)", ng16, "쀍왜앉"),
            ])
            for k in ("case2-nanumgothic-sample.png", "case2-nanumgothic-pieces.png"):
                print(f"{k}: {len(out[k])} bytes")

    # ---- Case 3: Galmuri11.ttf ----------------------------------------------
    if not args.galmuri11 or not os.path.isfile(args.galmuri11):
        reason = "--galmuri11 not given" if not args.galmuri11 else f"{args.galmuri11} is not there"
        for k in ("case3-galmuri11-sample.png", "case3-galmuri11-pieces.png"):
            print(f"{k}: skipped, {reason}")
            skipped.append(k)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            gal_all_pre = os.path.join(tmp, "gal12-all-pre.svf")
            gal_ks_pre = os.path.join(tmp, "gal12-ks-pre.svf")
            gal_ttf = os.path.join(tmp, "gal12-ttf.svf")
            gal_ks_hyb = os.path.join(tmp, "gal12-ks-hybrid.svf")
            run_tool("mkfont.py", [args.galmuri11, gal_all_pre, "--size", "12", "--bpp", "1",
                                   "--mono-hint", "--unicode", "ascii,hangul"])
            run_tool("mkfont.py", [args.galmuri11, gal_ks_pre, "--size", "12", "--bpp", "1",
                                   "--mono-hint", "--unicode", "ascii,ksx1001-hangul"])
            run_tool("jamohybrid.py", ["--from-ttf", args.galmuri11, "--size", "12",
                                       "-o", gal_ttf, "--check"], args.pylib)
            run_tool("jamohybrid.py", ["--from-svf", gal_ks_pre,
                                       "-o", gal_ks_hyb, "--check"], args.pylib)
            out["case3-galmuri11-sample.png"] = draw_sample_rows(lab, [
                ("원본 11,172자", gal_all_pre, [KS_LINE, NONKS_LINE]),
                ("from-ttf (11,172자)", gal_ttf, [KS_LINE, NONKS_LINE]),
                ("from-svf (KS 2,350자)", gal_ks_hyb, [KS_LINE, NONKS_LINE]),
            ])
            out["case3-galmuri11-pieces.png"] = draw_pieces_sheet(lab, [
                ("Galmuri11 12 px from-ttf (11,172자)", gal_ttf, "쀍왜앉"),
                ("Galmuri11 12 px from-svf (KS 2,350자)", gal_ks_hyb, "쀍왜앉"),
            ])
            for k in ("case3-galmuri11-sample.png", "case3-galmuri11-pieces.png"):
                print(f"{k}: {len(out[k])} bytes")

    return out, skipped


def write_or_check(images, out_dir, check, skipped):
    bad = 0
    if not check:
        os.makedirs(out_dir, exist_ok=True)
    for png, data in images.items():
        dest = os.path.join(out_dir, png)
        if check:
            try:
                with open(dest, "rb") as fh:
                    same = fh.read() == data
            except OSError:
                same = False
            if not same:
                print(f"differs: {dest}")
                bad += 1
        else:
            with open(dest, "wb") as fh:
                fh.write(data)
    if check:
        problems = []
        if bad:
            problems.append(f"{bad} differ")
        if skipped:
            problems.append(f"{len(skipped)} skipped ({', '.join(skipped)})")
        if problems:
            print(f"doc_figures_jamoguide: {'; '.join(problems)} of {len(images) + len(skipped)}")
            return 1
        print(f"doc_figures_jamoguide: ok ({len(images)} images equal)")
        return 0
    if skipped:
        print(f"doc_figures_jamoguide: wrote {len(images)} images, skipped {len(skipped)} ({', '.join(skipped)})")
        return 1
    total = sum(len(v) for v in images.values())
    print(f"doc_figures_jamoguide: wrote {len(images)} images ({total} bytes) into {out_dir}")
    return 0


def main(argv=None):
    if Image is None:
        raise SystemExit("doc_figures_jamoguide: Pillow is needed")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--neodg", default=DEFAULT_NEODG, help="NEODG16.SVF path (default: svf/dos/NEODG16.SVF)")
    ap.add_argument("--nanumgothic", help="NanumGothic.ttf path (OFL)")
    ap.add_argument("--galmuri11", help="Galmuri11.ttf path (OFL)")
    ap.add_argument("--pylib", help="directory holding numpy / freetype-py (also $JAMOSET_PYLIB)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--check", action="store_true", help="regenerate in memory and compare with --out")
    args = ap.parse_args(argv)
    ft = features.version_module("freetype2") if hasattr(features, "version_module") else "?"
    print(f"Pillow {Image.__version__}, FreeType {ft}")
    images, skipped = render(args)
    return write_or_check(images, args.out, args.check, skipped)


if __name__ == "__main__":
    sys.exit(main())
