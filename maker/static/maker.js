/* SVF maker page: the Task 13 API over `fetch`, the DOM built from the job JSON.
 *
 * One ES module, no framework, no localStorage. Every API error lands in `#notice` and the page keeps working; the
 * job is polled every POLL_MS while it is `queued` or `running`; `?job=<id>` restores a job on load. The DOM of the
 * font table is built from `job.effective_names` (the maker's suggestions over the owner's edits), while an edited
 * name is stored under `settings.fonts[id].names[key]` and PUT with the settings.
 *
 * `ROUTES`, `PRESETS`, `OPTION_VISIBLE`, `PREVIEW_KINDS`, `SOURCE_WORDS` mirror `maker/routes.py`, `maker/presets.py`,
 * `maker/server.py` and `maker/settings.py`: the page cannot import Python, so the words it prints in a `title`, the
 * routes it offers and the options it shows are kept in step by hand. Every mirrored table is written as strict JSON
 * so `test_server.py` can read it back and compare it with the Python one.
 *
 * Every server-provided string goes in through `textContent` and through `escapeControls`, which turns Cc/Cf
 * characters (including the bidi controls) into visible `\uXXXX` escapes: an uploaded name or path cannot reorder
 * the table or the notices.
 */

"use strict";

const POLL_MS = 2000;

// Mirrors presets.PRESETS (name -> what it reproduces). The select shows only the name (a long `reproduces` in an
// option makes the control wide enough to push the form off the page, Q2) and carries the whole text in its title.
// Strict JSON (the P12 test).
const PRESETS = [
  ["plain", "the tools' defaults"],
  ["dos-l-1bpp", "svf/dos/NEODG16.SVF (the L preset; one glyph fewer than the shipped file)"],
  ["dos-u-2bpp", "svf/dos/GBATB17.SVF (byte-identical at size 17) and NGOTB16.SVF (one glyph fewer)"],
  ["latin-18cell-2bpp", "svf/dos/PAPLG16.SVF (the command in svf/dos/PAPLG.TXT)"],
  ["jamo-844", "the 8x4x4 layout of svf/dos/NEODG16A.SVF (no face here is built from a DOS raw font)"],
  ["jamo-844-symbols", "the 8x4x4 layout with U+2026 and U+25A1 (no face here is built from a DOS raw font)"],
  ["jamo-844-hbios24", "the 24 px HBIOS 8x4x4 layout (no face of this repository is built with it)"],
  ["jamo-621", "the 6x2x1 layout of svf/dos/NEODG16G.SVF (no face here is built from a DOS raw font)"]
];

// Mirrors routes.routes(font): the routes a fully capable font of each source_kind offers, in page order. An SVF
// route's bpps are the SVF's own bpp, so the entry lists both here. Strict JSON (the P12 test reads it back).
const ROUTES = {
  "outline": [{"kind": "precomposed", "label": "mkfont", "native": true, "bpps": [1, 2]},
              {"kind": "jamo", "label": "experimental fit", "native": false, "bpps": [1, 2]}],
  "outline-composite": [{"kind": "precomposed", "label": "mkfont", "native": true, "bpps": [1, 2]},
                        {"kind": "jamo", "label": "composite", "native": true, "bpps": [1, 2]}],
  "bitmap": [{"kind": "precomposed", "label": "mkfont", "native": true, "bpps": [1]}],
  "bdf-iso10646": [{"kind": "precomposed", "label": "mkfont", "native": true, "bpps": [1]}],
  "bdf-ksc5601": [{"kind": "precomposed", "label": "bdfface", "native": true, "bpps": [1]},
                  {"kind": "jamo", "label": "bdfface + from-svf fit", "native": false, "bpps": [1]}],
  "bdf-johab": [{"kind": "jamo", "label": "hanterm", "native": true, "bpps": [1]}],
  "dos-raw": [{"kind": "jamo", "label": "dos raw", "native": true, "bpps": [1]}],
  "svf-precomposed": [{"kind": "precomposed", "label": "copy", "native": true, "bpps": [1, 2]},
                      {"kind": "jamo", "label": "from-svf fit", "native": false, "bpps": [1]}],
  "svf-jamo": [{"kind": "jamo", "label": "copy", "native": true, "bpps": [1, 2]}]
};

const KINDS = ["precomposed", "jamo"];
const LAYOUTS = ["844", "adaptive", "hanterm-johab"];
const DEST_FIXED = ["dos", "jamo-extra"];

// The advanced panel's inputs (Shared data shapes `options`); `group` is the tool the key belongs to, and a key in
// `FLAG_KEYS` is a boolean (`false` in DEFAULT_OPTIONS), the rest a number (`null`).
const ADVANCED = [
  {key: "cell", group: "mkfont", label: "cell"},
  {key: "ascent", group: "mkfont", label: "ascent"},
  {key: "space_advance", group: "mkfont", label: "space advance"},
  {key: "mono_hint", group: "mkfont", label: "mono hint"},
  {key: "clip_cell", group: "mkfont", label: "clip cell"},
  {key: "embolden", group: "jamoset", label: "embolden"},
  {key: "symbols", group: "jamoset", label: "symbols"},
  {key: "jset_version", group: "jamoset", label: "JSET version"},
];

const FLAG_KEYS = new Set(["mono_hint", "clip_cell", "embolden", "symbols"]);

// Mirrors presets.panel_argv: which option a route label and bpp actually uses (the spec's "Advanced panel
// options"), i.e. the option keys the panel shows for that route. Only labels the routes above offer appear. Strict
// JSON (the drift test compares it with the flags panel_argv emits for every route label and bpp).
const OPTION_VISIBLE = {
  "mkfont": {"1": ["cell", "ascent", "mono_hint", "clip_cell", "space_advance"],
             "2": ["cell", "ascent", "clip_cell", "space_advance"]},
  "dos raw": {"1": ["embolden", "symbols", "jset_version"]},
  "hanterm": {"1": ["embolden", "symbols", "jset_version"]},
  "composite": {"1": ["symbols", "jset_version"], "2": ["symbols", "jset_version"]},
  "experimental fit": {"1": ["jset_version"], "2": ["symbols", "jset_version"]},
  "copy": {"1": ["jset_version"], "2": ["jset_version"]},
  "from-svf fit": {"1": ["jset_version"]},
  "bdfface": {"1": []},
  "bdfface + from-svf fit": {"1": []}
};

// Mirrors server._make_source_preview: how the page gets a source preview, per source kind. "draw": the server draws
// the source with Pillow (`preview.source_png`); "bake": it bakes the source first (a DOS raw font also needs its
// layout confirmed); "none": no preview (a Latin-only BDF, a BDF FreeType gives no Unicode charmap, an HBF, a kind
// with no face). Strict JSON (the drift test classifies every kind in presets.ALL_SOURCES).
const PREVIEW_KINDS = {
  "outline": "draw", "outline-composite": "draw", "bitmap": "draw", "bdf-iso10646": "draw",
  "bdf-iso8859": "none", "bdf-ksc5601": "none", "bdf-johab": "none", "hbf": "none",
  "dos-raw": "bake", "svf-precomposed": "bake", "svf-jamo": "bake", "other": "none"
};

