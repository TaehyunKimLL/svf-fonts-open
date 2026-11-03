#!/usr/bin/env python3
"""Write faces.json (svf-fonts-web-index/1), the face index of the WASM font picker, from svf/ and web/LICENCES.tsv.

  python3 web/mkindex.py SVF_DIR OUT_JSON [--licences TSV] [--families TSV]
  python3 web/mkindex.py SVF_DIR [OUT_JSON] --check [--licences TSV] [--families TSV]

One entry per SVF_DIR/**/*.SVF|svf, sorted by key: key (svf/<rel>), url (faces/<rel>), group (the directory of <rel>),
label, cell [w, h], px (cell h), bpp, ascent, glyphs, jamo, flags, bytes, licences [licences/<rel>], hangul (how many of
the 2,350 KS X 1001 syllables the face draws), latin_only, subset (not jamo, not latin_only, hangul < 2350: hidden by
the page) and family, style, variant (from FAMILIES.tsv beside this script). The header values
come from tools/jamoset.py parse_svfn; jamo is true when tools/svfline.py Face composes with the face's JSET or JMAP (it unpacks
and every piece it names has a glyph), the same rule the renderer uses, so the index agrees with the renderer's view.

The licence files of a face come from LICENCES.tsv beside this script (rows glob<TAB>licence[,licence], both relative to
SVF_DIR, fnmatch case-sensitive). A face that no row covers, or more than one, or whose licence file is missing, makes
this exit 2 naming the first such face; so does a row with no licence, an absolute licence path or one outside SVF_DIR
after normalisation, and a malformed jamo-extra/FACES.TSV (file and line named). Nothing is written then. --check runs every check and writes nothing.

label: jamo-extra faces take FACES.TSV family + " {px} px" (+ " AA" at 2 bpp); other faces take the first line of their
first licence note (a licence file not named OFL*/LICENSE*) without its trailing parenthesis + " {px} px"; a face with
no note is labelled with its file stem. Only OUT_JSON is written; stdlib only.

FAMILIES.tsv: header row with file and family (style, variant optional, other columns ignored), then one row per face,
file being the index key svf/<rel>. Every listed (not subset) face needs a row with a family; a row whose file is no
face is an error; two listed faces sharing (family, style, px, bpp, jamo, cell_w, cell_h, variant) are an error naming
both. Errors name FAMILIES.tsv:<line> or the face and exit 2 with nothing written.
"""

import argparse
import fnmatch
import importlib.util
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FORMAT = "svf-fonts-web-index/1"


