#!/usr/bin/env python3
"""HWP 1.x .SFT/.PFT, HWP 3.0 .FNT and headerless KS X 1001 syllable dumps in the maker: detection, routes, settings
and a local job over HTTP. Synthetic files only (the builders of tools/test_hwpfont.py); no HWP data is in the
repository.

  python3 -m unittest discover -s maker/test -p 'test_hwp_inputs.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import shutil
import tempfile
import unittest

import detect
import hwpfont
import jamoset
import localfx
import routes
import settings
import test_hwpfont as fx
from sources import Sources
import wincompat


def ks_raw(px=24):
    """A headerless dump of 2,350 px x px syllables (Taebaek GHAN24.PFT's layout)."""
    return b"".join(fx.encode(fx.pattern(i, px, px), px, px, False) for i in range(2350))


def han16():
    """An HWP 3.0 HAN16 FNT: 2,350 syllables and an 8x4x4 set with its fill slots blank."""
    blank = set(jamoset.slots_of(8, 4, 4, 160, 248))
    return fx.hwp3(1, 16, 16, 2710, glyph=lambda i, w, h: [0] * h if i >= 2350 and i - 2350 in blank
                   else fx.pattern(i, w, h))


FILES = {
    "h1/HANGUL.SFT": lambda: fx.hwp1(16, 16, 1193),
    "h1/ASCII.SFT": lambda: fx.hwp1(8, 16, 991, glyph=fx.ascii_glyph),
    "h1/HANJA.SFT": lambda: fx.hwp1(16, 16, 4888),
    "h1p/HANGUL1.PFT": lambda: fx.hwp1(24, 24, 980),
    "h1p/ASCII.PFT": lambda: fx.hwp1(14, 24, 991, glyph=fx.ascii_glyph),
    "h3/HAN16_0.FNT": han16,
    "h3/ENG16_0.FNT": lambda: fx.hwp3(0, 8, 16, 147, glyph=fx.ascii_glyph),
    "h3/HAN24_0.FNT": lambda: fx.hwp3(1, 24, 24, 2350, count=2710),
    "h3/HAJ16_0.FNT": lambda: fx.hwp3(2, 16, 16, 4888),
    "tb/GHAN24.PFT": ks_raw,
    "zero/GHAN24.PFT": lambda: bytes(169200),
}


class Tree(wincompat.SlashEqual, unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="svf-hwp-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        for rel, make in FILES.items():
            path = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(make())

    def scan(self, *folders, local=True):
        roots = [os.path.join(self.root, f) for f in folders]
        fonts = detect.scan(Sources("local", roots), local=True) if local else detect.scan(roots[0])
        return fonts, {(f.get("root", 0), f["path"], f["face_index"]): f for f in fonts}


class DetectTest(Tree):
    def test_hwp1_faces_and_companion(self):
        fonts, by = self.scan("h1")
        faces = [by[(0, "HANGUL.SFT", i)] for i in range(3)]
        self.assertEqual([(f["format"], f["source_kind"], f["sizes"], f["jamo"]) for f in faces],
                         [("hwp1", "hwp1", [16], "native (hwp1)")] * 3)
        self.assertEqual([f["family"] for f in faces], ["HANGUL Myeongjo", "HANGUL Gothic", "HANGUL Saemmul"])
        self.assertEqual(faces[1]["label"], "HWP 1.x Hangul (screen .SFT, 16x16), face 1 of 3 (Gothic by HWP's menu order)")
        self.assertEqual(faces[0]["coverage"], detect.HWP1_COVERAGE)
        eng = by[(0, "ASCII.SFT", 0)]
        self.assertEqual((eng["format"], eng["eng"]["cell"]), ("eng", "8x16"))
        self.assertEqual([f["companions"] for f in faces], [[eng["id"]]] * 3)
        hanja = by[(0, "HANJA.SFT", 0)]
        self.assertEqual((hanja["source_kind"], hanja["label"]),
                         ("other", "HWP 1.x font: 4888 hanja of 16x16, not a Hangul face"))

    def test_hwp_is_local_only(self):
        fonts, by = self.scan("h1", local=False)
        self.assertEqual({f["path"]: (f["format"], f["source_kind"], f["label"]) for f in fonts},
                         {p: ("hwp1", "other", detect.HWP_LOCAL_ONLY) for p in ("HANGUL.SFT", "ASCII.SFT", "HANJA.SFT")})
        fonts, _ = self.scan("h3", local=False)
        self.assertEqual({f["format"] for f in fonts}, {"hwp3"})
        self.assertEqual({f["source_kind"] for f in fonts}, {"other"})

    def test_hwp3_and_ks_raw(self):
        fonts, by = self.scan("h3", "tb", "zero")
        h16 = by[(0, "HAN16_0.FNT", 0)]
        self.assertEqual((h16["source_kind"], h16["sizes"], h16["hwp"]["jamo844"], h16["jamo"]),
                         ("ks-raw", [16], True, "native (844-hwp3)"))
        self.assertEqual(h16["label"], "HWP 3.0 FNT Hangul 16x16: 2,350 KS X 1001 syllables + an 8x4x4 jamo set")
        h24 = by[(0, "HAN24_0.FNT", 0)]
        self.assertEqual((h24["source_kind"], h24["hwp"]["jamo844"], h24["jamo"]), ("ks-raw", False, "none"))
        self.assertEqual(h24["coverage"], detect.KS_RAW_COVERAGE)
        self.assertEqual(by[(0, "ENG16_0.FNT", 0)]["format"], "eng")
        self.assertIn(by[(0, "ENG16_0.FNT", 0)]["id"], h16["companions"])
        self.assertEqual(by[(0, "HAJ16_0.FNT", 0)]["source_kind"], "other")
        tb = by[(1, "GHAN24.PFT", 0)]
        self.assertEqual((tb["format"], tb["source_kind"], tb["label"]),
                         ("ks-raw", "ks-raw", "KS X 1001 raw dump Hangul 24x24: 2,350 KS X 1001 syllables"))
        zero = by[(2, "GHAN24.PFT", 0)]                    # a blank file of that size is not a dump: the .PFT rule names it
        self.assertEqual((zero["format"], zero["source_kind"]), ("hwp-pft", "other"))
        up, _ = self.scan("tb", local=False)                # a headerless dump is read by its size in an upload too
        self.assertEqual([f["source_kind"] for f in up], ["ks-raw"])

    def test_the_hwp1_printer_ascii_is_offered_to_a_24px_face_from_another_folder(self):
        fonts, by = self.scan("h1p", "tb")
        tb, eng = by[(1, "GHAN24.PFT", 0)], by[(0, "ASCII.PFT", 0)]
        self.assertEqual(eng["eng"]["cell"], "14x24")
        self.assertIn(eng["id"], tb["companions"])
        self.assertEqual(settings.defaults(fonts)["fonts"][tb["id"]]["latin_companion"], eng["id"])


class RoutesTest(Tree):
    PATHS = {"tools": "/T", "src": "/s/X", "out": "/w/O.SVF", "work": "/w", "eng": "/e/ENG", "latin": None,
             "master": None, "range_file": None}

    def test_hwp1_routes_and_argv(self):
        font = {"source_kind": "hwp1", "face_index": 2, "sizes": [16]}
        rs = routes.routes(font)
        self.assertEqual([(r.kind, r.label, r.native, r.layouts) for r in rs],
                         [("jamo", "hwp1", True, ["hwp1"]), ("precomposed", "hwp bdf + mkfont", True, [])])
        argv = rs[0].commands(font, 16, 1, "hwp1", ("2350", None), self.PATHS, [["--embolden"]])
        self.assertEqual(argv[0][3:], ["/s/X", "--layout", "hwp1", "--face", "2", "--check", "-o", "/w/O.SVF",
                                       "--eng", "/e/ENG", "--embolden"])
        argv = rs[1].commands(font, 16, 1, None, ("11172", None), dict(self.PATHS, eng=None), [["--ascent", "13"]])
        self.assertEqual([a[2].rsplit("/", 1)[1] for a in argv], ["hwpfont.py", "mkfont.py", "svf2to3.py"])
        self.assertEqual(argv[0][3:], ["bdf", "/s/X", "--face", "2", "--syllables", "all", "-o", "/w/hwp.bdf"])
        self.assertEqual(argv[1][3:], ["/w/hwp.bdf", "/w/mkfont.tmp", "--size", "16", "--bpp", "1", "--unicode", "hangul",
                                       "--ascent", "13"])

    def test_ks_raw_routes(self):
        plain = {"source_kind": "ks-raw", "sizes": [24], "hwp": {"jamo844": False}}
        self.assertEqual([r.label for r in routes.routes(plain)], ["hwp bdf + mkfont", "hwp bdf + from-svf fit"])
        self.assertIsNone(routes.route_for(plain, "jamo", False))
        h16 = {"source_kind": "ks-raw", "sizes": [16], "hwp": {"jamo844": True}}
        self.assertEqual(routes.route_for(h16, "jamo", False).label, "hwp3 844")
        fit = routes.route_for(plain, "jamo", True)
        argv = fit.commands(plain, 24, 1, "844", ("2350", None), self.PATHS, [["--jset-version", "2"]])
        self.assertEqual(argv[0][3:], ["bdf", "/s/X", "--ascii", "/e/ENG", "-o", "/w/hwp.bdf"])
        self.assertIn("ascii,ksx1001-hangul", argv[1])
        self.assertEqual(argv[2][-3:], ["/w/precomposed.svf", "--profile", "default"])
        self.assertEqual(argv[3][3:], ["--layout", "844", "--from-svf", "/w/precomposed.svf", "--check", "-o", "/w/O.SVF",
                                       "--jset-version", "2"])

    def test_defaults_validate(self):
        fonts, by = self.scan("h1", "h3")
        st = settings.defaults(fonts)
        face = by[(0, "HANGUL.SFT", 1)]
        per = st["fonts"][face["id"]]
        self.assertEqual((per.get("kinds"), per.get("layout"), per["latin_companion"]),
                         (["jamo"], "hwp1", by[(0, "ASCII.SFT", 0)]["id"]))
        h16 = by[(1, "HAN16_0.FNT", 0)]
        self.assertEqual(st["fonts"][h16["id"]].get("layout"), "844-hwp3")
        for fid in (face["id"], h16["id"]):
            st["fonts"][fid]["selected"] = True
        self.assertEqual([e for e in settings.validate(fonts, st, Sources("local", [os.path.join(self.root, "h1"),
                                                                                    os.path.join(self.root, "h3")]))
                          if e.startswith((face["id"], h16["id"]))], [])


class ReviewFixTest(Tree):
    def put(self, rel, data):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)

    def test_hwp_english_is_not_offered_to_a_dos_raw_font_and_stays_alone(self):
        import inputfx
        self.put("dos/HAN24.FNT", inputfx.dos844_24())
        self.put("dos/ENG24_0.FNT", fx.hwp3(0, 12, 24, 147, glyph=fx.ascii_glyph))
        self.put("dos/GASCII24.PFT", inputfx.pft_eng())
        self.put("alone/ASCII.SFT", FILES["h1/ASCII.SFT"]())
        fonts, by = self.scan("dos", "alone")
        dos, hwp_eng, raw_eng = by[(0, "HAN24.FNT", 0)], by[(0, "ENG24_0.FNT", 0)], by[(0, "GASCII24.PFT", 0)]
        self.assertEqual(dos["companions"], [raw_eng["id"]])        # johab844 / jamoset reads the raw one
        alone = by[(1, "ASCII.SFT", 0)]
        self.assertEqual((alone["format"], alone["eng"]["cell"]), ("eng", "8x16"))

    def test_companion_defaults_take_the_own_height_and_family(self):
        self.put("k/MHAN24.PFT", ks_raw())
        self.put("k/GASCII24.PFT", bytes(12288))
        self.put("k/MASCII24.PFT", bytes(12288))
        self.put("k/ENG16_0.FNT", fx.hwp3(0, 8, 16, 147, glyph=fx.ascii_glyph))
        self.put("big/96MT.FNT", fx.hwp3(1, 32, 32, 2350))            # a tall face: the tallest companion that fits
        self.put("big/ENG16_0.FNT", fx.hwp3(0, 8, 16, 147, glyph=fx.ascii_glyph))
        self.put("big/ENG24_0.FNT", fx.hwp3(0, 12, 24, 147, glyph=fx.ascii_glyph))
        fonts, by = self.scan("k", "big")
        st = settings.defaults(fonts)
        self.assertEqual(st["fonts"][by[(0, "MHAN24.PFT", 0)]["id"]]["latin_companion"], by[(0, "MASCII24.PFT", 0)]["id"])
        self.assertEqual(st["fonts"][by[(1, "96MT.FNT", 0)]["id"]]["latin_companion"], by[(1, "ENG24_0.FNT", 0)]["id"])

    def test_no_default_companion_when_none_fits(self):
        """A 16-row HANGUL.SFT with only the 14x24 ASCII.PFT beside it gets no default (it would fail validation); a 15 px
        face keeps the 8x16 font that goes with any face over a 12x24 one that sorts first."""
        self.put("lone/HANGUL.SFT", FILES["h1/HANGUL.SFT"]())
        self.put("lone/ASCII.PFT", FILES["h1p/ASCII.PFT"]())
        fonts, by = self.scan("lone")
        st = settings.defaults(fonts)
        face = by[(0, "HANGUL.SFT", 1)]
        self.assertEqual(face["companions"], [by[(0, "ASCII.PFT", 0)]["id"]])
        self.assertIsNone(st["fonts"][face["id"]]["latin_companion"])
        st["fonts"][face["id"]]["selected"] = True
        self.assertEqual([e for e in settings.validate(fonts, st, Sources("local", [os.path.join(self.root, "lone")]))
                          if e.startswith(face["id"])], [])
        fmap = {"e24": {"eng": {"cell": "12x24"}, "path": "A24.PFT"}, "e16": {"eng": {"cell": "8x16"}, "path": "SAN.ENG"}}
        kyra = {"source_kind": "dos-raw", "sizes": [15], "companions": ["e24", "e16"], "path": "MK15.BIT"}
        self.assertEqual(settings._default_companion(kyra, fmap), "e16")

    def test_the_ascent_control_covers_the_native_hwp_jamo_steps(self):
        with open(os.path.join(MAKER_DIR, "static", "maker.js"), encoding="utf-8") as fh:
            js = fh.read()
        cond = js[js.index('aria-label": "ascent to try"') - 600:js.index('aria-label": "ascent to try"')]
        for word in ('"dos-raw"', '"bdf-johab"', '"hwp1"', '"844-hwp3"'):
            self.assertIn(word, cond)

    def test_magic_without_the_size_falls_through(self):
        self.put("m/A.BIN", hwpfont.HWP1_MAGIC + bytes(4096 - len(hwpfont.HWP1_MAGIC)))
        self.put("m/B.BIN", b"FNT\x01" + bytes(2044))
        fonts, by = self.scan("m")
        for name in ("A.BIN", "B.BIN"):                   # read by its size as an 8x16 English font (alone: demoted)
            self.assertIn("no DOS Johab font beside it", by[(0, name, 0)]["label"])

    def test_clear_outputs_drops_the_hwp_intermediates(self):
        import jobs
        d = os.path.join(self.root, "step")
        os.makedirs(d)
        for name in (routes.HWP_BDF, routes.HWP_PRECOMPOSED):
            open(os.path.join(d, name), "wb").close()
        jobs.Worker._clear_outputs(d, os.path.join(d, "OUT.SVF"), {"kind": "jamo"})
        self.assertEqual(os.listdir(d), [])


class LocalJobTest(localfx.LocalBase):
    """An HWP 1.x face (jamo and precomposed) and an HWP 3.0 HAN16 (precomposed and its own 8x4x4) through a local job."""

    def setUp(self):
        super().setUp()
        self.src = os.path.join(self.tmp, "hwp")
        os.makedirs(self.src)
        for name, make in (("HANGUL.SFT", FILES["h1/HANGUL.SFT"]), ("ASCII.SFT", FILES["h1/ASCII.SFT"]),
                           ("HAN16_0.FNT", han16)):
            with open(os.path.join(self.src, name), "wb") as fh:
                fh.write(make())

    def test_end_to_end(self):
        jid = self.local_job([self.src])
        job = self.job(jid)
        by = {(f["path"], f["face_index"]): f for f in job["fonts"]}
        face, h16 = by[("HANGUL.SFT", 1)], by[("HAN16_0.FNT", 0)]
        st = job["settings"]
        st["fonts"][face["id"]].update(selected=True, dest="jamo-extra", kinds=["jamo", "precomposed"],
                                       names={"jamo/16/1": "HWPG16J.SVF", "precomposed/16/1": "HWPG16.SVF"})
        st["fonts"][h16["id"]].update(selected=True, dest="jamo-extra", kinds=["jamo", "precomposed"],
                                      names={"jamo/16/1": "HAN316J.SVF", "precomposed/16/1": "HAN316.SVF"})
        status, body = self.api("PUT", "/api/jobs/%s/settings" % jid, st)
        self.assertEqual(status, 200, body)
        for f in (face, h16):
            r = self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, f["id"]))
            self.assertEqual(r[0], 200, r[2][:200])
        done = self.run_to_done(jid)
        self.assertEqual(done["state"], "done", done.get("error") or [s.get("error") for s in done["steps"]])
        with open(os.path.join(self.srv.store.path(jid), "log.md"), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("hwp1: 11172 syllables identical to the HWP 1.x rule", log)
        self.assertIn("identical to johab844.py", log)
        out = {os.path.basename(p): p for p in done["result"]["files"] if p.endswith(".SVF")}
        self.assertEqual(sorted(out), ["HAN316.SVF", "HAN316J.SVF", "HWPG16.SVF", "HWPG16J.SVF"])
        read = lambda n: jamoset.parse_svfn(open(os.path.join(self.out, out[n]), "rb").read())
        jam, pre = read("HWPG16J.SVF"), read("HWPG16.SVF")
        h = hwpfont.Hwp1Hangul(hwpfont.read(FILES["h1/HANGUL.SFT"]()), 1)
        for ch in "가한힝":
            self.assertEqual(fx.svf_rows(jam, ord(ch)), h.syllable(ord(ch)))
            self.assertEqual(pre.glyphs[ord(ch)], b"".join(r.to_bytes(2, "big") for r in h.syllable(ord(ch))))
        self.assertIn(0x41, jam.glyphs)                    # the ASCII.SFT companion reached both routes
        self.assertIn(0x41, pre.glyphs)
        self.assertEqual(read("HAN316.SVF").glyphs[0xAC00], fx.encode(fx.pattern(0, 16, 16), 16, 16, False))
        self.assertTrue(read("HAN316J.SVF").flags & jamoset.FLAG_JAMO)

    def test_ks_dump_fit_and_preview_without_a_companion(self):
        """A lone KS X 1001 dump: its source preview keeps 가 (the BDF's blank first glyph), and the experimental
        `hwp bdf + from-svf fit` runs end to end and is scored against the precomposed face it made."""
        d = os.path.join(self.tmp, "ks")
        os.makedirs(d)
        with open(os.path.join(d, "GHAN24.PFT"), "wb") as fh:
            fh.write(ks_raw())
        jid = self.local_job([d])
        job = self.job(jid)
        font = job["fonts"][0]
        self.assertEqual(font["source_kind"], "ks-raw")
        r = self.raw("GET", "/api/jobs/%s/source/%s.svf" % (jid, font["id"]))
        self.assertEqual(r[0], 200)
        self.assertIn(0xAC00, jamoset.parse_svfn(r[2]).glyphs)
        st = job["settings"]
        st["fonts"][font["id"]].update(selected=True, dest="jamo-extra", kinds=["jamo", "precomposed"], experimental=True,
                                       jamo_route="hwp bdf + from-svf fit", layout="844",
                                       names={"jamo/24/1": "GHAN24J.SVF", "precomposed/24/1": "GHAN24.SVF"})
        status, body = self.api("PUT", "/api/jobs/%s/settings" % jid, st)
        self.assertEqual(status, 200, body)
        done = self.run_to_done(jid)
        self.assertEqual(done["state"], "done", done.get("error") or [s.get("error") for s in done["steps"]])
        jam = next(s for s in done["steps"] if s["kind"] == "jamo")
        self.assertEqual(jam["quality"]["compared"], 2350)        # scored against the step's own precomposed face
        self.assertLess(0, jam["quality"]["all"])
        out = {os.path.basename(p): p for p in done["result"]["files"] if p.endswith(".SVF")}
        pre = jamoset.parse_svfn(open(os.path.join(self.out, out["GHAN24.SVF"]), "rb").read())
        self.assertEqual(sum(1 for cp in pre.glyphs if 0xAC00 <= cp <= 0xD7A3), 2350)


if __name__ == "__main__":
    unittest.main()
