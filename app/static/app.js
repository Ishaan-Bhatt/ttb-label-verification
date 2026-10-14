"use strict";

const FIELDS = ["brand_name", "class_type", "alcohol_content", "net_contents", "bottler", "country_of_origin"];
const BATCH_CONCURRENCY = 4;
const REQUEST_TIMEOUT_MS = 30000;

const STATUS_TEXT = {
  match: "✓ Match",
  review: "⚠ Review",
  mismatch: "✗ Mismatch",
  not_checked: "– Not checked",
};
const VERDICT_TEXT = {
  pass: "✓ Passed",
  review: "⚠ Needs review",
  fail: "✗ Problems found",
  error: "! Couldn't check",
};
const VERDICT_ICON = { pass: "✅", review: "⚠️", fail: "❌" };

const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function badge(status, text) {
  return `<span class="badge ${esc(status)}">${esc(text ?? STATUS_TEXT[status] ?? status)}</span>`;
}

// ---------------------------------------------------------------- API

async function verifyLabel(file, application) {
  const body = new FormData();
  body.append("image", file, file.name);
  for (const key of FIELDS) body.append(key, application[key] || "");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let response;
  try {
    response = await fetch("/api/verify", { method: "POST", body, signal: controller.signal });
  } catch (err) {
    if (err.name === "AbortError") throw new Error("The check took too long. Please try again.");
    throw new Error("Couldn't reach the server. Check your connection and try again.");
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) {
    let message = `Something went wrong (error ${response.status}). Please try again.`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
    } catch (_) { /* keep the generic message */ }
    throw new Error(message);
  }
  return response.json();
}

// ---------------------------------------------------------------- CSV

function parseCsv(text) {
  text = text.replace(/^﻿/, "");
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); rows.push(row); row = []; field = "";
    } else field += c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }

  const nonEmpty = rows.filter((r) => r.some((v) => v.trim()));
  if (!nonEmpty.length) return [];
  const headers = nonEmpty[0].map((h) => h.trim().toLowerCase().replace(/[\s/]+/g, "_"));
  return nonEmpty.slice(1).map((r) => Object.fromEntries(headers.map((h, i) => [h, (r[i] || "").trim()])));
}

function rowFilename(row) {
  return (row.filename || row.file || row.image || row.file_name || "").trim();
}

function toCsv(rows) {
  const cell = (v) => {
    const s = String(v ?? "");
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return rows.map((r) => r.map(cell).join(",")).join("\r\n");
}

// ---------------------------------------------------------------- Result rendering

function renderResult(result, imageUrl) {
  const checksRows = result.fields.map((c) => `
    <tr class="row-${esc(c.status)}">
      <td class="name">${esc(c.label)}</td>
      <td class="value" data-label="Application">${c.expected ? esc(c.expected) : '<span class="missing">—</span>'}</td>
      <td class="value" data-label="Label">${c.found ? esc(c.found) : '<span class="missing">—</span>'}</td>
      <td>${badge(c.status)}<div class="msg">${esc(c.message)}</div></td>
    </tr>`).join("");

  const w = result.warning;
  const sub = w.checks.map((c) => `<li>${badge(c.status)}<div><strong>${esc(c.label)}</strong><br>${esc(c.message)}</div></li>`).join("");
  const diffs = w.differences.length ? `
    <div class="diffs">
      <h4>Differences from the required wording</h4>
      <table>
        <tr><th>Required</th><th>On the label</th></tr>
        ${w.differences.map((d) => `<tr>
          <td>${d.expected ? `<del class="req">${esc(d.expected)}</del>` : '<span class="missing">(nothing)</span>'}</td>
          <td>${d.found ? `<ins class="got">${esc(d.found)}</ins>` : '<span class="missing">(missing)</span>'}</td>
        </tr>`).join("")}
      </table>
    </div>` : "";

  return `
    <div class="verdict ${esc(result.verdict)}" role="status">
      <span class="verdict-icon" aria-hidden="true">${VERDICT_ICON[result.verdict] || ""}</span>
      <div><h2>${esc(result.headline)}</h2>
      <p>${result.verdict === "pass" ? "No action needed." : "See the items marked below."}</p></div>
    </div>
    <div class="result-grid">
      ${imageUrl ? `<div class="result-image"><img src="${esc(imageUrl)}" alt="The label that was checked"></div>` : ""}
      <div>
        <div class="card">
          <table class="checks">
            <thead><tr><th>Item</th><th>Application says</th><th>Label says</th><th>Result</th></tr></thead>
            <tbody>${checksRows}</tbody>
          </table>
        </div>
        <div class="card warning-box">
          <h3>Government warning ${badge(w.status)}</h3>
          <p>${esc(w.message)}</p>
          <ul class="subchecks">${sub}</ul>
          ${diffs}
        </div>
        <details>
          <summary>Show all text read from the label</summary>
          <div class="ocr-text">${esc(result.ocr_text)}</div>
        </details>
        <p class="timing">Checked in ${(result.elapsed_ms / 1000).toFixed(1)} seconds.</p>
      </div>
    </div>`;
}

// ---------------------------------------------------------------- Tabs

function selectTab(name) {
  for (const t of ["single", "batch"]) {
    const on = t === name;
    $(`tab-${t}`).setAttribute("aria-selected", on);
    $(`panel-${t}`).hidden = !on;
  }
}
$("tab-single").addEventListener("click", () => selectTab("single"));
$("tab-batch").addEventListener("click", () => selectTab("batch"));

// ---------------------------------------------------------------- Single label

let singleFile = null;
let singlePreviewUrl = null;

function setSingleFile(file) {
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    showSingleError("That file isn't an image. Please choose a JPG or PNG of the label.");
    return;
  }
  singleFile = file;
  if (singlePreviewUrl) URL.revokeObjectURL(singlePreviewUrl);
  singlePreviewUrl = URL.createObjectURL(file);
  $("image-preview").src = singlePreviewUrl;
  $("image-preview").hidden = false;
  $("dropzone-text").hidden = true;
  $("image-name").textContent = `${file.name} (click the image to choose a different one)`;
  showSingleError(null);
}

