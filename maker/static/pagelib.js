/* pagelib.js - the maker page's pure helpers (no DOM, no fetch): importable by node for tests. */

/** Python's int(text, 0): 0x/0o/0b prefixes or decimal without leading zeros; NaN otherwise. */
export function intBase0(text) {
  const m = /^([+-]?)(0[xX][0-9a-fA-F]+|0[oO][0-7]+|0[bB][01]+|0+|[1-9][0-9]*)$/.exec(text.trim());
  if (!m) return NaN;
  const body = m[2];
  const value = /^0[xX]/.test(body) ? parseInt(body.slice(2), 16)
    : /^0[oO]/.test(body) ? parseInt(body.slice(2), 8)
    : /^0[bB]/.test(body) ? parseInt(body.slice(2), 2) : parseInt(body, 10);
  return m[1] === "-" ? -value : value;
}

/** The code point a dy key names, read as tools/svfdy.json_dy reads it (and settings._dy_key): a one-character key is
 *  that character ("5" is U+0035), any other key is int(key, 0); the page also takes "U+0041". null for anything else. */
export function dyKey(key) {
  const chars = Array.from(key);
  if (chars.length === 1) return chars[0].codePointAt(0);
  const u = /^U\+([0-9a-fA-F]{1,6})$/.exec(key);
  const cp = u ? parseInt(u[1], 16) : intBase0(key);
  return Number.isInteger(cp) && cp >= 0 && cp <= 0x10FFFF ? cp : null;
}

/** "U+0041=1 g=-1 0x67=2" -> {65: 1, 103: -1}; null when a token does not parse. */
export function parseDyText(text) {
  const out = {};
  for (const token of text.split(/[\s,]+/).filter(Boolean)) {
    const at = token.lastIndexOf("=");
    if (at <= 0) return null;
    const cp = dyKey(token.slice(0, at));
    const value = /^-?\d+$/.test(token.slice(at + 1)) ? Number(token.slice(at + 1)) : NaN;
    if (cp === null || !Number.isInteger(value) || value < -128 || value > 127) return null;
    out[cp] = value;
  }
  return out;
}

/** A signature of a step row: equal signatures mean the row's DOM can be kept (its controls, its glyph grid). */
export function stepSig(step, companion) {
  const pick = (s) => s ? [s.id, s.state, s.seconds, s.error, s.kind, s.size, s.bpp, s.name, s.output, s.report, s.exit, s.identical_to] : null;
  return JSON.stringify([pick(step), pick(companion), step.stderr_tail || "", step.quality || null, step.facts || null,
    step.identity || null]);
}

// ---- busy answers (t_39c9fb52) -------------------------------------------------------------------------------
// The server tags its retryable 409s with `busy: "lock" | "preparing" | "preview"`. Repeat the identical request after
// these delays (at most three repeats), and never once BUSY_RETRY_TOTAL_MS have passed since the first send.
export const BUSY_RETRY_MS = [500, 1000, 2000];
export const BUSY_RETRY_TOTAL_MS = 15000;
const BUSY_KINDS = ["lock", "preparing", "preview"];

// The wait before the next repeat, or null when the page must not repeat: an answer with no busy kind (also a network
// error: no answer means the outcome is unknown), a "being prepared" answer to anything but a GET (another run is
// being made: repeating would only race it), the repeats used up, or the total time spent.
export function busyRetryDelay(method, kind, repeats, elapsedMs, bounds) {
  const delays = (bounds && bounds.retryMs) || BUSY_RETRY_MS;                 // @p bounds: a test's override
  const total = bounds && bounds.totalMs !== undefined ? bounds.totalMs : BUSY_RETRY_TOTAL_MS;
  if (typeof kind !== "string" || !BUSY_KINDS.includes(kind)) return null;
  if (kind === "preparing" && method !== "GET") return null;
  if (repeats >= delays.length || elapsedMs >= total) return null;
  return delays[repeats];
}

export function isBusyKind(kind) { return typeof kind === "string" && BUSY_KINDS.includes(kind); }
