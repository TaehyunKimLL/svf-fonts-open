'use strict';
// Electron end-to-end test (main script): runs the real main.js with stubbed dialogs under xvfb. Prints
// "E2E PASS <name>" / "E2E FAIL <name> <message>", exits 1 on any failure. Pass 1: the development sidecar
// (python3 maker/server.py); pass 2 (SVF_MAKER_SIDECAR + SVF_MAKER_STAGED_REPO): the packaged layout.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const { execFile } = require('node:child_process');
const execFileAsync = require('node:util').promisify(execFile);
global.SVF_MAKER_EMBEDDED = true;                       // main.js must not auto-start: this script calls start()
const electron = require('electron');
const { app, BrowserWindow, session } = electron;

const TMP = process.env.TMP_DIR || os.tmpdir();
const REPO = path.join(__dirname, '..', '..');
const results = { pass: 0, fail: 0 };
const dialogQueue = [];
const messageBoxes = [];
const revealed = [];
electron.dialog.showOpenDialog = async () => dialogQueue.shift() || { canceled: true, filePaths: [] };
electron.dialog.showMessageBox = async (...a) => { messageBoxes.push(a); return { response: 0 }; };
electron.shell.showItemInFolder = (p) => { revealed.push(p); };

// A stub in front of the real sidecar command: it prints one stderr line carrying a path with spaces and the per-launch
// token, then execs the real command (same pid). The shell logs the sidecar's last stderr lines, so shell.log must hold
// the redacted line (positive pin) and neither the path nor either token.
const CANARY_DIR = '/home/canary/My Fonts/Secret Project/out';
const { resolveLaunch } = require('../lib/paths.js');
function wrappedLaunch(opts, ud) {
  const base = resolveLaunch({ resourcesPath: opts.resourcesPath || process.resourcesPath, appDir: path.join(__dirname, '..'),
    env: opts.env, pid: process.pid, userData: ud });
  const script = 'echo "test-stderr: ' + CANARY_DIR + ' $SVF_MAKER_TOKEN" >&2; exec "$@"';
  return Object.assign({}, base, { cmd: 'sh', args: ['-c', script, 'sh', base.cmd].concat(base.args) });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitUntil(fn, ms, what) {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error('timeout: ' + what);
    await sleep(100);
  }
}
async function step(name, fn) {
  try { await fn(); results.pass++; console.log('E2E PASS ' + name); }
  catch (e) { results.fail++; console.log('E2E FAIL ' + name + ' ' + String(e && e.message || e).split('\n')[0]); }
}

const PRELUDE = `const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const waitFor = async (fn, ms = 60000) => { const end = Date.now() + ms; for (;;) { const v = await fn(); if (v) return v;
    if (Date.now() > end) throw new Error('page timeout: ' + fn); await sleep(100); } };
  const visible = (el) => !!el && !el.hidden && el.getClientRects().length > 0;`;
const run = (handle, js) => handle.win.webContents.executeJavaScript('(async () => {' + PRELUDE + js + '})()', true);
const logText = (handle) => fs.readFileSync(handle.log.path, 'utf8');

function mkdir(...p) { const d = path.join(TMP, ...p); fs.mkdirSync(d, { recursive: true }); return d; }

