#!/usr/bin/env python3
"""vesa-lines.txt in Python: the same parser as c/ports/dos/vesa_lines.c (same table, same palette, same message at
the same line for every file; change the two together), and the oracle of the DOS example: the buffer c/ports/dos/
svfvesa.c should hold after drawing the file's lines, computed with tools/svfline.py.

  vesa_lines.py --print-table FILE [--dac 6|8]      the text c/tests/vesa-lines-dump prints
  vesa_lines.py --expect FILE --faces DIR W H BPP   sum=<FNV-1a of the expected back buffer, 8 hex digits>

The file format is described in c/ports/dos/vesa_lines.h and c/ports/dos/README.md.
"""

import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import svfline  # noqa: E402

MAX_COLOURS, MAX_LINES, MAX_FACES, LINE_BYTES, MAX_FILE = 16, 32, 4, 512, 65536

Colour = collections.namedtuple("Colour", "name rgb565 rgb555 rgb888 index_base index_levels")
Line = collections.namedtuple("Line", "faces num den colour x baseline text src_line")  # colour: an index into Table.colours;
# src_line: the file line of the record (Python only; the face errors of expected_buffer name it)
Table = collections.namedtuple("Table", "colours background lines")  # background: an index into colours


class VesaLinesError(Exception):
    """A refusal at the 1-based line line_no (the line after the last one for a refusal at the end of the file)."""

    def __init__(self, line_no, message):
        super().__init__("line %d: %s" % (line_no, message))
        self.line_no, self.message = line_no, message


_NUM = re.compile(r"-?(?:0[xX][0-9A-Fa-f]+|[0-9]+)\Z")
_UNS = re.compile(r"(?:0[xX][0-9A-Fa-f]+|[0-9]+)\Z")
_FACE = re.compile(r"(?!(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])\.SVF\Z)[A-Z0-9_]{1,8}\.SVF\Z")
_TRIM = " \t"


def _num(s, neg_ok=False):
    """The value of a decimal or 0x hex number (a leading '-' only when @p neg_ok), or None."""
    if not (_NUM if neg_ok else _UNS).match(s):
        return None
    return int(s, 16) if "x" in s.lower() else int(s, 10)


def _ranged(s, lo, hi, what, neg_ok=False):
    v = _num(s, neg_ok)
    if v is None:
        raise ValueError("bad number")
    if not lo <= v <= hi:
        raise ValueError("%s out of range" % what)
    return v


def _name_ok(s):
    return 1 <= len(s) <= 31 and all(0x20 < ord(c) < 0x7F for c in s)


def _colour_record(colours, fields, nf):
    if len(colours) == MAX_COLOURS:
        raise ValueError("more than 16 colours")
    if nf != 6:
        raise ValueError("a colour record has 6 fields")
    if any(not f for f in fields):
        raise ValueError("empty field")
    name = fields[0]
    if not _name_ok(name):
        raise ValueError("bad colour name")
    if any(c.name == name for c in colours):
        raise ValueError("duplicate colour name")
    rgb565 = _ranged(fields[1], 0, 0xFFFF, "rgb565")
    rgb555 = _ranged(fields[2], 0, 0x7FFF, "rgb555")
    rgb888 = _ranged(fields[3], 0, 0xFFFFFF, "rgb888")
    base = _ranged(fields[4], 0, 255, "index_base")
    levels = _ranged(fields[5], 0, 255, "index_levels")
    isbg = name == "background"
    if isbg and levels != 0:
        raise ValueError("background index_levels must be 0")
    if not isbg and levels == 0:
        raise ValueError("index_levels 0 only for background")
    if base + levels > 255:
        raise ValueError("index_base + index_levels above 255")
    for e in colours:
        if isbg or e.name == "background":
            ramp_base, bg_base = (e.index_base, base) if isbg else (base, e.index_base)
            if ramp_base <= bg_base:
                raise ValueError("background index must be below every ramp")
        elif base <= e.index_base + e.index_levels and e.index_base <= base + levels:
            raise ValueError("ramps overlap")
    return Colour(name, rgb565, rgb555, rgb888, base, levels)