// settings._SOURCE_WORDS / _SOURCE_ARTICLES: the phrase the validator uses in its reasons. Strict JSON.
const SOURCE_WORDS = {
  "dos-raw": "DOS raw", "outline": "outline", "outline-composite": "outline", "bitmap": "bitmap",
  "bdf-iso10646": "bitmap", "bdf-iso8859": "bitmap", "bdf-ksc5601": "bitmap", "bdf-johab": "bitmap", "hbf": "bitmap",
  "svf-precomposed": "SVF", "svf-jamo": "SVF"
};
const SOURCE_ARTICLES = {
  "outline": "an", "SVF": "an"
};

// The Cc/Cf characters the Task 11 note names, plus the bidi controls that can reorder a cell.
const CONTROL_RE = /[\u0000-\u001f\u007f-\u009f\u200e\u200f\u202a-\u202e\u2066-\u2069]/g;

const $ = (id) => document.getElementById(id);
const stateEl = $("state");
const noticeEl = $("notice");
const refusedEl = $("refused");
const fontsEl = $("fonts");
const stepsEl = $("steps");
const jobsEl = $("jobs");
const positionEl = $("position");
const downloadEl = $("download");
const saveEl = $("save");
const runEl = $("run");
const detectEl = $("detect");
const cancelEl = $("cancel");
const settingsEl = $("settings");
const filesEl = $("files");
const folderEl = $("folder");
const uploadEl = $("upload");
const countEl = $("upload-count");
const destEl = $("dest");
const destNewEl = $("dest-new");
const kindsEl = $("kinds");
const layoutEl = $("layout");
const sizesEl = $("sizes");
const bppEl = $("bpp");
const rangeEl = $("range");
const presetEl = $("preset");

let job = null;              // the job JSON of GET /api/jobs/<id>, plus `effective_names`
let repo = null;             // GET /api/repo
let jobId = null;
let settings = {batch: {}, fonts: {}};   // the local Settings dict the page PUTs
let dirty = false;           // an edit the settings PUT has not seen
let pollTimer = null;
let perOptionBoxes = [];     // [{box, per}] for every override row's advanced panel, rebuilt with the table

// ---- small helpers --------------------------------------------------------------------------------------------

function el(tag, props, ...kids) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (value === null || value === undefined || value === false) continue;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const kid of kids) if (kid !== null && kid !== undefined) node.append(kid);
  return node;
}

// A font-derived string with its Cc/Cf characters shown as visible `\uXXXX` escapes (the Task 11 note, I3/I4).
function escapeControls(value) {
  return String(value === null || value === undefined ? "" : value)
    .replace(CONTROL_RE, (ch) => "\\u" + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, "0"));
}

// The same, for a notice: newlines and tabs stay (the API joins an error's lines), the bidi controls do not.
const NOTICE_RE = /[\u0000-\u0008\u000b-\u001f\u007f-\u009f\u200e\u200f\u202a-\u202e\u2066-\u2069]/g;

function escapeNotice(value) {
  return String(value === null || value === undefined ? "" : value)
    .replace(NOTICE_RE, (ch) => "\\u" + ch.codePointAt(0).toString(16).toUpperCase().padStart(4, "0"));
}

// The escaped text inside a `<bdi dir="auto">`, so a bidi control cannot reorder the surrounding cell either.
function bdi(value) { return el("bdi", {dir: "auto", text: escapeControls(value)}); }

function option(value, label, reasons) {
  const node = el("option", {value, text: escapeControls(label)});
  if (reasons && reasons.length) {                    // an option the source cannot take: disabled, with the reason
    node.disabled = true;
    node.title = reasons.join("; ");
  }
  return node;
}

function fillSelect(select, options, value) {
  select.innerHTML = "";
  for (const [v, label, reasons] of options) select.append(option(v, label, reasons));
  const text = value === null || value === undefined ? "" : String(value);
  if (!options.some(([v]) => v === text) && text) select.append(option(text, text));
  select.value = text;
}

function notice(message) {
  noticeEl.textContent = escapeNotice(message);
  noticeEl.hidden = !message;
}

function clearNotice() { notice(""); }

// The upload stop reasons: one line per refused file, escaped (I3).
function renderRefused(list) {
  const lines = (list || []).filter(Boolean);
  refusedEl.innerHTML = "";
  refusedEl.hidden = !lines.length;
  for (const line of lines) refusedEl.append(el("li", {text: escapeControls(line)}));
}

function markDirty() { dirty = true; }

function clone(value) { return JSON.parse(JSON.stringify(value)); }

function checked(id) { return $(id).checked; }

// A font's name for an `aria-label` or an `img alt`: the family and style, escaped the way the table's cells are
// (Q4), so a bidi control in an uploaded family cannot reorder a screen reader's reading of the control either.
function fontName(font) {
  const name = [font.family, font.style].filter(Boolean).join(" ") || font.label || font.id;
  return escapeControls(name + " (" + font.id + ")");
}

function previewSrc(id, fontId, kind) {
  return "/api/jobs/" + encodeURIComponent(id) + "/preview/" + encodeURIComponent(fontId) + "/" +
    encodeURIComponent(kind) + ".png";
}

function parseSizes(text) {
  const out = [];
  const bad = [];
  for (const part of String(text || "").split(",")) {
    const token = part.trim();
    if (!token) continue;
    const size = Number(token);
    if (Number.isInteger(size) && size >= 6 && size <= 96) {
      if (!out.includes(size)) out.push(size);
    } else {
      bad.push(token);
    }
  }
  if (bad.length) notice("ignored sizes " + bad.join(", ") + ": sizes are ints 6..96");
  return out;
}

// ---- the advanced panel's inputs (batch and per font) ---------------------------------------------------------

// Read the batch panel's inputs into the Settings `options` shape; a non-numeric value is refused (I5/M5, P11).
// @p previous is the stored batch options: a field the panel does not show keeps its stored value (Q3/m1), so a
// batch value hidden by the current selection is never dropped on the next save.
function readOptions(root, previous) {
  const options = {mkfont: {}, jamoset: {}};
  const bad = [];
  for (const node of root.querySelectorAll("input[data-option]")) {
    const group = node.dataset.group;
    const key = node.dataset.option;
    if (node.closest("[hidden]")) {                 // a hidden option's stale value is not read (I5), but is kept
      const kept = ((previous || {})[group] || {})[key];
      if (kept !== undefined) options[group][key] = kept;
      continue;
    }
    if (node.type === "checkbox") {
      options[group][key] = node.checked;
      continue;
    }
    const text = node.value.trim();
    if (text === "") options[group][key] = null;
    else if (/^-?\d+$/.test(text)) options[group][key] = Number(text);
    else bad.push(node.dataset.label || key);       // never saved as null: the form names the field instead
  }
  return {options, bad};
}

