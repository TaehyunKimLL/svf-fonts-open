[English](README.md) | **한국어**

# 데스크톱 설계 스파이크: `docs/superpowers/specs/2026-11-05-maker-desktop-design.md`의 근거가 된 측정

일회용 프로브이며, 설계의 수치를 다시 실행해 볼 수 있도록 남겨 두었다. 여기 있는 것은 어느 것도 제품이 아니다. `sidecar_spike.py`는
`maker/sidecar.py`가 아니며(설계가 거부하는 `-P path.py` shim을 가지고 있다), Electron 프로브는 셸이 아니다.
모든 것은 2026-11-05에 Ubuntu 24.04 x86_64(glibc 2.39), Python 3.12.3, node v22.23.4, npm 12.0.2 환경에서,
체크아웃 `W=/home/thkim/work/svf-fonts-open-wt/desktop`의 `1513dd2`에서 실행했다(스파이크가 다루는 코드는 이후의
수명 주기 커밋들로 바뀌지 않았다). 출력은 찍힌 그대로 인용하며, 크기는 `du -sh`이다.

스크래치 규칙(프로젝트 규칙): 아래에서 `$TMP_DIR` 아래의 모든 경로는 스크래치이며, `/tmp`에 흩어 두지 않는다:

    export TMP_DIR=$HOME/work/tmp/svf-desktop-spike; mkdir -p "$TMP_DIR"
    echo "made by <agent> for the desktop spike: <purpose>; delete when done" > "$TMP_DIR/README"

## 1. 도구

    python3 -m venv x                       # fails here: "ensurepip is not available" (python3-venv not installed)
    python3 -m pip install --target $TMP_DIR/pyi-probe/site pyinstaller     # PyInstaller 6.22.3
    mkdir $TMP_DIR/el-probe && cd $TMP_DIR/el-probe && npm init -y && npm install --no-audit --no-fund electron electron-builder
    # "added 283 packages in 3s"; electron 45.2.3, electron-builder 26.18.0; npm 12 blocked electron's postinstall:
    node node_modules/electron/install.js    # fetches the 275 MB dist into ~/.cache/electron (119 MB zip)
    node_modules/.bin/electron --version      # without a display: "exited with signal SIGTRAP"
    xvfb-run -a node_modules/.bin/electron --no-sandbox --version       # works

## 2. 동결된 사이드카 (PyInstaller one-dir)

첫 빌드(모든 도구를 hidden import로, `--collect-submodules fontTools`, 제외 없음): 113 MB이며 **시작 시
실패**한다**: `pyi_rth_pkgres ... ImportError: The 'jaraco' package is required` (Debian의 setuptools `pkg_resources`가
`fontTools.ui` -> wx를 통해 끌려 들어온다). 경량 빌드:

    cd $TMP_DIR/pyi-probe && PYTHONPATH=$TMP_DIR/pyi-probe/site python3 -m PyInstaller --noconfirm --onedir \
      --name sidecar-lean --paths $W/maker --paths $W/tools \
      --workpath build2 --distpath dist2 --specpath spec2 \
      $(for t in jamoset jamovec mkfont macfbit_svf macfbit3 macsfnt bdfface johab844 svf2to3 svfdy svfline \
               facecheck srcprep recog_score server jamoaa jamofit jamoadapt detect jobs routes settings presets \
               naming preview quality zipout archive caps sources; do echo --hidden-import $t; done) \
      --collect-submodules fontTools.ttLib --collect-submodules fontTools.pens --hidden-import fontTools.varLib.instancer \
      --hidden-import fontTools.varLib \
      --exclude-module wx --exclude-module fontTools.ui --exclude-module brotli --exclude-module _brotli \
      --exclude-module zopfli --exclude-module lxml --exclude-module numpy --exclude-module torch --exclude-module tkinter \
      --exclude-module gi --exclude-module PIL.ImageQt --exclude-module PIL.ImageTk --exclude-module unicodedata2 \
      --exclude-module lz4 --exclude-module scipy --exclude-module matplotlib --exclude-module sympy --exclude-module xattr \
      --add-data "$W/maker/static:static" $W/desktop/spike/sidecar_spike.py
    # real 0m6.048s; du -sh dist2/sidecar-lean -> 47M (fontTools 11M, libpython3.12 8.7M, libcrypto 5.1M, PIL 0.6M, 40 .so)

