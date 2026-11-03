// picker.js - the SVF font picker page: the face list, lazy face loading and the preview canvas. It is the only module
// of the page; svf.js (the renderer compiled to WebAssembly) draws every pixel, this file only moves bytes in and turns
// the target buffer (GRAY8, MONO row, RGB565) into canvas pixels. window.picker is what the UI calls and what
// web/test/check.mjs drives.
import SvfModule from './svf.js';

const ERR = ['SVF_OK', 'SVF_E_MAGIC', 'SVF_E_VERSION', 'SVF_E_BPP', 'SVF_E_RANGE', 'SVF_E_NOMEM', 'SVF_E_IO', 'SVF_E_ARG', 'SVF_E_LAYOUT'];
const errName = e => ERR[e] ?? 'svf_err ' + e;
const KIND_CODE = { gray8: 0, mono: 2, rgb565: 3 }; // svf_target_kind: GRAY8, MONO_ROW, RGB565
const PRESETS = {
	pangram: '다람쥐 헌 쳇바퀴에 타고파',
	clash: '국궉귁개객게각',
	rare: '뛔횰쓿긹',
	finals: '삶닭값읊핥',
	ascii: '!"#$%&\'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~',
	mixed: "King's Quest IV: 로제라의 모험 (1988)",
	compat: 'ㄱㄴㄷㄹㅁㅂㅅ ㅏㅑㅓㅕㅗㅛㅜㅠㅡㅣ',
	marks: 'é à',
	supplement: 'â é … ™ 퉝', // what the small per-game supplement faces hold
};
const PRESET_LABELS = { pangram: 'pangram', clash: 'boundary clash', rare: 'rare', finals: 'double finals', ascii: 'ASCII',
	mixed: 'mixed game line', compat: 'compat jamo', marks: 'marks', supplement: 'supplements' };
const RATIOS = [[1, 2], [2, 3], [1, 1], [3, 2], [2, 1], [3, 1], [4, 1], [6, 1], [8, 1]];
const DEFAULT_HANGUL = 'svf/dos/NGOTB16.SVF';

// Faces kept in the module heap in total (all 153 faces are 21 MB): past this the oldest faces outside the chain are dropped.
const MAX_TOTAL_FACE_BYTES = 64 << 20, MAX_LICENCE_BYTES = 256 << 10, MAX_INDEX_BYTES = 4 << 20;

const state = {
	M: null, index: null, byKey: new Map(),
	files: new Map(), // key -> {ptr, len}: a face is fetched once and copied into the module heap; kept in fetch order
	faceBytes: 0, faceBudget: MAX_TOTAL_FACE_BYTES,
	lack: { text: null, counts: new Map() }, // lacking(): key -> count for lack.text; faces not in it are scanned when asked
	text: PRESETS.pangram, num: 1, den: 1,
	target: { kind: 'gray8', fg: '#1d211c', bg: '#ffffff', threshold: 128, zoom: 2, grid: false },
	fams: new Map(), // px -> Map(famKey -> family row), see buildFams
	px: null, selRow: null, // the pressed size chip (null before any); famKey of the selected row of that size (null: none)
	rows: [], active: null, // the rows shown ({k, fam, li, ...}); the listbox's active row
	stripFor: null, // famKey@px of the row the variant strip is built for
	latin: null, hangul: null, infos: [], // the chain open in the module
	pix: { ptr: 0, cap: 0 }, txt: { ptr: 0, cap: 0 }, // render buffers, grown (never shrunk)
	drawn: null, // {kind, w, h, len} of the last successful render
	queue: Promise.resolve(), // the select queue: selects (and prefetch()) run in the order they were made
	pending: null, // the keys of the select in flight (fetched or being fetched): makeRoom never drops them; null when none
	heap: Promise.resolve(), // the heap lock: a chain of jobs that change the module heap or the open slots, one at a time (heapJob)
	selects: 0, selectIdle: Promise.resolve(), idleRelease: null, // selects queued or running; resolved while there are none
	prefetchGen: 0, prefetchRun: Promise.resolve(), // bumped by every chip move (stops a running loop); the loops, one after the other
	inflight: new Map(), // key -> the promise of the fetch in flight (one request per face; a second asker waits on it)
	scanQueued: false, // a lack scan is queued on the heap lock and has not run yet
	urlNotice: '', // the notices of the URL, joined with "; ": shown until the first prefetch summary has appended to them
	choices: [], // the picker choices (addChoice), each {game, id, lineh?, picked, korean: {...}}; persisted in localStorage
	marks: new Map(), // key -> {mark: '?' | '!', title}: a face that is not in memory (not fetched, evicted) or failed to fetch; cleared when it is fetched
};

class BudgetError extends Error { constructor(msg) { super(msg); this.name = 'BudgetError'; this.code = 'budget'; } }

// One job at a time on the module heap: a job runs after the one before it has settled, whatever that one did. Returns the job's own result.
function heapJob(fn) {
	const run = state.heap.then(fn);
	state.heap = run.catch(() => {});
	return run;
}

function fail(msg) { throw new Error(msg); }

// The left list: a face that is a whole Hangul face (not a subset supplement, not Latin-only). A family is a (family, style) pair.
const isLeft = f => !f.subset && !f.latin_only;
const famKey = f => JSON.stringify([f.family, f.style]);
// the best variant first: more bits per pixel, then a precomposed face over a jamo one, then a square cell, then more glyphs, then the key
function rankFace(a, b) {
	return (b.bpp - a.bpp) || ((a.jamo ? 1 : 0) - (b.jamo ? 1 : 0)) || ((b.cell[0] === b.cell[1] ? 1 : 0) - (a.cell[0] === a.cell[1] ? 1 : 0))
		|| (b.glyphs - a.glyphs) || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0);
}
// px -> Map(famKey -> {family, style, name, faces: [keys in rank order], default}), over the left list, rows sorted by family then style
function buildFams(faces) {
	const ci = (a, b) => { a = a.toLowerCase(); b = b.toLowerCase(); return a < b ? -1 : a > b ? 1 : 0; };
	const groups = new Map(); // px -> Map(famKey -> {family, style, list: [faces]})
	for (const f of faces) {
		if (!isLeft(f)) continue;
		if (!groups.has(f.px)) groups.set(f.px, new Map());
		const m = groups.get(f.px), k = famKey(f);
		if (!m.has(k)) m.set(k, { family: f.family, style: f.style, list: [] });
		m.get(k).list.push(f);
	}
	const byPx = new Map();
	for (const [px, m] of groups) {
		const rows = [...m].map(([k, g]) => {
			const list = g.list.sort(rankFace).map(f => f.key);
			return [k, { family: g.family, style: g.style, name: g.family + (g.style ? ' ' + g.style : ''), faces: list, default: list[0] }];
		}).sort((a, b) => ci(a[1].family, b[1].family) || ci(a[1].style, b[1].style));
		byPx.set(px, new Map(rows));
	}
	return byPx;
}

// Limits: the largest face of svf/ is 0.45 MB; the text is a sample line, not a document; the canvas stays under 64 MB.
const MAX_FACE_BYTES = 8 << 20, MAX_TEXT_BYTES = 16384, MAX_PIXEL_BYTES = 64 << 20;

// Module._malloc, checked: 0 is a controlled SVF_E_NOMEM, nothing has been written.
function alloc(n) {
	const p = state.M._malloc(Math.max(n, 1));
	if (!p) fail('SVF_E_NOMEM: out of memory for ' + n + ' bytes');
	return p;
}

// A URL from faces.json: a relative path under the page's own directory, resolved against location.origin. Absolute,
// protocol-relative, data:/blob: and ../ escapes are rejected (the error names the URL); returns the absolute URL.
function safeUrl(u) {
	if (typeof u !== 'string' || !u || /[\u0000-\u001f\\]/.test(u)) fail('bad URL ' + JSON.stringify(u));
	if (/^[a-z][a-z0-9+.-]*:/i.test(u) || u.startsWith('/')) fail('URL is not a relative path: ' + u);
	if (/%(2f|5c)/i.test(u)) fail('URL has an encoded / or \\ in a path segment: ' + u);
	let bad = false;
	try { bad = u.split('/').some(seg => seg === '..' || seg === '.' || decodeURIComponent(seg) === '..'); } catch { fail('bad URL (malformed percent sequence) ' + JSON.stringify(u)); }
	if (bad) fail('URL leaves the page directory: ' + u);
	const base = new URL('./', location.href), url = new URL(u, base);
	if (url.origin !== location.origin || !url.href.startsWith(base.href)) fail('URL leaves the page directory: ' + u);
	return url.href;
}

// Make room for need more bytes of face: drop the oldest fetched faces that are not protected. Protected, read when this runs:
// the open chain, the keys of the select in flight (state.pending) and keep. Refuses (BudgetError; the message reaches the
// status line) when that is not enough. A dropped face is fetched again if used again; its row shows "?" until then.
function makeRoom(need, keep = []) {
	if (state.faceBytes + need <= state.faceBudget) return;
	const M = state.M, held = key => key === state.latin || key === state.hangul || state.pending?.includes(key) || keep.includes(key);
	let evictable = 0;
	for (const [key, file] of state.files) if (!held(key)) evictable += file.len;
	if (state.faceBytes - evictable + need > state.faceBudget) { // refusal is certain: drop nothing for nothing
		throw new BudgetError(`face memory: ${need} bytes more would pass the ${state.faceBudget} byte budget (${state.faceBytes - evictable} bytes are protected: the open chain, the select in flight and the faces being kept)`);
	}
	let dropped = false;
	for (const [key, file] of [...state.files]) {
		if (state.faceBytes + need <= state.faceBudget) break;
		if (held(key)) continue;
		M._free(file.ptr); // not open in any slot: the chain is [latin, hangul] and those are skipped above
		state.files.delete(key); state.lack.counts.delete(key); state.faceBytes -= file.len;
		state.marks.set(key, { mark: '?', title: 'evicted: pick the size again to fetch' });
		dropped = true;
	}
	if (dropped) queueScan(); // the marks follow
}

// The decoded body of r as bytes, at most limit of them (exactly exact when given). Content-Length counts only when the
// body is not content-encoded (gzip makes it the compressed size): then it is an early reject when over the limit, and
// the body must have exactly that many bytes (a truncated response is an error). The limit is enforced on the decoded
// bytes: the stream reader stops (and cancels the request) as soon as more than limit have arrived.
async function readBounded(r, limit, what, exact) {
	const cl = r.headers.has('content-encoding') ? null : r.headers.get('content-length');
	const refuse = msg => { r.body?.cancel().catch(() => {}); fail(msg); }; // a refused response is not left downloading
	if (cl !== null && !/^\d+$/.test(cl)) refuse(`${what}: bad Content-Length ${JSON.stringify(cl)}`);
	if (cl !== null && +cl > limit) refuse(`${what}: Content-Length ${cl} is over the limit of ${limit} bytes`);
	const sized = n => {
		if (exact !== undefined && n !== exact) fail(`${what}: ${n} bytes, the index says ${exact}`);
		if (cl !== null && n !== +cl) fail(`${what}: ${n} bytes, Content-Length says ${cl}`);
	};
	// Accepted risk: a Content-Length that lies is only caught after the read (the size check below), never during it.
	if (!r.body) { // no stream: arrayBuffer() reads everything, so only a counted Content-Length (within the limit) bounds it
		if (cl === null) fail(`${what}: no body stream and no Content-Length${r.headers.has('content-encoding') ? ' that counts (content-encoded)' : ''}: the size cannot be bounded`);
		const b = new Uint8Array(await r.arrayBuffer());
		if (b.length > limit) fail(`${what}: ${b.length} bytes, the limit is ${limit}`);
		sized(b.length);
		return b;
	}
	const reader = r.body.getReader(), parts = [];
	let n = 0;
	for (;;) {
		const { done, value } = await reader.read();
		if (done) break;
		if (n + value.length > limit) { reader.cancel().catch(() => {}); fail(`${what}: more than ${limit} bytes`); } // the chunk that crosses the limit is dropped, not kept
		n += value.length;
		parts.push(value);
	}
	sized(n);
	const out = new Uint8Array(n);
	let o = 0;
	for (const v of parts) { out.set(v, o); o += v.length; }
	return out;
}

