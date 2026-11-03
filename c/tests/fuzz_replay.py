#!/usr/bin/env python3
"""Differential check of the C reader against tools/jamoset.parse_svfn over a fuzz corpus (stdlib + jamoset).

usage: fuzz_replay.py SVFDUMP DIR... [--jobs N]

SVFDUMP is the sanitizer build of c/tests/svfdump.c (make -C c svfdump-asan; a build that reads every layout). Every file
below the DIRs goes through `svfdump FILE info` (svf_open_mapped: open result, jset_bad, glyph count) and through
jamoset.parse_svfn. They must agree: both accept or both refuse; when both accept, the same glyph count (distinct code
points) and the same JSET verdict (C jset_bad=1 or jmap_bad=1 iff the Python parser marks the block bad). Any sanitizer report of the
C side is a failure.

A build without SVF_JMAP (SVF_JMAP_RECOG: svfdump prints jmap_unread=1 for a version 3 block) only recognises a JMAP block: it
validates its flags and NS (and the fallback JSET it reads in its place), not R2, R4's length, R5-R8. A version 3 block that
fails a later rule is then legitimately not bad there but bad for Python, and its compat and syllable cells come from the
fallback or the cmap, not the JMAP. For such a face (jmap_unread=1) the harness compares only open acceptance and the distinct
code points of the glyph table; the full comparison is the default: the host builds SVF_JMAP=1 (make ASAN='-DSVF_JMAP=0 ...' builds the recognition twin). Prints one line per disagreement and a total; exit 0 clean, 1 on any disagreement, 2 usage.
"""
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
import jamoset  # noqa: E402


def c_view(dump, path):
    r = subprocess.run([dump, path, "info"], capture_output=True, text=True)
    if "Sanitizer" in r.stderr or "runtime error" in r.stderr or r.returncode not in (0, 2):
        return "crash", r.stderr[:300]
    if r.returncode == 2:
        m = re.search(r"(SVF_E_\w+)", r.stderr)
        return "refused", m.group(1) if m else r.stderr.strip()[:80]
    kv = dict(p.split("=", 1) for p in r.stdout.split() if "=" in p)
    return "ok", kv


def py_view(path):
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        f = jamoset.parse_svfn(data)
    except ValueError as e:
        return "refused", str(e)[:80]
    return "ok", f


def compat_pieces(pv):
    """{compat code point: plane-15 piece code point} for a face whose JSET block is usable: spec/SVF.md draws U+3131..U+3163
    with a compatPiece as that piece alone, whatever glyph the table also holds for the code point (the C reader and
    jamoset.unpack agree). A usable block always has the glyph of every piece it names (jamoset.parse_svfn marks the block bad
    otherwise), so the lookup in pv.glyphs cannot miss."""
    if pv.jset_bad or not pv.jset:
        return {}
    try:
        t = jamoset.unpack(pv.jset)
    except ValueError:
        return {}
    return {0x3131 + k: 0xF0000 + p for k, p in enumerate(t.compat) if p != jamoset.BLANK}


def glyphs_differ(dump, path, cv, pv, unread=False):
    """The C glyph dump (one record per code point table entry, file order) against the Python glyphs {cp: cell}: the same
    distinct code points and, the last entry of a code point winning (spec: a code point listed twice), the same cell (a compat code point with a compatPiece is compared with that piece, a Hangul syllable of a face with a usable JSET block is not compared: the composed cell shadows the table glyph, and the composition itself is checked by jset2-identity.py and test_c_renderer; the Python parser keeps the padding bits of a row as the file has them, the C reader zeroes them: compared masked)."""
    r = subprocess.run([dump, path, "glyphs"], capture_output=True)
    if r.returncode:
        return "svfdump glyphs failed"
    cell = ((int(cv["cell_w"]) * int(cv["bpp"]) + 7) // 8) * int(cv["cell_h"])
    rec = 8 + cell
    out = r.stdout
    n = int(cv["glyphs"])
    if len(out) != n * rec:
        return f"glyph dump {len(out)} bytes, {n} records of {rec}"
    bpp, cw = int(cv["bpp"]), int(cv["cell_w"])
    pitch = (cw * bpp + 7) // 8
    used = (cw * bpp) % 8  # bits used in a row's last byte; the rest is padding, which the C reader zeroes
    keep = 0xFF if not used else (0xFF << (8 - used)) & 0xFF
    last = {}
    for i in range(n):
        o = i * rec
        last[int.from_bytes(out[o:o + 4], "little")] = out[o + 8:o + rec]
    if set(last) != set(pv.glyphs):
        return f"distinct code points C {len(last)}, Python {len(pv.glyphs)}"
    piece = compat_pieces(pv)
    syl = not pv.jset_bad and bool(pv.jset)
    for cp, c in last.items():
        if unread and (0x3131 <= cp <= 0x3163 or 0xAC00 <= cp <= 0xD7A3):
            continue    # a recognition build (jmap_unread): these cells are the fallback's or the cmap's, not the JMAP's
        if syl and 0xAC00 <= cp <= 0xD7A3:
            continue    # a syllable of a face with a usable JSET block is composed; the table glyph is shadowed (not compared)
        q = bytearray(pv.glyphs[piece[cp]] if cp in piece else pv.glyphs[cp])
        for y in range(len(q) // pitch):
            q[y * pitch + pitch - 1] &= keep
        if bytes(q) != c:
            return f"cell of U+{cp:04X} differs"
    return None


def check(dump, path):
    cs, cv = c_view(dump, path)
    ps, pv = py_view(path)
    if cs == "crash":
        return f"{path}: C crashed: {cv}"
    if cs != ps:
        return f"{path}: C {cs} ({cv if cs == 'refused' else ''}), Python {ps} ({pv if ps == 'refused' else ''})"
    if cs == "ok":
        unread = cv.get("jmap_unread") == "1"
        msg = glyphs_differ(dump, path, cv, pv, unread)
        if msg:
            return f"{path}: {msg}"
        if unread:
            return None     # the JMAP part is not read here: no verdict to compare (see the module doc)
        if bool(int(cv["jset_bad"]) or int(cv.get("jmap_bad", 0))) != bool(pv.jset_bad):
            return f"{path}: jset_bad C {cv['jset_bad']} jmap_bad {cv.get('jmap_bad', 0)}, Python {pv.jset_bad}"
    return None


def main(argv):
    jobs = 4
    args = [a for a in argv[1:]]
    if "--jobs" in args:
        i = args.index("--jobs")
        jobs = int(args[i + 1])
        del args[i:i + 2]
    if len(args) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    dump, dirs = args[0], args[1:]
    files = sorted(os.path.join(r, n) for d in dirs for r, _, ns in os.walk(d) for n in ns)
    with ThreadPoolExecutor(jobs) as ex:
        bad = [m for m in ex.map(lambda p: check(dump, p), files) if m]
    for m in bad:
        print(m)
    print(f"fuzz_replay: files={len(files)} disagreements={len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
