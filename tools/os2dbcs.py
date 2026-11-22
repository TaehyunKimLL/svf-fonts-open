#!/usr/bin/env python3
"""Decode an OS/2 "System DBCS" font ($korZN16.FNT / $korZN24.FNT of OS/2 Warp Korean; the Japanese and Chinese
$jpnZN.., $chtZN.. share the format) into a raw glyph table that `rawcarve.py bdf` reads.

  os2dbcs.py info FILE                 the header: cell, bytes a glyph, code ranges, glyph records
  os2dbcs.py table FILE -o OUT.bin     every glyph number 256..8997 in order (absent ones blank), row-major: the KS X 1001
                                       94 x 94 table from A1A1, so `rawcarve.py bdf OUT.bin --glyph 16x16 --chars
                                       ks-hangul --grid 0xA1,0xA1,94` cuts the 2,350 syllables out of it

The Korean fonts are precomposed (완성형): 1,128 symbols, 2,350 syllables and 4,888 Hanja in KS X 1001 order. Nothing
here runs OS/2 code; the format (read from the bytes and from the 16-bit FNTGETIMAGE code of FNTCALLS.DLL; the
johab-fonts research notes, `os2-dbcs.md`):

  0x00   "System DBCS NN  ", then u16 codepage tag, width, height, 1, bytes a glyph, 0, 1 and an 8-byte date
  0x80   u16 n, then n (first, last) lead-byte pairs; 0xA0: u16 n, then n (first, last) glyph numbers
         (glyph number = 256 + (lead - 0xA1) * 94 + (trail - 0xA1))
  0xC0   a 256-entry lookup of the next 8 bits of the stream: entry = (code length << 4) | nibble; entry 0 is an
         escape: the next 3 bits index the 8 entries at 0x1C0 (code length 8 + their length field)
  0x200  a 2,048-byte context table: 4,096 nibbles, nibble = T[(above2 << 8) | (above1 << 4) | residual]
  0x1A00 records in 512-byte blocks: u16 glyph number, u8 length, the Huffman-coded residual nibbles (two a byte,
         high first); a record that does not fit starts the next block (the rest is 0xFF)

A glyph is decoded as 2 x bytes-a-glyph nibbles, then each byte's high and low nibbles are predicted from the bytes one
and two rows above through the context table.
"""

import argparse
import struct
import sys


class DbcsError(Exception):
    pass


HEADER_END = 0x1A00
MAX_GLYPH = 8997


def header(d):
    if d[:11] != b"System DBCS":
        raise DbcsError("not an OS/2 System DBCS font (no 'System DBCS' at 0)")
    if len(d) < HEADER_END:
        raise DbcsError(f"truncated: {len(d)} bytes, the header and tables take {HEADER_END}")
    w, h, _, bpg = struct.unpack_from("<HHHH", d, 0x12)
    if not (1 <= w <= 64 and 1 <= h <= 64):
        raise DbcsError(f"cell {w}x{h} is outside 1..64")
    if bpg != (w + 7) // 8 * h:
        raise DbcsError(f"{bpg} bytes a glyph does not match a {w}x{h} cell ({(w + 7) // 8 * h})")
    n = struct.unpack_from("<H", d, 0x80)[0]
    if n > 15:
        raise DbcsError(f"{n} lead-byte ranges: the table holds at most 15")
    leads = [struct.unpack_from("<BB", d, 0x82 + 2 * i) for i in range(n)]
    n = struct.unpack_from("<H", d, 0xA0)[0]
    if n > 7:
        raise DbcsError(f"{n} glyph-number ranges: the table holds at most 7")
    ranges = [struct.unpack_from("<HH", d, 0xA2 + 4 * i) for i in range(n)]
    return w, h, bpg, leads, ranges


