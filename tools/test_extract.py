#!/usr/bin/env python3
"""Tests of the extraction tools of docs/recipes.md ("Finding a font inside a program or data file", "OS/2 Korean fonts",
"A low-resolution face from a high-resolution bitmap font"): binscan.py, rawcarve.py, os2dbcs.py and svfscale.py, on
synthetic files built here (no font data).
  python3 -m unittest tools.test_extract
"""
import json
import os
import random
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bdfface  # noqa: E402
import binscan  # noqa: E402
import jamoset  # noqa: E402
import os2dbcs  # noqa: E402
import rawcarve  # noqa: E402
import svfscale  # noqa: E402


def wr(path, data):
    with open(path, "wb" if isinstance(data, bytes) else "w") as fh:
        fh.write(data)


def rd(path, n=-1):
    with open(path, "rb") as fh:
        return fh.read(n)


def run(*argv):
    r = subprocess.run([sys.executable] + [str(a) for a in argv], capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError("%s exit %d\n%s%s" % (argv[0], r.returncode, r.stdout, r.stderr))
    return r.stdout


def raw844():
    """A raw 8x4x4 font: slot i (not a set's slot 0) is a 16x16 glyph with a 2-row bar at row 1 + i % 13 and a column
    stroke at column i % 16."""
    out = bytearray()
    blank = set(jamoset.slots_of(8, 4, 4, 160, 248))
    for i in range(360):
        rows = [0] * 16
        if i not in blank:
            r = 1 + i % 13
            rows[r] = rows[r + 1] = 0x3FFC
            for y in range(2, 14):
                rows[y] |= 0x8000 >> (i % 16)
        out += b"".join(v.to_bytes(2, "big") for v in rows)
    return bytes(out)


def ascii8x16():
    """An 8x16 font of 256 glyphs: space blank, '_' at row 14, '-' at row 8, every other printable a box at rows 3-12."""
    out = bytearray(4096)
    for c in range(0x21, 0x7F):
        g = [0] * 16
        if c == 0x5F:
            g[14] = 0xFE
        elif c == 0x2D:
            g[8] = 0x7C
        else:
            g[3] = g[12] = 0x7E
            for y in range(4, 12):
                g[y] = 0x42 | (c & 0x18)
        out[c * 16:c * 16 + 16] = bytes(g)
    return bytes(out)


class Binscan(unittest.TestCase):
    def test_sets_and_ascii_inside_a_program(self):
        rnd = random.Random(7)
        junk = bytes(rnd.randrange(1, 256) for _ in range(301))
        font, eng = raw844(), ascii8x16()
        data = junk + font + junk + eng + junk
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "PROG.COM")
            wr(p, data)
            out = run(os.path.join(HERE, "binscan.py"), "sets", p)
            self.assertIn(f"offset {len(junk):#x} ", out.replace(",", " ") + " ")
            out = run(os.path.join(HERE, "binscan.py"), "ascii", p)
            self.assertIn(f"offset {2 * len(junk) + len(font):#x} ", out)
            out = run(os.path.join(HERE, "binscan.py"), "info", p)
            self.assertIn("DOS .COM image", out)
            png = os.path.join(d, "g.png")
            run(os.path.join(HERE, "binscan.py"), "render", p, "--offset", str(len(junk)), "--glyph", "16x16",
                "--count", "20", "--png", png)
            self.assertEqual(rd(png, 8), b"\x89PNG\r\n\x1a\n")

    def test_decode_orders(self):
        # one 16x16 glyph with pixel (x=9, y=3) set, in each storage order
        rows = bytearray(32)
        rows[3 * 2 + 1] = 0x40
        strips = bytearray(32)
        strips[16 + 3] = 0x40
        cols = bytearray(32)
        cols[9 * 2 + 0] = 0x10
        for order, data in (("rows", rows), ("strips", strips), ("cols", cols)):
            g = binscan.decode(bytes(data), 0, 16, 16, order)
            self.assertEqual([(x, y) for y in range(16) for x in range(16) if g[y][x]], [(9, 3)], order)


