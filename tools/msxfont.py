#!/usr/bin/env python3
"""The Korean MSX fonts that are not a plain glyph table: the CPC-400S code-to-slot map and the MSX1 syllable layout.

Nothing here runs the machine's code: it reads bytes. Run it with `python3 -I` on ROM dumps.

  msxfont.py kfn-map U44 -o MAP.txt
      the Hangul syllables the Daewoo CPC-400 / 400S driver can draw from its 256 KB font ROM, as "SLOT U+XXXX" lines
      for `rawcarve.py bdf --chars map --map MAP.txt`. U44 is the 64 KB chip image CPC-400S.U44 (or the 16 KB
      "Kanji control ROM", its last quarter). Routine 8A96h of that ROM (mapped at 8000h) takes the Johab code and
      looks the trail byte up in one of two lists, A and B, each with 76 start offsets by lead byte 88h..D3h
      (word tables at 97BFh and 9859h, byte lists at 98F3h and 9E18h); slot = 0581h + list index (A) or
      1141h + list index (B). A syllable in neither list is not drawable.
  msxfont.py msx1 BIOS [--offset 0x1B49] [--ascii-top 8] -o OUT.bdf
      the 11,172 syllables of the Korean MSX1 Hangul ROM (모아쓰기 mode) built from the BIOS character table (256 cells of
      8x8, at 0x1B49 on the Daewoo DPC-100/180/200 and Goldstar FC-80U / GFC-1080 BIOS) by the layout rule below, and
      ASCII 0x20-0x7E as the table's 8x8 cells, --ascii-top rows down in the 16-row cell. A syllable is 8 or 16
      wide (one or two text columns) and 16 tall (two text rows); the BDF advance is its width.
  msxfont.py msx1-verify PREFIX [--bios BIOS --offset 0x1B49]
      the rule against an emulator harvest: PREFIX.index (one hex code point a line), PREFIX.names (768-byte SCREEN 1
      name tables, 77 syllables each, 7 to a row 4 columns apart from column 2, 2 rows apart), PREFIX.patterns (the
      2,048-byte pattern table). Exit 1 when a syllable differs, or (with --bios) a cell other than the cursor 0xFF.

The MSX1 layout (found by printing every syllable on the machine and reading the name table; cell codes of the table):
  initial L 0..18 = 0x86 + L;  vertical vowel cells ㅏ99 ㅐ9A ㅑ9B ㅒ9C ㅓ9D ㅔ9E ㅕ9F ㅖA0 ㅣA6;  ㅗA1 ㅛA2 ㅜA3 ㅠA4 ㅡA5;
  a final is the consonant's own cell (double finals two cells); M(L, h) = initial merged with ㅗㅛㅜㅠㅡ (h 0..4) =
  0xA7 + 5L + h, from 5L + h = 85 on 0x02 + (5L + h - 85);  ext(v) = the stem below a vertical vowel: 0C (ㅏㅑㅣ),
  0D (ㅓㅕ), 0E (ㅐㅒㅔㅖ);  _ = blank cell 0xFC.  Rows top / bottom:
    vertical vowel v     no final [L v] / [_ ext(v)]      final [L v] / [T1 T2|_]
    ㅗㅛㅜㅠㅡ h          no final [L] / [h]   a one-cell final [M(L,h)] / [T1]   a two-cell final [M(L,h) _] / [T1 T2]
    compound h + v       no final [L v] / [h ext(v)]      final [M(L,h) v] / [T1 T2|_]
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:  # python -I drops the script's directory
    sys.path.insert(0, HERE)
import binscan  # noqa: E402
import rawcarve  # noqa: E402


class MsxError(Exception):
    pass


# ---- CPC-400S: code -> slot ------------------------------------------------------------------------------------------

CTRL_BASE = 0x8000                       # the control ROM's CPU address
LISTS = ((0x97BF, 0x98F3, 0x0581), (0x9859, 0x9E18, 0x1141))   # (start-offset words, trail bytes, first slot): A, B
LEADS = 76                               # lead bytes 0x88 .. 0xD3


MAX_HARVEST = 4 << 20          # a full harvest is 146 x 768 bytes of name tables; any input file is capped


def read_capped(path, cap):
    """The bytes of @p path, refused (before reading) when it is larger than @p cap."""
    size = os.path.getsize(path)
    if size > cap:
        raise MsxError(f"{path}: {size} bytes, more than the {cap} this input can be")
    with open(path, "rb") as fh:
        return fh.read()


def control_rom(data):
    """The 16 KB control ROM: the last quarter of the 64 KB U44 image, or a 16 KB file as it is."""
    if len(data) == 0x10000:
        return data[0xC000:]
    if len(data) == 0x4000:
        return data
    raise MsxError(f"{len(data)} bytes: give the 64 KB CPC-400S.U44 image or its 16 KB control ROM")


def kfn_map(data):
    """{code point: slot} of every syllable the driver's lists A and B reach."""
    c = control_rom(data)

    def w(a):
        return c[a - CTRL_BASE] | c[a - CTRL_BASE + 1] << 8

    out = {}
    for words, base, first in LISTS:
        offs = [w(words + 2 * i) for i in range(LEADS + 1)]
        if offs != sorted(offs) or base - CTRL_BASE + offs[-1] > len(c):
            raise MsxError(f"the start offsets at {words:#x} are not a sorted list inside the ROM: not this driver")
        for i in range(LEADS):
            for r in range(offs[i], offs[i + 1]):
                t = c[base - CTRL_BASE + r]
                if t in (0, 0xFF):          # the sentinels at the ends of a list
                    continue
                try:
                    ch = bytes((0x88 + i, t)).decode("johab")
                except UnicodeDecodeError:
                    continue
                if len(ch) == 1 and 0xAC00 <= ord(ch) <= 0xD7A3:
                    out.setdefault(ord(ch), first + r)
    return out


