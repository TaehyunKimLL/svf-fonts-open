'use strict';
// Screenshots for docs/desktop-app(.ko).md and docs/maker-desktop(.ko).md: runs the real main.js (development sidecar,
// stubbed file dialogs, a fresh userData) under xvfb, drives the page through three jobs and writes one PNG per state
// into docs/images/maker/ (SHOT_DIR overrides). Inputs are synthetic or OFL only: the sample set of
// maker/test/uisample.py (the desktop e2e's), plus SVF faces from svf/, the synthetic DOS raw font of
// maker/test/fixtures.py and the synthetic 86Box ROM pair of maker/test/test_recipe.py (drawn from NEODG16.SVF; the
// sidecar is started with the recipe library patched to its hashes, as that test does in-process).
//
//   bash desktop/test/run-doc-shots.sh          (= xvfb-run ... electron --no-sandbox --disable-gpu test/doc-shots.js)
//
// The page has no language switch (its labels are English), so every shot is of the one UI. Paths, job ids and step
// seconds are masked in the page before each capture, so a re-run gives the same pictures. Prints "SHOT <name> WxH"
// per picture and "SHOTS DONE <n> files, <bytes> bytes"; exits 1 when a required shot fails.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFile } = require('node:child_process');
const execFileAsync = require('node:util').promisify(execFile);
global.SVF_MAKER_EMBEDDED = true;                       // main.js must not auto-start: this script calls start()
const electron = require('electron');
const { app, Menu, desktopCapturer } = electron;

const REPO = path.join(__dirname, '..', '..');
// the run's scratch is a sub-folder: TMP_DIR itself is also TMPDIR, where xvfb-run keeps its X authority file
const TMP = path.join(process.env.TMP_DIR || path.join(os.homedir(), 'work', 'tmp', 'svf-doc-shots'), 'run');
const OUT = process.env.SHOT_DIR || path.join(REPO, 'docs', 'images', 'maker');
const PY = process.env.SVF_E2E_PYTHON || 'python3';
const W = 1200, H = 800;                                 // the window's content size (the app's default window size)
const MASK = { tmp: '/home/user/svf-shots', repo: '/home/user/svf-fonts' };

app.commandLine.appendSwitch('force-device-scale-factor', '1');
app.commandLine.appendSwitch('no-sandbox');
app.disableHardwareAcceleration();
fs.rmSync(TMP, { recursive: true, force: true });
fs.mkdirSync(path.join(TMP, 'base'), { recursive: true });
app.setPath('userData', path.join(TMP, 'base'));         // Chromium's own profile: fresh as well

const dialogQueue = [];
const realMessageBox = electron.dialog.showMessageBox;
let messageBox = async () => ({ response: 0 });
electron.dialog.showOpenDialog = async () => dialogQueue.shift() || { canceled: true, filePaths: [] };
electron.dialog.showMessageBox = (...a) => messageBox(...a);
electron.shell.showItemInFolder = () => {};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PRELUDE = `const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const waitFor = async (fn, ms = 60000) => { const end = Date.now() + ms; for (;;) { const v = await fn(); if (v) return v;
    if (Date.now() > end) throw new Error('page timeout: ' + fn); await sleep(100); } };
  const visible = (el) => !!el && !el.hidden && el.getClientRects().length > 0;
  const $ = (id) => document.getElementById(id);
  const choose = (ctl, value) => {
    if (!ctl) throw new Error('no control for ' + JSON.stringify(value));
    if (ctl.tagName === 'SELECT') {
      const opt = [...ctl.options].find((o) => o.value === value);
      if (!opt) throw new Error('no option ' + JSON.stringify(value) + ' in ' + (ctl.getAttribute('aria-label') || ctl.id));
      ctl.value = value;
    } else if (ctl.type === 'checkbox') ctl.checked = !!value; else ctl.value = value;
    ctl.dispatchEvent(new Event('input', { bubbles: true })); ctl.dispatchEvent(new Event('change', { bubbles: true })); };
  const getJob = async () => (await fetch('/api/jobs/' + new URLSearchParams(location.search).get('job'))).json();
  const rowOf = (fid) => document.querySelector('#fonts tr[data-font="' + fid + '"]');
  const ovOf = (fid) => document.querySelector('#fonts tr.override[data-for="' + fid + '"]');
  const stepRow = (name) => [...document.querySelectorAll('#steps tbody tr')].find((tr) => tr.children[5] && tr.children[5].textContent === name);
  const mark = (el) => { if (el) { el.dataset.shotMark = '1'; el.style.outline = '3px solid #d33'; el.style.outlineOffset = '2px'; } };
  const unmark = () => { for (const el of document.querySelectorAll('[data-shot-mark]')) { el.style.outline = ''; el.style.outlineOffset = ''; delete el.dataset.shotMark; } };`;
