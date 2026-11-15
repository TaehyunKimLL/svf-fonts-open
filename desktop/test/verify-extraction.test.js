'use strict';
// The release check's comparisons of the extracted AppImage with the checkout and the regenerated notices.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const SCRIPT = path.join(__dirname, '..', 'build', 'verify-extraction.sh');
function setup(t) {
  const root = fs.mkdtempSync(path.join(process.env.TMP_DIR || os.tmpdir(), 'svf-ve-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const w = (rel, data) => { const p = path.join(root, rel); fs.mkdirSync(path.dirname(p), { recursive: true }); fs.writeFileSync(p, data); return p; };
  w('co/maker/a.py', 'print(1)\n'); w('co/maker/test_a.py', 'test\n'); w('co/tools/b.py', 'print(2)\n'); w('co/tools/test_b.py', 'test\n');
  w('co/web/mkindex.py', 'print(3)\n'); w('sq/resources/repo/web/mkindex.py', 'print(3)\n'); w('sq/resources/repo/maker/a.py', 'print(1)\n'); w('sq/resources/repo/tools/b.py', 'print(2)\n');
  w('sq/resources/THIRD-PARTY.txt', 'notices\n'); w('regen.txt', 'notices\n');
  const run = () => spawnSync('bash', [SCRIPT, path.join(root, 'sq'), path.join(root, 'regen.txt'), path.join(root, 'co')], { encoding: 'utf8' });
  return { root, w, run };
}

test('an honest extraction passes', (t) => {
  const r = setup(t).run();
  assert.equal(r.status, 0, r.stdout);
  assert.match(r.stdout, /notices ok/);
  assert.match(r.stdout, /repo-sources ok/);
});

test('a tampered notices file fails', (t) => {
  const s = setup(t);
  s.w('sq/resources/THIRD-PARTY.txt', 'notices with an edit\n');
  const r = s.run();
  assert.equal(r.status, 1);
  assert.match(r.stdout, /notices FAIL/);
});

test('a tampered or extra or missing tool source fails', (t) => {
  for (const [mutate, needle] of [
    [(s) => s.w('sq/resources/repo/tools/b.py', 'print("evil")\n'), 'repo/tools/b.py'],
    [(s) => s.w('sq/resources/repo/maker/extra.py', 'x\n'), 'maker(file set differs)'],
    [(s) => fs.rmSync(path.join(s.root, 'sq/resources/repo/maker/a.py')), 'maker(file set differs)'],
    [(s) => s.w('sq/resources/repo/web/mkindex.py', 'print("evil")\n'), 'repo/web/mkindex.py'],
    [(s) => fs.rmSync(path.join(s.root, 'sq/resources/repo/web/mkindex.py')), 'web(file set differs)'],
    [(s) => s.w('sq/resources/repo/web/extra.py', 'x\n'), 'web(file set differs)'],
  ]) {
    const s = setup(t);
    mutate(s);
    const r = s.run();
    assert.equal(r.status, 1, needle);
    assert.ok(r.stdout.includes('repo-sources FAIL') && r.stdout.includes(needle), r.stdout);
  }
});

test('release-check makes its extraction directory with mktemp, not a timestamp', () => {
  const src = fs.readFileSync(path.join(__dirname, '..', 'build', 'release-check.sh'), 'utf8');
  assert.match(src, /^X=\$\(mktemp -d "\$T\/release-XXXXXX"\) \|\| \{ fail extract /m);
  assert.ok(!/date \+%s\)"\s*$/m.test(src.split('\n').filter((l) => l.startsWith('X=')).join('\n')));
});

// release-check's parsing of the verifier's output (verify-report.sh) fails closed.
const REPORT = path.join(__dirname, '..', 'build', 'verify-report.sh');
function report(t, verifierBody) {
  const root = fs.mkdtempSync(path.join(process.env.TMP_DIR || os.tmpdir(), 'svf-vr-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const v = path.join(root, 'verifier.sh');
  fs.writeFileSync(v, verifierBody);
  return spawnSync('bash', [REPORT, '/sq', '/regen', '/co', v], { encoding: 'utf8' });
}

test('report: a verifier that prints nothing fails', (t) => {
  const r = report(t, 'exit 0\n');
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stdout, /CHECK notices FAIL/);
  assert.match(r.stdout, /CHECK repo-sources FAIL/);
});

test('report: a verifier that dies early or is missing fails', (t) => {
  let r = report(t, 'echo "notices ok"\nexit 3\n');
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stdout, /CHECK repo-sources FAIL/);
  assert.match(r.stdout, /exited 3/);
  r = spawnSync('bash', [REPORT, '/sq', '/regen', '/co', '/no/such/verifier.sh'], { encoding: 'utf8' });
  assert.equal(r.status, 1, r.stdout);
});

test('report: a verifier with a missing name fails even when it exits 0', (t) => {
  const r = report(t, 'echo "notices ok"\n');
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stdout, /CHECK repo-sources FAIL/);
});

test('report: both names ok passes; a FAIL line fails', (t) => {
  let r = report(t, 'echo "notices ok"\necho "repo-sources ok"\n');
  assert.equal(r.status, 0, r.stdout);
  assert.match(r.stdout, /CHECK notices ok\nCHECK repo-sources ok/);
  r = report(t, 'echo "notices ok"\necho "repo-sources FAIL repo/tools/b.py"\nexit 1\n');
  assert.equal(r.status, 1);
  assert.match(r.stdout, /CHECK repo-sources FAIL repo\/tools\/b.py/);
});

test('prune-appimage-toolset: a missing 7z is one stderr line and exit 1, not a traceback', (t) => {
  const root = fs.mkdtempSync(path.join(process.env.TMP_DIR || os.tmpdir(), 'svf-pr-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const py = spawnSync('bash', ['-c', 'command -v python3'], { encoding: 'utf8' }).stdout.trim();
  const r = spawnSync(py, [path.join(__dirname, '..', 'build', 'prune-appimage-toolset.py'), root, path.join(root, 'a.7z'), path.join(root, 'out')],
    { encoding: 'utf8', env: { PATH: root, HOME: process.env.HOME } });
  assert.equal(r.status, 1, r.stderr);
  assert.match(r.stderr, /7z/);
  assert.ok(!/Traceback/.test(r.stderr), r.stderr);
  assert.equal(r.stderr.trim().split('\n').length, 1, r.stderr);
});

test('report: only notices and repo-sources, each once; anything else is unexpected', (t) => {
  for (const body of [
    'echo garbage\necho "notices ok"\necho "repo-sources ok"\n',
    'echo "notices ok"\necho "repo-sources ok"\necho "bogus ok"\n',
    'echo "notices ok"\necho "notices ok"\necho "repo-sources ok"\n',
    'echo "notices ok"\necho "repo-sources ok"\necho "extra FAIL x"\n',
    'echo "notices unexpected ok"\necho "repo-sources ok"\n',
    'echo "notices ok"\necho "repo-sources garbage FAIL x"\n',
    'echo "notices ok"\necho "repo-sources FAILED x"\n',
  ]) {
    const r = report(t, body);
    assert.equal(r.status, 1, body + r.stdout);
    assert.match(r.stdout, /CHECK verify-extraction FAIL unexpected output: /, body);
  }
});

test('report: both ok lines then a non-zero exit fails; a stderr line is named in the FAIL', (t) => {
  let r = report(t, 'echo "notices ok"\necho "repo-sources ok"\nexit 4\n');
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stdout, /exited 4/);
  r = report(t, 'echo "notices ok"\necho "repo-sources ok"\necho "sha256sum: warning" >&2\n');
  assert.equal(r.status, 1, r.stdout);
  assert.match(r.stdout, /unexpected output: sha256sum: warning/);
});

test('verify-report.sh and run-verify.sh are executable', () => {
  for (const f of ['verify-report.sh', 'run-verify.sh']) {
    assert.ok(fs.statSync(path.join(__dirname, '..', 'build', f)).mode & 0o100, f);
  }
});

// run-verify.sh is release-check's step: it always prints a CHECK FAIL line when the report script is missing or dies
const RUNNER = path.join(__dirname, '..', 'build', 'run-verify.sh');
test('run-verify: a missing or dying report script still prints a CHECK FAIL line and exits 1', (t) => {
  const root = fs.mkdtempSync(path.join(process.env.TMP_DIR || os.tmpdir(), 'svf-rv-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const dies = path.join(root, 'dies.sh');
  fs.writeFileSync(dies, 'echo oops >&2\nexit 2\n');
  const ok = path.join(root, 'ok.sh');
  fs.writeFileSync(ok, 'echo "CHECK notices ok"\necho "CHECK repo-sources ok"\n');
  for (const [rep, status] of [[path.join(root, 'missing.sh'), 1], [dies, 1], [ok, 0]]) {
    const r = spawnSync('bash', [RUNNER, '/sq', '/regen', '/co', rep], { encoding: 'utf8' });
    assert.equal(r.status, status, r.stdout + r.stderr);
    if (status) assert.match(r.stdout, /^CHECK verify-extraction FAIL verify-report.sh exited \d+/m, r.stdout);
    else assert.match(r.stdout, /CHECK notices ok/);
  }
});

test('release-check runs the verification through run-verify.sh and keeps its status', () => {
  const src = fs.readFileSync(path.join(__dirname, '..', 'build', 'release-check.sh'), 'utf8');
  assert.match(src, /if ! bash "\$ROOT\/desktop\/build\/run-verify\.sh" .*; then FAILED=1; fi/);
});
