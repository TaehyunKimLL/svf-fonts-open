#!/usr/bin/env python3
"""check-measurements-md.py [--print] MEASUREMENTS.md [RAW] | --raw PICO_DIR ESP32_DIR [M33_DIR [RP2350_DIR [PICO_V2 PICO_DIV PICO_BASE [PICO_V1]]]] - the numbers of MEASUREMENTS.md that are derived, not measured.

Checks (exit 1 with the reason on any difference, 0 and silence otherwise):
  - every Pico row: cycles, us and insns are what report.awk prints for the run's own per_iter_cycles / per_iter_insns, kept
    in RAW (default c/bench/measurements-raw.txt next to this script, written by --raw from the run directories of
    run-pico.sh, run-esp32.sh, run-m33.sh and run-rp2350.sh: `python3 -I check-measurements-md.py --raw c/build/bench/before/pico
    c/build/bench/before/esp32 c/build/bench/before/m33 c/build/bench/before/rp2350 [c/build/t10/pico-v2 c/build/t10/pico-div c/build/jset1/bench/pico [PICO_V1]]`: the seven-directory form adds the JSET section's v2, reader-alone and BASE Pico runs, the eight-directory form its v1 Pico run (the "v1" column, RAW's picoV1 lines; the current run in the first directory is a different, later one));
  - the cycle columns of "Before -> after JSET v1 + v2" (Pico, per kind and optimisation): BASE, v1, "v2 reader alone" (scratch) and v2
    equal RAW's picoBASE, picoV1, picoDIV and picoV2 lines (picoV1 = the "pico" run of that task, kept when the result tables were re-taken on 2026-10-27, 450b776) (--raw with PICO_V2 PICO_DIV PICO_BASE PICO_V1 as the 5th to 8th directories);
  - every ESP32-C3 / ESP32-S3 / Cortex-M33 (QEMU) / RP2350 Hazard3 / RP2350 Cortex-M33 (rp2350js) row: the same for the counts and
    the us columns (/ 160, / 240, / 150, / 150 and / 150 MHz);
  - the ratio tables between <!-- ratios:begin --> and <!-- ratios:end --> equal what the result tables give.
--print writes that generated block (to paste between the markers). Run by tools/test_c_renderer.py, so by `make -C c check`.
The measured columns themselves (cycles, instructions, checksums) are checked at run time by report.awk and the run scripts."""
import re
import sys

KINDS = ("MONO_PAGE", "GRAY8", "RGB565")
BEGIN, END = "<!-- ratios:begin -->", "<!-- ratios:end -->"


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def exact(raw, key, shown, us, mhz):
    """True if the table figures are what report.awk prints for the run's own per_iter_cycles (the raw file): the cycles
    column %.0f of it and the us column %.2f of it / mhz."""
    if key not in raw:
        return False
    pic = raw[key]
    return "%.0f" % float(pic) == str(shown) and "%.2f" % (float(pic) / mhz) == us


