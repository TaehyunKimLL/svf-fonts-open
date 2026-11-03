#!/usr/bin/env python3
"""Tests of sdl_check.py: the dumps are built from expected() (no SDL needed). Run: python3 -I c/ports/sdl/test_sdl_check.py

The COracle tests compare expected() with the C library's own output (a host build of c/tests/svfdump.c) and FAIL when
there is no C compiler or make; SVF_SDL_CHECK_NO_C_ORACLE=1 turns them into visible skips (the summary says "skipped")."""

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "tools"))
import sdl_check  # noqa: E402
import vesa_lines  # noqa: E402

LINES = os.path.join(HERE, "sdl-lines.txt")
FACES = os.path.join(HERE, "..", "..", "..", "svf", "dos")
TABLE = vesa_lines.parse(LINES)
LITTLE = sys.byteorder == "little"


def rd(p):
    with open(p, "rb") as fh:
        return fh.read()


def wr(p, b):
    with open(p, "wb") as fh:
        fh.write(b)

# kind -> (bits per pixel, pitch at 63 wide rounded up to 4)
KINDS = {"xrgb8888": 32, "argb8888": 32, "rgb565": 16, "rgb555": 16, "bgr24": 24, "index8": 8, "alpha": 8}
GRAY = (1, 2, 4, 8)


