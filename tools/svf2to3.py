#!/usr/bin/env python3
"""Convert SVFN v2 faces to v3, or re-layout v3 faces into another profile, and prove the pixels did not change.

    svf2to3.py IN OUT [--profile P | --units R,W,T,O] [--box x|y|full] [--jset-version 1|2|auto] [--check]
    svf2to3.py --tree SRC DST [same options]

This is the only place that reads v2. --jset-version (default 1: v2 is an exception for memory-constrained targets, spec
amendment 3) picks the JSET block version of a jamo-set face: a v1 block is written as v2 when 2 (or auto: v2 when the
v1 block is at least jamoset.JSET_V2_MIN_SAVING bytes larger) says so, with its plane-15 pieces renumbered; a v2 block
is written as v1 (piece numbers kept) by 1, and stays v2 under 2 or auto. --check compares the output with the input
through svfline.Face: the same glyphs, metrics and cells for every code point outside plane 15 and every composed
syllable, and the plane-15 pieces as a multiset. Stdlib only.
"""
import argparse
import os
import signal
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jamoset  # noqa: E402
import svfline  # noqa: E402

COMPOSED = tuple(range(0xAC00, 0xD7A4)) + tuple(range(0x3131, 0x3164))


V2_VERSION = 2
V2_HEADER = "<4sHHBBHHBBBBHIII"      # bytes 0..35 of a v2 header (the code point table offset is the u32 at 32)
V2_HEADER_SIZE = 36


def _parse_v2(data):
    """An SVFN v2 file: header fields, glyph cells and metrics by code point, and the JSET block bytes (or None)."""
    if len(data) < V2_HEADER_SIZE:
        raise ValueError("not an SVFN v2 font: shorter than its header")
    (magic, version, flags, bpp, shadow, codepage, count, cw, ch, ascent, r0, r1, metrics_off, data_off,
     data_size) = struct.unpack_from(V2_HEADER, data)
    if magic != jamoset.MAGIC or version != V2_VERSION:
        raise ValueError("not an SVFN v2 or v3 font")
    (cmap_off,) = struct.unpack_from("<I", data, V2_HEADER_SIZE - 4)
    if bpp not in (1, 2, 8) or not cw or not ch:
        raise ValueError("SVFN v2: bad bpp or cell size")
    f = jamoset.Svfn()
    f.version, f.layout = 2, None
    f.metrics_ok = bool(flags & jamoset.FLAG_VARIABLE) and metrics_off >= V2_HEADER_SIZE and \
        metrics_off + 4 * count <= len(data)
    f.flags, f.bpp, f.cell_w, f.cell_h, f.ascent, f.count = flags, bpp, cw, ch, ascent, count
    # Header bytes 17 and 18: the per-glyph dy range (signed). f.dy holds the glyphs whose metrics byte 3 is not 0;
    # f.metrics stays (advance, ink x, ink w).
    f.dy_min, f.dy_max = struct.unpack_from("<bb", data, 17)
    pitch = (cw * bpp + 7) // 8
    stride = pitch * ch
    if cmap_off + 8 * count > len(data) or data_off + data_size > len(data) or data_size < count * stride:
        raise ValueError("SVFN v2: a table is outside the file")
    f.glyphs, f.metrics, f.dy = {}, {}, {}
    for k in range(count):
        cp, idx = struct.unpack_from("<II", data, cmap_off + 8 * k)
        if idx >= count:
            raise ValueError(f"SVFN v2: code point {cp:#x} names glyph {idx} of {count}")
        f.glyphs[cp] = data[data_off + idx * stride:data_off + (idx + 1) * stride]
        if f.metrics_ok:
            adv, ix, iw, dy = struct.unpack_from("<BbBb", data, metrics_off + idx * 4)
            f.metrics[cp] = (adv, ix, iw)
            if dy:
                f.dy[cp] = dy
    f.jset = None
    if flags & jamoset.FLAG_JAMO:
        start = cmap_off + 8 * count
        end = len(data)
        for off in ((metrics_off if flags & jamoset.FLAG_VARIABLE else 0), data_off):
            if start <= off < end:
                end = off
        f.jset = data[start:end]
    return f


