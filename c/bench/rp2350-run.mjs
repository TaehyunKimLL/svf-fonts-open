// rp2350-run.mjs RP2350JS_DIR CORE ELF NM - runs a c/bench/bench.c build (-DBENCH_RP2350) as a pico-sdk `pico2` image on
// rp2350js's RP2350 (CORE riscv: Hazard3, or arm: Cortex-M33) and prints one line a case:
//   case=NAME iters=N cycles=C per_iter_cycles=P insns=I per_iter_insns=Q sum=S
// (the line of pico-run.mjs), then "end=CODE total_cycles=T". Calibration intervals print "cal=NAME cycles=C insns=I".
// NM is a file of `nm` output ("ADDR TYPE NAME" lines) of the ELF.
//
// How a count is taken. The program has no clock. It calls four marker functions (bench.c, BENCH_RP2350):
// bench_mark_start / bench_mark_stop open and close an interval, bench_mark_report (a0-a2 / r0-r2: the name, iterations,
// checksum) ends a case, bench_mark_end (a0 / r0: the exit code) ends the run. The loop below watches core 0's PC before
// every mcu.step(): when it is the first instruction of a marker function, that function is about to run. The cycles of
// an interval are core 0's `cycles` when it is about to execute bench_mark_stop's first instruction minus the same at
// bench_mark_start's, so the start function's body and return and the call into stop are in the count: a constant per
// interval (cal=empty shows it: 7-8 cycles Hazard3, 11-12 Cortex-M33). The instructions are the mcu.step() calls in
// between (one core-0 instruction each). A case may have several intervals; they add up until the report. An interval
// that is closed twice or never, a report or the end inside one, a core-0 wait inside one and an entry to a fault
// handler end the run with "fail: ..." (exit 1): nothing is counted from a broken run. A run that passes 4e9 cycles fails.
//
// What is run. The ELF's PT_LOAD segments are copied to their physical addresses in flash (0x10000000) or SRAM
// (0x20000000); the chip is reset and boots through the A2 boot ROM bundled in rp2350js, which finds the image's
// IMAGE_DEF in flash and starts the SDK's crt0 and runtime init (clocks to 150 MHz, which rp2350js ignores) before main.
// Core 1 stays parked by the boot ROM (the bench never launches it); its cycles are not counted.
//
// What rp2350js does not model (its README at af0114c and the source): "somewhat correct instruction cycle counts" (its
// own words; Hazard3: 1 cycle an ALU op, a one-entry backward-branch predictor, +1 for a misaligned 32-bit fetch after a
// jump, 3 for an AMO, 17 for a divide; its Cortex-M33 table is its own and not checked here against Arm's); every memory
// access costs the same: no XIP flash or XIP cache timing (code and faces are in flash, as on a board), no QMI, no bus
// contention or APB wait states, no Hazard3 dependent-register (load-use) penalty; timer and system interrupts and
// exceptions are listed as missing (the bench uses none; a fault entry ends the run); clk_sys stays at 125 MHz whatever
// the SDK programs, so a time read from the emulated chip's timers would be wrong (this runner reads none; the rows
// convert cycles at 150 MHz, the SDK's clock). The counts are an estimate that could be off in either direction: rp2350js's timing tables are not checked against the chip.
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const [dir, coreArg, elfPath, nmPath] = process.argv.slice(2);
if (!dir || !coreArg || !elfPath || !nmPath || process.argv.length !== 6 || (coreArg !== 'riscv' && coreArg !== 'arm')) {
  console.error('usage: node rp2350-run.mjs RP2350JS_DIR riscv|arm ELF NM');
  process.exit(2);
}
const usage = (m) => {
  console.log(m);
  process.exit(2);
};
const require = createRequire(path.join(path.resolve(dir), 'x.js'));
const { RP2350 } = require(path.resolve(dir, 'dist/cjs/index.js'));

const FLASH = 0x10000000, SRAM = 0x20000000;
const LIMIT = 4e9; // cycles: a run that never ends is an error

// The ELF: 32-bit little-endian, the right machine, PT_LOAD segments with data to their physical addresses.
const elf = readFileSync(elfPath);
if (elf.length < 52 || elf.readUInt32BE(0) !== 0x7f454c46 || elf[4] !== 1 || elf[5] !== 1) usage('not a 32-bit LE ELF');
const machine = elf.readUInt16LE(18);
if (machine !== (coreArg === 'riscv' ? 243 : 40)) usage(`e_machine ${machine} for CORE ${coreArg}`);
const phoff = elf.readUInt32LE(28), phentsize = elf.readUInt16LE(42), phnum = elf.readUInt16LE(44);
if (phentsize < 32 || phoff + phnum * phentsize > elf.length) usage('truncated ELF: program headers beyond the end of the file');
const segments = [];
for (let i = 0; i < phnum; i++) {
  const ph = phoff + i * phentsize;
  if (elf.readUInt32LE(ph) !== 1 /* PT_LOAD */) continue;
  const off = elf.readUInt32LE(ph + 4), paddr = elf.readUInt32LE(ph + 12), filesz = elf.readUInt32LE(ph + 16);
  if (filesz === 0) continue;
  if (off + filesz > elf.length) usage(`truncated ELF: segment at 0x${paddr.toString(16)} beyond the end of the file`);
  segments.push({ bytes: elf.subarray(off, off + filesz), paddr });
}

