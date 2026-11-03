#!/usr/bin/env python3
"""tools/macfbit_svf.py on synthetic fixtures only (no Apple data): a type-3 'fbit' and an 'HTBL' 1 built here from a
made-up slot rule, a made-up resource fork with a FOND and an NFNT strike."""
import os
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jamoset as J  # noqa: E402
import macfbit3 as M3  # noqa: E402
import macfbit_svf as M  # noqa: E402

H = 12
VG = lambda V: 0 if V in (0, 1, 2, 3, 4, 5, 6, 7, 20) else (1 if V in (8, 12, 13, 17, 18) else 2)   # vertical/horiz/mixed
LG = lambda L: 0 if L in (0, 15) else 1                                                          # ㄱ ㅋ vs the rest


def _bitmap(rng, x0, x1, y0, y1):
    v = 0
    for _ in range(9):
        x, y = rng.randrange(x0, x1), rng.randrange(y0, y1)
        v |= 1 << (H * H - 1 - (y * H + x))
    return v


def synthetic(seed=1):
    """(fbit bytes, HTBL 1 bytes, slot rule) of a font whose initial glyph is chosen by (initial, vowel group, final
    present), the medial by (vowel, lead group), the final by (tail, vowel group % 2): 210 slots in bank 1."""
    rng = random.Random(seed)
    slots, glyphs = {}, []

    def slot(key, region):
        if key not in slots:
            slots[key] = len(glyphs)
            glyphs.append(_bitmap(rng, *region))
        return slots[key]
    for L in range(19):
        for g in range(3):
            for tp in (0, 1):
                slot(("i", L, g, tp), (0, 6, 0, 7))
    for V in range(21):
        for lg in (0, 1):
            slot(("m", V, lg), (6, 12, 0, 12))
    for T in range(1, 28):
        for g in (0, 1):
            slot(("f", T, g), (0, 8, 8, 12))
    while len(glyphs) < 482:
        glyphs.append(0)
    rule = lambda L, V, T: (slots["i", L, VG(V), int(T > 0)], slots["m", V, LG(L)],
                            slots["f", T, VG(V) % 2] if T else None)
    gb = (H * H + 7) // 8
    head = bytearray(0x54)
    head[0:6] = b"\x80\x00fbit"
    struct.pack_into(">H", head, 0x0c, 3)
    struct.pack_into(">H", head, 0x16, H)
    struct.pack_into(">H", head, 0x48, 3)
    struct.pack_into(">H", head, 0x4c, 1)
    fbit = bytes(head) + b"".join(g.to_bytes(gb, "big") for g in glyphs)

    def entry(gs):
        return bytes([1] + [0 if g is None else g + 0x0f for g in gs] + [0] * (3 - len(gs)))
    t1 = bytearray()
    for k in range(51):
        ch = bytes([0xa4, 0xa1 + k]).decode("euc_kr")
        kind, j = J.COMPAT[ord(ch) - 0x3131]
        g = (slots["i", j, 0, 0] if kind == "i" else slots["m", j, 1] if kind == "v" else slots["f", j, 0])
        t1 += entry([g, None, None])
    t2 = bytearray()
    for i in range(2350):
        n = ord(bytes([0xb0 + i // 94, 0xa1 + i % 94]).decode("euc_kr")) - 0xAC00
        t2 += entry(list(rule(*M.syl(n))))
    htbl = struct.pack(">I", len(t1)) + bytes(t1) + struct.pack(">I", len(t2)) + bytes(t2)
    return fbit, htbl, rule


def synthetic_classes():
    return [LG(L) for L in range(19)], [0] + [1] * 27


class TestInput(unittest.TestCase):
    def test_parse_and_compose(self):
        fbit, htbl, rule = synthetic()
        fb, ht = M.Fbit3(fbit), M.Htbl1(htbl)
        self.assertEqual((fb.h, len(fb.glyphs)), (H, 482))
        self.assertEqual(len(ht.syllables), 2350)
        self.assertEqual(len(ht.compat), 51)
        n = ord("각") - 0xAC00
        self.assertEqual(ht.syllables[n], rule(*M.syl(n)))
        L, V, T = M.syl(n)
        want = fb.glyphs[rule(L, V, T)[0]] | fb.glyphs[rule(L, V, T)[1]] | fb.glyphs[rule(L, V, T)[2]]
        self.assertEqual(M.mac_compose(fb, ht.syllables[n]), want)

    def test_refuses_other_fbit(self):
        fbit, _, _ = synthetic()
        bad = bytearray(fbit)
        struct.pack_into(">H", bad, 0x0c, 1)
        with self.assertRaises(ValueError):
            M.Fbit3(bytes(bad))


class TestModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fbit, htbl, _ = synthetic()
        cls.fb, cls.ht = M.Fbit3(fbit), M.Htbl1(htbl)
        cls.planes = M.mac_planes(cls.fb, cls.ht)

    def test_true_classes_exact_without_residual(self):
        lc, tc = synthetic_classes()
        m = M.Model(self.planes, lc, tc)
        self.assertEqual(m.bad, [])
        self.assertEqual(m.residual(), 0)
        for n in self.planes:
            self.assertEqual(m.compose(n), M.mac_compose(self.fb, self.ht.syllables[n]))

    def test_one_lead_class_moves_medial_variants_into_initials(self):
        m = M.Model(self.planes, [0] * 19, [0] + [1] * 27)
        self.assertEqual(m.bad, [])                # still exact: the lead-group strokes ride on the initials
        self.assertGreater(m.residual(), 0)

    def test_search_on_a_subset_finds_zero_residual(self):
        sub = {n: p for n, p in self.planes.items() if M.syl(n)[0] in (0, 2, 15, 16)}
        lc, tc = M.search_classes(sub)
        m = M.Model(sub, lc, tc)
        self.assertEqual((len(m.bad), m.residual()), (0, 0))
        self.assertLessEqual(max(lc) + 1, 12)
        self.assertEqual(len({lc[0], lc[2], lc[16]}), 2)      # ㄱ apart from ㄴ / ㅌ, which share a class
        self.assertEqual(lc[2], lc[16])

    def test_cluster(self):
        rows = {"a": {1: "x", 2: "y"}, "b": {2: "y", 3: "z"}, "c": {1: "q"}, "d": {4: "w"}}
        where, merged, cells, ok = M.cluster(rows, 3)
        self.assertTrue(ok)
        self.assertEqual(where["a"], where["b"])
        self.assertNotEqual(where["a"], where["c"])
        self.assertEqual(len(merged), 3)
        where, merged, cells, ok = M.cluster(rows, 2)   # d merges without evidence to meet the limit
        self.assertTrue(ok)
        self.assertEqual(len(merged), 2)
        _, _, _, ok = M.cluster({"a": {1: "x"}, "b": {1: "y"}, "c": {1: "z"}}, 2)
        self.assertFalse(ok)


class TestFace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fbit, htbl, rule = synthetic()
        cls.fb, cls.ht = M.Fbit3(fbit), M.Htbl1(htbl)
        cls.rules = (rule,)
        lc, tc = synthetic_classes()
        cls.b = M.Build(cls.fb, cls.ht, lc, tc)

    def test_statuses_and_sets(self):
        c = self.b.counts()
        self.assertEqual(c["ks"] + c["regular"] + c["guess"], M.N)
        self.assertEqual(c["ks"], 2350)
        t, images = self.b.tables()
        ni, nm, nf = self.b.sets
        self.assertLessEqual((ni, nm, nf), (32, 24, 16))
        self.assertEqual(nf, 2)                    # the two vowel groups of the finals
        self.assertEqual(nm, 2)                    # two lead groups per vowel

    def test_regular_syllables_follow_the_rule(self):
        # the slot rule is a function of the classes, so a regular extrapolation reproduces it exactly
        for n in range(M.N):
            if self.b.status[n] == "regular":
                L, V, T = M.syl(n)
                gs = [g for g in self.rules[0](L, V, T) if g is not None]
                want = 0
                for g in gs:
                    want |= self.fb.glyphs[g]
                self.assertEqual(self.b.composed(n), want, chr(0xAC00 + n))

    def test_face_v1_v2_exact(self):
        for ver in (1, 2):
            data, parts = M.write_face(self.b, None, ver)
            r = M.verify(data, self.b)
            self.assertEqual(r, {"ks_bad": [], "all_bad": [], "compat_bad": []})
            f = J.parse_svfn(data)
            self.assertEqual(J.unpack(f.jset).lc, 2)
            s = M.size_table(data)
            self.assertEqual(s["total"], len(data))
            self.assertGreaterEqual(s["padding"], 0)

    def test_cell_bytes_round_trip(self):
        v = self.fb.glyphs[5]
        self.assertEqual(M._bm(M.cell_bytes(v, H), H), v)
        self.assertEqual(len(M.cell_bytes(v, H)), 24)


def _nfnt(chars):
    """A tiny NFNT record: chars {code: (ow_offset, advance, rows of '0'/'1' strings)}, strike height 5, ascent 4."""
    first, last = min(chars), max(chars)
    frh, asc = 5, 4
    loc, x = [], 0
    for c in range(first, last + 3):
        loc.append(x)
        if c in chars:
            x += len(chars[c][2][0])
    rw = (x + 15) // 16
    img = [0] * frh
    for c in range(first, last + 1):
        if c in chars:
            for y, r in enumerate(chars[c][2]):
                for i, p in enumerate(r):
                    if p == "1":
                        img[y] |= 1 << (rw * 16 - 1 - (loc[c - first] + i))
    ow = [(chars[c][0] << 8 | chars[c][1]) if c in chars else 0xFFFF for c in range(first, last + 1)] + [0xFFFF, 0xFFFF]
    head = struct.pack(">HHHHhhHHHHHHH", 0x9000, first, last, 8, 0, -1, 8, frh, 0, asc, 1, 0, rw)
    return (head + b"".join(r.to_bytes(rw * 2, "big") for r in img) + struct.pack(">%dH" % len(loc), *loc)
            + struct.pack(">%dH" % len(ow), *ow))


def _fork(res):
    """A resource fork holding {(type, id): bytes}."""
    data = b""
    offs = {}
    for k, b in res.items():
        offs[k] = len(data)
        data += struct.pack(">I", len(b)) + b
    types = sorted({t for t, _ in res})
    tl = bytearray(struct.pack(">H", len(types) - 1))
    refs = bytearray()
    ref0 = 2 + 8 * len(types)
    for t in types:
        ids = [k for k in res if k[0] == t]
        tl += struct.pack(">4sHH", t.encode("mac_roman"), len(ids) - 1, ref0 + len(refs))
        for k in ids:
            refs += struct.pack(">hHIi", k[1], 0xFFFF, offs[k], 0)
    m = bytearray(28) + tl + refs
    struct.pack_into(">HH", m, 24, 28, len(m))
    doff = 256
    return struct.pack(">IIII", doff, doff + len(data), len(data), len(m)) + bytes(doff - 16) + data + bytes(m)


class TestLatin(unittest.TestCase):
    def test_fond_nfnt_and_cells(self):
        chars = {0x41: (0, 4, ["0110", "1001", "1111", "1001", "0000"]),
                 0x67: (0, 4, ["0000", "0111", "1001", "0111", "0001"])}
        fond = bytearray(52) + struct.pack(">HHHH", 0, 12, 0, 300)
        fork = M.resource_fork(_fork({("FOND", 1): bytes(fond), ("NFNT", 300): _nfnt(chars)}))
        g = M.nfnt_glyphs(M.nfnt_for_size(fork, 12), chars=range(0x41, 0x68))
        self.assertEqual(sorted(g), [0x41, 0x67])
        self.assertEqual(g[0x41][1], 4)
        with self.assertRaises(ValueError):
            M.nfnt_for_size(fork, 9)
        cells, notes = M.latin_cells(g, 4, 3)     # 4x4 cell, baseline row 3: 'A' (4 rows above) is drawn 1 up
        self.assertEqual((cells[0x41][2], cells[0x67][2]), (-1, 0))
        self.assertEqual(notes, [])
        cells, notes = M.latin_cells(g, 4, 4)     # baseline row 4: the descender of 'g' is drawn 1 down
        self.assertEqual((cells[0x41][2], cells[0x67][2]), (0, 1))
        self.assertEqual(M._bm(M.cell_bytes(cells[0x67][0], 4), 4) >> 12, 0b0111)   # top row: stored 1 higher

    def test_wide_glyph_shifted(self):
        g = {0x57: (1, 5, 2, [[1, 1, 1, 1], [1, 0, 0, 1]])}
        cells, notes = M.latin_cells(g, 4, 3)
        self.assertEqual(len(notes), 1)
        self.assertIn("shifted -1", notes[0])


def _distinct(fb, ht):
    """(slots, bitmaps) referenced per plane by the 2,350 KS syllables and the one-plane compat jamo (in their kind's plane)."""
    slots = [set(), set(), set()]
    for e in ht.syllables.values():
        for p, g in enumerate(e):
            if g is not None:
                slots[p].add(g)
    for k, e in ht.compat.items():
        gs = [g for g in e if g is not None]
        if len(gs) == 1:
            slots[{"i": 0, "v": 1, "f": 2}[J.COMPAT[k][0]]].add(gs[0])
    return slots, [{fb.glyphs[g] for g in s} for s in slots]


def _with_dups(fbit, a, b):
    """The fbit with the glyph of slot b overwritten by slot a's bytes."""
    gb = (H * H + 7) // 8
    out = bytearray(fbit)
    out[0x54 + b * gb:0x54 + (b + 1) * gb] = fbit[0x54 + a * gb:0x54 + (a + 1) * gb]
    return bytes(out)


def _mac_cells(fbit, htbl):
    """{cp: cell bytes} of every Mac composition (macfbit3.Fbit3.compose), 51 compat + 2,350 KS."""
    m3 = M3.Fbit3(fbit, htbl)
    out = {}
    for hi, lo in m3.codes():
        rows = m3.compose(hi, lo)
        nb = (m3.h + 7) // 8
        out[ord(bytes([hi, lo]).decode("euc_kr"))] = b"".join((r << (nb * 8 - m3.h)).to_bytes(nb, "big") for r in rows)
    return out


class TestDirect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fbit, cls.htbl, _ = synthetic()
        cls.fb, cls.ht = M.Fbit3(cls.fbit), M.Htbl1(cls.htbl)

    def test_verify_direct_refuses_a_list_face(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="macfbit-list-") as d:
            out = os.path.join(d, "L.SVF")
            r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "svf_synth.py"),
                                "--jmap-variant", "list1", "--from",
                                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "svf", "dos",
                                             "NEODG16G.SVF"), out], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out, "rb") as fh:
                data = fh.read()
        import contextlib, io
        with tempfile.TemporaryDirectory(prefix="macfbit-listcli-") as d:      # the CLI: a clean message, exit 1, no traceback
            fp, hp, lp = (os.path.join(d, n) for n in ("f.fbit", "h.htbl", "L.SVF"))
            for pth, b in ((fp, self.fbit), (hp, self.htbl), (lp, data)):
                with open(pth, "wb") as fh:
                    fh.write(b)
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(M.main(["verify", lp, fp, hp]), 1)
            self.assertIn("is not a direct-mode face", err.getvalue())
        with self.assertRaisesRegex(ValueError, r"verify: a LIST face \(JSET version 3 flag 0x08\) is not a direct-mode face"):
            M.verify_direct(data, self.fbit, self.htbl)

    def test_direct_golden(self):
        data, info = M.write_direct(self.fb, self.ht, dedup=False)
        r = M.verify_direct(data, self.fbit, self.htbl)
        self.assertEqual(r, {"ks_bad": [], "compat_bad": [], "non_ks_present": 0})
        slots, _ = _distinct(self.fb, self.ht)
        jm, num = M.direct_jmap(self.fb, self.ht, dedup=False)
        self.assertEqual((jm.pi, jm.pm, jm.pf), tuple(len(s) for s in slots))
        self.assertEqual(sorted(num.values()), sorted(set().union(*slots)))
        self.assertEqual(len(jm.entries), 2350)
        f = J.parse_svfn(data)
        self.assertEqual(struct.unpack_from("<H", f.jset, 4)[0], 3)
        self.assertEqual(sum(1 for cp in f.glyphs if cp >= J.PIECE_BASE), jm.pi + jm.pm + jm.pf)

    def test_direct_dedup_default(self):
        _, bms = _distinct(self.fb, self.ht)
        jm, _ = M.direct_jmap(self.fb, self.ht)
        self.assertEqual((jm.pi, jm.pm, jm.pf), tuple(len(b) for b in bms))
        jn, _ = M.direct_jmap(self.fb, self.ht, dedup=False)
        d1, _ = M.write_direct(self.fb, self.ht)
        d2, _ = M.write_direct(self.fb, self.ht, dedup=False)
        self.assertLessEqual(len(d1), len(d2))
        for d in (d1, d2):
            self.assertEqual(M.verify_direct(d, self.fbit, self.htbl), {"ks_bad": [], "compat_bad": [], "non_ks_present": 0})
        # identical bitmaps in one plane fold, the same bitmap in another plane does not (PR-8)
        fbit = _with_dups(_with_dups(self.fbit, 0, 1), 0, 114)
        fb = M.Fbit3(fbit)
        slots, bms = _distinct(fb, self.ht)
        self.assertLess(len(bms[0]), len(slots[0]))
        j1, _ = M.direct_jmap(fb, self.ht)
        j2, _ = M.direct_jmap(fb, self.ht, dedup=False)
        self.assertEqual((j1.pi, j1.pm, j1.pf), tuple(len(b) for b in bms))
        self.assertEqual((j2.pi, j2.pm, j2.pf), tuple(len(s) for s in slots))
        for dedup in (True, False):
            d, _ = M.write_direct(fb, self.ht, dedup=dedup)
            self.assertEqual(M.verify_direct(d, fbit, self.htbl), {"ks_bad": [], "compat_bad": [], "non_ks_present": 0})

    def test_slot_in_two_planes_is_refused(self):
        ht = M.Htbl1(self.htbl)
        n = ord("각") - 0xAC00
        i, m, f = ht.syllables[n]
        ht.syllables[n] = (i, i, f)
        with self.assertRaises(ValueError):
            M.direct_jmap(self.fb, ht)

    def test_multi_plane_compat_is_stored_whole(self):
        # a compat entry with two planes: blank JMAP compat, the OR stored at U+3131 + k (PR-10)
        ht = M.Htbl1(self.htbl)
        k = 5
        ht.compat[k] = (ht.syllables[0][0], ht.syllables[0][1], None)
        data, info = M.write_direct(self.fb, ht)
        f = J.parse_svfn(data)
        jm = J.unpack(f.jset)
        self.assertEqual(jm.block_compat[k], J.BLANK)
        self.assertIn(0x3131 + k, f.glyphs)
        want = M.cell_bytes(M.mac_compose(self.fb, ht.compat[k]), H)
        self.assertEqual(f.glyphs[0x3131 + k], want)

    def test_direct_with_jset(self):
        lc, tc = synthetic_classes()
        b = M.Build(self.fb, self.ht, lc, tc)
        data, info = M.write_direct(self.fb, self.ht, with_jset=b)
        f = J.parse_svfn(data)
        jm = J.unpack(f.jset)
        self.assertIsNotNone(jm.fallback)
        self.assertTrue(struct.unpack_from("<B", f.jset, 6)[0] & J.JMAP_FLAG_FALLBACK)
        r = M.verify_direct(data, self.fbit, self.htbl)
        self.assertEqual((r["ks_bad"], r["compat_bad"], r["non_ks_present"]), ([], [], M.N - 2350))
        for n in range(M.N):
            if n not in b.planes:
                self.assertEqual(J.compose(f, jm, 0xAC00 + n), M.cell_bytes(b.composed(n), H), n)
        data2, _ = M.write_direct(self.fb, self.ht, with_jset=b, jset_version=2)
        self.assertEqual(J.unpack(J.parse_svfn(data2).jset).fallback_version, 2)
        self.assertEqual(M.verify_direct(data2, self.fbit, self.htbl)["ks_bad"], [])

    def test_derived_unchanged(self):
        lc, tc = synthetic_classes()
        b = M.Build(self.fb, self.ht, lc, tc)
        want, _ = M.write_face(b, None, 1)
        with tempfile.TemporaryDirectory() as d:
            paths = {}
            for name, blob in (("f.fbit", self.fbit), ("h.htbl", self.htbl)):
                paths[name] = os.path.join(d, name)
                open(paths[name], "wb").write(blob)
            cls = os.path.join(d, "c.json")
            open(cls, "w").write('{"lc": %s, "tc": %s}' % (lc, tc))
            out = os.path.join(d, "o.svf")
            self.assertEqual(M.main(["build", paths["f.fbit"], paths["h.htbl"], "-o", out, "--classes", cls,
                                     "--mode", "derived"]), 0)
            self.assertEqual(open(out, "rb").read(), want)
            out2 = os.path.join(d, "d.svf")
            rep = os.path.join(d, "r.json")
            self.assertEqual(M.main(["build", paths["f.fbit"], paths["h.htbl"], "-o", out2, "--report", rep]), 0)
            got = open(out2, "rb").read()
            self.assertEqual(struct.unpack_from("<H", J.parse_svfn(got).jset, 4)[0], 3)       # direct is the default
            import json
            r = json.load(open(rep))
            self.assertEqual(r["mode"], "direct")
            self.assertEqual(r["jmap"], len(J.parse_svfn(got).jset))
            self.assertEqual(r["pieces"], r["sizes"]["n_pieces"])
            self.assertIn("pieces_as_slots", r)
            out3 = os.path.join(d, "n.svf")
            self.assertEqual(M.main(["build", paths["f.fbit"], paths["h.htbl"], "-o", out3, "--no-dedup"]), 0)
            self.assertGreaterEqual(os.path.getsize(out3), len(got))
            self.assertEqual(M.main(["verify", out2, paths["f.fbit"], paths["h.htbl"]]), 0)   # mode from the face
            self.assertEqual(M.main(["verify", out, paths["f.fbit"], paths["h.htbl"], "--classes", cls]), 0)

    def test_verify_big_face_uses_big_limits(self):
        lc, tc = synthetic_classes()
        seen = []
        real = M.Build
        with tempfile.TemporaryDirectory() as d:
            paths = {}
            for name, blob in (("f.fbit", self.fbit), ("h.htbl", self.htbl)):
                paths[name] = os.path.join(d, name)
                open(paths[name], "wb").write(blob)
            cls = os.path.join(d, "c.json")
            open(cls, "w").write('{"lc": %s, "tc": %s}' % (lc, tc))
            out = os.path.join(d, "o.svf")
            M.main(["build", paths["f.fbit"], paths["h.htbl"], "-o", out, "--classes", cls, "--mode", "derived"])
            args = ["verify", out, paths["f.fbit"], paths["h.htbl"], "--classes", cls]
            for big in (False, True):
                seen.clear()
                with mock.patch.object(M, "Build", lambda *a, **k: (seen.append(k.get("limits")), real(*a, **k))[1]), \
                        mock.patch.object(J, "needs_big", lambda t: big):
                    self.assertEqual(M.main(args), 0)
                self.assertEqual(seen, [(128, 128, 64) if big else M.SET_LIMITS])

    def test_compat_slot_in_another_plane_is_refused(self):
        ht = M.Htbl1(self.htbl)
        k = next(k for k in ht.compat if J.COMPAT[k][0] == "i")
        ht.compat[k] = (ht.syllables[0][1], None, None)       # a medial slot as an initial-kind compat jamo
        with self.assertRaises(ValueError):
            M.direct_jmap(self.fb, ht)

    def test_cli_sheets_and_damaged_face(self):
        lc, tc = synthetic_classes()
        with tempfile.TemporaryDirectory() as d:
            fp, hp, cls = (os.path.join(d, n) for n in ("f.fbit", "h.htbl", "c.json"))
            open(fp, "wb").write(self.fbit)
            open(hp, "wb").write(self.htbl)
            open(cls, "w").write('{"lc": %s, "tc": %s}' % (lc, tc))
            out = os.path.join(d, "o.svf")
            with self.assertRaises(SystemExit):                  # direct (default) draws no sheets: refused, not dropped
                M.main(["build", fp, hp, "-o", out, "--sheets", os.path.join(d, "s")])
            with self.assertRaises(SystemExit):
                M.main(["build", fp, hp, "-o", out, "--with-jset", "--classes", cls, "--name", "x"])
            try:
                import PIL  # noqa: F401
            except ImportError:
                pass
            else:
                self.assertEqual(M.main(["build", fp, hp, "-o", out, "--mode", "derived", "--classes", cls,
                                         "--sheets", os.path.join(d, "s")]), 0)
            # a face with a JMAP block that is unusable (the pieces' glyphs lost) is named, not sent to --classes
            data, _ = M.write_direct(self.fb, self.ht)
            f = J.parse_svfn(data)
            rows = [(cp, g, H, 0, H) for cp, g in f.glyphs.items() if cp != J.PIECE_BASE]
            bad = J.write_svfn(H, H, 10, rows, f.jset)
            bp = os.path.join(d, "bad.svf")
            open(bp, "wb").write(bad)
            self.assertTrue(J.parse_svfn(bad).jset_bad)
            with self.assertRaises(SystemExit):
                M.main(["verify", bp, fp, hp])

    def test_report_fallback_pieces_and_auto(self):
        lc, tc = synthetic_classes()
        b = M.Build(self.fb, self.ht, lc, tc)
        d1, p1 = M.write_direct(self.fb, self.ht, with_jset=b)
        d2, p2 = M.write_direct(self.fb, self.ht, with_jset=b, jset_version="auto")
        self.assertEqual(M.verify_direct(d2, self.fbit, self.htbl)["ks_bad"], [])
        self.assertGreater(len(p1["pieces"]), len(p1["slots"]))
        _, p0 = M.write_direct(self.fb, self.ht)
        self.assertEqual(len(p0["pieces"]), len(p0["slots"]))

    def test_direct_c_reader(self):
        import test_c_renderer as TC
        exe = TC.build_reader("jmap")["svfdump-asan"]
        for with_jset in (False, True):
            lc, tc = synthetic_classes()
            b = M.Build(self.fb, self.ht, lc, tc) if with_jset else None
            data, _ = M.write_direct(self.fb, self.ht, with_jset=b)
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, "f.svf")
                open(path, "wb").write(data)
                for opts in ((), ("--stream=4:512",)):
                    r = M.cverify_direct(path, self.fbit, self.htbl, exe, opts)
                    self.assertEqual((r["ks_bad"], r["compat_bad"], r["is_jamo"]), ([], [], 1), opts)
                    self.assertEqual(r["non_ks_ink"] <= M.N - 2350, True)
                    if not with_jset:
                        self.assertEqual(r["non_ks_ink"], 0)


