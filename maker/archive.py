#!/usr/bin/env python3
"""Upload archive unpacking with the guards.

`kind_of` tags an archive from its magic, `check_rel_path` refuses a member name that would escape or confuse the
upload tree, and `unpack` streams a top-level zip/tar/gzip/xz into @p dest. A member is refused (and the unpack
stops, keeping what was already written) when it is over the member or total size, would inflate past `ratio`
times the packed size, is not a regular file or directory, is a sparse tar member, has a name `check_rel_path`
refuses, is itself an archive, appears twice, or would push the archive past its file count. Nothing is ever
extracted with `extractall`.

A tar is read as a stream: this module decompresses it once and hands `tarfile` a stream, so every member is read
once, in order, as it arrives, and the unpack cost is linear in the archive size. No member is opened or
decompressed twice, and no seek ever rewinds the decompressor. The decompressed bytes `tarfile` reads outside a
member's data (its headers, including a pax or GNU longname header) are charged to the size and ratio guards
through `_TarStream`, so a header that names an enormous size stops before it is allocated; the bytes written to
disk are charged to the same guards, so a member whose data never passes through the stream (a sparse one) could
not slip past them either.

Whether a member is itself an archive is decided from a bounded peek: at most `PEEK_RAW` (64 KB) raw bytes are
read from the start of the member into a buffer, which is written first and then followed by the rest of the same
stream, so the member is read once and neither memory nor CPU can be driven past 64 KB of input per member. The
member is nested when that buffer is a zip, 7z, rar or tar as it stands, or is a gzip, xz or bz2 whose first 512
decompressed bytes (decompressed from the buffer only, never from the rest of the stream) are a zip or a tar
header; anything else, a `.pcf.gz` or `.ttf.gz` font included, is an ordinary member written as-is.

Member names are normalised in `unpack` only: a leading "./" is stripped repeatedly and empty components are
collapsed, so the archives `tar -cf x.tar .` and `shutil.make_archive` write unpack like any other and a name
that differs only in "//" or a leading "./" is still a duplicate. The bare "." (or "./") member is skipped when
it is a directory; a file by that name is refused. An interior "./", a "..", an absolute path and a drive letter
are still refused, and a path over 1024 bytes or deeper than 32 components is refused.

`bytes` in the result counts the decompressed member data that stays on disk: a member removed on a stop is
subtracted, so it is the sum of the written file sizes. The header bytes the guards also count are not reported.

Guards that go past the plan's list, so a malformed upload cannot crash the request that called this: a container
that will not parse is a `"broken archive"` stop (rather than a `zipfile`/`tarfile` exception), a corrupt tar
header after the first member is a `"broken archive"` stop (tarfile would end the archive silently), a zip name
flagged UTF-8 that is not is a `"bad name encoding"` stop, a member whose path runs through a file an earlier
member wrote is a `"<name>: not a directory"` stop, an encrypted or unsupported zip member stops with its own
reason, and no other exception escapes `unpack`: the last resort is an `"unpack error: <type>"` stop.

The module is standard library only.
"""

import bz2
import gzip
import lzma
import os
import re
import stat
import tarfile
import unicodedata
import zipfile
import zlib

# A container that claims to be an archive but will not parse (a truncated zip, a bad tar header) and the
# decompression errors a broken gzip/xz raises. `unpack` reports these as a stop, not as a crash: the upload path
# must never fail on a malformed upload.
_BROKEN = (zipfile.BadZipFile, zipfile.LargeZipFile, tarfile.TarError, gzip.BadGzipFile, lzma.LZMAError,
           zlib.error, EOFError)

# The archive limits (Global Constraints): a single member, the whole unpack, the packed-to-unpacked ratio, one
# path component and the number of files (Task 13's FILE_CAP, which passes its remaining allowance here).
# `unpack` takes them as an argument so a test can tighten one.
LIMITS = {"member": 134217728, "total": 536870912, "ratio": 50, "component": 255, "files": 2000}

