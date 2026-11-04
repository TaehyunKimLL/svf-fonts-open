/* svfview.js - the maker page's drawing layer: the SVF renderer built to WebAssembly (maker/build-wasm.sh) drawing
 * faces into GRAY8 / MONO / RGB565 buffers and <canvas> elements, plus the per-glyph compositor that previews a header
 * ascent or a per-glyph dy without a rebuild.
 *
 * An ES module with no DOM access at import time (the *Into functions and the glyph readers run under node). The
 * module instance is the one the page owns: load() imports /static/wasm/svf.js once, init(M) takes an instance a test
 * made. Face bytes are copied into the module heap by openChain() and stay there until the next openChain().
 *
 * drawGlyphsInto mirrors walk_next / svf_measure_utf8 / svf_draw_utf8 (c/src/svf_draw.c): one svfw_draw per code point
 * (a combining mark takes the pen as it is, the core places it), the face of a code point is the first slot with
 * svfw_has, a code point no slot has moves the pen by 0, the pen moves by S(advance) after a non-mark, and the cell of
 * slot 0 is moved to where a face with header ascent A' and the code point's new dy would put it:
 *   y = baseline + S(A) - S(A') + S(d_new) - S(d_stored)
 * with S the core's SCALE_LEN at the chain's reduced ratio.
 */

export const NOTICE = "preview module not built: run maker/build-wasm.sh";

const ERR = ["SVF_OK", "SVF_E_MAGIC", "SVF_E_VERSION", "SVF_E_BPP", "SVF_E_RANGE", "SVF_E_NOMEM", "SVF_E_IO",
  "SVF_E_ARG", "SVF_E_LAYOUT"];
const errName = (e) => ERR[e] ?? "svf_err " + e;
const KIND_CODE = {gray8: 0, mono_page: 1, mono: 2, mono_row: 2, rgb565: 3};
const MAX_FACE_BYTES = 16 << 20;
const PIECE_BASE = 0xF0000;
const SLOTS = 4;

let M = null;
let loading = null;
let faces = [];                    // pointers of the face bytes in the module heap
let infos = [];                    // per slot: {bpp, cellW, cellH, ascent, flags, status, count, jamo}
let num = 1, den = 1;

function need() {
  if (!M) throw new Error(NOTICE);
  return M;
}

function check(call, e) {
  if (e !== 0) throw new Error(call + ": " + errName(e));
}

function alloc(n) {
  const p = need()._malloc(Math.max(n, 1));
  if (!p) throw new Error("SVF_E_NOMEM: out of memory for " + n + " bytes");
  return p;
}

/** Use an instantiated module (a test, or load()). */
export function init(module) {
  M = module;
  faces = [];
  infos = [];
  num = den = 1;
  return M;
}

/** Import and instantiate the module once; rejects with Error(NOTICE) when the import fails. */
export function load(url = "/static/wasm/svf.js") {
  if (M) return Promise.resolve(M);
  if (!loading) {
    loading = import(url).then((mod) => mod.default()).then(init).catch(() => {
      loading = null;
      throw new Error(NOTICE);
    });
  }
  return loading;
}

/** Close every slot, free the old face bytes, copy @p byteArrays (up to 4, slot order) into the heap and open them.
 *  Returns [{bpp, cellW, cellH, ascent, flags, status, count, jamo}] per slot. A slot whose open failed throws. */
export function openChain(byteArrays) {
  const m = need();
  if (byteArrays.length > SLOTS) throw new Error("at most " + SLOTS + " faces");
  for (const bytes of byteArrays) {
    if (bytes.length > MAX_FACE_BYTES) throw new Error("face over 16 MiB");
  }
  check("svfw_reset", m._svfw_reset());
  for (const p of faces) m._free(p);
  faces = [];
  infos = [];
  const out = m._malloc(32);
  try {
    byteArrays.forEach((bytes, slot) => {
      const p = alloc(bytes.length);
      m.HEAPU8.set(bytes, p);
      faces.push(p);
      check("svfw_open " + slot, m._svfw_open(slot, p, bytes.length));
      check("svfw_info " + slot, m._svfw_info(slot, out));
      const v = m.HEAP32.subarray(out >> 2, (out >> 2) + 8);
      infos.push({bpp: v[0], cellW: v[1], cellH: v[2], ascent: v[3], flags: v[4], status: v[5], count: v[6],
                  jamo: v[7] !== 0});
    });
  } finally {
    m._free(out);
  }
  return infos.map((i) => ({...i}));
}

