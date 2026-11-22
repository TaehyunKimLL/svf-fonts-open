#!/usr/bin/env python3
"""Cut a bitmap font out of a file (a DOS driver, a .COM/.EXE, a ROM dump) into a file the other tools read.

`binscan.py` finds where a font is; this tool cuts it out. Nothing here runs the file's code: it reads bytes. Run it
with `python3 -I` on untrusted downloads.

  rawcarve.py cut FILE --offset O --length N -o OUT
      the bytes as they are: a raw 8x4x4 font (11,520 bytes) for `jamoset.py --layout 844`, an 8x16 English font
      (2,048 / 4,096 bytes) for `--eng`, any raw layout the repository reads by its size.
  rawcarve.py eng FILE --offset O [--height 16] [--top 0] -o OUT
      an 8xH English font (H = 8..16) as the 4,096-byte 8x16 file `--eng` reads; rows are padded to 16 (--top rows
      above the glyph), glyphs past the file's end are blank.
  rawcarve.py bdf FILE --offset O --glyph WxH --chars ascii|ks-hangul|ks-nonhanja|ks-all [--dense | --grid L0,T0,PITCH]
                  -o OUT.bdf
      glyphs at an offset as a Unicode BDF (CHARSET_REGISTRY "ISO10646"), for `bdfface.py --hangul / --ascii` and
      `mkfont.py`. ascii: glyph i is code `--first` + i (default 0). ks-*: the KS X 1001 code of each glyph is found by
      `--dense` (glyph i is the i-th code of the set in KS order, the 2,350-syllable dumps) or `--grid L0,T0,PITCH`
      (glyph index = (lead - L0) * PITCH + (trail - T0): 0xA1,0xA1,94 for a full 94 x 94 table, 0x80,0x80,128 for
      the Korean VGA font ROMs that 86Box reads). Blank glyphs are left out.
  rawcarve.py compose FILE --spec SPEC.json [--syllables ks|all] [--eng FILE2 --eng-offset O] -o OUT.bdf
      a jamo-piece font with its own set rules (read from the driver's code) composed into syllables, as a Unicode BDF:
      the KS X 1001 2,350 (ks, the default) or all 11,172 (all). See "Compose spec" below.

Glyph geometry is binscan.py's (`--glyph WxH`, `--stride`, `--order rows|strips|cols|bytecols`, `--lsb`). The BDF's
ascent is `--ascent` (default: 7/8 of the height, rounded up: 14 for 16 px).

Compose spec (JSON). Jamo are numbered as Unicode numbers them: L 0..18 (ㄱ..ㅎ), V 0..20 (ㅏ..ㅣ), T 1..27 (ㄱ..ㅎ).

  {"cell": [16, 16],
   "vowel_order": [21 ints],      optional: for each Unicode V, the font's own vowel number (the tables below are
                                  indexed by that number); default: the Unicode order
   "sets": {"NAME": {"offset": O, "stride": B, "x": 0, "y": 0, "width": 16, "height": 16, "order": "rows"}, ...},
                                  where the pieces of a set are: piece k at offset + k * stride, drawn width x height at
                                  (x, y) of the cell (a set stored row-cropped or as a half cell is placed back here)
   "initial": {"nofinal": [NAME by font vowel], "final": [NAME by font vowel], "novowel": NAME},   piece = L
   "medial":  {"nofinal": [[NAME, k] by font vowel], "final": [[NAME, k] by font vowel],
               "nofinal_kk": ..., "final_kk": ...},  optional *_kk tables: used when L is ㄱ or ㅋ (the 8x4x4 rule)
   "final":   {"by_vowel": [NAME by font vowel]} or {"set": NAME},   piece = T - 1
  }
A syllable is the OR of its pieces, as the drivers draw it.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:  # python -I drops the script's directory
    sys.path.insert(0, HERE)
import binscan  # noqa: E402


class CarveError(Exception):
    pass


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def ks_codes(which):
    """(lead, trail, code point) of the KS X 1001 codes of a set, in KS order."""
    out = []
    for lead in range(0xA1, 0xFF):
        if which == "ks-hangul" and not 0xB0 <= lead <= 0xC8:
            continue
        if which == "ks-nonhanja" and lead >= 0xCA:
            continue
        for trail in range(0xA1, 0xFF):
            try:
                ch = bytes((lead, trail)).decode("euc_kr")
            except UnicodeDecodeError:
                continue
            out.append((lead, trail, ord(ch)))
    return out


def bdf_text(glyphs, w, h, ascent, name, advance=None):
    """A Unicode BDF of {cp: rows (lists of 0/1)}; every glyph w x h, its top at the cell top."""
    descent = h - ascent
    lines = ["STARTFONT 2.1", f"FONT -rawcarve-{name}-medium-r-normal--{h}-{h * 10}-75-75-c-{w * 10}-iso10646-1",
             f"SIZE {h} 75 75", f"FONTBOUNDINGBOX {w} {h} 0 {-descent}", "STARTPROPERTIES 11",
             f'FAMILY_NAME "{name}"', 'WEIGHT_NAME "Medium"', 'SLANT "R"', f"PIXEL_SIZE {h}", f"POINT_SIZE {h * 10}",
             "RESOLUTION_X 75", "RESOLUTION_Y 75", f"FONT_ASCENT {ascent}", f"FONT_DESCENT {descent}",
             'CHARSET_REGISTRY "ISO10646"', 'CHARSET_ENCODING "1"', "ENDPROPERTIES", f"CHARS {len(glyphs)}"]
    for cp in sorted(glyphs):
        rows = glyphs[cp]
        gw = len(rows[0]) if rows else w
        adv = advance.get(cp, gw) if advance else gw
        lines += [f"STARTCHAR U+{cp:04X}", f"ENCODING {cp}", f"SWIDTH {adv * 1000 // h} 0", f"DWIDTH {adv} 0",
                  f"BBX {gw} {h} 0 {-descent}", "BITMAP"]
        gnb = (gw + 7) // 8
        for r in rows:
            v = 0
            for x, bit in enumerate(r):
                v |= bit << (gnb * 8 - 1 - x)
            lines.append(f"{v:0{gnb * 2}X}")
        lines.append("ENDCHAR")
    lines.append("ENDFONT")
    return "\n".join(lines) + "\n"


def default_ascent(h):
    return (h * 7 + 7) // 8


def cmd_cut(a):
    if a.offset < 0 or a.length < 1:
        raise CarveError("--offset must be 0 or more and --length 1 or more")
    size = os.path.getsize(a.file)
    if a.offset + a.length > size:
        raise CarveError(f"{a.offset:#x} + {a.length} is past the end of the file ({size} bytes)")
    with open(a.file, "rb") as fh:
        fh.seek(a.offset)
        part = fh.read(a.length)
    with open(a.output, "wb") as fh:
        fh.write(part)
    print(f"wrote {a.output}: {a.length} bytes from {a.offset:#x}")


def cmd_eng(a):
    h = a.height
    if a.offset < 0:
        raise CarveError("--offset must be 0 or more")
    if not 1 <= h <= 16 or a.top < 0 or a.top + h > 16:
        raise CarveError("--height (1..16) and --top (0 or more) must fit 16 rows")
    d = read(a.file)
    out = bytearray(4096)
    n = 0
    for c in range(256):
        src = a.offset + c * h
        if src + h > len(d):
            break
        out[c * 16 + a.top:c * 16 + a.top + h] = d[src:src + h]
        n += 1
    with open(a.output, "wb") as fh:
        fh.write(out)
    print(f"wrote {a.output}: 4096 bytes, {n} glyphs of 8x{h} from {a.offset:#x} (rows {a.top}..{a.top + h - 1})")


def cmd_bdf(a):
    if a.offset < 0:
        raise CarveError("--offset must be 0 or more")
    if a.grid and (len(a.grid) != 3 or a.grid[2] < 1):
        raise CarveError("--grid is L0,T0,PITCH with PITCH 1 or more")
    d = read(a.file)
    w, h = a.glyph
    gb = a.stride or binscan.glyph_bytes(w, h, a.order)
    glyphs = {}
    if a.chars == "ascii":
        for i in range(a.count or 256):
            cp = a.first + i
            off = a.offset + i * gb
            if off + gb > len(d) or cp > 0x7E:
                break
            if cp < 0x20:
                continue
            rows = binscan.decode(d, off, w, h, a.order, a.lsb)
            glyphs[cp] = rows
    else:
        codes = ks_codes(a.chars)
        if not a.dense and not a.grid:
            raise CarveError("ks-* needs --dense or --grid L0,T0,PITCH")
        for i, (lead, trail, cp) in enumerate(codes):
            if a.dense:
                idx = i
            else:
                l0, t0, pitch = a.grid
                if trail - t0 >= pitch:
                    raise CarveError(f"--grid {l0:#x},{t0:#x},{pitch}: trail {trail:#x} falls past a row of {pitch}")
                idx = (lead - l0) * pitch + (trail - t0)
                if idx < 0:
                    raise CarveError(f"--grid {l0:#x},{t0:#x},{pitch}: code {lead:02X}{trail:02X} comes before the grid")
            off = a.offset + idx * gb
            if off + gb > len(d):
                continue
            rows = binscan.decode(d, off, w, h, a.order, a.lsb)
            if any(map(any, rows)):
                glyphs[cp] = rows
    if not glyphs:
        raise CarveError("no inked glyph at these offsets")
    ascent = a.ascent if a.ascent is not None else default_ascent(h)
    with open(a.output, "w", encoding="ascii") as fh:
        fh.write(bdf_text(glyphs, w, h, ascent, a.name))
    hangul = sum(1 for cp in glyphs if 0xAC00 <= cp <= 0xD7A3)
    print(f"wrote {a.output}: {len(glyphs)} glyphs ({hangul} Hangul syllables) of {w}x{h}, ascent {ascent}")


class Composer:
    def __init__(self, data, spec):
        self.d, self.spec = data, spec
        self.w, self.h = spec.get("cell", [16, 16])
        self.vorder = spec.get("vowel_order") or list(range(21))
        if sorted(self.vorder) != list(range(21)):
            raise CarveError("vowel_order must be a permutation of 0..20")
        self.sets = spec["sets"]
        for name, s in self.sets.items():
            for k in ("offset", "stride"):
                if k not in s:
                    raise CarveError(f"set {name}: no {k}")
            if s["offset"] < 0 or s["stride"] < 1:
                raise CarveError(f"set {name}: offset must be 0 or more and stride 1 or more")
            if not (1 <= s.get("width", self.w) <= 256 and 1 <= s.get("height", self.h) <= 256):
                raise CarveError(f"set {name}: width and height are 1..256")
        self._cache = {}

    def piece(self, name, k):
        key = (name, k)
        if key not in self._cache:
            s = self.sets[name]
            w, h = s.get("width", self.w), s.get("height", self.h)
            self._cache[key] = (s.get("x", 0), s.get("y", 0),
                                binscan.decode(self.d, s["offset"] + k * s["stride"], w, h, s.get("order", "rows"),
                                               s.get("lsb", False)))
        return self._cache[key]

    def syllable(self, L, V, T):
        cell = [[0] * self.w for _ in range(self.h)]
        fv = self.vorder[V]
        ini, med, fin = self.spec["initial"], self.spec["medial"], self.spec["final"]
        has = "final" if T else "nofinal"
        parts = [(ini[has][fv], L)]
        mtab = med.get(has + "_kk") if L in (0, 15) and med.get(has + "_kk") else med[has]
        parts.append(tuple(mtab[fv]))
        if T:
            parts.append((fin["by_vowel"][fv] if "by_vowel" in fin else fin["set"], T - 1))
        for name, k in parts:
            x0, y0, rows = self.piece(name, k)
            for y, r in enumerate(rows):
                for x, v in enumerate(r):
                    if v and 0 <= y0 + y < self.h and 0 <= x0 + x < self.w:
                        cell[y0 + y][x0 + x] = 1
        return cell


def cmd_compose(a):
    if a.eng_offset < 0 or not 1 <= a.eng_height <= 64 or a.eng_top < 0:
        raise CarveError("--eng-offset and --eng-top must be 0 or more, --eng-height 1..64")
    d = read(a.file)
    with open(a.spec, encoding="utf-8") as fh:
        spec = json.load(fh)
    c = Composer(d, spec)
    if a.syllables == "ks":
        cps = [cp for _, _, cp in ks_codes("ks-hangul")]
    else:
        cps = list(range(0xAC00, 0xD7A4))
    glyphs = {}
    for cp in cps:
        s = cp - 0xAC00
        glyphs[cp] = c.syllable(s // 588, (s // 28) % 21, s % 28)
    advance = {}
    if a.eng:
        e = read(a.eng)
        eh = a.eng_height
        for cp in range(0x20, 0x7F):
            off = a.eng_offset + cp * eh
            rows = binscan.decode(e, off, 8, eh, "rows")
            pad = c.h - eh
            rows = [[0] * 8 for _ in range(a.eng_top)] + rows + [[0] * 8 for _ in range(max(0, pad - a.eng_top))]
            glyphs[cp] = rows[:c.h]
            advance[cp] = 8
    ascent = a.ascent if a.ascent is not None else default_ascent(c.h)
    with open(a.output, "w", encoding="ascii") as fh:
        fh.write(bdf_text(glyphs, c.w, c.h, ascent, a.name, advance))
    print(f"wrote {a.output}: {len(cps)} syllables{' + ASCII' if a.eng else ''} of {c.w}x{c.h}, ascent {ascent}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = binscan.parse_int

    p = sub.add_parser("cut")
    p.add_argument("file")
    p.add_argument("--offset", type=pi, required=True)
    p.add_argument("--length", type=pi, required=True)
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_cut)

    p = sub.add_parser("eng")
    p.add_argument("file")
    p.add_argument("--offset", type=pi, required=True)
    p.add_argument("--height", type=int, default=16)
    p.add_argument("--top", type=int, default=0)
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_eng)

    p = sub.add_parser("bdf")
    p.add_argument("file")
    p.add_argument("--offset", type=pi, default=0)
    p.add_argument("--glyph", type=binscan.parse_glyph, required=True, metavar="WxH")
    p.add_argument("--stride", type=pi, default=None)
    p.add_argument("--order", choices=("rows", "strips", "cols", "bytecols"), default="rows")
    p.add_argument("--lsb", action="store_true")
    p.add_argument("--chars", choices=("ascii", "ks-hangul", "ks-nonhanja", "ks-all"), required=True)
    p.add_argument("--first", type=pi, default=0, help="ascii: the code of the glyph at the offset (0)")
    p.add_argument("--count", type=int, default=None, help="ascii: glyphs to read (256)")
    p.add_argument("--dense", action="store_true")
    p.add_argument("--grid", type=lambda s: tuple(int(x, 0) for x in s.split(",")), default=None,
                   metavar="L0,T0,PITCH")
    p.add_argument("--ascent", type=int, default=None)
    p.add_argument("--name", default="carved")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_bdf)

    p = sub.add_parser("compose")
    p.add_argument("file")
    p.add_argument("--spec", required=True)
    p.add_argument("--syllables", choices=("ks", "all"), default="ks")
    p.add_argument("--eng", default=None, help="a file holding an 8xH English font (often the same file)")
    p.add_argument("--eng-offset", type=pi, default=0)
    p.add_argument("--eng-height", type=int, default=16)
    p.add_argument("--eng-top", type=int, default=0)
    p.add_argument("--ascent", type=int, default=None)
    p.add_argument("--name", default="composed")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_compose)

    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (CarveError, KeyError, IndexError, ValueError) as e:
        print(f"rawcarve.py: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
