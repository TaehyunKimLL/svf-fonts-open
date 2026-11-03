#!/usr/bin/env python3
"""LIST exception faces: a jamo-set face plus whole glyphs and recombinations for chosen syllables (t_455b15cb).

  python3 tools/jamoexc.py build FACE.SVF EXC.json OUT.SVF [--jset-version 1|2] [--profile P] [--box B]

FACE is a v3 jamo-set face (JSET version 1 or 2). OUT is the same face with a JMAP block in list mode (LIST,
spec/SVF.md): the face's own JSET bytes are the fallback, kept verbatim, and up to 255 exceptions are listed. EXC is a
JSON object keyed by a syllable or a compat jamo, as the character ("가", "ㄱ") or "U+AC00":

  {"가": {"whole": "HEX"}, "각": {"pieces": [3, 7, 9]}, "ㄱ": {"pieces": [5]}}

"whole" is cell_h rows of ceil(cell_w * bpp / 8) bytes as hex; it becomes a new piece glyph numbered above the highest
U+F0000 + n of the face (syllables in ascending order first, then compat jamo). "pieces" are piece numbers of the face
(1 to 3 for a syllable, exactly one for a compat jamo). Any other key in a value (dy, advance, ...) is refused: a piece
carries no dy or metrics. Prints `jmap=BYTES ns=N whole=W recomb=R total=BYTES`, plus ` sparse=BYTES` (the size of a
SPARSE block with N entries) from N >= 200. Exit 0 written, 1 refused, 2 usage.

The face keeps its layout (no --profile: the source's units and flags), its JSET version (--jset-version re-encodes the
fallback through pack_fallback, numbers kept), and every glyph's metrics and dy. A new piece gets the metrics of the
face's first piece glyph and dy 0.
"""

import argparse
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jamoset  # noqa: E402

PIECE_KEYS = ("whole", "pieces")


class Refusal(Exception):
    pass


def parse_key(key):
    """('syl', s) or ('compat', k) of an EXC key: one character or U+XXXX."""
    cp = None
    m = re.fullmatch(r"[Uu]\+([0-9A-Fa-f]{4,6})", key)
    if len(key) == 1:
        cp = ord(key)
    elif m:
        cp = int(m.group(1), 16)
    if cp is None:
        raise Refusal(f"key {key!r} is not one character or U+XXXX")
    if 0xAC00 <= cp <= 0xD7A3:
        return "syl", cp - 0xAC00
    if 0x3131 <= cp <= 0x3163:
        return "compat", cp - 0x3131
    raise Refusal(f"key {key!r} (U+{cp:04X}) is not a syllable U+AC00..U+D7A3 or a compat jamo U+3131..U+3163")


def parse_exc(obj, stride, cell_w, cell_h, bpp):
    """(exceptions {s: bytes | [pieces]}, compat {k: bytes | piece}) of the EXC object @p obj."""
    if not isinstance(obj, dict):
        raise Refusal("the EXC file must be a JSON object")
    exc, compat = {}, {}
    for key, v in obj.items():
        kind, n = parse_key(key)
        if (exc if kind == "syl" else compat).get(n) is not None:
            raise Refusal(f"key {key!r} names U+{(0xAC00 if kind == 'syl' else 0x3131) + n:04X} twice")
        if not isinstance(v, dict):
            raise Refusal(f"{key!r}: the value must be an object with \"whole\" or \"pieces\"")
        extra = sorted(set(v) - set(PIECE_KEYS))
        if extra:
            raise Refusal(f"{key!r}: unknown key {extra[0]!r}: a piece carries no dy or metrics (only \"whole\" or "
                          "\"pieces\")")
        if len(v) != 1:
            raise Refusal(f"{key!r}: exactly one of \"whole\" or \"pieces\"")
        if "whole" in v:
            h = v["whole"]
            try:
                cell = bytes.fromhex(h) if isinstance(h, str) else None
            except ValueError:
                cell = None
            if cell is None:
                raise Refusal(f"{key!r}: \"whole\" is not hex")
            if len(cell) != stride:
                raise Refusal(f"{key!r}: \"whole\" is {len(cell)} bytes, expected {stride} bytes ({cell_h} rows of "
                              f"{(cell_w * bpp + 7) // 8})")
            val = cell
        else:
            p = v["pieces"]
            if not isinstance(p, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in p):
                raise Refusal(f"{key!r}: \"pieces\" must be a list of piece numbers")
            if kind == "compat":
                if len(p) != 1:
                    raise Refusal(f"{key!r}: a compat jamo takes exactly one piece, not {len(p)}")
                if p[0] == jamoset.BLANK:
                    raise Refusal(f"{key!r}: a compat entry needs a piece (65535 is BLANK); omit the key to keep the "
                                  "fallback's")
                val = p[0]
            else:
                if not 1 <= len(p) <= 3:
                    raise Refusal(f"{key!r}: a syllable takes 1 to 3 pieces, not {len(p)}")
                val = p
        (exc if kind == "syl" else compat)[n] = val
    if not exc:
        raise Refusal("a LIST needs at least one syllable entry (L3); compat jamo alone cannot be listed")
    return exc, compat


