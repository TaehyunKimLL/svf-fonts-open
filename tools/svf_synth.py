#!/usr/bin/env python3
"""Synthetic SVFN faces for the C renderer's tests (tools/test_c_renderer.py), written with jamoset.write_svfn.

  svf_synth.py --jset-bad KIND --from FACE OUT     FACE (a valid jamo set face) with its JSET block (version 2) broken
                                                   one way; with --jset-version 1 a version 1 block (BAD_KINDS_V1)
  svf_synth.py --reencode --from FACE OUT          FACE with its JSET block written in the --jset-version (1: pack_v1,
                                                   the piece numbers kept; 2: jamoset.pack, the pieces renumbered), in
                                                   FACE's own layout unless --profile / --units is given
  svf_synth.py --jset-variant V --from FACE OUT    FACE with a valid version 2 block of another shape (below)
  svf_synth.py --jmap-variant V --from FACE OUT    FACE with a valid JSET block version 3 (JMAP) built from its tables by
                                                   jamoset.jmap_from_tables (JMAP_VARIANTS, below)
  svf_synth.py --jmap-bad KIND --from FACE OUT     FACE with a JMAP block broken one way (JMAP_BAD_KINDS, below)
  svf_synth.py --jmap-variant L --from FACE OUT    L in LIST_VARIANTS: FACE with a JSET version 3 LIST (flag 0x08) block
  svf_synth.py --jmap-bad KIND --from FACE OUT     KIND in LIST_BAD_KINDS: a LIST block broken one way (below)
  svf_synth.py --jset-unused-finset --from FACE OUT
                                                   FACE with 3 final sets (copies of set 0) and finSet = 3 in every cell
                                                   of a tail class no tail 1..27 uses (valid: the engine never reads
                                                   those cells)
  svf_synth.py --jset-cut N --from FACE OUT        FACE with its JSET block cut to its first N bytes
  svf_synth.py --bpp8 --from FACE OUT              FACE (1 bpp) at 8 bpp: every pixel a level that depends on the glyph
                                                   and the position (ink 128..255, background 0..15, some 0), so the
                                                   pieces of a syllable overlap with different levels everywhere
  svf_synth.py --marks OUT                         a 16 px 1 bpp face with flags bit 2 (marks at origin) and metrics, no
                                                   JSET: A, e, U+FFFD (a box), and the combining marks U+0301 (acute)
                                                   and U+0300 (grave) with negative bearings, stored with the pen at
                                                   column -bearing so their ink lies left of the pen

The shipped writers (jamoset.py, jamovec.py, jamoaa.py, svf2to3.py) default to --jset-version 1, the standard (spec
amendment 3); this test tool keeps 2 because most of its cases exercise the version 2 reader and its refusals.

Every face is rebuilt from FACE's glyphs, metrics and dy (header, code points, JSET, metrics, glyphs), so the cmap
glyphs are those of FACE. --jset-version 2 (the default): every JSET written is version 2 (jamoset.pack), the plane-15
piece glyphs renumbered by its piece map (jamoset.renumber_glyphs). --jset-version 1: the block is jamoset.pack_v1 of
FACE's tables (piece numbers as they are) for --reencode, --jset-bad (BAD_KINDS_V1 below), --jset-cut,
--jset-unused-finset and --bpp8; --jset-variant is version 2 only. Version 2 bad kinds, each a field edit (jamoset.Jset2) of FACE's packed block breaking one
rule of jamoset.unpack and the C reader; "the alias edit" first turns the last fresh slot of initial row 0 into an alias
of its own piece (NA = 1, still valid):

  lc13, tc13, ni33, nm25, nf17
                    a well-formed block (length matching its counts) with 13 lead classes, 13 tail classes, 33 initial,
                    25 medial or 17 final sets; the extra classes and sets copy the first one (BAD_KINDS_STD: bad for the
                    narrow readers, valid tables for a BIG reader)
  lc20, tc29, ni129, nm129, nf65
                    the same, one past each BIG cap (BAD_KINDS_BIG, versions 1 and 2): refused by every reader
  length            the block one byte longer than its counts give
  leadclass         leadClass[18] = LC
  finset            3 final sets (copies of set 0) and a finSet entry = 3 in a cell of a tail class some tail 1..27 uses
  initset           an initSet entry = NI (FACE's NI must not be a power of two)
  missing_piece     the last final row's base past every piece glyph (fresh pieces with no glyph)
  magic             the block's magic "JSEX"
  version           version 1 on the version 2 body (a version 1 reader refuses its length)
  version4          version 4
  short             the block cut to 11 bytes (shorter than its header)
  na_over           NA one above the slot count (the alias table that long, so the length matches)
  reserved          the reserved u16 = 1
  pad_bits          initial row 0's presence bit 19 (padding) set
  alias_no_presence the alias edit, then medial row 0's presence bit 0 cleared and its alias bit 0 set
  abase_over        the alias edit, then initial row 0's abase = 1 (abase + 1 alias > NA = 1)
  alias_blank       the alias edit, then alias[0] = 0xFFFF
  missing_alias_piece
                    the alias edit, then alias[0] = a piece with no glyph
  base_wrap         initial row 0's base = 0xFFF0 (its 19 fresh pieces reach past 0xFFFE)
  compat_set_over   compat ㅏ (U+314F) names medial set NM
  compat_slot_blank compat ㅎ (U+314E) names the last initial set, whose ㅎ presence bit is cleared
  compat_bits56     compat ㄱ with bit 5 set
  compat_vowel_bit7, compat_tt_bit7, compat_pp_bit7, compat_jj_bit7, compat_cluster_bit7
                    bit 7 on compat ㅏ, ㄸ, ㅃ, ㅉ or ㄳ (only a lead-capable consonant with a final form may carry it)

Version 1 bad kinds (--jset-version 1 --jset-bad KIND; the kinds of c592140, each one rule of jamoset.unpack's
version 1 reader and the C version 1 reader):

  lc13, tc13, ni33, nm25, nf17
                    as above, in a version 1 block
  length            the block one byte longer than its counts give
  leadclass         leadClass[18] = LC
  finset            a finSet entry = NF in a cell of a tail class some tail 1..27 uses
  missing_piece     compatPiece[50] (U+3163) names a piece with no glyph
  magic             the block's magic "JSEX"
  version           JSET version 2 on the version 1 body (a version 2 reader refuses its length)
  short             the block cut to 11 bytes (shorter than its header)

Valid variants (--jset-variant):

  alias             the alias edit (NA = 1)
  bit7              compat ㄱ as 0x80 (final set 0, whose ㄱ slot is present)
  overlap           the bases of initial rows 0 and 1 swapped (fresh ranges out of order)
  limits            12 x 12 classes, 32/24/16 sets (W = 14; the copied sets make aliases)
  w0                1 x 1 class, 1/1/1 sets from FACE's set-0 rows (W = 0, no set table), compat from set 0
  limits_big        19 x 28 classes, 128/128/64 sets, every slot its own piece (NA 0; v2 29,708 B, with --jset-version 1
                    47,373 B), a glyph for every piece; BIG readers only
  limits_big_alias  the same, every slot an alias (NA = 6,848; 45,068 B; version 2 only)

JMAP faces keep FACE's non-piece glyphs and replace its plane-15 piece glyphs by the pieces of the JMAP planes (and, in a
hybrid, of the fallback at U+F0000 + PI+PM+PF + the original piece number; the pieces' dy is not carried over). FACE must
be a face with JSET tables (version 1 or 2), not itself a JMAP face. Variants (all advance 16 but adv0; sparse = every 5th
syllable):

  sparse3, dense3   3 byte entries, NS about 2235 / 11172
  sparse4, dense4   4 byte entries: every plane padded with 300 unused pieces (PI, PM, PF > 255) and 60 entries naming
                    padded pieces with indices 256.. in all three planes (the high bits of the entry bytes)
  hybrid1, hybrid2  16 exception syllables, the fallback FACE's own JSET as version 1 / 2 (pieces shifted past the planes);
                    hybrid1 blanks the JMAP's compat[0] so the fallback's compat answers it (PR-10)
  dhybrid1, dhybrid2  dense3 with a version 1 fallback / dense4 (padded planes) with a version 2 fallback: the fallback
                    follows 11,172 entries (the 118 byte base; a region of 34 / 45 KB, past a streamed face's load maximum)
  adv0              sparse3 with advance 0 (the cell width)
  adv0fb            hybrid1 with advance 0 in the JMAP and in its fallback (R4's equality at 0)
  hybrid_big1, hybrid_big2  hybrid1 / hybrid2 over the limits_big tables (19 x 28 classes, 128/128/64 sets): the JMAP lists 16
                    syllables, the fallback is a BIG JSET version 1 / 2 (FACE only supplies the glyph template and the profile);
                    a reader without SVF_JSET_BIG reads the JMAP part alone (fallback JSET_UNREAD)
  sparse_full       the SPARSE flag with NS = 11,172 (a full exception list, PR-21; jamoset.pack_jmap writes such a table dense,
                    so this block is assembled by hand: every rank 256 * b, every bitmap bit set)
  blanks            sparse3 with some entries' m = 0 and some tail syllables' f = 0
  pi2047            4 byte entries, PI 2047, PM 1, PF 1 (built by hand, not by jmap_from_tables)

Bad kinds, each breaking one rule of unpack_jmap (R1-R7; the rule is the first its message names) except
jmap_missing_piece and jmap_region_max (below). The 3 byte kinds (jmap_pi256_3b, jmap_entry_over) and the 4 byte kinds
(jmap_pi2048_4b, jmap_pf1024_4b, jmap_entry_over_4b) refuse a FACE whose tables make the block the other width:

  jmap_short            the block cut to 100 bytes (R1)           jmap_flags            flags 0x0A: LIST + SPARSE (R1')
  jmap_pi256_3b         PI 256 in a 3 byte block (R2)             jmap_pi2048_4b        PI 2048 in a 4 byte block (R2)
  jmap_pf1024_4b        PF 1024 in a 4 byte block (R2)            jmap_zero_pieces      PI = PM = PF = 0 (R2)
  jmap_ns0              sparse NS = 0 (R3)                        jmap_dense_ns         dense NS = 11171 (R3)
  jmap_length           one byte too long (R4)                    jmap_fallback_short   the fallback 11 bytes (R4)
  jmap_fallback_bad     the fallback magic "JSEX" (R4)            jmap_fallback_v3      the fallback version 3 (R4)
  jmap_fallback_adv     the fallback advance 17, the JMAP 16 (R4) jmap_compat_over      compat[0] = PI+PM+PF (R5)
  jmap_pad              sparse pad byte 1 (R6)                    jmap_bitmap_tail      bitmap bit 11172 set (R6)
  jmap_rank_wrong       rank[1] one too high (R6)                 jmap_ns_popcount      one more bitmap bit than NS (R6)
  jmap_entry_over       a 3 byte entry's i = PI + 1 (R7)          jmap_entry_over_4b    a 4 byte entry's m = PM + 1 (R7)
  v2_as_v3              FACE's version 2 block relabelled version 3: the first rule its fields break (R3 for NEODG16G)
  jmap_missing_piece    valid block, the face lacks the last piece's glyph (R8: a plain face, JMAP_BAD; unpack passes)
  jmap_region_max       valid block, the header's JSET size 0x10000 over a file that holds it (PR-7: the C reader clips
                        it to 0xFFFF, JMAP_BAD; Python unpacks the 65,536 byte region: R4 over the region limit)

LIST variants (LIST_VARIANTS; JMAP_VARIANTS stay as they are, PL-14). The source tables are first re-encoded with advance
16 through pack_fallback in their own version (numbers kept; NEODG16G says 0), so the LIST advance, the fallback's byte 11
(PL-9), is non-zero. list1 has 38 entries, s = 0, 300, ..., 11,100: even positions whole cells (the composed cell, made
distinct, a new piece), odd positions recombinations of fallback pieces composing differently from the fallback's own
(the pixels tell LIST from fallback). The planes are the source's plane-15 glyphs plus the new pieces:

  list1         fallback in the source's version                      list2         list1 over a version 2 fallback, pieces 5, 3, 9, ...
  list_nofb     one entry (s 5,000), no fallback          list_blank    list1 + an all-BLANK entry and an (i, BLANK, BLANK) one
  list_zero     list1 + an entry naming piece 0           list_compat   list1 + a compat entry naming another jamo's piece
  list_max      NS 255 (keys 0 and 11,171), no fallback, region 2,158      list_big   list1 over the limits_big tables (BIG)

LIST bad kinds (LIST_BAD_KINDS: 16 LIST_HEADER_KINDS and 6 LIST_CONTENT_KINDS), byte edits of list1 (jlist_short_nofb and
jlist_length of list_nofb). Every kind breaks a rule of unpack_jmap, named first in its message, except the four of
LIST_UNPACK_PASSES (PL-4), which pass it:

  jlist_short, jlist_short_nofb  block cut to 100 bytes (R1)        jlist_sparse   LIST + SPARSE flags (R1)
  jlist_4b                      LIST + 4B flags (R1)                 jlist_flags    reserved flag bit 4 (R1)
  jlist_planes_i, _m, _f        PI / PM / PF = 1 (L2)                jlist_ns0      NS 0, entries kept (L3)
  jlist_ns256                   NS 256, entries kept (L3)            jlist_length   one byte too long (R4)
  jlist_fallback_short, _bad, _v3, _adv  as jmap_fallback_* (R4)
  jlist_key_equal               two equal keys (L6)                  jlist_key_desc two keys swapped (L6)
  jlist_key_over                last key 11,172 (L6)
  jlist_region_max              valid block, header JSET size 0x10000 over a file holding it (the C reader clips it to
                                0xFFFF; Python's R4 refuses the 65,536 byte region)
  jlist_field_noglyph, jlist_field_fffe, jlist_compat_noglyph   a field (or compat[0]) naming a piece without a glyph
                                (the glyph is absent, or the piece is 0xFFFE): unpack_jmap passes, parse_svfn's usable
                                rule (L5 / L7) marks the face JMAP_BAD

  svf_synth.py --layout-bad KIND --from FACE OUT   FACE (a v3 face, the `default` profile: u32 offsets) with its layout
                                                   or one record broken one way; LAYOUT_BAD names the error the C reader
                                                   gives (the record kinds are caught at a mapped open, and in a
                                                   streamed face when that glyph is read):

  rec7, row_gt_rec, reserved9, reserved10     header byte 9 / 10 faults (REC 7; ROW 3 over REC 2; reserved bits set)
  table_unaligned, data_unaligned, size_unaligned, entry_unaligned
                                              a table offset, the glyph data offset or size, an offset table entry that is
                                              not a multiple of its unit (the file is padded so no range fault comes first)
  offsets_decrease, offsets_overshoot, last_not_size, u16_past_data
                                              an inconsistent glyph offset table (the last: u16 entries over 256 KB of data)
  box_x, box_y, rows_past, record_3_bytes     glyph 5's record: x0 + wb past the pitch, y0 + h past the cell, rows past the
                                              record, a record of 3 bytes (the face is laid out byte-tight for it)
  jset_size, jset_zero                        the header's JSET size 1 over its counts, or 0 with the flag set: opens, a
                                              plain face (jset_bad=1)

--profile P / --units R,W,T,O (any kind but --layout-bad) write the v3 face in that layout (default: the `default` profile;
--box x|y|full sets the ink box policy); --layout-bad FACE is read as it is.

There is no default output path: OUT is required (--from FACE is required by every kind but --marks).
"""

