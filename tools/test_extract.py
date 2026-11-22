#!/usr/bin/env python3
"""Tests of the extraction tools of docs/recipes.md ("Finding a font inside a program or data file", "OS/2 Korean fonts",
"A low-resolution face from a high-resolution bitmap font"): binscan.py, rawcarve.py, os2dbcs.py and svfscale.py, on
synthetic files built here (no font data).
  python3 -m unittest tools.test_extract
"""
import json
import os
import random
import re
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
import nkpspec  # noqa: E402
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
            listed = re.findall(r"0x[0-9a-f]+", out.split("\n", 1)[1].split(":")[0])
            self.assertIn(f"{len(junk):#x}", listed)  # the true offset is listed (with its whole-row shifts, if any)
            if len(listed) > 1:
                self.assertIn("tie", out)
            out = run(os.path.join(HERE, "binscan.py"), "ascii", p)
            self.assertIn(f"offset {2 * len(junk) + len(font):#x} ", out)
            out = run(os.path.join(HERE, "binscan.py"), "ascii", p, "--start", str(len(junk) + len(font)))
            self.assertIn(f"offset {2 * len(junk) + len(font):#x} ", out)  # offsets stay file offsets in a window
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

    def test_bad_arguments(self):
        with tempfile.TemporaryDirectory() as d:
            p, o = os.path.join(d, "F.BIN"), os.path.join(d, "o")
            wr(p, bytes(range(1, 256)) * 2400)  # every glyph inked: a bad grid must fail, not draw something
            rc = os.path.join(HERE, "rawcarve.py")
            for argv in (("cut", p, "--offset", "-1", "--length", "4"), ("cut", p, "--offset", "0", "--length", "0"),
                         ("cut", p, "--offset", "611998", "--length", "4"), ("eng", p, "--offset", "0", "--top", "-1"),
                         ("eng", p, "--offset", "0", "--height", "14", "--top", "3"),
                         ("bdf", p, "--glyph", "16x16", "--chars", "ks-hangul", "--grid", "0xB1,0xA1,94"),
                         ("bdf", p, "--glyph", "16x16", "--chars", "ks-hangul", "--grid", "0xA1,0xA1,10")):
                r = subprocess.run([sys.executable, rc] + list(argv) + ["-o", o], capture_output=True, text=True)
                self.assertEqual(r.returncode, 1, argv)
            bs = os.path.join(HERE, "binscan.py")
            for argv in (("info", p, "--block", "0"), ("render", p, "--glyph", "0x16"), ("runs", p, "--step", "0")):
                r = subprocess.run([sys.executable, bs] + list(argv), capture_output=True, text=True)
                self.assertEqual(r.returncode, 2, argv)

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


def nkp_like():
    """A synthetic .COM with an NKP-style Hangul routine: the instruction patterns nkpspec.py looks for, the jamo tables
    (Unicode order), 17 piece-set records (record 0: 16 wide, rows 3-11, stride 18; record 48: right 8 pixels, rows
    1-14, stride 14; record 96: the finals, 16 wide, rows 10-14) and their pieces (piece k of a set: one row of value
    k + 1 at the set's first stored row)."""
    d = bytearray(0x3000)
    org = 0x100
    desc, cho, jung, jong, iset, med = 0x1100, 0x1200, 0x1220, 0x1240, 0x1260, 0x1290
    d[0x10:0x1A] = b"\xba" + struct.pack("<H", desc) + b"\x03\xda\x8b\x0f\x8a\x47\x02"
    d[0x20:0x2E] = b"\x24\x7f\xd0\xe8\xd0\xe8\x8a\xd8\x32\xff\x8a\x87" + struct.pack("<H", cho)
    d[0x30:0x36] = b"\xd3\xeb\x8a\x87" + struct.pack("<H", jung)
    d[0x40:0x47] = b"\x80\xe3\x1f\x8a\x87" + struct.pack("<H", jong)
    d[0x50:0x55] = b"\x8a\x9f" + struct.pack("<H", iset) + b"\xe8"
    d[0x60:0x66] = b"\x8a\xa7" + struct.pack("<H", med) + b"\x8a\x9f"
    c = [31] * 32
    for i in range(19):
        c[2 + i] = i
    d[cho - org:cho - org + 32] = bytes(c)
    j = [31] * 32
    for v, f in enumerate((3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 18, 19, 20, 21, 22, 23, 26, 27, 28, 29)):
        j[f] = v
    d[jung - org:jung - org + 32] = bytes(j)
    t = [31] * 32
    for i, f in enumerate(list(range(2, 18)) + list(range(19, 30))):
        t[f] = i
    d[jong - org:jong - org + 32] = bytes(t)
    d[iset - org:iset - org + 42] = bytes([0] * 21 + [6] * 21)
    d[med - org:med - org + 84] = bytes(sum(([v, 48] for v in range(21)), []) + sum(([v, 54] for v in range(21)), []))
    data = 0x1400
    recs = {0: (18, 6, 24, 1), 6: (18, 4, 22, 1), 48: (14, 3, 30, 0), 54: (14, 3, 30, 0), 96: (10, 20, 30, 1)}
    for r in range(17):
        stride, first, end, fl = recs.get(6 * r, (2, 0, 2, 1))
        struct.pack_into("<HBBBB", d, desc - org + 6 * r, data + org, stride, first, end, fl)
        if 6 * r in recs:
            for k in range(27):
                d[data + k * stride] = (k + 1) & 0xFF
            data += 27 * stride
    return bytes(d)


