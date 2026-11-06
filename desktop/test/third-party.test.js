'use strict';
// The THIRD-PARTY.txt generator over extraction-shaped fixtures: node --test test/third-party.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const GEN = path.join(__dirname, '..', 'build', 'third-party.mjs');
const generate = async (opts) => (await import(GEN)).generate(opts);
const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex');

const MAP = [
  { match: 'libpython3.12.so*', component: 'CPython', from: 'dpkg', licence: 'PSF-2.0', source_url: 'https://www.python.org/', class: 'none' },
  { match: 'libfreetype-*.so*', component: 'FreeType', from: 'wheel', licence: 'FTL', source_url: 'https://freetype.org/', class: 'none', licence_file: 'freetype.txt' },
  { match: 'libffmpeg.so', component: 'ffmpeg', version: '7.1', licence: 'LGPL-2.1-or-later', source_url: 'https://ffmpeg.org/', class: 'lgpl',
    licence_file: 'lgpl-2.1.txt', record: { source: 'https://example.invalid/ffmpeg.tar.xz', replace: 'a separate shared object; replace libffmpeg.so' } },
  { match: 'libXtst.so*', component: 'libXtst', version: '1.2.3', licence: 'MIT', source_url: 'https://x.org/', class: 'none', licence_file: 'mit.txt' },
  { match: 'libbad.so*', component: 'badlib', version: '1', licence: 'GPL-3.0-only', source_url: 'https://example.invalid/', class: 'gpl', licence_file: 'mit.txt' },
  { match: 'libboot*.so*', component: 'bootloader', version: '6', licence: 'GPL-2.0-or-later WITH Bootloader-exception', source_url: 'https://pyinstaller.org/',
    class: 'gpl-exception', licence_file: 'mit.txt' },
  { match: 'libnorecord.so*', component: 'norecord', version: '1', licence: 'LGPL-2.1-only', source_url: 'https://example.invalid/', class: 'lgpl', licence_file: 'lgpl-2.1.txt' },
];

function write(root, rel, data) {
  const p = path.join(root, rel);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, data);
  return p;
}

