#!/usr/bin/env python3
"""Recipes: known font files (ROM sets) described by names, sizes, hashes and offsets, and the planner that turns a
recipe into the tools' command lines.

A recipe is schema version 1 of the font finder's design (docs/superpowers/specs/2026-11-23-desktop-font-finder-design.md,
section 9.4). This module implements what card t_97acecf9's known ROM sets need: `files`, `regions`, `items` of kind
`ks-grid`, `ks-dense`, `english`, `raw-set` and `compose` (the built-in spec `spc1500` only), readings with `gfx` /
`bg` / `fg` / `invert`, `faces` of the routes `bdfface`, `bdfface + from-svf fit`, `spec` and `dos raw`, and an
optional `expect`. Anything else the schema names (an inline or derived compose spec, an English item's `top` on a BDF
route, ...) is refused by name ("not supported yet: ..."), never ignored; the finder extends this module (the
validator, `_item_file`, `face_commands`), it does not replace it. One extension beyond 9.4: a face's `english` may be
a list of English items, OR-ed into one English font (Quiz King of Fighters keeps its digits and letters apart).

A recipe is untrusted input: it carries parameters, never a command, a path or a tool name. `validate` checks every
key, type and range before anything is used, and the server builds every argv itself (`face_commands`). File names in
a recipe are labels: a file is bound to a recipe by its size and its SHA-256 (`match`), never by its name.

The built-in library is `maker/recipes/*.json` (bundled into the frozen sidecar as `recipes/`): names, sizes, hashes and
offsets of proprietary files, no byte of them.

The library assumes `maker/` and `tools/` are on sys.path (the entry points set it).
"""

import hashlib
import json
import os
import re
import sys

import binscan
import rawcarve
import toolrun

VERSION = 1
MAX_BYTES = 256 * 1024                 # a recipe file
MAX_SIZE = 1 << 26                     # an offset or a size: 64 MiB
ID_RE = re.compile(r"\A[a-z0-9][a-z0-9-]{0,47}\Z")
FACE_RE = re.compile(r"\A[A-Z0-9]{1,8}\Z")        # naming.NAME_RE without `.SVF`
HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
HEX40 = re.compile(r"\A[0-9a-f]{40}\Z")

# The schema's keys (9.4).
TOP_KEYS = {"recipe", "id", "title", "notes", "refs", "files", "regions", "items", "faces", "expect"}
FILE_KEYS = {"id", "name", "size", "sha256", "sha1", "optional"}
REGION_KEYS = {"id", "groups", "unit", "swap"}
ITEM_COMMON = {"id", "kind", "region", "offset", "reading", "ascent", "decided"}
ITEM_KEYS = {"ks-grid": {"chars", "grid"}, "english": {"first", "count", "top"}, "ks-dense": {"chars"},
             "raw-set": {"layout", "length"}, "compose": {"spec", "syllables"}}
READING_KEYS = {"glyph", "order", "stride", "lsb", "invert", "gfx", "bg", "fg"}
FACE_KEYS = {"name", "kind", "route", "hangul", "english", "from", "layout"}
DECIDED = ("by eye", "loose copy", "driver code")
ORDERS = ("rows", "strips", "cols", "bytecols")
KS_CHARS = ("ks-hangul", "ks-nonhanja", "ks-all")
RAW_LAYOUTS = ("844", "844-ihnm", "844-hbios24", "1044-san", "621", "kyra-lok")   # jamoset.py raw layouts
# The storage jamoset.py reads each raw layout in, by length (finder design 8.2): "rows" (headerless row-major cells: any
# reading, a non-plain one inked to rows first), "strips" (621: exactly 16x16 strips, cut as it is), "plain" (a
# header or the layout's own framing: a plain reading only, cut as it is). The printer layouts are not offered.
RAW_STORAGE = {"844": {11520: "rows", 25920: "rows", 72000: "rows", 103680: "rows", 11522: "plain", 15584: "plain"},
               "1044-san": {12800: "rows"}, "621": {6144: "strips"}, "844-ihnm": {11520: "plain"},
               "844-hbios24": {243900: "plain"}, "kyra-lok": {11550: "plain"}}
BUILTIN_SPECS = ("spc1500",)                       # rawcarve.py / jamoset.py --spec NAME

# The routes a face may name: route -> (kind, the Hangul item kinds it reads; None: it reads an earlier face).
ROUTES = {"bdfface": ("precomposed", ("ks-grid", "ks-dense", "compose")),
          "bdfface + from-svf fit": ("jamo", None),
          "spec": ("jamo", ("compose",)),
          "dos raw": ("jamo", ("raw-set",))}
NATIVE = {"bdfface": True, "bdfface + from-svf fit": False, "spec": True, "dos raw": True}
FIT_LAYOUTS = ("844", "adaptive")

# The files the planner writes in a step's work folder start with this; the job runner clears them before a run.
WORK_PREFIX = "recipe-"
PRECOMPOSED = "precomposed.svf"                    # routes.HWP_PRECOMPOSED: the reference a jamo fit is scored against


class RecipeError(ValueError):
    """A recipe that is not schema version 1, or uses what this implementation does not read yet."""


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _text(value, what, lo, hi):
    if not isinstance(value, str) or not lo <= len(value) <= hi:
        raise RecipeError("%s: a text of %d..%d characters" % (what, lo, hi))
    if any(ord(ch) < 0x20 or 0x7F <= ord(ch) < 0xA0 for ch in value):
        raise RecipeError("%s: a control character" % what)
    return value


