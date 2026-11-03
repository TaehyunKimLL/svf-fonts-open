#!/usr/bin/env python3
"""The output zip, the `.lines` files and the build log.

`write_zip` is the last thing a job does: it reads back every `done` `precomposed`/`jamo` step, keeps a produced face
that is byte-equal to a shipped one out of the zip (it is named in the lines instead), reuses a licence or note text
that already exists under `svf/`, and writes `svf-maker-<id>.zip` holding `svf/...` plus a sidecar folder with
`BUILD.md` (`log.md` + the zip summary + the rows that may duplicate an existing row), `FACES.TSV.lines`,
`LICENCES.tsv.lines` and `FAMILIES.tsv.lines`. The `.lines` files are what the owner appends to the repository's three
TSVs, so they are produced in exactly the formats `web/mkindex.py` reads.

`append_log`, `log_header`, `log_step` and `repo_head` build `log.md` while the worker runs; `write_zip` never writes a
partial zip: everything (the note texts included) is prepared before the archive is opened, and a failure raises (a
`naming.note_text` refusal raises `NoteRefused`, a name that exists with other bytes raises `NameClash`). The caller
catches one exception type and, because `write_zip` restores the `identical_to` it set before raising, a failed call
leaves the steps as they were.

The library assumes `maker/` and `tools/` are on sys.path (the entry points set it).
"""

import datetime
import fnmatch
import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import zipfile

import naming
import presets
import settings

# Every zip entry is stamped with this mtime so the archive's bytes are reproducible (Global Constraints).
ZIP_TIME = (1980, 1, 1, 0, 0, 0)

# FACES.TSV's columns, in the order the repository's file uses them.
FACES_COLUMNS = ["file", "family", "px", "bpp", "cell", "sets_ini_med_fin", "classes_lead_tail", "bytes",
                 "quality_all", "quality_ks2350", "quality_freq", "quality_top500", "syllables_compared",
                 "licence", "hangul_baseline_row", "latin_baseline_row"]

# The faces FACES.TSV describes: a jamo set in jamo-extra.
FACES_DEST = "jamo-extra"

DUPLICATE_HEADING = "## Rows that may duplicate an existing row"


class NameClash(Exception):
    """A produced face's or text's name already exists in its destination with other bytes.

    `settings.run_ready` refuses such a name before the job starts, so this fires only when the checkout changed
    while the job ran (or two entries of one job collide). The message names the owner and the `svf/`-relative path,
    which is what the job's error says.
    """

    def __init__(self, step_id, path):
        super().__init__("%s: %s already exists in svf/ with different bytes" % (step_id, path))
        self.step_id = step_id
        self.path = path


class NoteRefused(ValueError):
    """`naming.note_text` refused a note (a control character, or a line over 512 bytes).

    `write_zip` sets `job["error"]` to the same message and raises this, so the runner has one failure path
    (Q2 of the fix round): nothing returns `None`.
    """


# ---- the build log ---------------------------------------------------------------------------------------------

def append_log(job_dir, text):
    """Append @p text to `<job_dir>/log.md` (UTF-8), creating it when it is not there yet."""
    with open(os.path.join(job_dir, "log.md"), "a", encoding="utf-8") as f:
        f.write(text)


