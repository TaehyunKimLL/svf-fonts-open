#!/usr/bin/env python3
"""The portable C SVF renderer (c/) against the Python reference (jamoset.py), byte for byte, on every face in svf/.

  python3 -m unittest tools.test_c_renderer        (or: python3 tools/test_c_renderer.py)

The library is built with `make -C c O=<temp dir>` once per run; a host without a C compiler skips with a message.
With SVF_ASAN=1 in the environment (c/check.sh) every run uses the -fsanitize=address,undefined build.
`svfdump` writes the library's view of a face (formats in c/tests/svfdump.c); the expected bytes are computed here from
jamoset.parse_svfn plus the engine's load rules (spec/SVF.md "Per-glyph dy"), so no golden files are stored.
"""

import copy
import glob
import importlib.util
import itertools
import os
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import jamoset  # noqa: E402
import svf_synth  # noqa: E402
import svfline  # noqa: E402

C_DIR = os.path.join(ROOT, "c")
SVF_DIR = os.path.join(ROOT, "svf")
EXPECTED_FACES = 117

_build = {}


def build():
    """Build c/ once into a temp dir; returns {'svfdump': path, 'svfdump-asan': path} or raises SkipTest."""
    if "dir" in _build:
        return _build
    cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("gcc")
    if not cc or not shutil.which("make"):
        raise unittest.SkipTest("no C compiler or make on this host: the C renderer tests are skipped")
    out = tempfile.mkdtemp(prefix="svf-c-")
    _build["dir"] = out
    r = subprocess.run(["make", "-s", "-C", C_DIR, "O=" + out, "svfdump", "svfdump-asan", "svfdump-page",
                        "svfdump-vesa", "svfdump-bytes", "vesa-lines-dump", "test-pad", "svfdump-rd8", "test-open", "test-args", "test-args-page",
                        "test-args-vesa", "test-args-gray", "test-args-jmap", "svfdump-gray", "test-layouts", "test-open-size16"],
                       capture_output=True,
                       text=True)
    if r.returncode != 0:
        raise AssertionError("make -C c failed:\n" + r.stdout + r.stderr)
    # SVF_ASAN=1 (c/check.sh): every run, the plain svfdump's too, uses the sanitizer build.
    _build["svfdump"] = os.path.join(out, "svfdump-asan" if os.environ.get("SVF_ASAN") == "1" else "svfdump")
    _build["svfdump-asan"] = os.path.join(out, "svfdump-asan")
    _build["svfdump-page"] = os.path.join(out, "svfdump-page")
    _build["svfdump-vesa"] = os.path.join(out, "svfdump-vesa")
    _build["svfdump-bytes"] = os.path.join(out, "svfdump-bytes")
    _build["test-pad"] = os.path.join(out, "test-pad")
    _build["test-pad-bytes"] = os.path.join(out, "test-pad-bytes")
    _build["svfdump-rd8"] = os.path.join(out, "svfdump-rd8")
    _build["test-open"] = os.path.join(out, "test-open")
    _build["test-args"] = os.path.join(out, "test-args")
    _build["test-args-page"] = os.path.join(out, "test-args-page")
    _build["test-args-vesa"] = os.path.join(out, "test-args-vesa")
    _build["test-args-gray"] = os.path.join(out, "test-args-gray")
    _build["test-args-jmap"] = os.path.join(out, "test-args-jmap")
    _build["svfdump-gray"] = os.path.join(out, "svfdump-gray")
    _build["test-open-size16"] = os.path.join(out, "test-open-size16")
    for name in ("test-layouts", "test-layouts-strict", "test-layouts-tight", "test-layouts-pair"):
        _build[name] = os.path.join(out, name)
    return _build


READER_FLAGS = {"v2only": "-DSVF_JSET_V1=0", "v1only": "-DSVF_JSET_V2=0", "trusted": "-DSVF_JSET_TRUSTED=1",
                "trusted1": "-DSVF_JSET_TRUSTED=1 -DSVF_JSET_V2=0", "trusted2": "-DSVF_JSET_TRUSTED=1 -DSVF_JSET_V1=0",
                "pop4off": "-DSVF_JSET_POP4=0", "nojmap": "-DSVF_JMAP=0 -DSVF_JMAP_RECOG=1",
                "v1nojmap": "-DSVF_JSET_V2=0 -DSVF_JMAP=0 -DSVF_JMAP_RECOG=1", "nojmap_norecog": "-DSVF_JMAP=0 -DSVF_JMAP_RECOG=0",
                "nojmap_default": "-DSVF_JMAP=0", "v2only_nojmap": "-DSVF_JSET_V1=0 -DSVF_JMAP=0",
                "v1only_nojmap": "-DSVF_JSET_V2=0 -DSVF_JMAP=0", "jmap": "-DSVF_JMAP=1",
                "jmap_trusted": "-DSVF_JMAP=1 -DSVF_JSET_TRUSTED=1",
                "nolist": "-DSVF_JMAP=1 -DSVF_JMAP_LIST=0", "list": "-DSVF_JMAP=1 -DSVF_JMAP_LIST=1", "list_big": "-DSVF_JMAP=1 -DSVF_JMAP_LIST=1 -DSVF_JSET_BIG=1",
                "list_trusted": "-DSVF_JMAP=1 -DSVF_JMAP_LIST=1 -DSVF_JSET_TRUSTED=1",
                "nolist_trusted": "-DSVF_JMAP=1 -DSVF_JMAP_LIST=0 -DSVF_JSET_TRUSTED=1",
                "list_ks": "-DSVF_JMAP=1 -DSVF_JMAP_LIST=1 -DSVF_JSET_V1=0 -DSVF_JSET_V2=0",
                "ksonly": "-DSVF_JMAP=1 -DSVF_JSET_V1=0 -DSVF_JSET_V2=0",
                "narrow": "-DSVF_JSET_BIG=0", "big": "-DSVF_JSET_BIG=1", "big_v1": "-DSVF_JSET_BIG=1 -DSVF_JSET_V2=0",
                "big_v2": "-DSVF_JSET_BIG=1 -DSVF_JSET_V1=0", "big_trusted": "-DSVF_JSET_BIG=1 -DSVF_JSET_TRUSTED=1",
                "big_nojmap": "-DSVF_JSET_BIG=1 -DSVF_JMAP=0", "big_v2_nojmap": "-DSVF_JSET_BIG=1 -DSVF_JSET_V1=0 -DSVF_JMAP=0"}


def reader_flag(which):
    """The make flags of build_reader(@p which). The reader-switch builds (everything but the big* ones) pin -DSVF_JSET_BIG=0:
    svf.h now defaults SVF_JSET_BIG to 1 on the host (Task 17), and these tests model the narrow reader (12 x 12 classes,
    32/24/16 sets; JSET_MAX, JSET_LOAD_MAX); BIG has its own builds (big*) and the default host build is BIG."""
    flag = READER_FLAGS[which]
    return flag if "JSET_BIG" in flag else flag + " -DSVF_JSET_BIG=0"


def build_reader(which):
    """svfdump-asan and svfdump-rd8 built with a JSET switch: @p which "v2only" (-DSVF_JSET_V1=0, the version 2 reader
    alone), "v1only" (-DSVF_JSET_V2=0, the version 1 reader alone), "trusted" (-DSVF_JSET_TRUSTED=1: no JSET validation;
    only valid faces are ever run on it) or "pop4off" (-DSVF_JSET_POP4=0). {'svfdump-asan': path, 'svfdump-rd8': path}."""
    b = build()
    if which not in b:
        flag = reader_flag(which)
        out = os.path.join(b["dir"], which)
        asan = ("-O1 -g -fsanitize=address,undefined,pointer-overflow -fno-sanitize-recover=all "
                "-fno-omit-frame-pointer " + flag)
        r = subprocess.run(["make", "-s", "-C", C_DIR, "O=" + out, "ASAN=" + asan, "svfdump-asan", "svfdump-rd8"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError(f"make -C c ({flag}) failed:\n" + r.stdout + r.stderr)
        b[which] = {name: os.path.join(out, name) for name in ("svfdump-asan", "svfdump-rd8")}
    return b[which]


def build_v2only():
    return build_reader("v2only")


def build_v1only():
    return build_reader("v1only")


def tearDownModule():
    if "dir" in _build:
        shutil.rmtree(_build.pop("dir"), ignore_errors=True)
    _build.clear()  # the reader-switch builds live below that dir: a later test module must rebuild them


def faces():
    """Every face under svf/ (*.SVF or *.svf, any case), sorted."""
    return sorted(p for p in glob.glob(os.path.join(SVF_DIR, "**", "*"), recursive=True)
                  if os.path.isfile(p) and p.lower().endswith(".svf"))


def run_dump(face, *args, asan=False):
    """svfdump FACE ARGS...: stdout bytes; fails the test on a non-zero exit."""
    exe = build()["svfdump-asan" if asan else "svfdump"]
    r = subprocess.run([exe, face] + list(args), capture_output=True)
    if r.returncode != 0:
        raise AssertionError(f"svfdump {face} {' '.join(args)} exited {r.returncode}: {r.stderr.decode(errors='replace')}")
    return r.stdout


def header(data):
    """(flags, bpp, count, cell_w, cell_h, dy_min, dy_max, metrics_off, data_off, data_size, cmap_off)."""
    (_, _, flags, bpp, _, _, _, count, cw, ch, _, dy_min, dy_max, _, metrics_off, data_off, data_size, cmap_off, _, _,
     _) = struct.unpack_from(jamoset.HEADER3, data)
    return flags, bpp, count, cw, ch, dy_min, dy_max, metrics_off, data_off, data_size, cmap_off


def offset_table_end(data):
    """The end of a v3 file's glyph offset table (header byte 44, count + 1 entries of 2 or 4 bytes)."""
    (_, _, _, _, _, b10, _, count) = struct.unpack_from("<4sHHBBBBH", data)
    (tab_off,) = struct.unpack_from("<I", data, 44)
    return tab_off + (count + 1) * (4 if b10 & 8 else 2)


def fill_rows(data, value=0xFF):
    """A copy of the v3 file @p data with every row byte of every non-blank glyph record set to @p value (the record
    headers, the phase bytes and the padding stay), so the bits past the cell width come back as padding."""
    d = bytearray(data)
    (_, _, _, _, b9, b10, _, count, cw, ch) = struct.unpack_from("<4sHHBBBBHBB", d)
    bpp = d[8]
    rec, row, off32 = b9 & 7, b9 >> 3 & 7, bool(b10 & 8)
    pitch = (cw * bpp + 7) // 8
    data_off, tab_off = struct.unpack_from("<I", d, 24)[0], struct.unpack_from("<I", d, 44)[0]
    for g in range(count):
        a = struct.unpack_from("<I" if off32 else "<H", d, tab_off + (4 if off32 else 2) * g)[0] << (0 if off32 else rec)
        x0, y0, wb, h = d[data_off + a:data_off + a + 4]
        if not wb or not h:
            continue
        rp = (wb + (1 << row) - 1) >> row << row
        start = data_off + a + 4 + (((y0 * pitch) & 3) if rec >= 2 and not row and wb == pitch else 0)
        for r in range(h):
            d[start + r * rp:start + r * rp + wb] = bytes([value]) * wb
    return bytes(d)


def v3_span(data, g):
    """(file offset, byte length) of the record of glyph index @p g of a v3 file."""
    count, stride, rec, row, data_off, tab_off, off32, pitch, ch, bpp = v3_info(data)
    w = 4 if off32 else 2
    a, b = (struct.unpack_from("<I" if off32 else "<H", data, tab_off + w * i)[0] << (0 if off32 else rec)
            for i in (g, g + 1))
    return data_off + a, b - a


def dy_range_used(data):
    """The engine's dy range: the header's, or (0, 0) when it is given without metrics or does not fit the cell."""
    flags, _, count, _, ch, lo, hi, metrics_off, _, _, _ = header(data)
    metrics_ok = bool(flags & jamoset.FLAG_VARIABLE) and metrics_off >= jamoset.HEADER3_SIZE and metrics_off + 4 * count <= len(data)
    if (lo or hi) and (not metrics_ok or lo > 0 or hi < 0 or -lo > ch or hi > ch):
        return 0, 0
    return lo, hi


def expected_glyphs(data):
    """svfdump FACE glyphs, from jamoset: per cmap entry in cmap order u32 cp, advance, bearing x, ink width, dy
    (zeros without a metrics table; dy 0 outside the range), then the cell with the bits past the cell width masked."""
    f = jamoset.parse_svfn(data)
    flags, bpp, count, cw, ch, _, _, _, _, _, cmap_off = header(data)
    lo, hi = dy_range_used(data)
    pitch = (cw * bpp + 7) // 8
    used = (cw * bpp) % 8
    last = (0xFF << (8 - used)) & 0xFF if used else 0xFF
    out = bytearray()
    for k in range(count):
        (cp,) = struct.unpack_from("<I", data, cmap_off + 8 * k)
        out += struct.pack("<I", cp)
        if flags & jamoset.FLAG_VARIABLE:
            adv, ix, iw = f.metrics[cp]
            dy = f.dy.get(cp, 0)
            if not lo <= dy <= hi:
                dy = 0
            out += struct.pack("<BbBb", adv, ix, iw, dy)
        else:
            out += bytes(4)
        cell = bytearray(f.glyphs[cp])
        for y in range(ch):
            cell[y * pitch + pitch - 1] &= last
        out += cell
    return bytes(out)


class TestFace(unittest.TestCase):
    def test_face_count(self):
        self.assertEqual(len(faces()), EXPECTED_FACES)

    def test_glyphs_all_faces(self):
        n = 0
        for face in faces():
            with self.subTest(face=os.path.relpath(face, ROOT)):
                with open(face, "rb") as fh:
                    data = fh.read()
                self.assertEqual(run_dump(face, "glyphs"), expected_glyphs(data))
                n += 1
        print(f"\n  test_glyphs_all_faces: {n} faces match jamoset", file=sys.stderr)

    def test_syllables_all_jamo_faces_svf(self):
        n = 0
        for face in faces():
            with open(face, "rb") as fh:
                data = fh.read()
            if not header(data)[0] & jamoset.FLAG_JAMO:
                continue
            with self.subTest(face=os.path.relpath(face, ROOT)):
                self.assertEqual(run_dump(face, "syllables"), expected_syllables(data))
            n += 1
        self.assertGreater(n, 0)
        print(f"\n  test_syllables_all_jamo_faces_svf: {n} jamo faces", file=sys.stderr)

    def test_profiles_identical(self):
        """Spec test 2, kept forever: one face in every profile (and units 6,6,6,32, and mcu-strict y-cropped) gives the
        source face's glyphs, syllables and lines."""
        tmp = tempfile.mkdtemp(prefix="svf-prof-")
        try:
            variants = sample_variants(tmp)
            n = 0
            for name in V3_SAMPLE:
                orig = face_named(name)
                with open(orig, "rb") as fh:
                    data = fh.read()
                stride = stride_of(data)
                jamo = bool(header(data)[0] & jamoset.FLAG_JAMO)
                want_glyphs = split_glyphs(expected_glyphs(data), stride)
                want_lines = [line_run("line", [orig], t, LINE_W, LINE_H, *LINE_PLACES[0])[1] for t in LINE_TEXTS]
                for prof in V3_PROFILES + ("mcu-strict/y",):
                    path = variants[(name, prof)]
                    with self.subTest(face=name, profile=prof):
                        self.assertEqual(split_glyphs(run_dump(path, "glyphs"), stride), want_glyphs)
                        if jamo:
                            self.assertEqual(run_dump(path, "syllables"), expected_syllables(data))
                        for text, want in zip(LINE_TEXTS, want_lines):
                            rc, out, err = line_run("line", [path], text, LINE_W, LINE_H, *LINE_PLACES[0])
                            self.assertEqual(rc, 0, err)
                            self.assertEqual(out, want, repr(text))
                    n += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        print(f"\n  test_profiles_identical: {n} face x profile variants", file=sys.stderr)

    def test_truncated_faces_fail(self):
        """Every face cut at 40 evenly spaced lengths (and 0, 35, 36, 47, 48): exit 2 naming an SVF_E_ error, never a crash or a
        sanitizer report. A cut that only shortens a JSET block lying after every other table may load as a plain face
        (SVF.md: a bad JSET loads a plain face); no repo face is laid out that way today."""
        exe = build()["svfdump-asan"]
        tmp = tempfile.mkdtemp(prefix="svf-trunc-")
        runs = 0
        try:
            for face in faces():
                with open(face, "rb") as fh:
                    data = fh.read()
                flags, _, count, _, _, _, _, metrics_off, data_off, data_size, cmap_off = header(data)
                tables_end = max(cmap_off + 8 * count, data_off + data_size, offset_table_end(data),
                                 metrics_off + 4 * count if flags & jamoset.FLAG_VARIABLE else 0)
                cuts = sorted({len(data) * i // 40 for i in range(40)} | {0, 35, 36, 47, 48})
                for cut in cuts:
                    if cut >= len(data):
                        continue
                    path = os.path.join(tmp, "cut.svf")
                    with open(path, "wb") as fh:
                        fh.write(data[:cut])
                    r = subprocess.run([exe, path, "glyphs"], capture_output=True)
                    err = r.stderr.decode(errors="replace")
                    runs += 1
                    where = f"{os.path.relpath(face, ROOT)} cut at {cut}: exit {r.returncode}, {err.strip()}"
                    self.assertNotIn("Sanitizer", err, where)
                    self.assertNotIn("runtime error", err, where)
                    if r.returncode == 0 and flags & jamoset.FLAG_JAMO and cut >= tables_end:
                        continue
                    self.assertEqual(r.returncode, 2, where)
                    self.assertIn("SVF_E_", err, where)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        print(f"\n  test_truncated_faces_fail: {runs} truncated faces refused", file=sys.stderr)


class TestValidation(unittest.TestCase):
    """Hand-made header faults on one real face: each is refused with its own error, or loads with its status bit."""

    FACE = os.path.join(SVF_DIR, "dos", "NEODG16A.SVF")

    def setUp(self):
        build()
        with open(self.FACE, "rb") as fh:
            self.data = bytearray(fh.read())
        self.tmp = tempfile.mkdtemp(prefix="svf-val-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def dump(self, data, what="info"):
        path = os.path.join(self.tmp, "f.svf")
        with open(path, "wb") as fh:
            fh.write(bytes(data))
        r = subprocess.run([build()["svfdump-asan"], path, what], capture_output=True)
        err = r.stderr.decode(errors="replace")
        self.assertNotIn("Sanitizer", err)
        self.assertNotIn("runtime error", err)
        return r.returncode, r.stdout.decode(errors="replace"), err

    def refused(self, data, name):
        code, _, err = self.dump(data)
        self.assertEqual(code, 2, err)
        self.assertIn(name, err)

    def info(self, data):
        code, out, err = self.dump(data)
        self.assertEqual(code, 0, err)
        return dict(kv.split("=") for kv in out.split())

    def test_face_present(self):
        self.assertTrue(os.path.exists(self.FACE))

    def test_info_of_a_good_face(self):
        flags, bpp, count, cw, ch = header(self.data)[:5]
        i = self.info(self.data)
        self.assertEqual((int(i["bpp"]), int(i["cell_w"]), int(i["cell_h"]), int(i["flags"]), int(i["glyphs"])),
                         (bpp, cw, ch, flags, count))
        self.assertEqual(i["cmap_linear"], "0")
        self.assertEqual(i["dy_ignored"], "0")

    def test_bad_magic(self):
        self.data[0:4] = b"SVFX"
        self.refused(self.data, "SVF_E_MAGIC")

    def test_versions_1_2_and_4_refused(self):
        for version in (1, 2, 4):
            with self.subTest(version=version):
                struct.pack_into("<H", self.data, 4, version)
                self.refused(self.data, "SVF_E_VERSION")
        struct.pack_into("<H", self.data, 4, 2)
        self.refused(self.data, "convert with tools/svf2to3.py")

    def test_bad_bpp(self):
        for bpp in (0, 3, 4, 16):
            self.data[8] = bpp
            self.refused(self.data, "SVF_E_BPP")

    def test_empty_glyph_box(self):
        for field in (12, 14, 15):
            d = bytearray(self.data)
            if field == 12:
                struct.pack_into("<H", d, 12, 0)
            else:
                d[field] = 0
            self.refused(d, "SVF_E_RANGE")

    def test_offsets_past_the_end(self):
        """Offsets of the glyph data, code point table, JSET and glyph offset table past the file (or wrapping 32 bits)
        are range errors; the metrics table is dropped, the glyphs kept, when its (aligned) offset is past the file;
        a misaligned table offset is SVF_E_LAYOUT first, even for the table that would be dropped."""
        n = len(self.data)
        for off in (24, 28, 32, 36, 40, 44):
            for value in (n + 1, 0xFFFFFFFF, 0xFFFFFFF0):
                d = bytearray(self.data)
                struct.pack_into("<I", d, off, value)
                with self.subTest(field=off, value=value):
                    self.refused(d, "SVF_E_RANGE")
        for value in ((n + 16) & ~15, 0xFFFFFFF0, 0xFFFFFFFC):
            d = bytearray(self.data)
            struct.pack_into("<I", d, 20, value)
            with self.subTest(field=20, value=value):
                # The metrics table is dropped, the glyphs kept (SVF.md "Validation"); a dy range then is void.
                self.assertEqual(self.info(d)["metrics"], "0")
        for value in (n + 1, 0xFFFFFFFF):
            d = bytearray(self.data)
            struct.pack_into("<I", d, 20, value)
            with self.subTest(field=20, value=value, misaligned=True):
                self.refused(d, "SVF_E_LAYOUT")

    def test_cmap_offset_zero(self):
        struct.pack_into("<I", self.data, 32, 0)
        self.refused(self.data, "SVF_E_RANGE")

    def test_glyph_count_beyond_data(self):
        count = header(self.data)[2]
        struct.pack_into("<H", self.data, 12, count + 1)
        self.refused(self.data, "SVF_E_RANGE")

    def test_cmap_index_beyond_count(self):
        cmap_off = header(self.data)[10]
        struct.pack_into("<I", self.data, cmap_off + 4, 0xFFFF)
        self.refused(self.data, "SVF_E_RANGE")

    def test_unsorted_cmap_is_searched_linearly(self):
        count, cmap_off = header(self.data)[2], header(self.data)[10]
        a = self.data[cmap_off:cmap_off + 8]
        b = self.data[cmap_off + 8 * (count - 1):cmap_off + 8 * count]
        self.data[cmap_off:cmap_off + 8], self.data[cmap_off + 8 * (count - 1):cmap_off + 8 * count] = b, a
        self.assertEqual(self.info(self.data)["cmap_linear"], "1")
        self.assertEqual(self.dump_bytes(self.data), expected_glyphs(bytes(self.data)))

    def dump_bytes(self, data):
        path = os.path.join(self.tmp, "g.svf")
        with open(path, "wb") as fh:
            fh.write(bytes(data))
        return run_dump(path, "glyphs", asan=True)

    def test_len_above_32_bits_refused(self):
        r = subprocess.run([build()["test-open"]], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)
        self.assertNotIn("Sanitizer", r.stderr)

    def test_duplicate_code_point_last_entry_wins(self):
        """A code point listed twice with different glyphs: the last entry wins, as jamoset.parse_svfn's dict keeps it."""
        _, bpp, count, cw, ch, _, _, _, data_off, _, cmap_off = header(self.data)
        stride = (cw * bpp + 7) // 8 * ch
        orig = jamoset.parse_svfn(bytes(self.data))
        cp0, g0 = struct.unpack_from("<II", self.data, cmap_off)
        for k in (count // 2, count - 1):
            d = bytearray(self.data)
            cp, g = struct.unpack_from("<II", d, cmap_off + 8 * k)
            self.assertNotEqual(orig.glyphs[cp], orig.glyphs[cp0])
            struct.pack_into("<I", d, cmap_off + 8 * k, cp0)      # entry k now names cp0 with glyph g
            with self.subTest(duplicate_at=k):
                self.assertEqual(self.info(d)["cmap_linear"], "1")
                out = self.dump_bytes(d)
                self.assertEqual(out, expected_glyphs(bytes(d)))
                self.assertEqual(out[8:8 + stride], orig.glyphs[cp])

    def test_padding_bits_are_masked(self):
        """The repo faces store zero padding; a face with every glyph byte 0xFF must come back with the bits past the
        cell width cleared."""
        for face in faces():
            with open(face, "rb") as fh:
                data = bytearray(fh.read())
            _, bpp, count, cw, ch, _, _, _, data_off, _, _ = header(data)
            if (cw * bpp) % 8:
                break
        else:
            self.fail("no face with padded rows")
        stride = (cw * bpp + 7) // 8 * ch
        data = bytearray(fill_rows(bytes(data)))
        out = self.dump_bytes(data)
        self.assertEqual(out, expected_glyphs(bytes(data)))
        self.assertNotIn(b"\xff" * stride, out)

    def test_bad_dy_ranges_are_ignored(self):
        ch = header(self.data)[4]
        for lo, hi in ((1, 2), (-2, -1), (-(ch + 1), 0), (0, ch + 1)):
            d = bytearray(self.data)
            struct.pack_into("<bb", d, 17, lo, hi)
            with self.subTest(lo=lo, hi=hi):
                self.assertEqual(self.info(d)["dy_ignored"], "1")
                self.assertEqual(self.dump_bytes(d), expected_glyphs(bytes(d)))

    def test_dy_outside_the_range_draws_at_0(self):
        flags, _, count, _, _, _, _, metrics_off = header(self.data)[:8]
        self.assertTrue(flags & jamoset.FLAG_VARIABLE)
        struct.pack_into("<bb", self.data, 17, -1, 2)
        for k, dy in enumerate((-1, 2, 3, -2)):
            self.data[metrics_off + 4 * k + 3] = dy & 0xFF
        self.assertEqual(self.info(self.data)["dy_ignored"], "0")
        self.assertEqual(self.dump_bytes(self.data), expected_glyphs(bytes(self.data)))

    def test_dy_range_without_metrics_is_ignored(self):
        struct.pack_into("<H", self.data, 6, header(self.data)[0] & ~jamoset.FLAG_VARIABLE)
        struct.pack_into("<bb", self.data, 17, -1, 1)
        i = self.info(self.data)
        self.assertEqual((i["dy_ignored"], i["metrics"]), ("1", "0"))
        self.assertEqual(self.dump_bytes(self.data), expected_glyphs(bytes(self.data)))


class TestHostile(unittest.TestCase):
    """Crafted header mutations of two small valid faces (1 bpp jamo set, 2 bpp padded face): each is refused with an
    SVF_E_ error, or (a metrics table that does not fit) loads with the table dropped, always ASan/UBSan clean."""

    FACES = (os.path.join(SVF_DIR, "dos", "NEODG16G.SVF"), os.path.join(SVF_DIR, "dos", "NGO16BX2.SVF"))

    def setUp(self):
        build()
        self.tmp = tempfile.mkdtemp(prefix="svf-hostile-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_asan(self, data, what):
        path = os.path.join(self.tmp, "h.svf")
        with open(path, "wb") as fh:
            fh.write(bytes(data))
        r = subprocess.run([build()["svfdump-asan"], path, what], capture_output=True)
        err = r.stderr.decode(errors="replace")
        self.assertNotIn("Sanitizer", err)
        self.assertNotIn("runtime error", err)
        return r.returncode, r.stdout, err

    @staticmethod
    def put(data, fmt, off, *values):
        d = bytearray(data)
        struct.pack_into(fmt, d, off, *values)
        return d

    def refused_cases(self, data):
        flags, bpp, count, cw, ch, _, _, metrics_off, data_off, data_size, cmap_off = header(data)
        n = len(data)
        yield "cmap end one entry past the file", self.put(data, "<I", 32, n - 8 * count + 1)
        yield "cmap end at the file end plus 8", self.put(data, "<I", 32, n - 8 * count + 8)
        yield "cmap offset wrapping 32 bits", self.put(data, "<I", 32, 0xFFFFFFF8)
        yield "cmap offset 0xFFFFFFFF", self.put(data, "<I", 32, 0xFFFFFFFF)
        for off in (1, 4, 20, 35):
            yield f"cmap offset {off} inside the header", self.put(data, "<I", 32, off)
        for k in (0, count - 1):
            for idx in (count, count + 1, 0xFFFF, 0x10000, 0xFFFFFFFF):
                yield f"cmap entry {k} glyph index {idx:#x}", self.put(data, "<I", cmap_off + 8 * k + 4, idx)
        yield "glyph count + 1", self.put(data, "<H", 12, count + 1)
        yield "glyph count 0xFFFF", self.put(data, "<H", 12, 0xFFFF)
        for off, size in ((0xFFFFFFF0, 0x20), (0xFFFFFFFF, 1), (0xFFFFFFFF, 0), (data_off, 0xFFFFFFFF),
                          (data_off, 0x100000000 - data_off), (data_off + 1, data_size), (0, data_size),
                          (35, data_size)):
            yield f"glyph data {off:#x}+{size:#x}", self.put(data, "<II", 24, off, size)
        for w, h in ((0, ch), (cw, 0), (0, 0)):
            yield f"cell {w}x{h}", self.put(data, "<BB", 14, w, h)
        yield "cell 255x255 with glyph count 0xFFFF", self.put(self.put(data, "<BB", 14, 255, 255), "<H", 12, 0xFFFF)

    def test_refused(self):
        for face in self.FACES:
            with open(face, "rb") as fh:
                data = fh.read()
            for name, d in self.refused_cases(data):
                with self.subTest(face=os.path.basename(face), case=name):
                    for what in ("info", "glyphs"):
                        code, _, err = self.run_asan(d, what)
                        self.assertEqual(code, 2, err)
                        self.assertIn("SVF_E_RANGE", err)

    def test_metrics_that_do_not_fit_are_dropped(self):
        for face in self.FACES:
            with open(face, "rb") as fh:
                data = fh.read()
            count = header(data)[2]
            for off in (0, 4, 44, 0xFFFFFFFC, 0x100000000 - 4 * count, 0x100000000 - 4 * count + 4,
                        (len(data) - 4 * count + 4) & ~3, (len(data) + 3) & ~3):    # the table unit's multiples
                d = self.put(data, "<I", 20, off)
                with self.subTest(face=os.path.basename(face), metrics_off=hex(off)):
                    code, out, err = self.run_asan(d, "info")
                    self.assertEqual(code, 0, err)
                    self.assertIn("metrics=0", out.decode())
                    code, out, err = self.run_asan(d, "glyphs")
                    self.assertEqual(code, 0, err)
                    expected = bytearray(expected_glyphs(data))
                    entry = len(expected) // count
                    for k in range(count):          # the same cells, the metrics bytes zero
                        expected[k * entry + 4:k * entry + 8] = bytes(4)
                    self.assertEqual(out, bytes(expected))


SYLLABLES = range(0xAC00, 0xD7A4)
COMPAT_JAMO = range(0x3131, 0x3164)
SYNTH = os.path.join(HERE, "svf_synth.py")
SYNTH_BASE = os.path.join(SVF_DIR, "dos", "NEODG16G.SVF")      # a small valid 16 px jamo set (1x2x6x2x1)
NSQRB16 = os.path.join(SVF_DIR, "jamo-extra", "NSQRB16.SVF")   # a 12 x 12 class v1 face with aliases once v2
# the kinds the current (narrow) C reader refuses: the STD five (valid BIG tables, Task 16 moves them to the narrow-build
# tests) with BAD_KINDS (which ends with the BIG kinds, refused by every reader)
BAD_JSET_KINDS = svf_synth.BAD_KINDS_STD + svf_synth.BAD_KINDS
# the JMAP variants whose fallback is within the narrow row (the hybrid_big ones need SVF_JSET_BIG for it)
NARROW_JMAP_VARIANTS = tuple(v for v in svf_synth.JMAP_VARIANTS if not v.startswith("hybrid_big"))
NARROW_VARIANTS = tuple(v for v in svf_synth.VARIANTS if v not in svf_synth.BIG_VARIANTS)   # the BIG ones: BIG readers only


def jamo_tables(data, big=False):
    """(parsed face, JSET tables or None): the tables when the block passes jamoset.unpack (within the standard limits, or
    the BIG ones for @p big: the C reader built -DSVF_JSET_BIG=1) and every piece number it
    names has a glyph (the engine's JamoGlyphSource::usable), else None (the face loads plain)."""
    f = jamoset.parse_svfn(data)
    if f.jset is None:
        return f, None
    try:
        t = jamoset.unpack(f.jset)
    except ValueError:
        return f, None
    if not big and isinstance(t, jamoset.Tables) and jamoset.needs_big(t):
        return f, None      # unpack reads the BIG counts (PR-16); the C reader without SVF_JSET_BIG refuses
    for n in t.init_piece + t.med_piece + t.fin_piece + t.compat:
        if n != jamoset.BLANK and jamoset.PIECE_BASE + n not in f.glyphs:
            return f, None
    return f, t


def masked(cell, cw, ch, bpp):
    pitch = (cw * bpp + 7) // 8
    used = (cw * bpp) % 8
    last = (0xFF << (8 - used)) & 0xFF if used else 0xFF
    cell = bytearray(cell)
    for y in range(ch):
        cell[y * pitch + pitch - 1] &= last
    return bytes(cell)


def expected_syllables(data, plain=False, jmap=True, fallback=True, big=False):
    """svfdump FACE syllables, from jamoset: U+AC00..D7A3 by jamoset.compose, then U+3131..3163 from the compat piece
    when it is not blank, else the cmap glyph (blank_compat), a zero cell where nothing draws; then the is_jamo byte.
    @p plain: as a plain face whatever the block holds (a JSET version the build does not read). @p jmap False: a JMAP
    block is read through its fallback alone (a build without SVF_JMAP); plain when it has none. @p fallback False: the
    JMAP alone, its fallback unread (the KS-only build: a miss is not composed, a blank compat entry is the cmap glyph).
    @p big: the reader is built -DSVF_JSET_BIG=1 (tables up to 19 x 28 classes, 128/128/64 sets)."""
    f, t = jamo_tables(data, big)
    if isinstance(t, jamoset.Jmap) and not fallback:
        t = copy.copy(t)
        t.fallback = None
    if isinstance(t, jamoset.Jmap) and not jmap:
        t = t.fallback
    if plain:
        t = None
    stride = (f.cell_w * f.bpp + 7) // 8 * f.cell_h
    blank = bytes(stride)
    out = bytearray()
    for cp in SYLLABLES:
        cell = jamoset.compose(f, t, cp) if t else None
        if cell is None:        # no JSET part, or a JMAP that does not list the syllable: the cmap glyph
            cell = f.glyphs.get(cp, blank)
        out += masked(cell, f.cell_w, f.cell_h, f.bpp)
    for k, cp in enumerate(COMPAT_JAMO):
        if t and t.compat[k] != jamoset.BLANK:
            cell = f.glyphs[jamoset.PIECE_BASE + t.compat[k]]
        else:
            cell = f.glyphs.get(cp, blank)
        out += masked(cell, f.cell_w, f.cell_h, f.bpp)
    out.append(1 if t else 0)
    return bytes(out)


def limits_tables(lc, tc, ni, nm, nf):
    """lc x tc classes and ni/nm/nf sets, every class, set and piece used (tools/test_jamoset.py JsetCodec.limits_table)."""
    t = jamoset.Tables(lc, tc, ni, nm, nf)
    t.lead_class = [L % lc for L in range(19)]
    t.tail_class = [0] + [1 + (T - 1) % (tc - 1) for T in range(1, 28)]
    n = lc * 21 * tc
    t.init_set, t.med_set, t.fin_set = [c % ni for c in range(n)], [c % nm for c in range(n)], [c % nf for c in range(n)]
    t.init_piece = [1 + i for i in range(ni * 19)]
    t.med_piece = [1000 + i for i in range(nm * 21)]
    t.fin_piece = [2000 + i for i in range(nf * 27)]
    return t


def synth(out_dir, *args):
    """tools/svf_synth.py ARGS... OUT: the path of the face written."""
    out = os.path.join(out_dir, "synth.svf")
    r = subprocess.run([sys.executable, SYNTH] + list(args) + [out], capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"svf_synth {' '.join(args)} exited {r.returncode}: {r.stderr}")
    return out


class TestFuzzReplayCompat(unittest.TestCase):
    """c/tests/fuzz_replay.py: a compat code point whose compat entry names a piece AND whose glyph table holds another
    glyph is drawn from the piece (spec/SVF.md: "a compatPiece are that piece alone"); the oracle follows the piece."""

    def test_compat_entry_beats_table_glyph(self):
        spec = importlib.util.spec_from_file_location("fuzz_replay", os.path.join(C_DIR, "tests", "fuzz_replay.py"))
        fr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fr)
        exe = build()["svfdump-asan"]
        for version in (1, 2):
            with self.subTest(jset_version=version), tempfile.TemporaryDirectory() as d:
                f, t = svf_synth.load(os.path.join(SVF_DIR, "dos", "NEODG16G.SVF"))
                block, pm = svf_synth.packed(t, version)
                path = os.path.join(d, "base.svf")
                with open(path, "wb") as fh:
                    fh.write(svf_synth.rebuild(f, block, piece_map=pm))
                f, t = svf_synth.load(path)           # the face as that version writes it (pieces renumbered for 2)
                piece = t.compat[0x3157 - 0x3131]
                self.assertNotEqual(piece, jamoset.BLANK)
                self.assertNotIn(0x3157, f.glyphs)
                other = f.glyphs[0xF0000 + piece]
                # a different whole glyph for the same code point, and one for a Hangul syllable the JSET composes
                for cp in (0x3157, 0xAC00):
                    f.glyphs[cp] = bytes(b ^ 0xFF for b in other)
                    f.metrics[cp] = f.metrics[0xF0000 + piece]
                path = os.path.join(d, "both.svf")
                with open(path, "wb") as fh:
                    fh.write(svf_synth.rebuild(f, f.jset))
                self.assertIsNone(fr.check(exe, path))
                # the old oracle (raw table glyph) would have called this a disagreement: the C cells are composed
                with open(path, "rb") as fh:
                    pv = jamoset.parse_svfn(fh.read())
                self.assertEqual(fr.compat_pieces(pv)[0x3157], 0xF0000 + piece)
                out = run_dump(path, "glyphs", asan=True)
                rec = 8 + len(other)
                got = {int.from_bytes(out[i * rec:i * rec + 4], "little"): out[i * rec + 8:(i + 1) * rec]
                       for i in range(len(out) // rec)}
                self.assertEqual(got[0x3157], other)
                self.assertNotEqual(got[0x3157], bytes(pv.glyphs[0x3157]))
                self.assertNotEqual(got[0xAC00], bytes(pv.glyphs[0xAC00]))


# The commit whose narrow (SVF_JSET_BIG=0) object code test_narrow_hot_path_identical compares with. None: the root commit of
# this repository, whose narrow code is the object code of the commit before any BIG code (a0a6144 of the original working
# repository, checked when this repository was cut from it). Re-baseline (set this to a commit, or SVF_HOTPATH_BASELINE for one
# run) when the narrow code changes on purpose.
HOTPATH_BASELINE = None
# The commit test_jmap_nolist_identical compares the LIST=0 JMAP lookup with. None: the root commit, whose LIST=0 code is the
# object code of the commit before the LIST reader (fa76afb of the original working repository). SVF_NOLIST_BASELINE overrides it.
NOLIST_BASELINE = None


def root_commit():
    """The root commit of the checkout (the first line of `git rev-list --max-parents=0 HEAD`), or "HEAD" when there is none."""
    r = subprocess.run(["git", "-C", ROOT, "rev-list", "--max-parents=0", "HEAD"], capture_output=True, text=True)
    lines = r.stdout.split()
    return lines[-1] if r.returncode == 0 and lines else "HEAD"
# The functions of svf_jamo.c that hold the JSET version 1 / 2 lookup and validation (those the compiler does not inline).
HOTPATH_FUNCS = ("svf_jamo_pieces", "pieces_v1", "pieces_v2", "cell_set", "slot_piece", "row_at", "compat_piece",
                 "jset_valid_v1", "jset_valid_v2", "svf__jset_check")


class TestJamo(unittest.TestCase):
    """JSET validation and syllable composition against jamoset.unpack / jamoset.compose."""

    def setUp(self):
        build()
        self.tmp = tempfile.mkdtemp(prefix="svf-jamo-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_syllables_all_jamo_faces(self):
        n = 0
        for face in faces():
            with open(face, "rb") as fh:
                data = fh.read()
            if not header(data)[0] & jamoset.FLAG_JAMO:
                continue
            with self.subTest(face=os.path.relpath(face, ROOT)):
                out = run_dump(face, "syllables")
                self.assertEqual(out[-1], 1, "a repo jamo face loads plain")
                self.assertEqual(out, expected_syllables(data))
                n += 1
        self.assertGreater(n, 0)
        print(f"\n  test_syllables_all_jamo_faces: {n} jamo faces match jamoset.compose", file=sys.stderr)

    def test_plain_face_draws_its_cmap_only(self):
        face = os.path.join(SVF_DIR, "dos", "NEODG16A.SVF")
        with open(face, "rb") as fh:
            data = bytearray(fh.read())
        struct.pack_into("<H", data, 6, header(data)[0] & ~jamoset.FLAG_JAMO)
        path = os.path.join(self.tmp, "plain.svf")
        with open(path, "wb") as fh:
            fh.write(bytes(data))
        out = run_dump(path, "syllables", asan=True)
        self.assertEqual(out, expected_syllables(bytes(data)))
        self.assertEqual(out[-1], 0)

    def test_malformed_jset_falls_back(self):
        with open(SYNTH_BASE, "rb") as fh:
            base = fh.read()
        self.assertIsNotNone(jamo_tables(base)[1])
        # the default host build is BIG (Task 17): the STD count kinds are valid tables to it (test_std_kinds_by_build)
        for kind in svf_synth.BAD_KINDS:
            with self.subTest(kind=kind):
                path = synth(self.tmp, "--jset-bad", kind, "--from", SYNTH_BASE)
                with open(path, "rb") as fh:
                    data = fh.read()
                self.assertIsNone(jamo_tables(data, big=True)[1], "the synthetic block passes jamoset")
                self.assert_plain_everywhere(path, data)

    @staticmethod
    def jset_version_word(data):
        """The version word of the JSET block the header names, 0 when the region is short or not magic JSET."""
        off, size = struct.unpack_from("<II", data, 36)
        if size < 12 or data[off:off + 4] != b"JSET":
            return 0
        return struct.unpack_from("<H", data, off + 4)[0]

    def assert_plain_everywhere(self, path, data, exes=None, unread=False, reads=(1, 2)):
        """@p path loads plain (jamo=0 jset_bad=1) with the glyphs and syllables of jamoset's plain face: mapped
        (sanitizer build), streamed in every STREAM_CONFIGS configuration, and through svfdump-rd8 mapped. @p exes
        names other builds ({'svfdump-asan': path, 'svfdump-rd8': path}). @p unread: the block is valid but of a
        version the build does not read. @p reads: the JSET versions the build reads: a well-formed header of version 1 or 2
        outside it is JSET_UNREAD, anything else that loads plain JSET_BAD (PR-4)."""
        ver = self.jset_version_word(data)
        unread = unread or (ver in (1, 2) and ver not in reads)
        want_glyphs, want_syl = expected_glyphs(data), expected_syllables(data, plain=unread)
        self.assertEqual(want_syl[-1], 0)
        runs = [(("svfdump-asan", ""))] + [("svfdump-asan", cfg) for cfg in STREAM_CONFIGS] + [("svfdump-rd8", "")]
        for exe, cfg in runs:
            exe = (exes or {}).get(exe, exe)
            with self.subTest(exe=os.path.basename(exe), cfg=cfg):
                outs = {}
                for cmd in ("info", "glyphs", "syllables"):
                    code, out, err = stream_dump(path, *([cfg] if cfg else []), cmd, exe=exe)
                    self.assertEqual(code, 0, err)
                    self.assertNotIn("Sanitizer", err)
                    self.assertNotIn("runtime error", err)
                    outs[cmd] = out
                info = dict(kv.split("=") for kv in outs["info"].decode().split())
                self.assertEqual((info["jamo"], info["jset_bad"], info["jset_unread"]), ("0", "0" if unread else "1", "1" if unread else "0"))
                self.assertEqual(outs["glyphs"], want_glyphs)
                self.assertEqual(outs["syllables"], want_syl)

    def assert_jamo_everywhere(self, path, data, exes=None, big=False):
        """@p path loads as a jamo face (jamo=1 jset_bad=0) whose glyphs and syllables are jamoset's, mapped (sanitizer
        build), streamed in every STREAM_CONFIGS configuration (sanitizer build) and through svfdump-rd8 mapped."""
        self.assertIsNotNone(jamo_tables(data, big)[1], "jamoset refuses the block")
        want_glyphs, want_syl = expected_glyphs(data), expected_syllables(data, big=big)
        self.assertEqual(want_syl[-1], 1)
        runs = [(("svfdump-asan", ""))] + [("svfdump-asan", cfg) for cfg in STREAM_CONFIGS] + [("svfdump-rd8", "")]
        for exe, cfg in runs:
            exe = (exes or {}).get(exe, exe)
            with self.subTest(exe=os.path.basename(exe), cfg=cfg):
                outs = {}
                for cmd in ("info", "glyphs", "syllables"):
                    code, out, err = stream_dump(path, *([cfg] if cfg else []), cmd, exe=exe)
                    self.assertEqual(code, 0, err)
                    self.assertNotIn("Sanitizer", err)
                    self.assertNotIn("runtime error", err)
                    outs[cmd] = out
                info = dict(kv.split("=") for kv in outs["info"].decode().split())
                self.assertEqual((info["jamo"], info["jset_bad"]), ("1", "0"))
                self.assertEqual(outs["glyphs"], want_glyphs)
                self.assertEqual(outs["syllables"], want_syl)

    def assert_status(self, path, data, exes, want, syllables, cfgs=None, rd8=True):
        """svfdump info of @p path in every build of @p exes ({'svfdump-asan': path, 'svfdump-rd8': path}) has the
        key=value pairs @p want, and its glyphs and syllables equal jamoset's plain glyphs and @p syllables: mapped and
        streamed (sanitizer build), mapped through SVF_RD8."""
        want_glyphs = expected_glyphs(data)
        runs = [("svfdump-asan", cfg) for cfg in cfgs or ("",) + STREAM_CONFIGS] + \
            ([("svfdump-rd8", "")] if rd8 else [])
        for exe, cfg in runs:
            with self.subTest(path=os.path.basename(path), exe=exe, cfg=cfg):
                outs = {}
                for cmd in ("info", "glyphs", "syllables"):
                    code, out, err = stream_dump(path, *([cfg] if cfg else []), cmd, exe=exes[exe])
                    self.assertEqual(code, 0, err)
                    self.assertNotIn("Sanitizer", err)
                    self.assertNotIn("runtime error", err)
                    outs[cmd] = out
                info = dict(kv.split("=") for kv in outs["info"].decode().split())
                self.assertEqual({k: info[k] for k in want}, want)
                self.assertEqual(outs["glyphs"], want_glyphs)
                self.assertEqual(outs["syllables"], syllables)

    def jmap_face(self, variant=None, bad=None):
        args = ["--jmap-variant", variant] if variant else ["--jmap-bad", bad]
        path = synth(self.tmp, *args, "--from", SYNTH_BASE)
        with open(path, "rb") as fh:
            return path, fh.read()

    def test_status_unread_bits(self):
        """A block of a version whose reader is not compiled is JSET_UNREAD (jset_bad=0); a version 4 block is
        JSET_BAD in every build (PR-4)."""
        unread = {"jamo": "0", "jset_bad": "0", "jset_unread": "1"}
        path, data = self.v2_base()
        exes = build_reader("v1only")
        self.assert_status(path, data, exes, unread, expected_syllables(data, plain=True))
        with open(SYNTH_BASE, "rb") as fh:
            v1 = fh.read()
        self.assert_status(SYNTH_BASE, v1, build_reader("v2only"), unread, expected_syllables(v1, plain=True))
        path = synth(self.tmp, "--jset-bad", "version4", "--from", SYNTH_BASE)
        with open(path, "rb") as fh:
            data = fh.read()
        for exes in (build_reader("v1only"), build_reader("v2only")):
            self.assert_status(path, data, exes, {"jamo": "0", "jset_bad": "1", "jset_unread": "0"},
                               expected_syllables(data, plain=True))

    def test_jmap_unread_plain(self):
        """A JMAP block without a fallback in a build without SVF_JMAP: a plain face, JMAP_UNREAD only."""
        for v, which in itertools.product(("sparse3", "dense4"), ("nojmap", "nojmap_default")):
            exes = build_reader(which)
            path, data = self.jmap_face(v)
            self.assert_status(path, data, exes, {"jamo": "0", "jmap_unread": "1", "jset_bad": "0", "jset_unread": "0",
                                                  "jmap_bad": "0"}, expected_syllables(data, plain=True))

    def test_jmap_unread_fallback(self):
        """A readable fallback is composed from in a build without SVF_JMAP (PR-6), the JMAP part unread; an unreadable
        one leaves a plain face with both bits."""
        path, data = self.jmap_face("hybrid1")
        want = expected_syllables(data, jmap=False)
        self.assertEqual(want[-1], 1)
        for which in ("nojmap", "v1nojmap", "nojmap_default"):
            self.assert_status(path, data, build_reader(which), {"jamo": "1", "jmap_unread": "1", "jset_bad": "0",
                                                                 "jset_unread": "0", "jmap_bad": "0"}, want)
        path, data = self.jmap_face("hybrid2")
        self.assert_status(path, data, build_reader("v1nojmap"),
                           {"jamo": "0", "jmap_unread": "1", "jset_unread": "1", "jset_bad": "0"},
                           expected_syllables(data, plain=True))
        self.assert_status(path, data, build_reader("nojmap"), {"jamo": "1", "jmap_unread": "1", "jset_bad": "0"},
                           expected_syllables(data, jmap=False))

    def test_jmap_norecog(self):
        """Without SVF_JMAP_RECOG a version 3 block is an unknown version: JSET_BAD, plain, no JMAP bit, no fallback use
        (every JMAP variant and bad kind)."""
        exes = build_reader("nojmap_norecog")
        want = {"jamo": "0", "jset_bad": "1", "jmap_unread": "0", "jmap_bad": "0", "jset_unread": "0"}
        for v in svf_synth.JMAP_VARIANTS:
            path, data = self.jmap_face(v)
            self.assert_status(path, data, exes, want, expected_syllables(data, plain=True), cfgs=("", "--stream"))
        for kind in svf_synth.JMAP_BAD_KINDS:
            path, data = self.jmap_face(bad=kind)
            if self.jset_version_word(data) == 3:
                self.assert_status(path, data, exes, want, expected_syllables(data, plain=True), cfgs=("", "--stream"))

    def test_jmap_unread_bad_fallback(self):
        """The guards and verdicts of the recognition (ruling R-M, R-N, M-1): a malformed fallback (bad magic, version 3, or
        a region that ends before its 12 byte header) is JSET_BAD beside JMAP_UNREAD; a fallback whose advance differs
        from the JMAP's, a reserved flag bit, an NS outside R3 are JMAP_BAD alone."""
        bad_fb = {"jamo": "0", "jmap_unread": "1", "jset_bad": "1", "jmap_bad": "0"}
        jmap_bad = {"jamo": "0", "jmap_unread": "0", "jmap_bad": "1", "jset_bad": "0", "jset_unread": "0"}
        kinds = {"jmap_fallback_bad": bad_fb, "jmap_fallback_v3": bad_fb, "jmap_fallback_short": bad_fb,
                 "jmap_fallback_adv": jmap_bad, "jmap_flags": jmap_bad, "jmap_dense_ns": jmap_bad, "jmap_ns0": jmap_bad}
        for which in ("nojmap", "v1nojmap"):
            exes = build_reader(which)
            for kind, want in kinds.items():
                with self.subTest(build=which, kind=kind):
                    path, data = self.jmap_face(bad=kind)
                    self.assert_status(path, data, exes, want, expected_syllables(data, plain=True))
            path, data = self.jmap_face("hybrid1")
            for ns in (11173, 65535):       # NS over 11,172 (a sparse hybrid): R3, JMAP_BAD
                d = bytearray(data)
                off = struct.unpack_from("<I", d, 36)[0]
                struct.pack_into("<H", d, off + 8, ns)
                edited = os.path.join(self.tmp, "ns.svf")
                with open(edited, "wb") as fh:
                    fh.write(bytes(d))
                with self.subTest(build=which, ns=ns):
                    self.assert_status(edited, bytes(d), exes, jmap_bad, expected_syllables(bytes(d), plain=True))

    def test_jmap_recog_region_over_load_max(self):
        """A dense hybrid (a 34 KB / 45 KB region, over SVF__JSET_LOAD_MAX) is read through its fallback when mapped; a
        streamed face loads only the 16 header bytes of such a region and stays plain (JMAP_UNREAD alone), whatever the cache.
        dhybrid1 has a version 1 fallback (dense, 3 byte entries), dhybrid2 version 2 (4 byte entries)."""
        for v, builds in (("dhybrid1", ("nojmap", "v1nojmap")), ("dhybrid2", ("nojmap",))):
            path, data = self.jmap_face(v)
            self.assertGreater(struct.unpack_from("<I", data, 40)[0], JSET_LOAD_MAX)
            for which in builds:
                exes = build_reader(which)
                with self.subTest(variant=v, build=which):
                    self.assert_status(path, data, exes, {"jamo": "1", "jmap_unread": "1", "jset_bad": "0", "jmap_bad": "0"},
                                       expected_syllables(data, jmap=False), cfgs=("",))
                    self.assert_status(path, data, exes, {"jamo": "0", "jmap_unread": "1", "jset_bad": "0", "jmap_bad": "0",
                                                          "jset_unread": "0"},
                                       expected_syllables(data, plain=True), cfgs=STREAM_CONFIGS, rd8=False)
        path, data = self.jmap_face("dhybrid2")      # a version 2 fallback in a build that reads version 1 only
        self.assert_status(path, data, build_reader("v1nojmap"),
                           {"jamo": "0", "jmap_unread": "1", "jset_unread": "1", "jset_bad": "0"},
                           expected_syllables(data, plain=True), cfgs=("",))

    def jmap_status(self, jmap_bad=False):
        return {"jamo": "0", "jmap_bad": "1", "jmap_unread": "0", "jset_bad": "0", "jset_unread": "0"} if jmap_bad else \
            {"jamo": "1", "jmap_bad": "0", "jmap_unread": "0", "jset_bad": "0", "jset_unread": "0"}

    def test_jmap_variants_compose(self):
        """Every JMAP variant in a SVF_JMAP build: a jamo face, syllables and glyphs as jamoset's Jmap composes them, mapped
        (sanitizer build), in every STREAM_CONFIGS configuration and through svfdump-rd8."""
        exes = build_reader("jmap")
        for v in NARROW_JMAP_VARIANTS:
            path, data = self.jmap_face(v)
            want = expected_syllables(data)
            self.assertEqual(want[-1], 1)
            with self.subTest(variant=v):
                self.assert_status(path, data, exes, self.jmap_status(), want)

    def test_jmap_big_fallback_by_build(self):
        """A JMAP whose fallback is a BIG JSET (hybrid_big1 / hybrid_big2: limits_big tables, 16 listed syllables): the default
        build (JMAP + BIG) composes everything; a JMAP build without BIG keeps the JMAP part and calls the fallback JSET_UNREAD
        (the KS-only precedent: listed syllables only); a build without JMAP and with BIG reads the fallback in the JMAP's place
        (JMAP_UNREAD); without JMAP and without BIG the fallback is over the narrow row: JSET_BAD, plain (PR-4). The two no-JMAP builds
        are run mapped: a streamed region longer than their SVF__JSET_LOAD_MAX loads its header only (PR-6: plain, JMAP_UNREAD)."""
        b = build()
        default = {"svfdump-asan": b["svfdump-asan"], "svfdump-rd8": b["svfdump-rd8"]}
        for v in ("hybrid_big1", "hybrid_big2"):
            path, data = self.jmap_face(v)
            self.assertTrue(jamoset.needs_big(jamoset.unpack(jamoset.parse_svfn(data).jset).fallback))
            with self.subTest(variant=v, build="JMAP BIG"):
                self.assert_status(path, data, default, self.jmap_status(), expected_syllables(data, big=True), cfgs=("", "--stream"))
            with self.subTest(variant=v, build="JMAP, no BIG"):
                self.assert_status(path, data, build_reader("jmap"), dict(self.jmap_status(), jset_unread="1"),
                                   expected_syllables(data, fallback=False), cfgs=("", "--stream"))
            with self.subTest(variant=v, build="no JMAP, BIG"):
                self.assert_status(path, data, build_reader("big_nojmap"),
                                   {"jamo": "1", "jmap_unread": "1", "jmap_bad": "0", "jset_bad": "0"},
                                   expected_syllables(data, jmap=False, big=True), cfgs=("",))
            with self.subTest(variant=v, build="no JMAP, no BIG"):
                self.assert_status(path, data, build_reader("nojmap"),
                                   {"jamo": "0", "jmap_unread": "1", "jmap_bad": "0", "jset_bad": "1"},
                                   expected_syllables(data, plain=True), cfgs=("",))

    def test_jmap_bad_kinds_plain(self):
        """Every JMAP bad kind in a SVF_JMAP build: a plain face with JMAP_BAD alone (a region cut under 12 bytes or a
        version word of the JSET kinds are JSET_BAD instead), no sanitizer report."""
        exes = build_reader("jmap")
        for kind in svf_synth.JMAP_BAD_KINDS:
            path, data = self.jmap_face(bad=kind)
            want = self.jmap_status(True)
            if self.jset_version_word(data) != 3:
                want = {"jamo": "0", "jmap_bad": "0", "jset_bad": "1"}
            with self.subTest(kind=kind):
                self.assert_status(path, data, exes, want, expected_syllables(data, plain=True))

    def test_jmap_bad_jset_kinds_unchanged(self):
        """The JSET bad kinds (v1/v2 blocks) in a SVF_JMAP build are Task 5's verdicts: JSET_BAD, no JMAP bit."""
        exes = build_reader("jmap")
        for kind in BAD_JSET_KINDS:
            path = synth(self.tmp, "--jset-bad", kind, "--from", SYNTH_BASE)
            with open(path, "rb") as fh:
                data = fh.read()
            with self.subTest(kind=kind):
                self.assert_status(path, data, exes, {"jamo": "0", "jset_bad": "1", "jmap_bad": "0", "jmap_unread": "0"},
                                   expected_syllables(data, plain=True), cfgs=("", "--stream"))

    def test_jmap_advance_zero(self):
        """adv0 (advance byte 0): a composed syllable and compat jamo advance by the cell width; the other variants by
        the JMAP advance (also after a fallback re-point)."""
        exes = build_reader("jmap")
        for v in ("adv0", "adv0fb", "sparse3", "hybrid1", "hybrid2", "sparse_full"):
            path, data = self.jmap_face(v)
            f = jamoset.parse_svfn(data)
            adv = struct.unpack_from("<B", f.jset, 7)[0]
            for cfg in ("", "--stream"):
                code, out, err = stream_dump(path, *([cfg] if cfg else []), "has", "U+AC00", "U+3131", exe=exes["svfdump-asan"])
                self.assertEqual(code, 0, err)
                for line in out.decode().splitlines():
                    self.assertIn(f"advance={adv or f.cell_w} ", line, (v, line))
            self.assertEqual(adv == 0, v in ("adv0", "adv0fb"))

    def test_jmap_trusted_draws_identically(self):
        """SVF_JSET_TRUSTED with SVF_JMAP keeps R1-R4 only and draws every valid variant as the validating build."""
        a, b = build_reader("jmap"), build_reader("jmap_trusted")
        for v in NARROW_JMAP_VARIANTS:
            path, data = self.jmap_face(v)
            for cmd in ("info", "glyphs", "syllables"):
                self.assertEqual(stream_dump(path, cmd, exe=a["svfdump-asan"])[1:2], stream_dump(path, cmd, exe=b["svfdump-asan"])[1:2], (v, cmd))
            self.assert_status(path, data, b, self.jmap_status(), expected_syllables(data), cfgs=("", "--stream"))
        for kind in ("jmap_short", "jmap_flags", "jmap_pi256_3b", "jmap_zero_pieces", "jmap_ns0", "jmap_dense_ns", "jmap_length",
                     "jmap_region_max", "jmap_fallback_adv", "jmap_fallback_bad", "jmap_fallback_v3", "jmap_fallback_short"):
            path, data = self.jmap_face(bad=kind)
            with self.subTest(kind=kind):
                self.assert_status(path, data, b, self.jmap_status(True), expected_syllables(data, plain=True), cfgs=("",))

    def test_jmap_ks_only_build(self):
        """-DSVF_JMAP=1 -DSVF_JSET_V1=0 -DSVF_JSET_V2=0: a JMAP alone composes; a fallback is JSET_UNREAD and the JMAP part
        stays usable (a miss is not composed, a blank compat entry is the cmap glyph); a plain v1 face is JSET_UNREAD."""
        exes = build_reader("ksonly")
        path, data = self.jmap_face("sparse3")
        self.assert_status(path, data, exes, self.jmap_status(), expected_syllables(data))
        for v in ("hybrid1", "hybrid2", "dhybrid1", "dhybrid2", "adv0fb"):
            path, data = self.jmap_face(v)
            want = dict(self.jmap_status(), jset_unread="1")
            with self.subTest(variant=v):     # dhybrid1/2 (a 34 / 45 KB region, under the 65,534 load max) stream whole too
                self.assert_status(path, data, exes, want, expected_syllables(data, fallback=False))
        self.assert_status(SYNTH_BASE, open(SYNTH_BASE, "rb").read(), exes, {"jamo": "0", "jset_unread": "1", "jset_bad": "0"},
                           expected_syllables(open(SYNTH_BASE, "rb").read(), plain=True))
        path, data = self.jmap_face(bad="jmap_fallback_adv")      # R4's advance is checked where no fallback reader exists
        self.assert_status(path, data, exes, self.jmap_status(True), expected_syllables(data, plain=True))

    def test_jmap_fallback_readers(self):
        """hybrid1 (v1 fallback) and hybrid2 (v2 fallback) in builds that read only one of them: the JMAP part is usable
        either way; the unreadable fallback is JSET_UNREAD and its syllables are not composed."""
        for v in ("hybrid1", "hybrid2"):
            path, data = self.jmap_face(v)
            self.assert_status(path, data, build_reader("jmap"), self.jmap_status(), expected_syllables(data))
        for name, flags in (("jmap_v1", "-DSVF_JMAP=1 -DSVF_JSET_V2=0"), ("jmap_v2", "-DSVF_JMAP=1 -DSVF_JSET_V1=0")):
            READER_FLAGS[name] = flags
        for v, which, unread in (("hybrid1", "jmap_v1", False), ("hybrid2", "jmap_v1", True),
                                 ("hybrid1", "jmap_v2", True), ("hybrid2", "jmap_v2", False)):
            path, data = self.jmap_face(v)
            want = dict(self.jmap_status(), jset_unread="1" if unread else "0")
            with self.subTest(variant=v, build=which):
                self.assert_status(path, data, build_reader(which), want, expected_syllables(data, fallback=not unread),
                                   cfgs=("", "--stream"))

    def test_jmap_reader_off_unchanged(self):
        """A build with -DSVF_JMAP=0 (the host default is 1) gives Task 5's verdicts: a JMAP face is a plain face or its fallback."""
        exes = build_reader("nojmap_default")
        path, data = self.jmap_face("sparse3")
        self.assert_status(path, data, exes, {"jamo": "0", "jmap_unread": "1", "jmap_bad": "0", "jset_bad": "0"},
                           expected_syllables(data, plain=True), cfgs=("", "--stream"))
        path, data = self.jmap_face("hybrid1")
        self.assert_status(path, data, exes, {"jamo": "1", "jmap_unread": "1", "jmap_bad": "0", "jset_bad": "0"},
                           expected_syllables(data, jmap=False), cfgs=("", "--stream"))

    def test_jmap_build_jset_only_and_plain_faces(self):
        """Task 7 bug (svf_jamo_pieces called the JMAP lookup on a face with no JMAP and read out of bounds): in a
        -DSVF_JMAP=1 sanitizer build a JSET-only face (NEODG16G, version 1; its version 2 re-encoding) composes every
        syllable as jamoset does, and a plain face (no JSET, no JMAP) is read without touching a JMAP table: mapped,
        in every STREAM_CONFIGS configuration and through svfdump-rd8, no sanitizer report."""
        exes = build_reader("jmap")
        jset_only = {"jamo": "1", "jmap_bad": "0", "jmap_unread": "0", "jset_bad": "0", "jset_unread": "0"}
        with open(SYNTH_BASE, "rb") as fh:
            v1 = fh.read()
        path2, v2 = self.v2_base()
        for path, data in ((SYNTH_BASE, v1), (path2, v2)):
            want = expected_syllables(data)
            self.assertEqual(want[-1], 1)
            self.assert_status(path, data, exes, jset_only, want)
        plain = os.path.join(SVF_DIR, "dos", "COUSB24.SVF")
        with open(plain, "rb") as fh:
            data = fh.read()
        self.assertIsNone(jamoset.parse_svfn(data).jset)
        self.assert_status(plain, data, exes, {"jamo": "0", "jmap_bad": "0", "jmap_unread": "0", "jset_bad": "0", "jset_unread": "0"},
                           expected_syllables(data, plain=True))
        for cfg in ("",) + STREAM_CONFIGS:      # glyph() of a syllable and a compat jamo on the plain face
            code, out, err = stream_dump(plain, *([cfg] if cfg else []), "has", "U+AC00", "U+3131", exe=exes["svfdump-asan"])
            self.assertEqual(code, 0, err)
            self.assertNotIn("Sanitizer", err)

    def test_jmap_region_max_recog(self):
        """A region of exactly 0xFFFF (the clip of a 65,536 byte region) is never valid: JMAP_BAD in a RECOG build too
        (Task 5 review, Minor 2), for a face with and without a fallback."""
        want = {"jamo": "0", "jmap_bad": "1", "jmap_unread": "0", "jset_bad": "0", "jset_unread": "0"}
        path, data = self.jmap_face(bad="jmap_region_max")
        for which in ("nojmap", "v1nojmap"):
            self.assert_status(path, data, build_reader(which), want, expected_syllables(data, plain=True))

    def test_jmap_region_over_max_reads_only_header(self):
        """G1: a JMAP region of 65,535 bytes (the clip: never valid) whose bytes past the 16-byte header would validate
        cleanly (a real sparse3 block, or a hybrid1 block with FALLBACK, padded with zeros) is refused by R4 before any later byte is read: JMAP_BAD, and a
        streamed face never asks the callback for a byte past the header, a mapped SVF_RD8 face never reads one
        (--forbid exits 3 on a read there). Moving R5/R6 above R4's length test fails this."""
        for variant in ("sparse3", "hybrid1"):      # hybrid1: FALLBACK set, so R4 reads the fallback header right after the cap
            self.over_max_reads_only_header(variant)

    def over_max_reads_only_header(self, variant):
        path0, base = self.jmap_face(variant)
        off, size = struct.unpack_from("<II", base, 36)
        block = base[off:off + size]
        d = bytearray(base)
        d += bytes(-len(d) % 64)
        jset_at = len(d)
        d += block + bytes(0xFFFF - len(block))
        struct.pack_into("<II", d, 36, jset_at, 0xFFFF)
        path = os.path.join(self.tmp, "overmax-%s.svf" % variant)
        with open(path, "wb") as fh:
            fh.write(bytes(d))
        forbid = f"--forbid={jset_at + 16}:{len(d)}"
        want = {"jamo": "0", "jmap_bad": "1", "jmap_unread": "0", "jset_bad": "0", "jset_unread": "0"}
        for which, want_status in (("jmap", want), ("jmap_trusted", want),
                                   ("nojmap", dict(want)), ("v1nojmap", dict(want))):
            exes = build_reader(which)
            for exe, cfgs in (("svfdump-asan", STREAM_CONFIGS), ("svfdump-rd8", ("",) + STREAM_CONFIGS)):
                for cfg in cfgs:
                    with self.subTest(variant=variant, build=which, exe=exe, cfg=cfg):
                        opts = [o for o in (cfg, forbid, "--trace-reads") if o]
                        code, out, err = stream_dump(path, *opts, "info", exe=exes[exe])
                        self.assertEqual(code, 0, err)
                        self.assertNotIn("forbidden", err)
                        self.assertNotIn("Sanitizer", err)
                        info = dict(kv.split("=") for kv in out.decode().split())
                        self.assertEqual({k: info[k] for k in want_status}, want_status)
                        if cfg:
                            self.assertIn(f"svfdump: read {jset_at} 16", err)

    def v2_base(self):
        """SYNTH_BASE re-encoded as JSET version 2 (jamoset.pack, the pieces renumbered): (path, data)."""
        f, t = svf_synth.load(SYNTH_BASE)
        pk = jamoset.pack(t)
        data = svf_synth.rebuild(f, pk.block, "default", pk.piece_map)
        path = os.path.join(self.tmp, "v2base.svf")
        with open(path, "wb") as fh:
            fh.write(data)
        return path, data

    def variant(self, v):
        path = synth(self.tmp, "--jset-variant", v, "--from", SYNTH_BASE)
        with open(path, "rb") as fh:
            return path, fh.read()

    def test_jset2_valid_variants(self):
        """The plain version 2 re-encode of SYNTH_BASE and the alias and bit 7 variants: jamo faces drawing exactly as
        jamoset does, in every configuration; bit 7 draws compat ㄱ from final set 0."""
        path, data = self.v2_base()
        self.assertEqual(struct.unpack_from("<H", jamoset.parse_svfn(data).jset, 4)[0], 2)
        with self.subTest(face="v2 base"):
            self.assert_jamo_everywhere(path, data)
            with open(SYNTH_BASE, "rb") as fh:
                self.assertEqual(run_dump(path, "syllables", asan=True), expected_syllables(fh.read()))
        for v in ("alias", "bit7"):
            with self.subTest(variant=v):
                path, data = self.variant(v)
                self.assert_jamo_everywhere(path, data)
                b = jamoset.decode_jset2(jamoset.parse_svfn(data).jset)
                t = jamo_tables(data)[1]
                if v == "alias":
                    self.assertEqual(b.na, 1)
                else:
                    self.assertEqual(b.compat[0], 0x80)
                    self.assertEqual(t.compat[0], t.fin_piece[0])
                    self.assertNotEqual(t.compat[0], t.init_piece[0])
                    out = run_dump(path, "syllables", asan=True)
                    f = jamoset.parse_svfn(data)
                    stride = (f.cell_w * f.bpp + 7) // 8 * f.cell_h
                    at = len(SYLLABLES) * stride
                    self.assertEqual(out[at:at + stride],
                                     masked(f.glyphs[jamoset.PIECE_BASE + t.fin_piece[0]], f.cell_w, f.cell_h, f.bpp))

    def test_jset2_width_edges(self):
        """W = 14 (12 x 12 classes, 32/24/16 sets, the last cell's fetch past the table) and W = 0 (one set each: no
        set table, the rows at byte 63): every syllable as jamoset composes it, in every configuration."""
        for v, w in (("limits", 14), ("w0", 0)):
            with self.subTest(variant=v):
                path, data = self.variant(v)
                b = jamoset.decode_jset2(jamoset.parse_svfn(data).jset)
                self.assertEqual(jamoset.jset_width(b.ni) + jamoset.jset_width(b.nm) + jamoset.jset_width(b.nf), w)
                self.assert_jamo_everywhere(path, data)

    def jset_at_end(self, data, pad=0):
        """@p data with its JSET block moved to the very end of the file (the header names the new place; the old copy
        stays as dead bytes), followed by @p pad bytes of 0xA5: (bytes, JSET offset, JSET end)."""
        jset = jamoset.parse_svfn(data).jset
        d = bytearray(data)
        d += bytes(-len(d) % 64)
        at = len(d)
        d += jset + b"\xa5" * pad
        struct.pack_into("<II", d, 36, at, len(jset))
        return bytes(d), at, at + len(jset)

    def test_jset2_block_at_file_end(self):
        """The version 2 faces of the width edges and the other variants with the block last in the file: a read one byte
        past it (the W = 14 last-cell fetch, the compat bytes, the presence words) is a read past the allocation. Mapped:
        the exact allocation at every alignment (ASan); mapped through SVF_RD8 and streamed: 64 bytes follow, forbidden
        (the streamed tables buffer holds the offset table after the block: its overreads are not visible)."""
        faces = [("v2 base", self.v2_base())] + [("variant " + v, self.variant(v)) for v in NARROW_VARIANTS] + \
            [("variant " + v, self.variant(v)) for v in svf_synth.BIG_VARIANTS]     # BIG: 45,068 B ends, 7-bit set fields
        for label, (path, data) in faces:
            big = label.split()[-1] in svf_synth.BIG_VARIANTS       # the default host build is BIG (Task 17)
            with self.subTest(face=label):
                moved, at, end = self.jset_at_end(data)
                exact = os.path.join(self.tmp, "end.svf")
                with open(exact, "wb") as fh:
                    fh.write(moved)
                self.assert_jamo_everywhere(exact, moved, big=big)
                want = expected_syllables(moved, big=big)
                for k in (1, 2, 3):
                    code, out, err = stream_dump(exact, f"--face-offset={k}", "syllables", asan=True)
                    self.assertEqual(code, 0, err)
                    self.assertNotIn("Sanitizer", err)
                    self.assertEqual(out, want)
                padded, _, _ = self.jset_at_end(data, 64)
                pad_path = os.path.join(self.tmp, "end-pad.svf")
                with open(pad_path, "wb") as fh:
                    fh.write(padded)
                for exe, cfgs in (("svfdump-asan", STREAM_CONFIGS), ("svfdump-rd8", ("",) + STREAM_CONFIGS)):
                    for cfg in cfgs:
                        opts = [o for o in (cfg, f"--forbid={end}:{len(padded)}") if o]
                        code, out, err = stream_dump(pad_path, *opts, "syllables", exe=exe)
                        self.assertEqual(code, 0, f"{exe} {cfg}: {err}")
                        self.assertNotIn("forbidden", err)
                        self.assertNotIn("Sanitizer", err)
                        self.assertEqual(out, want)

    def test_jset2_overlapping_bases(self):
        """Two initial rows' fresh ranges swapped (out of order): valid in jamoset and in C, drawn alike."""
        path, data = self.variant("overlap")
        b = jamoset.decode_jset2(jamoset.parse_svfn(data).jset)
        self.assertGreater(b.rows["i"][0][0], b.rows["i"][1][0])
        jamoset.unpack(jamoset.parse_svfn(data).jset)
        self.assert_jamo_everywhere(path, data)

    def test_jset2_header_cut(self):
        """A version 2 block cut to 12..15 bytes (inside its 16-byte header): a plain face in every configuration;
        and such a region at the end of a file, followed by bytes no reader may touch, is read only up to its end."""
        for n in range(12, 16):
            with self.subTest(cut=n):
                path = synth(self.tmp, "--jset-cut", str(n), "--from", SYNTH_BASE)
                with open(path, "rb") as fh:
                    data = fh.read()
                self.assertEqual(struct.unpack_from("<I", data, 40)[0], n)
                self.assert_plain_everywhere(path, data)
        path, base = self.v2_base()
        jset = jamoset.parse_svfn(base).jset
        for n in range(12, 16):
            d = bytearray(base)
            d += bytes(-len(d) % 64)
            jset_at = len(d)
            d += jset[:n] + b"\xa5" * 64
            struct.pack_into("<II", d, 36, jset_at, n)
            cut = os.path.join(self.tmp, "cut.svf")
            with open(cut, "wb") as fh:
                fh.write(bytes(d))
            forbid = f"--forbid={jset_at + n}:{len(d)}"
            for exe, cfgs in (("svfdump-asan", STREAM_CONFIGS), ("svfdump-rd8", ("",) + STREAM_CONFIGS)):
                for cfg in cfgs:
                    with self.subTest(cut=n, exe=exe, cfg=cfg):
                        opts = [o for o in (cfg, forbid, "--trace-reads") if o]
                        code, out, err = stream_dump(cut, *opts, "info", exe=exe)
                        self.assertEqual(code, 0, err)
                        self.assertNotIn("forbidden", err)
                        info = dict(kv.split("=") for kv in out.decode().split())
                        self.assertEqual((info["jamo"], info["jset_bad"]), ("0", "1"))
                        if cfg:
                            self.assertIn(f"svfdump: read {jset_at} {n}", err)

    def test_jset2_reader_alone(self):
        """The version 2 reader alone (-DSVF_JSET_V1=0): a version 1 face (SYNTH_BASE) loads plain; the version
        2 re-encode, the variants and every bad kind behave as in the default build (both readers)."""
        exes = build_v2only()
        with open(SYNTH_BASE, "rb") as fh:
            v1 = fh.read()
        self.assertEqual(struct.unpack_from("<H", jamoset.parse_svfn(v1).jset, 4)[0], 1)
        for exe in exes.values():
            with self.subTest(exe=os.path.basename(exe), face="v1"):
                code, out, err = stream_dump(SYNTH_BASE, "info", exe=exe)
                self.assertEqual(code, 0, err)
                info = dict(kv.split("=") for kv in out.decode().split())
                self.assertEqual((info["jamo"], info["jset_bad"], info["jset_unread"]), ("0", "0", "1"))
                code, out, err = stream_dump(SYNTH_BASE, "--stream=4:512", "syllables", exe=exe)
                self.assertEqual(code, 0, err)
                self.assertEqual(out[-1], 0)
        path, data = self.v2_base()
        self.assert_jamo_everywhere(path, data, exes)
        for v in NARROW_VARIANTS:
            with self.subTest(variant=v):
                path, data = self.variant(v)
                self.assert_jamo_everywhere(path, data, exes)
        for kind in BAD_JSET_KINDS:
            with self.subTest(kind=kind):
                path = synth(self.tmp, "--jset-bad", kind, "--from", SYNTH_BASE)
                with open(path, "rb") as fh:
                    self.assert_plain_everywhere(path, fh.read(), exes, reads=(2,))

    def test_decomposition_constants(self):
        """The version 2 reader's syllable decomposition: lead = (s * 14267) >> 23 and vowel = ((s % 588) * 2341) >> 16
        are s // 588 and (s % 588) // 28 for every s below 11,172, in 32 bits."""
        self.assertLess(11171 * 14267, 2 ** 32)
        for s in range(11172):
            self.assertEqual((s * 14267) >> 23, s // 588, s)
            self.assertEqual(((s % 588) * 2341) >> 16, (s % 588) // 28, s)

    def test_jset1_reader_alone(self):
        """-DSVF_JSET_V2=0 (the version 1 reader alone): the version 1 face (SYNTH_BASE) draws as in the default build;
        its version 2 re-encode and the variants load plain."""
        exes = build_v1only()
        with open(SYNTH_BASE, "rb") as fh:
            v1 = fh.read()
        self.assertEqual(struct.unpack_from("<H", jamoset.parse_svfn(v1).jset, 4)[0], 1)
        want = {cmd: run_dump(SYNTH_BASE, cmd, asan=True) for cmd in ("glyphs", "syllables")}
        self.assertEqual(want["syllables"][-1], 1)
        for exe in exes.values():
            for cfg in ("",) + STREAM_CONFIGS:
                with self.subTest(exe=os.path.basename(exe), cfg=cfg, face="v1"):
                    for cmd in ("info", "glyphs", "syllables"):
                        code, out, err = stream_dump(SYNTH_BASE, *([cfg] if cfg else []), cmd, exe=exe)
                        self.assertEqual(code, 0, err)
                        self.assertNotIn("Sanitizer", err)
                        self.assertNotIn("runtime error", err)
                        if cmd == "info":
                            info = dict(kv.split("=") for kv in out.decode().split())
                            self.assertEqual((info["jamo"], info["jset_bad"]), ("1", "0"))
                        else:
                            self.assertEqual(out, want[cmd])
        path, data = self.v2_base()
        self.assert_plain_everywhere(path, data, exes, unread=True)
        for v in NARROW_VARIANTS:
            with self.subTest(variant=v):
                path, data = self.variant(v)
                self.assert_plain_everywhere(path, data, exes, unread=True)
        for kind in BAD_JSET_KINDS:
            with self.subTest(kind=kind):
                path = synth(self.tmp, "--jset-bad", kind, "--from", SYNTH_BASE)
                with open(path, "rb") as fh:
                    self.assert_plain_everywhere(path, fh.read(), exes, reads=(1,))

    def reencoded(self, face, version, name):
        """@p face with its JSET written in @p version (svf_synth --reencode): (path, data)."""
        path = os.path.join(self.tmp, name)
        r = subprocess.run([sys.executable, SYNTH, "--reencode", "--jset-version", str(version), "--from", face, path],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(path, "rb") as fh:
            return path, fh.read()

    def valid_faces(self):
        """The valid faces of the trusted and POP4 comparisons: [(label, path)]."""
        out = [("v1 base", SYNTH_BASE), ("v2 base", self.reencoded(SYNTH_BASE, 2, "v2base.svf")[0])]
        for v in NARROW_VARIANTS:
            path = os.path.join(self.tmp, "variant-%s.svf" % v)
            shutil.copy(self.variant(v)[0], path)
            out.append(("variant " + v, path))
        out.append(("NSQRB16 v1", NSQRB16))
        out.append(("NSQRB16 v2", self.reencoded(NSQRB16, 2, "nsqrb16-v2.svf")[0]))
        return out

    def assert_same_drawing(self, faces, exes):
        """Every face of @p faces draws the same in the default build and in @p exes ({'svfdump-asan': path,
        'svfdump-rd8': path}): info, glyphs and syllables, mapped, in every STREAM_CONFIGS configuration (sanitizer
        builds) and through svfdump-rd8 mapped; every one a jamo face."""
        runs = [("svfdump-asan", "")] + [("svfdump-asan", cfg) for cfg in STREAM_CONFIGS] + [("svfdump-rd8", "")]
        for label, path in faces:
            for exe, cfg in runs:
                with self.subTest(face=label, exe=exe, cfg=cfg):
                    for cmd in ("info", "glyphs", "syllables"):
                        args = ([cfg] if cfg else []) + [cmd]
                        outs = []
                        for x in (exe, exes[exe]):
                            code, out, err = stream_dump(path, *args, exe=x)
                            self.assertEqual(code, 0, err)
                            self.assertNotIn("Sanitizer", err)
                            self.assertNotIn("runtime error", err)
                            outs.append(out)
                        self.assertEqual(outs[0], outs[1], f"{cmd} differs")
                        if cmd == "info":
                            info = dict(kv.split("=") for kv in outs[0].decode().split())
                            self.assertEqual((info["jamo"], info["jset_bad"]), ("1", "0"))

    def test_jset_defaults_per_target(self):
        """svf.h's JSET switch defaults (V1, V2, POP4, TRUSTED, JMAP, BIG, then LIST): host 1/1/1/0/1/1/1 (SVF_JMAP_LIST follows SVF_JMAP unless set explicitly; JMAP on only off AVR, off SVF_SMALL, with __unix__ _WIN32 __APPLE__ __DJGPP__ __EMSCRIPTEN__); AVR 1/0/0/0/0/0; SVF_JSET_BIG follows SVF_JMAP's positive list (PR-13) but is independent of it (-DSVF_JMAP=0 keeps BIG 1); SVF_SMALL POP4 0; an explicit
        -DSVF_JSET_V2=1 or -DSVF_JSET_POP4=1 wins on AVR and over SVF_SMALL; AVR with -DSVF_JSET_V1=0 has no reader."""
        cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("gcc")
        if not cc:
            self.skipTest("no C compiler")
        probe = os.path.join(self.tmp, "defaults.c")
        with open(probe, "w") as fh:
            fh.write('#include "svf.h"\nJSET SVF_JSET_V1 SVF_JSET_V2 SVF_JSET_POP4 SVF_JSET_TRUSTED SVF_JMAP SVF_JSET_BIG SVF_JMAP_LIST\n')

        def defaults(*flags):
            r = subprocess.run([cc, "-E", "-P", "-I", os.path.join(C_DIR, "include")] + list(flags) + [probe],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            line = [ln for ln in r.stdout.splitlines() if ln.startswith("JSET ")][-1]
            return tuple(int(x) for x in line.split()[1:])

        self.assertEqual(defaults(), (1, 1, 1, 0, 1, 1, 1))
        self.assertEqual(defaults("-DSVF_SMALL"), (1, 1, 0, 0, 0, 0, 0))
        self.assertEqual(defaults("-D__AVR__"), (1, 0, 0, 0, 0, 0, 0))
        self.assertEqual(defaults("-U__unix__", "-U__linux__", "-Uunix", "-Ulinux"), (1, 1, 1, 0, 0, 0, 0))
        self.assertEqual(defaults("-D__AVR__", "-DSVF_JMAP=1"), (1, 0, 0, 0, 1, 0, 1))
        self.assertEqual(defaults("-D__AVR__", "-DSVF_JSET_BIG=1"), (1, 0, 0, 0, 0, 1, 0))
        self.assertEqual(defaults("-DSVF_JSET_BIG=0"), (1, 1, 1, 0, 1, 0, 1))
        self.assertEqual(defaults("-D__AVR__", "-DSVF_JSET_V2=1"), (1, 1, 0, 0, 0, 0, 0))
        self.assertEqual(defaults("-D__AVR__", "-DSVF_JSET_V2=1", "-DSVF_JSET_POP4=1"), (1, 1, 1, 0, 0, 0, 0))
        self.assertEqual(defaults("-DSVF_SMALL", "-DSVF_JSET_POP4=1"), (1, 1, 1, 0, 0, 0, 0))
        self.assertEqual(defaults("-DSVF_JSET_TRUSTED=1"), (1, 1, 1, 1, 1, 1, 1))
        self.assertEqual(defaults("-DSVF_JMAP=0"), (1, 1, 1, 0, 0, 1, 0))
        self.assertEqual(defaults("-DSVF_JMAP=1", "-DSVF_JMAP_LIST=0"), (1, 1, 1, 0, 1, 1, 0))
        self.assertEqual(defaults("-D__AVR__", "-DSVF_JSET_V1=0", "-DSVF_JMAP=1"), (0, 0, 0, 0, 1, 0, 1))
        r = subprocess.run([cc, "-E", "-I", os.path.join(C_DIR, "include"), "-D__AVR__", "-DSVF_JSET_V1=0", probe],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0, "AVR with -DSVF_JSET_V1=0 must have no reader")
        self.assertIn("at least one reader", r.stderr)

    def test_trusted_draws_identically(self):
        """-DSVF_JSET_TRUSTED=1 (no JSET validation) draws every valid face exactly as the validating build: SYNTH_BASE
        (v1) and its v2 re-encode, every --jset-variant, NSQRB16 (v1, 12 x 12 classes) and its v2 re-encode. Only valid
        faces are run on it."""
        self.assert_same_drawing(self.valid_faces(), build_reader("trusted"))

    def test_trusted_keeps_region_length_check(self):
        """-DSVF_JSET_TRUSTED=1 skips the table contents only: a JSET size in the header that does not match the block
        (shorter, longer, past the loaded maximum, past the file) opens a plain face or fails the open, with no read past
        the region the build loaded (sanitizer builds, mapped, streamed, rd8), whichever reader the block needs."""
        v1 = NSQRB16
        v2 = self.reencoded(NSQRB16, 2, "nsqrb16-v2.svf")[0]
        for label, path in (("v1", v1), ("v2", v2)):
            with open(path, "rb") as fh:
                base = fh.read()
            real = struct.unpack_from("<I", base, 40)[0]
            for which in ("trusted", "trusted1", "trusted2"):
                exes = build_reader(which)
                for size in (0, 12, 16, 63, real - 1, real + 1, 12322, 13000):
                    if size == real:
                        continue
                    d = bytearray(base)
                    struct.pack_into("<I", d, 40, size)
                    bad = os.path.join(self.tmp, "badsize.svf")
                    with open(bad, "wb") as fh:
                        fh.write(bytes(d))
                    for exe, cfgs in (("svfdump-asan", ("", "--stream", "--stream=4:512")), ("svfdump-rd8", ("",))):
                        for cfg in cfgs:
                            with self.subTest(face=label, build=which, size=size, exe=exe, cfg=cfg):
                                code, out, err = stream_dump(bad, *([cfg] if cfg else []), "info", exe=exes[exe])
                                self.assertNotIn("Sanitizer", err)
                                self.assertNotIn("runtime error", err)
                                if code == 0:
                                    info = dict(kv.split("=") for kv in out.decode().split())
                                    reads = {"trusted": (1, 2), "trusted1": (1,), "trusted2": (2,)}[which]
                                    ver = self.jset_version_word(bytes(d))
                                    unread = ver in (1, 2) and ver not in reads
                                    self.assertEqual((info["jamo"], info["jset_bad"], info["jset_unread"]),
                                                     ("0", "0", "1") if unread else ("0", "1", "0"))
                                    code, out, err = stream_dump(bad, *([cfg] if cfg else []), "syllables", exe=exes[exe])
                                    self.assertEqual(code, 0, err)
                                    self.assertNotIn("Sanitizer", err)
                                    self.assertEqual(out[-1], 0)
                                else:
                                    self.assertIn("SVF_E_", err)

    def test_pop4_off_same(self):
        """-DSVF_JSET_POP4=0 (popcount by bit clearing) draws the version 2 faces as the default build (nibble table)."""
        faces = [(label, path) for label, path in self.valid_faces() if "v1" not in label]
        self.assert_same_drawing(faces, build_reader("pop4off"))

    def test_fuzz_refuses_trusted(self):
        """A fuzz harness compiled with -DSVF_JSET_TRUSTED=1 is a compile error (and compiles without it)."""
        cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("gcc")
        if not cc:
            self.skipTest("no C compiler")
        cmd = [cc, "-std=c99", "-fsyntax-only", "-I", os.path.join(C_DIR, "include"), "-I", os.path.join(C_DIR, "tests"),
               os.path.join(C_DIR, "tests", "fuzz_open.c")]
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run(cmd + ["-DSVF_JSET_TRUSTED=1"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("fuzz builds validate every JSET", r.stderr)

    REAL_FACES = (("NSQRB16", NSQRB16), ("NEODG16G", SYNTH_BASE))

    def real_face_copies(self, scratch):
        """[(label, path, JSET version)] of NSQRB16 (12 x 12 classes, aliases once v2) and NEODG16G (6x2x1, width 0): the
        v1 faces of svf/ and their `svf2to3 --jset-version 2` copies, written into @p scratch."""
        out = []
        for name, face in self.REAL_FACES:
            out.append((name + " v1", face, 1))
            copy = os.path.join(scratch, name + "-v2.SVF")
            r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "svf2to3.py"), face, copy, "--jset-version", "2",
                                "--check"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            out.append((name + " v2", copy, 2))
        return out

    def test_jset_real_faces(self):
        """NSQRB16 and NEODG16G from svf/ (JSET v1) and their generated v2 copies compose all 11,172 syllables as svfline
        composes the v1 face of svf/ (jamo=1 jset_bad=0): mapped and streamed in every STREAM_CONFIGS configuration, in the default build and in
        the single-reader build that reads each version (v1 alone for the v1 faces, v2 alone for the copies)."""
        os.makedirs(os.path.join(C_DIR, "build"), exist_ok=True)
        scratch = tempfile.mkdtemp(prefix="jset-real-", dir=os.path.join(C_DIR, "build"))
        self.addCleanup(shutil.rmtree, scratch, True)
        builds = {1: build_v1only()["svfdump-asan"], 2: build_v2only()["svfdump-asan"]}
        n = 0
        wants = {}
        for name, v1 in self.REAL_FACES:     # the syllables of the v1 face of svf/: a v2 copy must draw the same ones
            with open(v1, "rb") as fh:
                face = svfline.Face(fh.read())
            self.assertTrue(face.tables, name)
            wants[name] = b"".join(masked(face.cell(cp), face.cell_w, face.cell_h, face.bpp) for cp in SYLLABLES)
            blank = bytes((face.cell_w * face.bpp + 7) // 8 * face.cell_h)
            for cp in COMPAT_JAMO:           # then the compat jamo cells (zero where nothing draws) and the is_jamo byte
                try:
                    cell = face.cell(cp)
                except KeyError:
                    cell = blank
                wants[name] += masked(cell, face.cell_w, face.cell_h, face.bpp)
            wants[name] += b"\x01"
        for label, path, version in self.real_face_copies(scratch):
            with open(path, "rb") as fh:
                data = fh.read()
            self.assertEqual(struct.unpack_from("<H", jamoset.parse_svfn(data).jset, 4)[0], version, label)
            want = wants[label.split()[0]]
            for build_name, exe in (("default", "svfdump-asan"), ("v%d-only" % version, builds[version])):
                for cfg in ("",) + STREAM_CONFIGS:
                    with self.subTest(face=label, build=build_name, cfg=cfg):
                        args = ([cfg] if cfg else [])
                        code, out, err = stream_dump(path, *args, "info", exe=exe)
                        self.assertEqual(code, 0, err)
                        info = dict(kv.split("=") for kv in out.decode().split())
                        self.assertEqual((info["jamo"], info["jset_bad"]), ("1", "0"))
                        code, out, err = stream_dump(path, *args, "syllables", exe=exe)
                        self.assertEqual(code, 0, err)
                        self.assertNotIn("Sanitizer", err)
                        self.assertNotIn("runtime error", err)
                        self.assertEqual(out, want)
                        n += 1
        print(f"\n  test_jset_real_faces: {n} face/build/mode runs match svfline", file=sys.stderr)

    def test_reencode_both_versions(self):
        """svf_synth --reencode: --jset-version 1 of NEODG16G keeps its glyphs and JSET byte for byte; --jset-version 2
        writes a 181-byte version 2 block; both draw the same syllables as NEODG16G."""
        with open(SYNTH_BASE, "rb") as fh:
            base = fh.read()
        fb = jamoset.parse_svfn(base)
        _, d1 = self.reencoded(SYNTH_BASE, 1, "re1.svf")
        f1 = jamoset.parse_svfn(d1)
        self.assertEqual(f1.jset, fb.jset)
        self.assertEqual(f1.glyphs, fb.glyphs)
        path2, d2 = self.reencoded(SYNTH_BASE, 2, "re2.svf")
        f2 = jamoset.parse_svfn(d2)
        self.assertEqual(len(f2.jset), 181)
        self.assertEqual(struct.unpack_from("<H", f2.jset, 4)[0], 2)
        want = run_dump(SYNTH_BASE, "syllables", asan=True)
        self.assertEqual(want[-1], 1)
        self.assertEqual(run_dump(os.path.join(self.tmp, "re1.svf"), "syllables", asan=True), want)
        self.assertEqual(run_dump(path2, "syllables", asan=True), want)

    def test_malformed_jset1_falls_back(self):
        """BASE's twelve version 1 bad kinds (svf_synth --jset-version 1 --jset-bad K): refused by jamoset (unpack, or
        the piece without a glyph) and a plain face in the default and the v1-only builds, mapped, streamed in every
        configuration and through svfdump-rd8."""
        v1only = build_v1only()
        for kind in svf_synth.BAD_KINDS_V1:
            with self.subTest(kind=kind):
                path = synth(self.tmp, "--jset-version", "1", "--jset-bad", kind, "--from", SYNTH_BASE)
                with open(path, "rb") as fh:
                    data = fh.read()
                std = kind in svf_synth.BAD_KINDS_STD       # a valid table to the BIG (default) build, bad to the v1-only (narrow) one
                self.assertIsNone(jamo_tables(data)[1], "the synthetic block passes jamoset")
                jset = jamoset.parse_svfn(data).jset
                if kind not in ("missing_piece", "lc13", "tc13", "ni33", "nm25", "nf17") and jset is not None:
                    with self.assertRaises(ValueError):     # the count kinds are valid BIG tables to unpack (PR-16)
                        jamoset.unpack(jset)
                if kind not in ("version", "short") and jset is not None:
                    self.assertEqual(struct.unpack_from("<H", jset, 4)[0], 1)
                if not std:
                    self.assert_plain_everywhere(path, data)
                self.assert_plain_everywhere(path, data, v1only, reads=(1,))

    def test_set_limits_32_24_16(self):
        """A 12x12 class face with 32/24/16 sets (the narrow format maximum, the build without SVF_JSET_BIG): the C library
        composes every syllable as jamoset.compose does, streamed and mapped; one set more of any kind is a bad JSET, a
        plain face (it is a valid face to the BIG build: test_std_kinds_by_build)."""
        def limits_face(ni, nm, nf):
            # over the limits pack refuses: the block is pack's at 32/24/16 with the counts widened (Jset2 rows copied)
            t = limits_tables(12, 12, min(ni, 32), min(nm, 24), min(nf, 16))
            glyphs = [(jamoset.PIECE_BASE + n, bytes([n & 0xFF, (n >> 8) | 0x80, (n * 7) & 0xFF]) + bytes(5), 8, 0, 8)
                      for n in sorted(set(t.init_piece + t.med_piece + t.fin_piece))]
            pk = jamoset.pack(t)
            block = pk.block
            if (ni, nm, nf) != (t.ni, t.nm, t.nf):
                block = jamoset.encode_jset2(svf_synth.widened2(jamoset.decode_jset2(block), ni=ni, nm=nm, nf=nf))
            return jamoset.write_svfn(8, 8, 7, jamoset.renumber_glyphs(glyphs, pk.piece_map), block)
        narrow = build_reader("narrow")["svfdump-asan"]
        path = os.path.join(self.tmp, "limits.svf")
        with open(path, "wb") as fh:
            fh.write(limits_face(32, 24, 16))
        info = dict(kv.split("=") for kv in stream_dump(path, "info", exe=narrow)[1].decode().split())
        self.assertEqual((info["jamo"], info["jset_bad"]), ("1", "0"))
        with open(path, "rb") as fh:
            data = fh.read()
        self.assertEqual(len(jamoset.parse_svfn(data).jset), 5782)
        want = expected_syllables(data)
        self.assertEqual(want[-1], 1)
        self.assertEqual(stream_dump(path, "syllables", exe=narrow)[1], want)
        for cfg in STREAM_CONFIGS:
            code, out, err = stream_dump(path, cfg, "syllables", exe=narrow)
            self.assertEqual(code, 0, err)
            self.assertEqual(out, want)
        for dims in ((33, 24, 16), (32, 25, 16), (32, 24, 17)):
            with self.subTest(dims=dims):
                bad = os.path.join(self.tmp, "bad.svf")
                with open(bad, "wb") as fh:
                    fh.write(limits_face(*dims))
                info = dict(kv.split("=") for kv in stream_dump(bad, "info", exe=narrow)[1].decode().split())
                self.assertEqual((info["jamo"], info["jset_bad"]), ("0", "1"))
                self.assertEqual(stream_dump(bad, "syllables", exe=narrow)[1][-1], 0)

    # SVF_JSET_BIG (Task 16): 19 x 28 classes, 128/128/64 sets in place in versions 1 and 2

    def limits_big_face(self, variant="limits_big", version=2):
        path = synth(self.tmp, "--jset-variant", variant, "--jset-version", str(version), "--from", SYNTH_BASE)
        keep = os.path.join(self.tmp, "%s-v%d.svf" % (variant, version))    # synth writes one file name: keep each face
        os.replace(path, keep)
        with open(keep, "rb") as fh:
            return keep, fh.read()

    def test_set_limits_big(self):
        """limits_big (19 x 28 classes, 128/128/64 sets, every slot its own piece) in version 2 and its version 1
        re-encode, and limits_big_alias (version 2, every slot an alias): jamo=1 and all 11,172 syllables + 51 compat
        jamo as jamoset.compose draws them, mapped, in every STREAM_CONFIGS configuration and through rd8, on the BIG
        build; the readers of one version alone read their own (the other is JSET_UNREAD); the narrow build refuses all."""
        big, big_v1, big_v2, narrow = (build_reader(w) for w in ("big", "big_v1", "big_v2", "narrow"))
        for variant, version, readers in (("limits_big", 2, (big, big_v2)), ("limits_big", 1, (big, big_v1)),
                                          ("limits_big_alias", 2, (big, big_v2))):
            path, data = self.limits_big_face(variant, version)
            self.assertEqual(struct.unpack_from("<H", jamoset.parse_svfn(data).jset, 4)[0], version)
            for exes in readers:
                with self.subTest(variant=variant, version=version, build=exes["svfdump-asan"]):
                    self.assert_jamo_everywhere(path, data, exes, big=True)
            with self.subTest(variant=variant, version=version, build="narrow"):
                self.assert_plain_everywhere(path, data, narrow)
        # the other version's reader alone: well-formed, unread
        for variant, version, exes in (("limits_big", 2, big_v1), ("limits_big", 1, big_v2)):
            path, data = self.limits_big_face(variant, version)
            self.assert_status(path, data, exes, {"jamo": "0", "jset_bad": "0", "jset_unread": "1"},
                               expected_syllables(data, plain=True, big=True))

    def test_big_plus_one_plain(self):
        """One past each BIG cap (lc20 tc29 ni129 nm129 nf65, versions 1 and 2): jamo=0 jset_bad=1 on the BIG build."""
        exes = build_reader("big")
        for version in (1, 2):
            for kind in svf_synth.BAD_KINDS_BIG:
                with self.subTest(kind=kind, version=version):
                    path = synth(self.tmp, "--jset-bad", kind, "--jset-version", str(version), "--from", SYNTH_BASE)
                    with open(path, "rb") as fh:
                        data = fh.read()
                    self.assert_plain_everywhere(path, data, exes)

    def test_big_compat_high_sets(self):
        """The BIG variants' compat entries held only by high sets (svf_synth.big_tables): ㄴ initial set 64 (0x40), ㄳ final set 63
        (0x3F), ㄱ final set 63 in the bit 7 form (0xBF), ㅏ medial set 100 (0x64) draw their piece on the BIG build (a reader that
        masks the set to 5 bits, or keeps the narrow bit 5-6 test, fails); the narrow build refuses the faces. One past: ㄱ as
        0x80 | 64 (a final set 64 of NF = 64), ㅏ as 0x80 (bit 7 on a vowel), ㄳ as 0x80 (bit 7 on a cluster) are plain on the
        BIG build."""
        big, narrow = build_reader("big"), build_reader("narrow")
        for variant, version in (("limits_big", 2), ("limits_big", 1), ("limits_big_alias", 2)):
            path, data = self.limits_big_face(variant, version)
            t = jamoset.unpack(jamoset.parse_svfn(data).jset)
            self.assertEqual(len({t.compat[k] for k in (0, 2, 3, 30)}), 4)
            if version == 2:
                self.assertEqual(list(jamoset.parse_svfn(data).jset[-51:][:4]), [0xBF, 0, 0x3F, 0x40])
                self.assertEqual(jamoset.parse_svfn(data).jset[-51 + 30], 0x64)
            with self.subTest(variant=variant, version=version):
                self.assert_jamo_everywhere(path, data, big, big=True)
                self.assert_plain_everywhere(path, data, narrow)
        path, data = self.limits_big_face("limits_big", 2)
        off, size = struct.unpack_from("<II", data, 36)
        for k, byte in ((0, 0x80 | 64), (30, 0x80), (2, 0x80)):
            with self.subTest(compat=k, byte=hex(byte)):
                bad = bytearray(data)
                bad[off + size - 51 + k] = byte
                bad_path = os.path.join(self.tmp, "badcompat.svf")
                with open(bad_path, "wb") as fh:
                    fh.write(bytes(bad))
                self.assert_plain_everywhere(bad_path, bytes(bad), big)

    def test_std_kinds_by_build(self):
        """lc13 tc13 ni33 nm25 nf17 (one past the narrow caps, versions 1 and 2): plain (jset_bad=1) on the narrow build,
        a jamo face on the BIG build."""
        narrow, big = build_reader("narrow"), build_reader("big")
        for version in (1, 2):
            for kind in svf_synth.BAD_KINDS_STD:
                with self.subTest(kind=kind, version=version):
                    path = synth(self.tmp, "--jset-bad", kind, "--jset-version", str(version), "--from", SYNTH_BASE)
                    with open(path, "rb") as fh:
                        data = fh.read()
                    self.assert_plain_everywhere(path, data, narrow)
                    self.assert_jamo_everywhere(path, data, big, big=True)

    def test_big_trusted_draws_identically(self):
        """SVF_JSET_TRUSTED with SVF_JSET_BIG draws what the validating BIG build draws, on the valid faces and the
        limits_big ones (versions 1 and 2, the alias form)."""
        trusted, big = build_reader("big_trusted"), build_reader("big")
        with open(SYNTH_BASE, "rb") as fh:
            faces_ = [(SYNTH_BASE, fh.read())]
        base2 = self.v2_base()
        keep = os.path.join(self.tmp, "base2.svf")
        os.replace(base2[0], keep)
        faces_.append((keep, base2[1]))
        faces_ += [self.limits_big_face(v, ver) for v, ver in (("limits_big", 2), ("limits_big", 1), ("limits_big_alias", 2))]
        for path, data in faces_:
            with self.subTest(face=os.path.basename(path), size=len(data)):
                self.assert_jamo_everywhere(path, data, trusted, big=True)
                for cfg in ("", "--stream"):
                    a = stream_dump(path, *([cfg] if cfg else []), "syllables", exe=trusted["svfdump-asan"])
                    b = stream_dump(path, *([cfg] if cfg else []), "syllables", exe=big["svfdump-asan"])
                    self.assertEqual(a[1], b[1])

    def test_big_without_jmap(self):
        """-DSVF_JSET_BIG=1 -DSVF_JMAP=0 (the region cap is the largest BIG block, 47,373 B): limits_big faces still compose; the
        version 2 reader alone (the cap is the version 2 maximum, 45,068 B: limits_big_alias is exactly at it) reads the version 2
        faces, the version 1 face is JSET_UNREAD."""
        exes = build_reader("big_nojmap")
        for variant, version in (("limits_big", 2), ("limits_big", 1), ("limits_big_alias", 2)):
            path, data = self.limits_big_face(variant, version)
            with self.subTest(variant=variant, version=version):
                self.assert_jamo_everywhere(path, data, exes, big=True)
        exes = build_reader("big_v2_nojmap")
        for variant, version in (("limits_big", 2), ("limits_big_alias", 2)):
            path, data = self.limits_big_face(variant, version)
            with self.subTest(variant=variant, version=version, build="v2 only"):
                self.assert_jamo_everywhere(path, data, exes, big=True)
        path, data = self.limits_big_face("limits_big", 1)
        self.assert_status(path, data, exes, {"jamo": "0", "jset_bad": "0", "jset_unread": "1"},
                           expected_syllables(data, plain=True, big=True))

    def arm_functions(self, gcc, objdump, c_dir, tag, flags):
        """{function: instruction list} of svf_jamo.o of @p c_dir compiled with cortex-m0plus -Os -ffunction-sections
        -DSVF_JSET_BIG=0 and @p flags."""
        obj = os.path.join(self.tmp, "hot-%s.o" % tag)
        r = subprocess.run([gcc, "-mcpu=cortex-m0plus", "-mthumb", "-Os", "-ffunction-sections", "-std=c99"] + flags.split() +
                           ["-DSVF_JSET_BIG=0", "-I" + os.path.join(c_dir, "include"), "-c", os.path.join(c_dir, "src", "svf_jamo.c"),
                            "-o", obj], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        dis = subprocess.run([objdump, "-d", "--no-show-raw-insn", obj], capture_output=True, text=True).stdout
        funcs, cur = {}, None
        for line in dis.splitlines():
            m = re.match(r"^[0-9a-f]+ <(\w+)>:$", line)
            if m:
                cur = funcs.setdefault(m.group(1), [])
            elif cur is not None and line.strip():
                cur.append(re.sub(r"^\s*[0-9a-f]+:\s*", "", line))
        return funcs

    def test_jmap_nolist_identical(self):
        """-DSVF_JMAP=1 -DSVF_JMAP_LIST=0: jmap_pieces, jmap_fields and svf_jamo_pieces are the object code of NOLIST_BASELINE
        (before LIST); jmap_valid changes by design (R1' mask, the LIST arm to bad) and is not compared."""
        gcc = os.path.join(os.environ.get("OPT", os.path.expanduser("~/opt")), "arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-gcc")
        objdump = os.path.join(os.path.dirname(gcc), "arm-none-eabi-objdump")
        missing = [x for x in (gcc, objdump) if not os.path.exists(x)] + [x for x in ("git", "tar") if not shutil.which(x)]
        if missing:
            self.skipTest("SKIPPED, the LIST=0 identity is NOT checked: missing " + ", ".join(missing))
        nolist_baseline = os.environ.get("SVF_NOLIST_BASELINE") or NOLIST_BASELINE or root_commit()
        base = os.path.join(self.tmp, "base")
        os.mkdir(base)
        r = subprocess.run("git -C '%s' archive '%s' c | tar -x -C '%s'" % (ROOT, nolist_baseline, base), shell=True,
                           capture_output=True, text=True)
        if r.returncode != 0:
            why = "baseline commit %s not in the repository (%s)" % (nolist_baseline, r.stderr.strip())
            if os.environ.get("SVF_HOTPATH_REQUIRE") == "1":
                self.fail("the LIST=0 identity cannot be checked: " + why)
            self.skipTest("SKIPPED, the LIST=0 identity is NOT checked: " + why)
        new = self.arm_functions(gcc, objdump, C_DIR, "lnew", "-DSVF_JMAP=1 -DSVF_JMAP_LIST=0")
        old = self.arm_functions(gcc, objdump, os.path.join(base, "c"), "lold", "-DSVF_JMAP=1 -DSVF_JMAP_LIST=0")  # LIST=0 is void before LIST
        found = []
        for n in ("jmap_pieces", "jmap_fields", "svf_jamo_pieces"):
            with self.subTest(function=n):
                self.assertEqual(n in new, n in old, "inlined or present on one side only")
                if n in new:
                    found.append(n)
                    self.assertEqual(new[n], old[n])
        self.assertIn("svf_jamo_pieces", found)
        self.assertFalse([n for n in new if n.startswith("jlist_")], "a jlist_ symbol with SVF_JMAP_LIST=0")
        print("\n  LIST=0 vs %s: identical (%s)" % (nolist_baseline, ", ".join(found)), file=sys.stderr)

    def test_jmap_list_compose(self):
        """Every LIST variant but list_big on the LIST build: a jamo face, syllables (11,172 + 51) and glyphs as jamoset composes them."""
        exes = build_reader("list")
        for v in svf_synth.LIST_VARIANTS:
            if v == "list_big":
                continue
            path, data = self.jmap_face(v)
            want = expected_syllables(data)
            stride = ((header(data)[3] * header(data)[1] + 7) // 8) * header(data)[4]
            self.assertEqual((len(want), want[-1]), ((11172 + 51) * stride + 1, 1))
            with self.subTest(variant=v):
                self.assert_status(path, data, exes, self.jmap_status(), want)

    def test_jmap_list_bad_kinds_plain(self):
        """Every LIST bad kind on the LIST build: a plain face with JMAP_BAD alone, no sanitizer report."""
        exes = build_reader("list")
        for kind in svf_synth.LIST_BAD_KINDS:
            path, data = self.jmap_face(bad=kind)
            with self.subTest(kind=kind):
                self.assert_status(path, data, exes, self.jmap_status(True), expected_syllables(data, plain=True))

    def test_jmap_list_search_edges(self):
        """list_max and list_nofb: the syllables at s = 0, 1, 11,170, 11,171 and each key +- 1 equal the reference, one message per code point."""
        exes = build_reader("list")
        for v in ("list_max", "list_nofb"):
            path, data = self.jmap_face(v)
            keys = sorted(jamoset.unpack(jamoset.parse_svfn(data).jset).entries)
            stride = ((header(data)[3] * header(data)[1] + 7) // 8) * header(data)[4]
            want = expected_syllables(data)
            edges = sorted({s for s in [0, 1, 11170, 11171] + [k + d for k in keys for d in (-1, 0, 1)] if 0 <= s <= 11171})
            runs = [("svfdump-asan", cfg) for cfg in ("",) + STREAM_CONFIGS] + [("svfdump-rd8", "")]
            for exe, cfg in runs:
                code, out, err = stream_dump(path, *([cfg] if cfg else []), "syllables", exe=exes[exe])
                self.assertEqual(code, 0, err)
                self.assertNotIn("Sanitizer", err)
                for s in edges:
                    self.assertEqual(out[s * stride:(s + 1) * stride], want[s * stride:(s + 1) * stride],
                                     "%s %s %s U+%04X" % (v, exe, cfg or "mapped", 0xAC00 + s))

    def test_jmap_list_max(self):
        """list_max (NS 255, region 2,158): mapped and --stream=4:512 compose."""
        exes = build_reader("list")
        path, data = self.jmap_face("list_max")
        self.assertEqual(struct.unpack_from("<I", data, 40)[0], 2158)
        self.assert_status(path, data, exes, self.jmap_status(), expected_syllables(data), cfgs=("", "--stream=4:512"))

    def test_jmap_list_advance(self):
        """A listed syllable (a whole glyph and a recombination; on list1 U+3131 too) advance by the JSET advance 16 (byte 7)."""
        exes = build_reader("list")
        for v in ("list1", "list_nofb"):
            path, data = self.jmap_face(v)
            jm = jamoset.unpack(jamoset.parse_svfn(data).jset)
            self.assertEqual(jm.advance, 16)
            keys = sorted(jm.entries)
            cps = ["U+%04X" % (0xAC00 + k) for k in (keys[:2] if v == "list1" else keys[:1])]
            if v == "list1":      # list_nofb has no compat jamo at all (blank entries, no fallback, no cmap glyph)
                cps.append("U+3131")
            for cfg in ("", "--stream"):
                code, out, err = stream_dump(path, *([cfg] if cfg else []), "has", *cps, exe=exes["svfdump-asan"])
                self.assertEqual(code, 0, err)
                lines = out.decode().splitlines()
                self.assertEqual(len(lines), len(cps))
                for line in lines:
                    self.assertIn("has=1 advance=16 ", line, (v, line))

    def test_jmap_list_big_fallback_by_build(self):
        """list_big: the LIST build (BIG pinned off) keeps the LIST and calls the fallback JSET_UNREAD; the BIG LIST build composes."""
        path, data = self.jmap_face("list_big")
        self.assertTrue(jamoset.needs_big(jamoset.unpack(jamoset.parse_svfn(data).jset).fallback))
        self.assert_status(path, data, build_reader("list"), dict(self.jmap_status(), jset_unread="1"),
                           expected_syllables(data, fallback=False))
        self.assert_status(path, data, build_reader("list_big"), self.jmap_status(), expected_syllables(data, big=True))

    def test_jmap_list_trusted(self):
        """SVF_JSET_TRUSTED keeps the header rules: it draws every variant as the validating build and runs the content-rule kinds clean."""
        a, b = build_reader("list"), build_reader("list_trusted")
        for v in svf_synth.LIST_VARIANTS:
            path, data = self.jmap_face(v)
            for cmd in ("info", "glyphs", "syllables"):
                ra, rb = (stream_dump(path, cmd, exe=x["svfdump-asan"]) for x in (a, b))
                self.assertEqual((ra[0], rb[0]), (0, 0), (v, cmd, ra[2], rb[2]))
                self.assertEqual(ra[1], rb[1], (v, cmd))
        for kind in svf_synth.LIST_CONTENT_KINDS:
            path, data = self.jmap_face(bad=kind)
            for cmd in ("info", "glyphs", "syllables"):
                code, out, err = stream_dump(path, cmd, exe=b["svfdump-asan"])
                with self.subTest(kind=kind, cmd=cmd):
                    self.assertEqual(code, 0, err)
                    self.assertNotIn("Sanitizer", err)
                    self.assertNotIn("runtime error", err)

    def test_jmap_list_nolist_trusted(self):
        """-DSVF_JMAP_LIST=0 -DSVF_JSET_TRUSTED=1: every LIST variant and bad kind runs clean (exit 0, no sanitizer line) and prints what the
        validating LIST=0 build prints. Observed: the same bytes for all of them (the LIST=0 arm applies the header rules only, and a
        TRUSTED build keeps R1-R4 for the block and its fallback header; the content rules are not checked in either build)."""
        a, b = build_reader("nolist"), build_reader("nolist_trusted")
        for label in svf_synth.LIST_VARIANTS + svf_synth.LIST_BAD_KINDS:
            path, data = self.jmap_face(label) if label in svf_synth.LIST_VARIANTS else self.jmap_face(bad=label)
            for cmd in ("info", "glyphs", "syllables"):
                ra, rb = (stream_dump(path, cmd, exe=x["svfdump-asan"]) for x in (a, b))
                with self.subTest(face=label, cmd=cmd):
                    self.assertEqual(rb[0], 0, rb[2])
                    self.assertNotIn("Sanitizer", rb[2])
                    self.assertNotIn("runtime error", rb[2])
                    self.assertEqual(ra[1], rb[1])

    def test_jmap_list_ns256_self_consistent(self):
        """A block that is consistent in every way except L3: NS 256 (256 strictly increasing keys, F = 118 + 8 * 256 = 2,166, length F, no
        fallback), made from list_max by one inserted entry. L3 alone refuses it (R4 agrees with it): JMAP_BAD on the LIST, LIST=0 and
        RECOG builds, JSET_BAD where version 3 is unknown. Pins the 255 bound of jmap_valid and of the recognition separately from R4."""
        path, data = self.jmap_face("list_max")
        pf = jamoset.parse_svfn(data)
        jset = bytearray(pf.jset)
        ns = struct.unpack_from("<H", jset, 8)[0]
        self.assertEqual((ns, len(jset)), (255, 2158))
        keys = [struct.unpack_from("<H", jset, 118 + 8 * i)[0] for i in range(ns)]
        gap = next(i for i in range(1, ns) if keys[i] - keys[i - 1] > 1)
        entry = bytearray(jset[118 + 8 * gap:126 + 8 * gap])
        struct.pack_into("<H", entry, 0, keys[gap] - 1)
        jset[118 + 8 * gap:118 + 8 * gap] = entry
        struct.pack_into("<H", jset, 8, 256)
        new_keys = [struct.unpack_from("<H", jset, 118 + 8 * i)[0] for i in range(256)]
        self.assertEqual((len(jset), new_keys), (2166, sorted(set(new_keys))))
        self.assertEqual(len(jset), 118 + 8 * 256)
        path = os.path.join(self.tmp, "ns256.svf")
        data = svf_synth.rebuild(pf, bytes(jset))
        with open(path, "wb") as fh:
            fh.write(data)
        base = {"jamo": "0", "jmap_bad": "0", "jmap_unread": "0", "jset_bad": "0", "jset_unread": "0"}
        for which, bits in (("list", dict(base, jmap_bad="1")), ("nolist", dict(base, jmap_bad="1")), ("nojmap", dict(base, jmap_bad="1")),
                            ("nojmap_norecog", dict(base, jset_bad="1"))):
            with self.subTest(build=which):
                self.assert_status(path, data, build_reader(which), bits, expected_syllables(data, plain=True), cfgs=("",))

    def test_jmap_list_miss_draws_cmap_glyph(self):
        """A LIST without fallback: an unlisted syllable with a precomposed cmap glyph draws that glyph (design 2.3), a listed one the LIST's
        composition even when the cmap also holds a glyph for it, an unlisted one without a glyph stays blank. list_nofb plus two cmap syllables."""
        path, data = self.jmap_face("list_nofb")
        pf = jamoset.parse_svfn(data)
        listed = next(iter(jamoset.unpack(pf.jset).entries))
        stride = ((pf.cell_w * pf.bpp + 7) // 8) * pf.cell_h
        extra = {0xAC00 + 1: bytes([0x5A] * stride), 0xAC00 + listed: bytes([0xA5] * stride)}
        self.assertFalse(set(extra) & set(pf.glyphs))
        for cp, cell in extra.items():
            pf.glyphs[cp] = cell
            pf.metrics[cp] = (pf.cell_w, 0, pf.cell_w)
        data = svf_synth.rebuild(pf, pf.jset)
        path = os.path.join(self.tmp, "nofb_cmap.svf")
        with open(path, "wb") as fh:
            fh.write(data)
        want = expected_syllables(data)
        self.assertEqual(want[1 * stride:2 * stride], masked(extra[0xAC01], pf.cell_w, pf.cell_h, pf.bpp))
        self.assertNotEqual(want[listed * stride:(listed + 1) * stride], masked(extra[0xAC00 + listed], pf.cell_w, pf.cell_h, pf.bpp))
        self.assertEqual(want[2 * stride:3 * stride], bytes(stride))
        exe = build_reader("list")["svfdump-asan"]
        for cfg in ("",) + STREAM_CONFIGS:
            with self.subTest(cfg=cfg or "mapped"):
                code, out, err = stream_dump(path, *([cfg] if cfg else []), "syllables", exe=exe)
                self.assertEqual(code, 0, err)
                bad = next((i for i in range(len(want)) if out[i:i + 1] != want[i:i + 1]), None) if out != want else None
                self.assertTrue(out == want, "syllables dump differs at byte %s (syllable %s), lengths %d / %d" % (
                    bad, None if bad is None else bad // stride, len(out), len(want)))
                self.assertNotIn("Sanitizer", err)
                code, out, err = stream_dump(path, *([cfg] if cfg else []), "glyphs", exe=exe)
                self.assertEqual(code, 0, err)
                rec = 8 + stride
                cells = {struct.unpack_from("<I", out, o)[0]: out[o + 8:o + rec] for o in range(0, len(out), rec)}
                self.assertEqual(cells[0xAC01], extra[0xAC01])      # the cmap glyph itself, not a composition

    def test_jmap_list_ks_only(self):
        """The KS-only LIST build: the fallback is JSET_UNREAD, the listed syllables only."""
        path, data = self.jmap_face("list1")
        self.assert_status(path, data, build_reader("list_ks"), dict(self.jmap_status(), jset_unread="1"),
                           expected_syllables(data, fallback=False))

    def test_jmap_list_status_matrix(self):
        """Task 6's matrix: every LIST variant and bad kind on the LIST, LIST=0, RECOG (nojmap) and no-RECOG builds (BIG pinned
        off), mapped and --stream=4:512, status bits and syllables per cell (see the plan)."""
        builds = {w: build_reader(w) for w in ("list", "nolist", "nojmap", "nojmap_norecog")}
        base = {"jamo": "0", "jmap_bad": "0", "jmap_unread": "0", "jset_bad": "0", "jset_unread": "0"}
        st = lambda **kw: dict(base, **kw)
        unread = st(jmap_unread="1")                                    # plain, JMAP_UNREAD alone
        unread_fb = st(jamo="1", jmap_unread="1")                       # the fallback composes
        bad = st(jmap_bad="1")
        norecog = st(jset_bad="1")                                      # an unknown version: plain
        ok = st(jamo="1")
        cells = []                                                      # (label, path, data, {build: (bits, kind of syllables)})

        def face(variant=None, bad=None):               # jmap_face rewrites one file; keep each face under its own name
            path, data = self.jmap_face(variant, bad)
            kept = os.path.join(self.tmp, "%s.svf" % (variant or bad))
            shutil.copy(path, kept)
            return kept, data
        for v in svf_synth.LIST_VARIANTS:
            path, data = face(v)
            jm = jamoset.unpack(jamoset.parse_svfn(data).jset)
            if v == "list_big":
                cells.append((v, path, data, {
                    "list": (st(jamo="1", jset_unread="1"), "nofb"), "nolist": (st(jmap_unread="1", jset_unread="1"), "plain"),
                    "nojmap": ({"": st(jmap_unread="1", jset_bad="1"), "--stream=4:512": st(jmap_unread="1")}, "plain"),
                    "nojmap_norecog": (norecog, "plain")}))
            elif jm.fallback is None:
                cells.append((v, path, data, {"list": (ok, "list"), "nolist": (unread, "plain"), "nojmap": (unread, "plain"),
                                              "nojmap_norecog": (norecog, "plain")}))
            else:
                cells.append((v, path, data, {"list": (ok, "list"), "nolist": (unread_fb, "fb"), "nojmap": (unread_fb, "fb"),
                                              "nojmap_norecog": (norecog, "plain")}))
        recog_header = {"jlist_sparse": bad, "jlist_4b": bad, "jlist_flags": bad, "jlist_ns0": bad, "jlist_ns256": bad,
                        "jlist_fallback_adv": bad, "jlist_region_max": bad, "jlist_short_nofb": unread, "jlist_length": unread,
                        "jlist_short": st(jmap_unread="1", jset_bad="1"), "jlist_fallback_short": st(jmap_unread="1", jset_bad="1"),
                        "jlist_fallback_bad": st(jmap_unread="1", jset_bad="1"), "jlist_fallback_v3": st(jmap_unread="1", jset_bad="1"),
                        "jlist_planes_i": unread_fb, "jlist_planes_m": unread_fb, "jlist_planes_f": unread_fb}
        self.assertEqual(set(recog_header), set(svf_synth.LIST_HEADER_KINDS))
        for kind in svf_synth.LIST_BAD_KINDS:
            path, data = face(bad=kind)
            if kind in svf_synth.LIST_HEADER_KINDS:
                rec = recog_header[kind]
                cells.append((kind, path, data, {"list": (bad, "plain"), "nolist": (bad, "plain"),
                                                 "nojmap": (rec, "fb" if rec["jamo"] == "1" else "plain"),
                                                 "nojmap_norecog": (norecog, "plain")}))
            else:
                cells.append((kind, path, data, {"list": (bad, "plain"), "nolist": (unread_fb, "fb"), "nojmap": (unread_fb, "fb"),
                                                 "nojmap_norecog": (norecog, "plain")}))
        for label, path, data, per in cells:
            want = {"plain": expected_syllables(data, plain=True)}
            if label in svf_synth.LIST_BAD_KINDS:       # jamoset refuses the block: the face as its fallback alone, written plain
                pf = jamoset.parse_svfn(data)
                off, size = struct.unpack_from("<II", data, 36)
                jset = data[off:off + size]
                fb = 118 + 8 * struct.unpack_from("<H", jset, 8)[0] if size >= 10 else 0
                if size >= fb + 12:
                    want["fb"] = expected_syllables(svf_synth.rebuild(pf, jset[fb:]))
            else:
                want["fb"] = expected_syllables(data, jmap=False)
            if label in svf_synth.LIST_VARIANTS:
                want["list"] = expected_syllables(data, big=False) if label != "list_big" else None
                if label == "list_big":
                    want["nofb"] = expected_syllables(data, fallback=False)
            for which, (bits, how) in per.items():
                for cfg in ("", "--stream=4:512"):
                    b = bits if "jamo" in bits else bits[cfg]       # a dict by cfg where the streamed verdict differs
                    with self.subTest(cell=label, build=which, cfg=cfg or "mapped"):
                        self.assert_status(path, data, builds[which], b, want[how], cfgs=(cfg,), rd8=not cfg)

    def test_jmap_list_recog_stream_load_max(self):
        """A LIST of NS 255 over a version 1 fallback of the 12 x 12 class, 24/16/16 set table (11,681 B; region 13,839, over
        SVF__JSET_LOAD_MAX) on the RECOG build: streamed it loads the 16 header bytes only (plain, JMAP_UNREAD alone), mapped the
        fallback composes."""
        t = limits_tables(12, 12, 24, 16, 16)
        glyphs = [(jamoset.PIECE_BASE + n, bytes([n & 0xFF, (n >> 8) | 0x80, (n * 7) & 0xFF]) + bytes(5), 8, 0, 8)
                  for n in sorted(set(t.init_piece + t.med_piece + t.fin_piece))]
        fbk = jamoset.pack_v1(t)
        self.assertEqual(len(fbk), 11681)
        f = jamoset.parse_svfn(jamoset.write_svfn(8, 8, 7, glyphs, fbk))
        base = jamoset.unpack(f.jset)
        pool = [sorted(set(x)) for x in (base.init_piece, base.med_piece, base.fin_piece)]
        exc = {s: [pool[0][j % len(pool[0])], pool[1][3 * j % len(pool[1])], pool[2][5 * j % len(pool[2])]]
               for j, s in enumerate([j * 44 for j in range(254)] + [11171])}
        jm, new = jamoset.jmap_list(f, exc)
        self.assertEqual(len(exc), 255)
        block = jamoset.pack_jmap(jm, jm.fallback_block)
        self.assertEqual(len(block), 13839)
        self.assertGreater(len(block), JSET_LOAD_MAX)
        path = os.path.join(self.tmp, "listbig.svf")
        with open(path, "wb") as fh:
            fh.write(jamoset.write_svfn(8, 8, 7, glyphs, block))
        with open(path, "rb") as fh:
            data = fh.read()
        exes = build_reader("v1nojmap")
        self.assert_status(path, data, exes, {"jamo": "1", "jmap_unread": "1", "jset_bad": "0", "jmap_bad": "0"},
                           expected_syllables(data, jmap=False), cfgs=("",))
        self.assert_status(path, data, exes, {"jamo": "0", "jmap_unread": "1", "jset_bad": "0", "jmap_bad": "0", "jset_unread": "0"},
                           expected_syllables(data, plain=True), cfgs=("--stream=4:512",), rd8=False)

    def test_jmap_list_needs_jmap(self):
        cc = os.environ.get("CC") or shutil.which("cc") or "gcc"
        r = subprocess.run([cc, "-E", "-x", "c", "-DSVF_JMAP=0", "-DSVF_JMAP_LIST=1", os.path.join(C_DIR, "include", "svf.h")],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SVF_JMAP_LIST needs SVF_JMAP", r.stderr)

    def test_narrow_hot_path_identical(self):
        """The version 1 / 2 lookup and validation code of -DSVF_JMAP=0 -DSVF_JSET_BIG=0 is the code of the baseline commit
        (HOTPATH_BASELINE, the commit before SVF_JSET_BIG): arm-none-eabi-gcc -mcpu=cortex-m0plus -Os -ffunction-sections,
        the disassembly of HOTPATH_FUNCS in svf_jamo.o equal, each present on both sides or on neither (one inlined on one
        side only is a finding). Environment: SVF_HOTPATH_BASELINE overrides the commit; OPT the toolchain directory; SVF_HOTPATH_REQUIRE=1 (set by
        make -C c check) makes a baseline commit that is not in the repository a failure (a missing toolchain stays a skip)."""
        gcc = os.path.join(os.environ.get("OPT", os.path.expanduser("~/opt")), "arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-gcc")
        objdump = os.path.join(os.path.dirname(gcc), "arm-none-eabi-objdump")
        baseline = os.environ.get("SVF_HOTPATH_BASELINE") or HOTPATH_BASELINE or root_commit()
        missing = [x for x in (gcc, objdump) if not os.path.exists(x)] + [x for x in ("git", "tar") if not shutil.which(x)]
        if missing:
            self.skipTest("SKIPPED, the narrow hot-path identity is NOT checked: missing " + ", ".join(missing))
        base = os.path.join(self.tmp, "base")
        os.mkdir(base)
        r = subprocess.run("git -C '%s' archive '%s' c | tar -x -C '%s'" % (ROOT, baseline, base), shell=True, capture_output=True, text=True)
        if r.returncode != 0:
            why = "baseline commit %s not in the repository (%s)" % (baseline, r.stderr.strip())
            if os.environ.get("SVF_HOTPATH_REQUIRE") == "1":       # make -C c check
                self.fail("the narrow hot-path identity cannot be checked: " + why)
            self.skipTest("SKIPPED, the narrow hot-path identity is NOT checked: " + why)

        def functions(c_dir, tag):
            return self.arm_functions(gcc, objdump, c_dir, tag, "-DSVF_JMAP=0")
        new, old = functions(C_DIR, "new"), functions(os.path.join(base, "c"), "base")
        found = []
        for n in HOTPATH_FUNCS:
            with self.subTest(function=n):
                self.assertEqual(n in new, n in old, "inlined or present on one side only")
                if n in new:
                    found.append(n)
                    self.assertEqual(new[n], old[n])
        self.assertIn("svf_jamo_pieces", found)
        print("\n  narrow hot path vs %s: identical (%s)" % (baseline[:8], ", ".join(found)), file=sys.stderr)

    def test_composed_padding_is_masked(self):
        """A 22 px 1 bpp jamo face with every glyph byte 0xFF: composed cells come back with the bits past the cell
        width cleared."""
        face = os.path.join(SVF_DIR, "dos", "NEODG16D.SVF")
        with open(face, "rb") as fh:
            data = bytearray(fh.read())
        _, bpp, count, cw, ch, _, _, _, data_off, _, _ = header(data)
        self.assertTrue((cw * bpp) % 8)
        stride = (cw * bpp + 7) // 8 * ch
        data = bytearray(fill_rows(bytes(data)))
        path = os.path.join(self.tmp, "ff.svf")
        with open(path, "wb") as fh:
            fh.write(bytes(data))
        out = run_dump(path, "syllables", asan=True)
        self.assertEqual(out, expected_syllables(bytes(data)))
        self.assertNotIn(b"\xff" * stride, out)

    def test_jset_cut_at_each_section_falls_back(self):
        """The version 2 block cut at the start of each section (and one byte short of its end): a plain face, ASan
        clean."""
        with open(SYNTH_BASE, "rb") as fh:
            t = jamoset.unpack(jamoset.parse_svfn(fh.read()).jset)
        b = jamoset.decode_jset2(jamoset.pack(t).block)
        w = jamoset.jset_width(t.ni) + jamoset.jset_width(t.nm) + jamoset.jset_width(t.nf)
        cuts = [0, 4, 6, 12, 14, 16, 35, 63]
        p = 63 + (t.lc * 21 * t.tc * w + 7) // 8
        rows = (10, 10, 12) if b.na else (5, 5, 6)
        for size in (t.ni * rows[0], t.nm * rows[1], t.nf * rows[2], 2 * b.na, 51):
            cuts.append(p)
            p += size
        self.assertEqual(p, jamoset.jset_size(t.lc, t.tc, t.ni, t.nm, t.nf, b.na))
        cuts.append(p - 1)
        for cut in cuts:
            with self.subTest(cut=cut):
                path = synth(self.tmp, "--jset-cut", str(cut), "--from", SYNTH_BASE)
                with open(path, "rb") as fh:
                    data = fh.read()
                # v3: the header names the block's size; a block cut short is not usable, so parse_svfn leaves a plain face
                self.assertEqual(struct.unpack_from("<I", data, 40)[0], cut)
                self.assertTrue(jamoset.parse_svfn(data).jset_bad)
                info = dict(kv.split("=") for kv in run_dump(path, "info", asan=True).decode().split())
                self.assertEqual((info["jamo"], info["jset_bad"]), ("0", "1"))
                self.assertEqual(run_dump(path, "glyphs", asan=True), expected_glyphs(data))
                out = run_dump(path, "syllables", asan=True)
                self.assertEqual(out, expected_syllables(data))
                self.assertEqual(out[-1], 0)

    def test_8bpp_compose(self):
        """An 8 bpp jamo face whose pieces overlap at every pixel with different levels: the byte max of jamoset."""
        path = synth(self.tmp, "--bpp8", "--from", SYNTH_BASE)
        with open(path, "rb") as fh:
            data = fh.read()
        self.assertEqual(header(data)[1], 8)
        out = run_dump(path, "syllables", asan=True)
        self.assertEqual(out[-1], 1)
        self.assertEqual(out, expected_syllables(data))

    def test_unused_finset_entry_accepted(self):
        path = synth(self.tmp, "--jset-unused-finset", "--from", SYNTH_BASE)
        with open(path, "rb") as fh:
            data = fh.read()
        f, t = jamo_tables(data)
        self.assertIsNotNone(t)
        final_classes = set(t.tail_class[1:])
        self.assertTrue(any(s >= t.nf for i, s in enumerate(t.fin_set) if i % t.tc not in final_classes))
        info = dict(kv.split("=") for kv in run_dump(path, "info", asan=True).decode().split())
        self.assertEqual((info["jamo"], info["jset_bad"]), ("1", "0"))
        out = run_dump(path, "syllables", asan=True)
        self.assertEqual(out, expected_syllables(data))
        with open(SYNTH_BASE, "rb") as fh:
            self.assertEqual(out, expected_syllables(fh.read()))      # the same drawing as the face it came from

    def has_lines(self, path, cps):
        out = run_dump(path, "has", *("U+%04X" % cp for cp in cps), asan=True).decode()
        return out.splitlines()

    def test_has_composable(self):
        face = os.path.join(SVF_DIR, "dos", "NEODG16A.SVF")
        with open(face, "rb") as fh:
            data = fh.read()
        f, t = jamo_tables(data)
        self.assertIsNotNone(t)
        self.assertNotIn(0xAC00, f.glyphs)
        self.assertNotEqual(t.compat[0], jamoset.BLANK)
        self.assertIn(0x41, f.glyphs)
        adv = t.advance or f.cell_w
        a = f.metrics[0x41]
        self.assertEqual(self.has_lines(face, (0xAC00, 0xD7A3, 0x3131, 0x0041, 0xD7A4, 0x3130)), [
            f"U+AC00 has=1 advance={adv} bearing=0 ink={f.cell_w} dy=0",
            f"U+D7A3 has=1 advance={adv} bearing=0 ink={f.cell_w} dy=0",
            f"U+3131 has=1 advance={adv} bearing=0 ink={f.cell_w} dy=0",
            f"U+0041 has=1 advance={a[0]} bearing={a[1]} ink={a[2]} dy={f.dy.get(0x41, 0)}",
            "U+D7A4 has=0",
            "U+3130 has=0",
        ])

    def test_has_after_fallback(self):
        """A face whose JSET fails draws no syllable, and a compat jamo only from its cmap."""
        path = synth(self.tmp, "--jset-bad", "missing_piece", "--from", SYNTH_BASE)
        with open(path, "rb") as fh:
            f = jamoset.parse_svfn(fh.read())
        self.assertNotIn(0x3131, f.glyphs)
        self.assertEqual(self.has_lines(path, (0xAC00, 0x3131)), ["U+AC00 has=0", "U+3131 has=0"])

    def test_compat_from_cmap_when_piece_is_blank(self):
        """NEODG16C keeps 42 compat jamo as whole glyphs (blank compat piece) and 9 by piece."""
        face = os.path.join(SVF_DIR, "dos", "NEODG16C.SVF")
        with open(face, "rb") as fh:
            data = fh.read()
        f, t = jamo_tables(data)
        by_cmap = [0x3131 + k for k in range(51) if t.compat[k] == jamoset.BLANK]
        self.assertTrue(by_cmap)
        self.assertTrue(all(cp in f.glyphs for cp in by_cmap))
        lines = self.has_lines(face, by_cmap[:1])
        a = f.metrics[by_cmap[0]]
        self.assertEqual(lines, [f"U+{by_cmap[0]:04X} has=1 advance={a[0]} bearing={a[1]} ink={a[2]} dy=0"])


STREAM_CONFIGS = ("--stream", "--stream=4:512", "--stream=32:4096")    # no cache; 4 KB / 512 B; 32 KB / 4 KB
JSET_MAX = 9246
# A build with the version 1 reader (SVF_JSET_V1, the default) loads a JSET region up to the largest version 1 block whole
# (SVF__JSET_LOAD_MAX); the version 2 reader alone (build_v2only) up to JSET_MAX.
JSET_LOAD_MAX = 12321


def stream_dump(face, *args, asan=False, exe=None):
    """svfdump OPTIONS... FACE CMD...: (exit code, stdout bytes, stderr text). @p exe names another build ("svfdump-rd8"),
    or is the absolute path of one (build_v2only).
    """
    exe = exe or ("svfdump-asan" if asan else "svfdump")
    exe = exe if os.path.isabs(exe) else build()[exe]
    opts = [a for a in args if a.startswith("--")]
    rest = [a for a in args if not a.startswith("--")]
    r = subprocess.run([exe] + opts + [face] + rest, capture_output=True)
    return r.returncode, r.stdout, r.stderr.decode(errors="replace")


def open_reads(err):
    """The read callback calls svf_open_stream made (svfdump's "open reads=N" line)."""
    for line in err.splitlines():
        if "open reads=" in line:
            return int(line.rsplit("=", 1)[1])
    raise AssertionError("no open reads line in: " + err)


def glyph_errors(err):
    """The code points svfdump reports SVF_E_IO for ("svfdump: glyph U+XXXX: SVF_E_IO"), in order."""
    return [int(line.split("U+")[1].split(":")[0], 16) for line in err.splitlines()
            if line.startswith("svfdump: glyph U+") and line.endswith("SVF_E_IO")]


def tables_need(data):
    """svf_stream_tables_size: 8 bytes of stream state, the cmap, a usable metrics table, the JSET block (only its
    16-byte header when the size the header names is longer than any valid block, as such a block fails before its
    length check) and the glyph offset table (count + 1 entries of 2 or 4 bytes)."""
    flags, _, count, _, _, _, _, metrics_off, data_off, _, cmap_off = header(data)
    n = 8 + 8 * count
    metrics_ok = metrics_off >= jamoset.HEADER3_SIZE and metrics_off + 4 * count <= len(data)
    if flags & jamoset.FLAG_VARIABLE and metrics_ok:
        n += 4 * count
    if flags & jamoset.FLAG_JAMO:
        (jl,) = struct.unpack_from("<I", data, 40)
        n += jl if jl <= JSET_LOAD_MAX else min(jl, 16)
    return n + (count + 1) * (4 if data[10] & 8 else 2)


class SynthJmap(unittest.TestCase):
    """svf_synth's JMAP variants and bad kinds (Python only: jamoset is the reference, no C)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-synth-jmap-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def face(self, *args):
        with open(synth(self.tmp, *args, "--from", SYNTH_BASE), "rb") as fh:
            return fh.read()

    def test_variants_unpack(self):
        self.assertEqual(svf_synth.JMAP_VARIANTS, ("sparse3", "sparse4", "dense3", "dense4", "hybrid1", "hybrid2", "adv0",
                                                   "blanks", "pi2047", "dhybrid1", "dhybrid2", "sparse_full",
                                                   "adv0fb", "hybrid_big1", "hybrid_big2"))
        for v in svf_synth.JMAP_VARIANTS:
            with self.subTest(variant=v):
                f = jamoset.parse_svfn(self.face("--jmap-variant", v))
                self.assertIsNotNone(f.jset, "the face keeps its JMAP block (every piece has a glyph)")
                self.assertFalse(f.jset_bad)
                jm = jamoset.unpack(f.jset)
                self.assertIsInstance(jm, jamoset.Jmap)
                if v != "sparse_full":     # pack_jmap writes 11,172 entries dense
                    self.assertEqual(jamoset.pack_jmap(jm, jm.fallback_block), f.jset)
                if v == "sparse_full":
                    self.assertTrue(f.jset[6] & 2, "SPARSE")
                    self.assertEqual(len(jm.entries), 11172)
                    self.assertEqual(len(f.jset), jamoset.jmap_size(11172, False, True))
                if v in ("sparse3", "sparse4", "adv0", "blanks"):
                    self.assertTrue(f.jset[6] & 2, "SPARSE")
                    self.assertEqual(len(jm.entries), len(range(0, 11172, svf_synth.JMAP_STRIDE)))
                if v in ("sparse4", "dense4", "dhybrid2"):
                    self.assertTrue(f.jset[6] & 1, "4B")
                    self.assertTrue(min(jm.pi, jm.pm, jm.pf) > 255, (jm.pi, jm.pm, jm.pf))
                    for plane in range(3):      # the entry bytes' high bits (b0) are exercised in every plane
                        self.assertTrue(any(e[plane] >= 256 for e in jm.entries.values()), plane)
                    self.assertLessEqual(len(f.jset), jamoset.JMAP_REGION_MAX)
                if v in ("dense3", "dense4", "dhybrid1", "dhybrid2"):
                    self.assertEqual(len(jm.entries), 11172)
                    self.assertFalse(f.jset[6] & 2)
                if v == "adv0fb":
                    self.assertEqual((jm.advance, jm.fallback.advance, jm.fallback_version), (0, 0, 1))
                    self.assertEqual(len(jm.entries), 16)
                    self.assertEqual(f.jset[jamoset.JMAP_SPARSE_ENTRIES + 16 * 3 + 11], 0)
                if v.startswith("hybrid"):
                    self.assertEqual(len(jm.entries), 16)
                    self.assertEqual(jm.fallback_version, int(v[-1]))
                    self.assertTrue(f.jset[6] & 4)
                    total = jm.pi + jm.pm + jm.pf
                    self.assertTrue(all(p >= total for p in jm.fallback.init_piece + jm.fallback.med_piece
                                        + jm.fallback.fin_piece if p != jamoset.BLANK))
                    if v == "hybrid1":     # a blank JMAP compat entry whose fallback names a piece (PR-10)
                        k = next(k for k, c in enumerate(jm.block_compat) if c == jamoset.BLANK
                                 and jm.fallback.compat[k] != jamoset.BLANK)
                        self.assertEqual(jm.compat[k], jm.fallback.compat[k])
                    miss = next(s for s in range(11172) if s not in jm.entries)
                    self.assertEqual(len(jm.pieces(0xAC00 + miss)), 2 if miss % 28 == 0 else 3)
                elif v.startswith("dhybrid"):
                    self.assertEqual(jm.fallback_version, int(v[-1]))
                    self.assertTrue(f.jset[6] & 4)
                    total = jm.pi + jm.pm + jm.pf
                    self.assertTrue(all(p >= total for p in jm.fallback.init_piece + jm.fallback.med_piece
                                        + jm.fallback.fin_piece if p != jamoset.BLANK))
                elif v != "adv0fb":
                    self.assertIsNone(jm.fallback)
                self.assertEqual(jm.advance, 0 if v in ("adv0", "adv0fb") else svf_synth.JMAP_ADVANCE)
                if v == "blanks":
                    self.assertTrue(any(e[1] == 0 for e in jm.entries.values()))
                    self.assertTrue(any(s % 28 and e[2] == 0 for s, e in jm.entries.items()))
                if v == "pi2047":
                    self.assertEqual((jm.pi, jm.pm, jm.pf), (2047, 1, 1))
                    self.assertTrue(f.jset[6] & 1)

    def test_bad_kinds_refused(self):
        """Every kind's face is plain (the block fails unpack_jmap, R8 or the region size)."""
        self.assertEqual(len(svf_synth.JMAP_BAD_KINDS), 23)
        for kind in svf_synth.JMAP_BAD_KINDS:
            with self.subTest(kind=kind):
                f = jamoset.parse_svfn(self.face("--jmap-bad", kind))
                self.assertTrue(f.jset_bad)
                self.assertIsNone(f.jset)

    BAD_PREFIX = {
        "jmap_short": "JMAP R1 length 100 is shorter than 118",
        "jmap_flags": "JMAP R1 flags 0x0a set reserved bits",
        "jmap_pi256_3b": "JMAP R2 counts PI 256 PM 42 PF 27 are over the 3B limits",
        "jmap_pi2048_4b": "JMAP R2 counts PI 2048 ",
        "jmap_pf1024_4b": "JMAP R2 counts PI 395 PM 342 PF 1024 are over the 4B limits",
        "jmap_zero_pieces": "JMAP R2 PI + PM + PF is 0",
        "jmap_ns0": "JMAP R3 NS 0 is not 1..11172",
        "jmap_dense_ns": "JMAP R3 NS 11171 of a dense block is not 11172",
        "jmap_length": "JMAP R4 length ",
        "jmap_fallback_short": "JMAP R4 length ",
        "jmap_fallback_bad": "JMAP R4 fallback is not a JSET block",
        "jmap_fallback_v3": "JMAP R4 fallback is version 3, not 1 or 2",
        "jmap_fallback_adv": "JMAP R4 fallback advance 17 differs from the JMAP advance 16",
        "jmap_compat_over": "JMAP R5 compat[0] = 164 is not blank or below 164",
        "jmap_pad": "JMAP R6 pad byte is not 0",
        "jmap_bitmap_tail": "JMAP R6 bitmap bits 11172..11175 are not 0",
        "jmap_rank_wrong": "JMAP R6 rank[1] = 53, the bitmap has 52 bits below 256",
        "jmap_ns_popcount": "JMAP R6 NS 2235 but the bitmap has 2236 bits",
        "jmap_entry_over": "JMAP R7 entry 0 field i = 96 is over 95",
        "jmap_entry_over_4b": "JMAP R7 entry 0 field m = 343 is over 342",
        "v2_as_v3": "JMAP R3 NS 518 of a dense block is not 11172",
    }

    def test_bad_kinds_unpack(self):
        """unpack_jmap refuses every kind with its own rule's message but jmap_missing_piece (R8: the block is valid, the
        face lacks a glyph) and jmap_region_max (the block is valid; the 65,536 byte region of its header is over the cap)."""
        self.assertEqual(svf_synth.JMAP_BAD_KINDS, (
            "jmap_short", "jmap_flags", "jmap_pi256_3b", "jmap_pi2048_4b", "jmap_pf1024_4b", "jmap_zero_pieces",
            "jmap_ns0", "jmap_dense_ns", "jmap_length", "jmap_fallback_short", "jmap_fallback_bad", "jmap_fallback_v3",
            "jmap_fallback_adv", "jmap_compat_over", "jmap_pad", "jmap_bitmap_tail", "jmap_rank_wrong",
            "jmap_ns_popcount", "jmap_entry_over", "jmap_entry_over_4b", "jmap_missing_piece", "jmap_region_max",
            "v2_as_v3"))
        self.assertEqual(set(self.BAD_PREFIX), set(svf_synth.JMAP_BAD_KINDS) - {"jmap_missing_piece", "jmap_region_max"})
        ft, t = svf_synth.load(SYNTH_BASE)
        for kind in svf_synth.JMAP_BAD_KINDS:
            with self.subTest(kind=kind):
                block, planes, size = svf_synth.bad_jmap(ft, t, kind)
                if kind == "jmap_missing_piece":
                    jm = jamoset.unpack(block)
                    self.assertIsInstance(jm, jamoset.Jmap)
                    self.assertNotIn(jamoset.PIECE_BASE + jm.pi + jm.pm + jm.pf - 1, planes)
                elif kind == "jmap_region_max":
                    self.assertIsInstance(jamoset.unpack(block), jamoset.Jmap)
                    self.assertEqual(size, 0x10000)
                    data = self.face("--jmap-bad", kind)
                    (off, got) = struct.unpack_from("<II", data, 36)
                    self.assertEqual(got, 0x10000)
                    self.assertGreaterEqual(len(data), off + 0x10000)
                    with self.assertRaisesRegex(ValueError, "JMAP R4 length 65536 is over the region limit 65534"):
                        jamoset.unpack(data[off:off + got])
                else:
                    with self.assertRaises(ValueError) as cm:
                        jamoset.unpack(block)
                    self.assertTrue(str(cm.exception).startswith(self.BAD_PREFIX[kind]), str(cm.exception))

    def test_jmap_refuses_jmap_face(self):
        path = synth(self.tmp, "--jmap-variant", "sparse3", "--from", SYNTH_BASE)
        out = os.path.join(self.tmp, "again.svf")
        r = subprocess.run([sys.executable, SYNTH, "--jmap-variant", "dense3", "--from", path, out],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a JMAP or LIST face", r.stderr)

    def test_version4_kind(self):
        self.assertIn("version4", svf_synth.BAD_KINDS)
        self.assertNotIn("version3", svf_synth.BAD_KINDS)
        f = jamoset.parse_svfn(self.face("--jset-bad", "version4"))
        self.assertTrue(f.jset_bad)
        ft, t = svf_synth.load(SYNTH_BASE)
        block = svf_synth.bad_jset(ft, t, "version4")[0]
        with self.assertRaisesRegex(ValueError, "JSET version 4"):
            jamoset.unpack(block)


class SynthList(unittest.TestCase):
    """svf_synth's LIST variants and jlist bad kinds (Python only: jamoset is the reference, no C)."""

    RULE = {"jlist_short": "R1", "jlist_short_nofb": "R1", "jlist_sparse": "R1", "jlist_4b": "R1", "jlist_flags": "R1",
            "jlist_planes_i": "L2", "jlist_planes_m": "L2", "jlist_planes_f": "L2", "jlist_ns0": "L3",
            "jlist_ns256": "L3", "jlist_length": "R4", "jlist_fallback_short": "R4", "jlist_fallback_bad": "R4",
            "jlist_fallback_v3": "R4", "jlist_fallback_adv": "R4", "jlist_key_equal": "L6", "jlist_key_desc": "L6",
            "jlist_key_over": "L6"}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-synth-list-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def face(self, *args):
        with open(synth(self.tmp, *args, "--from", SYNTH_BASE), "rb") as fh:
            return fh.read()

    def test_list_variants_unpack(self):
        for v in svf_synth.LIST_VARIANTS:
            with self.subTest(variant=v):
                f = jamoset.parse_svfn(self.face("--jmap-variant", v))
                self.assertFalse(f.jset_bad)
                self.assertIsNotNone(f.jset)
                jm = jamoset.unpack(f.jset)
                self.assertIsInstance(jm, jamoset.Jmap)
                self.assertTrue(jm.list_mode)
                self.assertEqual(jamoset.pack_jmap(jm, jm.fallback_block), f.jset)
                if v == "list_max":
                    self.assertEqual(len(jm.entries), 255)
                    self.assertIn(0, jm.entries)
                    self.assertIn(11171, jm.entries)
                    self.assertEqual(len(f.jset), 2158)
                    self.assertIsNone(jm.fallback)
                elif v == "list_nofb":
                    self.assertEqual(list(jm.entries), [5000])
                    self.assertIsNone(jm.fallback)
                    self.assertEqual(jm.advance, svf_synth.JMAP_ADVANCE)
                else:
                    self.assertIsNotNone(jm.fallback)
                    self.assertEqual(f.jset[7], 16)
                    self.assertEqual(jm.fallback_block[11], 16)
                    self.assertEqual(jm.fallback_version, 2 if v == "list2" else 1)
                    n = 38 + {"list_blank": 2, "list_zero": 1}.get(v, 0)
                    self.assertEqual(len(jm.entries), n)
                if v == "list_blank":
                    self.assertIn((jamoset.BLANK,) * 3, jm.entries.values())
                    self.assertTrue(any(e[0] != jamoset.BLANK and e[1:] == (jamoset.BLANK,) * 2
                                        for e in jm.entries.values()))
                if v == "list_zero":
                    self.assertTrue(any(0 in e for e in jm.entries.values()))
                if v == "list_big":
                    self.assertTrue(jamoset.needs_big(jm.fallback))

    def test_list_variants_distinguishable(self):
        """Every listed syllable composes differently from the fallback's own pieces, so the pixels tell LIST from fallback."""
        for v in ("list1", "list2", "list_compat"):
            with self.subTest(variant=v):
                f = jamoset.parse_svfn(self.face("--jmap-variant", v))
                jm = jamoset.unpack(f.jset)
                self.assertEqual(len(jm.entries), 38)
                for s in jm.entries:
                    cp = 0xAC00 + s
                    self.assertNotEqual(jamoset.compose(f, jm, cp), jamoset.compose(f, jm.fallback, cp), s)
                if v == "list_compat":
                    named = [k for k, c in enumerate(jm.block_compat) if c != jamoset.BLANK]
                    blank = [k for k, c in enumerate(jm.block_compat) if c == jamoset.BLANK
                             and jm.fallback.compat[k] != jamoset.BLANK]
                    self.assertTrue(named and blank)
                    self.assertNotEqual(jm.block_compat[named[0]], jm.fallback.compat[named[0]])

    def test_list2_noncanonical(self):
        f = jamoset.parse_svfn(self.face("--jmap-variant", "list2"))
        fb = jamoset.unpack(f.jset).fallback
        seen = []
        for p in fb.init_piece + fb.med_piece + fb.fin_piece + fb.compat:
            if p != jamoset.BLANK and p not in seen:
                seen.append(p)
        self.assertNotEqual(seen, list(range(len(seen))))
        self.assertEqual(seen[:3], [5, 3, 9])

    def test_list_advance_nonzero_source(self):
        """NEODG16G's own advance is 0: the LIST's (the fallback's) is the re-encoded 16."""
        ft, t = svf_synth.load(SYNTH_BASE)
        self.assertEqual(t.advance, 0)
        f = jamoset.parse_svfn(self.face("--jmap-variant", "list1"))
        self.assertEqual((f.jset[7], jamoset.unpack(f.jset).fallback.advance), (16, 16))

    def test_list_bad_kinds_refused(self):
        passes = svf_synth.LIST_UNPACK_PASSES
        self.assertEqual(passes, ("jlist_field_noglyph", "jlist_field_fffe", "jlist_compat_noglyph", "jlist_region_max"))
        ft, t = svf_synth.load(SYNTH_BASE)
        for kind in svf_synth.LIST_BAD_KINDS:
            with self.subTest(kind=kind):
                block, planes, size = svf_synth.bad_list(ft, t, kind)
                if kind in passes:
                    self.assertTrue(jamoset.unpack_jmap(block).list_mode)
                    data = self.face("--jmap-bad", kind)
                    f = jamoset.parse_svfn(data)
                    if kind == "jlist_region_max":
                        self.assertEqual(size, 0x10000)
                        self.assertEqual(struct.unpack_from("<I", data, 40)[0], 0x10000)
                        self.assertTrue(f.jset_bad)       # Python's R4 refuses the 65,536 byte region
                    else:
                        self.assertTrue(f.jset_bad)
                else:
                    with self.assertRaisesRegex(ValueError, "^JMAP " + self.RULE[kind]):
                        jamoset.unpack_jmap(block)
                    f = jamoset.parse_svfn(self.face("--jmap-bad", kind))
                    self.assertTrue(f.jset_bad)
                    self.assertIsNone(f.jset)

    def test_list_kind_counts(self):
        self.assertEqual(len(svf_synth.LIST_VARIANTS), 8)
        self.assertEqual(len(svf_synth.LIST_BAD_KINDS), 22)
        self.assertEqual(set(svf_synth.LIST_CONTENT_KINDS) | set(svf_synth.LIST_HEADER_KINDS), set(svf_synth.LIST_BAD_KINDS))
        self.assertEqual((len(svf_synth.LIST_HEADER_KINDS), len(svf_synth.LIST_CONTENT_KINDS)), (16, 6))
        self.assertFalse(set(svf_synth.LIST_HEADER_KINDS) & set(svf_synth.LIST_CONTENT_KINDS))
        self.assertEqual(set(self.RULE) | set(svf_synth.LIST_UNPACK_PASSES), set(svf_synth.LIST_BAD_KINDS))
        self.assertEqual(len(svf_synth.JMAP_VARIANTS), 15)
        self.assertEqual(len(svf_synth.JMAP_BAD_KINDS), 23)


class SynthBig(unittest.TestCase):
    """svf_synth's BIG kinds and variants (Python only: jamoset is the reference; the C reader is Task 16)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-synth-big-")
        self.ft, self.t = svf_synth.load(SYNTH_BASE)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def jset(self, *args):
        with open(synth(self.tmp, *args, "--from", SYNTH_BASE), "rb") as fh:
            return jamoset.parse_svfn(fh.read()).jset

    def test_kind_lists(self):
        self.assertEqual(svf_synth.BAD_KINDS_STD, ("lc13", "tc13", "ni33", "nm25", "nf17"))
        self.assertEqual(svf_synth.BAD_KINDS_BIG, ("lc20", "tc29", "ni129", "nm129", "nf65"))
        self.assertTrue(set(svf_synth.BAD_KINDS_BIG) <= set(svf_synth.BAD_KINDS))
        self.assertFalse(set(svf_synth.BAD_KINDS_STD) & set(svf_synth.BAD_KINDS))
        self.assertEqual(svf_synth.VARIANTS[-2:], ("limits_big", "limits_big_alias"))

    def block(self, kind, version):
        """The bad block of @p kind in @p version (svf_synth's own functions: a face with a refused block has no jset)."""
        return (svf_synth.bad_jset_v1 if version == 1 else svf_synth.bad_jset)(self.ft, self.t, kind)[0]

    def test_variant_sizes(self):
        for v, version, size in (("limits_big", 2, 29708), ("limits_big", 1, 47373), ("limits_big_alias", 2, 45068)):
            with self.subTest(variant=v, version=version):
                block = self.jset("--jset-variant", v, "--jset-version", str(version))
                self.assertEqual(len(block), size)
                self.assertEqual(struct.unpack_from("<H", block, 4)[0], version)
                t = jamoset.unpack(block)
                self.assertEqual((t.lc, t.tc, t.ni, t.nm, t.nf), (19, 28, 128, 128, 64))
                self.assertTrue(jamoset.needs_big(t))

    def test_alias_variant_equals_plain(self):
        a = jamoset.unpack(self.jset("--jset-variant", "limits_big"))
        b = jamoset.unpack(self.jset("--jset-variant", "limits_big_alias"))
        self.assertEqual(jamoset.decode_jset2(self.jset("--jset-variant", "limits_big_alias")).na, 128 * 19 + 128 * 21 + 64 * 27)
        for attr in ("init_set", "med_set", "fin_set", "lead_class", "tail_class", "compat", "init_piece", "med_piece",
                     "fin_piece"):
            self.assertEqual(getattr(a, attr), getattr(b, attr), attr)
        for cp in range(0xAC00, 0xD7A4, 97):
            self.assertEqual(jamoset.pieces_of(a, cp), jamoset.pieces_of(b, cp), cp)

    def test_alias_variant_needs_v2(self):
        r = subprocess.run([sys.executable, SYNTH, "--jset-variant", "limits_big_alias", "--jset-version", "1", "--from",
                            SYNTH_BASE, os.path.join(self.tmp, "x.svf")], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)

    def test_big_kinds_refused(self):
        for version in (1, 2):
            for kind in svf_synth.BAD_KINDS_BIG:
                with self.subTest(kind=kind, version=version):
                    block = self.block(kind, version)
                    self.assertEqual(struct.unpack_from("<H", block, 4)[0], version)
                    with self.assertRaisesRegex(ValueError, "not 1.."):
                        jamoset.unpack(block)
                    with open(synth(self.tmp, "--jset-bad", kind, "--jset-version", str(version), "--from", SYNTH_BASE),
                              "rb") as fh:       # the CLI writes it: the face has no usable JSET
                        f = jamoset.parse_svfn(fh.read())
                    self.assertTrue(f.jset_bad)
                    self.assertIsNone(f.jset)

    def test_big_kinds_one_past_one_cap(self):
        caps = dict(zip(("lc", "tc", "ni", "nm", "nf"), jamoset.JSET_LIMITS["big"]))
        for kind in svf_synth.BAD_KINDS_BIG:
            with self.subTest(kind=kind):
                key, n = kind[:2], int(kind[2:])
                self.assertEqual(n, caps[key] + 1)
                block = self.block(kind, 2)
                counts = dict(zip(("lc", "tc", "ni", "nm", "nf"), block[6:11]))
                for k, v in counts.items():
                    self.assertEqual(v, n if k == key else min(getattr(self.t, k), caps[k]), k)

    def test_std_kinds_valid_big_narrow_refused(self):
        for version in (1, 2):
            for kind in svf_synth.BAD_KINDS_STD:
                with self.subTest(kind=kind, version=version):
                    block = self.jset("--jset-bad", kind, "--jset-version", str(version))
                    self.assertEqual(block, self.block(kind, version))
                    t = jamoset.unpack(block)
                    self.assertTrue(jamoset.needs_big(t))
                    with self.assertRaisesRegex(ValueError, "--jset-big"):
                        (jamoset.pack_v1 if version == 1 else jamoset.pack)(t)
                    (jamoset.pack_v1 if version == 1 else jamoset.pack)(t, big=True)

    def test_std_kinds_keep_their_bytes(self):
        """The v2 STD kinds are widened2 + encode_jset2, the v1 ones pack_v1(big=True) of the widened tables."""
        for kind in svf_synth.BAD_KINDS_STD:
            with self.subTest(kind=kind):
                n = {"lc": "lc", "tc": "tc", "ni": "ni", "nm": "nm", "nf": "nf"}[kind[:2]]
                want2 = jamoset.encode_jset2(svf_synth.widened2(jamoset.decode_jset2(jamoset.pack(self.t).block),
                                                                **{n: int(kind[2:])}))
                self.assertEqual(svf_synth.bad_jset(self.ft, self.t, kind)[0], want2)
                want1 = jamoset.pack_v1(svf_synth.widened(self.t, **{n: int(kind[2:])}), big=True)
                self.assertEqual(svf_synth.bad_jset_v1(self.ft, self.t, kind)[0], want1)


class TestStream(unittest.TestCase):
    """svf_open_stream: the same validation and the same glyphs as a mapped face, through a read callback, with and
    without a block cache; short reads and read errors fail that glyph only and leave no stale cache block."""

    JAMO_FACE = os.path.join(SVF_DIR, "dos", "NEODG16A.SVF")

    def setUp(self):
        build()
        self.tmp = tempfile.mkdtemp(prefix="svf-stream-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def clean(self, err):
        self.assertNotIn("Sanitizer", err)
        self.assertNotIn("runtime error", err)
        self.assertNotIn("past the end", err)
        self.assertNotIn("forbidden", err)

    def test_stream_equals_mapped(self):
        n = 0
        for face in faces():
            with open(face, "rb") as fh:
                jamo = header(fh.read())[0] & jamoset.FLAG_JAMO
            cmds = ("info", "glyphs", "syllables") if jamo else ("info", "glyphs")
            for cmd in cmds:
                mapped = run_dump(face, cmd)
                for cfg in STREAM_CONFIGS:
                    with self.subTest(face=os.path.relpath(face, ROOT), cmd=cmd, cfg=cfg):
                        code, out, err = stream_dump(face, cfg, cmd)
                        self.clean(err)
                        self.assertEqual(code, 0, err)
                        self.assertEqual(out, mapped)
            n += 1
        print(f"\n  test_stream_equals_mapped: {n} faces x {len(STREAM_CONFIGS)} configurations", file=sys.stderr)

    def test_stream_asan(self):
        """Every configuration under ASan/UBSan on 1, 2 and 8 bpp jamo faces and a padded 2 bpp face."""
        bpp8 = synth(self.tmp, "--bpp8", "--from", SYNTH_BASE)
        for face in (self.JAMO_FACE, os.path.join(SVF_DIR, "dos", "PAPER16A.SVF"), bpp8,
                     os.path.join(SVF_DIR, "dos", "NGO16BX2.SVF")):
            for cmd in ("glyphs", "syllables"):
                mapped = run_dump(face, cmd)
                for cfg in STREAM_CONFIGS + ("--stream=3:1024", "--stream=1:64"):
                    with self.subTest(face=os.path.basename(face), cmd=cmd, cfg=cfg):
                        code, out, err = stream_dump(face, cfg, cmd, asan=True)
                        self.clean(err)
                        self.assertEqual(code, 0, err)
                        self.assertEqual(out, mapped)

    def test_stream_validation_equals_mapped(self):
        """Truncated and hostile faces: the stream open gives the mapped open's result (error name, or the same info and
        glyphs), and never asks the callback for a byte past the file length."""
        cases = []
        for face in TestHostile.FACES + (self.JAMO_FACE,):
            with open(face, "rb") as fh:
                data = fh.read()
            for cut in sorted({len(data) * i // 12 for i in range(12)} | {0, 3, 4, 5, 6, 35, 36}):
                cases.append((f"{os.path.basename(face)} cut {cut}", data[:cut]))
            if face in TestHostile.FACES:
                cases += [(f"{os.path.basename(face)} {name}", d) for name, d in TestHostile.refused_cases(TestHostile, data)]
                count = header(data)[2]
                for off in (0, 35, 0xFFFFFFFF, len(data) - 4 * count + 1):
                    cases.append((f"{os.path.basename(face)} metrics {off:#x}", TestHostile.put(data, "<I", 20, off)))
        path = os.path.join(self.tmp, "v.svf")
        for name, d in cases:
            with open(path, "wb") as fh:
                fh.write(bytes(d))
            for cmd in ("info", "glyphs"):
                with self.subTest(case=name, cmd=cmd):
                    mcode, mout, merr = stream_dump(path, cmd, asan=True)
                    scode, sout, serr = stream_dump(path, "--stream=4:512", cmd, asan=True)
                    self.clean(serr)
                    self.assertEqual((scode, sout), (mcode, mout), serr)
                    if mcode:
                        self.assertEqual(merr.strip().rsplit(": ", 1)[1], serr.strip().splitlines()[-1].rsplit(": ", 1)[1])

    def test_tables_size_too_small(self):
        for face in faces():
            with open(face, "rb") as fh:
                data = fh.read()
            need = tables_need(data)
            with self.subTest(face=os.path.relpath(face, ROOT)):
                code, _, err = stream_dump(face, "--stream", f"--tables-bytes={need - 1}", "info")
                self.assertEqual(code, 2, err)
                self.assertIn("SVF_E_NOMEM", err)
                self.assertIn(f"tables need {need} bytes", err)
                code, out, err = stream_dump(face, "--stream", f"--tables-bytes={need}", "info")
                self.assertEqual(code, 0, err)
                self.assertEqual(out, run_dump(face, "info"))

    def test_failed_open_clears_face(self):
        """c/tests/test_open.c: every failed open (argument, header, tables size, read, table errors; mapped and
        streamed) leaves the face all zero."""
        r = subprocess.run([build()["test-open"], self.JAMO_FACE], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)
        self.assertNotIn("Sanitizer", r.stderr)
        self.assertGreaterEqual(sum(1 for line in r.stdout.splitlines() if line.startswith("cleared: ")), 12)

    def test_bad_arguments(self):
        """c/tests/test_args.c (sanitizer build): every public entry point of svf.h with each NULL pointer (face,
        out-parameters, buffers with a nonzero length, chain, faces, target, text) and bad argument returns the result
        svf.h documents (SVF_E_ARG, or the sentinel of a function without svf_err), for a NULL face, a zeroed face and
        mapped, streamed and cached faces."""
        r = subprocess.run([build()["test-args"], self.JAMO_FACE], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)
        self.assertNotIn("Sanitizer", r.stderr)
        self.assertNotIn("runtime error", r.stderr)
        self.assertGreaterEqual(sum(1 for line in r.stdout.splitlines() if line.endswith(": ok")), 100)

    def test_left_out_target_kind(self):
        """test-args built with -DSVF_TARGETS=0x02: svf_target_init and svf_draw_utf8 refuse GRAY8 and the callback."""
        r = subprocess.run([build()["test-args-page"], self.JAMO_FACE], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)
        self.assertNotIn("Sanitizer", r.stderr)
        self.assertIn("left out: svf_draw_utf8 GRAY8: ok", r.stdout)
        self.assertIn("left out: buffer unchanged: ok", r.stdout)

    def test_args_vesa(self):
        """test-args built with -DSVF_TARGETS=0x1E8: the kinds left out are refused, a kept kind draws."""
        r = subprocess.run([build()["test-args-vesa"], self.JAMO_FACE], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)
        self.assertNotIn("Sanitizer", r.stderr)
        self.assertIn("left out: svf_draw_utf8 GRAY8: ok", r.stdout)
        self.assertIn("left out: svf_draw_utf8 control ok", r.stdout)

    def test_args_jmap(self):
        """test-args built with -DSVF_JMAP=1 on a face with a JMAP block (sparse3): every entry point as for a JSET face,
        a composed syllable and a streamed face included."""
        path = synth(self.tmp, "--jmap-variant", "sparse3", "--from", SYNTH_BASE)
        r = subprocess.run([build()["test-args-jmap"], path], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)
        self.assertNotIn("Sanitizer", r.stderr)
        self.assertIn("svf_jamo_pieces works: ok", r.stdout.replace("open: ", "").replace("mapped: ", "").replace("stream: ", ""))
        self.assertGreaterEqual(sum(1 for line in r.stdout.splitlines() if line.endswith(": ok")), 100)

    def test_args_gray(self):
        """test-args built with -DSVF_TARGETS=0x200 (GRAY only): the kinds left out are refused, GRAY bits 8 draws on
        a stride of w. (make check does not run this program; this test does.)"""
        r = subprocess.run([build()["test-args-gray"], self.JAMO_FACE], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)
        self.assertNotIn("Sanitizer", r.stderr)
        self.assertIn("left out: svf_draw_utf8 GRAY8: ok", r.stdout)
        self.assertIn("left out: svf_target_init GRAY: ok", r.stdout)
        self.assertIn("left out: draw GRAY bits 8 on stride 63: ok", r.stdout)

    def test_bad_arguments_run_the_target_cases(self):
        """The default-build test-args runs lines() (guarded by SVF_TARGETS == 0x3FF): the GRAY cases appear."""
        r = subprocess.run([build()["test-args"], self.JAMO_FACE], capture_output=True, text=True)
        for name in ("init GRAY stride 8 ok", "draw GRAY bits 4 on stride 31", "draw GRAY bits 16"):
            self.assertIn("line: %s: ok" % name, r.stdout)

    def test_jset_region_longer_than_max(self):
        """A JSET block the header sizes longer than the build loads (9,246 bytes, the largest valid block; 12,321 in the
        builds that also read version 1): refused as JSET_BAD, a plain face, and neither source reads a
        byte of it past its 16-byte header (the stream callback and the mapped SVF_RD8
        reader both exit 3 on a read in the forbidden range)."""
        with open(self.JAMO_FACE, "rb") as fh:
            base = fh.read()
        flags = header(base)[0]
        self.assertTrue(flags & jamoset.FLAG_VARIABLE and flags & jamoset.FLAG_JAMO)
        # JMAP off in every build: with SVF_JMAP the load max is 65,534 and these blocks are loaded whole
        v2, v1, both = build_reader("v2only_nojmap"), build_reader("v1only_nojmap"), build_reader("nojmap_default")
        f, t = svf_synth.load(self.JAMO_FACE)
        jset_off = struct.unpack_from("<I", base, 36)[0]
        hdr1 = bytes(base[jset_off:jset_off + 16])                    # a REAL v1 block's first 16 bytes, counts intact
        hdr2 = svf_synth.packed(t, 2)[0][:16]                        # a REAL v2 block's, likewise
        self.assertEqual(struct.unpack_from("<H", hdr1, 4)[0], 1)
        self.assertEqual(struct.unpack_from("<H", hdr2, 4)[0], 2)
        # the padding follows a real header, so the build reaches the size check (not the magic): the block size the counts
        # give is not the region's length
        for pad, exes, hdr in ((JSET_LOAD_MAX + 1, both, hdr1), (20000, both, hdr1), (JSET_LOAD_MAX + 1, both, hdr2),
                               (20000, both, hdr2), (JSET_MAX + 1, v2, hdr2), (20000, v2, hdr2),
                               (JSET_LOAD_MAX + 1, v1, hdr1)):
            d = bytearray(base)
            d += bytes(-len(d) % 64)
            jset_at = len(d)
            d += hdr + b"\x00" * (pad - 16)                         # the block runs to the end of the file
            struct.pack_into("<II", d, 36, jset_at, pad)
            self.assertIsNone(jamo_tables(bytes(d))[1], "jamoset accepts the long block")
            path = os.path.join(self.tmp, "longjset.svf")
            with open(path, "wb") as fh:
                fh.write(bytes(d))
            forbid = f"--forbid={jset_at + 16}:{len(d)}"
            for exe, cfgs in (("svfdump-asan", STREAM_CONFIGS), ("svfdump-rd8", ("",) + STREAM_CONFIGS)):
                exe = exes.get(exe, exe)
                for cfg in cfgs:
                    with self.subTest(pad=pad, hdr=hdr[4], exe=os.path.relpath(exe, build()["dir"]) if exes else exe, cfg=cfg):
                        opts = [o for o in (cfg, forbid, "--trace-reads") if o]
                        code, out, err = stream_dump(path, *opts, "info", exe=exe)
                        self.clean(err)
                        self.assertEqual(code, 0, err)
                        info = dict(kv.split("=") for kv in out.decode().split())
                        self.assertEqual((info["jamo"], info["jset_bad"]), ("0", "1"))
                        if cfg:
                            self.assertIn(f"svfdump: read {jset_at} 16", err)
                        code, out, err = stream_dump(path, *opts, "glyphs", exe=exe)
                        self.clean(err)
                        self.assertEqual(code, 0, err)
                        self.assertEqual(out, expected_glyphs(bytes(d)))

    def test_bad_cache_arguments(self):
        for cfg in ("--stream=1:1024", "--stream=4:4096", "--stream=4:32", "--stream=16:8192", "--stream=4:500"):
            with self.subTest(cfg=cfg):
                code, _, err = stream_dump(self.JAMO_FACE, cfg, "info")
                self.assertEqual(code, 2, err)
                self.assertIn("SVF_E_ARG", err)

    def reads_of(self, cfg, cps):
        code, out, err = stream_dump(self.JAMO_FACE, cfg, "reads", *("U+%04X" % cp for cp in cps))
        self.assertEqual(code, 0, err)
        return [int(line.split("reads=")[1]) for line in out.decode().splitlines()]

    def test_stream_reads_per_glyph(self):
        """No cache: one call per glyph, one per non-blank piece of a syllable (at most 3); a cache serves a repeat with
        none."""
        with open(self.JAMO_FACE, "rb") as fh:
            f, t = jamo_tables(fh.read())
        sylls = (0xAC00, 0xAC01, 0xB098, 0xD7A3, 0xD55C)
        want = [sum(1 for p in jamoset.pieces_of(t, cp) if p != jamoset.BLANK) for cp in sylls]
        got = self.reads_of("--stream", sylls + (0x41,))
        self.assertEqual(got, want + [1])
        self.assertTrue(all(n <= 3 for n in got))
        got = self.reads_of("--stream=4:512", (0xAC00, 0xAC00, 0x41, 0x41))
        self.assertGreater(got[0], 0)
        self.assertEqual(got[1], 0)
        self.assertEqual(got[3], 0)

    def test_stream_short_read(self):
        """No cache: the glyph whose read is short (or fails) returns SVF_E_IO, the dump records it, later glyphs are
        right."""
        with open(self.JAMO_FACE, "rb") as fh:
            data = fh.read()
        count, cmap_off = header(data)[2], header(data)[10]
        mapped = run_dump(self.JAMO_FACE, "glyphs")
        entry = len(mapped) // count
        base = open_reads(stream_dump(self.JAMO_FACE, "--stream", "glyphs")[2])
        for k in (0, 7, count - 1):
            for mode in ("", ":error"):
                with self.subTest(glyph=k, mode=mode):
                    code, out, err = stream_dump(self.JAMO_FACE, "--stream", f"--fail-read-after={base + k}{mode}",
                                                 "glyphs", asan=True)
                    self.clean(err)
                    self.assertEqual(code, 2, err)
                    (cp,) = struct.unpack_from("<I", data, cmap_off + 8 * k)
                    self.assertEqual(glyph_errors(err), [cp])
                    want = bytearray(mapped)
                    want[k * entry + 8:(k + 1) * entry] = bytes(entry - 8)
                    self.assertEqual(out, bytes(want))

    def test_stream_short_read_at_open(self):
        """A short read of the header or a table fails the open with SVF_E_IO."""
        for n in range(4):
            with self.subTest(read=n):
                code, _, err = stream_dump(self.JAMO_FACE, "--stream", f"--fail-read-after={n}", "info", asan=True)
                self.clean(err)
                self.assertEqual(code, 2, err)
                self.assertIn("SVF_E_IO", err)

    def test_short_read_slot_is_not_served_later(self):
        """A 2-slot cache (3 KB / 1 KB blocks) and glyphs a, b, c in three blocks: a, b fill the slots, c's read
        replaces a's block and is short. Then a and c again: each is read anew, neither shows the short read's bytes
        (a slot left tagged with the old or the new block would serve them)."""
        with open(self.JAMO_FACE, "rb") as fh:
            data = fh.read()
        _, bpp, count, cw, ch, _, _, _, data_off, _, cmap_off = header(data)
        stride = (cw * bpp + 7) // 8 * ch
        parsed = jamoset.parse_svfn(data)
        cells, blocks = {}, []
        for k in range(count):
            cp, g = struct.unpack_from("<II", data, cmap_off + 8 * k)
            start, ln = v3_span(data, g)
            first, last = start // 1024, (start + ln - 1) // 1024
            if first == last and first not in blocks and any(parsed.glyphs[cp]):
                blocks.append(first)
                cells[cp] = masked(parsed.glyphs[cp], cw, ch, bpp)
            if len(cells) == 3:
                break
        a, b, c = cells
        order = (a, b, c, a, c, b)
        base = open_reads(stream_dump(self.JAMO_FACE, "--stream=3:1024", "info")[2])
        for mode in ("", ":error"):
            with self.subTest(mode=mode):
                code, out, err = stream_dump(self.JAMO_FACE, "--stream=3:1024", "--trace-reads",
                                             f"--fail-read-after={base + 2}{mode}", "cells",
                                             *("U+%04X" % cp for cp in order), asan=True)
                self.clean(err)
                self.assertEqual(code, 2, err)
                self.assertEqual(glyph_errors(err), [c])
                want = b"".join(bytes(stride) if i == 2 else cells[cp] for i, cp in enumerate(order))
                self.assertEqual(out, want)
                reads = [line.split()[2] for line in err.splitlines() if line.startswith("svfdump: read ")]
                # a, b, c (short), a again (into the emptied slot), c again (evicting b), b again
                ba, bb, bc = (str(blk * 1024) for blk in blocks)
                self.assertEqual(reads[base:], [ba, bb, bc, ba, bc, bb])

    def test_stream_short_read_replacing_block(self):
        """A 2-slot cache (3 KB / 1 KB blocks): the third block read replaces an occupied slot. When it is short, that
        syllable returns SVF_E_IO, the slot is invalidated (the block is read again when next needed) and no later cell
        shows bytes of the old block or of the short read."""
        mapped = run_dump(self.JAMO_FACE, "syllables")
        stride = (len(mapped) - 1) // (len(SYLLABLES) + len(COMPAT_JAMO))
        cps = list(SYLLABLES) + list(COMPAT_JAMO)
        base = open_reads(stream_dump(self.JAMO_FACE, "--stream=3:1024", "syllables")[2])
        for nth in (2, 3, 5, 9):
            for mode in ("", ":error"):
                with self.subTest(read=nth, mode=mode):
                    code, out, err = stream_dump(self.JAMO_FACE, "--stream=3:1024", "--trace-reads",
                                                 f"--fail-read-after={base + nth}{mode}", "syllables", asan=True)
                    self.clean(err)
                    self.assertEqual(code, 2, err)
                    bad = glyph_errors(err)
                    self.assertEqual(len(bad), 1, err)
                    want = bytearray(mapped)
                    i = cps.index(bad[0])
                    want[i * stride:(i + 1) * stride] = bytes(stride)
                    self.assertEqual(out, bytes(want))
                    reads = [line.split()[2] for line in err.splitlines() if line.startswith("svfdump: read ")]
                    failed = reads[base + nth]
                    self.assertIn(failed, reads[base + nth + 1:], "the failed block was not read again")


def rd8_calls(err):
    """svf_test_rd8 calls of an svfdump-rd8 run ("svfdump: rd8 calls=N")."""
    for line in err.splitlines():
        if line.startswith("svfdump: rd8 calls="):
            return int(line.rsplit("=", 1)[1])
    raise AssertionError("no rd8 calls line in: " + err)


class TestReadOverride(unittest.TestCase):
    """A build overriding SVF_RD8 (an AVR PROGMEM stand-in: tests/test_rd8.h) draws mapped and streamed faces in one
    binary. Mapped face bytes reach the library only at an alias of 0x5A bytes read through SVF_RD8; streamed bytes
    (RAM) are read with plain loads and an SVF_RD8 call on them exits 3."""

    def setUp(self):
        build()
        self.tmp = tempfile.mkdtemp(prefix="svf-rd8-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def dump(self, face, *args):
        code, out, err = stream_dump(face, *args, exe="svfdump-rd8")
        self.assertNotIn("Sanitizer", err)
        self.assertNotIn("runtime error", err)
        self.assertEqual(code, 0, err)
        return out, rd8_calls(err)

    def test_glyphs_all_faces(self):
        for face in faces():
            with open(face, "rb") as fh:
                want = expected_glyphs(fh.read())
            with self.subTest(face=os.path.relpath(face, ROOT)):
                out, calls = self.dump(face, "glyphs")
                self.assertEqual(out, want)
                self.assertGreater(calls, 0)
                for cfg in ("--stream", "--stream=4:512"):
                    out, calls = self.dump(face, cfg, "glyphs")
                    self.assertEqual(out, want)
                    self.assertEqual(calls, 0, "SVF_RD8 used on a streamed face")

    def test_syllables(self):
        """1, 2 and 8 bpp jamo faces: composition through SVF_RD8 (mapped) and plain loads (streamed)."""
        bpp8 = synth(self.tmp, "--bpp8", "--from", SYNTH_BASE)
        for face in (os.path.join(SVF_DIR, "dos", "NEODG16A.SVF"), os.path.join(SVF_DIR, "dos", "PAPER16A.SVF"), bpp8):
            with open(face, "rb") as fh:
                want = expected_syllables(fh.read())
            with self.subTest(face=os.path.basename(face)):
                out, calls = self.dump(face, "syllables")
                self.assertEqual(out, want)
                self.assertGreater(calls, 0)
                for cfg in STREAM_CONFIGS:
                    out, calls = self.dump(face, cfg, "syllables")
                    self.assertEqual(out, want)
                    self.assertEqual(calls, 0, "SVF_RD8 used on a streamed face")


class TestFaceSize(unittest.TestCase):
    """The face state budget (spec: about 64 bytes per mapped face) on a 32-bit target, and the brief's cap of 96 on the
    host."""

    def size_with(self, cc, flags):
        tmp = tempfile.mkdtemp(prefix="svf-size-")
        try:
            exe = os.path.join(tmp, "face_size")
            r = subprocess.run([cc] + flags + ["-std=c99", "-Wall", "-Wextra", "-Werror", "-I" + os.path.join(C_DIR, "include"),
                                os.path.join(C_DIR, "tests", "face_size.c"), "-o", exe], capture_output=True, text=True)
            if r.returncode != 0:
                return None, r.stderr
            r = subprocess.run([exe], capture_output=True, text=True)
            return int(r.stdout), r.stderr
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_host_size(self):
        build()
        size, err = self.size_with(os.environ.get("CC") or shutil.which("cc") or "gcc", [])
        self.assertIsNotNone(size, err)
        self.assertLessEqual(size, 96)
        print(f"\n  sizeof(svf_face) host: {size}", file=sys.stderr)

    def test_32_bit_size(self):
        build()
        # the budget is the MCU default (SVF_JMAP 0); the desktop default adds the JMAP fields (measured below)
        size, err = self.size_with(os.environ.get("CC") or shutil.which("cc") or "gcc", ["-m32", "-DSVF_JMAP=0"])
        if size is None:
            last = err.strip().splitlines()[-1] if err.strip() else ""
            self.skipTest("no -m32 compiler/libc on this host; sizeof(svf_face) on 32 bits not measured: " + last)
        self.assertLessEqual(size, 64)
        print(f"\n  sizeof(svf_face) -m32: {size}", file=sys.stderr)
        big, _ = self.size_with(os.environ.get("CC") or shutil.which("cc") or "gcc", ["-m32", "-DSVF_JMAP=1"])
        self.assertLessEqual(big, 80)
        print(f"  sizeof(svf_face) -m32 SVF_JMAP=1: {big}", file=sys.stderr)

    def test_jset_big_adds_no_field(self):
        """SVF_JSET_BIG changes code, not svf_face: the same size with it on, in every JMAP and word-size configuration."""
        cc = os.environ.get("CC") or shutil.which("cc") or "gcc"
        build()
        for flags in ([], ["-DSVF_JMAP=0"], ["-m32", "-DSVF_JMAP=0"], ["-m32", "-DSVF_JMAP=1"]):
            off, err = self.size_with(cc, flags + ["-DSVF_JSET_BIG=0"])
            if off is None:
                self.assertTrue(flags and flags[0] == "-m32", err)
                continue
            on, err = self.size_with(cc, flags + ["-DSVF_JSET_BIG=1"])
            self.assertEqual(on, off, " ".join(flags))
            self.assertLessEqual(on, 96)
            print(f"\n  sizeof(svf_face) {' '.join(flags) or 'host'}: BIG=0 {off}, BIG=1 {on}", file=sys.stderr)



# The brief's samples (its "Áè" decomposed: A + U+0301, e + U+0300, as the marks face draws it), and a line of
# MARUS24's dy glyphs (g j p q y, brackets, underscore: dy 1..4).
LINE_TEXTS = ("다람쥐 헌 쳇바퀴에 타고파", "Score: 120 점", "뷁쌓읽 ㄱㄴㅎ ㅏ", "A\u0301e\u0300", "", "(jpg, Qy)_")
LINE_W, LINE_H = 400, 40
LINE_PLACES = ((2, 28), (-5, 10), (390, 30))    # (x, y_baseline): inside; cut at the left and top; cut at the right
INVALID_UTF8 = b"\xff\xc0\xafA\xed\xa0\x80\xf4\x90\x80\x80\xe1\x80"
PAPLG16 = os.path.join(SVF_DIR, "dos", "PAPLG16.SVF")
PAPLG18 = os.path.join(SVF_DIR, "dos", "PAPLG18.SVF")
MARUS24 = os.path.join(SVF_DIR, "dos", "MARUS24.SVF")      # per-glyph dy


def jamo16():
    """A 16 px 8x4x4 jamo face of svf/ (NEODG16A)."""
    return os.path.join(SVF_DIR, "dos", "NEODG16A.SVF")


def line_run(cmd, chain, text, *place, opts=(), exe_name="svfdump-asan"):
    """svfdump-asan OPTS... CMD PLACE... TEXT FACE...: (exit code, stdout bytes, stderr text). TEXT str or bytes."""
    exe = build()[exe_name]
    if isinstance(text, str):
        text = text.encode("utf-8")
    args = [exe.encode()] + [o.encode() for o in opts] + [cmd.encode()] + [str(v).encode() for v in place] + [text]
    r = subprocess.run(args + [p.encode() for p in chain], capture_output=True)
    return r.returncode, r.stdout, r.stderr.decode(errors="replace")


class TestLine(unittest.TestCase):
    """svf_draw_utf8 (GRAY8) and svf_measure_utf8 against tools/svfline.py over face chains."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.tmp = tempfile.mkdtemp(prefix="svf-line-")
        cls.marks = os.path.join(cls.tmp, "marks.svf")
        r = subprocess.run([sys.executable, SYNTH, "--marks", cls.marks], capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError("svf_synth --marks: " + r.stderr)
        cls.chains = ([PAPLG16, PAPLG18], [MARUS24], [jamo16()], [cls.marks, PAPLG18])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def clean(self, err):
        self.assertNotIn("Sanitizer", err)
        self.assertNotIn("runtime error", err)

    def line(self, chain, text, x, y, w=LINE_W, h=LINE_H, opts=()):
        rc, out, err = line_run("line", chain, text, w, h, x, y, opts=opts)
        self.clean(err)
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(out), w * h)
        return out

    def name(self, chain):
        return "+".join(os.path.basename(p) for p in chain)

    def test_marks_face(self):
        """The synthetic face: 16 px, 1 bpp, flags bit 2, A and e, and U+0301/U+0300 with negative bearings."""
        with open(self.marks, "rb") as fh:
            f = jamoset.parse_svfn(fh.read())
        self.assertEqual((f.cell_h, f.bpp), (16, 1))
        self.assertTrue(f.flags & jamoset.FLAG_MARKS_AT_ORIGIN)
        self.assertFalse(f.flags & jamoset.FLAG_JAMO)
        for cp in (0x41, 0x65, 0x301, 0x300):
            self.assertIn(cp, f.glyphs)
        self.assertLess(f.metrics[0x301][1], 0)
        self.assertLess(f.metrics[0x300][1], 0)

    def test_lines_match_reference(self):
        n = 0
        for chain in self.chains:
            for text in LINE_TEXTS:
                for x, y in LINE_PLACES:
                    with self.subTest(chain=self.name(chain), text=text, x=x, y=y):
                        out = self.line(chain, text, x, y)
                        want = svfline.layout(chain, text, x, y, LINE_W, LINE_H)
                        self.assertEqual(out, bytes(want))
                        drawable = any(svfline.Face.load(f).has(ord(ch)) for f in chain for ch in text.strip())
                        if drawable and (x, y) == LINE_PLACES[0]:
                            self.assertTrue(any(out), "nothing drawn")
                        n += 1
        print(f"\n  test_lines_match_reference: {n} lines match svfline", file=sys.stderr)

    def test_missing_advance(self):
        """A code point no face has draws nothing and advances by the chain's missing_advance."""
        for adv in (0, 7):
            with self.subTest(adv=adv):
                out = self.line([MARUS24], "AЀB", 2, 28, opts=["--missing-advance=%d" % adv])
                self.assertEqual(out, bytes(svfline.layout([MARUS24], "AЀB", 2, 28, LINE_W, LINE_H,
                                                           missing_advance=adv)))
        self.assertNotEqual(self.line([MARUS24], "AЀB", 2, 28),
                            self.line([MARUS24], "AЀB", 2, 28, opts=["--missing-advance=7"]))

    def test_mark_draws_over_its_base(self):
        """U+0301 after A is drawn at the pen after A minus its origin, so its ink lies over A (left of the pen)."""
        f = svfline.Face.load(self.marks)
        _, bx, _, _ = f.metrics(0x301)
        out = self.line([self.marks], "Á", 0, 20)
        alone = self.line([self.marks], "A", 0, 20)
        adv_a = f.metrics(0x41)[0]
        cols = {i % LINE_W for i, (a, b) in enumerate(zip(out, alone)) if a != b}
        self.assertTrue(cols, "the mark drew nothing")
        self.assertLess(max(cols), adv_a)
        self.assertGreaterEqual(min(cols), adv_a + bx)

    def test_mark_edge_cases(self):
        """A mark first in the line (anchored at the pen it starts at), a mark after a code point no face has (at the
        pen after the missing advance), and marks of a face without flags bit 2 (drawn at the pen, originX 0)."""
        with open(self.marks, "rb") as fh:
            data = bytearray(fh.read())
        struct.pack_into("<H", data, 6, struct.unpack_from("<H", data, 6)[0] & ~jamoset.FLAG_MARKS_AT_ORIGIN)
        plain = os.path.join(self.tmp, "marks-no-bit2.svf")
        with open(plain, "wb") as fh:
            fh.write(data)
        for chain in ([self.marks], [plain], [plain, self.marks]):
            for text in ("\u0301A", "\u0300", "\u0400\u0301e", "A\u0400\u0300", "A\u0301\u0300e", "\u0400\u0301"):
                for adv in (0, 6):
                    with self.subTest(chain=self.name(chain), text=text, adv=adv):
                        out = self.line(chain, text, 9, 20, opts=["--missing-advance=%d" % adv])
                        self.assertEqual(out, bytes(svfline.layout(chain, text, 9, 20, LINE_W, LINE_H,
                                                                   missing_advance=adv)))
        # Bit 2 moves the mark left by -bearing_x: the two faces draw "A\u0301" differently.
        self.assertNotEqual(self.line([self.marks], "A\u0301", 9, 20), self.line([plain], "A\u0301", 9, 20))

    def test_chain_baseline_paplg(self):
        """PAPLG16 'A' (cell 18, ascent 14) and PAPLG18 '가' (ascent 17) stand on one baseline: A's lowest ink row is
        the row above it, and each cell is placed at baseline - its face's ascent."""
        x, yb = 4, 30
        out = self.line([PAPLG16, PAPLG18], "A가", x, yb)
        self.assertEqual(out, bytes(svfline.layout([PAPLG16, PAPLG18], "A가", x, yb, LINE_W, LINE_H)))
        p16, p18 = svfline.Face.load(PAPLG16), svfline.Face.load(PAPLG18)
        self.assertEqual((p16.ascent, p18.ascent), (14, 17))
        adv_a = p16.metrics(0x41)[0]
        a_rows = [y for y in range(LINE_H) if any(out[y * LINE_W + c] for c in range(x, x + adv_a))]
        self.assertEqual(max(a_rows), yb - 1, "A does not stand on the baseline")
        want = bytearray(LINE_W * LINE_H)
        for face, cp, cx, top in ((p16, 0x41, x, yb - 14), (p18, 0xAC00, x + adv_a, yb - 17)):
            cov = face.coverage(cp)
            for r in range(face.cell_h):
                for c in range(face.cell_w):
                    i = (top + r) * LINE_W + cx + c
                    want[i] = max(want[i], cov[r][c])
        self.assertEqual(out, bytes(want))

    def test_utf8_invalid(self):
        """Overlong, surrogate, past U+10FFFF and truncated sequences: U+FFFD per maximal subpart when the chain has
        it (the marks face does), else skipped; every cut of the bytes too, in a buffer of exactly its length (ASan)."""
        self.assertEqual("".join("�" if c is None else chr(c) for c in svfline.decode(INVALID_UTF8)),
                         INVALID_UTF8.decode("utf-8", "replace"))
        for chain in self.chains:
            for adv in (0, 5):
                with self.subTest(chain=self.name(chain), adv=adv):
                    out = self.line(chain, INVALID_UTF8, 2, 28, opts=["--missing-advance=%d" % adv])
                    self.assertEqual(out, bytes(svfline.layout(chain, INVALID_UTF8, 2, 28, LINE_W, LINE_H,
                                                               missing_advance=adv)))
        chain = [self.marks, PAPLG18]
        self.assertNotEqual(self.line(chain, INVALID_UTF8, 2, 28), self.line(chain, b"A", 2, 28))
        for n in range(len(INVALID_UTF8) + 1):
            with self.subTest(cut=n):
                text = INVALID_UTF8[:n]
                self.assertEqual(self.line(chain, text, 2, 28),
                                 bytes(svfline.layout(chain, text, 2, 28, LINE_W, LINE_H)))

    def measure(self, chain, text, opts=()):
        rc, out, err = line_run("measure", chain, text, opts=opts)
        self.clean(err)
        self.assertEqual(rc, 0, err)
        w, a, d = (int(kv.split("=")[1]) for kv in out.decode().split())
        return w, a, d

    def test_measure_matches(self):
        for chain in self.chains:
            for text in LINE_TEXTS + (INVALID_UTF8,):
                with self.subTest(chain=self.name(chain), text=text):
                    self.assertEqual(self.measure(chain, text), svfline.measure(chain, text))
        self.assertEqual(self.measure([MARUS24], ""), (0, 0, 0))
        self.assertEqual(self.measure([MARUS24], "Score"), svfline.measure([MARUS24], "Score"))
        self.assertEqual(self.measure([MARUS24], "Score")[1:], (20, 4))
        self.assertEqual(self.measure([MARUS24], "jpg")[1:], (20 - 4, 24 - 20 + 4), "MARUS24's dy is not in the extent")

    def test_stream_faces(self):
        """Streamed faces (no cache: composing needs twice the cell of scratch; with a cache) draw the mapped line."""
        for cfg in STREAM_CONFIGS:
            for chain in ([MARUS24], [PAPLG16, PAPLG18]):
                with self.subTest(cfg=cfg, chain=self.name(chain)):
                    self.assertEqual(self.line(chain, LINE_TEXTS[0], 2, 28, opts=[cfg]),
                                     bytes(svfline.layout(chain, LINE_TEXTS[0], 2, 28, LINE_W, LINE_H)))

    def test_scratch_too_small(self):
        for opts, chain in (((), [PAPLG16, PAPLG18]), (("--stream",), [MARUS24])):
            with self.subTest(opts=opts):
                rc, _, err = line_run("line", chain, "A", LINE_W, LINE_H, 2, 28, opts=list(opts) + ["--scratch-delta=-1"])
                self.clean(err)
                self.assertEqual(rc, 2)
                self.assertIn("SVF_E_NOMEM", err)
                rc, _, err = line_run("line", chain, "A", LINE_W, LINE_H, 2, 28, opts=list(opts) + ["--scratch-delta=0"])
                self.assertEqual(rc, 0, err)

    def test_read_error_skips_one_glyph(self):
        """A failed read stops drawing that glyph only: the others are drawn and advance as usual; SVF_E_IO at the end."""
        rc, _, err = line_run("line", [MARUS24], "", LINE_W, LINE_H, 2, 28, opts=["--stream"])
        opened = open_reads(err)
        rc, out, err = line_run("line", [MARUS24], "ABC", LINE_W, LINE_H, 2, 28,
                                opts=["--stream", "--fail-read-after=%d" % (opened + 1)])
        self.clean(err)
        self.assertEqual(rc, 2)
        self.assertIn("SVF_E_IO", err)
        chain = svfline.load_chain([MARUS24])
        want = svfline.draw_gray8([p for k, p in enumerate(svfline.placements(chain, "ABC", 2, 28)) if k != 1],
                                  LINE_W, LINE_H)
        self.assertEqual(out, bytes(want))
        self.assertNotEqual(out, bytes(svfline.layout([MARUS24], "ABC", 2, 28, LINE_W, LINE_H)))

    def test_bad_arguments(self):
        rc, _, err = line_run("line", [MARUS24], "A", 0, LINE_H, 2, 28)
        self.assertEqual(rc, 2)
        self.assertIn("SVF_E_ARG", err)


TARGET_SIZES = ((128, 64), (100, 37))   # 100 x 37: mono-row rows of 13 bytes, a last mono-page page of 5 rows
TARGET_FILL = 0x5A                      # every buffer is pre-filled: untouched bytes are compared too


def target_places(w, h):
    """(x, y_baseline) per target: inside, cut at the left and top, cut at the right and bottom."""
    return ((2, 28), (-5, 10), (w - 10, h - 3))


# INDEXED8 in the sweeps: the spec's ramps (16, 3) and (64, 63) over fills 0, base - 1 and base + 1, and (0, 255) once
# (fill 0). The fill is a variant parameter: a sweep's checks compare against kt.get("fill", TARGET_FILL).
INDEXED8_VARIANTS = tuple(dict(index_base=b, index_levels=n, fill=f)
                          for b, n in ((16, 3), (64, 63)) for f in (0, b - 1, b + 1)) + \
                    (dict(index_base=0, index_levels=255, fill=0),)


# GRAY in the sweeps: every bits x bit order (the parametric kind of svf.h; lsb_first has no effect at bits 8, the run
# is kept so the flag is proven inert there).
GRAY_VARIANTS = tuple({"gray_bits": b, "lsb_first": o} for b in (1, 2, 4, 8) for o in (False, True))


def kind_runs(kinds, gray=GRAY_VARIANTS):
    """(kind, kt) per run of a sweep: kt = {} for every kind but indexed8, which runs once per variant (kt holds its
    index_base, index_levels and fill), and gray, which runs once per @p gray variant (kt holds gray_bits and
    lsb_first): pass **kt to the target helpers."""
    return [(k, kt) for k in kinds
            for kt in (INDEXED8_VARIANTS if k == "indexed8" else gray if k == "gray" else ({},))]


def row_bytes(kind, w, kt):
    """The least stride of a target of @p kind, @p w wide, for the run @p kt of kind_runs (gray: its gray_bits)."""
    return svfline.target_row_bytes(kind, w, kt.get("gray_bits", 8))


# every sweep covers svfline.TARGET_KINDS
SWEEP_KINDS = tuple(svfline.TARGET_KINDS)
BUFFER_KINDS = tuple(k for k in SWEEP_KINDS if k != "cb")


def pack565(rgb):
    """The RGB565 value of the channels (r, g, b): 5, 6 and 5 bits."""
    return rgb[0] << 11 | rgb[1] << 5 | rgb[2]


def pack555(rgb):
    """The RGB555 value of the channels (r, g, b): 5, 5 and 5 bits."""
    return rgb[0] << 10 | rgb[1] << 5 | rgb[2]


class TestReferenceFormulas(unittest.TestCase):
    """The packed kinds' reference formulas (pure Python): ramp level, the 5/5/5 and 8-bit blends, byte orders."""

    def test_gray_levels(self):
        # one pixel at x=0, MSB first; (bits, cov, threshold) -> the byte
        for bits, cov, thr, want in ((1, 85, 128, 0x00), (1, 170, 128, 0x80), (1, 85, 1, 0x80), (1, 255, 255, 0x80),
                                     (1, 254, 255, 0x00), (1, 1, 0, 0x80), (2, 85, 128, 0x40), (2, 170, 128, 0x80),
                                     (2, 255, 128, 0xC0), (4, 85, 128, 0x50), (4, 170, 128, 0xA0), (4, 255, 128, 0xF0),
                                     (8, 85, 0, 85), (8, 200, 0, 200)):
            t = svfline.Target("gray", 8, 1, gray_bits=bits, threshold=thr)
            t.put(0, 0, cov)
            self.assertEqual(t.buf[0], want, (bits, cov, thr))

    def test_gray_bit_order_and_max(self):
        t = svfline.Target("gray", 4, 1, gray_bits=4, lsb_first=True)
        t.put(1, 0, 255); t.put(0, 0, 85); t.put(0, 0, 17)   # 17 -> level 1 < 5: max keeps 5
        self.assertEqual(bytes(t.buf), bytes((0xF5, 0x00)))
        t = svfline.Target("gray", 9, 1, gray_bits=2)          # 9 px: 3 bytes, the last holds 1 px + 6 padding bits
        t.put(8, 0, 255)
        self.assertEqual(bytes(t.buf), bytes((0, 0, 0xC0)))
        self.assertEqual(svfline.target_row_bytes("gray", 9, gray_bits=2), 3)
        self.assertEqual(svfline.target_row_bytes("gray", 9, gray_bits=1), 2)
        with self.assertRaises(ValueError):
            svfline.Target("gray", 4, 1, gray_bits=3)

    def test_gray_equalities(self):
        for cov in range(1, 256):
            for thr in (0, 1, 128, 255):
                a = svfline.Target("gray", 8, 1, gray_bits=1, threshold=thr); a.put(3, 0, cov)
                b = svfline.Target("mono-row", 8, 1, threshold=thr); b.put(3, 0, cov)
                self.assertEqual(a.buf, b.buf, (cov, thr))
            c = svfline.Target("gray", 2, 1, gray_bits=8); c.put(1, 0, cov)
            d = svfline.Target("gray8", 2, 1); d.put(1, 0, cov)
            self.assertEqual(c.buf, d.buf, cov)

    def test_gray_level_rule_exhaustive(self):
        for bits in (2, 4):
            for cov in range(1, 256):
                t = svfline.Target("gray", 8, 1, gray_bits=bits)
                t.put(0, 0, cov)
                self.assertEqual(t.buf[0] >> (8 - bits), (cov * ((1 << bits) - 1) + 127) // 255, (bits, cov))

    def test_gray_phase_table(self):
        for bits in (1, 2, 4):
            ppb, n = 8 // bits, (1 << bits) - 1
            for lsb in (False, True):
                for x in range(2 * ppb):
                    t = svfline.Target("gray", 2 * ppb, 1, gray_bits=bits, lsb_first=lsb)
                    t.put(x, 0, 255)
                    p = x % ppb
                    want = bytearray(2)
                    want[x // ppb] = n << (bits * p if lsb else 8 - bits * (p + 1))
                    self.assertEqual(bytes(t.buf), bytes(want), (bits, lsb, x))

    def test_gray_multi_pixel_and_max_update(self):
        t = svfline.Target("gray", 2, 1, gray_bits=4)
        t.put(0, 0, 17); t.put(1, 0, 255); t.put(0, 0, 85)    # levels 1, 15, then 5 over 1
        self.assertEqual(t.buf[0], 0x5F)
        t.put(0, 0, 17)                                         # lower: kept
        self.assertEqual(t.buf[0], 0x5F)
        t = svfline.Target("gray", 4, 1, gray_bits=2)           # MSB first: 1, 2, 3, 0 -> 01 10 11 00
        for x, c in ((0, 85), (1, 170), (2, 255)):
            t.put(x, 0, c)
        self.assertEqual(t.buf[0], 0x6C)
        t = svfline.Target("gray", 4, 1, gray_bits=2, lsb_first=True)   # 11 10 01 00 read from the high end
        for x, c in ((0, 85), (1, 170), (2, 255)):
            t.put(x, 0, c)
        self.assertEqual(t.buf[0], 0x39)
        t = svfline.Target("gray", 8, 1, gray_bits=1, lsb_first=True)
        t.put(0, 0, 255); t.put(3, 0, 255); t.put(7, 0, 255)
        self.assertEqual(t.buf[0], 0x89)

    def test_gray_rows_and_stride(self):
        t = svfline.Target("gray", 4, 2, gray_bits=4)
        t.put(1, 1, 255)
        self.assertEqual(bytes(t.buf), bytes((0, 0, 0x0F, 0)))
        t = svfline.Target("gray", 5, 2, stride=4, gray_bits=4)
        t.put(4, 1, 255)
        self.assertEqual(bytes(t.buf), bytes(4) + bytes((0, 0, 0xF0, 0)))
        buf = bytearray(b"\xA5" * 8)                            # existing content: neighbours and padding stay
        t = svfline.Target("gray", 5, 2, stride=4, gray_bits=4, buf=buf)
        t.put(1, 1, 255)
        self.assertEqual(bytes(buf), bytes.fromhex("A5A5A5A5AFA5A5A5"))

    def test_index_level_values(self):
        for cov, want in ((85, 1), (170, 2), (255, 3), (42, 0), (43, 1)):
            self.assertEqual(svfline.index_level(cov, 3, 128), want, cov)
        self.assertEqual([svfline.index_level(c, 255, 128) for c in range(256)], list(range(256)))
        self.assertEqual((svfline.index_level(127, 1, 128), svfline.index_level(128, 1, 128)), (0, 1))
        self.assertEqual((svfline.index_level(0, 1, 0), svfline.index_level(1, 1, 0)), (0, 1))

    def test_blend555_equals_blend565_r_and_b(self):
        for cb in range(32):
            for cf in range(32):
                # both values built from the same (r, g, b) channel tuples; green is 0 (its width differs)
                bg565, fg565 = pack565((cb, 0, cb)), pack565((cf, 0, cf))
                bg555, fg555 = pack555((cb, 0, cb)), pack555((cf, 0, cf))
                for cov in range(256):
                    w565 = svfline.blend565(fg565, bg565, cov)
                    w555 = svfline.blend555(fg555, bg555, cov)
                    self.assertEqual((w555 >> 10 & 31, w555 & 31), (w565 >> 11 & 31, w565 & 31), (cb, cf, cov))
                    self.assertEqual(w555 >> 5 & 31, 0)
                    self.assertEqual(w555 >> 15, 0)

    def test_blend555_green_and_asymmetric_channels(self):
        def chan(bg, fg, cov):   # the 5-bit blend, written out
            return (bg * (255 - cov) + fg * cov + 127) // 255

        for cov in (1, 64, 100, 128, 200, 254):
            for bg, fg in (((0, 0, 31), (31, 0, 0)), ((3, 17, 29), (30, 8, 1)), ((31, 31, 0), (0, 5, 31))):
                want = pack555(tuple(chan(b, f, cov) for b, f in zip(bg, fg)))
                self.assertEqual(svfline.blend555(pack555(fg), pack555(bg), cov), want, (bg, fg, cov))
                t = svfline.Target("rgb555", 1, 1, fg565=pack555(fg), bg565=pack555(bg))
                t.put(0, 0, cov)
                self.assertEqual(bytes(t.buf), want.to_bytes(2, "little"))
        # a red/blue swap would be caught: red ink on a blue background at coverage 100
        self.assertEqual(svfline.blend555(31 << 10, 31, 100), (12 << 10) | 19)

    def test_blend888_bounds(self):
        self.assertEqual(svfline.blend888(0xABCDEF, 0x123456, 0), 0x123456)
        self.assertEqual(svfline.blend888(0xABCDEF, 0x123456, 255), 0xABCDEF)
        self.assertEqual(svfline.blend888(0xFFFFFF, 0x000000, 128), 0x808080)

    def test_put_byte_orders(self):
        def one(kind, cov, **t):
            tg = svfline.Target(kind, 1, 1, **t)
            tg.put(0, 0, cov)
            return bytes(tg.buf)

        self.assertEqual(one("xrgb8888", 255, fg888=0x8C123456), bytes((0x56, 0x34, 0x12, 0x8C)))
        self.assertEqual(one("rgb888", 255, fg888=0x8C123456), bytes((0x56, 0x34, 0x12)))
        self.assertEqual(one("rgb555", 255, fg565=0xFFFF), (0xFFFF).to_bytes(2, "little"))
        self.assertEqual(one("rgb555", 255, fg565=0x7FFF), (0x7FFF).to_bytes(2, "little"))
        self.assertEqual(one("rgb555", 255, fg565=0xFFFF, big_endian=True), (0xFFFF).to_bytes(2, "big"))
        self.assertEqual(one("rgb555", 255, fg565=0x83E0, big_endian=True), bytes((0x83, 0xE0)))
        self.assertEqual(one("rgb555", 255, fg565=0x83E0), bytes((0xE0, 0x83)))
        tg = svfline.Target("indexed8", 1, 1, buf=bytearray([0]), index_base=16, index_levels=3)
        tg.put(0, 0, 170)
        self.assertEqual(bytes(tg.buf), bytes((18,)))
        tg = svfline.Target("indexed8", 1, 1, buf=bytearray([0]), index_base=16, index_levels=3)
        tg.put(0, 0, 42)   # level 0: the pixel stays
        self.assertEqual(bytes(tg.buf), bytes((0,)))
        tg = svfline.Target("indexed8", 1, 1, buf=bytearray([200]), index_base=16, index_levels=3)
        tg.put(0, 0, 170)
        self.assertEqual(bytes(tg.buf), bytes((200,)))

    def test_put_partial_coverage_asymmetric_888(self):
        # cov 128, fg R,G,B = 7F,20,E0 and bg = 10,80,30: each channel (bg * 127 + fg * 128 + 127) // 255, worked by
        # hand: R (16*127 + 127*128 + 127) // 255 = 72 = 0x48, G (128*127 + 32*128 + 127) // 255 = 80 = 0x50,
        # B (48*127 + 224*128 + 127) // 255 = 136 = 0x88. The byte order is B, G, R (then the fg X byte, 0x6C).
        def one(kind):
            tg = svfline.Target(kind, 1, 1, fg888=0x6C7F20E0, bg888=0xEE108030)
            tg.put(0, 0, 128)
            return bytes(tg.buf)

        self.assertEqual(one("xrgb8888"), bytes((0x88, 0x50, 0x48, 0x6C)))
        self.assertEqual(one("rgb888"), bytes((0x88, 0x50, 0x48)))

    def test_index_level_levels_below_one_invalid(self):
        for levels in (0, -1):
            with self.assertRaises(ValueError):
                svfline.index_level(128, levels, 128)
        self.assertEqual([svfline.index_level(c, 1, 0) for c in (0, 1, 255)], [0, 1, 1])
        self.assertEqual([svfline.index_level(c, 1, 128) for c in (127, 128, 255)], [0, 1, 1])

    def test_target_row_bytes(self):
        self.assertEqual([svfline.target_row_bytes(k, 10) for k in svfline.TARGET_KINDS[5:9]], [10, 20, 40, 30])
        self.assertEqual(svfline.TARGET_KINDS[-1], "gray")
        self.assertEqual(svfline.target_row_bytes("gray", 10), 10)


class TestSvfdumpTargetOptions(unittest.TestCase):
    """svfdump's target options: empty values refused, --misalign, targets too large for the buffer limit."""

    def run_opts(self, *opts, w=40, h=20, kind="gray8"):
        return line_run("line", [MARUS24], "Ag", w, h, 2, 15, opts=["--target=" + kind] + list(opts))

    def test_misalign(self):
        base = self.run_opts()
        self.assertEqual(base[0], 0, base[2])
        for k in range(4):
            rc, out, err = self.run_opts("--misalign=%d" % k)
            self.assertEqual(rc, 0, err)
            self.assertEqual(out, base[1], "misalign %d" % k)
            self.assertNotIn("guard bytes", err)
        for bad in ("4", "-1", "", "x"):
            self.assertEqual(self.run_opts("--misalign=" + bad)[0], 1, bad)

    def test_empty_values_refused(self):
        for opt in ("--index-base=", "--index-levels=", "--misalign=", "--fg888=", "--bg888="):
            rc, _, err = self.run_opts(opt)
            self.assertEqual(rc, 1, opt + err)

    def test_every_empty_value_refused(self):
        for opt in ("--stream=", "--tables-bytes=", "--fail-read-after=", "--forbid=", "--missing-advance=",
                    "--target=", "--stride=", "--buf-delta=", "--clip=", "--fg=", "--bg=", "--index-base=",
                    "--index-levels=", "--fg888=", "--bg888=", "--misalign=", "--threshold=", "--fill=",
                    "--gray-bits=", "--syllable-cache=", "--scale=", "--scratch-delta="):
            rc, _, err = self.run_opts(opt)
            self.assertEqual(rc, 1, opt + err)

    def test_indexed8_library_defaults(self):
        """--target=indexed8 without --index-base / --index-levels is the library's default (base 0, 255 levels): the
        bytes are the GRAY8 line's. (opts_of must not inject a ramp there.)"""
        rc, idx, err = self.run_opts("--fill=0", kind="indexed8", w=60, h=30)
        self.assertEqual(rc, 0, err)
        rc, gray0, err = self.run_opts("--fill=0", kind="gray8", w=60, h=30)
        self.assertEqual(rc, 0, err)
        self.assertEqual(idx, gray0)
        self.assertNotEqual(set(idx), {0})
        self.assertEqual(TargetMixin.opts_of("indexed8").count("--index-base=0"), 0)
        self.assertFalse([o for o in TargetMixin.opts_of("indexed8") if o.startswith("--index-")])

    def test_fg888_leading_sign_refused(self):
        for opt in ("--fg888=", "--bg888="):
            for bad in ("-1", "-0", " -1", "+1", " 1"):
                self.assertEqual(self.run_opts(opt + bad, kind="rgb888")[0], 1, opt + bad)
            self.assertEqual(self.run_opts(opt + "0xFFFFFFFF")[0], 0)  # parsed on any kind

    def test_numeric_options_one_parser(self):
        """--fg --bg --threshold --fill --index-base --index-levels (and the 888 pair): decimal or 0x hex digits only;
        an empty value, a leading '+', '-' or blank, a trailing junk char, a value over the option's maximum and
        anything strtoul would wrap are refused (exit 1); the maxima themselves are accepted."""
        maxima = {"--fg": 0xFFFF, "--bg": 0xFFFF, "--threshold": 255, "--fill": 255, "--index-base": 255,
                  "--index-levels": 255, "--gray-bits": 255, "--fg888": 0xFFFFFFFF, "--bg888": 0xFFFFFFFF}
        for opt, mx in maxima.items():
            kind = "indexed8" if opt.startswith("--index") else "gray" if opt == "--gray-bits" else "gray8"
            for bad in ("", "+1", "-1", "-0", " 1", "1 ", "x", "0x", "1x", str(mx + 1), hex(mx + 1),
                        "18446744073709551616", "99999999999999999999", "4294967297"):
                with self.subTest(opt=opt, value=bad):
                    self.assertEqual(self.run_opts(opt + "=" + bad, kind=kind)[0], 1, opt + "=" + bad)
            for good in (str(mx), hex(mx), "0", "0x0", "7"):
                with self.subTest(opt=opt, value=good):
                    rc, _, err = self.run_opts(opt + "=" + good, kind=kind)
                    # parsed: indexed8 may still refuse a ramp past index 255, gray a bit count other than 1/2/4/8
                    # (exit 2, the library's rule)
                    self.assertIn(rc, (0, 2) if kind in ("indexed8", "gray") else (0,), opt + "=" + good + err)

    def test_buf_delta_range(self):
        for bad in ("9223372036854775807", "-9223372036854775808", "1099511627776", "-1099511627776"):
            rc, _, err = self.run_opts("--buf-delta=" + bad)
            self.assertEqual(rc, 1, bad + err)
        self.assertEqual(self.run_opts("--buf-delta=-5")[0], 2)   # too short: the library refuses the target

    def test_huge_targets_refused_cleanly(self):
        for kind in ("xrgb8888", "rgb888", "rgb565", "rgb555", "indexed8", "gray8", "gray"):
            rc, out, err = self.run_opts(w=32767, h=32767, kind=kind)
            self.assertEqual(rc, 1, kind + err)
            self.assertIn("too large", err)
            self.assertNotIn("Sanitizer", err)
            self.assertNotIn("runtime error", err)


class TestBlend16(unittest.TestCase):
    """c/tests/test_blend16.c: the level, blend and palette formulas under a 16-bit int model, at every value."""

    def test_runs(self):
        r = subprocess.run(["make", "-s", "-C", C_DIR, "O=" + build()["dir"], "test-blend16"], capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([os.path.join(build()["dir"], "test-blend16")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("blend16: OK", r.stdout)


class TestVbe(unittest.TestCase):
    """c/tests/test_vbe.c: ports/dos/vbe_select.c on hostile mode lists and mode blocks, under the sanitizers."""

    def test_runs(self):
        r = subprocess.run(["make", "-s", "-C", C_DIR, "O=" + build()["dir"], "test-vbe"], capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([os.path.join(build()["dir"], "test-vbe")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)
        self.assertNotIn("runtime error", r.stderr)
        self.assertIn("vbe: OK", r.stdout)


# ---- vesa-lines.txt: the C reader (c/tests/vesa_lines_dump.c) and tools/vesa_lines.py ----

VESA_LINES = os.path.join(C_DIR, "ports", "dos", "vesa-lines.txt")
GOOD_HEAD = ("[colours]\n"
             "background | 0x0010 | 0x0010 | 0x000084 | 0 | 0\n"
             "white | 0xFFFF | 0x7FFF | 0xFFFFFF | 16 | 3\n"
             "yellow | 0xFFE0 | 0x7FE0 | 0xFFFF00 | 32 | 3\n")
GOOD_LINE = "PAPLG16.SVF | 1/1 | 16 | 40 | white | abc\n"


def dump_exe():
    return os.path.join(build()["dir"], "vesa-lines-dump")


def write_tmp(tmp, data, name="v.txt"):
    path = os.path.join(tmp, name)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def both_read(data):
    """(python, c) outcomes of reading @p data: None when accepted, else (line_no, message). The C side is the exit
    code 1 and stderr `vesa-lines: line N: message` of vesa-lines-dump --print-table."""
    import vesa_lines
    with tempfile.TemporaryDirectory(prefix="svf-vl-") as tmp:
        path = write_tmp(tmp, data)
        try:
            vesa_lines.parse(path)
            py = None
        except vesa_lines.VesaLinesError as e:
            py = (e.line_no, e.message)
        r = subprocess.run([dump_exe(), "--print-table", path], capture_output=True)
        if r.returncode == 0:
            c = None
            if py is None:   # both accept: the parsed tables print the same, text included (a cut last byte shows)
                assert r.stdout.decode("utf-8") == vesa_lines.print_table(vesa_lines.parse(path), 8), data
        else:
            err = r.stderr.decode("utf-8", "replace")
            assert r.returncode == 1 and err.startswith("vesa-lines: line "), (r.returncode, err)
            n, msg = err[len("vesa-lines: line "):].rstrip("\n").split(": ", 1)
            c = (int(n), msg)
    return py, c


class TestVesaLines(unittest.TestCase):
    """The one parser of vesa-lines.txt in two languages: the same table, the same palette, the same refusals at the
    same line, and the Python expected_buffer the DOS run is held to."""

    def agree(self, data, expect_line=None):
        py, c = both_read(data)
        self.assertEqual(py, c, "the readers differ on %r" % (data,))
        if expect_line is None:
            self.assertIsNone(py, "expected accepted: %r" % (py,))
        else:
            self.assertIsNotNone(py, "expected a refusal at line %d" % expect_line)
            self.assertEqual(py[0], expect_line, py)
        return py

    def test_dump_equals_python(self):
        import vesa_lines
        table = vesa_lines.parse(VESA_LINES)
        for dac in (8, 6):
            args = [dump_exe(), "--print-table", VESA_LINES] + (["--dac", "6"] if dac == 6 else [])
            r = subprocess.run(args, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.decode("utf-8"), vesa_lines.print_table(table, dac))
        out = vesa_lines.print_table(table, 8)
        self.assertEqual(len(table.colours), 4)
        self.assertEqual(len(table.lines), 5)
        self.assertIn("colour name=white rgb565=0xFFFF rgb555=0x7FFF rgb888=0xFFFFFF base=16 levels=3\n", out)
        self.assertIn("background=background\n", out)
        self.assertIn("line faces=PAPLG16.SVF+PAPLG18.SVF scale=3/2 x=16 baseline=180 colour=scaled "
                      "text=스케일 3/2: 가나다 Score 120 점\n", out)
        self.assertEqual(out.count("palette["), 256)

    def test_palette_values(self):
        import vesa_lines
        table = vesa_lines.parse(VESA_LINES)
        pal = vesa_lines.palette(table, 8)
        self.assertEqual(len(pal), 256)
        self.assertEqual(pal[0], (132, 0, 0, 0))             # B G R pad
        self.assertEqual(pal[17], (173, 85, 85, 0))          # (132 * 2 + 255 + 1) // 3, (0 * 2 + 255 + 1) // 3
        self.assertEqual(pal[35], (0, 255, 255, 0))          # yellow
        self.assertEqual(pal[127], (255, 255, 255, 0))
        self.assertEqual(pal[200], (132, 0, 0, 0))
        r = subprocess.run([dump_exe(), "--print-table", VESA_LINES], capture_output=True, text=True)
        rows = {int(l[8:l.index("]")]): l.split("=")[1] for l in r.stdout.splitlines() if l.startswith("palette[")}
        self.assertEqual(rows[0], "84 00 00")
        self.assertEqual(rows[17], "AD 55 55")
        self.assertEqual(rows[35], "00 FF FF")
        self.assertEqual(rows[127], "FF FF FF")
        self.assertEqual(rows[200], "84 00 00")
        self.assertEqual(vesa_lines.palette(table, 6)[17], (173 >> 2, 85 >> 2, 85 >> 2, 0))

    def test_vesa_lines_limits(self):
        # 16 vs 17 colours (ramps of 3 levels, 4 apart)
        def colours(n):
            rows = ["background | 0x10 | 0x10 | 0x84 | 0 | 0"]
            rows += ["c%d | 0xFFFF | 0x7FFF | 0xFFFFFF | %d | 3" % (i, 1 + 4 * i) for i in range(n - 1)]
            return "[colours]\n" + "\n".join(rows) + "\n"
        self.agree(colours(16))
        self.agree(colours(17), 18)
        # 32 vs 33 lines
        self.agree(GOOD_HEAD + "[lines]\n" + GOOD_LINE * 32)
        self.agree(GOOD_HEAD + "[lines]\n" + GOOD_LINE * 33, 5 + 33)
        # 4 vs 5 faces
        names = ["A%d.SVF" % i for i in range(5)]
        self.agree(GOOD_HEAD + "[lines]\n%s | 1/1 | 0 | 0 | white | x\n" % "+".join(names[:4]))
        self.agree(GOOD_HEAD + "[lines]\n%s | 1/1 | 0 | 0 | white | x\n" % "+".join(names), 6)
        # a 512-byte line (newline included) and a 513-byte one, with a three-byte letter in the text
        prefix = "PAPLG16.SVF|1/1|0|10|white|"
        for total, line_no in ((512, None), (513, 6)):
            pad = total - 1 - len(prefix) - 3
            text = "가" + "a" * pad
            data = (GOOD_HEAD + "[lines]\n" + prefix + text + "\n").encode("utf-8")
            self.assertEqual(len(data) - len(GOOD_HEAD) - 8, total)
            self.agree(data, line_no)
        # the last line without a newline: 512 bytes accepted, 513 refused
        for total, line_no in ((512, None), (513, 6)):
            data = (GOOD_HEAD + "[lines]\n" + prefix + "a" * (total - len(prefix))).encode("utf-8")
            self.agree(data, line_no)
        # an empty text is accepted; an empty numeric or name field is not
        self.agree(GOOD_HEAD + "[lines]\nPAPLG16.SVF | 1/1 | 16 | 40 | white |\n")
        for bad in ("PAPLG16.SVF | | 16 | 40 | white | a\n", "PAPLG16.SVF | 1/1 | | 40 | white | a\n",
                    "PAPLG16.SVF | 1/1 | 16 | | white | a\n", "PAPLG16.SVF | 1/1 | 16 | 40 | | a\n",
                    " | 1/1 | 16 | 40 | white | a\n"):
            self.agree(GOOD_HEAD + "[lines]\n" + bad, 6)
        self.agree("[colours]\nbackground | 0x10 | 0x10 | 0x84 | 0 |\n", 2)
        self.agree("[colours]\n | 0x10 | 0x10 | 0x84 | 0 | 0\n", 2)
        # the trim rule: spaces and tabs at both ends of every field, the inner ones stay
        import vesa_lines
        with tempfile.TemporaryDirectory(prefix="svf-vl-") as tmp:
            path = write_tmp(tmp, GOOD_HEAD + "[lines]\n \t PAPLG16.SVF\t|\t1/1 | 16 |40|\twhite  |  a b  \n")
            t = vesa_lines.parse(path)
            self.assertEqual(t.lines[0].text, "a b")
            r = subprocess.run([dump_exe(), "--print-table", path], capture_output=True, text=True)
            self.assertIn("colour=white text=a b\n", r.stdout)
        # a name of 31 bytes is accepted, 32 refused
        self.agree("[colours]\nbackground | 1 | 1 | 1 | 0 | 0\n" + "n" * 31 + " | 1 | 1 | 1 | 2 | 3\n")
        self.agree("[colours]\nbackground | 1 | 1 | 1 | 0 | 0\n" + "n" * 32 + " | 1 | 1 | 1 | 2 | 3\n", 3)

    def test_vesa_lines_malformed(self):
        ok = GOOD_HEAD + "[lines]\n" + GOOD_LINE
        self.agree(ok)

        def line(s):
            return GOOD_HEAD + "[lines]\n" + s + "\n"
        cases = [
            ("5 fields", line("PAPLG16.SVF | 1/1 | 16 | 40 | white"), 6),
            ("7 fields", line("PAPLG16.SVF | 1/1 | 16 | 40 | white | a | b"), 6),
            ("dotdot", line("..\\X.SVF | 1/1 | 16 | 40 | white | a"), 6),
            ("drive", line("C:X.SVF | 1/1 | 16 | 40 | white | a"), 6),
            ("lower", line("x.svf | 1/1 | 16 | 40 | white | a"), 6),
            ("slash", line("A/B.SVF | 1/1 | 16 | 40 | white | a"), 6),
            ("long name", line("ABCDEFGHI.SVF | 1/1 | 16 | 40 | white | a"), 6),
            ("no ext", line("ABC | 1/1 | 16 | 40 | white | a"), 6),
            ("empty entry", line("A.SVF+ | 1/1 | 16 | 40 | white | a"), 6),
            ("dot first", line(".A.SVF | 1/1 | 16 | 40 | white | a"), 6),
            ("scale 0/1", line("A.SVF | 0/1 | 16 | 40 | white | a"), 6),
            ("scale 17/1", line("A.SVF | 17/1 | 16 | 40 | white | a"), 6),
            ("scale 1/0", line("A.SVF | 1/0 | 16 | 40 | white | a"), 6),
            ("scale no slash", line("A.SVF | 2 | 16 | 40 | white | a"), 6),
            ("x 32768", line("A.SVF | 1/1 | 32768 | 40 | white | a"), 6),
            ("baseline -32769", line("A.SVF | 1/1 | 16 | -32769 | white | a"), 6),
            ("unknown colour", line("A.SVF | 1/1 | 16 | 40 | pink | a"), 6),
            ("colour background", line("A.SVF | 1/1 | 16 | 40 | background | a"), 6),
            ("bad number", line("A.SVF | 1/1 | 1_6 | 40 | white | a"), 6),
            ("invalid utf-8", GOOD_HEAD.encode() + b"[lines]\nA.SVF | 1/1 | 16 | 40 | white | a\xff\n", 6),
            ("invalid utf-8 in a comment", b"# \xff\n" + ok.encode(), 1),
            ("overlong utf-8", GOOD_HEAD.encode() + b"[lines]\nA.SVF | 1/1 | 16 | 40 | white | \xc0\x80\n", 6),
            ("nul", GOOD_HEAD.encode() + b"[lines]\nA.SVF | 1/1 | 16 | 40 | white | a\x00b\n", 6),
            ("extra header", GOOD_HEAD + "[extra]\n", 5),
            ("repeated lines", ok + "[lines]\n", 7),
            ("colours after lines", ok + "[colours]\n", 7),
            ("repeated colours", GOOD_HEAD + "[colours]\n", 5),
            ("record first", GOOD_LINE + ok, 1),
            ("lines first", "[lines]\n" + ok, 1),
            ("record after comment", "# c\n\n" + GOOD_LINE + ok, 3),
            ("empty file", "", 1),
            ("comments only", "# a\n\n", 3),
            ("duplicate colour", GOOD_HEAD + "white | 1 | 1 | 1 | 100 | 3\n[lines]\n", 5),
            ("missing background", "[colours]\nwhite | 0xFFFF | 0x7FFF | 0xFFFFFF | 16 | 3\n[lines]\n", 3),
            ("missing background at end", "[colours]\nwhite | 0xFFFF | 0x7FFF | 0xFFFFFF | 16 | 3\n", 3),
            ("overlapping ramps", GOOD_HEAD.replace("| 32 | 3", "| 18 | 3") + "[lines]\n", 4),
            ("touching ramps", GOOD_HEAD.replace("| 32 | 3", "| 19 | 3") + "[lines]\n", 4),
            ("background inside a ramp", GOOD_HEAD.replace("| 0 | 0", "| 17 | 0") + "[lines]\n", 3),
            ("background after a ramp", "[colours]\nwhite | 0xFFFF | 0x7FFF | 0xFFFFFF | 16 | 3\n"
             "background | 1 | 1 | 1 | 17 | 0\n", 3),
            ("background equal to a base", GOOD_HEAD.replace("| 0 | 0", "| 16 | 0") + "[lines]\n", 3),
            ("rgb888 0x1000000", GOOD_HEAD.replace("0xFFFFFF", "0x1000000") + "[lines]\n", 3),
            ("rgb565 0x10000", GOOD_HEAD.replace("0xFFFF |", "0x10000 |", 1) + "[lines]\n", 3),
            ("index_base 255 levels 1", GOOD_HEAD + "top | 1 | 1 | 1 | 255 | 1\n[lines]\n", 5),
            ("levels 0 on a colour", GOOD_HEAD + "top | 1 | 1 | 1 | 100 | 0\n[lines]\n", 5),
            ("levels 256", GOOD_HEAD + "top | 1 | 1 | 1 | 1 | 256\n[lines]\n", 5),
            ("index_base 256", GOOD_HEAD + "top | 1 | 1 | 1 | 256 | 1\n[lines]\n", 5),
            ("name with a space", "[colours]\nback ground | 1 | 1 | 1 | 0 | 0\n", 2),
            ("5 colour fields", "[colours]\nbackground | 1 | 1 | 1 | 0\n", 2),
            ("7 colour fields", "[colours]\nbackground | 1 | 1 | 1 | 0 | 0 | 0\n", 2),
            ("background levels", "[colours]\nbackground | 1 | 1 | 1 | 0 | 2\n", 2),
        ]
        for name, data, expect in cases:
            with self.subTest(name):
                self.agree(data, expect)
        # accepted corners
        self.agree(line("A.SVF | 16/16 | -32768 | 32767 | white | a|".replace("a|", "a")))
        self.agree(line("A.SVF | 0x10/0x1 | 0x10 | -0 | yellow | a"))
        self.agree("# lead\n\n" + ok)
        self.agree(ok.replace("0xFFFFFF", "0xffffff"))
        self.agree(GOOD_HEAD + "top | 1 | 1 | 1 | 254 | 1\n[lines]\n")

    def test_substitute(self):
        import vesa_lines
        self.assertEqual(vesa_lines.substitute("{W}x{H} {BPP}", 640, 480, 16), "640x480 16")
        self.assertEqual(vesa_lines.substitute("no braces", 640, 480, 16), "no braces")
        self.assertEqual(vesa_lines.substitute("{X} {W} {w} {", 1024, 768, 8), "{X} 1024 {w} {")

    def test_expected_buffer_fill(self):
        import vesa_lines
        with tempfile.TemporaryDirectory(prefix="svf-vl-") as tmp:
            path = write_tmp(tmp, GOOD_HEAD)
            t = vesa_lines.parse(path)
            self.assertEqual(t.lines, [])
            faces_dir = os.path.join(SVF_DIR, "dos")
            for bpp, px in ((16, b"\x10\x00"), (15, b"\x10\x00"), (8, b"\x00"), (32, b"\x84\x00\x00\x00"),
                            (24, b"\x84\x00\x00")):
                buf = vesa_lines.expected_buffer(t, faces_dir, 64, 16, bpp)
                self.assertEqual(buf, px * (64 * 16), bpp)
            self.assertEqual(vesa_lines.fnv1a(b""), 2166136261)
            self.assertEqual(vesa_lines.fnv1a(b"a"), 0xE40C292C)

    def test_expected_buffer_draws(self):
        """A line is drawn with its chain, scale, x, baseline and colour: the white text is in the 16 bpp buffer and
        the faces are looked up only inside the faces directory."""
        import vesa_lines
        table = vesa_lines.parse(VESA_LINES)
        faces_dir = os.path.join(SVF_DIR, "dos")
        buf = vesa_lines.expected_buffer(table, faces_dir, 640, 480, 16)
        self.assertEqual(len(buf), 640 * 480 * 2)
        self.assertNotEqual(buf, b"\x10\x00" * (640 * 480))
        self.assertIn(b"\xff\xff", buf)
        buf8 = vesa_lines.expected_buffer(table, faces_dir, 640, 480, 8)
        self.assertEqual(set(buf8) - set(range(256)), set())
        self.assertTrue(set(buf8) & {17, 18, 19})
        self.assertTrue(set(buf8) & {33, 34, 35})
        self.assertTrue(max(buf8) <= 127)
        with tempfile.TemporaryDirectory(prefix="svf-vl-") as tmp:
            outside = os.path.join(tmp, "outside")
            os.mkdir(outside)
            shutil.copy(os.path.join(faces_dir, "PAPLG16.SVF"), os.path.join(outside, "PAPLG16.SVF"))
            fd = os.path.join(tmp, "faces")
            os.mkdir(fd)
            os.symlink(os.path.join(outside, "PAPLG16.SVF"), os.path.join(fd, "PAPLG16.SVF"))
            path = write_tmp(tmp, GOOD_HEAD + "[lines]\nPAPLG16.SVF | 1/1 | 16 | 40 | white | abc\n")
            with self.assertRaises(vesa_lines.VesaLinesError):
                vesa_lines.expected_buffer(vesa_lines.parse(path), fd, 64, 64, 16)

    def test_substitute_c(self):
        """vl_substitute (C) against the Python substitute, and its cut to out_len."""
        import vesa_lines

        def c_sub(w, h, bpp, text, outlen=None):
            args = [dump_exe(), "--substitute", str(w), str(h), str(bpp), text] + ([str(outlen)] if outlen else [])
            r = subprocess.run(args, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            res, need = r.stdout.split(b"\nneed=")
            return res, int(need)
        for text in ("{W}x{H} {BPP}", "no braces", "{X} {W} {w} {", "{", "{W", "{BPP}{BPP}{", "가{H}나", ""):
            for w, h, bpp in ((640, 480, 16), (1024, 768, 8), (4096, 4096, 32)):
                want = vesa_lines.substitute(text, w, h, bpp).encode("utf-8")
                self.assertEqual(c_sub(w, h, bpp, text), (want, len(want)), (text, w, h, bpp))
        big = "{W}" * 170    # 510 bytes, expands to 680
        want = vesa_lines.substitute(big, 1024, 768, 16).encode("utf-8")
        self.assertEqual(len(want), 680)
        self.assertEqual(c_sub(1024, 768, 16, big, 1024), (want, 680))
        self.assertEqual(c_sub(1024, 768, 16, big, 512), (want[:511], 680))     # cut, NUL-terminated, need reported
        self.assertEqual(c_sub(1024, 768, 16, big, 1), (b"", 680))

    def test_face_name_device_names(self):
        for name in ("CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9"):
            self.agree(GOOD_HEAD + "[lines]\n%s.SVF | 1/1 | 16 | 40 | white | a\n" % name, 6)
        for name in ("COM0", "COM10", "LPT0", "CONS", "XCON", "COM", "NULL"):
            self.agree(GOOD_HEAD + "[lines]\n%s.SVF | 1/1 | 16 | 40 | white | a\n" % name)

    def test_rgb555_range(self):
        """rgb555 is 0..0x7FFF (bit 15 is never set from the file): 0x8000 is refused by both readers."""
        for v, expect in (("0x7FFF", None), ("0x8000", 3), ("0xFFFF", 3), ("0", None)):
            self.agree(GOOD_HEAD.replace("0xFFFF | 0x7FFF | 0xFFFFFF", "0xFFFF | %s | 0xFFFFFF" % v) + "[lines]\n", expect)
        py, _ = both_read(GOOD_HEAD.replace("| 0x7FFF |", "| 0x8000 |") + "[lines]\n")
        self.assertEqual(py, (3, "rgb555 out of range"))

    def test_file_too_large(self):
        """The C reader counts bytes as it parses (a pipe will do), the Python reader the same bytes: the 65537th byte
        is refused at line 1 as soon as a line reads it; a refusal on an earlier line wins; the byte the C reader
        peeks at after a 512-byte stretch counts."""
        head = GOOD_HEAD + "[lines]\n"

        def padded(total, tail=""):
            body, room = head, total - len(head) - len(tail)
            while room > 0:
                n = min(room, 400)
                body += "#" * (n - 1) + "\n" if n > 1 else "\n"
                room -= n
            return body + tail

        def piped(data):
            import vesa_lines
            r = subprocess.run([dump_exe(), "--print-table", "/dev/stdin"], input=data.encode("utf-8"),
                               capture_output=True)
            if r.returncode == 0:
                return None
            n, msg = r.stderr.decode().rstrip("\n")[len("vesa-lines: line "):].split(": ", 1)
            return int(n), msg

        long513 = "#" + "x" * 511 + "y"    # 513 bytes before its newline: "line too long" unless the size comes first
        cases = []
        for total in (65536, 65537):
            cases.append((padded(total), None if total == 65536 else (1, "file too large")))
        cases.append((padded(65537, "bad line\n"), (1, "file too large")))
        cases.append((head + "bad record\n" + padded(65600)[len(head):], (6, "a line record has 6 fields")))
        # a 513-byte stretch starting at `start`: C reads 512 bytes and peeks at the 513th, so it reads start + 513 bytes
        for start in (65536 - 512, 65536 - 513, 65536 - 520):
            cases.append((padded(start) + long513 + "\n", (1, "file too large") if start + 513 > 65536 else False))
        for data, want in cases:
            py, c = both_read(data)
            self.assertEqual(py, c, len(data))
            self.assertEqual(piped(data), py, len(data))
            if want is not False:
                self.assertEqual(py, want, len(data))
            elif py is not None:
                self.assertEqual(py[1], "line too long", len(data))

    def test_read_error(self):
        """A file that cannot be read (a directory): both readers refuse at line 1, 'read error'."""
        import vesa_lines
        with tempfile.TemporaryDirectory(prefix="svf-vl-") as tmp:
            with self.assertRaises(vesa_lines.VesaLinesError) as cm:
                vesa_lines.parse(tmp)
            self.assertEqual((cm.exception.line_no, cm.exception.message), (1, "read error"))
            r = subprocess.run([dump_exe(), "--print-table", tmp], capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stderr), (1, "vesa-lines: line 1: read error\n"))

    def test_expected_buffer_colours(self):
        """Full-coverage pixels pin the colour of every kind: white and yellow ink in the pixel grid, the X byte 0."""
        import vesa_lines
        table = vesa_lines.parse(VESA_LINES)
        faces_dir = os.path.join(SVF_DIR, "dos")
        want = {15: (b"\xff\x7f", b"\xe0\x7f", b"\x10\x00"), 16: (b"\xff\xff", b"\xe0\xff", b"\x10\x00"),
                24: (b"\xff\xff\xff", b"\x00\xff\xff", b"\x84\x00\x00"),
                32: (b"\xff\xff\xff\x00", b"\x00\xff\xff\x00", b"\x84\x00\x00\x00")}
        for bpp, (white, yellow, bg) in want.items():
            n = len(bg)
            buf = vesa_lines.expected_buffer(table, faces_dir, 640, 480, bpp)
            px = {buf[i:i + n] for i in range(0, len(buf), n)}
            self.assertIn(white, px, bpp)
            self.assertIn(yellow, px, bpp)
            self.assertIn(bg, px, bpp)
            if bpp == 32:
                self.assertEqual({buf[i] for i in range(3, len(buf), 4)}, {0})
            if bpp == 15:
                self.assertTrue(all(buf[i] < 0x80 for i in range(1, len(buf), 2)))

    def test_face_errors_carry_the_line(self):
        import vesa_lines
        with tempfile.TemporaryDirectory(prefix="svf-vl-") as tmp:
            fd = os.path.join(tmp, "faces")
            os.mkdir(fd)
            path = write_tmp(tmp, GOOD_HEAD + "[lines]\n" + GOOD_LINE + "NOSUCH.SVF | 1/1 | 16 | 40 | white | abc\n")
            shutil.copy(os.path.join(SVF_DIR, "dos", "PAPLG16.SVF"), fd)
            with self.assertRaises(vesa_lines.VesaLinesError) as cm:
                vesa_lines.expected_buffer(vesa_lines.parse(path), fd, 64, 64, 16)
            self.assertEqual(cm.exception.line_no, 7)
            r = subprocess.run([sys.executable, os.path.join(HERE, "vesa_lines.py"), "--expect", path, "--faces", fd,
                                "64", "64", "16"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn("line 7", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_open_face_small_files(self):
        """The cache sizing svfvesa uses (vl_cache_slots) opens a streamed face of any length, 1024 bytes or less too."""
        for cps, bpp, w in (([0x41], 2, 5), ([0x41], 1, 3), ([0x41, 0x42], 2, 5), (list(range(0x41, 0x41 + 40)), 8, 7)):
            data = synth_face(bpp, w, 6, cps)
            with tempfile.TemporaryDirectory(prefix="svf-vl-") as tmp:
                path = os.path.join(tmp, "F.SVF")
                with open(path, "wb") as fh:
                    fh.write(data)
                r = subprocess.run([dump_exe(), "--open-face", path], capture_output=True, text=True)
                self.assertEqual((r.returncode, r.stdout), (0, "ok\n"), (len(data), r.stderr))
        self.assertLessEqual(len(synth_face(2, 5, 6, [0x41])), 1024)
        for n, want in ((1, 2), (1024, 2), (1025, 2), (2048, 2), (2049, 3), (64 * 1024, 64), (10 ** 6, 64)):
            r = subprocess.run([dump_exe(), "--cache-slots", str(n)], capture_output=True, text=True)
            self.assertEqual(r.stdout, "%d\n" % want, n)


    def test_expect_cli(self):
        r = subprocess.run([sys.executable, os.path.join(HERE, "vesa_lines.py"), "--expect", VESA_LINES, "--faces",
                            os.path.join(SVF_DIR, "dos"), "640", "480", "16"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"^sum=[0-9a-f]{8}\n$")
        r = subprocess.run([sys.executable, os.path.join(HERE, "vesa_lines.py"), "--print-table", VESA_LINES,
                            "--dac", "6"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("palette[17]=2B 15 15\n", r.stdout)


# The 888 kinds' sweep colours: a non-zero X byte and distinct channels, so a channel swap or a lost X byte shows.
SWEEP_FG888, SWEEP_BG888 = 0x5A123456, 0x00ABCDEF


# ---- vesa_check.py and vesa-shots.sh (c/ports/dos): the capture check, on synthetic dumps ----

VESA_CHECK = os.path.join(C_DIR, "ports", "dos", "vesa_check.py")
VESA_SHOTS = os.path.join(C_DIR, "ports", "dos", "vesa-shots.sh")


class TestVesaCheck(unittest.TestCase):
    """The capture check on synthetic 64 x 8 dumps: the exact rule, derived rules, and the faults it must refuse.
    Exit codes: 0 ok, 1 a check failed, 2 unusable input (no traceback ever)."""

    W, H = 64, 8
    BG565, FG565 = 0x0010, 0xF8DF  # blue background, magenta ink: r 0/31, g 0/6, b 16/31 all differ

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-vc-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    @staticmethod
    def ink(x, y):
        return x % 4 < 2 and y % 2 == 0

    def dump_words(self, bg, fg):
        out = bytearray()
        for y in range(self.H):
            for x in range(self.W):
                out += (fg if self.ink(x, y) else bg).to_bytes(2, "little")
        return bytes(out)

    def dump16(self):
        return self.dump_words(self.BG565, self.FG565)

    def png(self, name, pixel, w=None, h=None, shift=0):
        """A PNG whose pixel (x, y) is pixel(x, y), shifted right by `shift` columns."""
        from PIL import Image
        w, h = w or self.W, h or self.H
        im = Image.new("RGB", (w, h))
        px = im.load()
        for y in range(h):
            for x in range(w):
                px[x, y] = pixel((x - shift) % w, y)
        path = os.path.join(self.tmp, name)
        im.save(path)
        return path

    def write(self, name, data):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def run_check(self, png, dump, bpp=16, dac="8", *extra):
        argv = [sys.executable, VESA_CHECK, png, dump, str(self.W), str(self.H), str(bpp)]
        if dac is not None:
            argv += ["--dac", dac]
        r = subprocess.run(argv + ["--palette-from", VESA_LINES] + list(extra), capture_output=True, text=True)
        self.assertNotIn("Traceback", r.stderr)
        return r.returncode, r.stdout + r.stderr

    check = run_check

    EXACT = staticmethod(lambda v, bits: v * 0x21 >> 2 if bits == 5 else v * 0x41 >> 4)
    SHL = staticmethod(lambda v, bits: v << (8 - bits))

    def channels(self, v, bpp):
        if bpp == 16:
            return (v >> 11, v >> 5 & 63, v & 31), (5, 6, 5)
        return (v >> 10 & 31, v >> 5 & 31, v & 31), (5, 5, 5)

    def pixel_words(self, rule, bg, fg, bpp, delta=(0, 0, 0), swap=False):
        def expand(v):
            ch, bits = self.channels(v, bpp)
            return tuple(min(255, (rule[i] if isinstance(rule, tuple) else rule)(ch[i], bits[i]) + delta[i])
                         for i in range(3))
        cb, cf = expand(bg), expand(fg)

        def f(x, y):
            c = cf if self.ink(x, y) else cb
            return c[::-1] if swap else c
        return f

    def pixel16(self, rule, swap=False, delta=(0, 0, 0)):
        return self.pixel_words(rule, self.BG565, self.FG565, 16, delta, swap)

    # 15 bpp: the 5/5/5 split, distinct values in every channel
    BG555, FG555 = (1 << 10 | 16 << 5 | 20), (31 << 10 | 8 << 5 | 2)

    def dump15(self):
        return self.dump_words(self.BG555, self.FG555)

    def pixel15(self, rule, swap=False, delta=(0, 0, 0)):
        return self.pixel_words(rule, self.BG555, self.FG555, 15, delta, swap)

    def test_exact_16bpp(self):
        dump = self.write("d.raw", self.dump16())
        rc, out = self.check(self.png("a.png", self.pixel16(self.EXACT)), dump)
        self.assertEqual(rc, 0, out)
        self.assertIn("rule=exact", out)

    def test_swapped_channels_fail(self):
        dump = self.write("d.raw", self.dump16())
        rc, out = self.check(self.png("a.png", self.pixel16(self.EXACT, swap=True)), dump)
        self.assertEqual(rc, 1, out)

    def test_derived_rule(self):
        dump = self.write("d.raw", self.dump16())
        rc, out = self.check(self.png("a.png", self.pixel16(self.SHL)), dump)
        self.assertEqual(rc, 0, out)
        self.assertIn("rule=shl", out)
        self.assertNotIn("shl3", out)  # the name says what it computes: v << (8 - bits), not always << 3
        self.assertNotIn("tolerance", out)

    def test_scale255_rule(self):
        dump = self.write("d.raw", self.dump16())
        rc, out = self.check(self.png("a.png", self.pixel16(lambda v, bits: v * 255 // ((1 << bits) - 1))), dump)
        self.assertEqual(rc, 0, out)
        self.assertIn("rule=scale255", out)

    def test_mixed_rules_fail(self):
        """One expansion rule for all channels: R on shl with G and B exact is a broken channel, not a rule."""
        dump = self.write("d.raw", self.dump16())
        mixed = (self.SHL, self.EXACT, self.EXACT)
        rc, out = self.check(self.png("a.png", self.pixel16(mixed)), dump)
        self.assertEqual(rc, 1, out)
        self.assertIn("one rule", out)

    def test_single_channel_off_fails(self):
        """r + 3 or g ^ 4 on one channel only: tolerance is a decision over all channels, so it fails (exit 1);
        the tolerance path needs every channel off every rule (test_tolerance_boundaries)."""
        dump = self.write("d.raw", self.dump16())
        rc, out = self.check(self.png("a.png", self.pixel16(self.EXACT, delta=(3, 0, 0))), dump)
        self.assertEqual(rc, 1, out)
        rc, out = self.check(self.png("b.png", self.pixel16(self.EXACT, delta=(0, 4, 0))), dump)
        self.assertEqual(rc, 1, out)

    def test_tolerance_when_every_channel_is_off(self):
        dump = self.write("d.raw", self.dump16())
        f = self.pixel16(self.EXACT)
        rc, out = self.check(self.png("a.png", lambda x, y: tuple(max(0, v - 3) for v in f(x, y))), dump)
        self.assertEqual(rc, 0, out)
        self.assertIn("tolerance=yes", out)
        rc, out = self.check(self.png("b.png", lambda x, y: tuple(max(0, v - 20) for v in f(x, y))), dump)
        self.assertEqual(rc, 1, out)

    def test_tolerance_when_one_channel_fits_every_rule(self):
        """15 bpp, R is 0 everywhere (every rule fits it), G and B are off by 3: a tolerance case, not a failure."""
        bg, fg = 16 << 5 | 20, 8 << 5 | 2
        dump = self.write("d.raw", self.dump_words(bg, fg))
        rc, out = self.check(self.png("a.png", self.pixel_words(self.EXACT, bg, fg, 15, delta=(0, 3, 3))), dump, 15)
        self.assertEqual(rc, 0, out)
        self.assertIn("tolerance=yes", out)

    def test_tolerance_boundaries(self):
        """5-bit channels allow +-8, 6-bit channels +-4: 15 bpp (all 5-bit) takes +8 and not +9; 16 bpp takes R/B +8
        and G +4, and not G +5 (a 6-bit channel at the 5-bit limit)."""
        d15 = self.write("d15.raw", self.dump15())
        rc, out = self.check(self.png("a.png", self.pixel15(self.EXACT, delta=(8, 8, 8))), d15, 15)
        self.assertEqual(rc, 0, out)
        self.assertIn("tolerance=yes", out)
        rc, out = self.check(self.png("b.png", self.pixel15(self.EXACT, delta=(9, 8, 8))), d15, 15)
        self.assertEqual(rc, 1, out)
        d16 = self.write("d16.raw", self.dump16())
        rc, out = self.check(self.png("c.png", self.pixel16(self.EXACT, delta=(8, 4, 8))), d16)
        self.assertEqual(rc, 0, out)
        rc, out = self.check(self.png("d.png", self.pixel16(self.EXACT, delta=(8, 5, 8))), d16)
        self.assertEqual(rc, 1, out)

    def test_15bpp_split(self):
        dump = self.write("d.raw", self.dump15())
        rc, out = self.check(self.png("a.png", self.pixel15(self.EXACT)), dump, 15)
        self.assertEqual(rc, 0, out)
        self.assertIn("rule=exact", out)
        rc, out = self.check(self.png("b.png", self.pixel15(self.EXACT, swap=True)), dump, 15)
        self.assertEqual(rc, 1, out)
        # the same words read as 5/6/5 would not match: the PNG built that way fails at 15 bpp
        wrong = self.pixel_words(self.EXACT, self.BG555, self.FG555, 16)
        rc, out = self.check(self.png("c.png", wrong), dump, 15)
        self.assertEqual(rc, 1, out)

    def test_24bpp_is_bgr(self):
        bg, fg = (10, 20, 130), (200, 100, 50)  # R, G, B
        raw = b"".join(bytes(((fg if self.ink(x, y) else bg)[::-1])) for y in range(self.H) for x in range(self.W))
        dump = self.write("d24.raw", raw)
        f = lambda x, y: fg if self.ink(x, y) else bg
        rc, out = self.check(self.png("a.png", f), dump, 24)
        self.assertEqual(rc, 0, out)
        rc, out = self.check(self.png("b.png", lambda x, y: f(x, y)[::-1]), dump, 24)
        self.assertEqual(rc, 1, out)

    def test_wrong_pitch_fail(self):
        dump = self.write("d.raw", self.dump16())
        rc, out = self.check(self.png("a.png", self.pixel16(self.EXACT), shift=1), dump)
        self.assertEqual(rc, 1, out)

    def test_wrong_size_fail(self):
        dump = self.write("d.raw", self.dump16())
        rc, out = self.check(self.png("a.png", self.pixel16(self.EXACT), w=65), dump)
        self.assertEqual(rc, 1, out)
        self.assertIn("PNG is 65x8", out)

    def test_blank_png_with_good_dump_fails(self):
        """The 1 % rule counts the PNG's own non-background pixels (a good dump does not rescue a blank capture)."""
        dump = self.write("d.raw", self.dump16())
        bg = self.pixel16(self.EXACT)(2, 1)  # a background pixel
        rc, out = self.check(self.png("blank.png", lambda x, y: bg), dump)
        self.assertEqual(rc, 1, out)
        self.assertIn("1 %", out)

    def pal8(self):
        import vesa_lines
        return vesa_lines.palette(vesa_lines.parse(VESA_LINES), 8)

    def dump8(self):
        return self.write("d8.raw", bytes(35 if self.ink(x, y) else 0 for y in range(self.H) for x in range(self.W)))

    def test_palette_swap_fail(self):
        pal = self.pal8()
        idx = lambda x, y: 35 if self.ink(x, y) else 0  # the yellow ramp's top, and the background
        good = lambda x, y: (pal[idx(x, y)][2], pal[idx(x, y)][1], pal[idx(x, y)][0])
        rc, out = self.check(self.png("a.png", good), self.dump8(), 8)
        self.assertEqual(rc, 0, out)
        self.assertIn("rule=exact", out)
        rc, out = self.check(self.png("b.png", lambda x, y: good(x, y)[::-1]), self.dump8(), 8)
        self.assertEqual(rc, 1, out)

    def test_8bpp_off_by_one_fails(self):
        """An 8-bit DAC channel has no tolerance: one level off is a failure."""
        pal = self.pal8()
        idx = lambda x, y: 35 if self.ink(x, y) else 0
        off = lambda x, y: (pal[idx(x, y)][2], pal[idx(x, y)][1], pal[idx(x, y)][0] - 1 if idx(x, y) else 1)
        rc, out = self.check(self.png("a.png", off), self.dump8(), 8)
        self.assertEqual(rc, 1, out)
        rc, out = self.check(self.png("b.png", lambda x, y: tuple(max(0, v - 1) for v in off(x, y))), self.dump8(), 8)
        self.assertEqual(rc, 1, out)

    def test_8bpp_6bit_dac(self):
        pal = [(b >> 2, g >> 2, r >> 2, 0) for (b, g, r, _) in self.pal8()]
        up = lambda v: v * 0x41 >> 4
        idx = lambda x, y: 35 if self.ink(x, y) else 0
        px = lambda x, y: tuple(up(pal[idx(x, y)][i]) for i in (2, 1, 0))
        rc, out = self.check(self.png("a.png", px), self.dump8(), 8, "6")
        self.assertEqual(rc, 0, out)
        self.assertIn("rule=exact", out)

    def test_unusable_input_exits_2(self):
        """No traceback, exit 2 and a message: a bad --dac, a missing or truncated dump, a PNG that is not one."""
        dump = self.write("d.raw", self.dump16())
        png = self.png("a.png", self.pixel16(self.EXACT))
        for dac in ("7", "x", "0"):
            rc, out = self.check(png, dump, 16, dac)
            self.assertEqual(rc, 2, (dac, out))
        rc, out = self.check(png, dump, 8, None)
        self.assertEqual(rc, 2, out)
        rc, out = self.check(png, os.path.join(self.tmp, "missing.raw"))
        self.assertEqual(rc, 2, out)
        rc, out = self.check(png, self.write("short.raw", self.dump16()[:-2]))
        self.assertEqual(rc, 2, out)
        rc, out = self.check(self.write("junk.png", b"not a png"), dump)
        self.assertEqual(rc, 2, out)
        rc, out = self.check(os.path.join(self.tmp, "none.png"), dump)
        self.assertEqual(rc, 2, out)
        self.assertTrue(out.strip(), "a message is printed")

    def test_dump_compared_byte_for_byte(self):
        """With --faces the dump must equal expected_buffer: one wrong pixel is named by x, y and kind."""
        import vesa_lines
        table = vesa_lines.parse(VESA_LINES)
        faces = os.path.join(os.path.dirname(C_DIR), "svf", "dos")
        w, h = 640, 480
        exp = bytearray(vesa_lines.expected_buffer(table, faces, w, h, 32))
        rgb = lambda px: (px[2], px[1], px[0])
        rows = [[rgb(exp[(y * w + x) * 4:(y * w + x) * 4 + 4]) for x in range(w)] for y in range(h)]
        png = self.png("a.png", lambda x, y: rows[y][x], w, h)
        argv = lambda dump: [sys.executable, VESA_CHECK, png, dump, str(w), str(h), "32", "--dac", "8",
                             "--palette-from", VESA_LINES, "--faces", faces, "--diff", os.path.join(self.tmp, "d.png")]
        r = subprocess.run(argv(self.write("ok.raw", bytes(exp))), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        exp[(10 * w + 20) * 4] ^= 0x40  # the PNG now disagrees with the dump too, but the dump check comes first
        r = subprocess.run(argv(self.write("bad.raw", bytes(exp))), capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("x=20 y=10 kind=xrgb8888", r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "d.png")))

    def shots(self, out, **env):
        e = dict(os.environ, VESA_SHOTS_CHECK_ONLY="1", **env)
        return subprocess.run(["bash", VESA_SHOTS, out], capture_output=True, text=True, env=e)

    def test_out_dir_refused(self):
        base = os.path.join(self.tmp, "o")
        os.makedirs(base)
        # OUT holding a stray file
        stray = os.path.join(base, "stray")
        os.makedirs(stray)
        with open(os.path.join(stray, "keep.txt"), "w") as fh:
            fh.write("x")
        r = self.shots(stray)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(os.listdir(stray), ["keep.txt"])
        # OUT with a symlinked capture/
        sym = os.path.join(base, "sym")
        os.makedirs(sym)
        open(os.path.join(sym, ".vesa-shots"), "w").close()
        target = os.path.join(base, "target")
        os.makedirs(target)
        with open(os.path.join(target, "p.png"), "w") as fh:
            fh.write("x")
        os.symlink(target, os.path.join(sym, "capture"))
        r = self.shots(sym)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(os.listdir(target), ["p.png"])
        # a symlinked prefix, a relative OUT, a space, a dot component
        link = os.path.join(base, "link")
        os.symlink(target, link)
        for bad in (os.path.join(link, "x"), "relative/out", os.path.join(base, "a b"), os.path.join(base, ".", "x"),
                    os.path.join(base, "..", "x")):
            r = self.shots(bad)
            self.assertEqual(r.returncode, 1, (bad, r.stderr))
            self.assertIn("vesa-shots:", r.stderr)
        # accepted: absent, empty, marker
        self.assertEqual(self.shots(os.path.join(base, "new")).returncode, 0)
        empty = os.path.join(base, "empty")
        os.makedirs(empty)
        self.assertEqual(self.shots(empty).returncode, 0)
        marked = os.path.join(base, "marked")
        os.makedirs(os.path.join(marked, "capture"))
        open(os.path.join(marked, ".vesa-shots"), "w").close()
        open(os.path.join(marked, "SUM.TXT"), "w").close()
        self.assertEqual(self.shots(marked).returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(marked, "SUM.TXT")))
        self.assertEqual(os.listdir(empty), [])

    def test_out_symlinked_names_refused(self):
        """Every name the script writes or deletes: a symlink anywhere under OUT refuses the run, nothing followed."""
        victim = os.path.join(self.tmp, "victim")
        os.makedirs(victim)
        with open(os.path.join(victim, "keep"), "w") as fh:
            fh.write("x")
        for name in ("obj", ".vesa-shots-x", "mapper.txt", "dosbox.conf", "VESALINE.TXT", "PAPLG16.SVF", "flush.md",
                     "OUT.clean", "rule.txt", "shot-640x480-8bpp.png", "SVFVESA.EXE", "dosbox.log"):
            out = os.path.join(self.tmp, "o-" + name.replace(".", "_"))
            os.makedirs(out)
            open(os.path.join(out, ".vesa-shots"), "w").close()
            os.symlink(victim if name == "obj" else os.path.join(victim, "keep"), os.path.join(out, name))
            r = self.shots(out)
            self.assertEqual(r.returncode, 1, (name, r.stderr))
            self.assertIn("symlink", r.stderr)
        # the marker itself, and a link below obj/
        out = os.path.join(self.tmp, "o-marker")
        os.makedirs(out)
        os.symlink(os.path.join(victim, "keep"), os.path.join(out, ".vesa-shots"))
        self.assertEqual(self.shots(out).returncode, 1)
        out = os.path.join(self.tmp, "o-deep")
        os.makedirs(os.path.join(out, "obj", "vbe"))
        open(os.path.join(out, ".vesa-shots"), "w").close()
        os.symlink(victim, os.path.join(out, "obj", "vbe", "x.o"))
        self.assertEqual(self.shots(out).returncode, 1)
        self.assertEqual(os.listdir(victim), ["keep"])
        with open(os.path.join(victim, "keep")) as fh:
            self.assertEqual(fh.read(), "x")

# the fake emulator's work for test_failed_store...: SUM.TXT, DUMP.RAW, OUT.TXT and gen.png for the mode in argv
GEN_CAPTURE = r'''
import sys
sys.path.insert(0, %r)
sys.path.insert(0, %r)
import os, vesa_lines, vesa_check
from PIL import Image
w, h, bpp = (int(v) for v in sys.argv[1:4])
t = vesa_lines.parse(%r)
faces = os.path.join(%r, "svf", "dos")
buf = bytes(vesa_lines.expected_buffer(t, faces, w, h, bpp))
pal = vesa_lines.palette(t, 8) if bpp == 8 else None
vals, bits = vesa_check.pixel_values(buf, w, h, bpp, pal)
bits = bits or (8, 8, 8)
ex = vesa_check.FAMILIES["exact"]
im = Image.new("RGB", (w, h))
im.putdata([tuple(ex[bits[i]](v[i]) for i in range(3)) for v in vals])
im.save("gen.png")
open("DUMP.RAW", "wb").write(buf)
open("SUM.TXT", "w").write("sum=%%08x dac=8 mode=0x101 %%dx%%d %%dbpp pitch=%%d bits=%%d\r\n" %% (
    vesa_lines.fnv1a(buf), w, h, bpp, w * vesa_lines.BYTES_PP[bpp], bpp))
open("OUT.TXT", "w").write("flush_%%dx%%d_%%d rows=%%d us=100\r\n" %% (w, h, bpp, h))
'''


def run_in_session(argv, env, timeout):
    """subprocess.run in a session of its own: whatever the command leaves behind (an emulator, Xvfb) is killed on a
    timeout or when it returns. Raises subprocess.TimeoutExpired after the kill."""
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
                            start_new_session=True)
    try:
        so, se = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_session(proc.pid)
        proc.communicate()
        raise
    finally:
        kill_session(proc.pid)
    return subprocess.CompletedProcess(argv, proc.returncode, so, se)


def proc_session(stat):
    """The session id (field 6) of the text of a /proc/<pid>/stat, or None when the text is short or malformed. The
    command name (field 2) may hold spaces and parentheses: the fields start after the last ')'."""
    i = stat.rfind(")")
    fields = stat[i + 1:].split() if i >= 0 else []
    try:
        return int(fields[3])
    except (IndexError, ValueError):
        return None


def kill_session(sid):
    """SIGKILL every process whose session is @p sid (the group alone misses `timeout`, which makes its own)."""
    for _ in range(20):
        found = False
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            try:
                with open("/proc/%s/stat" % d) as fh:
                    stat = fh.read()
                if proc_session(stat) == sid:
                    os.kill(int(d), signal.SIGKILL)
                    found = True
            except OSError:
                pass
        if not found:
            return
        time.sleep(0.05)


class TestProcSession(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(proc_session("123 (sleep) S 1 123 77 0 -1"), 77)
        self.assertEqual(proc_session("123 (a b) (c) S 1 123 88 0 -1"), 88)  # spaces and parentheses in the name
        for bad in ("", "123", "123 (x", "123 (x) S", "123 (x) S 1 2", "123 (x) S 1 2 abc 4", ") "):
            self.assertIsNone(proc_session(bad), bad)


class TestVesaShotsRun(unittest.TestCase):
    """vesa-shots.sh against a fake emulator and a fake xdotool (VESA_SHOTS_NO_BUILD skips the DJGPP build): the
    failure paths of the run, each ending with exit 1, no `OK` line, nothing running."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-vr-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out = os.path.join(self.tmp, "out")
        os.makedirs(self.out)
        open(os.path.join(self.out, ".vesa-shots"), "w").close()
        with open(os.path.join(self.out, "SVFVESA.EXE"), "w") as fh:
            fh.write("fake")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        self.script(os.path.join(self.bin, "dosbox-x"), r'''#!/bin/bash
echo $$ > fake.pid
[ -z "${FAKE_IGNORE_TERM:-}" ] || trap '' TERM
[ -z "${FAKE_SUMLINE:-}" ] || printf '%s\r\n' "$FAKE_SUMLINE" > SUM.TXT
[ -z "${FAKE_DUMP:-}" ] || cp "$FAKE_DUMP" DUMP.RAW
[ -z "${FAKE_OUTTXT:-}" ] || printf '%b' "$FAKE_OUTTXT" > OUT.TXT
MODE=$(sed -n 's/^SVFVESA.EXE \([0-9]*\) \([0-9]*\) \([0-9]*\) .*/\1 \2 \3/p' dosbox.conf)
[ -z "${FAKE_GEN:-}" ] || python3 "$FAKE_GEN" $MODE
exec sleep 300
''')
        self.script(os.path.join(self.bin, "xdotool"), r'''#!/bin/bash
case $1 in
search) echo 4242 ;;
getwindowgeometry) printf '%s' "${FAKE_GEOM:-}" ;;
key) case "$*" in
	*ctrl+F5*) if [ -n "${FAKE_PNG:-}" ]; then mkdir -p capture; cp "$FAKE_PNG" capture/svfvesa_000.png;
		elif [ -f gen.png ]; then mkdir -p capture; cp gen.png capture/svfvesa_000.png; fi ;;
	*space*) kill "$(cat fake.pid)" 2>/dev/null ;;
	esac ;;
esac
exit 0
''')
        self.dest = os.path.join(self.tmp, "shots")

    def script(self, path, text):
        with open(path, "w") as fh:
            fh.write(text)
        os.chmod(path, 0o755)

    def good_sum(self, w=640, h=480, bpp=8):
        import vesa_lines
        t = vesa_lines.parse(VESA_LINES)
        faces = os.path.join(os.path.dirname(C_DIR), "svf", "dos")
        return "%08x" % vesa_lines.fnv1a(vesa_lines.expected_buffer(t, faces, w, h, bpp))

    def sumline(self, s=None, dac="dac=8 ", mode="mode=0x101 640x480 8bpp"):
        return "sum=%s %s%s pitch=640 bits=8" % (s or self.good_sum(), dac, mode)

    def run_script(self, timeout=150, **env):
        e = dict(os.environ, PATH=self.bin + ":" + os.environ["PATH"], DOSBOX_X=os.path.join(self.bin, "dosbox-x"),
                 VESA_SHOTS_NO_BUILD="1", VESA_SHOTS_DEST=self.dest, **env)
        t0 = time.time()
        # its own session (run_in_session): every process of it is killed on a timeout, not just bash
        r = run_in_session(["bash", VESA_SHOTS, self.out], e, timeout)
        self.elapsed = time.time() - t0
        self.assertNotIn("vesa-shots: OK", r.stdout + r.stderr)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        pid = os.path.join(self.out, "fake.pid")
        if os.path.exists(pid):
            with open(pid) as fh:
                p = int(fh.read())
            time.sleep(0.2)
            self.assertFalse(os.path.exists("/proc/%d" % p) and "sleep" in open("/proc/%d/cmdline" % p).read(),
                             "the emulator was left running")
        return r.stdout + r.stderr

    def good_capture(self):
        """A dump and a PNG that pass the capture check for 640 x 480 8 bpp."""
        import vesa_lines
        from PIL import Image
        t = vesa_lines.parse(VESA_LINES)
        faces = os.path.join(os.path.dirname(C_DIR), "svf", "dos")
        buf = vesa_lines.expected_buffer(t, faces, 640, 480, 8)
        pal = vesa_lines.palette(t, 8)
        im = Image.new("RGB", (640, 480))
        im.putdata([(pal[i][2], pal[i][1], pal[i][0]) for i in buf])
        png = os.path.join(self.tmp, "good.png")
        im.save(png)
        raw = os.path.join(self.tmp, "good.raw")
        with open(raw, "wb") as fh:
            fh.write(buf)
        return png, raw

    def test_term_ignoring_emulator_is_killed(self):
        out = self.run_script(FAKE_IGNORE_TERM="1", FAKE_SUMLINE=self.sumline("00000000"))
        self.assertIn("sum mismatch", out)
        self.assertLess(self.elapsed, 30)

    def test_no_report_and_overall_timeout(self):
        out = self.run_script(FAKE_IGNORE_TERM="1", VESA_SHOTS_WAIT="2")
        self.assertIn("SVFVESA did not report (640 480 8)", out)
        self.assertLess(self.elapsed, 30)
        out = self.run_script(FAKE_IGNORE_TERM="1", VESA_SHOTS_RUN_TIMEOUT="3")
        self.assertLess(self.elapsed, 30)

    def test_sum_line_must_be_exact(self):
        out = self.run_script(FAKE_SUMLINE=self.sumline(dac=""), VESA_SHOTS_WAIT="5")
        self.assertIn("SUM.TXT", out)
        self.assertNotIn("Traceback", out)
        # the mode text must come after mode=0x<n>, not anywhere in the line
        out = self.run_script(FAKE_SUMLINE="sum=%s dac=8 640x480 8bpp mode=0x101 x pitch=640 bits=8" % self.good_sum(),
                              VESA_SHOTS_WAIT="5")
        self.assertIn("SUM.TXT", out)

    def test_ffmpeg_fallback_without_geometry_dies_cleanly(self):
        out = self.run_script(FAKE_SUMLINE=self.sumline(), VESA_SHOTS_PNG_TRIES="3")
        self.assertIn("window geometry", out)
        self.assertNotIn("unbound", out)

    def test_flush_line_must_match_exactly(self):
        png, raw = self.good_capture()
        out = self.run_script(FAKE_SUMLINE=self.sumline(), FAKE_PNG=png, FAKE_DUMP=raw,
                              FAKE_OUTTXT="flush_640x480_8 rows=480 us=4140 extra=1\r\n")
        self.assertIn("capture ok", out)
        self.assertIn("source=scrshot", out)
        self.assertIn("flush", out)
        self.assertFalse(os.path.exists(os.path.join(self.dest, "640x480-8bpp.png")), "no shot is stored on failure")

    def test_unwritable_shots_dir_fails_before_the_run(self):
        os.makedirs(self.dest)
        os.chmod(self.dest, 0o500)
        self.addCleanup(os.chmod, self.dest, 0o700)
        if os.access(self.dest, os.W_OK):
            self.skipTest("running as a user that can write anywhere")
        out = self.run_script()
        self.assertIn("shots", out)
        self.assertFalse(os.path.exists(os.path.join(self.out, "fake.pid")), "the emulator was not started")

    def test_run_script_timeout_kills_the_group(self):
        """A timed-out run_script leaves no emulator behind and returns at once (the old subprocess.run waited for the
        grandchildren's pipes)."""
        t0 = time.time()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_script(timeout=3, FAKE_IGNORE_TERM="1", FAKE_SUMLINE="", VESA_SHOTS_WAIT="100",
                            VESA_SHOTS_RUN_TIMEOUT="100")
        self.assertLess(time.time() - t0, 20)
        with open(os.path.join(self.out, "fake.pid")) as fh:
            p = int(fh.read())
        time.sleep(0.3)
        self.assertFalse(os.path.exists("/proc/%d" % p), "the emulator was left running")

    def test_env_numbers_are_validated(self):
        """VESA_SHOTS_WAIT, _PNG_TRIES and _RUN_TIMEOUT are [0-9]+: anything else (a command substitution in bash
        arithmetic would run) refuses the run before anything is done."""
        mark = os.path.join(self.tmp, "PWNED")
        for var in ("VESA_SHOTS_WAIT", "VESA_SHOTS_PNG_TRIES", "VESA_SHOTS_RUN_TIMEOUT"):
            for bad in ("abc", "-1", "1.5", "a[$(touch %s)]" % mark, "$(touch %s)" % mark, "1 2", ""):
                with self.subTest(var=var, bad=bad):
                    e = dict(os.environ, DOSBOX_X=os.path.join(self.bin, "dosbox-x"), **{var: bad})
                    r = run_in_session(["bash", VESA_SHOTS, "--inner", "640", "480", "8", self.out], e, 20)
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertIn(var, r.stderr)
                    self.assertFalse(os.path.exists(mark))
                    r = run_in_session(["bash", VESA_SHOTS, self.out], dict(e, VESA_SHOTS_CHECK_ONLY="1"), 20)
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertFalse(os.path.exists(mark))
        self.assertFalse(os.path.exists(os.path.join(self.out, "fake.pid")))
        # leading zeros are decimal, not octal
        e = dict(os.environ, VESA_SHOTS_CHECK_ONLY="1", VESA_SHOTS_WAIT="08", VESA_SHOTS_PNG_TRIES="09")
        r = subprocess.run(["bash", VESA_SHOTS, self.out], capture_output=True, text=True, env=e, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_check_only_says_what_it_skipped(self):
        e = dict(os.environ, VESA_SHOTS_CHECK_ONLY="1")
        r = subprocess.run(["bash", VESA_SHOTS, self.out], capture_output=True, text=True, env=e, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("VESA_SHOTS_CHECK_ONLY", r.stderr)
        self.assertIn("skipped", r.stderr)

    def inner(self, *mode, out=None, **env):
        e = dict(os.environ, DOSBOX_X=os.path.join(self.bin, "dosbox-x"), VESA_SHOTS_WAIT="1", **env)
        return run_in_session(["bash", VESA_SHOTS, "--inner", *mode] + ([out or self.out] if len(mode) == 3 else []),
                              e, 60)

    def test_inner_checks_out_and_mode(self):
        """--inner holds OUT to the outer half's rules and W H BPP to numbers and a known depth, before the emulator."""
        stray = os.path.join(self.tmp, "stray")
        os.makedirs(stray)
        with open(os.path.join(stray, "keep.txt"), "w") as fh:
            fh.write("x")
        r = self.inner("640", "480", "8", out=stray)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("marker", r.stderr)
        self.assertEqual(os.listdir(stray), ["keep.txt"])
        r = self.inner("640", "480", "8", out="relative/out")
        self.assertEqual(r.returncode, 1, r.stderr)
        os.symlink(self.tmp, os.path.join(self.out, "capture"))
        r = self.inner("640", "480", "8")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("symlink", r.stderr)
        os.unlink(os.path.join(self.out, "capture"))
        for w, h, bpp in (("abc", "480", "8"), ("640", "$(true)", "8"), ("640", "480", "7"), ("640", "480", ""),
                          ("0", "480", "8"), ("640", "480", "8 ")):
            with self.subTest(mode=(w, h, bpp)):
                r = self.inner(w, h, bpp)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn("vesa-shots:", r.stderr)
        r = self.inner("640", "480")  # too few arguments
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.out, "fake.pid")), "the emulator was started")

    def test_failed_store_removes_its_temporary_files(self):
        """All ten modes pass (the fake emulator draws each mode's expected buffer), the store then fails on the last
        copy: no .<name>.new file is left in the shots directory."""
        gen = os.path.join(self.bin, "gen.py")
        with open(gen, "w") as fh:
            fh.write(GEN_CAPTURE % (HERE, os.path.dirname(VESA_SHOTS), VESA_LINES, ROOT))
        os.makedirs(self.dest)
        blocker = os.path.join(self.dest, ".640x480-8bpp.png.new")
        os.makedirs(blocker)
        os.chmod(blocker, 0o500)
        self.addCleanup(os.chmod, blocker, 0o700)
        if os.access(blocker, os.W_OK):
            self.skipTest("running as a user that can write anywhere")
        out = self.run_script(timeout=400, FAKE_GEN=gen)
        self.assertIn("cannot store", out)
        left = [n for n in os.listdir(self.dest) if n.endswith(".new") and os.path.isfile(os.path.join(self.dest, n))]
        self.assertEqual(left, [])
        self.assertEqual([n for n in os.listdir(self.dest) if n.endswith(".png")], [], "nothing is stored")


BENCH_DIR = os.path.join(C_DIR, "bench")


class TestBenchScripts(unittest.TestCase):
    """c/bench/run-host.sh keeps the bench's exit status; run-dos.sh checks OUT before it deletes anything."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-bs-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_host_bench_failure_is_not_swallowed(self):
        """A bench that stops with a code (-DSVF_TARGETS=0x01: INDEXED8 refused, bench_end(7 * 16 + e)) fails the
        script; the pipeline into tee used to turn it into 0."""
        r = run_in_session(["sh", os.path.join(BENCH_DIR, "run-host.sh"), os.path.join(self.tmp, "o"),
                            "-DSVF_TARGETS=0x01"], dict(os.environ), 300)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_in_session(["sh", os.path.join(BENCH_DIR, "run-host.sh"), os.path.join(self.tmp, "o2")],
                           dict(os.environ), 300)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("end=0", r.stdout)

    def test_mkface_profile_aligned(self):
        """mkface.py --profile mcu-strict declares aligned(4), dos none, and the array bytes are relayout's; without
        --profile the file's bytes as they are."""
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import jamoset
        src = os.path.join(SVF_DIR, "dos", "PAPLG16.SVF")
        with open(src, "rb") as fh:
            raw = fh.read()

        def run(*extra):
            out = os.path.join(self.tmp, "f.c")
            subprocess.run([sys.executable, "-I", os.path.join(BENCH_DIR, "mkface.py"), src, out] + list(extra),
                           check=True)
            with open(out) as fh:
                text = fh.read()
            body = text[text.index("= {") + 3:text.index("};")]
            return text, bytes(int(v) for v in body.replace("\n", "").replace("\t", "").split(",") if v.strip())

        text, data = run("--profile", "mcu-strict")
        self.assertIn("__attribute__((aligned(4)))", text)
        self.assertEqual(data, jamoset.relayout(raw, "mcu-strict"))
        self.assertIn(f"_len = {len(data)}u;", text)
        text, data = run("--profile", "dos")
        self.assertNotIn("aligned", text)
        self.assertEqual(data, jamoset.relayout(raw, "dos"))
        text, data = run("--profile", "simd16")
        self.assertIn("aligned(16)", text)
        text, data = run()
        self.assertEqual(data, raw)
        self.assertIn("aligned(4)", text)  # the default profile's units are 4 bytes: the file is aligned as its record unit
        text, data = run("--profile", "mcu-strict", "--box", "full")
        self.assertEqual(data, jamoset.relayout(raw, "mcu-strict", "full"))

    # The layout bytes (header bytes 9 and 10) of each writer profile: REC | ROW << 3, TAB.
    LAYOUT_BYTES = {"mcu-strict": (2, 2), "dos": (0, 0), "wasm": (0, 0)}

    @staticmethod
    def face_array(path):
        """The bytes and the declaration of a mkface.py output."""
        with open(path) as fh:
            text = fh.read()
        body = text[text.index("= {") + 3:text.index("};")]
        return text, bytes(int(v) for v in body.replace("\n", "").replace("\t", "").split(",") if v.strip())

    def mkface_lines(self, path):
        """The mkface.py command lines of the script or CMake file @p path, continuation lines joined."""
        with open(path) as fh:
            text = fh.read().replace("\\\n", " ")
        return [ln.strip() for ln in text.splitlines()
                if "python3" in ln and "mkface.py" in ln and not ln.lstrip().startswith("#")]

    def run_script_mkface(self, path, env_extra=None):
        """Runs each mkface.py line of the runner @p path as the script would (HERE, C, OUT, FACE..., SVF, d, f and n
        set as the script sets them before the line; BENCH_PROFILE and BENCH_BOX unset unless @p env_extra sets them).
        Returns {output file: (declaration, bytes)}."""
        out = tempfile.mkdtemp(dir=self.tmp)
        os.makedirs(os.path.join(out, "gen"), exist_ok=True)
        os.makedirs(os.path.join(out, "faces"), exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k not in ("BENCH_PROFILE", "BENCH_BOX")}
        env.update(HERE=BENCH_DIR, C=C_DIR, OUT=out, d=out, SVF=SVF_DIR, f="dos/PAPLG16.SVF", n="paplg16",
                   FACE=os.path.join(SVF_DIR, "dos", "NEODG16G.SVF"),
                   FACE16=os.path.join(SVF_DIR, "dos", "PAPLG16.SVF"), FACE18=os.path.join(SVF_DIR, "dos", "PAPLG18.SVF"))
        env.update(env_extra or {})
        lines = self.mkface_lines(path)
        self.assertTrue(lines, path)
        for ln in lines:
            ln = ln.replace("|| exit 1", "").replace("|| return 1", "")
            r = subprocess.run(["sh", "-c", "set -u; " + ln], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{path}: {ln}: {r.stderr}")
        got = {}
        for c in glob.glob(os.path.join(out, "*.c")) + glob.glob(os.path.join(out, "*", "*.c")):
            got[c] = self.face_array(c)
        # every line's output path, expanded with the same environment, is a generated file and every generated file is
        # some line's output (ports that wrote the same file would be counted once and checked once)
        targets = set()
        for ln in lines:
            tok = re.search(r'mkface\.py"?\s+\S+\s+(\S+)', ln).group(1)
            r = subprocess.run(["sh", "-c", "set -u; printf %s " + tok], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{path}: {tok}: {r.stderr}")
            targets.add(os.path.realpath(r.stdout))
        self.assertEqual(len(targets), len(lines), f"{path}: two mkface lines write one file")
        self.assertEqual({os.path.realpath(c) for c in got}, targets, path)
        return got

    def assert_profile(self, faces, profile, where):
        for c, (text, data) in faces.items():
            self.assertEqual(data[:4], b"SVFN", (where, c))
            self.assertEqual(data[4], 3, (where, c))
            self.assertEqual((data[9], data[10]), self.LAYOUT_BYTES[profile], (where, c, profile))
            if profile == "mcu-strict":
                self.assertIn("__attribute__((aligned(4)))", text, (where, c))

    def test_mcu_runners_embed_mcu_strict(self):
        """Each MCU runner (Pico, ESP32, M33, RP2350, AVR) and the port faces of build-all.sh (the nine MCU images and
        the Arduino port) embed their faces in the mcu-strict layout: the generated arrays' layout bytes 9 and 10 are
        2 and 2 (4-byte records and tables) and the arrays are aligned(4). BENCH_PROFILE still overrides it for one run
        (dos: 0 and 0). run-wasm embeds the wasm profile."""
        scripts = [os.path.join(BENCH_DIR, f"run-{r}.sh") for r in ("pico", "esp32", "m33", "rp2350", "avr")]
        scripts.append(os.path.join(C_DIR, "cross", "build-all.sh"))
        for path in scripts:
            self.assert_profile(self.run_script_mkface(path), "mcu-strict", path)
        self.assert_profile(self.run_script_mkface(scripts[0], {"BENCH_PROFILE": "dos"}), "dos", "BENCH_PROFILE=dos")
        self.assert_profile(self.run_script_mkface(os.path.join(BENCH_DIR, "run-wasm.sh"),
                                                   {"SVF": os.path.join(SVF_DIR, "dos")}), "wasm", "run-wasm.sh")

    def test_cmake_ports_embed_mcu_strict(self):
        """The Pico and ESP32 CMake builds generate their faces with mkface.py in the mcu-strict layout (the COMMAND
        line run as CMake would run it, layout bytes 2 and 2, aligned(4)); the Arduino README's line does too, and
        the Arduino flags in the README and in build-all.sh read that one layout, without the stream reader."""
        import shlex
        for rel in ("ports/pico/CMakeLists.txt", "ports/esp32/main/CMakeLists.txt"):
            lines = self.mkface_lines(os.path.join(C_DIR, rel))
            self.assertEqual(len(lines), 1, rel)
            out = tempfile.mkdtemp(dir=self.tmp)
            cmd = lines[0].split("COMMAND", 1)[1]
            for var, val in (("${SVF_C}", C_DIR), ("${_svf_path}", os.path.join(SVF_DIR, "dos", "PAPLG16.SVF")),
                             ("${SVF_FACE_GEN}", out), ("${_svf_name}", "paplg16")):
                cmd = cmd.replace(var, val)
            self.assertNotIn("${", cmd, rel)
            subprocess.run(shlex.split(cmd), check=True)
            self.assert_profile({c: self.face_array(c) for c in glob.glob(os.path.join(out, "*.c"))}, "mcu-strict", rel)
        readme = os.path.join(C_DIR, "ports", "arduino", "README.md")
        lines = self.mkface_lines(readme)
        self.assertEqual(len(lines), 1, readme)
        out = os.path.join(self.tmp, "arduino-face.c")
        argv = shlex.split(lines[0])
        argv = [sys.executable if a == "python3" else os.path.join(ROOT, a) if a.startswith(("c/", "svf/")) else a
                for a in argv]
        argv[argv.index(os.path.join(ROOT, "c/ports/arduino/face.c"))] = out
        subprocess.run(argv, check=True)
        self.assert_profile({out: self.face_array(out)}, "mcu-strict", readme)
        with open(readme) as fh:
            flags = [ln for ln in fh.read().splitlines() if ln.strip().startswith("F=")]
        with open(os.path.join(C_DIR, "cross", "build-all.sh")) as fh:
            ball = fh.read()
        arduino = ball[ball.index("\tarduino)\n\t\tpython3"):]  # the port build, not the install check before it
        arduino = arduino[:arduino.index(";;")]
        for text, where in ((flags[0] if flags else "", "README F="), (arduino, "build-all.sh arduino")):
            self.assertIn("-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT", text, where)
            self.assertIn("-DSVF_NO_STREAM", text, where)

    def dos(self, out):
        home = os.path.join(self.tmp, "home")  # a HOME of its own: the unfixed script deletes below OUT
        os.makedirs(home, exist_ok=True)
        return run_in_session(["sh", os.path.join(BENCH_DIR, "run-dos.sh"), out],
                              dict(os.environ, HOME=home, DOSBOX_X="/nonexistent/dosbox-x",
                                   OPT=os.path.join(self.tmp, "noopt")), 60)

    def test_dos_out_refused_before_any_delete(self):
        stray = os.path.join(self.tmp, "stray")
        os.makedirs(os.path.join(stray, "run"))
        with open(os.path.join(stray, "run", "keep"), "w") as fh:
            fh.write("x")
        with open(os.path.join(stray, "mine.txt"), "w") as fh:
            fh.write("x")
        link = os.path.join(self.tmp, "link")
        os.symlink(stray, link)
        for bad in (os.path.join(self.tmp, "home"), "relative/out", stray, os.path.join(link, "x"),
                    os.path.join(self.tmp, ".", "x"), os.path.join(self.tmp, "a b")):
            with self.subTest(out=bad):
                r = self.dos(bad)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("run-dos: OUT", r.stderr)
        self.assertTrue(os.path.exists(os.path.join(stray, "run", "keep")))
        self.assertTrue(os.path.exists(os.path.join(stray, "mine.txt")))
        # a foreign directory that holds only run/precious has no .run-dos marker: refused, nothing deleted
        foreign = os.path.join(self.tmp, "foreign")
        os.makedirs(os.path.join(foreign, "run"))
        with open(os.path.join(foreign, "run", "precious"), "w") as fh:
            fh.write("x")
        r = self.dos(foreign)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("run-dos: OUT", r.stderr)
        self.assertEqual(os.listdir(foreign), ["run"])
        self.assertTrue(os.path.exists(os.path.join(foreign, "run", "precious")))
        # a fresh OUT gets the marker (the run then stops at the missing compiler)
        fresh = os.path.join(self.tmp, "fresh")
        r = self.dos(fresh)
        self.assertNotIn("run-dos: OUT", r.stderr)
        self.assertTrue(os.path.exists(os.path.join(fresh, ".run-dos")))
        # a marked directory is cleaned: its old run/ goes
        os.makedirs(os.path.join(fresh, "run"), exist_ok=True)
        open(os.path.join(fresh, "run", "old"), "w").close()
        r = self.dos(fresh)
        self.assertNotIn("run-dos: OUT", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(fresh, "run", "old")))


class TargetMixin:
    """svfdump-asan line on a target against svfline: draw_target, and to_target of the line's GRAY8 buffer."""

    EXE = "svfdump-asan"    # the executable draw runs; a subclass sets "svfdump-bytes" (the byte loops, no word stores)

    @staticmethod
    def opts_of(kind, stride=None, fill=TARGET_FILL, clip=None, fg=0xFFFF, bg=0, threshold=128, big_endian=False,
                index_base=None, index_levels=None, fg888=SWEEP_FG888, bg888=SWEEP_BG888, misalign=0, extra=(),
                gray_bits=None, lsb_first=False):
        opts = ["--target=" + kind, "--fill=%d" % fill, "--fg=%d" % fg, "--bg=%d" % bg, "--threshold=%d" % threshold]
        if kind == "indexed8":
            if index_base is not None:      # None: leave the option out, the library's defaults (0, 255) apply
                opts.append("--index-base=%d" % index_base)
            if index_levels is not None:
                opts.append("--index-levels=%d" % index_levels)
        if kind in ("xrgb8888", "rgb888"):
            opts += ["--fg888=%d" % fg888, "--bg888=%d" % bg888]
        if kind == "gray":
            if gray_bits is not None:       # None: leave the option out, the library's default (8) applies
                opts.append("--gray-bits=%d" % gray_bits)
            if lsb_first:
                opts.append("--lsb-first")
        if misalign:
            opts.append("--misalign=%d" % misalign)
        if stride is not None:
            opts.append("--stride=%d" % stride)
        if clip is not None:
            opts.append("--clip=%d:%d:%d:%d" % clip)
        if big_endian:
            opts.append("--big-endian")
        return opts + list(extra)

    def draw(self, chain, text, x, y, w, h, kind, extra=(), scale=None, **t):
        """(exit code, buffer bytes or plot list, stderr) of svfdump-asan line on the target (scale: (num, den))."""
        if scale is not None:
            extra = ["--scale=%d/%d" % scale] + list(extra)
        rc, out, err = line_run("line", chain, text, w, h, x, y, opts=self.opts_of(kind, extra=extra, **t),
                                 exe_name=self.EXE)
        self.assertNotIn("Sanitizer", err)
        self.assertNotIn("runtime error", err)
        self.assertNotIn("guard bytes changed", err)
        if kind == "cb":
            out = [tuple(int(v) for v in ln.split()) for ln in out.decode().splitlines()]
        return rc, out, err

    @staticmethod
    def target(kind, w, h, stride=None, fill=TARGET_FILL, clip=None, fg=0xFFFF, bg=0, threshold=128,
               big_endian=False, index_base=None, index_levels=None, fg888=SWEEP_FG888, bg888=SWEEP_BG888, misalign=0,
               gray_bits=None, lsb_first=False):
        index_base = 0 if index_base is None else index_base       # the library's defaults
        index_levels = 255 if index_levels is None else index_levels
        gray_bits = 8 if gray_bits is None else gray_bits
        stride = svfline.target_row_bytes(kind, w, gray_bits) if stride is None else stride
        buf = bytearray([fill]) * (svfline.target_rows(kind, h) * stride)
        return svfline.Target(kind, w, h, stride, buf, fg, bg, threshold, big_endian, index_base, index_levels, fg888,
                              bg888, gray_bits=gray_bits, lsb_first=lsb_first)

    def expect(self, chain, text, x, y, w, h, kind, scale=None, **t):
        """(draw_target result, to_target result) of the reference: buffers, or plot lists for cb."""
        clip = t.get("clip")
        places = svfline.placements(svfline.load_chain(chain), text, x, y, scale=scale or (1, 1))
        a = svfline.draw_target(places, self.target(kind, w, h, **t), clip)
        b = svfline.to_target(svfline.draw_gray8(places, w, h, clip), self.target(kind, w, h, **t))
        return (a.plots, b.plots) if kind == "cb" else (bytes(a.buf), bytes(b.buf))

    def check(self, chain, text, x, y, w, h, kind, scale=None, **t):
        rc, out, err = self.draw(chain, text, x, y, w, h, kind, scale=scale, **t)
        self.assertEqual(rc, 0, err)
        cells, line = self.expect(chain, text, x, y, w, h, kind, scale=scale, **t)
        self.assertEqual(out, cells)
        if kind == "cb":
            # One call a cell pixel: the same pixels and (the most of a pixel's calls) coverage as the GRAY8 line.
            most = {}
            for px, py, cov in out:
                most[px, py] = max(most.get((px, py), 0), cov)
            self.assertEqual(sorted((px, py, c) for (px, py), c in most.items()), sorted(line))
        else:
            self.assertEqual(out, line, "differs from to_target of the GRAY8 line")
        return out


class TestTargets(TargetMixin, unittest.TestCase):
    """svf_draw_utf8 on MONO_PAGE, MONO_ROW, RGB565 and COVERAGE_CB (and GRAY8 at other strides) against
    svfline.draw_target, and against svfline.to_target of the line's GRAY8 buffer; clipping; refused targets."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.tmp = tempfile.mkdtemp(prefix="svf-target-")
        cls.marks = os.path.join(cls.tmp, "marks.svf")
        r = subprocess.run([sys.executable, SYNTH, "--marks", cls.marks], capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError("svf_synth --marks: " + r.stderr)
        cls.chains = ([PAPLG16, PAPLG18], [MARUS24], [jamo16()], [cls.marks, PAPLG18])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_targets_match_reference(self):
        n = 0
        for w, h in TARGET_SIZES:
            odd = w == 100
            for kind, kt in kind_runs(SWEEP_KINDS):
                t = dict(stride=row_bytes(kind, w, kt) + 3 if odd and kind != "cb" else None,
                         fg=0x8410 if odd else 0xFFFF, bg=0x1F if odd else 0xF800, threshold=200 if odd else 128,
                         big_endian=odd, fg888=0x8C7F20E0 if odd else 0xFFFFFF, bg888=0x00108030 if odd else 0,
                         **kt)
                for chain in self.chains:
                    for text in LINE_TEXTS:
                        for x, y in target_places(w, h):
                            with self.subTest(size=(w, h), kind=kind, kt=kt,
                                              chain="+".join(map(os.path.basename, chain)), text=text, x=x, y=y):
                                out = self.check(chain, text, x, y, w, h, kind, **t)
                                drawable = any(svfline.Face.load(f).has(ord(ch)) for f in chain for ch in text.strip())
                                if drawable and (x, y) == (2, 28):
                                    self.assertTrue(out != bytes(self.target(kind, w, h, **t).buf) and out != [],
                                                    "nothing drawn")
                                n += 1
        print(f"\n  test_targets_match_reference: {n} lines match svfline", file=sys.stderr)

    def test_threshold_and_byte_order(self):
        """A 2 bpp face: threshold 128 sets level 2 and 3 pixels, 200 level 3 only, 0 every inked one; the two RGB565
        byte orders are each other's swap."""
        chain, text = [PAPLG16, PAPLG18], LINE_TEXTS[0]
        bits = {}
        for thr in (0, 1, 128, 200, 255):
            out = self.check(chain, text, 2, 28, 128, 64, "mono-row", threshold=thr, fill=0)
            bits[thr] = sum(bin(b).count("1") for b in out)
        self.assertEqual(bits[0], bits[1])
        self.assertGreater(bits[1], bits[128])
        self.assertGreater(bits[128], bits[200])
        self.assertEqual(bits[200], bits[255])
        for kind in sorted(svfline.RGB16_KINDS):
            le = self.check(chain, text, 2, 28, 128, 64, kind, fg=0x1234, bg=0xABCD)
            be = self.check(chain, text, 2, 28, 128, 64, kind, fg=0x1234, bg=0xABCD, big_endian=True)
            self.assertEqual(le, bytes(b for i in range(0, len(be), 2) for b in (be[i + 1], be[i])), kind)
            self.assertIn((0x1234).to_bytes(2, "little"), le, kind)

    def test_mono_page_hand_computed(self):
        """SSD1306 page bytes worked out by hand (not from svfline): the marks face's 'A' (ink rows 3..12 of its cell,
        rows in svf_synth.MARKS_GLYPHS) drawn at x 0 on baseline 13 (ascent 13: cell row r is target row r) on a 16 x 16
        page target: byte page * 16 + column, bit row & 7."""
        rc, out, err = self.draw([self.marks], "A", 0, 13, 16, 16, "mono-page", fill=0)
        self.assertEqual(rc, 0, err)
        want = bytearray(32)
        # Page 0 (rows 0..7): column 1 and 6 rows 6, 7; columns 2 and 5 rows 4, 5, 7; columns 3 and 4 rows 3, 7.
        want[1] = want[6] = 0xC0
        want[2] = want[5] = 0x10 | 0x20 | 0x80
        want[3] = want[4] = 0x08 | 0x80
        # Page 1 (rows 8..15): columns 1 and 6 rows 8..12.
        want[16 + 1] = want[16 + 6] = 0x1F
        self.assertEqual(out, bytes(want))

    def test_clip_edges(self):
        """Lines cut by every edge (x = -7 on baseline 3: ink above row 0; x = w - 5: past the right), the clip
        inset by 3: pixels outside the clip stay the fill, the guard bytes around the buffer stay 0xA5 (ASan)."""
        for w, h in TARGET_SIZES:
            clip = (3, 3, w - 3, h - 3)
            for kind, kt in kind_runs(SWEEP_KINDS):
                fill = kt.get("fill", TARGET_FILL)
                for chain in ([PAPLG16, PAPLG18], [MARUS24]):
                    for x, y in ((-7, 3), (w - 5, 28), (-7, h + 2)):
                        for text in (LINE_TEXTS[0], "(jpg, Qy)_"):
                            with self.subTest(size=(w, h), kind=kind, kt=kt, chain=os.path.basename(chain[0]), x=x,
                                              y=y):
                                out = self.check(chain, text, x, y, w, h, kind, clip=clip, **kt)
                                if kind == "cb":
                                    self.assertTrue(all(3 <= px < w - 3 and 3 <= py < h - 3 for px, py, _ in out))
                                elif kind in ("gray8", "indexed8"):
                                    self.assertTrue(all(out[py * w + px] == fill for py in range(h)
                                                        for px in range(w)
                                                        if not (3 <= px < w - 3 and 3 <= py < h - 3)))
                # The clip does cut: the same line unclipped draws more.
                text, (x, y) = LINE_TEXTS[0], (-7, 3)
                if kind == "gray8":
                    self.assertNotEqual(self.check([PAPLG16, PAPLG18], text, x, y, w, h, kind, clip=clip),
                                        self.check([PAPLG16, PAPLG18], text, x, y, w, h, kind))

    def test_clip_sweep(self):
        """Every offset of a line across each clip edge, one pixel at a time (an off-by-one at an edge shows)."""
        w, h, chain, text = 100, 37, [MARUS24], "#WM#"     # MARUS24 'W' has ink in its cell's last column
        for clip in ((3, 3, w - 3, h - 3), (1, 1, w - 1, h - 1)):
            for kind, kt in kind_runs(BUFFER_KINDS):
                for x, y in [(x, 20) for x in range(-50, 4)] + [(x, 20) for x in range(w - 56, w - 2)] + \
                            [(10, y) for y in range(-2, 24)] + [(10, y) for y in range(h - 8, h + 20)]:
                    with self.subTest(clip=clip, kind=kind, kt=kt, x=x, y=y):
                        self.check(chain, text, x, y, w, h, kind, clip=clip, **kt)

    def refused(self, kind, w, h, **t):
        rc, out, err = self.draw([MARUS24], "Score", 2, 20, w, h, kind, **t)
        self.assertEqual(rc, 2, err)
        self.assertIn("SVF_E_ARG", err)
        if kind == "cb":
            self.assertEqual(out, [])
        else:
            self.assertEqual(set(out), {TARGET_FILL} if out else set(), "a refused target was written")

    def test_bad_targets(self):
        w, h = 100, 37
        for kind in SWEEP_KINDS:
            with self.subTest(kind=kind, case="w or h <= 0"):
                for bw, bh in ((0, h), (w, 0), (-1, h), (w, -5)):
                    self.refused(kind, bw, bh)
            with self.subTest(kind=kind, case="clip outside the target or empty"):
                for clip in ((w, 0, w + 50, h), (-50, 0, 0, h), (0, h, w, h + 9), (60, 0, 40, h), (0, 20, w, 20)):
                    rc, out, err = self.draw([MARUS24], "Score", 2, 20, w, h, kind, clip=clip)
                    self.assertEqual(rc, 0, err)
                    self.assertEqual(out, [] if kind == "cb" else bytes(self.target(kind, w, h).buf))
            if kind == "cb":
                with self.subTest(kind=kind, case="no plot"):
                    self.refused(kind, w, h, extra=["--no-plot"])
                continue
            row = svfline.target_row_bytes(kind, w)
            with self.subTest(kind=kind, case="stride below the row bytes"):
                self.refused(kind, w, h, stride=row - 1)
                self.refused(kind, w, h, stride=0)
            with self.subTest(kind=kind, case="buf_len one byte short"):
                self.refused(kind, w, h, extra=["--buf-delta=-1"])
                self.refused(kind, w, h, stride=row + 5, extra=["--buf-delta=-1"])
                self.check([MARUS24], "Score", 2, 20, w, h, kind, stride=row + 5)
        # 320 x 240 RGB565 (153,600 bytes, stride 640): 16-bit address math would wrap; drawn at the far corner.
        for x, y in ((300, 238), (2, 120), (-3, 250)):
            with self.subTest(case="320x240 rgb565", x=x, y=y):
                out = self.check([PAPLG16, PAPLG18], LINE_TEXTS[0], x, y, 320, 240, "rgb565", fg=0x07E0, bg=0)
                if (x, y) == (300, 238):
                    # Ink in rows 220..239 (bytes 140,800 on, past 16 bits).
                    self.assertNotEqual(out[220 * 640:], bytes([TARGET_FILL]) * (20 * 640), "nothing drawn at the end")


DOS = os.path.join(SVF_DIR, "dos")
NGOTB17 = os.path.join(DOS, "NGOTB17.SVF")      # 18 x 18, 1 bpp (pitch 3: 6 padding bits)
NEODG16D = os.path.join(DOS, "NEODG16D.SVF")    # 22 x 22, 1 bpp
NGOTB14 = os.path.join(DOS, "NGOTB14.SVF")      # 14 x 14, 2 bpp
GBA17BX1 = os.path.join(DOS, "GBA17BX1.SVF")    # 26 x 24, 2 bpp; its cmap is U+2026, U+2122, U+D25D only
NEODG32A = os.path.join(DOS, "NEODG32A.SVF")    # 46 x 54, 1 bpp: wider and taller than a 32 x 20 target
ODD_FACES = (NGOTB17, NEODG16D, NGOTB14, GBA17BX1)          # 18, 22 (1 bpp), 14, 26 (2 bpp) pixel cells
PHASE_X = tuple(range(-9, 16))                              # every x & 7 twice, negative included
PHASE_Y = tuple(range(0, 16))                               # every page phase of a cell top (y_baseline - ascent + dy)
THRESHOLDS = (0, 1, 85, 86, 128, 170, 171, 255)
BLIT_TEXT = "W#가각 Qy"
# GBA17BX1 has none of BLIT_TEXT: its three glyphs follow (missing code points advance 0, so they start at x).
BLIT_TEXT_EXTRA = {GBA17BX1: "…퉝™"}


def set_bits(buf):
    return sum(bin(b).count("1") for b in buf)


OVERLAP_W, OVERLAP_H, OVERLAP_ASCENT, OVERLAP_ADVANCE = 12, 16, 13, 5


def overlap_level(cp, x, y, bpp):
    """'H': high coverage everywhere (8 bpp 192..255, 2 bpp level 3); 'L': low and never 0 (8 bpp 1..100, 2 bpp level
    1), below threshold 128 everywhere."""
    if bpp == 2:
        return 3 if cp == 0x48 else 1
    return 192 + (x * 7 + y * 3) % 64 if cp == 0x48 else 1 + (x * 5 + y * 3) % 100


def overlap_face(bpp):
    """A 12 x 16 face of @p bpp (2 or 8) with 'H' and 'L' whose advance (5) is less than the cell: in "HL" the later
    'L' cell lays low coverage over columns 5..11 of the earlier 'H' cell (and in "LH" high over low)."""
    pitch = (OVERLAP_W * bpp + 7) // 8
    glyphs = []
    for cp in (0x48, 0x4C):
        cell = bytearray(pitch * OVERLAP_H)
        for y in range(OVERLAP_H):
            for x in range(OVERLAP_W):
                v = overlap_level(cp, x, y, bpp)
                if bpp == 8:
                    cell[y * pitch + x] = v
                else:
                    cell[y * pitch + x // 4] |= v << (6 - 2 * (x % 4))
        glyphs.append((cp, bytes(cell), OVERLAP_ADVANCE, 0, OVERLAP_W))
    data = bytearray(jamoset.write_svfn(OVERLAP_W, OVERLAP_H, OVERLAP_ASCENT, glyphs, b"", bpp=bpp))
    struct.pack_into("<H", data, 6, jamoset.FLAG_VARIABLE)      # no JSET block
    return bytes(data)


THR8_VALUES = (16, 85, 86, 127, 128, 100, 255, 84, 129, 40)    # the 8 bpp values: >= vs > at thresholds 85/86/128


def synth_face(bpp, width, height, cps, padded=False, level3=False):
    """A face of @p bpp whose cells are @p width x @p height (width not a multiple of 8) with glyphs @p cps: 8 bpp
    pixels cycle THR8_VALUES (16..255, none 0), 2 bpp levels cycle 1..3, 1 bpp every pixel inked and, with @p padded,
    the padding bits past the width set too (2 bpp: the padding pixels at level 3); with @p level3 every 2 bpp pixel is
    level 3."""
    pitch = (width * bpp + 7) // 8
    glyphs = []
    for n, cp in enumerate(sorted(cps)):
        cell = bytearray(pitch * height)
        for y in range(height):
            for x in range(width):
                i = x + 3 * y + n
                if bpp == 8:
                    cell[y * pitch + x] = THR8_VALUES[i % len(THR8_VALUES)]
                elif bpp == 2:
                    cell[y * pitch + x // 4] |= (3 if level3 else 1 + i % 3) << (6 - 2 * (x % 4))
                else:
                    cell[y * pitch + x // 8] |= 0x80 >> (x % 8)
            if bpp == 1 and padded and width % 8:
                cell[y * pitch + pitch - 1] |= 0xFF >> (width % 8)
            if bpp == 2 and padded:
                for x in range(width, pitch * 4):
                    cell[y * pitch + x // 4] |= 3 << (6 - 2 * (x % 4))
        glyphs.append((cp, bytes(cell), width, 0, width))
    data = bytearray(jamoset.write_svfn(width, height, height - 3, glyphs, b"", bpp=bpp))
    struct.pack_into("<H", data, 6, jamoset.FLAG_VARIABLE)
    return bytes(data)


def single_pixel_face():
    """An 8 x 8 1 bpp face whose 64 glyphs (U+0100 + n) each hold one set pixel: column n % 8, row n // 8."""
    glyphs = []
    for n in range(64):
        cell = bytearray(8)
        cell[n // 8] = 0x80 >> (n % 8)
        glyphs.append((0x100 + n, bytes(cell), 8, 0, 8))
    data = bytearray(jamoset.write_svfn(8, 8, 8, glyphs, b"", bpp=1))
    struct.pack_into("<H", data, 6, jamoset.FLAG_VARIABLE)
    return bytes(data)


def ramp_face():
    """A 16 x 16 8 bpp face whose one glyph (U+0100) holds every coverage 0..255 once (pixel n at column n % 16, row
    n // 16)."""
    glyphs = [(0x100, bytes(range(256)), 16, 0, 16)]
    data = bytearray(jamoset.write_svfn(16, 16, 16, glyphs, b"", bpp=8))
    struct.pack_into("<H", data, 6, jamoset.FLAG_VARIABLE)
    return bytes(data)


class TestBlitPaths(TargetMixin, unittest.TestCase):
    """The oracle the blit fast paths are held to: every x & 7 and page phase, clip edges inside a source byte, every
    bpp and 2 bpp threshold step, scaled (8 bpp) cells on every kind, overlapping cells, cells larger than the target;
    byte for byte against svfline (draw_target and to_target of the GRAY8 line), under ASan with guard bytes."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.tmp = tempfile.mkdtemp(prefix="svf-blit-")
        cls.marks = os.path.join(cls.tmp, "marks.svf")
        cls.bpp8 = os.path.join(cls.tmp, "bpp8.svf")
        for args, out in ((["--marks"], cls.marks), (["--bpp8", "--from", SYNTH_BASE], cls.bpp8)):
            r = subprocess.run([sys.executable, SYNTH] + args + [out], capture_output=True, text=True)
            if r.returncode != 0:
                raise AssertionError("svf_synth %s: %s" % (" ".join(args), r.stderr))
        cls.synth = {}
        for name, bpp, padded in (("thr8", 8, False), ("pad1", 1, True), ("two", 2, False)):
            cls.synth[name] = os.path.join(cls.tmp, name + ".svf")
            with open(cls.synth[name], "wb") as fh:
                fh.write(synth_face(bpp, 13, 14, {ord(c) for c in BLIT_TEXT}, padded))
        cls.overlap = {}
        for bpp in (2, 8):
            cls.overlap[bpp] = os.path.join(cls.tmp, "overlap%d.svf" % bpp)
            with open(cls.overlap[bpp], "wb") as fh:
                fh.write(overlap_face(bpp))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def blank(self, kind, w, h, **t):
        return [] if kind == "cb" else bytes(self.target(kind, w, h, **t).buf)

    def test_mono_every_phase(self):
        w, h, n = 100, 37, 0
        for face in ODD_FACES + (MARUS24, self.bpp8):
            text = BLIT_TEXT + BLIT_TEXT_EXTRA.get(face, "")
            bpp = svfline.Face.load(face).bpp
            for kind in ("mono-page", "mono-row"):
                stride = svfline.target_row_bytes(kind, w) + 3
                places = [(x, 20, 128) for x in PHASE_X] + [(3, y, 128) for y in PHASE_Y]
                if bpp != 1:
                    places += [(3, 20, thr) for thr in THRESHOLDS]
                for x, y, thr in places:
                    with self.subTest(face=os.path.basename(face), kind=kind, x=x, y=y, threshold=thr):
                        out = self.check([face], text, x, y, w, h, kind, stride=stride, threshold=thr)
                        if (x, y) == (3, 20):
                            self.assertNotEqual(out, self.blank(kind, w, h, stride=stride), "nothing drawn")
                        n += 1
        # 2 bpp levels 1, 2, 3 are coverage 85, 170, 255: thresholds 0 and 1..85 set every inked pixel, 86..170
        # levels 2 and 3, 171..255 level 3 only; the set bits never grow with the threshold.
        for face in (NGOTB14, GBA17BX1):
            text = BLIT_TEXT + BLIT_TEXT_EXTRA.get(face, "")
            for kind in ("mono-page", "mono-row"):
                bits = {thr: set_bits(self.check([face], text, 3, 20, w, h, kind, threshold=thr, fill=0))
                        for thr in THRESHOLDS}
                with self.subTest(face=os.path.basename(face), kind=kind, bits=bits):
                    counts = [bits[thr] for thr in THRESHOLDS]
                    self.assertEqual(counts, sorted(counts, reverse=True))
                    self.assertEqual(bits[0], bits[1])
                    self.assertEqual(bits[1], bits[85])
                    self.assertEqual(bits[86], bits[128])
                    self.assertEqual(bits[128], bits[170])
                    self.assertEqual(bits[171], bits[255])
                    self.assertGreater(bits[255], 0)
        print(f"\n  test_mono_every_phase: {n} lines match svfline", file=sys.stderr)

    def test_clip_at_byte_edges(self):
        w, h = 100, 37
        clips = [(x0, 3, x1, h - 3) for x0 in (0, 1, 7, 8, 9, 15, 16) for x1 in (w, w - 1, w - 7, w - 8, w - 9)] + \
                [(3, y0, w - 3, y1) for y0 in (0, 1, 7, 8, 9) for y1 in (h, h - 1, h - 5, h - 8)]
        for kind, kt in kind_runs(BUFFER_KINDS):
            fill = kt.get("fill", TARGET_FILL)
            stride = row_bytes(kind, w, kt) + 3
            for chain in ([NGOTB17], [PAPLG16, PAPLG18], [NGOTB14], [self.synth["thr8"]],
                          [self.synth["pad1"]], [self.synth["two"]]):
                for clip in clips:
                    for x, thr in [(-7, 128), (w - 20, 128)] + \
                            ([(x, thr) for x in (-3, 5, w - 20) for thr in (85, 86, 128, 171)]
                             if kind.startswith("mono") and chain[0] != NGOTB17 else []):
                        with self.subTest(kind=kind, kt=kt, chain=os.path.basename(chain[0]), clip=clip, x=x,
                                          thr=thr):
                            out = self.check(chain, BLIT_TEXT, x, 20, w, h, kind, stride=stride, clip=clip,
                                             threshold=thr, **kt)
                            if kind in ("gray8", "indexed8"):
                                x0, y0, x1, y1 = clip
                                self.assertTrue(all(v == fill for i, v in enumerate(out)
                                                    if not (x0 <= i % stride < x1 and y0 <= i // stride < y1)),
                                                "a byte outside the clip was written")

    def test_scaled_cells_every_kind(self):
        w, h = 128, 64
        for ratio in ((2, 1), (3, 2), (5, 4), (1, 2)):
            for kind, kt in kind_runs(SWEEP_KINDS):
                for chain in ([NGOTB14], [NGOTB17], [PAPLG16, PAPLG18]):
                    for thr in (128, 200) if kind.startswith("mono") else (128,):
                        for x in (-3, 0, 5, 8, 13):
                            with self.subTest(ratio=ratio, kind=kind, kt=kt, chain=os.path.basename(chain[0]),
                                              threshold=thr, x=x):
                                out = self.check(chain, BLIT_TEXT, x, 30, w, h, kind, scale=ratio, threshold=thr, **kt)
                                if x == 5:
                                    self.assertNotEqual(out, self.blank(kind, w, h, **kt), "nothing drawn")

    def test_scaled_padded_stride(self):
        """Scaled cells (3/2, 2/1) on targets whose stride is the row bytes + 3 (mono-page: a page stride wider than
        w): a row address taken from the width instead of the stride shows. The 3 padding bytes of every row (page)
        are guards: they stay TARGET_FILL."""
        n = 0
        for w, h in ((128, 64), (100, 37)):
            for kind, kt in kind_runs(BUFFER_KINDS):
                fill = kt.get("fill", TARGET_FILL)
                row = row_bytes(kind, w, kt)
                stride = row + 3
                for ratio in ((3, 2), (2, 1)):
                    for chain in ([NGOTB14], [NGOTB17], [PAPLG16, PAPLG18], [self.bpp8]):
                        for x, y in ((-3, 30), (5, 30), (13, h - 2)):
                            with self.subTest(size=(w, h), kind=kind, kt=kt, ratio=ratio,
                                              chain=os.path.basename(chain[0]), x=x, y=y):
                                t = dict(stride=stride, scale=ratio, **kt)
                                if kind in svfline.LATER_CELL_KINDS and chain == [self.bpp8]:
                                    # Overlapping cells with background levels: the later cell wins (per cell only).
                                    rc, out, err = self.draw(chain, BLIT_TEXT, x, y, w, h, kind, **t)
                                    self.assertEqual(rc, 0, err)
                                    self.assertEqual(out, self.expect(chain, BLIT_TEXT, x, y, w, h, kind, **t)[0])
                                else:
                                    out = self.check(chain, BLIT_TEXT, x, y, w, h, kind, **t)
                                self.assertTrue(all(out[i] == fill for i in range(len(out))
                                                    if i % stride >= row), "a padding byte was written")
                                if (x, y) == (5, 30):
                                    self.assertNotEqual(out, self.blank(kind, w, h, stride=stride, **kt),
                                                        "nothing drawn")
                                n += 1
        print(f"\n  test_scaled_padded_stride: {n} lines match svfline", file=sys.stderr)

    def test_overlap_every_kind(self):
        w, h, text = 128, 64, "Áè 가́"
        for kind, kt in kind_runs(SWEEP_KINDS):
            for big_endian in (False, True) if kind in svfline.RGB16_KINDS else (False,):
                for x in (0, 1, 7, 8):
                    with self.subTest(kind=kind, kt=kt, big_endian=big_endian, x=x):
                        out = self.check([self.marks, PAPLG18], text, x, 20, w, h, kind, fg=0x1234, bg=0xABCD,
                                         big_endian=big_endian, fg888=0x6C7F20E0, bg888=0x00108030, **kt)
                        self.assertNotEqual(out, self.blank(kind, w, h, **kt), "nothing drawn")

    def test_rgb555_bit15_follows_fg(self):
        """RGB555 copies bit 15 of fg to every drawn pixel (1 or 2 bpp: the level bytes; 8 bpp: the per-pixel blend)
        and leaves the rest of the target alone; the colour bits never see it (fg 0xFFFF and 0x7FFF give the same
        low 15 bits)."""
        w, h = 100, 37
        for chain in ([PAPLG16, PAPLG18], [self.bpp8], [NGOTB17]):   # 2 bpp; 8 bpp (cells overlap: per-cell ref); 1 bpp
            for big_endian in (False, True):
                order = "big" if big_endian else "little"
                low = {}
                for fg in (0xFFFF, 0x7FFF, 0x8000):
                    with self.subTest(chain=os.path.basename(chain[0]), fg=fg, big_endian=big_endian):
                        t = dict(fill=0, fg=fg, bg=0x0010, big_endian=big_endian)
                        rc, out, err = self.draw(chain, LINE_TEXTS[0], 2, 28, w, h, "rgb555", **t)
                        self.assertEqual(rc, 0, err)
                        self.assertEqual(out, self.expect(chain, LINE_TEXTS[0], 2, 28, w, h, "rgb555", **t)[0])
                        px = [int.from_bytes(out[i:i + 2], order) for i in range(0, len(out), 2)]
                        drawn = [v for v in px if v]
                        self.assertGreater(len(drawn), 50)
                        self.assertTrue(all(v >> 15 == fg >> 15 for v in drawn), "bit 15 is not fg's")
                        low[fg] = [v & 0x7FFF for v in px]
                with self.subTest(chain=os.path.basename(chain[0]), big_endian=big_endian, case="bit 15 is not a colour bit"):
                    # a failed subtest above leaves low[fg] unset: skip, the loop goes on and fails cleanly
                    if 0xFFFF in low and 0x7FFF in low:
                        self.assertEqual(low[0xFFFF], low[0x7FFF])
                    else:
                        self.fail("a bit-15 subtest failed before low[] was filled")

    def test_888_byte_order(self):
        """HL on a 1 bpp face: every inked pixel is the bytes B G R (X), X the top byte of fg888 (0x8C, then 0x00)."""
        w, h = 64, 37
        for kind, fg888, want in (("xrgb8888", 0x8C123456, bytes((0x56, 0x34, 0x12, 0x8C))),
                                  ("xrgb8888", 0x00123456, bytes((0x56, 0x34, 0x12, 0x00))),
                                  ("rgb888", 0x8C123456, bytes((0x56, 0x34, 0x12)))):
            with self.subTest(kind=kind, fg888=hex(fg888)):
                out = self.check([NEODG16D], "HL", 2, 28, w, h, kind, fg888=fg888, bg888=0x00ABCDEF)
                n = len(want)
                px = [out[i:i + n] for i in range(0, len(out), n)]
                self.assertEqual(set(px), {want, bytes([TARGET_FILL]) * n}, "a pixel is neither ink nor untouched")
                self.assertGreater(px.count(want), 20)

    def test_888_byte_order_2bpp(self):
        """A 2 bpp face: ink levels 1..3 are coverage 85, 170, 255; raw bytes B G R (X) of each level are asserted
        against hand-worked values (not svfline) and all three levels occur."""
        fg, bg = 0x8C7F20E0, 0x00108030
        # (bg * (255 - cov) + fg * cov + 127) // 255 per channel, by hand: B (0x30 -> 0xE0): cov 85 (48*170 + 224*85 +
        # 127) // 255 = 107 = 0x6B, cov 170 165 = 0xA5; G (0x80 -> 0x20): 96 = 0x60, 64 = 0x40; R (0x10 -> 0x7F):
        # 53 = 0x35, 90 = 0x5A; cov 255 is fg. Tuples are (B, G, R).
        want = {85: (0x6B, 0x60, 0x35), 170: (0xA5, 0x40, 0x5A), 255: (0xE0, 0x20, 0x7F)}
        for kind in ("xrgb8888", "rgb888"):
            with self.subTest(kind=kind):
                out = self.check([NGOTB14], "W#", 2, 28, 64, 37, kind, fg888=fg, bg888=bg)
                n = 4 if kind == "xrgb8888" else 3
                seen = {out[i:i + n] for i in range(0, len(out), n)} - {bytes([TARGET_FILL]) * n}
                exp = {bytes(b) + (b"\x8c" if n == 4 else b"") for b in want.values()}
                self.assertEqual(seen, exp)

    def test_888_padding_untouched(self):
        w, h = 100, 37
        for kind in ("xrgb8888", "rgb888"):
            row = svfline.target_row_bytes(kind, w)
            for pad in (3, 5):
                for chain in ([PAPLG16, PAPLG18], [NEODG16D], [self.bpp8]):
                    for x, y in ((2, 28), (-5, 10), (w - 10, h - 3)):
                        with self.subTest(kind=kind, pad=pad, chain=os.path.basename(chain[0]), x=x, y=y):
                            t = dict(stride=row + pad, fg888=0x8C7F20E0, bg888=0x00108030)
                            rc, out, err = self.draw(chain, LINE_TEXTS[0], x, y, w, h, kind, **t)
                            self.assertEqual(rc, 0, err)
                            self.assertEqual(out, self.expect(chain, LINE_TEXTS[0], x, y, w, h, kind, **t)[0])
                            self.assertTrue(all(out[i] == TARGET_FILL for i in range(len(out)) if i % (row + pad) >= row),
                                            "a padding byte was written")
                            if (x, y) == (2, 28):
                                self.assertNotEqual(out, self.blank(kind, w, h, **t), "nothing drawn")

    def test_888_blend_every_coverage(self):
        """Every coverage 0..255 of an 8 bpp cell, on colour pairs with edge and mid channel values, for both 888
        kinds: the C blend888 equals svfline.blend888 at each pixel (a rounding off by one at any value shows)."""
        face = os.path.join(self.tmp, "ramp.svf")
        with open(face, "wb") as fh:
            fh.write(ramp_face())
        w, h = 16, 16
        pairs = ((0xFFFFFF, 0x000000), (0x7F20E0, 0x108030), (0xFE01FF, 0x01FE00), (0x80FF7F, 0xFF0080),
                 (0x000000, 0xFFFFFF), (0x336699, 0x996633))
        for kind in ("xrgb8888", "rgb888"):
            n = svfline.target_row_bytes(kind, 1)
            for fg, bg in pairs:
                with self.subTest(kind=kind, fg=hex(fg), bg=hex(bg)):
                    t = dict(fg888=0x5A000000 | fg, bg888=bg, fill=0)
                    out = self.check([face], "\u0100", 0, 16, w, h, kind, **t)
                    for cov in range(1, 256):
                        c = svfline.blend888(fg, bg, cov)
                        want = bytes((c & 255, c >> 8 & 255, c >> 16 & 255)) + (b"\x5a" if n == 4 else b"")
                        self.assertEqual(out[cov * n:cov * n + n], want, "coverage %d" % cov)
                    self.assertEqual(out[:n], bytes(n), "coverage 0 drew")

    def test_888_width_limits(self):
        """stride is a uint16_t: XRGB8888 4w <= 65535 (w <= 16383), RGB888 3w <= 65535 (w <= 21845); h 1."""
        chain, asc = [NEODG16D], svfline.Face.load(NEODG16D).ascent
        for kind, bad, good, stride in (("xrgb8888", 16384, 16383, 65532), ("rgb888", 21846, 21845, 65535)):
            with self.subTest(kind=kind, w=bad):
                # also widths whose row wraps 16 bits to a small value: 4w = 65540 and 3w = 65541 (or the like)
                for wbad in (bad, bad + 1, 32767):
                    rc, out, err = self.draw(chain, "HL", 2, asc, wbad, 1, kind)
                    self.assertEqual(rc, 2, (wbad, err))
                    self.assertIn("SVF_E_ARG", err)
                    self.assertEqual(set(out), {TARGET_FILL} if out else set(), "a refused target was written")
            with self.subTest(kind=kind, w=good):
                drawn = False
                for y in range(asc - 15, asc + 1):   # cell row asc - y on the single target row
                    out = self.check(chain, "HL", good - 30, y, good, 1, kind, stride=stride, fg888=0x8C123456)
                    self.assertEqual(len(out), stride)
                    drawn = drawn or out != self.blank(kind, good, 1, stride=stride)
                self.assertTrue(drawn, "nothing drawn")

    def test_later_cell_lower_coverage(self):
        """A later cell with lower, non-zero coverage over pixels an earlier cell covered more ("HL" on the overlap
        faces). svfline.draw_target models the C per-cell rule: RGB565 takes the later cell's blend (it differs from
        to_target of the GRAY8 max), cb gets one call per cell (more calls than pixels). gray8 keeps the max, and a
        mono bit once set stays set (a later pixel below the threshold clears nothing), so for those kinds the
        per-cell rule and the line rule agree, and both are asserted."""
        w, h, text = 100, 37, "HLHHL"
        for bpp, face in sorted(self.overlap.items()):
            for x in (-3, 0, 5, 8):
                for kind, kt in kind_runs(SWEEP_KINDS):
                    thrs = (128, 50 if bpp == 8 else 86) if kind.startswith("mono") else (128,)
                    for big_endian in (False, True) if kind in svfline.RGB16_KINDS else (False,):
                        for thr in thrs:
                            t = dict(stride=row_bytes(kind, w, kt) + 3 if kind != "cb" else None,
                                     fg=0x1234, bg=0xABCD, big_endian=big_endian, threshold=thr,
                                     fg888=0x6C7F20E0, bg888=0x00108030, **kt)
                            with self.subTest(bpp=bpp, x=x, kind=kind, kt=kt, big_endian=big_endian, threshold=thr):
                                rc, out, err = self.draw([face], text, x, 20, w, h, kind, **t)
                                self.assertEqual(rc, 0, err)
                                cells, line = self.expect([face], text, x, 20, w, h, kind, **t)
                                self.assertEqual(out, cells, "differs from svfline.draw_target (per cell)")
                                if kind in svfline.LATER_CELL_KINDS:
                                    self.assertNotEqual(cells, line, "the case does not tell later-wins from max")
                                    # Column 5 of the line, row 0 of the cells: 'L' (later, low) over 'H'.
                                    px, py = x + OVERLAP_ADVANCE, 20 - OVERLAP_ASCENT
                                    low = svfline.Face.load(face).coverage(0x4C)[0][0]
                                    if kind in ("xrgb8888", "rgb888"):
                                        c = svfline.blend888(0x7F20E0, 0x108030, low)
                                        want = bytes((c & 255, c >> 8 & 255, c >> 16 & 255))
                                        if kind == "xrgb8888":
                                            want += b"\x6c"
                                        i = py * t["stride"] + len(want) * px
                                    else:
                                        if kind == "rgb555":
                                            c = svfline.blend555(0x1234 & 0x7FFF, 0xABCD & 0x7FFF, low) | (0x1234 & 0x8000)
                                        else:
                                            c = svfline.blend565(0x1234, 0xABCD, low)
                                        want = c.to_bytes(2, "big" if big_endian else "little")
                                        i = py * t["stride"] + 2 * px
                                    self.assertEqual(out[i:i + len(want)], want)
                                elif kind == "cb":
                                    self.assertGreater(len(out), len({(px, py) for px, py, _ in out}))
                                    self.check([face], text, x, 20, w, h, kind, **t)   # the max rule per pixel
                                else:
                                    self.assertEqual(out, line, "gray8 / mono: per cell equals the line rule")
                                    if kind.startswith("mono") and thr == 128:
                                        # 'L' alone sets nothing at 128: its pixels over 'H' are below threshold.
                                        rc, alone, err = self.draw([face], "L", x, 20, w, h, kind, **t)
                                        self.assertEqual(alone, self.blank(kind, w, h, **t))

    def test_mono_page_single_pixel(self):
        """Each of the 64 positions of an 8 x 8 cell set alone, drawn page-aligned (y = 0) and straddling a page
        boundary (y = 3), at x = 0 and x = -3, against svfline: a mirrored or shifted transpose cannot pass."""
        face = os.path.join(self.tmp, "single.svf")
        with open(face, "wb") as fh:
            fh.write(single_pixel_face())
        text = "".join(chr(0x100 + n) for n in range(64))
        for x in (0, -3):
            for y in (0, 3):
                with self.subTest(x=x, y=y):
                    out = self.check([face], text, x, y + 8, 520, 24, "mono-page", fill=0)
                    self.assertGreater(sum(bin(b).count("1") for b in out), 50)

    def test_negative_x_on_row_zero(self):
        """A cell at x < 0 whose top row is target row 0: the destination pointer must not be formed before the row
        start (the sanitizer build has -fsanitize=pointer-overflow). gray8, rgb565 (both byte orders), mono-row and
        mono-page, 1, 2 and 8 bpp sources, glyph tops at and one row above the target."""
        w, h, n = 100, 37, 0
        for chain in ([NGOTB17], [NGOTB14], [self.bpp8]):
            asc = svfline.Face.load(chain[-1]).ascent
            for (kind, kt), big_endian in [(kr, be) for kr in kind_runs(BUFFER_KINDS)
                                           for be in ((False, True) if kr[0] in svfline.RGB16_KINDS else (False,))]:
                for x in (-1, -5, -9, -17):
                    for y in (asc, asc - 1):
                        with self.subTest(chain=os.path.basename(chain[0]), kind=kind, kt=kt, big_endian=big_endian,
                                          x=x, y=y):
                            t = dict(stride=row_bytes(kind, w, kt) + 3, big_endian=big_endian,
                                     fg=0x1234, bg=0xABCD, fg888=0x6C7F20E0, bg888=0x00108030, **kt)
                            if kind in svfline.LATER_CELL_KINDS and chain == [self.bpp8]:
                                rc, out, err = self.draw(chain, BLIT_TEXT, x, y, w, h, kind, **t)
                                self.assertEqual(rc, 0, err)
                                self.assertEqual(out, self.expect(chain, BLIT_TEXT, x, y, w, h, kind, **t)[0])
                            else:
                                out = self.check(chain, BLIT_TEXT, x, y, w, h, kind, **t)
                            n += 1
        print(f"\n  test_negative_x_on_row_zero: {n} lines match svfline", file=sys.stderr)

    def test_bottom_edge(self):
        """Cells pushed over the bottom of the 100 x 37 target (rows 32..36: the last, 5-row SSD1306 page), and y1
        clips that cut a cell mid-height, on every kind for 1, 2 and 8 bpp; scaled 3/2 and 2/1 cells over the
        bottom too. Each chain and kind is asserted to write rows 32..36 somewhere."""
        w, h = 100, 37
        chains = ([NGOTB17], [NEODG16D], [MARUS24], [NGOTB14], [PAPLG16, PAPLG18], [self.bpp8])
        cases = []      # (chain, x, y_baseline, clip, scale)
        for chain in chains:
            asc = svfline.Face.load(chain[-1]).ascent
            ch = svfline.Face.load(chain[-1]).cell_h
            cases += [(chain, x, y, None, None) for y in range(33, 46) for x in (3, -5)]
            # y1 through the middle of the cells (page boundaries 8, 16, 32 and rows off them).
            cases += [(chain, 3, y1 + asc - ch // 2, (0, 0, w, y1), None) for y1 in (9, 13, 16, 30, 32, 35)]
        for chain in ([NGOTB14], [NGOTB17], [PAPLG16, PAPLG18]):
            cases += [(chain, 5, y, None, ratio) for ratio in ((3, 2), (2, 1)) for y in (30, 36, 40, 46)]
        for kind, kt in kind_runs(SWEEP_KINDS):
            fill = kt.get("fill", TARGET_FILL)
            stride = row_bytes(kind, w, kt) + 3 if kind != "cb" else None
            reached = set()
            for chain, x, y, clip, scale in cases:
                thrs = (128,) if svfline.Face.load(chain[-1]).bpp == 1 or not kind.startswith("mono") else (128, 86)
                for thr in thrs:
                    with self.subTest(kind=kind, kt=kt, chain=os.path.basename(chain[0]), x=x, y=y, clip=clip,
                                      scale=scale, threshold=thr):
                        t = dict(stride=stride, clip=clip, scale=scale, threshold=thr, **kt)
                        if kind in svfline.LATER_CELL_KINDS and chain == [self.bpp8]:
                            # Its cells overlap with non-zero background levels: the later cell wins, so only the
                            # per-cell reference applies (test_later_cell_lower_coverage).
                            rc, out, err = self.draw(chain, BLIT_TEXT, x, y, w, h, kind, **t)
                            self.assertEqual(rc, 0, err)
                            self.assertEqual(out, self.expect(chain, BLIT_TEXT, x, y, w, h, kind, **t)[0])
                        else:
                            out = self.check(chain, BLIT_TEXT, x, y, w, h, kind, **t)
                        if kind == "cb":
                            bottom = any(py >= 32 for _, py, _ in out)
                        elif kind == "mono-page":
                            bottom = any(v != fill for v in out[4 * stride:5 * stride])
                        else:
                            bottom = any(v != fill for v in out[32 * stride:])
                        if bottom:
                            reached.add((tuple(chain), scale))
                        if clip is not None and kind in ("gray8", "indexed8"):
                            self.assertTrue(all(v == fill for v in out[clip[3] * stride:]),
                                            "a row at or below y1 was written")
            for chain, _, _, _, scale in cases:
                self.assertIn((tuple(chain), scale), reached,
                              "%s %s scale %s never writes rows 32..36" % (kind, os.path.basename(chain[0]), scale))

    def test_wide_cell_on_small_target(self):
        w, h = 32, 20
        variants = [(k, dict({"fg": 0x1234, "bg": 0xABCD, "big_endian": be} if k in svfline.RGB16_KINDS else {}, **kt))
                    for k, kt in kind_runs(BUFFER_KINDS) for be in ((False, True) if k in svfline.RGB16_KINDS else (False,))]
        for kind, t in variants:   # the 16-bit kinds twice, asymmetric bytes pin the order
            for x in (-40, -8, -1, 0, 20):
                for y in (-10, 5, 19, 60):
                    with self.subTest(kind=kind, x=x, y=y, **t):
                        out = self.check([NEODG32A], BLIT_TEXT, x, y, w, h, kind, **t)
                        if y == 60:     # the cells' top row is 60 - 35 = 25, below the target's last row
                            self.assertEqual(out, self.blank(kind, w, h, **t))
                        elif (x, y) == (0, 19):
                            self.assertNotEqual(out, self.blank(kind, w, h, **t), "nothing drawn")

    # ---- INDEXED8 ------------------------------------------------------------------------------------------------

    @staticmethod
    def level_of(cov, n):
        """The ramp level of coverage cov for n >= 2 levels, written out here (not svfline's): round(cov * n / 255)."""
        return (cov * n + 127) // 255

    def test_indexed8_defaults_equal_gray8(self):
        """Base 0, 255 levels, a zero fill: a coverage byte maps to itself, so the INDEXED8 buffer is the GRAY8 one."""
        w, h, n = 100, 37, 0
        for chain in ([NGOTB17], [NGOTB14], [self.bpp8]):
            asc = svfline.Face.load(chain[-1]).ascent
            for x, y in target_places(w, h) + ((-5, asc), (-9, asc - 1)):
                with self.subTest(chain=os.path.basename(chain[0]), x=x, y=y):
                    stride = w + 3
                    rc, gray, err = self.draw(chain, BLIT_TEXT, x, y, w, h, "gray8", fill=0, stride=stride)
                    self.assertEqual(rc, 0, err)
                    rc, idx, err = self.draw(chain, BLIT_TEXT, x, y, w, h, "indexed8", fill=0, stride=stride,
                                             index_base=0, index_levels=255)
                    self.assertEqual(rc, 0, err)
                    self.assertEqual(idx, gray)
                    self.assertNotEqual(set(idx), {0}, "nothing drawn")
                    n += 1

    def test_indexed8_ramp_levels(self):
        """2 bpp faces, base 16, 3 levels, fill 0: every drawn byte is 16 + level, level in 1..3 (coverage 85, 170,
        255 -> 1, 2, 3), and all three levels occur."""
        w, h = 128, 64
        seen = set()
        for chain, text in (([PAPLG16, PAPLG18], LINE_TEXTS[0]), ([NGOTB14], BLIT_TEXT),
                            ([self.synth["two"]], BLIT_TEXT)):
            for x in (2, -3):
                with self.subTest(chain=os.path.basename(chain[0]), x=x):
                    t = dict(fill=0, index_base=16, index_levels=3)
                    rc, idx, err = self.draw(chain, text, x, 28, w, h, "indexed8", **t)
                    self.assertEqual(rc, 0, err)
                    rc, gray, err = self.draw(chain, text, x, 28, w, h, "gray8", fill=0)
                    self.assertEqual(rc, 0, err)
                    self.assertEqual(set(idx) - {0}, set(idx) & {17, 18, 19})
                    self.assertEqual(idx, bytes(16 + self.level_of(g, 3) if self.level_of(g, 3) else 0 for g in gray))
                    seen |= set(idx)
                    self.check(chain, text, x, 28, w, h, "indexed8", **t)
        self.assertEqual(seen, {0, 17, 18, 19})

    def test_indexed8_8bpp_ramp_rounding(self):
        """8 bpp coverage at level counts coprime to 255 (2, 7, 64, 128), where (cov * n + 127) / 255 rounds at
        values the 3, 63 and 255 level ramps never reach: every byte is base + round(cov * n / 255)."""
        w, h = 100, 37
        for n in (2, 7, 64, 128, 254):
            with self.subTest(levels=n):
                chain = [self.synth["thr8"], self.bpp8]
                rc, idx, err = self.draw(chain, BLIT_TEXT, 3, 28, w, h, "indexed8", fill=0, index_base=1,
                                         index_levels=n)
                self.assertEqual(rc, 0, err)
                rc, gray, err = self.draw(chain, BLIT_TEXT, 3, 28, w, h, "gray8", fill=0)
                self.assertEqual(rc, 0, err)
                self.assertEqual(idx, bytes(1 + self.level_of(g, n) if self.level_of(g, n) else 0 for g in gray))
                self.check(chain, BLIT_TEXT, 3, 28, w, h, "indexed8", fill=0, index_base=1, index_levels=n)

    def test_indexed8_threshold_form(self):
        """One level: a pixel is the single index base + 1 when the mono rule sets it (coverage >= the threshold, 0 as
        1): the bytes unpacked are the mono-row bits of the same line."""
        w, h = 96, 40
        for chain, text in (([PAPLG16, PAPLG18], LINE_TEXTS[0]), ([self.synth["two"]], BLIT_TEXT),
                            ([self.bpp8], BLIT_TEXT), ([self.synth["thr8"]], BLIT_TEXT),
                            ([NGOTB17], BLIT_TEXT), ([self.synth["pad1"]], BLIT_TEXT)):     # 1 bpp: always set
            for thr in THRESHOLDS:
                with self.subTest(chain=os.path.basename(chain[0]), threshold=thr):
                    rc, idx, err = self.draw(chain, text, 2, 28, w, h, "indexed8", fill=0, index_base=16,
                                             index_levels=1, threshold=thr)
                    self.assertEqual(rc, 0, err)
                    rc, mono, err = self.draw(chain, text, 2, 28, w, h, "mono-row", fill=0, threshold=thr)
                    self.assertEqual(rc, 0, err)
                    bits = bytes(17 if mono[y * (w // 8) + x // 8] >> (7 - x % 8) & 1 else 0
                                 for y in range(h) for x in range(w))
                    self.assertEqual(idx, bits)
                    self.assertIn(17, idx, "nothing drawn")

    def test_indexed8_max_rule(self):
        """Overlapping cells ("HLHHL": a later, lower cell over an earlier one) keep the greater index, whatever the
        fill: draw_target, to_target of the GRAY8 line and the C bytes agree; fill 255 is never lowered."""
        w, h, text = 100, 37, "HLHHL"
        for bpp, face in sorted(self.overlap.items()):
            for base, n in ((16, 3), (64, 63)):
                for fill in (0, base - 1, base + 1, base + n, base + n + 1, 255):
                    for x in (-3, 0, 5):
                        with self.subTest(bpp=bpp, base=base, levels=n, fill=fill, x=x):
                            t = dict(fill=fill, index_base=base, index_levels=n, stride=w + 3)
                            rc, out, err = self.draw([face], text, x, 20, w, h, "indexed8", **t)
                            self.assertEqual(rc, 0, err)
                            cells, line = self.expect([face], text, x, 20, w, h, "indexed8", **t)
                            self.assertEqual(out, cells)
                            self.assertEqual(out, line)
                            if fill == 255:
                                self.assertEqual(set(out), {255})
                            elif fill == 0:
                                self.assertTrue(any(out[i] > fill for i in range(len(out))), "nothing drawn")
                                self.assertTrue(all(v == 0 or base < v <= base + n for i, v in enumerate(out)
                                                    if i % (w + 3) < w), "a byte outside the ramp")

    def test_indexed8_max_rule_1bpp(self):
        """1 bpp sets index base + n (the ramp's top): over a fill of base + n, base + n + 1 or 255 the byte stays,
        under it the byte becomes the top. (Removing the max from the 1 bpp loop fails this.)"""
        w, h = 100, 37
        for chain in ([NGOTB17], [NEODG16D], [self.synth["pad1"]]):
            for base, n in ((16, 3), (64, 63), (0, 255), (200, 55)):
                top = base + n
                for fill in sorted({0, top - 1, top, min(top + 1, 255), 255}):
                    for x in (-3, 0, 5):
                        with self.subTest(chain=os.path.basename(chain[0]), base=base, levels=n, fill=fill, x=x):
                            t = dict(fill=fill, index_base=base, index_levels=n, stride=w + 3)
                            out = self.check(chain, BLIT_TEXT, x, 20, w, h, "indexed8", **t)
                            self.assertEqual(set(out), {fill} if fill >= top else {fill, top})

    def test_indexed8_level0_untouched(self):
        """8 bpp coverage 1..42 is level 0 at 3 levels (round(42 * 3 / 255) = 0): the pixel stays the fill; 43 is
        level 1 (a control that the face draws at all)."""
        faces = []
        for lo, hi in ((1, 42), (43, 43)):
            cell = bytearray(8 * 8)
            for i in range(64):
                cell[i] = lo + i % (hi - lo + 1)
            glyphs = [(0x41, bytes(cell), 8, 0, 8)]
            data = bytearray(jamoset.write_svfn(8, 8, 8, glyphs, b"", bpp=8))
            struct.pack_into("<H", data, 6, jamoset.FLAG_VARIABLE)
            path = os.path.join(self.tmp, "lvl%d.svf" % lo)
            with open(path, "wb") as fh:
                fh.write(bytes(data))
            faces.append(path)
        for fill in (0, 7, 200):
            for x in (0, -3):
                t = dict(fill=fill, index_base=16, index_levels=3)
                with self.subTest(fill=fill, x=x):
                    out = self.check([faces[0]], "A", x, 12, 16, 16, "indexed8", **t)
                    self.assertEqual(set(out), {fill})
        out = self.check([faces[1]], "A", 0, 12, 16, 16, "indexed8", fill=0, index_base=16, index_levels=3)
        self.assertEqual(set(out), {0, 17})

    def test_indexed8_refused(self):
        w, h = 100, 37
        for base, levels in ((0, 0), (200, 56), (255, 1), (1, 255), (100, 156)):
            with self.subTest(base=base, levels=levels):
                rc, out, err = self.draw([MARUS24], "Score", 2, 20, w, h, "indexed8", fill=5, index_base=base,
                                         index_levels=levels)
                self.assertEqual(rc, 2, err)
                self.assertIn("SVF_E_ARG", err)
                self.assertEqual(set(out), {5})
        # The boundary is accepted: base + levels = 255.
        for base, levels in ((200, 55), (0, 255), (254, 1), (100, 155)):
            with self.subTest(accepted=(base, levels)):
                self.check([MARUS24], "Score", 2, 20, w, h, "indexed8", fill=0, index_base=base, index_levels=levels)


SCALE_RATIOS = ((2, 1), (3, 1), (3, 2), (5, 4))
SCALE_EXTRA = ((1, 2), (4, 6))                  # downscaling, and a ratio reduced by gcd (2/3)
SCALE_W, SCALE_H = 640, 100
SCALE_PLACES = ((2, 70), (-5, 10), (630, 90))   # inside; cut at the left and top; cut at the right and bottom


class TestBlitPathsBytes(TestBlitPaths):
    """TestBlitPaths again on the byte-loop build (SVF_WORD_STORE=0): the same bytes."""
    EXE = "svfdump-bytes"


WORD_KINDS = ("indexed8", "rgb565", "rgb555", "xrgb8888", "rgb888", "gray")   # the packed kinds (gray: every bits x order)
# Fills above the ramp top (16 + 3 = 19: fill 20) and just above its base (fill 17) make a word store that stores instead
# of taking the max visible; (0, 255) over fill 0 is the full ramp.
WORD_VARIANTS = (dict(index_base=16, index_levels=3, fill=20), dict(index_base=16, index_levels=3, fill=17),
                 INDEXED8_VARIANTS[-1])


class TestWordStores(TargetMixin, unittest.TestCase):
    """The word stores (SVF_WORD_STORE: 4 px INDEXED8 load-max-store, 2 px RGB16 pairs) are byte-identical to the byte
    loops: every source phase against every target alignment, cuts inside a word group, narrow targets, and padding
    bits of a stored cell never reaching the target. The expected bytes come from svfline, so the byte loops are the
    oracle for the word paths. (Padding bits that are set never reach the target: c/tests/test_pad.c, TestBlitPadding;
    the checks below are not redundant with TestBlitPaths: test_word_path_cut_edges puts every clip edge inside every
    word group, test_misalign_every_phase every destination alignment, test_narrow_targets targets narrower than a
    word.)"""

    @classmethod
    def setUpClass(cls):
        build()
        cls.tmp = tempfile.mkdtemp(prefix="svf-word-")
        cls.bpp8 = os.path.join(cls.tmp, "bpp8.svf")
        r = subprocess.run([sys.executable, SYNTH, "--bpp8", "--from", SYNTH_BASE, cls.bpp8], capture_output=True,
                           text=True)
        if r.returncode != 0:
            raise AssertionError("svf_synth --bpp8: " + r.stderr)
        cps = {ord(c) for c in BLIT_TEXT}
        cls.faces = {}
        # pad1: 13 px, pitch 2, 3 pad bits set. two3: 2 bpp all level 3, 3 padding pixels at level 3. twopad: 2 bpp
        # cycling levels 1..3, the same padding.
        for name, args in (("pad1", (1, 13, 14, cps, True)), ("two3", (2, 13, 14, cps, True, True)),
                           ("twopad", (2, 13, 14, cps, True)), ("thr8", (8, 13, 14, cps))):
            cls.faces[name] = os.path.join(cls.tmp, name + ".svf")
            with open(cls.faces[name], "wb") as fh:
                fh.write(synth_face(*args))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def runs(kinds):
        return [(k, kt) for k in kinds
                for kt in (WORD_VARIANTS if k == "indexed8" else GRAY_VARIANTS if k == "gray" else ({},))]

    def test_misalign_every_phase(self):
        w, h, n = 100, 37, 0
        for chain in ([NGOTB17], [NGOTB14], [MARUS24], [self.bpp8], [self.faces["thr8"]]):
            for kind, kt in self.runs(WORD_KINDS):
                # bpp8 is an overlapping jamo set: a colour target draws its cells later-wins, the GRAY8 line max, so
                # check() cannot compare the two; the colour kinds take thr8 (no overlap) as the 8 bpp face (indexed8
                # and gray are max-rule kinds: they take bpp8 too)
                if chain[0] == self.bpp8 and kind not in ("indexed8", "gray"):
                    continue
                stride = row_bytes(kind, w, kt) + 3
                for mis in (1, 2, 3):
                    for x in PHASE_X:
                        with self.subTest(chain=os.path.basename(chain[0]), kind=kind, kt=kt, misalign=mis, x=x):
                            self.check(chain, BLIT_TEXT, x, 20, w, h, kind, stride=stride, misalign=mis, **kt)
                            n += 1
        print(f"\n  test_misalign_every_phase: {n} lines match svfline", file=sys.stderr)

    def test_word_path_cut_edges(self):
        w, h, n = 20, 37, 0
        bpx = {"indexed8": 1, "rgb565": 2, "rgb555": 2}
        for face in ("pad1", "two3", "twopad"):
            chain = [self.faces[face]]
            for kind in ("indexed8", "rgb565", "rgb555"):
                stride = svfline.target_row_bytes(kind, w) + 3
                for x0 in range(0, 9):
                    for x1 in range(w - 8, w + 1):
                        for x in (-3, 0, 1, 2, 3, 5):
                            clip = (x0, 3, x1, h - 3)
                            with self.subTest(face=face, kind=kind, clip=clip, x=x):
                                out = self.check(chain, BLIT_TEXT, x, 20, w, h, kind, stride=stride, clip=clip)
                                self.assertTrue(
                                    all(v == TARGET_FILL for i, v in enumerate(out)
                                        if not (x0 <= i % stride // bpx[kind] < x1 and 3 <= i // stride < h - 3)),
                                    "a byte outside the clip was written")
                                n += 1
        print(f"\n  test_word_path_cut_edges: {n} lines match svfline", file=sys.stderr)

    def test_narrow_targets(self):
        n = 0
        for face in ("pad1", "two3", "twopad", "thr8"):
            for kind, kt in self.runs(WORD_KINDS):
                for w in (1, 2, 3):
                    for x in range(-4, 4):
                        for mis in (0, 1):
                            with self.subTest(face=face, kind=kind, kt=kt, w=w, x=x, misalign=mis):
                                self.check([self.faces[face]], BLIT_TEXT, x, 14, w, 20, kind, misalign=mis, **kt)
                                n += 1
        print(f"\n  test_narrow_targets: {n} lines match svfline", file=sys.stderr)


class TestGrayKind(TargetMixin, unittest.TestCase):
    """SVF_T_GRAY (svfdump --target=gray --gray-bits=N [--lsb-first]) beyond the sweeps (which run every bits x order
    against svfline): the equalities svf.h states with GRAY8 and MONO_ROW, the packing as grey_pack.h does it, where the
    threshold is read, and the padding bits of a row's last byte."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.tmp = tempfile.mkdtemp(prefix="svf-gray-")
        cls.bpp8 = os.path.join(cls.tmp, "bpp8.svf")
        r = subprocess.run([sys.executable, SYNTH, "--bpp8", "--from", SYNTH_BASE, cls.bpp8], capture_output=True,
                           text=True)
        if r.returncode != 0:
            raise AssertionError("svf_synth --bpp8: " + r.stderr)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def out(self, chain, text, x, y, w, h, kind, **t):
        rc, out, err = self.draw(chain, text, x, y, w, h, kind, **t)
        self.assertEqual(rc, 0, err)
        return out

    def test_bits8_equals_gray8(self):
        w, h, n = 100, 37, 0
        for face in ODD_FACES + (MARUS24, self.bpp8):
            text = BLIT_TEXT + BLIT_TEXT_EXTRA.get(face, "")
            for x in PHASE_X:
                want = self.out([face], text, x, 20, w, h, "gray8")
                for lsb in (False, True):
                    with self.subTest(face=os.path.basename(face), x=x, lsb_first=lsb):
                        self.assertEqual(self.out([face], text, x, 20, w, h, "gray", gray_bits=8, lsb_first=lsb), want)
                        n += 1
        self.assertGreater(n, 0)

    def test_packed_every_phase(self):
        """Every packed variant (bits 1, 2, 4, both orders) at every x & 7 phase on faces of every bpp, stride row + 3,
        against svfline (the sweeps' check: the line rule and the per-cell rule). Bits 1 also over THRESHOLDS x
        PHASE_X on the 2 bpp and 8 bpp faces (the threshold steps), and for bits 2 and 4 the 2 bpp steps give the same
        bytes at every threshold."""
        w, h, n = 100, 37, 0
        for face in ODD_FACES + (MARUS24, self.bpp8):
            text = BLIT_TEXT + BLIT_TEXT_EXTRA.get(face, "")
            bpp = svfline.Face.load(face).bpp
            for kt in GRAY_VARIANTS:
                if kt["gray_bits"] == 8:
                    continue
                stride = row_bytes("gray", w, kt) + 3
                for x in PHASE_X:
                    with self.subTest(face=os.path.basename(face), x=x, **kt):
                        self.check([face], text, x, 20, w, h, "gray", stride=stride, **kt)
                        n += 1
                if kt["gray_bits"] == 1 and bpp != 1:
                    for thr in THRESHOLDS:
                        for x in PHASE_X:
                            with self.subTest(face=os.path.basename(face), x=x, threshold=thr, **kt):
                                self.check([face], text, x, 20, w, h, "gray", stride=stride, threshold=thr, **kt)
                                n += 1
        for face in (NGOTB14, GBA17BX1):
            text = BLIT_TEXT + BLIT_TEXT_EXTRA.get(face, "")
            for bits in (2, 4):
                outs = {thr: self.out([face], text, 3, 20, w, h, "gray", gray_bits=bits, threshold=thr)
                        for thr in THRESHOLDS}
                with self.subTest(face=os.path.basename(face), bits=bits):
                    self.assertEqual(len(set(outs.values())), 1)
        self.assertGreater(n, 0)

    def test_bits1_equals_mono_row(self):
        w, h = 100, 37
        for face in ODD_FACES + (MARUS24, self.bpp8):
            text = BLIT_TEXT + BLIT_TEXT_EXTRA.get(face, "")
            for thr in (1, 128, 255):
                for x in (-3, 0, 5, 8, 13):
                    with self.subTest(face=os.path.basename(face), threshold=thr, x=x):
                        self.assertEqual(self.out([face], text, x, 20, w, h, "gray", gray_bits=1, threshold=thr),
                                         self.out([face], text, x, 20, w, h, "mono-row", threshold=thr))

    def test_bits4_equals_grey_pack(self):
        """Only 1 bpp and 2 bpp faces: c/ports/grey_pack.h packs a GRAY8 buffer as cov >> 4, which equals the rule
        (cov * 15 + 127) / 255 only on the levels 0, 85, 170 and 255 those faces hold (5, 10, 15 both ways)."""
        w, h = 100, 37
        for face in ODD_FACES:
            text = BLIT_TEXT + BLIT_TEXT_EXTRA.get(face, "")
            for x in (-3, 0, 5, 8, 13):
                with self.subTest(face=os.path.basename(face), x=x):
                    g8 = self.out([face], text, x, 20, w, h, "gray8", fill=0)
                    packed = bytes(g8[i] >> 4 << 4 | g8[i + 1] >> 4 for i in range(0, len(g8), 2))
                    self.assertEqual(self.out([face], text, x, 20, w, h, "gray", gray_bits=4, fill=0), packed)

    def test_threshold_only_bits1(self):
        w, h = 100, 37
        for bits in (2, 4):
            for lsb in (False, True):
                with self.subTest(bits=bits, lsb_first=lsb):
                    a = self.out([NGOTB14], BLIT_TEXT, 3, 20, w, h, "gray", gray_bits=bits, lsb_first=lsb, threshold=1)
                    b = self.out([NGOTB14], BLIT_TEXT, 3, 20, w, h, "gray", gray_bits=bits, lsb_first=lsb, threshold=255)
                    self.assertEqual(a, b)
        a = self.out([NGOTB14], BLIT_TEXT, 3, 20, w, h, "gray", gray_bits=1, threshold=1)
        b = self.out([NGOTB14], BLIT_TEXT, 3, 20, w, h, "gray", gray_bits=1, threshold=255)
        self.assertNotEqual(a, b)

    def test_padding_bits_untouched(self):
        """w 61: bits 1 leaves 3 padding bits in the last byte, bits 2 leaves 3 pixels' worth (6 bits), bits 4 one
        pixel's (4 bits). A line that crosses column 60 leaves them as filled (0xA5)."""
        w, h, fill = 61, 37, 0xA5
        for bits in (1, 2, 4):
            stride = (w * bits + 7) // 8
            used = w * bits - (stride - 1) * 8           # bits of the last byte that hold pixels
            for lsb in (False, True):
                pad = ((1 << (8 - used)) - 1) << used if lsb else (1 << (8 - used)) - 1
                crossed = False
                for x in (40, 45, 52):
                    with self.subTest(bits=bits, lsb_first=lsb, x=x):
                        out = self.check([MARUS24], "WM#", x, 20, w, h, "gray", gray_bits=bits, lsb_first=lsb,
                                         fill=fill)
                        for row in range(h):
                            last = out[row * stride + stride - 1]
                            self.assertEqual(last & pad, fill & pad, "padding bits of row %d" % row)
                            crossed = crossed or last & ~pad & 0xFF != fill & ~pad & 0xFF
                self.assertTrue(crossed, "no line reached the last byte's pixels")

    def test_refused_bits_and_strides(self):
        w, h = 100, 37
        for bits in (0, 3, 5, 16, 255):
            with self.subTest(bits=bits):
                rc, out, err = self.draw([MARUS24], "Score", 2, 20, w, h, "gray", gray_bits=bits)
                self.assertEqual(rc, 2, err)
                self.assertIn("SVF_E_ARG", err)
                self.assertEqual(set(out), {TARGET_FILL}, "a refused target was written")
        for bits in (1, 2, 4, 8):
            row = (w * bits + 7) // 8
            with self.subTest(bits=bits, case="stride"):
                rc, out, err = self.draw([MARUS24], "Score", 2, 20, w, h, "gray", gray_bits=bits, stride=row - 1)
                self.assertEqual(rc, 2, err)
                self.assertIn("SVF_E_ARG", err)


class TestBlitPadding(unittest.TestCase):
    """c/tests/test_pad.c: the blitters on stored cells whose padding bits are inked (svf_glyph clears them, so no
    draw reaches this), INDEXED8, RGB16 and GRAY (bits 1, 2, 4, both bit orders) at 1 and 2 bpp, every phase and clip edge, whole buffer against a model;
    the word build and the byte build must print the same line."""

    def test_padding_never_leaks(self):
        b = build()
        outs = []
        for exe in ("test-pad", "test-pad-bytes"):
            r = subprocess.run([b[exe]], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, exe + ": " + r.stderr)
            self.assertTrue(r.stdout.startswith("pad: OK "), r.stdout)
            outs.append(r.stdout)
        self.assertEqual(outs[0], outs[1])


class TestWordStoresBytes(TestWordStores):
    """TestWordStores again on the byte-loop build: the same bytes."""
    EXE = "svfdump-bytes"



def build_noscale():
    """make lib-noscale svfdump-noscale (the library built with -DSVF_NO_SCALE) into the build dir."""
    b = build()
    if "svfdump-noscale" not in b:
        r = subprocess.run(["make", "-s", "-C", C_DIR, "O=" + b["dir"], "lib-noscale", "svfdump-noscale"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError("make lib-noscale svfdump-noscale failed:\n" + r.stdout + r.stderr)
        b["svfdump-noscale"] = os.path.join(b["dir"], "svfdump-noscale")
        b["noscale-obj"] = os.path.join(b["dir"], "noscale")
    return b


class TestTargetsSwitch(TargetMixin, unittest.TestCase):
    """SVF_TARGETS=0x02 (svfdump-page, MONO_PAGE only) and 0x1E8 (svfdump-vesa, the five packed kinds): the same bytes
    on a kept kind as the default build; every other kind is SVF_E_ARG with the buffer untouched."""

    def test_kind_left_out_is_refused(self):
        w, h, chain, text = 128, 64, [PAPLG16, PAPLG18], LINE_TEXTS[0]
        opts = self.opts_of("mono-page")
        rc, out, err = line_run("line", chain, text, w, h, 2, 28, opts=opts, exe_name="svfdump-page")
        self.assertEqual(rc, 0, err)
        rc0, out0, err0 = line_run("line", chain, text, w, h, 2, 28, opts=opts)
        self.assertEqual(rc0, 0, err0)
        self.assertEqual(out, out0)
        self.assertNotEqual(set(out), {TARGET_FILL}, "nothing was drawn")
        for kind in ("gray8", "mono-row", "rgb565", "rgb555", "indexed8", "xrgb8888", "rgb888", "gray", "cb"):
            with self.subTest(kind=kind):
                rc, out, err = line_run("line", chain, text, w, h, 2, 28, opts=self.opts_of(kind),
                                        exe_name="svfdump-page")
                self.assertEqual(rc, 2, err)
                self.assertIn("SVF_E_ARG", err)
                if kind == "cb":
                    self.assertEqual(out, b"", "a refused callback target plotted")
                else:
                    size = svfline.target_rows(kind, h) * svfline.target_row_bytes(kind, w)
                    self.assertEqual(out, bytes([TARGET_FILL]) * size, "a refused target was written or not returned")


    def test_page_refuses_new_kinds(self):
        """svfdump-page (0x02): the four kinds added for VESA are SVF_E_ARG, the buffer comes back as it was filled."""
        w, h, chain, text = 128, 64, [PAPLG16, PAPLG18], LINE_TEXTS[0]
        for kind in ("indexed8", "rgb555", "xrgb8888", "rgb888"):
            with self.subTest(kind=kind):
                rc, out, err = line_run("line", chain, text, w, h, 2, 28, opts=self.opts_of(kind),
                                        exe_name="svfdump-page")
                self.assertEqual(rc, 2, err)
                self.assertIn("SVF_E_ARG", err)
                size = svfline.target_rows(kind, h) * svfline.target_row_bytes(kind, w)
                self.assertEqual(out, bytes([TARGET_FILL]) * size)

    def test_gray_only_build(self):
        """svfdump-gray (0x200: GRAY only): GRAY draws the bytes the default build draws (bits 8, and the packed bits
        too); GRAY8 and the others are SVF_E_ARG with exit 2."""
        w, h, chain, text = 128, 64, [PAPLG16, PAPLG18], LINE_TEXTS[0]
        for bits, lsb in ((8, False), (4, False), (2, True), (1, False)):
            for x, y in target_places(w, h):
                with self.subTest(bits=bits, x=x, y=y):
                    opts = self.opts_of("gray", gray_bits=bits, lsb_first=lsb)
                    rc, out, err = line_run("line", chain, text, w, h, x, y, opts=opts, exe_name="svfdump-gray")
                    self.assertEqual(rc, 0, err)
                    rc0, out0, err0 = line_run("line", chain, text, w, h, x, y, opts=opts)
                    self.assertEqual(rc0, 0, err0)
                    self.assertEqual(out, out0)
                    if (x, y) == (2, 28):
                        self.assertNotEqual(set(out), {TARGET_FILL}, "nothing was drawn")
        for kind in ("gray8", "mono-page", "mono-row", "rgb565", "indexed8", "rgb555", "xrgb8888", "rgb888", "cb"):
            with self.subTest(kind=kind):
                rc, out, err = line_run("line", chain, text, w, h, 2, 28, opts=self.opts_of(kind),
                                        exe_name="svfdump-gray")
                self.assertEqual(rc, 2, err)
                self.assertIn("SVF_E_ARG", err)

    def test_vesa_build_matches_default(self):
        """svfdump-vesa (0x1E8: RGB565, INDEXED8, RGB555, XRGB8888, RGB888): the five packed kinds draw the bytes the
        default build draws; GRAY8, MONO_PAGE, MONO_ROW and the callback are SVF_E_ARG."""
        w, h, chain, text = 128, 64, [PAPLG16, PAPLG18], LINE_TEXTS[0]
        for kind in ("rgb565", "indexed8", "rgb555", "xrgb8888", "rgb888"):
            for x, y in target_places(w, h):
                with self.subTest(kind=kind, x=x, y=y):
                    opts = self.opts_of(kind)
                    rc, out, err = line_run("line", chain, text, w, h, x, y, opts=opts, exe_name="svfdump-vesa")
                    self.assertEqual(rc, 0, err)
                    rc0, out0, err0 = line_run("line", chain, text, w, h, x, y, opts=opts)
                    self.assertEqual(rc0, 0, err0)
                    self.assertEqual(out, out0)
                    if (x, y) == (2, 28):
                        self.assertNotEqual(set(out), {TARGET_FILL}, "nothing was drawn")
        for kind in ("gray8", "mono-page", "mono-row", "gray", "cb"):
            with self.subTest(kind=kind):
                rc, out, err = line_run("line", chain, text, w, h, 2, 28, opts=self.opts_of(kind),
                                        exe_name="svfdump-vesa")
                self.assertEqual(rc, 2, err)
                self.assertIn("SVF_E_ARG", err)
                if kind == "cb":
                    self.assertEqual(out, b"")
                else:
                    size = svfline.target_rows(kind, h) * svfline.target_row_bytes(kind, w)
                    self.assertEqual(out, bytes([TARGET_FILL]) * size)


class TestScale(unittest.TestCase):
    """svf_chain.scale_num / scale_den: whole multiples as N x N blocks, other ratios area-averaged; against
    tools/svfline.py (layout, draw_target, measure with scale=)."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.tmp = tempfile.mkdtemp(prefix="svf-scale-")
        cls.marks = os.path.join(cls.tmp, "marks.svf")
        r = subprocess.run([sys.executable, SYNTH, "--marks", cls.marks], capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError("svf_synth --marks: " + r.stderr)
        cls.chains = ([PAPLG16, PAPLG18], [MARUS24], [jamo16()], [cls.marks, PAPLG18])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_line(self, chain, text, x, y, w, h, ratio, opts=(), kind="gray8", exe=None):
        args = ["--scale=%d/%d" % ratio, "--target=" + kind] + list(opts)
        if exe is None:
            rc, out, err = line_run("line", chain, text, w, h, x, y, opts=args)
        else:
            t = text.encode("utf-8") if isinstance(text, str) else text
            r = subprocess.run([build_noscale()[exe]] + args + ["line", str(w), str(h), str(x), str(y)] +
                               [t] + list(chain), capture_output=True)
            rc, out, err = r.returncode, r.stdout, r.stderr.decode(errors="replace")
        self.assertNotIn("Sanitizer", err)
        self.assertNotIn("runtime error", err)
        self.assertNotIn("guard bytes changed", err)
        if kind == "cb":
            out = [tuple(int(v) for v in ln.split()) for ln in out.decode().splitlines()]
        return rc, out, err

    def ok(self, *a, **k):
        rc, out, err = self.run_line(*a, **k)
        self.assertEqual(rc, 0, err)
        return out

    @staticmethod
    def want(chain, text, x, y, w, h, ratio, kind="gray8", clip=None, **t):
        places = svfline.placements(svfline.load_chain(chain), text, x, y, scale=ratio)
        tgt = svfline.draw_target(places, svfline.Target(kind, w, h, **t), clip)
        return tgt.plots if kind == "cb" else bytes(tgt.buf)

    def test_scaled_lines_match_reference(self):
        n = 0
        for ratio in SCALE_RATIOS + SCALE_EXTRA:
            for kind in ("gray8", "mono-page"):
                for chain in self.chains:
                    for text in LINE_TEXTS:
                        for x, y in SCALE_PLACES:
                            with self.subTest(ratio=ratio, kind=kind, chain="+".join(map(os.path.basename, chain)),
                                              text=text, x=x, y=y):
                                out = self.ok(chain, text, x, y, SCALE_W, SCALE_H, ratio, kind=kind)
                                self.assertEqual(out, self.want(chain, text, x, y, SCALE_W, SCALE_H, ratio, kind))
                                if kind == "gray8":
                                    self.assertEqual(out, bytes(svfline.layout(chain, text, x, y, SCALE_W, SCALE_H,
                                                                               scale=ratio)))
                                drawable = any(svfline.Face.load(f).has(ord(ch)) for f in chain for ch in text.strip())
                                if drawable and (x, y) == SCALE_PLACES[0]:
                                    self.assertTrue(any(out), "nothing drawn")
                                n += 1
        print(f"\n  test_scaled_lines_match_reference: {n} lines match svfline", file=sys.stderr)

    def test_integer_scale_is_block_copy(self):
        """N/1 at (N*x, N*y) is the 1/1 line at (x, y) with every pixel an N x N block (an independent check of the
        reference's integer path); 2/2 and 0/0 are 1/1."""
        w, h = 200, 40
        for chain in self.chains:
            for text in LINE_TEXTS[:4]:
                base = svfline.layout(chain, text, 1, 28, w, h)
                for n in (2, 3):
                    with self.subTest(chain="+".join(map(os.path.basename, chain)), text=text, n=n):
                        out = self.ok(chain, text, n, 28 * n, w * n, h * n, (n, 1))
                        self.assertEqual(out, bytes(base[(i // (w * n) // n) * w + (i % (w * n)) // n]
                                                    for i in range(w * n * h * n)))
                for ratio in ((2, 2), (0, 0), (16, 16)):
                    with self.subTest(chain="+".join(map(os.path.basename, chain)), text=text, ratio=ratio):
                        self.assertEqual(self.ok(chain, text, 1, 28, w, h, ratio), bytes(base))

    def test_box_filter_exact(self):
        """svfline.scale_coverage: every output pixel is the area-weighted mean of the source (outside the cell
        counts 0) rounded half up, computed here with fractions."""
        from fractions import Fraction
        import random
        rnd = random.Random(6)
        for num, den in ((3, 2), (5, 4), (1, 2), (2, 3), (7, 16), (16, 15), (3, 1)):
            for w, h in ((1, 1), (5, 3), (9, 7)):
                rows = [[rnd.choice((0, 85, 170, 255, rnd.randrange(256))) for _ in range(w)] for _ in range(h)]
                got = svfline.scale_coverage(rows, num, den)
                sw, sh = -(-w * num // den), -(-h * num // den)
                self.assertEqual((len(got), len(got[0])), (sh, sw))
                for oy in range(sh):
                    for ox in range(sw):
                        acc = Fraction(0)
                        for sy in range(h):
                            wy = max(0, min(Fraction(sy + 1), Fraction((oy + 1) * den, num)) -
                                     max(Fraction(sy), Fraction(oy * den, num)))
                            for sx in range(w):
                                wx = max(0, min(Fraction(sx + 1), Fraction((ox + 1) * den, num)) -
                                         max(Fraction(sx), Fraction(ox * den, num)))
                                acc += rows[sy][sx] * wx * wy
                        mean = acc / Fraction(den, num) ** 2
                        self.assertEqual(got[oy][ox], int(mean + Fraction(1, 2)), (num, den, w, h, ox, oy))
        self.assertEqual([svfline.scale_len(v, 3, 2) for v in (-3, -1, 0, 1, 3, 5)], [-5, -2, 0, 2, 5, 8])
        self.assertEqual([svfline.scale_len(v, 2, 3) for v in (-2, -1, 1, 2)], [-1, -1, 1, 1])

    def test_scaled_targets(self):
        """Every target kind at 3/2 and 2/1, the marks over their base (overlap: RGB565 later cell wins, one cb call a
        cell pixel, row-major in each scaled cell), with and without a clip."""
        w, h = 100, 37
        for ratio in ((3, 2), (2, 1)):
            for kind, kt in kind_runs(SWEEP_KINDS):
                for chain, text in (([self.marks, PAPLG18], "Áè 가"), ([PAPLG16, PAPLG18], LINE_TEXTS[0])):
                    for clip in (None, (3, 3, w - 3, h - 3)):
                        with self.subTest(ratio=ratio, kind=kind, kt=kt, chain=os.path.basename(chain[0]), clip=clip):
                            t = dict(fg565=0x8410, bg565=0x1F, threshold=100, big_endian=True)
                            opts = ["--fg=%d" % t["fg565"], "--bg=%d" % t["bg565"], "--threshold=100", "--big-endian"]
                            if kind in ("xrgb8888", "rgb888"):      # X byte 0x6C in fg888 for XRGB8888
                                t.update(fg888=0x6C7F20E0, bg888=0x00108030)
                                opts += ["--fg888=%d" % t["fg888"], "--bg888=%d" % t["bg888"]]
                            if kind == "indexed8":      # this test builds its Target and options itself
                                t.update(index_base=kt["index_base"], index_levels=kt["index_levels"],
                                         buf=bytearray([kt["fill"]]) * (svfline.target_rows(kind, h) * w))
                                opts += ["--index-base=%d" % kt["index_base"], "--index-levels=%d" % kt["index_levels"],
                                         "--fill=%d" % kt["fill"]]
                            if kind == "gray":
                                t.update(gray_bits=kt["gray_bits"], lsb_first=kt["lsb_first"])
                                opts += ["--gray-bits=%d" % kt["gray_bits"]] + (["--lsb-first"] if kt["lsb_first"] else [])
                            if clip:
                                opts.append("--clip=%d:%d:%d:%d" % clip)
                            out = self.ok(chain, text, -3, 30, w, h, ratio, opts=opts, kind=kind)
                            self.assertEqual(out, self.want(chain, text, -3, 30, w, h, ratio, kind, clip, **t))

    def test_scaled_measure(self):
        for ratio in SCALE_RATIOS + SCALE_EXTRA:
            for chain in self.chains:
                for text in LINE_TEXTS + (INVALID_UTF8,):
                    with self.subTest(ratio=ratio, chain="+".join(map(os.path.basename, chain)), text=text):
                        rc, out, err = line_run("measure", chain, text, opts=["--scale=%d/%d" % ratio,
                                                                              "--missing-advance=3"])
                        self.assertEqual(rc, 0, err)
                        got = tuple(int(kv.split("=")[1]) for kv in out.decode().split())
                        self.assertEqual(got, svfline.measure(chain, text, missing_advance=3, scale=ratio))
        # MARUS24 at 3/2: 'j' ascent 20 dy 4 -> 30 - 6 above the baseline; cell 24 -> 36 rows.
        rc, out, _ = line_run("measure", [MARUS24], "j", opts=["--scale=3/2"])
        self.assertEqual(out.decode().split()[1:], ["ascent=24", "descent=12"])

    def test_scaled_stream(self):
        for cfg in STREAM_CONFIGS:
            for chain in ([MARUS24], [PAPLG16, PAPLG18]):
                with self.subTest(cfg=cfg, chain="+".join(map(os.path.basename, chain))):
                    self.assertEqual(self.ok(chain, LINE_TEXTS[0], 2, 70, SCALE_W, SCALE_H, (5, 4), opts=[cfg]),
                                     self.want(chain, LINE_TEXTS[0], 2, 70, SCALE_W, SCALE_H, (5, 4)))

    def test_stream_compose_scaled(self):
        """A streamed face without a block cache composes into the scratch's first two cells (the piece read into
        [cell, 2 * cell)), the scaled cell after them: at ratios that are not whole multiples the line is svfline's,
        with exactly svf_chain_scratch_bytes of scratch (ASan: nothing written past it)."""
        for ratio in ((3, 2), (5, 4), (2, 3)):
            for chain in ([PAPLG18], [PAPLG16, PAPLG18], [jamo16()]):
                with self.subTest(ratio=ratio, chain="+".join(map(os.path.basename, chain))):
                    for text in (LINE_TEXTS[0], LINE_TEXTS[2]):
                        out = self.ok(chain, text, 2, 70, SCALE_W, SCALE_H, ratio, opts=["--stream", "--scratch-delta=0"])
                        self.assertEqual(out, self.want(chain, text, 2, 70, SCALE_W, SCALE_H, ratio))
                        self.assertTrue(any(out))

    def test_scratch_too_small(self):
        """Scaled: 2 * svf_cell_bytes + the scaled GRAY8 cell, the most of any face of the chain; one byte less is
        SVF_E_NOMEM (nothing drawn)."""
        for ratio in ((2, 1), (3, 2), (1, 2)):
            for opts, chain in (((), [PAPLG16, PAPLG18]), (("--stream",), [MARUS24])):
                with self.subTest(ratio=ratio, opts=opts):
                    num, den = ratio
                    need = max(2 * svfline.Face.load(p).pitch * svfline.Face.load(p).cell_h +
                               -(-svfline.Face.load(p).cell_w * num // den) * -(-svfline.Face.load(p).cell_h * num // den)
                               for p in chain)
                    rc, out, err = self.run_line(chain, "A가", 2, 70, SCALE_W, SCALE_H, ratio,
                                                 opts=list(opts) + ["--scratch-delta=-1", "--print-scratch"])
                    self.assertEqual(rc, 2)
                    self.assertIn("SVF_E_NOMEM", err)
                    self.assertIn("svfdump: scratch=%d" % need, err)
                    self.assertFalse(any(out), "drawn with too little scratch")
                    rc, out, err = self.run_line(chain, "A가", 2, 70, SCALE_W, SCALE_H, ratio,
                                                 opts=list(opts) + ["--scratch-delta=0"])
                    self.assertEqual(rc, 0, err)
                    self.assertTrue(any(out))

    def test_bad_ratio(self):
        for ratio in ((0, 1), (1, 0), (17, 1), (1, 17), (255, 255)):
            with self.subTest(ratio=ratio):
                rc, out, err = self.run_line([MARUS24], "Score", 2, 28, 100, 40, ratio)
                self.assertEqual(rc, 2)
                self.assertIn("SVF_E_ARG", err)
                self.assertFalse(any(out))
                rc, _, err = line_run("measure", [MARUS24], "Score", opts=["--scale=%d/%d" % ratio])
                self.assertEqual(rc, 2)
                self.assertIn("SVF_E_ARG", err)

    def test_no_scale_build(self):
        """-DSVF_NO_SCALE: svf_draw.o refers to nothing of svf_scale.o (which defines nothing), a ratio other than 1
        is SVF_E_ARG, and n/n draws the 1/1 line."""
        b = build_noscale()
        nm = os.environ.get("NM", "nm")
        undef = subprocess.run([nm, "-u", os.path.join(b["noscale-obj"], "svf_draw.o")], capture_output=True,
                               text=True, check=True).stdout
        self.assertNotIn("svf__scale", undef)
        defined = subprocess.run([nm, "--defined-only", os.path.join(b["noscale-obj"], "svf_scale.o")],
                                 capture_output=True, text=True, check=True).stdout
        self.assertNotIn(" T ", defined)
        rc, out, err = self.run_line([MARUS24], "Score", 2, 28, 100, 40, (2, 1), exe="svfdump-noscale")
        self.assertEqual(rc, 2)
        self.assertIn("SVF_E_ARG", err)
        for ratio in ((0, 0), (3, 3)):
            with self.subTest(ratio=ratio):
                rc, out, err = self.run_line([MARUS24], "Score", 2, 28, 100, 40, ratio, exe="svfdump-noscale")
                self.assertEqual(rc, 0, err)
                self.assertEqual(out, bytes(svfline.layout([MARUS24], "Score", 2, 28, 100, 40)))
        # The default build does scale.
        undef = subprocess.run([nm, "-u", os.path.join(b["dir"], "obj", "svf_draw.o")], capture_output=True,
                               text=True, check=True).stdout
        self.assertIn("svf__scale", undef)


CACHE_SLOTS = (0, 1, 7, 64)
REPEATS = "가나가다가 뷁뷁 ㄱㄱ 가"      # syllables and compat jamo drawn more than once


def cache_bytes(chain, slots):
    """svf_chain_cache's buffer for @p slots slots: 8 + the largest cell of the chain each."""
    return slots * (8 + max(svfline.Face.load(p).pitch * svfline.Face.load(p).cell_h for p in chain))


def line_reads(err):
    """The read callback calls of the faces' svf_stream_reads summed after drawing ("svfdump: line reads=N")."""
    for line in err.splitlines():
        if line.startswith("svfdump: line reads="):
            return int(line.split("=")[1])
    raise AssertionError("no line reads in: " + err)


class TestCache(unittest.TestCase):
    """svf_chain_cache: the composed-syllable cache changes no pixel (every target, scaled, streamed) and saves
    composing (and a streamed face's reads); a failed read is not cached."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.tmp = tempfile.mkdtemp(prefix="svf-cache-")
        cls.marks = os.path.join(cls.tmp, "marks.svf")
        r = subprocess.run([sys.executable, SYNTH, "--marks", cls.marks], capture_output=True, text=True)
        if r.returncode != 0:
            raise AssertionError("svf_synth --marks: " + r.stderr)
        cls.chains = ([PAPLG16, PAPLG18], [MARUS24], [jamo16()], [cls.marks, PAPLG18])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_line(self, chain, text, x, y, w, h, slots, opts=()):
        rc, out, err = line_run("line", chain, text, w, h, x, y,
                                opts=["--syllable-cache=%d" % cache_bytes(chain, slots)] + list(opts))
        self.assertNotIn("Sanitizer", err)
        self.assertNotIn("runtime error", err)
        self.assertNotIn("guard bytes changed", err)
        return rc, out, err

    def test_cache_transparent(self):
        """The Task 4 lines (GRAY8) and the Task 5 targets drawn with caches of 0, 1, 7 and 64 slots: the same bytes
        as svfline's, so as each other's."""
        n = 0
        for chain in self.chains:
            for text in LINE_TEXTS + (REPEATS,):
                for x, y in LINE_PLACES:
                    want = bytes(svfline.layout(chain, text, x, y, LINE_W, LINE_H))
                    for slots in CACHE_SLOTS:
                        with self.subTest(chain="+".join(map(os.path.basename, chain)), text=text, x=x, y=y,
                                          slots=slots):
                            rc, out, err = self.run_line(chain, text, x, y, LINE_W, LINE_H, slots)
                            self.assertEqual(rc, 0, err)
                            self.assertEqual(out, want)
                            n += 1
        w, h = 100, 37
        for kind, kt in kind_runs(SWEEP_KINDS):
            for chain in self.chains:
                for text in (LINE_TEXTS[0], LINE_TEXTS[2], REPEATS):
                    places = svfline.placements(svfline.load_chain(chain), text, -3, 30)
                    ramp = dict(index_base=kt["index_base"], index_levels=kt["index_levels"]) if kind == "indexed8" else {}
                    gbits = dict(gray_bits=kt["gray_bits"], lsb_first=kt["lsb_first"]) if kind == "gray" else {}
                    c888 = dict(fg888=0x6C7F20E0, bg888=0x00108030) if kind in ("xrgb8888", "rgb888") else {}
                    tbuf = bytearray([kt["fill"]]) * (svfline.target_rows(kind, h) * w) if kind == "indexed8" else None
                    tgt = svfline.draw_target(places, svfline.Target(kind, w, h, buf=tbuf, fg565=0x8410, bg565=0x1F,
                                                                     **ramp, **c888, **gbits))
                    want = tgt.plots if kind == "cb" else bytes(tgt.buf)
                    for slots in CACHE_SLOTS:
                        with self.subTest(kind=kind, kt=kt, chain="+".join(map(os.path.basename, chain)), text=text,
                                          slots=slots):
                            rc, out, err = self.run_line(chain, text, -3, 30, w, h, slots,
                                                         opts=["--target=" + kind, "--fg=%d" % 0x8410,
                                                               "--bg=%d" % 0x1F] +
                                                              (["--fg888=%d" % c888["fg888"],
                                                                "--bg888=%d" % c888["bg888"]] if c888 else []) +
                                                              (["--index-base=%d" % kt["index_base"],
                                                                "--index-levels=%d" % kt["index_levels"],
                                                                "--fill=%d" % kt["fill"]] if kind == "indexed8" else []) +
                                                              (["--gray-bits=%d" % kt["gray_bits"]] +
                                                               (["--lsb-first"] if kt["lsb_first"] else [])
                                                               if kind == "gray" else []))
                            self.assertEqual(rc, 0, err)
                            if kind == "cb":
                                out = [tuple(int(v) for v in ln.split()) for ln in out.decode().splitlines()]
                            self.assertEqual(out, want)
                            n += 1
        print(f"\n  test_cache_transparent: {n} lines match svfline", file=sys.stderr)

    def test_cache_scaled(self):
        """The cache holds the stored (unscaled) cell: scaled lines are unchanged by it."""
        for ratio in ((3, 2), (2, 1), (1, 2)):
            for chain in ([PAPLG16, PAPLG18], [jamo16()]):
                want = bytes(svfline.layout(chain, REPEATS, 2, 70, SCALE_W, SCALE_H, scale=ratio))
                for slots in CACHE_SLOTS:
                    with self.subTest(ratio=ratio, chain="+".join(map(os.path.basename, chain)), slots=slots):
                        rc, out, err = self.run_line(chain, REPEATS, 2, 70, SCALE_W, SCALE_H, slots,
                                                     opts=["--scale=%d/%d" % ratio])
                        self.assertEqual(rc, 0, err)
                        self.assertEqual(out, want)

    def test_cache_stream(self):
        """Streamed faces draw the same line with the cache; without a block cache svf_stream_reads drops when it is
        on (every hit saves its pieces' reads)."""
        for cfg in STREAM_CONFIGS:
            for chain in ([PAPLG18], [PAPLG16, PAPLG18]):
                want = bytes(svfline.layout(chain, REPEATS, 2, 28, LINE_W, LINE_H))
                reads = {}
                for slots in CACHE_SLOTS:
                    with self.subTest(cfg=cfg, chain="+".join(map(os.path.basename, chain)), slots=slots):
                        rc, out, err = self.run_line(chain, REPEATS, 2, 28, LINE_W, LINE_H, slots,
                                                     opts=[cfg, "--print-reads"])
                        self.assertEqual(rc, 0, err)
                        self.assertEqual(out, want)
                        reads[slots] = line_reads(err)
                if cfg == "--stream":   # one read a piece: every hit saves the syllable's pieces
                    self.assertLess(reads[1], reads[0])
                    self.assertLess(reads[7], reads[1])
                    self.assertEqual(reads[64], reads[7])
                # With a block cache the reads are whole blocks: skipping a syllable's piece lookups changes which
                # block is least recently used, so the count may move either way (PAPLG18 at 4:512: 12 -> 13).

    def test_failed_read_not_cached(self):
        """A syllable whose piece read fails draws nothing (SVF_E_IO) and is not cached: its next occurrence is read
        again and drawn."""
        chain, text = [PAPLG18], "가가"
        _, _, err = line_run("line", chain, "", LINE_W, LINE_H, 2, 28, opts=["--stream"])
        opened = open_reads(err)
        places = svfline.placements(svfline.load_chain(chain), text, 2, 28)
        want = bytes(svfline.draw_gray8(places[1:], LINE_W, LINE_H))
        for slots in CACHE_SLOTS:
            with self.subTest(slots=slots):
                rc, out, err = self.run_line(chain, text, 2, 28, LINE_W, LINE_H, slots,
                                             opts=["--stream", "--fail-read-after=%d" % opened])
                self.assertEqual(rc, 2)
                self.assertIn("SVF_E_IO", err)
                self.assertEqual(out, want)
                self.assertTrue(any(out))

    def test_cache_arguments(self):
        """A buffer below one slot is SVF_E_NOMEM; 0 bytes is no cache; one slot exactly is a cache."""
        chain = [PAPLG16, PAPLG18]
        one = cache_bytes(chain, 1)
        rc, out, err = line_run("line", chain, "가", LINE_W, LINE_H, 2, 28, opts=["--syllable-cache=%d" % (one - 1)])
        self.assertEqual(rc, 2)
        self.assertIn("SVF_E_NOMEM", err)
        for n in (0, one, one + 1):
            rc, out, err = line_run("line", chain, "가", LINE_W, LINE_H, 2, 28, opts=["--syllable-cache=%d" % n])
            self.assertEqual(rc, 0, err)
            self.assertEqual(out, bytes(svfline.layout(chain, "가", 2, 28, LINE_W, LINE_H)))


class TestCheckScript(unittest.TestCase):
    """c/check.sh's no-malloc scan (without --asan: the sanitizer run is this file): it fails on an object that calls
    the allocator, when nm fails, and with no object; it passes the library's objects of both builds."""

    def check(self, *objs, nm=None):
        env = dict(os.environ)
        if nm:
            env["NM"] = nm
        r = subprocess.run(["sh", os.path.join(C_DIR, "check.sh")] + list(objs), capture_output=True, text=True,
                           env=env)
        return r.returncode, r.stdout + r.stderr

    def test_check_script(self):
        b = build_noscale()
        objs = sorted(glob.glob(os.path.join(b["dir"], "obj", "*.o")) +
                      glob.glob(os.path.join(b["noscale-obj"], "*.o")))
        self.assertTrue(objs)
        rc, out = self.check(*objs)
        self.assertEqual(rc, 0, out)
        self.assertIn("no-malloc: OK (%d objects)" % len(objs), out)
        cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("gcc")
        with tempfile.TemporaryDirectory(prefix="svf-check-") as tmp:
            src, obj = os.path.join(tmp, "m.c"), os.path.join(tmp, "m.o")
            with open(src, "w") as fh:
                fh.write("#include <stdlib.h>\nvoid *m(void) { return malloc(4); }\n")
            subprocess.run([cc, "-c", src, "-o", obj], check=True)
            rc, out = self.check(objs[0], obj)
            self.assertEqual(rc, 1, out)
            self.assertIn("no-malloc: FAIL: %s uses malloc" % obj, out)
        rc, out = self.check(*objs, nm="false")
        self.assertEqual(rc, 1, out)
        self.assertIn("failed", out)
        self.assertNotIn("no-malloc: OK", out)
        rc, out = self.check(os.path.join(b["dir"], "no-such.o"))
        self.assertEqual(rc, 1, out)
        rc, out = self.check()
        self.assertEqual(rc, 1, out)
        self.assertIn("no objects given", out)

    def test_targets_jobs(self):
        """CHECK_LIST_ONLY=1: targets_ok writes its job list and exits 0 before compiling anything (and before the
        Python suite --asan would start): 2066 job lines, nothing else."""
        b = build_noscale()
        objs = sorted(glob.glob(os.path.join(b["dir"], "obj", "*.o")))
        env = dict(os.environ, CHECK_LIST_ONLY="1")
        r = subprocess.run(["sh", os.path.join(C_DIR, "check.sh"), "--asan"] + objs, capture_output=True, text=True,
                           env=env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        jobs = r.stdout.splitlines()
        self.assertEqual(len(jobs), 2066, r.stdout[:200])
        for ln in jobs:
            self.assertRegex(ln, r"^0x[0-9A-F]{3}(:-D[A-Z_]+(=[01])?)?$")
        self.assertEqual(len(set(jobs)), len(jobs))
        self.assertIn("0x1E8:-DSVF_WORD_STORE=1", jobs)
        self.assertIn("0x000", jobs)
        self.assertIn("0x1FF:-DSVF_NO_SCALE", jobs)
        self.assertIn("0x3FF:-DSVF_NO_SCALE", jobs)
        self.assertIn("0x200:-DSVF_WORD_STORE=0", jobs)
        self.assertIn("0x3FF:-DSVF_WORD_STORE=1", jobs)
        self.assertEqual(r.stderr, "")

    def test_list_only_needs_exactly_1(self):
        """CHECK_LIST_ONLY=0 (or empty) runs the gate: with CC=false the jobs fail, the list is not printed."""
        b = build_noscale()
        objs = sorted(glob.glob(os.path.join(b["dir"], "obj", "*.o")))
        for val in ("0", ""):
            with self.subTest(value=val), tempfile.TemporaryDirectory(prefix="svf-check-") as tmp:
                env = dict(os.environ, CHECK_LIST_ONLY=val, CC="false", PYTHON="true", OUT=tmp)
                r = subprocess.run(["sh", os.path.join(C_DIR, "check.sh"), "--asan"] + objs, capture_output=True,
                                   text=True, env=env, timeout=120)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("targets: FAIL: false", r.stdout)

    def test_jobs_file_in_out(self):
        """The gate writes its job list to $OUT/jobs and keeps it, also after a failed run."""
        b = build_noscale()
        objs = sorted(glob.glob(os.path.join(b["dir"], "obj", "*.o")))
        with tempfile.TemporaryDirectory(prefix="svf-check-") as tmp:
            out = os.path.join(tmp, "sub")
            env = dict(os.environ, CC="false", PYTHON="true", OUT=out)
            env.pop("CHECK_LIST_ONLY", None)
            r = subprocess.run(["sh", os.path.join(C_DIR, "check.sh"), "--asan"] + objs, capture_output=True,
                               text=True, env=env, timeout=120)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            with open(os.path.join(out, "jobs")) as fh:
                self.assertEqual(len(fh.read().splitlines()), 2066)
            self.assertEqual(os.listdir(out), ["jobs"])


BENCH = os.path.join(C_DIR, "bench")
# (kind, SVF_TARGETS); MONO_PAGE also with every kind compiled (the default): set B belongs to GRAY8 and RGB565 only;
# GRAY (SVF_T_GRAY at its default 8 bits, alone) takes GRAY8's sums
BENCH_KINDS = (("MONO_PAGE", "0x02"), ("GRAY8", "0x01"), ("RGB565", "0x08"), ("MONO_PAGE", "0x1F"),
              ("GRAY", "0x200"))


def bench_sums():
    """{kind: 'case:sum ...'} printed by c/bench/sums.py."""
    r = subprocess.run([sys.executable, "-I", os.path.join(BENCH, "sums.py")], capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError("sums.py failed:\n" + r.stderr)
    out = {}
    for line in r.stdout.splitlines():
        m = re.fullmatch(r'SUMS_(\w+)="(.*)"', line)
        out[m.group(1)] = m.group(2)
    return out


class TestBenchSums(unittest.TestCase):
    """c/bench/bench.c on the host agrees with sums.py (tools/svfline.py) and with the constants sums.inc.sh holds (run-pico.sh and run-esp32.sh source it);
    report.awk refuses a run whose case set or instruction counts are wrong."""

    def test_host_matches_sums_inc(self):
        cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("gcc")
        if not cc:
            raise unittest.SkipTest("no C compiler")
        want = bench_sums()
        with open(os.path.join(BENCH, "sums.inc.sh")) as fh:
            embedded = dict(re.findall(r'^SUMS_(\w+)="(.*)"$', fh.read(), re.M))
        self.assertEqual(embedded, want, "the SUMS_<kind> constants of sums.inc.sh differ from sums.py")
        with tempfile.TemporaryDirectory() as tmp:
            srcs = []
            for name, face in (("face", "dos/NEODG16G.SVF"), ("face16", "dos/PAPLG16.SVF"),
                               ("face18", "dos/PAPLG18.SVF")):
                out = os.path.join(tmp, name + ".c")
                subprocess.run([sys.executable, "-I", os.path.join(BENCH, "mkface.py"),
                                os.path.join(SVF_DIR, face), out] + (["--name", "bench_" + name] if name != "face"
                                                                      else []), check=True)
                srcs.append(out)
            for kind, bit in BENCH_KINDS:
                exe = os.path.join(tmp, "bench-" + kind + bit)
                r = subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-O2", "-DBENCH_HOST",
                                    "-DBENCH_MCU", "-DBENCH_KIND=SVF_T_" + kind, "-DSVF_TARGETS=" + bit,
                                    "-DSVF_NO_SCALE", "-I", os.path.join(C_DIR, "include"),
                                    os.path.join(BENCH, "bench.c")] + sorted(glob.glob(os.path.join(C_DIR, "src",
                                                                                                    "*.c"))) + srcs +
                                   ["-o", exe], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                r = subprocess.run([exe], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout)
                got = " ".join(m[0] + ":" + m[1] for m in re.findall(r"case=(\w+) .* sum=([0-9a-f]{8})", r.stdout))
                self.assertEqual(got, want["GRAY8" if kind == "GRAY" else kind], kind + " " + bit)


    def test_layout_probe_sums(self):
        """sums.py and sums.inc.sh agree on the layout_probe sums: SVF_E_RANGE three times for a build that reads every
        layout, SVF_E_LAYOUT for dos and simd16 on a strict build; every per-kind sum ends in the default one."""
        want = bench_sums()
        with open(os.path.join(BENCH, "sums.inc.sh")) as fh:
            embedded = dict(re.findall(r'^SUMS_(\w+)="(.*)"$', fh.read(), re.M))
        self.assertEqual(want["LAYOUT_DEFAULT"], "layout_probe:00040404")
        self.assertEqual(want["LAYOUT_STRICT"], "layout_probe:00080804")
        for k in ("LAYOUT_DEFAULT", "LAYOUT_STRICT"):
            self.assertEqual(embedded[k], want[k], k)
        for k in ("MONO_PAGE", "GRAY8", "RGB565", "LINE40"):
            self.assertTrue(want[k].endswith(" " + want["LAYOUT_DEFAULT"]), k)
        with open(os.path.join(BENCH, "run-avr.sh")) as fh:
            avr = fh.read()
        self.assertIn("SUMS_LAYOUT_STRICT", avr)
        self.assertIn("-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT", avr)
        self.assertIn("-DSVF_NO_STREAM", avr)

    def test_bench_host_layout_probe(self):
        """The host bench prints layout_probe:00040404 built default and layout_probe:00080804 built with
        -DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT (and -DSVF_NO_STREAM would link: the probe opens mapped only)."""
        cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("gcc")
        if not cc:
            raise unittest.SkipTest("no C compiler")
        with tempfile.TemporaryDirectory() as tmp:
            srcs = []
            for name, face in (("face", "dos/NEODG16G.SVF"), ("face16", "dos/PAPLG16.SVF"),
                               ("face18", "dos/PAPLG18.SVF")):
                out = os.path.join(tmp, name + ".c")
                subprocess.run([sys.executable, "-I", os.path.join(BENCH, "mkface.py"),
                                os.path.join(SVF_DIR, face), out, "--profile", "mcu-strict"] +
                               (["--name", "bench_" + name] if name != "face" else []), check=True)
                srcs.append(out)
            for flags, sums, tag in (([], "layout_probe:00040404", "default"),
                                     (["-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT"], "layout_probe:00080804", "strict")):
                exe = os.path.join(tmp, "bench-" + tag)
                r = subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-O1", "-DBENCH_HOST", "-DBENCH_MCU",
                                    "-DSVF_NO_SCALE", "-DSVF_TARGETS=0x02"] + flags +
                                   ["-I", os.path.join(C_DIR, "include"), os.path.join(BENCH, "bench.c")] +
                                   sorted(glob.glob(os.path.join(C_DIR, "src", "*.c"))) + srcs + ["-o", exe],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                r = subprocess.run([exe], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout)
                got = " ".join(m[0] + ":" + m[1] for m in re.findall(r"case=(layout_probe) .* sum=([0-9a-f]{8})",
                                                                       r.stdout))
                self.assertEqual(got, sums, tag)
            # a mapped-only build links without the stream reader
            r = subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-O1", "-DBENCH_HOST", "-DBENCH_MCU",
                                "-DSVF_NO_SCALE", "-DSVF_TARGETS=0x02", "-DSVF_NO_STREAM",
                                "-DSVF_LAYOUTS=SVF_LAYOUT_MCU_STRICT", "-I", os.path.join(C_DIR, "include"),
                                os.path.join(BENCH, "bench.c")] + sorted(glob.glob(os.path.join(C_DIR, "src", "*.c"))) +
                               srcs + ["-o", os.path.join(tmp, "bench-nostream")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = subprocess.run([os.path.join(tmp, "bench-nostream")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("layout_probe", r.stdout)

    def test_host_line_build_matches_sums_line40(self):
        """The host line build (no BENCH_MCU) prints the SUMS_LINE40 checksums: the 1/1 line and the 3/2 line, both
        computed by svfline (sums.py)."""
        if not shutil.which("cc"):                                  # run-host.sh calls cc
            raise unittest.SkipTest("no cc")
        want = bench_sums()["LINE40"]
        with tempfile.TemporaryDirectory() as tmp:
            r = run_in_session(["sh", os.path.join(BENCH, "run-host.sh"), os.path.join(tmp, "line")], dict(os.environ),
                               300)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = dict(re.findall(r"case=(line40_\w+|layout_probe) .* sum=([0-9a-f]{8})", r.stdout))
        for pair in want.split():
            name, s = pair.split(":")
            self.assertEqual(got.get(name), s, name)

    def test_pico_run_counts_steps_between_the_markers(self):
        opt = os.environ.get("OPT", os.path.expanduser("~/opt"))
        gcc = os.path.join(opt, "arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-gcc")
        node = os.environ.get("NODE", os.path.join(opt, "node-v24.13.0-linux-x64/bin/node"))
        rp = os.path.join(opt, "rp2040js-1.4.0")
        if not all(os.path.exists(x) for x in (gcc, node, os.path.join(rp, "node_modules", "rp2040js"))):
            raise unittest.SkipTest("no arm-none-eabi-gcc / node / rp2040js under OPT")
        # Two intervals of 7 and 5 nops; the BKPTs themselves are not counted, the cycles of both intervals add up.
        asm = (".syntax unified\n.thumb\n.global main\n.thumb_func\nmain:\n"
               "bkpt #1\n" + "nop\n" * 7 + "bkpt #2\nnop\nnop\nbkpt #1\n" + "nop\n" * 5 + "bkpt #2\n"
               "ldr r0, =name\nmovs r1, #4\nmovs r2, #0\nbkpt #3\nmovs r0, #0\nbkpt #4\n.ltorg\n"
               "name: .asciz \"x\"\n")
        with tempfile.TemporaryDirectory() as tmp:
            src, elf, nm = (os.path.join(tmp, n) for n in ("t.S", "t.elf", "nm.txt"))
            with open(src, "w") as fh:
                fh.write(asm)
            subprocess.run([gcc, "-mcpu=cortex-m0plus", "-mthumb", "-nostartfiles", "-Wl,-e,main",
                            "-Wl,-Ttext=0x10000000", "-Wl,-Tdata=0x20000000", src, "-o", elf], check=True)
            with open(nm, "w") as fh:
                subprocess.run([gcc[:-3] + "nm", "-S", "--size-sort", elf], check=True, stdout=fh)
            for extra in ([], [nm]):
                r = subprocess.run([node, os.path.join(BENCH, "pico-run.mjs"), rp, elf] + extra,
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                m = re.search(r"case=x iters=4 cycles=(\d+) .* insns=(\d+) per_iter_insns=([0-9.]+)", r.stdout)
                self.assertTrue(m, r.stdout)
                self.assertEqual(int(m.group(2)), 12, (extra, r.stdout))
                self.assertEqual(m.group(3), "3.0")
                # One cycle a nop, and the BKPTs are excluded from the cycles as from the insns.
                self.assertEqual(int(m.group(1)), 12, (extra, r.stdout))

    def test_sums_refuses_clipped_text(self):
        spec = importlib.util.spec_from_file_location("bench_sums", os.path.join(BENCH, "sums.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        t = svfline.Target("gray8", mod.BAND_W, mod.BAND_H)
        with self.assertRaises(SystemExit) as cm:
            mod.draw(mod.PAPLG, "가" * 30, 8, 19, t)
        self.assertIn("does not fit", str(cm.exception))

    def test_sums_face_not_jamo_is_a_clear_error(self):
        r = subprocess.run([sys.executable, "-I", os.path.join(BENCH, "sums.py"), "--face",
                            os.path.join(SVF_DIR, "dos", "PAPLG16.SVF")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("not a jamo face", r.stderr)
        self.assertEqual(r.stdout, "")

    def awk(self, run_text, kind="GRAY8"):
        with tempfile.NamedTemporaryFile("w", suffix=".txt") as fh:
            fh.write(run_text)
            fh.flush()
            r = subprocess.run(["awk", "-v", "build=t", "-v", "mhz=125", "-v", "sums=" + bench_sums()[kind],
                                "-v", "exact=1", "-v", "need_insns=1", "-f", os.path.join(BENCH, "report.awk"),
                                fh.name], capture_output=True, text=True)
        return r.returncode

    def run_text(self, kind="GRAY8", drop=None, extra=None, no_insns=None, zero_insns=None):
        lines = []
        for item in bench_sums()[kind].split() + (extra or []):
            name, s = item.split(":")
            if name == drop:
                continue
            ins = "" if name == no_insns else " insns=1000 per_iter_insns=10.0"
            if name == zero_insns:  # per_iter_insns positive but insns 0 (an inconsistent line)
                ins = " insns=0 per_iter_insns=10.0"
            lines.append(f"case={name} iters=100 cycles=2000 per_iter_cycles=20.0{ins} sum={s}")
        return "\n".join(lines) + "\nend=0 total_cycles=1\n"

    def test_esp_sections_compile_and_report_on_host(self):
        """bench.c's BENCH_ESP32C3 / BENCH_ESP32S3 / BENCH_M33 sections with stubbed counters (-DBENCH_ESP_STUB): they
        compile warning-free, print lines report.awk accepts with the expected checksums, the S3 prints its calibration
        lines and check-esp32-cal.sh accepts them, the M33 prints its one calibration line; the M33 line section
        (-DBENCH_M33 without -DBENCH_MCU) builds and calibrates too."""
        cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("gcc")
        if not cc:
            raise unittest.SkipTest("no C compiler")
        want = bench_sums()
        with tempfile.TemporaryDirectory() as tmp:
            srcs = []
            for name, face in (("face", "dos/NEODG16G.SVF"), ("face16", "dos/PAPLG16.SVF"),
                               ("face18", "dos/PAPLG18.SVF")):
                out = os.path.join(tmp, name + ".c")
                subprocess.run([sys.executable, "-I", os.path.join(BENCH, "mkface.py"),
                                os.path.join(SVF_DIR, face), out] + (["--name", "bench_" + name] if name != "face"
                                                                      else []), check=True)
                srcs.append(out)
            for chip, extra in (("ESP32C3", []), ("ESP32S3", ["-DBENCH_ICOUNT_SHIFT=5"]), ("M33", ["-DBENCH_MCU"])):
                for kind, bit in BENCH_KINDS[:3]:
                    exe = os.path.join(tmp, "bench-" + chip + kind)
                    r = subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-O1", "-DBENCH_" + chip,
                                        "-DBENCH_ESP_STUB", "-DBENCH_KIND=SVF_T_" + kind, "-DSVF_TARGETS=" + bit,
                                        "-DSVF_NO_SCALE", "-I", os.path.join(C_DIR, "ports"), "-I",
                                        os.path.join(C_DIR, "include"), os.path.join(BENCH, "bench.c")] +
                                       sorted(glob.glob(os.path.join(C_DIR, "src", "*.c"))) + srcs + extra +
                                       ["-o", exe], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    r = subprocess.run([exe], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, r.stdout)
                    run = os.path.join(tmp, "run.txt")
                    with open(run, "w") as fh:
                        fh.write(r.stdout)
                    a = subprocess.run(["awk", "-v", "build=t", "-v", "mhz=160", "-v", "sums=" + want[kind],
                                        "-v", "exact=1", "-f", os.path.join(BENCH, "report.awk"), run],
                                       capture_output=True, text=True)
                    self.assertEqual(a.returncode, 0, (chip, kind, r.stdout, a.stderr))
                    self.assertEqual(a.stdout.count(" ok |"), len(want[kind].split()), a.stdout)
                    if chip == "M33":
                        cal = re.findall(r"^cal=loop2m ticks=(\d+) insns=(\d+)$", r.stdout, re.M)
                        self.assertEqual(len(cal), 1, r.stdout)
                        self.assertEqual(int(cal[0][1]), int(cal[0][0]) * 50, r.stdout)
                    if chip == "ESP32S3":
                        self.assertEqual(r.stdout.count("cal=loop1m"), 4, r.stdout)
                        c = subprocess.run(["sh", os.path.join(BENCH, "check-esp32-cal.sh"), run, "4"],
                                           capture_output=True, text=True)
                        self.assertEqual(c.returncode, 0, c.stdout + c.stderr)
            # the M33 line section: no -DBENCH_MCU (BENCH_M33 must not imply it), default SVF_TARGETS, scaling in
            exe = os.path.join(tmp, "bench-M33-line")
            r = subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-O1", "-DBENCH_M33", "-DBENCH_ESP_STUB",
                                "-I", os.path.join(C_DIR, "include"), os.path.join(BENCH, "bench.c")] +
                               sorted(glob.glob(os.path.join(C_DIR, "src", "*.c"))) + srcs[1:] + ["-o", exe],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = subprocess.run([exe], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertEqual(len(re.findall(r"^cal=loop2m ticks=(\d+) insns=(\d+)$", r.stdout, re.M)), 1, r.stdout)
            run = os.path.join(tmp, "line.txt")
            with open(run, "w") as fh:
                fh.write(r.stdout)
            a = subprocess.run(["awk", "-v", "build=t", "-v", "mhz=150", "-v", "sums=" + want["LINE40"], "-v", "exact=1",
                                "-f", os.path.join(BENCH, "report.awk"), run], capture_output=True, text=True)
            self.assertEqual(a.returncode, 0, (r.stdout, a.stderr))
            self.assertEqual(a.stdout.count(" ok |"), len(want["LINE40"].split()), a.stdout)

    def cal(self, nops=("cal=nop1000 ccount=1281",), loops=4, loop="cal=loop1m icount=1000001 ccount=1280004",
            extra=()):
        with tempfile.NamedTemporaryFile("w", suffix=".txt") as fh:
            fh.write("\n".join(list(nops) + [loop] * loops + list(extra)) + "\nend=0\n")
            fh.flush()
            r = subprocess.run(["sh", os.path.join(BENCH, "check-esp32-cal.sh"), fh.name, "4"],
                               capture_output=True, text=True)
        return r.returncode

    def test_esp32_calibration_check(self):
        self.assertEqual(self.cal(), 0)
        self.assertEqual(self.cal(nops=("cal=nop1000 ccount=1281", "cal=nop1000 ccount=1281")), 1)  # a duplicate
        self.assertEqual(self.cal(nops=()), 1)  # none
        self.assertEqual(self.cal(nops=("cal=nop1000 ccount=1290",)), 1)  # out of range
        self.assertEqual(self.cal(nops=("cal=nop1000 ccount=1281 x",)), 1)  # not strictly parsed
        self.assertEqual(self.cal(nops=("cal=nop1000 ccount=-1281",)), 1)
        self.assertEqual(self.cal(loops=5), 1)  # one loop too many
        self.assertEqual(self.cal(loops=3), 1)
        # core 1's spinning in the count (the 9234022 build: CCOUNT converted, 2,171,877 for every second loop)
        self.assertEqual(self.cal(loops=3, extra=("cal=loop1m icount=2171877 ccount=2780002",)), 1)
        self.assertEqual(self.cal(loop="cal=loop1m icount=1001001 ccount=1"), 1)
        self.assertEqual(self.cal(extra=("cal=other x=1",), loops=4), 1)

    def test_report_awk_cycle_fields_of_an_esp_format_run(self):
        def awk(line):
            with tempfile.NamedTemporaryFile("w", suffix=".txt") as fh:
                fh.write(line + "\nend=0\n")
                fh.flush()
                return subprocess.run(["awk", "-v", "build=t", "-v", "mhz=160", "-v", "sums=syl_ga:29897c8f",
                                       "-v", "exact=1", "-f", os.path.join(BENCH, "report.awk"), fh.name],
                                      capture_output=True, text=True).returncode
        ok = "case=syl_ga iters=100 cycles=361912 per_iter_cycles=3619.1 sum=29897c8f"
        self.assertEqual(awk(ok), 0)
        self.assertEqual(awk(ok.replace("cycles=361912", "cycles=0").replace("3619.1", "0.0")), 1)
        self.assertEqual(awk(ok.replace("iters=100", "iters=0")), 1)
        self.assertEqual(awk(ok.replace("iters=100", "iters=abc")), 1)
        self.assertEqual(awk(ok.replace("per_iter_cycles=3619.1", "per_iter_cycles=-1")), 1)
        self.assertEqual(awk(ok.replace("3619.1", "3000.0")), 1)  # inconsistent with cycles / iters
        self.assertEqual(awk(ok.replace(" cycles=361912", "")), 1)
        self.assertEqual(awk(ok.replace("per_iter_cycles=3619.1 ", "")), 1)

    def test_run_scripts_leave_no_emulator_when_terminated(self):
        """SIGTERM to run-esp32.sh / run-pico.sh / run-m33.sh while an emulator runs: the emulator is gone afterwards
        (run-m33.sh only where the pinned qemu-arm tree is installed; the others are not skipped for want of it)."""
        import signal
        import time
        opt = os.environ.get("OPT", os.path.expanduser("~/opt"))
        for script, tool, var in (("run-esp32.sh", "riscv32-esp-elf-esp-16.1.0_20260609/bin/riscv32-esp-elf-gcc",
                                   "QEMU_RV"),
                                  ("run-pico.sh", "arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-gcc", "NODE")):
            if not os.path.exists(os.path.join(opt, tool)):
                raise unittest.SkipTest("no " + tool + " under OPT")
        entries = [("run-esp32.sh", "QEMU_RV"), ("run-pico.sh", "NODE")]
        # run-m33.sh verifies the qemu-arm tree even with QEMU_ARM overridden: its entry runs only if that passes
        v = subprocess.run(["sh", os.path.join(BENCH, "install-emulators.sh"), "--verify", "qemu-arm"],
                           env=dict(os.environ, OPT=opt), capture_output=True, text=True)
        if v.returncode == 0 and "qemu-arm: OK" in v.stdout:
            entries.append(("run-m33.sh", "QEMU_ARM"))
        if self.rp2350_installed(opt):
            # run-rp2350.sh verifies rp2350js, pico-rv and pico-sdk even with NODE overridden; the fake node starts after
            # its two CMake builds (about 10 s)
            entries.append(("run-rp2350.sh", "NODE"))
        with tempfile.TemporaryDirectory() as tmp:
            for script, var in entries:
                fake = os.path.join(tmp, "fake-emulator-" + script + ".sh")
                with open(fake, "w") as fh:
                    fh.write("#!/bin/sh\nsleep 300 &\necho \"$$ $!\" > '" + fake + ".pids'\nwait\n")
                os.chmod(fake, 0o755)
                env = dict(os.environ, **{var: fake})
                p = subprocess.Popen(["sh", os.path.join(BENCH, script), os.path.join(tmp, "out-" + script)],
                                     env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
                try:
                    seen = False
                    for _ in range(300):  # up to 60 s
                        if os.path.exists(fake + ".pids"):
                            seen = True
                            break
                        time.sleep(0.2)
                    self.assertTrue(seen, script + ": the fake emulator never started")
                    os.kill(p.pid, signal.SIGTERM)  # to the script only, not its group
                    p.wait(timeout=30)
                    time.sleep(0.5)
                    self.assertNotEqual(subprocess.run(["pgrep", "-f", fake], capture_output=True).returncode, 0,
                                        script + ": the emulator survived SIGTERM")
                    with open(fake + ".pids") as fh:
                        for pid in fh.read().split():  # the emulator and its child
                            with self.assertRaises(ProcessLookupError, msg=script + ": pid %s lives" % pid):
                                os.kill(int(pid), 0)
                finally:
                    if p.poll() is None:
                        os.killpg(p.pid, signal.SIGKILL)
                    subprocess.run(["pkill", "-f", fake])

    @staticmethod
    def rp2350_installed(opt):
        """True when the pinned rp2350js, riscv32-pico-elf and pico-sdk trees verify under OPT and cmake is on PATH
        (what run-rp2350.sh needs): the install-dependent tests run only then."""
        if shutil.which("cmake") is None:
            return False
        env = dict(os.environ, OPT=opt)
        e = subprocess.run(["sh", os.path.join(BENCH, "install-emulators.sh"), "--verify", "rp2350js"], env=env,
                           capture_output=True, text=True)
        t = subprocess.run(["sh", os.path.join(ROOT, "c", "cross", "install-toolchains.sh"), "--verify", "arm",
                            "pico-rv", "pico-sdk"], env=env, capture_output=True, text=True)
        return (e.returncode == 0 and "rp2350js: OK" in e.stdout and t.returncode == 0 and "pico-rv: OK" in t.stdout
                and "pico-sdk: OK" in t.stdout and "arm: OK" in t.stdout)

    def test_rp2350_section_compiles(self):
        """bench.c's BENCH_RP2350 section (marker functions, calibration) compiles under -std=c99 -Wall -Wextra -Werror
        with each RP2350 compiler present, as the MCU build (-DBENCH_MCU) and as the line section; no SDK header is needed."""
        opt = os.environ.get("OPT", os.path.expanduser("~/opt"))
        compilers = (("pico-riscv-toolchain-16-v2.3.1-0/bin/riscv32-pico-elf-gcc", ["-mcpu=hazard3-rp2350", "-mstrict-align"]),
                     ("arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-gcc", ["-mcpu=cortex-m33", "-mthumb"]))
        ran = 0
        for tool, flags in compilers:
            cc = os.path.join(opt, tool)
            if not os.path.exists(cc):
                continue
            for extra in (["-DBENCH_MCU", "-DSVF_NO_SCALE", "-DSVF_TARGETS=0x01", "-DBENCH_KIND=SVF_T_GRAY8"], []):
                r = subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-fsyntax-only", "-DBENCH_RP2350",
                                    *flags, *extra, "-I", os.path.join(ROOT, "c", "include"),
                                    os.path.join(BENCH, "bench.c")], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, tool + " " + " ".join(extra) + r.stdout + r.stderr)
                self.assertEqual(r.stdout + r.stderr, "", tool)
                ran += 1
        if not ran:
            raise unittest.SkipTest("no RP2350 compiler under OPT")

    def test_rp2350_run_reads_the_marks(self):
        """run-rp2350.sh for the Hazard3 core: 60 rows ok, the calibration lines present, a second run of one image
        byte-identical, and a missing marker symbol refused."""
        opt = os.environ.get("OPT", os.path.expanduser("~/opt"))
        if not self.rp2350_installed(opt):
            raise unittest.SkipTest("rp2350js, pico-rv, pico-sdk or cmake is not installed or not verified under OPT")
        node = os.path.join(opt, "node-v24.13.0-linux-x64/bin/node")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "o")
            r = subprocess.run(["sh", os.path.join(BENCH, "run-rp2350.sh"), out], env=dict(os.environ, CORES="riscv"),
                               capture_output=True, text=True, timeout=900)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            rows = [l for l in r.stdout.splitlines() if l.endswith(" ok |")]
            self.assertEqual(len(rows), 68, r.stdout)  # (6 + 10 + 10 + 8) cases (layout_probe each) x 2 optimisations
            self.assertNotIn("**expected", r.stdout)
            runs = sorted(glob.glob(os.path.join(out, "run-riscv-*.txt")))
            self.assertEqual(len(runs), 8)
            for f in runs:
                with open(f) as fh:
                    lines = fh.read().splitlines()
                self.assertEqual(len([l for l in lines if l.startswith("cal=empty ")]), 1, f)
                self.assertEqual(len([l for l in lines if l.startswith("cal=loop1m ")]), 1, f)
            elf = os.path.join(out, "build-riscv", "bench-Os-MONO_PAGE.elf")
            nm = os.path.join(out, "nm-riscv-Os-MONO_PAGE.txt")
            js = os.path.join(opt, "rp2350js-af0114c")
            again = subprocess.run([node, os.path.join(BENCH, "rp2350-run.mjs"), js, "riscv", elf, nm],
                                   capture_output=True, text=True)
            self.assertEqual(again.returncode, 0, again.stderr)
            with open(os.path.join(out, "run-riscv-Os-MONO_PAGE.txt")) as fh:
                self.assertEqual(again.stdout, fh.read())
            nostart = os.path.join(tmp, "nm-nostart.txt")
            with open(nm) as fh, open(nostart, "w") as oh:
                oh.writelines(l for l in fh if not l.rstrip().endswith(" bench_mark_start"))
            bad = subprocess.run([node, os.path.join(BENCH, "rp2350-run.mjs"), js, "riscv", elf, nostart],
                                 capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2, bad.stdout + bad.stderr)
            self.assertIn("no bench_mark_start", bad.stdout + bad.stderr)

    @staticmethod
    def _patch_elf(src, dst, nm, sym, data=None, find=None, repl=None):
        """A copy of the ELF src at dst: the bytes `data` written at the file offset of symbol `sym` (from the nm file),
        or the first `find` replaced by `repl` (same length)."""
        with open(src, "rb") as fh:
            raw = bytearray(fh.read())
        if find is not None:
            i = raw.index(find)
            raw[i:i + len(find)] = repl
        else:
            addr = None
            with open(nm) as nh:
                for line in nh:
                    f = line.split()
                    if len(f) == 3 and f[2] == sym:
                        addr = int(f[0], 16) & ~1
            phoff, phentsize, phnum = struct.unpack_from("<I", raw, 28)[0], struct.unpack_from("<H", raw, 42)[0], struct.unpack_from("<H", raw, 44)[0]
            for k in range(phnum):
                ph = phoff + k * phentsize
                typ, off, _, paddr, filesz = struct.unpack_from("<IIIII", raw, ph)
                if typ == 1 and filesz and paddr <= addr < paddr + filesz:
                    raw[off + addr - paddr:off + addr - paddr + len(data)] = data
                    break
            else:
                raise AssertionError("symbol not in a segment")
        with open(dst, "wb") as oh:
            oh.write(raw)

    def test_rp2350_run_arm_images(self):
        """run-rp2350.sh for the Cortex-M33 core end to end (60 rows ok, calibration lines), then the runner on patched
        copies of one image: a udf or a bkpt inside a timed interval, a truncated ELF and a bad case name all fail."""
        opt = os.environ.get("OPT", os.path.expanduser("~/opt"))
        if not self.rp2350_installed(opt):
            raise unittest.SkipTest("rp2350js, pico-rv, pico-sdk or cmake is not installed or not verified under OPT")
        node = os.path.join(opt, "node-v24.13.0-linux-x64/bin/node")
        js = os.path.join(opt, "rp2350js-af0114c")
        runner = os.path.join(BENCH, "rp2350-run.mjs")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "o")
            r = subprocess.run(["sh", os.path.join(BENCH, "run-rp2350.sh"), out], env=dict(os.environ, CORES="arm"),
                               capture_output=True, text=True, timeout=900)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            rows = [l for l in r.stdout.splitlines() if l.endswith(" ok |")]
            self.assertEqual(len(rows), 68, r.stdout)
            self.assertNotIn("**expected", r.stdout)
            runs = sorted(glob.glob(os.path.join(out, "run-arm-*.txt")))
            self.assertEqual(len(runs), 8)
            for f in runs:
                with open(f) as fh:
                    lines = fh.read().splitlines()
                self.assertEqual(len([l for l in lines if l.startswith("cal=empty ")]), 1, f)
                self.assertEqual(len([l for l in lines if l.startswith("cal=loop1m ")]), 1, f)
            elf = os.path.join(out, "build-arm", "bench-Os-MONO_PAGE.elf")
            nm = os.path.join(out, "nm-arm-Os-MONO_PAGE.txt")

            def run(e, expect, word):
                p = subprocess.run([node, runner, js, "arm", e, nm], capture_output=True, text=True, timeout=120)
                self.assertEqual(p.returncode, expect, word + p.stdout + p.stderr)
                self.assertIn(word, p.stdout + p.stderr)

            for name, code in (("udf", b"\x00\xde"), ("bkpt", b"\x00\xbe")):
                bad = os.path.join(tmp, name + ".elf")  # the first instruction of bench_mark_start, inside its interval
                self._patch_elf(elf, bad, nm, "bench_mark_start", data=code)
                run(bad, 1, "fail:")
            trunc = os.path.join(tmp, "trunc.elf")
            with open(elf, "rb") as fh, open(trunc, "wb") as oh:
                oh.write(fh.read(100))
            run(trunc, 2, "truncated")
            badname = os.path.join(tmp, "badname.elf")
            self._patch_elf(elf, badname, nm, None, find=b"cal_empty\x00", repl=b"CAL-empty\x00")
            run(badname, 1, "bad case name")

    def test_run_pico_names_the_guard_exit(self):
        """run-pico.sh: a non-zero guard status (124 time, 127 cannot run, 1 failed run) is named in the message."""
        opt = os.environ.get("OPT", os.path.expanduser("~/opt"))
        if not os.path.exists(os.path.join(opt, "arm-gnu-toolchain-15.2.rel1/bin/arm-none-eabi-gcc")):
            raise unittest.SkipTest("no arm-none-eabi-gcc under OPT")
        # run-pico.sh verifies the rp2040js install before it builds anything: skip unless that passes
        v = subprocess.run(["sh", os.path.join(BENCH, "install-emulators.sh"), "--verify", "rp2040js"],
                           env=dict(os.environ, OPT=opt), capture_output=True, text=True)
        if v.returncode != 0 or "rp2040js: OK" not in v.stdout:
            raise unittest.SkipTest("rp2040js is not installed or not verified under OPT")
        with tempfile.TemporaryDirectory() as tmp:
            for body, extra, code, word in (("sleep 30\n", {"LIMIT": "1"}, "124", "time limit"),
                                            ("exit 1\n", {}, "1", "non-zero exit"),
                                            ("yes\n", {}, "125", "cap"),
                                            (None, {}, "127", "could not be run")):
                fake = os.path.join(tmp, "fake-node")
                node = fake if body is not None else os.path.join(tmp, "no-such-node")
                if body is not None:
                    with open(fake, "w") as fh:
                        fh.write("#!/bin/sh\n" + body)
                    os.chmod(fake, 0o755)
                r = subprocess.run(["sh", os.path.join(BENCH, "run-pico.sh"), os.path.join(tmp, "out")],
                                   env=dict(os.environ, NODE=node, **extra), capture_output=True, text=True,
                                   timeout=300)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("guard exit " + code, r.stdout)
                self.assertIn(word, r.stdout)

    def test_measurements_md_numbers_are_derived(self):
        """c/bench/check-measurements-md.py: the us columns follow from cycles / insns and the clock, and the generated
        ratio tables equal what the result tables give; a doctored copy fails."""
        script = os.path.join(BENCH, "check-measurements-md.py")
        md = os.path.join(BENCH, "MEASUREMENTS.md")
        r = subprocess.run([sys.executable, "-I", script, md], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = open(md, encoding="utf-8").read()
        with tempfile.TemporaryDirectory() as tmp:
            for name, old, new in (("us", "| 6049 | 48.39 |", "| 6049 | 48.38 |"),
                                   ("us-a-hundredth-up", "| 1449609 | 11596.87 |", "| 1449609 | 11596.88 |"),
                                   ("us-neighbour", "| 19522 | 156.17 |", "| 19522 | 156.18 |"),
                                   ("ratio", "<!-- ratios:begin -->\n", "<!-- ratios:begin -->\nx\n"),
                                   ("insns", "| syl_ga | 100 | 3375 |", "| syl_ga | 100 | 3275 |"),
                                   ("m33-us", "| syl_ga | 100 | 3308 | 2626 | 22.05 |", "| syl_ga | 100 | 3308 | 2626 | 22.06 |"),
                                   ("m33-count", "| syl_ga | 100 | 3308 | 2626 |", "| syl_ga | 100 | 3309 | 2626 |"),
                                   ("h3-us", "| syl_ga | 100 | 3601 | 2808 | 24.01 | 18.72 |", "| syl_ga | 100 | 3601 | 2808 | 24.02 | 18.72 |"),
                                   ("m33r-count", "| syl_ga | 100 | 5132 | 3795 | 34.21 | 25.30 |", "| syl_ga | 100 | 5133 | 3795 | 34.21 | 25.30 |")):
                self.assertIn(old, text, name)
                bad = os.path.join(tmp, name + ".md")
                with open(bad, "w", encoding="utf-8") as fh:
                    fh.write(text.replace(old, new, 1))
                r = subprocess.run([sys.executable, "-I", script, bad], capture_output=True, text=True)
                self.assertEqual(r.returncode, 1, name + r.stdout + r.stderr)

    def test_run_scripts_fail_on_a_missing_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            for script in ("run-esp32.sh", "run-pico.sh", "run-m33.sh", "run-rp2350.sh"):
                r = subprocess.run(["sh", os.path.join(BENCH, script), os.path.join(tmp, "o")],
                                   env=dict(os.environ, OPT=os.path.join(tmp, "nothing")), capture_output=True,
                                   text=True)
                self.assertEqual(r.returncode, 1, script + r.stdout + r.stderr)
                self.assertIn("not installed", r.stdout, script)

    def test_report_awk_case_set_and_insns(self):
        for kind in ("MONO_PAGE", "GRAY8", "RGB565"):
            self.assertEqual(self.awk(self.run_text(kind), kind), 0, kind)
        self.assertEqual(self.awk(self.run_text(drop="aa_line12")), 1)
        self.assertEqual(self.awk(self.run_text(drop="line8")), 1)
        self.assertEqual(self.awk(self.run_text(extra=["bogus:00000000"])), 1)
        self.assertEqual(self.awk(self.run_text(no_insns="screen32")), 1)
        self.assertEqual(self.awk(self.run_text(zero_insns="screen32")), 1)
        dup = self.run_text().replace("end=0", "case=line8 iters=1 cycles=1 per_iter_cycles=1.0 insns=1 "
                                       "per_iter_insns=1.0 sum=00000000\nend=0")
        self.assertEqual(self.awk(dup), 1)


# ---- SVFN v3: the library reads the faces in every layout ---------------------------------------------------------------

SVF2TO3 = os.path.join(HERE, "svf2to3.py")
_v3 = {}


def v3_faces(profile):
    """The directory with svf/ converted to @p profile (a name, or a units string "R,W,T,O"), made once per run under
    c/build/v3faces/<profile> with svf2to3.py --tree (absolute paths). The path of a face below it is the same as below
    svf/."""
    if profile in _v3:
        return _v3[profile]
    out = os.path.join(C_DIR, "build", "v3faces", profile.replace(",", "-"))
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    flag = "--units" if "," in profile else "--profile"
    r = subprocess.run([sys.executable, "-I", SVF2TO3, "--tree", SVF_DIR, out, flag, profile],
                       capture_output=True, text=True)
    if r.returncode != 0 or "failed=0" not in r.stdout:
        raise AssertionError("svf2to3 --tree failed:\n" + r.stdout[-2000:] + r.stderr)
    _v3[profile] = out
    return out


def v3_path(profile, face):
    """The converted copy of the face at @p face (a path below svf/); svf/ is the default profile, so that is the face."""
    if profile == "default":
        return face
    return os.path.join(v3_faces(profile), os.path.relpath(face, SVF_DIR))


def face_named(name):
    for p in faces():
        if os.path.basename(p) == name + ".SVF":
            return p
    raise AssertionError("no face " + name)


def split_glyphs(blob, stride):
    """svfdump glyphs output -> {code point: the 4 metrics bytes + the cell}."""
    n = 8 + stride
    return {struct.unpack_from("<I", blob, k)[0]: blob[k + 4:k + n] for k in range(0, len(blob), n)}


def stride_of(data):
    _, bpp, _, cw, ch = header(data)[:5]
    return (cw * bpp + 7) // 8 * ch


def convert(src, dst, *opts):
    """tools/svf2to3.py SRC DST OPTS...: the converted face's path."""
    r = subprocess.run([sys.executable, "-I", SVF2TO3, src, dst] + list(opts), capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"svf2to3 {src} {' '.join(opts)} exited {r.returncode}: {r.stderr}")
    return dst


def v3_info(data):
    """(count, cell bytes, rec, row, glyph data offset, offset table offset, u32 offsets, pitch, cell_h, bpp) of a v3
    file."""
    (_, _, _, bpp, b9, b10, _, count, cw, ch) = struct.unpack_from("<4sHHBBBBHBB", data)
    data_off, data_size = struct.unpack_from("<II", data, 24)
    (tab_off,) = struct.unpack_from("<I", data, 44)
    pitch = (cw * bpp + 7) // 8
    return count, pitch * ch, b9 & 7, b9 >> 3 & 7, data_off, tab_off, bool(b10 & 8), pitch, ch, bpp


def v3_record(data, g):
    """(record length, x0, y0, wb, h, rp) of glyph index @p g of a v3 file."""
    count, stride, rec, row, data_off, tab_off, off32, pitch, ch, bpp = v3_info(data)
    w = 4 if off32 else 2
    a, b = (struct.unpack_from("<I" if off32 else "<H", data, tab_off + w * i)[0] << (0 if off32 else rec)
            for i in (g, g + 1))
    x0, y0, wb, h = data[data_off + a:data_off + a + 4]
    unit = 1 << row
    return b - a, x0, y0, wb, h, (wb + unit - 1) // unit * unit


def expected_glyph_reads(data, g):
    """The read callback calls a streamed face without a cache makes for glyph index @p g (svf_glyph, spec "Reading a
    glyph"): a record that fits the cell is one read; a longer one is its header and then all rows (two) when the rows
    fit the cell, else the header and one read a row; a blank longer record is the header only."""
    ln, _, _, wb, h, rp = v3_record(data, g)
    stride = v3_info(data)[1]
    if ln <= stride:
        return 1
    if not wb or not h:
        return 1
    return 2 if h * rp <= stride else 1 + h


def cmap_of(data):
    count = struct.unpack_from("<H", data, 12)[0]
    (cmap_off,) = struct.unpack_from("<I", data, 32)
    return {struct.unpack_from("<I", data, cmap_off + 8 * k)[0]: struct.unpack_from("<I", data, cmap_off + 8 * k + 4)[0]
            for k in range(count)}


V3_PROFILES = ("mcu-strict", "default", "dos", "full", "simd16", "6,6,6,32")
V3_SAMPLE = ("NEODG16G", "PAPLG16", "PAPLG18", "MARUS24", "NGOTB16B")


def sample_variants(tmp):
    """{(face name, profile label): path} of the five sample faces in V3_PROFILES and in mcu-strict with box y. The
    JSET block keeps the source face's version (a re-layout only; --jset-version auto would renumber the pieces of a
    large v1 face)."""
    out = {}
    for name in V3_SAMPLE:
        src = face_named(name)
        with open(src, "rb") as fh:
            jset = jamoset.parse_svfn(fh.read()).jset
        keep = [] if jset is None else ["--jset-version", str(struct.unpack_from("<H", jset, 4)[0])]
        for prof in V3_PROFILES + ("mcu-strict/y",):
            dst = os.path.join(tmp, name + "-" + prof.replace(",", "-").replace("/", "-") + ".svf")
            if prof == "mcu-strict/y":
                convert(src, dst, "--profile", "mcu-strict", "--box", "y", *keep)
            else:
                convert(src, dst, "--units" if "," in prof else "--profile", prof, *keep)
            out[(name, prof)] = dst
    return out


class TestV3Stream(unittest.TestCase):
    """v3 faces through svf_open_stream, mapped at an odd address, and the offset width at its boundary."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.tmp = tempfile.mkdtemp(prefix="svf-v3stream-")
        cls.variants = sample_variants(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def clean(self, err):
        self.assertNotIn("Sanitizer", err)
        self.assertNotIn("runtime error", err)
        self.assertNotIn("past the end", err)

    def dumps(self, path):
        with open(path, "rb") as fh:
            jamo = struct.unpack_from("<H", fh.read(8), 6)[0] & jamoset.FLAG_JAMO
        return ("info", "glyphs", "syllables") if jamo else ("info", "glyphs")

    def same_as_mapped(self, path, *opts):
        for cmd in self.dumps(path):
            mapped = run_dump(path, cmd)
            code, out, err = stream_dump(path, *opts, cmd)
            self.clean(err)
            self.assertEqual(code, 0, err)
            self.assertEqual(out, mapped, f"{os.path.basename(path)} {opts} {cmd}")

    def test_stream_equals_mapped_all_profiles(self):
        for (name, prof), path in sorted(self.variants.items()):
            for cfg in ("--stream", "--stream=4:512"):
                with self.subTest(face=name, profile=prof, cfg=cfg):
                    self.same_as_mapped(path, cfg)

    def test_stream_records_longer_than_cell(self):
        """Review Focus 1: no cache, `full` profile (every non-blank record is its header and a whole cell, longer than the
        cell), and dos / units 6,6,6,32 whose rows fill or pass it: the streamed cells are the mapped ones, using only the
        cell (and its second half for a syllable) as scratch; the reads per glyph are the header and then the rows."""
        for name in V3_SAMPLE:
            for prof in ("full", "dos", "6,6,6,32", "default"):
                path = self.variants[(name, prof)]
                with self.subTest(face=name, profile=prof):
                    self.same_as_mapped(path, "--stream")
        path = self.variants[("PAPLG16", "full")]
        with open(path, "rb") as fh:
            data = fh.read()
        cm = cmap_of(data)
        ascii_cps = [cp for cp in sorted(cm) if 0x21 <= cp < 0x7F]
        code, out, err = stream_dump(path, "--stream", "reads", *("U+%04X" % cp for cp in ascii_cps))
        self.assertEqual(code, 0, err)
        got = [int(line.split("reads=")[1]) for line in out.decode().splitlines()]
        want = [expected_glyph_reads(data, cm[cp]) for cp in ascii_cps]
        self.assertEqual(got, want)
        self.assertIn(2, got, "no full glyph read in 2 reads")
        self.assertEqual(set(got) - {1, 2}, set())

    def test_stream_cache_records_straddle_blocks(self):
        """Review Focus 2: 64-byte blocks, every profile (the dos profile's byte-tight records start at every offset):
        a record's header or a row crosses a block end and the cells still equal the mapped ones."""
        for (name, prof), path in sorted(self.variants.items()):
            with self.subTest(face=name, profile=prof):
                self.same_as_mapped(path, "--stream=1:64")

    def test_mapped_face_at_odd_address(self):
        """Review Focus 3: the file bytes start 1, 2 or 3 past a 4-aligned allocation (svfdump --face-offset): the same
        dumps as at an aligned address, ASan clean."""
        for (name, prof), path in sorted(self.variants.items()):
            for cmd in self.dumps(path):
                base = run_dump(path, cmd)
                for k in (1, 2, 3):
                    with self.subTest(face=name, profile=prof, cmd=cmd, offset=k):
                        code, out, err = stream_dump(path, f"--face-offset={k}", cmd, asan=True)
                        self.clean(err)
                        self.assertEqual(code, 0, err)
                        self.assertEqual(out, base)

    def test_stream_reads_per_glyph_v3(self):
        """No cache: a record that fits the cell is one read per glyph or jamo piece (an x-boxed jamo face), `full` two for
        a full glyph (header, then all rows), and a face whose rows pass the cell (units 6,6,6,32: rows of 64 bytes) the
        header and one read per row, h + 1."""
        jamo = self.variants[("NEODG16G", "default")]
        with open(jamo, "rb") as fh:
            data = fh.read()
        cm = cmap_of(data)
        _, t = jamo_tables(data)
        sylls = (0xAC00, 0xAC01, 0xB098, 0xD7A3, 0xD55C)
        code, out, err = stream_dump(jamo, "--stream", "reads", *("U+%04X" % cp for cp in sylls))
        self.assertEqual(code, 0, err)
        got = [int(line.split("reads=")[1]) for line in out.decode().splitlines()]
        want = [sum(expected_glyph_reads(data, cm[jamoset.PIECE_BASE + p]) for p in jamoset.pieces_of(t, cp)
                    if p != jamoset.BLANK) for cp in sylls]
        self.assertEqual(got, want)
        pieces = [expected_glyph_reads(data, g) for g in cm.values()]
        self.assertEqual(set(pieces) - {1, 2}, set())
        # x-boxed pieces of the default profile that fit the 32 byte cell are one read each
        self.assertGreater(pieces.count(1), len(pieces) // 2)
        for prof, expect in (("full", {1, 2}), ("6,6,6,32", None)):
            path = self.variants[("PAPLG16", prof)]
            with open(path, "rb") as fh:
                d = fh.read()
            c = cmap_of(d)
            cps = [cp for cp in sorted(c) if 0x21 <= cp < 0x7F]
            code, out, err = stream_dump(path, "--stream", "reads", *("U+%04X" % cp for cp in cps))
            self.assertEqual(code, 0, err)
            got = [int(line.split("reads=")[1]) for line in out.decode().splitlines()]
            self.assertEqual(got, [expected_glyph_reads(d, c[cp]) for cp in cps])
            if expect:
                self.assertEqual(set(got), {2})
            else:
                hs = [v3_record(d, c[cp])[4] for cp in cps]
                self.assertEqual(got, [1 + h for h in hs])
                self.assertTrue(all(h > 1 for h in hs))

    def test_u16_offsets_at_boundary(self):
        """Review Focus 5: glyph data of exactly 65535 byte units stays u16, one more unit is u32 (dos profile: unit 1),
        and the C reader (mapped and streamed) reads both."""
        cw, ch = 8, 16
        n = 4000
        for total, want_off32 in ((65535, False), (65536, True)):
            extra = total - 4 * n
            hs = [12] * n
            for i in range(extra - 12 * n):
                hs[i] += 1
            self.assertEqual(sum(hs) + 4 * n, total)
            cells = []
            for i, h in enumerate(hs):
                cell = bytearray(ch)
                for y in range(h):
                    cell[y] = 0x80 | (i + y) & 0x7F
                cells.append(bytes(cell))
            cmap = [(0x100 + i, i) for i in range(n)]
            blob = jamoset.pack_svfn(cw, ch, 12, 1, 0, cells, cmap, None, None, (0, 0), "dos")
            self.assertEqual(bool(blob[10] & 8), want_off32, total)
            self.assertEqual(struct.unpack_from("<I", blob, 28)[0], total)
            path = os.path.join(self.tmp, f"u16-{total}.svf")
            with open(path, "wb") as fh:
                fh.write(blob)
            want = b"".join(struct.pack("<I", 0x100 + i) + bytes(4) + c for i, c in enumerate(cells))
            for opts in ((), ("--stream",), ("--stream=4:512",)):
                with self.subTest(total=total, opts=opts):
                    code, out, err = stream_dump(path, *opts, "glyphs", asan=True)
                    self.clean(err)
                    self.assertEqual(code, 0, err)
                    self.assertEqual(out, want)


class TestLayoutHostile(unittest.TestCase):
    """Hostile v3 headers, offset tables and records: each LAYOUT_BAD kind is refused with its error, a streamed open
    gives the mapped open's result for header and table faults and refuses a bad record only when that glyph is read."""

    @classmethod
    def setUpClass(cls):
        build()
        cls.tmp = tempfile.mkdtemp(prefix="svf-layout-")
        cls.base = os.path.join(cls.tmp, "base.svf")
        convert(face_named("NEODG16G"), cls.base)
        with open(cls.base, "rb") as fh:
            cls.data = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def clean(self, err):
        self.assertNotIn("Sanitizer", err)
        self.assertNotIn("runtime error", err)
        self.assertNotIn("past the end", err)

    def run_face(self, path, *args):
        code, out, err = stream_dump(path, *args, asan=True)
        self.clean(err)
        return code, out, err

    def bad_face(self, kind):
        import svf_synth
        path = os.path.join(self.tmp, kind + ".svf")
        r = subprocess.run([sys.executable, "-I", SYNTH, "--layout-bad", kind, "--from", self.base, path],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return path, svf_synth.LAYOUT_BAD[kind]

    def test_layout_bad_kinds(self):
        import svf_synth
        want_glyphs = run_dump(self.base, "glyphs")
        with open(face_named("NEODG16G"), "rb") as fh:
            stride = stride_of(fh.read())
        for kind in sorted(svf_synth.LAYOUT_BAD):
            path, expect = self.bad_face(kind)
            for cfg in ("", "--stream", "--stream=4:512"):
                opts = (cfg,) if cfg else ()
                with self.subTest(kind=kind, cfg=cfg):
                    code, out, err = self.run_face(path, *opts, "info")
                    if expect == "jset_bad":
                        self.assertEqual(code, 0, err)
                        info = dict(kv.split("=") for kv in out.decode().split())
                        self.assertEqual((info["jset_bad"], info["jamo"]), ("1", "0"))
                        code, out, err = self.run_face(path, *opts, "glyphs")
                        self.assertEqual(code, 0, err)
                        self.assertEqual(out, want_glyphs)
                    elif expect == "SVF_E_RANGE" and cfg:
                        # a streamed open does not read the records: the bad glyph fails when it is read
                        self.assertEqual(code, 0, err)
                        code, out, err = self.run_face(path, *opts, "glyphs")
                        self.assertEqual(code, 2, err)
                        bad = [line for line in err.splitlines() if line.startswith("svfdump: glyph U+")]
                        self.assertEqual(len(bad), 1, err)
                        self.assertTrue(bad[0].endswith("SVF_E_RANGE"), err)
                        cp = int(bad[0].split("U+")[1].split(":")[0], 16)
                        got, want = split_glyphs(out, stride), split_glyphs(want_glyphs, stride)
                        self.assertEqual(sorted(got), sorted(want))
                        for c in want:
                            if c == cp:
                                self.assertEqual(got[c][4:], bytes(stride), "the cell of the bad record is not zero")
                            else:
                                self.assertEqual(got[c], want[c], hex(c))
                    else:
                        self.assertEqual(code, 2, err)
                        self.assertIn(expect, err)

    def test_jset_missing_piece_parity(self):
        """A v3 JSET naming a piece with no glyph leaves a plain face in C (the engine's usable() rule) and in
        jamoset.parse_svfn alike."""
        for prof in ("default", "dos"):
            path = os.path.join(self.tmp, f"mp-{prof}.svf")
            r = subprocess.run([sys.executable, "-I", SYNTH, "--jset-bad", "missing_piece", "--profile", prof,
                                "--from", self.base, path], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(path, "rb") as fh:
                f = jamoset.parse_svfn(fh.read())
            self.assertTrue(f.jset_bad, prof)
            self.assertIsNone(f.jset, prof)
            code, out, err = self.run_face(path, "info")
            self.assertEqual(code, 0, err)
            info = dict(kv.split("=") for kv in out.decode().split())
            self.assertEqual((info["jset_bad"], info["jamo"]), ("1", "0"))
        # and a good face is unchanged
        with open(self.base, "rb") as fh:
            f = jamoset.parse_svfn(fh.read())
        self.assertFalse(f.jset_bad)
        self.assertIsNotNone(f.jset)

    def test_versions_refused(self):
        for version in (0, 1, 4, 0xFFFF):
            d = bytearray(self.data)
            struct.pack_into("<H", d, 4, version)
            path = os.path.join(self.tmp, f"v{version}.svf")
            with open(path, "wb") as fh:
                fh.write(bytes(d))
            for cfg in ("", "--stream"):
                with self.subTest(version=version, cfg=cfg):
                    code, _, err = self.run_face(path, *((cfg,) if cfg else ()), "info")
                    self.assertEqual(code, 2, err)
                    self.assertIn("SVF_E_VERSION", err)

    def test_header_fields_hostile(self):
        """Counts, cell size, bpp and table offsets of a v3 header broken one at a time: refused cleanly, mapped and
        streamed alike."""
        d0 = self.data
        count = struct.unpack_from("<H", d0, 12)[0]
        cases = {
            "bpp 3": (8, "<B", 3, "SVF_E_BPP"),
            "glyphs 0": (12, "<H", 0, "SVF_E_RANGE"),
            "cell width 0": (14, "<B", 0, "SVF_E_RANGE"),
            "cell height 0": (15, "<B", 0, "SVF_E_RANGE"),
            "cmap in the header": (32, "<I", 44, "SVF_E_RANGE"),
            "cmap past the file": (32, "<I", len(d0) - 4, "SVF_E_RANGE"),
            "offset table in the header": (44, "<I", 40, "SVF_E_RANGE"),
            "offset table past the file": (44, "<I", len(d0) - 4, "SVF_E_RANGE"),
            "data in the header": (24, "<I", 0, "SVF_E_RANGE"),
            "data past the file": (28, "<I", len(d0), "SVF_E_RANGE"),
            "jset past the file": (36, "<I", len(d0) - 4, "SVF_E_RANGE"),
            "jset in the header": (36, "<I", 40, "SVF_E_RANGE"),
            "glyphs 65535": (12, "<H", 65535, "SVF_E_RANGE"),
        }
        for name, (off, fmt, value, err_name) in sorted(cases.items()):
            d = bytearray(d0)
            struct.pack_into(fmt, d, off, value)
            path = os.path.join(self.tmp, "hdr.svf")
            with open(path, "wb") as fh:
                fh.write(bytes(d))
            for cfg in ("", "--stream", "--stream=4:512"):
                with self.subTest(case=name, cfg=cfg):
                    code, _, err = self.run_face(path, *((cfg,) if cfg else ()), "info")
                    self.assertEqual(code, 2, err)
                    self.assertIn(err_name, err)
        self.assertGreater(count, 6)

    def test_unknown_flag_bits_refused(self):
        """Header flag bits 3..15 refused with SVF_E_LAYOUT by the C library (mapped and streamed) and with ValueError
        by jamoset.parse_svfn; the defined bits keep the face valid."""
        for bit in range(3, 16):
            d = bytearray(self.data)
            flags = struct.unpack_from("<H", d, 6)[0] | 1 << bit
            struct.pack_into("<H", d, 6, flags)
            path = os.path.join(self.tmp, "flag.svf")
            with open(path, "wb") as fh:
                fh.write(bytes(d))
            for cfg in ("", "--stream", "--stream=4:512"):
                with self.subTest(bit=bit, cfg=cfg):
                    code, _, err = self.run_face(path, *((cfg,) if cfg else ()), "info")
                    self.assertEqual(code, 2, err)
                    self.assertIn("SVF_E_LAYOUT", err)
            with self.subTest(bit=bit, reader="jamoset"):
                with self.assertRaisesRegex(ValueError, "SVFN flags 0x%04x: unknown bits" % flags):
                    jamoset.parse_svfn(bytes(d))
        # a defined bit changed (marks at origin) stays valid in both readers
        d = bytearray(self.data)
        struct.pack_into("<H", d, 6, struct.unpack_from("<H", d, 6)[0] | 4)
        path = os.path.join(self.tmp, "flag4.svf")
        with open(path, "wb") as fh:
            fh.write(bytes(d))
        code, _, err = self.run_face(path, "info")
        self.assertEqual(code, 0, err)
        jamoset.parse_svfn(bytes(d))

    def test_metrics_in_header_dropped_v3(self):
        d = bytearray(self.data)
        struct.pack_into("<I", d, 20, 44)
        path = os.path.join(self.tmp, "m.svf")
        with open(path, "wb") as fh:
            fh.write(bytes(d))
        for cfg in ("", "--stream"):
            code, out, err = self.run_face(path, *((cfg,) if cfg else ()), "info")
            self.assertEqual(code, 0, err)
            self.assertIn("metrics=0", out.decode())

    def refused_or_plain(self, path):
        r = subprocess.run([build()["svfdump-asan"], path, "info"], capture_output=True)
        err = r.stderr.decode(errors="replace")
        self.assertNotIn("Sanitizer", err, path)
        self.assertNotIn("runtime error", err, path)
        return r.returncode, err

    def test_truncated_at_every_byte_to_the_offset_table(self):
        """NEODG16G and PAPLG18 in `default` and `dos`, cut at every byte up to the end of their glyph offset table: every
        cut refused, mapped and streamed, the face left all zero, no sanitizer report (test-layouts --cuts opens each cut
        in a buffer of exactly its size)."""
        total = 0
        for name in ("NEODG16G", "PAPLG18"):
            for prof in ("default", "dos"):
                path = v3_path(prof, face_named(name))
                with open(path, "rb") as fh:
                    count, _, _, _, _, tab_off, off32, _, _, _ = v3_info(fh.read())
                end = tab_off + (4 if off32 else 2) * (count + 1)
                r = subprocess.run([build()["test-layouts"], "--cuts", path, str(end)], capture_output=True, text=True)
                with self.subTest(face=name, profile=prof):
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    self.assertEqual(r.stdout.strip(), f"cuts: {end + 1} refused")
                    self.assertNotIn("Sanitizer", r.stderr)
                total += end + 1
        print(f"\n  test_truncated_at_every_byte_to_the_offset_table: {total} cuts refused", file=sys.stderr)


class TestLayoutsBuild(unittest.TestCase):
    """c/tests/test_layouts.c built four ways (the default build and three SVF_LAYOUTS sets), and test_open built for a
    16-bit size_t: run here, where the six input files are written (make check does not run them itself, F17)."""

    FILES = {"default": ("--profile", "default"), "mcu-strict": ("--profile", "mcu-strict"),
             "dos": ("--profile", "dos"), "simd16": ("--profile", "simd16"), "full": ("--profile", "full"),
             "u64": ("--units", "6,6,6,32")}

    def test_four_builds(self):
        b = build()
        tmp = tempfile.mkdtemp(prefix="svf-layouts-")
        try:
            for name, opts in self.FILES.items():
                convert(face_named("NEODG16G"), os.path.join(tmp, name + ".svf"), *opts)
            lines = {}
            for exe, label in (("test-layouts", "default"), ("test-layouts-strict", "strict"),
                               ("test-layouts-tight", "tight"), ("test-layouts-pair", "pair")):
                r = subprocess.run([b[exe], tmp, label], capture_output=True, text=True)
                out = r.stdout.strip().splitlines()
                self.assertEqual(r.returncode, 0, exe + "\n" + r.stdout + r.stderr)
                self.assertNotIn("Sanitizer", r.stderr)
                self.assertEqual(out[-1], f"layouts: OK {label}", exe)
                lines[label] = dict(kv.split("=") for kv in out[0].split()[1:])
                self.assertEqual(sorted(lines[label]), sorted(self.FILES), exe)
            ok, no = "SVF_OK", "SVF_E_LAYOUT"
            self.assertEqual(set(lines["default"].values()), {ok})
            self.assertEqual(lines["strict"], {"default": ok, "mcu-strict": ok, "full": ok, "dos": no, "simd16": no,
                                               "u64": no})
            self.assertEqual(lines["tight"], {"default": no, "mcu-strict": no, "full": no, "dos": ok, "simd16": no,
                                              "u64": no})
            self.assertEqual(lines["pair"], {"default": ok, "mcu-strict": ok, "full": ok, "dos": ok, "simd16": no,
                                             "u64": no})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_open_for_a_16_bit_size_t(self):
        face = v3_path("default", face_named("NEODG16G"))
        for exe in ("test-open", "test-open-size16"):
            r = subprocess.run([build()[exe], face], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, exe + "\n" + r.stdout + r.stderr)
            self.assertNotIn("FAIL", r.stdout)
            self.assertNotIn("Sanitizer", r.stderr)
        r = subprocess.run([build()["test-open-size16"], face], capture_output=True, text=True)
        self.assertIn("tables-size-overflow: ok", r.stdout)


class TestMacFbit45C(unittest.TestCase):
    """HangulTalk 1.0 faces (--layout mac-fbit-45sets: JSET version 1, 8 lead x 4 tail classes, 20/15/4 sets) through the
    version 1 reader alone (build_reader("v1only")): svfdump's 11,172 syllables equal jamoset's composition, which
    tools/test_jamoset.py MacFbit45Sets proves equal to the Mac composer. Mapped, in every STREAM_CONFIGS entry, and
    through the 8-bit-read build. The Mac fonts are not in the repository: a font that is absent is skipped by name."""

    def test_mac_fbit45_c_reader(self):
        import test_jamoset
        with tempfile.TemporaryDirectory() as tmp:
            faces = test_jamoset.mac_fbit_faces(tmp)
            if not os.path.isdir(test_jamoset.MAC_TOOLS):
                self.skipTest(f"mac_kfont.py not collected: {test_jamoset.MAC_TOOLS} is missing")
            missing = [os.path.join(test_jamoset.MAC_SYSTEM, n + ".rsrc") for n in test_jamoset.MAC_FBIT_FONTS
                       if n not in faces]
            if len(missing) == len(test_jamoset.MAC_FBIT_FONTS):
                self.skipTest("no HangulTalk font collected: " + ", ".join(missing))
            exes = build_reader("v1only")
            runs = [("svfdump-asan", "")] + [("svfdump-asan", c) for c in STREAM_CONFIGS] + [("svfdump-rd8", "")]
            for name, (path, run, _ref, w, h) in faces.items():
                with self.subTest(font=name):
                    self.assertEqual(run.returncode, 0, run.stderr)
                    data = open(path, "rb").read()
                    want = expected_syllables(data)
                    self.assertEqual(want[-1], 1)
                    self.assertEqual(len(want), (11172 + len(COMPAT_JAMO)) * ((w + 7) // 8 * h) + 1)
                    for exe, cfg in runs:
                        with self.subTest(exe=exe, cfg=cfg):
                            code, out, err = stream_dump(path, *([cfg] if cfg else []), "syllables", exe=exes[exe])
                            self.assertEqual(code, 0, err)
                            self.assertNotIn("Sanitizer", err)
                            self.assertNotIn("runtime error", err)
                            self.assertEqual(out, want)
                    code, out, err = stream_dump(path, "info", exe=exes["svfdump-asan"])
                    info = dict(kv.split("=") for kv in out.decode().split())
                    self.assertEqual((info["jamo"], info["jset_bad"]), ("1", "0"))
            for path in missing:
                with self.subTest(font=os.path.basename(path)):
                    self.skipTest("font absent: " + path)
            print(f"\n  test_mac_fbit45_c_reader: {len(faces)} fonts, v1only reader", file=sys.stderr)


if __name__ == "__main__":
    unittest.main()
