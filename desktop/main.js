'use strict';
// SVF maker desktop shell: spawns the maker sidecar, adds the per-launch token header, hands the page the four-function
// bridge and stops the sidecar cleanly (docs/superpowers/specs/2026-11-05-maker-desktop-design.md, section 6).
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const { app, BrowserWindow, Menu, dialog, ipcMain, session, shell } = require('electron');

const { createSupervisor } = require('./lib/supervisor.js');
const { isOurs, withToken } = require('./lib/guard.js');
const budget = require('./lib/budget.js');
const { restartAllowed } = require('./lib/restart.js');
const { readSandbox, sandboxText } = require('./lib/sandbox.js');
const { resolveLaunch } = require('./lib/paths.js');
const { createLog, pathsLine, redactLine } = require('./lib/log.js');
const { loadState, saveState } = require('./lib/state.js');

const APP_VERSION = require('./package.json').version;

// The guards every web contents gets (spec 6.4): the main window, a devtools window, anything created later. They read
// the running start()'s state at call time.
let active = null;
let guardsInstalled = false;
function installGuards() {
  if (guardsInstalled) return;
  guardsInstalled = true;
  app.on('web-contents-created', (_e, contents) => {
    const allowed = (url) => active && isOurs(active.origin(), url, { startingUrl: active.startingUrl, devtools: active.devtools });
    contents.on('will-navigate', (e, url) => { if (!allowed(url)) e.preventDefault(); });
    contents.on('will-redirect', (e, url) => { if (!allowed(url)) e.preventDefault(); });
    contents.setWindowOpenHandler(() => ({ action: 'deny' }));
    contents.on('will-attach-webview', (e) => e.preventDefault());
  });
}

