#!/usr/bin/env python3
"""The WASM font picker (web/): the face index, the module and the page.

  python3 -m unittest tools.test_web_picker        (or: python3 tools/test_web_picker.py)

TestIndex runs web/mkindex.py over svf/ into a temp dir and checks faces.json against jamoset.parse_svfn, svfline.Face
(the jamo flag) and web/LICENCES.tsv (every face has a licence row, every licence file exists); fixture trees check that
a face with a missing piece is plain and that bad licence rows, missing licence files and a malformed FACES.TSV exit 2.

TestPage (web/test/check.mjs under node with playwright-core, a Chrome and the built dist; skips with a message
when any is missing) renders every face on the page and screenshots it into web/test/out/.

TestModule builds the WASM module with web/build.sh into a temp dir (once per run) and draws with web/test/render.mjs
under node: every buffer must equal tools/svfline.py byte for byte. It skips with a message when emcc
($EMSDK/upstream/emscripten/emcc, EMSDK default ~/opt/emsdk) or node ($NODE, ~/opt/node-v24.13.0-linux-x64/bin/node,
then node on PATH) is missing.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import struct
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import jamoset  # noqa: E402
import svfdy  # noqa: E402
import svfline  # noqa: E402

SVF_DIR = os.path.join(ROOT, "svf")
WEB_DIR = os.path.join(ROOT, "web")
MKINDEX = os.path.join(WEB_DIR, "mkindex.py")


def run_mkindex(svf_dir, out_json, *extra):
    args = [sys.executable, "-B", MKINDEX, svf_dir] + ([out_json] if out_json else []) + list(extra)
    return subprocess.run(args, capture_output=True, text=True)


def svf_faces(svf_dir):
    """Every svf/**/*.SVF|svf, as paths relative to svf_dir."""
    out = []
    for p in glob.glob(os.path.join(svf_dir, "**", "*"), recursive=True):
        if os.path.isfile(p) and p.lower().endswith(".svf"):
            out.append(os.path.relpath(p, svf_dir).replace(os.sep, "/"))
    return sorted(out)


# The faces in the tree today (116 in this repository); derived, so adding a face only needs its LICENCES.tsv row.
EXPECTED_FACES = len(svf_faces(SVF_DIR))


MINI = ("NEO16BX2.SVF", "NEODG16A.SVF", "NEODG16B.SVF", "NEODG16D.SVF", "NEODG16G.SVF", "NEODGM.TXT", "OFL.TXT")


def mini_tree(tmp):
    """A fixture svf dir under tmp holding svf/dos/ with a few Neo Dunggeunmo faces and their licence files (MINI);
    web/LICENCES.tsv covers them. Returns its path."""
    svf = os.path.join(tmp, "svf")
    os.makedirs(os.path.join(svf, "dos"))
    for name in MINI:
        shutil.copyfile(os.path.join(SVF_DIR, "dos", name), os.path.join(svf, "dos", name))
    return svf


FAMILIES_TSV = os.path.join(WEB_DIR, "FAMILIES.tsv")
KS = {0xAC00 + n for n in jamoset.ks_x_1001_syllables()}  # computed once


def mini_families(tmp, drop=(), extra=""):
    """tmp/FAMILIES.tsv: the header and the rows of web/FAMILIES.tsv for the faces of mini_tree (minus the faces in drop, plus the text
    extra); returns its path."""
    with open(FAMILIES_TSV, encoding="utf-8") as f:
        lines = f.read().splitlines()
    keep = [ln for i, ln in enumerate(lines) if i == 0 or (ln.split("\t")[0].split("/")[-1] in MINI and ln.split("\t")[0].split("/")[-1] not in drop)]
    path = os.path.join(tmp, "FAMILIES.tsv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(keep) + "\n" + extra)
    return path


def drop_piece(path):
    """Remove from the cmap of the face at path one piece glyph its JSET names (moved to an unused code point at the
    end, so the file keeps its layout); returns the removed code point."""
    with open(path, "rb") as f:
        data = bytearray(f.read())
    svf = jamoset.parse_svfn(bytes(data))
    t = jamoset.unpack(svf.jset)
    cp = next(jamoset.PIECE_BASE + n for n in t.init_piece if n != jamoset.BLANK)
    cmap_off = struct.unpack_from(jamoset.HEADER3, data)[17]    # the v3 header's code point table offset, byte 32
    entries = [struct.unpack_from("<II", data, cmap_off + 8 * k) for k in range(svf.count)]
    k = next(i for i, (c, _) in enumerate(entries) if c == cp)
    entries.append((0x10FFFD, entries.pop(k)[1]))
    for i, (c, idx) in enumerate(entries):
        struct.pack_into("<II", data, cmap_off + 8 * i, c, idx)
    with open(path, "wb") as f:
        f.write(bytes(data))
    return cp


class TestIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="svf-web-index-")
        out = os.path.join(cls.tmp, "faces.json")
        r = run_mkindex(SVF_DIR, out)
        if r.returncode != 0:
            raise AssertionError(f"mkindex.py exit {r.returncode}: {r.stderr.strip()}")
        cls.stdout = r.stdout
        with open(out, encoding="utf-8") as f:
            cls.index = json.load(f)
        cls.faces = cls.index["faces"]
        cls.by_key = {e["key"]: e for e in cls.faces}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_lists_every_face(self):
        self.assertEqual(self.index["format"], "svf-fonts-web-index/1")
        expected = {"svf/" + rel for rel in svf_faces(SVF_DIR)}
        self.assertGreater(len(expected), 0)
        self.assertEqual({e["key"] for e in self.faces}, expected)
        self.assertEqual(len(self.faces), EXPECTED_FACES)
        self.assertRegex(self.stdout, r"^\d+ faces, \d+ listed \(\d+ latin-only\), \d+ subset, 0 unmapped$")
        for e in self.faces:
            rel = e["key"][len("svf/"):]
            self.assertEqual(e["url"], "faces/" + rel)
            self.assertEqual(e["group"], os.path.dirname(rel))

    def test_header_fields_match_jamoset(self):
        for e in self.faces:
            path = os.path.join(ROOT, e["key"])
            with open(path, "rb") as f:
                data = f.read()
            svf = jamoset.parse_svfn(data)
            jamo = svfline.Face(data).tables is not None
            with self.subTest(face=e["key"]):
                self.assertEqual(e["cell"], [svf.cell_w, svf.cell_h])
                self.assertEqual(e["px"], svf.cell_h)
                self.assertEqual(e["bpp"], svf.bpp)
                self.assertEqual(e["ascent"], svf.ascent)
                self.assertEqual(e["glyphs"], svf.count)
                self.assertEqual(e["flags"], svf.flags)
                self.assertEqual(e["jamo"], jamo)
                self.assertEqual(e["bytes"], len(data))

    def test_every_licence_exists(self):
        family = {}
        with open(os.path.join(SVF_DIR, "jamo-extra", "FACES.TSV"), encoding="utf-8") as f:
            rows = [ln.rstrip("\n").split("\t") for ln in f if ln.strip() and not ln.startswith("#")]
        head = rows[0]
        for row in rows[1:]:
            family[row[head.index("file")]] = row[head.index("licence")]
        for e in self.faces:
            with self.subTest(face=e["key"]):
                self.assertTrue(e["licences"], "no licence")
                for url in e["licences"]:
                    self.assertTrue(url.startswith("licences/"), url)
                    self.assertTrue(os.path.isfile(os.path.join(SVF_DIR, url[len("licences/"):])), url)
                if e["group"] == "jamo-extra":
                    name = os.path.basename(e["key"])
                    self.assertIn("licences/jamo-extra/" + family[name], e["licences"])

    def test_jmap_face_is_jamo(self):
        tmp = tempfile.mkdtemp(prefix="svf-web-jmap-")
        try:
            svf = mini_tree(tmp)
            face = os.path.join(svf, "dos", "NEODG16G.SVF")
            for variant, jamo in (("sparse3", True), ("hybrid2", True)):
                r = subprocess.run([sys.executable, os.path.join(HERE, "svf_synth.py"), "--jmap-variant", variant, "--from",
                                    os.path.join(SVF_DIR, "dos", "NEODG16G.SVF"), face], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                out = os.path.join(tmp, "faces.json")
                r = run_mkindex(svf, out, "--families", mini_families(tmp))
                self.assertEqual(r.returncode, 0, r.stderr)
                with open(out, encoding="utf-8") as f:
                    e = {x["key"]: x for x in json.load(f)["faces"]}["svf/dos/NEODG16G.SVF"]
                self.assertIs(e["jamo"], jamo, variant)
                self.assertFalse(e["subset"])
            r = subprocess.run([sys.executable, os.path.join(HERE, "svf_synth.py"), "--jmap-bad", "jmap_missing_piece", "--from",
                                os.path.join(SVF_DIR, "dos", "NEODG16G.SVF"), face], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            r = run_mkindex(svf, out, "--families", mini_families(tmp))
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out, encoding="utf-8") as f:
                e = {x["key"]: x for x in json.load(f)["faces"]}["svf/dos/NEODG16G.SVF"]
            self.assertIs(e["jamo"], False)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_list_face_is_jamo(self):
        tmp = tempfile.mkdtemp(prefix="svf-web-list-")
        try:
            svf = mini_tree(tmp)
            face = os.path.join(svf, "dos", "NEODG16G.SVF")
            r = subprocess.run([sys.executable, os.path.join(HERE, "svf_synth.py"), "--jmap-variant", "list1", "--from",
                                os.path.join(SVF_DIR, "dos", "NEODG16G.SVF"), face], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = os.path.join(tmp, "faces.json")
            r = run_mkindex(svf, out, "--families", mini_families(tmp))
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out, encoding="utf-8") as f:
                e = {x["key"]: x for x in json.load(f)["faces"]}["svf/dos/NEODG16G.SVF"]
            self.assertIs(e["jamo"], True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unmapped_face_fails(self):
        tmp = tempfile.mkdtemp(prefix="svf-web-unmapped-")
        try:
            svf = mini_tree(tmp)
            shutil.copyfile(os.path.join(SVF_DIR, "dos", "NEODG16G.SVF"), os.path.join(svf, "ZZZ.SVF"))
            out = os.path.join(tmp, "faces.json")
            r = run_mkindex(svf, out, "--families", mini_families(tmp))
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("ZZZ.SVF", r.stderr)
            self.assertFalse(os.path.exists(out))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_piece_missing_is_plain(self):
        tmp = tempfile.mkdtemp(prefix="svf-web-piece-")
        try:
            svf = mini_tree(tmp)
            face = os.path.join(svf, "dos", "NEODG16G.SVF")
            drop_piece(face)
            with open(face, "rb") as f:
                data = f.read()
            jset_off, jset_size = struct.unpack_from("<II", data, 36)
            self.assertIsNotNone(jamoset.unpack(data[jset_off:jset_off + jset_size]))  # the JSET itself is still valid
            self.assertTrue(jamoset.parse_svfn(data).jset_bad)     # but it names a piece with no glyph: a plain face
            self.assertIsNone(svfline.Face(data).tables)
            out = os.path.join(tmp, "faces.json")
            r = run_mkindex(svf, out, "--families", mini_families(tmp))
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out, encoding="utf-8") as f:
                by_key = {e["key"]: e for e in json.load(f)["faces"]}
            self.assertIs(by_key["svf/dos/NEODG16G.SVF"]["jamo"], False)
            self.assertIs(by_key["svf/dos/NEODG16A.SVF"]["jamo"], True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bad_licence_rows_fail(self):
        cases = {
            "empty": ("dos/*\t , \n", "names no licence"),
            "absolute": ("dos/*\t" + os.path.join(SVF_DIR, "dos", "NEODGM.TXT") + "\n", "is absolute"),
            "escape": ("dos/*\tdos/../../svf/dos/NEODGM.TXT\n", "outside the svf dir"),
            "ambiguous": ("dos/*\tdos/NEODGM.TXT\ndos/NEODG16G*\tdos/NEODGM.TXT\n", "more than one"),
        }
        for name, (rows, message) in cases.items():
            with self.subTest(case=name):
                tmp = tempfile.mkdtemp(prefix="svf-web-rows-")
                try:
                    svf = mini_tree(tmp)
                    tsv = os.path.join(tmp, "LICENCES.tsv")
                    with open(tsv, "w", encoding="utf-8") as f:
                        f.write(rows)
                    out = os.path.join(tmp, "faces.json")
                    r = run_mkindex(svf, out, "--licences", tsv, "--families", mini_families(tmp))
                    self.assertEqual(r.returncode, 2, r.stderr)
                    self.assertIn(message, r.stderr)
                    self.assertIn("LICENCES.tsv:" if name != "ambiguous" else "NEODG16G.SVF", r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                    self.assertFalse(os.path.exists(out))
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)

    def test_licence_urls_normalised(self):
        tmp = tempfile.mkdtemp(prefix="svf-web-norm-")
        try:
            svf = mini_tree(tmp)
            tsv = os.path.join(tmp, "LICENCES.tsv")
            with open(tsv, "w", encoding="utf-8") as f:
                f.write("dos/*\t./dos//x/../NEODGM.TXT\n")
            os.mkdir(os.path.join(svf, "dos", "x"))
            out = os.path.join(tmp, "faces.json")
            r = run_mkindex(svf, out, "--licences", tsv, "--families", mini_families(tmp))
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out, encoding="utf-8") as f:
                faces = json.load(f)["faces"]
            self.assertEqual({tuple(e["licences"]) for e in faces}, {("licences/dos/NEODGM.TXT",)})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_licence_file_fails(self):
        tmp = tempfile.mkdtemp(prefix="svf-web-nofile-")
        try:
            svf = mini_tree(tmp)
            os.remove(os.path.join(svf, "dos", "OFL.TXT"))
            out = os.path.join(tmp, "faces.json")
            r = run_mkindex(svf, out, "--families", mini_families(tmp))
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("dos/NEO16BX2.SVF", r.stderr)  # the first face in sorted order
            self.assertIn("dos/OFL.TXT", r.stderr)
            self.assertFalse(os.path.exists(out))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_check_writes_nothing(self):
        tmp = tempfile.mkdtemp(prefix="svf-web-check-")
        try:
            r = run_mkindex(SVF_DIR, None, "--check")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(f"{EXPECTED_FACES} faces, ", r.stdout)
            self.assertIn(", 0 unmapped", r.stdout)
            out = os.path.join(tmp, "faces.json")
            r = run_mkindex(SVF_DIR, out, "--check")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(os.listdir(tmp), [])
            r = run_mkindex(SVF_DIR, None)
            self.assertEqual(r.returncode, 2)
            self.assertIn("OUT_JSON is required", r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_malformed_faces_tsv_fails(self):
        cases = {"header": ("file\tpx\nA.SVF\t16\n", "FACES.TSV:1"),
                 "row": ("# note\nfile\tfamily\tpx\nA.SVF\n", "FACES.TSV:3")}
        for name, (text, where) in cases.items():
            with self.subTest(case=name):
                tmp = tempfile.mkdtemp(prefix="svf-web-tsv-")
                try:
                    svf = mini_tree(tmp)
                    os.mkdir(os.path.join(svf, "jamo-extra"))
                    with open(os.path.join(svf, "jamo-extra", "FACES.TSV"), "w", encoding="utf-8") as f:
                        f.write(text)
                    r = run_mkindex(svf, None, "--check", "--families", mini_families(tmp))
                    self.assertEqual(r.returncode, 2, r.stderr)
                    self.assertIn(where, r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)

    def test_hangul_coverage_matches_cmap(self):
        ks = KS
        for e in self.faces:
            with open(os.path.join(ROOT, e["key"]), "rb") as f:
                data = f.read()
            cmap = set(jamoset.parse_svfn(data).glyphs)
            if e["jamo"]:
                face = svfline.Face(data)
                want = sum(face.has(cp) for cp in ks)
            else:
                want = len(ks & cmap)
            with self.subTest(face=e["key"]):
                self.assertEqual(e["hangul"], want)
                latin = not e["jamo"] and want == 0 and all(c in cmap for c in range(0x21, 0x7F))
                self.assertIs(e["latin_only"], latin)
                self.assertIs(e["subset"], not e["jamo"] and not latin and want < 2350)

    def test_subset_examples(self):
        b = self.by_key
        self.assertIs(b["svf/dos/NGOTB14.SVF"]["subset"], True)
        self.assertEqual(b["svf/dos/NGOTB14.SVF"]["hangul"], 1120)
        self.assertIs(b["svf/dos/NGOTB16.SVF"]["subset"], False)
        self.assertEqual(b["svf/dos/NGOTB16.SVF"]["hangul"], 2350)
        self.assertIs(b["svf/dos/NEODG16G.SVF"]["subset"], False)
        self.assertIs(b["svf/dos/NEODG16G.SVF"]["jamo"], True)
        self.assertEqual(b["svf/dos/NEODG16G.SVF"]["hangul"], 2350)
        for k in ("svf/dos/COUSB24.SVF", "svf/dos/PAPLG16.SVF"):
            self.assertIs(b[k]["latin_only"], True, k)
            self.assertIs(b[k]["subset"], False, k)
            self.assertEqual(b[k]["hangul"], 0, k)
        self.assertIs(b["svf/dos/GBA14X2.SVF"]["subset"], True)
        self.assertIs(b["svf/dos/GBA14X2.SVF"]["latin_only"], False)
        n = len(self.faces)
        sub = sum(e["subset"] for e in self.faces)
        lo = sum(e["latin_only"] for e in self.faces)
        self.assertEqual((n, n - sub, lo, sub), (116, 85, 2, 31))
        self.assertEqual(self.stdout.strip(), "116 faces, 85 listed (2 latin-only), 31 subset, 0 unmapped")

    def test_every_listed_face_has_a_family(self):
        for e in self.faces:
            if not e["subset"]:
                self.assertNotEqual(e["family"], "", e["key"])
        with open(FAMILIES_TSV, encoding="utf-8") as f:
            files = [ln.split("\t")[0] for ln in f.read().splitlines()[1:] if ln.strip() and not ln.startswith("#")]
        for e in self.faces:
            if e["key"] not in files:
                self.assertEqual((e["family"], e["style"], e["variant"]), ("", "", ""), e["key"])
        for k in files:
            self.assertIn(k, self.by_key)

    def test_family_examples(self):
        b = self.by_key
        fs = lambda k: (b[k]["family"], b[k]["style"])
        self.assertEqual(fs("svf/dos/MARUS24.SVF"), ("MaruBuri", "SemiBold"))
        self.assertEqual(fs("svf/dos/MARUB24A.SVF"), ("MaruBuri", "Bold"))
        self.assertEqual(b["svf/dos/NEODG16G.SVF"]["variant"], "6x2x1 jamo set")
        self.assertEqual(b["svf/dos/NEODG16G.SVF"]["family"], "Neo Dunggeunmo")
        self.assertEqual(fs("svf/jamo-extra/GOTHB16A.SVF"), ("Gothic A1", "Bold"))
        self.assertEqual(fs("svf/dos/COUSB24.SVF"), ("Coustard", "Bold"))
        self.assertEqual(b["svf/dos/NGOTB16.SVF"]["variant"], "KS X 1001 symbols")

    def _families_case(self, text=None, drop=(), extra="", tree=None):
        """Runs mkindex over a mini_tree with a fixture family table; returns (result, out path, tmp)."""
        tmp = tempfile.mkdtemp(prefix="svf-web-fam-")
        self.addCleanup(shutil.rmtree, tmp, True)
        svf = mini_tree(tmp)
        if tree:
            tree(svf)
        tsv = mini_families(tmp, drop, extra)
        if text is not None:
            with open(tsv, "wb") as f:
                f.write(text)
        out = os.path.join(tmp, "faces.json")
        return run_mkindex(svf, out, "--families", tsv), out, tmp

    def test_missing_family_row_fails(self):
        r, out, _ = self._families_case(drop=("NEODG16G.SVF",))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("NEODG16G.SVF", r.stderr)
        self.assertFalse(os.path.exists(out))

    def test_stale_family_row_fails(self):
        r, out, tmp = self._families_case(extra="svf/dos/NOPE.SVF\tNope\t\t\n")
        self.assertEqual(r.returncode, 2, r.stderr)
        with open(os.path.join(tmp, "FAMILIES.tsv"), encoding="utf-8") as f:
            n = next(i for i, ln in enumerate(f, 1) if ln.startswith("svf/dos/NOPE.SVF"))
        self.assertIn(f"FAMILIES.tsv:{n}", r.stderr)
        self.assertFalse(os.path.exists(out))

    def test_duplicate_family_row_fails(self):
        r, out, tmp = self._families_case(extra="svf/dos/NEODG16G.SVF\tAgain\t\t\n")
        self.assertEqual(r.returncode, 2, r.stderr)
        with open(os.path.join(tmp, "FAMILIES.tsv"), encoding="utf-8") as f:
            n = len(f.read().splitlines())
        self.assertIn(f"FAMILIES.tsv:{n}:", r.stderr)
        self.assertIn("NEODG16G.SVF", r.stderr)
        self.assertFalse(os.path.exists(out))

    def test_long_family_fields_fail(self):
        # the page refuses a field over 256 characters (MAX_FIELD): the table must too, or the whole page fails to start
        for col, cells in {"family": ("a" * 257, "", ""), "style": ("X", "a" * 257, ""), "variant": ("X", "", "a" * 257)}.items():
            with self.subTest(column=col):
                r, out, tmp = self._families_case(drop=("NEODG16G.SVF",), extra="svf/dos/NEODG16G.SVF\t" + "\t".join(cells) + "\n")
                with open(os.path.join(tmp, "FAMILIES.tsv"), encoding="utf-8") as f:
                    n = len(f.read().splitlines())
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn(f"FAMILIES.tsv:{n}:", r.stderr)
                self.assertIn(col, r.stderr)
                self.assertFalse(os.path.exists(out))
        r, out, _ = self._families_case(drop=("NEODG16G.SVF",), extra="svf/dos/NEODG16G.SVF\t" + "a" * 256 + "\t\t\n")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_face_at_the_root_of_svf_fails(self):
        # a root face has group "" which checkIndex refuses: mkindex must say so instead of building an index the page rejects
        def tree(svf):
            shutil.copy(os.path.join(svf, "dos", "NEODG16G.SVF"), os.path.join(svf, "ROOT.SVF"))
        r, out, _ = self._families_case(tree=tree)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("ROOT.SVF", r.stderr)
        self.assertIn("root", r.stderr)  # the root rule, not the licence error that would come next
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse(os.path.exists(out))

    def test_family_header_fails(self):
        for name, text in {"no family": b"file\tstyle\nsvf/dos/NEODG16G.SVF\tX\n",
                           "dup file": b"file\tfamily\tfile\nsvf/dos/NEODG16G.SVF\tX\tY\n"}.items():
            with self.subTest(case=name):
                r, out, _ = self._families_case(text)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("FAMILIES.tsv:1", r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                self.assertFalse(os.path.exists(out))

    def test_family_key_without_prefix_fails(self):
        r, out, _ = self._families_case(b"file\tfamily\nsvf/dos/NEO16BX2.SVF\tX\ndos/NEODG16G.SVF\tX\n")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("FAMILIES.tsv:3", r.stderr)
        self.assertFalse(os.path.exists(out))

    def test_short_row_is_padded(self):
        with open(FAMILIES_TSV, encoding="utf-8") as f:
            rows = [ln for ln in f.read().splitlines()[1:] if ln.split("\t")[0].split("/")[-1] in MINI and "NEODG16G" not in ln]
        text = ("\ufefffile\tfamily\tstyle\tvariant\r\n" + "\r\n".join(rows) + "\r\nsvf/dos/NEODG16G.SVF\tX\r\n").encode("utf-8")
        r, out, _ = self._families_case(text)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            e = next(e for e in json.load(f)["faces"] if e["key"] == "svf/dos/NEODG16G.SVF")
        self.assertEqual((e["family"], e["style"], e["variant"]), ("X", "", ""))

    def test_extra_column_ignored(self):
        with open(FAMILIES_TSV, encoding="utf-8") as f:
            rows = [ln for ln in f.read().splitlines()[1:] if ln.split("\t")[0].split("/")[-1] in MINI]
        text = ("file\tfamily\tstyle\tvariant\tnote\n" + "".join(ln + "\tn\n" for ln in rows)).encode("utf-8")
        r, out, _ = self._families_case(text)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out, encoding="utf-8") as f:
            faces = json.load(f)["faces"]
        self.assertNotIn("note", faces[0])
        e = next(e for e in faces if e["key"] == "svf/dos/NEODG16G.SVF")
        self.assertEqual((e["family"], e["style"], e["variant"]),
                         ("Neo Dunggeunmo", "", "6x2x1 jamo set"))

    def test_long_row_and_empty_file_fail(self):
        for name, text, line in (("long", b"file\tfamily\nsvf/dos/NEO16BX2.SVF\tX\tY\n", 2),
                                 ("empty file", b"file\tfamily\n\tX\n", 2)):
            with self.subTest(case=name):
                r, out, _ = self._families_case(text)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn(f"FAMILIES.tsv:{line}", r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                self.assertFalse(os.path.exists(out))

    def test_licence_error_comes_first(self):
        def add(svf):
            shutil.copyfile(os.path.join(svf, "dos", "NEODG16G.SVF"), os.path.join(svf, "ZZZ.SVF"))
        r, out, _ = self._families_case(drop=("NEODG16G.SVF",), tree=add)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("ZZZ.SVF", r.stderr)
        self.assertNotIn("NEODG16G", r.stderr)

    def test_variant_collision_fails(self):
        def add(svf):
            shutil.copyfile(os.path.join(svf, "dos", "NEODG16G.SVF"), os.path.join(svf, "dos", "NEODG16Z.SVF"))
        with open(FAMILIES_TSV, encoding="utf-8") as f:
            fam, var = next(ln.split("\t")[1:4:2] for ln in f if ln.startswith("svf/dos/NEODG16G.SVF"))
        r, out, _ = self._families_case(extra=f"svf/dos/NEODG16Z.SVF\t{fam}\t\t{var}\n", tree=add)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("NEODG16G.SVF", r.stderr)
        self.assertIn("NEODG16Z.SVF", r.stderr)
        self.assertFalse(os.path.exists(out))
        r, out, _ = self._families_case(extra=f"svf/dos/NEODG16Z.SVF\t{fam}\t\tcopy\n", tree=add)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_real_table_has_no_collision(self):
        # setUpClass ran mkindex over the real tree and table (exit 0); also assert the rule itself.
        self.assertEqual(self.index["format"], "svf-fonts-web-index/1")
        seen = {}
        for e in self.faces:
            if e["subset"]:
                continue
            t = (e["family"], e["style"], e["px"], e["bpp"], e["jamo"], e["cell"][0], e["cell"][1], e["variant"])
            self.assertNotIn(t, seen, f"{e['key']} collides with {seen.get(t)}")
            seen[t] = e["key"]

    def test_label_examples(self):
        self.assertEqual(self.by_key["svf/dos/PAPLG18.SVF"]["label"], "Paperlogy faces 18 px")
        self.assertEqual(self.by_key["svf/jamo-extra/GOTHA16A.SVF"]["label"],
                         "Gothic A1 Regular 2.50 (HanYang I&C) 16 px AA")


# ---- the module (web/build.sh, web/test/render.mjs) ----------------------------------------------------------------

EMSDK = os.environ.get("EMSDK") or os.path.expanduser("~/opt/emsdk")
EMCC = os.path.join(EMSDK, "upstream", "emscripten", "emcc")
BUILD_SH = os.path.join(WEB_DIR, "build.sh")
RENDER_MJS = os.path.join(WEB_DIR, "test", "render.mjs")
SVFVIEW_JS = os.path.join(ROOT, "maker", "static", "svfview.js")
SVF_ERR = ["SVF_OK", "SVF_E_MAGIC", "SVF_E_VERSION", "SVF_E_BPP", "SVF_E_RANGE", "SVF_E_NOMEM", "SVF_E_IO", "SVF_E_ARG", "SVF_E_LAYOUT"]


def find_node():
    for cand in (os.environ.get("NODE"), os.path.expanduser("~/opt/node-v24.13.0-linux-x64/bin/node")):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return shutil.which("node")


_built = {}


def built_dist():
    """The OUT directory of one web/build.sh run (built once per test run, removed at exit); SkipTest without emcc or
    node."""
    if "skip" in _built:
        raise unittest.SkipTest(_built["skip"])
    if "dir" in _built:
        return _built["dir"]
    node = find_node()
    if not os.path.isfile(EMCC) or not node:
        missing = [m for m, ok in (("emcc at " + EMCC, os.path.isfile(EMCC)), ("node", node)) if not ok]
        _built["skip"] = "no %s on this host: the WASM module tests are skipped" % " and no ".join(missing)
        raise unittest.SkipTest(_built["skip"])
    out = tempfile.mkdtemp(prefix="svf-web-dist-")
    import atexit
    atexit.register(shutil.rmtree, out, True)
    r = subprocess.run(["bash", BUILD_SH, out], capture_output=True, text=True, env=dict(os.environ, EMSDK=EMSDK))
    if r.returncode != 0:
        raise AssertionError("build.sh exit %d: %s%s" % (r.returncode, r.stdout, r.stderr))
    _built["dir"], _built["stdout"], _built["node"] = out, r.stdout, node
    return out


def face_path(name):
    hits = glob.glob(os.path.join(SVF_DIR, "**", name + ".SVF"), recursive=True)
    assert len(hits) == 1, (name, hits)
    return hits[0]


class TestModule(unittest.TestCase):
    PAPLG = ["PAPLG16", "PAPLG18"]
    PANGRAM = "Web: 다람쥐 헌 쳇바퀴에 타고파!"

    @classmethod
    def setUpClass(cls):
        cls.dist = built_dist()
        cls.node = _built["node"]

    def run_render(self, spec, expect_ok=True):
        r = subprocess.run([self.node, RENDER_MJS, self.dist, json.dumps(spec)], capture_output=True)
        if expect_ok:
            self.assertEqual(r.returncode, 0, r.stderr.decode(errors="replace"))
        return r

    PRELUDE = r"""
