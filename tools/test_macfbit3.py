#!/usr/bin/env python3
"""Tests for tools/macfbit3.py: the JM / -lh5- decoder, the resource fork reader, fbit type 3 planes, HTBL 1
composition, PNG sheets and the BDF export.

Synthetic data only, except TestRealCD712, which runs when MACFBIT3_CD712 names the extracted HangulTalk 7.1.2 CD
tree (the directory holding "Hangul System Install"); it is skipped otherwise.
"""
import contextlib
import io
import os
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macfbit3 as m  # noqa: E402


class BitWriter:
    def __init__(self):
        self.bits = []

    def put(self, v, n):
        self.bits += [(v >> (n - 1 - k)) & 1 for k in range(n)]

    def bytes(self):
        b = self.bits + [0] * (-len(self.bits) % 8)
        return bytes(int("".join(map(str, b[i:i + 8])), 2) for i in range(0, len(b), 8))


def lh5_block(symbols, plen_single=None):
    """One ar002 block: C lengths are all 9 for symbols 0..256 (literals + match length 3), coded through a
    single-valued PT tree; the P tree is single-valued. `symbols` = list of ('lit', byte) or ('match', j)."""
    w = BitWriter()
    w.put(len(symbols), 16)
    w.put(0, 5); w.put(9 + 2, 5)          # T tree: n = 0, every C length decodes as 11 -> 9
    w.put(257, 9)                         # C: 257 lengths given (0..256), rest 0
    w.put(0, 4); w.put(plen_single or 0, 4)   # P tree: n = 0, single value
    for kind, v in symbols:
        if kind == "lit":
            w.put(v, 9)
        else:
            w.put(256, 9)                 # match length 3
            j = plen_single or 0
            if j > 1:
                w.put(v, j - 1)
    return w.bytes()


def jm_archive(payload, unpacked_len):
    hdr_len = 0x1e                       # real archives say 0x35..0x4c; the decoder does not use it
    body = b"\xff" * 8 + payload
    flen = 0x16 + len(body)
    ck = sum(payload) & 0xFFFFFFFF      # byte sum of file[0x1e:]
    return b"JM" + struct.pack(">5I", hdr_len, flen - hdr_len, flen, unpacked_len, ck) + body


def resource_fork(res):
    """Build a resource fork from {(type, id): bytes}."""
    data = b""
    offs = {}
    for k, v in res.items():
        offs[k] = len(data)
        data += struct.pack(">I", len(v)) + v
    types = sorted({t for t, _ in res})
    tl = 28
    reflist_start = 2 + 8 * len(types)
    typelist = struct.pack(">H", len(types) - 1)
    refs = b""
    for t in types:
        ids = [k for k in res if k[0] == t]
        typelist += t.encode("mac_roman") + struct.pack(">HH", len(ids) - 1, reflist_start + len(refs))
        for k in ids:
            refs += struct.pack(">hhB", k[1], -1, 0) + offs[k].to_bytes(3, "big") + b"\0" * 4
    mp = b"\0" * 24 + struct.pack(">HH", tl, tl + len(typelist) + len(refs)) + typelist + refs
    doff = 256
    moff = doff + len(data)
    head = struct.pack(">4I", doff, moff, len(data), len(mp))
    return head + b"\0" * (doff - 16) + data + mp


def make_fbit(h, glyphs):
    """fbit type 3 with one range; glyphs = list of row lists."""
    hdr = bytearray(0x54)
    hdr[0:6] = b"\x80\x00fbit"
    hdr[0x0C:0x0E] = struct.pack(">H", 3)
    hdr[0x16:0x18] = struct.pack(">H", h)
    hdr[0x48:0x4A] = struct.pack(">H", 3)
    hdr[0x4C:0x4E] = struct.pack(">H", 1)
    gb = (h * h + 7) // 8
    out = bytes(hdr)
    for rows in glyphs:
        v = 0
        for r in rows:
            v = (v << h) | r
        v <<= gb * 8 - h * h
        out += v.to_bytes(gb, "big")
    return out


def make_htbl(jamo, syl):
    t1 = b"".join(jamo)
    t2 = b"".join(syl) + b"\0\0\0\0" * (m.KS_SYLLABLES - len(syl))
    return struct.pack(">I", len(t1)) + t1 + struct.pack(">I", 0x2468) + t2 + t1


class TestLh5(unittest.TestCase):
    def test_distance_before_start(self):
        # P single 3 -> j = (1 << 2) + get(2) = 4 -> source len - 5 < 0 after three literals
        payload = lh5_block([("lit", 0x41), ("lit", 0x42), ("lit", 0x43), ("match", 0)], plen_single=3)
        with self.assertRaisesRegex(ValueError, "before start"):
            m.lh5_unpack(payload, 0, 6)

    def test_match_distance_zero(self):
        # P single 0 -> distance j = 0 -> copy from out[-1] (run of the last byte)
        payload = lh5_block([("lit", 0x41), ("lit", 0x42), ("match", 0), ("lit", 0x43)], plen_single=0)
        self.assertEqual(m.lh5_unpack(payload, 0, 6), b"ABBBBC")

    def test_match_distance_two(self):
        # P single 2 -> j = (1 << 1) + get(1); get(1) = 0 -> 2 -> copy from len - 3
        payload = lh5_block([("lit", 0x31), ("lit", 0x32), ("lit", 0x33), ("match", 0)], plen_single=2)
        self.assertEqual(m.lh5_unpack(payload, 0, 6), b"123123")

    def test_zero_block_refused(self):
        self.assertRaises(ValueError, m.lh5_unpack, b"\0\0\0\0", 0, 1)


