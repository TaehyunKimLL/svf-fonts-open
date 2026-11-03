#!/usr/bin/env python3
"""The reference panel memory of the emulated screens, built with tools/svfline.py from screens.py.

    screen_ref.py [--ref-only [--gray8]] [--bigendian 0|1] BOARD PROFILE OUT

Writes OUT/<board>-<profile>.ref and -ref.png. Unless --ref-only, reads OUT/<board>-<profile>.fb, compares it byte for
byte, writes OUT/<board>-<profile>.png and, on a difference, -diff.png; prints "screen-<board>-<profile>: OK" or
"differs at byte N (x X, y Y)" (exit 1).

A .fb of the wrong size is a difference too: "differs: .fb is N bytes, expected M" (at most M + 1 bytes are read),
with the .png and a -diff.png (bytes missing from a short .fb shown red; for a longer one a red border).

When OUT/<board>-<profile>.ppm exists (colour, a QEMU screendump) the PNG is not written here: the runner's PNG, made
from that PPM, wins. The PPM is then compared with the reference too, with each 5/6/5 channel replicated to 8 bits
("ppm differs at x X, y Y", "ppm differs: <mode/size>"). Precondition: that compare runs only once the .fb equals the
reference byte for byte, so the PPM is judged against a reference the panel memory has already confirmed; a .fb
mismatch is reported first and the PPM is not looked at.

--gray8 (with --ref-only, grey only) writes the unpacked 128 x 128 GRAY8 frame (16,384 bytes) to
OUT/<board>-grey.gray8.ref instead of the packed panel memory in <board>-grey.ref.
Panel memory: mono 1,024 bytes (SSD1306 pages), grey 8,192 (SSD1327, two pixels a byte), colour
w * 240 * 2 (RGB565, byte order --bigendian, default the board's driver)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "tools")))

import svfline  # noqa: E402
import screens  # noqa: E402


def _places(profile, board, i, baseline):
    p = screens.PROFILES[profile]
    chain = svfline.load_chain(screens.face_paths(profile))
    return svfline.placements(chain, screens.lines(board, profile)[i], p["x"], baseline,
                              missing_advance=p["missing_advance"])


def build_gray8(board):
    """The grey profile's unpacked 128 x 128 GRAY8 frame (bytes)."""
    p = screens.PROFILES["grey"]
    t = svfline.Target("gray8", p["w"][board], p["h"])
    for i, base in enumerate(p["baselines"]):
        svfline.draw_target(_places("grey", board, i, base), t)
    return bytes(t.buf)


def pack_gray8(gray, w, h):
    """GRAY8 rows packed to w / 2 bytes a row, the left pixel in the high nibble, level = coverage >> 4."""
    if w < 2 or w % 2 or h < 0 or len(gray) != w * h:
        raise ValueError("pack_gray8: w %d must be even and >= 2, h %d >= 0, and %d bytes must be w * h" %
                         (w, h, len(gray)))
    out = bytearray()
    for r in range(h):
        row = gray[r * w:(r + 1) * w]
        for x in range(0, w, 2):
            out.append((row[x] & 0xF0) | (row[x + 1] >> 4))
    return bytes(out)


def build_ref(board, profile, bigendian=None):
    """The expected panel memory of @p profile on @p board (bytes)."""
    p = screens.PROFILES[profile]
    if profile == "mono":
        t = svfline.Target("mono-page", p["w"][board], p["h"], threshold=p["threshold"])
        for i, base in enumerate(p["baselines"]):
            svfline.draw_target(_places(profile, board, i, base), t)
        return bytes(t.buf)
    if profile == "grey":
        return pack_gray8(build_gray8(board), p["w"][board], p["h"])
    be = screens.BIGENDIAN[board] if bigendian is None else bigendian
    w, bh = p["w"][board], p["band_h"]
    order = "big" if be else "little"
    frame = bytearray(p["bg"].to_bytes(2, order) * (w * p["h"]))
    for i, y in enumerate(p["text_y"]):
        band = svfline.Target("rgb565", w, bh, fg565=p["fg"], bg565=p["bg"], big_endian=bool(be))
        band.buf[:] = p["bg"].to_bytes(2, order) * (w * bh)
        svfline.draw_target(_places(profile, board, i, p["band_baseline"]), band)
        frame[y * w * 2:(y + bh) * w * 2] = band.buf
    return bytes(frame)


