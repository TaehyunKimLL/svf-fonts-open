#!/usr/bin/env python3
"""macfbit3.py - HangulTalk 7.1.x jamo-plane 'fbit' fonts (Seoul12, AppleGothic12, AppleMyungjo12, and the 24 px
AppleGothic24 / AppleMyungjo24) and their Installer 'splt' "JM" archives: unpack, glyph planes, composition, sheets
and a BDF of the 2,350 KS X 1001 syllables + 51 compatibility jamo.

Stdlib only. Reads the files named on the command line and writes only the output path given.

Formats (findings: johab-fonts notes/mac.md, section "HangulTalk 7.1.x jamo-plane fbit (type 3)", card t_0b4481e5):
  splt "JM"  data fork: 'JM' | u32 header len | u32 packed len | u32 file len | u32 unpacked len |
             u32 checksum = 32-bit byte sum of file[0x1e:] | ff x 8 (0x16..0x1d) | 0x1e: LHA -lh5- (Okumura ar002) bit stream,
             8 KB window, NC 510, NP 14, PBIT 4, NT 19, TBIT 5, CBIT 9, 16-bit block sizes, MSB first.
             The unpacked stream is the resource fork of the installed font file.
  fbit type 3  resource 'fbit' (ids 17408 Seoul, 17409 AppleMyungjo, 17410 AppleGothic): 80 00 'fbit', u16 at 0x0c = 3
             (FDEF handler type), u16 at 0x16 = cell size h, u16 at 0x4c = n ranges (6 B each), glyphs from
             0x4e + 6n (0x54): (h*h+7)//8 bytes each, rows bit-packed MSB first without row padding;
             482 glyphs = 2 banks x 241.
  HTBL 1     resource of InputBackSupport (7.1.2, uncompressed): u32 L1, L1 bytes = 51 x 4 B for KS A4A1..A4D3,
             u32 (0x2468, not a length), then 2,350 x 4 B for KS B0A1..C8FE (index (hi-0xb0)*94 + lo-0xa1)
             and a byte-identical copy of the 51 jamo entries (2,401 entries in all).
             Entry [bank][g1][g2][g3]: glyph = (bank-1)*241 + g - 0x0f, g in (0x00, 0x0e) = no plane; OR the planes.
             There are no computed composition rules: the table is the composition (FDEF 129 type-3 handler ->
             script selector 0x36 in PTCH 129 -> HTBL 1). Only these 2,401 codes can be composed.

usage:
  macfbit3.py unpack SPLT.data OUT              JM archive -> unpacked resource fork
  macfbit3.py fbit RSRC OUT                     the 'fbit' resource of a resource fork (raw or a JM archive)
  macfbit3.py info FONT                         FONT = fbit resource, resource fork or JM archive
  macfbit3.py sheets FONT HTBLSRC OUTPREFIX     PNG sheets: OUTPREFIX_glyphs_x1/_x4, _ks2350_x1/_x4
  macfbit3.py bdf FONT HTBLSRC NAME OUT.bdf     composed KS syllables + jamo as a BDF (Unicode encodings)
HTBLSRC is the InputBackSupport resource fork or a raw HTBL 1 resource.
"""
import argparse
import struct
import sys
import zlib

BANK = 241
KS_SYLLABLES = 2350


# ---------------------------------------------------------------- JM / LHA -lh5- (ar002) decoder

class Bits:
    def __init__(self, data, pos=0):
        self.d, self.p = data, pos * 8

    def get(self, n):
        v = 0
        for _ in range(n):
            q = self.p
            b = self.d[q >> 3] if (q >> 3) < len(self.d) else 0
            v = (v << 1) | ((b >> (7 - (q & 7))) & 1)
            self.p += 1
        return v


def _canon(lens):
    """Canonical Huffman table: {(length, code): symbol}."""
    tab, code = {}, 0
    for length in range(1, 33):
        for sym, ln in enumerate(lens):
            if ln == length:
                tab[(length, code)] = sym
                code += 1
        code <<= 1
    return tab


def _dec(bits, tab, single):
    if single is not None:
        return single
    c = 0
    for length in range(1, 33):
        c = (c << 1) | bits.get(1)
        if (length, c) in tab:
            return tab[(length, c)]
    raise ValueError("bad code at bit %d" % bits.p)


def _read_pt(bits, nn, nbit, ispecial):
    n = bits.get(nbit)
    if n == 0:
        return None, bits.get(nbit)
    lens = []
    while len(lens) < n:
        c = bits.get(3)
        if c == 7:
            while bits.get(1):
                c += 1
        lens.append(c)
        if len(lens) == ispecial:
            lens += [0] * bits.get(2)
    lens += [0] * (nn - len(lens))
    return lens[:nn], None


