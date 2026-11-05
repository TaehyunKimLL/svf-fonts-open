// Linux sandbox probe: for each child process report Seccomp, NoNewPrivs and whether it is in a different user namespace.
const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
function info(pid) {
  try {
    const st = fs.readFileSync(`/proc/${pid}/status`, 'utf8');
    const get = (k) => (st.match(new RegExp('^' + k + ':\\s*(\\S+)', 'm')) || [])[1];
    let userns = 'n/a';
    try { userns = fs.readlinkSync(`/proc/${pid}/ns/user`) !== fs.readlinkSync(`/proc/self/ns/user`) ? 'own' : 'same'; } catch (e) { userns = 'err:' + e.code; }
    return { seccomp: get('Seccomp'), nonewprivs: get('NoNewPrivs'), userns };
  } catch (e) { return { err: e.code }; }
}
app.whenReady().then(async () => {
  const win = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, sandbox: true, nodeIntegration: false } });
  await win.loadURL('data:text/html,<title>sb</title>ok');
  const m = app.getAppMetrics().map((p) => ({ type: p.type, pid: p.pid, ...info(p.pid) }));
  console.log('SANDBOX ' + JSON.stringify({ noSandboxFlag: process.argv.includes('--no-sandbox'), metrics: m }));
  app.quit();
});