function fixture(t, { buildTime = false } = {}) {
  const root = fs.mkdtempSync(path.join(process.env.TMP_DIR || os.tmpdir(), 'svf-tp-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sq = path.join(root, 'squashfs-root');
  const sidecar = path.join(sq, 'resources/sidecar/svf-maker-sidecar');
  const repo = path.join(sq, 'resources/repo');
  const electron = buildTime ? path.join(root, 'dist') : sq;
  if (buildTime) { write(electron, 'LICENSE', 'Electron MIT\n'); } else { write(electron, 'LICENSE.electron.txt', 'Electron MIT\n'); }
  write(electron, 'LICENSES.chromium.html', '<html>chromium notices</html>');
  write(electron, 'libffmpeg.so', 'ffmpeg-bytes');
  const usrlib = buildTime ? path.join(root, 'toolset-lib') : path.join(sq, 'usr/lib');
  write(usrlib, 'libXtst.so.6', 'xtst');
  const lib1 = write(sidecar, '_internal/libpython3.12.so.1.0', 'py-bytes');
  const lib2 = write(sidecar, '_internal/libfreetype-abc.so.6.20.1', 'ft-bytes');
  const provenance = {
    'libpython3.12.so.1.0': { source: '/usr/lib/x86_64-linux-gnu/libpython3.12.so.1.0', sha256: sha(fs.readFileSync(lib1)), origin: 'dpkg', package: 'libpython3.12', version: '3.12.3' },
    'libfreetype-abc.so.6.20.1': { source: '/pysite/pillow.libs/libfreetype-abc.so.6.20.1', sha256: sha(fs.readFileSync(lib2)), origin: 'wheel', package: 'pillow', version: '10.2.0' },
  };
  write(repo, 'svf/dos/A.SVF', 'face');
  write(repo, 'svf/dos/OFL.TXT', 'OFL text');
  write(repo, 'svf/jamo-extra/FACES.TSV', 'a\tb\n');
  write(repo, 'web/LICENCES.tsv', '# comment\ndos/A*.SVF\tdos/OFL.TXT\n');
  const pysite = path.join(root, 'pysite');
  write(pysite, 'pillow-10.2.0.dist-info/METADATA', 'Name: pillow\nVersion: 10.2.0\n');
  write(pysite, 'pillow-10.2.0.dist-info/LICENSE', 'HPND licence text');
  write(pysite, 'fonttools-4.66.1.dist-info/METADATA', 'Name: fonttools\nVersion: 4.66.1\n');
  write(pysite, 'fonttools-4.66.1.dist-info/licenses/LICENSE', 'MIT fonttools');
  write(pysite, 'pyinstaller-6.22.3.dist-info/METADATA', 'Name: pyinstaller\nVersion: 6.22.3\n');
  write(pysite, 'pyinstaller-6.22.3.dist-info/licenses/COPYING.txt', 'GPL with bootloader exception');
  const meta = path.join(root, 'meta');
  write(meta, 'LICENSE', 'MIT maker licence');
  write(meta, 'NOTICE.md', '# Notice\n\n| Faces | Source |\n|---|---|\n| `svf/dos/A*` | Font A |\n');
  write(meta, 'desktop/package.json', JSON.stringify({ name: 'svf-maker', version: '0.1.0', devDependencies: { electron: '45.2.3' } }));
  const licences = path.join(root, 'licences');
  for (const f of ['freetype.txt', 'lgpl-2.1.txt', 'mit.txt']) write(licences, f, 'text of ' + f);
  const opts = { sidecar, provenance, electron, usrlib, pysite, repo, meta, map: MAP, licencesDir: licences,
    readCopyright: (pkg) => 'copyright of ' + pkg };
  return { root, sq, sidecar, repo, electron, usrlib, pysite, meta, opts, lib1, lib2 };
}

const withoutProblems = (r) => assert.deepEqual(r.problems, []);

test('extraction-shaped tree -> no problems, every component in the text', async (t) => {
  const f = fixture(t);
  const r = await generate(f.opts);
  withoutProblems(r);
  for (const needle of ['MIT maker licence', 'SIL Open Font License', 'Electron MIT', 'LICENSES.chromium.html', 'CPython', 'Pillow', 'fontTools',
    'FreeType', 'ffmpeg', 'libXtst', 'text of freetype.txt', 'copyright of libpython3.12', 'HPND licence text', 'MIT fonttools',
    'https://example.invalid/ffmpeg.tar.xz', 'Copyleft check', 'release gate (D8): corresponding sources archived: NO']) {
    assert.ok(r.text.includes(needle), 'missing ' + needle);
  }
  assert.ok(r.components.some((c) => c.component === 'ffmpeg' && c.class === 'lgpl'));
});

test('build-time tree (LICENSE, toolset usr/lib) -> no problems', async (t) => {
  const f = fixture(t, { buildTime: true });
  const r = await generate(f.opts);
  withoutProblems(r);
  assert.ok(r.text.includes('Electron MIT'));
});

test('an unmatched .so fails closed (sidecar, electron and usr/lib each)', async (t) => {
  for (const where of ['sidecar', 'electron', 'usrlib']) {
    const f = fixture(t);
    const dir = where === 'sidecar' ? path.join(f.sidecar, '_internal') : where === 'electron' ? f.electron : f.usrlib;
    write(dir, 'libmystery.so.1', 'x');
    if (where === 'sidecar') f.opts.provenance['libmystery.so.1'] = { source: '/x', sha256: sha('x'), origin: 'dpkg', package: 'p', version: '1' };
    const r = await generate(f.opts);
    assert.ok(r.problems.some((p) => p.startsWith('unattributed: ') && p.includes('libmystery.so.1')), where + ': ' + r.problems.join('|'));
  }
});

test('a sidecar .so whose sha256 differs from its provenance fails', async (t) => {
  const f = fixture(t);
  fs.writeFileSync(f.lib1, 'changed after the build');
  const r = await generate(f.opts);
  assert.ok(r.problems.some((p) => p.startsWith('provenance mismatch: ') && p.includes('libpython3.12.so.1.0')), r.problems.join('|'));
  delete f.opts.provenance['libfreetype-abc.so.6.20.1'];
  const r2 = await generate(f.opts);
  assert.ok(r2.problems.some((p) => p.startsWith('provenance mismatch: ') && p.includes('libfreetype')), r2.problems.join('|'));
});

test('a gpl entry fails; a gpl-exception entry (bootloader) is attributed', async (t) => {
  const f = fixture(t);
  write(f.usrlib, 'libbad.so.1', 'bad');
  let r = await generate(f.opts);
  assert.ok(r.problems.some((p) => p.startsWith('gpl forbidden: ') && p.includes('libbad.so.1')), r.problems.join('|'));
  fs.rmSync(path.join(f.usrlib, 'libbad.so.1'));
  write(f.sidecar, '_internal/libboot.so.1', 'boot');
  f.opts.provenance['libboot.so.1'] = { source: '/b', sha256: sha('boot'), origin: 'wheel', package: 'pyinstaller', version: '6.22.3' };
  r = await generate(f.opts);
  withoutProblems(r);
  assert.ok(r.text.includes('Bootloader-exception'));
  assert.ok(/Copyleft check[^]*bootloader/.test(r.text));
});

test('lgpl needs a record', async (t) => {
  const f = fixture(t);
  write(f.usrlib, 'libnorecord.so.1', 'n');
  const r = await generate(f.opts);
  assert.ok(r.problems.includes('lgpl without distribution record: norecord'), r.problems.join('|'));
  const map = MAP.map((m) => (m.component === 'ffmpeg' ? { ...m, record: undefined } : m));
  const r2 = await generate({ ...f.opts, map });
  assert.ok(r2.problems.includes('lgpl without distribution record: ffmpeg'), r2.problems.join('|'));
});

test('non-OFL file under repo/svf fails; FACES.TSV and listed .TXT pass', async (t) => {
  const f = fixture(t);
  write(f.repo, 'svf/dos/STRAY.ttf', 'a font that is not listed');
  write(f.repo, 'svf/dos/B.SVF', 'face with no row');
  write(f.repo, 'svf/dos/NOTE.TXT', 'a text no row names');
  const r = await generate(f.opts);
  for (const rel of ['dos/STRAY.ttf', 'dos/B.SVF', 'dos/NOTE.TXT']) {
    assert.ok(r.problems.includes('not OFL-listed: svf/' + rel), rel + ': ' + r.problems.join('|'));
  }
  assert.ok(!r.problems.some((p) => p.includes('FACES.TSV') || p.includes('OFL.TXT') || p.includes('A.SVF')));
});

test('package.json dependencies make a problem', async (t) => {
  const f = fixture(t);
  write(f.meta, 'desktop/package.json', JSON.stringify({ dependencies: { left: '1' } }));
  const r = await generate(f.opts);
  assert.ok(r.problems.some((p) => p.includes('dependencies')), r.problems.join('|'));
});

// ---- the sources gate -------------------------------------------------------------------------------------------------
function sourcesDir(t, f, { omit, wrongDigest, wrongVersion, noRecipe } = {}) {
  const dir = path.join(f.root, 'sources');
  const entries = [];
  const add = (component, version, kind, name, data) => {
    const file = write(dir, name, data);
    entries.push({ component, version, kind, archive: name, sha256: sha(data) });
    return file;
  };
  if (omit !== 'ffmpeg') add('ffmpeg', wrongVersion ? '9.9' : '7.1', 'source', 'ffmpeg-7.1.tar.xz', 'ffmpeg source bytes');
  if (wrongDigest) { entries[0].sha256 = sha('something else'); }
  add('appimage-runtime', '12.0.1', 'source', 'runtime-src.tar.gz', 'runtime source');
  if (!noRecipe) add('appimage-runtime', '12.0.1', 'recipe', 'runtime-recipe.txt', 'build recipe');
  write(dir, 'MANIFEST.json', JSON.stringify(entries));
  return dir;
}
const RUNTIME = { match: 'AppImage-runtime', component: 'appimage-runtime', version: '12.0.1', licence: 'MIT AND BSD-2-Clause AND LGPL-2.1-only',
  source_url: 'https://github.com/electron-userland/electron-builder-binaries', class: 'lgpl', licence_file: 'lgpl-2.1.txt',
  record: { source: 'electron-builder-binaries', replace: 'rebuild the runtime' }, runtime: true };

test('sources: YES with a complete manifest', async (t) => {
  const f = fixture(t);
  const r = await generate({ ...f.opts, map: MAP.concat([RUNTIME]), sources: sourcesDir(t, f) });
  withoutProblems(r);
  assert.ok(r.text.includes('release gate (D8): corresponding sources archived: YES'), r.text.slice(-400));
});

test('sources: missing archive / digest mismatch / version mismatch / no runtime recipe each -> NO + its problem', async (t) => {
  const cases = [
    [{ omit: 'ffmpeg' }, 'sources: missing archive ffmpeg'],
    [{ wrongDigest: true }, 'sources: digest mismatch ffmpeg-7.1.tar.xz'],
    [{ wrongVersion: true }, 'sources: version mismatch ffmpeg'],
    [{ noRecipe: true }, 'sources: no recipe for appimage runtime'],
  ];
  for (const [opt, problem] of cases) {
    const f = fixture(t);
    const r = await generate({ ...f.opts, map: MAP.concat([RUNTIME]), sources: sourcesDir(t, f, opt) });
    assert.ok(r.problems.includes(problem), problem + ' <- ' + r.problems.join('|'));
    assert.ok(r.text.includes('corresponding sources archived: NO'));
  }
  // an archive named in the manifest but absent on disk
  const f = fixture(t);
  const dir = sourcesDir(t, f);
  fs.rmSync(path.join(dir, 'ffmpeg-7.1.tar.xz'));
  const r = await generate({ ...f.opts, map: MAP.concat([RUNTIME]), sources: dir });
  assert.ok(r.problems.includes('sources: missing archive ffmpeg'), r.problems.join('|'));
});

test('no --sources -> NO without a problem', async (t) => {
  const f = fixture(t);
  const r = await generate({ ...f.opts, map: MAP.concat([RUNTIME]) });
  withoutProblems(r);
  assert.ok(r.text.includes('corresponding sources archived: NO'));
});

test('the toolset modification record is printed', async (t) => {
  const f = fixture(t);
  const record = { toolset: 'appimage-12.0.1', archive: 'a.7z', archive_sha256: 'ab'.repeat(32), why: 'GPL', removed: { 'lib/x64/libindicator.so.7': 'cd'.repeat(32) } };
  const r = await generate({ ...f.opts, toolsetRecord: record });
  withoutProblems(r);
  for (const needle of ['AppImage toolset modification', 'lib/x64/libindicator.so.7  ' + 'cd'.repeat(32), 'ab'.repeat(32)]) assert.ok(r.text.includes(needle), needle);
});