async function localJob(handle, srcDir, outDir) {
  dialogQueue.push({ canceled: false, filePaths: [srcDir] }, { canceled: false, filePaths: [outDir] });
  return run(handle, `
    document.getElementById('choose-folder').click();
    await waitFor(() => document.getElementById('source-roots').textContent.includes(${JSON.stringify(srcDir)}));
    document.getElementById('choose-output').click();
    await waitFor(() => document.getElementById('sources-panel').textContent.includes(${JSON.stringify(path.basename(outDir))}));
    document.getElementById('detect-local').click();
    await sleep(300);
    const ack = document.getElementById('ack');
    if (visible(ack)) document.getElementById('ack-ok').click();
    await waitFor(() => document.querySelectorAll('#fonts tr[data-font]').length >= 1);
    const id = new URLSearchParams(location.search).get('job');
    const job = await (await fetch('/api/jobs/' + id)).json();
    const st = job.settings;
    const fid = job.fonts[0].id;
    Object.assign(st.fonts[fid], { selected: true, dest: 'dos', kinds: ['precomposed'], sizes: [16], bpp: [1] });
    const put = await fetch('/api/jobs/' + id + '/settings', { method: 'PUT', body: JSON.stringify(st) });
    if (put.status !== 200) throw new Error('PUT settings ' + put.status + ' ' + await put.text());
    location.reload();
    return id;`).then(async (id) => {
      await waitUntil(async () => (await run(handle, `return document.readyState === 'complete' && !!document.getElementById('run');`)), 30000, 'reload');
      await run(handle, `await sleep(500); document.getElementById('run').click();
        await waitFor(() => document.getElementById('state').textContent.includes('written to'), 120000);
        await waitFor(() => document.querySelector('canvas[data-step][data-drawn="1"]'), 60000);`);
      return id;
    });
}

