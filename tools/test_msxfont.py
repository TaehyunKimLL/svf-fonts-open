#!/usr/bin/env python3
"""Tests of tools/msxfont.py and `rawcarve.py bdf --chars map` on synthetic ROM images built here (no font data).
  python3 -m unittest tools.test_msxfont
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bdfface  # noqa: E402
import msxfont  # noqa: E402


def run(*argv, code=0):
    r = subprocess.run([sys.executable, "-I"] + [str(a) for a in argv], capture_output=True, text=True)
    if r.returncode != code:
        raise AssertionError("%s exit %d\n%s%s" % (argv[0], r.returncode, r.stdout, r.stderr))
    return r.stdout + r.stderr


def wr(path, data):
    with open(path, "wb") as fh:
        fh.write(data)


def control_rom(a_lists, b_lists):
    """A 64 KB U44 image whose control ROM (the last 16 KB, CPU 8000h) holds lists A and B: {lead: [trail, ...]},
    each list with a 0 sentinel first and a 0xFF sentinel last, and the 77 start-offset words."""
    c = bytearray(0x4000)
    for (words, base, _), lists in zip(msxfont.LISTS, (a_lists, b_lists)):
        trails = [0]
        offs = []
        for i in range(msxfont.LEADS):
            offs.append(len(trails))
            trails += lists.get(0x88 + i, [])
        offs.append(len(trails))
        trails.append(0xFF)
        for i, o in enumerate(offs):
            c[words - 0x8000 + 2 * i:words - 0x8000 + 2 * i + 2] = o.to_bytes(2, "little")
        c[base - 0x8000:base - 0x8000 + len(trails)] = bytes(trails)
    return bytes(0xC000) + bytes(c)


def rd(path):
    with open(path, "rb") as fh:
        return fh.read()


def cell_table():
    """A 256 x 8-byte table at 0x1B49 of a 32 KB BIOS: cell k has byte k in every row."""
    d = bytearray(0x8000)
    for k in range(256):
        d[0x1B49 + k * 8:0x1B49 + k * 8 + 8] = bytes([k]) * 8
    return bytes(d)


class KfnMap(unittest.TestCase):
    def test_lists_to_slots(self):
        # Johab: 가 = 8861, 각 = 8862, 힣 = D3BD (lead 0xD3, the last); 갉 = 886A in list B
        u44 = control_rom({0x88: [0x61, 0x62], 0xD3: [0xBD]}, {0x88: [0x6A]})
        m = msxfont.kfn_map(u44)
        self.assertEqual(m, {0xAC00: 0x582, 0xAC01: 0x583, 0xD7A3: 0x584, 0xAC09: 0x1142})
        self.assertEqual(msxfont.kfn_map(u44[0xC000:]), m)   # the 16 KB control ROM alone
        with self.assertRaises(msxfont.MsxError):
            msxfont.kfn_map(bytes(1000))
        bad = bytearray(u44)                                # list A's start offsets out of order
        at = 0xC000 + 0x97BF - 0x8000 + 2
        bad[at:at + 2] = (0xFFFF).to_bytes(2, "little")
        with self.assertRaisesRegex(msxfont.MsxError, "not a sorted list"):
            msxfont.kfn_map(bytes(bad))
        # a syllable in both lists keeps its list A slot
        self.assertEqual(msxfont.kfn_map(control_rom({0x88: [0x61]}, {0x88: [0x61]})), {0xAC00: 0x582})

    def test_map_to_bdf(self):
        u44 = control_rom({0x88: [0x61, 0x62]}, {})
        font = bytearray(8192 * 32)
        font[0x582 * 32] = 0x80                   # 가: one pixel at (0, 0)
        font[0x583 * 32 + 31] = 0x01              # 각: one pixel at (15, 15)
        with tempfile.TemporaryDirectory() as d:
            p, f, m, b = (os.path.join(d, n) for n in ("u44", "font.rom", "map.txt", "o.bdf"))
            wr(p, u44)
            wr(f, bytes(font))
            self.assertIn("2 syllables", run(os.path.join(HERE, "msxfont.py"), "kfn-map", p, "-o", m))
            with open(m) as fh:
                self.assertEqual(fh.read(), "1410 U+AC00\n1411 U+AC01\n")
            run(os.path.join(HERE, "rawcarve.py"), "bdf", f, "--glyph", "16x16", "--chars", "map", "--map", m, "-o", b)
            glyphs = bdfface.read_bdf(b)[1]
            self.assertEqual(sorted(glyphs), [0xAC00, 0xAC01])
            self.assertEqual(glyphs[0xAC00][4][0], 0x8000)
            self.assertEqual(glyphs[0xAC01][4][15], 0x0001)
            # comments (also non-ASCII), hex indices and blank glyphs
            wr(m, "# 가 각\n0x582 U+AC00  # 가\n\n0x584 U+AC02\n".encode())
            run(os.path.join(HERE, "rawcarve.py"), "bdf", f, "--glyph", "16x16", "--chars", "map", "--map", m, "-o", b)
            self.assertEqual(sorted(bdfface.read_bdf(b)[1]), [0xAC00])     # slot 0x584 is blank: left out
            # an index past the file is refused before anything is read; bad lines name the file and line
            for text, msg in ((b"99999999999 U+AC00\n", "past the 8192 whole glyphs"),
                              (b"1410 U+ZZZZ\n", "map.txt:1: expected GLYPH U+XXXX"),
                              (b"1410 U+110000\n", "out of range"),
                              (b"# nothing\n", "no mapping line")):
                wr(m, text)
                self.assertIn(msg, run(os.path.join(HERE, "rawcarve.py"), "bdf", f, "--glyph", "16x16",
                                       "--chars", "map", "--map", m, "-o", b, code=1))
            wr(m, b"1410 AC00\n")
            self.assertIn("GLYPH U+XXXX", run(os.path.join(HERE, "rawcarve.py"), "bdf", f, "--glyph", "16x16",
                                              "--chars", "map", "--map", m, "-o", b, code=1))
            self.assertIn("--map", run(os.path.join(HERE, "rawcarve.py"), "bdf", f, "--glyph", "16x16",
                                       "--chars", "map", "-o", b, code=1))


class Msx1(unittest.TestCase):
    def test_layout_cases(self):
        L = msxfont.layout
        self.assertEqual(L(0xAC00), [[0x86, 0x99], [0xFC, 0x0C]])          # 가: vertical, no final
        self.assertEqual(L(0xAC01), [[0x86, 0x99], [0x86, 0xFC]])          # 각
        self.assertEqual(L(0xAC03), [[0x86, 0x99], [0x86, 0x8F]])          # 갃: ㄱ + ㅅ
        self.assertEqual(L(0xACE0), [[0x86], [0xA1]])                      # 고: horizontal, no final
        self.assertEqual(L(0xACE1), [[0xA7], [0x86]])                      # 곡: merged ㄱ+ㅗ over ㄱ
        self.assertEqual(L(0xACE3), [[0xA7, 0xFC], [0x86, 0x8F]])          # 곣: a two-cell final
        self.assertEqual(L(0xD638), [[0x86 + 18], [0xA1]])                 # 호
        self.assertEqual(L(0xD639), [[0x07], [0x86]])                      # 혹: ㅎ+ㅗ past 0xFB, at 0x07
        self.assertEqual(L(0xACFC), [[0x86, 0x99], [0xA1, 0x0C]])          # 과: compound, no final
        self.assertEqual(L(0xACFD), [[0xA7, 0x99], [0x86, 0xFC]])          # 곽
        self.assertEqual(L(0xC758), [[0x86 + 11, 0xA6], [0xA5, 0x0C]])     # 의

    def test_layout_refuses_a_non_syllable(self):
        for cp in (0xABFF, 0xD7A4, 0x41):
            with self.assertRaises(msxfont.MsxError):
                msxfont.layout(cp)

    def test_msx1_refusals(self):
        with tempfile.TemporaryDirectory() as d:
            p, b = os.path.join(d, "bios.rom"), os.path.join(d, "o.bdf")
            wr(p, cell_table()[:0x1B49 + 1000])
            self.assertIn("no 256 x 8-byte table", run(os.path.join(HERE, "msxfont.py"), "msx1", p, "-o", b, code=1))
            wr(p, cell_table())
            self.assertIn("--ascii-top is 0..8", run(os.path.join(HERE, "msxfont.py"), "msx1", p, "--ascii-top", "9",
                                                    "-o", b, code=1))
            self.assertIn("--ascent is 0..16", run(os.path.join(HERE, "msxfont.py"), "msx1", p, "--ascent", "17",
                                                  "-o", b, code=1))
            big = os.path.join(d, "big.rom")
            with open(big, "wb") as fh:
                fh.truncate(0x10001)
            self.assertIn("more than the 65536", run(os.path.join(HERE, "msxfont.py"), "kfn-map", big, "-o", b,
                                                     code=1))

    def test_bdf_from_cells(self):
        with tempfile.TemporaryDirectory() as d:
            p, b = os.path.join(d, "bios.rom"), os.path.join(d, "o.bdf")
            wr(p, cell_table())
            out = run(os.path.join(HERE, "msxfont.py"), "msx1", p, "-o", b)
            self.assertIn("11172 syllables (1615 8x16, 9557 16x16) + 95 ASCII", out)
            face, glyphs = bdfface.read_bdf(b)
            self.assertEqual(len(glyphs), 11172 + 95)
            # 가: rows 0-7 = cells 86 | 99, rows 8-15 = FC | 0C (each row of a cell is its own code)
            rows = glyphs[0xAC00][4]
            self.assertEqual(rows[0], 0x8699)
            self.assertEqual(rows[8], 0xFC0C)
            self.assertEqual(glyphs[0xACE0][0], 8)        # 고 is one column wide
            self.assertEqual(glyphs[0xACE0][5], 8)        # and advances 8
            self.assertEqual(glyphs[0x41][4][8:], [0x41] * 8)

    def test_verify_against_a_harvest(self):
        cps = list(range(0xAC00, 0xAC00 + 80))            # two screens
        names = bytearray()
        for b in range(2):
            nt = bytearray([0x20]) * 768
            for k, cp in enumerate(cps[b * 77:(b + 1) * 77]):
                cx, cy = (k % 7) * 4 + 2, (k // 7) * 2
                for j, row in enumerate(msxfont.layout(cp)):
                    nt[(cy + j) * 32 + cx:(cy + j) * 32 + cx + len(row)] = bytes(row)
            names += nt
        bios = cell_table()
        pat = bytearray(bios[0x1B49:0x1B49 + 2048])
        pat[0xFF * 8] = 0x00                               # the cursor cell
        with tempfile.TemporaryDirectory() as d:
            pre = os.path.join(d, "h")
            wr(pre + ".names", bytes(names))
            wr(pre + ".patterns", bytes(pat))
            wr(pre + ".index", "".join("%04X\n" % c for c in cps).encode())
            wr(os.path.join(d, "bios.rom"), bios)
            out = run(os.path.join(HERE, "msxfont.py"), "msx1-verify", pre, "--bios", os.path.join(d, "bios.rom"))
            self.assertIn("80 of 80 syllables identical", out)
            self.assertIn("255 of 256 cells identical (differ: 0xff)", out)
            # input errors: an empty or non-syllable index, short names, a short pattern table, a wrong BIOS
            bios_arg = ["--bios", os.path.join(d, "bios.rom")]
            for files, args, msg in (({".index": b""}, [], "no syllable"),
                                     ({".index": b"0041\n"}, [], "U+0041 is not a Hangul syllable"),
                                     ({".index": b"zz\n"}, [], "one hex code point a line"),
                                     ({".names": bytes(names[:768])}, [], "short of 80 syllables"),
                                     ({".patterns": bytes(pat[:1024])}, bios_arg, "not the 2,048-byte pattern table")):
                saved = {k: rd(pre + k) for k in files}
                for k, v in files.items():
                    wr(pre + k, v)
                self.assertIn(msg, run(os.path.join(HERE, "msxfont.py"), "msx1-verify", pre, *args, code=1))
                for k, v in saved.items():
                    wr(pre + k, v)
            wr(os.path.join(d, "other.rom"), bytes(0x8000))
            self.assertIn("cells other than the cursor", run(os.path.join(HERE, "msxfont.py"), "msx1-verify", pre,
                                                             "--bios", os.path.join(d, "other.rom"), code=1))
            names[0 * 32 + 2 + 1] ^= 1                      # 가's top right cell changed
            wr(pre + ".names", bytes(names))
            self.assertIn("1 syllables differ, first U+AC00",
                          run(os.path.join(HERE, "msxfont.py"), "msx1-verify", pre, code=1))


if __name__ == "__main__":
    unittest.main()
