#!/usr/bin/env python3
"""Naming: the file-name suggestion, the note text and the index of the checkout's `svf/` tree.

Every name is only a suggestion: the owner edits it in the page before `run` (spec, "The file-name suggestion").
`RepoIndex` is what the maker knows about the checkout's `svf/`: the destination folders that exist, the entry names
in them, the sha256 of every readable regular file (so a produced face or text that is byte-equal to one already there
is reused instead of written) and the first line of every text (the page's "use an existing licence" pick).

The library assumes `maker/` and `tools/` are on sys.path (the entry points set it).
"""

import hashlib
import unicodedata
import os
import re
import stat

import oscompat

# A face name, a text name and a destination folder (Global Constraints).
NAME_RE = re.compile(r"^[A-Z0-9]{1,8}\.SVF$")
TXT_RE = re.compile(r"^[A-Z0-9]{1,8}\.TXT$")
# A face's TTF / BDF export (`maker/routes.py` export_name): the face's stem and a lower-case extension.
EXPORT_RE = re.compile(r"^[A-Z0-9]{1,8}\.(ttf|bdf)$")
DEST_RE = re.compile(r"^(dos|jamo-extra|games/[a-z0-9-]+|new/[a-z0-9-]+)$")

_ABBR_CHARS = re.compile(r"[A-Za-z0-9]")
_SIL_MARK = "SIL OPEN FONT LICENSE"

FIRST_LINE_BYTES = 4096     # detect._first_line's window, so the page shows the same line for both
FIRST_LINE_MAX = 120

CHUNK_BYTES = 1 << 20       # a file is hashed chunk by chunk, never read whole
MAX_FIELD_BYTES = 512       # a note's fields and command lines are single lines, capped in bytes


# U+202A..U+202E and U+2066..U+2069: bidi embedding, override and isolate controls
_BIDI_CONTROLS = set("\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")

def abbr(family):
    """The first 5 ASCII letters or digits of @p family, upper-cased; `"FONT"` when there are none.

    The repository's own names are hand-picked, so this is a starting point only: `"NanumGothic"` -> `"NANUM"`,
    `"Gothic A1"` -> `"GOTHI"`, `"D2 Coding"` -> `"D2COD"`, `"나눔고딕"` -> `"FONT"`.
    """
    return "".join(_ABBR_CHARS.findall(family or ""))[:5].upper() or "FONT"


def windows_reserved(name):
    """True on Windows when the face/text name or destination @p name (`NAME.SVF`, `games/<name>`) has a part
    Windows cannot hold as a plain file or folder name (a device name: `CON.SVF`, `NUL.TXT`, `new/con`). Always False
    elsewhere: the names are valid there."""
    return oscompat.WINDOWS and any(oscompat.windows_unsafe_name(part) for part in name.split("/"))


def _unreserved(stem):
    """@p stem, with a `0` added on Windows when it is a device name there (`CON` -> `CON0`)."""
    return stem + "0" if windows_reserved(stem) else stem


def suggest_face_name(family, px, bpp, kind, svf_stem=None):
    """The suggested `.SVF` name: `svf_stem` kept when an SVF source gives one, else `abbr` + the size.

    `px` is 2 digits (`"%02d"`, so 3 above 99) and a 2 bpp face carries an `A`. A jamo set uses the first 4
    abbreviation characters, then `J` before the `A`. A 3 digit size makes a 9 character name that `NAME_RE`
    rejects; the suggestion is still returned, and validation reports it so the owner shortens it.
    """
    if svf_stem:
        return _unreserved(svf_stem.upper()[:8])[:8] + ".SVF"
    px2 = "%02d" % px
    a = "A" if bpp == 2 else ""
    if kind == "jamo":
        return abbr(family)[:4] + px2 + "J" + a + ".SVF"
    return abbr(family) + px2 + a + ".SVF"


def suggest_licence_name(family, text):
    """`OFL`/`LIC` + `abbr` + `.TXT`: `OFL` when @p text carries the SIL Open Font License marker."""
    head = "OFL" if _SIL_MARK in (text or "").upper() else "LIC"
    return head + abbr(family) + ".TXT"


