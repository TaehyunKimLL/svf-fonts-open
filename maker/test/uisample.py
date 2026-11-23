#!/usr/bin/env python3
"""The sample set of the desktop UI test (t_30b843b8): the OFL fonts of `ttf/` plus synthetic Mac / HWP / BDF /
HangulTalk inputs, the settings the UI must make per font, the exact tree the run must write, and the checks of an
output folder.

    python3 -B -P maker/test/uisample.py make DIR                          build DIR/in, DIR/out, DIR/sample.json
    python3 -B -P maker/test/uisample.py check DIR JOB_JSON [--same-as OUT] check DIR/out against the sample

Both print one JSON object. `make` builds the synthetic inputs from the existing fixture builders (no proprietary data).
`check` reads only DIR/out, the picked input roots and the job JSON (`GET /api/jobs/<id>`); its scratch is DIR/check/,
removed again. The library functions (`make`, `apply_ui`, `check`) never refuse a directory; the `/tmp` refusal is the
CLI's. The desktop e2e (`desktop/test/e2e.js`) drives the same table through the page; `test_uisample.py` drives it
through the HTTP API and proves every check fails on a mutation.
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hashlib
import json
import shutil
import unittest

import e2efx
import fixtures
import inputfx
import inputkinds
import jamoset
import macfx
import quality
import svfline

REPO = os.path.realpath(REPO_DIR)

# ---- the sample (definition) -------------------------------------------------------------------------------------

# The dialog picks, in pick order: (button, base, relative path). base "repo" is REPO, "in" is DIR/in.
DIALOG = (
    ("choose-folder", "repo", "ttf/neodgm"),
    ("choose-folder", "repo", "ttf/nanumgothic"),
    ("choose-folder", "repo", "ttf/gowunbatang"),
    ("choose-folder", "repo", "ttf/caveat"),
    ("choose-folder", "in", "mac"),
    ("choose-folder", "in", "v1"),
    ("choose-folder", "in", "hwp"),
    ("choose-folder", "in", "bdf"),
    ("choose-files", "in", "dfont/Synth.dfont"),
)

# What the UI must set per font: key -> (index into DIALOG, path relative to that root, ui). Only keys the page has a
# control for. `htbl` / `latin` are companion paths (relative to the same root); the page maps a path to a font id.
FONTS = {
    "neodgm": (0, "neodgm.ttf", {"kinds": ["precomposed"], "sizes": [16], "bpp": [1], "dest": "dos"}),
    "nanum": (1, "NanumGothic-Bold.ttf", {"kinds": ["precomposed"], "sizes": [17], "bpp": [2], "dest": "dos"}),
    "gowun": (2, "GowunBatang-Bold.ttf", {"kinds": ["precomposed"], "sizes": [17], "bpp": [2], "dest": "dos",
                                          "preset": "dos-u-2bpp"}),
    "caveat": (3, "Caveat-VF.ttf", {"kinds": ["precomposed"], "sizes": [16], "bpp": [1], "dest": "dos",
                                    "instance": {"wght": 700}}),
    "seoul": (4, "Seoul12.rsrc", {"kinds": ["jamo"], "dest": "jamo-extra", "htbl": "InputBackSupport.rsrc",
                                  "latin": "Suitcase.rsrc"}),
    "munjo": (5, "Munjo16.rsrc", {"kinds": ["jamo"], "dest": "jamo-extra"}),
    "dfont": (8, "Synth.dfont", {"kinds": ["precomposed"], "sizes": [16], "bpp": [1], "dest": "dos"}),
    "hwp": (6, "HAN24.FNT", {"kinds": ["jamo"], "dest": "jamo-extra", "dos_layout": "844", "latin": "ASCII.PFT"}),
    "ksc": (7, "ksc.bdf", {"kinds": ["precomposed"], "dest": "dos", "latin": "latin.bdf",
                           "export": {"ttf": True, "bdf": True}}),          # its TTF and BDF too (svf2ttf.py)
    "johab": (7, "johab.bdf", {"kinds": ["jamo"], "dest": "jamo-extra"}),
}
UNTICK = (("nanum-regular", 1, "NanumGothic-Regular.ttf"), ("latin", 7, "latin.bdf"))
NOT_READ = ((6, "HANGUL24.PFT"),)

FACES = {  # key -> face path, relative to the output folder (the expected result, pinned)
    "neodgm": "svf/dos/NEODU16.SVF", "nanum": "svf/dos/NANUM17A.SVF", "gowun": "svf/dos/GOWUN17A.SVF",
    "caveat": "svf/dos/CAVEA16.SVF", "dfont": "svf/dos/SYNTH16.SVF", "ksc": "svf/dos/KSC16.SVF",
    "seoul": "svf/jamo-extra/SEOU12J.SVF", "munjo": "svf/jamo-extra/MUNJ16J.SVF",
    "hwp": "svf/jamo-extra/HAN224J.SVF", "johab": "svf/jamo-extra/JOHA16J.SVF",
}
# The 35 expected files (`<id>` of the build folder is the job id); measured from the API run, asserted by the test.
EXPECTED = (
    "svf/dos/KSC16.ttf", "svf/dos/KSC16.bdf",
    "svf/dos/CAVEA16.SVF", "svf/dos/CAVEA.TXT", "svf/dos/OFLCAVEA.TXT",
    "svf/dos/GOWUN17A.SVF", "svf/dos/GOWUN.TXT", "svf/dos/OFLGOWUN.TXT",
    "svf/dos/KSC16.SVF", "svf/dos/KSC.TXT", "svf/dos/OFLKSC.TXT",
    "svf/dos/NANUM17A.SVF", "svf/dos/NANUM.TXT", "svf/dos/OFLNANUM.TXT",
    "svf/dos/NEODU16.SVF", "svf/dos/NEODU.TXT", "svf/dos/LICNEODU.TXT",
    "svf/dos/SYNTH16.SVF", "svf/dos/SYNTH.TXT",
    "svf/jamo-extra/HAN224J.SVF", "svf/jamo-extra/HAN24.TXT", "svf/jamo-extra/OFLHAN24.TXT",
    "svf/jamo-extra/JOHA16J.SVF", "svf/jamo-extra/JOHAB.TXT", "svf/jamo-extra/OFLJOHAB.TXT",
    "svf/jamo-extra/MUNJ16J.SVF", "svf/jamo-extra/MUNJO.TXT", "svf/jamo-extra/OFLMUNJO.TXT",
    "svf/jamo-extra/SEOU12J.SVF", "svf/jamo-extra/SEOUL.TXT", "svf/jamo-extra/OFLSEOUL.TXT",
    "build-{id}/BUILD.md", "build-{id}/LICENCES.tsv.lines", "build-{id}/FAMILIES.tsv.lines",
    "build-{id}/FACES.TSV.lines",
)
BUILD_FILES = ("BUILD.md", "LICENCES.tsv.lines", "FAMILIES.tsv.lines", "FACES.TSV.lines")
GBATB17 = os.path.join(REPO, "svf", "dos", "GBATB17.SVF")
# Cross-pass equality (`--same-as`): pure-Python faces must be identical; the outline faces differ only by the host's
# Pillow/FreeType vs the pinned wheels (D8), so a difference is a note.
HARD_SAME = ("seoul", "hwp", "johab", "ksc", "munjo")
# The exports (key -> (face path, export path)): read back against their face; across passes the BDF must be identical and
# the TTF identical but for head.created / head.modified (svf2ttf.py stamps the time of the run).
EXPORTS = {"ksc-ttf": ("svf/dos/KSC16.SVF", "svf/dos/KSC16.ttf"), "ksc-bdf": ("svf/dos/KSC16.SVF", "svf/dos/KSC16.bdf")}
NOTE_SAME = ("neodgm", "nanum", "gowun", "caveat", "dfont")


def expected_files(job_id):
    """The expected relative paths for a job id (None: the build folder's entries are left out)."""
    return {p.replace("{id}", job_id) for p in EXPECTED if job_id or "{id}" not in p}


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hashes(roots):
    """{absolute path: sha256} of every file under the directories of @p roots (a file root counts as itself)."""
    out = {}
    for root in roots:
        if os.path.isfile(root):
            out[root] = _sha(root)
            continue
        for dirpath, _dirs, names in os.walk(root):
            for name in names:
                path = os.path.join(dirpath, name)
                out[path] = _sha(path)
    return out


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def _synthetic(base):
    """Write the synthetic inputs under @p base (= DIR/in)."""
    for folder in ("mac", "v1", "hwp", "bdf"):
        _write(os.path.join(base, folder, "LICENSE.txt"), fixtures.SIL_LICENCE)
    _write(os.path.join(base, "mac", "Seoul12.rsrc"), macfx.fbit3_fork(1))
    _write(os.path.join(base, "mac", "InputBackSupport.rsrc"), macfx.htbl_fork(1))
    _write(os.path.join(base, "mac", "Suitcase.rsrc"), macfx.suitcase(12))
    _write(os.path.join(base, "v1", "Munjo16.rsrc"), macfx.fbit1_fork())
    _write(os.path.join(base, "dfont", "Synth.dfont"),
           inputfx.fork([(b"sfnt", 128, "Synth", inputfx.mac_cmap_ttf())]))
    _write(os.path.join(base, "hwp", "HAN24.FNT"), inputfx.dos844_24())
    _write(os.path.join(base, "hwp", "ASCII.PFT"), inputfx.pft_eng())
    _write(os.path.join(base, "hwp", "HANGUL24.PFT"), macfx.hangul_pft())
    fixtures._bdf(os.path.join(base, "bdf", "ksc.bdf"),
                  [(gl, 16, 16, 0, -2, rows) for gl, rows, _w in inputfx.ksc_glyphs_from_neodg()],
                  16, 14, 2, "KSC5601.1987", (16, 16))
    inputfx.latin_bdf_from_neodg(os.path.join(base, "bdf", "latin.bdf"))
    fixtures._bdf(os.path.join(base, "bdf", "johab.bdf"), fixtures._johab_glyphs(), 16, 13, 3, "johab", (16, 16))


def make(dir_):
    """Build the sample under @p dir_ (new or empty): `in/`, an empty `out/`, `sample.json`; returns the sample dict."""
    dir_ = os.path.realpath(dir_)
    if os.path.isdir(dir_) and os.listdir(dir_):
        raise FileExistsError("uisample: %s is not empty" % dir_)
    os.makedirs(dir_, exist_ok=True)
    base = os.path.join(dir_, "in")
    _synthetic(base)
    out = os.path.join(dir_, "out")
    os.makedirs(out)
    dialog = [{"button": button, "path": os.path.join(REPO if where == "repo" else base, *rel.split("/"))}
              for button, where, rel in DIALOG]
    for entry in dialog:
        if not os.path.exists(entry["path"]):
            raise FileNotFoundError(entry["path"])
    fonts = {}
    for key, (idx, path, ui) in FONTS.items():
        fonts[key] = {"root_path": dialog[idx]["path"], "path": path, "ui": json.loads(json.dumps(ui))}
    sample = {"dialog": dialog, "output": out, "fonts": fonts, "untick": [p for _k, _i, p in UNTICK],
              "not_read": [p for _i, p in NOT_READ], "faces": len(FACES),
              "inputs": hashes([e["path"] for e in dialog])}
    with open(os.path.join(dir_, "sample.json"), "w", encoding="utf-8") as fh:
        json.dump(sample, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return sample


def apply_ui(job):
    """The settings of a detected @p job with the sample's table applied (the API twin of the page script): every font
    unselected, then each sample font selected with its `ui`. Returns the settings dict (job is not changed)."""
    st = json.loads(json.dumps(job["settings"]))
    fonts = job["fonts"]

    def fid(root, path):
        hits = [f["id"] for f in fonts if f["root"] == root and f["path"] == path]
        assert len(hits) == 1, (root, path, hits)
        return hits[0]
    for per in st["fonts"].values():
        per["selected"] = False
    for key, (idx, path, ui) in FONTS.items():
        per = st["fonts"][fid(idx, path)]
        per["selected"] = True
        for field in ("kinds", "sizes", "bpp", "dest", "preset", "instance", "dos_layout"):
            if field in ui:
                per[field] = json.loads(json.dumps(ui[field]))
        if "export" in ui:
            per["options"] = {"export": dict(ui["export"])}
        if "htbl" in ui:
            per["htbl_companion"] = fid(idx, ui["htbl"])
        if "latin" in ui:
            per["latin_companion"] = fid(idx, ui["latin"])
    return st


# ---- the checks ---------------------------------------------------------------------------------------------------

class _Shim(unittest.TestCase):
    """The `test` argument the reused helpers expect: its assert methods raise."""

    def runTest(self):
        pass


def _walk_rel(root):
    out = set()
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            out.add(os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/"))
    return out


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def draws_latin(face_path, text="A"):
    """True when @p text (Latin) draws ink with the face: the Latin-only twin of `e2efx.assert_draws`."""
    width, ascent, descent = svfline.measure([face_path], text)
    buf = svfline.layout([face_path], text, 1, ascent + 1, width + 2, ascent + descent + 2)
    return any(buf)


def _check_files(sample, out_dir, job, fails, scratch):
    jid = job.get("id") or ""
    want = expected_files(jid)
    have = _walk_rel(out_dir)
    result = job.get("result")
    if not result or not jid:
        fails.append("files: job has no result")
        for rel in sorted(want - have):
            fails.append("files: missing %s" % rel)
        return
    for rel in sorted(want - have):
        fails.append("files: missing %s" % rel)
    for rel in sorted(have - want):
        fails.append("files: unexpected %s" % rel)
    for name in sorted(n for n in (os.listdir(out_dir) if os.path.isdir(out_dir) else []) if n.startswith(".svf-maker-")):      # an empty one counts
        fails.append("files: work folder not swept: %s" % name)
    reported = set(result.get("files") or [])
    for rel in sorted(reported - have):
        fails.append("files: reported by the job but not on disk: %s" % rel)
    for rel in sorted(have - reported):
        fails.append("files: on disk but not reported by the job: %s" % rel)
    written = {s.get("written") for s in job.get("steps") or [] if s.get("written")}
    for rel in sorted(p for p in want if p.endswith(".SVF")):
        if rel not in written:
            fails.append("files: no step wrote %s" % rel)
    if job.get("state") != "done":
        fails.append("files: job state is %s, not done" % job.get("state"))


def _check_parse(out_dir, fails):
    """Every SVF parses as v3; failures name the file."""
    for rel in sorted(p for p in _walk_rel(out_dir) if p.lower().endswith(".svf")):
        try:
            face = jamoset.parse_svfn(_read(os.path.join(out_dir, rel)))
            if face.version != 3:
                fails.append("parse: %s is version %s" % (rel, face.version))
        except Exception as exc:
            fails.append("parse: %s: %s: %s" % (rel, type(exc).__name__, str(exc).splitlines()[0] if str(exc) else ""))


def _check_facecheck(out_dir, scratch):
    d = os.path.join(scratch, "fc")
    shutil.copytree(os.path.join(out_dir, "svf"), os.path.join(d, "svf"))
    inputkinds._facecheck(_Shim(), d)


def _check_mkindex(out_dir, job, scratch):
    side = os.path.join(out_dir, "build-%s" % job["id"])
    lines = {name: _read(os.path.join(side, name)) for name in BUILD_FILES}
    e2efx.merge_check(_Shim(), os.path.join(out_dir, "svf"), lines, base_repo=False, scratch=os.path.join(scratch, "mk"))


def _check_pins_and_ink(out_dir, fails):
    gow = os.path.join(out_dir, FACES["gowun"])
    try:
        if _read(gow) != _read(GBATB17):
            fails.append("pin: %s is not byte-equal to svf/dos/GBATB17.SVF" % FACES["gowun"])
    except OSError as exc:
        fails.append("pin: %s: %s" % (FACES["gowun"], exc))
    for key, rel in sorted(FACES.items()):
        path = os.path.join(out_dir, rel)
        try:
            face = svfline.Face.load(path)
            if face.has(0xAC00):
                e2efx.assert_draws(_Shim(), path)
            elif not draws_latin(path):
                fails.append("ink: %s draws a blank U+0041" % rel)
        except Exception as exc:
            fails.append("ink: %s: %s: %s" % (rel, type(exc).__name__, str(exc).splitlines()[0] if str(exc) else ""))


def _check_exports(out_dir, fails):
    """Every export holds exactly its face's characters (`quality.export_facts`, the job's own read-back)."""
    for key, (face, export) in sorted(EXPORTS.items()):
        try:
            quality.export_facts(os.path.join(out_dir, export), export.rsplit(".", 1)[1], os.path.join(out_dir, face))
        except Exception as exc:
            fails.append("export: %s: %s: %s" % (export, type(exc).__name__, (str(exc).splitlines() or [""])[0]))


def _ttf_same(a, b):
    """True when two TTFs are equal once head.created / head.modified are set equal (each saved again as it is)."""
    import io
    from fontTools.ttLib import TTFont
    out = []
    for path in (a, b):
        with TTFont(path, recalcTimestamp=False, recalcBBoxes=False) as font:
            font["head"].created = font["head"].modified = 0
            buf = io.BytesIO()
            font.save(buf)
            out.append(buf.getvalue())
    return out[0] == out[1]


def _check_inputs(sample, fails):
    now = hashes([e["path"] for e in sample["dialog"]])
    want = sample["inputs"]
    for path in sorted(set(want) - set(now)):
        fails.append("inputs: removed %s" % path)
    for path in sorted(set(now) - set(want)):
        fails.append("inputs: added %s" % path)
    for path in sorted(p for p in want if p in now and want[p] != now[p]):
        fails.append("inputs: changed %s" % path)


def _check_same_as(out_dir, other, fails, notes):
    for key in HARD_SAME + NOTE_SAME:
        rel = FACES[key]
        a, b = os.path.join(out_dir, rel), os.path.join(other, rel)
        if not (os.path.isfile(a) and os.path.isfile(b)):
            fails.append("same-as: %s is missing in %s" % (rel, "this tree" if not os.path.isfile(a) else other))
        elif _read(a) != _read(b):
            if key in HARD_SAME:
                fails.append("same-as: %s differs from %s" % (rel, other))
            else:
                notes.append("%s differs from the dev pass (host Pillow vs pinned wheels, D8)" % os.path.basename(rel))
    for key, (_face, rel) in sorted(EXPORTS.items()):
        a, b = os.path.join(out_dir, rel), os.path.join(other, rel)
        if not (os.path.isfile(a) and os.path.isfile(b)):
            fails.append("same-as: %s is missing in %s" % (rel, "this tree" if not os.path.isfile(a) else other))
        elif rel.endswith(".ttf") and not _ttf_same(a, b):
            fails.append("same-as: %s differs from %s (beyond its timestamps)" % (rel, other))
        elif rel.endswith(".bdf") and _read(a) != _read(b):
            fails.append("same-as: %s differs from %s" % (rel, other))


def check(sample, out_dir, job, same_as=None, notes=None):
    """Check @p out_dir against the sample; returns the failure lines (empty: ok). Notes (a list, when given) get
    the cross-pass differences that are not failures. Scratch is `<out_dir>/../check`, removed afterwards."""
    out_dir = os.path.realpath(out_dir)
    notes = notes if notes is not None else []
    fails = []
    scratch = os.path.join(os.path.dirname(out_dir), "check")
    shutil.rmtree(scratch, ignore_errors=True)
    os.makedirs(scratch)
    saved = sys.dont_write_bytecode                  # merge_check imports web/mkindex.py in-process
    sys.dont_write_bytecode = True
    try:
        have_result = bool(job.get("result") and job.get("id"))
        steps = [("files", lambda: _check_files(sample, out_dir, job, fails, scratch)),
                 ("parse", lambda: _check_parse(out_dir, fails)),
                 ("facecheck", lambda: _check_facecheck(out_dir, scratch) if have_result and
                  os.path.isdir(os.path.join(out_dir, "svf")) else None),
                 ("mkindex", lambda: _check_mkindex(out_dir, job, scratch) if have_result and
                  os.path.isdir(os.path.join(out_dir, "build-%s" % job["id"])) else None),
                 ("pins", lambda: _check_pins_and_ink(out_dir, fails) if have_result else None),
                 ("export", lambda: _check_exports(out_dir, fails) if have_result else None),
                 ("inputs", lambda: _check_inputs(sample, fails))]
        if same_as:
            steps.append(("same-as", lambda: _check_same_as(out_dir, os.path.realpath(same_as), fails, notes)))
        for name, fn in steps:
            try:
                fn()
            except Exception as exc:
                first = (str(exc).splitlines() or [""])[0]
                fails.append("%s: %s: %s" % (name, type(exc).__name__, first))
    finally:
        sys.dont_write_bytecode = saved
        shutil.rmtree(scratch, ignore_errors=True)
    return fails


# ---- the CLI ------------------------------------------------------------------------------------------------------

def _under_tmp(path):
    real = os.path.realpath(path)
    return real == "/tmp" or real.startswith("/tmp/")


def main(argv=None):
    sys.dont_write_bytecode = True
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[0] not in ("make", "check"):
        sys.stderr.write("usage: uisample.py make DIR | check DIR JOB_JSON [--same-as OTHER_OUT]\n")
        return 2
    cmd, dir_ = argv[0], argv[1]
    if _under_tmp(dir_):
        sys.stderr.write("uisample: refusing a directory under /tmp\n")
        return 2
    if cmd == "make":
        if len(argv) != 2:
            sys.stderr.write("usage: uisample.py make DIR\n")
            return 2
        try:
            sample = make(dir_)
        except FileExistsError as exc:
            sys.stderr.write("%s\n" % exc)
            return 2
        json.dump(sample, sys.stdout)
        sys.stdout.write("\n")
        return 0
    rest = argv[2:]
    same_as = None
    if "--same-as" in rest:
        i = rest.index("--same-as")
        same_as = rest[i + 1] if i + 1 < len(rest) else None
        rest = rest[:i] + rest[i + 2:]
    if len(rest) != 1 or ("--same-as" in argv and not same_as):
        sys.stderr.write("usage: uisample.py check DIR JOB_JSON [--same-as OTHER_OUT]\n")
        return 2
    try:
        with open(os.path.join(dir_, "sample.json"), encoding="utf-8") as fh:
            sample = json.load(fh)
        with open(rest[0], encoding="utf-8") as fh:
            job = json.load(fh)
        if not isinstance(sample, dict) or not isinstance(job, dict) or not isinstance(sample.get("output"), str):
            raise ValueError("not a sample / job object")
    except (OSError, ValueError) as exc:
        sys.stderr.write("uisample: cannot read the sample or the job: %s: %s\n"
                         % (type(exc).__name__, (str(exc).splitlines() or [""])[0]))
        return 2
    if os.path.realpath(sample["output"]) != os.path.realpath(os.path.join(dir_, "out")):
        sys.stderr.write("uisample: sample.json names an output folder other than DIR/out\n")
        return 2
    notes = []
    fails = check(sample, sample["output"], job, same_as=same_as, notes=notes)
    if fails:
        json.dump({"ok": False, "failures": fails, "notes": notes}, sys.stdout)
        sys.stdout.write("\n")
        return 1
    json.dump({"ok": True, "notes": notes}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