def load_svfline():
    """tools/svfline.py by path (it imports tools/jamoset.py); writes no bytecode into tools/."""
    sys.dont_write_bytecode = True
    path = os.path.join(os.path.dirname(HERE), "tools", "svfline.py")
    spec = importlib.util.spec_from_file_location("svfline", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FaceError(Exception):
    """A face the index cannot ship (no licence row, ambiguous row, missing licence file)."""


def licence_path(lic, where):
    """A licence path of LICENCES.tsv normalised relative to SVF_DIR; absolute or escaping paths are errors."""
    if os.path.isabs(lic) or lic.startswith(("/", "\\")):
        raise FaceError(f"{where}: licence path {lic} is absolute")
    norm = os.path.normpath(lic).replace(os.sep, "/")
    if norm == ".." or norm.startswith("../") or norm == ".":
        raise FaceError(f"{where}: licence path {lic} is outside the svf dir")
    return norm


def read_licences(path):
    """[(glob, [licence, ...], 'path:line')] from LICENCES.tsv, skipping blank and # lines."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            where = f"{path}:{n}"
            parts = line.split("\t")
            if len(parts) != 2 or not parts[0].strip():
                raise FaceError(f"{where}: expected glob<TAB>licence[,licence]")
            lics = [p.strip() for p in parts[1].split(",") if p.strip()]
            if not lics:
                raise FaceError(f"{where}: row {parts[0]} names no licence file")
            rows.append((parts[0], [licence_path(lic, f"{where} ({parts[0]})") for lic in lics], where))
    return rows


class FamilyTable(dict):
    def __init__(self):
        super().__init__()
        self.lines = {}
        self.path = ""


MAX_FIELD = 256  # picker.js MAX_FIELD: the page refuses a longer family, style or variant


def read_families(path):
    """{key: (family, style, variant)} from FAMILIES.tsv (key svf/<rel>); the result's .lines maps key -> line number
    and .path is the path as given. Raises FaceError (FAMILIES.tsv:<line>: ...) on a syntax error."""
    rows = FamilyTable()
    rows.path = path
    with open(path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    head = None
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        where = f"{path}:{n}"
        cells = [c.strip() for c in line.split("\t")]
        if head is None:
            if len(set(cells)) != len(cells):
                raise FaceError(f"{where}: duplicate column name in the header")
            if "file" not in cells or "family" not in cells:
                raise FaceError(f"{where}: header has no 'file' and 'family' columns")
            head = cells
            continue
        if len(cells) > len(head):
            raise FaceError(f"{where}: row has {len(cells)} cells, the header {len(head)}")
        cells += [""] * (len(head) - len(cells))
        cell = dict(zip(head, cells))
        key = cell["file"]
        if not key:
            raise FaceError(f"{where}: empty file")
        if not key.startswith("svf/") or len(key) == 4:
            raise FaceError(f"{where}: file {key} does not start with svf/")
        if key in rows:
            raise FaceError(f"{where}: file {key} is already on line {rows.lines[key]}")
        for col in ("family", "style", "variant"):
            if len(cell.get(col, "")) > MAX_FIELD:
                raise FaceError(f"{where}: {col} is over {MAX_FIELD} characters (the page's limit)")
        rows[key] = (cell["family"], cell.get("style", ""), cell.get("variant", ""))
        rows.lines[key] = n
    if head is None:
        raise FaceError(f"{path}:1: no header row")
    return rows


_KS = {}  # the 2,350 syllable code points, computed once


def coverage(data, svf, jamo, svfline):
    """(hangul, latin_only, subset): hangul counts the 2,350 KS X 1001 syllables the face draws (the renderer's rule
    for a jamo face, the cmap otherwise); latin_only: no jamo, no Hangul, all of U+0021..U+007E; subset: not jamo, not
    latin_only and hangul < 2350."""
    if "ks" not in _KS:
        _KS["ks"] = [0xAC00 + n for n in svfline.jamoset.ks_x_1001_syllables()]
    ks = _KS["ks"]
    if jamo:
        face = svfline.Face(data)
        hangul = sum(1 for cp in ks if face.has(cp))
    else:
        cmap = svf.glyphs
        hangul = sum(1 for cp in ks if cp in cmap)
    latin_only = (not jamo and hangul == 0 and all(c in svf.glyphs for c in range(0x21, 0x7F)))
    subset = (not jamo and not latin_only and hangul < len(ks))
    return hangul, latin_only, subset


def check_families(faces, rows, svf_dir):
    """The family rules over all entries; raises FaceError."""
    keys = {e["key"] for e in faces}
    for e in faces:
        if not e["subset"] and not e["family"]:
            raise FaceError(f"{e['key']}: no FAMILIES.tsv row with a family for this face")
    for key in sorted(rows):
        if key not in keys:
            raise FaceError(f"{rows.path}:{rows.lines[key]}: {key} is not a face under {svf_dir}")
    seen = {}
    for e in faces:
        if e["subset"]:
            continue
        t = (e["family"], e["style"], e["px"], e["bpp"], e["jamo"], e["cell"][0], e["cell"][1], e["variant"])
        if t in seen:
            raise FaceError(f"{seen[t]} and {e['key']} share family, style, size, bpp, composition, cell and variant "
                            f"({e['family']!r}, {e['style']!r}, {e['variant']!r}): give one a variant in FAMILIES.tsv")
        seen[t] = e["key"]


def find_faces(svf_dir):
    out = []
    for dirpath, dirnames, filenames in os.walk(svf_dir):
        dirnames.sort()
        for name in filenames:
            if name.lower().endswith(".svf"):
                rel = os.path.relpath(os.path.join(dirpath, name), svf_dir).replace(os.sep, "/")
                if "/" not in rel:  # group is the directory of <rel>; the page requires 1..256 characters of it
                    raise FaceError(f"{rel}: a face at the root of the svf directory has no group; put it in a group directory")
                out.append(rel)
    return sorted(out)


def read_faces_tsv(path):
    """{file: family} from a jamo-extra FACES.TSV (header row with 'file' and 'family'), or {} when there is none."""
    if not os.path.isfile(path):
        return {}
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if line.strip() and not line.startswith("#"):
                rows.append((n, line.rstrip("\n").split("\t")))
    if not rows:
        return {}
    hn, head = rows[0]
    if "file" not in head or "family" not in head:
        raise FaceError(f"{path}:{hn}: header has no 'file' and 'family' columns")
    fi, fa = head.index("file"), head.index("family")
    out = {}
    for n, r in rows[1:]:
        if len(r) <= max(fi, fa) or not r[fi]:
            raise FaceError(f"{path}:{n}: row has {len(r)} columns, the header {len(head)}")
        out[r[fi]] = r[fa]
    return out


def is_note(licence):
    name = os.path.basename(licence).upper()
    return not (name.startswith("OFL") or name.startswith("LICENSE"))


def note_title(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        first = f.readline().strip()
    return re.sub(r"\s*\([^()]*\)\s*$", "", first).strip()


def licences_for(rel, rows, svf_dir):
    hits = [(g, lic) for g, lic, _ in rows if fnmatch.fnmatchcase(rel, g)]
    if not hits:
        raise FaceError(f"{rel}: no LICENCES.tsv row covers this face")
    if len(hits) > 1:
        raise FaceError(f"{rel}: more than one LICENCES.tsv row covers this face ({', '.join(g for g, _ in hits)})")
    for lic in hits[0][1]:
        if not os.path.isfile(os.path.join(svf_dir, lic)):
            raise FaceError(f"{rel}: licence file {lic} is missing")
    return hits[0][1]


def entry(rel, svf_dir, rows, families, fam_rows, svfline):
    licences = licences_for(rel, rows, svf_dir)
    path = os.path.join(svf_dir, rel)
    with open(path, "rb") as f:
        data = f.read()
    try:
        svf = svfline.jamoset.parse_svfn(data)
        # jamo: the face composes Hangul as the renderer loads it (svfline.Face: the JSET unpacks and every piece it
        # names has a glyph); otherwise it is a plain face.
        jamo = svfline.Face(data).tables is not None
        hangul, latin_only, subset = coverage(data, svf, jamo, svfline)
    except (ValueError, struct.error) as e:  # a face the renderer would reject
        raise FaceError(f"{rel}: {e}")
    group = os.path.dirname(rel)
    name = os.path.basename(rel)
    px = svf.cell_h
    if group == "jamo-extra" and name in families:
        label = f"{families[name]} {px} px" + (" AA" if svf.bpp == 2 else "")
    else:
        notes = [lic for lic in licences if is_note(lic)]
        title = note_title(os.path.join(svf_dir, notes[0])) if notes else ""
        label = f"{title} {px} px" if title else os.path.splitext(name)[0]
    family, style, variant = fam_rows.get("svf/" + rel, ("", "", ""))
    return {
        "key": "svf/" + rel,
        "url": "faces/" + rel,
        "group": group,
        "label": label,
        "cell": [svf.cell_w, svf.cell_h],
        "px": px,
        "bpp": svf.bpp,
        "ascent": svf.ascent,
        "glyphs": svf.count,
        "jamo": jamo,
        "flags": svf.flags,
        "bytes": len(data),
        "licences": ["licences/" + lic for lic in licences],
        "hangul": hangul,
        "latin_only": latin_only,
        "subset": subset,
        "family": family,
        "style": style,
        "variant": variant,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("svf_dir")
    ap.add_argument("out_json", nargs="?", help="required unless --check")
    ap.add_argument("--check", action="store_true", help="run every check, write nothing")
    ap.add_argument("--licences", default=os.path.join(HERE, "LICENCES.tsv"),
                    help="the face-to-licence table (default: LICENCES.tsv beside this script)")
    ap.add_argument("--families", default=os.path.join(HERE, "FAMILIES.tsv"),
                    help="the face-to-family table (default: FAMILIES.tsv beside this script)")
    args = ap.parse_args(argv)
    if not args.check and not args.out_json:
        ap.error("OUT_JSON is required unless --check is given")
    svfline = load_svfline()
    try:
        rows = read_licences(args.licences)
        families = read_faces_tsv(os.path.join(args.svf_dir, "jamo-extra", "FACES.TSV"))
        fam_rows = read_families(args.families)
        faces = [entry(rel, args.svf_dir, rows, families, fam_rows, svfline) for rel in find_faces(args.svf_dir)]
        check_families(faces, fam_rows, args.svf_dir)
    except FaceError as e:
        print(f"mkindex.py: {e}", file=sys.stderr)
        return 2
    if not args.check:
        with open(args.out_json, "w", encoding="utf-8") as f:
            json.dump({"format": FORMAT, "faces": faces}, f, ensure_ascii=False, indent=1)
            f.write("\n")
    listed = sum(not e["subset"] for e in faces)
    print(f"{len(faces)} faces, {listed} listed ({sum(e['latin_only'] for e in faces)} latin-only), "
          f"{sum(e['subset'] for e in faces)} subset, 0 unmapped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