function showSingleError(message) {
  $("single-error").hidden = !message;
  $("single-error").textContent = message || "";
}

$("image-input").addEventListener("change", (e) => setSingleFile(e.target.files[0]));

const dropzone = $("dropzone");
dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragging"); });
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragging"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragging");
  setSingleFile(e.dataTransfer.files[0]);
});

$("single-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!singleFile) {
    showSingleError("Please choose a label image first (step 1).");
    return;
  }
  showSingleError(null);
  const application = Object.fromEntries(FIELDS.map((k) => [k, $(k).value]));
  const out = $("single-result");
  const btn = $("check-btn");
  btn.disabled = true;
  btn.textContent = "Checking…";
  out.innerHTML = '<div class="card loading"><div class="spinner" aria-hidden="true"></div>Reading the label…</div>';
  out.scrollIntoView({ behavior: "smooth", block: "start" });
  try {
    const result = await verifyLabel(singleFile, application);
    out.innerHTML = renderResult(result, singlePreviewUrl);
  } catch (err) {
    out.innerHTML = "";
    showSingleError(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Check label";
  }
});

$("clear-btn").addEventListener("click", () => {
  $("single-form").reset();
  singleFile = null;
  $("image-preview").hidden = true;
  $("dropzone-text").hidden = false;
  $("image-name").textContent = "";
  $("single-result").innerHTML = "";
  showSingleError(null);
});

// ---------------------------------------------------------------- Examples

let sampleRows = [];

async function loadSamples() {
  try {
    const res = await fetch("/samples/applications.csv");
    if (!res.ok) return;
    sampleRows = parseCsv(await res.text());
    const select = $("example-select");
    for (const row of sampleRows) {
      const opt = document.createElement("option");
      opt.value = row.filename;
      opt.textContent = row.notes ? `${row.filename} — ${row.notes}` : row.filename;
      select.appendChild(opt);
    }
  } catch (_) {
    $("example-select").closest(".examples").hidden = true;
  }
}

async function fetchSampleFile(name) {
  const res = await fetch(`/samples/${encodeURIComponent(name)}`);
  if (!res.ok) throw new Error(`Couldn't load example ${name}.`);
  const blob = await res.blob();
  return new File([blob], name, { type: blob.type });
}

$("example-select").addEventListener("change", async (e) => {
  const row = sampleRows.find((r) => r.filename === e.target.value);
  if (!row) return;
  try {
    setSingleFile(await fetchSampleFile(row.filename));
    for (const k of FIELDS) $(k).value = row[k] || "";
    $("single-result").innerHTML = "";
  } catch (err) {
    showSingleError(err.message);
  }
});

loadSamples();

// ---------------------------------------------------------------- Batch

let batchImages = [];
let batchRows = null;
let batchResults = [];
let batchCancelled = false;
let batchFilter = "all";

function showBatchError(message) {
  $("batch-error").hidden = !message;
  $("batch-error").textContent = message || "";
}