def cmd_kfn_map(a):
    m = kfn_map(read_capped(a.file, 0x10000))
    if not m:
        raise MsxError("no syllable found: not the CPC-400S control ROM")
    ks = {ord(bytes((le, tr)).decode("euc_kr")) for le in range(0xB0, 0xC9) for tr in range(0xA1, 0xFF)}
    with open(a.output, "w", encoding="ascii") as fh:
        for cp, slot in sorted(m.items(), key=lambda kv: kv[1]):
            fh.write(f"{slot} U+{cp:04X}\n")
    print(f"wrote {a.output}: {len(m)} syllables ({sum(1 for c in m if c in ks)} of the 2,350 KS X 1001), "
          f"slots {min(m.values())}..{max(m.values())}")


# ---- MSX1: the 모아쓰기 layout --------------------------------------------------------------------------------------

HORIZ = {8: 0xA1, 12: 0xA2, 13: 0xA3, 17: 0xA4, 18: 0xA5}                       # V of ㅗㅛㅜㅠㅡ -> cell
VERT = {0: 0x99, 1: 0x9A, 2: 0x9B, 3: 0x9C, 4: 0x9D, 5: 0x9E, 6: 0x9F, 7: 0xA0, 20: 0xA6}
COMPOUND = {9: (0xA1, 0x99), 10: (0xA1, 0x9A), 11: (0xA1, 0xA6), 14: (0xA3, 0x9D), 15: (0xA3, 0x9E), 16: (0xA3, 0xA6),
            19: (0xA5, 0xA6)}
EXT = {0x99: 0x0C, 0x9B: 0x0C, 0xA6: 0x0C, 0x9D: 0x0D, 0x9F: 0x0D, 0x9A: 0x0E, 0x9C: 0x0E, 0x9E: 0x0E, 0xA0: 0x0E}
# T 1..27 as consonant cells (initial numbering: ㄱ0 ㄲ1 ㄴ2 ㄷ3 ㄹ5 ㅁ6 ㅂ7 ㅅ9 ㅆ10 ㅇ11 ㅈ12 ㅊ14 ㅋ15 ㅌ16 ㅍ17 ㅎ18)
FINALS = [(), (0,), (1,), (0, 9), (2,), (2, 12), (2, 18), (3,), (5,), (5, 0), (5, 6), (5, 7), (5, 9), (5, 16), (5, 17),
          (5, 18), (6,), (7,), (7, 9), (9,), (10,), (11,), (12,), (14,), (15,), (16,), (17,), (18,)]
BLANK = 0xFC


def merged(L, h):
    m = 5 * L + h
    return 0xA7 + m if m < 85 else 0x02 + (m - 85)


def layout(cp):
    """The two rows of cell codes (one or two columns) the Hangul ROM prints for syllable @p cp."""
    if not 0xAC00 <= cp <= 0xD7A3:
        raise MsxError(f"U+{cp:04X} is not a Hangul syllable")
    s = cp - 0xAC00
    L, V, T = s // 588, s % 588 // 28, s % 28
    fin = [0x86 + c for c in FINALS[T]]
    t1 = fin[0] if fin else BLANK
    t2 = fin[1] if len(fin) > 1 else BLANK
    ini = 0x86 + L
    if V in VERT:
        v = VERT[V]
        return [[ini, v], [t1, t2]] if fin else [[ini, v], [BLANK, EXT[v]]]
    if V in HORIZ:
        h = HORIZ[V]
        if not fin:
            return [[ini], [h]]
        m = merged(L, h - 0xA1)
        return [[m], [t1]] if len(fin) == 1 else [[m, BLANK], [t1, t2]]
    h, v = COMPOUND[V]
    return [[merged(L, h - 0xA1), v], [t1, t2]] if fin else [[ini, v], [h, EXT[v]]]


def cells(data, offset):
    if offset < 0 or offset + 2048 > len(data):
        raise MsxError(f"no 256 x 8-byte table at {offset:#x} ({len(data)} bytes)")
    return [data[offset + k * 8:offset + k * 8 + 8] for k in range(256)]


