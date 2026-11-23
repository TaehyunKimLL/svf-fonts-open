#!/usr/bin/env python3
"""The import graph the frozen sidecar bundles: the modules reachable from the server and every tool, the third-party
names they import, and every use of `__file__` (what it resolves to when frozen).

  python3 -m unittest discover -s maker/test -p 'test_sidecar_imports.py'
"""

import ast
import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
TOOLS_DIR = os.path.join(REPO_DIR, "tools")
import unittest

for _p in (MAKER_DIR, TOOLS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ROOTS = ["sidecar"]
EXPECTED = {"archive", "bdfface", "binscan", "caps", "detect", "hwpfont", "rawcarve", "jamoaa", "jamoadapt", "jamofit", "jamoset", "jamovec", "jobs",
            "johab844", "macfbit3", "macfbit_svf", "macsfnt", "mkfont", "naming", "presets", "preview", "quality",
            "routes", "server", "settings", "sources", "srcprep", "svf2to3", "svfdy", "svfline", "toolreg", "toolrun",
            "zipout"}
SP = "sys.path entry for the tool's own directory (python -I drops it); frozen the modules are bundled, the entry is harmless"
FILE_USES = {   # every __file__ use in a reachable module, with why it is right frozen (spec 7.5/7.6)
    ("server", "MAKER_DIR"): "static/ is bundled as <_internal>/static",
    ("server", "repo_dir"): "main(): the default repo dir; the shell passes SVF_MAKER_REPO (the shipped repo/)",
    ("sidecar", "MAKER_DIR"): "source-mode sys.path entry and the default repo dir for --version; frozen: not inserted",
    ("toolrun", "MAKER_DIR"): "maker_script() source mode only; frozen launches use run-tool",
    ("srcprep", "MAKER_DIR"): "sys.path entry for maker/ (srcprep is a run-tool entry frozen)",
    ("jamoset", "DEFAULT_MASK_FONT"): "mask_font_beside(); None frozen (no ScummVM tree); JAMOSET_MASK_FONT is forwarded (base_env)",
    ("jamoset", "MAC_GOLDEN"): "testdata/mac-fbit-golden.json, a test/--verify file; not a product path, absent frozen",
    ("jamoset", "_jamoaa"): "sys.path entry before a local import; frozen the module is bundled",
    ("jamoset", "_jamofit"): "sys.path entry before a local import; frozen the module is bundled",
    ("jamoset", "check"): "sys.path entry before `import johab844`; frozen the module is bundled",
    ("jamoset", "_hwpfont"): "sys.path entry before a local import; frozen the module is bundled",
    ("hwpfont", "HERE"): "SP",
    ("rawcarve", "HERE"): "SP",
    ("bdfface", "HERE"): "SP",
    ("johab844", "HERE"): "SP",
    ("mkfont", "HERE"): "SP",
    ("jamovec", "<module>"): "SP",
    ("macfbit_svf", "<module>"): "SP",
    ("svf2to3", "<module>"): "SP",
    ("svfdy", "<module>"): "SP",
    ("svfline", "<module>"): "SP",
}
FILE_USES = {k: (v if v != "SP" else SP) for k, v in FILE_USES.items()}
STDLIB = set(sys.stdlib_module_names)


def _path_of(name):
    for base in (MAKER_DIR, TOOLS_DIR):
        path = os.path.join(base, name + ".py")
        if os.path.isfile(path):
            return path
    return None


def _imports(tree):
    """Top-level module names a module imports, anywhere in its body (function-local imports included)."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _graph():
    seen, third, todo = {}, set(), list(ROOTS)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        path = _path_of(name)
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        seen[name] = tree
        for mod in _imports(tree):
            if _path_of(mod):
                todo.append(mod)
            elif mod not in STDLIB:
                third.add(mod)
    return seen, third


class SidecarImportsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules, cls.third = _graph()

    def test_reachable_set(self):
        import sidecar
        self.assertEqual(set(self.modules), set(sidecar.GRAPH_MODULES))
        self.assertTrue(EXPECTED | {"sidecar", "toolreg"} <= set(self.modules))
        self.assertEqual(set(self.modules), EXPECTED | {"sidecar"})

    def test_third_party(self):
        self.assertEqual(self.third, {"PIL", "fontTools", "freetype", "uharfbuzz"})

    def test_file_uses_listed(self):
        found = {}
        for name, tree in self.modules.items():
            parents = {}
            for node in ast.walk(tree):
                for child in ast.iter_child_nodes(node):
                    parents[child] = node
            for node in ast.walk(tree):
                if not ((isinstance(node, ast.Name) and node.id == "__file__")
                        or (isinstance(node, ast.Attribute) and node.attr == "__file__")):
                    continue
                where, cur = None, node
                while cur in parents and where is None:
                    cur = parents[cur]
                    if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        where = cur.name
                    elif isinstance(cur, ast.Assign) and isinstance(cur.targets[0], ast.Name):
                        where = cur.targets[0].id
                    elif isinstance(cur, ast.AnnAssign) and isinstance(cur.target, ast.Name):
                        where = cur.target.id
                found[(name, where or "<module>")] = True
        unlisted = sorted(set(found) - set(FILE_USES))
        self.assertEqual(unlisted, [], "unlisted __file__ use(s); add each with its frozen resolution")
        self.assertEqual(sorted(set(FILE_USES) - set(found)), [], "FILE_USES lists a use that is gone")


if __name__ == "__main__":
    unittest.main()