// One request per face: while a fetch of key is in flight, a second asker (a select for a face the prefetch is downloading)
// waits on the same promise. If that fetch is refused for room (its keep set is the asker's business, not ours), the waiter
// tries once for itself with its own keep; any other failure is the face's and is shared.
// out.own is set when this call started the download itself (also after it waited for a refused one), not when it joined or found the face.
async function fetchFace(key, keep = [key], out = {}) {
	const f = state.byKey.get(key) ?? fail('no such face ' + key);
	for (let cur; (cur = state.inflight.get(key)); ) {
		try { return await cur; } catch (err) { if (!(err instanceof BudgetError)) throw err; }
	}
	if (state.files.has(key)) return state.files.get(key);
	out.own = true;
	const run = loadFace(key, f, keep);
	state.inflight.set(key, run);
	const done = () => { if (state.inflight.get(key) === run) state.inflight.delete(key); };
	run.then(done, done);
	return run;
}

async function loadFace(key, f, keep) {
	if (!Number.isInteger(f.bytes) || f.bytes < 1 || f.bytes > MAX_FACE_BYTES) fail(`${key}: bad size ${f.bytes} in faces.json`);
	makeRoom(f.bytes, keep); // early: no point reading a face that cannot fit
	const url = safeUrl(f.url);
	// a redirect is a bad URL like any other; the browser reports it and a network error alike as "Failed to fetch"
	const r = await fetch(url, { redirect: 'error' }).catch(err => fail(`${f.url}: the request failed (a redirect is refused; else the network): ${err?.message ?? err}`));
	if (!r.ok) { r.body?.cancel().catch(() => {}); fail(`${f.url}: HTTP ${r.status}`); }
	const bytes = await readBounded(r, Math.min(f.bytes, MAX_FACE_BYTES), f.url, f.bytes);
	// room, malloc and copy are one heap job; the chain and the pending selection are read there, not when the request began
	return heapJob(() => {
		if (state.files.has(key)) return state.files.get(key); // a concurrent fetch got there first
		makeRoom(bytes.length, keep);
		const ptr = alloc(bytes.length);
		state.M.HEAPU8.set(bytes, ptr); // read HEAPU8 after the malloc: the heap may have grown
		const entry = { ptr, len: bytes.length };
		state.files.set(key, entry); state.faceBytes += bytes.length; state.marks.delete(key);
		return entry;
	});
}

function slotInfo(slot) {
	const M = state.M, p = alloc(32);
	try {
		const e = M._svfw_info(slot, p);
		if (e) fail('svfw_info: ' + errName(e));
		const v = Array.from(M.HEAP32.subarray(p >> 2, (p >> 2) + 8));
		return { bpp: v[0], cellW: v[1], cellH: v[2], ascent: v[3], flags: v[4], status: v[5], glyphs: v[6], jamo: v[7] !== 0 };
	} finally { M._free(p); }
}

async function selectNow({ latin = null, hangul }) {
	const order = latin ? [latin, hangul] : [hangul];
	state.pending = order; // protected from eviction until this select has settled, however it ends
	try {
		if (!hangul) fail('select: a Hangul face is required');
		for (const key of order) await fetchFace(key, order); // all fetched before the chain is touched
		return await heapJob(() => { // the reset and the opens are one job: no scan or fetch runs between them
			const M = state.M, files = order.map(key => state.files.get(key) ?? fail('select: ' + key + ' left the face memory'));
			M._svfw_reset(); // faces stay in the heap; nothing is freed
			state.latin = state.hangul = null; state.infos = []; // no chain until every slot is open
			const infos = [];
			try {
				order.forEach((key, slot) => {
					const e = M._svfw_open(slot, files[slot].ptr, files[slot].len);
					if (e) fail(`svfw_open ${key}: ${errName(e)}`);
					infos.push(slotInfo(slot));
				});
			} catch (err) {
				M._svfw_reset(); // no half-open chain: render reports "no face selected" until a select succeeds
				ui.chain?.();
				throw err;
			}
			state.latin = latin; state.hangul = hangul; state.infos = infos;
			ui.chain?.(); // the controls follow, whoever called select (the UI or a driver)
			writeUrl();
			return { latin: latin ? infos[0] : null, hangul: infos[infos.length - 1] };
		});
	} finally { state.pending = null; }
}

function select(arg) { // serialised: selects run in the order they were made
	if (state.selects++ === 0) state.selectIdle = new Promise(r => { state.idleRelease = r; }); // the prefetch loop waits on this
	const run = state.queue.then(() => selectNow(arg)).finally(() => { if (--state.selects === 0) state.idleRelease(); });
	state.queue = run.catch(() => {});
	return run;
}

// A render buffer grows to a malloc of at least need bytes. The previous block is left in buf.old: the pixel buffer is the
// module's target until svfw_target2 names the new one, so render frees it after that call; the text buffer is free at once.
function grow(buf, need, freeOld) {
	if (buf.cap >= need) return;
	const ptr = alloc(need);
	buf.old = buf.ptr; buf.ptr = ptr; buf.cap = need;
	if (freeOld && buf.old) { state.M._free(buf.old); buf.old = 0; }
}

function hexTo565(hex) {
	const n = parseInt(hex.slice(1), 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255;
	return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3);
}
const x8 = (v, bits) => (v << (8 - bits)) | (v >> (2 * bits - 8));
function rgbOf(hex) { const n = parseInt(hex.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255]; }

// Hangul class: Hangul Jamo, Compatibility Jamo, Jamo Extended-A, Syllables, Jamo Extended-B. A combining mark (the
// renderer's svf_is_mark_default, U+0300..036F) joins the run before it; everything else is the Latin class.
const isHangul = cp => (cp >= 0x1100 && cp <= 0x11FF) || (cp >= 0x3130 && cp <= 0x318F) || (cp >= 0xA960 && cp <= 0xA97F) ||
	(cp >= 0xAC00 && cp <= 0xD7A3) || (cp >= 0xD7B0 && cp <= 0xD7FF);
const isMark = cp => cp >= 0x300 && cp <= 0x36F;

// s with every lone surrogate replaced by U+FFFD, as TextEncoder encodes it (String.prototype.toWellFormed is ES2024)
const wellFormed = s => s.replace(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g, '\uFFFD');

// A line split into runs of one class: [{hangul, text}]. A lone surrogate is U+FFFD (Latin class), as the encoder makes it.
function runsOf(line) {
	const runs = [];
	for (const ch of wellFormed(line)) {
		const cp = ch.codePointAt(0), last = runs[runs.length - 1];
		const hangul = isMark(cp) && last ? last.hangul : isHangul(cp);
		if (last && last.hangul === hangul) last.text += ch; else runs.push({ hangul, text: ch });
	}
	return runs;
}

const gcd = (a, b) => (b ? gcd(b, a % b) : a);

