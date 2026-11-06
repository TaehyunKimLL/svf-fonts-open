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
  w('sq/resources/repo/maker/a.py', 'print(1)\n'); w('sq/resources/repo/tools/b.py', 'print(2)\n');
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
  ]) {
    const s = setup(t);
    mutate(s);
    const r = s.run();
    assert.equal(r.status, 1, needle);
    assert.ok(r.stdout.includes('repo-sources FAIL') && r.stdout.includes(needle), r.stdout);
  }
});