_CHUNK = 1 << 20                # the copy chunk every counter is checked after
_HEAD = 512                     # the bytes `kind_of` needs to see a tar header (ustar at 257)
_PEEK_OUT = 512                 # the decompressed bytes the nested peek looks at
PEEK_RAW = 65536                # the most raw bytes the nested peek reads from a member (bounds its work)
_HEADER_CAP = 1 << 20           # the largest run of header bytes read while no member data is being copied
_NAME = 200                     # how much of a member name a stop reason echoes
_PATH_MAX = 1024                # the longest a whole relative path may be, in UTF-8 bytes
_DEPTH_MAX = 32                 # the most components a relative path may have

_ZIP_MAGIC = b"PK\x03\x04"
_GZIP_MAGIC = b"\x1f\x8b"
_XZ_MAGIC = b"\xfd7zXZ\x00"
_BZ2_MAGIC = b"BZh"
_SEVENZIP_MAGIC = b"7z\xbc\xaf\x27\x1c"
_RAR_MAGIC = b"Rar!\x1a\x07"
_TAR_OFFSET = 257
_TAR_MAGIC = b"ustar"

# The zip methods `zipfile` can read: anything else (Deflate64, AES, ...) is refused by name rather than crashing.
_SUPPORTED_ZIP = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA)

_DRIVE = re.compile(r"^[A-Za-z]:")

# Unicode categories that make a name confusing or unsafe: control (Cc), format (Cf), line (Zl) and paragraph
# (Zp) separators.
_CONTROL = ("Cc", "Cf", "Zl", "Zp")


class _Stop(Exception):
    """A refusal that ends the unpack; `.reason` is the `stopped` string it reports."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class _TarStream:
    """A decompressed tar stream that charges the bytes `tarfile` reads for its headers to the unpack counters.

    `tarfile` reads a pax or GNU longname/longlink header whole, before any member data passes through this
    module's counters. Every read made while `copying` is false is a header read: it is charged to the total and
    ratio guards and to a run counter that stops a header over `_HEADER_CAP` bytes before it is allocated. The
    reads made while a member's data is streamed are not charged here; `_pump` charges the bytes it writes, so
    member data is counted once and the holes of a sparse member (served without reading the stream) count too.

    `tarfile` is opened with `bufsize=_HEAD`, so it asks for one tar block at a time and never reads a whole
    buffer ahead of what it consumes: the header charge is exactly the header bytes, a member's data is not
    charged twice, and a header bomb still trips the run counter.
    """

    def __init__(self, raw, limits, state):
        self.raw = raw
        self.limits = limits
        self.state = state
        self.copying = False
        self._header = 0

    def header(self):
        """Start a header window: the reads until `member` are header reads again."""
        self.copying = False
        self._header = 0

    def member(self):
        """Start a member's data: its reads are charged by the writer, not here."""
        self.copying = True

    def read(self, size=-1):
        if not self.copying and (size is None or size < 0 or size > _HEADER_CAP):
            raise _Stop("header over %d bytes" % _HEADER_CAP)
        data = self.raw.read(size)
        if not self.copying:
            self._charge_header(len(data))
        return data

    def readinto(self, b):
        if not self.copying and len(b) > _HEADER_CAP:
            raise _Stop("header over %d bytes" % _HEADER_CAP)
        n = self.raw.readinto(b)
        if not self.copying:
            self._charge_header(n)
        return n

    def readable(self):
        return True

    def writable(self):
        return False

    def seekable(self):
        return False

    def close(self):
        self.raw.close()

    def _charge_header(self, n):
        self._header += n
        if self._header > _HEADER_CAP:
            raise _Stop("header over %d bytes" % _HEADER_CAP)
        if n <= 0:
            return
        state, limits = self.state, self.limits
        state["counted"] += n
        if state["counted"] > limits["total"]:
            raise _Stop("total over %d bytes" % limits["total"])
        if limits["packed"] and state["counted"] > limits["ratio"] * limits["packed"]:
            raise _Stop("total over ratio (%d x %d packed bytes)" % (limits["ratio"], limits["packed"]))