function renderNow() {
	const t0 = performance.now();
	const out = { err: 0, errName: 'SVF_OK', width: 0, ascent: 0, descent: 0, lines: [], ink: 0, ms: 0 };
	const M = state.M, T = state.target;
	state.drawn = null; // set again only when this render succeeds
	const bad = (e, name) => { out.err = e; out.errName = name ?? errName(e); return out; };
	if (!state.hangul) return bad(-1, 'no face selected');
	let e = M._svfw_scale(state.num, state.den);
	if (e) return bad(e);
	if (state.text.length > MAX_TEXT_BYTES) return bad(7, `text is at least ${state.text.length} bytes, the limit is ${MAX_TEXT_BYTES}`); // UTF-8 bytes >= UTF-16 length
	// each line is split into runs by class: a Hangul run tries [Hangul, Latin], a Latin run [Latin, Hangul] (slot 0 is the
	// Latin face when there is one); the runs of a line share its baseline, the pen moving by each run's measured width
	const lines = state.text.split('\n').map(runsOf);
	const enc = new TextEncoder();
	for (const line of lines) for (const r of line) r.utf = enc.encode(r.text);
	const total = lines.reduce((n, l) => n + l.reduce((m, r) => m + r.utf.length, 0), 0);
	if (total > MAX_TEXT_BYTES) return bad(7, `text is ${total} bytes, the limit is ${MAX_TEXT_BYTES}`);
	const two = !!state.latin; // [Latin, Hangul]; with no Latin face the chain is [Hangul] for every run
	const order = r => (two ? M._svfw_order(r.hangul ? 1 : 0) : 0);
	grow(state.txt, Math.max(total, 1), true);
	const mp = alloc(8);
	let off = 0;
	try {
		for (const line of lines) { // measure run by run: a line is as wide as its runs, as high as the highest
			line.width = 0; line.asc = 0; line.desc = 0;
			for (const r of line) {
				M.HEAPU8.set(r.utf, state.txt.ptr + off);
				r.off = off; off += r.utf.length;
				e = order(r) || M._svfw_measure(state.txt.ptr + r.off, r.utf.length, mp);
				if (e) return bad(e);
				const [rw, ra, rd] = M.HEAP16.subarray(mp >> 1, (mp >> 1) + 3);
				r.width = rw; line.width += rw; line.asc = Math.max(line.asc, ra); line.desc = Math.max(line.desc, rd);
			}
		}
	} finally { M._free(mp); if (two) M._svfw_order(0); }
	const width = Math.max(...lines.map(l => l.width)), asc = Math.max(...lines.map(l => l.asc)), desc = Math.max(...lines.map(l => l.desc));
	out.width = width; out.ascent = asc; out.descent = desc; // the maxima, for the status line
	// each line is as high as its own runs (ascent + descent + 2) and its baseline sits that line's ascent below its top
	// an empty line has no runs to measure: it gets the chain's line, the max scaled ascent and descent over the open
	// faces (a line holding one plain glyph of each face), so blank lines keep paragraph spacing
	const g = gcd(state.num, state.den), num = state.num / g, den = state.den / g;
	const S = v => Math.floor((v * num + Math.floor(den / 2)) / den), ceil = v => Math.ceil((v * num) / den); // svfline scale_len, scaled_dim
	const chainAsc = Math.max(0, ...state.infos.map(i => S(i.ascent)));
	const chainDesc = Math.max(0, ...state.infos.map(i => ceil(i.cellH) - S(i.ascent)));
	let h = 0;
	for (const line of lines) {
		if (!line.length) { line.asc = chainAsc; line.desc = chainDesc; }
		line.top = h; line.h = line.asc + line.desc + 2; h += line.h;
	}
	out.lines = lines.map(l => l.h);
	const w = width + 2;
	const kind = KIND_CODE[T.kind] ?? 0;
	const stride = kind === 2 ? (w + 7) >> 3 : kind === 3 ? 2 * w : w;
	const len = stride * h;
	if (w > 32767 || h > 32767 || len > MAX_PIXEL_BYTES) return bad(7, `canvas ${w} x ${h} is too large`);
	// the RGBA ImageData the canvas gets is 4 bytes a pixel whatever the target: refuse before allocating either buffer
	if (4 * w * h > MAX_PIXEL_BYTES) return bad(7, `canvas ${w} x ${h} is too large: ${4 * w * h} bytes of RGBA, the limit is ${MAX_PIXEL_BYTES}`);
	grow(state.pix, len);
	M.HEAPU8.fill(0, state.pix.ptr, state.pix.ptr + len);
	const fg565 = hexTo565(T.fg), bg565 = hexTo565(T.bg);
	if (kind === 3) { // RGB565 never reads the buffer: undrawn pixels must already hold the paper colour (low byte first)
		const row = new Uint8Array(2 * w);
		for (let x = 0; x < w; x++) { row[2 * x] = bg565 & 255; row[2 * x + 1] = bg565 >> 8; }
		for (let y = 0; y < h; y++) M.HEAPU8.set(row, state.pix.ptr + y * stride);
	}
	e = M._svfw_target2(kind, state.pix.ptr, len, w, h, stride, fg565, bg565, T.threshold, 0);
	if (state.pix.old) { M._free(state.pix.old); state.pix.old = 0; } // the old buffer is no longer the target
	if (e) return bad(e);
	try {
		for (const line of lines) {
			let x = 1;
			for (const r of line) {
				e = order(r) || M._svfw_draw(state.txt.ptr + r.off, r.utf.length, x, line.top + 1 + line.asc);
				if (e) break;
				x += r.width;
			}
			if (e) break;
		}
	} finally { if (two) M._svfw_order(0); }
	out.ms = performance.now() - t0;
	if (e) return bad(e); // a failed draw paints nothing
	state.drawn = { kind: T.kind, w, h, len }; // what pixels() returns: the target buffer as the renderer left it
	// pixels: the renderer drew the buffer; JS only converts it
	const img = new ImageData(w, h), d = img.data, src = M.HEAPU8.subarray(state.pix.ptr, state.pix.ptr + len);
	const fg = rgbOf(T.fg), bg = rgbOf(T.bg);
	let ink = 0;
	for (let y = 0; y < h; y++) {
		for (let x = 0; x < w; x++) {
			const o = (y * w + x) * 4;
			let r, g, b;
			if (kind === 0) {
				const a = src[y * stride + x];
				if (a) ink++;
				r = (bg[0] * (255 - a) + fg[0] * a + 127) / 255; g = (bg[1] * (255 - a) + fg[1] * a + 127) / 255;
				b = (bg[2] * (255 - a) + fg[2] * a + 127) / 255;
			} else if (kind === 2) {
				const on = (src[y * stride + (x >> 3)] >> (7 - (x & 7))) & 1;
				if (on) ink++;
				r = on ? fg[0] : bg[0]; g = on ? fg[1] : bg[1]; b = on ? fg[2] : bg[2];
			} else {
				const v = src[y * stride + 2 * x] | (src[y * stride + 2 * x + 1] << 8);
				if (v !== bg565) ink++;
				r = x8(v >> 11, 5); g = x8((v >> 5) & 63, 6); b = x8(v & 31, 5);
			}
			d[o] = r; d[o + 1] = g; d[o + 2] = b; d[o + 3] = 255;
		}
	}
	out.ink = ink;
	ui.paint?.(img, out);
	return out;
}

function render() { // every failure, wherever render was called from, reaches the status line
	let r;
	try { r = renderNow(); } catch (err) { r = { err: -2, errName: String(err.message ?? err), width: 0, ascent: 0, descent: 0, ink: 0, ms: 0 }; }
	if (r.err) ui.error?.(r);
	return r;
}

const COLOUR = /^#[0-9a-fA-F]{6}$/;
function setTarget(t) {
	const T = { ...state.target };
	for (const k of ['kind', 'fg', 'bg', 'threshold', 'zoom', 'grid']) if (t[k] !== undefined) T[k] = t[k];
	if (!Object.hasOwn(KIND_CODE, T.kind)) fail('unknown target ' + T.kind);
	for (const k of ['fg', 'bg']) if (typeof T[k] !== 'string' || !COLOUR.test(T[k])) fail(`setTarget: ${k} must be #RRGGBB, got ${JSON.stringify(T[k])}`);
	if (!Number.isFinite(+T.threshold) || !Number.isFinite(+T.zoom)) fail('setTarget: threshold and zoom must be numbers');
	T.threshold = Math.min(255, Math.max(1, Math.round(T.threshold)));
	T.zoom = Math.min(8, Math.max(1, Math.round(T.zoom)));
	T.grid = !!T.grid;
	Object.assign(state.target, T); // all or nothing
	ui.inputs?.();
}

// For every face already fetched (the others are not in the heap; fetching 153 faces to fill a list would defeat lazy
// loading): how many distinct code points of text (line ends aside) that face alone does not draw (svfw_has). Counts are
// kept per (face, text), so only a changed text or a newly fetched face costs a scan. A scan opens each new face in slot 0
// and restores the open chain, all in one synchronous run (no render sees it); every svfw_open return is checked.
// With keys, only those faces and the chain are scanned (the others keep no count): the page asks for the shown size only.
// The scan reads the chain when it runs, never when it was asked for.
function lacking(text = state.text, keys) {
	text = String(text);
	if (text.length > MAX_TEXT_BYTES) fail(`lacking: text is at least ${text.length} bytes, the limit is ${MAX_TEXT_BYTES}`);
	text = wellFormed(text); // a lone surrogate is U+FFFD to the renderer
	const total = new TextEncoder().encode(text).length;
	if (total > MAX_TEXT_BYTES) fail(`lacking: text is ${total} bytes, the limit is ${MAX_TEXT_BYTES}`);
	const M = state.M, L = state.lack;
	if (!M) return {};
	if (L.text !== text) { L.text = text; L.counts = new Map(); }
	const only = keys ? new Set([...keys, state.latin, state.hangul]) : null;
	const todo = [...state.files].filter(([key]) => !L.counts.has(key) && (!only || only.has(key)));
	if (todo.length) {
		const cps = [...new Set([...text].map(c => c.codePointAt(0)))].filter(c => c !== 10 && c !== 13);
		const chain = [state.latin, state.hangul].filter(Boolean);
		for (const [key, file] of todo) {
			M._svfw_reset();
			// a face that did not open once stays failed (error badge) until it is evicted and fetched again
			const e = file.bad ? 1 : M._svfw_open(0, file.ptr, file.len);
			if (e) file.bad = true;
			L.counts.set(key, e ? -1 : cps.filter(c => !M._svfw_has(0, c)).length);
		}
		M._svfw_reset(); // always put the chain back
		let err = null;
		for (let slot = 0; slot < chain.length; slot++) {
			const file = state.files.get(chain[slot]), e = M._svfw_open(slot, file.ptr, file.len);
			if (e) { err = `lacking: restoring ${chain[slot]}: ${errName(e)}`; break; }
		}
		if (err) {
			M._svfw_reset(); state.latin = state.hangul = null; state.infos = [];
			ui.chain?.(); // the selects and the selected row follow
			fail(err); // render() reports it on the status line
		}
	}
	return Object.fromEntries(L.counts);
}

// Fetch every face of the size px (the left list: families(px) top to bottom, a family's faces in rank order) into the face
// memory, one at a time, a select in flight first. A face that does not fit is skipped ("?"), one that fails to load is "!".
// gen is the chip move that started it: a later move stops it. Never rejects. -> {px, fetched, held, skipped, failed, stopped[, error]}
async function prefetchSize(px, gen) {
	const res = { px, fetched: 0, held: 0, skipped: 0, failed: 0, stopped: false };
	const stopped = () => { // a newer chip move: say so, so the line of the loop before does not stay as if it were this size's
		res.stopped = true; loopNotice(`${px} px: stopped after ${res.fetched + res.held} of ${keys.length} faces`);
		return res;
	};
	const keys = [...(state.fams.get(px)?.values() ?? [])].flatMap(f => f.faces); // all of them are protected while the loop fills the others
	try { await prefetchKeys(gen, keys, res, stopped); } catch (err) { // not a face's failure: the loop itself broke; the notice says so
		res.error = String(err?.message ?? err);
		loopNotice(`${px} px: prefetch failed: ${res.error} (${res.fetched + res.held} of ${keys.length} faces fetched)`);
		return res;
	}
	if (res.stopped) return res;
	loopNotice(`${px} px: ${res.fetched + res.held} of ${keys.length} faces fetched, ${res.skipped} over the face budget, ${res.failed} failed`);
	return res;
}

async function prefetchKeys(gen, keys, res, stopped) {
	for (const key of keys) {
		if (state.prefetchGen !== gen) return stopped();
		if (!state.files.has(key)) {
			while (state.selects) await state.selectIdle; // a select (a pick, a selector) goes before the loop
			if (state.prefetchGen !== gen) return stopped();
		}
		if (state.files.has(key)) { res.held++; continue; } // also a face a select fetched while the loop waited
		try {
			const how = {}; // how.own: this loop downloaded it; else another download (a select's, prefetch()'s) made it resident
			await fetchFace(key, keys, how);
			if (how.own) res.fetched++; else res.held++;
		} catch (err) {
			if (err instanceof BudgetError) { res.skipped++; state.marks.set(key, { mark: '?', title: `not fetched: the ${state.faceBudget} byte face budget is full` }); }
			else { res.failed++; state.marks.set(key, { mark: '!', title: String(err?.message ?? err) }); }
		}
		queueScan(); // a fetched face gets its lack mark, a refused one its ? or !
	}
}


// ---- choices and the export ----------------------------------------------------------------------------------------
const CHOICE_KEY = 'svfpicker.choices', MAX_CHOICES = 256, MAX_CHOICE_STR = 256, MAX_STORED_BYTES = 2 << 20;
// The game names the datalist suggests (any name is accepted); check.mjs compares the datalist with this list.
const GAMES = ['KQ1 (DOS 1991 remake)', 'KQ4', "LB1 Colonel's Bequest", 'LB2 (DOS CD)', 'LB2 (DOS floppy)', 'LSL1 EGA remake', 'LSL2', 'PQ2',
	'QFG1 EGA', 'QFG2', 'SQ4 (DOS CD)', 'SQ4 (DOS EGA floppy)', 'Conquests of Camelot', 'LSL1 AGI', 'MI1 EGA/VGA floppy', 'MI1 CD',
	'MI2 DOS VGA', 'Indy3 VGA', 'Indy3 EGA', 'Indy4 DOS CD', 'Indy4 DOS floppy', 'Loom CD (VGA talkie)', 'DOTT DOS floppy',
	'Maniac Mansion / Zak McKracken'];
const jsonCopy = v => JSON.parse(JSON.stringify(v)); // a caller never holds the model's own objects

