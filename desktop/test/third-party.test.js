'use strict';
// The THIRD-PARTY.txt generator over extraction-shaped fixtures: node --test test/third-party.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const GEN = path.join(__dirname, '..', 'build', 'third-party.mjs');
const generate = async (opts) => (await import(require('node:url').pathToFileURL(GEN).href)).generate(opts);   // a file URL: Windows paths are not URLs
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
  // a listed licence file with a lower-case .txt (svf/iolo/LICENSE-MIT.txt) passes as well
  write(f.repo, 'svf/iolo/C.SVF', 'face');
  write(f.repo, 'svf/iolo/LICENSE-MIT.txt', 'MIT');
  fs.appendFileSync(path.join(f.repo, 'web', 'LICENCES.tsv'), 'iolo/C.SVF\tiolo/LICENSE-MIT.txt\n');
  const r2 = await generate(f.opts);
  assert.ok(!r2.problems.some((p) => p.includes('iolo/')), r2.problems.join('|'));
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

// ---- the real map and licence texts ---------------------------------------------------------------------------------
const REAL_MAP = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'build', 'third-party-map.json'), 'utf8'));
const REAL_LICENCES = path.join(__dirname, '..', 'build', 'licences');

test('libXss and libXtst carry their upstream copyright notices into THIRD-PARTY.txt', async (t) => {
  for (const name of ['libxss1.txt', 'libxtst6.txt']) {
    const text = fs.readFileSync(path.join(REAL_LICENCES, name), 'utf8');
    assert.match(text, /Copyright (\(c\) |\(C\) )?19\d\d/, name + ' has no copyright line');
  }
  const f = fixture(t);
  write(f.usrlib, 'libXss.so.1', 'xss');
  const r = await generate({ ...f.opts, map: REAL_MAP, licencesDir: REAL_LICENCES });
  withoutProblems(r);
  assert.ok(r.text.includes('Copyright (c) 1992  X Consortium'), 'libXss notice missing');
  assert.ok(r.text.includes('Copyright 1990, 1991 by UniSoft Group Limited'), 'libXtst notice missing');
  assert.ok(r.text.includes('(sha256 ' + sha('xtst') + ')'), 'the digest of an unattributed-by-provenance file is recorded');
});

test('the AppImage runtime section carries every embedded component with its version, text and no GPL token in its licence', async (t) => {
  const f = fixture(t);
  const r = await generate({ ...f.opts, map: REAL_MAP, licencesDir: REAL_LICENCES });
  withoutProblems(r);
  const entry = REAL_MAP.find((e) => e.runtime);
  assert.ok(!/GPL-/.test(entry.licence.replace(/LGPL-2\.1-only/g, '')), entry.licence);
  assert.equal(entry.licence, 'MIT AND BSD-2-Clause AND LGPL-2.1-only AND BSD-3-Clause AND Zlib');
  for (const needle of ['type2-runtime (MIT)', 'Copyright (c) 2004-23 probonopd', 'musl libc (MIT', 'Copyright © 2005-2020 Rich Felker',
    'squashfuse 0.5.2 (BSD-2-Clause)', 'Copyright (c) 2012 Dave Vasilevsky', 'libzstd 1.5.6 (BSD-3-Clause)', 'Copyright (c) Meta Platforms',
    'zlib 1.3.1 (Zlib', 'Copyright (C) 1995-2024 Jean-loup Gailly and Mark Adler', 'The origin of this software must not be misrepresented',
    'libfuse 3.15.0 (LGPL-2.1)', 'GNU LESSER GENERAL PUBLIC LICENSE', 'libfuse 3.15.0: https://github.com/libfuse/libfuse/releases/tag/fuse-3.15.0']) {
    assert.ok(r.text.includes(needle), needle);
  }
});

test('every licence_file named by the map exists', () => {
  for (const e of REAL_MAP) if (e.licence_file) assert.ok(fs.existsSync(path.join(REAL_LICENCES, e.licence_file)), e.licence_file);
});

