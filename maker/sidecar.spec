# -*- mode: python -*-
# maker/sidecar.spec: pyinstaller maker/sidecar.spec (from the checkout root; maker/build-sidecar.sh runs it).
import os
import sys
from PyInstaller.utils.hooks import collect_submodules
ROOT = os.path.abspath(SPECPATH + "/..")
# fontTools loads table classes by name at run time: the lists must be COMPUTED BEFORE Analysis() and passed to it
# (mutating a.hiddenimports afterwards does nothing: the graph is already built).
HIDDEN = (["fontTools.varLib.instancer"] + collect_submodules("fontTools.ttLib")
          + collect_submodules("fontTools.pens") + collect_submodules("fontTools.varLib"))
a = Analysis([os.path.join(ROOT, "maker", "sidecar.py")],
             pathex=[os.path.join(ROOT, "maker"), os.path.join(ROOT, "tools")],
             datas=[(os.path.join(ROOT, "maker", "static"), "static"),        # index.html, *.js, style.css, wasm/
                    (os.path.join(ROOT, "maker", "recipes"), "recipes")],     # the built-in recipes (recipe.builtin_dir)
             hiddenimports=HIDDEN,
             hookspath=[], runtime_hooks=[],
             excludes=["wx", "fontTools.ui", "brotli", "_brotli", "zopfli", "lxml", "unicodedata2", "lz4", "numpy",
                       "torch", "scipy", "matplotlib", "sympy", "tkinter", "gi", "PIL.ImageQt", "PIL.ImageTk",
                       "xattr", "pkg_resources", "setuptools", "jaraco", "freetype", "uharfbuzz", "pathops",
                       "readline", "curses", "_curses", "test", "unittest.mock"],
             noarchive=False)
pyz = PYZ(a.pure)
if sys.platform == "win32":
    # Windows (t_9b8f56f0): UTF-8 mode, so a tool's stdout and stderr are UTF-8 as under LANG=C.UTF-8 (a frozen program
    # ignores PYTHONUTF8); the icon from desktop/build/make-icon.py --ico when the build made it
    ICO = os.path.join(ROOT, "desktop", "build", "out", "icon.ico")
    exe = EXE(pyz, a.scripts, [("X utf8_mode=1", None, "OPTION")], exclude_binaries=True, name="svf-maker-sidecar",
              console=True, upx=False, strip=False, icon=ICO if os.path.isfile(ICO) else None)
else:
    exe = EXE(pyz, a.scripts, exclude_binaries=True, name="svf-maker-sidecar", console=True, upx=False,
              strip=False)                               # strip/upx: off (reproducibility, antivirus; spec 8.10)
coll = COLLECT(exe, a.binaries, a.datas, name="svf-maker-sidecar")
