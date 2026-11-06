'use strict';
const fs = require('node:fs');

const DEFAULTS = () => ({ bounds: null, zoom: 1, lastOutputDir: null, handedOut: [] });

// shell-state.json holds exactly four keys: window bounds, zoom, the last output folder (D3), and the output folders
// the shell handed out (realpaths, the last 32). No token, no input directory.
function loadState(file) {
  const state = DEFAULTS();
  try {
    const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (raw && typeof raw === 'object') {
      if (raw.bounds && typeof raw.bounds === 'object') {          // only finite numbers of the four window keys (the object goes into BrowserWindow options)
        const b = {};
        for (const k of ['x', 'y', 'width', 'height']) if (Number.isFinite(raw.bounds[k])) b[k] = raw.bounds[k];
        if (Object.keys(b).length) state.bounds = b;
      }
      if (typeof raw.zoom === 'number' && raw.zoom > 0) state.zoom = raw.zoom;
      if (typeof raw.lastOutputDir === 'string') state.lastOutputDir = raw.lastOutputDir;
      if (Array.isArray(raw.handedOut)) state.handedOut = raw.handedOut.filter((p) => typeof p === 'string').slice(-32);
    }
  } catch (e) { /* defaults */ }
  return state;
}

function saveState(file, state) {
  const out = { bounds: state.bounds || null, zoom: state.zoom || 1, lastOutputDir: state.lastOutputDir || null,
    handedOut: (state.handedOut || []).slice(-32) };
  const tmp = file + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(out, null, 1));
  fs.renameSync(tmp, file);
}
module.exports = { loadState, saveState };
