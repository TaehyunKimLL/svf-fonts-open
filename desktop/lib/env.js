'use strict';
const crypto = require('node:crypto');
const os = require('node:os');

// The one list of keys the sidecar's environment may hold (spec 6.2; JAMOSET_MASK_FONT added, design issue 25).
const ENV_KEYS = ['PATH', 'HOME', 'LANG', 'SVF_MAKER_TOKEN', 'SVF_MAKER_BIND', 'SVF_MAKER_DATA', 'SVF_MAKER_REPO',
  'SVF_MAKER_ROOTS', 'JAMOSET_PYLIB', 'JAMOSET_MASK_FONT', 'SVF_RECOG_DIR', 'SVF_RECOG_PYTHON'];
const PASS_KEYS = ENV_KEYS.slice(-5);
// Windows only (t_9b8f56f0): what a Python process needs to start at all (SYSTEMROOT: Winsock and the crypto provider)
// and to find its temp folder, passed through when set; PYTHONUTF8=1 is added (a development run's python then writes
// UTF-8 as under LANG=C.UTF-8; the frozen sidecar is built with UTF-8 mode on).
const WINDOWS_KEYS = ['SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA', 'PYTHONUTF8'];

function buildEnv(parentEnv, { repo, data }, platform = process.platform) {
  const token = crypto.randomBytes(16).toString('hex');
  if (platform === 'win32') {
    // Windows names are case-blind (`Path`, `SystemRoot`): process.env answers either spelling, a plain copy of it does not
    const upper = {};
    for (const [k, v] of Object.entries(parentEnv)) if (!(k.toUpperCase() in upper)) upper[k.toUpperCase()] = v;
    parentEnv = upper;
  }
  const env = {
    PATH: parentEnv.PATH || '/usr/bin:/bin',
    HOME: parentEnv.HOME || os.homedir(),
    LANG: 'C.UTF-8',
    SVF_MAKER_TOKEN: token,
    SVF_MAKER_BIND: '127.0.0.1:0',
    SVF_MAKER_DATA: data,
    SVF_MAKER_REPO: repo,
  };
  for (const k of PASS_KEYS) if (parentEnv[k]) env[k] = parentEnv[k];
  if (platform === 'win32') {
    for (const k of WINDOWS_KEYS.slice(0, -1)) if (parentEnv[k]) env[k] = parentEnv[k];
    env.PYTHONUTF8 = '1';
  }
  return { env, token };
}
module.exports = { ENV_KEYS, PASS_KEYS, WINDOWS_KEYS, buildEnv };
