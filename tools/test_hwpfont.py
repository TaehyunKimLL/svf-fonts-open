#!/usr/bin/env python3
"""Tests of hwpfont.py (HWP 1.x .SFT/.PFT, HWP 3.0 .FNT, headerless KS X 1001 syllable dumps) and of the jamoset.py paths
that read them (--layout hwp1, --layout 844-hwp3, --eng of an HWP English font), on synthetic files built here (no font
data). The real-file checks run only where JOHAB_FONTS names the research tree, and compare hashes.
  python3 -m unittest tools.test_hwpfont
"""
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bdfface  # noqa: E402
import hwpfont  # noqa: E402
import jamoset  # noqa: E402


def run(*argv, ok=True):
    r = subprocess.run([sys.executable, "-I"] + [str(a) for a in argv], capture_output=True, text=True)
    if ok and r.returncode != 0:
        raise AssertionError("%s exit %d\n%s%s" % (argv[0], r.returncode, r.stdout, r.stderr))
    return r


def wr(path, data):
    with open(path, "wb") as fh:
        fh.write(data)


def rd(path):
    with open(path, "rb") as fh:
        return fh.read()


def txt(path):
    with open(path, encoding="ascii") as fh:
        return fh.read()


def pattern(i, w, h):
    """Glyph @p i of a synthetic font: a 1-pixel mark at column i % w on row i % h, a second at column (i // w) % w on row
    (i * 7) % h, and the glyph's low bits in the top row - every glyph of a few thousand distinct."""
    rows = [0] * h
    rows[i % h] |= 1 << (w - 1 - i % w)
    rows[(i * 7) % h] |= 1 << (w - 1 - (i // w) % w)
    rows[0] |= (i & ((1 << min(w, 12)) - 1)) << max(0, w - 12)
    return rows


def encode(rows, w, h, colmajor):
    if colmajor:                         # w columns of h/8 bytes, MSB = top
        out = bytearray()
        for x in range(w):
            col = 0
            for y in range(h):
                if rows[y] >> (w - 1 - x) & 1:
                    col |= 1 << (h - 1 - y)
            out += col.to_bytes(h // 8, "big")
        return bytes(out)
    bpr = (w + 7) // 8
    return b"".join((r << (bpr * 8 - w)).to_bytes(bpr, "big") for r in rows)


def hwp1(w, h, count, magic=hwpfont.HWP1_MAGIC, glyph=pattern):
    """An HWP 1.x font file: the 32-byte "HWP Font Editor v1.0" header, BE16 count at 0x1c, (w-1, h-1) at 0x1e, then
    @p count glyphs (column-major for a 24-row printer font)."""
    head = bytearray(32)
    head[:len(magic)] = magic
    struct.pack_into(">H", head, 0x1c, count)
    head[0x1e], head[0x1f] = w - 1, h - 1
    col = h == 24
    return bytes(head) + b"".join(encode(glyph(i, w, h), w, h, col) for i in range(count))


def hwp3(kind, w, h, stored, count=None, glyph=pattern, name="test".encode()):
    """An HWP 3.0 .FNT: the 72-byte header ("FNT\\x01", type, 1, LE16 W and H, 8/4/4 for Hangul, LE32 count, a name)
    and @p stored row-major glyphs."""
    head = bytearray(72)
    head[:4] = b"FNT\x01"
    head[4], head[5] = kind, 1
    struct.pack_into("<HH", head, 6, w, h)
    if kind == 1 and w == h == 16:
        struct.pack_into("<HHH", head, 10, 8, 4, 4)
    struct.pack_into("<I", head, 0x10, count if count is not None else stored)
    head[0x14:0x14 + len(name)] = name
    return bytes(head) + b"".join(encode(glyph(i, w, h), w, h, False) for i in range(stored))


def ascii_glyph(i, w, h):
    """An HWP English font's glyph @p i: an 'H'-like box whose ink ends at row h - 4 (the baseline row h - 3)."""
    rows = [0] * h
    for y in range(2, h - 3):
        rows[y] = (1 << (w - 1)) | 1
    rows[h // 2] |= (1 << w) - 1
    rows[1] = i & ((1 << w) - 1)
    return rows


def or_rows(*gs):
    out = [0] * len(gs[0])
    for g in gs:
        out = [a | b for a, b in zip(out, g)]
    return out


def svf_rows(face, cp):
    """The rows of @p cp as composed by the engine's rule from a jamo-set SVF (bit w-1-x = pixel x)."""
    t = jamoset.unpack(face.jset)
    raw = jamoset.compose(face, t, cp)
    bpr = (face.cell_w + 7) // 8
    return [int.from_bytes(raw[y * bpr:(y + 1) * bpr], "big") >> (bpr * 8 - face.cell_w) for y in range(face.cell_h)]


class Container(unittest.TestCase):
    def test_hwp1_header_and_glyph_orders(self):
        sft = hwpfont.read(hwp1(16, 16, 1193))
        self.assertEqual((sft.family, sft.kind, sft.w, sft.h, sft.count), ("hwp1", "hangul", 16, 16, 1193))
        self.assertEqual(sft.glyph(5), pattern(5, 16, 16))
        pft = hwpfont.read(hwp1(24, 24, 980))
        self.assertEqual((pft.kind, pft.w, pft.h, pft.count), ("hangul", 24, 24, 980))
        self.assertEqual(pft.glyph(977), pattern(977, 24, 24))      # column-major, MSB = top
        fe = hwpfont.read(hwp1(24, 24, 980, magic=b"FE\x1a\x00"))   # HPFT3.LZH's HANGUL3.PFT
        self.assertEqual(fe.glyph(3), pattern(3, 24, 24))
        asc = hwpfont.read(hwp1(14, 24, 991))
        self.assertEqual((asc.kind, asc.w, asc.h), ("ascii", 14, 24))
        self.assertEqual(hwpfont.read(hwp1(16, 16, 4888)).kind, "hanja")
        self.assertEqual(hwpfont.read(hwp1(16, 16, 855)).kind, "other")

    def test_hwp1_refusals(self):
        with self.assertRaisesRegex(hwpfont.HwpError, "size"):
            hwpfont.read(hwp1(16, 16, 1193)[:-1])
        with self.assertRaisesRegex(hwpfont.HwpError, "not"):
            hwpfont.read(b"\0" * 1000)

    def test_hwp3_header(self):
        han = hwpfont.read(hwp3(1, 16, 16, 2710))
        self.assertEqual((han.family, han.kind, han.w, han.h, han.count, han.jamo844), ("hwp3", "hangul", 16, 16, 2710, True))
        self.assertEqual(han.glyph(2351), pattern(2351, 16, 16))
        h24 = hwpfont.read(hwp3(1, 24, 24, 2350, count=2710))      # HAN24: the header says 2710, the body holds 2350
        self.assertEqual((h24.count, h24.jamo844), (2350, False))
        eng = hwpfont.read(hwp3(0, 20, 40, 96, count=147))
        self.assertEqual((eng.kind, eng.w, eng.h, eng.count), ("ascii", 20, 40, 96))
        self.assertEqual(hwpfont.read(hwp3(2, 16, 16, 4888)).kind, "hanja")
        with self.assertRaisesRegex(hwpfont.HwpError, "size"):
            hwpfont.read(hwp3(1, 16, 16, 2710)[:-3])

    def test_ks_raw_sizes(self):
        for px in (16, 24, 32, 40, 48):
            gb = (px + 7) // 8 * px
            self.assertEqual(hwpfont.ks_raw_px(2350 * gb), px)
            f = hwpfont.read(b"".join(encode(pattern(i, px, px), px, px, False) for i in range(2350)))
            self.assertEqual((f.family, f.kind, f.w, f.count), ("ks-raw", "hangul", px, 2350))
        self.assertIsNone(hwpfont.ks_raw_px(11520))
        with self.assertRaisesRegex(hwpfont.HwpError, "blank"):
            hwpfont.read(bytes(169200))


class Hwp1Composition(unittest.TestCase):
    def test_rule_by_hand(self):
        """가 and 한 of the SFT's face 0, worked out by hand from HWP.EXE's tables (notes in hwpfont.py): 가 = initial set 0
        piece 1 (glyph 0) | vowel set 0 piece 1 (glyph 310); 한 = initial set 5 piece 19 (glyph 173) | vowel set 3
        piece 1 (397) | final set 0 piece 4 (429). The PFT's face 1 starts at glyph 368."""
        f = hwpfont.read(hwp1(16, 16, 1193))
        h = hwpfont.Hwp1Hangul(f, 0)
        self.assertEqual(h.pieces(0xAC00), (0, 310, None))
        self.assertEqual(h.pieces(ord("한")), (173, 397, 429))
        self.assertEqual(h.syllable(ord("한")), or_rows(f.glyph(173), f.glyph(397), f.glyph(429)))
        p = hwpfont.Hwp1Hangul(hwpfont.read(hwp1(24, 24, 980)), 1)
        self.assertEqual(p.pieces(0xAC00), (368, 368 + 7 * 31, None))
        with self.assertRaisesRegex(hwpfont.HwpError, "face"):
            hwpfont.Hwp1Hangul(f, 3)

    def test_jamoset_layout_composes_like_the_rule(self):
        """jamoset.py --layout hwp1 writes the HWP rule as JSET tables: --check composes every syllable from the SVF and
        compares it with hwpfont's own composition; the face equals the rule at 가, 한, 뷁 and 힣."""
        with tempfile.TemporaryDirectory() as d:
            for w, n, face in ((16, 1193, 0), (16, 1193, 2), (24, 980, 1)):
                src = os.path.join(d, "HANGUL.%d" % w)
                wr(src, hwp1(w, w, n))
                out = os.path.join(d, "o%d%d.svf" % (w, face))
                r = run(os.path.join(HERE, "jamoset.py"), "--layout", "hwp1", "--face", face, src, "--check", "-o", out)
                self.assertIn("identical to the HWP 1.x rule", r.stdout)
                sv = jamoset.parse_svfn(rd(out))
                h = hwpfont.Hwp1Hangul(hwpfont.read(rd(src)), face)
                for ch in "가한뷁힣":
                    self.assertEqual(svf_rows(sv, ord(ch)), h.syllable(ord(ch)), (w, face, ch))
            r = run(os.path.join(HERE, "jamoset.py"), "--layout", "hwp1", "--face", 3, src, "-o", out, ok=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("face", r.stderr)

    def test_hwp1_eng_companion(self):
        """--eng takes an HWP 1.x ASCII file: face --eng-face of its six (glyph 109 + face * 147 + code - 0x20)."""
        with tempfile.TemporaryDirectory() as d:
            src, eng, out = os.path.join(d, "H.SFT"), os.path.join(d, "ASCII.SFT"), os.path.join(d, "o.svf")
            wr(src, hwp1(16, 16, 1193))
            wr(eng, hwp1(8, 16, 991, glyph=ascii_glyph))
            run(os.path.join(HERE, "jamoset.py"), "--layout", "hwp1", src, "--eng", eng, "--eng-face", 1, "-o", out)
            sv = jamoset.parse_svfn(rd(out))
            want = ascii_glyph(109 + 147 + 0x41 - 0x20, 8, 16)
            got = sv.glyphs[0x41]
            self.assertEqual([got[y * 2] for y in range(16)], want)
            pft, eng24 = os.path.join(d, "H.PFT"), os.path.join(d, "ASCII.PFT")
            wr(pft, hwp1(24, 24, 980))
            wr(eng24, hwp1(14, 24, 991, glyph=ascii_glyph))
            run(os.path.join(HERE, "jamoset.py"), "--layout", "hwp1", "--face", 1, pft, "--eng", eng24, "-o", out)
            sv = jamoset.parse_svfn(rd(out))
            self.assertEqual(sv.metrics[0x41][0], 14)
            self.assertEqual(sv.ascent, 21)                    # the companion's baseline row ('H' ink ends at row 20)


class Hwp3AndKsRaw(unittest.TestCase):
    def test_hwp3_jamo_tail_is_an_844(self):
        """HAN16's 360 glyphs after the 2,350 syllables are an 8x4x4 set: --layout 844-hwp3 reads them (blank fill
        slots checked) and --check compares with johab844.py."""
        def g(i, w, h):
            return [0] * h if i >= 2350 and (i - 2350) in blank else pattern(i, w, h)
        blank = set(jamoset.slots_of(8, 4, 4, 160, 248))
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "HAN16_0.FNT"), os.path.join(d, "o.svf")
            wr(src, hwp3(1, 16, 16, 2710, glyph=g))
            r = run(os.path.join(HERE, "jamoset.py"), "--layout", "844-hwp3", src, "--check", "-o", out)
            self.assertIn("identical to johab844.py", r.stdout)
            wr(src, hwp3(1, 24, 24, 2350, count=2710))
            r = run(os.path.join(HERE, "jamoset.py"), "--layout", "844-hwp3", src, "-o", out, ok=False)
            self.assertIn("no 8x4x4", r.stderr)

    def test_bdf_of_syllables_then_bdfface(self):
        """`hwpfont.py bdf` writes the KS X 1001 syllables of a KS raw dump, an HWP 3.0 FNT and a composed HWP 1.x face
        as a Unicode BDF (glyph i = the i-th syllable in KS order), with the ASCII of a companion; bdfface.py bakes it."""
        ks = [cp for cp in hwpfont.ks_hangul()]
        self.assertEqual((len(ks), chr(ks[0]), chr(ks[-1])), (2350, "가", "힝"))
        with tempfile.TemporaryDirectory() as d:
            raw, fnt, eng = os.path.join(d, "GHAN24.PFT"), os.path.join(d, "HAN24_0.FNT"), os.path.join(d, "ENG24_0.FNT")
            wr(raw, b"".join(encode(pattern(i, 24, 24), 24, 24, False) for i in range(2350)))
            wr(fnt, hwp3(1, 24, 24, 2350, count=2710))
            wr(eng, hwp3(0, 12, 24, 147, glyph=ascii_glyph))
            chars = os.path.join(d, "ks.txt")
            with open(chars, "w", encoding="utf-8") as fh:
                fh.write("".join(map(chr, ks)))
            for src in (raw, fnt):
                bdf, svf = src + ".bdf", src + ".svf"
                r = run(os.path.join(HERE, "hwpfont.py"), "bdf", src, "--ascii", eng, "-o", bdf)
                self.assertIn("2350 Hangul syllables", r.stdout)
                text = txt(bdf)
                self.assertIn("PIXEL_SIZE 24", text)
                self.assertIn("FONT_ASCENT 21", text)       # the companion's baseline
                run(os.path.join(HERE, "bdfface.py"), "--hangul", bdf, "--ascii", bdf, "--cell", "24x24", "--chars-from",
                    chars, "-o", svf)
                sv = jamoset.parse_svfn(rd(svf))
                cp = ks[1000]
                self.assertEqual(sv.glyphs[cp], encode(pattern(1000, 24, 24), 24, 24, False), src)
                self.assertEqual(sv.metrics[0x41][0], 12)
            h1, a1 = os.path.join(d, "HANGUL.SFT"), os.path.join(d, "ASCII.SFT")
            wr(h1, hwp1(16, 16, 1193))
            wr(a1, hwp1(8, 16, 991, glyph=ascii_glyph))
            bdf = os.path.join(d, "h1.bdf")
            r = run(os.path.join(HERE, "hwpfont.py"), "bdf", h1, "--face", 2, "--syllables", "all", "--ascii", a1, "-o", bdf)
            self.assertIn("11172 Hangul syllables", r.stdout)
            text = txt(bdf)
            hh = hwpfont.Hwp1Hangul(hwpfont.read(rd(h1)), 2)
            block = text.split("STARTCHAR U+D7A3\n", 1)[1].split("BITMAP\n", 1)[1].split("ENDCHAR", 1)[0].split()
            self.assertEqual([int(x, 16) for x in block], hh.syllable(0xD7A3))
            self.assertIn("FONT_ASCENT 13", text)            # ASCII.SFT's 'H' ink ends at row 12

    def test_bdf_with_a_raw_english_companion(self):
        """--ascii reads what jamoset.py --eng reads: a Taebaek 12x24 .PFT (12,288 bytes, 2 bytes a row, step 12)."""
        with tempfile.TemporaryDirectory() as d:
            raw, eng, bdf = os.path.join(d, "GHAN24.PFT"), os.path.join(d, "GASCII24.PFT"), os.path.join(d, "o.bdf")
            wr(raw, b"".join(encode(pattern(i, 24, 24), 24, 24, False) for i in range(2350)))
            wr(eng, b"".join(encode(ascii_glyph(c, 16, 24), 16, 24, False) for c in range(256)))
            r = run(os.path.join(HERE, "hwpfont.py"), "bdf", raw, "--ascii", eng, "-o", bdf)
            self.assertIn("95 ASCII of 12x24", r.stdout)
            block = txt(bdf).split("STARTCHAR U+0041\n", 1)[1].split("ENDCHAR", 1)[0]
            self.assertIn("DWIDTH 12 0", block)
            self.assertIn("BBX 16 24", block)
            wr(eng, bytes(1000))
            r = run(os.path.join(HERE, "hwpfont.py"), "bdf", raw, "--ascii", eng, "-o", bdf, ok=False)
            self.assertIn("an English font has", r.stderr)

    def test_bdf_of_english_and_hanja(self):
        with tempfile.TemporaryDirectory() as d:
            eng, haj = os.path.join(d, "ASCII.PFT"), os.path.join(d, "HAJ16.FNT")
            wr(eng, hwp1(14, 24, 991, glyph=ascii_glyph))
            wr(haj, hwp3(2, 16, 16, 4888))
            r = run(os.path.join(HERE, "hwpfont.py"), "bdf", eng, "--face", 4, "-o", eng + ".bdf")
            self.assertIn("95 ASCII", r.stdout)
            r = run(os.path.join(HERE, "hwpfont.py"), "bdf", haj, "-o", haj + ".bdf")
            self.assertIn("4888 hanja", r.stdout)
            self.assertIn("STARTCHAR U+4F3D", txt(haj + ".bdf"))     # KS X 1001 CAA1 = 伽, the first hanja
            r = run(os.path.join(HERE, "hwpfont.py"), "info", haj)
            self.assertIn("HWP 3.0 FNT", r.stdout)

    def test_info_and_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.bin")
            wr(p, b"\1" * 5000)
            r = run(os.path.join(HERE, "hwpfont.py"), "info", p, ok=False)
            self.assertEqual(r.returncode, 1)
            self.assertIn("not an HWP", r.stderr)
            wr(p, hwp1(24, 24, 980))
            r = run(os.path.join(HERE, "hwpfont.py"), "info", p)
            self.assertIn("HWP 1.x", r.stdout)
            self.assertIn("7/2/3", r.stdout)


# sha256 of repr([pieces(cp) for every syllable]) per (table, face): pins HWP.EXE's selection tables (L/V/T_IDX, the
# classes, SEL, SETS) without font data. The values are those of the tables whose compositions equal the research
# renderer's on the real HWP 1.20 files (RealFiles below, 2026-11-23).
PIECES_SHA = {("sft", 0): "e0a6bc4ee45f10537ef655f45084557141c98f2774fce2278947dc365003735b",
              ("sft", 1): "1a8911fcf85ea55e8f6e632dfe2674b6f6e77c242560e6d315c4a37db2267b50",
              ("sft", 2): "9aee06c04718afa7c86bc2ff7bd8c26d258b4d958be0d19d3b60ee61d841b6e9",
              ("pft", 0): "20b206307a492ba88c12ee20939764923b44cb1597bcf7596621ab6d5ececd2c",
              ("pft", 1): "772b5408550b0381f6c479e7e4c01048e51a3ac1c7c4dc951ab2c7474ae6d201",
              ("pft", 2): "8d74cd3a1bb24a867d64ce9d0da5ce40484f996f4f9257d88fde0752a6f0367a"}


class ReviewFixes(unittest.TestCase):
    def test_selection_tables_are_pinned(self):
        for (table, face), want in PIECES_SHA.items():
            w, n = (16, 1193) if table == "sft" else (24, 980)
            h = hwpfont.Hwp1Hangul(hwpfont.read(hwp1(w, w, n, glyph=lambda i, a, b: [0] * b)), face)
            got = hashlib.sha256(repr([h.pieces(c) for c in range(0xAC00, 0xD7A4)]).encode()).hexdigest()
            self.assertEqual(got, want, (table, face))
        with self.assertRaisesRegex(hwpfont.HwpError, "not a Hangul syllable"):
            h.pieces(0x41)

    def test_short_and_lying_headers_are_clean_errors(self):
        for data in (hwp1(16, 16, 1193), hwp1(24, 24, 980), hwp3(1, 16, 16, 2710), hwp3(0, 12, 24, 147)):
            for n in list(range(0, 80)) + [len(data) - 1]:
                with self.assertRaises(hwpfont.HwpError):
                    hwpfont.read(data[:n])
                self.assertIsNone(hwpfont.sniff(data[:n], n))
            self.assertIsNotNone(hwpfont.sniff(data[:512], len(data)))
        self.assertIsNone(hwpfont.sniff(hwpfont.HWP1_MAGIC + bytes(12), 2048))     # the magic alone is not an HWP font
        self.assertIsNone(hwpfont.sniff(b"FNT\x01" + bytes(100), 4096))

    def test_hwp3_english_count(self):
        eng40 = hwpfont.read(hwp3(0, 20, 40, 96, count=147, glyph=ascii_glyph))   # ENG40_0: declares 147, holds 96
        self.assertIn("the header declares 147", eng40.describe())
        self.assertEqual(len(hwpfont.ascii_glyphs(eng40)), 95)
        with self.assertRaisesRegex(hwpfont.HwpError, "95 codes"):
            hwpfont.read(hwp3(0, 8, 16, 60, count=147))

    def test_bounded_read_and_name(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "big")
            wr(p, bytes(101))
            with self.assertRaisesRegex(hwpfont.HwpError, "larger than 100"):
                hwpfont.read_bounded(p, 100)
            self.assertEqual(len(hwpfont.read_bounded(p, 101)), 101)
            raw = os.path.join(d, "GHAN24.PFT")
            wr(raw, b"".join(encode(pattern(i, 24, 24), 24, 24, False) for i in range(2350)))
            r = run(os.path.join(HERE, "hwpfont.py"), "bdf", raw, "--name", "한글", "-o", p, ok=False)
            self.assertEqual(r.returncode, 2)

    def test_first_syllable_survives_mkfont_without_ascii(self):
        """A BDF without ASCII starts with a blank U+0020: FreeType's .notdef is the first glyph, and mkfont.py drops
        glyphs equal to it, so 가 would be lost (96MT.FNT lost it before this)."""
        with tempfile.TemporaryDirectory() as d:
            raw, bdf, tmp = os.path.join(d, "GHAN24.PFT"), os.path.join(d, "k.bdf"), os.path.join(d, "k.tmp")
            wr(raw, b"".join(encode(pattern(i, 24, 24), 24, 24, False) for i in range(2350)))
            run(os.path.join(HERE, "hwpfont.py"), "bdf", raw, "-o", bdf)
            self.assertLess(txt(bdf).index("STARTCHAR U+0020"), txt(bdf).index("STARTCHAR U+AC00"))
            run(os.path.join(HERE, "mkfont.py"), bdf, tmp, "--size", 24, "--bpp", 1, "--unicode", "ksx1001-hangul")
            sv = jamoset.parse_svfn(rd(tmp))
            self.assertEqual(sum(1 for cp in sv.glyphs if 0xAC00 <= cp <= 0xD7A3), 2350)
            self.assertEqual(sv.glyphs[0xAC00], encode(pattern(0, 24, 24), 24, 24, False))

    def test_jamoset_refusals_and_embolden_check(self):
        blank = set(jamoset.slots_of(8, 4, 4, 160, 248))
        def g(i, w, h):
            return [0] * h if i >= 2350 and (i - 2350) in blank else pattern(i, w, h)
        J = os.path.join(HERE, "jamoset.py")
        with tempfile.TemporaryDirectory() as d:
            sft, pft_eng, out = os.path.join(d, "H.SFT"), os.path.join(d, "ASCII.PFT"), os.path.join(d, "o.svf")
            wr(sft, hwp1(16, 16, 1193))
            wr(pft_eng, hwp1(14, 24, 991, glyph=ascii_glyph))
            r = run(J, "--layout", "hwp1", sft, "--bpp", 2, "-o", out, ok=False)
            self.assertEqual(r.returncode, 2)
            self.assertIn("1 bpp", r.stderr)
            r = run(J, "--layout", "hwp1", sft, "--eng", pft_eng, "-o", out, ok=False)
            self.assertIn("taller than the 16-row cell", r.stderr)
            fnt = os.path.join(d, "HAN16_0.FNT")
            wr(fnt, hwp3(1, 16, 16, 2710, glyph=g))
            r = run(J, "--layout", "844-hwp3", fnt, "--embolden", "--check", "-o", out)
            self.assertIn("identical to johab844.py", r.stdout)
            r = run(J, "--layout", "844-hwp3", fnt, "--eng", pft_eng, "-o", out, ok=False)
            self.assertIn("taller than the 16-row cell", r.stderr)


JOHAB_FONTS = os.environ.get("JOHAB_FONTS", os.path.join(HERE, "no-johab-fonts"))
HWP120 = os.path.join(JOHAB_FONTS, "printer/extracted/ia-HWP120.zip")
HWP30 = os.path.join(JOHAB_FONTS, "dos/extracted/hwp-30-dos__HWP30_DOS/HNCAPP/HDR30/FONT")
TB351 = os.path.join(JOHAB_FONTS, "dos/extracted/tb351__tb351/FNT")


def ks_hash(font, face=0):
    """sha256 of the 2,350 KS X 1001 syllables as hwpfont draws them (rows packed MSB first)."""
    bpr = (font.w + 7) // 8
    rows = hwpfont.syllables(font, face, "ks")
    return hashlib.sha256(b"".join(r.to_bytes(bpr, "big") for cp in sorted(rows) for r in
                                   [x << (bpr * 8 - font.w) for x in rows[cp]])).hexdigest()


class RealFiles(unittest.TestCase):
    """The real HWP 1.20, HWP 3.0 and Taebaek 3.5.1 files (proprietary, not in this repository): hashes only."""

    @unittest.skipUnless(os.path.exists(os.path.join(HWP120, "HANGUL1.PFT")), "JOHAB_FONTS does not name the HWP 1.20 tree")
    def test_hwp120(self):
        got = {}
        for name, face in (("HANGUL.SFT", 0), ("HANGUL.SFT", 1), ("HANGUL1.PFT", 1), ("HANGUL2.PFT", 2)):
            got[name, face] = ks_hash(hwpfont.read(rd(os.path.join(HWP120, name))), face)
        self.assertEqual(got, REAL_HWP120)

    @unittest.skipUnless(os.path.exists(os.path.join(HWP30, "HAN16_0.FNT")), "JOHAB_FONTS does not name the HWP 3.0 tree")
    def test_hwp30(self):
        got = {name: ks_hash(hwpfont.read(rd(os.path.join(HWP30, name)))) for name in ("HAN16_0.FNT", "HAN24_0.FNT")}
        self.assertEqual(got, REAL_HWP30)

    @unittest.skipUnless(os.path.exists(os.path.join(TB351, "GHAN24.PFT")), "JOHAB_FONTS does not name the Taebaek tree")
    def test_taebaek(self):
        self.assertEqual(ks_hash(hwpfont.read(rd(os.path.join(TB351, "GHAN24.PFT")))), REAL_TB351)


# sha256 of the 2,350 KS X 1001 syllables (ks_hash). The HWP 1.20 ones equal the research renderer's composition
# (johab-fonts tools/hwp1_fnt.py: all 11,172 syllables of the seven HANGUL files, three faces each, identical; 2026-11-23).
REAL_HWP120 = {("HANGUL.SFT", 0): "3ce073baa425ff00e1e560786381b456e1723d5021cfbf57ba9bd7a882f32511",
               ("HANGUL.SFT", 1): "6798c675266038ec87546c9e8fba9b86d3876ee974f145c47e6525e050481fd2",
               ("HANGUL1.PFT", 1): "25545c0cebe592ed0408f4001ceca667ba5df2032c04d1baa363e8259aeac2db",
               ("HANGUL2.PFT", 2): "6e2b32ce158113a075fd266abc42d0b5f7b59d8fa7afd650bcdfa7b1edcfa76f"}
REAL_HWP30 = {"HAN16_0.FNT": "a679e70f9480920be425cc34e1c5efd8d670e0493008df457797dbebad9cb4ed",
              "HAN24_0.FNT": "b9ef994b399fb35806c56840c5b4946b6d71521027143f620cb541e3d994f8ad"}
REAL_TB351 = "e48a53a3a42adbed3c86fbf937ae06778def5bff82e0853c32dd82eb75455e98"


if __name__ == "__main__":
    unittest.main()
