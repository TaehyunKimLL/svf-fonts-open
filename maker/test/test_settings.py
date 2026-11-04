#!/usr/bin/env python3
"""settings.py tests: defaults, effective values, validation and the step list.

  python3 -m unittest discover -s maker/test -p 'test_*.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import copy
import shutil
import signal
import tempfile
import unittest
from unittest import mock

import detect
import fixtures
import naming
import routes
import settings
from test_routes import FONT_COMPOSITE, FONT_DOS, FONT_JOHAB, FONT_KSC, FONT_TTF

ROOT = None
FONTS = []
REPO_TOOLS = os.path.join(REPO_DIR, "tools")


def setUpModule():
    """One fixture tree for the whole module; `fid` and `FONTS` read it."""
    global ROOT, FONTS
    ROOT = tempfile.mkdtemp(prefix="svf-maker-settings-")
    fixtures.write_fixtures(ROOT)
    # a list file whose name carries a comma: mkfont's --unicode is comma-split (Task 5 I1)
    with open(os.path.join(ROOT, "x,cp949.txt"), "w", encoding="utf-8") as f:
        f.write("가나다\nABC\n")
    FONTS = detect.scan(ROOT)


def tearDownModule():
    shutil.rmtree(ROOT, ignore_errors=True)


def fid(path):
    """The id `detect.scan` gave the fixture whose relative path is @p path."""
    for font in FONTS:
        if font["path"] == path:
            return font["id"]
    raise KeyError(path)


def font_entry(fid_):
    """The font entry `detect.scan` gave id @p fid_."""
    for font in FONTS:
        if font["id"] == fid_:
            return font
    raise KeyError(fid_)


class DefaultsTest(unittest.TestCase):
    def test_batch_and_selection(self):
        s = settings.defaults(FONTS)
        self.assertEqual(sorted(s), ["batch", "fonts"])                 # R1: no "detected" key
        self.assertEqual(s["batch"]["sizes"], [16]); self.assertEqual(s["batch"]["range"], "2350")
        self.assertTrue(s["fonts"][fid("nanum/NanumGothic-Bold.ttf")]["selected"])
        self.assertFalse(s["fonts"][fid("nolic/NoLicence.ttf")]["selected"])
        self.assertFalse(s["fonts"][fid("dos/HAN.FNT")]["selected"])
        self.assertNotIn(fid("list.txt"), s["fonts"])
    def test_kinds_dest_layout(self):
        S = settings.defaults(FONTS); s = S["fonts"]
        self.assertEqual(s[fid("composite/Composite.ttf")]["kinds"], ["precomposed", "jamo"])
        self.assertEqual(s[fid("composite/Composite.ttf")]["layout"], "adaptive")
        self.assertEqual((s[fid("dos/HAN.FNT")]["kinds"], s[fid("dos/HAN.FNT")]["dest"], s[fid("dos/HAN.FNT")]["bpp"]), (["jamo"], "jamo-extra", [1]))
        nan = s[fid("nanum/NanumGothic-Bold.ttf")]
        self.assertEqual(sorted(nan), sorted(settings.FONT_ONLY_KEYS))        # nothing differs from the batch: no batch key stored
        self.assertEqual(nan["names"], {})
        self.assertEqual(settings.effective(FONTS, S, fid("svf/JAMO6J.SVF"))["names"], {"jamo/16/1": "JAMO6J.SVF"})   # a 16x16 cell; "6J" names the 621 layout
        self.assertEqual(settings.effective(FONTS, S, fid("nanum/NanumGothic-Bold.ttf"))["names"], {"precomposed/16/1": "NANUM16.SVF", "precomposed/16/2": "NANUM16A.SVF"})
        self.assertEqual(nan["licence_name"], "OFLNANUM.TXT")
        self.assertEqual(s[fid("dos/HAN.FNT")]["latin_companion"], fid("dos/ENG.FNT"))
    def test_batch_edit_reaches_fonts_and_renames(self):
        S = settings.defaults(FONTS); S["batch"].update(sizes=[17], bpp=[2])
        e = settings.effective(FONTS, S, fid("nanum/NanumGothic-Bold.ttf"))
        self.assertEqual((e["sizes"], e["bpp"], e["names"]), ([17], [2], {"precomposed/17/2": "NANUM17A.SVF"}))
        S["fonts"][fid("nanum/NanumGothic-Bold.ttf")]["names"] = {"precomposed/17/2": "MINE.SVF", "precomposed/16/1": "OLD.SVF"}
        self.assertEqual(settings.effective(FONTS, S, fid("nanum/NanumGothic-Bold.ttf"))["names"], {"precomposed/17/2": "MINE.SVF"})
        self.assertEqual(settings.effective(FONTS, S, fid("bdf/iso.bdf"))["sizes"], [16])           # a fixed-size font kept its own
    def test_two_bpp_svf_default_bpp(self):
        """F5: an SVF source's default bpp is the face's own, so a 2 bpp entry validates clean."""
        font = copy.deepcopy(font_entry(fid("svf/JAMO6J.SVF")))
        font["svf"]["bpp"] = 2
        s = settings.defaults([font])
        self.assertEqual(s["fonts"][font["id"]]["bpp"], [2])
        self.assertEqual(settings.validate([font], s, ROOT), [])
    def test_effective_names_covers_every_font_with_routes(self):
        """F11: the server's view of the names (Tasks 13/14)."""
        S = settings.defaults(FONTS)
        names = settings.effective_names(FONTS, S)
        self.assertEqual(sorted(names), sorted(S["fonts"]))
        self.assertEqual(names[fid("nanum/NanumGothic-Bold.ttf")],
                         {"precomposed/16/1": "NANUM16.SVF", "precomposed/16/2": "NANUM16A.SVF"})
        self.assertEqual(names[fid("svf/JAMO6J.SVF")], {"jamo/16/1": "JAMO6J.SVF"})
        self.assertNotIn(fid("list.txt"), names)
        self.assertNotIn(fid("fnt/win.fnt"), names)      # a bare FNT header has no size, so it offers no route