def pitch_for(w, bits):
    return (((w * bits + 7) // 8) + 3) & ~3


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name="d.bin"):
        return os.path.join(self.tmp.name, name)

    def dump(self, kind, w=63, h=40, bits=None, lsb=False, big=None, threshold=128, **hdr):
        bits = bits or KINDS.get(kind)
        if big is None:   # a 16-bit dump is made in the host's byte order, as the port's is
            big = kind in ("rgb565", "rgb555") and not LITTLE
        pitch = w if kind == "alpha" else pitch_for(w, bits)    # the alpha buffer has pitch = w
        data = sdl_check.expected(TABLE, FACES, kind, w, h, pitch, threshold=threshold, gray_bits=bits, lsb_first=lsb,
                                  big_endian=big)
        p = self.path()
        sdl_check.write_dump(p, w, h, pitch, bits, data, kind=kind, lsb_first=lsb, big_endian=big, **hdr)
        return p, data, pitch

    def check(self, p, kind, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = sdl_check.main([p, "--kind", kind, "--lines", LINES, "--faces", FACES, *extra])
            except SystemExit as e:  # argparse
                rc = e.code
        return rc, out.getvalue(), err.getvalue()


class RoundTrip(Base):
    def test_every_kind(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                p, data, pitch = self.dump(kind)
                clear = sdl_check.expected(vesa_lines.Table(TABLE.colours, TABLE.background, []), FACES, kind, 63, 40,
                                           pitch, gray_bits=KINDS[kind], big_endian=kind[:3] == "rgb" and not LITTLE)
                self.assertNotEqual(data, clear, "nothing drawn")
                rc, out, err = self.check(p, kind)
                self.assertEqual(rc, 0, out + err)
                self.assertRegex(out, r"^sdl-check: OK %s 63x40 pitch=%d sdl3 sum=[0-9a-f]{8}\n$" % (kind, pitch))
                self.assertEqual(self.check(p, kind)[1], out)
                self.assertIn("sum=%08x" % vesa_lines.fnv1a(data), out)

    def test_gray_bits_and_order(self):
        for bits in GRAY:
            for lsb in (False, True):
                with self.subTest(bits=bits, lsb=lsb):
                    p, data, pitch = self.dump("gray", bits=bits, lsb=lsb)
                    rc, out, err = self.check(p, "gray")
                    self.assertEqual(rc, 0, out + err)
                    self.assertIn("pitch=%d" % pitch, out)
        a = self.dump("gray", bits=4, lsb=False)[1]
        b = self.dump("gray", bits=4, lsb=True)[1]
        self.assertNotEqual(a, b)

    def test_pitch_beyond_minimum_and_sdl2(self):
        p = self.path()
        data = sdl_check.expected(TABLE, FACES, "rgb565", 63, 40, 140, big_endian=not LITTLE)
        sdl_check.write_dump(p, 63, 40, 140, 16, data, kind="rgb565", sdl_major=2, big_endian=not LITTLE)
        rc, out, err = self.check(p, "rgb565")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("pitch=140 sdl2", out)

    def test_big_endian(self):
        data_be = sdl_check.expected(TABLE, FACES, "rgb565", 63, 40, 128, big_endian=True)
        data_le = sdl_check.expected(TABLE, FACES, "rgb565", 63, 40, 128)
        self.assertNotEqual(data_be, data_le)
        self.assertEqual(data_be[:2], TABLE.colours[TABLE.background].rgb565.to_bytes(2, "big"))
        for kind in ("rgb565", "rgb555"):
            with self.subTest(kind=kind):
                p, _, _ = self.dump(kind)                       # the host's order: checks
                self.assertEqual(self.check(p, kind)[0], 0)
                p, _, _ = self.dump(kind, big=LITTLE)           # the other order: refused (exit 2)
                self.assertEqual(self.check(p, kind)[0], 2)

    def test_alpha_draws_first_line_only(self):
        w, h = 300, 140      # lines 1 (baseline 40) and 2 (baseline 90) both reach the buffer
        a = sdl_check.expected(TABLE, FACES, "alpha", w, h, w)
        one = vesa_lines.Table(TABLE.colours, TABLE.background, TABLE.lines[:1])
        two = vesa_lines.Table(TABLE.colours, TABLE.background, TABLE.lines[1:2])
        self.assertEqual(a, sdl_check.expected(one, FACES, "alpha", w, h, w))
        self.assertTrue(any(a[:50 * w]))
        b = sdl_check.expected(two, FACES, "alpha", w, h, w)
        self.assertTrue(any(b[60 * w:]), "line 2 would draw below row 60")
        self.assertFalse(any(a[60 * w:]), "only line 1 is drawn")

    def test_alpha_pitch_must_be_w(self):
        p = self.path()
        data = sdl_check.expected(TABLE, FACES, "alpha", 63, 40, 64)
        sdl_check.write_dump(p, 63, 40, 64, 8, data, kind="alpha")
        rc, out, err = self.check(p, "alpha")
        self.assertEqual(rc, 2)
        self.assertIn("alpha pitch 64, must be the width 63", err)

    def test_ok_removes_stale_diff_png(self):
        p, data, pitch = self.dump("index8")
        png = p + ".diff.png"
        wr(png, b"stale")
        self.assertEqual(self.check(p, "index8")[0], 0)
        self.assertFalse(os.path.exists(png))
        mine = self.path("mine.png")
        wr(mine, b"stale")
        self.assertEqual(self.check(p, "index8", "--diff", mine)[0], 0)
        self.assertFalse(os.path.exists(mine))

    def test_background_and_padding(self):
        bg = TABLE.colours[TABLE.background]
        # nothing drawn: a table whose only line lies outside the surface
        empty = vesa_lines.Table(TABLE.colours, TABLE.background, [])
        e = lambda k, **kw: sdl_check.expected(empty, FACES, k, 3, 2, kw.pop("pitch"), **kw)
        px = bytes((bg.rgb888 & 255, bg.rgb888 >> 8 & 255, bg.rgb888 >> 16 & 255))
        self.assertEqual(e("xrgb8888", pitch=16), (px + b"\0") * 3 + bytes(4) + (px + b"\0") * 3 + bytes(4))
        self.assertEqual(e("argb8888", pitch=12)[:4], px + b"\xff")
        self.assertEqual(e("bgr24", pitch=12), (px * 3 + bytes(3)) * 2)
        self.assertEqual(e("index8", pitch=4), (bytes((bg.index_base,)) * 3 + b"\0") * 2)
        self.assertEqual(e("gray", pitch=2, gray_bits=4), bytes(4))
        self.assertEqual(e("rgb565", pitch=8)[:6], bg.rgb565.to_bytes(2, "little") * 3)
        self.assertEqual(e("rgb555", pitch=8)[6:8], b"\0\0")


class Failures(Base):
    def test_flipped_pixel_byte(self):
        for kind, (x, y) in (("xrgb8888", (5, 3)), ("gray", (20, 7))):
            with self.subTest(kind=kind):
                p, data, pitch = self.dump(kind, bits=4 if kind == "gray" else None)
                bits = 4 if kind == "gray" else 32
                i = y * pitch + x * bits // 8
                raw = bytearray(rd(p))
                raw[16 + i] ^= 0x10 if kind == "gray" else 0x01
                wr(p, raw)
                rc, out, err = self.check(p, kind)
                self.assertEqual(rc, 1, out + err)
                self.assertIn("sdl-check: DIFF %s byte %d pixel (%d,%d) got 0x%02X want 0x%02X" % (
                    kind, i, x, y, raw[16 + i], data[i]), out)
                self.assertTrue(os.path.exists(p + ".diff.png"))

    def test_diff_option_and_png_size(self):
        from PIL import Image
        p, data, pitch = self.dump("index8")
        raw = bytearray(rd(p))
        raw[16 + 10] ^= 0xFF
        wr(p, raw)
        png = self.path("my.png")
        rc, out, err = self.check(p, "index8", "--diff", png)
        self.assertEqual(rc, 1)
        im = Image.open(png)
        self.assertEqual(im.size, (pitch, 40))
        self.assertEqual(im.convert("RGB").getpixel((10, 0)), (255, 0, 0))

    def test_padding_bytes(self):
        # whole padding bytes after the 63 pixels of row 0 (alpha has none: its pitch is w)
        for kind, bits in (("bgr24", None), ("rgb565", None), ("index8", None), ("gray", 8)):
            with self.subTest(kind=kind):
                p, data, pitch = self.dump(kind, bits=bits)
                nb = KINDS.get(kind, bits) // 8 * 63
                self.assertGreater(pitch, nb, "no padding bytes in this case")
                raw = bytearray(rd(p))
                self.assertEqual(raw[16 + nb], 0)
                raw[16 + nb] = 1
                wr(p, raw)
                rc, out, err = self.check(p, kind)
                self.assertEqual(rc, 1, out + err)
                self.assertIn("byte %d padding row 0 got 0x01 want 0x00" % nb, out)

    def test_padding_bits_in_last_byte(self):
        for bits in (4, 2, 1):
            for lsb in (False, True):
                with self.subTest(bits=bits, lsb=lsb):
                    p, data, pitch = self.dump("gray", bits=bits, lsb=lsb)
                    nb = (63 * bits + 7) // 8
                    used = 63 * bits - 8 * (nb - 1)          # bits of the last byte holding pixels
                    pad = 8 - used
                    self.assertGreater(pad, 0)
                    # one padding pixel: the lowest bit of the byte MSB first, the highest bit LSB first
                    bit = 1 if not lsb else 1 << (8 - 1)
                    raw = bytearray(rd(p))
                    raw[16 + nb - 1] |= bit
                    wr(p, raw)
                    rc, out, err = self.check(p, "gray")
                    self.assertEqual(rc, 1, out + err)
                    self.assertIn("byte %d padding row 0 " % (nb - 1), out)

    def test_subbyte_pixel_named(self):
        # a flipped pixel inside a byte: the first differing pixel, by bit order
        for lsb in (False, True):
            p, data, pitch = self.dump("gray", bits=2, lsb=lsb)
            raw = bytearray(rd(p))
            i = 3 * pitch + 5                        # pixels 20..23 of row 3
            raw[16 + i] ^= (0x03 << (2 * 2)) if lsb else (0x03 << (8 - 2 * 3))   # pixel 22 (x), the 3rd of the byte
            wr(p, raw)
            rc, out, err = self.check(p, "gray")
            self.assertEqual(rc, 1)
            self.assertIn("byte %d pixel (22,3) " % i, out)

    def test_diff_png_failures_are_messages(self):
        p, data, pitch = self.dump("index8")
        raw = bytearray(rd(p))
        raw[16 + 10] ^= 0xFF
        wr(p, raw)
        for target in (self.path("x.unknownext"), os.path.join(self.tmp.name, "no", "such", "dir.png")):
            with self.subTest(target=target):
                rc, out, err = self.check(p, "index8", "--diff", target)
                self.assertEqual(rc, 1)
                self.assertIn("sdl-check: DIFF index8 byte 10 pixel (10,0) ", out)
                self.assertIn("sdl-check: cannot write %s: " % target, err)
                self.assertNotIn("Traceback", err)

    def test_argb_dump_as_xrgb(self):
        p, _, _ = self.dump("argb8888")
        rc, out, err = self.check(p, "xrgb8888")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("byte 3 ", out)

    def test_gray1_threshold(self):
        a = sdl_check.expected(TABLE, FACES, "gray", 160, 56, 20, threshold=128, gray_bits=1)
        b = sdl_check.expected(TABLE, FACES, "gray", 160, 56, 20, threshold=255, gray_bits=1)
        self.assertNotEqual(a, b)
        p = self.path()
        sdl_check.write_dump(p, 160, 56, 20, 1, a, kind="gray")
        self.assertEqual(self.check(p, "gray")[0], 0)
        self.assertEqual(self.check(p, "gray", "--threshold", "128")[0], 0)
        self.assertEqual(self.check(p, "gray", "--threshold", "255")[0], 1)


class BadInput(Base):
    def raw(self, mutate=None, kind="index8"):
        p, data, pitch = self.dump(kind)
        b = bytearray(rd(p))
        if mutate:
            mutate(b)
        wr(p, b)
        return p

    def rc(self, p, kind, *extra):
        rc, out, err = self.check(p, kind, *extra)
        self.assertTrue(err or rc == 2, "no message")
        return rc

    def test_palettised_flag(self):
        p = self.raw(lambda b: b.__setitem__(15, b[15] & ~2))
        self.assertEqual(self.rc(p, "index8"), 2)

    def test_header_vs_kind(self):
        cases = {
            "magic": (lambda b: b.__setitem__(slice(0, 8), b"SVFSDL2 "), "index8"),
            "bpp": (lambda b: b.__setitem__(14, 16), "index8"),
            "bpp3": (lambda b: b.__setitem__(14, 3), "index8"),
            "lsb on non-gray": (lambda b: b.__setitem__(15, b[15] | 4), "index8"),
            "alpha flag on index8": (lambda b: b.__setitem__(15, b[15] | 8), "index8"),
            "reserved 6": (lambda b: b.__setitem__(15, b[15] | 0x40), "index8"),
            "reserved 7": (lambda b: b.__setitem__(15, b[15] | 0x80), "index8"),
            "sdl major 4": (lambda b: b.__setitem__(15, b[15] | 0x20), "index8"),
            "be on 8 bit": (lambda b: b.__setitem__(15, b[15] | 1), "index8"),
            "short": (lambda b: b.__delitem__(slice(len(b) - 1, None)), "index8"),
            "long": (lambda b: b.append(0), "index8"),
            "tiny": (lambda b: b.__delitem__(slice(10, None)), "index8"),
            "pitch below row": (lambda b: b.__setitem__(slice(12, 14), (10).to_bytes(2, "little")), "index8"),
            "zero width": (lambda b: b.__setitem__(slice(8, 10), bytes(2)), "index8"),
        }
        for name, (mut, kind) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.rc(self.raw(mut), kind), 2)

    def test_reference_length_differs_from_dump(self):
        p, _, _ = self.dump("index8")
        real = sdl_check.expected
        for cut in (lambda w: w[:-1], lambda w: w + b"\0"):
            with self.subTest(cut=cut(b"ab")):
                sdl_check.expected = lambda *a, _c=cut, **k: _c(real(*a, **k))
                try:
                    rc, _, err = self.check(p, "index8")
                finally:
                    sdl_check.expected = real
                self.assertEqual(rc, 2)
                self.assertIn("reference is", err)
        self.assertEqual(self.check(p, "index8")[0], 0)

    def test_kind_mismatch_and_options(self):
        p = self.raw()
        for kind in ("xrgb8888", "alpha", "rgb565"):  # gray at 8 bits has the index8 header: a byte DIFF, not exit 2
            with self.subTest(kind=kind):
                self.assertEqual(self.rc(p, kind), 2)
        self.assertEqual(self.check(p, "bogus")[0], 2)
        self.assertEqual(self.check(p + ".none", "index8")[0], 2)
        self.assertEqual(self.check(p, "index8", "--threshold", "256")[0], 2)
        rc, _, _ = self.check(p, "index8", "--faces", self.tmp.name)
        self.assertEqual(rc, 2)            # a directory without the faces: a missing face
        rc, _, err = self.check(p, "index8", "--faces", p)   # a regular file
        self.assertEqual(rc, 2)
        self.assertIn("is not a directory", err)

    def test_gray_flags(self):
        p, _, _ = self.dump("gray", bits=2)
        self.assertEqual(self.check(p, "gray")[0], 0)
        b = bytearray(rd(p))
        b[15] &= ~2  # gray without the palettised flag
        wr(p, b)
        self.assertEqual(self.check(p, "gray")[0], 2)

    def test_alpha_flag_required(self):
        p, _, _ = self.dump("alpha")
        b = bytearray(rd(p))
        b[15] &= ~8
        wr(p, b)
        self.assertEqual(self.check(p, "alpha")[0], 2)

    def test_bad_lines_file(self):
        p, _, _ = self.dump("index8")
        bad = self.path("bad.txt")
        wr(bad, b"[lines]\n")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = sdl_check.main([p, "--kind", "index8", "--lines", bad, "--faces", FACES])
        self.assertEqual(rc, 2)
        self.assertIn("line 1", err.getvalue())


class Dumps(unittest.TestCase):
    def test_header_layout(self):
        h = sdl_check.header(63, 40, 252, 32, kind="argb8888", sdl_major=3)
        self.assertEqual(h, b"SVFSDL1 " + (63).to_bytes(2, "little") + (40).to_bytes(2, "little") +
                         (252).to_bytes(2, "little") + bytes((32, 0x10)))
        h = sdl_check.header(8, 2, 4, 2, kind="gray", lsb_first=True, sdl_major=2)
        self.assertEqual(h[14:], bytes((2, 0x02 | 0x04)))
        h = sdl_check.header(8, 2, 8, 8, kind="alpha", sdl_major=3)
        self.assertEqual(h[15], 0x08 | 0x10)
        h = sdl_check.header(8, 2, 16, 16, kind="rgb565", big_endian=True, sdl_major=2)
        self.assertEqual(h[15], 0x01)

    def test_read_dump(self):
        raw = sdl_check.header(2, 1, 8, 32, kind="xrgb8888", sdl_major=3) + bytes(range(8))
        d = sdl_check.read_dump(raw)
        self.assertEqual((d.w, d.h, d.pitch, d.bpp, d.sdl_major, d.data), (2, 1, 8, 32, 3, bytes(range(8))))
        self.assertEqual((d.big_endian, d.palettised, d.lsb_first, d.alpha), (False,) * 4)
        with self.assertRaises(sdl_check.DumpError):
            sdl_check.read_dump(raw[:-1])

    def test_cli_isolated(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "d.bin")
            data = sdl_check.expected(TABLE, FACES, "bgr24", 20, 20, 60)
            sdl_check.write_dump(p, 20, 20, 60, 24, data, kind="bgr24")
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "sdl_check.py"), p, "--kind", "bgr24",
                                "--lines", LINES, "--faces", FACES], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.startswith("sdl-check: OK bgr24 20x20 pitch=60 sdl3 sum="))


