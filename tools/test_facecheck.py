#!/usr/bin/env python3
"""Tests for facecheck.py: the face manifest, its verification, and the map-face check."""
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, HERE_T := os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(HERE_T), "maker"))

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "facecheck.py")


def run(*args, cwd=None):
    return subprocess.run([sys.executable, "-I", TOOL] + list(args), capture_output=True, text=True, cwd=cwd)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def git(repo, *args):
    subprocess.run(["git", "-C", repo] + list(args), check=True, capture_output=True)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def repo(self):
        r = os.path.join(self.d, "repo")
        os.makedirs(r)
        git(r, "init", "-q")
        git(r, "config", "user.email", "t@t")
        git(r, "config", "user.name", "t")
        write(os.path.join(r, "fonts/dos/A.SVF"), b"SVFN-committed")
        write(os.path.join(r, "fonts/dos/KQ.MAP"), b"[fonts]\n")
        write(os.path.join(r, "other/B.SVF"), b"not listed")
        git(r, "add", "-A")
        git(r, "commit", "-q", "-m", "c")
        return r


class ManifestTest(Fixture):
    def test_manifest_reads_committed_blob_not_worktree(self):
        r = self.repo()
        write(os.path.join(r, "fonts/dos/A.SVF"), b"changed in the worktree")
        out = os.path.join(self.d, "m.tsv")
        p = run("manifest", "--git", r, "--rev", "HEAD", "--path", "fonts/dos", "--exclude", "*.MAP", "-o", out)
        self.assertEqual(p.returncode, 0, p.stderr)
        rows = [l.split("\t") for l in open(out).read().splitlines()]
        self.assertEqual(rows, [["fonts/dos/A.SVF", hashlib.sha256(b"SVFN-committed").hexdigest(),
                                 str(len(b"SVFN-committed"))]])


class VerifyTest(Fixture):
    def manifest(self):
        r = self.repo()
        out = os.path.join(self.d, "m.tsv")
        run("manifest", "--git", r, "--rev", "HEAD", "--path", "fonts/dos", "--exclude", "*.MAP", "-o", out)
        return out

    def test_verify_maps_prefix(self):
        m = self.manifest()
        new = os.path.join(self.d, "new")
        write(os.path.join(new, "svf/dos/A.SVF"), b"SVFN-committed")
        p = run("verify", m, "--map", "fonts/dos=svf/dos", cwd=new)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_verify_reports_changed_byte(self):
        m = self.manifest()
        new = os.path.join(self.d, "new")
        write(os.path.join(new, "svf/dos/A.SVF"), b"SVFN-committeD")
        p = run("verify", m, "--map", "fonts/dos=svf/dos", cwd=new)
        self.assertEqual(p.returncode, 1)
        self.assertIn("svf/dos/A.SVF", p.stdout)

    def test_verify_reports_missing_file(self):
        m = self.manifest()
        new = os.path.join(self.d, "new")
        os.makedirs(new)
        p = run("verify", m, "--map", "fonts/dos=svf/dos", cwd=new)
        self.assertEqual(p.returncode, 1)
        self.assertIn("MISSING", p.stdout)


