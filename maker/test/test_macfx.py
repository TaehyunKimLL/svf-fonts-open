#!/usr/bin/env python3
"""The synthetic Mac fixtures parse with the tools' own readers.

  python3 -m unittest discover -s maker/test -p 'test_macfx.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import unittest

import jamoset
import macfbit3
import macfbit_svf
import macfx


class MacFixtureTest(unittest.TestCase):
    def test_fixtures_parse(self):
        self.assertEqual(len(macfx.htbl_raw()), 9612)
        self.assertEqual(len(macfx.htbl_raw_padded()), 9816)
        macfbit_svf.Fbit3(macfx.fbit3_raw())
        macfbit_svf.Htbl1(macfx.htbl_raw_padded())
        macfbit_svf.Htbl1(macfx.htbl_raw())
        self.assertEqual(macfbit3.jm_unpack(macfx.jm(macfx.fbit3_fork())), macfx.fbit3_fork())
        self.assertEqual(macfbit3.load_fbit(macfx.fbit3_fork()), macfx.fbit3_raw())
        self.assertEqual(macfbit3.load_htbl1(macfx.htbl_fork()), macfx.htbl_raw())

    def test_fbit1_header(self):
        m = jamoset.MacFbit(macfx.fbit1_fork())
        self.assertEqual((m.w, m.h, len(m.sets)), (16, 16, 45))

    def test_latin_suitcase(self):
        fork = macfbit_svf.resource_fork(macfx.suitcase(12))
        macfbit_svf.nfnt_for_size(fork, 12)
        with self.assertRaises(ValueError):
            macfbit_svf.nfnt_for_size(fork, 9)
        self.assertEqual(len(macfx.hangul_pft()), 40000)


if __name__ == "__main__":
    unittest.main()
