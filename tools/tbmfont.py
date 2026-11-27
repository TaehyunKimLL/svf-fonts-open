#!/usr/bin/env python3
"""Read the header of a Korean Windows 3.1 / Windows 95 `.TBM` bitmap font and list where its glyphs are.

Korean Windows 3.1 (`BT16.TBM`, `BT20.TBM`) and the Windows 95 Korean setup's MINI cabinet (`GULIM16.TBM`,
`GULIM12.TBM`) carry wansung (KS X 1001) bitmap fonts in one layout. Nothing here runs anything from the file: it
reads bytes. Run it with `python3 -I`.

  tbmfont.py info FILE                  the header, the glyph table, and the offset of each block for rawcarve.py
  tbmfont.py map [--blocks B,...] -o MAP.txt
                                        "GLYPH U+XXXX" lines (rawcarve.py bdf --chars map) for KS X 1001 rows
                                        stored one after the other with no gap: symbols (rows A1-AC, 1,128 slots),
                                        hangul (B0-C8, 2,350), hanja (CA-FD, 4,888); default all three in that order

File layout (all numbers little-endian):

  0x00  32 bytes  "TTBITMAP VARIABLE-PITCH HANGEUL " (the signature)
  0x20  u16       the height of a double-byte glyph (16, 20, 12)
  0x22  u16       its width
  0x24  u16       N, the number of range records
  0x26  N x 16    range records: u32 file offset, u16 bytes, u16 bytes (the same number again), 8 zero bytes; the
                  ranges follow one another and together hold the glyph data
  then  M x 7     the glyph table, one entry per glyph in code order: u16 range, u16 offset in the range, u16 bytes,
                  u8 width (the height is bytes / ceil(width / 8)); it runs up to the first range's offset
  then            the glyph data: rows of ceil(width / 8) bytes, most significant bit on the left, ink = 0 bits
                  (rawcarve.py --invert)

The four files measured hold M = 8,494 glyphs: 128 single-byte glyphs (codes 0x00-0x7F, half the width) and 8,366
double-byte glyphs in KS X 1001 order with no gaps (symbol rows A1-AC, 1,128 slots; the syllables B0A1-C8FE, 2,350;
hanja CA-FD, 4,888). `info` checks that the table tiles the data and prints the offsets of these blocks, so
rawcarve.py cuts each block with --dense (syllables) or --chars map (symbols and hanja, with the map from `map`).
"""

import argparse
import os
import struct
import sys

SIGNATURE = b"TTBITMAP VARIABLE-PITCH HANGEUL "
MAX_FILE = 16 << 20
ASCII_COUNT = 128
BLOCKS = {"symbols": range(0xA1, 0xAD), "hangul": range(0xB0, 0xC9), "hanja": range(0xCA, 0xFE)}


class TbmError(Exception):
    pass


