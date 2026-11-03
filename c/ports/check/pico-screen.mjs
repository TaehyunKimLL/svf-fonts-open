// pico-screen.mjs RP2040JS_DIR BOOTROM_BIN NM ELF PROFILE SHOWS OUT
//
// Runs one pico-sdk image of the Pico example (c/ports/pico, -DSVF_PROFILE=PROFILE) on rp2040js with the panel model of
// the profile (panels.mjs) on the emulated I2C or SPI, until the firmware enters svf_port_idle, and writes
// OUT/pico-PROFILE.fb (the panel memory, raw) and OUT/pico-PROFILE.log. screen_ref.py compares the .fb with the
// reference and writes the PNG. SHOWS is the show count the profile must produce (screens.py shows PROFILE); NM is
// arm-none-eabi-nm (the address of svf_port_idle comes from `NM ELF`).
//
// Prints "ok: shows=N transfers=M cycles=C nanos=T" and exits 0, or one line "fail: ..." on stdout and exits 1:
//   fail: bad ELF: ...          the ELF is malformed, or a PT_LOAD does not fit flash or SRAM, or has no svf_port_idle
//   fail: bad bootrom: ...      the boot ROM file is not 16,384 bytes
//   fail: BKPT #N at 0xPC       the firmware hit a BKPT (a fault, panic or _exit under the pico-sdk)
//   fail: emulated time > 10 s  the firmware never reached svf_port_idle
//   fail: waiting with no alarm the core sleeps (WFI/WFE) and nothing will wake it
//   fail: iteration bound       10^9 host iterations without either (a last resort)
//   fail: shows N != SHOWS      the panel saw another number of shows
//   fail: emulator: ...         rp2040js threw
// Exit 2 is a usage error.
// SVF_PICO_ITER_BOUND=N lowers the iteration bound (default and maximum 10^9; anything else is ignored).
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, rmSync, statSync } from 'node:fs';
import path from 'node:path';
import { attachPanel } from './panels.mjs';

const FLASH = 0x10000000, FLASH_SIZE = 2 * 1024 * 1024;
const SRAM = 0x20000000, SRAM_SIZE = 264 * 1024;
const BOOTROM_BYTES = 16384;
const NANOS_PER_CYCLE = 8; // 125 MHz
const NANOS_CAP = 10e9;
// host-side last resort; SVF_PICO_ITER_BOUND lowers it (the test of this exit uses a small one)
const ITERATION_BOUND = (() => {
  const n = Number(process.env.SVF_PICO_ITER_BOUND);
  return Number.isFinite(n) && n > 0 ? Math.min(1e9, n) : 1e9; // it may only be lowered
})();
const ELF_MAX = 16 * 1024 * 1024; // the largest image read (an image is at most 2 MiB of flash and 264 KiB of SRAM)
const LOG_MAX = 1024 * 1024; // bytes of .log

class Fail extends Error {}
const fail = (msg) => { throw new Fail(msg); };

const args = process.argv.slice(2);
if (args.length !== 7) {
  console.error('usage: node pico-screen.mjs RP2040JS_DIR BOOTROM_BIN NM ELF PROFILE SHOWS OUT');
  process.exit(2);
}
const [dir, bootromPath, nm, elfPath, profile, showsArg, out] = args;
const wantShows = Number(showsArg);
if (!['colour', 'grey', 'mono'].includes(profile) || !Number.isInteger(wantShows) || wantShows < 0) {
  console.error('pico-screen: PROFILE is colour, grey or mono and SHOWS a count');
  process.exit(2);
}

function readFile(file, what, prefix, max) {
  let size;
  try {
    size = statSync(file).size;
  } catch (e) {
    return fail(prefix + ': cannot read ' + what + ' ' + file + ': ' + e.code);
  }
  if (max !== undefined && size > max) {
    return fail(prefix + ': ' + what + ' ' + file + ' is larger than ' + max / (1024 * 1024) + ' MiB');
  }
  try {
    return readFileSync(file);
  } catch (e) {
    return fail(prefix + ': cannot read ' + what + ' ' + file + ': ' + e.code);
  }
}

// Every header field and every PT_LOAD is checked before anything is copied; arithmetic is in Numbers (the u32 sums
// cannot overflow a double) with explicit <= 0xFFFFFFFF checks.
function loadSegments(elf) {
  const bad = (m) => fail('bad ELF: ' + m);
  if (elf.length < 52) bad('shorter than the 52-byte header');
  if (elf.readUInt32BE(0) !== 0x7f454c46) bad('no ELF magic');
  if (elf[4] !== 1) bad('not a 32-bit ELF (class ' + elf[4] + ')');
  if (elf[5] !== 1) bad('not little-endian (data ' + elf[5] + ')');
  const machine = elf.readUInt16LE(18);
  if (machine !== 40) bad('e_machine ' + machine + ' is not ARM (40)');
  const phoff = elf.readUInt32LE(28), phentsize = elf.readUInt16LE(42), phnum = elf.readUInt16LE(44);
  if (phnum > 0 && phentsize < 32) bad('e_phentsize ' + phentsize + ' < 32');
  if (phoff + phnum * phentsize > 0xFFFFFFFF) bad('program header table overflows 32 bits');
  if (phoff + phnum * phentsize > elf.length) bad('program headers end past the file');
  const segs = [];
  for (let i = 0; i < phnum; i++) {
    const ph = phoff + i * phentsize;
    if (elf.readUInt32LE(ph) !== 1) continue; // PT_LOAD only
    const off = elf.readUInt32LE(ph + 4), paddr = elf.readUInt32LE(ph + 12), filesz = elf.readUInt32LE(ph + 16);
    if (filesz === 0) continue;
    if (off + filesz > 0xFFFFFFFF || paddr + filesz > 0xFFFFFFFF) bad('PT_LOAD ' + i + ' overflows 32 bits');
    if (off + filesz > elf.length) bad('PT_LOAD ' + i + ' data ends past the file');
    const inFlash = paddr >= FLASH && paddr + filesz <= FLASH + FLASH_SIZE;
    const inSram = paddr >= SRAM && paddr + filesz <= SRAM + SRAM_SIZE;
    if (!inFlash && !inSram) {
      bad('PT_LOAD ' + i + ' at 0x' + paddr.toString(16) + ' + ' + filesz + ' is outside flash and SRAM');
    }
    segs.push({ bytes: elf.subarray(off, off + filesz), paddr, inFlash });
  }
  if (segs.length === 0) bad('no PT_LOAD segment');
  return segs;
}