async function start({ smoke, resourcesPath, env, userData, quitOnClose = true, launch: launchOverride } = {}) {
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
  // launchOverride: a test seam (the e2e wraps the real command in a stub that prints a known stderr line)
  const launch = launchOverride || resolveLaunch({ resourcesPath, appDir, env, pid: process.pid, userData });
  fs.mkdirSync(launch.data, { recursive: true });
  const stateFile = path.join(userData, 'shell-state.json');
  const state = loadState(stateFile);
  const startingUrl = pathToFileURL(path.join(appDir, 'starting.html')).href;
  const devtools = env.SVF_MAKER_DEVTOOLS === '1';
  const iconPath = [path.join(appDir, 'build', 'icon.png'), path.join(resourcesPath || '', 'icon.png')].find((p) => fs.existsSync(p));

  const handle = { win: null, log, state, quitting: false };
  let lastUrl = null;                                   // the maker page the window showed last (its query string included)
  let reloaded = false;
  const sup = createSupervisor({ launch, parentEnv: env, log, onUnexpectedExit: (code, signal) => onSidecarExit(code, signal) });
  const sidecar = sup.sidecar;                           // the one mutable object every handler reads at call time
  handle.sidecar = sidecar;
  const origin = () => sidecar.origin || 'http://127.0.0.1:0';
  active = { origin, startingUrl, devtools };
  installGuards();

  const ses = session.fromPartition('maker');              // no persist: prefix, so nothing reaches the disk
  ses.webRequest.onBeforeSendHeaders({ urls: ['http://127.0.0.1/*', 'http://[::1]/*'] }, (details, cb) => {
    cb({ requestHeaders: withToken(details.url, details.requestHeaders, sidecar) });
  });
  ses.webRequest.onBeforeRequest({ urls: ['<all_urls>'] }, (details, cb) => {
    cb({ cancel: !isOurs(origin(), details.url, { startingUrl, devtools, subresource: details.resourceType !== 'mainFrame' }) });
  });
  ses.on('will-download', (e) => e.preventDefault());
  ses.setPermissionRequestHandler((_wc, _perm, cb) => cb(false));
  ses.setPermissionCheckHandler(() => false);
  ses.setDevicePermissionHandler(() => false);

  let saveTimer = null;
  const flush = () => { clearTimeout(saveTimer); saveTimer = null; try { saveState(stateFile, state); } catch (e) { /* ignore */ } };
  const saveSoon = () => { clearTimeout(saveTimer); saveTimer = setTimeout(flush, 500); };

  // ---- the sidecar ---------------------------------------------------------------------------------------------
  // The failure path of the initial start and of a restart: stop whatever is alive, say why, quit.
  async function failStart(e, win) {
    log.line('start failure: ' + redactLine(e.message));
    await sup.cleanupAfterFailure(e);
    if (!sup.quitting) {
      const last = e.ring ? e.ring.lines().slice(-20).map(redactLine).join('\n') : '';
      const busy = e.busy ? '\nAnother maker is still shutting down; try again in a moment.' : '';
      await dialog.showMessageBox(win && !win.isDestroyed() ? win : null, { type: 'error', message: String(e.message) + busy, detail: last, buttons: ['Quit'] });
    }
    app.quit();
  }

  async function onSidecarExit(code, signal) {
    if (!restartAllowed(sup.history, Date.now())) {
      log.line('restart refused: too many restarts');
      await dialog.showMessageBox(handle.win, { type: 'error', message: 'The maker stopped (exit ' + code + ') too often.', buttons: ['Quit'] });
      app.quit();
      return;
    }
    const r = await dialog.showMessageBox(handle.win, { type: 'error', message: 'The maker stopped (exit ' + (code === null ? signal : code) + '). Restart it?',
      buttons: ['Restart', 'Quit'], defaultId: 0 });
    if (r.response !== 0) { log.line('restart declined'); app.quit(); return; }
    log.line('restart allowed');
    sup.history.push(Date.now());
    try {
      await sup.start();
      lastUrl = sidecar.origin + '/';
      if (handle.win && !handle.win.isDestroyed()) await handle.win.loadURL(lastUrl);
    } catch (e) {
      if (e.cancelled) return;
      await failStart(e, handle.win);
    }
  }

  // ---- the window ----------------------------------------------------------------------------------------------
  const win = new BrowserWindow(Object.assign({
    width: 1200, height: 800, show: false, title: 'SVF maker', icon: iconPath,
    webPreferences: { preload: path.join(appDir, 'preload.js'), contextIsolation: true, sandbox: true, nodeIntegration: false,
      nodeIntegrationInWorker: false, webSecurity: true, allowRunningInsecureContent: false, spellcheck: false,
      partition: 'maker', devTools: devtools },
  }, state.bounds || {}));
  handle.win = win;
  win.once('ready-to-show', () => win.show());
  win.on('resize', () => { state.bounds = win.getBounds(); saveSoon(); });
  win.on('move', () => { state.bounds = win.getBounds(); saveSoon(); });
  win.webContents.setZoomFactor(state.zoom || 1);
  const remember = (url) => { if (sidecar.origin && url.startsWith(sidecar.origin + '/')) lastUrl = url; };
  win.webContents.on('did-navigate', (_e, url) => remember(url));
  win.webContents.on('did-navigate-in-page', (_e, url) => remember(url));
  win.webContents.on('did-finish-load', () => { if (sidecar.origin && win.webContents.getURL().startsWith(sidecar.origin + '/')) reloaded = false; });
  win.webContents.on('render-process-gone', async () => {
    log.line('renderer gone');
    if (!reloaded) {                                    // the first crash since the last clean load: the same page again
      reloaded = true;
      if (lastUrl) win.loadURL(lastUrl); else win.loadFile(path.join(appDir, 'starting.html'));
      return;
    }
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
  const sidecarVersion = () => {                         // the packaged sidecar reports its own version and Python
    if (launch.mode !== 'packaged') return '';
    try { return String(spawnSync(launch.cmd, ['--version'], { timeout: 5000, env: { PATH: '' } }).stdout || '').trim(); } catch (e) { return ''; }
  };
  const about = async () => {
    const buildId = (() => { try { return fs.readFileSync(path.join(launch.repo, 'BUILD_ID'), 'utf8').split('\n')[0]; } catch (e) { return 'unknown'; } })();
    const r = await dialog.showMessageBox(win, { type: 'info', title: 'About SVF maker', buttons: ['OK', 'Third-party licences'],
      message: 'SVF maker ' + APP_VERSION, detail: ['build ' + buildId, 'Electron ' + process.versions.electron, 'Chromium ' + process.versions.chrome,
        'Node ' + process.versions.node, sidecarVersion(), handle.sandboxLine || ''].filter(Boolean).join('\n') });
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
    flush();                                              // a pending debounced save must not be lost to app.exit
    stopping = sup.stopAll();                             // every child, a pending one included
    return stopping;
  };
  handle.stop = stop;
  handle.flush = flush;
  handle.sup = sup;
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
    await sup.start();
  } catch (e) {
    clearTimeout(showStarting);
    if (e.cancelled) return handle;                     // quit during the handshake: stopAll has already dealt with the child
    await failStart(e, win);
    return handle;
  }
  clearTimeout(showStarting);
  lastUrl = sidecar.origin + '/';
  await win.loadURL(lastUrl);

  // the renderer's sandbox state, once, for the log and About
  const userns = (() => { try { const r = spawnSync('unshare', ['-Ur', 'true'], { timeout: 5000 }); return r.error ? 'unknown' : (r.status === 0 ? 'available' : 'unavailable'); } catch (e) { return 'unknown'; } })();
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

// The app entry. Electron's require.main is not this module, and module.parent is not reliable inside app.asar (the
// packaged app never started with it); the one embedder, test/e2e.js, sets global.SVF_MAKER_EMBEDDED first.
if (!global.SVF_MAKER_EMBEDDED) {
  app.whenReady().then(() => start()).catch((e) => { process.stderr.write(String(e && e.stack || e) + '\n'); app.exit(1); });
}
module.exports = { start };
