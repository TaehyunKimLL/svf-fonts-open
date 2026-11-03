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
               "bdf-johab", "hbf", "dos-raw", "svf-precomposed", "svf-jamo", "other"]

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


def panel_argv(options, kind, route_label, bpp):
    """The advanced panel's values as an argv fragment for one route and bpp; null/false values are absent."""
    out = []
    if kind == "precomposed":
        if route_label != "mkfont":      # the panel's mkfont values say nothing about bdfface's or copy's flags
            return out
        mkfont = options.get("mkfont", {})
        if mkfont.get("cell") is not None:
            out += ["--cell", str(mkfont["cell"])]
        if mkfont.get("ascent") is not None:
            out += ["--ascent", str(mkfont["ascent"])]
        if mkfont.get("mono_hint") and bpp == 1:   # mkfont.py refuses --mono-hint for 2 bpp
            out.append("--mono-hint")
        if mkfont.get("clip_cell"):
            out.append("--clip-cell")
        if mkfont.get("space_advance") is not None:
            out += ["--space-advance", str(mkfont["space_advance"])]
        return out
    jamoset = options.get("jamoset", {})
    if jamoset.get("embolden") and route_label in ("dos raw", "hanterm"):
        out.append("--embolden")
    if jamoset.get("symbols") and (route_label in ("dos raw", "hanterm", "composite")
                                   or (route_label == "experimental fit" and bpp == 2)):
        out.append("--symbols")
    if jamoset.get("jset_version") is not None and route_label in ("dos raw", "hanterm", "composite", "experimental fit",
                                                                   "from-svf fit", "copy", "bdfface + from-svf fit"):
        out += ["--jset-version", str(jamoset["jset_version"])]   # unset: a writer's own 1, an SVF upload keeps its block
    return out
