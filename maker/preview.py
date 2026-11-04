#!/usr/bin/env python3
"""Previews: the source and result sample PNGs the page shows.

`source_png` draws the sample line with Pillow at one size, for the source kinds FreeType reads (outline, bitmap,
BDF, PCF, FNT/FON). A DOS raw font and an SVF are baked first with `bake_source_face`: an SVF is copied, a DOS raw
font goes through the same `jamoset.py` command the conversion runs, into the caller's `work/`; both are then drawn by
`svf_png`, the sample line through `svfline`. `result_png` draws one produced face the same way, over `chain_for`'s
chain: a face that carries no U+0041 is drawn with a Latin companion beside it, because `svfline` takes the first face
of the chain that has the code point.

A `.gz` source is never read compressed: `materialize` decompresses it once into the caller's work directory (the entry
carries `"gzip": true`) and returns the plain path, which every reader here uses instead.

Every PNG goes to its own `<out>.<random>.tmp` beside the output (`tempfile.mkstemp`) and then through `os.replace`, so
a page fetch never sees a half-written file and two threads writing the same output never collide: a failed write
removes its own temp file, never the output. `source_png` refuses a canvas past `MAX_CANVAS` / `MAX_PIXELS` before
`Image.new`, including the `.notdef` mask `_draws_sample` needs, and refuses a face that does not really draw the
sample (`_draws_sample`): a KSC5601 or Johab BDF, which FreeType gives no Unicode charmap, draws every character as
glyph 0, and a face without Hangul has no glyph for the sample at all. Previews read faces through the uncached loader
(`Face.load`'s process-wide cache is serialized by `RENDER_LOCK` and cleared after every read), so a face rebaked under
the same path is re-rendered as it now is, even while another thread is rendering.

The library assumes `maker/` and `tools/` are on sys.path (the entry points set it).
"""

import gzip
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import zlib

import detect
import routes
import svfline
from PIL import Image, ImageDraw, ImageFont

# The repository face a chain falls back to when the produced face has no ASCII of its own (relative to `svf/`).
LATIN_FALLBACK = "dos/NEODG16.SVF"

# One render at a time: `svfline.Face.load` caches by path for the whole process, so without this a render could draw
# with a face another thread cached before a rebake (or measure one face and draw another). Held across a render and
# its `cache_clear`, never across the PNG write.
RENDER_LOCK = threading.Lock()

# The Global Constraints subprocess form: an explicit environment, no shell, the tool's own work directory as cwd.
ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/"), "LANG": "C.UTF-8"}
TIMEOUT_S = 60

# The largest source-preview canvas `source_png` will allocate: no side past MAX_CANVAS px and no more than MAX_PIXELS
# in area. Pillow's MAX_IMAGE_PIXELS guards `Image.open`, not `Image.new`, and a font whose metrics are hostile (a
# tiny `unitsPerEm`, a huge advance) asks for gigabytes at a legal size: one upload must not be able to do that.
MAX_CANVAS = 4096
MAX_PIXELS = 4_000_000

# The character `source_png` insists a face really draws. FreeType offers a KSC5601 or Johab BDF no Unicode charmap, so
# every character there is glyph 0; a face without Hangul has no glyph for it either. `detect.NOTDEF_CHAR` is a
# noncharacter no font maps, so its mask is glyph 0's.
SAMPLE_CHAR = "\uac00"


