#!/usr/bin/env python3
"""Recipes (card t_97acecf9, finder design schema v1): the built-in library of known ROM sets, the validator (a recipe is
untrusted input), detection by size then SHA-256 (known / part of a set / similar), the planner's commands, and a local
job that converts a synthetic 86Box Korean VGA ROM pair. No ROM byte is in the repository: the synthetic ROMs are
built from the OFL face svf/dos/NEODG16.SVF at the documented layout, and the real files are read only when
SVF_MAKER_REAL_86BOX names a folder holding them (hashes compared, nothing copied).

  python3 -m unittest discover -s maker/test -p 'test_recipe.py'
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools"), TEST_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import detect
import rawcarve
import recipe
import routes
import settings
import svf2ttf
import toolrun
from localfx import LocalBase, walk_rel

NEODG16 = os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF")
TG = "86box-tgkorvga"
BIOS_OFFSET = 0x4a2d


def synthetic_pair(folder, rom_name="tg_ksc5601.rom", bios_name="tgkorvga.bin"):
    """A 512 KB KS C 5601 ROM (128 x 128 grid, two 8-pixel strips a glyph) and a 32 KB BIOS with an 8x16 English font at
    0x4a2d, both drawn from NEODG16.SVF (OFL). Returns the two paths."""
    face = svf2ttf.load_face(NEODG16)
    rom = bytearray(524288)
    for lead, trail, cp in rawcarve.ks_codes("ks-hangul"):
        if not face.has(cp):
            continue
        rows = svf2ttf._levels(face, cp)
        base = (((lead & 0x7F) << 7) | (trail & 0x7F)) * 32
        for y in range(16):
            left = right = 0
            for x in range(8):
                left |= rows[y][x] << (7 - x)
                right |= rows[y][8 + x] << (7 - x)
            rom[base + y], rom[base + 16 + y] = left, right
    bios = bytearray(32768)
    for cp in range(0x21, 0x7F):
        if not face.has(cp):
            continue
        rows = svf2ttf._levels(face, cp)
        for y in range(16):
            bios[BIOS_OFFSET + cp * 16 + y] = sum(rows[y][x] << (7 - x) for x in range(8))
    os.makedirs(folder, exist_ok=True)
    paths = []
    for name, data in ((rom_name, rom), (bios_name, bios)):
        path = os.path.join(folder, name)
        with open(path, "wb") as f:
            f.write(bytes(data))
        paths.append(path)
    return paths


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def library_for(rom, bios):
    """The built-in TG recipe with the synthetic files' hashes: a library the tests inject."""
    rec = copy.deepcopy(recipe.library()[TG])
    rec["files"][0]["sha256"], rec["files"][1]["sha256"] = sha(rom), sha(bios)
    rec.pop("expect", None)
    return {TG: recipe.validate(rec)}


