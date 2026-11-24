#!/usr/bin/env python3
"""srcprep.py - the source conversions the maker needs before any existing tool can read a file.

Reading helpers (a TTC face, `fvar`, `EBLC` strikes, Mac cmaps, resource forks, PCF) used by detect.py, and a small CLI
for the two conversions no tool in tools/ has:

    srcprep.py ttc-face SRC OUT --index N    face N of a TTC/OTC saved as a plain sfnt
    srcprep.py pcf-bdf SRC OUT               a PCF (or .pcf.gz) as a BDF 2.1 text
    srcprep.py mac-fork SRC OUT              the resource fork of an AppleDouble / MacBinary / raw fork file
    srcprep.py mac-htbl SRC OUT              the HTBL 1 table of a fork or a raw table
    srcprep.py mac-fork-named SRC OUT        the native resource fork of a macOS file (SRC/..namedfork/rsrc)
    srcprep.py bdf-pixel-size SRC OUT --size N   a BDF with PIXEL_SIZE N set (FreeType otherwise derives it from SIZE)
    srcprep.py or-files OUT A B ...          the bytes of files of one size OR-ed (English fonts kept in several runs
                                             of a ROM merged into one table: a known set's recipe, maker/recipe.py)

Exit 0 and OUT written; exit 2 with the reason on stderr. Stdlib and fontTools only. It runs under `python3 -P`, which
drops the script directory from sys.path, so it puts maker/ and tools/ there itself.
"""