let handle;
const run = (js) => handle.win.webContents.executeJavaScript('(async () => {' + PRELUDE + js + '})()', true);
const results = { shots: [], failed: [] };
const jobIds = [];

// Replace what differs between runs or hosts (the scratch and checkout paths, the job ids, the step seconds) in the
// page's text and form values; a poll may redraw a row afterwards, so the capture follows at once.
async function mask() {
  const real = (p) => { try { return fs.realpathSync(p); } catch (e) { return p; } };
  const pairs = [[real(TMP), MASK.tmp], [TMP, MASK.tmp], [real(REPO), MASK.repo], [path.resolve(REPO), MASK.repo]];
  jobIds.forEach((id, i) => pairs.push([id, '0000000000a' + (i + 1)]));
  await run(`const pairs = ${JSON.stringify(pairs)};
    const fix = (s) => { for (const [a, b] of pairs) s = s.split(a).join(b); return s; };
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) { const v = fix(n.nodeValue); if (v !== n.nodeValue) n.nodeValue = v; }
    for (const el of document.querySelectorAll('input, textarea')) { const v = fix(el.value); if (v !== el.value) el.value = v;
      if (el.placeholder) el.placeholder = fix(el.placeholder); }
    for (const td of document.querySelectorAll('#steps td.nums')) if (/^\\d+\\.\\d s$/.test(td.textContent)) td.textContent = '·.· s';
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));`);
}

// One picture: the whole viewport, or the union of the boxes of `sel` (CSS selectors, or a page expression returning
// elements) scrolled below the sticky top bar, with `pad` pixels around it.
async function shot(name, opts = {}) {
  try {
    await sleep(opts.wait === undefined ? 600 : opts.wait);
    let rect;
    if (opts.sel || opts.expr) {
      rect = await run(`const els = (${opts.expr || 'null'}) || [...document.querySelectorAll(${JSON.stringify(opts.sel || '')})];
        const list = (Array.isArray(els) ? els : [els]).filter((e) => e && e.getClientRects().length);
        if (!list.length) throw new Error('nothing to capture');
        ${opts.noScroll ? '' : `list[0].scrollIntoView({ block: 'start' });
        const bar = document.querySelector('header.top').getBoundingClientRect().height;
        window.scrollBy(0, -(bar + ${opts.pad === undefined ? 8 : opts.pad} + ${opts.above || 0}));`}
        await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
        let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
        for (const e of list) { const b = e.getBoundingClientRect(); x0 = Math.min(x0, b.left); y0 = Math.min(y0, b.top); x1 = Math.max(x1, b.right); y1 = Math.max(y1, b.bottom); }
        const p = ${opts.pad === undefined ? 8 : opts.pad};
        ${opts.fromTop ? 'y0 = 0;' : ''}
        ${opts.fullWidth ? 'x0 = 0; x1 = innerWidth;' : ''}
        x0 = Math.max(0, Math.floor(x0 - p)); y0 = Math.max(0, Math.floor(y0 - p));
        x1 = Math.min(innerWidth, Math.ceil(x1 + p)); y1 = Math.min(innerHeight, Math.ceil(y1 + p));
        return { x: x0, y: y0, width: x1 - x0, height: y1 - y0 };`);
    }
    await mask();
    const img = await handle.win.webContents.capturePage(rect);
    fs.writeFileSync(path.join(OUT, name + '.png'), img.toPNG());
    const s = img.getSize();
    results.shots.push(name);
    console.log('SHOT ' + name + ' ' + s.width + 'x' + s.height);
  } catch (e) {
    results.failed.push(name);
    console.log('SHOT FAIL ' + name + ' ' + String(e && e.message || e).split('\n')[0]);
  }
}