class Rawcarve(unittest.TestCase):
    def test_cut_and_eng(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "F.BIN")
            wr(p, b"xyz" + raw844() + ascii8x16()[:2048])
            out = os.path.join(d, "f.fnt")
            run(os.path.join(HERE, "rawcarve.py"), "cut", p, "--offset", "3", "--length", "11520", "-o", out)
            self.assertEqual(rd(out), raw844())
            eng = os.path.join(d, "e.raw")
            run(os.path.join(HERE, "rawcarve.py"), "eng", p, "--offset", str(3 + 11520), "-o", eng)
            e = rd(eng)
            self.assertEqual(len(e), 4096)
            self.assertEqual(e[:2048], ascii8x16()[:2048])
            self.assertEqual(e[2048:], bytes(2048))
            # the carved pieces build as any raw 8x4x4 font
            run(os.path.join(HERE, "jamoset.py"), "--layout", "844", out, "--eng", eng, "--check",
                "-o", os.path.join(d, "J.SVF"))

    def test_ks_grid_to_bdf(self):
        # a 128-per-row KS grid (the Korean VGA ROM layout), glyphs in 8-pixel strips: 가 (B0A1) and 힝 (C8FE)
        data = bytearray(16384 * 32)
        for lead, trail, row in ((0xB0, 0xA1, 2), (0xC8, 0xFE, 5)):
            idx = ((lead & 0x7F) << 7) | (trail & 0x7F)
            data[idx * 32 + row] = 0x80        # left strip: x = 0
            data[idx * 32 + 16 + row] = 0x01   # right strip: x = 15
        with tempfile.TemporaryDirectory() as d:
            p, b = os.path.join(d, "ks.rom"), os.path.join(d, "ks.bdf")
            wr(p, bytes(data))
            run(os.path.join(HERE, "rawcarve.py"), "bdf", p, "--glyph", "16x16", "--order", "strips",
                "--chars", "ks-hangul", "--grid", "0x80,0x80,128", "-o", b)
            face, glyphs = bdfface.read_bdf(b)
            self.assertEqual(sorted(glyphs), [0xAC00, 0xD79D])
            bw, bh, bx, by, rows, adv = glyphs[0xAC00]
            self.assertEqual(rows[2], 0x8001)
            self.assertEqual(sum(1 for r in rows if r), 1)

    def test_compose_spec_equals_844(self):
        """An 8x4x4 font described as a compose spec draws the syllables jamoset.py's 844 layout composes."""
        font = raw844()
        sets = {}
        for s in range(8):
            sets[f"i{s}"] = {"offset": (s * 20 + 1) * 32, "stride": 32}
        for s in range(4):
            sets[f"m{s}"] = {"offset": (160 + s * 22 + 1) * 32, "stride": 32}
            sets[f"f{s}"] = {"offset": (248 + s * 28 + 1) * 32, "stride": 32}
        med = lambda tc, kk: [[f"m{(0 if kk else 1) + 2 * tc}", v] for v in range(21)]  # noqa: E731
        spec = {"sets": sets,
                "initial": {"nofinal": [f"i{x}" for x in jamoset.I844_NOFIN],
                            "final": [f"i{x}" for x in jamoset.I844_FIN]},
                "medial": {"nofinal": med(0, False), "final": med(1, False),
                           "nofinal_kk": med(0, True), "final_kk": med(1, True)},
                "final": {"by_vowel": [f"f{x}" for x in jamoset.F844]}}
        c = rawcarve.Composer(font, spec)
        for cp in (0xAC00, 0xAC01, 0xACE0, 0xB000, 0xD7A3, 0xCE74, 0xD0C8):
            s = cp - 0xAC00
            L, V, T = s // 588, (s // 28) % 21, s % 28
            want = [[0] * 16 for _ in range(16)]
            idx = [L + 1 + 20 * (jamoset.I844_FIN if T else jamoset.I844_NOFIN)[V],
                   160 + 22 * ((0 if L in jamoset.KK else 1) + 2 * (1 if T else 0)) + V + 1]
            if T:
                idx.append(248 + 28 * jamoset.F844[V] + T)
            for i in idx:
                g = binscan.decode(font, i * 32, 16, 16)
                for y in range(16):
                    for x in range(16):
                        want[y][x] |= g[y][x]
            self.assertEqual(c.syllable(L, V, T), want, hex(cp))
        with tempfile.TemporaryDirectory() as d:
            p, sp, b = os.path.join(d, "F.COM"), os.path.join(d, "s.json"), os.path.join(d, "o.bdf")
            wr(p, font)
            wr(sp, json.dumps(spec))
            run(os.path.join(HERE, "rawcarve.py"), "compose", p, "--spec", sp, "--syllables", "all", "-o", b)
            self.assertEqual(len(bdfface.read_bdf(b)[1]), 11172)


