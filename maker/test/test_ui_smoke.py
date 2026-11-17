#!/usr/bin/env python3
"""The upload page driven once in headless Chrome (t_e073891a): a zip put into the `#files` input, `#upload`, the batch
controls, `#save`, `#run`, the drawn result canvas, the `#download` link; the downloaded zip passes facecheck. This is the
path of `maker/server.py` on loopback in a browser. Skipped without Chrome, node or the built preview module.

  flock $HOME/work/tmp/svf-browser.lock ~/.local/bin/heavy python3 -m unittest discover -s maker/test -p test_ui_smoke.py
"""

import os, sys
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (TEST_DIR, MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import json
import shutil
import signal
import subprocess
import tempfile
import unittest

import e2efx
import inputkinds
import jamoset
from test_page_dom import browser

DRIVER = os.path.join(TEST_DIR, "pagedrive.mjs")
PAGE_S = 90          # the page script's one deadline for every step
WATCHDOG_S = 120     # the driver kills Chrome after this
KILL_S = 140         # Python kills the driver's process group after this (the test's budget is 150 s)

PAGE_SCRIPT = r"""
const deadline = Date.now() + %(page_ms)d;
const left = () => Math.max(1000, deadline - Date.now());
const $ = (id) => document.getElementById(id);
const fire = (node) => { node.dispatchEvent(new Event('input', {bubbles: true})); node.dispatchEvent(new Event('change', {bubbles: true})); };

// 1. the zip is already in #files (pagedrive --files): upload it
if (!$('files').files.length) throw new Error('no file in #files');
$('upload').click();
await waitFor(() => document.querySelector('#fonts tr[data-font]'), left());
if ($('ack') && !$('ack').hidden) $('ack-ok').click();

// 2. the job and its outline font
const id = new URLSearchParams(location.search).get('job');
if (!id) throw new Error('no job in the page address');
const job = await (await fetch('/api/jobs/' + id)).json();
const outline = job.fonts.filter((f) => f.source_kind === 'outline');
if (outline.length !== 1) throw new Error('outline fonts: ' + outline.length);
const fid = outline[0].id;

// 3. the controls: tick the font, 1 bpp only, size 20
const row = document.querySelector('#fonts tr[data-font="' + fid + '"]');
const tick = row.querySelector('input.selected');
if (!tick.checked) { tick.checked = true; fire(tick); }
const bpp = $('bpp');
const two = bpp.querySelector('input[value="2"]'), one = bpp.querySelector('input[value="1"]');
if (two.checked) { two.checked = false; fire(two); }
if (!one.checked) { one.checked = true; fire(one); }
$('sizes').value = '20'; fire($('sizes'));

// 4. save: the server holds the settings
$('save').click();
await waitFor(async () => {
  const s = (await (await fetch('/api/jobs/' + id)).json()).settings;
  return JSON.stringify(s.batch.bpp) === '[1]' && JSON.stringify(s.batch.sizes) === '[20]';
}, left());

// 5. run: done, and the result canvas drawn
$('run').click();
await waitFor(() => $('state').textContent.includes('done'), left());
await waitFor(() => document.querySelector('canvas[data-step][data-drawn="1"]'), left());

// 6. the download link
await waitFor(() => !$('download').hidden, left());
const r = await fetch($('download').href);
const bytes = new Uint8Array(await r.arrayBuffer());
return {job: id, status: r.status, magic: Array.from(bytes.slice(0, 4))};
"""


class UploadPageSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chrome = browser()
        if not cls.chrome or not shutil.which("node"):
            raise unittest.SkipTest("no headless Chrome or node: the page is not driven")
        if not os.path.isfile(os.path.join(MAKER_DIR, "static", "wasm", "svf.wasm")):
            r = subprocess.run(["bash", os.path.join(MAKER_DIR, "build-wasm.sh")], capture_output=True, text=True)
            if r.returncode != 0:
                raise unittest.SkipTest("the preview module is not built and emcc is missing")
        cls.tmp = os.path.realpath(tempfile.mkdtemp(prefix="e2e-smoke-"))
        cls.server = None
        try:
            src = os.path.join(cls.tmp, "src", "nanum")
            os.makedirs(src)
            for name, rel in (("NanumGothic-Bold.ttf", "NanumGothic-Bold.ttf"), ("OFL.txt", "OFL.txt")):
                shutil.copyfile(os.path.join(REPO_DIR, "ttf", "nanumgothic", name), os.path.join(src, rel))
            cls.zip_in = os.path.join(cls.tmp, "smoke.zip")
            with open(cls.zip_in, "wb") as fh:
                fh.write(e2efx.zip_tree(os.path.join(cls.tmp, "src")))
            cls.server = e2efx.Server(os.path.join(cls.tmp, "data"))
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "server", None):
            cls.server.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def drive(self):
        script = os.path.join(self.tmp, "page.js")
        with open(script, "w") as fh:
            fh.write(PAGE_SCRIPT % {"page_ms": PAGE_S * 1000})
        env = dict(os.environ, PAGEDRIVE_WATCHDOG_S=str(WATCHDOG_S))
        proc = subprocess.Popen(["node", DRIVER, self.chrome, "http://127.0.0.1:%d/" % self.server.port, script,
                                 "--files", "#files=" + self.zip_in],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True, env=env)
        try:
            stdout, stderr = proc.communicate(timeout=KILL_S)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            self.fail("the page driver timed out after %d s" % KILL_S)
        self.assertEqual(proc.returncode, 0, stderr)
        return json.loads(stdout)

    def test_upload_run_download_in_the_page(self):
        out = self.drive()
        self.assertEqual((out["status"], out["magic"]), (200, [0x50, 0x4B, 0x03, 0x04]))
        status, _h, data = self.server.call("GET", "/api/jobs/%s/zip" % out["job"])
        self.assertEqual(status, 200)
        zpath = os.path.join(self.tmp, "page.zip")
        with open(zpath, "wb") as f:
            f.write(data)
        inputkinds.assert_facecheck(self, zpath)
        faces = inputkinds.zip_faces(zpath)
        self.assertEqual(len(faces), 1)
        face = jamoset.parse_svfn(next(iter(faces.values())))
        self.assertEqual((face.bpp, face.cell_h), (1, 20))


if __name__ == "__main__":
    unittest.main()
