'use strict';
const fs = require('node:fs');
const path = require('node:path');

// How to start the sidecar: packaged (the frozen executable under resources/) or development (python3 on the checkout).
// Windows (t_9b8f56f0): the executable is svf-maker-sidecar.exe, the development interpreter is `python` (the python.org
// installer and actions/setup-python name it so), and the sidecar also gets --stop-on-eof: Windows has no SIGTERM, so the
// shell asks for a clean stop by closing the sidecar's stdin (lib/shutdown.js).
function resolveLaunch({ resourcesPath, appDir, env, pid, userData, exists = fs.existsSync, platform = process.platform }) {
  const win = platform === 'win32';
  const P = win ? path.win32 : path.posix;
  const extra = win ? ['--stop-on-eof'] : [];
  const exe = resourcesPath ? P.join(resourcesPath, 'sidecar', 'svf-maker-sidecar', win ? 'svf-maker-sidecar.exe' : 'svf-maker-sidecar') : null;
  if (exe && exists(exe) && env.SVF_MAKER_DEV !== '1') {
    return { mode: 'packaged', cmd: exe, args: ['serve', '--exit-with-parent=' + pid, ...extra],
      repo: P.join(resourcesPath, 'repo'), data: P.join(userData, 'maker') };
  }
  const checkout = env.SVF_MAKER_DEV_REPO || P.dirname(appDir);
  return { mode: 'dev', cmd: win ? winPython(env, exists) : 'python3', args: ['-P', P.join(checkout, 'maker', 'server.py'), '--exit-with-parent=' + pid, ...extra],
    repo: checkout, data: P.join(userData, 'maker-dev') };
}
// Windows: `python` resolved on PATH's absolute folders only. A bare name would be looked up in the current folder first
// (CreateProcess, libuv), so a python.exe planted in the shell's working folder would run; none found is an error.
function winPython(env, exists) {
  const dirs = String(env.PATH || env.Path || '').split(';').filter((d) => path.win32.isAbsolute(d) && /^([a-zA-Z]:\\|\\\\)/.test(d));
  for (const d of dirs) {
    const exe = path.win32.join(d, 'python.exe');
    if (exists(exe)) return exe;
  }
  throw new Error('development mode (SVF_MAKER_DEV=1) on Windows needs python.exe in an absolute folder on PATH; none was found');
}
module.exports = { resolveLaunch };