def _int(value, what, lo, hi):
    if not _is_int(value) or not lo <= value <= hi:
        raise RecipeError("%s: an integer %d..%d" % (what, lo, hi))
    return value


def _bool(value, what):
    if not isinstance(value, bool):
        raise RecipeError("%s: true or false" % what)
    return value


def _keys(obj, allowed, what, later=()):
    """Refuse a key outside @p allowed (a typo) and, by name, a key of a later phase (@p later)."""
    if not isinstance(obj, dict):
        raise RecipeError("%s: an object" % what)
    for key in obj:
        if key in later:
            raise RecipeError("%s: not supported yet: %s" % (what, key))
        if key not in allowed:
            raise RecipeError("%s: unknown key %s" % (what, key))


def _id(value, what):
    if not isinstance(value, str) or not ID_RE.match(value):
        raise RecipeError("%s: an id ([a-z0-9][a-z0-9-]{0,47})" % what)
    return value


def _required(obj, keys, what):
    for key in keys:
        if key not in obj:
            raise RecipeError("%s: missing %s" % (what, key))


def _reading(obj, what, region_bytes):
    _keys(obj, READING_KEYS, what)
    _required(obj, ("glyph",), what)
    glyph = obj["glyph"]
    if not isinstance(glyph, list) or len(glyph) != 2:
        raise RecipeError("%s.glyph: [W, H]" % what)
    w, h = (_int(v, "%s.glyph" % what, 1, 1024) for v in glyph)
    if obj.get("order", "rows") not in ORDERS:
        raise RecipeError("%s.order: one of %s" % (what, ", ".join(ORDERS)))
    if "stride" in obj:
        _int(obj["stride"], "%s.stride" % what, 1, MAX_SIZE)
    for key in ("lsb", "invert"):
        if key in obj:
            _bool(obj[key], "%s.%s" % (what, key))
    if "gfx" in obj:
        _text(obj["gfx"], what + ".gfx", 1, 2000)
        for key in ("order", "stride", "lsb"):
            if key in obj:
                raise RecipeError("%s: %s and gfx: the layout gives the tile" % (what, key))
        if "bg" in obj and "fg" in obj:
            raise RecipeError("%s: bg or fg, not both" % what)
        if "bg" in obj:
            _int(obj["bg"], what + ".bg", 0, 255)
        if "fg" in obj:
            if not isinstance(obj["fg"], list) or not 1 <= len(obj["fg"]) <= 16:
                raise RecipeError("%s.fg: a list of 1..16 pens" % what)
            for pen in obj["fg"]:
                _int(pen, what + ".fg", 0, 255)
        try:
            gfx = binscan.parse_gfx(obj["gfx"], region_bytes, obj.get("bg", 0), obj.get("fg"))   # pens < 2^planes
        except Exception as exc:                       # binscan.GfxError, or a number past a bound
            raise RecipeError("%s.gfx: %s" % (what, (str(exc).splitlines() or [type(exc).__name__])[0]))
        if (gfx.w, gfx.h) != (w, h):
            raise RecipeError("%s.glyph: [%d, %d] is not the gfx tile's %dx%d" % (what, w, h, gfx.w, gfx.h))
    elif "bg" in obj or "fg" in obj:
        raise RecipeError("%s: bg / fg only with gfx" % what)
    return w, h