// The X screen (the window frame, the menu bar, a native menu or dialog), cropped to `rect` when given.
async function screenShot(name, rect) {
  try {
    await sleep(800);
    const sources = await desktopCapturer.getSources({ types: ['screen'], thumbnailSize: { width: 1280, height: 1024 } });
    if (!sources.length) throw new Error('no screen source');
    let img = sources[0].thumbnail;
    if (img.isEmpty()) throw new Error('empty screen capture');
    if (rect) img = img.crop(rect);
    fs.writeFileSync(path.join(OUT, name + '.png'), img.toPNG());
    const s = img.getSize();
    results.shots.push(name);
    console.log('SHOT ' + name + ' ' + s.width + 'x' + s.height);
  } catch (e) {
    results.failed.push(name);
    console.log('SHOT FAIL ' + name + ' ' + String(e && e.message || e).split('\n')[0]);
  }
}

async function section(name, fn) {
  try { await fn(); } catch (e) { results.failed.push('section:' + name); console.log('SECTION FAIL ' + name + ' ' + (e && e.stack || e)); }
}

// The inputs beside the uisample set: SVF faces (OFL, from svf/), the synthetic DOS raw font and its English font, the
// synthetic 86Box pair, and a file no detector knows.
const EXTRA_PY = `
import os, sys, json, shutil
repo, base = sys.argv[1], sys.argv[2]
for p in (os.path.join(repo, 'maker', 'test'), os.path.join(repo, 'maker'), os.path.join(repo, 'tools')):
    sys.path.insert(0, p)
import fixtures, test_recipe
def put(rel, data):
    path = os.path.join(base, rel); os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f: f.write(data if isinstance(data, bytes) else data.encode('utf-8'))
    return path
for rel in ('svf/jamo-extra/GOTHA16A.SVF', 'svf/dos/NEODG16.SVF'):
    os.makedirs(os.path.join(base, 'svf'), exist_ok=True)
    shutil.copyfile(os.path.join(repo, rel), os.path.join(base, 'svf', os.path.basename(rel)))
put('svf/OFL.txt', fixtures.SIL_LICENCE)
os.makedirs(os.path.join(base, 'dos'), exist_ok=True)
fixtures._dos_raw(os.path.join(base, 'dos', 'HAN.FNT'))
fixtures._eng(os.path.join(base, 'dos', 'ENG.FNT'))
put('dos/LICENSE.txt', fixtures.SIL_LICENCE)
rom, bios = test_recipe.synthetic_pair(os.path.join(base, 'roms'))
put('misc/notes.dat', bytes(range(256)) * 4)
os.makedirs(os.path.join(base, 'out'))
print(json.dumps({'roots': [os.path.join(base, d) for d in ('svf', 'dos', 'roms', 'misc')], 'out': os.path.join(base, 'out'),
                  'rom': rom, 'bios': bios}))
`;
// The sidecar with the built-in 86Box recipe set to the synthetic pair's hashes (test_recipe.library_for).
const SIDECAR_PY = `
import os, sys
repo, rom, bios = sys.argv[1], sys.argv[2], sys.argv[3]
for p in (os.path.join(repo, 'maker', 'test'), os.path.join(repo, 'tools'), os.path.join(repo, 'maker')):
    sys.path.insert(0, p)
import recipe, test_recipe
lib = dict(recipe.library()); lib.update(test_recipe.library_for(rom, bios))
recipe._LIBRARY[recipe.builtin_dir()] = lib
import server
server.main(sys.argv[4:])
`;
const OPTIMISE_PY = `
import os, sys
from PIL import Image
total = 0
for name in sorted(os.listdir(sys.argv[1])):
    if not name.endswith('.png'): continue
    p = os.path.join(sys.argv[1], name)
    im = Image.open(p).convert('RGB').quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    im.save(p, optimize=True)
    total += os.path.getsize(p)
print(total)
`;

