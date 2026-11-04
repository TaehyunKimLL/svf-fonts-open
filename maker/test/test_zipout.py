#!/usr/bin/env python3
"""zipout.py tests: the output zip, the `.lines` files and the build log.

The job dir is built by hand (no worker): four produced faces (two written, two byte-equal to shipped faces), a
`prepare` step that is not a face, two fonts (one `text` licence, one `repo` licence) and an `effective` callable
that returns the explicit values the brief names.

  python3 -m unittest discover -s maker/test -p 'test_*.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import copy
import importlib.util
import json
import tempfile
import unittest
import warnings
import zipfile
from unittest import mock

import fixtures
import naming
import quality
import zipout

# The hand-built job dir and job; `setUp` fills them so every test starts from the same state.
JOB = JD = IDX = FONTS = EFF = REPO = None

SIL = "SIL OPEN FONT LICENSE Version 1.1 - 26 February 2007\n\nPermission is hereby granted, free of charge.\n"

# The two fonts' effective settings; `_eff` overlays one test's per-font changes on a copy.
EFFS = {
    "f01": {"dest": "dos", "licence_name": "OFLNEO.TXT", "note_name": "NEO.TXT",
            "licence": {"kind": "text", "text": SIL}},
    "f02": {"dest": "jamo-extra", "licence_name": "OFLHGKEY.TXT", "note_name": "HGKEY.TXT",
            "licence": {"kind": "repo", "path": "dos/OFL.TXT"}},
}


def _eff(**fonts):
    """`effective` with per-font overrides: `_eff(f01={"dest": "../x"})`."""
    def eff(font_id):
        value = dict(EFFS.get(font_id, {}))
        value.update(fonts.get(font_id) or {})
        return value
    return eff


def _tool(name):
    return os.path.join(REPO_DIR, "tools", name)


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _flip(data):
    return data[:-1] + bytes([data[-1] ^ 0xFF])


def _step(sid, fid, kind, size, bpp, name, argv, output):
    return {"id": sid, "font": fid, "kind": kind, "size": size, "bpp": bpp, "layout": None, "name": name,
            "argv": argv, "output": output, "state": "done", "exit": 0, "seconds": 0.5, "error": None,
            "stderr_tail": "", "facts": None, "quality": None, "identical_to": None, "report": None, "identity": None}


class _ZipBase(unittest.TestCase):
    """Builds the hand-made job dir for every test; the two test classes below share it."""

    def setUp(self):
        global JOB, JD, IDX, FONTS, EFF, REPO
        tmp = tempfile.TemporaryDirectory(prefix="svf-maker-zipout-")
        self.addCleanup(tmp.cleanup)
        JD = tmp.name
        REPO = fixtures.REPO_DIR

        with open(os.path.join(REPO, "svf", "dos", "NEODG16.SVF"), "rb") as f:
            neodg = f.read()
        with open(os.path.join(REPO, "svf", "dos", "NEODG16G.SVF"), "rb") as f:
            hgkey = f.read()

        # work/s01 NEWONE (not identical, new name: written); s02 COPY (identical -> skipped);
        # s03 NEODG16G (identical, jamo-extra); s04 FAKE6J (written, jamo-extra).
        _write(os.path.join(JD, "work", "s01", "NEWONE.SVF"), _flip(neodg))
        _write(os.path.join(JD, "work", "s02", "COPY.SVF"), neodg)
        _write(os.path.join(JD, "work", "s03", "NEODG16G.SVF"), hgkey)
        _write(os.path.join(JD, "work", "s04", "FAKE6J.SVF"), _flip(hgkey))
        _write(os.path.join(JD, "work", "s00", "master.json"), b"{}")

        facts_new = quality.face_facts(_flip(neodg))
        facts_copy = quality.face_facts(neodg)
        facts_hgkey = quality.face_facts(hgkey)
        facts_fake = quality.face_facts(_flip(hgkey))

        steps = [
            _step("s00", "f02", "prepare", None, None, None,
                  [[sys.executable, "-P", _tool("jamovec.py"), "master", "/tmp/x/Composite.ttf",
                    "-o", os.path.join(JD, "work", "s00", "master.json"), "--components"]],
                  "work/s00/master.json"),
            _step("s01", "f01", "precomposed", 16, 1, "NEWONE.SVF",
                  [[sys.executable, "-P", _tool("mkfont.py"), "/tmp/x/Neo.ttf",
                    os.path.join(JD, "work", "s01", "NEWONE.SVF"), "--size", "16", "--bpp", "1",
                    "--unicode", "ascii,ksx1001-hangul"]], "work/s01/NEWONE.SVF"),
            _step("s02", "f01", "precomposed", 16, 1, "COPY.SVF",
                  [[sys.executable, "-P", _tool("mkfont.py"), "/tmp/x/Neo.ttf",
                    os.path.join(JD, "work", "s02", "COPY.SVF"), "--size", "16", "--bpp", "1",
                    "--unicode", "ascii,ksx1001-hangul"]], "work/s02/COPY.SVF"),
            _step("s03", "f02", "jamo", 6, 1, "NEODG16G.SVF",
                  [[sys.executable, "-P", _tool("jamoset.py"), "/tmp/x/HGKEY.FNT", "--layout", "844",
                    "--check", "-o", os.path.join(JD, "work", "s03", "NEODG16G.SVF")]],
                  "work/s03/NEODG16G.SVF"),
            _step("s04", "f02", "jamo", 6, 1, "FAKE6J.SVF",
                  [[sys.executable, "-P", _tool("jamoset.py"), "/tmp/x/HGKEY.FNT", "--layout", "844",
                    "--check", "-o", os.path.join(JD, "work", "s04", "FAKE6J.SVF")]],
                  "work/s04/FAKE6J.SVF"),
        ]
        steps[1]["facts"] = facts_new
        steps[2]["facts"] = facts_copy
        steps[3]["facts"] = facts_hgkey
        steps[4]["facts"] = facts_fake
        steps[4]["quality"] = {"all": 0.9, "ks2350": 0.95, "compared": 2000}

        FONTS = {
            "f01": {"id": "f01", "path": "fonts/Neo.ttf", "label": "TTF", "family": "Neo", "style": "Regular",
                    "version": "1.0", "sizes": [16], "sizes_fixed": False,
                    "coverage": {"ascii": 95, "ks2350": 2350, "all": 11172, "compat": 51},
                    "jamo": "none", "error": None},
            "f02": {"id": "f02", "path": "fonts/HGKEY.FNT", "label": "DOS raw", "family": "HGKEY", "style": "",
                    "version": "1.0", "sizes": [6], "sizes_fixed": True,
                    "coverage": {"ascii": 0, "ks2350": 0, "all": 0, "compat": 0},
                    "jamo": "native (844)", "error": None},
        }
        EFF = lambda font_id: dict(EFFS[font_id])  # noqa: E731 (the brief's callable shape)
        JOB = {"id": "3f9c2b7a1d04", "state": "running", "created": 1760000000.0, "updated": 1760000001.0,
               "error": None, "upload": {"files": 4, "bytes": 1, "refused": []},
               "fonts": [FONTS["f01"], FONTS["f02"]],
               "settings": {"batch": {"dest": "dos", "kinds": ["precomposed", "jamo"], "layout": "844",
                                      "sizes": [16], "bpp": [1, 2], "range": "2350", "preset": "plain",
                                      "options": {"mkfont": {"cell": None, "ascent": None, "mono_hint": False,
                                                             "clip_cell": False, "space_advance": None},
                                                  "jamoset": {"embolden": False, "symbols": False}}},
                            "fonts": {}},
               "steps": steps, "queue_position": None, "result": None}
        IDX = naming.RepoIndex(os.path.join(REPO, "svf"))

        zipout.append_log(JD, zipout.log_header(JOB, "abc"))
        for step in JOB["steps"]:
            zipout.append_log(JD, zipout.log_step(step, "stdout\n", "stderr\n"))


class ZipTest(_ZipBase):
    def test_identity_line_says_how_many_are_unscored(self):
        step = {"kind": "jamo", "id": "s01", "identity": {"available": True, "identity": "warn", "recog_ks": 0.66,
                                                          "unscored": 3724,
                                                          "pieces": {"pass": 330, "warn": 0, "fail": 0, "unscored": 14, "unused": 0}}}
        block = zipout.log_step(dict(step, argv=[], output="x", name="X", exit=0, seconds=0, state="done"), "", "")
        self.assertIn("identity: warn, 344 pieces, 0 warn, 0 fail, 3724 unscored, ks 0.66", block)

    def test_entries_mtime_and_skips(self):
        res = zipout.write_zip(JOB, JD, IDX, FONTS, EFF, REPO)
        z = zipfile.ZipFile(os.path.join(JD, res["zip"]))
        names = z.namelist()
        self.assertIn("svf/dos/NEWONE.SVF", names); self.assertNotIn("svf/dos/COPY.SVF", names)
        self.assertIn("svf/jamo-extra/FAKE6J.SVF", names); self.assertNotIn("svf/jamo-extra/NEODG16G.SVF", names)
        self.assertFalse([n for n in names if n.endswith("master.json")])          # a prepare step is not a face
        self.assertIn("svf/dos/OFLNEO.TXT", names); self.assertIn("svf/dos/NEO.TXT", names)
        self.assertNotIn("svf/jamo-extra/OFLHGKEY.TXT", names)   # byte-equal to dos/OFL.TXT: reused, not written
        self.assertIn("svf/jamo-extra/HGKEY.TXT", names)
        self.assertTrue(all(i.date_time == zipout.ZIP_TIME for i in z.infolist()))
        self.assertEqual(res["skipped"], [{"name": "svf/dos/COPY.SVF", "identical_to": "dos/NEODG16.SVF"}, {"name": "svf/jamo-extra/NEODG16G.SVF", "identical_to": "dos/NEODG16G.SVF"}])
        self.assertEqual(JOB["steps"][2]["identical_to"], "dos/NEODG16.SVF")      # steps: s00 prepare, s01, s02, s03, s04
        side = "svf-maker-%s/" % JOB["id"]
        for n in ("BUILD.md", "FACES.TSV.lines", "LICENCES.tsv.lines", "FAMILIES.tsv.lines"): self.assertIn(side + n, names)
    def test_lines_parse_with_mkindex(self):
        res = zipout.write_zip(JOB, JD, IDX, FONTS, EFF, REPO)
        z = zipfile.ZipFile(os.path.join(JD, res["zip"])); side = "svf-maker-%s/" % JOB["id"]
        with tempfile.TemporaryDirectory() as d:
            lic = os.path.join(d, "L.tsv")
            with open(lic, "wb") as f:
                f.write(z.read(side + "LICENCES.tsv.lines"))
            rows = mkindex.read_licences(lic)
            self.assertEqual([r[0] for r in rows], ["dos/NEWONE.SVF", "dos/NEODG16.SVF", "dos/NEODG16G.SVF", "jamo-extra/FAKE6J.SVF"])
            self.assertEqual(rows[0][1], ["dos/NEO.TXT", "dos/OFLNEO.TXT"])
            self.assertEqual(rows[3][1], ["jamo-extra/HGKEY.TXT", "dos/OFL.TXT"])   # the reused text is named by its existing path
            fam = os.path.join(d, "F.tsv")
            with open(fam, "wb") as f:
                f.write(b"file\tfamily\tstyle\tvariant\n" + z.read(side + "FAMILIES.tsv.lines"))
            self.assertEqual(mkindex.read_families(fam)["svf/dos/NEWONE.SVF"], ("Neo", "Regular", ""))
            faces = os.path.join(d, "FACES.TSV")
            with open(faces, "wb") as f:
                f.write(("\t".join(zipout.FACES_COLUMNS) + "\n").encode() + z.read(side + "FACES.TSV.lines"))
            self.assertEqual(mkindex.read_faces_tsv(faces), {"FAKE6J.SVF": "HGKEY"})
            row = z.read(side + "FACES.TSV.lines").decode().splitlines()[0].split("\t")
            self.assertEqual(len(row), 16); self.assertEqual(row[8:13], ["0.9", "0.95", "", "", "2000"])
    def test_build_log_names_commands_and_identicals(self):
        res = zipout.write_zip(JOB, JD, IDX, FONTS, EFF, REPO)
        z = zipfile.ZipFile(os.path.join(JD, res["zip"])); b = z.read("svf-maker-%s/BUILD.md" % JOB["id"]).decode()
        self.assertIn("mkfont.py", b); self.assertIn("identical to dos/NEODG16.SVF", b)
        block = b.split("## Rows that may duplicate an existing row", 1)[1].split("```")[1].strip().splitlines()
        self.assertEqual(block, ["dos/NEODG16.SVF\tdos/NEO.TXT,dos/OFLNEO.TXT", "dos/NEODG16G.SVF\tjamo-extra/HGKEY.TXT,dos/OFL.TXT"])
    def test_glob_matched_new_face_is_listed_as_duplicate(self):
        job = copy.deepcopy(JOB); job["steps"][1]["name"] = "NEODG16X.SVF"; os.rename(os.path.join(JD, "work/s01/NEWONE.SVF"), os.path.join(JD, "work/s01/NEODG16X.SVF")); job["steps"][1]["output"] = "work/s01/NEODG16X.SVF"
        res = zipout.write_zip(job, JD, IDX, FONTS, EFF, REPO)
        b = zipfile.ZipFile(os.path.join(JD, res["zip"])).read("svf-maker-%s/BUILD.md" % JOB["id"]).decode()
        self.assertIn("dos/NEODG16X.SVF\tdos/NEO.TXT,dos/OFLNEO.TXT", b.split("## Rows that may duplicate an existing row", 1)[1])   # matches the dos/NEODG* glob
        os.rename(os.path.join(JD, "work/s01/NEODG16X.SVF"), os.path.join(JD, "work/s01/NEWONE.SVF"))
    def test_clash_is_refused(self):
        job = copy.deepcopy(JOB); job["steps"][1]["name"] = "NEODG16.SVF"
        with self.assertRaises(zipout.NameClash): zipout.write_zip(job, JD, IDX, FONTS, EFF, REPO)
    def test_log_helpers(self):
        self.assertEqual(zipout.repo_head("/nonexistent"), "unknown")
        self.assertTrue(zipout.log_step(JOB["steps"][1], "out", "err").startswith("## s01 "))
        self.assertIn("plain", zipout.log_header(JOB, "abc"))


def _mkindex():
    """web/mkindex.py by path (it is not on sys.path)."""
    path = os.path.join(REPO_DIR, "web", "mkindex.py")
    spec = importlib.util.spec_from_file_location("mkindex", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mkindex = _mkindex()


class ZipEdgeTest(_ZipBase):
    """Extra cases the brief's six tests do not reach: a note `note_text` refuses and a face no glob matches."""

    def test_a_note_that_note_text_refuses_raises_noterefused(self):
        job = copy.deepcopy(JOB)
        job["steps"][1]["argv"] = [[sys.executable, "-P", _tool("mkfont.py"), "x" * 600]]
        with self.assertRaises(zipout.NoteRefused) as caught:
            zipout.write_zip(job, JD, IDX, FONTS, EFF, REPO)
        self.assertTrue(job["error"].startswith("note for f01:"), job["error"])
        self.assertEqual(str(caught.exception), job["error"])                  # one message, in the exception and the job
        self.assertIsNone(job["steps"][2]["identical_to"])                     # a failed call leaves the steps as they were
        with open(os.path.join(JD, "log.md"), encoding="utf-8") as f:
            self.assertIn(job["error"], f.read())
        self.assertFalse(os.path.exists(os.path.join(JD, "out", "%s.zip" % JOB["id"])))

    def test_a_new_face_that_matches_no_glob_is_not_listed(self):
        job = copy.deepcopy(JOB)
        job["steps"][1]["name"] = "AAA1.SVF"                                  # no glob matches dos/AAA1.SVF
        os.rename(os.path.join(JD, "work/s01/NEWONE.SVF"), os.path.join(JD, "work/s01/AAA1.SVF"))
        job["steps"][1]["output"] = "work/s01/AAA1.SVF"
        res = zipout.write_zip(job, JD, IDX, FONTS, EFF, REPO)
        b = zipfile.ZipFile(os.path.join(JD, res["zip"])).read("svf-maker-%s/BUILD.md" % JOB["id"]).decode()
        block = b.split("## Rows that may duplicate an existing row", 1)[1].split("```")[1].strip().splitlines()
        # the two identical faces remain; the new face's path matches no glob
        self.assertEqual(block, ["dos/NEODG16.SVF\tdos/NEO.TXT,dos/OFLNEO.TXT", "dos/NEODG16G.SVF\tjamo-extra/HGKEY.TXT,dos/OFL.TXT"])