class _TarInfo(tarfile.TarInfo):
    """A `TarInfo` that records on the `TarFile` how the last header parse ended.

    `tarfile` treats a header it cannot parse after the first member as the end of the archive and returns None
    with no sign of the corruption. Recording the exception kind on the `TarFile` (`_end`) lets `unpack` tell a
    real end (an all-zero or absent header) from a corrupt or truncated one.
    """

    @classmethod
    def fromtarfile(cls, tf):
        try:
            return super().fromtarfile(tf)
        except tarfile.EOFHeaderError:
            tf._end = "eof"
            raise
        except tarfile.EmptyHeaderError:
            tf._end = "empty"
            raise
        except tarfile.InvalidHeaderError:
            tf._end = "invalid"
            raise
        except tarfile.TruncatedHeaderError:
            tf._end = "truncated"
            raise


# ---- sniffing --------------------------------------------------------------------------------------------------

def kind_of(head):
    """The archive kind of @p head: `"zip"`, `"gzip"`, `"xz"`, `"tar"` or `None`.

    A tar header's magic sits at 257, so @p head must hold at least 512 bytes to name a tar.
    """
    if head[:4] == _ZIP_MAGIC:
        return "zip"
    if head[:2] == _GZIP_MAGIC:
        return "gzip"
    if head[:6] == _XZ_MAGIC:
        return "xz"
    if len(head) >= _HEAD and head[_TAR_OFFSET:_TAR_OFFSET + len(_TAR_MAGIC)] == _TAR_MAGIC:
        return "tar"
    return None


def _nested_from(buf):
    """True when the raw member bytes @p buf (at most `PEEK_RAW` of them) are an archive, from @p buf alone.

    A zip, 7z or rar member is nested as it stands, and so is a plain tar (`ustar` at 257). A gzip, xz or bz2
    member is nested only when the first `_PEEK_OUT` bytes inside it, decompressed from @p buf alone, are a zip
    or a tar header. Nothing beyond @p buf is read or fed to a decompressor, so the decision costs at most
    `PEEK_RAW` input bytes whatever the member claims its decompressed size to be.
    """
    if buf.startswith(_ZIP_MAGIC) or buf.startswith(_SEVENZIP_MAGIC) or buf.startswith(_RAR_MAGIC):
        return True
    if buf[_TAR_OFFSET:_TAR_OFFSET + len(_TAR_MAGIC)] == _TAR_MAGIC:
        return True
    if buf.startswith(_GZIP_MAGIC):
        inner = _decompress_head(buf, "gzip")
    elif buf.startswith(_XZ_MAGIC):
        inner = _decompress_head(buf, "xz")
    elif buf.startswith(_BZ2_MAGIC):
        inner = _decompress_head(buf, "bz2")
    else:
        return False
    return inner.startswith(_ZIP_MAGIC) or inner[_TAR_OFFSET:_TAR_OFFSET + len(_TAR_MAGIC)] == _TAR_MAGIC


def _decompress_head(buf, kind):
    """The first `_PEEK_OUT` bytes @p buf holds inside its gzip/xz/bz2 stream, or `b""` when it will not decompress.

    Only @p buf is fed to the decompressor: nothing beyond it is read, so the work is bounded by `PEEK_RAW` bytes
    of input however large a decompressed size the member claims. A truncated header, a decompression error and a
    stream with no output yet all answer `b""`, i.e. "not nested".
    """
    try:
        if kind == "gzip":
            return zlib.decompressobj(31).decompress(buf, _PEEK_OUT)
        if kind == "xz":
            return lzma.LZMADecompressor().decompress(buf, max_length=_PEEK_OUT)
        return bz2.BZ2Decompressor().decompress(buf, max_length=_PEEK_OUT)
    except (zlib.error, lzma.LZMAError, OSError, EOFError, ValueError):
        return b""


def is_nested_archive(head, member_bytes_reader):
    """True when the member whose first stored bytes are @p head is an archive itself.

    @p member_bytes_reader is a zero-argument callable returning a fresh binary stream of the member's stored
    bytes. Only the first `PEEK_RAW` stored bytes are read and looked at, so the answer is bounded whatever the
    member claims. A zip, 7z, rar or tar member is nested as it stands; a gzip, xz or bz2 member is nested only
    when the bytes inside it (from that buffer alone) are a zip or a tar header. A gzip/xz member holding a plain
    file (`18x18ko.pcf.gz`, `font.bdf.gz`) is an ordinary file: it is written as-is, stays compressed, and
    `detect` undoes that one level later.
    """
    buf = head
    if len(buf) < PEEK_RAW:
        raw = member_bytes_reader()
        if raw is not None:
            try:
                buf = buf + raw.read(PEEK_RAW - len(buf))
            finally:
                raw.close()
    return _nested_from(buf)