import { pathToFileURL } from 'node:url';
import { readFileSync } from 'node:fs';
const [dist, ...args] = process.argv.slice(1);
const M = await (await import(pathToFileURL(dist + '/svf.js').href)).default();
const put = b => { const p = M._malloc(Math.max(b.length, 1)); M.HEAPU8.set(b, p); return p; };
const out = {};
"""

    def run_script(self, body, *args):
        """Runs PRELUDE + @p body under node with the module dir and @p args; returns the JSON it prints (out)."""
        script = self.PRELUDE + body + "\nconsole.log(JSON.stringify(out));\n"
        r = subprocess.run([self.node, "--input-type=module", "-e", script, self.dist, *args], capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def geometry(self, paths, text, scale):
        width, ascent, descent = svfline.measure(paths, text, scale=scale)
        return width + 4, ascent + descent + 2, 2, ascent + 1

    def spec(self, paths, text, scale, kind, **extra):
        w, h, x, baseline = self.geometry(paths, text, scale)
        d = {"faces": paths, "text": text, "scale": list(scale), "kind": kind, "w": w, "h": h, "x": x,
             "baseline": baseline, "fg565": 0xFFFF, "bg565": 0, "threshold": 128}
        d.update(extra)
        return d

    def expect_gray8(self, paths, text, scale):
        w, h, x, baseline = self.geometry(paths, text, scale)
        return bytes(svfline.layout(paths, text, x, baseline, w, h, scale=scale))

    CASES = [
        (PAPLG, PANGRAM, (1, 1)), (PAPLG, PANGRAM, (2, 1)), (PAPLG, PANGRAM, (3, 2)),
        (["NEODG16G"], "삶닭값읊핥", (1, 1)), (["NEODG16G"], "삶닭값읊핥", (3, 1)),
        (["GOTHA24A"], "국궉귁개객게각", (1, 1)),
        (["GBATB47"], "뛔횰쓿긹", (1, 2)),
    ]

    def test_gray8_matches_svfline(self):
        for names, text, scale in self.CASES:
            paths = [face_path(n) for n in names]
            with self.subTest(faces=names, scale=scale):
                got = self.run_render(self.spec(paths, text, scale, "gray8")).stdout
                want = self.expect_gray8(paths, text, scale)
                self.assertEqual(len(got), len(want))
                self.assertTrue(any(want), "svfline drew nothing")
                self.assertEqual(got, want)

    def test_mono_row_matches_svfline(self):
        paths = [face_path(n) for n in self.PAPLG]
        scale = (2, 1)
        w, h, x, baseline = self.geometry(paths, self.PANGRAM, scale)
        gray = self.expect_gray8(paths, self.PANGRAM, scale)
        for threshold in (128, 1):
            with self.subTest(threshold=threshold):
                got = self.run_render(self.spec(paths, self.PANGRAM, scale, "mono_row", threshold=threshold)).stdout
                want = svfline.to_target(gray, svfline.Target("mono-row", w, h, threshold=threshold)).buf
                self.assertEqual(got, bytes(want))

    def test_mono_page_matches_svfline(self):
        paths = [face_path(n) for n in self.PAPLG]
        scale = (2, 1)
        w, h, x, baseline = self.geometry(paths, self.PANGRAM, scale)
        self.assertNotEqual(h % 8, 0, "a height that is not a whole page checks the last, partial page")
        gray = self.expect_gray8(paths, self.PANGRAM, scale)
        for threshold in (128, 1):
            with self.subTest(threshold=threshold):
                got = self.run_render(self.spec(paths, self.PANGRAM, scale, "mono_page", threshold=threshold)).stdout
                want = svfline.to_target(gray, svfline.Target("mono-page", w, h, threshold=threshold)).buf
                self.assertEqual(len(want), (h + 7) // 8 * w)
                self.assertEqual(got, bytes(want))

    def test_rgb565_matches_svfline(self):
        paths = [face_path(n) for n in self.PAPLG]
        scale = (1, 1)
        w, h, x, baseline = self.geometry(paths, self.PANGRAM, scale)
        places = svfline.placements(svfline.load_chain(paths), self.PANGRAM, x, baseline, scale=scale)
        for fg, bg in ((0xFFFF, 0x0000), (0xF800, 0x07E0)):
            for big in (False, True):
                with self.subTest(fg=hex(fg), bg=hex(bg), big_endian=big):
                    got = self.run_render(self.spec(paths, self.PANGRAM, scale, "rgb565", fg565=fg, bg565=bg,
                                                    big_endian=big)).stdout
                    want = svfline.draw_target(places, svfline.Target("rgb565", w, h, fg565=fg, bg565=bg,
                                                                      big_endian=big)).buf
                    self.assertEqual(got, bytes(want))

    def test_scratch_grows_for_gbatb47_16x(self):
        paths = [face_path("GBATB47")]
        big = self.spec(paths, "가", (16, 1), "gray8")
        small = self.spec(paths, "뛔횰쓿긹", (1, 1), "gray8")
        r = self.run_render([big, small])  # one module: the 16/1 draw grows the scratch, the 1/1 draw reuses it
        want_big = self.expect_gray8(paths, "가", (16, 1))
        want_small = self.expect_gray8(paths, "뛔횰쓿긹", (1, 1))
        self.assertGreater(svfline.scaled_dim(46, 16, 1) * svfline.scaled_dim(54, 16, 1), 65536)
        self.assertEqual(r.stdout, want_big + want_small)

    def test_reset_and_info(self):
        path, jamo_path = face_path("PAPLG16"), face_path("NEODG16G")
        with open(path, "rb") as f:
            svf = jamoset.parse_svfn(f.read())
        with open(jamo_path, "rb") as f:
            jsvf = jamoset.parse_svfn(f.read())
        out = self.run_script(r"""