def _item(obj, regions):
    """@p regions: every file and region id -> its size in bytes."""
    what = "item %s" % (obj.get("id") if isinstance(obj, dict) else "?")
    if not isinstance(obj, dict):
        raise RecipeError("item: an object")
    kind = obj.get("kind")
    if kind not in ITEM_KEYS:
        raise RecipeError("%s.kind: one of %s" % (what, ", ".join(ITEM_KEYS)))
    _keys(obj, ITEM_COMMON | ITEM_KEYS[kind], what)
    _required(obj, ("id", "kind", "region", "reading"), what)
    _id(obj["id"], what + ".id")
    if obj["region"] not in regions:
        raise RecipeError("%s.region: %s is not a file or region of the recipe" % (what, obj["region"]))
    _int(obj.get("offset", 0), what + ".offset", 0, MAX_SIZE)
    w, h = _reading(obj["reading"], what + ".reading", regions[obj["region"]])
    if "ascent" in obj:
        _int(obj["ascent"], what + ".ascent", 1, h)
    if "decided" in obj and obj["decided"] not in DECIDED:
        raise RecipeError("%s.decided: one of %s" % (what, ", ".join(DECIDED)))
    if kind in ("ks-grid", "ks-dense"):
        _required(obj, ("chars",), what)
        if obj["chars"] not in KS_CHARS:
            raise RecipeError("%s.chars: one of %s" % (what, ", ".join(KS_CHARS)))
    if kind == "ks-grid":
        _required(obj, ("grid",), what)
        grid = obj["grid"]
        if not isinstance(grid, list) or len(grid) != 3:
            raise RecipeError("%s.grid: [L0, T0, PITCH]" % what)
        _int(grid[0], what + ".grid", 0, 255)
        _int(grid[1], what + ".grid", 0, 255)
        _int(grid[2], what + ".grid", 1, 256)
    elif kind == "english":
        first = _int(obj.get("first", 0), what + ".first", 0, 255)
        _int(obj.get("count", 256 - first), what + ".count", 1, 256 - first)
        _int(obj.get("top", 0), what + ".top", 0, 15)
        if not ((w == 8 and 8 <= h <= 16) or (w, h) == (16, 16)):
            raise RecipeError("%s.reading.glyph: [8, 8..16] or [16, 16]" % what)
    elif kind == "raw-set":
        if "ascent" in obj:                            # jamoset.py reads a raw layout's own cell
            raise RecipeError("%s: a raw-set item takes no ascent" % what)
        _required(obj, ("layout", "length"), what)
        if obj["layout"] not in RAW_LAYOUTS:
            raise RecipeError("%s: not supported yet: layout %s (one of %s)" % (what, obj["layout"], ", ".join(RAW_LAYOUTS)))
        _int(obj["length"], what + ".length", 1, MAX_SIZE)
        storage = RAW_STORAGE[obj["layout"]].get(obj["length"])
        if storage is None:
            raise RecipeError("%s.length: a %s raw set is %s bytes" % (what, obj["layout"], " or ".join(
                str(n) for n in sorted(RAW_STORAGE[obj["layout"]]))))
        r = obj["reading"]
        if storage == "strips" and r != {"glyph": [16, 16], "order": "strips"}:
            raise RecipeError("%s.reading: not supported yet: a 621 set read other than as its own 16x16 strips "
                              "({\"glyph\": [16, 16], \"order\": \"strips\"})" % what)
        if storage == "plain" and (set(r) - {"glyph", "order"} or r.get("order", "rows") != "rows"):
            raise RecipeError("%s.reading: not supported yet: a %s set of %d bytes keeps its own framing, so only a "
                              "plain reading (rows, no stride, lsb, invert or gfx)" % (what, obj["layout"], obj["length"]))
        if storage == "rows" and obj["length"] % ((w + 7) // 8 * h):
            raise RecipeError("%s.reading.glyph: %dx%d glyphs do not fill the %d bytes" % (what, w, h, obj["length"]))
    elif kind == "compose":
        ignored = sorted(set(obj["reading"]) - {"glyph"}) + (["offset"] if "offset" in obj else [])
        if ignored:                                    # the built-in spec reads its own region: nothing else applies
            raise RecipeError("%s: a compose item takes no %s" % (what, ", ".join(ignored)))
        _required(obj, ("spec",), what)
        spec = obj["spec"]
        if not isinstance(spec, dict) or set(spec) != {"builtin"}:
            raise RecipeError("%s: not supported yet: spec other than {\"builtin\": NAME}" % what)
        if spec["builtin"] not in BUILTIN_SPECS:
            raise RecipeError("%s.spec.builtin: one of %s" % (what, ", ".join(BUILTIN_SPECS)))
        if obj.get("syllables", "ks") not in ("ks", "all"):
            raise RecipeError("%s.syllables: ks or all" % what)
    return obj


def _english_ids(face):
    eng = face.get("english")
    if eng is None:
        return []
    return list(eng) if isinstance(eng, list) else [eng]


def _face(obj, items, earlier):
    what = "face %s" % (obj.get("name") if isinstance(obj, dict) else "?")
    _keys(obj, FACE_KEYS, what)
    _required(obj, ("name", "kind", "route"), what)
    if not isinstance(obj["name"], str) or not FACE_RE.match(obj["name"]):
        raise RecipeError("%s.name: [A-Z0-9]{1,8}" % what)
    kind, route = obj["kind"], obj["route"]
    if kind not in ("precomposed", "jamo"):
        raise RecipeError("%s.kind: precomposed or jamo" % what)
    if route not in ROUTES:
        raise RecipeError("%s: not supported yet: route %s" % (what, route))
    if ROUTES[route][0] != kind:
        raise RecipeError("%s: route %s makes a %s face" % (what, route, ROUTES[route][0]))
    eng = obj.get("english")
    if eng is not None and not (isinstance(eng, str) or (isinstance(eng, list) and 1 <= len(eng) <= 8)):
        raise RecipeError("%s.english: an item id or a list of 1..8" % what)
    for eid in _english_ids(obj):
        if not isinstance(eid, str) or (items.get(eid) or {}).get("kind") != "english":
            raise RecipeError("%s.english: an item of kind english" % what)
    if len({tuple(items[eid]["reading"]["glyph"]) for eid in _english_ids(obj)}) > 1:
        raise RecipeError("%s.english: the items of a list are OR-ed, so of one glyph size" % what)
    takes = ROUTES[route][1]
    if takes is None:                                  # a fit of an earlier face
        if "hangul" in obj:
            raise RecipeError("%s: not supported yet: hangul on a fit (a fit reads its from face)" % what)
        _required(obj, ("from",), what)
        if earlier.get(obj["from"], {}).get("kind") != "precomposed":
            raise RecipeError("%s.from: an earlier precomposed face of the recipe" % what)
        if obj.get("layout", "844") not in FIT_LAYOUTS:
            raise RecipeError("%s.layout: %s" % (what, " or ".join(FIT_LAYOUTS)))
    else:
        for key in ("from", "layout"):
            if key in obj:
                raise RecipeError("%s: %s is for a fit" % (what, key))
        _required(obj, ("hangul",), what)
        hangul = items.get(obj["hangul"])
        if hangul is None or hangul["kind"] not in takes:
            raise RecipeError("%s.hangul: an item of kind %s" % (what, " or ".join(takes)))
        if route == "bdfface":
            _required(obj, ("english",), what)         # bdfface.py takes its ASCII from a BDF
            for eid in _english_ids(obj):
                if items[eid].get("top", 0):
                    raise RecipeError("%s: not supported yet: top on an English BDF (rawcarve.py bdf)" % what)
    return obj


def _expect(obj, items, faces):
    _keys(obj, {"items", "faces"}, "expect")
    for key, names, fields in (("items", items, {"glyphs", "sha256"}), ("faces", faces, {"bytes", "glyphs", "ink"})):
        sub = obj.get(key, {})
        if not isinstance(sub, dict):
            raise RecipeError("expect.%s: an object" % key)
        for name, values in sub.items():
            if name not in names:
                raise RecipeError("expect.%s: %s is not one of the recipe's" % (key, name))
            _keys(values, fields, "expect.%s.%s" % (key, name))
            for field, value in values.items():
                if field == "sha256":
                    if not isinstance(value, str) or not HEX64.match(value):
                        raise RecipeError("expect.%s.%s.sha256: 64 lower-case hex characters" % (key, name))
                else:
                    _int(value, "expect.%s.%s.%s" % (key, name, field), 0, MAX_SIZE)


def validate(obj):
    """@p obj (a parsed recipe) checked against schema version 1 and this implementation's subset; returns it.
    RecipeError names the first problem."""
    if not isinstance(obj, dict):
        raise RecipeError("a recipe is a JSON object")
    if obj.get("recipe") != VERSION or not _is_int(obj.get("recipe")):
        raise RecipeError("recipe: version %r is not 1" % (obj.get("recipe"),))
    _keys(obj, TOP_KEYS, "recipe")
    _required(obj, ("id", "title", "files", "items", "faces"), "recipe")
    _id(obj["id"], "id")
    _keys(obj["title"], {"en", "ko"}, "title")
    _required(obj["title"], ("en",), "title")
    for lang, text in obj["title"].items():
        _text(text, "title." + lang, 1, 120)
    if "notes" in obj:
        _text(obj["notes"], "notes", 0, 2000)
    refs = obj.get("refs", [])
    if not isinstance(refs, list) or len(refs) > 16:
        raise RecipeError("refs: a list of at most 16 texts")
    for ref in refs:
        _text(ref, "refs", 0, 200)
    for key, hi in (("files", 16), ("items", 64), ("faces", 16)):
        if not isinstance(obj[key], list) or not 1 <= len(obj[key]) <= hi:
            raise RecipeError("%s: a list of 1..%d" % (key, hi))
    files = {}
    for f in obj["files"]:
        what = "file %s" % (f.get("id") if isinstance(f, dict) else "?")
        _keys(f, FILE_KEYS, what)
        _required(f, ("id", "name", "size", "sha256"), what)
        _id(f["id"], what + ".id")
        name = f["name"]
        if (not isinstance(name, str) or not 1 <= len(name.encode("utf-8")) <= 255 or "/" in name or "\\" in name
                or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name)):
            raise RecipeError("%s.name: a base name of 1..255 bytes" % what)
        _int(f["size"], what + ".size", 1, MAX_SIZE)
        if not isinstance(f["sha256"], str) or not HEX64.match(f["sha256"]):
            raise RecipeError("%s.sha256: 64 lower-case hex characters" % what)
        if "sha1" in f and (not isinstance(f["sha1"], str) or not HEX40.match(f["sha1"])):
            raise RecipeError("%s.sha1: 40 lower-case hex characters" % what)
        if "optional" in f and _bool(f["optional"], what + ".optional"):
            raise RecipeError("%s: not supported yet: optional (every file of a set is needed)" % what)
        if f["id"] in files:
            raise RecipeError("files: id %s twice" % f["id"])
        files[f["id"]] = f
    sizes_of = {fid: f["size"] for fid, f in files.items()}
    regions = obj.get("regions", [])
    if not isinstance(regions, list) or len(regions) > 16:
        raise RecipeError("regions: a list of at most 16")
    for r in regions:
        what = "region %s" % (r.get("id") if isinstance(r, dict) else "?")
        _keys(r, REGION_KEYS, what)
        _required(r, ("id", "groups"), what)
        _id(r["id"], what + ".id")
        if r["id"] in sizes_of:
            raise RecipeError("%s.id: also a file or region id" % what)
        groups = r["groups"]
        if not isinstance(groups, list) or not 1 <= len(groups) <= 16:
            raise RecipeError("%s.groups: a list of 1..16 groups" % what)
        total = 0
        for group in groups:
            if not isinstance(group, list) or not 1 <= len(group) <= 8 or any(g not in files for g in group):
                raise RecipeError("%s.groups: each a list of 1..8 file ids" % what)
            if len({files[g]["size"] for g in group}) != 1:
                raise RecipeError("%s.groups: the files of a group are interleaved, so of one size" % what)
            total += sum(files[g]["size"] for g in group)
        unit = r.get("unit", 1)
        if unit not in (1, 2, 4) or not _is_int(unit):
            raise RecipeError("%s.unit: 1, 2 or 4" % what)
        if any(files[g]["size"] % unit for group in groups for g in group):
            raise RecipeError("%s.unit: %d does not divide every file's size" % (what, unit))
        if "swap" in r and _bool(r["swap"], what + ".swap") and total % 2:
            raise RecipeError("%s.swap: the region's %d bytes are not whole 16-bit words" % (what, total))
        sizes_of[r["id"]] = _int(total, what + " size", 1, MAX_SIZE)
    items = {}
    for item in obj["items"]:
        _item(item, sizes_of)
        if item["id"] in items:
            raise RecipeError("items: id %s twice" % item["id"])
        items[item["id"]] = item
    faces = {}
    for face in obj["faces"]:
        _face(face, items, faces)
        if face["name"] in faces:
            raise RecipeError("faces: name %s twice" % face["name"])
        faces[face["name"]] = face
    if "expect" in obj:
        _expect(obj["expect"], items, faces)
    check_fit(obj)                                     # every size is in the recipe: an item past its region is refused
    return obj