// JSON values only: strings and keys at most MAX_CHOICE_STR characters, numbers finite, nesting and arrays bounded
function plainValue(v, depth = 0) {
	if (v === null || typeof v === 'boolean') return true;
	if (typeof v === 'number') return Number.isFinite(v);
	if (typeof v === 'string') return v.length <= MAX_CHOICE_STR;
	if (typeof v !== 'object' || depth > 6) return false;
	if (Array.isArray(v)) return v.length <= MAX_CHOICE_STR && v.every(x => plainValue(x, depth + 1));
	return Object.entries(v).every(([k, x]) => k.length <= MAX_CHOICE_STR && plainValue(x, depth + 1));
}
const isObj = v => v !== null && typeof v === 'object' && !Array.isArray(v);
// Line-oriented fields end up in a line of a map written from the export: a control character (a line break above all) would start another line.
const CONTROL = /[\u0000-\u001f\u007f-\u009f\u2028\u2029]/; // C0, DEL, C1 (U+0085 NEL is a line break to Python's splitlines), LS, PS
const textOk = (v, min = 0) => typeof v === 'string' && v.length >= min && v.length <= MAX_CHOICE_STR && !CONTROL.test(v);
const nameOk = v => textOk(v) && v.trim().length > 0 && !v.includes('|'); // game and id: something besides blanks, no '|' (it breaks a Markdown table written from the export)
const lineOk = v => v === undefined || (Number.isInteger(v) && v >= 1 && v <= 65535);
// A stored choice is held to makeChoice's rules (so the export keeps one shape): game and id are names, lineh is absent or an
// integer 1..65535, picked is true, korean.file is the key, the index's words are texts, latin is a key or null, scale is two integers 1..16.
// The metrics (w, h, bpp, ascent) stay as saved: finite numbers.
function storedChoiceOk(c) {
	if (!isObj(c) || !nameOk(c.game) || !nameOk(c.id) || !lineOk(c.lineh) || c.picked !== true) return false;
	const k = c.korean;
	if (!isObj(k) || !textOk(k.key, 1) || k.file !== k.key || !['label', 'family', 'style', 'variant'].every(n => textOk(k[n]))) return false;
	if (!(k.latin === null || textOk(k.latin, 1))) return false;
	if (!Array.isArray(k.scale) || k.scale.length !== 2 || !k.scale.every(v => Number.isInteger(v) && v >= 1 && v <= 16)) return false;
	return ['w', 'h', 'bpp', 'ascent'].every(n => Number.isFinite(k[n])) && plainValue(c);
}
const UNREADABLE = 'stored choices unreadable: starting empty';
// {list, notice}: anything that is not a JSON array of at most 256 valid choices (a throwing storage included) is an empty list and a notice
function loadChoices() {
	try {
		const raw = localStorage.getItem(CHOICE_KEY);
		if (raw === null) return { list: [], notice: '' };
		if (raw.length > MAX_STORED_BYTES) return { list: [], notice: UNREADABLE };
		const v = JSON.parse(raw);
		if (!Array.isArray(v) || v.length > MAX_CHOICES) return { list: [], notice: UNREADABLE };
		const valid = v.filter(storedChoiceOk).map(c => ({ ...c, game: c.game.trim(), id: c.id.trim() })), skipped = v.length - valid.length; // a record that fails is dropped
		if (v.length && !valid.length) return { list: [], notice: UNREADABLE };
		const seen = new Set(), list = valid.filter(c => { const k = JSON.stringify([c.game, c.id]); return seen.has(k) ? false : (seen.add(k), true); }); // a game and id are one choice: the first stays
		const again = valid.length - list.length, many = n => `${n} stored ${n === 1 ? 'choice' : 'choices'}`;
		return { list, notice: [skipped && `${many(skipped)} skipped: not valid`, again && `${many(again)} skipped: same game and id as an earlier one`].filter(Boolean).join('; ') };
	} catch { return { list: [], notice: UNREADABLE }; }
}
function saveChoices() { // a storage exception is a notice, never a page error
	try { localStorage.setItem(CHOICE_KEY, JSON.stringify(state.choices)); } catch (err) { setNotice(`choices not saved: ${String(err?.message ?? err)}`); }
}
function changed() { saveChoices(); ui.choices?.(); }

function exportText() {
	const games = [], seen = new Map();
	for (const { game, ...font } of state.choices) { // games grouped by name in first-seen order, fonts in insertion order
		if (!seen.has(game)) { const g = { game, fonts: [] }; seen.set(game, g); games.push(g); }
		seen.get(game).fonts.push(font);
	}
	// order "per-run": a Hangul run is drawn by the Hangul face first, a Latin run by the Latin face first (how the choice was looked at)
	return JSON.stringify({ format: 'scummvm-ko-font-pairing/1', created: new Date().toISOString().replace(/\.\d+Z$/, 'Z'), order: 'per-run', source: 'svf-fonts web picker', games }, null, 1);
}

function makeChoice({ game, id, lineh } = {}) {
	const text = (name, v) => {
		if (typeof v !== 'string' || !v.trim() || v.length > MAX_CHOICE_STR) fail(`addChoice: ${name} must be a text of 1..${MAX_CHOICE_STR} characters`);
		if (CONTROL.test(v)) fail(`addChoice: ${name} holds a control character`);
		if (v.includes('|')) fail(`addChoice: ${name} holds '|' (it breaks a Markdown table written from the export)`);
		return v.trim();
	};
	game = text('game', game); id = text('id', id);
	if (lineh !== undefined && lineh !== null && !(Number.isInteger(lineh) && lineh >= 1 && lineh <= 65535)) fail(`addChoice: lineh ${lineh}: an integer 1..65535 or none`);
	if (!state.hangul) fail('addChoice: no face is open (pick a face first)');
	if (state.choices.length >= MAX_CHOICES) fail(`addChoice: at most ${MAX_CHOICES} choices`);
	if (state.choices.some(c => c.game === game && c.id === id)) fail(`addChoice: ${game} ${id} is already a choice (remove it first)`);
	const f = state.byKey.get(state.hangul), { num, den } = state;
	if (CONTROL.test(f.key)) fail("addChoice: the key of the Hangul face holds a control character");
	if (state.latin !== null && CONTROL.test(state.latin)) fail(`addChoice: the key of the Latin face holds a control character`);
	for (const n of ['label', 'family', 'style', 'variant']) if (CONTROL.test(f[n])) fail(`addChoice: the index's ${n} of ${f.key} holds a control character`);
	const S = v => Math.floor((v * num + Math.floor(den / 2)) / den);
	return {
		game, id, ...(lineh == null ? {} : { lineh }), picked: true,
		korean: { key: f.key, label: f.label, family: f.family, style: f.style, variant: f.variant, file: f.key, latin: state.latin,
			scale: [num, den], w: Math.ceil(f.cell[0] * num / den), h: Math.ceil(f.cell[1] * num / den), bpp: f.bpp, ascent: S(f.ascent) },
	};
}

const picker = {
	presets: PRESETS,
	ready: null,
	faces: () => state.index.faces,
	listed: () => state.index.faces.filter(f => !f.subset),
	sizes: () => [...state.fams.keys()].sort((a, b) => a - b),
	families: px => [...(state.fams.get(px)?.values() ?? [])].map(r => ({ ...r, faces: [...r.faces] })), // copies: a caller cannot change the model
	defaultVariant: (family, style, px) => state.fams.get(px)?.get(famKey({ family, style }))?.default ?? null,
	async pick(key) { // a left-list face opens as the whole chain (Latin and Hangul from the one face); nothing else is picked
		const f = state.byKey.get(key);
		if (!f || !isLeft(f)) fail(`pick: ${key} is not a listed Hangul face`);
		return select({ latin: key, hangul: key });
	},
	async setSize(px) { // shows the faces of px and fetches them all; resolves with the counts once the marks are painted
		if (!state.fams.has(px)) fail(`setSize: no faces of ${px} px`);
		if (state.px !== px) showSize(px); // the shown size stays as it is (a pick starts a prefetch of it: focus and scroll must survive)
		const gen = state.prefetchGen;
		const run = state.prefetchRun = state.prefetchRun.catch(() => {}).then(() => prefetchSize(px, gen)); // assigned here, before any await: loops run one after the other. prefetchSize catches everything (the notice says so), so the catch is only a guard
		const res = await run;
		await state.heap; // the scan the loop queued
		return res;
	},
	view() { // what the page shows of the chain: the Hangul face's family when it is a left-list face
		const h = state.byKey.get(state.hangul), listed = !!h && isLeft(h);
		// a hidden Hangul face (a subset face, or a Latin-only one) is on no chip: px is its own; the chips keep the last pressed size
		return { px: h && !listed ? h.px : state.px, family: listed ? h.family : '', style: listed ? h.style : '', variant: listed ? h.variant : '', hangul: state.hangul, latin: state.latin,
			same: state.latin !== null && state.latin === state.hangul && listed, listed };
	},
	notice: () => $('notice').textContent,
	setNotice, // test hook
	select,
	addChoice(opts) { // the current chain and scale as a choice for one original game font; returns a copy
		const c = makeChoice(opts);
		state.choices.push(c); changed();
		return jsonCopy(c);
	},
	choices: () => jsonCopy(state.choices),
	removeChoice(i) {
		if (!Number.isInteger(i) || i < 0 || i >= state.choices.length) fail(`removeChoice: no choice ${i}`);
		state.choices.splice(i, 1); changed();
	},
	exportJSON: exportText,
	setText(s) { // over-long text is refused before it is stored: the status line says why, the text stays as it was
		s = String(s);
		const n = s.length > MAX_TEXT_BYTES ? s.length : new TextEncoder().encode(s).length; // UTF-8 bytes >= UTF-16 length
		if (n > MAX_TEXT_BYTES) {
			const msg = `text is ${s.length > MAX_TEXT_BYTES ? 'at least ' : ''}${n} bytes, the limit is ${MAX_TEXT_BYTES}`;
			ui.error?.({ errName: msg });
			fail(msg);
		}
		state.text = s; ui.inputs?.();
	},
	setScale(num, den) {
		for (const v of [num, den]) if (!Number.isInteger(v) || v < 1 || v > 16) fail(`setScale: ${num}/${den}: each must be an integer 1..16`);
		state.num = num; state.den = den; ui.inputs?.();
		writeUrl();
	},
	setTarget,
	render,
	chain: () => ({ latin: state.latin, hangul: state.hangul }), // the keys of the open chain
	lacking, // (text = the sample text) -> {key: n}: for each face fetched so far, how many distinct code points of text it lacks
	prefetch(key, keep = []) { // fetch a face into the heap without opening it; serialised with select. The chain is protected anyway
		const run = state.queue.then(() => fetchFace(key, [key, ...keep]));
		state.queue = run.catch(() => {});
		return run.then(f => f.len);
	},
	holdHeap() { let release; const gate = new Promise(r => { release = r; }); heapJob(() => gate); return () => release(); }, // test hook: blocks the heap lock until the returned function is called (the gate exists before the job starts: an early release is not lost)
	pendingKeys: () => state.pending && [...state.pending], // test hook: the keys of the select in flight, null when none
	prefetching: () => state.prefetchRun, // test hook: resolves with the result of the latest loop
	async idle() { for (let h; h !== state.heap;) { h = state.heap; await h; } }, // test hook: resolves when no heap job is queued or running

	module: () => state.M, // test hook
	spyAfterPick(fn) { const next = ui.afterPick; ui.afterPick = (...a) => { fn(...a); return next(...a); }; }, // test hook: fn runs before every ui.afterPick
	licence: url => licenceText(url), // test hook: the pane's text for a licence URL (cached: the same request)
	runs: line => runsOf(String(line)).map(r => ({ hangul: r.hangul, text: r.text })), // test hook: how render splits a line
	pixels: () => (state.drawn ? { ...state.drawn, bytes: Array.from(state.M.HEAPU8.subarray(state.pix.ptr, state.pix.ptr + state.drawn.len)) } : null), // test hook
	settings: () => ({ text: state.text, num: state.num, den: state.den, target: { ...state.target } }), // test hook
	faceMemory: () => ({ keys: [...state.files.keys()], bytes: state.faceBytes, budget: state.faceBudget }),
	setFaceBudget(n) { if (!Number.isInteger(n) || n < 1) fail('setFaceBudget: a positive integer'); state.faceBudget = n; }, // test hook
	// how many code points of text the open chain draws (svf_has of each face; the first face to hold one counts it)
	covers(text) {
		let n = 0;
		for (const ch of String(text)) {
			for (let slot = 0; slot < state.infos.length; slot++) if (state.M._svfw_has(slot, ch.codePointAt(0))) { n++; break; }
		}
		return n;
	},
};
window.picker = picker;

