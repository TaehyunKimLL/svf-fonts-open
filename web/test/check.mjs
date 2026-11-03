// check.mjs DIST OUT - drives the built page (web/build.sh output in DIST) in Chrome with playwright-core and writes
// OUT/browser.txt, OUT/faces-report.tsv, OUT/paplg18-chain.png (and OUT/page.png, the whole page).
//   Case A  every face of faces.json: select({latin: null, hangul: key}), text exactly pangram + ASCII, scale 1/1, GRAY8.
//           A face that holds at least one of those code points (picker.covers) must give err 0 and ink > 0.
//   Case supplement  the faces that hold none of them (the small per-game supplement faces) must give ink from the
//           supplement line. One row "key err ink ms case" a face goes to faces-report.tsv; counts of both go to cases.txt.
//   Case B  the controls. PAPLG18 over NGOTB16 at 2/1 GRAY8 -> paplg18-chain.png; NEODG16G 3/1 MONO threshold 128 ->
//           hgkey6j-mono.png; GBATB47 over NGOTB16 1/2 RGB565 #FFE000 on #203040 -> gbatb47-rgb565.png. controls.json:
//           width1/width2 (ASCII on PAPLG16 at 1/1 and 2/1), mono1/mono255 (GOTHA24A, threshold 1 and 255), licence_ok
//           (the PAPLG18 licence pane); the face list's "-n" marks equal picker.lacking().
//   Case fetch-once  every face file was requested exactly once over A, supplement and B (B selects twice).
//   Case C  without ?manual the default pair is open when ready resolves; a select after ready is not overwritten.
//   Case D  the UI: filter, row click, target MONO / RGB565 with configured colours (mono.png, rgb565.png).
//   Case E  hostile URLs in faces.json are rejected with no request; bad colours rejected; render errors reach the status;
//           over-long text is refused (typed text goes back to the text the picker holds).
//   Cases sizes (chips, rows, view, the selects' optgroups), pick (row / chip / select clicks, badges, notes), hidden in chain (a hidden face in a slot), keyboard (the groups and the listbox by keys), marks, bad face, transport (gzip, same-origin redirects, truncated licences), index (faces.json redirect and
//           size, schema), no stream (readBounded's fallback), surrogates, budget, dom (every control driven through
//           the page), export (two choices -> selection.json, export.png), choices (storage, validation, UI): see each case.
// Exit 0 all cases passed; 1 a case failed (named on stderr); 2 no browser launches or playwright-core is missing.
// The browser is Google Chrome (channel "chrome"); PICKER_BROWSER names another executable.
import { mkdirSync, writeFileSync, appendFileSync, readFileSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { startServer } from './serve.mjs';

const [dist, outArg] = process.argv.slice(2);
if (!dist || !outArg) { process.stderr.write('usage: check.mjs DIST OUT\n'); process.exit(2); }
const out = resolve(outArg);
const here = dirname(fileURLToPath(import.meta.url));

let chromium, pwVersion;
try {
	const require = createRequire(join(here, 'package.json'));
	({ chromium } = require('playwright-core'));
	pwVersion = JSON.parse(readFileSync(require.resolve('playwright-core/package.json'), 'utf8')).version;
} catch (err) {
	process.stderr.write(`check.mjs: playwright-core is missing (npm ci in web/test): ${err.message}\n`);
	process.exit(2);
}

mkdirSync(out, { recursive: true });
for (const f of ['browser.txt', 'cases.txt', 'mono.png', 'rgb565.png', 'page-ui.png', 'faces-report.tsv', 'paplg18-chain.png', 'hgkey6j-mono.png', 'gbatb47-rgb565.png', 'controls.json', 'page.png', 'page-default.png', 'runs.json', 'runs-split.json', 'selection.json', 'export.png']) rmSync(join(out, f), { force: true });
for (const n of ['mixed', 'mixed32', 'multiline', 'multiline32', 'fallback', 'lines']) for (const x of ['.bin', '.json']) rmSync(join(out, 'runs-' + n + x), { force: true }); // runs.json lists them

let browser;
try {
	browser = await chromium.launch(process.env.PICKER_BROWSER
		? { executablePath: process.env.PICKER_BROWSER, headless: true }
		: { channel: 'chrome', headless: true });
} catch (err) {
	process.stderr.write(`check.mjs: no browser launches: ${String(err.message).split('\n')[0]}\n`);
	process.exit(2);
}

const server = await startServer(dist);
let failed = null, nfailed = 0; // the first failure; how many so far (a case reports its summary only when it added none)
const fail = (name, why) => { failed ??= `${name}: ${why}`; nfailed++; process.stderr.write(`FAIL ${name}: ${why}\n`); };

try {
	const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
	const page = await ctx.newPage();
	const problems = [];
	page.on('pageerror', e => problems.push('pageerror ' + e.message));
	page.on('console', m => { if (m.type() === 'error') problems.push('console ' + m.text()); });
	// Chrome at times reports a file read through the stream reader (picker.js readBounded: faces, faces.json, licences)
	// as ERR_ABORTED although every byte arrived (readBounded checks the decoded length against the index or
	// Content-Length). Such requests are collected and accepted below only for faces whose select succeeded, a faces.json
	// that loaded all its faces, and licences whose cached pane text is not an error.
	const aborted = [];
	page.on('requestfailed', r => { const t = r.failure()?.errorText ?? ''; if (t === 'net::ERR_ABORTED' && /\.SVF$|\/faces\.json$|\/licences\/.+\.(TXT|txt)$/.test(r.url())) aborted.push(r.url()); else problems.push('request failed ' + r.url() + ' ' + t); });
	page.on('response', r => { if (r.status() >= 400) problems.push(`HTTP ${r.status()} ${r.url()}`); });
	const ua = await page.evaluate(() => navigator.userAgent);
	writeFileSync(join(out, 'browser.txt'), `browser.version() ${browser.version()}\nuser agent ${ua}\nplaywright-core ${pwVersion}\n`);

	await page.goto(server.url + '?manual'); // ?manual: the page does not open its default pair, this driver selects
	await page.evaluate(() => window.picker.ready);

	const counts = [];
	// every .SVF the page requests, counted (faces are fetched once: the server sends no-store, so a re-fetch would show)
	const faceHits = new Map();
	page.on('request', r => { const u = r.url(); if (u.endsWith('.SVF')) faceHits.set(u, (faceHits.get(u) ?? 0) + 1); });

	// Case A: every face, text = pangram + ASCII exactly. A face that holds at least one of those code points must give
	// err 0 and ink > 0; a face that holds none (the supplement-only faces) goes to the supplement case.
	const keys = await page.evaluate(() => window.picker.faces().map(f => f.key));
	const text = await page.evaluate(() => { const p = window.picker.presets; return p.pangram + '\n' + p.ascii; });
	await page.evaluate(t => { window.picker.setText(t); window.picker.setScale(1, 1); window.picker.setTarget({ kind: 'gray8' }); }, text);
	const rows = new Map(), later = [];
	let required = 0;
	for (const key of keys) {
		const r = await page.evaluate(async k => {
			try {
				await window.picker.select({ latin: null, hangul: k });
				const covers = window.picker.covers(window.picker.presets.pangram + window.picker.presets.ascii);
				return { covers, ...window.picker.render() };
			} catch (e) { return { covers: 0, err: -2, errName: String(e.message), ink: 0, ms: 0 }; }
		}, key);
		if (r.err !== 0) { fail('case A ' + key, `err ${r.err} ${r.errName}`); rows.set(key, ['A', r]); continue; }
		if (r.covers > 0) {
			required++;
			if (!(r.ink > 0)) fail('case A ' + key, `holds ${r.covers} of the text's code points but drew no ink`);
			rows.set(key, ['A', r]);
		} else later.push(key);
	}
	// Case supplement: the faces that hold none of pangram + ASCII must draw the supplement line
	const supp = await page.evaluate(() => window.picker.presets.supplement);
	await page.evaluate(t => window.picker.setText(t), supp);
	for (const key of later) {
		const r = await page.evaluate(async k => {
			try {
				await window.picker.select({ latin: null, hangul: k });
				return { covers: window.picker.covers(window.picker.presets.supplement), ...window.picker.render() };
			} catch (e) { return { covers: 0, err: -2, errName: String(e.message), ink: 0, ms: 0 }; }
		}, key);
		if (r.err !== 0) fail('case supplement ' + key, `err ${r.err} ${r.errName}`);
		else if (!(r.covers > 0 && r.ink > 0)) fail('case supplement ' + key, `covers ${r.covers}, ink ${r.ink}`);
		rows.set(key, ['supplement', r]);
	}
	for (const key of keys) {
		const [c, r] = rows.get(key) ?? ['none', { err: -3, ink: 0, ms: 0 }];
		appendFileSync(join(out, 'faces-report.tsv'), `${key}\t${r.err}\t${r.ink}\t${r.ms.toFixed(2)}\t${c}\n`);
	}
	counts.push(`case A: ${keys.length} faces, ${required} hold pangram+ASCII code points and drew ink`);
	counts.push(`case supplement: ${later.length} supplement-only faces drew ink from the supplement line`);

	// Case B: the first screenshot
	const info = await page.evaluate(async () => {
		window.picker.setText(window.picker.presets.pangram + ' / Quest 1988');
		window.picker.setScale(2, 1);
		window.picker.setTarget({ kind: 'gray8', zoom: 1 });
		await window.picker.select({ latin: 'svf/dos/NGOTB16.SVF', hangul: 'svf/dos/PAPLG18.SVF' });
		await window.picker.select({ latin: 'svf/dos/NGOTB16.SVF', hangul: 'svf/dos/PAPLG18.SVF' }); // again: no second fetch
		return { r: window.picker.render() };
	});
	if (info.r.err !== 0 || !(info.r.ink > 0)) fail('case B', `render ${info.r.errName} ink ${info.r.ink}`);
	await page.locator('#preview').screenshot({ path: join(out, 'paplg18-chain.png') });
	await page.screenshot({ path: join(out, 'page.png') });

	// Case B, the controls: three faces on three targets, the scale and threshold relations, the licence pane, the list marks
	{
		const shot = async (cfg, file) => {
			const r = await page.evaluate(async c => {
				const P = window.picker;
				P.setText(P.presets[c.preset]); P.setScale(c.num, c.den); P.setTarget(c.target);
				await P.select({ latin: c.latin, hangul: c.hangul });
				return P.render();
			}, cfg);
			if (r.err !== 0 || !(r.ink > 0)) fail('case B ' + file, `render ${r.errName} ink ${r.ink}`);
			await page.locator('#preview').screenshot({ path: join(out, file) });
			return r;
		};
		await shot({ preset: 'finals', num: 3, den: 1, latin: null, hangul: 'svf/dos/NEODG16G.SVF',
			target: { kind: 'mono', threshold: 128, zoom: 2, fg: '#000000', bg: '#ffffff' } }, 'hgkey6j-mono.png');
		await shot({ preset: 'mixed', num: 1, den: 2, latin: 'svf/dos/NGOTB16.SVF', hangul: 'svf/dos/GBATB47.SVF',
			target: { kind: 'rgb565', zoom: 3, fg: '#FFE000', bg: '#203040' } }, 'gbatb47-rgb565.png');
		const ctl = await page.evaluate(async () => {
			const P = window.picker, o = {};
			P.setText(P.presets.ascii); P.setTarget({ kind: 'gray8', zoom: 1, fg: '#1d211c', bg: '#ffffff' });
			await P.select({ latin: null, hangul: 'svf/dos/PAPLG16.SVF' });
			P.setScale(1, 1); o.width1 = P.render().width;
			P.setScale(2, 1); o.width2 = P.render().width;
			P.setText(P.presets.pangram + P.presets.mixed); P.setScale(1, 1);
			await P.select({ latin: null, hangul: 'svf/jamo-extra/GOTHA24A.SVF' });
			P.setTarget({ kind: 'mono', threshold: 1 }); o.mono1 = P.render().ink;
			P.setTarget({ kind: 'mono', threshold: 255 }); o.mono255 = P.render().ink;
			return o;
		});
		// the licence pane of PAPLG18: one pre per licence file, the file name as heading
		await page.evaluate(() => { window.picker.setText(window.picker.presets.pangram); window.picker.setTarget({ kind: 'gray8' }); return window.picker.select({ latin: null, hangul: 'svf/dos/PAPLG18.SVF' }); });
		await page.waitForFunction(() => [...document.querySelectorAll('#cards pre.licence')].length === 2 &&
			[...document.querySelectorAll('#cards pre.licence')].every(p => p.textContent !== 'loading...'));
		const lic = await page.evaluate(() => [...document.querySelectorAll('#cards details')].map(d => [d.querySelector('summary').textContent, d.querySelector('pre').textContent]));
		const names = lic.map(l => l[0]).join(',');
		ctl.licence_ok = names === 'PAPLG.TXT,OFLPAPLG.TXT' && lic[0][1].includes('Paperlogy faces (PAPLG18.SVF, PAPLG16.SVF)') &&
			lic[1][1].startsWith('Copyright (c) 2024 PT& (www.designptn.com), Paperlogy; redesigned by Lee Juim, Hangul glyphs from');
		if (!ctl.licence_ok) fail('case B licence', JSON.stringify(lic.map(l => [l[0], l[1].slice(0, 100)])));
		// a face with three licence files: the card shows them in order; one face in both slots is one card "Latin and Hangul"
		const licPanes = async () => {
			await page.waitForFunction(() => [...document.querySelectorAll('#cards pre.licence')].length === 2 && [...document.querySelectorAll('#cards pre.licence')].every(p => p.textContent !== 'loading...'), null, { timeout: 5000 })
				.catch(() => {}); // the caller reports a pane set that is not there, once
			return page.evaluate(() => ({ cards: [...document.querySelectorAll('#cards .facecard')].map(c => c.querySelector('h3').textContent),
				dts: [...document.querySelectorAll('#cards .facecard')].map(c => [...c.querySelectorAll('dl dt')].slice(0, 3).map(d => d.textContent).join()),
				subs: [...document.querySelectorAll('#cards .facecard')].map(c => c.querySelector('.sub')?.textContent), lic: [...document.querySelectorAll('#cards details')].map(d => [d.querySelector('summary').textContent, d.querySelector('pre').textContent]) }));
		};
		const wantLic = [['NEODGM.TXT', 'Neo Dunggeunmo faces'], ['OFL.TXT', 'Copyright (c) 2017-2021, Eunbin Jeong']];
		const licOk = l => l.lic.length === 2 && wantLic.every(([n, t], i) => l.lic[i][0] === n && l.lic[i][1].startsWith(t)) && l.lic[1][1].includes('SIL Open Font License');
		await page.evaluate(() => window.picker.select({ latin: null, hangul: 'svf/dos/NEODG16G.SVF' }));
		const l3 = await licPanes();
		if (!licOk(l3)) fail('case B licence', 'NEODG16G licence panes: ' + JSON.stringify(l3).slice(0, 400));
		await page.evaluate(() => window.picker.select({ latin: 'svf/dos/NEODG16G.SVF', hangul: 'svf/dos/NEODG16G.SVF' }));
		const l3b = await licPanes();
		const hgLabel = await page.evaluate(() => window.picker.faces().find(f => f.key === 'svf/dos/NEODG16G.SVF').label);
		if (licOk(l3) && (!licOk(l3b) || l3b.cards.join() !== 'Latin and Hangul' || !l3b.dts[0].startsWith('family,style,variant') || l3b.subs.join() !== hgLabel || l3.subs.join() !== hgLabel)) fail('case B licence', 'NEODG16G in both slots: ' + JSON.stringify(l3b).slice(0, 400));
		if (ctl.width2 !== 2 * ctl.width1) fail('case B scale', `width at 2/1 ${ctl.width2}, at 1/1 ${ctl.width1}`);
		if (!(ctl.mono1 > ctl.mono255 && ctl.mono255 > 0)) fail('case B threshold', `ink at 1 ${ctl.mono1} must exceed ink at 255 ${ctl.mono255}`);
		writeFileSync(join(out, 'controls.json'), JSON.stringify(ctl) + '\n');
		counts.push(`case B: scale 2/1 width ${ctl.width2} = 2 x ${ctl.width1}, MONO ink ${ctl.mono1} at threshold 1 > ${ctl.mono255} at 255, PAPLG18 licence pane ok`);
	}

	// Case fetch-once: every face file was requested exactly once over all those selections
	const multi = [...faceHits].filter(([, n]) => n !== 1);
	if (multi.length || faceHits.size !== keys.length) fail('case fetch-once', `${faceHits.size} face files requested, repeated: ${JSON.stringify(multi)}`);
	counts.push(`case fetch-once: ${faceHits.size} face files, each requested once`);
	{ // an aborted .SVF request is fine when that face was selected without error in case A or the supplement case
		const urls = await page.evaluate(() => Object.fromEntries(window.picker.faces().map(f => [f.url, f.key])));
		for (const u of aborted) {
			if (u.includes('/licences/')) {
				const text = await page.evaluate(p => window.picker.licence(p), u.slice(u.indexOf('/licences/') + 1));
				if (text.startsWith('(')) fail('page', `request failed (ERR_ABORTED) for a licence that did not load: ${u} ${text.slice(0, 100)}`);
				continue;
			}
			if (u.endsWith('/faces.json')) { if (Object.keys(urls).length !== (await (await fetch(server.url + 'faces.json')).json()).faces.length) fail('page', 'request failed (ERR_ABORTED) for a faces.json that did not load: ' + u); continue; }
			const key = urls[u.slice(u.indexOf('/faces/') + 1)];
			if (!key || rows.get(key)?.[1].err !== 0) fail('page', 'request failed (ERR_ABORTED) for a face that did not load: ' + u);
		}
	}
	for (const p of problems) fail('page', p);

	// Case C: ready and the default selection. A caller that awaits ready then selects is not overwritten.
	{
		const p2 = await ctx.newPage();
		const probs = [];
		p2.on('pageerror', e => probs.push('pageerror ' + e.message));
		await p2.goto(server.url);
		const NG16 = 'svf/dos/NGOTB16.SVF';
		const first = await p2.evaluate(async () => { await window.picker.ready; return window.picker.chain(); });
		if (first.hangul !== NG16 || first.latin !== NG16) fail('case C', 'no default pair when ready resolved: ' + JSON.stringify(first));
		const ui0 = await p2.evaluate(() => ({
			chip: document.querySelector('#sizes [aria-checked="true"]')?.dataset.px, chips: document.querySelectorAll('#sizes [aria-checked="true"]').length,
			sel: [...document.querySelectorAll('#faces li[aria-selected="true"] .name')].map(n => n.textContent),
			variant: document.querySelector('#variants [aria-checked="true"]')?.dataset.key, shown: !document.getElementById('variants').hidden,
			same: window.picker.view().same, view: window.picker.view() }));
		if (ui0.chip !== '16' || ui0.chips !== 1 || JSON.stringify(ui0.sel) !== '["NanumGothic Bold"]' || ui0.variant !== NG16 || !ui0.shown || ui0.same !== true) fail('case C', 'the default pair is not shown: ' + JSON.stringify(ui0));
		// the load's own prefetch (ui.afterPick): the 16 px list is fetched, NGOTB16 was held; 44 keys in memory
		const pre = await p2.evaluate(async () => ({ r: await window.picker.prefetching(), n: window.picker.faceMemory().keys.length }));
		if (JSON.stringify(pre.r) !== '{"px":16,"fetched":21,"held":1,"skipped":0,"failed":0,"stopped":false}' || pre.n !== 22) fail('case C', 'the load did not prefetch the 16 px list: ' + JSON.stringify(pre));
		const other = keys[0];
		await p2.evaluate(k => window.picker.select({ latin: null, hangul: k }), other);
		await p2.waitForTimeout(500);
		const after = await p2.evaluate(() => window.picker.chain());
		if (after.hangul !== other || after.latin !== null) fail('case C', 'the caller selection was overwritten: ' + JSON.stringify(after));
		counts.push('case C: ready resolves with the default pair NGOTB16 x2 open, chip 16 and row NanumGothic Bold pressed; a later select is kept');

		// Case D: the UI: size chip, search over the shown size, #also, row click, MONO and RGB565 (colours fg #b43c1e on bg #3c78b4)
		await p2.click('#sizes [data-px="18"]');
		// a term that matches here and at other sizes (Paperlogy has 16 px faces): #also stays hidden
		await p2.fill('#f-name', 'paperlogy');
		const here = await p2.evaluate(() => ({ rows: document.querySelectorAll('#faces li:not([hidden])').length, also: document.getElementById('also').hidden, other: window.picker.families(16).some(f => /paperlogy/i.test(f.name)) }));
		if (!here.rows || !here.other || !here.also) fail('case D', '#also with a match here and at other sizes: ' + JSON.stringify(here));
		await p2.fill('#f-name', 'PAPLG18');
		const visible = await p2.$$eval('#faces li:not([hidden])', l => l.map(x => [x.dataset.key, x.querySelector('.name').textContent]));
		if (visible.length !== 1 || visible[0][1] !== 'Paperlogy Regular') fail('case D', 'search PAPLG18 at 18 px shows ' + JSON.stringify(visible));
		if (!(await p2.evaluate(() => document.getElementById('also').hidden))) fail('case D', '#also is shown although the shown size has a match');
		await p2.locator('#faces li:not([hidden])').first().click();
		await p2.waitForFunction(() => { const k = window.picker.defaultVariant('Paperlogy', 'Regular', 18); return window.picker.chain().hangul === k && document.querySelector('#faces li[aria-selected="true"]')?.dataset.key === k; });
		const strip = await p2.evaluate(() => ({ shown: !document.getElementById('variants').hidden, chips: [...document.querySelectorAll('#variants [role="radio"]')].map(b => b.textContent) }));
		if (!strip.shown || !strip.chips.some(t => t.includes('PAPLG18.SVF'))) fail('case D', 'no PAPLG18 chip in the variant strip: ' + JSON.stringify(strip));
		await p2.fill('#f-name', '');
		await p2.click('#sizes [data-px="16"]');
		await p2.fill('#f-name', 'PAPLG18');
		const gone = await p2.evaluate(() => ({ rows: document.querySelectorAll('#faces li:not([hidden])').length, also: !document.getElementById('also').hidden,
			buttons: [...document.querySelectorAll('#also button')].map(b => b.textContent) }));
		if (gone.rows !== 0 || !gone.also || !gone.buttons.includes('18 px')) fail('case D', 'search PAPLG18 at 16 px: ' + JSON.stringify(gone));
		await p2.locator('#also button', { hasText: '18 px' }).click();
		const back = await p2.evaluate(() => ({ chip: document.querySelector('#sizes [aria-checked="true"]')?.dataset.px, rows: document.querySelectorAll('#faces li:not([hidden])').length }));
		if (back.chip !== '18' || back.rows !== 1) fail('case D', '#also did not press chip 18 and show the row: ' + JSON.stringify(back));
		await p2.fill('#f-name', '');
		await p2.fill('#fg', '#b43c1e'); await p2.fill('#bg', '#3c78b4');
		await p2.fill('#zoom', '1');
		const colours = () => p2.evaluate(() => {
			const c = document.getElementById('preview'), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data, seen = new Map();
			for (let i = 0; i < d.length; i += 4) { const k = `${d[i]},${d[i + 1]},${d[i + 2]}`; seen.set(k, (seen.get(k) ?? 0) + 1); }
			return { corner: `${d[0]},${d[1]},${d[2]}`, distinct: [...seen.keys()], w: c.width, h: c.height };
		});
		await p2.check('input[name=kind][value=gray8]');
		const g = await colours();
		if (g.corner !== '60,120,180' || g.distinct.length < 3) fail('case D gray8', JSON.stringify(g));
		await p2.check('input[name=kind][value=mono]');
		await p2.locator('#preview').screenshot({ path: join(out, 'mono.png') });
		const m = await colours();
		if (m.corner !== '60,120,180' || m.distinct.length !== 2 || !m.distinct.includes('180,60,30')) fail('case D mono', 'not exactly the configured fg/bg: ' + JSON.stringify(m));
		await p2.check('input[name=kind][value=rgb565]');
		await p2.locator('#preview').screenshot({ path: join(out, 'rgb565.png') });
		const q = await colours();
		if (q.corner !== '57,121,181' || q.distinct.length < 3) fail('case D rgb565', 'expected the 5/6/5 quantised paper 57,121,181 and blends: ' + JSON.stringify(q));
		await p2.screenshot({ path: join(out, 'page-ui.png') });
		counts.push(`case D: chip 18 and the search show one row, the row click opens the strip, #also leads back from 16 px, MONO (2 colours) and RGB565 (${q.distinct.length} colours) drawn`);
		for (const p of probs) fail('page C/D', p);
		await p2.close();
	}

	// Case marks: its own page. Only fetched faces carry a "-n" mark; fetching one more face adds its mark.
	{
		const p5 = await ctx.newPage();
		const probs = [];
		p5.on('pageerror', e => probs.push('pageerror ' + e.message));
		await p5.goto(server.url + '?manual');
		await p5.evaluate(() => window.picker.ready);
		const snap = () => p5.evaluate(() => ({
			fetched: window.picker.faceMemory().keys, api: window.picker.lacking(), px: document.querySelector('#sizes [aria-checked="true"]')?.dataset.px,
			rows: [...document.querySelectorAll('#faces li')].map(l => ({ key: l.dataset.key, mark: l.querySelector('.lack')?.textContent ?? null, title: l.querySelector('.lack')?.title ?? null, liTitle: l.title,
				want: window.picker.families(+document.querySelector('#sizes [aria-checked="true"]').dataset.px).find(f => JSON.stringify([f.family, f.style]) === l.dataset.fam).faces
					.filter(k => k in window.picker.lacking()).map(k => `${k.slice(k.lastIndexOf('/') + 1)} ${window.picker.lacking()[k] < 0 ? '!' : '-' + window.picker.lacking()[k]}`).join(', ') })),
		}));
		await p5.evaluate(async () => {
			const P = window.picker;
			P.setText('Quest 가 … ™ ☺'); // PAPLB18A draws all of 'Quest 가', so the extra face (F7) would get no mark: '… ™ ☺' are drawn by none of these faces
			await P.select({ latin: 'svf/dos/NGOTB16.SVF', hangul: 'svf/dos/PAPLG18.SVF' });
			P.render(); await P.idle();
		});
		const s1 = await snap();
		// the shown size is the Hangul face's (18); a row's mark is the lack count of its picked face (data-key), absent for 0
		const consistent = (s, tag) => {
			const want = s.rows.map(r => { const n = s.api[r.key] ?? 0; return n ? (n < 0 ? '!' : '-' + n) : null; });
			if (s.px !== '18' || !s.rows.length || JSON.stringify(want) !== JSON.stringify(s.rows.map(r => r.mark)) || !want.some(x => x)) fail('case marks ' + tag, JSON.stringify(s).slice(0, 400));
			// the title lists FILE -n per fetched variant of the row, the picked face among them
			if (s.rows.some(r => r.mark && !(/^[A-Z0-9]+\.SVF (-\d+|!)(, [A-Z0-9]+\.SVF (-\d+|!))*$/.test(r.title) && r.title.includes(r.key.slice(r.key.lastIndexOf('/') + 1) + ' ' + r.mark)))) fail('case marks ' + tag, 'a mark title: ' + JSON.stringify(s.rows.filter(r => r.mark)).slice(0, 300));
			// every row's own title lists its fetched variants as FILE -n, mark or no mark
			if (s.rows.some(r => r.liTitle !== r.want) || !s.rows.some(r => r.liTitle)) fail('case marks ' + tag, 'a row title: ' + JSON.stringify(s.rows.filter(r => r.liTitle !== r.want || r.want)).slice(0, 300));
			if (s.rows.some(r => r.mark && !s.fetched.includes(r.key))) fail('case marks ' + tag, 'a mark on an unfetched face: ' + JSON.stringify(s).slice(0, 300));
		};
		consistent(s1, 'before');
		const extra = 'svf/dos/PAPLB18A.SVF'; // the default of row Paperlogy Bold; a non-default variant changes no row mark
		if (s1.fetched.includes(extra) || s1.rows.find(r => r.key === extra)?.mark) fail('case marks', 'the extra face was marked before it was fetched');
		await p5.evaluate(async k => { await window.picker.prefetch(k); window.picker.render(); await window.picker.idle(); }, extra);
		const s2 = await snap();
		consistent(s2, 'after');
		if (s2.fetched.length !== s1.fetched.length + 1 || !s2.rows.find(r => r.key === extra)?.mark) fail('case marks', 'fetching one more face did not add its row mark: ' + JSON.stringify(s2).slice(0, 300));
		// the plain sample: PAPLB18A draws all of it, so its row has no mark and lacking() counts 0
		const plain = await p5.evaluate(async () => { window.picker.setText('Quest 가'); window.picker.render(); await window.picker.idle(); return { n: window.picker.lacking()['svf/dos/PAPLB18A.SVF'], mark: document.querySelector('#faces li[data-key="svf/dos/PAPLB18A.SVF"] .lack')?.textContent ?? null }; });
		if (plain.n !== 0 || plain.mark !== null) fail('case marks', 'PAPLB18A and the plain text "Quest 가": ' + JSON.stringify(plain));
		counts.push(`case marks: ${s1.fetched.length} fetched faces, ${s1.rows.filter(r => r.mark).length} marked rows at 18 px, unfetched faces carry none; fetching PAPLB18A adds its row mark`);
		for (const p of probs) fail('page marks', p);
		await p5.close();
	}

	// Case bad face: a face whose header is zeroed (same length, so it is fetched) does not open; the scan marks it, restores the chain, and does not reopen it, not even after the text changes
	{
		const p6 = await ctx.newPage();
		const probs = [];
		p6.on('pageerror', e => probs.push('pageerror ' + e.message));
		await p6.route('**/faces/dos/NEODG16.SVF', async route => { const r = await route.fetch(); await route.fulfill({ response: r, body: Buffer.concat([Buffer.alloc(16), (await r.body()).subarray(16)]) }); });
		await p6.goto(server.url + '?manual');
		await p6.evaluate(() => window.picker.ready);
		const r = await p6.evaluate(async () => {
			const P = window.picker, M = P.module(), o = { opens: 0, badOpens: 0 };
			const orig = M._svfw_open;
			let badLen = 0; // the zeroed face's length: no other face of the test has it
			M._svfw_open = (slot, ptr, len) => { o.opens++; if (len === badLen) o.badOpens++; return orig(slot, ptr, len); };
			P.setText('Quest 가');
			await P.pick('svf/dos/NGOTB16.SVF');
			badLen = await P.prefetch('svf/dos/NEODG16.SVF');
			o.sizes = P.faces().filter(f => f.key === 'svf/dos/NGOTB16.SVF').map(f => f.bytes).concat(badLen);
			o.first = P.render(); await P.idle(); o.chain = P.chain(); o.firstBad = o.badOpens;
			o.badge = document.querySelector('#faces li[data-key="svf/dos/NEODG16.SVF"] .lack')?.textContent;
			o.before = o.opens;
			o.second = P.render(); await P.idle(); o.reopened = o.opens - o.before;
			P.setText('Hero 나'); // another text: the good faces are scanned again, the bad one must not be opened again
			o.third = P.render(); await P.idle(); o.badAgain = o.badOpens - o.firstBad; o.scanned = o.opens - o.before;
			o.badge3 = document.querySelector('#faces li[data-key="svf/dos/NEODG16.SVF"] .lack')?.textContent;
			o.selected = document.getElementById('hangul').value;
			return o;
		});
		if (r.first.err !== 0 || !(r.first.ink > 0) || r.second.err !== 0 || !(r.second.ink > 0) || r.third.err !== 0 || !(r.third.ink > 0)) fail('case bad face', 'render after the scan: ' + JSON.stringify([r.first, r.second, r.third]));
		if (JSON.stringify([...new Set(r.sizes)].sort()) !== JSON.stringify([133720, 219480])) fail('case bad face', 'the face lengths are not {219480, 133720}, opens cannot be told apart: ' + r.sizes);
		if (r.chain.hangul !== 'svf/dos/NGOTB16.SVF' || r.chain.latin !== 'svf/dos/NGOTB16.SVF' || r.selected !== 'svf/dos/NGOTB16.SVF') fail('case bad face', 'chain changed: ' + JSON.stringify(r));
		if (r.badge !== '!') fail('case bad face', 'no error badge on the bad face: ' + r.badge);
		if (r.reopened !== 0) fail('case bad face', `a second repaint reopened faces ${r.reopened} times`);
		if (r.firstBad !== 1 || r.badAgain !== 0 || r.badge3 !== '!') fail('case bad face', `after a text change the bad face was opened ${r.badAgain} more times (first scan ${r.firstBad}), badge ${r.badge3}`);
		if (!(r.scanned > 0)) fail('case bad face', 'the text change scanned nothing: ' + r.scanned);
		counts.push('case bad face: a face that does not open gets an error badge, the chain stays open and paints, a second repaint opens nothing, a text change rescans the good faces only');
		for (const p of probs) fail('page bad face', p);
		await p6.close();
	}

	// Case transport: gzip-encoded face and licence load (Content-Length is the compressed size, the decoded body is
	// longer); same-origin redirects (to the same file, so only redirect: 'error' refuses them) are refused; a licence
	// whose body is shorter than its Content-Length shows an error, not the text
	{
		const n0 = nfailed, srv2 = await startServer(dist, {
			gzip: ['/faces/dos/PAPLG16.SVF', '/licences/dos/PAPLG.TXT'],
			redirect: { '/faces/dos/PAPLG18.SVF': '/faces/dos/PAPLG18.SVF?r', '/licences/dos/OFLPAPLG.TXT': '/licences/dos/OFLPAPLG.TXT?r' },
			short: ['/licences/dos/NANUMGOT.TXT'],
		});
		try {
			const p7 = await ctx.newPage();
			// Chrome itself fails a body cut short on the wire (serve.mjs short: "network error"); a fulfilled route hands the
			// page a short body with the long Content-Length and no network error, so only readBounded can refuse it
			await p7.route('**/licences/dos/GOWUNBAT.TXT', async route => {
				const body = await (await route.fetch()).body();
				await route.fulfill({ status: 200, headers: { 'content-type': 'text/plain; charset=utf-8', 'content-length': String(body.length + 1000) }, body });
			});
			await p7.goto(srv2.url + '?manual');
			await p7.evaluate(() => window.picker.ready);
			const r = await p7.evaluate(async () => {
				const P = window.picker, o = {};
				P.setText('Quest');
				try { await P.select({ latin: null, hangul: 'svf/dos/PAPLG16.SVF' }); o.gz = P.render(); } catch (e) { o.gz = { err: e.message }; }
				try { await P.select({ latin: null, hangul: 'svf/dos/PAPLG18.SVF' }); o.redirect = 'selected'; } catch (e) { o.redirect = e.message; }
				return o;
			});
			// the licence texts the pane shows for a face selected alone (['(select failed: ...)'] when it does not open)
			const licences = async key => {
				const err = await p7.evaluate(k => window.picker.select({ latin: null, hangul: k }).then(() => null, e => e.message), key);
				if (err) return [`(select failed: ${err})`, ''];
				await p7.waitForFunction(() => [...document.querySelectorAll('#cards pre.licence')].length === 2 && [...document.querySelectorAll('#cards pre.licence')].every(p => p.textContent !== 'loading...'));
				return p7.evaluate(() => [...document.querySelectorAll('#cards pre.licence')].map(p => p.textContent));
			};
			const lic = await licences('svf/dos/PAPLG16.SVF'), short = await licences('svf/dos/NGOTB16.SVF'), routed = await licences('svf/dos/GBATB47.SVF');
			if (r.gz.err !== 0 || !(r.gz.ink > 0)) fail('case transport', 'gzip face: ' + JSON.stringify(r.gz));
			if (r.redirect === 'selected') fail('case transport', 'a redirected face was loaded');
			if (!lic[0].includes('Paperlogy faces')) fail('case transport', 'gzip licence did not load: ' + lic[0].slice(0, 100));
			if (!lic[1].startsWith('(licences/dos/OFLPAPLG.TXT: ') || lic[1].includes('Copyright')) fail('case transport', 'a redirected licence was loaded: ' + lic[1].slice(0, 100));
			if (!short[0].startsWith('(licences/dos/NANUMGOT.TXT: ') || short[0].length > 200) fail('case transport', 'a truncated licence was shown: ' + short[0].slice(0, 100));
			if (!short[1].includes('Copyright')) fail('case transport', 'the other NGOTB16 licence did not load: ' + short[1].slice(0, 100));
			if (!/^\(licences\/dos\/GOWUNBAT\.TXT: \d+ bytes, Content-Length says \d+\)$/.test(routed[0])) fail('case transport', 'a short body under a longer Content-Length was shown: ' + routed[0].slice(0, 100));
			if (nfailed === n0) counts.push(`case transport: gzip face and licence load, a redirected face and licence are refused (${r.redirect.slice(0, 40)}), truncated licences show ${short[0].slice(0, 60)} and ${routed[0].slice(0, 80)}`);
			await p7.close();
		} finally { await srv2.close(); }
	}

	// Case index: faces.json goes through the same rules: a redirect (same origin) and a body over 4 MiB are refused
	{
		const n0 = nfailed, srv3 = await startServer(dist, { redirect: { '/faces.json': '/faces.json?r' } });
		try {
			const res = [];
			for (const [url, big] of [[srv3.url + '?manual', false], [server.url + '?manual', true]]) {
				const p9 = await ctx.newPage();
				if (big) await p9.route('**/faces.json', route => route.fulfill({ contentType: 'application/json', body: '{"faces":[]}' + ' '.repeat(4 << 20) }));
				await p9.goto(url);
				const why = await p9.evaluate(() => window.picker.ready.then(() => 'loaded', e => String(e.message)));
				res.push({ why, status: await p9.evaluate(() => document.getElementById('status').textContent) });
				await p9.close();
			}
			for (const r of res) if (r.why === 'loaded' || !r.why.includes('faces.json') || !r.status.includes(r.why)) fail('case index', 'faces.json accepted or the status line is silent: ' + JSON.stringify(r).slice(0, 200));
			if (!/limit/.test(res[1].why)) fail('case index', 'an over-long faces.json was not refused by size: ' + res[1].why);
			// schema: a duplicate key, a wrong-typed field; either stops start() with the status line naming the face
			for (const [what, edit, want] of [
				['duplicate key', j => { j.faces[1].key = j.faces[0].key; }, /^faces\.json: face 1 "[^"]+": duplicate key$/],
				['wrong type', j => { j.faces[2].cell = '18x20'; }, /^faces\.json: face 2 "[^"]+": cell must be \[w, h\], integers 1\.\.255$/],
				['wrong type', j => { j.faces[3].bytes = '1000'; }, /^faces\.json: face 3 "[^"]+": bytes must be an integer/],
				['no licence', j => { j.faces[4].licences = []; }, /^faces\.json: face 4 "[^"]+": licences must be a list of 1\.\.16 strings/],
				['bad licence URL', j => { j.faces[5].licences = ['../../etc/passwd']; }, /^faces\.json: face 5 "[^"]+": licence URL leaves the page directory: \.\.\/\.\.\/etc\/passwd$/],
				['licence outside licences/', j => { j.faces[5].licences = ['picker.js']; }, /^faces\.json: face 5 "[^"]+": licence URL must be under licences\/: picker\.js$/],
				['null face', j => { j.faces[1] = null; }, /^faces\.json: face 1: not an object$/],
				['number face', j => { j.faces[1] = 5; }, /^faces\.json: face 1: not an object$/],
				['no format', j => { delete j.format; }, /^faces\.json: format must be "svf-fonts-web-index\/1"$/],
				['format /2', j => { j.format = 'svf-fonts-web-index/2'; }, /^faces\.json: format must be "svf-fonts-web-index\/1"$/],
				['url of another face', j => { j.faces[1].url = j.faces[2].url; }, /^faces\.json: face 1 "[^"]+": url must be faces\/<rel> for this key$/],
				['key with ..', j => { j.faces[1].key = 'svf/dos/../x.SVF'; }, /^faces\.json: face 1 "[^"]+": key must be svf\/<rel> \(1\.\.6 segments/],
				['key with a space', j => { j.faces[1].key = 'svf/dos/A B.SVF'; }, /^faces\.json: face 1 "[^"]+": key must be svf\/<rel> \(1\.\.6 segments/],
				['group', j => { j.faces[1].group = 'nope'; }, /^faces\.json: face 1 "[^"]+": group must be the key's directory$/],
				['px', j => { j.faces[1].px = j.faces[1].cell[1] + 1; }, /^faces\.json: face 1 "[^"]+": px must equal cell\[1\]$/],
				['subset flipped', j => { const f = j.faces.find(x => x.key === 'svf/dos/NGOTB16.SVF'); f.subset = !f.subset; }, /: subset must equal \(!jamo && !latin_only && hangul < 2350\)$/],
				['latin_only with hangul', j => { const f = j.faces.find(x => x.key === 'svf/dos/COUSB24.SVF'); f.latin_only = true; f.hangul = 5; }, /: latin_only requires jamo false and hangul 0$/],
				['empty family', j => { j.faces.find(x => x.key === 'svf/dos/NGOTB16.SVF').family = ''; }, /: family must be a string of 1\.\.256 characters for a listed face$/],
				['long style', j => { j.faces[1].style = 'x'.repeat(257); }, /: family, style and variant must be strings of at most 256 characters$/],
				['numeric variant', j => { j.faces[1].variant = 5; }, /: family, style and variant must be strings of at most 256 characters$/],
				['hangul 3000', j => { j.faces[1].hangul = 3000; }, /: hangul must be an integer 0\.\.2350$/],
				['65 distinct px', j => { j.faces.forEach((f, i) => { const v = i < 65 ? 100 + i : 100; f.px = v; f.cell[1] = v; }); }, /^faces\.json: 65 distinct px values, the limit is 64$/],
			]) {
				const p9 = await ctx.newPage();
				await p9.route('**/faces.json', async route => { const j = await (await route.fetch()).json(); edit(j); await route.fulfill({ json: j }); });
				await p9.goto(server.url + '?manual');
				const why = await p9.evaluate(() => window.picker.ready.then(() => 'loaded', e => String(e.message)));
				const r = { why, status: await p9.evaluate(() => document.getElementById('status').textContent), rows: await p9.$$eval('#faces li', l => l.length) };
				if (!want.test(r.why) || !r.status.includes(r.why) || r.rows !== 0) fail('case index', `${what}: ` + JSON.stringify(r).slice(0, 200));
				await p9.close();
			}
			if (nfailed === n0) counts.push('case index: a redirected faces.json, one over 4 MiB, a duplicate key, wrong-typed fields, bad licences and licence URLs (incl. hostile ones), and a bad format, key, url, group, px, subset, latin_only, family/style/variant, hangul or more than 64 distinct px are refused and named on the status line');
		} finally { await srv3.close(); }
	}

	// Case default variant: the families model over the real index, and over an edited one
	{
		const n0 = nfailed;
		const p11 = await ctx.newPage(), errs = [];
		p11.on('pageerror', e => errs.push(e.message));
		await p11.goto(server.url + '?manual');
		await p11.evaluate(() => window.picker.ready);
		const r = await p11.evaluate(async () => {
			const P = window.picker, o = {};
			o.dv = [['Neo Dunggeunmo', '', 16], ['Gothic A1', 'Bold', 16], ['Gowun Batang', 'Bold', 24], ['NanumGothic', 'Bold', 16], ['NanumGothic', 'Bold', 24], ['Paperlogy', 'Regular', 18], ['Coustard', 'Bold', 28]].map(a => P.defaultVariant(...a));
			const latinOnly = new Set(P.faces().filter(f => f.latin_only).map(f => f.key));
			o.lo = P.families(18).some(f => f.faces.some(k => latinOnly.has(k)));
			o.sizes = P.sizes();
			const f16 = P.families(16);
			o.n16 = f16.length;
			o.none = P.families(17).length;
			const before = P.chain();
			o.listed = { n: P.listed().length, want: P.faces().filter(f => !f.subset).length, subset: P.listed().some(f => f.subset), lat: P.listed().filter(f => f.latin_only).length, arr: Array.isArray(P.listed()) };
			o.names = f16.map(f => [f.family, f.style]);
			const d0 = f16[0].default, k0 = f16[0].faces.length; f16[0].faces.push('x'); f16[0].faces.splice(0, 1); f16[0].family = 'mutated'; const g0 = P.families(16)[0]; o.mut = g0.family === 'mutated' || g0.faces.length !== k0 || g0.faces[0] !== d0 || g0.default !== d0 || P.defaultVariant(g0.family, g0.style, 16) !== d0;
			o.subsetPick = await P.pick('svf/dos/BHSAN28.SVF').then(() => 'accepted', e => e.message);
			o.sameSub = JSON.stringify(before) === JSON.stringify(P.chain());
			o.pick = await P.pick('svf/dos/COUSB24.SVF').then(() => 'accepted', e => e.message);
			o.same = JSON.stringify(before) === JSON.stringify(P.chain());
			await P.pick('svf/dos/PAPLG18.SVF'); o.ok = P.chain();
			return o;
		});
		const want = ['svf/dos/NEODG16.SVF', 'svf/jamo-extra/GOTHB16A.SVF', 'svf/dos/GBATB23.SVF', 'svf/dos/NGOTB16.SVF', 'svf/dos/NGOTB17A.SVF', 'svf/dos/PAPER18A.SVF', null];
		if (JSON.stringify(r.dv) !== JSON.stringify(want)) fail('case default variant', 'defaults ' + JSON.stringify(r.dv));
		if (r.lo) fail('case default variant', 'families(18) holds a Latin-only face');
		if (JSON.stringify(r.sizes) !== JSON.stringify([16, 18, 20, 22, 24, 32, 36, 54])) fail('case default variant', 'sizes ' + JSON.stringify(r.sizes));
		const lc = r.names.map(n => n.map(x => x.toLowerCase()));
		const gt = (a, b) => a[0] > b[0] || (a[0] === b[0] && a[1] > b[1]);
		if (r.n16 !== 11 || new Set(r.names.map(n => JSON.stringify(n))).size !== 11 || lc.some((n, i) => i && gt(lc[i - 1], n))) fail('case default variant', 'families(16): ' + r.n16 + ' ' + JSON.stringify(r.names));
		if (!r.listed.arr || r.listed.n !== r.listed.want || r.listed.subset || r.listed.lat < 1) fail('case default variant', 'listed(): ' + JSON.stringify(r.listed));
		if (r.mut) fail('case default variant', 'families() returned the model itself');
		if (!r.subsetPick.includes('svf/dos/BHSAN28.SVF') || !r.sameSub) fail('case default variant', 'pick of a subset face: ' + r.subsetPick);
		if (r.ok.latin !== 'svf/dos/PAPLG18.SVF' || r.ok.hangul !== 'svf/dos/PAPLG18.SVF') fail('case default variant', 'pick of a listed face: ' + JSON.stringify(r.ok));
		if (r.none !== 0) fail('case default variant', 'families(17) is not empty');
		if (!r.pick.includes('svf/dos/COUSB24.SVF') || !r.same) fail('case default variant', 'pick of a Latin-only face: ' + r.pick + ' chain same: ' + r.same);
		await p11.close();
		const p12 = await ctx.newPage();
		p12.on('pageerror', e => errs.push(e.message));
		await p12.route('**/faces.json', async route => {
			const j = await (await route.fetch()).json();
			j.faces.find(f => f.key === 'svf/jamo-extra/GOTHB16.SVF').bpp = 8;
			const g = j.faces.find(f => f.key === 'svf/dos/NGOTB16.SVF'); g.family = '__proto__'; g.style = 'constructor';
			await route.fulfill({ json: j });
		});
		await p12.goto(server.url + '?manual');
		await p12.evaluate(() => window.picker.ready);
		const q = await p12.evaluate(() => {
			const P = window.picker, f = P.families(16);
			return { d: P.defaultVariant('Gothic A1', 'Bold', 16), n: f.length, row: f.some(x => x.family === '__proto__' && x.name === '__proto__ constructor') };
		});
		if (q.d !== 'svf/jamo-extra/GOTHB16.SVF') fail('case default variant', 'bpp 8 did not win: ' + q.d);
		if (q.n !== 12 || !q.row) fail('case default variant', 'prototype-named family: ' + JSON.stringify(q));
		if (errs.length) fail('case default variant', 'pageerror ' + errs[0]);
		await p12.close();
		if (nfailed === n0) counts.push('case default variant: defaults, sizes, 11 families at 16 px, pick refuses a Latin-only face, a prototype-named family is a plain row (12 rows: NGOTB15 keeps NanumGothic Bold)');
	}

	// Case no stream: Response.body hidden, so readBounded takes its arrayBuffer fallback. A good face loads; a face over its
	// index size sent as "gzip" (so no Content-Length counts; a fulfilled route is not decoded) is refused before the body
	// is read, as unbounded, and so is one sent chunked (no Content-Length at all); a face under its index size is refused
	// as differing from the index
	{
		const n0 = nfailed, srv4 = await startServer(dist, { chunked: ['/faces/dos/GBATB47.SVF'] });
		try {
			const p10 = await ctx.newPage();
			await p10.addInitScript(() => Object.defineProperty(Response.prototype, 'body', { get: () => null }));
			await p10.route('**/faces.json', async route => {
				const j = await (await route.fetch()).json();
				for (const f of j.faces) if (f.key === 'svf/dos/PAPLG16.SVF' || f.key === 'svf/dos/GBATB47.SVF') f.bytes -= 1; else if (f.key === 'svf/dos/NGOTB16.SVF') f.bytes += 1;
				await route.fulfill({ json: j });
			});
			await p10.route('**/faces/dos/PAPLG16.SVF', async route => {
				await route.fulfill({ status: 200, headers: { 'content-type': 'application/octet-stream', 'content-encoding': 'gzip' }, body: await (await route.fetch()).body() });
			});
			await p10.goto(srv4.url + '?manual');
			await p10.evaluate(() => window.picker.ready);
			const r = await p10.evaluate(async () => {
				const P = window.picker, o = { body: new Response('x').body };
				const sel = async k => { try { await P.select({ latin: null, hangul: k }); return 'selected'; } catch (e) { return e.message; } };
				o.good = await sel('svf/dos/PAPLG18.SVF'); P.setText('가나'); o.ink = P.render().ink;
				o.over = await sel('svf/dos/PAPLG16.SVF');
				o.under = await sel('svf/dos/NGOTB16.SVF');
				o.chunked = await sel('svf/dos/GBATB47.SVF');
				return o;
			});
			if (r.body !== null) fail('case no stream', 'Response.body is not hidden');
			if (r.good !== 'selected' || !(r.ink > 0)) fail('case no stream', 'a good face did not load without a stream: ' + JSON.stringify(r));
			if (r.over !== 'faces/dos/PAPLG16.SVF: no body stream and no Content-Length that counts (content-encoded): the size cannot be bounded') fail('case no stream', 'an oversized response without a counted Content-Length: ' + r.over);
			if (!/^faces\/dos\/NGOTB16\.SVF: \d+ bytes, the index says \d+$/.test(r.under)) fail('case no stream', 'differs from the index: ' + r.under);
			if (r.chunked !== 'faces/dos/GBATB47.SVF: no body stream and no Content-Length: the size cannot be bounded') fail('case no stream', 'an oversized chunked response: ' + r.chunked);
			if (nfailed === n0) counts.push(`case no stream: a good face loads; "${r.over}"; "${r.chunked}"; "${r.under}"`);
			await p10.close();
		} finally { await srv4.close(); }
	}

	// Case surrogates: its own clean page. Two different lone surrogates count as one U+FFFD: 3 distinct code points, not 4
	{
		const p8 = await ctx.newPage();
		await p8.goto(server.url + '?manual');
		await p8.evaluate(() => window.picker.ready);
		const n = await p8.evaluate(async () => {
			await window.picker.select({ latin: null, hangul: 'svf/dos/PAPLG18.SVF' });
			return window.picker.lacking('AB\ud800\ud801')['svf/dos/PAPLG18.SVF'];
		});
		if (n !== 3) fail('case surrogates', `PAPLG18 lacks ${n} of A, B and two lone surrogates; expected 3 (A, B, U+FFFD)`);
		else counts.push('case surrogates: two different lone surrogates count as one U+FFFD');
		await p8.close();
	}

	// Case budget: a small face-memory budget (test hook) drops the oldest faces outside the chain and refuses what cannot fit
	{
		const p4 = await ctx.newPage();
		const probs = [];
		p4.on('pageerror', e => probs.push('pageerror ' + e.message));
		await p4.goto(server.url + '?manual');
		await p4.evaluate(() => window.picker.ready);
		const r = await p4.evaluate(async () => {
			const P = window.picker, by = Object.fromEntries(P.faces().map(f => [f.key, f.bytes]));
			const A = 'svf/dos/PAPLG18.SVF', B = 'svf/dos/NGOTB16.SVF', C = 'svf/dos/PAPLB18A.SVF', o = {};
			P.setFaceBudget(by[A] + by[B] + 10);
			await P.select({ latin: B, hangul: A });
			try { await P.select({ latin: null, hangul: C }); o.refused = 'no'; } catch (e) { o.refused = e.message; }
			o.afterRefuse = { keys: P.faceMemory().keys, chain: P.chain() };
			await P.select({ latin: null, hangul: A }); // B is now outside the chain
			await P.select({ latin: null, hangul: C }); // making room drops B (oldest outside the chain), keeps A until C is open
			o.afterEvict = { keys: P.faceMemory().keys, chain: P.chain(), bytes: P.faceMemory().bytes, ink: (P.setText('Quest'), P.render().ink) };
			o.sum = by[A] + by[C];
			o.budget = P.faceMemory().budget;
			return o;
		});
		if (!/face memory/.test(r.refused) || !/\d+ bytes are protected/.test(r.refused)) fail('case budget', 'no refusal, or its message does not say what is protected: ' + JSON.stringify(r));
		if (r.afterRefuse.keys.length !== 2 || r.afterRefuse.chain.hangul !== 'svf/dos/PAPLG18.SVF' || r.afterRefuse.chain.latin !== 'svf/dos/NGOTB16.SVF') fail('case budget', 'a refused select changed state: ' + JSON.stringify(r.afterRefuse));
		if (r.afterEvict.keys.includes('svf/dos/NGOTB16.SVF') || !r.afterEvict.keys.includes('svf/dos/PAPLB18A.SVF') || r.afterEvict.chain.hangul !== 'svf/dos/PAPLB18A.SVF' || !(r.afterEvict.ink > 0) || r.afterEvict.bytes > r.budget) fail('case budget', 'no eviction: ' + JSON.stringify(r.afterEvict));
		counts.push('case budget: over a small budget the oldest face outside the chain is dropped, a selection that cannot fit is refused and leaves the chain open');
		for (const p of probs) fail('page budget', p);
		await p4.close();
	}

	// Case runs: a Hangul run is drawn by the Hangul face first, a Latin run by the Latin face first. With Latin NGOTB16 (which
	// has Hangul too) the Hangul face still changes the picture; ASCII-only text does not change with the Hangul face, and
	// Hangul-only text not with the Latin face. GRAY8 buffers of six specimens go to runs-NAME.bin (runs.json lists
	// text, faces, scale and size) for the svfline comparison in tools/test_web_picker.py: the mixed line at 1/1 and 3/2,
	// three lines with an empty middle one at 1/1 and 3/2, a Hangul run whose U+3165 PAPLG18 lacks (NGOTB16, second in that run, draws
	// it), and "A\n가" with Hangul MARUS24 (lines of different heights: each line is as high as its own runs)
	{
		const n0 = nfailed, p12 = await ctx.newPage();
		await p12.goto(server.url + '?manual');
		await p12.evaluate(() => window.picker.ready);
		const r = await p12.evaluate(async () => {
			const P = window.picker, o = {};
			const N = 'svf/dos/NGOTB16.SVF', PA18 = 'svf/dos/PAPLG18.SVF', DK = 'svf/dos/MARUS24.SVF', PA16 = 'svf/dos/PAPLG16.SVF';
			const draw = async (latin, hangul, text) => {
				await P.select({ latin, hangul }); P.setText(text);
				const r = P.render(), px = P.pixels();
				return { err: r.err, ink: r.ink, w: px.w, h: px.h, bytes: px.bytes.join(',') };
			};
			const same = (a, b) => a.w === b.w && a.h === b.h && a.bytes === b.bytes;
			P.setTarget({ kind: 'gray8' }); P.setScale(1, 1);
			const pg = P.presets.pangram;
			o.pa = await draw(N, PA18, pg); o.dk = await draw(N, DK, pg);
			o.hangulChanges = !same(o.pa, o.dk) && o.pa.ink !== o.dk.ink;
			o.asciiCovered = P.lacking('Quest OK')[N] === 0;
			o.asciiSame = same(await draw(N, PA18, 'Quest OK'), await draw(N, DK, 'Quest OK'));
			o.hangulCovered = P.lacking('가나다')[PA18] === 0;
			o.hangulSame = same(await draw(N, PA18, '가나다'), await draw(PA16, PA18, '가나다'));
			o.latinChanges = !same(await draw(N, PA18, 'Quest OK'), await draw(PA16, PA18, 'Quest OK'));
			const m = await draw(N, PA18, 'Quest 가나 OK');
			o.specimens = [];
			for (const [name, text, num, den, hangul] of [['mixed', 'Quest 가나 OK', 1, 1, PA18], ['mixed32', 'Quest 가나 OK', 3, 2, PA18], ['multiline', 'Quest 가\n\n나 OK', 1, 1, PA18], ['multiline32', 'Quest 가\n\n나 OK', 3, 2, PA18], ['fallback', 'A가\u3165나B', 1, 1, PA18], ['lines', 'A\n가', 1, 1, DK]]) {
				P.setScale(num, den);
				const d = await draw(N, hangul, text), px = P.pixels(), r = P.render();
				o.specimens.push({ name, text, scale: [num, den], latin: 'NGOTB16', hangul: hangul.slice(8, -4), err: d.err, kind: px.kind, w: px.w, h: px.h, bytes: px.bytes,
					lines: r.lines, lacks: P.lacking('\u3165')[PA18], has: P.lacking('\u3165')[N] });
			}
			P.setScale(1, 1);
			o.errs = [o.pa.err, o.dk.err, m.err, ...o.specimens.map(x => x.err)];
			// the classes at their edges, and marks: a mark joins the run before it (no face of svf/ draws U+0300..036F, so
			// this is the one place the rule shows); a mark that starts a line is Latin class
			// lines whose split tools/test_web_picker.py compares with its own class rule (runs-split.json): the class edges
			// above and astral characters (a surrogate pair is one character, Latin class) next to a lone surrogate
			o.splits = ['A\ud83d\ude00가\ud800B\ud83c\udf89나\u0301', '\ud83d\ude00\u0301가'].map(line => ({ line, runs: P.runs(line) }));
			o.split = P.runs('\u0301A\u10FF\u1100\u11FF\u1200\u312F\u3130\u318F\u3190\uA95F\uA960\uA97F\uA980\uABFF\uAC00\uD7A3\u0301\uD7A4\uD7AF\uD7B0\uD7FF\u0300x\u0301 \ud800');
			return o;
		});
		if (r.errs.some(e => e !== 0)) fail('case runs', 'render errors ' + r.errs);
		if (!r.hangulChanges) fail('case runs', `the Hangul face does not change the pangram under Latin NGOTB16 (ink ${r.pa.ink} vs ${r.dk.ink})`);
		if (!r.asciiCovered || !r.asciiSame) fail('case runs', 'ASCII-only text changed with the Hangul face (or NGOTB16 lacks it): ' + [r.asciiCovered, r.asciiSame]);
		if (!r.hangulCovered || !r.hangulSame) fail('case runs', 'Hangul-only text changed with the Latin face (or PAPLG18 lacks it): ' + [r.hangulCovered, r.hangulSame]);
		if (!r.latinChanges) fail('case runs', 'the Latin face does not change ASCII text');
		const wantSplit = [[false, '\u0301A\u10FF'], [true, '\u1100\u11FF'], [false, '\u1200\u312F'], [true, '\u3130\u318F'], [false, '\u3190\uA95F'],
			[true, '\uA960\uA97F'], [false, '\uA980\uABFF'], [true, '\uAC00\uD7A3\u0301'], [false, '\uD7A4\uD7AF'], [true, '\uD7B0\uD7FF\u0300'], [false, 'x\u0301 \uFFFD']];
		if (JSON.stringify(r.split.map(x => [x.hangul, x.text])) !== JSON.stringify(wantSplit)) fail('case runs', 'runs at the class edges: ' + JSON.stringify(r.split));
		writeFileSync(join(out, 'runs-split.json'), JSON.stringify(r.splits) + '\n');
		for (const x of r.specimens) writeFileSync(join(out, `runs-${x.name}.bin`), Buffer.from(x.bytes));
		writeFileSync(join(out, 'runs.json'), JSON.stringify(r.specimens.map(({ bytes, err, lines, lacks, has, ...x }) => x)) + '\n');
		// the canvas is as high as its lines together; multiline: the empty middle line is as high as the chain's line (max
		// scaled ascent + max scaled descent over NGOTB16 and PAPLG18, from faces.json) and has no ink, the others do
		const sum = a => a.reduce((n, v) => n + v, 0);
		for (const x of r.specimens) if (x.lines.length !== x.text.split('\n').length || x.h !== sum(x.lines)) fail('case runs', `${x.name}: canvas height ${x.h}, line heights ${x.lines}`);
		const idx = Object.fromEntries((await (await fetch(server.url + 'faces.json')).json()).faces.map(f => [f.key.slice(8, -4), f]));
		for (const ml of r.specimens.filter(x => x.name.startsWith('multiline'))) {
			const [num, den] = ml.scale, S = v => Math.floor((v * num + Math.floor(den / 2)) / den);
			const faces = [idx[ml.latin], idx[ml.hangul]];
			const chainLine = Math.max(...faces.map(f => S(f.ascent))) + Math.max(...faces.map(f => Math.ceil(f.cell[1] * num / den) - S(f.ascent))) + 2;
			const band = i => { const top = sum(ml.lines.slice(0, i)); return ml.bytes.slice(top * ml.w, (top + ml.lines[i]) * ml.w).some(v => v); };
			if (ml.lines[1] !== chainLine || band(1) || !band(0) || !band(2)) fail('case runs', `${ml.name}: line heights ${ml.lines} (the empty one should be ${chainLine}), ink by line ${[band(0), band(1), band(2)]}`);
		}
		const li = r.specimens.find(x => x.name === 'lines');
		if (!(li.lines[1] > li.lines[0])) fail('case runs', `"A\\n가": the MARUS24 line is not higher than the NGOTB16 line: ${li.lines}`);
		const fb = r.specimens.find(x => x.name === 'fallback');
		if (fb.lacks !== 1 || fb.has !== 0) fail('case runs', `fallback: PAPLG18 should lack U+3165 and NGOTB16 have it: ${fb.lacks} ${fb.has}`);
		if (nfailed === n0) counts.push(`case runs: under Latin NGOTB16 the Hangul face changes the pangram (ink ${r.pa.ink} PAPLG18, ${r.dk.ink} MARUS24); ASCII text follows only the Latin face, Hangul text only the Hangul face`);
		await p12.close();
	}

	// Case dom: every control driven through the page, as a user would. Each step checks the picker state and that the
	// canvas was painted again (putImageData calls, counted by an init script)
	{
		const n0 = nfailed, p11 = await ctx.newPage();
		const probs = [];
		p11.on('pageerror', e => probs.push('pageerror ' + e.message));
		await p11.addInitScript(() => {
			window.paints = 0;
			const put = CanvasRenderingContext2D.prototype.putImageData;
			CanvasRenderingContext2D.prototype.putImageData = function (...a) { window.paints++; return put.apply(this, a); };
		});
		await p11.goto(server.url + '?manual');
		await p11.evaluate(() => window.picker.ready);
		const look = () => p11.evaluate(() => ({ s: window.picker.settings(), chain: window.picker.chain(), paints: window.paints,
			grid: document.getElementById('grid').disabled, gridShown: !document.getElementById('gridlines').hidden,
			hangul: document.getElementById('hangul').value, latinSel: document.getElementById('latin').value,
			noneDisabled: document.querySelector('#hangul option[value=""]')?.disabled, zoom: document.getElementById('zoom').value, num: document.getElementById('num').value, den: document.getElementById('den').value,
			status: document.getElementById('status').textContent,
			// rows with a role: row name -> [data-role, tags, aria-selected]
			rows: Object.fromEntries([...document.querySelectorAll('#faces li')].filter(li => li.dataset.role).map(li => [li.querySelector('.name').textContent,
				[li.dataset.role, [...li.querySelectorAll('.tags .role')].map(t => t.textContent).join('+'), li.getAttribute('aria-selected')]])),
			sel: [...document.querySelectorAll('#faces li[aria-selected="true"]')].map(li => li.querySelector('.name').textContent),
			chip: document.querySelector('#sizes [aria-checked="true"]')?.dataset.px, pressed: document.querySelector('#variants [aria-checked="true"]')?.dataset.key }));
		const at0 = await look();
		if (at0.hangul !== '' || at0.noneDisabled !== true || at0.s.target.zoom !== 2 || !at0.grid) fail('case dom', 'at load: no disabled "(none)" Hangul placeholder shown, or the grid checkbox is enabled at zoom 2: ' + JSON.stringify(at0));
		let last = at0;
		const step = async (name, act, ok) => {
			const before = last.paints;
			await act();
			try { await p11.waitForFunction(n => window.paints > n, before, { timeout: 5000 }); } catch { /* reported below */ }
			last = await look();
			if (!(last.paints > before)) fail('case dom', `${name}: the canvas was not painted again`);
			if (!ok(last)) fail('case dom', `${name}: ` + JSON.stringify(last).slice(0, 300));
		};
		const rowsAre = (l, want) => JSON.stringify(l.rows) === JSON.stringify(want);
		if (!rowsAre(at0, {}) || at0.sel.length) fail('case dom', 'a row is marked before any face is chosen: ' + JSON.stringify(at0.rows));
		const NG = 'svf/dos/NGOTB16.SVF', NG15 = 'svf/dos/NGOTB15.SVF';
		await step('row click', () => p11.click('#faces li:has(.name:text-is("NanumGothic Bold"))'), l => l.chain.hangul === NG && l.chain.latin === NG && l.hangul === NG && l.chip === '16' && l.pressed === NG &&
			rowsAre(l, { 'NanumGothic Bold': ['latin hangul', 'Latin+Hangul', 'true'] }) && l.sel.join() === 'NanumGothic Bold');
		await step('variant chip', () => p11.click(`#variants [data-key="${NG15}"]`), l => l.chain.hangul === NG15 && l.chain.latin === NG15 && l.pressed === NG15 && l.sel.join() === 'NanumGothic Bold' &&
			rowsAre(l, { 'NanumGothic Bold': ['latin hangul', 'Latin+Hangul', 'true'] }));
		// a row click is "this family, as it comes": the default variant again, also on the selected row
		await step('row click again', () => p11.click('#faces li:has(.name:text-is("NanumGothic Bold"))'), l => l.chain.hangul === NG && l.chain.latin === NG && l.pressed === NG);
		const presetText = await p11.evaluate(() => Object.values(window.picker.presets)[3]); // the buttons follow the presets' order
		await step('preset', () => p11.click('#presets button:nth-child(4)'), l => l.s.text === presetText && l.s.text !== at0.s.text);
		await step('ratio', () => p11.selectOption('#ratio', '2/1'), l => l.s.num === 2 && l.s.den === 1 && l.num === '2' && l.den === '1');
		await step('num', () => p11.fill('#num', '3'), l => l.s.num === 3 && l.s.den === 1);
		await step('den', () => p11.fill('#den', '2'), l => l.s.num === 3 && l.s.den === 2);
		await step('MONO', () => p11.check('input[name=kind][value=mono]'), l => l.s.target.kind === 'mono');
		await step('threshold', async () => { await p11.focus('#threshold'); await p11.keyboard.press('ArrowRight'); }, l => l.s.target.threshold === at0.s.target.threshold + 1);
		await step('zoom 3', () => p11.fill('#zoom', '3'), l => l.s.target.zoom === 3 && !l.grid);
		await step('grid', () => p11.click('#grid'), l => l.s.target.grid === true && l.gridShown);
		await step('#latin select', () => p11.selectOption('#latin', ''), l => l.chain.latin === null && l.latinSel === '' && l.chain.hangul === NG && rowsAre(l, { 'NanumGothic Bold': ['hangul', 'Hangul', 'true'] }));
		await step('#hangul select', () => p11.selectOption('#hangul', 'svf/dos/PAPLG18.SVF'), l => l.chain.hangul === 'svf/dos/PAPLG18.SVF' && l.chain.latin === null && l.chip === '18' && l.sel.join() === 'Paperlogy Regular' && l.pressed === 'svf/dos/PAPLG18.SVF');
		await step('#latin select again', () => p11.selectOption('#latin', 'svf/dos/NGOTB16.SVF'), l => l.chain.latin === 'svf/dos/NGOTB16.SVF' && l.chain.hangul === 'svf/dos/PAPLG18.SVF');
		// a field can be cleared and retyped: while typing an invalid value stays in the field (state unchanged, status says
		// why); a valid one applies; on commit (Tab: 'change') an invalid field shows the state again
		await p11.fill('#num', '');
		const cleared = await look();
		if (cleared.num !== '' || cleared.s.num !== 3 || !/each must be an integer 1\.\.16/.test(cleared.status)) fail('case dom', 'a cleared #num: ' + JSON.stringify(cleared).slice(0, 300));
		await step('retyped #num', () => p11.fill('#num', '5'), l => l.s.num === 5 && l.num === '5');
		await p11.fill('#num', '17');
		const over = await look();
		await p11.locator('#num').press('Tab');
		const committed = await look();
		if (over.num !== '17' || over.s.num !== 5 || committed.num !== '5' || committed.s.num !== 5) fail('case dom', 'an invalid #num and its commit: ' + JSON.stringify([over.num, over.s.num, committed.num]));
		if (!/integer/.test(over.status) || /integer/.test(committed.status)) fail('case dom', 'the #num error is not shown while typing or not cleared on commit: ' + JSON.stringify([over.status, committed.status]));
		await p11.fill('#zoom', '');
		const zc = await look();
		await p11.locator('#zoom').press('Tab');
		const zt = await look();
		if (zc.zoom !== '' || zc.s.target.zoom !== 3 || zt.zoom !== '3' || !/zoom/.test(zc.status) || /integer/.test(zt.status)) fail('case dom', 'a cleared #zoom and its commit: ' + JSON.stringify([zc.zoom, zc.s.target.zoom, zt.zoom, zc.status, zt.status]));
		// a blank #zoom refuses only zoom: a colour change still applies (zoom keeps its value)
		await p11.evaluate(() => { const z = document.getElementById('zoom'); z.value = ''; z.dispatchEvent(new Event('input')); });
		await step('fg with a blank #zoom', () => p11.fill('#fg', '#204080'), l => l.s.target.fg === '#204080' && l.s.target.zoom === 3);
		if (nfailed === n0) counts.push(`case dom: row click, variant chip, preset, ratio, num, den, MONO, threshold, zoom 3, grid, the #latin and #hangul selects each changed the picker and repainted (${last.paints - at0.paints} paints); the row and chip follow the chain and carry Latin / Hangul tags (one row both); cleared fields wait for a valid value and show the state again on commit`);
		for (const p of probs) fail('page dom', p);
		await p11.close();
	}

	// Case sizes: the size chips and the family rows over the real index, then over an edited one
	{
		const n0 = nfailed, p13 = await ctx.newPage(), errs = [];
		p13.on('pageerror', e => errs.push(e.message));
		await p13.goto(server.url + '?manual');
		await p13.evaluate(() => window.picker.ready);
		const r = await p13.evaluate(async () => {
			const P = window.picker, o = {}, bar = document.getElementById('sizes');
			o.group = [bar.getAttribute('role'), bar.getAttribute('aria-label')];
			const chips = [...bar.querySelectorAll('button')];
			o.chips = chips.map(b => +b.dataset.px); o.sizes = P.sizes();
			o.roles = chips.every(b => b.getAttribute('role') === 'radio' && ['true', 'false'].includes(b.getAttribute('aria-checked')));
			const subset = new Set(P.faces().filter(f => f.subset).map(f => f.key));
			o.leak = [];
			const pl = (n, a, b) => `${n} ${n === 1 ? a : b}`;
			o.titles = chips.map(b => [b.title, `${pl(P.families(+b.dataset.px).length, 'family', 'families')}, ${pl(P.families(+b.dataset.px).reduce((n, f) => n + f.faces.length, 0), 'face', 'faces')}`]).filter(([a, b]) => a !== b);
			o.title16 = chips[0].title;
			o.notice = [P.notice(), document.getElementById('notice').getAttribute('role'), document.getElementById('notice').hidden]; // before any prefetch has a summary
			for (const px of P.sizes()) {
				const res = await P.setSize(px);
				if (px === 16) o.res = res; // the first look at 16 px fetches its 44 faces
				for (const li of document.querySelectorAll('#faces li[data-key]')) if (subset.has(li.dataset.key)) o.leak.push(li.dataset.key);
				if (document.querySelectorAll('#faces li').length !== P.families(px).length) o.leak.push('rows of ' + px);
			}
			o.fams = [];
			for (const px of P.sizes()) { await P.setSize(px); const m = P.families(px).map(f => JSON.stringify([f.family, f.style])), d = [...document.querySelectorAll('#faces li')].map(l => l.dataset.fam); if (JSON.stringify(m) !== JSON.stringify(d)) o.fams.push(px); }
			await P.setSize(16);
			const pos = (a, b) => !!(document.getElementById(a).compareDocumentPosition(document.getElementById(b)) & Node.DOCUMENT_POSITION_FOLLOWING);
			// the spec's tab order (search, sizes, listbox, variant strip); "also at N px" sits under the list, after the strip
			o.order = pos('f-name', 'sizes') && pos('sizes', 'faces') && pos('faces', 'variants') && pos('variants-sub', 'also');
			o.summary = P.notice(); // the last prefetch leaves its summary
			P.setNotice('hello'); o.noticeOn = [P.notice(), document.getElementById('notice').hidden, document.getElementById('notice').textContent];
			P.setNotice(''); o.noticeOff = [P.notice(), document.getElementById('notice').hidden];
			o.names = [...document.querySelectorAll('#faces li .name')].map(n => n.textContent);
			o.fam = P.families(16).map(f => [f.family, f.style, f.name]);
			o.n = document.querySelectorAll('#faces li').length;
			o.role = [...document.querySelectorAll('#faces li')].every(l => l.getAttribute('role') === 'option' && /^fam-\d+$/.test(l.id) && !l.querySelector('button, a, input, select'));
			o.list = [document.getElementById('faces').getAttribute('role'), document.getElementById('faces').getAttribute('aria-label')];
			o.count = document.getElementById('count').textContent;
			// the selects offer no subset face; COUSB24 and PAPLG16 (Latin-only) are Latin options only
			const byKey = new Map(P.faces().map(f => [f.key, f]));
			const optKeys = id => [...document.querySelectorAll(`#${id} option`)].map(x => x.value).filter(v => byKey.has(v));
			const want = f => `${f.family}${f.style ? ' ' + f.style : ''} · ${f.bpp} bpp ${f.jamo ? 'jamo set' : 'precomposed'} ${f.cell[0]}x${f.cell[1]} · ${f.key.slice(f.key.lastIndexOf('/') + 1)}`;
			o.struct = {};
			for (const id of ['latin', 'hangul']) {
				const sel = document.getElementById(id), groups = [...sel.querySelectorAll(':scope > optgroup')], bad = [];
				const loose = [...sel.querySelectorAll(':scope > option')].map(x => x.value);
				for (const og of groups) for (const x of og.querySelectorAll('option')) {
					const f = byKey.get(x.value);
					if (!f) { bad.push([og.label, x.textContent, 'no such face']); continue; } // an unknown option value is a finding, not a TypeError
					const text = want(f) + (id === 'latin' && f.latin_only ? ' · Latin only' : '');
					if (og.label !== f.px + ' px' || x.textContent !== text) bad.push([og.label, x.textContent, text]);
				}
				const labels = groups.map(g => parseInt(g.label)), floats = [...sel.querySelectorAll(':scope > option')].length;
				o.struct[id] = { bad: bad.slice(0, 3), sorted: labels.every((v, i) => !i || labels[i - 1] < v), labelsOk: groups.every(g => /^\d+ px$/.test(g.label)), n: groups.reduce((n, g) => n + g.children.length, 0), loose, floats };
			}
			o.struct.latinOnlyOpt = [...document.querySelectorAll('#latin option')].find(x => x.value === 'svf/dos/COUSB24.SVF')?.textContent;
			o.struct.expectLatin = P.faces().filter(f => !f.subset).length; o.struct.expectHangul = P.listed().filter(f => !f.latin_only).length;
			o.opt = { latSubset: optKeys('latin').filter(k => byKey.get(k).subset), hanSubset: optKeys('hangul').filter(k => byKey.get(k).subset),
				latOnlyInHangul: optKeys('hangul').filter(k => byKey.get(k).latin_only),
				lat: ['svf/dos/COUSB24.SVF', 'svf/dos/PAPLG16.SVF'].map(k => optKeys('latin').includes(k)), han: ['svf/dos/COUSB24.SVF', 'svf/dos/PAPLG16.SVF'].map(k => optKeys('hangul').includes(k)) };
			o.rej = await P.setSize(17).then(() => 'resolved', e => e.message);
			o.view = P.view();
			await P.pick('svf/dos/NGOTB16.SVF');
			o.picked = P.view();
			// the strip is named by the selected row's name: "Variant of NanumGothic Bold at 16 px"
			const lab = (document.getElementById('variants').getAttribute('aria-labelledby') ?? '').split(' ').filter(Boolean);
			o.lab = { name: lab.map(id => document.getElementById(id)?.textContent ?? '?').join(' '), row: lab.includes(document.querySelector('#faces li[aria-selected="true"] .name')?.id) };
			const q = document.getElementById('f-name'), type = v => { q.value = v; q.dispatchEvent(new Event('input')); }, vs = () => [document.getElementById('variants').hidden, document.getElementById('variants-sub').hidden];
			o.act = [document.getElementById('faces').getAttribute('aria-activedescendant'), document.querySelectorAll('#faces li.active').length];
			o.stripShown = vs();
			type('gothic a1'); o.count2 = document.getElementById('count').textContent; o.stripFiltered = vs(); // the selected row is hidden
			type(''); o.stripBack = vs();
			// move the active row away from the selected one (ArrowDown on the listbox), so only syncRows can clear it
			document.getElementById('faces').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
			o.moved = [document.getElementById('faces').getAttribute('aria-activedescendant'), document.querySelector('#faces li[aria-selected="true"]')?.id ?? null];
			await P.select({ latin: 'svf/dos/NGOTB16.SVF', hangul: 'svf/dos/BHSAN28.SVF' });
			o.sub = P.view();
			o.actSub = [document.getElementById('faces').getAttribute('aria-activedescendant'), document.querySelectorAll('#faces li.active').length, document.querySelectorAll('#faces li[aria-selected="true"]').length, document.getElementById('variants').hidden];
			return o;
		});
		if (JSON.stringify(r.group) !== '["radiogroup","Size (face file height)"]' || JSON.stringify(r.chips) !== JSON.stringify(r.sizes) || !r.roles) fail('case sizes', 'the chips: ' + JSON.stringify(r).slice(0, 300));
		if (r.titles.length || r.leak.length || !/^11 families, \d+ faces$/.test(r.title16)) fail('case sizes', 'chip titles or rows: ' + JSON.stringify([r.titles, r.leak]));
		const lcs = r.fam.map(f => [f[0].toLowerCase(), f[1].toLowerCase()]);
		if (r.n !== 11 || new Set(r.names).size !== 11 || JSON.stringify(r.names) !== JSON.stringify(r.fam.map(f => f[2])) || lcs.some((x, i) => i && (lcs[i - 1][0] > x[0] || (lcs[i - 1][0] === x[0] && lcs[i - 1][1] > x[1])))) fail('case sizes', 'the 16 px rows: ' + JSON.stringify(r.names));
		if (!r.role || r.list.join() !== 'listbox,Families') fail('case sizes', 'the listbox: ' + JSON.stringify([r.role, r.list]));
		if (!/^11 families · \d+ faces$/.test(r.count)) fail('case sizes', 'count ' + r.count);
		if (JSON.stringify(r.res) !== '{"px":16,"fetched":22,"held":0,"skipped":0,"failed":0,"stopped":false}') fail('case sizes', 'setSize(16) resolved ' + JSON.stringify(r.res));
		if (r.fams.length || !r.order) fail('case sizes', 'data-fam of the rows differs from families() at ' + r.fams + ', or the DOM order is not search, sizes, list, variants, also: ' + r.order);
		if (r.notice.join() !== ',status,true' || r.noticeOn.join() !== 'hello,false,hello' || r.noticeOff.join() !== ',true') fail('case sizes', 'notice: ' + JSON.stringify([r.notice, r.noticeOn, r.noticeOff]));
		if (r.summary !== '16 px: 22 of 22 faces fetched, 0 over the face budget, 0 failed') fail('case sizes', 'the prefetch summary on the notice line: ' + r.summary);
		if (!r.act[0] || r.act[1] !== 1 || r.stripShown.join() !== 'false,false' || r.count2 !== '2 of 11' || r.stripFiltered.join() !== 'true,true' || r.stripBack.join() !== 'false,false') fail('case sizes', 'active row, filtered strip or count: ' + JSON.stringify([r.act, r.stripShown, r.count2, r.stripFiltered, r.stripBack]));
		if (!r.moved[1]) fail('case sizes', 'no selected row after picking NGOTB16: ' + JSON.stringify(r.moved));
		else if (!r.moved[0] || r.moved[0] === r.moved[1]) fail('case sizes', 'the active row was not moved off the selected row: ' + r.moved);
		if (r.actSub[0] !== null || r.actSub[1] !== 0 || r.actSub[2] !== 0 || r.actSub[3] !== true) fail('case sizes', 'a subset Hangul face leaves an active row, a selected row or the strip: ' + JSON.stringify(r.actSub));
		const stc = r.struct;
		if (stc.latin.bad.length || stc.hangul.bad.length || !stc.latin.sorted || !stc.hangul.sorted || !stc.latin.labelsOk || !stc.hangul.labelsOk || stc.latin.n !== stc.expectLatin || stc.hangul.n !== stc.expectHangul
			|| stc.latin.loose.join() !== '' || stc.hangul.loose.join() !== '' || stc.latin.floats !== 1 || stc.hangul.floats !== 1 || stc.latinOnlyOpt !== 'Coustard Bold · 2 bpp precomposed 28x28 · COUSB24.SVF · Latin only') fail('case sizes', 'the selects\' optgroups and option text: ' + JSON.stringify(stc).slice(0, 500));
		if (r.opt.latSubset.length || r.opt.hanSubset.length || r.opt.latOnlyInHangul.length || r.opt.lat.join() !== 'true,true' || r.opt.han.join() !== 'false,false') fail('case sizes', 'the selects offer a subset face, or the Latin-only faces are misplaced: ' + JSON.stringify(r.opt));
		if (r.rej !== 'setSize: no faces of 17 px') fail('case sizes', 'setSize(17): ' + r.rej);
		if (r.view.px !== 16 || r.view.hangul !== null || r.view.same || r.view.listed || r.view.family !== '') fail('case sizes', 'view() before a pick: ' + JSON.stringify(r.view));
		const NG = 'svf/dos/NGOTB16.SVF';
		if (JSON.stringify(r.picked) !== JSON.stringify({ px: 16, family: 'NanumGothic', style: 'Bold', variant: 'KS X 1001 symbols', hangul: NG, latin: NG, same: true, listed: true })) fail('case sizes', 'view() after pick: ' + JSON.stringify(r.picked));
		if (r.lab.name !== 'Variant of NanumGothic Bold at 16 px' || !r.lab.row) fail('case sizes', 'the variant strip is not labelled by the selected row: ' + JSON.stringify(r.lab));
		if (r.sub.listed !== false || r.sub.same !== false || r.sub.family !== '' || r.sub.variant !== '' || r.sub.px !== 28) fail('case sizes', 'view() with a subset Hangul face (px is the face own 28): ' + JSON.stringify(r.sub));
		await p13.close();
		// two variants of one family with equal cell, glyphs and variant: still two chips, told apart by their file names
		const p14 = await ctx.newPage();
		p14.on('pageerror', e => errs.push(e.message));
		await p14.route('**/faces.json', async route => {
			const j = await (await route.fetch()).json();
			const a = j.faces.find(f => f.key === 'svf/dos/NGOTB15.SVF'), b = j.faces.find(f => f.key === 'svf/dos/NGOTB16.SVF');
			a.cell = [...b.cell]; a.glyphs = b.glyphs; a.variant = b.variant;
			await route.fulfill({ json: j });
		});
		await p14.goto(server.url + '?manual');
		await p14.evaluate(() => window.picker.ready);
		await p14.click('#faces li:has(.name:text-is("NanumGothic Bold"))');
		await p14.waitForFunction(() => window.picker.chain().hangul !== null);
		const ch = await p14.$$eval('#variants [role="radio"]', b => b.map(x => x.textContent));
		const lbl = await p14.evaluate(() => ({ lbls: document.querySelectorAll('#variants .lbl').length, sub: document.getElementById('variants-sub').textContent }));
		if (lbl.lbls !== 0 || !lbl.sub.startsWith('all 2 bpp precomposed, 16x16')) fail('case sizes', 'equal axes belong in the subtitle only: ' + JSON.stringify([lbl, ch]));
		if (ch.length !== 2 || !ch.some(t => t.includes('NGOTB15.SVF')) || !ch.some(t => t.includes('NGOTB16.SVF'))) fail('case sizes', 'two equal variants: ' + JSON.stringify(ch));
		await p14.close();
		for (const e of errs) fail('page sizes', e);
		if (nfailed === n0) counts.push(`case sizes: ${r.chips.length} chips equal sizes(), ${r.n} rows at 16 px unique and sorted, no subset face among the family rows of any size, setSize resolves its counts and refuses 17, view() follows the pick, the strip is named "Variant of <row> at N px", equal variants stay two chips`);
	}

	// Case pick: the row / chip clicks set both slots, the selects change one; badges and the line under each select
	{
		const n0 = nfailed, pp = await ctx.newPage(), errs = [], svf = [];
		pp.on('pageerror', e => errs.push(e.message));
		pp.on('request', r => { if (/\/faces\/.+\.SVF$/.test(r.url())) svf.push(r.url().slice(r.url().indexOf('/faces/') + 1).replace(/^faces/, 'svf')); });
		await pp.route('**/faces/dos/NGOTB15.SVF', route => route.fulfill({ status: 404, body: 'gone' }));
		await pp.goto(server.url + '?manual');
		await pp.evaluate(() => window.picker.ready);
		await pp.evaluate(() => window.picker.setSize(16));
		const noneOff = () => pp.evaluate(() => document.querySelector('#latin option[value=""]').disabled);
		if ((await noneOff()) !== true) fail('case pick', 'the Latin "(none ...)" option is enabled while no Hangul face is open');
		const D = 'svf/dos/', st = () => pp.evaluate(() => {
			const note = id => document.getElementById(id), vis = id => !document.getElementById(id).hidden;
			return { chain: window.picker.chain(), view: window.picker.view(), latSel: note('latin').value, hanSel: note('hangul').value, badges: [vis('latin-badge'), vis('hangul-badge')],
				badgeText: [note('latin-badge').textContent, note('hangul-badge').textContent], latNote: note('latin-note').textContent, latBtns: note('latin-note').querySelectorAll('button').length,
				hanNote: note('hangul-note').textContent, chip: document.querySelector('#sizes [aria-checked="true"]')?.dataset.px, sel: [...document.querySelectorAll('#faces li[aria-selected="true"]')].map(li => li.querySelector('.name').textContent),
				pressed: document.querySelector('#variants [aria-checked="true"]')?.dataset.key };
		});
		const chainIs = (l, h) => pp.waitForFunction(([l, h]) => { const c = window.picker.chain(); return c.latin === l && c.hangul === h; }, [l, h], { timeout: 5000 }).catch(() => {});
		await pp.click('#faces li:has(.name:text-is("Neo Dunggeunmo"))');
		await chainIs(D + 'NEODG16.SVF', D + 'NEODG16.SVF');
		const s1 = await st();
		if (s1.chain.latin !== D + 'NEODG16.SVF' || s1.chain.hangul !== D + 'NEODG16.SVF' || s1.latSel !== s1.chain.latin || s1.hanSel !== s1.chain.hangul || s1.badges.join() !== 'true,true' || s1.badgeText.join() !== '= list,= list' || s1.view.same !== true) fail('case pick', 'row click: ' + JSON.stringify(s1));
		if ((await noneOff()) !== false) fail('case pick', 'the Latin "(none ...)" option stays disabled with a Hangul face open');
		await pp.click(`#variants [data-key="${D}NEODG16C.SVF"]`);
		await chainIs(D + 'NEODG16C.SVF', D + 'NEODG16C.SVF');
		const s2 = await st();
		if (s2.chain.latin !== D + 'NEODG16C.SVF' || s2.chain.hangul !== D + 'NEODG16C.SVF' || s2.latSel !== s2.chain.latin || s2.hanSel !== s2.chain.hangul || s2.badges.join() !== 'true,true') fail('case pick', 'chip click (the row handler must not fire): ' + JSON.stringify(s2));
		await pp.selectOption('#latin', D + 'NGOTB16.SVF');
		await chainIs(D + 'NGOTB16.SVF', D + 'NEODG16C.SVF');
		const s3 = await st();
		if (s3.chain.latin !== D + 'NGOTB16.SVF' || s3.chain.hangul !== D + 'NEODG16C.SVF' || s3.badges.join() !== 'false,false' || s3.view.same !== false || s3.sel.join() !== 'Neo Dunggeunmo' || s3.pressed !== D + 'NEODG16C.SVF' || s3.chip !== '16' || s3.latNote !== '') fail('case pick', 'Latin select NGOTB16: ' + JSON.stringify(s3));
		// ui.afterPick (Task 5's prefetch hook) runs once for a selector change that succeeded, not for a failed one or a driver's select
		await pp.evaluate(() => { window.apCalls = 0; window.picker.spyAfterPick(() => { window.apCalls++; }); });
		await pp.selectOption('#latin', D + 'NGOTB16.SVF');
		await pp.selectOption('#latin', D + 'NGOTB15.SVF'); // 404: the chain stays, the select goes back to the slot's face
		await pp.waitForFunction(() => /HTTP 404/.test(document.getElementById('status').textContent), null, { timeout: 5000 }).catch(() => {});
		const s3b = await st();
		await pp.selectOption('#hangul', D + 'NGOTB15.SVF');
		await pp.waitForFunction(() => document.getElementById('hangul').value === 'svf/dos/NEODG16C.SVF', null, { timeout: 5000 }).catch(() => {});
		const s3c = await st(), ap = await pp.evaluate(() => window.apCalls);
		if (s3b.latSel !== D + 'NGOTB16.SVF' || s3b.chain.latin !== D + 'NGOTB16.SVF' || s3c.hanSel !== D + 'NEODG16C.SVF' || s3c.chain.hangul !== D + 'NEODG16C.SVF' || s3c.latSel !== D + 'NGOTB16.SVF') fail('case pick', 'a failed select left the DOM select on the face that did not load: ' + JSON.stringify([s3b.latSel, s3b.chain, s3c.hanSel, s3c.chain]));
		if (ap !== 1) fail('case pick', `ui.afterPick ran ${ap} times for one good selector change and two failed ones`);
		const nreq = svf.length;
		await pp.selectOption('#latin', D + 'COUSB24.SVF');
		await chainIs(D + 'COUSB24.SVF', D + 'NEODG16C.SVF');
		const s4 = await st();
		if (s4.latNote !== 'Latin: Coustard Bold 28 px is a Latin-only face: not in the list' || s4.latBtns !== 0 || s4.chip !== '16' || s4.badges.join() !== 'false,false' || svf.slice(nreq).filter(k => !k.endsWith('/NGOTB15.SVF')).join() !== D + 'COUSB24.SVF') fail('case pick', 'Latin-only face in the Latin slot: ' + JSON.stringify([s4, svf.slice(nreq)]));
		await pp.selectOption('#latin', D + 'PAPLG16.SVF');
		await chainIs(D + 'PAPLG16.SVF', D + 'NEODG16C.SVF');
		await pp.evaluate(() => window.picker.setSize(18)); // a select follows the Hangul face's size (16), so the list is put on 18 afterwards
		const s5 = await st();
		if (s5.latNote !== 'Latin: Paperlogy Regular 18 px is a Latin-only face: not in the list' || s5.latBtns !== 0 || s5.chip !== '18') fail('case pick', 'PAPLG16 at 18 px: ' + JSON.stringify(s5));
		await pp.selectOption('#latin', D + 'NGOTB16.SVF');
		await chainIs(D + 'NGOTB16.SVF', D + 'NEODG16C.SVF');
		await pp.evaluate(() => window.picker.setSize(18));
		const s6 = await st();
		if (s6.latNote !== 'Latin: NanumGothic Bold 16 px (list shows 18 px)' || s6.latBtns !== 1 || s6.chip !== '18') fail('case pick', 'list shows 18 px: ' + JSON.stringify(s6));
		await pp.click('#latin-note button');
		const s7 = await st();
		if (s7.chip !== '16' || s7.chain.latin !== D + 'NGOTB16.SVF' || s7.chain.hangul !== D + 'NEODG16C.SVF' || s7.latNote !== '') fail('case pick', 'the "list shows" button: ' + JSON.stringify(s7));
		await pp.click('#faces li:has(.name:text-is("Neo Dunggeunmo"))');
		await chainIs(D + 'NEODG16.SVF', D + 'NEODG16.SVF');
		const s8 = await st();
		if (s8.chain.latin !== D + 'NEODG16.SVF' || s8.chain.hangul !== D + 'NEODG16.SVF' || s8.badges.join() !== 'true,true' || s8.latNote !== '') fail('case pick', 'a row click sets both again: ' + JSON.stringify(s8));
		for (const e of errs) fail('page pick', e);
		if (nfailed === n0) counts.push('case pick: a row or chip click sets both slots and shows "= list" on both selects; a select changes one slot and drops the badges; a Latin-only face and a face of another size get their line under the Latin select (the latter with a button that presses its chip and leaves the chain)');
		await pp.close();
	}

	// Case hidden in chain: a subset face, or a Latin-only face, in a slot (a driver, the URL): transient option, line, no row
	{
		const n0 = nfailed, ph = await ctx.newPage(), errs = [], svf = [];
		ph.on('pageerror', e => errs.push(e.message));
		ph.on('request', r => { if (/\/faces\/.+\.SVF$/.test(r.url())) svf.push(r.url().slice(r.url().indexOf('/faces/') + 1).replace(/^faces/, 'svf')); });
		await ph.goto(server.url + '?manual');
		await ph.evaluate(() => window.picker.ready); // a fresh page: the load's chip 16 is the last pressed size
		const D = 'svf/dos/', st = () => ph.evaluate(() => {
			const id = x => document.getElementById(x), opts = x => [...id(x).querySelectorAll('option')].map(o => [o.value, o.textContent]);
			return { view: window.picker.view(), latSel: id('latin').value, hanSel: id('hangul').value, latOpts: opts('latin'), hanOpts: opts('hangul'),
				badges: [!id('latin-badge').hidden, !id('hangul-badge').hidden], latNote: id('latin-note').textContent, latBtns: id('latin-note').querySelectorAll('button').length, hanNote: id('hangul-note').textContent,
				hanBtns: id('hangul-note').querySelectorAll('button').length, pressedChips: [...document.querySelectorAll('#sizes [aria-checked="true"]')].map(b => b.dataset.px),
				sel: [...document.querySelectorAll('#faces li[aria-selected="true"]')].map(li => li.querySelector('.name').textContent), strip: id('variants').hidden,
				pressed: document.querySelector('#variants [aria-checked="true"]')?.dataset.key, transient: document.querySelectorAll("option[data-transient]").length };
		});
		const has = (opts, k, text) => opts.some(([v, t]) => v === k && t === text);
		const req0 = svf.length;
		await ph.evaluate(() => window.picker.select({ latin: null, hangul: 'svf/dos/NGOTB14.SVF' }));
		const h1 = await st(), req1 = svf.slice(req0);
		if (!has(h1.hanOpts, D + 'NGOTB14.SVF', 'NGOTB14.SVF (hidden: subset face)') || h1.hanSel !== D + 'NGOTB14.SVF' || h1.hanNote !== 'Hangul: NGOTB14 14 px is a hidden subset face: not in the list' || h1.hanBtns !== 0
			|| h1.pressedChips.join() !== '16' || h1.sel.length || h1.strip !== true || h1.view.listed !== false || h1.view.px !== 14 || h1.view.family !== '' || h1.view.style !== '' || req1.join() !== D + 'NGOTB14.SVF') fail('case hidden in chain', 'Hangul hidden: ' + JSON.stringify([h1, req1]));
		await ph.evaluate(() => window.picker.select({ latin: 'svf/dos/NGOTB14.SVF', hangul: 'svf/dos/PAPLG18.SVF' }));
		const h2 = await st();
		if (h2.pressedChips.join() !== '18' || h2.sel.join() !== 'Paperlogy Regular' || h2.pressed !== D + 'PAPLG18.SVF' || h2.latSel !== D + 'NGOTB14.SVF' || !has(h2.latOpts, D + 'NGOTB14.SVF', 'NGOTB14.SVF (hidden: subset face)')
			|| h2.latNote !== 'Latin: NGOTB14 14 px is a hidden subset face: not in the list' || h2.latBtns !== 0 || h2.badges.join() !== 'false,false' || h2.hanNote !== '' || h2.hanOpts.some(([v]) => v === D + 'NGOTB14.SVF')) fail('case hidden in chain', 'Latin hidden: ' + JSON.stringify(h2));
		await ph.evaluate(() => window.picker.select({ latin: 'svf/dos/PAPLG18.SVF', hangul: 'svf/dos/NGOTB14.SVF' }));
		const h3 = await st();
		if (h3.sel.length || h3.pressedChips.join() !== '18' || h3.hanNote !== 'Hangul: NGOTB14 14 px is a hidden subset face: not in the list' || h3.latNote !== '' || h3.latOpts.some(([v]) => v === D + 'NGOTB14.SVF')
			|| h3.strip !== true || h3.badges.join() !== 'false,false') fail('case hidden in chain', 'Hangul hidden after a listed Latin: ' + JSON.stringify(h3));
		await ph.evaluate(() => window.picker.select({ latin: null, hangul: 'svf/dos/COUSB24.SVF' }));
		const h4 = await st();
		if (!has(h4.hanOpts, D + 'COUSB24.SVF', 'COUSB24.SVF (Latin-only face)') || h4.hanSel !== D + 'COUSB24.SVF' || h4.hanNote !== 'Hangul: COUSB24 28 px is a Latin-only face: not in the list' || h4.view.listed !== false || h4.view.px !== 28 || h4.pressedChips.join() !== '18' || h4.strip !== true || h4.sel.length) fail('case hidden in chain', 'Latin-only face in the Hangul slot: ' + JSON.stringify(h4));
		await ph.evaluate(() => window.picker.select({ latin: 'svf/dos/NGOTB14.SVF', hangul: 'svf/dos/COUSB24.SVF' }));
		const h5 = await st();
		if (h5.transient !== 2 || h5.latNote !== 'Latin: NGOTB14 14 px is a hidden subset face: not in the list' || h5.hanNote !== 'Hangul: COUSB24 28 px is a Latin-only face: not in the list' || h5.sel.length || h5.strip !== true || h5.pressedChips.join() !== '18' || h5.badges.join() !== 'false,false') fail('case hidden in chain', 'both slots hidden: ' + JSON.stringify(h5));
		await ph.evaluate(() => window.picker.pick('svf/dos/NGOTB16.SVF'));
		const h6 = await st();
		if (h6.transient !== 0 || h6.latNote !== '' || h6.hanNote !== '' || h6.badges.join() !== 'true,true') fail('case hidden in chain', 'after a pick: ' + JSON.stringify(h6));
		for (const e of errs) fail('page hidden in chain', e);
		if (nfailed === n0) counts.push('case hidden in chain: a subset or Latin-only face in a slot gets a transient option and a plain line, selects no row, keeps the pressed chip, view().px is its own px; a pick removes the options');
		await ph.close();
	}

	// ---- the prefetch cases (each its own ?manual page): a size's faces are fetched under the heap lock, the marks follow ----
	const D = 'svf/dos/';
	const markWant = `(n => (n ? (n < 0 ? '!' : '-' + n) : null))`; // the "-n" / "!" a lack count shows, null for 0
	// the family row of a face (its data-fam), found from families(px) in the page
	const rowOf = (px, key) => `[...document.querySelectorAll('#faces li')].find(l => l.dataset.fam === JSON.stringify((f => [f.family, f.style])(window.picker.families(${px}).find(f => f.faces.includes('${key}')))))`;
	const until = async (fn, ms = 5000) => { const t = Date.now(); for (;;) { const v = await fn(); if (v) return v; if (Date.now() - t > ms) return null; await new Promise(r => setTimeout(r, 25)); } };
	const within = (p, ms = 5000) => Promise.race([p.then(() => true), new Promise(r => setTimeout(() => r(false), ms))]); // false when p does not settle in time
	// a route that holds the requests for glob until released; arrived resolves at the first request
	const gated = async (pg, glob) => {
		const g = { requests: 0 };
		g.released = new Promise(r => { g.release = r; }); g.arrived = new Promise(r => { g.arrive = r; });
		await pg.route(glob, async route => { g.requests++; g.arrive(); await g.released; try { await route.continue(); } catch { /* page closed */ } });
		return g;
	};
	// the chain's pixels on a fresh default-budget page, to compare with what a prefetching page drew
	const freshPixels = async (latin, hangul) => {
		const pg = await ctx.newPage();
		try {
			await pg.goto(server.url + '?manual'); await pg.evaluate(() => window.picker.ready);
			return await pg.evaluate(async ([l, h]) => { const P = window.picker; await P.select({ latin: l, hangul: h }); const r = P.render(); return { err: r.err, ink: r.ink, px: JSON.stringify(P.pixels()) }; }, [latin, hangul]);
		} finally { await pg.close(); }
	};

	const pf_scanResult = pg => pg.evaluate(`(async () => {
		const P = window.picker, M = P.module(), o = { sel: await window.selp, res: await window.szp, chain: P.chain() };
		await P.idle();
		o.info = [0, 1].map(s => { const p = M._malloc(32); M._svfw_info(s, p); const v = Array.from(M.HEAP32.subarray(p >> 2, (p >> 2) + 8)); M._free(p); return [v[1], v[2]]; });
		const r = P.render(); await P.idle();
		o.render = { err: r.err, ink: r.ink }; o.px = JSON.stringify(P.pixels()); o.log = window.slog;
		const lack = P.lacking(), want = ${markWant};
		o.bad = [...document.querySelectorAll('#faces li')].filter(l => (l.querySelector(':scope > .lack')?.textContent ?? null) !== want(lack[l.dataset.key] ?? 0)).map(l => l.dataset.key);
		return o;
	})()`);

	// Case prefetch: setSize(px) fetches the faces of that size once, in order, and the marks equal lacking(). A second look
	// finds them held; a newer chip move stops the older loop; the scan only reads the shown size (plus the chain).
	{
		const n0 = nfailed, pf = await ctx.newPage(), errs = [], hits = new Map();
		pf.on('pageerror', e => errs.push(e.message));
		pf.on('request', r => { if (r.url().endsWith('.SVF')) hits.set(r.url(), (hits.get(r.url()) ?? 0) + 1); });
		await pf.goto(server.url + '?manual');
		await pf.evaluate(() => window.picker.ready);
		const marksOk = () => pf.evaluate(`(() => {
			const P = window.picker, lack = P.lacking(), want = ${markWant}, bad = [];
			for (const el of [...document.querySelectorAll('#faces li'), ...document.querySelectorAll('#variants [data-key]')]) {
				const key = el.dataset.key, mark = el.querySelector(':scope > .lack')?.textContent ?? null;
				if (mark !== want(lack[key] ?? 0)) bad.push([key, mark, lack[key]]);
			}
			return bad;
		})()`);
		const r1 = await pf.evaluate(async () => {
			const P = window.picker;
			P.setText('Quest 가 … ™ ☺'); // '… ™ ☺' are drawn by few of these faces: marks to compare
			const res = await P.setSize(16), keys = P.families(16).flatMap(f => f.faces), mem = P.faceMemory().keys;
			await P.idle();
			return { res, n: keys.length, held: keys.every(k => mem.includes(k)), memN: mem.length };
		});
		if (JSON.stringify(r1.res) !== '{"px":16,"fetched":22,"held":0,"skipped":0,"failed":0,"stopped":false}' || r1.n !== 22 || !r1.held || r1.memN !== 22) fail('case prefetch', 'setSize(16): ' + JSON.stringify(r1));
		const bad1 = await marksOk();
		if (bad1.length) fail('case prefetch', 'row marks differ from lacking(): ' + JSON.stringify(bad1.slice(0, 3)));
		const marked = await pf.evaluate(() => document.querySelectorAll('#faces li .lack').length);
		if (!marked) fail('case prefetch', 'no row carries a mark after the prefetch of 22 faces (the check would pass for nothing)');
		const hits16 = [...hits];
		if (hits16.length !== 22 || hits16.some(([, n]) => n !== 1)) fail('case prefetch', 'each 16 px file once: ' + JSON.stringify(hits16.map(([u, n]) => [u.slice(-12), n]).filter(([, n]) => n !== 1)) + ' of ' + hits16.length);
		const before = hits.size;
		const r2 = await pf.evaluate(async () => { const P = window.picker, a = await P.setSize(24), b = await P.setSize(16); return { a, b, n24: P.families(24).reduce((n, f) => n + f.faces.length, 0) }; });
		if (hits.size !== before + r2.n24 || [...hits.values()].some(n => n !== 1)) fail('case prefetch', `24 px then 16 px again requested ${hits.size - before} new files (24 px has ${r2.n24}) or one twice`);
		if (JSON.stringify(r2.b) !== '{"px":16,"fetched":0,"held":22,"skipped":0,"failed":0,"stopped":false}' || r2.a.fetched !== r2.n24) fail('case prefetch', 'second look: ' + JSON.stringify(r2));
		// a chip move stops the loop in flight: 18 px is new, so its loop has work to stop (24 px is all held and would stop at once for any reason)
		// the 18 px loop is really under way (its first face is on the wire, held on a route) when the newer move comes: it must stop
		// after that face instead of running on, so a loop without its generation check fails here
		const first18 = await pf.evaluate(() => window.picker.families(18)[0].faces[0]);
		const g18 = await gated(pf, '**/' + first18.replace(/^svf\//, 'faces/'));
		await pf.evaluate(() => { window.a18 = window.picker.setSize(18); });
		if (!(await within(g18.arrived))) fail('case prefetch', 'the 18 px loop never requested its first face');
		await pf.evaluate(() => { window.b16 = window.picker.setSize(16); });
		g18.release();
		const r3 = await pf.evaluate(async () => ({ a: await window.a18, b: await window.b16, n18: window.picker.families(18).reduce((n, f) => n + f.faces.length, 0) }));
		if (r3.a.stopped !== true || r3.a.fetched !== 1 || r3.a.fetched >= r3.n18 || r3.b.stopped !== false || r3.b.held !== 22) fail('case prefetch', 'setSize(16) during setSize(18) (first face in flight): ' + JSON.stringify(r3));
		// the scan reads the shown size and the chain only: 44 shown faces + 2 restores, not the 27 + more faces of 24 px (and 18 px)
		await pf.evaluate(async () => { await window.picker.pick('svf/dos/NGOTB16.SVF'); await window.picker.idle(); });
		const sc = await pf.evaluate(async () => {
			const P = window.picker, M = P.module(), orig = M._svfw_open, o = { opens: 0, lens: [] };
			M._svfw_open = (slot, ptr, len) => { o.opens++; o.lens.push(len); return orig(slot, ptr, len); };
			try { P.setText('Hero 나'); P.render(); await P.idle(); } finally { M._svfw_open = orig; }
			o.fetched = P.faceMemory().keys.length;
			const by = Object.fromEntries(P.faces().map(f => [f.key, f.bytes]));
			// exactly the opened faces: the 22 faces of the shown size once each, then the chain (NGOTB16 twice) restored
			o.want = [...P.families(16).flatMap(f => f.faces).map(k => by[k]), by['svf/dos/NGOTB16.SVF'], by['svf/dos/NGOTB16.SVF']];
			return o;
		});
		if (!(sc.opens >= 1 && sc.opens <= 24) || sc.fetched <= 24 || JSON.stringify([...sc.lens].sort((a, b) => a - b)) !== JSON.stringify([...sc.want].sort((a, b) => a - b))) fail('case prefetch', `a text change scanned ${sc.opens} opens (${sc.lens.length} lengths, want the 22 faces of 16 px plus the chain twice) with ${sc.fetched} faces in memory`);
		const bad2 = await marksOk();
		if (bad2.length) fail('case prefetch', 'row and chip marks differ from lacking() after the text change: ' + JSON.stringify(bad2.slice(0, 3)));
		if (!(await pf.evaluate(() => document.querySelectorAll('#variants [data-key]').length))) fail('case prefetch', 'no variant chip to check marks on');
		for (const e of errs) fail('page prefetch', e);
		if (nfailed === n0) counts.push(`case prefetch: setSize(16) fetched 22 faces once each and marks equal lacking(); 24 px then 16 px again requested no 16 px file twice and held 22; a newer chip move stopped the older loop; a text change scanned ${sc.opens} opens (shown size plus chain) with ${sc.fetched} faces in memory`);
		await pf.close();
	}

	// Case prefetch priority: a pick made while a size is being prefetched is served first; the loop waits, then goes on
	{
		const n0 = nfailed, pq = await ctx.newPage(), errs = [], T = D + 'MARUS24.SVF';
		pq.on('pageerror', e => errs.push(e.message));
		await pq.route('**/*.SVF', async route => { await new Promise(r => setTimeout(r, route.request().url().endsWith('/MARUS24.SVF') ? 500 : 20)); try { await route.continue(); } catch { /* page closed */ } }); // a window to pick in; the picked face is slow, so a loop that did not wait for it would fetch a dozen faces meanwhile
		await pq.goto(server.url + '?manual');
		await pq.evaluate(() => window.picker.ready);
		const r = await pq.evaluate(async T => {
			const P = window.picker, o = { order: [] };
			const sz = P.setSize(24).then(v => { o.order.push('size'); return v; });
			for (let i = 0; i < 200 && !P.faceMemory().keys.length; i++) await new Promise(r => setTimeout(r, 25)); // the first face has landed
			o.mid = P.faceMemory().keys.length;
			const pk = P.pick(T).then(() => o.order.push('pick'));
			o.growAtCall = P.faceMemory().keys.length;
			await pk;
			o.growAtPick = P.faceMemory().keys.length; o.chip = document.querySelector('#sizes [aria-checked="true"]').dataset.px;
			o.res = await sz;
			const r = P.render(); await P.idle();
			o.render = { err: r.err, ink: r.ink }; o.chain = P.chain(); o.has = P.faceMemory().keys.includes(T); o.px = JSON.stringify(P.pixels());
			o.n24 = P.families(24).reduce((n, f) => n + f.faces.length, 0);
			return o;
		}, T);
		if (r.order.join() !== 'pick,size' || r.chip !== '24') fail('case prefetch priority', 'the pick did not finish before the size, or the chip moved: ' + JSON.stringify(r));
		if (!(r.mid > 0 && r.mid < r.n24 - 2) || r.growAtPick - r.growAtCall > 2) fail('case prefetch priority', `the loop was not mid-way at the pick (${r.mid} of ${r.n24}) or fetched ${r.growAtPick - r.growAtCall} faces during it`);
		if (JSON.stringify(r.res) !== '{"px":24,"fetched":20,"held":1,"skipped":0,"failed":0,"stopped":false}') fail('case prefetch priority', 'setSize resolved ' + JSON.stringify(r.res));
		if (r.render.err !== 0 || !(r.render.ink > 0) || !r.has || r.chain.hangul !== T || r.chain.latin !== T) fail('case prefetch priority', 'render or chain: ' + JSON.stringify([r.render, r.chain, r.has]));
		const ref = await freshPixels(T, T);
		if (ref.err !== 0 || ref.px !== r.px) fail('case prefetch priority', 'the pixels differ from MARUS24 x2 on a fresh page');
		for (const e of errs) fail('page prefetch priority', e);
		if (nfailed === n0) counts.push(`case prefetch priority: a pick during the 24 px prefetch finished first (${r.growAtPick - r.growAtCall} faces in memory meanwhile, its own included), the chip stayed 24, the loop then fetched 20 and held 1, and the picked face draws as on a fresh page`);
		await pq.close();
	}

	// Case prefetch shared: a select that asks for a face the prefetch is downloading waits for that download (one request), and
	// setSize waits for the scans it queued
	{
		const n0 = nfailed, ph = await ctx.newPage(), errs = [];
		ph.on('pageerror', e => errs.push(e.message));
		const reqs = [];
		ph.on('request', r => { if (r.url().endsWith('.SVF')) reqs.push(r.url()); });
		await ph.goto(server.url + '?manual');
		await ph.evaluate(() => window.picker.ready);
		const F = await ph.evaluate(() => window.picker.families(16)[0].faces[0]);
		const gF = await gated(ph, '**/' + F.replace(/^svf\//, 'faces/'));
		await ph.evaluate(() => { window.szp = window.picker.setSize(16); });
		if (!(await within(gF.arrived))) fail('case prefetch shared', 'the loop never requested its first face');
		await ph.evaluate(F => { window.selp = window.picker.select({ latin: null, hangul: F }).then(() => 'ok', e => 'rejected ' + e.message); }, F);
		if (!(await until(() => ph.evaluate(F => (window.picker.pendingKeys() ?? []).includes(F), F)))) fail('case prefetch shared', 'the select never started asking for the face'); // it asked for F in the same step: it has joined the download
		gF.release();
		const o = await ph.evaluate(async () => { const sel = await window.selp, res = await window.szp; return { sel, res, chain: window.picker.chain(), n: window.picker.faceMemory().keys.length }; });
		const nF = reqs.filter(u => u.endsWith(F.replace(/^svf\//, '/faces/'))).length;
		if (nF !== 1 || o.sel !== 'ok' || o.chain.hangul !== F || o.res.fetched + o.res.held !== 22 || o.res.skipped || o.res.failed || o.n !== 22) fail('case prefetch shared', `requests for the shared face ${nF}, ${JSON.stringify(o)}`);
		// releasing the heap lock before the held job has started neither throws nor leaves the lock held
		const early = await ph.evaluate(async () => {
			const P = window.picker, o = {};
			try { const rel = P.holdHeap(); rel(); o.threw = null; } catch (e) { o.threw = e.message; }
			o.freed = await Promise.race([P.idle().then(() => true), new Promise(r => setTimeout(() => r(false), 3000))]);
			return o;
		});
		if (early.threw !== null || !early.freed) fail('case prefetch shared', 'holdHeap released at once: ' + JSON.stringify(early));
		// setSize resolves only after the scan it queued: hold the heap lock, queue a scan with a render, and ask for the (held) size
		const h = await ph.evaluate(async () => {
			const P = window.picker, rel = P.holdHeap(), out = { done: false };
			P.setText('Quest 가 … ™ ☺'); P.render();
			const p = P.setSize(16).then(() => { out.done = true; });
			await new Promise(r => setTimeout(r, 200));
			out.early = out.done;
			rel(); await p;
			out.marks = [...document.querySelectorAll('#faces li')].filter(l => l.querySelector(':scope > .lack')).length; // no idle() before reading
			return out;
		});
		if (h.early || !h.done || !h.marks) fail('case prefetch shared', 'setSize resolved before the queued scan, or the marks were not painted when it did: ' + JSON.stringify(h));
		for (const e of errs) fail('page prefetch shared', e);
		if (nfailed === n0) counts.push('case prefetch shared: a select for the face the prefetch was downloading made one request and both counts add up to 22; setSize waited for the scan queued behind a held heap lock');
		await ph.close();
	}

	// Case prefetch carry-overs: a face that a prefetch() download shared with the loop and that was refused for room, which the
	// loop then fetched itself, counts as fetched; a failure inside the loop shows in the notice and does not reject setSize
	{
		const n0 = nfailed, pc = await ctx.newPage(), errs = [], reqs = [];
		pc.on('pageerror', e => errs.push(e.message));
		pc.on('request', r => { if (r.url().endsWith('.SVF')) reqs.push(r.url()); });
		await pc.goto(server.url + '?manual');
		await pc.evaluate(() => window.picker.ready);
		const [X, A] = await pc.evaluate(() => [window.picker.families(16)[0].faces[0], window.picker.families(24)[0].faces[0]]);
		const gX = await gated(pc, '**/' + X.replace(/^svf\//, 'faces/'));
		const budget = await pc.evaluate(async ([X, A]) => {
			const P = window.picker, by = Object.fromEntries(P.faces().map(f => [f.key, f.bytes]));
			await P.prefetch(A, []);
			window.pre = P.prefetch(X, [A]).then(() => 'fetched', e => e.code ?? e.message); // X downloads (gated); it will be refused for room when it lands
			return by[A] + by[X] - 1;
		}, [X, A]);
		if (!(await within(gX.arrived))) fail('case prefetch carry-overs', 'prefetch(X) never requested X');
		await pc.evaluate(budget => {
			const P = window.picker;
			P.setFaceBudget(budget); // X was admitted under the old budget; it lands under this one, with A protected by its keep list
			window.szc = P.setSize(16); // the loop's first face is X: it joins that download
		}, budget);
		gX.release();
		const o = await pc.evaluate(async () => ({ pre: await window.pre, res: await window.szc, files: window.picker.faceMemory().keys }));
		const nX = reqs.filter(u => u.endsWith(X.replace(/^svf\//, '/faces/'))).length;
		if (o.pre !== 'budget' || nX !== 2 || o.res.held !== 0 || o.res.failed || o.res.fetched < 1 || o.res.fetched + o.res.skipped !== 22 || o.res.stopped) fail('case prefetch carry-overs', `the shared face refused for room, then fetched by the loop (${nX} requests): ` + JSON.stringify(o).slice(0, 300));
		await pc.close();
		// a failure of the loop itself: the 404 face's mark cannot be stored
		const pd = await ctx.newPage();
		pd.on('pageerror', e => errs.push(e.message));
		await pd.goto(server.url + '?manual');
		await pd.evaluate(() => window.picker.ready);
		const Y = await pd.evaluate(() => window.picker.families(16)[1].faces[0]);
		await pd.route('**/' + Y.replace(/^svf\//, 'faces/'), route => route.fulfill({ status: 404, body: 'gone' }));
		const d = await pd.evaluate(async () => {
			const P = window.picker, set = Map.prototype.set, o = {};
			Map.prototype.set = function (k, v) { if (v?.mark === '!') throw new Error('boom'); return set.call(this, k, v); };
			try { o.res = await P.setSize(16); } catch (e) { o.rejected = e.message; } finally { Map.prototype.set = set; }
			o.notice = P.notice();
			return o;
		});
		if (d.rejected || !d.res?.error?.includes('boom') || !d.notice.includes('16 px') || !d.notice.includes('prefetch failed') || !d.notice.includes('boom')) fail('case prefetch carry-overs', 'a failure inside the loop: ' + JSON.stringify(d).slice(0, 300));
		await pd.close();
		for (const e of errs) fail('page prefetch carry-overs', e);
		if (nfailed === n0) counts.push(`case prefetch carry-overs: a shared download refused for room and then fetched by the loop counts as fetched (${nX} requests, held ${o.res.held}); a failure inside the loop is in the notice (${d.notice.slice(0, 60)}) and setSize still resolves`);
	}

	// Case prefetch errors: five default variants of 16 px families that fail in five ways show "!" with the reason and nothing of
	// them stays in the face memory; a body is read only up to its limit: the chunk that crosses it is dropped and the request
	// cancelled (a reader tap counts what the page read), a declared over-long body is refused on its header, and without a
	// stream nothing unbounded goes through arrayBuffer()
	{
		const n0 = nfailed, errs = [], P = '/faces/dos/', HUGE = '/faces/dos/MARUS24.SVF';
		const srv5 = await startServer(dist, {
			status: { '/faces/jamo-extra/SGDAY16A.SVF': 404 }, redirect: { [P + 'NEODG16.SVF']: P + 'NEODG16.SVF?r' },
			big: { [P + 'PAPER16A.SVF']: { bytes: 9000000, declared: true }, [P + 'PAPLB16A.SVF']: { bytes: 9000000, declared: false } },
		});
		// what the page reads of each response, by request path: wraps fetch (tags the Response, and the replacement for hugeUrl), clone,
		// the body getter, getReader, reader.read / cancel and arrayBuffer
		const readerTaps = hugeUrl => {
			const resp = new WeakMap(), streams = new WeakMap(), readers = new WeakMap(), reads = window.__reads = {};
			const rec = u => (reads[u] ??= { bytes: 0, lastChunk: 0, chunks: 0, cancelled: 0, arrayBuffer: 0 });
			const fetch0 = window.fetch;
			window.fetch = async function (input, init) {
				const u = new URL(typeof input === 'string' ? input : input.url, location.href).pathname;
				const r = u === hugeUrl
					? new Response(new ReadableStream({ start(c) { c.enqueue(new Uint8Array(6000000)); c.close(); } }), { status: 200, headers: { 'content-type': 'application/octet-stream' } }) // one huge chunk, no Content-Length
					: await fetch0.call(this, input, init);
				resp.set(r, u); rec(u);
				return r;
			};
			const clone0 = Response.prototype.clone;
			Response.prototype.clone = function () { const c = clone0.call(this); if (resp.has(this)) resp.set(c, resp.get(this)); return c; };
			const body0 = Object.getOwnPropertyDescriptor(Response.prototype, 'body');
			Object.defineProperty(Response.prototype, 'body', { ...body0, get() { const st = body0.get.call(this); if (st && resp.has(this)) streams.set(st, resp.get(this)); return st; } });
			const getReader0 = ReadableStream.prototype.getReader;
			ReadableStream.prototype.getReader = function (...a) { const rd = getReader0.apply(this, a); if (streams.has(this)) readers.set(rd, streams.get(this)); return rd; };
			const read0 = ReadableStreamDefaultReader.prototype.read, cancel0 = ReadableStreamDefaultReader.prototype.cancel;
			ReadableStreamDefaultReader.prototype.read = async function () {
				const res = await read0.call(this), u = readers.get(this);
				if (u && !res.done) { const x = rec(u); x.chunks++; x.bytes += res.value.length; x.lastChunk = res.value.length; }
				return res;
			};
			ReadableStreamDefaultReader.prototype.cancel = function (...a) { const u = readers.get(this); if (u) rec(u).cancelled++; return cancel0.apply(this, a); };
			const ab0 = Response.prototype.arrayBuffer;
			Response.prototype.arrayBuffer = function () { if (resp.has(this)) rec(resp.get(this)).arrayBuffer++; return ab0.call(this); };
		};
		try {
			const pe5 = await ctx.newPage();
			pe5.on('pageerror', e => errs.push(e.message));
			await pe5.addInitScript(readerTaps, HUGE);
			await pe5.route('**/faces/jamo-extra/NDGPR16.SVF', async route => {
				const b = await (await route.fetch()).body();
				await route.fulfill({ status: 200, headers: { 'content-type': 'application/octet-stream', 'content-length': String(b.length - 1) }, body: b.subarray(0, b.length - 1) });
			});
			await pe5.goto(srv5.url + '?manual');
			await pe5.evaluate(() => window.picker.ready);
			const bad = { 'svf/jamo-extra/SGDAY16A.SVF': 'HTTP 404', 'svf/jamo-extra/NDGPR16.SVF': 'the index says', 'svf/dos/NEODG16.SVF': 'redirect', 'svf/dos/PAPER16A.SVF': 'over the limit', 'svf/dos/PAPLB16A.SVF': 'more than 71172 bytes' };
			const r = await pe5.evaluate(async () => {
				const P = window.picker, o = {};
				P.setText('Quest 가 … ™ ☺');
				o.res = await P.setSize(16); await P.idle();
				const by = Object.fromEntries(P.faces().map(f => [f.key, f.bytes]));
				o.mem = P.faceMemory(); o.reads = window.__reads;
				o.rows = [...document.querySelectorAll('#faces li')].map(l => [l.dataset.key, l.querySelector(':scope > .lack')?.textContent ?? null, l.querySelector(':scope > .lack')?.title ?? null]);
				o.lack = P.lacking(); o.notice = P.notice();
				o.sizes = P.families(16).flatMap(f => f.faces).map(k => [k, by[k]]);
				return o;
			});
			if (JSON.stringify(r.res) !== '{"px":16,"fetched":17,"held":0,"skipped":0,"failed":5,"stopped":false}') fail('case prefetch errors', 'setSize(16) resolved ' + JSON.stringify(r.res));
			const want = n => (n ? (n < 0 ? '!' : '-' + n) : null), rowsBad = [];
			for (const [k, mark, title] of r.rows) {
				if (k in bad) { if (mark !== '!' || !String(title).includes(bad[k])) rowsBad.push([k, mark, title]); } else if (mark !== want(r.lack[k] ?? 0)) rowsBad.push([k, mark, r.lack[k]]);
			}
			if (rowsBad.length || r.rows.filter(([k]) => k in bad).length !== 5) fail('case prefetch errors', 'row marks: ' + JSON.stringify(rowsBad.slice(0, 5)));
			if (!r.notice.includes('5 failed')) fail('case prefetch errors', 'notice: ' + r.notice);
			const good = r.sizes.filter(([k]) => !(k in bad)), sum = good.reduce((n, [, b]) => n + b, 0);
			if (good.length !== 17 || sum !== 1437660 || r.mem.bytes !== 1437660 || r.mem.keys.some(k => k in bad) || r.mem.keys.length !== 17) fail('case prefetch errors', `face memory ${r.mem.bytes} B in ${r.mem.keys.length} faces, the 17 good faces sum ${sum}`);
			const rd = u => r.reads[u] ?? { bytes: 0, lastChunk: 0, chunks: 0, cancelled: 0, arrayBuffer: 0 };
			if (rd(P + 'PAPER16A.SVF').bytes !== 0 || rd(P + 'PAPER16A.SVF').chunks !== 0) fail('case prefetch errors', 'the declared over-long body was read: ' + JSON.stringify(rd(P + 'PAPER16A.SVF')));
			const tb = rd(P + 'PAPLB16A.SVF');
			if (!(tb.chunks > 0) || tb.bytes - tb.lastChunk > 71172 || tb.cancelled !== 1) fail('case prefetch errors', 'the chunked over-long body: ' + JSON.stringify(tb));
			const noStream = Object.entries(r.reads).filter(([u, x]) => u.startsWith('/faces/') && x.arrayBuffer !== 0).map(([u]) => u); // the wasm loader may use arrayBuffer
			if (noStream.length) fail('case prefetch errors', 'arrayBuffer() was used on ' + noStream.join());
			const idle = r.sizes.filter(([k]) => !(k in bad)).filter(([k]) => !(rd('/faces/' + k.slice(4)).chunks > 0));
			if (idle.length) fail('case prefetch errors', 'good faces read without the stream reader: ' + JSON.stringify(idle.slice(0, 3)));
			// the server side of the cancel: the client left (closed) and the paced writer stopped far short of 9,000,000 bytes, for the
			// chunked body that crossed the limit as for the declared one that was refused on its header
			for (const u of ['PAPLB16A.SVF', 'PAPER16A.SVF']) {
				const st = await until(() => { const x = srv5.stats()[P + u]; return x?.closed ? x : null; }, 5000);
				if (!st || st.completed !== false || st.error !== undefined || !(st.written < 1000000)) fail('case prefetch errors', `${u}: the client did not leave early: ${JSON.stringify(srv5.stats()[P + u])}`);
			}
			// the residual: one 6,000,000-byte chunk (no test can fail for the drop rule itself: readBounded's parts array is local and
			// discarded on the throw, so it is true by construction; this asserts the cancel and that nothing reached the memory)
			const h = await pe5.evaluate(async () => {
				const P = window.picker, snap = () => ({ mem: P.faceMemory(), heap: P.module().HEAPU8.byteLength }), before = snap(), o = {};
				o.err = await P.prefetch('svf/dos/MARUS24.SVF', []).then(() => 'accepted', e => e.message);
				o.before = before; o.after = snap(); o.reads = window.__reads['/faces/dos/MARUS24.SVF'];
				return o;
			});
			if (!h.err.includes('more than 87956 bytes') || h.reads?.chunks !== 1 || h.reads.bytes - h.reads.lastChunk !== 0 || h.reads.cancelled !== 1) fail('case prefetch errors', 'the one huge chunk: ' + JSON.stringify(h).slice(0, 300));
			if (JSON.stringify(h.before) !== JSON.stringify(h.after)) fail('case prefetch errors', 'the huge chunk changed the face memory or the heap: ' + JSON.stringify([h.before.mem.bytes, h.after.mem.bytes, h.before.heap, h.after.heap]));
			await pe5.close();
			// without a body stream the two oversized bodies are refused before arrayBuffer() is called
			const pn = await ctx.newPage();
			pn.on('pageerror', e => errs.push(e.message));
			await pn.addInitScript(readerTaps, HUGE);
			await pn.addInitScript(() => Object.defineProperty(Response.prototype, 'body', { get: () => null }));
			const srvN = await startServer(dist, { big: { [P + 'PAPER16A.SVF']: { bytes: 9000000, declared: true }, [P + 'PAPLB16A.SVF']: { bytes: 9000000, declared: false } } });
			try {
				await pn.goto(srvN.url + '?manual');
				await pn.evaluate(() => window.picker.ready);
				const n = await pn.evaluate(async () => {
					const P = window.picker, o = { body: new Response('x').body };
					o.res = await P.setSize(16); await P.idle();
					o.rows = Object.fromEntries([...document.querySelectorAll('#faces li')].map(l => [l.dataset.key, l.querySelector(':scope > .lack')?.title ?? null]));
					o.ab = Object.entries(window.__reads).filter(([, x]) => x.arrayBuffer).map(([u]) => u);
					return o;
				});
				if (n.body !== null || JSON.stringify(n.res) !== '{"px":16,"fetched":20,"held":0,"skipped":0,"failed":2,"stopped":false}') fail('case prefetch errors', 'no stream: ' + JSON.stringify([n.body, n.res]));
				if (!n.rows['svf/dos/PAPLB16A.SVF']?.includes('no Content-Length') || !n.rows['svf/dos/PAPER16A.SVF']?.includes('over the limit')) fail('case prefetch errors', 'no stream titles: ' + JSON.stringify([n.rows['svf/dos/PAPLB16A.SVF'], n.rows['svf/dos/PAPER16A.SVF']]));
				if (n.ab.includes(P + 'PAPER16A.SVF') || n.ab.includes(P + 'PAPLB16A.SVF') || !n.ab.length) fail('case prefetch errors', 'arrayBuffer reads without a stream: ' + JSON.stringify(n.ab).slice(0, 200));
			} finally { await pn.close(); await srvN.close(); }
			for (const e of errs) fail('page prefetch errors', e);
			if (nfailed === n0) counts.push(`case prefetch errors: five faces fail (404, one byte short, redirect, declared 9 MB, chunked 9 MB) and show ! with their reason, 17 good faces ${r.mem.bytes} B in memory; the chunked body was read to ${tb.bytes} B (last chunk ${tb.lastChunk}) and cancelled, the declared one not at all, the 6 MB chunk dropped (${h.err}); without a stream the oversized bodies never reach arrayBuffer()`);
		} finally { await srv5.close(); }
	}

	// Case prefetch budget: a size that does not fit is fetched as far as it goes; the rest shows "?"; a pick evicts and marks
	{
		const n0 = nfailed, pb = await ctx.newPage(), errs = [], HK = 'svf/jamo-extra/NDGPR16.SVF', RX = 'svf/jamo-extra/SGDAY16A.SVF', AD = 'svf/jamo-extra/GOTHB16A.SVF', C = D + 'NEODG16C.SVF', NG = D + 'NGOTB16.SVF';
		pb.on('pageerror', e => errs.push(e.message));
		await pb.goto(server.url + '?manual');
		await pb.evaluate(() => window.picker.ready);
		const r = await pb.evaluate(async ([HK, AD, C]) => {
			const P = window.picker, by = Object.fromEntries(P.faces().map(f => [f.key, f.bytes]));
			P.setText('Quest 가 … ™ ☺'); // SGDAY16A lacks some of it: its row mark appears
			await P.pick(HK);
			const budget = by[HK] + by[AD] + by[C] + 10; // 122978: AD and C fit beside HK, nothing else does
			P.setFaceBudget(budget);
			// the oracle: the same walk over families(16), top to bottom, a face is fetched while it fits (nothing outside the held ones can be dropped)
			const exp = { fetched: 0, held: 0, skipped: 0 }, skippedKeys = [], seq = [];
			let mem = by[HK];
			for (const f of P.families(16)) for (const k of f.faces) {
				if (k === HK) exp.held++;
				else if (mem + by[k] <= budget) { mem += by[k]; exp.fetched++; seq.push(by[k]); } else { exp.skipped++; skippedKeys.push(k); }
			}
			const res = await P.setSize(16); await P.idle();
			return { res, exp, skippedKeys, seq, budget, expMem: mem, notice: P.notice(), mem: P.faceMemory().bytes };
		}, [HK, AD, C]);
		if (r.budget !== 122978 || JSON.stringify([r.res.fetched, r.res.held, r.res.skipped, r.res.failed]) !== '[2,1,19,0]' || JSON.stringify([r.exp.fetched, r.exp.held, r.exp.skipped]) !== '[2,1,19]' || r.seq.join() !== '76040,20164' || r.res.stopped) fail('case prefetch budget', 'setSize(16) under 122,978 bytes (sizes fetched ' + r.seq.join() + '): ' + JSON.stringify(r).slice(0, 400));
		if (r.mem !== r.expMem) fail('case prefetch budget', `the oracle expects ${r.expMem} bytes in memory, the page holds ${r.mem}`);
		if (!/3 of 22 .* 19 over the face budget/.test(r.notice)) fail('case prefetch budget', 'notice: ' + r.notice);
		const rows = await pb.evaluate(`(() => [...document.querySelectorAll('#faces li')].map(l => [l.dataset.key, l.querySelector(':scope > .lack')?.textContent ?? null, l.querySelector(':scope > .lack')?.title ?? null]))()`);
		const skipped = new Set(r.skippedKeys), qs = rows.filter(([k, m]) => skipped.has(k) && m === '?');
		if (qs.length !== rows.filter(([k]) => skipped.has(k)).length || !qs.length || qs.some(x => x[2] !== 'not fetched: the 122978 byte face budget is full')) fail('case prefetch budget', 'skipped rows should show ? (not fetched: the 122978 byte face budget is full, the budget in force): ' + JSON.stringify(rows.filter(([k]) => skipped.has(k)).slice(0, 3)));
		// a pick of a skipped face evicts the oldest faces outside the chain (GOTHB16A, the oldest after the chain) and marks them
		const p = await pb.evaluate(async RX => { const P = window.picker; await P.pick(RX); await P.idle(); return { keys: P.faceMemory().keys, chain: P.chain() }; }, RX);
		if (p.keys.includes(AD) || !p.keys.includes(RX) || p.chain.hangul !== RX || p.chain.latin !== RX) fail('case prefetch budget', 'SGDAY16A pick: ' + JSON.stringify(p));
		const ad = await pb.evaluate(`(() => { const li = ${rowOf(16, AD)}; return li ? [li.dataset.key, li.querySelector(':scope > .lack')?.textContent ?? null, li.querySelector(':scope > .lack')?.title ?? null] : null; })()`);
		if (!ad || ad[0] !== AD || ad[1] !== '?' || ad[2] !== 'evicted: pick the size again to fetch') fail('case prefetch budget', 'the evicted GOTHB16A row: ' + JSON.stringify(ad));
		const rx = await pb.evaluate(`(() => { const li = ${rowOf(16, RX)}; return li ? [li.dataset.key, li.querySelector(':scope > .lack')?.textContent ?? null] : null; })()`);
		if (!rx || rx[0] !== RX || !/^-\d+$/.test(rx[1] ?? '')) fail('case prefetch budget', 'SGDAY16A row mark: ' + JSON.stringify(rx));
		// a face that cannot fit at all is refused; the chain stays
		const q = await pb.evaluate(async NG => { const P = window.picker, before = P.faceMemory().keys; let msg = 'accepted'; try { await P.pick(NG); } catch (e) { msg = e.message; } await P.idle(); return { msg, chain: P.chain(), before, after: P.faceMemory().keys }; }, NG);
		if (!/face memory/.test(q.msg) || q.chain.hangul !== RX || q.chain.latin !== RX) fail('case prefetch budget', 'NGOTB16 pick: ' + JSON.stringify(q));
		if (JSON.stringify(q.before) !== JSON.stringify(q.after)) fail('case prefetch budget', 'a pick that cannot fit evicted faces for nothing: ' + JSON.stringify([q.before.length, q.after.length]));
		for (const e of errs) fail('page prefetch budget', e);
		if (nfailed === n0) counts.push('case prefetch budget: under 122,978 bytes setSize(16) fetched 2, held 1 and skipped 19 (the oracle walk agrees), skipped rows show ?, a pick evicts GOTHB16A and marks its row, a face of 219,480 bytes is refused with the chain kept');
		await pb.close();
	}

	// Case select during eviction: a select whose faces need the room a prefetch is filling wins; the prefetch is skipped, not the select
	{
		const n0 = nfailed, pe = await ctx.newPage(), errs = [], X = D + 'NEODG32.SVF', Y = D + 'NEODG16G.SVF', P1 = D + 'NEODG16C.SVF';
		pe.on('pageerror', e => errs.push(e.message));
		const gP = await gated(pe, '**/faces/dos/NEODG16C.SVF'), gY = await gated(pe, '**/faces/dos/NEODG16G.SVF');
		await pe.goto(server.url + '?manual');
		await pe.evaluate(() => window.picker.ready);
		const by = await pe.evaluate(() => Object.fromEntries(window.picker.faces().map(f => [f.key, f.bytes])));
		if (by[X] !== 31496 || by[Y] !== 10684 || by[P1] !== 20164 || by[X] + by[Y] !== 42180 || by[X] + by[P1] !== 51660) fail('case select during eviction', 'face sizes: ' + JSON.stringify([by[X], by[Y], by[P1]]));
		await pe.evaluate(() => { window.picker.setFaceBudget(44000); window.szp = window.picker.setSize(16); });
		if (!(await within(gP.arrived))) fail('case select during eviction', 'P was never requested (setSize fetched nothing)'); // P is in flight: the loop is past its wait for the select queue (otherwise it would sit behind the select whose Y is held)
		await pe.evaluate(([X, Y]) => { window.selp = window.picker.select({ latin: X, hangul: Y }).then(() => 'ok', e => 'rejected ' + e.message); }, [X, Y]);
		const haveX = await until(() => pe.evaluate(X => window.picker.faceMemory().keys.includes(X), X));
		const haveY = await until(() => gY.requests > 0);
		if (!haveX || !haveY) fail('case select during eviction', `X fetched ${!!haveX}, Y requested ${!!haveY}`);
		gP.release();
		const rowQ = () => pe.evaluate(`(() => { const li = ${rowOf(16, P1)}; return li?.querySelector(':scope > .lack')?.textContent ?? null; })()`);
		const q1 = await until(async () => (await rowQ()) === '?');
		if (!q1) fail('case select during eviction', 'the Neo Dunggeunmo row never showed ? for P: ' + (await rowQ()));
		gY.release();
		const out = await pe.evaluate(async () => ({ sel: await window.selp, res: await window.szp, chain: window.picker.chain(), keys: window.picker.faceMemory().keys }));
		if (out.sel !== 'ok' || out.chain.latin !== X || out.chain.hangul !== Y || !out.keys.includes(X) || !out.keys.includes(Y) || out.keys.includes(P1)) fail('case select during eviction', 'select or memory: ' + JSON.stringify(out));
		if (JSON.stringify(out.res) !== '{"px":16,"fetched":0,"held":1,"skipped":21,"failed":0,"stopped":false}') fail('case select during eviction', 'setSize resolved ' + JSON.stringify(out.res));
		const dr = await pe.evaluate(() => { const r = window.picker.render(); return { err: r.err, ink: r.ink, px: JSON.stringify(window.picker.pixels()) }; });
		const ref = await freshPixels(X, Y);
		if (dr.err !== 0 || !(dr.ink > 0) || ref.err !== 0 || ref.px !== dr.px) fail('case select during eviction', 'the chain draws differently from a fresh page: ' + JSON.stringify([dr.err, dr.ink, ref.err, ref.ink]));
		for (const e of errs) fail('page select during eviction', e);
		// a failed open must not leave its selection protected: on a fresh page (F9) the select fetches NEODG16 (133,720 bytes of 140,000) and fails
		// to open it; the next prefetch must be able to evict it, which needs state.pending cleared
		const pz = await ctx.newPage(), ez = [];
		pz.on('pageerror', e => ez.push(e.message));
		await pz.route('**/faces/dos/NEODG16.SVF', async route => { const r = await route.fetch(); await route.fulfill({ response: r, body: Buffer.concat([Buffer.alloc(16), (await r.body()).subarray(16)]) }); });
		await pz.goto(server.url + '?manual');
		await pz.evaluate(() => window.picker.ready);
		const z = await pz.evaluate(async () => {
			const P = window.picker, o = {};
			P.setFaceBudget(140000);
			try { await P.select({ latin: null, hangul: 'svf/dos/NEODG16.SVF' }); o.sel = 'accepted'; } catch (e) { o.sel = e.message; }
			o.held = P.faceMemory().keys.includes('svf/dos/NEODG16.SVF');
			try { await P.prefetch('svf/dos/NEODG16G.SVF', []); o.pre = 'ok'; } catch (e) { o.pre = e.message; }
			o.keys = P.faceMemory().keys;
			return o;
		});
		if (!/svfw_open/.test(z.sel) || !z.held || z.pre !== 'ok' || z.keys.includes('svf/dos/NEODG16.SVF') || !z.keys.includes('svf/dos/NEODG16G.SVF')) fail('case select during eviction', 'failed open then prefetch: ' + JSON.stringify(z));
		for (const e of ez) fail('page select during eviction (failed open)', e);
		if (nfailed === n0) counts.push('case select during eviction: a select that needs the room wins over the prefetch in flight (P skipped with ? on its row, the loop then held 1 and skipped 21), the chain draws as on a fresh page, and a failed open leaves nothing protected');
		await pz.close();
		await pe.close();
	}

	// Case scan during select: the scan and a select's reset/opens are synchronous, so they cannot interleave; what can go wrong
	// is a scan job that read the chain (or the face list) when it was queued instead of when it ran, which would restore the
	// old chain (NEODG16C) after the select. The rule: the scan reads the chain at run time. The heap lock is defence in depth
	// for any future asynchronous step inside the scan.
	// (A scratch build whose scan captured the chain when queued still passed this case: jobs run in the order they were queued,
	// so a queued scan always ran before a later select's job. The case pins the observable order and the restores.)
	{
		const n0 = nfailed, ps = await ctx.newPage(), errs = [], X = D + 'NEODG32.SVF', Y2 = 'svf/jamo-extra/NDGPR16.SVF', OLD = D + 'NEODG16C.SVF';
		ps.on('pageerror', e => errs.push(e.message));
		const gP = await gated(ps, '**/faces/jamo-extra/GOTHB16A.SVF'), gY = await gated(ps, '**/faces/jamo-extra/NDGPR16.SVF');
		await ps.goto(server.url + '?manual');
		await ps.evaluate(() => window.picker.ready);
		await ps.evaluate(async OLD => { await window.picker.pick(OLD); window.picker.render(); await window.picker.idle(); }, OLD);
		await ps.evaluate(() => {
			const M = window.picker.module(), log = window.slog = [], r = M._svfw_reset, o = M._svfw_open;
			M._svfw_reset = () => { log.push(['reset']); return r(); };
			M._svfw_open = (slot, ptr, len) => { log.push(['open', slot, len]); return o(slot, ptr, len); };
		});
		await ps.evaluate(() => { window.szp = window.picker.setSize(16); });
		if (!(await within(gP.arrived))) fail('case scan during select', 'P was never requested (setSize fetched nothing)');
		await ps.evaluate(([X, Y2]) => { window.selp = window.picker.select({ latin: X, hangul: Y2 }).then(() => 'ok', e => 'rejected ' + e.message); }, [X, Y2]);
		if (!(await until(() => ps.evaluate(X => window.picker.faceMemory().keys.includes(X), X)))) fail('case scan during select', 'X was not fetched');
		const at = await ps.evaluate(() => window.slog.length);
		gP.release();
		const want = JSON.stringify([['reset'], ['open', 0, 76040], ['reset'], ['open', 0, 20164], ['open', 1, 20164]]);
		const got = await until(async () => { const l = await ps.evaluate(at => window.slog.slice(at), at); return l.length >= 5 ? JSON.stringify(l.slice(0, 5)) : null; });
		if (got !== want) fail('case scan during select', `P's scan then the restore of both NEODG16C slots: ${got} (want ${want})`);
		gY.release();
		const out = await pf_scanResult(ps);
		if (out.sel !== 'ok' || out.chain.latin !== X || out.chain.hangul !== Y2 || JSON.stringify(out.info) !== '[[36,36],[16,16]]') fail('case scan during select', 'chain or slot cells: ' + JSON.stringify([out.sel, out.chain, out.info]));
		const si = out.log.findIndex((e, i) => i >= at && e[0] === 'reset' && out.log[i + 1]?.[0] === 'open' && out.log[i + 1][2] === 31496 && out.log[i + 2]?.[0] === 'open' && out.log[i + 2][2] === 26764);
		if (si < 0) fail('case scan during select', 'no reset, open(0, 31496), open(1, 26764) of the select in the log');
		else {
			const rest = out.log.slice(si);
			if (rest.some(e => e[0] === 'open' && e[2] === 20164)) fail('case scan during select', 'NEODG16C was opened after the select: a scan restored the old chain');
			if (JSON.stringify(rest.slice(0, 3)) !== JSON.stringify([['reset'], ['open', 0, 31496], ['open', 1, 26764]])) fail('case scan during select', 'a scan open between the select\'s reset and its last open');
			const resets = rest.map((e, i) => e[0] === 'reset' ? i : -1).filter(i => i >= 0);
			if (resets.slice(1).some(i => rest[i + 1]?.[0] === 'open' && rest[i + 1][1] === 0 && rest[i + 2]?.[0] === 'open' && rest[i + 2][1] === 1 && (rest[i + 1][2] !== 31496 || rest[i + 2][2] !== 26764))) fail('case scan during select', 'a restore after the select opened another chain');
		}
		if (JSON.stringify(out.res) !== '{"px":16,"fetched":20,"held":2,"skipped":0,"failed":0,"stopped":false}') fail('case scan during select', 'setSize resolved ' + JSON.stringify(out.res));
		const ref = await freshPixels(X, Y2);
		if (out.render.err !== 0 || !(out.render.ink > 0) || ref.err !== 0 || ref.px !== out.px) fail('case scan during select', 'the chain draws differently from a fresh page');
		if (out.bad.length) fail('case scan during select', 'marks differ from lacking(): ' + out.bad.slice(0, 3));
		for (const e of errs) fail('page scan during select', e);
		if (nfailed === n0) counts.push('case scan during select: a scan queued by a face that arrived during a select restored the chain that was open when it ran, the select\'s reset and opens were not interleaved, and NEODG16C never came back after the select');
		await ps.close();
	}

	// Case keyboard: the size group, the listbox and the variant group by keys
	{
		const n0 = nfailed, p15 = await ctx.newPage(), errs = [];
		p15.on('pageerror', e => errs.push(e.message));
		await p15.goto(server.url + '?manual');
		await p15.evaluate(() => window.picker.ready);
		const look = () => p15.evaluate(() => ({ chip: document.querySelector('#sizes [aria-checked="true"]')?.dataset.px, rows: document.querySelectorAll('#faces li').length,
			active: document.getElementById('faces').getAttribute('aria-activedescendant'), ids: [...document.querySelectorAll('#faces li:not([hidden])')].map(l => l.id), chain: window.picker.chain(),
			focus: document.activeElement?.closest('#sizes, #faces, #variants')?.id ?? '' }));
		const wait = (fn, arg) => p15.waitForFunction(fn, arg, { timeout: 5000 }).catch(() => {});
		const k0 = await look();
		await p15.focus('#sizes button');
		await p15.keyboard.press('ArrowRight');
		const k1 = await look();
		if (k0.chip !== '16' || k1.chip !== '18' || k1.rows === k0.rows || k1.focus !== 'sizes' || k1.chain.hangul !== null) fail('case keyboard', 'ArrowRight on the size chips: ' + JSON.stringify([k0, k1]));
		await p15.keyboard.press('End');
		const kEnd = await look();
		await p15.keyboard.press('Home');
		const kHome = await look();
		if (kEnd.chip !== '54' || kHome.chip !== '16') fail('case keyboard', 'End / Home on the size chips: ' + JSON.stringify([kEnd.chip, kHome.chip]));
		await p15.keyboard.press('ArrowLeft'); // wraps from the first chip to the last
		const kLeft = await look();
		await p15.keyboard.press('ArrowUp');
		const kUp = await look();
		if (kLeft.chip !== '54' || kUp.chip !== '36' || kUp.focus !== 'sizes') fail('case keyboard', 'ArrowLeft / ArrowUp on the size chips: ' + JSON.stringify([kLeft.chip, kUp.chip]));
		await p15.keyboard.press('Home');
		await p15.keyboard.press('ArrowRight');
		await p15.focus('#faces');
		const f0 = await look();
		if (f0.active !== f0.ids[0] || f0.chain.hangul !== null) fail('case keyboard', 'focusing the listbox did not activate the first row: ' + JSON.stringify(f0));
		await p15.keyboard.press('ArrowDown');
		const f1 = await look();
		if (f1.active !== f1.ids[1] || f1.chain.hangul !== null) fail('case keyboard', 'ArrowDown: ' + JSON.stringify(f1));
		await p15.keyboard.press('Enter');
		await wait(() => window.picker.chain().hangul !== null);
		const want = await p15.evaluate(() => window.picker.families(18)[1]);
		const f2 = await look();
		if (f2.chain.hangul !== want.default || f2.chain.latin !== want.default) fail('case keyboard', 'Enter did not pick the active row: ' + JSON.stringify([f2.chain, want.default]));
		const lab18 = await p15.evaluate(() => (document.getElementById('variants').getAttribute('aria-labelledby') ?? '').split(' ').filter(Boolean).map(id => document.getElementById(id)?.textContent ?? '?').join(' '));
		if (lab18 !== `Variant of ${want.name} at 18 px`) fail('case keyboard', 'the variant strip label at 18 px: ' + lab18);
		await p15.keyboard.press('End');
		const f3 = await look();
		await p15.keyboard.press('Home');
		const f4 = await look();
		if (f3.active !== f3.ids.at(-1) || f4.active !== f4.ids[0] || f4.chain.hangul !== want.default) fail('case keyboard', 'End / Home on the listbox: ' + JSON.stringify([f3.active, f3.ids.at(-1), f4.active]));
		await p15.keyboard.press('ArrowUp'); // clamped at the first row
		const fUp = await look();
		await p15.keyboard.press('ArrowDown');
		await p15.keyboard.press('ArrowUp');
		const fUp2 = await look();
		if (fUp.active !== fUp.ids[0] || fUp2.active !== fUp.ids[0]) fail('case keyboard', 'ArrowUp on the listbox: ' + JSON.stringify([fUp.active, fUp2.active, fUp.ids[0]]));
		if (want.faces.length < 2) fail('case keyboard', 'the row picked by Enter has one variant: ' + JSON.stringify(want));
		await p15.focus('#variants [aria-checked="true"]');
		await p15.keyboard.press('ArrowRight');
		await wait(k => window.picker.chain().hangul === k, want.faces[1]);
		const v1 = await look();
		if (v1.chain.hangul !== want.faces[1] || v1.focus !== 'variants') fail('case keyboard', 'ArrowRight in the variant strip: ' + JSON.stringify([v1, want.faces]));
		await p15.keyboard.press('ArrowLeft'); // back to the first chip, then ArrowUp from the first wraps to the last again
		await wait(k => window.picker.chain().hangul === k, want.faces[0]);
		const vL = await look();
		await p15.keyboard.press('ArrowUp');
		await wait(k => window.picker.chain().hangul === k, want.faces[1]);
		const vU = await look();
		if (vL.chain.hangul !== want.faces[0] || vU.chain.hangul !== want.faces[1]) fail('case keyboard', 'ArrowLeft / ArrowUp in the variant strip: ' + JSON.stringify([vL.chain, vU.chain, want.faces]));
		await p15.focus('#faces');
		await p15.keyboard.press('Home'); // the active row leaves the selected one (fam-1) ...
		await p15.focus('#variants [aria-checked="true"]');
		await p15.focus('#faces'); // ... and focusing the listbox brings it back
		const sel1 = await look();
		if (sel1.active !== 'fam-1') fail('case keyboard', 'focusing the listbox did not activate the selected row: ' + sel1.active);
		// Enter and Space on the selected row (its variant is not the default) pick the default variant
		await p15.keyboard.press('Enter');
		await wait(k => window.picker.chain().hangul === k, want.default);
		const en = await look();
		if (en.chain.hangul !== want.default || en.chain.latin !== want.default) fail('case keyboard', 'Enter on the selected row did not pick the default: ' + JSON.stringify([en.chain, want.default]));
		await p15.focus('#variants [aria-checked="true"]');
		await p15.keyboard.press('ArrowRight');
		await wait(k => window.picker.chain().hangul === k, want.faces[1]);
		await p15.focus('#faces');
		await p15.keyboard.press(' ');
		await wait(k => window.picker.chain().hangul === k, want.default);
		const sp0 = await look();
		if (sp0.chain.hangul !== want.default) fail('case keyboard', 'Space on the selected row did not pick the default: ' + JSON.stringify([sp0.chain, want.default]));
		await p15.keyboard.type('pa');
		const wantPa = await p15.evaluate(() => window.picker.families(18).findIndex(r => r.name.toLowerCase().startsWith('pa')));
		const t1 = await look();
		if (wantPa < 0 || t1.active !== 'fam-' + wantPa) fail('case keyboard', 'type-ahead "pa": ' + JSON.stringify([t1.active, wantPa]));
		// Space picks the active row, also right after typing (within the type-ahead window): the default variant of that row
		await p15.keyboard.press(' ');
		const wantSp = await p15.evaluate(i => window.picker.families(18)[i].default, wantPa);
		await wait(k => window.picker.chain().hangul === k, wantSp);
		const sp = await look();
		if (sp.chain.hangul !== wantSp || sp.chain.latin !== wantSp) fail('case keyboard', 'Space did not pick the active row: ' + JSON.stringify([sp.chain, wantSp]));
		// type-ahead goes to the NEXT family starting with the letters, from the active row on, wrapping: "n" from the "pa"
		// row wraps to the first N family, a second "n" moves to the next N family, and so on round to the first again
		const nIdx = await p15.evaluate(() => window.picker.families(18).map((f, i) => f.name.toLowerCase().startsWith('n') ? i : -1).filter(i => i >= 0));
		const seenN = [];
		for (let i = 0; i <= nIdx.length; i++) { await p15.keyboard.press('n'); seenN.push((await look()).active); }
		const wantN = [...nIdx, nIdx[0]].map(i => 'fam-' + i);
		if (nIdx.length < 2 || JSON.stringify(seenN) !== JSON.stringify(wantN)) fail('case keyboard', 'type-ahead "n" repeated: ' + JSON.stringify([seenN, wantN]));
		// a mouse click on a row while the focus is elsewhere and the list is scrolled away from the selected row is not lost
		// (the focus handler must not scroll back under the pointer)
		const p16 = await ctx.newPage();
		p16.on('pageerror', e => errs.push(e.message));
		await p16.goto(server.url);
		await p16.evaluate(() => window.picker.ready);
		await p16.evaluate(() => { const u = document.getElementById('faces'); u.style.height = u.style.maxHeight = '120px'; u.scrollTop = u.scrollHeight; }); // a short list, so that 11 rows scroll
		await p16.focus('#f-name');
		const lastKey = await p16.evaluate(() => window.picker.families(16).at(-1).default);
		const before = await p16.evaluate(() => document.getElementById('faces').scrollTop);
		await p16.locator('#faces li').last().click();
		await p16.waitForFunction(k => window.picker.chain().hangul === k, lastKey, { timeout: 3000 }).catch(() => {});
		const after = await p16.evaluate(() => ({ chain: window.picker.chain(), top: document.getElementById('faces').scrollTop }));
		if (before < 1 || after.chain.hangul !== lastKey) fail('case keyboard', 'a click on the last row was lost: ' + JSON.stringify([after, lastKey, before]));
		await p16.close();
		for (const e of errs) fail('page keyboard', e);
		if (nfailed === n0) counts.push('case keyboard: arrows, Home and End move the size chips, the listbox and the variant strip; Enter picks the active row; type-ahead finds the first family starting with "pa" and a repeated "n" steps through the N families, wrapping');
		await p15.close();
	}

	// Case E: hostile faces.json URLs are rejected without a request; bad colours; render failures reach the status line
	{
		const p3 = await ctx.newPage();
		const reqs = [], probs = [];
		p3.on('request', r => reqs.push(r.url()));
		p3.on('pageerror', e => probs.push('pageerror ' + e.message));
		const bad = ['https://evil.invalid/a.SVF', '//evil.invalid/a.SVF', 'data:application/octet-stream;base64,AAAA', 'blob:x', '../faces.json', 'faces/../../x.SVF', '/etc/passwd', 'faces/%zz.SVF', 'faces%2f..%2f..%2fx.SVF', 'faces/dos%5C..%5Cx.SVF', 'faces/dos%2FPAPLG18.SVF'];
		// the index check refuses each hostile url by name, before any request; one page per url (the page is dead after that)
		for (let i = 0; i < bad.length; i++) {
			const pb = await ctx.newPage();
			pb.on('request', r => reqs.push(r.url()));
			await pb.route('**/faces.json', async route => {
				const j = await (await route.fetch()).json();
				j.faces[3].url = bad[i];
				await route.fulfill({ json: j });
			});
			await pb.goto(server.url + '?manual');
			const res = await pb.evaluate(() => window.picker.ready.then(() => 'loaded', e => String(e.message)));
			if (!/^faces\.json: face 3 "[^"]+": url must be faces\/<rel> for this key$/.test(res)) fail('case E', `${bad[i]} was not rejected by the index check: ${res}`);
			await pb.close();
		}
		// the same urls as licences are refused by safeUrl, naming the url (licences/ ones too)
		for (const u of [...bad, 'licences/..%2f..%2fx.txt', 'licences/../../x.txt']) {
			const pl = await ctx.newPage();
			await pl.route('**/faces.json', async route => {
				const j = await (await route.fetch()).json();
				j.faces[3].licences = [u];
				await route.fulfill({ json: j });
			});
			await pl.goto(server.url + '?manual');
			const res = await pl.evaluate(() => window.picker.ready.then(() => 'loaded', e => String(e.message)));
			if (!/^faces\.json: face 3 "[^"]+": licence /.test(res) || /must be under licences/.test(res) || !res.includes(u)) fail('case E', `licence ${u} was not refused by safeUrl: ${res}`);
			await pl.close();
		}
		await p3.goto(server.url + '?manual');
		await p3.evaluate(() => window.picker.ready);
		if (reqs.some(u => /evil\.invalid|^data:|^blob:|passwd|x\.SVF|%2f|%5c/i.test(u))) fail('case E', 'a hostile URL was requested: ' + JSON.stringify(reqs));
		const tgt = await p3.evaluate(() => {
			const out = [];
			for (const c of ['red', '#12345', '#12345g', 'url(x)', 5, null]) { try { window.picker.setTarget({ fg: c }); out.push('accepted'); } catch (e) { out.push('rejected'); } }
			return out;
		});
		if (tgt.some(x => x !== 'rejected')) fail('case E', 'bad colours accepted: ' + tgt);
		const good = await p3.evaluate(async () => {
			const P = window.picker;
			await P.select({ latin: null, hangul: 'svf/dos/PAPLG18.SVF' });
			P.setText('가'.repeat(5000)); P.setScale(16, 1); // fits the text limit, not the canvas limit
			const r = P.render();
			return { r, status: document.getElementById('status').textContent };
		});
		if (good.r.err === 0 || !good.status.includes('too large')) fail('case E', 'a direct render failure did not reach the status line: ' + JSON.stringify(good));
		// MONO packs 8 pixels a byte: 60 lines of 80 syllables at 16/1 fit the 64 MiB pixel budget packed, not as RGBA
		const rgba = await p3.evaluate(() => {
			const P = window.picker;
			P.setTarget({ kind: 'mono' }); P.setScale(1, 1); P.setText('가');
			const before = P.render().err === 0 && P.pixels() !== null; // a good render first: its buffer must not outlive the failure
			P.setScale(16, 1); P.setText(Array(60).fill('가'.repeat(80)).join('\n'));
			const r = P.render(), w = r.width + 2, h = (r.ascent + r.descent + 2) * 60, drawn = P.pixels();
			P.setTarget({ kind: 'gray8' });
			return { r, before, drawn, packed: ((w + 7) >> 3) * h, rgba: 4 * w * h, status: document.getElementById('status').textContent };
		});
		if (!(rgba.packed <= 64 << 20 && rgba.rgba > 64 << 20)) fail('case E', 'the RGBA test text does not separate the budgets: ' + JSON.stringify(rgba));
		if (!rgba.before || rgba.drawn !== null) fail('case E', 'pixels() still returns the last good buffer after a failed render');
		if (rgba.r.err !== 7 || !/bytes of RGBA, the limit is 67108864$/.test(rgba.r.errName) || !rgba.status.includes(rgba.r.errName)) fail('case E', 'an RGBA canvas over the budget: ' + JSON.stringify(rgba));
		// setText refuses over-long text (JS length, then UTF-8 bytes) before storing it; the status line says why
		const txt = await p3.evaluate(() => {
			const P = window.picker, o = [];
			P.setText('keep'); P.setScale(1, 1);
			for (const t of ['x'.repeat(20000), '가'.repeat(6000)]) {
				let msg = 'accepted';
				try { P.setText(t); } catch (e) { msg = e.message; }
				o.push({ msg, status: document.getElementById('status').textContent, text: document.getElementById('text').value });
			}
			return o;
		});
		for (const t of txt) if (!/^text is (at least )?\d+ bytes, the limit is 16384$/.test(t.msg) || !t.status.includes(t.msg) || t.text !== 'keep') fail('case E', 'setText over the limit: ' + JSON.stringify(t).slice(0, 300));
		// typed into the textarea: it goes back to the text the picker holds, the status line says why
		for (const t of ['x'.repeat(20000), '가'.repeat(6000)]) {
			await p3.fill('#text', t);
			const ui = await p3.evaluate(() => ({ text: document.getElementById('text').value, status: document.getElementById('status').textContent }));
			if (ui.text !== 'keep' || !/text is (at least )?\d+ bytes, the limit is 16384/.test(ui.status)) fail('case E', 'over-long typed text: ' + JSON.stringify(ui).slice(0, 300));
		}
		counts.push(`case E: ${bad.length} hostile URLs rejected without a request, bad colours rejected, render failure and over-long text shown in the status line, typed over-long text taken back, an RGBA canvas over the pixel budget refused`);
		for (const p of probs) fail('page E', p);
		await p3.close();
	}

	// Case url: the query carries the chain and the scale (readUrl, writeUrl); every fault is a notice, ready never rejects for one
	{
		const n0 = nfailed, errs = [], D = 'svf/dos/', U = k => D + k + '.SVF';
		const opened = async (query, huge) => {
			const pu = await ctx.newPage(), reqs = [];
			if (huge) { // the server cannot take such a URL: the document is served by a route; a spy sees the longest string URLSearchParams was given
				await pu.addInitScript(() => { const U0 = window.URLSearchParams; window.__maxQ = 0; window.URLSearchParams = class extends U0 { constructor(a, ...b) { super(a, ...b); if (typeof a === 'string') window.__maxQ = Math.max(window.__maxQ, a.length); } }; });
				await pu.route(u => u.search.length > 100000, async route => route.fulfill({ response: await route.fetch({ url: server.url }) }));
			}
			pu.on('pageerror', e => errs.push(e.message));
			pu.on('request', r => { const p = new URL(r.url()).pathname; if (p.endsWith('.SVF')) reqs.push(p); }); // the page's own URL may end in .SVF (its query)
			await pu.goto(server.url + query);
			const ready = await pu.evaluate(() => window.picker.ready.then(() => 'ok', e => String(e.message)));
			if (ready !== 'ok') fail('case url', `${query.slice(0, 80)}: ready rejected: ${ready}`);
			await pu.evaluate(() => window.picker.prefetching());
			const o = await pu.evaluate(() => ({ chain: window.picker.chain(), s: window.picker.settings(), notice: window.picker.notice(), chip: [...document.querySelectorAll('#sizes [aria-checked=true]')].map(b => +b.dataset.px), search: location.search }));
			return { pu, reqs, maxQ: huge ? await pu.evaluate(() => window.__maxQ) : 0, ...o };
		};
		const chainIs = (r, latin, hangul) => r.chain.latin === (latin && U(latin)) && r.chain.hangul === (hangul && U(hangul));
		const sc = (r, n, d) => r.s.num === n && r.s.den === d;
		const check = (name, r, ok, note) => { if (!ok) fail('case url', `${name}: ${JSON.stringify({ chain: r.chain, scale: [r.s.num, r.s.den], chip: r.chip, notice: r.notice.slice(0, 160), search: r.search.slice(0, 120) })}${note ?? ''}`); };
		let r = await opened('?hangul=svf/dos/MARUS24.SVF&latin=&scale=2/1');
		check('hangul+empty latin+scale', r, chainIs(r, null, 'MARUS24') && sc(r, 2, 1) && r.chip.join() === '24' && r.notice.startsWith('24 px:'));
		await r.pu.close();
		r = await opened('?hangul=svf/dos/MARUS24.SVF');
		check('hangul only', r, chainIs(r, 'MARUS24', 'MARUS24') && sc(r, 1, 1)); await r.pu.close();
		r = await opened('?latin=svf/dos/NEODG32.SVF');
		check('latin only', r, chainIs(r, 'NEODG32', 'NGOTB16') && r.chip.join() === '16'); await r.pu.close();
		// F5 and the look of the finished page: a fault-free load (no query) ends with the plain prefetch summary and no URL notice before it
		r = await opened('');
		check('default page', r, chainIs(r, 'NGOTB16', 'NGOTB16') && r.notice === '16 px: 22 of 22 faces fetched, 0 over the face budget, 0 failed');
		await r.pu.screenshot({ path: join(out, 'page-default.png'), fullPage: true }); await r.pu.close();
		// F4: a URL fault outlives the first prefetch (the summary is appended after it)
		r = await opened('?hangul=svf/dos/NOPE.SVF');
		check('no face', r, chainIs(r, 'NGOTB16', 'NGOTB16') && r.notice.startsWith('URL: no face svf/dos/NOPE.SVF; the default opened; 16 px: ') && /\d+ of 22 faces fetched/.test(r.notice)); await r.pu.close();
		for (const v of ['bad', '0/0', '17/1']) {
			r = await opened('?scale=' + v);
			check('scale ' + v, r, chainIs(r, 'NGOTB16', 'NGOTB16') && sc(r, 1, 1) && r.notice.startsWith(`URL: scale ${v} ignored; `) && new URLSearchParams(r.search).get('scale') === '1/1'); await r.pu.close();
		}
		r = await opened('?x=' + 'a'.repeat(3000));
		check('long query', r, chainIs(r, 'NGOTB16', 'NGOTB16') && r.notice.startsWith('URL ignored: too long; ')); await r.pu.close();
		r = await opened('?hangul=svf/dos/MARUS24.SVF&x=' + 'a'.repeat(300));
		check('long value', r, chainIs(r, 'NGOTB16', 'NGOTB16') && r.notice.startsWith('URL ignored: too long')); await r.pu.close();
		for (const [k, word] of [['COUSB24', 'Latin-only'], ['NGOTB14', 'hidden subset']]) {
			r = await opened('?hangul=svf/dos/' + k + '.SVF');
			check('hangul ' + k, r, chainIs(r, 'NGOTB16', 'NGOTB16') && r.notice.includes(U(k)) && r.notice.includes(word) && !r.reqs.some(u => u.endsWith('/' + k + '.SVF'))); await r.pu.close();
		}
		r = await opened('?hangul=svf/dos/MARUS24.SVF&latin=svf/dos/COUSB24.SVF');
		check('latin-only latin', r, chainIs(r, 'COUSB24', 'MARUS24')); await r.pu.close();
		r = await opened('?latin=svf/dos/NGOTB14.SVF');
		check('subset latin', r, chainIs(r, null, 'NGOTB16') && !r.reqs.some(u => u.endsWith('/NGOTB14.SVF')) && r.notice.includes('NGOTB14') && r.notice.includes('hidden subset') && r.notice.includes('Latin none')); await r.pu.close();
		r = await opened('?latin=svf/dos/NOPE.SVF');
		check('missing latin', r, chainIs(r, null, 'NGOTB16') && !r.reqs.some(u => u.endsWith('/NOPE.SVF')) && r.notice.includes('no face svf/dos/NOPE.SVF; Latin none')); await r.pu.close();
		// the URL follows a pick; a reload restores the chain and the scale; other parameters are kept
		r = await opened('?scale=2/1&keep=1');
		await r.pu.evaluate(() => window.picker.pick('svf/dos/NEODG16.SVF'));
		let q = await r.pu.evaluate(() => ({ s: location.search, h: new URLSearchParams(location.search).get('hangul'), l: new URLSearchParams(location.search).get('latin'), sc: new URLSearchParams(location.search).get('scale'), keep: new URLSearchParams(location.search).get('keep') }));
		if (q.h !== U('NEODG16') || q.l !== U('NEODG16') || q.sc !== '2/1' || q.keep !== '1' || !/hangul=svf%2Fdos%2FNEODG16\.SVF/.test(q.s)) fail('case url', 'after a pick: ' + JSON.stringify(q));
		await r.pu.evaluate(() => window.picker.setScale(3, 2));
		q = await r.pu.evaluate(() => new URLSearchParams(location.search).get('scale'));
		if (q !== '3/2') fail('case url', 'after setScale: ' + q);
		await r.pu.evaluate(() => window.picker.select({ latin: null, hangul: 'svf/dos/NEODG16.SVF' }));
		q = await r.pu.evaluate(() => new URLSearchParams(location.search).get('latin'));
		if (q !== '') fail('case url', 'a select without Latin should write latin= empty: ' + JSON.stringify(q));
		await r.pu.reload();
		await r.pu.evaluate(() => window.picker.ready); await r.pu.evaluate(() => window.picker.prefetching());
		const back = await r.pu.evaluate(() => ({ chain: window.picker.chain(), s: window.picker.settings() }));
		if (back.chain.hangul !== U('NEODG16') || back.chain.latin !== null || back.s.num !== 3 || back.s.den !== 2) fail('case url', 'after a reload: ' + JSON.stringify(back));
		await r.pu.close();
		// ?manual: no default, no URL chain, no prefetch, no .SVF request; a bad scale is still a notice
		r = await opened('?manual&hangul=svf/dos/MARUS24.SVF&scale=bad');
		check('manual', r, chainIs(r, null, null) && r.reqs.length === 0 && r.notice.includes('scale') && sc(r, 1, 1)); await r.pu.close();
		// ---- fix round 1
		// 1: the bounds, exactly. The query counts with its '?'. A huge query is never parsed (ignored, notice, default chain).
		const mk = (n, head = '?hangul=svf/dos/MARUS24.SVF') => { let q = head, i = 0; while (n - q.length > 250) q += '&p' + i++ + '=' + 'a'.repeat(200); const rem = n - q.length; return q + '&q=' + 'a'.repeat(rem - 3); };
		for (const [name, query, ok] of [['2048 chars', mk(2048), true], ['2049 chars', mk(2049), false], ['value of 256', '?hangul=svf/dos/MARUS24.SVF&v=' + 'a'.repeat(256), true], ['value of 257', '?hangul=svf/dos/MARUS24.SVF&v=' + 'a'.repeat(257), false], ['key of 256', '?hangul=svf/dos/MARUS24.SVF&' + 'k'.repeat(256) + '=1', true], ['key of 257', '?hangul=svf/dos/MARUS24.SVF&' + 'k'.repeat(257) + '=1', false], ['200,000 chars', '?hangul=svf/dos/MARUS24.SVF&x=' + 'a'.repeat(200000), false]]) {
			if (name === '2048 chars' || name === '2049 chars') { const want = +name.slice(0, 4); if (query.length !== want) fail('case url', `${name}: the test query has ${query.length} characters`); }
			r = await opened(query, query.length > 100000);
			if (r.maxQ > 2048) fail('case url', `${name}: URLSearchParams was given ${r.maxQ} characters`);
			check('bound ' + name, r, ok ? chainIs(r, 'MARUS24', 'MARUS24') && !r.notice.includes('too long') : chainIs(r, 'NGOTB16', 'NGOTB16') && r.notice.startsWith('URL ignored: too long; '));
			await r.pu.close();
		}
		// 2 and 3: ?manual keeps a bad face as a notice (no chain, no request); hostile values are text only and never requested
		for (const [name, key] of [['typo', 'svf/dos/TYPO.SVF'], ['hidden', U('NGOTB14')], ['latin-only', U('COUSB24')]]) {
			r = await opened('?manual&hangul=' + encodeURIComponent(key));
			check('manual ' + name, r, chainIs(r, null, null) && r.reqs.length === 0 && r.notice.includes(key) && r.notice.startsWith('URL: ')); await r.pu.close();
		}
		// 2b: a bad latin under ?manual ends like a bad hangul: nothing opened
		for (const [name, key] of [['typo', 'svf/dos/TYPO.SVF'], ['hidden', U('NGOTB14')]]) {
			r = await opened('?manual&latin=' + encodeURIComponent(key));
			check('manual latin ' + name, r, chainIs(r, null, null) && r.reqs.length === 0 && r.notice.includes(key) && r.notice.endsWith('nothing opened (?manual)') && !r.notice.includes('Latin none')); await r.pu.close();
		}
		const hostile = ['../../x.SVF', '%2f..%2fx', 'javascript:alert(1)', '<img src=x onerror=document.title=1>', 'svf/dos/' + 'z'.repeat(247), '__proto__', 'constructor'];
		for (const key of hostile) for (const which of ['hangul', 'latin']) {
			r = await opened('?' + which + '=' + encodeURIComponent(key));
			const ids = await r.pu.evaluate(() => ({ kids: document.getElementById('notice').children.length, imgs: document.querySelectorAll('img').length, title: document.title })), valid = await r.pu.evaluate(() => window.picker.faces().map(f => '/' + f.url));
			check(`hostile ${which} ${key.slice(0, 20)}`, r, chainIs(r, which === 'hangul' ? 'NGOTB16' : null, 'NGOTB16') && r.notice.startsWith('URL: no face ' + key + '; ') && ids.kids === 0 && ids.imgs === 0 && ids.title !== '1' && r.reqs.every(u => valid.includes(u)) && !r.reqs.some(u => /x\.SVF|zzzz/.test(u)));
			await r.pu.close();
		}
		// 4: latin absent is the Hangul face, whether the Hangul face came from the URL or is the default; with no default face there is no chain
		{
			const routed = async query => {
				const pr = await ctx.newPage(), reqs = [];
				pr.on('pageerror', e => errs.push(e.message));
				await pr.route('**/faces.json', async route => { const j = await (await route.fetch()).json(); j.faces = j.faces.filter(f => f.key !== U('NGOTB16')); await route.fulfill({ json: j }); });
				await pr.goto(server.url + query);
				const ready = await pr.evaluate(() => window.picker.ready.then(() => 'ok', e => String(e.message)));
				const o = await pr.evaluate(() => ({ chain: window.picker.chain(), notice: window.picker.notice() }));
				await pr.close();
				return { ready, ...o };
			};
			let x = await routed('?hangul=svf/dos/MARUS24.SVF');
			if (x.ready !== 'ok' || x.chain.latin !== U('MARUS24') || x.chain.hangul !== U('MARUS24')) fail('case url', 'routed index, hangul only: ' + JSON.stringify(x));
			x = await routed('');
			if (x.ready !== 'ok' || x.chain.latin !== null || x.chain.hangul !== null) fail('case url', 'routed index without the default face: ' + JSON.stringify(x));
			x = await routed('?hangul=svf/dos/NOPE.SVF');
			if (x.chain.hangul !== null || x.notice.includes('the default opened') || !x.notice.includes('nothing opened')) fail('case url', 'no default face in the index: the notice must say nothing opened: ' + JSON.stringify(x));
		}
		// 5: two faults, two notices, joined with "; " ahead of the prefetch line
		r = await opened('?hangul=svf/dos/NOPE.SVF&latin=svf/dos/NGOTB14.SVF&scale=bad');
		check('three faults', r, r.notice.startsWith('URL: no face svf/dos/NOPE.SVF; the default opened; URL: svf/dos/NGOTB14.SVF is a hidden subset face; Latin none; URL: scale bad ignored; 16 px: ') && chainIs(r, null, 'NGOTB16') && !r.reqs.some(u => u.endsWith('/NGOTB14.SVF'))); await r.pu.close();
		// 6: writeUrl never writes a query over 2048 or a value over 256; the page's own state round-trips through a reload
		r = await opened('?keep=1&big=' + 'a'.repeat(300));
		check('big value', r, r.notice.startsWith('URL ignored: too long') && !r.search.includes('big=') && r.search.includes('keep=1') && new URLSearchParams(r.search).get('hangul') === U('NGOTB16'));
		await r.pu.reload(); await r.pu.evaluate(() => window.picker.ready); await r.pu.evaluate(() => window.picker.prefetching());
		q = await r.pu.evaluate(() => window.picker.notice());
		if (q.includes('too long')) fail('case url', 'the rewritten URL was ignored again: ' + q); await r.pu.close();
		r = await opened(mk(2500, '?manual&hangul=svf/dos/MARUS24.SVF'));
		await r.pu.evaluate(() => window.picker.select({ latin: null, hangul: 'svf/dos/MARUS24.SVF' }));
		q = await r.pu.evaluate(() => location.search);
		if (q.length > 2048 || !q.includes('hangul=') || !q.includes('manual')) fail('case url', 'a query over 2048 was kept: ' + q.length + ' ' + q.slice(0, 60));
		await r.pu.reload(); await r.pu.evaluate(() => window.picker.ready);
		q = await r.pu.evaluate(() => ({ n: window.picker.notice(), c: window.picker.chain() }));
		if (q.n.includes('too long') || q.c.hangul !== null) fail('case url', 'reload of the rewritten manual URL: ' + JSON.stringify(q)); await r.pu.close();
		// 7: the URL notice ends with the first loop, also a stopped one; a ?manual page does not carry it to its first setSize
		{
			const pd = await ctx.newPage();
			pd.on('pageerror', e => errs.push(e.message));
			await pd.route('**/*.SVF', async route => { await new Promise(ok => setTimeout(ok, 60)); try { await route.continue(); } catch { /* closed */ } });
			await pd.goto(server.url + '?scale=bad');
			await pd.evaluate(() => window.picker.ready);
			await pd.evaluate(() => window.picker.setSize(24)); // stops the load loop at 16 px
			const n1 = await pd.evaluate(() => window.picker.notice());
			if (n1.includes('scale') || !n1.startsWith('24 px: ')) fail('case url', 'the URL notice outlived a stopped loop: ' + n1);
			await pd.close();
			r = await opened('?manual&scale=bad');
			const n2 = await r.pu.evaluate(async () => { await window.picker.setSize(16); return window.picker.notice(); });
			if (!r.notice.includes('scale') || n2.includes('scale') || !n2.startsWith('16 px: ')) fail('case url', 'a ?manual URL notice reached the first setSize: ' + n1 + ' | ' + r.notice + ' | ' + n2);
			await r.pu.close();
		}
		// 8: a chain the reader would refuse (a hidden Hangul face by a driver) is not written; the old hangul/latin go; scale stays
		r = await opened('?keep=1');
		q = await r.pu.evaluate(async () => { await window.picker.select({ latin: null, hangul: 'svf/dos/NGOTB14.SVF' }); const p = new URLSearchParams(location.search); return [p.has('hangul'), p.has('latin'), p.get('scale'), p.get('keep')]; });
		if (q.join() !== 'false,false,1/1,1') fail('case url', 'a hidden Hangul face reached the URL: ' + q);
		q = await r.pu.evaluate(async () => { await window.picker.select({ latin: 'svf/dos/COUSB24.SVF', hangul: 'svf/dos/MARUS24.SVF' }); return [new URLSearchParams(location.search).get('latin'), new URLSearchParams(location.search).get('hangul')]; });
		if (q.join() !== 'svf/dos/COUSB24.SVF,svf/dos/MARUS24.SVF') fail('case url', 'a Latin-only Latin face is representable: ' + q);
		await r.pu.close();
		// 9: keep and manual survive writeUrl and a reload
		r = await opened('?manual&keep=1');
		await r.pu.evaluate(async () => { await window.picker.select({ latin: null, hangul: 'svf/dos/MARUS24.SVF' }); window.picker.setScale(2, 1); });
		await r.pu.reload(); await r.pu.evaluate(() => window.picker.ready);
		q = await r.pu.evaluate(() => { const p = new URLSearchParams(location.search); return [p.has('manual'), p.get('keep'), p.get('scale'), window.picker.chain().hangul, window.picker.settings().num]; });
		if (q.join() !== 'true,1,2/1,,2') fail('case url', 'manual and keep after writeUrl and a reload: ' + q);
		await r.pu.close();
		// final fix 1: with no chain open a scale change drops a foreign hangul / latin (?manual&hangul=X then setScale)
		r = await opened('?manual&hangul=svf/dos/MARUS24.SVF&latin=svf/dos/NGOTB16.SVF&keep=1');
		q = await r.pu.evaluate(() => { window.picker.setScale(2, 1); const p = new URLSearchParams(location.search); return [p.has('hangul'), p.has('latin'), p.get('scale'), p.has('manual'), p.get('keep')]; });
		if (q.join() !== 'false,false,2/1,true,1') fail('case url', 'a ?manual hangul with no chain open survived a scale change: ' + q);
		await r.pu.close();
		// final fix 8: other parameters stay byte-exact (a malformed escape is not re-encoded)
		r = await opened('?manual&x=%E0%A4%A&keep=a+b');
		q = await r.pu.evaluate(() => { window.picker.setScale(2, 1); return location.search; });
		if (!q.includes('x=%E0%A4%A&') || !q.includes('keep=a+b') || !q.includes('scale=2%2F1')) fail('case url', 'foreign parameters were re-encoded: ' + q);
		await r.pu.close();
		// final fix 11: an empty hangul= says it is empty
		r = await opened('?hangul=');
		if (!r.notice.startsWith('URL: hangul is empty; the default opened')) fail('case url', 'empty hangul notice: ' + r.notice);
		await r.pu.close();
		// final fix 5: ?manual with nothing open: the Latin select offers nothing that must fail; a select enables them
		r = await opened('?manual');
		q = await r.pu.evaluate(async () => { const os = () => [...document.querySelectorAll('#latin option')]; const a = [os().length, os().filter(o => !o.disabled).length]; await window.picker.select({ latin: null, hangul: 'svf/dos/NGOTB16.SVF' }); return [...a, os().filter(o => o.disabled).length]; });
		if (!(q[0] > 40) || q[1] !== 0 || q[2] !== 0) fail('case url', 'Latin options with no Hangul face open / after a select: ' + q);
		await r.pu.close();
		// final fix 4: a failed select or pick from the page clears the old notice (it is not the failure's)
		for (const how of ['select', 'row']) {
			const pn = await ctx.newPage();
			pn.on('pageerror', e => errs.push(e.message));
			await pn.route('**/NGOTB16.SVF', route => route.abort());
			await pn.route('**/MARUS24.SVF', route => route.abort());
			await pn.goto(server.url + (how === 'select' ? '?scale=bad&hangul=svf/dos/PAPLG18.SVF' : '?manual&scale=bad'));
			await pn.evaluate(() => window.picker.ready); await pn.evaluate(() => window.picker.prefetching());
			const before = await pn.evaluate(() => window.picker.notice());
			if (!before.includes('scale')) fail('case url', `${how}: the test needs a notice to clear: ${before}`);
			if (how === 'select') await pn.selectOption('#hangul', U('MARUS24')); else await pn.click('#faces li:has-text("NanumGothic Bold")');
			await pn.waitForFunction(() => /fail|load|NGOTB16|MARUS24|error/i.test(document.getElementById('status').textContent));
			const after = await pn.evaluate(() => ({ n: window.picker.notice(), hidden: document.getElementById('notice').hidden }));
			if (after.n !== '' || !after.hidden) fail('case url', `${how}: the notice outlived a failed pick: ${JSON.stringify(after)}`);
			await pn.close();
		}
		// final fix 2: a select on a narrow page scrolls the list, never the window
		{
			const pw = await ctx.newPage();
			pw.on('pageerror', e => errs.push(e.message));
			await pw.setViewportSize({ width: 600, height: 700 });
			await pw.goto(server.url);
			await pw.evaluate(() => window.picker.ready); await pw.evaluate(() => window.picker.prefetching());
			await pw.evaluate(() => document.getElementById('hangul').scrollIntoView({ block: 'center' }));
			// scrolled well down; the banner above may shift the content by a line (scroll anchoring), the old scrollIntoView moved it by hundreds
			await pw.evaluate(() => window.scrollTo(0, 1200));
			const at = () => pw.evaluate(() => Math.round(window.scrollY));
			const y0 = await at();
			// a 16 px face of another family: a face of another size shrinks the 16 px list above the select (layout, not a scroll)
			await pw.selectOption('#hangul', U('NEODG16'));
			await pw.evaluate(() => window.picker.idle());
			const y1 = await at();
			if (!(y0 > 1000) || Math.abs(y1 - y0) > 100) fail('case url', `a Hangul select moved the window from ${y0} to ${y1}`);
			await pw.close();
		}
		for (const e of errs) fail('page url', e);
		if (nfailed === n0) counts.push('case url: the query sets hangul, latin and scale; absent, empty, unknown, Latin-only and subset values give the defaults or none with a notice that outlives the first prefetch; a query over 2,048 characters or a value over 256 is ignored; a pick, a select and setScale rewrite the URL and keep other parameters; a reload restores the chain; ?manual reads only the scale');
	}

	// Case export: two choices (PAPLG18 over NGOTB16 at 1/1, GBATB47 alone at 1/2) become selection.json and export.png
	// (the choices table and the export box); the table, the export box and localStorage follow the choices.
	const faceIndex = (await (await fetch(server.url + 'faces.json')).json()).faces, byKey = new Map(faceIndex.map(f => [f.key, f]));
	const wordsOf = f => (f.family + (f.style ? ' ' + f.style : '')).trim() + (f.variant ? ' · ' + f.variant : '');
	{
		const n0 = nfailed, errs = [], D = 'svf/dos/';
		const cx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
		const pe = await cx.newPage();
		pe.on('pageerror', e => errs.push(e.message));
		await pe.goto(server.url + '?manual');
		await pe.evaluate(() => window.picker.ready);
		const made = await pe.evaluate(async () => {
			const p = window.picker;
			await p.select({ latin: 'svf/dos/NGOTB16.SVF', hangul: 'svf/dos/PAPLG18.SVF' }); p.setScale(1, 1);
			const a = p.addChoice({ game: 'KQ4', id: '300', lineh: 12 });
			await p.select({ latin: null, hangul: 'svf/dos/GBATB47.SVF' }); p.setScale(1, 2);
			const b = p.addChoice({ game: 'KQ4', id: '600', lineh: 24 });
			return { a, b, text: p.exportJSON(), n: p.choices().length };
		});
		writeFileSync(join(out, 'selection.json'), made.text + '\n');
		const sel = JSON.parse(made.text);
		const fonts = sel.games?.[0]?.fonts ?? [];
		if (sel.order !== 'per-run' || sel.games?.length !== 1 || fonts.length !== 2 || made.n !== 2) fail('case export', 'shape: ' + made.text.slice(0, 300));
		for (const [f, key] of [[fonts[0], D + 'PAPLG18.SVF'], [fonts[1], D + 'GBATB47.SVF']]) {
			const x = byKey.get(key), k = f?.korean ?? {};
			if (k.key !== key || k.file !== key || k.label !== x.label || k.family !== x.family || k.style !== x.style || k.variant !== x.variant || k.bpp !== x.bpp) fail('case export', `${key}: the korean block does not carry the index fields: ` + JSON.stringify(k));
		}
		if (made.a.korean?.key !== D + 'PAPLG18.SVF' || made.a.game !== 'KQ4') fail('case export', 'addChoice returned ' + JSON.stringify(made.a));
		// the table: "Family Style · variant words", the file name in small type; the Latin cell; scale; px
		const rowsOf = () => pe.evaluate(() => [...document.querySelectorAll('#choice-rows tr')].map(tr => [...tr.children].map(td => ({ text: td.textContent, small: td.querySelector('small')?.textContent ?? null }))));
		const rows = await rowsOf();
		const x0 = byKey.get(D + 'PAPLG18.SVF'), x1 = byKey.get(D + 'GBATB47.SVF');
		const want = [[x0, 'NGOTB16.SVF', '1/1', '18 x 18'], [x1, null, '1/2', '23 x 27']];
		if (rows.length !== 2) fail('case export', 'table rows: ' + JSON.stringify(rows));
		else for (const [i, [x, lat, sc, px]] of want.entries()) {
			const c = rows[i], file = x.key.slice(x.key.lastIndexOf('/') + 1);
			if (c[0].text !== 'KQ4' || c[1].text !== ['300', '600'][i] || c[2].text !== ['12', '24'][i]
				|| c[3].small !== file || !c[3].text.startsWith(wordsOf(x)) || c[3].text.includes(x.label)
				|| (lat ? c[4].small !== lat : (c[4].text !== '(none)' || c[4].small !== null))
				|| c[5].text !== sc || c[6].text !== px) fail('case export', `row ${i}: ${JSON.stringify(c)}`);
		}
		// the export box and localStorage follow the choices (created differs per call)
		const same = await pe.evaluate(() => {
			const strip = t => { const j = JSON.parse(t); delete j.created; return JSON.stringify(j); };
			return { box: strip(document.getElementById('export').value) === strip(window.picker.exportJSON()), stored: JSON.parse(localStorage.getItem('svfpicker.choices')).length };
		});
		if (!same.box || same.stored !== 2) fail('case export', 'the export box / localStorage do not follow the choices: ' + JSON.stringify(same));
		await pe.locator('#choices').screenshot({ path: join(out, 'export.png') });
		// Download: a Blob named selection.json holding the box
		const [dl] = await Promise.all([pe.waitForEvent('download'), pe.click('#choice-download')]);
		if (dl.suggestedFilename() !== 'selection.json') fail('case export', 'download is named ' + dl.suggestedFilename());
		{ // the saved bytes are the export (created differs per call)
			const saved = readFileSync(await dl.path(), 'utf8'), now = await pe.evaluate(() => window.picker.exportJSON());
			const strip = t => { const j = JSON.parse(t); delete j.created; return JSON.stringify(j); };
			if (strip(saved) !== strip(now) || !saved.startsWith('{')) fail('case export', 'the downloaded file differs from exportJSON(): ' + saved.slice(0, 120));
		}
		await cx.close();
		for (const e of errs) fail('page export', e);
		if (nfailed === n0) counts.push('case export: two choices give selection.json (order per-run, family / style / variant beside label, scaled w h ascent), the table shows "Family Style · variant" with the file in small type, the box and localStorage follow, Download is selection.json');
	}

	// Case choices: the API limits, the datalist, stored choices (valid, unreadable in eight ways, unknown key, hidden faces)
	// and storage exceptions, the UI add / open / remove
	{
		const n0 = nfailed, errs = [], D = 'svf/dos/', UNREADABLE = 'stored choices unreadable: starting empty';
		const mk = (key, latin, sc = [1, 1], extra = {}) => { // a stored choice, built from the index as picker.js builds it
			const f = byKey.get(key), [num, den] = sc;
			return { game: 'LSL2', id: 'cs3', picked: true, korean: { key, label: f.label, family: f.family, style: f.style, variant: f.variant, file: key, latin, scale: sc,
				w: Math.ceil(f.cell[0] * num / den), h: Math.ceil(f.cell[1] * num / den), bpp: f.bpp, ascent: Math.floor((f.ascent * num + Math.floor(den / 2)) / den) }, ...extra };
		};
		const scenario = async (seed, init) => {
			const cx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
			const pg = await cx.newPage();
			pg.on('pageerror', e => errs.push(e.message));
			await pg.addInitScript(([seed, fault]) => {
				if (seed !== null) localStorage.setItem('svfpicker.choices', seed);
				const SP = Storage.prototype;
				if (fault === 'getItem') SP.getItem = () => { throw new Error('denied'); };
				if (fault === 'setItem') SP.setItem = () => { throw new DOMException('quota', 'QuotaExceededError'); };
				if (fault === 'setItem string') SP.setItem = () => { throw 'quota string'; }; // eslint-disable-line no-throw-literal
				if (fault === 'setItem null') SP.setItem = () => { throw null; }; // eslint-disable-line no-throw-literal
				if (fault === 'localStorage') Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });
			}, [seed, init ?? null]);
			await pg.goto(server.url + '?manual');
			const ready = await pg.evaluate(() => window.picker.ready.then(() => 'ok', e => String(e.message)));
			if (ready !== 'ok') fail('case choices', 'ready rejected: ' + ready);
			return { cx, pg };
		};
		const state = pg => pg.evaluate(() => ({ n: window.picker.choices().length, notice: window.picker.notice(), rows: document.querySelectorAll('#choice-rows tr').length, stored: localStorage.getItem('svfpicker.choices') }));
		const NG = D + 'NGOTB16.SVF';
		// stored: valid
		{
			const s = await scenario(JSON.stringify([mk(D + 'PAPLG18.SVF', NG)]));
			const st = await state(s.pg);
			if (st.n !== 1 || st.notice !== '' || st.rows !== 1) fail('case choices', 'a valid stored choice: ' + JSON.stringify(st));
			await s.cx.close();
		}
		// stored: unreadable in eight ways; each gives the notice and an empty list, and the next save overwrites it
		const ok = mk(D + 'PAPLG18.SVF', NG);
		const bad = {
			'not JSON': '{', 'an object': '{"a":1}', 'a string': '"x"', 'a non-object entry': '[1]', 'no korean block': '[{"game":"a","id":"b"}]',
			'257 choices': JSON.stringify(Array.from({ length: 257 }, () => ok)),
			'a 257-character string': JSON.stringify([{ ...ok, game: 'g'.repeat(257) }]),
			'an infinite number': JSON.stringify([ok]).replace('"picked":true', '"picked":true,"lineh":1e999'),
		};
		// makeChoice's rules on a stored record, one rule each (a record that fails is dropped; none left = unreadable)
		const withK = o => ({ ...ok, korean: { ...ok.korean, ...o } });
		const rules = {
			'a blank game': { ...ok, game: '  ' }, 'an empty id': { ...ok, id: '' }, 'lineh 0': { ...ok, lineh: 0 }, 'lineh 1.5': { ...ok, lineh: 1.5 },
			'lineh -3': { ...ok, lineh: -3 }, 'lineh 65536': { ...ok, lineh: 65536 }, 'lineh as a string': { ...ok, lineh: '12' }, 'lineh null': { ...ok, lineh: null },
			'picked false': { ...ok, picked: false }, 'picked missing': (({ picked, ...r }) => r)(ok),
			'file differs from key': withK({ file: D + 'NGOTB16.SVF' }), 'file missing': withK({ file: undefined }), 'an empty key': withK({ key: '', file: '' }),
			'label a number': withK({ label: 5 }), 'family a number': withK({ family: 5 }), 'style missing': withK({ style: undefined }), 'variant null': withK({ variant: null }),
			'latin a number': withK({ latin: 5 }), 'latin missing': withK({ latin: undefined }), 'scale 0/1': withK({ scale: [0, 1] }), 'scale 1.5/1': withK({ scale: [1.5, 1] }), 'scale 17/1': withK({ scale: [17, 1] }),
			'scale of three': withK({ scale: [1, 1, 1] }), 'w as a string': withK({ w: '18' }), 'w missing': withK({ w: undefined }),
			// control characters (a line break would start a new line in a map written from the export)
			'a line break in game': { ...ok, game: 'KQ4\n[section]' }, 'a tab in id': { ...ok, id: 'a\tb' }, 'U+2028 in id': { ...ok, id: 'a\u2028b' }, 'U+2029 in game': { ...ok, game: 'a\u2029b' },
			'NEL in id': { ...ok, id: 'a\u0085[fonts]\u0085b' }, 'C1 in game': { ...ok, game: 'a\u009fb' }, 'a bar in game': { ...ok, game: 'A|B' }, 'a bar in id': { ...ok, id: 'cs|3' }, 'NEL in label': withK({ label: 'L\u0085[fonts]\u0085evil=X.SVF' }), 'C1 in key': withK({ key: D + 'P\u0085X.SVF', file: D + 'P\u0085X.SVF' }),
			'a line break in label': withK({ label: 'x\n[font]\nkey=value' }), 'NUL in family': withK({ family: 'a\u0000b' }), 'DEL in style': withK({ style: 'a\u007fb' }),
			'a line break in variant': withK({ variant: 'a\nb' }), 'a line break in key': withK({ key: D + 'P\nX.SVF', file: D + 'P\nX.SVF' }), 'a line break in latin': withK({ latin: D + 'N\nX.SVF' }),
		};
		for (const [name, rec] of Object.entries(rules)) bad[name] = JSON.stringify([rec]);
		for (const [name, seed] of Object.entries(bad)) {
			const s = await scenario(seed);
			const st = await state(s.pg);
			if (st.n !== 0 || st.notice !== UNREADABLE || st.rows !== 0) fail('case choices', `${name}: ` + JSON.stringify(st));
			await s.pg.evaluate(async k => { await window.picker.select({ latin: null, hangul: k }); window.picker.addChoice({ game: 'G', id: '1' }); }, NG);
			const after = JSON.parse(await s.pg.evaluate(() => localStorage.getItem('svfpicker.choices')));
			if (after.length !== 1 || after[0].game !== 'G') fail('case choices', `${name}: the next save did not overwrite: ` + JSON.stringify(after).slice(0, 200));
			await s.cx.close();
		}
		// a stored game / id is trimmed the way makeChoice trims it
		{
			const s = await scenario(JSON.stringify([{ ...ok, game: '  KQ4 ', id: ' cs3  ' }]));
			const got = await s.pg.evaluate(() => window.picker.choices().map(c => [c.game, c.id]));
			if (JSON.stringify(got) !== '[["KQ4","cs3"]]') fail('case choices', 'a stored game / id was not trimmed: ' + JSON.stringify(got));
			await s.cx.close();
		}
		// a bad record among good ones is dropped and counted; the good ones stay in order
		{
			const s = await scenario(JSON.stringify([{ ...ok, id: 'one' }, { ...ok, id: 'two', lineh: 0 }, { ...ok, id: 'three', game: 'a\nb' }, { ...ok, id: 'four' }]));
			const st = await state(s.pg), ids = await s.pg.evaluate(() => window.picker.choices().map(c => c.id));
			if (ids.join() !== 'one,four' || st.rows !== 2 || st.notice !== '2 stored choices skipped: not valid') fail('case choices', 'a mixed stored list: ' + JSON.stringify({ ids, notice: st.notice, rows: st.rows }));
			await s.cx.close();
			const s1 = await scenario(JSON.stringify([{ ...ok, id: 'one' }, { ...ok, id: 'two', lineh: 0 }]));
			const n1 = (await state(s1.pg)).notice;
			if (n1 !== '1 stored choice skipped: not valid') fail('case choices', 'one skipped: ' + n1);
			await s1.cx.close();
		}
		// a game and id are one choice: the loader keeps the first of a repeat and says so; addChoice refuses a repeat (after trimming)
		{
			const s = await scenario(JSON.stringify([{ ...ok, id: 'one' }, { ...ok, id: 'two' }, { ...ok, id: ' one ' }, { ...ok, id: 'one', lineh: 9 }]));
			const st = await state(s.pg), got = await s.pg.evaluate(() => window.picker.choices().map(c => [c.id, c.lineh ?? null]));
			if (JSON.stringify(got) !== '[["one",null],["two",null]]' || st.rows !== 2 || st.notice !== '2 stored choices skipped: same game and id as an earlier one') fail('case choices', 'repeats in a stored list: ' + JSON.stringify({ got, notice: st.notice, rows: st.rows }));
			await s.cx.close();
		}
		// add -> reload round trip: the stored choices come back equal
		{
			const s = await scenario(null);
			const before = await s.pg.evaluate(async k => { await window.picker.select({ latin: null, hangul: k }); window.picker.setScale(3, 2); window.picker.addChoice({ game: 'KQ4', id: '300', lineh: 12 }); window.picker.addChoice({ game: 'KQ4', id: '600' }); return window.picker.choices(); }, NG);
			await s.pg.reload(); await s.pg.evaluate(() => window.picker.ready);
			const after = await s.pg.evaluate(() => window.picker.choices());
			if (before.length !== 2 || JSON.stringify(after) !== JSON.stringify(before)) fail('case choices', 'add -> reload: ' + JSON.stringify({ before, after }).slice(0, 300));
			await s.cx.close();
		}
		// exactly 256 choices of 256-character strings are accepted
		{
			const edge = Array.from({ length: 256 }, (_, i) => ({ ...ok, id: String(i).padStart(256, 'i') }));
			const s = await scenario(JSON.stringify(edge));
			const st = await state(s.pg);
			if (st.n !== 256 || st.notice !== '') fail('case choices', 'the limits themselves are valid: ' + JSON.stringify({ ...st, stored: null }));
			const thrown = await s.pg.evaluate(async k => { await window.picker.select({ latin: null, hangul: k }); try { window.picker.addChoice({ game: 'G', id: '1' }); return null; } catch (e) { return e.message; } }, NG);
			if (!/256/.test(thrown ?? '')) fail('case choices', 'a 257th choice was not refused with the limit: ' + thrown);
			await s.cx.close();
		}
		// stored: an unknown key is kept, marked, not openable, and exported
		{
			const unknown = mk(D + 'PAPLG18.SVF', NG, [2, 1]); unknown.korean.key = unknown.korean.file = 'svf/dos/NOPE99.SVF';
			const s = await scenario(JSON.stringify([unknown, { ...unknown, korean: { ...unknown.korean, key: 'svf/dos/NOPE98.SVF', file: 'svf/dos/NOPE98.SVF', extra: { deep: [1, 'two'] } }, note: 'kept', id: 'cs4' }]));
			const st = await state(s.pg);
			const row = await s.pg.evaluate(() => ({ text: document.querySelector('#choice-rows tr')?.textContent, open: document.querySelector('#choice-rows tr button[data-act=open]')?.disabled }));
			const exp = await s.pg.evaluate(() => window.picker.exportJSON());
			if (st.n !== 2 || st.notice !== '' || !row.text?.includes('not in this index') || row.open !== true || !exp.includes('NOPE99') || !/"note": "kept"/.test(exp)) fail('case choices', 'unknown key: ' + JSON.stringify({ st: { ...st, stored: null }, row, exp: exp.slice(0, 200) }));
			await s.cx.close();
		}
		// stored: hidden faces. A subset face as the Hangul face, a Latin-only face as the Latin face: they open through select's rules
		{
			const subset = faceIndex.find(f => f.subset && !f.latin_only), lonly = faceIndex.find(f => f.latin_only);
			if (!subset || !lonly) fail('case choices', 'the index has no subset or Latin-only face');
			else {
				const s = await scenario(JSON.stringify([mk(subset.key, null, [1, 1]), mk(NG, lonly.key, [3, 2], { id: 'cs4' })]));
				for (const [i, want] of [[0, { h: subset.key, l: null, num: 1 }], [1, { h: NG, l: lonly.key, num: 3 }]]) {
					await s.pg.locator('#choice-rows tr').nth(i).locator('button[data-act=open]').click();
					await s.pg.waitForFunction(h => window.picker.chain().hangul === h, want.h);
					await s.pg.evaluate(() => window.picker.idle());
					const o = await s.pg.evaluate(() => ({ c: window.picker.chain(), v: window.picker.view(), num: window.picker.settings().num, status: document.querySelector('#status .err')?.textContent ?? null, lat: document.getElementById('latin').value, han: document.getElementById('hangul').value }));
					if (o.c.hangul !== want.h || o.c.latin !== want.l || o.num !== want.num || o.status || o.han !== want.h || o.lat !== (want.l ?? '')) fail('case choices', `hidden-face choice ${i} did not open: ` + JSON.stringify(o));
					if (i === 0 && o.v.listed !== false) fail('case choices', 'a subset Hangul face is on the list: ' + JSON.stringify(o.v));
				}
				await s.cx.close();
			}
		}
		// storage exceptions: a notice, never a page error
		for (const [name, init] of [['getItem throws', 'getItem'], ['setItem throws', 'setItem'], ['setItem throws a string', 'setItem string'], ['setItem throws null', 'setItem null'], ['localStorage throws', 'localStorage']]) {
			const s = await scenario(null, init);
			const st0 = await s.pg.evaluate(() => window.picker.notice());
			const got = await s.pg.evaluate(async k => { await window.picker.select({ latin: null, hangul: k }); const c = window.picker.addChoice({ game: 'G', id: '1' }); return { c: !!c, n: window.picker.choices().length, notice: window.picker.notice() }; }, NG);
			const loadFails = name === 'getItem throws' || name === 'localStorage throws';
			if (loadFails ? st0 !== UNREADABLE : st0 !== '') fail('case choices', `${name}: the load notice is "${st0}"`);
			const tail = { 'setItem throws': 'quota', 'setItem throws a string': 'quota string', 'setItem throws null': 'null' }[name];
			if (!got.c || got.n !== 1 || !got.notice.startsWith(name === 'getItem throws' ? UNREADABLE : 'choices not saved: ') || (tail && !got.notice.includes(tail))) fail('case choices', `${name}: ${JSON.stringify(got)}`);
			await s.cx.close();
		}
		// the API: limits and errors
		{
			const s = await scenario(null);
			const t = await s.pg.evaluate(async k => {
				const p = window.picker, err = f => { try { f(); return null; } catch (e) { return String(e.message); } };
				const r = { nochain: err(() => p.addChoice({ game: 'G', id: '1' })) };
				await p.select({ latin: null, hangul: k });
				r.nogame = err(() => p.addChoice({ game: '', id: '1' })); r.noid = err(() => p.addChoice({ game: 'G', id: '' }));
				r.longgame = err(() => p.addChoice({ game: 'g'.repeat(257), id: '1' }));
				for (const v of [0, -1, 1.5, NaN, Infinity, '12']) r['lineh ' + String(v)] = err(() => p.addChoice({ game: 'G', id: '1', lineh: v }));
				for (const [name, v] of [['line break', 'a\n[section]\nkey=value'], ['tab', 'a\tb'], ['NUL', 'a\u0000b'], ['DEL', 'a\u007fb'], ['U+2028', 'a\u2028b'], ['U+2029', 'a\u2029b'], ['CR', 'a\rb'], ['C1 NEL', 'a\u0085b'], ['C1 0x80', 'a\u0080b'], ['C1 0x9f', 'a\u009fb']]) {
					r['game ' + name] = err(() => p.addChoice({ game: v, id: '1' })); r['id ' + name] = err(() => p.addChoice({ game: 'G', id: v }));
				}
				r.bargame = err(() => p.addChoice({ game: 'A|B', id: '1' })); r.barid = err(() => p.addChoice({ game: 'G', id: 'a|b' }));
				p.addChoice({ game: 'R', id: 'x' }); r.dup = err(() => p.addChoice({ game: ' R ', id: 'x ' })); r.dupn = p.choices().length; p.removeChoice(0);
				r.none = p.addChoice({ game: 'G', id: '1', lineh: null }); r.undef = p.addChoice({ game: 'G', id: '2' });
				r.keys = [p.choices()[0], p.choices()[1]].map(c => 'lineh' in c);
				for (const v of [-1, 2, 1.5, '0']) r['rm ' + String(v)] = err(() => p.removeChoice(v));
				r.copy = (() => { const c = p.choices(); c[0].game = 'changed'; c.pop(); return [p.choices().length, p.choices()[0].game]; })();
				p.removeChoice(0);
				r.left = p.choices().map(c => c.id);
				return r;
			}, NG);
			const ctl = Object.keys(t).filter(k => /^(game|id) /.test(k));
			if (ctl.length !== 20 || ctl.some(k => !/control character/.test(t[k] ?? ''))) fail('case choices', 'control characters in game / id: ' + JSON.stringify(ctl.map(k => [k, t[k]])));
			if (!/'\|'/.test(t.bargame ?? '') || !/'\|'/.test(t.barid ?? '') || t.left.join() !== '2') fail('case choices', "game / id with '|' (the export refuses it): " + JSON.stringify([t.bargame, t.barid]));
			if (!/already/.test(t.dup ?? '') || t.dupn !== 1) fail('case choices', 'a repeated game and id: ' + JSON.stringify([t.dup, t.dupn]));
			const need = ['nochain', 'nogame', 'noid', 'longgame', 'lineh 0', 'lineh -1', 'lineh 1.5', 'lineh NaN', 'lineh Infinity', 'lineh 12', 'rm -1', 'rm 2', 'rm 1.5', 'rm 0'];
			const missing = need.filter(k => !t[k]);
			if (missing.length) fail('case choices', 'no error for: ' + missing.join(', '));
			if (!/face/i.test(t.nochain ?? '')) fail('case choices', 'addChoice with no chain said: ' + t.nochain);
			if (t.keys.join() !== 'false,false' || t.copy.join() !== '2,G' || t.left.join() !== '2') fail('case choices', 'lineh omission / copies / removal: ' + JSON.stringify(t));
			await s.cx.close();
		}
		// w, h are ceil(cell * num / den) and ascent rounds half up, over a ratio that is not exact for this face (so ceil and floor differ)
		{
			const s = await scenario(null), RATIOS = [[3, 2], [1, 2], [2, 3], [3, 4], [5, 3], [7, 4], [1, 3], [5, 2]];
			// a face and ratio where ceil differs from floor in w and h, and the ascent is an exact half (rounds up)
			let f, n, d;
			for (const g of faceIndex) {
				if (g.subset || g.latin_only) continue;
				const r = RATIOS.find(([n, d]) => (g.cell[0] * n) % d && (g.cell[1] * n) % d && (g.ascent * n * 2) % (2 * d) === d);
				if (r) { f = g; [n, d] = r; break; }
			}
			if (!n) fail('case choices', 'no face has a ratio that is inexact in w, h and an exact half in the ascent');
			else {
				const k = (await s.pg.evaluate(async ([key, n, d]) => { await window.picker.select({ latin: null, hangul: key }); window.picker.setScale(n, d); return window.picker.addChoice({ game: 'G', id: '1' }); }, [f.key, n, d])).korean;
				const want = [Math.ceil(f.cell[0] * n / d), Math.ceil(f.cell[1] * n / d), Math.floor((f.ascent * n + Math.floor(d / 2)) / d)];
				if ([k.w, k.h, k.ascent].join() !== want.join() || want[0] === Math.floor(f.cell[0] * n / d)) fail('case choices', `${n}/${d}: w h ascent ${[k.w, k.h, k.ascent]}, expected ${want}`);
			}
			await s.cx.close();
		}
		// the index's own text goes into the export too: a label / family / style / variant with a control character refuses the choice
		for (const field of ['label', 'family', 'style', 'variant']) {
			const cx = await browser.newContext({ viewport: { width: 1440, height: 900 } }), pg = await cx.newPage();
			pg.on('pageerror', e => errs.push(e.message));
			await pg.route('**/faces.json', async route => { const j = await (await route.fetch()).json(); j.faces.find(f => f.key === 'svf/dos/PAPLG18.SVF')[field] = 'x\n[font]\nkey=value'; await route.fulfill({ json: j }); });
			await pg.goto(server.url + '?manual');
			await pg.evaluate(() => window.picker.ready);
			const r = await pg.evaluate(async () => {
				await window.picker.select({ latin: null, hangul: 'svf/dos/PAPLG18.SVF' });
				try { window.picker.addChoice({ game: 'G', id: '1' }); return { err: null }; } catch (e) { return { err: e.message, n: window.picker.choices().length }; }
			});
			if (!/control character/.test(r.err ?? '') || r.n !== 0 || !(r.err ?? '').includes(field)) fail('case choices', `a control character in the index's ${field}: ` + JSON.stringify(r));
			await cx.close();
		}
		// export order: games by first appearance, fonts in insertion order (three choices across two games, interleaved)
		{
			const s = await scenario(null);
			const g = await s.pg.evaluate(async k => {
				await window.picker.select({ latin: null, hangul: k });
				for (const [game, id] of [['QFG2', 'a1'], ['KQ4', 'b1'], ['QFG2', 'a2'], ['KQ4', 'b2']]) window.picker.addChoice({ game, id });
				return JSON.parse(window.picker.exportJSON()).games.map(x => [x.game, x.fonts.map(f => f.id)]);
			}, NG);
			if (JSON.stringify(g) !== '[["QFG2",["a1","a2"]],["KQ4",["b1","b2"]]]') fail('case choices', 'export order: ' + JSON.stringify(g));
			await s.cx.close();
		}
		// Open whose select fails leaves the scale as it was; Open of a good choice sets it
		{
			const cx = await browser.newContext({ viewport: { width: 1440, height: 900 } }), pg = await cx.newPage();
			pg.on('pageerror', e => errs.push(e.message));
			await pg.addInitScript(seed => localStorage.setItem('svfpicker.choices', seed), JSON.stringify([mk(D + 'MARUS24.SVF', null, [3, 1])]));
			await pg.route('**/faces/dos/MARUS24.SVF', route => route.fulfill({ status: 500, contentType: 'text/plain', body: 'no' }));
			await pg.goto(server.url + '?manual');
			await pg.evaluate(() => window.picker.ready);
			await pg.evaluate(async k => { await window.picker.select({ latin: null, hangul: k }); window.picker.setScale(2, 3); }, NG);
			await pg.click('#choice-rows tr button[data-act=open]');
			await pg.waitForSelector('#status .err');
			const o = await pg.evaluate(() => ({ s: window.picker.settings(), c: window.picker.chain(), num: document.getElementById('num').value, den: document.getElementById('den').value, q: location.search }));
			if (o.s.num !== 2 || o.s.den !== 3 || o.c.hangul !== NG || o.num !== '2' || o.den !== '3' || !o.q.includes('scale=2%2F3')) fail('case choices', 'a failed Open changed the scale: ' + JSON.stringify(o));
			await cx.close();
		}
		// Copy: the clipboard holds the export box; with the clipboard refused, the box is selected and the status says so
		{
			const cx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
			await cx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: new URL(server.url).origin });
			const pg = await cx.newPage();
			pg.on('pageerror', e => errs.push(e.message));
			await pg.goto(server.url + '?manual');
			await pg.evaluate(() => window.picker.ready);
			await pg.evaluate(async k => { await window.picker.select({ latin: null, hangul: k }); window.picker.addChoice({ game: 'G', id: '1' }); }, NG);
			await pg.click('#choice-copy');
			await pg.waitForFunction(() => /export copied/.test(document.getElementById('status').textContent));
			const c = await pg.evaluate(async () => ({ clip: await navigator.clipboard.readText(), box: document.getElementById('export').value }));
			if (!c.box.includes('"game": "G"') || c.clip !== c.box) fail('case choices', 'Copy: the clipboard is not the export box: ' + JSON.stringify({ clip: c.clip.slice(0, 80), box: c.box.slice(0, 80) }));
			await pg.evaluate(() => { navigator.clipboard.writeText = () => Promise.reject(new Error('denied')); });
			await pg.click('#choice-copy');
			await pg.waitForSelector('#status .err');
			const f = await pg.evaluate(() => { const t = document.getElementById('export'); return { sel: [t.selectionStart, t.selectionEnd, t.value.length], focus: document.activeElement === t, status: document.querySelector('#status .err').textContent }; });
			if (f.sel[0] !== 0 || f.sel[1] !== f.sel[2] || !f.focus || !/Ctrl\+C/.test(f.status)) fail('case choices', 'Copy with the clipboard refused: ' + JSON.stringify(f));
			await cx.close();
		}
		// Remove the middle one of three: the others keep their order in the table, the export and storage
		{
			const s = await scenario(null), pg = s.pg;
			await pg.evaluate(async k => { await window.picker.select({ latin: null, hangul: k }); for (const id of ['a', 'b', 'c']) window.picker.addChoice({ game: 'G', id }); }, NG);
			await pg.locator('#choice-rows tr').nth(1).locator('button[data-act=remove]').click();
			const r = await pg.evaluate(() => ({ cs: window.picker.choices().map(c => c.id), rows: [...document.querySelectorAll('#choice-rows tr')].map(tr => tr.children[1].textContent),
				exp: JSON.parse(window.picker.exportJSON()).games[0].fonts.map(f => f.id), stored: JSON.parse(localStorage.getItem('svfpicker.choices')).map(c => c.id) }));
			if ([r.cs, r.rows, r.exp, r.stored].some(x => x.join() !== 'a,c')) fail('case choices', 'removing the middle choice: ' + JSON.stringify(r));
			await s.cx.close();
		}
		// the datalist is the GAMES list of picker.js (read from the source file)
		{
			const src = readFileSync(join(here, '..', 'picker.js'), 'utf8');
			const block = src.slice(src.indexOf('const GAMES = ['), src.indexOf('];', src.indexOf('const GAMES = [')));
			const names = [...block.matchAll(/'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"/g)].map(m => m[1] ?? m[2]);
			const s = await scenario(null);
			const got = await s.pg.evaluate(() => [...document.querySelectorAll('#choice-games option')].map(o => o.value));
			if (names.length < 20 || JSON.stringify(got) !== JSON.stringify(names) || (await s.pg.getAttribute('#choice-game', 'list')) !== 'choice-games') fail('case choices', `the datalist is not GAMES (${got.length} of ${names.length})`);
			await s.cx.close();
		}
		// the UI: add (line height empty), open restores chain and scale, remove empties storage
		{
			const s = await scenario(null), pg = s.pg;
			await pg.fill('#choice-game', 'LSL2'); await pg.fill('#choice-id', 'cs3'); // the form's own required fields are filled: the picker itself must refuse
			await pg.click('#choice-add');
			const none = await state(pg);
			const refusal = await pg.evaluate(() => document.querySelector('#status .err')?.textContent ?? null);
			if (none.n !== 0 || none.rows !== 0 || refusal !== 'addChoice: no face is open (pick a face first)' || none.stored !== null) fail('case choices', 'Add with no face open: ' + JSON.stringify({ ...none, refusal }));
			await pg.evaluate(async k => { await window.picker.select({ latin: k, hangul: 'svf/dos/MARUS24.SVF' }); window.picker.setScale(2, 1); }, NG);
			await pg.fill('#choice-game', 'LSL2'); await pg.fill('#choice-id', 'cs3'); await pg.fill('#choice-lineh', '');
			await pg.click('#choice-add');
			const one = await pg.evaluate(() => ({ cs: window.picker.choices(), rows: document.querySelectorAll('#choice-rows tr').length, status: document.querySelector('#status .err')?.textContent ?? null }));
			if (one.cs.length !== 1 || 'lineh' in one.cs[0] || one.rows !== 1 || one.status || one.cs[0].korean.scale.join() !== '2,1' || one.cs[0].korean.latin !== NG) fail('case choices', 'UI add: ' + JSON.stringify(one));
			await pg.evaluate(async () => { await window.picker.select({ latin: null, hangul: 'svf/dos/NGOTB16.SVF' }); window.picker.setScale(1, 1); });
			await pg.click('#choice-rows tr button[data-act=open]');
			await pg.waitForFunction(h => window.picker.chain().hangul === h, D + 'MARUS24.SVF');
			await pg.evaluate(() => window.picker.idle());
			const back = await pg.evaluate(() => ({ c: window.picker.chain(), s: window.picker.settings() }));
			if (back.c.hangul !== D + 'MARUS24.SVF' || back.c.latin !== NG || back.s.num !== 2 || back.s.den !== 1) fail('case choices', 'Open did not restore the chain and scale: ' + JSON.stringify(back));
			await pg.click('#choice-rows tr button[data-act=remove]');
			const gone = await state(pg);
			if (gone.n !== 0 || gone.rows !== 0 || gone.stored !== '[]') fail('case choices', 'Remove: ' + JSON.stringify(gone));
			await s.cx.close();
		}
		for (const e of errs) fail('page choices', e);
		if (nfailed === n0) counts.push('case choices: API limits, the datalist equals GAMES, stored choices validated (eight unreadable shapes give the notice and are overwritten, the limits themselves pass), an unknown key is kept and marked, hidden faces open, storage exceptions are notices, UI add / open / remove');
	}

	// Case server and cancel: serve.mjs records a HEAD as completed; an error response of faces.json or a licence has its body cancelled
	{
		const n0 = nfailed, errs = [], P = '/faces/dos/MARUS24.SVF';
		const srvH = await startServer(dist, { chunked: [P] });
		try {
			const h = await fetch(srvH.url + P.slice(1), { method: 'HEAD' });
			await h.arrayBuffer();
			const st = await until(() => srvH.stats()[P]?.completed ? srvH.stats()[P] : null, 2000);
			if (!st || st.closed !== false || st.error !== undefined || st.written !== 0) fail('case server and cancel', 'a HEAD should be completed: ' + JSON.stringify(srvH.stats()[P]));
		} finally { await srvH.close(); }
		const spy = () => { window.__cancels = 0; const c0 = ReadableStream.prototype.cancel; ReadableStream.prototype.cancel = function (...a) { window.__cancels++; return c0.apply(this, a); }; };
		const pc = await ctx.newPage();
		pc.on('pageerror', e => errs.push(e.message));
		await pc.addInitScript(spy);
		await pc.route('**/licences/**', route => route.fulfill({ status: 404, contentType: 'text/plain', body: 'x'.repeat(5000) }));
		await pc.goto(server.url + '?manual');
		await pc.evaluate(() => window.picker.ready);
		const lic = await pc.evaluate(async () => { const f = window.picker.faces()[0]; const t = await window.picker.licence(f.licences[0]); return { t, c: window.__cancels }; });
		if (!lic.t.includes('HTTP 404') || lic.c < 1) fail('case server and cancel', 'licence !ok body not cancelled: ' + JSON.stringify(lic));
		await pc.close();
		const pf = await ctx.newPage();
		await pf.addInitScript(spy);
		await pf.route('**/faces.json', route => route.fulfill({ status: 500, contentType: 'text/plain', body: 'x'.repeat(5000) }));
		await pf.goto(server.url + '?manual');
		const idx = await pf.evaluate(() => window.picker.ready.then(() => 'loaded', e => ({ m: String(e.message), c: window.__cancels })));
		if (!idx.m?.includes('HTTP 500') || idx.c < 1) fail('case server and cancel', 'faces.json !ok body not cancelled: ' + JSON.stringify(idx));
		await pf.close();
		for (const e of errs) fail('page server and cancel', e);
		if (nfailed === n0) counts.push('case server and cancel: a HEAD is completed in the server stats, the body of an error answer of a licence and of faces.json is cancelled');
	}
	writeFileSync(join(out, 'cases.txt'), counts.join('\n') + '\n');
	process.stdout.write(counts.join('\n') + '\n');
} catch (err) {
	fail('harness', String(err.stack ?? err));
} finally {
	await browser.close();
	await server.close();
}
if (failed) { process.stderr.write(`check.mjs: ${failed}\n`); process.exit(1); }
process.stdout.write('check.mjs: ok\n');
