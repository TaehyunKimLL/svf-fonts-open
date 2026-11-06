'use strict';
// Unit tests of the shell's pure helpers (no Electron): node --test test/unit.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');

const lib = (name) => require(path.join(__dirname, '..', 'lib', name));
const REPO = path.join(__dirname, '..', '..');
const tmpDir = () => fs.mkdtempSync(path.join(os.tmpdir(), 'svf-unit-'));   // os.tmpdir() is TMP_DIR (TMPDIR)

test('parsePortLine', () => {
  const { parsePortLine } = lib('portline.js');
  assert.deepEqual(parsePortLine('svf-maker listening on 127.0.0.1:38253\n'), { host: '127.0.0.1', port: 38253 });
  assert.equal(parsePortLine('svf-maker listening on 127.0.0.1:382'), null);          // no newline yet
  assert.equal(parsePortLine('noise\nsvf-maker listening on 127.0.0.1:5\nmore\n').port, 5);
  assert.deepEqual(parsePortLine('svf-maker listening on ::1:9\n'), { host: '::1', port: 9 });
  assert.equal(parsePortLine('svf-maker listening on 0.0.0.0:9\n'), null);
});

test('isOurs', () => {
  const { isOurs } = lib('guard.js');
  const o = 'http://127.0.0.1:4000', s = 'file:///app/starting.html';
  const opts = { startingUrl: s, devtools: false };
  for (const url of [o + '/', o + '/api/caps', s, 'data:,']) assert.equal(isOurs(o, url, opts), true, url);
  for (const url of ['http://127.0.0.1:4001/', 'http://localhost:4000/', o, 'http://127.0.0.1:4000.evil/',
    'file:///etc/passwd', 'devtools://devtools/x']) assert.equal(isOurs(o, url, opts), false, url);
  assert.equal(isOurs(o, 'devtools://devtools/x', { startingUrl: s, devtools: true }), true);
});

test('withToken', () => {
  const { withToken } = lib('guard.js');
  const sc = { origin: 'http://127.0.0.1:4000', token: 'a'.repeat(32) };
  const evil = { 'x-maker-token': 'evil', 'X-MAKER-TOKEN': 'evil2', Accept: '*/*' };
  const h = withToken(sc.origin + '/api/x', evil, sc);
  const keys = Object.keys(h).filter((k) => /x-maker-token/i.test(k));
  assert.equal(keys.length, 1);
  assert.equal(h[keys[0]], sc.token);
  assert.equal(h.Accept, '*/*');
  assert.ok('x-maker-token' in evil, 'the input is not modified');
  for (const url of [sc.origin + '/', sc.origin + '/static/maker.js', 'http://127.0.0.1:4001/api/x']) {
    assert.deepEqual(Object.keys(withToken(url, evil, sc)).filter((k) => /x-maker-token/i.test(k)), [], url);
  }
});

test('buildEnv', () => {
  const { buildEnv, ENV_KEYS, PASS_KEYS } = lib('env.js');
  const parent = { ...process.env, SVF_MAKER_TOKEN: 'decoy', PYTHONPATH: '/x', SVF_RECOG_PYTHON: '/py',
    JAMOSET_MASK_FONT: '/f.ttf' };
  delete parent.JAMOSET_PYLIB;
  const { env, token } = buildEnv(parent, { repo: '/r', data: '/d' });
  for (const k of Object.keys(env)) assert.ok(ENV_KEYS.includes(k), k);
  assert.match(token, /^[0-9a-f]{32}$/);
  assert.notEqual(token, 'decoy');
  assert.equal(env.SVF_MAKER_TOKEN, token);
  assert.equal(env.PYTHONPATH, undefined);
  assert.equal(env.SVF_RECOG_PYTHON, '/py');
  assert.equal(env.JAMOSET_MASK_FONT, '/f.ttf');
  assert.equal(env.JAMOSET_PYLIB, undefined);
  assert.equal(buildEnv({ ...parent, JAMOSET_PYLIB: '' }, { repo: '/r', data: '/d' }).env.JAMOSET_PYLIB, undefined);
  assert.notEqual(buildEnv(parent, { repo: '/r', data: '/d' }).token, token);
  assert.deepEqual([env.SVF_MAKER_BIND, env.LANG, env.SVF_MAKER_REPO, env.SVF_MAKER_DATA], ['127.0.0.1:0', 'C.UTF-8', '/r', '/d']);
  assert.deepEqual(PASS_KEYS, ENV_KEYS.slice(-5));
  assert.ok(ENV_KEYS.includes('JAMOSET_MASK_FONT'));
});

