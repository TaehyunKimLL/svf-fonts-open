#!/usr/bin/env python3
"""Settings: the defaults, the effective values, validation and the step list.

`defaults(fonts)` is what `detect` fills the page with; `effective(fonts, settings, font_id)` is one font's values
with the batch's overlaid by its own; `effective_names` is the whole batch's names for the server (Tasks 13/14);
`validate` refuses a setting a route cannot honour and `run_ready` adds the checks that need the checkout's `svf/`
(an existing name, the chosen licence's bytes); `plan_steps` turns a ready job into the Step dicts (Shared data
shapes) the worker runs. Every path a tool receives is absolute; every face name comes from `effective`'s
suggestions overlaid by the owner's edits.

A Settings dict is `{"batch": ..., "fonts": ...}` and nothing else (Shared data shapes): the font entries
`effective` needs are passed in, never stored. `validate` returns every problem as an error string and never
raises: a wrongly typed body is a 400 at the API, not a 500.

The library assumes `maker/` and `tools/` are on sys.path (the entry points set it).
"""

import datetime
import hashlib
import os
import re
import shutil

import mkfont
import naming
import presets
import routes

BATCH_KEYS = ("dest", "kinds", "layout", "sizes", "bpp", "range", "preset", "options")
FONT_ONLY_KEYS = ("selected", "experimental", "dos_layout", "latin_companion", "licence", "names", "licence_name",
                  "note_name", "instance")
DEFAULT_OPTIONS = {"mkfont": {"cell": None, "ascent": None, "mono_hint": False, "clip_cell": False, "space_advance": None},
                   "jamoset": {"embolden": False, "symbols": False, "jset_version": None}}

# The batch defaults (Global Constraints); `defaults` copies them so an edit never reaches another settings dict.
BATCH_DEFAULTS = {"dest": "dos", "kinds": ["precomposed"], "layout": "844", "sizes": [16], "bpp": [1, 2],
                  "range": "2350", "preset": "plain", "options": DEFAULT_OPTIONS}

_FONT_ONLY_DEFAULTS = {"selected": False, "experimental": False, "dos_layout": None, "latin_companion": None,
                       "licence": None, "names": {}, "licence_name": "", "note_name": "",
                       "instance": None}

# A `names` key: a kind, a size and a bpp, all digits (`effective` ignores a well-formed key outside the selection).
NAME_KEY_RE = re.compile(r"^(precomposed|jamo)/\d+/\d+$")

# `naming.suggest_licence_name` decides `OFL`/`LIC` from the text; a licence file whose own name says `OFL` (the
# repository's `OFL*.txt`, `LICENSE-OFL.txt`) is one too, even when only its first line is at hand (see the report).
_OFL_HINT = "SIL OPEN FONT LICENSE"

RANGE_FILES = (("11172", "hangul"), ("2350", "ksx1001-hangul"))
RANGE_CHARS_PER_LINE = 50
MAX_SIZES = 16                  # a sizes list longer than this would plan more steps than a page can show

# The plan's wording for a source kind (R4): the preset message names the preset's sources, the bpp message the
# font's own. `_source_phrase` adds the article ("a bitmap source", "an outline source", "an SVF source").
_SOURCE_WORDS = {"dos-raw": "DOS raw", "outline": "outline", "outline-composite": "outline", "bitmap": "bitmap",
                 "bdf-iso10646": "bitmap", "bdf-iso8859": "bitmap", "bdf-ksc5601": "bitmap", "bdf-johab": "bitmap",
                 "hbf": "bitmap", "svf-precomposed": "SVF", "svf-jamo": "SVF"}

# The article each source word takes (G2): chosen by the word, not by its first letter (`an SVF`, `a DOS raw`).
_SOURCE_ARTICLES = {"outline": "an", "SVF": "an"}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _source_word(kind):
    return _SOURCE_WORDS.get(kind, kind or "unknown")


def _source_phrase(kind):
    """The plan's article + word for a source kind: `"a bitmap"`, `"an outline"`, `"an SVF"`, `"a DOS raw"`."""
    word = _source_word(kind)
    return "%s %s" % (_SOURCE_ARTICLES.get(word, "a"), word)


def _sources_label(sources):
    """The preset message's label for a list of source kinds: the words, de-duplicated in order."""
    words = []
    for kind in sources:
        word = _source_word(kind)
        if word not in words:
            words.append(word)
    return ", ".join(words)


def _copy_value(value):
    """A copy of a settings value: a list or a dict is never shared with `DEFAULT_OPTIONS` or another font."""
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return {key: _copy_value(item) for key, item in value.items()}
    return value


def _batch_defaults():
    return {key: _copy_value(value) for key, value in BATCH_DEFAULTS.items()}


# ---- defaults --------------------------------------------------------------------------------------------------

def _font_kinds(font):
    """The per-font `kinds` default: `jamo` alone for a native-jamo source, both for a composite TTF, else precomposed."""
    kind = font.get("source_kind")
    if kind in ("dos-raw", "bdf-johab", "svf-jamo"):
        return ["jamo"]
    if kind == "outline-composite":
        return ["precomposed", "jamo"]
    return ["precomposed"]


def _font_layout(font):
    """The per-font `layout` default: the detected one for DOS raw, `adaptive`/`hanterm-johab`, else the batch's 844."""
    kind = font.get("source_kind")
    if kind == "dos-raw":
        candidates = [l for l in (font.get("dos") or {}).get("candidates", []) if l != "none"]
        return candidates[0] if candidates else "844"
    if kind == "outline-composite":
        return "adaptive"
    if kind == "bdf-johab":
        return "hanterm-johab"
    return "844"


def _font_sizes(font):
    """The per-font `sizes` default: the strikes of a fixed-size source, else `[16]`."""
    return list(font.get("sizes") or []) if font.get("sizes_fixed") else [16]


def _font_bpp(font):
    """The per-font `bpp` default: an SVF source's own bpp, `[1, 2]` for an outline source, else `[1]`."""
    if font.get("source_kind") in ("svf-precomposed", "svf-jamo"):
        return [(font.get("svf") or {}).get("bpp")]      # the route pins this bpp, so the default must match it
    return [1, 2] if font.get("source_kind") in ("outline", "outline-composite") else [1]


def _licence_name(family, licence):
    """The suggested `.TXT` name of @p licence (`""` without one).

    `naming.suggest_licence_name` reads the text; a licence entry carries its file's `first_line` (not its whole
    text), so a licence whose own file name carries `OFL` is treated as one too.
    """
    if not licence:
        return ""
    text = licence.get("text") or licence.get("first_line") or ""
    name = os.path.basename(licence.get("path") or "")
    if "OFL" in name.upper():
        text = _OFL_HINT + " " + text
    return naming.suggest_licence_name(family or "", text)


