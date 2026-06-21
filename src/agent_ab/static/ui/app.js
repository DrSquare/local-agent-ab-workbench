const state = {
  experiments: [],
  taskpacks: [],
  runs: [],
  views: [],
  selectedRun: null,
  selectedTrace: null,
  selectedSpanId: null,
  playgroundDefaults: null,
  playgroundResult: null,
  collapsedSpanIds: new Set(),
  traceFilters: {
    kind: "",
    status: "",
  },
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

async function loadAll(options = {}) {
  const { refreshPlaygroundDefaults = true } = options;
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
  if (refreshPlaygroundDefaults) {
    await loadPlaygroundDefaults({ silent: true });
  }
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
  renderPlaygroundResult();
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
    <button class="list-item saved-view" data-view-id="${escapeAttribute(view.id)}" type="button">
      <strong>${escapeHtml(view.label || view.id)}</strong>
      <span>${escapeHtml(view.task_id)} via ${escapeHtml(view.variant_id)}</span>
      <span>${escapeHtml(view.run_id)}</span>
    </button>
  `).join("") || `<div class="empty">No saved candidates</div>`;
}

function renderTrace() {
  const run = state.selectedRun;
  const trace = state.selectedTrace;
  $("#selectedRunLabel").textContent = run ? run.run_id : "No run selected";

  if (!run) {
    $("#traceTree").innerHTML = `<div class="empty">Select a run to load its trace</div>`;
    $("#traceDetails").innerHTML = "";
    $("#traceTimeline").innerHTML = "";
    renderTraceFilterOptions([]);
    return;
  }

  if (!trace) {
    $("#traceTree").innerHTML = `<div class="empty">Trace data is not loaded</div>`;
    $("#traceTimeline").innerHTML = "";
    renderRunDetail(run);
    renderTraceFilterOptions([]);
    return;
  }

  const spans = trace.spans || [];
  renderTraceFilterOptions(spans);
  const filteredSpans = filterSpansWithAncestors(spans);
  const children = groupByParent(filteredSpans);
  const root = filteredSpans.find((span) => !span.parent_span_id);
  if (!root) {
    $("#traceTree").innerHTML = `<div class="empty">No spans match the current filters</div>`;
    $("#traceTimeline").innerHTML = "";
    renderRunDetail(run);
    return;
  }

  if (!filteredSpans.some((span) => span.span_id === state.selectedSpanId)) {
    state.selectedSpanId = root.span_id;
  }

  $("#traceTree").innerHTML = renderSpan(root, children, 0);
  renderSpanDetail(filteredSpans.find((span) => span.span_id === state.selectedSpanId) || root);
  renderTimeline(filteredSpans);
}

async function selectRun(runId) {
  const run = state.runs.find((item) => item.run_id === runId);
  state.selectedRun = run || null;
  state.selectedTrace = null;
  state.selectedSpanId = null;
  state.collapsedSpanIds.clear();
  activateView("trace");
  renderTrace();
  if (!run) return;

  try {
    const tracePayload = await fetchJson(`/runs/${encodeURIComponent(run.run_id)}/trace`);
    state.selectedTrace = (tracePayload.traces || [])[0] || null;
    const root = (state.selectedTrace?.spans || []).find((span) => !span.parent_span_id);
    state.selectedSpanId = root?.span_id || null;
    renderTrace();
  } catch (error) {
    $("#traceTree").innerHTML = `<div class="empty">${escapeHtml(error.message)}</div>`;
  }
}

async function submitPlayground(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const saveCandidate = event.submitter?.dataset.action === "save";

  $("#playgroundStatus").textContent = saveCandidate ? "Saving candidate" : "Running replay";
  try {
    const payload = buildPlaygroundPayload(form, saveCandidate);
    const result = await fetchJson("/playground/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    $("#playgroundStatus").textContent = `${result.status}: ${result.run_id}`;
    state.playgroundResult = result;
    renderPlaygroundResult();
    await loadAll({ refreshPlaygroundDefaults: false });
    await selectRun(result.run_id);
  } catch (error) {
    $("#playgroundStatus").textContent = error.message;
  }
}

function buildPlaygroundPayload(form, saveCandidate) {
  return {
    experiment_path: form.experiment_path.value.trim(),
    variant_id: form.variant_id.value.trim(),
    task_id: form.task_id.value.trim(),
    run_id: optionalValue(form.run_id.value),
    prompt_variables: parseJsonObject($("#pgPromptVariables").value, "Extra prompt variables JSON"),
    save_view: saveCandidate,
    view_id: saveCandidate ? optionalValue(form.view_id.value) : undefined,
    label: saveCandidate ? optionalValue(form.label.value) : undefined,
    overrides: collectPlaygroundOverrides(),
  };
}

function collectPlaygroundOverrides() {
  return {
    messages: collectPromptMessages(),
    variables: parseList($("#pgVariables").value),
    model: {
      provider: $("#pgModelProvider").value,
      name: $("#pgModelName").value.trim(),
      endpoint: optionalValue($("#pgModelEndpoint").value),
    },
    parameters: {
      temperature: optionalNumber($("#pgTemperature").value),
      top_p: optionalNumber($("#pgTopP").value),
      max_tokens: optionalInteger($("#pgMaxTokens").value),
    },
    tool_policy: {
      allow_tools: parseList($("#pgAllowTools").value),
      read_only_tools: parseList($("#pgReadOnlyTools").value),
      require_confirmation: parseList($("#pgRequireConfirmation").value),
      block_tools: parseList($("#pgBlockTools").value),
    },
    metadata: {
      source: "module9_playground_ui",
    },
  };
}

async function loadPlaygroundDefaults(options = {}) {
  const { silent = false } = options;
  const experimentPath = $("#pgExperiment").value.trim();
  const variantId = $("#pgVariant").value.trim();
  if (!experimentPath || !variantId) return null;

  if (!silent) {
    $("#playgroundStatus").textContent = "Loading variant";
  }

  try {
    const defaults = await fetchJson(
      `/playground/defaults?experiment_path=${encodeURIComponent(experimentPath)}&variant_id=${encodeURIComponent(variantId)}`,
    );
    state.playgroundDefaults = defaults;
    applyPlaygroundDefaults(defaults);
    if (!silent) {
      $("#playgroundStatus").textContent = `Loaded ${defaults.variant_id}`;
    }
    return defaults;
  } catch (error) {
    if (!silent) {
      $("#playgroundStatus").textContent = error.message;
    }
    return null;
  }
}

function applyPlaygroundDefaults(defaults) {
  syncSelectValues("#pgVariant", defaults.variants || [], defaults.variant_id);
  syncSelectValues("#pgTask", defaults.task_ids || [], $("#pgTask").value || (defaults.task_ids || [])[0]);
  const prompt = defaults.prompt || {};
  const model = prompt.model || {};
  const parameters = prompt.parameters || {};
  const registry = defaults.local_model_registry || {};

  syncDatalist("#pgModelOptions", registry.models || []);
  $("#pgModelProvider").value = model.provider || registry.provider || "ollama";
  $("#pgModelName").value = model.name || (registry.models || [])[0] || "";
  $("#pgModelEndpoint").value = model.endpoint || registry.endpoint || "";
  $("#pgTemperature").value = valueOrEmpty(parameters.temperature);
  $("#pgTopP").value = valueOrEmpty(parameters.top_p);
  $("#pgMaxTokens").value = valueOrEmpty(parameters.max_tokens);
  $("#pgVariables").value = (prompt.variables || []).join(", ");
  renderPromptEditors(prompt.messages || []);
  populateToolPolicyFromPrompt(prompt.tools || []);
  setPlaygroundCapabilities(defaults.capabilities || {});
}

function syncSelectValues(selector, values, selectedValue) {
  const select = $(selector);
  const current = selectedValue || select.value;
  select.innerHTML = values.map((value) => `<option value="${escapeAttribute(value)}">${escapeHtml(value)}</option>`).join("");
  select.value = values.includes(current) ? current : values[0] || "";
}

function syncDatalist(selector, values) {
  $(selector).innerHTML = values
    .map((value) => `<option value="${escapeAttribute(value)}"></option>`)
    .join("");
}

function renderPromptEditors(messages) {
  $("#promptEditors").innerHTML = messages.map((message, index) => `
    <div class="prompt-card" data-index="${index}">
      <label>
        Role
        <select class="prompt-role">
          ${["system", "developer", "user", "assistant", "tool"].map((role) => `
            <option value="${role}" ${role === message.role ? "selected" : ""}>${role}</option>
          `).join("")}
        </select>
      </label>
      <label>
        Content
        <textarea class="prompt-content" rows="7">${escapeHtml(message.content || "")}</textarea>
      </label>
    </div>
  `).join("") || `<div class="empty">No prompt messages</div>`;
}

function populateToolPolicyFromPrompt(tools) {
  $("#pgAllowTools").value = tools
    .filter((tool) => tool.enabled && tool.policy === "allow")
    .map((tool) => tool.name)
    .join(", ");
  $("#pgReadOnlyTools").value = tools
    .filter((tool) => tool.enabled && tool.policy === "read_only")
    .map((tool) => tool.name)
    .join(", ");
  $("#pgRequireConfirmation").value = tools
    .filter((tool) => tool.enabled && tool.policy === "require_confirmation")
    .map((tool) => tool.name)
    .join(", ");
  $("#pgBlockTools").value = tools
    .filter((tool) => !tool.enabled || tool.policy === "block")
    .map((tool) => tool.name)
    .join(", ");
}

function setPlaygroundCapabilities(capabilities) {
  const promptDisabled = capabilities.allow_prompt_editing === false;
  const modelDisabled = capabilities.allow_model_switching === false;
  const parameterDisabled = capabilities.allow_parameter_editing === false;
  const toolPolicyDisabled = capabilities.allow_tool_policy_editing === false;
  document.querySelectorAll(".prompt-role, .prompt-content, #pgVariables").forEach((field) => {
    field.disabled = promptDisabled;
  });
  ["#pgModelProvider", "#pgModelName", "#pgModelEndpoint"].forEach((selector) => {
    $(selector).disabled = modelDisabled;
  });
  ["#pgTemperature", "#pgTopP", "#pgMaxTokens"].forEach((selector) => {
    $(selector).disabled = parameterDisabled;
  });
  ["#pgAllowTools", "#pgReadOnlyTools", "#pgRequireConfirmation", "#pgBlockTools"].forEach((selector) => {
    $(selector).disabled = toolPolicyDisabled;
  });
}

function collectPromptMessages() {
  return [...document.querySelectorAll(".prompt-card")].map((card) => ({
    role: card.querySelector(".prompt-role").value,
    content: card.querySelector(".prompt-content").value,
  }));
}

function renderPlaygroundResult() {
  const result = state.playgroundResult;
  if (!result) {
    $("#playgroundResult").innerHTML = `<div class="empty">No replay result</div>`;
    return;
  }
  const model = result.effective_prompt?.model || {};
  const metrics = (result.metrics || [])
    .map((metric) => `${metric.name}: ${metric.value}`)
    .join(", ") || "-";
  const renderedMessages = (result.rendered_messages || [])
    .map((message) => `
      <div class="rendered-message">
        <strong>${escapeHtml(message.role)}</strong>
        <pre>${escapeHtml(message.content)}</pre>
      </div>
    `)
    .join("");
  $("#playgroundResult").innerHTML = `
    <dl class="detail-list">
      ${detailRows({
        Status: result.status,
        Run: result.run_id,
        Trace: result.trace_id,
        Candidate: result.view_id || "-",
        Model: `${model.provider || "-"} / ${model.name || "-"}`,
        Metrics: metrics,
      })}
    </dl>
    <div class="rendered-stack">${renderedMessages}</div>
  `;
}

function applyPlaygroundView(view) {
  const request = view.request || {};
  const response = view.response || {};
  $("#pgExperiment").value = request.experiment_path || $("#pgExperiment").value;
  syncSelectValues(
    "#pgVariant",
    uniqueValues([...(state.playgroundDefaults?.variants || []), request.variant_id]),
    request.variant_id,
  );
  syncSelectValues(
    "#pgTask",
    uniqueValues([...(state.playgroundDefaults?.task_ids || []), request.task_id]),
    request.task_id,
  );
  $("#pgRunId").value = "";
  $("#pgViewId").value = "";
  $("#pgLabel").value = view.label || request.label || "";
  $("#pgPromptVariables").value = JSON.stringify(request.prompt_variables || {}, null, 2);
  applyPlaygroundOverridesToForm(request.overrides || {});
  state.playgroundResult = response;
  renderPlaygroundResult();
}

function applyPlaygroundOverridesToForm(overrides) {
  if (overrides.messages) {
    renderPromptEditors(overrides.messages);
  }
  $("#pgVariables").value = (overrides.variables || []).join(", ");
  if (overrides.model) {
    $("#pgModelProvider").value = overrides.model.provider || "ollama";
    $("#pgModelName").value = overrides.model.name || "";
    $("#pgModelEndpoint").value = overrides.model.endpoint || "";
  }
  if (overrides.parameters) {
    $("#pgTemperature").value = valueOrEmpty(overrides.parameters.temperature);
    $("#pgTopP").value = valueOrEmpty(overrides.parameters.top_p);
    $("#pgMaxTokens").value = valueOrEmpty(overrides.parameters.max_tokens);
  }
  if (overrides.tool_policy) {
    $("#pgAllowTools").value = (overrides.tool_policy.allow_tools || []).join(", ");
    $("#pgReadOnlyTools").value = (overrides.tool_policy.read_only_tools || []).join(", ");
    $("#pgRequireConfirmation").value = (overrides.tool_policy.require_confirmation || []).join(", ");
    $("#pgBlockTools").value = (overrides.tool_policy.block_tools || []).join(", ");
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
  const isCollapsed = state.collapsedSpanIds.has(span.span_id);
  const isSelected = state.selectedSpanId === span.span_id;
  const indent = `${depth * 18}px`;
  return `
    <div class="span-node ${isSelected ? "is-selected" : ""}" data-span-id="${escapeAttribute(span.span_id)}" data-kind="${escapeAttribute(span.kind)}" style="margin-left: ${indent}" role="button" tabindex="0" aria-selected="${isSelected}">
      <button class="span-toggle" data-span-id="${escapeAttribute(span.span_id)}" ${childNodes.length ? "" : "disabled"} type="button" aria-label="${isCollapsed ? "Expand" : "Collapse"} ${escapeAttribute(span.name)}">${childNodes.length ? (isCollapsed ? "+" : "-") : ""}</button>
      <span>${escapeHtml(span.kind)}</span>
      <strong>${escapeHtml(span.name)}</strong>
      <span>${escapeHtml(span.status || "-")}</span>
      <span>${span.duration_ms ?? "-"} ms</span>
    </div>
    ${isCollapsed ? "" : childNodes.map((child) => renderSpan(child, children, depth + 1)).join("")}
  `;
}

function detailRows(details) {
  return Object.entries(details).map(([key, value]) => `
    <dt>${escapeHtml(key)}</dt>
    <dd>${escapeHtml(value)}</dd>
  `).join("");
}

function renderRunDetail(run) {
  $("#traceDetails").innerHTML = detailRows({
    Run: run.run_id,
    Task: run.task_id || "-",
    Variant: run.variant_id || "-",
    Trace: run.trace_id || "-",
    Artifacts: artifactSummary(run.artifacts || [], false),
  });
}

function renderSpanDetail(span) {
  const typedDetail = span.model_call
    || span.tool_call
    || span.desktop_action
    || span.shell_action
    || span.validator
    || span.scoring;
  const typedDetailName = span.model_call ? "model_call"
    : span.tool_call ? "tool_call"
      : span.desktop_action ? "desktop_action"
        : span.shell_action ? "shell_action"
          : span.validator ? "validator"
            : span.scoring ? "scoring"
              : null;

  $("#traceDetails").innerHTML = detailRows({
    Span: span.span_id,
    Parent: span.parent_span_id || "-",
    Name: span.name,
    Kind: span.kind,
    Status: span.status || "-",
    Start: `${span.started_at_ms} ms`,
    End: span.ended_at_ms === null || span.ended_at_ms === undefined ? "-" : `${span.ended_at_ms} ms`,
    Duration: span.duration_ms === null || span.duration_ms === undefined ? "-" : `${span.duration_ms} ms`,
    Detail: typedDetailName || "-",
  }) + (typedDetail ? `<dt>Payload</dt><dd><pre class="detail-json">${escapeHtml(JSON.stringify(typedDetail, null, 2))}</pre></dd>` : "");
}

function renderTraceFilterOptions(spans) {
  syncSelectOptions("#traceKindFilter", uniqueValues(spans.map((span) => span.kind)), "All kinds");
  syncSelectOptions("#traceStatusFilter", uniqueValues(spans.map((span) => span.status)), "All statuses");
  state.traceFilters.kind = $("#traceKindFilter").value;
  state.traceFilters.status = $("#traceStatusFilter").value;
}

function syncSelectOptions(selector, values, emptyLabel) {
  const select = $(selector);
  const current = select.value;
  select.innerHTML = [
    `<option value="">${emptyLabel}</option>`,
    ...values.map((value) => `<option value="${escapeAttribute(value)}">${escapeHtml(value)}</option>`),
  ].join("");
  select.value = values.includes(current) ? current : "";
}

function uniqueValues(values) {
  return [...new Set(values.filter(Boolean))].sort();
}

function filterSpansWithAncestors(spans) {
  const matches = spans.filter(matchesSpanFilters);
  if (!state.traceFilters.kind && !state.traceFilters.status) {
    return spans;
  }
  const byId = Object.fromEntries(spans.map((span) => [span.span_id, span]));
  const included = new Set();
  matches.forEach((span) => {
    let current = span;
    while (current) {
      included.add(current.span_id);
      current = current.parent_span_id ? byId[current.parent_span_id] : null;
    }
  });
  return spans.filter((span) => included.has(span.span_id));
}

function matchesSpanFilters(span) {
  return (!state.traceFilters.kind || span.kind === state.traceFilters.kind)
    && (!state.traceFilters.status || span.status === state.traceFilters.status);
}

function renderTimeline(spans) {
  if (!spans.length) {
    $("#traceTimeline").innerHTML = `<div class="empty">No timing data</div>`;
    return;
  }
  const start = Math.min(...spans.map((span) => span.started_at_ms));
  const end = Math.max(...spans.map((span) => span.ended_at_ms ?? span.started_at_ms));
  const total = Math.max(end - start, 1);
  $("#traceTimeline").innerHTML = spans
    .slice()
    .sort((a, b) => a.started_at_ms - b.started_at_ms)
    .map((span) => {
      const duration = Math.max((span.ended_at_ms ?? span.started_at_ms) - span.started_at_ms, 0);
      const offset = Math.max(((span.started_at_ms - start) / total) * 100, 0);
      const width = Math.max((duration / total) * 100, 1);
      return `
        <button class="timeline-row" data-span-id="${escapeAttribute(span.span_id)}" type="button">
          <span>${escapeHtml(span.name)}</span>
          <span class="timeline-track" aria-hidden="true">
            <span class="timeline-bar" style="left: ${offset}%; width: ${width}%;"></span>
          </span>
          <span>${duration} ms</span>
        </button>
      `;
    })
    .join("");
}

function artifactSummary(artifacts, useBadges = true) {
  const names = artifacts.filter((artifact) => artifact.exists).map((artifact) => artifact.name);
  const text = names.join(", ") || "none";
  return useBadges ? badge(text, names.length ? "ok" : "warn") : text;
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

function optionalNumber(value) {
  const trimmed = value.trim();
  return trimmed ? Number(trimmed) : undefined;
}

function optionalInteger(value) {
  const numberValue = optionalNumber(value);
  return numberValue === undefined ? undefined : Math.trunc(numberValue);
}

function valueOrEmpty(value) {
  return value === null || value === undefined ? "" : String(value);
}

function parseList(value) {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseJsonObject(value, label) {
  const trimmed = value.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${label} must be a JSON object`);
  }
  return parsed;
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