async function pass(name, opts) {
  const { main } = { main: require('../main.js') };
  fs.rmSync(path.join(TMP, name), { recursive: true, force: true });       // every run starts from nothing
  const ud = mkdir(name, 'ud');
  const handle = await main.start(Object.assign({ userData: ud, quitOnClose: false, launch: wrappedLaunch(opts, ud) }, opts));
  const pids = { shell: process.pid, sidecar: handle.sidecar.pid };
  const tmpA = mkdir(name, 'tmpA'), tmpB = mkdir(name, 'tmpB'), outA = mkdir(name, 'outA'), outB = mkdir(name, 'outB');
  const outC = mkdir(name, 'realparent', 'outC'), outD = mkdir(name, 'outD');
  // the dialog hands out a path through a symlinked parent (the server refuses a symlink as the folder itself)
  const outCLink = path.join(TMP, name, 'linkparent', 'outC');
  fs.symlinkSync(path.join(TMP, name, 'realparent'), path.join(TMP, name, 'linkparent'));
  for (const d of [tmpA, tmpB]) fs.copyFileSync(path.join(REPO, 'ttf', 'neodgm', 'neodgm.ttf'), path.join(d, 'neodgm.ttf'));
  const T = (n) => name + ': ' + n;
  let jobA = null, jobB = null, jobC = null;
  const tokens = [];                                          // every sidecar token this pass saw

  await step(T('handshake'), async () => {
    await waitUntil(() => handle.sidecar.port > 0, 75000, 'port');
    tokens.push(handle.sidecar.token);
    assert.match(logText(handle), /sidecar port=\d+/);
    assert.match(logText(handle), new RegExp('sidecar start mode=' + (name === 'packaged' ? 'packaged' : 'dev')));
  });
  await step(T('title'), async () => {
    await waitUntil(async () => (await run(handle, 'return document.title')) === 'SVF maker', 20000, 'title');
  });
  await step(T('bridge'), async () => {
    const t = await run(handle, `return ['pickFiles', 'pickFolder', 'pickOutputDir', 'openOutputFolder'].map((k) => typeof window.svfMaker[k])
      .concat([window.svfMaker.platform, typeof window.require, typeof window.ipcRenderer]);`);
    assert.deepEqual(t, ['function', 'function', 'function', 'function', 'linux', 'undefined', 'undefined']);
  });
  await step(T('header'), async () => {
    const t = await run(handle, `return [(await fetch('/api/caps')).status,
      (await fetch('/api/caps', { headers: { 'X-Maker-Token': '0'.repeat(32) } })).status];`);
    assert.deepEqual(t, [200, 200]);
  });
  await step(T('outbound'), async () => {
    const t = await run(handle, `let rejected = false;
      try { await fetch('http://127.0.0.1:1/x'); } catch (e) { rejected = true; }
      const opened = window.open('http://example.invalid/');
      const before = location.origin;
      location.href = 'http://example.invalid/';
      await sleep(1000);
      return { rejected, opened, same: location.origin === before, origin: location.origin };`);
    assert.equal(t.rejected, true);
    assert.equal(t.opened, null);
    assert.equal(t.origin, handle.sidecar.origin);
  });
  await step(T('download'), async () => {
    const ses = session.fromPartition('maker');
    const seen = [];
    const listener = (e, item) => seen.push({ prevented: e.defaultPrevented });
    ses.on('will-download', listener);
    const dl = app.getPath('downloads');
    const before = fs.existsSync(dl) ? fs.readdirSync(dl).length : 0;
    await run(handle, `const a = document.createElement('a'); a.href = '/static/maker.js'; a.download = 'x.js'; document.body.appendChild(a); a.click(); await sleep(800);`);
    ses.removeListener('will-download', listener);
    assert.ok(seen.length >= 1 && seen.every((s) => s.prevented), JSON.stringify(seen));
    assert.equal(fs.existsSync(dl) ? fs.readdirSync(dl).length : 0, before);
  });
  await step(T('flow'), async () => {
    jobA = await localJob(handle, tmpA, outA);
    await handle.win.loadURL(handle.sidecar.origin + '/');
    jobB = await localJob(handle, tmpB, outB);
  });
  await step(T('sample set'), async () => {
    // The OFL sample set plus the synthetic Mac/HWP/BDF/HangulTalk sample through the page (maker/test/uisample.py owns the
    // sample, the settings table and the checks of the written tree).
    const t0 = Date.now();
    const realTmp = fs.realpathSync(TMP);
    assert.ok(realTmp !== '/tmp' && !realTmp.startsWith('/tmp/'), 'TMP must not be under /tmp: ' + realTmp);
    const PY = process.env.SVF_E2E_PYTHON || 'python3';
    const helper = path.join(REPO, 'maker', 'test', 'uisample.py');
    const sampleDir = path.join(TMP, name, 'sample');
    const env = Object.assign({}, process.env, { TMPDIR: TMP });
    const made = await execFileAsync(PY, ['-B', '-P', helper, 'make', sampleDir], { env, timeout: 60000 });
    const sample = JSON.parse(made.stdout);
    assert.equal(sample.dialog.length, 9);
    await handle.win.loadURL(handle.sidecar.origin + '/');
    for (const e of sample.dialog) dialogQueue.push({ canceled: false, filePaths: [e.path] });
    dialogQueue.push({ canceled: false, filePaths: [sample.output] });
    const jobId = await run(handle, `
      const S = ${JSON.stringify(sample)};
      for (const e of S.dialog) {
        document.getElementById(e.button).click();
        await waitFor(() => document.getElementById('source-roots').textContent.includes(e.path));
      }
      document.getElementById('choose-output').click();
      await waitFor(() => document.getElementById('output-shown').textContent === S.output);
      document.getElementById('detect-local').click();
      await waitFor(() => {
        const ack = document.getElementById('ack');
        if (visible(ack)) document.getElementById('ack-ok').click();
        return document.querySelectorAll('#fonts tr[data-font]').length >= 24;
      }, 120000);
      return new URLSearchParams(location.search).get('job');`);
    assert.equal(dialogQueue.length, 0, 'every dialog answer must have been used');
    const settled = await run(handle, `
      const S = ${JSON.stringify(sample)};
      const id = ${JSON.stringify(jobId)};
      const getJob = async () => (await fetch('/api/jobs/' + id)).json();
      let job = await getJob();
      const problems = [];
      // the page's own controls only: a control must exist, be enabled and (a select) offer the option, enabled
      const choose = (ctl, value, what) => {
        if (!ctl) throw new Error('no control: ' + what);
        if (ctl.disabled) throw new Error('disabled control: ' + what);
        if (ctl.tagName === 'SELECT') {
          const opt = [...ctl.options].find((o) => o.value === value);
          if (!opt) throw new Error('no option ' + JSON.stringify(value) + ' in ' + what);
          if (opt.disabled) throw new Error('disabled option ' + JSON.stringify(value) + ' in ' + what + ': ' + opt.title);
          ctl.value = value;
        } else if (ctl.type === 'checkbox') ctl.checked = !!value;
        else ctl.value = value;
        ctl.dispatchEvent(new Event('input', { bubbles: true }));
        ctl.dispatchEvent(new Event('change', { bubbles: true }));
      };
      S.dialog.forEach((e, i) => { if (!job.roots[i] || job.roots[i].path !== e.path) throw new Error('root ' + i + ' is not ' + e.path); });
      const rootOf = (p) => S.dialog.findIndex((e) => e.path === p);
      const fidOf = (root, p) => {
        const hit = job.fonts.filter((f) => f.root === root && f.path === p);
        if (hit.length !== 1) throw new Error('font ' + root + '/' + p + ': ' + hit.length + ' entries');
        return hit[0].id;
      };
      const rowOf = (fid) => document.querySelector('#fonts tr[data-font="' + fid + '"]');
      const ovrOf = (fid) => document.querySelector('#fonts tr.override[data-for="' + fid + '"]');
      const want = new Map(Object.entries(S.fonts).map(([key, f]) => [fidOf(rootOf(f.root_path), f.path), { key, ui: f.ui }]));
      if (want.size !== Object.keys(S.fonts).length) throw new Error('two sample fonts share a row');
      const rows = [...document.querySelectorAll('#fonts tr[data-font]')];
      if (rows.length !== job.fonts.length) throw new Error('rows ' + rows.length + ' != fonts ' + job.fonts.length);
      // 1. the rows the page offers no route for stay disabled and unchecked, and are never touched
      const noRoute = [];
      for (const tr of rows) {
        const fid = tr.dataset.font, cb = tr.querySelector('input.selected');
        if (job.settings.fonts[fid]) { if (cb.disabled) problems.push(fid + ': has a route but its tick is disabled'); continue; }
        noRoute.push(fid);
        if (!cb.disabled || cb.checked) problems.push(fid + ': a row with no route must be a disabled, unchecked tick');
        if (!tr.querySelector('input.override').disabled) problems.push(fid + ': override must be disabled');
        if (!tr.querySelector('select.licence').disabled) problems.push(fid + ': licence select must be disabled');
      }
      const byPath = (p) => job.fonts.filter((f) => f.path === p).map((f) => f.id);
      for (const p of ['InputBackSupport.rsrc', 'Suitcase.rsrc', 'ASCII.PFT', 'HANGUL24.PFT'])
        for (const fid of byPath(p)) if (!noRoute.includes(fid)) problems.push(p + ' (' + fid + ') must have no route');
      for (const f of job.fonts) if (f.format === 'licence' && !noRoute.includes(f.id)) problems.push(f.path + ' (' + f.id + ') must have no route');
      for (const p of S.not_read) {
        const ids = byPath(p);
        if (ids.length !== 1) problems.push(p + ': ' + ids.length + ' rows');
        else if (!rowOf(ids[0]).textContent.includes('not read')) problems.push(p + ': its label does not say "not read"');
      }
      if (problems.length) throw new Error('rows: ' + problems.join('; '));
      // 2. the ticks: only the enabled ones are changed (on for each sample font, off for every other)
      for (const tr of rows) {
        const fid = tr.dataset.font, cb = tr.querySelector('input.selected');
        if (cb.disabled) continue;
        const on = want.has(fid);
        choose(cb, on, 'use ' + fid);
      }
      for (const p of S.untick) for (const fid of byPath(p)) if (rowOf(fid).querySelector('input.selected').checked) throw new Error(p + ' is still ticked');
      // 3. each sample font's settings, in its override row
      for (const [fid, { ui }] of want) {
        const tr = rowOf(fid);
        choose(tr.querySelector('input.override'), true, 'override ' + fid);
        const ov = ovrOf(fid);
        const q = (sel, what) => { const c = ov.querySelector(sel); if (!c) throw new Error('no ' + what + ' for ' + fid); return c; };
        const companion = (p) => fidOf(job.fonts.find((f) => f.id === fid).root, p);
        if (ui.kinds) choose(q('select.ov-kinds', 'kinds'), ui.kinds.join(','), 'kinds ' + fid);
        if (ui.dest) choose(q('select[aria-label^="dest for "]', 'dest'), ui.dest, 'dest ' + fid);
        if (ui.sizes) choose(q('input.ov-sizes', 'sizes'), ui.sizes.join(', '), 'sizes ' + fid);
        if (ui.bpp) choose(q('select.ov-bpp', 'bpp'), ui.bpp.join(','), 'bpp ' + fid);
        if (ui.preset) choose(q('select[aria-label^="preset for "]', 'preset'), ui.preset, 'preset ' + fid);
        if (ui.instance) choose(q('select[data-field=instance]', 'instance'), JSON.stringify(ui.instance), 'instance ' + fid);
        if (ui.htbl) choose(q('select[data-field=htbl_companion]', 'htbl'), companion(ui.htbl), 'htbl ' + fid);
        if (ui.latin) choose(q('select[aria-label^="latin companion for "]', 'latin'), companion(ui.latin), 'latin ' + fid);
        if (ui.dos_layout) choose(tr.querySelector('select.dos-layout'), ui.dos_layout, 'dos layout ' + fid);
      }
      // 4. save, then read back what the page wrote
      const intended = (j) => {
        const bad = [];
        for (const [fid, per] of Object.entries(j.settings.fonts)) {
          const w = want.get(fid);
          const on = !!w;
          if (!!per.selected !== on) bad.push(fid + ' selected=' + per.selected);
          if (!w) continue;
          const ui = w.ui, cmp = (k, v, got) => { if (JSON.stringify(v) !== JSON.stringify(got)) bad.push(fid + ' ' + k + '=' + JSON.stringify(got)); };
          for (const k of ['kinds', 'sizes', 'bpp', 'dest', 'preset', 'instance', 'dos_layout']) if (k in ui) cmp(k, ui[k], per[k]);
          const root = j.fonts.find((f) => f.id === fid).root;
          if (ui.htbl) cmp('htbl_companion', fidOf(root, ui.htbl), per.htbl_companion);
          if (ui.latin) cmp('latin_companion', fidOf(root, ui.latin), per.latin_companion);
        }
        return bad;
      };
      await waitFor(() => visible(document.getElementById('save')) && !document.getElementById('save').disabled);
      document.getElementById('save').click();
      let bad = ['not saved yet'];
      const end = Date.now() + 60000;
      while (Date.now() < end) { job = await getJob(); bad = intended(job); if (!bad.length) break; await sleep(200); }
      if (bad.length) throw new Error('saved settings differ from the table: ' + bad.join('; '));
      // 5. run
      await waitFor(() => visible(document.getElementById('run')) && !document.getElementById('run').disabled);
      document.getElementById('run').click();
      await waitFor(() => document.getElementById('state').textContent.includes('written to'), 180000);
      return await getJob();`);
    // the output is checked before the canvases are counted, so a missing face fails here by name
    const dl = Date.now() + 10000;                              // the end-of-run sweep of .svf-maker-<id>/, bounded
    while (fs.readdirSync(sample.output).some((n) => n.startsWith('.svf-maker-')) && Date.now() < dl) await sleep(100);
    const jobJson = path.join(sampleDir, 'job.json');
    fs.writeFileSync(jobJson, JSON.stringify(settled));
    const args = ['-B', '-P', helper, 'check', sampleDir, jobJson];
    if (name === 'packaged') args.push('--same-as', path.join(TMP, 'dev', 'sample', 'out'));
    let verdict;
    try { verdict = JSON.parse((await execFileAsync(PY, args, { env, timeout: 180000 })).stdout); }
    catch (e) {
      if (e.stdout) { try { verdict = JSON.parse(e.stdout); } catch (e2) { throw e; } } else throw e;
    }
    for (const n of verdict.notes || []) console.log('E2E NOTE sample set: ' + n);
    if (!verdict.ok) throw new Error('uisample check: ' + verdict.failures.slice(0, 3).join(' | '));
    const canvases = await run(handle, `
      const sel = 'canvas[data-step][data-drawn="1"]';
      await waitFor(() => document.querySelectorAll(sel).length >= 10, 120000);
      return [...document.querySelectorAll(sel)].map((c) => [c.dataset.step, Number(c.dataset.ink)]);`);
    assert.equal(canvases.length, 10, 'result canvases: ' + JSON.stringify(canvases));
    for (const [stepId, ink] of canvases) assert.ok(ink > 0, 'canvas of step ' + stepId + ' has no ink');
    console.log('E2E NOTE sample set ' + name + ' ' + ((Date.now() - t0) / 1000).toFixed(1) + ' s');
  });
  await step(T('open-folder'), async () => {
    revealed.length = 0;
    await handle.win.loadURL(handle.sidecar.origin + '/?job=' + jobA);
    await run(handle, `await waitFor(() => visible(document.getElementById('open-folder')) && !document.getElementById('open-folder').disabled);
      document.getElementById('open-folder').click(); await sleep(500);`);
    assert.deepEqual(revealed, [fs.realpathSync(outA)]);
    dialogQueue.push({ canceled: false, filePaths: [tmpA] }, { canceled: false, filePaths: [outCLink] });
    const created = await run(handle, `
      const r = await fetch('/api/jobs', { method: 'POST', body: JSON.stringify({ source: 'local', output_dir: ${JSON.stringify(outCLink)} }) });
      if (r.status !== 200) throw new Error('create ' + r.status + ' ' + await r.text());
      return (await r.json()).id;`);
    jobC = created;
    // hand the symlink out through the bridge (what the page's #choose-output does), then reveal for that job
    await run(handle, `await window.svfMaker.pickFolder(); await window.svfMaker.pickOutputDir();`);
    revealed.length = 0;
    await handle.win.loadURL(handle.sidecar.origin + '/?job=' + jobC);
    await run(handle, `await window.svfMaker.openOutputFolder();`);
    assert.deepEqual(revealed, [fs.realpathSync(outC)]);
    const direct = await run(handle, `
      const r = await fetch('/api/jobs', { method: 'POST', body: JSON.stringify({ source: 'local', output_dir: ${JSON.stringify(outD)} }) });
      return (await r.json()).id;`);
    revealed.length = 0;
    await handle.win.loadURL(handle.sidecar.origin + '/?job=' + direct);
    await run(handle, `await window.svfMaker.openOutputFolder();`);
    assert.deepEqual(revealed, []);
    assert.match(logText(handle), /open-output: refused/);
  });
  await step(T('ipc-sender'), async () => {
    dialogQueue.push({ canceled: false, filePaths: [tmpA] });
    const before = dialogQueue.length;                       // taken after the push: the entry must still be there
    const probe = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, sandbox: true,
      preload: path.join(__dirname, 'probe-preload.js') } });
    await probe.loadURL('data:text/html,<p>probe</p>');
    const out = await probe.webContents.executeJavaScript(`window.probeInvoke('maker:pick-files').then(() => 'ok', () => 'rejected')`);
    probe.destroy();
    assert.equal(out, 'rejected');
    assert.equal(dialogQueue.length, before, 'the dialog stub must not have been consumed');
    dialogQueue.length = 0;
  });
  await step(T('guards on every web contents'), async () => {
    // a second web contents (not the main window) must get the navigation and window guards from web-contents-created
    const probe = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, sandbox: true } });
    await probe.loadURL('data:text/html,<p>second</p>');
    const url = probe.webContents.getURL();
    const opened = await probe.webContents.executeJavaScript(`window.open('http://example.invalid/') === null`);
    await probe.webContents.executeJavaScript(`location.href = 'http://example.invalid/'; 0`);
    await sleep(1000);
    const after = probe.webContents.getURL();
    probe.destroy();
    assert.equal(opened, true, 'window.open must be denied');
    assert.equal(after, url, 'will-navigate must keep the second contents where it is');
  });
  await step(T('request filter cancels what no other guard stops'), async () => {
    // a page with no CSP in the maker session (starting.html) asks a local listener for an image and a fetch
    const http = require('node:http');
    const seen = [];
    const srv = http.createServer((req, res) => { seen.push(req.url); res.end('x'); });
    await new Promise((r) => srv.listen(0, '127.0.0.1', r));
    const port = srv.address().port;
    const probe = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, sandbox: true, partition: 'maker' } });
    try {
      await probe.loadFile(path.join(__dirname, '..', 'starting.html'));
      const r = await probe.webContents.executeJavaScript(`new Promise((resolve) => {
        const img = new Image(); img.onload = img.onerror = () => resolve('img-done');
        img.src = 'http://127.0.0.1:${port}/img'; document.body.appendChild(img);
        fetch('http://127.0.0.1:${port}/fetch').catch(() => 0); })`);
      await sleep(700);
      assert.equal(r, 'img-done');
      assert.deepEqual(seen, [], 'the listener saw ' + seen.join(','));
    } finally { probe.destroy(); srv.close(); }
  });
  await step(T('renderer crash keeps the open job'), async () => {
    const boxes = messageBoxes.length;
    for (let i = 0; i < 2; i++) {                                // twice: a clean reload resets the "crashed twice" counter
      await handle.win.loadURL(handle.sidecar.origin + '/?job=' + jobA);
      await waitUntil(() => handle.win.webContents.getURL().includes('?job=' + jobA), 20000, 'job page');
      const reloaded = new Promise((resolve) => handle.win.webContents.once('did-finish-load', resolve));
      handle.win.webContents.forcefullyCrashRenderer();
      await Promise.race([reloaded, sleep(30000).then(() => { throw new Error('no reload after crash ' + i); })]);
      assert.ok(handle.win.webContents.getURL().includes('?job=' + jobA), 'url after crash ' + i + ': ' + handle.win.webContents.getURL());
    }
    assert.equal(messageBoxes.length, boxes, 'no "crashed twice" box');
  });
  await step(T('restart'), async () => {
    await handle.win.loadURL(handle.sidecar.origin + '/');
    fs.mkdirSync(path.join(outA, '.svf-maker-0123456789ab'), { recursive: true });
    const old = { pid: handle.sidecar.pid, token: handle.sidecar.token, port: handle.sidecar.port };
    const boxes = messageBoxes.length;
    process.kill(old.pid, 'SIGKILL');
    await waitUntil(() => messageBoxes.length > boxes, 20000, 'message box');
    await waitUntil(() => handle.sidecar.pid !== old.pid && handle.sidecar.port > 0 && handle.sidecar.pid > 0, 80000, 'new sidecar');
    assert.notEqual(handle.sidecar.token, old.token);
    tokens.push(handle.sidecar.token);
    await waitUntil(async () => (await run(handle, `return (await fetch('/api/caps')).status`).catch(() => 0)) === 200, 30000, 'caps after restart');
    pids.sidecar2 = handle.sidecar.pid;
  });
  await step(T('quit within the debounce keeps the handed-out folder'), async () => {
    const outE = mkdir(name, 'outE');
    dialogQueue.push({ canceled: false, filePaths: [outE] });
    await run(handle, `await window.svfMaker.pickOutputDir();`);
    await handle.shutdown();                                      // well inside the 500 ms save debounce
    const saved = JSON.parse(fs.readFileSync(path.join(ud, 'shell-state.json'), 'utf8'));
    assert.ok(saved.handedOut.includes(fs.realpathSync(outE)), JSON.stringify(saved.handedOut));
  });
  await step(T('log privacy'), async () => {
    const text = logText(handle);
    assert.equal(tokens.length, 2);
    for (const tok of tokens) assert.ok(tok && !text.includes(tok), 'a token is in the log');
    for (const d of [tmpA, tmpB, outA, outB, outC, outCLink, fs.realpathSync(tmpA), fs.realpathSync(outA), outD,
      path.join(TMP, name, 'sample'), path.join(REPO, 'ttf', 'neodgm')]) assert.ok(!text.includes(d), 'log has ' + d);
    assert.ok(!text.includes('/api/jobs/'));
    // the positive pin: the stub's stderr line (a path with spaces, a token) is in the log, redacted, for both sidecars
    const lines = text.split('\n').filter((l) => l.includes('sidecar stderr:'));
    assert.ok(lines.length >= 2, 'expected the redacted stderr line of both sidecars, got ' + lines.length);
    for (const l of lines) assert.match(l, /sidecar stderr: test-stderr: <path>$/);
    for (const frag of ['Secret', 'My Fonts', 'canary']) assert.ok(!text.includes(frag), 'log has ' + frag);
    assert.match(text, /pick-folder: 1/);
    assert.match(text, /sandbox renderer sandbox: off \(--no-sandbox; user namespaces \w+\)/);
    assert.match(text, /restart allowed/);
    assert.match(text, /stopped \d+ sidecar\(s\) in \d+ ms/);
  });
  for (const p of [pids.sidecar, pids.sidecar2]) {
    if (!p) continue;
    try { process.kill(p, 0); console.log('E2E NOTE pid ' + p + ' still exists (zombie or alive)'); } catch (e) { /* gone */ }
  }
}

