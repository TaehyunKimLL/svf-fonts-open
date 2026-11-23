#!/usr/bin/env python3
"""Tests of the ROM-tile paths of docs/recipes.md ("Korean font ROMs in MAME sets"): inverted fonts (binscan.py /
rawcarve.py --invert), multi-bit tiles (--gfx, --bg), ROM regions (rawcarve.py region), 1 bpp ink maps (rawcarve.py
ink), 16-wide English fonts (rawcarve.py eng --width 16, jamoset.py --eng / --eng-advance) and exact jamo sets from a
compose spec (jamoset.py --layout spec, the built-in spc1500 spec), on synthetic files built here (no ROM or font data).

The real-ROM checks run only when MAME_ROMS names a folder of unpacked MAME 0.289 sets (<set>/<file>, e.g.
MAME_ROMS=/path/to/mame-sets); they compare hashes, and no ROM byte is in this repository.
  python3 -m unittest tools.test_tiles
"""
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bdfface  # noqa: E402
import binscan  # noqa: E402
import jamoset  # noqa: E402
import rawcarve  # noqa: E402
from test_extract import ascii8x16, raw844  # noqa: E402


def wr(path, data):
    with open(path, "wb" if isinstance(data, bytes) else "w") as fh:
        fh.write(data)


def rd(path):
    with open(path, "rb") as fh:
        return fh.read()


def run(*argv):
    r = subprocess.run([sys.executable] + [str(a) for a in argv], capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError("%s exit %d\n%s%s" % (argv[0], r.returncode, r.stdout, r.stderr))
    return r.stdout


def _cap_memory():
    """A refused input must be refused before it allocates: the child gets 1 GiB of address space (POSIX)."""
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    except (ImportError, ValueError, OSError):
        pass


def fails(*argv):
    """(exit code, stderr) of a command expected to fail, run with capped memory and a 120 s timeout."""
    r = subprocess.run([sys.executable] + [str(a) for a in argv], capture_output=True, text=True, timeout=120,
                       preexec_fn=_cap_memory if os.name == "posix" else None)
    return r.returncode, r.stderr


BS, RC, JS = (os.path.join(HERE, n) for n in ("binscan.py", "rawcarve.py", "jamoset.py"))


def bits(data, off, w, h):
    """Row-major 1 bpp glyph at @p off as rows of 0/1 (the reference reading)."""
    return binscan.decode(data, off, w, h)


def random_glyphs(n, w=16, h=16, seed=1):
    """@p n glyphs of w x h: an outline box and random ink inside (every glyph inked, none alike)."""
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        g = [[0] * w for _ in range(h)]
        for y in range(2, h - 2):
            for x in range(1, w - 3):
                g[y][x] = 1 if (y in (2, h - 3) or x in (1, w - 4) or rnd.random() < 0.3) else 0
        out.append(g)
    return out


def packed4(glyphs, lsb, bg=15, seed=2):
    """16x16 4 bpp packed tiles (128 bytes each) of @p glyphs: ink pixels a random pen other than @p bg, paper @p bg.
    @p lsb: the first pixel of a byte in its low nibble (MAME gfx_16x16x4_packed_lsb), else the high nibble."""
    rnd = random.Random(seed)
    out = bytearray()
    for g in glyphs:
        for y in range(16):
            for x in range(0, 16, 2):
                p = [rnd.choice([v for v in range(16) if v != bg]) if g[y][x + k] else bg for k in (0, 1)]
                out.append((p[1] << 4 | p[0]) if lsb else (p[0] << 4 | p[1]))
    return bytes(out)


# Date Quiz Go Go's sprite layout (MAME dataeast/tumbleb.cpp tlayout), as the driver writes it
TLAYOUT = "planes=RGN_FRAC(1,2)+8,RGN_FRAC(1,2)+0,8,0;x=STEP8(16*8*2,1),STEP8(0,1);y=STEP16(0,8*2);inc=64*8"


def tlayout_region(glyphs, seed=3):
    """The region the tumbleb tlayout reads, built by hand: tile t is 64 bytes in each half of the region; in a half,
    row y of the left 8 pixels is bytes 32 + 2y (pen bit 1 / bit 3) and 33 + 2y (bit 0 / bit 2), the right 8 pixels
    bytes 2y and 2y + 1; pen bits 3 and 2 are in the second half. Ink pixels have a random non-zero pen."""
    rnd = random.Random(seed)
    n = len(glyphs)
    reg = bytearray(n * 128)
    half = n * 64
    for t, g in enumerate(glyphs):
        for y in range(16):
            for x in range(16):
                if not g[y][x]:
                    continue
                pen = rnd.randrange(1, 16)
                byte = t * 64 + (32 if x < 8 else 0) + 2 * y
                mask = 0x80 >> (x % 8)
                # planes {half+8, half+0, 8, 0}: plane 0 (pen bit 3) is bit offset half*8 + 8, byte + 1 of the 2nd half
                if pen & 8:
                    reg[half + byte + 1] |= mask
                if pen & 4:
                    reg[half + byte] |= mask
                if pen & 2:
                    reg[byte + 1] |= mask
                if pen & 1:
                    reg[byte] |= mask
    return bytes(reg)


class Invert(unittest.TestCase):
    def test_inverted_font_reads_as_the_plain_one(self):
        font, eng = raw844(), ascii8x16()
        inv = bytes(b ^ 0xFF for b in font)
        einv = bytes(b ^ 0xFF for b in eng)
        rnd = random.Random(4)
        junk = bytes(rnd.randrange(1, 255) for _ in range(301))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "ROM.BIN")
            wr(p, junk + inv + junk + einv)
            out = run(BS, "sets", p, "--invert")
            self.assertIn(f"{len(junk):#x}", out.split("\n", 1)[1])
            self.assertIn("none", run(BS, "sets", p))  # without --invert the blank slots are 0xFF: nothing
            self.assertIn(f"offset {2 * len(junk) + len(font):#x} ", run(BS, "ascii", p, "--invert"))
            # render, cut to rows (ink), eng: the same glyphs as the plain font
            plain = os.path.join(d, "PLAIN.BIN")
            wr(plain, font)
            t1 = run(BS, "render", p, "--offset", len(junk), "--glyph", "16x16", "--count", "8", "--invert")
            t2 = run(BS, "render", plain, "--offset", 0, "--glyph", "16x16", "--count", "8")
            self.assertEqual([ln for ln in t1.splitlines() if not ln.startswith("0x")][2:],
                             [ln for ln in t2.splitlines() if not ln.startswith("0x")][2:])
            ink = os.path.join(d, "ink.fnt")
            run(RC, "ink", p, "--offset", len(junk), "--glyph", "16x16", "--count", 360, "--invert", "-o", ink)
            self.assertEqual(rd(ink), font)
            e = os.path.join(d, "e.raw")
            run(RC, "eng", p, "--offset", 2 * len(junk) + len(font), "--invert", "-o", e)
            self.assertEqual(rd(e), eng)
            b1, b2 = os.path.join(d, "a1.bdf"), os.path.join(d, "a2.bdf")
            run(RC, "bdf", p, "--offset", 2 * len(junk) + len(font), "--glyph", "8x16", "--chars", "ascii", "--invert",
                "-o", b1)
            wr(os.path.join(d, "E.BIN"), eng)
            run(RC, "bdf", os.path.join(d, "E.BIN"), "--glyph", "8x16", "--chars", "ascii", "-o", b2)
            self.assertEqual(bdfface.read_bdf(b1)[1], bdfface.read_bdf(b2)[1])

    def test_compose_invert_spec_and_flag(self):
        """An inverted font composes like the plain one, by the spec's "invert" and by --invert (pieces and --eng)."""
        font = raw844()
        inv = bytes(b ^ 0xFF for b in font)
        spec = spec_844()
        plain = rawcarve.Composer(font, spec)
        by_spec = rawcarve.Composer(inv, dict(spec, invert=True))
        by_flag = rawcarve.Composer(inv, spec, invert=True)
        per_set = rawcarve.Composer(inv, dict(spec, sets={k: dict(v, invert=True) for k, v in spec["sets"].items()}))
        for cp in (0xAC00, 0xAC01, 0xB000, 0xD7A3, 0xCE74):
            want = plain.syllable(*jamoset.decompose(cp))
            for c in (by_spec, by_flag, per_set):
                self.assertEqual(c.syllable(*jamoset.decompose(cp)), want, hex(cp))
        self.assertNotEqual(rawcarve.Composer(inv, spec).syllable(0, 0, 0), plain.syllable(0, 0, 0))
        # a set's own "invert": false wins over --invert (the flag's help says so)
        keep = dict(spec, sets={k: dict(v, invert=False) for k, v in spec["sets"].items()})
        self.assertEqual(rawcarve.Composer(font, keep, invert=True).syllable(0, 0, 0), plain.syllable(0, 0, 0))
        with tempfile.TemporaryDirectory() as d:
            p, sp = os.path.join(d, "F.BIN"), os.path.join(d, "s.json")
            wr(p, inv + bytes(b ^ 0xFF for b in ascii8x16()))
            wr(sp, json.dumps(spec))
            b = os.path.join(d, "o.bdf")
            run(RC, "compose", p, "--spec", sp, "--invert", "--eng", p, "--eng-offset", len(font), "-o", b)
            g = bdfface.read_bdf(b)[1]
            self.assertEqual(g[0x41][4], list(ascii8x16()[0x41 * 16:0x42 * 16]))


