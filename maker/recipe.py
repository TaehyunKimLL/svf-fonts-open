#!/usr/bin/env python3
"""Recipes: known font files (ROM sets) described by names, sizes, hashes and offsets, and the planner that turns a
recipe into the tools' command lines.

A recipe is schema version 1 of the font finder's design (docs/superpowers/specs/2026-11-23-desktop-font-finder-design.md,
section 9.4). This module implements the subset card t_97acecf9 needs: `files`, `items` of kind `ks-grid` and
`english`, `faces` of the routes `bdfface` and `bdfface + from-svf fit`, and an optional `expect`. Every other key or
kind the schema names is refused by name ("not supported yet: regions"), never ignored; the finder extends this
module (the validator, `item_commands`, `face_commands`), it does not replace it.

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

# The schema's keys (9.4); those of a later phase are refused by name.
TOP_KEYS = {"recipe", "id", "title", "notes", "refs", "files", "regions", "items", "faces", "expect"}
FILE_KEYS = {"id", "name", "size", "sha256", "sha1", "optional"}
ITEM_COMMON = {"id", "kind", "region", "offset", "reading", "ascent", "decided"}
ITEM_KEYS = {"ks-grid": {"chars", "grid"}, "english": {"first", "count", "top"}, "ks-dense": {"chars"},
             "raw-set": {"layout", "length"}, "compose": {"spec", "syllables"}}
READING_KEYS = {"glyph", "order", "stride", "lsb", "invert", "gfx", "bg", "fg"}
FACE_KEYS = {"name", "kind", "route", "hangul", "english", "from", "layout"}
DECIDED = ("by eye", "loose copy", "driver code")
ORDERS = ("rows", "strips", "cols", "bytecols")
KS_CHARS = ("ks-hangul", "ks-nonhanja", "ks-all")

# What this implementation reads (t_97acecf9's subset).
SUPPORTED_KINDS = ("ks-grid", "english")
ROUTE_ITEMS = {"bdfface": ("ks-grid",)}           # a precomposed route -> the Hangul item kinds it takes
FIT_ROUTES = ("bdfface + from-svf fit",)          # a jamo fit of an earlier face of the recipe
FIT_LAYOUTS = ("844", "adaptive")

# The files the planner writes in a step's work folder (the job runner clears them before a run).
HANGUL_BDF = "recipe-hangul.bdf"
ENGLISH_BDF = "recipe-english.bdf"
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


def _reading(obj, what):
    _keys(obj, READING_KEYS - {"gfx", "bg", "fg"}, what, later=("gfx", "bg", "fg"))
    _required(obj, ("glyph",), what)
    glyph = obj["glyph"]
    if not isinstance(glyph, list) or len(glyph) != 2:
        raise RecipeError("%s.glyph: [W, H]" % what)
    w, h = (_int(v, "%s.glyph" % what, 1, 1024) for v in glyph)
    order = obj.get("order", "rows")
    if order not in ORDERS:
        raise RecipeError("%s.order: one of %s" % (what, ", ".join(ORDERS)))
    if "stride" in obj:
        _int(obj["stride"], "%s.stride" % what, 1, MAX_SIZE)
    for key in ("lsb", "invert"):
        if key in obj:
            _bool(obj[key], "%s.%s" % (what, key))
    if obj.get("invert"):
        raise RecipeError("%s: not supported yet: invert (rawcarve.py bdf reads ink as set bits)" % what)
    return w, h


def _item(obj, files):
    what = "item %s" % (obj.get("id") if isinstance(obj, dict) else "?")
    if not isinstance(obj, dict):
        raise RecipeError("item: an object")
    kind = obj.get("kind")
    if kind not in ITEM_KEYS:
        raise RecipeError("%s.kind: one of %s" % (what, ", ".join(ITEM_KEYS)))
    if kind not in SUPPORTED_KINDS:
        raise RecipeError("%s: not supported yet: kind %s" % (what, kind))
    _keys(obj, ITEM_COMMON | ITEM_KEYS[kind], what)
    _required(obj, ("id", "kind", "region", "reading"), what)
    _id(obj["id"], what + ".id")
    if obj["region"] not in files:
        raise RecipeError("%s.region: %s is not a file of the recipe" % (what, obj["region"]))
    _int(obj.get("offset", 0), what + ".offset", 0, MAX_SIZE)
    w, h = _reading(obj["reading"], what + ".reading")
    if "ascent" in obj:
        _int(obj["ascent"], what + ".ascent", 1, h)
    if "decided" in obj and obj["decided"] not in DECIDED:
        raise RecipeError("%s.decided: one of %s" % (what, ", ".join(DECIDED)))
    if kind == "ks-grid":
        _required(obj, ("chars", "grid"), what)
        if obj["chars"] not in KS_CHARS:
            raise RecipeError("%s.chars: one of %s" % (what, ", ".join(KS_CHARS)))
        grid = obj["grid"]
        if not isinstance(grid, list) or len(grid) != 3:
            raise RecipeError("%s.grid: [L0, T0, PITCH]" % what)
        _int(grid[0], what + ".grid", 0, 255)
        _int(grid[1], what + ".grid", 0, 255)
        _int(grid[2], what + ".grid", 1, 256)
    else:                                          # english
        first = _int(obj.get("first", 0), what + ".first", 0, 255)
        _int(obj.get("count", 256 - first), what + ".count", 1, 256 - first)
        top = _int(obj.get("top", 0), what + ".top", 0, 15)
        if not (w == 8 and 8 <= h <= 16):
            raise RecipeError("%s.reading.glyph: [8, 8..16] (a 16x16 English font: not supported yet)" % what)
        if top:
            raise RecipeError("%s: not supported yet: top (rawcarve.py bdf places the glyph at row 0)" % what)
    return obj


def _face(obj, items, earlier):
    what = "face %s" % (obj.get("name") if isinstance(obj, dict) else "?")
    _keys(obj, FACE_KEYS, what)
    _required(obj, ("name", "kind", "route"), what)
    if not isinstance(obj["name"], str) or not FACE_RE.match(obj["name"]):
        raise RecipeError("%s.name: [A-Z0-9]{1,8}" % what)
    kind, route = obj["kind"], obj["route"]
    if kind not in ("precomposed", "jamo"):
        raise RecipeError("%s.kind: precomposed or jamo" % what)
    if kind == "precomposed":
        if route not in ROUTE_ITEMS:
            raise RecipeError("%s: not supported yet: route %s" % (what, route))
        for key in ("from", "layout"):
            if key in obj:
                raise RecipeError("%s: %s is for a jamo fit" % (what, key))
        _required(obj, ("hangul",), what)
        hangul = items.get(obj["hangul"])
        if hangul is None or hangul["kind"] not in ROUTE_ITEMS[route]:
            raise RecipeError("%s.hangul: an item of kind %s" % (what, " or ".join(ROUTE_ITEMS[route])))
        if route == "bdfface":
            _required(obj, ("english",), what)     # bdfface.py takes its ASCII from a BDF
        if "english" in obj and (items.get(obj["english"]) or {}).get("kind") != "english":
            raise RecipeError("%s.english: an item of kind english" % what)
    else:
        if route not in FIT_ROUTES:
            raise RecipeError("%s: not supported yet: route %s" % (what, route))
        for key in ("hangul", "english"):
            if key in obj:
                raise RecipeError("%s: not supported yet: %s on a jamo fit (it reads its from face)" % (what, key))
        _required(obj, ("from",), what)
        if earlier.get(obj["from"], {}).get("kind") != "precomposed":
            raise RecipeError("%s.from: an earlier precomposed face of the recipe" % what)
        if obj.get("layout", "844") not in FIT_LAYOUTS:
            raise RecipeError("%s.layout: %s" % (what, " or ".join(FIT_LAYOUTS)))
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
    _keys(obj, TOP_KEYS - {"regions"}, "recipe", later=("regions",))
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
        if "optional" in f:
            _bool(f["optional"], what + ".optional")
        if f["id"] in files:
            raise RecipeError("files: id %s twice" % f["id"])
        files[f["id"]] = f
    items = {}
    for item in obj["items"]:
        _item(item, files)
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
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "recipes")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "recipes")


_LIBRARY = {}


def library(folder=None):
    """`{id: recipe}` of the recipes in @p folder (default the built-in ones), each file `<id>.json`. A built-in recipe
    that does not validate is a bug and raises; the result is cached per folder."""
    folder = folder or builtin_dir()
    if folder not in _LIBRARY:
        out = {}
        names = sorted(n for n in os.listdir(folder) if n.endswith(".json")) if os.path.isdir(folder) else []
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
    to a key."""
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
        if bound:
            out.append({"recipe": rec, "state": "part" if missing else "known", "bound": bound, "missing": missing,
                        "similar": {}})
        elif similar:
            out.append({"recipe": rec, "state": "similar", "bound": {}, "missing": missing, "similar": similar})
    return out


