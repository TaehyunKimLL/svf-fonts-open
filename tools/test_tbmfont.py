#!/usr/bin/env python3
"""Tests of tools/tbmfont.py, the TBM part of docs/recipes/windows.md, tools/doc_figures_windows.py and
tools/doc_figures_hbios.py on synthetic TBM files and a synthetic HBIOS disk built here (no font data).
  python3 -m unittest tools.test_tbmfont
"""
import os
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jamoset  # noqa: E402
import tbmfont  # noqa: E402


def run(*argv, code=0):
    r = subprocess.run([sys.executable, "-I"] + [str(a) for a in argv], capture_output=True, text=True)
    if r.returncode != code:
        raise AssertionError("%s exit %d\n%s%s" % (argv[0], r.returncode, r.stdout, r.stderr))
    return r.stdout + r.stderr


def glyph(i, w, h):
    """Rows of glyph @p i (w x h, MSB left): a top bar, a left bar, and i's low bits in the middle row; ink = 1."""
    rb = (w + 7) // 8
    full = (1 << w) - 1
    rows = []
    for y in range(h):
        v = full if y == 1 else (1 << (w - 1))
        if y == h // 2:
            v |= (i * 2 + 1) & full
        rows.append(v << (rb * 8 - w))
    return b"".join(v.to_bytes(rb, "big") for v in rows)


def tbm(size, half=None, range_bytes=4096, trailing=0, counts=(128, 8366)):
    """A TBM file of @p size x @p size double-byte glyphs (and half-width single-byte ones), data inverted, cut into
    ranges of at most @p range_bytes, with the 7-byte glyph table, and @p trailing blank bytes after the data."""
    half = half or size // 2
    sizes = [(half, size)] * counts[0] + [(size, size)] * counts[1]
    datas = [bytes(255 - b for b in glyph(i, w, h)) for i, (w, h) in enumerate(sizes)]
    ranges, entries, cur = [], [], b""
    for i, d in enumerate(datas):
        if len(cur) + len(d) > range_bytes:
            ranges.append(cur)
            cur = b""
        entries.append((len(ranges), len(cur), len(d), sizes[i][0]))
        cur += d
    ranges.append(cur)
    head = 0x26 + 16 * len(ranges) + 7 * len(entries)
    out = bytearray(tbmfont.SIGNATURE + struct.pack("<HHH", size, size, len(ranges)))
    at = head
    for r in ranges:
        out += struct.pack("<IHH", at, len(r), len(r)) + bytes(8)
        at += len(r)
    for r, off, n, w in entries:
        out += struct.pack("<HHHB", r, off, n, w)
    for r in ranges:
        out += r
    return bytes(out) + b"\xff" * trailing


def wr(path, data):
    with open(path, "wb") as fh:
        fh.write(data)


class Parse(unittest.TestCase):
    def test_layout(self):
        t = tbmfont.parse(tbm(16, trailing=32))
        self.assertEqual((t["width"], t["height"]), (16, 16))
        self.assertEqual(len(t["glyphs"]), 8494)
        self.assertEqual(t["size"] - t["end"], 32)
        self.assertEqual(tbmfont.runs(t["glyphs"]),
                         [(0, 128, 8, 16, t["data"]), (128, 8366, 16, 16, t["data"] + 128 * 16)])
        b = tbmfont.blocks(t)
        self.assertEqual(b["ascii"], (t["data"], 128))
        self.assertEqual(b["symbols"], (t["data"] + 2048, 1128))
        self.assertEqual(b["hangul"], (t["data"] + 2048 + 1128 * 32, 2350))
        self.assertEqual(b["hanja"], (t["data"] + 2048 + 3478 * 32, 4888))

    def test_20px_odd_bytes(self):
        t = tbmfont.parse(tbm(20, half=10, range_bytes=4080))
        self.assertEqual(tbmfont.runs(t["glyphs"])[1][1:4], (8366, 20, 20))
        self.assertEqual(t["glyphs"][128][3], 60)

    def test_other_count_has_no_blocks(self):
        t = tbmfont.parse(tbm(12, counts=(128, 100)))
        self.assertEqual(tbmfont.blocks(t), {})

    def test_refusals(self):
        good = bytearray(tbm(12, counts=(4, 4)))
        with self.assertRaisesRegex(tbmfont.TbmError, "signature"):
            tbmfont.parse(b"x" + bytes(good[1:]))
        bad = bytearray(good)
        struct.pack_into("<H", bad, 0x26 + 6, 1)      # the range's second size
        with self.assertRaisesRegex(tbmfont.TbmError, "differ"):
            tbmfont.parse(bytes(bad))
        bad = bytearray(good)
        struct.pack_into("<I", bad, 0x26, len(good))  # the range past the end
        with self.assertRaisesRegex(tbmfont.TbmError, "past the end"):
            tbmfont.parse(bytes(bad))
        t = 0x26 + 16
        bad = bytearray(good)
        struct.pack_into("<H", bad, t + 7 + 2, 0)     # glyph 1 at offset 0 again
        with self.assertRaisesRegex(tbmfont.TbmError, "do not follow"):
            tbmfont.parse(bytes(bad))

    def test_map(self):
        lines = tbmfont.map_lines(["symbols"])
        self.assertEqual(lines[0], "0 U+3000")
        self.assertEqual(len(lines), 986 + 1)         # the assigned symbols of rows A1-AC (A1A9 = U+00AD included)
        h = tbmfont.map_lines(["hangul"])
        self.assertEqual((h[0], h[-1], len(h)), ("0 U+AC00", "2349 U+D79D", 2350))


