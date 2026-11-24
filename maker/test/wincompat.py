#!/usr/bin/env python3
"""Test helpers for the Windows run of the maker suite (t_9b8f56f0); on POSIX every helper is the plain call.

- `posix_only(reason)`: a skip on Windows for a test that is POSIX by nature (permission bits, signals, FIFOs, a
  `#!/bin/sh` stub, /proc, zombies); the reason names what Windows lacks, so the run's skip list says why.
- `SlashEqual`: a TestCase mixin whose `assertEqual` treats `\\` and `/` as one path separator on Windows. The routes
  build argv paths with `os.path.join` (which writes `\\` there) and with "/"-joined relative paths (which stay "/");
  Windows reads both, so an argv-shape test compares them as one separator. POSIX: the plain `assertEqual`.
- `kill_group(proc)` / `popen_group(argv, ...)`: a test's own process tree (`oscompat`), killed whatever its state.
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
if MAKER_DIR not in sys.path:
    sys.path.insert(0, MAKER_DIR)

import unittest

import oscompat

WIN = oscompat.WINDOWS


def posix_only(reason):
    """Skip the test (or class) on Windows: @p reason says what is POSIX about it."""
    return unittest.skipIf(WIN, "POSIX only: " + reason)


def slashes(value):
    """@p value with every `\\` of every string in it made `/` (lists, tuples, dicts and sets walked)."""
    if isinstance(value, str):
        return value.replace("\\", "/")
    if isinstance(value, list):
        return [slashes(v) for v in value]
    if isinstance(value, tuple):
        return tuple(slashes(v) for v in value)
    if isinstance(value, dict):
        return {slashes(k): slashes(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return type(value)(slashes(v) for v in value)
    return value


class SlashEqual:
    """Mixin: on Windows `assertEqual`, `assertIn` and `assertNotIn` compare with `\\` and `/` as one separator."""

    if WIN:
        def assertEqual(self, first, second, msg=None):
            super().assertEqual(slashes(first), slashes(second), msg)

        def assertIn(self, member, container, msg=None):
            super().assertIn(slashes(member), slashes(container), msg)

        def assertNotIn(self, member, container, msg=None):
            super().assertNotIn(slashes(member), slashes(container), msg)


def popen_group(argv, **kwargs):
    return oscompat.popen_group(argv, **kwargs)


def kill_group(proc_or_pid):
    """Kill a test's own process tree: a Popen from `popen_group` (both platforms) or, on POSIX, a group id."""
    try:
        if isinstance(proc_or_pid, int):
            if WIN:
                oscompat.kill_registered(proc_or_pid)
            else:
                os.killpg(proc_or_pid, oscompat.SIGKILL)
        else:
            oscompat.signal_group(proc_or_pid, oscompat.SIGKILL)
    except OSError:
        pass


def interpreter_stub(path, sh_body, py_body):
    """An executable stand-in for an interpreter at @p path; returns the path to run. POSIX: `#!/bin/sh` + @p sh_body
    (the test's own shell body, unchanged). Windows: `<path>.bat` running this Python on `<path>.py`, which holds
    @p py_body (sys.argv[1:] are the arguments the batch file was given)."""
    if not WIN:
        with open(path, "w") as f:
            f.write("#!/bin/sh\n%s\n" % sh_body)
        os.chmod(path, 0o755)
        return path
    with open(path + ".py", "w", encoding="utf-8") as f:
        f.write(py_body + "\n")
    with open(path + ".bat", "w") as f:
        f.write('@"%s" "%s.py" %%*\n' % (sys.executable, path))
    return path + ".bat"


# The glyphs whose pixels Pillow's Windows wheel draws differently from the Linux Pillow the shipped faces were made with
# (measured on GitHub Actions windows-latest, raqm on through FriBiDi: GowunBatang-Bold 17 px 2 bpp, U+2116 only). On
# Windows a face made from the same font is then not the shipped face's bytes; every other glyph and the glyph set must be.
WINDOWS_RENDER_DIFFERS = {"GBATB17.SVF": frozenset({0x2116})}


def face_difference(made, shipped):
    """`(only_made, only_shipped, differing)`: the code points of two SVF faces (bytes) that are not the same glyph."""
    import jamoset
    a, b = jamoset.parse_svfn(made), jamoset.parse_svfn(shipped)
    differ = {cp for cp in set(a.glyphs) & set(b.glyphs)
              if a.glyphs[cp] != b.glyphs[cp] or a.metrics.get(cp) != b.metrics.get(cp)}
    return set(a.glyphs) - set(b.glyphs), set(b.glyphs) - set(a.glyphs), differ


def render_matches(made, shipped, name):
    """True when @p made is @p shipped byte for byte, or (Windows) differs from it only in the pinned glyphs of
    `WINDOWS_RENDER_DIFFERS[name]` (same glyph set, every other glyph and metric equal)."""
    if made == shipped:
        return True
    if not WIN or name not in WINDOWS_RENDER_DIFFERS:
        return False
    only_made, only_shipped, differ = face_difference(made, shipped)
    return not only_made and not only_shipped and differ <= WINDOWS_RENDER_DIFFERS[name]
