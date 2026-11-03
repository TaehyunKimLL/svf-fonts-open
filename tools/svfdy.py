#!/usr/bin/env python3
"""svfdy.py - set the per-glyph vertical delta (dy) of an SVFN font (graphics/hires_text/README.md, "Per-glyph dy").

A glyph with dy is drawn dy rows below its cell position (negative: above); its ink may then leave the cell, e.g. a
descender below it. The dy is metrics byte 3 of the glyph, the font-wide range header bytes 17 (dy_min <= 0) and 18
(dy_max >= 0); an engine that predates them ignores both and draws every glyph at its cell position. Only a font with a
metrics table (flags bit 0) can carry it.

The face is read with jamoset.parse_svfn (SVFN v3) and written again as v3 with jamoset.pack_svfn in --profile
(default: the input's own layout; --box sets the ink box policy): every glyph, metric, JSET block and flag is kept, only the dy of the
glyphs asked for changes, and the range is worked out again from all glyphs. Glyphs are stored in code point order.

  svfdy.py IN.svf OUT.svf --range 0x20-0x7e --dy 3        # one dy for a range of code points
  svfdy.py IN.svf OUT.svf --set 0x67,0x6a,0x70-0x71,0x79=3 --set 0x5e=-1
  svfdy.py IN.svf OUT.svf --json dy.json                  # {"0x67": 3, "106": 3, "y": 3}
  svfdy.py IN.svf OUT.svf --clear                          # every dy back to 0
  svfdy.py IN.svf --show                                   # the range and the glyphs with a dy

Code points the font lacks are skipped (counted). A dy on a jamo piece (U+F0000..) is refused: the engine composes a
syllable inside its cell.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jamoset  # noqa: E402

def parse_cps(text):
    """'0x20-0x7e,0x2026,a' -> [code points]. A single character stands for itself."""
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if len(part) == 1:
            out.append(ord(part))
            continue
        if "-" in part[1:]:
            k = part.index("-", 1)
            lo, hi = int(part[:k], 0), int(part[k + 1:], 0)
            if hi < lo:
                raise ValueError(f"range {part} runs backwards")
            out.extend(range(lo, hi + 1))
        else:
            out.append(int(part, 0))
    return out


def json_dy(path):
    """{code point: dy} from a JSON object whose keys are '0x67', '103' or 'g'."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    out = {}
    for k, v in raw.items():
        cp = ord(k) if len(k) == 1 else int(k, 0)
        out[cp] = int(v)
    return out


def read(data):
    """The parsed face @p data (jamoset.parse_svfn); ValueError when it has no metrics table to carry a dy."""
    f = jamoset.parse_svfn(data)
    if not f.flags & jamoset.FLAG_VARIABLE or not f.metrics_ok:
        raise ValueError("the font has no metrics table (flags bit 0), so no place for a dy")
    if f.jset_bad:
        raise ValueError("the font has a JSET block it cannot use (jamo flag set, block missing or invalid): "
                         "rewriting it would drop the block and leave a plain face")
    return f


def current(data):
    """{cp: dy} of every glyph with a dy, and the header range."""
    f = read(data)
    return dict(f.dy), (f.dy_min, f.dy_max)


def _write(f, dy, profile):
    glyphs = [(cp, f.glyphs[cp], *f.metrics[cp]) for cp in sorted(f.glyphs)]
    return jamoset.write_svfn(f.cell_w, f.cell_h, f.ascent, glyphs, f.jset or b"",
                              f.flags & ~(jamoset.FLAG_VARIABLE | jamoset.FLAG_JAMO), f.bpp, dy, profile)


def apply(data, want, clear=False, profile=None):
    """The font @p data (v3) with the glyphs of @p want {cp: dy} given that dy (and every other glyph's kept, or
    0 when @p clear), the header range recomputed, written as v3 in @p profile (None: the face's own layout). Returns (bytes, {"set": n, "missing":
    [cps]})."""
    f = read(data)
    dy = {} if clear else dict(f.dy)
    missing, n = [], 0
    for cp, v in sorted(want.items()):
        if cp >= jamoset.PIECE_BASE:
            raise ValueError(f"U+{cp:04X} is a jamo piece: the engine composes a syllable in its cell, no dy")
        if not -128 <= v <= 127:
            raise ValueError(f"dy {v} of U+{cp:04X} does not fit a signed byte")
        if cp not in f.glyphs:
            missing.append(cp)
            continue
        dy[cp] = v
        n += 1
    dy = {cp: v for cp, v in dy.items() if v}
    lo, hi = jamoset.dy_range(dy, f.cell_h)
    return _write(f, dy, jamoset.face_profile(f, profile)), {"set": n, "missing": missing, "dy_min": lo, "dy_max": hi}


def verify(before, after):
    """Only the dy of a glyph and the header range may differ: the cells, metrics, JSET block, flags and sizes of
    the result are those of @p before; the result's dy checks."""
    b, f = jamoset.parse_svfn(before), jamoset.parse_svfn(after)
    for name in ("flags", "bpp", "cell_w", "cell_h", "ascent", "glyphs", "metrics", "jset", "jset_bad"):
        if getattr(b, name) != getattr(f, name):
            raise ValueError(f"{name} changed")
    jamoset.check_dy(f)
    return f


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--range", help="code points (e.g. 0x20-0x7e,0x2026) given --dy")
    ap.add_argument("--dy", type=int, help="the dy for --range")
    ap.add_argument("--set", action="append", default=[], metavar="CPS=DY", help="code points and their dy; repeatable")
    ap.add_argument("--json", help="a JSON object {code point: dy}")
    ap.add_argument("--clear", action="store_true", help="every glyph's dy to 0 first")
    ap.add_argument("--show", action="store_true", help="print the range and the glyphs that have a dy")
    jamoset.add_profile_args(ap, None)
    a = ap.parse_args(argv)

    profile = jamoset.profile_arg(ap, a)
    try:
        return _run(ap, a, profile)
    except (ValueError, OSError) as e:
        ap.error(f"{a.input}: {e}")


def _run(ap, a, profile):
    data = open(a.input, "rb").read()
    if a.show and not a.output:
        f = read(data)
        print(f"{a.input}: dy range {f.dy_min}..{f.dy_max}, {len(f.dy)} glyphs with a dy")
        for cp, v in sorted(f.dy.items()):
            print(f"  U+{cp:04X} {chr(cp) if 0x20 < cp < 0x7f else ''} {v:+d}")
        return 0
    if not a.output:
        ap.error("an output file is needed (or --show)")
    want = {}
    if (a.range is None) != (a.dy is None):
        ap.error("--range and --dy go together")
    if a.range is not None:
        for cp in parse_cps(a.range):
            want[cp] = a.dy
    for item in a.set:
        if "=" not in item:
            ap.error(f"--set {item}: CPS=DY")
        cps, dy = item.rsplit("=", 1)
        for cp in parse_cps(cps):
            want[cp] = int(dy)
    if a.json:
        want.update(json_dy(a.json))
    if not want and not a.clear:
        ap.error("nothing to set: --range/--dy, --set, --json or --clear")
    if profile is None and a.box:
        profile = jamoset.face_profile(read(data), None, a.box)
    out, info = apply(data, want, a.clear, profile)
    verify(data, out)
    with open(a.output, "wb") as fh:
        fh.write(out)
    miss = f", {len(info['missing'])} code points not in the font" if info["missing"] else ""
    print(f"{a.output}: dy set on {info['set']} glyphs, range {info['dy_min']}..{info['dy_max']}{miss}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
