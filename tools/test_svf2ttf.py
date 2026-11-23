#!/usr/bin/env python3
"""Tests of tools/svf2ttf.py on the repository's own faces (svf/) and faces derived from them in a temp dir.

  python3 -m unittest tools.test_svf2ttf
"""
import glob
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import svf2ttf  # noqa: E402
import svfline  # noqa: E402
import jamoset  # noqa: E402

from fontTools.ttLib import TTFont  # noqa: E402
from fontTools.ttLib.tables.E_B_D_T_ import ComponentBitmapGlyph  # noqa: E402
from fontTools.ttLib.tables._g_l_y_f import (ARGS_ARE_XY_VALUES, MORE_COMPONENTS, OVERLAP_COMPOUND,  # noqa: E402
                                              ROUND_XY_TO_GRID)
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

DOS = os.path.join(ROOT, "svf", "dos")
NEODG16 = os.path.join(DOS, "NEODG16.SVF")        # precomposed 1 bpp 16x16
NEODG16A = os.path.join(DOS, "NEODG16A.SVF")      # jamo set 1 bpp 16x16
NEODG16J = os.path.join(DOS, "NEODG16J.SVF")      # precomposed 1 bpp 18x18, 779 glyphs
NGOTB15C = os.path.join(DOS, "NGOTB15C.SVF")      # precomposed 2 bpp 16x16, 781 glyphs
GOTHA16A = os.path.join(ROOT, "svf", "jamo-extra", "GOTHA16A.SVF")   # jamo set 2 bpp 16x16, 24/16/16 sets


