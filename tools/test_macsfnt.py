#!/usr/bin/env python3
"""macsfnt.py tests on a synthetic Mac-style TrueType font built here with fontTools (two glyphs, a Mac Korean cmap only)
and a resource fork written here: extraction from a raw fork, AppleDouble and MacBinary, the cmap report, the added
Unicode subtable, and mkfont.py drawing the syllable through it.
  python3 -m unittest tools.test_macsfnt
"""
import io
import os
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import macsfnt  # noqa: E402


def mac_korean_font():
    """TrueType bytes: glyphs .notdef, A (a bar), ga (a box), cmap only (1,3) format 2 (A = 0x41, 가 = 0xB0A1)."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

    def box(x0, y0, x1, y1):
        pen = TTGlyphPen(None)
        pen.moveTo((x0, y0)); pen.lineTo((x0, y1)); pen.lineTo((x1, y1)); pen.lineTo((x1, y0)); pen.closePath()
        return pen.glyph()

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A", "ga"])
    fb.setupCharacterMap({0x41: "A", 0xAC00: "ga"})
    fb.setupGlyf({".notdef": box(0, 0, 10, 10), "A": box(100, 0, 400, 700), "ga": box(50, -100, 950, 800)})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 100), "ga": (1000, 50)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Synth Mac Korean", "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    st = CmapSubtable.newSubtable(2)
    st.platformID, st.platEncID, st.language = 1, 3, 0
    st.cmap = {0x41: "A", 0xB0A1: "ga", 0xA1A1: "A"}   # 0xA1A1 is the ideographic space of KS X 1001
    fb.font["cmap"].tables = [st]
    buf = io.BytesIO()
    fb.font.save(buf)
    return buf.getvalue()


def resource_fork(entries):
    """A resource fork holding @p entries [(type, id, name, bytes)] (the Resource Manager layout)."""
    data = bytearray()
    offsets = []
    for _, _, _, body in entries:
        offsets.append(len(data))
        data += struct.pack(">I", len(body)) + body
    types = {}
    for i, (t, rid, name, _) in enumerate(entries):
        types.setdefault(t, []).append((rid, name, offsets[i]))
    names = bytearray()
    type_list = bytearray(struct.pack(">H", len(types) - 1))
    refs = bytearray()
    ref_base = 2 + 8 * len(types)
    for t, items in types.items():
        type_list += struct.pack(">4sHH", t, len(items) - 1, ref_base + len(refs))
        for rid, name, off in items:
            noff = 0xFFFF
            if name:
                noff = len(names)
                names += bytes([len(name)]) + name.encode("mac_roman")
            refs += struct.pack(">hHII", rid, noff, off & 0xFFFFFF, 0)
    tl = type_list + refs
    map_body = bytearray(16 + 4 + 2 + 2) + struct.pack(">HH", 28, 28 + len(tl)) + tl + names   # header copy, handle, ref, attrs
    data_off = 256
    map_off = data_off + len(data)
    head = struct.pack(">IIII", data_off, map_off, len(data), len(map_body))
    return head + bytes(data_off - 16) + bytes(data) + bytes(map_body)


class MacSfnt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ttf = mac_korean_font()
        cls.fork = resource_fork([(b"FOND", 128, "Synth", b"\0" * 52), (b"sfnt", 128, "Synth", cls.ttf),
                                  (b"sfnt", 129, "", cls.ttf[:]), (b"NFNT", 200, "", b"\0" * 26)])

    def test_resources_and_wrappers(self):
        dbl = bytearray(struct.pack(">II", 0x00051607, 0x00020000) + bytes(16) + struct.pack(">H", 1))
        dbl += struct.pack(">III", 2, len(dbl) + 12, len(self.fork)) + self.fork
        mb = bytearray(128)
        mb[1] = 5; mb[2:7] = b"Synth"
        struct.pack_into(">II", mb, 83, 0, len(self.fork))
        mb += self.fork
        for name, blob in (("raw", self.fork), ("appledouble", bytes(dbl)), ("macbinary", bytes(mb))):
            with self.subTest(wrapper=name):
                res = macsfnt.resources(macsfnt.resource_fork(blob))
                self.assertEqual([(t, i, n) for t, i, n, _ in res],
                                 [(b"FOND", 128, "Synth"), (b"sfnt", 128, "Synth"), (b"sfnt", 129, ""), (b"NFNT", 200, "")])
                self.assertEqual(res[1][3], self.ttf)
        from fontTools.misc.macRes import ResourceReader     # an independent reader of the same fork
        rr = ResourceReader(io.BytesIO(self.fork))
        self.assertEqual(rr.getIndResource("sfnt", 1).data, self.ttf)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            fork = os.path.join(d, "Synth.dfont")
            with open(fork, "wb") as fh:
                fh.write(self.fork)
            tool = os.path.join(HERE, "macsfnt.py")
            r = subprocess.run([sys.executable, tool, "list", fork], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.splitlines()[1], "sfnt\t128\tSynth\t%d" % len(self.ttf))
            ttf = os.path.join(d, "s.ttf")
            r = subprocess.run([sys.executable, tool, "extract", fork, ttf, "--id", "129"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(open(ttf, "rb").read(), self.ttf)
            r = subprocess.run([sys.executable, tool, "cmap", ttf], capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), "platform=1 encoding=3 format=2 entries=3 hangul=1")
            uni = os.path.join(d, "u.ttf")
            r = subprocess.run([sys.executable, tool, "unicode", ttf, uni], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("3 code points", r.stdout)
            r = subprocess.run([sys.executable, tool, "unicode", uni, os.path.join(d, "again.ttf")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("already has a Unicode", r.stderr)
            r = subprocess.run([sys.executable, tool, "extract", ttf, os.path.join(d, "x.ttf")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertNotIn("Traceback", r.stderr)
            # mkfont.py draws the syllable through the added Unicode subtable
            svf = os.path.join(d, "s.svf")
            r = subprocess.run([sys.executable, os.path.join(HERE, "mkfont.py"), uni, svf, "--size", "16", "--bpp", "1",
                                "--unicode", "0041,AC00,3000", "--only-listed"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            import jamoset
            f = jamoset.parse_svfn(open(svf, "rb").read())
            self.assertEqual(sorted(f.glyphs), [0x41, 0x3000, 0xAC00])
            self.assertTrue(any(f.glyphs[0xAC00]))


if __name__ == "__main__":
    unittest.main()