def bits_ints(data, off):
    """The 16x16 row-major glyph at @p off as 16 row ints (MSB = the left pixel)."""
    return [int.from_bytes(data[off + 2 * y:off + 2 * y + 2], "big") for y in range(16)]


def spec_844():
    """The 8x4x4 rule of raw844() as a compose spec (two lead classes through the *_kk tables)."""
    sets = {}
    for s in range(8):
        sets[f"i{s}"] = {"offset": (s * 20 + 1) * 32, "stride": 32}
    for s in range(4):
        sets[f"m{s}"] = {"offset": (160 + s * 22 + 1) * 32, "stride": 32}
        sets[f"f{s}"] = {"offset": (248 + s * 28 + 1) * 32, "stride": 32}
    med = lambda tc, kk: [[f"m{(0 if kk else 1) + 2 * tc}", v] for v in range(21)]  # noqa: E731
    return {"sets": sets,
            "initial": {"nofinal": [f"i{x}" for x in jamoset.I844_NOFIN], "final": [f"i{x}" for x in jamoset.I844_FIN]},
            "medial": {"nofinal": med(0, False), "final": med(1, False), "nofinal_kk": med(0, True),
                       "final_kk": med(1, True)},
            "final": {"by_vowel": [f"f{x}" for x in jamoset.F844]}}


