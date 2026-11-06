#!/usr/bin/env python3
"""sidecar-provenance.py WORKPATH OUT.json [--pysite DIR]: where every binary PyInstaller collected came from.

Reads `WORKPATH/COLLECT-00.toc` (the table of contents PyInstaller wrote while building) and writes, for every binary
entry (an extension module or a shared library), `{dest: {"source", "sha256", "origin": "wheel" | "dpkg" | "python",
"package", "version"}}`. This must happen at build time: `dpkg -S` of the bundled copy finds nothing, and a library in a
wheel's `*.libs/` directory belongs to no Debian package (design issue 23). The THIRD-PARTY generator compares each
bundled file's sha256 with this record.
"""
import ast
import glob
import hashlib
import os
import re
import subprocess
import sys


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wheel_owner(source, pysite):
    """(distribution, version) of the wheel under @p pysite that lists @p source in its RECORD, else None."""
    if not pysite:
        return None
    rel = os.path.relpath(os.path.realpath(source), os.path.realpath(pysite))
    if rel.startswith(".."):
        return None
    for record in glob.glob(os.path.join(pysite, "*.dist-info", "RECORD")):
        with open(record, encoding="utf-8") as f:
            if any(line.split(",", 1)[0] == rel for line in f):
                m = re.match(r"^(.+)-([^-]+)\.dist-info$", os.path.basename(os.path.dirname(record)))
                return m.group(1), m.group(2)
    return None


def dpkg_owner(source):
    """(package, version) that owns @p source (or its real path) per dpkg, else None."""
    for path in dict.fromkeys([source, os.path.realpath(source)]):
        out = subprocess.run(["dpkg", "-S", path], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            pkg = out.stdout.split(":")[0].split(",")[0].strip()
            ver = subprocess.run(["dpkg-query", "-W", "-f=${Version}", pkg], capture_output=True, text=True)
            if ver.returncode == 0:
                return pkg, ver.stdout.strip()
    return None


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    work, out = argv[0], argv[1]
    pysite = argv[argv.index("--pysite") + 1] if "--pysite" in argv else None
    with open(os.path.join(work, "COLLECT-00.toc"), encoding="utf-8") as f:
        toc = ast.literal_eval(f.read())
    entries = toc[0] if isinstance(toc, tuple) and toc and isinstance(toc[0], list) else toc
    result = {}
    for item in entries:
        dest, source, kind = item[0], item[1], item[2]
        if kind not in ("BINARY", "EXTENSION") and not re.search(r"\.so(\.|$)", os.path.basename(dest)):
            continue
        if not os.path.isfile(source):
            continue
        owner = wheel_owner(source, pysite)
        if owner:
            record = {"origin": "wheel", "package": owner[0], "version": owner[1]}
        else:
            deb = dpkg_owner(source)
            if deb:
                record = {"origin": "dpkg", "package": deb[0], "version": deb[1]}
            else:
                record = {"origin": "python", "package": "python3", "version": "%d.%d.%d" % sys.version_info[:3]}
        record.update({"source": source, "sha256": sha256(source)})
        result[dest] = record
    import json
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, sort_keys=True)
    print("provenance: %d binaries -> %s" % (len(result), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
