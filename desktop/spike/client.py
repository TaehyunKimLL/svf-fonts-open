#!/usr/bin/env python3
"""Drive one local job through a running maker (frozen or source) over HTTP; prints the job's end state."""
import http.client, json, os, sys, time, shutil

port, token, src, out = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]


def api(method, path, obj=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
    body = None if obj is None else json.dumps(obj).encode()
    conn.request(method, path, body=body, headers={"X-Maker-Token": token, "Content-Type": "application/json"})
    r = conn.getresponse()
    data = r.read()
    conn.close()
    try:
        return r.status, json.loads(data)
    except ValueError:
        return r.status, data


st, body = api("POST", "/api/jobs", {"source": "local", "output_dir": out}); assert st == 200, body
jid = body["id"]
st, body = api("PUT", "/api/jobs/%s/sources" % jid, {"paths": [src]}); assert st == 200, body
st, body = api("POST", "/api/jobs/%s/detect" % jid); assert st == 200, body
job = api("GET", "/api/jobs/%s" % jid)[1]
fid = job["fonts"][0]["id"]
print("font:", job["fonts"][0]["label"], job["fonts"][0]["source_kind"])
s = job["settings"]
s["fonts"][fid].update(selected=True, dest="dos", kinds=["precomposed"], sizes=[16], bpp=[1])
st, body = api("PUT", "/api/jobs/%s/settings" % jid, s); assert st == 200, body
st, body = api("GET", "/api/jobs/%s/probe/%s/16/1.json" % (jid, fid)); print("probe:", st)
t0 = time.monotonic()
st, body = api("POST", "/api/jobs/%s/run" % jid); assert st == 200, body
while True:
    job = api("GET", "/api/jobs/%s" % jid)[1]
    if job["state"] in ("done", "failed"):
        break
    time.sleep(0.2)
print("state:", job["state"], job.get("error"), "in %.1f s" % (time.monotonic() - t0))
for step in job["steps"]:
    print(" step", step["id"], step["kind"], step["state"], step.get("exit"), [a[:3] for a in step.get("argv") or []])
print("files:", job["result"]["files"] if job.get("result") else None)
st, data = api("GET", "/api/jobs/%s/face/%s.svf" % (jid, job["steps"][-1]["id"]))
print("face GET:", st, len(data) if isinstance(data, bytes) else data)