def suggest_note_name(family):
    """The suggested note name: `abbr` + `.TXT`."""
    return _unreserved(abbr(family)) + ".TXT"


def _check_note_field(value, field, newlines=False):
    """Refuse the @p value that would forge or overrun a line of the note.

    A control character is refused (only `\\n` is allowed, and only where it separates command lines, i.e. when
    @p newlines), as is any line longer than `MAX_FIELD_BYTES` bytes (the cap is bytes, not characters).
    """
    for ch in value:
        if ch == "\n" and newlines:
            continue
        if unicodedata.category(ch) in ("Cc", "Zl", "Zp") or ch in _BIDI_CONTROLS:
            raise ValueError("note_text: %s carries the control character %r" % (field, ch))
    for line in value.split("\n"):
        if len(line.encode("utf-8")) > MAX_FIELD_BYTES:
            raise ValueError("note_text: %s has a line longer than %d bytes" % (field, MAX_FIELD_BYTES))


def note_text(family, style, names, source_file, version, date, commands, licence=None):
    """The note's text: the faces' line, the source, the version, the maker's stamp, then one line per command.

    The first line is `"<family> <style> faces (<names>)"`, or `"<family> faces (<names>)"` when the style is empty;
    `names` are comma-joined. Lines end in `\\n`, including the last. A field or command carrying a control
    character (a `\\n` is allowed inside a command, where it separates command lines) or a line longer than
    `MAX_FIELD_BYTES` bytes is refused with `ValueError`: a crafted family or command must not be able to forge a
    provenance line or an absurd one. A local job without a licence passes @p licence, a line placed after `Made:`.
    """
    for value, field in ((family, "family"), (style, "style"), (source_file, "source_file"), (version, "version"), (date, "date"), (licence, "licence")):
        _check_note_field(value or "", field)
    for command in commands:
        _check_note_field(command or "", "command", newlines=True)
    title = "%s %s faces (%s)" % (family, style, ", ".join(names)) if style else "%s faces (%s)" % (family, ", ".join(names))
    head = [title, "", "Source: %s" % source_file, "Version: %s" % version, "Made: %s by maker/ (svf-fonts)" % date] + ([licence] if licence else []) + [""]
    return "\n".join(head + [c.rstrip("\n") for c in commands]) + "\n"


def duplicates(names):
    """The values of @p names that occur more than once, in first-appearance order."""
    seen = set()
    twice = []
    for name in names:
        if name in seen:
            if name not in twice:
                twice.append(name)
        else:
            seen.add(name)
    return twice


def _first_line(data):
    """The first non-empty line of @p data's first `FIRST_LINE_BYTES`, stripped and at most `FIRST_LINE_MAX`
    characters; "" when there is none. A leading UTF-8 BOM is stripped first (`detect._first_line`'s rule)."""
    for line in data[:FIRST_LINE_BYTES].decode("utf-8", "replace").lstrip("\ufeff").splitlines():
        line = line.strip()
        if line:
            return line[:FIRST_LINE_MAX]
    return ""


