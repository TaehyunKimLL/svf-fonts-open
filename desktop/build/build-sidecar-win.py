#!/usr/bin/env python3
"""build-sidecar-win.py [--no-test]: the Windows counterpart of maker/build-sidecar.sh (t_9b8f56f0), run from any
directory on a Windows host with Python 3.12 (python.org or actions/setup-python) and git.

Steps, as build-sidecar.sh takes them:
  1. the WASM preview module must already be built (maker/static/wasm/svf.js + svf.wasm; emcc does not run here: the
     Windows workflow builds it on Linux with maker/build-wasm.sh and hands it over);
  2. the pinned win_amd64 wheels (desktop/build/requirements-win.lock, `pip install --target`, hashes required);
  3. desktop/build/out/icon.ico from desktop/build/icon.png (make-icon.py --ico), and the pinned FriBiDi DLL
     (fetch-fribidi-win.py: Pillow's raqm layout needs it; the spec bundles it), checked by loading raqm with the
     pinned Pillow;
  4. the PyInstaller one-dir bundle into desktop/build/out/sidecar/ (`python -S`, PYTHONPATH = the wheels only;
     SOURCE_DATE_EPOCH = the last commit's time);
  5. the build-time provenance of every collected binary (sidecar-provenance.py);
  6. the staged repo tree desktop/build/out/repo/ (svf/, web/ index files, tools/*.py and maker/*.py without tests,
     BUILD_ID);
  7. a selfcheck under a minimal environment (SYSTEMROOT only: the Windows `env -i`);
  8. unless --no-test, the frozen test (maker/test/test_frozen.py, SVF_MAKER_FROZEN_REQUIRED=1: no skip allowed).

SVF_DESKTOP_TMP (default %USERPROFILE%\\work\\tmp\\svf-desktop-build) holds the wheels and PyInstaller's work directory.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "desktop", "build", "out")
LOCK = os.path.join(ROOT, "desktop", "build", "requirements-win.lock")


def run(argv, **kwargs):
    print("+ " + " ".join(argv), flush=True)
    subprocess.run(argv, check=True, **kwargs)


def git(*args):
    return subprocess.run(["git", "-C", ROOT] + list(args), check=True, capture_output=True, text=True).stdout.strip()


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main(argv):
    if sys.platform != "win32":
        print("build-sidecar-win.py: Windows only (maker/build-sidecar.sh builds the Linux sidecar)", file=sys.stderr)
        return 2
    no_test = argv == ["--no-test"]
    if argv and not no_test:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    started = time.monotonic()
    tmp = os.environ.get("SVF_DESKTOP_TMP") or os.path.join(os.path.expanduser("~"), "work", "tmp", "svf-desktop-build")
    os.makedirs(tmp, exist_ok=True)
    tmp = os.path.abspath(tmp)

    wasm = os.path.join(ROOT, "maker", "static", "wasm")
    for name in ("svf.js", "svf.wasm"):
        if not os.path.isfile(os.path.join(wasm, name)):
            print("build-sidecar-win.py: %s is missing: build it with maker/build-wasm.sh (Linux or WSL) first"
                  % os.path.join(wasm, name), file=sys.stderr)
            return 1
        print("wasm %s %d bytes sha256 %s" % (name, os.path.getsize(os.path.join(wasm, name)), sha256(os.path.join(wasm, name))))

    pysite = os.path.join(tmp, "pysite")
    stamp = os.path.join(pysite, ".ok")
    want = sha256(LOCK)
    if not (os.path.isfile(stamp) and open(stamp, encoding="ascii").read().strip() == want):
        shutil.rmtree(pysite, ignore_errors=True)
        run([sys.executable, "-m", "pip", "install", "--target", pysite, "--require-hashes", "--only-binary=:all:",
             "--no-deps", "-r", LOCK])
        with open(stamp, "w", encoding="ascii") as f:
            f.write(want + "\n")

    os.makedirs(OUT, exist_ok=True)
    run([sys.executable, os.path.join(HERE, "make-icon.py"), "--ico", os.path.join(OUT, "icon.ico")])
    fribidi = os.path.join(tmp, "fribidi")
    run([sys.executable, os.path.join(HERE, "fetch-fribidi-win.py"), fribidi])
    probe = subprocess.run([sys.executable, "-S", "-c", "from PIL import features; import sys; "
                            "print('raqm', features.version('raqm'), 'fribidi', features.version('fribidi')); "
                            "sys.exit(0 if features.check('raqm') else 1)"],
                           env=dict(os.environ, PYTHONPATH=pysite, PATH=fribidi + os.pathsep + os.environ.get("PATH", "")),
                           capture_output=True, text=True)
    print(probe.stdout.strip() or probe.stderr.strip())
    if probe.returncode != 0:
        print("build-sidecar-win.py: the pinned Pillow does not load raqm with %s" % fribidi, file=sys.stderr)
        return 1

    env = dict(os.environ, SOURCE_DATE_EPOCH=git("log", "-1", "--format=%ct"), PYTHONPATH=pysite, TMP=tmp, TEMP=tmp,
               SVF_FRIBIDI_DIR=fribidi)
    work = os.path.join(tmp, "pyi-work")
    for path in (os.path.join(OUT, "sidecar"), work):
        shutil.rmtree(path, ignore_errors=True)
    run([sys.executable, "-S", "-m", "PyInstaller", "--noconfirm", "--clean", "--workpath", work, "--distpath",
         os.path.join(OUT, "sidecar"), os.path.join(ROOT, "maker", "sidecar.spec")], env=env, cwd=ROOT)

    run([sys.executable, os.path.join(HERE, "sidecar-provenance.py"), os.path.join(work, "sidecar"),
         os.path.join(OUT, "sidecar-provenance.json"), "--pysite", pysite, "--fetched", fribidi])

    repo = os.path.join(OUT, "repo")
    shutil.rmtree(repo, ignore_errors=True)
    for sub in ("web", "tools", "maker"):
        os.makedirs(os.path.join(repo, sub))
    shutil.copytree(os.path.join(ROOT, "svf"), os.path.join(repo, "svf"))
    for name in ("mkindex.py", "LICENCES.tsv", "FAMILIES.tsv"):
        shutil.copy2(os.path.join(ROOT, "web", name), os.path.join(repo, "web", name))
    for sub in ("tools", "maker"):
        for name in sorted(os.listdir(os.path.join(ROOT, sub))):
            if name.endswith(".py") and not name.startswith("test_"):
                shutil.copy2(os.path.join(ROOT, sub, name), os.path.join(repo, sub, name))
    version = None
    with open(os.path.join(ROOT, "maker", "sidecar.py"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("VERSION = \""):
                version = line.split("\"")[1]
                break
    with open(os.path.join(repo, "BUILD_ID"), "w", encoding="utf-8", newline="\n") as f:
        f.write("%s %s sidecar %s\n" % (git("describe", "--always", "--dirty"), git("log", "-1", "--format=%cs"), version))

    exe = os.path.join(OUT, "sidecar", "svf-maker-sidecar", "svf-maker-sidecar.exe")
    minimal = {"SYSTEMROOT": os.environ["SYSTEMROOT"]}
    out = subprocess.run([exe, "selfcheck"], env=minimal, capture_output=True, timeout=120)
    try:
        info = json.loads(out.stdout.decode("utf-8"))
    except ValueError:
        print(out.stdout.decode("utf-8", "replace") + out.stderr.decode("utf-8", "replace"), file=sys.stderr)
        return 1
    bad = {k: v for k, v in info["modules"].items() if v is not None}
    print("selfcheck: frozen=%s version=%s modules=%d bad=%s" % (info["frozen"], info["version"], len(info["modules"]), bad))
    if bad or not info["frozen"] or out.returncode != 0:
        return 1

    if not no_test:
        test_env = dict(os.environ, SVF_MAKER_SIDECAR=exe, SVF_MAKER_REF_SITE=pysite, SVF_MAKER_STAGED_REPO=repo,
                        SVF_MAKER_FROZEN_REQUIRED="1", SVF_FRIBIDI_DIR=fribidi)
        run([sys.executable, os.path.join(HERE, "run-suite.py"), os.path.join(ROOT, "maker", "test"), "test_frozen.py"],
            env=test_env, cwd=ROOT)
    size = sum(os.path.getsize(os.path.join(d, n)) for d, _, ns in os.walk(os.path.join(OUT, "sidecar")) for n in ns)
    print("build-sidecar-win: %d s, %d MB" % (time.monotonic() - started, size >> 20))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