def os2_font(glyphs, w=16, h=16, short=None):
    """A synthetic System DBCS file. Codes: nibble n (1..15) = '1' + 4 bits; nibble 0 = eight 0 bits (the escape) +
    '001': escape entry 1 (3 more bits; the other entries name other nibbles). The context table is not the identity: T[(c << 8) | (a << 4) | r] =
    r ^ a ^ (c >> 1), a permutation of r for every (c, a). @p short: {glyph: bytes} to cut off a record's payload."""
    bpg = (w + 7) // 8 * h
    rb = (w + 7) // 8
    d = bytearray(0x1A00)
    d[:16] = b"System DBCS %-4d" % h
    struct.pack_into("<HHHHHHH", d, 0x10, 0x3B7, w, h, 1, bpg, 0, 1)
    struct.pack_into("<HBBBBBB", d, 0x80, 3, 0xA1, 0xAC, 0xB0, 0xC8, 0xCA, 0xFD)
    struct.pack_into("<HHHHHHH", d, 0xA0, 3, 256, 1383, 1666, 4015, 4110, 8997)
    for v in range(1, 256):
        d[0xC0 + v] = (5 << 4) | ((v >> 3) & 15) if v & 0x80 else 0
    d[0x1C0:0x1C8] = bytes([(3 << 4) | 5] + [(3 << 4) | 0] + [(3 << 4) | 9] * 6)  # nibble 0 is escape entry 1
    t = [0] * 4096
    for c in range(16):
        for a in range(16):
            for r in range(16):
                t[(c << 8) | (a << 4) | r] = r ^ a ^ (c >> 1)
    for i in range(2048):
        d[0x200 + i] = (t[2 * i] << 4) | t[2 * i + 1]
    inv = {}
    for k, v in enumerate(t):
        inv[(k >> 4, v)] = k & 15
    blocks, cur = [], bytearray()
    for g, out in sorted(glyphs.items()):
        res = []
        for i in range(bpg):
            c = out[i - 2 * rb] if i >= 2 * rb else 0
            a = out[i - rb] if i >= rb else 0
            hi = inv[(((c >> 4) << 4) | (a >> 4), out[i] >> 4)]
            lo = inv[(((c & 15) << 4) | (a & 15), out[i] & 15)]
            res += [hi, lo]
        bits = "".join("00000000001" if n == 0 else "1" + format(n, "04b") for n in res)
        bits += "1" * (-len(bits) % 8)
        payload = int(bits, 2).to_bytes(len(bits) // 8, "big")
        if short and g in short:
            payload = payload[:short[g]]
        rec = struct.pack("<HB", g, len(payload)) + payload
        if len(cur) + len(rec) > 512:
            blocks.append(bytes(cur) + b"\xff" * (512 - len(cur)))
            cur = bytearray()
        cur += rec
    blocks.append(bytes(cur) + b"\xff" * (512 - len(cur)))
    return bytes(d) + b"".join(blocks)


class NkpSpec(unittest.TestCase):
    def test_spec_from_tables(self):
        d = nkp_like()
        found = nkpspec.find(d)
        self.assertEqual(found["desc"], 0x1100)
        sp = nkpspec.spec(d, found)
        self.assertEqual(sp["vowel_order"], list(range(21)))
        self.assertEqual({k: sp["sets"][k] for k in ("d0", "d48", "d96")}, {
            "d0": {"offset": 0x1400, "stride": 18, "x": 0, "y": 3, "width": 16, "height": 9},
            "d48": {"offset": sp["sets"]["d48"]["offset"], "stride": 14, "x": 8, "y": 1, "width": 8, "height": 14},
            "d96": {"offset": sp["sets"]["d96"]["offset"], "stride": 10, "x": 0, "y": 10, "width": 16, "height": 5}})
        # 각 = initial ㄱ (with a final: set d6, piece 0), medial ㅏ (d54, piece 0), final ㄱ (d96, piece 0)
        c = rawcarve.Composer(d, sp)
        g = c.syllable(0, 0, 1)
        self.assertEqual(g[2], [0] * 7 + [1] + [0] * 8)        # d6 piece 0 = value 1 at row 2, bit 7 = x 7
        self.assertEqual(g[1][8:], [0, 0, 0, 0, 0, 0, 0, 1])    # d54 piece 0: one byte at row 1, right half
        self.assertEqual(g[10], [0] * 7 + [1] + [0] * 8)       # d96 piece 0 at row 10
        with tempfile.TemporaryDirectory() as t:
            p, o = os.path.join(t, "NKP.COM"), os.path.join(t, "nkp.json")
            wr(p, d)
            run(os.path.join(HERE, "nkpspec.py"), "spec", p, "-o", o)
            self.assertEqual(json.loads(rd(o)), sp)
        bad = bytearray(d)
        bad[0x1260 - 0x100] = 5  # a record offset that is not a multiple of 6
        with self.assertRaises(nkpspec.SpecError):
            nkpspec.spec(bytes(bad), found)


class Os2Dbcs(unittest.TestCase):
    def test_decode_and_table(self):
        rnd = random.Random(3)
        # a sparse set with large gaps (256 .. 8997), random bitmaps (zero nibbles take the escape code), several blocks
        nums = [256, 1666, 1667, 4015, 4110] + list(range(5000, 5040)) + [8997]
        glyphs = {g: bytes(rnd.choice((0, 0, rnd.randrange(256))) for _ in range(32)) for g in nums}
        d = os2_font(glyphs)
        self.assertGreater(len(d), 0x1A00 + 512)
        self.assertEqual(os2dbcs.decode(d), glyphs)
        g24 = {1666: bytes(rnd.randrange(256) for _ in range(72))}
        self.assertEqual(os2dbcs.decode(os2_font(g24, 24, 24)), g24)
        with tempfile.TemporaryDirectory() as t:
            p, o, b = os.path.join(t, "ZN16.FNT"), os.path.join(t, "zn.bin"), os.path.join(t, "zn.bdf")
            wr(p, d)
            run(os.path.join(HERE, "os2dbcs.py"), "table", p, "-o", o)
            tab = rd(o)
            self.assertEqual(len(tab), (8998 - 256) * 32)
            self.assertEqual(tab[(1666 - 256) * 32:(1667 - 256) * 32], glyphs[1666])
            self.assertEqual(tab[(8997 - 256) * 32:], glyphs[8997])
            run(os.path.join(HERE, "rawcarve.py"), "bdf", o, "--glyph", "16x16", "--chars", "ks-hangul",
                "--grid", "0xA1,0xA1,94", "-o", b)
            want = sorted(0xAC00 + s for s in jamoset.ks_x_1001_syllables()
                          if any(glyphs.get(1666 + jamoset.ks_x_1001_syllables().index(s), b"")))
            self.assertEqual(sorted(bdfface.read_bdf(b)[1]), want)

    def test_bad_files(self):
        g = {1666: bytes(range(32))}
        d = os2_font(g)
        with self.assertRaisesRegex(os2dbcs.DbcsError, "truncated"):
            os2dbcs.decode(d[:0x1000])
        for cut in range(5, 40):  # cut inside a code and between codes
            with self.assertRaisesRegex(os2dbcs.DbcsError, "past its"):
                os2dbcs.decode(os2_font(g, short={1666: cut}))
        bad = bytearray(d)
        struct.pack_into("<H", bad, 0x18, 31)
        with self.assertRaisesRegex(os2dbcs.DbcsError, "bytes a glyph"):
            os2dbcs.decode(bytes(bad))
        with self.assertRaisesRegex(os2dbcs.DbcsError, "runs past its block or the file"):
            os2dbcs.decode(d[:0x1A00 + 20])  # a record cut by the end of the file
        many = os2_font({g: bytes(range(32)) for g in range(1666, 1700)})
        q, last = 0x1A00, None
        while many[q] | many[q + 1] << 8 != 0xFFFF:
            last, q = q, q + 3 + many[q + 2]
        bad = bytearray(many)
        bad[last + 2] = 0x1A00 + 512 - last  # the last record of the block now runs into the next block
        with self.assertRaisesRegex(os2dbcs.DbcsError, "runs past its block"):
            os2dbcs.decode(bytes(bad))


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
                self.assertEqual(px(10, 12), 1 if bpp == 1 else 2)  # share 0.5: kept at the 0.5 threshold
                if bpp == 1:
                    iou, dx, dy, exact, n = svfscale.overlap(o, o)
                    self.assertEqual((iou, dx, dy, exact, n), (1.0, 0, 0, 1, 1))

    def test_level_rule(self):
        """48 -> 16: a 3x3 footprint; 2 inked source pixels = share 2/9: level (57 x 3 + 127) // 255 = 1 at 2 bpp, nothing
        at 1 bpp; 5 pixels = 5/9: level 2, and kept at 1 bpp."""
        rows = [[0] * 48 for _ in range(48)]
        rows[0][0] = rows[1][1] = 1
        for x, y in ((3, 0), (4, 0), (5, 0), (3, 1), (4, 1)):
            rows[y][x] = 1
        with tempfile.TemporaryDirectory() as d:
            b = os.path.join(d, "big.bdf")
            wr(b, rawcarve.bdf_text({0xAC00: rows}, 48, 48, 42, "t"))
            for bpp, want in ((2, (1, 2)), (1, (0, 1))):
                o = os.path.join(d, f"s{bpp}.svf")
                run(os.path.join(HERE, "svfscale.py"), b, "--size", "16", "--bpp", bpp, "--chars", "face", "-o", o)
                g = jamoset.parse_svfn(rd(o)).glyphs[0xAC00]
                first = g[0] >> (8 - bpp), (g[0] >> (8 - 2 * bpp)) & ((1 << bpp) - 1)
                self.assertEqual(first, want, bpp)

    @staticmethod
    def face(path, w, h, ascent, glyphs, dy=None):
        """An SVF of {cp: (rows of 0/1, advance)}."""
        recs = []
        for cp, (rows, adv) in sorted(glyphs.items()):
            cols = [x for x in range(w) if any(r[x] for r in rows)]
            packed = b"".join(int("".join(map(str, r)), 2).to_bytes((w + 7) // 8, "big")
                              if w % 8 == 0 else (int("".join(map(str, r)), 2) << (-w % 8)).to_bytes((w + 7) // 8, "big")
                              for r in rows)
            recs.append((cp, packed, adv, cols[0] if cols else 0, cols[-1] - cols[0] + 1 if cols else 0))
        wr(path, jamoset.write_svfn(w, h, ascent, recs, b"", jamoset.FLAG_MARKS_AT_ORIGIN, bpp=1, dy=dy or {}))

    def test_metrics_dy_and_compare(self):
        """24 -> 16: ascent 22 -> 15 (rounded), advance 12 -> 8 and 24 -> 16, a dy of 3 -> 2 with the glyph resampled
        from its own cell; --compare puts both faces on one baseline."""
        full = [[1 if 4 <= x < 20 and 4 <= y < 21 else 0 for x in range(24)] for y in range(24)]
        half = [[1 if 0 <= x < 12 and 6 <= y < 18 else 0 for x in range(24)] for y in range(24)]
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "s.svf"), os.path.join(d, "o.svf")
            self.face(src, 24, 24, 22, {0xAC00: (full, 24), 0x41: (half, 12)}, dy={0xAC00: 3})
            run(os.path.join(HERE, "svfscale.py"), src, "--size", "16", "--chars", "face", "-o", out)
            f = jamoset.parse_svfn(rd(out))
            self.assertEqual((f.cell_w, f.cell_h, f.ascent), (16, 16, 15))
            self.assertEqual(f.metrics[0xAC00][0], 16)
            self.assertEqual(f.metrics[0x41][0], 8)
            self.assertEqual(f.dy.get(0xAC00, 0), 2)
            g = f.glyphs[0xAC00]
            row = lambda y: int.from_bytes(g[y * 2:y * 2 + 2], "big")  # noqa: E731
            # resampled from its own cell: source rows 4-20 -> rows 3-13 (columns 3-12), the dy kept apart
            self.assertEqual([y for y in range(16) if row(y)], list(range(3, 14)))
            self.assertEqual(row(3), 0x1FF8)
            # the same glyph in a taller cell with a larger ascent: on one baseline the faces overlap exactly
            box = [[1 if 2 <= x < 10 and 3 <= y < 11 else 0 for x in range(16)] for y in range(16)]
            tall = [[0] * 16 for _ in range(3)] + box[:15]
            a, b = os.path.join(d, "a.svf"), os.path.join(d, "b.svf")
            self.face(a, 16, 16, 12, {0xAC00: (box, 16)})
            self.face(b, 16, 18, 15, {0xAC00: (tall, 16)})
            self.assertEqual(svfscale.overlap(a, b), (1.0, 0, 0, 1, 1))
            bad = subprocess.run([sys.executable, os.path.join(HERE, "svfscale.py"), src, "--size", "0", "-o", out],
                                 capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)


if __name__ == "__main__":
    unittest.main()