class ValidateTest(unittest.TestCase):
    def setUp(self): self.s = settings.defaults(FONTS)
    def bad(self, font_path, **over):
        self.s = settings.defaults(FONTS)
        self.s["fonts"][fid(font_path)].update(over); return settings.validate(FONTS, self.s, ROOT)
    def test_defaults_are_valid(self): self.assertEqual(settings.validate(FONTS, self.s, ROOT), [])
    def test_refusals(self):
        nan = fid("nanum/NanumGothic-Bold.ttf")
        self.assertIn(nan + ": jamo needs experimental on a precomposed font", self.bad("nanum/NanumGothic-Bold.ttf", kinds=["jamo"]))
        self.assertIn(fid("bdf/iso.bdf") + ": size 17 is not a strike (16)", self.bad("bdf/iso.bdf", sizes=[17]))
        self.assertIn(fid("bdf/iso.bdf") + ": bpp 2 is not offered for a bitmap source", self.bad("bdf/iso.bdf", bpp=[2]))
        self.assertIn(nan + ": preset jamo-844 is for DOS raw sources", self.bad("nanum/NanumGothic-Bold.ttf", preset="jamo-844"))
        self.assertIn(nan + ": name nanum16.svf is not [A-Z0-9]{1,8}.SVF", self.bad("nanum/NanumGothic-Bold.ttf", names={"precomposed/16/1": "nanum16.svf"}))
        self.assertIn(nan + ": unknown key foo", self.bad("nanum/NanumGothic-Bold.ttf", foo=1))
        self.s["fonts"]["f99"] = {}; self.assertIn("unknown font id f99", settings.validate(FONTS, self.s, ROOT))
        self.assertEqual(settings.validate(FONTS, {"batch": {}, "fonts": {"f99": {}}}, ROOT)[0], "unknown font id f99")   # ids/keys first, missing batch keys after
        han = fid("dos/HAN.FNT")
        self.assertIn(han + ": preset jamo-844 is for layout 844", self.bad("dos/HAN.FNT", selected=True, dos_layout="844-ihnm", preset="jamo-844"))   # F17: the preset layout is checked against dos_layout
        self.assertEqual(self.bad("dos/HAN.FNT", selected=True, dos_layout="844", preset="jamo-844"), [])
        self.assertEqual(self.bad("nolic/NoLicence.ttf", kinds=["jamo"]), [])   # route rules skip an unselected font
        self.assertEqual(self.bad("nolic/NoLicence.ttf", sizes=[99]), [fid("nolic/NoLicence.ttf") + ": size 99 is not 6..96"])   # value shapes apply to all
    def test_dos_needs_confirmation_then_runs(self):
        errs = self.bad("dos/HAN.FNT", selected=True)
        self.assertIn(fid("dos/HAN.FNT") + ": confirm the DOS Johab layout", errs)
        self.assertEqual(self.bad("dos/HAN.FNT", selected=True, dos_layout="844"), [])
    def test_dos_raw_skips_the_layout_rule(self):
        """F7: a DOS raw font's `layout` is not what its jamo route reads; `dos_layout` covers it."""
        self.assertEqual(self.bad("dos/HAN.FNT", selected=True, dos_layout="844", layout="bogus"), [])
    def test_ksc_needs_a_latin_companion(self):
        """The plan's KSC fixture rule: a selected KSC BDF with no companion is refused by `validate` too."""
        self.assertIn(fid("bdf/ksc.bdf") + ": needs a Latin companion", self.bad("bdf/ksc.bdf", latin_companion=None))
    def test_repeated_and_huge_lists_are_refused(self):
        """R3: duplicates would plan duplicate steps; a 16-entry cap bounds the step list."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        self.assertIn(nan + ": sizes has a repeated value", self.bad("nanum/NanumGothic-Bold.ttf", sizes=[16, 16]))
        self.assertIn(nan + ": bpp has a repeated value", self.bad("nanum/NanumGothic-Bold.ttf", bpp=[1, 1]))
        self.assertIn(nan + ": kinds has a repeated value", self.bad("nanum/NanumGothic-Bold.ttf", kinds=["precomposed", "precomposed"]))
        self.assertIn(nan + ": sizes has more than 16 entries", self.bad("nanum/NanumGothic-Bold.ttf", sizes=list(range(6, 97))))
    def test_ascent_over_the_cell_is_refused(self):
        nan = fid("nanum/NanumGothic-Bold.ttf")
        self.assertIn(nan + ": ascent 20 is over the cell 16", self.bad("nanum/NanumGothic-Bold.ttf", options={"mkfont": {"ascent": 20}}))
    def test_an_inherited_ascent_is_checked_against_the_fonts_own_sizes(self):
        """H1: the ascent rule runs on a font's effective sizes even when it inherits the options."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        s = settings.defaults(FONTS)
        s["batch"]["sizes"] = [24]
        s["batch"]["options"]["mkfont"]["ascent"] = 20
        s["fonts"][nan]["sizes"] = [12]
        errors = settings.validate(FONTS, s, ROOT)
        self.assertIn(nan + ": ascent 20 is over the cell 12", errors)
        self.assertEqual([e for e in errors if e.startswith("batch: ") and "ascent" in e], [])
    def test_a_font_that_inherits_sizes_and_options_does_not_repeat_the_ascent(self):
        """H1: when both the sizes and the options are the batch's, only `batch: ...` reports the rule."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        s = settings.defaults(FONTS)
        s["batch"]["sizes"] = [12]
        s["batch"]["options"]["mkfont"]["ascent"] = 20
        errors = settings.validate(FONTS, s, ROOT)
        self.assertIn("batch: ascent 20 is over the cell 12", errors)
        self.assertNotIn(nan + ": ascent 20 is over the cell 12", errors)
    def test_a_partial_options_override_does_not_repeat_the_batch_error(self):
        """H3: a bad batch option a font inherits is `batch: ...` only; the font reports only its own keys."""
        s = settings.defaults(FONTS)
        s["batch"]["options"]["mkfont"]["cell"] = 300
        s["fonts"][fid("nanum/NanumGothic-Bold.ttf")]["options"] = {"mkfont": {"mono_hint": True}}
        errors = settings.validate(FONTS, s, ROOT)
        self.assertEqual([e for e in errors if "cell 300" in e], ["batch: cell 300 is not 4..255"])
    def test_jset_version_option_is_1_or_2_or_unset(self):
        s = settings.defaults(FONTS)
        self.assertIsNone(s["batch"]["options"]["jamoset"]["jset_version"])
        for good in (None, 1, 2):
            s["batch"]["options"]["jamoset"]["jset_version"] = good
            self.assertEqual([e for e in settings.validate(FONTS, s, ROOT) if "jset_version" in e], [], good)
        for bad in (0, 3, "2"):
            s["batch"]["options"]["jamoset"]["jset_version"] = bad
            self.assertTrue([e for e in settings.validate(FONTS, s, ROOT) if "jset_version" in e], bad)

    def test_names_keys_and_values_are_checked_on_the_raw_dict(self):
        """F2: a malformed key and a bad value are refused, and the value is reported as given."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        self.assertIn(nan + ": name key foo is not <kind>/<size>/<bpp>",
                      self.bad("nanum/NanumGothic-Bold.ttf", names={"foo": "NANUM16.SVF"}))
        self.assertIn(nan + ": name nanum16.svf is not [A-Z0-9]{1,8}.SVF",
                      self.bad("nanum/NanumGothic-Bold.ttf", names={"precomposed/16/1": "nanum16.svf"}))
    def test_the_source_article_is_chosen_by_the_word(self):
        """G2: the article comes from the word, not its first letter (`an outline`, `an SVF`)."""
        self.assertIn(fid("otf/Cff.otf") + ": bpp 3 is not offered for an outline source",
                      self.bad("otf/Cff.otf", bpp=[3]))
        self.assertEqual(self.bad("svf/JAMO6J.SVF", bpp=[2]),
                         [fid("svf/JAMO6J.SVF") + ": bpp 2 is not offered for an SVF source"])
    def test_a_bad_licence_name_is_reported_once(self):
        """G3: a bad non-empty name is the shape rule's; the route rule reports only the empty case."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        for key in ("licence_name", "note_name"):
            errors = self.bad("nanum/NanumGothic-Bold.ttf", **{key: "bad"})
            self.assertEqual([e for e in errors if key in e], [nan + ": %s bad is not [A-Z0-9]{1,8}.TXT" % key])
    def test_non_string_licence_and_note_names_are_refused(self):
        """H5: a non-str name is refused on every font, a falsy one (0, False, []) included."""
        for path in ("nanum/NanumGothic-Bold.ttf", "nolic/NoLicence.ttf"):
            for key in ("licence_name", "note_name"):
                for value in (0, False, [], 5):
                    with self.subTest(path=path, key=key, value=value):
                        self.assertIn(fid(path) + ": %s is not a string" % key,
                                      self.bad(path, **{key: value}))
    def test_a_batch_value_is_reported_under_the_batch(self):
        """G5: a batch value is checked once as `batch: <key> ...`, even when no font inherits it."""
        s = settings.defaults(FONTS)
        s["batch"]["sizes"] = ["16"]
        nan = fid("nanum/NanumGothic-Bold.ttf")
        errors = settings.validate(FONTS, s, ROOT)
        self.assertIn("batch: sizes has a value that is not an int", errors)
        self.assertNotIn(nan + ": sizes has a value that is not an int", errors)   # inherited: reported once
        self.assertFalse(any(e.startswith(nan + ": size ") for e in errors))
        body = {"batch": copy.deepcopy(settings.defaults(FONTS)["batch"]), "fonts": {}}   # no fonts at all
        body["batch"]["sizes"] = ["16"]
        self.assertIn("batch: sizes has a value that is not an int", settings.validate(FONTS, body, ROOT))
    def test_a_fonts_own_batch_value_is_reported_under_its_id(self):
        """G5: an override the font carries is still reported under the font's id."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        errors = self.bad("nanum/NanumGothic-Bold.ttf", sizes=["16"])
        self.assertIn(nan + ": sizes has a value that is not an int", errors)
        self.assertNotIn("batch: sizes has a value that is not an int", errors)
    def test_a_repeated_problem_is_reported_once(self):
        """G3: two values that give the same string report it once, in order."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        self.assertEqual(self.bad("nanum/NanumGothic-Bold.ttf", sizes=[99, 99]),
                         [nan + ": size 99 is not 6..96"])
        self.assertEqual(self.bad("nanum/NanumGothic-Bold.ttf",
                                  names={"precomposed/16/1": "x", "precomposed/16/2": "x"}),
                         [nan + ": name x is not [A-Z0-9]{1,8}.SVF"])
    def test_a_bad_batch_value_never_crashes_an_inheriting_font(self):
        """G5/F1: a wrongly typed batch value is refused as `batch: ...`, never iterated or hashed under a font id."""
        idx = naming.RepoIndex(os.path.join(fixtures.REPO_DIR, "svf"))
        nan = fid("nanum/NanumGothic-Bold.ttf")
        for key, value in (("sizes", 5), ("bpp", 1), ("kinds", [{}]), ("preset", []), ("range", []), ("dest", 5)):
            with self.subTest(key=key):
                body = {"batch": copy.deepcopy(settings.defaults(FONTS)["batch"]),
                        "fonts": {nan: {"options": {"mkfont": {"ascent": 3}}, "selected": True}}}
                body["batch"][key] = value
                for errors in (settings.validate(FONTS, body, ROOT),
                               settings.run_ready(FONTS, body, idx, ROOT)):
                    self.assertTrue(any(e.startswith("batch: %s" % key) for e in errors), errors)
    def test_empty_licence_and_note_names_are_refused_when_selected(self):
        """F3: the plan's TXT_RE rule refuses `""` for a selected font."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        self.assertIn(nan + ": licence_name  is not [A-Z0-9]{1,8}.TXT", self.bad("nanum/NanumGothic-Bold.ttf", licence_name=""))
        self.assertIn(nan + ": note_name  is not [A-Z0-9]{1,8}.TXT", self.bad("nanum/NanumGothic-Bold.ttf", note_name=""))
    def test_repo_licence_path_shape(self):
        """F4: `validate` has no index, so it checks a repo path's shape only."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        for path in ("../etc/passwd", "/etc/passwd", "dos/NOPE", "dos/../passwd"):
            self.assertIn(nan + ": licence path %s is not a text file in svf/" % path,
                          self.bad("nanum/NanumGothic-Bold.ttf", licence={"kind": "repo", "path": path}))
        self.assertIn(nan + ": licence path None is not a text file in svf/",
                      self.bad("nanum/NanumGothic-Bold.ttf", licence={"kind": "repo"}))
    def test_empty_licence_is_refused(self):
        nan = fid("nanum/NanumGothic-Bold.ttf")
        self.assertIn(nan + ": licence text is empty",
                      self.bad("nanum/NanumGothic-Bold.ttf", licence={"kind": "text", "text": "   "}))
        with tempfile.TemporaryDirectory() as up:
            with open(os.path.join(up, "zero.txt"), "w", encoding="utf-8"):
                pass
            font = copy.deepcopy(font_entry(nan))
            font["licences"] = [{"path": "zero.txt", "first_line": ""}]
            s = settings.defaults([font])
            self.assertIn(nan + ": licence text is empty", settings.validate([font], s, up))
    def test_validate_and_run_ready_never_raise_on_malformed_bodies(self):
        """F1: every wrongly typed body comes back as errors, never as an exception."""
        idx = naming.RepoIndex(os.path.join(fixtures.REPO_DIR, "svf"))
        nan = fid("nanum/NanumGothic-Bold.ttf")
        base = settings.defaults(FONTS)
        batch_keys = {key: copy.deepcopy(base["batch"][key]) for key in settings.BATCH_KEYS}
        cases = [
            ("settings not an object", [], "settings: not an object"),
            ("batch not an object", {"batch": [], "fonts": {}}, "batch: not an object"),
            ("fonts not an object", {"batch": batch_keys, "fonts": []}, "fonts: not an object"),
            ("font not an object", {nan: []}, nan + ": not an object"),
            ("sizes not ints", {nan: {"sizes": ["16"]}}, nan + ": sizes has a value that is not an int"),
            ("bpp not ints", {nan: {"bpp": [True]}}, nan + ": bpp has a value that is not an int"),
            ("kinds item not a string", {nan: {"kinds": [{}]}}, nan + ": kinds has a value that is not a string"),
            ("kinds a string", {nan: {"kinds": "jamo"}}, nan + ": kinds is not a list"),
            ("preset not a string", {nan: {"preset": ["plain"]}}, nan + ": preset is not a string"),
            ("range not a string", {nan: {"range": ["2350"]}}, nan + ": range is not a string"),
            ("dest not a string", {nan: {"dest": 5}}, nan + ": dest is not a string"),
            ("layout not a string", {nan: {"layout": 5}}, nan + ": layout is not a string"),
            ("dos_layout not a string", {nan: {"dos_layout": 5}}, nan + ": dos_layout is not a string"),
            ("latin_companion not a string", {nan: {"latin_companion": 5}}, nan + ": latin_companion is not a string"),
            ("options not an object", {nan: {"options": [1]}}, nan + ": options is not an object"),
            ("options tool not an object", {nan: {"options": {"mkfont": [1]}}}, nan + ": options mkfont is not an object"),
            ("unknown option key", {nan: {"options": {"mkfont": {"zzz": 1}}}}, nan + ": unknown option key mkfont.zzz"),
            ("option value wrong type", {nan: {"options": {"mkfont": {"cell": "16"}}}}, nan + ": option mkfont.cell is not an int or null"),
            ("names not an object", {nan: {"names": []}}, nan + ": names is not an object"),
            ("names value not a string", {nan: {"names": {"precomposed/16/1": 5}}}, nan + ": names has a value that is not a string"),
            ("licence not an object", {nan: {"licence": "x"}}, nan + ": licence is not an object"),
            ("licence path not a string", {nan: {"licence": {"kind": "upload", "path": 5}}}, nan + ": licence path is not a string"),
            ("licence text not a string", {nan: {"licence": {"kind": "text", "text": 5}}}, nan + ": licence text is not a string"),
            ("selected not a bool", {nan: {"selected": "yes"}}, nan + ": selected is not true or false"),
            ("experimental not a bool", {nan: {"experimental": 1}}, nan + ": experimental is not true or false"),
        ]
        for label, fonts_part, expected in cases:
            with self.subTest(label=label):
                if isinstance(fonts_part, list):
                    body = fonts_part
                elif isinstance(fonts_part, dict) and set(fonts_part) == {"batch", "fonts"}:
                    body = fonts_part
                else:
                    body = {"batch": copy.deepcopy(batch_keys), "fonts": fonts_part}
                errors = settings.validate(FONTS, body, ROOT)
                self.assertIsInstance(errors, list)
                self.assertIn(expected, errors)
                errors = settings.run_ready(FONTS, body, idx, ROOT)
                self.assertIsInstance(errors, list)
                self.assertIn(expected, errors)


class ControlsTest(unittest.TestCase):
    """The recipes' controls (options schema, ranges, dy, jamo_route) on synthetic entries with id f01."""

    UNSET = object()

    def errors(self, font=FONT_TTF, options=None, dy=UNSET, jamo_route=UNSET, kinds=None, experimental=False,
               **per_over):
        font = dict(copy.deepcopy(font), id="f01")
        s = settings.defaults([font])
        per = s["fonts"]["f01"]
        per.update(selected=True, experimental=experimental, licence={"kind": "text", "text": "OFL"},
                   licence_name="OFL.TXT", note_name="NOTE.TXT")
        if font["source_kind"] == "dos-raw":
            per["dos_layout"] = "844"
        if kinds is not None:
            per["kinds"] = kinds
        if options is not None:
            per["options"] = options
        if dy is not self.UNSET:
            per["dy"] = dy
        if jamo_route is not self.UNSET:
            per["jamo_route"] = jamo_route
        per.update(per_over)
        return settings.validate([font], s, None)

    def test_clean_base_case(self):
        self.assertEqual(self.errors(), [])

    def test_new_defaults_and_unique_keys(self):
        keys = [k for group in settings.DEFAULT_OPTIONS.values() for k in group]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(settings.DEFAULT_OPTIONS["jamoset"]["clean"], True)
        self.assertEqual(settings.DEFAULT_OPTIONS["bdfface"], {"latin_ascent": None, "hangul_ascent": None})
        self.assertEqual(settings.OPTION_CHOICES, {"binarize": ("threshold", "ridge", "mono")})
        self.assertEqual(settings.DEFAULT_OPTIONS["mkfont"],
                         {"cell": None, "ascent": None, "width": None, "mono_hint": False, "clip_cell": False,
                          "fit_cell": False, "latin": False, "space_advance": None})
        self.assertEqual(settings.DEFAULT_OPTIONS["jamoset"],
                         {"embolden": False, "symbols": False, "jset_version": None, "jamo_ascent": None,
                          "fit_baseline": None, "aa_refine": None, "clean": True, "binarize": "threshold"})
        self.assertIn("dy", settings.FONT_ONLY_KEYS)
        self.assertIn("jamo_route", settings.FONT_ONLY_KEYS)

    def test_choice_value_type(self):
        errs = self.errors(options={"jamoset": {"binarize": "otsu"}})
        self.assertIn("f01: option jamoset.binarize is not one of threshold, ridge, mono", errs)
        self.assertIn("f01: option jamoset.binarize is not one of threshold, ridge, mono",
                      self.errors(options={"jamoset": {"binarize": 1}}))
        self.assertEqual(self.errors(options={"jamoset": {"binarize": "ridge", "clean": False}}), [])
        self.assertIn("f01: option jamoset.clean is not true or false",
                      self.errors(options={"jamoset": {"clean": "no"}}))

    def test_int_ranges(self):
        for key, group, bad, msg in (("width", "mkfont", 0, "f01: width 0 is not 1..255"),
                                     ("width", "mkfont", 256, "f01: width 256 is not 1..255"),
                                     ("aa_refine", "jamoset", 10, "f01: aa_refine 10 is not 0..9")):
            with self.subTest(key=key, bad=bad):
                self.assertIn(msg, self.errors(options={group: {key: bad}}))
        self.assertEqual(self.errors(options={"jamoset": {"aa_refine": 0}, "mkfont": {"width": 255}}), [])

    def test_ascent_zero_refused_on_every_ascent_key(self):
        cases = ((FONT_TTF, {}, "mkfont", "ascent", "cell"),
                 (FONT_DOS, {}, "jamoset", "jamo_ascent", "cell"),
                 (FONT_TTF, {"experimental": True, "kinds": ["jamo"]}, "jamoset", "fit_baseline", "size"),
                 (FONT_KSC, {}, "bdfface", "latin_ascent", "box"),
                 (FONT_KSC, {}, "bdfface", "hangul_ascent", "box"))
        for font, over, group, key, word in cases:
            with self.subTest(key=key):
                self.assertIn("f01: %s 0 is not 1..%s" % (key, word),
                              self.errors(font, options={group: {key: 0}}, **over))

    def test_ascent_keys_against_their_cells(self):
        self.assertIn("f01: jamo_ascent 17 is over the cell 16", self.errors(FONT_DOS, options={"jamoset": {"jamo_ascent": 17}}))
        self.assertEqual([e for e in self.errors(FONT_DOS, options={"jamoset": {"jamo_ascent": 16}}) if "jamo_ascent" in e], [])
        self.assertIn("f01: jamo_ascent 17 is over the cell 16", self.errors(FONT_JOHAB, options={"jamoset": {"jamo_ascent": 17}}))
        self.assertIn("f01: hangul_ascent 25 is over the cell 24", self.errors(FONT_KSC, options={"bdfface": {"hangul_ascent": 25}}))
        self.assertIn("f01: latin_ascent 25 is over the cell 24", self.errors(FONT_KSC, options={"bdfface": {"latin_ascent": 25}}))
        self.assertIn("f01: fit_baseline 17 is over the cell 16",
                      self.errors(options={"jamoset": {"fit_baseline": 17}}, experimental=True, kinds=["jamo"]))

    def test_dy_shape_and_bounds(self):
        self.assertIn("f01: dy is not an object of code point -> int", self.errors(dy={"0x41": "1"}))
        self.assertIn("f01: dy is not an object of code point -> int", self.errors(dy={"zz": 1}))
        self.assertIn("f01: dy is not an object of code point -> int", self.errors(dy=[1]))
        self.assertIn("f01: dy 0xF0001 names a jamo piece", self.errors(dy={"0xF0001": 1}))
        self.assertIn("f01: dy 17 of 0x41 is not -16..16", self.errors(dy={"0x41": 17}))     # sizes [16]
        self.assertIn("f01: dy -17 of 0x41 is not -16..16", self.errors(dy={"0x41": -17}))
        self.assertEqual(self.errors(dy={"0x41": -2, "g": 1}), [])
        # the cell option replaces the size as the bound, capped at 127
        self.assertEqual(self.errors(dy={"0x41": 20}, options={"mkfont": {"cell": 24}}), [])
        self.assertIn("f01: dy 128 of 0x41 is not -127..127", self.errors(dy={"0x41": 128}, options={"mkfont": {"cell": 200}}))

    def test_dy_needs_a_precomposed_face(self):
        self.assertIn("f01: dy needs a precomposed face", self.errors(kinds=["jamo"], experimental=True, dy={"0x41": 1}))
        self.assertEqual([e for e in self.errors(kinds=["jamo"], experimental=True, dy={}) if "dy" in e], [])

    def test_jamo_route_rules(self):
        self.assertIn("f01: jamo_route hanterm is not offered", self.errors(kinds=["jamo"], jamo_route="hanterm"))
        self.assertIn("f01: jamo_route experimental fit needs experimental",
                      self.errors(kinds=["jamo"], jamo_route="experimental fit"))
        self.assertIn("f01: jamo_route 3 is not a route label", self.errors(jamo_route=3))
        self.assertEqual(self.errors(kinds=["jamo"], experimental=True, jamo_route="experimental fit"), [])
        self.assertEqual(self.errors(FONT_COMPOSITE, kinds=["jamo"], jamo_route="composite"), [])

    def test_route_for_with_jamo_route(self):
        self.assertEqual(routes.route_for(FONT_COMPOSITE, "jamo", True, "composite").label, "composite")
        self.assertIsNone(routes.route_for(FONT_TTF, "jamo", False, "experimental fit"))
        self.assertEqual(routes.route_for(FONT_TTF, "jamo", True, "experimental fit").label, "experimental fit")
        self.assertIsNone(routes.route_for(FONT_TTF, "jamo", True, "hanterm"))
        self.assertEqual(routes.route_for(FONT_TTF, "jamo", True).label, "experimental fit")          # no label: today's rule
        self.assertEqual(routes.route_for(FONT_TTF, "precomposed", False, "composite").label, "mkfont")   # only for jamo

    def test_fit_cell_against_the_merged_clip_cell(self):
        self.assertIn("f01: fit_cell and clip_cell: choose one",
                      self.errors(options={"mkfont": {"fit_cell": True, "clip_cell": True}}))
        self.assertIn("f01: fit_cell and clip_cell: choose one",
                      self.errors(preset="dos-u-2bpp", bpp=[2], options={"mkfont": {"fit_cell": True}}))
        self.assertEqual(self.errors(options={"mkfont": {"fit_cell": True}}), [])

    def test_binarize_mono_refusals(self):
        self.assertIn("f01: binarize mono needs freetype-py",
                      self.errors(kinds=["jamo"], experimental=True, bpp=[1], options={"jamoset": {"binarize": "mono"}}))
        self.assertIn("f01: binarize mono is not a jamovec choice",
                      self.errors(font=FONT_COMPOSITE, kinds=["jamo"], bpp=[1], options={"jamoset": {"binarize": "mono"}}))
        # a font the libraries are there for takes it; 2 bpp has no binarize
        masked = dict(FONT_TTF, mask_ok=True)
        self.assertEqual(self.errors(font=masked, kinds=["jamo"], experimental=True, bpp=[1],
                                     options={"jamoset": {"binarize": "mono"}}), [])
        self.assertEqual([e for e in self.errors(kinds=["jamo"], experimental=True, bpp=[2],
                                                 options={"jamoset": {"binarize": "mono"}}) if "binarize" in e], [])

    def test_plan_steps_carry_the_panel_flags(self):
        font = dict(copy.deepcopy(FONT_TTF), id="f01", path="in.ttf")
        s = settings.defaults([font])
        s["fonts"]["f01"].update(selected=True, experimental=True, kinds=["precomposed", "jamo"], bpp=[1],
                                 options={"mkfont": {"width": 20, "latin": True}, "jamoset": {"binarize": "ridge", "fit_baseline": 11}})
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "up"))
            job = {"fonts": [font], "settings": s}
            steps = settings.plan_steps(job, os.path.join(d, "job"), os.path.join(REPO_TOOLS), os.path.join(d, "up"))
        by_kind = {step["kind"]: step["argv"][0] for step in steps}
        self.assertEqual(by_kind["precomposed"][by_kind["precomposed"].index("--width") + 1], "20")
        self.assertIn("--latin", by_kind["precomposed"])
        jamo = by_kind["jamo"]
        self.assertEqual(jamo[jamo.index("--binarize") + 1], "ridge")
        self.assertEqual(jamo[jamo.index("--baseline") + 1], "11")
        self.assertEqual(jamo.count("--binarize"), 1)


