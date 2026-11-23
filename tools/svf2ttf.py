#!/usr/bin/env python3
"""svf2ttf.py - an SVF face back to a bitmap font: a TrueType font (pixel outlines + an embedded bitmap strike) or a BDF.

  svf2ttf.py ttf FACE.SVF OUT.ttf [--family F] [--style S] [--version V] [--ppem N] [--threshold C]
                                  [--licence FILE|none] [--no-strike] [--apple]
  svf2ttf.py bdf FACE.SVF OUT.bdf [--family F] [--style S] [--version V] [--ppem N] [--licence FILE|none] [--bpp1]
  svf2ttf.py compare A.SVF B.SVF
  svf2ttf.py cps FACE.SVF            prints the face's code points as mkfont.py --unicode ranges (20-7e,ac00-d7a3,...)

The face is read as the C library loads it (svfline.Face): a precomposed face gives its glyphs, a jamo set gives every
syllable its JSET composes (all 11,172 for a full table, as svfline draws them, through jamoset.compose) and the
compatibility jamo its table maps, plus its other glyphs. The jamo pieces themselves (U+F0000 + n) are not exported, and
no conjoining-jamo (U+1100) shaping, GSUB or GPOS is written: the output is a precomposed font.

Every glyph is placed exactly as svfline draws it: the cell's left column at the pen (a combining mark U+0300..U+036F of
a face with flags bit 2 and a negative bearing_x: min(-bearing_x, cell_w) columns left of it, and advance 0), its top row
ascent - dy rows above the baseline; the advance is the face's metrics advance (a composed syllable the JSET advance or
the cell width).

ttf: unitsPerEm = ppem * 64 (one pixel = 64 units; ppem defaults to the cell height, so ascent + descent = the em).
  - glyf: the pixels with coverage >= --threshold (default 128: every 1 bpp pixel, 2 bpp levels 2 and 3, 8 bpp bytes
    >= 128, the C library's mono-target rule) traced into contours along the pixel edges (outer contours clockwise,
    holes counter-clockwise, collinear points dropped, diagonal neighbours kept apart), so the outline covers exactly
    those pixels at ppem and at whole multiples of it. No hinting instructions.
  - EBLC/EBDT: one strike at ppem x ppem with the face's own bit depth (1, 2 or 8), every glyph's pixels cut to its ink
    box (image format 1: small metrics, byte-aligned rows; index format 1), its advance and bearings in the metrics.
    A renderer that uses embedded bitmaps (FreeType, Windows GDI/DirectWrite) draws the face's own pixels and levels at
    ppem, and the outlines at other sizes. --no-strike leaves it out; --apple adds the same strike as bloc/bdat.
  - cmap (format 4, and 12 when a code point is past U+FFFF), hmtx (advance * 64, lsb = the outline's x minimum),
    hhea / OS/2 typo ascender and descender = the face's ascent and cell height - ascent (USE_TYPO_METRICS), OS/2 win
    ascent / descent = the larger of those and the ink's reach (a dy may take ink past the cell), post format 3,
    head (fontRevision = --version), maxp, gasp, and a .notdef box.
  - name: family (--family, default "<FACE STEM> SVF": never the source font's name, which an OFL Reserved Font Name
    may forbid), style (--style, default Regular; Bold / Italic / Bold Italic also set the OS/2 and head style bits),
    version, a description naming FACE.SVF, its cell, bit depth and kind, and the licence (find_licence): --licence FILE
    (and the licence files it names); else for a face inside a repository's svf/ tree the files its row of
    web/LICENCES.tsv names (no row: an error); else the *.TXT beside the face whose title line names the face's file or
    a pattern matching it (and the licence files it names), else the licence column of a FACES.TSV beside it. The texts
    go into the licence description (name 13), the copyright paragraph above the OFL header into name 0 (copyright_of),
    the OFL URL into name 14 when an OFL text is embedded. --licence none writes no licence text.
  - head created / modified: $SOURCE_DATE_EPOCH when set, else now.

bdf: BDF 2.1 (1 bpp) or 2.3 (2 and 8 bpp: SIZE's fourth field is the bit depth; --bpp1 writes 1 bpp by --threshold),
  ISO10646-1, one glyph a code point with BBX = its ink box (a blank glyph 0 x 0) and DWIDTH = its advance,
  FONT_ASCENT / FONT_DESCENT the face's, PIXEL_SIZE ppem, COPYRIGHT / NOTICE from the licence note. FreeType (and so
  mkfont.py, at the BDF's pixel size) reads it.

compare: every code point either face has, compared as svfline places it (pixels with their level relative to the
  pen and the baseline, and the advance). Prints the counts and the first differing code points; mismatches = glyphs
  whose pixels or advance differ plus inked glyphs only one face has (blank glyphs only one face has, as mkfont.py drops
  every blank glyph but the spaces, are counted apart). Exit 0 when mismatches is 0, else 1.
"""