NAMES = ("Seoul12", "AppleGothic12", "AppleGothic24", "AppleMyungjo12", "AppleMyungjo24")
# the writer's output itself (size, sha256; dedup on, off): a hash only, no Apple byte. A change that keeps the
# composition but alters the bytes (piece order, dedup choice) fails here.
DIRECT_PINS = {
    "Seoul12": ((15016, "13d0d4f5da9142b7164ce42149c6463e0cbed9359351c5d5e55d7f0283eda56a"),
                (22980, "bca2a2216a8adb26654d402588ae7f50e94205e43ccab7361c63cc17508609aa")),
    "AppleGothic12": ((19864, "c0616f79a27b50b3e05f6dc81b7627c4a1ec29569fb3db12859001085fc73679"),
                      (23300, "6264f0178c26f146c2d176aff5481bb5fb714786a5deccaef7b5ee6392473979")),
    "AppleGothic24": ((31212, "7ef825c09eeaf5af2a16cea468b7396d0e122bcd14114300a0eccfbae2ef26e0"),
                      (32128, "57f7cfb1426278cf67fcbd8127656f0149bfb2844292d026726bc8c369ac6f55")),
    "AppleMyungjo12": ((20788, "9a64a83efb8e0cbb1b637839aed632c319b4c9017ca3d6cc9712007e91074c30"),
                       (23404, "415ef3fb8ebbae00d81a8d8f481e0b1d1a5c8d01ea37b5deab0b400d26d62705")),
    "AppleMyungjo24": ((32044, "7d78c2e9434a65cfd6f0610d3d5feb32f169a1534618b5a8a6c6a51e80e71ddf"),
                       (32520, "fbf3ba5b07823ed62e4af8db84d1ea13a2c81aadd097951fe0d2d12cb4a9e5e5")),
}


