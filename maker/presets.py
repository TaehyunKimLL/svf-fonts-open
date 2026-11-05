#!/usr/bin/env python3
"""Presets: the named bake recipes the page offers, as tool argv fragments.

A preset is a starting point, not the whole command: the worker merges its fragment with the advanced panel
(`panel_argv`) through `routes.apply_flags`, so a panel value wins over the preset's. `reproduces` names the
shipped face the recipe was derived from, for the page's own documentation.

The segmentation project adds one `Route(kind="jamo", label="segmented")` in routes.py and touches nothing else;
it adds no preset here.
"""

# Every source_kind (Shared data shapes) in one list, for `plain`'s "the tools' defaults".
ALL_SOURCES = ["outline", "outline-composite", "bitmap", "bdf-iso10646", "bdf-iso8859", "bdf-ksc5601",
               "bdf-johab", "hbf", "dos-raw", "svf-precomposed", "svf-jamo", "mac-fbit3", "mac-fbit1", "mac-htbl", "mac-suitcase",
               "other"]

PRESETS = {
    "plain": {"argv": {}, "layout": None, "bpp": None, "sources": list(ALL_SOURCES),
              "reproduces": "the tools' defaults"},
    "dos-l-1bpp": {
        "argv": {"precomposed": ["--cell", "16", "--bpp", "1", "--unicode",
                                 "ascii,ksx1001-nohanja,AC37,B2CF,B584,C125,C2BA,D14A,D59D"]},
        "layout": None, "bpp": [1], "sources": ["outline", "outline-composite"],
        "reproduces": "svf/dos/NEODG16.SVF (the L preset; one glyph fewer than the shipped file)"},
    "dos-u-2bpp": {
        "argv": {"precomposed": ["--cell", "16", "--clip-cell", "--ascent", "{size-2}", "--bpp", "2", "--unicode",
                                 "ascii,ksx1001-nohanja,AC37,B2CF,B584,C125,C2BA,D14A,D59D"]},
        "layout": None, "bpp": [2], "sources": ["outline", "outline-composite"],
        "reproduces": "svf/dos/GBATB17.SVF (byte-identical at size 17) and NGOTB16.SVF (one glyph fewer)"},
    "latin-18cell-2bpp": {
        "argv": {"precomposed": ["--cell", "18", "--width", "18", "--bpp", "2", "--clip-cell", "--ascent", "14",
                                 "--unicode", "ascii,2026,2122,3131-318e", "--only-listed", "--space-advance", "6",
                                 "--punct-extra", "1"]},
        "layout": None, "bpp": [2], "sources": ["outline", "outline-composite"],
        "reproduces": "svf/dos/PAPLG16.SVF (the command in svf/dos/PAPLG.TXT)"},
    "jamo-844": {
        "argv": {"jamo": ["--layout", "844", "--check"]},
        "layout": "844", "bpp": [1], "sources": ["dos-raw"],
        "reproduces": "the 8x4x4 layout of svf/dos/NEODG16A.SVF (no face here is built from a DOS raw font)"},
    "jamo-844-symbols": {
        "argv": {"jamo": ["--layout", "844", "--symbols", "--check"]},
        "layout": "844", "bpp": [1], "sources": ["dos-raw"],
        "reproduces": "the 8x4x4 layout with U+2026 and U+25A1 (no face here is built from a DOS raw font)"},
    "jamo-844-hbios24": {
        "argv": {"jamo": ["--layout", "844-hbios24", "--symbols", "--check"]},
        "layout": "844-hbios24", "bpp": [1], "sources": ["dos-raw"],
        "reproduces": "the 24 px HBIOS 8x4x4 layout (no face of this repository is built with it)"},
    "jamo-621": {
        "argv": {"jamo": ["--layout", "621", "--check"]},
        "layout": "621", "bpp": [1], "sources": ["dos-raw"],
        "reproduces": "the 6x2x1 layout of svf/dos/NEODG16G.SVF (no face here is built from a DOS raw font)"},
}


def argv_for(name, kind, size):
    """The preset's argv fragment for @p kind, `{size-2}` resolved with @p size; `[]` when it has none.

    KeyError for an unknown preset name (the page only offers `PRESETS` keys).
    """
    fragment = PRESETS[name]["argv"].get(kind, [])
    return [str(size - 2) if token == "{size-2}" else token for token in fragment]


