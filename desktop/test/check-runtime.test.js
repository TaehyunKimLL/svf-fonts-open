'use strict';
// The release check "runtime": logic of build/check-runtime.mjs over synthetic ELF64 images, plus the real runtimes
// when electron-builder's toolset caches are on this host.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');

// an ELF64 LE image: PT_LOAD over everything, optional PT_INTERP, PT_DYNAMIC with the given DT_NEEDED values, trailing text
function elf({ interp = false, needed = [], text = '' } = {}) {
  const phnum = 2 + (interp ? 1 : 0), phoff = 64, dynoff = phoff + 56 * phnum, dynsz = 16 * (needed.length + 1), body = dynoff + dynsz;
  const buf = Buffer.alloc(body + text.length);
  buf.writeUInt32BE(0x7f454c46, 0); buf[4] = 2; buf[5] = 1; buf[6] = 1;
  buf.writeUInt16LE(3, 16); buf.writeUInt16LE(62, 18);
  buf.writeBigUInt64LE(BigInt(phoff), 0x20); buf.writeUInt16LE(64, 0x34); buf.writeUInt16LE(56, 0x36); buf.writeUInt16LE(phnum, 0x38);
  let p = phoff;
  const ph = (type, off, sz) => { buf.writeUInt32LE(type, p); buf.writeBigUInt64LE(BigInt(off), p + 8); buf.writeBigUInt64LE(BigInt(sz), p + 32); p += 56; };
  ph(1, 0, buf.length);
  if (interp) ph(3, body, 0);
  ph(2, dynoff, dynsz);
  needed.forEach((v, i) => { buf.writeBigInt64LE(1n, dynoff + 16 * i); buf.writeBigUInt64LE(BigInt(v), dynoff + 16 * i + 8); });
  buf.write(text, body, 'latin1');
  return buf;
}

async function load() { return (await import('../build/check-runtime.mjs')).checkRuntime; }

test('a static runtime passes', async () => {
  const r = (await load())(Buffer.concat([elf({ text: 'type2 runtime libfuse3.so.3' }), Buffer.alloc(100, 7)]));
  assert.equal(r.ok, true, r.msg);
});
test('a dynamic loader fails (the old runtime)', async () => {
  const r = (await load())(elf({ interp: true }));
  assert.equal(r.ok, false); assert.match(r.msg, /PT_INTERP/);
});
test('a needed library fails', async () => {
  const r = (await load())(elf({ needed: [1] }));
  assert.equal(r.ok, false); assert.match(r.msg, /needed/);
});
test('the string libfuse.so.2 inside the runtime fails; after it (in the squashfs) does not', async () => {
  const check = await load();
  const bad = check(elf({ text: 'dlopen libfuse.so.2' }));
  assert.equal(bad.ok, false); assert.match(bad.msg, /libfuse\.so\.2/);
  const after = check(Buffer.concat([elf(), Buffer.from('libfuse.so.2 in the payload')]));
  assert.equal(after.ok, true, after.msg);
});
test('not an ELF, truncated and 32-bit inputs fail without throwing', async () => {
  const check = await load();
  assert.equal(check(Buffer.from('#!/bin/sh\n'.repeat(20))).ok, false);
  assert.equal(check(elf().subarray(0, 100)).ok, false);
  const e32 = elf(); e32[4] = 1;
  assert.equal(check(e32).ok, false);
});
test('the CLI prints one ok/FAIL line and the exit code', async (t) => {
  const { spawnSync } = require('node:child_process');
  const dir = fs.mkdtempSync(path.join(process.env.TMP_DIR || os.tmpdir(), 'svf-rt-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const run = (buf) => { const f = path.join(dir, 'a.AppImage'); fs.writeFileSync(f, buf); return spawnSync('node', [path.join(__dirname, '..', 'build', 'check-runtime.mjs'), f], { encoding: 'utf8' }); };
  let r = run(elf()); assert.equal(r.status, 1); assert.match(r.stdout, /^FAIL --appimage-version/);   // static image, but not runnable: the run stage fails it
  r = run(elf({ interp: true })); assert.equal(r.status, 1); assert.match(r.stdout, /^FAIL the runtime has a dynamic loader/);
});

test('--appimage-version: exit 0 with the version line passes; a non-zero exit after valid output, no line or a libfuse message fails', async () => {
  const { checkVersionRun } = await import('../build/check-runtime.mjs');
  const line = 'AppImage runtime version: https://github.com/AppImage/type2-runtime/commit/dd6cebe\n';
  assert.equal(checkVersionRun({ status: 0, stdout: line }).ok, true);
  const bad = checkVersionRun({ status: 1, stdout: line });
  assert.equal(bad.ok, false); assert.match(bad.msg, /exited 1/);
  assert.equal(checkVersionRun({ status: 0, stdout: 'hello\n' }).ok, false);
  assert.equal(checkVersionRun({ status: 0, stdout: '' }).ok, false);
  assert.equal(checkVersionRun({ status: 0, stdout: line, stderr: 'dlopen(): error loading libfuse.so.2' }).ok, false);
  assert.equal(checkVersionRun({ status: 'signal SIGSEGV', stdout: line }).ok, false);
});

// the real runtimes of electron-builder's caches, when this host has them
const CACHE = path.join(os.homedir(), '.cache', 'electron-builder');
const find = (pool, glob) => {
  try { for (const d of fs.readdirSync(path.join(CACHE, pool))) { const f = path.join(CACHE, pool, d, ...glob); if (fs.existsSync(f)) return f; } } catch (e) { /* absent */ }
  return null;
};
const NEW_RT = find('appimage@1.0.3', ['runtimes', 'runtime-x64']);
const OLD_RT = find('appimage-12.0.1', ['runtime-x64']);

test('the cached appimage@1.0.3 runtime is static', { skip: NEW_RT ? false : 'toolset not cached' }, async () => {
  const r = (await load())(fs.readFileSync(NEW_RT));
  assert.equal(r.ok, true, r.msg);
});
test('the cached appimage-12.0.1 runtime fails on PT_INTERP', { skip: OLD_RT ? false : 'legacy toolset not cached' }, async () => {
  const r = (await load())(fs.readFileSync(OLD_RT));
  assert.equal(r.ok, false); assert.match(r.msg, /PT_INTERP/);
});

test('prune-appimage-toolset: a recorded file missing from the toolset is one message and exit 1, not a traceback', { skip: NEW_RT ? false : 'toolset not cached' }, (t) => {
  const { spawnSync } = require('node:child_process');
  const archive = fs.readdirSync(path.join(CACHE, 'appimage@1.0.3')).find((n) => n.endsWith('.tar.gz'));
  if (!archive) return t.skip('archive not cached');
  const empty = fs.mkdtempSync(path.join(process.env.TMP_DIR || os.tmpdir(), 'svf-pr-'));
  t.after(() => fs.rmSync(empty, { recursive: true, force: true }));
  const r = spawnSync('python3', [path.join(__dirname, '..', 'build', 'prune-appimage-toolset.py'), empty, path.join(CACHE, 'appimage@1.0.3', archive), path.join(empty, 'out')], { encoding: 'utf8' });
  assert.equal(r.status, 1, r.stderr);
  assert.match(r.stderr, /is not in/);
  assert.ok(!/Traceback/.test(r.stderr), r.stderr);
});