// Pick the roots and the output folder through the page's buttons (the stubbed dialogs answer in order).
async function pickAll(roots, output) {
  for (const r of roots) dialogQueue.push({ canceled: false, filePaths: [r.path] });
  dialogQueue.push({ canceled: false, filePaths: [output] });
  await run(`const roots = ${JSON.stringify(roots)};
    await waitFor(() => visible($('choose-folder')));
    for (const r of roots) { $(r.button).click(); await waitFor(() => $('source-roots').textContent.includes(r.path)); }
    $('choose-output').click();
    await waitFor(() => $('output-shown').textContent === ${JSON.stringify(output)});`);
}

async function detect(count, ackShot) {
  await run(`$('detect-local').click(); await sleep(300);`);
  const ack = await run(`await sleep(300); return visible($('ack'));`);
  if (ack && ackShot) await shot(ackShot);
  const id = await run(`await waitFor(() => { const ack = $('ack'); if (visible(ack)) $('ack-ok').click();
      return document.querySelectorAll('#fonts tr[data-font]').length >= ${count}; }, 120000);
    // the rows' previews are lazy images: load them all now, so a capture never depends on how far they got
    for (const img of document.querySelectorAll('#fonts img.preview')) img.loading = 'eager';
    await waitFor(() => [...document.querySelectorAll('#fonts img.preview')].every((img) => img.complete), 60000);
    await sleep(800); return new URLSearchParams(location.search).get('job');`);
  jobIds.push(id);
  return id;
}

async function saveAndRun() {
  await run(`await waitFor(() => visible($('save')) && !$('save').disabled); $('save').click(); await sleep(1500);
    await waitFor(() => visible($('run')) && !$('run').disabled); $('run').click();`);
}

const waitDone = (minCanvases) => run(`await waitFor(() => /— (done|failed)/.test($('state').textContent), 300000);
  await waitFor(() => document.querySelectorAll('canvas[data-step][data-drawn="1"]').length >= ${minCanvases}, 120000);
  await sleep(1500); return $('state').textContent;`);

const toSteps = (above = 0) => run(`$('steps').closest('section').scrollIntoView({ block: 'start' });
  window.scrollBy(0, -(document.querySelector('header.top').getBoundingClientRect().height + ${above}));`);

