#!/usr/bin/env python3
"""The how-tos of docs/recipes.md, run end to end on synthetic fonts built here and on OFL fonts in ttf/ (no other
font data). Each test runs the commands the document gives, as subprocesses, into a temp dir.
  python3 -m unittest tools.test_recipes
"""
import io
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import jamoset  # noqa: E402
import mkfont  # noqa: E402


def run(*argv):
    r = subprocess.run([sys.executable] + [str(a) for a in argv], capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError("%s exit %d\n%s%s" % (argv[0], r.returncode, r.stdout, r.stderr))
    return r.stdout


def face(path):
    with open(path, "rb") as fh:
        return jamoset.parse_svfn(fh.read())


def raw_johab(px, slots, blank, bpr=None):
    """A raw jamo font: @p slots glyphs of px x px, row major; slot i draws a 2-pixel-high bar at row i % (px - 2) and
    a column mark at i % px, except the @p blank slots (the layout's empty slot 0 of every set)."""
    bpr = bpr or (px + 7) // 8
    out = bytearray()
    for i in range(slots):
        rows = [0] * px
        if i not in blank:
            r = i % (px - 2)
            rows[r] = rows[r + 1] = (1 << (bpr * 8)) - 1
            for y in range(px):
                rows[y] |= 1 << (bpr * 8 - 1 - (i % px))
        for v in rows:
            out += v.to_bytes(bpr, "big")
    return bytes(out)


def eng_8x16():
    """A raw 8x16 DOS English font (4096 bytes): every glyph a box with its code's low bits in the middle row."""
    out = bytearray()
    for c in range(256):
        g = [0] * 16
        if 0x21 <= c <= 0x7E:
            g[2] = g[13] = 0xFF
            for y in range(2, 14):
                g[y] |= 0x81
            g[7] = c & 0x7F
        out += bytes(g)
    return bytes(out)


def bdf(glyphs, w, h, ascent, registry, encoding):
    """A BDF text: @p glyphs {encoding: [row ints]} in a w x h box with the baseline at row @p ascent."""
    lines = ["STARTFONT 2.1", "FONT -synth-test-medium-r-normal--%d-%d-75-75-c-%d-%s-%s" % (h, h * 10, w * 10, registry, encoding),
             "SIZE %d 75 75" % h, "FONTBOUNDINGBOX %d %d 0 %d" % (w, h, ascent - h),
             "STARTPROPERTIES 4", "FONT_ASCENT %d" % ascent, "FONT_DESCENT %d" % (h - ascent),
             'CHARSET_REGISTRY "%s"' % registry, 'CHARSET_ENCODING "%s"' % encoding, "ENDPROPERTIES",
             "CHARS %d" % len(glyphs)]
    bpr = (w + 7) // 8
    for enc, rows in sorted(glyphs.items()):
        lines += ["STARTCHAR g%04X" % enc, "ENCODING %d" % enc, "SWIDTH 1000 0", "DWIDTH %d 0" % w,
                  "BBX %d %d 0 %d" % (w, h, ascent - h), "BITMAP"]
        lines += ["%0*X" % (bpr * 2, r << (bpr * 8 - w)) for r in rows]
        lines.append("ENDCHAR")
    lines.append("ENDFONT")
    return "\n".join(lines) + "\n"


class DosJohab(unittest.TestCase):
    """(f) DOS raw jamo fonts: 8x4x4 (16 px, 11,520 bytes) and 6x2x1 (6,144 bytes), with an 8x16 English font."""

    def test_raw_844_with_eng(self):
        with tempfile.TemporaryDirectory() as d:
            raw = os.path.join(d, "HANGUL.FNT")
            eng = os.path.join(d, "ENGLISH.FNT")
            blank = set(jamoset.slots_of(8, 4, 4, 160, 248))
            with open(raw, "wb") as fh:
                fh.write(raw_johab(16, 360, blank))
            with open(eng, "wb") as fh:
                fh.write(eng_8x16())
            out = os.path.join(d, "SYN16J.SVF")
            text = run(os.path.join(HERE, "jamoset.py"), "--layout", "844", raw, "--eng", eng, "--symbols", "--check",
                       "-o", out)
            self.assertIn("check: composed 11172 syllables", text)
            f = face(out)
            t = jamoset.unpack(f.jset)
            self.assertEqual((f.cell_w, f.cell_h, t.ni, t.nm, t.nf), (16, 16, 8, 4, 4))
            self.assertIn(0x41, f.glyphs)
            self.assertIn(0x2026, f.glyphs)
            # 가 = initial ㄱ of set 0 (slot 1) OR medial ㅏ of set 0 (slot 161): the raw rows themselves
            src = open(raw, "rb").read()
            want = bytes(a | b for a, b in zip(src[1 * 32:2 * 32], src[161 * 32:162 * 32]))
            self.assertEqual(jamoset.compose(f, t, 0xAC00), want)

    def test_raw_621(self):
        with tempfile.TemporaryDirectory() as d:
            raw = os.path.join(d, "APPLE2.FNT")
            # 192 glyphs of 32 bytes in byte-column order: column byte x of row y at x * 16 + y
            data = bytearray()
            for i in range(192):
                g = bytearray(32)
                if i % 20 and not (120 <= i < 164 and (i - 120) % 22 == 0) and i != 164:
                    g[i % 16] = 0xFF
                    g[16 + (i * 7) % 16] = 0x81
                data += g
            with open(raw, "wb") as fh:
                fh.write(bytes(data))
            out = os.path.join(d, "SYN6J.SVF")
            text = run(os.path.join(HERE, "jamoset.py"), "--layout", "621", raw, "--check", "-o", out)
            self.assertIn("check: composed 11172 syllables", text)
            t = jamoset.unpack(face(out).jset)
            self.assertEqual((t.lc, t.tc, t.ni, t.nm, t.nf), (1, 2, 6, 2, 1))

    def test_from_svf_fit_of_a_precomposed_face(self):
        """A precomposed 1 bpp face (a subset bake of neodgm) refitted to 8x4x4 pieces."""
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "J.SVF")
            text = run(os.path.join(HERE, "jamoset.py"), "--layout", "844", "--from-svf",
                       os.path.join(ROOT, "svf", "dos", "NEODG16J.SVF"), "--mask", "none", "--check", "-o", out)
            self.assertIn("IoU 1.000", text)
            f = face(out)
            self.assertTrue(f.jset)
            src = face(os.path.join(ROOT, "svf", "dos", "NEODG16J.SVF"))
            t = jamoset.unpack(f.jset)
            for cp in [c for c in src.glyphs if 0xAC00 <= c <= 0xD7A3][:50]:
                self.assertEqual(jamoset.compose(f, t, cp), src.glyphs[cp], hex(cp))


