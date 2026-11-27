'use strict';
// SIGTERM the sidecar's group, wait, then SIGKILL it and wait again. Resolves {code, signal, escalated}.
// Windows (t_9b8f56f0) has no signals: the clean stop is the end of the sidecar's stdin (it runs with --stop-on-eof and
// stops as on SIGTERM), the escalation is child.kill() (TerminateProcess). The sidecar's tools sit in Job Objects that
// close with it, so they go with it.
function stopSidecar(child, { termWaitS, killWaitS, kill = process.kill, platform = process.platform }) {
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
    const send = platform === 'win32'
      ? (sig) => {
        if (sig === 'SIGTERM') { try { if (child.stdin && !child.stdin.destroyed) child.stdin.end(); } catch (e) { /* closed already */ } }
        else { try { child.kill('SIGKILL'); } catch (e) { /* gone */ } }
      }
      : (sig) => {
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
