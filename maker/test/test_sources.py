#!/usr/bin/env python3
"""`sources.Sources`: the one resolver for a job's input paths (upload: one root; local: picked roots).

  python3 -m unittest discover -s maker/test -p 'test_sources.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import tempfile
import unittest
from unittest import mock

import sources
from sources import Sources


class SourcesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = os.path.realpath(self._tmp.name)

    def put(self, rel, data=b"x"):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_upload_abs_of_matches_the_old_rule(self):
        u = os.path.join(self.tmp, "U")
        self.put("U/a/b.ttf")
        os.symlink("/etc", os.path.join(u, "out"))
        s = Sources("upload", [u])
        self.assertEqual(s.abs_of(0, "a/b.ttf"), os.path.join(u, "a/b.ttf"))
        for rel in ("../x", "/etc/passwd", "out/passwd", "", "a\0b"):
            with self.assertRaises(ValueError, msg=repr(rel)):
                s.abs_of(0, rel)
        for root in (1, True, -1, None, "0"):
            with self.assertRaises(ValueError, msg=repr(root)):
                s.abs_of(root, "a/b.ttf")

    def test_file_root(self):
        f = self.put("in/Seoul12.rsrc")
        s = Sources("local", [f])
        self.assertEqual(s.abs_of(0, "Seoul12.rsrc"), f)
        with self.assertRaises(ValueError):
            s.abs_of(0, "other.rsrc")
        self.assertTrue(s.is_file_root(0))
        self.assertTrue(s.inside(f))
        self.assertEqual(s.rel_of(f), (0, "Seoul12.rsrc"))

    def test_two_roots_same_rel(self):
        a, b = os.path.join(self.tmp, "A"), os.path.join(self.tmp, "B")
        self.put("A/OFL.txt")
        self.put("B/OFL.txt")
        s = Sources("local", [a, b])
        self.assertEqual((s.abs_of(0, "OFL.txt"), s.abs_of(1, "OFL.txt")), (a + "/OFL.txt", b + "/OFL.txt"))
        with self.assertRaises(ValueError):
            s.abs_of(0, ".")                                  # the root itself: refused
        self.assertEqual(s.rel_of(b + "/OFL.txt"), (1, "OFL.txt"))
        self.assertFalse(s.is_file_root(0))
        self.assertFalse(s.inside(self.tmp + "/elsewhere.txt"))
        with self.assertRaises(ValueError):
            s.rel_of(self.tmp + "/elsewhere.txt")

    def test_walk_skips_links_and_devices(self):
        root = os.path.join(self.tmp, "r")
        x = self.put("r/x.ttf")
        os.makedirs(os.path.join(root, "real"))
        os.symlink("x.ttf", os.path.join(root, "link"))
        os.symlink("real", os.path.join(root, "sub"))
        os.mkfifo(os.path.join(root, "fifo"))
        files, refused = Sources("local", [root]).walk()
        self.assertEqual(files, [(0, "x.ttf", x)])
        self.assertEqual(refused, [(0, "link", "symlink, skipped"), (0, "sub", "symlink, skipped")])
        files, refused = Sources("upload", [root]).walk()            # an upload walk omits a directory link silently
        self.assertEqual(files, [(0, "x.ttf", x)])
        self.assertEqual(refused, [(0, "link", "symlink, skipped")])

    def test_walk_caps(self):
        root = os.path.join(self.tmp, "r")
        for n in range(5):
            self.put("r/f%d.bin" % n)
        with mock.patch.object(sources, "FILE_CAP", 3):
            files, refused = Sources("local", [root]).walk()
        self.assertEqual(len(files), 3)
        self.assertEqual(refused[-1], (0, "", "more than 3 files: choose a smaller folder"))
        root2 = os.path.join(self.tmp, "r2")
        self.put("r2/big.bin", b"x" * 20)
        self.put("r2/ok.bin", b"x" * 5)
        with mock.patch.object(sources, "LOCAL_FILE_CAP", 10):
            files, refused = Sources("local", [root2]).walk()
        self.assertEqual([f[1] for f in files], ["ok.bin"])
        self.assertEqual(refused, [(0, "big.bin", "too large, skipped")])
        with mock.patch.object(sources, "LOCAL_BYTES_CAP", 8):
            files, refused = Sources("local", [root2]).walk()
        self.assertEqual(refused[-1], (0, "", "more than 1 GiB: choose a smaller folder"))

    def test_upload_walk_has_no_caps(self):
        root = os.path.join(self.tmp, "r")
        for n in range(3):
            self.put("r/f%d.bin" % n)
        with mock.patch.object(sources, "FILE_CAP", 1):
            files, refused = Sources("upload", [root]).walk()
        self.assertEqual((len(files), refused), (3, []))

    def test_file_root_walk(self):
        f = self.put("in/Seoul12.rsrc")
        self.assertEqual(Sources("local", [f]).walk(), ([(0, "Seoul12.rsrc", f)], []))

    def test_coerce(self):
        self.assertEqual(Sources.coerce("/u").roots, ["/u"])
        self.assertEqual(Sources.coerce("/u").kind, "upload")
        s = Sources("local", ["/a"])
        self.assertIs(Sources.coerce(s), s)
        self.assertIsNone(Sources.coerce(None))
        with self.assertRaises(ValueError):
            Sources("nope", ["/a"])


if __name__ == "__main__":
    unittest.main()