/** The line scale (each 1..16). */
export function setScale(n, d) {
  check("svfw_scale", need()._svfw_scale(n, d));
  const gcd = (a, b) => (b ? gcd(b, a % b) : a);
  const g = gcd(n, d);
  num = n / g;
  den = d / g;
}

/** SCALE_LEN of the chain's reduced ratio: round half up on the magnitude, sign kept. */
export function S(v) {
  if (num === den) return v;
  const a = Math.abs(v);
  const r = Math.trunc((a * num + Math.trunc(den / 2)) / den);
  return v < 0 ? -r : r;
}

/** SCALE_DIM: the scaled cell size, rounded up. */
function D(v) {
  return num === den ? v : Math.trunc((v * num + den - 1) / den);
}

const isMark = (cp) => cp >= 0x300 && cp <= 0x36F;

/** The rows of @p slot's cell for a line whose baseline row is @p baseline: {top, baseline, bottom} (the guides). */
export function cellBox(slot, baseline, ascentOverride = null) {
  const info = infos[slot];
  if (!info) throw new Error("slot " + slot + " is not open");
  const top = baseline - S(ascentOverride ?? info.ascent);
  return {top, baseline, bottom: top + D(info.cellH)};
}

export const has = (slot, cp) => need()._svfw_has(slot, cp) !== 0;

export function metrics(slot, cp) {
  const m = need();
  const o = m._malloc(16);
  try {
    const rc = m._svfw_metrics(slot, cp, o);
    const v = m.HEAP32.subarray(o >> 2, (o >> 2) + 4);
    return rc < 0 ? {rc, advance: 0, bearing: 0, inkW: 0, dy: 0}
                  : {rc, advance: v[0], bearing: v[1], inkW: v[2], dy: v[3]};
  } finally {
    m._free(o);
  }
}

/** The jamo pieces of a composed code point: piece numbers (0xFFFF blank). The count is trusted (piece 0 is real). */
export function pieces(slot, cp) {
  const m = need();
  const o = m._malloc(8);
  try {
    const n = m._svfw_pieces(slot, cp, o);
    const out = [];
    for (let i = 0; i < n; i++) out.push(m.HEAPU8[o + 2 * i] | (m.HEAPU8[o + 2 * i + 1] << 8));
    return out;
  } finally {
    m._free(o);
  }
}

/** The cell of @p cp in @p slot as levels 0..255: {w, h, bpp, levels}. */
export function glyphCell(slot, cp) {
  const m = need();
  const info = infos[slot];
  if (!info) throw new Error("slot " + slot + " is not open");
  const bytes = m._svfw_cell_bytes(slot);
  const buf = alloc(2 * bytes);
  try {
    check("svfw_glyph U+" + cp.toString(16), m._svfw_glyph(slot, cp, buf, 2 * bytes));
    const cell = m.HEAPU8.slice(buf, buf + bytes);
    const w = info.cellW, h = info.cellH, bpp = info.bpp;
    const pitch = (w * bpp + 7) >> 3;
    const levels = new Uint8Array(w * h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const row = y * pitch;
        if (bpp === 1) levels[y * w + x] = (cell[row + (x >> 3)] >> (7 - (x & 7))) & 1 ? 255 : 0;
        else if (bpp === 2) levels[y * w + x] = ((cell[row + (x >> 2)] >> (6 - 2 * (x & 3))) & 3) * 85;
        else levels[y * w + x] = cell[row + x];
      }
    }
    return {w, h, bpp, levels};
  } finally {
    m._free(buf);
  }
}