function bootromWords(file) {
  const raw = readFile(file, 'boot ROM', 'bad bootrom');
  if (raw.length !== BOOTROM_BYTES) fail('bad bootrom: ' + file + ' is ' + raw.length + ' bytes, not ' + BOOTROM_BYTES);
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  const words = new Uint32Array(BOOTROM_BYTES / 4);
  for (let i = 0; i < words.length; i++) words[i] = view.getUint32(i * 4, true);
  return words;
}

function idleAddress() {
  let text;
  try {
    text = execFileSync(nm, [elfPath], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  } catch (e) {
    return fail('bad ELF: ' + nm + ' failed on ' + elfPath + ': ' + (e.message || e).split('\n')[0]);
  }
  for (const line of text.split('\n')) {
    const m = /^([0-9a-fA-F]+)\s+[Tt]\s+svf_port_idle$/.exec(line.trim());
    if (m) return parseInt(m[1], 16) & ~1; // a Thumb function symbol: bit 0 is the mode, not the address
  }
  return fail('bad ELF: no svf_port_idle function in ' + elfPath);
}

async function main() {
  const base = path.join(out, 'pico-' + profile);
  mkdirSync(out, { recursive: true });
  rmSync(base + '.fb', { force: true }); // a failed run must not leave an earlier run's frame for the compare
  rmSync(base + '.log', { force: true });

  const segs = loadSegments(readFile(elfPath, 'ELF', 'bad ELF', ELF_MAX));
  const words = bootromWords(bootromPath);
  const idle = idleAddress();

  const require = createRequire(path.join(path.resolve(dir), 'node_modules', 'x.js'));
  const rp = require('rp2040js');
  const mcu = new rp.RP2040();
  const clock = mcu.clock;
  const warnings = [];
  mcu.logger = {
    debug() {}, info() {},
    warn: (c, m) => warnings.length < 100 && warnings.push('warn ' + c + ': ' + m),
    error: (c, m) => warnings.length < 100 && warnings.push('error ' + c + ': ' + m),
  };
  mcu.loadBootrom(words); // first: loading the ROM resets the chip and fills flash with 0xFF
  for (const s of segs) {
    if (s.inFlash) mcu.flash.set(s.bytes, s.paddr - FLASH);
    else mcu.sram.set(s.bytes, s.paddr - SRAM);
  }
  mcu.onBreak = (code) => fail('BKPT #' + code + ' at 0x' + mcu.core.PC.toString(16));
  mcu.core.PC = FLASH; // boot2 at the start of flash
  const panel = attachPanel(profile, mcu, rp);

  let iterations = 0;
  // the panel keeps its own capped log; the emulator warnings are few (kept to 100 lines); the file stops at LOG_MAX
  const writeLog = (tail) => {
    let text = ['iteration bound ' + ITERATION_BOUND, ...panel.log, ...panel.others.flatMap((m) => m.log), ...warnings, tail].join('\n') + '\n';
    if (text.length > LOG_MAX) text = text.slice(0, LOG_MAX) + '\nlog truncated\n' + tail + '\n';
    writeFileSync(base + '.log', text);
  };
  try {
    for (;;) {
      if (mcu.core.PC === idle) break;
      if (++iterations > ITERATION_BOUND) fail('iteration bound');
      if (clock.nanos > NANOS_CAP) fail('emulated time > 10 s');
      if (mcu.core.waiting) {
        const t = clock.nanosToNextAlarm;
        if (!t) fail('waiting with no alarm');
        clock.tick(t);
      } else {
        clock.tick(mcu.core.executeInstruction() * NANOS_PER_CYCLE);
      }
    }
    if (panel.shows !== wantShows) fail('shows ' + panel.shows + ' != ' + wantShows);
  } catch (e) {
    if (!(e instanceof Fail)) e = new Fail('emulator: ' + (e && e.message || e)); // an rp2040js throw mid-instruction
    writeLog('fail: ' + e.message);
    throw e;
  }
  const nanos = clock.nanos, cycles = mcu.core.cycles;
  writeFileSync(base + '.fb', panel.memory);
  writeLog('ok: shows=' + panel.shows + ' transfers=' + panel.transfers + ' cycles=' + cycles + ' nanos=' + nanos);
  console.log('ok: shows=' + panel.shows + ' transfers=' + panel.transfers + ' cycles=' + cycles + ' nanos=' + nanos);
}

main().catch((e) => {
  if (e instanceof Fail) {
    console.log('fail: ' + e.message);
    process.exit(1);
  }
  throw e;
});