class Gfx(unittest.TestCase):
    def test_packed_lsb_and_msb(self):
        glyphs = random_glyphs(40)
        for lsb in (True, False):
            data = packed4(glyphs, lsb)
            g = binscan.parse_gfx(f"16x16x4_packed_{'lsb' if lsb else 'msb'}", len(data), bg=15)
            self.assertEqual((g.w, g.h, g.stride), (16, 16, 128))
            for t in (0, 1, 39):
                self.assertEqual(binscan.decode(data, t * 128, 16, 16, gfx=g), glyphs[t], (lsb, t))
            other = binscan.parse_gfx(f"16x16x4_packed_{'msb' if lsb else 'lsb'}", len(data), bg=15)
            self.assertNotEqual(binscan.decode(data, 0, 16, 16, gfx=other), glyphs[0])
            # the default background pen 0 reads paper (pen 15) as ink: not the glyph
            self.assertNotEqual(binscan.decode(data, 0, 16, 16, gfx=binscan.parse_gfx("16x16x4_packed_lsb", len(data))),
                                glyphs[0])
        # plane 0 is the pen's high bit: with background pen 1, pen 8 (plane 0 alone) is ink and pen 1 is not
        two = bytes([0x81] + [0x11] * 127)  # packed_lsb: pixel 0 pen 1, pixel 1 pen 8, the rest pen 1
        g1 = binscan.parse_gfx("16x16x4_packed_lsb", 128, bg=1)
        self.assertEqual([x for x, v in enumerate(binscan.decode(two, 0, 16, 16, gfx=g1)[0]) if v], [1])
        # --fg: only the listed pens are ink (pen 8 here), the outline pen 1 is not
        gf = binscan.parse_gfx("16x16x4_packed_lsb", 128, fg=[8])
        self.assertEqual([x for x, v in enumerate(binscan.decode(two, 0, 16, 16, gfx=gf)[0]) if v], [1])
        gf2 = binscan.parse_gfx("16x16x4_packed_lsb", 128, fg=[1, 8])
        self.assertEqual(sum(binscan.decode(two, 0, 16, 16, gfx=gf2)[0]), 16)
        # the low nibble is the first pixel of a byte (packed_lsb)
        one = bytearray([0xFF] * 128)
        one[0] = 0xF0  # pixel 0 pen 0, pixel 1 pen 15
        g = binscan.parse_gfx("16x16x4_packed_lsb", 128, bg=15)
        self.assertEqual([x for x, v in enumerate(binscan.decode(bytes(one), 0, 16, 16, gfx=g)[0]) if v], [0])

    def test_packed_cli_ink_runs_render(self):
        font = raw844()  # glyph-like strokes (runs looks for those), slots 1..48
        glyphs = [bits(font, i * 32, 16, 16) for i in range(1, 49)]
        data = bytes(range(256)) * 8 + packed4(glyphs, True)  # 2,048 bytes of other data first
        want = b"".join(rawcarve.pack_rows(g, 16) for g in glyphs)
        with tempfile.TemporaryDirectory() as d:
            p, o = os.path.join(d, "OBJ.BIN"), os.path.join(d, "ink.bin")
            wr(p, data)
            run(RC, "ink", p, "--offset", 2048, "--gfx", "16x16x4_packed_lsb", "--bg", 15, "-o", o)
            self.assertEqual(rd(o), want)
            out = run(BS, "runs", p, "--gfx", "16x16x4_packed_lsb", "--bg", 15, "--min", 40)
            self.assertIn("offset 0x800 (2048): 48 glyphs", out)
            t = run(BS, "render", p, "--offset", 2048, "--gfx", "16x16x4_packed_lsb", "--bg", 15, "--count", 1)
            self.assertEqual(t.splitlines()[2:18], ["".join("#" if v else "." for v in r) for r in glyphs[0]])
            b = os.path.join(d, "a.bdf")
            run(RC, "bdf", p, "--offset", 2048, "--gfx", "16x16x4_packed_lsb", "--bg", 15, "--chars", "ascii",
                "--first", 0x41, "--count", 3, "-o", b)
            got = bdfface.read_bdf(b)[1][0x42][4]
            self.assertEqual(got, [int("".join(map(str, r)), 2) for r in glyphs[1]])

    def test_mame_layout_string(self):
        """The tumbleb sprite layout, copied from the driver, against a region built by hand."""
        glyphs = random_glyphs(20, seed=9)
        reg = tlayout_region(glyphs)
        g = binscan.parse_gfx(TLAYOUT, len(reg))
        self.assertEqual((g.w, g.h, g.stride, g.planes[:2]), (16, 16, 64, [len(reg) * 4 + 8, len(reg) * 4]))
        for t in range(20):
            self.assertEqual(binscan.decode(reg, t * 64, 16, 16, gfx=g), glyphs[t], t)
        with tempfile.TemporaryDirectory() as d:
            p, o = os.path.join(d, "spr.bin"), os.path.join(d, "ink.bin")
            wr(p, reg)
            run(RC, "ink", p, "--gfx", TLAYOUT, "-o", o)
            self.assertEqual(rd(o), b"".join(rawcarve.pack_rows(x, 16) for x in glyphs))
            self.assertEqual(fails(RC, "ink", p, "--gfx", TLAYOUT, "--count", 21, "-o", o + "x")[0], 1)
            self.assertFalse(os.path.exists(o + "x"))
            # --invert with --gfx: the background pens are the ink
            run(RC, "ink", p, "--gfx", TLAYOUT, "--invert", "--count", 1, "-o", o)
            self.assertEqual(rd(o), rawcarve.pack_rows([[1 - v for v in r] for r in glyphs[0]], 16))

    def test_layout_lists(self):
        L = binscan._gfx_list
        self.assertEqual(L("STEP4(0,8)", 0), [0, 8, 16, 24])
        self.assertEqual(L("16*64+7, 16*64, 7,0", 0), [1031, 1024, 7, 0])
        self.assertEqual(L("RGN_FRAC(1,2)+8, RGN_FRAC(3,4)", 1024), [520, 768])
        self.assertEqual(L("STEP2(RGN_FRAC(1,2),(2+2)*2)", 64), [32, 40])
        self.assertEqual(L("0x10-1", 0), [15])
        self.assertEqual(L("-(4)+12/3", 0), [0])

    def test_bad_layouts_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p, o = os.path.join(d, "F.BIN"), os.path.join(d, "o")
            wr(p, bytes(4096))
            for spec in ("planes=0;x=STEP8(0,1);y=STEP8(0,8)",            # no inc
                         "planes=0;x=STEP8(0,1);y=STEP8(0,8);inc=60",     # inc not whole bytes
                         "planes=0;x=STEP8(0,1);y=STEP8(0,8);inc=64;inc=64",
                         "planes=0;x=STEP8(0,1);y=STEP8(0,8);inc=64,8",
                         "planes=FOO(1);x=0;y=0;inc=8", "planes=0;x=0;y=0;inc=8;z=1", "planes=-1;x=0;y=0;inc=8",
                         "planes=STEP9(0,1);x=0;y=0;inc=8", "planes=0;x=1 2;y=0;inc=8", "16x16x3_packed_lsb",
                         "planes=0;x=0;y=0;inc=8$"):
                for argv in ((RC, "ink", p, "--gfx", spec, "-o", o), (BS, "render", p, "--gfx", spec)):
                    rc, err = fails(*argv)
                    self.assertEqual(rc, 2, (spec, err))
                    self.assertIn("--gfx", err)
                self.assertFalse(os.path.exists(o))
            # a background pen outside the planes, a --glyph that is not the tile's, no --glyph and no --gfx
            for argv in ((RC, "ink", p, "--gfx", "8x8x2_packed_msb", "--bg", 4, "-o", o),
                         (RC, "ink", p, "--gfx", "8x8x2_packed_msb", "--fg", "1,4", "-o", o),
                         (RC, "ink", p, "--glyph", "8x8", "--fg", "1", "-o", o),
                         (RC, "ink", p, "--gfx", "8x8x2_packed_msb", "--glyph", "16x16", "-o", o),
                         (RC, "ink", p, "--glyph", "8x8", "--bg", "1", "-o", o),
                         (RC, "ink", p, "--gfx", "8x8x2_packed_msb", "--bg", "0", "--fg", "1", "-o", o),
                         (RC, "ink", p, "-o", o), (BS, "render", p)):
                self.assertEqual(fails(*argv)[0], 2, argv)
            self.assertFalse(os.path.exists(o))
            rc, err = fails(BS, "sets", p, "--gfx", "8x8x2_packed_msb")
            self.assertEqual(rc, 2)
            self.assertIn("rawcarve.py ink first", err)
            # hostile layouts: refused quickly with the --gfx message, never a traceback
            for spec in ("1000000000x1x4_packed_lsb", "99999999999999999999x1x4_packed_lsb", "3x4x4_packed_lsb",
                         "planes=0;x=" + ",".join(["STEP1024(0,1)"] * 50) + ";y=0;inc=8",
                         "planes=" + "(" * 2000 + "0" + ")" * 2000 + ";x=0;y=0;inc=8",
                         "planes=" + "-" * 2000 + "1;x=0;y=0;inc=8",
                         "planes=0x10000000000000000;x=0;y=0;inc=8", "planes=0;x=0;y=0;inc=4096*4096*4096*4096",
                         "planes=08;x=0;y=0;inc=8", "planes=1e3;x=0;y=0;inc=8", "planes=\u00b2;x=0;y=0;inc=8",
                         "planes=" + "9" * 5000 + ";x=0;y=0;inc=8", "planes=0;x=STEP3(0,1);y=0;inc=8",
                         "planes=0;x=STEP4096(0,1);y=0;inc=8", "{ 0 };x=0;y=0;inc=8"):
                for argv in ((RC, "ink", p, "--gfx", spec, "-o", o), (BS, "render", p, "--gfx", spec)):
                    rc, err = fails(*argv)
                    self.assertEqual(rc, 2, (spec[:40], err[-300:]))
                    self.assertIn("--gfx", err)
                    self.assertNotIn("Traceback", err)

    def test_bounds_before_building(self):
        with self.assertRaises(binscan.GfxError):
            binscan.packed_layout(10 ** 9, 1, 4, True)  # refused before a billion offsets are listed
        with self.assertRaises(binscan.GfxError):
            binscan.parse_gfx("planes=0xFFFFFFFFFF;x=0;y=0;inc=8", 128)  # one literal past 2^36

    def test_step_inv_and_mame_steps(self):
        L = binscan._gfx_list
        self.assertEqual(L("STEP4_INV(0,8)", 0), [24, 16, 8, 0])
        self.assertEqual(L("STEP2_INV(4,1),STEP2(0,1)", 0), [5, 4, 0, 1])
        self.assertEqual(L("STEP1024(0,1)", 0)[-1], 1023)
        self.assertEqual(L("STEP8_INV(0,1)", 0), list(range(7, -1, -1)))
        for bad in ("STEP2048(0,1)", "STEP3(0,1)", "STEP1(0,1)", "STEP4_REV(0,1)", "STEP\uff18(0,1)"):
            with self.assertRaises(binscan.GfxError):
                L(bad, 0)

    def test_fg_cli_and_gfx_compose_spec(self):
        """--fg through the CLI; a compose spec set read with "gfx" and "bg" draws what the 1 bpp set draws."""
        glyphs = [bits(raw844(), i * 32, 16, 16) for i in range(360)]
        data = packed4(glyphs, True)
        # outline pen: every ink pixel pen 1 or 2, paper 15; --fg 1,2 is the glyph, --fg 1 a part of it
        with tempfile.TemporaryDirectory() as d:
            p, o = os.path.join(d, "OBJ.BIN"), os.path.join(d, "ink.bin")
            two = bytearray(data)
            for k, b in enumerate(two):
                lo, hi = b & 15, b >> 4
                two[k] = ((hi if hi == 15 else 1 + (k & 1)) << 4) | (lo if lo == 15 else 1 + (k & 1))
            wr(p, bytes(two))
            run(RC, "ink", p, "--gfx", "16x16x4_packed_lsb", "--fg", "1,2", "--count", 360, "-o", o)
            self.assertEqual(rd(o), raw844())
            run(RC, "ink", p, "--gfx", "16x16x4_packed_lsb", "--fg", "1", "--count", 360, "-o", o)
            self.assertNotEqual(rd(o), raw844())
            spec = spec_844()
            gspec = dict(spec, sets={k: {"offset": v["offset"] * 4, "stride": 128, "gfx": "16x16x4_packed_lsb", "bg": 15}
                                    for k, v in spec["sets"].items()})
            plain = rawcarve.Composer(raw844(), spec)
            tiles = rawcarve.Composer(data, gspec)
            for cp in (0xAC00, 0xB000, 0xD7A3):
                self.assertEqual(tiles.syllable(*jamoset.decompose(cp)), plain.syllable(*jamoset.decompose(cp)))
            sp, b1, b2 = os.path.join(d, "g.json"), os.path.join(d, "g.bdf"), os.path.join(d, "p.bdf")
            wr(sp, json.dumps(gspec))
            wr(os.path.join(d, "T.BIN"), data)
            wr(os.path.join(d, "P.BIN"), raw844())
            wr(os.path.join(d, "p.json"), json.dumps(spec))
            run(RC, "compose", os.path.join(d, "T.BIN"), "--spec", sp, "-o", b1)
            run(RC, "compose", os.path.join(d, "P.BIN"), "--spec", os.path.join(d, "p.json"), "-o", b2)
            self.assertEqual(bdfface.read_bdf(b1)[1], bdfface.read_bdf(b2)[1])

    def test_planar_scans_stop_at_the_last_whole_tile(self):
        """With planes in both halves of the region, only the first half's tile numbers are whole tiles."""
        glyphs = [bits(raw844(), i * 32, 16, 16) for i in range(1, 41)]
        reg = tlayout_region(glyphs)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "spr.bin")
            wr(p, reg)
            t = run(BS, "render", p, "--gfx", TLAYOUT)
            self.assertIn("39 ", t)
            self.assertNotIn("\n40 ", "\n" + t.replace("  ", "\n"))
            self.assertEqual(len([ln for ln in t.splitlines() if ln.startswith("0x")]), 40 // 8)
            out = run(BS, "runs", p, "--gfx", TLAYOUT, "--min", 8)
            n = sum(int(x) for x in __import__("re").findall(r": (\d+) glyphs", out))
            self.assertLessEqual(n, 40)


class Runs(unittest.TestCase):
    def test_runs_invert_finds_the_inverted_font(self):
        font = raw844()
        rnd = random.Random(11)
        junk = bytes(rnd.randrange(256) for _ in range(256))
        with tempfile.TemporaryDirectory() as d:
            p, q = os.path.join(d, "PLAIN.BIN"), os.path.join(d, "INV.BIN")
            wr(p, junk + font + junk)
            wr(q, bytes(b ^ 0xFF for b in junk + font + junk))
            a = run(BS, "runs", p, "--glyph", "16x16")
            b = run(BS, "runs", q, "--glyph", "16x16", "--invert")
            self.assertRegex(a, r": 3[0-9][0-9] glyphs")  # the font's run
            self.assertEqual(a.split("\n", 1)[1], b.split("\n", 1)[1])
            self.assertIn("none", run(BS, "runs", q, "--glyph", "16x16"))


    def test_runs_keeps_the_last_glyph_with_a_long_stride(self):
        """--stride 48 with 32-byte glyphs: the file ends 32 bytes after the last start, and that glyph is counted."""
        font = raw844()
        data = b"".join(font[i * 32:i * 32 + 32] + bytes(16) for i in range(1, 41))[:-16]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "F.BIN")
            wr(p, data)
            out = run(BS, "runs", p, "--glyph", "16x16", "--stride", 48, "--step", 48, "--min", 8)
            self.assertIn("offset 0x0 (0): 40 glyphs", out)


