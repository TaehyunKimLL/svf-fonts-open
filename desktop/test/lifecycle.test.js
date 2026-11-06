'use strict';
// Process lifecycle of the real shell under xvfb: node --test test/lifecycle.test.js (needs TMP_DIR; run under the
// browser lock and heavy, see the plan's G5). One Electron instance at a time (two only in the second-instance case).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');                                    // a test, not shipped code: the no-outbound scan skips test/
const { spawn, spawnSync } = require('node:child_process');

const DESKTOP = path.join(__dirname, '..');
const ELECTRON = path.join(DESKTOP, 'node_modules', '.bin', 'electron');
const TMP = process.env.TMP_DIR || os.tmpdir();
const have = spawnSync('which', ['xvfb-run']).status === 0 && fs.existsSync(ELECTRON);
const skip = have ? false : 'xvfb-run or the electron binary is missing';
const STOP_WAIT_S = 45;
const baseEnv = () => { const e = Object.assign({}, process.env); delete e.NODE_TEST_CONTEXT; return e; };   // node --test marks its children

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function alive(pid) {
  try {
    const stat = fs.readFileSync('/proc/' + pid + '/stat', 'utf8');
    const state = stat.slice(stat.lastIndexOf(')') + 2).split(' ')[0];
    return state !== 'Z' && state !== 'X';
  } catch (e) { return false; }
}
async function until(fn, ms, what) {
  const end = Date.now() + ms;
  for (;;) { const v = await fn(); if (v) return v; if (Date.now() > end) throw new Error('timeout: ' + what); await sleep(100); }
}

function launch(name, extraEnv = {}) {
  const dir = path.join(TMP, 'lc-' + name);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
  const env = Object.assign(baseEnv(), { SVF_MAKER_DEV: '1', SVF_MAKER_SHELL_LOG: 'stderr', TMPDIR: TMP }, extraEnv);
  const child = spawn('xvfb-run', ['-a', ELECTRON, '--no-sandbox', '--disable-gpu', DESKTOP, '--user-data-dir=' + dir],
    { env, stdio: ['ignore', 'pipe', 'pipe'], detached: true });
  const run = { child, dir, out: '', err: '', exited: null };
  child.stdout.on('data', (d) => { run.out += d; });
  child.stderr.on('data', (d) => { run.err += d; });
  child.on('exit', (code, signal) => { run.exited = { code, signal }; });
  run.all = () => run.out + run.err;           // Electron's main process writes its stderr to the stdout pipe on Linux
  run.shellPid = () => { const m = /shell pid=(\d+)/.exec(run.all()); return m ? Number(m[1]) : 0; };
  run.sidecarPid = () => { const m = /sidecar start mode=\w+ pid=(\d+)/.exec(run.all()); return m ? Number(m[1]) : 0; };
  run.port = () => { const m = /sidecar port=(\d+)/.exec(run.all()); return m ? Number(m[1]) : 0; };
  run.cleanup = () => { try { process.kill(-child.pid, 'SIGKILL'); } catch (e) { /* gone */ } for (const p of [run.shellPid(), run.sidecarPid()]) { if (p && alive(p)) { try { process.kill(p, 'SIGKILL'); } catch (e) { /* gone */ } } } };
  return run;
}

test('close: smoke ok, sidecar exit 0, nothing left', { skip, timeout: 240000 }, async (t) => {
  const run = launch('close', { SVF_MAKER_SMOKE: '1' });
  t.after(run.cleanup);
  await until(() => run.exited, 150000, 'the shell to exit');
  assert.match(run.out, /svf-maker smoke ok SVF maker/);
  assert.match(run.all(), /sidecar exit code=0/);
  await sleep(300);
  assert.equal(alive(run.sidecarPid()), false);
  assert.equal(alive(run.shellPid()), false);
});

test('SIGTERM to the shell stops the sidecar', { skip, timeout: 240000 }, async (t) => {
  const run = launch('term');
  t.after(run.cleanup);
  await until(() => run.port(), 100000, 'port line');
  const t0 = Date.now();
  process.kill(run.shellPid(), 'SIGTERM');
  await until(() => run.exited, (STOP_WAIT_S + 5) * 1000, 'the shell to exit');
  assert.match(run.all(), /sidecar exit code=0/);
  assert.ok(Date.now() - t0 < (STOP_WAIT_S + 5) * 1000);
  assert.equal(alive(run.sidecarPid()), false);
});