def _font_defaults(font, batch):
    """One font's per-font settings: the font-only keys plus only the batch keys that differ from the batch default."""
    per = {}
    kinds = _font_kinds(font)
    for key, value in (("kinds", kinds), ("dest", "jamo-extra" if kinds == ["jamo"] else "dos"),
                       ("layout", _font_layout(font)), ("sizes", _font_sizes(font)), ("bpp", _font_bpp(font))):
        if value != batch.get(key):
            per[key] = value
    licences = font.get("licences") or []
    per.update({
        "selected": bool(licences) and font.get("source_kind") != "dos-raw",
        "experimental": False,
        "dos_layout": None,
        "latin_companion": (font.get("companions") or [None])[0],
        "licence": {"kind": "upload", "path": licences[0]["path"]} if licences else None,
        "names": {},
        "licence_name": _licence_name(font.get("family", ""), licences[0] if licences else None),
        "note_name": naming.suggest_note_name(font.get("family", "")),
        "instance": None,
    })
    return per


def instance_coords(font, instance):
    """The full `{axis tag: value}` of a variable-font instance: every axis's default, overlaid by @p instance."""
    coords = {axis["tag"]: axis["default"] for axis in (font.get("variable") or {}).get("axes") or []}
    coords.update(instance)
    return coords


def defaults(fonts):
    """The Settings dict `detect` fills (Shared data shapes) for the fonts that have at least one route.

    The batch keys hold the Global Constraints defaults; a per-font dict holds the font-only keys and only those
    batch keys whose per-font default differs from the batch default, so a later batch edit reaches every font that
    did not need a value of its own. The Settings dict is `{"batch", "fonts"}` only: `effective` takes the font
    entries as an argument, so they are never duplicated into `job["settings"]`.
    """
    batch = _batch_defaults()
    settings = {"batch": batch, "fonts": {}}
    for font in fonts:
        if not routes.routes(font):
            continue
        settings["fonts"][font["id"]] = _font_defaults(font, batch)
    return settings


# ---- the effective values --------------------------------------------------------------------------------------

def _merge_options(base, over):
    """The advanced panel's values: the batch's, then the per-font dict's, merged per sub-key.

    A non-dict on either side is ignored here (the type rules report it); the result is always the two tools' dicts.
    """
    out = {}
    for tool in ("mkfont", "jamoset"):
        merged = {}
        for source in (base, over):
            sub = source.get(tool) if isinstance(source, dict) else None
            if isinstance(sub, dict):
                merged.update(sub)
        out[tool] = merged
    return out


def suggested_names(font, eff):
    """`{"<kind>/<size>/<bpp>": <name>}` for the current selection, restricted to what each route pins.

    An SVF source keeps its own stem; every other name comes from `naming.suggest_face_name`. A size or bpp a route
    does not offer gets no key (validation refuses such a selection separately). A wrongly typed kind, size or bpp
    is skipped rather than raised on: the type rules report it and `validate` never raises.
    """
    out = {}
    by_kind = {}
    for route in routes.routes(font):
        by_kind.setdefault(route.kind, route)
    stem = font.get("family") if font.get("source_kind") in ("svf-precomposed", "svf-jamo") else None
    kinds = eff.get("kinds") if isinstance(eff.get("kinds"), list) else []
    sizes = eff.get("sizes") if isinstance(eff.get("sizes"), list) else []
    bpps = eff.get("bpp") if isinstance(eff.get("bpp"), list) else []
    for kind in kinds:
        if not isinstance(kind, str):
            continue
        route = by_kind.get(kind)
        for size in sizes:
            if not _is_int(size):
                continue
            if route is not None and route.sizes is not None and size not in route.sizes:
                continue
            for bpp in bpps:
                if not _is_int(bpp):
                    continue
                if route is not None and bpp not in route.bpps:
                    continue
                out["%s/%d/%d" % (kind, size, bpp)] = naming.suggest_face_name(
                    font.get("family", ""), size, bpp, kind, svf_stem=stem)
    return out


def _effective(settings, font, font_id):
    """One font's effective values: the batch overlaid by its own dict, with the suggestions overlaid by its names.

    A wrongly typed settings dict, batch or per-font entry is read as absent rather than raised on: the type rules
    report it and `validate` never raises.
    """
    batch = settings.get("batch") if isinstance(settings, dict) else None
    batch = batch if isinstance(batch, dict) else {}
    sfonts = settings.get("fonts") if isinstance(settings, dict) else None
    per = sfonts.get(font_id) if isinstance(sfonts, dict) else None
    per = per if isinstance(per, dict) else {}
    eff = {}
    for key in BATCH_KEYS:
        if key == "options":
            continue
        if key in per:
            eff[key] = _copy_value(per[key])
        elif key in batch:
            eff[key] = _copy_value(batch[key])
        else:
            eff[key] = None
    eff["options"] = _merge_options(batch.get("options"), per.get("options"))
    for key in FONT_ONLY_KEYS:
        if key != "names":
            eff[key] = per.get(key, _FONT_ONLY_DEFAULTS[key])
    if font.get("sizes_fixed") and "sizes" not in per:      # a fixed-size source keeps its own strikes
        eff["sizes"] = list(font.get("sizes") or [])
    suggestions = suggested_names(font, eff)
    eff["names"] = dict(suggestions)
    raw_names = per.get("names")
    if isinstance(raw_names, dict):
        for key, value in raw_names.items():                 # a key outside the selection is ignored
            if key in suggestions:
                eff["names"][key] = value
    return eff


def effective(fonts, settings, font_id):
    """One font's effective values; the font entry is looked up in @p fonts (Settings carries no copy of them)."""
    for font in fonts:
        if font.get("id") == font_id:
            return _effective(settings, font, font_id)
    raise KeyError(font_id)


def effective_names(fonts, settings):
    """`{font id: {"<kind>/<size>/<bpp>": <name>}}` for every font that has a route (the server shows these)."""
    out = {}
    sfonts = settings.get("fonts") if isinstance(settings, dict) else None
    if not isinstance(sfonts, dict):
        return out
    for font in fonts:
        font_id = font.get("id")
        if font_id not in sfonts or not routes.routes(font):
            continue
        out[font_id] = dict(_effective(settings, font, font_id).get("names") or {})
    return out


# ---- validation ------------------------------------------------------------------------------------------------

def _font_map(fonts):
    return {font["id"]: font for font in fonts}


def _entry_paths(fonts, formats):
    """The relative paths of the batch entries whose `format` is in @p formats."""
    return {font.get("path") for font in fonts if font.get("format") in formats}