import argparse
import copy
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jamoset  # noqa: E402

LAYOUT_BAD = {
    "rec7": "SVF_E_LAYOUT", "row_gt_rec": "SVF_E_LAYOUT", "reserved9": "SVF_E_LAYOUT", "reserved10": "SVF_E_LAYOUT",
    "table_unaligned": "SVF_E_LAYOUT", "data_unaligned": "SVF_E_LAYOUT", "entry_unaligned": "SVF_E_LAYOUT",
    "size_unaligned": "SVF_E_LAYOUT", "offsets_decrease": "SVF_E_LAYOUT", "offsets_overshoot": "SVF_E_LAYOUT",
    "last_not_size": "SVF_E_LAYOUT", "u16_past_data": "SVF_E_LAYOUT",
    "box_x": "SVF_E_RANGE", "box_y": "SVF_E_RANGE", "rows_past": "SVF_E_RANGE", "record_3_bytes": "SVF_E_RANGE",
    "jset_size": "jset_bad", "jset_zero": "jset_bad",
}
BAD_GLYPH = 5      # the glyph index whose record the box_x .. record_3_bytes kinds break
BAD_KINDS_STD = ("lc13", "tc13", "ni33", "nm25", "nf17")         # bad on the narrow readers, valid BIG tables
BAD_KINDS_BIG = ("lc20", "tc29", "ni129", "nm129", "nf65")       # one past one BIG cap: refused by every reader
BAD_KINDS = ("length", "leadclass", "finset", "initset", "missing_piece", "magic",
             "version", "version4", "short", "na_over", "reserved", "pad_bits", "alias_no_presence", "abase_over",
             "alias_blank", "missing_alias_piece", "base_wrap", "compat_set_over", "compat_slot_blank", "compat_bits56",
             "compat_vowel_bit7", "compat_tt_bit7", "compat_pp_bit7", "compat_jj_bit7", "compat_cluster_bit7"
             ) + BAD_KINDS_BIG
