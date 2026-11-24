#!/usr/bin/env python3
"""`Sources`: the one resolver for the paths a job reads its inputs from.

An upload job has one root (its `upload/` directory); a local job (design 7, 8.1) has the roots the user picked, each
a directory or a single file. Every function that took an `upload_dir` string takes a `Sources` (or a string, through
`Sources.coerce`) and asks it for `abs_of(root, rel)`, so the realpath containment rule lives here once.

Windows (t_9b8f56f0): a link is a symlink or a junction / mount point (`oscompat.islink`); a relative path with a
drive or a colon (an alternate data stream) is outside; a picked path must carry a drive or a UNC share; a device path, an
extended-length path and a drive root are refused; `SVF_MAKER_ROOTS` is `;`-separated (`os.pathsep`). Real paths come from
`os.path.realpath` (GetFinalPathNameByHandle: long names, the on-disk case, the drive letter upper-case), so two
spellings of one folder compare equal; every overlap rule is decided by volume serial + file index, as by inode on
POSIX.

Stdlib only.
"""

import os

import oscompat

FILE_CAP = 2000                       # a local walk stops at this many files
LOCAL_FILE_CAP = 256 << 20            # a local file over this is refused ("too large, skipped")
LOCAL_BYTES_CAP = 1 << 30             # a local walk stops once the files add up past this
LOCAL_FREE_MIN = 256 << 20            # the free space a local run needs in the output folder (Task 7)

KINDS = ("upload", "local")


class PathRefused(ValueError):
    """A picked path the maker will not use; `.reason` is the sentence the page shows."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class OutputGone(Exception):
    """A local job's output folder is gone or is no longer the folder that was picked."""


def stat_id(path):
    """`(st_dev, st_ino)` of @p path (symlinks followed)."""
    st = os.stat(path)
    return (st.st_dev, st.st_ino)


def ancestors_ids(path):
    """The ids of @p path, its parent, and so on up to `/` (the path is resolved first)."""
    out = []
    current = os.path.realpath(path)
    while True:
        out.append(stat_id(current))
        parent = os.path.dirname(current)
        if parent == current:
            return out
        current = parent


def overlaps(a, b):
    """True when one of @p a, @p b is the other or lies inside it, decided by inode (a symlinked parent cannot hide
    it); a cheap prefix pass on the real paths runs first."""
    ra, rb = os.path.realpath(a), os.path.realpath(b)
    if ra == rb or ra.startswith(rb + os.sep) or rb.startswith(ra + os.sep):
        return True
    return stat_id(a) in ancestors_ids(b) or stat_id(b) in ancestors_ids(a)