class ZipFixTest(_ZipBase):
    """Fix round 1: every ruling of task-9-fix1.md has a test that asserts its exact behaviour."""

    # ---- Q1: hangul_baseline_row is the 0-based row of the baseline, ascent - 1 --------------------------------

    def test_hangul_baseline_row_is_ascent_minus_one(self):
        step = JOB["steps"][4]                                                # FAKE6J, a jamo face in jamo-extra
        row = zipout.faces_line(step, FONTS["f02"], "OFLHGKEY.TXT").split("\t")
        self.assertEqual(row[14], str(step["facts"]["ascent"] - 1))
        self.assertEqual(row[15], "")                                         # latin_baseline_row stays empty

    def test_faces_line_of_a_jmap_face_writes_dashes(self):
        step = dict(JOB["steps"][4])
        step["facts"] = dict(step["facts"], jset={"sets": None, "classes": None, "pieces": [95, 42, 27], "jmap": True})
        row = zipout.faces_line(step, FONTS["f02"], "OFLHGKEY.TXT").split("\t")
        self.assertEqual(row[5:7], ["-", "-"])

    # ---- J1: one entry per name, equal bytes dropped, other bytes refused --------------------------------------

    def test_two_fonts_that_share_a_licence_name_write_one_entry(self):
        job = copy.deepcopy(JOB)
        fonts = copy.deepcopy(FONTS)
        fonts["f03"] = dict(FONTS["f01"], id="f03", path="fonts/NeoB.ttf", family="NeoB", style="Bold")
        job["fonts"] = [fonts["f01"], fonts["f02"], fonts["f03"]]
        other = _read(os.path.join(JD, "work", "s01", "NEWONE.SVF"))[:-1] + bytes([0x5A])
        _write(os.path.join(JD, "work", "s05", "NEOB16.SVF"), other)
        step = copy.deepcopy(job["steps"][1])
        step.update(id="s05", font="f03", name="NEOB16.SVF", output="work/s05/NEOB16.SVF")
        step["facts"] = quality.face_facts(other)
        job["steps"].append(step)
        eff = _eff(f03={"dest": "dos", "licence_name": "OFLNEO.TXT", "note_name": "NEOB.TXT",
                        "licence": {"kind": "text", "text": SIL}})            # f01 and f03 share OFLNEO.TXT, equal bytes
        with warnings.catch_warnings():
            warnings.simplefilter("error")                                    # a "Duplicate name" warning fails the test
            res = zipout.write_zip(job, JD, IDX, fonts, eff, REPO)
        with zipfile.ZipFile(os.path.join(JD, res["zip"])) as z:
            names = z.namelist()
        self.assertEqual(names.count("svf/dos/OFLNEO.TXT"), 1)
        self.assertIn("svf/dos/NEOB16.SVF", names)

    # ---- J2: hostile dest, face name and text names are refused ------------------------------------------------

    def test_the_reviews_hostile_entry_paths_are_refused(self):
        # probe 4's three entry names: svf/../x/../../../evil.SVF, svf/../x//abs/L.TXT, svf/../x/../../N.TXT
        for label, effs, changes in (
                ("face name", {"f01": {"dest": "../x"}}, {"name": "../../../evil.SVF"}),
                ("licence name", {"f01": {"dest": "../x", "licence_name": "/abs/L.TXT"}}, None),
                ("note name", {"f01": {"dest": "../x", "note_name": "../../N.TXT"}}, None)):
            with self.subTest(label):
                job = copy.deepcopy(JOB)
                if changes:
                    job["steps"][1].update(changes)
                with self.assertRaises(ValueError):
                    zipout.write_zip(job, JD, IDX, FONTS, _eff(**effs), REPO)
                self.assertFalse(os.path.exists(os.path.join(JD, "out", "%s.zip" % JOB["id"])))

    def test_a_hostile_name_with_a_valid_dest_is_refused(self):
        for label, effs, changes in (
                ("face name", {}, {"name": "../../../evil.SVF"}),
                ("licence name", {"f01": {"licence_name": "/abs/L.TXT"}}, None),
                ("note name", {"f01": {"note_name": "../../N.TXT"}}, None),
                ("dest", {"f01": {"dest": "dos/../x"}}, None)):
            with self.subTest(label):
                job = copy.deepcopy(JOB)
                if changes:
                    job["steps"][1].update(changes)
                with self.assertRaises(ValueError):
                    zipout.write_zip(job, JD, IDX, FONTS, _eff(**effs), REPO)

    def test_a_final_entry_path_with_a_dotdot_leading_slash_or_double_slash_is_refused(self):
        for entry in ("svf/../x/evil.SVF", "/abs/evil.SVF", "svf/dos//evil.SVF"):
            with self.subTest(entry):
                with self.assertRaises(ValueError) as caught:
                    zipout._check_entry_path(entry)
                self.assertIn(entry, str(caught.exception))                   # the bad value is named

    # ---- J3: a text that would overwrite a different file is refused -------------------------------------------

    def test_a_text_name_that_exists_with_other_bytes_is_refused(self):
        for label, over in (("licence", {"licence_name": "OFL.TXT"}), ("note", {"note_name": "NEODGM.TXT"})):
            with self.subTest(label):
                job = copy.deepcopy(JOB)
                with self.assertRaises(zipout.NameClash):
                    zipout.write_zip(job, JD, IDX, FONTS, _eff(f01=over), REPO)
                self.assertFalse(os.path.exists(os.path.join(JD, "out", "%s.zip" % JOB["id"])))

    # ---- J4: the FACES licence cell names a file that exists --------------------------------------------------

    def test_faces_licence_cell_names_the_existing_path(self):
        res = zipout.write_zip(JOB, JD, IDX, FONTS, EFF, REPO)
        with zipfile.ZipFile(os.path.join(JD, res["zip"])) as z:
            row = z.read("svf-maker-%s/FACES.TSV.lines" % JOB["id"]).decode().splitlines()[0].split("\t")
        self.assertEqual(row[13], "dos/OFL.TXT")                     # reused from another folder: svf/-relative

    def test_faces_licence_cell_is_a_plain_name_when_written_in_its_own_dest(self):
        res = zipout.write_zip(JOB, JD, IDX, FONTS, _eff(f02={"licence": {"kind": "text", "text": SIL}}), REPO)
        with zipfile.ZipFile(os.path.join(JD, res["zip"])) as z:
            row = z.read("svf-maker-%s/FACES.TSV.lines" % JOB["id"]).decode().splitlines()[0].split("\t")
        self.assertEqual(row[13], "OFLHGKEY.TXT")

    # ---- J5 + J6: the note lists the shipped faces and the done commands only ----------------------------------

    def test_the_note_lists_shipped_faces_and_done_commands_only(self):
        job = copy.deepcopy(JOB)
        job["steps"][1]["argv"] = []                                          # a copy step: the note names the upload's file
        job["steps"][1]["src"] = "/placeholder/SRC.SVF"                       # ...not this placeholder
        failed = copy.deepcopy(job["steps"][1])
        failed.update(id="s09", name="FAILED.SVF", output="work/s09/FAILED.SVF", state="failed",
                      argv=[["/usr/bin/python3", "-P", "/t/mkfont.py", "FAILEDCMD"]])
        job["steps"].append(failed)
        res = zipout.write_zip(job, JD, IDX, FONTS, EFF, REPO)
        with zipfile.ZipFile(os.path.join(JD, res["zip"])) as z:
            note = z.read("svf/dos/NEO.TXT").decode()
        self.assertEqual(note.splitlines()[0], "Neo Regular faces (NEWONE.SVF, NEODG16.SVF)")  # the identical face by the file it equals
        self.assertNotIn("COPY.SVF", note.splitlines()[0])
        self.assertIn("copy upload/fonts/Neo.ttf -> work/s01/NEWONE.SVF", note)
        self.assertNotIn("FAILEDCMD", note)

    # ---- J7: two new faces with equal bytes share one entry ----------------------------------------------------

    def test_two_new_faces_with_equal_bytes_are_written_once(self):
        job = copy.deepcopy(JOB)
        _write(os.path.join(JD, "work", "s05", "NEWTWO.SVF"), _read(os.path.join(JD, "work", "s01", "NEWONE.SVF")))
        step = copy.deepcopy(job["steps"][1])
        step.update(id="s05", name="NEWTWO.SVF", output="work/s05/NEWTWO.SVF")
        job["steps"].append(step)
        res = zipout.write_zip(job, JD, IDX, FONTS, EFF, REPO)
        with zipfile.ZipFile(os.path.join(JD, res["zip"])) as z:
            names = z.namelist()
            rows = z.read("svf-maker-%s/LICENCES.tsv.lines" % JOB["id"]).decode().splitlines()
        self.assertNotIn("svf/dos/NEWTWO.SVF", names)
        self.assertEqual(step["identical_to"], "dos/NEWONE.SVF")
        self.assertIn({"name": "svf/dos/NEWTWO.SVF", "identical_to": "dos/NEWONE.SVF"}, res["skipped"])
        self.assertEqual(rows.count("dos/NEWONE.SVF\tdos/NEO.TXT,dos/OFLNEO.TXT"), 2)

    # ---- J8: an upload licence path is confined to upload/ -----------------------------------------------------

    def test_an_upload_licence_outside_the_upload_dir_is_refused(self):
        with self.assertRaises(ValueError):
            zipout.write_zip(JOB, JD, IDX, FONTS,
                             _eff(f01={"licence": {"kind": "upload", "path": "../../../../../../etc/passwd"}}), REPO)
        self.assertFalse(os.path.exists(os.path.join(JD, "out", "%s.zip" % JOB["id"])))

    def test_an_upload_licence_inside_the_upload_dir_is_used(self):
        _write(os.path.join(JD, "upload", "fonts", "OFL.txt"), b"an upload licence\n")
        res = zipout.write_zip(JOB, JD, IDX, FONTS,
                               _eff(f01={"licence": {"kind": "upload", "path": "fonts/OFL.txt"}}), REPO)
        with zipfile.ZipFile(os.path.join(JD, res["zip"])) as z:
            self.assertEqual(z.read("svf/dos/OFLNEO.TXT"), b"an upload licence\n")

    def test_a_repo_licence_outside_svf_is_refused(self):
        with self.assertRaisesRegex(ValueError, "outside svf/"):
            zipout.write_zip(JOB, JD, IDX, FONTS, _eff(f01={"licence": {"kind": "repo", "path": "/etc/hostname"}}), REPO)
        self.assertFalse(os.path.exists(os.path.join(JD, "out", "%s.zip" % JOB["id"])))

    def test_an_unreadable_licence_is_refused(self):
        with self.assertRaisesRegex(ValueError, "the licence of f01 cannot be read"):
            zipout.write_zip(JOB, JD, IDX, FONTS, _eff(f01={"licence": {"kind": "repo", "path": "dos/NOSUCH.TXT"}}), REPO)

    def test_a_done_step_whose_face_is_missing_is_refused(self):
        os.remove(os.path.join(JD, "work", "s01", "NEWONE.SVF"))
        with self.assertRaisesRegex(ValueError, "is done but its face"):
            zipout.write_zip(JOB, JD, IDX, FONTS, EFF, REPO)
        self.assertFalse(os.path.exists(os.path.join(JD, "out", "%s.zip" % JOB["id"])))

    # ---- J9: every `.lines` file ends with a newline -----------------------------------------------------------

    def test_every_lines_file_ends_with_a_newline(self):
        res = zipout.write_zip(JOB, JD, IDX, FONTS, EFF, REPO)
        with zipfile.ZipFile(os.path.join(JD, res["zip"])) as z:
            for name in ("FACES.TSV.lines", "LICENCES.tsv.lines", "FAMILIES.tsv.lines"):
                self.assertTrue(z.read("svf-maker-%s/%s" % (JOB["id"], name)).endswith(b"\n"), name)

    # ---- J10: web/mkindex.py is loaded from repo_dir -----------------------------------------------------------

    def test_mkindex_is_loaded_from_repo_dir(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "web"))
            with open(os.path.join(d, "web", "mkindex.py"), "w") as f:
                f.write("MARKER = 'from-repo'\ndef read_licences(path):\n    return [['dos/X*']]\n")
            with open(os.path.join(d, "web", "LICENCES.tsv"), "w"):
                pass
            self.assertEqual(zipout._mkindex(d).MARKER, "from-repo")
            self.assertEqual(zipout._existing_globs(d), ["dos/X*"])

    # ---- J11: the zip is written to `<out>.tmp` and replaced into place ----------------------------------------

    def test_a_failed_write_leaves_neither_tmp_nor_zip(self):
        with mock.patch.object(zipfile.ZipFile, "writestr", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                zipout.write_zip(JOB, JD, IDX, FONTS, EFF, REPO)
        self.assertEqual(os.listdir(os.path.join(JD, "out")), [])

    # ---- J12: the log's exact header and fenced identical_to ---------------------------------------------------

    def test_log_header_and_identical_to_cosmetics(self):
        self.assertIn("repo HEAD abc", zipout.log_header(JOB, "abc"))
        step = copy.deepcopy(JOB["steps"][2])
        step["identical_to"] = "dos/NEODG16.SVF"
        self.assertIn("identical_to:\n```json\n\"dos/NEODG16.SVF\"\n```", zipout.log_step(step, "out", "err"))


if __name__ == "__main__":
    unittest.main()
