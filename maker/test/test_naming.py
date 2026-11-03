#!/usr/bin/env python3
"""naming.py tests: the name suggestion, the note text and the repository index.

  python3 -m unittest discover -s maker/test -p 'test_*.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hashlib
import tempfile
import unittest
from unittest import mock

import detect
import fixtures
import naming


class SuggestTest(unittest.TestCase):
    def test_abbr(self):
        self.assertEqual(naming.abbr("NanumGothic"), "NANUM"); self.assertEqual(naming.abbr("Gothic A1"), "GOTHI")
        self.assertEqual(naming.abbr("나눔고딕"), "FONT"); self.assertEqual(naming.abbr("D2 Coding"), "D2COD")
    def test_face_names(self):
        self.assertEqual(naming.suggest_face_name("NanumGothic", 16, 2, "precomposed"), "NANUM16A.SVF")
        self.assertEqual(naming.suggest_face_name("Gothic A1", 18, 1, "jamo"), "GOTH18J.SVF")
        self.assertEqual(naming.suggest_face_name("Gothic A1", 120, 2, "jamo"), "GOTH120JA.SVF")  # see the note below
        self.assertEqual(naming.suggest_face_name("x", 16, 1, "precomposed", svf_stem="neodg16"), "NEODG16.SVF")
        self.assertTrue(naming.NAME_RE.match("NANUM16A.SVF")); self.assertFalse(naming.NAME_RE.match("nanum16.svf"))
        # the 120 px suggestion above is 9 characters: the suggestion is still returned, NAME_RE rejects it
        self.assertFalse(naming.NAME_RE.match(naming.suggest_face_name("Gothic A1", 120, 2, "jamo")))
    def test_text_names(self):
        self.assertEqual(naming.suggest_licence_name("NanumGothic", "... SIL Open Font License ..."), "OFLNANUM.TXT")
        self.assertEqual(naming.suggest_licence_name("NanumGothic", "MIT"), "LICNANUM.TXT")
        self.assertEqual(naming.suggest_note_name("Gothic A1"), "GOTHI.TXT")
    def test_note_text(self):
        t = naming.note_text("NanumGothic", "Bold", ["NANUM16.SVF"], "NanumGothic-Bold.ttf", "3.00", "2026-10-21", ["python3 mkfont.py a b"])
        self.assertEqual(t.splitlines()[0], "NanumGothic Bold faces (NANUM16.SVF)")
        self.assertIn("Source: NanumGothic-Bold.ttf", t); self.assertTrue(t.endswith("python3 mkfont.py a b\n"))
    def test_note_text_empty_style_and_several_names(self):
        t = naming.note_text("NanumGothic", "", ["NANUM16.SVF", "NANUM16A.SVF"], "NanumGothic.ttf", "3.00", "2026-10-21", ["python3 mkfont.py a b"])
        self.assertEqual(t.splitlines()[0], "NanumGothic faces (NANUM16.SVF, NANUM16A.SVF)")  # no double space


class NoteTextValidationTest(unittest.TestCase):
    """`note_text` refuses the values that would forge a provenance line or an absurd one."""

    ARGS = {"family": "NanumGothic", "style": "Bold", "names": ["NANUM16.SVF"],
            "source_file": "NanumGothic-Bold.ttf", "version": "3.00", "date": "2026-10-21",
            "commands": ["python3 mkfont.py a b"]}

    def _args(self, **over):
        return dict(self.ARGS, **over)

    def test_a_control_character_in_a_single_line_field_is_refused(self):
        for field in ("family", "style", "source_file", "version", "date"):
            for bad in ("a\x00b", "a\nb", "a\rb", "a\x1bb", "a\x7fb"):
                with self.assertRaises(ValueError, msg="%s %r" % (field, bad)):
                    naming.note_text(**self._args(**{field: bad}))

    def test_a_control_character_in_a_command_is_refused_but_a_newline_is_not(self):
        for bad in ("a\x00b", "a\rb", "a\x1bb", "a\x7fb"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                naming.note_text(**self._args(commands=[bad]))
        # '\n' is the only control character a command may carry: it is what separates command lines
        t = naming.note_text(**self._args(commands=["python3 mkfont.py a", "python3 mkfont.py b\npython3 other"]))
        self.assertTrue(t.endswith("python3 mkfont.py a\npython3 mkfont.py b\npython3 other\n"))

    def test_a_line_longer_than_512_bytes_is_refused(self):
        for field in ("family", "style", "source_file", "version", "date"):
            with self.assertRaises(ValueError, msg=field):
                naming.note_text(**self._args(**{field: "x" * 513}))
            self.assertIn("x" * 512, naming.note_text(**self._args(**{field: "x" * 512})))
        with self.assertRaises(ValueError):
            naming.note_text(**self._args(commands=["y" * 513]))
        with self.assertRaises(ValueError):     # the long line is the second one of a command
            naming.note_text(**self._args(commands=["short\n" + "z" * 513]))
        with self.assertRaises(ValueError):     # the limit is bytes, not characters
            naming.note_text(**self._args(source_file="나" * 171))   # 513 bytes
        self.assertIn("나" * 170, naming.note_text(**self._args(source_file="나" * 170)))   # 510 bytes


class RepoIndexTest(unittest.TestCase):
    def setUp(self):
        self.idx = naming.RepoIndex(os.path.join(fixtures.REPO_DIR, "svf"))
    def test_folders_and_names(self):
        self.assertIn("dos", self.idx.folders); self.assertIn("jamo-extra", self.idx.folders)
        self.assertIn("NEODG16.SVF", self.idx.names["dos"])
    def test_nested_destination(self):
        with tempfile.TemporaryDirectory() as d:                        # a `games/<name>` destination
            os.makedirs(os.path.join(d, "games", "demo"))
            with open(os.path.join(d, "games", "demo", "FACE40.SVF"), "wb") as f:
                f.write(b"SVFN")
            idx = naming.RepoIndex(d)
            self.assertIn("games/demo", idx.folders)
            self.assertIn("FACE40.SVF", idx.names["games/demo"])
        self.assertTrue(naming.DEST_RE.match("games/lb1")); self.assertTrue(naming.DEST_RE.match("new/han-1"))
        self.assertFalse(naming.DEST_RE.match("games/LB1")); self.assertFalse(naming.DEST_RE.match("games"))
    def test_identical_and_clash(self):
        with open(os.path.join(fixtures.REPO_DIR, "svf", "dos", "NEODG16.SVF"), "rb") as f:
            data = f.read()
        self.assertEqual(self.idx.check_face("jamo-extra", "X.SVF", data), ("identical", "dos/NEODG16.SVF"))
        self.assertEqual(self.idx.check_face("dos", "NEODG16.SVF", data + b"\0"), ("clash", "dos/NEODG16.SVF"))
        self.assertEqual(self.idx.check_face("dos", "NEWNAME.SVF", data + b"\0"), ("ok", None))
    def test_clash_is_case_insensitive(self):
        with open(os.path.join(fixtures.REPO_DIR, "svf", "dos", "NEODG16.SVF"), "rb") as f:
            data = f.read()
        self.assertEqual(self.idx.check_face("dos", "neodg16.svf", data + b"\0"), ("clash", "dos/neodg16.svf"))
    def test_text_reuse(self):
        with open(os.path.join(fixtures.REPO_DIR, "svf", "dos", "OFLNANUM.TXT"), "rb") as f:
            ofl = f.read()
        self.assertEqual(self.idx.check_text(ofl), "dos/OFLNANUM.TXT"); self.assertIsNone(self.idx.check_text(b"never"))
        self.assertIsNone(self.idx.check_text(b""))                     # an empty text is never "already present"
        self.assertIn("dos/OFLNANUM.TXT", [t["path"] for t in self.idx.texts])
    def test_text_first_line(self):
        first = {t["path"]: t["first_line"] for t in self.idx.texts}
        self.assertTrue(first["dos/OFLNANUM.TXT"].startswith("Copyright (c) 2010, NHN Corporation"))
        self.assertTrue(first["dos/OFL.TXT"].startswith("Copyright (c) 2017-2021, Eunbin Jeong"))
    def test_sha_of(self):
        path = os.path.join(fixtures.REPO_DIR, "svf", "dos", "NEODG16.SVF")
        with open(path, "rb") as f:
            data = f.read()
        self.assertEqual(self.idx.sha_of("dos/NEODG16.SVF"), hashlib.sha256(data).hexdigest())
        self.assertEqual(self.idx.by_sha[self.idx.sha_of("dos/NEODG16.SVF")], "dos/NEODG16.SVF")
    def test_sha_of_refuses_anything_the_walk_did_not_index(self):
        for rel in ("/etc/passwd", "../../etc/passwd", "dos/../dos/NEODG16.SVF", "dos/MISSING.SVF", "MISSING.SVF", ""):
            with self.assertRaises(ValueError, msg=rel):
                self.idx.sha_of(rel)
    def test_duplicates(self):
        self.assertEqual(naming.duplicates(["A.SVF", "B.SVF", "A.SVF"]), ["A.SVF"])


class RepoIndexTreeTest(unittest.TestCase):
    """What the index knows comes from the directory listing, not from what it managed to read: a name that would
    clash is listed even when the entry is a symlink, and a file that cannot be read is indexed with no sha instead
    of failing the walk."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="svf-maker-naming-")
        self.addCleanup(self.tmp.cleanup)
        self.svf = os.path.join(self.tmp.name, "svf")
        os.makedirs(os.path.join(self.svf, "dos"))

    def put(self, rel, data=b"face"):
        path = os.path.join(self.svf, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_a_symlinked_name_clashes(self):
        target = self.put("real/FOO.SVF", b"face")
        os.symlink(target, os.path.join(self.svf, "dos", "FOO.SVF"))
        idx = naming.RepoIndex(self.svf)
        self.assertIn("FOO.SVF", idx.names["dos"])
        self.assertEqual(idx.check_face("dos", "FOO.SVF", b"other"), ("clash", "dos/FOO.SVF"))
        self.assertIsNone(idx.sha_of("dos/FOO.SVF"))        # a symlink is never read, so it is never "identical"
        self.assertNotIn("dos/FOO.SVF", idx.by_sha.values())

    def test_a_symlinked_directory_name_clashes(self):
        target = os.path.join(self.tmp.name, "elsewhere")
        os.makedirs(target)
        os.symlink(target, os.path.join(self.svf, "dos", "LINK.SVF"))
        idx = naming.RepoIndex(self.svf)
        self.assertIn("LINK.SVF", idx.names["dos"])
        self.assertEqual(idx.check_face("dos", "LINK.SVF", b"other"), ("clash", "dos/LINK.SVF"))

    def test_a_lower_case_name_on_disk_clashes(self):
        self.put("dos/foo.svf", b"face")
        idx = naming.RepoIndex(self.svf)
        self.assertIn("dos", idx.folders)                   # a `*.svf` is a face too
        self.assertIn("FOO.SVF", idx.names["dos"])
        self.assertEqual(idx.check_face("dos", "FOO.SVF", b"other"), ("clash", "dos/FOO.SVF"))
        self.assertEqual(idx.check_face("dos", "foo.svf", b"other"), ("clash", "dos/foo.svf"))

    @unittest.skipIf(os.geteuid() == 0, "root reads a mode-000 file")
    def test_an_unreadable_file_does_not_break_the_index(self):
        path = self.put("dos/BAD.SVF", b"face")
        os.chmod(path, 0)
        idx = naming.RepoIndex(self.svf)                    # no PermissionError
        self.assertIn("BAD.SVF", idx.names["dos"])
        self.assertIsNone(idx.sha_of("dos/BAD.SVF"))
        self.assertEqual(idx.check_face("dos", "BAD.SVF", b"other"), ("clash", "dos/BAD.SVF"))
        self.assertEqual(idx.check_face("dos", "BAD.SVF", b"face"), ("clash", "dos/BAD.SVF"))   # not "identical"

    def test_a_file_that_vanishes_after_the_walk(self):
        path = self.put("dos/GONE.SVF", b"face")

        class Vanishing(naming.RepoIndex):
            def _walk(self):
                out = super()._walk()
                os.unlink(path)                             # between the walk and the reads
                return out

        idx = Vanishing(self.svf)                           # no FileNotFoundError
        self.assertIn("GONE.SVF", idx.names["dos"])
        self.assertIsNone(idx.sha_of("dos/GONE.SVF"))
        self.assertEqual(idx.check_face("dos", "GONE.SVF", b"face"), ("clash", "dos/GONE.SVF"))

    def test_check_text_never_matches_an_empty_text(self):
        self.put("dos/EMPTY.TXT", b"")
        self.put("dos/REAL.TXT", b"licence")
        idx = naming.RepoIndex(self.svf)
        self.assertIn(hashlib.sha256(b"").hexdigest(), idx.by_sha)      # the zero-byte file is indexed
        self.assertIsNone(idx.check_text(b""))                          # but an empty text is never "already present"
        self.assertEqual(idx.check_text(b"licence"), "dos/REAL.TXT")

    def test_a_large_file_is_hashed_in_chunks(self):
        data = os.urandom(3 << 20)
        self.put("dos/BIG.SVF", data)
        real_open = open
        reads = []

        class Counting:
            def __init__(self, f):
                self._f = f
            def read(self, n=-1):
                reads.append(n)
                return self._f.read(n)
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return self._f.__exit__(*exc)

        def spy(path, *a, **kw):
            f = real_open(path, *a, **kw)
            return Counting(f) if str(path).endswith("BIG.SVF") else f

        with mock.patch("builtins.open", spy):
            idx = naming.RepoIndex(self.svf)
        self.assertEqual(idx.sha_of("dos/BIG.SVF"), hashlib.sha256(data).hexdigest())
        chunk = naming.CHUNK_BYTES
        self.assertTrue(all(0 < n <= chunk for n in reads), reads)      # always a bounded read, never read()
        self.assertEqual(len(reads), -(-len(data) // chunk) + 1)        # one read per chunk, then the EOF read


class FirstLineTest(unittest.TestCase):
    """`naming._first_line` must equal `detect._first_line`, or the page's "use an existing licence" line drifts."""

    CASES = [b"\xef\xbb\xbfFamily A1\nsecond\n", b"\n\n\nTitle\n", b"line one\r\nline two\r\n", b"", b"   \n  trimmed  \n",
             b"no trailing newline", ("x" * 300).encode()]

    def test_matches_detect_first_line(self):
        with tempfile.TemporaryDirectory(prefix="svf-maker-firstline-") as d:
            for i, data in enumerate(self.CASES):
                path = os.path.join(d, "case%d.txt" % i)
                with open(path, "wb") as f:
                    f.write(data)
                self.assertEqual(naming._first_line(data), detect._first_line(path), repr(data))

    def test_matches_detect_first_line_on_the_checkout(self):
        texts = []
        for root, dirs, files in os.walk(os.path.join(fixtures.REPO_DIR, "svf")):
            texts += [os.path.join(root, n) for n in files if n.upper().endswith(".TXT")]
        self.assertTrue(texts)
        for path in texts:
            with open(path, "rb") as f:
                self.assertEqual(naming._first_line(f.read()), detect._first_line(path), path)


if __name__ == "__main__":
    unittest.main()


class FixRoundTwoTest(unittest.TestCase):
    def _tree(self):
        import tempfile
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "dos"))
        with open(os.path.join(d, "dos", "A.SVF"), "wb") as f:
            f.write(b"x")
        open(os.path.join(d, "dos", "EMPTY.SVF"), "wb").close()
        return d

    def test_unlisted_folder_names_clash(self):
        d = self._tree()
        locked = os.path.join(d, "locked")
        os.makedirs(locked)
        os.chmod(locked, 0)
        try:
            if os.access(locked, os.R_OK):
                self.skipTest("running as a user who can read mode-000 folders")
            idx = naming.RepoIndex(d)
            self.assertEqual(idx.check_face("locked", "NEW.SVF", b"y")[0], "clash")
        finally:
            os.chmod(locked, 0o755)

    def test_empty_data_is_never_identical(self):
        idx = naming.RepoIndex(self._tree())
        self.assertNotEqual(idx.check_face("dos", "NEW.SVF", b"")[0], "identical")

    def test_unreadable_txt_not_offered(self):
        d = self._tree()
        p = os.path.join(d, "dos", "LIC.TXT")
        with open(p, "w") as f:
            f.write("x")
        os.chmod(p, 0)
        try:
            if os.access(p, os.R_OK):
                self.skipTest("running as a user who can read mode-000 files")
            idx = naming.RepoIndex(d)
            self.assertNotIn("dos/LIC.TXT", [t["path"] for t in idx.texts])
        finally:
            os.chmod(p, 0o644)

    def test_unicode_line_breaks_and_bidi_refused(self):
        for ch in ("\u0085", "\u2028", "\u2029", "\u202e"):
            with self.assertRaises(ValueError):
                naming.note_text("Fam" + ch, "", ["A.SVF"], "a.ttf", "1", "2026-10-21", [])

    def test_command_trailing_newline_leaves_no_blank_line(self):
        text = naming.note_text("Fam", "", ["A.SVF"], "a.ttf", "1", "2026-10-21", ["cmd one\n"])
        self.assertTrue(text.endswith("cmd one\n"))
        self.assertNotIn("\n\n\n", text)
