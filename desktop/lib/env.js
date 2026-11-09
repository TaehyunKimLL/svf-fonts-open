'use strict';
const crypto = require('node:crypto');
const os = require('node:os');

// The one list of keys the sidecar's environment may hold (spec 6.2; JAMOSET_MASK_FONT added, design issue 25).
const ENV_KEYS = ['PATH', 'HOME', 'LANG', 'SVF_MAKER_TOKEN', 'SVF_MAKER_BIND', 'SVF_MAKER_DATA', 'SVF_MAKER_REPO',
  'SVF_MAKER_ROOTS', 'JAMOSET_PYLIB', 'JAMOSET_MASK_FONT', 'SVF_RECOG_DIR', 'SVF_RECOG_PYTHON'];
const PASS_KEYS = ENV_KEYS.slice(-5);

function buildEnv(parentEnv, { repo, data }) {
  const token = crypto.randomBytes(16).toString('hex');
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
  return { env, token };
}
module.exports = { ENV_KEYS, PASS_KEYS, buildEnv };