// ---- the UI -------------------------------------------------------------------------------------------------------
const ui = {};
const $ = id => document.getElementById(id);
const keyFile = k => k.slice(k.lastIndexOf('/') + 1);
const fileOf = f => keyFile(f.key);
const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };

function setStatus(parts, bad) {
	const s = $('status');
	s.replaceChildren(...parts.map(p => el('span', bad ? 'err' : '', p)));
}

function repaint() {
	return picker.render();
}

ui.error = r => setStatus([r.errName], true);

ui.paint = (img, r) => {
	const c = $('preview');
	c.width = img.width; c.height = img.height;
	c.getContext('2d').putImageData(img, 0, 0);
	const z = state.target.zoom;
	c.style.width = img.width * z + 'px'; c.style.height = img.height * z + 'px';
	const g = $('gridlines');
	g.hidden = !(state.target.grid && z >= 3);
	g.style.backgroundImage = 'linear-gradient(to right,var(--grid) 1px,transparent 1px),linear-gradient(to bottom,var(--grid) 1px,transparent 1px)';
	g.style.backgroundSize = `${z}px ${z}px`;
	queueScan();
	const h = state.infos[state.infos.length - 1];
	$('measure').textContent = `${r.width} x ${r.ascent}+${r.descent}`;
	$('px').textContent = h ? `= ${Math.ceil(h.cellH * state.num / state.den)} px high` : '';
	setStatus([`measure ${r.width} wide, ascent ${r.ascent}, descent ${r.descent}`, `${r.ms.toFixed(1)} ms`, `ink ${r.ink} px`, `canvas ${img.width} x ${img.height}`]);
};

// the mark text of a lack count: "-n" for n code points the face does not draw, "!" when the face file did not open
const markText = n => (n < 0 ? '!' : '-' + n);

// a row's mark: the picked face's (the row's data-key); its title lists every fetched variant, "NGOTB16.SVF -0, NGOTB15.SVF -3"
function rowMark(row, lack) {
	const key = row.li.dataset.key, n = lack[key] ?? 0;
	const seen = row.fam.faces.filter(k => k in lack).map(k => `${keyFile(k)} ${markText(lack[k])}`).join(', ');
	const gone = !(key in lack) && !state.files.has(key) ? state.marks.get(key) : null; // not in memory: "?" (not fetched, evicted) or "!" (failed)
	return gone ? { text: gone.mark, title: gone.title, list: seen } : { text: n ? markText(n) : '', title: seen, list: seen };
}

// A lack scan on the heap lock, one queued at a time; it reads the chain, the text and the shown size when it runs
function queueScan() {
	if (state.scanQueued) return;
	state.scanQueued = true;
	heapJob(() => {
		state.scanQueued = false;
		try { markLacking(); } catch (err) { setStatus([err.message], true); }
	});
}

// the rows and the variant chips: a face fetched already that lacks code points of the current text carries its mark
function markLacking() {
	const lack = lacking(state.text, state.rows.flatMap(r => r.fam.faces)); // the shown size's faces and the chain
	const put = (host, text, title) => {
		let m = host.querySelector(':scope > .lack');
		if (!text) { m?.remove(); return; }
		if (!m) { m = el('span', 'badge lack'); host.append(m); }
		m.textContent = text; m.title = title;
	};
	for (const row of state.rows) {
		const mk = rowMark(row, lack);
		row.li.title = mk.list; // the per-variant list, also when the picked face's own mark is absent
		put(row.li, mk.text, mk.title); // a "-n" mark means the picked face is fetched, so its own entry is in the title
	}
	for (const b of $('variants').querySelectorAll('[data-key]')) {
		const n = lack[b.dataset.key] ?? 0, gone = !(b.dataset.key in lack) && !state.files.has(b.dataset.key) ? state.marks.get(b.dataset.key) : null;
		if (gone) put(b, gone.mark, gone.title);
		else put(b, n ? markText(n) : '', n < 0 ? 'this face file did not open' : `${n} code point${n > 1 ? 's' : ''} of the sample text this face does not draw`);
	}
}

const licenceCache = new Map();
async function licenceText(url) {
	if (!licenceCache.has(url)) {
		let abs;
		try { abs = safeUrl(url); } catch (err) { return `(${err.message})`; }
		licenceCache.set(url, fetch(abs, { redirect: 'error' }).then(async r => r.ok ? new TextDecoder().decode(await readBounded(r, MAX_LICENCE_BYTES, url)) : (r.body?.cancel().catch(() => {}), `(${url}: HTTP ${r.status})`)).catch(err => `(${err.message.startsWith(url + ':') ? '' : url + ': '}${err.message})`)); // readBounded names url itself
	}
	return licenceCache.get(url);
}

function faceCard(role, key, info) {
	const f = state.byKey.get(key);
	const card = el('div', 'facecard');
	card.append(el('h3', '', role), el('p', 'sub', f.label)); // label: where the face comes from
	const dl = el('dl', 'kv');
	const rows = [['family', f.family || '-'], ['style', f.style || '-'], ['variant', f.variant || '-'], ['file', f.key], ['bpp', info.bpp], ['cell', `${info.cellW} x ${info.cellH}`], ['ascent', info.ascent],
		['glyphs', info.glyphs], ['jamo set', info.jamo ? 'yes' : 'no'], ['status', '0x' + info.status.toString(16)],
		['flags', '0x' + info.flags.toString(16)], ['bytes', f.bytes]];
	for (const [k, v] of rows) { dl.append(el('dt', '', k), el('dd', '', String(v))); }
	card.append(dl);
	for (const url of f.licences) {
		const d = el('details'), pre = el('pre', 'licence', 'loading...');
		d.open = true;
		d.append(el('summary', '', url.slice(url.lastIndexOf('/') + 1)), pre);
		card.append(d);
		licenceText(url).then(t => { pre.textContent = t; });
	}
	return card;
}

function showCards() {
	const box = $('cards');
	box.replaceChildren();
	$('card-empty').hidden = state.hangul !== null;
	const hanInfo = state.infos[state.infos.length - 1];
	if (state.latin && state.latin === state.hangul) box.append(faceCard('Latin and Hangul', state.hangul, hanInfo)); // one face, one card, one licence pane
	else {
		if (state.latin) box.append(faceCard('Latin', state.latin, state.infos[0]));
		if (state.hangul) box.append(faceCard('Hangul', state.hangul, hanInfo));
	}
}

// The rows of the shown size follow the chain: the row of the Hangul face is selected (inset bar) and its data-key is that
// face, every other row's is its default; the row holding the Latin face carries a "Latin" tag (the Hangul one "Hangul").
function syncRows() {
	const h = state.byKey.get(state.hangul);
	state.selRow = h && isLeft(h) && h.px === state.px ? famKey(h) : null;
	let sel = null;
	for (const row of state.rows) {
		const on = row.k === state.selRow, lat = state.latin !== null && row.fam.faces.includes(state.latin), han = on || (state.hangul !== null && row.fam.faces.includes(state.hangul));
		if (on) sel = row;
		row.li.dataset.key = on ? state.hangul : row.fam.default;
		row.li.setAttribute('aria-selected', String(on));
		row.li.dataset.role = [lat && 'latin', han && 'hangul'].filter(Boolean).join(' ');
		row.tags.replaceChildren(...[lat && 'Latin', han && 'Hangul'].filter(Boolean).map(t => el('span', 'badge role ' + t.toLowerCase(), t)));
	}
	buildStrip(sel);
	setActive(sel); // null when no row is selected: no active descendant, no active styling
	syncSlots();
	queueScan();
}

// After any select: the shown size is the Hangul face's when that is a left-list face, else it stays and no row is selected.
function followChain() {
	const h = state.byKey.get(state.hangul);
	if (h && isLeft(h) && h.px !== state.px) showSize(h.px); else syncRows();
}

ui.chain = () => {
	showCards(); followChain(); // followChain ends in syncRows, which brings the two selects, badges and notes along
};
ui.afterPick = () => { picker.setSize(state.px).catch(err => setStatus([err.message], true)); }; // a pick, a chip or a selector change: fetch the shown size

// the face words of a chip and of a select option: "2 bpp precomposed 16x16"
const kindWord = f => (f.jamo ? 'jamo set' : 'precomposed');
const faceWords = f => `${f.bpp} bpp ${kindWord(f)} ${f.cell[0]}x${f.cell[1]}`;
const famName = f => (f.family + (f.style ? ' ' + f.style : '')).trim();
const stemOf = f => fileOf(f).replace(/\.svf$/i, '');
// the Hangul select offers whole Hangul faces; the Latin select also the Latin-only ones; a subset face is in neither
const offeredLatin = f => !f.subset, offeredHangul = isLeft;

// The two selects follow the chain: a face the select does not offer gets a transient option "FILE (hidden: subset face)" /
// "FILE (Latin-only face)" while it is in that slot; the "= list" badges, and the line under each select.
function syncSlots() {
	const L = state.byKey.get(state.latin), H = state.byKey.get(state.hangul);
	for (const [id, f, offered] of [['latin', L, offeredLatin], ['hangul', H, offeredHangul]]) {
		const sel = $(id);
		sel.querySelectorAll('option[data-transient]').forEach(o => o.remove());
		if (f && !offered(f)) {
			const o = el('option', '', `${fileOf(f)} (${f.subset ? 'hidden: subset face' : 'Latin-only face'})`);
			o.value = f.key; o.dataset.transient = ''; sel.append(o);
		}
		sel.value = f ? f.key : '';
	}
	// with no Hangul face open nothing in the Latin select can be chosen ("(none)" means the Hangul face's own ASCII, and a select needs a Hangul face)
	for (const o of $('latin').querySelectorAll('option')) o.disabled = !state.hangul;
	const same = picker.view().same;
	$('latin-badge').hidden = $('hangul-badge').hidden = !same;
	const notIn = (f, name) => `${name} ${f.px} px is a ${f.subset ? 'hidden subset face' : 'Latin-only face'}: not in the list`;
	const ln = $('latin-note'), hn = $('hangul-note');
	ln.replaceChildren(); hn.replaceChildren();
	if (L && !isLeft(L)) ln.append(`Latin: ${notIn(L, L.subset ? stemOf(L) : famName(L))}`);
	else if (L && L.px !== state.px) {
		const b = el('button', '', `(list shows ${state.px} px)`);
		b.type = 'button'; b.title = `show ${L.px} px in the list`;
		b.addEventListener('click', () => picker.setSize(L.px).catch(err => setStatus([err.message], true)));
		ln.append(`Latin: ${famName(L)} ${L.px} px `, b);
	}
	if (H && !isLeft(H)) hn.append(`Hangul: ${notIn(H, stemOf(H))}`);
}