class Sources:
    """The input roots of a job: @p kind `"upload"` or `"local"`, @p roots absolute paths, @p tmp_dir for temp copies."""

    def __init__(self, kind, roots, tmp_dir=None, kinds=None):
        if kind not in KINDS:
            raise ValueError("Sources kind %r is not one of %s" % (kind, "/".join(KINDS)))
        self.kind = kind
        self.roots = list(roots)
        self.tmp_dir = tmp_dir
        if kinds is None:                         # probed once here; a job passes the kinds recorded at put time
            kinds = ["file" if kind == "local" and os.path.isfile(r) and not os.path.isdir(r) else "dir"
                     for r in self.roots]
        self.kinds = list(kinds)

    def __repr__(self):
        return "Sources(%r, %r)" % (self.kind, self.roots)

    @staticmethod
    def coerce(value):
        """A `Sources` passes through, a string is an upload directory, None stays None."""
        if value is None or isinstance(value, Sources):
            return value
        if isinstance(value, str):
            return Sources("upload", [value])
        raise TypeError("not a Sources or a path: %r" % (value,))

    def is_file_root(self, i):
        """True when root @p i is a single picked file (a local job only; an upload root is a directory)."""
        return self.kinds[i] == "file"

    def abs_of(self, root, rel):
        """The absolute path of @p rel under root @p root; `ValueError("outside")` when it is not strictly under it.

        A directory root: the realpath of the joined path must be under `realpath(root) + os.sep` (the root itself
        is refused). A file root: @p rel must be the file's own basename, and the root is returned.
        """
        if isinstance(root, bool) or not isinstance(root, int) or not 0 <= root < len(self.roots):
            raise ValueError("outside")
        if not isinstance(rel, str) or not rel or "\0" in rel or os.path.isabs(rel):
            raise ValueError("outside")
        if oscompat.WINDOWS and (":" in rel or os.path.splitdrive(rel)[0] or rel[:1] in "\\/"):
            raise ValueError("outside")           # a drive, a rooted path or an alternate data stream
        base = self.roots[root]
        if self.is_file_root(root):
            if rel != os.path.basename(base):
                raise ValueError("outside")
            return base
        joined = os.path.join(base, rel)
        real = os.path.realpath(joined)
        real_base = os.path.realpath(base)
        if not real.startswith(real_base + os.sep):
            raise ValueError("outside")
        if self.kind == "local" and real != os.path.join(real_base, os.path.normpath(rel)):
            raise ValueError("outside")           # a link below the root: `walk` refuses it, so does this
        return joined

    def inside(self, abs_path):
        """True when the realpath of @p abs_path is under a root, or is a file root."""
        try:
            return self._locate(abs_path) is not None
        except (OSError, ValueError, TypeError):
            return False

    def rel_of(self, abs_path):
        """`(root index, "/"-separated rel)` of the first root that contains @p abs_path; `ValueError` for none."""
        found = self._locate(abs_path)
        if found is None:
            raise ValueError("outside")
        return found

    def _locate(self, abs_path):
        real = os.path.realpath(abs_path)
        for i, base in enumerate(self.roots):
            real_base = os.path.realpath(base)
            if self.is_file_root(i):
                if real == real_base:
                    return i, os.path.basename(base)
            elif real.startswith(real_base + os.sep):
                return i, os.path.relpath(real, real_base).replace(os.sep, "/")
        return None

    def walk(self):
        """`(files, refused)`, both in `(root, rel)` order: `files` are regular files `(root, rel, abs)`.

        Links are never followed: a symlinked file is refused with "symlink, skipped" (both kinds), and so is a
        symlinked directory of a local root (an upload root omits it silently, as `os.walk` does). Devices, sockets
        and FIFOs are dropped silently. A local walk is capped: a file over `LOCAL_FILE_CAP` is "too large,
        skipped", and the walk stops at `FILE_CAP` files or `LOCAL_BYTES_CAP` bytes with one refusal `(root, "",
        message)`. An upload walk has no caps.
        """
        local = self.kind == "local"
        files, refused = [], []
        total = 0
        stop = None
        seen = set()                                  # local: a file reached through two roots is listed once
        for i, base in enumerate(self.roots):
            if stop:
                break
            if self.is_file_root(i):
                name = os.path.basename(base)
                if oscompat.islink(base):
                    refused.append((i, name, "symlink, skipped"))
                elif not os.path.isfile(base):
                    refused.append((i, name, "file is gone or changed"))
                else:
                    stop, total = self._admit(files, refused, i, name, base, os.lstat(base), total, local, seen)
                continue
            if local and (oscompat.islink(base) or not os.path.isdir(base)):
                refused.append((i, "", "folder is gone or changed"))
                continue

            def unreadable(exc, i=i, base=base):
                if local and exc.filename:
                    rel = os.path.relpath(exc.filename, base).replace(os.sep, "/")
                    if rel != ".":
                        refused.append((i, rel, "unreadable, skipped"))

            for dirpath, dirnames, filenames in os.walk(base, followlinks=False, onerror=unreadable):
                dirnames.sort()
                linked = []
                for d in dirnames:
                    path = os.path.join(dirpath, d)
                    if oscompat.islink(path):
                        linked.append(d)
                        if local:
                            refused.append((i, os.path.relpath(path, base).replace(os.sep, "/"), "symlink, skipped"))
                if linked:                                   # never descended (os.walk already skips a symlink; a junction too)
                    dirnames[:] = [d for d in dirnames if d not in linked]
                for name in sorted(filenames):
                    path = os.path.join(dirpath, name)
                    rel = os.path.relpath(path, base).replace(os.sep, "/")
                    if oscompat.islink(path):
                        refused.append((i, rel, "symlink, skipped"))
                        continue
                    if not os.path.isfile(path):
                        continue                                 # a device, a socket or a FIFO
                    try:
                        st = os.lstat(path)
                    except OSError:
                        continue
                    stop, total = self._admit(files, refused, i, rel, path, st, total, local, seen)
                    if stop:
                        break
                if stop:
                    break
        files.sort(key=lambda item: (item[0], item[1]))
        refused.sort(key=lambda item: (item[0], item[1]))
        if stop:
            refused.append((stop[0], "", stop[1]))      # last, so the page shows the cut after what was kept
        return files, refused

    @staticmethod
    def _admit(files, refused, i, rel, path, st, total, local, seen):
        """Add one regular file to @p files under the local caps; returns `(stop or None, total)`."""
        size = st.st_size
        if local:
            if (st.st_dev, st.st_ino) in seen:
                return None, total                         # the same file through an overlapping root
            seen.add((st.st_dev, st.st_ino))
            if size > LOCAL_FILE_CAP:
                refused.append((i, rel, "too large, skipped"))
                return None, total
            if len(files) >= FILE_CAP:
                return (i, "more than %d files: choose a smaller folder" % FILE_CAP), total
            if total + size > LOCAL_BYTES_CAP:
                return (i, "more than 1 GiB: choose a smaller folder"), total
            total += size
        files.append((i, rel, path))
        return None, total