# ---- the path guard --------------------------------------------------------------------------------------------

def check_rel_path(rel, component=LIMITS["component"]):
    """The reason @p rel is not a safe upload-relative path, or `None` when it is one.

    Components are split on "/": nothing absolute, no backslash, no control, format or separator character, no
    ".." or "." component, no empty component (a trailing slash or "//": W5), no drive-letter first component
    (`"C:..."`), no empty path, no component over @p component bytes, no path over `_PATH_MAX` bytes and no path
    deeper than `_DEPTH_MAX` components.
    """
    if not rel:
        return "empty path"
    if rel.startswith("/"):
        return "absolute path"
    if "\\" in rel:
        return "backslash in path"
    if any(unicodedata.category(c) in _CONTROL for c in rel):
        return "control character in path"
    parts = rel.split("/")
    if _DRIVE.match(parts[0]):
        return "drive letter in path"
    if "" in parts:
        return "empty path component"
    if ".." in parts:
        return "path has .."
    if "." in parts:
        return "path has ."
    if any(len(part.encode("utf-8", "surrogateescape")) > component for part in parts):
        return "path component over %d bytes" % component
    if len(rel.encode("utf-8", "surrogateescape")) > _PATH_MAX or len(parts) > _DEPTH_MAX:
        return "path too long"
    return None


# ---- unpacking -------------------------------------------------------------------------------------------------

def unpack(path, dest, limits=LIMITS):
    """Unpack the top-level archive @p path into @p dest; return `{"files", "bytes", "stopped"}`.

    `files` counts the files written, `bytes` the decompressed member data that stays on disk (the header bytes
    the guards also count are not reported), and `stopped` is `None` or the reason the unpack ended. Files land
    at `dest/<member name>`; whatever was written before a refusal stays. No exception escapes: an unexpected one
    becomes an `"unpack error: <type>"` stop.
    """
    counted = {"member": limits.get("member", LIMITS["member"]), "total": limits.get("total", LIMITS["total"]),
               "ratio": limits.get("ratio", LIMITS["ratio"]), "component": limits.get("component", LIMITS["component"]),
               "files": limits.get("files", LIMITS["files"]), "packed": 0}
    state = {"files": 0, "bytes": 0, "counted": 0, "members": 0, "stopped": None}
    try:
        counted["packed"] = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(PEEK_RAW)                                     # enough for `kind_of` and the nested peek
        kind = kind_of(head)
        if kind == "zip":
            _unpack_zip(path, dest, counted, state)
        elif kind == "tar":
            _unpack_tar(path, dest, counted, state, "tar")
        elif kind in ("gzip", "xz"):
            if _nested_from(head):                                      # a tar.gz / tar.xz
                _unpack_tar(path, dest, counted, state, kind)
            else:
                _unpack_single(path, dest, kind, counted, state)
        else:
            raise _Stop("not an archive")
    except _Stop as stop:
        state["stopped"] = stop.reason
    except UnicodeDecodeError as exc:                                   # a zip name flagged UTF-8 that is not
        state["stopped"] = "%s: bad name encoding" % repr(exc.object[:_NAME])
    except _BROKEN:
        state["stopped"] = "broken archive"
    except (RuntimeError, NotImplementedError):                         # a zip method or password zipfile cannot read
        state["stopped"] = "broken archive"
    except Exception as exc:                                            # last resort: nothing escapes the upload path
        state["stopped"] = "unpack error: %s" % type(exc).__name__
    return {"files": state["files"], "bytes": state["bytes"], "stopped": state["stopped"]}