import argparse
import datetime
import fnmatch
import glob
import os
import re
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:  # python -I drops the script's directory
    sys.path.insert(0, HERE)
import jamoset  # noqa: E402
import svfline  # noqa: E402

UNITS = 64                     # font units per pixel
DEFAULT_THRESHOLD = 128        # svfline Target mono threshold
OFL_URL = "https://openfontlicense.org"


# ---- the face as svfline draws it ----------------------------------------------------------------------------------

def face_cps(face):
    """The code points @p face draws (svfline.Face.has), in order: its glyphs below the jamo-piece plane, and with a JSET
    every syllable it composes and the compatibility jamo it maps."""
    cps = {cp for cp in face.glyphs if cp < jamoset.PIECE_BASE}
    if face.tables:
        cps.update(cp for cp in range(0xAC00, 0xD7A4) if face.composed(cp))
        cps.update(cp for cp in range(0x3131, 0x3164) if face.composed(cp))
    return sorted(cp for cp in cps if face.has(cp))


def _levels(face, cp):
    """The cell of @p cp as rows of stored values (1 bpp 0/1, 2 bpp 0..3, 8 bpp 0..255)."""
    cell, p = face.cell(cp), face.pitch
    rows = []
    for y in range(face.cell_h):
        row = cell[y * p:(y + 1) * p]
        if face.bpp == 1:
            rows.append([row[x >> 3] >> (7 - (x & 7)) & 1 for x in range(face.cell_w)])
        elif face.bpp == 2:
            rows.append([row[x >> 2] >> (6 - 2 * (x & 3)) & 3 for x in range(face.cell_w)])
        else:
            rows.append(list(row[:face.cell_w]))
    return rows


def glyph_pixels(face, cp):
    """(advance, {(x, y): level}) of @p cp as svfline places it: x from the pen, y rows below the baseline (the row just
    above the baseline is -1), level the stored value (> 0)."""
    adv, bx, _, dy = face.metrics(cp)
    if svfline.is_mark_default(cp):
        origin = min(-bx, face.cell_w) if face.flags & jamoset.FLAG_MARKS_AT_ORIGIN and bx < 0 else 0
        adv = 0
    else:
        origin = 0
    top = -face.ascent + dy
    px = {}
    for r, row in enumerate(_levels(face, cp)):
        for c, v in enumerate(row):
            if v:
                px[(c - origin, top + r)] = v
    return adv, px


def coverage_of(face, level):
    """The 0..255 coverage of a stored @p level (svfline's GRAY8 rule)."""
    return 255 if face.bpp == 1 else level * 85 if face.bpp == 2 else level


# ---- pixel outlines (ported from johab-fonts tools/bdf2ttf.py) ------------------------------------------------------

def contours(px):
    """Closed polygons around the pixel set @p px ({(x, y)}: a pixel's lower-left corner, y up): outer contours
    clockwise, holes counter-clockwise (the ink always on the right), collinear points dropped; at a pinch point (two
    pixels touching at a corner) the walk turns right, so the pixels stay apart."""
    edges = {}
    for (x, y) in px:
        if (x - 1, y) not in px:
            edges.setdefault((x, y), []).append((x, y + 1))
        if (x, y + 1) not in px:
            edges.setdefault((x, y + 1), []).append((x + 1, y + 1))
        if (x + 1, y) not in px:
            edges.setdefault((x + 1, y + 1), []).append((x + 1, y))
        if (x, y - 1) not in px:
            edges.setdefault((x + 1, y), []).append((x, y))
    polys = []
    while edges:
        start = min(edges)
        p, poly, d = start, [start], None
        while True:
            outs = edges[p]
            if len(outs) > 1 and d is not None:
                outs.sort(key=lambda q: d[0] * (q[1] - p[1]) - d[1] * (q[0] - p[0]))   # right turn first
                q = outs.pop(0)
            else:
                q = outs.pop()
            if not outs:
                del edges[p]
            d = (q[0] - p[0], q[1] - p[1])
            p = q
            if p == start:
                break
            poly.append(p)
        polys.append(poly)
    out = []
    for poly in polys:
        n = len(poly)
        keep = [poly[i] for i in range(n)
                if (poly[i][0] - poly[i - 1][0]) * (poly[(i + 1) % n][1] - poly[i][1])
                - (poly[i][1] - poly[i - 1][1]) * (poly[(i + 1) % n][0] - poly[i][0]) != 0]
        if len(keep) >= 3:
            out.append(keep)
    return out