def host_file(rec):
    """The recipe file whose entry carries the recipe in the fonts table: the region of the first face's Hangul item."""
    items = {item["id"]: item for item in rec["items"]}
    for face in rec["faces"]:
        if face.get("hangul"):
            return items[face["hangul"]]["region"]
    return rec["files"][0]["id"]


def item_height(rec):
    """The pixel height of the recipe's faces: the glyph height of the first face's Hangul item."""
    items = {item["id"]: item for item in rec["items"]}
    for face in rec["faces"]:
        if face.get("hangul"):
            return items[face["hangul"]]["reading"]["glyph"][1]
    return rec["items"][0]["reading"]["glyph"][1]


def _span(item):
    """The bytes @p item reads from its region's start (offset + through its last glyph)."""
    w, h = item["reading"]["glyph"]
    order = item["reading"].get("order", "rows")
    foot = binscan.glyph_bytes(w, h, order)
    stride = item["reading"].get("stride", foot)
    if item["kind"] == "english":
        count = item.get("count", 256 - item.get("first", 0))
        last = count - 1
    else:
        l0, t0, pitch = item["grid"]
        last = max((lead - l0) * pitch + (trail - t0) for lead, trail, _cp in rawcarve.ks_codes(item["chars"]))
    return item.get("offset", 0) + last * stride + foot