test('budget derives from the server', () => {
  const b = lib('budget.js');
  assert.equal(b.HANDSHAKE_S, 75);
  assert.ok(b.HANDSHAKE_S >= b.SERVER.startupCleanupS + b.SERVER.recogProbeS + b.SERVER.reapTotalS);
  assert.equal(b.STOP_WAIT_S, 45);
  assert.ok(b.STOP_WAIT_S >= b.SERVER.stopTimeoutS + b.SERVER.joinS + b.SERVER.stopSweepS);
  const read = (f) => fs.readFileSync(path.join(REPO, 'maker', f), 'utf8');
  assert.equal(Number(/^STARTUP_CLEANUP_S = ([\d.]+)/m.exec(read('server.py'))[1]), b.SERVER.startupCleanupS);
  assert.equal(Number(/^STOP_SWEEP_TOTAL_S = ([\d.]+)/m.exec(read('jobs.py'))[1]), b.SERVER.stopSweepS);
  assert.equal(Number(/def stop\(self, timeout=(\d+)\)/.exec(read('jobs.py'))[1]), b.SERVER.stopTimeoutS);
  assert.equal(Number(/^RECOG_PROBE_S = (\d+)/m.exec(read('caps.py'))[1]), b.SERVER.recogProbeS);
  assert.equal(Number(/^REAP_TOTAL_S = ([\d.]+)/m.exec(read('toolreg.py'))[1]), b.SERVER.reapTotalS);
  assert.equal(b.KILL_WAIT_S, 5);
  assert.equal(b.STARTING_PAGE_S, 2);
});

test('stopSidecar', async () => {
  const { stopSidecar } = lib('shutdown.js');
  const code = "process.on('SIGTERM',()=>process.exit(0)); setInterval(()=>{},1e3)";
  const a = spawn(process.execPath, ['-e', code], { detached: true, stdio: 'ignore' });
  await new Promise((r) => setTimeout(r, 300));
  const t0 = Date.now();
  const res = await stopSidecar(a, { termWaitS: 5, killWaitS: 2 });
  assert.equal(res.code, 0);
  assert.equal(res.escalated, false);
  assert.ok(Date.now() - t0 < 2500);
  const stubborn = spawn(process.execPath, ['-e', "process.on('SIGTERM',()=>{}); setInterval(()=>{},1e3)"],
    { detached: true, stdio: 'ignore' });
  await new Promise((r) => setTimeout(r, 300));
  const res2 = await stopSidecar(stubborn, { termWaitS: 0.3, killWaitS: 3 });
  assert.equal(res2.escalated, true);
  assert.equal(res2.signal, 'SIGKILL');
  const t1 = Date.now();
  const res3 = await stopSidecar(a, { termWaitS: 5, killWaitS: 2 });          // already exited
  assert.ok(Date.now() - t1 < 200);
  assert.equal(res3.escalated, false);
});

test('restartAllowed', () => {
  const { restartAllowed } = lib('restart.js');
  const t = 1e6;
  assert.equal(restartAllowed([], t), true);
  assert.equal(restartAllowed([t - 1, t - 2], t), true);
  assert.equal(restartAllowed([t - 1, t - 2, t - 3], t), false);
  assert.equal(restartAllowed([t - 400000, t - 500000, t - 600000], t), true);
});

test('readSandbox / sandboxText', () => {
  const { readSandbox, sandboxText } = lib('sandbox.js');
  assert.deepEqual(readSandbox(1, () => 'Name:\tx\nSeccomp:\t0\nNoNewPrivs:\t1\n'), { seccomp: 0, noNewPrivs: 1 });
  assert.equal(readSandbox(1, () => { throw new Error('x'); }), null);
  assert.equal(sandboxText({ seccomp: 0 }, { noSandboxSwitch: true, userns: 'unavailable' }),
    'renderer sandbox: off (--no-sandbox; user namespaces unavailable)');
  assert.equal(sandboxText({ seccomp: 2 }, { noSandboxSwitch: false, userns: 'available' }), 'renderer sandbox: on');
  assert.equal(sandboxText(null, { noSandboxSwitch: false, userns: 'unknown' }), 'renderer sandbox: unknown');
});

