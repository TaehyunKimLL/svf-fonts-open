#!/usr/bin/env python3
"""Copy the faces and licence files a faces.json names from SVF_DIR into OUT (web/build.sh's copy step).

  python3 web/copyfaces.py SVF_DIR FACES_JSON OUT

Each entry's key (svf/<rel>) is copied to OUT/<url> (faces/<rel>) and each licences url (licences/<rel>) from
SVF_DIR/<rel>. Every path is checked before anything is copied: a key must start with svf/, a face url with faces/, a
licence url with licences/; no path may be absolute, hold a backslash, an empty, . or .. component, and each source
must resolve (symlinks followed) under SVF_DIR and each destination under OUT. A path that fails exits 2 naming it,
with nothing copied. Prints "F faces, N MB copied" (N the copied bytes in MB, rounded). Stdlib only.
"""

import json
import os
import shutil
import sys


class PathError(Exception):
    pass


def rel_under(path, prefix):
    """The part of @p path after @p prefix ("svf/", "faces/", "licences/"), refused unless it is a plain relative
    path."""
    if not isinstance(path, str) or not path.startswith(prefix):
        raise PathError("%r does not start with %s" % (path, prefix))
    rel = path[len(prefix):]
    parts = rel.split("/")
    if "\\" in path or os.path.isabs(rel) or any(p in ("", ".", "..") for p in parts):
        raise PathError("%r is not a plain relative path" % path)
    return rel


def inside(path, root):
    """@p path resolved (symlinks followed) lies under @p root resolved."""
    path, root = os.path.realpath(path), os.path.realpath(root)
    return os.path.commonpath([path, root]) == root and path != root


def plan(svf_dir, faces, out):
    """[(source, destination)] of every file the index names, each checked; PathError on the first bad one."""
    pairs = {}
    for e in faces:
        items = [(rel_under(e["key"], "svf/"), e["url"], "faces/")]
        items += [(rel_under(u, "licences/"), u, "licences/") for u in e["licences"]]
        for rel, url, prefix in items:
            rel_under(url, prefix)
            src, dst = os.path.join(svf_dir, rel), os.path.join(out, url)
            if not inside(src, svf_dir):
                raise PathError("source %r resolves outside %s" % (rel, svf_dir))
            if not inside(dst, out):
                raise PathError("destination %r resolves outside %s" % (url, out))
            pairs[dst] = src
    return sorted((s, d) for d, s in pairs.items())


def main(argv):
    if len(argv) != 3:
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        return 1
    svf_dir, index, out = argv
    with open(index, encoding="utf-8") as f:
        faces = json.load(f)["faces"]
    try:
        pairs = plan(svf_dir, faces, out)
    except (PathError, KeyError, TypeError) as e:
        print("copyfaces.py: %s: %s" % (index, e), file=sys.stderr)
        return 2
    total = 0
    for src, dst in pairs:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        total += os.path.getsize(dst)
    print("%d faces, %d MB copied" % (len(faces), round(total / 1e6)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