def parse(data):
    """{"height", "width", "ranges": [(offset, bytes)], "glyphs": [(file offset, width, height, bytes)], "data",
    "end"} of a TBM file's bytes; TbmError when the header or the glyph table does not hold together."""
    if data[:32] != SIGNATURE:
        raise TbmError("no TTBITMAP VARIABLE-PITCH HANGEUL signature")
    if len(data) < 0x26:
        raise TbmError("header cut short")
    height, width, n = struct.unpack_from("<HHH", data, 0x20)
    table = 0x26 + 16 * n
    if n == 0 or table > len(data):
        raise TbmError(f"{n} range records do not fit in the file")
    ranges = []
    for i in range(n):
        off, size, size2 = struct.unpack_from("<IHH", data, 0x26 + 16 * i)
        if size != size2:
            raise TbmError(f"range {i}: sizes {size} and {size2} differ")
        if off + size > len(data):
            raise TbmError(f"range {i}: {off:#x} + {size} is past the end of the file")
        if ranges and off != ranges[-1][0] + ranges[-1][1]:
            raise TbmError(f"range {i} at {off:#x} does not follow range {i - 1}")
        ranges.append((off, size))
    start = ranges[0][0]
    if start < table or (start - table) % 7:
        raise TbmError(f"glyph table {table:#x}..{start:#x} is not a whole number of 7-byte entries")
    glyphs = []
    pos = start
    for k in range((start - table) // 7):
        r, off, size, w = struct.unpack_from("<HHHB", data, table + 7 * k)
        if r >= n:
            raise TbmError(f"glyph {k}: range {r} of {n}")
        at = ranges[r][0] + off
        rb = (w + 7) // 8
        if w == 0 or size % rb or off + size > ranges[r][1]:
            raise TbmError(f"glyph {k}: {size} bytes of width {w} at {off} do not fit range {r}")
        if at != pos:
            raise TbmError(f"glyph {k} at {at:#x}: the glyphs do not follow one another (expected {pos:#x})")
        glyphs.append((at, w, size // rb, size))
        pos = at + size
    return {"height": height, "width": width, "ranges": ranges, "glyphs": glyphs, "data": start, "end": pos,
            "size": len(data)}


def load(path):
    """parse() of the file at @p path; TbmError when it is larger than MAX_FILE (checked before it is read)."""
    if os.path.getsize(path) > MAX_FILE:
        raise TbmError(f"{path}: larger than {MAX_FILE} bytes")
    with open(path, "rb") as fh:
        data = fh.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise TbmError(f"{path}: larger than {MAX_FILE} bytes")
    return parse(data)


def runs(glyphs):
    """[(first index, count, width, height, first offset)] of the glyphs grouped by size."""
    out = []
    for i, (at, w, h, _) in enumerate(glyphs):
        if out and out[-1][2:4] == [w, h]:
            out[-1][1] += 1
        else:
            out.append([i, 1, w, h, at])
    return [tuple(r) for r in out]


def blocks(t):
    """{name: (file offset, glyphs)} of the ASCII, symbol, syllable and hanja blocks when the file has the 128 +
    8,366 layout: exactly 128 half-width glyphs (half the cell's width, the cell's height), then 8,366 glyphs of the
    cell size; {} otherwise."""
    g = t["glyphs"]
    sizes = [len(ks_rows([name])) for name in BLOCKS]
    w, h = t["width"], t["height"]
    shape = [r[1:4] for r in runs(g)]
    if shape != [(ASCII_COUNT, w // 2, h), (sum(sizes), w, h)]:
        return {}
    out = {"ascii": (g[0][0], ASCII_COUNT)}
    i = ASCII_COUNT
    for name, count in zip(BLOCKS, sizes):
        out[name] = (g[i][0], count)
        i += count
    return out


def ks_rows(names):
    """[(lead, trail)] of the 94-slot KS X 1001 rows of the named blocks, in order."""
    return [(lead, trail) for name in names for lead in BLOCKS[name] for trail in range(0xA1, 0xFF)]


def map_lines(names):
    """'GLYPH U+XXXX' lines: glyph i is the i-th slot of the named blocks; slots no code point decodes to are left
    out (the unassigned symbol slots)."""
    out = []
    for i, (lead, trail) in enumerate(ks_rows(names)):
        try:
            ch = bytes((lead, trail)).decode("euc_kr")
        except UnicodeDecodeError:
            continue
        out.append(f"{i} U+{ord(ch):04X}")
    return out


def cmd_info(a):
    t = load(a.file)
    print(f"{a.file}: {t['size']} bytes, cell {t['width']}x{t['height']}, {len(t['ranges'])} ranges, "
          f"{len(t['glyphs'])} glyphs, data {t['data']:#x}..{t['end']:#x}, {t['size'] - t['end']} bytes after the data")
    for first, count, w, h, at in runs(t["glyphs"]):
        print(f"  glyphs {first}..{first + count - 1}: {count} of {w}x{h} ({(w + 7) // 8 * h} bytes) from {at:#x}")
    for name, (at, count) in blocks(t).items():
        print(f"  {name}: offset {at:#x} ({at}), {count} glyphs")


def cmd_map(a):
    names = a.blocks.split(",")
    bad = [n for n in names if n not in BLOCKS]
    if bad:
        raise TbmError(f"--blocks: unknown {bad[0]!r} (symbols, hangul, hanja)")
    lines = map_lines(names)
    with open(a.output, "w", encoding="ascii") as fh:
        fh.write("# tbmfont.py map --blocks " + a.blocks + "\n" + "\n".join(lines) + "\n")
    print(f"wrote {a.output}: {len(lines)} glyphs of {len(ks_rows(names))} slots ({a.blocks})")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info")
    p.add_argument("file")
    p.set_defaults(fn=cmd_info)
    p = sub.add_parser("map")
    p.add_argument("--blocks", default="symbols,hangul,hanja")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_map)
    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (TbmError, OSError) as e:
        print(f"tbmfont.py: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