def _licence_paths(fonts):
    """Every upload path a licence may name: the scan's licence candidates and the batch's list files.

    `detect` classifies a `.txt` as `licence`/`list` but a name-only licence such as `COPYING` (no `.txt`) keeps its
    sniffed format, so the candidates the scan found for each font are the reliable set.
    """
    paths = set(_entry_paths(fonts, ("list",)))
    for font in fonts:
        for licence in font.get("licences") or []:
            paths.add(licence.get("path"))
    return paths


def _bad_repo_path(path):
    """True when @p path is not a plain `svf/`-relative `.TXT` path (relative, no `..`, no leading `/`)."""
    if os.path.isabs(path):
        return True
    if any(part in ("", ".", "..") for part in path.split("/")):
        return True
    return not path.upper().endswith(".TXT")


def _mkfont_options(values):
    """The `mkfont` sub-dict of a settings dict's options, or `{}` when it is not an object."""
    options = values.get("options") if isinstance(values, dict) else None
    sub = options.get("mkfont") if isinstance(options, dict) else None
    return sub if isinstance(sub, dict) else {}


def _jamoset_options(values):
    """The `jamoset` sub-dict of a settings dict's options, or `{}` when it is not an object."""
    options = values.get("options") if isinstance(values, dict) else None
    sub = options.get("jamoset") if isinstance(options, dict) else None
    return sub if isinstance(sub, dict) else {}


def _own_option_keys(per):
    """The option keys the font's own options carry (H3): a key it merely inherits is checked as `batch: ...`.

    The two tools' keys are disjoint, so the tool name does not matter here; a wrongly typed `options` is read as
    no keys (the type rules already report it).
    """
    options = per.get("options") if isinstance(per, dict) else None
    keys = set()
    if isinstance(options, dict):
        for sub in options.values():
            if isinstance(sub, dict):
                keys.update(sub)
    return keys


def _option_errors(fid, values, keys=None):
    """The advanced panel's int values: cell 4..255, ascent 0..cell, space_advance 0..255, jset_version 1 or 2.

    @p keys limits the checks to the font's own option keys (H3): a batch value a font inherits unchanged is
    reported once as `batch: ...`, so a font that overrides one key does not repeat the batch's other errors.
    `None` checks every key (the batch's own scope).
    """
    errors = []
    mkfont_options = _mkfont_options(values)
    cell = mkfont_options.get("cell")
    if (keys is None or "cell" in keys) and cell is not None and (not _is_int(cell) or not 4 <= cell <= 255):
        errors.append("%s: cell %s is not 4..255" % (fid, cell))
    ascent = mkfont_options.get("ascent")
    if (keys is None or "ascent" in keys) and ascent is not None and (not _is_int(ascent) or ascent < 0):
        errors.append("%s: ascent %s is not 0..cell" % (fid, ascent))
    advance = mkfont_options.get("space_advance")
    if (keys is None or "space_advance" in keys) and advance is not None and (not _is_int(advance) or not 0 <= advance <= 255):
        errors.append("%s: space_advance %s is not 0..255" % (fid, advance))
    jset_version = _jamoset_options(values).get("jset_version")
    if (keys is None or "jset_version" in keys) and jset_version is not None and (not _is_int(jset_version) or jset_version not in (1, 2)):
        errors.append("%s: jset_version %s is not 1 or 2" % (fid, jset_version))
    return errors


def _ascent_cell_errors(fid, values):
    """The cross-key rule (Task 5 M2): the ascent must fit the cell it is used at.

    The cell is the effective `cell` option when it is an int, else each effective size. The rule runs on every
    font's effective values (H1), whether or not the font carries its own options; a font whose sizes and options
    are the batch's relies on the batch-level report, so `_shape_errors` calls this only when they differ. A wrongly
    typed ascent is the key rule's (H3); a non-list `sizes` is read as no size rather than iterated.
    """
    errors = []
    mkfont_options = _mkfont_options(values)
    ascent = mkfont_options.get("ascent")
    if ascent is None or not _is_int(ascent) or ascent < 0:
        return errors
    cell = mkfont_options.get("cell")
    sizes = values.get("sizes")
    for size in (sizes if isinstance(sizes, list) else []):
        limit = cell if _is_int(cell) else size
        if _is_int(limit) and ascent > limit:
            errors.append("%s: ascent %s is over the cell %s" % (fid, ascent, limit))
            break
    return errors


def _same_as_batch(eff, batch):
    """True when the font's effective sizes and options are the batch's own (its report already covers them, H1)."""
    if eff.get("sizes") != batch.get("sizes"):
        return False
    return eff.get("options") == _merge_options(batch.get("options"), None)


def _options_type_errors(fid, options):
    """The advanced panel's shape: an object of the two tools' objects, every key known, every value the right type."""
    errors = []
    if options is None:
        return errors
    if not isinstance(options, dict):
        return ["%s: options is not an object" % fid]
    for tool, sub in options.items():
        if tool not in DEFAULT_OPTIONS:
            errors.append("%s: unknown option %s" % (fid, tool))
            continue
        if not isinstance(sub, dict):
            errors.append("%s: options %s is not an object" % (fid, tool))
            continue
        for key, value in sub.items():
            if key not in DEFAULT_OPTIONS[tool]:
                errors.append("%s: unknown option key %s.%s" % (fid, tool, key))
                continue
            default = DEFAULT_OPTIONS[tool][key]
            if default is None:
                if value is not None and not _is_int(value):
                    errors.append("%s: option %s.%s is not an int or null" % (fid, tool, key))
            elif not isinstance(value, bool):
                errors.append("%s: option %s.%s is not true or false" % (fid, tool, key))
    return errors


def _batch_type_errors(batch):
    """The batch values' types, checked once as `batch: <key> ...` (G5): a font's own value is checked per font.

    Only the keys the batch actually carries are checked: a missing key is already reported as `batch: missing key`.
    """
    errors = []
    for key in ("dest", "preset", "range"):
        if key in batch and not isinstance(batch.get(key), str):
            errors.append("batch: %s is not a string" % key)
    if "layout" in batch and batch.get("layout") is not None and not isinstance(batch.get("layout"), str):
        errors.append("batch: layout is not a string")
    if "kinds" in batch:
        kinds = batch.get("kinds")
        if not isinstance(kinds, list):
            errors.append("batch: kinds is not a list")
        elif any(not isinstance(kind, str) for kind in kinds):
            errors.append("batch: kinds has a value that is not a string")
    if "sizes" in batch:
        sizes = batch.get("sizes")
        if not isinstance(sizes, list):
            errors.append("batch: sizes is not a list")
        elif any(not _is_int(size) for size in sizes):
            errors.append("batch: sizes has a value that is not an int")
    if "bpp" in batch:
        bpp = batch.get("bpp")
        if not isinstance(bpp, list):
            errors.append("batch: bpp is not a list")
        elif any(not _is_int(value) for value in bpp):
            errors.append("batch: bpp has a value that is not an int")
    errors += _options_type_errors("batch", batch.get("options"))
    return errors


