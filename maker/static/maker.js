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

import * as svfview from "./svfview.js";
import {parseDyText, stepSig, busyRetryDelay, isBusyKind, BUSY_RETRY_MS, BUSY_RETRY_TOTAL_MS} from "./pagelib.js";
import {cutList} from "./clip.js";

const POLL_MS = 2000;
const SAMPLE_TEXT = "다람쥐 헌 쳇바퀴에 타고파 ABC xyz 0123";   // detect.SAMPLE_TEXT

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
              {"kind": "jamo", "label": "experimental fit", "native": false, "bpps": [1, 2]},
              {"kind": "jamo", "label": "mask fit", "native": false, "bpps": [1]},
              {"kind": "jamo", "label": "vector fit", "native": false, "bpps": [1, 2]}],
  "outline-composite": [{"kind": "precomposed", "label": "mkfont", "native": true, "bpps": [1, 2]},
                        {"kind": "jamo", "label": "composite", "native": true, "bpps": [1, 2]},
                        {"kind": "jamo", "label": "mask fit", "native": false, "bpps": [1]},
                        {"kind": "jamo", "label": "vector fit", "native": false, "bpps": [1, 2]}],
  "bitmap": [{"kind": "precomposed", "label": "mkfont", "native": true, "bpps": [1]}],
  "bdf-iso10646": [{"kind": "precomposed", "label": "mkfont", "native": true, "bpps": [1]}],
  "bdf-ksc5601": [{"kind": "precomposed", "label": "bdfface", "native": true, "bpps": [1]},
                  {"kind": "jamo", "label": "bdfface + from-svf fit", "native": false, "bpps": [1]}],
  "bdf-johab": [{"kind": "jamo", "label": "hanterm", "native": true, "bpps": [1]}],
  "dos-raw": [{"kind": "precomposed", "label": "johab844", "native": true, "bpps": [1]},
              {"kind": "jamo", "label": "dos raw", "native": true, "bpps": [1]}],
  "svf-precomposed": [{"kind": "precomposed", "label": "copy", "native": true, "bpps": [1, 2]},
                      {"kind": "jamo", "label": "from-svf fit", "native": false, "bpps": [1]}],
  "svf-jamo": [{"kind": "jamo", "label": "copy", "native": true, "bpps": [1, 2]}],
  "mac-fbit1": [{"kind": "jamo", "label": "mac fbit 1.0", "native": true, "bpps": [1]}],
  "mac-fbit3": [{"kind": "jamo", "label": "mac fbit 7.1 direct", "native": true, "bpps": [1]},
                {"kind": "jamo", "label": "mac fbit 7.1 derived", "native": false, "bpps": [1]},
                {"kind": "precomposed", "label": "mac fbit 7.1 bdf + mkfont", "native": true, "bpps": [1]}]
};

const KINDS = ["precomposed", "jamo"];
const LAYOUTS = ["844", "adaptive", "hanterm-johab", "mac-htbl1", "mac-fbit-45sets"];
const DEST_FIXED = ["dos", "jamo-extra"];

// The advanced panel's inputs (Shared data shapes `options`); `group` is the tool the key belongs to, and a key in
// `FLAG_KEYS` is a boolean (`false` in DEFAULT_OPTIONS, `true` for `FLAG_DEFAULT_ON`), a key in `CHOICE_KEYS` one of
// its strings, the rest a number (`null`). Keys are unique across the three groups.
const ADVANCED = [
  {key: "cell", group: "mkfont", label: "cell"},
  {key: "ascent", group: "mkfont", label: "ascent"},
  {key: "width", group: "mkfont", label: "width"},
  {key: "space_advance", group: "mkfont", label: "space advance"},
  {key: "mono_hint", group: "mkfont", label: "mono hint"},
  {key: "clip_cell", group: "mkfont", label: "clip cell"},
  {key: "fit_cell", group: "mkfont", label: "fit cell"},
  {key: "latin", group: "mkfont", label: "Latin top"},
  {key: "embolden", group: "jamoset", label: "embolden"},
  {key: "symbols", group: "jamoset", label: "symbols"},
  {key: "jset_version", group: "jamoset", label: "JSET version"},
  {key: "jamo_ascent", group: "jamoset", label: "header ascent"},
  {key: "fit_baseline", group: "jamoset", label: "fit baseline"},
  {key: "aa_refine", group: "jamoset", label: "AA refine"},
  {key: "clean", group: "jamoset", label: "clean noise"},
  {key: "binarize", group: "jamoset", label: "binarize"},
  {key: "latin_ascent", group: "bdfface", label: "Latin ascent"},
  {key: "hangul_ascent", group: "bdfface", label: "Hangul ascent"},
];

const FLAG_KEYS = new Set(["mono_hint", "clip_cell", "fit_cell", "latin", "embolden", "symbols", "clean"]);
// A flag whose batch default is on (settings.DEFAULT_OPTIONS): "off" is the value worth storing.
const FLAG_DEFAULT_ON = new Set(["clean"]);
// settings.OPTION_CHOICES: a key drawn as a <select data-option>; its first value is the default.
const CHOICE_KEYS = {"binarize": ["threshold", "ridge", "mono"]};

// Mirrors presets.panel_argv: which option a route label and bpp actually uses (the spec's "Advanced panel
// options"), i.e. the option keys the panel shows for that route. Only labels the routes above offer appear. Strict
// JSON (the drift test compares it with the flags panel_argv emits for every route label and bpp).
const OPTION_VISIBLE = {
  "mkfont": {"1": ["cell", "ascent", "width", "mono_hint", "clip_cell", "fit_cell", "latin", "space_advance"],
             "2": ["cell", "ascent", "width", "clip_cell", "fit_cell", "latin", "space_advance"]},
  "johab844": {"1": []},
  "dos raw": {"1": ["embolden", "symbols", "jset_version", "jamo_ascent"]},
  "hanterm": {"1": ["embolden", "symbols", "jset_version", "jamo_ascent"]},
  "composite": {"1": ["symbols", "jset_version", "fit_baseline", "binarize"],
                "2": ["symbols", "jset_version", "fit_baseline"]},
  "experimental fit": {"1": ["jset_version", "fit_baseline", "binarize"],
                       "2": ["symbols", "jset_version", "fit_baseline", "aa_refine", "clean"]},
  "mask fit": {"1": ["jset_version", "fit_baseline", "binarize"]},
  "vector fit": {"1": ["symbols", "jset_version", "fit_baseline", "binarize"],
                 "2": ["symbols", "jset_version", "fit_baseline"]},
  "copy": {"1": ["jset_version"], "2": ["jset_version"]},
  "from-svf fit": {"1": ["jset_version"]},
  "bdfface": {"1": ["latin_ascent", "hangul_ascent"]},
  "bdfface + from-svf fit": {"1": ["jset_version", "latin_ascent", "hangul_ascent"]},
  "mac fbit 1.0": {"1": ["embolden", "symbols", "jset_version", "jamo_ascent"]},
  "mac fbit 7.1 direct": {"1": []},
  "mac fbit 7.1 derived": {"1": ["jset_version"]},
  "mac fbit 7.1 bdf + mkfont": {"1": ["cell", "ascent", "width", "space_advance"]}
};

// Mirrors server._make_source_preview: how the page gets a source preview, per source kind. "draw": the server draws
// the source with Pillow (`preview.source_png`); "bake": it bakes the source first (a DOS raw font also needs its
// layout confirmed); "none": no preview (a Latin-only BDF, a BDF FreeType gives no Unicode charmap, an HBF, a kind
// with no face). Strict JSON (the drift test classifies every kind in presets.ALL_SOURCES).
const PREVIEW_KINDS = {
  "outline": "draw", "outline-composite": "draw", "bitmap": "draw", "bdf-iso10646": "draw",
  "bdf-iso8859": "none", "bdf-ksc5601": "none", "bdf-johab": "none", "hbf": "none",
  "dos-raw": "bake", "svf-precomposed": "bake", "svf-jamo": "bake", "mac-fbit3": "bake", "mac-fbit1": "bake", "mac-htbl": "none",
  "mac-suitcase": "none", "other": "none"
};

// settings._SOURCE_WORDS / _SOURCE_ARTICLES: the phrase the validator uses in its reasons. Strict JSON.
const SOURCE_WORDS = {
  "dos-raw": "DOS raw", "outline": "outline", "outline-composite": "outline", "bitmap": "bitmap",
  "bdf-iso10646": "bitmap", "bdf-iso8859": "bitmap", "bdf-ksc5601": "bitmap", "bdf-johab": "bitmap", "hbf": "bitmap",
  "svf-precomposed": "SVF", "svf-jamo": "SVF", "mac-fbit3": "Mac fbit", "mac-fbit1": "Mac fbit", "mac-htbl": "Mac table",
  "mac-suitcase": "Mac suitcase"
};
const SOURCE_ARTICLES = {
  "outline": "an", "SVF": "an"
};

// The Cc/Cf characters the Task 11 note names, plus the bidi controls that can reorder a cell.
const CONTROL_RE = /[\u0000-\u001f\u007f-\u009f\u200e\u200f\u202a-\u202e\u2066-\u2069]/g;

