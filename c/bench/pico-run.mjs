// pico-run.mjs RP2040JS_DIR ELF [NM] - runs a c/bench/bench.c build (-DBENCH_PICO) on rp2040js's RP2040 core and prints
// one line a case: "case=NAME iters=N cycles=C per_iter_cycles=P insns=I per_iter_insns=Q sum=S". I counts the
// mcu.step() calls strictly between a BKPT #1 and the next BKPT #2 (neither BKPT itself), the same with and without a
// profile; a case may have several such intervals (start/stop pairs), whose cycles and instructions add up until the
// report (BKPT #3). The cycles are those of the same steps, so they exclude the two BKPT instructions too (cycles
// and insns cover the same instructions; before 9234022, 2026-10-21, the cycles included one BKPT cycle an interval).
//
// The ELF's loadable segments are copied to their addresses (flash at 0x10000000, SRAM at 0x20000000; bss is the
// SRAM's zero fill), SP is set to the top of SRAM and the core starts at the entry point: no boot ROM, no boot2, no
// clocks set up. The program marks each case with BKPT #1 (start), #2 (stop), #3 (report: r0 the name, r1 iterations,
// r2 the checksum) and ends with BKPT #4 (r0 the exit code); the cycles are rp2040js's per-instruction count
// (core.cycles), summed over the steps counted for insns. rp2040js charges every memory access the same, flash included: XIP cache
// misses and flash wait states are not modelled.
//
// NM, the output of `nm -S --size-sort ELF` (or any "ADDR SIZE TYPE NAME" lines), adds a profile: after each case,
// one line a function with its share of the case's cycles ("  fn=NAME cycles=C pct=P"), the function being the
// symbol whose [ADDR, ADDR + SIZE) holds the PC of each instruction.
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const [dir, elfPath, nmPath] = process.argv.slice(2);
if (!dir || !elfPath) {
  console.error('usage: node pico-run.mjs RP2040JS_DIR ELF [NM]');
  process.exit(2);
}
const require = createRequire(path.join(path.resolve(dir), 'node_modules', 'x.js'));
const { RP2040 } = require('rp2040js');

const FLASH = 0x10000000, SRAM = 0x20000000, SRAM_TOP = 0x20042000;
const elf = readFileSync(elfPath);
if (elf.readUInt32BE(0) !== 0x7f454c46 || elf[4] !== 1 || elf[5] !== 1) throw new Error('not a 32-bit LE ELF');
const entry = elf.readUInt32LE(24), phoff = elf.readUInt32LE(28);
const phentsize = elf.readUInt16LE(42), phnum = elf.readUInt16LE(44);

const mcu = new RP2040();
const say = (c, m) => console.error(`${c}: ${m}`);
mcu.logger = { debug() {}, info() {}, warn: say, error: say };
for (let i = 0; i < phnum; i++) {
  const ph = phoff + i * phentsize;
  if (elf.readUInt32LE(ph) !== 1 /* PT_LOAD */) continue;
  const off = elf.readUInt32LE(ph + 4), vaddr = elf.readUInt32LE(ph + 8), filesz = elf.readUInt32LE(ph + 16);
  const bytes = elf.subarray(off, off + filesz);
  if (vaddr >= SRAM && vaddr + filesz <= SRAM_TOP) mcu.sram.set(bytes, vaddr - SRAM);
  else if (vaddr >= FLASH && vaddr + filesz <= FLASH + mcu.flash.length) mcu.flash.set(bytes, vaddr - FLASH);
  else if (filesz) throw new Error(`segment at 0x${vaddr.toString(16)} outside flash and SRAM`);
}
const core = mcu.core;
core.SP = SRAM_TOP;
core.PC = entry & ~1;

// The profile: function ranges sorted by address, cycles a function between start and stop.
const fns = [];
if (nmPath) {
  for (const line of readFileSync(nmPath, 'utf8').split('\n')) {
    const m = /^([0-9a-f]+) ([0-9a-f]+) [tTwW] (\S+)$/.exec(line.trim());
    if (m) fns.push({ lo: parseInt(m[1], 16) & ~1, hi: (parseInt(m[1], 16) & ~1) + parseInt(m[2], 16), name: m[3] });
  }
  fns.sort((a, b) => a.lo - b.lo);
}
const fnOf = (pc) => {
  let lo = 0, hi = fns.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (pc < fns[mid].lo) hi = mid - 1;
    else if (pc >= fns[mid].hi) lo = mid + 1;
    else return fns[mid].name;
  }
  return '?';
};
let timing = false, prof = new Map();

const readStr = (a) => {
  let s = '';
  for (let c; (c = mcu.readUint8(a++)) !== 0 && s.length < 64; ) s += String.fromCharCode(c);
  return s;
};
let exit = null;
let cycles = 0, insns = 0; // of the case so far: the steps of the intervals
let seg = 0, segc = 0; // steps and cycles of the interval now open
mcu.onBreak = (code) => {
  const r = core.registers;
  if (code === 1) {
    seg = segc = 0;
    timing = true;
  } else if (code === 2) {
    cycles += segc;
    insns += seg;
    timing = false;
  } else if (code === 3) {
    const iters = r[1], sum = (r[2] >>> 0).toString(16).padStart(8, '0');
    console.log(`case=${readStr(r[0])} iters=${iters} cycles=${cycles} per_iter_cycles=${(cycles / iters).toFixed(1)} ` +
      `insns=${insns} per_iter_insns=${(insns / iters).toFixed(1)} sum=${sum}`);
    for (const [name, c] of [...prof].sort((a, b) => b[1] - a[1]))
      if (c * 100 >= cycles) console.log(`  fn=${name} cycles=${c} pct=${(c * 100 / cycles).toFixed(1)}`);
    cycles = insns = 0;
    prof = new Map();
  } else if (code === 4) exit = r[0] | 0;
  else throw new Error(`BKPT #${code} at 0x${core.PC.toString(16)}`);
};
const LIMIT = 4e9; // cycles: a run that never ends is an error
while (exit === null) {
  // A step counts when the interval is open before it and still open after it: the step that executes BKPT #1 opens
  // it (not counted) and the one that executes BKPT #2 closes it (not counted).
  const open = timing, pc = core.PC, c0 = core.cycles;
  mcu.step();
  if (open && timing) {
    ++seg;
    segc += core.cycles - c0;
    if (fns.length) {
      const name = fnOf(pc);
      prof.set(name, (prof.get(name) || 0) + core.cycles - c0);
    }
  }
  if (core.cycles > LIMIT) throw new Error(`no end after ${LIMIT} cycles (PC 0x${core.PC.toString(16)})`);
}
console.log(`end=${exit} total_cycles=${core.cycles}`);
process.exit(exit === 0 ? 0 : 1);