def _type_errors(fid, eff, per):
    """The type rules: a wrongly typed value is refused before `_effective` is trusted or `_shape_errors` runs.

    A batch key is checked here only when the font carries its own value for it (G5): a font that inherits a batch
    value has that value checked once as `batch: <key> ...`, so a bad batch value is not reported per font.
    `options` and `names` are read from the raw dicts (the font's): `_effective` merges them, so the effective
    values alone would hide a wrongly typed source.
    """
    errors = []
    for key in ("dest", "preset", "range"):
        if key in per and not isinstance(eff.get(key), str):
            errors.append("%s: %s is not a string" % (fid, key))
    if "layout" in per:
        value = eff.get("layout")
        if value is not None and not isinstance(value, str):
            errors.append("%s: layout is not a string" % fid)
    for key in ("dos_layout", "latin_companion"):
        value = eff.get(key)
        if value is not None and not isinstance(value, str):
            errors.append("%s: %s is not a string" % (fid, key))
    if "kinds" in per:
        kinds = eff.get("kinds")
        if not isinstance(kinds, list):
            errors.append("%s: kinds is not a list" % fid)
        elif any(not isinstance(kind, str) for kind in kinds):
            errors.append("%s: kinds has a value that is not a string" % fid)
    if "sizes" in per:
        sizes = eff.get("sizes")
        if not isinstance(sizes, list):
            errors.append("%s: sizes is not a list" % fid)
        elif any(not _is_int(size) for size in sizes):
            errors.append("%s: sizes has a value that is not an int" % fid)
    if "bpp" in per:
        bpp = eff.get("bpp")
        if not isinstance(bpp, list):
            errors.append("%s: bpp is not a list" % fid)
        elif any(not _is_int(value) for value in bpp):
            errors.append("%s: bpp has a value that is not an int" % fid)
    instance = eff.get("instance")
    if instance is not None and not (isinstance(instance, dict) and all(
            isinstance(tag, str) and isinstance(value, (int, float)) and not isinstance(value, bool)
            for tag, value in instance.items())):
        errors.append("%s: instance is not an object of axis values" % fid)
    for key in ("selected", "experimental"):
        if not isinstance(eff.get(key), bool):
            errors.append("%s: %s is not true or false" % (fid, key))
    for key in ("licence_name", "note_name"):                 # H5: a non-str name, a falsy one included
        if not isinstance(eff.get(key), str):
            errors.append("%s: %s is not a string" % (fid, key))
    errors += _options_type_errors(fid, per.get("options"))
    names = per.get("names", eff.get("names"))
    if not isinstance(names, dict):
        errors.append("%s: names is not an object" % fid)
    elif any(not isinstance(value, str) for value in names.values()):
        errors.append("%s: names has a value that is not a string" % fid)
    licence = eff.get("licence")
    if licence is not None:
        if not isinstance(licence, dict):
            errors.append("%s: licence is not an object" % fid)
        else:
            if licence.get("path") is not None and not isinstance(licence.get("path"), str):
                errors.append("%s: licence path is not a string" % fid)
            if licence.get("text") is not None and not isinstance(licence.get("text"), str):
                errors.append("%s: licence text is not a string" % fid)
    return errors


def _shape_errors(fid, font, eff, per, batch, fonts, upload_dir):
    """The value-shape rules: they apply to every font, selected or not (the types are already checked).

    A batch key is checked here only when the font carries its own value for it (G5); an inherited batch value is
    checked once by `_batch_shape_errors` as `batch: <key> ...`. A per-font option error is reported only for a key
    the font's own options carry (H3); the cross-key ascent rule runs on the effective values (H1), under the font's
    id only when its sizes or options differ from the batch's (the batch report covers the equal case).
    """
    errors = []
    dest = eff.get("dest")
    if "dest" in per and (not isinstance(dest, str) or not naming.DEST_RE.match(dest)):
        errors.append("%s: dest %s is not dos, jamo-extra, games/<name> or new/<name>" % (fid, dest))
    kinds = eff.get("kinds")
    if "kinds" in per and (not isinstance(kinds, list) or not kinds
                           or any(kind not in ("precomposed", "jamo") for kind in kinds)):
        errors.append("%s: kinds %s is not a non-empty subset of precomposed jamo" % (fid, kinds))
    elif "kinds" in per and len(set(kinds)) != len(kinds):
        errors.append("%s: kinds has a repeated value" % fid)
    sizes = eff.get("sizes")
    if "sizes" in per and (not isinstance(sizes, list) or not sizes):
        errors.append("%s: sizes is not a non-empty list of ints" % fid)
    elif "sizes" in per:
        bad = [size for size in sizes if not _is_int(size) or not 6 <= size <= 96]
        for size in bad:
            errors.append("%s: size %s is not 6..96" % (fid, size))
        if not bad:
            if len(sizes) > MAX_SIZES:
                errors.append("%s: sizes has more than %d entries" % (fid, MAX_SIZES))
            if len(set(sizes)) != len(sizes):
                errors.append("%s: sizes has a repeated value" % fid)
    bpps = eff.get("bpp")
    if "bpp" in per and (not isinstance(bpps, list) or not bpps
                         or any(not _is_int(bpp) or bpp not in (1, 2) for bpp in bpps)):
        errors.append("%s: bpp %s is not a non-empty subset of 1 2" % (fid, bpps))
    elif "bpp" in per and len(set(bpps)) != len(bpps):
        errors.append("%s: bpp has a repeated value" % fid)
    rng = eff.get("range")
    if "range" in per and rng not in ("11172", "2350"):
        if rng not in _entry_paths(fonts, ("list",)) or (upload_dir and not os.path.isfile(os.path.join(upload_dir, rng))):
            errors.append("%s: range %s is not 11172, 2350 or a list file in the batch" % (fid, rng))
    if "preset" in per and eff.get("preset") not in presets.PRESETS:
        errors.append("%s: unknown preset %s" % (fid, eff.get("preset")))
    errors += _option_errors(fid, eff, _own_option_keys(per))
    if not _same_as_batch(eff, batch):
        errors += _ascent_cell_errors(fid, eff)
    raw_names = per.get("names") if isinstance(per, dict) else None
    for key in (raw_names if isinstance(raw_names, dict) else {}):
        if not isinstance(key, str) or not NAME_KEY_RE.match(key):
            errors.append("%s: name key %s is not <kind>/<size>/<bpp>" % (fid, key))
    for name in sorted((eff.get("names") or {}).values()):
        if not isinstance(name, str) or not naming.NAME_RE.match(name):
            errors.append("%s: name %s is not [A-Z0-9]{1,8}.SVF" % (fid, name))
    for key in ("licence_name", "note_name"):
        value = eff.get(key) or ""
        if value and (not isinstance(value, str) or not naming.TXT_RE.match(value)):
            errors.append("%s: %s %s is not [A-Z0-9]{1,8}.TXT" % (fid, key, value))
    licence = eff.get("licence")
    if licence is not None:
        if not isinstance(licence, dict) or licence.get("kind") not in ("upload", "repo", "text"):
            errors.append("%s: licence kind %s is not upload, repo or text"
                          % (fid, licence.get("kind") if isinstance(licence, dict) else licence))
        elif licence["kind"] == "upload":
            if licence.get("path") not in _licence_paths(fonts):
                errors.append("%s: licence %s is not a licence file in the batch" % (fid, licence.get("path")))
            elif upload_dir:
                try:
                    size = os.path.getsize(os.path.join(upload_dir, licence.get("path") or ""))
                except OSError:
                    size = None
                if size == 0:
                    errors.append("%s: licence text is empty" % fid)
        elif licence["kind"] == "text":
            if not isinstance(licence.get("text"), str) or not licence["text"].strip():
                errors.append("%s: licence text is empty" % fid)
        elif licence["kind"] == "repo":
            path = licence.get("path")
            if not isinstance(path, str) or _bad_repo_path(path):
                errors.append("%s: licence path %s is not a text file in svf/" % (fid, path))
    companion = eff.get("latin_companion")
    if companion is not None and companion not in (font.get("companions") or []):
        errors.append("%s: latin_companion %s is not a companion of this font" % (fid, companion))
    if eff.get("selected") and font.get("source_kind") == "bdf-ksc5601" and companion is None:
        errors.append("%s: needs a Latin companion" % fid)
    return errors


