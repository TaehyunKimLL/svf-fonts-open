#!/usr/bin/env python3
"""The SVF maker sidecar: one executable (frozen by PyInstaller) or one script, three commands.

  sidecar serve [--exit-with-parent=PID]   the maker server (`server.main`; environment as server.py)
  sidecar run-tool NAME ARGS...            one of the CLIs in TOOLS; the exit code is the tool's
  sidecar selfcheck                        JSON: flags, sys.path, the tool table, every module imported, the budgets
  sidecar --version                        svf-maker-sidecar <version> <build id> python <x.y.z>

`run-tool` is the one launch form of a tool when frozen (`toolrun.tool`); `sys.argv[0]` is `NAME.py`, so usage lines
and argparse messages are the ones `python3 tools/NAME.py` prints. One small function per table entry holds that entry's
import, so `run-tool mkfont` does not import the server and every other tool (and PyInstaller's analysis follows them).
"""

import os, sys
MAKER_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(MAKER_DIR)
if not getattr(sys, "frozen", False):
    for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
        if _p not in sys.path:
            sys.path.insert(0, _p)

import json
import signal
import traceback

import toolrun

VERSION = "0.1.0"           # the same string as desktop/package.json "version" (Task 6 pins the equality)

# name -> (where, how main is called). bare: `main(); exit 0` (the file's guard ignores main's value);
# exit: `sys.exit(main())`; args: `sys.exit(main(ARGS))`.
TOOLS = {
    "jamoset": ("tools", "bare"), "jamovec": ("tools", "bare"), "mkfont": ("tools", "bare"),
    "bdfface": ("tools", "bare"), "johab844": ("tools", "bare"), "hwpfont": ("tools", "bare"),
    "macfbit_svf": ("tools", "exit"), "macfbit3": ("tools", "exit"), "macsfnt": ("tools", "exit"),
    "svf2to3": ("tools", "exit"), "svfdy": ("tools", "exit"), "svfline": ("tools", "exit"),
    "svf2ttf": ("tools", "exit"), "rawcarve": ("tools", "bare"),
    "srcprep": ("maker", "exit"),
    "instancer": ("module", "args"),
}

# name -> (smoke argv, exit code, stream, expected prefix): what `run-tool NAME --help` prints. svfline has no argparse.
SMOKE = {name: (["--help"], 0, "stdout", "usage: %s.py" % name) for name in TOOLS}
SMOKE["instancer"] = (["--help"], 0, "stdout", "usage: fonttools varLib.instancer")
SMOKE["svfline"] = (["--help"], 1, "stderr", "  svfline.py line W H X Y")

# The modules reachable from this file (test_sidecar_imports computes the same set from the sources and pins equality).
GRAPH_MODULES = ("archive", "bdfface", "binscan", "caps", "detect", "hwpfont", "jamoaa", "jamoadapt", "jamofit", "jamoset",
                 "jamovec", "jobs", "johab844", "macfbit3", "macfbit_svf", "macsfnt", "mkfont", "naming", "oscompat", "presets",
                 "preview", "quality", "rawcarve", "recipe", "routes", "server", "settings", "sidecar", "sources", "srcprep",
                 "svf2to3", "svf2ttf", "svfdy", "svfline", "toolreg", "toolrun", "zipout")


def _entry_jamoset():
    import jamoset
    return jamoset.main


def _entry_jamovec():
    import jamovec
    return jamovec.main


def _entry_mkfont():
    import mkfont
    return mkfont.main


def _entry_bdfface():
    import bdfface
    return bdfface.main


def _entry_johab844():
    import johab844
    return johab844.main


def _entry_hwpfont():
    import hwpfont
    return hwpfont.main


def _entry_macfbit_svf():
    import macfbit_svf
    return macfbit_svf.main


def _entry_macfbit3():
    import macfbit3
    return macfbit3.main


def _entry_macsfnt():
    import macsfnt
    return macsfnt.main


def _entry_svf2to3():
    import svf2to3
    return svf2to3.main


def _entry_svfdy():
    import svfdy
    return svfdy.main


def _entry_svfline():
    import svfline
    return svfline.main


def _entry_rawcarve():
    import rawcarve
    return rawcarve.main


def _entry_svf2ttf():
    import svf2ttf
    return svf2ttf.main


def _entry_srcprep():
    import srcprep
    return srcprep.main


def _entry_instancer():
    from fontTools.varLib import instancer
    return instancer.main


ENTRIES = {name: globals()["_entry_" + name] for name in TOOLS}


