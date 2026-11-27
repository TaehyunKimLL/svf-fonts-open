#!/usr/bin/env python3
"""Read the syllable layout of a Korean MSX1 Hangul ROM (모아쓰기 mode) off the running machine, in openMSX.

  msx1_harvest.py MACHINE PREFIX (--emu DIR | --openmsx BIN) [--first N] [--count N] [--timeout 600] [--script-only]

The script writes PREFIX.tcl (an openMSX script) and PREFIX.index (the syllables, one hex code point a line), then runs
`timeout T xvfb-run -a openmsx -machine MACHINE -script PREFIX.tcl`. Inside the emulator the Tcl script types
`poke -851,0` (모아쓰기) and a BASIC program, writes 77 syllables at a time into RAM at C000h (a length byte and the
jamo bytes each), raises a flag at BFFEh, waits for the program's flag at BFFFh and appends the SCREEN 1 name table
(VRAM 1800h, 768 bytes) to PREFIX.names; it writes the pattern table (VRAM 0, 2,048 bytes) to PREFIX.patterns once,
and at the end a raw screenshot of the last screen to PREFIX.png. `msxfont.py msx1-verify PREFIX --bios BIOS` then
checks the layout rule against every syllable.

--emu DIR     an openMSX unpacked without installing it (a Debian package unpacked with `dpkg -x` into DIR/root, the
              system ROMs in DIR/userdata/share/systemroms): sets HOME=DIR/home, LD_LIBRARY_PATH, OPENMSX_SYSTEM_DATA
              and OPENMSX_USER_DATA for that tree.
--openmsx BIN an installed openMSX (its own data and system ROM folders).
--script-only write PREFIX.tcl and PREFIX.index and stop.

No ROM data is in this script; the machine's ROMs are run only inside the emulator. PREFIX must lie outside the
repository and hold no space or Tcl special character.
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PER = 77                      # syllables a screen: 11 rows of 7 slots, each 4 columns wide and 2 rows tall
ALL = list(range(0xAC00, 0xD7A4))

# jamo bytes the Hangul ROM stores for a syllable (found by typing 2-set keys into a REM line and reading RAM):
# initial 0x86 + L, the vowel cells (a compound vowel is two), a final as its consonant cells (a double final is two)
VOWEL_BYTES = [[0x99], [0x9A], [0x9B], [0x9C], [0x9D], [0x9E], [0x9F], [0xA0], [0xA1], [0xA1, 0x99], [0xA1, 0x9A],
               [0xA1, 0xA6], [0xA2], [0xA3], [0xA3, 0x9D], [0xA3, 0x9E], [0xA3, 0xA6], [0xA4], [0xA5], [0xA5, 0xA6],
               [0xA6]]
# T 1..27 as consonant numbers in initial order (ㄱ0 ㄲ1 ㄴ2 ㄷ3 ㄹ5 ㅁ6 ㅂ7 ㅅ9 ㅆ10 ㅇ11 ㅈ12 ㅊ14 ㅋ15 ㅌ16 ㅍ17 ㅎ18)
FINALS = [(), (0,), (1,), (0, 9), (2,), (2, 12), (2, 18), (3,), (5,), (5, 0), (5, 6), (5, 7), (5, 9), (5, 16), (5, 17),
          (5, 18), (6,), (7,), (7, 9), (9,), (10,), (11,), (12,), (14,), (15,), (16,), (17,), (18,)]

# BASIC: wait for BFFEh, clear both flags, print the 77 syllables at C000h at their slots, set BFFFh, repeat.
# The text window starts 2 columns in, so a 32-column row holds 7 slots of 4 columns.
PROGRAM = [
    "10 defint a-z",
    "20 if peek(&hbffe)=0 then 20",
    "30 poke &hbffe,0:poke &hbfff,0:cls:a=&hc000",
    "40 for k=0 to 76",
    "50 locate (k mod 7)*4,(k\\7)*2",
    "60 n=peek(a):a=a+1",
    "70 for j=1 to n:print chr$(peek(a));:a=a+1:next",
    "80 print \" \";",
    "90 next",
    "100 poke &hbfff,1",
    "110 goto 20",
]


class HarvestError(Exception):
    pass


def jamo_bytes(cp):
    if not 0xAC00 <= cp <= 0xD7A3:
        raise HarvestError(f"U+{cp:04X} is not a Hangul syllable")
    s = cp - 0xAC00
    return [0x86 + s // 588] + VOWEL_BYTES[s % 588 // 28] + [0x86 + c for c in FINALS[s % 28]]


def batches(cps):
    """The syllables in screens of PER; the last screen is padded with copies of its last syllable, since the
    program always prints PER (without the padding it would read the previous screen's stale bytes)."""
    if not cps:
        raise HarvestError("no syllable")
    out = [list(cps[i:i + PER]) for i in range(0, len(cps), PER)]
    out[-1] += [out[-1][-1]] * (PER - len(out[-1]))
    return out


def blob(batch):
    """The RAM image of one screen: a length byte and the jamo bytes of each syllable."""
    d = bytearray()
    for cp in batch:
        j = jamo_bytes(cp)
        d.append(len(j))
        d += bytes(j)
    return bytes(d)


def tcl_quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("[", "\\[") + '"'


def type_cmd(line):
    """An openMSX `type` command for one BASIC line and RETURN."""
    return "type " + tcl_quote(line)[:-1] + '\\r"'


def tcl_script(prefix, cps, boot=10.0):
    """The openMSX Tcl script of a harvest of @p cps into files PREFIX.names / .patterns / .png."""
    blobs = [blob(b).hex() for b in batches(cps)]
    t = ["set renderer SDL",
         "set throttle off",       # emulated time as fast as the host runs it; no frames are drawn meanwhile
         "set blobs {%s}" % " ".join(blobs),
         "set names %s" % tcl_quote(prefix + ".names"),
         "set pat %s" % tcl_quote(prefix + ".patterns"),
         "set shot %s" % tcl_quote(prefix + ".png"),
         "close [open $names wb]",
         'proc rd {a} { return [debug read "Main RAM" $a] }',
         "proc batch {i} {",
         " global blobs shot",
         " if {$i >= [llength $blobs]} { set ::throttle on; after time 3 { screenshot -raw -doublesize $::shot; exit }; return }",
         ' debug write_block "Main RAM" 0xC000 [binary format H* [lindex $blobs $i]]',
         ' debug write "Main RAM" 0xBFFF 0',
         ' debug write "Main RAM" 0xBFFE 1',
         " waitdone $i 0 }",
         "proc waitdone {i n} {",
         " if {[rd 0xBFFF] == 1} { after time 0.5 [list dumpit $i] } elseif {$n > 4000} { exit 1 } else {",
         "  after time 0.5 [list waitdone $i [expr {$n + 1}]] } }",
         "proc dumpit {i} {",
         " global names",
         " set f [open $names ab]; puts -nonewline $f [debug read_block VRAM 0x1800 768]; close $f",
         " batch [expr {$i + 1}] }"]
    at = boot
    steps = [(at, type_cmd("poke -851,0"))]
    at += 1.5
    for line in PROGRAM:
        steps.append((at, type_cmd(line)))
        at += 0.12 * len(line) + 1.5           # typing takes emulated time; wait until the line is in
    steps.append((at, type_cmd("run")))
    at += 3
    steps.append((at, "set f [open $pat wb]; puts -nonewline $f [debug read_block VRAM 0 2048]; close $f; batch 0"))
    t += ["after time %.2f { %s }" % s for s in steps]
    return "\n".join(t) + "\n"


def check_prefix(prefix):
    prefix = os.path.abspath(prefix)
    if any(c in prefix for c in '{}[]$"\\ \t\n;'):
        raise HarvestError("give a PREFIX path without spaces or Tcl special characters")
    if os.path.commonpath([prefix, ROOT]) == ROOT:
        raise HarvestError(f"PREFIX {prefix} is inside the repository: write the harvest elsewhere")
    if not os.path.isdir(os.path.dirname(prefix)):
        raise HarvestError(f"{os.path.dirname(prefix)}: no such folder")
    return prefix


def command(a, script):
    """(argv, environment) of the emulator run."""
    env = dict(os.environ, SDL_AUDIODRIVER="dummy")
    if a.emu:
        e = os.path.abspath(a.emu)
        binary = os.path.join(e, "root", "usr", "bin", "openmsx")
        env.update(HOME=os.path.join(e, "home"), LD_LIBRARY_PATH=os.path.join(e, "root", "usr", "lib", "x86_64-linux-gnu"),
                   OPENMSX_SYSTEM_DATA=os.path.join(e, "root", "usr", "share", "openmsx"),
                   OPENMSX_USER_DATA=os.path.join(e, "userdata", "share"))
    else:
        binary = a.openmsx
    return ["timeout", str(a.timeout), "xvfb-run", "-a", binary, "-machine", a.machine, "-script", script], env


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("machine", help="openMSX machine name, e.g. Daewoo_DPC-200")
    ap.add_argument("prefix", help="output files PREFIX.tcl / .index / .names / .patterns / .png, outside the repository")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--emu", help="an openMSX unpacked into DIR/root with system ROMs in DIR/userdata/share/systemroms")
    g.add_argument("--openmsx", help="an installed openMSX binary")
    ap.add_argument("--first", type=int, default=0, help="first syllable, 0 = 가")
    ap.add_argument("--count", type=int, default=len(ALL))
    ap.add_argument("--timeout", type=int, default=600, help="seconds before the emulator is stopped (600)")
    ap.add_argument("--script-only", action="store_true")
    a = ap.parse_args(argv)
    try:
        if not 0 <= a.first < len(ALL) or a.count < 1:
            raise HarvestError("--first is 0..11171 and --count 1 or more")
        if not a.script_only and not (a.emu or a.openmsx):
            raise HarvestError("give --emu DIR or --openmsx BIN (or --script-only)")
        prefix = check_prefix(a.prefix)
        cps = ALL[a.first:a.first + a.count]
        with open(prefix + ".tcl", "w", encoding="ascii") as fh:
            fh.write(tcl_script(prefix, cps))
        with open(prefix + ".index", "w", encoding="ascii") as fh:
            fh.write("".join(f"{cp:04X}\n" for cp in cps))
        n = len(batches(cps))
        print(f"wrote {prefix}.tcl and {prefix}.index: {len(cps)} syllables in {n} screens")
        if a.script_only:
            return
        argv_, env = command(a, prefix + ".tcl")
        r = subprocess.run(argv_, env=env, capture_output=True, text=True)
        got = os.path.getsize(prefix + ".names") // 768 if os.path.exists(prefix + ".names") else 0
        print(f"openMSX exit {r.returncode}; screens dumped {got} of {n}"
              + (f"; screenshot {prefix}.png" if os.path.exists(prefix + ".png") else ""))
        if got != n:
            tail = (r.stdout + r.stderr).strip().splitlines()[-8:]
            raise HarvestError("the harvest is incomplete" + ("" if r.returncode != 124 else " (timeout)") +
                               ("\n  " + "\n  ".join(tail) if tail else ""))
    except (HarvestError, OSError) as e:
        print(f"msx1_harvest.py: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