def os2_font(glyphs, w=16, h=16):
    """A synthetic System DBCS file: 5-bit Huffman codes 1xxxx for the 16 nibbles, an identity context table."""
    bpg = (w + 7) // 8 * h
    d = bytearray(0x1A00)
    d[:16] = b"System DBCS 16  "
    struct.pack_into("<HHHHHHH", d, 0x10, 0x3B7, w, h, 1, bpg, 0, 1)
    struct.pack_into("<HBBBBBB", d, 0x80, 3, 0xA1, 0xAC, 0xB0, 0xC8, 0xCA, 0xFD)
    struct.pack_into("<HHHHHHH", d, 0xA0, 3, 256, 1383, 1666, 4015, 4110, 8997)
    for v in range(256):
        d[0xC0 + v] = (5 << 4) | ((v >> 3) & 15) if v & 0x80 else 0
    for c in range(2048):
        d[0x200 + c] = (((2 * c) & 15) << 4) | ((2 * c + 1) & 15)
    recs = bytearray()
    for g, data in sorted(glyphs.items()):
        bits = "".join("1" + format(n, "04b") for b in data for n in (b >> 4, b & 15))
        bits += "0" * (-len(bits) % 8)
        payload = int(bits, 2).to_bytes(len(bits) // 8, "big")
        rec = struct.pack("<HB", g, len(payload)) + payload
        if len(recs) % 512 + len(rec) > 512:
            recs += b"\xff" * (-len(recs) % 512)
        recs += rec
    return bytes(d + recs + b"\xff" * (-len(recs) % 512))


class Os2Dbcs(unittest.TestCase):
    def test_decode_and_table(self):
        rnd = random.Random(3)
        glyphs = {g: bytes(rnd.randrange(256) for _ in range(32)) for g in (256, 500, 760, 1000, 1250, 1383, 1666, 1667, 1900)}  # the reader takes a jump of
        # more than 300 glyph numbers for padding, as the real files never have one
        d = os2_font(glyphs)
        self.assertEqual(os2dbcs.decode(d), glyphs)
        with tempfile.TemporaryDirectory() as t:
            p, o, b = os.path.join(t, "ZN16.FNT"), os.path.join(t, "zn.bin"), os.path.join(t, "zn.bdf")
            wr(p, d)
            run(os.path.join(HERE, "os2dbcs.py"), "table", p, "-o", o)
            tab = rd(o)
            self.assertEqual(len(tab), (8998 - 256) * 32)
            self.assertEqual(tab[(1666 - 256) * 32:(1667 - 256) * 32], glyphs[1666])
            run(os.path.join(HERE, "rawcarve.py"), "bdf", o, "--glyph", "16x16", "--chars", "ks-hangul",
                "--grid", "0xA1,0xA1,94", "-o", b)
            self.assertEqual(sorted(bdfface.read_bdf(b)[1])[:2], [0xAC00, 0xAC01])


class Svfscale(unittest.TestCase):
    def test_box_filter_levels(self):
        """A 32 px glyph whose left 16 columns and rows 0-15 are inked, plus a 1-pixel-wide column at x = 20: at 16 px
        the block is 8x8 full pixels and the column a half-covered column (level 2 at 2 bpp; kept at 1 bpp, the share is exactly the threshold)."""
        rows = [[1 if (x < 16 and y < 16) or x == 20 else 0 for x in range(32)] for y in range(32)]
        glyphs = {0xAC00: rows}
        with tempfile.TemporaryDirectory() as d:
            b = os.path.join(d, "big.bdf")
            wr(b, rawcarve.bdf_text(glyphs, 32, 32, 28, "t"))
            for bpp in (1, 2):
                o = os.path.join(d, f"s{bpp}.svf")
                run(os.path.join(HERE, "svfscale.py"), b, "--size", "16", "--bpp", bpp, "--chars", "face", "-o", o)
                with open(o, "rb") as fh:
                    f = jamoset.parse_svfn(fh.read())
                self.assertEqual((f.cell_w, f.cell_h, f.ascent, f.bpp), (16, 16, 14, bpp))
                g = f.glyphs[0xAC00]
                pitch = (16 * bpp + 7) // 8

                def px(x, y):
                    v = int.from_bytes(g[y * pitch:(y + 1) * pitch], "big")
                    return v >> ((15 - x) * bpp) & ((1 << bpp) - 1)
                full = (1 << bpp) - 1
                self.assertEqual(px(0, 0), full)
                self.assertEqual(px(7, 7), full)
                self.assertEqual(px(8, 8), 0)
                self.assertEqual(px(10, 12), 1 if bpp == 1 else 2)
                if bpp == 1:
                    iou, dx, dy, exact, n = svfscale.overlap(o, o)
                    self.assertEqual((iou, dx, dy, exact, n), (1.0, 0, 0, 1, 1))  # share 0.5: kept at the 0.5 threshold


if __name__ == "__main__":
    unittest.main()