def run_tool(name, args):
    """Run tool @p name with @p args and exit with its code (never returns)."""
    if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
        # a tool dies with its sidecar (SIGKILL on the parent's death). If the sidecar died between the fork and the
        # prctl the signal never comes: the sidecar names its own pid in the environment (toolrun.base_env) and the
        # parent is compared with it after the prctl. Run by a person or a test without the variable, nothing is checked.
        want = os.environ.get(toolrun.SIDECAR_PID_KEY, "")
        if toolrun.set_pdeathsig(signal.SIGKILL) and want.isdigit() and os.getppid() != int(want):
            os._exit(1)
    if name not in TOOLS:
        print("run-tool: unknown tool '%s'" % name, file=sys.stderr)
        sys.exit(2)
    _, how = TOOLS[name]
    sys.argv = [name + ".py"] + list(args)
    if os.name == "nt":                                   # UTF-8 and LF on the pipes, as a POSIX tool writes
        for stream in (sys.stdout, sys.stderr):           # (the frozen sidecar is built in UTF-8 mode already)
            try:
                stream.reconfigure(encoding="utf-8", newline="\n")
            except (AttributeError, ValueError):
                pass
    try:
        main = ENTRIES[name]()
        if how == "bare":
            main()
            sys.exit(0)
        elif how == "exit":
            sys.exit(main())
        sys.exit(main(list(args)))
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        sys.exit(1)


def _build_id():
    repo = os.environ.get("SVF_MAKER_REPO") or REPO_DIR
    try:
        with open(os.path.join(repo, "BUILD_ID"), encoding="utf-8", errors="replace") as f:
            first = f.readline().strip()[:200]
        return first or "unknown"
    except OSError:
        return "unknown"


def selfcheck():
    """The self-check document (see the module docstring); `modules` maps every module of GRAPH_MODULES to None or an
    error text."""
    import inspect
    import platform
    modules = {}
    for name in GRAPH_MODULES:
        if name == "sidecar":                             # this file: frozen it is the entry script, not importable
            modules[name] = None
            continue
        try:
            __import__(name)
            modules[name] = None
        except BaseException as exc:                      # a missing module is a failed self-check, not a failed job
            modules[name] = "%s: %s" % (type(exc).__name__, exc)
    budget = {}
    try:
        import caps
        import jobs
        import server
        import toolreg
        budget = {"startup_cleanup_s": server.STARTUP_CLEANUP_S,
                  "stop_timeout_s": inspect.signature(jobs.Worker.stop).parameters["timeout"].default,
                  "stop_sweep_s": jobs.STOP_SWEEP_TOTAL_S, "reap_total_s": toolreg.REAP_TOTAL_S,
                  "recog_probe_s": caps.RECOG_PROBE_S}
    except BaseException as exc:
        budget = {"error": "%s: %s" % (type(exc).__name__, exc)}
    try:                                                  # the built-in recipes are bundled data (sidecar.spec)
        import recipe
        recipes = sorted(recipe.library())
    except BaseException as exc:
        recipes = "%s: %s" % (type(exc).__name__, exc)
    flags = sys.flags
    return {"recipes": recipes, "frozen": bool(getattr(sys, "frozen", False)), "version": VERSION, "build_id": _build_id(),
            "python": platform.python_version(),
            "flags": {"isolated": bool(flags.isolated), "ignore_environment": bool(flags.ignore_environment),
                      "safe_path": bool(getattr(flags, "safe_path", False)), "no_site": bool(flags.no_site)},
            "path": list(sys.path), "tools": sorted(TOOLS), "modules": modules, "budget": budget}


USAGE = ("usage: svf-maker-sidecar serve [--exit-with-parent=PID]\n"
         "       svf-maker-sidecar run-tool NAME ARGS...\n"
         "       svf-maker-sidecar selfcheck\n"
         "       svf-maker-sidecar --version\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["serve"]:
        import server
        return server.main(argv[1:])
    if argv[:1] == ["run-tool"] and len(argv) >= 2:
        run_tool(argv[1], argv[2:])
    if argv == ["selfcheck"]:
        info = selfcheck()
        print(json.dumps(info, indent=1, sort_keys=True))
        return 0 if (all(v is None for v in info["modules"].values()) and "error" not in info["budget"]
                     and isinstance(info["recipes"], list) and info["recipes"]) else 1
    if argv == ["--version"]:
        import platform
        print("svf-maker-sidecar %s %s python %s" % (VERSION, _build_id(), platform.python_version()))
        return 0
    sys.stderr.write(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
