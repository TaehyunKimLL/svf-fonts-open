#!/usr/bin/env python3
"""import_graph.py [ROOT] - the sibling modules of maker/ and tools/ reachable (by any import statement, top-level or
inside a function) from the sidecar's roots, and the third-party top-level names they import. Run from the checkout.
Used by the desktop design (section 7.1) and by the planned maker/test/test_sidecar_imports.py."""
import ast, os, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
ROOTS = ["server", "jamoset", "jamovec", "mkfont", "macfbit_svf", "macfbit3", "macsfnt", "bdfface", "johab844",
         "svf2to3", "svfdy", "svfline", "srcprep"]


def modules():
    out = {}
    for d in ("maker", "tools"):
        for f in sorted(os.listdir(os.path.join(ROOT, d))):
            if f.endswith(".py") and not f.startswith("test_"):
                out[f[:-3]] = os.path.join(ROOT, d, f)
    return out


def imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def reachable(roots=ROOTS):
    mods = modules()
    graph = {m: imports(p) for m, p in mods.items()}
    seen, third, stack = set(), set(), list(roots)
    while stack:
        m = stack.pop()
        if m in seen:
            continue
        seen.add(m)
        for name in graph[m]:
            if name in mods:
                stack.append(name)
            elif name not in sys.stdlib_module_names and name != "__future__":
                third.add(name)
    return sorted(seen), sorted(third), sorted(set(mods) - seen)


if __name__ == "__main__":
    seen, third, unused = reachable()
    print("reachable (%d): %s" % (len(seen), " ".join(seen)))
    print("third-party: %s" % " ".join(third))
    print("never reached: %s" % " ".join(unused))
