#!/usr/bin/env python3
"""toolrun: the one place that knows how a tool is launched.

Source mode runs `python3 -P tools/X.py` (and `maker/X.py`, `-m dotted`); a frozen sidecar runs
`<sidecar> run-tool X`. Every launch site builds its argv here, and every note, `BUILD.md` and `log.md` line shows the
source form (`python3 -P tools/X.py`) in both modes, with repo-relative paths, so the text does not depend on the mode.

Stdlib only; importable from `maker/` and `tools/` on `sys.path`.
"""

import os
import sys

import oscompat

FROZEN = bool(getattr(sys, "frozen", False))
PYTHON = sys.executable                   # the interpreter of source-mode launches (a test seam)
MAKER_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_SCRIPTS = ("srcprep", "recog_score")
MODULE_NAMES = {"fontTools.varLib.instancer": "instancer"}

# Environment keys a tool may see besides PATH, HOME and LANG (spec 7.4; JAMOSET_MASK_FONT: design issue 25;
# SOURCE_DATE_EPOCH: svf2ttf.py's TTF timestamps, so a build that sets it exports the same bytes twice).
FORWARD_KEYS = ("JAMOSET_PYLIB", "JAMOSET_MASK_FONT", "SOURCE_DATE_EPOCH")
# Windows only: what a Python process needs to start at all (SYSTEMROOT: Winsock and the crypto provider) and to find
# its temp folder; PYTHONUTF8=1 is added, so a tool's stdout and stderr are UTF-8 as under LANG=C.UTF-8 on Linux.
WINDOWS_KEYS = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA")
# Test-only knob, forwarded only as "1" (design issue 17).
TEST_KEYS = ("SVF_MAKER_NO_PDEATHSIG",)
# The frozen sidecar's own pid, for the tools it starts: `run-tool` compares its parent with it after the prctl (a parent
# that died between the fork and the prctl never signals). Set by `base_env` only when frozen; the one other SVF_ key.
SIDECAR_PID_KEY = "SVF_MAKER_SIDECAR_PID"


def tool(name, tools_dir):
    """The launcher prefix of `tools/<name>.py` (@p name has no `.py`)."""
    if FROZEN:
        return [sys.executable, "run-tool", name]
    return [PYTHON, "-P", os.path.join(tools_dir, name + ".py")]


def maker_script(name):
    """The launcher prefix of `maker/<name>.py`."""
    if FROZEN:
        return [sys.executable, "run-tool", name]
    return [PYTHON, "-P", os.path.join(MAKER_DIR, name + ".py")]


def module(dotted):
    """The launcher prefix of `python -m <dotted>` (frozen: the module's run-tool name)."""
    if FROZEN:
        return [sys.executable, "run-tool", MODULE_NAMES[dotted]]
    return [PYTHON, "-P", "-m", dotted]


def split_prefix(argv):
    """`(prefix, rest)` of a launcher argv, whatever `FROZEN` is; `ValueError` when @p argv is not a launch."""
    argv = list(argv)
    if len(argv) >= 3 and argv[1] == "-P" and isinstance(argv[2], str) and argv[2].endswith(".py"):
        return argv[:3], argv[3:]
    if len(argv) >= 4 and argv[1] == "-P" and argv[2] == "-m":
        return argv[:4], argv[4:]
    if len(argv) >= 3 and argv[1] == "run-tool":
        return argv[:3], argv[3:]
    raise ValueError("not a tool launch: %r" % (argv[:3],))


def prefix_name(prefix):
    """The run-tool name of a prefix: `mkfont`, `srcprep`, `instancer`."""
    if prefix[1] == "run-tool":
        return prefix[2]
    if prefix[2] == "-m":
        return MODULE_NAMES.get(prefix[3], prefix[3])
    return os.path.basename(prefix[2])[:-len(".py")]


def note_prefix(argv):
    """`(prefix, rest)` with the prefix as a note shows it in both modes; an argv that is no launch is `([], argv)`."""
    try:
        prefix, rest = split_prefix(argv)
    except ValueError:
        return [], list(argv)
    name = prefix_name(prefix)
    for dotted, short in MODULE_NAMES.items():
        if short == name:
            return ["python3", "-P", "-m", dotted], rest
    if name in MAKER_SCRIPTS:
        return ["python3", "-P", "maker/%s.py" % name], rest
    return ["python3", "-P", "tools/%s.py" % name], rest