// A prefetch line is appended to the URL notices ("; "), so a URL fault outlives the first prefetch; the summary or failure line
// of a loop, and also its "stopped" line (a chip move is an action that clears the notice), end their life.
function loopNotice(text) {
	setNotice(state.urlNotice ? state.urlNotice + '; ' + text : text);
	state.urlNotice = '';
}

function setNotice(text) {
	$('notice').textContent = text; $('notice').hidden = !text;
}

// the inputs show the state the API holds (a driver may have set it)
ui.inputs = () => {
	const T = state.target;
	if ($('text').value !== state.text) $('text').value = state.text;
	$('num').value = state.num; $('den').value = state.den;
	$('ratio').value = RATIOS.some(([n, d]) => n === state.num && d === state.den) ? `${state.num}/${state.den}` : '';
	for (const r of document.querySelectorAll('input[name=kind]')) r.checked = r.value === T.kind;
	$('fg').value = T.fg; $('bg').value = T.bg; $('threshold').value = T.threshold;
	$('zoom').value = T.zoom; $('grid').checked = T.grid;
	$('grid').disabled = T.zoom < 3; // the grid lines need at least 3 screen pixels a pixel
	$('grid').title = T.zoom < 3 ? 'the pixel grid shows from zoom 3' : '';
	$('thr-wrap').hidden = T.kind !== 'mono';
	// RGB565 keeps 5/6/5 bits of each colour: show what the picker values become, expanded back to 8 bits
	const q = h => { const v = hexTo565(h), x = [x8(v >> 11, 5), x8((v >> 5) & 63, 6), x8(v & 31, 5)]; return '#' + x.map(n => n.toString(16).padStart(2, '0')).join(''); };
	$('q565').hidden = T.kind !== 'rgb565';
	$('q565').textContent = `RGB565: ink ${q(T.fg)}, paper ${q(T.bg)}`;
};

// A failed pick from the page: the old notice (a URL fault, an earlier summary) is not about this action and goes.
const clearNotice = () => { state.urlNotice = ''; setNotice(''); };

async function choose(latin, hangul) { // true when the select went through
	try {
		await select({ latin, hangul });
	} catch (err) {
		setStatus([err.message], true); // the face that failed is named
		syncSlots(); // a select whose face did not load shows the slot's face again (the chain is untouched when the fetch failed)
		return false;
	}
	ui.afterPick();
	repaint();
	return true;
}

// A row or chip click picks a left-list face as the whole chain; a failure is named on the status line
async function pickUi(key) {
	try { await picker.pick(key); } catch (err) { setStatus([err.message], true); clearNotice(); return; }
	ui.afterPick();
	repaint();
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// the shown size: its chip is pressed, #faces holds one row a family, the strip follows the selected row. No fetching.
function showSize(px) {
	const fams = state.fams.get(px) ?? fail(`showSize: no faces of ${px} px`);
	if (state.px !== px) state.prefetchGen++; // a loop for the size that was shown stops
	state.px = px;
	for (const b of $('sizes').children) { const on = +b.dataset.px === px; b.setAttribute('aria-checked', String(on)); b.tabIndex = on ? 0 : -1; }
	const ul = $('faces');
	ul.replaceChildren(); state.rows = []; state.active = null; ul.removeAttribute('aria-activedescendant');
	for (const [k, fam] of fams) {
		const i = state.rows.length, li = el('li');
		li.id = 'fam-' + i; li.dataset.fam = k; li.setAttribute('role', 'option');
		const name = el('span', 'name', fam.name); name.id = `fam-${i}-name`;
		li.append(name);
		if (fam.faces.length > 1) {
			const jamo = fam.faces.filter(f => state.byKey.get(f).jamo).length, pre = fam.faces.length - jamo;
			const c = el('span', 'count', '· ' + fam.faces.length);
			c.title = [pre && plural(pre, 'precomposed', 'precomposed'), jamo && plural(jamo, 'jamo set', 'jamo sets')].filter(Boolean).join(', ');
			li.append(c);
		}
		const tags = el('span', 'tags'); li.append(tags); // "Latin" / "Hangul" while the row holds that face of the chain
		const row = { k, fam, li, name, tags, hay: null };
		li.addEventListener('click', () => { setActive(row); pickUi(row.fam.default); }); // a row click is the family as it comes
		state.rows.push(row); ul.append(li);
	}
	state.stripFor = null;
	syncRows();
	filterList();
}

function setActive(row) {
	state.active?.li.classList.remove('active');
	state.active = row;
	if (!row) { $('faces').removeAttribute('aria-activedescendant'); return; }
	row.li.classList.add('active');
	$('faces').setAttribute('aria-activedescendant', row.li.id);
	const ul = $('faces'), a = row.li.getBoundingClientRect(), b = ul.getBoundingClientRect(); // scroll the list only: scrollIntoView moves the window too
	if (a.top < b.top) ul.scrollTop -= b.top - a.top;
	else if (a.bottom > b.bottom) ul.scrollTop += a.bottom - b.bottom;
}

// the variant strip of the selected row (null: hidden); its buttons are kept while the same row stays selected
function buildStrip(row) {
	const box = $('variants'), sub = $('variants-sub');
	if (!row) {
		box.hidden = sub.hidden = true; state.stripFor = null; box.replaceChildren(); box.removeAttribute('aria-labelledby'); return; }
	const id = row.k + '@' + state.px;
	if (state.stripFor !== id) {
		state.stripFor = id;
		const fs = row.fam.faces.map(k => state.byKey.get(k));
		const axes = {
			bpp: f => `${f.bpp} bpp`, kind: f => (f.jamo ? 'jamo set' : 'precomposed'), cell: f => `${f.cell[0]}x${f.cell[1]}`, variant: f => f.variant,
		};
		const differ = Object.fromEntries(Object.entries(axes).map(([a, get]) => [a, new Set(fs.map(get)).size > 1]));
		const same = [];
		if (!differ.bpp) same.push(axes.bpp(fs[0]));
		if (!differ.kind) same.push(fs[0].jamo ? 'jamo sets' : 'precomposed');
		const subParts = [same.join(' ')].filter(Boolean);
		if (!differ.cell) subParts.push(axes.cell(fs[0]));
		if (!differ.variant && fs[0].variant) subParts.push(fs[0].variant);
		sub.textContent = subParts.length ? 'all ' + subParts.join(', ') : '';
		$('variants-at').textContent = `at ${state.px} px`;
		box.setAttribute('aria-labelledby', `variants-of ${row.name.id} variants-at`); // "Variant of NanumGothic Bold at 16 px"
		box.replaceChildren(...fs.map(f => {
			const b = el('button'), parts = ['bpp', 'kind', 'cell', 'variant'].filter(a => differ[a]).map(a => axes[a](f)).filter(Boolean);
			b.type = 'button'; b.setAttribute('role', 'radio'); b.dataset.key = f.key;
			if (parts.length) b.append(el('span', 'lbl', parts.join(', '))); // axes shared by every chip live in the subtitle only
			b.append(el('small', '', fileOf(f)));
			b.addEventListener('click', ev => { ev.stopPropagation(); pickUi(f.key); });
			return b;
		}));
	}
	const shown = !row.li.hidden; // a search that hides the selected row hides its strip
	box.hidden = !shown; sub.hidden = !shown || !sub.textContent;
	for (const b of box.children) { const on = b.dataset.key === state.hangul; b.setAttribute('aria-checked', String(on)); b.tabIndex = on ? 0 : -1; }
}

// the search over the shown size: family, style, variant and file name of any of a row's faces
const hayOfFam = fam => [fam.name, ...fam.faces.map(k => { const f = state.byKey.get(k); return `${f.variant} ${fileOf(f)}`; })].join('\n').toLowerCase();
const hayOf = row => (row.hay ??= hayOfFam(row.fam));

function filterList() {
	const q = $('f-name').value.trim().toLowerCase();
	let n = 0;
	for (const row of state.rows) { row.li.hidden = !!q && !hayOf(row).includes(q); if (!row.li.hidden) n++; }
	if (state.active?.li.hidden) setActive(null);
	const fams = state.fams.get(state.px);
	const nf = fams ? [...fams.values()].reduce((m, f) => m + f.faces.length, 0) : 0;
	$('count').textContent = q ? `${n} of ${state.rows.length}` : `${state.rows.length} families · ${nf} faces`;
	buildStrip(state.rows.find(r => r.k === state.selRow) ?? null);
	const also = $('also'), others = [];
	if (q && !n) { // the search matches nothing here: say where it does
		for (const px of picker.sizes()) {
			if (px === state.px) continue;
			const m = [...state.fams.get(px).values()].filter(f => hayOfFam(f).includes(q)).length;
			if (m) others.push([px, m]);
		}
	}
	also.hidden = !others.length;
	also.replaceChildren(...(others.length ? ['also at '] : []));
	others.forEach(([px, m], i) => {
		const b = el('button', '', px + ' px');
		b.type = 'button'; b.title = plural(m, 'family', 'families');
		b.addEventListener('click', () => picker.setSize(px).catch(err => setStatus([err.message], true)));
		also.append(...(i ? [', '] : []), b);
	});
}

// Arrow keys move a radio group (size chips, variant chips) and apply the chip they land on; Home / End jump to the ends
function radioKeys(group, apply) {
	const step = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 };
	group.addEventListener('keydown', ev => {
		const bs = [...group.querySelectorAll('[role="radio"]')], i = bs.indexOf(ev.target.closest('[role="radio"]'));
		if (i < 0 || ev.ctrlKey || ev.metaKey || ev.altKey) return;
		const j = ev.key in step ? (i + step[ev.key] + bs.length) % bs.length : ev.key === 'Home' ? 0 : ev.key === 'End' ? bs.length - 1 : -1;
		if (j < 0) return;
		ev.preventDefault();
		bs[j].focus(); apply(bs[j]);
	});
}

