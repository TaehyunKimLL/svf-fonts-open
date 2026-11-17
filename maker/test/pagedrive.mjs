// pagedrive.mjs CHROME URL SCRIPT_FILE [--header NAME:VALUE]... [--preload FILE] [--files SELECTOR=PATH]... - loads URL in headless Chrome and evaluates the async function body in
// SCRIPT_FILE in the page (helpers: sleep(ms), waitFor(fn, ms)); prints the JSON it returns on stdout. Chrome is driven
// over the DevTools protocol with node's built-in WebSocket (no playwright). Exit 1 with the page's error on stderr.
import { spawn } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, existsSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir, homedir } from 'node:os';
import { join } from 'node:path';

const [chrome, url, scriptFile, ...options] = process.argv.slice(2);
// --header NAME:VALUE (any number) is sent with every request the page makes (Network.setExtraHTTPHeaders, the way the
// Electron shell adds the maker's token); --preload FILE is evaluated in every new document before the page's own
// scripts run (Page.addScriptToEvaluateOnNewDocument: a stand-in for the shell's preload bridge).
const extraHeaders = {};
let preloadFile = null;
// --files SELECTOR=PATH (repeatable): after the page's load event and before the script runs, PATH is put into the file
// input SELECTOR matches (DOM.setFileInputFiles), as a user choosing it in the dialog would; no match exits 1. The
// selector ends at the first `=` outside square brackets (`input[type=file]=/x` works).
const fileInputs = [];
for (let i = 0; i < options.length; i++) {
  if (options[i] === '--header') {
    const text = options[++i] || '';
    const cut = text.indexOf(':');
    extraHeaders[text.slice(0, cut)] = text.slice(cut + 1);
  } else if (options[i] === '--preload') {
    preloadFile = options[++i];
  } else if (options[i] === '--files') {
    const text = options[++i] || '';
    let depth = 0, cut = -1;
    for (let k = 0; k < text.length && cut < 0; k++) {
      if (text[k] === '[') depth++;
      else if (text[k] === ']') depth--;
      else if (text[k] === '=' && depth === 0) cut = k;
    }
    if (cut < 1) { process.stderr.write('pagedrive: --files wants SELECTOR=PATH\n'); process.exit(1); }
    fileInputs.push([text.slice(0, cut), text.slice(cut + 1)]);
  }
}
// Chrome's singleton socket lives under TMPDIR and a unix socket path is limited to 107 bytes: when the temp directory
// is long (a TMP_DIR the project rule puts under $HOME/work/tmp) the profile goes to a short directory instead.
// It is removed with Chrome, as before.
let base = tmpdir();
let prefix = 'pagedrive-';
if (join(base, 'pagedrive-XXXXXX', 'tmp').length > 60) {   // 60 + Chrome's /.org.chromium.Chromium.XXXXXX/SingletonSocket < 107
  base = join(homedir(), 'work', 'tmp');                   // the authorised scratch root (project rule), never /dev/shm or /tmp
  prefix = 'pd-';
}
const profile = mkdtempSync(join(base, prefix));
if (process.env.PAGEDRIVE_PROFILE_FILE) writeFileSync(process.env.PAGEDRIVE_PROFILE_FILE, profile);
// Chrome's own temp files (/tmp/com.google.Chrome.*) go under the profile and leave with it
mkdirSync(join(profile, 'tmp'));
const proc = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-sandbox', '--remote-debugging-port=0',
  '--user-data-dir=' + profile, 'about:blank'],
  { stdio: 'ignore', env: { ...process.env, TMPDIR: join(profile, 'tmp') } });
