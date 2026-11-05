#!/usr/bin/env python3
"""Routes: one font entry's source kind -> the tool commands that make its faces.

`routes(font)` lists the `Route`s a font entry (Shared data shapes) offers, in the order the page shows them.
A `Route` names a tool and carries the closures that build one size and bpp's argv; the worker runs each argv and
copies `paths["out"]` on, so nothing here writes a file. `apply_flags` is how a preset or the advanced panel
overrides a route's own flag: the new value replaces the route's and moves to the end.

The library assumes `maker/` and `tools/` are on sys.path (the entry points set it).

The segmentation project adds one `Route(kind="jamo", label="segmented")` here and touches nothing else.
"""

import os
import sys
from dataclasses import dataclass

import detect

PY = [sys.executable, "-P"]

# The 16x16 1 bpp base face johab844.py redraws the Hangul of (relative to the checkout's svf/).
JOHAB844_BASE = "dos/NEODG16.SVF"

# The maker's own source-conversion CLI (a TTC face, a PCF as BDF): tools/ has no tool for those two.
SRCPREP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "srcprep.py")

# A flag whose next token is its value: `apply_flags` removes the old value with the old flag.
VALUED = frozenset({"--cell", "--ascent", "--space-advance", "--unicode", "--width", "--punct-extra", "--eng",
                    "--size", "--bpp", "--layout", "--binarize", "--face", "--threshold", "--jset-version",
                    "--baseline", "--aa-refine", "--mask-font", "--mask-radius", "--hangul-ascent", "--pylib",
                    "--report"})

# The routes whose fit is jamovec.py (its --binarize takes threshold and ridge only).
JAMOVEC_LABELS = frozenset({"composite", "vector fit"})


def apply_flags(argv, extra):
    """@p argv with every flag in @p extra set to extra's value, appended in extra's order.

    A flag in `extra` replaces an earlier occurrence of the same flag (and, for a `VALUED` flag, its value);
    positional tokens keep their places, so `mkfont.py`'s input and output stay argv[0] and argv[1] of the tool.
    A `VALUED` flag with no value (the end of `extra`, or another flag next) is refused: a half-read panel value
    must not silently drop the flag or swallow the next one.
    """
    out = list(argv)
    i = 0
    while i < len(extra):
        token = extra[i]
        if token in VALUED:
            if i + 1 >= len(extra) or extra[i + 1].startswith("--"):
                raise ValueError("%s needs a value" % token)
            value = extra[i + 1]
        else:
            value = None
        j = 0
        while j < len(out):
            if out[j] == token and token.startswith("--"):
                del out[j]
                if value is not None and j < len(out) and not out[j].startswith("--"):
                    del out[j]              # the old flag's value went with it
            else:
                j += 1
        out.append(token)
        if value is not None:
            out.append(value)
            i += 2
        else:
            i += 1
    return out


@dataclass
class Route:
    """One way to make a font's faces: a kind (`precomposed` | `jamo`), a label, and the argv it builds.

    `native` is true when the source kind is exactly what the route makes (so it needs no fit); `layouts` are the
    `jamoset.py` layouts it offers (empty for a precomposed route); `bpps` and `sizes` bound what the page may ask
    (`sizes` None = any size 6..96); `reference` names the source a fit's numbers are compared against.
    """

    kind: str
    label: str
    native: bool
    layouts: list
    bpps: list
    sizes: object
    reference: object
    prepare: object
    commands: object

    def prepare_commands(self, font, layout, paths):
        """The commands to run once per font and layout before any size; `[]` for every route but composite."""
        if self.prepare is None:
            return []
        return self.prepare(font, layout, paths)


def _tool(paths, name):
    return os.path.join(paths["tools"], name)


def _with_extra(commands, extras):
    """@p extras (one flag list per command, as `presets.panel_argv` gives them) applied to the last `len(extras)`
    commands of @p commands; `[]` leaves them as they are. The last command is the one that writes the face."""
    extras = list(extras or [])
    if len(extras) > len(commands):
        extras = extras[len(extras) - len(commands):]
    for i, extra in enumerate(extras, start=len(commands) - len(extras)):
        if extra:
            commands[i] = apply_flags(commands[i], extra)
    return commands