// The listbox keeps focus on #faces; aria-activedescendant names the active row. Up / Down / Home / End move it, Enter and
// Space pick it, letters jump to the next visible family starting with what was typed (from the active row on, wrapping;
// one letter repeated steps through the families starting with it).
function listboxKeys(ul) {
	const visible = () => state.rows.filter(r => !r.li.hidden);
	let typed = '', last = 0;
	// a focus that a mouse press caused must not scroll: the press would land on another row and the click would be lost
	let pressed = false;
	ul.addEventListener('mousedown', () => { pressed = true; setTimeout(() => { pressed = false; }, 0); });
	ul.addEventListener('focus', () => { // the selected row, else the first visible one
		if (pressed) return;
		const v = visible();
		setActive(v.find(r => r.k === state.selRow) ?? v[0] ?? null);
	});
	ul.addEventListener('keydown', ev => {
		if (ev.ctrlKey || ev.metaKey || ev.altKey) return;
		const v = visible(), i = v.indexOf(state.active);
		if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp' || ev.key === 'Home' || ev.key === 'End') {
			ev.preventDefault();
			if (v.length) setActive(v[ev.key === 'Home' ? 0 : ev.key === 'End' ? v.length - 1 : ev.key === 'ArrowDown' ? Math.min(i + 1, v.length - 1) : Math.max(i - 1, 0)]);
		} else if (ev.key === 'Enter' || ev.key === ' ') { // Space picks even in the middle of type-ahead
			ev.preventDefault();
			typed = '';
			if (state.active) pickUi(state.active.fam.default);
		} else if (ev.key.length === 1) {
			const now = Date.now();
			typed = now - last > 800 ? ev.key.toLowerCase() : typed + ev.key.toLowerCase();
			last = now;
			const one = [...typed].every(c => c === typed[0]), q = one ? typed[0] : typed;
			// a new letter (or a repeated one) looks past the active row; a longer prefix may stay on it
			const from = i < 0 ? 0 : q.length === 1 ? i + 1 : i;
			const hit = v.map((_, j) => v[(from + j) % v.length]).find(r => r.fam.name.toLowerCase().startsWith(q));
			if (hit) setActive(hit);
			ev.preventDefault();
		}
	});
}

function buildControls() {
	const faces = state.index.faces;
	const bar = $('sizes');
	for (const px of picker.sizes()) {
		const fams = state.fams.get(px), b = el('button', '', px + ' px');
		b.type = 'button'; b.setAttribute('role', 'radio'); b.setAttribute('aria-checked', 'false'); b.dataset.px = px; b.tabIndex = -1;
		b.title = `${plural(fams.size, 'family', 'families')}, ${plural([...fams.values()].reduce((n, f) => n + f.faces.length, 0), 'face', 'faces')}`;
		b.addEventListener('click', ev => { ev.stopPropagation(); picker.setSize(px).catch(err => setStatus([err.message], true)); });
		bar.append(b);
	}
	radioKeys(bar, b => picker.setSize(+b.dataset.px).catch(err => setStatus([err.message], true)));
	radioKeys($('variants'), b => pickUi(b.dataset.key));
	listboxKeys($('faces'));
	const lat = $('latin'), han = $('hangul');
	const none = el('option', '', '(none: the Hangul face\'s own ASCII)'); none.value = ''; lat.append(none);
	// "(none)" is a placeholder shown until a Hangul face is open; it cannot be chosen (a chain needs a Hangul face)
	const noHangul = el('option', '', '(none)'); noHangul.value = ''; noHangul.disabled = true; han.append(noHangul);
	// options in one <optgroup> per size, a family's faces together; a Latin-only face of the Latin select says so
	const ci = (a, b) => { a = a.toLowerCase(); b = b.toLowerCase(); return a < b ? -1 : a > b ? 1 : 0; };
	for (const [sel, offered, latinSel] of [[lat, offeredLatin, true], [han, offeredHangul, false]]) {
		const byPx = new Map();
		for (const f of faces.filter(offered)) { if (!byPx.has(f.px)) byPx.set(f.px, []); byPx.get(f.px).push(f); }
		for (const px of [...byPx.keys()].sort((a, b) => a - b)) {
			const og = el('optgroup');
			og.label = px + ' px';
			for (const f of byPx.get(px).sort((a, b) => ci(a.family, b.family) || ci(a.style, b.style) || rankFace(a, b))) {
				const o = el('option', '', `${famName(f)} · ${faceWords(f)} · ${fileOf(f)}${latinSel && f.latin_only ? ' · Latin only' : ''}`);
				o.value = f.key; og.append(o);
			}
			sel.append(og);
		}
	}
	lat.value = han.value = ''; // no face open yet: "(none)" in both
	$('f-name').addEventListener('input', filterList);
	lat.addEventListener('change', async () => { if (!await choose(lat.value || null, state.hangul)) clearNotice(); });
	han.addEventListener('change', async () => { if (!await choose(state.latin, han.value)) clearNotice(); });
	const ratio = $('ratio');
	const custom = el('option', '', 'custom'); custom.value = ''; ratio.append(custom);
	for (const [n, d] of RATIOS) { const o = el('option', '', d === 1 ? String(n) : `${n}/${d}`); o.value = `${n}/${d}`; if (n === d) o.selected = true; ratio.append(o); }
	// Number fields: while typing ('input') only a valid value is applied, anything else is left in the field (so it can be
	// cleared and retyped) with the reason on the status line; on 'change' (commit, blur) the field shows the state again.
	const whole = (id, lo, hi) => { const v = $(id).value.trim(); return /^\d+$/.test(v) && +v >= lo && +v <= hi ? +v : null; };
	const applyScale = () => {
		const n = whole('num', 1, 16), d = whole('den', 1, 16);
		if (n === null || d === null) { setStatus([`scale ${$('num').value}/${$('den').value}: each must be an integer 1..16`], true); return; }
		picker.setScale(n, d);
		repaint();
	};
	ratio.addEventListener('change', () => { if (!ratio.value) return; const [n, d] = ratio.value.split('/'); $('num').value = n; $('den').value = d; applyScale(); });
	const restore = () => { ui.inputs(); repaint(); }; // the field shows the state again; the repaint replaces its error
	for (const id of ['num', 'den']) { $(id).addEventListener('input', applyScale); $(id).addEventListener('change', restore); }
	const text = $('text');
	text.value = state.text;
	// a refused text: the textarea goes back to the text the picker holds; setText has put the reason on the status line
	text.addEventListener('input', () => { try { picker.setText(text.value); } catch { ui.inputs(); return; } repaint(); });
	for (const k of Object.keys(PRESETS)) {
		const b = el('button', '', PRESET_LABELS[k]);
		b.addEventListener('click', () => { text.value = PRESETS[k]; try { picker.setText(text.value); } catch { ui.inputs(); return; } repaint(); });
		$('presets').append(b);
	}
	// an invalid #zoom / #threshold refuses only its own edit; a change of another control applies with the held value
	const tgt = ev => {
		const t = { kind: document.querySelector('input[name=kind]:checked').value, fg: $('fg').value, bg: $('bg').value, grid: $('grid').checked };
		const bad = [];
		for (const [id, hi] of [['zoom', 8], ['threshold', 255]]) {
			const v = whole(id, 1, hi);
			if (v === null) bad.push(`${id} ${$(id).value}: an integer 1..${hi}`); else t[id] = v;
		}
		if (bad.length && ['zoom', 'threshold'].includes(ev?.target?.id)) { setStatus(bad, true); return; }
		try { picker.setTarget(t); } catch (err) { setStatus([err.message], true); ui.inputs(); return; }
		repaint();
	};
	for (const id of ['fg', 'bg', 'threshold', 'zoom', 'grid']) $(id).addEventListener('input', tgt);
	for (const id of ['threshold', 'zoom']) $(id).addEventListener('change', restore);
	for (const r of document.querySelectorAll('input[name=kind]')) r.addEventListener('change', tgt);
	$('zoom').value = state.target.zoom;
}

// ---- the choices panel: form, table, export box ---------------------------------------------------------------------
// "Family Style · variant words" of a face as the lists show it; a face the index does not know shows what the choice stored
const wordsOfFace = f => {
	const name = (famName(f) || f.label || '').trim();
	return f.variant ? `${name} · ${f.variant}` : name;
};
function faceCell(key, stored, withMark) {
	const td = el('td'), f = state.byKey.get(key);
	if (f) td.append(wordsOfFace(f));
	else td.append(typeof stored?.family === 'string' && stored.family ? wordsOfFace({ ...stored, label: stored.label }) : keyFile(key));
	td.append(' ', el('small', 'file', keyFile(key)));
	if (!f && withMark) td.append(' ', el('span', 'mark', 'not in this index'));
	return td;
}

async function openChoice(c) { // the chain and scale of a choice; hidden and subset faces open through select as ever
	const k = c.korean;
	const [num, den] = [state.num, state.den];
	picker.setScale(k.scale[0], k.scale[1]);
	if (!await choose(k.latin, k.key)) picker.setScale(num, den); // a failed select leaves the page as it was
}

ui.choices = () => {
	const body = $('choice-rows');
	body.replaceChildren();
	state.choices.forEach((c, i) => {
		const k = c.korean, tr = el('tr');
		const hangul = faceCell(k.key, k, true), latin = k.latin === null ? el('td', '', '(none)') : faceCell(k.latin, null, true);
		const unknown = !state.byKey.has(k.key) || (k.latin !== null && !state.byKey.has(k.latin));
		const open = el('button', '', 'Open'), rm = el('button', '', 'Remove');
		open.type = rm.type = 'button'; open.dataset.act = 'open'; rm.dataset.act = 'remove';
		open.disabled = unknown; open.title = unknown ? 'a face of this choice is not in this index' : 'open this chain and scale';
		open.addEventListener('click', () => { openChoice(c).catch(err => setStatus([err.message], true)); });
		rm.addEventListener('click', () => picker.removeChoice(i));
		const act = el('td', 'act'); act.append(open, ' ', rm);
		tr.append(el('td', '', c.game), el('td', '', c.id), el('td', '', c.lineh === undefined ? '' : String(c.lineh)), hangul, latin,
			el('td', '', k.scale.join('/')), el('td', '', `${k.w} x ${k.h}`), act);
		body.append(tr);
	});
	$('choice-count').textContent = plural(state.choices.length, 'choice', 'choices');
	$('choice-empty').hidden = state.choices.length > 0;
	$('choice-table').hidden = state.choices.length === 0;
	$('export').value = exportText();
};

function buildChoices() {
	for (const g of GAMES) { const o = el('option'); o.value = g; $('choice-games').append(o); }
	$('choice-form').addEventListener('submit', ev => {
		ev.preventDefault();
		const lh = $('choice-lineh').value.trim();
		try {
			if (lh !== '' && !/^\d+$/.test(lh)) fail(`line height ${lh}: an integer or empty`);
			picker.addChoice({ game: $('choice-game').value, id: $('choice-id').value, lineh: lh === '' ? undefined : +lh });
			setStatus(['choice added']);
		} catch (err) { setStatus([err.message], true); }
	});
	$('choice-copy').addEventListener('click', async () => {
		const ta = $('export');
		try { await navigator.clipboard.writeText(ta.value); setStatus(['export copied']); } catch { ta.focus(); ta.select(); setStatus(['copy is not allowed here: the export is selected, press Ctrl+C'], true); }
	});
	$('choice-download').addEventListener('click', () => {
		const url = URL.createObjectURL(new Blob([$('export').value], { type: 'application/json' })), a = el('a');
		a.href = url; a.download = 'selection.json';
		document.body.append(a); a.click(); a.remove();
		setTimeout(() => URL.revokeObjectURL(url), 1000);
	});
}

