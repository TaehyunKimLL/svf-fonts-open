#!/usr/bin/env python3
"""The maker page in headless Chrome (driven over the DevTools protocol by pagedrive.mjs, node's WebSocket): the page
behaviours no Python test can see. Skipped without google-chrome / chromium-browser, node or the built module.

  python3 -m unittest discover -s maker/test -p test_page_dom.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
import http.client

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(TEST_DIR)
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, TEST_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import fixtures  # noqa: E402
import inputfx  # noqa: E402
import server  # noqa: E402

DRIVER = os.path.join(TEST_DIR, "pagedrive.mjs")
WAIT_S = 240


def read_report(srv, job, step):
    with open(srv.store.path(job, step["report"]), encoding="utf-8") as f:
        return json.load(f)


def browser():
    return next((shutil.which(n) for n in ("google-chrome", "chromium-browser") if shutil.which(n)), None)


def read(path):
    with open(path, "rb") as f:
        return f.read()


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

    def dos_job(self, run):
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
        if run:
            s = self.api("GET", "/api/jobs/" + job)["settings"]
            s["fonts"][self.font].update(selected=True, dest="new/dom", licence={"kind": "text", "text": "OFL"},
                                         licence_name="OFL.TXT", note_name="NOTE.TXT")
            self.api("PUT", "/api/jobs/%s/settings" % job, s)
            self.api("POST", "/api/jobs/%s/run" % job)
            self.assertEqual(self.wait_done(job)["state"], "done")
        return job

    def drive(self, job, script):
        script = script.replace("FONTID", getattr(self, "font", ""))
        fd, path = tempfile.mkstemp(suffix=".js", dir=self.tmp)
        with os.fdopen(fd, "w") as f:
            f.write(script)
        r = subprocess.run(["node", DRIVER, self.chrome, "http://127.0.0.1:%d/?job=%s" % (self.port, job), path],
                           capture_output=True, text=True, timeout=WAIT_S)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    # ---- tests ------------------------------------------------------------------------------------------------

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
const rows = panel.querySelectorAll('.clip-row').length;
const bands = panel.querySelectorAll('.clip-band').length;
[...panel.querySelectorAll('button')].find((b) => b.textContent === 'apply').click();
await sleep(500);
document.getElementById('save').click();
await sleep(1500);
return {first, second, rows, bands, ink: canvas.dataset.ink};
""")
        self.assertRegex(out["first"]["counts"], r"^\d+ glyphs cut")
        self.assertNotEqual(out["first"]["counts"], out["second"])               # the count follows the ascent typed
        self.assertIn("glyphs cut", out["second"])
        self.assertGreater(out["rows"], 0)                                      # a 15-row ink in a 12-row cell
        self.assertGreater(out["bands"], 0)                                     # the cut rows are tinted on the probe face
        self.assertGreater(int(out["ink"]), 0)
        mk = self.api("GET", "/api/jobs/" + job)["settings"]["fonts"][font]["options"]["mkfont"]
        self.assertEqual((mk["ascent"], mk["clip_cell"]), (12, True))

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


if __name__ == "__main__":
    unittest.main()
