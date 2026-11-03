"""Tests for screens.py (the screen text table) and screen_ref.py (the reference frame of the emulated panels)."""
import contextlib
import copy
import io
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import svfline  # noqa: E402
import screens  # noqa: E402
import screen_ref  # noqa: E402

SVF = os.path.join(ROOT, "svf")
PAPLG = [os.path.join(SVF, "dos", "PAPLG16.SVF"), os.path.join(SVF, "dos", "PAPLG18.SVF")]
MONO = [os.path.join(SVF, "dos", "NEODG16G.SVF")]
CLI = os.path.join(HERE, "screen_ref.py")

# the spec's text table: (faces, missing_advance, string, width)
WIDTHS = [
    (PAPLG, 6, "Pico ST7789 RGB565", 178), (PAPLG, 6, "ESP32-C3 ILI9341 RGB565", 227),
    (PAPLG, 6, "ESP32-S3 ILI9341 RGB565", 225), (PAPLG, 6, "다람쥐 헌 쳇바퀴에 타고파!", 222),
    (PAPLG, 6, "키스의 고유조건은 입술끼리", 228), (PAPLG, 6, "만나야 하고 특별한 기술은", 216),
    (PAPLG, 6, "필요치 않다.", 101),
    (PAPLG, 6, "Pico GRAY8", 97), (PAPLG, 6, "ESP32 GRAY8", 116), (PAPLG, 6, "ESP32-S3 GRAY8", 144),
    (PAPLG, 6, "다람쥐 헌", 78), (PAPLG, 6, "쳇바퀴에", 72), (PAPLG, 6, "타고파!", 60), (PAPLG, 6, "안녕하세요", 90),
    (MONO, 0, "Pico SVF 예제", 104), (MONO, 0, "ESP32 SVF 예제", 112), (MONO, 0, "다람쥐 헌 쳇바퀴", 128),
    (MONO, 0, "에 타고파! 1bpp", 120), (MONO, 0, "안녕하세요", 80),
    (MONO, 0, "CH582 SVF 예제", 112),
]
REFS = [("pico", "colour", None, 115200), ("pico", "grey", None, 8192), ("pico", "mono", None, 1024),
        ("esp32c3", "colour", None, 153600), ("esp32s3", "colour", None, 153600),
        ("esp32c3", "colour", 1, 153600), ("ch582", "mono", None, 1024)]


