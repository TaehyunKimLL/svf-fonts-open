# SDL2 / SDL3 target for the C renderer (`c/ports/sdl`): design

Card t_02418f83 (svf-fonts), 2026-10-24, written on branch `sdl-target` from main e5232ca (SVF v3, the C speedups
6-11 with `SVF_SMALL`, the CH582M port). Written from `c/include/svf.h`, `c/src/svf_draw.c`, the ports `c/ports/dos`
(`svfvesa.c`, `vesa_lines.c`, `vesa-lines.txt`, `vesa-shots.sh`, `vesa_check.py`), `c/ports/web`, `c/ports/pico`,
`c/ports/esp32`, `c/ports/ch582`, `c/cross/build-all.sh` (`--ports`), `c/cross/SIZES.md` ("Port examples"),
`c/check.sh`, `c/Makefile`, `tools/svfline.py`, `tools/vesa_lines.py`, `tools/test_c_renderer.py`,
`spec/renderer-design.md`, the VESA design (`2026-10-20-vesa-packed-kinds-design.md`) and cards t_02418f83 and
t_5a7bcd78. Every fact about SDL below marked *measured* was checked on this host today with the programs in
"What was checked on this host". Choices the user and the card did not make are marked **my call**. A plan follows
this document; nothing here is implemented.

## Intent

The C renderer draws Korean and ASCII lines into packed pixel buffers: RGB565, RGB555, XRGB8888 and RGB888 since the
VESA card. SDL is where such buffers live on a desktop: an `SDL_Surface` (a window's back buffer, or one the program
owns) and a streaming `SDL_Texture`. The user wants a port that draws into those through the existing target kinds,
with **both SDL majors from one source**, and proves, headlessly, that the bytes in the SDL buffer are the bytes
`tools/svfline.py` gives. Beyond being an example, it is the step before the ScummVM card (t_5a7bcd78, "ScummVM
hires_text uses the svf-fonts C renderer"): ScummVM runs on SDL2 and SDL3 from one source already (139
`SDL_VERSION_ATLEAST(3, 0, 0)` sites in `backends/`), its screen is an SDL surface or an RGB565 texture, and the SDL
port is where the library first meets SDL-allocated pitches, SDL's pixel-format names and an SDL build with `-Werror`.
What the port proves and provides for that card is listed in its own section; no ScummVM work is designed here.

## Goals

