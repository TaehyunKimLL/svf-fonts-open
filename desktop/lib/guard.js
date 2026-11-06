'use strict';
// URL rules of the shell (spec 6.3): what the window may load, and where the token header goes.
function isOurs(origin, url, { startingUrl, devtools } = {}) {
  if (typeof url !== 'string') return false;
  if (url === origin + '/' || url.startsWith(origin + '/')) return true;
  if (startingUrl && url === startingUrl) return true;
  if (url.startsWith('data:')) return true;                       // the page's <link rel="icon" href="data:,">
  if (devtools && url.startsWith('devtools://')) return true;
  return false;
}

// A new headers object: every spelling of x-maker-token removed; the sidecar's token set only for its own /api/ URLs.
function withToken(url, headers, sidecar) {
  const out = {};
  for (const [k, v] of Object.entries(headers || {})) {
    if (k.toLowerCase() !== 'x-maker-token') out[k] = v;
  }
  if (sidecar && typeof url === 'string' && url.startsWith(sidecar.origin + '/')) {
    let pathname = '';
    try { pathname = new URL(url).pathname; } catch (e) { pathname = ''; }
    if (pathname.startsWith('/api/')) out['X-Maker-Token'] = sidecar.token;
  }
  return out;
}
module.exports = { isOurs, withToken };
