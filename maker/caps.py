#!/usr/bin/env python3
"""Capabilities the maker computes once at server start: whether the preview module is built, whether the mask-fit
libraries are there, whether the identity recogniser can run. Booleans only (no path leaves the server); nothing heavy
is imported (the recogniser's libraries are only looked up with `importlib.util.find_spec`).

The library assumes `maker/` and `tools/` are on sys.path (the entry points set it).
"""

import importlib.util
import os
import subprocess

PUBLIC_KEYS = ("wasm", "mask_libs", "recog", "local")      # what /api/caps serves; the private keys never leave
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
    if not probe:
        return path
    if importlib.util.find_spec("numpy") and importlib.util.find_spec("torch"):
        return path
    return None


def recog_python(environ):
    """$SVF_RECOG_PYTHON when it is an executable file, the recogniser's directory is there, and that interpreter can
    import numpy, torch, PIL and fontTools (run once, in a scrubbed environment); else None."""
    path = environ.get("SVF_RECOG_PYTHON") or ""
    if not (path and os.path.isfile(path) and os.access(path, os.X_OK)):
        return None
    if recog_dir(environ, probe=False) is None:
        return None
    env = {"PATH": environ.get("PATH", "/usr/bin:/bin"), "HOME": environ.get("HOME", "/"), "LANG": "C.UTF-8"}
    try:
        proc = subprocess.run([path, "-I", "-c", "import numpy, torch, PIL, fontTools"], env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=RECOG_PROBE_S)
    except (OSError, subprocess.SubprocessError):
        return None
    return path if proc.returncode == 0 else None


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