// faces.json under the same rules as the faces: no redirect, at most MAX_INDEX_BYTES, every failure names the file
async function loadIndex() {
	let r;
	try { r = await fetch('faces.json', { redirect: 'error' }); } catch (err) { fail('faces.json: ' + err.message); }
	if (!r.ok) { r.body?.cancel().catch(() => {}); fail('faces.json: HTTP ' + r.status); }
	const bytes = await readBounded(r, MAX_INDEX_BYTES, 'faces.json').catch(err => fail(err.message.startsWith('faces.json') ? err.message : 'faces.json: ' + err.message));
	try { return JSON.parse(new TextDecoder().decode(bytes)); } catch (err) { fail('faces.json: ' + err.message); }
}

// faces.json as mkindex.py writes it, checked before any of it reaches the DOM or the heap; the first fault stops start()
const MAX_INDEX_FACES = 2048, MAX_FIELD = 256;
function checkIndex(index) {
	const bad = why => fail('faces.json: ' + why);
	if (!index || typeof index !== 'object' || index.format !== 'svf-fonts-web-index/1') bad('format must be "svf-fonts-web-index/1"');
	if (!index || typeof index !== 'object' || !Array.isArray(index.faces)) bad('no "faces" list');
	if (index.faces.length > MAX_INDEX_FACES) bad(`${index.faces.length} faces, the limit is ${MAX_INDEX_FACES}`);
	const str = v => typeof v === 'string' && v.length > 0 && v.length <= MAX_FIELD;
	const int = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
	const keys = new Set();
	index.faces.forEach((f, i) => {
		const at = why => bad(`face ${i}${f && typeof f.key === 'string' ? ' ' + JSON.stringify(f.key.slice(0, MAX_FIELD)) : ''}: ${why}`);
		if (!f || typeof f !== 'object' || Array.isArray(f)) at('not an object');
		for (const k of ['key', 'url', 'group', 'label']) if (!str(f[k])) at(`${k} must be a string of 1..${MAX_FIELD} characters`);
		if (keys.has(f.key)) at('duplicate key');
		const m = /^svf\/((?:[A-Za-z0-9._-]+\/){0,5}[A-Za-z0-9._-]+\.(?:SVF|svf))$/.exec(f.key);
		if (!m || m[1].split('/').some(seg => seg === '.' || seg === '..')) at('key must be svf/<rel> (1..6 segments of [A-Za-z0-9._-], ending in .SVF or .svf)');
		if (f.url !== 'faces/' + m[1]) at('url must be faces/<rel> for this key');
		if (f.group !== m[1].split('/').slice(0, -1).join('/')) at("group must be the key's directory");
		if (!Array.isArray(f.cell) || f.cell.length !== 2 || !f.cell.every(v => int(v, 1, 255))) at('cell must be [w, h], integers 1..255');
		if (![1, 2, 8].includes(f.bpp)) at('bpp must be 1, 2 or 8');
		if (!int(f.bytes, 1, MAX_FACE_BYTES)) at(`bytes must be an integer 1..${MAX_FACE_BYTES}`);
		for (const k of ['px', 'ascent', 'glyphs', 'flags']) if (!int(f[k], 0, 65535)) at(`${k} must be an integer 0..65535`);
		if (f.px !== f.cell[1]) at('px must equal cell[1]');
		if (typeof f.jamo !== 'boolean') at('jamo must be true or false');
		if (!int(f.hangul, 0, 2350)) at('hangul must be an integer 0..2350');
		if (typeof f.latin_only !== 'boolean') at('latin_only must be true or false');
		if (typeof f.subset !== 'boolean') at('subset must be true or false');
		if (f.subset !== (!f.jamo && !f.latin_only && f.hangul < 2350)) at('subset must equal (!jamo && !latin_only && hangul < 2350)');
		if (f.latin_only && (f.jamo || f.hangul !== 0)) at('latin_only requires jamo false and hangul 0');
		if (!f.subset && !(typeof f.family === 'string' && f.family.length >= 1 && f.family.length <= MAX_FIELD)) at(`family must be a string of 1..${MAX_FIELD} characters for a listed face`);
		for (const k of ['family', 'style', 'variant']) if (typeof f[k] !== 'string' || f[k].length > MAX_FIELD) at(`family, style and variant must be strings of at most ${MAX_FIELD} characters`);
		if (!Array.isArray(f.licences) || f.licences.length < 1 || f.licences.length > 16 || !f.licences.every(str)) at(`licences must be a list of 1..16 strings of 1..${MAX_FIELD} characters`);
		for (const u of f.licences) { try { safeUrl(u); } catch (err) { at('licence ' + err.message); } if (!u.startsWith('licences/')) at('licence URL must be under licences/: ' + u.slice(0, MAX_FIELD)); } // every face shows its licence, and only a licence
		keys.add(f.key);
	});
	const pxs = new Set(index.faces.map(f => f.px));
	if (pxs.size > 64) bad(`${pxs.size} distinct px values, the limit is 64`);
	return index;
}

async function main() {
	const [M, index] = await Promise.all([
		SvfModule(),
		loadIndex(),
	]);
	state.M = M; state.index = checkIndex(index);
	for (const f of index.faces) state.byKey.set(f.key, f);
	state.fams = buildFams(index.faces);
	buildControls();
	buildChoices();
	const sizes = picker.sizes();
	if (sizes.length) showSize(sizes.includes(16) ? 16 : sizes[0]);
	ui.inputs(); // the controls start from the state (zoom 2: the grid checkbox is disabled)
	setStatus([`${index.faces.length} faces`]);
}

// The query of the page: {latin, hangul, num, den, notices}. The raw query is measured before it is parsed: over MAX_QUERY
// characters (the '?' counts) it is never given to URLSearchParams; a key or a value over MAX_FIELD after parsing ignores it
// as well. Ignored: the defaults and the notice "URL ignored: too long". Every fault is a notice and a default, never an
// exception. manual: nothing is opened (hangul and latin come back null) but a bad face is still a notice, and the scale is read.
const MAX_QUERY = 2048;
// One source: URLSearchParams decides whether `manual` is present; only a query too long to parse is scanned (it is never parsed).
const isManual = q => q.length > MAX_QUERY ? /(?:^\?|&)manual(?:=|&|$)/.test(q) : new URLSearchParams(q).has('manual');
function readUrl(manual) {
	const out = { latin: null, hangul: null, num: 1, den: 1, notices: [] };
	const dflt = state.byKey.has(DEFAULT_HANGUL) ? DEFAULT_HANGUL : null;
	const q = location.search, params = q.length > MAX_QUERY ? null : new URLSearchParams(q);
	if (!params || [...params].some(([k, v]) => k.length > MAX_FIELD || v.length > MAX_FIELD)) {
		out.notices.push('URL ignored: too long');
		if (!manual) out.hangul = out.latin = dflt;
		return out;
	}
	let hangul = dflt;
	if (params.has('hangul')) {
		const key = params.get('hangul'), f = state.byKey.get(key), tail = manual ? 'nothing opened (?manual)' : dflt ? 'the default opened' : 'nothing opened';
		if (key === '') out.notices.push(`URL: hangul is empty; ${tail}`);
		else if (!f) out.notices.push(`URL: no face ${key}; ${tail}`);
		else if (!isLeft(f)) out.notices.push(`URL: ${key} is a ${f.latin_only ? 'Latin-only' : 'hidden subset'} face; ${tail}`);
		else hangul = key;
	}
	let latin = hangul; // absent: the Hangul face's own
	if (params.has('latin')) {
		const key = params.get('latin'), f = state.byKey.get(key);
		latin = null;
		if (key === '') { /* none */ }
		else if (!f) out.notices.push(`URL: no face ${key}; ${manual ? 'nothing opened (?manual)' : 'Latin none'}`);
		else if (f.subset) out.notices.push(`URL: ${key} is a hidden subset face; ${manual ? 'nothing opened (?manual)' : 'Latin none'}`);
		else latin = key;
	}
	if (!manual && hangul) { out.hangul = hangul; out.latin = latin; }
	if (params.has('scale')) {
		const v = params.get('scale'), m = /^(\d{1,2})\/(\d{1,2})$/.exec(v);
		if (m && +m[1] >= 1 && +m[1] <= 16 && +m[2] >= 1 && +m[2] <= 16) { out.num = +m[1]; out.den = +m[2]; }
		else out.notices.push(`URL: scale ${v} ignored`);
	}
	return out;
}

// After every successful select and scale change: the chain and the scale go into the query (replaceState: no history entry).
// Other parameters stay, except a key or value over MAX_FIELD; a query that would pass MAX_QUERY (or one too long to read) keeps
// only ?manual, so what the page writes is always read back by a reload. A chain the reader would refuse (a hidden or Latin-only
// Hangul face, a subset Latin face: a driver's select) is not written, and the old hangul and latin go. With no chain open
// (?manual before a select) only the scale is written.
function writeUrl() {
	try {
		const old = location.search, own = new URLSearchParams();
		// the other parameters stay as the page got them (byte for byte: no re-encoding), except our own, a key or a value over MAX_FIELD
		// and, for a query too long to read, everything but ?manual
		const keep = [], isOwn = k => k === 'hangul' || k === 'latin' || k === 'scale';
		if (old.length > MAX_QUERY) { if (isManual(old)) own.set('manual', ''); }
		else for (const seg of old.slice(1).split('&')) {
			if (!seg) continue;
			const [[k, v] = ['', '']] = new URLSearchParams(seg);
			if (k.length > MAX_FIELD || v.length > MAX_FIELD || isOwn(k)) continue;
			keep.push(seg);
		}
		const h = state.byKey.get(state.hangul), l = state.byKey.get(state.latin);
		if (h && isLeft(h) && !l?.subset) { own.set('hangul', state.hangul); own.set('latin', state.latin ?? ''); } // else: no chain the reader accepts, none written
		own.set('scale', `${state.num}/${state.den}`);
		let qs = '?' + [...keep, ...(own.toString() ? [own.toString()] : [])].join('&');
		if (qs.length > MAX_QUERY) { // keep only what the page itself writes
			const mine = new URLSearchParams(own);
			if (!mine.has('manual') && keep.some(seg => new URLSearchParams(seg).has('manual'))) mine.set('manual', '');
			qs = '?' + mine;
		}
		history.replaceState(history.state, '', location.pathname + qs + location.hash);
	} catch { /* a page without a history (sandboxed): the URL is a convenience */ }
}

// ready resolves after svf.js and faces.json are loaded AND the default pair (NGOTB16 in both slots) is open and drawn, so a
// caller that awaits ready and then selects is never overwritten by a late default. ?manual skips the default.
async function start() {
	await main();
	const manual = isManual(location.search), u = readUrl(manual);
	// the URL notices are shown now; the load prefetch appends its summary and then ends them. Under ?manual there is no load
	// prefetch, so nothing carries them to a later setSize; a URL chain that fails to load leaves no loop for them either.
	const stored = loadChoices(); // stored choices: an unreadable value is a notice beside the URL's
	state.choices = stored.list; ui.choices();
	const notices = [...(stored.notice ? [stored.notice] : []), ...u.notices];
	state.urlNotice = manual ? '' : notices.join('; ');
	if (notices.length) setNotice(notices.join('; '));
	picker.setScale(u.num, u.den); // the scale first: the select below writes the URL with it
	if (!manual && u.hangul) await choose(u.latin, u.hangul); // reports its own failure (the status line; the default is not tried instead)
	if (!state.hangul) state.urlNotice = '';
}
picker.ready = start();
picker.ready.catch(err => { setStatus([String(err.message ?? err)], true); });