BAD_KINDS_V1 = ("lc13", "tc13", "ni33", "nm25", "nf17", "length", "leadclass", "finset", "missing_piece", "magic",
                "version", "short")
VARIANTS = ("alias", "bit7", "overlap", "limits", "w0", "limits_big", "limits_big_alias")
BIG_VARIANTS = ("limits_big", "limits_big_alias")
JMAP_VARIANTS = ("sparse3", "sparse4", "dense3", "dense4", "hybrid1", "hybrid2", "adv0", "blanks", "pi2047", "dhybrid1",
                 "dhybrid2", "sparse_full", "adv0fb", "hybrid_big1", "hybrid_big2")
JMAP_BAD_KINDS = ("jmap_short", "jmap_flags", "jmap_pi256_3b", "jmap_pi2048_4b", "jmap_pf1024_4b", "jmap_zero_pieces",
                  "jmap_ns0", "jmap_dense_ns", "jmap_length", "jmap_fallback_short", "jmap_fallback_bad",
                  "jmap_fallback_v3", "jmap_fallback_adv", "jmap_compat_over", "jmap_pad", "jmap_bitmap_tail",
                  "jmap_rank_wrong", "jmap_ns_popcount", "jmap_entry_over", "jmap_entry_over_4b", "jmap_missing_piece",
                  "jmap_region_max", "v2_as_v3")
LIST_VARIANTS = ("list1", "list2", "list_nofb", "list_blank", "list_zero", "list_compat", "list_max", "list_big")
LIST_BAD_KINDS = ("jlist_short", "jlist_short_nofb", "jlist_sparse", "jlist_4b", "jlist_flags", "jlist_planes_i",
                  "jlist_planes_m", "jlist_planes_f", "jlist_ns0", "jlist_ns256", "jlist_length", "jlist_fallback_short",
                  "jlist_fallback_bad", "jlist_fallback_v3", "jlist_fallback_adv", "jlist_key_equal", "jlist_key_desc",
                  "jlist_key_over", "jlist_region_max", "jlist_field_noglyph", "jlist_field_fffe",
                  "jlist_compat_noglyph")
LIST_UNPACK_PASSES = ("jlist_field_noglyph", "jlist_field_fffe", "jlist_compat_noglyph", "jlist_region_max")
LIST_CONTENT_KINDS = ("jlist_key_equal", "jlist_key_desc", "jlist_key_over", "jlist_field_noglyph", "jlist_field_fffe",
                      "jlist_compat_noglyph")
LIST_HEADER_KINDS = tuple(k for k in LIST_BAD_KINDS if k not in LIST_CONTENT_KINDS)
LIST_STRIDE = 300        # the list1 family lists every 300th syllable: 38 entries
JMAP_ADVANCE = 16        # the advance of every JMAP variant but adv0 (NEODG16G's own tables say 0 = the cell width)
JMAP_STRIDE = 5          # the sparse variants hold every 5th syllable


def load(path):
    with open(path, "rb") as fh:
        data = fh.read()
    f = jamoset.parse_svfn(data)
    if f.jset is None or not f.flags & jamoset.FLAG_VARIABLE:
        raise SystemExit(f"svf_synth: {path}: not a jamo set face with a metrics table")
    return f, jamoset.unpack(f.jset)


def rebuild(f, jset, profile="default", piece_map=None):
    """FACE's glyphs with @p jset (bytes) as its JSET block, written as v3 in @p profile (an empty block: the JAMO flag
    with JSET size 0); with @p piece_map (jamoset.pack's) the plane-15 piece glyphs renumbered by it."""
    glyphs = [(cp, g) + tuple(f.metrics[cp]) for cp, g in sorted(f.glyphs.items())]
    dy = f.dy
    if piece_map is not None:
        glyphs = sorted(jamoset.renumber_glyphs(glyphs, piece_map))
        dy = jamoset.renumber_glyphs(dict(f.dy), piece_map) if f.dy else f.dy
    data = jamoset.write_svfn(f.cell_w, f.cell_h, f.ascent, glyphs, jset,
                              f.flags & ~(jamoset.FLAG_VARIABLE | jamoset.FLAG_JAMO), bpp=f.bpp,
                              dy=dy, profile=profile)
    if not jset:     # pack_svfn writes no JAMO flag for an empty block; the cut-to-0 kind is the flag with size 0
        data = bytearray(data)
        struct.pack_into("<H", data, 6, struct.unpack_from("<H", data, 6)[0] | jamoset.FLAG_JAMO)
        data = bytes(data)
    return data


def widened(t, lc=None, tc=None, ni=None, nm=None, nf=None):
    """A copy of @p t with more lead classes, tail classes or sets; new ones copy class / set 0."""
    lc, tc, ni, nm, nf = lc or t.lc, tc or t.tc, ni or t.ni, nm or t.nm, nf or t.nf
    out = jamoset.Tables(lc, tc, ni, nm, nf, t.advance)
    out.lead_class, out.tail_class = list(t.lead_class), list(t.tail_class)
    for l in range(lc):
        for v in range(21):
            for c in range(tc):
                src = ((l if l < t.lc else 0) * 21 + v) * t.tc + (c if c < t.tc else 0)
                dst = (l * 21 + v) * tc + c
                out.init_set[dst], out.med_set[dst], out.fin_set[dst] = t.init_set[src], t.med_set[src], t.fin_set[src]
    out.init_piece = list(t.init_piece) + list(t.init_piece[:19]) * (ni - t.ni)
    out.med_piece = list(t.med_piece) + list(t.med_piece[:21]) * (nm - t.nm)
    out.fin_piece = list(t.fin_piece) + list(t.fin_piece[:27]) * (nf - t.nf)
    out.compat = list(t.compat)
    return out


def widened2(b, lc=None, tc=None, ni=None, nm=None, nf=None):
    """A copy of the Jset2 @p b with more lead classes, tail classes or sets (counts past the limits included); new
    classes copy class 0, new set rows copy row 0 (the same pieces)."""
    lc, tc, ni, nm, nf = lc or b.lc, tc or b.tc, ni or b.ni, nm or b.nm, nf or b.nf
    out = jamoset.Jset2(lc, tc, ni, nm, nf, b.advance, b.na, b.reserved)
    out.lead_class, out.tail_class = list(b.lead_class), list(b.tail_class)
    for l in range(lc):
        for v in range(21):
            for c in range(tc):
                src = ((l if l < b.lc else 0) * 21 + v) * b.tc + (c if c < b.tc else 0)
                dst = (l * 21 + v) * tc + c
                out.init_set[dst], out.med_set[dst], out.fin_set[dst] = b.init_set[src], b.med_set[src], b.fin_set[src]
    for key, n in (("i", ni), ("m", nm), ("f", nf)):
        rows = [list(r) for r in b.rows[key]]
        out.rows[key] = rows + [list(rows[0]) for _ in range(n - len(rows))]
    out.alias, out.compat = list(b.alias), list(b.compat)
    return out


def alias_edit(b):
    """The alias edit (in place): the last fresh slot of initial row 0 becomes an alias of its own piece; NA = 1. The
    other rows' abase is 1 (their alias bits are 0)."""
    if b.na:
        raise SystemExit("svf_synth: the alias edit needs a block without aliases")
    base, _, pres, _ = b.rows["i"][0]
    j = pres.bit_length() - 1
    piece = base + bin(pres & ((1 << j) - 1)).count("1")
    for key in "imf":
        for row in b.rows[key]:
            row[1] = 1
    b.rows["i"][0][1], b.rows["i"][0][3] = 0, 1 << j
    b.alias, b.na = [piece], 1
    return b


def pieces_past(f, piece_map):
    """A piece number past every piece glyph of FACE once renumbered by @p piece_map."""
    cps = jamoset.renumber_glyphs(dict.fromkeys(f.glyphs, 0), piece_map)
    return max(cp - jamoset.PIECE_BASE for cp in cps if jamoset.PIECE_BASE <= cp < jamoset.PIECE_BASE + 0x10000) + 1