def decode(d):
    """{glyph number: bytes} of every record. The records fill 512-byte blocks from 0x1A00: a record never crosses a
    block, and the rest of a block a record does not fit in is 0xFF (a glyph number 0xFFFF). A record's Huffman stream
    must end within its own payload."""
    w, h, bpg, _, _ = header(d)
    rb = (w + 7) // 8
    tab, ext, ctx = d[0xC0:0x1C0], d[0x1C0:0x1C8], d[0x200:0xA00]

    def nib(c):
        b = ctx[c >> 1]
        return (b & 15) if c & 1 else (b >> 4)

    def glyph(pos, end, g):
        """The glyph whose payload is d[pos:end]."""
        limit = end * 8

        def bits(bp, n):
            # a peek may look past the payload (the next record's bytes, as the OS/2 reader does); a code may not
            if (bp + n + 7) >> 3 > len(d):
                raise DbcsError(f"glyph {g}: the code runs past the end of the file")
            return int.from_bytes(d[bp >> 3:(bp >> 3) + 3].ljust(3, b"\0"), "big") >> (24 - n - (bp & 7)) & ((1 << n) - 1)
        bp, nibs = pos * 8, []
        while len(nibs) < 2 * bpg:
            if bp >= limit:
                raise DbcsError(f"glyph {g}: the code runs past its {end - pos}-byte payload")
            v = bits(bp, min(8, len(d) * 8 - bp)) << max(0, 8 - (len(d) * 8 - bp))
            if v == 0:
                e = ext[bits(bp + 8, 3)]
                length = 8 + (e >> 4)
            else:
                e = tab[v]
                length = e >> 4
            if length == 0:
                if bp + 8 > limit:
                    raise DbcsError(f"glyph {g}: the code runs past its {end - pos}-byte payload")
                raise DbcsError(f"glyph {g}: code of length 0 at bit {bp}")
            if bp + length > limit:
                raise DbcsError(f"glyph {g}: the code runs past its {end - pos}-byte payload")
            nibs.append(e & 15)
            bp += length
        res = bytes((nibs[2 * k] << 4) | nibs[2 * k + 1] for k in range(bpg))
        out = bytearray(bpg)
        for i in range(bpg):
            c = out[i - 2 * rb] if i >= 2 * rb else 0
            a = out[i - rb] if i >= rb else 0
            r = res[i]
            out[i] = (nib(((c >> 4) << 8) | ((a >> 4) << 4) | (r >> 4)) << 4) | nib(
                ((c & 15) << 8) | ((a & 15) << 4) | (r & 15))
        return bytes(out)

    glyphs, prev = {}, -1
    for block in range(HEADER_END, len(d), 512):
        p, end = block, min(block + 512, len(d))
        while p + 3 <= end:
            g, ln = d[p] | d[p + 1] << 8, d[p + 2]
            if g == 0xFFFF:
                break  # the rest of the block is padding
            if p + 3 + ln > end:
                raise DbcsError(f"record of glyph {g} at {p:#x} runs past its block or the file")
            if g > MAX_GLYPH or g <= prev:
                raise DbcsError(f"record at {p:#x}: glyph number {g} after {prev}")
            glyphs[g] = glyph(p + 3, p + 3 + ln, g)
            prev = g
            p += 3 + ln
    return glyphs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info")
    p.add_argument("file")
    p = sub.add_parser("table")
    p.add_argument("file")
    p.add_argument("-o", "--output", required=True)
    a = ap.parse_args(argv)
    try:
        with open(a.file, "rb") as fh:
            d = fh.read()
        w, h, bpg, leads, ranges = header(d)
        if a.cmd == "info":
            print(f"{a.file}: {d[:16].decode('ascii', 'replace').strip()!r}, {w}x{h}, {bpg} bytes a glyph")
            print("  lead bytes: " + ", ".join(f"{lo:02X}-{hi:02X}" for lo, hi in leads))
            print("  glyph numbers: " + ", ".join(f"{lo}-{hi} ({hi - lo + 1})" for lo, hi in ranges))
            g = decode(d)
            print(f"  {len(g)} glyph records; syllables (1666-4015) present: "
                  f"{sum(1 for i in range(1666, 4016) if i in g)}")
            return
        g = decode(d)
        blank = bytes(bpg)
        with open(a.output, "wb") as fh:
            fh.write(b"".join(g.get(i, blank) for i in range(256, 8998)))
        print(f"wrote {a.output}: {8998 - 256} slots of {bpg} bytes ({w}x{h}), {len(g)} glyphs present; "
              f"glyph number 256 + n is KS X 1001 code (0xA1 + n // 94, 0xA1 + n % 94)")
    except (DbcsError, struct.error, OSError) as e:
        print(f"os2dbcs.py: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