/** Every code point of the slot's code point table, in file order. */
export function codePoints(slot) {
  const m = need();
  const out = [];
  const count = infos[slot] ? infos[slot].count : 0;
  for (let i = 0; i < count; i++) {
    const cp = m._svfw_cmap_cp(slot, i);
    if (cp >= 0) out.push(cp);
  }
  return out;
}

/** U+AC00..U+D7A3 the slot draws (svfw_has): the composed syllables of a jamo face. */
export function syllables(slot) {
  const out = [];
  for (let cp = 0xAC00; cp <= 0xD7A3; cp++) if (has(slot, cp)) out.push(cp);
  return out;
}

/** [x, baseline - ascent, width, baseline + descent] of @p text at the current chain and scale (svfw_line_box). */
export function lineBox(text, x, baseline) {
  const m = need();
  const bytes = new TextEncoder().encode(text);
  const t = alloc(bytes.length);
  const o = m._malloc(16);
  try {
    m.HEAPU8.set(bytes, t);
    check("svfw_line_box", m._svfw_line_box(t, bytes.length, x, baseline, o));
    return Array.from(m.HEAP32.subarray(o >> 2, (o >> 2) + 4));
  } finally {
    m._free(o);
    m._free(t);
  }
}

// ---- target buffers -----------------------------------------------------------------------------------------

function geometry(kind, w, h) {
  const code = KIND_CODE[kind];
  if (code === undefined) throw new Error("unknown target " + kind);
  const stride = code === 2 ? (w + 7) >> 3 : code === 3 ? 2 * w : w;
  return {code, stride, len: stride * (code === 1 ? (h + 7) >> 3 : h)};
}

function withTarget(kind, w, h, opts, fn) {
  const m = need();
  const g = geometry(kind, w, h);
  const buf = alloc(g.len);
  try {
    m.HEAPU8.fill(0, buf, buf + g.len);
    check("svfw_target2", m._svfw_target2(g.code, buf, g.len, w, h, g.stride, opts.fg ?? 0xFFFF, opts.bg ?? 0,
                                          opts.threshold ?? 128, opts.bigEndian ? 1 : 0));
    fn();
    return m.HEAPU8.slice(buf, buf + g.len);
  } finally {
    m._free(buf);
  }
}

function drawText(text, x, baseline) {
  const m = need();
  const bytes = new TextEncoder().encode(text);
  const t = alloc(bytes.length);
  try {
    m.HEAPU8.set(bytes, t);
    const e = m._svfw_draw(t, bytes.length, x, baseline);
    if (e !== 0) throw new Error("svfw_draw: " + errName(e));
  } finally {
    m._free(t);
  }
}

function measure(text) {
  const m = need();
  const bytes = new TextEncoder().encode(text);
  const t = alloc(bytes.length);
  const o = m._malloc(8);
  try {
    m.HEAPU8.set(bytes, t);
    check("svfw_measure", m._svfw_measure(t, bytes.length, o));
    const v = m.HEAP16.subarray(o >> 1, (o >> 1) + 3);
    return {width: v[0], ascent: v[1], descent: v[2]};
  } finally {
    m._free(o);
    m._free(t);
  }
}

/** Draw @p text with one svfw_draw. Returns {w, h, baseline, pixels}: w = width + 2, h = ascent + descent + 2, the pen
 *  at x 1, the baseline row ascent + 1; pixels is the target buffer (GRAY8 by default). */
export function drawLineInto(text, opts = {}) {
  const kind = opts.target ?? "gray8";
  const e = measure(text);
  const w = e.width + 2, h = e.ascent + e.descent + 2, baseline = e.ascent + 1;
  const pixels = withTarget(kind, w, h, opts, () => drawText(text, 1, baseline));
  return {w, h, baseline, pixels};
}