def loads(data, name="recipe"):
    """A recipe from @p data (bytes of a JSON file, at most MAX_BYTES), validated."""
    if len(data) > MAX_BYTES:
        raise RecipeError("%s: larger than %d bytes" % (name, MAX_BYTES))
    try:
        obj = json.loads(data.decode("utf-8"), parse_constant=lambda c: (_ for _ in ()).throw(RecipeError(c)))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RecipeError("%s: not JSON (%s)" % (name, type(exc).__name__))
    return validate(obj)


# ---- the library -----------------------------------------------------------------------------------------------

def builtin_dir():
    """The built-in recipes: `maker/recipes/`, or `recipes/` of the frozen bundle."""
    if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None):
        return os.path.join(sys._MEIPASS, "recipes")              # PyInstaller's <_internal>
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "recipes")


_LIBRARY = {}


def library(folder=None):
    """`{id: recipe}` of the recipes in @p folder (default the built-in ones), each file `<id>.json`. A built-in recipe
    that does not validate is a bug and raises; the result is cached per folder."""
    folder = folder or builtin_dir()
    if folder not in _LIBRARY:
        out = {}
        if not os.path.isdir(folder):                  # the built-in folder is part of the maker (and of the sidecar)
            raise RecipeError("the recipes folder %s is missing" % folder)
        names = sorted(n for n in os.listdir(folder) if n.endswith(".json"))
        for name in names:
            with open(os.path.join(folder, name), "rb") as f:
                rec = loads(f.read(MAX_BYTES + 1), name)
            if rec["id"] + ".json" != name:
                raise RecipeError("%s: its id is %s" % (name, rec["id"]))
            out[rec["id"]] = rec
        _LIBRARY[folder] = out
    return _LIBRARY[folder]