app.on('window-all-closed', () => {});
app.whenReady().then(async () => {
  try {
    fs.mkdirSync(OUT, { recursive: true });
    for (const n of fs.readdirSync(OUT)) if (n.endsWith('.png')) fs.rmSync(path.join(OUT, n));
    const env = Object.assign({}, process.env, { SVF_MAKER_DEV: '1', TMPDIR: TMP });
    const pyEnv = Object.assign({}, process.env, { TMPDIR: TMP });
    const S = JSON.parse((await execFileAsync(PY, ['-B', '-P', path.join(REPO, 'maker', 'test', 'uisample.py'), 'make',
      path.join(TMP, 'sample')], { env: pyEnv, timeout: 60000 })).stdout);
    const X = JSON.parse((await execFileAsync(PY, ['-B', '-P', '-c', EXTRA_PY, REPO, path.join(TMP, 'extra')],
      { env: pyEnv, timeout: 60000 })).stdout);
    const ud = path.join(TMP, 'ud');
    fs.mkdirSync(ud, { recursive: true });
    const launch = { mode: 'dev', cmd: PY, args: ['-B', '-P', '-c', SIDECAR_PY, REPO, X.rom, X.bios, '--exit-with-parent=' + process.pid],
      repo: REPO, data: path.join(ud, 'maker-dev') };
    handle = await require('../main.js').start({ userData: ud, quitOnClose: false, env, launch, fatal: () => app.exit(1) });
    const t0 = Date.now();
    while (!(handle.sidecar.port > 0)) { await sleep(100); if (Date.now() - t0 > 75000) throw new Error('no sidecar port'); }
    handle.win.setContentSize(W, H);
    handle.win.setPosition(0, 0);

    // ---- the starting page and the empty window ------------------------------------------------------------------
    await section('start', async () => {
      await handle.win.loadFile(path.join(__dirname, '..', 'starting.html'));
      await shot('starting', { sel: 'p', pad: 40, noScroll: true });
      await handle.win.loadURL(handle.sidecar.origin + '/');
      await run(`await waitFor(() => visible($('choose-folder')));`);
      await shot('start');
    });

    // ---- job 1: the uisample set ---------------------------------------------------------------------------------
    let job1 = null;
    await section('sample set', async () => {
      await pickAll(S.dialog, S.output);
      await shot('sources-chosen', { sel: '#sources-panel', pad: 6 });
      job1 = await detect(Object.keys(S.inputs).length, 'acknowledge');
      await shot('detected', { sel: '#fonts', above: 34 });
      await shot('fonts-mac-hwp', { expr: `await (async () => { const j = await getJob(); const f = j.fonts.find((x) => x.path === 'Seoul12.rsrc');
        const rows = [...document.querySelectorAll('#fonts tr[data-font]')]; const i = rows.indexOf(rowOf(f.id));
        return rows.slice(i, i + 9); })()`, fullWidth: true });
    });
    await section('batch', async () => {
      await run(`for (const k of ['ttf', 'bdf', 'composite']) choose($('export-' + k), true); mark($('export'));`);
      await shot('batch-settings', { sel: '#settings', pad: 6 });
      await run(`unmark(); for (const k of ['ttf', 'bdf', 'composite']) choose($('export-' + k), false);
        $('advanced').open = true;`);
      await shot('batch-advanced', { sel: '#settings', pad: 6 });
      await run(`$('advanced').open = false;`);
    });
    await section('per-font settings', async () => {
      // the sample's table (uisample FONTS), through the page's controls, as the desktop e2e does
      await run(`const S = ${JSON.stringify(S)};
        const job = await getJob();
        const rootOf = (p) => S.dialog.findIndex((e) => e.path === p);
        const fidOf = (root, p) => job.fonts.filter((f) => f.root === root && f.path === p)[0].id;
        const want = new Map(Object.entries(S.fonts).map(([key, f]) => [fidOf(rootOf(f.root_path), f.path), { key, ui: f.ui }]));
        for (const tr of document.querySelectorAll('#fonts tr[data-font]')) { const cb = tr.querySelector('input.selected'); if (!cb.disabled) choose(cb, want.has(tr.dataset.font)); }
        for (const [fid, { ui }] of want) {
          const tr = rowOf(fid); choose(tr.querySelector('input.override'), true);
          const ov = ovOf(fid); const q = (s) => ov.querySelector(s);
          const companion = (p) => fidOf(job.fonts.find((f) => f.id === fid).root, p);
          if (ui.kinds) choose(q('select.ov-kinds'), ui.kinds.join(','));
          if (ui.dest) choose(q('select[aria-label^="dest for "]'), ui.dest);
          if (ui.sizes) choose(q('input.ov-sizes'), ui.sizes.join(', '));
          if (ui.bpp) choose(q('select.ov-bpp'), ui.bpp.join(','));
          if (ui.preset) choose(q('select[aria-label^="preset for "]'), ui.preset);
          if (ui.instance) choose(q('select[data-field=instance]'), JSON.stringify(ui.instance));
          if (ui.htbl) choose(q('select[data-field=htbl_companion]'), companion(ui.htbl));
          if (ui.latin) choose(q('select[aria-label^="latin companion for "]'), companion(ui.latin));
          if (ui.dos_layout) choose(tr.querySelector('select.dos-layout'), ui.dos_layout);
          for (const [fmt, on] of Object.entries(ui.export || {})) choose(q('select[data-export=' + fmt + ']'), on ? 'on' : 'off');
        }
        // the overrides of the fonts not pictured are closed again (their settings stay)
        const keep = new Set(['neodgm.ttf', 'johab.bdf']);
        for (const f of job.fonts) if (want.has(f.id) && !keep.has(f.path)) { const ov = ovOf(f.id); if (ov) ov.hidden = true; }`);
      const fid = (p) => `(async () => (await getJob()).fonts.find((x) => x.path === ${JSON.stringify(p)}).id)()`;
      await shot('font-override', { expr: `await (async () => { const id = await ${fid('neodgm.ttf')}; return [rowOf(id), ovOf(id)]; })()` });
      await run(`const id = await ${fid('johab.bdf')}; const ov = ovOf(id);
        const r = ov.querySelector('select[aria-label^="jamo route for "]'); r.size = Math.min(6, r.options.length); mark(r);
        mark(ov.querySelector('.export-own'));`);
      await shot('font-override-jamo-route', { expr: `await (async () => { const id = await ${fid('johab.bdf')}; return [rowOf(id), ovOf(id)]; })()` });
      await run(`unmark(); for (const s of document.querySelectorAll('select[size]')) s.removeAttribute('size');
        const id = await ${fid('neodgm.ttf')}; const sel = rowOf(id).querySelector('select.licence');
        sel.size = Math.min(12, sel.options.length); sel.style.width = '250px'; mark(sel);`);
      await shot('licence-picker', { expr: `await (async () => { const id = await ${fid('neodgm.ttf')}; return rowOf(id); })()`,
        fullWidth: true, above: 30 });
      await run(`unmark(); for (const s of document.querySelectorAll('select[size]')) { s.removeAttribute('size'); s.style.width = ''; }`);
    });
    await section('run sample set', async () => {
      await saveAndRun();
      await run(`await waitFor(() => /— (running|queued)/.test($('state').textContent) && document.querySelectorAll('#steps tbody tr').length > 0, 60000);
        await waitFor(() => [...document.querySelectorAll('#steps tbody tr')].some((tr) => tr.children[6].textContent.startsWith('done')), 120000);`);
      await toSteps();
      await shot('running', { wait: 200 });
      await waitDone(10);
      await toSteps();
      await shot('done');
      await shot('preview-precomposed-1bpp', { expr: `stepRow('NEODU16.SVF')`, fullWidth: true });
      await shot('preview-precomposed-2bpp', { expr: `stepRow('NANUM17A.SVF')`, fullWidth: true });
      await shot('preview-jamo-1bpp', { expr: `stepRow('JOHA16J.SVF')`, fullWidth: true });
      await shot('export-ttf-bdf', { expr: `[...document.querySelectorAll('#steps tbody tr')].filter((tr) => /^KSC16|^JOHA16J/.test(tr.children[5].textContent))`,
        fullWidth: true });
      await run(`const tr = stepRow('NANUM17A.SVF'); [...tr.querySelectorAll('button')].find((b) => b.textContent === 'glyphs').click(); await sleep(1500);`);
      await shot('glyph-grid', { expr: `stepRow('NANUM17A.SVF')`, fullWidth: true });
      await shot('jobs-list', { expr: `[$('jobs').previousElementSibling, $('jobs')]`, pad: 6 });
    });

    // ---- the window frame, a native menu, About (the X screen) -------------------------------------------------------
    await section('screen', async () => {
      await handle.win.loadURL(handle.sidecar.origin + '/?job=' + job1);
      await run(`await waitFor(() => /— done/.test($('state').textContent)); await sleep(1000);`);
      await mask();
      const b = handle.win.getBounds();
      await screenShot('window', { x: Math.max(0, b.x), y: Math.max(0, b.y), width: Math.min(b.width, 1280), height: Math.min(b.height, 1024) });
      const view = Menu.getApplicationMenu().items.find((i) => i.label === 'View');
      view.submenu.popup({ window: handle.win, x: 60, y: 0 });
      await screenShot('menu-view', { x: 0, y: 0, width: 420, height: 260 });
      view.submenu.closePopup(handle.win);
      await sleep(300);
      const ac = new AbortController();
      messageBox = (win, opts) => realMessageBox.call(electron.dialog, win, Object.assign({}, opts, { signal: ac.signal }));
      const help = Menu.getApplicationMenu().items.find((i) => i.label === 'Help');
      help.submenu.items.find((i) => i.label === 'About').click();
      await screenShot('about', { x: 0, y: 0, width: 600, height: 210 });
      ac.abort();
      messageBox = async () => ({ response: 0 });
      await sleep(500);
    });

    // ---- job 2: SVF, DOS raw, known ROM set, unknown -------------------------------------------------------------
    await section('more kinds', async () => {
      await handle.win.loadURL(handle.sidecar.origin + '/');
      await run(`await waitFor(() => visible($('choose-folder')));`);
      await pickAll(X.roots.map((p) => ({ button: 'choose-folder', path: p })), X.out);
      const n = 9;
      await detect(n, null);
      await shot('detected-kinds', { sel: '#fonts', above: 34 });
      await run(`const j = await getJob(); const f = j.fonts.find((x) => x.path === 'HAN.FNT');
        const s = rowOf(f.id).querySelector('select.dos-layout'); s.size = Math.min(5, s.options.length); mark(s);`);
      await shot('dos-layout-confirm', { expr: `await (async () => { const j = await getJob(); return rowOf(j.fonts.find((x) => x.path === 'HAN.FNT').id); })()`,
        fullWidth: true, above: 20 });
      await run(`unmark(); for (const s of document.querySelectorAll('select[size]')) s.removeAttribute('size');
        const job = await getJob(); const by = (p) => job.fonts.find((x) => x.path === p);
        const want = { 'GOTHA16A.SVF': 1, 'NEODG16.SVF': 1, 'tg_ksc5601.rom': 1, 'HAN.FNT': 1 };
        for (const tr of document.querySelectorAll('#fonts tr[data-font]')) { const cb = tr.querySelector('input.selected');
          const f = job.fonts.find((x) => x.id === tr.dataset.font); if (!cb.disabled) choose(cb, !!want[f.path]); }
        const open = (p) => { const f = by(p); choose(rowOf(f.id).querySelector('input.override'), true); return { tr: rowOf(f.id), ov: ovOf(f.id) }; };
        let o = open('GOTHA16A.SVF');
        choose(o.ov.querySelector('select.ov-kinds'), 'jamo'); choose(o.ov.querySelector('select[aria-label^="dest for "]'), 'jamo-extra');
        o = open('NEODG16.SVF');
        choose(o.ov.querySelector('select[aria-label^="precomposed route for "]'), 'svf2ttf');
        choose(o.ov.querySelector('select[data-export=ttf]'), 'on'); choose(o.ov.querySelector('select[data-export=bdf]'), 'on');
        o = open('tg_ksc5601.rom');
        choose(o.ov.querySelector('select.ov-kinds'), 'precomposed'); choose(o.ov.querySelector('select.ov-bpp'), '1');
        choose(o.ov.querySelector('select[data-export=ttf]'), 'on');
        o = open('HAN.FNT');
        choose(o.tr.querySelector('select.dos-layout'), '844');
        choose(o.ov.querySelector('select.ov-kinds'), 'jamo'); choose(o.ov.querySelector('select[aria-label^="dest for "]'), 'jamo-extra');
        for (const p of ['GOTHA16A.SVF', 'tg_ksc5601.rom', 'HAN.FNT']) ovOf(by(p).id).hidden = true;
        const r = ovOf(by('NEODG16.SVF').id).querySelector('select[aria-label^="precomposed route for "]');
        r.size = Math.min(4, r.options.length); mark(r);`);
      await shot('font-override-svf2ttf', { expr: `await (async () => { const j = await getJob(); const id = j.fonts.find((x) => x.path === 'NEODG16.SVF').id; return [rowOf(id), ovOf(id)]; })()` });
      await run(`unmark(); for (const s of document.querySelectorAll('select[size]')) s.removeAttribute('size');`);
      await saveAndRun();
      const state = await waitDone(3);
      console.log('NOTE job 2: ' + state.split(MASK.tmp).join('').split(TMP).join('<tmp>'));
      await toSteps();
      await shot('done-kinds');
      await shot('preview-jamo-2bpp', { expr: `stepRow('GOTHA16A.SVF') || [...document.querySelectorAll('#steps tbody tr')].find((tr) => tr.children[2].textContent === 'jamo' && tr.children[4].textContent === '2')`, fullWidth: true });
      await shot('preview-known-rom', { expr: `[...document.querySelectorAll('#steps tbody tr')].filter((tr) => /^TGVGA16/.test(tr.children[5].textContent))`, fullWidth: true });
      await shot('export-svf2ttf', { expr: `[...document.querySelectorAll('#steps tbody tr')].filter((tr) => /^NEODG16/.test(tr.children[5].textContent))`, fullWidth: true });
    });

    // ---- job 3: a refused setting and a failed step --------------------------------------------------------------
    await section('errors', async () => {
      await handle.win.loadURL(handle.sidecar.origin + '/');
      await run(`await waitFor(() => visible($('choose-folder')));`);
      const errOut = path.join(TMP, 'err-out');
      fs.mkdirSync(errOut, { recursive: true });
      await pickAll([{ button: 'choose-folder', path: path.join(REPO, 'ttf', 'neodgm') }], errOut);
      await detect(2, null);
      await run(`choose($('dest'), '__new'); $('dest-new').disabled = false; $('dest-new').value = 'my/set';
        $('dest-new').dispatchEvent(new Event('input', { bubbles: true }));
        $('save').click(); await waitFor(() => visible($('notice')) && $('notice').textContent.length > 0, 20000);
        window.scrollTo(0, 0);`);
      await shot('dest-refused', { sel: '#notice, #settings', fromTop: true, noScroll: true, pad: 6 });
      await run(`choose($('dest'), 'dos'); $('dest-new').value = '';
        for (const cb of $('bpp').querySelectorAll('input')) choose(cb, cb.value === '1');
        $('advanced').open = true; choose($('opt-cell'), '6'); choose($('opt-fit-cell'), true);
        for (const cb of $('kinds').querySelectorAll('input')) choose(cb, cb.value === 'precomposed');
        const job = await getJob(); const f = job.fonts.find((x) => x.path === 'neodgm.ttf');
        choose(rowOf(f.id).querySelector('input.selected'), true);
        choose(rowOf(f.id).querySelector('input.override'), true);
        choose(ovOf(f.id).querySelector('select.ov-kinds'), 'precomposed'); choose(ovOf(f.id).querySelector('select.ov-bpp'), '1');
        ovOf(f.id).hidden = true;`);
      await saveAndRun();
      const state = await waitDone(0);
      console.log('NOTE job 3: ' + state.split(TMP).join('<tmp>'));
      await run(`window.scrollTo(0, 0);`);
      await toSteps(0);
      await shot('failed-step', { sel: '#steps', above: 0, fullWidth: true, pad: 4 });
      await run(`window.scrollTo(0, 0);`);
      await shot('failed-status', { sel: 'header.top', noScroll: true, pad: 0 });
    });

    await handle.shutdown();
    const total = Number((await execFileAsync(PY, ['-B', '-I', '-c', OPTIMISE_PY, OUT], { timeout: 120000 })).stdout.trim());
    console.log('SHOTS DONE ' + results.shots.length + ' files, ' + total + ' bytes' +
      (results.failed.length ? '; failed: ' + results.failed.join(', ') : ''));
    fs.rmSync(TMP, { recursive: true, force: true });
    app.exit(results.failed.length ? 1 : 0);
  } catch (e) {
    console.log('SHOTS FAIL ' + (e && e.stack || e));
    app.exit(1);
  }
});