const [face, jamo] = args;
const data = readFileSync(face), jdata = readFileSync(jamo);
const info = M._malloc(32);
const infoOf = slot => { out['info' + slot + '_err'] = M._svfw_info(slot, info);
                         return Array.from(M.HEAP32.subarray(info >> 2, (info >> 2) + 8)); };
out.open = M._svfw_open(0, put(data), data.length);
out.info = infoOf(0);
out.info1_before = M._svfw_info(1, info);
out.has = M._svfw_has(0, 0x41);
out.has1_before = M._svfw_has(1, 0xAC00);
out.open1 = M._svfw_open(1, put(jdata), jdata.length);
out.jinfo = infoOf(1);
out.jhas_ac00 = M._svfw_has(1, 0xAC00);
out.jhas_d7a3 = M._svfw_has(1, 0xD7A3);
out.jhas_unmapped = M._svfw_has(1, 0xE000);
out.has_slot_bad = M._svfw_has(4, 0x41) + M._svfw_has(-1, 0x41);
const buf = M._malloc(64 * 32);
out.target_cb = M._svfw_target2(4, buf, 64 * 32, 64, 32, 64, 0xFFFF, 0, 128, 0);
out.target = M._svfw_target2(0, buf, 64 * 32, 64, 32, 64, 0xFFFF, 0, 128, 0);
const t = put(new TextEncoder().encode('A'));
out.draw = M._svfw_draw(t, 1, 0, 20);
out.reset = M._svfw_reset();
out.draw_after = M._svfw_draw(t, 1, 0, 20);
out.has_after = M._svfw_has(0, 0x41) + M._svfw_has(1, 0xAC00);
out.info_after = M._svfw_info(0, info) === 7 && M._svfw_info(1, info) === 7;
""", path, jamo_path)
        e_arg = SVF_ERR.index("SVF_E_ARG")
        self.assertEqual((out["open"], out["info0_err"]), (0, 0))
        self.assertEqual(out["info"], [2, 18, 18, 14, svf.flags, 0, 149, 0])
        self.assertEqual(out["info"], [svf.bpp, svf.cell_w, svf.cell_h, svf.ascent, svf.flags, 0, svf.count,
                                       int(svfline.Face.load(path).tables is not None)])
        self.assertEqual(out["info1_before"], e_arg)
        self.assertEqual((out["has"], out["has1_before"]), (1, 0))
        self.assertEqual((out["open1"], out["info1_err"]), (0, 0))
        self.assertEqual(out["jinfo"][:4], [jsvf.bpp, jsvf.cell_w, jsvf.cell_h, jsvf.ascent])
        self.assertEqual(out["jinfo"][6], jsvf.count)
        self.assertEqual(out["jinfo"][7], 1, "NEODG16G is a jamo face")
        self.assertIsNotNone(svfline.Face.load(jamo_path).tables)
        self.assertEqual((out["jhas_ac00"], out["jhas_d7a3"], out["jhas_unmapped"]), (1, 1, 0))
        self.assertFalse(svfline.Face.load(jamo_path).has(0xE000))
        self.assertEqual(out["has_slot_bad"], 0)
        self.assertEqual((out["target_cb"], out["target"], out["draw"], out["reset"]), (e_arg, 0, 0, 0))
        self.assertEqual(out["draw_after"], e_arg)
        self.assertEqual(out["has_after"], 0)
        self.assertTrue(out["info_after"])

    def test_hostile_arguments(self):
        """Every glue call refuses bad arguments with SVF_E_ARG (7), the target ones included."""
        out = self.run_script(r"""