/** Draw @p text one code point at a time with the overrides of the file header. Options: ascentOverride (slot 0's
 *  header ascent to try), dy ({code point: dy} replacing the stored dy of slot 0), pitch (a fixed advance), symbolsFixed
 *  (U+2026 and U+25A1 get no ascent term: a DOS raw face built with --symbols frames them by the ascent), and the
 *  target options of drawLineInto. */
export function drawGlyphsInto(text, opts = {}) {
  const m = need();
  const kind = opts.target ?? "gray8";
  const dyMap = opts.dy ?? {};
  const info0 = infos[0];
  if (!info0) throw new Error("no face open");
  const A = info0.ascent;
  const A2 = opts.ascentOverride ?? A;
  const cps = [];
  for (const ch of text) {
    let cp = ch.codePointAt(0);
    if (cp >= 0xD800 && cp <= 0xDFFF) cp = 0xFFFD;
    cps.push(cp);
  }
  const placed = [];
  let pen = 0, up = 0, down = 0;
  for (const cp of cps) {
    let slot = -1;
    for (let s = 0; s < infos.length; s++) {
      if (m._svfw_has(s, cp)) { slot = s; break; }
    }
    const mt = slot >= 0 ? metrics(slot, cp) : null;
    if (!mt || mt.rc < 0) continue;                     // no face has it: the pen moves by 0
    let y = 0, dyScaled, ascent, upAscent;
    if (slot === 0) {
      const composed = pieces(0, cp).length > 0;
      const dOld = mt.dy;
      const dNew = composed ? 0 : (dyMap[cp] ?? dOld);
      dyScaled = S(dNew);
      ascent = upAscent = S(A2);
      // A DOS raw face built with --symbols frames U+2026 and U+25A1 by its ascent, so a rebuild keeps them on the
      // baseline: no ascent term. Below the header ascent their cell then sticks out above the others', so the box
      // grows upward to hold it (a rebuild would re-frame and cut them: that part is approximate).
      const fixedSymbol = opts.symbolsFixed && (cp === 0x2026 || cp === 0x25A1);
      if (fixedSymbol) upAscent = Math.max(S(A), S(A2));
      y = (fixedSymbol ? 0 : S(A) - S(A2)) + S(dNew) - S(dOld);
    } else {
      dyScaled = S(mt.dy);
      ascent = upAscent = S(infos[slot].ascent);
    }
    const cellH = D(infos[slot].cellH);
    up = Math.max(up, upAscent - dyScaled);
    down = Math.max(down, cellH - ascent + dyScaled);
    placed.push({cp, x: pen, y});
    if (!isMark(cp)) pen += opts.pitch ?? S(mt.advance);
  }
  const w = Math.min(pen, 32765) + 2, h = up + down + 2, baseline = up + 1;
  const pixels = withTarget(kind, w, h, opts, () => {
    for (const p of placed) {
      const x = 1 + p.x, y = baseline + p.y;
      if (x >= w || x < -32768 || y < -32768 || y > 32767) continue;   // beyond the buffer (the glue takes int16)
      drawText(String.fromCodePoint(p.cp), x, y);
    }
  });
  return {w, h, baseline, pixels};
}

// ---- canvases (the browser) ---------------------------------------------------------------------------------------

const INK = [0x1d, 0x21, 0x1c];
const PAPER = [0xff, 0xff, 0xff];

/** The RGBA bytes of a drawn buffer @p r ({w, h, pixels}) for target @p kind (gray8, mono, mono_row, mono_page,
 *  rgb565): coverage blended ink over paper, set bits as ink, 565 values as colours. Returns {rgba, drawn} where drawn
 *  counts the pixels that are not blank. Pure (no DOM). */
