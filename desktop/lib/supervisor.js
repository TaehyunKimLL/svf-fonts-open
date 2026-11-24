'use strict';
// The sidecar process manager: spawn, handshake, drained pipes, the stderr ring, one stop sequence for every child the
// shell has started (a pending one included), a bounded retry while the data root is still locked by a dying sidecar.
// No Electron here: node --test drives it with stub sidecars.
const { spawn } = require('node:child_process');
const os = require('node:os');
const { buildEnv } = require('./env.js');
const { parsePortLine } = require('./portline.js');
const { stopSidecar } = require('./shutdown.js');
const { Ring, redactLine } = require('./log.js');
const budget = require('./budget.js');

const BUSY_MESSAGE = 'another svf-maker server is using this data root';
const BUSY_RETRY_S = 10;

function createSupervisor({ launch, parentEnv, log, handshakeS = budget.HANDSHAKE_S, termWaitS = budget.STOP_WAIT_S,
  killWaitS = budget.KILL_WAIT_S, busyRetryS = BUSY_RETRY_S, spawnFn = spawn, onUnexpectedExit = () => {} }) {
  const sidecar = { child: null, port: 0, origin: '', token: '', pid: 0, mode: launch.mode };
  const children = new Set();                         // every child started and not yet exited, pending ones included
  const sup = { sidecar, children, quitting: false, failing: false, ring: null, history: [] };

  function logRing(ring) {
    if (!ring) return;
    for (const line of ring.lines()) log.line('sidecar stderr: ' + redactLine(line));
  }

  function attempt() {
    return new Promise((resolve, reject) => {
      const { env, token } = buildEnv(parentEnv, { repo: launch.repo, data: launch.data });
      // Windows: stdin is a pipe the shell keeps open; closing it is the clean stop (--stop-on-eof, lib/shutdown.js)
      const stdin = process.platform === 'win32' ? 'pipe' : 'ignore';
      const child = spawnFn(launch.cmd, launch.args, { detached: true, stdio: [stdin, 'pipe', 'pipe'], windowsHide: true,
        cwd: os.homedir(), env });
      if (child.stdin) child.stdin.on('error', () => {});   // a sidecar that is gone already: EPIPE on the close is fine
      children.add(child);                            // tracked from the spawn on, before any handshake
      const ring = new Ring(50);
      sup.ring = ring;
      let out = '';
      let errBuf = '';
      let settled = false;
      const settle = (fn, v) => { if (!settled) { settled = true; clearTimeout(timer); fn(v); } };
      const fail = (message, extra) => { const err = new Error(message); err.ring = ring; err.child = child; Object.assign(err, extra); settle(reject, err); };
      const timer = setTimeout(() => fail('the maker did not start within ' + handshakeS + ' s'), handshakeS * 1000);
      child.on('error', (e) => { children.delete(child); fail('could not start the maker: ' + e.code); });
      child.stdout.on('data', (chunk) => {            // read for the sidecar's whole life; kept only until the port line
        if (settled) return;
        out += chunk.toString('utf8');
        const parsed = parsePortLine(out);
        if (parsed) {
          Object.assign(sidecar, { child, port: parsed.port, token, pid: child.pid,
            origin: 'http://' + (parsed.host === '::1' ? '[::1]' : parsed.host) + ':' + parsed.port });
          log.line('sidecar port=' + parsed.port);
          settle(resolve, sidecar);
        }
      });
      child.stderr.on('data', (chunk) => {
        errBuf += chunk.toString('utf8');
        let i;
        while ((i = errBuf.indexOf('\n')) >= 0) { ring.push(errBuf.slice(0, i)); errBuf = errBuf.slice(i + 1); }
      });
      log.line('sidecar start mode=' + launch.mode + ' pid=' + child.pid + ' cmd=' + require('node:path').basename(launch.cmd));
      child.on('exit', (code, signal) => {
        children.delete(child);
        if (errBuf) { ring.push(errBuf); errBuf = ''; }          // an unterminated last line is the one that matters most
        log.line('sidecar exit code=' + code + ' signal=' + signal);
        logRing(ring);                                          // the last stderr lines, redacted
        if (!settled) {
          const busy = code === 2 && ring.lines().some((l) => l.includes(BUSY_MESSAGE));
          fail('the maker exited before it was ready (exit ' + code + ')', { busy });
        } else if (child === sidecar.child && !sup.quitting && !sup.failing) {
          onUnexpectedExit(code, signal, ring);
        }
      });
    });
  }

  // One start: retried for up to busyRetryS while a previous sidecar still holds the data root (exit 2 + its message).
  sup.start = async function start() {
    const until = Date.now() + busyRetryS * 1000;
    for (;;) {
      if (sup.quitting || sup.failing) throw Object.assign(new Error(sup.quitting ? 'quitting' : 'failing'), { cancelled: true });
      try {
        return await attempt();
      } catch (e) {
        if (e.busy && !sup.quitting && !sup.failing && Date.now() < until) {
          log.line('sidecar start: the data root is still in use, retrying');
          await new Promise((r) => setTimeout(r, 1000));
          continue;
        }
        if (sup.quitting || sup.failing) e.cancelled = true;
        throw e;
      }
    }
  };

  // Stops every live child with the one sequence (SIGTERM, wait, SIGKILL, wait); marks the supervisor as quitting so a
  // pending start is cancelled.
  sup.stopAll = async function stopAll() {
    sup.quitting = true;
    const started = Date.now();
    const live = [...children];
    const results = await Promise.all(live.map((c) => stopSidecar(c, { termWaitS, killWaitS })));
    if (live.length) log.line('stopped ' + live.length + ' sidecar(s) in ' + (Date.now() - started) + ' ms');
    return results;
  };

  // The failure path of an initial start and of a restart alike: whatever is still alive is stopped by the one sequence.
  sup.cleanupAfterFailure = async function cleanupAfterFailure(err) {
    sup.failing = true;                                  // the exits below are ours, not a crash to offer a restart for
    const live = [...children];
    if (err && err.child && !live.includes(err.child) && err.child.exitCode === null && err.child.signalCode === null) live.push(err.child);
    await Promise.all(live.filter((c) => c.pid).map((c) => stopSidecar(c, { termWaitS, killWaitS })));
  };

  return sup;
}
module.exports = { createSupervisor, BUSY_MESSAGE };