def parse(text, raw):
    errs, pico, esp = [], {}, {}
    sect = kind = None
    jk = jo = None
    njset = 0
    for line in text.split("\n"):
        m = re.match(r"(MONO_PAGE|GRAY8|RGB565) `-(Os|O2)`:$", line)
        if m:
            jk, jo = m.group(1), m.group(2)
            continue
        if jk and line.startswith("| ") and not line.startswith("| case") and not line.startswith("|---"):
            c = cells(line)
            njset += 1
            for col, chip in ((1, "picoBASE"), (2, "picoV1"), (4, "picoDIV"), (5, "picoV2")):
                want = raw.get((chip, jo, jk, c[0]))
                if want is None or "%.0f" % float(want) != c[col]:
                    errs.append("JSET section %s %s %s %s: %s, the raw run gives %s" % (jk, jo, c[0], chip, c[col], want))
            continue
        if line.startswith("#"):
            sect = ("C3" if line.startswith("### ESP32-C3") else "S3" if line.startswith("### ESP32-S3")
                    else "M33" if line.startswith("### Cortex-M33") else "H3" if line.startswith("### RP2350 Hazard3")
                    else "M33R" if line.startswith("### RP2350 Cortex-M33") else None)
            kind = jk = jo = None
            continue
        if line.startswith("| Pico emulated ("):
            c = cells(line)
            m = re.search(r"-(O[s2]); (\w+),", c[0])
            cyc, us, ins = int(c[3]), c[4], c[5]
            if not exact(raw, ("pico", m.group(1), m.group(2), c[1]), cyc, us, 125):
                errs.append("Pico %s %s %s: cycles %d / us %s are not what the raw run gives (%s)" % (m.group(2), m.group(1), c[1], cyc, us, raw.get(("pico", m.group(1), m.group(2), c[1]))))
            pico[(m.group(2), m.group(1), c[1])] = (cyc, int(ins))
            continue
        m = re.match(r"(MONO_PAGE|GRAY8|RGB565|LINE) \(", line)
        if m:
            kind = m.group(1)
            continue
        if sect and kind and line.startswith("| ") and not line.startswith("| case") and not line.startswith("|---"):
            c = cells(line)
            mhz = {"C3": 160, "S3": 240, "M33": 150, "H3": 150, "M33R": 150}[sect]
            for i, o in ((2, "Os"), (3, "O2")):
                n = int(c[i])
                esp[(sect, kind, o, c[0])] = n
                if not exact(raw, (sect, o, kind, c[0]), n, c[i + 2], mhz):
                    errs.append("%s %s %s %s: count %d / us %s are not what the raw run gives (%s)" % (sect, kind, o, c[0], n, c[i + 2], raw.get((sect, o, kind, c[0]))))
    if not njset:
        errs.append("no JSET section cycle rows found (a heading `MONO_PAGE `-Os`:` was reflowed?)")
    return errs, pico, esp


def block(pico, esp):
    out = []
    cases = ("syl_ga", "syl_bwelk", "compose_bwelk", "screen32", "line8", "aa_syl_ga", "aa_syl_bwelk", "aa_line12", "aa_screen10")
    out.append("Pico cycles per iteration against MONO_PAGE (GRAY8 / MONO_PAGE, RGB565 / MONO_PAGE) and RGB565 against GRAY8,"
               " single-kind builds:\n")
    out.append("| case | `-Os` GRAY8 / MONO | `-Os` RGB565 / MONO | `-Os` RGB565 / GRAY8 | `-O2` GRAY8 / MONO | `-O2` RGB565 / MONO | `-O2` RGB565 / GRAY8 |")
    out.append("|---|---:|---:|---:|---:|---:|---:|")
    for cs in cases:
        row = []
        for o in ("Os", "O2"):
            g, r = pico.get(("GRAY8", o, cs)), pico.get(("RGB565", o, cs))
            mo = pico.get(("MONO_PAGE", o, cs))
            row += ["%.2fx" % (g[0] / mo[0]) if g and mo else "-", "%.2fx" % (r[0] / mo[0]) if r and mo else "-",
                    "%.2fx" % (r[0] / g[0]) if r and g else "-"]
        out.append("| %s | %s |" % (cs, " | ".join(row)))
    out.append("")
    out.append("Instructions per iteration, Pico `insns` / C3 and S3 core-0 `ICOUNT` / C3 (counts, not time):\n")
    out.append("| kind | case | `-Os` Pico / C3 | `-Os` S3 / C3 | `-O2` Pico / C3 | `-O2` S3 / C3 |")
    out.append("|---|---|---:|---:|---:|---:|")
    for k in KINDS:
        for cs in cases:
            if ("Os", k, cs) not in {(o, kk, c) for (kk, o, c) in pico}:
                continue
            row = []
            for o in ("Os", "O2"):
                p, c3, s3 = pico[(k, o, cs)][1], esp[("C3", k, o, cs)], esp[("S3", k, o, cs)]
                row += ["%.2fx" % (p / c3), "%.2fx" % (s3 / c3)]
            out.append("| %s | %s | %s |" % (k, cs, " | ".join(row)))
    return "\n".join(out)