// A sidecar that prints a port line for a dead port: the first page load fails; the shell must show its failure dialog,
// run the stop sequence on the child and end the app (here: the injected `fatal`), not die with a stack trace.
async function loadFailureCase() {
  const dir = mkdir('loadfail');
  const ud = mkdir('loadfail', 'ud');
  const launch = { mode: 'dev', cmd: 'sh', args: ['-c', 'echo "svf-maker listening on 127.0.0.1:1"; exec sleep 300'], repo: REPO, data: path.join(dir, 'data') };
  let fatal = 0;
  const boxes = messageBoxes.length;
  let pid = 0;
  await step('load failure: dialog, stop sequence, fatal', async () => {
    const handle = await require('../main.js').start({ userData: ud, quitOnClose: false, env: Object.assign({}, process.env, { SVF_MAKER_DEV: '1' }), launch,
      fatal: () => { fatal++; } });
    pid = handle.sidecar.pid;
    assert.ok(pid > 0, 'the stub never printed its port line');
    assert.equal(messageBoxes.length, boxes + 1, 'the failure dialog was not shown');
    assert.equal(fatal, 1, 'the app was not ended');
    await waitUntil(() => { try { process.kill(pid, 0); return false; } catch (e) { return true; } }, 5000, 'the stub to be stopped');
    handle.win.destroy();
  });
}