class Recipe(unittest.TestCase):
    def test_tbm_face(self):
        """The commands of docs/recipes/windows.md on a synthetic 16 px TBM: every syllable and the ASCII come out
        with the glyph the file stores at its slot."""
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "BT16.TBM")
            wr(src, tbm(16))
            info = run("tools/tbmfont.py", "info", src)
            self.assertIn("hangul: offset", info)
            t = tbmfont.parse(tbm(16))
            b = tbmfont.blocks(t)
            ks = os.path.join(d, "ks.txt")
            with open(ks, "w", encoding="utf-8") as fh:
                fh.write("".join(chr(int(line.split("U+")[1], 16)) for line in tbmfont.map_lines(["hangul"])))
            run("tools/rawcarve.py", "bdf", src, "--offset", hex(b["ascii"][0]), "--glyph", "8x16", "--invert",
                "--chars", "ascii", "--count", "128", "-o", os.path.join(d, "a.bdf"))
            out = run("tools/rawcarve.py", "bdf", src, "--offset", hex(b["hangul"][0]), "--glyph", "16x16", "--invert",
                      "--chars", "ks-hangul", "--dense", "-o", os.path.join(d, "h.bdf"))
            self.assertIn("2350 glyphs (2350 Hangul syllables)", out)
            run("tools/tbmfont.py", "map", "-o", os.path.join(d, "all.map"))
            out = run("tools/rawcarve.py", "bdf", src, "--offset", hex(b["symbols"][0]), "--glyph", "16x16",
                      "--invert", "--chars", "map", "--map", os.path.join(d, "all.map"), "-o", os.path.join(d, "k.bdf"))
            self.assertIn("(2350 Hangul syllables)", out)
            face = os.path.join(d, "BT16.SVF")
            run("tools/bdfface.py", "--hangul", os.path.join(d, "h.bdf"), "--ascii", os.path.join(d, "a.bdf"),
                "--cell", "16x16", "--chars-from", ks, "-o", face)
            with open(face, "rb") as fh:
                f = jamoset.parse_svfn(fh.read())
            self.assertEqual(f.glyphs[0xAC00], glyph(128 + 1128, 16, 16))
            self.assertEqual(f.glyphs[0xD79D], glyph(128 + 1128 + 2349, 16, 16))
            self.assertEqual(sum(1 for cp in f.glyphs if 0xAC00 <= cp <= 0xD7A3), 2350)
            a, g = f.glyphs[0x41], glyph(0x41, 8, 16)
            self.assertEqual([a[2 * y] for y in range(16)], list(g))   # 8 px wide in the 16 px cell's left byte


class Figures(unittest.TestCase):
    def test_check_round_trip(self):
        """doc_figures_windows.py writes an image for a synthetic BT16 and --check then passes; a changed file fails."""
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow")
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "BT16.TBM")
            wr(src, tbm(16))
            out = os.path.join(d, "png")
            run("tools/doc_figures_windows.py", "--bt16", src, "--out", out)
            png = os.path.join(out, "bt16.png")
            with open(png, "rb") as fh:
                self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")
            self.assertIn("check: ok", run("tools/doc_figures_windows.py", "--bt16", src, "--out", out, "--check"))
            with open(png, "ab") as fh:
                fh.write(b"x")
            run("tools/doc_figures_windows.py", "--bt16", src, "--out", out, "--check", code=1)


class HbiosFigures(unittest.TestCase):
    def test_check_round_trip(self):
        """doc_figures_hbios.py on a synthetic HBIOS disk: four images, --check passes, a changed one fails."""
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow")
        from test_recipes import eng_8x16, raw_johab
        blank = {0, 20, 40, 60, 80, 100, 120, 140, 160, 182, 204, 226, 248, 276, 304, 332}   # slot 0 of every set
        j16 = raw_johab(16, 360, blank)
        j24 = raw_johab(24, 360, blank)
        cell30 = b"".join(bytes(9) + j24[i * 72:(i + 1) * 72] + bytes(9) for i in range(360))        # rows 3-26 of 30
        syl = b"".join(bytes(9) + glyph(i, 24, 24) + bytes(9) for i in range(2350))
        eng = eng_8x16()
        eng24 = b"".join(bytes(6) + glyph(c, 16, 24) + bytes(6) for c in range(256))
        sym16 = b"".join(glyph(i, 16, 16) for i in range(6016))
        sym24 = b"".join(bytes(9) + glyph(i, 24, 24) + bytes(9) for i in range(6016))
        with tempfile.TemporaryDirectory() as d:
            for name, data in (("$KGOZN16.FNT", j16), ("$KMYZN16.FNT", j16), ("$KMYZN24.FNT", cell30 + syl),
                               ("$KSAHN16.FNT", eng), ("$KROHN16.FNT", eng), ("$KROHN24.FNT", eng24),
                               ("$KSPHJ16.FNT", sym16), ("$KSPHJ24.FNT", sym24)):
                wr(os.path.join(d, name), data)
            self.assertEqual(len(cell30 + syl), 243900)
            out = os.path.join(d, "png")
            log = run("tools/doc_figures_hbios.py", "--disk", d, "--out", out)
            self.assertEqual(sorted(os.listdir(out)), ["hbios-gothic16.png", "hbios-myeongjo16.png",
                                                       "hbios-myeongjo24-precomposed.png", "hbios-myeongjo24.png"], log)
            self.assertIn("check: ok", run("tools/doc_figures_hbios.py", "--disk", d, "--out", out, "--check"))
            with open(os.path.join(out, "hbios-gothic16.png"), "ab") as fh:
                fh.write(b"x")
            run("tools/doc_figures_hbios.py", "--disk", d, "--out", out, "--check", code=1)


if __name__ == "__main__":
    unittest.main()
