#!/usr/bin/env python3
"""Spike entry point for the frozen sidecar (design probe only; not the repo's code).

  sidecar serve                      -> maker/server.py main()
  sidecar run-tool NAME ARGS...      -> tools/NAME.py main() (or maker/srcprep.py, maker/recog_score.py, instancer)
  sidecar -P /path/to/NAME.py ARGS   -> compatibility shim for the unmodified routes.PY launch
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("SVF_MAKER_SRC_REPO")  # source mode only
if REPO:
    for p in (os.path.join(REPO, "maker"), os.path.join(REPO, "tools")):
        if p not in sys.path:
            sys.path.insert(0, p)

TOOLS = ("jamoset", "jamovec", "mkfont", "macfbit_svf", "macfbit3", "macsfnt", "bdfface", "johab844",
         "svf2to3", "svfdy", "svfline", "facecheck", "srcprep", "recog_score")


def run_tool(name, args):
    if name == "instancer":
        from fontTools.varLib import instancer
        sys.exit(instancer.main(args) or 0)
    if name not in TOOLS:
        print("run-tool: unknown tool %r" % name, file=sys.stderr)
        sys.exit(2)
    mod = __import__(name)
    sys.argv = [name + ".py"] + list(args)
    rc = mod.main()
    sys.exit(rc or 0)


def main():
    argv = sys.argv[1:]
    if argv[:1] == ["serve"]:
        import server
        sys.argv = ["server.py"]
        server.main()
    elif argv[:1] == ["run-tool"] and len(argv) >= 2:
        run_tool(argv[1], argv[2:])
    elif argv[:1] == ["-P"] and len(argv) >= 2:           # shim: [sys.executable, "-P", tools/X.py, ...]
        if argv[1] == "-m":
            run_tool("instancer" if argv[2] == "fontTools.varLib.instancer" else argv[2], argv[3:])
        name = os.path.splitext(os.path.basename(argv[1]))[0]
        run_tool(name, argv[2:])
    elif argv[:1] == ["--probe"]:
        import json
        print(json.dumps({"frozen": getattr(sys, "frozen", False), "path": sys.path, "flags": repr(sys.flags),
                          "executable": sys.executable, "cwd": os.getcwd(),
                          "env_keys": sorted(os.environ)}))
    else:
        print("usage: sidecar serve | run-tool NAME ARGS... | --probe", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
