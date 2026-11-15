#!/usr/bin/env python3
"""prune-appimage-toolset.py SRC_TOOLSET_DIR ARCHIVE OUT_DIR: a copy of electron-builder's downloaded legacy AppImage
toolset without the files listed in appimage-toolset.json ("removed").

Nothing is hand-edited and nothing binary is kept in the repository: the script checks the sha256 of the downloaded archive
and of every file it removes against appimage-toolset.json (a different toolset fails), checks the extracted directory
against a fresh extraction of that archive (7z), copies the directory and deletes
exactly those files. electron-builder is then pointed at OUT_DIR with APPIMAGE_TOOLS_PATH (its documented override).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def tree_digest(root):
    """sha256 over the sorted (relative path, file sha256) pairs of the regular files and symlink targets under @p root."""
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            if os.path.islink(path):
                h.update(("L " + rel + " -> " + os.readlink(path) + "\n").encode())
            else:
                h.update(("F " + rel + " " + sha256(path) + "\n").encode())
    return h.hexdigest()


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    src, archive, out = argv
    if shutil.which("7z") is None:
        print("prune-appimage-toolset: 7z is not on PATH (install p7zip-full)", file=sys.stderr)
        return 1
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "appimage-toolset.json"), encoding="utf-8") as f:
        record = json.load(f)
    if sha256(archive) != record["archive_sha256"]:
        print("prune-appimage-toolset: %s is not the recorded %s" % (archive, record["archive"]), file=sys.stderr)
        return 1
    for rel, digest in record["removed"].items():
        if sha256(os.path.join(src, rel)) != digest:
            print("prune-appimage-toolset: %s does not match its recorded sha256" % rel, file=sys.stderr)
            return 1
    # the cached, already-extracted toolset must be exactly what the verified archive holds
    with tempfile.TemporaryDirectory(prefix="appimage-toolset-") as tmp:
        subprocess.run(["7z", "x", "-y", "-o" + tmp, archive], check=True, stdout=subprocess.DEVNULL)
        entries = os.listdir(tmp)
        fresh = os.path.join(tmp, entries[0]) if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])) else tmp
        if tree_digest(fresh) != tree_digest(src):
            print("prune-appimage-toolset: %s does not match the extraction of %s" % (src, record["archive"]), file=sys.stderr)
            return 1
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(src, out, symlinks=True)
    for rel in record["removed"]:
        os.remove(os.path.join(out, rel))
    print("pruned %s -> %s (removed %d files)" % (record["toolset"], out, len(record["removed"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
