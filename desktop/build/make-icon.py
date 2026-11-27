#!/usr/bin/env python3
"""Draws desktop/build/icon.png: the Hangul jamo "ㅅ" in white on a dark square, 512x512, from the OFL Neo Dunggeunmo
font of this repository (ttf/neodgm/neodgm.ttf). Run once; the PNG is committed.

  python3 desktop/build/make-icon.py
  python3 desktop/build/make-icon.py --ico OUT.ico   # the Windows icon (16-256 px) from the committed icon.png; the
                                                     # Windows build writes desktop/build/out/icon.ico (not committed)
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "..", "..", "ttf", "neodgm", "neodgm.ttf")
OUT = os.path.join(HERE, "icon.png")
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

if sys.argv[1:2] == ["--ico"] and len(sys.argv) == 3:
    os.makedirs(os.path.dirname(os.path.abspath(sys.argv[2])), exist_ok=True)
    Image.open(OUT).convert("RGBA").save(sys.argv[2], format="ICO", sizes=ICO_SIZES)
    print("wrote", sys.argv[2], ICO_SIZES[-1])
    sys.exit(0)

img = Image.new("RGB", (512, 512), (24, 28, 40))
draw = ImageDraw.Draw(img)
font = ImageFont.truetype(FONT, 400)
draw.text((256, 256), "ㅅ", fill=(255, 255, 255), font=font, anchor="mm")
img.save(OUT, optimize=False)
print("wrote", OUT, img.size)
