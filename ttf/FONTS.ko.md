[English](FONTS.md) | **한국어**

# 고해상도 게임 텍스트용 폰트

이 폰트들은 고해상도 텍스트 레이어(`graphics/hires_text`)를 위해 ScummVM과 함께 배포된다.
게임의 `hires_text.map`은 `data:` 접두사로 폰트를 지정한다. 예를 들면 다음과 같다.

    [fonts]
    ko=data:hires_text/fonts/nanumgothic/NanumGothic-Bold.ttf

`data:`는 유효한 extrapath(명령줄, 게임 또는 전역 설정)에서 먼저 찾고, 다음으로 애플리케이션 수준 extrapath,
그다음으로 ScummVM 데이터 디렉터리에서 찾는다. `make install`은 이 폴더를
`<datadir>/hires_text/fonts/`에 설치한다. 소스 트리에서는 `--extrapath=dists/engine-data`로 실행한다. 예제 맵은 `../maps/`에 있다.

`hires_text/`는 POSIX `make install`만 설치한다. macOS 앱 번들,
dist-generic, 그 밖의 포트 패키지는 설치하지 않는다. 그런 환경에서는 `hires_text/`를 아무 곳에나 복사하고
`extrapath`가 그 폴더가 들어 있는 위치를 가리키게 한다.
`data:` 경로는 절대 경로일 수 없고 `..`를 포함할 수 없다.

여기 있는 모든 폰트는 수정하지 않은 상류(upstream) 파일이다. 라이선스 본문도 같은 폴더에 수정 없이
그 옆에 있다. 모두 SIL Open Font License 1.1(`LICENSES/COPYING.OFL`에도 있음)로
라이선스된다. OFL에서는 폰트를 번들하고, 내장하고, 재배포할 수 있으며 상업적으로도 가능하지만, 폰트
자체를 판매할 수는 없다. 수정 버전(서브셋, 구워 낸 비트맵 폰트,
변환물)은 Reserved Font Name을 사용해서는 안 된다.

파일 두 개만 이름을 바꾸었으며 내용은 그대로이다. Google Fonts는 가변 폰트를
`EBGaramond[wght].ttf`와 `Caveat[wght].ttf`로 부른다. 여기서는
`EBGaramond-VF.ttf`와 `Caveat-VF.ttf`로 하여 맵 파일과
Makefile에 대괄호가 필요 없게 했다.

각 파일은 상류와 바이트 단위로 일치한다. 2026-09-28에
github.com/google/fonts(`ofl/<family>/`), Galmuri v2.40.4 릴리스 zip,
neodgm v1.601 릴리스 자산과 대조해 확인했다.

## 텍스트 페이스

| 폴더 | 파일 | 크기 | 권장 용도 |
|---|---|---|---|
| `nanumgothic/` | NanumGothic-Regular.ttf, NanumGothic-Bold.ttf, OFL.txt | 2.0 + 2.0 MB | 기본 한글 페이스(face). 2배율의 블렌딩(알파) 텍스트(SCUMM v5/v6, SCI, AGS)에는 **Bold**. 키잉(keyed) 8비트 텍스트에는 **Regular**. 한글 음절 11172자를 모두 담지만 한자는 없다. |

**NanumGothic** (나눔고딕)
- Copyright © 2010 NHN Corporation(현재 Naver), `OFL.txt`에 따름. 폰트의
  name 테이블에는 "Copyright © 2011 NHN Corporation. All rights reserved.
  Font designed by Sandoll Communications Inc."라고 되어 있다.
- 디자이너(name 테이블): Bruce Kwon, Nicolas Noh, Sung-woo Choi.
- 라이선스: SIL OFL 1.1(`OFL.txt`).
- Reserved Font Names: Nanum, Naver Nanum, NanumGothic, Naver NanumGothic,
  NanumMyeongjo, Naver NanumMyeongjo, NanumBrush, Naver NanumBrush,
  NanumPen, Naver NanumPen.
- 출처: Google Fonts, https://github.com/google/fonts/tree/main/ofl/nanumgothic.
  같은 패밀리를 Naver가 https://hangeul.naver.com/font 에서 배포하며,
  공유마당(gongu.copyright.or.kr)에 OFL로 올라 있다.

