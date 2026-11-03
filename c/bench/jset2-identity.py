#!/usr/bin/env python3
"""JSET pixel identity per block version over a tree of faces.

usage: jset2-identity.py OLD_DUMP NEW_DUMP OLD_DIR NEW_DIR OUT.md [--only-version N]

OLD_DUMP is the svfdump of the baseline build (all faces version 1 blocks), NEW_DUMP the build under test. For every *.SVF
below NEW_DIR (and the same relative path below OLD_DIR; a face below OLD_DIR only is ignored, a face below NEW_DIR only is a
failure) the two dumps must agree on
  info        bpp, cell, ascent, flags, metrics, dy_ignored, jset_bad, jamo; a face with a JSET block has jamo=1 jset_bad=0
              on both sides,
  syllables   the Hangul cells and the jamo flag,
  glyphs      by code point outside plane 15 (record = metrics bytes + cell), the plane-15 records as a sorted multiset
              (a JSET version change renumbers the pieces), mapped, with --stream and with --stream=4:512;
              syllables also with --stream and --stream=4:512 (both sides, equal to the old mapped dump),
  lines       every LINE_TEXTS line of tools/test_c_renderer.py (imported, not copied) drawn at 400 40 2 28, mapped.
Each row of OUT.md carries the JSET version of the new block, the v1 bytes (the old block), the new bytes and NA (the alias
count of a version 2 block, - for version 1). The total line:
  faces=F jamo=J different=D v1_faces=A v1_bytes=B v2_faces=C v2_bytes=E jset_before=G jset_after=H
(v1_bytes / v2_bytes: the new blocks by version), followed by the means per geometry (lc x tc x ni x nm x nf).
--only-version N compares only the faces whose new block is version N. Exit 1 on any difference or unmatched path, 2 on a
usage error. Stdlib only (plus the tools directory's own modules).
"""
import hashlib
import importlib.util
import os
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools")
sys.path.insert(0, TOOLS)
import jamoset  # noqa: E402
import svf2to3  # noqa: E402


def _line_texts():
    spec = importlib.util.spec_from_file_location("test_c_renderer", os.path.join(TOOLS, "test_c_renderer.py"))
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


def glyph_split(blob, nglyphs):
    """({code point: record} outside plane 15, sorted list of the plane-15 records)."""
    if nglyphs == 0:
        return {}, []
    if len(blob) % nglyphs:
        raise RuntimeError("glyph dump of %d bytes for %d glyphs" % (len(blob), nglyphs))
    n = len(blob) // nglyphs
    plain, pieces = {}, []
    for i in range(nglyphs):
        rec = blob[i * n:(i + 1) * n]
        cp = int.from_bytes(rec[:4], "little")
        if jamoset.PIECE_BASE <= cp < jamoset.PIECE_BASE + 0x10000:
            pieces.append(rec[4:])
        else:
            plain[cp] = rec[4:]
    return plain, sorted(pieces)


def block_of(path):
    """The JSET block bytes of the face file, None without one (or when it is not an SVFN font)."""
    with open(path, "rb") as fh:
        return svf2to3._parse(fh.read()).jset


def block_facts(blk):
    """(version, size, NA or None, geometry string) of a block; (0, 0, None, '-') for none."""
    if blk is None:
        return 0, 0, None, "-"
    ver = struct.unpack_from("<H", blk, 4)[0]
    na = struct.unpack_from("<H", blk, 12)[0] if ver == 2 else None
    return ver, len(blk), na, "x".join(str(b) for b in blk[6:11])


def compare_face(old_dump, new_dump, fo, fn, only_version):
    """(row dict or None when skipped by only_version, list of differences)."""
    bo, bn = block_of(fo), block_of(fn)
    vo, so, _, go = block_facts(bo)
    vn, sn, na, gn = block_facts(bn)
    if only_version is not None and vn != only_version:
        return None, []
    diffs = []
    io, ko = info(old_dump, fo)
    inw, kn = info(new_dump, fn)
    if ko != kn:
        diffs.append("info %s != %s" % (ko, kn))
    for side, k, blk in (("old", ko, bo), ("new", kn, bn)):
        if blk is not None and (k["jamo"], k["jset_bad"]) != ("1", "0"):
            diffs.append("%s face has a JSET block but jamo=%s jset_bad=%s" % (side, k["jamo"], k["jset_bad"]))
    if go != gn:
        diffs.append("JSET geometry %s != %s" % (go, gn))
    go_, po = glyph_split(run(old_dump, fo, "glyphs"), int(io["glyphs"]))
    gn_, pn = glyph_split(run(new_dump, fn, "glyphs"), int(inw["glyphs"]))
    if go_ != gn_:
        bad = sorted(cp for cp in set(go_) | set(gn_) if go_.get(cp) != gn_.get(cp))
        diffs.append("glyphs differ at %d code points, first U+%04X" % (len(bad), bad[0]))
    if po != pn:
        diffs.append("plane-15 multiset differs (%d vs %d pieces)" % (len(po), len(pn)))
    for opt in ("--stream", "--stream=4:512"):
        for tag, dump, face, n, want in (("old", old_dump, fo, io, (go_, po)), ("new", new_dump, fn, inw, (gn_, pn))):
            if glyph_split(run(dump, opt, face, "glyphs"), int(n["glyphs"])) != want:
                diffs.append("%s %s glyphs differ from mapped" % (tag, opt))
    syl_o = run(old_dump, fo, "syllables")
    syl_n = run(new_dump, fn, "syllables")
    if syl_o != syl_n:
        diffs.append("syllables differ")
    for opt in ("--stream", "--stream=4:512"):     # composed through the JSET reader on the streamed path
        for tag, dump, face in (("old", old_dump, fo), ("new", new_dump, fn)):
            if run(dump, opt, face, "syllables") != syl_o:
                diffs.append("%s %s syllables differ from the old mapped ones" % (tag, opt))
    lines = hashlib.sha256()
    for text in LINE_TEXTS:
        lo = run(old_dump, "line", *LINE_ARGS, text, fo)
        ln = run(new_dump, "line", *LINE_ARGS, text, fn)
        lines.update(lo)
        if lo != ln:
            diffs.append("line %r differs" % text)
    return {"glyphs": len(go_) + len(po), "ver": vn, "before": so, "after": sn, "na": na, "geo": gn,
            "ssha": hashlib.sha256(syl_o).hexdigest()[:16], "lsha": lines.hexdigest()[:16],
            "jamo": bn is not None}, diffs