1. `c/ports/sdl/` builds against SDL2 (the host's 2.30.0) and SDL3 (built from source into `~/opt`, below) from **one
   `svfsdl.c`** and a compat header of macros and static inline functions, `-std=c99 -Wall -Wextra -Werror -O2`, the
   library sources unchanged.
2. It draws the lines of a table (the `vesa-lines.txt` format, parser shared with the DOS port) into an SDL surface of
   the pixel format asked for, through the matching `svf_target` kind, and shows it in a window (presented through
   the window surface or through a streaming texture, the user's choice on the command line).
3. **Byte-identity, headless:** with `SDL_VIDEODRIVER=dummy` the program dumps the surface's bytes; a checker rebuilds
   the same buffer with `tools/svfline.py` (stride = the SDL pitch) and compares every byte, for every mapped kind,
   under SDL2 and under SDL3, with the faces mapped and with the faces streamed. One script, `c/ports/sdl/check.sh`,
   runs it all and prints `port-sdl: OK ...`; `c/cross/build-all.sh --ports` runs that script.
4. `make -C c check` stays green (nothing in `c/src`, `c/tests` or `tools/test_c_renderer.py` changes; the SDL check is
   outside it, like the DOS captures).
5. **The parametric GRAY kind in the library first** (`SVF_T_GRAY`, bits 1/2/4/8, bit order, the one level rule,
   byte-identical to `svfline.py`, behind `SVF_TARGET_GRAY`, MCU profiles without it unchanged, bits 8 as fast as
   GRAY8), then its SDL formats.
6. A README with build and run lines for SDL2 and SDL3 (and how to get SDL3 without root), the format table, the
   check, and screenshots: SDL2 and SDL3, each at XRGB8888, ARGB8888, RGB565, INDEX8 and GRAY (4 bits), checked by eye by the user.

## Non-goals

- **No new target kind in the library beyond the parametric `SVF_T_GRAY`** the user asked for (its own section), in
  particular no kind that writes coverage as an alpha channel (text over an unknown background). `svfline.py` has no rule for it, so there is nothing to be byte-identical to; see "ARGB8888"
  below for what the port does instead, in the port.
- No change to `c/src`, `c/include/svf.h`, `tools/svfline.py` or the reference rules **other than the GRAY task**
  (one kind, one field, one flag, one bit, its reference rule and tests). If the port finds a library defect, that is a finding for its own card (or folded into the next task's dispatch), not a change here.
- No SDL 1.2, no Emscripten-SDL build (the web port exists), no SDL_ttf, no font picker UI, no HiDPI handling, no
  text input, no audio or events beyond "a key or the close button ends the program".
- No Windows or macOS verification. The code avoids platform-specific calls so it should build there; only Linux is
  run.
- No speed claims. The program prints the draw time of one frame as information, nothing is budgeted or gated.
- No MCU size budget: the port is a desktop program, it is not in the `SIZES.md` port rows gate (below).
- No drawing straight into a locked texture as the proven path (it is offered as a demonstration mode only, below).

## Anti-goals (a failure even if it works)

- Any byte in the dumped surface that differs from `svfline.py` for the same kind, on either SDL, mapped or streamed.
- A "proof" that reads pixels back from the renderer (`SDL_RenderReadPixels`) instead of the buffer the library wrote:
  the renderer converts; the identity claim is about the library's bytes.
- A compat layer that grows into an abstraction (a struct of function pointers, a second event loop): it is a short
  header of `#if SDL_VERSION_ATLEAST(3, 0, 0)` macros, and nothing outside it mentions an SDL version.
- Copies of library sources, or an `#if` on SDL anywhere in `c/src`.
- A padding byte of an SDL row (pitch past `w * bytes`) written by the library, or a dump that trims rows so such a
  write would go unseen.
- A byte-order assumption that is only true on little-endian x86 without saying so (the endian rule below).

## Already decided (by the card and the user)

- One source, a thin compat layer, both SDL majors (card).
- The kinds are the ones matching SDL pixel formats: XRGB8888, ARGB8888 and RGB565 (card).
- Output byte-identical to `tools/svfline.py` for the same kind under both SDL versions, proven with the headless
  dummy video driver (card). Exact by default; the renderer's output is byte-identical (user's accuracy policy).
- `make -C c check` green, a README with build/run for SDL2 and SDL3, screenshots checked by eye (card).
- The port is done before the ScummVM card, which also waits for it (user, 2026-10-22).
- Not for dispatcher workers: Claude main builds it (user, 2026-10-21).
- **The SDL3 the gate pins is the user's own fork at `~/opt/src/SDL3`** (3.5.0-dev with the DOS commits), not an
  upstream 3.2.x tarball: `install-toolchains.sh` builds that tree into `~/opt/sdl3`, records the fork commit it was
  built from, with `-DSDL_X11_XTEST=OFF` (user, 2026-10-24, builder-check answer 1).
- The two extra kinds stay: RGB555 via `XRGB1555`, RGB888 via `BGR24`, headless check only, no screenshots (user,
  2026-10-24, answer 2).
- `--alpha-demo` stays (user, 2026-10-24, answer 3).
- **CLUT8 (8-bit palettised, `SDL_PIXELFORMAT_INDEX8`) must be supported, at least for 1 bpp faces** ("CLUT8도 최소
  1bpp는 지원해야 함", user, 2026-10-25): mapped to the library's `SVF_T_INDEXED8`, the section "INDEX8 (CLUT8)" below.
- **AA faces (2 bpp and higher) must be drawable onto 1-bit outputs at a given threshold** ("4bpp 등의 AA 폰트도
  쓰레시홀드 주고 1bpp 처리 가능해야 함", user, 2026-10-25): the existing per-target `mono_threshold`, exposed as
  `--threshold`; no library change (the INDEX8 section says what the library does today).
- **Grey output is one parametric kind** (bits 1/2/4/8 and bit order as parameters, one level rule; user,
  2026-10-25, after weighing separate kinds and driver-side packing): `SVF_T_GRAY`, a library task that opens this
  plan and subsumes the kind part of card t_8e7da3c1 (the section "The parametric GRAY kind"); the SDL port shows it
  on `INDEX1/2/4/8` surfaces.

## What was checked on this host (measured, 2026-10-24)

- **SDL2** 2.30.0 (`libsdl2-dev`, `pkg-config sdl2`). `SDL_VIDEODRIVER=dummy`: `SDL_Init(VIDEO)` succeeds, a window's
  surface is `SDL_PIXELFORMAT_RGB888` (= `SDL_PIXELFORMAT_XRGB8888`, the same value; pitch 4 x width), the software
  renderer exists and lists ARGB8888, ABGR8888, RGBA8888, BGRA8888, RGB888, BGR888, RGB565, RGB555; a streaming
  ARGB8888 texture locks with pitch 252 for 63 px. `SDL_CreateRGBSurfaceWithFormat` gives **pitch rounded up to 4
  bytes**: 63 px wide is 252 (XRGB8888, ARGB8888), 128 (RGB565, XRGB1555: 126 rounded), 192 (RGB24: 189 rounded).
- **SDL3** is not packaged on this host. It was built from the local tree `~/opt/src/SDL3` (upstream plus the user's
  DOS commits; `SDL_version.h` says 3.5.0, HEAD 7a588ba) into `~/opt/sdl3-host` with
  `cmake -DCMAKE_BUILD_TYPE=Release -DSDL_SHARED=ON -DSDL_STATIC=ON -DSDL_TESTS=OFF -DSDL_EXAMPLES=OFF -DSDL_AUDIO=OFF
  -DSDL_JOYSTICK=OFF -DSDL_HAPTIC=OFF -DSDL_CAMERA=OFF -DSDL_SENSOR=OFF -DSDL_GPU=OFF -DSDL_WAYLAND=OFF
  -DSDL_X11_XTEST=OFF` (the first attempt failed: `libxtst-dev` is not installed and X11 XTEST is on by default; the
  switch is the whole fix, no root needed), in a few minutes. With `PKG_CONFIG_PATH=~/opt/sdl3-host/lib/pkgconfig`,
  `pkg-config sdl3` works. Under the dummy driver (`SDL_VIDEO_DRIVER=dummy`, and the SDL2 name `SDL_VIDEODRIVER=dummy`
  is accepted too, measured): the window surface is `SDL_PIXELFORMAT_XRGB8888`, the software renderer lists only
  XRGB8888, ARGB8888 and INDEX8 as texture formats, yet `SDL_CreateTexture(RGB565, STREAMING)` succeeds and locks with
  pitch 128 for 63 px (SDL converts at unlock: this is why a locked texture is not the proven path). `SDL_CreateSurface`
  pitches are the same 4-byte rounding as SDL2 (252 / 128 / 192 for 63 px).
- `xvfb-run` and `ffmpeg` are installed (the DOS captures use them); the X11 video driver is built into both SDLs.
- Python: `tools/svfline.py Target(kind, w, h, stride=..., buf=...)` takes any stride, so the checker needs no change
  to the reference. PIL is installed (`vesa_check.py` uses it).

## Format table: SDL pixel format <-> `svf_target` kind

The port names SDL formats by **memory byte order**, using SDL's array-order aliases where one exists, because the
library's kinds are defined in memory order (`svf.h`: XRGB8888 is "memory B G R X", RGB888 "memory B G R") while
SDL's packed names are native-endian.

| port name (`--format`) | SDL format requested | memory order | `svf_target_kind` | `svf_target` fields | bytes |
|---|---|---|---|---|---:|
| `xrgb8888` | `SDL_PIXELFORMAT_BGRX32` (= `XRGB8888` on little-endian) | B G R X | `SVF_T_XRGB8888` | `fg888 = 0x00RRGGBB`, `bg888 = 0x00RRGGBB`; X written 0 | 4 |
| `argb8888` | `SDL_PIXELFORMAT_BGRA32` (= `ARGB8888` on little-endian) | B G R A | `SVF_T_XRGB8888` | `fg888 = 0xFFRRGGBB` (bits 31..24 are the byte the kind writes at X: alpha 255), `bg888 = 0x00RRGGBB`; the clear pixel has A = 0xFF too | 4 |
| `rgb565` | `SDL_PIXELFORMAT_RGB565` (packed16, native endian) | low byte first on LE | `SVF_T_RGB565` | `fg565`, `bg565`; `flags |= SVF_TF_RGB16_BIGENDIAN` when `SDL_BYTEORDER == SDL_BIG_ENDIAN` | 2 |
| `rgb555` (extra) | `SDL_PIXELFORMAT_XRGB1555` | as above | `SVF_T_RGB555` | `fg565 = 0x7FFF`-masked 5/5/5 (bit 15 clear), same endian rule | 2 |
| `bgr24` (extra) | `SDL_PIXELFORMAT_BGR24` (array order) | B G R | `SVF_T_RGB888` | `fg888`, `bg888` | 3 |
| `index8` (CLUT8; user, 2026-10-25) | `SDL_PIXELFORMAT_INDEX8` with a 256-entry palette | one index | `SVF_T_INDEXED8` | `index_base`, `index_levels` (1 = one ink index, thresholded; 3 = a 2 bpp ramp), `mono_threshold` | 1 |
| `gray` with `--gray-bits 8/4/2/1` (user, 2026-10-25; **new parametric library kind**, the section "The parametric GRAY kind") | `SDL_PIXELFORMAT_INDEX8` / `INDEX4MSB` / `INDEX2MSB` / `INDEX1MSB` (or the `LSB` ones with `--lsb-first`), a grey palette of 2^bits entries; every one creates, takes a palette and blits on SDL2 and SDL3 (INDEX4 and INDEX8 measured, INDEX1/2 exist in both headers) | 8/2/4/1 pixels a byte, first pixel in the high bits by default | `SVF_T_GRAY` (to be added) | `gray_bits`, `flags` bit `SVF_TF_GRAY_LSB_FIRST`, `mono_threshold` for bits 1 | 1, 1/2, 1/4, 1/8 |

- The three kinds the card names are required; `rgb555` and `bgr24` are kept by the user's decision (2026-10-24):
  they cost one table row each, go through the same checker and complete the "every packed kind of the library has
  an SDL home" statement. They get the headless identity check but no screenshot.
- `SDL_PIXELFORMAT_RGB24` (memory R G B) has **no** matching kind and is not offered; the README says so, so nobody
  maps it to `SVF_T_RGB888` by the name.
- On a big-endian host the 32-bit rows are still right (array-order aliases), the 16-bit kinds take the endian flag,
  so the table holds everywhere; only little-endian is run. In SDL2 the array-order aliases exist since 2.0.5 and
  `SDL_PIXELFORMAT_XRGB8888` since 2.0.14; the compat header defines the latter from `RGB888` if missing, but the
  INDEX2 formats of the 1 and 2 bit GRAY targets exist only since SDL 2.30.0, so that is the real minimum (`sdl_compat.h` refuses an older SDL2 with an `#error`).
- After `svf_target_init` the port checks that the SDL format of the surface it got is the one it asked for
  (`SDL_CreateSurface` with a format cannot substitute, a window surface can): a mismatch is an error, never a silent
  conversion.

### ARGB8888: alpha, blending, premultiplication

- The library's XRGB8888 kind writes bits 31..24 of `fg888` as the fourth byte and blends the colour channels against
  `bg888`, never reading the destination. For an opaque ARGB8888 surface that is exactly right: `fg888 = 0xFF000000
  | rgb`, every drawn pixel is alpha 255, the surface is cleared to `0xFF000000 | bg`, and the surface is blitted or
  uploaded with `SDL_BLENDMODE_NONE`. Premultiplication does not arise (alpha is 255 everywhere), and the reference's
  rule (`svfline.Target.put` xrgb8888: `px + bytes((fg888 >> 24 & 255,))`) covers it byte for byte.
- Text with coverage as alpha (anti-aliased text composited by SDL over whatever is behind it) is **not a library
  kind** (non-goal). The port shows the way that is done in an application, in a separate, clearly-labelled mode
  `--alpha-demo` (kept by the user's decision, 2026-10-24; small): one line is drawn with `SVF_T_GRAY8` into a coverage buffer, the port converts
  coverage `c` to `SDL_PIXELFORMAT_BGRA32` pixels `(B, G, R, A) = (b, g, r, c)` (straight alpha) and blits with
  `SDL_BLENDMODE_BLEND` over a colour gradient. SDL composites; no byte-identity claim is made for the composite, only
  the GRAY8 buffer is checked (the existing GRAY8 identity in `test_c_renderer.py` already covers that kind, so the
  checker compares the port's dump of that buffer against `svfline.layout`). This is the shape ScummVM's
  `coverageToArgb` has today (`graphics/hires_text/text_compose.cpp`), which is why it is shown. Premultiplied alpha
  (`SDL_BLENDMODE_BLEND_PREMULTIPLIED`, SDL 2.0.12+ / SDL3) is mentioned in the README as the alternative the
  application would pick; not demonstrated.

### INDEX8 (CLUT8): the palettised surface, and AA faces thresholded to one bit

**What the library does today (checked in `svf.h`, `c/src/svf_draw.c` 423, 634, 952-1053 and
`tools/svfline.py index_level`):** `SVF_T_INDEXED8` writes one byte a pixel. With `n = index_levels` and
`b = index_base`, a pixel of coverage `cov` gets level `L = (cov * n + 127) / 255` for `n >= 2` (`n = 3` maps the
2 bpp levels 85/170/255 to 1/2/3 exactly; `n = 255` is the coverage itself); for **`n = 1` it is 1 when
`cov >= mono_threshold` (0 counting as 1), else 0** — the same rule as the mono kinds `MONO_PAGE` and `MONO_ROW`.
`L = 0` leaves the pixel untouched (the background index is never written); otherwise the pixel becomes
`max(existing, b + L)`. The threshold is a **per-target field**, `svf_target.mono_threshold`, `svf_target_init` sets it
to 128, and it is applied in the blit, **after composition** (a syllable's cell is the maximum of its pieces before
any target sees it: `svf_compose`), so jamo composition is unchanged by it. There is no refusal and no fixed level:
a 2 bpp or 8 bpp face on a 1-level or mono target is thresholded at the target's value today. `svfline.py` has the
identical rule (`Target(threshold=...)`, `index_level`). The format allows **1, 2 and 8 bpp only** (`spec/SVF.md`
header byte 8, `SVF_E_BPP` otherwise): there is no 4 bpp SVF; an 8 bpp face goes through the same rule.

**Consequence: the user's two requirements need no library change.** "CLUT8 at least for 1 bpp" and "AA faces
(2 bpp and higher) drawable to 1-bit outputs at a given threshold" are the existing `INDEXED8` kind with
`index_levels = 1` and `mono_threshold`, and the mono kinds with the same field. Nothing under `c/src` or
`c/include` moves; no M0+/AVR profile grows; byte-identity rests on the tests that already exist
(`test_c_renderer.py`'s INDEXED8 and mono sweeps). The port only has to expose it:

- `--format index8` (**required**, user 2026-10-25) creates an `SDL_PIXELFORMAT_INDEX8` back buffer (pitch is the
  width rounded to 4: 64 for 63 px, measured on both SDLs) and a `SVF_T_INDEXED8` target over it.
- **Colours come from the lines table's `index_base` / `index_levels` columns**, which were unused before: a
  colour with `index_levels 1` is one ink index `base + 1`, written where `cov >= threshold` (a 1 bpp face: every
  ink pixel, whatever the threshold; a 2 bpp face: the levels at or above it); a colour with `index_levels 3` is a
  three-level ramp `base + 1..3` for a 2 bpp face, and `255` the full coverage ramp. The table's `background` has
  `index_levels 0` and its `index_base` below every ramp, as the format already requires (the `max` rule needs the
  background index below the ink). The DOS table's rules are the SDL table's.
- `--threshold N` (0..255, default 128 = the library's default, so a run without it is today's bytes) sets
  `svf_target.mono_threshold` for the INDEX8 target; it also applies to the mono kinds, should a `--format mono-row`
  1-bit view be added (the builder's call; `index8` with one level is the 1-bit output the user named). The README
  states the rule in one line: "levels 85/170/255 of a 2 bpp face: 128 keeps the upper two, 255 keeps only full
  pixels, 1 keeps any ink".
- **2 bpp faces on INDEX8 are supported, two ways, by the table's choice per colour**: a ramp (`index_levels 3`,
  anti-aliased against the colour's own background, the DOS 8 bpp example's way) or a single index with the
  threshold (`index_levels 1`): never refused, never silently changed. The demo table gives the title line a ramp and
  one line a single index at the threshold so the picture shows both; `MARUS24` is the table's 1 bpp face.
- **The palette** is built the way the DOS port builds the VGA palette, with the same function (`vbe_palette_entry`
  of `vbe_select.c`, DAC width 8): index `background.index_base` and every index no colour names are the background's
  `rgb888`; index `base + k` of a colour with `n` levels is `(bg * (n - k) + fg * k + n / 2) / n` per channel. So
  the SDL picture of an INDEX8 run is, through the palette, the same colours the DOS 8 bpp capture shows, and
  `tools/vesa_lines.py`'s palette code is the checker's for the shot comparison. Setting it is the one place the two
  SDLs differ in kind: **SDL2** allocates a 256-entry palette with the surface (`s->format->palette`, measured),
  **SDL3** does not (`SDL_GetSurfacePalette` is NULL after `SDL_CreateSurface`; `SDL_CreateSurfacePalette(s)` makes the
  256-entry one, measured). The compat header gets `svfsdl_surface_palette(s)` (SDL2: `s->format->palette`; SDL3:
  `SDL_GetSurfacePalette(s)`, else `SDL_CreateSurfacePalette(s)`), and both then take the same
  `SDL_SetPaletteColors(pal, colors, 0, 256)` with the same `SDL_Color {r, g, b, a}` (return convention through
  `SVFSDL_OK`). Alpha 255 in every entry.
- **Presenting an INDEX8 buffer:** `--present surface` is a `SDL_BlitSurface` to the window surface, which converts
  through the palette in both SDLs (measured: the blit succeeds under the dummy driver on both). `--present texture`
  cannot stream INDEX8 on SDL2 ("Palettized textures are not supported", measured; SDL3's software renderer does
  accept it) so for `index8` texture mode uses `SDL_CreateTextureFromSurface` (both SDLs, measured ok), which
  converts once through the palette; `texture-direct` is not offered for `index8`. The proof is on the INDEX8 back
  buffer either way.
- **Headless check:** `index8` is the sixth kind of the dump matrix, SDL2 and SDL3, mapped and streamed, and twice
  more with `--threshold 1` and `--threshold 255` (the two ends of the rule); the dump is the `pitch * h` index
  bytes (header bits per pixel 8 and the "palettised" flag; 8-bit gray has the same header, a mislabelled dump is a DIFF), and the checker
  builds `svfline.Target("indexed8", w, h, stride=pitch, index_base=..., index_levels=..., threshold=N)` per line
  exactly as `vesa_lines.expected_buffer` does for `bpp 8`, cleared to the background index with zero padding. The
  shot comparison expands the dump through the intended palette (DAC 8), `vesa_check.py`'s 8 bpp branch.
- Screenshots: `index8` joins the pictured formats (SDL2 and SDL3), so the eye check sees a palettised 1 bpp line and
  a thresholded 2 bpp line next to the ramp.

### The parametric GRAY kind (user decision, 2026-10-25): the library task this plan starts with

The user considered three shapes for grey outputs (separate kinds GRAY8 + GRAY4; one parametric kind; GRAY8 only
with packing in the driver) and **chose one parametric kind**: bits per pixel 1 / 2 / 4 / 8 and bit order as
parameters of a single kind, one coverage-to-level rule. This is a **library change** (`c/include/svf.h`,
`c/src/svf_draw.c`, `tools/svfline.py`, tests), kept minimal, and it is the first task of the plan: the SDL port's
`gray` format needs it. **Card t_8e7da3c1 (GRAY4 kind + Pico/ESP32 grey-OLED profiles) is subsumed in its kind part**
by this task: `SVF_T_GRAY` with `gray_bits 4` is that card's GRAY4 (2 px a byte, nibble order option, max rule,
TestBlitPaths-style identity). Its profile part (the Pico/ESP32 `grey` images switching to 4 bits through the
`SVF_GREY_KIND` CMake hook the MCU design prepared, the SSD1327 screen references, `run-pico.sh` GRAY4 bench rows and
`SIZES.md` rows) **stays on that card**: it is a build-profile, emulator and bench job, not trivial, and not needed
by the SDL port.

**Public API (the whole change to `svf.h`):**

```c
typedef enum { /* ... 0..8 as today ... */
	SVF_T_GRAY      /* 9: gray_bits (1, 2, 4 or 8) bits a pixel, packed in rows; the first pixel of a byte in its most
	                 * significant bits, or its least with SVF_TF_GRAY_LSB_FIRST; a level 0..2^bits-1 a pixel, the
	                 * GRAY8 max rule on levels */
} svf_target_kind;
#define SVF_TF_GRAY_LSB_FIRST 0x02u   /* SVF_T_GRAY: the first pixel of a byte in its low bits (bit 0x01 stays RGB16's) */
#define SVF_TARGET_GRAY 0x200u        /* SVF_TARGETS default becomes 0x3FF */
/* in svf_target, after index_levels: */
	uint8_t gray_bits; /* SVF_T_GRAY: 1, 2, 4 or 8 (svf_target_init sets 8); checked on every draw, SVF_E_ARG else */
```

- **Rule (the one mapping).** With `n = 2^bits - 1`, a pixel of coverage `cov` (after composition: a syllable's cell
  is already the maximum of its pieces, `svf_compose`, untouched by this) gets level `L = (cov * n + 127) / 255`
  for bits 2, 4, 8 — the INDEXED8 ramp rule with `n` = the kind's top level, so `svfline.index_level` is reused —
  and for **bits 1** `L = 1` when `cov >= mono_threshold` (0 counting as 1), else 0: the mono rule, so
  `--threshold` applies to the 1-bit output and to nothing else (for bits >= 2 the threshold is not read: the output
  is anti-aliased and a threshold has no meaning there; the README says so). `L = 0` leaves the pixel untouched;
  otherwise the pixel's field becomes `max(existing, L)`. Exact values for the faces that exist: a 1 bpp face (ink
  255) is `n` at every bits; a 2 bpp face (85 / 170 / 255) is 1 / 2 / 3 at bits 2, 5 / 10 / 15 at bits 4, 85 / 170 /
  255 at bits 8, and at bits 1 with the default threshold 128 it is 0 / 1 / 1 (the rounding rule `(cov + 127) / 255`
  and the threshold-128 rule coincide: a run without `--threshold` is the same bytes under either description). An
  8 bpp face goes through the same formula. Padding bits of a row's last byte (a width not a multiple of the pixels
  a byte) and padding bytes of a row are never written.
- **Relation to GRAY8 and MONO_ROW.** `SVF_T_GRAY` with `gray_bits 8` writes **the same bytes as `SVF_T_GRAY8`** (max
  of coverage, one byte a pixel), and `SVF_T_GRAY` with `gray_bits 1`, MSB first, writes **the same bytes as
  `SVF_T_MONO_ROW`** at the same `mono_threshold` (bit `7 - (x & 7)` set at `cov >= threshold`, never cleared: the
  max rule on one bit is OR). Both are stated in `svf.h` and tested (below). **`SVF_T_GRAY8` and `SVF_T_MONO_ROW`
  stay as they are**, enum values, bits and behaviour: every port, the web module, the Pico grey profile, the bench
  and the MCU size rows use them, and removing or aliasing them would move every `SVF_TARGETS` mask in the repo for
  no byte of difference. In the implementation the **bits-8 body of `SVF_T_GRAY` is the existing `blit_gray8`** (with
  its nibble-table fast path), reached through the kind dispatch that already runs once per cell: that is how
  "bits 8 must not regress" is met by construction rather than by tuning. The 1 / 2 / 4-bit bodies are new, one
  generic packed loop (shift and mask per pixel, `max` on the field), with the row's first byte handled like the
  other kinds' partial first word. `SVF_TARGET_GRAY` (0x200) compiles the parametric entry and the 1/2/4 bodies; the
  8-bit body is compiled when either 0x001 or 0x200 is set, so a `0x200`-only build draws bits 8 too.
- **`svf_target_init(t, SVF_T_GRAY, buf, buf_len, w, h, stride)`** sets `gray_bits 8`, `mono_threshold 128`, and
  checks `stride >= ceil(w / 8)` and `buf_len >= h * stride` (the least any bits needs; the caller sets `gray_bits`
  after it, as `index_levels` is set after it); **`svf_draw_utf8` re-checks** `stride >= ceil(w * gray_bits / 8)` and
  `gray_bits` in {1, 2, 4, 8}, SVF_E_ARG otherwise. No new function, no new argument: the one new field.
- **`tools/svfline.py`:** kind `"gray"` with `Target(..., gray_bits=8, lsb_first=False)`; `target_row_bytes` is
  `(w * bits + 7) // 8`; `put` computes the shift (`8 - bits * (x % ppb + 1)` MSB first, `bits * (x % ppb)` LSB
  first), the level by `index_level(cov, 2**bits - 1, threshold)` for bits >= 2 and the mono rule for bits 1, and
  stores `max`. `TARGET_KINDS` gains `"gray"`; `svfdump` gains `--target=gray --gray-bits=N [--lsb-first]`.
- **Tests (the card's TestBlitPaths style, in `tools/test_c_renderer.py`, run by `make -C c check` through
  `check.sh --asan` under gcc and clang):** for each of the 8 combinations (bits x order), on the sweep faces: every
  pen phase 0..7 (bit and nibble phases matter now), the clip rectangles, overlapping cells (a mark over its base;
  two cells on one byte), the scales 1/1, 2/1, 3/2, the odd widths (padding bits), `--stride` above the least,
  `--misalign 0..3`, the guard bytes; plus the three equalities: `gray` bits 8 == `gray8` bytes, `gray` bits 1 MSB ==
  `mono-row` bytes at thresholds 1, 128, 255, and `gray` bits 4 MSB == `c/ports/grey_pack.h grey_pack_rows` of the
  GRAY8 buffer **only where the two rules agree** (that helper is `cov >> 4`: it agrees on 1 and 2 bpp faces, whose
  levels are 0/85/170/255, and differs on 8 bpp coverage: the equality test runs on the 1 and 2 bpp sweep faces and
  says so). `c/tests/test_args.c` gets the new kind's NULL/size cases; `test_kernels` its 1/2/4-bit rows; the
  `SVF_TARGETS` gate of `check.sh` goes to `0x000..0x3FF` (1024 masks x 2 + the extras: about twice today's jobs,
  still parallel; `CHECK_LIST_ONLY` test updated). `c/tests/test_pad.c` covers the padding bits.
- **Size and speed rule.** M0+ P1 and P2 (`SVF_TARGETS 0x02`) and the Uno (`0x02`), the Pico/ESP32 colour (`0x08`)
  and mono images: **unchanged bytes** — the kind is behind its bit; `build-all.sh` measures and the `SIZES.md` gate
  fails on a difference, which is the proof. The grey images (`0x01`) gain nothing unless they opt into `0x200`
  (that is the t_8e7da3c1 profile work). P1\* (every kind) and P4/P5 grow by the new bodies: estimate **200-400 B on
  M0+** (the nine-kind library costs 2,804 B over MONO_PAGE alone today, ~350 B a kind; the packed loop is one body
  with the bit width a variable); reported in `SIZES.md` "Before -> after", the user's acceptance asked for P1\* as
  before. Speed: `c/bench` GRAY8 rows (host, and the Pico `grey` build's syllable / line / screen rows through
  `run-pico.sh`, same checksums) are re-measured after the change; the GRAY8 body is untouched and only a per-cell
  branch is added, so the rows must be equal within the bench's noise (the bench prints both runs side by side as the
  speedups tasks did); a measured regression on bits 8 is a failure of this task.
- **AVR:** every arithmetic stays 16-bit-safe (`cov * 255 + 127` fits `uint16_t`; the shifts are on `uint8_t`); P4
  builds with all kinds and `-Werror`, as today.
- **MONO_PAGE is not a case of this kind** (its byte holds 8 rows of one column; the parametric kind packs along the
  row) and stays separate; `grey_pack.h` stays for the GRAY8-drawing grey profile until t_8e7da3c1's profile part.

**The SDL side of `gray`:** `--format gray --gray-bits N [--lsb-first] [--threshold T]` makes an
`SDL_PIXELFORMAT_INDEX8` / `INDEX4MSB|LSB` / `INDEX2MSB|LSB` / `INDEX1MSB|LSB` back buffer (SDL's indexed formats
pack the first pixel in the high bits for `MSB`, matching the kind's default; both orders exist in SDL2 and SDL3;
INDEX4 measured: pitch 32 for 63 px on both, palette 16 entries, blit to the window surface converts correctly in
both orders), a `SVF_T_GRAY` target with `gray_bits N` and the order flag over it, and a grey palette of 2^N entries:
entry `k` is `(bg * (n - k) + fg * k + n / 2) / n` per channel with `n = 2^N - 1`, `fg` white and `bg` the
table's `background` `rgb888` (**my call**: a coverage kind carries no colour; the table's line colours are ignored
for `gray`, as they would be for GRAY8, and the README says so). SDL has no 8-bit grey format, so bits 8 is INDEX8
with a 256-grey palette. Presenting: `surface` blits through the palette; `texture` uses
`SDL_CreateTextureFromSurface` as for `index8`. The headless dump is the packed buffer (`pitch * h`, header bpp =
N and the "palettised" flag), the checker a `svfline.Target("gray", w, h, stride=pitch, gray_bits=N,
lsb_first=..., threshold=T)`; the matrix gets the 8 (bits x order) cases under SDL2 and SDL3, mapped (streamed once,
at bits 4), and `--threshold 1 / 255` at bits 1. One screenshot pair (SDL2, SDL3) at bits 4 joins the README; the
others are checked headlessly.

### Surfaces, pitch, locking, textures

- **The back buffer is always an `SDL_Surface` the port creates** (`SDL_CreateSurface(w, h, fmt)` in SDL3,
  `SDL_CreateRGBSurfaceWithFormat(0, w, h, 0, fmt)` in SDL2) of the requested format. `svf_target_init(&t, kind,
  s->pixels, (size_t)s->pitch * s->h, s->w, s->h, (uint16_t)s->pitch)`: **stride = pitch**, never `w * bytes`.
  `svf_target.stride` is `uint16_t` and `w`, `h` are `int16_t`: a pitch above 65535 or a size above 32767 is refused
  with a message (16383 px wide at 32 bpp is the practical limit; the program's default is 640 x 480, 1024 x 768 is
  offered as in the DOS port).
- **Clearing.** Before drawing, the port writes every row itself: `w` background pixels in the kind's byte order,
  then the padding bytes `pitch - w * bytes` set to 0. The library never touches padding (`svf.h`: "no padding byte of
  a row past its pixels"), so after drawing the padding is still 0, and the dump of the **whole `pitch * h`** bytes is
  what the checker compares against a reference buffer built with `stride = pitch`, its own rows cleared the same way.
- **Locking.** `SDL_LockSurface` / `SDL_UnlockSurface` around every draw and every dump, whether or not `SDL_MUSTLOCK`
  says so (a plain surface needs none; the call costs nothing and keeps the code correct for an RLE or window surface).
  SDL2 returns 0 on success, SDL3 `true`: one compat macro (`SVFSDL_OK(call)`).
- **Presenting**, chosen by `--present`:
  - `surface` (default for SDL2 and SDL3 alike): `SDL_BlitSurface(back, NULL, SDL_GetWindowSurface(win), NULL)` then
    `SDL_UpdateWindowSurface(win)`. The window surface's own format (XRGB8888 under the dummy and X11 drivers here)
    may differ from the back buffer's: SDL converts in the blit; the identity claim is on the back buffer.
  - `texture`: `SDL_CreateRenderer` (SDL2 `(win, -1, 0)`, SDL3 `(win, NULL)`), a streaming texture of the same format,
    `SDL_UpdateTexture(tex, NULL, back->pixels, back->pitch)`, `SDL_RenderClear`, `SDL_RenderCopy` / `SDL_RenderTexture`,
    `SDL_RenderPresent`. Under the SDL3 software renderer an RGB565 texture is converted internally (measured); that is
    fine because the proof is on the back buffer.
  - `texture-direct` (**my call**, demonstration only): lock the streaming texture and run `svf_draw_utf8` directly on
    the locked pixels with the locked pitch, then unlock. This shows the library drawing into SDL's own memory with
    SDL's own pitch; it is not dumped and makes no identity claim (after unlock the bytes may have been converted).
    The README says exactly that.
- **No `SDL_ConvertSurface` anywhere on the proven path.**

### Streaming vs mapped faces in the demo

- Default **mapped**: each face file is read whole into memory the port allocates (`SDL_LoadFile` or `fread`; the
  port may allocate, the library never does, and `c/check.sh`'s no-malloc gate is on `c/src` objects only) and opened
  with `svf_open_mapped`.
- `--stream`: each face is opened with `svf_open_stream` through a `fseek` + `fread` callback and a block cache (1 KB
  blocks, 64 slots, as `svfvesa.c`; sizes from `svf_stream_tables_size`), the tables buffer allocated by the port.
  The dump must be identical in both modes; the checker runs both. This is the shape ScummVM would use (faces inside
  pack files behind a seekable stream) and is cheap to prove on the host at full-screen size.
- The chain, scale, colours, positions and text come from the lines table (next section); a composed-syllable cache
  (`svf_chain_cache`) is given when `--syllable-cache=BYTES` is passed (default 0, pixels are the same either way by
  contract; the checker runs one case with it).

### The lines table

The port reads the `vesa-lines.txt` format with the DOS port's parser compiled in (`c/ports/dos/vesa_lines.c`,
`vesa_lines.h`; the Python twin `tools/vesa_lines.py` parses the same file for the checker and `substitute()`
expands `{W}`, `{H}`, `{BPP}`). Its own file is `c/ports/sdl/sdl-lines.txt` (**my call**: an own file, so the DOS
captures and their sums do not move), with the same four faces from `svf/dos` (`PAPLG16.SVF` + `PAPLG18.SVF`,
`MARUS24A.SVF`, `MARUS24.SVF`: ASCII, a 2 bpp jamo set, two 24 px faces), five or six lines: a title with
`{W}x{H} {BPP} bpp`, two 24 px lines, a 3/2 scaled line, a 2/1 scaled line, a coloured line. The SDL version and
driver go into the window title and stdout, never into the text (the text must be the same under both SDLs for one
expected buffer). The table's `rgb565`, `rgb555` and `rgb888` columns give each colour in every kind; `index_base` /
`index_levels` give the `index8` indices and the palette (the INDEX8 section): the title line gets a 3-level ramp,
one line a single ink index (thresholded), as the DOS table does with `white` and `yellow`.

The DOS-name rule of the format (`[A-Z0-9_]{1,8}\.SVF`, resolved inside a faces directory) stays as it is; the faces
directory is `--faces DIR` (default `svf/dos`).

## The compat layer (`c/ports/sdl/sdl_compat.h`)

One header, target about 60-90 lines, nothing else in the port knows which SDL it is. The build passes `-DSVFSDL=2` or
`-DSVFSDL=3` (from the Makefile's `SDL=` choice) only to pick the include; every other difference keys on
`SDL_VERSION_ATLEAST(3, 0, 0)`, the idiom ScummVM's backends use.

```c
#if SVFSDL == 3
#include <SDL3/SDL.h>
#else
#define SDL_MAIN_HANDLED
#include <SDL.h>
#endif
#if SDL_VERSION_ATLEAST(3, 0, 0)
#define SVFSDL_OK(call) (call)                 /* SDL3: bool, true on success */
#define SVFSDL_EVENT_QUIT SDL_EVENT_QUIT
#define SVFSDL_EVENT_KEY_DOWN SDL_EVENT_KEY_DOWN
static inline SDL_Window *svfsdl_create_window(const char *t, int w, int h) { return SDL_CreateWindow(t, w, h, 0); }
static inline SDL_Surface *svfsdl_create_surface(int w, int h, SDL_PixelFormat f) { return SDL_CreateSurface(w, h, f); }
static inline SDL_PixelFormat svfsdl_surface_format(const SDL_Surface *s) { return s->format; }
static inline SDL_Renderer *svfsdl_create_renderer(SDL_Window *w) { return SDL_CreateRenderer(w, NULL); }
static inline bool svfsdl_render_copy(SDL_Renderer *r, SDL_Texture *t) { return SDL_RenderTexture(r, t, NULL, NULL); }
#else
#define SVFSDL_OK(call) ((call) == 0)          /* SDL2: int, 0 on success */
#define SVFSDL_EVENT_QUIT SDL_QUIT
#define SVFSDL_EVENT_KEY_DOWN SDL_KEYDOWN
#ifndef SDL_PIXELFORMAT_XRGB8888
#define SDL_PIXELFORMAT_XRGB8888 SDL_PIXELFORMAT_RGB888
#endif
/* ... the SDL2 twins: SDL_CreateWindow(t, SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED, w, h, 0),
 *     SDL_CreateRGBSurfaceWithFormat(0, w, h, 0, f), s->format->format, SDL_CreateRenderer(w, -1, 0),
 *     SDL_RenderCopy(r, t, NULL, NULL) == 0 */
#endif
```

What differs between the two and is covered (the whole list the port touches): header path; `SDL_main` (SDL2 may
rename `main` on some platforms: `SDL_MAIN_HANDLED` plus `SDL_SetMainReady()` on both, which SDL3 also has);
`SDL_Init` and the other return conventions (`int 0` vs `bool`); window creation arguments; surface creation name
and the `format` field (a pointer to a struct in SDL2, an enum in SDL3; `SDL_GetPixelFormatName` takes the enum in
both); renderer creation; `SDL_RenderCopy` vs `SDL_RenderTexture` (`SDL_FRect`); event type names; `SDL_Delay` and
`SDL_PollEvent` are the same; `SDL_GetError`, `SDL_SaveBMP`, `SDL_LockSurface`, `SDL_UpdateTexture`,
`SDL_LockTexture`, `SDL_BlitSurface`, `SDL_UpdateWindowSurface`, `SDL_CreateTextureFromSurface` and
`SDL_SetPaletteColors` exist in both with the return-convention difference only; the surface palette is allocated
with the surface in SDL2 and by `SDL_CreateSurfacePalette` in SDL3 (`svfsdl_surface_palette`, the INDEX8 section). Anything that turns out to need more than a macro or a one-line inline is reported, not hidden.

The window-surface path and the renderer path are both kept because ScummVM's `SurfaceSdlGraphicsManager` uses both
(`_hwScreen` surface, `_screenTexture` RGB565) and the two differ most between SDL2 and SDL3.

## Headless byte-identity: how it is tested

- **Dump mode.** `svfsdl --format K [--stream] [--syllable-cache=N] --dump FILE [--present P] [--frames 1]` with
  `SDL_VIDEODRIVER=dummy`: the port initialises video, draws the table into its back buffer, presents once (so the
  present path runs under the dummy driver too, and an SDL error there fails the run), writes a 16-byte header
  (`"SVFSDL1 "`, then u16 w, h, pitch, u8 bits per pixel (32, 24, 16, 8, 4, 2 or 1), u8 flags: bit 0
  `SVF_TF_RGB16_BIGENDIAN` was set, bit 1 palettised (index8, gray), bit 2 LSB first (gray), bit 3 alpha-demo coverage
  buffer, bits 4-5 SDL major - 2, bits 6-7 zero; the reference is `c/ports/sdl/sdl_check.py`) and the `pitch * h`
  bytes, and exits 0 without waiting for a key.
  `--shot` and `--dump` may be given together: the order in a run is draw, present, shot, dump, exit. In `--alpha-demo` dump mode the GRAY8 coverage buffer is written instead (bits per pixel 8, flag bit 3, pitch = w, and `{BPP}` is 8 in the text).
- **Checker** `c/ports/sdl/sdl_check.py DUMP --lines sdl-lines.txt --faces svf/dos [--kind K]`: reads the header,
  takes `w`, `h`, `pitch` from it, builds `svfline.Target(kind, w, h, stride=pitch, buf=cleared rows)` with the colours
  the kind uses (`fg565`/`bg565` from the table's `rgb565` or `rgb555`, `fg888`/`bg888` from `rgb888`, the ARGB case
  with `0xFF000000` added to `fg888` and to the clear pixel; `big_endian` from the dump's header flag), draws each
  line with `svfline.placements` + `draw_target` (as `tools/vesa_lines.py expected_buffer` does, the one difference
  being the stride and the clear), and compares all `pitch * h` bytes. A difference names the first differing byte,
  its pixel (x, y) and the kind, and writes a diff PNG next to the dump. It also prints the FNV-1a of the buffer
  (`sum=`) as the DOS tooling does, so a number can be quoted in the README. Exit 0 / 1 / 2 as `vesa_check.py`.
  The shared parts (`parse`, `substitute`, colour lookup) are imported from `tools/vesa_lines.py`; if a
  `stride`/`clear` parameter is the cleanest way, `expected_buffer` grows optional arguments with the old defaults
  (the DOS sums must not change; `test_c_renderer.py`'s vesa tests pin them).
- **`c/ports/sdl/check.sh [OUT]`**: builds `svfsdl2` (pkg-config sdl2) and `svfsdl3` (pkg-config sdl3 with
  `PKG_CONFIG_PATH` including `~/opt/sdl3/lib/pkgconfig`, overridable by `SDL3_PREFIX`), then for each binary, each
  of the six kinds, mapped and streamed (and once with a syllable cache, once `--present texture`, and `index8` twice
  more at `--threshold 1` and `255`), runs the dump under `SDL_VIDEODRIVER=dummy` and the checker: 2 x 6 x 2 +
  extras, about 34 runs, each well under a second. Prints
  one `port-sdl-check: OK sdl2 N runs, sdl3 N runs, sum=...` line (the sums per kind are equal between SDL2 and SDL3
  by construction: the checker's expected buffer does not depend on the SDL; the script asserts the two dumps of one
  case are byte-equal to each other as well, a second, SDL-independent statement). A missing SDL2 or SDL3 is a
  **failure**, not a skip (**my call**: like every other toolchain of `build-all.sh`; `--port sdl` with
  `SVFSDL_ONLY=2` runs one when someone wants that).
- Where it runs: `c/cross/build-all.sh --ports` gets a `sdl` case in `port()` that calls `check.sh` and prints
  `port-sdl: OK svfsdl2 N bytes, svfsdl3 M bytes` (one line, as `port-dos`), and the full run's OK count in the
  script's header comment goes from 42 to 43 (+ the check line if it is separate: the builder keeps it to one line).
  The binary sizes go to `rows.txt` as `program sdl2` / `program sdl3` **informational** lines that
  `check-sizes-md.sh` does not gate (**my call**: they depend on the host's SDL build, not on the library), and
  `SIZES.md` "Port examples" gets the two sizes in the parenthesis with dos and web.
- `make -C c check` is unchanged and stays green; `tools/test_c_renderer.py` is unchanged.

## Screenshots

- `c/ports/sdl/shots.sh [OUT]` (as `vesa-shots.sh`): for SDL2 and SDL3, for `xrgb8888`, `argb8888`, `rgb565`, `index8` and `gray --gray-bits 4`, at
  640 x 480, runs `xvfb-run -a -s "-screen 0 1280x1024x24" svfsdl --format K --present surface --shot FILE.bmp
  --frames 1`: the program draws, presents, and then saves what the **window** holds (`SDL_GetWindowSurface` after
  `SDL_UpdateWindowSurface` in surface mode; `SDL_RenderReadPixels` in texture mode) with `SDL_SaveBMP`, so the
  picture is what SDL showed, not the back buffer. The script converts BMP to PNG (PIL), checks the PNG is W x H with
  at least 1 % of pixels off its background, and compares it with the same run's `--dump` through the rules of
  `vesa_check.py` (32-bit: exact; RGB565 expanded by SDL as `v << 3 | v >> 2` for 5 bits and `v << 2 | v >> 4` for
  6, which is the checker's `exact` rule `v * 0x21 >> 2` / `v * 0x41 >> 4`; a `shl` or `tolerance` result is printed,
  not failed, since this is SDL's conversion, not the library's). The shared comparison code moves from
  `vesa_check.py` into a small module both import, or is copied if a move would touch the DOS card's script
  (**builder's call**; a move must keep `vesa-shots.sh` green).
- The ten PNGs go to `c/ports/sdl/shots/` and into the README in a 2 x 5 table (SDL2 / SDL3 by format), with the
  `rgb555` and `bgr24` runs available but not pictured. The user checks them by eye (the card's criterion); the
  design expects the SDL2 and SDL3 pictures of one format to be pixel-identical (the back buffers are, and the
  present path is a straight blit at 1:1), and the script reports whether they are.

## Build integration

- **Makefile, not CMake** (**my call**): the library and the DOS/web ports are plain compiler lines, only the Pico and
  ESP32 ports use CMake because their SDKs do; SDL is found with `pkg-config`, which Make does well.
  `c/ports/sdl/Makefile`:
  - `make -C c/ports/sdl SDL=2` builds `c/build/ports/sdl/svfsdl2` with `pkg-config --cflags --libs sdl2`;
    `SDL=3` builds `svfsdl3` with `pkg-config sdl3` and adds `-Wl,-rpath,$(pkg-config --variable=libdir sdl3)` so a
    `~/opt` install runs without `LD_LIBRARY_PATH`. `make -C c/ports/sdl` (no `SDL=`) builds both; `check` runs
    `check.sh`; `shots` runs `shots.sh`. `PKG_CONFIG_PATH` is extended with `$(SDL3_PREFIX)/lib/pkgconfig`,
    `SDL3_PREFIX ?= $(HOME)/opt/sdl3`.
  - Sources: `svfsdl.c`, `sdl_compat.h`, `../dos/vesa_lines.c ../dos/vbe_select.c` (with `-I../dos`;
    `vesa_lines.c` calls `vbe_palette_entry` for the 8 bpp palette, unused here but linked; both are pure C99, the
    host builds them for `test_vbe` already), `../../src/*.c`, flags
    `-std=c99 -Wall -Wextra -Werror -O2 -I../../include`, the library with its defaults (every kind, every layout,
    streaming and scaling in: a desktop binary; **my call**). `svfsdl.c` is `-std=c99` plus `_POSIX_C_SOURCE`
    only if `fseeko` is wanted; plain `fseek`/`fread` suffice for the faces in the repo.
- **Getting SDL3 without root** (README, and `c/cross/install-toolchains.sh` gets an `sdl3` entry so the gate host
  is reproducible as for every other toolchain). **The user's decision (2026-10-24): the SDL3 is the user's own fork
  at `~/opt/src/SDL3`** (upstream plus the DOS commits, `SDL_version.h` 3.5.0, HEAD 7a588ba today), not an upstream
  release tarball. The entry builds that tree with the cmake lines of "What was checked" (`-DSDL_X11_XTEST=OFF`
  included: `libxtst-dev` is not installed) into `-DCMAKE_INSTALL_PREFIX=$HOME/opt/sdl3`, and **records the fork
  commit it was built from** (`git -C ~/opt/src/SDL3 rev-parse HEAD`) in `SIZES.md`'s toolchain table and in a
  `COMMIT` file under the prefix; a rebuild after the fork moves updates the sha in the table (the manifest check of
  `build-all.sh` compares it, as it pins the other toolchains to a commit). A host without the fork tree is told
  where it lives (the path, not a URL: the fork is the user's). `~/opt/sdl3-host` (today's measurement build of the
  same tree) is reached with `SDL3_PREFIX=~/opt/sdl3-host` and is otherwise unused.
- The MCU budgets are untouched by construction: no file under `c/src` or `c/include` changes, and the port is not an
  MCU row.

## README contents (`c/ports/sdl/README.md`)

1. What it is (one paragraph), the format table above with the SDL names and the `svf_target` fields.
2. Build and run: the two `make` lines, the direct compiler lines for SDL2 and SDL3 (as the DOS README gives), the
   SDL3-from-source recipe, the command-line options (`--format`, `--present`, `--stream`, `--syllable-cache`,
   `--faces`, `--lines`, `--size WxH`, `--threshold`, `--dump`, `--shot`, `--frames`, `--alpha-demo`), what the program prints
   (SDL version, driver, window-surface format, draw time, `sum=`).
3. The headless check: the command, what is compared, the exit codes, the `port-sdl` line of `build-all.sh --ports`.
4. Screenshots table, and the sentence that the back buffer, not the picture, is the proven object.
5. Notes for an application author: stride is the pitch; padding bytes; clear before drawing; the endian rule;
   ARGB8888 opaque vs alpha-from-coverage (`--alpha-demo`); `texture-direct` is a demonstration; the kinds never read
   the destination (text over a photo needs the GRAY8 route).
6. "For ScummVM" (the next section's list, shortened), and the faces' licences by reference to `c/ports/FACES.md`.

## What the SDL port proves or provides for the ScummVM card (t_5a7bcd78)

Stated here so that card's design can rely on it; nothing of ScummVM is designed.

- **Build:** the library compiles under `-Wall -Wextra -Werror` inside an SDL2 and an SDL3 program on the host
  compiler, with the same `SDL_VERSION_ATLEAST(3, 0, 0)` idiom ScummVM's backends use. ScummVM's own warnings set,
  code style and module placement are that card's.
- **Pitch and formats:** SDL-allocated buffers have pitches rounded to 4 bytes; the port shows that `stride = pitch`
  is the whole adaptation, and gives the mapping from SDL's names to the kinds. ScummVM's `Graphics::PixelFormat` is
  masks and shifts, not names; the README's table gives, per kind, the equivalent (`PixelFormat(4, 8, 8, 8, 0, 16, 8,
  0, 0)` on little-endian for XRGB8888, `PixelFormat(2, 5, 6, 5, 0, 11, 5, 0, 0)` for RGB565), so the mapping can be
  checked rather than guessed.
- **What the kinds do not do:** the colour kinds blend against a known background and never read the destination; GRAY8, GRAY and INDEXED8 take the maximum of the existing value and the new level, and the mono kinds OR (they need a cleared buffer).
  ScummVM's `hires_text` composes coverage over the existing pixel with the game palette
  (`text_compose.cpp`: `composeSpan` reads `dst`, `blendRGB` with a palette index; `coverageToArgb` builds ARGB with
  alpha = coverage; `stampSpan` thresholds at 128 into CLUT8). That is the GRAY8 / `SVF_T_COVERAGE_CB` route of the
  library plus ScummVM's own compositor; the `--alpha-demo` mode is that route in miniature. The packed kinds fit
  where the background is a known solid (menus, status lines), not the game screen.
- **Streaming on a desktop:** `--stream` proves the stream reader with a block cache identical to mapped at
  full-screen sizes on the host; ScummVM's faces come from pack files behind `Common::SeekableReadStream`, the same
  shape as the port's `fseek`/`fread` callback.
- **A headless proof method** (dummy driver, dump, `svfline` with the real pitch) that an `engine_gate.sh` step can
  copy.
- **What it does not prove:** anything about ScummVM's threading, its scalers, its CLUT8 planes, the
  `JSET` set-limit change noted on the card (`kJamoMaxInitSets`/`MedSets`), or performance inside ScummVM.

## What counts as done (the card's close criterion, measurable)

1. `make -C c/ports/sdl` builds `svfsdl2` and `svfsdl3` from `svfsdl.c` + `sdl_compat.h`, `-Werror` clean; the only
   library change on the branch is the GRAY task's (`git diff --stat main -- c/src c/include tools/svfline.py` names
   `svf.h`, `svf_draw.c`, `svfline.py` and nothing else), with its tests green under `make -C c check` (gate
   `0x000..0x3FF`), the equalities (bits 8 == GRAY8, bits 1 == MONO_ROW) passing, `build-all.sh` showing P1/P2, Uno,
   colour and mono images byte-equal to before, P1\*/P4/P5 growth and the GRAY8 bench rows reported.
2. `c/ports/sdl/check.sh` prints `port-sdl-check: OK` with every run of the matrix (2 SDLs x 6 kinds x {mapped,
   streamed} + the 8 `gray` bits-x-order cases + the cache, texture and threshold extras) byte-identical to `svfline`, and the SDL2 and SDL3 dumps of each case
   equal to each other; `c/cross/build-all.sh --port sdl` prints `port-sdl: OK ...`.
3. `make -C c check` green (unchanged), `tools/test_c_renderer.py` green, `vesa-shots.sh` still green if any shared
   checker code moved.
4. `c/ports/sdl/README.md` with the build/run lines for both SDLs, the SDL3 recipe, the format table, the check and
   the ten screenshots; `shots.sh` reports the SDL2/SDL3 pictures of one format identical (or says why not).
5. The user has looked at the ten pictures.
6. `SIZES.md`: the toolchain table has the pinned SDL3 entry; "Port examples" names the two binaries' sizes
   (informational); `build-all.sh`'s OK count updated.

## Risks

- **The GRAY task's size on P1\***: a second body in the hot dispatch; if the estimate (200-400 B on M0+) is
  exceeded, the task stops at the measurement and reports before the SDL work continues, as the speedups tasks did.
- **SDL3 API drift**: the gate's SDL3 is the user's fork, a moving development tree (3.5.0-dev today). The functions
  used are all stable 3.2 API (`SDL_CreateSurface`, `SDL_RenderTexture`, `SDL_GetWindowSurface`, no properties), so
  a later fork commit should build unchanged; if a name moves, it is one more line in the compat header, and the
  recorded fork commit says which tree the last green gate was on.
- **The dummy driver's window surface** is XRGB8888 for both SDLs here; a different format elsewhere only changes the
  blit's conversion, never the back buffer. The present step is run headlessly so such an error surfaces in the check.
- **`vesa_lines.c` reuse** pulls the DOS parser's limits (16 colours, 32 lines, 512-byte lines, DOS face names) into
  the SDL port. Accepted: the table is small and the limits are tested; if a limit bites, the SDL table shrinks, the
  parser does not change under the DOS card.
- **Padding rule**: if an SDL ever hands back a surface whose padding is not writable (it is: `pixels` is a flat
  allocation of `pitch * h`), the clear step would fault; checked by the sanitizer build of the port (the Makefile
  offers `ASAN=1`, **my call**, and `check.sh` runs one case with it).
- **X11 under Xvfb for the screenshots** needs the X11 driver in the SDL3 build (it is, `SDL_X11` is on by default;
  only XTEST was switched off). If `xvfb-run` is absent on a host, `shots.sh` says so and exits 2; the check is not
  affected.

## Left to the builder

- Exact option names and the dump header's byte layout (within the fields named), the Makefile's variable names, the
  file names of the shots, the C file's internal structure.
- Whether the shared capture-comparison code is moved out of `vesa_check.py` or copied (above).
- The `install-toolchains.sh` entry's shape for the SDL3 fork build (follow the existing entries; the tree, prefix,
  cmake switches and the recorded commit are fixed above).
- The lines of `sdl-lines.txt` (within the format's limits and the faces named), the window title text, the gradient
  of `--alpha-demo`.
- Where `--frames 1` ends: after one present and the dump/shot; the interactive default waits for a key or close.
- The sanitizer case's flags and which case runs under it.

## Builder check (2026-10-24, one fresh reviewer on this document)

Six questions came back; two it ranked as mattering. Sorted:

**Answered already, now stated in the document:**

- *How does the checker learn the `big_endian` flag? The header lists no flag.* The dump header has a flags byte
  (bit 0: `SVF_TF_RGB16_BIGENDIAN` was set on the target); the header field list above now names it. The checker
  takes `big_endian` from it, and also checks it against the dump's SDL major and the host's `sys.byteorder` (a
  mismatch is exit 2).
- *The Makefile's source list lacks `vbe_select.c`, which `vesa_lines.c` needs for `vbe_palette_entry`.* Correct:
  `vesa_lines.c` includes `vbe_select.h` (lines 5, 381, 391). `vbe_select.c` is pure C99 (`c/tests/test_vbe.c` builds
  it on the host already) and is in the source list above now: `../dos/vesa_lines.c ../dos/vbe_select.c`.
- *Where does the pinned SDL3 come from; is there network; what does the gate use on this host?* Settled by the
  user (2026-10-24): the gate's SDL3 is the user's fork at `~/opt/src/SDL3`, built by `install-toolchains.sh` into
  `~/opt/sdl3` with the fork commit recorded; no download is involved, so network does not matter. `~/opt/sdl3-host`
  (today's build of the same tree) is reached with `SDL3_PREFIX` and is otherwise unused.

**Minor, settled here (my call):**

- *If the gate's SDL3 behaves differently from today's measurements (a name, the dummy driver's window format, the
  texture formats) after the fork moves, gate on which?* The gate is on the fork commit `install-toolchains.sh`
  recorded, one SDL3 only. A name difference is one more line in the compat header; a behaviour difference on the
  present side (window-surface format, texture conversions) does not touch the proof, which is on the back buffer,
  and is recorded in the README's "What was measured" with the commit. A difference on the proof side (a surface
  pitch rule, a format alias missing) is reported before any work-around.
- *May `--shot` and `--dump` be given together?* Yes, in one invocation, and `shots.sh` relies on it: the order within
  a run is draw, present, shot (what the window holds), dump (the back buffer), exit. One run, one pair of files.
- *Can the card close without the user's look?* No: the builder delivers the ten PNGs and the check lines, posts them
  on the card, and the card waits for the user's eye check (done-criterion 5). Everything else is measurable and is
  closed by evidence.

**Put to the user, decided by the user (2026-10-24; also listed under "Already decided"):**

1. The SDL3 the gate builds against: the design proposed an upstream 3.2.x release pinned by sha256; **the user chose
   the own fork at `~/opt/src/SDL3`** (3.5.0-dev with the DOS commits), built by `install-toolchains.sh` into
   `~/opt/sdl3` with `-DSDL_X11_XTEST=OFF` and the fork commit recorded. The document was changed accordingly ("Build
   integration", "Risks", "Left to the builder").
2. The two extras (`rgb555` via `XRGB1555`, `bgr24` via `BGR24`): **kept**, headless check only, no screenshots.
3. `--alpha-demo` (GRAY8 coverage to a straight-alpha BGRA32 texture blended by SDL, the ScummVM `coverageToArgb`
   shape): **kept**.

Nothing is left for the user to answer before planning.
