#!/usr/bin/env python3
"""The facts read back from a produced face and the quality numbers against a reference.

`face_facts` reads an SVFN v3 file the way the page reports it; `composed_syllables` composes every syllable with the
engine's own rule; `reference_targets` builds the reference the fit is scored against (an outline font rendered and
binarised at 1 bpp, its whole syllables quantised at 2 bpp, or the precomposed syllables of an SVF file);
`compare` scores the face's own composition against those targets and `measure` ties it together for a step.

The library assumes `maker/` and `tools/` are on sys.path (the entry points set it).
"""

import detect
import jamoaa
import jamoset
import jamofit

# KS X 1001 Hangul (2,350 syllables), the range the maker's default covers; a set, looked up once per comparison.
KS2350 = frozenset(detect.KS2350)


def face_facts(data):
    """The facts of an SVFN v3 face (Shared data shapes' `facts`); raises ValueError for anything else.

    A JSET the renderer would not use (it does not unpack, or a piece it names has no glyph) leaves `jset` None: the
    face loads as a plain precomposed SVFN (spec/SVF.md's rule), which is not an error. A structurally damaged face
    (magic or version, a header, table or glyph record past the end of the file, a bpp that is not 1, 2 or 8: every
    check `jamoset.parse_svfn` makes) is one, and so is a v2 or v1 face: the maker writes v3 only.
    """
    try:
        face = jamoset.parse_svfn(data)
    except ValueError as exc:
        raise ValueError("not an SVFN v3 font: %s" % exc) from None
    t = detect.usable_jset(face)
    if t is None:
        jset = None
    elif isinstance(t, jamoset.Jmap):      # a JMAP has no sets or classes (None); its piece counts per plane are "pieces"
        mode = detect.jmap_mode(face.jset)
        if t.list_mode:                    # a LIST has no planes (PI = PM = PF = 0): "pieces" None, "pool" its distinct pieces
            # the distinct pieces the block names: its entries' fields and its own compat entries (not the fallback's)
            pool = len({n for e in t.entries.values() for n in e if n != jamoset.BLANK}
                       | {n for n in t.block_compat if n != jamoset.BLANK})
            jset = {"sets": None, "classes": None, "pieces": None, "jmap": True, "jmap_mode": mode, "pool": pool}
        else:
            jset = {"sets": None, "classes": None, "pieces": [t.pi, t.pm, t.pf], "jmap": True, "jmap_mode": mode}
    else:
        jset = {"sets": [t.ni, t.nm, t.nf], "classes": [t.lc, t.tc]}
    return {"version": face.version, "flags": face.flags, "variable": bool(face.flags & jamoset.FLAG_VARIABLE),
            "jamo": bool(face.flags & jamoset.FLAG_JAMO), "bpp": face.bpp, "cell": [face.cell_w, face.cell_h],
            "ascent": face.ascent, "glyphs": face.count, "jset": jset, "bytes": len(data)}


def composed_syllables(face):
    """{syllable index: the face's own composition of it} for all 11,172 syllables (bytes, cell sized). Raises
    ValueError when the face has no usable jamo set (detect.usable_jset). A syllable the face does not compose (a miss of
    a JMAP face) is absent from the result."""
    t = detect.usable_jset(face)
    if t is None:
        raise ValueError("the face has no usable jamo set")
    out = {}
    for s in range(11172):
        cell = jamoset.compose(face, t, 0xAC00 + s)
        if cell is not None:            # a JMAP-only miss is not composed (PR-5): left out
            out[s] = cell
    return out


def reference_targets(reference, src_path, size, face):
    """The targets a step's face is scored against, keyed by syllable index.

    `"outline"` is the source outline font rendered at `size` px: binarised at 1 bpp, or (2 bpp) every syllable it
    draws rendered whole and quantised to levels. The outline reference takes the face's header ascent as the Hangul
    baseline (`jamoaa.frame`'s baseline). That holds for every face the maker writes (the fit and composite routes both
    put the Hangul baseline at the header ascent), but not for a repo face whose Latin was rebuilt after the fit
    (GOTHA16 has ascent 15 with its Hangul baseline on row 14), which would be scored against a shifted reference.
    `"svf"` is a precomposed SVF file's own syllables (a v3 or v2 file).
    """
    w, h = face.cell_w, face.cell_h
    if reference == "outline":
        if face.bpp == 2:
            of = jamoaa.OutlineFace(src_path, size)
            cps = [0xAC00 + s for s in range(11172) if of.has(0xAC00 + s)]
            ox, oy, _ = jamoaa.frame(of, cps, w, h, face.ascent)
            return {cp - 0xAC00: jamoaa.direct_levels(of, cp, ox, oy, w, h) for cp in cps}
        return jamoaa.outline_targets(src_path, size, (w, h), face.ascent, "threshold", 0.5)[0]
    if reference == "svf":
        if face.bpp != 1:
            raise ValueError("an SVF reference scores 1 bpp faces only (this face is %d bpp)" % face.bpp)
        with open(src_path, "rb") as f:
            return jamoset.svf_targets(detect.read_svf(f.read()))   # the source may be v2
    raise ValueError(f"unknown reference {reference!r}")


def _mean(vals):
    return round(sum(vals) / len(vals), 4) if vals else None


def compare(face, targets):
    """The face's composition against @p targets: mean agreement over the target syllables (`all`), the same over the
    KS X 1001 syllables, and how many were compared. 1 bpp scores IoU (1 is exact); 2 bpp scores the mean absolute
    level error over the cell's levels, 0 is exact. Empty targets score None. A target syllable the face does not compose
    (a JMAP-only miss) is skipped, and `compared` counts the scored ones; none scored gives None as for empty targets. Raises ValueError when the face has no
    usable jamo set (detect.usable_jset)."""
    if not targets:
        return {"all": None, "ks2350": None, "compared": 0}
    w, h = face.cell_w, face.cell_h
    t = detect.usable_jset(face)
    if t is None:
        raise ValueError("the face has no usable jamo set")
    vals, ks_vals = [], []
    for s, target in targets.items():
        cell = jamoset.compose(face, t, 0xAC00 + s)
        if cell is None:
            continue
        if face.bpp == 2:
            got = jamoaa.unpack_levels(cell, w, h, 2)
            score = sum(abs(a - b) for a, b in zip(target, got)) / float(w * h) / 3
        else:
            got = jamoset.glyph_gint(cell, w, h)
            score = jamofit.iou(target, got)
        vals.append(score)
        if 0xAC00 + s in KS2350:
            ks_vals.append(score)
    if not vals:
        return {"all": None, "ks2350": None, "compared": 0}
    return {"all": _mean(vals), "ks2350": _mean(ks_vals), "compared": len(vals)}


def measure(face_bytes, reference, src_path, size):
    """The quality dict of a produced face, or None when there is no reference or the face is not a usable jamo set
    (no JSET, one the renderer would not use, or a piece with no glyph): it is then scored as precomposed, never an
    error (a KeyError here would escape a worker's step)."""
    if reference is None:
        return None
    face = jamoset.parse_svfn(face_bytes)
    if detect.usable_jset(face) is None:
        return None
    return compare(face, reference_targets(reference, src_path, size, face))