class Region(unittest.TestCase):
    def test_interleave_concat_swap(self):
        a, b, c, e = (bytes(range(k, k + 8)) for k in (0x10, 0x20, 0x30, 0x40))
        with tempfile.TemporaryDirectory() as d:
            names = []
            for n, x in zip("abce", (a, b, c, e)):
                names.append(os.path.join(d, n))
                wr(names[-1], x)
            na, nb, nc, ne = names
            o = os.path.join(d, "r")
            run(RC, "region", f"{na},{nb}", f"{nc},{ne}", "-o", o)  # ROM_LOAD16_BYTE pairs, one after the other
            self.assertEqual(rd(o), bytes(v for p in zip(a, b) for v in p) + bytes(v for p in zip(c, e) for v in p))
            run(RC, "region", "--unit", 2, f"{na},{nb},{nc},{ne}", "-o", o)  # ROM_LOAD64_WORD
            self.assertEqual(rd(o)[:16], a[:2] + b[:2] + c[:2] + e[:2] + a[2:4] + b[2:4] + c[2:4] + e[2:4])
            self.assertEqual(len(rd(o)), 32)
            run(RC, "region", na, nb, "--swap", "-o", o)  # concatenated, then ROM_LOAD16_WORD_SWAP
            self.assertEqual(rd(o)[:4], bytes((a[1], a[0], a[3], a[2])))
            comma = os.path.join(d, "ROMs, Korean")              # --group: a path with a comma is one file
            os.makedirs(comma)
            ca, cb = os.path.join(comma, "a"), os.path.join(comma, "b")
            wr(ca, a)
            wr(cb, b)
            run(RC, "region", "--group", ca, cb, "--group", nc, ne, "-o", o)
            self.assertEqual(rd(o), bytes(v for p in zip(a, b) for v in p) + bytes(v for p in zip(c, e) for v in p))
            self.assertEqual(fails(RC, "region", "--group", ca, f"{na},{nb}", "-o", o)[0], 1)   # not both forms
            self.assertEqual(fails(RC, "region", "-o", o)[0], 1)                                  # no group
            run(RC, "region", na, nb, "--swap", "-o", o)
            self.assertEqual(rd(o)[:4], bytes((a[1], a[0], a[3], a[2])))
            wr(os.path.join(d, "odd"), bytes(3))
            big = os.path.join(d, "big")
            with open(big, "wb") as fh:  # sparse: 40 MiB that take no disk
                fh.truncate(40 << 20)
            for argv, msg in ((("region", ","), "empty group"), (("region", f"{big},{big}"), "83886080 bytes"),
                              (("region", big, big), "83886080 bytes")):
                os.path.exists(o) and os.remove(o)
                rc, err = fails(RC, *argv, "-o", o)
                self.assertEqual(rc, 1, argv)
                self.assertIn(msg, err)
                self.assertFalse(os.path.exists(o))
            for argv in (("region", f"{na},{os.path.join(d, 'odd')}"), ("region", "--unit", 2, os.path.join(d, "odd"))):
                os.path.exists(o) and os.remove(o)
                self.assertEqual(fails(RC, *argv, "-o", o)[0], 1, argv)
                self.assertFalse(os.path.exists(o))


