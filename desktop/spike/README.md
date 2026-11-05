# Desktop design spike: the measurements behind `docs/superpowers/specs/2026-11-05-maker-desktop-design.md`

Throw-away probes, kept so the numbers in the design can be re-run. Nothing here is the product: `sidecar_spike.py`
is not `maker/sidecar.py` (it carries a `-P path.py` shim the design rejects), the Electron probes are not the shell.
Everything ran on 2026-11-05 on Ubuntu 24.04 x86_64 (glibc 2.39), Python 3.12.3, node v22.23.4, npm 12.0.2, from the
checkout `W=/home/thkim/work/svf-fonts-open-wt/desktop` at `1513dd2` (the code the spike exercises is unchanged by
the later lifecycle commits). Outputs are quoted as printed; sizes are `du -sh`.

## 1. Tools

    python3 -m venv x                       # fails here: "ensurepip is not available" (python3-venv not installed)
    python3 -m pip install --target /tmp/pyi-probe/site pyinstaller     # PyInstaller 6.22.3
    mkdir /tmp/el-probe && cd /tmp/el-probe && npm init -y && npm install --no-audit --no-fund electron electron-builder
    # "added 283 packages in 3s"; electron 45.2.3, electron-builder 26.18.0; npm 12 blocked electron's postinstall:
    node node_modules/electron/install.js    # fetches the 275 MB dist into ~/.cache/electron (119 MB zip)
    node_modules/.bin/electron --version      # without a display: "exited with signal SIGTRAP"
    xvfb-run -a node_modules/.bin/electron --no-sandbox --version       # works

## 2. Frozen sidecar (PyInstaller one-dir)

First build (every tool as a hidden import, `--collect-submodules fontTools`, no excludes): 113 MB, and it **fails at
start** with `pyi_rth_pkgres ... ImportError: The 'jaraco' package is required` (Debian's setuptools `pkg_resources`,
pulled in through `fontTools.ui` -> wx). The lean build:

    cd /tmp/pyi-probe && PYTHONPATH=/tmp/pyi-probe/site python3 -m PyInstaller --noconfirm --onedir \
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

`maker/static/wasm/` was built first with `bash maker/build-wasm.sh` ("svf.wasm 39808 bytes, svf.js 6937 bytes", 1.3 s).

    S=/tmp/pyi-probe/dist2/sidecar-lean/sidecar-lean; mkdir -p emptybin evil; echo 'raise SystemExit("SHADOWED")' > evil/json.py
    env -i PATH=/tmp/pyi-probe/emptybin HOME=$HOME LANG=C.UTF-8 PYTHONPATH=/tmp/pyi-probe/evil $S --probe
    # frozen True; path [_internal/base_library.zip, _internal/python3.12/lib-dynload, _internal]
    # flags isolated=1 ignore_environment=1 no_site=1 safe_path=True dont_write_bytecode=1
    # env keys: HOME LANG LD_LIBRARY_PATH PATH PYTHONPATH _PYI_ARCHIVE_FILE _PYI_LINUX_PROCESS_NAME _PYI_PARENT_PROCESS_LEVEL
    (cd evil && env -i PATH=/tmp/pyi-probe/emptybin HOME=$HOME LANG=C.UTF-8 $S --probe)   # cwd not on sys.path
    for i in 1 2 3; do /usr/bin/time -f "%e s" env -i PATH=/tmp/pyi-probe/emptybin HOME=$HOME LANG=C.UTF-8 $S run-tool svfline --help >/dev/null; done
    # 0.03 s x3; run-tool mkfont --help 0.05 s; python3 -P tools/mkfont.py --help 0.05 s
    env -i PATH=/tmp/pyi-probe/emptybin HOME=$HOME LANG=C.UTF-8 $S run-tool mkfont $W/ttf/neodgm/neodgm.ttf F16.SVF --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    python3 -P $W/tools/mkfont.py $W/ttf/neodgm/neodgm.ttf S16.SVF --size 16 --bpp 1 --unicode ascii,ksx1001-hangul
    cmp F16.SVF S16.SVF && echo identical          # identical, 115,460 bytes; frozen 0.30-0.34 s, source 0.24 s
    $S run-tool srcprep --help; $S run-tool instancer --help; $S run-tool jamoset --help; $S run-tool macfbit_svf --help
    # "usage: srcprep.py", "usage: fonttools varLib.instancer", "usage: jamoset.py", "usage: macfbit_svf.py"; run-tool nosuch -> exit 2

PYZ contents of the lean build (`build2/sidecar-lean/PYZ-00.toc`) hold every module `import_graph.py` lists as
reachable (28), plus `facecheck` and `recog_score` (hidden imports); `jamofill`, `jamomerge`, `jamoseg`, `jamoexc`,
`fontmetrics` are absent (never reached); `fontTools.varLib.instancer`, `fontTools.ttLib.tables._c_m_a_p`,
`fontTools.pens.areaPen`, `PIL.ImageFont` present.

