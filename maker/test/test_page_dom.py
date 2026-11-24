#!/usr/bin/env python3
"""The maker page in headless Chrome (driven over the DevTools protocol by pagedrive.mjs, node's WebSocket): the page
behaviours no Python test can see. Skipped without google-chrome / chromium-browser, node or the built module.

  python3 -m unittest discover -s maker/test -p test_page_dom.py
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from unittest import mock
import http.client

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, TEST_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fixtures  # noqa: E402
import inputfx  # noqa: E402
import jobs  # noqa: E402
import localfx  # noqa: E402
import server  # noqa: E402
import wincompat

DRIVER = os.path.join(TEST_DIR, "pagedrive.mjs")
WAIT_S = 240


def read_report(srv, job, step):
    with open(srv.store.path(job, step["report"]), encoding="utf-8") as f:
        return json.load(f)


def browser():
    """google-chrome or chromium-browser on PATH; SVF_TEST_CHROME names one anywhere; on Windows the standard Chrome
    install (no chrome on PATH there)."""
    if os.environ.get("SVF_TEST_CHROME") and os.path.isfile(os.environ["SVF_TEST_CHROME"]):
        return os.environ["SVF_TEST_CHROME"]
    found = next((shutil.which(n) for n in ("google-chrome", "chromium-browser") if shutil.which(n)), None)
    if found or os.name != "nt":
        return found
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        path = os.path.join(base or "", "Google", "Chrome", "Application", "chrome.exe")
        if base and os.path.isfile(path):
            return path
    return None


def read(path):
    with open(path, "rb") as f:
        return f.read()


class ReleaseOnWait(threading.Event):
    """A "run being prepared" marker that is released by its @p n-th `wait`: it pops itself from `preparing` and sets."""

    def __init__(self, n, preparing, job):
        super().__init__()
        self.n, self.calls, self.preparing, self.job = n, 0, preparing, job

    def wait(self, timeout=None):
        self.calls += 1
        if self.calls == self.n:
            self.preparing.pop(self.job, None)
            self.set()
        return super().wait(timeout)


class PageDomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chrome = browser()
        if not cls.chrome or not shutil.which("node"):
            raise unittest.SkipTest("no headless Chrome or node: the page is not driven")
        if not os.path.isfile(os.path.join(MAKER_DIR, "static", "wasm", "svf.wasm")):
            r = subprocess.run(["bash", os.path.join(MAKER_DIR, "build-wasm.sh")], capture_output=True, text=True)
            if r.returncode != 0:
                raise unittest.SkipTest("the preview module is not built and emcc is missing")
        sys.stderr.write("test_page_dom: %d threads in the test process at start\n" % threading.active_count())
        cls.tmp = tempfile.mkdtemp(prefix="svf-page-dom-")
        cls.fx = fixtures.write_fixtures(os.path.join(cls.tmp, "fx"))
        cls.srv = server.make_server("127.0.0.1", 0, REPO_DIR, os.path.join(cls.tmp, "data"))
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "srv", None):
            for item in cls.srv.store.list():
                while cls.srv.worker.cancel(item["id"]) != "not running":
                    time.sleep(0.05)
            cls.srv.shutdown()
            cls.srv.worker.stop()
            cls.srv.server_close()
            shutil.rmtree(cls.tmp, ignore_errors=True)

    # ---- helpers ----------------------------------------------------------------------------------------------

    def api(self, method, path, obj=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=WAIT_S)
        try:
            if obj is not None:
                body = json.dumps(obj).encode()
            conn.request(method, path, body=body)
            resp = conn.getresponse()
            data = resp.read()
            self.assertEqual(resp.status, 200, "%s %s: %s" % (method, path, data[:300]))
            return json.loads(data)
        finally:
            conn.close()

    def upload(self, job, rel, path):
        self.upload_bytes(job, rel, read(path))

    def upload_bytes(self, job, rel, data):
        self.api("PUT", "/api/jobs/%s/files?path=%s" % (job, urllib.parse.quote(rel, safe="")), body=data)

    def wait_done(self, job):
        deadline = time.monotonic() + WAIT_S
        while time.monotonic() < deadline:
            state = self.api("GET", "/api/jobs/" + job)
            if state["state"] in ("done", "failed"):
                return state
            time.sleep(0.2)
        self.fail("job did not finish")

    def dos_job(self, run, **extra):
        job = self.api("POST", "/api/jobs")["id"]
        self.upload(job, "dos/HAN.FNT", self.fx["dos_raw"])
        self.upload(job, "dos/ENG.FNT", self.fx["dos_eng"])
        detected = self.api("POST", "/api/jobs/%s/detect" % job)
        s = detected["settings"]
        for per in s["fonts"].values():
            if "dos_layout" in per:
                per["dos_layout"] = "844"
        self.api("PUT", "/api/jobs/%s/settings" % job, s)
        self.font = next(f["id"] for f in detected["fonts"] if f["path"].endswith("HAN.FNT"))
        if extra:
            s = self.api("GET", "/api/jobs/" + job)["settings"]
            s["fonts"][self.font].update(extra)
            self.api("PUT", "/api/jobs/%s/settings" % job, s)
        if run:
            s = self.api("GET", "/api/jobs/" + job)["settings"]
            s["fonts"][self.font].update(selected=True, dest="new/dom", licence={"kind": "text", "text": "OFL"},
                                         licence_name="OFL.TXT", note_name="NOTE.TXT")
            self.api("PUT", "/api/jobs/%s/settings" % job, s)
            self.api("POST", "/api/jobs/%s/run" % job)
            self.assertEqual(self.wait_done(job)["state"], "done")
        return job

    def drive(self, job, script, **env_extra):
        script = script.replace("FONTID", getattr(self, "font", ""))
        fd, path = tempfile.mkstemp(suffix=".js", dir=self.tmp)
        with os.fdopen(fd, "w") as f:
            f.write(script)
        # its own process group: a driver that overruns takes Chrome (and its ~100 tasks) down with it, so a hung page
        # cannot starve the rest of the suite of threads
        env = dict(os.environ, PAGEDRIVE_WATCHDOG_S=str(WAIT_S - 20))        # the driver's own limit comes first
        env.update(env_extra)
        proc = wincompat.popen_group(["node", DRIVER, self.chrome, "http://127.0.0.1:%d/?job=%s" % (self.port, job), path],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            stdout, stderr = proc.communicate(timeout=WAIT_S)
        except subprocess.TimeoutExpired:
            wincompat.kill_group(proc)
            proc.communicate()
            self.fail("the page driver timed out after %d s" % WAIT_S)
        self.assertEqual(proc.returncode, 0, stderr)
        return json.loads(stdout)

    # ---- tests ------------------------------------------------------------------------------------------------

    @wincompat.posix_only("the Unix socket path limit of Chrome's singleton (107 bytes); Windows has no such socket")
    def test_driver_starts_chrome_with_a_long_tmpdir(self):
        """Chrome's singleton socket path must stay under 107 bytes whatever TMPDIR is (the TMP_DIR project rule); the
        short profile goes under $HOME/work/tmp, never /dev/shm or /tmp."""
        long_tmp = os.path.join(self.tmp, "t" * 70, "u" * 40)
        os.makedirs(long_tmp)
        self.assertGreater(len(os.path.join(long_tmp, "pagedrive-XXXXXX", "tmp")), 107)
        marker = os.path.join(self.tmp, "profile-path.txt")
        job = self.api("POST", "/api/jobs")["id"]
        self.assertEqual(self.drive(job, "return 1;", TMPDIR=long_tmp, PAGEDRIVE_PROFILE_FILE=marker), 1)
        profile = open(marker).read().strip()
        authorised = os.path.join(os.path.expanduser("~"), "work", "tmp") + os.sep
        self.assertTrue(profile.startswith(authorised + "pd-"), profile)
        self.assertLess(len(profile + "/tmp"), 60)

    def test_source_column_follows_the_sample_text_and_ignores_the_result_scale(self):
        job = self.dos_job(run=True)
        out = self.drive(job, """
const drawn = (sel) => waitFor(() => { const c = document.querySelector(sel); return c && c.dataset.drawn === '1' && c; });
const source = await drawn('canvas[data-font]');
const result = await drawn('canvas[data-step]');
const first = {w: source.width, h: source.height};
const scale = document.querySelector('.svf-preview select[aria-label="scale"]');
scale.value = '3'; scale.dispatchEvent(new Event('change'));
await sleep(500);
const text = document.querySelector('.svf-preview input[aria-label="sample text"]');
text.value = 'AB'; text.dispatchEvent(new Event('input'));
await waitFor(() => document.querySelector('canvas[data-font]').width !== first.w);
await sleep(500);
const src = document.querySelector('canvas[data-font]');
return {first, after: {w: src.width, h: src.height}, resultH: document.querySelector('canvas[data-step]').height};
""")
        self.assertNotEqual(out["after"]["w"], out["first"]["w"])             # the source follows the sample text
        self.assertEqual(out["after"]["h"], out["first"]["h"])                # and is drawn at 1/1, not the result's 3/1
        self.assertGreater(out["resultH"], out["first"]["h"])                 # while the result cell was drawn at 3/1

    def test_the_source_face_follows_a_saved_setting(self):
        job = self.dos_job(run=False)
        out = self.drive(job, """
const drawn = () => waitFor(() => { const c = document.querySelector('canvas[data-font]'); return c && c.dataset.drawn === '1' && c; });
const before = (await drawn()).toDataURL();
const fid = 'FONTID';
const row = document.querySelector('tr[data-font="' + fid + '"]');
row.querySelector('input.override').click();
const panel = document.querySelector('tr.override[data-for="' + fid + '"]');
panel.querySelector('.ov-advanced-toggle').click();
// embolden changes the baked pixels (a header ascent only moves the baseline, so a line looks the same)
const field = panel.querySelector('select[data-option="embolden"]');
field.value = 'on'; field.dispatchEvent(new Event('change', {bubbles: true}));
document.getElementById('save').click();
const changed = await waitFor(async () => { const c = document.querySelector('canvas[data-font]'); return c && c.dataset.drawn === '1' && c.toDataURL() !== before && c; });
return {changed: !!changed, notice: document.getElementById('notice').textContent};
""")
        self.assertTrue(out["changed"], out)

    def slow_job(self):
        """A job whose second step blocks until a flag file exists: it stays `running` as long as the test wants."""
        job = self.api("POST", "/api/jobs")["id"]
        self.upload(job, "svf/NEODG16.SVF", os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF"))
        detected = self.api("POST", "/api/jobs/%s/detect" % job)
        font = detected["fonts"][0]["id"]
        s = detected["settings"]
        s["fonts"][font].update(selected=True, dest="new/dom", licence={"kind": "text", "text": "OFL"},
                                licence_name="OFL.TXT", note_name="NOTE.TXT")
        self.api("PUT", "/api/jobs/%s/settings" % job, s)
        names = self.api("GET", "/api/jobs/" + job)["effective_names"][font]
        name = names["precomposed/16/1"]
        flag = os.path.join(self.tmp, "release-" + job)
        neodg = os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF")
        job_dir = self.srv.store.path(job)
        steps = []
        for i, wait in enumerate((False, True, True), 1):
            sid = "s%02d" % i
            os.makedirs(os.path.join(job_dir, "work", sid), exist_ok=True)
            out = os.path.join(job_dir, "work", sid, name)
            text = "import sys, os, time, shutil\n" + (
                "while not os.path.exists(%r):\n    time.sleep(0.05)\n" % flag if wait else "") + \
                "shutil.copy(%r, sys.argv[1])\n" % neodg
            steps.append({"id": sid, "font": font, "kind": "precomposed", "size": 16, "bpp": 1, "layout": None,
                          "name": name, "argv": [[sys.executable, "-c", text, out]], "output": "work/%s/%s" % (sid, name),
                          "state": "pending", "exit": None, "seconds": None, "error": None, "stderr_tail": "",
                          "facts": None, "quality": None, "identical_to": None})
        self.srv.store.update(job, lambda j: j.update(steps=steps))
        self.srv.worker.enqueue(job)
        return job, flag

    def test_polling_keeps_the_controls_of_finished_steps(self):
        job, flag = self.slow_job()
        try:
            out = self.drive(job, """