class TestScreens(unittest.TestCase):
    def test_widths_fit(self):
        self.assertEqual(screens.check(), [])
        self.assertEqual(len(WIDTHS), 20)
        for faces, adv, text, width in WIDTHS:
            self.assertEqual(svfline.measure(faces, text, missing_advance=adv)[0], width, text)

    def test_table_strings_are_the_spec_strings(self):
        self.assertEqual(screens.lines("pico", "colour")[0], "Pico ST7789 RGB565")
        self.assertEqual(screens.lines("ch582", "mono")[0], "CH582 SVF 예제")
        self.assertEqual(screens.lines("esp32c3", "colour")[0], "ESP32-C3 ILI9341 RGB565")
        self.assertEqual(screens.lines("esp32s3", "colour")[0], "ESP32-S3 ILI9341 RGB565")
        self.assertEqual(screens.lines("esp32c3", "grey"), screens.lines("esp32s3", "grey"))
        self.assertEqual(screens.lines("esp32c3", "mono"), screens.lines("esp32s3", "mono"))
        self.assertEqual(screens.lines("pico", "grey")[0], "Pico GRAY8")
        self.assertEqual(screens.lines("esp32s3", "grey")[0], "ESP32 GRAY8")
        self.assertEqual(screens.lines("esp32s3", "mono")[0], "ESP32 SVF 예제")
        self.assertEqual([len(screens.lines("pico", p)) for p in ("colour", "grey", "mono")], [5, 5, 4])

    def test_missing_advance(self):
        self.assertEqual([screens.PROFILES[p]["missing_advance"] for p in ("colour", "grey", "mono")], [6, 6, 0])
        self.assertEqual(screens.BIGENDIAN, {"pico": 1, "esp32c3": 0, "esp32s3": 0, "ch582": 0})

    def test_ref_sizes(self):
        for board, profile, be, size in REFS:
            self.assertEqual(len(screen_ref.build_ref(board, profile, be)), size, (board, profile, be))

    def test_colour_background(self):
        for board, bg in (("pico", b"\x00\x10"), ("esp32c3", b"\x10\x00")):
            ref = screen_ref.build_ref(board, "colour")
            w = screens.PROFILES["colour"]["w"][board]
            bands = [range(16 + 28 * i, 16 + 28 * i + 24) for i in range(5)]
            inside = {y for b in bands for y in b}
            for y in range(240):
                row = ref[y * w * 2:(y + 1) * w * 2]
                if y in inside:
                    continue
                self.assertEqual(row, bg * w, (board, y))
            # text is there: a band holds at least one non-bg pixel
            self.assertNotEqual(ref[16 * w * 2:40 * w * 2], bg * (24 * w))

    def test_colour_byte_order(self):
        be, le = screen_ref.build_ref("esp32c3", "colour", 1), screen_ref.build_ref("esp32c3", "colour", 0)
        swapped = bytearray(le)
        swapped[0::2], swapped[1::2] = le[1::2], le[0::2]
        self.assertEqual(bytes(swapped), be)

    def test_mono_matches_svfline_layout(self):
        # an independent route: GRAY8 per line from svfline.layout, thresholded, packed into pages here
        self.assertEqual(screens.PROFILES["mono"]["threshold"], 128)
        for board in screens.BOARDS:
            gray = bytearray(128 * 64)
            for text, base in zip(screens.lines(board, "mono"), (12, 28, 44, 60)):
                g = svfline.layout(MONO, text, 0, base, 128, 64, missing_advance=0)
                for i, v in enumerate(g):
                    gray[i] = max(gray[i], v)
            want = bytearray(1024)
            for y in range(64):
                for x in range(128):
                    if gray[y * 128 + x] >= 128:
                        want[(y >> 3) * 128 + x] |= 1 << (y & 7)
            self.assertTrue(any(want))
            self.assertEqual(screen_ref.build_ref(board, "mono"), bytes(want), board)

    def test_grey_packing(self):
        self.assertEqual(screen_ref.pack_gray8(bytes([0xFF, 0x50, 0x00, 0x1F]), 4, 1), bytes([0xF5, 0x01]))

    def test_grey_gray8_frame(self):
        g = screen_ref.build_gray8("pico")
        self.assertEqual(len(g), 16384)
        self.assertEqual(screen_ref.pack_gray8(g, 128, 128), screen_ref.build_ref("pico", "grey"))
        self.assertTrue(any(g))  # kept: it ties the --gray8 frame to the packed panel reference

    def test_compare_reports_xy(self):
        ref = screen_ref.build_ref("pico", "colour")
        fb = bytearray(ref)
        fb[2 * (7 + 240 * 30)] ^= 1
        self.assertEqual(screen_ref.compare(ref, bytes(fb), "rgb565", 240), (2 * (7 + 240 * 30), 7, 30))
        self.assertIsNone(screen_ref.compare(ref, ref, "rgb565", 240))
        ref = screen_ref.build_ref("pico", "mono")
        fb = bytearray(ref)
        fb[130] ^= 1
        self.assertEqual(screen_ref.compare(ref, bytes(fb), "mono-page", 128), (130, 2, 8))
        ref = screen_ref.build_ref("pico", "grey")
        fb = bytearray(ref)
        fb[70] ^= 1
        self.assertEqual(screen_ref.compare(ref, bytes(fb), "gray4panel", 128), (70, 12, 1))

    def test_shows(self):
        self.assertEqual([screens.shows(p) for p in ("colour", "grey", "mono")], [15, 1, 1])


def write_ppm(path, ref565):
    """A PPM the way QEMU writes it: each little-endian 5/6/5 pixel with every channel replicated to 8 bits."""
    px = bytearray()
    for i in range(0, len(ref565), 2):
        v = ref565[i] | ref565[i + 1] << 8
        r, g, b = v >> 11, v >> 5 & 63, v & 31
        px += bytes((r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2))
    with open(path, "wb") as f:
        f.write(b"P6\n320 240\n255\n" + bytes(px))


def run_cli(*args, preexec=None):
    return subprocess.run([sys.executable, "-I", CLI, *args], capture_output=True, text=True, preexec_fn=preexec)


def limit_memory():
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))


