// render.mjs MODULE_DIR SPEC_JSON - draws a line with the WASM module (web/build.sh output in MODULE_DIR) under node and
// writes the target buffer's bytes to stdout.
//
// SPEC_JSON (the JSON text, or the path of a file holding it): {faces: [paths], text, scale: [num, den],
// kind: "gray8"|"mono_page"|"mono_row"|"rgb565", w, h, x, baseline, fg565, bg565, threshold, big_endian (optional,
// rgb565 high byte first), order (optional: svfw_order(order), the slot the chain tries first)}. The buffer starts zeroed, has the least stride of the kind (mono_page: SSD1306 pages,
// stride w, ceil(h/8) pages) and is drawn with svfw_target2. An array of specs is drawn in turn by one module instance
// (svfw_reset before each), the buffers written one after another.
// A call that fails exits 3 with "<call>: <svf_err name>" on stderr; bad arguments exit 2.
import { readFileSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const ERR = ['SVF_OK', 'SVF_E_MAGIC', 'SVF_E_VERSION', 'SVF_E_BPP', 'SVF_E_RANGE', 'SVF_E_NOMEM', 'SVF_E_IO',
	'SVF_E_ARG', 'SVF_E_LAYOUT'];
const KINDS = { gray8: 0, mono_page: 1, mono_row: 2, rgb565: 3 };
const SVF_TF_565_BIGENDIAN = 1;

const [dir, arg] = process.argv.slice(2);
if (!dir || !arg) {
	process.stderr.write('usage: render.mjs MODULE_DIR SPEC_JSON\n');
	process.exit(2);
}
const text = arg.trimStart().startsWith('{') || arg.trimStart().startsWith('[') ? arg : readFileSync(arg, 'utf8');
const specs = [].concat(JSON.parse(text));

const M = await (await import(pathToFileURL(join(resolve(dir), 'svf.js')).href)).default();

function check(call, e) {
	if (e !== 0) {
		process.stderr.write(`${call}: ${ERR[e] ?? 'svf_err ' + e}\n`);
		process.exit(3);
	}
}

function put(bytes) {
	const p = M._malloc(Math.max(bytes.length, 1));
	M.HEAPU8.set(bytes, p);
	return p;
}

const out = [];
for (const s of specs) {
	const kind = KINDS[s.kind];
	if (kind === undefined) {
		process.stderr.write(`render.mjs: unknown kind ${s.kind}\n`);
		process.exit(2);
	}
	check('svfw_reset', M._svfw_reset());
	const held = [];
	s.faces.forEach((path, slot) => {
		if (!existsSync(path)) {
			process.stderr.write(`render.mjs: no face ${path}\n`);
			process.exit(2);
		}
		const data = readFileSync(path);
		const p = put(data);
		held.push(p);
		check(`svfw_open ${path}`, M._svfw_open(slot, p, data.length));
	});
	if (s.order !== undefined) check('svfw_order', M._svfw_order(s.order));
	const [num, den] = s.scale ?? [1, 1];
	check('svfw_scale', M._svfw_scale(num, den));
	const stride = kind === 2 ? (s.w + 7) >> 3 : kind === 3 ? 2 * s.w : s.w;
	const len = stride * (kind === 1 ? (s.h + 7) >> 3 : s.h);
	const buf = M._malloc(Math.max(len, 1));
	M.HEAPU8.fill(0, buf, buf + len);
	check('svfw_target2', M._svfw_target2(kind, buf, len, s.w, s.h, stride, s.fg565 ?? 0xFFFF, s.bg565 ?? 0,
		s.threshold ?? 128, s.big_endian ? SVF_TF_565_BIGENDIAN : 0));
	const utf8 = new TextEncoder().encode(s.text);
	const t = put(utf8);
	check('svfw_draw', M._svfw_draw(t, utf8.length, s.x, s.baseline));
	out.push(Buffer.from(M.HEAPU8.slice(buf, buf + len)));
	M._free(t);
	M._free(buf);
	check('svfw_reset', M._svfw_reset()); // close the slots before their bytes are freed
	held.forEach(p => M._free(p));
}
process.stdout.write(Buffer.concat(out));