$("batch-images").addEventListener("change", (e) => {
  batchImages = [...e.target.files].filter((f) => f.type.startsWith("image/"));
  const skipped = e.target.files.length - batchImages.length;
  $("batch-images-summary").textContent =
    `${batchImages.length} image${batchImages.length === 1 ? "" : "s"} selected` +
    (skipped ? ` (${skipped} non-image file${skipped === 1 ? "" : "s"} ignored).` : ".");
  showBatchError(null);
});

$("batch-csv").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const rows = parseCsv(await file.text());
  if (!rows.length || !rowFilename(rows[0])) {
    batchRows = null;
    showBatchError('That spreadsheet needs a "filename" column with one row per label. Download the template to see the layout.');
    return;
  }
  batchRows = rows;
  $("batch-csv-summary").textContent = `${file.name}: ${rows.length} application row${rows.length === 1 ? "" : "s"}.`;
  showBatchError(null);
});

$("batch-start").addEventListener("click", () => {
  if (!batchImages.length) return showBatchError("Please choose the label images first (step 1).");
  if (!batchRows) return showBatchError("Please choose the spreadsheet of application details (step 2).");
  runBatch(batchImages, batchRows);
});

$("batch-sample").addEventListener("click", async () => {
  const btn = $("batch-sample");
  btn.disabled = true;
  try {
    if (!sampleRows.length) await loadSamples();
    const files = await Promise.all(sampleRows.map((r) => fetchSampleFile(r.filename)));
    runBatch(files, sampleRows);
  } catch (err) {
    showBatchError(err.message);
  } finally {
    btn.disabled = false;
  }
});

$("batch-cancel").addEventListener("click", () => { batchCancelled = true; });

async function runBatch(images, rows) {
  showBatchError(null);
  const byName = new Map(rows.map((r) => [rowFilename(r).toLowerCase(), r]));
  const imageNames = new Set(images.map((f) => f.name.toLowerCase()));
  const unmatchedRows = rows.filter((r) => !imageNames.has(rowFilename(r).toLowerCase())).length;

  batchResults = images.map((file) => ({
    file,
    application: byName.get(file.name.toLowerCase()) || null,
    result: null,
    error: null,
    state: "waiting",
  }));
  batchCancelled = false;
  batchFilter = "all";
  document.querySelectorAll(".filter").forEach((b) => b.setAttribute("aria-pressed", b.dataset.filter === "all"));

  $("batch-progress").hidden = false;
  $("batch-cancel").hidden = false;
  $("batch-results").hidden = false;
  $("batch-start").disabled = true;
  $("batch-sample").disabled = true;
  renderBatchList();

  const started = performance.now();
  let next = 0, done = 0;
  const updateProgress = () => {
    const pct = Math.round((done / batchResults.length) * 100);
    $("progress-fill").style.width = `${pct}%`;
    document.querySelector(".progress-bar").setAttribute("aria-valuenow", pct);
    $("progress-text").textContent = `Checked ${done} of ${batchResults.length} labels`;
    renderBatchSummary(unmatchedRows);
  };
  updateProgress();

  async function worker() {
    while (!batchCancelled && next < batchResults.length) {
      const item = batchResults[next++];
      item.state = "running";
      try {
        item.result = await verifyLabel(item.file, item.application || {});
      } catch (err) {
        item.error = err.message;
      }
      item.state = "done";
      done++;
      updateProgress();
      updateBatchItem(batchResults.indexOf(item));
    }
  }
  await Promise.all(Array.from({ length: BATCH_CONCURRENCY }, worker));

  const seconds = ((performance.now() - started) / 1000).toFixed(1);
  $("progress-text").textContent = batchCancelled
    ? `Stopped after ${done} of ${batchResults.length} labels.`
    : `Finished: ${done} labels in ${seconds} seconds.`;
  $("batch-cancel").hidden = true;
  $("batch-start").disabled = false;
  $("batch-sample").disabled = false;
}

function itemVerdict(item) {
  if (item.error) return "error";
  return item.result ? item.result.verdict : "waiting";
}

function itemSummary(item) {
  if (item.state === "waiting") return "Waiting…";
  if (item.state === "running") return "Checking…";
  if (item.error) return item.error;
  const note = item.application ? "" : " (No spreadsheet row for this file, so only the government warning was checked.)";
  const issues = resultIssues(item.result);
  if (!issues.length) return item.result.headline + note;
  const more = issues.length > 1 ? ` (+${issues.length - 1} more)` : "";
  return issues[0] + more + note;
}