def _flat(extras):
    """The fragments of @p extras as one flag list (a route that reads a flag's value, not only appends it)."""
    return [token for fragment in (extras or []) for token in fragment]


def _mkfont_unicode(range_spec, paths):
    """mkfont.py's `--unicode` value for a range spec: a named range (2350, 11172, ksx1001-nohanja, ksx1001-symbols, ksx1001, jamo, cp949) or the maker's own list copy.

    The value is comma-separated, so an uploaded list file's path is never spliced in (a name with a comma would
    inject a named range or hex ranges): the maker copies the list to `paths["range_file"]` and passes that.
    """
    kind, _ = range_spec
    if kind == "file":
        if not paths.get("range_file"):
            raise ValueError("mkfont needs a range file")
        return "ascii,file:" + paths["range_file"]
    return {"11172": "ascii,hangul", "2350": "ascii,ksx1001-hangul"}.get(kind, "ascii," + kind)


def _mkfont_commands(font, size, bpp, layout, range_spec, paths, extra):
    argv = PY + [_tool(paths, "mkfont.py"), paths["src"], paths["out"], "--size", str(size), "--bpp", str(bpp),
                 "--unicode", _mkfont_unicode(range_spec, paths)]
    return _with_extra([argv], extra)


def _composite_prepare(font, layout, paths):
    argv = PY + [_tool(paths, "jamovec.py"), "master", paths["src"], "-o", paths["master"], "--components"]
    if layout == "adaptive":
        argv.append("--adaptive")
    return [argv]


def _composite_commands(font, size, bpp, layout, range_spec, paths, extra):
    argv = PY + [_tool(paths, "jamovec.py"), "render", paths["master"], "--size", str(size), "--bpp", str(bpp),
                 "--binarize", "threshold", "--check", "-o", paths["out"]]
    return _with_extra([argv], extra)


def _vector_prepare(font, layout, paths):
    """jamovec.py's master from the outlines themselves (no --components): the vector fit for a font whose syllables
    are not composites."""
    argv = PY + [_tool(paths, "jamovec.py"), "master", paths["src"], "-o", paths["master"]]
    if layout == "adaptive":
        argv.append("--adaptive")
    return [argv]


def _mask_fit_commands(font, size, bpp, layout, range_spec, paths, extra):
    """The free fit with the font's own GSUB-composed jamo as the mask (needs freetype-py and uharfbuzz): 1 bpp only,
    always --no-clean (the mask would be discarded by a cleaned raster), `--pylib` when the libraries are in a folder."""
    argv = PY + [_tool(paths, "jamoset.py"), "--layout", layout, "--from-ttf", paths["src"], "--size", str(size),
                 "--binarize", "threshold", "--mask-font", paths["src"], "--no-clean", "--check", "-o", paths["out"]]
    if paths.get("pylib"):
        argv += ["--pylib", paths["pylib"]]
    return _with_extra([argv], extra)


def _fit_commands(font, size, bpp, layout, range_spec, paths, extra):
    argv = PY + [_tool(paths, "jamoset.py"), "--layout", layout, "--from-ttf", paths["src"], "--size", str(size)]
    if bpp == 1:
        argv += ["--binarize", "threshold"]     # a 1 bpp fit always binarizes; a 2 bpp fit never does
    else:
        argv += ["--bpp", "2"]
    argv += ["--check", "-o", paths["out"]]
    if bpp == 1 and paths.get("eng"):           # the panel shows --eng for a 1 bpp fit only
        argv += ["--eng", paths["eng"]]
    if bpp == 1:
        argv += ["--mask-font", "none"]         # the free fit whatever the worker's environment holds (2 bpp never reads it)
    return _with_extra([argv], extra)


