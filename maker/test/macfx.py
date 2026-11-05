#!/usr/bin/env python3
"""Synthetic Mac fixtures for the maker's Mac kinds (t_cbd14d61): a type-3 `fbit`, an `HTBL` 1, the forks and JM
archives around them, a FOND/NFNT suitcase, a HangulTalk 1.0 font and a 12x24 `HANGUL24.PFT`. Everything is built
from the tools' own synthetic builders (`tools/test_macfbit3.py`, `tools/test_macfbit_svf.py`): no Apple data.
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import struct

import inputfx
import test_macfbit3
import test_macfbit_svf

CHARS = {0x41: (0, 4, ["0110", "1001", "1111", "1001", "0000"]),
         0x67: (0, 4, ["0000", "0111", "1001", "0111", "0001"])}      # the two glyphs of TestLatin


def fbit3_raw(seed=1):
    """The type-3 `fbit` resource (12 px cells, 482 planes)."""
    return test_macfbit_svf.synthetic(seed)[0]


def htbl_raw(seed=1):
    """The `HTBL` 1 table as `synthetic` makes it: 4 + 204 + 4 + 9,400 = 9,612 bytes, no trailing copy."""
    return test_macfbit_svf.synthetic(seed)[1]


def htbl_raw_padded(seed=1):
    """The same table in the 9,816-byte form `test_macfbit3.make_htbl` makes (second length 0x2468, trailing copy)."""
    raw = htbl_raw(seed)
    l1 = struct.unpack(">I", raw[:4])[0]
    t1, t2 = raw[4:4 + l1], raw[8 + l1:]
    return test_macfbit3.make_htbl([t1[i:i + 4] for i in range(0, len(t1), 4)],
                                   [t2[i:i + 4] for i in range(0, len(t2), 4)])


def fbit3_fork(seed=1):
    return test_macfbit3.resource_fork({("fbit", 17408): fbit3_raw(seed)})


def htbl_fork(seed=1):
    return test_macfbit3.resource_fork({("HTBL", 1): htbl_raw(seed)})


def jm(fork):
    """@p fork as a JM archive (literal-only -lh5- payload)."""
    return test_macfbit3.jm_archive(test_macfbit3.lh5_block([("lit", c) for c in fork]), len(fork))


def appledouble(fork):
    return inputfx.appledouble(fork)


def macbinary(fork):
    return inputfx.macbinary(fork)


def suitcase(size=12):
    """A resource fork with a FOND listing @p size (NFNT id 300) and that NFNT (a 5-row strike of two glyphs)."""
    fond = bytearray(52) + struct.pack(">HHHH", 0, size, 0, 300)
    return test_macfbit_svf._fork({("FOND", 1): bytes(fond), ("NFNT", 300): test_macfbit_svf._nfnt(CHARS)})


def nfnt_only():
    return test_macfbit_svf._fork({("NFNT", 300): test_macfbit_svf._nfnt(CHARS)})


def fbit1_raw():
    """The 1.0 `fbit` resource alone (no fork, so no `fdef`): 45 glyph sets of one 16x16 glyph each."""
    sets, data = [], b""
    for i in range(45):
        sets.append(struct.pack(">4H", 4, 0, i * 32, 16) + bytes(4))        # width/4, offset (hi, lo), height, pad
        data += bytes([0xFF, 0xFF]) + bytes(30)
    head = bytearray(0x54)
    head[0:6] = b"\x80\x00fbit"
    return bytes(head) + struct.pack(">H", 45 * 12) + b"".join(sets) + data


def fbit1_fork():
    """A HangulTalk 1.0 font as jamoset.MacFbit reads it: the `fbit` of `fbit1_raw` and an `fdef` 3 resource of zeros
    (empty lookup tables, a degenerate but self-consistent rule). It passes `jamoset.py --layout mac-fbit-45sets
    --check` (composes all 11,172 syllables), which the maker's end-to-end test runs."""
    return test_macfbit3.resource_fork({("fbit", 1): fbit1_raw(), ("fdef", 3): bytes(0x800)})


def hangul_pft():
    """A 40,000-byte 12x24 Hangul font file (`HANGUL24.PFT`)."""
    return bytes(range(256)) * 156 + bytes(64)
