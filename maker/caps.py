#!/usr/bin/env python3
"""Capabilities the maker computes once at server start: whether the preview module is built, whether the mask-fit
libraries are there, whether the identity recogniser can run. Booleans only (no path leaves the server); nothing heavy
is imported (the recogniser's libraries are only looked up with `importlib.util.find_spec`).

The library assumes `maker/` and `tools/` are on sys.path (the entry points set it).
"""

import importlib.util
import os


def wasm_built(static_dir):
    """True when `wasm/svf.js` and `wasm/svf.wasm` are files under @p static_dir."""
    return all(os.path.isfile(os.path.join(static_dir, "wasm", name)) for name in ("svf.js", "svf.wasm"))


def mask_libs(environ):
    """True when the mask fit's libraries load (`jamofit.libs_available` with $JAMOSET_PYLIB)."""
    import jamofit
    return bool(jamofit.libs_available(environ.get("JAMOSET_PYLIB")))


def recog_dir(environ):
    """$SVF_RECOG_DIR when it is a directory holding `recog.py` and numpy and torch can be found, else None."""
    path = environ.get("SVF_RECOG_DIR") or ""
    if not (path and os.path.isdir(path) and os.path.isfile(os.path.join(path, "recog.py"))):
        return None
    if importlib.util.find_spec("numpy") and importlib.util.find_spec("torch"):
        return path
    return None


def compute(static_dir, environ):
    """`{"wasm": bool, "mask_libs": bool, "recog": bool}`."""
    return {"wasm": wasm_built(static_dir), "mask_libs": mask_libs(environ), "recog": recog_dir(environ) is not None}