import os, sys
MAKER_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (MAKER_DIR, os.path.join(os.path.dirname(MAKER_DIR), "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import argparse
import array
import io
import struct
import zlib

import macfbit3
import macsfnt
from fontTools.ttLib import TTFont, TTLibError

MAX_ROWS = 1 << 20            # glyph rows one PCF may convert to BDF (a CJK 24 px face is about 270,000)
JM_CAP = 4 << 20               # a JM archive's declared unpacked size (a type-3 fbit is ~10 KB)
MAX_BYTES = 128 << 20          # the same cap as detect.MAX_DECOMPRESSED (srcprep does not import detect)


class PrepError(Exception):
    pass


# ---- sfnt reading ----------------------------------------------------------------------------------------------

def ttc_face_bytes(data, index):
    """Face @p index of a TTC/OTC saved as a plain sfnt (only that face is opened: a header may list thousands)."""
    if data[:4] != b"ttcf" or len(data) < 12:
        raise PrepError("not a font collection")
    total = struct.unpack_from(">I", data, 8)[0]
    if not 0 <= index < total:
        raise PrepError("face %d out of range (the collection has %d faces)" % (index, total))
    buf = io.BytesIO()
    try:
        TTFont(io.BytesIO(data), fontNumber=index).save(buf)
    except Exception as e:
        raise PrepError("cannot save face %d (%s: %s)" % (index, type(e).__name__, e))
    return buf.getvalue()


def _num(v):
    return int(v) if v == int(v) else v


def variable_info(font):
    """{"axes": [{tag, min, default, max}], "instances": [{name, coords}]} from `fvar`; None without it."""
    if "fvar" not in font:
        return None
    fvar = font["fvar"]
    axes = [{"tag": a.axisTag, "min": _num(a.minValue), "default": _num(a.defaultValue), "max": _num(a.maxValue)}
            for a in fvar.axes]
    instances = []
    for n, inst in enumerate(fvar.instances, 1):
        name = None
        try:
            name = font["name"].getDebugName(inst.subfamilyNameID)
        except Exception:
            pass
        instances.append({"name": name or "instance %d" % n,
                          "coords": {t: _num(v) for t, v in inst.coordinates.items()}})
    return {"axes": axes, "instances": instances}


def embedded_strikes(font):
    """Sorted unique ppemY of the raw EBLC (else bloc) table; [] when absent or truncated."""
    for tag in ("EBLC", "bloc"):
        if tag not in font:
            continue
        try:
            raw = font.getTableData(tag)
        except Exception:
            return []
        if len(raw) < 8:
            return []
        n = struct.unpack_from(">I", raw, 4)[0]
        if 8 + 48 * n > len(raw):
            return []
        return sorted({raw[8 + 48 * i + 45] for i in range(n)} - {0})
    return []


def has_outlines(font):
    return any(t in font for t in ("glyf", "CFF ", "CFF2"))


def mac_cmap_only(font):
    """No Unicode subtable and at least one Mac Korean (1,3) or Wansung (3,5) one."""
    try:
        tables = font["cmap"].tables
    except Exception:
        return False
    if any(st.isUnicode() for st in tables):
        return False
    return any((st.platformID, st.platEncID) in ((1, 3), (3, 5)) for st in tables)


# ---- Mac containers --------------------------------------------------------------------------------------------

MAX_RESOURCES = 4096


def _fork_guard(fork):
    """Refuse a fork macsfnt.resources would expand into a huge copy: more than MAX_RESOURCES references, or reference
    bodies that add up past MAX_BYTES (many references may share one body). Raises PrepError."""
    if len(fork) < 16:
        return                                   # macsfnt names this one
    data_off, map_off, data_len, _map_len = struct.unpack_from(">IIII", fork, 0)
    if map_off + 30 > len(fork) or data_off + data_len > len(fork):
        return
    type_list = map_off + struct.unpack_from(">H", fork, map_off + 24)[0]
    ntypes = (struct.unpack_from(">H", fork, type_list)[0] + 1) & 0xFFFF
    if ntypes > MAX_RESOURCES:
        raise PrepError("too many resource types (%d)" % ntypes)
    refs = []
    for t in range(ntypes):
        _rtype, count, ref_off = struct.unpack_from(">4sHH", fork, type_list + 2 + 8 * t)
        if len(refs) + count + 1 > MAX_RESOURCES:
            raise PrepError("too many resources (more than %d)" % MAX_RESOURCES)
        refs.extend(type_list + ref_off + 12 * r for r in range(count + 1))
    total = 0
    for ref in refs:
        _rid, _noff, attr_data = struct.unpack_from(">hHI", fork, ref)
        doff = data_off + (attr_data & 0xFFFFFF)
        if doff + 4 > len(fork):
            return                                   # out of range: macsfnt.resources names the bounds error
        length = struct.unpack_from(">I", fork, doff)[0]
        if doff + 4 + length > len(fork):
            return
        total += length
        if total > MAX_BYTES:
            raise PrepError("resources too large")


def mac_resources(data):
    """(container, [(type, id, name, body)]); container is "AppleDouble", "MacBinary" or "resource fork"."""
    try:
        fork = macsfnt.resource_fork(data)
        _fork_guard(fork)
        res = macsfnt.resources(fork)
    except (macsfnt.MacError, struct.error, IndexError) as e:
        raise PrepError(str(e) or type(e).__name__)
    if data[:4] == b"\x00\x05\x16\x07":
        container = "AppleDouble"
    elif fork is not data:
        container = "MacBinary"
    else:
        container = "resource fork"
    return container, res


def mac_fork_bytes(data):
    """The raw resource fork held by @p data (AppleDouble, MacBinary or the fork itself), once it parses as one."""
    try:
        fork = macsfnt.resource_fork(data)
        _fork_guard(fork)
        macsfnt.resources(fork)
    except (macsfnt.MacError, struct.error, IndexError) as e:
        raise PrepError(str(e) or type(e).__name__)
    return fork


def bdf_pixel_size(data, size):
    """@p data (a BDF 2.1 text) with `PIXEL_SIZE <size>` in its properties; one it already has is replaced."""
    text = data.decode("latin-1")
    lines = text.split("\n")
    out, done = [], False
    for line in lines:
        if line.startswith("PIXEL_SIZE"):
            continue
        out.append(line)
    for i, line in enumerate(out):
        if line.startswith("STARTPROPERTIES"):
            count = int(line.split()[1]) if len(line.split()) > 1 else 0
            had = sum(1 for l in lines if l.startswith("PIXEL_SIZE"))
            out[i] = "STARTPROPERTIES %d" % (count - had + 1)
            out.insert(i + 1, "PIXEL_SIZE %d" % size)
            done = True
            break
    if not done:
        for i, line in enumerate(out):
            if line.startswith("FONTBOUNDINGBOX"):
                out[i + 1:i + 1] = ["STARTPROPERTIES 1", "PIXEL_SIZE %d" % size, "ENDPROPERTIES"]
                done = True
                break
    if not done:
        raise PrepError("not a BDF")
    return "\n".join(out).encode("latin-1")


def mac_htbl_bytes(data):
    """The `HTBL` 1 table of @p data (a fork holding it, or the raw table), checked: a 204-byte jamo part and at least
    the 2,350 syllable entries. Raises PrepError("not an HTBL 1 table")."""
    try:
        table = macfbit3.load_htbl1(data)
        ok = (len(table) >= 8 + 204 + 4 * 2350 and struct.unpack(">I", table[:4])[0] == 204)
    except (ValueError, struct.error, IndexError):
        ok = False
    if not ok:
        raise PrepError("not an HTBL 1 table")
    return table


# ---- ops -------------------------------------------------------------------------------------------------------

def prepared_bytes(data, ops):
    """@p ops applied in order, in-process (detection applies none that instantiate; the previews and the probe apply the
    `instance` op the planned source step would run)."""
    for op in ops:
        try:
            data = _apply_op(data, op)
        except PrepError:
            raise
        except Exception as e:                     # a damaged table can raise anything: one reason, never a crash
            raise PrepError("%s: %s" % (type(e).__name__, e))
    return data


def _apply_op(data, op):
    kind = op.get("op")
    if kind == "rsrc-sfnt":
        for rtype, rid, _name, body in mac_resources(data)[1]:
            if rtype == b"sfnt" and rid == op["id"]:
                return body
        raise PrepError("no 'sfnt' resource %s" % op["id"])
    if kind == "ttc-face":
        return ttc_face_bytes(data, op["index"])
    if kind == "mac-cmap":
        try:
            font = TTFont(io.BytesIO(data))
            macsfnt.add_unicode(font)
            buf = io.BytesIO()
            font.save(buf)
        except macsfnt.MacError as e:
            raise PrepError(str(e))
        except (TTLibError, struct.error, OSError, KeyError) as e:
            raise PrepError("not an sfnt font (%s)" % e)
        return buf.getvalue()
    if kind == "instance":
        from fontTools.varLib import instancer
        font = TTFont(io.BytesIO(data))
        pinned = instancer.instantiateVariableFont(font, {tag: float(v) for tag, v in op["coords"].items()},
                                                   inplace=False)
        buf = io.BytesIO()
        pinned.save(buf)
        return buf.getvalue()
    if kind == "pcf-bdf":
        return pcf_to_bdf(data)
    if kind == "mac-fork":
        return mac_fork_bytes(data)
    if kind == "mac-fbit3":
        try:
            if data[:2] == b"JM" and macfbit3.jm_header(data)["unpacked_len"] > JM_CAP:
                raise PrepError("JM archive too large to unpack")
            return macfbit3.load_fbit(data)
        except (ValueError, struct.error, IndexError) as e:
            raise PrepError(str(e) or type(e).__name__)
    if kind == "mac-htbl":
        return mac_htbl_bytes(data)
    if kind == "mac-fork-named":
        raise PrepError("named forks are read by the CLI only")
    raise PrepError("unsupported prep op %r" % kind)


# ---- PCF -------------------------------------------------------------------------------------------------------

_PCF_PROPERTIES, _PCF_METRICS, _PCF_BITMAPS, _PCF_ENCODINGS = 1, 4, 8, 0x20


def _inflate(data):
    """@p data, gunzipped when it starts with the gzip magic (1 MiB chunks up to MAX_BYTES)."""
    if data[:2] != b"\x1f\x8b":
        return data
    import gzip
    parts, size = [], 0
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise PrepError("too large")
                parts.append(chunk)
    except (OSError, EOFError, zlib.error) as e:
        raise PrepError("bad gzip (%s)" % e)
    return b"".join(parts)


def _pcf_tables(data):
    """{type: (format, offset, size)} of a PCF's table of contents; PrepError when it is not a PCF or runs past the data."""
    if data[:4] != b"\x01fcp" or len(data) < 8:
        raise PrepError("not a PCF font")
    count = struct.unpack_from("<I", data, 4)[0]
    if count > 64 or 8 + 16 * count > len(data):
        raise PrepError("PCF table of contents runs past the data")
    out = {}
    for i in range(count):
        typ, fmt, size, off = struct.unpack_from("<IIII", data, 8 + 16 * i)
        out.setdefault(typ, (fmt, off, size))
    return out


def _need(data, tables, typ, what):
    """(offset, size) of table @p typ, PrepError when it is missing or runs past the data (a table the reader does not
    use may be truncated: real files are)."""
    if typ not in tables:
        raise PrepError("PCF without a %s table" % what)
    _fmt, off, size = tables[typ]
    if size < 8 or off + size > len(data):
        raise PrepError("PCF %s table runs past the data" % what)
    return off, size


def _pcf_properties(data, tables):
    off, size = _need(data, tables, _PCF_PROPERTIES, "properties")
    fmt = struct.unpack_from("<I", data, off)[0]
    en = ">" if fmt & 4 else "<"
    n = struct.unpack_from(en + "I", data, off + 4)[0]
    rec = off + 8
    if n > 4096 or rec + 9 * n > off + size:
        raise PrepError("PCF properties run past the table")
    base = rec + ((9 * n + 3) & ~3) + 4
    if base > off + size:
        raise PrepError("PCF properties run past the table")

    def text(o):
        if not 0 <= o < off + size - base:
            raise PrepError("PCF property string offset out of range")
        start = base + o
        end = data.find(b"\0", start, off + size)
        if start >= off + size or end < 0:
            raise PrepError("PCF property string runs past the table")
        return data[start:end].decode("latin-1")

    out = {}
    for i in range(n):
        name_off, is_str = struct.unpack_from(en + "IB", data, rec + 9 * i)
        value = struct.unpack_from(en + ("I" if is_str else "i"), data, rec + 9 * i + 5)[0]
        out[text(name_off)] = text(value) if is_str else value
    return out


def pcf_properties(data):
    """The PCF properties table (type 1) as {name: str | int}; @p data may be gzip."""
    data = _inflate(data)
    try:
        return _pcf_properties(data, _pcf_tables(data))
    except (struct.error, IndexError, ValueError) as e:
        raise PrepError("bad PCF (%s)" % e)


def _pcf_metrics(data, tables):
    """[(lsb, rsb, width, ascent, descent)] of the metrics table (compressed or not)."""
    off, size = _need(data, tables, _PCF_METRICS, "metrics")
    fmt = struct.unpack_from("<I", data, off)[0]
    en = ">" if fmt & 4 else "<"
    out = []
    if fmt & 0x100:
        n = struct.unpack_from(en + "H", data, off + 4)[0]
        if off + 6 + 5 * n > off + size:
            raise PrepError("PCF metrics run past the table")
        for i in range(n):
            out.append(tuple(b - 0x80 for b in data[off + 6 + 5 * i:off + 11 + 5 * i]))
    else:
        n = struct.unpack_from(en + "I", data, off + 4)[0]
        if n > 1 << 20 or off + 8 + 12 * n > off + size:
            raise PrepError("PCF metrics run past the table")
        for i in range(n):
            out.append(struct.unpack_from(en + "5h", data, off + 8 + 12 * i))
    return out


def _swap_units(block, unit):
    """@p block with the bytes inside each @p unit byte scan unit reversed (a tail shorter than a unit is kept)."""
    if unit == 1:
        return block
    code = {2: "H", 4: "I", 8: "Q"}.get(unit)
    if code is None:
        return block
    whole = len(block) - len(block) % unit
    arr = array.array(code, bytes(block[:whole]))
    arr.byteswap()
    return bytearray(arr.tobytes()) + block[whole:]


def _pcf_bitmaps(data, tables, metrics):
    """[bytes] one glyph's rows (MSBit-first, rows padded to the table's row pad) per glyph, bit/byte order undone."""
    off, size = _need(data, tables, _PCF_BITMAPS, "bitmaps")
    fmt = struct.unpack_from("<I", data, off)[0]
    en = ">" if fmt & 4 else "<"
    n = struct.unpack_from(en + "I", data, off + 4)[0]
    if n != len(metrics) or n > 1 << 20 or off + 8 + 4 * n + 16 > off + size:
        raise PrepError("PCF bitmaps do not match the metrics")
    offsets = struct.unpack_from(en + "%dI" % n, data, off + 8)
    sizes = struct.unpack_from(en + "4I", data, off + 8 + 4 * n)
    start = off + 8 + 4 * n + 16
    total = sizes[fmt & 3]
    if start + total > off + size:
        raise PrepError("PCF bitmaps run past the table")
    block = bytearray(data[start:start + total])
    if not fmt & 8:                                   # LSBit first: reverse the bits of each byte
        table = bytes(int("{:08b}".format(b)[::-1], 2) for b in range(256))
        block = bytearray(block.translate(table))
    if bool(fmt & 4) != bool(fmt & 8):                # byte order differs from bit order: swap inside each scan unit
        block = _swap_units(block, 1 << ((fmt >> 4) & 3))
    pad = 1 << (fmt & 3)
    out = []
    budget = 0
    for i, (lsb, rsb, _w, ascent, descent) in enumerate(metrics):
        rows = ascent + descent
        row_bytes = (max(0, rsb - lsb) + 7) // 8
        stride = (row_bytes + pad - 1) // pad * pad
        if rows < 0 or offsets[i] + rows * stride > len(block):
            raise PrepError("PCF glyph %d runs past the bitmaps" % i)
        budget += rows * row_bytes                    # glyphs may share bytes: bound what is copied out
        if budget > MAX_BYTES // 4:
            raise PrepError("PCF bitmaps too large")
        out.append(b"".join(bytes(block[offsets[i] + r * stride:offsets[i] + r * stride + row_bytes])
                            for r in range(rows)))
    return out


def _pcf_encodings(data, tables):
    """{code: glyph index} of the BDF encodings table; code = (byte1 << 8) | byte2."""
    off, size = _need(data, tables, _PCF_ENCODINGS, "encodings")
    fmt = struct.unpack_from("<I", data, off)[0]
    en = ">" if fmt & 4 else "<"
    min2, max2, min1, max1, _default = struct.unpack_from(en + "5h", data, off + 4)
    w, h = max2 - min2 + 1, max1 - min1 + 1
    if min2 < 0 or min1 < 0 or w <= 0 or h <= 0 or off + 14 + 2 * w * h > off + size:
        raise PrepError("PCF encodings run past the table")
    idx = struct.unpack_from(en + "%dH" % (w * h), data, off + 14)
    out = {}
    for i, g in enumerate(idx):
        if g != 0xFFFF:
            out[((min1 + i // w) << 8) | (min2 + i % w)] = g
    return out


def _ink_box(metrics, enc):
    """(x0, y0, x1, y1): the union of the ink boxes of the encoded glyphs (all zero without any)."""
    inked = [metrics[g] for g in enc.values() if metrics[g][1] > metrics[g][0] and metrics[g][3] + metrics[g][4] > 0]
    if not inked:
        return 0, 0, 0, 0
    return (min(m[0] for m in inked), min(-m[4] for m in inked), max(m[1] for m in inked), max(m[3] for m in inked))


def pcf_box(data):
    """[w, h] of the font bounding box (the union of the encoded glyphs' ink boxes), read from the metrics alone."""
    data = _inflate(data)
    try:
        tables = _pcf_tables(data)
        metrics = _pcf_metrics(data, tables)
        enc = _pcf_encodings(data, tables)
    except (struct.error, IndexError, ValueError) as e:
        raise PrepError("bad PCF (%s)" % e)
    if any(g >= len(metrics) for g in enc.values()):
        raise PrepError("PCF encodings name a glyph it does not have")
    x0, y0, x1, y1 = _ink_box(metrics, enc)
    return [x1 - x0, y1 - y0]


def _clean(text):
    """@p text with control characters replaced by a space (a BDF line must not be split by a property)."""
    return "".join(" " if ord(c) < 32 or ord(c) == 127 else c for c in text)


def pcf_to_bdf(data):
    """A BDF 2.1 text (latin-1 bytes) of every encoded glyph of a PCF (or .pcf.gz)."""
    data = _inflate(data)
    try:
        tables = _pcf_tables(data)
        props = _pcf_properties(data, tables)
        metrics = _pcf_metrics(data, tables)
        bitmaps = _pcf_bitmaps(data, tables, metrics)
        enc = _pcf_encodings(data, tables)
    except (struct.error, IndexError, ValueError) as e:
        raise PrepError("bad PCF (%s)" % e)
    if any(g >= len(metrics) for g in enc.values()):
        raise PrepError("PCF encodings name a glyph it does not have")
    x0, y0, x1, y1 = _ink_box(metrics, enc)
    px = props.get("PIXEL_SIZE")
    if not isinstance(px, int) or px <= 0:
        px = (y1 - y0) or 16
    props = dict(props)
    props.setdefault("FONT_ASCENT", max([m[3] for m in metrics] or [0]))
    props.setdefault("FONT_DESCENT", max([m[4] for m in metrics] or [0]))
    name = _clean(str(props.pop("FONT", None) or "-pcf-%s" % (props.get("FAMILY_NAME") or "font")))
    out = ["STARTFONT 2.1", "FONT %s" % name, "SIZE %d 75 75" % px,
           "FONTBOUNDINGBOX %d %d %d %d" % (x1 - x0, y1 - y0, x0, y0), "STARTPROPERTIES %d" % len(props)]
    for k, v in props.items():
        if isinstance(v, str):
            v = _clean(v).replace('"', '""')
        out.append('%s "%s"' % (k, v) if isinstance(v, str) else "%s %d" % (k, v))
    out += ["ENDPROPERTIES", "CHARS %d" % len(enc)]
    size = sum(len(x) + 1 for x in out)
    rows_total = 0
    for code in sorted(enc):
        g = enc[code]
        start = len(out)
        lsb, rsb, width, ascent, descent = metrics[g]
        w, h = max(0, rsb - lsb), ascent + descent
        rows_total += max(h, 0)                       # refuse before the glyph's row strings are built
        if rows_total > MAX_ROWS or size + 80 + max(h, 0) * ((w + 7) // 8 * 2 + 1) > MAX_BYTES:
            raise PrepError("PCF converts to too large a BDF")
        out += ["STARTCHAR g%04X" % code, "ENCODING %d" % code,
                "SWIDTH %d 0" % round(width * 72000 / (px * 75)), "DWIDTH %d 0" % width,
                "BBX %d %d %d %d" % (w, h, lsb, -descent), "BITMAP"]
        nb = (w + 7) // 8
        if w and h > 0:
            out += [bitmaps[g][r * nb:(r + 1) * nb].hex().upper() for r in range(h)]
        out.append("ENDCHAR")
        size += sum(len(x) + 1 for x in out[start:])
        if size > MAX_BYTES:
            raise PrepError("PCF converts to more than %d MiB of BDF" % (MAX_BYTES >> 20))
    out += ["ENDFONT", ""]
    return "\n".join(out).encode("latin-1", "replace")


# ---- CLI -------------------------------------------------------------------------------------------------------

def or_files(datas):
    """The byte-wise OR of @p datas (bytes of one length)."""
    if not datas or len({len(d) for d in datas}) != 1:
        raise PrepError("or-files needs files of one size")
    out = bytearray(datas[0])
    for d in datas[1:]:
        for i, v in enumerate(d):
            out[i] |= v
    return bytes(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("or-files")
    p.add_argument("out")
    p.add_argument("files", nargs="+")
    p = sub.add_parser("ttc-face")
    p.add_argument("src")
    p.add_argument("out")
    p.add_argument("--index", type=int, required=True)
    for name in ("pcf-bdf", "mac-fork", "mac-htbl", "bdf-pixel-size", "mac-fork-named"):
        p = sub.add_parser(name)
        p.add_argument("src")
        p.add_argument("out")
        if name == "bdf-pixel-size":
            p.add_argument("--size", type=int, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "or-files":
        try:
            datas = []
            for path in a.files:
                with open(path, "rb") as fh:
                    datas.append(fh.read(MAX_BYTES + 1))
            if any(len(d) > MAX_BYTES for d in datas):
                raise PrepError("too large")
            with open(a.out, "wb") as fh:
                fh.write(or_files(datas))
        except (PrepError, OSError) as e:
            print("srcprep: %s" % e, file=sys.stderr)
            return 2
        return 0
    if a.cmd == "mac-fork-named" and sys.platform != "darwin":
        print("srcprep: mac-fork-named: macOS only", file=sys.stderr)
        return 2
    try:
        with open(a.src + "/..namedfork/rsrc" if a.cmd == "mac-fork-named" else a.src, "rb") as fh:
            data = fh.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise PrepError("too large")
        if a.cmd == "ttc-face":
            out = ttc_face_bytes(data, a.index)
        elif a.cmd in ("mac-fork", "mac-fork-named"):
            out = mac_fork_bytes(data)
        elif a.cmd == "mac-htbl":
            out = mac_htbl_bytes(data)
        elif a.cmd == "bdf-pixel-size":
            out = bdf_pixel_size(data, a.size)
        else:
            out = pcf_to_bdf(data)
        with open(a.out, "wb") as fh:
            fh.write(out)
    except (PrepError, OSError) as e:
        print("srcprep: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
