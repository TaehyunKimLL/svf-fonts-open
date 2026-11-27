#!/usr/bin/env python3
"""Write the `rawcarve.py compose` spec of an NKP Hangul TSR (the 1989 Hercules Hangul drivers NKP.COM V3.00 and NKP3.COM)
from the driver's own tables: the worked example of docs/recipes/programs-and-drivers.md, "NKP: a Hercules Hangul TSR with cropped pieces".

  nkpspec.py find NKP.COM                  the table addresses, found by the instruction bytes that use them
  nkpspec.py spec NKP.COM -o NKP.json      the compose spec (addresses found, or given with --desc ... --med)

Nothing here runs the driver: it reads bytes. The spec holds offsets and rules, no glyph. What the driver's Hangul routine
does (read from its 8086 code; all addresses are memory addresses of the .COM image, file offset = address - 0x100):

- the Johab code is split by three 32-byte tables (initial, vowel, final: 5-bit code -> the driver's jamo number, 31 =
  none); the initial and final numbers are the Unicode order, the vowels have the driver's own order;
- the initial piece is drawn from the set a 42-byte table names (21 vowels without a final, 21 with one; each value the
  byte offset of a piece-set record, record = value / 6), piece = the initial;
- the medial piece from an 84-byte table of (u8 piece, u8 record byte offset) pairs (21 without a final, 21 with);
- the final piece from record 96 (the 17th), piece = the final;
- a piece-set record is 6 bytes: u16 address of the set's first piece, u8 stride (bytes from one piece to the next),
  u8 first and u8 end byte of the 32-byte (16x16, 2 bytes a row) cell it is ORed into, u8 flags. Flag bit 0 set: the
  piece is 16 pixels wide and fills cell bytes first..end-1, so it is (end - first) / 2 = stride / 2 rows from row
  first / 2. Bit 0 clear: one byte a row into every other cell byte (first, first + 2, ... < end), the right 8 pixels
  when first is odd, so it is stride = (end - first + 1) / 2 rows of 8 pixels from row first // 2.

The instruction patterns (`find`): the record table from `mov dx,imm16; add bx,dx; mov cx,[bx]; mov al,[bx+2]`, the
initial/vowel/final tables from the `mov al,[bx+imm16]` after the code is split, the initial-set table from
`mov bl,[bx+imm16]; call`, the medial table from `mov ah,[bx+imm16]; mov bl,[bx+imm16]`, the English font from
`mov ax,imm16; add si,ax; call` (8x16, 128 glyphs). Each is the first match; check them against the disassembly.
"""

import argparse
import json
import re
import struct
import sys

JUNG_FIELD = (3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 22, 23, 26, 27, 28, 29)  # Unicode V -> 5-bit code
PATTERNS = {
    "desc": rb"\xba(..)\x03\xda\x8b\x0f\x8a\x47\x02",
    "cho": rb"\x24\x7f\xd0\xe8\xd0\xe8\x8a\xd8\x32\xff\x8a\x87(..)",
    "jung": rb"\xd3\xeb\x8a\x87(..)",
    "jong": rb"\x80\xe3\x1f\x8a\x87(..)",
    "iset": rb"\x8a\x9f(..)\xe8",
    "med": rb"\x8a\xa7(..)\x8a\x9f",
    "ascii": rb"\xb8(..)\x03\xf0\xe8",
}
RECORDS = 17
FINAL_RECORD = 96


class SpecError(Exception):
    pass


def find(d):
    """{name: memory address} of the first match of each pattern."""
    out = {}
    for name, pat in PATTERNS.items():
        m = re.search(pat, d, re.S)
        if m:
            out[name] = struct.unpack("<H", m.group(1))[0]
    return out


def table(d, addr, n, what):
    off = addr - 0x100
    if off < 0 or off + n > len(d):
        raise SpecError(f"{what} table at {addr:#x} ({n} bytes) is outside the file")
    return d[off:off + n]