const T = (...a) => M._svfw_target2(...a);
const b = M._malloc(256);
// kind, buf, buf_len, w, h, stride, fg565, bg565, threshold, flags
out.null_buf = T(0, 0, 64, 8, 8, 8, 0xFFFF, 0, 128, 0);
out.null_buf_rgb = T(3, 0, 128, 8, 8, 16, 0xFFFF, 0, 128, 0);
out.short_gray = T(0, b, 63, 8, 8, 8, 0xFFFF, 0, 128, 0);
out.short_rgb = T(3, b, 127, 8, 8, 16, 0xFFFF, 0, 128, 0);
out.short_row = T(2, b, 7, 8, 8, 1, 0xFFFF, 0, 128, 0);
out.stride0 = T(0, b, 64, 8, 8, 0, 0xFFFF, 0, 128, 0);
out.stride_small_gray = T(0, b, 64, 8, 8, 7, 0xFFFF, 0, 128, 0);
out.stride_small_rgb = T(3, b, 128, 8, 8, 15, 0xFFFF, 0, 128, 0);
out.stride_small_row = T(2, b, 16, 9, 8, 1, 0xFFFF, 0, 128, 0);
out.stride_neg = T(0, b, 64, 8, 8, -8, 0xFFFF, 0, 128, 0);
out.stride_big = T(0, b, 64, 8, 8, 65536, 0xFFFF, 0, 128, 0);
out.page_short = T(1, b, 7, 8, 8, 8, 0xFFFF, 0, 128, 0);        // one page of 8 bytes needed
out.page_partial_short = T(1, b, 8, 8, 9, 8, 0xFFFF, 0, 128, 0); // 9 rows: two pages, 16 bytes
out.page_stride_small = T(1, b, 64, 8, 8, 7, 0xFFFF, 0, 128, 0);
out.page_ok = T(1, b, 16, 8, 9, 8, 0xFFFF, 0, 128, 0);
out.w0 = T(0, b, 64, 0, 8, 8, 0xFFFF, 0, 128, 0);
out.h0 = T(0, b, 64, 8, 0, 8, 0xFFFF, 0, 128, 0);
out.w_neg = T(0, b, 64, -8, 8, 8, 0xFFFF, 0, 128, 0);
out.w_big = T(0, b, 64, 32768, 1, 32768, 0xFFFF, 0, 128, 0);
out.kind_neg = T(-1, b, 64, 8, 8, 8, 0xFFFF, 0, 128, 0);
out.kind_cb = T(4, b, 64, 8, 8, 8, 0xFFFF, 0, 128, 0);
out.kind_5 = T(5, b, 64, 8, 8, 8, 0xFFFF, 0, 128, 0);
out.fg_big = T(3, b, 128, 8, 8, 16, 0x10000, 0, 128, 0);
out.bg_neg = T(3, b, 128, 8, 8, 16, 0xFFFF, -1, 128, 0);
out.thr_big = T(2, b, 8, 8, 8, 1, 0xFFFF, 0, 256, 0);
out.thr_neg = T(2, b, 8, 8, 8, 1, 0xFFFF, 0, -1, 0);
out.flags_2 = T(3, b, 128, 8, 8, 16, 0xFFFF, 0, 128, 2);
out.target_w0 = M._svfw_target(b, 0, 8);
out.target_null = M._svfw_target(0, 8, 8);
out.open_slot4 = M._svfw_open(4, b, 16);
out.open_slot_neg = M._svfw_open(-1, b, 16);
out.open_null = M._svfw_open(0, 0, 16);
out.info_null = M._svfw_info(0, 0);
out.info_slot4 = M._svfw_info(4, b);
out.scale0 = M._svfw_scale(0, 1);
out.scale17 = M._svfw_scale(1, 17);
out.measure_neg = M._svfw_measure(b, -1, b);
out.measure_null = M._svfw_measure(b, 1, 0);
out.draw_neg = M._svfw_draw(b, -1, 0, 0);
""")
        page_ok = out.pop("page_ok")
        self.assertEqual(page_ok, 0)
        self.assertEqual({k: v for k, v in out.items() if v != SVF_ERR.index("SVF_E_ARG")}, {})

    def test_order_puts_a_slot_first(self):
        """svfw_order(1) on [NGOTB16, PAPLG18] draws as svfline on [PAPLG18, NGOTB16]; svfw_order(0) is slot order again.
        Both faces hold '가', so the order decides which one draws it."""
        ngot, paplg = face_path("NGOTB16"), face_path("PAPLG18")
        w, h = 64, 40
        base = {"faces": [ngot, paplg], "text": "가", "scale": [1, 1], "kind": "gray8", "w": w, "h": h, "x": 2,
                "baseline": 30}
        got1 = self.run_render(dict(base, order=1)).stdout
        got0 = self.run_render(dict(base, order=0)).stdout
        want1 = bytes(svfline.layout([paplg, ngot], "가", 2, 30, w, h))
        want0 = bytes(svfline.layout([ngot, paplg], "가", 2, 30, w, h))
        self.assertNotEqual(want1, want0, "the two faces draw '가' alike: the test would prove nothing")
        self.assertEqual(got1, want1)
        self.assertEqual(got0, want0)
        out = self.run_script(r"""