def _batch_shape_errors(batch, fonts, upload_dir):
    """The batch values' shapes, checked once as `batch: <key> ...` (G5), even when no font inherits them.

    Only the keys the batch actually carries are checked; the font-only keys are never batch keys.
    """
    errors = []
    dest = batch.get("dest")
    if "dest" in batch and (not isinstance(dest, str) or not naming.DEST_RE.match(dest)):
        errors.append("batch: dest %s is not dos, jamo-extra, games/<name> or new/<name>" % dest)
    kinds = batch.get("kinds")
    if "kinds" in batch and (not isinstance(kinds, list) or not kinds
                             or any(kind not in ("precomposed", "jamo") for kind in kinds)):
        errors.append("batch: kinds %s is not a non-empty subset of precomposed jamo" % kinds)
    elif "kinds" in batch and len(set(kinds)) != len(kinds):
        errors.append("batch: kinds has a repeated value")
    sizes = batch.get("sizes")
    if "sizes" in batch and (not isinstance(sizes, list) or not sizes):
        errors.append("batch: sizes is not a non-empty list of ints")
    elif "sizes" in batch:
        bad = [size for size in sizes if not _is_int(size) or not 6 <= size <= 96]
        for size in bad:
            errors.append("batch: size %s is not 6..96" % size)
        if not bad:
            if len(sizes) > MAX_SIZES:
                errors.append("batch: sizes has more than %d entries" % MAX_SIZES)
            if len(set(sizes)) != len(sizes):
                errors.append("batch: sizes has a repeated value")
    bpps = batch.get("bpp")
    if "bpp" in batch and (not isinstance(bpps, list) or not bpps
                           or any(not _is_int(bpp) or bpp not in (1, 2) for bpp in bpps)):
        errors.append("batch: bpp %s is not a non-empty subset of 1 2" % bpps)
    elif "bpp" in batch and len(set(bpps)) != len(bpps):
        errors.append("batch: bpp has a repeated value")
    rng = batch.get("range")
    if "range" in batch and rng not in ("11172", "2350"):
        if rng not in _entry_paths(fonts, ("list",)) or (upload_dir and not os.path.isfile(os.path.join(upload_dir, rng))):
            errors.append("batch: range %s is not 11172, 2350 or a list file in the batch" % rng)
    if "preset" in batch and batch.get("preset") not in presets.PRESETS:
        errors.append("batch: unknown preset %s" % batch.get("preset"))
    if "options" in batch:
        errors += _option_errors("batch", batch)
        errors += _ascent_cell_errors("batch", batch)
    return errors


def _route_errors(fid, font, eff, fmap=None):
    """The route rules, on the effective values: what each selected font's routes can honour.

    An effective value may be a batch value the type rules refused (the font does not override it), so `kinds`,
    `sizes`, `bpp` and `preset` are read defensively here rather than iterated or hashed blindly.
    """
    errors = []
    kinds = eff.get("kinds")
    if not isinstance(kinds, list) or any(not isinstance(kind, str) for kind in kinds):
        return errors
    sizes = eff.get("sizes")
    sizes = sizes if isinstance(sizes, list) else []
    bpps = eff.get("bpp")
    bpps = bpps if isinstance(bpps, list) else []
    by_kind = {}
    for route in routes.routes(font):
        by_kind.setdefault(route.kind, []).append(route)
    for kind in kinds:
        route = routes.route_for(font, kind, bool(eff.get("experimental")))
        if route is None:
            if by_kind.get(kind):
                errors.append("%s: %s needs experimental on a precomposed font" % (fid, kind))
            else:
                errors.append("%s: no %s route" % (fid, kind))
            continue
        if font.get("sizes_fixed") and route.sizes is not None:
            strikes = ", ".join(str(size) for size in font.get("sizes") or [])
            for size in sizes:
                if size not in route.sizes:
                    errors.append("%s: size %s is not a strike (%s)" % (fid, size, strikes))
        for bpp in bpps:
            if bpp not in route.bpps:
                errors.append("%s: bpp %s is not offered for %s source" % (fid, bpp, _source_phrase(font.get("source_kind"))))
        if kind == "jamo" and font.get("source_kind") != "dos-raw" and route.layouts and eff.get("layout") not in route.layouts:
            errors.append("%s: layout %s is not offered for %s" % (fid, eff.get("layout"), kind))   # F7: dos_layout covers dos-raw
    if font.get("source_kind") == "dos-raw":
        candidates = [l for l in (font.get("dos") or {}).get("candidates", []) if l != "none"]
        if eff.get("dos_layout") is None:
            errors.append("%s: confirm the DOS Johab layout" % fid)
        elif eff.get("dos_layout") not in candidates:
            errors.append("%s: dos_layout %s is not one of %s" % (fid, eff.get("dos_layout"), ", ".join(candidates)))
    if font.get("source_kind") == "dos-raw" and "precomposed" in kinds:
        route = routes.route_for(font, "precomposed", False)
        if route is not None and route.label == "johab844":
            if eff.get("dos_layout") not in (None, "844"):
                errors.append("%s: johab844 needs layout 844" % fid)
            companion = (fmap or {}).get(eff.get("latin_companion")) if isinstance(eff.get("latin_companion"), str) else None
            if companion and (companion.get("eng") or {}).get("cell") == "12x24":
                errors.append("%s: johab844 takes an 8x16 English font" % fid)
    instance = eff.get("instance")
    if isinstance(instance, dict):
        axes = {axis["tag"]: axis for axis in (font.get("variable") or {}).get("axes") or []}
        if not axes:
            errors.append("%s: instance needs a variable font" % fid)
        for tag, value in instance.items():
            if axes and tag not in axes:
                errors.append("%s: instance axis %s is not in the font" % (fid, tag))
            elif axes and not axes[tag]["min"] <= value <= axes[tag]["max"]:
                errors.append("%s: instance %s=%g is outside %g..%g" % (fid, tag, value, axes[tag]["min"], axes[tag]["max"]))
    preset_name = eff.get("preset")
    preset = presets.PRESETS.get(preset_name) if isinstance(preset_name, str) else None
    if preset is not None:
        if font.get("source_kind") not in preset["sources"]:
            errors.append("%s: preset %s is for %s sources" % (fid, preset_name, _sources_label(preset["sources"])))
        if preset["bpp"] is not None and preset["bpp"] != bpps:
            errors.append("%s: preset %s needs bpp %s" % (fid, preset_name, preset["bpp"]))
        layout = eff.get("dos_layout") if font.get("source_kind") == "dos-raw" else eff.get("layout")
        if preset["layout"] is not None and preset["layout"] != layout:
            errors.append("%s: preset %s is for layout %s" % (fid, preset_name, preset["layout"]))
    for key in ("licence_name", "note_name"):                 # a selected font needs both (F3)
        value = eff.get(key) or ""
        if not value:                                         # G3: a bad non-empty value is the shape rule's, once
            errors.append("%s: %s %s is not [A-Z0-9]{1,8}.TXT" % (fid, key, value))
    return errors