// Read one font's own advanced panel into `settings.fonts[id].options` (Q1/R1): only the keys the owner set. A
// number left empty and a flag left at "(batch)" remove the key, so the font inherits the batch's value again; an
// untouched key is never written as null or false. A field the panel does not show keeps its stored key, and
// @p per's stored options are the starting point, so a save never drops a value the owner cannot see.
function readPerPanel(box, per) {
  const options = clone(per.options || {});
  const bad = [];
  for (const node of box.querySelectorAll("[data-option]")) {
    const group = node.dataset.group;
    const key = node.dataset.option;
    if (node.closest("[hidden]")) continue;
    if (!options[group]) options[group] = {};
    if (node.tagName === "SELECT") {
      if (node.value === "on") options[group][key] = true;
      else if (node.value === "off") options[group][key] = false;
      else delete options[group][key];
      continue;
    }
    const text = node.value.trim();
    if (text === "") delete options[group][key];
    else if (/^-?\d+$/.test(text)) options[group][key] = Number(text);
    else bad.push(node.dataset.label || key);
  }
  return {options, bad};
}

function optionsAreEmpty(options) {
  for (const group of Object.values(options || {})) {
    for (const value of Object.values(group)) if (value !== null && value !== false) return false;
  }
  return true;
}

function fillOptions(root, options) {
  for (const node of root.querySelectorAll("input[data-option]")) {
    const value = ((options || {})[node.dataset.group] || {})[node.dataset.option];
    if (node.type === "checkbox") node.checked = !!value;
    else node.value = value === null || value === undefined ? "" : value;
  }
}

// Mirrors presets.panel_argv: which option a route label and bpp actually uses (the spec's "Advanced panel options").
// panel_argv emits no JSET flag for the precomposed kind (the copy route of a precomposed SVF has no JSET block).
function optionVisible(key, label, bpp, kind) {
  if (key === "jset_version" && kind === "precomposed") return false;
  return ((OPTION_VISIBLE[label] || {})[String(bpp)] || []).includes(key);
}

// The options a batch value is used by: every font that inherits it (a font's own key is its own, m1) and whose
// route, kinds and bpp can take it (each font's effective kinds and bpp, per-font values included, Q3/m1).
function visibleOptions(fonts, kindsOf, bppOf, inherits) {
  const visible = new Set();
  for (const font of fonts) {
    const per = perFont(font.id) || {};
    const kinds = kindsOf(font, per);
    const bpps = bppOf(font, per);
    for (const route of usableRoutes(font, !!per.experimental)) {
      if (!kinds.includes(route.kind)) continue;
      for (const bpp of route.bpps) {
        if (!bpps.includes(bpp)) continue;
        for (const opt of ADVANCED) {
          if (inherits && !inherits(per, opt)) continue;
          if (optionVisible(opt.key, route.label, bpp, route.kind)) visible.add(opt.key);
        }
      }
    }
  }
  return visible;
}

// The kinds and bpp a font works at: its own when it carries them, the batch's when it inherits them (Q3/m1).
function effectiveKinds(_font, per) { return Array.isArray(per.kinds) ? per.kinds : batchKinds(); }
function effectiveBpp(_font, per) { return Array.isArray(per.bpp) ? per.bpp : batchBpp(); }

// True when the font carries no value of its own for @p opt, so the batch's value is the one it uses.
function inheritsOption(per, opt) {
  const sub = (per.options || {})[opt.group];
  return !(sub && opt.key in sub);
}

function applyVisible(nodes, visible) {
  for (const node of nodes) node.label.hidden = !visible.has(node.key);
}

function batchKinds() { return [...kindsEl.querySelectorAll("input:checked")].map((box) => box.value); }
function batchBpp() { return [...bppEl.querySelectorAll("input:checked")].map((box) => Number(box.value)); }

// ---- the API --------------------------------------------------------------------------------------------------