test('golden TOC: sidecar-provenance.py keys and the generator agree on the destination form', async (t) => {
  const { spawnSync } = require('node:child_process');
  const root = fs.mkdtempSync(path.join(process.env.TMP_DIR || os.tmpdir(), 'svf-toc-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const work = path.join(root, 'work');
  const pysite = path.join(root, 'pysite');
  const sys_ = path.join(root, 'system');
  let toc = fs.readFileSync(path.join(__dirname, 'fixtures', 'collect-sample.toc'), 'utf8');
  const lit = (p) => p.split(path.sep).join('/');       // a TOC is a Python literal: no backslash (Windows) in it
  toc = toc.replace(/PYSITE/g, lit(pysite)).replace(/SYSTEM/g, lit(sys_)).replace(/WORK/g, lit(work));
  write(work, 'COLLECT-00.toc', toc);
  write(pysite, 'pillow-10.2.0.dist-info/RECORD', 'PIL/_imaging.cpython-312-x86_64-linux-gnu.so,,\npillow.libs/libfreetype-f154df84.so.6.20.1,,\n');
  write(pysite, 'pillow-10.2.0.dist-info/LICENSE', 'HPND');
  for (const rel of ['PIL/_imaging.cpython-312-x86_64-linux-gnu.so', 'pillow.libs/libfreetype-f154df84.so.6.20.1']) write(pysite, rel, 'bytes of ' + rel);
  write(sys_, 'libz.so.1', 'zlib bytes');
  write(sys_, 'lib-dynload/_json.cpython-312-x86_64-linux-gnu.so', 'json bytes');
  const out = path.join(root, 'prov.json');
  const python = process.platform === 'win32' ? 'python' : 'python3';
  const r = spawnSync(python, ['-I', path.join(__dirname, '..', 'build', 'sidecar-provenance.py'), work, out, '--pysite', pysite], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  const prov = JSON.parse(fs.readFileSync(out, 'utf8'));
  assert.deepEqual(Object.keys(prov).sort(), ['PIL/_imaging.cpython-312-x86_64-linux-gnu.so', 'libfreetype-f154df84.so.6.20.1', 'libz.so.1',
    'python3.12/lib-dynload/_json.cpython-312-x86_64-linux-gnu.so'].sort());
  assert.equal(prov['libfreetype-f154df84.so.6.20.1'].origin, 'wheel');
  // the generator looks each one up under _internal/<dest> without a prefix in the key
  const sidecar = path.join(root, 'sidecar');
  for (const dest of Object.keys(prov)) fs.mkdirSync(path.dirname(path.join(sidecar, '_internal', dest)), { recursive: true });
  for (const [dest, p] of Object.entries(prov)) fs.copyFileSync(p.source, path.join(sidecar, '_internal', dest));
  const map = [{ match: '*.so*', component: 'any', version: '1', licence: 'MIT', source_url: 'x', class: 'none', licence_file: 'mit.txt' }];
  const lic = path.join(root, 'lic'); write(lic, 'mit.txt', 'mit');
  const fx = fixture(t);
  const res = await generate({ ...fx.opts, sidecar, provenance: prov, map, licencesDir: lic });
  assert.ok(!res.problems.some((p) => p.startsWith('provenance mismatch')), res.problems.join('|'));
});

// A real built tree against the real map (env-gated like test_frozen: it needs desktop/build/out/sidecar from build-sidecar.sh)
const BUILT = path.join(__dirname, '..', 'build', 'out');
const builtOk = fs.existsSync(path.join(BUILT, 'sidecar', 'svf-maker-sidecar', '_internal')) && fs.existsSync(path.join(BUILT, 'sidecar-provenance.json'));
test('the real built _internal tree is fully attributed by the map', { skip: builtOk ? false : 'no built sidecar (run maker/build-sidecar.sh)' }, async () => {
  const dist = path.join(__dirname, '..', 'node_modules', 'electron', 'dist');
  const empty = fs.mkdtempSync(path.join(process.env.TMP_DIR || os.tmpdir(), 'svf-empty-'));
  try {
    const r = await generate({ sidecar: path.join(BUILT, 'sidecar', 'svf-maker-sidecar'),
      provenance: JSON.parse(fs.readFileSync(path.join(BUILT, 'sidecar-provenance.json'), 'utf8')), electron: dist, usrlib: empty,
      pysite: process.env.SVF_MAKER_REF_SITE || path.join(process.env.HOME, 'work', 'tmp', 'svf-desktop-t4-sidecar', 'pysite'),
      repo: path.join(BUILT, 'repo'), meta: path.join(__dirname, '..', '..'), map: REAL_MAP });
    assert.deepEqual(r.problems.filter((p) => p.startsWith('unattributed') || p.startsWith('provenance') || p.startsWith('gpl')), []);
  } finally { fs.rmSync(empty, { recursive: true, force: true }); }
});

test('a missing or non-directory input directory is a problem, not an empty walk', async (t) => {
  for (const [key, mutate] of [
    ['sidecar', (f) => { f.opts.sidecar = path.join(f.root, 'no-such-sidecar'); }],
    ['sidecar', (f) => fs.rmSync(path.join(f.sidecar, '_internal'), { recursive: true })],
    ['usrlib', (f) => { f.opts.usrlib = path.join(f.root, 'no-such-usrlib'); }],
    ['usrlib', (f) => { f.opts.usrlib = write(f.root, 'a-file', 'x'); }],
    ['electron', (f) => { f.opts.electron = path.join(f.root, 'no-such-electron'); }],
  ]) {
    const f = fixture(t);
    mutate(f);
    const r = await generate(f.opts);
    assert.ok(r.problems.some((p) => p.startsWith('missing input directory') && p.includes(key)), key + ': ' + JSON.stringify(r.problems));
  }
});

test('usr/lib64 next to usr/lib is attributed like usr/lib', async (t) => {
  const f = fixture(t);
  write(path.join(f.sq, 'usr/lib64'), 'libmystery64.so.1', 'x');
  const r = await generate(f.opts);
  assert.ok(r.problems.includes('unattributed: usr/lib64/libmystery64.so.1'), JSON.stringify(r.problems));
  write(path.join(f.sq, 'usr/lib64'), 'libXtst.so.6', 'xtst64');
  fs.rmSync(path.join(f.sq, 'usr/lib64/libmystery64.so.1'));
  const ok = await generate(f.opts);
  assert.deepEqual(ok.problems, []);
  assert.ok(ok.text.includes('usr/lib64/libXtst.so.6'));
});

// The Windows notices (t_9b8f56f0): --platform win32 attributes *.dll and *.pyd (case-blind), needs no usr/lib, takes an
// entry "from": "python" from the interpreter's LICENSE.txt, and still fails closed on an unmatched DLL.
test('win32: dll and pyd attributed, python-origin text, unmatched dll fails closed', async (t) => {
  const root = fs.mkdtempSync(path.join(process.env.TMP_DIR || os.tmpdir(), 'svf-tpw-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sidecar = path.join(root, 'sidecar');
  const electron = path.join(root, 'win-unpacked');
  const repo = path.join(root, 'repo');
  write(electron, 'LICENSE.electron.txt', 'Electron MIT\n');
  write(electron, 'LICENSES.chromium.html', '<html>chromium notices</html>');
  write(electron, 'ffmpeg.dll', 'ffmpeg-bytes');
  write(electron, 'resources/app.asar.unpacked/x.dll', 'not walked');
  const py = write(sidecar, '_internal/python312.dll', 'py-bytes');
  const vc = write(sidecar, '_internal/VCRUNTIME140.dll', 'vc-bytes');
  const im = write(sidecar, '_internal/PIL/_imaging.cp312-win_amd64.pyd', 'imaging');
  const ffi = write(sidecar, '_internal/libffi-8.dll', 'ffi-bytes');
  const provenance = {
    'libffi-8.dll': { source: 'C:/py/DLLs/libffi-8.dll', sha256: sha(fs.readFileSync(ffi)), origin: 'python', package: 'python3', version: '3.12.3' },
    'python312.dll': { source: 'C:/py/python312.dll', sha256: sha(fs.readFileSync(py)), origin: 'python', package: 'python3', version: '3.12.3' },
    'VCRUNTIME140.dll': { source: 'C:/py/VCRUNTIME140.dll', sha256: sha(fs.readFileSync(vc)), origin: 'python', package: 'python3', version: '3.12.3' },
    'PIL/_imaging.cp312-win_amd64.pyd': { source: 'C:/pysite/PIL/_imaging.pyd', sha256: sha(fs.readFileSync(im)), origin: 'wheel', package: 'pillow', version: '10.2.0' },
  };
  write(repo, 'svf/dos/A.SVF', 'face');
  write(repo, 'svf/dos/OFL.TXT', 'OFL text');
  write(repo, 'web/LICENCES.tsv', 'dos/A*.SVF\tdos/OFL.TXT\n');
  const pysite = path.join(root, 'pysite');
  write(pysite, 'pillow-10.2.0.dist-info/LICENSE', 'HPND licence text');
  write(pysite, 'fonttools-4.66.1.dist-info/LICENSE', 'MIT fonttools');
  write(pysite, 'pyinstaller-6.22.3.dist-info/COPYING.txt', 'GPL with bootloader exception');
  const meta = path.join(root, 'meta');
  write(meta, 'LICENSE', 'MIT maker licence');
  write(meta, 'NOTICE.md', '| `svf/dos/A*` | Font A |\n');
  write(meta, 'desktop/package.json', JSON.stringify({ name: 'svf-maker' }));
  const pyLicence = write(root, 'LICENSE.txt', 'PSF licence and the bundled libraries of the Windows build');
  const licences = path.join(__dirname, '..', 'build', 'licences');
  const map = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'build', 'third-party-map-win.json'), 'utf8'));
  const opts = { platform: 'win32', sidecar, provenance, electron, pysite, repo, meta, map, licencesDir: licences, pythonLicence: pyLicence };
  const r = await generate(opts);
  withoutProblems(r);
  assert.equal(r.text.split('PSF licence and the bundled libraries').length - 1, 1, 'CPython LICENSE.txt printed once');
  assert.ok(r.text.includes('libffi-8.dll'));
  for (const needle of ['PSF licence and the bundled libraries', 'python312.dll', 'Microsoft Visual C++ runtime', 'ffmpeg.dll', 'HPND licence text']) {
    assert.ok(r.text.includes(needle), needle);
  }
  write(electron, 'mystery.dll', 'x');
  const r2 = await generate(opts);
  assert.deepEqual(r2.problems, ['unattributed: mystery.dll']);
  fs.rmSync(path.join(electron, 'mystery.dll'));
  // a compiled module a wheel brought, matched only by the "*.pyd" CPython catch-all: refused, not labelled CPython
  const ext = write(sidecar, '_internal/newpkg/_speedups.cp312-win_amd64.pyd', 'ext');
  provenance['newpkg/_speedups.cp312-win_amd64.pyd'] = { source: 'C:/pysite/newpkg/_speedups.pyd', sha256: sha(fs.readFileSync(ext)),
    origin: 'wheel', package: 'newpkg', version: '1.0' };
  const r3 = await generate(opts);
  assert.deepEqual(r3.problems, ['origin mismatch: _internal/newpkg/_speedups.cp312-win_amd64.pyd (map python, built from wheel)']);
});
