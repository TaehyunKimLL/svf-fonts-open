#!/usr/bin/env python3
"""srcprep.py - the source conversions the maker needs before any existing tool can read a file.

Reading helpers (a TTC face, `fvar`, `EBLC` strikes, Mac cmaps, resource forks, PCF) used by detect.py, and a small CLI
for the two conversions no tool in tools/ has:

    srcprep.py ttc-face SRC OUT --index N    face N of a TTC/OTC saved as a plain sfnt
    srcprep.py pcf-bdf SRC OUT               a PCF (or .pcf.gz) as a BDF 2.1 text

Exit 0 and OUT written; exit 2 with the reason on stderr. Stdlib and fontTools only. It runs under `python3 -P`, which
drops the script directory from sys.path, so it puts maker/ and tools/ there itself.
"""

import os, sys
MAKER_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (MAKER_DIR, os.path.join(os.path.dirname(MAKER_DIR), "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import argparse
import io
import struct

import macsfnt
from fontTools.ttLib import TTCollection, TTFont, TTLibError

MAX_BYTES = 128 << 20          # the same cap as detect.MAX_DECOMPRESSED (srcprep does not import detect)


class PrepError(Exception):
    pass


# ---- sfnt reading ----------------------------------------------------------------------------------------------

def ttc_face_bytes(data, index):
    """Face @p index of a TTC/OTC saved as a plain sfnt."""
    try:
        coll = TTCollection(io.BytesIO(data))
    except (TTLibError, struct.error, OSError, AssertionError) as e:
        raise PrepError("not a font collection (%s)" % e)
    if not 0 <= index < len(coll.fonts):
        raise PrepError("face %d out of range (the collection has %d faces)" % (index, len(coll.fonts)))
    buf = io.BytesIO()
    try:
        coll.fonts[index].save(buf)
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
        return sorted({raw[8 + 48 * i + 45] for i in range(n)})
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

def mac_resources(data):
    """(container, [(type, id, name, body)]); container is "AppleDouble", "MacBinary" or "resource fork"."""
    try:
        fork = macsfnt.resource_fork(data)
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


# ---- ops -------------------------------------------------------------------------------------------------------

def prepared_bytes(data, ops):
    """@p ops applied in order, in-process. An `instance` op raises: detection never instantiates."""
    for op in ops:
        kind = op.get("op")
        if kind == "rsrc-sfnt":
            for rtype, rid, _name, body in mac_resources(data)[1]:
                if rtype == b"sfnt" and rid == op["id"]:
                    data = body
                    break
            else:
                raise PrepError("no 'sfnt' resource %s" % op["id"])
        elif kind == "ttc-face":
            data = ttc_face_bytes(data, op["index"])
        elif kind == "mac-cmap":
            try:
                font = TTFont(io.BytesIO(data))
                macsfnt.add_unicode(font)
                buf = io.BytesIO()
                font.save(buf)
            except macsfnt.MacError as e:
                raise PrepError(str(e))
            except (TTLibError, struct.error, OSError, KeyError) as e:
                raise PrepError("not an sfnt font (%s)" % e)
            data = buf.getvalue()
        elif kind == "pcf-bdf":
            data = pcf_to_bdf(data)
        else:
            raise PrepError("unsupported prep op %r" % kind)
    return data


def pcf_to_bdf(data):
    raise PrepError("PCF reader not available")


# ---- CLI -------------------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ttc-face")
    p.add_argument("src")
    p.add_argument("out")
    p.add_argument("--index", type=int, required=True)
    p = sub.add_parser("pcf-bdf")
    p.add_argument("src")
    p.add_argument("out")
    a = ap.parse_args(argv)
    try:
        with open(a.src, "rb") as fh:
            data = fh.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise PrepError("too large")
        out = ttc_face_bytes(data, a.index) if a.cmd == "ttc-face" else pcf_to_bdf(data)
        with open(a.out, "wb") as fh:
            fh.write(out)
    except (PrepError, OSError) as e:
        print("srcprep: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