async function api(method, path, body) {
  const init = {method, headers: {}};
  if (body !== undefined && body !== null) {
    if (typeof Blob !== "undefined" && body instanceof Blob) init.body = body;
    else if (typeof ArrayBuffer !== "undefined" && body instanceof ArrayBuffer) init.body = body;
    else {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (err) {
    const message = method + " " + path + ": " + err;
    notice(message);
    throw new Error(message);
  }
  if (!response.ok) {
    let message = method + " " + path + ": HTTP " + response.status;
    try {
      const data = await response.json();
      if (data && data.error) message += ": " + data.error;
      if (data && Array.isArray(data.errors) && data.errors.length) message += "\n" + data.errors.join("\n");
    } catch (err) { /* a non-JSON error body: the status line stands */ }
    notice(message);
    throw new Error(message);
  }
  try {
    return await response.json();
  } catch (err) {
    notice(method + " " + path + ": the answer is not JSON");
    throw err;
  }
}

// ---- what one font offers (mirrors maker/routes.py) -----------------------------------------------------------

function offeredRoutes(font) {
  const kind = font.source_kind;
  const entries = ROUTES[kind];
  if (!entries) return [];
  const sizes = Array.isArray(font.sizes) ? font.sizes : [];
  if (kind === "outline" || kind === "outline-composite") {
    if ((font.face_index || 0) > 0) return [];
  } else if (kind === "bitmap" || kind === "bdf-iso10646") {
    if ((font.face_index || 0) > 0 || !sizes.length) return [];
  } else if (kind === "bdf-ksc5601") {
    if (!(font.bdf || {}).box) return [];
  } else if (kind === "svf-precomposed" || kind === "svf-jamo") {
    const bpp = (font.svf || {}).bpp;
    if (bpp !== 1 && bpp !== 2) return [];
  }
  const svfBpp = (font.svf || {}).bpp;
  const out = [];
  for (const entry of entries) {
    if (entry.label === "from-svf fit" && svfBpp !== 1) continue;   // only a 1 bpp SVF can be re-fitted
    const bpps = (kind === "svf-precomposed" || kind === "svf-jamo") ? [svfBpp] : entry.bpps.slice();
    if (bpps.some((bpp) => bpp !== 1 && bpp !== 2)) continue;
    out.push({kind: entry.kind, label: entry.label, native: entry.native, bpps});
  }
  return out;
}

function usableRoutes(font, experimental) {
  return offeredRoutes(font).filter((route) => route.native || experimental);
}

function kindReasons(font, experimental) {
  const routes = offeredRoutes(font);
  const usable = usableRoutes(font, experimental).map((route) => route.kind);
  const out = {};
  for (const kind of KINDS) {
    if (usable.includes(kind)) continue;
    if (routes.some((route) => route.kind === kind)) out[kind] = [kind + " needs experimental on a precomposed font"];
    else out[kind] = ["this source has no " + kind + " route"];
  }
  return out;
}

function bppReasons(font, experimental) {
  const routes = usableRoutes(font, experimental);
  const out = {};
  for (const bpp of [1, 2]) {
    if (routes.some((route) => route.bpps.includes(bpp))) continue;
    out[bpp] = ["bpp " + bpp + " is not offered for " + sourcePhrase(font.source_kind) + " source"];
  }
  return out;
}

function sourcePhrase(kind) {
  const word = SOURCE_WORDS[kind] || kind || "unknown";
  return (SOURCE_ARTICLES[word] || "a") + " " + word;
}

// A source preview exists where the server can draw one (PREVIEW_KINDS), the font has a route, and a DOS raw font
// has confirmed its layout (M2/P8: no request, so no console 404/409 on a normal load).
function hasSourcePreview(font, per) {
  if (!per) return false;
  const how = PREVIEW_KINDS[font.source_kind];
  if (!how || how === "none") return false;
  if (font.source_kind === "dos-raw") return !!per.dos_layout;
  return usableRoutes(font, !!per.experimental).length > 0;
}

// ---- the state line, the download, the buttons ----------------------------------------------------------------

function renderStatus() {
  if (!job) {
    stateEl.textContent = "no job";
    positionEl.hidden = true;
    downloadEl.hidden = true;
    saveEl.hidden = true;
    runEl.hidden = true;
    detectEl.hidden = true;
    cancelEl.hidden = true;
    return;
  }
  stateEl.textContent = "job " + job.id + " — " + job.state + (job.error ? " (" + job.error + ")" : "");
  positionEl.hidden = job.queue_position === null || job.queue_position === undefined;
  positionEl.textContent = positionEl.hidden ? "" : "queue position " + job.queue_position;
  downloadEl.hidden = !(job.state === "done" && job.result && job.result.zip);
  downloadEl.href = "/api/jobs/" + encodeURIComponent(job.id) + "/zip";
  saveEl.hidden = job.state !== "detected";
  runEl.hidden = job.state !== "detected";
  detectEl.hidden = !(job.state === "uploading" || job.state === "failed" || job.state === "done");   // I1/S1
  cancelEl.hidden = job.state !== "queued" && job.state !== "running";
}

// ---- jobs list ------------------------------------------------------------------------------------------------

async function renderJobs() {
  let data;
  try {
    data = await api("GET", "/api/jobs");
  } catch (err) {
    return;
  }
  jobsEl.innerHTML = "";
  for (const item of data.jobs || []) {
    const link = el("a", {href: "?job=" + encodeURIComponent(item.id),
                          text: escapeControls(item.id + " " + (item.state || "?") + " (" + (item.fonts || 0) + ")")});
    if (item.id === jobId) link.className = "current";
    jobsEl.append(el("li", {}, link));
  }
}

// ---- the batch form -------------------------------------------------------------------------------------------

function destOptions(stored) {
  const options = DEST_FIXED.map((value) => [value, value]);
  for (const folder of (repo && repo.folders) || []) {
    if (!DEST_FIXED.includes(folder)) options.push([folder, folder]);
  }
  options.push(["__new", "new…"]);
  if (stored && !options.some(([value]) => value === stored)) options.push([stored, stored]);
  return options;
}

function layoutOptions(stored) {
  const options = [["", "—"]];                        // layout is null for a precomposed-only batch
  for (const value of LAYOUTS) options.push([value, value]);
  if (stored && !options.some(([value]) => value === stored)) options.push([stored, stored]);
  return options;
}

function rangeOptions(stored) {
  const options = [["11172", "11172 (all Hangul)"], ["2350", "2350 (KS X 1001)"]];
  if (job) {
    for (const font of job.fonts || []) {
      if (font.format === "list" && font.path && !options.some(([value]) => value === font.path)) {
        options.push([font.path, "file " + font.path]);
      }
    }
  }
  if (stored && !options.some(([value]) => value === stored)) options.push([stored, stored]);
  return options;
}

function presetOptions(stored) {
  const options = PRESETS.map(([value]) => [value, value]);   // Q2: the name only; `presetTitle` carries the rest
  if (stored && !options.some(([value]) => value === stored)) options.push([stored, stored]);
  return options;
}

// The full preset text ("name — what it reproduces") for a select's title tooltip; the unknown name is its own text.
function presetTitle(value) {
  const row = PRESETS.find(([name]) => name === value);
  return row ? row[0] + " — " + row[1] : String(value === null || value === undefined ? "" : value);
}

function renderBatchForm() {
  const batch = (settings && settings.batch) || {};
  // I2: `#dest` shows the stored destination; "new…" only for a `new/...` value that is not a repo folder.
  fillSelect(destEl, destOptions(batch.dest), batch.dest || "dos");
  const custom = !!(batch.dest && batch.dest.startsWith("new/") &&
    !((repo && repo.folders) || []).includes(batch.dest));
  if (custom) { destEl.value = "__new"; destNewEl.value = batch.dest; }
  else destNewEl.value = "";
  destNewEl.disabled = destEl.value !== "__new";

  const kindReasonsAll = allKindReasons();
  for (const box of kindsEl.querySelectorAll("input")) {
    box.checked = Array.isArray(batch.kinds) && batch.kinds.includes(box.value);
    const reason = kindReasonsAll[box.value];
    box.disabled = !!reason;
    box.title = reason ? reason.join("; ") : "";
  }
  fillSelect(layoutEl, layoutOptions(batch.layout), batch.layout === undefined ? "" : batch.layout);
  sizesEl.value = Array.isArray(batch.sizes) ? batch.sizes.join(", ") : "";
  sizesEl.title = offeredSizesReason();
  const bppReasonsAll = allBppReasons();
  for (const box of bppEl.querySelectorAll("input")) {
    box.checked = Array.isArray(batch.bpp) && batch.bpp.includes(Number(box.value));
    const reason = bppReasonsAll[Number(box.value)];
    box.disabled = !!reason;
    box.title = reason ? reason.join("; ") : "";
  }
  fillSelect(rangeEl, rangeOptions(batch.range), batch.range === undefined ? "2350" : batch.range);
  fillSelect(presetEl, presetOptions(batch.preset), batch.preset === undefined ? "plain" : batch.preset);
  presetEl.title = presetTitle(presetEl.value);          // Q2: the long `reproduces` text lives in the tooltip
  fillOptions($("advanced-fields"), batch.options || {});
}

// Q3/m1: the batch panel shows an option when any font that inherits the batch's value could use it, at that font's
// own kinds and bpp (per-font overrides included), not at the batch's kinds and bpp alone.
function refreshBatchOptions() {
  const visible = visibleOptions(batchFonts(), effectiveKinds, effectiveBpp, inheritsOption);
  applyVisible(ADVANCED.map((opt) => ({key: opt.key,
    label: $("advanced-fields").querySelector('[data-field="' + opt.key + '"]')})), visible);
}

function batchFonts() {
  return ((job && job.fonts) || []).filter((font) => settings.fonts && settings.fonts[font.id]);
}

function allKindReasons() {
  const first = {};                                   // kind -> the reason when no font can take it
  for (const kind of KINDS) {
    let usable = false;
    for (const font of batchFonts()) {
      const reasons = kindReasons(font, settings.fonts[font.id].experimental);
      if (!reasons[kind]) { usable = true; break; }
      if (!first[kind]) first[kind] = reasons[kind];
    }
    if (usable) delete first[kind];
  }
  return first;
}

function allBppReasons() {
  const first = {};
  for (const bpp of [1, 2]) {
    let usable = false;
    for (const font of batchFonts()) {
      const reasons = bppReasons(font, settings.fonts[font.id].experimental);
      if (!reasons[bpp]) { usable = true; break; }
      if (!first[bpp]) first[bpp] = reasons[bpp];
    }
    if (usable) delete first[bpp];
  }
  return first;
}

function offeredSizesReason() {
  const fonts = batchFonts();
  const fixed = fonts.filter((font) => font.sizes_fixed);
  if (fixed.length && fixed.length === fonts.length) {
    const strikes = fixed.map((font) => (font.sizes || []).join(" ")).filter(Boolean).join("; ");
    return "every source here is fixed-size: only its own strikes work" + (strikes ? " (" + strikes + ")" : "");
  }
  return "comma-separated sizes, each an int 6..96";
}

function readBatch() {
  const batch = settings.batch;
  if (destEl.value === "__new") {
    const text = destNewEl.value.trim();
    if (text) batch.dest = text;
  } else if (destEl.value) {
    batch.dest = destEl.value;
  }
  batch.kinds = batchKinds();
  batch.layout = layoutEl.value || null;
  batch.sizes = parseSizes(sizesEl.value);
  batch.bpp = batchBpp();
  batch.range = rangeEl.value;
  batch.preset = presetEl.value;
  const read = readOptions($("advanced-fields"), batch.options);
  if (read.bad.length) {
    notice("advanced values must be numbers: " + read.bad.join(", "));   // M5/P11: refused, never saved as null
    return false;
  }
  batch.options = read.options;
  return true;
}

// Read every per-font advanced panel into `settings.fonts[id].options`; a bad value refuses the save.
function readPerOptions() {
  const bad = [];
  for (const {box, per} of perOptionBoxes) {
    if (box.hidden) continue;                          // the toggle is off: unticking it already dropped per.options
    const read = readPerPanel(box, per);
    if (read.bad.length) bad.push(...read.bad);
    else if (optionsAreEmpty(read.options)) delete per.options;
    else per.options = read.options;
  }
  if (bad.length) notice("advanced values must be numbers: " + bad.join(", "));
  return bad.length === 0;
}

// ---- the font table -------------------------------------------------------------------------------------------

function perFont(fontId) {
  return settings && settings.fonts ? settings.fonts[fontId] : undefined;
}

function coverageText(font) {
  const cov = font.coverage || {};
  const show = (value) => (value === null || value === undefined ? "?" : value);
  return show(cov.ascii) + "/" + show(cov.ks2350) + "/" + show(cov.all);
}

function sizesText(font) {
  const sizes = (font.sizes || []).join(", ");
  return font.sizes_fixed ? sizes + " (fixed)" : sizes;
}

function licenceSelect(font, per) {
  const select = el("select", {class: "licence"});
  select.setAttribute("aria-label", "licence for " + fontName(font));
  const stored = (per && per.licence) || null;
  const options = [["", "none"]];
  for (const licence of font.licences || []) {
    options.push(["upload:" + licence.path,
                  licence.path + (licence.first_line ? " — " + licence.first_line : "")]);
  }
  for (const text of (repo && repo.texts) || []) options.push(["repo:" + text.path, "svf/" + text.path]);
  options.push(["text:", "paste…"]);
  if (stored && stored.kind === "upload" && !options.some(([value]) => value === "upload:" + stored.path)) {
    options.push(["upload:" + stored.path, stored.path]);
  }
  if (stored && stored.kind === "repo" && !options.some(([value]) => value === "repo:" + stored.path)) {
    options.push(["repo:" + stored.path, "svf/" + stored.path]);
  }
  fillSelect(select, options, "");

  const area = el("textarea", {class: "licence-text", rows: "3", placeholder: "paste the licence text"});
  area.value = stored && stored.kind === "text" ? stored.text || "" : "";
  // Q2: the select is capped to its cell, so the full name of the chosen licence lives in the tooltip.
  const sync = () => {
    area.hidden = select.value !== "text:";
    const chosen = select.options[select.selectedIndex];
    select.title = chosen ? chosen.textContent : "";
  };
  const write = () => {
    if (!per) return;
    if (select.value === "") per.licence = null;
    else if (select.value.startsWith("upload:")) per.licence = {kind: "upload", path: select.value.slice(7)};
    else if (select.value.startsWith("repo:")) per.licence = {kind: "repo", path: select.value.slice(5)};
    else per.licence = {kind: "text", text: area.value};
    markDirty();
  };
  if (stored && stored.kind === "text") select.value = "text:";
  else if (stored && stored.kind === "upload") select.value = "upload:" + stored.path;
  else if (stored && stored.kind === "repo") select.value = "repo:" + stored.path;
  sync();
  select.disabled = !per;
  area.disabled = !per;
  select.onchange = () => { sync(); write(); };
  area.oninput = () => { if (select.value === "text:" && per) { per.licence = {kind: "text", text: area.value}; markDirty(); } };
  if (!per) select.title = "this entry offers no route";
  return el("div", {class: "licence-cell"}, select, area);
}

function dosLayoutCell(font, per) {
  if (font.source_kind !== "dos-raw") return el("span", {class: "sub", text: "—"});
  const select = el("select", {class: "dos-layout"});
  select.setAttribute("aria-label", "DOS layout for " + fontName(font));
  const options = [["", "confirm"]];
  for (const candidate of (font.dos || {}).candidates || []) {
    if (candidate !== "none") options.push([candidate, candidate]);
  }
  if (per && per.dos_layout && !options.some(([value]) => value === per.dos_layout)) {
    options.push([per.dos_layout, per.dos_layout]);
  }
  fillSelect(select, options, (per && per.dos_layout) || "");
  select.disabled = !per;
  select.onchange = () => { if (per) { per.dos_layout = select.value || null; markDirty(); } };
  return select;
}

function fontMainRow(font, per, override) {
  const tr = el("tr", {dataset: {font: font.id}});
  tr.append(el("td", {class: "fid", text: escapeControls(font.id)}));

  const use = el("input", {type: "checkbox"});
  use.className = "selected";
  use.setAttribute("aria-label", "use " + fontName(font));
  use.disabled = !per;
  use.checked = !!(per && per.selected);
  if (!per) use.title = "this entry offers no route";
  use.onchange = () => { if (per) { per.selected = use.checked; markDirty(); } };
  tr.append(el("td", {}, use));

  const cell = el("td", {});
  if (job && hasSourcePreview(font, per)) {           // M2: no request for an entry that has no preview
    const image = el("img", {class: "preview", loading: "lazy", alt: fontName(font)});
    image.src = previewSrc(job.id, font.id, "source");
    image.onerror = () => { image.hidden = true; };
    cell.append(image);
  }
  tr.append(cell);

  tr.append(el("td", {}, bdi(font.label || "")));
  tr.append(el("td", {}, bdi([font.family, font.style].filter(Boolean).join(" "))));
  tr.append(el("td", {class: "nums", text: sizesText(font)}));
  tr.append(el("td", {class: "nums", text: coverageText(font)}));
  tr.append(el("td", {}, bdi(font.jamo || "none")));
  tr.append(el("td", {}, licenceSelect(font, per)));
  tr.append(el("td", {}, dosLayoutCell(font, per)));

  const toggle = el("input", {type: "checkbox"});
  toggle.className = "override";
  toggle.setAttribute("aria-label", "override " + fontName(font));
  toggle.disabled = !per;
  toggle.onchange = () => { override.hidden = !toggle.checked; };
  tr.append(el("td", {}, toggle));
  return tr;
}

function perFontSelect(per, key, options, fallback, font) {
  const select = el("select");
  select.setAttribute("aria-label", key + " for " + fontName(font));      // Q4: the row's control names the font
  fillSelect(select, [["", "(batch)"]].concat(options), key in per ? per[key] : "");
  select.onchange = () => {
    if (select.value === "") delete per[key];
    else per[key] = select.value;
    markDirty();
  };
  if (fallback !== undefined) select.title = "empty: the batch's value (" + fallback + ")";
  return select;
}

function perFontKinds(per, font, refresh) {
  const select = el("select", {class: "ov-kinds"});
  select.setAttribute("aria-label", "kinds for " + fontName(font));
  const fill = () => {
    const reasons = kindReasons(font, !!per.experimental);
    const options = [["", "(batch)"]];
    options.push(["precomposed", "precomposed — variable width (v3)", reasons.precomposed]);
    options.push(["jamo", "jamo", reasons.jamo]);
    options.push(["precomposed,jamo", "precomposed (v3) + jamo",
                  (reasons.precomposed || []).concat(reasons.jamo || [])]);
    fillSelect(select, options, Array.isArray(per.kinds) ? per.kinds.join(",") : "");
  };
  fill();
  select.onchange = () => {
    if (select.value === "") delete per.kinds;
    else per.kinds = select.value.split(",");
    markDirty();
    for (const run of refresh) run();
  };
  refresh.push(fill);
  return select;
}

function perFontBpp(per, font, refresh) {
  const select = el("select", {class: "ov-bpp"});
  select.setAttribute("aria-label", "bpp for " + fontName(font));
  const fill = () => {
    const reasons = bppReasons(font, !!per.experimental);
    const options = [["", "(batch)"]];
    options.push(["1", "1", reasons[1]]);
    options.push(["2", "2", reasons[2]]);
    options.push(["1,2", "1 + 2", (reasons[1] || []).concat(reasons[2] || [])]);
    fillSelect(select, options, Array.isArray(per.bpp) ? per.bpp.join(",") : "");
  };
  fill();
  select.onchange = () => {
    if (select.value === "") delete per.bpp;
    else per.bpp = select.value.split(",").map(Number);
    markDirty();
    for (const run of refresh) run();
  };
  refresh.push(fill);
  return select;
}

function perFontSizes(per, font) {
  const input = el("input", {type: "text", class: "ov-sizes"});
  input.setAttribute("aria-label", "sizes for " + fontName(font));
  input.value = Array.isArray(per.sizes) ? per.sizes.join(", ") : "";
  const strikes = (font.sizes || []).join(" ");
  input.placeholder = font.sizes_fixed && strikes ? strikes : "(batch)";
  input.title = font.sizes_fixed
    ? "this source is fixed-size: only the strikes " + strikes + " are offered"
    : "comma-separated sizes, each an int 6..96; empty: the batch's value";
  input.onchange = () => {
    if (!input.value.trim()) { delete per.sizes; markDirty(); return; }
    const sizes = parseSizes(input.value);
    if (font.sizes_fixed) {
      const bad = sizes.filter((size) => !(font.sizes || []).includes(size));
      if (bad.length) { notice("size " + bad.join(", ") + " is not a strike of " + font.id); return; }
    }
    per.sizes = sizes;
    input.value = sizes.join(", ");
    markDirty();
  };
  return input;
}

function perFontCompanion(per, font) {
  const select = el("select");
  select.setAttribute("aria-label", "latin companion for " + fontName(font));
  const options = [["", "none"]];
  for (const id of font.companions || []) {
    const other = ((job && job.fonts) || []).find((entry) => entry.id === id);
    options.push([id, id + (other ? " — " + other.path : "")]);
  }
  fillSelect(select, options, per.latin_companion || "");
  select.onchange = () => { per.latin_companion = select.value || null; markDirty(); };
  return select;
}

function perFontText(per, key, font) {
  const input = el("input", {type: "text"});
  input.setAttribute("aria-label", key.replace(/_/g, " ") + " for " + fontName(font));
  input.value = per[key] === null || per[key] === undefined ? "" : per[key];
  input.oninput = () => { per[key] = input.value; markDirty(); };
  return input;
}

function namesField(font) {
  const box = el("div", {class: "names"});
  const names = ((job && job.effective_names) || {})[font.id] || {};
  const keys = Object.keys(names);
  if (!keys.length) {
    box.append(el("p", {class: "sub", text: "no name yet: pick a kind, a size and a bpp first"}));
    return box;
  }
  for (const key of keys) {
    const input = el("input", {type: "text", class: "name", dir: "auto"});
    input.dataset.key = key;
    input.setAttribute("aria-label", "name " + escapeControls(key) + " for " + fontName(font));
    input.value = names[key];
    input.onchange = () => {
      const per = perFont(font.id);
      if (!per) return;
      if (!per.names || typeof per.names !== "object") per.names = {};
      per.names[key] = input.value;
      markDirty();
    };
    box.append(el("div", {class: "name-row"}, el("code", {text: escapeControls(key)}), input));
  }
  return box;
}

// The per-font advanced panel (Q1/R1): a toggle that reveals one field per option. A field shows the batch's value
// as its placeholder (a number) or its first option (`(batch: on/off)`, a flag), and a "reset to batch" button
// removes the font's own key. Only the fields the owner set are read back (readPerPanel), so an untouched field is
// never stored as null or false and never drops the batch's other values.
function advancedFieldset(per, font) {
  const toggle = el("input", {type: "checkbox", class: "ov-advanced-toggle"});
  toggle.checked = !!(per.options && !optionsAreEmpty(per.options));
  toggle.setAttribute("aria-label", "advanced options for " + fontName(font));
  const box = el("div", {class: "override-grid advanced-grid"});
  const nodes = [];
  const stored = (group, key) => ((per.options || {})[group] || {})[key];
  const batchOf = (group, key) => (((settings.batch || {}).options || {})[group] || {})[key];
  for (const opt of ADVANCED) {
    const flag = FLAG_KEYS.has(opt.key);
    const value = stored(opt.group, opt.key);
    const batch = batchOf(opt.group, opt.key);
    const hasBatch = batch !== undefined && batch !== null && batch !== false;
    let input;
    if (flag) {
      input = el("select", {class: "ov-flag"});
      input.title = "empty: the batch's value (" + (batch ? "on" : "off") + ")";
      fillSelect(input, [["", "(batch: " + (batch ? "on" : "off") + ")"], ["on", "on"], ["off", "off"]],
                 value === undefined ? "" : (value ? "on" : "off"));
    } else {
      input = el("input", {type: "text", inputmode: "numeric", size: "4"});
      input.value = value === undefined || value === null ? "" : String(value);
      input.placeholder = hasBatch ? String(batch) : "(batch)";
      input.title = "empty: the batch's value" + (hasBatch ? " (" + batch + ")" : " (none set)");
    }
    input.dataset.option = opt.key;
    input.dataset.group = opt.group;
    input.dataset.label = opt.label;
    input.setAttribute("aria-label", opt.label + " for " + fontName(font));
    const reset = el("button", {type: "button", class: "reset-to-batch", text: "↺"});
    reset.title = "reset to batch: " + opt.label;
    reset.setAttribute("aria-label", "reset " + opt.label + " to the batch for " + fontName(font));
    reset.onclick = () => { input.value = ""; markDirty(); };
    const label = el("label", {class: "label", dataset: {field: opt.key}},
      el("span", {text: opt.label + " "}), input, reset);
    nodes.push({key: opt.key, label});
    box.append(label);
  }
  box.hidden = !toggle.checked;
  box.addEventListener("input", markDirty);
  box.addEventListener("change", markDirty);
  // Unticking the toggle drops the font's own options (the panel is not read while it is hidden), so the fields it
  // would show next time belong to the batch again.
  toggle.onchange = () => {
    box.hidden = !toggle.checked;
    if (!toggle.checked) { delete per.options; for (const node of box.querySelectorAll("[data-option]")) node.value = ""; }
    markDirty();
  };
  const refresh = () => {
    const visible = visibleOptions([font], effectiveKinds, effectiveBpp);
    applyVisible(nodes, visible);
  };
  refresh();
  return {toggle, box, refresh};
}

function overridePanel(font, per) {
  const grid = el("div", {class: "override-grid"});
  grid.append(el("h3", {}, bdi(font.path + (font.version ? " — " + font.version : ""))));
  const refresh = [];

  const kinds = perFontKinds(per, font, refresh);
  const bpp = perFontBpp(per, font, refresh);
  const experimental = el("input", {type: "checkbox"});
  experimental.className = "ov-experimental";
  experimental.setAttribute("aria-label", "experimental for " + fontName(font));
  experimental.checked = !!per.experimental;
  experimental.onchange = () => {
    per.experimental = experimental.checked;
    markDirty();
    for (const run of refresh) run();                 // jamo, 2 bpp and the panel options become usable (or not)
  };

  const advanced = advancedFieldset(per, font);
  refresh.push(advanced.refresh);
  refresh.push(refreshBatchOptions);
  perOptionBoxes.push({box: advanced.box, per});

  grid.append(el("label", {class: "label"}, el("span", {text: "dest "}),
    perFontSelect(per, "dest", destOptions(per.dest).filter(([value]) => value !== "__new"), settings.batch.dest, font)));
  grid.append(el("label", {class: "label"}, el("span", {text: "kinds "}), kinds));
  grid.append(el("label", {class: "label"}, el("span", {text: "layout "}),
    perFontSelect(per, "layout", LAYOUTS.map((value) => [value, value]), settings.batch.layout, font)));
  grid.append(el("label", {class: "label"}, el("span", {text: "sizes "}), perFontSizes(per, font)));
  grid.append(el("label", {class: "label"}, el("span", {text: "bpp "}), bpp));
  grid.append(el("label", {class: "label"}, el("span", {text: "range "}),
    perFontSelect(per, "range", rangeOptions(per.range), settings.batch.range, font)));
  grid.append(el("label", {class: "label"}, el("span", {text: "preset "}),
    perFontSelect(per, "preset", presetOptions(per.preset), settings.batch.preset, font)));
  grid.append(el("label", {class: "label"}, experimental, el("span", {text: " experimental"})));
  grid.append(el("label", {class: "label"}, el("span", {text: "latin companion "}), perFontCompanion(per, font)));
  grid.append(el("label", {class: "label"}, el("span", {text: "licence name "}), perFontText(per, "licence_name", font)));
  grid.append(el("label", {class: "label"}, el("span", {text: "note name "}), perFontText(per, "note_name", font)));
  grid.append(el("label", {class: "label"}, advanced.toggle, el("span", {text: " advanced options"})));
  grid.append(advanced.box);
  grid.append(namesField(font));
  return grid;
}

function buildFonts() {
  fontsEl.innerHTML = "";
  perOptionBoxes = [];
  if (!job || !(job.fonts || []).length) return;
  const head = el("thead", {}, el("tr", {},
    ...["id", "use", "preview", "label", "family/style", "sizes", "coverage", "jamo", "licence", "layout", "override"]
      .map((title) => el("th", {text: title}))));
  const body = el("tbody");
  for (const font of job.fonts) {
    const per = perFont(font.id);
    const override = el("tr", {class: "override", hidden: true, dataset: {for: font.id}});
    const cell = el("td", {colspan: "11"});
    if (per) cell.append(overridePanel(font, per));
    else cell.append(el("p", {class: "sub", text: "this entry offers no route: nothing to make from it"}));
    override.append(cell);
    body.append(fontMainRow(font, per, override), override);
  }
  fontsEl.append(head, body);
}

// ---- the steps table ------------------------------------------------------------------------------------------

function qualityText(step) {
  const quality = step.quality;
  if (!quality) return "";
  const all = typeof quality.all === "number" ? quality.all.toFixed(3) : String(quality.all);
  return all;
}

function stepRow(step) {
  const tr = el("tr", {dataset: {step: step.id}});
  tr.append(el("td", {class: "fid", text: escapeControls(step.id)}));
  tr.append(el("td", {class: "fid", text: escapeControls(step.font || "")}));
  tr.append(el("td", {}, bdi(step.kind || "")));
  tr.append(el("td", {class: "nums", text: step.size === null || step.size === undefined ? "" : String(step.size)}));
  tr.append(el("td", {class: "nums", text: step.bpp === null || step.bpp === undefined ? "" : String(step.bpp)}));
  tr.append(el("td", {class: "nums", text: escapeControls(step.name || "")}));

  const state = el("td", {});
  state.append(el("span", {text: escapeControls(step.state || "")}));
  if (step.error) state.append(el("div", {class: "sub", text: escapeControls(step.error)}));
  if (step.identical_to) state.append(el("div", {class: "sub", text: "identical to " + escapeControls(step.identical_to)}));
  tr.append(state);

  tr.append(el("td", {class: "nums",
    text: typeof step.seconds === "number" ? step.seconds.toFixed(1) + " s" : ""}));

  const quality = el("td", {class: "nums", text: qualityText(step)});
  if (step.quality) {
    const parts = [];
    if (step.quality.ks2350 !== null && step.quality.ks2350 !== undefined) parts.push("ks2350 " + step.quality.ks2350);
    if (step.quality.compared !== null && step.quality.compared !== undefined) parts.push("compared " + step.quality.compared);
    quality.title = parts.join(", ");
  }
  tr.append(quality);

  tr.append(el("td", {}, el("pre", {class: "stderr", text: escapeControls(step.stderr_tail || "")})));

  const result = el("td", {});
  if (job && step.preview) {
    const image = el("img", {class: "preview", loading: "lazy", alt: escapeControls(step.name || step.id)});
    image.src = previewSrc(job.id, step.font, step.id);
    image.onerror = () => { image.hidden = true; };
    result.append(image);
  }
  tr.append(result);
  return tr;
}

function buildSteps() {
  stepsEl.innerHTML = "";
  if (!job || !(job.steps || []).length) return;
  stepsEl.append(el("thead", {}, el("tr", {},
    ...["id", "font", "kind", "size", "bpp", "name", "state", "seconds", "quality", "stderr", "result"]
      .map((title) => el("th", {text: title})))));
  const body = el("tbody");
  for (const step of job.steps) body.append(stepRow(step));
  stepsEl.append(body);
}

// ---- render ---------------------------------------------------------------------------------------------------

function renderAll() {
  renderStatus();
  settingsEl.hidden = !job;
  if (job) renderBatchForm();
  buildFonts();
  buildSteps();
  renderRefused(job && job.upload ? job.upload.refused : []);
  refreshBatchOptions();
}

async function reload() {
  try {
    job = await api("GET", "/api/jobs/" + encodeURIComponent(jobId));
  } catch (err) {
    return;
  }
  settings = clone(job.settings || {batch: {}, fonts: {}});
  dirty = false;
  renderAll();
}

async function loadJob(id) {
  try {
    job = await api("GET", "/api/jobs/" + encodeURIComponent(id));
  } catch (err) {
    job = null;
    jobId = null;
    renderAll();
    return;
  }
  jobId = job.id;
  settings = clone(job.settings || {batch: {}, fonts: {}});
  dirty = false;
  renderAll();
  if (job.state === "queued" || job.state === "running") startPolling();
}

// ---- actions --------------------------------------------------------------------------------------------------

function stopPolling() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setTimeout(poll, POLL_MS);
}

async function poll() {
  pollTimer = null;
  if (!jobId) return;
  try {
    job = await api("GET", "/api/jobs/" + encodeURIComponent(jobId));
  } catch (err) {
    /* the notice carries the error; keep polling while the state says so */
  }
  if (job) {
    if (!dirty) settings = clone(job.settings || {batch: {}, fonts: {}});
    renderStatus();
    buildSteps();
    renderRefused(job.upload ? job.upload.refused : []);
  }
  if (job && (job.state === "queued" || job.state === "running")) startPolling();
  else renderJobs();
}

async function upload() {
  clearNotice();
  const chosen = Array.from(filesEl.files || []).concat(Array.from(folderEl.files || []));
  if (!chosen.length && !jobId) {
    notice("choose files or a folder first");
    return;
  }
  if (!jobId) {
    let created;
    try {
      created = await api("POST", "/api/jobs");
    } catch (err) {
      return;
    }
    jobId = created.id;
    job = {id: jobId, state: "uploading"};
    settings = {batch: {}, fonts: {}};
    renderStatus();                                  // the state line shows the new job while its files go up
    history.replaceState(null, "", "?job=" + jobId);   // a reload mid-upload still finds the job
  }
  const stopped = [];
  let done = 0;
  for (const file of chosen) {
    const rel = file.webkitRelativePath || file.name;
    let answer;
    try {
      answer = await api("PUT", "/api/jobs/" + encodeURIComponent(jobId) + "/files?path=" + encodeURIComponent(rel),
                         file);
    } catch (err) {
      countEl.textContent = "";
      return;
    }
    const unpacked = answer && answer.unpacked;
    if (unpacked && unpacked.stopped) stopped.push(rel + ": " + unpacked.stopped);   // I3: an archive cut short
    renderRefused(stopped);
    countEl.textContent = ++done + "/" + chosen.length;
  }
  countEl.textContent = "";
  try {
    await api("POST", "/api/jobs/" + encodeURIComponent(jobId) + "/detect");
  } catch (err) {
    return;
  }
  history.replaceState(null, "", "?job=" + jobId);
  await reload();                                    // the GET carries effective_names; detect's answer does not
  await renderJobs();
}

// I1/S1: re-run the detect path for a job that is `uploading`, `failed` or `done`, then reload it.
async function detect() {
  clearNotice();
  if (!jobId) return;
  try {
    await api("POST", "/api/jobs/" + encodeURIComponent(jobId) + "/detect");
  } catch (err) {
    return;
  }
  history.replaceState(null, "", "?job=" + jobId);
  await reload();
  await renderJobs();
}

async function save() {
  clearNotice();
  if (!jobId) return;
  if (!readBatch()) return;
  if (!readPerOptions()) return;
  try {
    await api("PUT", "/api/jobs/" + encodeURIComponent(jobId) + "/settings", settings);
  } catch (err) {
    return;
  }
  await reload();
  await renderJobs();
}

async function run() {
  clearNotice();
  if (!jobId) return;
  if (dirty) {
    if (!readBatch()) return;
    if (!readPerOptions()) return;
    try {
      await api("PUT", "/api/jobs/" + encodeURIComponent(jobId) + "/settings", settings);
    } catch (err) {
      return;
    }
    await reload();
  }
  try {
    await api("POST", "/api/jobs/" + encodeURIComponent(jobId) + "/run");
  } catch (err) {
    return;
  }
  await reload();
  startPolling();
  await renderJobs();
}

async function cancel() {
  clearNotice();
  if (!jobId) return;
  try {
    await api("POST", "/api/jobs/" + encodeURIComponent(jobId) + "/cancel");
  } catch (err) {
    startPolling();                                   // "not running" is the server's answer; keep polling anyway
    return;
  }
  await reload();
  startPolling();
}

// ---- wiring ---------------------------------------------------------------------------------------------------

function wire() {
  settingsEl.addEventListener("submit", (event) => event.preventDefault());
  uploadEl.onclick = upload;
  saveEl.onclick = save;
  runEl.onclick = run;
  detectEl.onclick = detect;
  cancelEl.onclick = cancel;
  destEl.onchange = () => { destNewEl.disabled = destEl.value !== "__new"; markDirty(); };
  presetEl.onchange = () => { presetEl.title = presetTitle(presetEl.value); };   // Q2: the short label keeps the tooltip
  const count = () => {
    const chosen = (filesEl.files || []).length + (folderEl.files || []).length;
    countEl.textContent = chosen ? chosen + " file(s) chosen" : "";
  };
  filesEl.onchange = count;
  folderEl.onchange = count;
  for (const node of settingsEl.querySelectorAll("input, select")) {
    if (node.type === "checkbox" || node.tagName === "SELECT") node.addEventListener("change", markDirty);
    else node.addEventListener("input", markDirty);
  }
  for (const box of [kindsEl, bppEl]) {
    for (const node of box.querySelectorAll("input")) node.addEventListener("change", refreshBatchOptions);
  }
}

async function init() {
  wire();
  let repoError = null;
  try {
    repo = await api("GET", "/api/repo");
  } catch (err) {
    repo = null;
    repoError = err.message || String(err);           // M1: kept visible after a `?job=` load
  }
  const id = new URLSearchParams(location.search).get("job");
  if (id) await loadJob(id);
  else renderAll();
  if (repoError) notice(repoError);
  await renderJobs();
}

init();
