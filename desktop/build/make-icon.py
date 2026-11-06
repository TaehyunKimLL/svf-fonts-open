#!/usr/bin/env python3
"""Draws desktop/build/icon.png: the Hangul jamo "ㅅ" in white on a dark square, 512x512, from the OFL Neo Dunggeunmo
font of this repository (ttf/neodgm/neodgm.ttf). Run once; the PNG is committed.

  python3 desktop/build/make-icon.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "..", "..", "ttf", "neodgm", "neodgm.ttf")
OUT = os.path.join(HERE, "icon.png")

img = Image.new("RGB", (512, 512), (24, 28, 40))
draw = ImageDraw.Draw(img)
font = ImageFont.truetype(FONT, 400)
draw.text((256, 256), "ㅅ", fill=(255, 255, 255), font=font, anchor="mm")
img.save(OUT, optimize=False)
print("wrote", OUT, img.size)