class TestCli(unittest.TestCase):
    def test_cli_diff(self):
        with tempfile.TemporaryDirectory() as out:
            ref = screen_ref.build_ref("pico", "mono")
            bad = bytearray(ref)
            bad[130] ^= 1
            with open(os.path.join(out, "pico-mono.fb"), "wb") as f:
                f.write(bad)
            r = run_cli("pico", "mono", out)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn("differs at byte 130 (x 2, y 8)", r.stdout)
            for n in ("pico-mono.ref", "pico-mono-ref.png", "pico-mono-diff.png", "pico-mono.png"):
                self.assertTrue(os.path.exists(os.path.join(out, n)), n)
            with open(os.path.join(out, "pico-mono.fb"), "wb") as f:
                f.write(ref)
            r = run_cli("pico", "mono", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("screen-pico-mono: OK", r.stdout)
            self.assertFalse(os.path.exists(os.path.join(out, "pico-mono-diff.png")))

    def test_missing_fb_is_an_error(self):
        with tempfile.TemporaryDirectory() as out:
            r = run_cli("pico", "mono", out)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("pico-mono.fb", r.stderr)

    def test_ref_only_writes_no_fb_compare(self):
        with tempfile.TemporaryDirectory() as out:
            r = run_cli("--ref-only", "--bigendian", "0", "esp32c3", "colour", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(os.path.getsize(os.path.join(out, "esp32c3-colour.ref")), 153600)
            self.assertTrue(os.path.exists(os.path.join(out, "esp32c3-colour-ref.png")))
            self.assertFalse(os.path.exists(os.path.join(out, "esp32c3-colour.png")))
            with open(os.path.join(out, "esp32c3-colour.ref"), "rb") as f:
                self.assertEqual(f.read(), screen_ref.build_ref("esp32c3", "colour", 0))

    def test_ref_only_gray8(self):
        with tempfile.TemporaryDirectory() as out:
            r = run_cli("--ref-only", "--gray8", "pico", "grey", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(out, "pico-grey.gray8.ref"), "rb") as f:
                self.assertEqual(f.read(), bytes(screen_ref.build_gray8("pico")))
            self.assertFalse(os.path.exists(os.path.join(out, "pico-grey.ref")))
            r = run_cli("--gray8", "pico", "grey", out)
            self.assertNotEqual(r.returncode, 0)  # --gray8 needs --ref-only

    def test_png_only_without_ppm(self):
        with tempfile.TemporaryDirectory() as out:
            ref = screen_ref.build_ref("esp32c3", "colour")
            with open(os.path.join(out, "esp32c3-colour.fb"), "wb") as f:
                f.write(ref)
            r = run_cli("--bigendian", "0", "esp32c3", "colour", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.exists(os.path.join(out, "esp32c3-colour.png")))
            os.remove(os.path.join(out, "esp32c3-colour.png"))
            write_ppm(os.path.join(out, "esp32c3-colour.ppm"), ref)
            r = run_cli("--bigendian", "0", "esp32c3", "colour", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(os.path.exists(os.path.join(out, "esp32c3-colour.png")))

    def test_ppm_compare(self):
        """The QEMU screendump (PPM) is compared with the 5/6/5-replicated reference; one pixel off must fail."""
        ref = screen_ref.build_ref("esp32c3", "colour", 0)
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "esp32c3-colour.fb"), "wb") as f:
                f.write(ref)
            ppm = os.path.join(out, "esp32c3-colour.ppm")
            write_ppm(ppm, ref)
            r = run_cli("--bigendian", "0", "esp32c3", "colour", out)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "screen-esp32c3-colour: OK"), r.stdout + r.stderr)
            with open(ppm, "rb") as f:
                data = bytearray(f.read())
            i = len(b"P6\n320 240\n255\n") + 3 * (320 * 100 + 7) + 2  # pixel (7, 100): one blue channel, one level off
            data[i] ^= 1
            with open(ppm, "wb") as f:
                f.write(bytes(data))
            r = run_cli("--bigendian", "0", "esp32c3", "colour", out)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertEqual(r.stdout.strip(), "screen-esp32c3-colour: ppm differs at x 7, y 100")
            write_ppm(ppm, ref[:-640] + bytes(640))  # the last row black: another pixel
            r = run_cli("--bigendian", "0", "esp32c3", "colour", out)
            self.assertEqual(r.returncode, 1)
            self.assertRegex(r.stdout.strip(), r"^screen-esp32c3-colour: ppm differs at x \d+, y 239$")
            with open(ppm, "wb") as f:  # a PPM of the wrong size
                f.write(b"P6\n1 1\n255\n\0\0\0")
            r = run_cli("--bigendian", "0", "esp32c3", "colour", out)
            self.assertEqual(r.returncode, 1)
            self.assertIn("ppm differs", r.stdout)

    def test_ppm_size_checked_before_load(self):
        """A PPM header may claim any size: mode and size are judged before the pixels are loaded or any
        decompression-bomb error can surface."""
        ref = screen_ref.build_ref("esp32c3", "colour", 0)
        with tempfile.TemporaryDirectory() as out:
            ppm = os.path.join(out, "x.ppm")
            with open(ppm, "wb") as f:  # claims 9000 x 9000, carries 3 bytes
                f.write(b"P6\n9000 9000\n255\n\0\0\0")
            self.assertIn("RGB 9000 x 9000, expected RGB 320 x 240", screen_ref.compare_ppm(ppm, ref, 320, 240, 0))
            with open(ppm, "wb") as f:  # past Pillow's decompression-bomb limit
                f.write(b"P6\n30000 30000\n255\n")
            self.assertTrue(screen_ref.compare_ppm(ppm, ref, 320, 240, 0).startswith("ppm differs"))
            with open(ppm, "wb") as f:  # a grey PGM of the right size
                f.write(b"P5\n320 240\n255\n" + bytes(320 * 240))
            self.assertIn("L 320 x 240", screen_ref.compare_ppm(ppm, ref, 320, 240, 0))

    def test_ppm_compare_primaries(self):
        """Red, green and blue at full level replicate to 255, and the compare says so (little-endian RGB565)."""
        ref = b"".join(v.to_bytes(2, "little") for v in (0xF800, 0x07E0, 0x001F, 0xFFFF)) * 2
        with tempfile.TemporaryDirectory() as out:
            ppm = os.path.join(out, "p.ppm")
            px = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)] * 2
            with open(ppm, "wb") as f:
                f.write(b"P6\n4 2\n255\n" + bytes(c for p in px for c in p))
            self.assertIsNone(screen_ref.compare_ppm(ppm, ref, 4, 2, 0))
            px[1] = (0, 254, 0)  # 6-bit green 63 is 255, not 254
            with open(ppm, "wb") as f:
                f.write(b"P6\n4 2\n255\n" + bytes(c for p in px for c in p))
            self.assertEqual(screen_ref.compare_ppm(ppm, ref, 4, 2, 0), "ppm differs at x 1, y 0")

    def test_screens_cli(self):
        s = os.path.join(HERE, "screens.py")
        r = subprocess.run([sys.executable, "-I", s, "lines", "esp32s3", "grey"], capture_output=True, text=True)
        self.assertEqual(r.stdout.splitlines()[0], "ESP32 GRAY8")
        r = subprocess.run([sys.executable, "-I", s, "shows", "colour"], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "15")
        r = subprocess.run([sys.executable, "-I", s, "--check"], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "screens: OK"))