def _dos_commands(font, size, bpp, layout, range_spec, paths, extra):
    argv = PY + [_tool(paths, "jamoset.py"), paths["src"], "--layout", layout, "--check", "-o", paths["out"]]
    if paths.get("eng"):
        argv += ["--eng", paths["eng"]]
    if layout in detect.DKB_LAYOUTS:
        argv += ["--face", str(font.get("face_index", 0))]
    return _with_extra([argv], extra)


def _johab844_commands(font, size, bpp, layout, range_spec, paths, extra):
    argv = PY + [_tool(paths, "johab844.py"), paths["src"], paths["base"], paths["out"]]
    if paths.get("eng"):
        argv += ["--eng", paths["eng"]]
    return _with_extra([argv], extra)


def _hanterm_commands(font, size, bpp, layout, range_spec, paths, extra):
    argv = PY + [_tool(paths, "jamoset.py"), paths["src"], "--layout", "hanterm-johab", "--check", "-o",
                 paths["out"]]
    if paths.get("eng"):
        argv += ["--eng", paths["eng"]]
    return _with_extra([argv], extra)


def _mac71_commands(mode):
    """`macfbit_svf.py build FBIT HTBL -o OUT --mode direct|derived [--latin SUITCASE]` for a 7.1 type-3 fbit."""
    def commands(font, size, bpp, layout, range_spec, paths, extra):
        if not paths.get("htbl"):
            raise ValueError("needs an HTBL 1 table")
        argv = PY + [_tool(paths, "macfbit_svf.py"), "build", paths["src"], paths["htbl"], "-o", paths["out"],
                     "--mode", mode]
        if paths.get("latin"):
            argv += ["--latin", paths["latin"]]
        return _with_extra([argv], extra)
    return commands


def _mac71_bdf_commands(font, size, bpp, layout, range_spec, paths, extra):
    """The fbit's planes composed into a BDF strike (`macfbit3.py bdf`), then `mkfont.py` on that BDF at its own size."""
    if not paths.get("htbl"):
        raise ValueError("needs an HTBL 1 table")
    bdf = os.path.join(paths["work"], "mac.bdf")
    sized = os.path.join(paths["work"], "mac-sized.bdf")
    first = PY + [_tool(paths, "macfbit3.py"), "bdf", paths["src"], paths["htbl"], font.get("family") or "Mac", bdf]
    # the tool's BDF has no PIXEL_SIZE, so FreeType would read its `SIZE 12 75 75` as 13 px: name the strike's own size
    second = PY + [SRCPREP, "bdf-pixel-size", bdf, sized, "--size", str(size)]
    unicode_range = ("ksx1001-hangul,3131-318e" if range_spec[0] == "2350"       # the strike holds no ASCII
                     else _mkfont_unicode(range_spec, paths))
    third = PY + [_tool(paths, "mkfont.py"), sized, paths["out"], "--size", str(size), "--bpp", "1",
                  "--unicode", unicode_range]
    return _with_extra([first, second, third], extra)    # the panel's flags go on the last command


def _bdfface_commands(font, size, bpp, layout, range_spec, paths, extra):
    latin = paths.get("latin")
    if not latin:
        raise ValueError("bdfface needs a Latin companion")
    chars = range_spec[1] if range_spec[0] == "file" else paths.get("range_file")
    if not chars:
        raise ValueError("bdfface needs a range file")
    box = font["bdf"]["box"]
    argv = PY + [_tool(paths, "bdfface.py"), "--hangul", paths["src"], "--ascii", latin,
                 "--cell", "%dx%d" % (box[0], box[1]), "--chars-from", chars, "-o", paths["out"]]
    return _with_extra([argv], extra)


def _bdfface_fit_commands(font, size, bpp, layout, range_spec, paths, extra):
    """The KS X 1001 face from bdfface.py, then a jamo set fitted to it (`jamoset.py --from-svf`)."""
    precomposed = os.path.join(paths["work"], "precomposed.svf")
    first = _bdfface_commands(font, size, bpp, layout, range_spec, dict(paths, out=precomposed), [])[0]
    argv = PY + [_tool(paths, "jamoset.py"), "--layout", layout, "--from-svf", precomposed, "--check", "-o",
                 paths["out"]]                  # no --eng: the companion is a BDF (bdfface.py took its ASCII already)
    return _with_extra([first, argv], extra)