class Eng16(unittest.TestCase):
    def eng16(self):
        """A 16x16 English font of 95 glyphs from code 0x20: letters and digits inked at columns 2..9, '~' to 15."""
        out = bytearray()
        for c in range(0x20, 0x7F):
            rows = [0] * 16
            if chr(c).isalnum():
                for y in range(3, 13):
                    rows[y] = 0x3FC0 if y in (3, 12) else 0x2040 | (c & 0x0F) << 7
            elif c == 0x7E:
                rows[7] = 0x7FFF
            out += b"".join(r.to_bytes(2, "big") for r in rows)
        return bytes(out)

    def test_width16_eng_into_a_jamo_set(self):
        with tempfile.TemporaryDirectory() as d:
            p, e = os.path.join(d, "INK.BIN"), os.path.join(d, "e16.raw")
            wr(p, bytes(64) + self.eng16())
            run(RC, "eng", p, "--offset", 64, "--width", 16, "--first", 0x20, "-o", e)
            raw = rd(e)
            self.assertEqual(len(raw), 8192)
            self.assertEqual(raw[0x41 * 32:0x42 * 32], self.eng16()[0x21 * 32:0x22 * 32])
            self.assertEqual(raw[:0x20 * 32], bytes(0x20 * 32))
            # --count: only that many codes, the rest blank
            e3 = os.path.join(d, "e3.raw")
            run(RC, "eng", p, "--offset", 64, "--width", 16, "--first", 0x20, "--count", 3, "-o", e3)
            self.assertEqual(rd(e3)[:0x23 * 32], raw[:0x23 * 32])
            self.assertEqual(rd(e3)[0x23 * 32:], bytes(8192 - 0x23 * 32))
            # 14 rows placed one row down (--top), 16 wide
            e14 = os.path.join(d, "e14.raw")
            run(RC, "eng", p, "--offset", 64 + 0x21 * 32, "--width", 16, "--height", 14, "--top", 1, "--first", 0x41,
                "-o", e14)
            self.assertEqual(rd(e14)[0x41 * 32:0x42 * 32], bytes(2) + self.eng16()[0x21 * 32:0x21 * 32 + 28] + bytes(2))
            self.assertEqual(jamoset.read_eng(bytes(8192)).adv, 16)  # no ink to measure: the cell
            cell = jamoset.read_eng(raw)
            self.assertEqual((cell.w, cell.h, cell.adv), (16, 16, 12))  # right edge 10 + left margin 2
            self.assertEqual(cell.glyph(0x7E)[7], 0x7FFF)  # columns past 8 are kept
            f844 = os.path.join(d, "f.fnt")
            wr(f844, raw844())
            o = os.path.join(d, "J.SVF")
            run(JS, "--layout", "844", f844, "--eng", e, "--check", "-o", o)
            f = jamoset.parse_svfn(rd(o))
            self.assertEqual(f.metrics[0x41][0], 12)
            self.assertEqual(f.glyphs[0x7E][14:16], b"\x7f\xff")
            self.assertEqual(f.ascent, 13)  # the row below the ink of 'H'
            run(JS, "--layout", "844", f844, "--eng", e, "--eng-advance", 10, "-o", o)
            self.assertEqual(jamoset.parse_svfn(rd(o)).metrics[0x41][0], 10)
            e8 = os.path.join(d, "e8.raw")
            wr(e8, ascii8x16())
            for argv in (("--eng", e8, "--eng-advance", 10), ("--eng-advance", 10), ("--eng", e, "--eng-advance", 0)):
                rc, err = fails(JS, "--layout", "844", f844, *argv, "-o", o + "x")
                self.assertEqual(rc, 1, (argv, err))
                self.assertIn("--eng", err)
            rc, err = fails(RC, "eng", p, "--offset", 0, "--first", 256, "-o", o + "x")
            self.assertEqual(rc, 1)