## 3. The frozen server end to end

    TOK=$(python3 -c "import secrets; print(secrets.token_hex(16))")
    env -i PATH=/tmp/pyi-probe/emptybin HOME=$HOME LANG=C.UTF-8 SVF_MAKER_REPO=$W SVF_MAKER_DATA=/tmp/pyi-probe/data \
        SVF_MAKER_BIND=127.0.0.1:0 SVF_MAKER_TOKEN=$TOK $S serve &
    # "svf-maker listening on 127.0.0.1:38253"; one process (ps: no re-exec parent)
    curl -s -o /dev/null -w "%{http_code} %{size_download}\n" http://127.0.0.1:$PORT/           # 200 9222
    curl -s -o /dev/null -w "%{http_code} %{content_type}\n" http://127.0.0.1:$PORT/static/wasm/svf.wasm   # 200 application/wasm
    curl -s http://127.0.0.1:$PORT/api/caps                                  # 403 {"error": "missing or wrong token"}
    curl -s -H "X-Maker-Token: $TOK" http://127.0.0.1:$PORT/api/caps         # {"wasm": true, "mask_libs": false, "recog": false, "local": true}
    mkdir srcdir jobout && cp $W/ttf/neodgm/neodgm.ttf srcdir/
    python3 -I $W/desktop/spike/client.py $PORT $TOK /tmp/pyi-probe/srcdir /tmp/pyi-probe/jobout
    # font: TTF; conjoining jamo (GSUB) outline-composite / probe: 200 / state: done None in 0.7 s
    # step s01 precomposed done 0 [[<sidecar>, '-P', '<W>/tools/mkfont.py']]   (the spike's shim; the design uses run-tool)
    # files: svf/dos/NEODU16.SVF svf/dos/NEODU.TXT build-<id>/{BUILD.md,FACES.TSV.lines,LICENCES.tsv.lines,FAMILIES.tsv.lines}
    # face GET: 200 115460; the note line: "python3 -P tools/mkfont.py neodgm.ttf NEODU16.SVF --size 16 --bpp 1 --unicode ascii,ksx1001-hangul --report report.json"
    cmp jobout/svf/dos/NEODU16.SVF S16.SVF    # identical
    # GET preview/<font>/source.png -> 200, 521-byte PNG (Pillow + its FreeType binding work in the bundle)
    kill -TERM $PID                          # exited after ~200 ms; no .svf-maker-<id>/ left in jobout

    node $W/desktop/spike/spawn-probe.mjs $S $W /tmp/pyi-probe/data2
    # port 42373 after 96 ms; caps 200 {...}; exit 0 null after 16 ms   (SIGTERM to the group of a detached child)

## 4. Electron probes (xvfb)

    cd /tmp/el-probe && xvfb-run -a node_modules/.bin/electron --no-sandbox $W/desktop/spike/electron-header-probe.js
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

    cp -r $W/desktop/spike/appimage-probe /tmp/el-probe/app && cd /tmp/el-probe/app   # adjust extraResources "from" paths
    ../node_modules/.bin/electron-builder --linux AppImage --publish never --config.electronVersion=45.2.3
    # bare app: real 0m6.853s, downloads appimage-12.0.1.7z + 7zip-linux-x64.tar.gz (GitHub) into ~/.cache/electron-builder
    # -> out/svf-maker-probe-0.0.1.AppImage 125,839,701 bytes
    # with extraResources (sidecar 47M + svf 12M + web): real 0m6.110s -> 150,621,923 bytes; linux-unpacked 334M
    ./out/x.AppImage                 # no FUSE here: "...run it with the --appimage-extract option"
    ./out/x.AppImage --appimage-extract && xvfb-run -a ./squashfs-root/AppRun          # "probe ok"
    grep -n "no-sandbox\|unshare" squashfs-root/AppRun; grep Exec squashfs-root/*.desktop
    # AppRun: 'if ! unshare -Ur true; then NO_SANDBOX=(--no-sandbox)'; .desktop: "Exec=AppRun --no-sandbox %U"
    xvfb-run -a ./squashfs-root/svf-maker-probe app2    # the binary without the flag:
    # FATAL ... The SUID sandbox helper binary was found, but is not configured correctly ... chrome-sandbox ... mode 4755
    node $W/desktop/spike/spawn-probe.mjs squashfs-root/resources/sidecar/sidecar-lean squashfs-root/resources/repo /tmp/d3
    # port 33523 after 145 ms; caps 200; exit 0 after 17 ms

## 6. Pillow: PyPI wheel against Debian's package

    python3 -m pip install --target /tmp/pyi-probe/wheel-site pillow==10.2.0
    # pillow.libs: libfreetype-f154df84.so.6.20.1 libharfbuzz-2093a78b.so.0.60830.0 libjpeg libtiff libwebp libopenjp2 liblcms2 libpng16 ...
    # both: freetype 2.13.2, raqm 0.10.1
    # mkfont neodgm.ttf 16 px 1 bpp: 115,460 bytes, cmp identical; NanumGothic-Bold.ttf 17 px 2 bpp: 207,684 bytes, cmp identical

## 7. Import graph

    python3 desktop/spike/import_graph.py
    # reachable (28): archive bdfface caps detect jamoaa jamoadapt jamofit jamoset jamovec jobs johab844 macfbit3 macfbit_svf
    #   macsfnt mkfont naming presets preview quality routes server settings sources srcprep svf2to3 svfdy svfline zipout
    # third-party: PIL fontTools freetype uharfbuzz        (freetype/uharfbuzz: optional, inside try/except in jamofit)
    # never reached: facecheck fontmetrics jamoexc jamofill jamomerge jamoseg recog_score svf_synth vesa_lines