def bad_jset(f, t, kind):
    """(block bytes, piece map) of FACE's tables @p t broken the way @p kind says."""
    pk = jamoset.pack(t)
    b = jamoset.decode_jset2(pk.block)
    if kind in BAD_KINDS_STD + BAD_KINDS_BIG:
        b = widened2(b, **{kind[:2]: int(kind[2:])})
    elif kind == "length":
        return pk.block + b"\0", pk.piece_map
    elif kind == "leadclass":
        b.lead_class[18] = b.lc
    elif kind == "finset":
        b = widened2(b, nf=3)
        used = set(b.tail_class[1:])
        i = next(i for i in range(len(b.fin_set)) if i % b.tc in used)
        b.fin_set[i] = 3
    elif kind == "initset":
        if b.ni & (b.ni - 1) == 0:
            raise SystemExit("svf_synth: initset needs an NI that is not a power of two")
        b.init_set[0] = b.ni
    elif kind == "missing_piece":
        b.rows["f"][-1][0] = pieces_past(f, pk.piece_map)
    elif kind == "magic":
        return b"JSEX" + pk.block[4:], pk.piece_map
    elif kind in ("version", "version4"):
        return pk.block[:4] + struct.pack("<H", 1 if kind == "version" else 4) + pk.block[6:], pk.piece_map
    elif kind == "short":
        return pk.block[:11], pk.piece_map
    elif kind == "na_over":
        slots = b.ni * 19 + b.nm * 21 + b.nf * 27
        b.na, b.alias = slots + 1, [0] * (slots + 1)
    elif kind == "reserved":
        b.reserved = 1
    elif kind == "pad_bits":
        b.rows["i"][0][2] |= 1 << 19
    elif kind in ("alias_no_presence", "abase_over", "alias_blank", "missing_alias_piece"):
        alias_edit(b)
        if kind == "alias_no_presence":
            row = b.rows["m"][0]
            row[2] &= ~1
            row[3] |= 1
        elif kind == "abase_over":
            b.rows["i"][0][1] = 1
        elif kind == "alias_blank":
            b.alias[0] = 0xFFFF
        else:
            b.alias[0] = pieces_past(f, pk.piece_map)
    elif kind == "base_wrap":
        b.rows["i"][0][0] = 0xFFF0
    elif kind == "compat_set_over":
        b.compat[30] = b.nm
    elif kind == "compat_slot_blank":
        b.rows["i"][-1][2] &= ~(1 << 18)
        b.compat[29] = b.ni - 1
    elif kind == "compat_bits56":
        b.compat[0] |= 0x20
    elif kind.startswith("compat_") and kind.endswith("_bit7"):
        k = {"vowel": 30, "tt": 7, "pp": 18, "jj": 24, "cluster": 2}[kind[7:-5]]
        b.compat[k] = 0x80
    else:
        raise ValueError(kind)
    return jamoset.encode_jset2(b), pk.piece_map


def bad_jset_v1(f, t, kind):
    """(version 1 block bytes, None) of FACE's tables @p t broken the way @p kind (BAD_KINDS_V1) says: c592140's kinds."""
    if kind in BAD_KINDS_STD + BAD_KINDS_BIG:
        return pack_v1_raw(widened(t, **{kind[:2]: int(kind[2:])})), None   # over the standard row (BIG kinds: the BIG row) on purpose
    if kind == "length":
        return jamoset.pack_v1(t) + b"\0", None
    if kind == "leadclass":
        t.lead_class[18] = t.lc
    elif kind == "finset":
        used = set(t.tail_class[1:])
        i = next(i for i in range(len(t.fin_set)) if i % t.tc in used)
        t.fin_set[i] = t.nf
    elif kind == "missing_piece":
        have = {cp - jamoset.PIECE_BASE for cp in f.glyphs if cp >= jamoset.PIECE_BASE}
        t.compat[50] = max(have) + 1
    elif kind == "magic":
        return b"JSEX" + jamoset.pack_v1(t)[4:], None
    elif kind == "version":
        return jamoset.pack_v1(t)[:4] + struct.pack("<H", 2) + jamoset.pack_v1(t)[6:], None
    elif kind == "short":
        return jamoset.pack_v1(t)[:11], None
    else:
        raise ValueError(kind)
    return jamoset.pack_v1(t), None


def pack_v1_raw(t):
    """The version 1 block of the Tables @p t with no count check (jamoset.pack_v1 minus _check_counts): a BIG kind."""
    out = bytearray(b"JSET" + struct.pack("<HBBBBBB", 1, t.lc, t.tc, t.ni, t.nm, t.nf, t.advance))
    out += bytes(t.lead_class) + bytes(t.tail_class)
    out += bytes(t.init_set) + bytes(t.med_set) + bytes(t.fin_set)
    for lst in (t.init_piece, t.med_piece, t.fin_piece, t.compat):
        out += struct.pack("<%dH" % len(lst), *lst)
    return bytes(out)


def packed(t, version):
    """(block, piece map) of the tables @p t in JSET @p version: 1 pack_v1 (no renumbering, map None), 2 jamoset.pack."""
    if version == 1:
        return jamoset.pack_v1(t), None
    pk = jamoset.pack(t)
    return pk.block, pk.piece_map


def variant_jset(t, kind):
    """(block bytes, piece map) of the valid --jset-variant @p kind of FACE's tables @p t."""
    if kind == "limits":
        pk = jamoset.pack(widened(t, 12, 12, 32, 24, 16))
        return pk.block, pk.piece_map
    if kind == "w0":
        w = jamoset.Tables(1, 1, 1, 1, 1, t.advance)
        w.init_piece, w.med_piece, w.fin_piece = t.init_piece[:19], t.med_piece[:21], t.fin_piece[:27]
        lists = {"i": w.init_piece, "m": w.med_piece, "f": w.fin_piece}
        for k, (key, idx) in enumerate(jamoset.COMPAT_HOME):
            if t.compat[k] != jamoset.BLANK:
                w.compat[k] = lists[key][idx - 1 if key == "f" else idx]
        pk = jamoset.pack(w)
        return pk.block, pk.piece_map
    pk = jamoset.pack(t)
    b = jamoset.decode_jset2(pk.block)
    if kind == "alias":
        alias_edit(b)
    elif kind == "bit7":
        if not b.rows["f"][0][2] & 1:
            raise SystemExit("svf_synth: bit7 needs final set 0 to draw ㄱ")
        b.compat[0] = 0x80
    elif kind == "overlap":
        ri = b.rows["i"]
        if len(ri) < 2:
            raise SystemExit("svf_synth: overlap needs two initial sets")
        ri[0][0], ri[1][0] = ri[1][0], ri[0][0]
    else:
        raise ValueError(kind)
    return jamoset.encode_jset2(b), pk.piece_map


def big_tables(t):
    """The BIG limit tables: 19 x 28 classes, 128/128/64 sets, every class and set used and every slot its own piece
    (initial 1.., medial 3000.., final 6000..); the compat entries as the first set of each kind draws them, except four
    held only by high sets (below)."""
    lc, tc, ni, nm, nf = jamoset.JSET_LIMITS["big"]
    out = jamoset.Tables(lc, tc, ni, nm, nf, t.advance)
    out.lead_class = [L % lc for L in range(19)]
    out.tail_class = [0] + [1 + (T - 1) % (tc - 1) for T in range(1, 28)]
    n = lc * 21 * tc
    out.init_set, out.med_set, out.fin_set = [c % ni for c in range(n)], [c % nm for c in range(n)], [c % nf for c in range(n)]
    out.init_piece = [1 + i for i in range(ni * 19)]
    out.med_piece = [3000 + i for i in range(nm * 21)]
    out.fin_piece = [6000 + i for i in range(nf * 27)]
    lists = {"i": out.init_piece, "m": out.med_piece, "f": out.fin_piece}
    for k, (key, idx) in enumerate(jamoset.COMPAT_HOME):
        if t.compat[k] != jamoset.BLANK:
            out.compat[k] = lists[key][idx - 1 if key == "f" else idx]
    # Compat jamo held only by sets past the narrow range, so a reader that masks the compat set to 5 bits (or tests the
    # narrow bits 5-6) draws the wrong piece: ㄴ from initial set 64 (byte 0x40), ㄳ from final set 63 (0x3F), ㄱ from final
    # set 63 in the bit 7 form (0xBF), ㅏ from medial set 100 (0x64).
    for k, key, s, slot in ((3, "i", 64, 2), (2, "f", 63, 2), (0, "f", 63, 0), (30, "m", 100, 0)):
        lst = lists[key]
        out.compat[k] = lst[s * jamoset._JSET_SLOTS[key] + slot]
    return out


