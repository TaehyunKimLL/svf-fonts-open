#!/usr/bin/env python3
"""srcprep.py tests: the reading helpers and the PCF reader, on fixtures built in inputfx.py.

  python3 -m unittest discover -s maker/test -p 'test_srcprep.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gzip
import io
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

import bdfface
import fixtures
import inputfx
import macfx
import srcprep
from PIL import Image, ImageFont
from fontTools.ttLib import TTFont


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = self._tmp.name

    def write(self, name, data):
        p = os.path.join(self.dir, name)
        with open(p, "wb") as fh:
            fh.write(data)
        return p


class SrcprepTest(TmpCase):
    def test_ttc_face_bytes_saves_face_1(self):
        data = inputfx.ttc([inputfx.ttf("One", (50, 0, 950, 800)), inputfx.ttf("Two", (300, 0, 700, 400))])
        face = TTFont(io.BytesIO(srcprep.ttc_face_bytes(data, 1)))
        self.assertEqual(face["name"].getDebugName(1), "Two")
        with self.assertRaises(srcprep.PrepError):
            srcprep.ttc_face_bytes(data, 2)

    def test_variable_info(self):
        info = srcprep.variable_info(TTFont(io.BytesIO(inputfx.variable_ttf())))
        self.assertEqual(info["axes"], [{"tag": "wght", "min": 100, "default": 400, "max": 900}])
        self.assertEqual(info["instances"], [{"name": "Regular", "coords": {"wght": 400}},
                                             {"name": "Bold", "coords": {"wght": 700}}])
        self.assertIsNone(srcprep.variable_info(TTFont(io.BytesIO(inputfx.ttf("S", (0, 0, 9, 9))))))

    def test_embedded_strikes_and_outlines(self):
        self.assertEqual(srcprep.embedded_strikes(TTFont(io.BytesIO(inputfx.eblc_ttf((16, 12, 16))))), [12, 16])
        self.assertEqual(srcprep.embedded_strikes(TTFont(io.BytesIO(inputfx.ttf("S", (0, 0, 9, 9))))), [])
        self.assertFalse(srcprep.has_outlines(TTFont(io.BytesIO(inputfx.bitmap_only_ttf()))))
        self.assertTrue(srcprep.has_outlines(TTFont(io.BytesIO(inputfx.otf("C", (0, 0, 9, 9))))))

    def test_mac_cmap_only(self):
        self.assertTrue(srcprep.mac_cmap_only(TTFont(io.BytesIO(inputfx.mac_cmap_ttf()))))
        self.assertFalse(srcprep.mac_cmap_only(TTFont(io.BytesIO(inputfx.both_cmaps_ttf()))))
        self.assertFalse(srcprep.mac_cmap_only(TTFont(io.BytesIO(inputfx.ttf("S", (0, 0, 9, 9))))))

    def test_mac_resources_names_the_container(self):
        fk = inputfx.fork([(b"sfnt", 128, "Synth", inputfx.mac_cmap_ttf()), (b"NFNT", 200, "", bytes(26))])
        for blob, name in ((fk, "resource fork"), (inputfx.appledouble(fk), "AppleDouble"),
                           (inputfx.macbinary(fk), "MacBinary")):
            container, res = srcprep.mac_resources(blob)
            self.assertEqual((container, [(t, i) for t, i, _, _ in res]), (name, [(b"sfnt", 128), (b"NFNT", 200)]))
        with self.assertRaises(srcprep.PrepError):
            srcprep.mac_resources(fk[:40])

    def test_prepared_bytes_chains_ops(self):
        fk = inputfx.fork([(b"sfnt", 129, "", inputfx.mac_cmap_ttf())])
        out = TTFont(io.BytesIO(srcprep.prepared_bytes(inputfx.appledouble(fk),
                                                        [{"op": "rsrc-sfnt", "id": 129}, {"op": "mac-cmap"}])))
        self.assertEqual(out.getBestCmap()[0xAC00], "ga")
        with self.assertRaises(srcprep.PrepError):
            srcprep.prepared_bytes(b"", [{"op": "instance", "coords": {}}])

    def test_prepared_bytes_instance_op(self):
        out = TTFont(io.BytesIO(srcprep.prepared_bytes(inputfx.variable_ttf(),
                                                       [{"op": "instance", "coords": {"wght": 700}}])))
        self.assertNotIn("fvar", out)
        wide = TTFont(io.BytesIO(srcprep.prepared_bytes(inputfx.variable_ttf(),
                                                        [{"op": "instance", "coords": {"wght": 900}}])))
        # the gvar delta moves ga's right edge at the axis maximum
        right = lambda f: max(x for x, _ in f["glyf"]["ga"].getCoordinates(f["glyf"])[0])
        self.assertLess(right(wide), right(out))

    def test_cli_ttc_face(self):
        src = self.write("two.ttc", inputfx.ttc([inputfx.ttf("One", (50, 0, 950, 800)),
                                                 inputfx.ttf("Two", (300, 0, 700, 400))]))
        out = os.path.join(self.dir, "face.ttf")
        tool = os.path.join(MAKER_DIR, "srcprep.py")
        r = subprocess.run([sys.executable, "-P", tool, "ttc-face", src, out, "--index", "1"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(TTFont(out)["name"].getDebugName(1), "Two")
        r = subprocess.run([sys.executable, "-P", tool, "ttc-face", src, out, "--index", "5"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("face", r.stderr)

    def test_a_damaged_cmap_body_is_a_prep_error_not_an_index_error(self):
        with self.assertRaises(srcprep.PrepError):
            srcprep.prepared_bytes(inputfx.damaged_mac_cmap_ttf(), [{"op": "mac-cmap"}])

    def test_a_large_ttc_header_opens_only_the_face_asked_for(self):
        import struct
        import time
        n = 100000
        face = bytearray(inputfx.ttf("One", BOX))
        hdr = 12 + 4 * n
        for i in range(struct.unpack_from(">H", face, 4)[0]):
            struct.pack_into(">I", face, 12 + 16 * i + 8, struct.unpack_from(">I", face, 12 + 16 * i + 8)[0] + hdr)
        ttc = b"ttcf" + struct.pack(">II", 0x00010000, n) + struct.pack(">%dI" % n, *([hdr] * n)) + bytes(face)
        t = time.time()
        out = srcprep.ttc_face_bytes(ttc, 1)
        self.assertLess(time.time() - t, 2.0)
        self.assertEqual(TTFont(io.BytesIO(out))["name"].getDebugName(1), "One")
        with self.assertRaises(srcprep.PrepError):
            srcprep.ttc_face_bytes(ttc, n)

    def test_a_resource_fork_with_many_references_to_one_body_is_refused(self):
        import struct
        n, body = 300, 1 << 20
        data = struct.pack(">I", body) + bytes(body)
        type_list = struct.pack(">H", 0) + struct.pack(">4sHH", b"NFNT", n - 1, 2 + 8)
        refs = b"".join(struct.pack(">hHI", i, 0xFFFF, 0) + bytes(4) for i in range(n))
        mp = bytes(24) + struct.pack(">HH", 28, 28 + len(type_list) + len(refs)) + type_list + refs
        fork = struct.pack(">IIII", 256, 256 + len(data), len(data), len(mp)) + bytes(240) + data + mp
        with self.assertRaises(srcprep.PrepError):
            srcprep.mac_resources(fork)
        many = struct.pack(">H", 0) + struct.pack(">4sHH", b"NFNT", 5000, 10) + refs[:12] * 5001
        mp = bytes(24) + struct.pack(">HH", 28, 28 + len(many)) + many
        fork = struct.pack(">IIII", 256, 256 + 4, 4, len(mp)) + bytes(240) + bytes(4) + mp
        with self.assertRaises(srcprep.PrepError):
            srcprep.mac_resources(fork)

    def test_a_fork_with_an_out_of_range_resource_is_named_by_the_reader(self):
        import struct
        fk = bytearray(inputfx.fork([(b"sfnt", 128, "", inputfx.ttf("P", BOX))]))
        data_off = struct.unpack_from(">I", fk, 0)[0]
        struct.pack_into(">I", fk, data_off, 0xFFFFFFF0)            # the body's length field: far past the fork
        with self.assertRaises(srcprep.PrepError) as ctx:
            srcprep.mac_resources(bytes(fk))
        self.assertIn("runs past the fork", str(ctx.exception))      # macsfnt's message, not "resources too large"
        for cut in (60, 200, len(fk) - 10):
            with self.assertRaises(srcprep.PrepError):
                srcprep.mac_resources(bytes(fk[:cut]))

    def test_embedded_strikes_ignore_a_zero_ppem(self):
        self.assertEqual(srcprep.embedded_strikes(TTFont(io.BytesIO(inputfx.eblc_ttf((0, 12))))), [12])

    def test_fixtures_are_deterministic(self):
        for build in (lambda: inputfx.ttc([inputfx.ttf("One", BOX), inputfx.ttf("Two", BOX)]), inputfx.both_cmaps_ttf,
                      inputfx.eblc_ttf, inputfx.bitmap_only_ttf, inputfx.mac_cmap_ttf, inputfx.variable_ttf):
            self.assertEqual(build(), build())
        self.assertEqual(TTFont(io.BytesIO(inputfx.eblc_ttf()))["head"].modified, fixtures.HEAD_TIME)


BOX = (50, 0, 950, 800)
GLYPHS = [(0x3021, [0x8001 | (y << 3) for y in range(16)], 16),
          (0x3022, [0xFFFF if y == 8 else 0 for y in range(16)], 16)]


class MacPrepTest(TmpCase):
    def cli(self, sub, data, *flags):
        """`(exit code, OUT bytes or b"")` of `python3 -P srcprep.py <sub> IN OUT [flags]` over @p data."""
        src = self.write("in.bin", data)
        out = os.path.join(self.dir, "out.bin")
        if os.path.exists(out):
            os.remove(out)
        r = subprocess.run([sys.executable, "-P", os.path.join(MAKER_DIR, "srcprep.py"), sub, src, out] + list(flags),
                           capture_output=True, text=True)
        content = b""
        if os.path.exists(out):
            with open(out, "rb") as fh:
                content = fh.read()
        return r.returncode, content

    def test_mac_fork_unwraps(self):
        f = macfx.fbit3_fork()
        for wrapped in (macfx.appledouble(f), macfx.macbinary(f)):
            self.assertEqual(self.cli("mac-fork", wrapped), (0, f))
        self.assertEqual(self.cli("mac-fork", f), (0, f))
        self.assertEqual(self.cli("mac-fork", b"not a fork at all")[0], 2)

    def test_mac_fork_refuses_oversized(self):
        f = macfx.fbit3_fork()
        with mock.patch.object(srcprep, "MAX_BYTES", 100):
            with self.assertRaises(srcprep.PrepError):
                srcprep._apply_op(f, {"op": "mac-fork"})

    def test_mac_fbit3_caps_a_jm_archive_before_unpacking(self):
        big = bytearray(macfx.jm(macfx.fbit3_fork()))
        struct.pack_into(">I", big, 14, srcprep.JM_CAP + 1)               # unpacked_len, the 4th header word
        with self.assertRaisesRegex(srcprep.PrepError, "too large"):
            srcprep.prepared_bytes(bytes(big), [{"op": "mac-fbit3"}])

    def test_bdf_pixel_size(self):
        bdf = (b"STARTFONT 2.1\nFONT x\nSIZE 12 75 75\nFONTBOUNDINGBOX 12 12 0 -2\nSTARTPROPERTIES 2\n"
               b"FONT_ASCENT 10\nFONT_DESCENT 2\nENDPROPERTIES\nCHARS 0\nENDFONT\n")
        code, out = self.cli("bdf-pixel-size", bdf, "--size", "12")
        self.assertEqual(code, 0)
        self.assertIn(b"STARTPROPERTIES 3\nPIXEL_SIZE 12\nFONT_ASCENT 10", out)
        again = self.cli("bdf-pixel-size", out, "--size", "14")[1]                # replaced, not doubled
        self.assertEqual(again.count(b"PIXEL_SIZE"), 1)
        self.assertIn(b"STARTPROPERTIES 3\nPIXEL_SIZE 14", again)
        self.assertEqual(self.cli("bdf-pixel-size", b"not a bdf", "--size", "12")[0], 2)

    def test_mac_htbl(self):
        self.assertEqual(self.cli("mac-htbl", macfx.htbl_fork()), (0, macfx.htbl_raw()))
        self.assertEqual(self.cli("mac-htbl", macfx.htbl_raw()), (0, macfx.htbl_raw()))
        self.assertEqual(self.cli("mac-htbl", macfx.htbl_raw_padded()), (0, macfx.htbl_raw_padded()))
        bad = struct.pack(">I", 200) + macfx.htbl_raw()[4:]
        self.assertEqual(self.cli("mac-htbl", bad)[0], 2)
        self.assertEqual(self.cli("mac-htbl", macfx.htbl_raw()[:300])[0], 2)

    def test_apply_op_mac(self):
        self.assertEqual(srcprep.prepared_bytes(macfx.jm(macfx.fbit3_fork()), [{"op": "mac-fbit3"}]), macfx.fbit3_raw())
        self.assertEqual(srcprep.prepared_bytes(macfx.appledouble(macfx.fbit3_fork()),
                                                [{"op": "mac-fork"}, {"op": "mac-fbit3"}]), macfx.fbit3_raw())
        self.assertEqual(srcprep.prepared_bytes(macfx.htbl_fork(), [{"op": "mac-htbl"}]), macfx.htbl_raw())
        with self.assertRaisesRegex(srcprep.PrepError, "named forks are read by the CLI only"):
            srcprep.prepared_bytes(b"x", [{"op": "mac-fork-named"}])


class PcfTest(TmpCase):
    def test_properties_and_gzip(self):
        data = inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2)
        for blob in (data, gzip.compress(data)):
            p = srcprep.pcf_properties(blob)
            self.assertEqual((p["CHARSET_REGISTRY"], p["CHARSET_ENCODING"], p["PIXEL_SIZE"]),
                             ("KSC5601.1987", "0", 16))

    def test_pcf_to_bdf_round_trips_through_bdfface(self):
        bdf = srcprep.pcf_to_bdf(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2))
        path = self.write("k.bdf", bdf)
        glyphs = bdfface.read_bdf(path)[1]
        self.assertEqual(sorted(glyphs), [0xAC00, 0xAC01])        # bdfface reads KSC GL codes 0x3021/0x3022 as U+AC00/AC01
        self.assertEqual(glyphs[0xAC01][4][8], 0xFFFF)            # bdfface's row ints, row 8
        self.assertEqual(glyphs[0xAC00][4], GLYPHS[0][1])
        raw = bdfface.read_bdf(path, unicode_enc=True)[1]
        self.assertEqual(sorted(raw), [0x3021, 0x3022])
        self.assertIn(b"FONTBOUNDINGBOX 16 16 0 -2", bdf)

    def test_lsbit_and_lsbyte_tables_read_the_same(self):
        want = srcprep.pcf_to_bdf(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2))
        for fmt in (0x00000010 | 0x1,            # LSByte, LSBit, pad 2, scan unit 2
                    0x00000004 | 0x10 | 0x1,     # MSByte, LSBit, pad 2, scan unit 2: the bytes swap inside a unit
                    0x00000008 | 0x2 | 0x20):    # LSByte, MSBit, pad 4, scan unit 4
            with self.subTest(fmt=fmt):
                got = srcprep.pcf_to_bdf(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2, fmt=fmt))
                self.assertEqual(got, want)

    def test_pillow_reads_every_bitmap_format_like_the_reader(self):
        rows = [0x8001 | (y << 3) for y in range(16)]
        want = [[(r >> (15 - x)) & 1 for x in range(16)] for r in rows]
        for fmt in (0x0C, 0x11, 0x04 | 0x10 | 0x1, 0x08 | 0x2 | 0x20):
            with self.subTest(fmt=fmt):
                data = inputfx.pcf([(0x41, rows, 16)], "ISO10646", "1", 16, 14, 2, fmt=fmt)
                font = ImageFont.truetype(self.write("f%d.pcf" % fmt, data), 16)
                core = font.getmask("A", mode="1")
                img = Image.frombytes(core.mode, core.size, bytes(core)).convert("L")
                self.assertEqual(img.size, (16, 16))
                self.assertEqual([[1 if img.getpixel((x, y)) else 0 for x in range(16)] for y in range(16)], want)
                bdf = srcprep.pcf_to_bdf(data)
                self.assertIn(b"\n8001\n", bdf)

    def test_amplified_bitmaps_are_refused_quickly(self):
        import struct
        import time
        n, w8, rows = 2000, 8192, 128
        e = ">"
        base = inputfx.pcf([(0x3021, [0] * 16, 16)], "KSC5601.1987", "0", 16, 14, 2)
        tabs = {}
        for i in range(struct.unpack_from("<I", base, 4)[0]):
            t, _f, size, off = struct.unpack_from("<IIII", base, 8 + 16 * i)
            tabs[t] = base[off:off + size]
        met = struct.pack("<I", 0xC) + struct.pack(e + "I", n) + struct.pack(e + "6h", 0, w8, w8, rows, 0, 0) * n
        blk = w8 // 8 * rows
        bm = (struct.pack("<I", 0xC) + struct.pack(e + "I", n) + struct.pack(e + "%dI" % n, *([0] * n)) +
              struct.pack(e + "4I", *([blk] * 4)) + bytes(blk))
        cols = 94
        idx = [i if i < n else 0xFFFF for i in range(cols * ((n + cols - 1) // cols))]
        enc = (struct.pack("<I", 0xC) + struct.pack(e + "5h", 0x21, 0x21 + cols - 1, 0x30, 0x30 + len(idx) // cols - 1, 0) +
               struct.pack(e + "%dH" % len(idx), *idx))
        tables = [(1, tabs[1]), (4, met), (8, bm), (0x20, enc)]
        off, toc, body = 8 + 16 * len(tables), b"", b""
        for t, b in tables:
            b += bytes((-len(b)) % 4)
            toc += struct.pack("<IIII", t, 0xC, len(b), off + len(body))
            body += b
        pcf = b"\x01fcp" + struct.pack("<I", len(tables)) + toc + body
        t0 = time.time()
        with self.assertRaises(srcprep.PrepError):
            srcprep.pcf_to_bdf(pcf)
        self.assertLess(time.time() - t0, 5.0)

    def test_many_small_glyphs_are_refused_before_their_rows_are_built(self):
        import resource
        import time
        glyphs = [(0x3021 + 0x100 * (i // 94) + i % 94, [1] * 16, 16) for i in range(900)]
        self.assertTrue(srcprep.pcf_to_bdf(inputfx.pcf(glyphs, "KSC5601.1987", "0", 16, 14, 2)))   # sane sizes convert
        saved = srcprep.MAX_ROWS
        srcprep.MAX_ROWS = 5000
        self.addCleanup(setattr, srcprep, "MAX_ROWS", saved)
        t0 = time.time()
        with self.assertRaises(srcprep.PrepError):
            srcprep.pcf_to_bdf(inputfx.pcf(glyphs, "KSC5601.1987", "0", 16, 14, 2))
        self.assertLess(time.time() - t0, 2.0)

    def test_pcf_box_reads_the_metrics_only(self):
        self.assertEqual(srcprep.pcf_box(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2)), [16, 16])

    def test_a_negative_property_offset_and_negative_encodings_are_refused(self):
        import struct
        data = bytearray(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2))
        toc = {struct.unpack_from("<I", data, 8 + 16 * i)[0]: struct.unpack_from("<IIII", data, 8 + 16 * i)
               for i in range(5)}
        off = toc[1][3]
        bad = bytearray(data)
        struct.pack_into(">i", bad, off + 8 + 5, -4)            # property 0's name offset (FONT) as a string value < 0
        struct.pack_into(">I", bad, off + 8, 0xFFFFFFF0)
        with self.assertRaises(srcprep.PrepError):
            srcprep.pcf_properties(bytes(bad))
        bad = bytearray(data)
        struct.pack_into(">h", bad, toc[0x20][3] + 4, -1)        # min_byte2 < 0
        with self.assertRaises(srcprep.PrepError):
            srcprep.pcf_to_bdf(bytes(bad))

    def test_a_corrupt_gzip_is_a_prep_error(self):
        blob = gzip.compress(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2))
        for bad in (blob[:-20], blob[:12] + bytes(8) + blob[20:]):
            with self.assertRaises(srcprep.PrepError):
                srcprep.pcf_to_bdf(bad)

    def test_property_strings_cannot_break_the_bdf(self):
        data = inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2, family='A"B\nENDFONT')
        bdf = srcprep.pcf_to_bdf(data).decode("latin-1")
        self.assertEqual(bdf.splitlines().count("ENDFONT"), 1)
        self.assertIn('FAMILY_NAME "A""B ENDFONT"', bdf)

    def test_pillow_opens_the_fixture_pcf(self):
        data = inputfx.pcf([(0x41, [0x8001] * 16, 16)], "ISO10646", "1", 16, 14, 2)
        font = ImageFont.truetype(self.write("a.pcf", data), 16)
        self.assertIsNotNone(font.getmask("A").getbbox())

    def test_truncated_pcf_is_a_prep_error(self):
        with self.assertRaises(srcprep.PrepError):
            srcprep.pcf_to_bdf(inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2)[:200])
        with self.assertRaises(srcprep.PrepError):
            srcprep.pcf_to_bdf(b"not a pcf at all")

    def test_the_pcf_bdf_op_and_cli(self):
        data = inputfx.pcf(GLYPHS, "KSC5601.1987", "0", 16, 14, 2)
        self.assertEqual(srcprep.prepared_bytes(data, [{"op": "pcf-bdf"}]), srcprep.pcf_to_bdf(data))
        out = os.path.join(self.dir, "o.bdf")
        r = subprocess.run([sys.executable, "-P", os.path.join(MAKER_DIR, "srcprep.py"), "pcf-bdf",
                            self.write("k.pcf.gz", gzip.compress(data)), out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, "rb") as fh:
            self.assertEqual(fh.read(), srcprep.pcf_to_bdf(data))

    @unittest.skipUnless(os.path.isfile(fixtures.PCF_SRC), "no 18x18ko.pcf.gz on this host")
    def test_the_host_pcf_converts(self):
        with open(fixtures.PCF_SRC, "rb") as fh:
            raw = fh.read()
        glyphs = bdfface.read_bdf(self.write("h.bdf", srcprep.pcf_to_bdf(raw)), unicode_enc=True)[1]
        self.assertGreater(len([cp for cp in glyphs if 0xAC00 <= cp <= 0xD7A3]), 2000)


if __name__ == "__main__":
    unittest.main()