$("#traceTree").addEventListener("click", (event) => {
  const toggle = event.target.closest(".span-toggle");
  if (toggle && !toggle.disabled) {
    const spanId = toggle.dataset.spanId;
    if (state.collapsedSpanIds.has(spanId)) {
      state.collapsedSpanIds.delete(spanId);
    } else {
      state.collapsedSpanIds.add(spanId);
    }
    renderTrace();
    return;
  }
  const node = event.target.closest(".span-node");
  if (node) {
    state.selectedSpanId = node.dataset.spanId;
    renderTrace();
  }
});

$("#traceTree").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const node = event.target.closest(".span-node");
  if (node) {
    event.preventDefault();
    state.selectedSpanId = node.dataset.spanId;
    renderTrace();
  }
});

$("#traceTimeline").addEventListener("click", (event) => {
  const row = event.target.closest(".timeline-row");
  if (row) {
    state.selectedSpanId = row.dataset.spanId;
    renderTrace();
  }
});

$("#traceKindFilter").addEventListener("change", (event) => {
  state.traceFilters.kind = event.target.value;
  renderTrace();
});

$("#traceStatusFilter").addEventListener("change", (event) => {
  state.traceFilters.status = event.target.value;
  renderTrace();
});

$("#expandTraceButton").addEventListener("click", () => {
  state.collapsedSpanIds.clear();
  renderTrace();
});