const $ = (id) => document.getElementById(id);
const stateEl = $("state");
const noticeEl = $("notice");
const noticeRetryEl = $("notice-retry");
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
const deleteJobEl = $("delete-job");
const jobNoticeEl = $("job-notice");
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
const openFolderEl = $("open-folder");
const uploadPanelEl = $("upload-panel");
const sourcesPanelEl = $("sources-panel");
const rootsEl = $("source-roots");
const sourcePathsEl = $("source-paths");
const sourcePathsLabelEl = $("source-paths-label");
const outputDirEl = $("output-dir");
const outputDirLabelEl = $("output-dir-label");
const outputShownEl = $("output-shown");
const chooseFilesEl = $("choose-files");
const chooseFolderEl = $("choose-folder");
const chooseOutputEl = $("choose-output");
const detectLocalEl = $("detect-local");
const ackEl = $("ack");
const ackOkEl = $("ack-ok");

// Local mode (the server was started with a per-launch token): the fonts are read where they are and the results are
// written into an output folder. `roots` and `output` are what the bridge picked (typed paths are read from the fields).
const state = {local: false, roots: [], output: "", acknowledged: false};
const ACK_KEY = "svfMakerAcknowledged";

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

// The notice epoch: every public notice() / clearNotice() (an action starting, a message of its own) moves it, hides the
// "Try again" control and rejects a request that waits on it; api() watches it so that a retry the user has moved on
// from sends nothing more. api()'s own lines (the retry line, the exhausted message) go through setNoticeQuiet.
let noticeEpoch = 0;
let busyWait = null;                                  // {resolve, reject, error, args}: the one request waiting on "Try again"

function setNoticeQuiet(message) {
  noticeEl.textContent = escapeNotice(message);
  noticeEl.hidden = !message;
}

// Hide the control and reject the request that waits on it with its original error.
function dropBusyWait() {
  const wait = busyWait;
  busyWait = null;
  noticeRetryEl.hidden = true;
  if (wait) wait.reject(wait.error);
}