class TestJM(unittest.TestCase):
    def setUp(self):
        self.payload = lh5_block([("lit", c) for c in b"hello"])

    def test_unpack(self):
        a = jm_archive(self.payload, 5)
        self.assertEqual(m.jm_unpack(a), b"hello")
        self.assertEqual(m.jm_header(a)["unpacked_len"], 5)

    def test_checksum_mismatch(self):
        a = bytearray(jm_archive(self.payload, 5))
        a[-1] ^= 0xFF
        with self.assertRaisesRegex(ValueError, "checksum"):
            m.jm_unpack(bytes(a))

    def test_length_mismatch(self):
        with self.assertRaisesRegex(ValueError, "length"):
            m.jm_unpack(jm_archive(self.payload, 5) + b"\0")

    def test_not_jm(self):
        self.assertRaises(ValueError, m.jm_unpack, b"XX" + b"\0" * 40)


H = 4
# planes: 0 = left column, 1 = top row, 2 = bottom row, 3 = right column (bank 1 bytes 0x0f..0x12)
PLANES = [[8, 8, 8, 8], [15, 0, 0, 0], [0, 0, 0, 15], [1, 1, 1, 1]]


class TestFbit3(unittest.TestCase):
    def setUp(self):
        self.fbit = make_fbit(H, PLANES)
        jamo = [bytes([1, 0x0F, 0x0E, 0])]                                        # A4A1 = plane 0
        syl = [bytes([1, 0x0F, 0x10, 0]), bytes([1, 0x10, 0x11, 0x12])]           # B0A1, B0A2
        self.htbl = make_htbl(jamo, syl)
        self.f = m.Fbit3(self.fbit, self.htbl)

    def test_layout(self):
        self.assertEqual((self.f.h, self.f.gb, self.f.base, self.f.n), (4, 2, 0x54, 4))
        self.assertEqual(self.f.glyph(1), [15, 0, 0, 0])
        self.assertRaises(IndexError, self.f.glyph, 4)

    def test_compose(self):
        self.assertEqual(self.f.parts(0xB0, 0xA1), [0, 1])
        self.assertEqual(self.f.compose(0xB0, 0xA1), [15, 8, 8, 8])
        self.assertEqual(self.f.compose(0xB0, 0xA2), [15, 1, 1, 15])
        self.assertEqual(self.f.compose(0xA4, 0xA1), [8, 8, 8, 8])     # 0x0e = no plane
        self.assertIsNone(self.f.compose(0xA1, 0xA1))
        self.assertIsNone(self.f.compose(0xA4, 0xA2))                 # only one jamo entry here

    def test_bank_two(self):
        f = m.Fbit3(make_fbit(H, PLANES * 61), make_htbl([], [bytes([2, 0x0F, 0, 0])]))
        self.assertEqual(f.parts(0xB0, 0xA1), [241])

    def test_codes(self):
        codes = self.f.codes()
        self.assertEqual(len(codes), 1 + m.KS_SYLLABLES)
        self.assertEqual(codes[1], (0xB0, 0xA1))
        self.assertEqual(codes[-1], (0xC8, 0xFE))

    def test_not_type3(self):
        bad = bytearray(self.fbit)
        bad[0x0D] = 2
        self.assertRaises(ValueError, m.Fbit3, bytes(bad))

    def test_load_paths(self):
        fork = resource_fork({("fbit", 17408): self.fbit, ("vers", 1): b"x"})
        self.assertEqual(m.load_fbit(self.fbit), self.fbit)
        self.assertEqual(m.load_fbit(fork), self.fbit)
        ib = resource_fork({("HTBL", 1): self.htbl, ("HTBL", 2): b"other"})
        self.assertEqual(m.load_htbl1(ib), self.htbl)
        self.assertEqual(m.load_htbl1(self.htbl), self.htbl)

    def test_compressed_resource_refused(self):
        fork = bytearray(resource_fork({("HTBL", 1): b"\0\0\0\x12\xa8\x9f\x65\x72" + b"\0" * 8}))
        # set attribute bit 0 (compressed) on the only reference
        moff = struct.unpack(">I", fork[4:8])[0]
        fork[moff + 28 + 2 + 8 + 4] |= 1
        with self.assertRaisesRegex(ValueError, "compressed"):
            m.resources(bytes(fork))