def check_fit(rec):
    """RecipeError when an item's reading does not fit its file (checked when files are bound, not at load)."""
    files = {f["id"]: f for f in rec["files"]}
    for item in rec["items"]:
        if item["kind"] == "ks-grid":
            l0, t0, pitch = item["grid"]
            for lead, trail, _cp in rawcarve.ks_codes(item["chars"]):
                if lead < l0 or not t0 <= trail < t0 + pitch:
                    raise RecipeError("item %s: code %02X%02X is outside its grid" % (item["id"], lead, trail))
        if _span(item) > files[item["region"]]["size"]:
            raise RecipeError("item %s reads past the end of %s" % (item["id"], files[item["region"]]["name"]))


# ---- the planner -----------------------------------------------------------------------------------------------

def _hexa(value):
    return "0x%x" % value


def item_commands(item, src, out, tools_dir):
    """The `rawcarve.py bdf` argv that writes @p item of the file @p src as a Unicode BDF at @p out."""
    r = item["reading"]
    w, h = r["glyph"]
    argv = toolrun.tool("rawcarve", tools_dir) + ["bdf", src]
    if item.get("offset", 0):
        argv += ["--offset", _hexa(item["offset"])]
    argv += ["--glyph", "%dx%d" % (w, h)]
    if r.get("order", "rows") != "rows":
        argv += ["--order", r["order"]]
    if "stride" in r:
        argv += ["--stride", str(r["stride"])]
    if r.get("lsb"):
        argv.append("--lsb")
    if item["kind"] == "ks-grid":
        l0, t0, pitch = item["grid"]
        argv += ["--chars", item["chars"], "--grid", "%s,%s,%d" % (_hexa(l0), _hexa(t0), pitch)]
    else:
        argv += ["--chars", "ascii"]
        if item.get("first", 0):
            argv += ["--first", str(item["first"])]
        if "count" in item and item["count"] != 256 - item.get("first", 0):
            argv += ["--count", str(item["count"])]
    if "ascent" in item:
        argv += ["--ascent", str(item["ascent"])]
    return argv + ["-o", out]


def face_commands(rec, face_name, files, paths, chars_from, tools_dir):
    """The argvs that make face @p face_name of @p rec: its items carved (`rawcarve.py bdf`) into the step's work folder
    (`paths["work"]`), then its route: `bdfface.py --hangul H --ascii A --cell WxH --chars-from LIST -o OUT` for a
    precomposed face, and for a jamo fit the face it reads made as `precomposed.svf` followed by `jamoset.py --layout L
    --from-svf precomposed.svf --mask-font none --check -o OUT`. @p files maps a recipe file id to the bound file's
    absolute path; @p chars_from is the range list. The commands of docs/recipes.md "Korean VGA font ROMs (86Box)"."""
    faces = {face["name"]: face for face in rec["faces"]}
    items = {item["id"]: item for item in rec["items"]}
    face = faces[face_name]
    if face["kind"] == "jamo":
        precomposed = os.path.join(paths["work"], PRECOMPOSED)
        first = face_commands(rec, face["from"], files, dict(paths, out=precomposed), chars_from, tools_dir)
        fit = toolrun.tool("jamoset", tools_dir) + ["--layout", face.get("layout", "844"), "--from-svf", precomposed,
                                                    "--mask-font", "none", "--check", "-o", paths["out"]]
        return first + [fit]
    hangul = items[face["hangul"]]
    english = items[face["english"]]
    for item in (hangul, english):
        if item["region"] not in files:
            raise RecipeError("face %s needs %s" % (face_name, item["region"]))
    hbdf = os.path.join(paths["work"], HANGUL_BDF)
    ebdf = os.path.join(paths["work"], ENGLISH_BDF)
    w, h = hangul["reading"]["glyph"]
    return [item_commands(hangul, files[hangul["region"]], hbdf, tools_dir),
            item_commands(english, files[english["region"]], ebdf, tools_dir),
            toolrun.tool("bdfface", tools_dir) + ["--hangul", hbdf, "--ascii", ebdf, "--cell", "%dx%d" % (w, h),
                                                  "--chars-from", chars_from, "-o", paths["out"]]]