def _unpack_zip(path, dest, limits, state):
    """A zip: the central directory is counted first, then every member through `ZipFile.open`, directories skipped."""
    seen = set()
    with zipfile.ZipFile(path) as zf:
        if len(zf.infolist()) > limits["files"] + 1:                     # over the count: refuse before reading any
            raise _Stop("more than %d files" % limits["files"])
        for info in zf.infolist():
            name = _normalize(info.filename)
            if name == "":
                if info.is_dir() or not info.filename:
                    continue
                raise _Stop("%s: path has ." % _short(info.filename))
            _count_member(limits, state)
            _refuse(name, limits)
            if info.is_dir():
                continue
            if _not_a_regular_file(info):
                raise _Stop("%s: not a regular file" % _short(name))
            if info.compress_type not in _SUPPORTED_ZIP:
                raise _Stop("%s: unsupported compression" % _short(name))
            if info.flag_bits & 0x1:
                raise _Stop("%s: encrypted" % _short(name))
            if name in seen:
                raise _Stop("%s: duplicate member" % _short(name))
            seen.add(name)
            try:
                _copy(lambda: zf.open(info), name, dest, limits, state, peek=True)
            except NotImplementedError:
                raise _Stop("%s: unsupported compression" % _short(name))
            except RecursionError:
                raise                                                       # a deep path is not an "encrypted" member
            except RuntimeError:
                raise _Stop("%s: encrypted" % _short(name))


def _unpack_tar(path, dest, limits, state, kind):
    """A tar (or a gzip/xz holding one), read as a stream: every member once, in order, as it arrives.

    The decompressed stream is wrapped so the bytes `tarfile` reads for its headers count against the size and
    ratio guards. `_TarInfo` records how the parse ended, so a corrupt header after a member is a stop rather
    than the silent end `tarfile` would make of it.
    """
    if kind == "gzip":
        raw = gzip.open(path, "rb")
    elif kind == "xz":
        raw = lzma.open(path, "rb")
    else:
        raw = open(path, "rb")
    with raw:
        stream = _TarStream(raw, limits, state)
        with tarfile.open(fileobj=stream, mode="r|", tarinfo=_TarInfo, bufsize=_HEAD) as tf:
            seen = set()
            while True:
                stream.header()
                tf._end = None
                member = tf.next()
                if member is None:
                    if tf._end in ("invalid", "truncated"):
                        raise _Stop("broken archive")
                    break
                name = _normalize(member.name)
                if name == "":
                    if member.isdir() or not member.name:
                        continue
                    raise _Stop("%s: path has ." % _short(member.name))
                _count_member(limits, state)
                _refuse(name, limits)
                if member.isdir():
                    continue
                if not member.isreg():
                    raise _Stop("%s: not a regular file" % _short(name))
                if member.issparse():
                    raise _Stop("%s: sparse member" % _short(name))
                if name in seen:
                    raise _Stop("%s: duplicate member" % _short(name))
                seen.add(name)
                stream.member()
                src = tf.extractfile(member)
                if src is None:
                    raise _Stop("%s: not a regular file" % _short(name))
                _copy(lambda: src, name, dest, limits, state, peek=True)


def _unpack_single(path, dest, kind, limits, state):
    """A top-level gzip/xz with no tar inside: write the single file `dest/<basename without .gz/.xz>`."""
    name = os.path.basename(path)
    for suffix in (".gz", ".xz"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    if not name:
        name = "upload"
    _count_member(limits, state)
    _refuse(name, limits)
    opener = gzip.open if kind == "gzip" else lzma.open
    _copy(lambda: opener(path, "rb"), name, dest, limits, state)


def _not_a_regular_file(info):
    """True when a zip entry's Unix mode says it is neither a regular file nor a directory.

    `ZipFile.writestr` records only permission bits (0o600), a Windows zip no Unix mode at all: both have no file
    type bits and count as regular files. A symlink, fifo, socket or device entry does not.
    """
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)


def _normalize(name):
    """The member name with a leading "./" stripped and empty components collapsed; `""` for the bare "." member.

    A member named "." or "./" (what `tar -cf x.tar .` writes) becomes `""`: `unpack` skips it when it is a
    directory and refuses it otherwise. Empty components are collapsed, so a name that differs only in "//" is
    the same member; a leading "/" is kept, so an absolute path is still refused.
    """
    while name.startswith("./"):
        name = name[2:]
    if name in (".", ""):
        return ""
    parts = name.split("/")
    lead = [""] if parts[0] == "" else []
    return "/".join(lead + [part for part in parts if part != ""])