def blend565(fg, bg, cov):
    """5/6/5 blend written out from the spec's rule (not svfline's code)."""
    out = 0
    for shift, mask in ((11, 31), (5, 63), (0, 31)):
        b, f = bg >> shift & mask, fg >> shift & mask
        out |= ((b * (255 - cov) + f * cov + 127) // 255) << shift
    return out


def pack_nibbles(gray, w, h):
    out = bytearray()
    for y in range(h):
        for x in range(0, w, 2):
            out.append(gray[y * w + x] & 0xF0 | gray[y * w + x + 1] >> 4)
    return bytes(out)


class TestLayoutPinned(unittest.TestCase):
    """Positions written here from the spec's text tables, not read from screens.py."""

    def test_colour_layout(self):
        fg, bg = 0xFFE0, 0x0010
        for board, w, order in (("pico", 240, "big"), ("esp32c3", 320, "little"), ("esp32s3", 320, "little")):
            ref = screen_ref.build_ref(board, "colour")
            want = bytearray(bg.to_bytes(2, order) * (w * 240))
            for i, text in enumerate(screens.lines(board, "colour")):
                y0 = 16 + 28 * i  # band top; band baseline 19; band 24 rows; x 8
                # rgb565 puts replace: a later cell's pixel wins (svfline.draw_target contract), so go cell by cell
                places = svfline.placements(svfline.load_chain(PAPLG), text, 8, y0 + 19, missing_advance=6)
                ink = 0
                for place in places:
                    for x, y, cov in svfline.cell_pixels(place, w, 240, clip=(0, y0, w, y0 + 24)):
                        want[2 * (y * w + x):2 * (y * w + x) + 2] = blend565(fg, bg, cov).to_bytes(2, order)
                        ink += 1
                self.assertTrue(ink, (board, i))  # the text is in its band
            self.assertEqual(ref, bytes(want), board)
            # nothing left of x = 8
            for y in range(240):
                self.assertEqual(ref[y * w * 2:(y * w + 8) * 2], bg.to_bytes(2, order) * 8, (board, y))

    def test_grey_layout(self):
        for board in screens.BOARDS:
            gray = bytearray(128 * 128)
            for text, base in zip(screens.lines(board, "grey"), (17, 41, 65, 89, 113)):
                g = svfline.layout(PAPLG, text, 4, base, 128, 128, missing_advance=6)
                for i, v in enumerate(g):
                    gray[i] = max(gray[i], v)
            self.assertTrue(any(gray))
            self.assertFalse(any(gray[0:128 * 3]))  # the first line's ascent is below row 3
            self.assertEqual(screen_ref.build_gray8(board), bytes(gray), board)
            self.assertEqual(screen_ref.build_ref(board, "grey"), pack_nibbles(gray, 128, 128), board)

    def test_clear_y_tiles_the_colour_panel(self):
        p = screens.PROFILES["colour"]
        self.assertEqual(p["clear_y"], list(range(0, 240, 24)))
        for y in p["text_y"]:  # firmware clears whole bands; each text band is inside the clear range
            self.assertLess(y + p["band_h"], 241)


class TestCheck(unittest.TestCase):
    def table(self):
        return copy.deepcopy(screens.PROFILES)

    def test_good_table(self):
        self.assertEqual(screens.check(self.table()), [])

    def test_x_term(self):
        t = self.table()
        # "키스의 고유조건은 입술끼리" is 228 px: fits at x 8 on 240, not at x 13
        t["colour"]["x"] = 13
        msgs = screens.check(t)
        self.assertTrue(any("키스의" in m and "pico" in m for m in msgs), msgs)
        t["colour"]["x"] = 12  # 228 + 12 = 240 still fits
        self.assertEqual([m for m in screens.check(t) if "pico/colour" in m], [])

    def test_width_rule(self):
        t = self.table()
        t["colour"]["w"]["pico"] = 200
        self.assertTrue(screens.check(t))

    def test_line_count_rule(self):
        t = self.table()
        t["grey"]["lines"]["pico"].append("extra")
        self.assertTrue(any("lines" in m for m in screens.check(t)))

    def test_descent_rule(self):
        t = self.table()
        t["grey"]["baselines"][-1] = 128  # baseline 128 + descent 1 passes the 128 rows
        self.assertTrue(any("descent" in m or "below" in m for m in screens.check(t)))

    def test_cli_check_fails_on_a_bad_table(self):
        saved = screens.PROFILES
        try:
            screens.PROFILES = self.table()
            screens.PROFILES["mono"]["w"]["pico"] = 100
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = screens.main(["--check"])
            self.assertEqual(rc, 1)
            self.assertIn("pico/mono", buf.getvalue())
            self.assertNotIn("screens: OK", buf.getvalue())
        finally:
            screens.PROFILES = saved


class TestValidation(unittest.TestCase):
    def test_pack_gray8(self):
        for args in ((bytes(4), 3, 1), (bytes(4), 0, 1), (bytes(4), 4, -1), (bytes(5), 4, 1), (bytes(3), 4, 1)):
            with self.assertRaises(ValueError, msg=args):
                screen_ref.pack_gray8(*args)

    def test_compare(self):
        ref = bytes(1024)
        for args in ((ref, bytes(1023), "mono-page", 128), (ref, ref, "mono-page", 0), (ref, ref, "gray8", 128),
                     (bytes(100), bytes(100), "mono-page", 128), (bytes(63), bytes(63), "gray4panel", 128),
                     (bytes(10), bytes(10), "gray4panel", 7)):
            with self.assertRaises(ValueError, msg=args):
                screen_ref.compare(*args)

    def test_geometry_from_the_table(self):
        self.assertEqual(screen_ref.geometry("esp32s3", "colour"), ("rgb565", 320, 240))
        self.assertEqual(screen_ref.geometry("pico", "grey"), ("gray4panel", 128, 128))
        self.assertEqual(screen_ref.geometry("pico", "mono"), ("mono-page", 128, 64))


def png_pixel_checks(tc, path, size, mode, points):
    from PIL import Image
    with open(path, "rb") as f:
        head = f.read(33)
    tc.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n")
    tc.assertEqual(head[12:16], b"IHDR")
    tc.assertEqual((int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")), size)
    with Image.open(path) as im:
        tc.assertEqual((im.size, im.mode), (size, mode))
        for xy, val in points:
            tc.assertEqual(im.getpixel(xy), val, (path, xy))


def rep565(v):
    r, g, b = v >> 11, v >> 5 & 63, v & 31
    return (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2)


class TestPng(unittest.TestCase):
    def test_png_content(self):
        with tempfile.TemporaryDirectory() as out:
            # mono: first set bit of the reference
            ref = screen_ref.build_ref("pico", "mono")
            i = next(k for k, b in enumerate(ref) if b)
            bit = (ref[i] & -ref[i]).bit_length() - 1
            x, y = i % 128, i // 128 * 8 + bit
            screen_ref.to_png("mono-page", 128, 64, ref).save(os.path.join(out, "m.png"))
            png_pixel_checks(self, os.path.join(out, "m.png"), (128, 64), "L", [((x, y), 255), ((0, 63), 0)])
            # grey: packed nibbles expanded by 17
            ref = screen_ref.build_ref("pico", "grey")
            i = next(k for k, b in enumerate(ref) if b >> 4 and b & 15)
            screen_ref.to_png("gray4panel", 128, 128, ref).save(os.path.join(out, "g.png"))
            x, y = i % 64 * 2, i // 64
            png_pixel_checks(self, os.path.join(out, "g.png"), (128, 128), "L",
                             [((x, y), (ref[i] >> 4) * 17), ((x + 1, y), (ref[i] & 15) * 17), ((0, 127), 0)])
            # colour: bg expanded, and an ink pixel
            ref = screen_ref.build_ref("esp32c3", "colour")
            k = next(k for k in range(0, len(ref), 2) if ref[k:k + 2] != b"\x10\x00")
            v = int.from_bytes(ref[k:k + 2], "little")
            screen_ref.to_png("rgb565", 320, 240, ref, 0).save(os.path.join(out, "c.png"))
            png_pixel_checks(self, os.path.join(out, "c.png"), (320, 240), "RGB",
                             [((0, 0), (0, 0, 132)), ((k // 2 % 320, k // 2 // 320), rep565(v))])

    def test_diff_png_marks_the_pixel(self):
        with tempfile.TemporaryDirectory() as out:
            ref = screen_ref.build_ref("pico", "mono")
            bad = bytearray(ref)
            bad[130] ^= 1  # pixel (2, 8)
            with open(os.path.join(out, "pico-mono.fb"), "wb") as f:
                f.write(bad)
            self.assertEqual(run_cli("pico", "mono", out).returncode, 1)
            g3, g0 = (ref[131] & 1) * 255, (ref[0] & 1) * 255
            png_pixel_checks(self, os.path.join(out, "pico-mono-diff.png"), (128, 64), "RGB",
                             [((2, 8), (255, 0, 0)), ((3, 8), (g3, g3, g3)), ((0, 0), (g0, g0, g0))])


class TestFbSize(unittest.TestCase):
    def run_with(self, out, fb, extra=()):
        with open(os.path.join(out, "pico-mono.fb"), "wb") as f:
            f.write(fb)
        return run_cli(*extra, "pico", "mono", out)

    def test_short_and_oversized_fb(self):
        ref = screen_ref.build_ref("pico", "mono")
        for name, fb in (("short", ref[:1000]), ("oversized", ref + b"\0" * 8)):
            with tempfile.TemporaryDirectory() as out:
                r = self.run_with(out, fb)
                self.assertEqual(r.returncode, 1, name)
                self.assertIn("differs", r.stdout)
                self.assertIn("%d bytes" % len(fb), r.stdout)
                self.assertIn("expected %d" % len(ref), r.stdout)
                self.assertTrue(os.path.exists(os.path.join(out, "pico-mono.png")), name)
                png_pixel_checks(self, os.path.join(out, "pico-mono-diff.png"), (128, 64), "RGB", [])

    def test_short_fb_marks_the_missing_area(self):
        ref = screen_ref.build_ref("pico", "mono")
        with tempfile.TemporaryDirectory() as out:
            self.run_with(out, ref[:1000])
            from PIL import Image
            with Image.open(os.path.join(out, "pico-mono-diff.png")) as im:
                self.assertEqual(im.getpixel((110, 63)), (255, 0, 0))  # bytes from 1000 (page 7, col 104) are missing
                self.assertEqual(im.getpixel((0, 0)), ((255,) * 3 if ref[0] & 1 else (0,) * 3))

    def test_short_fb_no_png_with_ppm(self):
        ref = screen_ref.build_ref("pico", "mono")
        with tempfile.TemporaryDirectory() as out:
            open(os.path.join(out, "pico-mono.ppm"), "wb").close()
            r = self.run_with(out, ref[:10])
            self.assertEqual(r.returncode, 1)
            self.assertFalse(os.path.exists(os.path.join(out, "pico-mono.png")))

    def test_stale_diff_removed_on_match(self):
        ref = screen_ref.build_ref("pico", "mono")
        with tempfile.TemporaryDirectory() as out:
            open(os.path.join(out, "pico-mono-diff.png"), "wb").close()
            r = self.run_with(out, ref)
            self.assertEqual(r.returncode, 0)
            self.assertFalse(os.path.exists(os.path.join(out, "pico-mono-diff.png")))


# the spec's text table, every board: (lines, widths). Shared lines follow the board line.
SPEC_TEXT = {
    ("colour", "pico"): ["Pico ST7789 RGB565"], ("colour", "esp32c3"): ["ESP32-C3 ILI9341 RGB565"],
    ("colour", "esp32s3"): ["ESP32-S3 ILI9341 RGB565"],
    ("colour", "ch582"): ["Pico ST7789 RGB565"], ("grey", "ch582"): ["Pico GRAY8"], ("mono", "ch582"): ["CH582 SVF 예제"],
    ("grey", "pico"): ["Pico GRAY8"], ("grey", "esp32c3"): ["ESP32 GRAY8"], ("grey", "esp32s3"): ["ESP32 GRAY8"],
    ("mono", "pico"): ["Pico SVF 예제"], ("mono", "esp32c3"): ["ESP32 SVF 예제"], ("mono", "esp32s3"): ["ESP32 SVF 예제"],
}
SPEC_SHARED = {
    "colour": ["다람쥐 헌 쳇바퀴에 타고파!", "키스의 고유조건은 입술끼리", "만나야 하고 특별한 기술은", "필요치 않다."],
    "grey": ["다람쥐 헌", "쳇바퀴에", "타고파!", "안녕하세요"],
    "mono": ["다람쥐 헌 쳇바퀴", "에 타고파! 1bpp", "안녕하세요"],
}
SPEC_WIDTHS = {"Pico ST7789 RGB565": 178, "ESP32-C3 ILI9341 RGB565": 227, "ESP32-S3 ILI9341 RGB565": 225,
               "다람쥐 헌 쳇바퀴에 타고파!": 222, "키스의 고유조건은 입술끼리": 228, "만나야 하고 특별한 기술은": 216,
               "필요치 않다.": 101, "Pico GRAY8": 97, "ESP32 GRAY8": 116, "다람쥐 헌": 78, "쳇바퀴에": 72, "타고파!": 60,
               "안녕하세요": 90, "Pico SVF 예제": 104, "ESP32 SVF 예제": 112, "CH582 SVF 예제": 112,
               "다람쥐 헌 쳇바퀴": 128,
               "에 타고파! 1bpp": 120}
SPEC_WIDTHS_MONO = {"안녕하세요": 80}


class TestSpecText(unittest.TestCase):
    def test_every_line_is_the_spec_line_with_its_width(self):
        faces = {"colour": PAPLG, "grey": PAPLG, "mono": MONO}
        adv = {"colour": 6, "grey": 6, "mono": 0}
        for (profile, board), first in SPEC_TEXT.items():
            want = first + SPEC_SHARED[profile]
            self.assertEqual(screens.lines(board, profile), want, (board, profile))
            for text in want:
                width = SPEC_WIDTHS_MONO[text] if profile == "mono" and text in SPEC_WIDTHS_MONO else SPEC_WIDTHS[text]
                self.assertEqual(svfline.measure(faces[profile], text, missing_advance=adv[profile])[0], width,
                                 (board, profile, text))


class TestPanelKind(unittest.TestCase):
    def test_mapping(self):
        self.assertEqual([screens.panel_kind(p) for p in ("colour", "grey", "mono")],
                         ["rgb565", "gray4panel", "mono-page"])
        self.assertEqual([screens.PROFILES[p]["kind"] for p in ("colour", "grey", "mono")],
                         ["rgb565", "gray8", "mono-page"])
        self.assertEqual([screen_ref.geometry("pico", p)[0] for p in ("colour", "grey", "mono")],
                         ["rgb565", "gray4panel", "mono-page"])

    def test_profile_kind_is_refused_with_the_panel_kind(self):
        for call in (lambda: screen_ref.to_png("gray8", 128, 128, bytes(8192)),
                     lambda: screen_ref.compare(bytes(8192), bytes(8192), "gray8", 128)):
            with self.assertRaises(ValueError) as cm:
                call()
            self.assertIn("gray4panel", str(cm.exception))

    def test_to_png_validates_the_size(self):
        for args in (("mono-page", 128, 64, bytes(1023)), ("gray4panel", 128, 128, bytes(8193)),
                     ("rgb565", 240, 240, bytes(10)), ("gray4panel", 127, 128, bytes(8192))):
            with self.assertRaises(ValueError, msg=args):
                screen_ref.to_png(*args)

    def test_cli_compares_grey_through_the_mapping(self):
        with tempfile.TemporaryDirectory() as out:
            ref = screen_ref.build_ref("pico", "grey")
            bad = bytearray(ref)
            bad[70] ^= 1
            with open(os.path.join(out, "pico-grey.fb"), "wb") as f:
                f.write(bad)
            r = run_cli("pico", "grey", out)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn("differs at byte 70 (x 12, y 1)", r.stdout)
            with open(os.path.join(out, "pico-grey.fb"), "wb") as f:
                f.write(ref)
            r = run_cli("pico", "grey", out)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "screen-pico-grey: OK"))

    def test_bigendian_png(self):
        with tempfile.TemporaryDirectory() as out:
            ref = screen_ref.build_ref("pico", "colour")
            k = next(k for k in range(0, len(ref), 2) if ref[k:k + 2] != b"\x00\x10")
            v = int.from_bytes(ref[k:k + 2], "big")
            screen_ref.to_png("rgb565", 240, 240, ref, 1).save(os.path.join(out, "c.png"))
            png_pixel_checks(self, os.path.join(out, "c.png"), (240, 240), "RGB",
                             [((0, 0), (0, 0, 132)), ((k // 2 % 240, k // 2 // 240), rep565(v))])


class TestCheckMore(unittest.TestCase):
    def test_custom_profile_and_mutated_faces(self):
        t = copy.deepcopy(screens.PROFILES)
        t["tiny"] = copy.deepcopy(t["mono"])  # a profile name the module does not know
        self.assertEqual(screens.check(t), [])
        t["tiny"]["faces"] = ["dos/PAPLG16.SVF", "dos/PAPLG18.SVF"]  # wider text: must be measured with these
        msgs = screens.check(t)
        self.assertTrue(msgs and all("/tiny" in m for m in msgs), msgs)

    def test_ascent_rule(self):
        cases = (("colour", "band_baseline", None), ("grey", "baselines", 0), ("mono", "baselines", 0))
        for profile, key, idx in cases:
            t = copy.deepcopy(screens.PROFILES)
            if idx is None:
                t[profile][key] = 10
            else:
                t[profile][key][idx] = 5
            self.assertTrue(any("ascent" in m and "/" + profile in m for m in screens.check(t)), profile)

    def test_text_y_band_inside_panel(self):
        t = copy.deepcopy(screens.PROFILES)
        t["colour"]["text_y"][-1] = 230
        self.assertTrue(any("text_y" in m for m in screens.check(t)))


class TestFbBounds(unittest.TestCase):
    def test_huge_fb_is_read_bounded(self):
        ref = screen_ref.build_ref("pico", "mono")
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "pico-mono.fb"), "wb") as f:
                f.truncate(4 << 30)  # sparse: reading it whole needs 4 GiB, the child may use 2
            r = run_cli("pico", "mono", out, preexec=limit_memory)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn("%d bytes" % (4 << 30), r.stdout)
            self.assertIn("expected %d" % len(ref), r.stdout)

    def test_oversized_diff_png_is_marked(self):
        ref = screen_ref.build_ref("pico", "mono")
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "pico-mono.fb"), "wb") as f:
                f.write(ref + b"\0" * 8)
            self.assertEqual(run_cli("pico", "mono", out).returncode, 1)
            from PIL import Image
            with Image.open(os.path.join(out, "pico-mono-diff.png")) as im:
                self.assertEqual(im.getpixel((0, 0)), (255, 0, 0))
                self.assertEqual(im.getpixel((127, 63)), (255, 0, 0))
                self.assertEqual(im.getpixel((64, 32)), (255,) * 3 if ref[4 * 128 + 64] & 1 else (0,) * 3)


if __name__ == "__main__":
    unittest.main()
