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
            names[0 * 32 + 2 + 1] ^= 1                      # 가's top right cell changed
            wr(pre + ".names", bytes(names))
            self.assertIn("1 syllables differ, first U+AC00",
                          run(os.path.join(HERE, "msxfont.py"), "msx1-verify", pre, code=1))


if __name__ == "__main__":
    unittest.main()