def _read_c(bits, nc, cbit, ptlens, ptsingle):
    n = bits.get(cbit)
    if n == 0:
        return None, bits.get(cbit)
    tab = _canon(ptlens) if ptlens else None
    lens = []
    while len(lens) < n:
        c = _dec(bits, tab, ptsingle)
        if c <= 2:
            lens += [0] * (1 if c == 0 else (bits.get(4) + 3 if c == 1 else bits.get(cbit) + 20))
        else:
            lens.append(c - 2)
    lens += [0] * (nc - len(lens))
    return lens[:nc], None


def lh5_unpack(data, start, outlen, dicbit=13, maxmatch=256, threshold=3, cbit=9, tbit=5, nt=19, pbit=4):
    """Decode an ar002 / -lh5- bit stream starting at byte `start` until `outlen` bytes are out."""
    nc = 255 + maxmatch + 2 - threshold
    np_ = dicbit + 1
    bits = Bits(data, start)
    out = bytearray()
    while len(out) < outlen:
        size = bits.get(16)
        if size == 0:
            raise ValueError("zero block size at bit %d" % (bits.p - 16))
        tl, ts = _read_pt(bits, nt, tbit, 3)
        cl, cs = _read_c(bits, nc, cbit, tl, ts)
        pl, ps = _read_pt(bits, np_, pbit, -1)
        ctab = _canon(cl) if cl else None
        ptab = _canon(pl) if pl else None
        for _ in range(size):
            c = _dec(bits, ctab, cs)
            if c < 256:
                out.append(c)
            else:
                ln = c - 256 + threshold
                j = _dec(bits, ptab, ps)
                if j:
                    j = (1 << (j - 1)) + bits.get(j - 1)
                src = len(out) - j - 1
                if src < 0:
                    raise ValueError("match distance before start of output")
                for k in range(ln):
                    out.append(out[src + k])
            if len(out) >= outlen:
                break
    return bytes(out[:outlen])


def jm_header(data):
    if data[:2] != b"JM" or len(data) < 0x1e:
        raise ValueError("not a JM archive")
    hl, packed, flen, unpacked, ck = struct.unpack(">5I", data[2:22])
    return {"header_len": hl, "packed_len": packed, "file_len": flen, "unpacked_len": unpacked, "checksum": ck}


def jm_unpack(data):
    h = jm_header(data)
    if h["file_len"] != len(data):
        raise ValueError("file length %d, header says %d" % (len(data), h["file_len"]))
    if sum(data[0x1e:]) & 0xFFFFFFFF != h["checksum"]:
        raise ValueError("JM checksum mismatch")
    return lh5_unpack(data, 0x1e, h["unpacked_len"])


# ---------------------------------------------------------------- resource fork

def resources(fork):
    """{(type, id): bytes} of a Mac resource fork. Compressed resources are refused."""
    doff, moff, _dlen, mlen = struct.unpack(">4I", fork[:16])
    if moff + mlen > len(fork):
        raise ValueError("not a resource fork")
    m = fork[moff:moff + mlen]
    tl = struct.unpack(">H", m[24:26])[0]
    ntypes = struct.unpack(">H", m[tl:tl + 2])[0] + 1
    out = {}
    for t in range(ntypes):
        e = tl + 2 + 8 * t
        rtype = m[e:e + 4].decode("mac_roman")
        count, rl = struct.unpack(">HH", m[e + 4:e + 8])
        for r in range(count + 1):
            ref = tl + rl + 12 * r
            rid = struct.unpack(">h", m[ref:ref + 2])[0]
            attrs = m[ref + 4]
            off = doff + int.from_bytes(m[ref + 5:ref + 8], "big")
            ln = struct.unpack(">I", fork[off:off + 4])[0]
            body = fork[off + 4:off + 4 + ln]
            if attrs & 1 and body[4:8] == b"\xa8\x9f\x65\x72":
                raise ValueError("resource %s %d is dcmp-compressed (use the 7.1.2 copy)" % (rtype, rid))
            out[(rtype, rid)] = body
    return out


def _one(res, rtype, rid=None):
    hits = [k for k in res if k[0] == rtype and (rid is None or k[1] == rid)]
    if len(hits) != 1:
        raise ValueError("expected one %r resource, found %d" % (rtype, len(hits)))
    return res[hits[0]]