PANEL_KINDS = ("mono-page", "gray4panel", "rgb565")


def geometry(board, profile):
    """(panel kind, w, h) of the panel memory; the kind is screens.panel_kind(profile): "mono-page", "rgb565" or
    "gray4panel" (the SSD1327's two pixels a byte; the profile's own kind "gray8" is one byte a pixel and is the
    --gray8 file)."""
    p = screens.PROFILES[profile]
    return screens.panel_kind(profile), p["w"][board], p["h"]


def _check_kind(who, kind):
    if kind not in PANEL_KINDS:
        hint = " (the panel kind of a gray8 profile is gray4panel: screens.panel_kind)" if kind == "gray8" else ""
        raise ValueError("%s: unknown panel kind %r, use mono-page, gray4panel or rgb565%s" % (who, kind, hint))


def _pixel_rows(kind, w, h, data, bigendian=0):
    """Rows of (r, g, b) or grey 8-bit values: mono bits and grey nibbles expanded, 5/6/5 replicated."""
    if kind == "mono-page":
        return [[255 if data[(y >> 3) * w + x] >> (y & 7) & 1 else 0 for x in range(w)] for y in range(h)]
    if kind == "gray4panel":
        return [[(data[y * (w // 2) + x // 2] >> (4 if x % 2 == 0 else 0) & 15) * 17 for x in range(w)]
                for y in range(h)]
    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            i = 2 * (y * w + x)
            v = int.from_bytes(data[i:i + 2], "big" if bigendian else "little")
            r, g, b = v >> 11, v >> 5 & 63, v & 31
            row.append((r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2))
        rows.append(row)
    return rows


def to_png(kind, w, h, data, bigendian=0):
    """A Pillow image of the panel memory @p data (mono-page, gray4panel = packed nibbles, rgb565)."""
    from PIL import Image
    _check_kind("to_png", kind)
    row = {"mono-page": w, "gray4panel": w // 2, "rgb565": 2 * w}[kind]
    rows_n = h // 8 if kind == "mono-page" else h
    if w < 2 or (kind == "gray4panel" and w % 2) or h < 1 or (kind == "mono-page" and h % 8) or \
            len(data) != row * rows_n:
        raise ValueError("to_png: %s of %d x %d pixels is %d bytes, not %d" % (kind, w, h, row * rows_n, len(data)))
    rows = _pixel_rows(kind, w, h, data, bigendian)
    img = Image.new("RGB" if kind == "rgb565" else "L", (w, h))
    img.putdata([v for row in rows for v in row])
    return img


def compare(ref, fb, kind, w):
    """None when equal, else (offset, x, y) of the first differing byte (a mono byte is one column of an 8-row page;
    a gray4panel byte holds two pixels, x is the left one). Takes panel memory (kind mono-page, gray4panel, rgb565),
    two buffers of the same whole-row size; anything else is a ValueError. Precondition: len(ref) == len(fb) (the CLI
    reports a size mismatch itself before calling this; a PPM compare must do the same)."""
    _check_kind("compare", kind)
    row = {"mono-page": w, "gray4panel": w // 2, "rgb565": 2 * w}[kind]
    if w < 2 or (kind == "gray4panel" and w % 2) or len(ref) != len(fb) or not ref or len(ref) % row:
        raise ValueError("compare: %s buffers of %d and %d bytes are not whole rows of width %d" %
                         (kind, len(ref), len(fb), w))
    for off in range(len(ref)):
        if ref[off] != fb[off]:
            break
    else:
        return None
    if kind == "mono-page":
        return off, off % w, off // w * 8
    if kind == "gray4panel":
        return off, off % (w // 2) * 2, off // (w // 2)
    return off, off // 2 % w, off // 2 // w


def compare_ppm(path, ref, w, h, bigendian):
    """None when the QEMU screendump @p path is the reference with each 5/6/5 channel replicated to 8 bits
    (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2), else a message "ppm differs ..." (Pillow parses the file)."""
    from PIL import Image
    try:
        with Image.open(path) as img:
            if img.mode != "RGB" or img.size != (w, h):  # before load(): a header can claim any size
                return "ppm differs: %s %d x %d, expected RGB %d x %d" % (img.mode, img.size[0], img.size[1], w, h)
            img.load()
            got = img.tobytes()
    except (OSError, ValueError, Image.DecompressionBombError) as e:
        return "ppm differs: unreadable (%s)" % e
    want = bytes(c for row in _pixel_rows("rgb565", w, h, ref, bigendian) for px in row for c in px)
    if got == want:
        return None
    i = next(k for k in range(len(want)) if got[k] != want[k]) // 3
    return "ppm differs at x %d, y %d" % (i % w, i // w)


def _diff_png(kind, w, h, ref, fb, bigendian):
    from PIL import Image
    fb_all = fb
    n = min(len(ref), len(fb))  # bytes past the shorter buffer differ by construction: show them as wrong
    fb = fb[:n] + bytes(b ^ 0xFF for b in ref[n:])
    a, b = _pixel_rows(kind, w, h, ref, bigendian), _pixel_rows(kind, w, h, fb, bigendian)
    img = Image.new("RGB", (w, h))
    img.putdata([(255, 0, 0) if pa != pb else ((pb, pb, pb) if isinstance(pb, int) else pb)
                 for ra, rb in zip(a, b) for pa, pb in zip(ra, rb)])
    if len(fb_all) > len(ref):  # the extra bytes have no pixel: a red border says so
        for x in range(w):
            img.putpixel((x, 0), (255, 0, 0))
            img.putpixel((x, h - 1), (255, 0, 0))
        for y in range(h):
            img.putpixel((0, y), (255, 0, 0))
            img.putpixel((w - 1, y), (255, 0, 0))
    return img


def main(argv):
    ref_only = gray8 = False
    be = None
    args = list(argv)
    while args and args[0].startswith("--"):
        o = args.pop(0)
        if o == "--ref-only":
            ref_only = True
        elif o == "--gray8":
            gray8 = True
        elif o == "--bigendian" and args and args[0] in ("0", "1"):
            be = int(args.pop(0))
        else:
            print(__doc__, file=sys.stderr)
            return 2
    if len(args) != 3 or args[0] not in screens.BOARDS or args[1] not in screens.PROFILES:
        print(__doc__, file=sys.stderr)
        return 2
    if gray8 and not (ref_only and args[1] == "grey"):
        print("screen_ref: --gray8 needs --ref-only and the grey profile", file=sys.stderr)
        return 2
    board, profile, out = args
    base = os.path.join(out, "%s-%s" % (board, profile))
    kind, w, h = geometry(board, profile)
    bige = screens.BIGENDIAN[board] if be is None else be
    ref = build_ref(board, profile, be)
    os.makedirs(out, exist_ok=True)
    with open(base + (".gray8.ref" if gray8 else ".ref"), "wb") as f:
        f.write(build_gray8(board) if gray8 else ref)
    to_png(kind, w, h, ref, bige).save(base + "-ref.png")
    if ref_only:
        return 0
    try:
        size = os.path.getsize(base + ".fb")
        with open(base + ".fb", "rb") as f:
            fb = f.read(len(ref) + 1)  # never more: a longer file is a size mismatch, reported from its stat size
    except OSError as e:
        print("screen_ref: cannot read %s: %s" % (base + ".fb", e.strerror), file=sys.stderr)
        return 2
    if not os.path.exists(base + ".ppm"):
        to_png(kind, w, h, fb[:len(ref)] + bytes(max(0, len(ref) - len(fb))), bige).save(base + ".png")
    diff = base + "-diff.png"
    if size != len(ref):
        _diff_png(kind, w, h, ref, fb, bige).save(diff)
        print("screen-%s-%s: differs: .fb is %d bytes, expected %d" % (board, profile, size, len(ref)))
        return 1
    d = compare(ref, fb, kind, w)
    if d is None and kind == "rgb565" and os.path.exists(base + ".ppm"):
        bad = compare_ppm(base + ".ppm", ref, w, h, bige)
        if bad:
            print("screen-%s-%s: %s" % (board, profile, bad))
            return 1
    if d is None:
        if os.path.exists(diff):
            os.remove(diff)
        print("screen-%s-%s: OK" % (board, profile))
        return 0
    _diff_png(kind, w, h, ref, fb, bige).save(diff)
    print("screen-%s-%s: differs at byte %d (x %d, y %d)" % (board, profile, d[0], d[1], d[2]))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