def validate(fonts, settings, upload_dir=None):
    """Every problem with @p settings as `"<font id>: <reason>"` (or `"batch: <reason>"`), in the plan's order.

    The structural rules come first for every font and the batch (an unknown font id, an unknown top-level or
    per-font key, a missing batch key), then the batch values' types and shapes once as `batch: <key> ...`, then
    the value types and shapes for every font, selected or not, then the route rules for the selected ones. A font
    whose types are wrong skips its shape and route rules: a body a client can PUT is refused as a list of errors,
    never as an exception. A batch key a font does not override is checked only at the batch scope (G5); a font's
    own value is checked under its own id. `upload_dir` is where the batch was uploaded (a list file's own path is
    checked there); `None` skips the disk checks. Every problem is reported once, in the plan's order (G3).
    """
    if not isinstance(settings, dict):
        return ["settings: not an object"]
    errors = []
    batch = settings.get("batch")
    sfonts = settings.get("fonts")
    if not isinstance(batch, dict):
        errors.append("batch: not an object")
    if not isinstance(sfonts, dict):
        errors.append("fonts: not an object")
    for key in settings:
        if key not in ("batch", "fonts"):
            errors.append("settings: unknown key %s" % key)
    if not isinstance(batch, dict) or not isinstance(sfonts, dict):
        return errors
    fmap = _font_map(fonts)
    for fid in sfonts:
        if fid not in fmap:
            errors.append("unknown font id %s" % fid)
    for fid, per in sfonts.items():
        if not isinstance(per, dict):
            errors.append("%s: not an object" % fid)
            continue
        for key in per:
            if key not in BATCH_KEYS and key not in FONT_ONLY_KEYS:
                errors.append("%s: unknown key %s" % (fid, key))
    for key in batch:
        if key not in BATCH_KEYS:
            errors.append("batch: unknown key %s" % key)
    for key in BATCH_KEYS:
        if key not in batch:
            errors.append("batch: missing key %s" % key)
    batch_type = _batch_type_errors(batch)
    errors += batch_type
    if not batch_type:                                       # a wrongly typed batch value is not shape-checked (G5)
        errors += _batch_shape_errors(batch, fonts, upload_dir)
    shaped = []
    for fid, per in sfonts.items():
        if fid not in fmap or not isinstance(per, dict):
            continue
        eff = _effective(settings, fmap[fid], fid)
        type_errors = _type_errors(fid, eff, per)
        if type_errors:
            errors += type_errors
            continue
        shaped.append((fid, eff))
        errors += _shape_errors(fid, fmap[fid], eff, per, batch, fonts, upload_dir)
    for fid, eff in shaped:
        if eff.get("selected"):
            errors += _route_errors(fid, fmap[fid], eff, fmap)
    return list(dict.fromkeys(errors))                       # G3: each problem is reported once, order kept


# ---- ready to run ----------------------------------------------------------------------------------------------

def _licence_sha(index, licence, upload_dir, licence_paths):
    """The sha256 hex digest of the chosen licence's bytes, or `None` when it cannot be established.

    A `repo` licence is the file's bytes under `svf/` (the index, which never follows a symlink); a `text` licence
    is its text as UTF-8; an `upload` licence is hashed in chunks from its file under `upload_dir`, but only when it
    is one of the batch's own licence/list/text entries (G1), its real path is under `realpath(upload_dir)` and it
    is a regular file. A wrongly typed or unresolvable licence counts as "no bytes" (`None`), never "equal".
    """
    if not isinstance(licence, dict):
        return None
    kind = licence.get("kind")
    if kind == "repo":
        path = licence.get("path")
        if not isinstance(path, str):
            return None
        try:
            return index.sha_of(path)
        except ValueError:
            return None
    if kind == "text":
        text = licence.get("text")
        if not isinstance(text, str):
            return None
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    if kind == "upload":
        path = licence.get("path")
        if not isinstance(path, str) or path not in licence_paths:
            return None
        root = os.path.realpath(upload_dir)
        abs_path = os.path.realpath(os.path.join(upload_dir, path))
        if not abs_path.startswith(root + os.sep) or not os.path.isfile(abs_path):
            return None
        try:
            digest = hashlib.sha256()
            with open(abs_path, "rb") as f:
                while True:
                    chunk = f.read(naming.CHUNK_BYTES)
                    if not chunk:
                        break
                    digest.update(chunk)
        except OSError:
            return None
        return digest.hexdigest()
    return None


def _licence_present_ok(index, dest, licence_name, licence, upload_dir, licence_paths):
    """True when the chosen licence's bytes equal the destination's `svf/<dest>/<licence_name>`.

    The existing file's sha comes from the index (the walk's on-disk spelling of the name); the chosen licence's
    comes from `_licence_sha`. Anything the index cannot read, or a licence with no bytes, counts as "not equal";
    no path `validate` refused is opened.
    """
    on_disk = None
    for text in index.texts:
        if os.path.dirname(text["path"]) == dest and os.path.basename(text["path"]).upper() == licence_name.upper():
            on_disk = text["path"]
            break
    if on_disk is None:
        return False
    try:
        existing = index.sha_of(on_disk)
    except ValueError:
        return False
    if existing is None:
        return False
    return _licence_sha(index, licence, upload_dir, licence_paths) == existing


