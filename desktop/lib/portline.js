'use strict';
// The server's start line: "svf-maker listening on <host>:<port>\n" (a partial chunk without its newline is no line).
function parsePortLine(text) {
  const m = /^svf-maker listening on (127\.0\.0\.1|::1):(\d+)\r?\n/m.exec(String(text));
  return m ? { host: m[1], port: Number(m[2]) } : null;
}
module.exports = { parsePortLine };