def spc_region(seed=5):
    """A synthetic SPC-1500 "font1" region (32 KB): ss150 (an inverted 8x16 English font at 0x1000), then the initial,
    medial and final ROMs as the driver reads them: 8 sets of 32 slots of 16x16 pieces in two 8-pixel strips, ink as 0
    bits, slot 0 of every set blank (0xFF)."""
    rnd = random.Random(seed)
    reg = bytearray([0xFF] * 0x8000)
    reg[0x1000:0x2000] = bytes(b ^ 0xFF for b in ascii8x16())
    for rom in (0x2000, 0x4000, 0x6000):
        for st in range(8):
            for slot in range(1, 32):
                off = rom + st * 0x400 + slot * 32
                for k in range(32):
                    reg[off + k] = 0xFF ^ (rnd.getrandbits(8) & rnd.getrandbits(8) & rnd.getrandbits(8))
    return bytes(reg)


def mame_spc1500(font, L, V, T):
    """A syllable as MAME's spc1500.cpp crtc_update_row draws it (an independent reading: Samsung code h1 = L + 1,
    h2 = the Johab vowel code, h3 = T; the AND of the three inverted pieces, ink = the 0 bits), as 16 row ints."""
    # cho[] and jong[] as spc1500.cpp has them (copied from the driver, not from rawcarve.py), by the Johab vowel code
    cho = (1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 3, 5, 5, 0, 0, 5, 3, 3, 5, 5, 5, 0, 0, 3, 3, 5, 1)
    jong = (0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 2, 2, 2, 0, 0, 2, 2, 2, 2, 2, 2, 0, 0, 2, 2, 1, 1)
    vowel_code = (3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 22, 23, 26, 27, 28, 29)  # ㅏ .. ㅣ
    h1, h2, h3 = L + 1, vowel_code[V], T
    rows = []
    for n in range(16):
        def piece(addr):
            return (font[addr + n] << 8) | font[addr + n + 16]
        hfnt = piece(0x2000 + h1 * 32 + (cho[h2] + (h3 != 0) - 1) * 16 * 2 * 32)
        hfnt &= piece(0x4000 + h2 * 32 + (0 if h3 == 0 else 1) * 16 * 2 * 32)
        hfnt &= piece(0x6000 + h3 * 32 + (jong[h2] - 1) * 16 * 2 * 32)
        rows.append(0xFFFF ^ hfnt)
    return rows


