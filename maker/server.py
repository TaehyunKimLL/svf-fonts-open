#!/usr/bin/env python3
"""The SVF maker's HTTP server: the JSON API, the previews, the zip and the static page.

`make_server` builds the job `Store`, the `Worker` (recovered and started) and a `ThreadingHTTPServer` whose
`Handler` serves the routes the plan's Task 13 lists. `main` reads `SVF_MAKER_REPO`, `SVF_MAKER_DATA` and
`SVF_MAKER_BIND` and serves forever.

  SVF_MAKER_REPO=... SVF_MAKER_DATA=... SVF_MAKER_BIND=host:port python3 -P maker/server.py
"""

import os, sys
MAKER_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(MAKER_DIR)
for _p in (MAKER_DIR, os.path.join(REPO_DIR, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import atexit
import contextlib
import datetime
import glob
import hmac
import http.server
import ipaddress
import json
import re
import shutil
import signal
import socket
import subprocess
import stat
import tempfile
import threading
import time
import traceback
import urllib.parse

import archive
import caps
import detect
import jobs
import naming
import preview
import routes
import settings
import sources as sourcesmod
import zipout
from sources import Sources

# The spec's upload limits (Global Constraints).
BODY_CAP = 67108864
JOB_CAP = 268435456
FILE_CAP = 2000

CHUNK = 1 << 20                          # the upload body is read in 1 MB chunks
LOCAL_IDLE_SWEEP_S = 1800                 # a `detected` local job untouched this long loses its files directory
STATIC_TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".png": "image/png",
                ".wasm": "application/wasm"}
UPLOAD_TMP = ".upload-"                   # `_receive`'s temp files: never counted as uploads (they are in flight)
IDLE_TIMEOUT = 60                        # seconds a socket may hold a read open (W8: 60 s idle per read)
JSON_DEPTH = 200                         # the deepest a settings body may nest before it is refused (W5)
HOST_HEADER_MAX = 256                    # a Host/Origin header longer than this is not one of ours
_STATE_CHANGERS = ("PUT", "POST", "DELETE")   # the requests W9 checks Host and Origin on

# One bake/render at a time per (job, font): two requests for one font must not bake into one face, and a render must
# not read a face while another writes it (Task 10's `preview.py` locks its own cache, not this file name).
_PREVIEW_LOCKS = {}
_PREVIEW_GUARD = threading.Lock()


def _preview_lock(job_id, font_id):
    with _PREVIEW_GUARD:
        lock = _PREVIEW_LOCKS.get((job_id, font_id))
        if lock is None:
            lock = _PREVIEW_LOCKS[(job_id, font_id)] = threading.Lock()
        return lock


@contextlib.contextmanager
def _sweep_locks(job):
    """Hold the preview locks of every font of @p job while its files directory is swept (the store's `on_sweep`)."""
    with contextlib.ExitStack() as stack:
        for font_id in dict.fromkeys(font.get("id") for font in job.get("fonts") or []):
            if font_id:
                stack.enter_context(_preview_lock(job["id"], font_id))
        yield


def _sweep_idle(server, now=None):
    """Sweep the files directory of every `detected` local job nobody touched for `LOCAL_IDLE_SWEEP_S`."""
    now = time.monotonic() if now is None else now
    for item in server.store.list():
        if item.get("source") != "local" or item["state"] != "detected":
            continue
        if now - server.touched.get(item["id"], server.started) > LOCAL_IDLE_SWEEP_S:
            try:
                server.store.sweep_files(server.store.load(item["id"]))
            except KeyError:
                continue


def _drop_preview_locks(job_id):
    """Forget @p job_id's per-font preview locks (its directory is gone: `DELETE` and `retain`, W13)."""
    with _PREVIEW_GUARD:
        for key in [key for key in _PREVIEW_LOCKS if key[0] == job_id]:
            _PREVIEW_LOCKS.pop(key, None)


class _HttpError(Exception):
    """An API error: the status and message `send_json` answers with, plus any extra body keys (e.g. `errors`)."""

    def __init__(self, status, message, extra=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.extra = extra or {}


def _count_dir(root):
    """`(files, bytes)` of the regular files under @p root (`lstat`: a symlink is never followed).

    `_receive`'s in-flight temp files (`UPLOAD_TMP`) are skipped: a concurrent upload's bytes are held by its
    reservation, and counting its temp file here would count them twice (W4).
    """
    count = 0
    total = 0
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            if name.startswith(UPLOAD_TMP):
                continue
            try:
                st = os.lstat(os.path.join(dirpath, name))
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                count += 1
                total += st.st_size
    return count, total


def _inside(root, path):
    """True when @p path (`realpath`d) is @p root itself or below it."""
    resolved = os.path.realpath(path)
    root = os.path.realpath(root)
    return resolved == root or resolved.startswith(root + os.sep)


def _os_reason(exc):
    """A short reason from an `OSError` (a path the filesystem refuses: `ENAMETOOLONG` and friends, W5)."""
    return exc.strerror or type(exc).__name__


def _bind(bind):
    """`(host, port)` from a `host:port` string: no host means 127.0.0.1, an IPv6 host loses its brackets (W11)."""
    host, _, port = bind.rpartition(":")
    host = host or "127.0.0.1"
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host, int(port)


CSP = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; img-src 'self' blob: data:; "
       "font-src 'self'; style-src 'self'")
_TOKEN_RE = re.compile(r"\A[0-9a-f]{32}\Z")


class LocalModeError(ValueError):
    """A local-mode start-up refusal (a bad token, a non-loopback bind): `main` prints its message and exits 2."""


def _unbracket(host):
    host = str(host).strip()
    return host[1:-1] if host.startswith("[") and host.endswith("]") else host


_LOOPBACKS = (ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1"))


def _is_loopback(host):
    """True for 127.0.0.1 and ::1 (bracketed or not); `localhost` only when every address it resolves to is one of
    those; any other name, and the rest of 127.0.0.0/8, no."""
    host = _unbracket(host)
    try:
        return ipaddress.ip_address(host) in _LOOPBACKS
    except ValueError:
        pass
    if host.lower() != "localhost":
        return False
    try:
        found = socket.getaddrinfo(host, None)
        return bool(found) and all(ipaddress.ip_address(item[4][0].split("%")[0]) in _LOOPBACKS for item in found)
    except (OSError, ValueError):
        return False


def _parse_token(value):
    """The per-launch token as bytes (32 lower-case hex characters), or None for no token (D2: its presence is local mode)."""
    if value is None or value == "":
        return None
    if not _TOKEN_RE.match(value):
        raise LocalModeError("SVF_MAKER_TOKEN: 32 hex characters")
    return value.encode("ascii")


def _split_host(header):
    """`(hostname, port)` of a `Host`/`Origin` authority: lower-cased, brackets stripped, port `None` or an int."""
    try:
        split = urllib.parse.urlsplit("//" + header)
        return (split.hostname or "").lower().rstrip("."), split.port
    except ValueError:                                   # a malformed port is not a host we serve
        return "", None


def _json_depth(data):
    """The deepest `[`/`{` nesting of @p data, ignoring the ones inside strings (W5)."""
    depth = 0
    best = 0
    in_string = False
    escaped = False
    for byte in data:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:                            # backslash
                escaped = True
            elif byte == 0x22:                            # quote
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x5B, 0x7B):                        # [ {
            depth += 1
            best = max(best, depth)
        elif byte in (0x5D, 0x7D) and depth:              # ] }
            depth -= 1
    return best


def _preview_glob(store, job, font_id):
    """The `work/preview/` entries that belong to @p font_id (`<id>`, `<id>.*`, the `<id>/` directory).

    The id is matched whole (Y7): clearing `f10` must never touch `f100`'s preview.
    """
    base = os.path.join(store.files_dir(job), "work", "preview", glob.escape(str(font_id)))
    return glob.glob(base) + glob.glob(base + ".*")


def _remove_preview(store, job, font_id):
    """Remove every derived preview file of @p font_id of @p job (the loaded job); the caller holds that font's
    preview lock (W2)."""
    for path in _preview_glob(store, job, font_id):
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                pass


_PREVIEW_KEYS = ("dos_layout", "sizes", "kinds", "bpp", "range", "preset", "latin_companion", "instance",
                 "experimental", "jamo_route")
_PREVIEW_OPTIONS = {"mkfont": ("cell", "width", "latin", "mono_hint", "space_advance"),
                    "jamoset": ("jset_version", "jamo_ascent", "embolden", "symbols")}


def preview_inputs(eff):
    """The effective values a derived preview file (source PNG or face, probe) depends on (spec 6.5). Not keys:
    mkfont ascent / clip_cell / fit_cell (the page applies them to the probe data), dy (applied live), aa_refine,
    clean, binarize and the bdfface options."""
    out = {key: eff.get(key) for key in _PREVIEW_KEYS}
    options = eff.get("options") or {}
    for tool, keys in _PREVIEW_OPTIONS.items():
        sub = options.get(tool) or {}
        for key in keys:
            out["options.%s.%s" % (tool, key)] = sub.get(key)
    return out


def _changed_preview_fonts(fonts, before, after):
    """The font ids whose effective preview inputs differ between the two settings (W2)."""
    changed = []
    for font in fonts:
        font_id = font.get("id")
        try:
            old = settings.effective(fonts, before, font_id)
            new = settings.effective(fonts, after, font_id)
        except KeyError:
            continue
        if preview_inputs(old) != preview_inputs(new):
            changed.append(font_id)
    return changed


def _is_upload_tmp(rel):
    """True when @p rel names `_receive`'s temp file (a `.upload-*` component): never a real upload (Y3)."""
    return any(part.startswith(UPLOAD_TMP) for part in str(rel or "").replace(os.sep, "/").split("/"))


def _kept_settings(old, fonts, old_fonts, roots=None, old_roots=None, local=False):
    """`settings.defaults(fonts)` with the owner's earlier settings kept: the batch and every font still there.

    `POST detect` may run again on a job the owner already edited (S1: a failed or done job is re-detected), so the
    edit must survive the re-scan. The ids are positional (`f01`, `f02`, ... in path order), so a new upload that
    sorts earlier renumbers every font: an old per-font entry is remapped to the new id by the font's own path and
    face (Y2), never by the id. A path the new scan no longer has is dropped; a new one gets its defaults.

    A local job passes its `roots` and the `old_roots` of the earlier scan (lists of `{"path": ...}`): a font is
    then keyed by `(root path, path, face)`, and every root-indexed setting follows its root by path: a licence
    `{"kind": "upload", "root": i}`, a per-font `range_root` and the batch `range_root`. A root that is gone
    gives the licence its fresh default and drops the range (the batch's range falls back to its default).
    """
    fresh = settings.defaults(fonts, local=True) if local else settings.defaults(fonts)
    if not isinstance(old, dict):
        return fresh
    is_local = roots is not None and old_roots is not None

    def rootpath(table, entry):
        try:
            return table[entry.get("root")]["path"]
        except (KeyError, IndexError, TypeError):
            return None

    def key_of(entry, table):
        if is_local:
            return (rootpath(table, entry), entry.get("path"), entry.get("face_index"))
        return (entry.get("path"), entry.get("face_index"))

    new_index = {}
    if is_local:
        for i, item in enumerate(roots):
            new_index.setdefault(item.get("path"), i)

    def remap_root(old_root):
        """The new index of the root the old index named, or None when that root is gone."""
        try:
            return new_index.get(old_roots[old_root]["path"])
        except (KeyError, IndexError, TypeError):
            return None

    old_batch = old.get("batch")
    if isinstance(old_batch, dict) and all(key in old_batch for key in settings.BATCH_KEYS):
        fresh["batch"] = dict(old_batch) if is_local else old_batch
        old_range = old_batch.get("range")
        if is_local and isinstance(old_range, str) and old_range not in settings.NAMED_RANGE_NAMES:
            moved = remap_root(old_batch.get(settings.RANGE_ROOT_KEY, 0))
            if moved is None:
                fresh["batch"].pop(settings.RANGE_ROOT_KEY, None)
                fresh["batch"]["range"] = settings.defaults(fonts)["batch"]["range"]
            else:
                fresh["batch"][settings.RANGE_ROOT_KEY] = moved
    old_per_font = old.get("fonts")
    if not isinstance(old_per_font, dict):
        return fresh
    old_by_key = {}
    for entry in old_fonts or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            continue
        per = old_per_font.get(entry.get("id"))
        if isinstance(per, dict):
            old_by_key[key_of(entry, old_roots)] = per
    old_key_by_id = {entry.get("id"): key_of(entry, old_roots) for entry in old_fonts or [] if isinstance(entry, dict)}
    new_id_by_key = {key_of(font, roots): font.get("id") for font in fonts}
    for font in fonts:
        fid = font.get("id")
        per = old_by_key.get(key_of(font, roots))
        if per is None or fid not in fresh["fonts"]:
            continue
        per = dict(per)
        if "latin_companion" in per:                # an id too: remap it by path, else fall back to the default (Z1)
            new = new_id_by_key.get(old_key_by_id.get(per["latin_companion"]))
            if per["latin_companion"] is not None:
                per["latin_companion"] = new if new in (font.get("companions") or []) else \
                    fresh["fonts"][fid].get("latin_companion")
        if "instance" in per:                       # an instance stays only while the font still has those axes
            per["instance"] = per["instance"] if _instance_fits(font, per["instance"]) else None
        if is_local:
            licence = per.get("licence")
            if isinstance(licence, dict) and licence.get("kind") == "upload" and "root" in licence:
                moved = remap_root(licence["root"])
                per["licence"] = (dict(licence, root=moved) if moved is not None
                                  else fresh["fonts"][fid].get("licence"))
            rng = per.get("range")
            if isinstance(rng, str) and rng not in settings.NAMED_RANGE_NAMES:
                moved = remap_root(per.get(settings.RANGE_ROOT_KEY, 0))
                if moved is None:
                    per.pop("range", None)
                    per.pop(settings.RANGE_ROOT_KEY, None)
                else:
                    per[settings.RANGE_ROOT_KEY] = moved
        fresh["fonts"][fid] = per
    return fresh


def _instance_fits(font, instance):
    """True when @p instance is None or a dict whose every tag is still an axis of the re-detected @p font and whose
    value is a number (not a bool) inside that axis's range."""
    if instance is None:
        return True
    axes = {axis.get("tag"): axis for axis in (font.get("variable") or {}).get("axes") or []}
    if not axes or not isinstance(instance, dict):
        return False
    for tag, value in instance.items():
        axis = axes.get(tag)
        if axis is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if not axis["min"] <= value <= axis["max"]:          # False for NaN too
            return False
    return True


# ---- the server ------------------------------------------------------------------------------------------------

class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def server_close(self):
        stopping = getattr(self, "stopping", None)
        if stopping is not None:
            stopping.set()                                # the idle sweeper ends with the server
        super().server_close()

    @property
    def port(self):
        """The bound port (`server_address[1]`): a test binds `127.0.0.1:0` and reads the real one here."""
        return self.server_address[1]


class _Server6(_Server):
    """The IPv6 form: a host with a colon (`::1`) needs `AF_INET6` to bind at all (Y4)."""

    address_family = socket.AF_INET6


def make_server(host, port, repo_dir, data_root, token=None):
    """A started `ThreadingHTTPServer` for @p repo_dir over the job store under @p data_root.

    The store, the worker (recovered: a `running` job is `failed`/`interrupted`, a `queued` one re-enqueued, then
    started) and the checkout paths hang off the server: `store`, `worker`, `repo_dir`, `svf_dir`, `tools_dir`,
    `static_dir`, `index`. The handler threads (and the worker) are daemons, so the process exits when serving stops.
    A host with a colon is bound through `_Server6` (`AF_INET6`), everything else through `_Server` (Y4).
    With a @p token (bytes, or the 32-hex string) the server is in local mode: it binds loopback only (`ValueError`
    first, before the store, the worker or the socket exist), and every `/api/` request must carry it.
    """
    host = _unbracket(host)
    if isinstance(token, str):
        token = _parse_token(token)
    if token is not None and not _is_loopback(host):
        raise LocalModeError("local mode binds 127.0.0.1 or ::1 only")
    repo_dir = os.path.abspath(repo_dir)
    if token is not None:
        os.umask(0o077)                                  # local mode: nothing it makes is readable by others
    store = jobs.Store(data_root)
    store.on_delete = _drop_preview_locks                 # W13: `retain` drops a removed job's preview locks too
    store.on_sweep = _sweep_locks
    static_dir = os.path.join(MAKER_DIR, "static")
    capabilities = caps.compute(static_dir, os.environ, local=token is not None)
    worker = jobs.Worker(store, repo_dir, os.path.join(repo_dir, "svf"), os.path.join(repo_dir, "tools"),
                         capabilities)
    worker.recover()
    worker.start()
    server_class = _Server6 if ":" in str(host) else _Server
    server = server_class((host, port), Handler)
    server.store = store
    server.worker = worker
    server.repo_dir = repo_dir
    server.svf_dir = os.path.join(repo_dir, "svf")
    server.tools_dir = os.path.join(repo_dir, "tools")
    server.static_dir = static_dir
    server.caps = capabilities
    server.token = token
    server.data_root = store.data_root
    server.create_lock = threading.Lock()                # one local job per output folder, checked under it
    server.index = naming.RepoIndex(server.svf_dir)
    server.started = time.monotonic()
    server.touched = {}                                   # local job id -> when a preview/probe/source GET last asked
    server.sweep_idle = lambda now=None: _sweep_idle(server, now)
    local_ids = [item["id"] for item in store.list() if item.get("source") == "local"]   # jobs of an earlier run only

    def startup_sweep():
        store.retry_pending_sweeps()
        for job_id in local_ids:
            try:
                store.sweep_files(store.load(job_id))
            except KeyError:
                continue
    server.startup_sweep = threading.Thread(target=startup_sweep, daemon=True, name="svf-maker-startup-sweep")
    server.startup_sweep.start()

    def idle_sweeper():
        while not server.stopping.wait(60):
            try:
                _sweep_idle(server)
            except Exception:
                traceback.print_exc()
    server.stopping = threading.Event()
    threading.Thread(target=idle_sweeper, daemon=True, name="svf-maker-idle-sweep").start()
    server.reserved = {}                                  # job id -> the upload bytes/files in flight (W4)
    server.inflight = {}                                  # job id -> the `PUT files` requests not answered yet (Y3)
    return server


# ---- the handler -----------------------------------------------------------------------------------------------

_JOB = r"(?P<job>[0-9a-f]{12})"
_ROUTES = (
    ("GET", re.compile(r"^/$"), "_static_index"),
    ("GET", re.compile(r"^/static/(?P<file>.+)$"), "_static_file"),
    ("GET", re.compile(r"^/api/jobs$"), "_job_list"),
    ("GET", re.compile(r"^/api/jobs/%s/zip$" % _JOB), "_job_zip"),
    ("GET", re.compile(r"^/api/jobs/%s/face/(?P<step>s\d+)\.svf$" % _JOB), "_job_face"),
    ("GET", re.compile(r"^/api/jobs/%s/source/(?P<font>f\d+)\.svf$" % _JOB), "_job_source_face"),
    ("GET", re.compile(r"^/api/jobs/%s/report/(?P<step>s\d+)\.json$" % _JOB), "_job_report"),
    ("GET", re.compile(r"^/api/jobs/%s/probe/(?P<font>f\d+)/(?P<size>[1-9]\d*)/(?P<bpp>[1-9]\d*)\.(?P<ext>svf|json)$" % _JOB),
     "_job_probe"),
    ("GET", re.compile(r"^/api/jobs/%s/identity/(?P<step>s\d+)\.json$" % _JOB), "_job_identity"),
    ("GET", re.compile(r"^/api/repo/face/(?P<group>[A-Za-z0-9_-]+)/(?P<file>[A-Z0-9_]+\.SVF)$"), "_repo_face"),
    ("GET", re.compile(r"^/api/caps$"), "_caps"),
    ("GET", re.compile(r"^/api/jobs/%s/preview/(?P<font>[^/]+)/(?P<kind>[^/]+)\.png$" % _JOB), "_job_preview"),
    ("GET", re.compile(r"^/api/jobs/%s$" % _JOB), "_job_get"),
    ("GET", re.compile(r"^/api/repo$"), "_repo"),
    ("POST", re.compile(r"^/api/jobs$"), "_job_create"),
    ("POST", re.compile(r"^/api/jobs/%s/detect$" % _JOB), "_job_detect"),
    ("POST", re.compile(r"^/api/jobs/%s/run$" % _JOB), "_job_run"),
    ("POST", re.compile(r"^/api/jobs/%s/cancel$" % _JOB), "_job_cancel"),
    ("PUT", re.compile(r"^/api/jobs/%s/files$" % _JOB), "_job_files"),
    ("PUT", re.compile(r"^/api/jobs/%s/settings$" % _JOB), "_job_settings"),
    ("PUT", re.compile(r"^/api/jobs/%s/sources$" % _JOB), "_job_sources"),
    ("DELETE", re.compile(r"^/api/jobs/%s$" % _JOB), "_job_delete"),
)

# The GET handlers that hand out font bytes: they run the Host check too (a DNS-rebinding page must not read them).
_HOST_CHECKED = {"_job_face", "_job_source_face", "_repo_face", "_job_report", "_job_probe", "_job_identity",
                 "_job_zip", "_job_get", "_job_preview"}


class Handler(http.server.BaseHTTPRequestHandler):
    """The routes of Task 13; every answer is JSON except a static file and a PNG/zip body."""

    server_version = "svf-maker"
    sys_version = ""
    timeout = IDLE_TIMEOUT                    # a stalled read is closed and its reservation released (W8)

    def log_message(self, fmt, *args):
        """No per-request noise on stderr; the 500 path prints its own traceback."""

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_PUT(self):
        self._handle("PUT")

    def do_DELETE(self):
        self._handle("DELETE")

    # ---- responses -------------------------------------------------------------------------------------------

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(body, "application/json", status)

    def _send(self, body, content_type, status=200, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")     # W10: every response, errors included
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    @staticmethod
    def _no_store(job):
        """Bytes of a local job are never cached by the browser (design 10.4)."""
        return job.get("source") == "local"

    def _serve_bytes(self, path, content_type, no_store=False, extra=None):
        """@p path with `Cache-Control: no-cache` (`no-store` with @p no_store) and an `ETag` of size and mtime;
        `If-None-Match` equal is a 304."""
        try:
            st = os.stat(path)
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            raise _HttpError(404, "not found")
        etag = '"%d-%d"' % (st.st_size, st.st_mtime_ns)
        headers = {"Cache-Control": "no-store" if no_store else "no-cache", "ETag": etag}
        headers.update(extra or {})
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return
        self._send(body, content_type, 200, headers)

    def _serve_file(self, path, content_type, extra=None):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            raise _HttpError(404, "not found")
        self._send(body, content_type, 200, extra)

    # ---- dispatch --------------------------------------------------------------------------------------------

    def _handle(self, method):
        try:
            split = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(split.query)
            if self.server.token is not None:
                self._check_same_origin()                 # every request: `/` and `/static/*` too
                self._check_token(split.path)
            handler, params = self._route(method, split.path)
            if self.server.token is None and (method in _STATE_CHANGERS
                                              or (handler is not None and handler.__name__ in _HOST_CHECKED)):
                self._check_same_origin()
            if handler is None:
                raise _HttpError(404, "not found")
            handler(query, **params)
        except _HttpError as exc:
            self._reply_error(exc)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except TimeoutError:                            # W8: an idle read is over; the reservation is released below
            self._reply_error(_HttpError(400, "stalled body"))
        except Exception as exc:                        # anything uncaught is a 500 with the traceback on stderr
            traceback.print_exc()
            self._reply_error(_HttpError(500, "%s: %s" % (type(exc).__name__, exc)))

    def _check_token(self, path):
        """With a token, every `/api/` request carries exactly one `X-Maker-Token`, compared as bytes; else 403."""
        if not path.startswith("/api/"):
            return
        try:
            values = self.headers.get_all("X-Maker-Token") or []
            ok = len(values) == 1 and hmac.compare_digest(values[0].encode("latin-1"), self.server.token)
        except Exception:
            ok = False
        if not ok:
            raise _HttpError(403, "missing or wrong token")

    def _check_same_origin(self):
        """Refuse a state-changing request whose `Host` is not this server's, or whose `Origin` differs (W9).

        The page is served from the bound address's origin only, so a page the owner visits (or a DNS-rebinding
        name) cannot drive `PUT`/`POST`/`DELETE` from another origin. `Host` must name the bound host, `127.0.0.1`,
        `localhost` or `::1`; an `Origin`, when the client sends one, must name the same host and port as `Host`.
        """
        host_header = self.headers.get("Host") or ""
        if len(host_header) > HOST_HEADER_MAX:
            raise _HttpError(403, "bad Host")
        allowed = {"127.0.0.1", "localhost", "::1"}
        bound = str(self.server.server_address[0]).strip("[]").lower()
        if bound:
            allowed.add(bound)
        hostname, port = _split_host(host_header)
        if not hostname or hostname not in allowed:
            raise _HttpError(403, "cross-origin request")
        origin = self.headers.get("Origin")
        if origin is not None:
            split = urllib.parse.urlsplit(origin)
            origin_host, origin_port = _split_host(split.netloc)
            if (split.scheme not in ("http", "https") or not origin_host or origin_host not in allowed
                    or origin_port != port):
                raise _HttpError(403, "cross-origin request")

    def _reply_error(self, exc):
        try:
            self.send_json(dict(exc.extra, error=exc.message), exc.status)
        except Exception:
            pass

    def _route(self, method, path):
        for verb, pattern, name in _ROUTES:
            if verb != method:
                continue
            match = pattern.match(path)
            if match:
                return getattr(self, name), match.groupdict()
        return None, {}

    def _load(self, job_id):
        try:
            job = self.server.store.load(job_id)
        except KeyError:
            raise _HttpError(404, "no job %s" % job_id)
        job["fonts"] = self._stamped(job.get("fonts") or [])
        return job

    def _stamped(self, fonts):
        """Copies of @p fonts with `mask_ok` (the live `caps["mask_libs"]`) on every outline entry. A stored job never
        holds the flag: a restart with other libraries must not serve a stale one, so every read of the fonts for a
        decision (a GET, a settings PUT, a run) goes through here."""
        mask_ok = bool(self.server.caps.get("mask_libs"))
        out = []
        for font in fonts:
            if isinstance(font, dict) and font.get("source_kind") in ("outline", "outline-composite"):
                font = dict(font, mask_ok=mask_ok)
            out.append(font)
        return out

    def _update(self, job_id, fn):
        """`store.update` with a job deleted under us reported as a 409 conflict, never a 500 (W1)."""
        try:
            return self.server.store.update(job_id, fn)
        except KeyError:
            raise _HttpError(409, "job %s is gone" % job_id)

    def _content_length(self):
        raw = self.headers.get("Content-Length")
        if raw is None:
            raise _HttpError(411, "missing Content-Length")
        try:
            length = int(raw)
        except ValueError:
            raise _HttpError(400, "bad Content-Length")
        if length < 0:
            raise _HttpError(400, "bad Content-Length")
        return length

    def _json_body(self):
        length = self._content_length()
        if length > BODY_CAP:
            raise _HttpError(413, "body over %d bytes" % BODY_CAP)
        data = self.rfile.read(length) if length else b""
        if len(data) != length:
            raise _HttpError(400, "short body")
        if _json_depth(data) > JSON_DEPTH:              # a deep body would overflow the decoder's stack (W5)
            raise _HttpError(400, "invalid JSON")
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise _HttpError(400, "invalid JSON")

    # ---- static ----------------------------------------------------------------------------------------------

    def _static_index(self, query):
        self._static("index.html")

    def _static_file(self, query, file):
        self._static(urllib.parse.unquote(file))

    def _static(self, rel):
        if archive.check_rel_path(rel):
            raise _HttpError(404, "not found")
        content_type = STATIC_TYPES.get(os.path.splitext(rel)[1].lower())
        if content_type is None:
            raise _HttpError(404, "not found")
        path = os.path.join(self.server.static_dir, rel)
        if not _inside(self.server.static_dir, path) or not os.path.isfile(path):
            raise _HttpError(404, "not found")
        self._serve_bytes(path, content_type, extra={"Content-Security-Policy": CSP})

    # ---- jobs ------------------------------------------------------------------------------------------------

    ACTIVE_STATES = ("uploading", "detected", "queued", "running")

    def _job_create(self, query):
        """An upload job (no body, or `{"source": "upload"}`), or a local job: `{"source": "local", "output_dir"}`."""
        body = self._json_body() if self._content_length() else {}
        if not isinstance(body, dict) or body.get("source", "upload") not in ("upload", "local"):
            raise _HttpError(400, "source is upload or local")
        if body.get("source", "upload") == "upload":
            job = self.server.store.create()
            self.send_json({"id": job["id"]})
            return
        if self.server.token is None:
            raise _HttpError(403, "local mode is off")
        try:
            real, _kind = sourcesmod.check_path(body.get("output_dir"), want="output", data_root=self.server.data_root,
                                                allowed=sourcesmod.allowed_roots(os.environ))
        except sourcesmod.PathRefused as exc:
            raise _HttpError(400, "output folder: %s" % exc.reason)
        store = self.server.store
        output_id = list(sourcesmod.stat_id(real))
        with self.server.create_lock:
            for item in store.list():
                if (item.get("source") == "local" and item.get("output_id") == output_id
                        and item["state"] in self.ACTIVE_STATES):
                    raise _HttpError(409, "output folder is in use by job %s" % item["id"])
            job = store.create(source="local", output_dir=real, output_id=output_id)
        try:
            store.ensure_files_dir(job)
        except (jobs.OutputGone, OSError) as exc:
            store.delete(job["id"])
            raise _HttpError(400, "output folder: %s" % (_os_reason(exc) if isinstance(exc, OSError) else exc))
        self.send_json({"id": job["id"]})

    def _files_dir_ready(self, current):
        """The files directory of @p current, made when it is a local job's and the output folder is still the one
        picked; 404 `output folder is gone or changed` when it is not. For an upload job it is the job directory."""
        try:
            files = self.server.store.ensure_files_dir(current)
            if current.get("source") == "local":
                self.server.touched[current["id"]] = time.monotonic()
            return files
        except jobs.OutputGone as exc:
            raise _HttpError(404, str(exc))
        except OSError as exc:
            raise _HttpError(404, "output folder: %s" % _os_reason(exc))

    def _tool_env(self, job):
        """The environment every tool a request thread starts for @p job gets: a local job's `TMPDIR` is inside its
        files directory and Python writes no bytecode beside the tools. None (the default environment) for an upload."""
        if job.get("source") != "local":
            return None
        return dict(preview.ENV, TMPDIR=os.path.join(self.server.store.files_dir(job), "work", "tmp"),
                    PYTHONDONTWRITEBYTECODE="1")

    MAX_SOURCE_PATHS = 64

    def _job_sources(self, query, job):
        """`PUT sources`: the paths a local job reads its inputs from. Each is checked (`sources.check_path`), must not
        overlap the output folder nor another input, and the accepted ones replace the job's roots."""
        current = self._load(job)
        if current.get("source") != "local":
            raise _HttpError(409, "job %s is an upload job" % job)
        if current.get("state") not in ("uploading", "detected"):
            raise _HttpError(409, "job %s is %s" % (job, current.get("state")))
        body = self._json_body()
        paths = body.get("paths") if isinstance(body, dict) else None
        if (not isinstance(paths, list) or len(paths) > self.MAX_SOURCE_PATHS
                or any(not isinstance(p, str) for p in paths)):
            raise _HttpError(400, "paths is a list of at most %d paths" % self.MAX_SOURCE_PATHS)
        allowed = sourcesmod.allowed_roots(os.environ)
        roots, refused = [], []
        for path in paths:
            try:
                real, kind = sourcesmod.check_path(path, want="source", data_root=self.server.data_root,
                                                   allowed=allowed)
                if sourcesmod.overlaps(real, current["output_dir"]):
                    raise sourcesmod.PathRefused("the output folder must not overlap an input")
                if any(sourcesmod.overlaps(real, item["path"]) for item in roots):
                    raise sourcesmod.PathRefused("overlaps another input")
            except sourcesmod.PathRefused as exc:
                refused.append({"path": path.replace("\0", "?"), "reason": exc.reason})
                continue
            except OSError as exc:
                refused.append({"path": path, "reason": _os_reason(exc)})
                continue
            roots.append({"path": real, "kind": kind, "name": os.path.basename(real)})
        walker = Sources("local", [item["path"] for item in roots], kinds=[item["kind"] for item in roots])
        files, cut = walker.walk()
        for i, rel, reason in cut:
            refused.append({"path": os.path.join(roots[i]["path"], rel) if rel else roots[i]["path"], "reason": reason})
        total = 0
        for _i, _rel, path in files:
            try:
                total += os.lstat(path).st_size
            except OSError:
                pass

        def transition(j):
            if j.get("state") not in ("uploading", "detected"):
                raise _HttpError(409, "job %s is %s" % (job, j.get("state")))
            j["roots"] = roots
            j["state"] = "uploading"                          # the fonts of the earlier roots are stale: detect again
            j["upload"] = {"files": len(files), "bytes": total,
                           "refused": ["%s: %s" % (item["path"], item["reason"]) for item in refused]}
        updated = self._update(job, transition)
        self._clear_previews(job, [font.get("id") for font in updated.get("fonts") or []])
        self.send_json({"roots": roots, "files": len(files), "bytes": total, "refused": refused})

    def _job_list(self, query):
        self.send_json({"jobs": self.server.store.list()})

    def _job_get(self, query, job):
        current = self._load(job)
        current["queue_position"] = self.server.worker.position(job)
        current["effective_names"] = settings.effective_names(current.get("fonts") or [],
                                                              current.get("settings") or {})
        if current.get("source") == "local":                 # a traceback may quote the input: it lives in log.md
            current["fonts"] = [{k: v for k, v in font.items() if k != "error"} for font in current.get("fonts") or []]
        self.send_json(current)

    def _job_delete(self, query, job):
        """Delete the job's directory; the store's own locked check refuses a `queued`/`running` job (W1)."""
        try:
            self.server.store.delete(job)
        except KeyError:
            raise _HttpError(404, "no job %s" % job)
        except (ValueError, OSError):
            raise _HttpError(409, "job %s cannot be deleted" % job)
        self.send_json({"deleted": job})

    def _job_detect(self, query, job):
        """Scan the job's sources and reset it to `detected`; a `failed` or `done` job may be re-detected (S1).

        A local job's scan runs over its roots; each entry records the file's `[st_dev, st_ino, st_size]` (`POST run`
        refuses an input that changed since), its traceback (if any) goes to `log.md` and only its exception type stays
        in `job.json`. The job's `owned` record is not touched.
        """
        current = self._load(job)
        local = current.get("source") == "local"
        self._refuse_upload_in_flight(job)
        if local:
            self._files_dir_ready(current)                   # the scan's temp copies go under the files directory
        scanned_roots = list(current.get("roots") or [])
        fonts = self._scan_fonts(job)
        if local:
            self._stamp_local(job, current, fonts)
        cleared = []

        def transition(j):
            if j.get("state") not in ("uploading", "detected", "failed", "done"):
                raise _HttpError(409, "job %s is %s" % (job, j.get("state")))
            self._refuse_upload_in_flight(job)              # an upload that started during the scan (Y3)
            cleared.extend(font.get("id") for font in (j.get("fonts") or []))
            if local:
                if (j.get("roots") or []) != scanned_roots:
                    raise _HttpError(409, "the sources changed while detecting: detect again")
                kept = _kept_settings(j.get("settings") or {}, fonts, j.get("fonts") or [], roots=scanned_roots,
                                      old_roots=j.get("scan_roots") or scanned_roots, local=True)
                j["scan_roots"] = scanned_roots
            else:
                kept = _kept_settings(j.get("settings") or {}, fonts, j.get("fonts") or [])
            j.update(state="detected", fonts=fonts, settings=kept, steps=[], result=None, error=None)
        current = self._update(job, transition)
        # outside the job lock: waiting for a bake's preview lock must not stall this job's PUTs (Y6)
        self._clear_previews(job, cleared + [font.get("id") for font in fonts])
        self.send_json(current)

    def _stamp_local(self, job, current, fonts):
        """Give each scanned entry of a local job its `file_id`, and move its traceback out of the entry into `log.md`."""
        sources = self.server.store.sources(current)
        notes = []
        for font in fonts:
            try:
                st = os.lstat(sources.abs_of(font.get("root", 0), font.get("path")))
                font["file_id"] = [st.st_dev, st.st_ino, st.st_size]
            except (OSError, ValueError):
                font["file_id"] = None
            detail = font.pop("error", None)
            if detail:
                notes.append("detect: %s (root %s): %s\n%s\n" % (font.get("path"), font.get("root"),
                                                                  font.get("error_type", ""), detail))
        if notes:
            zipout.append_log(self.server.store.meta_dir(job), "\n" + "\n".join(notes))

    def _refuse_upload_in_flight(self, job):
        """409 while a `PUT files` for @p job is between its reservation and its reply (Y3).

        A scan must not see a body's `.upload-*` temp file or a half-unpacked archive, so `detect` waits for the
        upload to land. `_begin_upload`/`_end_upload` mark the request under the job lock, which is the lock the
        `transition` reads the mark under.
        """
        if self.server.inflight.get(job):
            raise _HttpError(409, "an upload is in flight for job %s" % job)

    def _scan_fonts(self, job):
        """`detect.scan` of the job's sources, without the temp files of uploads still in flight (Y3)."""
        current = self._load(job)
        fonts = detect.scan(self.server.store.sources(current), local=current.get("source") == "local")
        return [font for font in fonts if not _is_upload_tmp(font.get("path"))]

    def _begin_upload(self, job):
        """Mark a `PUT files` for @p job in flight, under the job lock (Y3)."""
        with self.server.store.lock(job):
            self.server.inflight[job] = self.server.inflight.get(job, 0) + 1

    def _end_upload(self, job):
        """Clear the mark `_begin_upload` set; a request still in flight keeps it (Y3)."""
        with self.server.store.lock(job):
            left = self.server.inflight.get(job, 0) - 1
            if left > 0:
                self.server.inflight[job] = left
            else:
                self.server.inflight.pop(job, None)

    def _clear_previews(self, job_id, font_ids):
        """Drop every derived preview before re-detecting (W2): the old font ids can now name other fonts.

        The per-font preview locks are held while the tree goes, so a preview a request is drawing for one of those
        fonts is serialized with the removal; the request then reloads the job and draws from the new fonts.
        """
        locks = [_preview_lock(job_id, font_id) for font_id in dict.fromkeys(font_ids) if font_id]
        with contextlib.ExitStack() as stack:
            for lock in locks:
                stack.enter_context(lock)
            try:
                previews = os.path.join(self.server.store.files_dir(self._load(job_id)), "work", "preview")
            except _HttpError:                                # the job was deleted meanwhile: nothing to clear
                return
            shutil.rmtree(previews, ignore_errors=True)

    # ---- files and detection ---------------------------------------------------------------------------------

    def _job_files(self, query, job):
        if self._load(job).get("source") == "local":
            raise _HttpError(409, "job %s is a local job" % job)
        length = self._content_length()
        if length > BODY_CAP:
            raise _HttpError(413, "body over %d bytes" % BODY_CAP)
        rel = (query.get("path") or [None])[0]
        reason = archive.check_rel_path(rel if isinstance(rel, str) else "")
        if reason:
            raise _HttpError(400, reason)
        store = self.server.store
        upload_dir = store.path(job, "upload")
        dest = os.path.join(upload_dir, rel)
        if not _inside(upload_dir, dest):
            raise _HttpError(400, "path escapes the upload")
        if os.path.isdir(dest) and not os.path.islink(dest):
            raise _HttpError(400, "path is a directory")
        self._begin_upload(job)                           # `detect` refuses while this request is open (Y3)
        try:
            # the job exists (404) and its state is right (409) before any folder is made (Y5)
            adds_file = self._reserve_upload(job, dest, length)
            state = {"held": True}
            out = {}

            def release():
                if state["held"]:
                    state["held"] = False
                    self._release_upload(job, length, adds_file)

            def record(current):
                if current.get("state") not in ("uploading", "detected"):
                    raise _HttpError(409, "job %s is %s" % (job, current.get("state")))
                try:
                    os.replace(out["tmp"], dest)                  # the body lands only under this lock (W1)
                except OSError as exc:
                    raise _HttpError(400, _os_reason(exc))
                release()                                         # reserved bytes become the real ones
                current["state"] = "uploading"
                files, total = _count_dir(upload_dir)
                current["upload"] = dict(current.get("upload") or {}, files=files, bytes=total)
                if out.get("archive"):
                    out["unpacked"] = self._unpack(current, dest, upload_dir)
                unpacked = out.get("unpacked")
                if unpacked and unpacked.get("stopped"):
                    refused = list(current["upload"].get("refused") or [])
                    refused.append("%s: %s" % (rel, unpacked["stopped"]))
                    current["upload"]["refused"] = refused

            try:
                try:
                    os.makedirs(os.path.dirname(dest), exist_ok=True)     # a file where a folder goes is 400 (W5)
                except OSError as exc:
                    raise _HttpError(400, _os_reason(exc))
                out["tmp"] = self._receive(dest, length)
                out["archive"] = self._archive_kind(out["tmp"])
                try:
                    store.update(job, record)
                except KeyError:
                    raise _HttpError(409, "job %s is gone" % job)
            except BaseException:
                if out.get("tmp"):
                    self._remove_file(out["tmp"])
                with store.lock(job):
                    release()
                raise
        finally:
            self._end_upload(job)
        self.send_json({"path": rel, "bytes": length, "unpacked": out.get("unpacked")})

    def _reserve_upload(self, job, dest, length):
        """Check the caps and hold @p length under the job's lock; return 1 when the path is a new file (W4/W13).

        The state check, the overwrite arithmetic and the reservation happen together under the job's lock, so three
        parallel PUTs cannot pass `FILE_CAP` (each in-flight request's bytes and files are held in
        `server.reserved`). An overwrite adds no file and its byte check subtracts the size it replaces (W13).
        """
        store = self.server.store
        with store.lock(job):
            try:
                current = store.load(job)
            except KeyError:
                raise _HttpError(404, "no job %s" % job)     # Y5: an unknown id is a 404, not a "gone" 409
            if current.get("state") not in ("uploading", "detected"):
                raise _HttpError(409, "job %s is %s" % (job, current.get("state")))
            try:
                replaced = os.lstat(dest).st_size
                exists = True
            except OSError:
                replaced = 0
                exists = False
            adds_file = 0 if exists else 1
            upload = current.get("upload") or {}
            held = self.server.reserved.get(job) or {"bytes": 0, "files": 0}
            if (upload.get("bytes") or 0) + held["bytes"] - replaced + length > JOB_CAP:
                raise _HttpError(413, "job over %d bytes" % JOB_CAP)
            if (upload.get("files") or 0) + held["files"] + adds_file > FILE_CAP:
                raise _HttpError(413, "job over %d files" % FILE_CAP)
            held["bytes"] += length
            held["files"] += adds_file
            self.server.reserved[job] = held
        return adds_file

    def _release_upload(self, job, length, adds_file):
        """Give back a reservation taken by `_reserve_upload`; the caller holds the job's lock."""
        held = self.server.reserved.get(job)
        if held is None:
            return
        held["bytes"] -= length
        held["files"] -= adds_file
        if held["bytes"] <= 0 and held["files"] <= 0:
            self.server.reserved.pop(job, None)

    def _unpack(self, current, dest, upload_dir):
        """Unpack the archive at @p dest into `<dest>.d/`, update @p current's counters and return the result (W3/W5).

        The unpack allowance is both the remaining file count and the remaining bytes (`JOB_CAP`), so one archive
        cannot take the job past the cap; the archive file itself is not counted, since it is removed once its
        members are out. The other uploads' reservations (`server.reserved`, held for bodies still arriving) are
        subtracted too (Y1): an archive cannot spend bytes and files another in-flight PUT already holds. The
        archive's name plus `.d` may be longer than the filesystem allows: that is a 400 with the archive removed,
        and so is any other path the filesystem refuses.
        """
        unpack_dir = dest + ".d"
        try:
            if os.path.islink(unpack_dir):                    # a fresh `<name>.d/`: never unpack through a link
                os.remove(unpack_dir)
            elif os.path.isdir(unpack_dir):
                shutil.rmtree(unpack_dir, ignore_errors=True)
            elif os.path.lexists(unpack_dir):
                os.remove(unpack_dir)                         # a stale file where the directory goes
            os.makedirs(unpack_dir, exist_ok=True)
        except OSError as exc:
            self._remove_file(dest)
            self._record_counts(current, upload_dir)
            raise _HttpError(400, _os_reason(exc))
        files = current["upload"]["files"]
        total = current["upload"]["bytes"]
        try:
            packed = os.path.getsize(dest)
        except OSError:
            packed = 0
        held = self.server.reserved.get(current.get("id")) or {}
        held_files = max(0, int(held.get("files") or 0))
        held_bytes = max(0, int(held.get("bytes") or 0))
        limits = dict(archive.LIMITS,
                      files=max(0, FILE_CAP - (files - 1) - held_files),
                      total=max(0, min(archive.LIMITS["total"],
                                      JOB_CAP - max(0, total - packed) - held_bytes)))
        unpacked = archive.unpack(dest, unpack_dir, limits)
        self._remove_file(dest)
        self._record_counts(current, upload_dir)
        return unpacked

    def _record_counts(self, current, upload_dir):
        """Re-read the upload's counters from disk into @p current (the caller holds the job's lock)."""
        files, total = _count_dir(upload_dir)
        current["upload"] = dict(current.get("upload") or {}, files=files, bytes=total)

    @staticmethod
    def _archive_kind(path):
        """`archive.kind_of`'s name for @p path, or `None` (an unreadable file is not an archive)."""
        try:
            with open(path, "rb") as f:
                return archive.kind_of(f.read(512))
        except OSError:
            return None

    @staticmethod
    def _remove_file(path):
        try:
            os.remove(path)
        except OSError:
            pass

    def _receive(self, dest, length):
        """Write exactly @p length body bytes for @p dest to a temp file beside it; return the temp path.

        The body is not in place yet: the caller replaces the temp file with @p dest under the job's lock, once the
        state is re-checked (W1). A short read leaves no temp file behind.
        """
        directory = os.path.dirname(dest)
        fd, tmp = tempfile.mkstemp(prefix=UPLOAD_TMP, dir=directory)
        received = 0
        try:
            with os.fdopen(fd, "wb") as out:
                while received < length:
                    chunk = self.rfile.read(min(CHUNK, length - received))
                    if not chunk:
                        break
                    out.write(chunk)
                    received += len(chunk)
            if received != length:
                raise _HttpError(400, "short body")
        except BaseException:
            self._remove_file(tmp)
            raise
        return tmp

    # ---- settings and run ------------------------------------------------------------------------------------

    def _job_settings(self, query, job):
        current = self._load(job)
        if current.get("state") != "detected":
            raise _HttpError(409, "job %s is %s" % (job, current.get("state")))
        body = self._json_body()
        store = self.server.store

        def transition(j):
            if j.get("state") != "detected":                 # re-checked under the job's lock (W1)
                raise _HttpError(409, "job %s is %s" % (job, j.get("state")))
            fonts = self._stamped(j.get("fonts") or [])
            errors = settings.validate(fonts, body, store.sources(j))
            if errors:
                raise _HttpError(400, errors[0], {"errors": errors})
            for font_id in _changed_preview_fonts(fonts, j.get("settings") or {}, body):
                with _preview_lock(job, font_id):            # W2: a new input invalidates the drawn preview
                    _remove_preview(store, j, font_id)
            j["settings"] = body
        current = self._update(job, transition)
        self.send_json(current)

    def _job_run(self, query, job):
        store = self.server.store
        first = self._load(job)
        local = first.get("source") == "local"
        # a fresh index: the checkout's current names count (a local job's: what its output folder holds)
        index = naming.RepoIndex(os.path.join(first["output_dir"], "svf") if local else self.server.svf_dir)

        def transition(j):
            if j.get("state") != "detected":                 # re-checked under the job's lock (W1)
                raise _HttpError(409, "job %s is %s" % (job, j.get("state")))
            fonts = self._stamped(j.get("fonts") or [])
            files_dir, sources = store.files_dir(j), store.sources(j)
            if local:
                self._check_local_run(j, fonts, sources)
            errors = settings.run_ready(fonts, j.get("settings") or {}, index, sources,
                                        own_earlier=jobs.own_earlier(j) if local else ())
            if errors:
                raise _HttpError(400, errors[0], {"errors": errors})
            try:
                steps = settings.plan_steps(dict(j, fonts=fonts), files_dir, self.server.tools_dir, sources,
                                            pylib=os.environ.get("JAMOSET_PYLIB") or None)
            except ValueError as exc:
                raise _HttpError(400, str(exc))
            self._check_steps(files_dir, sources, fonts, steps)
            self._check_notes(fonts, steps, sources, files_dir)
            j.update(state="queued", error=None, steps=steps, result=None)
        self._update(job, transition)
        position = self.server.worker.enqueue(job)          # the position it really got (W13)
        current = self._load(job)
        current["queue_position"] = position
        self.send_json(current)

    def _check_local_run(self, j, fonts, sources):
        """The checks a local `POST run` adds, under the job lock: the output folder is still the one picked, every
        root still passes the path rules, no other job is active on the folder, every input a step reads is the file
        that was detected, and the folder has room for the output."""
        store = self.server.store
        try:
            store.ensure_files_dir(j)
        except jobs.OutputGone as exc:
            raise _HttpError(409, str(exc))
        except OSError as exc:
            raise _HttpError(409, "output folder: %s" % _os_reason(exc))
        allowed = sourcesmod.allowed_roots(os.environ)
        for item in j.get("roots") or []:
            try:
                sourcesmod.check_path(item["path"], want="source", data_root=self.server.data_root, allowed=allowed)
            except sourcesmod.PathRefused as exc:
                raise _HttpError(409, "%s: %s" % (item["path"], exc.reason))
        for item in store.list():
            if (item.get("source") == "local" and item["id"] != j["id"] and item.get("output_id") == j.get("output_id")
                    and item["state"] in self.ACTIVE_STATES):
                raise _HttpError(409, "output folder is in use by job %s" % item["id"])
        total = 0
        for entry in self._inputs_of_selected(j, fonts):
            total += self._check_unchanged(entry, sources)
        free = shutil.disk_usage(j["output_dir"])[2]
        if free < sourcesmod.LOCAL_FREE_MIN + total:
            raise _HttpError(409, "not enough free space in %s" % j["output_dir"])

    @staticmethod
    def _inputs_of_selected(j, fonts):
        """The scan entries a run of the selected fonts reads: each font, its Latin companion, its chosen licence file
        and its range list."""
        by_id = {font.get("id"): font for font in fonts}
        by_key = {(font.get("root", 0), font.get("path")): font for font in fonts}
        st = j.get("settings") or {}
        out = []
        for fid in (st.get("fonts") or {}):
            try:
                eff = settings.effective(fonts, st, fid)
            except KeyError:
                continue
            if not eff.get("selected"):
                continue
            wanted = [by_id.get(fid), by_id.get(eff.get("latin_companion"))]
            licence = eff.get("licence")
            if isinstance(licence, dict) and licence.get("kind") == "upload":
                wanted.append(by_key.get((licence.get("root", 0), licence.get("path"))))
            rng = eff.get("range")
            if isinstance(rng, str) and rng not in settings.NAMED_RANGE_NAMES:
                wanted.append(by_key.get((eff.get("range_root", 0), rng)))
            for entry in wanted:
                if entry is not None and entry not in out:
                    out.append(entry)
        return out

    @staticmethod
    def _check_unchanged(entry, sources):
        """409 when the file of @p entry is no longer the one detected (`file_id` = dev, ino, size, regular); returns
        its size."""
        message = "%s: the input changed since detection: detect again" % entry.get("path")
        try:
            st = os.lstat(sources.abs_of(entry.get("root", 0), entry.get("path")))
        except (OSError, ValueError):
            raise _HttpError(409, message)
        if list(entry.get("file_id") or ()) != [st.st_dev, st.st_ino, st.st_size] or not stat.S_ISREG(st.st_mode):
            raise _HttpError(409, message)
        return st.st_size

    def _check_steps(self, files_dir, sources, fonts, steps):
        """Refuse a step whose `output` is not inside the files directory or whose font's `path` is not under its
        root of the sources.

        The worker trusts `job.json` and joins `output`/`path` onto those directories: the server, which is the one
        that writes them there, refuses anything that would leave them (Tasks 12/13 review).
        """
        by_id = {font.get("id"): font for font in fonts}
        earlier = set()
        for step in steps:
            if any(need not in earlier for need in step.get("needs") or []):
                raise ValueError("step %s needs a step that is not earlier" % step.get("id"))
            earlier.add(step.get("id"))
            output = step.get("output")
            if not isinstance(output, str) or not _inside(files_dir, os.path.join(files_dir, output)):
                raise _HttpError(400, "step %s output is outside the job directory" % step.get("id"))
            font = by_id.get(step.get("font")) or {}
            path = font.get("path")
            if isinstance(path, str):
                try:
                    sources.abs_of(font.get("root", 0), path)
                except ValueError:
                    raise _HttpError(400, "font %s path is outside the upload" % step.get("font"))

    def _check_notes(self, fonts, steps, sources, files_dir):
        """Refuse a note the zip step would refuse, using the real command lines the steps will run.

        The names and the command lines come from `zipout`'s own helpers, applied to the materialized argvs
        (`jobs.materialized_argv`), so the check cannot drift from the note `zipout` later writes (W12). A long
        upload path can push a command line past `naming.MAX_FIELD_BYTES`: running the same check here turns that
        into a 400 at `POST /run`, never a failed job at the zip step (Tasks 12/13 review).
        """
        by_id = {font.get("id"): font for font in fonts}
        work_dir = os.path.join(files_dir, "work")
        for font_id in dict.fromkeys(step.get("font") for step in steps):
            font = by_id.get(font_id) or {}
            mine = [step for step in steps if step.get("font") == font_id]
            faces = [step for step in mine if step.get("kind") in ("precomposed", "jamo")]
            if not faces:                                    # only a face step is named in a note (a prepare is not)
                continue
            materialized = [dict(step, argv=jobs.materialized_argv([step], sources, work_dir)) for step in mine]
            local = sources.kind == "local"
            names = zipout.note_names([{"name": step.get("name"), "identical_to": step.get("identical_to")}
                                       for step in faces])
            try:
                naming.note_text(font.get("family") or "", font.get("style") or "", names,
                                 os.path.basename(font.get("path") or ""), font.get("version") or "",
                                 datetime.date.today().isoformat(),
                                 zipout.note_commands(materialized, font, sources, files_dir, self.server.tools_dir)
                                 if local else zipout.note_commands(materialized, font))
            except ValueError as exc:
                raise _HttpError(400, "note for %s: %s" % (font_id, exc))

    def _job_cancel(self, query, job):
        result = self.server.worker.cancel(job)
        if result == "not running":
            raise _HttpError(409, "not running")
        self.send_json({"result": result})

    # ---- previews --------------------------------------------------------------------------------------------

    def _job_preview(self, query, job, font, kind):
        current = self._load(job)
        files_dir = self._files_dir_ready(current)
        by_id = {entry.get("id"): entry for entry in (current.get("fonts") or [])}
        entry = by_id.get(urllib.parse.unquote(font))
        if entry is None:
            raise _HttpError(404, "no font %s" % font)
        kind = urllib.parse.unquote(kind)
        if kind == "source":
            path = os.path.join(files_dir, "work", "preview", "%s.png" % entry.get("id"))
            if not os.path.isfile(path):
                with _preview_lock(job, entry.get("id")):
                    if not os.path.isfile(path):
                        fresh = self._load(job)              # the settings may have changed while we waited (W2)
                        fonts = {item.get("id"): item for item in (fresh.get("fonts") or [])}
                        if entry.get("id") not in fonts:
                            raise _HttpError(404, "no font %s" % font)
                        self._make_preview(fresh, files_dir, fonts[entry.get("id")])
            if not os.path.isfile(path):
                raise _HttpError(404, "no preview")
            self._serve_file(path, "image/png",
                             extra={"Cache-Control": "no-store"} if self._no_store(current) else None)
            return
        raise _HttpError(404, "no preview")                  # only the source PNG is served (the result faces are bytes)

    # ---- bytes for the page's WASM renderer ------------------------------------------------------------------

    def _job_face(self, query, job, step):
        """The output of a `done` face step of this job (never the file a re-run has not rewritten yet)."""
        current = self._load(job)
        files_dir = self.server.store.files_dir(current)
        found = next((item for item in (current.get("steps") or []) if item.get("id") == step), None)
        if (found is None or found.get("state") != "done" or found.get("kind") not in ("precomposed", "jamo")
                or not found.get("output")):
            raise _HttpError(404, "no face")
        if current.get("source") == "local" and current.get("state") == "done":
            path = self._output_face(current, found)       # the result lives in the output folder, not the files directory
        else:
            path = os.path.join(files_dir, found["output"])
            if not _inside(files_dir, path) or not os.path.isfile(path):
                raise _HttpError(404, "no face")
        self._serve_bytes(path, "application/octet-stream", self._no_store(current))

    @staticmethod
    def _output_face(current, step):
        """The face a done local step wrote (or found identical) in the output folder, else 404."""
        out = current.get("output_dir") or ""
        rel = step.get("written") or ("svf/" + step["identical_to"] if step.get("identical_to") else None)
        message = "face not in the output folder"
        if not rel:
            raise _HttpError(404, message)
        path = os.path.join(out, rel)
        try:
            same = sourcesmod.stat_id(out) == tuple(current.get("output_id") or ())
        except OSError:
            same = False
        if not same or not _inside(out, path) or not os.path.isfile(path) or os.path.islink(path):
            raise _HttpError(404, message)
        return path

    def _job_report(self, query, job, step):
        """The `--report` JSON of a `done` mkfont step of this job."""
        current = self._load(job)
        files_dir = self.server.store.files_dir(current)
        found = next((item for item in (current.get("steps") or []) if item.get("id") == step), None)
        if found is None or found.get("state") != "done" or not found.get("report"):
            raise _HttpError(404, "no report")
        base = self.server.store.meta_dir(job) if str(found["report"]).startswith("steps/") else files_dir
        path = os.path.join(base, found["report"])
        if not _inside(base, path) or not os.path.isfile(path):
            raise _HttpError(404, "no report")
        self._serve_bytes(path, "application/json", self._no_store(current))

    def _job_probe(self, query, job, font, size, bpp, ext):
        """The clipping probe of a mkfont font at an effective size and bpp (spec 8): a tall-cell bake of the step's own
        glyph set with its box report, made once under the font's preview lock into
        `work/preview/<font>/probe/<size>-<bpp>.{svf,json}` (the keyed settings drop the directory with the font's
        other previews). The `.json` carries `step_ascent`, the step's merged `--ascent` (or null)."""
        size, bpp = int(size), int(bpp)
        current = self._load(job)
        files_dir = self._files_dir_ready(current)
        sources = self.server.store.sources(current)
        fonts = current.get("fonts") or []
        entry = next((item for item in fonts if item.get("id") == font), None)
        if entry is None:
            raise _HttpError(404, "no font %s" % font)
        eff = settings.effective(fonts, current.get("settings") or {}, font)
        route = routes.route_for(entry, "precomposed", bool(eff.get("experimental")))
        if route is None or route.label != "mkfont" or size not in (eff.get("sizes") or []) \
                or bpp not in (eff.get("bpp") or []) or bpp not in route.bpps:
            raise _HttpError(404, "no probe")
        probe_dir = os.path.join(files_dir, "work", "preview", font, "probe")
        out_svf = os.path.join(probe_dir, "%d-%d.svf" % (size, bpp))
        out_json = os.path.join(probe_dir, "%d-%d.json" % (size, bpp))
        with _preview_lock(job, font):
            os.makedirs(probe_dir, exist_ok=True)
            src = self._prepared_source(entry, eff, sources, os.path.join(files_dir, "work", "preview"),
                                        env=self._tool_env(current))
            rkind, rabs = settings.range_spec(eff, sources)
            range_file = os.path.join(probe_dir, "range.txt")     # only an uploaded list is passed as a file
            if rkind == "file":
                if not rabs or not sources.inside(rabs) or not os.path.isfile(rabs):
                    raise _HttpError(404, "no probe")
                range_arg = ("file", range_file)
            else:
                range_arg = (rkind, None)                          # a named range is mkfont's own --unicode name
            paths = {"tools": self.server.tools_dir, "src": src, "out": out_svf, "work": probe_dir, "eng": None,
                     "latin": None, "master": None, "range_file": range_file, "base": None}
            try:
                step_argv = settings.face_argv(entry, eff, route, "precomposed", size, bpp, None, range_arg, paths)[0]
            except ValueError as exc:
                raise _HttpError(404, str(exc))
            argv = settings.probe_argv(step_argv, src, out_svf, out_json, size)
            if not os.path.isfile(out_json):
                if rkind == "file":
                    shutil.copyfile(rabs, range_file)
                self._run_probe(argv, probe_dir, out_svf, out_json, env=self._tool_env(current))
            if not os.path.isfile(out_json):
                raise _HttpError(404, "the probe failed")
            with open(out_json, encoding="utf-8") as f:
                report = json.load(f)
        if ext == "svf":
            if not report.get("probe_face") or not os.path.isfile(out_svf):
                raise _HttpError(404, "no probe face")
            self._serve_bytes(out_svf, "application/octet-stream", self._no_store(current))
            return
        cell = size
        if "--cell" in step_argv:
            try:
                cell = int(step_argv[step_argv.index("--cell") + 1])
            except (ValueError, IndexError):
                cell = size
        report["step_cell"] = cell                       # the step's own cell height (a preset may carry --cell)
        ascent = None
        if "--ascent" in step_argv:
            try:
                ascent = int(step_argv[step_argv.index("--ascent") + 1])
            except (ValueError, IndexError):
                ascent = None
        report["step_ascent"] = ascent
        self._send(json.dumps(report, ensure_ascii=False).encode("utf-8"), "application/json", 200,
                   {"Cache-Control": "no-store" if self._no_store(current) else "no-cache"})

    @staticmethod
    def _run_probe(argv, cwd, out_svf, out_json, env=None):
        """Run the probe; whatever it leaves after a failure is removed (a later GET asks again)."""
        try:
            done = preview.run_bounded(argv, cwd, preview.TIMEOUT_S, env=env)
            failed = done.returncode != 0
        except (OSError, subprocess.SubprocessError):
            failed = True
        if failed:
            for path in (out_svf, out_json):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _job_identity(self, query, job, step):
        """`work/sNN/identity.json` of a `done` jamo step that has one."""
        current = self._load(job)
        files_dir = self.server.store.files_dir(current)
        found = next((item for item in (current.get("steps") or []) if item.get("id") == step), None)
        if found is None or found.get("state") != "done" or found.get("kind") != "jamo":
            raise _HttpError(404, "no identity")
        meta = self.server.store.meta_dir(job)
        path = os.path.join(meta, "steps", "%s.identity.json" % step)
        if not os.path.isfile(path):
            path = os.path.join(files_dir, "work", step, "identity.json")
        if not (_inside(meta, path) or _inside(files_dir, path)) or not os.path.isfile(path):
            raise _HttpError(404, "no identity")
        self._serve_bytes(path, "application/json", self._no_store(current))

    def _job_source_face(self, query, job, font):
        """The baked source face of a DOS raw or SVF entry (`work/preview/<font id>.svf`), baked on demand."""
        current = self._load(job)
        files_dir = self._files_dir_ready(current)
        entry = next((item for item in (current.get("fonts") or []) if item.get("id") == font), None)
        if entry is None or entry.get("source_kind") not in ("dos-raw", "svf-precomposed", "svf-jamo"):
            raise _HttpError(404, "no source face")
        path = os.path.join(files_dir, "work", "preview", "%s.svf" % font)
        if not os.path.isfile(path):
            with _preview_lock(job, font):
                if not os.path.isfile(path):
                    fresh = self._load(job)
                    fonts = {item.get("id"): item for item in (fresh.get("fonts") or [])}
                    if font not in fonts:
                        raise _HttpError(404, "no source face")
                    try:
                        self._make_preview(fresh, files_dir, fonts[font])
                    except _HttpError as exc:
                        if exc.status == 409:                  # an unconfirmed DOS layout: no source face yet
                            raise _HttpError(404, exc.message)
                        raise
        if not os.path.isfile(path) or not _inside(files_dir, path):
            raise _HttpError(404, "no source face")
        self._serve_bytes(path, "application/octet-stream", self._no_store(current))

    def _repo_face(self, query, group, file):
        """A face of `svf/` (the page's Latin companion, `dos/NEODG16.SVF`)."""
        path = os.path.join(self.server.svf_dir, group, file)
        if not _inside(self.server.svf_dir, path) or not os.path.isfile(path):
            raise _HttpError(404, "no face")
        self._serve_bytes(path, "application/octet-stream")

    def _caps(self, query):
        self.send_json({key: bool(value) for key, value in self.server.caps.items()})

    def _make_preview(self, job, files_dir, font):
        """`_make_source_preview`, and for a local job the converted copy of the input is removed after the bake."""
        try:
            self._make_source_preview(job, files_dir, font)
        finally:
            if job.get("source") == "local":
                target_dir = os.path.join(files_dir, "work", "preview", str(font.get("id")))
                if os.path.isdir(target_dir):
                    for name in os.listdir(target_dir):
                        if name.startswith("source"):
                            try:
                                os.remove(os.path.join(target_dir, name))
                            except OSError:
                                pass

    def _make_source_preview(self, job, files_dir, font):
        """Bake or draw @p font's source preview into `work/preview/<font id>.png` (its own file: no shared name)."""
        fonts = job.get("fonts") or []
        sources = self.server.store.sources(job)
        out_dir = os.path.join(files_dir, "work", "preview")
        os.makedirs(out_dir, exist_ok=True)
        out_png = os.path.join(out_dir, "%s.png" % font.get("id"))
        eff = settings.effective(fonts, job.get("settings") or {}, font.get("id"))
        env = self._tool_env(job)
        local = job.get("source") == "local"
        abs_src = self._prepared_source(font, eff, sources, out_dir, env=env, keep=not local)
        if abs_src != self._plain_source(font, self._source_abs(sources, font), out_dir):
            font = dict(font, face_index=0)            # a prepared file holds the one face the build reads
        source_kind = font.get("source_kind") or ""
        if source_kind == "dos-raw":
            layout = eff.get("dos_layout")
            if not layout:
                raise _HttpError(409, "confirm the DOS Johab layout")
            eng_abs = self._companion_abs(eff, fonts, sources, out_dir)
            out_svf = os.path.join(out_dir, "%s.svf" % font.get("id"))
            if preview.bake_source_face(font, abs_src, layout, eng_abs, out_svf, self.server.tools_dir,
                                        self._bake_flags(eff, source_kind), env=env):
                self._render_preview(eng_abs, out_svf, out_png)
            return
        if source_kind in ("svf-precomposed", "svf-jamo"):
            out_svf = os.path.join(out_dir, "%s.svf" % font.get("id"))
            if preview.bake_source_face(font, abs_src, None, None, out_svf, self.server.tools_dir,
                                        self._bake_flags(eff, source_kind), env=env):
                self._render_preview(None, out_svf, out_png)
            return
        preview.source_png(font, abs_src, self._first_size(font, eff), out_png)

    @staticmethod
    def _source_abs(sources, font):
        """The absolute path of @p font's own file under its root of @p sources; 'no preview' when it is outside."""
        try:
            return sources.abs_of(font.get("root", 0), font.get("path"))
        except ValueError:
            raise _HttpError(404, "no preview")

    def _prepared_source(self, font, eff, sources, out_dir, env=None, keep=True):
        """The file the build's tools read for @p font: its plain source when no conversion is planned, else the
        converted copy `out_dir/<font id>/source.<ext>` (`settings.source_ops`: TTC face, Mac cmap or container,
        variable instance, PCF), written once. The caller holds the font's preview lock; the keyed settings drop the
        copy with the font's other previews. With @p keep False (a local job's bake) an earlier copy is not reused, and the
        caller removes the copy when it is done. A conversion that fails is 'no preview' (404)."""
        plain = self._plain_source(font, self._source_abs(sources, font), out_dir)
        ops = settings.source_ops(font, eff)
        if not ops:
            return plain
        last = ops[-1].get("op")
        ext = "bdf" if last == "pcf-bdf" else "otf" if font.get("cff") else "ttf"
        target_dir = os.path.join(out_dir, str(font.get("id")))
        target = os.path.join(target_dir, "source." + ext)
        if not keep or not os.path.isfile(target):
            # the build's own commands, in a subprocess with a time limit (an instancer on a large CJK font is slow and big)
            os.makedirs(target_dir, exist_ok=True)
            argvs, produced = routes.source_commands(ops, plain, target_dir, self.server.tools_dir, ext)
            try:
                for argv in argvs:
                    done = preview.run_bounded(argv, target_dir, preview.TIMEOUT_S, env=env)
                    if done.returncode != 0:
                        raise OSError("source conversion failed")
                if produced != target or not os.path.isfile(target):
                    raise OSError("no converted source")
            except (OSError, subprocess.SubprocessError):
                for name in os.listdir(target_dir):
                    if name.startswith("source"):
                        try:
                            os.remove(os.path.join(target_dir, name))
                        except OSError:
                            pass
                raise _HttpError(404, "no preview")
        return target

    @staticmethod
    def _bake_flags(eff, source_kind):
        """The panel's flags a source bake honours: `--jset-version V` for every bake and, for a DOS raw font,
        `--ascent N` (jamo_ascent), `--embolden` and `--symbols` (the order `presets.panel_argv` emits)."""
        jamoset = (eff.get("options") or {}).get("jamoset") or {}
        flags = []
        if jamoset.get("jset_version") is not None:
            flags += ["--jset-version", str(jamoset["jset_version"])]
        if source_kind == "dos-raw":
            if jamoset.get("jamo_ascent") is not None:
                flags += ["--ascent", str(jamoset["jamo_ascent"])]
            if jamoset.get("embolden"):
                flags.append("--embolden")
            if jamoset.get("symbols"):
                flags.append("--symbols")
        return flags

    @staticmethod
    def _plain_source(font, abs_path, out_dir):
        """@p abs_path, or the decompressed copy of a `.gz` upload under `work/preview/<font id>/` (W7).

        The copy is per font, so two fonts uploading the same `x.ttf.gz` cannot draw from one decompressed file
        (M3). A `.gz` that cannot be decompressed is "no preview" rather than a 500, the way `source_png` treats it.
        """
        if not font.get("gzip"):
            return abs_path
        gz_dir = os.path.join(out_dir, str(font.get("id") or "f"))
        try:
            os.makedirs(gz_dir, exist_ok=True)
            return preview.materialize(abs_path, gz_dir)
        except Exception:
            raise _HttpError(404, "no preview")

    def _render_preview(self, latin_abs, face_abs, out_png):
        """The `svfline` line through @p face_abs to @p out_png; a render failure leaves no file (404 later)."""
        try:
            preview.svf_png(preview.chain_for(face_abs, latin_abs, self.server.svf_dir), out_png)
        except Exception:
            pass

    def _companion_abs(self, eff, fonts, sources, out_dir):
        """The DOS raw font's Latin companion as an absolute path, or `None` (a `.gz` one is decompressed too)."""
        by_id = {font.get("id"): font for font in fonts}
        companion = eff.get("latin_companion")
        font = by_id.get(companion) if isinstance(companion, str) else None
        if font is None:
            return None
        return self._plain_source(font, self._source_abs(sources, font), out_dir)

    @staticmethod
    def _first_size(font, eff):
        """The first size the font's effective sizes list offers (its own first size when it lists none)."""
        for size in eff.get("sizes") or []:
            if isinstance(size, int) and not isinstance(size, bool):
                return size
        for size in font.get("sizes") or []:
            if isinstance(size, int) and not isinstance(size, bool):
                return size
        return None

    # ---- the zip and the repository --------------------------------------------------------------------------

    def _job_zip(self, query, job):
        current = self._load(job)
        if current.get("source") == "local":
            raise _HttpError(404, "a local job writes a folder")
        if current.get("state") != "done":
            raise _HttpError(409, "job %s is %s" % (job, current.get("state")))
        rel = ((current.get("result") or {}).get("zip")) or ""
        path = os.path.join(self.server.store.path(job), rel)
        if not rel or not _inside(self.server.store.path(job), path) or not os.path.isfile(path):
            raise _HttpError(404, "no zip")
        self._serve_file(path, "application/zip",
                         {"Content-Disposition": 'attachment; filename="svf-maker-%s.zip"' % job})

    def _repo(self, query):
        index = naming.RepoIndex(self.server.svf_dir)
        self.server.index = index
        self.send_json({"folders": index.folders,
                        "names": {folder: sorted(names) for folder, names in index.names.items()},
                        "texts": index.texts, "head": zipout.repo_head(self.server.repo_dir)})


def main():
    repo_dir = os.environ.get("SVF_MAKER_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_root = os.environ.get("SVF_MAKER_DATA") or os.path.expanduser("~/.local/share/svf-maker")
    bind = os.environ.get("SVF_MAKER_BIND") or "127.0.0.1:8766"
    host, port = _bind(bind)                              # no host means 127.0.0.1, not every interface (W11)
    try:
        token = _parse_token(os.environ.get("SVF_MAKER_TOKEN"))
        server = make_server(host, port, repo_dir, data_root, token=token)
    except LocalModeError as exc:                         # a bad token or a non-loopback bind with it; never print the token
        print(str(exc), file=sys.stderr)
        sys.exit(2)
    print("svf-maker listening on %s:%d" % (server.server_address[0], server.server_address[1]), flush=True)
    atexit.register(server.worker.stop)                   # however the process ends, the tool children are stopped first

    stopping = []

    def terminate(signum, frame):
        if stopping:                                      # a second signal while the first is being handled: ignore
            return
        stopping.append(signum)
        raise KeyboardInterrupt                           
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)               # also when the parent started us with SIGINT ignored (a background job)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.worker.stop()
        server.server_close()


if __name__ == "__main__":
    main()