function apiCall(port, token, method, pathname, body) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port, method, path: pathname, headers: { 'X-Maker-Token': token, 'Content-Length': Buffer.byteLength(body || '') } }, (res) => {
      let data = '';
      res.on('data', (d) => { data += d; });
      res.on('end', () => resolve({ status: res.statusCode, body: data }));
    });
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

test('SIGKILL of the shell: the sidecar exits by itself', { skip, timeout: 240000 }, async (t) => {
  // the token is the shell's own secret; this test reads it from the sidecar's environment to create a local job
  const run = launch('kill9');
  t.after(run.cleanup);
  await until(() => run.port(), 100000, 'port line');
  const sidecar = run.sidecarPid();
  const token = /SVF_MAKER_TOKEN=([0-9a-f]{32})/.exec(fs.readFileSync('/proc/' + sidecar + '/environ', 'latin1').split('\0').join('\n'))[1];
  const out = path.join(TMP, 'lc-kill9-out');
  fs.rmSync(out, { recursive: true, force: true });
  fs.mkdirSync(out, { recursive: true });
  const created = await apiCall(run.port(), token, 'POST', '/api/jobs', JSON.stringify({ source: 'local', output_dir: out }));
  assert.equal(created.status, 200, created.body);
  const jobId = JSON.parse(created.body).id;
  const src = path.join(TMP, 'lc-kill9-src');
  fs.mkdirSync(src, { recursive: true });
  fs.copyFileSync(path.join(DESKTOP, '..', 'ttf', 'neodgm', 'neodgm.ttf'), path.join(src, 'neodgm.ttf'));
  const put = await apiCall(run.port(), token, 'PUT', '/api/jobs/' + jobId + '/sources', JSON.stringify({ paths: [src] }));
  assert.equal(put.status, 200, put.body);
  const det = await apiCall(run.port(), token, 'POST', '/api/jobs/' + jobId + '/detect');
  assert.equal(det.status, 200, det.body);
  const filesDir = path.join(out, '.svf-maker-' + jobId);
  assert.ok(fs.existsSync(filesDir));
  process.kill(run.shellPid(), 'SIGKILL');
  await until(() => !alive(sidecar), 8000, 'the sidecar to exit by itself');
  await until(() => !fs.existsSync(filesDir), 8000, 'the job files directory to be swept');
});

test('second instance quits at once', { skip, timeout: 240000 }, async (t) => {
  const first = launch('second', { SVF_MAKER_SMOKE: '0' });
  t.after(first.cleanup);
  await until(() => first.port(), 100000, 'port line');
  // the second launch uses the same user-data-dir
  const env = Object.assign(baseEnv(), { SVF_MAKER_DEV: '1', SVF_MAKER_SHELL_LOG: 'stderr', TMPDIR: TMP });
  const second = spawn('xvfb-run', ['-a', ELECTRON, '--no-sandbox', '--disable-gpu', DESKTOP, '--user-data-dir=' + first.dir],
    { env, stdio: ['ignore', 'pipe', 'pipe'], detached: true });
  let secondErr = '';
  second.stdout.on('data', (d) => { secondErr += d; });
  let secondExit = null;
  second.stderr.on('data', (d) => { secondErr += d; });
  second.on('exit', (c) => { secondExit = c; });
  // sample the task count of every process that carries this test's user-data-dir while both instances run
  let peak = 0;
  const sample = () => {
    const n = spawnSync('ps', ['-eLo', 'args']).stdout.toString().split('\n').filter((l) => l.includes('--user-data-dir=' + first.dir)).length;
    if (n > peak) peak = n;
  };
  sample();
  const sampler = setInterval(sample, 250);
  try {
    await until(() => secondExit !== null, 5000 + 25000, 'the second instance to quit');
    await sleep(1500);                                                 // the first instance alone, still sampled
  } finally {
    clearInterval(sampler);
    try { process.kill(-second.pid, 'SIGKILL'); } catch (e) { /* gone */ }
  }
  assert.ok(!/sidecar start/.test(secondErr), 'the second instance started a sidecar');
  fs.writeFileSync(path.join(TMP, 'lc-second-peak.txt'), 'peak tasks (ps -eL lines carrying the user-data-dir): ' + peak + '\n');
  assert.ok(peak < 200, 'task peak ' + peak);
  process.kill(first.shellPid(), 'SIGTERM');                         // the first is then closed
  await until(() => first.exited, (STOP_WAIT_S + 5) * 1000, 'the first instance to exit');
});
