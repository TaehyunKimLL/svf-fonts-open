'use strict';
const { fileURLToPath } = require('node:url');
// URL rules of the shell (spec 6.3): what the window may load, and where the token header goes.
// The starting page is compared as a file path (a checkout path with "%" or "[" encodes differently on the two sides).
function sameFile(a, b) {
  try { return fileURLToPath(a) === fileURLToPath(b); } catch (e) { return false; }
}

// @p subresource: the request is not a top-level navigation (onBeforeRequest knows; the navigation guards do not say so).
function isOurs(origin, url, { startingUrl, devtools, subresource } = {}) {
  if (typeof url !== 'string') return false;
  if (url === origin + '/' || url.startsWith(origin + '/')) return true;
  if (startingUrl && (url === startingUrl || (url.startsWith('file:') && sameFile(url, startingUrl)))) return true;
  if (subresource && url.startsWith('data:')) return true;        // the page's <link rel="icon" href="data:,">; never a navigation
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