def run(*argv):
    r = subprocess.run([sys.executable] + [str(a) for a in argv], capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError("%s exit %d\n%s%s" % (argv[0], r.returncode, r.stdout, r.stderr))
    return r.stdout


def strike_pixels(font, name, depth):
    """{(x, y_down): level} of glyph @p name in the font's first EBDT strike, relative to pen and baseline."""
    g = font["EBDT"].strikeData[0][name]
    m = g.metrics
    pitch = (m.width * depth + 7) // 8
    out = {}
    data = g.imageData
    for r in range(m.height):
        row = data[r * pitch:(r + 1) * pitch]
        for c in range(m.width):
            bit = c * depth
            v = row[bit >> 3] >> (8 - depth - (bit & 7)) & ((1 << depth) - 1)
            if v:
                out[(m.BearingX + c, r - m.BearingY)] = v
    return out, m.Advance


def synth(path, cell_w, cell_h, ascent, glyphs, bpp=1, flags=jamoset.FLAG_MARKS_AT_ORIGIN, dy=None):
    """Write a precomposed SVFN v3 face: @p glyphs {cp: (advance, bearing_x, rows)}, rows a list of cell_h strings of
    cell_w characters ('.' blank, '#' ink for 1 bpp, '0'..'3' levels for 2 bpp)."""
    cells, cmap, metrics = [], [], []
    for i, (cp, (adv, bx, rows)) in enumerate(sorted(glyphs.items())):
        pitch = (cell_w * bpp + 7) // 8
        data = bytearray()
        ink = [x for r in rows for x, ch in enumerate(r) if ch not in ".0"]
        for r in rows:
            row = bytearray(pitch)
            for x, ch in enumerate(r):
                v = 1 if ch == "#" else 0 if ch == "." else int(ch)
                if v:
                    row[(x * bpp) >> 3] |= v << (8 - bpp - ((x * bpp) & 7))
            data += row
        cells.append(bytes(data))
        cmap.append((cp, i))
        metrics.append((adv, bx, (max(ink) - min(ink) + 1) if ink else 0, (dy or {}).get(cp, 0)))
    dys = [m[3] for m in metrics]
    with open(path, "wb") as fh:
        fh.write(jamoset.pack_svfn(cell_w, cell_h, ascent, bpp, flags, cells, cmap, metrics, None,
                                   (min(dys + [0]), max(dys + [0]))))
    return path


def box_rows(w, h, x0, y0, x1, y1, ch="#"):
    return ["".join(ch if x0 <= x < x1 and y0 <= y < y1 else "." for x in range(w)) for y in range(h)]


class GlyphSet(unittest.TestCase):
    def test_jamo_set_composes_every_syllable(self):
        face = svfline.Face.load(NEODG16A)
        cps = svf2ttf.face_cps(face)
        syll = [cp for cp in cps if 0xAC00 <= cp <= 0xD7A3]
        self.assertEqual(len(syll), 11172)
        self.assertFalse([cp for cp in cps if cp >= 0xF0000], "jamo pieces are not exported")
        others = [cp for cp in face.glyphs if cp < 0xF0000 and not 0xAC00 <= cp <= 0xD7A3]
        self.assertTrue(set(others) <= set(cps))

    def test_precomposed_glyph_set(self):
        face = svfline.Face.load(NEODG16)
        self.assertEqual(sorted(svf2ttf.face_cps(face)), sorted(face.glyphs))

    def test_glyph_pixels_follow_svfline(self):
        face = svfline.Face.load(NEODG16)
        adv, px = svf2ttf.glyph_pixels(face, 0x41)
        buf = svfline.layout([NEODG16], "A", 0, 12, 16, 16)
        want = {(i % 16, i // 16 - 12): 1 for i, v in enumerate(buf) if v}
        self.assertEqual(px, want)
        self.assertEqual(adv, face.metrics(0x41)[0])


class Ttf(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = cls.tmp.name
        cls.ttf16 = os.path.join(cls.d, "neodg16j.ttf")
        run(os.path.join(HERE, "svf2ttf.py"), "ttf", NEODG16J, cls.ttf16, "--family", "Test Pixel", "--version", "1.5")
        cls.ttf2 = os.path.join(cls.d, "ngotb15c.ttf")
        run(os.path.join(HERE, "svf2ttf.py"), "ttf", NGOTB15C, cls.ttf2, "--ppem", "15")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_tables_and_metrics(self):
        f = TTFont(self.ttf16)
        for tag in ("head", "hhea", "maxp", "OS/2", "name", "cmap", "post", "glyf", "loca", "hmtx", "EBLC", "EBDT"):
            self.assertIn(tag, f, tag)
        face = svfline.Face.load(NEODG16J)
        self.assertEqual(f["head"].unitsPerEm, 18 * 64)
        self.assertEqual(f["hhea"].ascent, face.ascent * 64)
        self.assertEqual(f["hhea"].descent, -(face.cell_h - face.ascent) * 64)
        cmap = f.getBestCmap()
        self.assertEqual(sorted(cmap), sorted(face.glyphs))
        for cp in (0x41, 0x67, 0xAC00, 0x20):
            self.assertEqual(f["hmtx"][cmap[cp]][0], face.metrics(cp)[0] * 64, hex(cp))
        names = f["name"]
        self.assertEqual(names.getDebugName(1), "Test Pixel")
        self.assertEqual(names.getDebugName(2), "Regular")
        self.assertIn("1.5", names.getDebugName(5))
        self.assertIn("NEODG16J.SVF", names.getDebugName(10))
        self.assertIn("18 px strike", names.getDebugName(10))
        self.assertEqual(svf2ttf.default_family("/x/neodg16j.svf"), "NEODG16J SVF")
        self.assertIn("Neo Dunggeunmo", names.getDebugName(13))       # the licence note beside the face
        self.assertIn("Copyright (c) 2017-2021", names.getDebugName(0))
        strike = f["EBLC"].strikes[0].bitmapSizeTable
        self.assertEqual((strike.ppemX, strike.ppemY, strike.bitDepth), (18, 18, 1))

    def test_strike_is_the_face(self):
        f = TTFont(self.ttf16)
        face = svfline.Face.load(NEODG16J)
        cmap = f.getBestCmap()
        bad = 0
        for cp in svf2ttf.face_cps(face):
            adv, want = svf2ttf.glyph_pixels(face, cp)
            got, gadv = strike_pixels(f, cmap[cp], 1)
            bad += got != want or gadv != adv
        self.assertEqual(bad, 0)

    def test_two_bit_strike(self):
        f = TTFont(self.ttf2)
        face = svfline.Face.load(NGOTB15C)
        self.assertEqual(f["EBLC"].strikes[0].bitmapSizeTable.bitDepth, 2)
        self.assertEqual(f["EBLC"].strikes[0].bitmapSizeTable.ppemY, 15)
        self.assertEqual(f["head"].unitsPerEm, 15 * 64)
        cmap = f.getBestCmap()
        bad = 0
        for cp in svf2ttf.face_cps(face):
            adv, want = svf2ttf.glyph_pixels(face, cp)
            got, _ = strike_pixels(f, cmap[cp], 2)
            bad += got != want
        self.assertEqual(bad, 0)

    def test_freetype_draws_the_face(self):
        """Pillow (FreeType) at the strike size draws the svfline line; at twice the size the outlines, 2x2 blocks."""
        text = "가각간한글 ABC 123"
        face = svfline.Face.load(NEODG16J)
        w, h = 200, 18
        want = svfline.layout([NEODG16J], text, 0, face.ascent, w, h)
        for size, k in ((18, 1), (36, 2)):
            font = ImageFont.truetype(self.ttf16, size)
            img = Image.new("L", (w * k, h * k), 0)
            ImageDraw.Draw(img).text((0, face.ascent * k), text, font=font, fill=255, anchor="ls")
            got = img.point(lambda v: 255 if v >= 128 else 0).tobytes()
            exp = bytes(want[(y // k) * w + x // k] for y in range(h * k) for x in range(w * k))
            self.assertEqual(got, exp, "size %d" % size)

    def test_unhinted_at_other_sizes(self):
        """At 1.5 x ppem FreeType draws the outline's exact area coverage (the no-op prep keeps the autohinter off):
        svfline's 3/2 scale of the line, within 1 level. NEODG16: ascent 12 and even advances, so the 3/2 grid is
        whole pixels."""
        ttf = os.path.join(self.d, "neodg16.ttf")
        run(os.path.join(HERE, "svf2ttf.py"), "ttf", NEODG16, ttf)
        f = TTFont(ttf)
        self.assertEqual(f["prep"].program.getBytecode(), svf2ttf.PREP_NOOP)
        self.assertEqual(f["maxp"].maxStackElements, 1)
        text = "가각간한글 ABC 123"
        w, h = 260, 24
        want = svfline.layout([NEODG16], text, 0, 18, w, h, scale=(3, 2))
        font = ImageFont.truetype(ttf, 24)
        img = Image.new("L", (w, h), 0)
        ImageDraw.Draw(img).text((0, 18), text, font=font, fill=255, anchor="ls")
        self.assertLessEqual(max(abs(a - b) for a, b in zip(img.tobytes(), want)), 1)
        self.assertGreater(sum(1 for v in want if 0 < v < 255), 100)      # partial coverage is really compared

    def test_roundtrip_through_mkfont(self):
        for src, ttf, size, bpp in ((NEODG16J, self.ttf16, 18, 1), (NGOTB15C, self.ttf2, 15, 2)):
            back = os.path.join(self.d, "back%d.svf" % bpp)
            face = svfline.Face.load(src)
            run(os.path.join(HERE, "mkfont.py"), ttf, back, "--size", size, "--bpp", bpp, "--probe", "--width",
                face.cell_w, "--only-listed", "--unicode", run(os.path.join(HERE, "svf2ttf.py"), "cps", src).strip())
            out = run(os.path.join(HERE, "svf2ttf.py"), "compare", src, back)
            self.assertIn("mismatches 0", out, out)

    def test_outline_only_roundtrip(self):
        ttf = os.path.join(self.d, "outline.ttf")
        run(os.path.join(HERE, "svf2ttf.py"), "ttf", NEODG16J, ttf, "--no-strike")
        self.assertNotIn("EBDT", TTFont(ttf))
        back = os.path.join(self.d, "outline.svf")
        face = svfline.Face.load(NEODG16J)
        run(os.path.join(HERE, "mkfont.py"), ttf, back, "--size", 18, "--bpp", 1, "--probe", "--width", face.cell_w,
            "--only-listed", "--unicode", run(os.path.join(HERE, "svf2ttf.py"), "cps", NEODG16J).strip())
        self.assertIn("mismatches 0", run(os.path.join(HERE, "svf2ttf.py"), "compare", NEODG16J, back))


def resolved_strike_pixels(font, name, depth):
    """strike_pixels of @p name with a compound (format 8 / 9) glyph resolved as FreeType does (ttsbit.c): each
    component's rows ORed into the compound's bitmap at its offset (for 2 / 8 bpp, an x offset only at 0: FreeType
    shifts by the offset in bits)."""
    g = font["EBDT"].strikeData[0][name]
    if not isinstance(g, ComponentBitmapGlyph):
        return strike_pixels(font, name, depth)
    m = g.metrics
    out = {}
    for c in g.componentArray:
        sub = font["EBDT"].strikeData[0][c.name]
        if depth > 1:
            assert c.xOffset == 0, (name, c.name, c.xOffset)
        sm = sub.metrics
        px, _ = resolved_strike_pixels(font, c.name, depth)
        for (x, y), v in px.items():
            # the component's own bearings are ignored: it lands at the offset from the compound's top-left
            k = (m.BearingX + c.xOffset + x - sm.BearingX, -m.BearingY + c.yOffset + y + sm.BearingY)
            out[k] = out.get(k, 0) | v
    return out, m.Advance


def composite_flags(data):
    """The component flags of the raw composite glyf entry @p data, in order."""
    out, p = [], 10
    while True:
        flags = struct.unpack(">H", data[p:p + 2])[0]
        out.append(flags)
        p += 4 + (4 if flags & 0x0001 else 2)                  # glyph index, then ARG_1_AND_2_ARE_WORDS args
        p += 2 if flags & 0x0008 else 4 if flags & 0x0040 else 8 if flags & 0x0080 else 0
        if not flags & MORE_COMPONENTS:
            return out


class Composite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.d = cls.tmp.name
        cls.ttf1 = os.path.join(cls.d, "neodg16a-c.ttf")
        cls.out1 = run(os.path.join(HERE, "svf2ttf.py"), "ttf", NEODG16A, cls.ttf1, "--composite")
        cls.exp1 = os.path.join(cls.d, "neodg16a.ttf")
        run(os.path.join(HERE, "svf2ttf.py"), "ttf", NEODG16A, cls.exp1)
        cls.ttf2 = os.path.join(cls.d, "gotha16a-c.ttf")
        cls.out2 = run(os.path.join(HERE, "svf2ttf.py"), "ttf", GOTHA16A, cls.ttf2, "--composite")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_structure(self):
        f = TTFont(self.ttf1)
        face = svfline.Face.load(NEODG16A)
        cmap = f.getBestCmap()
        glyf = f["glyf"]
        for cp, n in ((0xAC00, 2), (0xAC01, 3), (0xD55C, 3)):
            g = glyf[cmap[cp]]
            self.assertTrue(g.isComposite(), hex(cp))
            self.assertEqual(len(g.components), n, hex(cp))
            self.assertEqual({(c.x, c.y) for c in g.components}, {(0, 0)})
            for c in g.components:
                self.assertFalse(glyf[c.glyphName].isComposite())
            self.assertEqual(f["hmtx"][cmap[cp]][0], face.metrics(cp)[0] * 64)
            eb = f["EBDT"].strikeData[0][cmap[cp]]
            self.assertIsInstance(eb, ComponentBitmapGlyph, hex(cp))
            self.assertEqual(len(eb.componentArray), n)
        self.assertFalse(glyf[cmap[0x41]].isComposite())
        self.assertNotIsInstance(f["EBDT"].strikeData[0][cmap[0x41]], ComponentBitmapGlyph)
        # compatibility jamo map to the piece glyph itself
        self.assertFalse(glyf[cmap[0x3131]].isComposite())
        self.assertEqual(f["maxp"].maxComponentElements, 3)
        self.assertEqual(f["maxp"].maxComponentDepth, 1)
        pieces = {c.glyphName for cp in range(0xAC00, 0xD7A4) for c in glyf[cmap[cp]].components}
        used = {n for cp in range(0xAC00, 0xD7A4) for n in svfline.jamoset.pieces_of(face.tables, cp)
                if n != svfline.jamoset.BLANK}
        self.assertLessEqual(len(pieces), len(used))
        self.assertLess(len(f.getGlyphOrder()), 11319 + len(used) + 1)
        self.assertIn("composite", self.out1)
        self.assertLess(os.path.getsize(self.ttf1), os.path.getsize(self.exp1) * 2 // 5)
        self.assertIn("prep", f)        # keeps FreeType's autohinter off (see build_ttf)

    def test_component_flags_lsb_and_index_subtables(self):
        f = TTFont(self.ttf1)
        glyf, order = f["glyf"], f.getGlyphOrder()
        cmap = f.getBestCmap()
        multi = 0
        for cp in range(0xAC00, 0xD7A4):
            name = cmap[cp]
            flags = composite_flags(glyf.glyphs[name].data)       # as stored (fontTools masks some on decompile)
            n = len(flags)
            multi += n > 1
            for i, fl in enumerate(flags):
                self.assertEqual(fl & (ARGS_ARE_XY_VALUES | ROUND_XY_TO_GRID), ARGS_ARE_XY_VALUES | ROUND_XY_TO_GRID,
                                 hex(cp))
                self.assertEqual(bool(fl & MORE_COMPONENTS), i < n - 1, hex(cp))
                self.assertEqual(bool(fl & OVERLAP_COMPOUND), i == 0 and n > 1, hex(cp))
            g = glyf[name]
            self.assertEqual(len(g.components), n)
            g.recalcBounds(glyf)
            self.assertEqual(f["hmtx"][name][1], g.xMin, hex(cp))
        self.assertGreater(multi, 11000)
        # two index subtables: image format 1 from glyph 1, then format 8 up to the last glyph, contiguous
        subs = f["EBLC"].strikes[0].indexSubTables
        self.assertEqual([(t.indexFormat, t.imageFormat) for t in subs], [(1, 1), (1, 8)])
        ids = [(order.index(t.names[0]), order.index(t.names[-1])) for t in subs]
        self.assertEqual(ids[0][0], 1)
        self.assertEqual(ids[1][0], ids[0][1] + 1)
        self.assertEqual(ids[1][1], len(order) - 1)

    def test_strike_is_the_face(self):
        for path, ttf, depth in ((NEODG16A, self.ttf1, 1), (GOTHA16A, self.ttf2, 2)):
            f = TTFont(ttf)
            face = svfline.Face.load(path)
            cmap = f.getBestCmap()
            bad = []
            for cp in svf2ttf.face_cps(face):
                adv, want = svf2ttf.glyph_pixels(face, cp)
                got, gadv = resolved_strike_pixels(f, cmap[cp], depth)
                if got != want or gadv != adv:
                    bad.append(cp)
            self.assertEqual(bad, [], path)

    def test_two_bit_fallback(self):
        """A 2 bpp syllable whose pieces overlap with levels 1 and 2 (FreeType's OR gives 3, the SVF rule max 2) keeps
        an expanded bitmap; the others are compound bitmaps; the outlines are composites for all."""
        f = TTFont(self.ttf2)
        face = svfline.Face.load(GOTHA16A)
        cmap = f.getBestCmap()
        # derived here from the pieces, independently of svf2ttf.bitmap_conflicts: a pixel two pieces share where
        # FreeType's OR of the levels differs from the face's max
        t = face.tables
        piece = {}
        want = set()
        for cp in range(0xAC00, 0xD7A4):
            acc = {}
            for n in jamoset.pieces_of(t, cp):
                if n == jamoset.BLANK:
                    continue
                if n not in piece:
                    rows = face.coverage(jamoset.PIECE_BASE + n)
                    piece[n] = {(x, y): v // 85 for y, r in enumerate(rows) for x, v in enumerate(r) if v}
                for k, v in piece[n].items():
                    if k in acc and acc[k] | v != max(acc[k], v):
                        want.add(cp)
                    acc[k] = max(acc.get(k, 0), v)
        self.assertEqual(len(want), 5081)
        self.assertEqual(want, svf2ttf.bitmap_conflicts(face))
        strike = f["EBDT"].strikeData[0]
        expanded = {cp for cp in range(0xAC00, 0xD7A4) if not isinstance(strike[cmap[cp]], ComponentBitmapGlyph)}
        self.assertEqual(expanded, want)
        self.assertTrue(all(f["glyf"][cmap[cp]].isComposite() for cp in range(0xAC00, 0xD7A4)))
        self.assertIn("%d expanded" % len(want), self.out2)

    def test_freetype_draws_the_face(self):
        """Pillow (FreeType) draws the compound strike at ppem (2 bpp: the levels) and the composite outlines at 2 x."""
        for path, ttf, ppem in ((NEODG16A, self.ttf1, 16), (GOTHA16A, self.ttf2, 16)):
            face = svfline.Face.load(path)
            text = "가각간한글 ABC 123 " + "".join(chr(cp) for cp in range(0xAC00, 0xD7A4, 397))
            w, h = 20 * len(text), face.cell_h
            want = svfline.layout([path], text, 0, face.ascent, w, h)
            for k in (1, 2):
                font = ImageFont.truetype(ttf, ppem * k)
                img = Image.new("L", (w * k, h * k), 0)
                ImageDraw.Draw(img).text((0, face.ascent * k), text, font=font, fill=255, anchor="ls")
                if k == 1:
                    self.assertEqual(img.tobytes(), bytes(want), path)
                else:
                    got = img.point(lambda v: 255 if v >= 128 else 0).tobytes()
                    exp = bytes(255 if want[(y // k) * w + x // k] >= 128 else 0
                                for y in range(h * k) for x in range(w * k))
                    self.assertEqual(got, exp, path)

    def test_roundtrip_through_mkfont(self):
        back = os.path.join(self.d, "back.svf")
        run(os.path.join(HERE, "mkfont.py"), self.ttf2, back, "--size", 16, "--bpp", 2, "--probe", "--width", 16,
            "--only-listed", "--unicode", run(os.path.join(HERE, "svf2ttf.py"), "cps", GOTHA16A).strip())
        out = run(os.path.join(HERE, "svf2ttf.py"), "compare", GOTHA16A, back)
        self.assertIn("mismatches 0", out, out)

    def test_reopen_and_recompile(self):
        f = TTFont(self.ttf2)
        out = os.path.join(self.d, "re.ttf")
        f.save(out)
        g = TTFont(out)
        self.assertEqual(len(g.getGlyphOrder()), len(f.getGlyphOrder()))
        cmap = g.getBestCmap()
        self.assertTrue(g["glyf"][cmap[0xAC00]].isComposite())
        self.assertEqual(resolved_strike_pixels(g, cmap[0xAC01], 2), resolved_strike_pixels(f, cmap[0xAC01], 2))

    def test_precomposed_face_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.ttf"), os.path.join(d, "b.ttf")
            env = dict(os.environ, SOURCE_DATE_EPOCH="1700000000")
            r = subprocess.run([sys.executable, os.path.join(HERE, "svf2ttf.py"), "ttf", NGOTB15C, a, "--composite"],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("no jamo set", r.stderr)
            subprocess.run([sys.executable, os.path.join(HERE, "svf2ttf.py"), "ttf", NGOTB15C, b], check=True,
                           capture_output=True, env=env)
            with open(a, "rb") as fa, open(b, "rb") as fb:
                self.assertEqual(fa.read(), fb.read())


def tall_jamo_face(path, cell_w=8, cell_h=140, ascent=127, place=None):
    """A jamo set (1x1 classes, one set each) whose initial pieces ink the cell's top row, medials row 60 and finals its
    bottom row, plus an 'A': a syllable with a final spans the whole cell, so a compound bitmap's offset of its final
    (cell_h - 1 rows) is past an int8 for cell_h > 128."""
    t = jamoset.Tables(1, 1, 1, 1, 1)
    t.init_piece = list(range(19))
    t.med_piece = list(range(19, 40))
    t.fin_piece = list(range(40, 67))
    pitch = (cell_w + 7) // 8

    def cell(row, x):
        b = bytearray(pitch * cell_h)
        b[row * pitch + (x >> 3)] |= 0x80 >> (x & 7)
        return bytes(b)
    packed = jamoset.pack_jset(t, 1)
    glyphs = [(0x41, cell(ascent - 1, 1), cell_w, 1, 1)]
    for n in range(67):
        row, x = (0, n % cell_w) if n < 19 else (60, (n - 19) % cell_w) if n < 40 else (cell_h - 1, (n - 40) % cell_w)
        if place:
            row, x = place(n)
        glyphs.append((jamoset.PIECE_BASE + packed.piece_map[n], cell(row, x), cell_w, min(x, 127), 1))
    with open(path, "wb") as fh:
        fh.write(jamoset.write_svfn(cell_w, cell_h, ascent, glyphs, packed.block, extra_flags=jamoset.FLAG_JAMO))
    return path


class CompositeTall(unittest.TestCase):
    def test_offsets_past_int8_keep_an_expanded_bitmap(self):
        with tempfile.TemporaryDirectory() as d:
            face_path = tall_jamo_face(os.path.join(d, "tall.svf"))
            face = svf2ttf.load_face(face_path)
            self.assertEqual(len([cp for cp in range(0xAC00, 0xD7A4) if face.composed(cp)]), 11172)
            out = os.path.join(d, "tall.ttf")
            line = run(os.path.join(HERE, "svf2ttf.py"), "ttf", face_path, out, "--composite", "--licence", "none")
            self.assertIn("(strike: 399 compound, 10773 expanded bitmaps)", line)
            f = TTFont(out)
            cmap = f.getBestCmap()
            strike = f["EBDT"].strikeData[0]
            for cp in (0xAC00, 0xAC01, 0xD7A3):
                adv, want = svf2ttf.glyph_pixels(face, cp)
                self.assertEqual(resolved_strike_pixels(f, cmap[cp], 1), (want, adv), hex(cp))
                self.assertTrue(f["glyf"][cmap[cp]].isComposite())
            self.assertIsInstance(strike[cmap[0xAC00]], ComponentBitmapGlyph)
            self.assertNotIsInstance(strike[cmap[0xAC01]], ComponentBitmapGlyph)

    def test_piece_ink_past_x_127_starts_at_the_pen(self):
        """A 200-wide 1 bpp jamo set: initials ink x 0, finals x 199. The plain strike holds every syllable (bearing x
        0); the final pieces' own bitmaps start at the pen (bearing x 0, not 199), so --composite converts it too."""
        with tempfile.TemporaryDirectory() as d:
            face_path = tall_jamo_face(os.path.join(d, "wide.svf"), cell_w=200, cell_h=16, ascent=12,
                                       place=lambda n: (1, 0) if n < 19 else (6, 1) if n < 40 else (14, 199))
            face = svf2ttf.load_face(face_path)
            plain = os.path.join(d, "plain.ttf")
            run(os.path.join(HERE, "svf2ttf.py"), "ttf", face_path, plain, "--licence", "none")
            out = os.path.join(d, "wide.ttf")
            line = run(os.path.join(HERE, "svf2ttf.py"), "ttf", face_path, out, "--composite", "--licence", "none")
            self.assertIn("(strike: 11172 compound, 0 expanded bitmaps)", line)
            f = TTFont(out)
            cmap = f.getBestCmap()
            for cp in (0xAC00, 0xAC01, 0xD7A3):
                adv, want = svf2ttf.glyph_pixels(face, cp)
                self.assertEqual(resolved_strike_pixels(f, cmap[cp], 1), (want, adv), hex(cp))
            final = f["glyf"][cmap[0xAC01]].components[-1].glyphName
            self.assertEqual(f["EBDT"].strikeData[0][final].metrics.BearingX, 0)


class Dy(unittest.TestCase):
    def test_dy_and_marks_keep_their_place(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "dy.svf")
            run(os.path.join(HERE, "svfdy.py"), NEODG16J, src, "--range", "0x67-0x6a", "--dy", "2")
            face = svfline.Face.load(src)
            self.assertEqual(face.metrics(0x67)[3], 2)
            ttf = os.path.join(d, "dy.ttf")
            run(os.path.join(HERE, "svf2ttf.py"), "ttf", src, ttf)
            f = TTFont(ttf)
            cmap = f.getBestCmap()
            adv, want = svf2ttf.glyph_pixels(face, 0x67)
            self.assertEqual(strike_pixels(f, cmap[0x67], 1)[0], want)
            # the ink reaches dy rows lower than without it
            _, plain = svf2ttf.glyph_pixels(svfline.Face.load(NEODG16J), 0x67)
            self.assertEqual(max(y for _, y in want), max(y for _, y in plain) + 2)
            self.assertGreaterEqual(f["OS/2"].usWinDescent, (max(y for _, y in want) + 1) * 64)


class Bdf(unittest.TestCase):
    def test_bdf_of_a_jamo_set(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "a.bdf")
            run(os.path.join(HERE, "svf2ttf.py"), "bdf", NEODG16A, out)
            with open(out, encoding="utf-8") as fh:
                text = fh.read()
            face = svfline.Face.load(NEODG16A)
            n = len(svf2ttf.face_cps(face))
            self.assertIn("CHARS %d\n" % n, text)
            self.assertEqual(text.count("STARTCHAR"), n)
            self.assertIn("FONT_ASCENT 12\n", text)
            # FreeType reads it at its pixel size and draws the face
            font = ImageFont.truetype(out, 16)
            img = Image.new("L", (100, 16), 0)
            ImageDraw.Draw(img).text((0, 12), "한글 A", font=font, fill=255, anchor="ls")
            want = svfline.layout([NEODG16A], "한글 A", 0, 12, 100, 16)
            self.assertEqual(img.point(lambda v: 255 if v >= 128 else 0).tobytes(), bytes(want))

    def test_bdf_two_bit(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "b.bdf")
            run(os.path.join(HERE, "svf2ttf.py"), "bdf", NGOTB15C, out)
            with open(out, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("SIZE 16 72 72 2\n", text)
            self.assertIn("POINT_SIZE 160\n", text)
            self.assertIn("RESOLUTION_X 72\n", text)
            face = svfline.Face.load(NGOTB15C)
            adv = face.metrics(0x41)[0]
            self.assertIn("ENCODING 65\nSWIDTH %d 0\nDWIDTH %d 0\n" % (round(adv * 1000 / 16), adv), text)
            # FreeType reads the 2-bit BDF and draws the levels
            font = ImageFont.truetype(out, 16)
            img = Image.new("L", (100, 16), 0)
            ImageDraw.Draw(img).text((0, face.ascent), "가A", font=font, fill=255, anchor="ls")
            self.assertEqual(img.tobytes(), bytes(svfline.layout([NGOTB15C], "가A", 0, face.ascent, 100, 16)))


class Cps(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(svf2ttf.cp_ranges([0x20, 0x21, 0x22, 0x41, 0xAC00, 0xAC01]), "20-22,41,ac00-ac01")
        # a one-code-point gap is not bridged: 41 and 43 stay apart, 44 joins 43
        self.assertEqual(svf2ttf.cp_ranges([0x41, 0x43, 0x44]), "41,43-44")
        out = run(os.path.join(HERE, "svf2ttf.py"), "cps", NEODG16A).strip()
        self.assertIn("ac00-d7a3", out)


class Licence(unittest.TestCase):
    """Licence discovery: web/LICENCES.tsv inside the repository, notes and FACES.TSV outside it."""

    @staticmethod
    def licences_tsv():
        rows = []
        with open(os.path.join(ROOT, "web", "LICENCES.tsv"), encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("#") or not line.strip():
                    continue
                g, f = line.rstrip("\n").split("\t")
                rows.append((g, [os.path.join(ROOT, "svf", x) for x in f.split(",")]))
        return rows

    @staticmethod
    def notice_holders():
        """[(face patterns relative to svf/, copyright cell)] of NOTICE.md's face table."""
        out = []
        with open(os.path.join(ROOT, "NOTICE.md"), encoding="utf-8") as fh:
            for line in fh:
                if not line.startswith("| `svf/"):
                    continue
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                pats, d = [], None
                for p in re.findall(r"`([^`]+)`", cells[0]):
                    if p.startswith("svf/"):
                        d, p = p[4:].split("/", 1)
                    pats.append("%s/%s" % (d, p))
                out.append((pats, cells[2]))
        return out

    def test_every_shipped_face(self):
        import fnmatch
        rows = self.licences_tsv()
        holders = self.notice_holders()
        faces = sorted(glob.glob(os.path.join(ROOT, "svf", "*", "*.SVF")))
        self.assertGreater(len(faces), 100)
        for path in faces:
            rel = os.path.relpath(path, os.path.join(ROOT, "svf")).replace(os.sep, "/")
            want = next(f for g, f in rows if fnmatch.fnmatchcase(rel, g))
            self.assertEqual(svf2ttf.find_licence(path), (True, want), rel)
            desc, copyright_, url = svf2ttf.licence_text(path, None)
            self.assertEqual(url, svf2ttf.OFL_URL, rel)
            self.assertIn("SIL OPEN FONT LICENSE", desc, rel)
            holder = next(h for pats, h in holders if any(fnmatch.fnmatchcase(rel, p + ("" if "." in p else "*"))
                                                          for p in pats))
            for word in re.findall(r"[A-Za-z0-9]{5,}", holder):
                self.assertIn(word.lower(), copyright_.lower(), "%s: %r not in %r" % (rel, word, copyright_))
            self.assertNotIn("Font Software", copyright_, rel)
            self.assertNotIn("  ", copyright_, rel)

    def test_paperlogy_and_maruburi(self):
        _, pap, _ = svf2ttf.licence_text(os.path.join(DOS, "PAPER16A.SVF"), None)
        _, maru, _ = svf2ttf.licence_text(os.path.join(DOS, "MARUS24.SVF"), None)
        self.assertIn("PT&", pap)
        self.assertNotIn("NAVER", pap)
        self.assertIn("NAVER", maru)
        self.assertNotIn("PT&", maru)

    def test_public_domain_attribution(self):
        _, c, _ = svf2ttf.licence_text(os.path.join(ROOT, "svf", "jamo-extra", "NDGPR16.SVF"), None)
        self.assertTrue(c.startswith("Original font was released under the public domain by Jungtae Kim"), c)

    def test_note_route_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("NEODG16J.SVF", "NEODGM.TXT", "OFL.TXT"):
                shutil.copy(os.path.join(DOS, n), d)
            inside, files = svf2ttf.find_licence(os.path.join(d, "NEODG16J.SVF"))
            self.assertEqual((inside, [os.path.basename(f) for f in files]), (False, ["NEODGM.TXT", "OFL.TXT"]))
            desc, c, url = svf2ttf.licence_text(os.path.join(d, "NEODG16J.SVF"), None)
            self.assertTrue(c.startswith("Copyright (c) 2017-2021, Eunbin Jeong"), c)
            self.assertIn("Neo Dunggeunmo faces", desc)

    def test_faces_tsv_route(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("GOTHA16.SVF", "FACES.TSV", "OFLGOTHA.TXT"):
                shutil.copy(os.path.join(ROOT, "svf", "jamo-extra", n), d)
            inside, files = svf2ttf.find_licence(os.path.join(d, "GOTHA16.SVF"))
            self.assertEqual((inside, [os.path.basename(f) for f in files]), (False, ["OFLGOTHA.TXT"]))
            self.assertIn("HanYang", svf2ttf.licence_text(os.path.join(d, "GOTHA16.SVF"), None)[1])

    def test_two_licences_in_one_note_are_both_credited(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("PAPER16A.SVF", "PAPMARU.TXT", "OFLPAPLG.TXT", "OFLMARU.TXT"):
                shutil.copy(os.path.join(DOS, n), d)
            r = subprocess.run([sys.executable, os.path.join(HERE, "svf2ttf.py"), "ttf", os.path.join(d, "PAPER16A.SVF"),
                                os.path.join(d, "p.ttf")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("2 licence files", r.stderr)
            c = TTFont(os.path.join(d, "p.ttf"))["name"].getDebugName(0)
            self.assertIn("PT&", c)
            self.assertIn("NAVER", c)

    def test_no_licence(self):
        with tempfile.TemporaryDirectory() as d:
            # outside the repository: a warning and a line saying the source font's licence applies
            shutil.copy(NEODG16J, d)
            desc, c, url = svf2ttf.licence_text(os.path.join(d, "NEODG16J.SVF"), None)
            self.assertIn("No licence note", desc)
            self.assertEqual((c, url), ("", ""))
            # inside a repository's svf/ tree that LICENCES.tsv does not cover: an error unless --licence is given
            os.makedirs(os.path.join(d, "repo", "svf", "x"))
            os.makedirs(os.path.join(d, "repo", "web"))
            with open(os.path.join(d, "repo", "web", "LICENCES.tsv"), "w") as fh:
                fh.write("# none\nx/OTHER.SVF\tx/OFL.TXT\n")
            face = os.path.join(d, "repo", "svf", "x", "F.SVF")
            shutil.copy(NEODG16J, face)
            with self.assertRaises(ValueError):
                svf2ttf.licence_text(face, None)
            r = subprocess.run([sys.executable, os.path.join(HERE, "svf2ttf.py"), "ttf", face, os.path.join(d, "f.ttf")],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("LICENCES.tsv", r.stderr)
            self.assertIn("Neo Dunggeunmo", svf2ttf.licence_text(face, os.path.join(DOS, "NEODGM.TXT"))[0])
            self.assertEqual(svf2ttf.licence_text(face, "none"), ("", "", ""))


class Synthetic(unittest.TestCase):
    """Faces built here: marks, private use, limits, header fields."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def path(self, name):
        return os.path.join(self.d, name)

    def ttf(self, face, *opts):
        out = self.path(os.path.basename(face) + ".ttf")
        run(os.path.join(HERE, "svf2ttf.py"), "ttf", face, out, "--licence", "none", *opts)
        return TTFont(out)

    def fails(self, *argv):
        r = subprocess.run([sys.executable, os.path.join(HERE, "svf2ttf.py")] + [str(a) for a in argv],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        return r.stderr

    def test_mark_at_its_origin_with_advance_0(self):
        face = synth(self.path("m.svf"), 8, 8, 6, {
            0x41: (6, 0, box_rows(8, 8, 1, 1, 5, 6)),
            0x301: (5, -4, box_rows(8, 8, 1, 0, 3, 1))})
        f = self.ttf(face)
        cmap = f.getBestCmap()
        adv, px = svf2ttf.glyph_pixels(svf2ttf.load_face(face), 0x301)
        self.assertEqual(adv, 0)
        self.assertEqual(min(x for x, _ in px), 1 - 4)           # min(-bearing_x, cell_w) columns left of the pen
        self.assertEqual(f["hmtx"][cmap[0x301]], (0, -3 * 64))
        self.assertEqual(strike_pixels(f, cmap[0x301], 1), (px, 0))
        # without flags bit 2 the cell stays at the pen
        plain = synth(self.path("p.svf"), 8, 8, 6, {0x301: (5, -4, box_rows(8, 8, 1, 0, 3, 1))}, flags=0)
        self.assertEqual(min(x for x, _ in svf2ttf.glyph_pixels(svf2ttf.load_face(plain), 0x301)[1]), 1)

    def test_private_use_glyphs_of_a_precomposed_face(self):
        g = {0x41: (8, 0, box_rows(8, 8, 1, 1, 6, 7)), 0xF0000: (8, 0, box_rows(8, 8, 0, 0, 8, 8)),
             0x100000: (8, 0, box_rows(8, 8, 2, 2, 4, 4))}
        face = synth(self.path("pua.svf"), 8, 8, 6, g)
        self.assertEqual(svf2ttf.face_cps(svf2ttf.load_face(face)), [0x41, 0xF0000, 0x100000])
        cmap = self.ttf(face).getBestCmap()
        self.assertIn(0xF0000, cmap)
        self.assertIn(0x100000, cmap)
        self.assertEqual(run(os.path.join(HERE, "svf2ttf.py"), "cps", face).strip(), "41,f0000,100000")
        # compare sees an inked private-use glyph that only one face has
        del g[0xF0000]
        less = synth(self.path("less.svf"), 8, 8, 6, g)
        r = svf2ttf.compare(face, less)
        self.assertEqual((r["only_a"], r["mismatches"]), (1, 1))
        # a jamo set's piece plane is not exported
        self.assertEqual(svf2ttf.face_cps(svf2ttf.load_face(NEODG16A))[-1], 0xD7A3)

    def test_non_characters_are_not_exported(self):
        g = {0x41: (8, 0, box_rows(8, 8, 1, 1, 6, 7)), 0xD800: (8, 0, box_rows(8, 8, 1, 1, 6, 7)),
             0xFFFF: (8, 0, box_rows(8, 8, 1, 1, 6, 7))}
        self.assertEqual(svf2ttf.face_cps(svf2ttf.load_face(synth(self.path("s.svf"), 8, 8, 6, g))), [0x41])
        empty = synth(self.path("e.svf"), 8, 8, 6, {0xD800: (8, 0, box_rows(8, 8, 1, 1, 6, 7))})
        for cmd in ("ttf", "bdf"):
            self.assertIn("no glyph", self.fails(cmd, empty, self.path("e.out")))

    def test_strike_byte_limits(self):
        rows = lambda h, top: box_rows(4, h, 0, top, 2, top + 1)  # noqa: E731
        ok = synth(self.path("ok.svf"), 4, 130, 127, {0x41: (4, 0, rows(130, 0))})
        f = self.ttf(ok)
        self.assertEqual(f["EBLC"].strikes[0].bitmapSizeTable.hori.ascender, 127)
        self.assertEqual(strike_pixels(f, f.getBestCmap()[0x41], 1)[0], {(0, -127): 1, (1, -127): 1})
        high = synth(self.path("high.svf"), 4, 130, 128, {0x41: (4, 0, rows(130, 0))})
        err = self.fails("ttf", high, self.path("high.ttf"), "--licence", "none")
        self.assertIn("-128..127", err)
        self.assertIn("--no-strike", err)
        self.assertNotIn("EBDT", self.ttf(high, "--no-strike"))
        run(os.path.join(HERE, "svf2ttf.py"), "bdf", high, self.path("high.bdf"), "--licence", "none")

    def test_wide_and_narrow_glyphs(self):
        """A 200-wide cell: a full-width A (right side bearing 0) and a narrow '.' (199) fit the strike, which stores
        only the least right side bearing; a strike-wide least below -128 is refused."""
        g = {0x41: (200, 0, box_rows(200, 16, 0, 2, 200, 12)), 0x2E: (200, 0, box_rows(200, 16, 0, 10, 1, 12))}
        f = self.ttf(synth(self.path("wide.svf"), 200, 16, 12, g))
        hori = f["EBLC"].strikes[0].bitmapSizeTable.hori
        self.assertEqual((hori.minAdvanceSB, hori.minOriginSB, hori.widthMax), (0, 0, 200))
        cmap = f.getBestCmap()
        self.assertEqual(strike_pixels(f, cmap[0x2E], 1), svf2ttf.glyph_pixels(svf2ttf.load_face(
            self.path("wide.svf")), 0x2E)[::-1])
        g[0x41] = (60, 0, box_rows(200, 16, 0, 2, 200, 12))           # ink 140 past its advance: least rsb -140
        err = self.fails("ttf", synth(self.path("over.svf"), 200, 16, 12, g), self.path("o.ttf"), "--licence", "none")
        self.assertIn("least right side bearing -140", err)

    def test_strike_wide_least_values_past_127_are_clamped(self):
        """A 200-wide cell whose only glyph is a '.' of advance 200: the least right side bearing (199) is stored as
        127, a valid lower bound, not refused; a per-glyph bearing x past 127 is still an error naming the glyph."""
        face = synth(self.path("dot.svf"), 200, 16, 12, {0x2E: (200, 0, box_rows(200, 16, 0, 10, 1, 12))})
        f = self.ttf(face)
        hori = f["EBLC"].strikes[0].bitmapSizeTable.hori
        self.assertEqual((hori.minOriginSB, hori.minAdvanceSB, hori.widthMax), (0, 127, 200))
        self.assertEqual(strike_pixels(f, f.getBestCmap()[0x2E], 1),
                         svf2ttf.glyph_pixels(svf2ttf.load_face(face), 0x2E)[::-1])
        far = synth(self.path("far.svf"), 200, 16, 12, {0x2E: (200, 0, box_rows(200, 16, 150, 10, 151, 12))})
        err = self.fails("ttf", far, self.path("far.ttf"), "--licence", "none")
        self.assertIn("U+002E: the bearing x 150", err)

    def test_ppem_and_errors(self):
        for ppem in ("0", "256", "-5"):
            self.assertIn("ppem", self.fails("ttf", NEODG16J, self.path("x.ttf"), "--ppem", ppem))
            self.assertIn("ppem", self.fails("bdf", NEODG16J, self.path("x.bdf"), "--ppem", ppem))
        bad = self.path("bad.svf")
        with open(bad, "wb") as fh:
            fh.write(b"SVFN\x03\x00junk")
        self.fails("cps", bad)
        self.fails("compare", bad, NEODG16J)
        self.fails("compare", self.path("missing.svf"), NEODG16J)
        self.fails("ttf", bad, self.path("bad.ttf"))

    def test_default_ppem_is_the_cell_height(self):
        f = self.ttf(os.path.join(DOS, "GBA17BX1.SVF"))                   # a 26x24 cell
        self.assertEqual(f["head"].unitsPerEm, 24 * 64)
        self.assertEqual(f["EBLC"].strikes[0].bitmapSizeTable.ppemX, 24)
        self.assertEqual(f["name"].getDebugName(1), "GBA17BX1 SVF")
        self.assertEqual(f["name"].getDebugName(6), "GBA17BX1SVF-Regular")

    def test_header_fields(self):
        f = self.ttf(NEODG16)
        os2 = f["OS/2"]
        self.assertEqual(os2.fsType, 0)
        self.assertEqual(os2.fsSelection, 0x40 | 0x80)                    # REGULAR | USE_TYPO_METRICS
        self.assertEqual(os2.ulCodePageRange1, 1 | 1 << 19)               # Latin 1, Korean Wansung (2,350 syllables)
        self.assertEqual(f["post"].isFixedPitch, 0)
        j = self.ttf(NEODG16A)
        self.assertEqual(j["OS/2"].ulCodePageRange1, 1 | 1 << 19 | 1 << 21)  # all 11,172: Johab too
        mono = synth(self.path("mono.svf"), 8, 8, 6, {0x41: (8, 0, box_rows(8, 8, 1, 1, 6, 7)),
                                                       0x42: (8, 0, box_rows(8, 8, 2, 1, 6, 7))})
        m = self.ttf(mono, "--style", "Bold Italic")
        self.assertEqual(m["post"].isFixedPitch, 1)
        self.assertEqual(m["OS/2"].fsSelection, 1 | 32 | 0x80)
        self.assertEqual((m["OS/2"].usWeightClass, m["head"].macStyle), (700, 3))
        self.assertEqual(m["OS/2"].ulCodePageRange1, 1)
        self.assertNotIn(".notdef", m.getBestCmap().values())

    def test_postscript_name(self):
        self.assertEqual(svf2ttf.ps_name("내 폰트", "Regular", "/x/neo16.svf"), "neo16-Regular")
        self.assertEqual(svf2ttf.ps_name("가", "굵게", "/x/한.svf"), "SVF-Regular")
        long = svf2ttf.ps_name("A" * 80, "B" * 40, "/x/f.svf")
        self.assertEqual(len(long), 63)
        self.assertTrue(long.endswith("-" + "B" * 29))

    def test_two_bpp_outline_threshold(self):
        face = synth(self.path("g.svf"), 4, 4, 3, {0x41: (4, 0, ["1230", "0000", "3000", "0000"])}, bpp=2)
        for threshold, want in (("128", {(1, 0), (2, 0), (0, 2)}), ("80", {(0, 0), (1, 0), (2, 0), (0, 2)}),
                                ("200", {(2, 0), (0, 2)})):
            f = self.ttf(face, "--threshold", threshold)
            glyph = f["glyf"][f.getBestCmap()[0x41]]
            got = {(c, r) for c in range(4) for r in range(4)
                   if _inside(glyph, f["glyf"], c * 64 + 32, (3 - r - 1) * 64 + 32)}
            self.assertEqual(got, want, threshold)
            self.assertEqual(f["EBLC"].strikes[0].bitmapSizeTable.bitDepth, 2)

    def test_default_threshold_is_128(self):
        face = synth(self.path("t.svf"), 4, 4, 3, {0x41: (4, 0, ["1230", "0000", "3000", "0000"])}, bpp=2)
        plain, explicit = self.ttf(face), self.ttf(face, "--threshold", "128")
        name = plain.getBestCmap()[0x41]
        self.assertEqual(plain["glyf"][name].getCoordinates(plain["glyf"])[0],
                         explicit["glyf"][name].getCoordinates(explicit["glyf"])[0])
        got = {(c, r) for c in range(4) for r in range(4)
               if _inside(plain["glyf"][name], plain["glyf"], c * 64 + 32, (3 - r - 1) * 64 + 32)}
        self.assertEqual(got, {(1, 0), (2, 0), (0, 2)})          # levels 2 and 3

    def bdf_text(self, face, *opts):
        out = self.path("b.bdf")
        run(os.path.join(HERE, "svf2ttf.py"), "bdf", face, out, *opts)
        with open(out, "rb") as fh:
            return fh.read().decode("utf-8")

    def test_bdf_bpp1_threshold(self):
        face = synth(self.path("t.svf"), 4, 4, 3, {0x41: (4, 0, ["1230", "0000", "3000", "0000"])}, bpp=2)
        for opts, rows in (((), ["60", "00", "80"]), (("--threshold", "80"), ["E0", "00", "80"]),
                           (("--threshold", "200"), ["20", "00", "80"])):
            text = self.bdf_text(face, "--licence", "none", "--bpp1", *opts)
            self.assertIn("SIZE 4 72 72\n", text, opts)                  # BDF 2.1, no bit depth field
            bitmap = text.split("STARTCHAR uni0041")[1].split("BITMAP\n")[1].split("\nENDCHAR")[0].split("\n")
            self.assertEqual(bitmap, rows, opts)

    def test_bdf_utf8_and_average_width(self):
        note = self.path("NOTE.TXT")
        with open(note, "w", encoding="utf-8") as fh:
            fh.write("테스트 글꼴 (T.SVF)\nCopyright (c) 2026 누군가\n")
        face = synth(self.path("t.svf"), 8, 8, 6, {0x41: (8, 0, box_rows(8, 8, 1, 1, 6, 7)),
                                                    0x2E: (3, 0, box_rows(8, 8, 0, 5, 1, 6)),
                                                    0x20: (4, 0, box_rows(8, 8, 0, 0, 0, 0))})
        text = self.bdf_text(face, "--licence", note)
        self.assertIn("COMMENT 테스트 글꼴 (T.SVF)", text)
        self.assertIn("누군가", text)
        self.assertIn("AVERAGE_WIDTH 50\n", text)                         # (8 + 3 + 4) / 3 * 10
        self.assertIn("-P-50-ISO10646-1", text)

    def test_name_14_only_with_an_ofl_text(self):
        note = self.path("PLAIN.TXT")
        with open(note, "w", encoding="utf-8") as fh:
            fh.write("A test face. Public domain.\n")
        face = synth(self.path("t.svf"), 8, 8, 6, {0x41: (8, 0, box_rows(8, 8, 1, 1, 6, 7))})
        f = self.ttf(face, "--licence", note)                     # self.ttf passes --licence none first; last wins
        self.assertIn("Public domain", f["name"].getDebugName(13))
        self.assertIsNone(f["name"].getDebugName(14))
        out = self.path("ofl.ttf")
        run(os.path.join(HERE, "svf2ttf.py"), "ttf", NEODG16J, out)
        self.assertEqual(TTFont(out)["name"].getDebugName(14), svf2ttf.OFL_URL)

    def test_glyph_limit(self):
        n = 65535
        big = self.path("big.svf")
        with open(big, "wb") as fh:
            fh.write(jamoset.pack_svfn(1, 1, 1, 1, jamoset.FLAG_MARKS_AT_ORIGIN, [b"\x80"] * n,
                                       [(0x10000 + i, i) for i in range(n)], [(1, 0, 1, 0)] * n, None, (0, 0)))
        err = self.fails("ttf", big, self.path("big.ttf"), "--licence", "none")
        self.assertIn("has 65535 glyphs; a TrueType font holds 65534 besides .notdef", err)

    def test_strike_line_metrics_and_win_ascent(self):
        """Ink a dy moves above the cell: the strike's highest ink, OS/2 winAscent and the lowest ink follow it."""
        g = {0x41: (8, 0, box_rows(8, 8, 1, 0, 6, 6)), 0x67: (8, 0, box_rows(8, 8, 2, 3, 5, 8))}
        face = synth(self.path("up.svf"), 8, 8, 6, g, dy={0x41: -2})
        f = self.ttf(face)
        hori = f["EBLC"].strikes[0].bitmapSizeTable.hori
        # A: rows 0..5 of the cell, its top 6 + 2 = 8 rows above the baseline; g: rows 3..7, down to 2 rows below
        self.assertEqual((hori.ascender, hori.descender), (6, -2))
        self.assertEqual((hori.maxBeforeBL, hori.minAfterBL), (8, -2))
        self.assertEqual((hori.minOriginSB, hori.minAdvanceSB, hori.widthMax), (1, 2, 8))
        self.assertEqual((f["OS/2"].usWinAscent, f["OS/2"].usWinDescent), (8 * 64, 2 * 64))
        self.assertEqual(f["OS/2"].sTypoAscender, 6 * 64)

    def test_win_metrics_with_dy_below_the_cell(self):
        face = synth(self.path("dy.svf"), 8, 8, 6, {0x67: (8, 0, box_rows(8, 8, 1, 4, 6, 8))}, dy={0x67: 3})
        f = self.ttf(face)
        # rows 4..7 of the cell, top at the baseline - 6 + 3: ink rows 1..4 below the baseline (bottom edge 5)
        self.assertEqual((f["OS/2"].usWinAscent, f["OS/2"].usWinDescent), (6 * 64, 5 * 64))
        self.assertEqual((f["hhea"].ascent, f["hhea"].descent), (6 * 64, -2 * 64))


def _inside(glyph, glyf, x, y):
    """Whether point (x, y) is inside @p glyph (nonzero winding over its line segments)."""
    coords, ends, _ = glyph.getCoordinates(glyf)
    wind, start = 0, 0
    for end in ends:
        pts = list(coords[start:end + 1])
        start = end + 1
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            if y0 <= y < y1 and (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) > 0:
                wind += 1
            elif y1 <= y < y0 and (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) < 0:
                wind -= 1
    return wind != 0


class Compare(unittest.TestCase):
    def test_counters(self):
        with tempfile.TemporaryDirectory() as d:
            base = {0x20: (4, 0, box_rows(8, 8, 0, 0, 0, 0)), 0x41: (8, 0, box_rows(8, 8, 1, 1, 6, 7)),
                    0x42: (8, 0, box_rows(8, 8, 1, 1, 5, 7)), 0x43: (8, 0, box_rows(8, 8, 2, 2, 5, 7)),
                    0x2E: (3, 0, box_rows(8, 8, 0, 0, 0, 0))}
            a = synth(os.path.join(d, "a.svf"), 8, 8, 6, base)
            b_g = dict(base)
            b_g[0x41] = (7, 0, base[0x41][2])          # an advance difference
            del b_g[0x43]                              # an inked glyph only A has
            del b_g[0x20]                              # a space only A has: a mismatch
            del b_g[0x2E]                              # another blank glyph only A has: counted apart
            b = synth(os.path.join(d, "b.svf"), 8, 8, 6, b_g)
            r = svf2ttf.compare(a, b)
            self.assertEqual((r["compared"], r["pixel"], r["advance"], r["only_a"], r["only_b"], r["blank_only"],
                              r["mismatches"]), (2, 0, 1, 2, 0, 1, 3))
            r = svf2ttf.compare(b, a)
            self.assertEqual((r["only_a"], r["only_b"]), (0, 2))

    def test_compare_finds_a_difference(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "dy.svf")
            run(os.path.join(HERE, "svfdy.py"), NEODG16J, src, "--range", "0x41", "--dy", "1")
            r = subprocess.run([sys.executable, os.path.join(HERE, "svf2ttf.py"), "compare", NEODG16J, src],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("mismatches 1", r.stdout)


if __name__ == "__main__":
    unittest.main()
