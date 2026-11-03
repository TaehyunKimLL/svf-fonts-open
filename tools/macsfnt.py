#!/usr/bin/env python3
"""macsfnt.py - Mac-format TrueType for the SVF tools: 'sfnt' resources out of a resource fork, and a Unicode cmap for a
font that has only a Mac Korean (platform 1, script 3) or Windows Wansung (platform 3, encoding 5) one.

    macsfnt.py list FILE                       the font resources of FILE ('sfnt', 'NFNT', 'FONT', 'FOND', 'fbit'):
                                               type, id, name, bytes
    macsfnt.py extract FILE OUT.ttf [--id N]   one 'sfnt' resource as a plain TrueType file (default: the first)
    macsfnt.py cmap FONT                       the cmap subtables of an sfnt file: platform, encoding, format, entries,
                                               and how many of them are Hangul syllables once read as Unicode
    macsfnt.py unicode FONT OUT.ttf            add a Unicode subtable (3,1 format 4; 3,10 format 12 as well when a code
                                               point is past U+FFFF) made from the font's Mac Korean (1,3) or Wansung
                                               (3,5) subtable; a font that already has a Unicode subtable is refused

FILE is a resource fork as a plain file: a .dfont, a fork copied out of a Mac file system (`cat F/..namedfork/rsrc`
on macOS), an AppleDouble file (`._NAME`, magic 0x00051607, its resource fork entry is used) or a MacBinary file (the
fork after the 128-byte header). Fonts that are already plain .ttf / .ttc need no extraction.

The Mac Korean and Wansung subtables hold two-byte KS X 1001 (EUC-KR) codes; each is read as bytes and decoded with
Python's euc_kr codec (KS X 1001 rows 0xA1-0xFE; Apple's own additions to Mac Korean decode to nothing and are counted
as unmapped). The added subtable maps the same glyphs, so mkfont.py (Pillow/FreeType, which select a Unicode cmap) and
the jamo-set tools can then read the font. Stdlib and fontTools only. Writes only the output path it is given.
"""
import argparse
import io
import struct
import sys

FONT_TYPES = (b"sfnt", b"NFNT", b"FONT", b"FOND", b"fbit")


class MacError(Exception):
    pass


