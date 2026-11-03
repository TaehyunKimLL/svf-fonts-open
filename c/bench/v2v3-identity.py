#!/usr/bin/env python3
"""v2 -> v3 pixel identity over a tree of faces.

usage: v2v3-identity.py V2_DUMP V3_DUMP V2_DIR V3_DIR OUT.md

V2_DUMP is the last v2 build of svfdump, V3_DUMP the current one. For every *.SVF below V2_DIR (and the same relative
path below V3_DIR) the two dumps must agree on
  glyphs      as {code point: record}, the last entry of a code point winning (record = metrics bytes + cell),
  syllables   the Hangul cells and the jamo flag,
  info        bpp, cell, ascent, flags, metrics, dy_ignored, jset_bad, jamo,
  --stream and --stream=4:512 glyphs,
  every LINE_TEXTS line of tools/test_c_renderer.py (imported, not copied) drawn at 400 40 2 28.
The *.svf files are found case-insensitively; a path present in only one of the two trees is a failure.
OUT.md gets one table row per face and a total line. Exit 1 on any difference or unmatched path, 2 on a usage error.
Stdlib only (the import of tools/test_c_renderer.py needs the tools directory's own modules, all stdlib or fontTools).
"""
import hashlib
import importlib.util
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor



def _line_texts():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "test_c_renderer.py")
    spec = importlib.util.spec_from_file_location("test_c_renderer", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.LINE_TEXTS


LINE_TEXTS = _line_texts()
LINE_ARGS = ("400", "40", "2", "28")
INFO_KEYS = ("bpp", "cell_w", "cell_h", "ascent", "flags", "metrics", "dy_ignored", "jset_bad", "jamo")
JOBS = 4


def run(exe, *args):
    r = subprocess.run([exe, *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("%s %s: exit %d: %s" % (os.path.basename(exe), " ".join(map(str, args[-3:])), r.returncode,
                                                   r.stderr.decode(errors="replace")[:200]))
    return r.stdout


def info(exe, face):
    d = dict(kv.split("=", 1) for kv in run(exe, face, "info").decode().split())
    return d, {k: d[k] for k in INFO_KEYS}


def glyph_map(blob, nglyphs):
    if nglyphs == 0:
        return {}
    if len(blob) % nglyphs:
        raise RuntimeError("glyph dump of %d bytes for %d glyphs" % (len(blob), nglyphs))
    n = len(blob) // nglyphs
    out = {}
    for i in range(nglyphs):
        rec = blob[i * n:(i + 1) * n]
        out[int.from_bytes(rec[:4], "little")] = rec[4:]
    return out


def compare_face(v2_dump, v3_dump, f2, f3):
    """(row dict, list of differences)."""
    diffs = []
    i2, k2 = info(v2_dump, f2)
    i3, k3 = info(v3_dump, f3)
    if k2 != k3:
        diffs.append("info %s != %s" % (k2, k3))
    g2 = glyph_map(run(v2_dump, f2, "glyphs"), int(i2["glyphs"]))
    g3 = glyph_map(run(v3_dump, f3, "glyphs"), int(i3["glyphs"]))
    if g2 != g3:
        bad = sorted(cp for cp in set(g2) | set(g3) if g2.get(cp) != g3.get(cp))
        diffs.append("glyphs differ at %d code points, first U+%04X" % (len(bad), bad[0]))
    for opt in ("--stream", "--stream=4:512"):
        s2 = glyph_map(run(v2_dump, opt, f2, "glyphs"), int(i2["glyphs"]))
        s3 = glyph_map(run(v3_dump, opt, f3, "glyphs"), int(i3["glyphs"]))
        if s2 != g2:
            diffs.append("v2 %s glyphs differ from mapped" % opt)
        if s3 != s2:
            diffs.append("%s glyphs differ" % opt)
    syl2 = run(v2_dump, f2, "syllables")
    syl3 = run(v3_dump, f3, "syllables")
    if syl2 != syl3:
        diffs.append("syllables differ")
    lines2, lines3 = hashlib.sha256(), hashlib.sha256()
    for text in LINE_TEXTS:
        l2 = run(v2_dump, "line", *LINE_ARGS, text, f2)
        l3 = run(v3_dump, "line", *LINE_ARGS, text, f3)
        lines2.update(l2)
        lines3.update(l3)
        if l2 != l3:
            diffs.append("line %r differs" % text)
    gh = hashlib.sha256()
    for cp in sorted(g2):
        gh.update(cp.to_bytes(4, "little") + g2[cp])
    return {
        "glyphs": len(g2),
        "v2": os.path.getsize(f2), "v3": os.path.getsize(f3),
        "gsha": gh.hexdigest()[:16], "ssha": hashlib.sha256(syl2).hexdigest()[:16],
        "lsha": lines2.hexdigest()[:16],
    }, diffs


def main(argv):
    if len(argv) != 6:
        sys.stderr.write(__doc__)
        return 2
    v2_dump, v3_dump, d2, d3, out = argv[1:]
    def svfs(root):
        return {os.path.relpath(os.path.join(r, n), root).lower(): os.path.relpath(os.path.join(r, n), root)
                for r, _, ns in os.walk(root) for n in ns if n.lower().endswith(".svf")}

    t2, t3 = svfs(d2), svfs(d3)
    rels = sorted(t2[k] for k in t2)
    only = ["%s only in the v2 tree" % t2[k] for k in sorted(set(t2) - set(t3))] + \
           ["%s only in the v3 tree" % t3[k] for k in sorted(set(t3) - set(t2))]

    def one(rel):
        f3 = os.path.join(d3, t3.get(rel.lower(), rel))
        if rel.lower() not in t3:
            return rel, None, ["missing in v3 tree"]
        try:
            return (rel,) + compare_face(v2_dump, v3_dump, os.path.join(d2, rel), f3)
        except RuntimeError as e:
            return rel, None, [str(e)]

    with ThreadPoolExecutor(JOBS) as ex:
        results = list(ex.map(one, rels))
    rows = ["| face | glyphs | v2 bytes | v3 bytes | glyph dump sha256 | syllables sha256 | lines sha256 | identical |",
            "|---|---:|---:|---:|---|---|---|---|"]
    glyphs = b2 = b3 = same = 0
    bad = []
    for rel, row, diffs in results:
        if row is None:
            rows.append("| %s | | | | | | | NO (%s) |" % (rel, "; ".join(diffs)))
            bad.append((rel, diffs))
            continue
        glyphs += row["glyphs"]
        b2 += row["v2"]
        b3 += row["v3"]
        rows.append("| %s | %d | %d | %d | %s | %s | %s | %s |" % (
            rel, row["glyphs"], row["v2"], row["v3"], row["gsha"], row["ssha"], row["lsha"],
            "yes" if not diffs else "NO (%s)" % "; ".join(diffs)))
        if diffs:
            bad.append((rel, diffs))
        else:
            same += 1
    total = "total faces=%d identical=%d different=%d glyphs=%d v2_bytes=%d v3_bytes=%d unmatched=%d" % (
        len(rels), same, len(bad), glyphs, b2, b3, len(only))
    with open(out, "w") as fh:
        fh.write("\n".join(rows) + "\n\n" + total + "\n")
    print(total)
    for rel, diffs in bad:
        print("DIFFERENT %s: %s" % (rel, "; ".join(diffs)))
    for line in only:
        print("UNMATCHED %s" % line)
    return 1 if bad or only or not rels else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
