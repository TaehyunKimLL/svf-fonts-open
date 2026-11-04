#!/usr/bin/env python3
"""The page's one browser check: headless Chrome loads a finished job and the DOM must show the result face drawn.

Not a unittest (the name does not match test_*.py): it needs a browser and the built module.

  python3 maker/test/smoke_dom.py

Starts the maker on 127.0.0.1:0 over a temp data dir, builds maker/static/wasm/ with maker/build-wasm.sh when it is
missing, uploads ttf/neodgm/neodgm.ttf with its licence, runs one precomposed 16 px 1 bpp face, then (up to 10 times, 2 s
apart) dumps the DOM (with a virtual-time budget: a plain --dump-dom is taken at the load event, before the page's
fetches and the module have run) of http://127.0.0.1:PORT/?job=ID until the result canvas of step s01 has data-drawn="1", a
data-ink above 0 and no data-error. Exit 0 on success, 1 on timeout (the last DOM line is printed), 77 when there is no
browser or no emcc (skip).
"""

import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
MAKER_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import server  # noqa: E402

BROWSERS = ("google-chrome", "chromium-browser")
ATTEMPTS = 10
PAUSE_S = 2
JOB_WAIT_S = 180


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=JOB_WAIT_S)
    try:
        conn.request(method, path, body=body)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def api(port, method, path, obj=None):
    body = None if obj is None else json.dumps(obj).encode()
    status, data = request(port, method, path, body)
    if status != 200:
        raise RuntimeError("%s %s: %d %s" % (method, path, status, data[:200]))
    return json.loads(data)


def put_file(port, job, rel, path):
    with open(path, "rb") as f:
        status, data = request(port, "PUT", "/api/jobs/%s/files?path=%s" % (job, urllib.parse.quote(rel, safe="")),
                               f.read())
    if status != 200:
        raise RuntimeError("upload %s: %d %s" % (rel, status, data[:200]))


def ready_line(dom):
    """The <canvas ... data-step="s01"> tag of @p dom, or None."""
    for tag in re.findall(r"<canvas[^>]*>", dom):
        if 'data-step="s01"' in tag:
            return tag
    return None


def ok(tag):
    if not tag or 'data-error' in tag or 'data-drawn="1"' not in tag:
        return False
    m = re.search(r'data-ink="(\d+)"', tag)
    return bool(m) and int(m.group(1)) > 0


def main():
    browser = next((shutil.which(name) for name in BROWSERS if shutil.which(name)), None)
    if not browser:
        print("smoke_dom: no google-chrome or chromium-browser: skipped")
        return 77
    wasm = os.path.join(MAKER_DIR, "static", "wasm", "svf.wasm")
    if not os.path.isfile(wasm):
        r = subprocess.run(["bash", os.path.join(MAKER_DIR, "build-wasm.sh")], capture_output=True, text=True)
        if r.returncode != 0:
            print("smoke_dom: build-wasm.sh failed (no emcc?): skipped\n" + r.stderr)
            return 77
    tmp = tempfile.mkdtemp(prefix="svf-smoke-")
    srv = server.make_server("127.0.0.1", 0, REPO, os.path.join(tmp, "data"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        job = api(port, "POST", "/api/jobs")["id"]
        put_file(port, job, "neodgm/neodgm.ttf", os.path.join(REPO, "ttf", "neodgm", "neodgm.ttf"))
        put_file(port, job, "neodgm/LICENSE.txt", os.path.join(REPO, "ttf", "neodgm", "LICENSE.txt"))
        detected = api(port, "POST", "/api/jobs/%s/detect" % job)
        s = detected["settings"]
        font = next(f["id"] for f in detected["fonts"] if f["path"].endswith("neodgm.ttf"))
        for fid, per in s["fonts"].items():
            per["selected"] = fid == font
            per["dest"] = "new/smoke"
        s["fonts"][font].update(kinds=["precomposed"], sizes=[16], bpp=[1])
        api(port, "PUT", "/api/jobs/%s/settings" % job, s)
        api(port, "POST", "/api/jobs/%s/run" % job)
        deadline = time.monotonic() + JOB_WAIT_S
        while time.monotonic() < deadline:
            state = api(port, "GET", "/api/jobs/%s" % job)
            if state["state"] in ("done", "failed"):
                break
            time.sleep(0.2)
        if state["state"] != "done":
            print("smoke_dom: the job ended %s: %s" % (state["state"], state.get("error")))
            return 1
        url = "http://127.0.0.1:%d/?job=%s" % (port, job)
        profile = os.path.join(tmp, "chrome")
        last = None
        for _ in range(ATTEMPTS):
            r = subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--user-data-dir=" + profile,
                                "--virtual-time-budget=8000", "--dump-dom", url], capture_output=True, text=True, timeout=120)
            last = ready_line(r.stdout)
            if ok(last):
                print("smoke_dom: " + last)
                return 0
            time.sleep(PAUSE_S)
        print("smoke_dom: timeout, last canvas: %s" % last)
        return 1
    finally:
        srv.shutdown()
        srv.server_close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
