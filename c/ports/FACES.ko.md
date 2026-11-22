[English](FACES.md) | **한국어**

| 페이스 파일 | 출처(원본, 버전) | 저작권 / 저자 | 라이선스 | 라이선스 파일 | 만든 방법 |
|---|---|---|---|---|---|
| `svf/dos/PAPLG16.SVF` (ASCII, 2 bpp, 18 px 셀, 149 glyph) | Paperlogy-4Regular.ttf, Paperlogy 4 Regular 버전 1.000 | Copyright (c) 2024 PT& (www.designptn.com); Paperlogy는 Lee Juim이 재디자인했고 한글 glyph은 Gmarket Sans, 라틴은 Montserrat에서 가져왔다(폰트의 name 테이블, `OFLPAPLG.TXT`에 인용) | SIL OFL 1.1, Reserved Font Name 주장 없음 | `svf/dos/OFLPAPLG.TXT` | `mkfont.py`로 16 px에서 래스터화(정확한 명령은 `svf/dos/PAPLG.TXT`): OFL 하의 수정 버전(Modified Version) |
| `svf/dos/PAPLG18.SVF` (2 bpp 자모 세트, 18 x 18, 24/16/16 조각 세트) | 같은 폰트, 버전 1.000 | 같음 | 같음 | 같음 | Paperlogy의 음절 아웃라인을 초성/중성/종성 벡터 조각으로 분리하고, 18 px로 래스터화한 뒤 `fontbuild2.py`로 24/16/16 세트로 병합(연구 실행 `seg-night/F`; `svf/dos/PAPLG.TXT`에 실행, 해시, IoU가 기록되어 있음): OFL 하의 수정 버전 |
| `svf/dos/NEODG16G.SVF` (16 px 1 bpp 자모 세트, 6x2x1 레이아웃) | `ttf/neodgm/neodgm.ttf`, Neo Dunggeunmo 버전 1.601 | Copyright (c) 2017-2021, Eunbin Jeong (Dalgona.) | SIL OFL 1.1; Reserved Font Names "Neo둥근모", "Neo둥근모 Code", "NeoDunggeunmo", "NeoDunggeunmo Code" (페이스는 사용하지 않음) | `svf/dos/OFL.TXT` (`svf/dos/NEODGM.TXT`) | `mkfont.py`로 16 px 1 bpp 래스터화(ASCII와 KS X 1001 음절 2,350자) 후 `jamoset.py --layout 621 --from-svf --check`로 6x2x1 조각으로 분할(`tools/build/faces.tsv`, `docs/recipes.ko.md`): OFL 하의 수정 버전 |

포트와 벤치는 이 페이스들을 `c/bench/mkface.py --profile mcu-strict`로 재배치해 내장한다(레코드와 테이블
단위 4바이트, 들어맞는 곳은 16비트 오프셋. 픽셀은 같다). 내장 배열의 크기는 전체 파일과
glyph 데이터(`svfdump info`의 `data_size`) 순으로: `NEODG16G` 10,124와 5,512 바이트(`default` 파일에서는 10,684), `PAPLG16` 7,460과 5,324(명세 5,324), `PAPLG18` 67,200과 40,024
(명세 39,800, +0.6 %)이다. PAPLG 페이스는 명세 추정치의 1 % 이내이다. Pico와 ESP32 컬러 및 그레이 이미지는 `PAPLG16` +
`PAPLG18`(74,660 바이트)을 내장하고, 모노 이미지와 Arduino 스케치는 `NEODG16G`를 내장한다.

> Copyright (c) 2024 PT& (www.designptn.com), Paperlogy; redesigned by Lee Juim, Hangul glyphs from
> Gmarket Sans, Latin from Montserrat (as stated in the font file's name table: copyright, designer and
> licence entries of Paperlogy-4Regular.ttf, version 1.000).