export function decodeRGBA(kind, r, opts = {}) {
  const {w, h, pixels} = r;
  const ink = opts.ink ?? INK, paper = opts.paper ?? PAPER;
  const bg = opts.bg ?? 0;
  const g = geometry(kind, w, h);
  const rgba = new Uint8ClampedArray(4 * w * h);
  let drawn = 0;
  const put = (i, rgb) => { rgba[4 * i] = rgb[0]; rgba[4 * i + 1] = rgb[1]; rgba[4 * i + 2] = rgb[2]; rgba[4 * i + 3] = 255; };
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      if (kind === "gray8") {
        const c = pixels[i];
        if (c) drawn++;
        put(i, [0, 1, 2].map((k) => Math.round(paper[k] + (ink[k] - paper[k]) * c / 255)));
      } else if (kind === "mono" || kind === "mono_row") {
        const on = (pixels[y * g.stride + (x >> 3)] >> (7 - (x & 7))) & 1;
        if (on) drawn++;
        put(i, on ? ink : paper);
      } else if (kind === "mono_page") {
        const on = (pixels[(y >> 3) * g.stride + x] >> (y & 7)) & 1;      // SSD1306 pages: bit y & 7 of buf[(y >> 3) * w + x]
        if (on) drawn++;
        put(i, on ? ink : paper);
      } else if (kind === "rgb565") {
        const v = opts.bigEndian ? (pixels[y * g.stride + 2 * x] << 8) | pixels[y * g.stride + 2 * x + 1]
                                 : pixels[y * g.stride + 2 * x] | (pixels[y * g.stride + 2 * x + 1] << 8);
        if (v !== bg) drawn++;
        put(i, [((v >> 11) & 31) * 255 / 31, ((v >> 5) & 63) * 255 / 63, (v & 31) * 255 / 31].map(Math.round));
      } else {
        throw new Error("unknown target " + kind);
      }
    }
  }
  return {rgba, drawn};
}

function toImageData(canvas, kind, r, opts) {
  const {rgba, drawn} = decodeRGBA(kind, r, opts);
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(r.w, r.h);
  img.data.set(rgba);
  canvas.width = r.w;
  canvas.height = r.h;
  ctx.putImageData(img, 0, 0);
  canvas.dataset.drawn = "1";
  canvas.dataset.ink = String(drawn);
}

/** True for a value `String.fromCodePoint` takes and a face could draw: 0..0x10FFFF, no surrogate. */
export function isCodePoint(cp) {
  return Number.isInteger(cp) && cp >= 0 && cp <= 0x10FFFF && !(cp >= 0xD800 && cp <= 0xDFFF);
}

function onCanvas(canvas, draw, opts) {
  const kind = opts.target ?? "gray8";
  delete canvas.dataset.error;
  try {
    const r = draw();
    toImageData(canvas, kind, r, opts);
    return r;
  } catch (err) {
    canvas.dataset.error = String(err && err.message ? err.message : err);
    delete canvas.dataset.drawn;
    return null;
  }
}

/** drawLineInto onto @p canvas (sized to the line). Sets dataset.drawn, dataset.ink or dataset.error. */
export function drawLine(canvas, text, opts = {}) {
  return onCanvas(canvas, () => drawLineInto(text, opts), opts);
}

/** drawGlyphsInto onto @p canvas. */
export function drawGlyphs(canvas, text, opts = {}) {
  return onCanvas(canvas, () => drawGlyphsInto(text, opts), opts);
}

/** The piece p of @p slot at integer @p scale on @p canvas (a 1 bpp or 2 bpp cell as levels). */
export function drawPiece(canvas, slot, p, scale = 2) {
  const cell = glyphCell(slot, PIECE_BASE + p);
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(cell.w * scale, cell.h * scale);
  for (let y = 0; y < cell.h * scale; y++) {
    for (let x = 0; x < cell.w * scale; x++) {
      const c = cell.levels[Math.floor(y / scale) * cell.w + Math.floor(x / scale)];
      const o = 4 * (y * cell.w * scale + x);
      const v = 255 - c;
      img.data[o] = v; img.data[o + 1] = v; img.data[o + 2] = v; img.data[o + 3] = 255;
    }
  }
  canvas.width = cell.w * scale;
  canvas.height = cell.h * scale;
  ctx.putImageData(img, 0, 0);
  canvas.dataset.drawn = "1";
}
