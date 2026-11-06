'use strict';
// Electron end-to-end test (main script): runs the real main.js with stubbed dialogs under xvfb. Prints
// "E2E PASS <name>" / "E2E FAIL <name> <message>", exits 1 on any failure. Pass 1: the development sidecar
// (python3 maker/server.py); pass 2 (SVF_MAKER_SIDECAR + SVF_MAKER_STAGED_REPO): the packaged layout.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
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
  const handle = await main.start(Object.assign({ userData: ud, quitOnClose: false }, opts));
  const pids = { shell: process.pid, sidecar: handle.sidecar.pid };
  const tmpA = mkdir(name, 'tmpA'), tmpB = mkdir(name, 'tmpB'), outA = mkdir(name, 'outA'), outB = mkdir(name, 'outB');
  const outC = mkdir(name, 'realparent', 'outC'), outD = mkdir(name, 'outD');
  // the dialog hands out a path through a symlinked parent (the server refuses a symlink as the folder itself)
  const outCLink = path.join(TMP, name, 'linkparent', 'outC');
  fs.symlinkSync(path.join(TMP, name, 'realparent'), path.join(TMP, name, 'linkparent'));
  for (const d of [tmpA, tmpB]) fs.copyFileSync(path.join(REPO, 'ttf', 'neodgm', 'neodgm.ttf'), path.join(d, 'neodgm.ttf'));
  const T = (n) => name + ': ' + n;
  let jobA = null, jobB = null, jobC = null;

  await step(T('handshake'), async () => {
    await waitUntil(() => handle.sidecar.port > 0, 75000, 'port');
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
    const before = dialogQueue.length;
    dialogQueue.push({ canceled: false, filePaths: [tmpA] });
    const probe = new BrowserWindow({ show: false, webPreferences: { partition: 'maker', contextIsolation: true, sandbox: true,
      preload: path.join(__dirname, 'probe-preload.js') } });
    await probe.loadURL('data:text/html,<p>probe</p>');
    const out = await probe.webContents.executeJavaScript(`window.probeInvoke('maker:pick-files').then(() => 'ok', () => 'rejected')`);
    probe.destroy();
    assert.equal(out, 'rejected');
    assert.equal(dialogQueue.length, before + 1, 'the dialog stub was consumed');
    dialogQueue.length = 0;
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
    await waitUntil(async () => (await run(handle, `return (await fetch('/api/caps')).status`).catch(() => 0)) === 200, 30000, 'caps after restart');
    pids.sidecar2 = handle.sidecar.pid;
  });
  await step(T('log privacy'), async () => {
    const text = logText(handle);
    assert.ok(!text.includes(handle.sidecar.token));
    for (const d of [tmpA, tmpB, outA, outB, outC, outCLink, fs.realpathSync(tmpA), fs.realpathSync(outA), outD]) assert.ok(!text.includes(d), 'log has ' + d);
    assert.ok(!text.includes('/api/jobs/'));
    assert.ok(!text.includes('sweep: /'));
    for (const l of text.split('\n').filter((x) => x.includes('sidecar stderr:'))) assert.ok(!/\/\w/.test(l.split('sidecar stderr:')[1]), 'unredacted sidecar line: ' + l);
    assert.match(text, /pick-folder: 1/);
    assert.match(text, /sandbox renderer sandbox: off \(--no-sandbox; user namespaces \w+\)/);
  });
  await handle.shutdown();
  for (const p of [pids.sidecar, pids.sidecar2]) {
    if (!p) continue;
    try { process.kill(p, 0); console.log('E2E NOTE pid ' + p + ' still exists (zombie or alive)'); } catch (e) { /* gone */ }
  }
}

app.on('window-all-closed', () => {});            // pass 1 closes its window; the app must live on for pass 2
app.whenReady().then(async () => {
  const base = Object.assign({}, process.env);
  delete base.SVF_MAKER_DEV;
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