class RunReadyTest(unittest.TestCase):
    def setUp(self):
        self.idx = naming.RepoIndex(os.path.join(fixtures.REPO_DIR, "svf"))
    def only(self, *paths, **over):
        """Defaults with only @p paths selected and @p over applied to each of them."""
        s = settings.defaults(FONTS)
        for font in FONTS:
            if font["id"] in s["fonts"]:
                s["fonts"][font["id"]]["selected"] = False
        for path in paths:
            s["fonts"][fid(path)].update(selected=True, **over)
        return s
    def test_defaults_run_ready(self):
        self.assertEqual(settings.run_ready(FONTS, self.only("nanum/NanumGothic-Bold.ttf"), self.idx, ROOT), [])
    def test_run_ready(self):
        s = settings.defaults(FONTS)
        s["fonts"][fid("svf/JAMO6J.SVF")]["dest"] = "new/fixture"       # a new folder is free
        s["fonts"][fid("svf/NEODG16.SVF")]["dest"] = "new/fixture"
        self.assertEqual(settings.run_ready(FONTS, s, self.idx, ROOT), [])
        s["fonts"][fid("svf/NEODG16.SVF")]["dest"] = "dos"
        self.assertIn(fid("svf/NEODG16.SVF") + ": NEODG16.SVF already exists in svf/dos; choose another name", settings.run_ready(FONTS, s, self.idx, ROOT))
        s = settings.defaults(FONTS); s["fonts"][fid("nolic/NoLicence.ttf")]["selected"] = True
        self.assertIn(fid("nolic/NoLicence.ttf") + ": no licence", settings.run_ready(FONTS, s, self.idx, ROOT))
    def test_nothing_selected(self):
        s = settings.defaults(FONTS)
        for font in FONTS:
            if font["id"] in s["fonts"]:
                s["fonts"][font["id"]]["selected"] = False
        self.assertEqual(settings.run_ready(FONTS, s, self.idx, ROOT), ["batch: nothing selected"])
    def test_a_name_used_twice(self):
        s = self.only("nanum/NanumGothic-Bold.ttf", "otf/Cff.otf")
        for path in ("nanum/NanumGothic-Bold.ttf", "otf/Cff.otf"):
            s["fonts"][fid(path)]["names"] = {"precomposed/16/1": "DUP.SVF"}
        self.assertIn("name DUP.SVF is used twice", settings.run_ready(FONTS, s, self.idx, ROOT))
    def test_a_note_name_clash(self):
        s = self.only("nanum/NanumGothic-Bold.ttf", note_name="NEODGM.TXT")
        self.assertIn(fid("nanum/NanumGothic-Bold.ttf") + ": NEODGM.TXT already exists in svf/dos; choose another name",
                      settings.run_ready(FONTS, s, self.idx, ROOT))
    def test_an_upload_licence_with_other_bytes_is_refused(self):
        """R2: the chosen upload licence's bytes are compared with `svf/<dest>/<licence_name>`."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        with tempfile.TemporaryDirectory() as up:
            shutil.copyfile(os.path.join(ROOT, "dos", "LICENSE.txt"), os.path.join(up, "lic.txt"))
            s = self.only("nanum/NanumGothic-Bold.ttf", licence={"kind": "upload", "path": "lic.txt"})
            self.assertIn(nan + ": OFLNANUM.TXT already exists in svf/dos; choose another name",
                          settings.run_ready(FONTS, s, self.idx, up))
    def test_repo_licence_membership_and_bytes(self):
        """F4: `run_ready` refuses a repo path the walk never listed, accepts equal bytes, refuses others."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        self.assertIn(nan + ": licence path dos/NOPE.TXT is not a text file in svf/",
                      settings.run_ready(FONTS, self.only("nanum/NanumGothic-Bold.ttf",
                                                          licence={"kind": "repo", "path": "dos/NOPE.TXT"},
                                                          licence_name="OFLLIC.TXT"), self.idx, ROOT))
        self.assertEqual(settings.run_ready(FONTS, self.only("nanum/NanumGothic-Bold.ttf",
                                                             licence={"kind": "repo", "path": "dos/OFLNANUM.TXT"},
                                                             licence_name="OFLNANUM.TXT"), self.idx, ROOT), [])
        self.assertIn(nan + ": OFLNANUM.TXT already exists in svf/dos; choose another name",
                      settings.run_ready(FONTS, self.only("nanum/NanumGothic-Bold.ttf",
                                                          licence={"kind": "repo", "path": "dos/NEODGM.TXT"},
                                                          licence_name="OFLNANUM.TXT"), self.idx, ROOT))
    def test_a_destination_the_walk_could_not_read_is_refused(self):
        """F6: an unreadable destination folder fails at `POST run`, not at `write_zip`."""
        svf = tempfile.mkdtemp(prefix="svf-unlisted-")
        locked = os.path.join(svf, "new", "x")
        os.makedirs(locked)
        os.chmod(locked, 0)
        try:
            idx = naming.RepoIndex(svf)
            self.assertIn("new/x", idx.unlisted)
            s = self.only("nanum/NanumGothic-Bold.ttf", dest="new/x")
            self.assertIn(fid("nanum/NanumGothic-Bold.ttf") + ": svf/new/x could not be read; choose another folder",
                          settings.run_ready(FONTS, s, idx, ROOT))
        finally:
            os.chmod(locked, 0o755)
            shutil.rmtree(svf, ignore_errors=True)
    def test_the_note_dry_run(self):
        """The Task 6 note rule: a bad field becomes `f01: note: <message>`, never a 500."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        font = font_entry(nan)
        old = font["family"]
        font["family"] = "bad\x1b"
        try:
            s = self.only("nanum/NanumGothic-Bold.ttf")
            errors = settings.run_ready(FONTS, s, self.idx, ROOT)
        finally:
            font["family"] = old
        self.assertIn(nan + ": note: note_text: family carries the control character '\\x1b'", errors)
    def test_run_ready_needs_an_upload_dir(self):
        """G4: `upload_dir` is required, and a missing one fails at the call, not later."""
        s = settings.defaults(FONTS)
        with self.assertRaises(TypeError) as cm:
            settings.run_ready(FONTS, s, self.idx, None)
        self.assertEqual(str(cm.exception), "run_ready needs upload_dir")
    def test_an_upload_licence_outside_the_batch_is_never_opened(self):
        """G1: a path `validate` refused is not hashed; `/dev/zero` must not hang the request."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        s = self.only("nanum/NanumGothic-Bold.ttf", licence={"kind": "upload", "path": "/dev/zero"})
        def alarm(signum, frame):
            raise AssertionError("run_ready did not return within 2 seconds")
        previous = signal.signal(signal.SIGALRM, alarm)
        signal.alarm(2)
        try:
            errors = settings.run_ready(FONTS, s, self.idx, ROOT)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
        self.assertIn(nan + ": licence /dev/zero is not a licence file in the batch", errors)
        self.assertIn(nan + ": OFLNANUM.TXT already exists in svf/dos; choose another name", errors)
    def test_a_traversal_licence_path_is_never_opened(self):
        """G1: `../../../etc/hostname` is not one of the batch's paths, so its bytes are never read."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        s = self.only("nanum/NanumGothic-Bold.ttf",
                      licence={"kind": "upload", "path": "../../../etc/hostname"})
        real_open = open
        def guard(file, *args, **kwargs):
            self.assertNotIn("etc/hostname", str(file))
            return real_open(file, *args, **kwargs)
        with mock.patch("builtins.open", guard):
            errors = settings.run_ready(FONTS, s, self.idx, ROOT)
        self.assertIn(nan + ": licence ../../../etc/hostname is not a licence file in the batch", errors)
    def test_validate_errors_are_not_repeated(self):
        """G3: `run_ready` returns `validate`'s list plus its own new errors, each string once."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        s = self.only("nanum/NanumGothic-Bold.ttf", licence={"kind": "repo", "path": "../x.TXT"},
                      licence_name="OFLLIC.TXT")
        errors = settings.run_ready(FONTS, s, self.idx, ROOT)
        self.assertEqual(errors.count(nan + ": licence path ../x.TXT is not a text file in svf/"), 1)
        self.assertEqual(len(errors), len(set(errors)))
    def test_an_upload_licence_with_equal_bytes_passes(self):
        """G7: the upload's bytes equal `svf/dos/OFLNANUM.TXT`, so the clash is accepted."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        with tempfile.TemporaryDirectory() as up:
            os.makedirs(os.path.join(up, "nanum"))
            shutil.copyfile(os.path.join(ROOT, "nanum", "OFL.txt"), os.path.join(up, "nanum", "OFL.txt"))
            s = self.only("nanum/NanumGothic-Bold.ttf", licence={"kind": "upload", "path": "nanum/OFL.txt"})
            self.assertEqual(settings.run_ready(FONTS, s, self.idx, up), [])
    def test_a_zero_byte_upload_licence_is_refused_by_run_ready(self):
        """G7: a zero-byte upload is `licence text is empty` at `POST run` too."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        with tempfile.TemporaryDirectory() as up:
            os.makedirs(os.path.join(up, "nanum"))
            open(os.path.join(up, "nanum", "OFL.txt"), "w", encoding="utf-8").close()
            s = self.only("nanum/NanumGothic-Bold.ttf", licence={"kind": "upload", "path": "nanum/OFL.txt"})
            errors = settings.run_ready(FONTS, s, self.idx, up)
        self.assertIn(nan + ": licence text is empty", errors)
    def test_two_licence_names_in_one_dest_with_different_texts(self):
        """H2: two selected fonts in one dest must not share a licence_name with different bytes."""
        s = self.only("nanum/NanumGothic-Bold.ttf", "otf/Cff.otf", licence_name="LICX.TXT")
        self.assertIn("LICX.TXT is used twice in svf/dos with different texts",
                      settings.run_ready(FONTS, s, self.idx, ROOT))
    def test_two_upload_licences_with_equal_bytes_may_share_a_name(self):
        """H2: one OFL shared by a family is allowed; the upload's bytes decide."""
        s = self.only("nanum/NanumGothic-Bold.ttf", "otf/Cff.otf",
                      licence={"kind": "upload", "path": "nanum/OFL.txt"}, licence_name="LICX.TXT")
        self.assertEqual(settings.run_ready(FONTS, s, self.idx, ROOT), [])
    def test_two_repo_licences_with_equal_bytes_may_share_a_name(self):
        """H2: the repo file's bytes decide for a `repo` licence."""
        s = self.only("nanum/NanumGothic-Bold.ttf", "otf/Cff.otf",
                      licence={"kind": "repo", "path": "dos/OFLNANUM.TXT"}, licence_name="LICX.TXT")
        self.assertEqual(settings.run_ready(FONTS, s, self.idx, ROOT), [])
    def test_two_text_licences_with_equal_text_may_share_a_name(self):
        """H2: the UTF-8 bytes of the text decide for a `text` licence."""
        s = self.only("nanum/NanumGothic-Bold.ttf", "otf/Cff.otf",
                      licence={"kind": "text", "text": "shared\n"}, licence_name="LICX.TXT")
        self.assertEqual(settings.run_ready(FONTS, s, self.idx, ROOT), [])
    def test_a_note_name_used_twice_in_one_dest(self):
        """H2: a note_name two selected fonts share in one dest is refused."""
        s = self.only("nanum/NanumGothic-Bold.ttf", "otf/Cff.otf", note_name="SAME.TXT")
        self.assertIn("SAME.TXT is used twice in svf/dos", settings.run_ready(FONTS, s, self.idx, ROOT))
    def test_a_licence_name_equal_to_its_own_note_name(self):
        """H2: one font's licence_name must differ from its note_name."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        s = self.only("nanum/NanumGothic-Bold.ttf", licence_name="SAME.TXT", note_name="SAME.TXT")
        self.assertIn(nan + ": licence_name and note_name are the same",
                      settings.run_ready(FONTS, s, self.idx, ROOT))
    def test_a_licence_name_equal_to_another_fonts_note_name(self):
        """H2: a licence_name of one font equal to another's note_name in one dest is refused."""
        nan = fid("nanum/NanumGothic-Bold.ttf")
        cff = fid("otf/Cff.otf")
        s = self.only("nanum/NanumGothic-Bold.ttf", "otf/Cff.otf")
        s["fonts"][nan]["licence_name"] = "SAME.TXT"
        s["fonts"][cff]["note_name"] = "SAME.TXT"
        self.assertIn("SAME.TXT is used twice in svf/dos", settings.run_ready(FONTS, s, self.idx, ROOT))


