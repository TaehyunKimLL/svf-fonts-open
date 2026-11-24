#!/usr/bin/env python3
"""oscompat (t_9b8f56f0): the POSIX forms are the calls the maker made before; the Windows forms keep each check.

The cross-platform cases run everywhere; the Windows cases (junctions, held directories, device names, Job Objects)
run on Windows only and are skipped elsewhere with that reason.
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import errno
import shutil
import subprocess
import tempfile
import time
import unittest

import oscompat
import sources
import toolrun
import zipout

WIN = oscompat.WINDOWS


def _junction(target, link):
    """A directory junction (Windows; no privilege needed, unlike a symlink)."""
    import _winapi
    _winapi.CreateJunction(target, link)


def _wait(pred, seconds=10.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return pred()


class OsCompatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-oscompat-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_lock_is_exclusive_across_descriptors(self):
        path = os.path.join(self.tmp, "x.lock")
        a = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        b = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, a)
        self.addCleanup(os.close, b)
        oscompat.lock(a, blocking=False)
        with self.assertRaises(OSError):
            oscompat.lock(b, blocking=False)
        oscompat.unlock(a)
        oscompat.lock(b, blocking=False)
        oscompat.unlock(b)

    def test_open_nofollow_reads_a_regular_file(self):
        path = os.path.join(self.tmp, "f")
        with open(path, "wb") as f:
            f.write(b"abc")
        fd = oscompat.open_nofollow(path, os.O_RDONLY)
        with os.fdopen(fd, "rb") as f:
            self.assertEqual(f.read(), b"abc")

    def test_open_excl_refuses_an_existing_name(self):
        path = os.path.join(self.tmp, "f")
        os.close(oscompat.open_nofollow(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        with self.assertRaises(FileExistsError):
            oscompat.open_nofollow(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)

    def test_group_kill_reaches_a_grandchild(self):
        pidfile = os.path.join(self.tmp, "grandchild")
        code = ("import subprocess, sys, time\n"
                "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                "open(sys.argv[1], 'w').write(str(g.pid))\n"
                "time.sleep(60)\n")
        proc = oscompat.popen_group([sys.executable, "-c", code, pidfile], stdin=subprocess.DEVNULL)
        self.addCleanup(proc.wait)
        self.assertTrue(_wait(lambda: os.path.exists(pidfile) and open(pidfile).read().strip()))
        with open(pidfile) as f:
            grandchild = int(f.read())
        self.assertTrue(toolrun.alive(grandchild))
        oscompat.signal_group(proc, oscompat.SIGKILL)
        proc.wait(10)
        self.assertTrue(_wait(lambda: not toolrun.alive(grandchild)), "the grandchild outlived the group kill")

    def test_alive_and_start_time(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.assertTrue(toolrun.alive(proc.pid))
            import toolreg
            first = toolreg.start_time(proc.pid)
            if sys.platform.startswith("linux") or WIN:
                self.assertTrue(first)
                self.assertEqual(toolreg.start_time(proc.pid), first)
        finally:
            proc.kill()
            proc.wait()
        self.assertTrue(_wait(lambda: not toolrun.alive(proc.pid)))

    def test_unsafe_names(self):
        for name in ("CON", "con.svf", "NUL.TXT", "COM1.SVF", "LPT9", "AUX.ttf", "CONIN$", "a.", "a ", "a:b", "a?b",
                     "a\x01b", "", ".."):
            self.assertTrue(oscompat.windows_unsafe_name(name), name)
        for name in ("CONSOLE.SVF", "COM10.SVF", "NEODG16.SVF", "KSC16.ttf", "build-0123456789ab", "LICENCE.TXT"):
            self.assertFalse(oscompat.windows_unsafe_name(name), name)


@unittest.skipUnless(WIN, "Windows only: junctions, held directories, device names on disk")
class WindowsLinksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="svf-oscompat-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.real = os.path.join(self.tmp, "real")
        os.mkdir(self.real)
        with open(os.path.join(self.real, "f.ttf"), "wb") as f:
            f.write(b"x" * 10)
        self.link = os.path.join(self.tmp, "link")
        _junction(self.real, self.link)

    def test_a_junction_is_a_link(self):
        self.assertFalse(os.path.islink(self.link))           # the reason oscompat.islink exists
        self.assertTrue(oscompat.islink(self.link))
        self.assertTrue(oscompat.is_link(os.lstat(self.link)))
        self.assertFalse(oscompat.islink(self.real))

    def test_open_nofollow_refuses_through_a_junction_name(self):
        with self.assertRaises(OSError) as cm:
            oscompat.open_nofollow(self.link, os.O_RDONLY)
        self.assertIn(cm.exception.errno, (errno.ELOOP, errno.EACCES))

    def test_hold_dir_refuses_a_junction_and_pins_the_folder(self):
        with self.assertRaises(OSError) as cm:
            oscompat.hold_dir(self.link)
        self.assertEqual(cm.exception.errno, errno.ELOOP)
        inner = os.path.join(self.real, "inner")
        os.mkdir(inner)
        fd = oscompat.hold_dir(inner)
        try:
            with self.assertRaises(OSError):                  # the held folder cannot be renamed ...
                os.rename(inner, inner + "-moved")
            with self.assertRaises(OSError):                  # ... nor a folder above it (NTFS)
                os.rename(self.real, self.real + "-moved")
            with self.assertRaises(OSError):
                os.rmdir(inner)
        finally:
            os.close(fd)
        os.rename(inner, inner + "-moved")                    # free again once the handle is closed

    def test_sources_walk_refuses_a_junctioned_folder(self):
        root = os.path.join(self.tmp, "root")
        os.mkdir(root)
        _junction(self.real, os.path.join(root, "sub"))
        files, refused = sources.Sources("local", [root]).walk()
        self.assertEqual(files, [])
        self.assertEqual(refused, [(0, "sub", "symlink, skipped")])

    def test_check_path_refusals(self):
        with self.assertRaises(sources.PathRefused) as cm:
            sources.check_path(self.link, want="output", data_root=None, allowed=None)
        self.assertEqual(cm.exception.reason, "the path is a symlink")
        drive_root = os.path.splitdrive(self.tmp)[0] + "\\"
        with self.assertRaises(sources.PathRefused) as cm:
            sources.check_path(drive_root, want="output", data_root=None, allowed=None)
        self.assertEqual(cm.exception.reason, "/ cannot be chosen")
        for bad in ("\\\\.\\PhysicalDrive0", "\\\\?\\" + self.real, "\\no-drive"):
            with self.assertRaises(sources.PathRefused):
                sources.check_path(bad, want="source", data_root=None, allowed=None)
        with self.assertRaises(sources.PathRefused):
            sources.check_path(os.path.join(self.real, "f.ttf") + ":stream", want="source", data_root=None, allowed=None)
        real, kind = sources.check_path(self.real.lower(), want="source", data_root=None, allowed=None)
        self.assertEqual((real, kind), (self.real, "dir"))    # the on-disk spelling, whatever case was picked

    def test_abs_of_refuses_drives_and_streams(self):
        src = sources.Sources("local", [self.real])
        self.assertTrue(src.abs_of(0, "f.ttf").endswith("f.ttf"))
        for rel in ("C:f.ttf", "C:\\f.ttf", "\\f.ttf", "f.ttf:ads", "f.ttf::$DATA"):
            with self.assertRaises(ValueError):
                src.abs_of(0, rel)

    def test_write_tree_refuses_a_junction_below_the_output(self):
        out = os.path.join(self.tmp, "out")
        os.mkdir(out)
        os.mkdir(os.path.join(out, "svf"))
        _junction(self.real, os.path.join(out, "svf", "dos"))
        job = {"id": "0123456789ab"}
        st = os.stat(out)
        with self.assertRaises(zipout.TreeRefused):
            zipout.write_tree(job, {"svf/dos/NEODG16.SVF": b"x"}, [], out, [st.st_dev, st.st_ino], {}, lambda r, d: None)
        self.assertEqual(os.listdir(self.real), ["f.ttf"])

    def test_write_tree_refuses_a_device_name(self):
        out = os.path.join(self.tmp, "out")
        os.mkdir(out)
        st = os.stat(out)
        with self.assertRaises(zipout.TreeRefused):
            zipout.write_tree({"id": "0123456789ab"}, {"svf/dos/CON.SVF": b"x"}, [], out, [st.st_dev, st.st_ino], {},
                              lambda r, d: None)

    def test_write_tree_lands_and_never_replaces(self):
        out = os.path.join(self.tmp, "out")
        os.mkdir(out)
        st = os.stat(out)
        landed = zipout.write_tree({"id": "0123456789ab"}, {"svf/dos/NEODG16.SVF": b"one"}, [("BUILD.md", b"b")], out,
                                   [st.st_dev, st.st_ino], {}, lambda r, d: None)
        self.assertEqual(sorted(landed), ["build-0123456789ab/BUILD.md", "svf/dos/NEODG16.SVF"])
        with open(os.path.join(out, "svf", "dos", "NEODG16.SVF"), "rb") as f:
            self.assertEqual(f.read(), b"one")
        with self.assertRaises(zipout.NameClash):
            zipout.write_tree({"id": "ba9876543210"}, {"svf/dos/NEODG16.SVF": b"two"}, [], out, [st.st_dev, st.st_ino], {},
                              lambda r, d: None)
        with open(os.path.join(out, "svf", "dos", "NEODG16.SVF"), "rb") as f:
            self.assertEqual(f.read(), b"one")
        self.assertEqual(sorted(os.listdir(os.path.join(out, "svf", "dos"))), ["NEODG16.SVF"])   # no temp file left


if __name__ == "__main__":
    unittest.main()
