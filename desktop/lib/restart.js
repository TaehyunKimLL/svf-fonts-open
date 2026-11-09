'use strict';
// At most 3 restarts in 5 minutes.
function restartAllowed(history, now) {
  return history.filter((t) => now - t < 300000).length < 3;
}
module.exports = { restartAllowed };
