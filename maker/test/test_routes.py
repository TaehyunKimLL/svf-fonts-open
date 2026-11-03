#!/usr/bin/env python3
"""routes.py and presets.py tests: source kind -> tool argv, and the preset table.

  python3 -m unittest discover -s maker/test -p 'test_*.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import subprocess
import tempfile
import unittest

import jamoset
import presets
import routes

PY = [sys.executable, "-P"]
P = {"tools": "/T", "src": "/u/in.ttf", "out": "/w/OUT.SVF", "work": "/w", "eng": None, "latin": None,
     "master": "/w/master.json", "range_file": "/w/range-2350.txt"}


def font(**kw):
    """One font entry (Shared data shapes) with every key a route reads."""
    e = {"id": "f01", "path": "fonts/in.ttf", "face_index": 0, "format": "ttf", "label": "TTF",
         "source_kind": "outline", "family": "T", "style": "Regular", "version": "",
         "sizes": [16], "sizes_fixed": False,
         "coverage": {"ascii": 95, "ks2350": 2350, "all": 11172, "compat": 51},
         "jamo": "none", "dos": None, "bdf": None, "svf": None,
         "licences": [], "companions": [], "error": None}
    e.update(kw)
    return e


FONT_TTF = font()
FONT_COMPOSITE = font(source_kind="outline-composite", jamo="native (composite)")
FONT_DOS = font(format="dos-raw", label="DOS raw", source_kind="dos-raw", sizes=[16],
                dos={"candidates": ["844", "844-ihnm"], "faces": [0]}, jamo="native (844)")
FONT_DKB = font(format="dos-raw", label="DOS raw", source_kind="dos-raw", sizes=[16], face_index=1,
                dos={"candidates": ["dkb-printer-7x2x2", "dkb-printer-12x4x4"], "faces": [0, 1]},
                jamo="native (dkb-printer-7x2x2)")
FONT_KSC = font(format="bdf", label="BDF", source_kind="bdf-ksc5601", sizes=[24], sizes_fixed=True,
                bdf={"registry": "ksc5601-1", "box": [24, 24]}, jamo="compat 51/51")
FONT_JOHAB = font(format="bdf", label="BDF", source_kind="bdf-johab", sizes=[16], sizes_fixed=True,
                  bdf={"registry": "johab-1", "box": [16, 16]}, jamo="native (hanterm-johab)")
FONT_SVF_PRE = font(format="svf", label="SVF", source_kind="svf-precomposed", sizes=[16], sizes_fixed=True,
                    svf={"version": 3, "flags": 1, "bpp": 1, "cell": [16, 16], "ascent": 12, "glyphs": 2901})
FONT_SVF_JAMO = font(format="svf", label="SVF", source_kind="svf-jamo", sizes=[16], sizes_fixed=True,
                     svf={"version": 3, "flags": 1, "bpp": 1, "cell": [16, 16], "ascent": 12, "glyphs": 100})
FONT_SVF2_PRE = dict(FONT_SVF_PRE, format="svf2", svf=dict(FONT_SVF_PRE["svf"], version=2))
FONT_SVF2_JAMO = dict(FONT_SVF_JAMO, format="svf2", svf=dict(FONT_SVF_JAMO["svf"], version=2))
FONT_HBF = font(format="hbf", label="HBF", source_kind="hbf", sizes=[16])


class ApplyFlagsTest(unittest.TestCase):
    def test_replaces_valued_and_appends_new(self):
        argv = ["a", "b", "--bpp", "1", "--unicode", "ascii,hangul"]
        self.assertEqual(routes.apply_flags(argv, ["--unicode", "ascii", "--clip-cell", "--bpp", "2"]),
                         ["a", "b", "--unicode", "ascii", "--clip-cell", "--bpp", "2"])

    def test_flag_without_value_is_not_duplicated(self):
        self.assertEqual(routes.apply_flags(["x", "--check"], ["--check"]), ["x", "--check"])

    def test_a_trailing_valued_flag_is_refused(self):
        """M5/agy: `--cell` with no value must be refused, not silently dropped or swallowed."""
        with self.assertRaises(ValueError) as ctx:
            routes.apply_flags(["--cell", "16"], ["--cell"])
        self.assertIn("--cell", str(ctx.exception))

    def test_a_valued_flag_followed_by_another_flag_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            routes.apply_flags(["--cell", "16"], ["--cell", "--clip-cell"])
        self.assertIn("--cell", str(ctx.exception))


class PresetTest(unittest.TestCase):
    def test_names_and_size_placeholder(self):
        self.assertEqual(sorted(presets.PRESETS), ["dos-l-1bpp", "dos-u-2bpp", "jamo-621", "jamo-844", "jamo-844-hbios24", "jamo-844-symbols", "latin-18cell-2bpp", "plain"])
        self.assertEqual(presets.argv_for("dos-u-2bpp", "precomposed", 17)[:5], ["--cell", "16", "--clip-cell", "--ascent", "15"])
        self.assertEqual(presets.argv_for("plain", "precomposed", 16), [])
        self.assertEqual(presets.PRESETS["jamo-844-hbios24"]["layout"], "844-hbios24")

    def test_every_preset_matches_the_spec_table(self):
        """SOL: the whole payload, token for token, against the spec's preset table (a typo fails here)."""
        expected = {
            "plain": {"argv": {}, "layout": None, "bpp": None,
                      "sources": ["outline", "outline-composite", "bitmap", "bdf-iso10646", "bdf-iso8859",
                                  "bdf-ksc5601", "bdf-johab", "hbf", "dos-raw", "svf-precomposed", "svf-jamo",
                                  "other"],
                      "reproduces": "the tools' defaults"},
            "dos-l-1bpp": {
                "argv": {"precomposed": ["--cell", "16", "--bpp", "1", "--unicode",
                                         "ascii,ksx1001-nohanja,AC37,B2CF,B584,C125,C2BA,D14A,D59D"]},
                "layout": None, "bpp": [1], "sources": ["outline", "outline-composite"],
                "reproduces": "svf/dos/NEODG16.SVF (the L preset; one glyph fewer than the shipped file)"},
            "dos-u-2bpp": {
                "argv": {"precomposed": ["--cell", "16", "--clip-cell", "--ascent", "{size-2}", "--bpp", "2",
                                         "--unicode",
                                         "ascii,ksx1001-nohanja,AC37,B2CF,B584,C125,C2BA,D14A,D59D"]},
                "layout": None, "bpp": [2], "sources": ["outline", "outline-composite"],
                "reproduces": "svf/dos/GBATB17.SVF (byte-identical at size 17) and NGOTB16.SVF (one glyph fewer)"},
            "latin-18cell-2bpp": {
                "argv": {"precomposed": ["--cell", "18", "--width", "18", "--bpp", "2", "--clip-cell", "--ascent",
                                         "14", "--unicode", "ascii,2026,2122,3131-318e", "--only-listed",
                                         "--space-advance", "6", "--punct-extra", "1"]},
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
        self.assertEqual(sorted(presets.PRESETS), sorted(expected))
        for name, want in expected.items():
            self.assertEqual(presets.PRESETS[name], want, name)

    def test_panel_argv_respects_modes(self):
        o = {"mkfont": {"cell": 16, "ascent": 14, "mono_hint": True, "clip_cell": True, "space_advance": None}, "jamoset": {"embolden": True, "symbols": True}}
        self.assertEqual(presets.panel_argv(o, "precomposed", "mkfont", 1), ["--cell", "16", "--ascent", "14", "--mono-hint", "--clip-cell"])
        self.assertEqual(presets.panel_argv(o, "precomposed", "mkfont", 2), ["--cell", "16", "--ascent", "14", "--clip-cell"])
        self.assertEqual(presets.panel_argv(o, "jamo", "dos raw", 1), ["--embolden", "--symbols"])
        self.assertEqual(presets.panel_argv(o, "jamo", "experimental fit", 1), [])
        self.assertEqual(presets.panel_argv(o, "jamo", "experimental fit", 2), ["--symbols"])
        self.assertEqual(presets.panel_argv(o, "jamo", "composite", 2), ["--symbols"])

    def test_panel_argv_null_values_are_absent(self):
        o = {"mkfont": {"cell": None, "ascent": None, "mono_hint": False, "clip_cell": False, "space_advance": None},
             "jamoset": {"embolden": False, "symbols": False}}
        self.assertEqual(presets.panel_argv(o, "precomposed", "mkfont", 1), [])
        self.assertEqual(presets.panel_argv(o, "jamo", "dos raw", 1), [])

    def test_panel_argv_on_the_other_route_labels(self):
        """M5: hanterm and from-svf take the jamoset flags; bdfface and copy take none of them."""
        o = {"mkfont": {"cell": 16, "ascent": 14, "mono_hint": True, "clip_cell": True, "space_advance": 5},
             "jamoset": {"embolden": True, "symbols": True}}
        self.assertEqual(presets.panel_argv(o, "jamo", "hanterm", 1), ["--embolden", "--symbols"])
        self.assertEqual(presets.panel_argv(o, "jamo", "from-svf fit", 1), [])
        self.assertEqual(presets.panel_argv(o, "jamo", "from-svf fit", 2), [])
        self.assertEqual(presets.panel_argv(o, "precomposed", "bdfface", 1), [])
        self.assertEqual(presets.panel_argv(o, "precomposed", "copy", 1), [])
        self.assertEqual(presets.panel_argv(o, "jamo", "copy", 1), [])


class RoutesTest(unittest.TestCase):
    def test_outline_precomposed(self):
        r = routes.routes(FONT_TTF)
        self.assertEqual([(x.kind, x.label, x.native) for x in r], [("precomposed", "mkfont", True), ("jamo", "experimental fit", False)])
        self.assertEqual(r[0].commands(FONT_TTF, 16, 2, None, ("2350", None), P, []),
                         [PY + ["/T/mkfont.py", "/u/in.ttf", "/w/OUT.SVF", "--size", "16", "--bpp", "2", "--unicode", "ascii,ksx1001-hangul"]])
        self.assertEqual(r[0].commands(FONT_TTF, 16, 1, None, ("file", "/u/list.txt"), P, [])[0][-1], "ascii,file:/w/range-2350.txt")

    def test_a_list_files_name_never_reaches_unicode(self):
        """I1: `--unicode` is comma-split, so a user file name must not be spliced in: the maker's copy is."""
        r = routes.routes(FONT_TTF)[0]
        argv = r.commands(FONT_TTF, 16, 1, None, ("file", "/u/x,cp949"), P, [])[0]
        self.assertEqual(argv[-1], "ascii,file:/w/range-2350.txt")
        self.assertNotIn("/u/x,cp949", argv)

    def test_preset_fragment_replaces_route_flags(self):
        r = routes.routes(FONT_TTF)[0]
        cmd = r.commands(FONT_TTF, 17, 2, None, ("2350", None), P, presets.argv_for("dos-u-2bpp", "precomposed", 17))[0]
        self.assertEqual(cmd[5:], ["--size", "17", "--cell", "16", "--clip-cell", "--ascent", "15", "--bpp", "2", "--unicode", "ascii,ksx1001-nohanja,AC37,B2CF,B584,C125,C2BA,D14A,D59D"])

    def test_composite_jamo(self):
        r = routes.route_for(FONT_COMPOSITE, "jamo", False)
        self.assertEqual(r.prepare_commands(FONT_COMPOSITE, "adaptive", P), [PY + ["/T/jamovec.py", "master", "/u/in.ttf", "-o", "/w/master.json", "--components", "--adaptive"]])
        self.assertEqual(r.commands(FONT_COMPOSITE, 16, 1, "adaptive", ("2350", None), P, []),
                         [PY + ["/T/jamovec.py", "render", "/w/master.json", "--size", "16", "--bpp", "1", "--binarize", "threshold", "--check", "-o", "/w/OUT.SVF"]])
        self.assertEqual(r.commands(FONT_COMPOSITE, 16, 2, "844", ("2350", None), P, []),
                         [PY + ["/T/jamovec.py", "render", "/w/master.json", "--size", "16", "--bpp", "2", "--binarize", "threshold", "--check", "-o", "/w/OUT.SVF"]])

    def test_experimental_fit(self):
        r = routes.route_for(FONT_TTF, "jamo", True)
        self.assertEqual(r.commands(FONT_TTF, 16, 1, "844", ("2350", None), P, [])[0][3:], ["--layout", "844", "--from-ttf", "/u/in.ttf", "--size", "16", "--binarize", "threshold", "--check", "-o", "/w/OUT.SVF"])
        self.assertNotIn("--binarize", r.commands(FONT_TTF, 16, 2, "844", ("2350", None), P, [])[0])
        self.assertIsNone(routes.route_for(FONT_TTF, "jamo", False))

    def test_fit_routes_take_eng_at_1bpp_only(self):
        """M4: the spec's panel shows `--eng` for `--from-ttf` 1 bpp and `--from-svf`, so the routes pass it."""
        fit = routes.route_for(FONT_TTF, "jamo", True)
        svf = routes.routes(FONT_SVF_PRE)[1]
        p = dict(P, eng="/u/ENG.FNT")
        self.assertEqual(fit.commands(FONT_TTF, 16, 1, "844", ("2350", None), p, [])[0][-2:], ["--eng", "/u/ENG.FNT"])
        self.assertNotIn("--eng", fit.commands(FONT_TTF, 16, 2, "844", ("2350", None), p, [])[0])
        self.assertEqual(svf.commands(FONT_SVF_PRE, 16, 1, "844", ("2350", None), p, [])[0][-2:], ["--eng", "/u/ENG.FNT"])
        self.assertNotIn("--eng", svf.commands(FONT_SVF_PRE, 16, 1, "844", ("2350", None), P, [])[0])

    def test_dos_raw_with_eng_and_face(self):
        r = routes.routes(FONT_DOS)[0]
        p = dict(P, eng="/u/ENG.FNT")
        self.assertEqual(r.commands(FONT_DOS, 16, 1, "844", ("2350", None), p, [])[0][3:], ["/u/in.ttf", "--layout", "844", "--check", "-o", "/w/OUT.SVF", "--eng", "/u/ENG.FNT"])
        self.assertEqual(r.commands(FONT_DKB, 16, 1, "dkb-printer-7x2x2", ("2350", None), P, [])[0][-2:], ["--face", "1"])
        self.assertEqual(r.layouts, ["844", "844-ihnm"])

    def test_a_dos_entry_without_face_index_defaults_to_zero(self):
        f = dict(FONT_DKB)
        del f["face_index"]
        self.assertEqual(routes.routes(f)[0].commands(f, 16, 1, "dkb-printer-7x2x2", ("2350", None), P, [])[0][-2:],
                         ["--face", "0"])

    def test_bdf_ksc_and_hanterm(self):
        self.assertEqual(routes.routes(FONT_KSC)[0].commands(FONT_KSC, 24, 1, None, ("2350", None), dict(P, latin="/u/latin.bdf"), [])[0][3:],
                         ["--hangul", "/u/in.ttf", "--ascii", "/u/latin.bdf", "--cell", "24x24", "--chars-from", "/w/range-2350.txt", "-o", "/w/OUT.SVF"])
        self.assertEqual(routes.routes(FONT_JOHAB)[0].commands(FONT_JOHAB, 16, 1, "hanterm-johab", ("2350", None), P, [])[0][4:6], ["--layout", "hanterm-johab"])

    def test_bdfface_refuses_without_a_latin_companion(self):
        """M3: no `None` in argv; the reason is legible as a ValueError."""
        r = routes.routes(FONT_KSC)[0]
        with self.assertRaises(ValueError) as ctx:
            r.commands(FONT_KSC, 24, 1, None, ("2350", None), P, [])
        self.assertIn("Latin companion", str(ctx.exception))
        argv = r.commands(FONT_KSC, 24, 1, None, ("file", "/u/list.txt"), dict(P, latin="/u/latin.bdf"), [])[0]
        self.assertEqual(argv[argv.index("--chars-from") + 1], "/u/list.txt")   # a list path is its own token

    def test_a_bdf_without_a_box_has_no_route(self):
        self.assertEqual(routes.routes(dict(FONT_KSC, bdf=None)), [])
        self.assertEqual(routes.routes(dict(FONT_KSC, bdf={"registry": "ksc5601-1"})), [])

    def test_a_malformed_svf_has_no_route(self):
        self.assertEqual(routes.routes(dict(FONT_SVF_PRE, svf=None)), [])
        self.assertEqual(routes.routes(dict(FONT_SVF_PRE, svf={"version": 3})), [])
        self.assertEqual(routes.routes(dict(FONT_SVF_JAMO, svf={"bpp": 3})), [])

    def test_an_outline_with_a_face_index_has_no_route(self):
        self.assertEqual(routes.routes(dict(FONT_TTF, face_index=1)), [])
        self.assertEqual(routes.routes(dict(FONT_COMPOSITE, face_index=1)), [])

    def test_svf_routes(self):
        self.assertEqual([(x.kind, x.label) for x in routes.routes(FONT_SVF_PRE)], [("precomposed", "copy"), ("jamo", "from-svf fit")])
        self.assertEqual(routes.routes(FONT_SVF_PRE)[0].commands(FONT_SVF_PRE, 16, 1, None, ("2350", None), P, []), [])
        self.assertEqual([(x.kind, x.label) for x in routes.routes(FONT_SVF_JAMO)], [("jamo", "copy")])
        self.assertEqual(routes.routes(FONT_HBF), [])
        self.assertEqual(routes.routes(dict(FONT_KSC, source_kind="bdf-iso8859")), [])
        self.assertEqual(routes.routes(dict(FONT_TTF, source_kind="bitmap", sizes=[], sizes_fixed=True)), [])
        self.assertEqual(routes.routes(dict(FONT_KSC, source_kind="bdf-iso10646", sizes=[], sizes_fixed=True)), [])
        self.assertEqual(routes.routes(dict(FONT_TTF, face_index=1, source_kind="other")), [])

    def test_v2_svf_routes_convert_through_svf2to3(self):
        """A v2 SVF source is never shipped as it is: the copy route converts it (svf2to3.py --check, so through
        jamoset.pack_svfn) and the from-svf fit converts it into the step's work directory first."""
        conv = PY + ["/T/svf2to3.py", "/u/in.ttf", "/w/OUT.SVF", "--jset-version", "1", "--check"]
        for f in (FONT_SVF2_PRE, FONT_SVF2_JAMO):
            copy = routes.routes(f)[0]
            self.assertEqual(copy.label, "copy")
            self.assertEqual(copy.commands(f, 16, 1, None, ("2350", None), P, []), [conv])
            self.assertEqual(routes.svf_commands(f, P), [conv])
        self.assertEqual(routes.svf_commands(FONT_SVF_PRE, P), [])
        fit = routes.routes(FONT_SVF2_PRE)[1]
        cmds = fit.commands(FONT_SVF2_PRE, 16, 1, "844", ("2350", None), dict(P, eng="/u/ENG.FNT"), [])
        self.assertEqual(cmds[0], PY + ["/T/svf2to3.py", "/u/in.ttf", "/w/source-v3.svf", "--jset-version", "1", "--check"])
        self.assertEqual(cmds[1][2:], ["/T/jamoset.py", "--layout", "844", "--from-svf", "/w/source-v3.svf",
                                       "--check", "-o", "/w/OUT.SVF", "--eng", "/u/ENG.FNT"])
        self.assertEqual(routes.routes(dict(FONT_SVF_PRE, svf=dict(FONT_SVF_PRE["svf"], version=1))), [])

    def _jf(self, v):
        return dict(FONT_SVF_JAMO, svf=dict(FONT_SVF_JAMO["svf"], jset_version=v))

    def test_jset1_default_keeps_the_version(self):
        # v2 is for memory-constrained targets only: no flag, no conversion, big v1 block or not
        f = self._jf(1)
        self.assertEqual(routes.svf_commands(f, P), [])
        self.assertEqual(routes.routes(f)[0].commands(f, 16, 1, None, ("2350", None), P, []), [])
        f2 = self._jf(2)
        self.assertEqual(routes.svf_commands(f2, P), [])

    def test_jset_version_flag_converts(self):
        conv = lambda v: PY + ["/T/svf2to3.py", "/u/in.ttf", "/w/OUT.SVF", "--jset-version", v, "--check"]
        f = self._jf(1)
        self.assertEqual(routes.routes(f)[0].commands(f, 16, 1, None, ("2350", None), P, ["--jset-version", "2"]),
                         [conv("2")])
        self.assertEqual(routes.svf_commands(f, P, ["--jset-version", "1"]), [])       # already v1
        f2 = self._jf(2)
        self.assertEqual(routes.svf_commands(f2, P, ["--jset-version", "1"]), [conv("1")])   # R10: v2 -> v1
        self.assertEqual(routes.svf_commands(f2, P, ["--jset-version", "2"]), [])
        with self.assertRaises(ValueError):
            routes.svf_commands(f, P, ["--jset-version", "3"])
        # a v2 file converts to the requested version
        v2file = dict(FONT_SVF2_JAMO, svf=dict(FONT_SVF2_JAMO["svf"], jset_version=1))
        self.assertEqual(routes.svf_commands(v2file, P, ["--jset-version", "2"]), [conv("2")])

    def test_jset_version_flag_refused_for_a_jmap_face(self):
        f = self._jf(3)
        self.assertEqual(routes.svf_commands(f, P), [])
        with self.assertRaisesRegex(ValueError, "JMAP"):
            routes.svf_commands(f, P, ["--jset-version", "2"])

    def test_from_svf_fit_of_a_jmap_source_skips_the_svf2to3_flag(self):
        f = dict(FONT_SVF_PRE, svf=dict(FONT_SVF_PRE["svf"], jset_version=3))
        cmds = routes.routes(f)[1].commands(f, 16, 1, "844", ("2350", None), P, ["--jset-version", "2"])
        self.assertEqual(len(cmds), 1)
        self.assertIn("jamoset.py", cmds[0][2])
        self.assertEqual(cmds[0][cmds[0].index("--jset-version") + 1], "2")

    def test_from_svf_passes_the_jset_flag_to_the_writer(self):
        cmds = routes.routes(FONT_SVF_PRE)[1].commands(FONT_SVF_PRE, 16, 1, "844", ("2350", None), P,
                                                       ["--jset-version", "2", "--threshold", "5"])
        self.assertEqual(len(cmds), 1)          # a v3 source needs no svf2to3 step; jamoset.py writes the version asked
        self.assertIn("jamoset.py", cmds[0][2])
        self.assertEqual(cmds[0][cmds[0].index("--jset-version") + 1], "2")
        self.assertIn("--threshold", cmds[0])

    def test_panel_argv_jset_version(self):
        o = {"mkfont": {}, "jamoset": {"embolden": False, "symbols": False, "jset_version": 2}}
        for label in ("dos raw", "hanterm", "composite", "experimental fit", "from-svf fit", "copy"):
            self.assertEqual(presets.panel_argv(o, "jamo", label, 1), ["--jset-version", "2"], label)
        self.assertEqual(presets.panel_argv(o, "precomposed", "mkfont", 1), [])
        self.assertEqual(presets.panel_argv(o, "precomposed", "copy", 1), [])
        o["jamoset"]["jset_version"] = None
        self.assertEqual(presets.panel_argv(o, "jamo", "dos raw", 1), [])

    def test_commands_is_required(self):
        """M6: a Route with no `commands` must not be constructible (the brief has it required)."""
        with self.assertRaises(TypeError):
            routes.Route("jamo", "copy", True, [], [1])


class IsoBdfBakeTest(unittest.TestCase):
    """I3: the ISO10646 fixture's glyphs must be distinct, or mkfont drops them all (exit 1)."""

    def test_the_mkfont_route_bakes_the_iso_fixture_and_svfline_draws_it(self):
        import fixtures
        import svfline
        with tempfile.TemporaryDirectory() as d:
            got = fixtures.write_fixtures(d)
            entry = font(path="bdf/iso.bdf", format="bdf", label="BDF", source_kind="bdf-iso10646",
                         sizes=[16], sizes_fixed=True, bdf={"registry": "iso10646-1", "box": [16, 16]})
            route = routes.routes(entry)[0]
            out = os.path.join(d, "ISO16.SVF")
            paths = dict(P, tools=os.path.join(fixtures.REPO_DIR, "tools"), src=got["bdf_iso"], out=out, work=d)
            argv = route.commands(entry, 16, 1, None, ("2350", None), paths, [])[0]
            subprocess.run(argv, check=True, capture_output=True, cwd=d)
            with open(out, "rb") as f:
                data = f.read()
            self.assertEqual(data[:5], b"SVFN\x03")
            self.assertEqual(jamoset.parse_svfn(data).version, 3)
            gray = svfline.layout([out], b"ABC", 0, 13, 64, 16)
            self.assertTrue(any(gray), "svfline drew nothing from the baked fixture")
            self.assertGreater(svfline.measure([out], b"ABC")[0], 0)


if __name__ == "__main__":
    unittest.main()


class MkfontRangeFileTest(unittest.TestCase):
    def test_a_list_range_without_the_maker_copy_is_refused(self):
        import routes
        with self.assertRaisesRegex(ValueError, "mkfont needs a range file"):
            routes._mkfont_unicode(("file", "/u/x,cp949"), {})