// The symbols: the four markers (required) and the fault entries that exist.
const syms = new Map();
for (const line of readFileSync(nmPath, 'utf8').split('\n')) {
  const m = /^([0-9a-fA-F]+)\s+\S\s+(\S+)$/.exec(line.trim());
  if (m) syms.set(m[2], parseInt(m[1], 16) & ~1);
}
const marks = {};
for (const n of ['bench_mark_start', 'bench_mark_stop', 'bench_mark_report', 'bench_mark_end']) {
  if (!syms.has(n)) usage(`no ${n} in ${nmPath}`);
  marks[n] = syms.get(n) >>> 0;
}
const faultNames = ['isr_hardfault', 'isr_nmi', 'isr_svcall', '__unhandled_user_irq', 'panic', '_exit',
  'isr_riscv_machine_exception', 'hard_assertion_failure'];
const faults = new Map();
for (const n of faultNames) if (syms.has(n)) faults.set(syms.get(n) >>> 0, n);

const mcu = new RP2350({ coreArch: coreArg });
const say = (c, m) => console.error(`${c}: ${m}`);
mcu.logger = { debug() {}, info() {}, warn: say, error: say };
for (const s of segments) {
  if (s.paddr >= FLASH && s.paddr + s.bytes.length <= FLASH + mcu.flash.length) mcu.flash.set(s.bytes, s.paddr - FLASH);
  else if (s.paddr >= SRAM && s.paddr + s.bytes.length <= SRAM + mcu.sram.length) mcu.sram.set(s.bytes, s.paddr - SRAM);
  else usage(`segment at 0x${s.paddr.toString(16)} outside flash and SRAM`);
}
if (mcu.invalidateDecodeCache) mcu.invalidateDecodeCache();
mcu.reset();
const core0 = mcu.core[0];
// Any break the Cortex-M33 core reports (BKPT and UDF both call onBreak) ends the run; the RISC-V core takes an ebreak as a
// trap to the machine exception handler (a fault entry below) and throws on an illegal instruction (caught below).
for (const c of mcu.core) c.onBreak = (code) => fail(`BKPT/UDF #${code} on core ${c === core0 ? 0 : 1}`);
if ((core0.PC >>> 0) >= 0x8000) {
  console.log(`fail: core 0 starts at 0x${(core0.PC >>> 0).toString(16)}, not in the boot ROM`);
  process.exit(1);
}

// A case name: NUL-terminated within 64 bytes (null if not), the check of the caller is /^[a-z0-9_]+$/.
const readStr = (a) => {
  let s = '';
  for (let i = 0; i < 64; i++) {
    const c = mcu.readUint8(a++);
    if (c === 0) return s;
    s += String.fromCharCode(c);
  }
  return null;
};
// The arguments of a report: a0-a2 (x10-x12) on Hazard3, r0-r2 on the Cortex-M33.
const arg = coreArg === 'riscv' ? (i) => core0.getRegister(10 + i) >>> 0 : (i) => core0.regs.r[i] >>> 0;

class Fail extends Error {}
const fail = (m) => {
  throw new Fail(m);
};
const where = () => `PC 0x${(core0.PC >>> 0).toString(16)}`;

let steps = 0; // mcu.step() calls so far
let open = false, c0 = 0, s0 = 0; // the interval now open: core 0's cycles and the step count at its start
let cycles = 0, insns = 0; // of the case so far: the closed intervals
let exit = null;
try {
  while (exit === null) {
    const pc = core0.PC >>> 0;
    if (pc === marks.bench_mark_start) {
      if (open) fail('bench_mark_start inside an open interval');
      open = true;
      c0 = core0.cycles;
      s0 = steps;
    } else if (pc === marks.bench_mark_stop) {
      if (!open) fail('bench_mark_stop with no interval open');
      cycles += core0.cycles - c0;
      insns += steps - s0;
      open = false;
    } else if (pc === marks.bench_mark_report) {
      if (open) fail('bench_mark_report inside an open interval');
      const name = readStr(arg(0)), iters = arg(1), sum = arg(2).toString(16).padStart(8, '0');
      if (name === null || !/^[a-z0-9_]+$/.test(name)) fail(`bad case name ${JSON.stringify(name)}`);
      if (iters <= 0) fail(`bad iteration count ${iters} for ${name}`);
      if (name.startsWith('cal_')) console.log(`cal=${name.slice(4)} cycles=${cycles} insns=${insns}`);
      else
        console.log(`case=${name} iters=${iters} cycles=${cycles} per_iter_cycles=${(cycles / iters).toFixed(1)} ` +
          `insns=${insns} per_iter_insns=${(insns / iters).toFixed(1)} sum=${sum}`);
      cycles = insns = 0;
    } else if (pc === marks.bench_mark_end) {
      if (open) fail('bench_mark_end inside an open interval');
      exit = arg(0) | 0;
      break;
    } else {
      const f = faults.get(pc);
      if (f) fail(`entered ${f}`);
    }
    if (core0.cycles > LIMIT) fail(`no end after ${LIMIT} cycles`);
    if (core0.waiting) {
      // The boot ROM and the runtime init may wait (WFE/WFI/h3.block): jump to the next alarm. Inside an interval a wait
      // would put idle cycles into the count: that is an error.
      if (open) fail('core 0 waits inside an open interval');
      const t = mcu.clock.nanosToNextAlarm;
      if (!t || t <= 0) fail('core 0 waits with no alarm');
      mcu.clock.tick(t);
    }
    mcu.step(); // the RISC-V core evaluates its wake-up only inside executeInstruction
    ++steps;
  }
} catch (e) {
  const msg = e instanceof Fail ? `${e.message} (${where()})` : `emulator: ${(e && e.message) || e} (${where()})`;
  console.log(`fail: ${msg}`);
  process.exit(1);
}
console.log(`end=${exit} total_cycles=${core0.cycles}`);
process.exit(exit === 0 ? 0 : 1);