const row = await waitFor(() => { const c = document.querySelector('canvas[data-step="s01"]'); return c && c.dataset.drawn === '1' && c.closest('tr'); });
const input = row.querySelector('input[aria-label="sample text"]');
input.__mark = 1; input.value = 'keep me';
const seen = new Set();
const start = Date.now();
while (Date.now() - start < 6000) { seen.add(document.getElementById('state').textContent); await sleep(250); }   // three polls
const again = document.querySelector('canvas[data-step="s01"]').closest('tr').querySelector('input[aria-label="sample text"]');
return {same: again === input, mark: again.__mark, value: again.value, states: [...seen]};
""")
        finally:
            open(flag, "w").close()                     # let the worker finish
        self.assertTrue(out["same"], out)
        self.assertEqual((out["mark"], out["value"]), (1, "keep me"))
        self.assertTrue(all("running" in s for s in out["states"]), out)

    def test_apply_dy_on_a_finished_job_is_saved(self):
        job = self.api("POST", "/api/jobs")["id"]
        self.upload(job, "svf/NEODG16.SVF", os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF"))
        detected = self.api("POST", "/api/jobs/%s/detect" % job)
        font = detected["fonts"][0]["id"]
        s = detected["settings"]
        s["fonts"][font].update(selected=True, dest="new/dom", licence={"kind": "text", "text": "OFL"},
                                licence_name="OFL.TXT", note_name="NOTE.TXT")
        self.api("PUT", "/api/jobs/%s/settings" % job, s)
        self.api("POST", "/api/jobs/%s/run" % job)
        self.assertEqual(self.wait_done(job)["state"], "done")
        out = self.drive(job, """
window.confirm = () => true;
await waitFor(() => { const c = document.querySelector('canvas[data-step]'); return c && c.dataset.drawn === '1'; });
const dy = document.querySelector('input[aria-label="dy to try"]');
dy.value = 'A=1 5=-1'; dy.dispatchEvent(new Event('change'));
await sleep(500);
[...document.querySelectorAll('button')].find((b) => b.textContent === 'apply dy').click();
await waitFor(() => document.getElementById('notice').textContent.includes('saved'));
return {notice: document.getElementById('notice').textContent, state: document.getElementById('state').textContent};
""")
        state = self.api("GET", "/api/jobs/" + job)
        self.assertEqual(state["state"], "detected", out)
        self.assertEqual(state["settings"]["fonts"][font]["dy"], {"0x41": 1, "0x35": -1})

    def test_apply_ascent_on_a_finished_job_is_saved_and_the_guides_show(self):
        job = self.dos_job(run=True)
        out = self.drive(job, """
window.confirm = () => true;
await waitFor(() => { const c = document.querySelector('canvas[data-step]'); return c && c.dataset.drawn === '1'; });
const field = document.querySelector('input[aria-label="ascent to try"]');
field.value = '11'; field.dispatchEvent(new Event('change'));
const guides = await waitFor(() => document.querySelectorAll('.canvaswrap .guide').length);
const hint = document.querySelector('.svf-preview .sub').textContent;
[...document.querySelectorAll('button')].find((b) => b.textContent === 'apply ascent').click();
await waitFor(() => document.getElementById('notice').textContent.includes('saved'));
return {guides, hint};
""")
        self.assertEqual(out["guides"], 3)
        self.assertIn("baseline row", out["hint"])
        state = self.api("GET", "/api/jobs/" + job)
        self.assertEqual(state["state"], "detected")
        self.assertEqual(state["settings"]["fonts"][self.font]["options"]["jamoset"]["jamo_ascent"], 11)

    def test_the_dy_table_editor_saves_hex_keys(self):
        job = self.api("POST", "/api/jobs")["id"]
        self.upload(job, "svf/NEODG16.SVF", os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF"))
        detected = self.api("POST", "/api/jobs/%s/detect" % job)
        font = detected["fonts"][0]["id"]
        self.font = font
        self.drive(job, """
await waitFor(() => document.querySelector('tr[data-font="FONTID"]'));
document.querySelector('tr[data-font="FONTID"] input.override').click();
const input = document.querySelector('input[aria-label^="dy table"]');
input.value = 'g=-1 U+0041=2'; input.dispatchEvent(new Event('change'));
document.getElementById('save').click();
await waitFor(() => document.getElementById('state').textContent.includes('detected'));
await sleep(1000);
return 1;
""")
        self.assertEqual(self.api("GET", "/api/jobs/" + job)["settings"]["fonts"][font]["dy"], {"0x41": 2, "0x67": -1})

    def test_the_clipping_panel_counts_and_applies(self):
        job = self.api("POST", "/api/jobs")["id"]
        self.upload_bytes(job, "tall/Tall.ttf", inputfx.tall_ttf())
        self.upload(job, "tall/OFL.txt", self.fx["ttf_licence"])
        detected = self.api("POST", "/api/jobs/%s/detect" % job)
        font = next(f["id"] for f in detected["fonts"] if f["path"].endswith("Tall.ttf"))
        s = detected["settings"]
        s["fonts"][font].update(sizes=[16], bpp=[1], options={"mkfont": {"cell": 12, "width": 16}})
        self.api("PUT", "/api/jobs/%s/settings" % job, s)
        self.font = font
        out = self.drive(job, """
const row = document.querySelector('tr[data-font="FONTID"]');
row.querySelector('input.override').click();
const panel = document.querySelector('tr.override[data-for="FONTID"]');
const details = panel.querySelector('details.clipping');
details.open = true; details.dispatchEvent(new Event('toggle'));
await waitFor(() => panel.querySelector('.clip-counts').textContent.includes('glyphs cut'));
const field = panel.querySelector('input[aria-label="clipping ascent"]');
const first = {ascent: field.value, counts: panel.querySelector('.clip-counts').textContent};
const canvas = await waitFor(() => { const c = panel.querySelector('canvas.clip-overlay'); return c && c.dataset.drawn === '1' && c; });
field.value = '12'; field.dispatchEvent(new Event('input'));
await sleep(500);
const second = panel.querySelector('.clip-counts').textContent;
field.value = ''; field.dispatchEvent(new Event('input'));
await sleep(300);
const cleared = {counts: panel.querySelector('.clip-counts').textContent, rows: panel.querySelectorAll('.clip-row').length,
                 bands: panel.querySelectorAll('.clip-band').length, frames: panel.querySelectorAll('.clip-frame').length};
field.value = '12'; field.dispatchEvent(new Event('input'));
await sleep(500);
const rows = panel.querySelectorAll('.clip-row').length;
const bands = panel.querySelectorAll('.clip-band').length;
[...panel.querySelectorAll('button')].find((b) => b.textContent === 'apply').click();
await sleep(500);
document.getElementById('save').click();
await sleep(1500);
return {first, second, rows, bands, cleared, ink: canvas.dataset.ink};
""")
        self.assertRegex(out["first"]["counts"], r"^\d+ glyphs cut")
        self.assertNotEqual(out["first"]["counts"], out["second"])               # the count follows the ascent typed
        self.assertIn("glyphs cut", out["second"])
        self.assertGreater(out["rows"], 0)                                      # a 15-row ink in a 12-row cell
        self.assertGreater(out["bands"], 0)                                     # the cut rows are tinted on the probe face
        self.assertGreater(int(out["ink"]), 0)
        self.assertIn("whole number", out["cleared"]["counts"])
        self.assertEqual((out["cleared"]["rows"], out["cleared"]["bands"], out["cleared"]["frames"]), (0, 0, 0))
        mk = self.api("GET", "/api/jobs/" + job)["settings"]["fonts"][font]["options"]["mkfont"]
        self.assertEqual((mk["ascent"], mk["clip_cell"]), (12, True))

    def test_a_bad_watchdog_setting_falls_back_to_the_default(self):
        job = self.dos_job(run=False)
        for bad in ("0", "abc", "-5", ""):
            with self.subTest(value=bad):
                out = self.drive(job, "await waitFor(() => document.querySelector('canvas[data-font]')); return 1;",
                                 PAGEDRIVE_WATCHDOG_S=bad)
                self.assertEqual(out, 1)

    def test_apply_asks_before_it_discards_the_build(self):
        job = self.api("POST", "/api/jobs")["id"]
        self.upload(job, "svf/NEODG16.SVF", os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF"))
        detected = self.api("POST", "/api/jobs/%s/detect" % job)
        font = detected["fonts"][0]["id"]
        s = detected["settings"]
        s["fonts"][font].update(selected=True, dest="new/dom", licence={"kind": "text", "text": "OFL"},
                                licence_name="OFL.TXT", note_name="NOTE.TXT")
        self.api("PUT", "/api/jobs/%s/settings" % job, s)
        self.api("POST", "/api/jobs/%s/run" % job)
        self.assertEqual(self.wait_done(job)["state"], "done")
        script = """
let asked = 0;
window.confirm = (m) => { asked++; window.__message = m; return ACCEPT; };
await waitFor(() => { const c = document.querySelector('canvas[data-step]'); return c && c.dataset.drawn === '1'; });
const dy = document.querySelector('input[aria-label="dy to try"]');
dy.value = 'A=1'; dy.dispatchEvent(new Event('change'));
await sleep(500);
[...document.querySelectorAll('button')].find((b) => b.textContent === 'apply dy').click();
await sleep(3000);
return {asked, message: window.__message, state: document.getElementById('state').textContent};
"""
        cancelled = self.drive(job, script.replace("ACCEPT", "false"))
        self.assertEqual(cancelled["asked"], 1)
        self.assertIn("discard", cancelled["message"])
        state = self.api("GET", "/api/jobs/" + job)
        self.assertEqual(state["state"], "done")                                  # nothing was touched
        self.assertTrue(state["result"])
        self.assertIsNone(state["settings"]["fonts"][font]["dy"])
        accepted = self.drive(job, script.replace("ACCEPT", "true"))
        self.assertEqual(accepted["asked"], 1)
        state = self.api("GET", "/api/jobs/" + job)
        self.assertEqual(state["state"], "detected")
        self.assertEqual(state["settings"]["fonts"][font]["dy"], {"0x41": 1})

    def preset_job(self, preset, size, bpp, run):
        job = self.api("POST", "/api/jobs")["id"]
        self.upload(job, "nanum/NanumGothic-Bold.ttf", os.path.join(REPO_DIR, "ttf", "nanumgothic", "NanumGothic-Bold.ttf"))
        self.upload(job, "nanum/OFL.txt", os.path.join(REPO_DIR, "ttf", "nanumgothic", "OFL.txt"))
        detected = self.api("POST", "/api/jobs/%s/detect" % job)
        font = next(f["id"] for f in detected["fonts"] if f["path"].endswith(".ttf"))
        s = detected["settings"]
        for fid, per in s["fonts"].items():
            per["selected"] = fid == font and run
        s["fonts"][font].update(dest="new/dom", sizes=[size], bpp=[bpp], preset=preset)
        self.api("PUT", "/api/jobs/%s/settings" % job, s)
        self.font = font
        return job

    def panel_counts(self, job):
        return self.drive(job, """