def get(recipe_id):
    """The built-in recipe @p recipe_id, or None."""
    return library().get(recipe_id)


def sizes(lib=None):
    """The file sizes any recipe of @p lib names: a file of another size is never hashed."""
    return {f["size"] for rec in (lib or library()).values() for f in rec["files"]}


def file_hashes(path):
    """`(sha256, sha1)` hex digests of @p path, read in chunks."""
    a, b = hashlib.sha256(), hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            a.update(chunk)
            b.update(chunk)
    return a.hexdigest(), b.hexdigest()


def match(files, lib=None):
    """The recipes the batch's files (`[(key, abs path, size)]`) meet, `[{"recipe", "state", "bound", "missing",
    "similar"}]` in library order. Only a file of a size some recipe names is hashed. `state` is `known` (every
    non-optional file bound by size and sha256, and sha1 when the recipe has one), `part` (some bound, some missing) or
    `similar` (none bound; a file of a recipe file's name and size whose hash differs). `bound` maps a recipe file id
    to the key of the batch file, `missing` lists the names of the unbound non-optional files, `similar` maps a file id
    to a key (in a `part` set too: the missing file is there, in another revision)."""
    lib = lib if lib is not None else library()
    wanted = sizes(lib)
    hashes = {}
    for key, path, size in files:
        if size in wanted:
            try:
                hashes[key] = file_hashes(path)
            except OSError:
                pass
    out = []
    for rec in lib.values():
        bound, similar = {}, {}
        for f in rec["files"]:
            for key, path, size in files:
                if size != f["size"] or key not in hashes:
                    continue
                sha256, sha1 = hashes[key]
                if sha256 == f["sha256"] and sha1 == f.get("sha1", sha1):
                    bound.setdefault(f["id"], key)
                elif os.path.basename(path).lower() == f["name"].lower():
                    similar.setdefault(f["id"], key)
        missing = [f["name"] for f in rec["files"] if not f.get("optional") and f["id"] not in bound]
        if bound:                                      # a file of the set here in another revision is named as such
            out.append({"recipe": rec, "state": "part" if missing else "known", "bound": bound, "missing": missing,
                        "similar": {fid: key for fid, key in similar.items() if fid not in bound}})
        elif similar:
            out.append({"recipe": rec, "state": "similar", "bound": {}, "missing": missing, "similar": similar})
    return out