const files = args.map(p => readFileSync(p));
out.empty = M._svfw_order(0);                 // no slot open
files.forEach((d, slot) => { out['open' + slot] = M._svfw_open(slot, put(d), d.length); });
out.neg = M._svfw_order(-1);
out.past = M._svfw_order(2);                  // two slots open
out.ok1 = M._svfw_order(1);
out.has_slot0 = M._svfw_has(0, 0x41);         // slots, not chain positions: NGOTB16 has 'A', PAPLG18 does not
out.has_slot1 = M._svfw_has(1, 0x41);
out.ok0 = M._svfw_order(0);
""", ngot, paplg)
        E_ARG = SVF_ERR.index("SVF_E_ARG")
        # a chain never holds a gap: slots open in order, and a failed reopen of slot 0 leaves no chain to draw with
        gap = self.run_script(r"""
const files = args.map(p => readFileSync(p));
const p0 = put(files[0]), p1 = put(files[1]), bad = put(new Uint8Array(64));
out.skip = M._svfw_open(1, p1, files[1].length);  // slot 0 not open: slot 1 would be a gap
out.skip3 = (M._svfw_open(0, p0, files[0].length), M._svfw_open(3, p1, files[1].length));
out.order_gap = M._svfw_order(1);                 // only slot 0 is open
out.open1 = M._svfw_open(1, p1, files[1].length);
out.order1 = M._svfw_order(1);
out.reopen_bad = M._svfw_open(0, bad, 64) !== 0;  // slot 0 fails: the chain (the open prefix) is empty now
out.order_after = M._svfw_order(1);
const t = put(new TextEncoder().encode('가')), m = M._malloc(8);
out.measure_after = M._svfw_measure(t, 3, m);
out.draw_after = M._svfw_draw(t, 3, 0, 20);
out.reopen_ok = M._svfw_open(0, p0, files[0].length); // slot 1 was closed by the reopen of slot 0: no stale face
out.order_again = M._svfw_order(1);
out.has1_again = M._svfw_has(1, 0xAC00);
out.open1_again = M._svfw_open(1, p1, files[1].length);
out.order_last = M._svfw_order(1);
""", ngot, paplg)
        self.assertEqual(gap, {"skip": E_ARG, "skip3": E_ARG, "order_gap": E_ARG, "open1": 0, "order1": 0,
                               "reopen_bad": True, "order_after": E_ARG, "measure_after": E_ARG,
                               "draw_after": E_ARG, "reopen_ok": 0, "order_again": E_ARG, "has1_again": 0,
                               "open1_again": 0, "order_last": 0})
        self.assertEqual(out, {"empty": E_ARG, "open0": 0, "open1": 0, "neg": E_ARG, "past": E_ARG, "ok1": 0,
                               "has_slot0": 1, "has_slot1": 0, "ok0": 0})

    def test_failed_call_exits_3(self):
        spec = self.spec([face_path("PAPLG16")], "A", (1, 1), "gray8")
        spec["scale"] = [17, 1]
        r = self.run_render(spec, expect_ok=False)
        self.assertEqual(r.returncode, 3)
        self.assertIn(b"SVF_E_ARG", r.stderr)

    def test_build_prints_sizes(self):
        self.assertRegex(_built["stdout"], r"svf\.wasm \d+ bytes, svf\.js \d+ bytes, %d faces, \d+ MB copied"
                         % EXPECTED_FACES)
        with open(os.path.join(self.dist, "faces.json"), encoding="utf-8") as f:
            index = json.load(f)
        for e in index["faces"]:
            self.assertTrue(os.path.isfile(os.path.join(self.dist, e["url"])), e["url"])
            for url in e["licences"]:
                self.assertTrue(os.path.isfile(os.path.join(self.dist, url)), url)

    def test_build_all_ports_web(self):
        """build-all.sh --port web builds the web port alone (only emcc needed): exit 0, the port-web line and the
        module on disk; the full --ports run lists the same port (that run needs every port toolchain, so its exit
        status is the gate's business, not this test's)."""
        script = os.path.join(ROOT, "c", "cross", "build-all.sh")
        out = tempfile.mkdtemp(prefix="svf-web-ports-")
        try:
            r = subprocess.run(["sh", script, "--port", "web", out], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertRegex(r.stdout, r"^port-web: OK svf\.wasm \d+ bytes\n$")
            for f in ("svf.js", "svf.wasm"):
                self.assertGreater(os.path.getsize(os.path.join(out, "ports", "web", f)), 0)
            self.assertEqual(os.listdir(os.path.join(out, "ports")), ["web"])
            r = subprocess.run(["sh", script, "--port", "nope", out], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2)
            self.assertIn("--port NAME", r.stderr)
            r = subprocess.run(["sh", script, "--ports", out], capture_output=True, text=True)
            self.assertRegex(r.stdout, r"(?m)^port-web: OK svf\.wasm \d+ bytes$", r.stdout + r.stderr)
            # 12 builds: dos, web, arduino and the nine board-profile images (pico-colour, esp32c3-grey, ...); the
            # port-check-* lines of the gate are not builds, nor are the "port-arduino: info" lines (the Mega images)
            self.assertEqual(len(re.findall(r"(?m)^port-(dos|web|arduino|pico-\w+|esp32[cs]3-\w+): OK ", r.stdout)), 12,
                             r.stdout)
        finally:
            shutil.rmtree(out, ignore_errors=True)

    EXPORTS_JS = r"""
const paths = JSON.parse(args[0]), cps = JSON.parse(args[1]);
paths.forEach((p, slot) => { const d = readFileSync(p); out['open' + slot] = M._svfw_open(slot, put(d), d.length); });
const m = M._malloc(16), info = M._malloc(32), p3 = M._malloc(8);
M._svfw_info(0, info);
const count = M.HEAP32[(info >> 2) + 6];
const cellBytes = M._svfw_cell_bytes(0);
out.cell_bytes = cellBytes;
out.cmap = []; for (let i = 0; i < count; i++) out.cmap.push(M._svfw_cmap_cp(0, i));
out.cmap_m1 = M._svfw_cmap_cp(0, -1); out.cmap_count = M._svfw_cmap_cp(0, count); out.cmap_65536 = M._svfw_cmap_cp(0, 65536);
out.metrics = {}; out.glyph = {}; out.pieces = {};
const cell = M._malloc(cellBytes * 2 + 8);
for (const cp of cps) {
  const rc = M._svfw_metrics(0, cp, m);
  out.metrics[cp] = [rc, ...Array.from(M.HEAP32.subarray(m >> 2, (m >> 2) + 4))];
  const e = M._svfw_glyph(0, cp, cell, cellBytes * 2);
  out.glyph[cp] = e === 0 ? Buffer.from(M.HEAPU8.subarray(cell, cell + cellBytes)).toString('hex') : e;
  const n = M._svfw_pieces(0, cp, p3);
  out.pieces[cp] = Array.from(new Uint16Array(M.HEAPU8.buffer.slice(p3, p3 + 6))).slice(0, n);
}
"""

    def face_bytes_2bpp(self, tmp):
        src = os.path.join(ROOT, "ttf", "nanumgothic", "NanumGothic-Regular.ttf")
        out = os.path.join(tmp, "NG16.SVF")
        r = subprocess.run([sys.executable, "-P", os.path.join(HERE, "mkfont.py"), src, out, "--size", "16",
                            "--bpp", "2", "--unicode", "ascii,AC00-AC0F"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return out

    def test_glyph_metrics_pieces_cmap(self):
        with tempfile.TemporaryDirectory() as tmp:
            faces = [face_path("NEODG16"), face_path("NEODG16A"), face_path("MARUS20"), self.face_bytes_2bpp(tmp)]
            for path in faces:
                with self.subTest(face=os.path.basename(path)):
                    with open(path, "rb") as fh:
                        raw = fh.read()
                    f = jamoset.parse_svfn(raw)
                    stored = [cp for cp in f.glyphs if cp < jamoset.PIECE_BASE]
                    sample = stored[:: max(1, len(stored) // 40)] + [0x20, 0x41, 0xAC00, 0xE000, 0x10FFFF]
                    out = self.run_script(self.EXPORTS_JS, json.dumps([path]), json.dumps(sample))
                    self.assertEqual(out["cmap"], list(f.glyphs))
                    self.assertEqual([out["cmap_m1"], out["cmap_count"], out["cmap_65536"]], [-1, -1, -1])
                    face = svfline.Face(raw)
                    self.assertEqual(out["cell_bytes"], face.pitch * face.cell_h)
                    for cp in sample:
                        if cp in f.glyphs and cp < jamoset.PIECE_BASE:
                            self.assertEqual(bytes.fromhex(out["glyph"][str(cp)]), f.glyphs[cp])
                            self.assertEqual(out["metrics"][str(cp)],
                                             [1 if face.has_metrics else 0, *face.metrics(cp)])
                        elif not face.has(cp):
                            self.assertEqual(out["metrics"][str(cp)][0], -1)
                            self.assertEqual(out["glyph"][str(cp)], 4)  # SVF_E_RANGE
            path = face_path("NEODG16A")
            with open(path, "rb") as fh:
                a = jamoset.parse_svfn(fh.read())
            t = jamoset.unpack(a.jset)
            out = self.run_script(self.EXPORTS_JS, json.dumps([path]), json.dumps([0xAC00, 0xD7A3, 0x3131]))
            for cp in (0xAC00, 0xD7A3):
                self.assertEqual(bytes.fromhex(out["glyph"][str(cp)]), jamoset.compose(a, t, cp))
                self.assertEqual(out["pieces"][str(cp)], jamoset.pieces_of(t, cp))
                self.assertEqual(out["metrics"][str(cp)],
                                 [1, svfline.measure([path], chr(cp))[0], 0, a.cell_w, 0])

    def test_unopened_slot_answers(self):
        out = self.run_script(r"""