function notice(message) {
  noticeEpoch++;
  dropBusyWait();
  setNoticeQuiet(message);
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
  const options = {mkfont: {}, jamoset: {}, bdfface: {}};
  const bad = [];
  for (const node of root.querySelectorAll("[data-option]")) {
    const group = node.dataset.group;
    const key = node.dataset.option;
    if (node.closest("[hidden]")) {                 // a hidden option's stale value is not read (I5), but is kept
      const kept = ((previous || {})[group] || {})[key];
      if (kept !== undefined) options[group][key] = kept;
      continue;
    }
    if (node.tagName === "SELECT") {                // a choice: its string value
      options[group][key] = node.value;
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
    if (node.tagName === "SELECT" && CHOICE_KEYS[key]) {      // a choice: its string, empty = the batch's
      if (node.value === "") delete options[group][key];
      else options[group][key] = node.value;
      continue;
    }
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
    for (const [key, value] of Object.entries(group)) {
      if (value === null) continue;
      if (value === false && !FLAG_DEFAULT_ON.has(key)) continue;     // "off" is a value for a default-on flag
      return false;
    }
  }
  return true;
}

function fillOptions(root, options) {
  for (const node of root.querySelectorAll("[data-option]")) {
    const key = node.dataset.option;
    const value = ((options || {})[node.dataset.group] || {})[key];
    if (node.tagName === "SELECT") node.value = CHOICE_KEYS[key] && CHOICE_KEYS[key].includes(value) ? value : CHOICE_KEYS[key][0];
    else if (node.type === "checkbox") node.checked = value === undefined ? FLAG_DEFAULT_ON.has(key) : !!value;
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
      if (route.kind === "jamo" && per.jamo_route && route.label !== per.jamo_route) continue;   // the chosen route
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

const sleepMs = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// The retry bounds, read at call time. `window.__busyBounds` (tests only) may override the delays, the total, the follow
// interval, the clock and the sleep; the production values are pagelib's.
function busyBounds() {
  const o = (typeof window !== "undefined" && window.__busyBounds) || {};
  return {retryMs: o.retryMs || BUSY_RETRY_MS, totalMs: o.totalMs !== undefined ? o.totalMs : BUSY_RETRY_TOTAL_MS,
          followMs: o.followMs !== undefined ? o.followMs : 1000, now: o.now || Date.now, sleep: o.sleep || sleepMs};
}

// The run-retry generation: a request tagged with `opts.runGen` stops retrying (and never shows "Try again") once the
// generation has moved, which `followOtherRun` does when it sees the other run start.
let runGen = 0;

// One JSON call. A 409 the server tagged `busy` is repeated after 0.5, 1 and 2 s (a bounded retry of the one request,
// never after a network error and never once the user has started anything else: the notice epoch), then the notice
// stays with a "Try again" button that sends the identical request once more. The thrown Error carries `body`.
async function api(method, path, body, opts = {}) {
  const init = {method, headers: {}};
  if (body !== undefined && body !== null) {
    if (typeof Blob !== "undefined" && body instanceof Blob) init.body = body;
    else if (typeof ArrayBuffer !== "undefined" && body instanceof ArrayBuffer) init.body = body;
    else {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
  }
  const epoch = noticeEpoch;                          // before the first send: an action started meanwhile cancels the retry
  const bounds = busyBounds();
  const start = bounds.now();
  const superseded = () => noticeEpoch !== epoch || (opts.runGen !== undefined && opts.runGen !== runGen);
  let repeats = 0;
  let retried = false;
  for (;;) {
    let response;
    try {
      response = await fetch(path, init);
    } catch (err) {
      const message = method + " " + path + ": " + err;
      notice(message);
      throw new Error(message);
    }
    if (response.ok) {
      try {
        const data = await response.json();
        if (retried && noticeEpoch === epoch) setNoticeQuiet("");
        return data;
      } catch (err) {
        notice(method + " " + path + ": the answer is not JSON");
        throw err;
      }
    }
    let message = method + " " + path + ": HTTP " + response.status;
    let data = null;
    try {
      data = await response.json();
      if (data && data.error) message += ": " + data.error;
      if (data && Array.isArray(data.errors) && data.errors.length) message += "\n" + data.errors.join("\n");
    } catch (err) { /* a non-JSON error body: the status line stands */ }
    const error = new Error(message);
    error.body = data;
    const kind = response.status === 409 && data ? data.busy : undefined;
    if (!isBusyKind(kind)) {
      notice(message);
      throw error;
    }
    if (superseded()) throw error;                    // the user moved on while this answer was pending
    const delay = busyRetryDelay(method, kind, repeats, bounds.now() - start, bounds);
    if (delay !== null) {
      retried = true;
      setNoticeQuiet(message + " (retrying " + (repeats + 1) + "/" + bounds.retryMs.length + ")");
      await bounds.sleep(delay);
      if (superseded()) throw error;
      if (bounds.now() - start < bounds.totalMs) {   // the deadline is checked again right before the send
        repeats++;
        continue;
      }
    }
    // no (further) automatic retry: the message stays, with a "Try again" for the identical request
    if (superseded()) throw error;
    setNoticeQuiet(message);
    dropBusyWait();                                   // one control: a second exhausted call replaces the first
    noticeRetryEl.hidden = false;
    return new Promise((resolve, reject) => {
      busyWait = {resolve, reject, error, args: [method, path, body, opts]};
      if (typeof opts.onWait === "function") opts.onWait(kind, epoch);
    });
  }
}

function tryAgain() {
  const wait = busyWait;
  if (!wait) return;
  busyWait = null;
  noticeRetryEl.hidden = true;
  setNoticeQuiet("");
  wait.resolve(api(...wait.args));
}

// ---- what one font offers (mirrors maker/routes.py) -----------------------------------------------------------

function offeredRoutes(font) {
  const kind = font.source_kind;
  const entries = ROUTES[kind];
  if (!entries) return [];
  const sizes = Array.isArray(font.sizes) ? font.sizes : [];
  if (kind === "outline" || kind === "outline-composite") {
    if ((font.face_index || 0) > 0 && !(font.prep || []).length) return [];
  } else if (kind === "bitmap" || kind === "bdf-iso10646") {
    if (((font.face_index || 0) > 0 && !(font.prep || []).length) || !sizes.length) return [];
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
    if (entry.label === "mask fit" && !(font.gsub_jamo && font.mask_ok)) continue;   // GSUB jamo and the libraries
    if (entry.label === "johab844" && !(font.dos_bytes === 11520 && ((font.dos || {}).candidates || []).includes("844"))) continue;
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
    openFolderEl.hidden = true;
    positionEl.hidden = true;
    downloadEl.hidden = true;
    saveEl.hidden = true;
    runEl.hidden = true;
    detectEl.hidden = true;
    cancelEl.hidden = true;
    deleteJobEl.hidden = true;
    jobNoticeEl.hidden = true;
    return;
  }
  const local = job.source === "local";
  stateEl.textContent = "job " + job.id + " — " + job.state + (job.error ? " (" + job.error + ")" : "") +
    (local && job.state === "done" && job.output_dir ? " — written to " + job.output_dir : "");
  openFolderEl.hidden = !(local && job.state === "done");
  openFolderEl.disabled = !bridgeCan("openOutputFolder");
  positionEl.hidden = job.queue_position === null || job.queue_position === undefined;
  positionEl.textContent = positionEl.hidden ? "" : "queue position " + job.queue_position;
  downloadEl.hidden = !(job.state === "done" && job.result && job.result.zip);
  downloadEl.href = "/api/jobs/" + encodeURIComponent(job.id) + "/zip";
  saveEl.hidden = job.state !== "detected";
  runEl.hidden = job.state !== "detected";
  detectEl.hidden = !(job.state === "uploading" || job.state === "failed" || job.state === "done");   // I1/S1
  cancelEl.hidden = job.state !== "queued" && job.state !== "running";
  // a local job holds its output folder (409 for another job) until it is deleted or has been idle for a while
  deleteJobEl.hidden = !(local && job.state !== "queued" && job.state !== "running");
  jobNoticeEl.textContent = escapeNotice(job.notice || "");      // e.g. intermediates left in a moved output folder
  jobNoticeEl.hidden = !job.notice;
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

const NAMED_RANGES = ["11172", "2350", "ksx1001-nohanja", "ksx1001-symbols", "ksx1001", "jamo", "cp949"];

// A range select's value: a named range as it is; a list file as its path, and in a local job as `list:<root>:<path>`
// (the same path can sit under two roots; the settings keep `range` and `range_root` apart).
function rangeValue(range, root) {
  if (state.local && range !== undefined && range !== null && !NAMED_RANGES.includes(range)) {
    return "list:" + (root || 0) + ":" + range;
  }
  return range;
}

// Store a range select's value into a settings dict (the batch's or a font's): `range`, and `range_root` for a list file.
function setRange(target, value) {
  const m = /^list:(\d+):([\s\S]*)$/.exec(value);
  if (state.local && m) {
    target.range = m[2];
    target.range_root = Number(m[1]);
  } else {
    target.range = value;
    delete target.range_root;
  }
}

function rangeOptions(stored, storedRoot) {
  const options = [["11172", "11172 (all Hangul)"], ["2350", "2350 (KS X 1001)"],
    ["ksx1001-nohanja", "KS X 1001 without hanja"], ["ksx1001-symbols", "KS X 1001 symbols"], ["ksx1001", "KS X 1001"],
    ["jamo", "compatibility jamo"], ["cp949", "CP949"]];
  if (job) {
    for (const font of job.fonts || []) {
      const value = rangeValue(font.path, font.root);
      if (font.format === "list" && font.path && !options.some(([v]) => v === value)) {
        options.push([value, "file " + fontPathText(font)]);
      }
    }
  }
  const have = rangeValue(stored, storedRoot);
  if (stored && !options.some(([value]) => value === have)) options.push([have, stored]);
  return options;
}

// The per-font range select: the batch's range unless the font names its own (a list file also names its root).
function perFontRange(per, font) {
  const select = el("select");
  select.setAttribute("aria-label", "range for " + fontName(font));
  fillSelect(select, [["", "(batch)"]].concat(rangeOptions(per.range, per.range_root)),
             "range" in per ? rangeValue(per.range, per.range_root) : "");
  select.onchange = () => {
    if (select.value === "") { delete per.range; delete per.range_root; } else setRange(per, select.value);
    markDirty();
  };
  if (settings.batch.range !== undefined) select.title = "empty: the batch's value (" + settings.batch.range + ")";
  return select;
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
  fillSelect(rangeEl, rangeOptions(batch.range, batch.range_root),
             batch.range === undefined ? "2350" : rangeValue(batch.range, batch.range_root));
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
  setRange(batch, rangeEl.value);
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

// An uploaded licence is `upload:<path>`; in a local job it also names the root it was found under:
// `upload:<root>:<path>` (the server resolves a path against its root). A licence is optional either way.
function uploadLicenceValue(licence) {
  return "upload:" + (state.local ? (licence.root || 0) + ":" : "") + licence.path;
}

function parseUploadLicence(value) {
  if (state.local) {
    const m = /^upload:(\d+):([\s\S]*)$/.exec(value);
    if (m) return {kind: "upload", root: Number(m[1]), path: m[2]};
  }
  return {kind: "upload", path: value.slice(7)};
}

// A font's path as the table shows it: a local job's names the root it lives under (`a/Munjo.ttf`).
function fontPathText(font) {
  if (!state.local || !job || !Array.isArray(job.roots) || !job.roots[font.root || 0]) return font.path || "";
  return job.roots[font.root || 0].name + "/" + font.path;
}

function licenceSelect(font, per) {
  const select = el("select", {class: "licence"});
  select.setAttribute("aria-label", "licence for " + fontName(font));
  const stored = (per && per.licence) || null;
  const options = [["", "none"]];
  for (const licence of font.licences || []) {
    options.push([uploadLicenceValue(licence),
                  licence.path + (licence.first_line ? " — " + licence.first_line : "")]);
  }
  for (const text of (repo && repo.texts) || []) options.push(["repo:" + text.path, "svf/" + text.path]);
  options.push(["text:", "paste…"]);
  if (stored && stored.kind === "upload" && !options.some(([value]) => value === uploadLicenceValue(stored))) {
    options.push([uploadLicenceValue(stored), stored.path]);
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
    else if (select.value.startsWith("upload:")) per.licence = parseUploadLicence(select.value);
    else if (select.value.startsWith("repo:")) per.licence = {kind: "repo", path: select.value.slice(5)};
    else per.licence = {kind: "text", text: area.value};
    markDirty();
  };
  if (stored && stored.kind === "text") select.value = "text:";
  else if (stored && stored.kind === "upload") select.value = uploadLicenceValue(stored);
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
    if (PREVIEW_KINDS[font.source_kind] === "bake") {   // a baked source: its face drawn by the WASM renderer
      cell.append(sourceFaceCanvas(font));
    } else {
      const image = el("img", {class: "preview", loading: "lazy", alt: fontName(font)});
      image.src = previewSrc(job.id, font.id, "source");
      image.onerror = () => { image.hidden = true; };
      cell.append(image);
    }
  }
  tr.append(cell);

  const labelCell = el("td", {}, bdi(font.label || ""));
  if (state.local) labelCell.append(el("div", {class: "sub"}, bdi(fontPathText(font))));
  tr.append(labelCell);
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
  // a Mac 7.1 fbit's Latin companions are the suitcases with a strike at its size; its companions are HTBL tables
  const candidates = font.source_kind === "mac-fbit3" ? (font.latin_candidates || []) : (font.companions || []);
  for (const id of candidates) {
    const other = ((job && job.fonts) || []).find((entry) => entry.id === id);
    options.push([id, id + (other ? " — " + other.path : "")]);
  }
  fillSelect(select, options, per.latin_companion || "");
  select.onchange = () => { per.latin_companion = select.value || null; markDirty(); };
  return select;
}

// The Mac 7.1 fbit's HTBL 1 table: one of the batch's `mac-htbl` entries (its composition rules are a separate file).
function perFontHtbl(per, font) {
  const select = el("select", {"data-field": "htbl_companion"});
  select.setAttribute("aria-label", "HTBL table for " + fontName(font));
  const options = [["", "none: add the table to the sources"]];
  for (const id of font.companions || []) {
    const other = ((job && job.fonts) || []).find((entry) => entry.id === id);
    options.push([id, id + (other ? " — " + other.path : "")]);
  }
  fillSelect(select, options, per.htbl_companion || "");
  select.onchange = () => { per.htbl_companion = select.value || null; markDirty(); };
  return select;
}

// The variable-font chooser: "default instance" or one of the font's named instances (value = its coordinates as JSON).
function perFontInstance(per, font) {
  const select = el("select", {"data-field": "instance"});
  select.setAttribute("aria-label", "instance for " + fontName(font));
  const instances = (font.variable || {}).instances || [];
  const options = [["", "default instance"]];
  for (const instance of instances) options.push([JSON.stringify(instance.coords), instance.name]);
  let current = per.instance ? JSON.stringify(per.instance) : "";
  if (current && !options.some(([value]) => value === current)) {
    options.push([current, "custom " + current]);                // a value set elsewhere stays visible
  }
  fillSelect(select, options, current);
  select.onchange = () => { per.instance = select.value ? JSON.parse(select.value) : null; markDirty(); };
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
    if (CHOICE_KEYS[opt.key]) {
      const first = CHOICE_KEYS[opt.key][0];
      const shown = batch === undefined || batch === null ? first : batch;
      input = el("select", {class: "ov-choice"});
      input.title = "empty: the batch's value (" + shown + ")";
      fillSelect(input, [["", "(batch: " + shown + ")"], ...CHOICE_KEYS[opt.key].map((v) => [v, v])],
                 value === undefined || value === null ? "" : value);
    } else if (flag) {
      const on = batch === undefined ? FLAG_DEFAULT_ON.has(opt.key) : !!batch;
      input = el("select", {class: "ov-flag"});
      input.title = "empty: the batch's value (" + (on ? "on" : "off") + ")";
      fillSelect(input, [["", "(batch: " + (on ? "on" : "off") + ")"], ["on", "on"], ["off", "off"]],
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

// The per-font dy table (spec 7.5), shown while a precomposed face is selected: "U+0041=1 g=-1 0x67=2", written to
// per.dy as {"0x41": 1} (hex keys). Empty clears it.
function dyText(dy) {
  return Object.entries(dy || {}).map(([k, v]) => k + "=" + v).join(" ");
}

function dyEditor(per, font, refresh) {
  const input = el("input", {type: "text", size: "30", placeholder: "U+0041=1 g=-1",
                             "aria-label": "dy table for " + fontName(font)});
  input.value = dyText(per.dy);
  input.onchange = () => {
    const parsed = parseDyText(input.value);
    if (parsed === null) {
      notice("dy: tokens are CODEPOINT=ROWS (U+0041=1, g=-1, 0x67=2), ROWS -128..127");
      return;
    }
    const keys = Object.keys(parsed).map(Number).sort((a, b) => a - b);
    per.dy = keys.length ? Object.fromEntries(keys.map((cp) => ["0x" + cp.toString(16).toUpperCase(), parsed[cp]])) : null;
    markDirty();
  };
  const label = el("label", {class: "label", dataset: {field: "dy"}}, el("span", {text: "dy "}), input);
  refresh.push(() => { label.hidden = !effectiveKinds(font, per).includes("precomposed"); });
  label.hidden = !effectiveKinds(font, per).includes("precomposed");
  return label;
}

// A local edit of a font's own options from the page (the clipping panel's "apply"): the panels are read first so a
// typed value is not lost, then the table is rebuilt to show the change.
function applyLocal(per, mutate, message) {
  readPerOptions();
  mutate(per);
  markDirty();
  buildFonts();
  notice(message + "; save the settings to keep it");
}

// The "clipping" disclosure of a font with a mkfont route (spec 8.3): a probe bake (tall cell, nothing cut) and its box
// report, from which the rows any cell would cut are computed here for the ascent typed (clip.js, fit_counts' rule),
// listed and drawn over the probe face. "Apply" writes the ascent and ticks clip_cell.
function clippingPanel(font, per, optionBox) {
  if (!usableRoutes(font, !!per.experimental).some((route) => route.label === "mkfont")) return null;
  const details = el("details", {class: "clipping"}, el("summary", {text: "clipping"}));
  const effSizes = () => (Array.isArray(per.sizes) ? per.sizes : (settings.batch.sizes || []));
  const effBpps = () => (Array.isArray(per.bpp) ? per.bpp : (settings.batch.bpp || []));
  const sizeSel = el("select", {"aria-label": "clipping size"});
  fillSelect(sizeSel, effSizes().map((v) => [String(v), String(v) + " px"]), String(effSizes()[0] ?? ""));
  const bppSel = el("select", {"aria-label": "clipping bpp"});
  fillSelect(bppSel, effBpps().map((v) => [String(v), String(v) + " bpp"]), String(effBpps()[0] ?? ""));
  const note = el("div", {class: "sub"});
  const ascentIn = el("input", {type: "text", inputmode: "numeric", size: "3", "aria-label": "clipping ascent"});
  const cellEl = el("span", {class: "sub"});
  const counts = el("div", {class: "clip-counts"});
  const wrap = el("div", {class: "canvaswrap"});
  const canvas = el("canvas", {class: "result clip-overlay"});
  wrap.append(canvas);
  const list = el("div", {class: "clip-list"});
  const apply = el("button", {type: "button", text: "apply"});
  let report = null, face = null, selected = null, loaded = false;

  const effOption = (key) => {
    const own = ((per.options || {}).mkfont || {})[key];
    return own !== undefined && own !== null ? own : (((settings.batch.options || {}).mkfont || {})[key] ?? null);
  };
  // the cell the build cuts at: the step's own (a preset may carry --cell), else the effective cell option, else the size
  // A cell typed in the (open) advanced panel and not yet saved wins: it is what the user is about to build with.
  const typedCell = () => {
    const node = optionBox && optionBox.querySelector('[data-option="cell"]');
    if (!node || node.closest("[hidden]")) return null;
    const text = String(node.value).trim();
    return /^\d+$/.test(text) && Number(text) >= 4 ? Number(text) : null;
  };
  const cellH = () => typedCell() || (report && report.step_cell) || effOption("cell") || Number(sizeSel.value);

  const url = (ext) => "/api/jobs/" + encodeURIComponent(job.id) + "/probe/" + encodeURIComponent(font.id) + "/" +
    sizeSel.value + "/" + bppSel.value + "." + ext;

  const update = async () => {
    if (!report) return;
    const ascent = Number(ascentIn.value);
    const h = cellH();
    cellEl.textContent = "cell " + h + " rows";
    note.textContent = dirty ? "unsaved edits: the probe was measured with the saved settings; only the cell typed here is live" : "";
    if (!Number.isInteger(ascent) || ascent < 1) {
      counts.textContent = "ascent must be a whole number from 1";
      list.replaceChildren();                           // no ascent, no cut rows: the list and the overlay go too
      for (const old of wrap.querySelectorAll(".guide, .clip-band")) old.remove();
      return;
    }
    const cut = cutList(report, ascent, h, report.cell[0]);
    counts.textContent = cut.cut.toLocaleString("en") + " glyphs cut: " + cut.top.toLocaleString("en") + " at the top, " +
      cut.bottom.toLocaleString("en") + " at the bottom; " + cut.wide.toLocaleString("en") + " wider than the cell" +
      (effOption("fit_cell") ? " (fit cell is on: the run decides the size)" : "");
    list.replaceChildren();
    for (const row of cut.rows.slice(0, 200)) {
      const line = el("div", {class: "clip-row", dataset: {cp: String(row.cp)}, text:
        "U+" + row.cp.toString(16).toUpperCase().padStart(4, "0") + " " + String.fromCodePoint(row.cp) +
        "  top " + row.top + "  bottom " + row.bottom});
      line.onclick = () => { selected = row.cp; update(); };
      list.append(line);
    }
    if (cut.rows.length > 200) list.append(el("div", {class: "sub", text: "and " + (cut.rows.length - 200).toLocaleString("en") + " more"}));
    if (!face) return;                                   // no probe face (the ink spans past 255 rows): list and counts only
    const text = previewState.text + " " + cut.rows.slice(0, 12).map((row) => String.fromCodePoint(row.cp)).join("") +
      (selected !== null ? " " + String.fromCodePoint(selected) : "");
    try {
      await withChain([face], () => {
        svfview.setScale(1, 1);
        const r = svfview.drawLine(canvas, text, {target: "gray8"});
        canvas.style.imageRendering = "pixelated";
        canvas.style.width = canvas.width * 2 + "px";
        for (const old of wrap.querySelectorAll(".guide, .clip-band")) old.remove();
        const probeTop = 1, probeBottom = 1 + report.cell[1];     // the probe face's rows in the canvas
        const top = r.baseline - ascent, bottom = top + h;
        const band = (from, to) => {
          if (to <= from) return;
          const node = el("div", {class: "clip-band"});
          node.style.top = (from * 2) + "px";
          node.style.height = ((to - from) * 2) + "px";
          wrap.append(node);
        };
        band(probeTop, Math.min(top, probeBottom));
        band(Math.max(bottom, probeTop), probeBottom);
        const frame = el("div", {class: "guide clip-frame"});
        frame.style.top = (top * 2) + "px";
        frame.style.height = (h * 2) + "px";
        wrap.append(frame);
      });
    } catch (err) {
      counts.append(" (" + escapeControls(err && err.message) + ")");
    }
  };

  const load = async () => {
    report = null;
    face = null;
    selected = null;
    counts.textContent = "measuring…";
    try {
      const response = await fetch(url("json"), {cache: "no-cache"});
      if (!response.ok) throw new Error("no probe (" + response.status + "): save the settings first if the size or bpp is new");
      report = await response.json();
      if (report.probe_face) face = await fetchFresh(url("svf"));
    } catch (err) {
      counts.textContent = escapeControls(err && err.message);
      return;
    }
    if (ascentIn.value.trim() === "") ascentIn.value = String(report.step_ascent ?? report.auto_ascent);
    await update();
  };

  details.addEventListener("toggle", () => { if (details.open && !loaded) { loaded = true; load(); } });
  // The selectors follow the fields above as they change (sizes, bpp, cell); a size or bpp the server has not saved yet
  // has no probe, which the counts line says.
  details.sync = () => {
    const keep = [sizeSel.value, bppSel.value];
    fillSelect(sizeSel, effSizes().map((v) => [String(v), String(v) + " px"]), keep[0]);
    fillSelect(bppSel, effBpps().map((v) => [String(v), String(v) + " bpp"]), keep[1]);
    if (!effSizes().map(String).includes(keep[0])) sizeSel.value = String(effSizes()[0] ?? "");
    if (!effBpps().map(String).includes(keep[1])) bppSel.value = String(effBpps()[0] ?? "");
    if (details.open && loaded && (sizeSel.value !== keep[0] || bppSel.value !== keep[1])) { ascentIn.value = ""; load(); }
    else update();
  };
  sizeSel.onchange = () => { ascentIn.value = ""; load(); };
  bppSel.onchange = () => { ascentIn.value = ""; load(); };
  ascentIn.oninput = () => update();
  apply.onclick = () => {
    const ascent = Number(ascentIn.value);
    if (!Number.isInteger(ascent) || ascent < 1) return;
    applyLocal(per, (p) => {
      p.options = p.options || {};
      p.options.mkfont = Object.assign({}, p.options.mkfont || {}, {ascent, clip_cell: true, fit_cell: false});
    }, "ascent " + ascent + " and clip cell set");
  };
  details.append(el("div", {class: "svf-controls"}, sizeSel, bppSel, el("label", {}, "ascent ", ascentIn), cellEl, apply),
    note, counts, wrap, list);
  return details;
}

// The jamo route this font's jamo faces use (`jamo_route`): the routes it offers, the default being the first native
// one, else (with experimental) the first non-native. `vector fit` says it takes minutes per font.
function jamoRouteSelect(per, font, refresh) {
  const label = el("label", {class: "label"}, el("span", {text: "jamo route "}));
  const select = el("select", {"aria-label": "jamo route for " + fontName(font)});
  const fill = () => {
    const options = [["", "(default)"]];
    for (const route of offeredRoutes(font)) {
      if (route.kind !== "jamo") continue;
      const text = route.label + (route.label === "vector fit" ? " (minutes per font)" : "") + (route.native ? "" : " (experimental)");
      options.push([route.label, text, !route.native && !per.experimental ? ["needs experimental"] : null]);
    }
    fillSelect(select, options, per.jamo_route || "");
  };
  fill();
  select.onchange = () => {
    if (select.value === "") delete per.jamo_route;
    else per.jamo_route = select.value;
    markDirty();
    for (const run of refresh) run();                       // the options this route uses are shown
  };
  refresh.push(fill);
  label.append(select);
  return label;
}

function overridePanel(font, per) {
  const grid = el("div", {class: "override-grid"});
  grid.append(el("h3", {}, bdi(fontPathText(font) + (font.version ? " — " + font.version : ""))));
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
    perFontRange(per, font)));
  grid.append(el("label", {class: "label"}, el("span", {text: "preset "}),
    perFontSelect(per, "preset", presetOptions(per.preset), settings.batch.preset, font)));
  grid.append(jamoRouteSelect(per, font, refresh));
  grid.append(el("label", {class: "label"}, experimental, el("span", {text: " experimental"})));
  grid.append(el("label", {class: "label"}, el("span", {text: "latin companion "}), perFontCompanion(per, font)));
  if (font.source_kind === "mac-fbit3") {
    grid.append(el("label", {class: "label"}, el("span", {text: "HTBL table "}), perFontHtbl(per, font)));
  }
  if (font.variable) {
    grid.append(el("label", {class: "label"}, el("span", {text: "instance "}), perFontInstance(per, font)));
  }
  grid.append(el("label", {class: "label"}, el("span", {text: "licence name "}), perFontText(per, "licence_name", font)));
  grid.append(el("label", {class: "label"}, el("span", {text: "note name "}), perFontText(per, "note_name", font)));
  grid.append(el("label", {class: "label"}, advanced.toggle, el("span", {text: " advanced options"})));
  grid.append(advanced.box);
  grid.append(dyEditor(per, font, refresh));
  const clipping = clippingPanel(font, per, advanced.box);
  if (clipping) {
    grid.append(clipping);
    grid.addEventListener("input", clipping.sync);          // the sizes, bpp and cell fields feed the panel as they are typed
    grid.addEventListener("change", clipping.sync);
  }
  grid.append(namesField(font));
  return grid;
}

function buildFonts() {
  fontsEl.innerHTML = "";
  sourceRedraws.length = 0;
  sourceBytes = new Map();
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

// ---- the result and source previews (the WASM renderer) ------------------------------------------------------

const LATIN_FALLBACK_URL = "/api/repo/face/dos/NEODG16.SVF";
const previewState = {text: SAMPLE_TEXT, scale: 1, target: "gray8", threshold: 128, guides: false};
const sourceRedraws = [];                            // the redraw functions of the source canvases (rebuilt with the font table)
const stepRows = new Map();                          // step id -> {sig, tr}: a finished step's row is kept across polls
let sourceBytes = new Map();                         // url -> Promise<Uint8Array>, for one build of the font table
let latinBytes = null;                               // the repo's Latin companion (immutable)
let svfReady = null;                                 // svfview.load(), once
let drawChain = Promise.resolve();                   // draws run one at a time: the module has one chain

function svfModule() {
  if (!svfReady) {
    svfReady = svfview.load();
    svfReady.catch(() => notice(svfview.NOTICE));
  }
  return svfReady;
}

// A fresh read of @p url: the browser revalidates by ETag (the server answers 304), so a face the server re-baked or a
// step a re-run rewrote is never served from an earlier fetch.
function fetchFresh(url) {
  return fetch(url, {cache: "no-cache"}).then((response) => {
    if (!response.ok) throw new Error(url + ": " + response.status);
    return response.arrayBuffer();
  }).then((buffer) => new Uint8Array(buffer));
}

function repoLatin() {
  if (!latinBytes) {
    latinBytes = fetchFresh(LATIN_FALLBACK_URL);
    latinBytes.catch(() => { latinBytes = null; });
  }
  return latinBytes;
}

function faceUrl(step) {
  return "/api/jobs/" + encodeURIComponent(job.id) + "/face/" + encodeURIComponent(step.id) + ".svf";
}

// The same font's done precomposed face at this size (the Latin and the glyphs a jamo face lacks), else null.
function companionStep(step) {
  if (step.kind !== "jamo") return null;
  return (job.steps || []).find((other) => other !== step && other.font === step.font && other.kind === "precomposed"
    && other.size === step.size && other.state === "done") || null;
}

// Draw `fn` with the chain `faces` open; serialized (the module has one chain and one scale).
function withChain(faces, fn) {
  const run = drawChain.then(async () => {
    await svfModule();
    const infos = svfview.openChain(faces);
    return fn(infos);
  });
  drawChain = run.catch(() => {});
  return run;
}

function canvasOptions() {
  return {target: previewState.target, threshold: previewState.threshold};
}

function paintGuides(wrap, r, zoom, force) {
  for (const old of wrap.querySelectorAll(".guide")) old.remove();
  if (!(previewState.guides || force) || !r) return;
  const box = svfview.cellBox(0, r.baseline, r.ascentOverride);
  for (const [name, row] of [["top", box.top], ["baseline", box.baseline], ["bottom", box.bottom]]) {
    const line = el("div", {class: "guide guide-" + name});
    line.style.top = (row * zoom) + "px";
    wrap.append(line);
  }
}

// A small canvas with a baked source face of a DOS raw or SVF entry (GET .../source/<font>.svf), redrawn with the
// sample text and target controls. Its bytes are fetched afresh for each build of the font table.
function sourceFaceCanvas(font) {
  const holder = el("span", {class: "source-face"});
  const canvas = el("canvas", {class: "preview", "data-font": font.id});
  holder.append(canvas);
  const url = "/api/jobs/" + encodeURIComponent(job.id) + "/source/" + encodeURIComponent(font.id) + ".svf";
  const draw = async () => {
    try {
      if (!sourceBytes.has(url)) sourceBytes.set(url, fetchFresh(url));
      const bytes = await sourceBytes.get(url);
      await withChain([bytes], () => {
        svfview.setScale(1, 1);
        svfview.drawLine(canvas, previewState.text, canvasOptions());
      });
    } catch (err) {
      if (err && err.message === svfview.NOTICE) {
        holder.replaceChildren(el("span", {class: "sub", text: svfview.NOTICE}));
      } else {
        canvas.hidden = true;
      }
    }
  };
  draw();
  sourceRedraws.push(draw);
  return holder;
}

// The font's effective value of a jamoset option: its own, else the batch's.
function jamosetOption(fontId, key) {
  const own = (((settings.fonts || {})[fontId] || {}).options || {}).jamoset || {};
  if (key in own) return own[key];
  return (((settings.batch || {}).options || {}).jamoset || {})[key];
}

// The result cell of a done face step: the sample line drawn by the WASM renderer from the step's own bytes, with the
// sample text, scale, target, threshold, guides, the glyph grid and (per kind) an ascent or dy to try. Returns
// {node, redraw}; the step's bytes are fetched once for the life of the cell (a re-run makes a new cell).
function previewCell(step) {
  const box = el("div", {class: "svf-preview"});
  const font = (job.fonts || []).find((item) => item.id === step.font) || {};
  const wrap = el("div", {class: "canvaswrap"});
  const canvas = el("canvas", {class: "result", "data-step": step.id});
  wrap.append(canvas);
  const fail = el("div", {class: "sub", hidden: true});
  const hint = el("div", {class: "sub"});
  const tryState = {ascent: null, dy: {}};
  const mate = companionStep(step);
  let bytes = null;
  const chainBytes = () => {
    if (!bytes) {
      bytes = Promise.all([fetchFresh(faceUrl(step)), mate ? fetchFresh(faceUrl(mate)) : null]);
      bytes.catch(() => { bytes = null; });
    }
    return bytes;
  };

  const draw = async () => {
    fail.hidden = true;
    try {
      const [face, companion] = await chainBytes();
      await withChain(companion ? [face, companion] : [face], async (infos) => {
        if (!companion && !svfview.has(0, 0x41)) {                  // the face has no Latin: the repo's companion
          infos = svfview.openChain([face, await repoLatin()]);
        }
        svfview.setScale(previewState.scale, 1);
        const useGlyphs = tryState.ascent !== null || Object.keys(tryState.dy).length > 0;
        const opts = canvasOptions();
        let r;
        if (useGlyphs) {
          if (tryState.ascent !== null) opts.ascentOverride = tryState.ascent;
          opts.dy = tryState.dy;
          // a DOS raw face carries the two symbol glyphs when the build was told --symbols: by the option or by a preset
          // (jamo-844-symbols, jamo-844-hbios24) that puts the flag in the step's own argv
          opts.symbolsFixed = jamosetOption(step.font, "symbols") === true ||
            (step.argv || []).some((argv) => Array.isArray(argv) && argv.includes("--symbols"));
          r = svfview.drawGlyphs(canvas, previewState.text, opts);
          if (r) r.ascentOverride = tryState.ascent;
        } else {
          r = svfview.drawLine(canvas, previewState.text, opts);
        }
        canvas.style.imageRendering = "pixelated";
        canvas.style.width = canvas.width * 2 + "px";
        paintGuides(wrap, r, 2, tryState.ascent !== null);      // a header ascent moves the baseline only: show it
        hint.textContent = "";
        if (tryState.ascent !== null) {
          hint.textContent = "baseline row " + infos[0].ascent + " -> " + tryState.ascent + " (the line looks the same: " +
            "the cell and the baseline move together; watch the guides)" +
            (opts.symbolsFixed && tryState.ascent < infos[0].ascent
              ? "; symbols are approximate below the header ascent (a rebuild re-frames them)" : "");
        }
      });
    } catch (err) {
      canvas.dataset.error = String(err && err.message ? err.message : err);
      fail.textContent = escapeControls(canvas.dataset.error);
      fail.hidden = false;
    }
  };

  // controls
  const text = el("input", {type: "text", size: "24", value: previewState.text, "aria-label": "sample text"});
  text.oninput = () => { previewState.text = text.value; redrawPreviews(); };
  const scale = el("select", {"aria-label": "scale"});
  fillSelect(scale, [1, 2, 3, 4].map((n) => [String(n), n + "/1"]), previewState.scale);
  scale.onchange = () => { previewState.scale = Number(scale.value); redrawPreviews(); };
  const target = el("select", {"aria-label": "target"});
  fillSelect(target, [["gray8", "GRAY8"], ["mono", "MONO"], ["rgb565", "RGB565"]], previewState.target);
  target.onchange = () => { previewState.target = target.value; redrawPreviews(); };
  const threshold = el("input", {type: "text", inputmode: "numeric", size: "3", value: String(previewState.threshold),
                                 "aria-label": "mono threshold"});
  threshold.onchange = () => {
    const v = Number(threshold.value);
    if (Number.isInteger(v) && v >= 0 && v <= 255) { previewState.threshold = v; redrawPreviews(); }
  };
  const guides = el("input", {type: "checkbox", "aria-label": "guides"});
  guides.checked = previewState.guides;
  guides.onchange = () => { previewState.guides = guides.checked; redrawPreviews(); };
  const controls = el("div", {class: "svf-controls"}, text, scale, target, threshold,
    el("label", {}, guides, " guides"));

  const grid = glyphGrid(step, chainBytes);
  const toggle = el("button", {type: "button", text: "glyphs"});
  toggle.onclick = () => { grid.box.hidden = !grid.box.hidden; if (!grid.box.hidden) grid.show(); };
  controls.append(toggle);

  if (step.kind === "jamo" && (font.source_kind === "dos-raw" || font.source_kind === "bdf-johab")) {
    const ascent = el("input", {type: "text", inputmode: "numeric", size: "3", "aria-label": "ascent to try"});
    ascent.onchange = () => {
      const v = ascent.value.trim() === "" ? null : Number(ascent.value);
      tryState.ascent = v !== null && Number.isInteger(v) && v >= 1 ? v : null;
      draw();
    };
    const apply = el("button", {type: "button", text: "apply ascent"});
    apply.onclick = () => {
      if (tryState.ascent === null) return;
      const value = tryState.ascent;
      applySetting(step.font, "header ascent " + value, (per) => {
        per.options = per.options || {};
        per.options.jamoset = Object.assign({}, per.options.jamoset || {}, {jamo_ascent: value});
      });
    };
    controls.append(el("label", {}, "ascent ", ascent), apply);
  }
  if (step.kind === "precomposed") {
    const dy = el("input", {type: "text", size: "10", placeholder: "U+0041=1 g=-1", "aria-label": "dy to try"});
    dy.onchange = () => {
      tryState.dy = parseDyText(dy.value) || {};
      draw();
    };
    const apply = el("button", {type: "button", text: "apply dy"});
    apply.onclick = () => {
      if (!Object.keys(tryState.dy).length) return;
      const tried = Object.assign({}, tryState.dy);
      applySetting(step.font, "dy", (per) => {
        const merged = Object.assign({}, per.dy || {});
        for (const [cp, v] of Object.entries(tried)) merged["0x" + Number(cp).toString(16).toUpperCase()] = v;
        per.dy = merged;
      });
    };
    controls.append(el("label", {}, "dy ", dy), apply);
  }

  box.append(controls, wrap, hint, fail, grid.box);
  if (step.kind === "jamo") box.append(piecesPanel(step, chainBytes, mate));
  draw();
  return {node: box, redraw: draw};
}

// The pieces panel of a jamo step (spec 9.5): the identity check's verdict line and, opened, the per-piece table from
// GET .../identity/<step>.json. Each row draws its piece at 2x; a row opens to its worst syllables as the jamo face
// composes them beside the same syllables from the font's precomposed face of that size when one is done.
const IDENTITY_UNAVAILABLE = "identity check unavailable (set SVF_RECOG_DIR to a folder with recog.py and its weights; numpy and torch needed)";
const FLAG_COLOURS = {pass: "#2a7a3b", warn: "#a86b00", fail: "#b3261e", unavailable: "#777", unscored: "#777", unused: "#777"};

function piecesPanel(step, chainBytes, mate) {
  const box = el("div", {class: "pieces-panel"});
  const identity = step.identity;
  const line = el("div", {class: "pieces-summary"});
  box.append(line);
  if (!identity || identity.available !== true) {
    line.style.color = FLAG_COLOURS.unavailable;
    line.textContent = identity && identity.error ? "identity check failed: " + escapeControls(identity.error)
                                                  : IDENTITY_UNAVAILABLE;
    if (identity && identity.structural) box.append(el("div", {class: "sub", text: escapeControls(identity.structural)}));
    return box;
  }
  if (identity.applicable === false) {
    line.textContent = "identity check: " + escapeControls(identity.reason || "not applicable");
    return box;
  }
  const counts = identity.pieces || {};
  line.style.color = FLAG_COLOURS[identity.identity] || "inherit";
  line.textContent = "identity " + identity.identity + ": " + (counts.pass || 0) + " pass, " + (counts.warn || 0) + " warn, " +
    (counts.fail || 0) + " fail" + (counts.unscored ? ", " + counts.unscored + " unscored" : "") +
    (typeof identity.recog_ks === "number" ? "; KS X 1001 read " + (identity.recog_ks * 100).toFixed(1) + "%" : "");
  const details = el("details", {class: "pieces"}, el("summary", {text: "pieces"}));
  const table = el("div", {class: "pieces-table"});
  details.append(table);
  let loaded = false;
  details.addEventListener("toggle", async () => {
    if (!details.open || loaded) return;
    loaded = true;
    try {
      const response = await fetch("/api/jobs/" + encodeURIComponent(job.id) + "/identity/" + encodeURIComponent(step.id) + ".json",
                                   {cache: "no-cache"});
      if (!response.ok) throw new Error("identity.json: " + response.status);
      const data = await response.json();
      const [face, companion] = await chainBytes();
      const glyphs = [];                                   // [canvas, piece number], drawn with one chain below
      for (const piece of data.pieces || []) {
        const row = el("div", {class: "piece-row piece-" + piece.flag, dataset: {piece: String(piece.piece), flag: piece.flag}});
        const canvas = el("canvas", {class: "piece-glyph"});
        row.append(canvas,
          el("span", {text: " " + piece.slot + " " + piece.jamo + " set " + piece.set + "  users " + piece.users + "  read " +
            (piece.read * 100).toFixed(1) + "%  "}),
          el("b", {text: piece.flag, style: "color:" + (FLAG_COLOURS[piece.flag] || "inherit")}));
        glyphs.push([canvas, piece.piece]);
        if (piece.flag === "fail") {
          row.append(el("div", {class: "sub", text: "fix: fit again with a mask (mask fit, 1 bpp), more sets (adaptive), or a " +
            "LIST exception for its worst syllables (jamoexc.py, not in the maker)"}));
        }
        const worst = el("div", {class: "piece-worst", hidden: true});
        let drawing = false;                                // one fill of the worst syllables per row, however fast the clicks
        row.onclick = async () => {
          worst.hidden = !worst.hidden;
          if (worst.hidden || worst.childElementCount || drawing) return;
          drawing = true;
          try {
          for (const w of piece.worst || []) {
            const cell = el("span", {class: "piece-worst-cell", text: "U+" + w.cp.toString(16).toUpperCase() + " read " + (w.got || "-") + " "});
            const mine = el("canvas", {});
            cell.append(mine);
            await withChain([face], () => { svfview.setScale(1, 1); svfview.drawLine(mine, String.fromCodePoint(w.cp), {}); });
            if (companion) {
              const theirs = el("canvas", {});
              cell.append(" vs ", theirs);
              await withChain([companion], () => { svfview.setScale(1, 1); svfview.drawLine(theirs, String.fromCodePoint(w.cp), {}); });
            }
            worst.append(cell);
          }
          } finally {
            drawing = false;
          }
        };
        row.append(worst);
        table.append(row);
      }
      await withChain([face], () => { for (const [canvas, number] of glyphs) svfview.drawPiece(canvas, 0, number, 2); });
      if (data.bpp_note) table.append(el("div", {class: "sub", text: escapeControls(data.bpp_note)}));
    } catch (err) {
      table.textContent = escapeControls(err && err.message);
    }
  });
  box.append(details);
  return box;
}

// "Apply" of an ascent or dy to try: settings are accepted only while the job is being edited, so a finished job is
// re-opened first (detect keeps the settings), the value is written into the reloaded settings and saved. A running
// job cannot be re-opened. The job is then ready to run again (its old steps are gone).
async function applySetting(fontId, what, mutate) {
  clearNotice();
  if (!jobId || !job) return;
  if (job.state === "queued" || job.state === "running") {
    notice("the job is running: apply " + what + " when it has finished");
    return;
  }
  if (job.state !== "detected") {
    const lost = "Re-opening the job for editing discards its built faces and the zip" +
      (dirty ? ", and unsaved settings are replaced by the saved ones" : "") + ". Apply and re-open?";
    if (!window.confirm(lost)) return;
    try {
      await api("POST", "/api/jobs/" + encodeURIComponent(jobId) + "/detect");
    } catch (err) {
      return;
    }
    await reload();
  }
  const per = perFont(fontId);
  if (!per) {
    notice("this entry offers no route: " + what + " not applied");
    return;
  }
  mutate(per);
  markDirty();
  buildFonts();                                       // the panel shows the value; save() reads the panels back
  if (!readBatch() || !readPerOptions()) return;
  try {
    await api("PUT", "/api/jobs/" + encodeURIComponent(jobId) + "/settings", settings);
  } catch (err) {
    return;
  }
  await reload();
  await renderJobs();
  notice(what + " saved; the job is open for editing again: run it to build with it");
}

function redrawPreviews() {
  for (const redraw of sourceRedraws) redraw();
  for (const {redraw} of stepRows.values()) if (redraw) redraw();
}

// The glyph grid of a step's face: 16 a row at pitch cell_w + 2, 256 a page; a click shows the glyph's metrics and,
// for a jamo face's composed code point, its pieces.
function glyphGrid(step, chainBytes) {
  const box = el("div", {class: "glyph-grid", hidden: true});
  const info = el("div", {class: "sub"});
  const nav = el("div", {});
  const holder = el("div", {});
  box.append(nav, holder, info);
  let page = 0, syllableView = false, list = [], token = 0;

  // Only the latest show() renders: a second click while the first is still drawing must not append a second set.
  const show = async () => {
    const mine = ++token;
    holder.innerHTML = "";
    try {
      const [face] = await chainBytes();
      await withChain([face], async (infos) => {
        svfview.setScale(1, 1);
        list = (syllableView ? svfview.syllables(0) : svfview.codePoints(0)).filter(svfview.isCodePoint);
        const pitch = infos[0].cellW + 2;
        const pageList = list.slice(page * 256, page * 256 + 256);
        const rows = [];
        for (let row = 0; row < pageList.length; row += 16) {
          const cps = pageList.slice(row, row + 16);
          const canvas = el("canvas", {class: "grid-row"});
          svfview.drawGlyphs(canvas, cps.map((cp) => String.fromCodePoint(cp)).join(""),
            {pitch, target: "gray8"});
          canvas.style.imageRendering = "pixelated";
          canvas.style.width = canvas.width * 2 + "px";
          canvas.onclick = async (event) => {
            const col = Math.floor((event.offsetX / (canvas.clientWidth / canvas.width) - 1) / pitch);
            const cp = cps[col];
            if (cp === undefined) return;
            await withChain([face], () => {
              const m = svfview.metrics(0, cp);
              const pieces = svfview.pieces(0, cp);
              info.textContent = "U+" + cp.toString(16).toUpperCase().padStart(4, "0") + " advance " + m.advance +
                " bearing " + m.bearing + " ink " + m.inkW + " dy " + m.dy + (pieces.length ? " pieces " + pieces.join(" ") : "");
            });
          };
          rows.push(canvas);
        }
        if (mine !== token) return;                         // a newer show() is (or was) drawing: leave the page to it
        holder.replaceChildren(...rows);
        nav.innerHTML = "";
        const pages = Math.max(1, Math.ceil(list.length / 256));
        const prev = el("button", {type: "button", text: "<"});
        prev.disabled = page === 0;
        prev.onclick = () => { page--; show(); };
        const next = el("button", {type: "button", text: ">"});
        next.disabled = page + 1 >= pages;
        next.onclick = () => { page++; show(); };
        nav.append(prev, " " + (page + 1) + "/" + pages + " ", next);
        if (infos[0].jamo) {
          const view = el("button", {type: "button", text: syllableView ? "glyphs" : "syllables"});
          view.onclick = () => { syllableView = !syllableView; page = 0; show(); };
          nav.append(" ", view);
        }
      });
    } catch (err) {
      if (mine === token) info.textContent = escapeControls(err && err.message);
    }
  };
  return {box, show};
}

// ---- the steps table ------------------------------------------------------------------------------------------

// The one line a step row shows for its mkfont report (spec 8.2): clip "cut N (T top, B bottom)" (", G dropped" when the
// cell removes a glyph whole), nudge "nudged N", fit "fit at S px".
function reportText(report) {
  const n = (value) => Number(value || 0).toLocaleString("en");
  const counts = report.counts || {};
  if (report.mode === "clip") {
    return "cut " + n(counts.cut) + " (" + n(counts.top) + " top, " + n(counts.bottom) + " bottom)" +
      (counts.gone ? ", " + n(counts.gone) + " dropped" : "");
  }
  if (report.mode === "fit") return "fit at " + n(report.size) + " px";
  return "nudged " + n((report.nudged || []).length);
}

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
  if (step.kind === "source") {                       // the font's own conversion: no size, bpp or face name
    tr.append(el("td", {}, bdi("source")), el("td", {class: "nums"}), el("td", {class: "nums"}),
      el("td", {class: "nums"}));
  } else {
    tr.append(el("td", {}, bdi(step.kind || "")));
    tr.append(el("td", {class: "nums", text: step.size === null || step.size === undefined ? "" : String(step.size)}));
    tr.append(el("td", {class: "nums", text: step.bpp === null || step.bpp === undefined ? "" : String(step.bpp)}));
    tr.append(el("td", {class: "nums", text: escapeControls(step.name || "")}));
  }

  const state = el("td", {});
  state.append(el("span", {text: escapeControls(step.state || "")}));
  if (step.error) state.append(el("div", {class: "sub", text: escapeControls(step.error)}));
  if (step.identical_to) state.append(el("div", {class: "sub", text: "identical to " + escapeControls(step.identical_to)}));
  if (job && step.state === "done" && step.report) {
    const line = el("div", {class: "sub", dataset: {report: step.id}});
    state.append(line);
    fetch("/api/jobs/" + encodeURIComponent(job.id) + "/report/" + encodeURIComponent(step.id) + ".json",
          {cache: "no-cache"})
      .then((response) => (response.ok ? response.json() : null))
      .then((report) => { if (report) line.textContent = reportText(report); })
      .catch(() => {});
  }
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
  let redraw = null;
  if (job && step.state === "done" && (step.kind === "precomposed" || step.kind === "jamo")) {
    const cell = previewCell(step);
    result.append(cell.node);
    redraw = cell.redraw;
  }
  tr.append(result);
  return {tr, redraw};
}

// The steps table is updated, not rebuilt: a step whose row would come out the same keeps its DOM (the sample text
// being typed, the glyph grid, the ascent to try) while the job polls; only a changed step gets a new row.
let stepsJob = null;

function buildSteps() {
  if (!job || !(job.steps || []).length) {
    stepsEl.innerHTML = "";
    stepRows.clear();
    stepsJob = null;
    return;
  }
  if (stepsJob !== job.id || !stepsEl.querySelector("tbody")) {
    stepsEl.innerHTML = "";
    stepRows.clear();
    stepsJob = job.id;
    stepsEl.append(el("thead", {}, el("tr", {},
      ...["id", "font", "kind", "size", "bpp", "name", "state", "seconds", "quality", "stderr", "result"]
        .map((title) => el("th", {text: title})))), el("tbody"));
  }
  const body = stepsEl.querySelector("tbody");
  const seen = new Set();
  const rows = [];
  for (const step of job.steps) {
    seen.add(step.id);
    const sig = stepSig(step, companionStep(step)) + "|" + JSON.stringify((job.fonts || []).filter((f) => f.id === step.font).map((f) => f.source_kind));
    const old = stepRows.get(step.id);
    if (old && old.sig === sig) {
      rows.push(old.tr);
      continue;
    }
    const made = stepRow(step);
    stepRows.set(step.id, {sig, tr: made.tr, redraw: made.redraw});
    rows.push(made.tr);
  }
  for (const id of [...stepRows.keys()]) if (!seen.has(id)) stepRows.delete(id);
  body.replaceChildren(...rows);
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
  if (job.source === "local") restoreSources(job);
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
  const id = jobId;
  try {
    await api("POST", "/api/jobs/" + encodeURIComponent(id) + "/run", undefined,
              {runGen, onWait: (kind, epoch) => { if (kind === "preparing") followOtherRun(id, epoch); }});
  } catch (err) {
    if (err && err.body && err.body.stale === true) await reload();   // the settings changed under the run: show them
    return;
  }
  await reload();
  startPolling();
  await renderJobs();
}

// "A run of this job is being prepared" (another tab or window): follow that run instead of repeating ours. Every
// `followMs` (1 s), for up to 15 s, read the job; when its state leaves `detected` show it (polling while it runs),
// drop the "Try again" control and end every retry of the superseded request (`runGen`). The loop belongs to the action
// that started it (@p epoch): a user action (a public notice / clearNotice) or another open job ends it without touching
// the newer action's control or notice. One loop per action, also across "Try again".
let follow = null;
async function followOtherRun(id, epoch) {
  if (follow && follow.id === id && follow.epoch === epoch) return;
  const mine = follow = {id, epoch};
  const still = () => follow === mine && jobId === id && noticeEpoch === epoch;
  const bounds = busyBounds();
  const end = bounds.now() + bounds.totalMs;
  try {
    while (bounds.now() < end) {
      await bounds.sleep(bounds.followMs);
      if (!still()) return;
      let other = null;
      try {
        const response = await fetch("/api/jobs/" + encodeURIComponent(id));
        if (response.ok) other = await response.json();
      } catch (err) { /* no answer: look again */ }
      if (!still()) return;                           // a late answer must not render another job or wipe a newer notice
      if (other && other.state !== "detected") {
        runGen++;                                     // the run request (and its Try again) is superseded
        job = other;
        if (!dirty) settings = clone(job.settings || {batch: {}, fonts: {}});   // unsaved edits stay, as in poll()
        dropBusyWait();
        setNoticeQuiet("");
        renderAll();
        if (job.state === "queued" || job.state === "running") startPolling();
        await renderJobs();
        return;
      }
    }
  } finally {
    if (follow === mine) follow = null;
  }
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

// ---- local mode: the sources panel, the shell bridge, the acknowledgement ------------------------------------------

// The Electron shell's preload exposes `window.svfMaker` (pickFiles, pickFolder, pickOutputDir, openOutputFolder). Without
// it the page takes typed paths. The bridge is read when it is used, never cached.
function bridge() { return typeof window !== "undefined" && window.svfMaker ? window.svfMaker : null; }
function bridgeCan(name) { const b = bridge(); return !!b && typeof b[name] === "function"; }

function renderSources() {
  uploadPanelEl.hidden = state.local;
  sourcesPanelEl.hidden = !state.local;
  if (!state.local) return;
  const shell = bridge() !== null;
  chooseFilesEl.hidden = !shell;
  chooseFolderEl.hidden = !shell;
  chooseOutputEl.hidden = !shell;
  sourcePathsLabelEl.hidden = shell;                  // the typed fields exist only when there is no bridge
  outputDirLabelEl.hidden = shell;
  rootsEl.innerHTML = "";
  for (const path of state.roots) rootsEl.append(el("li", {}, bdi(path)));
  rootsEl.hidden = !shell;
  outputShownEl.textContent = shell ? escapeControls(state.output) : "";
}

function addRoots(picked) {
  if (!Array.isArray(picked)) return;                 // null: the dialog was cancelled
  let added = false;
  for (const path of picked) {
    if (typeof path === "string" && path && !state.roots.includes(path)) { state.roots.push(path); added = true; }
  }
  if (added) renderSources();
}

// The sources panel shows the job that is open: its roots and its output folder as the server holds them.
function restoreSources(j) {
  state.roots = (j.roots || []).map((item) => item.path);
  state.output = j.output_dir || "";
  sourcePathsEl.value = state.roots.join("\n");
  outputDirEl.value = state.output;
  renderSources();
}

async function deleteJob() {
  clearNotice();
  if (!jobId) return;
  try {
    await api("DELETE", "/api/jobs/" + encodeURIComponent(jobId));
  } catch (err) { return; }
  stopPolling();
  job = null;
  jobId = null;
  settings = {batch: {}, fonts: {}};
  history.replaceState(null, "", location.pathname);
  renderAll();
  await renderJobs();
}

async function chooseRoots(which) {
  const b = bridge();
  if (!b || typeof b[which] !== "function") return;
  try { addRoots(await b[which]()); } catch (err) { notice(String(err)); }
}

async function chooseOutput() {
  const b = bridge();
  if (!b || typeof b.pickOutputDir !== "function") return;
  try {
    const picked = await b.pickOutputDir();
    if (typeof picked === "string" && picked) { state.output = picked; renderSources(); }
  } catch (err) { notice(String(err)); }
}

// The one-time notice before the first local job of a page session: converting is the user's responsibility. It is
// remembered for the page session (and the tab, in sessionStorage), never on the server.
function acknowledged() {
  if (state.acknowledged) return true;
  try { return window.sessionStorage.getItem(ACK_KEY) === "1"; } catch (err) { return false; }
}

function acknowledge() {
  if (acknowledged()) return Promise.resolve();
  return new Promise((resolve) => {
    ackEl.hidden = false;
    ackOkEl.focus();
    ackOkEl.onclick = () => {
      state.acknowledged = true;
      try { window.sessionStorage.setItem(ACK_KEY, "1"); } catch (err) { /* no storage: the page session still counts */ }
      ackEl.hidden = true;
      resolve();
    };
  });
}

async function detectLocal() {
  clearNotice();
  const shell = bridge() !== null;
  const paths = shell ? state.roots.slice() : sourcePathsEl.value.split("\n").map((line) => line.trim()).filter(Boolean);
  const output = shell ? state.output : outputDirEl.value.trim();
  if (!paths.length) { notice("choose files or a folder first"); return; }
  if (!output) { notice("choose an output folder"); return; }
  await acknowledge();                                // nothing is created before the user has read it
  const idle = job && job.state !== "queued" && job.state !== "running" && job.source === "local";
  let created;
  try {
    // the open job is offered for reuse: the server decides by the folder's real path and identity, not by the
    // spelling (a trailing slash or a symlinked parent is the same folder), so a folder never gets a second job
    created = await api("POST", "/api/jobs", idle ? {source: "local", output_dir: output, reuse: jobId}
                                                  : {source: "local", output_dir: output});
  } catch (err) { return; }                           // e.g. "output folder is in use by job ...": the notice says so
  if (created.reused !== true) {
    jobId = created.id;
    job = {id: jobId, state: "uploading", source: "local"};
    settings = {batch: {}, fonts: {}};
    renderStatus();
    history.replaceState(null, "", "?job=" + jobId);
  }
  // the open job stays when it is for this folder (it owns the faces it wrote there and keeps its log); the sources
  // PUT is also accepted on a done or failed job, which goes back to `uploading` with its `owned` record kept
  let answer;
  try {
    answer = await api("PUT", "/api/jobs/" + encodeURIComponent(jobId) + "/sources", {paths});
  } catch (err) { return; }
  renderRefused((answer.refused || []).map((item) => item.path + ": " + item.reason));
  try {
    await api("POST", "/api/jobs/" + encodeURIComponent(jobId) + "/detect");
  } catch (err) { return; }
  await reload();                                    // the job's `upload.refused` carries the same lines
  await renderJobs();
}

function wire() {
  settingsEl.addEventListener("submit", (event) => event.preventDefault());
  chooseFilesEl.onclick = () => chooseRoots("pickFiles");
  chooseFolderEl.onclick = () => chooseRoots("pickFolder");
  chooseOutputEl.onclick = chooseOutput;
  detectLocalEl.onclick = detectLocal;
  deleteJobEl.onclick = deleteJob;
  noticeRetryEl.onclick = tryAgain;
  openFolderEl.onclick = async () => {
    const b = bridge();
    if (b && typeof b.openOutputFolder === "function") {
      try { await b.openOutputFolder(); } catch (err) { notice(String(err)); }   // no argument: the shell opens the output
    }
  };
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
  try {
    state.local = (await api("GET", "/api/caps")).local === true;
  } catch (err) {
    state.local = false;
  }
  renderSources();
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
