#!/usr/bin/env python3
"""mkfont.py 의 기준선 규칙 시험.

  python3 tools/test_mkfont.py
"""

import os
import pathlib
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jamoset  # noqa: E402
import mkfont  # noqa: E402

APPLE_GOTHIC = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
HERE_DIR = os.path.dirname(os.path.abspath(__file__))



class AscentTest(unittest.TestCase):
    def test_face_that_fits_keeps_its_own_ascent(self):
        self.assertEqual(mkfont.choose_ascent_from(12, 4, -12, 3, 16, latin=True), 12)
        self.assertEqual(mkfont.choose_ascent_from(12, 4, -12, 3, 16, latin=False), 12)

    def test_ink_that_fits_is_centred(self):
        # 줄은 셀보다 크지만 잉크는 들어간다: 가운데 놓는다.
        self.assertEqual(mkfont.choose_ascent_from(15, 6, -12, 2, 16, latin=True), 13)

    def test_latin_ink_taller_than_the_cell_keeps_the_capitals(self):
        # AppleGothic 16px: 줄 15+6, 'A' 위 -13, 'g' 아래 4 - 17줄이 16줄 셀에.
        # 대문자 위를 셀 맨 위에 두고 넘치는 한 줄은 내림자에서 잘린다.
        self.assertEqual(mkfont.choose_ascent_from(15, 6, -13, 4, 16, latin=True), 13)

    def test_cjk_ink_taller_than_the_cell_is_unchanged(self):
        # 한글 세트는 예전 규칙 그대로다 (글리프마다 셀 안으로 밀어 넣는다).
        self.assertEqual(mkfont.choose_ascent_from(15, 6, -13, 4, 16, latin=False), 10)


@unittest.skipUnless(os.path.exists(APPLE_GOTHIC), "AppleGothic.ttf not installed")
class AppleGothicLatinTest(unittest.TestCase):
    """C6 G2: ',' '.' 'r' 'l' sat on different baselines in a --latin bake."""

    def test_one_baseline_for_every_letter(self):
        from PIL import ImageFont
        font = ImageFont.truetype(APPLE_GOTHIC, 16)
        ascent = mkfont.choose_ascent(font, 16, latin=True)
        bottoms = {}
        for ch in "Hlr,.xo":
            img, _, _ = mkfont.render(font, ch, 16, 16, ascent, 8, center=True)
            # 잉크가 기준선 위에서 끝나는 줄: 기준선이 같으면 모두 같다.
            box = img.point(lambda v: 255 if v >= 128 else 0).getbbox()
            bottoms[ch] = box[3]
        self.assertEqual(len({bottoms[c] for c in "Hlrxo"}), 1, bottoms)
        # 쉼표와 마침표는 기준선에 닿거나 그 아래로 내려간다.
        self.assertGreaterEqual(bottoms[","], bottoms["H"], bottoms)
        self.assertGreaterEqual(bottoms["."], bottoms["H"] - 1, bottoms)


class RangeTest(unittest.TestCase):
    """C28: --unicode 목록. 16진 범위와 이름 붙인 묶음."""

    def test_hex_ranges_in_order_without_duplicates(self):
        self.assertEqual(mkfont.parse_ranges("0041-0043,0020,0042"), [0x41, 0x42, 0x43, 0x20])

    def test_named_sets(self):
        hangul = mkfont.parse_ranges("hangul")
        self.assertEqual(len(hangul), 11172)
        self.assertEqual((hangul[0], hangul[-1]), (0xAC00, 0xD7A3))
        self.assertEqual(mkfont.parse_ranges("ascii"), list(range(0x20, 0x7F)))
        # KS X 1001 전체: 완성형 2350자, 한자 4888자, 기호와 낱자.
        ks = set(mkfont.parse_ranges("ksx1001"))
        self.assertIn(0xAC00, ks)
        self.assertIn(0x4E00, ks)       # 一
        self.assertIn(0x3131, ks)       # ㄱ
        self.assertNotIn(0xB620, ks)    # 똠: 11172 에는 있지만 2350 에는 없다
        self.assertEqual(len([c for c in ks if 0xAC00 <= c <= 0xD7A3]), 2350)
        self.assertEqual(len(mkfont.parse_ranges("ascii,hangul,ascii")), 95 + 11172)

    def test_blank_code_points_are_kept_only_when_the_face_has_them(self):
        # 공백은 잉크가 없어도 싣는다. 하지만 글꼴에 없어 .notdef 로 그려졌다면
        # 공백 자리에 네모를 구워 넣지 않는다 (C28 리뷰).
        self.assertTrue(mkfont.unicode_keep(0x20, 0, False))
        self.assertFalse(mkfont.unicode_keep(0x3000, 7, True))
        self.assertFalse(mkfont.unicode_keep(0xA0, 0, True))
        self.assertTrue(mkfont.unicode_keep(0xAC00, 7, False))
        self.assertFalse(mkfont.unicode_keep(0xAC00, 7, True))
        self.assertFalse(mkfont.unicode_keep(0xAC00, 0, False))

    def test_unknown_name_is_an_error(self):
        with self.assertRaises(ValueError):
            mkfont.parse_ranges("klingon")

    def test_ksx1001_hangul_is_the_2350_syllables_only(self):
        hg = mkfont.parse_ranges("ksx1001-hangul")
        self.assertEqual(len(hg), 2350)
        self.assertTrue(all(0xAC00 <= cp <= 0xD7A3 for cp in hg))
        self.assertEqual(set(hg), {cp for cp in mkfont.parse_ranges("ksx1001") if 0xAC00 <= cp <= 0xD7A3})

    def test_ksx1001_symbols_excludes_hangul_and_hanja(self):
        sym = mkfont.parse_ranges("ksx1001-symbols")
        self.assertFalse(any(0xAC00 <= cp <= 0xD7A3 for cp in sym))
        self.assertFalse(any(0x4E00 <= cp <= 0x9FFF for cp in sym))
        self.assertIn(0x3131, sym)   # ㄱ
        nohanja = set(mkfont.parse_ranges("ksx1001-nohanja"))
        hangul = set(mkfont.parse_ranges("ksx1001-hangul"))
        self.assertEqual(set(sym), nohanja - hangul)

    def test_cp949_hangul_is_all_11172_syllables(self):
        self.assertEqual(mkfont.parse_ranges("cp949-hangul"), mkfont.parse_ranges("hangul"))
        self.assertEqual(len(mkfont.parse_ranges("cp949-hangul")), 11172)