const d = readFileSync(args[0]);
out.open = M._svfw_open(0, put(d), d.length);
const m = M._malloc(16), cell = M._malloc(512), p3 = M._malloc(8);
M.HEAP32.fill(7777, m >> 2, (m >> 2) + 4);
out.metrics = M._svfw_metrics(1, 0x41, m);
out.untouched = Array.from(M.HEAP32.subarray(m >> 2, (m >> 2) + 4));
out.null_out = M._svfw_metrics(0, 0x41, 0);
out.cell_bytes = M._svfw_cell_bytes(1);
out.glyph = M._svfw_glyph(1, 0x41, cell, 512);
out.glyph_null = M._svfw_glyph(0, 0x41, 0, 512);
out.pieces = M._svfw_pieces(1, 0xAC00, p3);
out.pieces_null = M._svfw_pieces(0, 0xAC00, 0);
out.cmap = M._svfw_cmap_cp(1, 0);
out.has = M._svfw_has(1, 0x41);
out.line_neg = M._svfw_line_box(0, -1, 0, 0, m);
out.line_null = M._svfw_line_box(0, 0, 0, 0, 0);
""", face_path("NEODG16"))
        self.assertEqual(out["open"], 0)
        self.assertEqual((out["metrics"], out["untouched"], out["null_out"]), (-1, [7777] * 4, -1))
        self.assertEqual((out["cell_bytes"], out["glyph"], out["glyph_null"]), (0, 7, 7))
        self.assertEqual((out["pieces"], out["pieces_null"], out["cmap"], out["has"]), (0, 0, -1, 0))
        self.assertEqual((out["line_neg"], out["line_null"]), (7, 7))

    def line_box(self, paths, text, scale, x, baseline):
        out = self.run_script(r"""
const paths = JSON.parse(args[0]), text = new TextEncoder().encode(args[1]);
paths.forEach((p, slot) => { const d = readFileSync(p); M._svfw_open(slot, put(d), d.length); });
M._svfw_scale(Number(args[2]), Number(args[3]));
const o = M._malloc(16);
out.rc = M._svfw_line_box(put(text), text.length, Number(args[4]), Number(args[5]), o);
out.box = Array.from(M.HEAP32.subarray(o >> 2, (o >> 2) + 4));
""", json.dumps(paths), text, str(scale[0]), str(scale[1]), str(x), str(baseline))
        self.assertEqual(out["rc"], 0)
        return out["box"]

    def test_line_box_matches_svfline(self):
        for scale in ((1, 1), (2, 1), (3, 2)):
            paths = [face_path("MARUS20"), face_path("NEODG16")]
            w, asc, desc = svfline.measure(paths, "Ag가 gy", scale=scale)
            self.assertEqual(self.line_box(paths, "Ag가 gy", scale, x=1, baseline=40), [1, 40 - asc, w, 40 + desc])

    def test_maker_build_matches_web_build(self):
        built_dist()
        out = tempfile.mkdtemp(prefix="svf-maker-wasm-")
        try:
            r = subprocess.run(["bash", os.path.join(ROOT, "maker", "build-wasm.sh")], capture_output=True, text=True,
                               env=dict(os.environ, EMSDK=EMSDK, SVF_WASM_OUT=out))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertRegex(r.stdout, r"^svf\.wasm \d+ bytes, svf\.js \d+ bytes\n$")
            self.assertEqual(sorted(os.listdir(out)), ["svf.js", "svf.wasm"])
            for name in ("svf.wasm", "svf.js"):
                with open(os.path.join(out, name), "rb") as a, open(os.path.join(_built["dir"], name), "rb") as b:
                    self.assertEqual(a.read(), b.read(), name)
        finally:
            shutil.rmtree(out, ignore_errors=True)


    # ---- maker/static/svfview.js: the per-glyph compositor ---------------------------------------------------------

    GLYPHS_JS = r"""
const sv = await import(pathToFileURL(args[0]).href);
sv.init(M);
const spec = JSON.parse(args[1]);
sv.openChain(spec.faces.map(p => new Uint8Array(readFileSync(p))));
sv.setScale(spec.scale[0], spec.scale[1]);
const r = spec.mode === 'line' ? sv.drawLineInto(spec.text, spec.opts) : sv.drawGlyphsInto(spec.text, spec.opts);
out.w = r.w; out.h = r.h; out.baseline = r.baseline; out.hex = Buffer.from(r.pixels).toString('hex');
"""

    CHAIN = ["dos/MARUS20.SVF", "dos/NEODG16.SVF"]       # stored dy over a second slot
    TEXT = "Ag가 gy\u00e9"                                # Latin, a syllable, a glyph only slot 1 has
    SCALES = ((1, 1), (2, 1), (3, 2))

    def draw(self, paths, text, scale, mode, opts=None):
        out = self.run_script(self.GLYPHS_JS, SVFVIEW_JS, json.dumps({"faces": paths, "text": text, "scale": list(scale),
                                                                       "mode": mode, "opts": opts or {}}))
        return out

    def glyphs(self, paths, text, scale, opts):
        return {"line": self.draw(paths, text, scale, "line"), "glyphs": self.draw(paths, text, scale, "glyphs", opts)}

    def tmpdir(self):
        d = tempfile.mkdtemp(prefix="svf-compositor-")
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def write_face(self, data, ascent=None):
        """A temp face holding @p data, its header ascent byte (offset 16) replaced by @p ascent when given."""
        data = bytearray(data)
        if ascent is not None:
            data[16] = ascent
            self.assertEqual(jamoset.parse_svfn(bytes(data)).ascent, ascent)
        fd, path = tempfile.mkstemp(suffix=".SVF", dir=self.tmpdir())
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path

    def read_face(self, path):
        with open(path, "rb") as f:
            return f.read()

    def test_compositor_equals_line_without_overrides(self):
        paths = [face_path("MARUS20"), face_path("NEODG16")]
        for scale in self.SCALES:
            with self.subTest(scale=scale):
                out = self.glyphs(paths, self.TEXT, scale, {})
                self.assertTrue(any(c != "0" for c in out["line"]["hex"]), "nothing drawn")
                self.assertEqual(out["glyphs"], out["line"])

    def test_line_equals_svfline(self):
        paths = [face_path("MARUS20"), face_path("NEODG16")]
        for scale in self.SCALES:
            with self.subTest(scale=scale):
                out = self.draw(paths, self.TEXT, scale, "line")
                width, ascent, descent = svfline.measure(paths, self.TEXT, scale=scale)
                w, h, x, baseline = width + 2, ascent + descent + 2, 1, ascent + 1
                self.assertEqual((out["w"], out["h"], out["baseline"]), (w, h, baseline))
                self.assertEqual(bytes.fromhex(out["hex"]), bytes(svfline.layout(paths, self.TEXT, x, baseline, w, h, scale=scale)))

    def test_compositor_ascent_override_equals_the_patched_header(self):
        paths = [face_path("MARUS20"), face_path("NEODG16")]
        a = jamoset.parse_svfn(self.read_face(paths[0])).ascent
        for new in (a + 2, a - 2):
            patched = self.write_face(self.read_face(paths[0]), new)
            for scale in self.SCALES:
                with self.subTest(ascent=new, scale=scale):
                    got = self.draw(paths, self.TEXT, scale, "glyphs", {"ascentOverride": new})
                    self.assertEqual(got, self.draw([patched, paths[1]], self.TEXT, scale, "line"))

    def test_compositor_dy_equals_svfdy(self):
        paths = [face_path("MARUS20"), face_path("NEODG16")]
        raw = self.read_face(paths[0])
        a = jamoset.parse_svfn(raw).ascent
        want = {0x67: 1, 0x41: -1}
        for ascent in (None, a + 2):
            fixed = self.write_face(svfdy.apply(raw, want)[0], ascent)
            for scale in self.SCALES:
                with self.subTest(ascent=ascent, scale=scale):
                    opts = {"dy": {str(cp): v for cp, v in want.items()}}
                    if ascent is not None:
                        opts["ascentOverride"] = ascent
                    self.assertEqual(self.draw(paths, self.TEXT, scale, "glyphs", opts),
                                     self.draw([fixed, paths[1]], self.TEXT, scale, "line"))

    def marks_chain(self):
        d = self.tmpdir()
        out = os.path.join(d, "EBG20.SVF")
        src = os.path.join(ROOT, "ttf", "ebgaramond", "EBGaramond-VF.ttf")
        r = subprocess.run([sys.executable, "-P", os.path.join(ROOT, "tools", "mkfont.py"), src, out, "--size", "20",
                            "--bpp", "1", "--unicode", "0020-007E,00A1,00E9,00F2,0300-0304"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        face = jamoset.parse_svfn(self.read_face(out))
        self.assertTrue(face.flags & (1 << 2), "marks at origin")
        self.assertIn(0x301, face.glyphs)
        return out, face_path("NEODG16")

    def test_compositor_marks(self):
        base, latin = self.marks_chain()
        raw = self.read_face(base)
        text = "A\u00e9\u00f2\u0302 gy \u00a1 e\u0301"
        for want in ({0x65: 1}, {0x301: 1}, {0x65: 1, 0x301: -1}):
            fixed = self.write_face(svfdy.apply(raw, want)[0])
            for scale in self.SCALES:
                with self.subTest(dy=want, scale=scale):
                    got = self.draw([base, latin], text, scale, "glyphs", {"dy": {str(k): v for k, v in want.items()}})
                    ref = self.draw([fixed, latin], text, scale, "line")
                    self.assertTrue(any(c != "0" for c in ref["hex"]))
                    self.assertEqual(got, ref)

    def test_compositor_mark_after_a_missing_code_point(self):
        base, latin = self.marks_chain()
        fixed = self.write_face(svfdy.apply(self.read_face(base), {0x301: 1})[0])
        text = "A\U0001F600\u0301g"
        got = self.draw([base, latin], text, (3, 2), "glyphs", {"dy": {"769": 1}})
        self.assertEqual(got, self.draw([fixed, latin], text, (3, 2), "line"))

    def test_compositor_dos_raw_symbols_under_an_ascent_override(self):
        d = self.tmpdir()
        raw = os.path.join(d, "raw.fnt")
        fill = set(jamoset.slots_of(8, 4, 4, 160, 248))
        data = bytearray(360 * 32)
        for i in range(360):
            if i not in fill:
                data[i * 32] = data[i * 32 + 1] = 0xFF
        with open(raw, "wb") as f:
            f.write(data)
        faces = {}
        for name, extra in (("A", []), ("B", ["--ascent", "16"])):
            faces[name] = os.path.join(d, name + ".svf")
            r = subprocess.run([sys.executable, "-P", os.path.join(ROOT, "tools", "jamoset.py"), raw, "--layout", "844",
                                "--symbols", "--check", "-o", faces[name]] + extra, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(jamoset.parse_svfn(self.read_face(faces["A"])).ascent, 14)
        text = "가\u2026\u25a1A"
        for scale in self.SCALES:
            with self.subTest(scale=scale):
                got = self.draw([faces["A"]], text, scale, "glyphs", {"ascentOverride": 16, "symbolsFixed": True})
                ref = self.draw([faces["B"]], text, scale, "line")
                self.assertTrue(any(c != "0" for c in ref["hex"]))
                self.assertEqual(got, ref)
        # without symbolsFixed the two symbol glyphs move with the header and do not match the rebuild
        self.assertNotEqual(self.draw([faces["A"]], text, (1, 1), "glyphs", {"ascentOverride": 16}),
                            self.draw([faces["B"]], text, (1, 1), "line"))

    def ink(self, out):
        return sum(1 for i in range(0, len(out["hex"]), 2) if out["hex"][i:i + 2] != "00")

    def test_compositor_lowered_ascent_keeps_the_symbols_whole(self):
        """Below the header ascent the two symbol cells would stick out above the canvas: the box grows instead."""
        d = self.tmpdir()
        raw = os.path.join(d, "raw.fnt")
        fill = set(jamoset.slots_of(8, 4, 4, 160, 248))
        data = bytearray(360 * 32)
        for i in range(360):
            if i not in fill:
                data[i * 32] = data[i * 32 + 1] = 0xFF
        with open(raw, "wb") as f:
            f.write(data)
        face = os.path.join(d, "A.svf")
        r = subprocess.run([sys.executable, "-P", os.path.join(ROOT, "tools", "jamoset.py"), raw, "--layout", "844",
                            "--symbols", "--check", "-o", face], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        whole = self.ink(self.draw([face], "\u2026\u25a1", (1, 1), "glyphs", {"symbolsFixed": True}))
        self.assertGreater(whole, 0)
        for new in (12, 10):
            got = self.draw([face], "\u2026\u25a1", (1, 1), "glyphs", {"ascentOverride": new, "symbolsFixed": True})
            self.assertEqual(self.ink(got), whole, new)

    DECODE_JS = r"""