def syllable_rows(table, cp):
    """16 rows of 0/1 lists, 8 or 16 wide."""
    rows = []
    for row in layout(cp):
        for y in range(8):
            rows.append([table[c][y] >> (7 - x) & 1 for c in row for x in range(8)])
    return rows


def cmd_msx1(a):
    if not 0 <= a.ascii_top <= 8:
        raise MsxError("--ascii-top is 0..8")
    if not 0 <= a.ascent <= 16:
        raise MsxError("--ascent is 0..16")
    table = cells(rawcarve.read_range(a.file, a.offset, 2048), 0)
    glyphs, advance = {}, {}
    for cp in range(0xAC00, 0xD7A4):
        glyphs[cp] = syllable_rows(table, cp)
    for cp in range(0x20, 0x7F):
        rows = [[0] * 8 for _ in range(16)]
        for y in range(8):
            rows[a.ascii_top + y] = [table[cp][y] >> (7 - x) & 1 for x in range(8)]
        glyphs[cp] = rows
    narrow = sum(1 for cp in range(0xAC00, 0xD7A4) if len(glyphs[cp][0]) == 8)
    with open(a.output, "w", encoding="ascii") as fh:
        fh.write(rawcarve.bdf_text(glyphs, 16, 16, a.ascent, a.name, advance))
    print(f"wrote {a.output}: 11172 syllables ({narrow} 8x16, {11172 - narrow} 16x16) + 95 ASCII (8x8 at row "
          f"{a.ascii_top}), ascent {a.ascent}")


PER, COLS = 77, 7
CURSOR = 0xFF                  # the cell BASIC redefines as the cursor


def harvest(prefix):
    """{code point: rows of cell codes} read from a harvest's name tables (the slot's trailing blank columns cut)."""
    try:
        idx = [int(x, 16) for x in read_capped(prefix + ".index", MAX_HARVEST).decode("ascii").split()]
    except (UnicodeDecodeError, ValueError):
        raise MsxError(f"{prefix}.index: expected one hex code point a line")
    if not idx:
        raise MsxError(f"{prefix}.index: no syllable")
    for cp in idx:
        if not 0xAC00 <= cp <= 0xD7A3:
            raise MsxError(f"{prefix}.index: U+{cp:04X} is not a Hangul syllable")
    nt = read_capped(prefix + ".names", MAX_HARVEST)
    if len(nt) < (len(idx) + PER - 1) // PER * 768:
        raise MsxError(f"{prefix}.names: {len(nt)} bytes, short of {len(idx)} syllables")
    out = {}
    for i, cp in enumerate(idx):
        b, k = divmod(i, PER)
        blk = nt[b * 768:(b + 1) * 768]
        cx, cy = (k % COLS) * 4 + 2, (k // COLS) * 2
        rows = [[blk[(cy + j) * 32 + cx + c] for c in range(4)] for j in range(2)]
        w = max((c + 1 for r in rows for c, v in enumerate(r) if v != 0x20), default=0)
        out[cp] = [r[:w] for r in rows]
    return out


def cmd_msx1_verify(a):
    got = harvest(a.prefix)
    bad = [cp for cp, rows in got.items() if rows != layout(cp)]
    print(f"layout rule vs the machine: {len(got) - len(bad)} of {len(got)} syllables identical")
    cell_diff = []
    if a.bios:
        pat = read_capped(a.prefix + ".patterns", MAX_HARVEST)
        if len(pat) != 2048:
            raise MsxError(f"{a.prefix}.patterns: {len(pat)} bytes, not the 2,048-byte pattern table")
        table = cells(rawcarve.read_range(a.bios, a.offset, 2048), 0)
        diff = [k for k in range(256) if pat[k * 8:k * 8 + 8] != table[k]]
        print(f"VRAM pattern table vs the BIOS table: {256 - len(diff)} of 256 cells identical"
              + (f" (differ: {', '.join(f'{k:#04x}' for k in diff)})" if diff else ""))
        cell_diff = [k for k in diff if k != CURSOR]
    if bad:
        raise MsxError(f"{len(bad)} syllables differ, first U+{bad[0]:04X}: machine {got[bad[0]]}, rule {layout(bad[0])}")
    if cell_diff:
        raise MsxError(f"{len(cell_diff)} cells other than the cursor ({CURSOR:#04x}) differ from the BIOS table")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("kfn-map")
    p.add_argument("file")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_kfn_map)
    p = sub.add_parser("msx1")
    p.add_argument("file")
    p.add_argument("--offset", type=binscan.nonneg, default=0x1B49)
    p.add_argument("--ascii-top", type=int, default=8)
    p.add_argument("--ascent", type=int, default=16)
    p.add_argument("--name", default="msx1")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_msx1)
    p = sub.add_parser("msx1-verify")
    p.add_argument("prefix")
    p.add_argument("--bios")
    p.add_argument("--offset", type=binscan.nonneg, default=0x1B49)
    p.set_defaults(fn=cmd_msx1_verify)
    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (MsxError, OSError, ValueError) as e:
        print(f"msxfont.py: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