def write_bmp(path, w, h, pix, bpp=24, top_down=False):
    """An uncompressed BMP as SDL_SaveBMP writes it: pix[y][x] = (r, g, b), bottom-up unless @p top_down."""
    step = bpp // 8
    stride = (w * step + 3) & ~3
    rows = [b"".join(bytes((b, g, r) + (0,) * (step - 3)) for (r, g, b) in row).ljust(stride, b"\0") for row in pix]
    body = b"".join(rows if top_down else rows[::-1])
    hdr = (b"BM" + (54 + len(body)).to_bytes(4, "little") + bytes(4) + (54).to_bytes(4, "little") +
           (40).to_bytes(4, "little") + w.to_bytes(4, "little") + (-h if top_down else h).to_bytes(4, "little", signed=True) +
           (1).to_bytes(2, "little") + bpp.to_bytes(2, "little") + bytes(24))
    with open(path, "wb") as fh:
        fh.write(hdr + body)


def indices(raw, w, h, pitch, bits, lsb):
    """pix[y][x] = palette index of a dump body, decoded pixel by pixel (the test's own decoder)."""
    out = []
    for y in range(h):
        row = []
        for x in range(w):
            byte = raw[y * pitch + x * bits // 8]
            sh = (x * bits) % 8 if lsb else 8 - bits - (x * bits) % 8
            row.append(byte >> sh & ((1 << bits) - 1))
        out.append(row)
    return out


class ShotPalette(Base):
    """--shot: the window shot must show palette[dump index], the palette computed here, not read from the port."""

    def shot(self, data, w, h, pitch, bits, lsb, pal, name="s.bmp", **kw):
        idx = indices(data, w, h, pitch, bits, lsb)
        p = self.path(name)
        write_bmp(p, w, h, [[pal[v] for v in row] for row in idx], **kw)
        return p

    def cases(self):
        yield "index8", 8, False
        for bits in GRAY:
            for lsb in (False, True):
                yield "gray", bits, lsb

    def test_palette_for_values(self):
        self.assertEqual(sdl_check.palette_for(TABLE, "gray", 1), [(0, 0, 132), (255, 255, 255)])
        self.assertEqual(sdl_check.palette_for(TABLE, "gray", 2)[1], (85, 85, 173))
        self.assertEqual(len(sdl_check.palette_for(TABLE, "gray", 8)), 256)
        pal = sdl_check.palette_for(TABLE, "index8")
        self.assertEqual((len(pal), pal[0], pal[16]), (256, (0, 0, 132), (0, 0, 132)))
        self.assertEqual(pal[19], (255, 255, 255))   # white: index_base 16, 3 levels

    def test_right_palette_passes(self):
        for kind, bits, lsb in self.cases():
            for bpp, td in ((24, False), (32, True)):
                with self.subTest(kind=kind, bits=bits, lsb=lsb, bmp=bpp):
                    p, data, pitch = self.dump(kind, w=41, h=30, bits=bits, lsb=lsb)
                    pal = sdl_check.palette_for(TABLE, kind, bits)
                    bmp = self.shot(data, 41, 30, pitch, bits, lsb, pal, bpp=bpp, top_down=td)
                    rc, out, err = self.check(p, kind, "--shot", bmp)
                    self.assertEqual((rc, err), (0, ""), out)
                    self.assertIn(" shot=ok sum=", out)

    def wrong(self, pal):
        yield "r/b swapped", [(b, g, r) for (r, g, b) in pal]
        yield "ramp inverted", pal[::-1]
        yield "one entry off", pal[:-1] + [(pal[-1][0], pal[-1][1], pal[-1][2] ^ 1)]

    def test_wrong_palette_fails(self):
        for kind, bits, lsb in self.cases():
            p, data, pitch = self.dump(kind, w=41, h=30, bits=bits, lsb=lsb)
            idx = {v for row in indices(data, 41, 30, pitch, bits, lsb) for v in row}
            pal = sdl_check.palette_for(TABLE, kind, bits)
            for name, bad in self.wrong(pal):
                if all(bad[v] == pal[v] for v in idx):    # a mutation no pixel shows cannot be seen
                    continue
                with self.subTest(kind=kind, bits=bits, lsb=lsb, mutation=name):
                    bmp = self.shot(data, 41, 30, pitch, bits, lsb, bad)
                    rc, out, err = self.check(p, kind, "--shot", bmp)
                    self.assertEqual(rc, 1, out + err)
                    self.assertIn("sdl-check: DIFF palette %s pixel" % kind, out)

    def test_transposed_bit_order_fails(self):
        p, data, pitch = self.dump("gray", w=41, h=30, bits=2, lsb=False)
        pal = sdl_check.palette_for(TABLE, "gray", 2)
        bmp = self.shot(data, 41, 30, pitch, 2, True, pal)   # the shot as if the surface read LSB first
        rc, out, _ = self.check(p, "gray", "--shot", bmp)
        self.assertEqual(rc, 1, out)

    def test_bad_shots(self):
        p, data, pitch = self.dump("index8", w=41, h=30)
        pal = sdl_check.palette_for(TABLE, "index8")
        self.assertEqual(self.check(p, "index8", "--shot", self.path("none.bmp"))[0], 2)
        wr(self.path("junk.bmp"), b"not a bmp" * 10)
        self.assertEqual(self.check(p, "index8", "--shot", self.path("junk.bmp"))[0], 2)
        small = self.shot(data, 41, 30, pitch, 8, False, pal)
        write_bmp(small, 40, 30, [[(0, 0, 0)] * 40] * 30)
        rc, out, _ = self.check(p, "index8", "--shot", small)
        self.assertEqual(rc, 1, out)
        self.assertIn("shot is 40x30", out)
        q, _, _ = self.dump("rgb565")
        self.assertEqual(self.check(q, "rgb565", "--shot", small)[0], 2)


# --- the independent oracle: the C library's own output -------------------------------------------------------------

C_DIR = os.path.join(HERE, "..", "..")      # c/
_c = {}


def svfdump():
    """The path of a host build of c/tests/svfdump.c, or SkipTest when there is no toolchain."""
    if "exe" not in _c:
        cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("gcc")
        if not cc or not shutil.which("make"):
            if os.environ.get("SVF_SDL_CHECK_NO_C_ORACLE") == "1":
                raise unittest.SkipTest("no C compiler or make; skipped because SVF_SDL_CHECK_NO_C_ORACLE=1")
            raise AssertionError("no C compiler or make on this host: the C oracle needs them "
                                 "(set SVF_SDL_CHECK_NO_C_ORACLE=1 to skip these tests)")
        _c["dir"] = tempfile.mkdtemp(prefix="svf-sdlcheck-")
        r = subprocess.run(["make", "-s", "-C", C_DIR, "O=" + _c["dir"], "svfdump"], capture_output=True, text=True)
        if r.returncode:
            raise AssertionError("make -C c svfdump failed:\n" + r.stdout + r.stderr)
        _c["exe"] = os.path.join(_c["dir"], "svfdump")
    return _c["exe"]


def tearDownModule():
    if "dir" in _c:
        shutil.rmtree(_c.pop("dir"), ignore_errors=True)


def one_line_tables():
    """Tables of one line each: the four scale/colour cases of sdl-lines.txt, short texts that fit 61 x 34."""
    by = {c.name: i for i, c in enumerate(TABLE.colours)}
    out = []
    for colour, (num, den), text, faces in (("white", (1, 1), "SVF 가나다 Aq", ["PAPLG16.SVF", "PAPLG18.SVF"]),
                                           ("white", (1, 1), "가힣 Ag", ["MARUS24A.SVF"]),
                                           ("scaled", (3, 2), "가나 Ag", ["PAPLG16.SVF", "PAPLG18.SVF"]),
                                           ("yellow", (1, 1), "만나 Rt", ["PAPLG16.SVF", "PAPLG18.SVF"])):
        line = vesa_lines.Line(faces, num, den, by[colour], 3, 24, text, 1)
        out.append((colour, vesa_lines.Table(TABLE.colours, TABLE.background, [line])))
    return out


class COracle(unittest.TestCase):
    """expected() on small one-line tables (odd width, pitch beyond the row) against `svfdump line --target=K`, the
    library's own output, so a wrong stride, colour, ramp or byte order in expected() fails here (not only a mismatch
    between expected() and itself). The C output is a drawing on a uniform fill; the colour kinds blend without reading
    the destination, so two fills (0 and 0xFF) tell the bytes the line touched from the others, which must be the
    background in expected()."""

    W, H = 61, 34

    def c_line(self, table, kind, pitch, opts, fill):
        l = table.lines[0]
        cmd = [svfdump(), "--target=" + kind, "--stride=%d" % pitch, "--fill=%d" % fill] + opts
        if (l.num, l.den) != (1, 1):
            cmd.append("--scale=%d/%d" % (l.num, l.den))
        cmd += ["line", str(self.W), str(self.H), str(l.x), str(l.baseline), l.text] + [
            os.path.join(FACES, f) for f in l.faces]
        r = subprocess.run(cmd, capture_output=True)
        self.assertEqual(r.returncode, 0, (cmd, r.stderr))
        return r.stdout

    def want_got(self, table, kind, pitch, copts, **kw):
        want = sdl_check.expected(table, FACES, kind, self.W, self.H, pitch, **kw)
        blank = sdl_check.expected(vesa_lines.Table(table.colours, table.background, []), FACES, kind, self.W, self.H,
                                   pitch, **kw)
        got0 = self.c_line(table, SVF[kind], pitch, copts, 0)
        self.assertEqual(len(got0), pitch * self.H)
        if kind in ("index8", "gray", "alpha"):   # max rule: the destination is read; the background is 0
            self.assertEqual(blank, bytes(len(blank)))
            return want, got0
        gotf = self.c_line(table, SVF[kind], pitch, copts, 255)
        touched = [a == b for a, b in zip(got0, gotf)]   # untouched bytes keep their fill, which differs
        self.assertTrue(any(touched), "the line drew nothing")
        merged = bytes(g if t else b for g, t, b in zip(got0, touched, blank))   # untouched bytes: the clear
        return want, merged

    def run_kind(self, kind, copts_of, **kw):
        for name, table in one_line_tables():
            with self.subTest(kind=kind, line=name):
                bits = kw.get("gray_bits", {"xrgb8888": 32, "argb8888": 32, "rgb565": 16, "rgb555": 16, "bgr24": 24}.get(kind, 8))
                pitch = (self.W * bits + 7) // 8 + 5
                c = table.colours[table.lines[0].colour]
                want, got = self.want_got(table, kind, pitch, copts_of(c, table.colours[table.background]), **kw)
                self.assertEqual(got, want)

    def test_xrgb8888(self):
        self.run_kind("xrgb8888", lambda c, b: ["--fg888=%d" % c.rgb888, "--bg888=%d" % b.rgb888])

    def test_argb8888(self):
        self.run_kind("argb8888", lambda c, b: ["--fg888=%d" % (c.rgb888 | 0xFF000000), "--bg888=%d" % b.rgb888])

    def test_bgr24(self):
        self.run_kind("bgr24", lambda c, b: ["--fg888=%d" % c.rgb888, "--bg888=%d" % b.rgb888])

    def test_rgb565(self):
        self.run_kind("rgb565", lambda c, b: NATIVE + ["--fg=%d" % c.rgb565, "--bg=%d" % b.rgb565],
                      big_endian=not LITTLE)

    def test_rgb555(self):
        self.run_kind("rgb555", lambda c, b: NATIVE + ["--fg=%d" % c.rgb555, "--bg=%d" % b.rgb555],
                      big_endian=not LITTLE)

    def test_big_endian(self):   # the flag gives big-endian bytes on any host
        for kind, f in (("rgb565", lambda c, b: ["--big-endian", "--fg=%d" % c.rgb565, "--bg=%d" % b.rgb565]),
                        ("rgb555", lambda c, b: ["--big-endian", "--fg=%d" % c.rgb555, "--bg=%d" % b.rgb555])):
            self.run_kind(kind, f, big_endian=True)

    def test_index8(self):
        for th in (1, 128, 255):
            self.run_kind("index8", lambda c, b, th=th: ["--index-base=%d" % c.index_base,
                                                         "--index-levels=%d" % c.index_levels,
                                                         "--threshold=%d" % th], threshold=th)

    def test_gray(self):
        for bits in GRAY:
            for lsb in (False, True):
                for th in (1, 128, 255):
                    self.run_kind("gray", lambda c, b, bits=bits, lsb=lsb, th=th: [
                        "--gray-bits=%d" % bits, "--threshold=%d" % th] + (["--lsb-first"] if lsb else []),
                                  gray_bits=bits, lsb_first=lsb, threshold=th)

    def test_alpha(self):
        self.run_kind("alpha", lambda c, b: [])


@unittest.skipUnless(LITTLE, "the shot tests build little-endian 16 bit dumps")
class TestShots(Base):
    """sdl_shots.py: the window shot (BMP) against the dump, as SDL shows it; built from expected(), no SDL needed."""
    W, H = 200, 100

    def rgb_of(self, kind, data, pitch, bits=8, mode="exact"):
        """The expected [(r, g, b)] of a dump, written out here independently of sdl_shots.py."""
        px = []
        pal = None
        if kind == "index8":
            pal = sdl_check.palette_for(TABLE, "index8")
        elif kind == "gray":
            pal = sdl_check.palette_for(TABLE, "gray", bits)
        for y in range(self.H):
            row = data[y * pitch:(y + 1) * pitch]
            for x in range(self.W):
                if kind in ("xrgb8888", "argb8888"):
                    px.append((row[4 * x + 2], row[4 * x + 1], row[4 * x]))
                elif kind == "rgb565":
                    v = row[2 * x] | row[2 * x + 1] << 8
                    r, g, b = v >> 11, v >> 5 & 63, v & 31
                    if mode == "exact":
                        px.append((r * 0x21 >> 2, g * 0x41 >> 4, b * 0x21 >> 2))
                    else:
                        px.append((r << 3, g << 2, b << 3))
                elif kind == "index8":
                    px.append(pal[row[x]])
                else:   # gray 4, MSB first
                    px.append(pal[row[x // 2] >> (4 if x % 2 == 0 else 0) & 15])
        return px

    def bmp(self, px, name="s.bmp"):
        from PIL import Image
        im = Image.new("RGB", (self.W, self.H))
        im.putdata(px)
        p = self.path(name)
        im.save(p)
        return p

    def shots(self, bmp, dump, kind, png=None, *extra):
        import sdl_shots
        png = png or self.path("o.png")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = sdl_shots.main([bmp, dump, "--kind", kind, "--png", png, "--lines", LINES, *extra])
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue(), err.getvalue(), png

    def make(self, kind, bits=None):
        bits = bits or {"xrgb8888": 32, "argb8888": 32, "rgb565": 16, "index8": 8, "gray": 4}[kind]
        pitch = pitch_for(self.W, bits)
        data = sdl_check.expected(TABLE, FACES, kind, self.W, self.H, pitch, gray_bits=bits)
        d = self.path("d.dump")
        sdl_check.write_dump(d, self.W, self.H, pitch, bits, data, kind=kind)
        return d, data, pitch, bits

    def test_exact_every_kind(self):
        from PIL import Image
        for kind in ("xrgb8888", "argb8888", "rgb565", "index8", "gray"):
            with self.subTest(kind=kind):
                d, data, pitch, bits = self.make(kind)
                px = self.rgb_of(kind, data, pitch, bits)
                rc, out, err, png = self.shots(self.bmp(px), d, kind)
                self.assertEqual((rc, err), (0, ""), out)
                self.assertRegex(out, r"^sdl-shots: %s %dx%d exact\b" % (kind, self.W, self.H))
                with Image.open(png) as im:
                    self.assertEqual(im.size, (self.W, self.H))
                    self.assertEqual(list(im.convert("RGB").getdata()), px)

    def test_rgb565_shl_is_not_a_failure(self):
        d, data, pitch, bits = self.make("rgb565")
        px = self.rgb_of("rgb565", data, pitch, mode="shl")
        rc, out, err, _ = self.shots(self.bmp(px), d, "rgb565")
        self.assertEqual(rc, 0, out + err)
        self.assertIn(" shl ", out)
        self.assertRegex(out, r"differs=[1-9][0-9]*")

    def rgb565_shot(self, delta):
        """(dump, bmp pixels): the exact expansion with every channel of every pixel moved by @p delta (clamped)."""
        d, data, pitch, bits = self.make("rgb565")
        px = [tuple(min(255, c + delta) for c in p) for p in self.rgb_of("rgb565", data, pitch)]
        return d, px

    def test_rgb565_tolerance_one_level(self):   # SDL2's own expansion: at most one level off, printed with the maximum
        d, px = self.rgb565_shot(1)
        rc, out, err, _ = self.shots(self.bmp(px), d, "rgb565")
        self.assertEqual(rc, 0, out + err)
        self.assertRegex(out, r" tolerance differs=[1-9][0-9]* maxdev=1 ")

    def test_rgb565_beyond_tolerance_fails(self):
        for delta in (2, 9):
            with self.subTest(delta=delta):
                d, px = self.rgb565_shot(delta)
                rc, out, err, _ = self.shots(self.bmp(px), d, "rgb565")
                self.assertEqual(rc, 1, out + err)
                self.assertIn("no expansion rule explains it", out)

    @staticmethod
    def bitfields(w, h, rows, top_down, header=124):
        """A 32 bit BI_BITFIELDS BMP as SDL3 writes it (masks R, G, B after the 40 byte header), @p rows top row first."""
        off = 14 + header
        hdr = (b"BM" + (off + 4 * w * h).to_bytes(4, "little") + bytes(4) + off.to_bytes(4, "little") +
               header.to_bytes(4, "little") + w.to_bytes(4, "little") + (-h if top_down else h).to_bytes(4, "little", signed=True) +
               (1).to_bytes(2, "little") + (32).to_bytes(2, "little") + (3).to_bytes(4, "little") +
               (4 * w * h).to_bytes(4, "little") + bytes(16) +
               (0xFF0000).to_bytes(4, "little") + (0xFF00).to_bytes(4, "little") + (0xFF).to_bytes(4, "little") +
               (0).to_bytes(4, "little"))
        hdr += bytes(off - len(hdr))
        order = rows if top_down else rows[::-1]
        return hdr + b"".join(bytes((b, g, r, 0)) for row in order for r, g, b in row)

    def test_bitfields_bmp(self):   # what SDL3 writes for a 32 bit window: BI_BITFIELDS
        w, h = 3, 2
        rows = [[(1, 2, 3), (4, 5, 6), (7, 8, 9)], [(10, 11, 12), (13, 14, 15), (16, 17, 18)]]
        p = self.path("bf.bmp")
        wr(p, self.bitfields(w, h, rows, True))
        self.assertEqual(sdl_check.read_bmp(p), (w, h, rows))
        # as SDL writes it: bottom-up (positive height), an odd width, a V4 header (pixel data at 122)
        w, h = 5, 3
        rows = [[(y * 16 + x, 255 - x, 7 * y) for x in range(w)] for y in range(h)]
        wr(p, self.bitfields(w, h, rows, False, header=108))
        self.assertEqual(sdl_check.read_bmp(p), (w, h, rows))

    def test_bmp_pixel_offset_inside_headers(self):
        w, h = 2, 1
        raw = bytearray(self.bitfields(w, h, [[(1, 2, 3), (4, 5, 6)]], True))
        raw[10:14] = (20).to_bytes(4, "little")    # the pixels "start" inside the info header
        p = self.path("off.bmp")
        wr(p, bytes(raw))
        self.assertRaises(sdl_check.DumpError, sdl_check.read_bmp, p)

    def test_uniform_wrong_colour_is_named(self):
        d, data, pitch, bits = self.make("xrgb8888")
        rc, out, err, _ = self.shots(self.bmp([(255, 255, 255)] * (self.W * self.H)), d, "xrgb8888")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("uniformly #FFFFFF, not the table's background #000084", out)

    def test_window_depth_list(self):   # window_deep.sh: an explicit list, not a suffix test
        sh = os.path.join(HERE, "window_deep.sh")
        for name, deep in (("XRGB8888", 1), ("RGB888", 1), ("ARGB8888", 1), ("BGRX8888", 1), ("RGB24", 1), ("BGR24", 1),
                           ("RGBA32", 1), ("XRGB2101010", 1), ("RGB332", 0), ("RGB565", 0), ("XRGB1555", 0),
                           ("INDEX8", 0), ("RGB444", 0), ("UNKNOWN", 0)):
            with self.subTest(name=name):
                line = "svfsdl: SDL 2.30.0 driver x11 window SDL_PIXELFORMAT_%s back SDL_PIXELFORMAT_INDEX8 pitch 640" % name
                r = subprocess.run(["sh", "-c", '. "$1"; w=$(window_of "$2"); echo "$w"; window_deep "$w"', "sh", sh, line],
                                   capture_output=True, text=True)
                self.assertEqual(r.stdout.strip(), "SDL_PIXELFORMAT_" + name)
                self.assertEqual(r.returncode == 0, bool(deep), line)

    def test_blank_shot_fails(self):
        d, data, pitch, bits = self.make("xrgb8888")
        bg = self.rgb_of("xrgb8888", data, pitch)[0]
        # the dump is blank too, so only the 1 % rule can catch it
        blank = bytes(data[:4]) * (len(data) // 4)
        sdl_check.write_dump(d, self.W, self.H, pitch, 32, blank, kind="xrgb8888")
        rc, out, err, _ = self.shots(self.bmp([bg] * (self.W * self.H)), d, "xrgb8888")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("blank", out + err)

    def test_wrong_picture_and_size_fail(self):
        d, data, pitch, bits = self.make("xrgb8888")
        px = self.rgb_of("xrgb8888", data, pitch)
        bad = list(px)
        bad[5000] = (1, 2, 3)
        rc, out, err, _ = self.shots(self.bmp(bad), d, "xrgb8888")
        self.assertEqual(rc, 1, out + err)
        self.assertIn("DIFF", out)
        from PIL import Image
        Image.new("RGB", (self.W + 1, self.H)).save(self.path("w.bmp"))
        rc, out, err, _ = self.shots(self.path("w.bmp"), d, "xrgb8888")
        self.assertEqual(rc, 1, out + err)

    def test_usage_errors(self):
        d, data, pitch, bits = self.make("xrgb8888")
        b = self.bmp(self.rgb_of("xrgb8888", data, pitch))
        self.assertEqual(self.shots(b, d, "nokind")[0], 2)
        self.assertEqual(self.shots(self.path("none.bmp"), d, "xrgb8888")[0], 2)
        self.assertEqual(self.shots(b, self.path("none.dump"), "xrgb8888")[0], 2)
        self.assertEqual(self.shots(b, d, "rgb565")[0], 2)    # the dump says 32 bits

    def test_compare(self):
        import sdl_shots
        from PIL import Image
        a, b = self.path("a.png"), self.path("b.png")
        Image.new("RGB", (4, 3), (1, 2, 3)).save(a)
        Image.new("RGB", (4, 3), (1, 2, 3)).save(b)
        self.assertEqual(sdl_shots.differing_pixels(a, b), 0)
        with Image.open(b) as im:
            im.load()
        im.putpixel((1, 1), (9, 9, 9))
        im.save(b)
        self.assertEqual(sdl_shots.differing_pixels(a, b), 1)

    def test_overview(self):
        import sdl_shots
        from PIL import Image
        d = self.path("shots")
        os.mkdir(d)
        for s in (2, 3):
            for k in ("xrgb8888", "argb8888", "rgb565", "index8", "gray4"):
                Image.new("RGB", (64, 48), (s * 40, 9, 9)).save(os.path.join(d, "sdl%d-%s.png" % (s, k)))
        o = self.path("ov.png")
        sdl_shots.overview(d, o)
        with Image.open(o) as im:
            self.assertGreater(im.size[0], 5 * 32)    # the cells are shown at half size
            self.assertGreater(im.size[1], 2 * 24)


NATIVE = [] if LITTLE else ["--big-endian"]     # the 16-bit kinds as the dump of this host has them
SVF = {"xrgb8888": "xrgb8888", "argb8888": "xrgb8888", "bgr24": "rgb888", "rgb565": "rgb565", "rgb555": "rgb555",
       "index8": "indexed8", "gray": "gray", "alpha": "gray8"}


if __name__ == "__main__":
    unittest.main()
