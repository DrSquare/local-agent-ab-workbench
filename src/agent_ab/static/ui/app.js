const state = {
  experiments: [],
  taskpacks: [],
  runs: [],
  views: [],
  selectedRun: null,
  selectedTrace: null,
};

const $ = (selector) => document.querySelector(selector);

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `${response.status} ${response.statusText}`);
  }
  return payload;
}

function setApiStatus(ok, message) {
  $("#apiDot").classList.toggle("is-ok", ok);
  $("#apiStatus").textContent = message;
}

function activateView(name) {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === name);
  });
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("is-active", section.id === `view-${name}`);
  });
}

async function loadAll() {
  setApiStatus(false, "Loading");
  const [health, experiments, taskpacks, runs, views] = await Promise.all([
    fetchJson("/health"),
    fetchJson("/experiments"),
    fetchJson("/taskpacks"),
    fetchJson("/runs"),
    fetchJson("/playground/views"),
  ]);

  state.experiments = experiments.experiments || [];
  state.taskpacks = taskpacks.taskpacks || [];
  state.runs = runs.runs || [];
  state.views = views.views || [];
  renderAll();
  setApiStatus(true, health.status || "Ready");
  $("#lastLoaded").textContent = new Date().toLocaleTimeString();
}

function renderAll() {
  $("#experimentCount").textContent = state.experiments.length;
  $("#taskpackCount").textContent = state.taskpacks.length;
  $("#runCount").textContent = state.runs.length;
  renderExperiments();
  renderTaskpacks();
  renderRuns();
  renderViews();
  renderTrace();
}

function renderExperiments() {
  const rows = state.experiments.map((experiment) => `
    <tr>
      <td>${escapeHtml(experiment.name || experiment.path)}</td>
      <td>${escapeHtml((experiment.agents || []).join(", ") || "-")}</td>
      <td>${escapeHtml(experiment.taskpack || "-")}</td>
      <td>${badge(experiment.valid ? "valid" : "invalid", experiment.valid ? "ok" : "error")}</td>
    </tr>
  `);
  $("#experimentRows").innerHTML = rows.join("") || emptyRow("No experiments found", 4);
}

function renderTaskpacks() {
  $("#taskpackList").innerHTML = state.taskpacks.map((pack) => `
    <div class="list-item">
      <strong>${escapeHtml(pack.id || pack.path)}</strong>
      <span>${pack.task_count || 0} tasks, version ${pack.version || "-"}</span>
      <span>${escapeHtml((pack.tasks || []).map((task) => task.id).join(", ") || "No tasks")}</span>
    </div>
  `).join("") || `<div class="empty">No TaskPacks found</div>`;
}

function renderRuns() {
  $("#runRows").innerHTML = state.runs.map((run) => `
    <tr class="run-row" data-run-id="${escapeAttribute(run.run_id)}" tabindex="0">
      <td>${escapeHtml(run.run_id)}</td>
      <td>${escapeHtml(run.task_id || "-")}</td>
      <td>${escapeHtml(run.variant_id || "-")}</td>
      <td>${escapeHtml(run.trace_id || "-")}</td>
      <td>${artifactSummary(run.artifacts || [])}</td>
    </tr>
  `).join("") || emptyRow("No runs found", 5);
}

function renderViews() {
  $("#viewList").innerHTML = state.views.map((view) => `
    <div class="list-item">
      <strong>${escapeHtml(view.label || view.id)}</strong>
      <span>${escapeHtml(view.task_id)} via ${escapeHtml(view.variant_id)}</span>
      <span>${escapeHtml(view.run_id)}</span>
    </div>
  `).join("") || `<div class="empty">No saved views</div>`;
}

