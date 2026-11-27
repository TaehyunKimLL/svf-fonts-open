#!/usr/bin/env python3
"""tools/doc_figures_mac.py on synthetic data: the bounds-checked 'bloc' / 'EBLC' strike reader, the skip report of
--check when a font folder or file is not given or not there, and the bootstrap the tools are started with."""
import contextlib
import io
import json
import os
import subprocess
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
            self.assertIn("15 face(s) skipped", out.getvalue())

    def test_missing_htbl_skips_712(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = D.argparse.Namespace(ht10=None, ht712=tmp, htbl=None, kh753=None, kh85=tmp)
            with contextlib.redirect_stdout(io.StringIO()):
                images, skipped = D.render(args)
            self.assertEqual(images, {})
            self.assertIn("ht712-seoul12.png", skipped)
            self.assertIn("kh85-hangang16.png", skipped)                          # its file is not there


PROBE = """import json, os, sys
print(json.dumps({"path": sys.path, "cwd": os.getcwd(), "argv": sys.argv}))
"""


class BootTest(unittest.TestCase):
    def run_boot(self, usersite):
        """sys.path, cwd and argv a probe script sees when started by BOOT from a temporary working directory."""
        with tempfile.TemporaryDirectory() as tools, tempfile.TemporaryDirectory() as cwd:
            probe = os.path.join(tools, "probe.py")
            with open(probe, "w") as fh:
                fh.write(PROBE)
            with open(os.path.join(cwd, "json.py"), "w") as fh:      # a planted module in the working directory
                fh.write("raise SystemExit('planted json.py imported')\n")
            r = subprocess.run([sys.executable, "-I", "-c", D.BOOT, usersite, probe, "a", "b"], cwd=cwd,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout)
            return out, tools, os.path.realpath(cwd)

    def test_cwd_not_on_path(self):
        out, tools, cwd = self.run_boot("")
        self.assertEqual(os.path.realpath(out["cwd"]), cwd)
        real = [os.path.realpath(p) if p else p for p in out["path"]]
        self.assertNotIn(cwd, real)
        self.assertNotIn("", out["path"])
        self.assertEqual(out["path"][0], tools)                                  # the tool's own folder first
        self.assertEqual(out["argv"][1:], ["a", "b"])

    def test_user_site_last(self):
        with tempfile.TemporaryDirectory() as site:
            out, _, _ = self.run_boot(site)
            self.assertEqual(out["path"][-1], site)
            self.assertEqual(out["path"].count(site), 1)

    def test_user_site_absent(self):
        missing = os.path.join(tempfile.gettempdir(), "no-such-user-site-for-doc-figures-mac")
        out, _, _ = self.run_boot(missing)
        self.assertNotIn(missing, out["path"])

    def test_user_site_from_this_python(self):
        u = D.user_site()
        self.assertIsInstance(u, str)


if __name__ == "__main__":
    unittest.main()
