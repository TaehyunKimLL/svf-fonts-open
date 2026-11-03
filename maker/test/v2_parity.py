#!/usr/bin/env python3
"""The maker's v3 output against the v2 output of the same routes (card t_a0a737c9), run by hand.

    python3 maker/test/v2_parity.py V2_TOOLS [--work DIR]

V2_TOOLS is a `tools/` tree that still writes SVFN v2 (`git archive svf-maker tools | tar -x -C DIR`). For every route
of the fixture tree (fixtures.write_fixtures) the script builds the route's argv with `routes.py`, runs it once with
V2_TOOLS and once with this checkout's tools, then proves the two faces equal:

  - the v3 face parses with jamoset.parse_svfn as version 3, the v2 face does not (it is v2);
  - `svf2to3.py V2 CONV --check` exits 0 (CONV is the v2 face packed as v3, pixel-identical to it);
  - svf2to3.check(V2, V3) passes (same glyphs, metrics and cells for every code point and composed syllable) and
    CONV parses to the same face as V3: header, layout, cells, metrics, dy and JSET (both are the default profile;
    the bytes may differ only in the glyph index order, which the line reports).

An SVF source is a v2 face on the v2 side (fixtures.v2_face of the checkout's v3 face) and the copy route ships it as
it is there; this checkout's copy route converts the same v2 upload. Exit 1 on the first difference. Needs Pillow and
fontTools (the maker's own requirements).
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import argparse
import subprocess
import tempfile

import fixtures
import jamoset
import routes
import svf2to3

TOOLS = os.path.join(REPO_DIR, "tools")
# what a reader sees of a parsed face; the glyph index order (and so the offset table) is the writer's own choice
FIELDS = ("version", "flags", "bpp", "cell_w", "cell_h", "ascent", "count", "dy_min", "dy_max", "layout", "glyphs",
          "metrics_ok", "metrics", "dy", "jset")


def cases(fx, work):
    """[(name, font entry, kind, size, bpp, layout, src, extra paths)] covering every route the fixtures reach."""
    v2_pre = os.path.join(work, "NEODG16-v2.SVF")
    v2_jamo = os.path.join(work, "NEODG16G-v2.SVF")
    for src, dst in ((fx["svf_pre"], v2_pre), (fx["svf_jamo"], v2_jamo)):
        with open(src, "rb") as f, open(dst, "wb") as out:
            out.write(fixtures.v2_face(f.read()))
    rng = os.path.join(work, "range.txt")
    with open(rng, "w", encoding="utf-8") as f:
        f.write("".join(chr(c) for c in range(0x20, 0x7F)) + "가각간갇갈감갑값강개객거건걸검겁게겨격견결겸겹경계고곡곤골곰곱공과관광괴교구국군굴궁권귀규균그극근글금급기긴길김")

    def svf(version, bpp=1):
        return {"version": version, "flags": 1, "bpp": bpp, "cell": [16, 16], "ascent": 12, "glyphs": 0}

    def font(kind, **kw):
        e = {"face_index": 0, "source_kind": kind, "sizes": [16], "sizes_fixed": True}
        e.update(kw)
        return e

    yield ("mkfont ttf 16/1", font("outline", sizes=[]), "precomposed", 16, 1, None, fx["ttf"], {"range_file": rng})
    yield ("mkfont ttf 16/2", font("outline", sizes=[]), "precomposed", 16, 2, None, fx["ttf"], {"range_file": rng})
    yield ("mkfont otf 16/1", font("outline", sizes=[]), "precomposed", 16, 1, None, fx["otf"], {"range_file": rng})
    yield ("mkfont bdf-iso 16/1", font("bdf-iso10646"), "precomposed", 16, 1, None, fx["bdf_iso"], {"range_file": rng})
    yield ("bdfface ksc 24/1", font("bdf-ksc5601", sizes=[24], bdf={"box": [24, 24]}), "precomposed", 24, 1, None,
           fx["bdf_ksc"], {"range_file": rng, "latin": fx["bdf_latin"]})
    yield ("dos raw 844", font("dos-raw", dos={"candidates": ["844"], "faces": [0]}), "jamo", 16, 1, "844",
           fx["dos_raw"], {"eng": fx["dos_eng"]})
    yield ("hanterm johab", font("bdf-johab"), "jamo", 16, 1, "hanterm-johab", fx["bdf_johab"], {})
    yield ("svf copy precomposed", font("svf-precomposed", svf=svf(2)), "precomposed", 16, 1, None, v2_pre, {})
    yield ("svf copy jamo", font("svf-jamo", svf=svf(2)), "jamo", 16, 1, None, v2_jamo, {})
    yield ("composite 844 16/1", font("outline-composite", sizes=[]), "jamo", 16, 1, "844", fx["composite"], {})
    yield ("composite adaptive 16/2", font("outline-composite", sizes=[]), "jamo", 16, 2, "adaptive", fx["composite"],
           {})
    yield ("from-svf fit 844", font("svf-precomposed", svf=svf(2)), "jamo-fit", 16, 1, "844", v2_pre, {})


def run(argvs, cwd):
    for argv in argvs:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
        if p.returncode:
            raise SystemExit("FAIL %s: exit %d\n%s" % (" ".join(argv), p.returncode, p.stderr[-2000:]))


def build(entry, kind, size, bpp, layout, src, extra, tools, step_dir, out):
    if kind == "jamo-fit":
        route = [r for r in routes.routes(entry) if r.label == "from-svf fit"][0]
    else:
        route = routes.route_for(entry, kind, False)
    paths = {"tools": tools, "src": src, "out": out, "work": step_dir, "eng": None, "latin": None, "master": None,
             "range_file": None}
    paths.update(extra)
    os.makedirs(step_dir, exist_ok=True)
    rng = ("file", extra["range_file"]) if extra.get("range_file") else ("2350", None)
    if route.prepare is not None:                   # composite: the jamovec master once, then the render
        paths["master"] = os.path.join(step_dir, "master.json")
        run(route.prepare_commands(entry, layout, dict(paths, out=paths["master"])), step_dir)
    argvs = route.commands(entry, size, bpp, layout, rng, paths, [])
    if not argvs:                                   # the copy route
        with open(src, "rb") as f, open(out, "wb") as o:
            o.write(f.read())
    else:
        run(argvs, step_dir)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("v2_tools")
    ap.add_argument("--work", default=None)
    args = ap.parse_args()
    v2_tools = os.path.abspath(args.v2_tools)
    work = args.work or tempfile.mkdtemp(prefix="v2parity-")
    fx = fixtures.write_fixtures(os.path.join(work, "fonts"))
    n = 0
    for i, (name, entry, kind, size, bpp, layout, src, extra) in enumerate(cases(fx, work)):
        d = os.path.join(work, "c%02d" % i)
        v2, v3, conv = os.path.join(d, "v2", "OUT.SVF"), os.path.join(d, "v3", "OUT.SVF"), os.path.join(d, "CONV.SVF")
        # the v2 side: the same route, its tools write v2 and read the v2 source as it is (no conversion step)
        v2_entry = dict(entry, svf=dict(entry["svf"], version=3)) if "svf" in entry else entry
        build(v2_entry, kind, size, bpp, layout, src, extra, v2_tools, os.path.dirname(v2), v2)
        build(entry, kind, size, bpp, layout, src, extra, TOOLS, os.path.dirname(v3), v3)
        with open(v2, "rb") as f:
            b2 = f.read()
        with open(v3, "rb") as f:
            b3 = f.read()
        if b2[4:6] != b"\x02\x00":
            raise SystemExit("FAIL %s: the v2 tools wrote version %d" % (name, b2[4] | b2[5] << 8))
        face = jamoset.parse_svfn(b3)
        if face.version != 3:
            raise SystemExit("FAIL %s: version %d" % (name, face.version))
        run([[sys.executable, os.path.join(TOOLS, "svf2to3.py"), v2, conv, "--check"]], d)
        try:
            svf2to3.check(b2, b3)
        except AssertionError as e:
            raise SystemExit("FAIL %s: v2 and v3 outputs differ: %s" % (name, e))
        with open(conv, "rb") as f:
            bc = f.read()
        fc = jamoset.parse_svfn(bc)
        for field in FIELDS:
            if getattr(fc, field) != getattr(face, field):
                raise SystemExit("FAIL %s: svf2to3 of the v2 output differs from the v3 output in %s" % (name, field))
        n += 1
        print("ok  %-22s v3 %6d bytes (v2 %6d), %5d glyphs, jamo %-5s svf2to3 --check identical, bytes %s"
              % (name, len(b3), len(b2), face.count, face.jset is not None,
                 "identical" if bc == b3 else "same face, glyph index order differs"))
    print("%d routes: v3 output == svf2to3(v2 output)" % n)


if __name__ == "__main__":
    main()