class TestOutput(unittest.TestCase):
    def setUp(self):
        self.f = m.Fbit3(make_fbit(H, PLANES), make_htbl([bytes([1, 0x0F, 0, 0])], [bytes([1, 0x0F, 0x10, 0])]))
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def read_png(self, path):
        with open(path, "rb") as fh:
            d = fh.read()
        self.assertEqual(d[:8], b"\x89PNG\r\n\x1a\n")
        w, h = struct.unpack(">II", d[16:24])
        idat = d[d.index(b"IDAT") + 4:d.index(b"IEND") - 8]
        raw = zlib.decompress(idat)
        rows = [raw[y * (w + 1) + 1:(y + 1) * (w + 1)] for y in range(h)]
        return w, h, rows

    def test_sheets(self):
        paths = m.write_sheets(self.f, os.path.join(self.tmp.name, "t"))
        self.assertEqual([os.path.basename(p) for p in paths],
                         ["t_glyphs_x1.png", "t_ks2350_x1.png", "t_glyphs_x4.png", "t_ks2350_x4.png"])
        w, h, rows = self.read_png(paths[0])
        self.assertEqual((w, h), (32 * 5 + 1, 6))
        self.assertEqual(rows[1][1], 0)          # glyph 0, pixel (0, 0) set
        self.assertEqual(rows[1][2], 255)        # (1, 0) clear
        self.assertEqual(rows[0][0], 192)        # grid
        w, h, rows = self.read_png(paths[3])
        self.assertEqual((w, h), (47 * 17 + 1, 50 * 17 + 1))
        self.assertEqual(rows[1][1:17], b"\x00" * 16)    # B0A1 top row (plane 1) at 4x

    def test_bdf(self):
        p = os.path.join(self.tmp.name, "t.bdf")
        self.assertEqual(m.write_bdf(self.f, "T", p), 1 + m.KS_SYLLABLES)
        with open(p, encoding="ascii") as fh:
            txt = fh.read()
        self.assertIn("CHARS 2351\n", txt)
        self.assertIn("STARTPROPERTIES 5\n", txt)
        self.assertIn('CHARSET_REGISTRY "ISO10646"\n', txt)
        ga = txt.index("ENCODING %d\n" % ord("가"))
        self.assertIn("BITMAP\nF0\n80\n80\n80\nENDCHAR", txt[ga:ga + 200])
        self.assertEqual(txt.count("STARTCHAR"), txt.count("ENDCHAR"))

    def test_cli(self):
        d = self.tmp.name
        fb = os.path.join(d, "f.fbit")
        ht = os.path.join(d, "h.bin")
        with open(fb, "wb") as fh:
            fh.write(self.f.fb)
        with open(ht, "wb") as fh:
            fh.write(make_htbl([bytes([1, 0x0F, 0, 0])], [bytes([1, 0x0F, 0x10, 0])]))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(m.main(["bdf", fb, ht, "T", os.path.join(d, "o.bdf")]), 0)
            self.assertEqual(m.main(["sheets", fb, ht, os.path.join(d, "s")]), 0)
            self.assertEqual(m.main(["info", fb, ht]), 0)
        self.assertIn("2351 glyphs", out.getvalue())
        self.assertIn("fbit type 3, cell 4 px", out.getvalue())
        self.assertTrue(os.path.exists(os.path.join(d, "s_ks2350_x4.png")))


CD = os.environ.get("MACFBIT3_CD712", "")


@unittest.skipUnless(CD, "MACFBIT3_CD712 not set (extracted HangulTalk 7.1.2 CD tree)")
class TestRealCD712(unittest.TestCase):
    """The claims of johab-fonts notes/mac.md, re-checked on the CD files."""
    FONT = "Hangul System Install/More Additions/Font"
    IB = "Hangul System Install/More Additions/Extensions/InputBackSupport[INIT].rsrc"
    SEOUL = "Hangul System Install/Disk Tools/\ud55c\uae00 \uc2dc\uc2a4\ud15c/\uc790\ud615 \ud3f4\ub354/Seoul12[fbit].rsrc"

    def font(self, name):
        with open(os.path.join(CD, self.FONT, name + "[splt].data"), "rb") as fh:
            return m.load_fbit(fh.read())

    def htbl(self):
        with open(os.path.join(CD, self.IB), "rb") as fh:
            return m.load_htbl1(fh.read())

    def test_seoul12_splt_equals_uncompressed(self):
        with open(os.path.join(CD, self.SEOUL), "rb") as fh:
            self.assertEqual(self.font("Seoul12"), m.load_fbit(fh.read()))

    def test_three_12px_fonts(self):
        ht = self.htbl()
        self.assertEqual(ht[-204:], ht[4:208])                  # trailing copy of the jamo entries
        for name in ("Seoul12", "AppleGothic12", "AppleMyungjo12"):
            f = m.Fbit3(self.font(name), ht)
            self.assertEqual((f.h, f.n, len(f.codes())), (12, 482, 2401), name)
            for hi, lo in f.codes():
                parts = f.parts(hi, lo)
                self.assertTrue(parts and all(0 <= g < f.n for g in parts), (name, hex(hi), hex(lo)))


if __name__ == "__main__":
    unittest.main()