def main(argv):
    argv = list(argv)
    only_version = None
    if "--only-version" in argv:
        i = argv.index("--only-version")
        try:
            only_version = int(argv[i + 1])
        except (IndexError, ValueError):
            sys.stderr.write(__doc__)
            return 2
        del argv[i:i + 2]
    if len(argv) != 6:
        sys.stderr.write(__doc__)
        return 2
    old_dump, new_dump, d_old, d_new, out = argv[1:]

    def svfs(root):
        return {os.path.relpath(os.path.join(r, n), root).lower(): os.path.relpath(os.path.join(r, n), root)
                for r, _, ns in os.walk(root) for n in ns if n.lower().endswith(".svf")}

    t_old, t_new = svfs(d_old), svfs(d_new)
    rels = sorted(t_new[k] for k in t_new)
    only = ["%s only in the new tree" % t_new[k] for k in sorted(set(t_new) - set(t_old))]

    def one(rel):
        if rel.lower() not in t_old:
            return rel, None, ["missing in the old tree"]
        try:
            return (rel,) + compare_face(old_dump, new_dump, os.path.join(d_old, t_old[rel.lower()]),
                                         os.path.join(d_new, rel), only_version)
        except Exception as e:     # any failure names the face and counts as a difference
            return rel, None, ["%s: %s: %s" % (rel, type(e).__name__, e)]

    with ThreadPoolExecutor(JOBS) as ex:
        results = list(ex.map(one, rels))
    rows = ["| face | JSET version | v1 bytes | new bytes | NA | geometry | syllables sha256 | lines sha256 | identical |",
            "|---|---:|---:|---:|---:|---|---|---|---|"]
    faces = jamo = same = 0
    nbytes = {1: 0, 2: 0}
    nfaces = {1: 0, 2: 0}
    before = after = 0
    geo = {}
    bad = []
    for rel, row, diffs in results:
        if row is None and not diffs:
            continue
        faces += 1
        if row is None:
            rows.append("| %s | | | | | | | | NO (%s) |" % (rel, "; ".join(diffs)))
            bad.append((rel, diffs))
            continue
        if row["jamo"]:
            jamo += 1
            before += row["before"]
            after += row["after"]
            if row["ver"] in nbytes:
                nbytes[row["ver"]] += row["after"]
                nfaces[row["ver"]] += 1
            g = geo.setdefault((row["ver"], row["geo"]), [0, 0, 0])
            g[0] += 1
            g[1] += row["before"]
            g[2] += row["after"]
        rows.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            rel, row["ver"] or "-", row["before"] or "-", row["after"] or "-", "-" if row["na"] is None else row["na"],
            row["geo"], row["ssha"], row["lsha"], "yes" if not diffs else "NO (%s)" % "; ".join(diffs)))
        if diffs:
            bad.append((rel, diffs))
        else:
            same += 1
    total = ("faces=%d jamo=%d different=%d v1_faces=%d v1_bytes=%d v2_faces=%d v2_bytes=%d jset_before=%d "
             "jset_after=%d" % (faces, jamo, len(bad), nfaces[1], nbytes[1], nfaces[2], nbytes[2], before, after))
    gl = ["", "| new version | geometry lc x tc x ni x nm x nf | faces | mean v1 bytes | mean new bytes |", "|---:|---|---:|---:|---:|"]
    for (ver, g), (n, b, a) in sorted(geo.items()):
        gl.append("| %d | %s | %d | %.1f | %.1f |" % (ver, g.replace("x", " x "), n, b / n, a / n))
    with open(out, "w") as fh:
        fh.write("\n".join(rows) + "\n\n" + total + "\n" + "\n".join(gl) + "\n")
    print(total)
    for rel, diffs in bad:
        print("DIFFERENT %s: %s" % (rel, "; ".join(diffs)))
    for line in only:
        print("UNMATCHED %s" % line)
    return 1 if bad or only or not faces else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
