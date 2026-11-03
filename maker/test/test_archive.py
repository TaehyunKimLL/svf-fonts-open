#!/usr/bin/env python3
"""archive.py tests: the path guard, the size/ratio bombs, symlinks and nested archives.

  python3 -m unittest discover -s maker/test -p 'test_*.py'
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
import lzma
import shutil
import subprocess
import tarfile
import tempfile
import time
import tracemalloc
import unittest
import warnings
import zipfile
from unittest import mock

import archive
import fixtures

FIXTURE_ROOT = None


def setUpModule():
    """One fixture tree for the whole module: the roundtrip archives the tree four times."""
    global FIXTURE_ROOT
    FIXTURE_ROOT = tempfile.mkdtemp(prefix="svf-maker-archive-")
    fixtures.write_fixtures(FIXTURE_ROOT)


def tearDownModule():
    shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)


def rel_paths(root):
    """Every directory and file below @p root as a relative path (sorted, no "." entry)."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        if rel != ".":
            out.append(rel)
        out.extend(os.path.join(rel, n) if rel != "." else n for n in filenames)
    return sorted(out)


def make_archive(root, kind, tmp):
    """An archive of @p root's tree at <tmp>/fixtures_<kind>, through `shutil.make_archive`.

    The tar kinds of `shutil.make_archive` name every member with a leading "./" and start with a bare "."
    member (`tar -cf x.tar .` does the same), so the roundtrip also exercises `unpack`'s member normalisation.
    Returns the archive path.
    """
    fmt = {"zip": "zip", "tar": "tar", "tar.gz": "gztar", "tar.xz": "xztar"}[kind]
    return shutil.make_archive(os.path.join(tmp, "fixtures_" + kind.replace(".", "_")), fmt, root_dir=root)


def dot_tar(root, out, mode="w"):
    """A tar of @p root whose members are ".", "./a" and "./a/b" (`t.add(root, arcname=".")`)."""
    with tarfile.open(out, mode) as t:
        t.add(root, arcname=".", recursive=True)
    return out


def patch_zip(path, flags=None, method=None):
    """Rewrite a single-member zip's local and central headers: set @p flags and/or @p method.

    A zip cannot be written encrypted or with Deflate64 through `zipfile`, so a hostile member is made by
    editing the two headers of a stored entry.
    """
    with open(path, "rb") as f:
        data = bytearray(f.read())
    assert data[:4] == b"PK\x03\x04", data[:4]
    if flags is not None:
        data[6:8] = flags.to_bytes(2, "little")
    if method is not None:
        data[8:10] = method.to_bytes(2, "little")
    c = data.rfind(b"PK\x01\x02")
    assert c >= 0
    if flags is not None:
        data[c + 8:c + 10] = flags.to_bytes(2, "little")
    if method is not None:
        data[c + 10:c + 12] = method.to_bytes(2, "little")
    with open(path, "wb") as f:
        f.write(bytes(data))
    return path