@unittest.skipUnless(os.environ.get("SVF_MAC71_INPUTS"), "SVF_MAC71_INPUTS (a directory of <Name>.fbit and <Name>.htbl1) is not set")
class RealFaces(unittest.TestCase):
    def test_five_faces(self):
        d = os.environ["SVF_MAC71_INPUTS"]
        exe = None
        try:
            import test_c_renderer as TC
            exe = TC.build_reader("jmap")["svfdump-asan"]
        except unittest.SkipTest:
            pass
        for name in NAMES:
            fbit = open(os.path.join(d, name + ".fbit"), "rb").read()
            htbl = open(os.path.join(d, name + ".htbl1"), "rb").read()
            fb, ht = M.Fbit3(fbit), M.Htbl1(htbl)
            for dedup in (True, False):
                data, _ = M.write_direct(fb, ht, dedup=dedup)
                with self.subTest(name=name, dedup=dedup):
                    import hashlib
                    self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), DIRECT_PINS[name][0 if dedup else 1])
                    r = M.verify_direct(data, fbit, htbl)
                    self.assertEqual(r, {"ks_bad": [], "compat_bad": [], "non_ks_present": 0})
                    if exe and dedup:
                        with tempfile.TemporaryDirectory() as t:
                            path = os.path.join(t, "f.svf")
                            open(path, "wb").write(data)
                            for opts in ((), ("--stream=4:512",)):
                                c = M.cverify_direct(path, fbit, htbl, exe, opts)
                                self.assertEqual((c["ks_bad"], c["compat_bad"], c["is_jamo"]), ([], [], 1))


if __name__ == "__main__":
    unittest.main()