def _svf_version(font):
    """The SVFN version detect read from @p font's header (3 when the entry does not say)."""
    svf = font.get("svf")
    return svf.get("version", 3) if isinstance(svf, dict) else 3


def _jset_target(extra):
    """The JSET version the user asked for in @p extra (`--jset-version 1|2`, the last one wins), else None. The maker
    keeps an uploaded face's JSET version by default (v2 is for memory-constrained targets only); only this flag
    converts: 2 turns a v1 block into v2, 1 turns a v2 block into v1."""
    target = None
    extra = list(extra or [])
    for i, tok in enumerate(extra):
        if tok == "--jset-version":
            if i + 1 >= len(extra) or extra[i + 1] not in ("1", "2"):
                raise ValueError("--jset-version needs 1 or 2")
            target = int(extra[i + 1])
    return target


def _jset_wants_change(font, extra):
    """True when @p extra asks for a JSET version other than the one @p font's block has (detect's svf.jset_version)."""
    svf = font.get("svf")
    have = svf.get("jset_version") if isinstance(svf, dict) else None
    target = _jset_target(extra)
    return have is not None and target is not None and target != have


def _svf2to3_argv(paths, src, out, version):
    """`svf2to3.py SRC OUT --jset-version V --check`: a v2 face packed as v3 (jamoset.pack_svfn) or a v3 face's JSET block
    rewritten in version @p version, proved pixel-identical to the source."""
    return PY + [_tool(paths, "svf2to3.py"), src, out, "--jset-version", str(version), "--check"]


def _svf2to3_version(font, extra, strict=True):
    """The --jset-version to convert with, or None when the face is used as uploaded: a v2 file always converts (to the
    requested version, else v1 = its own); a v3 file converts only when the request differs from its block."""
    target = _jset_target(extra)
    svf = font.get("svf")
    if target is not None and isinstance(svf, dict) and svf.get("jset_version") == 3:
        # svf2to3 copies a JMAP region verbatim and would only note on stderr that the flag did nothing: the copy route
        # refuses visibly (@p strict); the from-svf fit reads the JMAP source as it is and the flag only reaches its writer
        if not strict:
            return None
        raise ValueError("--jset-version %d does not apply to a JMAP face (JSET version 3): it is used as it is" % target)
    if _svf_version(font) == 2:
        return target or 1
    return target if _jset_wants_change(font, extra) else None


def _from_svf_commands(font, size, bpp, layout, range_spec, paths, extra):
    src = paths["src"]
    commands = []
    version = _svf2to3_version(font, _flat(extra), strict=False)
    if version is not None:                     # jamoset.py reads v3: convert the source in the step's work dir
        src = os.path.join(paths["work"], "source-v3.svf")
        commands.append(_svf2to3_argv(paths, paths["src"], src, version))
    argv = PY + [_tool(paths, "jamoset.py"), "--layout", layout, "--from-svf", src, "--check", "-o", paths["out"]]
    if paths.get("eng"):                        # the panel shows --eng for --from-svf
        argv += ["--eng", paths["eng"]]
    commands.append(argv)
    return _with_extra(commands, extra)         # --jset-version reaches the writer too: it writes that block version


def svf_commands(font, paths, extra=()):
    """An SVF source's own face as v3: [] when it is used as uploaded (the caller copies paths["src"] to paths["out"]),
    else the `svf2to3.py --jset-version V --check` command: for a v2 face, or a v3 face whose JSET version @p extra
    (`--jset-version 1|2`) asks to change. Without that flag the JSET version is kept. The copy route and
    preview.bake_source_face share it."""
    version = _svf2to3_version(font, extra)
    if version is not None:
        return [_svf2to3_argv(paths, paths["src"], paths["out"], version)]
    return []


def _copy_commands(font, size, bpp, layout, range_spec, paths, extra):
    return svf_commands(font, paths, _flat(extra))     # [] = the worker copies paths["src"] to paths["out"]


