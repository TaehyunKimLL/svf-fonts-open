'use strict';
// The server's constants the shell's waits derive from (a unit test reads the Python source and pins them).
const SERVER = { startupCleanupS: 30, recogProbeS: 20, reapTotalS: 10, stopTimeoutS: 30, joinS: 1, stopSweepS: 8 };
const HANDSHAKE_S = 75;      // >= startupCleanupS + recogProbeS + reapTotalS (+ margin)
const STOP_WAIT_S = 45;      // >= stopTimeoutS + joinS + stopSweepS (+ margin)
const KILL_WAIT_S = 5;
const STARTING_PAGE_S = 2;
module.exports = { SERVER, HANDSHAKE_S, STOP_WAIT_S, KILL_WAIT_S, STARTING_PAGE_S };