def header_bomb(path, typeflag, size, fmt=tarfile.PAX_FORMAT):
    """A small .tar.gz whose first header claims a @p size byte long pax/GNU-long header.

    The payload is written in 1 MB chunks through a streaming gzip writer, so the test never holds @p size
    bytes in memory. Returns the archive path.
    """
    info = tarfile.TarInfo("././@PaxHeader")
    info.type = typeflag
    info.size = size
    header = info.tobuf(fmt)
    assert len(header) == 512
    with gzip.open(path, "wb", compresslevel=1) as g:
        g.write(header)
        chunk = bytes(1 << 20)
        for _ in range(size // len(chunk)):
            g.write(chunk)
    return path


def tar_head(magic=b"ustar"):
    """A 512 byte tar header with @p magic at 257."""
    head = bytearray(512)
    head[257:262] = magic
    return bytes(head)


def gnu_tar():
    """The path to GNU tar, or None: the sparse-member test needs `--sparse` and `--format`."""
    tar = shutil.which("tar")
    if not tar:
        return None
    try:
        out = subprocess.run([tar, "--version"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return tar if "GNU tar" in out else None


GNU_TAR = gnu_tar()


def total_size(root):
    """The sum of the file sizes below @p root (0 when @p root does not exist)."""
    total = 0
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            total += os.path.getsize(os.path.join(dirpath, name))
    return total


def patch_zip_name(path, raw_name, flags=0x800):
    """Replace a single-member zip's name bytes (same length) and set @p flags in both headers.

    `zipfile` decodes a name with flag bit 11 set as strict UTF-8, and `writestr` only sets that flag for a name
    that is not ASCII, so the only way to build the hostile entry is to edit the two headers by hand.
    """
    with open(path, "rb") as f:
        data = bytearray(f.read())
    n = int.from_bytes(data[26:28], "little")
    assert len(raw_name) == n, (len(raw_name), n)
    data[30:30 + n] = raw_name
    data[6:8] = flags.to_bytes(2, "little")
    c = data.rfind(b"PK\x01\x02")
    cn = int.from_bytes(data[c + 28:c + 30], "little")
    assert len(raw_name) == cn, (len(raw_name), cn)
    data[c + 46:c + 46 + cn] = raw_name
    data[c + 8:c + 10] = flags.to_bytes(2, "little")
    with open(path, "wb") as f:
        f.write(bytes(data))
    return path


class RepeatStream:
    """A read-only stream of @p total bytes made of @p block repeated, never held whole in memory.

    `tarfile.addfile` copies a member's data from it in small chunks, so a test can declare a huge member (to
    drive the peek's declared size) while only the small packed archive reaches disk.
    """

    def __init__(self, block, total):
        self.block = block
        self.left = total

    def read(self, size=-1):
        if self.left <= 0:
            return b""
        if size is None or size < 0:
            size = self.left
        size = min(size, self.left)
        reps = (size + len(self.block) - 1) // len(self.block)
        data = (self.block * reps)[:size]
        self.left -= size
        return data


def inner_tar(kind, size):
    """The bytes of a tar (or tar.gz / tar.xz) holding one @p size byte member `a`."""
    buf = io.BytesIO()
    mode = {"tar": "w", "tar.gz": "w:gz", "tar.xz": "w:xz"}[kind]
    with tarfile.open(fileobj=buf, mode=mode) as t:
        i = tarfile.TarInfo("a")
        i.size = size
        t.addfile(i, io.BytesIO(b"x" * size))
    return buf.getvalue()


def outer_tar(path, members, mode="w"):
    """A tar (or tar.gz / tar.xz) at @p path holding the `(name, data)` byte @p members."""
    with tarfile.open(path, mode) as t:
        for name, data in members:
            i = tarfile.TarInfo(name)
            i.size = len(data)
            t.addfile(i, io.BytesIO(data))
    return path


class PathTest(unittest.TestCase):
    def test_rules(self):
        self.assertIsNone(archive.check_rel_path("fonts/a.ttf"))
        self.assertEqual(archive.check_rel_path("../x"), "path has ..")
        self.assertEqual(archive.check_rel_path("/etc/passwd"), "absolute path")
        self.assertEqual(archive.check_rel_path("a\\b"), "backslash in path")
        self.assertEqual(archive.check_rel_path("a\x01b"), "control character in path")
        self.assertEqual(archive.check_rel_path("x" * 256), "path component over 255 bytes")

    def test_more_rules(self):
        self.assertEqual(archive.check_rel_path(""), "empty path")
        self.assertEqual(archive.check_rel_path("a/../b"), "path has ..")
        self.assertEqual(archive.check_rel_path("a/./b"), "path has .")
        self.assertEqual(archive.check_rel_path("."), "path has .")
        self.assertEqual(archive.check_rel_path("a\x7fb"), "control character in path")
        self.assertEqual(archive.check_rel_path("a/" + "x" * 256), "path component over 255 bytes")
        self.assertIsNone(archive.check_rel_path("a/b/c.txt"))
        self.assertIsNone(archive.check_rel_path("fonts/" + "x" * 255))
        self.assertIsNone(archive.check_rel_path("나눔/고딕.ttf"))   # a multi-byte component counts its bytes

    def test_empty_components_are_refused(self):
        # W5: a trailing slash or "//" is a malformed path, not a second spelling of the same file
        self.assertEqual(archive.check_rel_path("a//b"), "empty path component")
        self.assertEqual(archive.check_rel_path("a/b/"), "empty path component")
        self.assertEqual(archive.check_rel_path("//a"), "absolute path")   # the leading slash still wins

    def test_drive_letters_are_refused(self):
        self.assertEqual(archive.check_rel_path("C:/evil"), "drive letter in path")
        self.assertEqual(archive.check_rel_path("C:evil"), "drive letter in path")
        self.assertEqual(archive.check_rel_path("c:/x"), "drive letter in path")
        self.assertEqual(archive.check_rel_path("Z:"), "drive letter in path")
        self.assertIsNone(archive.check_rel_path("a/C:evil"))        # only a *first* component is a drive
        self.assertIsNone(archive.check_rel_path("C"))

    def test_unicode_control_categories_are_refused(self):
        for ch in ("\x01", "\x7f", "\x85", "\u2028", "\u2029", "\u202e", "\u200b"):
            self.assertEqual(archive.check_rel_path("a" + ch + "b"), "control character in path", repr(ch))
            self.assertEqual(archive.check_rel_path("a/" + ch), "control character in path", repr(ch))

    def test_path_length_and_depth_are_bounded(self):
        self.assertIsNone(archive.check_rel_path("/".join(["a" * 255] * 4)))               # 1023 bytes, 4 parts
        self.assertEqual(archive.check_rel_path("/".join(["a" * 255] * 4 + ["a"] * 2)), "path too long")
        self.assertIsNone(archive.check_rel_path("/".join(["a"] * 32)))                    # 32 components is the bound
        self.assertEqual(archive.check_rel_path("/".join(["a"] * 33)), "path too long")
        self.assertEqual(archive.check_rel_path("x" * 256), "path component over 255 bytes")   # the part wins
        self.assertEqual(archive.check_rel_path("a/" + "x" * 256), "path component over 255 bytes")


class KindTest(unittest.TestCase):
    def test_kind_of(self):
        self.assertEqual(archive.kind_of(b"PK\x03\x04" + bytes(60)), "zip")
        self.assertEqual(archive.kind_of(b"\x1f\x8b" + bytes(60)), "gzip")
        self.assertEqual(archive.kind_of(b"\xfd7zXZ\x00" + bytes(60)), "xz")
        self.assertEqual(archive.kind_of(tar_head()), "tar")
        self.assertIsNone(archive.kind_of(tar_head()[:511]))          # a tar header needs the full 512 bytes
        self.assertIsNone(archive.kind_of(b"STARTFONT 2.1\n" + bytes(500)))
        self.assertIsNone(archive.kind_of(b""))

    def test_is_nested_archive(self):
        self.assertTrue(archive.is_nested_archive(b"PK\x03\x04" + bytes(60), lambda: io.BytesIO(b"")))
        self.assertTrue(archive.is_nested_archive(tar_head(), lambda: io.BytesIO(b"")))
        plain = gzip.compress(b"STARTFONT 2.1\n" + bytes(600))
        self.assertFalse(archive.is_nested_archive(plain[:512], lambda: io.BytesIO(plain)))
        inner = io.BytesIO()
        with tarfile.open(fileobj=inner, mode="w") as t:
            i = tarfile.TarInfo("a")
            i.size = 1
            t.addfile(i, io.BytesIO(b"x"))
        nested = gzip.compress(inner.getvalue())
        self.assertTrue(archive.is_nested_archive(nested[:512], lambda: io.BytesIO(nested)))
        self.assertFalse(archive.is_nested_archive(b"STARTFONT 2.1\n", lambda: io.BytesIO(b"")))


class UnpackTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="svf-maker-archive-t-")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_zip_tar_gz_xz_roundtrip(self):
        for kind in ("zip", "tar", "tar.gz", "tar.xz"):
            arc = make_archive(FIXTURE_ROOT, kind, self.d)         # helper in the test file: shutil.make_archive
            dest = os.path.join(self.d, "out-" + kind); r = archive.unpack(arc, dest)
            self.assertIsNone(r["stopped"]); self.assertTrue(os.path.isfile(os.path.join(dest, "nanum", "NanumGothic-Bold.ttf")))
            if fixtures.HAS_PCF:                                            # a gzip member with no tar inside is a plain file
                self.assertTrue(os.path.isfile(os.path.join(dest, "pcf", "18x18ko.pcf.gz")))
    def test_gzip_member_without_tar_is_kept_but_tar_gz_member_stops(self):
        p = os.path.join(self.d, "mixed.zip"); inner = io.BytesIO()
        with tarfile.open(fileobj=inner, mode="w:gz") as t:
            i = tarfile.TarInfo("a"); i.size = 1; t.addfile(i, io.BytesIO(b"x"))
        with zipfile.ZipFile(p, "w") as z: z.writestr("plain.bdf.gz", gzip.compress(b"STARTFONT 2.1\n")); z.writestr("nested.tar.gz", inner.getvalue())
        r = archive.unpack(p, os.path.join(self.d, "m"))
        self.assertTrue(os.path.isfile(os.path.join(self.d, "m", "plain.bdf.gz")))
        self.assertEqual(r["stopped"], "nested archive nested.tar.gz (listed, not opened)")
    def test_single_gzip_file(self):
        p = os.path.join(self.d, "a.bdf.gz")
        # the brief's `gzip.open(p, "wb").write(...)` leaves the file empty (nothing is flushed until the object is
        # collected), so the write is closed here
        with gzip.open(p, "wb") as f: f.write(b"STARTFONT 2.1\n")
        r = archive.unpack(p, os.path.join(self.d, "g")); self.assertEqual(r["files"], 1)
        self.assertTrue(os.path.isfile(os.path.join(self.d, "g", "a.bdf")))
    def test_traversal_stops(self):
        p = os.path.join(self.d, "bad.zip")
        with zipfile.ZipFile(p, "w") as z: z.writestr("ok.txt", "x"); z.writestr("../x", "y")
        r = archive.unpack(p, os.path.join(self.d, "t"))
        self.assertEqual(r["stopped"], "../x: path has .."); self.assertTrue(os.path.isfile(os.path.join(self.d, "t", "ok.txt")))
        self.assertFalse(os.path.exists(os.path.join(self.d, "x")))
    def test_bomb_stops_by_member_and_ratio(self):
        p = os.path.join(self.d, "bomb.zip")
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            with z.open("zeros.bin", "w") as m:                                # 1 GB written in chunks, never held in memory
                for _ in range(1024): m.write(bytes(1 << 20))
        r = archive.unpack(p, os.path.join(self.d, "b"), limits=dict(archive.LIMITS, member=1 << 20))
        self.assertTrue(r["stopped"].startswith("zeros.bin: member over"))
        r = archive.unpack(p, os.path.join(self.d, "b2"))
        self.assertIn("ratio", r["stopped"]); self.assertLess(r["bytes"], 1 << 30)
    def test_symlink_and_nested_archive_stop(self):
        p = os.path.join(self.d, "link.tar")
        with tarfile.open(p, "w") as t:
            i = tarfile.TarInfo("l"); i.type = tarfile.SYMTYPE; i.linkname = "/etc/passwd"; t.addfile(i)
        self.assertEqual(archive.unpack(p, os.path.join(self.d, "l"))["stopped"], "l: not a regular file")
        q = os.path.join(self.d, "nest.zip"); inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as z: z.writestr("a", "b")
        with zipfile.ZipFile(q, "w") as z: z.writestr("inner.zip", inner.getvalue())
        self.assertEqual(archive.unpack(q, os.path.join(self.d, "n"))["stopped"], "nested archive inner.zip (listed, not opened)")

    def test_total_limit_stops(self):
        p = os.path.join(self.d, "two.zip")
        with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as z:
            z.writestr("a.bin", bytes(1 << 20)); z.writestr("b.bin", bytes(1 << 20))
        r = archive.unpack(p, os.path.join(self.d, "tt"), limits=dict(archive.LIMITS, total=1 << 20))
        self.assertIn("total over", r["stopped"]); self.assertTrue(os.path.isfile(os.path.join(self.d, "tt", "a.bin")))

    def test_partial_member_is_removed_on_a_stop(self):
        p = os.path.join(self.d, "part.zip")
        with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as z: z.writestr("big.bin", bytes(3 << 20))
        dest = os.path.join(self.d, "p")
        r = archive.unpack(p, dest, limits=dict(archive.LIMITS, member=1 << 20))
        self.assertTrue(r["stopped"].startswith("big.bin: member over"))
        self.assertFalse(os.path.exists(os.path.join(dest, "big.bin")))

    def test_zip_symlink_stops(self):
        p = os.path.join(self.d, "sym.zip")
        info = zipfile.ZipInfo("link"); info.external_attr = 0o120777 << 16
        with zipfile.ZipFile(p, "w") as z: z.writestr(info, "/etc/passwd")
        self.assertEqual(archive.unpack(p, os.path.join(self.d, "sl"))["stopped"], "link: not a regular file")

    def test_not_an_archive(self):
        p = os.path.join(self.d, "plain.bin")
        with open(p, "wb") as f: f.write(b"STARTFONT 2.1\n" + bytes(600))
        r = archive.unpack(p, os.path.join(self.d, "na"))
        self.assertEqual((r["files"], r["bytes"]), (0, 0)); self.assertEqual(r["stopped"], "not an archive")

    def test_broken_archive_stops(self):
        p = os.path.join(self.d, "broken.zip")
        with open(p, "wb") as f: f.write(b"PK\x03\x04" + bytes(600))       # the magic, but no central directory
        self.assertEqual(archive.unpack(p, os.path.join(self.d, "br"))["stopped"], "broken archive")

    def test_path_conflicts_stop(self):
        p = os.path.join(self.d, "conflict.zip")
        with zipfile.ZipFile(p, "w") as z: z.writestr("a", "file"); z.writestr("a/b", "y")
        r = archive.unpack(p, os.path.join(self.d, "cf"))
        self.assertEqual(r["stopped"], "a/b: not a directory"); self.assertEqual(r["files"], 1)
        q = os.path.join(self.d, "conflict2.zip")
        with zipfile.ZipFile(q, "w") as z: z.writestr("a/b", "y"); z.writestr("a", "file")
        r = archive.unpack(q, os.path.join(self.d, "cf2"))
        self.assertEqual(r["stopped"], "a: is a directory"); self.assertEqual(r["files"], 1)

    def test_component_limit_comes_from_limits(self):
        p = os.path.join(self.d, "long.zip")
        with zipfile.ZipFile(p, "w") as z: z.writestr("abcdef.txt", "x")
        r = archive.unpack(p, os.path.join(self.d, "cl"), limits=dict(archive.LIMITS, component=3))
        self.assertEqual(r["stopped"], "abcdef.txt: path component over 3 bytes")

    def test_counts(self):
        p = os.path.join(self.d, "count.zip")
        with zipfile.ZipFile(p, "w") as z: z.writestr("a/one.txt", "12345"); z.writestr("two.txt", "678")
        r = archive.unpack(p, os.path.join(self.d, "c"))
        self.assertEqual((r["files"], r["bytes"], r["stopped"]), (2, 8, None))

    # ---- fix round 1: real-world member names (R1) ------------------------------------------------------------

    def test_dot_named_tar_unpacks_fully(self):
        for kind, mode in (("tar", "w"), ("tar.gz", "w:gz")):
            arc = dot_tar(FIXTURE_ROOT, os.path.join(self.d, "dot." + kind), mode)
            dest = os.path.join(self.d, "dot-out-" + kind)
            r = archive.unpack(arc, dest)
            self.assertIsNone(r["stopped"], kind)
            self.assertTrue(os.path.isfile(os.path.join(dest, "nanum", "NanumGothic-Bold.ttf")), kind)
            self.assertEqual(rel_paths(dest), rel_paths(FIXTURE_ROOT), kind)     # the whole tree, "." skipped

    def test_dot_prefix_is_stripped_repeatedly_but_traversal_still_stops(self):
        p = os.path.join(self.d, "dots.zip")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("ok.txt", "x")
            z.writestr("././a.txt", "y")                                  # "././a.txt" becomes "a.txt"
        dest = os.path.join(self.d, "dots")
        r = archive.unpack(p, dest)
        self.assertIsNone(r["stopped"])
        self.assertTrue(os.path.isfile(os.path.join(dest, "a.txt")))
        for bad, normalized, reason in (("./../x", "../x", "path has .."), ("/x", "/x", "absolute path"),
                                        ("a/./b", "a/./b", "path has ."),
                                        ("C:/evil", "C:/evil", "drive letter in path")):
            q = os.path.join(self.d, "slip.zip")
            with zipfile.ZipFile(q, "w") as z: z.writestr(bad, "y")
            r = archive.unpack(q, os.path.join(self.d, "slip"))
            self.assertEqual(r["stopped"], "%s: %s" % (normalized, reason), bad)
            self.assertFalse(os.path.exists(os.path.join(self.d, "x")), bad)

    # ---- fix round 1: the member-count limit (R3) -------------------------------------------------------------

    def test_member_count_stops_at_the_file_limit(self):
        p = os.path.join(self.d, "many.zip")
        with zipfile.ZipFile(p, "w") as z:
            for i in range(2001):
                z.writestr("f%04d" % i, "")
        dest = os.path.join(self.d, "many")
        r = archive.unpack(p, dest)
        self.assertEqual(r["stopped"], "more than %d files" % archive.LIMITS["files"])
        self.assertEqual(r["files"], archive.LIMITS["files"])
        self.assertTrue(os.path.isfile(os.path.join(dest, "f1999")))
        self.assertFalse(os.path.exists(os.path.join(dest, "f2000")))

    def test_member_count_comes_from_limits(self):
        p = os.path.join(self.d, "four.tar")
        with tarfile.open(p, "w") as t:
            for n in ("a", "b", "c", "d"):
                i = tarfile.TarInfo(n); i.size = 1; t.addfile(i, io.BytesIO(b"x"))
        r = archive.unpack(p, os.path.join(self.d, "four"), limits=dict(archive.LIMITS, files=3))
        self.assertEqual(r["stopped"], "more than 3 files"); self.assertEqual(r["files"], 3)

    def test_unicode_separator_in_a_member_name_stops(self):
        p = os.path.join(self.d, "uni.zip")
        with zipfile.ZipFile(p, "w") as z: z.writestr("a\u2028b", "y")
        r = archive.unpack(p, os.path.join(self.d, "uni"))
        self.assertEqual(r["stopped"], "a\u2028b: control character in path")

    # ---- fix round 1: the tar header bomb and reason truncation (P1) ------------------------------------------

    def test_header_bombs_stop_small(self):
        for typeflag, fmt, label in ((tarfile.XHDTYPE, tarfile.PAX_FORMAT, "pax"),
                                     (tarfile.GNUTYPE_LONGNAME, tarfile.GNU_FORMAT, "longname"),
                                     (tarfile.GNUTYPE_LONGLINK, tarfile.GNU_FORMAT, "longlink")):
            p = header_bomb(os.path.join(self.d, label + ".tar.gz"), typeflag, 400 << 20, fmt=fmt)
            dest = os.path.join(self.d, label)
            tracemalloc.start()
            try:
                r = archive.unpack(p, dest)
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            self.assertEqual(r["stopped"], "header over %d bytes" % (1 << 20), label)
            self.assertLess(peak, 64 << 20, "%s peak %d bytes" % (label, peak))
            self.assertEqual(os.listdir(dest) if os.path.isdir(dest) else [], [], label)

    def test_stop_reason_truncates_a_long_member_name(self):
        p = os.path.join(self.d, "longname.tar")
        with tarfile.open(p, "w") as t:                               # a pax long name, small enough to read
            i = tarfile.TarInfo("x" * 5000); i.size = 0; t.addfile(i)
        r = archive.unpack(p, os.path.join(self.d, "ln"))
        self.assertEqual(r["stopped"], "x" * 200 + ": path component over 255 bytes")

    # ---- fix round 1: encrypted / unsupported zip members (P2) -------------------------------------------------

    def test_encrypted_zip_member_stops(self):
        p = os.path.join(self.d, "enc.zip")
        with zipfile.ZipFile(p, "w") as z: z.writestr("secret.txt", "hello")
        patch_zip(p, flags=0x1)
        r = archive.unpack(p, os.path.join(self.d, "enc"))
        self.assertEqual(r["stopped"], "secret.txt: encrypted"); self.assertEqual(r["files"], 0)

    def test_unsupported_compression_stops(self):
        for name, method, flags in (("deflate64.zip", 9, None), ("aes.zip", 99, 0x1)):
            p = os.path.join(self.d, name)
            with zipfile.ZipFile(p, "w") as z: z.writestr("x.bin", "hello")
            patch_zip(p, flags=flags, method=method)
            dest = os.path.join(self.d, name + ".out")
            r = archive.unpack(p, dest)                                # no exception may escape
            self.assertEqual(r["stopped"], "x.bin: unsupported compression", name)
            self.assertFalse(os.path.exists(os.path.join(dest, "x.bin")), name)

    # ---- fix round 1: duplicate members (P3) ------------------------------------------------------------------

    def test_duplicate_member_stops_and_keeps_the_first(self):
        p = os.path.join(self.d, "dup.zip")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)                  # zipfile warns about the duplicate name
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("a.txt", "first"); z.writestr("a.txt", "second")
        dest = os.path.join(self.d, "dup")
        r = archive.unpack(p, dest)
        self.assertEqual(r["stopped"], "a.txt: duplicate member"); self.assertEqual(r["files"], 1)
        with open(os.path.join(dest, "a.txt")) as f: self.assertEqual(f.read(), "first")

        q = os.path.join(self.d, "dup.tar")
        with tarfile.open(q, "w") as t:
            for data in (b"first", b"second"):
                i = tarfile.TarInfo("a.txt"); i.size = len(data); t.addfile(i, io.BytesIO(data))
        dest = os.path.join(self.d, "dupt")
        r = archive.unpack(q, dest)
        self.assertEqual(r["stopped"], "a.txt: duplicate member"); self.assertEqual(r["files"], 1)
        with open(os.path.join(dest, "a.txt")) as f: self.assertEqual(f.read(), "first")

    # ---- fix round 1: a corrupt tar header is never a silent end (P5) -----------------------------------------

    def test_corrupt_tar_header_after_a_member_stops(self):
        p = os.path.join(self.d, "corrupt.tar")
        with tarfile.open(p, "w") as t:
            for n, data in (("a", b"x" * 10), ("b", b"y" * 20)):
                i = tarfile.TarInfo(n); i.size = len(data); t.addfile(i, io.BytesIO(data))
        with open(p, "rb") as f:
            raw = bytearray(f.read())
        raw[1024] ^= 0x41                                             # break the second header's checksum
        with open(p, "wb") as f: f.write(bytes(raw))
        dest = os.path.join(self.d, "corrupt")
        r = archive.unpack(p, dest)
        self.assertEqual(r["stopped"], "broken archive"); self.assertEqual(r["files"], 1)
        self.assertTrue(os.path.isfile(os.path.join(dest, "a")))
        self.assertFalse(os.path.exists(os.path.join(dest, "b")))

    # ---- fix round 1: the output handle is closed on every path (P6) ------------------------------------------

    def test_output_handles_are_closed_on_every_path(self):
        ok = os.path.join(self.d, "ok.zip")
        with zipfile.ZipFile(ok, "w") as z: z.writestr("a.txt", "x")
        big = os.path.join(self.d, "big.zip")
        with zipfile.ZipFile(big, "w", zipfile.ZIP_STORED) as z: z.writestr("big.bin", bytes(3 << 20))
        enc = os.path.join(self.d, "h-enc.zip")
        with zipfile.ZipFile(enc, "w") as z: z.writestr("s.txt", "x")
        patch_zip(enc, flags=0x1)
        trunc = os.path.join(self.d, "trunc.zip")
        with open(trunc, "wb") as f: f.write(b"PK\x03\x04" + bytes(600))
        broken = os.path.join(self.d, "corrupt.tar")
        with tarfile.open(broken, "w") as t:
            for n, data in (("a", b"x" * 10), ("b", b"y" * 20)):
                i = tarfile.TarInfo(n); i.size = len(data); t.addfile(i, io.BytesIO(data))
        with open(broken, "rb") as f:
            raw = bytearray(f.read())
        raw[1024] ^= 0x41
        with open(broken, "wb") as f: f.write(bytes(raw))

        real_open = open
        opened = []
        def spy(*args, **kw):
            handle = real_open(*args, **kw)
            opened.append(handle)
            return handle

        cases = [(ok, "h-ok"), (big, "h-big"), (enc, "h-enc"), (trunc, "h-trun"), (broken, "h-broken")]
        with mock.patch("builtins.open", spy):
            for arc, dest in cases:
                archive.unpack(arc, os.path.join(self.d, dest), limits=dict(archive.LIMITS, member=1 << 20))
        self.assertTrue(opened)
        leaked = [h.name for h in opened if not h.closed]
        self.assertEqual(leaked, [])

    # ---- fix round 2: sparse members stop before they are written (Q1 / S2) -----------------------------------

    @unittest.skipUnless(GNU_TAR, "GNU tar is not installed")
    def test_sparse_tar_members_stop_at_once(self):
        src = os.path.join(self.d, "sparse-src")
        os.makedirs(src)
        for i in range(5):
            with open(os.path.join(src, "f%d" % i), "wb") as f:
                f.truncate(120 << 20)                       # a 120 MB hole, so the packed archive is a few hundred bytes
        for fmt in ("gnu", "pax"):
            arc = os.path.join(self.d, "sparse-%s.tar.gz" % fmt)
            subprocess.run([GNU_TAR, "--sparse", "--format=" + fmt, "-czf", arc, "-C", src,
                            "f0", "f1", "f2", "f3", "f4"], check=True)
            self.assertLess(os.path.getsize(arc), 1 << 20, fmt)
            dest = os.path.join(self.d, "sparse-out-" + fmt)
            r = archive.unpack(arc, dest)
            self.assertEqual(r["stopped"], "f0: sparse member", fmt)
            self.assertEqual(r["files"], 0, fmt)
            self.assertEqual(total_size(dest), 0, fmt)      # not one sparse byte reached disk

    # ---- fix round 2: a tar is streamed once, in order (Q4 / S1) ----------------------------------------------

    def test_many_small_members_unpack_quickly(self):
        arc = os.path.join(self.d, "many-members.tar.gz")
        # 16 KB members: big enough that the old per-member second open had to rewind the decompressor (the 8 KB
        # read buffer covered a 1 KB member, which is why the quadratic cost only showed on larger ones).
        blobs = [os.urandom(16 << 10) for _ in range(2000)]  # incompressible, so the ratio guard stays out of the way
        with tarfile.open(arc, "w:gz") as t:
            for i, blob in enumerate(blobs):
                info = tarfile.TarInfo("m%04d" % i)
                info.size = len(blob)
                t.addfile(info, io.BytesIO(blob))
        dest = os.path.join(self.d, "many-members")
        start = time.monotonic()
        r = archive.unpack(arc, dest)
        elapsed = time.monotonic() - start
        print("\n[Q4] 2000 x 16 KB members in a .tar.gz unpacked in %.3f s" % elapsed)
        self.assertIsNone(r["stopped"])
        self.assertEqual(r["files"], 2000)
        self.assertLess(elapsed, 10.0)

    # ---- fix round 2: no exception escapes and a bad name is named (Q2) ----------------------------------------

    def test_bad_utf8_zip_name_stops(self):
        p = os.path.join(self.d, "badname.zip")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("ab", "hello")
        patch_zip_name(p, b"\xff\xfe")                      # flag 0x800 set, but not valid UTF-8
        r = archive.unpack(p, os.path.join(self.d, "badname"))
        self.assertEqual(r["stopped"], "b'\\xff\\xfe': bad name encoding")
        self.assertEqual(r["files"], 0)

    def test_unexpected_errors_are_named_stops(self):
        p = os.path.join(self.d, "boom.zip")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("a.txt", "x")
        with mock.patch.object(archive, "_unpack_zip", side_effect=ValueError("boom")):
            r = archive.unpack(p, os.path.join(self.d, "boom"))
        self.assertEqual(r["stopped"], "unpack error: ValueError")

    # ---- fix round 2: a long or deep path and an OSError are named stops (Q3) ----------------------------------

    def test_long_and_deep_member_paths_stop(self):
        deep = "/".join(["c" * 200] * 25)                   # 5 KB over 25 parts, every part under 255 bytes
        p = os.path.join(self.d, "deep.tar")
        with tarfile.open(p, "w") as t:
            info = tarfile.TarInfo(deep)
            info.size = 0
            t.addfile(info)
        r = archive.unpack(p, os.path.join(self.d, "deep"))
        self.assertEqual(r["stopped"], "%s: path too long" % ("c" * 200))    # the reason echoes the cut name
        self.assertEqual(r["files"], 0)
        q = os.path.join(self.d, "deep.zip")
        with zipfile.ZipFile(q, "w") as z:
            z.writestr("a/" * 2100, "")                     # 2100 parts: os.makedirs would recurse
        r = archive.unpack(q, os.path.join(self.d, "deepzip"))
        self.assertTrue(r["stopped"].endswith(": path too long"), r["stopped"])
        self.assertEqual(r["files"], 0)

    def test_oserror_writing_a_member_is_a_named_stop(self):
        p = os.path.join(self.d, "oserror.zip")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("a.txt", "x")
        real_open = open
        def failing_open(path, mode="r", *args, **kw):
            if "w" in mode:
                raise OSError(36, "File name too long")
            return real_open(path, mode, *args, **kw)
        with mock.patch("builtins.open", failing_open):
            r = archive.unpack(p, os.path.join(self.d, "oserror"))
        self.assertEqual(r["stopped"], "a.txt: File name too long")
        self.assertEqual(r["files"], 0)

    # ---- fix round 2: the zip central directory is counted before any member is read (Q5) ---------------------

    def test_zip_central_directory_over_the_file_limit_stops_first(self):
        p = os.path.join(self.d, "central.zip")
        with zipfile.ZipFile(p, "w") as z:
            for i in range(5):
                z.writestr("f%d" % i, "")
        dest = os.path.join(self.d, "central")
        r = archive.unpack(p, dest, limits=dict(archive.LIMITS, files=3))
        self.assertEqual(r["stopped"], "more than 3 files")
        self.assertEqual(r["files"], 0)
        self.assertEqual(os.listdir(dest) if os.path.isdir(dest) else [], [])

    # ---- fix round 2: duplicates and "." are seen on the normalised path (Q6, Q7) ------------------------------

    def test_duplicate_detection_uses_the_normalised_path(self):
        p = os.path.join(self.d, "dupnorm.zip")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("d/a.txt", "first")
            z.writestr("d//a.txt", "second")                # "d//a.txt" normalises to "d/a.txt"
        dest = os.path.join(self.d, "dupnorm")
        r = archive.unpack(p, dest)
        self.assertEqual(r["stopped"], "d/a.txt: duplicate member")
        with open(os.path.join(dest, "d", "a.txt")) as f:
            self.assertEqual(f.read(), "first")

        q = os.path.join(self.d, "dupnorm.tar")
        with tarfile.open(q, "w") as t:
            for name, data in (("d/a.txt", b"first"), ("d//a.txt", b"second")):
                info = tarfile.TarInfo(name)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        dest = os.path.join(self.d, "dupnorm-tar")
        r = archive.unpack(q, dest)
        self.assertEqual(r["stopped"], "d/a.txt: duplicate member")
        with open(os.path.join(dest, "d", "a.txt")) as f:
            self.assertEqual(f.read(), "first")

    def test_dot_member_that_is_a_file_stops(self):
        p = os.path.join(self.d, "dotfile.tar")
        with tarfile.open(p, "w") as t:
            info = tarfile.TarInfo("./")
            info.size = 5
            t.addfile(info, io.BytesIO(b"hello"))
        r = archive.unpack(p, os.path.join(self.d, "dotfile"))
        self.assertEqual(r["stopped"], "./: path has .")
        self.assertEqual(r["files"], 0)

        q = os.path.join(self.d, "dotfile.zip")
        with zipfile.ZipFile(q, "w") as z:
            z.writestr(".", "hello")
        r = archive.unpack(q, os.path.join(self.d, "dotfile-zip"))
        self.assertEqual(r["stopped"], ".: path has .")
        self.assertEqual(r["files"], 0)

        d = os.path.join(self.d, "dotdir.tar")
        with tarfile.open(d, "w") as t:
            t.add(FIXTURE_ROOT, arcname=".")                # the "." *directory* is still skipped
        r = archive.unpack(d, os.path.join(self.d, "dotdir"))
        self.assertIsNone(r["stopped"])

    # ---- fix round 2: `bytes` counts the member data written, not the headers (Q8) -----------------------------

    def test_bytes_counts_written_member_data_only(self):
        p = os.path.join(self.d, "sizes.tar")
        with tarfile.open(p, "w") as t:
            for name, size in (("a", 10), ("b", 3000)):
                info = tarfile.TarInfo(name)
                info.size = size
                t.addfile(info, io.BytesIO(bytes(size)))
        dest = os.path.join(self.d, "sizes")
        r = archive.unpack(p, dest)
        self.assertEqual((r["files"], r["bytes"], r["stopped"]), (2, 3010, None))
        self.assertEqual(os.path.getsize(os.path.join(dest, "a")), 10)
        self.assertEqual(os.path.getsize(os.path.join(dest, "b")), 3000)

    # ---- fix round 3: the nested peek reads at most 64 KB and never re-reads (T1 / U1) ------------------------

    def test_empty_xz_stream_chain_member_is_bounded(self):
        # The review's archive: a .tar.gz holding `ok.txt` and a 1 GB member made of 32-byte empty xz streams.
        # The old look-ahead decompressed until 512 bytes came out and buffered the whole member (30.6 s, 2.07 GB
        # RSS); the bounded peek reads at most 64 KB and writes the member as an ordinary file under the guards.
        arc = os.path.join(self.d, "xzchain.tar.gz")
        block = lzma.compress(b"")                       # one whole empty xz stream, 32 bytes
        size = 1000 << 20
        with tarfile.open(arc, "w:gz") as t:             # default level: the packed archive is ~2.5 MB
            i = tarfile.TarInfo("ok.txt")
            i.size = 5
            t.addfile(i, io.BytesIO(b"hello"))
            e = tarfile.TarInfo("evil.gz")
            e.size = size
            t.addfile(e, RepeatStream(block, size))
        self.assertLess(os.path.getsize(arc), 8 << 20)
        dest = os.path.join(self.d, "xzchain")
        tracemalloc.start()
        start = time.monotonic()
        try:
            r = archive.unpack(arc, dest)
            elapsed = time.monotonic() - start
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        print("\n[U1] empty-xz chain member unpacked in %.3f s, peak %d bytes" % (elapsed, peak))
        self.assertNotIn("nested", r["stopped"] or "")
        self.assertLess(elapsed, 2.0)
        self.assertLess(peak, 16 << 20)
        self.assertEqual(r["files"], 1)                  # ok.txt stays; the stopped member is removed
        self.assertTrue(os.path.isfile(os.path.join(dest, "ok.txt")))
        self.assertFalse(os.path.exists(os.path.join(dest, "evil.gz")))

    # ---- fix round 3: a .tar.gz / .tar.xz member inside a tar is nested again (T1 / U2) -----------------------

    def test_tar_gz_member_inside_every_outer_kind_is_nested(self):
        for label, size in (("small", 1), ("big", 100 << 10)):
            inner = inner_tar("tar.gz", size)
            for outer, mode in (("tar", "w"), ("tar.gz", "w:gz"), ("tar.xz", "w:xz")):
                arc = outer_tar(os.path.join(self.d, "o-%s-%s" % (label, outer)),
                                [("inner.tar.gz", inner)], mode)
                dest = os.path.join(self.d, "o-%s-%s-out" % (label, outer))
                r = archive.unpack(arc, dest)
                self.assertEqual(r["stopped"], "nested archive inner.tar.gz (listed, not opened)", (label, outer))
                self.assertEqual(r["files"], 0, (label, outer))
                self.assertFalse(os.path.exists(os.path.join(dest, "inner.tar.gz")), (label, outer))

    def test_tar_xz_member_inside_a_tar_is_nested(self):
        inner = inner_tar("tar.xz", 1)
        arc = outer_tar(os.path.join(self.d, "xzinner.tar"), [("inner.tar.xz", inner)], "w")
        r = archive.unpack(arc, os.path.join(self.d, "xzinner-out"))
        self.assertEqual(r["stopped"], "nested archive inner.tar.xz (listed, not opened)")
        self.assertEqual(r["files"], 0)

    def test_pcf_gz_member_inside_a_tar_is_written_as_a_plain_file(self):
        data = gzip.compress(b"\x01fcp" + bytes(200))    # a .pcf.gz: gzip, but no archive inside
        arc = outer_tar(os.path.join(self.d, "pcf.tar"), [("18x18ko.pcf.gz", data)], "w")
        dest = os.path.join(self.d, "pcf-out")
        r = archive.unpack(arc, dest)
        self.assertIsNone(r["stopped"])
        self.assertTrue(os.path.isfile(os.path.join(dest, "18x18ko.pcf.gz")))
        self.assertEqual(r["bytes"], len(data))

    def test_sevenzip_and_rar_members_are_nested(self):
        for label, magic in (("7z", b"7z\xbc\xaf\x27\x1c"), ("rar", b"Rar!\x1a\x07")):
            data = magic + bytes(600)
            arc = outer_tar(os.path.join(self.d, label + ".tar"), [("inner." + label, data)], "w")
            r = archive.unpack(arc, os.path.join(self.d, label + "-out"))
            self.assertEqual(r["stopped"], "nested archive inner.%s (listed, not opened)" % label, label)
            self.assertEqual(r["files"], 0, label)

    # ---- fix round 3: the zip look-ahead is bounded (T1 / U3) -------------------------------------------------

    def test_endless_gzip_name_member_in_a_zip_is_bounded(self):
        # The review's 102 KB zip: a deflated member that is a gzip header with FNAME and no NUL, followed by
        # 100 MB of "A". The old look-ahead read the name byte by byte through all of it (19.0 s).
        p = os.path.join(self.d, "fname.zip")
        header = b"\x1f\x8b\x08\x08" + bytes(4) + b"\x00\x03"      # gzip, FLG=FNAME, no name terminator
        chunk = b"A" * (1 << 20)
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            with z.open("evil.gz", "w") as m:
                m.write(header)
                for _ in range(100):
                    m.write(chunk)
        self.assertLess(os.path.getsize(p), 1 << 20)
        dest = os.path.join(self.d, "fname")
        start = time.monotonic()
        r = archive.unpack(p, dest)
        elapsed = time.monotonic() - start
        print("\n[U3] endless gzip FNAME member unpacked in %.3f s" % elapsed)
        self.assertNotIn("nested", r["stopped"] or "")
        self.assertLess(elapsed, 2.0)

    def test_empty_gzip_chain_member_in_a_zip_is_bounded(self):
        # The review's 257 KB zip: a deflated member that is a chain of empty gzip members (100 MB decompressed).
        # The old look-ahead walked every member (24.9 s).
        p = os.path.join(self.d, "chain.zip")
        unit = gzip.compress(b"")
        big = unit * ((1 << 20) // len(unit))
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            with z.open("evil.gz", "w") as m:
                for _ in range(100):
                    m.write(big)
        self.assertLess(os.path.getsize(p), 1 << 20)
        dest = os.path.join(self.d, "chain")
        start = time.monotonic()
        r = archive.unpack(p, dest)
        elapsed = time.monotonic() - start
        print("\n[U3] empty gzip chain member unpacked in %.3f s" % elapsed)
        self.assertNotIn("nested", r["stopped"] or "")
        self.assertLess(elapsed, 2.0)

    # ---- fix round 3: `bytes` counts only data that stays on disk (U4) ---------------------------------------

    def test_bytes_counts_only_data_that_stays_on_disk(self):
        p = os.path.join(self.d, "part.zip")
        with zipfile.ZipFile(p, "w", zipfile.ZIP_STORED) as z:
            z.writestr("a.txt", "hello")
            z.writestr("big.bin", bytes(3 << 20))
        dest = os.path.join(self.d, "part-zip")
        r = archive.unpack(p, dest, limits=dict(archive.LIMITS, member=1 << 20))
        self.assertTrue(r["stopped"].startswith("big.bin: member over"), r["stopped"])
        self.assertEqual(r["bytes"], 5)                  # the removed 1 MB partial is not counted
        self.assertEqual(r["bytes"], total_size(dest))

        q = os.path.join(self.d, "part.tar.gz")
        with tarfile.open(q, "w:gz") as t:               # incompressible, so the member guard fires before ratio
            for name, data in (("a.txt", b"hello"), ("big.bin", os.urandom(3 << 20))):
                i = tarfile.TarInfo(name)
                i.size = len(data)
                t.addfile(i, io.BytesIO(data))
        dest = os.path.join(self.d, "part-tar")
        r = archive.unpack(q, dest, limits=dict(archive.LIMITS, member=1 << 20))
        self.assertTrue(r["stopped"].startswith("big.bin: member over"), r["stopped"])
        self.assertEqual(r["bytes"], 5)
        self.assertEqual(r["bytes"], total_size(dest))

    # ---- fix round 3: every stop reason truncates the name (U5) ----------------------------------------------

    def test_bad_name_encoding_reason_is_truncated(self):
        p = os.path.join(self.d, "longname.zip")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("x" * 60000, "hello")
        patch_zip_name(p, b"\xff" * 60000)               # flag 0x800 set, but not valid UTF-8
        r = archive.unpack(p, os.path.join(self.d, "longname"))
        self.assertEqual(r["stopped"], "b'" + "\\xff" * 200 + "': bad name encoding")
        self.assertLess(len(r["stopped"]), 1000)


if __name__ == "__main__":
    unittest.main()