const panel = (document.querySelector('tr.override[data-for="FONTID"]'));
document.querySelector('tr[data-font="FONTID"] input.override').click();
const details = panel.querySelector('details.clipping');
details.open = true; details.dispatchEvent(new Event('toggle'));
await waitFor(() => /glyphs cut/.test(panel.querySelector('.clip-counts').textContent));
return {counts: panel.querySelector('.clip-counts').textContent, cell: panel.querySelector('.clip-controls, .svf-controls').textContent,
        ascent: panel.querySelector('input[aria-label="clipping ascent"]').value};
""")

    def test_the_clipping_panel_uses_the_presets_own_cell(self):
        """dos-u-2bpp carries --cell 16 --clip-cell --ascent {size-2}: the panel must show what that build cuts."""
        built = self.preset_job("dos-u-2bpp", 17, 2, run=True)
        done = self.wait_after_run(built)
        report = read_report(self.srv, built, done["steps"][0])
        cut = report["counts"]["cut"]
        self.assertGreater(cut, 1000)
        out = self.panel_counts(self.preset_job("dos-u-2bpp", 17, 2, run=False))
        self.assertTrue(out["counts"].startswith("{:,} glyphs cut".format(cut)), (out, cut))
        self.assertIn("cell 16 rows", out["cell"])
        self.assertEqual(out["ascent"], "15")
        # latin-18cell-2bpp: cell 18, nothing cut at 16 px
        out = self.panel_counts(self.preset_job("latin-18cell-2bpp", 16, 2, run=False))
        self.assertTrue(out["counts"].startswith("0 glyphs cut"), out)
        self.assertIn("cell 18 rows", out["cell"])

    def wait_after_run(self, job):
        self.api("POST", "/api/jobs/%s/run" % job)
        done = self.wait_done(job)
        self.assertEqual(done["state"], "done", done.get("error"))
        return done

    def test_the_pieces_panel_lists_pieces_from_the_identity_json(self):
        job = self.dos_job(run=True)
        done = self.api("GET", "/api/jobs/" + job)
        step = next(st for st in done["steps"] if st["kind"] == "jamo")
        summary = {"available": True, "identity": "fail", "recog_ks": 0.9, "recog_all": 0.9, "unscored": 0,
                   "pieces": {"pass": 1, "warn": 0, "fail": 1, "unscored": 0, "unused": 0}}
        pieces = [{"piece": 0, "slot": "i", "jamo": "ㄱ", "set": 0, "users": 10, "read": 0.1, "nll": 3.0, "flag": "fail",
                   "worst": [{"cp": 0xAC00, "got": "ㄲ"}]},
                  {"piece": 1, "slot": "m", "jamo": "ㅏ", "set": 0, "users": 20, "read": 0.99, "nll": 0.1, "flag": "pass",
                   "worst": []}]
        self.srv.store.update(job, lambda j: j["steps"][0].update(identity=summary))
        with open(self.srv.store.path(job, "work", step["id"], "identity.json"), "w") as f:
            json.dump({"available": True, "applicable": True, "face": summary, "pieces": pieces, "bpp_note": None}, f)
        out = self.drive(job, """
await waitFor(() => { const c = document.querySelector('canvas[data-step]'); return c && c.dataset.drawn === '1'; });
const summary = document.querySelector('.pieces-summary').textContent;
const details = document.querySelector('details.pieces');
details.open = true; details.dispatchEvent(new Event('toggle'));
await waitFor(() => document.querySelectorAll('.piece-row').length === 2);
await sleep(500);
const rows = [...document.querySelectorAll('.piece-row')].map((r) => ({flag: r.dataset.flag, drawn: r.querySelector('canvas').dataset.drawn,
  text: r.textContent}));
document.querySelector('.piece-row').click();
await waitFor(() => document.querySelectorAll('.piece-worst canvas').length >= 1);
return {summary, rows};
""")
        self.assertIn("identity fail", out["summary"])
        self.assertEqual([r["flag"] for r in out["rows"]], ["fail", "pass"])
        self.assertTrue(all(r["drawn"] == "1" for r in out["rows"]))
        self.assertIn("fix:", out["rows"][0]["text"])
        self.assertNotIn("fix:", out["rows"][1]["text"])

    def test_the_pieces_panel_says_when_the_check_is_unavailable(self):
        job = self.dos_job(run=True)
        out = self.drive(job, """
await waitFor(() => document.querySelector('.pieces-summary'));
return document.querySelector('.pieces-summary').textContent;
""")
        self.assertEqual(out, "identity check unavailable (set SVF_RECOG_DIR to a folder with recog.py and its weights; "
                              "numpy and torch needed)")

    def symbols_hint(self, job):
        return self.drive(job, """
window.confirm = () => true;
await waitFor(() => { const c = document.querySelector('canvas[data-step]'); return c && c.dataset.drawn === '1'; });
const field = document.querySelector('input[aria-label="ascent to try"]');
field.value = '5'; field.dispatchEvent(new Event('change'));
await waitFor(() => /baseline row/.test(document.querySelector('.svf-preview .sub').textContent));
return document.querySelector('.svf-preview .sub').textContent;
""")

    def test_the_symbols_hint_follows_the_flag_a_preset_puts_in_the_argv(self):
        """jamo-844-symbols injects --symbols: the compositor treats the two symbols as framed by the ascent."""
        self.assertIn("symbols are approximate", self.symbols_hint(self.dos_job(run=True, preset="jamo-844-symbols")))
        self.assertNotIn("symbols are approximate", self.symbols_hint(self.dos_job(run=True)))

    def test_the_clipping_panel_follows_the_unsaved_fields(self):
        job = self.api("POST", "/api/jobs")["id"]
        self.upload_bytes(job, "tall/Tall.ttf", inputfx.tall_ttf())
        self.upload(job, "tall/OFL.txt", self.fx["ttf_licence"])
        detected = self.api("POST", "/api/jobs/%s/detect" % job)
        font = next(f["id"] for f in detected["fonts"] if f["path"].endswith("Tall.ttf"))
        s = detected["settings"]
        s["fonts"][font].update(sizes=[16], bpp=[1], options={"mkfont": {"cell": 12, "width": 16}})
        self.api("PUT", "/api/jobs/%s/settings" % job, s)
        self.font = font
        out = self.drive(job, """
document.querySelector('tr[data-font="FONTID"] input.override').click();
const panel = document.querySelector('tr.override[data-for="FONTID"]');
const details = panel.querySelector('details.clipping');
details.open = true; details.dispatchEvent(new Event('toggle'));
await waitFor(() => /glyphs cut/.test(panel.querySelector('.clip-counts').textContent));
const cell = () => [...panel.querySelectorAll('.svf-controls span')].map((n) => n.textContent).join(' ');
const first = {counts: panel.querySelector('.clip-counts').textContent, cell: cell()};
const field = panel.querySelector('input[data-option="cell"]');       // the advanced panel is open: it holds a cell option
field.value = '9'; field.dispatchEvent(new Event('input', {bubbles: true}));
await sleep(500);
const typed = {counts: panel.querySelector('.clip-counts').textContent, cell: cell(), note: panel.querySelector('details.clipping .sub').textContent};
const sizes = panel.querySelector('input.ov-sizes');
sizes.value = '16, 17'; sizes.dispatchEvent(new Event('change', {bubbles: true}));
await sleep(500);
const options = [...panel.querySelectorAll('select[aria-label="clipping size"] option')].map((o) => o.value);
return {first, typed, options};
""")
        self.assertIn("cell 12 rows", out["first"]["cell"])
        self.assertIn("cell 9 rows", out["typed"]["cell"])
        self.assertNotEqual(out["typed"]["counts"], out["first"]["counts"])
        self.assertEqual(out["options"], ["16", "17"])

    def test_two_quick_page_clicks_in_the_glyph_grid_draw_one_page(self):
        job = self.api("POST", "/api/jobs")["id"]
        self.upload(job, "svf/NEODG16.SVF", os.path.join(REPO_DIR, "svf", "dos", "NEODG16.SVF"))
        detected = self.api("POST", "/api/jobs/%s/detect" % job)
        font = detected["fonts"][0]["id"]
        s = detected["settings"]
        s["fonts"][font].update(selected=True, dest="new/dom", licence={"kind": "text", "text": "OFL"},
                                licence_name="OFL.TXT", note_name="NOTE.TXT")
        self.api("PUT", "/api/jobs/%s/settings" % job, s)
        self.api("POST", "/api/jobs/%s/run" % job)
        self.assertEqual(self.wait_done(job)["state"], "done")
        out = self.drive(job, """
