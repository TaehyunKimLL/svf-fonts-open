#!/usr/bin/env python3
"""Every maker route writes SVFN v3 (card t_a0a737c9): the output parses with jamoset.parse_svfn as version 3.

A v2 SVF upload is converted by its copy route (svf2to3.py --check) and the output draws the same face as the upload.
The comparison with the v2 tools of the svf-maker branch is maker/test/v2_parity.py (needs that tools tree).

  python3 -m unittest discover -s maker/test -p 'test_*.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import shutil
import tempfile
import unittest

import fixtures
import jamoset
import svf2to3
import v2_parity


class V3OutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="maker-v3-")
        cls.fx = fixtures.write_fixtures(os.path.join(cls.tmp, "fonts"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_route_writes_v3(self):
        names = []
        for i, (name, entry, kind, size, bpp, layout, src, extra) in enumerate(v2_parity.cases(self.fx, self.tmp)):
            with self.subTest(route=name):
                d = os.path.join(self.tmp, "c%02d" % i)
                out = os.path.join(d, "OUT.SVF")
                v2_parity.build(entry, kind, size, bpp, layout, src, extra, v2_parity.TOOLS, d, out)
                with open(out, "rb") as f:
                    data = f.read()
                self.assertEqual(data[4:6], b"\x03\x00")
                face = jamoset.parse_svfn(data)
                self.assertEqual((face.version, face.bpp, face.cell_h), (3, bpp, size))
                self.assertEqual(face.jset is not None, kind != "precomposed")
                if entry.get("svf"):                    # a v2 upload: converted, never shipped as v2
                    with open(src, "rb") as f:
                        source = f.read()
                    self.assertEqual(source[4:6], b"\x02\x00")
                    if kind != "jamo-fit":
                        svf2to3.check(source, data)
                names.append(name)
        self.assertEqual(len(names), 12)

    def _run_copy(self, data, extra, name):
        import detect, routes, subprocess
        d = os.path.join(self.tmp, name)
        os.makedirs(d)
        src, out = os.path.join(d, "in.svf"), os.path.join(d, "OUT.SVF")
        with open(src, "wb") as f:
            f.write(data)
        font = detect.detect_file(src, "in.svf")[0]
        paths = {"tools": v2_parity.TOOLS, "src": src, "out": out, "work": d, "eng": None, "latin": None,
                 "master": None, "range_file": None}
        cmds = routes.routes(font)[0].commands(font, font["sizes"][0], font["svf"]["bpp"], None, ("2350", None),
                                                paths, extra)
        if not cmds:
            shutil.copyfile(src, out)
        for argv in cmds:
            subprocess.run(argv, check=True, cwd=d)
        with open(out, "rb") as f:
            return jamoset.parse_svfn(f.read()), data

    def test_jset1_big_upload_stays_v1_by_default(self):
        face, data = self._run_copy(fixtures.jset1_big_face(), [], "big-default")
        self.assertEqual(svf2to3.jset_version(face.jset), 1)
        self.assertEqual(face.jset, jamoset.parse_svfn(data).jset)

    def test_jset1_big_upload_bakes_v2_when_asked(self):
        face, _ = self._run_copy(fixtures.jset1_big_face(), ["--jset-version", "2"], "big-v2")
        self.assertEqual(svf2to3.jset_version(face.jset), 2)

    def test_jset1_small_upload_stays_v1(self):
        face, _ = self._run_copy(fixtures.jset1_face(), [], "small")
        self.assertEqual(svf2to3.jset_version(face.jset), 1)

    def test_jset2_upload_back_to_v1_when_asked(self):
        v2 = svf2to3.convert(fixtures.jset1_big_face(), "default", jset_version=2)
        face, _ = self._run_copy(v2, [], "v2-keep")
        self.assertEqual(svf2to3.jset_version(face.jset), 2)
        face, _ = self._run_copy(v2, ["--jset-version", "1"], "v2-to-v1")
        self.assertEqual(svf2to3.jset_version(face.jset), 1)


if __name__ == "__main__":
    unittest.main()