def make_raw(pico_dir, esp_dir, m33_dir=None, rp2350_dir=None, v2_dir=None, div_dir=None, base_dir=None, v1_dir=None):
    """The raw lines "chip opt kind case per_iter_cycles per_iter_insns" of the run files (Pico: run-KIND-OPT.txt, ESP32:
    run-CHIP-OPT-KIND.txt, Cortex-M33 under QEMU: run-OPT-KIND.txt with KIND also LINE; RP2350 under rp2350js:
    run-riscv-OPT-KIND.txt as H3 and run-arm-OPT-KIND.txt as M33R, KIND also LINE, with per_iter_insns)."""
    out = []
    for k in KINDS:
        for o in ("Os", "O2"):
            for chip, d, name in (("pico", pico_dir, "run-%s-%s.txt" % (k, o)), ("C3", esp_dir, "run-c3-%s-%s.txt" % (o, k)),
                                  ("S3", esp_dir, "run-s3-%s-%s.txt" % (o, k))):
                for line in open("%s/%s" % (d, name), encoding="utf-8"):
                    m = re.match(r"case=(\S+) .*per_iter_cycles=([\d.]+)(?:.*per_iter_insns=([\d.]+))?", line)
                    if m:
                        out.append("%s %s %s %s %s %s" % (chip, o, k, m.group(1), m.group(2), m.group(3) or "-"))
    for chip, d in (("picoV1", v1_dir), ("picoV2", v2_dir), ("picoDIV", div_dir), ("picoBASE", base_dir)):
        for k in KINDS:
            for o in ("Os", "O2"):
                for line in open("%s/run-%s-%s.txt" % (d, k, o), encoding="utf-8") if d else ():
                    m = re.match(r"case=(\S+) .*per_iter_cycles=([\d.]+)(?:.*per_iter_insns=([\d.]+))?", line)
                    if m:
                        out.append("%s %s %s %s %s %s" % (chip, o, k, m.group(1), m.group(2), m.group(3) or "-"))
    if m33_dir:
        for k in KINDS + ("LINE",):
            for o in ("Os", "O2"):
                for line in open("%s/run-%s-%s.txt" % (m33_dir, o, k), encoding="utf-8"):
                    m = re.match(r"case=(\S+) .*per_iter_cycles=([\d.]+)", line)
                    if m:
                        out.append("M33 %s %s %s %s -" % (o, k, m.group(1), m.group(2)))
    if rp2350_dir:
        for chip, core in (("H3", "riscv"), ("M33R", "arm")):
            for k in KINDS + ("LINE",):
                for o in ("Os", "O2"):
                    for line in open("%s/run-%s-%s-%s.txt" % (rp2350_dir, core, o, k), encoding="utf-8"):
                        m = re.match(r"case=(\S+) .*per_iter_cycles=([\d.]+).*per_iter_insns=([\d.]+)", line)
                        if m:
                            out.append("%s %s %s %s %s %s" % (chip, o, k, m.group(1), m.group(2), m.group(3)))
    return "\n".join(out) + "\n"


def read_raw(path):
    raw, insn = {}, {}
    for line in open(path, encoding="utf-8"):
        f = line.split()
        if len(f) == 6:
            raw[(f[0], f[1], f[2], f[3])] = f[4]
            insn[(f[0], f[1], f[2], f[3])] = f[5]
    return raw, insn


def main(argv):
    if 4 <= len(argv) <= 10 and argv[1] == "--raw":
        sys.stdout.write(make_raw(*argv[2:]))
        return 0
    args = [a for a in argv[1:] if a != "--print"]
    text = open(args[0], encoding="utf-8").read()
    import os
    rawpath = args[1] if len(args) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "measurements-raw.txt")
    raw, insn = read_raw(rawpath)
    errs, pico, esp = parse(text, raw)
    for (k, o, cs), (_, n) in pico.items():
        want = insn.get(("pico", o, k, cs))
        if want is None or str(round(float(want))) != str(n):
            errs.append("Pico %s %s %s: insns %d, the raw run gives %s" % (k, o, cs, n, want))
    gen = block(pico, esp) if pico and esp else ""
    if "--print" in argv:
        print(gen)
        return 0
    if not pico or not esp:
        errs.append("no Pico or ESP32 result rows found")
    if BEGIN not in text or END not in text:
        errs.append("the ratio block markers are missing")
    else:
        have = text.split(BEGIN, 1)[1].split(END, 1)[0].strip("\n")
        if have != gen:
            errs.append("the ratio tables differ from the result tables (python3 -I c/bench/check-measurements-md.py --print c/bench/MEASUREMENTS.md)")
    for e in errs:
        print("MEASUREMENTS.md: " + e)
    return 1 if errs else 0


sys.exit(main(sys.argv))
