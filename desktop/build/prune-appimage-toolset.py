#!/usr/bin/env python3
"""prune-appimage-toolset.py SRC_TOOLSET_DIR ARCHIVE OUT_DIR: a copy of electron-builder's downloaded legacy AppImage
toolset without the files listed in appimage-toolset.json ("removed").

Nothing is hand-edited and nothing binary is kept in the repository: the script checks the sha256 of the downloaded archive
and of every file it removes against appimage-toolset.json (a different toolset fails), copies the directory and deletes
exactly those files. electron-builder is then pointed at OUT_DIR with APPIMAGE_TOOLS_PATH (its documented override).
"""
import hashlib
import json
import os
import shutil
import sys


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    src, archive, out = argv
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
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(src, out, symlinks=True)
    for rel in record["removed"]:
        os.remove(os.path.join(out, rel))
    print("pruned %s -> %s (removed %d files)" % (record["toolset"], out, len(record["removed"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