def _region_files(rec, region_id):
    """The file ids a file or region id reads, in load order."""
    for r in rec.get("regions", []):
        if r["id"] == region_id:
            return [fid for group in r["groups"] for fid in group]
    return [region_id]


def host_file(rec):
    """The recipe file whose entry carries the recipe in the fonts table: the (first) file the first face's Hangul item
    reads."""
    items = {item["id"]: item for item in rec["items"]}
    for face in rec["faces"]:
        if face.get("hangul"):
            return _region_files(rec, items[face["hangul"]]["region"])[0]
    return rec["files"][0]["id"]


def item_height(rec):
    """The pixel height of the recipe's faces: the glyph height of the first face's Hangul item."""
    items = {item["id"]: item for item in rec["items"]}
    for face in rec["faces"]:
        if face.get("hangul"):
            return items[face["hangul"]]["reading"]["glyph"][1]
    return rec["items"][0]["reading"]["glyph"][1]


def offered_faces(rec):
    """The faces the maker offers: the first of each kind (the page has one route per kind and font)."""
    out, seen = [], set()
    for face in rec["faces"]:
        if face["kind"] not in seen:
            seen.add(face["kind"])
            out.append(face)
    return out


def _region_size(rec, region_id):
    files = {f["id"]: f for f in rec["files"]}
    return sum(files[fid]["size"] for fid in _region_files(rec, region_id))


def _copied_as_is(item):
    """True when a raw set is cut from its region byte for byte (its layout's own storage, or a plain row reading of a
    row layout); False when the planner inks it to rows first (any other reading: stride, order, lsb, invert, tiles)."""
    r = item["reading"]
    if RAW_STORAGE[item["layout"]][item["length"]] != "rows":
        return True
    return ("gfx" not in r and r.get("order", "rows") == "rows" and "stride" not in r and not r.get("lsb")
            and not r.get("invert"))