def _parse(data):
    """A v2 or v3 file as a jamoset.Svfn; ValueError on anything else."""
    if len(data) < 6 or data[:4] != jamoset.MAGIC:
        raise ValueError("not an SVFN font")
    v = struct.unpack_from("<H", data, 4)[0]
    if v == V2_VERSION:
        return _parse_v2(data)
    if v == jamoset.VERSION:
        return jamoset.parse_svfn(data)
    raise ValueError(f"SVFN version {v}: only 2 and 3 are read here")


def _block_version(jset):
    return None if jset is None else struct.unpack_from("<H", jset, 4)[0]


def jset_version(jset):
    """The version word of the JSET block @p jset (1, 2 or 3), None for no block."""
    return _block_version(jset)


def _jset_sizes(t, version, block):
    """(v1 bytes, v2 bytes or None when pack refuses) of the Tables @p t whose block @p block is in @p version."""
    v1 = len(block) if version == 1 else len(jamoset.pack_v1(t, True))
    if version == 2:
        return v1, len(block)
    try:
        return v1, len(jamoset.pack(t, True).block)
    except ValueError:
        return v1, None


def convert_info(data, profile, box=None, jset_version=1, jset_big=False):
    """convert() and what it did to the JSET block: (bytes, info), info None for a face without a (valid) block, else
    {"version": written version, "v1": v1 bytes, "v2": v2 bytes or None when the face has no v2 form, "bytes": block
    length}. A version 3 (JMAP) block is copied verbatim whatever @p jset_version says (v1 and v2 are None then).
    @p jset_big: a re-encoded v1 / v2 block may exceed the standard JSET limits (jamoset.pack_jset big)."""
    if jset_version not in jamoset.JSET_VERSIONS:
        raise ValueError(f"JSET version {jset_version!r} is not 1, 2 or auto")
    f = _parse(data)
    pr = jamoset.profile_of(profile, box)
    jset = f.jset
    t = None
    if jset is not None:           # a v2-file block that fails validation is dropped, as a v3 one is by the parser
        try:
            t = jamoset.unpack(jset)
            n = jamoset._jset_block_size(jset)      # by the block's own version (P18)
            jset = jset[:n] if len(jset) >= n else None
        except (ValueError, IndexError, TypeError, struct.error):
            jset = None
    glyphs, raw_metrics, raw_dy = f.glyphs, f.metrics, f.dy
    info = None
    if jset is not None:
        if isinstance(t, jamoset.Jmap):
            fb = t.fallback
            if not jset_big and fb is not None and jamoset.needs_big(fb):     # PR-16: its BIG fallback is a write too
                jamoset._check_counts(fb.lc, fb.tc, fb.ni, fb.nm, fb.nf)      # ValueError with the --jset-big hint
            packed = jamoset.Packed(jset, jamoset.IdentityMap())     # a version 3 region is copied verbatim, never re-encoded
        elif _block_version(jset) == 1:
            packed = jamoset.pack_jset(t, jset_version, jset_big)   # ValueError (compat no set holds, R4): the face fails
        elif jset_version == 1:
            packed = jamoset.pack_jset(t, 1, jset_big)         # R10: v2 -> v1 only when asked, piece numbers kept
        else:
            if not jset_big and jamoset.needs_big(t):          # PR-16: a verbatim copy is a write too
                jamoset._check_counts(t.lc, t.tc, t.ni, t.nm, t.nf)      # ValueError with the --jset-big hint
            packed = jamoset.Packed(jset, jamoset.IdentityMap())
        jset = packed.block
        # ONE old -> new code point map from the glyph keys, applied to glyphs, metrics and dy alike: unused pieces are
        # numbered by rank among a dict's keys, so separate calls on the sparser metrics / dy dicts would disagree
        keys = list(glyphs)
        cpmap = dict(zip(keys, jamoset.renumber_glyphs({k: None for k in keys}, packed.piece_map)))
        glyphs = {cpmap[k]: glyphs[k] for k in keys}
        raw_metrics = {cpmap[k]: raw_metrics[k] for k in keys if k in raw_metrics}
        raw_dy = {cpmap[k]: raw_dy[k] for k in keys if k in raw_dy}
        v = _block_version(jset)
        if isinstance(t, jamoset.Jmap):
            v1 = v2 = None            # a JMAP block has no set-table forms to size
        else:
            v1, v2 = _jset_sizes(t, v, jset)
        info = {"version": v, "v1": v1, "v2": v2, "bytes": len(jset)}
        if isinstance(t, jamoset.Jmap) and t.list_mode:
            info["list"] = True        # a LIST region (flag 0x08) is copied verbatim like any version 3 block
        if v == 3:
            # a JMAP region is copied verbatim whatever was asked. Library callers: True when @p jset_version is not 1 (the
            # default, so an explicit 1 cannot be told from none); main() also sets it for an explicit --jset-version 1.
            info["version_ignored"] = jset_version != 1
    cps = sorted(glyphs)
    cells = [glyphs[cp] for cp in cps]
    cmap = [(cp, i) for i, cp in enumerate(cps)]
    lo, hi = f.dy_min, f.dy_max
    dy_ok = f.metrics_ok and lo <= 0 <= hi and -lo <= f.cell_h and hi <= f.cell_h
    if not dy_ok:
        lo = hi = 0
    metrics = None
    if f.metrics_ok:
        metrics = []
        for cp in cps:
            a, bx, iw = raw_metrics[cp]
            d = raw_dy.get(cp, 0)
            metrics.append((a, bx, iw, d if dy_ok and lo <= d <= hi else 0))
    out = jamoset.pack_svfn(f.cell_w, f.cell_h, f.ascent, f.bpp, f.flags & jamoset.FLAG_MARKS_AT_ORIGIN, cells, cmap,
                            metrics, jset, (lo, hi), pr)
    return out, info