class CharsFromTest(unittest.TestCase):
    """--chars-from: TEXT.nnn (SCI 패치), sci-ko.str, .MAP, 그냥 UTF-8 텍스트."""

    def _write(self, tmpdir, name, data):
        path = os.path.join(tmpdir, name)
        mode = "wb" if isinstance(data, bytes) else "w"
        kwargs = {} if isinstance(data, bytes) else dict(encoding="utf-8")
        with open(path, mode, **kwargs) as f:
            f.write(data)
        return path

    def test_text_patch_is_nul_separated_utf8_after_2_byte_header(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "TEXT.000",
                                b"\x83\x00" + "안녕".encode("utf-8") + b"\x00" +
                                "하세요".encode("utf-8") + b"\x00")
            cps = mkfont.chars_from_text_patch(path)
            self.assertEqual(set(cps), {ord(c) for c in "안녕하세요"})

    def test_text_patch_honours_extra_header_byte(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            # header byte[1] = 3: header is 2 + 3 = 5 bytes total.
            path = self._write(d, "TEXT.001",
                                b"\x83\x03" + b"\x00\x00\x00" + "가".encode("utf-8") + b"\x00")
            cps = mkfont.chars_from_text_patch(path)
            self.assertEqual(cps, [ord("가")])

    def test_str_format_skips_comments_and_takes_the_text_field(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "sci-ko.str",
                                "# comment\n"
                                "0\t1\t안녕\n"
                                "\n"
                                "2\t3\t5\t\\n 이스케이프는 그대로 글자\n")
            cps = mkfont.chars_from_str(path)
            self.assertTrue({ord(c) for c in "안녕"} <= set(cps))
            self.assertIn(ord("이"), cps)

    def test_map_format_collects_missing_and_glyph_targets_not_ranges(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "test.map",
                                "[hires]\n"
                                "missing=u+25a1 ; box\n"
                                "[glyphs]\n"
                                "0x5e=u+2192\n"
                                "0x7e-0x7f=+10\n"
                                "0x60=keep\n")
            cps = mkfont.chars_from_map(path)
            self.assertEqual(sorted(cps), sorted([0x25A1, 0x2192]))

    def test_ini_comment_needs_leading_whitespace(self):
        # font_map.cpp 규칙: "single=my;font.fnt" 의 ; 는 주석이 아니다.
        self.assertEqual(mkfont._strip_ini_comment("scale=3  ; why").strip(), "scale=3")
        self.assertEqual(mkfont._strip_ini_comment("single=my;font.fnt").strip(), "single=my;font.fnt")
        self.assertEqual(mkfont._strip_ini_comment("; whole line"), "")
        self.assertEqual(mkfont._strip_ini_comment("# whole line"), "")

    def test_parse_code_value_matches_font_map_rules(self):
        self.assertEqual(mkfont._parse_code_value("u+25a1"), 0x25A1)
        self.assertEqual(mkfont._parse_code_value("0x25A1"), 0x25A1)
        self.assertEqual(mkfont._parse_code_value("9633"), 9633)
        self.assertIsNone(mkfont._parse_code_value("keep"))
        self.assertIsNone(mkfont._parse_code_value(""))

    def test_plain_text_file_is_read_as_utf8(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "plain.txt", "테스트 ABC")
            cps = mkfont.chars_from_text_patch  # not used; direct collect below
            found, counts = mkfont.collect_chars_from_files([path])
            self.assertTrue({ord(c) for c in "테스트"} <= set(found))
            self.assertEqual(len(counts), 1)

    def test_collect_classifies_each_kind_and_unions_them(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "TEXT.000", b"\x83\x00" + "가".encode("utf-8") + b"\x00")
            self._write(d, "sci-ko.str", "0\t1\t나\n")
            self._write(d, "x.map", "[hires]\nmissing=u+25a1\n")
            self._write(d, "notes.txt", "다")
            found, counts = mkfont.collect_chars_from_files(
                [os.path.join(d, n) for n in ("TEXT.000", "sci-ko.str", "x.map", "notes.txt")])
            self.assertEqual(len(counts), 4)
            self.assertTrue({ord("가"), ord("나"), ord("다"), 0x25A1} <= set(found))

    def test_glob_pattern_is_expanded(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self._write(d, "TEXT.000", b"\x83\x00" + "가".encode("utf-8") + b"\x00")
            self._write(d, "TEXT.001", b"\x83\x00" + "나".encode("utf-8") + b"\x00")
            found, counts = mkfont.collect_chars_from_files([os.path.join(d, "TEXT.*")])
            self.assertEqual(len(counts), 2)
            self.assertTrue({ord("가"), ord("나")} <= set(found))

    def test_missing_file_is_an_error(self):
        with self.assertRaises(SystemExit):
            mkfont.collect_chars_from_files(["/no/such/file/here"])

    def test_collect_drops_newlines_and_tabs_as_layout_not_glyphs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "TEXT.000",
                                b"\x83\x00" + "줄1\n줄2\t끝".encode("utf-8") + b"\x00")
            found, _ = mkfont.collect_chars_from_files([path])
            self.assertNotIn(0x0A, found)
            self.assertNotIn(0x09, found)
            self.assertTrue({ord(c) for c in "줄1"} <= set(found))

    def test_parse_ranges_file_token_matches_collect_chars_from_files(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "sci-ko.str", "0\t1\t라\n")
            cps = mkfont.parse_ranges(f"ascii,file:{path}")
            self.assertIn(ord("라"), cps)
            self.assertIn(0x41, cps)


def _make_trs(entries, utf8):
    """entries: [(original_bytes, translated_bytes)] -> SCVMTRS bundle with no rooms."""
    header_len = 8 + 2 + len(entries) * 10 + 1
    body = bytearray()
    if utf8:
        body += b"\xef\xbb\xbf"
    recs = []
    for orig, trans in entries:
        o1 = header_len + len(body)
        body += orig + b"\x00"
        o2 = header_len + len(body)
        body += trans + b"\x00"
        recs.append((o1, o2))
    out = bytearray(b"SCVMTRS ")
    out += struct.pack("<H", len(entries))
    for i, (o1, o2) in enumerate(recs):
        out += struct.pack("<HII", i, o1, o2)
    out.append(0)   # nroom = 0
    assert len(out) == header_len, (len(out), header_len)
    out += body
    return bytes(out)


class TrsCharsFromTest(unittest.TestCase):
    def _write(self, tmpdir, name, data):
        path = os.path.join(tmpdir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_utf8_bundle_with_bom_is_decoded_as_utf8(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            entries = [(b"Hello", "안녕".encode("utf-8"))]
            path = self._write(d, "korean.trs", _make_trs(entries, utf8=True))
            cps = mkfont.chars_from_trs(path)
            self.assertTrue({ord("안"), ord("녕")} <= set(cps))

    def test_bundle_without_bom_is_decoded_as_cp949(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            entries = [(b"Hello", "안녕".encode("cp949"))]
            path = self._write(d, "korean.trs", _make_trs(entries, utf8=False))
            cps = mkfont.chars_from_trs(path)
            self.assertTrue({ord("안"), ord("녕")} <= set(cps))

    def test_control_code_arguments_do_not_leak_as_characters(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            # FF 0A 00 99: an escape with 2 argument bytes, the embedded NUL included
            trans = "안녕".encode("utf-8") + b"\xff\x0a\x00\x99" + "하세요".encode("utf-8")
            entries = [(b"hi", trans)]
            path = self._write(d, "korean.trs", _make_trs(entries, utf8=True))
            cps = mkfont.chars_from_trs(path)
            self.assertEqual({ord(c) for c in "안녕하세요"}, {c for c in cps if c > 0x7F})
            self.assertNotIn(0x0A, cps)
            self.assertNotIn(0x99, cps)

    def test_control_codes_without_arguments_take_no_operand_bytes(self):
        import tempfile
        for code in (1, 2, 3, 8):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as d:
                trans = "안".encode("utf-8") + bytes([0xFF, code]) + "녕".encode("utf-8")
                path = self._write(d, "korean.trs", _make_trs([(b"hi", trans)], utf8=True))
                cps = mkfont.chars_from_trs(path)
                self.assertEqual({ord("안"), ord("녕")}, {c for c in cps if c > 0x7F})
                self.assertNotIn(code, cps)

    def test_control_code_without_arguments_at_string_end(self):
        import tempfile
        for code in (1, 2, 3, 8):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as d:
                trans = "안".encode("utf-8") + bytes([0xFF, code])
                path = self._write(d, "korean.trs", _make_trs([(b"hi", trans)], utf8=True))
                self.assertIn(ord("안"), mkfont.chars_from_trs(path))

    def test_string_without_terminator_is_a_clean_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            data = _make_trs([(b"hi", b"abc")], utf8=False)[:-1]
            path = self._write(d, "korean.trs", data)
            with self.assertRaises(SystemExit) as cm:
                mkfont.chars_from_trs(path)
            self.assertIn("korean.trs", str(cm.exception))
            self.assertIn("종료 NUL", str(cm.exception))

    def test_escape_running_past_end_of_file_is_a_clean_error(self):
        import tempfile
        cases = {
            "code byte missing": b"ab\xff",
            "operands missing": b"ab\xff\x0a",
        }
        for label, trans in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as d:
                data = _make_trs([(b"hi", trans)], utf8=False)
                if label == "code byte missing":
                    data = data[:-1]
                path = self._write(d, "korean.trs", data)
                with self.assertRaises(SystemExit) as cm:
                    mkfont.chars_from_trs(path)
                self.assertIn("korean.trs", str(cm.exception))
                self.assertIn("이스케이프", str(cm.exception))

    def test_original_and_translated_strings_are_both_collected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            entries = [("원본".encode("utf-8"), "번역".encode("utf-8"))]
            path = self._write(d, "korean.trs", _make_trs(entries, utf8=True))
            cps = mkfont.chars_from_trs(path)
            self.assertTrue({ord(c) for c in "원본번역"} <= set(cps))

    def test_shared_offsets_are_only_decoded_once_and_classify_dispatches_to_trs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            entries = [(b"same", "가".encode("utf-8")), (b"same", "가".encode("utf-8"))]
            path = self._write(d, "korean.trs", _make_trs(entries, utf8=True))
            found, counts = mkfont.collect_chars_from_files([path])
            self.assertIn(ord("가"), found)
            self.assertEqual(len(counts), 1)

    def test_bad_magic_is_an_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = self._write(d, "bad.trs", b"NOTATRS!!" + b"\x00" * 20)
            with self.assertRaises(SystemExit):
                mkfont.chars_from_trs(path)


class TwoBppTest(unittest.TestCase):
    """M2: --bpp 2. 0-255 커버리지를 4단계로, 네 픽셀을 한 바이트에 (왼쪽이 상위 비트 쌍)."""

    def test_quantize_is_round_to_nearest_level(self):
        self.assertEqual([mkfont.quantize2(v) for v in (0, 42, 43, 127, 128, 212, 213, 255)],
                         [0, 0, 1, 1, 2, 2, 3, 3])
        # 읽는 쪽은 단계 x 85: 어느 값도 43 넘게 틀어지지 않는다.
        self.assertLessEqual(max(abs(mkfont.quantize2(v) * 85 - v) for v in range(256)), 43)

    def test_pack_glyph_packs_four_pixels_a_byte_msb_first(self):
        from PIL import Image
        img = Image.new("L", (6, 2), 0)
        for x, v in enumerate((0, 85, 170, 255, 255, 170)):
            img.putpixel((x, 1), v)
        out = mkfont.pack_glyph(img, 6, 2, 2)
        # 6 px 는 12비트: 행마다 2바이트, 둘째 바이트의 아래 4비트는 채움.
        self.assertEqual(out, bytes([0x00, 0x00, 0x1B, 0xE0]))

    def test_cp949_is_every_code_it_decodes_and_ascii(self):
        cps = mkfont.parse_ranges("cp949")
        self.assertEqual(len(cps), len(set(cps)))
        self.assertEqual(cps[:95], list(range(0x20, 0x7F)))
        s = set(cps)
        self.assertEqual(len([c for c in s if 0xAC00 <= c <= 0xD7A3]), 11172)
        self.assertIn(0xB620, s)        # 똠: 2350 에 없는 음절도 cp949 에는 있다
        self.assertIn(0x4E00, s)
        self.assertLessEqual(set(mkfont.parse_ranges("ksx1001")), s)
        self.assertEqual(len(cps), 17143)


def _nanum_bold():
    for p in (os.environ.get("SCUMMVM_TEST_KO_BOLD_TTF", ""),
              os.path.expanduser("~/.local/sysroot/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
              "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"):
        if p and os.path.exists(p):
            return p
    return ""


NANUM_BOLD = _nanum_bold()


def read_svfn(data):
    """SVFN 을 jamoset.parse_svfn 으로 읽는다: {코드 포인트: (폭 표 네 바이트, [행마다 커버리지 0-255])}.
    버전 3 만. 픽셀은 TextCompose::expandCoverage 순서로 펼친다."""
    f = jamoset.parse_svfn(data)
    assert f.version == 3 and f.bpp in (1, 2, 8)
    bpp, cw, ch = f.bpp, f.cell_w, f.cell_h
    pitch = {1: (cw + 7) // 8, 2: (cw + 3) // 4, 8: cw}[bpp]

    def px(row, x):
        if bpp == 1:
            return 255 if row[x >> 3] & (0x80 >> (x & 7)) else 0
        if bpp == 2:
            return ((row[x >> 2] >> (6 - (x & 3) * 2)) & 3) * 85
        return row[x]

    out = {}
    for cp, g in f.glyphs.items():
        rows = [[px(g[y * pitch:(y + 1) * pitch], x) for x in range(cw)] for y in range(ch)]
        m = bytes((f.metrics[cp][0], f.metrics[cp][1] & 255, f.metrics[cp][2], 0)) if f.metrics_ok else b""
        out[cp] = (m, rows)
    return dict(bpp=bpp, cell=(cw, ch), pitch=pitch, glyphs=out)


@unittest.skipUnless(NANUM_BOLD, "NanumGothicBold.ttf not found (SCUMMVM_TEST_KO_BOLD_TTF)")
class TwoBppBakeTest(unittest.TestCase):
    """같은 TTF, 같은 크기를 8bpp 와 2bpp 로 구우면 같은 글자, 같은 폭, 픽셀마다
    커버리지 차 43 이하 (단계 양자화 오차)."""

    UNICODE = "ascii,AC00-AC40,B620,D7A3,4E00,3131,25A1"

    def bake(self, bpp):
        import subprocess
        import tempfile
        out = tempfile.NamedTemporaryFile(suffix=".fnt", delete=False).name
        try:
            subprocess.run([sys.executable, mkfont.__file__, NANUM_BOLD, out, "--size", "18",
                            "--bpp", str(bpp), "--unicode", self.UNICODE], check=True, capture_output=True)
            with open(out, "rb") as f:
                return read_svfn(f.read())
        finally:
            os.unlink(out)

    def test_2bpp_is_8bpp_within_one_half_level(self):
        f8, f2 = self.bake(8), self.bake(2)
        self.assertEqual(f2["bpp"], 2)
        self.assertEqual(f2["cell"], (18, 18))
        self.assertEqual(f2["pitch"], 5)
        self.assertEqual(sorted(f8["glyphs"]), sorted(f2["glyphs"]))
        worst = 0
        levels = set()
        for cp, (m8, rows8) in f8["glyphs"].items():
            m2, rows2 = f2["glyphs"][cp]
            self.assertEqual(m8[0], m2[0], hex(cp))     # 같은 advance
            for r8, r2 in zip(rows8, rows2):
                for a, b in zip(r8, r2):
                    worst = max(worst, abs(a - b))
                    levels.add(b)
        self.assertLessEqual(worst, 43)
        self.assertEqual(levels, {0, 85, 170, 255})
        print(f"\n  2bpp vs 8bpp, {len(f8['glyphs'])} glyphs at 18px: max per-pixel diff {worst}",
              file=sys.stderr)


@unittest.skipUnless(NANUM_BOLD, "NanumGothicBold.ttf not found (SCUMMVM_TEST_KO_BOLD_TTF)")
class MonoHintTest(unittest.TestCase):
    """--mono-hint: a 1 bpp bake with FreeType's monochrome renderer and the font's hinting, not cut at half coverage."""

    UNICODE = "ascii,AC00-AC40,B620,D7A3"

    def bake(self, *extra):
        import subprocess
        import tempfile
        out = tempfile.NamedTemporaryFile(suffix=".fnt", delete=False).name
        try:
            subprocess.run([sys.executable, mkfont.__file__, NANUM_BOLD, out, "--size", "17", "--cell", "18", "--width", "18",
                            "--bpp", "1", "--unicode", self.UNICODE, *extra], check=True, capture_output=True)
            with open(out, "rb") as f:
                return read_svfn(f.read())
        finally:
            os.unlink(out)

    def test_hinted_mono_differs_from_the_cut_antialiased_bake(self):
        plain, mono = self.bake(), self.bake("--mono-hint")
        self.assertEqual(sorted(plain["glyphs"]), sorted(mono["glyphs"]))
        diff = sum(1 for cp in plain["glyphs"] if plain["glyphs"][cp][1] != mono["glyphs"][cp][1])
        self.assertGreater(diff, len(plain["glyphs"]) // 4)
        for cp, (m, rows) in mono["glyphs"].items():
            self.assertTrue(any(any(r) for r in rows) or cp == 0x20, hex(cp))

    def test_mono_hint_needs_one_bpp(self):
        import subprocess
        r = subprocess.run([sys.executable, mkfont.__file__, NANUM_BOLD, os.devnull, "--size", "17", "--bpp", "2",
                            "--mono-hint", "--unicode", "ascii"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--mono-hint", r.stderr)


@unittest.skipUnless(NANUM_BOLD, "NanumGothicBold.ttf not found (SCUMMVM_TEST_KO_BOLD_TTF)")
class CharsFromLimitCliTest(unittest.TestCase):
    """--chars-from/--limit/--require/--fail-on-drop, mkfont.py 를 실제로 불러서."""

    def _str_file(self, d, text):
        import os as _os
        path = _os.path.join(d, "sci-ko.str")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"0\t1\t{text}\n")
        return path

    def run_mkfont(self, *extra, check=True):
        import subprocess
        return subprocess.run([sys.executable, mkfont.__file__] + list(extra),
                               capture_output=True, text=True)

    def test_chars_from_merges_with_unicode(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            src = self._str_file(d, "안녕")
            out = os.path.join(d, "out.fnt")
            r = self.run_mkfont(NANUM_BOLD, out, "--size", "18", "--bpp", "1",
                                 "--unicode", "ascii", "--chars-from", src)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(out, "rb") as fh:
                f = read_svfn(fh.read())
            self.assertIn(ord("안"), f["glyphs"])
            self.assertIn(ord("녕"), f["glyphs"])
            self.assertIn(0x41, f["glyphs"])   # ascii 'A' still there

    def test_limit_keeps_only_the_intersection_but_always_keeps_ascii_and_box(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            # 가 (0xAC00, 2350 안) 와 똠 (0xB620, 2350 밖: hangul 11172 에만 있음).
            src = self._str_file(d, "가똠")
            out = os.path.join(d, "out.fnt")
            r = self.run_mkfont(NANUM_BOLD, out, "--size", "18", "--bpp", "1",
                                 "--chars-from", src, "--limit", "ksx1001-nohanja")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("U+B620", r.stdout)   # dropped-list summary
            with open(out, "rb") as fh:
                f = read_svfn(fh.read())
            self.assertIn(ord("가"), f["glyphs"])
            self.assertNotIn(ord("똠"), f["glyphs"])
            self.assertIn(0x41, f["glyphs"])     # ASCII always kept
            self.assertIn(0x25A1, f["glyphs"])   # box always kept (Nanum has it)

    def test_fail_on_drop_is_a_nonzero_exit(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            src = self._str_file(d, "똠")   # outside ksx1001-nohanja
            out = os.path.join(d, "out.fnt")
            r = self.run_mkfont(NANUM_BOLD, out, "--size", "18", "--bpp", "1",
                                 "--chars-from", src, "--limit", "ksx1001-nohanja",
                                 "--fail-on-drop")
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse(os.path.exists(out))

    def test_require_fails_when_the_face_lacks_a_requested_code_point(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out.fnt")
            # U+3400 (CJK 확장 A) 는 NanumGothic-Bold 에 없다.
            r = self.run_mkfont(NANUM_BOLD, out, "--size", "18",
                                 "--bpp", "1", "--unicode", "ascii,3400", "--require")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("3400", r.stdout + r.stderr)
            self.assertFalse(os.path.exists(out))


def _galmuri(name):
    d = os.environ.get("SCUMMVM_TEST_PIXEL_FONT_DIR")
    if not d and os.environ.get("SCUMMVM_TEST_I18N_DATA"):
        d = os.path.join(os.environ["SCUMMVM_TEST_I18N_DATA"], "..", "fonts", "pixel", "galmuri")
    return os.path.join(d, name) if d else ""


GALMURI7 = _galmuri("Galmuri7.ttf")


@unittest.skipUnless(GALMURI7 and os.path.exists(GALMURI7), "Galmuri7.ttf not found (SCUMMVM_TEST_PIXEL_FONT_DIR)")
class UnicodeBakeTest(unittest.TestCase):
    """C28: --unicode 로 구운 SVFN 버전 3 는 11172자 전부를 싣는다."""

    def bake(self, *extra):
        import struct
        import subprocess
        import tempfile
        out = tempfile.NamedTemporaryFile(suffix=".fnt", delete=False).name
        try:
            subprocess.run([sys.executable, mkfont.__file__, GALMURI7, out, "--size", "8", "--cell", "9",
                            "--bpp", "1"] + list(extra), check=True, capture_output=True)
            data = pathlib.Path(out).read_bytes()
        finally:
            os.unlink(out)
        f = jamoset.parse_svfn(data)
        return dict(magic=data[:4], version=f.version, flags=f.flags, count=f.count, cell=(f.cell_w, f.cell_h),
                    glyphs=f.glyphs, layout=f.layout, data=data)

    def ink(self, f, cp):
        return sum(bin(b).count("1") for b in f["glyphs"][cp])

    def test_every_syllable_is_baked(self):
        f = self.bake("--unicode", "ascii,hangul")
        self.assertEqual(f["magic"], b"SVFN")
        self.assertEqual(f["version"], 3)
        self.assertEqual(f["cell"], (9, 9))
        for cp in (0xAC00, 0xAC01, 0xBDC1, 0xB620, 0xD7A3, 0x41):
            self.assertIn(cp, f["glyphs"])
            self.assertGreater(self.ink(f, cp), 0, hex(cp))
        self.assertEqual(len([c for c in f["glyphs"] if 0xAC00 <= c <= 0xD7A3]), 11172)
        self.assertIn(0x20, f["glyphs"])   # 공백은 잉크가 없어도 싣는다

    def test_code_points_the_face_lacks_are_left_out(self):
        # Galmuri7 에는 타이 문자가 없다: 빈 글리프를 실으면 대체 글꼴로
        # 넘어가지 못하므로 목록에서 뺀다.
        f = self.bake("--unicode", "0041,0E01")
        self.assertIn(0x41, f["glyphs"])
        self.assertNotIn(0x0E01, f["glyphs"])
        self.assertEqual(f["count"], 1)


class FitCellTest(unittest.TestCase):
    """--fit-cell: 글꼴 전체가 한 크기, 기준선 하나로 셀에 든다."""

    # 코드 포인트 -> (왼쪽, 위, 오른쪽, 아래), 기준선 기준
    BOXES = {1: (0, -10, 5, 2), 2: (0, -12, 14, 1), 3: (1, -3, 4, 0)}

    def test_every_ascent_that_fits_is_allowed_and_the_preferred_one_wins(self):
        # 위로 12줄, 아래로 2줄: ascent 12..14 가 16줄 셀에 든다.
        self.assertEqual(mkfont.fit_ascent(self.BOXES, 16, 13), (13, True))
        self.assertEqual(mkfont.fit_ascent(self.BOXES, 16, 20), (14, True))
        self.assertEqual(mkfont.fit_ascent(self.BOXES, 16, 3), (12, True))

    def test_no_ascent_fits_ink_taller_than_the_cell(self):
        ascent, ok = mkfont.fit_ascent(self.BOXES, 13, 12)
        self.assertFalse(ok)
        top, bottom, _ = mkfont.fit_counts(self.BOXES, 16, 13, ascent)
        self.assertEqual(len(set(top) | set(bottom)), 1)   # 가장 적게 넘치는 값

    def test_counts_rows_above_below_and_width(self):
        top, bottom, wide = mkfont.fit_counts(self.BOXES, 13, 16, 11)
        self.assertEqual(top, [2])
        self.assertEqual(bottom, [])
        self.assertEqual(wide, [2])
        top, bottom, wide = mkfont.fit_counts(self.BOXES, 16, 16, 15)
        self.assertEqual((top, bottom, wide), ([], [1], []))


NANUM_IN_TREE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ttf", "nanumgothic",
                             "NanumGothic-Bold.ttf")


@unittest.skipUnless(os.path.exists(NANUM_IN_TREE), "in-tree NanumGothic-Bold.ttf not found")
class FitCellBakeTest(unittest.TestCase):
    CHARS = [ord(c) for c in "가각한글뷁똠AQgjy$()W,"]

    def test_largest_size_whose_ink_fits_every_glyph(self):
        log = []
        size, ascent = mkfont.fit_cell(NANUM_IN_TREE, 18, self.CHARS, 16, 16, 2, log=log.append)
        _, boxes = mkfont.measure_boxes(NANUM_IN_TREE, size, self.CHARS, 2)
        self.assertEqual(len(boxes), len(self.CHARS))
        self.assertEqual(mkfont.fit_counts(boxes, 16, 16, ascent), ([], [], []))
        # One px larger does not fit at any single ascent.
        _, bigger = mkfont.measure_boxes(NANUM_IN_TREE, size + 1, self.CHARS, 2)
        self.assertFalse(mkfont.fit_ascent(bigger, 16, ascent)[1] and
                         not mkfont.fit_counts(bigger, 16, 16, mkfont.fit_ascent(bigger, 16, ascent)[0])[2])
        self.assertLess(size, 18)
        self.assertTrue(any("넘는 글자" in line for line in log))

    def test_baked_font_has_one_baseline_and_nothing_cropped(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "fit.svf")
            chars = os.path.join(d, "chars.txt")
            with open(chars, "w", encoding="utf-8") as f:
                f.write("".join(chr(c) for c in self.CHARS))
            r = subprocess.run([sys.executable, mkfont.__file__, NANUM_IN_TREE, out, "--size", "18",
                                "--cell", "16", "--fit-cell", "--ascent", "14", "--bpp", "2",
                                "--chars-from", chars], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            data = pathlib.Path(out).read_bytes()
        f = read_svfn(data)
        self.assertEqual(f["cell"], (16, 16))
        self.assertEqual(data[16], 14)          # header ascent
        size = int(r.stdout.split("크기 ")[1].split("px")[0])
        from PIL import ImageFont
        font = ImageFont.truetype(NANUM_IN_TREE, size)
        for cp in self.CHARS:
            _, rows = f["glyphs"][cp]
            ink_rows = [y for y, row in enumerate(rows) if any(row)]
            box, _ = mkfont.ink_box(font, chr(cp), 2)
            # The glyph as baked is the glyph as drawn: every row of ink,
            # on row ascent + its offset from the baseline.
            self.assertEqual((ink_rows[0], ink_rows[-1] + 1), (14 + box[1], 14 + box[3]), chr(cp))

    def test_clip_cell_keeps_one_baseline_and_cuts_what_leaves_the_cell(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "clip.svf")
            chars = os.path.join(d, "chars.txt")
            with open(chars, "w", encoding="utf-8") as f:
                f.write("".join(chr(c) for c in self.CHARS))
            r = subprocess.run([sys.executable, mkfont.__file__, NANUM_IN_TREE, out, "--size", "18",
                                "--cell", "16", "--clip-cell", "--ascent", "14", "--bpp", "2",
                                "--chars-from", chars], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("--clip-cell: 18px, ascent 14", r.stdout)
            data = pathlib.Path(out).read_bytes()
        f = read_svfn(data)
        from PIL import ImageFont
        font = ImageFont.truetype(NANUM_IN_TREE, 18)
        for cp in self.CHARS:
            _, rows = f["glyphs"][cp]
            ink_rows = [y for y, row in enumerate(rows) if any(row)]
            box, _ = mkfont.ink_box(font, chr(cp), 2)
            # Not moved: ink starts where the baseline puts it, or row 0 if
            # that is above the cell (cut, not pushed down).
            self.assertEqual(ink_rows[0], max(0, 14 + box[1]), chr(cp))
            self.assertEqual(ink_rows[-1] + 1, min(16, 14 + box[3]), chr(cp))


@unittest.skipUnless(NANUM_IN_TREE and os.path.exists(NANUM_IN_TREE), "in-tree NanumGothic-Bold not found")
class LatinAdvanceTest(unittest.TestCase):
    """--space-advance / --punct-extra: the advance table of a proportional Latin face."""

    def advances(self, *extra):
        import subprocess
        import tempfile
        out = tempfile.NamedTemporaryFile(suffix=".fnt", delete=False).name
        try:
            subprocess.run([sys.executable, mkfont.__file__, NANUM_IN_TREE, out, "--size", "16", "--cell", "18",
                            "--bpp", "1", "--unicode", "ascii,2026"] + list(extra), check=True, capture_output=True)
            data = pathlib.Path(out).read_bytes()
        finally:
            os.unlink(out)
        f = jamoset.parse_svfn(data)
        return {cp: m[0] for cp, m in f.metrics.items()}

    def test_defaults_keep_the_face_advances(self):
        a = self.advances()
        b = self.advances("--space-advance", str(a[0x20]), "--punct-extra", "0")
        self.assertEqual(a, b)

    def test_space_advance(self):
        a = self.advances()
        b = self.advances("--space-advance", "6")
        self.assertEqual(b[0x20], 6)
        for cp in a:
            if cp != 0x20:
                self.assertEqual(a[cp], b[cp], hex(cp))

    def test_punct_extra(self):
        a = self.advances()
        b = self.advances("--punct-extra", "1")
        for ch in ".,:;!?'\u2026":
            self.assertEqual(b[ord(ch)], a[ord(ch)] + 1, repr(ch))
        for ch in "aB1-()":
            self.assertEqual(b[ord(ch)], a[ord(ch)], repr(ch))
        self.assertEqual(b[0x20], a[0x20])


class V3WriterTest(unittest.TestCase):
    """mkfont.py writes SVFN v3 through jamoset.pack_svfn (--profile, --box); no character set is refused."""

    def run_mkfont(self, *extra, font=None):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.svf")
            r = subprocess.run([sys.executable, mkfont.__file__, font or NANUM_IN_TREE, out, "--size", "16", "--bpp", "1",
                                *extra], capture_output=True, text=True)
            data = pathlib.Path(out).read_bytes() if os.path.exists(out) else None
        return r, data

    @unittest.skipUnless(os.path.exists(NANUM_IN_TREE), "in-tree NanumGothic-Bold.ttf not found")
    def test_writes_v3_default(self):
        r, data = self.run_mkfont("--unicode", "ascii,AC00-AC10")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(data[4:6], b"\x03\x00")
        f = jamoset.parse_svfn(data)
        self.assertEqual(f.layout, (2, 0, 2, True))
        self.assertIn(0xAC00, f.glyphs)

    @unittest.skipUnless(os.path.exists(NANUM_IN_TREE), "in-tree NanumGothic-Bold.ttf not found")
    def test_profile_dos(self):
        _, a = self.run_mkfont("--unicode", "ascii,AC00-AC10")
        r, b = self.run_mkfont("--unicode", "ascii,AC00-AC10", "--profile", "dos")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(b[9], 0)
        self.assertEqual(jamoset.parse_svfn(b).glyphs, jamoset.parse_svfn(a).glyphs)

    @unittest.skipUnless(os.path.exists(NANUM_IN_TREE), "in-tree NanumGothic-Bold.ttf not found")
    def test_bad_profile_is_a_usage_error(self):
        r, _ = self.run_mkfont("--unicode", "ascii", "--profile", "nope")
        self.assertEqual(r.returncode, 2)

    @unittest.skipUnless(os.path.exists(NANUM_IN_TREE), "in-tree NanumGothic-Bold.ttf not found")
    def test_box_full(self):
        _, a = self.run_mkfont("--unicode", "ascii,AC00-AC10")
        r, b = self.run_mkfont("--unicode", "ascii,AC00-AC10", "--box", "full")
        self.assertEqual(r.returncode, 0, r.stderr)
        fa, fb = jamoset.parse_svfn(a), jamoset.parse_svfn(b)
        self.assertEqual(fb.glyphs, fa.glyphs)
        pitch = (fa.cell_w + 7) // 8
        inked = [x for x in jamoset.record_boxes(b) if x[2]]
        self.assertTrue(inked)
        self.assertTrue(all(x[2] == pitch and x[3] == fa.cell_h for x in inked))
        self.assertTrue(any(x[3] < fa.cell_h for x in jamoset.record_boxes(a) if x[2]))
        self.assertGreater(len(b), len(a))

    def test_no_charset_refused(self):
        r, data = self.run_mkfont(font=os.devnull)
        self.assertEqual(r.returncode, 2)
        self.assertIn("mkfont: version 1 (code page order) is gone: pass --unicode SET", r.stderr)
        self.assertIsNone(data)


try:
    import fontTools  # noqa: F401  (cmap_has answers None or bool only with fontTools)
    HAVE_FONTTOOLS = True
except ImportError:
    HAVE_FONTTOOLS = False


@unittest.skipUnless(HAVE_FONTTOOLS, "fontTools not importable")
class CmapHasTest(unittest.TestCase):
    def test_bdf_gives_none_and_caches_it(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.bdf")
            with open(p, "w") as f:
                f.write("STARTFONT 2.1\nFONT -t\nSIZE 16 75 75\nFONTBOUNDINGBOX 16 16 0 0\nCHARS 0\nENDFONT\n")
            mkfont.cmap_has.__dict__.pop("cache", None)
            self.assertIsNone(mkfont.cmap_has(p, 0x41))
            self.assertIn(p, mkfont.cmap_has.cache)
            self.assertIsNone(mkfont.cmap_has(p, 0xAC00))

    def test_ttf_still_answers(self):
        ttf = os.path.join(os.path.dirname(HERE_DIR), "ttf", "nanumgothic", "NanumGothic-Bold.ttf")
        self.assertTrue(mkfont.cmap_has(ttf, 0x41))
        self.assertFalse(mkfont.cmap_has(ttf, 0x10FFFF))


def tall_ttf(path):
    """A synthetic TTF (unitsPerEm 1000): 'ga' at U+AC00 and 'A' at U+0041, each a rectangle x 100..600, y -180..740
    (at 16 px 1 bpp the box rows are -12..3)."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    def rect():
        pen = TTGlyphPen(None)
        pen.moveTo((100, -180))
        pen.lineTo((100, 740))
        pen.lineTo((600, 740))
        pen.lineTo((600, -180))
        pen.closePath()
        return pen.glyph()

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "space", "A", "ga"])
    fb.setupCharacterMap({0x20: "space", 0x41: "A", 0xAC00: "ga"})
    fb.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "space": TTGlyphPen(None).glyph(), "A": rect(), "ga": rect()})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "space": (300, 0), "A": (700, 100), "ga": (700, 100)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": "Tall", "styleName": "Regular"})
    fb.save(path)
    return path


@unittest.skipUnless(HAVE_FONTTOOLS, "fontTools not importable")
class ReportTest(unittest.TestCase):
    """--report FILE.json, --probe, --probe-cell."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = tall_ttf(os.path.join(self.tmp.name, "tall.ttf"))
        self.out = os.path.join(self.tmp.name, "out.svf")
        self.report = os.path.join(self.tmp.name, "report.json")

    def run_mkfont(self, *flags):
        import subprocess
        return subprocess.run([sys.executable, "-P", os.path.join(HERE_DIR, "mkfont.py"), self.src, self.out,
                               "--unicode", "ascii,AC00", "--report", self.report, *flags],
                              capture_output=True, text=True)

    def bake(self, *flags):
        import json
        r = self.run_mkfont(*flags)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.report, encoding="utf-8") as f:
            return json.load(f)

    def probe(self, *flags):
        rep = self.bake(*flags)
        if not os.path.exists(self.out):
            return rep, None
        with open(self.out, "rb") as f:
            return rep, f.read()

    def test_report_json(self):
        rep = self.bake("--size", "16", "--bpp", "1", "--cell", "12", "--ascent", "10", "--clip-cell")
        self.assertEqual(rep["boxes"]["0xAC00"][1:4:2], [-12, 3])
        self.assertEqual(rep["cut"]["0xAC00"]["top"], 2)
        self.assertEqual(rep["cut"]["0xAC00"]["bottom"], 1)
        top, bottom, wide = mkfont.fit_counts({int(k, 16): v for k, v in rep["boxes"].items()}, 12, 12, 10)
        self.assertEqual(rep["counts"], {"glyphs": len(rep["boxes"]), "top": len(top), "bottom": len(bottom),
                                         "wide": len(wide), "cut": len(set(top) | set(bottom)), "gone": 0})
        self.assertIs(rep["cut"]["0xAC00"]["gone"], False)
        self.assertEqual((rep["mode"], rep["ascent"], rep["cell"]), ("clip", 10, [12, 12]))
        self.assertEqual(list(rep)[:3], ["tool", "probe", "probe_face"])
        self.assertEqual((rep["tool"], rep["probe"], rep["probe_face"], rep["size"], rep["requested_size"],
                          rep["bpp"], rep["latin"], rep["auto_ascent"]), ("mkfont", False, True, 16, 16, 1, False, 10))
        self.assertGreater(rep["cut"]["0xAC00"]["full"], 0)
        self.assertNotIn("nudged", rep)
        self.assertEqual(rep["wide"], [])

    def test_nudge_mode_lists_nudged(self):
        rep = self.bake("--size", "16", "--bpp", "1", "--cell", "12", "--ascent", "10")
        self.assertEqual(rep["mode"], "nudge")
        self.assertIn("0xAC00", rep["nudged"])
        self.assertNotIn("cut", rep)

    def test_fit_cell_reports_the_lowered_size(self):
        rep = self.bake("--size", "16", "--bpp", "1", "--cell", "12", "--fit-cell")
        self.assertEqual((rep["mode"], rep["requested_size"]), ("fit", 16))
        self.assertLess(rep["size"], 16)

    def test_probe_mode(self):
        from PIL import ImageFont
        rep, face = self.probe("--size", "16", "--bpp", "1", "--width", "16", "--probe", "--probe-cell", "12")
        f = jamoset.parse_svfn(face)
        self.assertEqual((f.cell_h, f.ascent, rep["probe"], rep["probe_face"]), (15, 12, True, True))
        boxes = {int(k, 16): v for k, v in rep["boxes"].items()}
        font = ImageFont.truetype(self.src, 16)
        self.assertEqual(rep["auto_ascent"], mkfont.fit_ascent(boxes, 12, mkfont.choose_ascent(font, 12, False))[0])
        self.assertEqual(mkfont.fit_counts(boxes, 16, 15, 12), ([], [], []))        # nothing cut by construction

    NANUM = os.path.join(os.path.dirname(HERE_DIR), "ttf", "nanumgothic", "NanumGothic-Regular.ttf")

    @unittest.skipUnless(os.path.exists(NANUM), "in-tree NanumGothic-Regular.ttf not found")
    def test_mono_hint_boxes_are_the_baked_ink(self):
        """--mono-hint bakes with FreeType's monochrome renderer; the boxes, the fit and the cut counts must measure that
        same ink, not the anti-aliased one (the probe's box rows equal the probe face's ink rows)."""
        self.src = self.NANUM
        rep, face = self.probe("--size", "13", "--bpp", "1", "--width", "13", "--probe", "--mono-hint")
        f = jamoset.parse_svfn(face)
        pitch = (f.cell_w + 7) // 8
        checked = 0
        for key, (left, top, right, bottom) in rep["boxes"].items():
            cell = f.glyphs.get(int(key, 16))
            if cell is None:
                continue
            rows = [i for i in range(f.cell_h) if any(cell[i * pitch:(i + 1) * pitch])]
            self.assertEqual((rows[0] - f.ascent, rows[-1] + 1 - f.ascent), (top, bottom), key)
            checked += 1
        self.assertGreater(checked, 50)

    @unittest.skipUnless(os.path.exists(NANUM), "in-tree NanumGothic-Regular.ttf not found")
    def test_mono_hint_clipped_ink_counts_the_hinted_pixels(self):
        from PIL import ImageFont
        font = ImageFont.truetype(self.NANUM, 13)
        old = mkfont.MONO_HINT
        try:
            mkfont.MONO_HINT = False
            plain = mkfont.clipped_ink(font, "\uac00", 1, 3, 8)
            mkfont.MONO_HINT = True
            hinted = mkfont.clipped_ink(font, "\uac00", 1, 3, 8)
            img, _, _ = mkfont.render(font, "\uac00", 16, 40, 30, 1, nudge=False)
        finally:
            mkfont.MONO_HINT = old
        self.assertNotEqual(plain, hinted)                       # the two renderers do not agree on this glyph
        # the cell above row 3 .. below row 11 of a glyph drawn at baseline 30 in a 40-row image: the cut pixels
        rows = [[img.getpixel((x, y)) for x in range(16)] for y in range(40)]
        top, bottom = 30 - 3, 30 - 3 + 8
        full = sum(1 for y, r in enumerate(rows) if y < top or y >= bottom for v in r if v == 255)
        self.assertEqual(hinted[0], full)

    def test_probe_cell_function(self):
        self.assertEqual(mkfont.probe_cell({}), (1, 1))
        self.assertEqual(mkfont.probe_cell({1: (0, -12, 5, 3), 2: (0, -4, 5, 0)}), (12, 15))
        self.assertEqual(mkfont.probe_cell({1: (0, 2, 5, 6)}), (1, 7))

    def test_probe_past_255_rows_writes_only_the_report(self):
        rep, face = self.probe("--size", "300", "--bpp", "1", "--width", "300", "--probe")
        self.assertEqual((rep["probe_face"], face), (False, None))

    def test_probe_refuses_cell_flags(self):
        for flags in (["--cell", "12"], ["--ascent", "9"], ["--clip-cell"], ["--fit-cell"]):
            with self.subTest(flags=flags):
                r = self.run_mkfont("--size", "16", "--bpp", "1", "--probe", *flags)
                self.assertEqual(r.returncode, 2)
                self.assertIn("--probe sets the cell and ascent itself", r.stderr)
                self.assertFalse(os.path.exists(self.report))

    def test_a_glyph_the_cell_removes_whole_is_gone(self):
        # ink rows -12..3, ascent 14, cell 2: the window is rows -14..-12, so every ink row is outside
        rep = self.bake("--size", "16", "--bpp", "1", "--cell", "2", "--ascent", "14", "--clip-cell")
        self.assertIs(rep["cut"]["0xAC00"]["gone"], True)
        self.assertEqual(rep["counts"]["gone"], rep["counts"]["cut"])
        self.assertGreater(rep["counts"]["gone"], 0)

    def test_nudged_cps_guards_whitespace_bitmap_fonts_and_picks_the_fallback(self):
        class Raises:
            def getbbox(self, ch, anchor=None):
                raise ValueError("bitmap font")

        class Boxes:
            def __init__(self, box):
                self.box = box

            def getbbox(self, ch, anchor=None):
                return self.box

        self.assertEqual(mkfont.nudged_cps([0x20, 0x3000], 10, lambda cp: Boxes(None)), [])
        self.assertEqual(mkfont.nudged_cps([0x41], 10, lambda cp: Raises()), [])
        primary, fallback = Boxes((0, -12, 5, 0)), Boxes((0, -3, 5, 0))
        self.assertEqual(mkfont.nudged_cps([0x41, 0xAC00], 10, lambda cp: fallback if cp == 0xAC00 else primary), [0x41])

    def test_probe_cell_is_range_checked(self):
        for bad in ("0", "-3", "256"):
            r = self.run_mkfont("--size", "16", "--probe", "--probe-cell", bad)
            self.assertEqual(r.returncode, 2, bad)
            self.assertIn("--probe-cell", r.stderr)

    def test_probe_cell_needs_probe(self):
        r = self.run_mkfont("--size", "16", "--probe-cell", "12")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--probe-cell", r.stderr)


BM_ORDER = [".notdef", "A", "B", "D", "C", "E", "F", "M", "G"]     # glyph order of the synthetic bitmap-only font


def bitmap_only_font(path, hmtx_px, strikes, with_g=False):
    """Write a bitmap-only TrueType (bdat + bloc + bhed + hmtx, no head, no glyf) of the glyphs BM_ORDER.

    @p hmtx_px {name: advance px at 16 ppem} fills hmtx (1024 units per em), on purpose unlike the strikes.
    @p strikes [(ppemX, ppemY, groups[, rows])]; rows (default 8) is the bitmap height, so the strikes draw
    distinguishable pictures; a group is ("small", {name: advance}) with per-glyph small metrics
    (bdat format 1), ("big", {name: advance}) with big metrics (format 6) or ("shared", [names], advance) of
    format 5, whose one metrics record sits in the bloc index subtable. Groups cover consecutive glyphs of
    BM_ORDER from .notdef; a glyph in no group is missing from that strike. Every glyph is an 8x8 block,
    .notdef a narrower one so the letters are not taken for "absent".
    """
    import tempfile
    from fontTools.fontBuilder import FontBuilder
    from fontTools.misc.xmlReader import XMLReader
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import TTFont, newTable

    names = BM_ORDER if with_g else BM_ORDER[:-1]     # G is in no strike: mkfont cannot bake a font that has it
    fb = FontBuilder(1024, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({(0x301 if n == "M" else ord(n)): n for n in names[1:]})
    fb.setupGlyf({n: TTGlyphPen(None).glyph() for n in names})
    fb.setupHorizontalMetrics({n: (hmtx_px.get(n, 0) * 64, 0) for n in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Synth Bitmap", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.save(path)
    f = TTFont(path)
    bhed = newTable("bhed")
    bhed.__dict__.update(f["head"].__dict__)
    del f["head"], f["glyf"], f["loca"]
    f["bhed"] = bhed
    line = ('<sbitLineMetrics direction="%s"><ascender value="13"/><descender value="-3"/>'
            '<widthMax value="16"/><caretSlopeNumerator value="1"/><caretSlopeDenominator value="0"/>'
            '<caretOffset value="0"/><minOriginSB value="0"/><minAdvanceSB value="0"/>'
            '<maxBeforeBL value="0"/><minAfterBL value="0"/><pad1 value="0"/><pad2 value="0"/></sbitLineMetrics>')

    def big(adv, w=8, rows=8):
        return ('<BigGlyphMetrics><height value="%d"/><width value="%d"/><horiBearingX value="0"/>'
                '<horiBearingY value="8"/><horiAdvance value="%d"/><vertBearingX value="0"/>'
                '<vertBearingY value="0"/><vertAdvance value="8"/></BigGlyphMetrics>' % (rows, w, adv))

    def bits(n, rows=8):
        return "<rawimagedata>%s</rawimagedata>" % " ".join(["f0" if n == ".notdef" else "ff"] * rows)

    xml = ['<?xml version="1.0"?><ttFont><bloc><header version="2.0"/>']
    data = ['<bdat><header version="2.0"/>']
    for k, (px, py, groups, *rest) in enumerate(strikes):
        rows = rest[0] if rest else 8
        ids = [BM_ORDER.index(n) for g in groups for n in (g[1] if g[0] == "shared" else g[1])]
        xml += ['<strike index="%d"><bitmapSizeTable>' % k, line % "hori", line % "vert",
                '<colorRef value="0"/><startGlyphIndex value="%d"/><endGlyphIndex value="%d"/>' % (min(ids), max(ids)),
                '<ppemX value="%d"/><ppemY value="%d"/><bitDepth value="1"/><flags value="1"/></bitmapSizeTable>'
                % (px, py)]
        data.append('<strikedata index="%d">' % k)
        for g in groups:
            gnames = list(g[1])
            lo, hi = BM_ORDER.index(gnames[0]), BM_ORDER.index(gnames[-1])
            if g[0] == "shared":
                xml.append('<eblc_index_sub_table_2 imageFormat="5" firstGlyphIndex="%d" lastGlyphIndex="%d">'
                           '<imageSize value="%d"/>%s' % (lo, hi, rows, big(g[2], 8, rows)))
                for n in gnames:
                    data.append('<ebdt_bitmap_format_5 name="%s">%s</ebdt_bitmap_format_5>' % (n, bits(n, rows)))
            else:
                fmt = 1 if g[0] == "small" else 6
                xml.append('<eblc_index_sub_table_1 imageFormat="%d" firstGlyphIndex="%d" lastGlyphIndex="%d">'
                           % (fmt, lo, hi))
                for n in gnames:
                    w = 4 if n == ".notdef" else 8
                    adv = g[1][n]
                    if fmt == 1:
                        m = ('<SmallGlyphMetrics><height value="%d"/><width value="%d"/><BearingX value="0"/>'
                             '<BearingY value="8"/><Advance value="%d"/></SmallGlyphMetrics>' % (rows, w, adv))
                    else:
                        m = big(adv, w, rows)
                    data.append('<ebdt_bitmap_format_%d name="%s">%s%s</ebdt_bitmap_format_%d>'
                                % (fmt, n, m, bits(n, rows), fmt))
            xml += ['<glyphLoc id="%d" name="%s"/>' % (BM_ORDER.index(n), n) for n in gnames]
            xml.append("</eblc_index_sub_table_%d>" % (2 if g[0] == "shared" else 1))
        xml.append("</strike>")
        data.append("</strikedata>")
    xml.append("</bloc>")
    data.append("</bdat></ttFont>")
    f.bitmapGlyphDataFormat = "raw"
    with tempfile.NamedTemporaryFile("w", suffix=".ttx", delete=False) as t:
        t.write("".join(xml + data))
    try:
        XMLReader(t.name, f).read()
    finally:
        os.unlink(t.name)
    f.save(path)


def _have_fonttools():
    try:
        import fontTools  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(_have_fonttools(), "fontTools not installed")
class BitmapOnlyAdvanceTest(unittest.TestCase):
    """A bitmap-only TrueType has no head, so Pillow's getlength() is 0: the advances come from the strike.

    hmtx here never agrees with the strikes (A 7 vs 9, ...), so only the strike can give the expected value.
    """

    HMTX = {"A": 7, "B": 7, "C": 7, "D": 7, "E": 7, "F": 7, "G": 13}
    N = (".notdef", 8)

    def strikes(self):
        n = {".notdef": 8}
        return [
            # decoys before the real 16 px strike: FreeType uses a strike only when ppemX AND ppemY are the size
            # (a 14x16-only font cannot be opened at 16), so neither is drawn; their bitmaps are 4 and 5 rows
            (14, 16, [("small", {**n, "A": 3, "B": 3, "D": 3})], 4),
            (16, 14, [("small", {**n, "A": 2, "B": 2, "D": 2})], 5),
            (16, 16, [("small", {**n, "A": 9, "B": 11, "D": 0}), ("big", {"C": 12}),
                      ("shared", ["E", "F", "M"], 14)]),
            (12, 12, [("small", {**n, "A": 5, "B": 6, "D": 7, "C": 8, "E": 9, "F": 10, "M": 11})], 6),
        ]

    def make(self, d, with_g=False):
        src = os.path.join(d, "bm.ttf")
        bitmap_only_font(src, self.HMTX, self.strikes(), with_g)
        return src

    def bake(self, letters, size="16", extra=()):
        """Advances of the glyphs named in @p letters (a string of the letters); the whole font is baked."""
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            src, out = self.make(d), os.path.join(d, "o.svf")
            r = subprocess.run([sys.executable, mkfont.__file__, src, out, "--size", size, "--bpp", "1",
                                "--unicode", "ascii,301", "--ascent", str(13 if size == "16" else 10), *extra],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            f = jamoset.parse_svfn(pathlib.Path(out).read_bytes())
        return {ord(c): f.metrics[ord(c)][0] for c in letters}

    def test_small_metrics_of_the_strike_not_hmtx(self):
        self.assertEqual(self.bake("AB"), {0x41: 9, 0x42: 11})

    def test_big_metrics_and_shared_format_5_metrics(self):
        self.assertEqual(self.bake("CEF"), {0x43: 12, 0x45: 14, 0x46: 14})

    def test_an_explicit_zero_in_the_strike_stays_zero(self):
        self.assertEqual(self.bake("D")[0x44], 0)

    def test_size_picks_its_own_strike(self):
        self.assertEqual(self.bake("ABD", size="12"), {0x41: 5, 0x42: 6, 0x44: 7})

    def test_the_advance_belongs_to_the_strike_pillow_draws(self):
        # 14x16 and 16x14 come first in the font; FreeType draws only the 16x16 one (8 rows), so A = 9
        # (a rule taking ppemX or ppemY alone would give 3 or 2)
        from PIL import ImageFont
        with tempfile.TemporaryDirectory() as d:
            src = self.make(d)
            self.assertEqual(ImageFont.truetype(src, 16).getmask("A").getbbox(), (0, 0, 8, 8))
            self.assertEqual(ImageFont.truetype(src, 12).getmask("A").getbbox(), (0, 0, 8, 6))
            self.assertEqual(mkfont.strike_advance(src, 16, "A"), 9)
            self.assertEqual(mkfont.strike_advance(src, 12, "A"), 5)    # one process, two sizes: the cache is per size
        self.assertEqual(self.bake("A")[0x41], 9)

    def test_glyph_missing_from_the_strike_falls_back_to_hmtx(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            src = self.make(d, with_g=True)
            self.assertEqual(mkfont.strike_advance(src, 16, "G"), 13)      # not in the 16 px strike: hmtx
            self.assertEqual(mkfont.strike_advance(src, 16, "A"), 9)
            self.assertIsNone(mkfont.strike_advance(src, 16, "\u00e9"))   # not in the cmap

    def test_outline_font_is_not_asked(self):
        self.assertIsNone(mkfont.strike_advance(NANUM_IN_TREE or "/nonexistent", 16, "A"))

    def test_marks_keep_advance_zero(self):
        # U+0301 has a strike advance of 14, and is baked with 0: a combining mark does not advance
        self.assertEqual(self.bake("AM".replace("M", "\u0301"))[0x301], 0)

    def test_collection_face_0_equals_the_standalone_face(self):
        import subprocess
        from fontTools.ttLib import TTCollection, TTFont
        with tempfile.TemporaryDirectory() as d:
            src = self.make(d)
            ttc = os.path.join(d, "bm.ttc")
            c = TTCollection()
            c.fonts = [TTFont(src)]
            c.save(ttc)
            outs = []
            for name in (src, ttc):
                out = os.path.join(d, os.path.basename(name) + ".svf")
                r = subprocess.run([sys.executable, mkfont.__file__, name, out, "--size", "16", "--bpp", "1",
                                    "--unicode", "ascii,301", "--ascent", "13"], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stderr, "")
                outs.append(pathlib.Path(out).read_bytes())
            self.assertEqual(mkfont.strike_advance(ttc, 16, "B"), 11)
            self.assertEqual(outs[0], outs[1])

    def advance_with_stderr(self, src, size=16):
        import contextlib
        import io
        mkfont._STRIKE_ADVANCES.clear()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            adv = mkfont.strike_advance(src, size, "A")
        return adv, err.getvalue()

    def test_unreadable_strike_data_says_so_on_stderr(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            src = self.make(d)
            self.assertEqual(self.advance_with_stderr(src), (9, ""))
            with mock.patch.object(mkfont, "_metrics_advance", side_effect=ValueError("boom")):
                adv, err = self.advance_with_stderr(src)
            self.assertIsNone(adv)
            self.assertIn("boom", err)
            self.assertEqual(err.count("\n"), 1)
            with mock.patch("fontTools.ttLib.TTFont", side_effect=OSError("cannot open")):
                adv, err = self.advance_with_stderr(src)
            self.assertIsNone(adv)
            self.assertIn("cannot open", err)
            with mock.patch.dict(sys.modules, {"fontTools.ttLib": None}):      # no fontTools
                adv, err = self.advance_with_stderr(src)
            self.assertIsNone(adv)
            self.assertIn(src, err)

    def test_ordinary_inputs_stay_silent(self):
        with tempfile.TemporaryDirectory() as d:
            txt = os.path.join(d, "x.bdf")
            pathlib.Path(txt).write_text("STARTFONT 2.1\n")
            self.assertEqual(self.advance_with_stderr(txt), (None, ""))
            self.assertEqual(self.advance_with_stderr(os.path.join(d, "missing.ttf")), (None, ""))
            if NANUM_IN_TREE and os.path.exists(NANUM_IN_TREE):
                self.assertEqual(self.advance_with_stderr(NANUM_IN_TREE), (None, ""))

    def test_ink_advance_is_unchanged(self):
        self.assertEqual(self.bake("AB", extra=("--ink-advance",)), {0x41: 9, 0x42: 9})


if __name__ == "__main__":
    unittest.main()