function renderTrace() {
  const run = state.selectedRun;
  const trace = state.selectedTrace;
  $("#selectedRunLabel").textContent = run ? run.run_id : "No run selected";

  if (!run) {
    $("#traceTree").innerHTML = `<div class="empty">Select a run to load its trace</div>`;
    $("#traceDetails").innerHTML = "";
    return;
  }

  $("#traceDetails").innerHTML = detailRows({
    Run: run.run_id,
    Task: run.task_id || "-",
    Variant: run.variant_id || "-",
    Trace: run.trace_id || "-",
    Artifacts: artifactSummary(run.artifacts || [], false),
  });

  if (!trace) {
    $("#traceTree").innerHTML = `<div class="empty">Trace data is not loaded</div>`;
    return;
  }

  const spans = trace.spans || [];
  const children = groupByParent(spans);
  const root = spans.find((span) => !span.parent_span_id);
  $("#traceTree").innerHTML = root ? renderSpan(root, children, 0) : `<div class="empty">Trace has no root span</div>`;
}

async function selectRun(runId) {
  const run = state.runs.find((item) => item.run_id === runId);
  state.selectedRun = run || null;
  state.selectedTrace = null;
  activateView("trace");
  renderTrace();
  if (!run) return;

  try {
    const tracePayload = await fetchJson(`/runs/${encodeURIComponent(run.run_id)}/trace`);
    state.selectedTrace = (tracePayload.traces || [])[0] || null;
    renderTrace();
  } catch (error) {
    $("#traceTree").innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function submitPlayground(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = {
    experiment_path: form.experiment_path.value.trim(),
    variant_id: form.variant_id.value.trim(),
    task_id: form.task_id.value.trim(),
    run_id: optionalValue(form.run_id.value),
    save_view: $("#pgSaveView").checked,
    view_id: optionalValue(form.view_id.value),
    label: "UI replay",
    overrides: {},
  };

  $("#playgroundStatus").textContent = "Running replay";
  try {
    const result = await fetchJson("/playground/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("#playgroundStatus").textContent = `${result.status}: ${result.run_id}`;
    await loadAll();
    await selectRun(result.run_id);
  } catch (error) {
    $("#playgroundStatus").textContent = error.message;
  }
}

function groupByParent(spans) {
  return spans.reduce((grouped, span) => {
    const key = span.parent_span_id || "";
    grouped[key] = grouped[key] || [];
    grouped[key].push(span);
    return grouped;
  }, {});
}

function renderSpan(span, children, depth) {
  const childNodes = children[span.span_id] || [];
  const indent = `${depth * 18}px`;
  return `
    <div class="span-node" data-kind="${escapeAttribute(span.kind)}" style="margin-left: ${indent}">
      <span>${escapeHtml(span.kind)}</span>
      <strong>${escapeHtml(span.name)}</strong>
      <span>${span.duration_ms ?? "-"} ms</span>
    </div>
    ${childNodes.map((child) => renderSpan(child, children, depth + 1)).join("")}
  `;
}

function detailRows(details) {
  return Object.entries(details).map(([key, value]) => `
    <dt>${escapeHtml(key)}</dt>
    <dd>${value}</dd>
  `).join("");
}

function artifactSummary(artifacts, useBadges = true) {
  const names = artifacts.filter((artifact) => artifact.exists).map((artifact) => artifact.name);
  const text = names.join(", ") || "none";
  return useBadges ? badge(text, names.length ? "ok" : "warn") : escapeHtml(text);
}

function badge(label, tone) {
  return `<span class="badge ${tone}">${escapeHtml(label)}</span>`;
}

function emptyRow(message, colspan) {
  return `<tr><td colspan="${colspan}"><div class="empty">${escapeHtml(message)}</div></td></tr>`;
}

function optionalValue(value) {
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#96;");
}

document.querySelectorAll(".nav-item").forEach((button) => {
  button.addEventListener("click", () => activateView(button.dataset.view));
});

$("#refreshButton").addEventListener("click", () => {
  loadAll().catch((error) => setApiStatus(false, error.message));
});

$("#runRows").addEventListener("click", (event) => {
  const row = event.target.closest(".run-row");
  if (row) selectRun(row.dataset.runId);
});

$("#runRows").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest(".run-row");
  if (row) {
    event.preventDefault();
    selectRun(row.dataset.runId);
  }
});

$("#playgroundForm").addEventListener("submit", submitPlayground);

loadAll().catch((error) => {
  setApiStatus(false, error.message);
  renderAll();
});
