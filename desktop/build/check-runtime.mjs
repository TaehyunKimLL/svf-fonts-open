// check-runtime.mjs APPIMAGE: the AppImage's runtime (the ELF at the start of the file) must start on a machine without
// libfuse2: no PT_INTERP, no DT_NEEDED entry (a static-pie executable), and no "libfuse.so.2" string in its image (the
// old type-2 runtime dlopen()s that library at the mount). Prints one line "ok <what>" or "FAIL <why>", exit 0 or 1.
// The logic is exported for desktop/test/check-runtime.test.js.
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const PT_LOAD = 1, PT_DYNAMIC = 2, PT_INTERP = 3, DT_NEEDED = 1, DT_NULL = 0;

/** @returns {{ok: boolean, msg: string}} for the bytes of an AppImage (or of just its runtime) */
export function checkRuntime(buf) {
  const fail = (msg) => ({ ok: false, msg });
  if (buf.length < 64 || buf.readUInt32BE(0) !== 0x7f454c46) return fail('the file does not start with an ELF runtime');
  if (buf[4] !== 2 || buf[5] !== 1) return fail('the runtime is not a little-endian ELF64 (only x86-64 and aarch64 are checked)');
  const phoff = Number(buf.readBigUInt64LE(0x20)), shoff = Number(buf.readBigUInt64LE(0x28));
  const phentsize = buf.readUInt16LE(0x36), phnum = buf.readUInt16LE(0x38), shentsize = buf.readUInt16LE(0x3a), shnum = buf.readUInt16LE(0x3c);
  let end = shoff + shentsize * shnum;                       // the runtime ends where its section table does
  let interp = false, dyn = null;
  if (phoff + phentsize * phnum > buf.length) return fail('truncated program headers');
  for (let i = 0; i < phnum; i++) {
    const p = phoff + i * phentsize;
    const type = buf.readUInt32LE(p), off = Number(buf.readBigUInt64LE(p + 8)), filesz = Number(buf.readBigUInt64LE(p + 32));
    if (type === PT_INTERP) interp = true;
    if (type === PT_DYNAMIC) dyn = { off, filesz };
    if (type === PT_LOAD) end = Math.max(end, off + filesz);
  }
  end = Math.min(end, buf.length);
  if (interp) return fail('the runtime has a dynamic loader (PT_INTERP): it is not static');
  const needed = [];
  if (dyn) {
    const strtab = [];
    for (let o = dyn.off; o + 16 <= Math.min(dyn.off + dyn.filesz, buf.length); o += 16) {
      const tag = Number(buf.readBigInt64LE(o)), val = Number(buf.readBigUInt64LE(o + 8));
      if (tag === DT_NULL) break;
      if (tag === DT_NEEDED) strtab.push(val);
    }
    if (strtab.length) needed.push(...strtab.map((v) => '#' + v));
  }
  if (needed.length) return fail('the runtime lists ' + needed.length + ' needed shared libraries: it is not static');
  if (buf.subarray(0, end).includes('libfuse.so.2')) return fail('the runtime names libfuse.so.2 (it would dlopen it at the mount)');
  return { ok: true, msg: 'static runtime (' + end + ' bytes): no loader, no needed libraries, no libfuse.so.2' };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const file = process.argv[2];
  let r;
  try {
    const fd = fs.openSync(file, 'r'); const head = Buffer.alloc(4 * 1024 * 1024); const n = fs.readSync(fd, head, 0, head.length, 0); fs.closeSync(fd);
    r = checkRuntime(head.subarray(0, n));                     // the runtime is under 1 MB; the squashfs follows
  } catch (e) { r = { ok: false, msg: 'cannot read ' + file + ': ' + e.message }; }
  console.log((r.ok ? 'ok ' : 'FAIL ') + r.msg);
  process.exit(r.ok ? 0 : 1);
}