app.on('window-all-closed', () => {});            // pass 1 closes its window; the app must live on for pass 2
app.whenReady().then(async () => {
  const base = Object.assign({}, process.env);
  delete base.SVF_MAKER_DEV;
  await loadFailureCase();
  await pass('dev', { env: Object.assign({}, base, { SVF_MAKER_DEV: '1' }) });
  if (process.env.SVF_MAKER_SIDECAR && process.env.SVF_MAKER_STAGED_REPO) {
    const res = mkdir('res');
    for (const n of ['sidecar', 'repo']) { try { fs.rmSync(path.join(res, n), { recursive: true, force: true }); } catch (e) { /* none */ } }
    fs.mkdirSync(path.join(res, 'sidecar'), { recursive: true });
    fs.symlinkSync(path.dirname(process.env.SVF_MAKER_SIDECAR), path.join(res, 'sidecar', 'svf-maker-sidecar'));
    fs.symlinkSync(process.env.SVF_MAKER_STAGED_REPO, path.join(res, 'repo'));
    await pass('packaged', { resourcesPath: res, env: base });
  }
  console.log('E2E DONE pass=' + results.pass + ' fail=' + results.fail);
  app.exit(results.fail ? 1 : 0);
}).catch((e) => { console.log('E2E FAIL setup ' + (e && e.stack || e)); app.exit(1); });