const sv = await import(pathToFileURL(args[0]).href);
sv.init(M);
const spec = JSON.parse(args[1]);
sv.openChain(spec.faces.map(p => new Uint8Array(readFileSync(p))));
sv.setScale(1, 1);
out.on = {};
for (const kind of ['gray8', 'mono', 'mono_page', 'rgb565']) {
  const r = sv.drawLineInto(spec.text, {target: kind});
  const d = sv.decodeRGBA(kind, r, {});
  out.on[kind] = Array.from({length: r.w * r.h}, (_, i) => d.rgba[4 * i] < 255 || d.rgba[4 * i + 1] < 255 ? 1 : 0).join('');
  out.drawn = out.drawn || {}; out.drawn[kind] = d.drawn;
}
const g = sv.drawLineInto(spec.text, {target: 'gray8'});
out.gray = Array.from({length: g.w * g.h}, (_, i) => g.pixels[i] >= 128 ? 1 : 0).join('');
"""

    def test_every_target_decodes_to_the_same_pixels(self):
        out = self.run_script(self.DECODE_JS, SVFVIEW_JS, json.dumps({"faces": [face_path("NEODG16")], "text": "Ag\uac00 y"}))
        self.assertIn("1", out["gray"])
        for kind in ("mono", "mono_page", "gray8"):
            self.assertEqual(out["on"][kind], out["gray"], kind)
        self.assertEqual(len({out["drawn"][k] for k in ("gray8", "mono", "mono_page")}), 1)
        self.assertGreater(out["drawn"]["rgb565"], 0)

    def test_a_pen_past_the_buffer_draws_nothing_out_of_range(self):
        out = self.draw([face_path("NEODG16")], "AAAAAA", (1, 1), "glyphs", {"pitch": 10000})
        self.assertEqual(out["w"], 32767)
        self.assertGreater(self.ink(out), 0)          # the first glyphs still draw


@unittest.skipIf(os.name == "nt", "POSIX only: the bash build scripts (the Windows build takes the WASM module a Linux "
                                  "build made)")
class TestBuildScriptsWithoutEmcc(unittest.TestCase):
    """A missing emcc is refused before any output directory exists, naming the script that was run."""

    def test_no_emcc(self):
        for script, name in ((BUILD_SH, "build.sh"), (os.path.join(ROOT, "maker", "build-wasm.sh"), "build-wasm.sh")):
            with self.subTest(script=name), tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "out")
                env = dict(os.environ, EMSDK=os.path.join(tmp, "no-emsdk"), SVF_WASM_OUT=out)
                r = subprocess.run(["bash", script, out], capture_output=True, text=True, env=env)
                self.assertEqual(r.returncode, 1)
                self.assertTrue(r.stderr.startswith(name + ": no emcc at "), r.stderr)
                self.assertFalse(os.path.exists(out))


COPYFACES = os.path.join(WEB_DIR, "copyfaces.py")


class TestCopyFaces(unittest.TestCase):
    """web/copyfaces.py (build.sh's copy step): every path faces.json names stays under svf/ and OUT."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-web-copy-")
        self.svf = os.path.join(self.tmp, "svf")
        os.makedirs(os.path.join(self.svf, "dos"))
        for name in ("NEODG16G.SVF", "NEODGM.TXT"):
            shutil.copyfile(os.path.join(SVF_DIR, "dos", name), os.path.join(self.svf, "dos", name))
        with open(os.path.join(self.tmp, "secret.txt"), "w") as f:
            f.write("outside svf/\n")
        self.out = os.path.join(self.tmp, "out")
        os.makedirs(self.out)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_copy(self, entry):
        good = {"key": "svf/dos/NEODG16G.SVF", "url": "faces/dos/NEODG16G.SVF", "licences": ["licences/dos/NEODGM.TXT"]}
        good.update(entry)
        index = os.path.join(self.tmp, "faces.json")
        with open(index, "w", encoding="utf-8") as f:
            json.dump({"format": "svf-fonts-web-index/1", "faces": [good]}, f)
        return subprocess.run([sys.executable, "-B", COPYFACES, self.svf, index, self.out], capture_output=True,
                              text=True)

    def copied(self):
        return sorted(os.path.relpath(os.path.join(d, f), self.out).replace(os.sep, "/")
                      for d, _, fs in os.walk(self.out) for f in fs)

    def test_good_index_copies(self):
        r = self.run_copy({})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "1 faces, 0 MB copied\n")
        self.assertEqual(self.copied(), ["faces/dos/NEODG16G.SVF", "licences/dos/NEODGM.TXT"])

    def test_escaping_paths_fail(self):
        os.symlink(os.path.join(self.tmp, "secret.txt"), os.path.join(self.svf, "dos", "LINK.TXT"))
        bad = [
            {"key": "svf/../secret.txt"},
            {"key": "svf//etc/passwd"},
            {"key": "/etc/passwd"},
            {"key": "svf/dos/./NEODG16G.SVF"},
            {"key": "svf/dos\\NEODG16G.SVF"},
            {"url": "faces/../../escape.SVF"},
            {"url": "/tmp/escape.SVF"},
            {"url": "licences/dos/NEODG16G.SVF"},
            {"url": "faces/"},
            {"licences": ["licences/../../secret.txt"]},
            {"licences": ["/etc/passwd"]},
            {"licences": ["faces/dos/NEODGM.TXT"]},
            {"licences": ["licences/dos/LINK.TXT"]},
        ]
        for entry in bad:
            with self.subTest(entry=entry):
                r = self.run_copy(entry)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("copyfaces.py:", r.stderr)
                self.assertEqual(self.copied(), [], "nothing is copied when a path fails")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "escape.SVF")))

    def test_build_sh_uses_it(self):
        with open(BUILD_SH, encoding="utf-8") as f:
            self.assertIn('python3 -B "$HERE/copyfaces.py" "$ROOT/svf" "$OUT/faces.json" "$OUT"', f.read())


# ---- the page (web/index.html, picker.js, web/test/check.mjs) ------------------------------------------------------

CHECK_MJS = os.path.join(WEB_DIR, "test", "check.mjs")
OUT_DIR = os.path.join(WEB_DIR, "test", "out")
PLAYWRIGHT = os.path.join(WEB_DIR, "test", "node_modules", "playwright-core")
_checked = {}


def checked_out():
    """OUT_DIR after one web/test/check.mjs run over the built dist (once per test run). SkipTest with a message when
    node, playwright-core (npm ci in web/test), emcc or a launchable Chrome is missing (check.mjs exits 2 then); an
    AssertionError naming the failing case when check.mjs exits 1."""
    if "skip" in _checked:
        raise unittest.SkipTest(_checked["skip"])
    if "dir" in _checked:
        return _checked["dir"]
    dist = built_dist()  # skips without emcc / node
    node = _built["node"]
    if not os.path.isdir(PLAYWRIGHT):
        _checked["skip"] = "no %s (run npm ci in web/test): the page tests are skipped" % PLAYWRIGHT
        raise unittest.SkipTest(_checked["skip"])
    r = subprocess.run([node, CHECK_MJS, dist, OUT_DIR], capture_output=True, text=True)
    if r.returncode == 2:
        lines = r.stderr.strip().splitlines() or ["no message"]
        _checked["skip"] = "check.mjs cannot run here (%s): the page tests are skipped" % lines[-1]
        raise unittest.SkipTest(_checked["skip"])
    if r.returncode != 0:
        raise AssertionError("check.mjs exit %d: %s%s" % (r.returncode, r.stdout, r.stderr))
    _checked["dir"] = OUT_DIR
    return OUT_DIR