def resource_fork(data):
    """The resource fork bytes held by @p data: AppleDouble, MacBinary, or the data itself (a .dfont / raw fork)."""
    if len(data) >= 26 and data[:4] == b"\x00\x05\x16\x07":
        n = struct.unpack_from(">H", data, 24)[0]
        for i in range(n):
            eid, off, length = struct.unpack_from(">III", data, 26 + 12 * i)
            if eid == 2:
                return data[off:off + length]
        raise MacError("AppleDouble file without a resource fork entry")
    if len(data) >= 128 and data[0] == 0 and 1 <= data[1] <= 63 and data[74] == 0 and data[82] == 0:
        dlen, rlen = struct.unpack_from(">II", data, 83)
        start = 128 + ((dlen + 127) // 128) * 128
        if rlen and start + rlen <= len(data):
            return data[start:start + rlen]
    return data


def resources(fork):
    """[(type, id, name, bytes)] of every resource of the fork (stdlib parser of the Resource Manager layout)."""
    if len(fork) < 16:
        raise MacError("too short for a resource fork")
    data_off, map_off, data_len, map_len = struct.unpack_from(">IIII", fork, 0)
    if map_off + 30 > len(fork) or data_off + data_len > len(fork):
        raise MacError("not a resource fork (header offsets out of range)")
    type_list = map_off + struct.unpack_from(">H", fork, map_off + 24)[0]
    name_list = map_off + struct.unpack_from(">H", fork, map_off + 26)[0]
    ntypes = (struct.unpack_from(">H", fork, type_list)[0] + 1) & 0xFFFF
    out = []
    for t in range(ntypes):
        rtype, count, ref_off = struct.unpack_from(">4sHH", fork, type_list + 2 + 8 * t)
        for r in range(count + 1):
            rid, noff, attr_data = struct.unpack_from(">hHI", fork, type_list + ref_off + 12 * r)
            doff = data_off + (attr_data & 0xFFFFFF)
            length = struct.unpack_from(">I", fork, doff)[0]
            if doff + 4 + length > len(fork):
                raise MacError("resource %s %d runs past the fork" % (rtype.decode("latin-1"), rid))
            name = ""
            if noff != 0xFFFF:
                n = fork[name_list + noff]
                name = fork[name_list + noff + 1:name_list + noff + 1 + n].decode("mac_roman")
            out.append((rtype, rid, name, fork[doff + 4:doff + 4 + length]))
    return out


def read(path):
    with open(path, "rb") as fh:
        return resource_fork(fh.read())


def cmap_report(font):
    """[(platform, encoding, format, entries, hangul)] of the font's cmap subtables."""
    rows = []
    for st in font["cmap"].tables:
        uni = unicode_map(st) if not st.isUnicode() else dict(st.cmap)
        hangul = sum(1 for cp in uni if 0xAC00 <= cp <= 0xD7A3)
        rows.append((st.platformID, st.platEncID, st.format, len(st.cmap), hangul))
    return rows


def ksc_char(code):
    """The Unicode character of a two-byte KS X 1001 / EUC-KR code (or a one-byte ASCII code), or None."""
    if code < 0x80:
        return chr(code)
    if code > 0xFFFF:
        return None
    try:
        s = bytes((code >> 8, code & 0xFF)).decode("euc_kr")
    except UnicodeDecodeError:
        return None
    return s if len(s) == 1 else None


def unicode_map(subtable):
    """{code point: glyph name} of a Mac Korean (1,3) or Wansung (3,5) subtable; other subtables give {}."""
    if (subtable.platformID, subtable.platEncID) not in ((1, 3), (3, 5)):
        return {}
    out = {}
    for code, glyph in subtable.cmap.items():
        ch = ksc_char(code)
        if ch is not None:
            out.setdefault(ord(ch), glyph)
    return out


def add_unicode(font):
    """Add the Unicode subtables to @p font (a fontTools TTFont); returns (mapped, unmapped)."""
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
    cmap = font["cmap"]
    if any(st.isUnicode() for st in cmap.tables):
        raise MacError("the font already has a Unicode cmap subtable")
    src = [st for st in cmap.tables if (st.platformID, st.platEncID) in ((1, 3), (3, 5))]
    if not src:
        raise MacError("no Mac Korean (1,3) or Wansung (3,5) cmap subtable")
    uni = {}
    for st in src:
        for cp, g in unicode_map(st).items():
            uni.setdefault(cp, g)
    unmapped = sum(len(st.cmap) for st in src) - len(uni)
    bmp = {cp: g for cp, g in uni.items() if cp <= 0xFFFF}
    st4 = CmapSubtable.newSubtable(4)
    st4.platformID, st4.platEncID, st4.language, st4.cmap = 3, 1, 0, bmp
    cmap.tables.append(st4)
    if len(bmp) != len(uni):
        st12 = CmapSubtable.newSubtable(12)
        st12.platformID, st12.platEncID, st12.language, st12.cmap = 3, 10, 0, uni
        cmap.tables.append(st12)
    return len(uni), max(0, unmapped)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("file")
    p = sub.add_parser("extract")
    p.add_argument("file")
    p.add_argument("out")
    p.add_argument("--id", type=int)
    p = sub.add_parser("cmap")
    p.add_argument("font")
    p = sub.add_parser("unicode")
    p.add_argument("font")
    p.add_argument("out")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            for rtype, rid, name, body in resources(read(a.file)):
                if rtype in FONT_TYPES:
                    print("%s\t%d\t%s\t%d" % (rtype.decode("latin-1"), rid, name, len(body)))
            return 0
        if a.cmd == "extract":
            sfnts = [(rid, name, body) for rtype, rid, name, body in resources(read(a.file)) if rtype == b"sfnt"]
            if a.id is not None:
                sfnts = [s for s in sfnts if s[0] == a.id]
            if not sfnts:
                raise MacError("no 'sfnt' resource%s in %s" % ("" if a.id is None else " %d" % a.id, a.file))
            rid, name, body = sfnts[0]
            with open(a.out, "wb") as fh:
                fh.write(body)
            print("%s: sfnt %d %r, %d bytes" % (a.out, rid, name, len(body)))
            return 0
        from fontTools.ttLib import TTFont, TTLibError
        try:
            font = TTFont(a.font)
        except (TTLibError, OSError) as e:
            raise MacError("%s: not an sfnt font (%s)" % (a.font, e))
        if a.cmd == "cmap":
            for row in cmap_report(font):
                print("platform=%d encoding=%d format=%d entries=%d hangul=%d" % row)
            return 0
        mapped, unmapped = add_unicode(font)
        buf = io.BytesIO()
        font.save(buf)
        with open(a.out, "wb") as fh:
            fh.write(buf.getvalue())
        print("%s: %d code points in the Unicode subtable, %d codes not in KS X 1001" % (a.out, mapped, unmapped))
        return 0
    except (MacError, struct.error) as e:
        print("macsfnt: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