def piece_set(d, rec, addr):
    base, stride, first, end, flags = struct.unpack("<HBBBB", table(d, addr + rec, 6, f"record {rec}"))
    if stride < 1 or end <= first or end > 32 or (flags & 1 and end - first < 2):
        raise SpecError(f"record {rec}: stride {stride}, bytes {first}..{end} is not a piece of a 32-byte cell")
    if base < 0x100:
        raise SpecError(f"record {rec}: piece address {base:#x} is below the .COM image (0x100)")
    if flags & 1:
        return {"offset": base - 0x100, "stride": stride, "x": 0, "y": first // 2, "width": 16,
                "height": (end - first) // 2}
    return {"offset": base - 0x100, "stride": stride, "x": 8 * (first & 1), "y": first // 2, "width": 8,
            "height": (end - first + 1) // 2}


def spec(d, addrs):
    for k in ("desc", "jung", "iset", "med"):
        if k not in addrs:
            raise SpecError(f"no {k} table: give --{k}")
    jung = table(d, addrs["jung"], 32, "vowel")
    vorder = [jung[c] for c in JUNG_FIELD]
    if sorted(vorder) != list(range(21)):
        raise SpecError(f"the vowel table at {addrs['jung']:#x} does not number the 21 vowels 0..20")
    iset = table(d, addrs["iset"], 42, "initial-set")
    med = table(d, addrs["med"], 84, "medial")
    if "cho" in addrs:
        cho = table(d, addrs["cho"], 32, "initial")
        if list(cho[2:21]) != list(range(19)):
            raise SpecError("the initial table is not the Unicode order (2..20 -> 0..18): not an NKP layout")
    if "jong" in addrs:
        jong = table(d, addrs["jong"], 32, "final")
        if list(jong[2:18]) + list(jong[19:30]) != list(range(27)):
            raise SpecError("the final table is not the Unicode order: not an NKP layout")
    used = set(iset) | set(med[1::2]) | {FINAL_RECORD}
    if any(r % 6 or r >= 6 * RECORDS for r in used):
        raise SpecError("a selection table names a record that is not a multiple of 6 below 102")
    sets = {f"d{r}": piece_set(d, r, addrs["desc"]) for r in sorted(used)}
    return {"cell": [16, 16], "vowel_order": vorder, "sets": sets,
            "initial": {"nofinal": [f"d{x}" for x in iset[:21]], "final": [f"d{x}" for x in iset[21:]]},
            "medial": {"nofinal": [[f"d{med[2 * i + 1]}", med[2 * i]] for i in range(21)],
                       "final": [[f"d{med[42 + 2 * i + 1]}", med[42 + 2 * i]] for i in range(21)]},
            "final": {"set": f"d{FINAL_RECORD}"}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("find")
    p.add_argument("file")
    p = sub.add_parser("spec")
    p.add_argument("file")
    for k in ("desc", "cho", "jung", "jong", "iset", "med"):
        p.add_argument(f"--{k}", type=lambda s: int(s, 0), help=f"memory address of the {k} table (default: found)")
    p.add_argument("-o", "--output", required=True)
    a = ap.parse_args(argv)
    try:
        with open(a.file, "rb") as fh:
            d = fh.read()
        found = find(d)
        if a.cmd == "find":
            for k in PATTERNS:
                v = found.get(k)
                print(f"{k:6s} " + (f"{v:#06x} (file {v - 0x100:#x})" if v is not None else "not found"))
            return
        addrs = dict(found)
        for k in ("desc", "cho", "jung", "jong", "iset", "med"):
            if getattr(a, k) is not None:
                addrs[k] = getattr(a, k)
        s = spec(d, addrs)
    except (SpecError, OSError, struct.error) as e:
        print(f"nkpspec.py: {e}", file=sys.stderr)
        sys.exit(1)
    with open(a.output, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(s, fh, indent=1)
    eng = f"; the English font at file {found['ascii'] - 0x100:#x}" if "ascii" in found else ""
    print(f"wrote {a.output}: {len(s['sets'])} piece sets{eng}")


if __name__ == "__main__":
    main()
