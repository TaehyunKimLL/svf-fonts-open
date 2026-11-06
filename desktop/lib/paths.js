'use strict';
const fs = require('node:fs');
const path = require('node:path');

// How to start the sidecar: packaged (the frozen executable under resources/) or development (python3 on the checkout).
function resolveLaunch({ resourcesPath, appDir, env, pid, userData, exists = fs.existsSync }) {
  const exe = resourcesPath ? path.join(resourcesPath, 'sidecar', 'svf-maker-sidecar', 'svf-maker-sidecar') : null;
  if (exe && exists(exe) && env.SVF_MAKER_DEV !== '1') {
    return { mode: 'packaged', cmd: exe, args: ['serve', '--exit-with-parent=' + pid],
      repo: path.join(resourcesPath, 'repo'), data: path.join(userData, 'maker') };
  }
  const checkout = env.SVF_MAKER_DEV_REPO || path.dirname(appDir);
  return { mode: 'dev', cmd: 'python3', args: ['-P', path.join(checkout, 'maker', 'server.py'), '--exit-with-parent=' + pid],
    repo: checkout, data: path.join(userData, 'maker-dev') };
}
module.exports = { resolveLaunch };