class XWindow(unittest.TestCase):
    """(g) X11 Korean bitmap fonts: a KS X 1001 (ksc5601) BDF through bdfface.py, then jamoset.py --from-svf; and a
    hanterm johab-1 BDF through jamoset.py --layout hanterm-johab."""

    def test_ksc5601_bdf(self):
        sylls = "가각간갇갈감갑갓강개"
        glyphs = {}
        for k, ch in enumerate(sylls):
            gl = int.from_bytes(ch.encode("euc_kr"), "big") - 0x8080          # EUC-KR -> GL code, as in the BDF
            glyphs[gl] = [(0xFFFF if y in (1, 14) else 0x8001) | (1 << (k + 3)) for y in range(16)]
        ascii_glyphs = {c: [0x00 if y < 3 or y > 12 else 0x3C for y in range(16)] for c in range(0x20, 0x7F)}
        with tempfile.TemporaryDirectory() as d:
            han = os.path.join(d, "hanglm16.bdf")
            asc = os.path.join(d, "ascii8x16.bdf")
            with open(han, "w") as fh:
                fh.write(bdf(glyphs, 16, 16, 14, "KSC5601.1987", "0"))
            with open(asc, "w") as fh:
                fh.write(bdf(ascii_glyphs, 8, 16, 14, "ISO10646", "1"))
            chars = os.path.join(d, "chars.txt")
            with open(chars, "w", encoding="utf-8") as fh:
                fh.write(sylls)
            pre = os.path.join(d, "SYNKS16.SVF")
            run(os.path.join(HERE, "bdfface.py"), "--hangul", han, "--ascii", asc, "--cell", "16x16", "--chars-from", chars,
                "-o", pre)
            f = face(pre)
            self.assertEqual(sorted(c for c in f.glyphs if 0xAC00 <= c <= 0xD7A3), sorted(ord(c) for c in sylls))
            self.assertIn(0x41, f.glyphs)
            ga = f.glyphs[0xAC00]
            self.assertEqual(int.from_bytes(ga[2:4], "big"), 0xFFFF)             # row 1 of the BDF is row 1 of the cell
            self.assertEqual(int.from_bytes(ga[4:6], "big"), 0x8001 | (1 << 3))

    def test_euc_kr_and_johab_mapping(self):
        self.assertEqual(bytes((0xB0, 0xA1)).decode("euc_kr"), "가")
        self.assertEqual(0xB0A1 - 0x8080, 0x3021)                            # the GL code a ksc5601 BDF carries
        self.assertEqual(bytes((0x88, 0x61)).decode("johab"), "가")          # KS X 1001 annex 3 (johab)
        self.assertEqual(bytes((0xD3, 0xBD)).decode("johab"), "힣")
        # johab code -> (initial, medial, final) bit fields = the Unicode syllable formula
        code = 0x8861
        cho, jung, jong = (code >> 10) & 31, (code >> 5) & 31, code & 31
        self.assertEqual((cho, jung, jong), (2, 3, 1))                      # fill values: ㄱ, ㅏ, no final

    def test_hanterm_johab_bdf(self):
        glyphs = {}
        for i in range(529):                                               # johab-1: glyph numbers 0..528
            glyphs[i] = [((1 << (i % 16)) | (0xFFFF if y == i % 15 else 0)) & 0xFFFF for y in range(16)]
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "johabm16.bdf")
            with open(src, "w") as fh:
                fh.write(bdf(glyphs, 16, 16, 14, "johab", "1"))
            out = os.path.join(d, "HTSYN16.SVF")
            text = run(os.path.join(HERE, "jamoset.py"), "--layout", "hanterm-johab", src, "--check", "-o", out)
            self.assertIn("check: composed 11172 syllables", text)
            t = jamoset.unpack(face(out).jset)
            self.assertEqual((t.ni, t.nm, t.nf), (10, 4, 4))