def materialize(abs_path, work_dir):
    """@p abs_path itself, or the path of its decompressed copy when it ends in `.gz`.

    A non-PCF `.gz` source (the entry carries `"gzip": true`) is decompressed once into @p work_dir, under the same
    cap `detect` reads a `.gz` under; the plain file is the source's name without the `.gz`. A gzip past
    `detect.MAX_DECOMPRESSED` raises `detect.TooLarge` (the caller then writes nothing), and the plain file replaces
    any earlier copy atomically, so a half-written file is never passed on.
    """
    if not abs_path.lower().endswith(".gz"):
        return abs_path
    out = os.path.join(work_dir, os.path.basename(abs_path)[:-3])
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(out) + ".", suffix=".tmp", dir=work_dir)
    size = 0
    try:
        with os.fdopen(fd, "wb") as dst, gzip.open(abs_path, "rb") as src:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > detect.MAX_DECOMPRESSED:
                    raise detect.TooLarge("too large (> %d MiB decompressed)" % (detect.MAX_DECOMPRESSED >> 20))
                dst.write(chunk)
        os.replace(tmp, out)
    except BaseException:
        _remove(tmp)
        raise
    return out


def svf_png(chain_paths, out_path):
    """The sample line through @p chain_paths as a PNG at @p out_path; returns its `(width, height)`.

    The geometry is the spec's: `svfline.measure` sizes the buffer, the baseline sits at `ascent + 1` and the left
    margin is 1 px, so the GRAY8 bytes go straight to Pillow (`svfline.main`'s `line W H X Y`). The faces are read
    through the uncached loader (`Face.load`'s `lru_cache` would answer with a face's earlier bytes for the life of the
    process: see `chain_for`), and the whole render holds `RENDER_LOCK` so no other thread's cached face can leak in.
    """
    try:
        with RENDER_LOCK:
            try:
                text = detect.SAMPLE_TEXT.encode("utf-8")
                width, ascent, descent = svfline.measure(chain_paths, text)
                w, h = width + 2, ascent + descent + 2
                buf = svfline.layout(chain_paths, text, 1, ascent + 1, w, h)
                img = Image.frombytes("L", (w, h), buf)
            finally:
                svfline.Face.load.cache_clear()
        _save_png(img, out_path)
        return w, h
    except Exception:
        _clear(out_path)
        raise


_LIVE = {}                                   # pid -> Popen of every run_bounded child still running
_LIVE_LOCK = threading.Lock()


def live_count():
    with _LIVE_LOCK:
        return len(_LIVE)


def kill_all():
    """SIGKILL the process group of every `run_bounded` child still running (the server is stopping); returns how many.
    Each caller sees its run end as a failed one (a bake that fails is 'no preview')."""
    with _LIVE_LOCK:
        pids = list(_LIVE)
    for pid in pids:
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass
    return len(pids)


def run_bounded(argv, cwd, timeout, env=None):
    """`subprocess.run(argv)` with stdout and stderr captured, in its own session: on @p timeout the whole process group
    is killed (not only the child, whose own children would survive) and `subprocess.TimeoutExpired` is raised."""
    proc = subprocess.Popen(argv, cwd=cwd, env=ENV if env is None else env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    with _LIVE_LOCK:
        _LIVE[proc.pid] = proc
    try:
        out, err = proc.communicate(timeout=timeout)
    except BaseException:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.communicate()
        raise
    finally:
        with _LIVE_LOCK:
            _LIVE.pop(proc.pid, None)
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)


def source_png(font, abs_path, size, out_path):
    """@p abs_path drawn with Pillow at @p size as a PNG at @p out_path; False when nothing could be written.

    A `.gz` source is decompressed first (`materialize`). `index=font["face_index"]` picks the entry's face. The line
    is drawn with 1 px margins, offset by `getbbox`'s left and top so ink left of the pen or above the line top is not
    clipped. The canvas is refused (False, nothing written) when a side would pass `MAX_CANVAS` or the area
    `MAX_PIXELS`, before `Image.new`; the preview is refused when the face does not really draw the sample
    (`_draws_sample`, whose `.notdef` mask is capped the same way before it is rasterized). Any failure (an unreadable
    file, a size Pillow cannot open) is False and leaves no PNG behind: a half-written or stale file must not look like
    a preview.
    """
    try:
        abs_path = materialize(abs_path, os.path.dirname(os.path.abspath(out_path)))
        face = ImageFont.truetype(abs_path, size, index=font.get("face_index", 0))
        left, top, right, bottom = face.getbbox(detect.SAMPLE_TEXT)
        x, y = 1 - min(left, 0), 1 - min(top, 0)
        w, h = right - min(left, 0) + 2, bottom - min(top, 0) + 2
        if _canvas_ok(w, h) and _draws_sample(face):
            img = Image.new("L", (w, h), 0)
            ImageDraw.Draw(img).text((x, y), detect.SAMPLE_TEXT, 255, font=face)
            _save_png(img, out_path)
            return True
    except Exception:
        pass
    _clear(out_path)
    return False


