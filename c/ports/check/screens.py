#!/usr/bin/env python3
"""The screen text of the emulated Pico/ESP32/CH582 panels, one place (spec "The text, per profile").

    screens.py lines BOARD PROFILE   one string a line
    screens.py shows PROFILE         how many shows the profile test makes
    screens.py --check               every line's width + x <= the panel width: "screens: OK" or the messages, exit 1

BOARD is pico, esp32c3, esp32s3 or ch582 (YD-CH582M + SH1106, mono only in practice); PROFILE colour, grey or
mono. screen_ref.py builds the reference from this data
and the profile sources carry the same strings (the host profile tests compare them)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

BOARDS = ("pico", "esp32c3", "esp32s3", "ch582")
# the screen drivers: ST7789 (big-endian words) on the Pico, esp_rgb (little-endian) on both ESP32 chips; the CH582
# board only draws the mono profile (its entries for the others are copies of the Pico text, never built)
BIGENDIAN = {"pico": 1, "esp32c3": 0, "esp32s3": 0, "ch582": 0}

_PAPLG = ["dos/PAPLG16.SVF", "dos/PAPLG18.SVF"]

PROFILES = {
    "colour": {
        "kind": "rgb565", "panel": "rgb565", "faces": _PAPLG, "missing_advance": 6, "x": 8, "h": 240, "shows": 15,
        # clear_y is data for the firmware only (the profile clears the panel in 24-row bands before drawing); the
        # reference starts from a bg-filled frame and does not read it
        "fg": 0xFFE0, "bg": 0x0010, "band_h": 24, "band_baseline": 19,
        "clear_y": list(range(0, 240, 24)), "text_y": [16, 44, 72, 100, 128],
        "w": {"pico": 240, "esp32c3": 320, "esp32s3": 320, "ch582": 240},
        "lines": {
            "pico": ["Pico ST7789 RGB565", "다람쥐 헌 쳇바퀴에 타고파!", "키스의 고유조건은 입술끼리",
                     "만나야 하고 특별한 기술은", "필요치 않다."],
            "esp32c3": ["ESP32-C3 ILI9341 RGB565", "다람쥐 헌 쳇바퀴에 타고파!", "키스의 고유조건은 입술끼리",
                        "만나야 하고 특별한 기술은", "필요치 않다."],
            "esp32s3": ["ESP32-S3 ILI9341 RGB565", "다람쥐 헌 쳇바퀴에 타고파!", "키스의 고유조건은 입술끼리",
                        "만나야 하고 특별한 기술은", "필요치 않다."],
            "ch582": ["Pico ST7789 RGB565", "다람쥐 헌 쳇바퀴에 타고파!", "키스의 고유조건은 입술끼리",
                      "만나야 하고 특별한 기술은", "필요치 않다."],
        },
    },
    "grey": {
        "kind": "gray8", "panel": "gray4panel", "faces": _PAPLG, "missing_advance": 6, "x": 4, "h": 128, "shows": 1,
        "baselines": [17, 41, 65, 89, 113],
        "w": {"pico": 128, "esp32c3": 128, "esp32s3": 128, "ch582": 128},
        "lines": {
            "pico": ["Pico GRAY8", "다람쥐 헌", "쳇바퀴에", "타고파!", "안녕하세요"],
            "esp32c3": ["ESP32 GRAY8", "다람쥐 헌", "쳇바퀴에", "타고파!", "안녕하세요"],
            "esp32s3": ["ESP32 GRAY8", "다람쥐 헌", "쳇바퀴에", "타고파!", "안녕하세요"],
            "ch582": ["Pico GRAY8", "다람쥐 헌", "쳇바퀴에", "타고파!", "안녕하세요"],
        },
    },
    "mono": {
        "kind": "mono-page", "panel": "mono-page", "faces": ["dos/NEODG16G.SVF"], "missing_advance": 0, "x": 0, "h": 64,
        "shows": 1,
        "threshold": 128, "baselines": [12, 28, 44, 60],
        "w": {"pico": 128, "esp32c3": 128, "esp32s3": 128, "ch582": 128},
        "lines": {
            "pico": ["Pico SVF 예제", "다람쥐 헌 쳇바퀴", "에 타고파! 1bpp", "안녕하세요"],
            "esp32c3": ["ESP32 SVF 예제", "다람쥐 헌 쳇바퀴", "에 타고파! 1bpp", "안녕하세요"],
            "esp32s3": ["ESP32 SVF 예제", "다람쥐 헌 쳇바퀴", "에 타고파! 1bpp", "안녕하세요"],
            "ch582": ["CH582 SVF 예제", "다람쥐 헌 쳇바퀴", "에 타고파! 1bpp", "안녕하세요"],
        },
    },
}


def lines(board, profile):
    return list(PROFILES[profile]["lines"][board])


def shows(profile):
    return PROFILES[profile]["shows"]


def panel_kind(profile):
    """The kind of the profile's panel memory, the one name every compare and PNG uses: rgb565, gray4panel (the
    SSD1327's two pixels a byte; the profile's own "kind" gray8 is one byte a pixel) or mono-page."""
    return PROFILES[profile]["panel"]


def face_paths(profile, table=None):
    """Absolute paths of the face chain of @p profile in @p table (default PROFILES)."""
    return [os.path.join(ROOT, "svf", f) for f in (PROFILES if table is None else table)[profile]["faces"]]


def check(profiles=None):
    """Messages for every rule a table breaks; [] when it is sound. Rules, per board and line: as many lines as
    positions (text_y for a profile with bands, else baselines); width + x <= panel width; the ascent fits above the
    baseline (band_baseline for bands) and the descent below it (inside the panel, or the band); and every band lies
    inside the panel (text_y + band_h <= h)."""
    import svfline
    table = PROFILES if profiles is None else profiles
    out = []
    for profile, p in table.items():
        banded = "text_y" in p
        rows = p["text_y"] if banded else p["baselines"]
        if banded:
            out += ["screens: %s text_y %d + band_h %d > %d" % (profile, y, p["band_h"], p["h"])
                    for y in rows if y + p["band_h"] > p["h"]]
        for board in BOARDS:
            w, texts = p["w"][board], p["lines"][board]
            if len(texts) != len(rows):
                out.append("screens: %s/%s has %d lines for %d positions" % (board, profile, len(texts), len(rows)))
            for i, text in enumerate(texts):
                width, ascent, descent = svfline.measure(face_paths(profile, table), text,
                                                         missing_advance=p["missing_advance"])
                tag = "screens: %s/%s %r" % (board, profile, text)
                if width + p["x"] > w:
                    out.append("%s is %d px + x %d > %d" % (tag, width, p["x"], w))
                base, limit = (p["band_baseline"], p["band_h"]) if banded else \
                    (p["baselines"][i] if i < len(rows) else 0, p["h"])
                if ascent > base:
                    out.append("%s ascent %d above baseline %d is clipped" % (tag, ascent, base))
                if base + descent > limit:
                    out.append("%s descent %d from baseline %d passes %d" % (tag, descent, base, limit))
    return out


def main(argv):
    if argv == ["--check"]:
        msgs = check()
        print("\n".join(msgs) if msgs else "screens: OK")
        return 1 if msgs else 0
    if len(argv) == 3 and argv[0] == "lines" and argv[1] in BOARDS and argv[2] in PROFILES:
        print("\n".join(lines(argv[1], argv[2])))
        return 0
    if len(argv) == 2 and argv[0] == "shows" and argv[1] in PROFILES:
        print(shows(argv[1]))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
