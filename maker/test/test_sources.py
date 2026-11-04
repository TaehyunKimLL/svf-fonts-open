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

    def test_walk_dedupes_overlapping_roots_by_inode(self):
        root = os.path.join(self.tmp, "r")
        self.put("r/x.ttf")
        self.put("r/sub/y.ttf")
        sub = os.path.join(root, "sub")
        for roots in ([root, root], [root, sub], [os.path.join(root, "x.ttf"), root]):
            files, _ = Sources("local", roots).walk()
            self.assertEqual(sorted(f[2] for f in files), [os.path.join(root, "sub/y.ttf"), os.path.join(root, "x.ttf")],
                             roots)
        files, _ = Sources("local", [root, sub]).walk()
        self.assertEqual({f[0] for f in files}, {0})                    # the first root keeps the file

    def test_overlaps_by_inode(self):
        a = os.path.join(self.tmp, "a")
        self.put("a/b/c.txt")
        link = os.path.join(self.tmp, "alias")
        os.symlink(self.tmp, link)
        self.assertTrue(sources.overlaps(a, os.path.join(a, "b")))
        self.assertTrue(sources.overlaps(os.path.join(a, "b", "c.txt"), a))
        self.assertTrue(sources.overlaps(a, a))
        self.assertTrue(sources.overlaps(os.path.join(link, "a"), os.path.join(a, "b")))      # through a symlinked parent
        os.makedirs(os.path.join(self.tmp, "a2"))
        self.assertFalse(sources.overlaps(os.path.join(a, "b"), os.path.join(self.tmp, "a2")))
        self.assertEqual(sources.stat_id(a), (os.stat(a).st_dev, os.stat(a).st_ino))
        self.assertIn(sources.stat_id(a), sources.ancestors_ids(os.path.join(a, "b", "c.txt")))

    def test_recorded_kind_wins_over_the_live_filesystem(self):
        f = self.put("in/a.ttf")
        s = Sources("local", [f], kinds=["file"])
        os.remove(f)
        os.makedirs(f)                                            # replaced by a folder of the same name
        self.assertTrue(s.is_file_root(0))
        self.assertEqual(s.abs_of(0, "a.ttf"), f)
        files, refused = s.walk()
        self.assertEqual(files, [])
        self.assertEqual(refused, [(0, "a.ttf", "file is gone or changed")])
        d = os.path.join(self.tmp, "d")
        os.makedirs(d)
        s = Sources("local", [d], kinds=["dir"])
        os.rmdir(d)
        self.put("d", b"x")                                       # now a file
        files, refused = s.walk()
        self.assertEqual((files, refused), ([], [(0, "", "folder is gone or changed")]))

    def test_local_abs_of_refuses_an_inner_symlink(self):
        root = os.path.join(self.tmp, "r")
        self.put("r/a.ttf")
        os.symlink("a.ttf", os.path.join(root, "alias.ttf"))
        os.makedirs(os.path.join(root, "real"))
        os.symlink("real", os.path.join(root, "dirlink"))
        self.put("r/real/z.ttf")
        s = Sources("local", [root])
        self.assertEqual(s.abs_of(0, "a.ttf"), os.path.join(root, "a.ttf"))
        self.assertEqual(s.abs_of(0, "real/z.ttf"), os.path.join(root, "real/z.ttf"))
        for rel in ("alias.ttf", "dirlink/z.ttf"):
            with self.assertRaises(ValueError, msg=rel):
                s.abs_of(0, rel)
        up = Sources("upload", [root])                            # an upload keeps today's rule
        self.assertEqual(up.abs_of(0, "alias.ttf"), os.path.join(root, "alias.ttf"))

    def test_unreadable_subfolder_is_reported(self):
        if os.geteuid() == 0:
            self.skipTest("root reads every folder")
        root = os.path.join(self.tmp, "r")
        self.put("r/ok.ttf")
        self.put("r/locked/x.ttf")
        os.chmod(os.path.join(root, "locked"), 0)
        self.addCleanup(os.chmod, os.path.join(root, "locked"), 0o755)
        files, refused = Sources("local", [root]).walk()
        self.assertEqual([f[1] for f in files], ["ok.ttf"])
        self.assertEqual(refused, [(0, "locked", "unreadable, skipped")])

    def test_inside_with_a_non_path(self):
        self.assertFalse(Sources("local", [self.tmp]).inside(None))

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
