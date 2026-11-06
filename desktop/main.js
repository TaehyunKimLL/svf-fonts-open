'use strict';
// SVF maker desktop shell: spawns the maker sidecar, adds the per-launch token header, hands the page the four-function
// bridge and stops the sidecar cleanly (docs/superpowers/specs/2026-11-05-maker-desktop-design.md, section 6).
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const { app, BrowserWindow, Menu, dialog, ipcMain, session, shell } = require('electron');

const { buildEnv } = require('./lib/env.js');
const { parsePortLine } = require('./lib/portline.js');
const { isOurs, withToken } = require('./lib/guard.js');
const budget = require('./lib/budget.js');
const { stopSidecar } = require('./lib/shutdown.js');
const { restartAllowed } = require('./lib/restart.js');
const { readSandbox, sandboxText } = require('./lib/sandbox.js');
const { resolveLaunch } = require('./lib/paths.js');
const { createLog, pathsLine, redactLine, Ring } = require('./lib/log.js');
const { loadState, saveState } = require('./lib/state.js');

const APP_VERSION = require('./package.json').version;

async function start({ smoke, resourcesPath, env, userData, quitOnClose = true } = {}) {
  smoke = smoke === undefined ? process.env.SVF_MAKER_SMOKE === '1' : smoke;
  resourcesPath = resourcesPath || process.resourcesPath;
  env = env || process.env;
  userData = userData || app.getPath('userData');
  const appDir = __dirname;

  if (!app.requestSingleInstanceLock()) {              // the loser quits before any spawn
    app.quit();
    return null;
  }
  const log = createLog({ dir: path.join(userData, 'logs'), toStderr: env.SVF_MAKER_SHELL_LOG === 'stderr' });
  log.line('shell pid=' + process.pid + ' version=' + APP_VERSION);
  const launch = resolveLaunch({ resourcesPath, appDir, env, pid: process.pid, userData });
  fs.mkdirSync(launch.data, { recursive: true });
  const stateFile = path.join(userData, 'shell-state.json');
  const state = loadState(stateFile);
  const startingUrl = pathToFileURL(path.join(appDir, 'starting.html')).href;
  const devtools = env.SVF_MAKER_DEVTOOLS === '1';

  // the one mutable sidecar object every handler reads at call time
  const sidecar = { child: null, port: 0, origin: '', token: '', pid: 0, mode: launch.mode };
  const handle = { win: null, sidecar, log, state, quitting: false };
  const history = [];
  let reloaded = false;

  const ses = session.fromPartition('maker');              // no persist: prefix, so nothing reaches the disk
  ses.webRequest.onBeforeSendHeaders({ urls: ['http://127.0.0.1/*'] }, (details, cb) => {
    cb({ requestHeaders: withToken(details.url, details.requestHeaders, sidecar) });
  });
  const origin = () => sidecar.origin || 'http://127.0.0.1:0';
  ses.webRequest.onBeforeRequest({ urls: ['<all_urls>'] }, (details, cb) => {
    cb({ cancel: !isOurs(origin(), details.url, { startingUrl, devtools }) });
  });
  ses.on('will-download', (e) => e.preventDefault());
  ses.setPermissionRequestHandler((_wc, _perm, cb) => cb(false));
  ses.setPermissionCheckHandler(() => false);
  ses.setDevicePermissionHandler(() => false);

  const saveSoon = (() => {
    let t = null;
    return () => { clearTimeout(t); t = setTimeout(() => { try { saveState(stateFile, state); } catch (e) { /* ignore */ } }, 500); };
  })();

  // ---- the sidecar ---------------------------------------------------------------------------------------------
  function spawnSidecar() {
    return new Promise((resolve, reject) => {
      const { env: childEnv, token } = buildEnv(env, { repo: launch.repo, data: launch.data });
      const child = spawn(launch.cmd, launch.args, { detached: true, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true,
        cwd: os.homedir(), env: childEnv });
      const ring = new Ring(50);
      let out = '';
      let settled = false;
      const settle = (fn, v) => { if (!settled) { settled = true; clearTimeout(timer); fn(v); } };
      const timer = setTimeout(() => {
        const err = new Error('the maker did not start within ' + budget.HANDSHAKE_S + ' s');
        err.ring = ring; err.child = child;
        settle(reject, err);
      }, budget.HANDSHAKE_S * 1000);
      child.on('error', (e) => { const err = new Error('could not start the maker: ' + e.code); err.ring = ring; settle(reject, err); });
      child.stdout.on('data', (chunk) => {                    // read for the sidecar's whole life; kept only until the port line
        if (settled) return;
        out += chunk.toString('utf8');
        const parsed = parsePortLine(out);
        if (parsed) {
          Object.assign(sidecar, { child, port: parsed.port, origin: 'http://' + (parsed.host === '::1' ? '[::1]' : parsed.host) + ':' + parsed.port,
            token, pid: child.pid });
          log.line('sidecar port=' + parsed.port);
          settle(resolve, sidecar);
        }
      });
      let errBuf = '';
      child.stderr.on('data', (chunk) => {
        errBuf += chunk.toString('utf8');
        let i;
        while ((i = errBuf.indexOf('\n')) >= 0) { ring.push(errBuf.slice(0, i)); errBuf = errBuf.slice(i + 1); }
      });
      log.line('sidecar start mode=' + launch.mode + ' pid=' + child.pid);
      child.on('exit', (code, signal) => {
        log.line('sidecar exit code=' + code + ' signal=' + signal);
        logRing(ring);                                        // the sidecar's last stderr lines, redacted (paths and hex removed)
        if (!settled) {
          const err = new Error('the maker exited before it was ready (exit ' + code + ')');
          err.ring = ring;
          settle(reject, err);
        } else if (child === sidecar.child && !handle.quitting) {
          onSidecarExit(code, signal, ring);
        }
      });
      handle.ring = ring;
    });
  }

  function logRing(ring) {
    if (!ring) return;
    for (const line of ring.lines()) log.line('sidecar stderr: ' + redactLine(line));
  }

  async function onSidecarExit(code, signal, ring) {
    if (!restartAllowed(history, Date.now())) {
      await dialog.showMessageBox(handle.win, { type: 'error', message: 'The maker stopped (exit ' + code + ') too often.', buttons: ['Quit'] });
      app.quit();
      return;
    }
    const r = await dialog.showMessageBox(handle.win, { type: 'error', message: 'The maker stopped (exit ' + (code === null ? signal : code) + '). Restart it?',
      buttons: ['Restart', 'Quit'], defaultId: 0 });
    if (r.response !== 0) { app.quit(); return; }
    history.push(Date.now());
    try {
      await spawnSidecar();
      if (handle.win && !handle.win.isDestroyed()) await handle.win.loadURL(sidecar.origin + '/');
    } catch (e) {
      await dialog.showMessageBox(handle.win, { type: 'error', message: String(e.message), buttons: ['Quit'] });
      app.quit();
    }
  }

  // ---- the window ----------------------------------------------------------------------------------------------
  const win = new BrowserWindow(Object.assign({
    width: 1200, height: 800, show: false, title: 'SVF maker',
    icon: path.join(appDir, 'build', 'icon.png'),
    webPreferences: { preload: path.join(appDir, 'preload.js'), contextIsolation: true, sandbox: true, nodeIntegration: false,
      nodeIntegrationInWorker: false, webSecurity: true, allowRunningInsecureContent: false, spellcheck: false,
      partition: 'maker', devTools: devtools },
  }, state.bounds || {}));
  handle.win = win;
  win.once('ready-to-show', () => win.show());
  win.on('resize', () => { state.bounds = win.getBounds(); saveSoon(); });
  win.on('move', () => { state.bounds = win.getBounds(); saveSoon(); });
  win.webContents.setZoomFactor(state.zoom || 1);
  win.webContents.on('will-navigate', (e, url) => { if (!isOurs(origin(), url, { startingUrl, devtools })) e.preventDefault(); });
  win.webContents.on('will-redirect', (e, url) => { if (!isOurs(origin(), url, { startingUrl, devtools })) e.preventDefault(); });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-attach-webview', (e) => e.preventDefault());
  win.webContents.on('render-process-gone', async () => {
    log.line('renderer gone');
    if (!reloaded && sidecar.origin) { reloaded = true; win.loadURL(sidecar.origin + '/'); return; }
    await dialog.showMessageBox(win, { type: 'error', message: 'The window crashed twice.', buttons: ['Quit'] });
    app.quit();
  });
  win.on('closed', () => { handle.win = null; });

  // ---- IPC -----------------------------------------------------------------------------------------------------
  const fromPage = (event) => {
    try {
      const f = event.senderFrame;
      if (f && sidecar.origin && new URL(f.url).origin === sidecar.origin) return true;
    } catch (e) { /* fall through */ }
    log.line('ipc refused: sender is not the maker page');
    return false;
  };
  const handlers = {
    'maker:pick-files': async () => {
      const r = await dialog.showOpenDialog(win, { properties: ['openFile', 'multiSelections'] });
      const paths = r.canceled ? [] : r.filePaths;
      log.line(pathsLine('pick-files', paths));
      return paths;
    },
    'maker:pick-folder': async () => {
      const r = await dialog.showOpenDialog(win, { properties: ['openDirectory'] });
      const paths = r.canceled ? [] : r.filePaths.slice(0, 1);
      log.line(pathsLine('pick-folder', paths));
      return paths;
    },
    'maker:pick-output-dir': async () => {
      const opts = { properties: ['openDirectory', 'createDirectory'] };
      if (state.lastOutputDir) opts.defaultPath = state.lastOutputDir;
      const r = await dialog.showOpenDialog(win, opts);
      if (r.canceled || !r.filePaths.length) { log.line(pathsLine('pick-output-dir', [])); return null; }
      const picked = r.filePaths[0];
      let real = picked;
      try { real = fs.realpathSync(picked); } catch (e) { /* keep as given */ }
      state.lastOutputDir = picked;
      state.handedOut = state.handedOut.filter((p) => p !== real).concat([real]).slice(-32);
      saveSoon();
      log.line(pathsLine('pick-output-dir', [picked]));
      return picked;
    },
    'maker:open-output': async () => {
      const m = /[?&]job=([0-9a-f]{12})(&|$)/.exec(win.webContents.getURL().split('#')[0]);
      if (!m) { log.line('open-output: refused'); return; }
      let outputDir = null;
      try {
        const res = await fetch(sidecar.origin + '/api/jobs/' + m[1], { headers: { 'X-Maker-Token': sidecar.token } });
        if (res.ok) outputDir = (await res.json()).output_dir;
      } catch (e) { /* refused below */ }
      let real = null;
      try { real = outputDir ? fs.realpathSync(outputDir) : null; } catch (e) { real = null; }
      if (real && state.handedOut.includes(real)) { shell.showItemInFolder(outputDir); log.line('open-output: ok'); } else log.line('open-output: refused');
    },
  };
  for (const [channel, fn] of Object.entries(handlers)) {
    ipcMain.removeHandler(channel);
    ipcMain.handle(channel, async (event) => {
      if (!fromPage(event)) throw new Error('refused');
      return fn(event);
    });
  }

  // ---- menu, quit ----------------------------------------------------------------------------------------------
  const zoom = (delta) => { state.zoom = Math.min(3, Math.max(0.5, Math.round((win.webContents.getZoomFactor() + delta) * 100) / 100)); win.webContents.setZoomFactor(state.zoom); saveSoon(); };
  const about = async () => {
    const buildId = (() => { try { return fs.readFileSync(path.join(launch.repo, 'BUILD_ID'), 'utf8').split('\n')[0]; } catch (e) { return 'unknown'; } })();
    const r = await dialog.showMessageBox(win, { type: 'info', title: 'About SVF maker', buttons: ['OK', 'Third-party licences'],
      message: 'SVF maker ' + APP_VERSION, detail: ['build ' + buildId, 'Electron ' + process.versions.electron, 'Chromium ' + process.versions.chrome,
        'Node ' + process.versions.node, handle.sandboxLine || ''].join('\n') });
    if (r.response === 1) shell.openPath(path.join(resourcesPath, 'THIRD-PARTY.txt'));
  };
  const menu = Menu.buildFromTemplate([
    { label: 'File', submenu: [{ label: 'Open output folder', click: () => handlers['maker:open-output']() }, { role: 'quit' }] },
    { label: 'View', submenu: [{ role: 'reload' }, { label: 'Actual size', click: () => { state.zoom = 1; win.webContents.setZoomFactor(1); saveSoon(); } },
      { label: 'Zoom in', accelerator: 'CommandOrControl+Plus', click: () => zoom(0.1) }, { label: 'Zoom out', accelerator: 'CommandOrControl+-', click: () => zoom(-0.1) },
      ...(devtools ? [{ role: 'toggleDevTools' }] : [])] },
    { label: 'Help', submenu: [{ label: 'About', click: about }] },
  ]);
  Menu.setApplicationMenu(menu);

  let stopping = null;
  const stop = () => {
    if (stopping) return stopping;
    handle.quitting = true;
    log.line('stopping the maker...');
    stopping = sidecar.child ? stopSidecar(sidecar.child, { termWaitS: budget.STOP_WAIT_S, killWaitS: budget.KILL_WAIT_S }) : Promise.resolve({});
    return stopping;
  };
  handle.stop = stop;
  handle.shutdown = async () => { await stop(); if (handle.win && !handle.win.isDestroyed()) handle.win.destroy(); };
  if (quitOnClose) {
    app.on('window-all-closed', () => app.quit());
    let quitState = 0;                                  // 0 running, 1 stopping the sidecar, 2 done
    app.on('before-quit', (e) => {
      if (quitState === 2) return;
      e.preventDefault();
      if (quitState === 1) return;
      quitState = 1;
      stop().then(() => { quitState = 2; app.exit(0); });
    });
    for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(sig, () => app.quit());
    app.on('second-instance', () => { if (handle.win) { if (handle.win.isMinimized()) handle.win.restore(); handle.win.focus(); } });
  }

  // ---- go ------------------------------------------------------------------------------------------------------
  const showStarting = setTimeout(() => { if (!sidecar.origin && handle.win) handle.win.loadFile(path.join(appDir, 'starting.html')); }, budget.STARTING_PAGE_S * 1000);
  try {
    await spawnSidecar();
  } catch (e) {
    clearTimeout(showStarting);
    log.line('start failure: ' + redactLine(e.message));
    handle.quitting = true;
    if (sidecar.child || e.child) await stopSidecar(e.child || sidecar.child, { termWaitS: budget.STOP_WAIT_S, killWaitS: budget.KILL_WAIT_S });
    const last = e.ring ? e.ring.lines().slice(-20).map(redactLine).join('\n') : '';
    await dialog.showMessageBox(win, { type: 'error', message: String(e.message), detail: last, buttons: ['Quit'] });
    app.quit();
    return handle;
  }
  clearTimeout(showStarting);
  await win.loadURL(sidecar.origin + '/');

  // the renderer's sandbox state, once, for the log and About
  const userns = (() => { try { return spawnSync('unshare', ['-Ur', 'true'], { timeout: 5000 }).status === 0 ? 'available' : 'unavailable'; } catch (e) { return 'unknown'; } })();
  const noSandboxSwitch = process.argv.includes('--no-sandbox');
  handle.sandboxLine = sandboxText(readSandbox(win.webContents.getOSProcessId()), { noSandboxSwitch, userns });
  log.line('sandbox ' + handle.sandboxLine);

  if (smoke) {
    try {
      const status = await win.webContents.executeJavaScript("fetch('/api/caps').then((r) => r.status)");
      if (status === 200) process.stdout.write('svf-maker smoke ok ' + win.webContents.getTitle() + '\n');
      else process.stdout.write('svf-maker smoke FAIL status ' + status + '\n');
    } catch (e) { process.stdout.write('svf-maker smoke FAIL ' + e.message + '\n'); }
    win.close();
  }
  return handle;
}

if (!module.parent) {                                  // the app entry (Electron's require.main is not this module); e2e.js requires us
  app.whenReady().then(() => start()).catch((e) => { process.stderr.write(String(e && e.stack || e) + '\n'); app.exit(1); });
}
module.exports = { start };
