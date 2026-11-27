#!/usr/bin/env python3
"""fetch-fribidi-win.py OUTDIR: the FriBiDi DLL Pillow's Windows wheel needs for its raqm layout (t_9b8f56f0).

Pillow's win_amd64 wheel carries libraqm and HarfBuzz but loads FriBiDi at run time (`fribidi`, `fribidi-0` or
`libfribidi-0`); without it Pillow falls back to its basic layout, which draws some characters differently from Linux
(a mark's advance, U+00AD, a glyph a font substitutes through `ccmp`), so a face made on Windows would not be the bytes
the same face made on Linux is. This script downloads conda-forge's MSVC build of FriBiDi 1.0.10 (the archive pinned below,
sha256 checked), and writes `fribidi-0.dll` and its licence `COPYING` (LGPL-2.1-or-later) into OUTDIR, each checked by
sha256. The Windows build bundles the DLL beside the sidecar's libraries; the Windows test runs put OUTDIR on PATH.
Prints `fribidi <version> -> OUTDIR`. Network: this one download (the build's only one besides pip and npm).
"""

import hashlib
import io
import os
import sys
import tarfile
import urllib.request

VERSION = "1.0.10"
URL = "https://conda.anaconda.org/conda-forge/win-64/fribidi-1.0.10-h8d14728_0.tar.bz2"
ARCHIVE_SHA256 = "e0323e6d7b6047042970812ee810c6b1e1a11a3af4025db26d0965ae5d206104"
MEMBERS = {   # member -> (written as, sha256)
    "Library/bin/fribidi-0.dll": ("fribidi-0.dll", "c351547238bcd32877130e53b3b31ce51d14a9c8a8d5436c6dd2c656d4625acd"),
    "info/licenses/COPYING": ("COPYING", "32434afcc8666ba060e111d715bfdb6c2d5dd8a35fa4d3ab8ad67d8f850d2f2b"),
}
SOURCE = "https://github.com/fribidi/fribidi/releases/tag/v1.0.10"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main(argv):
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    out = os.path.abspath(argv[0])
    os.makedirs(out, exist_ok=True)
    have = {name: os.path.join(out, name) for name, _ in MEMBERS.values()}
    if all(os.path.isfile(p) for p in have.values()):
        ok = True
        for name, digest in MEMBERS.values():
            with open(have[name], "rb") as f:
                ok = ok and sha256(f.read()) == digest
        if ok:
            print("fribidi %s -> %s (cached)" % (VERSION, out))
            return 0
    with urllib.request.urlopen(URL, timeout=120) as r:
        data = r.read()
    if sha256(data) != ARCHIVE_SHA256:
        print("fetch-fribidi-win: %s: sha256 %s, want %s" % (URL, sha256(data), ARCHIVE_SHA256), file=sys.stderr)
        return 1
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:bz2") as t:
        for member, (name, digest) in MEMBERS.items():
            body = t.extractfile(member).read()
            if sha256(body) != digest:
                print("fetch-fribidi-win: %s: sha256 %s, want %s" % (member, sha256(body), digest), file=sys.stderr)
                return 1
            with open(os.path.join(out, name), "wb") as f:
                f.write(body)
    print("fribidi %s -> %s" % (VERSION, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