`maker/static/wasm/`은 먼저 `bash maker/build-wasm.sh`로 빌드했다("svf.wasm 39808 bytes, svf.js 6937 bytes", 1.3 s).

    S=$TMP_DIR/pyi-probe/dist2/sidecar-lean/sidecar-lean; mkdir -p emptybin evil; echo 'raise SystemExit("SHADOWED")' > evil/json.py
    env -i PATH=$TMP_DIR/pyi-probe/emptybin HOME=$HOME LANG=C.UTF-8 PYTHONPATH=$TMP_DIR/pyi-probe/evil $S --probe
    # frozen True; path [_internal/base_library.zip, _internal/python3.12/lib-dynload, _internal]
    # flags isolated=1 ignore_environment=1 no_site=1 safe_path=True dont_write_bytecode=1
    # env keys: HOME LANG LD_LIBRARY_PATH PATH PYTHONPATH _PYI_ARCHIVE_FILE _PYI_LINUX_PROCESS_NAME _PYI_PARENT_PROCESS_LEVEL
    (cd evil && env -i PATH=$TMP_DIR/pyi-probe/emptybin HOME=$HOME LANG=C.UTF-8 $S --probe)   # cwd not on sys.path
    for i in 1 2 3; do /usr/bin/time -f "%e s" env -i PATH=$TMP_DIR/pyi-probe/emptybin HOME=$HOME LANG=C.UTF-8 $S run-tool svfline --help >/dev/null; done
    # 0.03 s x3; run-tool mkfont --help 0.05 s; python3 -P tools/mkfont.py --help 0.05 s
    env -i PATH=$TMP_DIR/pyi-probe/emptybin HOME=$HOME LANG=C.UTF-8 $S run-tool mkfont $W/ttf/neodgm/neodgm.ttf F16.SVF --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 -P $W/tools/mkfont.py $W/ttf/neodgm/neodgm.ttf S16.SVF --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    cmp F16.SVF S16.SVF && echo identical          # identical, 115,460 bytes; frozen 0.30-0.34 s, source 0.24 s
    $S run-tool srcprep --help; $S run-tool instancer --help; $S run-tool jamoset --help; $S run-tool macfbit_svf --help
    # "usage: srcprep.py", "usage: fonttools varLib.instancer", "usage: jamoset.py", "usage: macfbit_svf.py"; run-tool nosuch -> exit 2

경량 빌드의 PYZ 내용(`build2/sidecar-lean/PYZ-00.toc`)에는 `import_graph.py`가 도달 가능하다고 나열하는 모든 모듈(28개)과
`facecheck`, `recog_score`(hidden import)가 들어 있다. `jamofill`, `jamomerge`, `jamoseg`, `jamoexc`,
`fontmetrics`는 없다(도달하지 않음). `fontTools.varLib.instancer`, `fontTools.ttLib.tables._c_m_a_p`,
`fontTools.pens.areaPen`, `PIL.ImageFont`는 있다.

## 3. 동결된 서버의 종단 간 동작

    TOK=$(python3 -c "import secrets; print(secrets.token_hex(16))")
    env -i PATH=$TMP_DIR/pyi-probe/emptybin HOME=$HOME LANG=C.UTF-8 SVF_MAKER_REPO=$W SVF_MAKER_DATA=$TMP_DIR/pyi-probe/data \
        SVF_MAKER_BIND=127.0.0.1:0 SVF_MAKER_TOKEN=$TOK $S serve &
    # "svf-maker listening on 127.0.0.1:38253"; one process (ps: no re-exec parent)
    curl -s -o /dev/null -w "%{http_code} %{size_download}\n" http://127.0.0.1:$PORT/           # 200 9222
    curl -s -o /dev/null -w "%{http_code} %{content_type}\n" http://127.0.0.1:$PORT/static/wasm/svf.wasm   # 200 application/wasm
    curl -s http://127.0.0.1:$PORT/api/caps                                  # 403 {"error": "missing or wrong token"}
    curl -s -H "X-Maker-Token: $TOK" http://127.0.0.1:$PORT/api/caps         # {"wasm": true, "mask_libs": false, "recog": false, "local": true}
    mkdir srcdir jobout && cp $W/ttf/neodgm/neodgm.ttf srcdir/
    python3 -I $W/desktop/spike/client.py $PORT $TOK $TMP_DIR/pyi-probe/srcdir $TMP_DIR/pyi-probe/jobout
    # font: TTF; conjoining jamo (GSUB) outline-composite / probe: 200 / state: done None in 0.7 s
    # step s01 precomposed done 0 [[<sidecar>, '-P', '<W>/tools/mkfont.py']]   (the spike's shim; the design uses run-tool)
    # files: svf/dos/NEODU16.SVF svf/dos/NEODU.TXT build-<id>/{BUILD.md,FACES.TSV.lines,LICENCES.tsv.lines,FAMILIES.tsv.lines}
    # face GET: 200 115460; the note line: "python3 -P tools/mkfont.py neodgm.ttf NEODU16.SVF --size 16 --bpp 1 --unicode ascii,ksx1001-hangul --report report.json"
    cmp jobout/svf/dos/NEODU16.SVF S16.SVF    # identical
    # GET preview/<font>/source.png -> 200, 521-byte PNG (Pillow + its FreeType binding work in the bundle)
    kill -TERM $PID                          # exited after ~200 ms; no .svf-maker-<id>/ left in jobout

    node $W/desktop/spike/spawn-probe.mjs $S $W $TMP_DIR/pyi-probe/data2
    # port 42373 after 96 ms; caps 200 {...}; exit 0 null after 16 ms   (SIGTERM to the group of a detached child)