def _span(item, region_bytes):
    """The bytes @p item reads from its region's start: offset + through its last glyph (a tile layout's footprint is
    the bits its planes and offsets reach, RGN_FRAC included); None for a compose item (the built-in spec reads its own
    region, `rawcarve.py` checks it)."""
    r = item["reading"]
    if item["kind"] == "compose":
        return None
    if item["kind"] == "raw-set" and _copied_as_is(item):       # cut straight from the region: its length
        return item.get("offset", 0) + item["length"]
    w, h = r["glyph"]
    if "gfx" in r:
        gfx = binscan.parse_gfx(r["gfx"], region_bytes, r.get("bg", 0), r.get("fg"))
        foot, stride = gfx.foot, gfx.stride
    else:
        foot = binscan.glyph_bytes(w, h, r.get("order", "rows"))
        stride = r.get("stride", foot)
    if item["kind"] == "english":
        last = item.get("count", 256 - item.get("first", 0)) - 1
    elif item["kind"] == "ks-grid":
        l0, t0, pitch = item["grid"]
        last = max((lead - l0) * pitch + (trail - t0) for lead, trail, _cp in rawcarve.ks_codes(item["chars"]))
    elif item["kind"] == "ks-dense":
        last = len(rawcarve.ks_codes(item["chars"])) - 1
    else:                                              # raw-set read as tiles: the glyphs its length takes
        last = -(-item["length"] // ((w + 7) // 8 * h)) - 1
    return item.get("offset", 0) + last * stride + foot


def check_fit(rec):
    """RecipeError when an item's reading does not fit its region: every size is in the recipe, so `validate` runs it
    (a bound file has the recipe's size, its hash says so)."""
    for item in rec["items"]:
        if item["kind"] == "ks-grid":
            l0, t0, pitch = item["grid"]
            for lead, trail, _cp in rawcarve.ks_codes(item["chars"]):
                if lead < l0 or not t0 <= trail < t0 + pitch:
                    raise RecipeError("item %s: code %02X%02X is outside its grid" % (item["id"], lead, trail))
        size = _region_size(rec, item["region"])
        span = _span(item, size)
        if item.get("offset", 0) >= size or (span is not None and span > size):
            raise RecipeError("item %s reads past the end of its region (%d bytes)" % (item["id"], size))


# ---- the planner -----------------------------------------------------------------------------------------------

def _hexa(value):
    return "0x%x" % value


class _Plan:
    """The commands of one face step: each region and item file is made once, in the step's work folder."""

    def __init__(self, rec, files, work, tools_dir):
        self.rec, self.files, self.work, self.tools = rec, files, work, tools_dir
        self.items = {item["id"]: item for item in rec["items"]}
        self.argvs, self.made = [], {}

    def path(self, name):
        return os.path.join(self.work, WORK_PREFIX + name)

    def tool(self, name):
        return toolrun.tool(name, self.tools)

    def region(self, region_id):
        """The file an item's region is: a bound file, or `rawcarve.py region` of its groups."""
        key = ("region", region_id)
        if key in self.made:
            return self.made[key]
        r = next((r for r in self.rec.get("regions", []) if r["id"] == region_id), None)
        if r is None:
            if region_id not in self.files:
                raise RecipeError("needs the file %s" % region_id)
            out = self.files[region_id]
        else:
            for fid in (f for group in r["groups"] for f in group):
                if fid not in self.files:
                    raise RecipeError("needs the file %s" % fid)
            out = self.path("region-%s.bin" % region_id)
            argv = self.tool("rawcarve") + ["region"]
            for g in r["groups"]:                      # --group: a whole path each (a comma in a folder name stays)
                argv += ["--group"] + [self.files[f] for f in g]
            if r.get("unit", 1) != 1:
                argv += ["--unit", str(r["unit"])]
            if r.get("swap"):
                argv.append("--swap")
            self.argvs.append(argv + ["-o", out])
        self.made[key] = out
        return out

    @staticmethod
    def geometry(reading, glyph=True):
        """The tile options of a reading: `--gfx L [--bg P | --fg P,..]`, or `--glyph WxH [--order] [--stride] [--lsb]`;
        and `--invert`."""
        out = []
        if "gfx" in reading:
            out += ["--gfx", reading["gfx"]]
            if "bg" in reading:
                out += ["--bg", str(reading["bg"])]
            if "fg" in reading:
                out += ["--fg", ",".join(str(p) for p in reading["fg"])]
        elif glyph:
            out += ["--glyph", "%dx%d" % tuple(reading["glyph"])]
            if reading.get("order", "rows") != "rows":
                out += ["--order", reading["order"]]
            if "stride" in reading:
                out += ["--stride", str(reading["stride"])]
            if reading.get("lsb"):
                out.append("--lsb")
        if reading.get("invert"):
            out.append("--invert")
        return out

    def _ink(self, item, count, name):
        """`rawcarve.py ink` of @p count glyphs of @p item from its offset: plain 1 bpp row-major glyphs."""
        out = self.path(name)
        argv = self.tool("rawcarve") + ["ink", self.region(item["region"])]
        if item.get("offset", 0):
            argv += ["--offset", _hexa(item["offset"])]
        self.argvs.append(argv + ["--count", str(count)] + self.geometry(item["reading"]) + ["-o", out])
        return out

    def _plain(self, item):
        """True when `rawcarve.py eng` / `cut` read the item as it is: 1 bpp rows, no tile layout, no other order."""
        r = item["reading"]
        return "gfx" not in r and r.get("order", "rows") == "rows" and "stride" not in r and not r.get("lsb")

    def bdf(self, item_id):
        """A Unicode BDF of an item (bdfface.py's --hangul / --ascii)."""
        key = ("bdf", item_id)
        if key in self.made:
            return self.made[key]
        item = self.items[item_id]
        out = self.path("%s.bdf" % item_id)
        if item["kind"] == "compose":
            argv = self.tool("rawcarve") + ["compose", self.region(item["region"]), "--spec", item["spec"]["builtin"]]
            if item.get("syllables", "ks") != "ks":
                argv += ["--syllables", item["syllables"]]
        else:
            argv = self.tool("rawcarve") + ["bdf", self.region(item["region"])]
            if item.get("offset", 0):
                argv += ["--offset", _hexa(item["offset"])]
            argv += self.geometry(item["reading"])
            if item["kind"] == "ks-grid":
                l0, t0, pitch = item["grid"]
                argv += ["--chars", item["chars"], "--grid", "%s,%s,%d" % (_hexa(l0), _hexa(t0), pitch)]
            elif item["kind"] == "ks-dense":
                argv += ["--chars", item["chars"], "--dense"]
            else:
                argv += ["--chars", "ascii"]
                if item.get("first", 0):
                    argv += ["--first", _hexa(item["first"])]
                if "count" in item and item["count"] != 256 - item.get("first", 0):
                    argv += ["--count", str(item["count"])]
        if "ascent" in item:
            argv += ["--ascent", str(item["ascent"])]
        self.argvs.append(argv + ["-o", out])
        self.made[key] = out
        return out

    def eng(self, item_id):
        """An English item as the raw font `--eng` reads (`rawcarve.py eng`; a tile layout is inked first)."""
        key = ("eng", item_id)
        if key in self.made:
            return self.made[key]
        item = self.items[item_id]
        w, h = item["reading"]["glyph"]
        first = item.get("first", 0)
        count = item.get("count", 256 - first)
        if self._plain(item):
            src, offset = self.region(item["region"]), item.get("offset", 0)
            invert = item["reading"].get("invert")
        else:
            src, offset, invert = self._ink(item, count, "%s-ink.bin" % item_id), 0, False
        out = self.path("%s-eng.bin" % item_id)
        argv = self.tool("rawcarve") + ["eng", src, "--offset", _hexa(offset)]
        if h != 16:
            argv += ["--height", str(h)]
        if item.get("top", 0):
            argv += ["--top", str(item["top"])]
        if w == 16:
            argv += ["--width", "16"]
        if first:
            argv += ["--first", _hexa(first)]
        if "count" in item and count != 256 - first:
            argv += ["--count", str(count)]
        if invert:
            argv.append("--invert")
        self.argvs.append(argv + ["-o", out])
        self.made[key] = out
        return out

    def english_bdf(self, ids):
        """The English BDF of a face: its one item's BDF, or the OR of several items' fonts (`srcprep.py or-files`)
        read as one 16-row table."""
        if len(ids) == 1:
            return self.bdf(ids[0])
        engs = [self.eng(i) for i in ids]
        merged = self.path("english-merged.bin")
        self.argvs.append(toolrun.maker_script("srcprep") + ["or-files", merged] + engs)
        w = max(self.items[i]["reading"]["glyph"][0] for i in ids)
        out = self.path("english.bdf")
        argv = self.tool("rawcarve") + ["bdf", merged, "--glyph", "%dx16" % w, "--chars", "ascii"]
        ascent = self.items[ids[0]].get("ascent")
        if ascent is not None:
            argv += ["--ascent", str(ascent)]
        self.argvs.append(argv + ["-o", out])
        return out

    def english_eng(self, ids):
        """The `--eng` file of a face: its one item's, or the OR of several."""
        if len(ids) == 1:
            return self.eng(ids[0])
        engs = [self.eng(i) for i in ids]
        merged = self.path("english-merged.bin")
        self.argvs.append(toolrun.maker_script("srcprep") + ["or-files", merged] + engs)
        return merged

    def raw(self, item_id):
        """A raw-set item as the file `jamoset.py --layout L` reads (`rawcarve.py cut`; a tile layout is inked first)."""
        item = self.items[item_id]
        if _copied_as_is(item):                        # the bytes as they are
            src, offset = self.region(item["region"]), item.get("offset", 0)
        else:
            w, h = item["reading"]["glyph"]
            per = (w + 7) // 8 * h
            src, offset = self._ink(item, -(-item["length"] // per), "%s-ink.bin" % item_id), 0
        out = self.path("%s.fnt" % item_id)
        self.argvs.append(self.tool("rawcarve") + ["cut", src, "--offset", _hexa(offset), "--length",
                                                   str(item["length"]), "-o", out])
        return out


def face_plan(rec, face_name, files, paths, chars_from, tools_dir, layout=None, plan=None):
    """`(argvs, roles)`: the argvs that make face @p face_name of @p rec in the step's work folder (`paths["work"]`) at
    `paths["out"]`, and `roles` = `{"writer": index of the command that writes the face, "bdfface": index of the
    bdfface.py command or None}` (where the page's panel flags go: `routes._recipe_commands`).

    The regions (`rawcarve.py region --group ...`), the items as the route reads them (`rawcarve.py bdf` / `compose` /
    `eng` / `ink` + `cut`), then the route: `bdfface.py --hangul H --ascii A --cell WxH --chars-from LIST`; a fit makes
    the face it reads as `precomposed.svf` (with the same plan: each region and item once), then `jamoset.py --layout L
    --from-svf precomposed.svf --mask-font none [--eng E] --check`; `spec` is `jamoset.py --layout spec --spec NAME
    REGION [--eng E] --check`; `dos raw` is `jamoset.py RAW --layout L [--eng E] --check`. @p files maps a recipe file id
    to the bound file's absolute path, @p chars_from is the range list, @p layout a fit's layout (default the face's).
    The commands of docs/recipes/rom-86box.md ("Korean VGA font ROMs (86Box)") and docs/recipes/rom-mame.md ("Korean font
    ROMs in MAME sets")."""
    faces = {face["name"]: face for face in rec["faces"]}
    face = faces[face_name]
    plan = plan or _Plan(rec, files, paths["work"], tools_dir)
    route = face["route"]
    eng_ids = _english_ids(face)
    if route == "bdfface + from-svf fit":
        precomposed = os.path.join(paths["work"], PRECOMPOSED)
        _argvs, inner = face_plan(rec, face["from"], files, dict(paths, out=precomposed), chars_from, tools_dir,
                                  plan=plan)
        fit = plan.tool("jamoset") + ["--layout", layout or face.get("layout", "844"), "--from-svf", precomposed,
                                      "--mask-font", "none"]
        if eng_ids:
            fit += ["--eng", plan.english_eng(eng_ids)]
        plan.argvs.append(fit + ["--check", "-o", paths["out"]])
        return plan.argvs, {"writer": len(plan.argvs) - 1, "bdfface": inner["bdfface"]}
    hangul = plan.items[face["hangul"]]
    if route == "bdfface":
        hbdf = plan.bdf(hangul["id"])
        ebdf = plan.english_bdf(eng_ids)
        w, h = hangul["reading"]["glyph"]
        plan.argvs.append(plan.tool("bdfface") + ["--hangul", hbdf, "--ascii", ebdf, "--cell", "%dx%d" % (w, h),
                                                  "--chars-from", chars_from, "-o", paths["out"]])
        return plan.argvs, {"writer": len(plan.argvs) - 1, "bdfface": len(plan.argvs) - 1}
    if route == "spec":
        argv = plan.tool("jamoset") + ["--layout", "spec", "--spec", hangul["spec"]["builtin"],
                                       plan.region(hangul["region"])]
    else:                                              # dos raw
        raw = plan.raw(hangul["id"])
        argv = plan.tool("jamoset") + ["--layout", hangul["layout"], raw]
    if eng_ids:
        argv += ["--eng", plan.english_eng(eng_ids)]
    plan.argvs.append(argv + ["--check", "-o", paths["out"]])
    return plan.argvs, {"writer": len(plan.argvs) - 1, "bdfface": None}


def face_commands(rec, face_name, files, paths, chars_from, tools_dir, layout=None):
    """`face_plan`'s argvs alone."""
    return face_plan(rec, face_name, files, paths, chars_from, tools_dir, layout)[0]
