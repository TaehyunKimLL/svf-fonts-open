'use strict';
const fs = require('node:fs');

// The renderer's seccomp / no-new-privs state from /proc/<pid>/status, or null when it cannot be read.
function readSandbox(pid, readFile = fs.readFileSync) {
  try {
    const text = String(readFile('/proc/' + pid + '/status', 'utf8'));
    const seccomp = /^Seccomp:\s*(\d+)/m.exec(text);
    const nnp = /^NoNewPrivs:\s*(\d+)/m.exec(text);
    return { seccomp: seccomp ? Number(seccomp[1]) : null, noNewPrivs: nnp ? Number(nnp[1]) : null };
  } catch (e) {
    return null;
  }
}

// One line for the log and About. The cause of "off" is not inferred from the switch alone.
function sandboxText(state, { noSandboxSwitch, userns }) {
  if (!state || state.seccomp === null || state.seccomp === undefined) return 'renderer sandbox: unknown';
  if (state.seccomp === 0) {
    return 'renderer sandbox: off (' + (noSandboxSwitch ? '--no-sandbox; ' : '') + 'user namespaces ' + (userns || 'unknown') + ')';
  }
  return 'renderer sandbox: on';
}
module.exports = { readSandbox, sandboxText };
