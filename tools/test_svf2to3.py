#!/usr/bin/env python3
"""Tests for tools/svf2to3.py: v2 -> v3 conversion, profile re-layout, the --check comparison and --tree."""
import io
import os
import signal
import subprocess
import struct
import sys
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jamoset  # noqa: E402
import svf2to3  # noqa: E402
import svfline  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata", "v2")
FIXTURES = ("NEODG16A.SVF", "PAPLG16.SVF")
PROFILES = tuple(jamoset.PROFILES)


def fixture(name):
    with open(os.path.join(DATA, name), "rb") as fh:
        return fh.read()


def run(argv):
    out = io.StringIO()
    with redirect_stdout(out):
        st = svf2to3.main(argv)
    return st, out.getvalue()


def expected_count(data):
    f = svf2to3._parse_v2(data)
    cps = set(f.glyphs)
    if f.jset:
        cps |= set(range(0xAC00, 0xD7A4)) | set(range(0x3131, 0x3164))
    return len(cps)


SYNTH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "svf_synth.py")
SYNTH_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "svf", "dos", "NEODG16G.SVF")


class JmapRegion(unittest.TestCase):
    """A version 3 (JMAP) region is copied verbatim; --check composes through svfline."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf2to3-jmap-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def synth(self, *args):
        out = os.path.join(self.tmp, "in.svf")
        r = subprocess.run([sys.executable, SYNTH] + list(args) + ["--from", SYNTH_BASE, out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return out

    def test_verbatim_region_and_check(self):
        for variant in ("sparse3", "hybrid2", "dense4"):
            for profile in ("mcu-strict", "default", "dos"):
                with self.subTest(variant=variant, profile=profile):
                    src = self.synth("--jmap-variant", variant)
                    dst = os.path.join(self.tmp, "out.svf")
                    st, out = run([src, dst, "--profile", profile, "--check"])
                    self.assertEqual(st, 0, out)
                    with open(src, "rb") as fh:
                        a = jamoset.parse_svfn(fh.read())
                    with open(dst, "rb") as fh:
                        b = jamoset.parse_svfn(fh.read())
                    self.assertIsNotNone(a.jset)
                    self.assertEqual(b.jset, a.jset)
                    self.assertIn(" jset=3 ", out)
                    self.assertNotIn("unchecked", out)

    def test_jset_version_applies_to_nothing(self):
        src = self.synth("--jmap-variant", "hybrid1")
        with open(src, "rb") as fh:
            a = jamoset.parse_svfn(fh.read())
        for v in ("1", "2", "auto"):
            with self.subTest(v=v):
                dst = os.path.join(self.tmp, "out%s.svf" % v)
                err = io.StringIO()
                with mock.patch("sys.stderr", err):
                    st, out = run([src, dst, "--jset-version", v, "--check"])
                self.assertEqual(st, 0, err.getvalue())
                self.assertIn("applies to nothing", err.getvalue())
                with open(src, "rb") as fh:
                    _, info = svf2to3.convert_info(fh.read(), "default", jset_version=int(v) if v != "auto" else v)
                self.assertEqual(info["version"], 3)
                self.assertEqual(info["version_ignored"], v != "1")
                with open(dst, "rb") as fh:
                    self.assertEqual(jamoset.parse_svfn(fh.read()).jset, a.jset)

    def test_convert_info_reports_version_3(self):
        with open(self.synth("--jmap-variant", "sparse3"), "rb") as fh:
            data = fh.read()
        out, info = svf2to3.convert_info(data, "default", jset_version=2)
        self.assertEqual(info["version"], 3)
        self.assertEqual(jamoset.parse_svfn(out).jset, jamoset.parse_svfn(data).jset)
        self.assertEqual(svf2to3.jset_version(jamoset.parse_svfn(out).jset), 3)

    def test_tree(self):
        os.makedirs(os.path.join(self.tmp, "src"))
        shutil.copy(self.synth("--jmap-variant", "hybrid2"), os.path.join(self.tmp, "src", "A.SVF"))
        st, out = run([os.path.join(self.tmp, "src"), os.path.join(self.tmp, "dst"), "--tree", "--check"])
        self.assertEqual(st, 0, out)
        self.assertIn("failed=0", out)
        self.assertRegex(out, r" v3_faces=1 v3_jset=[1-9]\d* v1_faces=0 v1_jset=0 v2_faces=0 v2_jset=0 failed=0\n")


class ListFace(unittest.TestCase):
    """A version 3 LIST face (flag 0x08): svfline reads it, svf2to3 copies the region verbatim."""
    setUp, tearDown, synth = JmapRegion.setUp, JmapRegion.tearDown, JmapRegion.synth

    def test_svfline_composes_a_listed_syllable_and_not_an_unlisted_one(self):
        with open(self.synth("--jmap-variant", "list1"), "rb") as fh:
            f = svfline.Face(fh.read())
        jm = f.tables
        self.assertIsInstance(jm, jamoset.Jmap)
        self.assertTrue(jm.list_mode)
        s = sorted(jm.entries)[0]
        self.assertTrue(f.composed(0xAC00 + s))
        self.assertEqual(f.cell(0xAC00 + s), jamoset.compose(f, jm, 0xAC00 + s))
        # not the fallback's answer: a reader that ignored the entries would draw the fallback's cell
        self.assertNotEqual(jm.pieces(0xAC00 + s), jamoset.pieces_of(jm.fallback, 0xAC00 + s))
        self.assertNotEqual(f.cell(0xAC00 + s), jamoset.compose(f, jm.fallback, 0xAC00 + s))
        with open(self.synth("--jmap-variant", "list_nofb"), "rb") as fh:
            g = svfline.Face(fh.read())
        self.assertTrue(g.tables.list_mode)
        miss = next(s for s in range(11172) if s not in g.tables.entries)
        self.assertFalse(g.composed(0xAC00 + miss))      # PR-5: no fallback, an unlisted syllable is not composed
        self.assertFalse(g.has(0xAC00 + miss))

    def test_list_region_verbatim_check_and_line(self):
        for profile in ("mcu-strict", "default", "dos"):
            with self.subTest(profile=profile):
                src = self.synth("--jmap-variant", "list2")
                dst = os.path.join(self.tmp, "out.svf")
                st, out = run([src, dst, "--profile", profile, "--check"])
                self.assertEqual(st, 0, out)
                with open(src, "rb") as fh:
                    a = jamoset.parse_svfn(fh.read())
                with open(dst, "rb") as fh:
                    b = jamoset.parse_svfn(fh.read())
                self.assertEqual(b.jset, a.jset)
                jm = jamoset.unpack(b.jset)
                s = sorted(jm.entries)[0]       # the output face draws the listed cell, not the fallback's
                g = svfline.Face(open(dst, "rb").read())
                self.assertNotEqual(g.cell(0xAC00 + s), jamoset.compose(g, jm.fallback, 0xAC00 + s))
                self.assertIn(" jset=3 ", out)
                self.assertIn(" list=1", out)
                self.assertNotIn("unchecked", out)

    def test_list_mode_twin_of_the_big_fallback_case(self):
        t = jamoset.Tables(13, 12, 32, 24, 16)
        t.lead_class = [L % 13 for L in range(19)]
        t.tail_class = [0] + [1 + (T - 1) % 11 for T in range(1, 28)]
        n = 13 * 21 * 12
        t.init_set, t.med_set, t.fin_set = [c % 32 for c in range(n)], [c % 24 for c in range(n)], [c % 16 for c in range(n)]
        t.init_piece = list(range(32 * 19))
        t.med_piece = list(range(32 * 19, 32 * 19 + 24 * 21))
        t.fin_piece = list(range(32 * 19 + 24 * 21, 32 * 19 + 24 * 21 + 16 * 27))
        jm = jamoset.Jmap(0, 0, 0, 0, list_mode=True)
        jm.entries = {0: (1, 1, 0)}
        jm.fallback, jm.fallback_version = t, 1
        jm.fallback_block = jamoset.pack_fallback(t, 1, big=True)
        glyphs = [(jamoset.PIECE_BASE + p, bytes([1]) * 16, 8, 0, 8)
                  for p in range(max(t.init_piece + t.med_piece + t.fin_piece) + 1)]
        face = jamoset.write_svfn(8, 16, 14, glyphs, jamoset.pack_jmap(jm, jm.fallback_block))
        with self.assertRaisesRegex(ValueError, "--jset-big"):
            svf2to3.convert(face, "default")
        out = svf2to3.convert(face, "default", jset_big=True)
        self.assertEqual(block(out), block(face))


class Svf2To3Test(unittest.TestCase):
    def test_v2_fixture_converts_identically(self):
        for name in FIXTURES:
            v2 = fixture(name)
            self.assertEqual(struct.unpack_from("<H", v2, 4)[0], 2)
            for p in PROFILES:
                with self.subTest(name=name, profile=p):
                    v3 = svf2to3.convert(v2, p)
                    self.assertEqual(struct.unpack_from("<H", v3, 4)[0], 3)
                    self.assertEqual(svf2to3.check(v2, v3), expected_count(v2))

    def test_v3_relayout_identically(self):
        for name in FIXTURES:
            v2 = fixture(name)
            a = svf2to3.convert(v2, "default")
            b = svf2to3.convert(a, "dos")
            c = svf2to3.convert(b, "full")
            for out in (a, b, c):
                svf2to3.check(v2, out)
            self.assertEqual(jamoset.parse_svfn(b).layout, (0, 0, 0, False))
            self.assertEqual(jamoset.parse_svfn(c).layout, (2, 0, 2, True))

    def test_readers_refuse_v2(self):
        """Since v3 only jamoset.parse_svfn and svfline.Face refuse a v2 file (and versions 1 and 4) naming the converter;
        the private _parse_v2 here is the one v2 reader."""
        v2 = fixture("PAPLG16.SVF")
        for version in (1, 2, 4):
            data = bytearray(v2)
            struct.pack_into("<H", data, 4, version)
            for read in (jamoset.parse_svfn, svfline.Face):
                with self.subTest(version=version, reader=read.__name__):
                    with self.assertRaisesRegex(ValueError, "SVFN version %d: convert with tools/svf2to3.py" % version):
                        read(bytes(data))
        self.assertEqual(svf2to3._parse_v2(v2).count, struct.unpack_from("<H", v2, 12)[0])

    def test_check_catches_a_flipped_bit(self):
        v2 = fixture("PAPLG16.SVF")
        v3 = bytearray(svf2to3.convert(v2, "dos"))
        (_, _, _, _, _, _, _, count, _, _, _, _, _, _, _, data_off, _, cmap_off, _, _, tab_off) = \
            struct.unpack_from(jamoset.HEADER3, v3)
        offs = struct.unpack_from("<%dH" % (count + 1), v3, tab_off)   # dos: u16 in units of 1
        cp_of = {i: cp for cp, i in (struct.unpack_from("<II", v3, cmap_off + 8 * k) for k in range(count))}
        for i in range(count):
            rec = data_off + offs[i]
            if v3[rec + 2] and v3[rec + 3] and cp_of[i] < 0xF0000:
                break
        else:
            self.fail("no non-blank glyph")
        v3[rec + 4] ^= 0x80        # first row byte of the ink box (dos: no phase bytes)
        with self.assertRaisesRegex(AssertionError, "U\\+%04X" % cp_of[i]):
            svf2to3.check(v2, bytes(v3))

    def test_tree_totals(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "src"), os.path.join(d, "dst")
            os.makedirs(os.path.join(src, "sub"))
            total = 0
            for i, name in enumerate(FIXTURES):
                data = fixture(name)
                total += len(data)
                with open(os.path.join(src, "sub" if i else ".", name.lower() if i else name), "wb") as fh:
                    fh.write(data)
            with open(os.path.join(src, "note.txt"), "w") as fh:
                fh.write("not a face")
            st, text = run(["--tree", src, dst, "--check"])
            self.assertEqual(st, 0, text)
            last = text.strip().splitlines()[-1]
            self.assertTrue(last.startswith("total faces=2 in=%d " % total), last)
            self.assertTrue(last.endswith(" failed=0"), last)
            self.assertTrue(os.path.exists(os.path.join(dst, "NEODG16A.SVF")))
            self.assertTrue(os.path.exists(os.path.join(dst, "sub", "paplg16.svf")))
            self.assertFalse(os.path.exists(os.path.join(dst, "note.txt")))
            self.assertEqual([n for n in os.listdir(dst) if n.endswith(".tmp")], [])

    def test_refuses_garbage(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "in.SVF"), os.path.join(d, "out.SVF")
            with open(src, "wb") as fh:
                fh.write(b"0123456789")
            st, _ = run([src, dst])
            self.assertEqual(st, 2)
            self.assertEqual(os.listdir(d), ["in.SVF"])

    def test_tree_check_failure_keeps_target(self):
        real = jamoset.pack_svfn

        def bad(*a, **k):
            out = bytearray(real(*a, **k))
            if k.get("jset") or (len(a) > 8 and a[8]):          # the jamo face only
                cells = a[5]
                cells = [bytes(c) for c in cells]
                i = next(i for i, c in enumerate(cells) if any(c))
                j = next(j for j, b in enumerate(cells[i]) if b)
                cells[i] = cells[i][:j] + bytes([cells[i][j] ^ 0x01]) + cells[i][j + 1:]
                return real(a[0], a[1], a[2], a[3], a[4], cells, *a[6:], **k)
            return bytes(out)

        with tempfile.TemporaryDirectory() as d:
            before = {}
            for name in FIXTURES:
                before[name] = fixture(name)
                with open(os.path.join(d, name), "wb") as fh:
                    fh.write(before[name])
            with mock.patch.object(jamoset, "pack_svfn", bad):
                st, text = run(["--tree", d, d, "--check"])
            self.assertEqual(st, 1, text)
            with open(os.path.join(d, "NEODG16A.SVF"), "rb") as fh:
                self.assertEqual(fh.read(), before["NEODG16A.SVF"])
            with open(os.path.join(d, "PAPLG16.SVF"), "rb") as fh:
                self.assertEqual(struct.unpack_from("<H", fh.read(), 4)[0], 3)
            self.assertIn("NEODG16A.SVF FAIL", text)
            self.assertTrue(text.strip().splitlines()[-1].endswith(" failed=1"), text)
            self.assertEqual([n for n in os.listdir(d) if n.endswith(".tmp")], [])

    def test_face_api_kept(self):
        for name in FIXTURES:
            for data in (svf2to3.convert(fixture(name), "default"), svf2to3.convert(fixture(name), "dos")):
                a = svfline.Face(data)
                b = svfline.Face.from_svfn(svf2to3._parse(data))
                self.assertEqual(sorted(a.glyphs), sorted(b.glyphs))
                self.assertTrue(all(a.glyphs[cp] == b.glyphs[cp] for cp in a.glyphs))
                self.assertEqual((a.has_metrics, a.dy_min, a.dy_max, a.pitch), (b.has_metrics, b.dy_min, b.dy_max, b.pitch))
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, name)
                with open(path, "wb") as fh:
                    fh.write(svf2to3.convert(fixture(name), "default"))
                self.assertEqual(svfline.Face.load(path).glyphs,
                                 svfline.Face(svf2to3.convert(fixture(name), "default")).glyphs)

    # ---- fix round 1 ----
    def test_check_compares_marks_at_origin_flag(self):          # Z1
        v2 = fixture("PAPLG16.SVF")
        self.assertTrue(struct.unpack_from("<H", v2, 6)[0] & jamoset.FLAG_MARKS_AT_ORIGIN)
        v3 = bytearray(svf2to3.convert(v2, "default"))
        svf2to3.check(v2, bytes(v3))
        struct.pack_into("<H", v3, 6, struct.unpack_from("<H", v3, 6)[0] & ~jamoset.FLAG_MARKS_AT_ORIGIN)
        with self.assertRaisesRegex(AssertionError, "flag"):
            svf2to3.check(v2, bytes(v3))

    def test_tree_refuses_bad_source(self):                      # Z2
        with tempfile.TemporaryDirectory() as d:
            dst = os.path.join(d, "dst")
            for src in (os.path.join(d, "missing"), os.path.join(d, "afile")):
                with open(os.path.join(d, "afile"), "wb") as fh:
                    fh.write(b"x")
                st, _ = run(["--tree", src, dst])
                self.assertEqual(st, 2, src)
            self.assertFalse(os.path.exists(dst))

    @unittest.skipIf(os.geteuid() == 0, "root reads everything")
    def test_tree_unreadable_subdir_fails(self):                 # Z2
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "src"), os.path.join(d, "dst")
            os.makedirs(os.path.join(src, "locked"))
            with open(os.path.join(src, "ok.SVF"), "wb") as fh:
                fh.write(fixture("PAPLG16.SVF"))
            with open(os.path.join(src, "locked", "x.SVF"), "wb") as fh:
                fh.write(fixture("PAPLG16.SVF"))
            os.chmod(os.path.join(src, "locked"), 0)
            try:
                st, text = run(["--tree", src, dst])
            finally:
                os.chmod(os.path.join(src, "locked"), 0o755)
            self.assertEqual(st, 2, text)
            self.assertIn("locked FAIL", text)
            last = text.strip().splitlines()[-1]
            self.assertTrue(last.startswith("total faces=1 ") and last.endswith(" failed=1"), last)

    def test_v2_metrics_offset_inside_header(self):              # Z3
        for off in (0, 4, 35):
            v2 = bytearray(fixture("PAPLG16.SVF"))
            struct.pack_into("<I", v2, 20, off)    # metrics_off, as the v2 reader had it
            self.assertEqual(struct.unpack_from(svf2to3.V2_HEADER, v2)[12], off)
            self.assertFalse(svf2to3._parse_v2(bytes(v2)).metrics_ok, off)
            self.assertFalse(svfline.Face.from_svfn(svf2to3._parse_v2(bytes(v2))).has_metrics, off)

    def test_convert_drops_a_bad_v2_jset(self):                  # Z4
        v2 = bytearray(fixture("NEODG16A.SVF"))
        cmap_off = struct.unpack_from("<I", v2, 32)[0]
        count = struct.unpack_from("<H", v2, 12)[0]
        v2[cmap_off + 8 * count + 4] = 9                          # JSET version byte
        out = svf2to3.convert(bytes(v2), "default")
        f = jamoset.parse_svfn(out)
        self.assertIsNone(f.jset)
        self.assertFalse(f.jset_bad)
        self.assertFalse(f.flags & jamoset.FLAG_JAMO)
        svf2to3.check(bytes(v2), out)

    def test_sigterm_removes_temp_file(self):                    # Z5
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "src"), os.path.join(d, "dst")
            os.makedirs(src)
            for i in range(300):
                with open(os.path.join(src, "F%03d.SVF" % i), "wb") as fh:
                    fh.write(fixture("NEODG16A.SVF"))
            tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "svf2to3.py")
            p = subprocess.Popen([sys.executable, "-I", tool, "--tree", src, dst, "--check"],
                                 stdout=subprocess.PIPE, text=True)
            p.stdout.readline()                  # flushed per face
            p.send_signal(signal.SIGTERM)
            p.communicate()
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual([n for n in os.listdir(dst) if n.endswith(".tmp")], [])

    def test_total_counts_only_converted(self):                  # Z6
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "src"), os.path.join(d, "dst")
            os.makedirs(src)
            with open(os.path.join(src, "a.SVF"), "wb") as fh:
                fh.write(fixture("PAPLG16.SVF"))
            with open(os.path.join(src, "b.SVF"), "wb") as fh:
                fh.write(b"0123456789")
            st, text = run(["--tree", src, dst])
            self.assertEqual(st, 2)
            last = text.strip().splitlines()[-1]
            self.assertTrue(last.startswith("total faces=1 in=%d " % len(fixture("PAPLG16.SVF"))), last)
            self.assertTrue(last.endswith(" failed=1"), last)


JSET1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata", "jset1")


def jset1(name):
    with open(os.path.join(JSET1, name), "rb") as fh:
        return fh.read()


def repack(data, edit=None, jset=None):
    """The v3 face @p data rebuilt in its own layout through pack_svfn after @p edit(glyphs, metrics) (dicts by code
    point, edited in place); @p jset replaces its JSET block when given."""
    f = jamoset.parse_svfn(data)
    glyphs, metrics = dict(f.glyphs), dict(f.metrics)
    if edit:
        edit(glyphs, metrics)
    cps = sorted(glyphs)
    met = [metrics[cp] + (f.dy.get(cp, 0),) for cp in cps] if f.metrics_ok else None
    return jamoset.pack_svfn(f.cell_w, f.cell_h, f.ascent, f.bpp, f.flags & jamoset.FLAG_MARKS_AT_ORIGIN,
                             [glyphs[cp] for cp in cps], [(cp, i) for i, cp in enumerate(cps)], met,
                             f.jset if jset is None else jset, (f.dy_min, f.dy_max), jamoset.face_profile(f))


def block(data):
    return jamoset.parse_svfn(data).jset


class JsetVersionTest(unittest.TestCase):
    """svf2to3 --jset-version 1|2|auto (spec amendment 2026-10-23; plan Task 5)."""

    def test_upgrade_v3_jset1(self):
        src = jset1("NSQRB16.SVF")
        self.assertEqual(svf2to3.jset_version(block(src)), 1)
        out = svf2to3.convert(src, "default", jset_version="auto")
        j = block(out)
        self.assertEqual(svf2to3.jset_version(j), 2)
        na = struct.unpack_from("<H", j, 12)[0]
        self.assertGreater(na, 0)
        self.assertEqual(len(j), jamoset.jset_size(*j[6:11], na=na))
        svf2to3.check(src, out)
        h = jset1("NEODG16G.SVF")
        self.assertEqual(svf2to3.convert(h, "default"), h)
        self.assertEqual(svf2to3.convert(h, "default", jset_version="auto"), h)

    def test_convert_default_is_1(self):
        v2 = svf2to3.convert(jset1("NSQRB16.SVF"), "default", jset_version="auto")
        self.assertEqual(svf2to3.jset_version(block(v2)), 2)
        self.assertEqual(svf2to3.jset_version(block(svf2to3.convert(v2, "default"))), 1)
        n = jset1("NSQRB16.SVF")
        self.assertEqual(svf2to3.convert(n, "default"), n)

    def test_force_v2(self):
        src = jset1("NEODG16G.SVF")
        out = svf2to3.convert(src, "default", jset_version=2)
        j = block(out)
        self.assertEqual((svf2to3.jset_version(j), len(j)), (2, 181))
        svf2to3.check(src, out)

    def test_force_v1_from_v2(self):
        orig = jset1("NSQRB16.SVF")
        v2 = svf2to3.convert(orig, "default", jset_version="auto")
        v1 = svf2to3.convert(v2, "default", jset_version=1)
        self.assertEqual(svf2to3.jset_version(block(v1)), 1)
        t1, t2 = jamoset.unpack(block(v1)), jamoset.unpack(block(v2))
        self.assertEqual(vars(t1), vars(t2))        # piece numbers kept (R10)
        svf2to3.check(orig, v1)
        # the same slot glyphs as the original v1 face, slot by slot
        fo, f1, to = jamoset.parse_svfn(orig), jamoset.parse_svfn(v1), jamoset.unpack(block(orig))
        for name in ("init_piece", "med_piece", "fin_piece", "compat"):
            for a, b in zip(getattr(to, name), getattr(t1, name)):
                self.assertEqual(a == jamoset.BLANK, b == jamoset.BLANK)
                if a != jamoset.BLANK:
                    self.assertEqual(fo.glyphs[jamoset.PIECE_BASE + a], f1.glyphs[jamoset.PIECE_BASE + b])

    def test_auto_keeps_v2(self):
        v2 = svf2to3.convert(jset1("NEODG16G.SVF"), "default", jset_version=2)
        self.assertEqual(svf2to3.convert(v2, "default", jset_version="auto"), v2)
        self.assertEqual(svf2to3.convert(v2, "default", jset_version=2), v2)

    def test_upgrade_svfn_v2(self):
        src = fixture("NEODG16A.SVF")
        for v, want in (("auto", 1), (2, 2), (1, 1)):
            with self.subTest(version=v):
                out = svf2to3.convert(src, "default", jset_version=v)
                self.assertEqual(svf2to3.jset_version(block(out)), want)
                svf2to3.check(src, out)

    def test_check_catches_plane15_change(self):
        src = jset1("NSQRB16.SVF")
        out = svf2to3.convert(src, "default", jset_version="auto")
        f = jamoset.parse_svfn(out)
        cp = next(cp for cp in sorted(f.glyphs) if cp >= jamoset.PIECE_BASE and any(f.glyphs[cp]))

        def flip(glyphs, metrics):
            g = bytearray(glyphs[cp])
            g[next(i for i, b in enumerate(g) if b)] ^= 0x01
            glyphs[cp] = bytes(g)

        with self.assertRaisesRegex(AssertionError, "plane-15"):
            svf2to3.check(src, repack(out, flip))

    def test_upgrade_bad_v1_dropped(self):
        src = bytearray(jset1("NEODG16G.SVF"))
        jset_off = struct.unpack_from(jamoset.HEADER3, src)[18]
        self.assertEqual(src[jset_off:jset_off + 4], b"JSET")
        src[jset_off + 12] = src[jset_off + 6]               # v1 leadClass[0] = LC
        src = bytes(src)
        self.assertTrue(jamoset.parse_svfn(src).jset_bad)
        for v in ("auto", 2, 1):
            out = svf2to3.convert(src, "default", jset_version=v)
            f = jamoset.parse_svfn(out)
            self.assertFalse(f.flags & jamoset.FLAG_JAMO)
            self.assertIsNone(f.jset)
            svf2to3.check(src, out)

    def test_upgrade_unused_piece_kept(self):
        orig = jset1("NSQRB16.SVF")
        t = jamoset.unpack(block(orig))
        fresh = len(jamoset.pack(t).piece_map)
        extra = jamoset.PIECE_BASE + 0x7000
        f = jamoset.parse_svfn(orig)
        cell = bytes((i * 37 + 1) & 0xFF for i in range(len(next(iter(f.glyphs.values())))))

        def add(glyphs, metrics):
            self.assertNotIn(extra, glyphs)
            glyphs[extra] = cell
            metrics[extra] = (f.cell_w, 0, f.cell_w)

        src = repack(orig, add)
        out = svf2to3.convert(src, "default", jset_version=2)
        g = jamoset.parse_svfn(out).glyphs
        self.assertEqual(g[jamoset.PIECE_BASE + fresh], cell)
        self.assertEqual(max(cp for cp in g if cp >= jamoset.PIECE_BASE), jamoset.PIECE_BASE + fresh)
        svf2to3.check(src, out)

    def test_unused_pieces_keep_their_own_dy(self):
        # F1: two unused pieces A < B with dy[B] = 1: the one old -> new map carries glyph, metrics and dy together
        orig = jset1("NSQRB16.SVF")
        f = jamoset.parse_svfn(orig)
        self.assertTrue(f.metrics_ok)
        glyphs, metrics = dict(f.glyphs), dict(f.metrics)
        n = len(next(iter(glyphs.values())))
        A, B = jamoset.PIECE_BASE + 0x7000, jamoset.PIECE_BASE + 0x7001
        glyphs[A], glyphs[B] = bytes([0x11]) * n, bytes([0x22]) * n
        metrics[A], metrics[B] = (f.cell_w, 0, f.cell_w), (f.cell_w - 1, 1, f.cell_w - 1)
        dy = {B: 1}
        cps = sorted(glyphs)
        met = [metrics[cp] + (dy.get(cp, f.dy.get(cp, 0)),) for cp in cps]
        src = jamoset.pack_svfn(f.cell_w, f.cell_h, f.ascent, f.bpp, f.flags & jamoset.FLAG_MARKS_AT_ORIGIN,
                                [glyphs[cp] for cp in cps], [(cp, i) for i, cp in enumerate(cps)], met, f.jset,
                                (min(f.dy_min, 0), max(f.dy_max, 1)), jamoset.face_profile(f))
        for v in (2, "auto"):
            with self.subTest(version=v):
                out = svf2to3.convert(src, "default", jset_version=v)
                o = jamoset.parse_svfn(out)
                self.assertEqual(svf2to3.jset_version(o.jset), 2)
                found = {}
                for cp, g in o.glyphs.items():
                    if g in (bytes([0x11]) * n, bytes([0x22]) * n):
                        found[g[0]] = (o.metrics[cp], o.dy.get(cp, 0))
                self.assertEqual(found[0x11], ((f.cell_w, 0, f.cell_w), 0))
                self.assertEqual(found[0x22], ((f.cell_w - 1, 1, f.cell_w - 1), 1))
                svf2to3.check(src, out)

    def test_check_reports_unusable_jamo_set(self):
        # F3: both sides' sets unusable (a named piece has no glyph) -> composed comparison skipped, and said so
        orig = jset1("NEODG16G.SVF")
        f = jamoset.parse_svfn(orig)
        t = jamoset.unpack(f.jset)
        piece = next(jamoset.PIECE_BASE + p for p in t.init_piece if p != jamoset.BLANK)
        glyphs = {cp: g for cp, g in f.glyphs.items() if cp != piece}
        cps = sorted(glyphs)
        met = [f.metrics[cp] + (f.dy.get(cp, 0),) for cp in cps] if f.metrics_ok else None
        src = jamoset.pack_svfn(f.cell_w, f.cell_h, f.ascent, f.bpp, f.flags & jamoset.FLAG_MARKS_AT_ORIGIN,
                                [glyphs[cp] for cp in cps], [(cp, i) for i, cp in enumerate(cps)], met, f.jset,
                                (f.dy_min, f.dy_max), jamoset.face_profile(f))
        out, info = svf2to3.convert_info(src, "default")
        self.assertTrue(svf2to3.check_info(src, out)[1])
        self.assertFalse(svf2to3.check_info(orig, svf2to3.convert(orig, "default"))[1])

    def test_compat_refused(self):
        src = bytearray(jset1("NEODG16G.SVF"))
        jset_off, jset_len = struct.unpack_from(jamoset.HEADER3, src)[18:20]
        t = jamoset.unpack(src[jset_off:jset_off + jset_len])
        t.compat[30] = t.init_piece[0]                        # U+314F names a piece no medial set holds
        src[jset_off:jset_off + jset_len] = jamoset.pack_v1(t)
        src = bytes(src)
        self.assertIsNotNone(jamoset.parse_svfn(src).jset)    # a valid v1 face
        with tempfile.TemporaryDirectory() as d:
            s, dst = os.path.join(d, "src"), os.path.join(d, "dst")
            os.makedirs(s)
            with open(os.path.join(s, "BAD.SVF"), "wb") as fh:
                fh.write(src)
            st, text = run(["--tree", s, dst, "--jset-version", "2"])
            self.assertEqual(st, 2, text)
            self.assertIn("BAD.SVF FAIL", text)
            self.assertIn("U+314F", text)
            self.assertTrue(text.strip().splitlines()[-1].endswith(" failed=1"), text)
            self.assertFalse(os.path.exists(os.path.join(dst, "BAD.SVF")))
            # auto keeps it v1 (T5-C1)
            st, text = run(["--tree", s, dst, "--jset-version", "auto", "--check"])
            self.assertEqual(st, 0, text)
            self.assertIn("jset=1", text)
            # forced v1 keeps the block as it is
            st, text = run(["--tree", s, dst, "--jset-version", "1", "--check"])
            self.assertEqual(st, 0, text)
            with open(os.path.join(dst, "BAD.SVF"), "rb") as fh:
                self.assertEqual(fh.read(), src)

    def test_v2_input_idempotent(self):
        for name in ("NEODG16G.SVF", "NSQRB16.SVF"):
            for v in ("auto", 1, 2):
                with self.subTest(name=name, version=v):
                    out = svf2to3.convert(jset1(name), "default", jset_version=v)
                    self.assertEqual(svf2to3.convert(out, "default", jset_version=v), out)
                    if svf2to3.jset_version(block(out)) == 2:
                        self.assertEqual(svf2to3.convert(out, "default", jset_version="auto"), out)
        for name in FIXTURES:
            out = svf2to3.convert(fixture(name), "default")
            self.assertEqual(svf2to3.convert(out, "default"), out)

    def test_big_block_needs_jset_big(self):
        """PR-16: a verbatim v2 copy of a BIG table is a write too: refused without --jset-big, as a re-encode is."""
        t = jamoset.Tables(19, 28, 128, 128, 64)
        t.lead_class = [L % 19 for L in range(19)]
        t.tail_class = [0] + [1 + (T - 1) % 27 for T in range(1, 28)]
        n = 19 * 21 * 28
        t.init_set, t.med_set, t.fin_set = [c % 128 for c in range(n)], [c % 128 for c in range(n)], [c % 64 for c in range(n)]
        t.init_piece, t.med_piece, t.fin_piece = list(range(128 * 19)), list(range(128 * 19, 128 * 19 + 128 * 21)), \
            list(range(128 * 19 + 128 * 21, 128 * 19 + 128 * 21 + 64 * 27))
        npieces = len(t.init_piece) + len(t.med_piece) + len(t.fin_piece)
        for version in (1, 2):
            packed = jamoset.pack_jset(t, version, big=True)
            glyphs = [(jamoset.PIECE_BASE + p, bytes([1]) * 16, 8, 0, 8) for p in range(npieces)]
            face = jamoset.write_svfn(8, 16, 14, jamoset.renumber_glyphs(glyphs, packed.piece_map), packed.block)
            for v in (1, 2, "auto"):
                with self.subTest(block=version, jset_version=v):
                    with self.assertRaisesRegex(ValueError, "--jset-big"):
                        svf2to3.convert(face, "default", jset_version=v)
                    out = svf2to3.convert(face, "default", jset_version=v, jset_big=True)
                    self.assertTrue(jamoset.unpack(block(out)).nf == 64)

    def test_big_jmap_fallback_needs_jset_big(self):
        """The same rule for the fallback of a JMAP region copied verbatim."""
        t = jamoset.Tables(13, 12, 32, 24, 16)
        t.lead_class = [L % 13 for L in range(19)]
        t.tail_class = [0] + [1 + (T - 1) % 11 for T in range(1, 28)]
        n = 13 * 21 * 12
        t.init_set, t.med_set, t.fin_set = [c % 32 for c in range(n)], [c % 24 for c in range(n)], [c % 16 for c in range(n)]
        t.init_piece = list(range(32 * 19))
        t.med_piece = list(range(32 * 19, 32 * 19 + 24 * 21))
        t.fin_piece = list(range(32 * 19 + 24 * 21, 32 * 19 + 24 * 21 + 16 * 27))
        shifted = jamoset.shift_pieces(t, 2)
        jm = jamoset.Jmap(0, 1, 1, 0)
        jm.entries = {0: (1, 1, 0)}
        jm.fallback, jm.fallback_version = shifted, 1
        jm.fallback_block = jamoset.pack_fallback(shifted, 1, big=True)
        glyphs = [(jamoset.PIECE_BASE + p, bytes([1]) * 16, 8, 0, 8)
                  for p in range(max(shifted.init_piece + shifted.med_piece + shifted.fin_piece) + 1)]
        face = jamoset.write_svfn(8, 16, 14, glyphs, jamoset.pack_jmap(jm, jm.fallback_block))
        with self.assertRaisesRegex(ValueError, "--jset-big"):
            svf2to3.convert(face, "default")
        out = svf2to3.convert(face, "default", jset_big=True)
        self.assertEqual(block(out), block(face))

    def test_jset_version_of(self):
        self.assertIsNone(svf2to3.jset_version(None))
        self.assertEqual(svf2to3.jset_version(block(jset1("NEODG16G.SVF"))), 1)

    def test_cli_reports_versions(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "src"), os.path.join(d, "dst")
            os.makedirs(src)
            for name in ("NEODG16G.SVF", "NSQRB16.SVF"):
                with open(os.path.join(src, name), "wb") as fh:
                    fh.write(jset1(name))
            with open(os.path.join(src, "PAPLG16.SVF"), "wb") as fh:
                fh.write(fixture("PAPLG16.SVF"))
            st, text = run(["--tree", src, dst, "--check"])         # default 1 (amendment 3): no face changes version
            self.assertEqual(st, 0, text)
            lines = {ln.split()[0]: ln for ln in text.strip().splitlines()}
            self.assertTrue(lines["NSQRB16.SVF"].endswith(" jset=1 jset_v1=11681 jset_v2=5922"), lines["NSQRB16.SVF"])
            self.assertIn(" v1_faces=2 v1_jset=12334 v2_faces=0 v2_jset=0 failed=0", lines["total"])
            shutil.rmtree(dst)
            st, text = run(["--tree", src, dst, "--check", "--jset-version", "auto"])
            self.assertEqual(st, 0, text)
            n2 = len(block(svf2to3.convert(jset1("NSQRB16.SVF"), "default", jset_version="auto")))
            lines = {ln.split()[0]: ln for ln in text.strip().splitlines()}
            self.assertTrue(lines["NEODG16G.SVF"].endswith(" jset=1 jset_v1=653 jset_v2=181"), lines["NEODG16G.SVF"])
            self.assertTrue(lines["NSQRB16.SVF"].endswith(" jset=2 jset_v1=11681 jset_v2=%d" % n2),
                            lines["NSQRB16.SVF"])
            self.assertNotIn("jset", lines["PAPLG16.SVF"])
            self.assertIn(" v1_faces=1 v1_jset=653 v2_faces=1 v2_jset=%d failed=0" % n2, lines["total"])
            st, text = run([os.path.join(src, "NEODG16G.SVF"), os.path.join(d, "one.SVF"), "--jset-version", "2"])
            self.assertEqual(st, 0, text)
            self.assertTrue(text.strip().endswith(" jset=2 jset_v1=653 jset_v2=181"), text)
            with self.assertRaises(SystemExit):
                with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                    svf2to3.main([src, dst, "--jset-version", "3"])


if __name__ == "__main__":
    unittest.main()
