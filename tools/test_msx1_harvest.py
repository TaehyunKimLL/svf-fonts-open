#!/usr/bin/env python3
"""Tests of tools/msx1_harvest.py without the emulator: the stored jamo bytes, the screens and their padding, the
BASIC program typed and the Tcl script, the argument checks.
  python3 -m unittest tools.test_msx1_harvest
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import msx1_harvest as mh  # noqa: E402
import msxfont  # noqa: E402


class Pure(unittest.TestCase):
    def test_jamo_bytes(self):
        self.assertEqual(mh.jamo_bytes(0xAC00), [0x86, 0x99])                 # 가
        self.assertEqual(mh.jamo_bytes(0xAC03), [0x86, 0x99, 0x86, 0x8F])     # 갃: ㄳ = ㄱ ㅅ
        self.assertEqual(mh.jamo_bytes(0xACFC), [0x86, 0xA1, 0x99])           # 과: ㅘ = ㅗ ㅏ
        self.assertEqual(mh.jamo_bytes(0xC758), [0x86 + 11, 0xA5, 0xA6])      # 의
        self.assertEqual(mh.jamo_bytes(0xD7A3), [0x86 + 18, 0xA6, 0x86 + 18])  # 힣
        with self.assertRaises(mh.HarvestError):
            mh.jamo_bytes(0x41)
        # the finals are the consonant cells msxfont's layout rule draws below the syllable
        for cp in range(0xAC00, 0xAC00 + 28):
            fin = mh.jamo_bytes(cp)[2:]
            self.assertEqual([c for c in msxfont.layout(cp)[1] if c not in (msxfont.BLANK, 0x0C)], fin, hex(cp))

    def test_batches_pad_the_last_screen(self):
        b = mh.batches(mh.ALL)
        self.assertEqual(len(b), 146)                                         # 11,172 = 145 x 77 + 7
        self.assertTrue(all(len(x) == 77 for x in b))
        self.assertEqual(b[-1][:7], list(range(0xD79D, 0xD7A4)))
        self.assertEqual(b[-1][7:], [0xD7A3] * 70)
        self.assertEqual(sum(b, [])[:11172], mh.ALL)
        self.assertEqual(mh.batches([0xAC00] * 77), [[0xAC00] * 77])          # a full last screen gets no padding
        with self.assertRaises(mh.HarvestError):
            mh.batches([])

    def test_blob(self):
        self.assertEqual(mh.blob([0xAC00, 0xAC03]), bytes([2, 0x86, 0x99, 4, 0x86, 0x99, 0x86, 0x8F]))
        # the largest screen still fits below the BASIC work area (C000h .. about F380h)
        self.assertLess(max(len(mh.blob(b)) for b in mh.batches(mh.ALL)), 0x3380)

    def test_program_and_script(self):
        self.assertEqual(len(mh.PROGRAM), 11)
        self.assertIn("40 for k=0 to 76", mh.PROGRAM)                        # PER syllables a screen
        self.assertEqual(mh.PER, 77)
        t = mh.tcl_script("/x/h", mh.ALL[:100])
        self.assertTrue(t.startswith("set renderer SDL\nset throttle off\n"))
        blobs = re.search(r"set blobs \{([0-9a-f ]*)\}", t).group(1).split()
        self.assertEqual([bytes.fromhex(x) for x in blobs], [mh.blob(b) for b in mh.batches(mh.ALL[:100])])
        typed = re.findall(r'\{ type "(.*)\\r" \}', t)
        unq = [s.replace('\\"', '"').replace("\\$", "$").replace("\\[", "[").replace("\\\\", "\\") for s in typed]
        self.assertEqual(unq, ["poke -851,0"] + mh.PROGRAM + ["run"])
        times = [float(x) for x in re.findall(r"after time ([0-9.]+) \{ type", t)]
        self.assertEqual(times, sorted(times))
        for want in ("debug read_block VRAM 0x1800 768", "debug read_block VRAM 0 2048", 'debug write_block "Main RAM" 0xC000',
                     "screenshot -raw -doublesize", 'set names "/x/h.names"'):
            self.assertIn(want, t)

    def test_command(self):
        class A:
            emu, openmsx, machine, timeout = "/e", None, "Daewoo_DPC-200", 600
        argv, env = mh.command(A, "/x/h.tcl")
        self.assertEqual(argv, ["timeout", "600", "xvfb-run", "-a", "/e/root/usr/bin/openmsx", "-machine",
                                "Daewoo_DPC-200", "-script", "/x/h.tcl"])
        self.assertEqual(env["OPENMSX_USER_DATA"], "/e/userdata/share")
        self.assertEqual(env["SDL_AUDIODRIVER"], "dummy")

    def test_script_only_and_refusals(self):
        tool = os.path.join(HERE, "msx1_harvest.py")
        with tempfile.TemporaryDirectory() as d:
            pre = os.path.join(d, "h")
            r = subprocess.run([sys.executable, "-I", tool, "Daewoo_DPC-200", pre, "--script-only"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("11172 syllables in 146 screens", r.stdout)
            with open(pre + ".index") as fh:
                self.assertEqual(fh.read().split(), ["%04X" % c for c in mh.ALL])
            for args, msg in (([os.path.join(HERE, "h"), "--script-only"], "inside the repository"),
                              ([os.path.join(d, "a b"), "--script-only"], "without spaces"),
                              ([pre], "give --emu DIR or --openmsx BIN"),
                              ([pre, "--script-only", "--count", "0"], "--count 1 or more")):
                r = subprocess.run([sys.executable, "-I", tool, "Daewoo_DPC-200"] + args, capture_output=True, text=True)
                self.assertEqual(r.returncode, 1)
                self.assertIn(msg, r.stderr)


if __name__ == "__main__":
    unittest.main()
