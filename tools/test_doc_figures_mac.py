#!/usr/bin/env python3
"""tools/doc_figures_mac.py on synthetic data: the bounds-checked 'bloc' / 'EBLC' strike reader and the skip report of
--check when a font folder or file is not given or not there."""
import contextlib
import io
import os
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import doc_figures_mac as D  # noqa: E402


def sfnt(tables):
    """An sfnt file of @p tables {tag: bytes} (no checksums: the reader does not use them)."""
    n = len(tables)
    head = struct.pack(">IHHHH", 0x00010000, n, 0, 0, 0)
    off = 12 + 16 * n
    dirs, body = b"", b""
    for tag, data in tables.items():
        dirs += struct.pack(">4sIII", tag, 0, off + len(body), len(data))
        body += data
    return head + dirs + body


def bloc(ppems):
    """A 'bloc' table of one 48-byte bitmapSizeTable per ppem (ppemY at byte 45)."""
    out = struct.pack(">II", 0x00020000, len(ppems))
    for p in ppems:
        rec = bytearray(48)
        rec[44] = rec[45] = p
        out += bytes(rec)
    return out


class StrikeTest(unittest.TestCase):
    def strikes(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "f.ttf")
            with open(path, "wb") as fh:
                fh.write(data)
            return D.sfnt_strikes(path)

    def test_bloc(self):
        self.assertEqual(self.strikes(sfnt({b"bloc": bloc([24, 12, 16, 12])})), [12, 16, 24])

    def test_eblc(self):
        self.assertEqual(self.strikes(sfnt({b"EBLC": bloc([11, 13])})), [11, 13])

    def test_none(self):
        self.assertEqual(self.strikes(sfnt({b"head": bytes(54)})), [])

    def test_truncated(self):
        self.assertEqual(self.strikes(b""), [])
        self.assertEqual(self.strikes(b"\0\1\0\0\0\x09"), [])                    # header only
        whole = sfnt({b"bloc": bloc([12, 16])})
        self.assertEqual(self.strikes(whole[:-10]), [])                           # table past the end
        short = bloc([12, 16])[:-48]                                               # count 2, one record
        self.assertEqual(self.strikes(sfnt({b"bloc": short})), [])
        self.assertEqual(self.strikes(sfnt({b"bloc": b"\0\2\0\0"})), [])         # under 8 bytes
        huge = struct.pack(">IHHHH", 0x00010000, 0xFFFF, 0, 0, 0)                 # table count past the file
        self.assertEqual(self.strikes(huge), [])


class SkipTest(unittest.TestCase):
    def test_check_reports_skipped(self):
        args = D.argparse.Namespace(ht10=None, ht712=None, htbl=None, kh753=None, kh85=None)
        with contextlib.redirect_stdout(io.StringIO()):
            images, skipped = D.render(args)
        self.assertEqual(images, {})
        self.assertEqual(skipped, [f[0] for f in D.FACES])
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(D.write_or_check({}, tmp, True, skipped), 1)
            self.assertIn("14 face(s) skipped", out.getvalue())

    def test_missing_htbl_skips_712(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = D.argparse.Namespace(ht10=None, ht712=tmp, htbl=None, kh753=None, kh85=tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                images, skipped = D.render(args)
            self.assertEqual(images, {})
            self.assertIn("ht712-seoul12.png", skipped)
            self.assertIn("kh85-hangang16.png", skipped)                          # its file is not there


if __name__ == "__main__":
    unittest.main()
