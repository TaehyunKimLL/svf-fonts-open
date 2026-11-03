#!/usr/bin/env python3
"""jamoexc.py tests: the LIST exception writer over svf/dos/NEODG16G.SVF and synthetic cells (temp dirs only).

  python3 -m unittest tools.test_jamoexc
"""

import atexit
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jamoset  # noqa: E402
import svf_synth  # noqa: E402
import test_c_renderer as tcr  # noqa: E402

ROOT = os.path.dirname(HERE)
TOOL = os.path.join(HERE, "jamoexc.py")
FACE = os.path.join(ROOT, "svf", "dos", "NEODG16G.SVF")
PLAIN = os.path.join(ROOT, "svf", "dos", "NEODG16.SVF")      # no JSET block
B = jamoset.BLANK


@atexit.register
def _drop_build():
    # the C build dir is shared with later modules of the run: removed once, when the process ends
    d = tcr._build.get("dir")
    if d:
        shutil.rmtree(d, ignore_errors=True)


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def layout_bytes(data):
    """flags, bpp, layout bytes 9/10, dy range of the v3 header."""
    h = struct.unpack_from(jamoset.HEADER3, data)
    return h[2], h[3], h[4], h[5], h[11], h[12]


class ExcCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = read(FACE)
        cls.face = jamoset.parse_svfn(cls.data)
        cls.t = jamoset.unpack(cls.face.jset)
        cls.stride = ((cls.face.cell_w * cls.face.bpp + 7) // 8) * cls.face.cell_h

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def run_tool(self, src, exc, *args, out="out.svf"):
        """(exit code, stdout, stderr, out path) of `jamoexc.py build SRC EXC OUT ARGS`; @p exc a dict (written as JSON)."""
        ep = self.path("exc.json")
        with open(ep, "w", encoding="utf-8") as fh:
            json.dump(exc, fh, ensure_ascii=False)
        op = self.path(out)
        r = subprocess.run([sys.executable, TOOL, "build", src, ep, op, *args], capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr, op

    def source(self, name="src.svf", data=None):
        p = self.path(name)
        with open(p, "wb") as fh:
            fh.write(self.data if data is None else data)
        return p

    def cell(self, s, v):
        return svf_synth._distinct(jamoset.compose(self.face, self.t, 0xAC00 + s), v)

    def pool(self):
        return tuple(sorted({p for p in lst if p != B}) for lst in (self.t.init_piece, self.t.med_piece, self.t.fin_piece))

    def recomb(self, s, pool):
        return svf_synth._list_recombination(self.face, self.t, s, pool)

    def exc_mixed(self, nwhole=10, nrecomb=10):
        pool = self.pool()
        exc = {}
        for j in range(nwhole):
            s = 100 + 37 * j
            exc[chr(0xAC00 + s)] = {"whole": self.cell(s, j + 1).hex()}
        for j in range(nrecomb):
            s = 5000 + 41 * j
            exc["U+%04X" % (0xAC00 + s)] = {"pieces": self.recomb(s, pool)}
        named = [k for k, c in enumerate(self.t.compat) if c != B]
        exc[chr(0x3131 + named[0])] = {"whole": bytes(range(1, self.stride + 1)).hex()}
        exc["U+%04X" % (0x3131 + named[1])] = {"pieces": [self.t.compat[named[2]]]}
        return exc


class Golden(ExcCase):
    def test_build_golden(self):
        exc = self.exc_mixed()
        code, out, err, op = self.run_tool(FACE, exc)
        self.assertEqual((code, err), (0, ""), err)
        data = read(op)
        f = jamoset.parse_svfn(data)
        jm = jamoset.unpack(f.jset)
        self.assertTrue(isinstance(jm, jamoset.Jmap) and jm.list_mode)
        self.assertEqual(jm.fallback_block, self.face.jset)          # the fallback is the source JSET bytes
        # the report line equals the block and the file
        m = re.fullmatch(r"jmap=(\d+) ns=(\d+) whole=(\d+) recomb=(\d+) total=(\d+)\n", out)
        self.assertIsNotNone(m, out)
        self.assertEqual(tuple(map(int, m.groups())), (len(f.jset), 20, 11, 11, len(data)))
        # the whole cells are what the syllables draw
        for j in range(10):
            s = 100 + 37 * j
            self.assertEqual(jamoset.compose(f, jm, 0xAC00 + s), self.cell(s, j + 1))
        # the C reader draws what Python composes, mapped and streamed (sanitizer build, LIST reader)
        want = tcr.expected_syllables(data)
        self.assertEqual(len(want), (11172 + 51) * self.stride + 1)
        exes = tcr.build_reader("list")
        for cfg in ("", "--stream=4:512"):
            with self.subTest(cfg=cfg):
                code, got, err = tcr.stream_dump(op, *([cfg] if cfg else []), "syllables", exe=exes["svfdump-asan"])
                self.assertEqual(code, 0, err)
                self.assertEqual(got, want)

    def test_build_sparse_note(self):
        pool = self.pool()
        for n, note in ((200, True), (199, False)):
            with self.subTest(n=n):
                exc = {chr(0xAC00 + 20 * j): {"pieces": [pool[0][j % len(pool[0])], pool[1][j % len(pool[1])]]}
                       for j in range(n)}
                code, out, err, _ = self.run_tool(FACE, exc)
                self.assertEqual(code, 0, err)
                if note:
                    self.assertRegex(out, r" sparse=2204\n$")
                else:
                    self.assertNotIn("sparse=", out)


class Fidelity(ExcCase):
    def test_build_fidelity(self):
        r = subprocess.run([sys.executable, os.path.join(HERE, "svf2to3.py"), "--profile", "dos", FACE, self.path("dos.svf")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        for name, src in (("default", FACE), ("dos", self.path("dos.svf"))):
            with self.subTest(source=name):
                sdata = read(src)
                s = jamoset.parse_svfn(sdata)
                code, out, err, op = self.run_tool(src, self.exc_mixed())
                self.assertEqual(code, 0, err)
                data = read(op)
                self.assertEqual(layout_bytes(data), layout_bytes(sdata))
                self.assertEqual(jamoset.parse_svfn(data).layout, s.layout)
                # every source code point: advance, bearing, ink width, dy and the cell, as svfdump reads it
                got = tcr.run_dump(op, "glyphs", asan=True)
                full = tcr.expected_glyphs(data)
                self.assertEqual(got, full)
                f = jamoset.parse_svfn(data)
                for cp in s.glyphs:
                    self.assertEqual(f.glyphs[cp], s.glyphs[cp])
                    self.assertEqual((f.metrics[cp], f.dy.get(cp, 0)), (s.metrics[cp], s.dy.get(cp, 0)))
                new = sorted(set(f.glyphs) - set(s.glyphs))
                self.assertEqual(len(new), 11)
                dflt = next(iter(s.metrics[cp] for cp in sorted(s.glyphs) if cp >= jamoset.PIECE_BASE))
                for cp in new:
                    self.assertGreater(cp, max(c for c in s.glyphs if c < 0x10FFFF and c >= jamoset.PIECE_BASE))
                    self.assertEqual((f.metrics[cp], f.dy.get(cp, 0)), (dflt, 0))
        # a profile on request changes the layout and nothing else
        code, out, err, op = self.run_tool(FACE, self.exc_mixed(), "--profile", "mcu-strict")
        self.assertEqual(code, 0, err)
        self.assertEqual(jamoset.parse_svfn(read(op)).layout[:3], (2, 0, 2))
        self.assertEqual(layout_bytes(read(op))[3], (2 | 0 << 3))

    def test_build_fidelity_version2_source(self):
        f, t = svf_synth.load(FACE)
        block, pm = svf_synth.packed(t, 2)
        v2 = svf_synth.rebuild(f, block, piece_map=pm)
        sp = self.source("v2.svf", v2)
        sf = jamoset.parse_svfn(v2)
        self.assertEqual(struct.unpack_from("<H", sf.jset, 4)[0], 2)
        pool = tuple(sorted({p for p in lst if p != B}) for lst in
                     (jamoset.unpack(sf.jset).init_piece, jamoset.unpack(sf.jset).med_piece, jamoset.unpack(sf.jset).fin_piece))
        code, out, err, op = self.run_tool(sp, {"가": {"pieces": [pool[0][0], pool[1][0]]}})
        self.assertEqual(code, 0, err)
        f = jamoset.parse_svfn(read(op))
        jm = jamoset.unpack(f.jset)
        self.assertEqual((jm.fallback_version, jm.fallback_block), (2, sf.jset))

    def test_jset_version_reencode(self):
        # a version 1 source whose piece numbers are not canonical (shifted by 3): version 2 keeps the numbers
        t = jamoset.unpack(self.face.jset)
        glyphs = dict(self.face.glyphs)
        shifted = {}
        for cp in list(glyphs):
            if cp >= jamoset.PIECE_BASE:
                shifted[cp + 3] = glyphs.pop(cp)
        glyphs.update(shifted)
        t = jamoset.shift_pieces(t, 3)
        block = jamoset.pack_fallback(t, 1, 0)
        data = jamoset.write_svfn(self.face.cell_w, self.face.cell_h, self.face.ascent,
                                  [(cp, g) + tuple(self.face.metrics.get(cp, self.face.metrics[0xF0000])) for cp, g in sorted(glyphs.items())],
                                  block, 0, 1)
        sp = self.source("v1.svf", data)
        src = jamoset.parse_svfn(data)
        st = jamoset.unpack(src.jset)
        self.assertEqual(struct.unpack_from("<H", src.jset, 4)[0], 1)
        pool = tuple(sorted({p for p in lst if p != B}) for lst in (st.init_piece, st.med_piece, st.fin_piece))
        exc = {chr(0xAC00 + s): {"pieces": [pool[0][s % len(pool[0])], pool[1][s % len(pool[1])]]} for s in (0, 3, 7, 1000)}
        c1, _, e1, o1 = self.run_tool(sp, exc, out="same.svf")
        c2, _, e2, o2 = self.run_tool(sp, exc, "--jset-version", "2", out="v2.svf")
        self.assertEqual((c1, c2), (0, 0), e1 + e2)
        a, b = jamoset.parse_svfn(read(o1)), jamoset.parse_svfn(read(o2))
        ja, jb = jamoset.unpack(a.jset), jamoset.unpack(b.jset)
        self.assertEqual((ja.fallback_version, jb.fallback_version), (1, 2))
        self.assertEqual(ja.fallback_block, src.jset)
        for cp in range(0xAC00, 0xD7A4):
            self.assertEqual(jamoset.compose(a, ja, cp), jamoset.compose(b, jb, cp), hex(cp))
        self.assertEqual(jb.advance, ja.advance)


class Refusals(ExcCase):
    def refused(self, src, exc, *args, text=None):
        code, out, err, op = self.run_tool(src, exc, *args)
        self.assertEqual(code, 1, (out, err))
        self.assertEqual(out, "")
        self.assertFalse(os.path.exists(op))
        if text:
            self.assertRegex(err, text)
        return err

    def test_refusals(self):
        pool = self.pool()
        over = {chr(0xAC00 + 20 * j): {"pieces": [pool[0][0], pool[1][0]]} for j in range(256)}
        self.refused(FACE, over, text=re.escape("use SPARSE (2372 B"))
        # a version 3 source: a LIST face built by the tool itself
        code, _, err, op = self.run_tool(FACE, {"가": {"pieces": [pool[0][0], pool[1][0]]}}, out="list.svf")
        self.assertEqual(code, 0, err)
        self.refused(op, {"각": {"pieces": [pool[0][0], pool[1][0]]}},
                     text=re.escape("the face already has a JSET version 3 block; start from the plain face"))
        self.refused(PLAIN, {"가": {"pieces": [0, 0]}}, text=re.escape("the face has no usable JSET block"))
        self.refused(FACE, {"가": {"whole": bytes(self.stride).hex(), "dy": 1}}, text=r"a piece carries no dy or metrics")
        self.refused(FACE, {"가": {"pieces": [0, 0], "advance": 9}}, text=r"a piece carries no dy or metrics")
        self.refused(FACE, {"가": {"whole": bytes(self.stride - 1).hex()}},
                     text=r"%d bytes.*expected %d bytes" % (self.stride - 1, self.stride))
        self.refused(FACE, {"가": {"whole": "zz" * self.stride}}, text=r"not hex")
        self.refused(FACE, {"ㄱ": {"pieces": [0, 0]}}, text=r"exactly one piece")
        self.refused(FACE, {"A": {"pieces": [0, 0]}}, text=r"not a syllable")
        self.refused(FACE, {"가": {"pieces": [0, 0], "whole": bytes(self.stride).hex()}}, text=r"exactly one of")
        self.refused(FACE, {"가": {"pieces": [0, 0]}, "U+AC00": {"pieces": [0, 1]}}, text=r"twice")
        self.refused(FACE, {"가": {"pieces": [60000, 0]}}, text=r"no glyph")

    def test_group_c_review_refusals(self):
        w = {"whole": bytes(self.stride).hex()}
        p = {"pieces": [0, 0]}
        # a key written twice literally in the JSON
        ep = self.path("dup.json")
        with open(ep, "w", encoding="utf-8") as fh:
            fh.write('{"가": {"pieces": [0, 0]}, "가": {"pieces": [0, 1]}}')
        op = self.path("o.svf")
        r = subprocess.run([sys.executable, TOOL, "build", FACE, ep, op], capture_output=True, text=True)
        self.assertEqual((r.returncode, os.path.exists(op)), (1, False))
        self.assertIn("written twice", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        # no syllable key
        for exc in ({}, {"ㄱ": w}, {"ㄱ": {"pieces": [0]}}):
            self.refused(FACE, exc, text=re.escape("a LIST needs at least one syllable entry (L3); compat jamo alone "
                                                   "cannot be listed"))
        # a BLANK compat piece
        self.refused(FACE, {"가": p, "ㄱ": {"pieces": [65535]}}, text=r"needs a piece")
        # loose U+ forms
        for key in ("u+ac0", "U+ AC00", "U+0AC00x", "U+AC0G", "U+AC", "U+0000AC00", "+AC00", "U+-AC00"):
            self.refused(FACE, {key: p}, text=r"not one character or U\+XXXX")

    def test_u16_overflow_names_the_way_out(self):
        base = {cp: g for cp, g in self.face.glyphs.items()}

        def face(n):
            cells = dict(base)
            for i in range(n):
                cells[0x4E00 + i] = bytes((i * 7 + j * 13 + 1) & 255 | 1 for j in range(self.stride))
            data = jamoset.write_svfn(self.face.cell_w, self.face.cell_h, self.face.ascent,
                                      [(cp, g) + tuple(self.face.metrics.get(cp, (16, 0, 16))) for cp, g in sorted(cells.items())],
                                      self.face.jset, 0, 1, profile="dos")
            return data, jamoset.parse_svfn(data).layout[3]
        lo, hi = 0, 4000
        while hi - lo > 1:                     # the largest filler count that still has u16 offsets
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if not face(mid)[1] else (lo, mid)
        data, off32 = face(lo)
        self.assertFalse(off32)
        sp = self.source("u16.svf", data)
        pool = self.pool()
        exc = {chr(0xAC00 + s): {"whole": bytes([s % 250 + 1] * self.stride).hex()} for s in range(1, 9)}
        err = self.refused(sp, exc, text=r"does not fit u16 offsets.*drop whole cells, or pass --profile with u32 or auto")
        code, out, err, op = self.run_tool(sp, exc, "--profile", "dos")
        self.assertEqual(code, 0, err)
        self.assertTrue(jamoset.parse_svfn(read(op)).layout[3])

    def test_refusal_texts_match_pack(self):
        pool = self.pool()
        over = {chr(0xAC00 + 20 * j): {"pieces": [pool[0][0], pool[1][0]]} for j in range(256)}
        err = self.refused(FACE, over)
        self.assertIn("256 LIST entries is over 255: use SPARSE (2372 B plus plane copies for recombinations)", err)

    def test_usage(self):
        r = subprocess.run([sys.executable, TOOL, "build", FACE, "x.json", "o.svf", "--jset-version", "3"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        r = subprocess.run([sys.executable, TOOL], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