const exited = new Promise((res) => proc.once('exit', res));
let ws = null;
// Ask Chrome to close over CDP, wait for it (bounded, then SIGKILL and wait again) before the profile goes: its
// children are still writing the cache while it shuts down.
async function shutdown() {
  const wait = (ms) => Promise.race([exited, new Promise((r) => setTimeout(r, ms))]);
  if (proc.exitCode === null && proc.signalCode === null) {
    try { ws && ws.readyState === 1 && ws.send(JSON.stringify({ id: 999999, method: 'Browser.close' })); } catch {}
    await wait(10000);
    if (proc.exitCode === null && proc.signalCode === null) { try { proc.kill('SIGKILL'); } catch {} await wait(10000); }
  }
  for (let i = 0; i < 40 && existsSync(profile); i++) {      // Chrome's children may write a moment longer
    try { rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }); } catch {}
    if (existsSync(profile)) await new Promise((r) => setTimeout(r, 250));
  }
}
process.on('SIGTERM', () => { try { proc.kill('SIGKILL'); } catch {} try { rmSync(profile, { recursive: true, force: true }); } catch {} process.exit(1); });

async function until(fn, ms, what) {
  const end = Date.now() + ms;
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() > end) throw new Error('timeout: ' + what);
    await new Promise((r) => setTimeout(r, 100));
  }
}

// a hung page must not hang the suite: after PAGEDRIVE_WATCHDOG_S seconds (default 200) Chrome is killed and the driver exits 1
const asked = Number(process.env.PAGEDRIVE_WATCHDOG_S);
const watchdogMs = 1000 * (Number.isFinite(asked) && asked > 0 ? asked : 200);   // not a positive number: 200   // raise it for a long flow
setTimeout(async () => { process.stderr.write('pagedrive: watchdog\n'); process.exitCode = 1; await shutdown(); process.exit(1); }, watchdogMs).unref();

try {
  const portFile = join(profile, 'DevToolsActivePort');
  await until(() => existsSync(portFile), 30000, 'chrome start');
  const [port, path] = readFileSync(portFile, 'utf8').trim().split('\n');
  ws = new WebSocket('ws://127.0.0.1:' + port + path);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = () => rej(new Error('websocket')); });
  let id = 0;
  const pending = new Map();
  const events = [];
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); } else events.push(msg);
  };
  const send = (method, params = {}, sessionId) => new Promise((res) => {
    const i = ++id;
    pending.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params, sessionId }));
  });
  const { result: { targetId } } = await send('Target.createTarget', { url: 'about:blank' });
  const { result: { sessionId } } = await send('Target.attachToTarget', { targetId, flatten: true });
  await send('Page.enable', {}, sessionId);
  if (Object.keys(extraHeaders).length) {
    await send('Network.enable', {}, sessionId);
    await send('Network.setExtraHTTPHeaders', { headers: extraHeaders }, sessionId);
  }
  if (preloadFile) await send('Page.addScriptToEvaluateOnNewDocument', { source: readFileSync(preloadFile, 'utf8') }, sessionId);
  await send('Page.navigate', { url }, sessionId);
  await until(() => events.some((e) => e.method === 'Page.loadEventFired' && e.sessionId === sessionId), 60000, 'page load');
  for (const [selector, file] of fileInputs) {
    const doc = await send('DOM.getDocument', { depth: 0 }, sessionId);
    const found = await send('DOM.querySelector', { nodeId: doc.result.root.nodeId, selector }, sessionId);
    if (!found.result || !found.result.nodeId) throw new Error('pagedrive: no element for ' + selector);
    const set = await send('DOM.setFileInputFiles', { files: [file], nodeId: found.result.nodeId }, sessionId);
    if (set.error) throw new Error('pagedrive: cannot set files on ' + selector + ': ' + set.error.message);
  }
  const body = readFileSync(scriptFile, 'utf8');
  const expr = `(async () => { const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    const waitFor = async (fn, ms = 20000) => { const end = Date.now() + ms; for (;;) { const v = await fn(); if (v) return v; if (Date.now() > end) throw new Error('waitFor timeout: ' + fn); await sleep(100); } };
    ${body} })()`;
  const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }, sessionId);
  if (r.result.exceptionDetails) {
    const d = r.result.exceptionDetails;
    throw new Error((d.exception && (d.exception.description || d.exception.value)) || d.text);
  }
  process.stdout.write(JSON.stringify(r.result.result.value));
  ws.close();
} catch (err) {
  process.stderr.write(String(err && err.stack || err) + '\n');
  process.exitCode = 1;
}
await shutdown();
process.exit(process.exitCode || 0);