class SpecJamoSet(unittest.TestCase):
    def test_spc1500_builtin_spec_is_exact(self):
        reg = spc_region()
        with tempfile.TemporaryDirectory() as d:
            p, o = os.path.join(d, "font1.bin"), os.path.join(d, "SPCJ.SVF")
            wr(p, reg)
            e = os.path.join(d, "eng.raw")
            run(RC, "eng", p, "--offset", 0x1000, "--invert", "-o", e)
            out = run(JS, "--layout", "spec", "--spec", "spc1500", p, "--eng", e, "--check", "-o", o)
            self.assertIn("(6/2/2 sets, 1x2 classes)", out)
            self.assertIn("identical to rawcarve.py compose", out)
            f = jamoset.parse_svfn(rd(o))
            t = jamoset.unpack(f.jset)
            self.assertEqual((t.ni, t.nm, t.nf, t.lc, t.tc), (6, 2, 2, 1, 2))
            for cp in list(range(0xAC00, 0xD7A4, 97)) + [0xAC00, 0xAC01, 0xB5A0, 0xD7A3]:
                L, V, T = jamoset.decompose(cp)
                want = b"".join(r.to_bytes(2, "big") for r in mame_spc1500(reg, L, V, T))
                self.assertEqual(jamoset.compose(f, t, cp), want, hex(cp))
            self.assertEqual(f.glyphs[0x41], b"".join(bytes((v, 0)) for v in ascii8x16()[0x41 * 16:0x42 * 16]))
            # rawcarve compose with the same built-in spec writes the same syllables
            b = os.path.join(d, "s.bdf")
            run(RC, "compose", p, "--spec", "spc1500", "--syllables", "all", "-o", b)
            g = bdfface.read_bdf(b)[1]
            for cp in (0xAC00, 0xB5A0, 0xD7A3):
                self.assertEqual(g[cp][4], mame_spc1500(reg, *jamoset.decompose(cp)), hex(cp))
            # the region read without the inversion is not the font: the spec's "invert" matters
            spec = rawcarve.spc1500_spec()
            spec["invert"] = False
            sp = os.path.join(d, "noinv.json")
            wr(sp, json.dumps(spec))
            run(JS, "--layout", "spec", "--spec", sp, p, "-o", o)
            f2 = jamoset.parse_svfn(rd(o))
            self.assertNotEqual(jamoset.compose(f2, jamoset.unpack(f2.jset), 0xAC00), jamoset.compose(f, t, 0xAC00))

    def test_builtin_name_wins_over_a_folder(self):
        """--spec spc1500 is the built-in spec even in a folder that holds spc1500/ (the recipe's $MAME layout)."""
        reg = spc_region()
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "spc1500"))
            p, o = os.path.join(d, "font1.bin"), os.path.join(d, "J.SVF")
            wr(p, reg)
            for tool, argv in ((JS, ["--layout", "spec", "--spec", "spc1500", p, "-o", o]),
                               (RC, ["compose", p, "--spec", "spc1500", "-o", o + ".bdf"])):
                r = subprocess.run([sys.executable, tool] + argv, capture_output=True, text=True, cwd=d)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_novowel_set_is_set_0(self):
        """The spec's "novowel" set is JSET initial set 0 (the compatibility jamo's), whatever the tables list first."""
        font = raw844()
        spec = spec_844()
        spec["initial"] = dict(spec["initial"], novowel="i3")
        layout, src = jamoset.spec_layout(rawcarve.Composer(font, spec))
        t = jamoset.tables_for(layout)
        self.assertEqual(src.glyph(t.init_piece[0]).rows, bits_ints(font, (3 * 20 + 1) * 32))
        self.assertEqual(src.glyph(t.compat[0]).rows, bits_ints(font, (3 * 20 + 1) * 32))  # ㄱ from set i3

    def test_spec_refuses_a_taller_eng(self):
        with tempfile.TemporaryDirectory() as d:
            p, e, o = os.path.join(d, "font1.bin"), os.path.join(d, "PFT"), os.path.join(d, "J.SVF")
            wr(p, spc_region())
            wr(e, bytes(12288))  # a 12x24 Taebaek PFT English font: taller than the 16-row cell
            rc, err = fails(JS, "--layout", "spec", "--spec", "spc1500", p, "--eng", e, "-o", o)
            self.assertEqual(rc, 1)
            self.assertIn("taller", err)
            self.assertFalse(os.path.exists(o))

    def test_check_spec_finds_a_difference(self):
        """check_spec compares with the spec's composition: a face built from another font fails it."""
        font = raw844()
        other = bytes(font[:32 * 21]) + bytes(32) + font[32 * 22:]  # piece 21 (set 1's ㄱ) blanked
        spec = spec_844()
        layout, src = jamoset.spec_layout(rawcarve.Composer(other, spec))
        out = jamoset.build_from_source(layout, src)[0]
        self.assertIn("identical", jamoset.check_spec(out, rawcarve.Composer(other, spec)))
        with self.assertRaises(ValueError):
            jamoset.check_spec(out, rawcarve.Composer(font, spec))

    def test_844_spec_with_kk_classes(self):
        """The 8x4x4 rule as a spec (two lead classes): the jamo set composes every syllable as johab844.py does."""
        import johab844
        font = raw844()
        with tempfile.TemporaryDirectory() as d:
            p, sp, o = os.path.join(d, "F.FNT"), os.path.join(d, "s.json"), os.path.join(d, "J.SVF")
            wr(p, font)
            wr(sp, json.dumps(spec_844()))
            out = run(JS, "--layout", "spec", "--spec", sp, p, "--check", "-o", o)
            self.assertIn("(8/4/4 sets, 2x2 classes)", out)
            f = jamoset.parse_svfn(rd(o))
            t = jamoset.unpack(f.jset)
            for cp in range(0xAC00, 0xD7A4, 41):
                self.assertEqual(jamoset.compose(f, t, cp), johab844.compose(font, cp), hex(cp))

    def test_vowel_order_set_final_and_placement(self):
        """A spec with its own vowel order, one final set and a half-cell set placed at x = 8: still exact."""
        rnd = random.Random(8)
        font = bytes(rnd.getrandbits(8) & rnd.getrandbits(8) for _ in range(4096))
        vo = list(range(21))
        rnd.shuffle(vo)
        spec = {"cell": [16, 16], "vowel_order": vo,
                "sets": {"I": {"offset": 0, "stride": 32}, "J": {"offset": 640, "stride": 32},
                         "M": {"offset": 1280, "stride": 16, "x": 8, "width": 8, "height": 16},
                         "F": {"offset": 1700, "stride": 32, "order": "strips", "lsb": True}},
                "initial": {"nofinal": ["I"] * 21, "final": ["J"] * 10 + ["I"] * 11},
                "medial": {"nofinal": [["M", v] for v in range(21)], "final": [["M", 20 - v] for v in range(21)]},
                "final": {"set": "F"}}
        with tempfile.TemporaryDirectory() as d:
            p, sp, o = os.path.join(d, "F.BIN"), os.path.join(d, "s.json"), os.path.join(d, "J.SVF")
            wr(p, font)
            wr(sp, json.dumps(spec))
            out = run(JS, "--layout", "spec", "--spec", sp, p, "--check", "--embolden", "-o", o)
            self.assertIn("(2/2/1 sets, 1x2 classes)", out)
            self.assertIn("identical to rawcarve.py compose", out)

    def test_refusals(self):
        with tempfile.TemporaryDirectory() as d:
            p, o = os.path.join(d, "F.BIN"), os.path.join(d, "o")
            wr(p, raw844())
            bad = dict(spec_844(), final={"by_vowel": ["f0"] * 20})
            sp = os.path.join(d, "bad.json")
            wr(sp, json.dumps(bad))
            unknown = dict(spec_844(), final={"set": "nope"})
            su = os.path.join(d, "unknown.json")
            wr(su, json.dumps(unknown))
            for argv, code in (((p, "--spec", sp), 1), ((p, "--spec", su), 1), ((p,), 2),
                               ((p, "--spec", os.path.join(d, "none.json")), 1),
                               (("--from-svf", p, "--spec", "spc1500"), 2)):
                rc, err = fails(JS, "--layout", "spec", *argv, "-o", o)
                self.assertEqual(rc, code, (argv, err))
                self.assertFalse(os.path.exists(o), argv)
            rc, err = fails(JS, "--layout", "844", p, "--spec", "spc1500", "-o", o)
            self.assertEqual(rc, 2)
            self.assertIn("--layout spec", err)