class MapFacesTest(Fixture):
    MAP = (b"; a comment naming GONE.SVF\n[map]\nversion=2\n[fonts]\na=FOO.SVF ; why\n"
           b"b=data:hires_text/fonts/x/y.ttf#0\nc=data:BAR.SVF\n[font]\nface=a,b,original\n")

    def setup_roots(self, skip=None):
        maps = os.path.join(self.d, "maps")
        write(os.path.join(maps, "G.MAP"), self.MAP)
        d1, d2 = os.path.join(self.d, "svf"), os.path.join(self.d, "ttf")
        for p, root in (("FOO.SVF", d1), ("BAR.SVF", d1), ("x/y.ttf", d2)):
            if p != skip:
                write(os.path.join(root, p), b"x")
        return maps, d1, d2

    def test_mapfaces_bare_and_data_paths(self):
        maps, d1, d2 = self.setup_roots()
        p = run("mapfaces", "--maps", maps, "--root", ".=" + d1, "--root", "hires_text/fonts=" + d2)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_mapfaces_reports_missing_data_path(self):
        maps, d1, d2 = self.setup_roots(skip="x/y.ttf")
        p = run("mapfaces", "--maps", maps, "--root", ".=" + d1, "--root", "hires_text/fonts=" + d2)
        self.assertEqual(p.returncode, 1)
        self.assertIn("MISSING", p.stdout)
        self.assertIn("hires_text/fonts/x/y.ttf", p.stdout)

    def test_mapfaces_reports_missing_bare_name(self):
        maps, d1, d2 = self.setup_roots(skip="FOO.SVF")
        p = run("mapfaces", "--maps", maps, "--root", ".=" + d1, "--root", "hires_text/fonts=" + d2)
        self.assertEqual(p.returncode, 1)
        self.assertIn("FOO.SVF", p.stdout)
        self.assertNotIn("GONE.SVF", p.stdout)

    def test_mapfaces_builtin_archive_member(self):
        maps = os.path.join(self.d, "maps")
        write(os.path.join(maps, "T.MAP"), b"[fonts]\nko=data:NotoSansKR-Bold.otf\n")
        cjk = os.path.join(self.d, "fonts-cjk.dat")
        import zipfile
        with zipfile.ZipFile(cjk, "w") as z:
            z.writestr("NotoSansKR-Bold.otf", b"x")
        p = run("mapfaces", "--maps", maps, "--root", ".=" + self.d, "--builtin-zip", cjk)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        p = run("mapfaces", "--maps", maps, "--root", ".=" + self.d)
        self.assertEqual(p.returncode, 1)

SYNTH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "svf_synth.py")
SYNTH_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "svf", "dos", "NEODG16G.SVF")


class JmapFaceTest(unittest.TestCase):
    """The usable rule (svfline.Face, maker/detect.usable_jset) for a JMAP face; the synthetic faces are svf_synth's."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def face(self, *args):
        out = os.path.join(self.tmp.name, "f.svf")
        r = subprocess.run([sys.executable, SYNTH] + list(args) + ["--from", SYNTH_BASE, out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, "rb") as fh:
            return fh.read()

    def test_sparse3_is_a_jamo_face_with_misses_not_composed(self):
        import jamoset
        import svfline
        import detect
        data = self.face("--jmap-variant", "sparse3")
        f = svfline.Face(data)
        self.assertIsInstance(f.tables, jamoset.Jmap)
        self.assertIsInstance(detect.usable_jset(jamoset.parse_svfn(data)), jamoset.Jmap)
        hits = [0xAC00 + s for s in f.tables.entries]
        self.assertTrue(hits)
        for cp in hits[:50]:
            self.assertTrue(f.composed(cp) and f.has(cp), hex(cp))
            self.assertEqual(f.cell(cp), jamoset.compose(f, f.tables, cp))
            self.assertEqual(len(f.coverage(cp)), f.cell_h)
        misses = [cp for cp in range(0xAC00, 0xD7A4) if (cp - 0xAC00) not in f.tables.entries]
        self.assertTrue(misses)
        for cp in misses[:200]:
            self.assertFalse(f.composed(cp), hex(cp))
            self.assertEqual(f.has(cp), cp in f.glyphs)       # the cmap glyph or none, as a plain face

    def test_hybrid2_misses_fall_to_the_fallback(self):
        import svfline
        f = svfline.Face(self.face("--jmap-variant", "hybrid2"))
        self.assertIsNotNone(f.tables.fallback)
        self.assertTrue(all(f.composed(cp) for cp in range(0xAC00, 0xD7A4, 7)))

    def test_missing_piece_and_bad_kinds_are_plain(self):
        import jamoset
        import svfline
        import detect
        for kind in ("jmap_missing_piece", "jmap_short", "jmap_length", "v2_as_v3"):
            with self.subTest(kind=kind):
                out = os.path.join(self.tmp.name, "b.svf")
                r = subprocess.run([sys.executable, SYNTH, "--jmap-bad", kind, "--from", SYNTH_BASE, out],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                with open(out, "rb") as fh:
                    data = fh.read()
                self.assertIsNone(svfline.Face(data).tables)
                self.assertIsNone(detect.usable_jset(jamoset.parse_svfn(data)))


if __name__ == "__main__":
    unittest.main()
