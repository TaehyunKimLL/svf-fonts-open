'use strict';
const fs = require('node:fs');
const path = require('node:path');

// <dir>/shell.log, rotated to shell.log.1 past maxBytes (two files kept); toStderr mirrors every line.
function createLog({ dir, toStderr, maxBytes = 1 << 20 }) {
  fs.mkdirSync(dir, { recursive: true });
  const file = path.join(dir, 'shell.log');
  return {
    path: file,
    line(text) {
      const row = new Date().toISOString() + ' ' + text + '\n';
      try {
        const size = fs.existsSync(file) ? fs.statSync(file).size : 0;
        if (size + row.length > maxBytes && size > 0) fs.renameSync(file, file + '.1');
        fs.appendFileSync(file, row);
      } catch (e) { /* logging must never take the shell down */ }
      if (toStderr) process.stderr.write(row);
    },
  };
}

// "pick-files: 3": the count of what a dialog returned, never the paths.
function pathsLine(channel, paths) {
  return channel + ': ' + (Array.isArray(paths) ? paths.length : paths ? 1 : 0);
}

// A sidecar stderr line made safe to log. From the first path start (a "/" or "~/" at the start of the line or after
// whitespace, a quote, "=", "(", "[" or ",") to the END of the line is one path field (a folder name may hold spaces and
// colons, so there is no safe place to stop earlier); file-name-like tokens and 32-hex runs (tokens) are replaced too.
// Cut to 300 characters. A name with spaces and no "/" can still leak its last word: the log is a diagnostic, not a
// transcript, and the sidecar prints paths, not bare names, on its stderr.
const FILE_EXT = 'ttf|otf|ttc|woff2?|svf|fnt|bdf|pcf|dfont|rsrc|fon|gz|zip|tsv|txt|json|py';
function redactLine(text) {
  let s = String(text).replace(/(^|[\s"'=(\[,])~?\/[^]*$/, '$1<path>');
  s = s.replace(new RegExp('[^\\s"\'<>]+\\.(?:' + FILE_EXT + ')\\b', 'gi'), '<file>');
  return s.replace(/[0-9a-f]{32}/gi, '<hex>').slice(0, 300);
}

class Ring {
  constructor(n) { this.n = n; this.items = []; }
  push(line) { this.items.push(line); if (this.items.length > this.n) this.items.shift(); }
  lines() { return this.items.slice(); }
}
module.exports = { createLog, pathsLine, redactLine, Ring };
