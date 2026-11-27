#!/usr/bin/env python3
"""Face manifest and map-face checks. Run with `python3 -I`.

  facecheck.py manifest --git REPO --rev REV --path DIR... [--exclude GLOB...] -o OUT.tsv
      One row per committed blob under the paths (path, sha256, bytes), read from the commit, not the working tree.
  facecheck.py verify MANIFEST.tsv [--map OLD_PREFIX=NEW_DIR...]
      Exit 0 when every row's file exists (its path with OLD_PREFIX replaced by NEW_DIR, relative to the current
      directory) with the same sha256; prints MISSING / CHANGED lines otherwise.
  facecheck.py mapfaces --maps DIR... --root PREFIX=DIR... [--builtin-zip FILE...]
      Exit 0 when every face a map names is found; prints MISSING <map> <face> otherwise. A map is any *.map / *.MAP
      file under the DIRs. Faces are the [fonts*] values and the file entries of face= / range.* chains. A bare name
      (or data:NAME) is looked up beside the map and under every root with prefix "."; data:A/B/C under the root whose
      prefix A/B/C starts with. A "#N" collection suffix is ignored. data:NAME is also found as a member of a
      --builtin-zip archive (fonts-cjk.dat: the engine's own faces, graphics/hires_text/font_map.cpp).
"""
import argparse
import fnmatch
import hashlib
import os
import subprocess
import sys
import zipfile

FACE_EXT = (".svf", ".ttf", ".otf", ".ttc")


def blobs(repo, rev, paths):
    """(path, blob sha1) of every file under the paths at rev."""
    out = subprocess.run(["git", "-C", repo, "ls-tree", "-r", "-z", rev, "--"] + paths, check=True,
                         capture_output=True).stdout
    for rec in out.split(b"\0"):
        if rec:
            meta, path = rec.split(b"\t", 1)
            yield path.decode(), meta.split()[2].decode()


def cmd_manifest(a):
    rows = [(p, b) for p, b in blobs(a.git, a.rev, a.path)
            if not any(fnmatch.fnmatch(os.path.basename(p), g) for g in a.exclude)]
    cat = subprocess.Popen(["git", "-C", a.git, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    with open(a.o, "w", newline="\n") as out:
        for path, blob in sorted(rows):
            cat.stdin.write(blob.encode() + b"\n")
            cat.stdin.flush()
            size = int(cat.stdout.readline().split()[2])
            data = cat.stdout.read(size)
            cat.stdout.read(1)
            out.write("%s\t%s\t%d\n" % (path, hashlib.sha256(data).hexdigest(), size))
    cat.stdin.close()
    cat.wait()
    return 0


def remap(path, maps):
    for old, new in maps:
        if path == old or path.startswith(old + "/"):
            return new + path[len(old):]
    return path


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_verify(a):
    maps = [tuple(m.split("=", 1)) for m in a.map]
    bad = 0
    for line in open(a.manifest):
        path, digest, _ = line.rstrip("\n").split("\t")
        new = remap(path, maps)
        if not os.path.isfile(new):
            print("MISSING", new)
            bad += 1
        elif sha256_file(new) != digest:
            print("CHANGED", new)
            bad += 1
    return 1 if bad else 0


def strip_comment(line):
    """A ';' at the line start, or after whitespace, starts a comment (graphics/hires_text/README.md)."""
    s = line.strip()
    if s.startswith((";", "#")):
        return ""
    for i, ch in enumerate(s):
        if ch == ";" and i and s[i - 1] in " \t":
            return s[:i].rstrip()
    return s


def map_faces(text):
    """The file entries a map names: [fonts*] values and file-looking entries of face= / range.* chains."""
    section = ""
    for raw in text.splitlines():
        line = strip_comment(raw)
        if not line:
            continue
        if line.startswith("["):
            section = line.strip("[]").lower()
            continue
        if "=" not in line:
            continue
        key, value = (x.strip() for x in line.split("=", 1))
        if section.startswith("fonts"):
            entries = [value]
        elif section.startswith("font") and (key == "face" or key.startswith("range.")):
            entries = [e.strip() for e in value.split(",")]
        else:
            continue
        for e in entries:
            name = e.split("#", 1)[0]
            if name.lower().endswith(FACE_EXT):
                yield name


def find_face(name, map_dir, roots, builtin=frozenset()):
    data = name.startswith("data:")
    rel = name[5:] if data else name
    if data and rel in builtin:
        return True
    if os.path.isabs(rel):
        return os.path.isfile(rel)
    if not data and os.path.isfile(os.path.join(map_dir, rel)):
        return True
    for prefix, root in roots:
        if prefix == ".":
            if os.path.isfile(os.path.join(root, rel)):
                return True
        elif rel.startswith(prefix + "/") and os.path.isfile(os.path.join(root, rel[len(prefix) + 1:])):
            return True
    return False


def cmd_mapfaces(a):
    roots = [tuple(r.split("=", 1)) for r in a.root]
    builtin = set()
    for z in a.builtin_zip:
        with zipfile.ZipFile(z) as zf:
            builtin.update(zf.namelist())
    bad = 0
    for top in a.maps:
        for dirpath, _, files in os.walk(top):
            for f in sorted(files):
                if not f.lower().endswith(".map"):
                    continue
                path = os.path.join(dirpath, f)
                text = open(path, encoding="utf-8", errors="replace").read()
                for face in sorted(set(map_faces(text))):
                    if not find_face(face, dirpath, roots, builtin):
                        print("MISSING", path, face)
                        bad += 1
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("--git", required=True)
    m.add_argument("--rev", required=True)
    m.add_argument("--path", action="append", required=True)
    m.add_argument("--exclude", action="append", default=[])
    m.add_argument("-o", required=True)
    v = sub.add_parser("verify")
    v.add_argument("manifest")
    v.add_argument("--map", action="append", default=[])
    f = sub.add_parser("mapfaces")
    f.add_argument("--maps", action="append", required=True)
    f.add_argument("--root", action="append", required=True)
    f.add_argument("--builtin-zip", action="append", default=[])
    a = ap.parse_args()
    return {"manifest": cmd_manifest, "verify": cmd_verify, "mapfaces": cmd_mapfaces}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
