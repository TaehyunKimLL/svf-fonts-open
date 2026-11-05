// Electron probe: headless window under xvfb, loads a page over http from a node server, checks that
// onBeforeSendHeaders adds a header only to that origin, that other requests are cancelled, prints JSON, quits.
const { app, BrowserWindow, session } = require('electron');
const http = require('node:http');

const seen = [];
const srv = http.createServer((req, res) => {
  seen.push({ url: req.url, tok: req.headers['x-maker-token'] || null });
  if (req.url === '/') {
    res.writeHead(200, { 'content-type': 'text/html', 'content-security-policy': "default-src 'self'; script-src 'self'; connect-src 'self'" });
    res.end('<!doctype html><title>probe</title><script src="/probe.js"></script>');
  } else if (req.url === '/probe.js') {
    res.writeHead(200, { 'content-type': 'text/javascript' });
    res.end('window.st = "pending"; fetch("/api/caps").then(r => { window.st = r.status; }, e => { window.st = "err:" + e.message; });');
  } else {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end('{"ok":true}');
  }
});
srv.listen(0, '127.0.0.1', async () => {
  const port = srv.address().port;
  const origin = 'http://127.0.0.1:' + port;
  await app.whenReady();
  const ses = session.fromPartition('maker');            // in-memory (no persist:)
  ses.webRequest.onBeforeSendHeaders({ urls: [origin + '/*'] }, (details, cb) => {
    const h = { ...details.requestHeaders };
    if (new URL(details.url).pathname.startsWith('/api/')) h['X-Maker-Token'] = 'deadbeef';
    cb({ requestHeaders: h });
  });
  const cancelled = [];
  ses.webRequest.onBeforeRequest({ urls: ['<all_urls>'] }, (details, cb) => {
    const ok = details.url.startsWith(origin + '/');
    if (!ok) cancelled.push(details.url);
    cb({ cancel: !ok });
  });
  const win = new BrowserWindow({ show: false, webPreferences: { partition: 'maker', contextIsolation: true, sandbox: true, nodeIntegration: false } });
  await win.loadURL(origin + '/');
  await new Promise(r => setTimeout(r, 1500));
  const status = await win.webContents.executeJavaScript('window.st');
  let foreign = 'n/a';
  try { foreign = await win.webContents.executeJavaScript('fetch("http://127.0.0.1:1/x").then(r => r.status, e => "rejected:" + e.message)'); } catch (e) { foreign = 'threw:' + e.message; }
  console.log(JSON.stringify({ electron: process.versions.electron, chrome: process.versions.chrome, node: process.versions.node,
    apiStatus: status, seen, cancelled, foreign }));
  srv.close();
  app.quit();
});