await waitFor(() => { const c = document.querySelector('canvas[data-step]'); return c && c.dataset.drawn === '1'; });
[...document.querySelectorAll('button')].find((b) => b.textContent === 'glyphs').click();
await waitFor(() => document.querySelectorAll('canvas.grid-row').length === 16);
const next = [...document.querySelectorAll('.glyph-grid button')].find((b) => b.textContent === '>');
next.click(); next.click();
await sleep(2500);
return {rows: document.querySelectorAll('canvas.grid-row').length, nav: document.querySelector('.glyph-grid div').textContent};
""")
        self.assertEqual(out["rows"], 16, out)


ACK_TEXT = ("You are responsible for having the right to convert the fonts you choose. Converted faces are written "
            "only to your chosen output folder. If you publish them, check each font's licence.")


class LocalPageTest(localfx.LocalBase):
    """The sources panel, the shell bridge, the written-to line and the acknowledgement popup of a local-mode page,
    driven in headless Chrome against a server with the per-launch token (sent as an extra header, the way the
    Electron shell will). Skips like PageDomTest."""

    def setUp(self):
        self.chrome = browser()
        if not self.chrome or not shutil.which("node"):
            self.skipTest("no headless Chrome or node: the page is not driven")
        if not os.path.isfile(os.path.join(MAKER_DIR, "static", "wasm", "svf.wasm")):
            self.skipTest("the preview module is not built")
        super().setUp()

    def drive(self, script, query="", headers=True, preload=None):
        fd, path = tempfile.mkstemp(suffix=".js", dir=self.tmp)
        with os.fdopen(fd, "w") as f:
            f.write(script)
        argv = ["node", DRIVER, self.chrome, "http://127.0.0.1:%d/%s" % (self.port, query), path]
        if headers:
            argv += ["--header", "X-Maker-Token:" + localfx.TOKEN]
        if preload:
            pre = os.path.join(self.tmp, "preload.js")
            with open(pre, "w") as f:
                f.write(preload)
            argv += ["--preload", pre]
        env = dict(os.environ, PAGEDRIVE_WATCHDOG_S=str(WAIT_S - 20))
        proc = wincompat.popen_group(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            stdout, stderr = proc.communicate(timeout=WAIT_S)
        except subprocess.TimeoutExpired:
            wincompat.kill_group(proc)
            proc.communicate()
            self.fail("the page driver timed out after %d s" % WAIT_S)
        self.assertEqual(proc.returncode, 0, stderr)
        return json.loads(stdout)

    def done_job(self):
        jid = self.local_job()
        job = self.job(jid)
        ttf = next(f["id"] for f in job["fonts"] if f["path"] == "Munjo.ttf")
        st = job["settings"]
        st["fonts"][ttf].update(selected=True, dest="dos", kinds=["precomposed"], sizes=[16], bpp=[1])
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        self.assertEqual(self.run_to_done(jid)["state"], "done")
        return jid

    TYPED = """
      const visible = (el) => !!el && !el.hidden && el.getClientRects().length > 0;
      await waitFor(() => visible(document.getElementById('sources-panel')));
    """

    def test_without_the_header_every_api_call_is_403(self):
        out = self.drive("const r = await fetch('/api/caps'); return r.status;", headers=False)
        self.assertEqual(out, 403)

    def typed_script(self, tail):
        paths = json.dumps("\n".join(self.roots))
        return self.TYPED + """
      const fileInputsShown = [...document.querySelectorAll('input[type=file]')].filter(visible).length;
      const seen = {
        upload: visible(document.getElementById('upload-panel')),
        files: fileInputsShown,
        paths: visible(document.getElementById('source-paths')),
        output: visible(document.getElementById('output-dir')),
        chooseFiles: visible(document.getElementById('choose-files')),
        chooseOutput: visible(document.getElementById('choose-output')),
      };
      document.getElementById('source-paths').value = %s;
      document.getElementById('output-dir').value = %s;
      document.getElementById('source-paths').dispatchEvent(new Event('input', {bubbles: true}));
      document.getElementById('output-dir').dispatchEvent(new Event('input', {bubbles: true}));
      const ack = document.getElementById('ack');
      let shown = 0;
      new MutationObserver(() => { if (visible(ack)) shown++; }).observe(ack, {attributes: true});
      const rows = () => [...document.querySelectorAll('#fonts tr[data-font]')];
      const detectOnce = async () => {
        document.getElementById('detect-local').click();
        await sleep(300);
        if (visible(ack)) {
          seen.ackText = document.getElementById('ack-text').textContent.replace(/\\s+/g, ' ').trim();
          seen.jobsWhileAsking = (await (await fetch('/api/jobs')).json()).jobs.length;
          document.getElementById('ack-ok').click();
        }
        await waitFor(() => rows().length >= 5);
      };
      %s
    """ % (paths, json.dumps(self.out), tail)

    def test_sources_panel_with_typed_paths(self):
        out = self.drive(self.typed_script("""
      await detectOnce();
      seen.rows = rows().map((tr) => tr.textContent);
      seen.ackShown = shown;
      return seen;
    """))
        self.assertEqual(out["upload"], False)
        self.assertEqual(out["files"], 0)
        self.assertEqual((out["paths"], out["output"]), (True, True))
        self.assertEqual((out["chooseFiles"], out["chooseOutput"]), (False, False))
        self.assertTrue(any("a/Munjo.ttf" in row for row in out["rows"]), out["rows"])
        self.assertTrue(any("b/HAN.FNT" in row for row in out["rows"]), out["rows"])

    def test_the_acknowledgement_shows_once_per_page_session(self):
        out = self.drive(self.typed_script("""
      await detectOnce();
      const firstShown = shown;
      rows().forEach((tr) => tr.remove());
      await detectOnce();                      // a second local job in the same page: no popup this time
      seen.shownFirst = firstShown;
      seen.shownTotal = shown;
      seen.rows = rows().length;
      return seen;
    """))
        self.assertEqual(out["ackText"], ACK_TEXT)
        self.assertEqual(out["jobsWhileAsking"], 0)                              # nothing is created before OK
        self.assertEqual((out["shownFirst"], out["shownTotal"]), (1, 1))
        self.assertGreaterEqual(out["rows"], 5)

    def test_run_says_written_and_open_folder_disabled(self):
        jid = self.done_job()
        out = self.drive("""
      const visible = (el) => !!el && !el.hidden && el.getClientRects().length > 0;
      await waitFor(() => document.getElementById('state').textContent.includes('written to'));
      const open = document.getElementById('open-folder');
      return {state: document.getElementById('state').textContent, open: visible(open), disabled: open.disabled,
              download: visible(document.getElementById('download'))};
    """, query="?job=" + jid)
        self.assertIn("written to " + self.out, out["state"])
        self.assertEqual((out["open"], out["disabled"], out["download"]), (True, True, False))

    BRIDGE = """
      window.svfMaker = {pickFolder: async () => [%s], pickFiles: async () => [], pickOutputDir: async () => %s,
                         openOutputFolder: async (...a) => { window.__opened = a.length; }, platform: "linux"};
    """

    def test_bridge_fills_and_opens(self):
        jid = self.done_job()
        root = json.dumps(self.roots[0])
        pre = self.BRIDGE % (root, json.dumps(self.out))
        out = self.drive("""
      const visible = (el) => !!el && !el.hidden && el.getClientRects().length > 0;
      await waitFor(() => visible(document.getElementById('sources-panel')));
      const seen = {paths: visible(document.getElementById('source-paths')), output: visible(document.getElementById('output-dir')),
                    chooseFolder: visible(document.getElementById('choose-folder'))};
      document.getElementById('choose-folder').click();
      await waitFor(() => document.getElementById('source-roots').textContent.includes(%s));
      document.getElementById('choose-output').click();
      await waitFor(() => document.getElementById('sources-panel').textContent.includes(%s));
      await waitFor(() => document.getElementById('state').textContent.includes('written to'));
      const open = document.getElementById('open-folder');
      seen.openEnabled = visible(open) && !open.disabled;
      open.click();
      await waitFor(() => window.__opened !== undefined);
      seen.opened = window.__opened;
      return seen;
    """ % (root, json.dumps(self.out)), query="?job=" + jid, preload=pre)
        self.assertEqual((out["paths"], out["output"], out["chooseFolder"]), (False, False, True))
        self.assertTrue(out["openEnabled"])
        self.assertEqual(out["opened"], 0)                                      # called with no argument

    def test_a_list_file_range_on_another_root_sets_range_root(self):
        """A list file picked under the second root: choosing it as the range stores `range_root` beside `range`
        (batch and per font), and the select shows it again after the reload."""
        with open(os.path.join(self.roots[1], "chars.txt"), "w", encoding="utf-8") as f:
            f.write("\uac00\uac01\n")
        jid = self.local_job()
        job = self.job(jid)
        fid = next(f["id"] for f in job["fonts"] if f["path"] == "Munjo.ttf")
        out = self.drive("""
      const id = new URLSearchParams(location.search).get('job');
      const apiJob = async () => (await (await fetch('/api/jobs/' + id)).json());
      const pick = async (sel) => {
        await waitFor(() => [...sel.options].some((o) => o.value === 'list:1:chars.txt'));
        sel.value = 'list:1:chars.txt';
        sel.dispatchEvent(new Event('change', {bubbles: true}));
      };
      const batch = document.getElementById('range');
      await pick(batch);
      const perFont = [...document.querySelectorAll('select[aria-label^="range for"]')]
        .find((s) => s.getAttribute('aria-label').includes('(FONTID)'));
      await pick(perFont);
      document.getElementById('save').click();
      await waitFor(async () => { const j = await apiJob(); return j.settings.batch.range === 'chars.txt'; });
      const j = await apiJob();
      await waitFor(() => document.getElementById('range').value === 'list:1:chars.txt');   // drawn again after the reload
      return {batch: [j.settings.batch.range, j.settings.batch.range_root],
              font: [j.settings.fonts['FONTID'].range, j.settings.fonts['FONTID'].range_root]};
    """.replace("FONTID", fid), query="?job=" + jid)
        self.assertEqual(out["batch"], ["chars.txt", 1])
        self.assertEqual(out["font"], ["chars.txt", 1])

    def test_new_sources_keep_the_job_and_its_ownership(self):
        """Picking sources again with the same output folder re-detects the SAME job: its faces stay its own, so a
        re-run into the folder is not refused as someone else's names."""
        jid = self.done_job()
        before = self.srv.store.load(jid)["owned"]
        self.assertTrue(before)
        paths = json.dumps("\n".join(self.roots))
        out = self.drive("""
      const visible = (el) => !!el && !el.hidden && el.getClientRects().length > 0;
      await waitFor(() => visible(document.getElementById('sources-panel')));
      document.getElementById('source-paths').value = %s;
      document.getElementById('output-dir').value = %s;
      document.getElementById('detect-local').click();
      await waitFor(() => visible(document.getElementById('ack')));
      document.getElementById('ack-ok').click();
      await waitFor(() => document.getElementById('state').textContent.includes('detected'));
      document.getElementById('run').click();
      await waitFor(() => document.getElementById('state').textContent.includes('written to'));
      return {id: new URLSearchParams(location.search).get('job'), state: document.getElementById('state').textContent};
    """ % (paths, json.dumps(self.out)), query="?job=" + jid)
        self.assertEqual(out["id"], jid)                                          # the same job, not a new one
        self.assertEqual(len(self.srv.store.list()), 1)
        job = self.job(jid)
        self.assertEqual(job["state"], "done", job.get("error"))
        self.assertLessEqual(set(before), set(self.srv.store.load(jid)["owned"]))

    DETECT_AGAIN = """
      const visible = (el) => !!el && !el.hidden && el.getClientRects().length > 0;
      await waitFor(() => visible(document.getElementById('sources-panel')));
      const restored = {paths: document.getElementById('source-paths').value, output: document.getElementById('output-dir').value};
      document.getElementById('source-paths').value = %s;
      document.getElementById('output-dir').value = %s;
      document.getElementById('detect-local').click();
      await sleep(300);
      if (visible(document.getElementById('ack'))) document.getElementById('ack-ok').click();
      await waitFor(() => document.getElementById('state').textContent.includes('detected'));
      return {id: new URLSearchParams(location.search).get('job'), restored};
    """

    def test_another_spelling_of_the_output_folder_keeps_the_job(self):
        """A trailing slash, or a symlinked parent, is the same folder: the open job is re-detected (its owned faces
        kept), no second job is made, a done job is taken back to detected by the sources PUT alone."""
        jid = self.done_job()
        before = self.srv.store.load(jid)["owned"]
        link = os.path.join(self.tmp, "link")
        os.symlink(os.path.dirname(self.out), link)
        paths = json.dumps("\n".join(self.roots))
        for spelling in (self.out + "/", os.path.join(link, os.path.basename(self.out))):
            out = self.drive(self.DETECT_AGAIN % (paths, json.dumps(spelling)), query="?job=" + jid)
            self.assertEqual(out["id"], jid, spelling)
            self.assertEqual(len(self.srv.store.list()), 1, spelling)
            self.assertEqual(out["restored"]["paths"], "\n".join(r["path"] for r in self.job(jid)["roots"]))
            self.assertEqual(out["restored"]["output"], self.out)              # the reload shows the job's own folder
            self.assertEqual(set(self.srv.store.load(jid)["owned"]), set(before))
            self.assertEqual(self.job(jid)["state"], "detected")
            self.assertIsNone(self.job(jid)["result"])
            self.assertEqual(self.run_to_done(jid)["state"], "done")           # and it runs again over its own faces

    def test_the_job_notice_and_a_delete_button_for_an_abandoned_job(self):
        jid = self.local_job()                                                  # detected, nobody ran it
        self.srv.store.update(jid, lambda j: j.update(notice="intermediate files remain in .svf-maker-X (moved)"))
        out = self.drive("""
      const visible = (el) => !!el && !el.hidden && el.getClientRects().length > 0;
      await waitFor(() => visible(document.getElementById('job-notice')));
      const notice = document.getElementById('job-notice').textContent;
      document.getElementById('delete-job').click();
      await waitFor(() => document.getElementById('state').textContent === 'no job');
      return {notice, deleteShown: visible(document.getElementById('delete-job'))};
    """, query="?job=" + jid)
        self.assertIn("intermediate files remain", out["notice"])
        self.assertFalse(out["deleteShown"])
        self.assertEqual(self.api("GET", "/api/jobs/%s" % jid)[0], 404)
        self.assertEqual(self.api("POST", "/api/jobs", {"source": "local", "output_dir": self.out})[0], 200)   # the folder is free

    def test_sync_caveat_is_shown(self):
        with open(os.path.join(MAKER_DIR, "static", "index.html"), encoding="utf-8") as f:
            html = f.read()
        self.assertIn("intermediate files are kept in .svf-maker-&lt;id&gt;/ inside this folder while the maker runs; "
                      "choose a folder that is not synced", html)
        self.assertNotIn(' style="', html)                                       # the CSP allows no inline style

    # ---- busy / being-prepared 409s (t_39c9fb52): a fetch stub answers chosen requests with a 409 ----------------

    BUSY_STUB = """
      (() => {
        const real = window.fetch.bind(window);
        const st = window.__stub = {rules: [], sent: [], times: [], bodies: [], passed: [], realFetch: real};
        window.__t = 0;
        const gates = {};                                               // rules with hold: true (or a name) wait here
        const gate = (name) => gates[name] = gates[name] || (() => { let r; const p = new Promise((res) => { r = res; }); return {p, r}; })();
        st.release = (name) => gate(name === undefined ? 'default' : name).r();
        window.fetch = async (input, init) => {
          const method = ((init && init.method) || 'GET').toUpperCase();
          const path = new URL(typeof input === 'string' ? input : input.url, location.href).pathname;
          st.sent.push(method + ' ' + path);
          st.times.push(Date.now());
          st.bodies.push(init && typeof init.body === 'string' ? init.body : null);
          const rule = st.rules.find((r) => r.method === method && new RegExp(r.path).test(path) && r.times > 0);
          if (rule) {
            rule.times--;
            if (rule.hold) await gate(rule.hold === true ? 'default' : rule.hold).p;
            if (rule.fail) throw new TypeError('network down');
            if (rule.body !== undefined) {                              // no body: the real server answers (after the hold)
              return new Response(JSON.stringify(rule.body), {status: rule.status || 409,
                                                              headers: {'Content-Type': 'application/json'}});
            }
          }
          const res = await real(input, init);
          st.passed.push({m: method, path, status: res.status});
          if (rule && rule.holdAfter) await gate(rule.holdAfter).p;       // the real answer, delivered late
          return res;
        };
        window.__notices = [];
        document.addEventListener('DOMContentLoaded', () => {
          const n = document.getElementById('notice');
          new MutationObserver(() => window.__notices.push(n.textContent)).observe(n, {childList: true});
        });
      })();
    """

    BUSY_JS = """
      const visible = (el) => !!el && !el.hidden && el.getClientRects().length > 0;
      const $ = (id) => document.getElementById(id);
      const jid = new URLSearchParams(location.search).get('job');
      const rules = (list) => { window.__stub.rules.push(...list); };
      const count = (key) => window.__stub.sent.filter((s) => s === key).length;
      const lock = (jid) => ({error: 'job ' + jid + ' is busy; try again', busy: 'lock'});
      await waitFor(() => visible($('delete-job')));
    """

    def ready_job(self):
        jid = self.local_job()
        job = self.job(jid)
        ttf = next(f["id"] for f in job["fonts"] if f["path"] == "Munjo.ttf")
        st = job["settings"]
        st["fonts"][ttf].update(selected=True, dest="dos", kinds=["precomposed"], sizes=[16], bpp=[1])
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        return jid

    def busy_drive(self, jid, body, bounds=None):
        """@p bounds: JS for `window.__busyBounds`, set in the preload so it exists before any page script runs."""
        pre = self.BUSY_STUB + ("\nwindow.__busyBounds = %s;\n" % bounds if bounds else "")
        return self.drive(self.BUSY_JS + body, query="?job=" + jid, preload=pre)

    def test_a_busy_delete_is_retried_and_succeeds(self):
        jid = self.local_job()
        out = self.busy_drive(jid, """
      rules([{method: 'DELETE', path: '/api/jobs/[0-9a-f]+$', times: 2, body: lock(jid)}]);
      $('delete-job').click();
      await waitFor(() => $('state').textContent === 'no job');
      return {del: count('DELETE /api/jobs/' + jid), notices: window.__notices, notice: visible($('notice')),
              retry: visible($('notice-retry'))};
    """)
        self.assertEqual(out["del"], 3)
        text = "\n".join(out["notices"])
        self.assertIn("(retrying 1/3)", text)
        self.assertIn("(retrying 2/3)", text)
        self.assertFalse(out["notice"])
        self.assertFalse(out["retry"])
        self.assertEqual(self.api("GET", "/api/jobs/%s" % jid)[0], 404)

    def test_a_busy_run_past_the_bound_offers_try_again_and_runs_once(self):
        jid = self.ready_job()
        text = "job %s is busy: a preview is being made; try again" % jid
        out = self.busy_drive(jid, """
      rules([{method: 'POST', path: '/run$', times: 4, body: {error: %s, busy: 'preview'}}]);
      $('run').click();
      await waitFor(() => visible($('notice-retry')));
      const first = {sent: count('POST /api/jobs/' + jid + '/run'), notice: $('notice').textContent};
      $('notice-retry').click();
      await waitFor(() => $('state').textContent.includes('written to'), 60000);
      return {first, sent: count('POST /api/jobs/' + jid + '/run'),
              passed: window.__stub.passed.filter((p) => p.m === 'POST' && p.path.endsWith('/run')),
              notice: visible($('notice')), retry: visible($('notice-retry'))};
    """ % json.dumps(text))
        self.assertEqual(out["first"]["sent"], 4)
        self.assertEqual(out["first"]["notice"], "POST /api/jobs/%s/run: HTTP 409: %s" % (jid, text))
        self.assertEqual(out["sent"], 5)
        self.assertEqual([p["status"] for p in out["passed"]], [200])
        self.assertFalse(out["notice"])
        self.assertFalse(out["retry"])

    def test_a_run_being_prepared_is_not_retried_and_follows_the_other_run(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      rules([{method: 'POST', path: '/run$', times: 1, body: {error: 'a run of job ' + jid + ' is being prepared', busy: 'preparing'}}]);
      $('run').click();
      await waitFor(() => visible($('notice-retry')));
      await sleep(2000);
      await window.__stub.realFetch('/api/jobs/' + jid + '/run', {method: 'POST'});   // the other tab's run
      await waitFor(() => $('state').textContent.includes('written to'), 60000);
      const sent = window.__stub.sent;
      const at = sent.indexOf('POST /api/jobs/' + jid + '/run');
      return {runs: count('POST /api/jobs/' + jid + '/run'),
              gets: sent.slice(at).filter((s) => s === 'GET /api/jobs/' + jid).length, retry: visible($('notice-retry'))};
    """)
        self.assertEqual(out["runs"], 1)
        self.assertGreaterEqual(out["gets"], 2)
        self.assertLessEqual(out["gets"], 16)
        self.assertFalse(out["retry"])                                           # the follow dropped the control

    def test_try_again_on_a_run_being_prepared_keeps_one_follow_loop(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      window.__ticks = [];                                                     // the follow loop's waits, released by hand
      window.__busyBounds = {sleep: () => new Promise((res) => window.__ticks.push(res))};
      const body = {error: 'a run of job ' + jid + ' is being prepared', busy: 'preparing'};
      rules([{method: 'POST', path: '/run$', times: 2, body}]);
      $('run').click();
      await waitFor(() => visible($('notice-retry')));
      $('notice-retry').click();
      await waitFor(() => count('POST /api/jobs/' + jid + '/run') === 2);
      await waitFor(() => visible($('notice-retry')));
      await sleep(200);
      const waiting = window.__ticks.length;                                   // one loop: one pending wait
      const at = window.__stub.sent.indexOf('POST /api/jobs/' + jid + '/run');
      const gets = () => window.__stub.sent.slice(at).filter((x) => x === 'GET /api/jobs/' + jid).length;
      window.__ticks[0]();                                                     // one interval passes
      await waitFor(() => gets() === 1);
      await sleep(200);
      return {waiting, created: window.__ticks.length, gets: gets()};
    """)
        self.assertEqual(out, {"waiting": 1, "created": 2, "gets": 1})           # a second loop would have waited twice

    def test_a_late_busy_answer_of_a_superseded_try_again_neither_resumes_nor_shows_the_button(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      window.__busyBounds = {followMs: 100};
      const detected = $('state').textContent;
      rules([{method: 'POST', path: '/run$', times: 1, body: {error: 'a run of job ' + jid + ' is being prepared', busy: 'preparing'}},
             {method: 'POST', path: '/run$', times: 1, hold: true, body: {error: 'job ' + jid + ' is busy: a preview is being made; try again', busy: 'preview'}}]);
      $('run').click();
      await waitFor(() => visible($('notice-retry')));
      $('notice-retry').click();                                               // its answer is held
      await waitFor(() => count('POST /api/jobs/' + jid + '/run') === 2);
      await window.__stub.realFetch('/api/jobs/' + jid + '/run', {method: 'POST'});   // the other run starts
      await waitFor(() => $('state').textContent !== detected);                // the follow loop saw it leave `detected`
      window.__stub.release();                                                 // now the busy answer comes in late
      await sleep(1500);
      return {runs: count('POST /api/jobs/' + jid + '/run'), retry: visible($('notice-retry')), notice: $('notice').textContent};
    """)
        self.assertEqual(out["runs"], 2)                                         # no third send
        self.assertFalse(out["retry"])
        self.assertNotIn("retrying", out["notice"])
        self.wait_done(jid)

    def test_the_follow_loop_belongs_to_its_action_and_leaves_a_newer_notice_alone(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      window.__busyBounds = {followMs: 100};
      rules([{method: 'POST', path: '/run$', times: 1, body: {error: 'a run of job ' + jid + ' is being prepared', busy: 'preparing'}},
             {method: 'POST', path: '/run$', times: 1, body: {error: 'job ' + jid + ' is queued'}}]);
      $('run').click();
      await waitFor(() => visible($('notice-retry')));
      $('run').click();                                                        // a newer action: its own notice
      await waitFor(() => $('notice').textContent.includes('is queued'));
      await window.__stub.realFetch('/api/jobs/' + jid + '/run', {method: 'POST'});   // the other run starts
      await sleep(1000);                                                       // ten follow intervals
      return {notice: $('notice').textContent, retry: visible($('notice-retry'))};
    """)
        self.assertIn("is queued", out["notice"])                                # the loop wiped nothing
        self.assertFalse(out["retry"])
        self.wait_done(jid)

    def test_the_follow_loop_ignores_a_late_answer_after_the_open_job_changed(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      window.__busyBounds = {followMs: 100};
      rules([{method: 'POST', path: '/run$', times: 1, body: {error: 'a run of job ' + jid + ' is being prepared', busy: 'preparing'}},
             {method: 'GET', path: '/api/jobs/[0-9a-f]+$', times: 1, hold: true},
             {method: 'DELETE', path: '/api/jobs/[0-9a-f]+$', times: 1, status: 200, body: {deleted: jid}}]);
      const n0 = count('GET /api/jobs/' + jid);                               // the page's own load already read the job
      $('run').click();
      await waitFor(() => visible($('notice-retry')));
      await waitFor(() => window.__stub.rules[1].times === 0 && count('GET /api/jobs/' + jid) === n0 + 1);   // the follow GET is held
      await window.__stub.realFetch('/api/jobs/' + jid + '/run', {method: 'POST'});   // the other run starts
      $('delete-job').click();
      await waitFor(() => $('state').textContent === 'no job');
      const gets = count('GET /api/jobs/' + jid);
      window.__stub.release();                                                 // the held answer (job no longer detected) arrives
      await sleep(1500);
      return {state: $('state').textContent, laterGets: count('GET /api/jobs/' + jid) - gets};
    """)
        self.assertEqual(out["state"], "no job")                                 # the late answer rendered nothing
        self.assertEqual(out["laterGets"], 0)                                    # and the loop ended
        self.wait_done(jid)

    def test_a_source_preview_being_prepared_is_retried_and_shown(self):
        jid = self.local_job(roots=[self.roots[0]])                             # the TTF is the only entry with a preview
        ttf = next(f["id"] for f in self.job(jid)["fonts"] if f["path"] == "Munjo.ttf")
        marker = ReleaseOnWait(3, self.srv.preparing, jid)       # wait 1: the <img> load, 2: the fallback fetch, 3: its repeat
        self.srv.preparing[jid] = marker
        self.addCleanup(self.srv.preparing.pop, jid, None)
        with mock.patch.object(jobs, "LOCKED_IO_S", 0.3):
            out = self.busy_drive(jid, """
      const img = () => document.querySelector('img.preview');
      await waitFor(() => img() && img().naturalWidth > 0, 90000);
      return {shown: !img().hidden, passed: window.__stub.passed.filter((p) => p.path.endsWith('/source.png')).map((p) => p.status)};
    """)
        self.assertTrue(out["shown"])
        self.assertEqual(out["passed"], [409, 200])                              # the fallback's first answer, then its repeat
        self.assertGreaterEqual(marker.calls, 3)
        self.assertTrue(ttf)

    def test_a_source_preview_busy_past_the_bound_is_hidden_as_before(self):
        jid = self.local_job(roots=[self.roots[0]])
        marker = threading.Event()                                               # a run that never finishes preparing
        self.srv.preparing[jid] = marker
        self.addCleanup(self.srv.preparing.pop, jid, None)
        with mock.patch.object(jobs, "LOCKED_IO_S", 0.3):
            out = self.busy_drive(jid, """
      const img = () => document.querySelector('img.preview');
      await waitFor(() => img() && img().hidden, 30000);
      await sleep(500);
      return {gets: window.__stub.sent.filter((x) => x.includes('/source.png')).length, notice: visible($('notice'))};
    """, bounds="{retryMs: [50, 50, 50]}")
        self.assertGreater(out["gets"], 0)
        self.assertEqual(out["gets"] % 4, 0, out)                                # 1 + 3 repeats per table build
        self.assertFalse(out["notice"])                                          # silent

    def test_a_source_preview_retry_checks_the_deadline_before_every_resend(self):
        jid = self.local_job(roots=[self.roots[0]])
        marker = threading.Event()
        self.srv.preparing[jid] = marker
        self.addCleanup(self.srv.preparing.pop, jid, None)
        with mock.patch.object(jobs, "LOCKED_IO_S", 0.3):
            out = self.busy_drive(jid, """
      const img = () => document.querySelector('img.preview');
      await waitFor(() => img() && img().hidden, 30000);
      await sleep(500);
      return window.__stub.sent.filter((x) => x.includes('/source.png')).length;
    """, bounds="""{totalMs: 1000, retryMs: [20, 20, 20], now: () => window.__t,    // a controlled clock; each sleep adds 500
                             sleep: async (ms) => { window.__t += 500; await new Promise((res) => setTimeout(res, ms)); }}""")
        self.assertEqual(out, 2)                                                 # sends at t=0 and t=500; t=1000 is past it

    def superseded_terminal_error(self, fail):
        if True:
            jid = self.ready_job()
            held = {"method": "DELETE", "path": "/api/jobs/[0-9a-f]+$", "times": 1, "hold": True}
            if fail:
                held["fail"] = True
            else:
                held["body"] = {"error": "job x is queued"}
            out = self.busy_drive(jid, """
      rules([%s,
             {method: 'POST', path: '/run$', times: 1, body: {error: 'a run of job ' + jid + ' is being prepared', busy: 'preparing'}}]);
      $('delete-job').click();
      await waitFor(() => count('DELETE /api/jobs/' + jid) === 1);
      $('run').click();                                                        // a newer action: a message and a button
      await waitFor(() => visible($('notice-retry')));
      const before = $('notice').textContent;
      window.__stub.release();                                                 // the older call's terminal error arrives late
      await sleep(500);
      return {before, notice: $('notice').textContent, retry: visible($('notice-retry'))};
    """ % json.dumps(held))
            self.assertIn("being prepared", out["before"])
            self.assertEqual(out["notice"], out["before"], fail)                 # not replaced by the older call's error
            self.assertTrue(out["retry"], fail)                                  # and its button not rejected away

    def test_a_superseded_untagged_409_leaves_the_newer_message_and_button(self):
        self.superseded_terminal_error(False)

    def test_a_superseded_network_rejection_leaves_the_newer_message_and_button(self):
        self.superseded_terminal_error(True)

    def test_try_again_after_the_other_run_started_shows_the_job_instead_of_a_stale_page(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      const detected = $('state').textContent;
      rules([{method: 'POST', path: '/run$', times: 1, body: {error: 'a run of job ' + jid + ' is being prepared', busy: 'preparing'}}]);
      $('run').click();
      await waitFor(() => visible($('notice-retry')));
      await window.__stub.realFetch('/api/jobs/' + jid + '/run', {method: 'POST'});   // the other run starts; no follow GET yet
      $('notice-retry').click();                                               // "job X is queued" (or running / done)
      await waitFor(() => $('state').textContent.includes('written to'), 60000);
      return {runs: count('POST /api/jobs/' + jid + '/run'), detected};
    """, bounds="{sleep: () => new Promise(() => {})}")                          # the follow loop never reads the job
        self.assertEqual(out["runs"], 2)                                         # the second send is the Try again, nothing more

    def test_a_late_probe_of_an_earlier_size_does_not_overwrite_the_newer_one(self):
        jid = self.local_job()
        job = self.job(jid)
        ttf = next(f["id"] for f in job["fonts"] if f["path"] == "Munjo.ttf")
        st = job["settings"]
        st["fonts"][ttf].update(selected=True, dest="dos", kinds=["precomposed"], sizes=[16, 17], bpp=[1])
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        out = self.busy_drive(jid, """
      rules([{method: 'GET', path: '/probe/[^/]+/16/1\\.json$', times: 1, hold: true, body: {error: 'job ' + jid + ' is busy; try again', busy: 'lock'}}]);
      const row = document.querySelector('tr[data-font]');
      row.querySelector('input.override').click();
      const panel = document.querySelector('tr.override');
      const details = panel.querySelector('details.clipping');
      details.open = true; details.dispatchEvent(new Event('toggle'));       // size 16: its probe is held
      await waitFor(() => window.__stub.rules[0].times === 0);
      const size = panel.querySelector('select[aria-label="clipping size"]');
      size.value = '17'; size.dispatchEvent(new Event('change', {bubbles: true}));
      const counts = panel.querySelector('.clip-counts');
      await waitFor(() => /glyphs cut/.test(counts.textContent));
      const second = {counts: counts.textContent, cell: [...panel.querySelectorAll('.svf-controls span')].map((n) => n.textContent).join(' ')};
      let changes = 0;
      new MutationObserver(() => changes++).observe(counts, {childList: true});
      window.__stub.release();                                                 // size 16's probe gets through, late
      await sleep(2500);
      return {changes, counts: counts.textContent, size: size.value, second};
    """)
        self.assertEqual(out["size"], "17")
        self.assertEqual(out["changes"], 0)                                      # the older load wrote nothing
        self.assertEqual(out["counts"], out["second"]["counts"])

    def test_a_background_notice_does_not_supersede_a_pending_save(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      rules([{method: 'GET', path: '/api/jobs/[0-9a-f]+$', times: 1},                      // run's reload reads the job
             {method: 'GET', path: '/api/jobs/[0-9a-f]+$', times: 1, hold: 'poll', status: 500, body: {error: 'poll down'}},
             {method: 'PUT', path: '/settings$', times: 1, hold: true, status: 400, body: {error: 'bad settings'}}]);
      $('run').click();
      await waitFor(() => window.__stub.rules[0].times === 0);                 // run's reload is done; the poll timer is armed
      $('save').click();                                                       // the Save's PUT is held; the poll fires later
      await waitFor(() => count('PUT /api/jobs/' + jid + '/settings') === 1);
      await waitFor(() => window.__stub.rules[1].times === 0, 30000);          // the poll's GET (started after the Save) is held
      window.__stub.release('poll');                                           // a background notice appears ...
      await waitFor(() => $('notice').textContent.includes('poll down'));
      window.__stub.release();                                                 // ... then the Save is refused
      await sleep(500);
      return $('notice').textContent;
    """)
        self.assertIn("bad settings", out)                                       # the Save's own error is shown

    def test_an_unrelated_run_409_leaves_the_users_unsaved_edit_alone(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      rules([{method: 'POST', path: '/run$', times: 1, hold: true, body: {error: 'a/b.ttf: the input changed since detection: detect again'}}]);
      $('run').click();                                                        // the run's preparation is pending
      await waitFor(() => count('POST /api/jobs/' + jid + '/run') === 1);
      const toggle = document.querySelector('tr[data-font] input.override');
      toggle.click();                                                          // the user edits a setting meanwhile
      const edited = () => !!document.querySelector('tr[data-font] input.override').checked;
      const before = edited();
      window.__stub.release();
      await waitFor(() => $('notice').textContent.includes('input changed since detection'));
      await sleep(800);
      return {before, after: edited(), notice: $('notice').textContent};
    """)
        self.assertTrue(out["before"])
        self.assertTrue(out["after"])                                            # the edit survived the 409
        self.assertIn("input changed since detection", out["notice"])

    EDIT_JS = """
      const typeEdits = async () => {                                          // real inputs: they only mark dirty
        $('sizes').value = '24, 32'; $('sizes').dispatchEvent(new Event('input', {bubbles: true}));
        document.querySelector('tr[data-font] input.override').click();
        document.querySelector('tr.override input.ov-advanced-toggle').click();
        const cell = document.querySelector('tr.override [data-option="cell"]');
        cell.value = '9'; cell.dispatchEvent(new Event('input', {bubbles: true}));
      };
      const edits = () => ({sizes: $('sizes').value,                           // the override panel's open state is cosmetic
        cell: (document.querySelector('tr.override [data-option="cell"]') || {}).value});
    """

    def test_a_stale_run_keeps_the_typed_edits(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, self.EDIT_JS + """
      rules([{method: 'POST', path: '/run$', times: 1, hold: true, body: {error: 'the job changed while the run was being prepared: run again', stale: true}}]);
      $('run').click();
      await waitFor(() => count('POST /api/jobs/' + jid + '/run') === 1);
      await typeEdits();
      window.__stub.release();
      await waitFor(() => $('notice').textContent.includes('changed while the run'));
      await sleep(800);
      const kept = edits();
      $('run').click();                                                        // dirty is still true: the edits are saved first
      await waitFor(() => window.__stub.passed.some((p) => p.m === 'POST' && p.path.endsWith('/run') && p.status === 200));
      return {kept, puts: count('PUT /api/jobs/' + jid + '/settings')};
    """)
        self.assertEqual(out["kept"], {"sizes": "24, 32", "cell": "9"})
        self.assertEqual(out["puts"], 1)
        self.wait_done(jid)

    def test_a_run_409_after_the_job_left_detected_keeps_the_typed_edits(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, self.EDIT_JS + """
      rules([{method: 'POST', path: '/run$', times: 1, hold: true, body: {error: 'job ' + jid + ' is queued'}}]);
      $('run').click();
      await waitFor(() => count('POST /api/jobs/' + jid + '/run') === 1);
      await typeEdits();
      await window.__stub.realFetch('/api/jobs/' + jid + '/run', {method: 'POST'});   // the other run: the job leaves detected
      const detected = $('state').textContent;
      window.__stub.release();
      await waitFor(() => $('state').textContent !== detected, 30000);        // the page shows the job as it is now
      await sleep(500);
      return edits();
    """)
        self.assertEqual(out, {"sizes": "24, 32", "cell": "9"})
        self.wait_done(jid)

    def test_a_late_recovery_read_does_not_replace_newly_saved_settings(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      rules([{method: 'POST', path: '/run$', times: 1, body: {error: 'the job changed while the run was being prepared: run again', stale: true}},
             {method: 'GET', path: '/api/jobs/[0-9a-f]+$', times: 1, holdAfter: 'snap'}]);
      const before = $('sizes').value;
      $('run').click();                                                        // stale; its recovery read answers late
      await waitFor(() => window.__stub.rules[1].times === 0);                 // the read ran (its old snapshot is held back)
      await waitFor(() => $('notice').textContent.includes('changed while the run'));
      $('sizes').value = '24, 32'; $('sizes').dispatchEvent(new Event('input', {bubbles: true}));
      $('save').click();                                                       // a newer action: Save completes
      await waitFor(async () => (await (await window.__stub.realFetch('/api/jobs/' + jid)).json()).settings.batch.sizes.join() === '24,32');
      await sleep(500);
      window.__stub.release('snap');                                           // the old snapshot arrives
      await sleep(800);
      return {before, sizes: $('sizes').value};
    """)
        self.assertNotEqual(out["before"], "24, 32")
        self.assertEqual(out["sizes"], "24, 32")                                 # the saved value stayed

    # the recovery of a run conflict never rebuilds the form while it holds anything of the user's (t_6daa1bc7)
    LEFT_DETECTED = """
      const detected = $('state').textContent;
      rules([{method: 'POST', path: '/run$', times: 1, hold: true, body: {error: 'job ' + jid + ' is queued'}}]);
      $('run').click();
      await waitFor(() => count('POST /api/jobs/' + jid + '/run') === 1);
      const finish = async () => {
        await window.__stub.realFetch('/api/jobs/' + jid + '/run', {method: 'POST'});   // the other run: the job leaves detected
        window.__stub.release();
        await waitFor(() => $('state').textContent !== detected, 30000);              // the page shows the job as it is now
        await sleep(500);
      };
    """

    def test_a_focused_uncommitted_per_font_draft_survives_a_recovery(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, self.LEFT_DETECTED + """
      document.querySelector('tr[data-font] input.override').click();
      const sizes = document.querySelector('tr.override input.ov-sizes');
      sizes.focus(); sizes.value = '20'; sizes.dispatchEvent(new Event('input', {bubbles: true}));   // typed, not committed
      await finish();
      const now = document.querySelector('tr.override input.ov-sizes');
      return {value: now && now.value, focused: document.activeElement === now};
    """)
        self.assertEqual(out["value"], "20")
        self.assertTrue(out["focused"])
        self.wait_done(jid)

    def test_a_committed_unsaved_name_survives_a_recovery_and_is_what_save_sends(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      rules([{method: 'POST', path: '/run$', times: 1, hold: true, body: {error: 'the job changed while the run was being prepared: run again', stale: true}}]);
      $('run').click();
      await waitFor(() => count('POST /api/jobs/' + jid + '/run') === 1);
      const name = document.querySelector('input.name');
      name.value = 'MYNAME16.SVF'; name.dispatchEvent(new Event('change', {bubbles: true}));       // committed, not saved
      window.__stub.release();
      await waitFor(() => $('notice').textContent.includes('changed while the run'));
      await sleep(800);
      const shown = document.querySelector('input.name').value;
      $('save').click();
      await waitFor(() => window.__stub.passed.some((p) => p.m === 'PUT' && p.path.endsWith('/settings') && p.status === 200));
      const saved = (await (await window.__stub.realFetch('/api/jobs/' + jid)).json()).settings.fonts;
      return {shown, saved: Object.values(saved).map((f) => f.names).filter(Boolean)};
    """)
        self.assertEqual(out["shown"], "MYNAME16.SVF")
        self.assertTrue(any("MYNAME16.SVF" in n.values() for n in out["saved"]), out)

    def test_a_rebuild_shows_the_local_name_override(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      const name = document.querySelector('input.name');
      name.value = 'MYNAME16.SVF'; name.dispatchEvent(new Event('change', {bubbles: true}));
      document.querySelector('tr[data-font] input.override').click();
      const panel = document.querySelector('tr.override');
      const details = panel.querySelector('details.clipping');
      details.open = true; details.dispatchEvent(new Event('toggle'));
      await waitFor(() => /glyphs cut/.test(panel.querySelector('.clip-counts').textContent));
      [...panel.querySelectorAll('button')].find((b) => b.textContent === 'apply').click();   // rebuilds the font table
      await waitFor(() => $('notice').textContent.includes('save the settings to keep it'));
      return document.querySelector('input.name').value;
    """)
        self.assertEqual(out, "MYNAME16.SVF")

    def test_save_409_after_the_other_run_started_recovers_the_status_and_keeps_the_form(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      const detected = $('state').textContent;
      await window.__stub.realFetch('/api/jobs/' + jid + '/run', {method: 'POST'});          // another tab started the run
      rules([{method: 'POST', path: '/run$', times: 1, body: {error: 'job ' + jid + ' is queued'}},
             {method: 'GET', path: '/api/jobs/[0-9a-f]+$', times: 1, hold: 'rec'},          // the run conflict's recovery read
             {method: 'PUT', path: '/settings$', times: 1, body: {error: 'job ' + jid + ' is queued'}}]);
      $('run').click();
      await waitFor(() => window.__stub.rules[1].times === 0);
      $('sizes').value = '24, 32'; $('sizes').dispatchEvent(new Event('input', {bubbles: true}));
      $('save').click();                                                       // a newer action: it fails with a 409 too
      await waitFor(() => $('state').textContent !== detected, 30000);
      window.__stub.release('rec');                                            // the older recovery read comes late
      await waitFor(() => $('state').textContent.includes('written to'), 60000);
      return {sizes: $('sizes').value};
    """)
        self.assertEqual(out["sizes"], "24, 32")

    def test_a_partial_batch_size_and_a_new_destination_survive_a_recovery_and_the_409_stays(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, self.LEFT_DETECTED + """
      $('sizes').value = '24, 3'; $('sizes').dispatchEvent(new Event('input', {bubbles: true}));
      $('dest').value = '__new'; $('dest').dispatchEvent(new Event('change', {bubbles: true}));
      $('dest-new').value = 'abc/def'; $('dest-new').dispatchEvent(new Event('input', {bubbles: true}));
      await finish();
      return {sizes: $('sizes').value, dest: $('dest').value, destNew: $('dest-new').value, notice: $('notice').textContent};
    """)
        self.assertEqual((out["sizes"], out["dest"], out["destNew"]), ("24, 3", "__new", "abc/def"))
        self.assertIn("is queued", out["notice"])                                # the 409's reason is still there
        self.wait_done(jid)

    def test_following_the_other_run_keeps_typed_edits(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, self.EDIT_JS + """
      window.__busyBounds = {followMs: 200};
      rules([{method: 'POST', path: '/run$', times: 1, body: {error: 'a run of job ' + jid + ' is being prepared', busy: 'preparing'}}]);
      $('run').click();
      await waitFor(() => visible($('notice-retry')));
      await typeEdits();
      await window.__stub.realFetch('/api/jobs/' + jid + '/run', {method: 'POST'});   // the other run starts
      await waitFor(() => $('state').textContent.includes('written to'), 60000);
      return edits();
    """)
        self.assertEqual(out, {"sizes": "24, 32", "cell": "9"})

    def test_a_typed_name_draft_survives_a_recovery_a_poll_and_a_rebuild_and_is_what_save_sends(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, self.LEFT_DETECTED + """
      document.querySelector('tr[data-font] input.override').click();
      const panel = document.querySelector('tr.override');
      const details = panel.querySelector('details.clipping');
      details.open = true; details.dispatchEvent(new Event('toggle'));
      await waitFor(() => /glyphs cut/.test(panel.querySelector('.clip-counts').textContent));
      const name = document.querySelector('input.name');
      name.focus(); name.value = 'MYNAME16.SVF'; name.dispatchEvent(new Event('input', {bubbles: true}));   // a draft: no change yet
      await finish();
      await sleep(2600);                                                       // past a poll
      const live = document.querySelector('input.name');                      // the field as it is now (rebuilt or not)
      const draft = live.value;
      live.blur(); live.dispatchEvent(new Event('change', {bubbles: true}));   // blur: `change` commits the draft
      [...panel.querySelectorAll('button')].find((b) => b.textContent === 'apply').click();   // rebuilds the font table
      await waitFor(() => $('notice').textContent.includes('save the settings to keep it'));
      const shown = document.querySelector('input.name').value;
      $('save').click();
      await waitFor(() => window.__stub.sent.includes('PUT /api/jobs/' + jid + '/settings'));
      const at = window.__stub.sent.lastIndexOf('PUT /api/jobs/' + jid + '/settings');
      const sentNames = Object.values(JSON.parse(window.__stub.bodies[at]).fonts).map((f) => f.names).filter(Boolean);
      return {shown, draft, sentNames};
    """)
        self.assertEqual(out["draft"], "MYNAME16.SVF")                           # the recovery left the draft in its field
        self.assertEqual(out["shown"], "MYNAME16.SVF")
        self.assertTrue(any("MYNAME16.SVF" in n.values() for n in out["sentNames"]), out)
        self.wait_done(jid)

    def test_a_focused_untouched_field_does_not_keep_stale_settings_after_a_recovery(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      rules([{method: 'POST', path: '/run$', times: 1, hold: true, body: {error: 'the job changed while the run was being prepared: run again', stale: true}}]);
      $('run').click();
      await waitFor(() => count('POST /api/jobs/' + jid + '/run') === 1);
      const j = await (await window.__stub.realFetch('/api/jobs/' + jid)).json();      // another tab saves other sizes
      j.settings.batch.sizes = [20];
      await window.__stub.realFetch('/api/jobs/' + jid + '/settings', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(j.settings)});
      $('sizes').focus();                                                      // an untouched field merely has focus
      window.__stub.release();
      await waitFor(() => $('notice').textContent.includes('changed while the run'));
      await sleep(800);
      const shown = $('sizes').value;
      $('run').click();                                                        // clean: runs what the page shows
      await waitFor(() => window.__stub.passed.some((p) => p.m === 'POST' && p.path.endsWith('/run') && p.status === 200));
      return {shown, puts: count('PUT /api/jobs/' + jid + '/settings')};
    """)
        self.assertEqual(out["shown"], "20")
        self.assertEqual(out["puts"], 0)
        self.wait_done(jid)

    def test_a_save_refused_by_validation_still_recovers_the_job_status(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      const detected = $('state').textContent;
      await window.__stub.realFetch('/api/jobs/' + jid + '/run', {method: 'POST'});          // another tab started the run
      rules([{method: 'POST', path: '/run$', times: 1, body: {error: 'job ' + jid + ' is queued'}},
             {method: 'GET', path: '/api/jobs/[0-9a-f]+$', times: 1, hold: 'rec'}]);        // the run conflict's recovery read
      $('run').click();
      await waitFor(() => window.__stub.rules[1].times === 0);
      document.querySelector('tr[data-font] input.override').click();
      document.querySelector('tr.override input.ov-advanced-toggle').click();
      const cell = document.querySelector('tr.override [data-option="cell"]');
      cell.value = 'abc'; cell.dispatchEvent(new Event('input', {bubbles: true}));
      $('save').click();                                                       // refused locally: not a number
      await waitFor(() => $('state').textContent !== detected, 30000);
      window.__stub.release('rec');
      await waitFor(() => $('state').textContent.includes('written to'), 60000);
      return {notice: $('notice').textContent, puts: count('PUT /api/jobs/' + jid + '/settings'), cell: cell.value};
    """)
        self.assertIn("must be numbers", out["notice"])
        self.assertEqual(out["puts"], 0)
        self.assertEqual(out["cell"], "abc")

    def test_a_stale_probe_drawing_is_not_drawn_after_another_size_was_chosen(self):
        jid = self.local_job()
        job = self.job(jid)
        ttf = next(f["id"] for f in job["fonts"] if f["path"] == "Munjo.ttf")
        st = job["settings"]
        st["fonts"][ttf].update(selected=True, dest="dos", kinds=["precomposed"], sizes=[16, 17], bpp=[1])
        self.assertEqual(self.api("PUT", "/api/jobs/%s/settings" % jid, st)[0], 200)
        out = self.busy_drive(jid, """
      rules([{method: 'GET', path: '[.]wasm$', times: 1, hold: 'wasm'}]);      // the renderer module is not ready: draws queue up
      document.querySelector('tr[data-font] input.override').click();
      const panel = document.querySelector('tr.override');
      const wrap = panel.querySelector('.canvaswrap');
      let frames = 0;
      new MutationObserver((list) => { for (const m of list) for (const n of m.addedNodes) if (n.classList && n.classList.contains('clip-frame')) frames++; })
        .observe(wrap, {childList: true});
      const details = panel.querySelector('details.clipping');
      details.open = true; details.dispatchEvent(new Event('toggle'));       // size 16: its drawing is queued
      const counts = panel.querySelector('.clip-counts');
      await waitFor(() => /glyphs cut/.test(counts.textContent));
      const size = panel.querySelector('select[aria-label="clipping size"]');
      size.value = '17'; size.dispatchEvent(new Event('change', {bubbles: true}));   // size 17 queues its own
      await sleep(1000);
      window.__stub.release('wasm');
      await waitFor(() => wrap.querySelector('.clip-frame'), 30000);
      await sleep(1500);
      return {frames, counts: counts.textContent};
    """)
        self.assertEqual(out["frames"], 1)                                       # only the newer size was drawn
        self.assertNotIn("(", out["counts"])                                     # and no error was appended

    def test_busy_create_sources_and_detect_are_each_retried_once(self):
        out = self.drive(self.typed_script("""
      window.__stub.rules.push({method: 'POST', path: '/api/jobs$', times: 1, body: {error: 'job x is busy; try again', busy: 'lock', job: 'x'}},
                               {method: 'PUT', path: '/sources$', times: 1, body: {error: 'job x is busy; try again', busy: 'lock'}},
                               {method: 'POST', path: '/detect$', times: 1, body: {error: 'job x is busy; try again', busy: 'lock'}});
      await detectOnce();
      const sent = window.__stub.sent;
      const n = (m, re) => sent.filter((s) => s.startsWith(m + ' ') && re.test(s)).length;
      return {create: n('POST', /\\/api\\/jobs$/), sources: n('PUT', /\\/sources$/), detect: n('POST', /\\/detect$/),
              rows: rows().length};
    """), preload=self.BUSY_STUB)
        self.assertEqual((out["create"], out["sources"], out["detect"]), (2, 2, 2))
        self.assertGreaterEqual(out["rows"], 5)
        self.assertEqual(len(self.srv.store.list()), 1)

    def test_other_409s_are_unchanged(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      const notices = [];
      for (const error of ['job ' + jid + ' is queued', 'cleanup pending: the earlier files are still being removed']) {
        rules([{method: 'POST', path: '/run$', times: 1, body: {error, job: jid}}]);
        $('run').click();
        await waitFor(() => $('notice').textContent.includes(error));
        notices.push($('notice').textContent);
        await sleep(2500);                                                  // a retry would have shown by now
      }
      return {notices, runs: count('POST /api/jobs/' + jid + '/run'), retry: visible($('notice-retry')),
              retrying: window.__notices.some((t) => t.includes('retrying'))};
    """)
        self.assertEqual(out["notices"], ["POST /api/jobs/%s/run: HTTP 409: job %s is queued" % (jid, jid),
                                          "POST /api/jobs/%s/run: HTTP 409: cleanup pending: the earlier files are still "
                                          "being removed" % jid])
        self.assertEqual(out["runs"], 2)
        self.assertFalse(out["retry"])
        self.assertFalse(out["retrying"])

    def test_the_create_path_busy_answer_is_not_retried(self):
        out = self.drive(self.typed_script("""
      window.__stub.rules.push({method: 'POST', path: '/api/jobs$', times: 1, body: {error: 'job y is busy; try again'}});
      document.getElementById('detect-local').click();
      await sleep(300);
      if (visible(document.getElementById('ack'))) document.getElementById('ack-ok').click();
      await waitFor(() => document.getElementById('notice').textContent.includes('job y is busy'));
      await sleep(2500);
      return {notice: document.getElementById('notice').textContent,
              sent: window.__stub.sent.filter((s) => s === 'POST /api/jobs').length,
              retry: visible(document.getElementById('notice-retry')),
              retrying: window.__notices.some((t) => t.includes('retrying'))};
    """), preload=self.BUSY_STUB)
        self.assertEqual(out["notice"], "POST /api/jobs: HTTP 409: job y is busy; try again")
        self.assertEqual(out["sent"], 1)
        self.assertFalse(out["retry"])
        self.assertFalse(out["retrying"])

    def test_another_action_drops_the_try_again_control(self):
        jid = self.local_job()
        out = self.busy_drive(jid, """
      rules([{method: 'DELETE', path: '/api/jobs/[0-9a-f]+$', times: 4, body: lock(jid)}]);
      $('delete-job').click();
      await waitFor(() => visible($('notice-retry')));
      $('save').click();
      await sleep(3000);
      return {retry: visible($('notice-retry')), del: count('DELETE /api/jobs/' + jid)};
    """)
        self.assertFalse(out["retry"])
        self.assertEqual(out["del"], 4)
        self.assertEqual(self.api("GET", "/api/jobs/%s" % jid)[0], 200)

    def test_an_action_during_a_sleeping_retry_cancels_it(self):
        jid = self.local_job()
        out = self.busy_drive(jid, """
      window.__busyBounds = {sleep: () => new Promise((res) => { window.__wake = res; })};   // the retry sleeps until woken
      rules([{method: 'DELETE', path: '/api/jobs/[0-9a-f]+$', times: 4, body: lock(jid)}]);
      $('delete-job').click();
      await waitFor(() => window.__wake);
      const n0 = count('DELETE /api/jobs/' + jid);
      $('save').click();                                                       // an action starts during the sleep
      await sleep(300);
      window.__wake();
      await sleep(500);
      return {after: count('DELETE /api/jobs/' + jid) - n0, notice: $('notice').textContent, retry: visible($('notice-retry'))};
    """)
        self.assertEqual(out["after"], 0)
        self.assertNotIn("retrying", out["notice"])
        self.assertFalse(out["retry"])
        self.assertEqual(self.api("GET", "/api/jobs/%s" % jid)[0], 200)


    def test_an_action_while_the_first_answer_is_pending_cancels_the_retry(self):
        jid = self.local_job()
        out = self.busy_drive(jid, """
      window.__busyBounds = {sleep: () => new Promise(() => {})};              // a retry line would then stay for ever
      rules([{method: 'DELETE', path: '/api/jobs/[0-9a-f]+$', times: 4, hold: true, body: lock(jid)}]);
      $('delete-job').click();
      await waitFor(() => count('DELETE /api/jobs/' + jid) === 1);
      $('save').click();                                                       // an action starts while the answer is pending
      await sleep(300);
      window.__stub.release();                                                 // ... then the busy answer arrives
      await sleep(500);
      return {del: count('DELETE /api/jobs/' + jid), retry: visible($('notice-retry')), notice: $('notice').textContent};
    """)
        self.assertEqual(out["del"], 1)                                          # the late busy answer sent nothing more
        self.assertFalse(out["retry"])                                           # ... installed no button
        self.assertNotIn("retrying", out["notice"])                              # ... and wrote no retry line
        self.assertEqual(self.api("GET", "/api/jobs/%s" % jid)[0], 200)


    def test_a_sleep_that_crosses_the_deadline_sends_nothing_and_offers_try_again(self):
        jid = self.local_job()
        out = self.busy_drive(jid, """
      window.__t = 0;                                                          // a controlled clock; each sleep adds 500
      window.__busyBounds = {totalMs: 1000, retryMs: [20, 20, 20], now: () => window.__t,
                             sleep: async (ms) => { window.__t += 500; await new Promise((res) => setTimeout(res, ms)); }};
      rules([{method: 'DELETE', path: '/api/jobs/[0-9a-f]+$', times: 1, hold: true, body: lock(jid)}]);
      $('delete-job').click();
      await waitFor(() => count('DELETE /api/jobs/' + jid) === 1);
      window.__t = 900;                                                        // before the deadline when the answer comes ...
      window.__stub.release();                                                 // ... and past it when the 20 ms sleep ends
      await waitFor(() => visible($('notice-retry')));
      await sleep(300);
      return {del: count('DELETE /api/jobs/' + jid), retry: visible($('notice-retry'))};
    """)
        self.assertEqual(out["del"], 1)
        self.assertTrue(out["retry"])
        self.assertEqual(self.api("GET", "/api/jobs/%s" % jid)[0], 200)


    def test_a_stale_run_reloads_the_job_without_retry(self):
        jid = self.ready_job()
        out = self.busy_drive(jid, """
      rules([{method: 'POST', path: '/run$', times: 1, body: {error: 'the job changed while the run was being prepared: run again', stale: true}}]);
      $('run').click();
      await sleep(1500);
      const sent = window.__stub.sent;
      const at = sent.indexOf('POST /api/jobs/' + jid + '/run');
      return {runs: count('POST /api/jobs/' + jid + '/run'), reloaded: sent.slice(at + 1).includes('GET /api/jobs/' + jid),
              retry: visible($('notice-retry')), notice: $('notice').textContent};
    """)
        self.assertEqual(out["runs"], 1)
        self.assertTrue(out["reloaded"])
        self.assertFalse(out["retry"])
        self.assertEqual(out["notice"], "POST /api/jobs/%s/run: HTTP 409: the job changed while the run was being "
                                        "prepared: run again" % jid)


if __name__ == "__main__":
    unittest.main()
