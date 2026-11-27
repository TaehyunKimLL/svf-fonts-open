#!/usr/bin/env python3
"""smoke-win.py DIST: the Windows release smoke (t_9b8f56f0), the counterpart of release-check.sh's `smoke`.

DIST is electron-builder's output folder (desktop/dist). Three starts, each with SVF_MAKER_SMOKE=1 (the shell loads
the page, fetches /api/caps through the packaged sidecar, prints `svf-maker smoke ok <title>` and quits) and its own
`--user-data-dir`, each judged from the shell's log there (`logs/shell.log`: `sidecar start mode=packaged`, the port
line, the smoke verdict `svf-maker smoke ok`, `renderer sandbox: on`, the clean sidecar exit) and exit code 0:

  1. `win-unpacked/svf-maker.exe`;
  2. the NSIS installer run silently (`/S`, per user: no elevation) - the installed exe under
     %LOCALAPPDATA%\\Programs\\svf-maker and the Start-menu shortcut must exist; the installed exe is started; then the
     uninstaller (`/S`) must remove the install folder;
  3. the portable .exe (it unpacks itself to %TEMP% and starts the app; arguments are passed on).

Prints one `CHECK <name> ok|FAIL <detail>` line each; exit 1 on any FAIL.
"""

import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time

TIMEOUT_S = 150
failed = []


def check(name, ok, detail=""):
    print("CHECK %s %s %s" % (name, "ok" if ok else "FAIL", detail), flush=True)
    if not ok:
        failed.append(name)


def smoke(name, exe, scratch):
    """Start @p exe in smoke mode with its own user data folder; True when its log shows a packaged sidecar that served
    the page and stopped cleanly."""
    ud = os.path.join(scratch, name)
    shutil.rmtree(ud, ignore_errors=True)
    os.makedirs(ud)
    env = dict(os.environ, SVF_MAKER_SMOKE="1", SVF_MAKER_SHELL_LOG="stderr")
    started = time.monotonic()
    try:
        proc = subprocess.run([exe, "--user-data-dir=" + ud], env=env, capture_output=True, timeout=TIMEOUT_S)
        out = (proc.stdout + proc.stderr).decode("utf-8", "replace")
        rc = proc.returncode
    except subprocess.TimeoutExpired as exc:
        out = ((exc.stdout or b"") + (exc.stderr or b"")).decode("utf-8", "replace")
        rc = "timeout"
    seconds = time.monotonic() - started
    deadline = time.monotonic() + 30                      # a portable stub may return before the app it started ends
    log = ""
    while time.monotonic() < deadline:
        try:
            with open(os.path.join(ud, "logs", "shell.log"), encoding="utf-8", errors="replace") as f:
                log = f.read()
        except OSError:
            log = ""
        if "sidecar exit" in log:
            break
        time.sleep(1)
    print("---- %s: rc=%s %.1f s\n%s\n---- shell.log\n%s" % (name, rc, seconds, out.strip()[-3000:], log.strip()[-3000:]),
          flush=True)
    sandbox = next((line.split("sandbox ", 1)[1] for line in log.splitlines() if " sandbox renderer sandbox" in line), "no sandbox line")
    # the verdict is judged from shell.log (main.js logs it there too): a GUI process's stdout is often not passed on
    ok = (rc == 0 and "sidecar start mode=packaged" in log and "sidecar port=" in log and "sidecar exit code=0" in log
          and "svf-maker smoke ok " in log and "smoke FAIL" not in log + out and "renderer sandbox: on" in log)
    check("smoke-" + name, ok, "rc=%s %.1f s; %s; smoke line %s" % (rc, seconds, sandbox,
                                                                   "seen" if "svf-maker smoke ok" in out else "not passed through"))
    return ok


def main(argv):
    if len(argv) != 1 or sys.platform != "win32":
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    dist = os.path.abspath(argv[0])
    scratch = tempfile.mkdtemp(prefix="svf-smoke-")
    smoke("unpacked", os.path.join(dist, "win-unpacked", "svf-maker.exe"), scratch)

    setup = glob.glob(os.path.join(dist, "svf-maker-*-setup.exe"))
    portable = glob.glob(os.path.join(dist, "svf-maker-*-portable.exe"))
    check("artifacts", len(setup) == 1 and len(portable) == 1,
          ", ".join("%s %d bytes" % (os.path.basename(p), os.path.getsize(p)) for p in setup + portable))
    if setup:
        rc = subprocess.run([setup[0], "/S"], timeout=300).returncode
        target = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "svf-maker")
        exe = os.path.join(target, "svf-maker.exe")
        menu = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs")
        links = glob.glob(os.path.join(menu, "SVF maker*.lnk")) + glob.glob(os.path.join(menu, "*", "SVF maker*.lnk"))
        check("install", rc == 0 and os.path.isfile(exe) and bool(links),
              "rc=%s exe=%s shortcut=%s" % (rc, os.path.isfile(exe), [os.path.basename(p) for p in links]))
        if os.path.isfile(exe):
            sidecar = os.path.join(target, "resources", "sidecar", "svf-maker-sidecar", "svf-maker-sidecar.exe")
            check("installed-layout", os.path.isfile(sidecar) and os.path.isfile(os.path.join(target, "resources", "THIRD-PARTY.txt")),
                  "sidecar=%s" % os.path.isfile(sidecar))
            smoke("installed", exe, scratch)
            uninstaller = glob.glob(os.path.join(target, "Uninstall*.exe"))
            if uninstaller:
                # the uninstaller copies itself to %TEMP% and returns: wait for the folder to go
                subprocess.run([uninstaller[0], "/S"], timeout=300)
                end = time.monotonic() + 60
                while os.path.exists(exe) and time.monotonic() < end:
                    time.sleep(1)
            check("uninstall", bool(uninstaller) and not os.path.exists(exe), "uninstaller=%s" % bool(uninstaller))
    if portable:
        smoke("portable", portable[0], scratch)
    shutil.rmtree(scratch, ignore_errors=True)
    print("smoke-win: %s" % ("FAIL " + ", ".join(failed) if failed else "all ok"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