## 픽셀 페이스 (키잉 8비트 텍스트)

픽셀 폰트는 설계 크기이거나 그 정수배일 때만 선명하다.

| 폴더 | 파일 | 크기 | 설계 크기 | 권장 용도 |
|---|---|---|---|---|
| `galmuri/` | Galmuri7.ttf, Galmuri9.ttf, Galmuri11-Bold.ttf, LICENSE.txt | 3.7 + 4.6 + 2.6 MB | 8 / 10 / 12 px | Full Throttle의 12 px 셀에는 Galmuri9를 1배율 키잉으로. 10 px 셀에는 Galmuri7. 16 px 셀에는 Galmuri11 Bold. |
| `neodgm/` | neodgm.ttf, LICENSE.txt | 0.6 MB | 16 px | 2배율로 키잉하는 SCUMM v5/v6 텍스트를 16 px로 고정(`[font.N] size=16`)해서 사용. DOS 시절의 한글 느낌이 난다. |

**Galmuri** (갈무리) v2.40.4
- Copyright (c) 2019-2025 Lee Minseo (quiple).
- 라이선스: SIL OFL 1.1(`LICENSE.txt`). Reserved Font Name 없음.
- 출처: GitHub 릴리스 https://github.com/quiple/galmuri/releases/tag/v2.40.4
  (사이트: https://galmuri.quiple.dev).
- 크기를 줄이기 위해 포함하지 않은 것:
  - Galmuri11 Regular (5.4 MB);
  - Galmuri14;
  - Mono 컷;
  - strike만 있고 스케일할 수 없는 `*Bitmap-*.ttf` 빌드.

  게임에 필요하면 릴리스에서 받아 쓴다.

**Neo둥근모** (NeoDunggeunmo) v1.601
- Copyright (c) 2017-2021 Eunbin Jeong (Dalgona.). name 테이블에는 다음과 같이 적혀 있다:
  "Original font was released under the public domain by Jungtae Kim in
  1990s. Conversion and additional character design by Dalgona."
- 라이선스: SIL OFL 1.1(`LICENSE.txt`).
- Reserved Font Names: "Neo둥근모", "Neo둥근모 Code", "NeoDunggeunmo",
  "NeoDunggeunmo Code". 서브셋이나 구워 낸 사본은 이름을 바꿔야 한다.
- 출처: GitHub 릴리스 https://github.com/neodgm/neodgm/releases/tag/v1.601
  (사이트: https://neodgm.dalgona.dev).

## 스타일 페이스 (문자셋별 디스플레이, 세리프, 손글씨)

| 폴더 | 파일 | 크기 | 권장 용도 |
|---|---|---|---|
| `blackhansans/` | BlackHanSans-Regular.ttf, OFL.txt | 1.0 MB | 굵은 한글 디스플레이 페이스. 굵은 세리프 챕터 카드와 크레딧(MI1/MI2/Loom 문자셋 4)에 사용한다. 음절은 2581자(KS X 1001의 2350자 전부와 231자 추가)이며 11172자 전체는 아니므로, 뒤에 전체를 지원하는 페이스를 연결한다. |
| `coustard/` | Coustard-Black.ttf, OFL.txt | 0.1 MB | 라틴 굵은 세리프 디스플레이 페이스(Cooper/Clarendon 계열). Black Han Sans 옆에 `latin_font`로 사용한다. |
| `nanummyeongjo/` | NanumMyeongjo-Bold.ttf, OFL.txt | 3.1 MB | 한글 세리프(명조). MI1/MI2 동사(문자셋 6)처럼 가벼운 세리프 문자셋에 사용한다. 음절 11172자를 모두 담는다. |
| `gowunbatang/` | GowunBatang-Bold.ttf, OFL.txt | 8.2 MB | 나눔명조보다 획이 굵고 둥근 한글 세리프(바탕)이며 자체 라틴을 가진다. King's Quest I 한글판의 대화 및 제목 폰트(`../maps/kq1-ko.map`). 음절 11172자를 모두 담는다. |
| `ebgaramond/` | EBGaramond-VF.ttf, OFL.txt | 0.8 MB | 라틴 올드스타일 세리프. 나눔명조 옆에 `latin_font`로 사용한다. |
| `nanumpenscript/` | NanumPenScript-Regular.ttf, OFL.txt | 3.2 MB | 공책과 메모 같은 한글 손글씨(예: Blackwell). 음절 11172자를 모두 담는다. |
| `caveat/` | Caveat-VF.ttf, OFL.txt | 0.4 MB | 라틴 손글씨. 나눔손글씨 펜 앞에 오는 라틴 페이스로 사용한다. |

가변 폰트(EB Garamond: 웨이트 축 400-800, Caveat: 400-700)는
기본 인스턴스인 Regular 400으로 열린다. 맵에는 웨이트 키가 없으므로 이들의 굵은
인스턴스는 선택할 수 없다.

**Black Han Sans** (검은고딕)
- Copyright 2015 The Black Han Sans Project Authors. 디자인: Zess Type (name 테이블: ZESSTYPE).
- 라이선스: OFL 1.1. Reserved Font Name 없음.
- 상류: https://github.com/zesstype/Black-Han-Sans.
- 출처: Google Fonts, `ofl/blackhansans`.

**Coustard**
- Copyright 2011 The Coustard Project Authors. 디자인: Vernon Adams.
  (name 테이블의 저작권 URL은 googlefonts/bangers를 가리키는데,
  이 상류의 실수는 그대로 둔다.)
- 라이선스: OFL 1.1. Reserved Font Name 없음.
- 상류: https://github.com/googlefonts/coustardFont.
- 출처: Google Fonts, `ofl/coustard`.

**Nanum Myeongjo** (나눔명조)
- Copyright © 2010 NHN Corporation. All rights reserved. Font designed by
  FONTRIX (name 테이블; `OFL.txt`: "Copyright (c) 2010, NHN Corporation").
- 디자이너(name 테이블): Yong-rak Park, Ji-hee Yoon.
- 라이선스: OFL 1.1, NanumGothic 항목에 나열한 Nanum Reserved Font Names 포함.
- 출처: Google Fonts, `ofl/nanummyeongjo`.

**Gowun Batang** (고운바탕) Bold
- Copyright 2021 The Gowun Batang Project Authors
  (https://github.com/yangheeryu/Gowun-Batang), `OFL.txt`에 따름.
- 디자이너(Google Fonts METADATA.pb): Yanghee Ryu.
- 라이선스: OFL 1.1. Reserved Font Name 없음.
- 상류: https://github.com/yangheeryu/Gowun-Batang (커밋 4e73f5a9a0).
- 출처: Google Fonts, `ofl/gowunbatang`. Bold 컷만 배포한다.

**EB Garamond**
- Copyright 2017 The EB Garamond Project Authors. 디자인: Georg Duffner, Octavio Pardo.
- 라이선스: OFL 1.1. Reserved Font Name 없음.
- 상류: https://github.com/octaviopardo/EBGaramond12.
- 출처: Google Fonts, `ofl/ebgaramond`. 상류 파일 이름: `EBGaramond[wght].ttf`.

**Nanum Pen Script** (나눔손글씨 펜)
- Copyright © 2010 NHN Corporation. All rights reserved. Font designed by
  Sandoll Communications Inc. (name 테이블).
- 디자이너(name 테이블): Doo-yul Kwak, Hyunghwan Choi, Nicolas Noh.
- 라이선스: OFL 1.1, Nanum Reserved Font Names 포함.
- 출처: Google Fonts, `ofl/nanumpenscript`.

**Caveat**
- Copyright 2014 The Caveat Project Authors. 디자인: Pablo Impallari (Impallari Type).
- 라이선스: OFL 1.1. Reserved Font Name 없음.
- 상류: https://github.com/googlefonts/caveat.
- 출처: Google Fonts, `ofl/caveat`. 상류 파일 이름: `Caveat[wght].ttf`.

## 배포하지 않는 것

- **HBIOS-SYS**: 5.7 MB. 라틴과 상자 그리기 glyph은 CC BY-SA 4.0(VileR, int10h.org)이고
  나머지는 OFL이다. 라이선스가 섞여 있어 별도의
  표시와 동일조건변경허락 조건이 필요하다. Neo둥근모가 같은 용도를 대신한다.