class StepsTest(unittest.TestCase):
    def only(self, *paths, **over):
        s = settings.defaults(FONTS)
        for font in FONTS:
            if font["id"] in s["fonts"]:
                s["fonts"][font["id"]]["selected"] = False
        for path in paths:
            s["fonts"][fid(path)].update(selected=True, **over)
        return s
    def test_plan_steps(self):
        with tempfile.TemporaryDirectory() as jd:
            s = settings.defaults(FONTS)
            s["fonts"][fid("dos/HAN.FNT")].update(selected=True, dos_layout="844")
            for p in ("otf/Cff.otf", "bdf/iso.bdf", "bdf/ksc.bdf", "bdf/johab.bdf", "svf/NEODG16.SVF", "svf/JAMO6J.SVF"):
                s["fonts"][fid(p)]["selected"] = False
            s["batch"]["bpp"] = [1, 2]                      # the batch value; nanum inherits it, HAN keeps its own [1]
            steps = settings.plan_steps({"fonts": FONTS, "settings": s}, jd, "/T", ROOT)
            kinds = [(st["font"], st["kind"], st["size"], st["bpp"]) for st in steps]
            nan = fid("nanum/NanumGothic-Bold.ttf"); comp = fid("composite/Composite.ttf"); dos = fid("dos/HAN.FNT")
            self.assertIn((nan, "precomposed", 16, 1), kinds); self.assertIn((nan, "precomposed", 16, 2), kinds)
            self.assertIn((comp, "prepare", None, None), kinds)
            self.assertLess(kinds.index((comp, "prepare", None, None)), kinds.index((comp, "jamo", 16, 1)))
            self.assertIn((dos, "jamo", 16, 1), kinds)
            st = [x for x in steps if x["font"] == nan and x["bpp"] == 1][0]
            self.assertEqual(st["output"], "work/%s/NANUM16.SVF" % st["id"])
            self.assertEqual(st["argv"][0][2], "/T/mkfont.py"); self.assertEqual(st["state"], "pending")
            self.assertTrue(os.path.isfile(os.path.join(jd, "work", "range-2350.txt")))
            d = [x for x in steps if x["font"] == dos][0]
            self.assertIn("--eng", d["argv"][0]); self.assertEqual(d["layout"], "844")
    def test_steps_follow_the_sorted_order(self):
        """R3: kind precomposed first, then ascending size, then ascending bpp, whatever order the lists are in."""
        with tempfile.TemporaryDirectory() as jd:
            s = self.only("nanum/NanumGothic-Bold.ttf", sizes=[24, 16], bpp=[2, 1])
            steps = settings.plan_steps({"fonts": FONTS, "settings": s}, jd, "/T", ROOT)
            self.assertEqual([(st["size"], st["bpp"]) for st in steps], [(16, 1), (16, 2), (24, 1), (24, 2)])
    def test_a_list_files_name_never_reaches_unicode(self):
        """I1: `mkfont --unicode` is comma-split, so the owner's list is copied under `work/` and that copy is passed."""
        with tempfile.TemporaryDirectory() as jd:
            nan = fid("nanum/NanumGothic-Bold.ttf")
            s = self.only("nanum/NanumGothic-Bold.ttf", range="x,cp949.txt")
            steps = settings.plan_steps({"fonts": FONTS, "settings": s}, jd, "/T", ROOT)
            st = [x for x in steps if x["font"] == nan and x["bpp"] == 1][0]
            copy = os.path.join(jd, "work", nan, "range.txt")
            self.assertTrue(os.path.isfile(copy))
            self.assertIn("ascii,file:" + copy, st["argv"][0])
            self.assertNotIn("x,cp949.txt", " ".join(st["argv"][0]))
            with open(copy, "rb") as a, open(os.path.join(ROOT, "x,cp949.txt"), "rb") as b:   # F10: byte for byte
                self.assertEqual(a.read(), b.read())
    def test_the_11172_range_file_is_written_and_used(self):
        with tempfile.TemporaryDirectory() as jd:
            nan = fid("nanum/NanumGothic-Bold.ttf")
            s = self.only("nanum/NanumGothic-Bold.ttf", range="11172")
            steps = settings.plan_steps({"fonts": FONTS, "settings": s}, jd, "/T", ROOT)
            self.assertTrue(os.path.isfile(os.path.join(jd, "work", "range-11172.txt")))
            st = [x for x in steps if x["font"] == nan and x["bpp"] == 1][0]
            self.assertIn("ascii,hangul", st["argv"][0])
    def test_svf_copy_step_has_no_layout(self):
        """F9: an SVF copy step is not a 844 jamo step, so its `layout` is None."""
        with tempfile.TemporaryDirectory() as jd:
            hg = fid("svf/JAMO6J.SVF")
            steps = settings.plan_steps({"fonts": FONTS, "settings": self.only("svf/JAMO6J.SVF")}, jd, "/T", ROOT)
            st = [x for x in steps if x["font"] == hg][0]
            self.assertEqual(st["kind"], "jamo")
            self.assertIsNone(st["layout"])
    def test_plan_steps_refuses_ksc_without_a_companion(self):
        """F8: `plan_steps` never calls `commands` for such a font; it raises the plan's ValueError itself."""
        with tempfile.TemporaryDirectory() as jd:
            ksc = fid("bdf/ksc.bdf")
            s = self.only("bdf/ksc.bdf", latin_companion=None)
            with self.assertRaises(ValueError) as cm:
                settings.plan_steps({"fonts": FONTS, "settings": s}, jd, "/T", ROOT)
            self.assertEqual(str(cm.exception), ksc + ": needs a Latin companion")
    def test_plan_steps_refuses_a_range_outside_the_upload(self):
        """F8: a `range` that does not resolve under `upload_dir` is refused before it is copied."""
        with tempfile.TemporaryDirectory() as jd:
            s = self.only("nanum/NanumGothic-Bold.ttf", range="/etc/passwd")
            with self.assertRaises(ValueError) as cm:
                settings.plan_steps({"fonts": FONTS, "settings": s}, jd, "/T", ROOT)
            self.assertIn("is not under the upload directory", str(cm.exception))
    def test_plan_steps_refuses_a_step_without_a_name(self):
        """G8: a direct malformed call must not write a made-up `out.svf`."""
        with tempfile.TemporaryDirectory() as jd:
            nan = fid("nanum/NanumGothic-Bold.ttf")
            s = self.only("nanum/NanumGothic-Bold.ttf", names={"precomposed/16/1": ""})
            with self.assertRaises(ValueError) as cm:
                settings.plan_steps({"fonts": FONTS, "settings": s}, jd, "/T", ROOT)
            self.assertEqual(str(cm.exception), nan + ": no name for precomposed/16/1")
    def test_plan_steps_refuses_a_source_outside_the_upload(self):
        """H4: `paths["src"]` is re-checked under `upload_dir`, like the range."""
        with tempfile.TemporaryDirectory() as jd:
            nan = fid("nanum/NanumGothic-Bold.ttf")
            font = copy.deepcopy(font_entry(nan))
            font["path"] = "../evil.ttf"
            s = self.only("nanum/NanumGothic-Bold.ttf")
            with self.assertRaises(ValueError) as cm:
                settings.plan_steps({"fonts": [font], "settings": s}, jd, "/T", ROOT)
            self.assertEqual(str(cm.exception), nan + ": ../evil.ttf is outside the upload")
    def test_plan_steps_refuses_a_companion_outside_the_upload(self):
        """H4: `eng`/`latin` are re-checked under `upload_dir` too."""
        with tempfile.TemporaryDirectory() as jd:
            dos = fid("dos/HAN.FNT"); eng = fid("dos/ENG.FNT")
            fonts = [copy.deepcopy(font_entry(dos)), copy.deepcopy(font_entry(eng))]
            for font in fonts:
                if font["id"] == eng:
                    font["path"] = "../evil.fnt"
            s = self.only("dos/HAN.FNT", dos_layout="844")
            with self.assertRaises(ValueError) as cm:
                settings.plan_steps({"fonts": fonts, "settings": s}, jd, "/T", ROOT)
            self.assertEqual(str(cm.exception), dos + ": ../evil.fnt is outside the upload")


if __name__ == "__main__":
    unittest.main()