def bake_source_face(font, abs_path, layout, eng_abs, out_svf, tools_dir, extra=(), env=None):
    """Bake @p font's source into @p out_svf for a preview; True only when this bake really produced @p out_svf.

    A `.gz` source is decompressed first (`materialize`). An `svf-*` source is copied (v3) or converted (v2,
    `svf2to3.py --check`). A `dos-raw` source runs its
    native jamo route (the same `jamoset.py` command the conversion runs, `--eng` included when the caller passes one)
    at the font's first size, 1 bpp; the tool's report is dropped, since this bake is not the job's build log. Any other
    source kind is False.

    A failed bake is False, not an exception, and leaves no face behind: @p out_svf is removed before the commands run,
    every command must exit 0, and the file must exist afterwards - an earlier bake of the same path must never be
    mistaken for this one. A missing or unreadable source, a truncated or corrupt `.gz`, a source that is (or would be
    decompressed onto) @p out_svf itself, a relative @p out_svf (resolved against the process's cwd, never cwd "") and a
    tool that times out are all False too.

    @p extra is the flags the job's steps carry (`--jset-version V` among them), so the preview shows the face the job
    would write. @p env, when given, is the tools' environment (a local job's `TMPDIR` and no-bytecode flag).
    """
    out_svf = os.path.abspath(out_svf)
    src = abs_path
    try:
        abs_path = materialize(abs_path, os.path.dirname(out_svf))
        if _same_file(src, out_svf) or _same_file(abs_path, out_svf):
            return False                     # a copy onto the source is not a bake; leave the file alone
        _remove(out_svf)
        kind = font.get("source_kind")
        work = os.path.dirname(out_svf)
        paths = {"tools": tools_dir, "src": abs_path, "out": out_svf, "work": work,
                 "eng": eng_abs, "latin": None, "master": None, "range_file": None}
        if kind in ("svf-precomposed", "svf-jamo"):
            # the copy route: a v3 face is copied, a v2 face converted to v3 (svf2to3.py) the way the job does it
            commands = routes.svf_commands(font, paths, extra)
            if not commands:
                shutil.copyfile(abs_path, out_svf)
                return os.path.exists(out_svf)
        elif kind != "dos-raw":
            return False
        else:
            route = routes.route_for(font, "jamo", False)
            if route is None:
                return False
            size = (font.get("sizes") or [None])[0]
            commands = route.commands(font, size, 1, layout, ("2350", None), paths, [list(extra)])
        for argv in commands:
            done = run_bounded(argv, work, TIMEOUT_S, env=env)
            if done.returncode != 0:
                _remove(out_svf)
                return False
        return os.path.exists(out_svf)
    except (OSError, subprocess.SubprocessError, detect.TooLarge, EOFError, zlib.error, ValueError):
        # a ValueError is routes' refusal (a JSET version asked of a JMAP face): no preview. `gzip` raises EOFError for a truncated stream and `zlib.error` for a bad block; neither is an OSError
        _remove(out_svf)
        return False


