#!/usr/bin/env python3
"""prune-appimage-toolset.py SRC_TOOLSET_DIR ARCHIVE OUT_DIR: a copy of electron-builder's downloaded AppImage toolset
(appimage@1.0.3: the static type2 runtime, no libfuse2) without the files listed in appimage-toolset.json ("removed");
the runtime files named in "runtimes" are checked by sha256 too.

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
import tarfile
import sys
import tempfile


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def tree_digest(root):
    """sha256 over the sorted (relative path, file sha256) pairs of the regular files under @p root."""
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if not os.path.islink(path):
                h.update(("F " + os.path.relpath(path, root) + " " + sha256(path) + "\n").encode())
    return h.hexdigest()


def links_of(root):
    """{relative path: target} of the symlinks under @p root."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                found[os.path.relpath(path, root)] = os.readlink(path)
    return found


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    src, archive, out = argv
    if archive.endswith(".7z") and shutil.which("7z") is None:
        print("prune-appimage-toolset: 7z is not on PATH (install p7zip-full)", file=sys.stderr)
        return 1
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "appimage-toolset.json"), encoding="utf-8") as f:
        record = json.load(f)
    if sha256(archive) != record["archive_sha256"]:
        print("prune-appimage-toolset: %s is not the recorded %s" % (archive, record["archive"]), file=sys.stderr)
        return 1
    for what, table in (("runtime", record.get("runtimes", {})), ("file", record["removed"])):
        for rel, digest in table.items():
            try:
                good = sha256(os.path.join(src, rel)) == digest
            except OSError as e:
                print("prune-appimage-toolset: recorded %s %s is not in %s (%s)" % (what, rel, src, e.strerror), file=sys.stderr)
                return 1
            if not good:
                print("prune-appimage-toolset: %s %s does not match its recorded sha256" % (what, rel), file=sys.stderr)
                return 1
    # the cached, already-extracted toolset must be exactly what the verified archive holds
    with tempfile.TemporaryDirectory(prefix="appimage-toolset-") as tmp:
        if archive.endswith(".7z"):
            subprocess.run(["7z", "x", "-y", "-o" + tmp, archive], check=True, stdout=subprocess.DEVNULL)
        else:
            with tarfile.open(archive) as tf:
                tf.extractall(tmp, filter="tar")
        entries = os.listdir(tmp)
        fresh = os.path.join(tmp, entries[0]) if len(entries) == 1 and os.path.isdir(os.path.join(tmp, entries[0])) else tmp
        # every regular file equal; the links equal, except that electron-builder's extraction drops a link whose target
        # is itself a link (libopenjp2.so -> libopenjp2.so.7): only such a link may be missing from the cache
        fresh_links, src_links = links_of(fresh), links_of(src)
        def link_to_link(k):
            return os.path.join(os.path.dirname(k), fresh_links[k]) in fresh_links
        missing = [k for k in fresh_links if k not in src_links and not link_to_link(k)]
        if (tree_digest(fresh) != tree_digest(src) or missing
                or any(fresh_links.get(k) != v for k, v in src_links.items())):
            print("prune-appimage-toolset: %s does not match the extraction of %s" % (src, record["archive"]), file=sys.stderr)
            return 1
    shutil.rmtree(out, ignore_errors=True)
    shutil.copytree(src, out, symlinks=True)
    for rel in record["removed"]:
        os.remove(os.path.join(out, rel))
        d = os.path.dirname(os.path.join(out, rel))
        for name in os.listdir(d):             # a symlink left pointing at a removed file goes too
            link = os.path.join(d, name)
            if os.path.islink(link) and not os.path.exists(link):
                os.remove(link)
    print("pruned %s -> %s (removed %d files)" % (record["toolset"], out, len(record["removed"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
