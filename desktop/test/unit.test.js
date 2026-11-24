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
// Scratch under TMP_DIR (else os.tmpdir(), which is TMPDIR), removed when the test ends.
const tmpDir = (t) => {
  const d = fs.mkdtempSync(path.join(process.env.TMP_DIR || os.tmpdir(), 'svf-unit-'));
  t.after(() => fs.rmSync(d, { recursive: true, force: true }));
  return d;
};

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
  const root = process.platform === 'win32' ? 'file:///C:' : 'file://';       // a file URL is a drive path on Windows
  const o = 'http://127.0.0.1:4000', s = root + '/app/starting.html';
  const opts = { startingUrl: s, devtools: false };
  for (const url of [o + '/', o + '/api/caps', s]) assert.equal(isOurs(o, url, opts), true, url);
  assert.equal(isOurs(o, 'data:,', opts), false, 'data: is never a navigation');                   // top-level: refused
  assert.equal(isOurs(o, 'data:,', { ...opts, subresource: true }), true);                       // the favicon request
  assert.equal(isOurs(o, root + '/a%20b/starting.html', { startingUrl: root + '/a b/starting.html' }), true);
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
  const { buildEnv, ENV_KEYS, PASS_KEYS, WINDOWS_KEYS } = lib('env.js');
  const parent = { ...process.env, SVF_MAKER_TOKEN: 'decoy', PYTHONPATH: '/x', SVF_RECOG_PYTHON: '/py',
    JAMOSET_MASK_FONT: '/f.ttf' };
  delete parent.JAMOSET_PYLIB;
  const { env, token } = buildEnv(parent, { repo: '/r', data: '/d' }, 'linux');
  for (const k of Object.keys(env)) assert.ok(ENV_KEYS.includes(k), k);
  // Windows: the interpreter's own keys pass too (SYSTEMROOT and the temp folders), PYTHONUTF8=1 is added, nothing else
  const w = buildEnv({ ...parent, SYSTEMROOT: 'C:\\Windows', TEMP: 'C:\\T', PYTHONHOME: 'C:\\x' }, { repo: '/r', data: '/d' }, 'win32').env;
  for (const k of Object.keys(w)) assert.ok(ENV_KEYS.includes(k) || WINDOWS_KEYS.includes(k), k);
  assert.deepEqual([w.SYSTEMROOT, w.TEMP, w.PYTHONUTF8, w.PYTHONHOME, w.PYTHONPATH], ['C:\\Windows', 'C:\\T', '1', undefined, undefined]);
  // a plain copy of a Windows environment keeps its own spellings: Path and SystemRoot are found all the same
  const m = buildEnv({ Path: 'C:\\bin', SystemRoot: 'C:\\Windows', SVF_RECOG_DIR: 'C:\\r' }, { repo: '/r', data: '/d' }, 'win32').env;
  assert.deepEqual([m.PATH, m.SYSTEMROOT, m.SVF_RECOG_DIR], ['C:\\bin', 'C:\\Windows', 'C:\\r']);
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
  // Windows: the clean stop is the end of stdin (the sidecar's --stop-on-eof), the escalation TerminateProcess
  const win = process.platform === 'win32';
  const code = win ? "process.stdin.on('end',()=>process.exit(0)); process.stdin.resume(); setInterval(()=>{},1e3)"
    : "process.on('SIGTERM',()=>process.exit(0)); setInterval(()=>{},1e3)";
  const a = spawn(process.execPath, ['-e', code], { detached: true, stdio: [win ? 'pipe' : 'ignore', 'ignore', 'ignore'] });
  await new Promise((r) => setTimeout(r, 300));
  const t0 = Date.now();
  const res = await stopSidecar(a, { termWaitS: 5, killWaitS: 2 });
  assert.equal(res.code, 0);
  assert.equal(res.escalated, false);
  assert.ok(Date.now() - t0 < 2500);
  const stubborn = spawn(process.execPath, ['-e', "process.on('SIGTERM',()=>{}); process.stdin.resume(); setInterval(()=>{},1e3)"],
    { detached: true, stdio: [win ? 'pipe' : 'ignore', 'ignore', 'ignore'] });
  await new Promise((r) => setTimeout(r, 300));
  const res2 = await stopSidecar(stubborn, { termWaitS: 0.3, killWaitS: 3 });
  assert.equal(res2.escalated, true);
  assert.equal(res2.signal, 'SIGKILL');                 // node reports TerminateProcess as the signal it was asked for
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
  const { metricSandboxText } = lib('sandbox.js');
  assert.equal(metricSandboxText({ pid: 1, sandboxed: true }, { noSandboxSwitch: false }), 'renderer sandbox: on');
  assert.equal(metricSandboxText({ pid: 1, sandboxed: false }, { noSandboxSwitch: true }), 'renderer sandbox: off (--no-sandbox)');
  assert.equal(metricSandboxText(undefined, { noSandboxSwitch: false }), 'renderer sandbox: unknown');
});