class LibraryTest(unittest.TestCase):
    def test_builtin_recipes(self):
        lib = recipe.library()
        self.assertEqual(sorted(lib), ["86box-atikorvga", "86box-kasan16", "86box-tgkorvga"])
        for rec in lib.values():
            recipe.check_fit(rec)
            self.assertEqual([(f["size"], f.get("optional", False)) for f in rec["files"]], [(524288, False), (32768, False)])
            self.assertEqual(recipe.host_file(rec), "font")
            self.assertEqual(recipe.item_height(rec), 16)
        self.assertEqual(recipe.sizes(), {524288, 32768})
        self.assertEqual([(i["offset"]) for i in lib[TG]["items"]], [0, 0x4a2d])
        self.assertEqual(lib["86box-kasan16"]["items"][1]["offset"], 0x499a)
        self.assertEqual(lib["86box-atikorvga"]["items"][1]["offset"], 0x4d59)

    def test_planner_gives_the_recipe_commands(self):
        """docs/recipes.md "Korean VGA font ROMs (86Box)", token for token (paths aside)."""
        rec = recipe.library()[TG]
        files = {"font": "/u/tg_ksc5601.rom", "bios": "/u/tgkorvga.bin"}
        paths = {"work": "/w", "out": "/w/TGVGA16.SVF"}
        argvs = recipe.face_commands(rec, "TGVGA16", files, paths, "/w/ks.txt", "/T")
        rest = [toolrun.split_prefix(a)[1] for a in argvs]
        self.assertEqual(rest, [
            ["bdf", "/u/tg_ksc5601.rom", "--glyph", "16x16", "--order", "strips", "--chars", "ks-hangul",
             "--grid", "0x80,0x80,128", "--ascent", "12", "-o", "/w/recipe-hangul.bdf"],
            ["bdf", "/u/tgkorvga.bin", "--offset", "0x4a2d", "--glyph", "8x16", "--chars", "ascii", "--ascent", "12",
             "-o", "/w/recipe-english.bdf"],
            ["--hangul", "/w/recipe-hangul.bdf", "--ascii", "/w/recipe-english.bdf", "--cell", "16x16",
             "--chars-from", "/w/ks.txt", "-o", "/w/TGVGA16.SVF"]])
        jamo = recipe.face_commands(rec, "TGVGA16J", files, dict(paths, out="/w/TGVGA16J.SVF"), "/w/ks.txt", "/T")
        self.assertEqual(jamo[2][-1], "/w/precomposed.svf")
        self.assertEqual(toolrun.split_prefix(jamo[3])[1], ["--layout", "844", "--from-svf", "/w/precomposed.svf",
                                                            "--mask-font", "none", "--check", "-o", "/w/TGVGA16J.SVF"])

    def test_routes_and_names_of_a_known_entry(self):
        font = {"id": "f01", "path": "tg_ksc5601.rom", "source_kind": "recipe", "sizes": [16], "sizes_fixed": True,
                "family": "Trigem Korean VGA font ROM (ET4000)", "recipe": {"id": TG, "files": {}}}
        self.assertEqual([(r.kind, r.label, r.native) for r in routes.routes(font)],
                         [("precomposed", "bdfface", True), ("jamo", "bdfface + from-svf fit", False)])
        eff = {"kinds": ["precomposed", "jamo"], "sizes": [16], "bpp": [1]}
        self.assertEqual(settings.suggested_names(font, eff), {"precomposed/16/1": "TGVGA16.SVF", "jamo/16/1": "TGVGA16J.SVF"})
        self.assertEqual(routes.routes(dict(font, recipe={"id": "no-such"})), [])


class ValidateTest(unittest.TestCase):
    def base(self):
        return copy.deepcopy(recipe.library()[TG])

    def refused(self, rec, text):
        with self.assertRaises(recipe.RecipeError) as cm:
            recipe.validate(rec)
        self.assertIn(text, str(cm.exception))

    def test_refusals(self):
        r = self.base(); r["recipe"] = 2; self.refused(r, "version 2 is not 1")
        r = self.base(); r["recipe"] = True; self.refused(r, "is not 1")
        r = self.base(); r["colour"] = 1; self.refused(r, "unknown key colour")
        r = self.base(); r["regions"] = []; self.refused(r, "not supported yet: regions")
        r = self.base(); r["items"][0]["kind"] = "raw-set"; self.refused(r, "not supported yet: kind raw-set")
        r = self.base(); r["items"][0]["reading"]["gfx"] = "x"; self.refused(r, "not supported yet: gfx")
        r = self.base(); r["items"][0]["reading"]["invert"] = True; self.refused(r, "not supported yet: invert")
        r = self.base(); r["items"][1]["top"] = 2; self.refused(r, "not supported yet: top")
        r = self.base(); r["files"][0]["sha256"] = "AB" * 32; self.refused(r, "64 lower-case hex")
        r = self.base(); r["files"][0]["sha1"] = "0" * 39; self.refused(r, "40 lower-case hex")
        r = self.base(); r["files"][0]["name"] = "a/b.rom"; self.refused(r, "a base name")
        r = self.base(); r["files"][0]["size"] = (1 << 26) + 1; self.refused(r, "1..67108864")
        r = self.base(); r["id"] = "Bad"; self.refused(r, "an id")
        r = self.base(); r["faces"][0]["name"] = "TGVGA16.SVF"; self.refused(r, "[A-Z0-9]{1,8}")
        r = self.base(); r["faces"][1]["from"] = "NOPE"; self.refused(r, "an earlier precomposed face")
        r = self.base(); r["faces"][0]["route"] = "dos raw"; self.refused(r, "not supported yet: route dos raw")
        r = self.base(); r["items"][0]["region"] = "rom"; self.refused(r, "not a file of the recipe")
        r = self.base(); r["items"][0]["grid"] = [128, 128, 0]; self.refused(r, "1..256")
        r = self.base(); r["items"][1]["count"] = 300; self.refused(r, "count")
        r = self.base(); r["expect"]["faces"]["NOPE"] = {}; self.refused(r, "NOPE is not one")
        r = self.base(); r["items"][1]["id"] = "hangul"; self.refused(r, "id hangul twice")
        r = self.base(); r["title"] = {"ko": "x"}; self.refused(r, "missing en")
        self.refused([], "a JSON object")

    def test_loads_limits(self):
        with self.assertRaisesRegex(recipe.RecipeError, "larger than"):
            recipe.loads(b" " * (recipe.MAX_BYTES + 1))
        with self.assertRaisesRegex(recipe.RecipeError, "not JSON"):
            recipe.loads(b'{"recipe": NaN}')
        self.assertEqual(recipe.loads(json.dumps(self.base()).encode())["id"], TG)

    def test_fit_is_checked_when_bound(self):
        r = self.base()
        r["items"][1]["offset"] = 32768 - 100
        recipe.validate(r)                                  # fine at load
        with self.assertRaisesRegex(recipe.RecipeError, "past the end"):
            recipe.check_fit(r)


class MatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="svf-recipe-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.rom, self.bios = synthetic_pair(os.path.join(self.tmp, "set"))
        self.lib = library_for(self.rom, self.bios)

    def files(self, *paths):
        return [((0, os.path.basename(p)), p, os.path.getsize(p)) for p in paths]

    def test_states(self):
        [m] = recipe.match(self.files(self.rom, self.bios), self.lib)
        self.assertEqual((m["state"], m["bound"], m["missing"]),
                         ("known", {"font": (0, "tg_ksc5601.rom"), "bios": (0, "tgkorvga.bin")}, []))
        [m] = recipe.match(self.files(self.rom), self.lib)
        self.assertEqual((m["state"], m["missing"]), ("part", ["tgkorvga.bin"]))
        other = os.path.join(self.tmp, "tg_ksc5601.rom")
        with open(other, "wb") as f:
            f.write(b"\1" * 524288)
        [m] = recipe.match(self.files(other), self.lib)
        self.assertEqual((m["state"], m["similar"]), ("similar", {"font": (0, "tg_ksc5601.rom")}))
        renamed = os.path.join(self.tmp, "x.bin")
        with open(renamed, "wb") as f:
            f.write(b"\1" * 524288)
        self.assertEqual(recipe.match(self.files(renamed), self.lib), [])

    def test_only_a_listed_size_is_hashed(self):
        small = os.path.join(self.tmp, "small.bin")
        with open(small, "wb") as f:
            f.write(b"x" * 100)
        with mock.patch.object(recipe, "file_hashes", wraps=recipe.file_hashes) as spy:
            recipe.match(self.files(small, self.rom), self.lib)
        self.assertEqual([c.args[0] for c in spy.call_args_list], [self.rom])

    def test_scan_labels(self):
        with mock.patch.dict(recipe._LIBRARY, {recipe.builtin_dir(): self.lib}):
            fonts = detect.scan(os.path.dirname(self.rom))           # upload: labelled, no route
            host = next(f for f in fonts if f["path"] == "tg_ksc5601.rom")
            self.assertEqual((host["source_kind"], host["label"]),
                             ("other", "known: Trigem Korean VGA font ROM (ET4000): converted in local mode only"))
            os.remove(self.bios)
            from sources import Sources
            fonts = detect.scan(Sources("local", [os.path.dirname(self.rom)]), local=True)
            self.assertEqual(fonts[0]["label"],
                             "part of Trigem Korean VGA font ROM (ET4000): also needs tgkorvga.bin; pick the folder")
            self.assertEqual(routes.routes(fonts[0]), [])


