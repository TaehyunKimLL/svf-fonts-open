#!/usr/bin/env python3
"""Detection: a file's format from its magic and size, its metadata, its sizes and DOS raw candidates.

`sniff` tags a head plus a length; `detect_file` turns one file into the font entries (Shared data shapes) the
maker's page shows. The library assumes `maker/` and `tools/` are on sys.path (the entry points set it).
"""

import gzip
import io
import os
import re
import struct
import tempfile
import time
import traceback

import bdfface
import jamoaa
import jamoset
import mkfont
import srcprep
import svf2to3
from PIL import Image, ImageFont
from fontTools.ttLib import TTFont

SAMPLE_TEXT = "다람쥐 헌 쳇바퀴에 타고파 ABC xyz 0123"

# DOS raw fonts are matched by exact byte size alone: the candidate layouts for each size. "none" is an HBIOS 12x24
# English font, not convertible; it is always kept so the owner can see what the file is.
DOS_SIZES = {11520: ["844", "844-ihnm"], 11522: ["844"], 25920: ["844"], 72000: ["844"], 103680: ["844"],
             15584: ["844"], 243900: ["844-hbios24"], 12800: ["1044-san"], 6144: ["621"], 11550: ["kyra-lok"],
             15360: ["dkb-printer-7x2x2", "none"], 34560: ["dkb-printer-7x2x2"], 176000: ["dkb-printer-12x4x4"],
             253440: ["dkb-printer-12x4x4"]}

# A Latin companion (`--eng`) is recognised by its byte size: the 8x16 DOS fonts and the 12x24 ones (HWP `ASCII.PFT`;
# the HBIOS 15,360-byte file is told from a Dokkaebi face by `hbios_eng_like`).
ENG_SIZES = {2048: "8x16", 4096: "8x16", 12288: "12x24", 15360: "12x24"}

# The Dokkaebi printer layouts hold two faces in one file (HANGUL16/24.FNT, HANGUL40/48.FNT).
DKB_LAYOUTS = ("dkb-printer-7x2x2", "dkb-printer-12x4x4")

# A layout's cell px, when it does not depend on the file size. None means "ask the opener": for a given file the px is
# `jamoset.LAYOUTS[name].opener(data).w` (844 is 16/24/40/48 by size; the Dokkaebi printer layouts are 16/24 and 40/48).
LAYOUT_PX = {"844": None, "844-ihnm": 16, "844-hbios24": 24, "1044-san": 16, "621": 16, "kyra-lok": 15,
             "dkb-printer-7x2x2": None, "dkb-printer-12x4x4": None}

_HEAD = 512                     # the magic head `sniff` reads
_MAX_HEAD = 64 * 1024           # a BDF/HBF/PCF's own header data lives in the first 64 KiB (a BDF's before STARTCHAR)
_FACE_CAP = 64                  # never list more faces of one TTC/FON than this
_LICENCE_NAMES = re.compile(r"^(licen[cs]e|ofl|copying)", re.I)

# One gzip level is undone; an inner bigger than this is refused rather than decompressed (the archive member limit).
MAX_DECOMPRESSED = 128 << 20    # 128 MiB

# The coverage a font entry reports: the compatibility jamo U+3131..U+3163 (51 of them) and the 2,350 KS X 1001
# syllables mkfont.py names "ksx1001-hangul".
COMPAT = range(0x3131, 0x3164)
KS2350 = mkfont.NAMED_RANGES["ksx1001-hangul"]()

# A DOS Johab raw font draws every syllable from its pieces, so its coverage is a fact of the format, not a reading.
DOS_COVERAGE = {"ascii": 0, "ks2350": 2350, "all": 11172, "compat": 51}

# A johab BDF's ENCODING values are johab-1 glyph indices, not KS X 1001 codes, and the face draws every syllable
# from jamo: its coverage is the composed one too (reading the indices as code points gives garbage).
JOHAB_COVERAGE = {"ascii": 0, "ks2350": 2350, "all": 11172, "compat": 51}

# The whole coverage pass of one scan has this long; past it the rest of the entries get coverage None. A bitmap
# face costs about 0.4 s whatever its size, so an unbounded batch of small bitmaps could take many minutes.
SCAN_COVERAGE_BUDGET_S = 120

# mkfont.py draws this noncharacter to get the `.notdef` picture the bitmap test compares against.
NOTDEF_CHAR = "\U0010FFFF"


class TooLarge(Exception):
    """A gzip whose decompressed bytes would pass MAX_DECOMPRESSED."""


def _too_large():
    return "too large (> %d MiB decompressed)" % (MAX_DECOMPRESSED >> 20)


# ---- sniffing --------------------------------------------------------------------------------------------------

# SVFN header version (bytes 4..5) -> format tag: v3 is the maker's own format, v2 converts, v1 is refused
SVF_TAGS = {jamoset.VERSION: "svf", svf2to3.V2_VERSION: "svf2", 1: "svf1"}


def sniff(data, size=None):
    """A `format` tag from the magic in @p data (which may be only the first 512 bytes) and the file @p size."""
    if size is None:
        size = len(data)
    if data[:2] == b"\x1f\x8b":
        return "gzip"
    if data[:4] in (b"\x00\x01\x00\x00", b"true"):
        return "ttf"
    if data[:4] == b"OTTO":
        return "otf"
    if data[:4] == b"ttcf":
        return "ttc"
    if data.startswith(b"STARTFONT"):
        return "bdf"
    if data[:4] == b"\x01fcp":
        return "pcf"
    if data.startswith(b"HBF_START_FONT"):
        return "hbf"
    if data[:4] == b"SVFN":
        # v3 is the format the maker writes ("svf"); a v2 face is converted (svf2to3.py), a v1 one is refused
        version = struct.unpack_from("<H", data, 4)[0] if len(data) >= 6 else 1
        return SVF_TAGS.get(version, "unknown")
    if data[:4] == b"PK\x03\x04" or data[257:262] == b"ustar" or data[:6] == b"\xfd7zXZ\x00":
        return "archive"
    if data[:2] == b"MZ":
        return "fon"
    if len(data) >= 66 and struct.unpack_from("<H", data, 0)[0] in (0x200, 0x300) \
            and all(0x20 <= b <= 0x7E or b == 0 for b in data[6:66]):
        return "fnt"
    if size in DOS_SIZES:
        return "dos-raw"
    if size in (2048, 4096, 12288):
        return "eng"
    if _mac_head(data, size):
        return "mac-rsrc"
    return "unknown"


