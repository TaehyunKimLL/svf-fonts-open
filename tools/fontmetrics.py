#!/usr/bin/env python3
"""Do a font's advances actually clear its glyphs?

If a glyph's ink reaches past its advance, the next character starts on top of
it. The SVFN metrics table carries both numbers, so this is answerable from the
file without rendering anything:

    metrics per glyph = advance, bearingX, ink width, reserved

A glyph overlaps the next when bearingX + inkWidth > advance.

Usage:
    python3 fontmetrics.py tools/korean/indy3kor/vj00.fnt [more.fnt ...]
"""
import os
import struct
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:  # python -I drops the script's directory
    sys.path.insert(0, HERE)
import jamoset  # noqa: E402


def report(path):
    data = open(path, "rb").read()
    try:
        f = jamoset.parse_svfn(data)
    except (ValueError, struct.error) as e:
        print(f"{path}: not an SVFN v3 file ({e})")
        return

    proportional = bool(f.flags & jamoset.FLAG_VARIABLE)
    count, cellW = f.count, f.cell_w
    print(f"{path}")
    print(f"  version {f.version}  cell {cellW}x{f.cell_h}  bpp={f.bpp}  glyphs={count}  "
          f"{'proportional' if proportional else 'fixed width'}")

    if not proportional or not f.metrics_ok:
        print(f"  no metrics table - every glyph advances by the cell width ({cellW})")
        print()
        return

    overlap = []
    advances = Counter()
    widths = Counter()
    for cp, (advance, bearingX, inkW) in sorted(f.metrics.items()):
        advances[advance] += 1
        widths[inkW] += 1
        reach = bearingX + inkW
        if reach > advance:
            overlap.append((cp, advance, bearingX, inkW, reach - advance))

    print(f"  advances seen: {sorted(advances)[:12]}{' ...' if len(advances) > 12 else ''}")
    print(f"  ink widths:    {sorted(widths)[:12]}{' ...' if len(widths) > 12 else ''}")

    if overlap:
        worst = sorted(overlap, key=lambda t: -t[4])[:6]
        print(f"  *** {len(overlap)} of {count} glyphs reach past their advance ***")
        print("   U+code  advance  bearingX  inkW  overhang")
        for cp, adv, bx, iw, over in worst:
            print(f"   {cp:06X} {adv:8d} {bx:9d} {iw:5d} {over:9d}")
    else:
        print(f"  every glyph fits inside its advance")
    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    for path in sys.argv[1:]:
        try:
            report(path)
        except OSError as exc:
            print(f"{path}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