## 4. Electron 프로브 (xvfb)

    cd $TMP_DIR/el-probe && xvfb-run -a node_modules/.bin/electron --no-sandbox $W/desktop/spike/electron-header-probe.js
    # {"electron":"45.2.3","chrome":"156.0.8078.80","node":"24.22.2","apiStatus":200,
    #  "seen":[{"url":"/","tok":null},{"url":"/probe.js","tok":null},{"url":"/api/caps","tok":"deadbeef"}],
    #  "cancelled":[],"foreign":"rejected:Failed to fetch"}
    # (the foreign fetch is refused by the page's CSP before webRequest sees it: "cancelled" stays empty)

    xvfb-run -a node_modules/.bin/electron --no-sandbox $W/desktop/spike/sandbox-proc.js
    # SANDBOX {"noSandboxFlag":true,"metrics":[{"type":"Browser",...,"seccomp":"0","nonewprivs":"0","userns":"same"},
    #   {"type":"Utility",...,"seccomp":"0"},{"type":"Tab",...,"seccomp":"0","nonewprivs":"1","userns":"same"}]}
    xvfb-run -a node_modules/.bin/electron $W/desktop/spike/sandbox-proc.js       # without the flag: SIGTRAP
    # (app.getAppMetrics()[].sandboxed is Windows-only; the /proc fields are the Linux evidence)
    unshare -Ur true     # "unshare: write failed /proc/self/uid_map: Operation not permitted"
    cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns   # 1

## 5. AppImage (electron-builder)

    cp -r $W/desktop/spike/appimage-probe $TMP_DIR/el-probe/app && cd $TMP_DIR/el-probe/app   # adjust extraResources "from" paths
    ../node_modules/.bin/electron-builder --linux AppImage --publish never --config.electronVersion=45.2.3
    # bare app: real 0m6.853s, downloads appimage-12.0.1.7z + 7zip-linux-x64.tar.gz (GitHub) into ~/.cache/electron-builder
    # -> out/svf-maker-probe-0.0.1.AppImage 125,839,701 bytes
    # with extraResources (사이드카 47M + svf 12M + web): real 0m6.110s -> 150,621,923 bytes; linux-unpacked 334M
    ./out/x.AppImage                 # no FUSE here: "...run it with the --appimage-extract option"
    ./out/x.AppImage --appimage-extract && xvfb-run -a ./squashfs-root/AppRun          # "probe ok"
    grep -n "no-sandbox\|unshare" squashfs-root/AppRun; grep Exec squashfs-root/*.desktop
    # AppRun: 'if ! unshare -Ur true; then NO_SANDBOX=(--no-sandbox)'; .desktop: "Exec=AppRun --no-sandbox %U"
    xvfb-run -a ./squashfs-root/svf-maker-probe app2    # the binary without the flag:
    # FATAL ... The SUID sandbox helper binary was found, but is not configured correctly ... chrome-sandbox ... mode 4755
    node $W/desktop/spike/spawn-probe.mjs squashfs-root/resources/sidecar/sidecar-lean squashfs-root/resources/repo $TMP_DIR/d3
    # port 33523 after 145 ms; caps 200; exit 0 after 17 ms

## 6. Pillow: PyPI wheel과 Debian 패키지 비교

    python3 -m pip install --target $TMP_DIR/pyi-probe/wheel-site pillow==10.2.0
    # pillow.libs: libfreetype-f154df84.so.6.20.1 libharfbuzz-2093a78b.so.0.60830.0 libjpeg libtiff libwebp libopenjp2 liblcms2 libpng16 ...
    # both: freetype 2.13.2, raqm 0.10.1
    # mkfont neodgm.ttf 16 px 1 bpp: 115,460 bytes, cmp identical; NanumGothic-Bold.ttf 17 px 2 bpp: 207,684 bytes, cmp identical

## 7. 임포트 그래프

    python3 desktop/spike/import_graph.py
    # reachable (28): archive bdfface caps detect jamoaa jamoadapt jamofit jamoset jamovec jobs johab844 macfbit3 macfbit_svf
    #   macsfnt mkfont naming presets preview quality routes server settings sources srcprep svf2to3 svfdy svfline zipout
    # third-party: PIL fontTools freetype uharfbuzz        (freetype/uharfbuzz: optional, inside try/except in jamofit)
    # never reached: facecheck fontmetrics jamoexc jamofill jamomerge jamoseg recog_score svf_synth vesa_lines