def _num(out, flag, value):
    if value is not None:
        out += [flag, str(value)]


def panel_argv(options, kind, route_label, bpp):
    """The advanced panel's values as one argv fragment per command the panel addresses, for one route and bpp.

    `[[...]]` for every route but `bdfface + from-svf fit`, which is two commands and gets `[argv0 flags, argv1
    flags]` (the bdfface flags on the face writer, `--jset-version` on the jamo fit). Null and false values are absent;
    `--binarize` is emitted only when it is not the routes' own default, `threshold`, so a default panel changes no
    argv. The rows are the spec's 7.1/7.3 for today's route labels.
    """
    mkfont = options.get("mkfont", {})
    jamoset = options.get("jamoset", {})
    bdfface = options.get("bdfface", {})
    out = []
    if kind == "precomposed":
        if route_label == "mkfont":
            _num(out, "--cell", mkfont.get("cell"))
            _num(out, "--ascent", mkfont.get("ascent"))
            _num(out, "--width", mkfont.get("width"))
            if mkfont.get("mono_hint") and bpp == 1:   # mkfont.py refuses --mono-hint for 2 bpp
                out.append("--mono-hint")
            if mkfont.get("clip_cell"):
                out.append("--clip-cell")
            if mkfont.get("fit_cell"):
                out.append("--fit-cell")
            if mkfont.get("latin"):
                out.append("--latin")
            _num(out, "--space-advance", mkfont.get("space_advance"))
        elif route_label == "mac fbit 7.1 bdf + mkfont":     # a bitmap strike: the mkfont keys that apply to one
            _num(out, "--cell", mkfont.get("cell"))
            _num(out, "--ascent", mkfont.get("ascent"))
            _num(out, "--width", mkfont.get("width"))
            _num(out, "--space-advance", mkfont.get("space_advance"))
        elif route_label == "bdfface":
            _num(out, "--ascent", bdfface.get("latin_ascent"))
            _num(out, "--hangul-ascent", bdfface.get("hangul_ascent"))
        return [out]       # johab844 and copy take no panel flag (a precomposed copy has no JSET block)
    if route_label == "bdfface + from-svf fit":
        first = []
        _num(first, "--ascent", bdfface.get("latin_ascent"))
        _num(first, "--hangul-ascent", bdfface.get("hangul_ascent"))
        second = []
        _num(second, "--jset-version", jamoset.get("jset_version"))
        return [first, second]
    if jamoset.get("embolden") and route_label in ("dos raw", "hanterm", "mac fbit 1.0"):
        out.append("--embolden")
    if jamoset.get("symbols") and (route_label in ("dos raw", "hanterm", "mac fbit 1.0", "composite", "vector fit")
                                   or (route_label == "experimental fit" and bpp == 2)):
        out.append("--symbols")
    if jamoset.get("jset_version") is not None and route_label in ("dos raw", "hanterm", "mac fbit 1.0", "composite",
                                                                   "experimental fit",
                                                                   "mask fit", "vector fit", "from-svf fit", "copy", "mac fbit 7.1 derived"):
        out += ["--jset-version", str(jamoset["jset_version"])]   # unset: a writer's own 1, an SVF upload keeps its block
    if route_label in ("dos raw", "hanterm", "mac fbit 1.0"):
        _num(out, "--ascent", jamoset.get("jamo_ascent"))
    if route_label in ("composite", "experimental fit", "mask fit", "vector fit"):
        _num(out, "--baseline", jamoset.get("fit_baseline"))
        binarize = jamoset.get("binarize")
        if bpp == 1 and binarize not in (None, "threshold"):
            out += ["--binarize", binarize]
    if route_label == "experimental fit":
        _num(out, "--aa-refine", jamoset.get("aa_refine") if bpp == 2 else None)
        # jamoset cleans at 2 bpp by default; at 1 bpp the default depends on the layout (adaptive only), so the page
        # offers no control there and an unticked box could not be honoured both ways
        if bpp == 2 and jamoset.get("clean") is False:
            out.append("--no-clean")
    return [out]
