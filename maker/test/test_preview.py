#!/usr/bin/env python3
"""preview.py tests: the source and result sample PNGs.

  python3 -m unittest discover -s maker/test -p 'test_*.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import contextlib
import gzip
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest import mock

from PIL import Image, ImageDraw, ImageFont

import detect
import fixtures
import preview
import svfline

SVF = os.path.join(REPO_DIR, "svf")
TOOLS = os.path.join(fixtures.REPO_DIR, "tools")

ROOT = None
GZ_DIR = None
F = {}
GZ = {}
FONT_DOS = None
FONT_TTF = None
FONT_ISO = None
FONT_KSC = None
FONT_JOHAB = None
FONT_SVF_PRE = None
FONT_JAMO = None
FONT_HBF = None
FONT_FNT = None


def scan_entry(rel):
    """The detect.scan entry of the fixture file at @p rel (a path relative to the fixture root)."""
    for entry in detect.scan(ROOT):
        if entry["path"] == rel:
            return entry
    raise AssertionError("no scan entry for %s" % rel)


def read(path):
    with open(path, "rb") as f:
        return f.read()


def gzip_file(src, dst):
    """@p src gzipped to @p dst (the upload form of a non-PCF source, `"gzip": true`)."""
    with open(src, "rb") as fi, gzip.open(dst, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    return dst


@contextlib.contextmanager
def no_canvas():
    """A patched `Image.new` that records its calls and allocates a 1x1 image instead of the size asked for.

    `source_png` must decide that a hostile canvas is too big before `Image.new`, so this both proves the call never
    happens and keeps the red run from allocating hundreds of megabytes.
    """
    real = Image.new
    with mock.patch.object(preview.Image, "new", side_effect=lambda *a, **k: real("L", (1, 1))) as new:
        yield new


def _rect(pen, x0, y0, x1, y1):
    pen.moveTo((x0, y0))
    pen.lineTo((x1, y0))
    pen.lineTo((x1, y1))
    pen.lineTo((x0, y1))
    pen.closePath()


def _ttf(path, em, ascent, descent, glyphs, cmap, advance):
    """A minimal TTF: {name: (x0, y0, x1, y1)} boxes, @p cmap {code point: name}, one @p advance for every glyph."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    def box(coords):
        pen = TTGlyphPen(None)
        _rect(pen, *coords)
        return pen.glyph()

    order = [".notdef"] + [n for n in glyphs if n != ".notdef"]
    fb = FontBuilder(em, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf({n: box(glyphs[n]) for n in order})
    fb.setupHorizontalMetrics({n: (advance, 0) for n in order})
    fb.setupHorizontalHeader(ascent=ascent, descent=descent)
    fb.setupNameTable({"familyName": "Fixture", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.setupHead(created=fixtures.HEAD_TIME, modified=fixtures.HEAD_TIME)   # deterministic bytes
    fb.font.recalcTimestamp = False
    fb.save(path)
    return path


def latin_only_ttf(path):
    """A TTF that draws A-Z xyz 0123 - every sample character but 가 (R2's "a TTF without the sample")."""
    chars = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + list("xyz") + list("0123")
    glyphs = {".notdef": (0, 0, 1000, 1000)}
    glyphs.update({ch: (100, 100, 800, 800) for ch in chars})
    return _ttf(path, 1000, 800, -200, glyphs, {ord(ch): ch for ch in chars}, 1000)


def hostile_ttf(path):
    """The nanum fixture with `unitsPerEm` 16: at a legal size the sample line asks for a canvas of hundreds of Mpx."""
    from fontTools.ttLib import TTFont

    font = TTFont(F["ttf"])
    try:
        font["head"].unitsPerEm = 16
        font.save(path)
    finally:
        font.close()
    return path


def negative_bearing_ttf(path):
    """A TTF whose ink runs left of the pen and above the line top: getbbox's top is negative at 16 px."""
    return _ttf(path, 1000, 800, -200,
                {".notdef": (-400, -100, 900, 1600), "ga": (100, 100, 900, 800)},
                {0xAC00: "ga"}, 1000)


def hostile_notdef_ttf(path):
    """A TTF whose `unitsPerEm` is 16: every sample character is a small box, but the `.notdef` is 2225 units.

    The sample line therefore passes the canvas cap, while glyph 0's mask at 96 px asks for 13350x13350 px - just under
    Pillow's `DecompressionBombError` threshold, so nothing else stops it (m2).
    """
    from fontTools.ttLib import TTFont

    chars = set(detect.SAMPLE_TEXT) | set(preview.SAMPLE_CHAR)
    built = _ttf(path, 1000, 16, -4, {".notdef": (0, 0, 2225, 2225), "ga": (0, 0, 16, 16)},
                 {ord(ch): "ga" for ch in chars}, 16)
    font = TTFont(built)
    try:
        font["head"].unitsPerEm = 16
        font.save(built)
    finally:
        font.close()
    return built


def rss_kb():
    """This process's resident set in KiB, so a test can tell that a huge allocation never happened."""
    with open("/proc/self/statm") as f:
        pages = int(f.read().split()[1])
    return pages * (os.sysconf("SC_PAGE_SIZE") // 1024)


class RunBoundedTest(unittest.TestCase):
    def test_a_timeout_kills_the_whole_group(self):
        import subprocess as sp
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            pidfile = os.path.join(d, "pid")
            script = ("import subprocess, sys, time\n"
                      "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                      "open(%r, 'w').write(str(p.pid))\n"
                      "time.sleep(60)\n" % pidfile)
            with self.assertRaises(sp.TimeoutExpired):
                preview.run_bounded([sys.executable, "-c", script], d, 1)
            with open(pidfile) as f:
                pid = int(f.read())
            for _ in range(50):
                if not os.path.exists("/proc/%d" % pid) or open("/proc/%d/stat" % pid).read().split(") ")[1][0] == "Z":
                    break
                import time
                time.sleep(0.1)
            else:
                self.fail("the grandchild survived the timeout")

    def test_it_returns_the_code_and_the_output(self):
        r = preview.run_bounded([sys.executable, "-c", "import sys; print('hi'); sys.exit(3)"], ".", 10)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, b"hi"))


class PreviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global ROOT, GZ_DIR, F, GZ, FONT_DOS, FONT_TTF, FONT_ISO, FONT_KSC, FONT_JOHAB, FONT_SVF_PRE, FONT_JAMO, FONT_HBF, FONT_FNT
        cls.tmp = tempfile.mkdtemp(prefix="svf-maker-preview-")
        ROOT = cls.tmp
        F = fixtures.write_fixtures(ROOT)
        FONT_DOS = scan_entry("dos/HAN.FNT")
        FONT_TTF = scan_entry("nanum/NanumGothic-Bold.ttf")
        FONT_ISO = scan_entry("bdf/iso.bdf")
        FONT_KSC = scan_entry("bdf/ksc.bdf")
        FONT_JOHAB = scan_entry("bdf/johab.bdf")
        FONT_SVF_PRE = scan_entry("svf/NEODG16.SVF")
        FONT_JAMO = scan_entry("svf/JAMO6J.SVF")
        FONT_HBF = scan_entry("hbf/ascii.hbf")
        FONT_FNT = scan_entry("fnt/win.fnt")
        GZ_DIR = tempfile.mkdtemp(prefix="gz-", dir=cls.tmp)
        for name, src in (("iso.bdf.gz", F["bdf_iso"]), ("n.ttf.gz", F["ttf"]),
                          ("NEO.SVF.gz", F["svf_pre"]), ("HAN.FNT.gz", F["dos_raw"])):
            gzip_file(src, os.path.join(GZ_DIR, name))
        GZ = {e["path"]: e for e in detect.scan(GZ_DIR)}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="out-", dir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_svf_png_geometry_and_ink(self):
        out = os.path.join(self.d, "p.png")
        w, h = preview.svf_png([os.path.join(SVF, "dos", "NEODG16.SVF")], out)
        img = Image.open(out); self.assertEqual(img.size, (w, h)); self.assertEqual(img.mode, "L")
        self.assertGreater(max(img.getdata()), 0)
        width, asc, desc = svfline.measure([os.path.join(SVF, "dos", "NEODG16.SVF")], detect.SAMPLE_TEXT.encode())
        self.assertEqual((w, h), (width + 2, asc + desc + 2))

    def test_chain_adds_latin_for_jamo_only_face(self):
        jam = os.path.join(SVF, "dos", "NEODG16G.SVF")                      # carries its own ASCII: no fallback
        self.assertEqual(preview.chain_for(jam, None, SVF), [jam])
        self.assertEqual(preview.chain_for(os.path.join(SVF, "dos", "NEODG16.SVF"), None, SVF), [os.path.join(SVF, "dos", "NEODG16.SVF")])
        bare = os.path.join(self.d, "BARE.SVF")                             # a DOS raw bake without --eng has no U+0041
        self.assertTrue(preview.bake_source_face(FONT_DOS, F["dos_raw"], "844", None, bare, os.path.join(fixtures.REPO_DIR, "tools")))
        self.assertFalse(svfline.Face.load(bare).has(0x41))
        self.assertEqual(preview.chain_for(bare, None, SVF), [bare, os.path.join(SVF, "dos", "NEODG16.SVF")])
        self.assertEqual(preview.chain_for(bare, "/x/LATIN.SVF", SVF), [bare, "/x/LATIN.SVF"])
        self.assertTrue(preview.result_png(bare, None, SVF, os.path.join(self.d, "r.png")))

    def test_source_png_ttf_and_failure(self):
        self.assertTrue(preview.source_png(FONT_TTF, F["ttf"], 16, os.path.join(self.d, "s.png")))
        self.assertFalse(preview.source_png(FONT_TTF, F["list"], 16, os.path.join(self.d, "no.png")))
        self.assertFalse(os.path.exists(os.path.join(self.d, "no.png")))

    def test_bake_dos_source(self):
        out = os.path.join(self.d, "HAN.SVF")
        self.assertTrue(preview.bake_source_face(FONT_DOS, F["dos_raw"], "844", F["dos_eng"], out, os.path.join(fixtures.REPO_DIR, "tools")))
        self.assertTrue(preview.result_png(out, None, SVF, os.path.join(self.d, "d.png")))

    # ---- R1: a `.gz` source is decompressed first ------------------------------------------------------------

    def test_source_png_gz_renders_like_the_plain_file(self):
        for gz_name, plain, entry in (("iso.bdf.gz", F["bdf_iso"], FONT_ISO), ("n.ttf.gz", F["ttf"], FONT_TTF)):
            self.assertTrue(GZ[gz_name].get("gzip"), gz_name)
            gz = os.path.join(GZ_DIR, gz_name)
            out_plain, out_gz = os.path.join(self.d, gz_name + ".plain.png"), os.path.join(self.d, gz_name + ".gz.png")
            self.assertTrue(preview.source_png(entry, plain, 16, out_plain), gz_name)
            self.assertTrue(preview.source_png(entry, gz, 16, out_gz), gz_name)
            self.assertEqual(read(out_plain), read(out_gz), gz_name)
            self.assertTrue(os.path.exists(os.path.join(self.d, gz_name[:-3])), gz_name)   # decompressed beside the PNG

    def test_bake_gz_sources_like_the_plain_files(self):
        self.assertTrue(GZ["NEO.SVF.gz"].get("gzip") and GZ["HAN.FNT.gz"].get("gzip"))
        out = os.path.join(self.d, "SRC.SVF")                               # an SVF source: the copy is decompressed
        self.assertTrue(preview.bake_source_face(GZ["NEO.SVF.gz"], os.path.join(GZ_DIR, "NEO.SVF.gz"), None, None, out, TOOLS))
        self.assertEqual(read(out), read(F["svf_pre"]))
        plain, baked = os.path.join(self.d, "PLAIN.SVF"), os.path.join(self.d, "GZ.SVF")
        self.assertTrue(preview.bake_source_face(FONT_DOS, F["dos_raw"], "844", F["dos_eng"], plain, TOOLS))
        self.assertTrue(preview.bake_source_face(GZ["HAN.FNT.gz"], os.path.join(GZ_DIR, "HAN.FNT.gz"), "844", F["dos_eng"], baked, TOOLS))
        self.assertEqual(read(plain), read(baked))

    def test_gzip_bomb_is_refused(self):
        bomb = os.path.join(self.d, "bomb.bdf.gz")
        chunk = b"\0" * (1 << 20)
        with gzip.open(bomb, "wb", compresslevel=1) as f:
            for _ in range((detect.MAX_DECOMPRESSED >> 20) + 1):
                f.write(chunk)
        self.assertRaises(detect.TooLarge, preview.materialize, bomb, self.d)          # over the cap: nothing written
        self.assertFalse(os.path.exists(os.path.join(self.d, "bomb.bdf")))
        self.assertFalse(preview.source_png(FONT_ISO, bomb, 16, os.path.join(self.d, "bomb.png")))
        self.assertFalse(os.path.exists(os.path.join(self.d, "bomb.png")))
        self.assertFalse(preview.bake_source_face(FONT_DOS, bomb, "844", None, os.path.join(self.d, "bomb.SVF"), TOOLS))
        self.assertFalse(os.path.exists(os.path.join(self.d, "bomb.SVF")))
        self.assertEqual([n for n in os.listdir(self.d) if n.endswith(".tmp")], [])

    # ---- R2: a preview only when the font really draws the sample --------------------------------------------

    def test_source_png_skips_faces_that_do_not_map_the_sample(self):
        latin = latin_only_ttf(os.path.join(self.d, "Latin.ttf"))
        cases = (("ksc.bdf", FONT_KSC, F["bdf_ksc"], 24), ("johab.bdf", FONT_JOHAB, F["bdf_johab"], 16),
                 ("Latin.ttf", {"face_index": 0}, latin, 16),
                 ("ascii.hbf", FONT_HBF, F["hbf"], 16), ("win.fnt", FONT_FNT, F["fnt"], 16))
        for name, entry, path, size in cases:
            out = os.path.join(self.d, name + ".png")
            if name == "ksc.bdf":                                           # no preview means no stale preview either
                with open(out, "wb") as f:
                    f.write(b"stale")
            self.assertFalse(preview.source_png(entry, path, size, out), name)
            self.assertFalse(os.path.exists(out), name)

    # ---- K1: a failed bake must not leave the previous face in place ----------------------------------------

    def test_bake_removes_a_stale_face_and_checks_the_exit_status(self):
        out = os.path.join(self.d, "STALE.SVF")
        self.assertTrue(preview.bake_source_face(FONT_DOS, F["dos_raw"], "844", F["dos_eng"], out, TOOLS))
        good = read(out)
        self.assertFalse(preview.bake_source_face(FONT_DOS, F["dos_raw"], "bogus", F["dos_eng"], out, TOOLS))
        self.assertFalse(os.path.exists(out))
        self.assertTrue(preview.bake_source_face(FONT_DOS, F["dos_raw"], "844", F["dos_eng"], out, TOOLS))
        self.assertEqual(read(out), good)
        self.assertFalse(preview.bake_source_face(FONT_DOS, "/nonexistent/HAN.FNT", "844", F["dos_eng"], out, TOOLS))
        self.assertFalse(os.path.exists(out))

    # ---- K2: a hostile canvas is refused before it is allocated ---------------------------------------------

    def test_source_png_caps_the_canvas(self):
        hostile = hostile_ttf(os.path.join(self.d, "HOSTILE.ttf"))
        self.assertGreater(ImageFont.truetype(hostile, 96).getbbox(detect.SAMPLE_TEXT)[2], preview.MAX_CANVAS)
        out = os.path.join(self.d, "hostile.png")
        with no_canvas() as new:
            self.assertFalse(preview.source_png({"face_index": 0}, hostile, 96, out))
        new.assert_not_called()
        self.assertFalse(os.path.exists(out))
        big = os.path.join(self.d, "big.png")
        with no_canvas() as new:                                            # a plain size 3000 is over the cap too
            self.assertFalse(preview.source_png(FONT_TTF, F["ttf"], 3000, big))
        new.assert_not_called()
        self.assertFalse(os.path.exists(big))

    # ---- K3: a rebaked face is re-rendered, not read from `Face.load`'s cache -------------------------------

    def test_result_png_sees_a_rebaked_face(self):
        face = os.path.join(self.d, "FACE.SVF")
        one, two = os.path.join(self.d, "one.png"), os.path.join(self.d, "two.png")
        self.assertTrue(preview.bake_source_face(FONT_SVF_PRE, F["svf_pre"], None, None, face, TOOLS))
        self.assertTrue(preview.result_png(face, None, SVF, one))
        self.assertTrue(preview.bake_source_face(FONT_JAMO, F["svf_jamo"], None, None, face, TOOLS))
        self.assertTrue(preview.result_png(face, None, SVF, two))
        self.assertNotEqual(read(one), read(two))

    def test_bake_source_face_honours_the_jset_flags(self):
        import jamoset
        import svf2to3
        for extra, want in (([], 1), (["--jset-version", "2"], 2)):
            face = os.path.join(self.d, "JV%d.SVF" % want)
            src = os.path.join(self.d, "big-%d.SVF" % want)
            with open(src, "wb") as fh:
                fh.write(fixtures.jset1_big_face())
            font = dict(FONT_JAMO, svf=dict(FONT_JAMO["svf"], jset_version=1))
            self.assertTrue(preview.bake_source_face(font, src, None, None, face, TOOLS, extra))
            with open(face, "rb") as fh:
                self.assertEqual(svf2to3.jset_version(jamoset.parse_svfn(fh.read()).jset), want)

    # ---- K4: `bake_source_face` is False, never an exception -------------------------------------------------

    def test_bake_source_face_returns_false_instead_of_raising(self):
        out = os.path.join(self.d, "OUT.SVF")
        self.assertFalse(preview.bake_source_face(FONT_SVF_PRE, "/nonexistent/NEO.SVF", None, None, out, TOOLS))
        self.assertFalse(os.path.exists(out))
        same = os.path.join(self.d, "SAME.SVF")                             # a same-file copy must not touch the source
        shutil.copyfile(F["svf_pre"], same)
        self.assertFalse(preview.bake_source_face(FONT_SVF_PRE, same, None, None, same, TOOLS))
        self.assertEqual(read(same), read(F["svf_pre"]))
        locked = os.path.join(self.d, "LOCKED.SVF")                         # an unreadable source is False, not an OSError
        shutil.copyfile(F["svf_pre"], locked)
        os.chmod(locked, 0)
        try:
            self.assertFalse(preview.bake_source_face(FONT_SVF_PRE, locked, None, None, out, TOOLS))
        finally:
            os.chmod(locked, 0o644)
        self.assertFalse(os.path.exists(out))
        cwd = os.getcwd()                                                   # a relative out_svf resolves, not to cwd ""
        os.chdir(self.d)
        try:
            self.assertTrue(preview.bake_source_face(FONT_DOS, F["dos_raw"], "844", None, "REL.SVF", TOOLS))
            self.assertTrue(os.path.exists(os.path.join(self.d, "REL.SVF")))
        finally:
            os.chdir(cwd)
        with mock.patch.object(preview, "run_bounded", side_effect=subprocess.TimeoutExpired("jamoset.py", 60)):
            self.assertFalse(preview.bake_source_face(FONT_DOS, F["dos_raw"], "844", None, out, TOOLS))
        self.assertFalse(os.path.exists(out))
        jmap = dict(FONT_SVF_PRE, svf=dict(FONT_SVF_PRE["svf"], jset_version=3))     # routes refuse a JSET version for it
        self.assertFalse(preview.bake_source_face(jmap, F["svf_pre"], None, None, out, TOOLS, ["--jset-version", "2"]))
        self.assertFalse(os.path.exists(out))

    # ---- K5: negative bearings are not clipped ---------------------------------------------------------------

    def test_source_png_keeps_the_ink_above_the_line_top(self):
        path = negative_bearing_ttf(os.path.join(self.d, "NEG.ttf"))
        out = os.path.join(self.d, "neg.png")
        self.assertTrue(preview.source_png({"face_index": 0}, path, 16, out))
        face = ImageFont.truetype(path, 16)
        left, top, right, bottom = face.getbbox(detect.SAMPLE_TEXT)
        # Pillow 10's getbbox can report a negative left (a review probe saw -19 at 32 px on Pillow 10.2). This
        # fixture's text starts at 0, so only its top is observable; the code offsets by both regardless.
        self.assertLessEqual(left, 0)
        self.assertLess(top, 0)                                             # the fixture really rises above the line top
        with Image.open(out) as img:
            size, data, ink = img.size, img.tobytes(), img.getbbox()
        self.assertEqual(size, (right - min(left, 0) + 2, bottom - min(top, 0) + 2))
        ref = Image.new("L", size, 0)
        ImageDraw.Draw(ref).text((1 - min(left, 0), 1 - min(top, 0)), detect.SAMPLE_TEXT, 255, font=face)
        self.assertEqual(data, ref.tobytes())
        self.assertEqual(ink, (1, 1, right - min(left, 0) + 1, bottom - min(top, 0) + 1))

    # ---- K6 / L1: every PNG goes through its own `<out>.<rand>.tmp` then `os.replace` ----------------------

    def test_png_writes_go_through_a_temp_file(self):
        out = os.path.join(self.d, "s.png")
        self.assertTrue(preview.source_png(FONT_TTF, F["ttf"], 16, out))
        self.assertTrue(os.path.exists(out))
        self.assertEqual([n for n in os.listdir(self.d) if n.endswith(".tmp")], [])
        stale = os.path.join(self.d, "stale.png")
        with open(stale, "wb") as f:
            f.write(b"stale")
        with mock.patch.object(preview.Image.Image, "save", side_effect=OSError("disk full")) as save:
            self.assertFalse(preview.source_png(FONT_TTF, F["ttf"], 16, stale))
            target = save.call_args[0][0]
        self.assertIsInstance(target, str)
        self.assertNotEqual(target, stale)                                  # never the output itself
        self.assertEqual(os.path.realpath(os.path.dirname(target)), os.path.realpath(self.d))
        self.assertRegex(os.path.basename(target), r"^stale\.png\..+\.tmp$")   # its own temp name, not `<out>.tmp`
        self.assertFalse(os.path.exists(stale))
        self.assertEqual([n for n in os.listdir(self.d) if n.endswith(".tmp")], [])
        face = os.path.join(SVF, "dos", "NEODG16.SVF")
        with open(stale, "wb") as f:
            f.write(b"stale")
        with mock.patch.object(preview.Image.Image, "save", side_effect=OSError("disk full")):
            self.assertRaises(OSError, preview.svf_png, [face], stale)
        self.assertFalse(os.path.exists(stale))
        self.assertEqual([n for n in os.listdir(self.d) if n.endswith(".tmp")], [])
        with open(stale, "wb") as f:
            f.write(b"stale")
        with mock.patch.object(preview.Image.Image, "save", side_effect=OSError("disk full")):
            self.assertFalse(preview.result_png(face, None, SVF, stale))
        self.assertFalse(os.path.exists(stale))
        self.assertEqual([n for n in os.listdir(self.d) if n.endswith(".tmp")], [])

    # ---- L1: two concurrent writes of one PNG both succeed --------------------------------------------------

    def test_two_threads_writing_one_png_both_succeed(self):
        out = os.path.join(self.d, "shared.png")
        for _ in range(20):
            barrier = threading.Barrier(2)
            results, errors = [], []

            def write():
                try:
                    barrier.wait(30)
                    results.append(preview.source_png(FONT_TTF, F["ttf"], 16, out))
                except Exception as exc:                                    # a raised error is a failed write too
                    errors.append(exc)

            threads = [threading.Thread(target=write) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(60)
            self.assertEqual(errors, [])
            self.assertEqual(sorted(results), [True, True])                 # neither write may lose to the other
            self.assertEqual([n for n in os.listdir(self.d) if n.endswith(".tmp")], [])
            with Image.open(out) as img:                                    # a valid PNG is left on disk
                img.load()
                self.assertEqual(img.format, "PNG")
                self.assertEqual(img.mode, "L")
                self.assertGreater(max(img.getdata()), 0)

    # ---- L2: a render is never confused by a face rebaked under it ------------------------------------------

    def test_render_sees_a_rebaked_face_under_concurrency(self):
        neo, bhs = os.path.join(SVF, "dos", "NEODG16.SVF"), os.path.join(SVF, "dos", "BHSAN28.SVF")
        face = os.path.join(self.d, "FACE.SVF")
        self.assertTrue(preview.bake_source_face(FONT_SVF_PRE, neo, None, None, face, TOOLS))
        held = {}
        entered, release = threading.Event(), threading.Event()
        real_measure, state = preview.svfline.measure, {"first": True}

        def measure(chain, text, *args, **kwargs):
            got = real_measure(chain, text, *args, **kwargs)
            if state["first"]:                                              # thread A: hold the loaded face
                state["first"] = False
                entered.set()
                release.wait(2)
            return got

        def render_a():
            held["a"] = preview.svf_png([face], os.path.join(self.d, "a.png"))

        with mock.patch.object(preview.svfline, "measure", side_effect=measure):
            threaded = threading.Thread(target=render_a)
            threaded.start()
            try:
                self.assertTrue(entered.wait(30))
                self.assertTrue(preview.bake_source_face(FONT_SVF_PRE, bhs, None, None, face, TOOLS))
                held["b"] = preview.svf_png([face], os.path.join(self.d, "b.png"))
            finally:
                release.set()
                threaded.join(30)
        self.assertEqual(held["a"], (306, 18))                              # A drew the NEODG16 face it measured
        self.assertEqual(held["b"], (437, 30))                              # B drew the rebaked BHSAN28 face, not A's
        self.assertEqual(preview.svf_png([face], os.path.join(self.d, "fresh.png")), held["b"])

    # ---- L3: a hostile `.notdef` mask is refused before it is allocated -------------------------------------

    def test_source_png_caps_the_notdef_canvas(self):
        path = hostile_notdef_ttf(os.path.join(self.d, "NOTDEF.ttf"))
        face = ImageFont.truetype(path, 96)
        self.assertLessEqual(face.getbbox(detect.SAMPLE_TEXT)[2], preview.MAX_CANVAS)      # the line itself fits
        self.assertGreater(face.getbbox(detect.NOTDEF_CHAR)[2], preview.MAX_CANVAS)        # glyph 0 does not
        out = os.path.join(self.d, "notdef.png")
        before = rss_kb()
        with no_canvas() as new:
            self.assertFalse(preview.source_png({"face_index": 0}, path, 96, out))
        new.assert_not_called()
        self.assertFalse(os.path.exists(out))
        self.assertLess(rss_kb() - before, 8 * 1024)                        # the 178 Mpx mask is never allocated

    # ---- L4: a broken `.gz` source is False, never an exception ---------------------------------------------

    def test_bake_source_face_returns_false_on_a_broken_gz(self):
        good = os.path.join(self.d, "HAN.FNT.gz")
        gzip_file(F["dos_raw"], good)
        data = read(good)
        cases = (("truncated.gz", data[:len(data) // 2]),
                 ("corrupt.gz", b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff" + b"\x07" + b"\0" * 8))
        for name, blob in cases:
            path = os.path.join(self.d, name)
            with open(path, "wb") as f:
                f.write(blob)
            out = os.path.join(self.d, name + ".SVF")
            with open(out, "wb") as f:                                      # a stale bake must not survive
                f.write(b"stale")
            self.assertFalse(preview.bake_source_face(FONT_DOS, path, "844", F["dos_eng"], out, TOOLS), name)
            self.assertFalse(os.path.exists(out), name)
            self.assertEqual([n for n in os.listdir(self.d) if n.endswith(".tmp")], [], name)

    # ---- L5: an unsupported source kind is False -----------------------------------------------------------

    def test_bake_source_face_refuses_an_unsupported_kind(self):
        out = os.path.join(self.d, "KIND.SVF")
        for kind in ("outline", "bdf-iso10646", "hbf", None):
            with open(out, "wb") as f:
                f.write(b"stale")
            self.assertFalse(preview.bake_source_face({"source_kind": kind}, F["ttf"], None, None, out, TOOLS), kind)
            self.assertFalse(os.path.exists(out), kind)