def png_colours(path):
    """(width, height, set of (r, g, b)) of an 8-bit RGB/RGBA PNG, decoded with zlib. Raises ValueError for an unknown
    filter byte, a wrong row length, or a format other than 8-bit RGB/RGBA."""
    import zlib
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("%s: not a PNG" % path)
    width, height = struct.unpack(">II", data[16:24])
    pos, idat, ctype, depth = 8, b"", None, None
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"IHDR":
            depth, ctype = data[pos + 16], data[pos + 17]
        if kind == b"IDAT":
            idat += data[pos + 8:pos + 8 + n]
        pos += 12 + n
    if depth != 8 or ctype not in (2, 6):
        raise ValueError("%s: not 8-bit RGB/RGBA (depth %s, colour type %s)" % (path, depth, ctype))
    bpp = {2: 3, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = width * bpp
    if len(raw) != height * (stride + 1):
        raise ValueError("%s: %d bytes of image data, expected %d" % (path, len(raw), height * (stride + 1)))
    prev, seen = bytearray(stride), set()
    for y in range(height):
        base = y * (stride + 1)
        ft, line = raw[base], bytearray(raw[base + 1:base + 1 + stride])
        if ft > 4:
            raise ValueError("%s: unknown filter byte %d in row %d" % (path, ft, y))
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ft == 1:
                line[i] = (line[i] + a) & 255
            elif ft == 2:
                line[i] = (line[i] + b) & 255
            elif ft == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif ft == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        prev = line
        seen.update(tuple(line[i:i + 3]) for i in range(0, stride, bpp))
    return width, height, seen


class TestPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = checked_out()

    def test_every_face_renders(self):
        with open(os.path.join(self.out, "faces-report.tsv"), encoding="utf-8") as f:
            rows = [line.rstrip("\n").split("\t") for line in f if line.strip()]
        self.assertEqual(len(rows), 116)
        self.assertEqual(len({r[0] for r in rows}), 116, "one row a face")
        for key, err, ink, _ms, _case in rows:
            with self.subTest(face=key):
                self.assertEqual(err, "0")
                self.assertGreater(int(ink), 0)

    def test_page_reports_browser(self):
        with open(os.path.join(self.out, "browser.txt"), encoding="utf-8") as f:
            text = f.read()
        self.assertRegex(text, r"(Chrome|Chromium)/\d+\.\d+")
        self.assertIn("playwright-core 1.62.1", text)

    def test_cases(self):
        """Case A (pangram + ASCII) and the supplement case are counted separately; every other case reports."""
        with open(os.path.join(self.out, "cases.txt"), encoding="utf-8") as f:
            text = f.read()
        m = re.search(r"case A: 116 faces, (\d+) hold .* drew ink\ncase supplement: (\d+) ", text)
        self.assertIsNotNone(m, text)
        self.assertEqual(int(m.group(1)) + int(m.group(2)), 116)
        self.assertGreater(int(m.group(2)), 0)
        for name in ("fetch-once", "C:", "D:", "E:"):
            self.assertIn("case " + name if name[0] != "f" else "case fetch-once", text)
        for name in ("bad face", "transport", "index", "default variant", "sizes", "pick", "hidden in chain", "keyboard", "no stream", "surrogates", "budget", "dom", "runs", "prefetch", "prefetch priority", "prefetch shared", "prefetch carry-overs", "prefetch errors", "prefetch budget", "select during eviction", "scan during select", "server and cancel", "url", "export", "choices"):
            self.assertIn("case %s: " % name, text)
        with open(os.path.join(self.out, "faces-report.tsv"), encoding="utf-8") as f:
            cases = [line.split("\t")[4].strip() for line in f if line.strip()]
        self.assertEqual(cases.count("supplement"), int(m.group(2)))

    HANGUL_RANGES = ((0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xAC00, 0xD7A3), (0xD7B0, 0xD7FF))

    @classmethod
    def class_runs(cls, line):
        """[(is_hangul, text)] of @p line by the spec's rule (a U+0300..036F mark joins the run before it)."""
        # as picker.js: a surrogate pair is one (astral) character, a lone surrogate U+FFFD
        line = line.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")
        runs = []
        for ch in line:
            cp = ord(ch)
            hangul = runs[-1][0] if svfline.is_mark_default(cp) and runs else any(a <= cp <= b for a, b in cls.HANGUL_RANGES)
            if runs and runs[-1][0] == hangul:
                runs[-1][1] += ch
            else:
                runs.append([hangul, ch])
        return [tuple(r) for r in runs]

    def test_run_split_matches_class_rule(self):
        """picker.runs splits the lines check.mjs gave it (runs-split.json: class edges, astral characters next to a lone
        surrogate, marks) as this file's own class rule does."""
        with open(os.path.join(self.out, "runs-split.json"), encoding="utf-8") as f:
            splits = json.load(f)
        self.assertTrue(any(ord(c) > 0xFFFF for s in splits for c in s["line"]), "no astral character in the lines")
        for s in splits:
            with self.subTest(line=s["line"]):
                self.assertEqual([(r["hangul"], r["text"]) for r in s["runs"]], self.class_runs(s["line"]))

    def test_hangul_runs_match_svfline(self):
        """Each specimen check.mjs drew (runs.json: the mixed line "Quest 가나 OK" at 1/1 and 3/2, three lines with an
        empty middle one at 1/1 and 3/2, a Hangul run whose U+3165 the Hangul face lacks, "A\n가" with lines of two
        heights) equals svfline runs put side by side: a Latin run on [Latin, Hangul], a Hangul run on [Hangul, Latin],
        x moving by each run's measured width; each line its own height (max ascent + max descent of its runs + 2, an
        empty line the chain's line) and baseline, the lines stacked; and differs from the one-chain drawing."""
        with open(os.path.join(self.out, "runs.json"), encoding="utf-8") as f:
            specimens = json.load(f)
        names = ["mixed", "mixed32", "multiline", "multiline32", "fallback", "lines"]
        self.assertEqual([s["name"] for s in specimens], names)
        for s in specimens:
            with self.subTest(specimen=s["name"]):
                with open(os.path.join(self.out, "runs-%s.bin" % s["name"]), "rb") as f:
                    got = f.read()
                latin, hangul = face_path(s["latin"]), face_path(s["hangul"])
                scale = tuple(s["scale"])
                lines = [[(text, [hangul, latin] if h else [latin, hangul]) for h, text in self.class_runs(line)]
                         for line in s["text"].split("\n")]
                sizes = [[svfline.measure(chain, text, scale=scale) for text, chain in line] for line in lines]
                # per line: its own ascent and descent (max over its runs), height ascent + descent + 2, baseline
                # 1 + ascent below its top; the lines stack. An empty line gets the chain's line: the max scaled
                # ascent and the max scaled descent (scaled cell height - scaled ascent) over the two faces
                num, den = svfline.scale_ratio(scale)
                faces = svfline.load_chain([latin, hangul])
                chain_asc = max(svfline.scale_len(f.ascent, num, den) for f in faces)
                chain_desc = max(svfline.scaled_dim(f.cell_h, num, den) - svfline.scale_len(f.ascent, num, den)
                                 for f in faces)
                asc = [max(a for _, a, _ in size) if size else chain_asc for size in sizes]
                desc = [max(d for _, _, d in size) if size else chain_desc for size in sizes]
                tops = [sum(a + d + 2 for a, d in zip(asc[:i], desc[:i])) for i in range(len(lines) + 1)]
                w = max(sum(wd for wd, _, _ in size) for size in sizes) + 2
                h = tops[-1]
                self.assertEqual((s["kind"], s["w"], s["h"]), ("gray8", w, h))
                places = []
                for i, (line, size) in enumerate(zip(lines, sizes)):
                    x = 1
                    for (text, chain), (wd, _, _) in zip(line, size):
                        places += svfline.placements(svfline.load_chain(chain), text, x, tops[i] + 1 + asc[i], scale=scale)
                        x += wd
                want = bytes(svfline.draw_gray8(places, w, h))
                self.assertTrue(any(want))
                self.assertEqual(got, want)
                one = bytearray(w * h)
                for i, line in enumerate(s["text"].split("\n")):
                    row = svfline.layout([latin, hangul], line, 1, tops[i] + 1 + asc[i], w, h, scale=scale)
                    one = bytearray(max(a, b) for a, b in zip(one, row))
                if s["name"] != "fallback":  # there NGOTB16 draws U+3165 either way; its point is the fallback itself
                    self.assertNotEqual(got, bytes(one), "the runs draw as the one chain would")

    def test_non_gray8_screenshots(self):
        for name in ("mono.png", "rgb565.png", "page-ui.png"):
            w, h, seen = png_colours(os.path.join(self.out, name))
            self.assertGreater(len(seen), 1, name)

    def test_first_screenshot(self):
        width, height, seen = png_colours(os.path.join(self.out, "paplg18-chain.png"))
        self.assertGreater(width, 200)
        self.assertGreater(height, 8)
        self.assertGreater(len(seen), 1, "the screenshot is not one flat colour")

    def test_controls_report(self):
        """Case B: scale 2/1 doubles the 1/1 advance (ASCII on PAPLG16), MONO ink falls as the threshold rises (GOTHA24A,
        2 bpp), the licence pane for PAPLG18 shows PAPLG.TXT's heading and the OFL text's first line."""
        with open(os.path.join(self.out, "controls.json"), encoding="utf-8") as f:
            c = json.load(f)
        self.assertGreater(c["width1"], 0)
        self.assertEqual(c["width2"], 2 * c["width1"])
        self.assertGreater(c["mono1"], c["mono255"])
        self.assertGreater(c["mono255"], 0)
        self.assertIs(c["licence_ok"], True)

    def test_three_face_screenshots(self):
        shots = {}
        for name in ("paplg18-chain.png", "hgkey6j-mono.png", "gbatb47-rgb565.png"):
            w, h, seen = png_colours(os.path.join(self.out, name))
            shots[name] = seen
            with self.subTest(png=name):
                self.assertGreater(w, 40)
                self.assertGreater(h, 8)
                self.assertGreater(len(seen), 1, "not one flat colour")
        # RGB565 #FFE000 expanded from 5/6/5: r 31 -> 255, g 56 -> 227, b 0
        self.assertIn((255, 227, 0), shots["gbatb47-rgb565.png"])
        self.assertEqual(len(shots["hgkey6j-mono.png"]), 2, "MONO draws two colours")

    def test_export_shape(self):
        """Case export: two choices (PAPLG18 over NGOTB16 at 1/1, GBATB47 alone at 1/2) in one game, in insertion order."""
        with open(os.path.join(self.out, "selection.json"), encoding="utf-8") as f:
            sel = json.load(f)
        self.assertEqual(sel["format"], "scummvm-ko-font-pairing/1")
        self.assertEqual(sel["order"], "per-run")
        self.assertRegex(sel["created"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(sel["source"], "svf-fonts web picker")
        self.assertEqual([g["game"] for g in sel["games"]], ["KQ4"])
        fonts = sel["games"][0]["fonts"]
        self.assertEqual([f["id"] for f in fonts], ["300", "600"])
        self.assertEqual({f["korean"]["key"] for g in sel["games"] for f in g["fonts"] if f.get("korean")},
                         {"svf/dos/PAPLG18.SVF", "svf/dos/GBATB47.SVF"})
        self.assertEqual([f["lineh"] for f in fonts], [12, 24])
        self.assertEqual([f["picked"] for f in fonts], [True, True])
        self.assertEqual([f["korean"]["latin"] for f in fonts], ["svf/dos/NGOTB16.SVF", None])
        self.assertEqual([f["korean"]["scale"] for f in fonts], [[1, 1], [1, 2]])
        k0, k1 = fonts[0]["korean"], fonts[1]["korean"]
        self.assertEqual((k1["w"], k1["h"], k1["ascent"]), (23, 27, 23))  # GBATB47 46 x 54, ascent 45, at 1/2
        self.assertEqual((k0["w"], k0["h"], k0["bpp"]), (18, 18, 2))
        self.assertEqual(k0["file"], k0["key"])
        # label stays the index label; family, style and variant are new strings beside it
        for k in (k0, k1):
            for name in ("label", "family", "style", "variant"):
                self.assertIsInstance(k[name], str, name)
            self.assertTrue(k["label"])
            self.assertTrue(k["family"])

    def test_export_screenshot(self):
        w, h, seen = png_colours(os.path.join(self.out, "export.png"))
        self.assertGreater(w, 300)
        self.assertGreater(h, 100)
        self.assertGreater(len(seen), 1, "not one flat colour")


if __name__ == "__main__":
    unittest.main()