def convert(data, profile, box=None, jset_version=1, jset_big=False):
    """The face @p data (v2 or v3) packed in @p profile (box policy @p box when given): same pixels, glyphs in code
    point order, the metrics and dy a reader would use (no table stays no table; dy 0 outside a valid range). The JSET
    block: a v1 block becomes pack_jset(unpack(block), @p jset_version) with the plane-15 pieces renumbered by its map;
    a v2 block is kept unless @p jset_version is 1 (then v1, piece numbers kept); a block unpack refuses is dropped.
    ValueError when the block cannot be written in the version asked (pack's compat refusal, naming the code point)."""
    return convert_info(data, profile, box, jset_version, jset_big)[0]


def _face(data):
    f = _parse(data)
    t = None
    if f.jset is not None:
        try:
            t = jamoset.unpack(f.jset)
        except ValueError:
            t = None
    return svfline.Face.from_svfn(f, tables=t)


def _plane15(cp):
    return jamoset.PIECE_BASE <= cp < jamoset.PIECE_BASE + 0x10000


def check(a, b):
    """check_info(a, b)[0]: the number of code points compared."""
    return check_info(a, b)[0]


def check_info(a, b):
    """Compare two faces through svfline.Face: every code point outside plane 15 and every composed syllable and compat
    jamo by code point (has, metrics, cell), the plane-15 pieces as a sorted multiset of (metrics, cell), since a JSET
    version change renumbers them. Returns (code points compared, composed_skipped); composed_skipped is True when both
    faces carry a JSET block the parser refused (a named piece has no glyph): no syllable or compat jamo is composed
    then, so only the faces' own glyphs were compared. AssertionError names the first difference."""
    fa, fb = _face(a), _face(b)
    bad = [getattr(_parse(x), "jset_bad", False) for x in (a, b)]
    for name in ("bpp", "cell_w", "cell_h", "ascent", "has_metrics", "dy_min", "dy_max"):
        if getattr(fa, name) != getattr(fb, name):
            raise AssertionError(f"{name}: {getattr(fa, name)} != {getattr(fb, name)}")
    if (fa.flags ^ fb.flags) & jamoset.FLAG_MARKS_AT_ORIGIN:
        raise AssertionError("flag marks-at-origin differs")
    if (fa.tables is None) != (fb.tables is None):
        raise AssertionError("one face has a jamo set and the other has not")
    pieces = []
    for f in (fa, fb):
        pieces.append(sorted((f.metrics(cp), bytes(f.cell(cp))) for cp in f.glyphs if _plane15(cp)))
    if pieces[0] != pieces[1]:
        na, nb = len(pieces[0]), len(pieces[1])
        why = f"{na} != {nb} glyphs" if na != nb else \
            f"entry {next(i for i, (x, y) in enumerate(zip(*pieces)) if x != y)} differs"
        raise AssertionError(f"plane-15 multiset of (metrics, cell): {why}")
    cps = sorted({cp for cp in set(fa.glyphs) | set(fb.glyphs) if not _plane15(cp)} |
                 (set(COMPOSED) if fa.tables else set()))
    for cp in cps:
        if fa.has(cp) != fb.has(cp):
            raise AssertionError(f"U+{cp:04X}: present in one face only")
        if not fa.has(cp):
            continue
        if fa.metrics(cp) != fb.metrics(cp):
            raise AssertionError(f"U+{cp:04X}: metrics {fa.metrics(cp)} != {fb.metrics(cp)}")
        if fa.cell(cp) != fb.cell(cp):
            raise AssertionError(f"U+{cp:04X}: cell differs")
    skipped = fa.tables is None and fb.tables is None and any(bad)
    return len(cps) + len(pieces[0]), bool(skipped)