def fmt_num(value):
    """A number for an argv or a message: an integral value without `.0`, else repr (no six-digit rounding)."""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


# The extension of the file each source op writes (None: the sfnt's own, `ttf` or `otf`).
OP_EXT = {"rsrc-sfnt": None, "ttc-face": None, "mac-cmap": None, "instance": None, "pcf-bdf": "bdf",
          "mac-fork": "rsrc", "mac-fork-named": "rsrc", "mac-fbit3": "fbit", "mac-htbl": "htbl1"}


def op_ext(op, sfnt_ext="ttf"):
    """The extension of the file source op @p op writes."""
    ext = OP_EXT.get(op)
    return sfnt_ext if ext is None else ext


def source_commands(ops, src, work, tools_dir, sfnt_ext="ttf", last_name=None):
    """The argvs that turn @p src into the file the tools read, one per op in @p ops, and that file's path.

    Op i writes `work/source-<i+1>.<ext>` and the last op `work/source.<ext>` (or @p last_name), where `ext` is the
    op's own (`OP_EXT`: `bdf` after `pcf-bdf`, `rsrc` after `mac-fork`, `fbit`, `htbl1`) or @p sfnt_ext (`ttf` or `otf`
    for a CFF face), each reading the one before: `rsrc-sfnt` and `mac-cmap` are tools/macsfnt.py, `ttc-face`,
    `pcf-bdf`, `mac-fork` and `mac-htbl` are the maker's srcprep.py, `mac-fbit3` is tools/macfbit3.py, `instance` is
    fontTools' instancer. No ops: no argv and @p src itself.
    """
    argvs = []
    current = src
    for i, op in enumerate(ops):
        kind = op.get("op")
        last = i == len(ops) - 1
        ext = op_ext(kind, sfnt_ext)
        out = os.path.join(work, (last_name or "source." + ext) if last else "source-%d.%s" % (i + 1, ext))
        if kind == "rsrc-sfnt":
            argv = PY + [os.path.join(tools_dir, "macsfnt.py"), "extract", current, out, "--id", str(op["id"])]
        elif kind == "ttc-face":
            argv = PY + [SRCPREP, "ttc-face", current, out, "--index", str(op["index"])]
        elif kind == "mac-cmap":
            argv = PY + [os.path.join(tools_dir, "macsfnt.py"), "unicode", current, out]
        elif kind == "instance":
            pins = ["%s=%s" % (tag, fmt_num(value)) for tag, value in sorted(op["coords"].items())]
            argv = PY + ["-m", "fontTools.varLib.instancer", current] + pins + ["-o", out]
        elif kind == "pcf-bdf":
            argv = PY + [SRCPREP, "pcf-bdf", current, out]
        elif kind == "mac-fork":
            argv = PY + [SRCPREP, "mac-fork", current, out]
        elif kind == "mac-fbit3":
            argv = PY + [os.path.join(tools_dir, "macfbit3.py"), "fbit", current, out]
        elif kind == "mac-htbl":
            argv = PY + [SRCPREP, "mac-htbl", current, out]
        elif kind == "mac-fork-named":
            argv = PY + [SRCPREP, "mac-fork-named", current, out]
        else:
            raise ValueError("unknown source op %r" % (kind,))
        argvs.append(argv)
        current = out
    return argvs, current