def _no_duplicates(pairs):
    seen = set()
    for k, _ in pairs:
        if k in seen:
            raise Refusal(f"key {k!r} is written twice")
        seen.add(k)
    return dict(pairs)


def build(src, obj, jset_version=None, profile=None, box=None):
    """(face bytes, report line) of the face bytes @p src with the EXC object @p obj. Refusal (or ValueError) on a refusal."""
    f = jamoset.parse_svfn(src)
    stride = ((f.cell_w * f.bpp + 7) // 8) * f.cell_h
    exc, compat = parse_exc(obj, stride, f.cell_w, f.cell_h, f.bpp)
    jm, new = jamoset.jmap_list(f, exc, compat, jset_version=jset_version)
    block = jamoset.pack_jmap(jm, jm.fallback_block)
    pieces = sorted(cp for cp in f.glyphs if jamoset.PIECE_BASE <= cp < jamoset.PIECE_BASE + 0x10000)
    default = f.metrics[pieces[0]] if f.metrics_ok and pieces else (f.cell_w, 0, f.cell_w)
    cells = dict(f.glyphs)
    cells.update(new)
    cps = sorted(cells)
    metrics = None
    if f.metrics_ok:
        metrics = [tuple(f.metrics[cp]) + (f.dy.get(cp, 0),) if cp in f.metrics else tuple(default) + (0,) for cp in cps]
    lo, hi = (f.dy_min, f.dy_max) if f.metrics_ok else (0, 0)
    try:
        out = jamoset.pack_svfn(f.cell_w, f.cell_h, f.ascent, f.bpp, f.flags & jamoset.FLAG_MARKS_AT_ORIGIN,
                                [cells[cp] for cp in cps], [(cp, i) for i, cp in enumerate(cps)], metrics, block,
                                (lo, hi), jamoset.face_profile(f, profile, box))
    except ValueError as e:
        if "does not fit u16 offsets" in str(e):
            raise Refusal(f"{e}: drop whole cells, or pass --profile with u32 or auto offsets") from None
        raise
    whole = len(new)
    recomb = sum(1 for v in exc.values() if not isinstance(v, bytes)) + \
        sum(1 for v in compat.values() if not isinstance(v, bytes))
    n = len(jm.entries)
    line = f"jmap={len(block)} ns={n} whole={whole} recomb={recomb} total={len(out)}"
    if n >= 200:
        line += f" sparse={jamoset.JMAP_SPARSE_ENTRIES + 3 * n}"
    return out, line


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="write the LIST face", formatter_class=argparse.RawDescriptionHelpFormatter,
                       epilog="Output line: jmap = bytes of the JMAP block; ns = syllable entries; whole = new whole "
                              "glyphs written (syllables and compat); recomb = entries given as pieces (syllables and "
                              "compat); total = bytes of the output file; sparse = bytes of a SPARSE block of ns "
                              "entries (printed from ns >= 200).")
    b.add_argument("face")
    b.add_argument("exc")
    b.add_argument("out")
    b.add_argument("--jset-version", type=int, choices=(1, 2), default=None,
                   help="re-encode the fallback JSET in this version (default: keep the source's bytes)")
    jamoset.add_profile_args(b, None, "the source face's layout")
    args = ap.parse_args(argv)
    profile = jamoset.profile_arg(ap, args)
    try:
        with open(args.face, "rb") as fh:
            src = fh.read()
        with open(args.exc, encoding="utf-8") as fh:
            obj = json.load(fh, object_pairs_hook=_no_duplicates)
    except (OSError, ValueError, Refusal) as e:
        print(f"jamoexc: {e}", file=sys.stderr)
        return 1
    try:
        out, line = build(src, obj, args.jset_version, profile, args.box)
    except (Refusal, ValueError, struct.error) as e:
        print(f"jamoexc: {e}", file=sys.stderr)
        return 1
    tmp = f"{args.out}.tmp{os.getpid()}"
    try:
        with open(tmp, "wb") as fh:
            fh.write(out)
        os.replace(tmp, args.out)
    except OSError as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        print(f"jamoexc: {e}", file=sys.stderr)
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