def _clash_errors(selected, index, upload_dir, licence_paths):
    """The names two selected fonts would share in one destination, and a font's own licence/note clash (H2).

    Every selected font contributes its `licence_name` (a licence entry) and its `note_name` (a note entry) to its
    destination. Two entries with the same name (case-insensitively) are refused, unless both are licence entries
    whose chosen bytes are equal (two faces of one family sharing one OFL). A font whose own `licence_name` equals
    its own `note_name` is refused under its id, once.
    """
    errors = []
    by_dest = {}
    for fid, _font, eff in selected:
        dest = eff.get("dest")
        if not isinstance(dest, str):
            continue
        licence_name = eff.get("licence_name")
        note_name = eff.get("note_name")
        licence_name = licence_name if isinstance(licence_name, str) else ""
        note_name = note_name if isinstance(note_name, str) else ""
        if licence_name and note_name and licence_name.upper() == note_name.upper():
            errors.append("%s: licence_name and note_name are the same" % fid)
            note_name = ""                                   # one name; the font-level message above covers it
        if licence_name:
            by_dest.setdefault(dest, []).append((licence_name, "licence", eff.get("licence")))
        if note_name:
            by_dest.setdefault(dest, []).append((note_name, "note", None))
    for dest, entries in by_dest.items():
        groups = {}
        for name, kind, licence in entries:
            groups.setdefault(name.upper(), []).append((name, kind, licence))
        for group in groups.values():
            if len(group) < 2:
                continue
            name = group[0][0]
            if all(kind == "licence" for _, kind, _ in group):
                shas = [_licence_sha(index, licence, upload_dir, licence_paths) for _, _, licence in group]
                if all(sha is not None for sha in shas) and len(set(shas)) == 1:
                    continue                                 # one OFL shared by a family is legitimate
                errors.append("%s is used twice in svf/%s with different texts" % (name, dest))
            else:
                errors.append("%s is used twice in svf/%s" % (name, dest))
    return errors


def run_ready(fonts, settings, index, upload_dir):
    """`validate`'s rules plus the ones the checkout decides: a missing licence, a name `svf/` already holds.

    `upload_dir` is required (Task 13 passes `<job_dir>/upload`): an `upload` licence's bytes must be compared with
    the destination's, so a name clash with other bytes is refused here, not overwritten later. Passing `None` is a
    caller's bug and raises at once (G4). `validate`'s list is returned unchanged, then this function's own new
    errors, each at most once (G3).
    """
    if upload_dir is None:
        raise TypeError("run_ready needs upload_dir")
    errors = validate(fonts, settings, upload_dir)

    def add(message):
        if message not in errors:
            errors.append(message)

    if not isinstance(settings, dict):
        return errors
    sfonts = settings.get("fonts")
    if not isinstance(sfonts, dict):
        return errors
    fmap = _font_map(fonts)
    selected = []
    for fid, per in sfonts.items():
        if fid not in fmap or not isinstance(per, dict):
            continue
        eff = _effective(settings, fmap[fid], fid)
        if eff.get("selected"):
            selected.append((fid, fmap[fid], eff))
    if not selected:
        add("batch: nothing selected")
    licence_paths = _licence_paths(fonts)
    text_paths = {text["path"] for text in index.texts}
    for fid, font, eff in selected:
        licence = eff.get("licence")
        repo_missing = False
        if licence is None:
            add("%s: no licence" % fid)
        elif isinstance(licence, dict) and licence.get("kind") == "repo":
            path = licence.get("path")
            if not isinstance(path, str) or path not in text_paths:
                add("%s: licence path %s is not a text file in svf/" % (fid, path))
                repo_missing = True
        names = [name for name in (eff.get("names") or {}).values() if isinstance(name, str)]
        if len(names) == len(eff.get("names") or {}):
            try:
                naming.note_text(font.get("family") or "", font.get("style") or "", sorted(names),
                                 os.path.basename(font.get("path", "")), font.get("version") or "",
                                 datetime.date.today().isoformat(), [])
            except ValueError as exc:
                add("%s: note: %s" % (fid, exc))
        dest = eff.get("dest")
        if not isinstance(dest, str):
            continue
        if dest in index.unlisted:
            add("%s: svf/%s could not be read; choose another folder" % (fid, dest))
            continue
        known = index.names.get(dest, ())
        for name in sorted(names):
            if name.upper() in known:
                add("%s: %s already exists in svf/%s; choose another name" % (fid, name, dest))
        note_name = eff.get("note_name") or ""
        if isinstance(note_name, str) and note_name and note_name.upper() in known:
            add("%s: %s already exists in svf/%s; choose another name" % (fid, note_name, dest))
        licence_name = eff.get("licence_name") or ""
        if (isinstance(licence_name, str) and licence_name and licence_name.upper() in known
                and not repo_missing):
            if not _licence_present_ok(index, dest, licence_name, licence, upload_dir, licence_paths):
                add("%s: %s already exists in svf/%s; choose another name" % (fid, licence_name, dest))
    all_names = []
    for fid, font, eff in selected:
        all_names += [name for name in (eff.get("names") or {}).values() if isinstance(name, str)]
    for name in naming.duplicates(all_names):
        add("name %s is used twice" % name)
    for message in _clash_errors(selected, index, upload_dir, licence_paths):
        add(message)
    return errors


# ---- the range and the steps -----------------------------------------------------------------------------------

def range_spec(eff, upload_dir):
    """A font's range as `mkfont`/`bdfface` take it: a named set, or `("file", <the upload's own path>)`."""
    rng = eff.get("range")
    if rng == "11172":
        return ("11172", None)
    if rng == "2350":
        return ("2350", None)
    return ("file", os.path.join(upload_dir, rng) if rng else None)