$("#collapseTraceButton").addEventListener("click", () => {
  const spans = state.selectedTrace?.spans || [];
  const children = groupByParent(spans);
  state.collapsedSpanIds = new Set(Object.keys(children).filter((spanId) => spanId));
  renderTrace();
});

$("#loadPromptButton").addEventListener("click", () => {
  loadPlaygroundDefaults().catch((error) => {
    $("#playgroundStatus").textContent = error.message;
  });
});

$("#pgExperiment").addEventListener("change", () => {
  loadPlaygroundDefaults({ silent: true }).catch(() => {});
});

$("#pgVariant").addEventListener("change", () => {
  loadPlaygroundDefaults({ silent: true }).catch(() => {});
});

$("#viewList").addEventListener("click", async (event) => {
  const item = event.target.closest(".saved-view");
  if (!item) return;
  $("#playgroundStatus").textContent = "Loading candidate";
  try {
    const view = await fetchJson(`/playground/views/${encodeURIComponent(item.dataset.viewId)}`);
    applyPlaygroundView(view);
    $("#playgroundStatus").textContent = `Loaded ${view.id}`;
  } catch (error) {
    $("#playgroundStatus").textContent = error.message;
  }
});

$("#playgroundForm").addEventListener("submit", submitPlayground);

loadAll().catch((error) => {
  setApiStatus(false, error.message);
  renderAll();
});