def variant_big(f, t, kind, version):
    """(face, block bytes, piece map) of the valid BIG --jset-variant @p kind (BIG_VARIANTS) in JSET @p version: the BIG
    tables (big_tables) with a glyph for every piece (FACE's first piece glyph, made distinct); limits_big_alias (version
    2) has every slot an alias (NA = every slot)."""
    bt = big_tables(t)
    if kind == "limits_big_alias" and version == 1:
        raise SystemExit("svf_synth: limits_big_alias is a version 2 variant (version 1 has no aliases)")
    tmpl = next(cp for cp in sorted(f.glyphs) if cp >= jamoset.PIECE_BASE)
    keep = [cp for cp in f.glyphs if cp < jamoset.PIECE_BASE or cp >= jamoset.PIECE_BASE + 0x10000]
    g2 = copy.copy(f)
    g2.glyphs = {cp: f.glyphs[cp] for cp in keep}
    g2.metrics = {cp: f.metrics[cp] for cp in keep}
    g2.dy = {}
    for n in sorted(set(bt.init_piece + bt.med_piece + bt.fin_piece + bt.compat) - {jamoset.BLANK}):
        g2.glyphs[jamoset.PIECE_BASE + n] = _distinct(f.glyphs[tmpl], n)
        g2.metrics[jamoset.PIECE_BASE + n] = f.metrics[tmpl]
    if version == 1:
        return g2, jamoset.pack_v1(bt, big=True), None
    pk = jamoset.pack(bt, big=True)
    if kind == "limits_big":
        return g2, pk.block, pk.piece_map
    b = jamoset.decode_jset2(pk.block)
    alias = []
    for key in "imf":
        for row in b.rows[key]:
            base, _, pres, _ = row
            slots = [j for j in range(pres.bit_length()) if pres >> j & 1]
            row[1], row[3] = len(alias), pres
            alias += [base + k for k in range(len(slots))]
            row[0] = 0
    b.alias, b.na = alias, len(alias)
    return g2, jamoset.encode_jset2(b), pk.piece_map


def _distinct(cell, v):
    """@p cell with its first two bytes xor-ed by @p v (1..65535): a different, valid cell."""
    g = bytearray(cell)
    g[0] ^= v & 255
    g[1] ^= v >> 8
    return bytes(g)


def _jmap_parts(t, glyphs, kind):
    """(Jmap, block, {code point: cell}) of the valid --jmap-variant @p kind of FACE's tables @p t and glyph dict."""
    syl = range(0, 11172, JMAP_STRIDE)
    adv = JMAP_ADVANCE
    pad = (0, 0, 0)
    fb_version = 0
    big = kind in ("hybrid_big1", "hybrid_big2")
    if big:             # the limits_big tables and a glyph for each of their pieces (as variant_big)
        t = big_tables(t)
        tmpl = glyphs[next(cp for cp in sorted(glyphs) if cp >= jamoset.PIECE_BASE)]
        glyphs = {cp: c for cp, c in glyphs.items() if cp < jamoset.PIECE_BASE or cp >= jamoset.PIECE_BASE + 0x10000}
        for n in sorted(set(t.init_piece + t.med_piece + t.fin_piece + t.compat) - {jamoset.BLANK}):
            glyphs[jamoset.PIECE_BASE + n] = _distinct(tmpl, n)
    if kind in ("dense3", "dense4", "dhybrid1", "dhybrid2", "sparse_full"):
        syl = range(11172)
    if kind in ("dhybrid1", "dhybrid2"):
        fb_version = int(kind[-1])
    if kind in ("sparse4", "dense4", "dhybrid2"):
        pad = (300, 300, 300)
    elif kind in ("hybrid1", "hybrid2"):
        syl = range(0, 11172, 700)[:16]
        fb_version = int(kind[-1])
    elif big:
        syl = range(0, 11172, 700)[:16]
        fb_version = int(kind[-1])
    elif kind == "adv0fb":
        syl = range(0, 11172, 700)[:16]
        fb_version = 1
        adv = 0
    elif kind == "adv0":
        adv = 0
    elif kind == "pi2047":
        base = next(g for k, g in sorted(glyphs.items()) if k >= jamoset.PIECE_BASE)
        entries = {s: (1 + s % 2047, 1, 1 if s % 28 else 0) for s in range(0, 11172, 3)}
        jm = jamoset.Jmap(adv, 2047, 1, 1, entries)
        planes = {jamoset.PIECE_BASE + n: _distinct(base, n + 1) for n in range(2049)}
        return jm, jamoset.pack_jmap(jm), planes
    elif kind not in ("sparse3", "dense3", "blanks", "dhybrid1", "dhybrid2", "sparse_full"):
        raise ValueError(kind)
    jm, planes = jamoset.jmap_from_tables(t, syl, glyphs, pad)
    jm.advance = adv
    if kind in ("sparse4", "dense4", "dhybrid2"):          # entries naming padded pieces: indices 256.. in each plane (b0's high bits)
        for k, s in enumerate(sorted(jm.entries)[:60]):
            jm.entries[s] = (256 + k, 256 + k, 256 + k if s % 28 else 0)
    if kind == "hybrid1":
        jm.block_compat[next(k for k, c in enumerate(t.compat) if c != jamoset.BLANK)] = jamoset.BLANK
    if kind == "blanks":
        for s in sorted(jm.entries)[:400]:
            i, m, f = jm.entries[s]
            if s % 7 == 0:
                m = 0
            elif s % 28 and s % 3 == 0:
                f = 0
            jm.entries[s] = (i, m, f)
    fallback = None
    if fb_version:
        total = jm.pi + jm.pm + jm.pf
        shifted = jamoset.shift_pieces(t, total)
        shifted.advance = adv
        fallback = jamoset.pack_fallback(shifted, fb_version, big=big)
        for cp, cell in glyphs.items():
            if jamoset.PIECE_BASE <= cp < jamoset.PIECE_BASE + 0x10000:
                planes[cp + total] = cell
    block = jamoset.pack_jmap(jm, fallback)
    if kind == "sparse_full":       # pack_jmap writes 11,172 entries dense: set the SPARSE flag by hand
        bitmap = b"\xff" * 1396 + b"\x0f"
        ranks = struct.pack("<44H", *(256 * b for b in range(44)))
        block = block[:6] + bytes((block[6] | 2,)) + block[7:118] + ranks + bitmap + b"\0" + block[118:]
        assert len(block) == jamoset.jmap_size(11172, False, True)
    return jm, block, planes


def variant_jmap(f, t, kind):
    """(block bytes, {code point: cell} of the piece glyphs) of the valid --jmap-variant @p kind of FACE's tables."""
    jm, block, planes = _jmap_parts(t, f.glyphs, kind)
    return block, planes


def _entry4(i, m, f):
    return bytes((i >> 8 | (m >> 8) << 3 | (f >> 8) << 6, i & 255, m & 255, f & 255))