def _data_size(data):
    if data[4:6] == b"\x03\x00":
        return struct.unpack_from(jamoset.HEADER3, data)[16]
    return struct.unpack_from(V2_HEADER, data)[14]


def _write_checked(data, dst, profile, box, do_check, jset_version=1, jset_big=False):
    """Convert @p data into a temporary file beside @p dst, check it there, rename over @p dst. Returns (the output
    bytes, convert_info's info); raises ValueError (invalid input, or a JSET block pack refuses) or AssertionError
    (check) with @p dst untouched."""
    out, info = convert_info(data, profile, box, jset_version, jset_big)
    composed_skipped = False
    d = os.path.dirname(os.path.abspath(dst))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".svf2to3-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(out)
        if do_check:
            with open(tmp, "rb") as fh:
                _, skipped = check_info(data, fh.read())
            composed_skipped = skipped
        os.chmod(tmp, 0o644)
        os.replace(tmp, dst)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return out, info, composed_skipped


def _jset_text(info, skipped=False):
    note = " composed=unchecked(jamo set unusable: a named piece has no glyph)" if skipped else ""
    if info is None:
        return note
    if info["version"] == jamoset.JMAP_VERSION:
        return f" jset=3 jmap={info['bytes']}" + (" list=1" if info.get("list") else "") + note
    v2 = "-" if info["v2"] is None else info["v2"]
    return f" jset={info['version']} jset_v1={info['v1']} jset_v2={v2}" + note


def _jset_version_arg(s):
    if s == "auto":
        return s
    if s in ("1", "2"):
        return int(s)
    raise argparse.ArgumentTypeError(f"{s!r} is not 1, 2 or auto")


def _faces(src):
    """(relative paths of the *.SVF files below @p src, [(relative path, error)] of what could not be listed)."""
    found, errors = [], []

    def onerror(e):
        errors.append((os.path.relpath(e.filename, src) if e.filename else ".", e.strerror or str(e)))

    for root, dirs, files in os.walk(src, onerror=onerror):
        dirs.sort()
        for n in sorted(files):
            if n.lower().endswith(".svf"):
                found.append(os.path.relpath(os.path.join(root, n), src))
    return found, errors


