#!/usr/bin/env python3
"""`Sources`: the one resolver for the paths a job reads its inputs from.

An upload job has one root (its `upload/` directory); a local job (design 7, 8.1) has the roots the user picked, each
a directory or a single file. Every function that took an `upload_dir` string takes a `Sources` (or a string, through
`Sources.coerce`) and asks it for `abs_of(root, rel)`, so the realpath containment rule lives here once.

Stdlib only.
"""

import os

FILE_CAP = 2000                       # a local walk stops at this many files
LOCAL_FILE_CAP = 256 << 20            # a local file over this is refused ("too large, skipped")
LOCAL_BYTES_CAP = 1 << 30             # a local walk stops once the files add up past this
LOCAL_FREE_MIN = 256 << 20            # the free space a local run needs in the output folder (Task 7)

KINDS = ("upload", "local")


class Sources:
    """The input roots of a job: @p kind `"upload"` or `"local"`, @p roots absolute paths, @p tmp_dir for temp copies."""

    def __init__(self, kind, roots, tmp_dir=None):
        if kind not in KINDS:
            raise ValueError("Sources kind %r is not one of %s" % (kind, "/".join(KINDS)))
        self.kind = kind
        self.roots = list(roots)
        self.tmp_dir = tmp_dir

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
        return self.kind == "local" and os.path.isfile(self.roots[i]) and not os.path.isdir(self.roots[i])

    def abs_of(self, root, rel):
        """The absolute path of @p rel under root @p root; `ValueError("outside")` when it is not strictly under it.

        A directory root: the realpath of the joined path must be under `realpath(root) + os.sep` (the root itself
        is refused). A file root: @p rel must be the file's own basename, and the root is returned.
        """
        if isinstance(root, bool) or not isinstance(root, int) or not 0 <= root < len(self.roots):
            raise ValueError("outside")
        if not isinstance(rel, str) or not rel or "\0" in rel or os.path.isabs(rel):
            raise ValueError("outside")
        base = self.roots[root]
        if self.is_file_root(root):
            if rel != os.path.basename(base):
                raise ValueError("outside")
            return base
        joined = os.path.join(base, rel)
        if not os.path.realpath(joined).startswith(os.path.realpath(base) + os.sep):
            raise ValueError("outside")
        return joined

    def inside(self, abs_path):
        """True when the realpath of @p abs_path is under a root, or is a file root."""
        try:
            return self._locate(abs_path) is not None
        except (OSError, ValueError):
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
        for i, base in enumerate(self.roots):
            if stop:
                break
            if self.is_file_root(i) or (local and os.path.islink(base)):
                name = os.path.basename(base)
                if os.path.islink(base):
                    refused.append((i, name, "symlink, skipped"))
                    continue
                size = os.lstat(base).st_size
                stop, total = self._admit(files, refused, i, name, base, size, total, local)
                continue
            for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
                dirnames.sort()
                for d in dirnames:
                    path = os.path.join(dirpath, d)
                    if local and os.path.islink(path):
                        refused.append((i, os.path.relpath(path, base).replace(os.sep, "/"), "symlink, skipped"))
                for name in sorted(filenames):
                    path = os.path.join(dirpath, name)
                    rel = os.path.relpath(path, base).replace(os.sep, "/")
                    if os.path.islink(path):
                        refused.append((i, rel, "symlink, skipped"))
                        continue
                    if not os.path.isfile(path):
                        continue                                 # a device, a socket or a FIFO
                    try:
                        size = os.lstat(path).st_size
                    except OSError:
                        continue
                    stop, total = self._admit(files, refused, i, rel, path, size, total, local)
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
    def _admit(files, refused, i, rel, path, size, total, local):
        """Add one regular file to @p files under the local caps; returns `(stop or None, total)`."""
        if local:
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
