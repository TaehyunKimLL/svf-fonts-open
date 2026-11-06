#!/usr/bin/env node
// third-party.mjs: writes THIRD-PARTY.txt from the bundle itself (spec 8.9, 8.10; plan Task 7).
//
//   node desktop/build/third-party.mjs --sidecar DIR --provenance FILE --electron DIR --usrlib DIR --pysite DIR \
//        --repo DIR --meta DIR --out FILE [--sources DIR] [--map FILE] [--licences DIR]
//
// Fails closed: every shared object under the sidecar's _internal, under the Electron directory and under the AppImage
// usr/lib must match a map entry (unattributed: <path>); a sidecar library must match its build-time provenance
// (sha256); a GPL entry is forbidden; an LGPL entry needs a distribution record; svf/ may hold only OFL-listed faces.
// Exit 0 and the file, or exit 1 with one line per problem on stderr.
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SO = /\.so(\.|$)/;
const sha256 = (file) => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

function* walk(dir, base = dir) {
  if (!dir || !fs.existsSync(dir)) return;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (e.name !== 'node_modules') yield* walk(p, base); } else if (e.isFile() || e.isSymbolicLink()) yield [p, path.relative(base, p)];
  }
}

function globRe(glob) {
  const esc = glob.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.');
  return new RegExp('^' + esc + '$');
}
const readIf = (p) => { try { return fs.readFileSync(p, 'utf8'); } catch (e) { return null; } };

function defaultCopyright(pkg) {
  return readIf('/usr/share/doc/' + pkg + '/copyright');
}

// the licence text of a map entry: its committed file, a wheel's dist-info, or the Debian copyright file
function licenceText(entry, ctx, version) {
  if (entry.licence_file) {
    const t = readIf(path.join(ctx.licencesDir, entry.licence_file));
    if (t) return t;
  }
  if (entry.from === 'wheel' || entry.wheel) {
    const dist = entry.wheel || entry.component.toLowerCase();
    const info = ctx.distInfo(dist);
    if (info) return info;
  }
  if (entry.from === 'dpkg' && ctx.pkgOf) {
    const pkg = ctx.pkgOf(entry);
    const t = pkg && ctx.readCopyright(pkg);
    if (t) return t;
  }
  return null;
}

function distInfoText(pysite, dist) {
  if (!pysite || !fs.existsSync(pysite)) return null;
  const want = dist.toLowerCase().replace(/-/g, '_');
  for (const e of fs.readdirSync(pysite)) {
    const m = /^(.+)-([^-]+)\.dist-info$/.exec(e);
    if (!m || m[1].toLowerCase().replace(/-/g, '_') !== want) continue;
    const dir = path.join(pysite, e);
    const parts = [];
    for (const [file, rel] of walk(dir)) {
      if (/(^|\/)(LICEN[CS]E|COPYING|NOTICE|AUTHORS)[^/]*$/i.test(rel)) parts.push('--- ' + e + '/' + rel + '\n' + fs.readFileSync(file, 'utf8'));
    }
    if (parts.length) return parts.join('\n');
  }
  return null;
}

function distVersion(pysite, dist) {
  if (!pysite || !fs.existsSync(pysite)) return null;
  const want = dist.toLowerCase().replace(/-/g, '_');
  for (const e of fs.readdirSync(pysite)) {
    const m = /^(.+)-([^-]+)\.dist-info$/.exec(e);
    if (m && m[1].toLowerCase().replace(/-/g, '_') === want) return m[2];
  }
  return null;
}

function parseLicences(file) {
  const rows = [];
  for (const line of (readIf(file) || '').split('\n')) {
    if (!line.trim() || line.startsWith('#')) continue;
    const [glob, lic] = line.split('\t');
    if (!glob || !lic) continue;
    rows.push({ re: globRe(glob.trim()), lic: lic.split(',').map((x) => x.trim()).filter(Boolean) });
  }
  return rows;
}