def load_fbit(data):
    """fbit bytes from a raw fbit resource, a resource fork or a JM archive."""
    if data[:2] == b"JM":
        data = jm_unpack(data)
    if data[2:6] == b"fbit":
        return data
    return _one(resources(data), "fbit")


def load_htbl1(data):
    if len(data) >= 16:
        try:
            return _one(resources(data), "HTBL", 1)
        except (ValueError, struct.error, IndexError):
            pass
    return data


# ---------------------------------------------------------------- fbit type 3 + HTBL 1

class Fbit3:
    def __init__(self, fbit, htbl=None):
        if fbit[2:6] != b"fbit":
            raise ValueError("not an fbit resource")
        self.fb = fbit
        self.kind = struct.unpack(">H", fbit[0x0C:0x0E])[0]
        if self.kind != 3:
            raise ValueError("fbit handler type %d, not 3" % self.kind)
        self.h = struct.unpack(">H", fbit[0x16:0x18])[0]
        self.gb = (self.h * self.h + 7) // 8
        self.base = 0x4E + 6 * struct.unpack(">H", fbit[0x4C:0x4E])[0]
        self.n = (len(fbit) - self.base) // self.gb
        self.t1 = self.t2 = b""
        if htbl is not None:
            l1 = struct.unpack(">I", htbl[:4])[0]
            # the u32 after the jamo part (0x2468 in 7.1.2) is not the length of what follows: 2,401 entries
            # follow, the 2,350 syllables and then a copy of the 51 jamo entries; only the syllables are taken
            self.t1, self.t2 = htbl[4:4 + l1], htbl[8 + l1:8 + l1 + 4 * KS_SYLLABLES]

    def glyph(self, i):
        """Rows of plane i as h-bit integers, MSB = leftmost pixel."""
        if not 0 <= i < self.n:
            raise IndexError("glyph %d of %d" % (i, self.n))
        o = self.base + i * self.gb
        v = int.from_bytes(self.fb[o:o + self.gb], "big")
        h = self.h
        return [(v >> (self.gb * 8 - h * (y + 1))) & ((1 << h) - 1) for y in range(h)]

    def entry(self, hi, lo):
        if hi == 0xA4:
            t, i = self.t1, lo - 0xA1
        elif 0xB0 <= hi <= 0xC8:
            t, i = self.t2, (hi - 0xB0) * 94 + lo - 0xA1
        else:
            return None
        if not 0 <= i or i * 4 + 4 > len(t) or not 0xA1 <= lo <= 0xFE:
            return None
        return t[i * 4:i * 4 + 4]

    def parts(self, hi, lo):
        e = self.entry(hi, lo)
        if e is None:
            return None
        return [(e[0] - 1) * BANK + g - 0x0F for g in e[1:] if g not in (0, 0x0E)]

    def compose(self, hi, lo):
        parts = self.parts(hi, lo)
        if parts is None:
            return None
        rows = [0] * self.h
        for g in parts:
            rows = [a | b for a, b in zip(rows, self.glyph(g))]
        return rows

    def codes(self):
        """(hi, lo) of every composable code: 51 jamo (A4A1..), then the 2,350 syllables."""
        out = [(0xA4, 0xA1 + i) for i in range(len(self.t1) // 4)]
        out += [(0xB0 + i // 94, 0xA1 + i % 94) for i in range(len(self.t2) // 4)]
        return out


# ---------------------------------------------------------------- output

def png_gray(path, w, h, pixels):
    """Write an 8-bit greyscale PNG; pixels is a bytearray of w*h values."""
    raw = b"".join(b"\x00" + bytes(pixels[y * w:(y + 1) * w]) for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def sheet(path, bitmaps, h, cols, scale, gap=1):
    """Grid of h x h bitmaps (lists of row ints) at `scale`, white background, `gap` px grey grid lines."""
    cell = h * scale + gap
    rows = (len(bitmaps) + cols - 1) // cols
    w, H = cols * cell + gap, rows * cell + gap
    px = bytearray([255]) * (w * H)
    for y in range(H):
        for x in range(w):
            if x % cell < gap or y % cell < gap:
                px[y * w + x] = 192
    for k, bm in enumerate(bitmaps):
        X0, Y0 = gap + (k % cols) * cell, gap + (k // cols) * cell
        for y, r in enumerate(bm):
            for x in range(h):
                if r >> (h - 1 - x) & 1:
                    for dy in range(scale):
                        o = (Y0 + y * scale + dy) * w + X0 + x * scale
                        px[o:o + scale] = b"\x00" * scale
    png_gray(path, w, H, px)
    return w, H


def write_sheets(f, prefix):
    glyphs = [f.glyph(i) for i in range(f.n)]
    syl = [f.compose(hi, lo) for hi, lo in f.codes() if hi >= 0xB0]
    out = []
    for scale in (1, 4):
        p = "%s_glyphs_x%d.png" % (prefix, scale)
        sheet(p, glyphs, f.h, 32, scale)
        out.append(p)
        p = "%s_ks2350_x%d.png" % (prefix, scale)
        sheet(p, syl, f.h, 94 if scale == 1 else 47, scale)
        out.append(p)
    return out


def write_bdf(f, name, path):
    h = f.h
    items = []
    for hi, lo in f.codes():
        ch = bytes([hi, lo]).decode("euc_kr")
        items.append((ord(ch), "%02X%02X" % (hi, lo), f.compose(hi, lo)))
    items.sort()
    rb = (h + 7) // 8
    with open(path, "w", encoding="ascii") as o:
        o.write("STARTFONT 2.1\nCOMMENT HangulTalk 7.1.2 fbit type 3, composed by HTBL 1; research only (Apple/Elex)\n")
        o.write("FONT -Apple-%s-Medium-R-Normal--%d-%d-75-75-C-%d-ISO10646-1\n" % (name, h, h * 10, h * 10))
        o.write("SIZE %d 75 75\nFONTBOUNDINGBOX %d %d 0 %d\n" % (h, h, h, -(h // 6)))
        o.write("STARTPROPERTIES 5\nFONT_ASCENT %d\nFONT_DESCENT %d\nDEFAULT_CHAR %d\n" % (h - h // 6, h // 6, items[0][0]))
        o.write('CHARSET_REGISTRY "ISO10646"\nCHARSET_ENCODING "1"\n')
        o.write("ENDPROPERTIES\nCHARS %d\n" % len(items))
        for cp, ks, rows in items:
            o.write("STARTCHAR KS%s\nENCODING %d\nSWIDTH 1000 0\nDWIDTH %d 0\nBBX %d %d 0 %d\nBITMAP\n"
                    % (ks, cp, h, h, h, -(h // 6)))
            for r in rows:
                o.write("%0*X\n" % (rb * 2, r << (rb * 8 - h)))
            o.write("ENDCHAR\n")
        o.write("ENDFONT\n")
    return len(items)


def main(argv=None):
    ap = argparse.ArgumentParser(description="HangulTalk 7.1.x fbit type 3 fonts and JM splt archives")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("unpack"); s.add_argument("splt"); s.add_argument("out")
    s = sub.add_parser("fbit"); s.add_argument("src"); s.add_argument("out")
    s = sub.add_parser("info"); s.add_argument("font"); s.add_argument("htbl", nargs="?")
    s = sub.add_parser("sheets"); s.add_argument("font"); s.add_argument("htbl"); s.add_argument("prefix")
    s = sub.add_parser("bdf"); s.add_argument("font"); s.add_argument("htbl"); s.add_argument("name"); s.add_argument("out")
    a = ap.parse_args(argv)

    def rd(p):
        with open(p, "rb") as fh:
            return fh.read()

    if a.cmd == "unpack":
        d = rd(a.splt)
        out = jm_unpack(d)
        with open(a.out, "wb") as fh:
            fh.write(out)
        print("%s: JM %d -> %d bytes" % (a.splt, len(d), len(out)))
    elif a.cmd == "fbit":
        fb = load_fbit(rd(a.src))
        with open(a.out, "wb") as fh:
            fh.write(fb)
        print("fbit %d bytes" % len(fb))
    elif a.cmd == "info":
        f = Fbit3(load_fbit(rd(a.font)), load_htbl1(rd(a.htbl)) if a.htbl else None)
        print("fbit type %d, cell %d px, %d B/glyph, glyphs at 0x%x, %d glyph planes (%d banks x %d), %d codes"
              % (f.kind, f.h, f.gb, f.base, f.n, (f.n + BANK - 1) // BANK, BANK, len(f.codes())))
    elif a.cmd == "sheets":
        f = Fbit3(load_fbit(rd(a.font)), load_htbl1(rd(a.htbl)))
        for p in write_sheets(f, a.prefix):
            print(p)
    elif a.cmd == "bdf":
        f = Fbit3(load_fbit(rd(a.font)), load_htbl1(rd(a.htbl)))
        print("%s: %d glyphs" % (a.out, write_bdf(f, a.name, a.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