test('resolveLaunch', () => {
  const { resolveLaunch } = lib('paths.js');
  const base = { resourcesPath: '/res', appDir: '/co/desktop', env: {}, pid: 42, userData: '/ud', platform: 'linux' };
  const packaged = resolveLaunch({ ...base, exists: (p) => p === '/res/sidecar/svf-maker-sidecar/svf-maker-sidecar' });
  assert.deepEqual(packaged, { mode: 'packaged', cmd: '/res/sidecar/svf-maker-sidecar/svf-maker-sidecar',
    args: ['serve', '--exit-with-parent=42'], repo: '/res/repo', data: '/ud/maker' });
  const dev = resolveLaunch({ ...base, exists: () => false });
  assert.deepEqual(dev, { mode: 'dev', cmd: 'python3', args: ['-P', '/co/maker/server.py', '--exit-with-parent=42'],
    repo: '/co', data: '/ud/maker-dev' });
  const forced = resolveLaunch({ ...base, env: { SVF_MAKER_DEV: '1', SVF_MAKER_DEV_REPO: '/other' }, exists: () => true });
  assert.equal(forced.mode, 'dev');
  assert.equal(forced.repo, '/other');
  // Windows: the .exe, `python`, and --stop-on-eof (the shell's clean stop is the end of stdin)
  const wbase = { resourcesPath: 'C:\\res', appDir: 'C:\\co\\desktop', env: {}, pid: 42, userData: 'C:\\ud', platform: 'win32' };
  const wpack = resolveLaunch({ ...wbase, exists: (p) => p === 'C:\\res\\sidecar\\svf-maker-sidecar\\svf-maker-sidecar.exe' });
  assert.deepEqual(wpack, { mode: 'packaged', cmd: 'C:\\res\\sidecar\\svf-maker-sidecar\\svf-maker-sidecar.exe',
    args: ['serve', '--exit-with-parent=42', '--stop-on-eof'], repo: 'C:\\res\\repo', data: 'C:\\ud\\maker' });
  const wdev = resolveLaunch({ ...wbase, exists: () => false });
  assert.deepEqual(wdev, { mode: 'dev', cmd: 'python', args: ['-P', 'C:\\co\\maker\\server.py', '--exit-with-parent=42', '--stop-on-eof'],
    repo: 'C:\\co', data: 'C:\\ud\\maker-dev' });
});

