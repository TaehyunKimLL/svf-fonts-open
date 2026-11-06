#!/usr/bin/env python3
"""Capabilities the maker computes once at server start: whether the preview module is built, whether the mask-fit
libraries are there, whether the identity recogniser can run. `compute` returns the four public booleans (`PUBLIC_KEYS`,
the only keys `/api/caps` serves) plus two private absolute paths for the worker (`recog_python`, `recog_dir`; they
never leave the server). Nothing heavy is imported here. Without `SVF_RECOG_PYTHON` the recogniser's libraries are only
looked up with `importlib.util.find_spec`; with it, one bounded subprocess (`RECOG_PROBE_S`) imports them in that
interpreter, once, at start.

The library assumes `maker/` and `tools/` are on sys.path (the entry points set it).
"""

import importlib.util
import os
import signal
import subprocess
import sys

PUBLIC_KEYS = ("wasm", "mask_libs", "recog", "local")      # what /api/caps serves; the private keys never leave
PROBE_ARGS = ["-P", "-c", "import numpy, torch, PIL, fontTools"]
RECOG_PROBE_S = 20                                          # seconds the external interpreter's import probe may take


def wasm_built(static_dir):
    """True when `wasm/svf.js` and `wasm/svf.wasm` are files under @p static_dir."""
    return all(os.path.isfile(os.path.join(static_dir, "wasm", name)) for name in ("svf.js", "svf.wasm"))


def mask_libs(environ):
    """True when the mask fit's libraries load (`jamofit.libs_available` with $JAMOSET_PYLIB)."""
    import jamofit
    return bool(jamofit.libs_available(environ.get("JAMOSET_PYLIB")))


def recog_dir(environ, probe=True):
    """$SVF_RECOG_DIR when it is a directory holding `recog.py` and (with @p probe) numpy and torch can be found in
    this interpreter, else None. `probe=False` is the directory test alone (the external interpreter does the rest)."""
    path = environ.get("SVF_RECOG_DIR") or ""
    if not (path and os.path.isdir(path) and os.path.isfile(os.path.join(path, "recog.py"))):
        return None
    path = os.path.abspath(path)                     # the scorer runs from work/sNN/identity, not from our cwd
    if not probe:
        return path
    if importlib.util.find_spec("numpy") and importlib.util.find_spec("torch"):
        return path
    return None


def _rejected(reason):
    """None, after a one-line, path-free reason on stderr (an operator can tell why the page says unavailable)."""
    print("recogniser interpreter rejected: %s" % reason, file=sys.stderr, flush=True)
    return None


def recog_python(environ):
    """$SVF_RECOG_PYTHON when it is an executable file, the recogniser's directory is there, and that interpreter can
    import numpy, torch, PIL and fontTools (run once, in a scrubbed environment); else None."""
    path = environ.get("SVF_RECOG_PYTHON") or ""
    if not (path and os.path.isabs(path) and os.path.isfile(path) and os.access(path, os.X_OK)):
        return _rejected("not an absolute path to an executable file")
    if recog_dir(environ, probe=False) is None:
        return _rejected("SVF_RECOG_DIR is not a directory with recog.py")
    env = {"PATH": environ.get("PATH", "/usr/bin:/bin"), "HOME": environ.get("HOME", "/"), "LANG": "C.UTF-8"}
    # The same flag as the scorer's own launch (`toolrun.recog_argv`): -P keeps the cwd off the path and leaves the
    # user's site packages (a `pip install --user` numpy) visible to both; -I would hide them from both.
    try:
        proc = subprocess.Popen([path] + PROBE_ARGS, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return _rejected("could not start")
    code = None
    try:
        code = proc.wait(RECOG_PROBE_S)
    except subprocess.TimeoutExpired:
        pass
    finally:                                         # also on a KeyboardInterrupt (SIGTERM while the probe runs)
        try:
            os.killpg(proc.pid, signal.SIGKILL)      # a wrapper that did not exec leaves its python behind
        except OSError:
            pass
        proc.wait()
    if code is None:
        return _rejected("probe timed out")
    return path if code == 0 else _rejected("probe exit %d" % code)


def compute(static_dir, environ, local=False):
    """The four public booleans (`PUBLIC_KEYS`; local: the per-launch token is set) plus the private
    `recog_python` and `recog_dir` the worker reads (a path or None; they are never served)."""
    if environ.get("SVF_RECOG_PYTHON"):
        python = recog_python(environ)
        directory = recog_dir(environ, probe=False) if python is not None else None
    else:
        python = None
        directory = recog_dir(environ)
    return {"wasm": wasm_built(static_dir), "mask_libs": mask_libs(environ), "recog": directory is not None,
            "local": bool(local), "recog_python": python, "recog_dir": directory}