def bad_jmap(f, t, kind):
    """(block bytes, piece glyphs or None, header JSET size or None) of FACE's tables @p t broken the way @p kind
    (JMAP_BAD_KINDS) says: a byte edit of a valid block of one variant (None glyphs: v2_as_v3 keeps FACE's own)."""
    if kind == "v2_as_v3":
        pk = jamoset.pack(t)
        return pk.block[:4] + struct.pack("<H", 3) + pk.block[6:], None, None
    base = {"jmap_pi2048_4b": "sparse4", "jmap_pf1024_4b": "sparse4", "jmap_entry_over_4b": "sparse4",
            "jmap_dense_ns": "dense3"}.get(kind, "sparse3")
    if kind.startswith("jmap_fallback"):
        base = "hybrid1"
    block, planes = variant_jmap(f, t, base)
    jm = jamoset.unpack_jmap(block)
    d = bytearray(block)
    u16 = lambda at, v: struct.pack_into("<H", d, at, v)
    ent = jamoset.JMAP_SPARSE_ENTRIES if d[6] & 2 else jamoset.JMAP_DENSE_ENTRIES
    fb = ent + len(jm.entries) * (4 if d[6] & 1 else 3)
    size = None
    four = bool(d[6] & 1)
    if kind in ("jmap_pi256_3b", "jmap_entry_over") and four:
        raise SystemExit(f"svf_synth: {kind} needs 3 byte entries and FACE's tables give a 4 byte JMAP (a plane over 255)")
    if kind in ("jmap_pi2048_4b", "jmap_pf1024_4b", "jmap_entry_over_4b") and not four:
        raise SystemExit(f"svf_synth: {kind} needs 4 byte entries")
    if kind == "jmap_short":
        d = d[:100]
    elif kind == "jmap_flags":
        d[6] |= 0x08
    elif kind == "jmap_pi256_3b":
        u16(10, 256)
    elif kind == "jmap_pi2048_4b":
        u16(10, 2048)
    elif kind == "jmap_pf1024_4b":
        u16(14, 1024)
    elif kind == "jmap_zero_pieces":
        u16(10, 0), u16(12, 0), u16(14, 0)
    elif kind == "jmap_ns0":
        u16(8, 0)
    elif kind == "jmap_dense_ns":
        u16(8, 11171)
    elif kind == "jmap_length":
        d += b"\0"
    elif kind == "jmap_fallback_short":
        d = d[:fb + 11]
    elif kind == "jmap_fallback_bad":
        d[fb:fb + 4] = b"JSEX"
    elif kind == "jmap_fallback_v3":
        u16(fb + 4, 3)
    elif kind == "jmap_fallback_adv":
        d[fb + 11] += 1
    elif kind == "jmap_compat_over":
        u16(jamoset.JMAP_COMPAT_OFF, jm.pi + jm.pm + jm.pf)
    elif kind == "jmap_pad":
        d[jamoset.JMAP_PAD_OFF] = 1
    elif kind == "jmap_bitmap_tail":
        d[jamoset.JMAP_PAD_OFF - 1] |= 0x10
    elif kind == "jmap_rank_wrong":
        u16(jamoset.JMAP_RANK_OFF + 2, struct.unpack_from("<H", d, jamoset.JMAP_RANK_OFF + 2)[0] + 1)
    elif kind == "jmap_ns_popcount":
        d[jamoset.JMAP_BITMAP_OFF + (11171 >> 3)] |= 1 << (11171 & 7)      # an absent syllable of the last 256
    elif kind == "jmap_entry_over":
        d[ent] = jm.pi + 1
    elif kind == "jmap_entry_over_4b":
        i, m, fi = jm.entries[min(jm.entries)]
        d[ent:ent + 4] = _entry4(i, jm.pm + 1, fi)
    elif kind == "jmap_missing_piece":
        planes = {cp: c for cp, c in planes.items() if cp != max(planes)}
    elif kind == "jmap_region_max":
        size = 0x10000
    else:
        raise ValueError(kind)
    return bytes(d), planes, size


def _list_source(f, t, kind):
    """(face shim, fallback block) of the LIST variant @p kind: FACE's tables re-encoded with advance JMAP_ADVANCE through
    pack_fallback in the source's own version (version 2 for list2, its pieces renumbered 5, 3, 9, ... non-canonically), numbers kept, so
    the LIST advance (the fallback's byte 11, PL-9) is non-zero; the shim is FACE with those bytes as its JSET and, for
    list_big, the limits_big pieces as its plane-15 glyphs."""
    t = copy.copy(t)
    t.advance = JMAP_ADVANCE
    glyphs = dict(f.glyphs)
    if kind == "list_big":
        t = big_tables(t)
        tmpl = glyphs[next(cp for cp in sorted(glyphs) if cp >= jamoset.PIECE_BASE)]
        glyphs = {cp: c for cp, c in glyphs.items() if cp < jamoset.PIECE_BASE or cp >= jamoset.PIECE_BASE + 0x10000}
        for n in sorted(set(t.init_piece + t.med_piece + t.fin_piece + t.compat) - {jamoset.BLANK}):
            glyphs[jamoset.PIECE_BASE + n] = _distinct(tmpl, n)
    version = struct.unpack_from("<H", f.jset, 4)[0]       # the source's own version, numbers kept
    if kind == "list2":
        version = 2
        seen = []
        for p in t.init_piece + t.med_piece + t.fin_piece + t.compat:
            if p != jamoset.BLANK and p not in seen:
                seen.append(p)
        order = [5, 3, 9] + [x for x in range(len(seen)) if x not in (5, 3, 9)]
        mapping = dict(zip(seen, order))
        t = jamoset.renumber(t, mapping)
        glyphs = jamoset.renumber_glyphs(glyphs, mapping)
    block = jamoset.pack_fallback(t, version, 0, big=jamoset.needs_big(t))
    assert block[11] == JMAP_ADVANCE
    src = copy.copy(f)
    src.glyphs, src.jset = glyphs, block
    return src, block


