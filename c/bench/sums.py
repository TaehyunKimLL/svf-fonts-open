#!/usr/bin/env python3
"""sums.py - the reference checksums of the cases of c/bench/bench.c, per target kind, computed with tools/svfline.py
(the Python reference renderer) and tools/jamoset.py, not by the C logic.

Prints one line a kind, in the form run-pico.sh embeds (report.awk's `sums`):
    SUMS_MONO_PAGE="syl_ga:... syl_bwelk:... compose_bwelk:... screen32:... line8:..."
    SUMS_GRAY8="... aa_syl_ga:... aa_syl_bwelk:... aa_line12:... aa_screen10:..."
    SUMS_RGB565="..."
    SUMS_LINE40="line40_mapped:... ... line40_scaled32:..."   (the 40 code point line of bench.c's line section, 1/1 and 3/2)
every one ending in the layout_probe case of a build that reads every layout, and
    SUMS_LAYOUT_DEFAULT="layout_probe:00040404"   (SVF_E_RANGE three times)
    SUMS_LAYOUT_STRICT="layout_probe:00080804"    (-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT: SVF_E_LAYOUT for dos and simd16)
Each sum is FNV-1a 32 over the target buffer after the case (aa_screen10: over the ten bands in turn, the hash carried
across). Set A is the 1 bpp jamo face NEODG16G (128 x 64 target); set B is PAPLG16 + PAPLG18 on a 240 x 24 band
(fg 0xFFE0, bg 0x0010, high byte first). The texts and positions are those of bench.c; keep them in step.
Run as `python3 -I c/bench/sums.py` (the files it reads are found from its own location). The faces can be
overridden: --face (set A, default svf/dos/NEODG16G.SVF), --face16 and --face18 (set B, default svf/dos/PAPLG16.SVF
and PAPLG18.SVF); run-pico.sh passes its FACE, FACE16 and FACE18. Every text must lie inside its target (no clipping,
or the sum would not be of the text): otherwise the script stops with an error.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import jamoset  # noqa: E402
import svfline  # noqa: E402

MONO_FACE = os.path.join(ROOT, "svf", "dos", "NEODG16G.SVF")
PAPLG = [os.path.join(ROOT, "svf", "dos", n) for n in ("PAPLG16.SVF", "PAPLG18.SVF")]
BAND_W, BAND_H = 240, 24
SCREEN_TEXT = ["다람쥐헌쳇바퀴에", "타고파뷁쌓읽가나", "대한민국만세하늘", "바다보다넓은마음"]
AA_LINES = SCREEN_TEXT + ["다람쥐 헌 쳇바퀴에 타", "Score: 120 점", "뷁쌓읽 가나다", "OK 타고파!", "가나다라마바사", "한글 ABC"]
AA_LINE12 = "다람쥐 헌 쳇바퀴에 타"
LINE_TEXT = "Score: 120 점, 다람쥐 헌 쳇바퀴에 타고파! 뷁쌓읽 가나다 OK"  # bench.c line_text (40 code points)
LINE_W, LINE_H, LINE_Y = 640, 24, 19
SCALED_W, SCALED_H, SCALED_Y = 960, 36, 28
BG, FG = 0x0010, 0xFFE0
E_RANGE, E_LAYOUT = 4, 8  # svf_err
# layout_probe's checksum (e_simd16 << 16) | (e_dos << 8) | e_strict: the three headers' open errors
LAYOUT_DEFAULT = f"layout_probe:{E_RANGE << 16 | E_RANGE << 8 | E_RANGE:08x}"
LAYOUT_STRICT = f"layout_probe:{E_LAYOUT << 16 | E_LAYOUT << 8 | E_RANGE:08x}"
KINDS = (("MONO_PAGE", "mono-page"), ("GRAY8", "gray8"), ("RGB565", "rgb565"))


def fnv1a(data, h=2166136261):
    for b in data:
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h


def draw(paths, text, x, y, target, scale=(1, 1)):
    """@p text drawn with the faces at @p paths on @p target at (x, y baseline), at @p scale; stops if any of it would
    fall outside the target."""
    width, ascent, descent = svfline.measure(paths, text, scale=scale)
    if x < 0 or x + width > target.w or y - ascent < 0 or y + descent > target.h:
        sys.exit(f"sums.py: {text!r} at ({x}, {y}) does not fit the {target.w} x {target.h} target "
                 f"(width {width}, ascent {ascent}, descent {descent}): the checksum would be of clipped text")
    svfline.draw_target(svfline.placements(svfline.load_chain(paths), text, x, y, scale=scale), target)
    return target


def set_a(kind, face_path):
    face = svfline.Face.load(face_path)
    if face.tables is None:
        sys.exit(f"sums.py: --face {face_path} is not a jamo face (set A composes syllables from jamo pieces)")
    paths = [face_path]

    def fresh():
        return svfline.Target(kind, 128, 64)

    out = []
    for name, text in (("syl_ga", "가"), ("syl_bwelk", "뷁")):
        out.append((name, fnv1a(draw(paths, text, 0, 14, fresh()).buf)))
    cell = jamoset.compose(face, face.tables, 0xBDC1)
    out.append(("compose_bwelk", fnv1a(cell)))
    t = fresh()
    top = jamoset.parse_svfn(open(face_path, "rb").read()).ascent   # bench.c: the face's ascent + 16 * line
    for line, text in enumerate(SCREEN_TEXT):
        draw(paths, text, 0, top + 16 * line, t)
    out.append(("screen32", fnv1a(t.buf)))
    out.append(("line8", fnv1a(draw(paths, SCREEN_TEXT[0], 0, 14, fresh()).buf)))
    return out


def set_b(kind, paths):
    def band():
        if kind == "rgb565":
            t = svfline.Target(kind, BAND_W, BAND_H, fg565=FG, bg565=BG, big_endian=True)
            t.buf[:] = BG.to_bytes(2, "big") * (BAND_W * BAND_H)
        else:
            t = svfline.Target(kind, BAND_W, BAND_H)
        return t

    out = []
    for name, text in (("aa_syl_ga", "가"), ("aa_syl_bwelk", "뷁"), ("aa_line12", AA_LINE12)):
        out.append((name, fnv1a(draw(paths, text, 8, 19, band()).buf)))
    h = 2166136261
    for text in AA_LINES:
        h = fnv1a(draw(paths, text, 8, 19, band()).buf, h)
    out.append(("aa_screen10", h))
    return out


def set_line(paths):
    """The 40 code point line of bench.c's line section: at 1/1 on gray8 640 x 24 (baseline 19) and at 3/2 on gray8
    960 x 36 (baseline 28); the fourth line, SUMS_LINE40. The cases that stream or cache draw the same pixels."""
    one = fnv1a(draw(paths, LINE_TEXT, 0, LINE_Y, svfline.Target("gray8", LINE_W, LINE_H)).buf)
    scaled = fnv1a(draw(paths, LINE_TEXT, 0, SCALED_Y, svfline.Target("gray8", SCALED_W, SCALED_H), scale=(3, 2)).buf)
    names = ("line40_mapped", "line40_mapped_cache", "line40_stream_cold", "line40_stream_warm", "line40_stream_small",
             "line40_stream_nocache")
    return [(n, one) for n in names] + [("line40_scaled32", scaled)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--face", default=MONO_FACE, help="set A's 1 bpp jamo face")
    ap.add_argument("--face16", default=PAPLG[0], help="set B's first face")
    ap.add_argument("--face18", default=PAPLG[1], help="set B's second face")
    a = ap.parse_args(argv)
    for name, kind in KINDS:
        cases = set_a(kind, a.face) + (set_b(kind, [a.face16, a.face18]) if kind != "mono-page" else [])
        print(f'SUMS_{name}="' + " ".join(f"{c}:{s:08x}" for c, s in cases) + f' {LAYOUT_DEFAULT}"')
    print('SUMS_LINE40="' + " ".join(f"{c}:{s:08x}" for c, s in set_line([a.face16, a.face18])) + f' {LAYOUT_DEFAULT}"')
    print(f'SUMS_LAYOUT_DEFAULT="{LAYOUT_DEFAULT}"')
    print(f'SUMS_LAYOUT_STRICT="{LAYOUT_STRICT}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
