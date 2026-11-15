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
  assert.match(src, /^X=\$\(mktemp -d "\$T\/release-XXXXXX"\)$/m);
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