class RepoIndex:
    """The checkout's `svf/` tree, walked once at construction.

    `.folders` are the destinations that hold at least one `.SVF`/`.svf` entry (`"dos"`, `"games/<name>"`, sorted);
    `.names` maps a folder to its upper-cased entry names; `.by_sha` maps a readable file's sha256 to its
    `svf/`-relative path, the first in sorted order; `.texts` lists `{"path", "first_line"}` for every
    `.TXT`/`.txt`. Names come from the directory listing, so an entry a write would clash with is always listed —
    even a symlink, or a file whose bytes cannot be read. Only regular, non-symlink files are hashed (in chunks);
    a file that vanishes or becomes unreadable after the walk is indexed with no sha (`sha_of` returns `None`) and
    is never reported "identical".
    """

    def __init__(self, svf_dir):
        self.dir = os.path.abspath(svf_dir)
        self.folders = []
        self.names = {}
        self.by_sha = {}
        self.texts = []
        self._sha = {}
        self.unlisted = set()
        for folder, entries in self._walk():
            if folder:
                self.names[folder] = {name.upper() for name in entries}
                if any(name.upper().endswith(".SVF") for name in entries):
                    self.folders.append(folder)
            for name in entries:
                rel = folder + "/" + name if folder else name
                sha, head = self._read(os.path.join(self.dir, folder, name))
                self._sha[rel] = sha
                if sha is not None:
                    self.by_sha.setdefault(sha, rel)
                if name.upper().endswith(".TXT") and sha is not None:
                    self.texts.append({"path": rel, "first_line": _first_line(head)})
        self.folders.sort()

    @staticmethod
    def _read(full):
        """`(sha256 hex, first `FIRST_LINE_BYTES` bytes)` of the regular file @p full, or `(None, b"")` when it is
        not a regular file (`lstat`: a symlink is never followed, so a link is never hashed) or cannot be read (it
        vanished, or its permissions changed after the walk)."""
        try:
            if not stat.S_ISREG(os.lstat(full).st_mode):
                return (None, b"")
            digest = hashlib.sha256()
            head = b""
            with open(full, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    if len(head) < FIRST_LINE_BYTES:
                        head += chunk[:FIRST_LINE_BYTES - len(head)]
                    digest.update(chunk)
        except OSError:
            return (None, b"")
        return (digest.hexdigest(), head)

    def _walk(self):
        """`(folder, [entry names])` for every directory under `self.dir`, sorted; `folder` is `svf/`-relative with
        `/` separators (`""` for `svf/` itself).

        `os.walk(followlinks=False)` never descends a symlinked directory, so every entry of a directory it does
        visit is listed here — symlinks to files and to directories alike — because an existing name is a clash
        whatever it is: a write would follow the link or fail on it.
        """
        out = []
        def unreadable(err):
            # a folder the walk cannot list: every name in it counts as a clash (check_face), never "ok"
            self.unlisted.add(os.path.relpath(err.filename, self.dir).replace(os.sep, "/"))

        for root, dirs, files in os.walk(self.dir, followlinks=False, onerror=unreadable):
            dirs.sort()
            folder = os.path.relpath(root, self.dir).replace(os.sep, "/")
            linked = [d for d in dirs if oscompat.islink(os.path.join(root, d))]
            dirs[:] = [d for d in dirs if d not in linked]         # never descended (a Windows junction neither)
            entries = files + linked
            out.append(("" if folder == "." else folder, sorted(entries)))
        out.sort()
        return out

    def sha_of(self, rel):
        """The sha256 hex digest of the `svf/`-relative file @p rel, or `None` when the walk listed it but it could
        not be read.

        Only a name the walk indexed is accepted; anything else (an absolute path, a `..`, a file the walk never
        saw) raises `ValueError`. There is no disk fallback, so `sha_of` cannot read outside `svf/` and cannot
        follow a symlink the walk refused.
        """
        if rel not in self._sha:
            raise ValueError("sha_of: %r is not a file the index walked" % (rel,))
        return self._sha[rel]

    def check_face(self, dest, name, data):
        """`("identical", rel)` when @p data is byte-equal to an indexed file, `("clash", "<dest>/<name>")` when
        @p name already exists in @p dest (compared case-insensitively) with other bytes, else `("ok", None)`."""
        rel = self.by_sha.get(hashlib.sha256(data).hexdigest()) if data else None
        if rel is not None:
            return ("identical", rel)
        if dest in self.unlisted or name.upper() in self.names.get(dest, ()):
            return ("clash", dest + "/" + name)
        return ("ok", None)

    def check_text(self, data):
        """The `svf/`-relative path of a file byte-equal to @p data, or `None`; an empty text is never equal to
        anything, so an empty licence is never "already present"."""
        if not data:
            return None
        return self.by_sha.get(hashlib.sha256(data).hexdigest())
