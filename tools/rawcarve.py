#!/usr/bin/env python3
"""Cut a bitmap font out of a file (a DOS driver, a .COM/.EXE, a ROM dump) into a file the other tools read.

`binscan.py` finds where a font is; this tool cuts it out. Nothing here runs the file's code: it reads bytes. Run it
with `python3 -I` on untrusted downloads.

  rawcarve.py cut FILE --offset O --length N -o OUT
      the bytes as they are: a raw 8x4x4 font (11,520 bytes) for `jamoset.py --layout 844`, an 8x16 English font
      (2,048 / 4,096 bytes) for `--eng`, any raw layout the repository reads by its size.
  rawcarve.py eng FILE --offset O [--height 16] [--top 0] [--first C] [--count N] [--width 8|16] [--invert] -o OUT
      an 8xH English font (H = 8..16) as the 4,096-byte 8x16 file `--eng` reads; rows are padded to 16 (--top rows
      above the glyph), glyphs past the file's end are blank. --first: the code of the glyph at the offset (0),
      --count: how many glyphs (default: through code 255; the other codes stay blank);
      --width 16: 16-wide glyphs (2 bytes a row) as the 8,192-byte 16x16 file `jamoset.py --eng` reads.
  rawcarve.py region FILE[,FILE...] [FILE[,FILE...] ...] [--unit 1|2|4] [--swap] -o OUT
      a ROM region as a MAME driver loads it: the files of a group interleaved --unit bytes at a time (1:
      ROM_LOAD16_BYTE / ROM_LOAD32_BYTE, 2: ROM_LOAD32_WORD / ROM_LOAD64_WORD), the groups one after the other
      (a single file is a group of one); --swap swaps the bytes of each 16-bit word (ROM_LOAD16_WORD_SWAP).
  rawcarve.py ink FILE (--glyph WxH [--order ...] | --gfx LAYOUT [--bg PEN]) [--invert] [--offset O] [--count N] -o OUT
      glyphs (1 bpp in any order, inverted, or multi-bit tiles reduced by the pen rule) as plain 1 bpp row-major glyphs
      one after another (ceil(W/8) x H bytes each), for binscan.py sets / runs, rawcarve.py bdf / eng / cut and
      jamoset.py --layout 844.
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

Glyph geometry is binscan.py's (`--glyph WxH`, `--stride`, `--order rows|strips|cols|bytecols`, `--lsb`, `--invert`,
`--gfx LAYOUT`, `--bg PEN`). The BDF's ascent is `--ascent` (default: 7/8 of the height, rounded up: 14 for 16 px).

Compose spec (JSON). Jamo are numbered as Unicode numbers them: L 0..18 (ㄱ..ㅎ), V 0..20 (ㅏ..ㅣ), T 1..27 (ㄱ..ㅎ).

  {"cell": [16, 16],
   "invert": false,               optional: every set's ink is its 0 bits (also `compose --invert`, which inverts --eng);
                                  a set's own "invert" wins over both
   "vowel_order": [21 ints],      optional: for each Unicode V, the font's own vowel number (the tables below are
                                  indexed by that number); default: the Unicode order
   "sets": {"NAME": {"offset": O, "stride": B, "x": 0, "y": 0, "width": 16, "height": 16, "order": "rows"}, ...},
                                  where the pieces of a set are: piece k at offset + k * stride, drawn width x height at
                                  (x, y) of the cell (a set stored row-cropped or as a half cell is placed back here);
                                  a set may also give "lsb", "invert", or "gfx" (a binscan.py --gfx layout, its tile
                                  size the set's) and "bg" / "fg" (a pen list)
   "initial": {"nofinal": [NAME by font vowel], "final": [NAME by font vowel], "novowel": NAME},   piece = L
   "medial":  {"nofinal": [[NAME, k] by font vowel], "final": [[NAME, k] by font vowel],
               "nofinal_kk": ..., "final_kk": ...},  optional *_kk tables: used when L is ㄱ or ㅋ (the 8x4x4 rule)
   "final":   {"by_vowel": [NAME by font vowel]} or {"set": NAME},   piece = T - 1
  }
A syllable is the OR of its pieces, as the drivers draw it. `--spec spc1500` (the name always means it; a file of that
name is ./spc1500) is the built-in spec of the Samsung
SPC-1500 Hangul ROMs (spc1500_spec), for the 32 KB region `rawcarve.py region ss150fnt.bin ss151fnt.bin ss152fnt.bin
ss153fnt.bin` writes. `jamoset.py --layout spec --spec SPEC` turns the same spec into an exact jamo set.
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


MAX_FILE = 64 << 20  # compose reads the whole file (piece sets may sit anywhere); larger files are refused


def read(path):
    if os.path.getsize(path) > MAX_FILE:
        raise CarveError(f"{path}: larger than {MAX_FILE} bytes")
    with open(path, "rb") as fh:
        return fh.read()


def read_range(path, start, length):
    """The bytes [start, start + length) of the file, as far as it has them: no more is read."""
    with open(path, "rb") as fh:
        fh.seek(start)
        return fh.read(max(0, length))


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
    if not 0 <= a.first <= 255:
        raise CarveError("--first is a code 0..255")
    rb = a.width // 8  # bytes a row: 1 (8 wide) or 2 (16 wide)
    gb = rb * h
    last = 256 if a.count is None else min(256, a.first + a.count)
    d = read_range(a.file, a.offset, (last - a.first) * gb)
    if a.invert:
        d = bytes(b ^ 0xFF for b in d)
    out = bytearray(256 * 16 * rb)
    n = 0
    for c in range(a.first, last):
        src = (c - a.first) * gb
        if src + gb > len(d):
            break
        out[(c * 16 + a.top) * rb:(c * 16 + a.top + h) * rb] = d[src:src + gb]
        n += 1
    with open(a.output, "wb") as fh:
        fh.write(out)
    print(f"wrote {a.output}: {len(out)} bytes, {n} glyphs of {a.width}x{h} from {a.offset:#x} (codes {a.first:#x}.., "
          f"rows {a.top}..{a.top + h - 1}{', inverted' if a.invert else ''})")


def cmd_bdf(a):
    if a.grid and (len(a.grid) != 3 or a.grid[2] < 1):
        raise CarveError("--grid is L0,T0,PITCH with PITCH 1 or more")
    w, h = a.glyph
    foot = binscan.footprint(w, h, a.order, a.gfx)  # the bytes one glyph spans, whatever the stride
    gb = a.stride or binscan.glyph_bytes(w, h, a.order, a.gfx)
    glyphs = {}
    if a.chars == "ascii":
        n = a.count or 256
        d = read_range(a.file, a.offset, (n - 1) * gb + foot)  # through the last glyph, even with a short stride
        for i in range(n):
            cp = a.first + i
            if i * gb + foot > len(d) or cp > 0x7E:
                break
            if cp < 0x20:
                continue
            glyphs[cp] = binscan.decode(d, i * gb, w, h, a.order, a.lsb, a.invert, a.gfx)
    else:
        if not a.dense and not a.grid:
            raise CarveError("ks-* needs --dense or --grid L0,T0,PITCH")
        places = []
        for i, (lead, trail, cp) in enumerate(ks_codes(a.chars)):
            if a.dense:
                idx = i
            else:
                l0, t0, pitch = a.grid
                if lead < l0 or not t0 <= trail < t0 + pitch:
                    raise CarveError(f"--grid {l0:#x},{t0:#x},{pitch}: code {lead:02X}{trail:02X} is outside the grid "
                                     f"(lead below {l0:#x}, or trail outside {t0:#x}..{t0 + pitch - 1:#x})")
                idx = (lead - l0) * pitch + (trail - t0)
            places.append((idx, cp))
        d = read_range(a.file, a.offset, max(i for i, _ in places) * gb + foot)
        for idx, cp in places:
            if idx * gb + foot > len(d):
                continue
            rows = binscan.decode(d, idx * gb, w, h, a.order, a.lsb, a.invert, a.gfx)
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
    def __init__(self, data, spec, invert=False):
        self.d, self.spec = data, spec
        self.invert = bool(spec.get("invert", False)) or invert
        self.w, self.h = spec.get("cell", [16, 16])
        if not (1 <= self.w <= 256 and 1 <= self.h <= 256):
            raise CarveError(f"cell {self.w}x{self.h}: width and height are 1..256")
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
        self._gfx = {}
        for name, s in self.sets.items():
            if s.get("gfx") is not None:
                try:
                    g = binscan.parse_gfx(s["gfx"], len(data), s.get("bg", 0), s.get("fg"))
                except binscan.GfxError as e:
                    raise CarveError(f"set {name}: gfx: {e}")
                if (s.get("width", g.w), s.get("height", g.h)) != (g.w, g.h):
                    raise CarveError(f"set {name}: width x height is not the gfx tile's {g.w}x{g.h}")
                self._gfx[name] = g
        self._cache = {}

    def piece(self, name, k):
        if not isinstance(k, int) or k < 0:
            raise CarveError(f"set {name}: piece number {k!r} (must be 0 or more)")
        if name not in self.sets:
            raise CarveError(f"no set named {name!r}")
        key = (name, k)
        if key not in self._cache:
            s = self.sets[name]
            g = self._gfx.get(name)
            w, h = (g.w, g.h) if g else (s.get("width", self.w), s.get("height", self.h))
            self._cache[key] = (s.get("x", 0), s.get("y", 0),
                                binscan.decode(self.d, s["offset"] + k * s["stride"], w, h, s.get("order", "rows"),
                                               s.get("lsb", False), bool(s.get("invert", self.invert)), g))
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


# Samsung SPC-1500 (MAME spc1500.cpp, crtc_update_row): the Hangul ROMs ss151 / ss152 / ss153 hold 16x16 pieces in
# 8-pixel strips (left byte n, right byte n + 16), ink as 0 bits, sets of 32 slots (1 KB). A syllable's Samsung code
# gives h1 (initial, 1 = ㄱ), h2 (the Johab vowel code, 3 = ㅏ) and h3 (final, 0 = none, 1 = ㄱ); the driver ANDs
#   initial: 0x2000 + h1 * 32 + (cho[h2] + (h3 != 0) - 1) * 0x400
#   medial:  0x4000 + h2 * 32 + (h3 != 0) * 0x400
#   final:   0x6000 + h3 * 32 + (jong[h2] - 1) * 0x400
# with these two tables (by the Johab vowel code), so the initial sets used are 0-5 of 8, the medial 2, the final 2.
SPC1500_CHO = (1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 3, 5, 5, 0, 0, 5, 3, 3, 5, 5, 5, 0, 0, 3, 3, 5, 1)
SPC1500_JONG = (0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 2, 2, 2, 0, 0, 2, 2, 2, 2, 2, 2, 0, 0, 2, 2, 1, 1)
JUNG_FIELD = (3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 22, 23, 26, 27, 28, 29)  # Johab code of ㅏ..ㅣ


def spc1500_spec():
    """The compose spec of the SPC-1500 Hangul ROMs, for the 32 KB region MAME loads as "font1" (ss150fnt.bin,
    ss151fnt.bin, ss152fnt.bin, ss153fnt.bin one after another; `rawcarve.py region` writes it)."""
    sets = {}
    for k in range(6):
        sets[f"I{k}"] = {"offset": 0x2000 + k * 0x400 + 32, "stride": 32, "order": "strips"}
    for k in range(2):
        sets[f"M{k}"] = {"offset": 0x4000 + k * 0x400, "stride": 32, "order": "strips"}
        sets[f"F{k}"] = {"offset": 0x6000 + k * 0x400 + 32, "stride": 32, "order": "strips"}
    cho = [SPC1500_CHO[JUNG_FIELD[v]] for v in range(21)]
    return {"cell": [16, 16], "invert": True, "sets": sets,
            "initial": {"nofinal": [f"I{c - 1}" for c in cho], "final": [f"I{c}" for c in cho], "novowel": "I0"},
            "medial": {"nofinal": [["M0", JUNG_FIELD[v]] for v in range(21)],
                       "final": [["M1", JUNG_FIELD[v]] for v in range(21)]},
            "final": {"by_vowel": [f"F{SPC1500_JONG[JUNG_FIELD[v]] - 1}" for v in range(21)]}}


BUILTIN_SPECS = {"spc1500": spc1500_spec}


def load_spec(path):
    """A built-in compose spec by name (spc1500: the name always means the built-in; a JSON file of that name is
    read as ./spc1500), or a spec from a JSON file."""
    if path in BUILTIN_SPECS:
        return BUILTIN_SPECS[path]()
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def pack_rows(rows, w):
    """h rows of w 0/1 ints as row-major bytes, ceil(w / 8) a row, MSB = the left pixel."""
    nb = (w + 7) // 8
    out = bytearray()
    for r in rows:
        v = 0
        for x, bit in enumerate(r):
            v |= bit << (nb * 8 - 1 - x)
        out += v.to_bytes(nb, "big")
    return bytes(out)


def cmd_ink(a):
    w, h = a.glyph
    gb = a.stride or binscan.glyph_bytes(w, h, a.order, a.gfx)
    foot = binscan.footprint(w, h, a.order, a.gfx)
    d = read(a.file)
    if a.offset >= len(d):
        raise CarveError(f"--offset {a.offset:#x} is past the end of the file ({len(d)} bytes)")
    fit = max(0, (len(d) - a.offset - foot) // gb + 1) if len(d) - a.offset >= foot else 0
    count = a.count if a.count is not None else fit
    if count < 1:
        raise CarveError("no whole glyph at this offset")
    if count > fit:
        raise CarveError(f"--count {count}: only {fit} whole glyphs fit from {a.offset:#x}")
    out = bytearray()
    inked = 0
    for i in range(count):
        rows = binscan.decode(d, a.offset + i * gb, w, h, a.order, a.lsb, a.invert, a.gfx)
        inked += any(map(any, rows))
        out += pack_rows(rows, w)
    with open(a.output, "wb") as fh:
        fh.write(out)
    print(f"wrote {a.output}: {count} glyphs of {w}x{h} as 1 bpp rows ({(w + 7) // 8 * h} B each, {len(out)} bytes), "
          f"{inked} inked, from {a.offset:#x} stride {gb}")


MAX_REGION = 64 << 20


def cmd_region(a):
    groups = [[f for f in group.split(",") if f] for group in a.groups]
    if any(not g for g in groups):
        raise CarveError("an empty group: give FILE or FILE,FILE,...")
    total = sum(os.path.getsize(f) for g in groups for f in g)
    if total > MAX_REGION:
        raise CarveError(f"the region would be {total} bytes, more than {MAX_REGION}")
    out = bytearray()
    for group, files in zip(a.groups, groups):
        datas = [read(f) for f in files]
        n = len(datas[0])
        if any(len(x) != n for x in datas):
            raise CarveError(f"{group}: the files of a group must have the same size ({[len(x) for x in datas]})")
        if n % a.unit:
            raise CarveError(f"{group}: {n} bytes is not a whole number of {a.unit}-byte units")
        if len(out) + n * len(datas) > MAX_REGION:
            raise CarveError(f"the region would be larger than {MAX_REGION} bytes")
        if len(datas) == 1:
            out += datas[0]
            continue
        part = bytearray(n * len(datas))
        step = a.unit * len(datas)
        for k, x in enumerate(datas):
            for b in range(a.unit):
                part[k * a.unit + b::step] = x[b::a.unit]
        out += part
    if a.swap:
        if len(out) % 2:
            raise CarveError("--swap needs an even number of bytes")
        out[0::2], out[1::2] = out[1::2], out[0::2]
    with open(a.output, "wb") as fh:
        fh.write(out)
    print(f"wrote {a.output}: {len(out)} bytes from {len(a.groups)} group(s), interleaved by {a.unit} byte(s)"
          f"{', words swapped' if a.swap else ''}")


def cmd_compose(a):
    if a.eng_offset < 0 or not 1 <= a.eng_height <= 64 or a.eng_top < 0:
        raise CarveError("--eng-offset and --eng-top must be 0 or more, --eng-height 1..64")
    d = read(a.file)
    spec = load_spec(a.spec)
    c = Composer(d, spec, a.invert)
    if a.eng and a.eng_top + a.eng_height > c.h:
        raise CarveError(f"--eng-top {a.eng_top} + --eng-height {a.eng_height} is past the {c.h}-row cell")
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
        eh = a.eng_height
        e = read_range(a.eng, a.eng_offset, 0x7F * eh)
        for cp in range(0x20, 0x7F):
            off = cp * eh
            rows = binscan.decode(e, off, 8, eh, "rows", invert=c.invert)
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
    p.add_argument("--offset", type=binscan.nonneg, required=True)
    p.add_argument("--length", type=pi, required=True)
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_cut)

    p = sub.add_parser("eng")
    p.add_argument("file")
    p.add_argument("--offset", type=binscan.nonneg, required=True)
    p.add_argument("--height", type=int, default=16)
    p.add_argument("--top", type=int, default=0)
    p.add_argument("--width", type=int, choices=(8, 16), default=8,
                   help="glyph width: 8 (the 4,096-byte 8x16 file) or 16 (an 8,192-byte 16x16 file, 2 bytes a row)")
    p.add_argument("--first", type=binscan.nonneg, default=0, help="the code of the glyph at the offset (0)")
    p.add_argument("--count", type=binscan.positive, default=None, help="glyphs to read (default: to code 255)")
    p.add_argument("--invert", action="store_true", help="ink is the 0 bits")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_eng)

    def geometry(p):
        p.add_argument("--glyph", type=binscan.parse_glyph, default=None, metavar="WxH")
        p.add_argument("--stride", type=binscan.positive, default=None)
        p.add_argument("--order", choices=("rows", "strips", "cols", "bytecols"), default="rows")
        p.add_argument("--lsb", action="store_true")
        binscan.tile_args(p)

    p = sub.add_parser("bdf")
    p.add_argument("file")
    p.add_argument("--offset", type=binscan.nonneg, default=0)
    geometry(p)
    p.add_argument("--chars", choices=("ascii", "ks-hangul", "ks-nonhanja", "ks-all"), required=True)
    p.add_argument("--first", type=binscan.nonneg, default=0, help="ascii: the code of the glyph at the offset (0)")
    p.add_argument("--count", type=binscan.positive, default=None, help="ascii: glyphs to read (256)")
    p.add_argument("--dense", action="store_true")
    p.add_argument("--grid", type=lambda s: tuple(int(x, 0) for x in s.split(",")), default=None,
                   metavar="L0,T0,PITCH")
    p.add_argument("--ascent", type=int, default=None)
    p.add_argument("--name", default="carved")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_bdf)

    p = sub.add_parser("ink")
    p.add_argument("file")
    p.add_argument("--offset", type=binscan.nonneg, default=0)
    p.add_argument("--count", type=binscan.positive, default=None, help="glyphs to write (default: all that fit)")
    geometry(p)
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_ink)

    p = sub.add_parser("region")
    p.add_argument("groups", nargs="+", metavar="FILE[,FILE...]")
    p.add_argument("--unit", type=int, choices=(1, 2, 4), default=1,
                   help="bytes taken from each file of a group in turn (1: ROM_LOAD16_BYTE / ROM_LOAD32_BYTE, "
                   "2: ROM_LOAD32_WORD / ROM_LOAD64_WORD)")
    p.add_argument("--swap", action="store_true", help="swap the bytes of every 16-bit word (ROM_LOAD16_WORD_SWAP)")
    p.add_argument("-o", "--output", required=True)
    p.set_defaults(fn=cmd_region)

    p = sub.add_parser("compose")
    p.add_argument("file")
    p.add_argument("--spec", required=True, help="a JSON compose spec, or a built-in one: spc1500")
    p.add_argument("--invert", action="store_true",
                   help="ink is the 0 bits, in the --eng font and every set that does not say \"invert\": false")
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
    if a.cmd in ("bdf", "ink"):
        binscan.resolve_geometry(a, ap)
    try:
        a.fn(a)
    except (CarveError, binscan.GfxError, KeyError, IndexError, ValueError, TypeError, AttributeError, OSError) as e:
        print(f"rawcarve.py: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
