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
const cleanup = () => { try { proc.kill('SIGKILL'); } catch {} try { rmSync(profile, { recursive: true, force: true }); } catch {} };
process.on('exit', cleanup);

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
  const ws = new WebSocket('ws://127.0.0.1:' + port + path);
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
cleanup();
process.exit(process.exitCode || 0);