def _mac_head(data, size):
    """True when @p data (the first 512 bytes of a file of @p size bytes) opens a Mac resource-fork container: an
    AppleDouble head, a MacBinary head whose forks fit the file, or a raw fork (.dfont) whose header and map account
    for the whole file."""
    if data[:4] == b"\x00\x05\x16\x07":
        return True
    if len(data) >= 128 and data[0] == 0 and 1 <= data[1] <= 63 and data[74] == 0 and data[82] == 0:
        dlen, rlen = struct.unpack_from(">II", data, 83)
        if rlen and 128 + ((dlen + 127) // 128) * 128 + rlen <= size:
            return True
    if len(data) >= 16:
        data_off, map_off, data_len, map_len = struct.unpack_from(">IIII", data, 0)
        if data_off >= 16 and data_off + data_len <= map_off and map_len >= 30 and map_off + map_len == size:
            return True
    return False


def gunzip_head(path):
    """The first 512 decompressed bytes of @p path and its decompressed length, in 1 MB chunks up to the cap."""
    with gzip.open(path, "rb") as f:
        head = f.read(_HEAD)
        size = len(head)
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_DECOMPRESSED:
                raise TooLarge(_too_large())
    return head, size


# ---- text and licence classification ---------------------------------------------------------------------------

def is_licence_name(name):
    """LICENSE*, LICENCE*, OFL* or COPYING*, case-insensitively."""
    return bool(_LICENCE_NAMES.match(name))


def is_licence_text(path):
    """A `.txt` whose first 4 KB mention `license`/`licence` (decoded once). A file that cannot be read is not one."""
    if not path.lower().endswith(".txt"):
        return False
    try:
        with open(path, "rb") as f:
            head = f.read(4096).decode("utf-8", "replace").lower()
    except OSError:
        return False
    return "license" in head or "licence" in head


def classify_txt(path, rel):
    """A `.txt` file is a licence text when its name or its content claims it, else a character list."""
    return "licence" if is_licence_name(os.path.basename(rel)) or is_licence_text(path) else "list"


def _stem(rel):
    """A file's stem: one trailing `.gz` is dropped first, so `iso.bdf.gz` is `iso`."""
    name = os.path.basename(rel)
    if name.lower().endswith(".gz"):
        name = name[:-3]
    return os.path.splitext(name)[0]


# ---- metadata --------------------------------------------------------------------------------------------------

def _name_record(name_table, ids):
    """The first non-empty string for @p ids in order, preferring Windows (3), then Unicode (0), then Mac (1)."""
    for name_id in ids:
        cands = []
        for rec in name_table.names:
            if rec.nameID != name_id:
                continue
            try:
                s = (rec.toUnicode() or "").strip()
            except Exception:
                continue
            if s:
                cands.append((rec.platformID, s))
        for pref in (3, 0, 1):
            for plat, s in cands:
                if plat == pref:
                    return s
        if cands:
            return cands[0][1]
    return ""


def _names_of(font):
    """(family, style, version) of an open font: name IDs 16/17 else 1/2, version ID 5; "" when absent."""
    try:
        table = font["name"]
    except Exception:
        table = None
    family = _name_record(table, (16, 1)) if table is not None else ""
    style = _name_record(table, (17, 2)) if table is not None else ""
    version = _name_record(table, (5,)) if table is not None else ""
    return family.strip(), style.strip(), version.strip()


def read_name(path, face_index=0, data=None):
    """(family, style, version): name IDs 16/17 else 1/2, version ID 5; family falls back to the file stem.

    A file fontTools cannot open raises (the caller turns it into an `unreadable` entry); a font whose name table
    lacks the IDs, or holds only empty strings, falls back to the stem and "". @p data is the decompressed bytes of a
    non-PCF `.gz` source (fontTools is then given those, not the compressed path).
    """
    handle = open(path, "rb") if data is None else io.BytesIO(data)
    try:
        f = TTFont(handle, fontNumber=face_index, lazy=True)
        try:
            family, style, version = _names_of(f)
        finally:
            f.close()
    finally:
        handle.close()
    if not family:
        family = _stem(path)
    return family, style, version


def _open_font(path, size, index=0, data=None):
    """Pillow's font at @p size: FreeType opens @p path, or @p data (a non-PCF `.gz` source, decompressed)."""
    return ImageFont.truetype(io.BytesIO(data) if data is not None else path, size, index=index)


def bitmap_strikes(path, hint=None, data=None):
    """The sizes in 4..96 at which the font opens; @p hint (its header's own size) alone when that verifies."""
    if hint is not None and 4 <= hint <= 96:
        try:
            _open_font(path, hint, data=data)
            return [hint]
        except Exception:
            pass
    out = []
    for s in range(4, 97):
        try:
            _open_font(path, s, data=data)
        except Exception:
            continue
        out.append(s)
    return out


def hbios_eng_like(data):
    """True for an HBIOS 12x24 English font: 256 glyphs of 60 bytes (16x30, two bytes a row) whose top three and bottom
    three rows are blank and whose second byte of every row has its low nibble clear (a 12 px cell), with ink in `A`.

    The Dokkaebi 7x2x2 opener accepts any 15,360 bytes, so this is the only thing that tells the two apart. A Dokkaebi
    face with ink in a margin row stays `dos-raw`; the all-zero file has no ink in `A` and stays as it was.
    """
    if len(data) != 15360:
        return False
    for g in range(256):
        glyph = data[g * 60:(g + 1) * 60]
        if any(glyph[0:6]) or any(glyph[54:60]):
            return False
        if any(glyph[row * 2 + 1] & 0x0F for row in range(30)):
            return False
    return any(data[0x41 * 60:0x42 * 60])


def dos_candidates(data):
    """DOS_SIZES[len(data)] filtered by the layout opener not raising jamoset.SourceError ("none" always kept)."""
    out = []
    for name in DOS_SIZES.get(len(data), []):
        if name == "none":
            out.append(name)
            continue
        try:
            jamoset.LAYOUTS[name].opener(data)
        except jamoset.SourceError:
            continue
        out.append(name)
    return out


def layout_px(name, data, face=0):
    """A layout's cell px for @p data (None for "none", which has no layout)."""
    if name == "none":
        return None
    px = LAYOUT_PX.get(name)
    if px is not None:
        return px
    return jamoset.LAYOUTS[name].opener(data, face).w


# ---- the file --------------------------------------------------------------------------------------------------

def detect_file(abs_path, rel):
    """The font entries of one file (Shared data shapes without id/licences/companions; coverage None, jamo "none").

    One entry per face; every file yields at least one entry. Never raises: any exception becomes one `unreadable`
    entry carrying the traceback, and a gzip past MAX_DECOMPRESSED one labelled "too large".
    """
    try:
        return _detect_file(abs_path, rel)
    except TooLarge as e:
        return [_entry(rel, 0, "unreadable", str(e), "other", family=_stem(rel), error=str(e))]
    except Exception as e:
        return [_entry(rel, 0, "unreadable", "unreadable: %s: %s" % (type(e).__name__, e), "other",
                       family=_stem(rel), error=traceback.format_exc())]


def _entry(rel, face_index, fmt, label, source_kind, family="", style="", version="", sizes=None, sizes_fixed=False,
           dos=None, bdf=None, svf=None, error=None, gz=False, prep=None, variable=None, strikes=None, eng=None,
           dos_bytes=None):
    e = {"path": rel, "face_index": face_index, "format": fmt, "label": label, "source_kind": source_kind,
         "family": family, "style": style, "version": version, "sizes": sizes or [], "sizes_fixed": sizes_fixed,
         "coverage": None, "jamo": "none", "dos": dos, "bdf": bdf, "svf": svf, "error": error}
    if gz:                            # a non-PCF .gz source: decompress it before any tool or Pillow reads it
        e["gzip"] = True
    if prep:                          # the source conversions the file needs before any tool can read it
        e["prep"] = prep
    if variable is not None:
        e["variable"] = variable
    if strikes:
        e["strikes"] = strikes
    if eng:
        e["eng"] = eng
    if dos_bytes:
        e["dos_bytes"] = dos_bytes
    return e


def _sfnt_facts(font):
    """{"variable", "strikes", "mac_cmap", "outlines"} of an open sfnt; a table that cannot be read counts as absent."""
    def safe(fn, default):
        try:
            return fn(font)
        except Exception:
            return default
    return {"variable": safe(srcprep.variable_info, None), "strikes": safe(srcprep.embedded_strikes, []),
            "mac_cmap": safe(srcprep.mac_cmap_only, False), "outlines": srcprep.has_outlines(font)}


def _axis_label(a):
    return "%s %g..%g" % (a["tag"], a["min"], a["max"])


def _sfnt_entry(rel, face_index, fmt, label, font, prep, gz):
    """The entry of one open sfnt face: ttf, otf, a TTC face or a Mac `sfnt` resource.

    Outlines make an `outline` entry, embedded strikes alone a `bitmap` one at those sizes; @p prep is the list of
    source conversions it needs (the Mac cmap one is added here); the label says what the file carries.
    """
    facts = _sfnt_facts(font)
    family, style, version = _names_of(font)
    family = family or _stem(rel)
    prep = list(prep) + ([{"op": "mac-cmap"}] if facts["mac_cmap"] else [])
    strikes = facts["strikes"]
    suffix = ""
    if facts["variable"] is not None:
        suffix += "; variable (%s)" % ", ".join(_axis_label(a) for a in facts["variable"]["axes"])
    if strikes:
        suffix += "; bitmap strikes %s" % ", ".join(str(n) for n in strikes)
    if facts["mac_cmap"]:
        suffix += "; Mac Korean cmap"
    kw = dict(prep=prep, variable=facts["variable"], strikes=strikes, gz=gz)
    if facts["outlines"]:
        return _entry(rel, face_index, fmt, label + suffix, "outline", family, style, version, [16], False, **kw)
    if strikes:
        return _entry(rel, face_index, fmt, _bitmap_only(label) + suffix,
                      "bitmap", family, style, version, list(strikes), True, **kw)
    return _entry(rel, face_index, fmt, label + "; no outlines, no bitmap strikes" + suffix, "other", family, style,
                  version, **kw)


def _bitmap_only(label):
    """"TTF" -> "TTF bitmap-only"; a longer label ("TTC face 1") gets the word at its end."""
    return label + " bitmap-only"


def _open_sfnt_entry(abs_path, rel, face_index, fmt, label, data, prep, gz):
    """`_sfnt_entry` of face @p face_index of the file (or of @p data, a `.gz` source's decompressed bytes)."""
    handle = open(abs_path, "rb") if data is None else io.BytesIO(data)
    try:
        font = TTFont(handle, fontNumber=face_index, lazy=True)
        try:
            return _sfnt_entry(rel, face_index, fmt, label, font, prep, gz)
        finally:
            font.close()
    finally:
        handle.close()


def _read_bytes(path, gz=False):
    """The whole file (decompressed when @p gz), refusing a gzip that passes MAX_DECOMPRESSED.

    A gzip is inflated in 1 MiB chunks and the chunks joined: one `read(MAX_DECOMPRESSED + 1)` would make the reader
    pre-allocate a buffer of that size for every file, whatever the file's real length.
    """
    if not gz:
        with open(path, "rb") as f:
            return f.read()
    parts = []
    size = 0
    with gzip.open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_DECOMPRESSED:
                raise TooLarge(_too_large())
            parts.append(chunk)
    return parts[0] if len(parts) == 1 else b"".join(parts)


def _head_bytes(path, gz=False, cut=None):
    """At most _MAX_HEAD bytes of a file (decompressed when @p gz), cut at the first @p cut; never the whole file."""
    if gz:
        with gzip.open(path, "rb") as f:
            data = f.read(_MAX_HEAD)
    else:
        with open(path, "rb") as f:
            data = f.read(_MAX_HEAD)
    if cut is not None:
        i = data.find(cut)
        if i >= 0:
            data = data[:i]
    return data


def _detect_file(abs_path, rel):
    base = os.path.basename(rel)
    if base.lower().endswith(".txt"):
        fmt = classify_txt(abs_path, rel)
        return [_entry(rel, 0, fmt, "licence text" if fmt == "licence" else "list file", "other", family=_stem(rel))]
    size = os.path.getsize(abs_path)
    with open(abs_path, "rb") as f:
        head = f.read(_HEAD)
    fmt = sniff(head, size)
    gz = fmt == "gzip"
    if gz:
        head, size = gunzip_head(abs_path)
        fmt = sniff(head, size)
    zipped = gz and fmt != "pcf"      # PCF stays compressed: FreeType reads `.pcf.gz` itself

    if fmt in ("ttf", "otf"):
        data = _read_bytes(abs_path, True) if gz else None
        return [_open_sfnt_entry(abs_path, rel, 0, fmt, "TTF" if fmt == "ttf" else "OTF", data, [], zipped)]

    if fmt == "ttc":
        return _ttc_entries(abs_path, rel, gz, zipped)

    if fmt == "mac-rsrc":
        return _mac_entries(abs_path, rel, gz, zipped)

    if fmt == "bdf":
        text = _head_bytes(abs_path, gz, cut=b"STARTCHAR").decode("latin-1")
        reg, enc = _bdf_charset(text)
        box = _bdf_box(text)
        family, style = _bdf_names(text)
        family = family or _stem(rel)
        bdf = {"registry": ("%s-%s" % (reg, enc)) if enc else reg, "box": box}
        kind = _bdf_kind(reg)
        label = "BDF (%s)" % reg
        if kind == "other":
            return [_entry(rel, 0, "bdf", label + ": not convertible", "other", family, style, bdf=bdf, gz=zipped)]
        if kind == "bdf-iso10646":
            data = _read_bytes(abs_path, True) if gz else None
            sizes = bitmap_strikes(abs_path, hint=_bdf_pixel_hint(text), data=data)
            if not sizes:
                label += "; no openable size"
        else:
            sizes = [box[1]] if box else []
        return [_entry(rel, 0, "bdf", label, kind, family, style, bdf=bdf, sizes=sizes, sizes_fixed=True, gz=zipped)]

    if fmt == "hbf":
        text = _head_bytes(abs_path, gz, cut=b"STARTCHAR").decode("latin-1")
        box = _hbf_box(text)
        missing = _hbf_missing(text)
        if missing:                   # bdfface.read_hbf would refuse this file: it is not a usable companion
            return [_entry(rel, 0, "hbf", "HBF: no %s" % missing, "other",
                           _hbf_family(text) or _stem(rel), "", gz=zipped)]
        return [_entry(rel, 0, "hbf", "HBF", "hbf", _hbf_family(text) or _stem(rel), "",
                       sizes=[box[1]] if box else [], sizes_fixed=True, gz=zipped)]

    if fmt == "pcf":
        ksc = _ksc_pcf_entry(abs_path, rel, gz)
        if ksc is not None:
            return [ksc]
        sizes = bitmap_strikes(abs_path, hint=_pcf_pixel_hint(_head_bytes(abs_path, gz)))
        family, style = _pillow_name(abs_path, sizes[0]) if sizes else ("", "")
        label = "PCF" + ("" if sizes else "; no openable size")
        return [_entry(rel, 0, "pcf", label, "bitmap", family or _stem(rel), style, sizes=sizes, sizes_fixed=True)]

    if fmt == "fnt":
        data = _read_bytes(abs_path, True) if gz else None
        sizes = bitmap_strikes(abs_path, data=data)
        family, style = _pillow_name(abs_path, sizes[0], data=data) if sizes else ("", "")
        label = "Windows FNT" + ("" if sizes else "; no openable size")
        return [_entry(rel, 0, "fnt", label, "bitmap", family or _stem(rel), style, sizes=sizes, sizes_fixed=True,
                       gz=zipped)]

    if fmt == "fon":
        data = _read_bytes(abs_path, True) if gz else None
        faces = _fon_faces(abs_path, data)
        if not faces:                 # an MZ that FreeType cannot open still gets an entry: it must not vanish
            return [_entry(rel, 0, "fon", "Windows FON; no openable face", "other", family=_stem(rel), gz=zipped)]
        out = []
        for i in faces:
            if i == 0:
                sizes = bitmap_strikes(abs_path, data=data)
                family, style = _pillow_name(abs_path, sizes[0], data=data) if sizes else ("", "")
                label = "Windows FON face 0" + ("" if sizes else "; no openable size")
                out.append(_entry(rel, i, "fon", label, "bitmap", family or _stem(rel), style, sizes=sizes,
                                  sizes_fixed=True, gz=zipped))
            else:
                out.append(_entry(rel, i, "fon", "face index %d: not convertible in v1" % i, "other",
                                  family=_stem(rel), gz=zipped))
        return out

    if fmt == "dos-raw":
        data = _read_bytes(abs_path, gz)
        if hbios_eng_like(data):      # a 15,360 byte HBIOS English font, not a Dokkaebi face: a companion only
            return [_entry(rel, 0, "eng", "HBIOS 12x24 English (--eng)", "other", family=_stem(rel),
                           eng={"bytes": len(data), "cell": ENG_SIZES[len(data)]}, gz=zipped)]
        cands = dos_candidates(data)
        real = [c for c in cands if c != "none"]
        if not real:                  # no layout survives: the entry must not claim a route it has not got
            if not cands:
                return [_entry(rel, 0, "unknown", "unknown (%d bytes; no DOS layout fits)" % len(data), "other",
                               family=_stem(rel), gz=zipped)]
            return [_entry(rel, 0, "dos-raw", "HBIOS 12x24 English font, not convertible", "other",
                           family=_stem(rel), dos={"candidates": cands, "faces": [0]}, gz=zipped)]
        first = real[0]
        faces = [0, 1] if first in DKB_LAYOUTS else [0]
        label = "probable DOS Johab (%s)" % ", ".join(cands)
        out = []
        for i in faces:
            px = layout_px(first, data, i)
            out.append(_entry(rel, i, "dos-raw", label, "dos-raw", family=_stem(rel),
                              sizes=[px] if px is not None else [], sizes_fixed=True,
                              dos={"candidates": cands, "faces": faces}, gz=zipped, dos_bytes=len(data)))
        return out

    if fmt in ("svf", "svf2", "svf1"):
        if fmt == "svf1":
            return [_entry(rel, 0, "svf1", "v1: convert from the original font", "other", family=_stem(rel))]
        f = read_svf(_read_bytes(abs_path, gz))
        kind = "svf-jamo" if usable_jset(f) is not None else "svf-precomposed"
        # the JSET block's version (1 | 2 | 3, 3 = a JMAP), None for a face without a usable set: the maker keeps it unless asked
        jv = svf2to3.jset_version(f.jset) if kind == "svf-jamo" else None
        # a version 3 block's encoding ("dense" | "sparse" | "list"), None for set tables or no usable block
        jm = jmap_mode(f.jset) if jv == jamoset.JMAP_VERSION else None
        svf = {"version": f.version, "flags": f.flags, "bpp": f.bpp, "cell": [f.cell_w, f.cell_h], "ascent": f.ascent,
               "glyphs": f.count, "jset_version": jv, "jmap_mode": jm}
        label = "SVF v3" if f.version == jamoset.VERSION else "SVF v2: converted to v3"
        return [_entry(rel, 0, fmt, label, kind, family=_stem(rel), sizes=[f.cell_h], sizes_fixed=True, svf=svf,
                       gz=zipped)]

    if fmt == "eng":
        cell = ENG_SIZES[size]
        label = "Latin companion (--eng%s)" % (", 12x24" if cell == "12x24" else "")
        return [_entry(rel, 0, "eng", label, "other", family=_stem(rel), eng={"bytes": size, "cell": cell},
                       gz=zipped)]

    if fmt == "archive":
        return [_entry(rel, 0, "archive", "archive", "other", family=_stem(rel))]

    return [_entry(rel, 0, "unknown", "unknown (%s)" % head[:8].hex(), "other", family=_stem(rel), gz=zipped)]


def _ttc_entries(abs_path, rel, gz, zipped):
    """One entry per TTC face, capped at _FACE_CAP; the count is the header's, so no face is built to count."""
    data = _read_bytes(abs_path, True) if gz else None
    if data is not None:
        head = data[:12]
    else:
        with open(abs_path, "rb") as f:
            head = f.read(12)
    total = struct.unpack_from(">I", head, 8)[0] if len(head) >= 12 else 1   # ttcf + version, then numFonts
    faces = min(total, _FACE_CAP)
    if not faces:                     # a header claiming no faces still gets one entry: the file must not vanish
        faces = 1
    out = []
    for i in range(faces):
        label = "TTC face %d" % i
        more = "; more faces not listed" if i == faces - 1 and total > faces else ""
        prep = [{"op": "ttc-face", "index": i}] if i else []
        if i == 0:
            e = _open_sfnt_entry(abs_path, rel, 0, "ttc", label, data, prep, zipped)
            if e.get("prep"):             # a further op (a Mac cmap) must read the face, not the whole collection
                e["prep"] = [{"op": "ttc-face", "index": 0}] + e["prep"]
        else:
            try:
                e = _open_sfnt_entry(abs_path, rel, i, "ttc", label, data, prep, zipped)
            except Exception as ex:           # a face that does not open still gets its entry
                e = _entry(rel, i, "ttc", "%s: unreadable (%s)" % (label, type(ex).__name__), "other",
                           family=_stem(rel), gz=zipped)
        e["label"] += more
        out.append(e)
    return out


def _ksc_pcf_entry(abs_path, rel, gz):
    """The entry of a PCF whose charset is KS X 1001 or johab (a source for bdfface.py / hanterm), else None.

    The conversion to BDF is srcprep's (`pcf-bdf` prep op); the box is the converted BDF's FONTBOUNDINGBOX. Any other
    PCF, and one the reader cannot read, keeps the `bitmap` path (FreeType opens it).
    """
    try:
        data = _read_bytes(abs_path, gz)
        props = srcprep.pcf_properties(data)
        reg = str(props.get("CHARSET_REGISTRY", "")).strip().lower()
        enc = str(props.get("CHARSET_ENCODING", "")).strip().lower()
        kind = _bdf_kind(reg)
        if kind not in ("bdf-ksc5601", "bdf-johab"):
            return None
        box = srcprep.pcf_box(data)
    except Exception:                 # unreadable here: FreeType gets to try it as a bitmap font
        return None
    family = str(props.get("FAMILY_NAME", "")).strip() or _stem(rel)
    bdf = {"registry": ("%s-%s" % (reg, enc)) if enc else reg, "box": box}
    return _entry(rel, 0, "pcf", "PCF (%s)" % reg, kind, family, sizes=[box[1]] if box else [], sizes_fixed=True,
                  bdf=bdf, prep=[{"op": "pcf-bdf"}])


MAC_BITMAP_TYPES = (b"NFNT", b"FONT", b"fbit")


def _mac_entries(abs_path, rel, gz, zipped):
    """One entry per `sfnt` resource of a Mac container (capped at _FACE_CAP); a container with only bitmap fonts is one
    `other` entry and a corrupt resource map one `unknown` entry: the file never vanishes."""
    data = _read_bytes(abs_path, gz)
    try:
        container, res = srcprep.mac_resources(data)
    except srcprep.PrepError as e:
        return [_entry(rel, 0, "unknown", "unknown (Mac resource fork: %s)" % e, "other", family=_stem(rel),
                       gz=zipped)]
    all_sfnts = [(rid, body) for rtype, rid, _name, body in res if rtype == b"sfnt"]
    sfnts = all_sfnts[:_FACE_CAP]
    if not sfnts:
        if any(rtype in MAC_BITMAP_TYPES for rtype, _i, _n, _b in res):
            return [_entry(rel, 0, "mac-rsrc", "Mac bitmap font (NFNT/fbit): not converted here (local-only mode)",
                           "other", family=_stem(rel), gz=zipped)]
        return [_entry(rel, 0, "mac-rsrc", "%s: no sfnt or bitmap font resource" % container, "other",
                       family=_stem(rel), gz=zipped)]
    out = []
    for n, (rid, body) in enumerate(sfnts):
        label = "%s: sfnt %d" % (container, rid)
        try:
            font = TTFont(io.BytesIO(body), lazy=True)
            try:
                out.append(_sfnt_entry(rel, n, "mac-rsrc", label, font, [{"op": "rsrc-sfnt", "id": rid}], zipped))
            finally:
                font.close()
        except Exception as e:            # an sfnt resource that is not a font still gets its entry
            out.append(_entry(rel, n, "mac-rsrc", "%s unreadable (%s)" % (label, type(e).__name__), "other",
                              family=_stem(rel), gz=zipped))
    if len(all_sfnts) > len(sfnts):
        out[-1]["label"] += "; more faces not listed"
    return out


# ---- BDF, HBF, PCF, Pillow helpers -----------------------------------------------------------------------------

def _prop(text, name):
    """A BDF property's value: the text after `name`, without quotes."""
    m = re.search(r"\b%s\s+\"?([^\"\n]*)" % name, text)
    return m.group(1).strip() if m else ""


def _bdf_charset(text):
    """(registry, encoding), lower-cased: the CHARSET_* properties, else the FONT name's last two fields."""
    reg, enc = _prop(text, "CHARSET_REGISTRY"), _prop(text, "CHARSET_ENCODING")
    if not reg:
        m = re.search(r"^FONT\s+(\S+)", text, re.M)
        if m:
            parts = m.group(1).split("-")
            if len(parts) >= 3:
                reg, enc = parts[-2], enc or parts[-1]
    return reg.strip().lower(), enc.strip().lower()


def _bdf_box(text):
    m = re.search(r"FONTBOUNDINGBOX\s+(-?\d+)\s+(-?\d+)", text)
    return [int(m.group(1)), int(m.group(2))] if m else None


def _bdf_names(text):
    return _prop(text, "FAMILY_NAME"), _prop(text, "WEIGHT_NAME")


def _bdf_kind(reg):
    if reg.startswith("iso10646"):
        return "bdf-iso10646"
    if reg.startswith("iso8859"):
        return "bdf-iso8859"
    if "johab" in reg or "hanterm" in reg:
        return "bdf-johab"
    if "ksc" in reg or "ksx" in reg:
        return "bdf-ksc5601"
    return "other"


def _bdf_pixel_hint(text):
    """The px FreeType will open this BDF at: PIXEL_SIZE, else POINT_SIZE scaled by the y resolution."""
    m = re.search(r"PIXEL_SIZE\s+(\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"^SIZE\s+(\d+)\s+(\d+)\s+(\d+)", text, re.M)
    if m:
        return round(int(m.group(1)) * int(m.group(3)) / 72)
    return None


def _hbf_box(text):
    """HBF_BITMAP_BOUNDING_BOX (w, h): what bdfface.read_hbf reads. No FONTBOUNDINGBOX fallback."""
    m = re.search(r"HBF_BITMAP_BOUNDING_BOX\s+(-?\d+)\s+(-?\d+)", text)
    return [int(m.group(1)), int(m.group(2))] if m else None


def _hbf_missing(text):
    """The HBF field that would make bdfface.read_hbf raise, or "" when it has both."""
    if _hbf_box(text) is None:
        return "HBF_BITMAP_BOUNDING_BOX"
    if not re.search(r"FONT_ASCENT\s+(\d+)", text):
        return "FONT_ASCENT"
    return ""


def _hbf_family(text):
    m = re.search(r'HBF_FAMILY\s+"?([^"\n]*)', text)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = re.search(r"^FONT\s+(\S+)", text, re.M)
    if m:
        parts = m.group(1).strip("-").split("-")
        return parts[1] if len(parts) > 1 else parts[0]
    return ""


# The bitmap file each HBF_CODE_RANGE line names (bdfface.py's own pattern, without the trailing offset).
_HBF_RANGE = re.compile(r"HBF_CODE_RANGE\s+0x[0-9A-Fa-f]+-0x[0-9A-Fa-f]+\s+(\S+)\s+\d+")


def _plain_name(name):
    """True for a bare file name: no separator, not `..`, not absolute."""
    return bool(name) and name not in (".", "..") and "/" not in name and not os.path.isabs(name)


def hbf_refusal(path):
    """The reason `bdfface.read_hbf` must not read @p path's bitmaps, or "" when it is safe to call it.

    `read_hbf` joins each `HBF_CODE_RANGE` name onto the HBF's own folder and reads it whole, with no cap (and it
    decompresses a `.gz` bin with no cap either), so an uploaded HBF could name `../../etc/shadow` or `/dev/zero` and
    make the server read it. Every name must be plain, resolve to a regular, non-symlink file in the HBF's folder,
    and be at most MAX_DECOMPRESSED; a `.gz` bin gets its own reason ("`.gz bitmap not supported`") because its
    decompressed size is not known without reading it. An HBF that names nothing at all is safe (it yields no
    glyphs). The reason is the text after "HBF: " in the entry's label.
    """
    try:
        with open(path, "rb") as f:
            text = f.read(MAX_DECOMPRESSED + 1).decode("latin-1")
    except OSError:
        return "unsafe bitmap reference"
    if len(text) > MAX_DECOMPRESSED:
        return "unsafe bitmap reference"
    folder = os.path.dirname(os.path.abspath(path))
    for m in _HBF_RANGE.finditer(text):
        name = m.group(1)
        if not _plain_name(name):
            return "unsafe bitmap reference"
        if name.lower().endswith(".gz"):
            return ".gz bitmap not supported"
        p = os.path.join(folder, name)
        if os.path.islink(p) or not os.path.isfile(p):
            return "unsafe bitmap reference"
        try:
            if os.path.getsize(p) > MAX_DECOMPRESSED:
                return "unsafe bitmap reference"
        except OSError:
            return "unsafe bitmap reference"
    return ""


def hbf_refs_safe(path):
    """True when `hbf_refusal` finds no reason to refuse the HBF at @p path (see it for the rules)."""
    return hbf_refusal(path) == ""


def _pcf_pixel_hint(data):
    """The PIXEL_SIZE a PCF's properties table names (its own strike), or None.

    The table sits in the file's TOC at type 1: a format word, a count, that many 9 byte records and then the inline
    strings the records' offsets point into. The hint is only trusted after FreeType opens the font at it.
    """
    if data[:4] != b"\x01fcp" or len(data) < 16:
        return None
    props = None
    for i in range(min(struct.unpack_from("<I", data, 4)[0], 64)):
        typ, _fmt, _size, off = struct.unpack_from("<IIII", data, 8 + 16 * i)
        if typ == 1:
            props = off
            break
    if props is None or props + 8 > len(data):
        return None
    endian = ">" if struct.unpack_from("<I", data, props)[0] & 0x4 else "<"   # PCF_BYTE_MASK set: MSB first
    nprops = struct.unpack_from(endian + "I", data, props + 4)[0]
    records = props + 8
    if not 0 < nprops <= 1024 or records + 9 * nprops > len(data):
        return None
    base = ((records + 9 * nprops + 3) & ~3) + 4      # pad to 4 bytes, then the u32 string_size: the strings start here

    def text(off):
        start = base + off
        if start >= len(data):
            return ""
        end = data.find(b"\0", start)
        return data[start:end if end >= 0 else len(data)].decode("latin-1")

    for i in range(nprops):
        q = records + 9 * i
        name = text(struct.unpack_from(endian + "I", data, q)[0])
        if name == "PIXEL_SIZE" and not data[q + 4]:
            return struct.unpack_from(endian + "I", data, q + 5)[0]
    return None


def _pillow_name(path, size, index=0, data=None):
    """The face's (family, style) from the one open at @p size (no re-scan), or ("", "") when it does not open."""
    try:
        font = _open_font(path, size, index, data)
    except Exception:
        return "", ""
    try:
        family, style = font.getname()
    except Exception:
        return "", ""
    return (family or "").strip(), (style or "").strip()


def _pillow_opens(path, index=0, data=None):
    for s in range(4, 97):
        try:
            _open_font(path, s, index, data)
            return True
        except Exception:
            continue
    return False


def _fon_faces(path, data=None):
    """Pillow's `index` 0.. until it raises, capped at _FACE_CAP: the faces of a Windows FON."""
    faces = []
    while len(faces) < _FACE_CAP and _pillow_opens(path, len(faces), data):
        faces.append(len(faces))
    return faces


# ---- coverage --------------------------------------------------------------------------------------------------

def coverage_of(has):
    """{"ascii", "ks2350", "all", "compat"} counts of the code points @p has accepts.

    ASCII is 0x20..0x7E, `ks2350` the KS X 1001 syllables, `all` the 11,172 modern syllables and `compat` the
    compatibility jamo U+3131..U+3163.
    """
    return {"ascii": sum(1 for cp in range(0x20, 0x7F) if has(cp)),
            "ks2350": sum(1 for cp in KS2350 if has(cp)),
            "all": sum(1 for cp in range(0xAC00, 0xD7A4) if has(cp)),
            "compat": sum(1 for cp in COMPAT if has(cp))}


def coverage_outline(path, face_index=0, data=None):
    """An outline face's coverage by cmap membership (what the file claims to draw).

    @p data is a `.gz` source's decompressed bytes: the face is then opened from those, not from the compressed path.
    """
    face = jamoaa.OutlineFace(io.BytesIO(data) if data is not None else path, 48, font_number=face_index)
    try:
        cmap = face.cmap
        return coverage_of(lambda cp: cp in cmap)
    finally:
        face.font.close()


def coverage_cmap(path, face_index=0, data=None):
    """An sfnt face's coverage by cmap membership, for a face that has no outlines (a bitmap-only sfnt: Pillow would
    have to open it at every size and draw every glyph). @p data is the face's bytes when not read from @p path."""
    handle = open(path, "rb") if data is None else io.BytesIO(data)
    try:
        font = TTFont(handle, fontNumber=face_index, lazy=True)
        try:
            cmap = font.getBestCmap() or {}
        finally:
            font.close()
    finally:
        handle.close()
    return coverage_of(lambda cp: cp in cmap)


def _bitmap_cell(font):
    """The (cell_w, cell_h, ascent) the picture test draws in: the face's strike (size x size) and its ascent."""
    size = max(1, int(getattr(font, "size", 0) or 0))
    try:
        ascent = int(font.getmetrics()[0])
    except Exception:
        ascent = size
    return size, size, ascent


def _bitmap_image(font, ch):
    """A cell-sized 1 bpp image of @p ch, its ink placed at the glyph's own offset (as mkfont.render draws it).

    Pillow 10 returns the mask as an ImagingCore rather than an Image, so it is wrapped from its bytes and
    thresholded the way mkfont.py thresholds a 1 bpp render. The tight mask is pasted where `font.getbbox(ch,
    anchor="ls")` puts the glyph in the cell, not at (0, 0): two glyphs whose ink has the same shape at different
    offsets (a box-shaped `ㅁ` against a box `.notdef`) must not compare equal.
    """
    cell_w, cell_h, ascent = _bitmap_cell(font)
    img = Image.new("1", (cell_w, cell_h), 0)
    try:
        core = font.getmask(ch, mode="1")
        mask = Image.frombytes(core.mode, core.size, bytes(core)).convert("L")
        mask = mask.point(lambda v: 255 if v >= 128 else 0).convert("1", dither=Image.Dither.NONE)
    except Exception:
        return img
    x = y = 0
    try:
        bbox = font.getbbox(ch, anchor="ls")
    except (ValueError, OSError):
        bbox = None
    if bbox:
        left, top, right, bottom = bbox
        dx = -min(0, left)
        dy = ascent - min(0, top + ascent)
        if right + dx > cell_w:               # the ink would overflow the cell: pull it back left
            dx -= (right + dx) - cell_w
            dx = max(dx, -left)
        x, y = dx + left, dy + top
    if mask.width and mask.height:
        img.paste(mask, (x, y))
    return img


def notdef_absent(font, ch, notdef_bytes):
    """True when @p ch's cell image has no ink, or is the `.notdef` image (drawn for NOTDEF_CHAR).

    Pillow has no cmap question to ask, so a glyph the font has not got is the one it draws as `.notdef` - the same
    picture test `mkfont.py` uses to leave a character out.
    """
    img = _bitmap_image(font, ch)
    return img.getbbox() is None or img.tobytes() == notdef_bytes


def coverage_bitmap(path, size):
    """A bitmap face's coverage at @p size by the picture test: `.notdef` and blank glyphs are absent.

    A gzip-wrapped face (a `.pcf.gz`) is opened from its decompressed bytes: FreeType reads such a file itself, but
    re-inflating it on every glyph makes the 11,172-glyph sweep a hundred times slower.
    """
    with open(path, "rb") as f:
        wrapped = f.read(2) == b"\x1f\x8b"
    font = _open_font(path, size, data=_read_bytes(path, True)) if wrapped else _open_font(path, size)
    notdef = _bitmap_image(font, NOTDEF_CHAR).tobytes()
    return coverage_of(lambda cp: not notdef_absent(font, chr(cp), notdef))


def coverage_bdf(glyphs):
    """A BDF/HBF glyph dict's coverage: the code points whose glyph has rows (bdfface.py's own reading)."""
    return coverage_of(lambda cp: bool(glyphs.get(cp, (0, 0, 0, 0, [], 0))[4]))


def read_svf(data):
    """A v3 or v2 SVFN face as a jamoset.Svfn (`version` 3 or 2); v2 is read by tools/svf2to3.py, the one v2 reader.
    ValueError on anything else."""
    return svf2to3._parse(data)


def usable_jset(face):
    """The JSET tables (jamoset.Tables, or a jamoset.Jmap for a version 3 block) of an SVF face when the renderer would
    use them (tools/svfline.py's rule: the JSET unpacks and every non-blank piece glyph is present; for a Jmap that is
    rule R8: its plane pieces, its fallback's pieces and the effective compat), else None."""
    if not (face.flags & jamoset.FLAG_JAMO) or face.jset is None:
        return None
    try:
        t = jamoset.unpack(face.jset)
    except ValueError:
        return None
    if all(n == jamoset.BLANK or jamoset.PIECE_BASE + n in face.glyphs
           for n in t.init_piece + t.med_piece + t.fin_piece + t.compat):
        return t
    return None


def jmap_mode(block):
    """"dense" | "sparse" | "list" from the flags byte of a JSET version 3 block's header (0x08 LIST, 0x02 SPARSE, else
    dense), else None (set tables, no block). A SPARSE block that holds 11,172 entries is still "sparse"."""
    if block is None or len(block) < 7 or struct.unpack_from("<H", block, 4)[0] != jamoset.JMAP_VERSION:
        return None
    flags = block[6]
    return "list" if flags & jamoset.JMAP_FLAG_LIST else "sparse" if flags & jamoset.JMAP_FLAG_SPARSE else "dense"


def coverage_svf(face):
    """An SVF face's coverage.

    A jamo set draws every syllable from its pieces, so `all` and `ks2350` hold by construction (a JMAP face: the syllables it maps or the cmap holds), `ascii` comes from
    the glyphs the file carries and `compat` from its JSET compat table plus the compatibility jamo the face stores
    as whole glyphs (U+3131..U+3163 in its cmap). Anything else (a precomposed face, or a jamo flag whose JSET does
    not parse or names a missing piece glyph) is read from its glyphs.
    """
    t = usable_jset(face)
    if t is None:
        return coverage_of(lambda cp: cp in face.glyphs)
    if isinstance(t, jamoset.Jmap):
        # a JMAP draws only the syllables it maps (or its fallback does); the rest are the cmap glyph or none
        have = lambda cp: t.pieces(cp) is not None or cp in face.glyphs
        ks = sum(1 for n in jamoset.ks_x_1001_syllables() if have(0xAC00 + n))
        whole = sum(1 for cp in range(0xAC00, 0xD7A4) if have(cp))
    else:
        ks, whole = 2350, 11172
    return {"ascii": sum(1 for cp in range(0x20, 0x7F) if cp in face.glyphs),
            "ks2350": ks,
            "all": whole,
            "compat": sum(1 for k in range(51) if t.compat[k] != jamoset.BLANK or (0x3131 + k) in face.glyphs)}


def _composite_syllable(glyph, has_final, glyph_order):
    """True when @p glyph is a composite of 2 components (3 when @p has_final) that all name glyphs of the font.

    The count and the names come from the `glyf` table alone: nothing is flattened, so a component that is itself a
    composite costs no more than a plain one. A component naming a glyph the file has not got (a corrupt index)
    makes the syllable not composite rather than raising.
    """
    try:
        comps = glyph.components
        return len(comps) == 2 + (1 if has_final else 0) and all(c.glyphName in glyph_order for c in comps)
    except Exception:
        return False


def composite_test(path, face_index=0, data=None):
    """(is_composite, drawn, composite) of an outline face's Hangul syllables, from the `glyf` table alone.

    A CFF face has no `glyf` table and is never composite: `(False, 0, 0)`. `drawn` counts the syllables
    0xAC00..0xD7A3 with a cmap entry whose glyph has contours (a composite has -1); `composite` counts those whose
    glyph `isComposite()`, whose top-level component count is 2 (3 when the syllable has a final:
    `(cp - 0xAC00) % 28`), and whose component names all exist. Nothing is drawn or flattened, so a font whose
    components nest (a syllable of two glyphs that are themselves composites) is decided in table reads alone and
    the third value is exact. A face is "native composite" when at least 95 % of its drawn syllables are.
    @p data is a `.gz` source's decompressed bytes (the face is then opened from those).
    """
    try:
        face = jamoaa.OutlineFace(io.BytesIO(data) if data is not None else path, 48, font_number=face_index)
    except Exception:
        return False, 0, 0
    try:
        if "glyf" not in face.font:
            return False, 0, 0
        glyf = face.font["glyf"]
        order = set(face.font.getGlyphOrder())
        cmap = face.cmap
        drawn = composite = 0
        for cp in range(0xAC00, 0xD7A4):
            name = cmap.get(cp)
            if name is None:
                continue
            try:
                glyph = glyf[name]
            except KeyError:              # a cmap entry naming a glyph the file has not got
                continue
            except Exception:             # a glyph whose components cannot be read: not one we can count
                continue
            if not glyph.numberOfContours:    # an empty glyph (a composite is -1)
                continue
            drawn += 1
            if _composite_syllable(glyph, (cp - 0xAC00) % 28 != 0, order):
                composite += 1
    finally:
        face.font.close()
    return drawn > 0 and composite >= 0.95 * drawn, drawn, composite


def jamo_label(entry):
    """An entry's jamo availability: `native (<layout|composite|jset>)`, `compat N/51`, or `none`."""
    kind = entry.get("source_kind")
    if kind == "dos-raw":
        candidates = (entry.get("dos") or {}).get("candidates") or []
        return "native (%s)" % candidates[0] if candidates else "none"
    if kind == "bdf-johab":
        return "native (hanterm-johab)"
    if kind == "svf-jamo":
        return "native (jset)"
    if kind == "outline-composite":
        return "native (composite)"
    compat = (entry.get("coverage") or {}).get("compat", 0)
    return "compat %d/51" % compat if compat > 0 else "none"


# ---- licence search --------------------------------------------------------------------------------------------

def _licence_folders(paths):
    """The licence files of @p paths grouped by folder: the name/text verdict is decided once per file.

    A symlinked file is never a licence: the scan does not follow links, and neither does this map.
    """
    out = {}
    for p in paths:
        if os.path.islink(p):
            continue
        if is_licence_name(os.path.basename(p)) or is_licence_text(p):
            out.setdefault(os.path.dirname(p), []).append(p)
    return out


def find_licences(rel, all_rels, licences=None, root=None):
    """The licence files nearest to @p rel: those of its own folder, else of each parent up to the batch root.

    A file counts when its name matches `is_licence_name` or it is a `.txt` whose text `is_licence_text` claims.
    The nearest folder with any match wins and every match of that folder is returned, sorted. @p rel and
    @p all_rels are paths as the caller holds them (the scan passes absolute paths) and the matches come back in the
    same form; the root is the deepest folder that holds every file of the batch. @p licences (the map
    `_licence_folders` builds) and @p root, when given, are computed once by the scan, so the walk is linear.
    """
    if licences is None:
        licences = _licence_folders(all_rels)
    if root is None:
        root = os.path.commonpath([os.path.dirname(r) for r in all_rels]) if all_rels else os.path.dirname(rel)
    folder = os.path.dirname(rel)
    while True:
        hits = sorted(p for p in licences.get(folder, ()) if p != rel)
        if hits:
            return hits
        if folder == root or os.path.dirname(folder) == folder:
            return []
        folder = os.path.dirname(folder)


def _first_line(path):
    """The first non-empty line of @p path's first 4 KB, stripped and at most 120 characters; "" when unreadable.

    A leading UTF-8 BOM is stripped before the first line is taken.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return ""
    for line in head.decode("utf-8", "replace").lstrip("\ufeff").splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return ""


# ---- the batch -------------------------------------------------------------------------------------------------

def _rel(upload_dir, path):
    """@p path as the entry's `path`: relative to @p upload_dir, with `/` separators."""
    return os.path.relpath(path, upload_dir).replace(os.sep, "/")


def _bdf_glyphs(path, unicode_enc=None, data=None):
    """`bdfface.read_bdf`'s glyph dict.

    @p data is a `.gz` source's decompressed bytes: `read_bdf` takes a path only, so those bytes are written to a
    temp file under the system temp dir (never under `upload/`), parsed, and the temp file removed.
    """
    if data is None:
        return bdfface.read_bdf(path, unicode_enc=unicode_enc)[1]
    fd, tmp = tempfile.mkstemp(prefix="svf-maker-bdf-", suffix=".bdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return bdfface.read_bdf(tmp, unicode_enc=unicode_enc)[1]
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


SFNT_FORMATS = ("ttf", "otf", "ttc", "mac-rsrc")


def _coverage_of_entry(path, entry, data=None, face_index=None):
    """An entry's coverage, or None when the source cannot be read (a kind with none, or an unsafe HBF).

    @p data is a `.gz` source's decompressed bytes (read once per file by `scan`), shared with the composite test.
    A `.hbf.gz` stays None: an HBF's bitmap files resolve relative to the HBF's own path, which is not decompressed
    here.
    """
    kind = entry["source_kind"]
    face = entry["face_index"] if face_index is None else face_index
    try:
        if kind == "dos-raw":
            return dict(DOS_COVERAGE)
        if kind in ("outline", "outline-composite"):
            return coverage_outline(path, face, data)
        if kind == "bitmap" and entry["format"] in SFNT_FORMATS:
            return coverage_cmap(path, face, data)
        if kind == "bitmap":
            return coverage_bitmap(path, entry["sizes"][0]) if entry["sizes"] else None
        if kind in ("bdf-iso10646", "bdf-iso8859"):
            return coverage_bdf(_bdf_glyphs(path, unicode_enc=True, data=data))   # their ENCODING is a code point
        if kind == "bdf-ksc5601":
            return coverage_bdf(_bdf_glyphs(path, data=data))                    # a GL code, as bdfface.py reads it
        if kind == "bdf-johab":
            return dict(JOHAB_COVERAGE)          # johab-1 glyph indices, not KS X 1001 codes: composed from jamo
        if kind == "hbf":
            if entry.get("gzip") or not hbf_refs_safe(path):
                return None
            return coverage_bdf(bdfface.read_hbf(path)[1])
        if kind in ("svf-jamo", "svf-precomposed"):
            raw = data if data is not None else _read_bytes(path, entry.get("gzip", False))
            return coverage_svf(read_svf(raw))
    except Exception:
        return None
    return None


def _entry_size(path, entry, data=None):
    """A file's size for the `eng` -> `unknown` label: the decompressed length when it is a `.gz` source.

    @p data is the file's decompressed bytes, read by `scan` for this file alone; None (a source it could not read)
    falls back to the on-disk size.
    """
    if entry.get("gzip") and data is not None:
        return "%d bytes decompressed" % len(data)
    try:
        return "%d bytes" % os.path.getsize(path)
    except OSError:
        return "unknown size"


def scan(upload_dir):
    """Every regular file under @p upload_dir as a font entry (Shared data shapes), in relative path order.

    Archives are dropped; a file's entries keep their face order; the ids are `f01`, `f02`, ... in that order
    (`f100` after 99). Each entry gets its `coverage`, `jamo`, `licences` and `companions`; an outline face whose
    syllables are composites becomes `outline-composite`, and a 2048/4096 byte file with no DOS Johab font beside it
    is `unknown`. `licence`, `list`, `eng` and `unknown` entries stay in the list (the page shows them under
    "other").

    A symlinked file is never followed: it gets an `other` entry labelled "symlink, skipped". A `.gz` source is
    decompressed once per file, under MAX_DECOMPRESSED, and those bytes are used for that file's composite test and
    coverage and then dropped: nothing scan-wide holds a decompressed file. The whole coverage pass is bounded by
    SCAN_COVERAGE_BUDGET_S; past it the remaining entries get coverage None and their label carries "; coverage
    skipped (time budget)".
    """
    rels = []
    symlinks = set()
    for root, _dirs, files in os.walk(upload_dir):
        for name in files:
            path = os.path.join(root, name)
            rel = _rel(upload_dir, path)
            if os.path.islink(path):
                symlinks.add(rel)             # Task 11 refuses them at unpack; the scan never follows one
            elif not os.path.isfile(path):
                continue
            rels.append(rel)
    rels.sort()
    abs_of = {rel: os.path.join(upload_dir, rel) for rel in rels}
    all_abs = [abs_of[rel] for rel in rels]

    entries = []
    groups = {}                          # a file's entries, so one decompression serves all of them
    for rel in rels:
        if rel in symlinks:
            entry = _entry(rel, 0, "unknown", "symlink, skipped", "other", family=_stem(rel))
            entries.append(entry)
            groups.setdefault(rel, []).append(entry)
            continue
        for entry in detect_file(abs_of[rel], rel):
            if entry["format"] != "archive":
                entries.append(entry)
                groups.setdefault(rel, []).append(entry)

    dos_folders = {os.path.dirname(e["path"]) for e in entries if e["source_kind"] == "dos-raw"}
    for i, entry in enumerate(entries, 1):
        entry["id"] = "f%02d" % i

    licences = _licence_folders(all_abs)
    licence_root = os.path.commonpath([os.path.dirname(p) for p in all_abs]) if all_abs else upload_dir
    deadline = time.monotonic() + SCAN_COVERAGE_BUDGET_S
    for rel in rels:                     # one pass per file: a `.gz` source's bytes live for that file alone
        group = groups.get(rel)
        if not group:
            continue
        path = abs_of[rel]
        data = raw = None
        if any(e.get("gzip") for e in group):
            try:
                data = _read_bytes(path, True)
            except Exception:
                data = None
        for entry in group:
            if entry["source_kind"] == "hbf":
                reason = hbf_refusal(path)
                if reason:
                    entry["label"] = "HBF: " + reason
            if entry["format"] == "eng" and os.path.dirname(entry["path"]) not in dos_folders:
                entry["format"] = "unknown"       # a Latin companion needs a DOS Johab font beside it
                entry["label"] = "unknown (%s; no DOS Johab font beside it)" % _entry_size(path, entry, data)
            src, face, cannot = data, entry["face_index"], None
            if entry.get("prep") and time.monotonic() < deadline:
                # the font as the tools will read it: a prep entry's composite test and coverage run on those bytes
                try:
                    if data is None and raw is None:
                        raw = _read_bytes(path)
                    src, face = srcprep.prepared_bytes(data if data is not None else raw, entry["prep"]), 0
                except Exception as ex:           # a damaged table must not take the scan down
                    cannot = str(ex) or type(ex).__name__
            if cannot is None and entry["source_kind"] == "outline" and _is_composite(path, face, src):
                entry["source_kind"] = "outline-composite"
            if cannot is not None:
                entry["coverage"] = None
                entry["label"] += "; cannot prepare: %s" % cannot
            elif time.monotonic() >= deadline:
                entry["coverage"] = None
                entry["label"] += "; coverage skipped (time budget)"
            else:
                entry["coverage"] = _coverage_of_entry(path, entry, src, face)
            entry["jamo"] = jamo_label(entry)
            entry["licences"] = [{"path": _rel(upload_dir, p), "first_line": _first_line(p)}
                                 for p in find_licences(path, all_abs, licences, licence_root)]
        data = raw = src = None          # drop the decompressed bytes before the next file

    latin_ids = [e["id"] for e in entries if e["source_kind"] in ("bdf-iso10646", "bdf-iso8859", "hbf")]
    for entry in entries:
        if entry["source_kind"] == "dos-raw":
            folder = os.path.dirname(entry["path"])
            entry["companions"] = [o["id"] for o in entries
                                   if o["format"] == "eng" and os.path.dirname(o["path"]) == folder]
        elif entry["source_kind"] == "bdf-ksc5601":
            entry["companions"] = list(latin_ids)
        else:
            entry["companions"] = []
    return entries


def _is_composite(path, face_index, data=None):
    """`composite_test`'s verdict, never raising (a source the test cannot open is not composite)."""
    try:
        return composite_test(path, face_index, data)[0]
    except Exception:
        return False
