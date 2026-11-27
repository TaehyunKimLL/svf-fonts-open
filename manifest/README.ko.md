[English](README.md) | **한국어**

페이스 기준선(`svf/`에 대한 이후 변경의 인수 기준 데이터):

- baseline.tsv: `svf/` 아래 모든 `.SVF` 페이스(라이선스 노트, `*.TSV`, `*.md` 제외)의 sha256과 크기. 페이스당 한 행이며
  총 117행이다. 115행은 이 저장소가 공개하는 페이스에 대한, 원래 작업 저장소의 2026-10-21 SVFN v3 기준선
  (v3 변환 후 그곳에서 `facecheck.py manifest`로 작성)의 행이며, 해당 페이스들은
  그 뒤로 바뀌지 않았다. 117번째 행인 `svf/dos/NEODG16G.SVF`는 2026-11-03에 추가되었다(`tools/build/build_faces.py`로 만듦).

작업 트리를 기준선과 대조한다(저장소 루트에서 실행):

    python3 -I tools/facecheck.py verify manifest/baseline.tsv

모든 페이스가 존재하고 sha256이 같으면 종료 코드 0이며, 그렇지 않으면 MISSING / CHANGED 줄이 출력된다. 같은 표를 커밋에서 만들 수도 있다:

    python3 tools/facecheck.py manifest --git . --rev HEAD --path svf \
        --exclude '*.TXT' --exclude '*.txt' --exclude '*.TSV' --exclude '*.md' -o /tmp/check.tsv
    cmp /tmp/check.tsv manifest/baseline.tsv