def _short(name):
    """A member name cut to `_NAME` characters for a stop reason (a tar header can hold an enormous name)."""
    return name if len(name) <= _NAME else name[:_NAME]


def _count_member(limits, state):
    """Charge one member against the file limit, stopping before the member past it is written."""
    state["members"] += 1
    if state["members"] > limits["files"]:
        raise _Stop("more than %d files" % limits["files"])


def _refuse(name, limits):
    """Raise `_Stop` when the member name @p name fails the path guard."""
    reason = check_rel_path(name, limits.get("component", LIMITS["component"]))
    if reason is not None:
        raise _Stop("%s: %s" % (_short(name), reason))


def _copy(reader, name, dest, limits, state, peek=False):
    """Stream the member @p name (opened by @p reader) into @p dest in chunks, checking the counters after each.

    With @p peek the member's first `PEEK_RAW` stored bytes are read first: they decide nesting, and they are
    written first and then the rest of the same stream is copied, so the member is read once and the decision
    costs at most 64 KB of input. A stop mid-member removes the partial file: what the earlier members wrote
    stays, the refused member does not. The reader is opened before the output file, so no output handle is left
    open when the reader itself fails.
    """
    out_path = os.path.join(dest, *name.split("/"))
    try:
        with reader() as src:
            first = src.read(PEEK_RAW) if peek else b""
            if _nested_from(first):
                raise _Stop("nested archive %s (listed, not opened)" % _short(name))
            with _output(out_path, name) as out:
                _pump(src, out, name, limits, state, first=first)
    except BaseException:
        _remove(out_path)
        raise
    state["files"] += 1


def _remove(out_path):
    """Remove a partial output file, ignoring the case where the stop happened before it was created."""
    try:
        os.remove(out_path)
    except OSError:
        pass


def _output(out_path, name):
    """Open the output file for @p name, refusing a path that runs through an earlier member's file or directory.

    Every `OSError` (a path the filesystem refuses, a permission, a disk error) becomes a named stop rather than
    an exception out of `unpack`.
    """
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    except (NotADirectoryError, FileExistsError):
        raise _Stop("%s: not a directory" % _short(name))
    except OSError as exc:
        raise _Stop("%s: %s" % (_short(name), exc.strerror or type(exc).__name__))
    try:
        return open(out_path, "wb")
    except IsADirectoryError:
        raise _Stop("%s: is a directory" % _short(name))
    except OSError as exc:
        raise _Stop("%s: %s" % (_short(name), exc.strerror or type(exc).__name__))


def _pump(src, out, name, limits, state, first=b""):
    """Copy @p src into @p out in `_CHUNK` chunks, checking the member, total and ratio guards after each.

    @p first holds bytes already read from @p src (a member's peeked head); they are written first. The guards run
    before a chunk is written, and the caller removes the partial file on a stop. The bytes written are charged to
    the total and ratio guards here, so a member's data counts even when it never came from the decompressed
    stream (a sparse tar member) and no byte is counted twice. `bytes` counts only what is written: a stop (the
    caller removes the partial file) subtracts the chunks this member already wrote, so it stays the sum of the
    file sizes that remain on disk.
    """
    written = 0
    kept = 0
    chunk = first
    try:
        while True:
            if not chunk:
                chunk = src.read(_CHUNK)
                if not chunk:
                    break
            written += len(chunk)
            if written > limits["member"]:
                raise _Stop("%s: member over %d bytes" % (_short(name), limits["member"]))
            state["counted"] += len(chunk)
            if state["counted"] > limits["total"]:
                raise _Stop("total over %d bytes" % limits["total"])
            if limits["packed"] and state["counted"] > limits["ratio"] * limits["packed"]:
                raise _Stop("total over ratio (%d x %d packed bytes)" % (limits["ratio"], limits["packed"]))
            out.write(chunk)
            state["bytes"] += len(chunk)
            kept += len(chunk)
            chunk = b""
    except BaseException:
        state["bytes"] -= kept
        raise