// One line per failing or doubtful check, worst first, e.g. "Alcohol content: Label shows 40%...".
function resultIssues(result) {
  const all = [
    ...result.fields.map((c) => ({ status: c.status, text: `${c.label}: ${c.message}` })),
    ...result.warning.checks.map((c) => ({ status: c.status, text: `Government warning: ${c.message}` })),
  ];
  return [
    ...all.filter((i) => i.status === "mismatch"),
    ...all.filter((i) => i.status === "review"),
  ].map((i) => i.text);
}

function renderBatchSummary(unmatchedRows) {
  const counts = { pass: 0, review: 0, fail: 0, error: 0 };
  for (const item of batchResults) {
    const v = itemVerdict(item);
    if (v in counts) counts[v]++;
  }
  $("batch-summary").innerHTML = `
    <div class="stat pass"><span class="num">${counts.pass}</span>Passed</div>
    <div class="stat review"><span class="num">${counts.review}</span>Need review</div>
    <div class="stat fail"><span class="num">${counts.fail}</span>Problems found</div>
    ${counts.error ? `<div class="stat"><span class="num">${counts.error}</span>Couldn't check</div>` : ""}
    ${unmatchedRows ? `<div class="stat"><span class="num">${unmatchedRows}</span>Spreadsheet rows with no image</div>` : ""}`;
}

function batchItemHtml(item, index) {
  const v = itemVerdict(item);
  const statusBadge = v === "waiting" ? badge("not_checked", "…") : badge(v, VERDICT_TEXT[v]);
  return `
    <button type="button" aria-expanded="false" data-index="${index}" ${item.state !== "done" || item.error ? "disabled" : ""}>
      ${statusBadge}
      <span class="file">${esc(item.file.name)}</span>
      <span class="summary">${esc(itemSummary(item))}</span>
      <span class="chev" aria-hidden="true">${item.result ? "▶" : ""}</span>
    </button>
    <div class="batch-detail" hidden></div>`;
}

function renderBatchList() {
  const list = $("batch-list");
  list.innerHTML = "";
  batchResults.forEach((item, i) => {
    const li = document.createElement("li");
    li.className = "batch-item";
    li.id = `batch-item-${i}`;
    li.innerHTML = batchItemHtml(item, i);
    list.appendChild(li);
  });
  applyFilter();
}

function updateBatchItem(index) {
  const li = $(`batch-item-${index}`);
  if (!li) return;
  li.classList.remove("open");
  li.innerHTML = batchItemHtml(batchResults[index], index);
  applyFilter();
}

function applyFilter() {
  batchResults.forEach((item, i) => {
    const li = $(`batch-item-${i}`);
    const v = itemVerdict(item);
    li.hidden = batchFilter !== "all" && !(v === batchFilter || (batchFilter === "fail" && v === "error"));
  });
}

$("batch-list").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-index]");
  if (!btn) return;
  const item = batchResults[Number(btn.dataset.index)];
  const li = btn.parentElement;
  const detail = li.querySelector(".batch-detail");
  const open = !li.classList.contains("open");
  li.classList.toggle("open", open);
  btn.setAttribute("aria-expanded", open);
  detail.hidden = !open;
  if (open && !detail.innerHTML) {
    item.previewUrl = item.previewUrl || URL.createObjectURL(item.file);
    detail.innerHTML = renderResult(item.result, item.previewUrl);
  }
});

document.querySelectorAll(".filter").forEach((b) => b.addEventListener("click", () => {
  batchFilter = b.dataset.filter;
  document.querySelectorAll(".filter").forEach((x) => x.setAttribute("aria-pressed", x === b));
  applyFilter();
}));

$("batch-download").addEventListener("click", () => {
  const header = ["filename", "result", "summary"];
  for (const key of FIELDS) header.push(`${key}_result`, `${key}_note`);
  header.push("government_warning_result", "government_warning_note");

  const rows = [header];
  for (const item of batchResults) {
    const r = item.result;
    const row = [item.file.name, item.error ? "error" : r ? r.verdict : "not checked", itemSummary(item)];
    for (const key of FIELDS) {
      const c = r?.fields.find((f) => f.key === key);
      row.push(c ? c.status : "", c ? c.message : "");
    }
    row.push(r ? r.warning.status : "", r ? r.warning.message : "");
    rows.push(row);
  }
  const blob = new Blob([toCsv(rows)], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "label-check-results.csv";
  a.click();
  URL.revokeObjectURL(a.href);
});