def _repo_relative(token, repo_dir):
    """@p token as a repo-relative path when it is an absolute path under @p repo_dir, else unchanged."""
    if not isinstance(token, str) or not os.path.isabs(token):
        return token
    real_repo = os.path.realpath(repo_dir)
    for base, path in ((os.path.normpath(repo_dir), os.path.normpath(token)),
                       (real_repo, os.path.realpath(token))):
        if path.startswith(base.rstrip(os.sep) + os.sep):
            return os.path.relpath(path, base).replace(os.sep, "/")
    return token


def note_argv(argv, repo_dir=None):
    """The argv as a note shows it: the note prefix, and the rest with repo-rooted absolute paths made relative."""
    prefix, rest = note_prefix(argv)
    if repo_dir:
        rest = [_repo_relative(token, repo_dir) for token in rest]
    return prefix + rest


def note_text(text, repo_dir):
    """@p text (a tool's captured stdout/stderr) with every `<repo_dir>/` prefix removed, so a path the tool printed
    (johab844 prints its base face) reads the same from a checkout and from an AppImage mount."""
    if not text or not repo_dir:
        return text
    for base in sorted({os.path.normpath(repo_dir), os.path.realpath(repo_dir)}, key=len, reverse=True):
        if base != os.sep:
            text = text.replace(base.rstrip(os.sep) + os.sep, "")
    return text


def base_env(environ):
    """The scrubbed environment of a tool (spec 7.4)."""
    env = {"PATH": environ.get("PATH", "/usr/bin:/bin"), "HOME": environ.get("HOME", "/"), "LANG": "C.UTF-8"}
    for key in FORWARD_KEYS:
        if environ.get(key):
            env[key] = environ[key]
    if oscompat.WINDOWS:
        for key in WINDOWS_KEYS:
            if environ.get(key):
                env[key] = environ[key]
        env["PYTHONUTF8"] = "1"
    if environ.get("SVF_MAKER_NO_PDEATHSIG") == "1":
        env["SVF_MAKER_NO_PDEATHSIG"] = "1"
    if FROZEN:
        env[SIDECAR_PID_KEY] = str(os.getpid())
    return env


def recog_argv(caps, repo_dir):
    """The launcher prefix of the identity scorer, or None without the recogniser capability. With
    `caps["recog_python"]` (SVF_RECOG_PYTHON) it is that interpreter running the shipped `maker/recog_score.py`."""
    if not caps.get("recog"):
        return None
    if caps.get("recog_python"):
        return [caps["recog_python"], "-P", os.path.join(repo_dir, "maker", "recog_score.py")]
    return maker_script("recog_score")


def set_pdeathsig(sig):
    """Linux: ask the kernel to send @p sig to this process when its parent (thread) dies. True on success; False
    elsewhere, on failure, or (without calling prctl) when the test-only knob SVF_MAKER_NO_PDEATHSIG is "1"."""
    if os.environ.get("SVF_MAKER_NO_PDEATHSIG") == "1" or not sys.platform.startswith("linux"):
        return False
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        return libc.prctl(1, int(sig), 0, 0, 0) == 0           # PR_SET_PDEATHSIG = 1
    except (OSError, AttributeError, ValueError):
        return False


def alive(pid):
    """True when process @p pid exists and is not a zombie. Linux reads the state of `/proc/<pid>/stat`; elsewhere
    `kill(pid, 0)` (a zombie then counts as alive: the darwin limitation); Windows asks the process handle (`kill(pid, 0)`
    there would send CTRL_C_EVENT)."""
    if oscompat.WINDOWS:
        return oscompat.process_alive(pid)
    try:
        with open("/proc/%d/stat" % pid, "rb") as f:
            state = f.read().rsplit(b")", 1)[1].split()[0]
        return state not in (b"Z", b"X")
    except (OSError, IndexError):
        pass
    if sys.platform.startswith("linux"):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True