# ---- licence note -------------------------------------------------------------------------------------------------

def _title_patterns(line):
    """The file patterns of a note's title line: 'Neo Dunggeunmo faces (NEODG*.SVF, NEO*X?.SVF)' -> ['NEODG*.SVF',
    'NEO*X?.SVF']; a pattern without an extension gets '.SVF'."""
    m = re.search(r"\(([^)]*)\)\s*$", line.strip())
    if not m:
        return []
    out = []
    for part in m.group(1).split(","):
        part = part.strip()
        if not part or " " in part:
            continue
        out.append(part if "." in part else part + ".SVF")
    return out


def repo_licences(face_path):
    """The licence files web/LICENCES.tsv gives a face inside a repository's svf/ tree: (True, [paths]) for a face under
    such a tree ([] when no row matches it), (False, []) for a face outside one. The first row whose glob matches the
    face's path relative to svf/ wins (fnmatch, case-sensitive, as web/mkindex.py reads it)."""
    path = os.path.abspath(face_path)
    d = os.path.dirname(path)
    while True:
        parent = os.path.dirname(d)
        if os.path.basename(d) == "svf" and os.path.isfile(os.path.join(parent, "web", "LICENCES.tsv")):
            rel = os.path.relpath(path, d).replace(os.sep, "/")
            with open(os.path.join(parent, "web", "LICENCES.tsv"), encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("#") or not line.strip():
                        continue
                    glob_, _, files = line.rstrip("\n").partition("\t")
                    if fnmatch.fnmatchcase(rel, glob_):
                        return True, [os.path.join(d, f) for f in files.split(",") if f]
            return True, []
        if parent == d:
            return False, []
        d = parent


def find_licence(face_path):
    """The licence files of the face at @p face_path: web/LICENCES.tsv for a face inside a repository's svf/ tree (see
    repo_licences); else the *.TXT beside the face whose title line names it (and the licence files that note names),
    else the licence column of a FACES.TSV beside it. Returns (inside the repository, [paths])."""
    inside, files = repo_licences(face_path)
    if inside:
        return True, files
    d, base = os.path.dirname(os.path.abspath(face_path)), os.path.basename(face_path).upper()
    seen = set()
    for txt in sorted(glob.glob(os.path.join(d, "*.TXT")) + glob.glob(os.path.join(d, "*.txt"))):
        if os.path.normcase(txt) in seen:
            continue
        seen.add(os.path.normcase(txt))
        try:
            with open(txt, encoding="utf-8") as fh:
                first = fh.readline()
        except (OSError, UnicodeDecodeError):
            continue
        if any(fnmatch.fnmatchcase(base, p.upper()) for p in _title_patterns(first)):
            return False, [txt] + licence_files_named(txt)
    tsv = os.path.join(d, "FACES.TSV")
    if os.path.exists(tsv):
        head = None
        with open(tsv, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#") or not line.strip():
                    continue
                cols = line.rstrip("\n").split("\t")
                if head is None:
                    head = cols
                    continue
                row = dict(zip(head, cols))
                if row.get("file", "").upper() == base and row.get("licence"):
                    lic = os.path.join(d, row["licence"])
                    return False, [lic] if os.path.exists(lic) else []
    return False, []


def licence_files_named(note):
    """The files beside @p note that its text names (OFL.TXT, OFLNANUM.TXT, ...), in the order named."""
    d = os.path.dirname(os.path.abspath(note))
    with open(note, encoding="utf-8") as fh:
        text = fh.read()
    out = []
    for name in re.findall(r"\b([A-Z0-9_-]+\.TXT)\b", text):
        path = os.path.join(d, name)
        if os.path.abspath(path) != os.path.abspath(note) and os.path.exists(path) and path not in out:
            out.append(path)
    return out


_OFL_HEADER = re.compile(r"^(-{5,}|SIL OPEN FONT LICENSE\b)", re.M)


def is_licence_text(text):
    """Whether @p text holds the SIL Open Font License itself (its header line)."""
    return re.search(r"^SIL OPEN FONT LICENSE\b", text, re.M) is not None


def copyright_of(texts):
    """The copyright line of the licence @p texts (note and licence files): from each text that holds the OFL (else from
    every text), the paragraphs above the OFL header that say "Copyright" or "(c)"; when none does, the first such
    paragraph of the licence file (an attribution, as Neo Dunggeunmo Pro's public-domain origin). Whitespace is collapsed;
    several distinct paragraphs are joined with "; "."""
    lic = [t for t in texts if is_licence_text(t)] or list(texts)
    heads = []
    for t in lic:
        m = _OFL_HEADER.search(t)
        heads.append(t[:m.start()] if m else t)
    found, first = [], []
    for h in heads:
        paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", h) if p.strip()]
        if paras and not first:
            first = [paras[0]]
        for p in paras:
            if re.search(r"copyright|\(c\)|\u00a9", p, re.I) and p not in found:
                found.append(p)
                break
    return "; ".join(found or first)


def licence_text(face_path, licence):
    """(licence description, copyright, licence URL or '') for the name table; @p licence: a path, 'none' or None
    (find_licence). A face inside a repository's svf/ tree that web/LICENCES.tsv does not cover is an error (ValueError)
    unless @p licence is given; a face outside gets a line saying its source font's licence applies, and a warning."""
    if licence == "none":
        return "", "", ""
    if licence:
        files = [licence] + licence_files_named(licence)
    else:
        inside, files = find_licence(face_path)
        if not files and inside:
            raise ValueError("%s is inside the repository's svf/ tree but web/LICENCES.tsv gives it no licence: add a "
                             "row there, or pass --licence FILE" % face_path)
    if not files:
        print("svf2ttf: no licence note found beside %s; the licence of its source font applies (--licence FILE)"
              % face_path, file=sys.stderr)
        return ("No licence note was found beside %s; the licence of the font it was made from applies."
                % os.path.basename(face_path)), "", ""
    texts = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            texts.append(fh.read().strip())
    if sum(is_licence_text(t) for t in texts) > 1:
        print("svf2ttf: %s: %d licence files found; all are embedded (pass --licence FILE to choose)"
              % (face_path, sum(is_licence_text(t) for t in texts)), file=sys.stderr)
    desc = "\n\n".join(texts)
    url = OFL_URL if any(is_licence_text(t) for t in texts) else ""
    return desc, copyright_of(texts), url


# ---- glyph table --------------------------------------------------------------------------------------------------

def glyph_name(cp):
    return "uni%04X" % cp if cp <= 0xFFFF else "u%05X" % cp


class Glyph:
    __slots__ = ("cp", "name", "adv", "px")

    def __init__(self, cp, adv, px):
        self.cp, self.name, self.adv, self.px = cp, glyph_name(cp), adv, px

    def box(self):
        """(x0, y0, x1, y1) of the ink, half-open, y down from the baseline; None when blank."""
        if not self.px:
            return None
        xs = [x for x, _ in self.px]
        ys = [y for _, y in self.px]
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def face_glyphs(face):
    out = []
    for cp in face_cps(face):
        adv, px = glyph_pixels(face, cp)
        out.append(Glyph(cp, adv, px))
    return out


def _pack_rows(g, depth):
    """The ink box of @p g as rows of @p depth-bit pixels, MSB first, each row padded to a byte."""
    x0, y0, x1, y1 = g.box()
    out = bytearray()
    for y in range(y0, y1):
        row = bytearray((((x1 - x0) * depth) + 7) // 8)
        for x in range(x0, x1):
            v = g.px.get((x, y), 0)
            if v:
                bit = (x - x0) * depth
                row[bit >> 3] |= v << (8 - depth - (bit & 7))
        out += row
    return out


def strike_tables(glyphs, ppem, depth, ascent, descent):
    """(EBLC, EBDT) bytes: one strike, glyph ids 1..len(glyphs) (.notdef is id 0 and has no bitmap), image format 1
    (small metrics, byte-aligned rows), index format 1."""
    data = bytearray(struct.pack(">L", 0x00020000))
    offs = []
    bx_min, rsb_min, bl_max, bl_min, wmax = 127, 127, -128, 127, 0
    for g in glyphs:
        offs.append(len(data))
        box = g.box()
        if g.adv > 255:
            raise ValueError("U+%04X: advance %d is past 255" % (g.cp, g.adv))
        if box is None:
            data += struct.pack(">BBbbB", 0, 0, 0, 0, g.adv)
        else:
            x0, y0, x1, y1 = box
            w, h = x1 - x0, y1 - y0
            data += struct.pack(">BBbbB", h, w, x0, -y0, g.adv)
            data += _pack_rows(g, depth)
            bx_min, rsb_min = min(bx_min, x0), min(rsb_min, g.adv - x1)
            bl_max, bl_min = max(bl_max, -y0), min(bl_min, -y1)
        wmax = max(wmax, g.adv)
    offs.append(len(data))
    if bl_max < bl_min:
        bx_min = rsb_min = bl_max = bl_min = 0
    first, last = 1, len(glyphs)
    hori = struct.pack(">bbBbbbbbbbbb", ascent, -descent, wmax, 1, 0, 0, bx_min, rsb_min, bl_max, bl_min, 0, 0)
    vert = struct.pack(">bbBbbbbbbbbb", ascent, -descent, wmax, 1, 0, 0, 0, 0, 0, 0, 0, 0)
    sub = struct.pack(">HHL", 1, 1, 0) + b"".join(struct.pack(">L", o) for o in offs)
    # index subtable header: indexFormat 1, imageFormat 1, imageDataOffset 0 (offsets are from the EBDT start)
    arr = struct.pack(">HHL", first, last, 8)
    table_size = len(arr) + len(sub)
    size = (struct.pack(">LLLL", 8 + 48, table_size, 1, 0) + hori + vert
            + struct.pack(">HHBBBb", first, last, ppem, ppem, depth, 1))
    eblc = struct.pack(">LL", 0x00020000, 1) + size + arr + sub
    return bytes(eblc), bytes(data)


def _style_bits(style):
    s = style.lower()
    bold, italic = "bold" in s, "italic" in s or "oblique" in s
    fs = (1 if italic else 0) | (32 if bold else 0) or 64
    mac = (1 if bold else 0) | (2 if italic else 0)
    return fs, mac, 700 if bold else 400


def _kind(face):
    return "jamo set" if face.tables else "precomposed"


def default_family(face_path):
    return os.path.splitext(os.path.basename(face_path))[0].upper() + " SVF"


def _timestamp():
    from fontTools.misc.timeTools import epoch_diff
    t = int(os.environ.get("SOURCE_DATE_EPOCH", time.time()))
    return t - epoch_diff


def build_ttf(face_path, out, family=None, style="Regular", version="1.000", ppem=None, threshold=DEFAULT_THRESHOLD,
              licence=None, strike=True, apple=False):
    """Write the TrueType font of the face at @p face_path to @p out; returns a summary dict."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import newTable
    from fontTools.ttLib.tables.DefaultTable import DefaultTable

    face = svfline.Face.load(face_path)
    ppem = ppem or face.cell_h
    if not 1 <= ppem <= 255:
        raise ValueError("ppem %d is not 1..255" % ppem)
    k = UNITS
    family = family or default_family(face_path)
    glyphs = face_glyphs(face)
    ascent, descent = face.ascent, face.cell_h - face.ascent
    order = [".notdef"] + [g.name for g in glyphs]

    glyf, hmtx = {}, {}
    nb_w, nb_h = max(2, face.cell_w // 2), max(3, ascent)
    pen = TTGlyphPen(None)
    for poly in ([(0, 0), (0, nb_h), (nb_w, nb_h), (nb_w, 0)], [(1, 1), (nb_w - 1, 1), (nb_w - 1, nb_h - 1), (1, nb_h - 1)]):
        pen.moveTo((poly[0][0] * k, poly[0][1] * k))
        for x, y in poly[1:]:
            pen.lineTo((x * k, y * k))
        pen.closePath()
    glyf[".notdef"] = pen.glyph()
    hmtx[".notdef"] = ((nb_w + 1) * k, 0)
    ink_top, ink_bottom = ascent, descent
    for g in glyphs:
        pen = TTGlyphPen(None)
        on = {(x, -y - 1) for (x, y), v in g.px.items() if coverage_of(face, v) >= threshold}
        xmin = None
        for poly in contours(on):
            pen.moveTo((poly[0][0] * k, poly[0][1] * k))
            for x, y in poly[1:]:
                pen.lineTo((x * k, y * k))
            pen.closePath()
            m = min(x for x, _ in poly)
            xmin = m if xmin is None else min(xmin, m)
        glyf[g.name] = pen.glyph()
        hmtx[g.name] = (g.adv * k, (xmin or 0) * k)
        box = g.box()
        if box:
            ink_top, ink_bottom = max(ink_top, -box[1]), max(ink_bottom, box[3])

    fb = FontBuilder(ppem * k, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({g.cp: g.name for g in glyphs})
    fb.setupGlyf(glyf)
    fb.setupHorizontalMetrics(hmtx)
    fb.setupHorizontalHeader(ascent=ascent * k, descent=-descent * k, lineGap=0)
    fs_sel, mac_style, weight = _style_bits(style)
    ps_name = re.sub(r"[^A-Za-z0-9]", "", family)[:40] + "-" + re.sub(r"[^A-Za-z0-9]", "", style)
    desc, copyright_, url = licence_text(face_path, licence)
    base = os.path.basename(face_path)
    names = {
        "familyName": family, "styleName": style, "uniqueFontIdentifier": "%s;%s;%s" % (family, style, version),
        "fullName": family if style == "Regular" else "%s %s" % (family, style), "psName": ps_name,
        "version": "Version %s; svf2ttf.py from %s" % (version, base),
        "description": "Generated by svf2ttf.py from %s (%dx%d cell, %d bpp, %s, %d glyphs, %d px strike). %s"
                       % (base, face.cell_w, face.cell_h, face.bpp, _kind(face), len(glyphs), ppem,
                          "Its licence is the licence of the font the face was made from (see the licence "
                          "description)." if desc else ""),
    }
    if copyright_:
        names["copyright"] = copyright_
    if desc:
        names["licenseDescription"] = desc
    if url:
        names["licenseInfoURL"] = url
    fb.setupNameTable(names, mac=False)
    cps = {g.cp for g in glyphs}
    cpr1 = (1 if cps & set(range(0x41, 0x5B)) else 0)
    if cps & set(range(0xAC00, 0xD7A4)):
        cpr1 |= 1 << 19
        if set(range(0xAC00, 0xD7A4)) <= cps:
            cpr1 |= 1 << 21
    cap = next((-g.box()[1] for g in glyphs if g.cp == 0x48 and g.box()), ascent)
    xh = next((-g.box()[1] for g in glyphs if g.cp == 0x78 and g.box()), ascent // 2)
    fb.setupOS2(sTypoAscender=ascent * k, sTypoDescender=-descent * k, sTypoLineGap=0,
                usWinAscent=ink_top * k, usWinDescent=ink_bottom * k, sxHeight=xh * k, sCapHeight=cap * k,
                fsType=0, fsSelection=fs_sel | 0x80, achVendID="NONE", usWeightClass=weight,
                ulCodePageRange1=cpr1, ulCodePageRange2=0, version=4)
    advs = {g.adv for g in glyphs if g.adv}
    fb.setupPost(isFixedPitch=1 if len(advs) == 1 else 0, keepGlyphNames=False,
                 underlinePosition=-max(1, descent // 2) * k, underlineThickness=k)
    font = fb.font
    font["head"].fontRevision = float(version) if re.fullmatch(r"\d+(\.\d+)?", version) else 1.0
    font["head"].macStyle = mac_style
    font["head"].flags = 0x000B
    font["head"].created = font["head"].modified = _timestamp()
    font["OS/2"].recalcAvgCharWidth(font)
    font["OS/2"].recalcUnicodeRanges(font)
    font["gasp"] = newTable("gasp")
    font["gasp"].gaspRange = {0xFFFF: 0x000F}
    if strike:
        eblc, ebdt = strike_tables(glyphs, ppem, face.bpp, ascent, descent)
        pairs = [("EBLC", eblc), ("EBDT", ebdt)]
        if apple:
            pairs += [("bloc", eblc), ("bdat", ebdt)]
        for tag, blob in pairs:
            t = DefaultTable(tag)
            t.data = blob
            font[tag] = t
    font.recalcTimestamp = False
    font.save(out)
    return {"glyphs": len(glyphs), "bytes": os.path.getsize(out), "ppem": ppem, "bpp": face.bpp,
            "kind": _kind(face), "family": family}


# ---- BDF ----------------------------------------------------------------------------------------------------------

def _bdf_quote(s):
    return '"%s"' % s.replace('"', "''")


def build_bdf(face_path, out, family=None, style="Regular", version="1.000", ppem=None, licence=None, bpp1=False,
              threshold=DEFAULT_THRESHOLD):
    face = svfline.Face.load(face_path)
    ppem = ppem or face.cell_h
    family = family or default_family(face_path)
    glyphs = face_glyphs(face)
    depth = 1 if bpp1 or face.bpp == 1 else face.bpp
    if depth == 1 and face.bpp != 1:
        for g in glyphs:
            g.px = {p: 1 for p, v in g.px.items() if coverage_of(face, v) >= threshold}
    ascent, descent = face.ascent, face.cell_h - face.ascent
    boxes = [g.box() for g in glyphs if g.box()]
    fx0 = min([b[0] for b in boxes] + [0])
    fy0 = min([b[1] for b in boxes] + [0])
    fx1 = max([b[2] for b in boxes] + [1])
    fy1 = max([b[3] for b in boxes] + [1])
    desc, copyright_, _ = licence_text(face_path, licence)
    weight = "Bold" if "bold" in style.lower() else "Medium"
    slant = "I" if "italic" in style.lower() else "R"
    advs = {g.adv for g in glyphs if g.adv}
    spacing = "C" if len(advs) == 1 else "P"
    xlfd = "-svf-%s-%s-%s-normal--%d-%d-75-75-%s-%d-ISO10646-1" % (
        family.replace("-", " "), weight, slant, ppem, ppem * 10, spacing, (sum(advs) // len(advs) * 10) if advs else 0)
    props = [("FOUNDRY", _bdf_quote("svf")), ("FAMILY_NAME", _bdf_quote(family)), ("WEIGHT_NAME", _bdf_quote(weight)),
             ("SLANT", _bdf_quote(slant)), ("SETWIDTH_NAME", _bdf_quote("Normal")), ("PIXEL_SIZE", str(ppem)),
             ("POINT_SIZE", str(ppem * 10)), ("RESOLUTION_X", "75"), ("RESOLUTION_Y", "75"),
             ("SPACING", _bdf_quote(spacing)), ("CHARSET_REGISTRY", _bdf_quote("ISO10646")),
             ("CHARSET_ENCODING", _bdf_quote("1")), ("FONT_ASCENT", str(ascent)), ("FONT_DESCENT", str(descent)),
             ("FONT_VERSION", _bdf_quote(version)),
             ("NOTICE", _bdf_quote("Generated by svf2ttf.py from %s (%s)" % (os.path.basename(face_path), _kind(face))))]
    if copyright_:
        props.append(("COPYRIGHT", _bdf_quote(copyright_)))
    lines = ["STARTFONT %s" % ("2.1" if depth == 1 else "2.3")]
    lines += ["COMMENT " + ln for ln in desc.splitlines()] if desc else []
    lines += ["FONT " + xlfd, "SIZE %d 75 75%s" % (ppem, "" if depth == 1 else " %d" % depth),
              "FONTBOUNDINGBOX %d %d %d %d" % (fx1 - fx0, fy1 - fy0, fx0, -fy1),
              "STARTPROPERTIES %d" % len(props)]
    lines += ["%s %s" % p for p in props]
    lines += ["ENDPROPERTIES", "CHARS %d" % len(glyphs)]
    for g in glyphs:
        box = g.box()
        lines += ["STARTCHAR %s" % g.name, "ENCODING %d" % g.cp,
                  "SWIDTH %d 0" % round(g.adv * 1000 / ppem), "DWIDTH %d 0" % g.adv]
        if box is None:
            lines += ["BBX 0 0 0 0", "BITMAP"]
        else:
            x0, y0, x1, y1 = box
            lines += ["BBX %d %d %d %d" % (x1 - x0, y1 - y0, x0, -y1), "BITMAP"]
            rows = _pack_rows(g, depth)
            pitch = ((x1 - x0) * depth + 7) // 8
            lines += [rows[i:i + pitch].hex().upper() for i in range(0, len(rows), pitch)]
        lines.append("ENDCHAR")
    lines.append("ENDFONT")
    with open(out, "w", encoding="ascii", errors="replace", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return {"glyphs": len(glyphs), "bytes": os.path.getsize(out), "ppem": ppem, "bpp": depth, "kind": _kind(face)}


# ---- compare ------------------------------------------------------------------------------------------------------

def compare(path_a, path_b):
    """{'compared', 'mismatches', 'pixel', 'advance', 'only_a', 'only_b', 'blank_only', 'first'} of two faces (see the
    module doc). Levels are compared as coverage (svfline's GRAY8), so faces of one bit depth compare level for level."""
    a, b = svfline.Face.load(path_a), svfline.Face.load(path_b)
    ca, cb = set(face_cps(a)), set(face_cps(b))
    res = {"compared": 0, "pixel": 0, "advance": 0, "only_a": 0, "only_b": 0, "blank_only": 0, "first": []}
    for cp in sorted(ca | cb):
        if cp in ca and cp in cb:
            res["compared"] += 1
            adv_a, pa = glyph_pixels(a, cp)
            adv_b, pb = glyph_pixels(b, cp)
            ga = {p: coverage_of(a, v) for p, v in pa.items()}
            gb = {p: coverage_of(b, v) for p, v in pb.items()}
            bad = False
            if ga != gb:
                res["pixel"] += 1
                bad = True
            if adv_a != adv_b:
                res["advance"] += 1
                bad = True
            if bad and len(res["first"]) < 20:
                res["first"].append(cp)
            res["mismatches"] = res.get("mismatches", 0) + bad
        else:
            face, key = (a, "only_a") if cp in ca else (b, "only_b")
            if glyph_pixels(face, cp)[1]:
                res[key] += 1
                if len(res["first"]) < 20:
                    res["first"].append(cp)
            else:
                res["blank_only"] += 1
    res["mismatches"] = res.get("mismatches", 0) + res["only_a"] + res["only_b"]
    return res


def cp_ranges(cps):
    """'20-7e,3131,ac00-d7a3' (lower-case hex, mkfont.py --unicode syntax) of the sorted code points @p cps."""
    out = []
    for cp in cps:
        if out and out[-1][1] == cp - 1:
            out[-1][1] = cp
        else:
            out.append([cp, cp])
    return ",".join("%x" % a if a == b else "%x-%x" % (a, b) for a, b in out)


# ---- command line -------------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="an SVF face to a TrueType bitmap font or a BDF; compare two faces")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("face", help="the SVF face (SVFN v3)")
        p.add_argument("output")
        p.add_argument("--family", default=None, help='family name (default "<FACE STEM> SVF")')
        p.add_argument("--style", default="Regular", help="style name (default Regular)")
        p.add_argument("--version", default="1.000", help="font version (default 1.000)")
        p.add_argument("--ppem", type=int, default=None, help="pixels per em of the strike (default: the cell height)")
        p.add_argument("--licence", default=None, metavar="FILE|none",
                       help="the licence note to embed (default: the note beside the face; none: no licence text)")
        p.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, metavar="C",
                       help="coverage 1..255 a pixel needs to be in the outline / 1 bpp BDF (default 128)")

    pt = sub.add_parser("ttf", help="SVF -> TrueType: pixel outlines + an embedded bitmap strike")
    common(pt)
    pt.add_argument("--no-strike", action="store_true", help="no EBLC/EBDT strike: outlines only")
    pt.add_argument("--apple", action="store_true", help="also write the strike as bloc/bdat")
    pb = sub.add_parser("bdf", help="SVF -> BDF")
    common(pb)
    pb.add_argument("--bpp1", action="store_true", help="a 2 or 8 bpp face as a 1 bpp BDF (pixels >= --threshold)")
    pc = sub.add_parser("compare", help="compare the glyphs of two faces as svfline places them")
    pc.add_argument("a")
    pc.add_argument("b")
    pp = sub.add_parser("cps", help="the face's code points as mkfont.py --unicode ranges")
    pp.add_argument("face")
    args = ap.parse_args(argv)

    if args.cmd == "cps":
        print(cp_ranges(face_cps(svfline.Face.load(args.face))))
        return 0

    if args.cmd == "compare":
        r = compare(args.a, args.b)
        print("compared %d glyphs: mismatches %d (pixels %d, advance %d, inked only in A %d, only in B %d); "
              "blank glyphs only one face has %d" % (r["compared"], r["mismatches"], r["pixel"], r["advance"],
                                                     r["only_a"], r["only_b"], r["blank_only"]))
        if r["first"]:
            print("first: " + " ".join("U+%04X" % cp for cp in r["first"]))
        return 0 if r["mismatches"] == 0 else 1
    if not 1 <= args.threshold <= 255:
        ap.error("--threshold must be 1..255")
    try:
        if args.cmd == "ttf":
            r = build_ttf(args.face, args.output, args.family, args.style, args.version, args.ppem, args.threshold,
                          args.licence, not args.no_strike, args.apple)
            what = "TrueType, %d px %d bpp strike" % (r["ppem"], r["bpp"]) if not args.no_strike else "TrueType, outlines only"
        else:
            r = build_bdf(args.face, args.output, args.family, args.style, args.version, args.ppem, args.licence,
                          args.bpp1, args.threshold)
            what = "BDF, %d px %d bpp" % (r["ppem"], r["bpp"])
    except (ValueError, OSError) as e:
        print("svf2ttf: %s" % e, file=sys.stderr)
        return 1
    print("%s: %s, %s face, %d glyphs, %d bytes" % (args.output, what, r["kind"], r["glyphs"], r["bytes"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
