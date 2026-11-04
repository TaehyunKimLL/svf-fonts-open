// pagedrive.mjs CHROME URL SCRIPT_FILE - loads URL in headless Chrome and evaluates the async function body in
// SCRIPT_FILE in the page (helpers: sleep(ms), waitFor(fn, ms)); prints the JSON it returns on stdout. Chrome is driven
// over the DevTools protocol with node's built-in WebSocket (no playwright). Exit 1 with the page's error on stderr.
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [chrome, url, scriptFile] = process.argv.slice(2);
const profile = mkdtempSync(join(tmpdir(), 'pagedrive-'));
const proc = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-sandbox', '--remote-debugging-port=0',
  '--user-data-dir=' + profile, 'about:blank'], { stdio: 'ignore' });
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
  await send('Page.navigate', { url }, sessionId);
  await until(() => events.some((e) => e.method === 'Page.loadEventFired' && e.sessionId === sessionId), 60000, 'page load');
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