def write_range_files(work_dir):
    """Write the two named ranges as UTF-8 text, 50 characters a line, and return `{"11172": abs, "2350": abs}`.

    `mkfont --unicode` and `bdfface --chars-from` read a list file character by character, so a named range is a
    file too and no `--unicode` value has to name a comma-split set.
    """
    os.makedirs(work_dir, exist_ok=True)
    out = {}
    for name, named in RANGE_FILES:
        points = mkfont.NAMED_RANGES[named]()
        lines = ["".join(chr(cp) for cp in points[i:i + RANGE_CHARS_PER_LINE])
                 for i in range(0, len(points), RANGE_CHARS_PER_LINE)]
        path = os.path.join(work_dir, "range-%s.txt" % name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        out[name] = path
    return out


def _upload_path(fid, rel, upload_dir):
    """The absolute path of a font's own relative path, refused when it does not resolve under `upload_dir` (H4).

    The same realpath check the range gets: an entry (or a companion) the scan never meant to name must not let a
    tool read a file outside the batch's upload folder.
    """
    root = os.path.realpath(upload_dir)
    abs_path = os.path.join(upload_dir, rel) if isinstance(rel, str) else None
    if abs_path is None or not os.path.realpath(abs_path).startswith(root + os.sep):
        raise ValueError("%s: %s is outside the upload" % (fid, rel))
    return abs_path


def _step(sid, fid, kind, size, bpp, layout, name, argv, output):
    """One Step dict (Shared data shapes), `pending`."""
    return {"id": sid, "font": fid, "kind": kind, "size": size, "bpp": bpp, "layout": layout, "name": name,
            "argv": argv, "output": output, "state": "pending", "exit": None, "seconds": None, "error": None,
            "stderr_tail": "", "facts": None, "quality": None, "identical_to": None, "preview": None}


def plan_steps(job, job_dir, tools_dir, upload_dir):
    """The Step dicts of every selected font, kind, size and bpp, in run order (Shared data shapes).

    Font order, then `precomposed` before `jamo`, then ascending size, then ascending bpp (whatever order the
    settings lists are in); a composite font gets one `prepare` step per layout before its jamo steps. A named range
    is written once under `work/`; an uploaded list is copied under `work/<font id>/range.txt` and that copy is
    passed, never the upload's own name (a comma in it would inject a range into `mkfont --unicode`, which is
    comma-split). A `("file", ...)` range must resolve under `upload_dir`, a selected KSC font with no companion
    is refused before any command is built, and a step without an effective name raises `ValueError` rather than
    being written to a made-up `out.svf` (G8): `plan_steps` never calls `commands` for a font a route cannot honour.
    """
    fonts = job.get("fonts") or []
    settings = job.get("settings") or {}
    fmap = _font_map(fonts)
    sfonts = settings.get("fonts") or {}
    work_root = os.path.join(job_dir, "work")
    os.makedirs(work_root, exist_ok=True)
    range_files = None
    base = os.path.join(os.path.dirname(tools_dir), "svf", routes.JOHAB844_BASE)
    steps = []
    counter = 0
    for font in fonts:
        fid = font["id"]
        if fid not in sfonts:
            continue
        eff = _effective(settings, font, fid)
        if not eff.get("selected"):
            continue
        src = _upload_path(fid, font.get("path"), upload_dir)
        rkind, rabs = range_spec(eff, upload_dir)
        if rkind == "file":
            root = os.path.realpath(upload_dir)
            if not isinstance(rabs, str) or not os.path.realpath(rabs).startswith(root + os.sep):
                raise ValueError("%s: range %s is not under the upload directory" % (fid, eff.get("range")))
            copy_dir = os.path.join(work_root, fid)
            os.makedirs(copy_dir, exist_ok=True)
            range_file = os.path.join(copy_dir, "range.txt")
            shutil.copyfile(rabs, range_file)
            range_arg = ("file", range_file)
        else:
            if range_files is None:
                range_files = write_range_files(work_root)
            range_file = range_files[rkind]
            range_arg = (rkind, None)
        ops = list(font.get("prep") or [])
        if eff.get("instance") is not None:
            ops.append({"op": "instance", "coords": instance_coords(font, eff["instance"])})
        if ops:                                          # the font's source step: every later step reads its file
            counter += 1
            sid = "s%02d" % counter
            step_dir = os.path.join(work_root, sid)
            os.makedirs(step_dir, exist_ok=True)
            argvs, prepared = routes.source_commands(ops, src, step_dir, tools_dir)
            steps.append(_step(sid, fid, "source", None, None, None, None, argvs,
                               "work/%s/%s" % (sid, os.path.basename(prepared))))
            src = prepared
        companion = eff.get("latin_companion")
        if font.get("source_kind") == "bdf-ksc5601" and companion is None:
            raise ValueError("%s: needs a Latin companion" % fid)
        companion_abs = _upload_path(fid, fmap[companion].get("path"), upload_dir) if companion in fmap else None
        master = None
        prepared = set()
        for kind in ("precomposed", "jamo"):
            if kind not in (eff.get("kinds") or []):
                continue
            route = routes.route_for(font, kind, bool(eff.get("experimental")))
            if route is None:
                continue
            layout = eff.get("dos_layout") if font.get("source_kind") == "dos-raw" else eff.get("layout")
            if kind == "jamo" and route.prepare is not None and layout not in prepared:
                prepared.add(layout)
                counter += 1
                sid = "s%02d" % counter
                step_dir = os.path.join(work_root, sid)
                os.makedirs(step_dir, exist_ok=True)
                master = os.path.join(step_dir, "master.json")
                paths = {"tools": tools_dir, "src": src, "out": master,
                         "work": step_dir, "eng": companion_abs, "latin": companion_abs, "master": master,
                         "range_file": range_file, "base": base}
                steps.append(_step(sid, fid, "prepare", None, None, layout, None,
                                   route.prepare_commands(font, layout, paths), "work/%s/master.json" % sid))
            for size in sorted(eff.get("sizes") or []):
                if route.sizes is not None and size not in route.sizes:
                    continue
                for bpp in sorted(eff.get("bpp") or []):
                    if bpp not in route.bpps:
                        continue
                    counter += 1
                    sid = "s%02d" % counter
                    step_dir = os.path.join(work_root, sid)
                    os.makedirs(step_dir, exist_ok=True)
                    name = eff["names"].get("%s/%d/%d" % (kind, size, bpp))
                    if not name:                                 # G8: a direct caller must not get an unnamed face
                        raise ValueError("%s: no name for %s/%d/%d" % (fid, kind, size, bpp))
                    out = os.path.join(step_dir, name)
                    # a copy step (an SVF source) is not a jamo fit: it carries no layout of its own (F9)
                    step_layout = None if kind == "precomposed" or route.label == "copy" else layout
                    paths = {"tools": tools_dir, "src": src, "out": out,
                             "work": step_dir, "eng": companion_abs, "latin": companion_abs, "master": master,
                             "range_file": range_file, "base": base}
                    extra = routes.apply_flags(presets.argv_for(eff.get("preset"), kind, size),
                                               presets.panel_argv(eff.get("options"), kind, route.label, bpp))
                    try:
                        argv = route.commands(font, size, bpp, step_layout, range_arg, paths, extra)
                    except ValueError as exc:
                        raise ValueError("%s: %s" % (fid, exc))
                    steps.append(_step(sid, fid, kind, size, bpp, step_layout, name, argv,
                                       "work/%s/%s" % (sid, name)))
    return steps
