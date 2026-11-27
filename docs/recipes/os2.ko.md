[English](os2.md) | **한국어**

# 레시피: OS/2 한글 폰트(완성형)

OS/2 한글 System DBCS 폰트(`$korZN16.FNT`, `$korZN24.FNT`; 완성형): 94 x 94 표의 해독, 완성형 페이스, 그리고 거기에 맞춘 자모 세트.

**시작 전에.** 명령은 [색인](../recipes.ko.md)에서처럼 `$OUT`을 정하고 프로젝트 루트에서 실행한다. 모든 페이스는 [페이스 점검](../recipes.ko.md#페이스-점검)의 점검으로 끝난다. 폰트는 독점 파일이라 따로 마련한다. `$OUT/ks.txt`는 [프로그램과 드라이버 안의 폰트](programs-and-drivers.ko.md#프롬프트)에서처럼 쓴다.

위로: [레시피 색인](../recipes.ko.md) · 관련 문서: [프로그램과 드라이버 안의 폰트](programs-and-drivers.ko.md), [비트맵 폰트](bitmap-fonts.ko.md), [벌 수 정하기](sets.ko.md).

<a id="os2-한글-폰트완성형에서-완성형-페이스와-자모-세트-만들기"></a>

## OS/2 한글 폰트(완성형)에서 완성형 페이스와 자모 세트 만들기

<a id="os2-한글-폰트완성형"></a>

OS/2의 한글 "System DBCS" 폰트(`$korZN16.FNT`, `$korZN24.FNT`)는 완성형이다. KS X 1001 표 전체(기호 1,128개, 음절 2,350개, 한자
4,888개)를 코드 순서로 담고, 글리프마다 압축되어 있다(니블의 허프만 부호, 그다음 위 두 행에서 문맥 표로 예측). `tools/os2dbcs.py`가
이를 94 x 94 표로 풀고, 그다음은 어느 KS X 1001 덤프와 같은 길이다: BDF, `bdfface.py`, 그리고 그 페이스에 맞춘 자모 세트.

    python3 -I tools/os2dbcs.py info '$korZN16.FNT'
    python3 -I tools/os2dbcs.py table '$korZN16.FNT' -o $OUT/zn16.bin
    python3 -I tools/rawcarve.py bdf $OUT/zn16.bin --glyph 16x16 --chars ks-hangul --grid 0xA1,0xA1,94 -o $OUT/zn16.bdf
    python3 maker/srcprep.py pcf-bdf /usr/share/fonts/X11/misc/8x16.pcf.gz $OUT/8x16.bdf   # Misc Fixed 8x16, Debian xfonts-base
    python3 tools/bdfface.py --hangul $OUT/zn16.bdf --ascii $OUT/8x16.bdf --cell 16x16 --chars-from $OUT/ks.txt -o $OUT/OS2ZN16.SVF
    python3 tools/jamoset.py --layout 844 --from-svf $OUT/OS2ZN16.SVF --mask-font none --check -o $OUT/OS2ZN16J.SVF
    python3 tools/jamoset.py --layout adaptive --from-svf $OUT/OS2ZN16.SVF --mask-font none --check -o $OUT/OS2ZN16JA.SVF

OS/2 Warp 4 한국어판(IBM. CD의 FTCOMP 묶음을 johab-fonts 연구에서 푼 것, `D28REQ.004` = `$korZN16.FNT` 220,160 바이트, `D28REQ.002` =
`$korZN24.FNT` 346,624 바이트, 독점)에서 실행했다. `info`: "System DBCS 16", 16x16, 글리프당 32 바이트, 리드 바이트 A1-AC, B0-C8, CA-FD,
글리프 레코드 8,224개, 음절 2,350개 모두 있음. `table`은 슬롯 8,742개(279,744 바이트, 연구 디코더의 덤프와 같은 바이트)를 쓴다. 영문
절반은 이 호스트의 X11 "Misc Fixed" 8x16과 12x24(`xfonts-base`, 퍼블릭 도메인)이다. OS/2의 DBCS 파일에는 ASCII가 없다. 24 px 페이스는
같은 명령에 `--glyph 24x24 --ascent 22`, `12x24.pcf.gz`, `--cell 24x24`:

| 페이스 | 바이트 | 글리프 | 맞춤 | measure | 잉크 |
|---|---|---:|---|---|---:|
| `OS2ZN16.SVF`, 완성형 16 px | `123,328` | 2,447 | | `width=144 ascent=14 descent=2` | 469 |
| 그 8x4x4 자모 세트 | `17,264` | 441 | IoU 0.984 (p5 0.898), 2,350 중 1,753 정확, 0.3 s | 같음 | 470 |
| adaptive 자모 세트 | `42,140` | 858 | 벌 14/12/9, IoU 0.999, 2,299 정확, 3 s | 같음 | 469 |
| `OS2ZN24.SVF`, 완성형 24 px | `220,164` | 2,447 | | `width=216 ascent=22 descent=2`(규칙 `line 400 32 0 24`) | 922 |
| 그 8x4x4 자모 세트 | `30,544` | 441 | IoU 0.720 (p5 0.457), 17 정확, 0.8 s | 같음 | 909 |
| adaptive 자모 세트 | `100,740` | 1,533 | 벌 32/24/12, IoU 0.883, 548 정확, 11 s | 같음 | 921 |

모든 자모 세트에서 `--check`는 11,172 음절을 모두 조합한다. 16 px 디자인은 조각의 OR에 가까워 8x4x4로도 0.984가 맞지만, 24 px는
음절마다 따로 그린 디자인이라 기본 adaptive 예산(벌 32/24/12)으로도 잘 맞지 않는다. 예산이 허락하면 완성형 페이스를 두거나
[벌 수 정하기](sets.ko.md#벌-수-정하기)를 보라. `rawcarve.py bdf` 줄에 `--chars ks-nonhanja`를 주면 기호와 호환 자모까지 남는다
(글리프 3,334개). `bdfface.py`는 음절만 남기고, `mkfont.py`는 BDF를 그 자신의 크기로 읽는다: `mkfont.py $OUT/zn16-nh.bdf ... --size 16
--bpp 1 --unicode ksx1001-hangul,jamo`는 `123,880 bytes`, 글리프 2,444개, 샘플 줄의 다섯 음절 `width=80`, 잉크 310을 쓴다.
`--unicode ksx1001-nohanja`는 Pillow의 `raqm_get_glyphs() failed`로 멈춘다. KS X 1001 A1A9는 셰이퍼가 버리는 U+00AD(소프트 하이픈)이니
목록에서 빼라(`--chars-from`). 같은 CD의 `$SYS1Z16/24.FNT` 파일은 음절이 아니다(조각으로 된 IBM 사용자 영역). 읽지 않는다.

[레시피 색인](../recipes.ko.md) · [도구 설명서](../tools.ko.md)