class RecipeLocalJobTest(LocalBase):
    """A local job over a folder holding a synthetic TG pair: one `known` entry, its BIOS labelled, the precomposed
    face and the 8x4x4 fit written, BUILD.md naming the recipe's commands."""

    def test_synthetic_86box_pair(self):
        folder = os.path.join(self.tmp, "roms")
        rom, bios = synthetic_pair(folder)
        with mock.patch.dict(recipe._LIBRARY, {recipe.builtin_dir(): library_for(rom, bios)}):
            jid = self.local_job(roots=[folder])
            job = self.job(jid)
            host = next(f for f in job["fonts"] if f["path"] == "tg_ksc5601.rom")
            other = next(f for f in job["fonts"] if f["path"] == "tgkorvga.bin")
            self.assertEqual((host["source_kind"], host["label"], host["recipe"]),
                             ("recipe", "known: Trigem Korean VGA font ROM (ET4000)",
                              {"id": TG, "files": {"font": [0, "tg_ksc5601.rom"], "bios": [0, "tgkorvga.bin"]}}))
            self.assertEqual(other["label"], "known: Trigem Korean VGA font ROM (ET4000): tgkorvga.bin, read with tg_ksc5601.rom")
            self.assertNotIn(other["id"], job["settings"]["fonts"])
            st = job["settings"]
            st["fonts"][host["id"]].update(selected=True, kinds=["precomposed", "jamo"], experimental=True,
                                           options={"export": {"ttf": True}})
            status, body = self.api("PUT", "/api/jobs/%s/settings" % jid, st)
            self.assertEqual(status, 200, body)
            job = self.run_to_done(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        files = sorted(job["result"]["files"])
        svf = [f for f in files if f.startswith("svf/")]
        self.assertIn("svf/dos/TGVGA16.SVF", svf)
        self.assertIn("svf/dos/TGVGA16J.SVF", svf)
        self.assertIn("svf/dos/TGVGA16.ttf", svf)
        steps = {s["name"]: s for s in job["steps"]}
        self.assertEqual(steps["TGVGA16.SVF"]["facts"]["glyphs"], 2447)    # as the real ROMs (docs/recipes.md)
        self.assertIsNotNone(steps["TGVGA16J.SVF"]["quality"])                   # scored against the precomposed face
        build = open(os.path.join(self.out, "build-%s" % jid, "BUILD.md"), encoding="utf-8").read()
        self.assertIn("tools/rawcarve.py bdf", build)
        self.assertIn("--grid 0x80,0x80,128", build)
        self.assertIn("--offset 0x4a2d --glyph 8x16 --chars ascii --ascent 12", build)
        self.assertIn("--mask-font none --check", build)
        self.assertEqual(sorted(walk_rel(self.out, skip_prefix=".svf-maker-")), files)


@unittest.skipUnless(os.environ.get("SVF_MAKER_REAL_86BOX"), "SVF_MAKER_REAL_86BOX names a folder with the 86Box ROMs")
class RealRomTest(unittest.TestCase):
    """The real 86Box files (your own copy; nothing is copied or kept): every pair is `known`, and each recipe's
    precomposed and jamo faces have the sizes `expect` records (docs/recipes.md's table)."""

    def test_real_pairs(self):
        root = os.environ["SVF_MAKER_REAL_86BOX"]
        paths = []
        for folder, _dirs, names in os.walk(root):
            paths += [os.path.join(folder, n) for n in names]
        found = recipe.match([((0, p), p, os.path.getsize(p)) for p in paths])
        self.assertEqual(sorted((m["recipe"]["id"], m["state"]) for m in found),
                         [("86box-atikorvga", "known"), ("86box-kasan16", "known"), ("86box-tgkorvga", "known")])
        tmp = tempfile.mkdtemp(prefix="svf-real-86box-", dir=os.environ.get("TMPDIR"))
        self.addCleanup(shutil.rmtree, tmp, True)
        settings.write_range_files(tmp)
        for m in found:
            rec = m["recipe"]
            files = {fid: key[1] for fid, key in m["bound"].items()}
            for face in rec["faces"]:
                out = os.path.join(tmp, face["name"] + ".SVF")
                for argv in recipe.face_commands(rec, face["name"], files, {"work": tmp, "out": out},
                                                 os.path.join(tmp, "range-2350.txt"), os.path.join(REPO_DIR, "tools")):
                    subprocess.run(argv, check=True, capture_output=True, timeout=600)
                want = rec["expect"]["faces"][face["name"]]
                self.assertEqual(os.path.getsize(out), want["bytes"], face["name"])


if __name__ == "__main__":
    unittest.main()