class KsX1001(unittest.TestCase):
    """(h) the KS X 1001 sets of mkfont.py and jamoset.py agree with Python's euc_kr codec."""

    def test_sets(self):
        ks = [ord(bytes((hi, lo)).decode("euc_kr")) for hi in range(0xB0, 0xC9) for lo in range(0xA1, 0xFF)]
        self.assertEqual(len(ks), 2350)
        self.assertEqual(mkfont.NAMED_RANGES["ksx1001-hangul"](), ks)
        self.assertEqual([0xAC00 + s for s in jamoset.ks_x_1001_syllables()], sorted(ks))
        self.assertEqual(len(mkfont.NAMED_RANGES["hangul"]()), 11172)
        jamo = mkfont.NAMED_RANGES["jamo"]()
        self.assertEqual((jamo[0], jamo[-1], len(jamo)), (0x3131, 0x318E, 94))
        nohanja = mkfont.NAMED_RANGES["ksx1001-nohanja"]()
        self.assertFalse([c for c in nohanja if 0x4E00 <= c <= 0x9FFF])
        self.assertEqual(len(set(mkfont.NAMED_RANGES["ksx1001-symbols"]()) | set(ks)), len(nohanja))


class Outline(unittest.TestCase):
    """(c), (i), (j) on OFL fonts in ttf/: a variable font's instance, a TTC, the clip report and svfdy."""

    def test_variable_font_instance(self):
        from fontTools.varLib import instancer
        from fontTools.ttLib import TTFont
        with tempfile.TemporaryDirectory() as d:
            bold = os.path.join(d, "Caveat-Bold.ttf")
            instancer.instantiateVariableFont(TTFont(os.path.join(ROOT, "ttf", "caveat", "Caveat-VF.ttf")),
                                              {"wght": 700}).save(bold)
            a, b = os.path.join(d, "def.svf"), os.path.join(d, "bold.svf")
            for src, out in ((os.path.join(ROOT, "ttf", "caveat", "Caveat-VF.ttf"), a), (bold, b)):
                run(os.path.join(HERE, "mkfont.py"), src, out, "--size", "24", "--bpp", "2", "--unicode", "ascii", "--latin")
            fa, fb = face(a), face(b)
            self.assertEqual(len(fa.glyphs), len(fb.glyphs))
            ink = lambda f: sum(bin(x).count("1") for g in f.glyphs.values() for x in g)
            self.assertGreater(ink(fb), ink(fa))                             # the Bold instance, not the default

    def test_ttc_bakes_its_first_font(self):
        from fontTools.ttLib import TTFont
        from fontTools.ttLib.ttCollection import TTCollection
        with tempfile.TemporaryDirectory() as d:
            ttc = os.path.join(d, "g.ttc")
            c = TTCollection()
            c.fonts = [TTFont(os.path.join(ROOT, "ttf", "galmuri", n)) for n in ("Galmuri9.ttf", "Galmuri7.ttf")]
            c.save(ttc)
            one = os.path.join(d, "one.ttf")
            TTCollection(ttc).fonts[1].save(one)
            outs = []
            for src, size in ((ttc, 10), (os.path.join(ROOT, "ttf", "galmuri", "Galmuri9.ttf"), 10), (one, 8)):
                out = os.path.join(d, "%d-%s.svf" % (size, os.path.basename(src)))
                run(os.path.join(HERE, "mkfont.py"), src, out, "--size", size, "--bpp", "1", "--unicode", "ascii,AC00-AC10")
                outs.append(open(out, "rb").read())
            self.assertEqual(outs[0], outs[1])                               # index 0 of the TTC
            self.assertNotEqual(outs[1], outs[2])

    def test_clip_report_and_svfdy(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "c.svf")
            text = run(os.path.join(HERE, "mkfont.py"), os.path.join(ROOT, "ttf", "nanumgothic", "NanumGothic-Bold.ttf"),
                       out, "--size", "18", "--cell", "16", "--bpp", "1", "--unicode", "ascii,AC00-AC20", "--fit-cell")
            import re
            size, ascent = map(int, re.search(r"--fit-cell: (\d+)px, ascent (\d+)", text).groups())
            self.assertLess(size, 18)                                          # shrunk until every glyph fits
            self.assertIn("모두 셀 안", text)
            dy = os.path.join(d, "dy.svf")
            run(os.path.join(HERE, "svfdy.py"), out, dy, "--range", "0x67,0x6a,0x70,0x71,0x79", "--dy", "1")
            f = face(dy)
            self.assertEqual((f.dy_min, f.dy_max), (0, 1))