def _line_record(colours, background, nlines, fields, nf, src_line):
    if nlines == MAX_LINES:
        raise ValueError("more than 32 lines")
    if nf != 6:
        raise ValueError("a line record has 6 fields")
    if any(not f for f in fields[:5]):
        raise ValueError("empty field")
    faces = []
    for piece in fields[0].split("+"):
        if len(faces) == MAX_FACES:
            raise ValueError("more than 4 faces")
        if not _FACE.match(piece):
            raise ValueError("bad face name")
        faces.append(piece)
    if fields[1].count("/") != 1:
        raise ValueError("bad scale")
    n, d = (_num(p) for p in fields[1].split("/"))
    if n is None or d is None:
        raise ValueError("bad scale")
    if not (1 <= n <= 16 and 1 <= d <= 16):
        raise ValueError("scale out of range")
    x = _ranged(fields[2], -32768, 32767, "x", True)
    baseline = _ranged(fields[3], -32768, 32767, "baseline", True)
    for i, c in enumerate(colours):
        if c.name == fields[4]:
            break
    else:
        raise ValueError("unknown colour")
    if i == background:
        raise ValueError("background is not a line colour")
    return Line(faces, n, d, i, x, baseline, fields[5], src_line)


def parse(path):
    """The Table of the file at @p path; VesaLinesError(line_no, message) on a refusal."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(MAX_FILE + 1)
    except OSError:
        raise VesaLinesError(1, "read error") from None
    raw = data.split(b"\n")
    last_has_nl = True
    if raw and raw[-1] == b"":
        raw.pop()
    else:
        last_has_nl = False
    colours, lines, background = [], [], None
    state = 0  # 0 start, 1 colours, 2 lines
    n = 0
    offset = 0   # bytes the C reader has read before this line
    for k, rl in enumerate(raw):
        n = k + 1
        has_nl = k < len(raw) - 1 or last_has_nl
        total = len(rl) + (1 if has_nl else 0)
        try:
            # the C reader reads at most 512 bytes of a line and peeks at one more when the line goes on; a read past
            # 65536 bytes is refused first, at line 1, whatever the line
            if offset + (LINE_BYTES + 1 if total > LINE_BYTES else total) > MAX_FILE:
                n = 1
                raise ValueError("file too large")
            offset += total
            if len(rl) + (1 if has_nl else 0) > LINE_BYTES:
                raise ValueError("line too long")
            if b"\0" in rl:
                raise ValueError("NUL byte")
            try:
                s = rl.decode("utf-8")
            except UnicodeDecodeError:
                raise ValueError("invalid UTF-8") from None
            s = s.strip(_TRIM)
            if not s or s[0] == "#":
                continue
            if s[0] == "[":
                if s == "[colours]":
                    if state == 1:
                        raise ValueError("repeated header [colours]")
                    if state == 2:
                        raise ValueError("header after [lines]")
                    state = 1
                elif s == "[lines]":
                    if state == 0:
                        raise ValueError("first section must be [colours]")
                    if state == 2:
                        raise ValueError("repeated header [lines]")
                    if background is None:
                        raise ValueError("missing background")
                    state = 2
                else:
                    raise ValueError("first section must be [colours]" if state == 0 else "unknown section header")
                continue
            if state == 0:
                raise ValueError("first section must be [colours]")
            fields = [f.strip(_TRIM) for f in s.split("|")]
            if state == 1:
                c = _colour_record(colours, fields, len(fields))
                if c.name == "background":
                    background = len(colours)
                colours.append(c)
            else:
                lines.append(_line_record(colours, background, len(lines), fields, len(fields), n))
        except ValueError as e:
            raise VesaLinesError(n, str(e)) from None
    try:
        if state == 0:
            raise ValueError("first section must be [colours]")
        if background is None:
            raise ValueError("missing background")
    except ValueError as e:
        raise VesaLinesError(n + 1, str(e)) from None
    return Table(colours, background, lines)


def _rgb(v):
    return (v >> 16 & 255, v >> 8 & 255, v & 255)


def palette(table, dac_bits):
    """[(b, g, r, 0)] * 256: vbe_palette_entry's rule per index (>> 2 with a 6-bit DAC)."""
    bg = _rgb(table.colours[table.background].rgb888)

    def entry(k, n, fg):
        out = []
        for c in (2, 1, 0):  # B G R
            v = bg[c] if n == 0 else (bg[c] * (n - k) + fg[c] * k + n // 2) // n
            out.append(v >> 2 if dac_bits == 6 else v)
        return tuple(out) + (0,)

    pal = [entry(0, 0, bg)] * 256
    for i, c in enumerate(table.colours):
        if i == table.background:
            continue
        for k in range(c.index_levels + 1):
            pal[c.index_base + k] = entry(k, c.index_levels, _rgb(c.rgb888))
    return pal


def substitute(text, w, h, bpp):
    """text with {W} {H} {BPP} replaced by decimal numbers; anything else is kept."""
    return re.sub(r"\{(W|H|BPP)\}", lambda m: str({"W": w, "H": h, "BPP": bpp}[m.group(1)]), text)


def print_table(table, dac_bits):
    """The exact text of `vesa-lines-dump --print-table` (--dac dac_bits)."""
    out = []
    for c in table.colours:
        out.append("colour name=%s rgb565=0x%04X rgb555=0x%04X rgb888=0x%06X base=%d levels=%d\n" % c)
    out.append("background=%s\n" % table.colours[table.background].name)
    for l in table.lines:
        out.append("line faces=%s scale=%d/%d x=%d baseline=%d colour=%s text=%s\n" % (
            "+".join(l.faces), l.num, l.den, l.x, l.baseline, table.colours[l.colour].name, l.text))
    for i, (b, g, r, _) in enumerate(palette(table, dac_bits)):
        out.append("palette[%d]=%02X %02X %02X\n" % (i, b, g, r))
    return "".join(out)


KINDS = {8: "indexed8", 15: "rgb555", 16: "rgb565", 24: "rgb888", 32: "xrgb8888"}
BYTES_PP = {8: 1, 15: 2, 16: 2, 24: 3, 32: 4}


def _face_path(faces_dir, name, line_no):
    if not _FACE.match(name):
        raise VesaLinesError(line_no, "bad face name")
    root = os.path.realpath(faces_dir)
    real = os.path.realpath(os.path.join(faces_dir, name))
    if os.path.dirname(real) != root:
        raise VesaLinesError(line_no, "face %s is not inside the faces directory" % name)
    return real


def _pixel(table, bpp):
    bg = table.colours[table.background]
    if bpp == 8:
        return bytes((bg.index_base,))
    if bpp == 15:
        return bg.rgb555.to_bytes(2, "little")
    if bpp == 16:
        return bg.rgb565.to_bytes(2, "little")
    px = bytes((bg.rgb888 & 255, bg.rgb888 >> 8 & 255, bg.rgb888 >> 16 & 255))
    return px + b"\0" if bpp == 32 else px


def expected_buffer(table, faces_dir, w, h, bpp):
    """The back buffer svfvesa.c holds for a @p w x @p h mode of logical depth @p bpp: the background pixel
    everywhere, then each line drawn with its chain, scale, x, baseline and colour (svfline.draw_target)."""
    bg = table.colours[table.background]
    buf = bytearray(_pixel(table, bpp) * (w * h))
    cache = {}
    for l in table.lines:
        chain = []
        for name in l.faces:
            path = _face_path(faces_dir, name, l.src_line)
            if path not in cache:
                try:
                    cache[path] = svfline.Face.load(path)
                except (OSError, ValueError):
                    raise VesaLinesError(l.src_line, "cannot read face %s" % name) from None
            chain.append(cache[path])
        c = table.colours[l.colour]
        t = svfline.Target(KINDS[bpp], w, h, buf=buf, fg565=c.rgb555 if bpp == 15 else c.rgb565,
                           bg565=bg.rgb555 if bpp == 15 else bg.rgb565, index_base=c.index_base,
                           index_levels=c.index_levels, fg888=c.rgb888, bg888=bg.rgb888)
        places = svfline.placements(chain, substitute(l.text, w, h, bpp).encode("utf-8"), l.x, l.baseline,
                                    scale=(l.num, l.den))
        svfline.draw_target(places, t)
    return bytes(buf)


def fnv1a(data):
    h = 2166136261
    for b in data:
        h = (h ^ b) * 16777619 & 0xFFFFFFFF
    return h


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if len(argv) in (2, 4) and argv[0] == "--print-table":
            dac = 8
            if len(argv) == 4:
                if argv[2] != "--dac" or argv[3] not in ("6", "8"):
                    raise IndexError
                dac = int(argv[3])
            sys.stdout.buffer.write(print_table(parse(argv[1]), dac).encode("utf-8"))
            return 0
        if len(argv) == 7 and argv[0] == "--expect" and argv[2] == "--faces":
            w, h, bpp = (int(v) for v in argv[4:7])
            if bpp not in KINDS or not (1 <= w <= 4096 and 1 <= h <= 4096):
                raise IndexError
            print("sum=%08x" % fnv1a(expected_buffer(parse(argv[1]), argv[3], w, h, bpp)))
            return 0
    except VesaLinesError as e:
        print("vesa-lines: %s" % e, file=sys.stderr)
        return 1
    except (IndexError, ValueError):
        pass
    print(__doc__.split("\n\n")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
