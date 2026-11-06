'use strict';
// SIGTERM the sidecar's group, wait, then SIGKILL it and wait again. Resolves {code, signal, escalated}.
function stopSidecar(child, { termWaitS, killWaitS, kill = process.kill }) {
  return new Promise((resolve) => {
    if (!child.pid) {                                      // never spawned (ENOENT, EACCES): nothing to signal
      resolve({ code: null, signal: null, escalated: false });
      return;
    }
    if (child.exitCode !== null || child.signalCode !== null) {
      resolve({ code: child.exitCode, signal: child.signalCode, escalated: false });
      return;
    }
    let escalated = false;
    let done = false;
    const timers = [];
    const finish = (code, signal) => {
      if (done) return;
      done = true;
      timers.forEach(clearTimeout);
      resolve({ code, signal, escalated });
    };
    child.once('exit', finish);
    const send = (sig) => {
      try { kill(-child.pid, sig); } catch (e) { if (e.code !== 'ESRCH') throw e; }
    };
    send('SIGTERM');
    timers.push(setTimeout(() => {
      escalated = true;
      send('SIGKILL');
      timers.push(setTimeout(() => finish(child.exitCode, child.signalCode), killWaitS * 1000));
    }, termWaitS * 1000));
  });
}
module.exports = { stopSidecar };