def _list_recombination(src, base, s, pool):
    """Three (two without a final) pool pieces of a syllable @p s whose composition differs from base's own."""
    cp = 0xAC00 + s
    own = jamoset.compose(src, base, cp)
    ini, med, fin = pool
    for n in range(4000):
        pcs = [ini[(s // 7 + n) % len(ini)], med[(s // 3 + 5 * n) % len(med)]]
        if s % 28:
            pcs.append(fin[(s + n) % len(fin)])
        probe = jamoset.Jmap(0, 0, 0, 0, {s: tuple(pcs + [jamoset.BLANK] * (3 - len(pcs)))}, list_mode=True)
        if jamoset.compose(src, probe, cp) != own:
            return pcs
    raise SystemExit(f"svf_synth: no recombination of FACE's pieces composes differently for syllable {s}")


def _list_parts(f, t, kind):
    """(Jmap, block, {code point: cell} of the plane-15 glyphs) of the valid --jmap-variant @p kind in LIST_VARIANTS."""
    src, fb_block = _list_source(f, t, kind)
    base = jamoset.unpack(fb_block)
    pool = tuple(sorted({p for p in lst if p != jamoset.BLANK}) for lst in (base.init_piece, base.med_piece,
                                                                           base.fin_piece))
    fallback = kind != "list_nofb" and kind != "list_max"
    keys = list(range(0, 11172, LIST_STRIDE))
    exc, compat = {}, {}
    if kind == "list_nofb":
        exc[5000] = _list_recombination(src, base, 5000, pool)
    elif kind == "list_max":
        for j, s in enumerate([j * 44 for j in range(254)] + [11171]):
            exc[s] = [pool[0][j % len(pool[0])], pool[1][3 * j % len(pool[1])], pool[2][5 * j % len(pool[2])]]
    else:
        for j, s in enumerate(keys):
            if j % 2 == 0:
                exc[s] = _distinct(jamoset.compose(src, base, 0xAC00 + s), j + 1)      # a whole cell
            else:
                exc[s] = _list_recombination(src, base, s, pool)
    if kind == "list_zero":
        assert jamoset.PIECE_BASE in src.glyphs
        exc[150] = [0]
    if kind == "list_blank":
        exc[150] = [jamoset.BLANK] * 3
        exc[450] = [pool[0][0], jamoset.BLANK, jamoset.BLANK]
    if kind == "list_compat":
        named = [k for k, c in enumerate(base.compat) if c != jamoset.BLANK]
        ka = named[0]
        kb = next(k for k in named if base.compat[k] != base.compat[ka])
        compat[ka] = base.compat[kb]
    jm, new = jamoset.jmap_list(src, exc, compat, fallback=fallback, advance=JMAP_ADVANCE)
    assert jm.advance == JMAP_ADVANCE
    planes = {cp: c for cp, c in src.glyphs.items() if jamoset.PIECE_BASE <= cp < jamoset.PIECE_BASE + 0x10000}
    planes.update(new)
    return jm, jamoset.pack_jmap(jm, jm.fallback_block), planes


def variant_list(f, t, kind):
    """(block bytes, {code point: cell} of the piece glyphs) of the valid --jmap-variant @p kind in LIST_VARIANTS."""
    jm, block, planes = _list_parts(f, t, kind)
    return block, planes


def bad_list(f, t, kind):
    """(block bytes, piece glyphs, header JSET size or None) of FACE's tables @p t broken the way @p kind
    (LIST_BAD_KINDS) says: a byte edit of the list1 block (list_nofb for jlist_short_nofb and jlist_length)."""
    block, planes = variant_list(f, t, "list_nofb" if kind in ("jlist_short_nofb", "jlist_length") else "list1")
    d = bytearray(block)
    u16 = lambda at, v: struct.pack_into("<H", d, at, v)
    ns = struct.unpack_from("<H", d, 8)[0]
    fb = jamoset.JMAP_LIST_ENTRIES + ns * jamoset.JMAP_LIST_ENTRY
    ent = lambda j: jamoset.JMAP_LIST_ENTRIES + j * jamoset.JMAP_LIST_ENTRY
    size = None
    if kind in ("jlist_short", "jlist_short_nofb"):
        d = d[:100]
    elif kind == "jlist_sparse":
        d[6] |= 0x02
    elif kind == "jlist_4b":
        d[6] |= 0x01
    elif kind == "jlist_flags":
        d[6] |= 0x10
    elif kind in ("jlist_planes_i", "jlist_planes_m", "jlist_planes_f"):
        u16({"i": 10, "m": 12, "f": 14}[kind[-1]], 1)
    elif kind == "jlist_ns0":
        u16(8, 0)
    elif kind == "jlist_ns256":
        u16(8, 256)
    elif kind == "jlist_length":
        d += b"\0"
    elif kind == "jlist_fallback_short":
        d = d[:fb + 11]
    elif kind == "jlist_fallback_bad":
        d[fb:fb + 4] = b"JSEX"
    elif kind == "jlist_fallback_v3":
        u16(fb + 4, 3)
    elif kind == "jlist_fallback_adv":
        d[fb + 11] += 1
    elif kind == "jlist_key_equal":
        u16(ent(1), struct.unpack_from("<H", d, ent(0))[0])
    elif kind == "jlist_key_desc":
        k0, k1 = struct.unpack_from("<H", d, ent(0))[0], struct.unpack_from("<H", d, ent(1))[0]
        u16(ent(0), k1), u16(ent(1), k0)
    elif kind == "jlist_key_over":
        u16(ent(ns - 1), 11172)
    elif kind == "jlist_region_max":
        size = 0x10000
    elif kind == "jlist_field_noglyph":
        u16(ent(0) + 2, 1 + max(cp - jamoset.PIECE_BASE for cp in planes))
    elif kind == "jlist_field_fffe":
        u16(ent(0) + 2, 0xFFFE)
    elif kind == "jlist_compat_noglyph":
        u16(jamoset.JMAP_COMPAT_OFF, 1 + max(cp - jamoset.PIECE_BASE for cp in planes))
    else:
        raise ValueError(kind)
    return bytes(d), planes, size


def jmap_face(f, block, planes, profile="default", jset_size=None):
    """FACE's non-piece glyphs and metrics plus the piece glyphs @p planes ({code point: cell}) with @p block as the JSET
    block, written as v3 in @p profile; @p jset_size sets the header's JSET size (the file padded to hold that many bytes)."""
    base = jamoset.PIECE_BASE
    metric_of = {}
    for cp, g in sorted(f.glyphs.items()):
        if cp >= base:
            metric_of.setdefault(g, f.metrics[cp])
    default = next(iter(metric_of.values()), (f.cell_w, 0, f.cell_w))
    glyphs = [(cp, g) + tuple(f.metrics[cp]) for cp, g in sorted(f.glyphs.items()) if not base <= cp < base + 0x10000]
    glyphs += [(cp, g) + tuple(metric_of.get(g, default)) for cp, g in sorted(planes.items())]
    dy = {cp: v for cp, v in f.dy.items() if not base <= cp < base + 0x10000}
    data = jamoset.write_svfn(f.cell_w, f.cell_h, f.ascent, glyphs, block,
                              f.flags & ~(jamoset.FLAG_VARIABLE | jamoset.FLAG_JAMO), bpp=f.bpp, dy=dy, profile=profile)
    if jset_size is not None:
        data = bytearray(data)
        struct.pack_into("<I", data, 40, jset_size)
        need = struct.unpack_from("<I", data, 36)[0] + jset_size
        data += bytes(max(0, need - len(data)))
        data = bytes(data)
    return data


def bpp8(f):
    """FACE's glyphs as 8 bpp cells (f.bpp must be 1)."""
    if f.bpp != 1:
        raise SystemExit("svf_synth: --bpp8 needs a 1 bpp face")
    pitch = (f.cell_w + 7) // 8
    out = {}
    for cp, g in f.glyphs.items():
        cell = bytearray(f.cell_w * f.cell_h)
        for y in range(f.cell_h):
            for x in range(f.cell_w):
                k = cp * 7 + x * 13 + y * 29
                ink = g[y * pitch + x // 8] >> (7 - x % 8) & 1
                cell[y * f.cell_w + x] = 128 + k % 128 if ink else k % 19 if k % 19 < 16 else 0
        out[cp] = bytes(cell)
    f.glyphs, f.bpp = out, 8


def unused_finset(t, version=2):
    """(block, piece map): 3 final sets (copies of set 0) and finSet = 3 in every cell no syllable with a final reads
    (version 1: finSet = NF there, the sets as they are)."""
    used = set(t.tail_class[1:])
    cells = [i for i in range(len(t.fin_set)) if i % t.tc not in used]
    if not cells:
        raise SystemExit("svf_synth: every tail class is used by a tail 1..27: no unread finSet cell")
    if version == 1:
        for i in cells:
            t.fin_set[i] = t.nf
        return jamoset.pack_v1(t), None
    pk = jamoset.pack(t)
    b = widened2(jamoset.decode_jset2(pk.block), nf=3)
    for i in cells:
        b.fin_set[i] = 3
    return jamoset.encode_jset2(b), pk.piece_map


MARKS_W, MARKS_H, MARKS_ASCENT = 12, 16, 13
# cp: (advance, bearing x, ink width, rows of '#' ink, top row): the drawing starts at column 0 of the cell.
MARKS_GLYPHS = {
    0x41: (10, 1, 8, (" ..##....", " .#..#...", " .#..#...", " #....#..", " ######..", " #....#..", " #....#..",
                      " #....#..", " #....#..", " #....#.."), 3),
    0x65: (9, 1, 6, (" .####.", " #....#", " ######", " #.....", " #.....", " #....#", " .####."), 6),
    0xFFFD: (10, 1, 8, (" ########", " #......#", " #.####.#", " #......#", " #.####.#", " #......#", " ########"), 4),
    0x301: (0, -6, 3, ("..#", ".#.", "#.."), 0),         # acute: columns 0..2, the pen at column 6
    0x300: (0, -5, 3, (".#..", "..#.", "...#"), 2),      # grave: columns 1..3, the pen at column 5
}


def marks_face(profile="default"):
    """The --marks face (see the module docstring)."""
    pitch = (MARKS_W + 7) // 8
    glyphs = []
    for cp, (adv, bx, iw, rows, top) in sorted(MARKS_GLYPHS.items()):
        cell = bytearray(pitch * MARKS_H)
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch == "#":
                    cell[(top + r) * pitch + c // 8] |= 0x80 >> (c % 8)
        glyphs.append((cp, bytes(cell), adv, bx, iw))
    data = bytearray(jamoset.write_svfn(MARKS_W, MARKS_H, MARKS_ASCENT, glyphs, b"", jamoset.FLAG_MARKS_AT_ORIGIN,
                                        profile=profile))
    struct.pack_into("<H", data, 6, jamoset.FLAG_VARIABLE | jamoset.FLAG_MARKS_AT_ORIGIN)   # no JSET block
    return bytes(data)


def _u32(data, at):
    return struct.unpack_from("<I", data, at)[0]


def layout_bad(data, kind):
    """The v3 face @p data (default-profile layout: u32 offsets) broken the way LAYOUT_BAD's @p kind says."""
    f = jamoset.parse_svfn(data)
    if f.version != 3:
        raise SystemExit("svf_synth: --layout-bad needs a v3 face")
    if kind == "record_3_bytes":                  # byte-tight and u32, so a record can be 3 bytes long
        data = jamoset.relayout(data, "0,0,0,32")
        f = jamoset.parse_svfn(data)
    d = bytearray(data)
    rec, row, tab, off32 = f.layout
    count, cw, ch = f.count, f.cell_w, f.cell_h
    pitch = (cw * f.bpp + 7) // 8
    data_off, data_size, tab_off = _u32(d, 24), _u32(d, 28), _u32(d, 44)
    if not off32 and kind in ("entry_unaligned", "offsets_decrease", "offsets_overshoot", "last_not_size",
                              "box_x", "box_y", "rows_past", "record_3_bytes"):
        raise SystemExit(f"svf_synth: {kind} needs u32 offsets: use a `default` profile face")
    entries = lambda: list(struct.unpack_from("<%dI" % (count + 1), d, tab_off))
    put = lambda es: struct.pack_into("<%dI" % (count + 1), d, tab_off, *es)
    if kind == "rec7":
        d[9] = d[9] & ~7 | 7
    elif kind == "row_gt_rec":
        if rec == 6:
            raise SystemExit("svf_synth: row_gt_rec needs REC below 6")
        d[9] = rec | (rec + 1) << 3
    elif kind == "reserved9":
        d[9] |= 0x40
    elif kind == "reserved10":
        d[10] |= 0x10
    elif kind == "table_unaligned":
        struct.pack_into("<I", d, 32, _u32(d, 32) + 1)
        d += bytes(8)
    elif kind == "data_unaligned":
        struct.pack_into("<I", d, 24, data_off + 1)
        d += bytes(8)
    elif kind == "size_unaligned":
        struct.pack_into("<I", d, 28, data_size + 1)
        d += bytes(8)
    elif kind == "entry_unaligned":
        es = entries()
        es[BAD_GLYPH] += 1
        put(es)
    elif kind == "offsets_decrease":
        es = entries()
        es[BAD_GLYPH], es[BAD_GLYPH + 1] = es[BAD_GLYPH + 1], es[BAD_GLYPH]
        put(es)
    elif kind == "offsets_overshoot":
        es = entries()
        es[BAD_GLYPH] = data_size + (1 << rec)       # past the data, and larger than the entries after it
        put(es)
    elif kind == "last_not_size":
        es = entries()
        es[-1] = data_size + (1 << rec)
        put(es)
    elif kind == "u16_past_data":
        d[10] &= ~8
        big = (65535 << rec) + (1 << rec)
        struct.pack_into("<I", d, 28, big)
        d += bytes(big)                               # the data now ends inside the file; only the entries are wrong
    elif kind in ("box_x", "box_y", "rows_past", "record_3_bytes"):
        es = entries()
        at = data_off + es[BAD_GLYPH]
        n = es[BAD_GLYPH + 1] - es[BAD_GLYPH]
        if kind == "box_x":
            d[at] = pitch                             # x0 = pitch: x0 + wb > pitch even for a blank record
            d[at + 2] = max(d[at + 2], 1)
        elif kind == "box_y":
            d[at + 1] = ch
            d[at + 3] = max(d[at + 3], 1)
        elif kind == "rows_past":
            d[at + 1] = 0
            d[at + 2] = pitch
            d[at + 3] = ch                            # a full cell of rows in a record that cannot hold it
            if 4 + ch * pitch <= n:
                raise SystemExit("svf_synth: rows_past: glyph %d's record is big enough" % BAD_GLYPH)
        else:
            cut = n - 3                               # glyph 5's record becomes 3 bytes
            es = es[:BAD_GLYPH + 1] + [e - cut for e in es[BAD_GLYPH + 1:]]
            del d[at + 3:at + n]
            struct.pack_into("<I", d, 28, data_size - cut)
            put(es)
    elif kind == "jset_size":
        struct.pack_into("<I", d, 40, _u32(d, 40) + 1)
    elif kind == "jset_zero":
        struct.pack_into("<I", d, 40, 0)
    else:
        raise ValueError(kind)
    return bytes(d)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    what = ap.add_mutually_exclusive_group(required=True)
    kinds = BAD_KINDS_STD + BAD_KINDS + tuple(k for k in BAD_KINDS_V1 if k not in BAD_KINDS_STD + BAD_KINDS)
    what.add_argument("--jset-bad", choices=kinds, metavar="KIND",
                      help="version 2: " + ", ".join(BAD_KINDS_STD + BAD_KINDS) + "; version 1: " + ", ".join(BAD_KINDS_V1 + BAD_KINDS_BIG))
    what.add_argument("--jmap-variant", choices=JMAP_VARIANTS + LIST_VARIANTS, metavar="V",
                      help="one of: " + ", ".join(JMAP_VARIANTS + LIST_VARIANTS))
    what.add_argument("--jmap-bad", choices=JMAP_BAD_KINDS + LIST_BAD_KINDS, metavar="KIND",
                      help="one of: " + ", ".join(JMAP_BAD_KINDS + LIST_BAD_KINDS))
    what.add_argument("--reencode", action="store_true")
    what.add_argument("--jset-variant", choices=VARIANTS, metavar="V", help="one of: " + ", ".join(VARIANTS))
    what.add_argument("--jset-unused-finset", action="store_true")
    what.add_argument("--jset-cut", type=int, metavar="N")
    what.add_argument("--bpp8", action="store_true")
    what.add_argument("--marks", action="store_true")
    what.add_argument("--layout-bad", choices=sorted(LAYOUT_BAD), metavar="KIND",
                      help="one of: " + ", ".join(LAYOUT_BAD))
    prof = ap.add_mutually_exclusive_group()
    prof.add_argument("--profile", help="write the face in this profile (mcu-strict, default, dos, wasm, full, simd16; "
                      "default: default)")
    prof.add_argument("--units", metavar="R,W,T,O", help="write the face in these log2 units and offset width 16 or 32")
    ap.add_argument("--box", choices=jamoset.BOXES, default=None, help="ink box policy (default: the profile's)")
    ap.add_argument("--from", dest="src", help="a valid jamo set face to start from (every kind but --marks)")
    ap.add_argument("--jset-version", type=int, choices=(1, 2), default=2,
                    help="the JSET block version written (default 2)")
    ap.add_argument("out", help="the face to write")
    args = ap.parse_args(argv)
    try:
        profile = jamoset.profile_of(args.units or args.profile or "default", args.box)
    except ValueError as e:
        ap.error(str(e))
    if args.layout_bad and (args.units or args.profile or args.box):
        ap.error("--layout-bad reads FACE as it is: no --profile, --units or --box")
    if args.marks:
        with open(args.out, "wb") as fh:
            fh.write(marks_face(profile))
        return 0
    if not args.src:
        ap.error("--from is required")
    if args.layout_bad:
        with open(args.src, "rb") as fh:
            out = layout_bad(fh.read(), args.layout_bad)
        with open(args.out, "wb") as fh:
            fh.write(out)
        return 0
    f, t = load(args.src)
    if args.jmap_variant or args.jmap_bad:
        if isinstance(t, jamoset.Jmap):
            raise SystemExit("svf_synth: --jmap-* needs a face with JSET tables (version 1 or 2), not a JMAP or LIST face")
        size = None
        if args.jmap_variant in LIST_VARIANTS:
            block, planes = variant_list(f, t, args.jmap_variant)
        elif args.jmap_variant:
            block, planes = variant_jmap(f, t, args.jmap_variant)
        elif args.jmap_bad in LIST_BAD_KINDS:
            block, planes, size = bad_list(f, t, args.jmap_bad)
        else:
            block, planes, size = bad_jmap(f, t, args.jmap_bad)
        with open(args.out, "wb") as fh:
            if planes is None:           # v2_as_v3: FACE's own glyphs, its pieces renumbered as for a version 2 block
                fh.write(rebuild(f, block, profile, jamoset.pack(t).piece_map))
            else:
                fh.write(jmap_face(f, block, planes, profile, size))
        return 0
    v = args.jset_version
    if args.jset_bad:
        if args.jset_bad not in ((BAD_KINDS_V1 + BAD_KINDS_BIG) if v == 1 else (BAD_KINDS + BAD_KINDS_STD)):
            ap.error(f"--jset-bad {args.jset_bad} is not a version {v} kind")
        jset, pmap = bad_jset_v1(f, t, args.jset_bad) if v == 1 else bad_jset(f, t, args.jset_bad)
    elif args.jset_variant:
        if args.jset_variant in BIG_VARIANTS:
            f, jset, pmap = variant_big(f, t, args.jset_variant, v)
        elif v == 1:
            ap.error("--jset-variant writes version 2 blocks only (but the limits_big variant)")
        else:
            jset, pmap = variant_jset(t, args.jset_variant)
    elif args.jset_unused_finset:
        jset, pmap = unused_finset(t, v)
    elif args.jset_cut is not None:
        jset, pmap = packed(t, v)
        jset = jset[:args.jset_cut]
    elif args.reencode:
        if not (args.units or args.profile or args.box):
            profile = jamoset.face_profile(f)
        jset, pmap = packed(t, v)
    else:
        bpp8(f)
        jset, pmap = packed(t, v)
    with open(args.out, "wb") as fh:
        fh.write(rebuild(f, jset, profile, pmap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