export async function generate(opts) {
  const { sidecar, electron, usrlib, pysite, repo, meta, sources, toolsetRecord } = opts;
  const map = opts.map;
  const provenance = opts.provenance || {};
  const problems = [];
  const components = new Map();                         // "component version" -> {component, version, licence, class, ...}
  const ctx = {
    licencesDir: opts.licencesDir || path.join(HERE, 'licences'),
    readCopyright: opts.readCopyright || defaultCopyright,
    distInfo: (dist) => distInfoText(pysite, dist),
    pkgOf: null,
  };
  const matchEntry = (base) => map.find((m) => !m.runtime && !m.always && globRe(m.match).test(base));

  // ---- attribute every shared object -------------------------------------------------------------------------
  const attribute = (file, shown, where, prov) => {
    const entry = matchEntry(path.basename(file));
    if (!entry) { problems.push('unattributed: ' + shown); return; }
    let version = entry.version;
    let pkg = null;
    if (prov) {
      const p = provenance[shown.replace(/^_internal\//, '')];
      if (!p || p.sha256 !== sha256(file)) { problems.push('provenance mismatch: ' + shown); }
      if (p) { pkg = p.package; if (!version && entry.from === 'dpkg') version = p.version; }
    }
    if (!version && /^(Pillow|fontTools)$/.test(entry.component)) version = distVersion(pysite, entry.wheel) || 'unknown';
    if (!version && (entry.from === 'wheel' || entry.wheel)) {
      // a library vendored in a wheel: its own release is not recorded, the file's shared-object version and the wheel are
      const so = /\.so\.([\d.]+)$/.exec(path.basename(file));
      version = 'vendored in the ' + (entry.wheel || 'pillow') + ' ' + (distVersion(pysite, entry.wheel || 'pillow') || '?') + ' wheel' + (so ? ' (so ' + so[1] + ')' : '');
    }
    const key = entry.component + ' ' + (version || '?');
    if (!components.has(key)) components.set(key, { component: entry.component, version: version || 'unknown', entry, pkg, files: [], where });
    components.get(key).files.push(shown);
    if (entry.class === 'gpl') problems.push('gpl forbidden: ' + shown);
    if (entry.class === 'lgpl' && !entry.record) {
      const msg = 'lgpl without distribution record: ' + entry.component;
      if (!problems.includes(msg)) problems.push(msg);
    }
  };
  for (const [file, rel] of walk(path.join(sidecar, '_internal'))) if (SO.test(path.basename(file))) attribute(file, '_internal/' + rel, 'sidecar', true);
  for (const [file, rel] of walk(electron)) {
    if (rel.startsWith('resources/') || rel.startsWith('usr/') || rel.startsWith('node_modules/')) continue;
    if (SO.test(path.basename(file))) attribute(file, rel, 'electron', false);
  }
  for (const [file, rel] of walk(usrlib)) if (SO.test(path.basename(file))) attribute(file, 'usr/lib/' + rel, 'usrlib', false);

  // ---- runtime components (no file to match: the AppImage runtime) --------------------------------------------
  for (const entry of map.filter((m) => m.runtime || m.always)) {
    components.set(entry.component + ' ' + entry.version, { component: entry.component, version: entry.version, entry, pkg: null, files: [],
      where: entry.runtime ? 'appimage-runtime' : 'bundle' });
    if (entry.class === 'lgpl' && !entry.record) problems.push('lgpl without distribution record: ' + entry.component);
  }

  // ---- the faces: only OFL-listed files under repo/svf ---------------------------------------------------------
  const svf = path.join(repo, 'svf');
  const rows = parseLicences(path.join(repo, 'web', 'LICENCES.tsv'));
  const named = new Set(rows.flatMap((r) => r.lic));
  const metadataAllow = new Set(['jamo-extra/FACES.TSV']);
  for (const [, rel] of walk(svf)) {
    const posix = rel.split(path.sep).join('/');
    const ok = (posix.endsWith('.SVF') && rows.some((r) => r.re.test(posix))) || (posix.endsWith('.TXT') && named.has(posix)) || metadataAllow.has(posix);
    if (!ok) problems.push('not OFL-listed: svf/' + posix);
  }

  // ---- no runtime npm dependency ------------------------------------------------------------------------------
  try {
    const pkgJson = JSON.parse(fs.readFileSync(path.join(meta, 'desktop', 'package.json'), 'utf8'));
    if (pkgJson.dependencies && Object.keys(pkgJson.dependencies).length) problems.push('desktop/package.json has dependencies: ' + Object.keys(pkgJson.dependencies).join(','));
  } catch (e) { problems.push('cannot read desktop/package.json under --meta'); }

  // ---- the sources gate ---------------------------------------------------------------------------------------
  const lgpl = [...components.values()].filter((c) => c.entry.class === 'lgpl');
  let archived = false;
  if (sources) {
    const gaps = [];
    let manifest = [];
    try { manifest = JSON.parse(fs.readFileSync(path.join(sources, 'MANIFEST.json'), 'utf8')); } catch (e) { gaps.push('sources: no readable MANIFEST.json'); }
    for (const c of lgpl) {
      const sameName = manifest.filter((m) => m.component === c.component && m.kind === 'source');
      const hit = sameName.find((m) => m.version === c.version);
      if (!sameName.length) { gaps.push('sources: missing archive ' + c.component); continue; }
      if (!hit) { gaps.push('sources: version mismatch ' + c.component); continue; }
      const file = path.join(sources, hit.archive);
      if (!fs.existsSync(file) || fs.statSync(file).size === 0) { gaps.push('sources: missing archive ' + c.component); continue; }
      if (sha256(file) !== hit.sha256) gaps.push('sources: digest mismatch ' + hit.archive);
      if (c.entry.runtime) {
        const rec = manifest.find((m) => m.component === c.component && m.kind === 'recipe' && m.version === c.version);
        if (!rec) gaps.push('sources: no recipe for appimage runtime');
        else {
          const rf = path.join(sources, rec.archive);
          if (!fs.existsSync(rf) || fs.statSync(rf).size === 0) gaps.push('sources: no recipe for appimage runtime');
          else if (sha256(rf) !== rec.sha256) gaps.push('sources: digest mismatch ' + rec.archive);
        }
      }
    }
    for (const g of gaps) if (!problems.includes(g)) problems.push(g);
    archived = gaps.length === 0;
  }

  // ---- the text -----------------------------------------------------------------------------------------------
  const out = [];
  const hr = (title) => { out.push('', '='.repeat(78), title, '='.repeat(78), ''); };
  out.push('THIRD-PARTY NOTICES: SVF maker', '', 'Generated by desktop/build/third-party.mjs from the files of this package. Do not edit.');
  hr('The maker (MIT)');
  out.push(readIf(path.join(meta, 'LICENSE')) || '(LICENSE not found)');
  hr('The faces in resources/repo/svf (SIL Open Font License 1.1)');
  const notice = readIf(path.join(meta, 'NOTICE.md')) || '';
  const table = notice.split('\n').filter((l) => l.startsWith('|')).join('\n');
  out.push('Every face is under the SIL Open Font License 1.1; its licence text sits beside it (resources/repo/svf/**/OFL*.TXT).', '', table);
  hr('Electron and Chromium');
  const eLic = readIf(path.join(electron, 'LICENSE.electron.txt')) || readIf(path.join(electron, 'LICENSE'));
  if (!eLic) problems.push('no Electron licence file (LICENSE or LICENSE.electron.txt) under --electron');
  out.push('Electron (MIT):', '', eLic || '(missing)', '', 'Chromium and its third-party notices: LICENSES.chromium.html in this package.');
  if (!fs.existsSync(path.join(electron, 'LICENSES.chromium.html'))) problems.push('no LICENSES.chromium.html under --electron');
  const section = (title, filter) => {
    const list = [...components.values()].filter(filter);
    if (!list.length) return;
    hr(title);
    for (const c of list) {
      const e = c.entry;
      let text = licenceText(e, { ...ctx, pkgOf: () => c.pkg || e.package }, c.version);
      if (!text) problems.push('no licence text: ' + c.component);
      else if (['pillow', 'fonttools'].includes(e.wheel) && !e.licence_file) {
        text = '(the licence texts of this library are in the ' + e.wheel + ' wheel\'s LICENSE, printed once above under "Python packages in the sidecar")';
      }
      out.push('### ' + c.component + ' ' + c.version, 'licence: ' + e.licence, 'class: ' + e.class, 'source: ' + e.source_url);
      if (e.note) out.push('note: ' + e.note);
      if (e.record) out.push('distribution record: source ' + e.record.source + '; replacement: ' + e.record.replace);
      if (c.files.length) out.push('files: ' + c.files.join(', '));
      out.push('', text || '(licence text missing)', '');
    }
  };
  section('CPython and the standard library', (c) => c.where === 'sidecar' && /^cpython$/i.test(c.component));
  hr('Python packages in the sidecar');
  for (const [dist, label, licence] of [['pillow', 'Pillow', 'HPND'], ['fonttools', 'fontTools', 'MIT']]) {
    const version = distVersion(pysite, dist);
    const text = ctx.distInfo(dist);
    if (!version || !text) problems.push('no licence text: ' + label);
    components.set(label + ' ' + version, { component: label, version: version || 'unknown', entry: { class: 'none', licence }, pkg: null, files: [], where: 'python' });
    out.push('### ' + label + ' ' + (version || '?'), 'licence: ' + licence, '', text || '(missing)', '');
  }
  section('The libraries of the wheels and the interpreter', (c) => c.where === 'sidecar' && !/^cpython$/i.test(c.component) && c.entry.class !== 'gpl-exception');
  section("PyInstaller's bootloader", (c) => c.entry.class === 'gpl-exception');
  section('Electron native libraries', (c) => c.where === 'electron');
  section('AppImage usr/lib libraries', (c) => c.where === 'usrlib');
  section('AppImage runtime', (c) => c.where === 'appimage-runtime');
  if (toolsetRecord) {
    hr('AppImage toolset modification');
    out.push('The AppImage was built with a copy of electron-builder\'s ' + toolsetRecord.toolset + ' toolset (archive ' + toolsetRecord.archive + ', sha256 ' + toolsetRecord.archive_sha256 + ')',
      'from which these files were removed (sha256 of each):', ...Object.entries(toolsetRecord.removed).map(([k, v]) => '  ' + k + '  ' + v), '', 'Reason: ' + toolsetRecord.why, '');
  }
  hr('Copyleft check');
  const copyleft = [...components.values()].filter((c) => ['lgpl', 'gpl-exception', 'gcc-rle', 'gpl'].includes(c.entry.class));
  for (const c of copyleft) out.push('- ' + c.component + ' ' + c.version + ' (' + c.entry.class + ', ' + c.entry.licence + ')');
  if (!copyleft.length) out.push('(none)');
  out.push('', 'release gate (D8): corresponding sources archived: ' + (archived ? 'YES' : 'NO'));
  return { text: out.join('\n') + '\n', problems, components: [...components.values()].map((c) => ({ component: c.component, version: c.version, class: c.entry.class, licence: c.entry.licence })) };
}

async function main(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 2) args[argv[i].replace(/^--/, '')] = argv[i + 1];
  const need = ['sidecar', 'provenance', 'electron', 'usrlib', 'pysite', 'repo', 'meta', 'out'];
  const missing = need.filter((k) => !args[k]);
  if (missing.length) { process.stderr.write('third-party.mjs: missing --' + missing.join(' --') + '\n'); return 2; }
  const map = JSON.parse(fs.readFileSync(args.map || path.join(HERE, 'third-party-map.json'), 'utf8'));
  const provenance = JSON.parse(fs.readFileSync(args.provenance, 'utf8'));
  const r = await generate({ sidecar: args.sidecar, provenance, electron: args.electron, usrlib: args.usrlib, pysite: args.pysite, repo: args.repo,
    meta: args.meta, map, sources: args.sources, licencesDir: args.licences,
    toolsetRecord: args['toolset-record'] ? JSON.parse(fs.readFileSync(args['toolset-record'], 'utf8')) : undefined });
  if (r.problems.length) { process.stderr.write(r.problems.join('\n') + '\n'); return 1; }
  fs.writeFileSync(args.out, r.text);
  process.stdout.write('wrote ' + args.out + ' (' + r.components.length + ' components)\n');
  return 0;
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  main(process.argv.slice(2)).then((code) => process.exit(code));
}