def chain_for(face_path, latin_path, svf_dir):
    """The `svfline` chain for @p face_path: itself, or `[face, latin]` when the face carries no U+0041.

    @p latin_path is the caller's companion (the batch's own precomposed face); with none, the repository's
    `svf/dos/NEODG16.SVF` under @p svf_dir is the fallback. The face is read through the uncached loader under
    `RENDER_LOCK` (see `svf_png`), so a face rebaked under the same path in this process is seen as it now is.
    """
    with RENDER_LOCK:
        try:
            has_ascii = svfline.Face.load(face_path).has(0x41)
        finally:
            svfline.Face.load.cache_clear()
    if has_ascii:
        return [face_path]
    return [face_path, latin_path or os.path.join(svf_dir, LATIN_FALLBACK)]


def result_png(step_output_abs, latin_abs, svf_dir, out_path):
    """One produced face as a PNG at @p out_path (see `svf_png`); False when nothing could be written."""
    try:
        svf_png(chain_for(step_output_abs, latin_abs, svf_dir), out_path)
        return True
    except Exception:
        _clear(out_path)
        return False


# ---- helpers -----------------------------------------------------------------------------------------------------

def _canvas_ok(w, h):
    """True when a @p w x @p h source-preview canvas is inside `MAX_CANVAS` and `MAX_PIXELS`."""
    return 1 <= w <= MAX_CANVAS and 1 <= h <= MAX_CANVAS and w * h <= MAX_PIXELS


def _draws_sample(face):
    """True when @p face draws `SAMPLE_CHAR` as a real glyph, not as glyph 0 (the `.notdef`).

    Pillow has no cmap question to ask, so the character's mask is compared with the mask of `detect.NOTDEF_CHAR`, a
    noncharacter no font maps: when FreeType gives the font no Unicode charmap (a KSC5601 or Johab BDF), every
    character is glyph 0 and the two masks are equal. A face that has not got the character is glyph 0 too, so a face
    without Hangul draws no source preview. Both masks are sized by `getbbox` against the canvas cap first: a font
    whose `.notdef` is enormous at the requested size is refused rather than rasterized (Pillow's own bomb guard stops
    around 179 Mpx, and several concurrent requests would add up).
    """
    for ch in (SAMPLE_CHAR, detect.NOTDEF_CHAR):
        if not _mask_ok(face, ch):
            return False
    return _mask(face, SAMPLE_CHAR) != _mask(face, detect.NOTDEF_CHAR)


def _mask_ok(face, ch):
    """True when @p ch's mask, sized as `getbbox` reports it, is inside `MAX_CANVAS` / `MAX_PIXELS`."""
    left, top, right, bottom = face.getbbox(ch)
    return _canvas_ok(right - min(left, 0) + 2, bottom - min(top, 0) + 2)


def _mask(face, ch):
    """A character's rendered mask as `(size, bytes)`, the way Pillow 10 hands it back (an ImagingCore)."""
    core = face.getmask(ch, mode="1")
    return core.size, bytes(core)


def _same_file(a, b):
    """True when @p a and @p b are the same file on disk (False when either is not there)."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _remove(path):
    """Remove @p path, ignoring a file that is not there."""
    try:
        os.remove(path)
    except OSError:
        pass


def _clear(path):
    """Remove a PNG output: the failure path of every preview that did not write one of its own."""
    _remove(path)


def _save_png(img, out_path):
    """Save @p img to @p out_path through its own `<out>.<random>.tmp` and `os.replace`.

    A reader (the page's lazy image fetch) never sees a half-written PNG. The temp file is unique per call
    (`tempfile.mkstemp`, as `materialize` does), so two threads writing one output never share a temp name and both
    `replace`s succeed; a failed write removes only its own temp file, never @p out_path. The caller's `_clear` drops
    a stale @p out_path when this call produced no image.
    """
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(out_path) + ".", suffix=".tmp",
                               dir=os.path.dirname(os.path.abspath(out_path)))
    os.close(fd)
    try:
        img.save(tmp, "PNG")            # the `.tmp` name carries no format: say PNG outright
        os.replace(tmp, out_path)
    except Exception:
        _remove(tmp)
        raise