class SvfToTtf(unittest.TestCase):
    """An SVF face back to a TTF bitmap font: the section's commands on the shipped jamo set NEODG16A."""

    def test_jamo_set_to_ttf_and_back(self):
        with tempfile.TemporaryDirectory() as d:
            face_path = os.path.join(ROOT, "svf", "dos", "NEODG16A.SVF")
            tool = os.path.join(HERE, "svf2ttf.py")
            ttf, bdf, back = (os.path.join(d, n) for n in ("NEODG16A.ttf", "NEODG16A.bdf", "back.svf"))
            self.assertIn("11319 glyphs", run(tool, "ttf", face_path, ttf, "--family", "My Pixel", "--style",
                                             "Regular", "--version", "1.001"))
            self.assertIn("11319 glyphs", run(tool, "bdf", face_path, bdf))
            cps = run(tool, "cps", face_path).strip()
            self.assertEqual(cps, "20-7e,25a1,3131-3163,ac00-d7a3")
            run(os.path.join(HERE, "mkfont.py"), ttf, back, "--size", 16, "--bpp", 1, "--probe", "--width", 16,
                "--only-listed", "--unicode", cps)
            out = run(tool, "compare", face_path, back)
            self.assertIn("compared 11318 glyphs: mismatches 0", out)
            self.assertIn("blank glyphs only one face has 1", out)


if __name__ == "__main__":
    unittest.main()