def allowed_roots(environ):
    """`SVF_MAKER_ROOTS` (colon-separated, Windows `;`-separated: `os.pathsep`; each entry realpath'd) or None when
    unset or empty."""
    raw = (environ.get("SVF_MAKER_ROOTS") or "").strip()
    items = [os.path.realpath(item) for item in raw.split(os.pathsep) if item.strip()]
    return items or None


def check_path(path, *, want, data_root, allowed):
    """`(realpath, "file" | "dir")` of a picked @p path, or `PathRefused` with the sentence the page shows.

    @p want is `"source"` (a regular file or a folder) or `"output"` (a folder). Only the last component is checked
    for being a link (the path the user picked); every overlap rule is decided by inode (`overlaps`).
    """
    if not isinstance(path, str) or not os.path.isabs(path):
        raise PathRefused("not an absolute path")
    if len(path.encode("utf-8", "surrogateescape")) > 4096:
        raise PathRefused("path too long")
    if "\0" in path:
        raise PathRefused("NUL in path")
    if oscompat.WINDOWS:
        if path.replace("/", "\\")[:4] in ("\\\\?\\", "\\\\.\\") or not os.path.splitdrive(path)[0]:
            raise PathRefused("not an absolute path")          # a device or extended-length path, or no drive or share
        if ":" in os.path.splitdrive(path)[1]:
            raise PathRefused("not a regular file or folder")  # an alternate data stream
    path = os.path.normpath(path)
    if not os.path.lexists(path):
        raise PathRefused("no such file or folder")
    if oscompat.islink(path):
        raise PathRefused("the path is a symlink")
    real = os.path.realpath(path)
    if real == os.sep or (oscompat.WINDOWS and os.path.dirname(real) == real):
        raise PathRefused("/ cannot be chosen")
    is_dir = os.path.isdir(real)
    if want == "source":
        if not (is_dir or os.path.isfile(real)):
            raise PathRefused("not a regular file or folder")
    elif not is_dir:
        raise PathRefused("not a folder")
    if data_root and os.path.exists(data_root) and overlaps(real, data_root):
        raise PathRefused("the data folder cannot be chosen")
    if allowed is not None and not any(real == base or real.startswith(base + os.sep) for base in allowed):
        raise PathRefused("outside SVF_MAKER_ROOTS")
    return real, "dir" if is_dir else "file"