test('log rotation, redaction, ring', (t) => {
  const { createLog, pathsLine, redactLine, Ring } = lib('log.js');
  const dir = tmpDir(t);
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

test('state keeps only the four keys', (t) => {
  const { loadState, saveState } = lib('state.js');
  const f = path.join(tmpDir(t), 'shell-state.json');
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

test('redactLine hides whole path fields, names and tokens', () => {
  const { redactLine } = lib('log.js');
  assert.equal(redactLine('sweep: /home/u/Customer Secret/out/.svf-maker-0123456789ab: PermissionError'), 'sweep: <path>');
  assert.equal(redactLine('File "/home/u/My Fonts/Secret Project/x.py", line 3'), 'File "<path>');
  assert.equal(redactLine("open '/a b/c d' failed"), "open '<path>");
  assert.equal(redactLine('x=/Users/me/Fonts Folder/a.ttf'), 'x=<path>');
  assert.equal(redactLine('see ~/Private Stuff/out'), 'see <path>');
  assert.equal(redactLine('mkfont: Korean_Contract_2026.ttf: bad table'), 'mkfont: <file>: bad table');
  assert.equal(redactLine('token ' + 'ab'.repeat(16) + ' end'), 'token <hex> end');
  assert.equal(redactLine('plain message 12'), 'plain message 12');
});

test('state: bounds keep only finite numbers of the four window keys', (t) => {
  const { loadState } = lib('state.js');
  const f = path.join(tmpDir(t), 'shell-state.json');
  fs.writeFileSync(f, JSON.stringify({ bounds: { x: 1, y: 2, width: 300, height: 'big', webPreferences: { sandbox: false },
    preload: '/evil.js' }, zoom: 1.2 }));
  assert.deepEqual(loadState(f).bounds, { x: 1, y: 2, width: 300 });
  fs.writeFileSync(f, JSON.stringify({ bounds: { webPreferences: {} } }));
  assert.equal(loadState(f).bounds, null);
});

// ---- the sidecar supervisor with stub sidecars (no Electron) ------------------------------------------------------
function stubSidecar(t, body) {
  const f = path.join(tmpDir(t), 'stub.js');
  fs.writeFileSync(f, body);
  return f;
}
function supervisorFor(t, stubFile, extra = {}) {
  const { createSupervisor } = lib('supervisor.js');
  const { createLog } = lib('log.js');
  const dir = tmpDir(t);
  const log = createLog({ dir, toStderr: false });
  const launch = { mode: 'dev', cmd: process.execPath, args: [stubFile], repo: '/r', data: '/d' };
  const sup = createSupervisor({ launch, parentEnv: { PATH: process.env.PATH, HOME: process.env.HOME }, log, handshakeS: 30,
    termWaitS: 0.4, killWaitS: 3, busyRetryS: 0, ...extra });
  sup.logText = () => fs.readFileSync(log.path, 'utf8');
  t.after(async () => {
    for (const c of sup.children) {
      try { if (process.platform === 'win32') c.kill('SIGKILL'); else process.kill(-c.pid, 'SIGKILL'); } catch (e) { /* gone */ }
    }
  });
  return sup;
}
const alive = (pid) => {
  if (process.platform === 'win32') {                   // no /proc: signal 0 asks whether the process exists
    try { process.kill(pid, 0); return true; } catch (e) { return false; }
  }
  try {
    const st = fs.readFileSync('/proc/' + pid + '/stat', 'utf8');
    const state = st.slice(st.lastIndexOf(')') + 2).split(' ')[0];
    return state !== 'Z' && state !== 'X';
  } catch (e) { return false; }
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test('supervisor: quitting before the handshake stops the pending child (SIGTERM-ignoring included)', async (t) => {
  for (const ignore of [false, true]) {
    const stub = stubSidecar(t, (ignore ? "process.on('SIGTERM', () => {});" : '') + 'setInterval(() => {}, 1000);');
    const sup = supervisorFor(t, stub);
    const started = sup.start();
    const outcome = started.then(() => 'started', (e) => e);
    await sleep(400);
    assert.equal(sup.children.size, 1, 'the pending child is tracked from the spawn');
    const pid = [...sup.children][0].pid;
    assert.ok(alive(pid));
    await sup.stopAll();
    const e = await outcome;
    assert.equal(e.cancelled, true, String(e));
    assert.equal(alive(pid), false, 'the pending child outlived the quit (ignore SIGTERM: ' + ignore + ')');
  }
});

test('supervisor: start refuses once the failure path has run (a Restart click behind the failure dialog spawns nothing)', async (t) => {
  const stub = stubSidecar(t, "console.log('svf-maker listening on 127.0.0.1:' + 4000); setInterval(() => {}, 1000);");
  const sup = supervisorFor(t, stub);
  await sup.cleanupAfterFailure(new Error('the first page load failed'));
  assert.equal(sup.failing, true);
  let err = null;
  try { await sup.start(); } catch (e) { err = e; }
  assert.ok(err && err.cancelled === true, 'start() must be cancelled while failing, got ' + err);
  assert.equal(sup.children.size, 0, 'no child may be spawned while failing');
});

test('supervisor: a replacement that never answers and ignores SIGTERM is stopped by the one failure path', async (t) => {
  const stub = stubSidecar(t, "process.on('SIGTERM', () => {}); setInterval(() => {}, 1000);");
  const sup = supervisorFor(t, stub, { handshakeS: 0.5 });
  let err = null;
  try { await sup.start(); } catch (e) { err = e; }
  assert.match(err.message, /did not start within/);
  const pid = err.child.pid;
  assert.ok(alive(pid));
  await sup.cleanupAfterFailure(err);
  assert.equal(alive(pid), false);
});

test('supervisor: an unterminated last stderr line reaches the ring and the log, redacted', async (t) => {
  const stub = stubSidecar(t, "process.stderr.write('first\\nlast words /home/u/My Fonts/out', () => process.exit(1));");
  const sup = supervisorFor(t, stub);
  let err = null;
  try { await sup.start(); } catch (e) { err = e; }
  assert.match(err.message, /exited before it was ready \(exit 1\)/);
  assert.deepEqual(err.ring.lines(), ['first', 'last words /home/u/My Fonts/out']);
  const text = sup.logText();
  assert.match(text, /sidecar stderr: last words <path>/);
  assert.ok(!text.includes('My Fonts'));
});

test('supervisor: a data root still locked by a dying sidecar is retried, then given up', async (t) => {
  const { BUSY_MESSAGE } = lib('supervisor.js');
  const counter = path.join(tmpDir(t), 'n');
  const stub = stubSidecar(t, `const fs = require('fs'); let n = 0; try { n = Number(fs.readFileSync(${JSON.stringify(counter)}, 'utf8')); } catch (e) {}
    fs.writeFileSync(${JSON.stringify(counter)}, String(n + 1));
    if (n < 2) { process.stderr.write(${JSON.stringify(BUSY_MESSAGE)} + '\\n', () => process.exit(2)); }
    else { console.log('svf-maker listening on 127.0.0.1:4321'); setInterval(() => {}, 1000); }`);
  const sup = supervisorFor(t, stub, { busyRetryS: 10 });
  const sc = await sup.start();
  assert.equal(sc.port, 4321);
  assert.match(sup.logText(), /data root is still in use, retrying/);
  await sup.stopAll();
  const always = stubSidecar(t, `process.stderr.write(${JSON.stringify(BUSY_MESSAGE)} + '\\n', () => process.exit(2));`);
  const sup2 = supervisorFor(t, always, { busyRetryS: 2 });
  const t0 = Date.now();
  let err = null;
  try { await sup2.start(); } catch (e) { err = e; }
  assert.equal(err.busy, true);
  assert.ok(Date.now() - t0 >= 1900 && Date.now() - t0 < 8000);
});

test('supervisor: a command that cannot be spawned (ENOENT, EACCES) fails cleanly, with nothing to stop', async (t) => {
  const dir = tmpDir(t);
  const noexec = path.join(dir, 'not-executable');
  fs.writeFileSync(noexec, '#!/bin/sh\nexit 0\n', { mode: 0o644 });
  // a file without the execute bit (EACCES) is POSIX only: Windows has no such bit
  const cases = [[path.join(dir, 'missing'), 'ENOENT']].concat(process.platform === 'win32' ? [] : [[noexec, 'EACCES']]);
  for (const [cmd, code] of cases) {
    const { createSupervisor } = lib('supervisor.js');
    const { createLog } = lib('log.js');
    const log = createLog({ dir: tmpDir(t), toStderr: false });
    const sup = createSupervisor({ launch: { mode: 'packaged', cmd, args: [], repo: '/r', data: '/d' }, parentEnv: { PATH: process.env.PATH },
      log, handshakeS: 30, termWaitS: 0.4, killWaitS: 2, busyRetryS: 0 });
    let err = null;
    try { await sup.start(); } catch (e) { err = e; }
    assert.match(err.message, new RegExp('could not start the maker: ' + code));
    await sup.cleanupAfterFailure(err);                  // must not throw (it used to: kill(-undefined))
    await sup.stopAll();
  }
});

test('stopSidecar: a child that never spawned resolves at once', async () => {
  const { stopSidecar } = lib('shutdown.js');
  const res = await stopSidecar({ pid: undefined, exitCode: null, signalCode: null, once() {} }, { termWaitS: 5, killWaitS: 5 });
  assert.equal(res.escalated, false);
});

test('redactLine: drive-like, URL-like and relative paths, and a path after a colon', () => {
  const { redactLine } = lib('log.js');
  assert.equal(redactLine('error:/home/u/My Fonts/x'), '<path>');
  assert.equal(redactLine('open C:\\Users\\me\\My Fonts\\a.ttf failed'), 'open <path>');
  assert.equal(redactLine('open D:/Fonts Dir/a failed'), 'open <path>');
  assert.equal(redactLine('GET file:///home/u/My Fonts/x'), 'GET <path>');
  assert.equal(redactLine('read fonts/My Secret/x.ttf'), 'read <path>');
  assert.equal(redactLine('rel ../My Secret/x'), 'rel <path>');
  assert.equal(redactLine('plain message 12'), 'plain message 12');
});

test('supervisor: the failure path stopping an established child is not offered as a crash restart', async (t) => {
  const stub = stubSidecar(t, "console.log('svf-maker listening on 127.0.0.1:4321'); setInterval(() => {}, 1000);");
  const calls = [];
  const sup = supervisorFor(t, stub, { onUnexpectedExit: (...a) => calls.push(a) });
  const sc = await sup.start();
  const pid = sc.pid;
  await sup.cleanupAfterFailure(new Error('page did not load'));
  await sleep(300);
  assert.equal(alive(pid), false);
  assert.deepEqual(calls, []);
  // while an unexpected exit of a healthy sidecar still reports
  const sup2 = supervisorFor(t, stub, { onUnexpectedExit: (...a) => calls.push(a) });
  const sc2 = await sup2.start();
  process.kill(sc2.pid, 'SIGKILL');
  await sleep(500);
  assert.equal(calls.length, 1);
});
