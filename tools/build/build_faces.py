#!/usr/bin/env python3
"""Rebuild the faces of svf/ from their upstream fonts with the repository's tools, as tools/build/faces.tsv says.

    python3 tools/build/build_faces.py --out DIR [FACE ...] [--ext NAME=PATH ...] [--list]

FACE is a row's face (dos/NGOTB15.SVF) or its file name (NGOTB15.SVF, NGOTB15); none means every row with a recipe.
Each face is written to DIR/<face> and compared with svf/<face>:
    identical   the same bytes
    pixels      the same glyphs, metrics and header values, another byte layout
    differs     anything else (the first differing code points are printed)
A row whose source is ext:NAME needs --ext NAME=PATH (a font that is not in this repository); without it the row is
reported "skipped". Exit 0 when every built face matches its row's expect column ("identical" rows must be identical,
"differs" rows may differ), 1 otherwise, 2 for a usage error. --list prints the table's rows and exits.
Writes only below DIR. docs/recipes/svf-faces.md describes the recipes.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TOOLS = os.path.join(ROOT, "tools")
TABLE = os.path.join(HERE, "faces.tsv")
sys.path.insert(0, TOOLS)
import jamoset  # noqa: E402

COLUMNS = ("face", "method", "source", "args", "codepoints", "expect", "note")


def read_table(path=TABLE):
    """The rows of faces.tsv as dicts (COLUMNS), in file order; ValueError on a malformed line."""
    rows = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            cells = line.split("\t")
            if len(cells) != len(COLUMNS):
                raise ValueError("%s:%d: %d columns, want %d" % (path, n, len(cells), len(COLUMNS)))
            row = dict(zip(COLUMNS, cells))
            if row["method"] not in ("mkfont", "jamoset", "none"):
                raise ValueError("%s:%d: unknown method %r" % (path, n, row["method"]))
            if row["expect"] not in ("identical", "differs", "none"):
                raise ValueError("%s:%d: unknown expect %r" % (path, n, row["expect"]))
            if (row["method"] == "none") != (row["expect"] == "none"):
                raise ValueError("%s:%d: method none goes with expect none" % (path, n))
            if row["method"] == "none" and not row["note"]:
                raise ValueError("%s:%d: a row without a recipe needs a note" % (path, n))
            rows.append(row)
    return rows


def codepoints(spec):
    """mkfont.py --unicode text: a named set as it is, or the lines of a file under tools/build/ joined by commas."""
    if spec.startswith("cps/"):
        with open(os.path.join(HERE, spec), encoding="ascii") as fh:
            return ",".join(x.strip() for x in fh if x.strip())
    return spec


def source_path(src, ext):
    if src.startswith("ext:"):
        return ext.get(src[4:])
    return os.path.join(ROOT, src)


def resolve_ext(args, ext):
    """args with every ext:NAME replaced by its path (None when one is not given)."""
    out = []
    for a in args.split():
        if a.startswith("ext:"):
            if a[4:] not in ext:
                return None
            a = ext[a[4:]]
        out.append(a)
    return out


def run(cmd):
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("%s failed (%d): %s" % (os.path.basename(cmd[0]), r.returncode, (r.stderr or r.stdout)[-400:]))


def build(row, out_dir, ext):
    """Write the face of @p row below @p out_dir; returns its path, or None when an ext: font is missing."""
    src = source_path(row["source"], ext)
    if src is None:
        return None
    out = os.path.join(out_dir, row["face"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    if row["method"] == "mkfont":
        args = resolve_ext(row["args"], ext)
        if args is None:
            return None
        run([os.path.join(TOOLS, "mkfont.py"), src, tmp] + args + ["--unicode", codepoints(row["codepoints"])])
        run([os.path.join(TOOLS, "svf2to3.py"), tmp, out, "--profile", "default"])
    else:
        mk, _, js = row["args"].partition("|")
        mk_args, js_args = resolve_ext(mk, ext), resolve_ext(js, ext)
        if mk_args is None or js_args is None:
            return None
        run([os.path.join(TOOLS, "mkfont.py"), src, tmp] + mk_args + ["--unicode", codepoints(row["codepoints"])])
        run([os.path.join(TOOLS, "jamoset.py"), "--from-svf", tmp, "-o", out] + js_args)
    os.remove(tmp)
    return out


def compare(built, shipped):
    """'identical', 'pixels' or 'differs: ...' for two SVFN v3 files."""
    a, b = open(built, "rb").read(), open(shipped, "rb").read()
    if a == b:
        return "identical"
    fa, fb = jamoset.parse_svfn(a), jamoset.parse_svfn(b)
    head = lambda f: (f.cell_w, f.cell_h, f.ascent, f.bpp, f.flags, f.dy_min, f.dy_max, f.jset)
    if head(fa) != head(fb):
        return "differs: header or JSET block"
    only_b = sorted(set(fb.glyphs) - set(fa.glyphs))
    only_a = sorted(set(fa.glyphs) - set(fb.glyphs))
    diff = [c for c in fb.glyphs if c in fa.glyphs and (fa.glyphs[c] != fb.glyphs[c] or fa.metrics.get(c) != fb.metrics.get(c))]
    if not (only_a or only_b or diff):
        return "pixels"
    hx = lambda cps: " ".join("U+%04X" % c for c in cps[:4])
    return "differs: %d only in svf/ (%s), %d only built (%s), %d drawn otherwise (%s)" % (
        len(only_b), hx(only_b), len(only_a), hx(only_a), len(diff), hx(diff))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("faces", nargs="*")
    ap.add_argument("--out")
    ap.add_argument("--ext", action="append", default=[], metavar="NAME=PATH")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    rows = read_table()
    if a.list:
        for r in rows:
            print("\t".join(r[c] for c in COLUMNS))
        return 0
    if not a.out:
        ap.error("--out DIR is required")
    ext = {}
    for e in a.ext:
        name, sep, path = e.partition("=")
        if not sep:
            ap.error("--ext wants NAME=PATH, got %r" % e)
        ext[name] = path
    want = {f if "/" in f else (f if f.upper().endswith(".SVF") else f + ".SVF").upper() for f in a.faces}
    picked = [r for r in rows if r["method"] != "none" and
              (not want or r["face"] in want or os.path.basename(r["face"]).upper() in want)]
    if want and not picked:
        print("build_faces: no recipe row for %s" % " ".join(sorted(want)), file=sys.stderr)
        return 2
    bad = counts = 0
    tally = {}
    for r in picked:
        try:
            built = build(r, a.out, ext)
        except RuntimeError as e:
            print("%s FAIL %s" % (r["face"], e))
            bad += 1
            continue
        if built is None:
            status = "skipped (needs --ext %s=PATH)" % next(x[4:] for x in (r["source"] + " " + r["args"]).split()
                                                            if x.startswith("ext:"))
        else:
            status = compare(built, os.path.join(ROOT, "svf", r["face"]))
            if r["expect"] == "identical" and status != "identical":
                bad += 1
                status += "  (expected identical)"
        key = status.split(":")[0].split(" (")[0]
        tally[key] = tally.get(key, 0) + 1
        counts += 1
        print("%s %s" % (r["face"], status))
    print("build_faces: %d built, %s" % (counts, ", ".join("%s %d" % kv for kv in sorted(tally.items()))))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
