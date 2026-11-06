// Spawn the frozen sidecar as Electron's main process would (own process group, scrubbed env), read the port line,
// then SIGTERM the group and time the exit.
import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
const sidecar = process.argv[2], repo = process.argv[3], data = process.argv[4];
const token = randomBytes(16).toString('hex');
const t0 = Date.now();
const child = spawn(sidecar, ['serve'], {
  detached: true, stdio: ['ignore', 'pipe', 'pipe'],
  env: { PATH: (process.env.TMP_DIR || '.') + '/pyi-probe/emptybin', HOME: process.env.HOME, LANG: 'C.UTF-8', SVF_MAKER_TOKEN: token,
         SVF_MAKER_BIND: '127.0.0.1:0', SVF_MAKER_DATA: data, SVF_MAKER_REPO: repo },
});
let buf = '';
const port = await new Promise((resolve, reject) => {
  child.stdout.on('data', (d) => { buf += d; const m = /^svf-maker listening on 127\.0\.0\.1:(\d+)$/m.exec(buf); if (m) resolve(+m[1]); });
  child.on('exit', (c, s) => reject(new Error('exited ' + c + ' ' + s)));
  setTimeout(() => reject(new Error('no port line in 10 s')), 10000);
});
console.log('port', port, 'after', Date.now() - t0, 'ms; pid', child.pid);
const r = await fetch(`http://127.0.0.1:${port}/api/caps`, { headers: { 'X-Maker-Token': token } });
console.log('caps', r.status, await r.text());
const t1 = Date.now();
process.kill(-child.pid, 'SIGTERM');
const [code, sig] = await new Promise((res) => child.on('exit', (c, s) => res([c, s])));
console.log('exit', code, sig, 'after', Date.now() - t1, 'ms');