test('resolveLaunch', () => {
  const { resolveLaunch } = lib('paths.js');
  const base = { resourcesPath: '/res', appDir: '/co/desktop', env: {}, pid: 42, userData: '/ud' };
  const packaged = resolveLaunch({ ...base, exists: (p) => p === '/res/sidecar/svf-maker-sidecar/svf-maker-sidecar' });
  assert.deepEqual(packaged, { mode: 'packaged', cmd: '/res/sidecar/svf-maker-sidecar/svf-maker-sidecar',
    args: ['serve', '--exit-with-parent=42'], repo: '/res/repo', data: '/ud/maker' });
  const dev = resolveLaunch({ ...base, exists: () => false });
  assert.deepEqual(dev, { mode: 'dev', cmd: 'python3', args: ['-P', '/co/maker/server.py', '--exit-with-parent=42'],
    repo: '/co', data: '/ud/maker-dev' });
  const forced = resolveLaunch({ ...base, env: { SVF_MAKER_DEV: '1', SVF_MAKER_DEV_REPO: '/other' }, exists: () => true });
  assert.equal(forced.mode, 'dev');
  assert.equal(forced.repo, '/other');
});

test('log rotation, redaction, ring', () => {
  const { createLog, pathsLine, redactLine, Ring } = lib('log.js');
  const dir = tmpDir();
  const log = createLog({ dir, toStderr: false, maxBytes: 100 });
  for (let i = 0; i < 3; i++) log.line('x'.repeat(60 + i));
  assert.deepEqual(fs.readdirSync(dir).sort(), ['shell.log', 'shell.log.1']);
  assert.equal(pathsLine('pick-files', ['/home/u/a.ttf', '/b']), 'pick-files: 2');
  assert.equal(redactLine('sweep: /home/u/out/.svf-maker-0123456789ab'), 'sweep: <path>');
  assert.equal(redactLine('tok ' + 'a'.repeat(32)), 'tok <hex>');
  assert.equal(redactLine('y'.repeat(500)).length, 300);
  const ring = new Ring(50);
  for (let i = 0; i < 60; i++) ring.push('l' + i);
  assert.equal(ring.lines().length, 50);
  assert.equal(ring.lines()[0], 'l10');
});

test('state keeps only the four keys', () => {
  const { loadState, saveState } = lib('state.js');
  const f = path.join(tmpDir(), 'shell-state.json');
  assert.deepEqual(Object.keys(loadState(f)).sort(), ['bounds', 'handedOut', 'lastOutputDir', 'zoom']);
  const paths = Array.from({ length: 40 }, (_, i) => '/o/' + i);
  saveState(f, { zoom: 1.1, token: 'x', lastInputDir: '/in', handedOut: paths, bounds: { width: 3 }, lastOutputDir: '/o/39' });
  const raw = fs.readFileSync(f, 'utf8');
  assert.ok(!raw.includes('token') && !raw.includes('lastInputDir'));
  const st = loadState(f);
  assert.equal(st.handedOut.length, 32);
  assert.equal(st.handedOut[31], '/o/39');
  fs.writeFileSync(f, '{bad');
  assert.equal(loadState(f).zoom, 1);
});

function jsFiles(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name === 'node_modules' || e.name === 'test' || e.name === 'build' || e.name === 'dist' || e.name === 'spike') continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...jsFiles(p));
    else if (/\.(js|mjs)$/.test(e.name)) out.push(p);
  }
  return out;
}

test('no outbound code (spec 6.9)', () => {
  const files = jsFiles(path.join(__dirname, '..'));
  assert.ok(files.length >= 10);
  for (const f of files) {
    const text = fs.readFileSync(f, 'utf8');
    for (const m of ['electron-updater', 'http', 'https', 'net']) {
      assert.ok(!new RegExp(`require\\(['"](node:)?${m}['"]\\)`).test(text), `${f} requires ${m}`);
    }
    assert.ok(!/autoUpdater/.test(text), f + ' autoUpdater');
    assert.ok(!/XMLHttpRequest/.test(text), f + ' XMLHttpRequest');
    assert.ok(!/fetch\(\s*['"`]http/.test(text), f + ' fetch of an absolute URL');
  }
});

test('versions agree', () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));
  const py = /^VERSION = "([^"]+)"/m.exec(fs.readFileSync(path.join(REPO, 'maker', 'sidecar.py'), 'utf8'))[1];
  assert.equal(pkg.version, py);
});