def repo_head(repo_dir):
    """`git -C REPO rev-parse HEAD` stripped, `"unknown"` when git is missing, fails or prints nothing."""
    try:
        proc = subprocess.run(["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if proc.returncode != 0:
        return "unknown"
    head = proc.stdout.decode("utf-8", "replace").strip()
    return head or "unknown"


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc)


def _shown(value):
    """A step field as the log shows it: an absent value is an empty cell, not `None`."""
    return "" if value is None else value


def _one_line(text):
    """@p text with every newline escaped: a command line in the log or the note is exactly one line."""
    return str(text).replace("\r", "\\r").replace("\n", "\\n")


def _json(value):
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _effective_settings(job, font_id):
    """One font's effective settings (Shared data shapes), or `{}` when the job cannot supply them.

    The build log is diagnostic: a malformed job must not stop it, so a lookup failure shows what is at hand.
    """
    try:
        return settings.effective(job.get("fonts") or [], job.get("settings") or {}, font_id)
    except (KeyError, TypeError, ValueError):
        return {}


def log_header(job, repo_head_value):
    """The log's head: the job id, the date, the checkout's HEAD and every font with its facts and settings.

    Per font: its id, path, label, family/style, sizes, coverage, jamo state and licence choice, then the effective
    settings (the preset name and `presets.PRESETS[name]["argv"]` in full) as fenced JSON, then the font's detection
    error (the traceback) in a fenced block when it carries one.
    """
    fonts = job.get("fonts") or []
    lines = ["# svf-maker %s" % (job.get("id") or ""), "",
             "Date: %s" % _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
             "repo HEAD %s" % repo_head_value, "", "## Fonts", ""]
    for font in fonts:
        font_id = font.get("id")
        eff = _effective_settings(job, font_id)
        preset = eff.get("preset")
        shown = dict(eff)
        shown["preset_argv"] = presets.PRESETS.get(preset, {}).get("argv") if isinstance(preset, str) else None
        lines.append("- `%s` `%s` %s %s/%s sizes=%s coverage=%s jamo=%s licence=%s" % (
            font_id, font.get("path"), font.get("label"), font.get("family"), font.get("style"),
            json.dumps(font.get("sizes")), json.dumps(font.get("coverage")), json.dumps(font.get("jamo")),
            json.dumps(eff.get("licence"), sort_keys=True)))
        lines += ["```json", _json(shown), "```"]
        if font.get("error"):
            lines += ["", "Detection error:", "```", str(font["error"]), "```"]
        lines.append("")
    return "\n".join(lines) + "\n"


def _step_title(step):
    """The step's heading: a `prepare` or `source` step has no size, bpp or face name."""
    if step.get("kind") in ("prepare", "source"):
        return "## %s %s %s" % (step.get("id"), step.get("font"), step.get("kind"))
    return "## %s %s %s %spx %sbpp %s" % (step.get("id"), step.get("font"), step.get("kind"),
                                          step.get("size"), step.get("bpp"), step.get("name"))


def _command_lines(step, src=None):
    """The step's command lines: `shlex.join(argv)` per argv, or the copy a step with no argv performs.

    A copy step (`argv == []`, an SVF source) is not a subprocess: the worker copies the upload's file to the step's
    output, so its line is `copy <src> -> <out>`. `log_step` has no font to hand and falls back to `step["src"]`;
    `write_zip` passes the font's upload path, which is what the shipped note must name.
    """
    argvs = step.get("argv") or []
    if not argvs:
        source = src if src is not None else (step.get("src") or "<src>")
        return ["copy %s -> %s" % (source, step.get("output") or "<out>")]
    return [_one_line(shlex.join(argv)) for argv in argvs]


def log_step(step, stdout, stderr):
    """The log's block for one step: its heading, every command with its exit and seconds, then its result.

    `facts`, `quality` and `identical_to` are the values read back from the produced file, each as fenced JSON; a
    step that failed logs its error instead of facts.
    """
    lines = [_step_title(step), ""]
    for command in _command_lines(step):
        lines += ["```sh", command, "```",
                  "exit: %s" % _shown(step.get("exit")), "seconds: %s" % _shown(step.get("seconds")), ""]
    lines += ["stdout:", "```", (stdout or "").rstrip("\n"), "```", "",
              "stderr:", "```", (stderr or "").rstrip("\n"), "```", ""]
    if step.get("error"):
        lines += ["error: %s" % step["error"], ""]
    lines += ["facts:", "```json", _json(step.get("facts")), "```", "",
              "quality:", "```json", _json(step.get("quality")), "```", "",
              "identical_to:", "```json", _json(step.get("identical_to")), "```", ""]
    return "\n".join(lines) + "\n"


# ---- the `.lines` files ------------------------------------------------------------------------------------------

def _num(value):
    """A number cell: the value as text, or empty when there is none (the lines' "no number" rule)."""
    return "" if value is None else str(value)


def _is_jamo(step):
    """True when the step's face carries a JSET the renderer would use (`facts["jset"] is not None`).

    The header's `jamo` flag is not this: a face with no usable JSET loads as a plain precomposed SVFN, and FACES.TSV
    describes the jamo sets only.
    """
    facts = step.get("facts")
    return isinstance(facts, dict) and facts.get("jset") is not None


def _family_style(font):
    """The FACES.TSV `family` cell: the detected family and style (spec: "the detected family and style")."""
    return " ".join(part for part in (font.get("family") or "", font.get("style") or "") if part)


def _sets_cell(jset):
    """`ni/nm/nf`; a JMAP face (no sets) writes `-`."""
    return "-" if jset.get("sets") is None else "%d/%d/%d" % tuple(jset["sets"])


def _classes_cell(jset):
    """`lcxtc`; a JMAP face (no classes) writes `-`."""
    return "-" if jset.get("classes") is None else "%dx%d" % tuple(jset["classes"])


def faces_line(step, font, licence_name):
    """One FACES.TSV row (16 columns, no trailing newline) for a jamo face.

    Raises `ValueError` for a step whose facts carry no usable JSET: FACES.TSV lists jamo sets only, and the row's
    sets and classes come from that header. `hangul_baseline_row` is the 0-based row of the baseline, `ascent - 1`
    (Q1 of the fix round: every existing row holds that, and the column is a row index).
    """
    facts = step.get("facts")
    jset = facts.get("jset") if isinstance(facts, dict) else None
    if jset is None:
        raise ValueError("faces_line: %s has no usable JSET" % step.get("id"))
    quality = step.get("quality") or {}
    cell = "%dx%d" % (facts["cell"][0], facts["cell"][1])
    ascent = facts.get("ascent")
    baseline_row = "" if ascent is None else ascent - 1
    values = [step.get("name"), _family_style(font), _num(step.get("size")), _num(step.get("bpp")), cell,
              _sets_cell(jset), _classes_cell(jset), _num(facts.get("bytes")),
              _num(quality.get("all")), _num(quality.get("ks2350")), "", "", _num(quality.get("compared")),
              licence_name or "", _num(baseline_row), ""]
    return "\t".join(str(value) for value in values)


def licences_line(dest, name, note_name, licence_name):
    """One LICENCES.tsv row: `"<dest>/<NAME>.SVF\\t<note>,<licence>"` (both texts `svf/`-relative), no newline."""
    return "%s/%s\t%s,%s" % (dest, name, note_name, licence_name)


def families_line(dest, name, family, style):
    """One FAMILIES.tsv row: `"svf/<dest>/<NAME>.SVF\\t<family>\\t<style>\\t"` (an empty variant), no newline."""
    return "svf/%s/%s\t%s\t%s\t" % (dest, name, family, style)


# ---- the zip ---------------------------------------------------------------------------------------------------

def _read(path):
    """The bytes of @p path, or `None` when it cannot be read."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def _licence_bytes(job_dir, repo_dir, eff):
    """The chosen licence's bytes: an upload's file, the `svf/` file a `repo` path names, or a `text` as UTF-8.

    `None` when there is no licence or it cannot be read (the lines then name the chosen name and nothing is
    written; `settings.run_ready` refuses a selected font without a readable licence before the job runs). An
    `upload` path that resolves outside `<job_dir>/upload` raises `ValueError`: `write_zip` is the last gate before
    the zip is unpacked into the owner's checkout (J8).
    """
    licence = eff.get("licence")
    if not isinstance(licence, dict):
        return None
    kind = licence.get("kind")
    if kind == "text":
        text = licence.get("text")
        return text.encode("utf-8") if isinstance(text, str) else None
    path = licence.get("path")
    if not isinstance(path, str):
        return None
    if kind == "repo":
        root = os.path.realpath(os.path.join(repo_dir, "svf"))
        full = os.path.realpath(os.path.join(root, path))
        if not full.startswith(root + os.sep):
            raise ValueError("zipout: licence path %r is outside svf/" % (path,))
        return _read(full)
    if kind == "upload":
        root = os.path.realpath(os.path.join(job_dir, "upload"))
        full = os.path.realpath(os.path.join(root, path))
        if full != root and not full.startswith(root + os.sep):
            raise ValueError("zipout: licence path %r is outside the upload directory" % (path,))
        return _read(full)
    return None


def _check_entry_path(entry):
    """Refuse a zip entry name that could escape the unpack root (J2): a `..` component, a leading `/`, a `//`."""
    if entry.startswith("/") or "//" in entry or ".." in entry.split("/"):
        raise ValueError("zipout: refusing entry path %r" % (entry,))


def _check_dest(dest):
    if not isinstance(dest, str) or not naming.DEST_RE.match(dest):
        raise ValueError("zipout: refusing destination %r" % (dest,))


def _check_face_name(name):
    if not isinstance(name, str) or not naming.NAME_RE.match(name):
        raise ValueError("zipout: refusing face name %r" % (name,))


def _check_text_name(name):
    if not isinstance(name, str) or not naming.TXT_RE.match(name):
        raise ValueError("zipout: refusing text name %r" % (name,))


def _add_entry(entries, name, data, owner):
    """Add one `(entry name, bytes)` to @p entries: an equal repeat is dropped, a different one raises `NameClash`.

    Two selected fonts may legitimately share one licence file (equal bytes), and two faces of one job may hold
    equal bytes; a repeat with other bytes could only come from a checkout that changed under the job.
    """
    _check_entry_path(name)
    if name in entries:
        if entries[name] == data:
            return False
        raise NameClash(owner, name)
    entries[name] = data
    return True


def _text_entry(data, dest, name, index, owner):
    """`(entry name or None, the `svf/`-relative path the lines name)` for a text at `svf/<dest>/<name>`.

    A text byte-equal to a file already under `svf/` is not written: the existing path is named instead ("identical
    bytes share one file"). A text with no bytes or no name is not written either. A name that already exists in
    @p dest with other bytes raises `NameClash`, as a face's name does (J3).
    """
    if data is None or not name:
        return (None, "")
    _check_text_name(name)
    existing = index.check_text(data)
    if existing is not None:
        return (None, existing)
    rel = "%s/%s" % (dest, name)
    if dest in index.unlisted or name.upper() in index.names.get(dest, ()):
        raise NameClash(owner, rel)
    return ("svf/" + rel, rel)


def _faces_licence(licence_ref, dest, licence_name):
    """The FACES.TSV `licence` cell: the file that exists, named as the existing rows name it (J4).

    A licence written into the face's own destination keeps its plain name (`OFLGOTHA.TXT`); a licence reused from
    another folder is named by its `svf/`-relative path (`dos/OFL.TXT`), as the LICENCES.tsv rows do.
    """
    if not licence_ref:
        return licence_name or ""
    prefix = dest + "/"
    return licence_ref[len(prefix):] if licence_ref.startswith(prefix) else licence_ref


def note_names(faces):
    """The names the note's first line lists: the written faces and the existing file each identical face equals."""
    names = [face["identical_to"].rpartition("/")[2] if face["identical_to"] else face["name"] for face in faces]
    return list(dict.fromkeys(names))


def note_commands(steps, font):
    """Every command line of @p steps, in run order, each exactly one line (the note's provenance block).

    A copy step's line names the font's upload path, never `step["src"]` (J6): the shipped note must be reproducible.
    """
    path = font.get("path")
    src = "upload/%s" % path if path else "<src>"
    commands = []
    for step in steps:
        commands += _command_lines(step, src=src)
    return commands


def _lines_bytes(rows):
    """A `.lines` file's bytes: one row per line and a final newline (an empty file when there are no rows)."""
    return ("\n".join(rows) + "\n").encode("utf-8") if rows else b""


def _zip_summary(result):
    """The zip's own summary: what was written, what was skipped as identical, and the failed steps."""
    lines = ["## Zip", "", "- zip: %s" % result["zip"]]
    for entry in result["written"]:
        lines.append("- written: %s" % entry)
    for item in result["skipped"]:
        lines.append("- skipped: %s (identical to %s)" % (item["name"], item["identical_to"]))
    failed = result["failed_steps"]
    lines.append("- failed steps: %s" % (", ".join(failed) if failed else "none"))
    return "\n".join(lines) + "\n\n"


def _mkindex(repo_dir):
    """`<repo_dir>/web/mkindex.py` loaded by path: it is not on `sys.path`, and its readers are the lines' spec."""
    path = os.path.join(repo_dir, "web", "mkindex.py")
    spec = importlib.util.spec_from_file_location("mkindex", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _existing_globs(repo_dir):
    """The globs of the repository's `web/LICENCES.tsv` (`mkindex.read_licences`); `[]` when it cannot be read."""
    path = os.path.join(repo_dir, "web", "LICENCES.tsv")
    if not os.path.isfile(path):
        return []
    try:
        return [row[0] for row in _mkindex(repo_dir).read_licences(path)]
    except Exception:                                    # a malformed LICENCES.tsv must not fail the job
        return []


def _split_rel(rel):
    """`("dos", "NEODG16.SVF")` for an `svf/`-relative path (the row helpers take a dest and a name)."""
    dest, _, name = rel.rpartition("/")
    return dest, name


def write_zip(job, job_dir, index, fonts_by_id, effective, repo_dir):
    """Write `svf-maker-<id>.zip` for @p job's `done` faces and return the Job's `result` dict.

    A `precomposed`/`jamo` step whose output is byte-equal to a shipped file is skipped (`step["identical_to"]` is
    set, and the lines name the existing file), and so is a second new face whose bytes equal a face this job already
    wrote (`identical_to` is that face's `svf/`-relative path, J7); a name that exists with other bytes raises
    `NameClash`; everything else is written under `svf/<dest>/<name>`, one entry per name (an equal repeat is
    dropped, J1). `dest`, the face names and the text names are checked against `naming`'s patterns and no entry
    path may hold a `..` component, a leading `/` or a `//` (J2). Per font with at least one written or identical
    face, its licence and its note are written too, unless an equal text already exists under `svf/`; a text name
    that exists in the destination with other bytes raises `NameClash` (J3). `LICENCES.tsv.lines` has a row per
    written and per identical face, `FACES.TSV.lines` the written jamo sets in `jamo-extra` (the licence cell names
    the file that exists, J4) and `FAMILIES.tsv.lines` every written face. `BUILD.md` is `log.md` plus the summary
    plus the rows that may duplicate an existing one (an identical face's row, and a new face's row a
    `web/LICENCES.tsv` glob matches). Every `.lines` file ends with a newline (J9) and the archive is written to
    `<out>.zip.tmp` and `os.replace`d into place, the tmp file removed on any failure (J11).

    A note `naming.note_text` refuses (a control character or a line over 512 bytes) sets `job["error"]` to
    `"note for <font>: <message>"`, appends it to the log and raises `NoteRefused(message)`. Any failure restores the
    `identical_to` values this call set, so a failed call leaves the steps as they were. The caller saves the job
    afterwards: `identical_to` is set on its steps.
    """
    touched = []                                         # (step, the identical_to it had) to restore on failure
    try:
        return _write_zip(job, job_dir, index, fonts_by_id, effective, repo_dir, touched)
    except BaseException:
        for step, previous in touched:
            step["identical_to"] = previous
        raise


def _write_zip(job, job_dir, index, fonts_by_id, effective, repo_dir, touched):
    """`write_zip`'s body; @p touched collects the steps whose `identical_to` a failure must restore."""
    job_id = job.get("id") or ""
    steps = job.get("steps") or []
    entries = {}                                         # zip entry name -> bytes, built before the archive is opened
    written, skipped, faces = [], [], []
    by_sha = {}                                          # sha256 -> the first face this job writes at that digest

    for step in steps:
        if step.get("state") != "done" or step.get("kind") not in ("precomposed", "jamo"):
            continue                                     # a prepare step's master.json is never a face
        font_id = step.get("font")
        font = fonts_by_id.get(font_id) or {}
        eff = effective(font_id)
        dest, name = eff.get("dest"), step.get("name")
        _check_dest(dest)
        _check_face_name(name)
        data = _read(os.path.join(job_dir, step.get("output") or ""))
        if data is None:
            raise ValueError("zipout: step %s is done but its face %r cannot be read" % (step.get("id"), step.get("output")))
        status, rel = index.check_face(dest, name, data)
        if status == "clash":
            raise NameClash(step.get("id"), "%s/%s" % (dest, name))
        if status == "identical":
            touched.append((step, step.get("identical_to")))
            step["identical_to"] = rel
            entry = "svf/%s/%s" % (dest, name)
            skipped.append({"name": entry, "identical_to": rel})
            faces.append({"step": step, "font": font, "font_id": font_id, "eff": eff, "dest": dest, "name": name,
                          "row_path": rel, "identical_to": rel})
            continue
        rel = "%s/%s" % (dest, name)
        digest = hashlib.sha256(data).hexdigest()
        first = by_sha.get(digest)
        if first is not None:
            touched.append((step, step.get("identical_to")))
            step["identical_to"] = first
            skipped.append({"name": "svf/" + rel, "identical_to": first})
            faces.append({"step": step, "font": font, "font_id": font_id, "eff": eff, "dest": dest, "name": name,
                          "row_path": first, "identical_to": first})
            continue
        _add_entry(entries, "svf/" + rel, data, step.get("id"))
        by_sha[digest] = rel
        written.append("svf/" + rel)
        faces.append({"step": step, "font": font, "font_id": font_id, "eff": eff, "dest": dest, "name": name,
                      "row_path": rel, "identical_to": None})

    # Per font with at least one written or identical face: the licence and the note.
    refs = {}                                            # font id -> {"licence_name", "licence", "note"}
    for font_id in dict.fromkeys(face["font_id"] for face in faces):
        mine = [face for face in faces if face["font_id"] == font_id]
        font = mine[0]["font"]
        eff = mine[0]["eff"]
        dest = mine[0]["dest"]
        licence_name = eff.get("licence_name") if isinstance(eff.get("licence_name"), str) else ""
        note_name = eff.get("note_name") if isinstance(eff.get("note_name"), str) else ""
        licence_data = _licence_bytes(job_dir, repo_dir, eff)
        if licence_data is None and isinstance(eff.get("licence"), dict):
            raise ValueError("zipout: the licence of %s cannot be read" % (font_id,))
        licence_entry, licence_ref = _text_entry(licence_data, dest, licence_name, index, font_id)
        if licence_entry:
            _add_entry(entries, licence_entry, licence_data, font_id)
        font_steps = [step for step in steps if step.get("font") == font_id and step.get("state") == "done"]
        try:
            note_text = naming.note_text(font.get("family") or "", font.get("style") or "", note_names(mine),
                                         os.path.basename(font.get("path") or ""), font.get("version") or "",
                                         _utc_now().date().isoformat(), note_commands(font_steps, font))
        except ValueError as exc:
            message = "note for %s: %s" % (font_id, exc)
            job["error"] = message
            append_log(job_dir, "\n%s\n" % message)
            raise NoteRefused(message)                   # never a partial zip
        note_entry, note_ref = _text_entry(note_text.encode("utf-8"), dest, note_name, index, font_id)
        if note_entry:
            _add_entry(entries, note_entry, note_text.encode("utf-8"), font_id)
        refs[font_id] = {"licence_name": licence_name, "licence": licence_ref, "note": note_ref}

    # The three `.lines` files and the rows that may duplicate an existing row.
    licences, faces_rows, families, duplicate_rows = [], [], [], []
    globs = _existing_globs(repo_dir)
    for face in faces:
        font, step, ref = face["font"], face["step"], refs[face["font_id"]]
        row_dest, row_name = _split_rel(face["row_path"])
        row = licences_line(row_dest, row_name, ref["note"], ref["licence"])
        licences.append(row)
        if face["identical_to"] is not None:
            duplicate_rows.append(row)
        elif any(fnmatch.fnmatchcase(face["row_path"], glob) for glob in globs):
            duplicate_rows.append(row)
        if face["identical_to"] is None:
            families.append(families_line(face["dest"], face["name"], font.get("family") or "",
                                          font.get("style") or ""))
            if face["dest"] == FACES_DEST and _is_jamo(step):
                faces_rows.append(faces_line(step, font,
                                             _faces_licence(ref["licence"], face["dest"], ref["licence_name"])))

    result = {"zip": "out/%s.zip" % job_id, "written": written, "skipped": skipped,
              "failed_steps": [step.get("id") for step in steps if step.get("state") == "failed"]}

    log = _read_text(os.path.join(job_dir, "log.md"))
    if log and not log.endswith("\n"):
        log += "\n"
    sidecar = "svf-maker-%s/" % job_id
    build = (log + _zip_summary(result) + DUPLICATE_HEADING + "\n\n```\n" + "\n".join(duplicate_rows) + "\n```\n")
    sidecar_entries = [(sidecar + "BUILD.md", build.encode("utf-8")),
                       (sidecar + "FACES.TSV.lines", _lines_bytes(faces_rows)),
                       (sidecar + "LICENCES.tsv.lines", _lines_bytes(licences)),
                       (sidecar + "FAMILIES.tsv.lines", _lines_bytes(families))]

    out_dir = os.path.join(job_dir, "out")
    os.makedirs(out_dir, exist_ok=True)
    final = os.path.join(out_dir, "%s.zip" % job_id)
    tmp = final + ".tmp"
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in list(entries.items()) + sidecar_entries:
                info = zipfile.ZipInfo(name, ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, data)
        os.replace(tmp, final)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return result