def _on_sigterm(signum, frame):
    raise SystemExit(128 + signum)      # unwinds through _write_checked's cleanup, which removes the temp file


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs=2, metavar="PATH", help="IN OUT, or SRC DST with --tree")
    ap.add_argument("--tree", action="store_true", help="convert every *.SVF below SRC into DST")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--profile", default=None, help="mcu-strict, default, dos, wasm, full or simd16 (default: default)")
    g.add_argument("--units", metavar="R,W,T,O", help="log2 record, row, table units and offset width 16 or 32")
    ap.add_argument("--box", choices=jamoset.BOXES, default=None)
    ap.add_argument("--jset-version", type=_jset_version_arg, default=None, metavar="1|2|auto",
                    help="JSET block version of a jamo-set face (default 1; 2 for a memory-constrained target; auto: "
                         f"v2 when the v1 block is at least {jamoset.JSET_V2_MIN_SAVING} bytes larger); a JMAP block "
                         "(version 3) is copied verbatim and a note says so")
    ap.add_argument("--jset-big", action="store_true",
                    help="allow a re-encoded JSET block over the standard limits (up to 19 x 28 classes, 128/128/64 "
                         "sets); readers need SVF_JSET_BIG")
    ap.add_argument("--check", action="store_true", help="compare the output with the input through svfline")
    args = ap.parse_args(argv)
    asked = args.jset_version
    if args.jset_version is None:
        args.jset_version = 1
    signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        profile = jamoset.profile_of(args.units or args.profile or "default", args.box)
    except ValueError as e:
        print(f"svf2to3: {e}", file=sys.stderr)
        return 2
    a, b = args.paths
    if not args.tree:
        try:
            with open(a, "rb") as fh:
                data = fh.read()
            out, info, skipped = _write_checked(data, b, profile, None, args.check, args.jset_version, args.jset_big)
        except (ValueError, OSError, struct.error) as e:
            print(f"svf2to3: {a}: {e}", file=sys.stderr)
            return 2
        except AssertionError as e:
            print(f"svf2to3: {a}: check failed: {e}", file=sys.stderr)
            return 1
        if info is not None and info["version"] == 3 and asked is not None:
            info["version_ignored"] = True
            print(f"svf2to3: {a}: note: --jset-version applies to nothing here: a JMAP block (version 3) is copied "
                  "verbatim", file=sys.stderr)
        print(f"{b} in={len(data)} out={len(out)} data_in={_data_size(data)} data_out={_data_size(out)}"
              + _jset_text(info, skipped))
        return 0
    if not os.path.isdir(a):
        print(f"svf2to3: {a}: not a directory", file=sys.stderr)
        return 2
    tot = [0, 0, 0, 0]
    jtot = {1: [0, 0], 2: [0, 0], 3: [0, 0]}       # version -> [faces, JSET bytes written]
    faces, errors = _faces(a)
    bad = 0
    status = 0
    for rel, why in errors:
        print(f"{rel} FAIL unreadable: {why}", flush=True)
        bad += 1
        status = 2
    done = 0
    for rel in faces:
        try:
            with open(os.path.join(a, rel), "rb") as fh:
                data = fh.read()
            out, info, skipped = _write_checked(data, os.path.join(b, rel), profile, None, args.check, args.jset_version, args.jset_big)
        except (ValueError, OSError, struct.error) as e:
            print(f"{rel} FAIL {e}", flush=True)
            bad += 1
            status = 2
            continue
        except AssertionError as e:
            print(f"{rel} FAIL check: {e}", flush=True)
            bad += 1
            status = max(status, 1)
            continue
        row = (len(data), len(out), _data_size(data), _data_size(out))
        print("%s in=%d out=%d data_in=%d data_out=%d" % ((rel,) + row) + _jset_text(info, skipped), flush=True)
        done += 1
        if info is not None:
            jtot[info["version"]][0] += 1
            jtot[info["version"]][1] += info["bytes"]
            if info["version"] == 3 and asked is not None:
                info["version_ignored"] = True
                print(f"{rel}: note: --jset-version applies to nothing here: a JMAP block (version 3) is copied verbatim",
                      file=sys.stderr, flush=True)
        for i, v in enumerate(row):
            tot[i] += v
    print("total faces=%d in=%d out=%d data_in=%d data_out=%d v3_faces=%d v3_jset=%d v1_faces=%d v1_jset=%d v2_faces=%d v2_jset=%d failed=%d"
          % ((done,) + tuple(tot) + tuple(jtot[3]) + tuple(jtot[1]) + tuple(jtot[2]) + (bad,)), flush=True)
    return status


if __name__ == "__main__":
    sys.exit(main())