def routes(font):
    """The `Route`s one font entry offers, in page order (Shared data shapes).

    A font whose entry lacks what a route needs (a BDF with no `box`, an SVF with no usable `bpp`) offers no route:
    the page's validation names the reason; nothing here builds an argv with a missing path in it.
    """
    kind = font.get("source_kind")
    sizes = list(font.get("sizes") or [])
    face_index = font.get("face_index", 0)
    out = []
    if kind in ("outline", "outline-composite"):
        if face_index > 0 and not font.get("prep"):   # a FON's later face is not a source; a TTC / Mac face is, via prep
            return []
        out.append(Route("precomposed", "mkfont", True, [], [1, 2], None, None, None, _mkfont_commands))
        if kind == "outline-composite":
            out.append(Route("jamo", "composite", True, ["844", "adaptive"], [1, 2], None, "outline",
                             _composite_prepare, _composite_commands))
        else:
            out.append(Route("jamo", "experimental fit", False, ["844", "adaptive"], [1, 2], None, "outline",
                             None, _fit_commands))
        if font.get("gsub_jamo") and font.get("mask_ok"):
            out.append(Route("jamo", "mask fit", False, ["844", "adaptive"], [1], None, "outline", None,
                             _mask_fit_commands))
        out.append(Route("jamo", "vector fit", False, ["844", "adaptive"], [1, 2], None, "outline", _vector_prepare,
                         _composite_commands))
    elif kind in ("bitmap", "bdf-iso10646"):
        if (face_index > 0 and not font.get("prep")) or not sizes:   # a bare FNT header or a BDF Pillow opens at no size has no face
            return []
        out.append(Route("precomposed", "mkfont", True, [], [1], sizes, None, None, _mkfont_commands))
    elif kind == "dos-raw":
        layouts = [l for l in (font.get("dos") or {}).get("candidates", []) if l != "none"]
        if font.get("dos_bytes") == 11520 and "844" in layouts:   # a 16 px 8x4x4 raw font: its pieces make precomposed syllables
            out.append(Route("precomposed", "johab844", True, [], [1], [16], None, None, _johab844_commands))
        out.append(Route("jamo", "dos raw", True, layouts, [1], sizes, None, None, _dos_commands))
    elif kind == "mac-fbit3":
        out.append(Route("jamo", "mac fbit 7.1 direct", True, ["mac-htbl1"], [1], sizes, None, None,
                         _mac71_commands("direct")))
        out.append(Route("jamo", "mac fbit 7.1 derived", False, ["mac-htbl1"], [1], sizes, None, None,
                         _mac71_commands("derived")))
        out.append(Route("precomposed", "mac fbit 7.1 bdf + mkfont", True, [], [1], sizes, None, None,
                         _mac71_bdf_commands))
    elif kind == "bdf-johab":
        out.append(Route("jamo", "hanterm", True, ["hanterm-johab"], [1], sizes, None, None, _hanterm_commands))
    elif kind == "bdf-ksc5601":
        if not (font.get("bdf") or {}).get("box"):   # bdfface needs the BDF's box for --cell
            return []
        out.append(Route("precomposed", "bdfface", True, [], [1], sizes, None, None, _bdfface_commands))
        out.append(Route("jamo", "bdfface + from-svf fit", False, ["844", "adaptive"], [1], sizes, None, None,
                         _bdfface_fit_commands))
    elif kind in ("svf-precomposed", "svf-jamo"):
        bpp = (font.get("svf") or {}).get("bpp") if isinstance(font.get("svf"), dict) else None
        if bpp not in (1, 2) or _svf_version(font) not in (2, 3):   # a malformed SVF entry offers no route
            return []
        if kind == "svf-jamo":
            out.append(Route("jamo", "copy", True, [], [bpp], sizes, None, None, _copy_commands))
        else:
            out.append(Route("precomposed", "copy", True, [], [bpp], sizes, None, None, _copy_commands))
            if bpp == 1:
                out.append(Route("jamo", "from-svf fit", False, ["844", "adaptive"], [1], sizes, "svf", None,
                                 _from_svf_commands))
    return out


def route_for(font, kind, experimental, jamo_route=None):
    """The route of @p kind to use: the first native one, else (when @p experimental) the first non-native one.

    A @p jamo_route label picks the jamo route of that label instead, when the font offers it and it is native or
    @p experimental is set (else None); it never changes a precomposed choice."""
    found = [r for r in routes(font) if r.kind == kind]
    if kind == "jamo" and jamo_route:
        for route in found:
            if route.label == jamo_route and (route.native or experimental):
                return route
        return None
    for route in found:
        if route.native:
            return route
    if experimental:
        for route in found:
            if not route.native:
                return route
    return None