MAME_ROMS = os.environ.get("MAME_ROMS", os.path.join(HERE, "no-mame-roms"))
# SHA1 of each file as MAME 0.289's drivers list it (samsung/spc1500.cpp, dataeast/tumbleb.cpp, seibu/raiden2.cpp)
DRIVER_SHA1 = {
    "spc1500/ss150fnt.bin": "2a93582fcccf9e40b99ae238ce585d189afe9a5a",
    "spc1500/ss151fnt.bin": "2adf7816206dc74b9f0d32cb3b56cbab31fa6044",
    "spc1500/ss152fnt.bin": "c9a02756107083bf602ae7c90cfe29b8b964e0df",
    "spc1500/ss153fnt.bin": "34bfacc855c3846744cd586c150c72e5cbe948b0",
    "dquizgo/uor1": "ef827adba58470a201f3c1ecc3286d728a753eff",
    "dquizgo/uor2": "b993df91511ac17d5bf8e688333f2953b87d5be4",
    "dquizgo/uor3": "6b313462fd8985fae60bc59cd9c99c97ab70fdcc",
    "dquizgo/uor4": "7fc891810591458fd62f3d4b9b4c966662e90403",
    "xsedae/obj-1.u0811": "d9713c79eacb4b3ce5e82dd3ce39003e3a433d8f",
    "xsedae/obj-2.u082": "899a76a1b3f933c6f5cb6b5dcdf5b58e1b7e49c6",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


@unittest.skipUnless(os.path.isdir(os.path.join(MAME_ROMS, "spc1500")), "MAME_ROMS does not name a folder of MAME sets")
class RealRoms(unittest.TestCase):
    """The real ROM dumps (proprietary, not in this repository): driver SHA1s, then hashes of what the recipes cut."""

    def path(self, rel):
        return os.path.join(MAME_ROMS, rel)

    def test_driver_sha1(self):
        for rel, want in DRIVER_SHA1.items():
            if os.path.exists(self.path(rel)):
                self.assertEqual(hashlib.sha1(rd(self.path(rel))).hexdigest(), want, rel)

    def test_spc1500_exact_jamo_set(self):
        with tempfile.TemporaryDirectory() as d:
            reg, o = os.path.join(d, "font1.bin"), os.path.join(d, "SPC1500J.SVF")
            run(RC, "region", *(self.path(f"spc1500/ss15{k}fnt.bin") for k in range(4)), "-o", reg)
            font = rd(reg)
            run(JS, "--layout", "spec", "--spec", "spc1500", reg, "--check", "-o", o)
            f = jamoset.parse_svfn(rd(o))
            t = jamoset.unpack(f.jset)
            table = b""
            for cp in range(0xAC00, 0xD7A4):
                got = jamoset.compose(f, t, cp)
                self.assertEqual(got, b"".join(r.to_bytes(2, "big") for r in mame_spc1500(font, *jamoset.decompose(cp))),
                                 hex(cp))
                table += got
            self.assertEqual(sha(table), SPC1500_SYLLABLES)

    @unittest.skipUnless(os.path.isdir(os.path.join(MAME_ROMS, "dquizgo")), "no dquizgo set")
    def test_dquizgo_ink_map(self):
        with tempfile.TemporaryDirectory() as d:
            reg, ink = os.path.join(d, "spr.bin"), os.path.join(d, "ink.bin")
            run(RC, "region", ",".join(self.path(f"dquizgo/uor{k}") for k in (1, 2)),
                ",".join(self.path(f"dquizgo/uor{k}") for k in (3, 4)), "-o", reg)
            run(RC, "ink", reg, "--gfx", TLAYOUT, "-o", ink)
            data = rd(ink)
            self.assertEqual(sha(data[13347 * 32:(13347 + 2350) * 32]), DQUIZGO_KS)

    @unittest.skipUnless(os.path.isdir(os.path.join(MAME_ROMS, "xsedae")), "no xsedae set")
    def test_xsedae_844(self):
        with tempfile.TemporaryDirectory() as d:
            reg, ink = os.path.join(d, "obj.bin"), os.path.join(d, "ink.bin")
            run(RC, "region", "--unit", 2, self.path("xsedae/obj-1.u0811") + "," + self.path("xsedae/obj-2.u082"),
                "-o", reg)
            run(RC, "ink", reg, "--gfx", "16x16x4_packed_lsb", "--bg", 15, "--count", 360, "-o", ink)
            self.assertEqual(sha(rd(ink)), XSEDAE_844)
            if os.path.exists(GOTHIC16):  # Taebaek 3.5.1's GOTHIC16.FNT (JOHAB_FONTS research tree): the same bytes
                self.assertEqual(rd(ink), rd(GOTHIC16))


# sha256 of: the 11,172 syllables the SPC-1500 jamo set composes (32 B each, U+AC00 on); the 2,350 KS X 1001 syllables of
# the Date Quiz Go Go ink map (sprite 13347 on); the first 360 X Se Dae Quiz sprites as an ink map (an 8x4x4 font)
SPC1500_SYLLABLES = "b72bcadc1f74f707ec5ba6f3a2e6dde067436fae226e905109b340d129155dad"
DQUIZGO_KS = "412255d1f56c22f726d0d6784b7e40da248cf5af3f5ec7d39139efce101d7b8c"
XSEDAE_844 = "883f9ac74c48f483bfe0508a71e59d9d2fb8c7a55a9adf2a0a8390650d4a10e3"
JOHAB_FONTS = os.environ.get("JOHAB_FONTS", os.path.join(HERE, "no-johab-fonts"))
GOTHIC16 = os.path.join(JOHAB_FONTS, "dos/extracted/tb351__tb351/FNT/GOTHIC16.FNT")


if __name__ == "__main__":
    unittest.main()
