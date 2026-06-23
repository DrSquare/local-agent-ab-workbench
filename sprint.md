# Sprint Tracker

## Current Sprint

Module 19: Prompt and Harness Improvement Loop UI.

## Status

| Area | Status | Notes |
|---|---|---|
| Module 1 schemas | Done | Experiment, Prompt Object, metric registry, Playground config, tracing config, and CLI validators are committed. |
| Module 1 hardening | Done | Duplicate YAML keys, local endpoints, prompt templates, baseline variants, and tool policy conflicts are covered by tests. |
| TDD test folder | Done | `tests_tdd/` is available for opt-in red tests. |
| Module 2 task contracts | Done | Taskpack schema, task case schema, validator contracts, demo taskpack, CLI validation, and tests are implemented. |
| Module 3 trace contracts | Done | Trace envelope, typed span details, JSONL writer, SQLite index, and tests are implemented. |
| Module 4 mock runner | Done | Run workspace lifecycle, validator executor, deterministic mock adapter, trace artifact writing, and tests are implemented. |
| Module 5 local backend | Done | Localhost-only server command, experiment/taskpack discovery, run summaries, artifact listing, trace retrieval, and API tests are implemented. |
| Module 6 Playground backend | Done | Playground request/response schemas, override validation, deterministic mock replay, view persistence, API endpoints, and tests are implemented. |
| Module 7 frontend shell | Done | No-build static UI served from `/ui`, local API navigation, run/trace selection, Playground replay form, saved views list, and frontend route tests are implemented. |
| Module 8 trace visualizer UI | Done | Expandable span tree, span detail payload pane, timing waterfall, kind/status filters, keyboard selection, and trace UI tests are implemented. |
| Module 9 Playground UI | Done | Prompt editor, model/parameter controls, tool-policy controls, replay/save actions, defaults loading, and result rendering are implemented. |
| Module 10 OpenClaw adapter | Done | OpenClaw config translation, command planning, prepared run artifacts, trace wrapping, demo adapter experiment/taskpack, and CLI preparation are implemented. |
| Module 11 guardrails and sandbox | Done | Path policy, blocked command checks, local endpoint checks, timeout checks, secret redaction, and OpenClaw plan enforcement are implemented. |
| Module 12 demo and reporting | Done | Local demo helper/script, JSON and CSV run exports, reporting CLI commands, README updates, and known limitations are implemented. |
| Post-MVP aggregate reporting | Done | Task/variant comparison reports can aggregate repeated run artifacts and export JSON or CSV through the CLI. |
| Post-MVP OpenClaw execution gate | Done | Prepared OpenClaw plans can execute only through an explicit `allow_execute=True` opt-in and are covered with injected-runner tests. |
| Post-MVP browser UI tests | Done | Optional Playwright tests cover local inventory, trace selection, and Playground replay when a browser runtime is installed. |
| Post-MVP workflow docs | Done | PR checklist, required verification commands, release steps, and rollback guidance are documented. |
| Post-MVP guardrail edge cases | Done | Command normalization, run-dir path policy, POSIX root handling, and real-adapter trace aliases are covered. |
| Inspect AI reference review | Done | Mission, plan, tech stack, and sprint tracker now use task/dataset/solver/scorer/log/sandbox concepts as the next architecture reference. |
| Module 13 expert seed generation | Done | Public Mercor APEX seeds can generate a TaskPack with O*NET Task IDs and NBER Appendix A.4-style IWA metadata. |
| Arize-inspired GUI plan | Done | Plan, tech stack, and sprint tracker now define a local Observe/Evaluate/Improve GUI roadmap without adding Arize or cloud telemetry dependencies. |
| Arize GUI self-review | Done | Roadmap now includes Module 17 information architecture, backend read-model expectations, static frontend architecture, and fixture-based test requirements. |
| Module 13 EvalTask core | Done | Strict EvalTask, EvalSample, solver reference, scorer reference, EvalLog contracts, example eval configs, CLI validation, and tests are implemented. |
| Module 14 Eval Runner and Eval Sets | Done | EvalSet validation, deterministic EvalRunPlan generation, resume/skip detection over EvalLog JSON, failure/sample limits, plan JSON export, CLI commands, and tests are implemented without new real execution. |
| Module 15 Analysis and Scanner Layer | Done | EvalRunPlan/EvalLog loading, per-sample JSON/CSV exports, aggregate summaries, local scanner findings, failure taxonomy hooks, CLI commands, and tests are implemented. |
| Module 16 Sandbox Provider Interface | Done | Provider-level workspace, command, network, timeout, artifact, and approval/denial event contracts map onto existing guardrails without adding new execution. |
| Module 17 Observability and Eval GUI | Done | Backend read models, `/observability`, Dashboard/Evaluate/Observe/Improve/Settings routes, eval rows, regression queue, sandbox status, and Playground handoff are implemented. |
| Module 18 Regression Review UI | Done | Repeated-run and variant regression rows, failure/status/triage filters, local triage notes, export links, API routes, responsive styling, and focused tests are implemented. |
| Module 19 Improvement Loop UI | Done | Selected regression/failure handoff, improvement notes, rerun queue entries, candidate promotion artifacts, guardrail reminders, API routes, and focused tests are implemented. |

## Module 13 Seed Generation Acceptance Criteria

- Built-in public Mercor APEX seeds cover investment banking, management consulting, and corporate law examples.
- Seed metadata includes Mercor role/source details and explicit source limitations.
- Seed metadata includes O*NET occupation code/title plus official Task ID and task statement.
- Seed metadata includes GWA/IWA/DWA classification fields following the NBER Appendix A.4 IWA mapping shape.
- `agent-ab generate-seed-taskpack` writes TaskPack YAML and a fixture directory without network access.
- Generated seed taskpacks validate with `agent-ab validate-taskpack`.
- Tests cover schema strictness, duplicate seed rejection, deterministic generation, fixture validation, and CLI output.

## Module 13 Acceptance Criteria

- EvalTask config validates with strict unknown-key rejection.
- EvalTask selects all samples or named samples from an existing TaskPack.
- EvalTask can select the generated `mercor_apex_expert_seeded` TaskPack.
- Solver references validate against registered adapter names without executing real agents.
- Scorer references validate against built-in metrics, validators, or `custom.` names.
- EvalLog schema captures sample ID, solver ID, scorer results, trace reference, artifacts, limits, errors, and metadata.
- Current A/B reporting and Playground replay can be described as workflows over EvalTask/EvalLog.
- Module 13 tests cover every new schema rule.

## Module 16 Acceptance Criteria

- Sandbox provider schema separates provider identity, workspace policy,
  command policy, network policy, timeout policy, and artifact policy.
- Local workspace provider is described without Docker or cloud dependency.
- Optional Docker provider remains a design/contract only, not a required
  dependency.
- Tool approval and denial events are representable in EvalLog-compatible
  metadata.
- Existing guardrail helpers map into provider policy without regressions.
- Module 15 scanner classifies sandbox denial events once logs include them.
- Module 16 tests cover strict schema rules, guardrail mapping, CLI validation,
  event metadata compatibility, and sandbox-denial scanner findings.

## Arize-Inspired GUI Acceptance Criteria

- Module 17 starts only after EvalTask and EvalLog contracts are stable enough
  to drive dashboard, trace, and regression views.
- The first GUI screen is the workbench dashboard, not a landing page.
- Top-level navigation exposes Observe, Evaluate, and Improve modes.
- Module 17 includes Dashboard, Evaluate, Observe, Improve, and Settings routes
  in the existing no-build frontend shell.
- Observe mode joins trace/session spans, artifacts, errors, timing, and scorer
  context.
- Evaluate mode shows run status, pass rates, scorer results, score deltas,
  regressions, task metadata, and trace links.
- Improve mode opens failed or regressed samples in Playground with original
  prompt, model, parameters, tool policy, trace, and scorer context.
- Backend read models cover dashboard summaries, eval-run rows, regression
  rows, trace links, and Playground handoff payloads before UI complexity grows.
- Regression review supports variant and repeated-run comparison before
  candidate promotion.
- Frontend assets remain local-only: no external fonts, scripts, CDNs, images,
  cloud telemetry, Arize SDK, or Phoenix dependency.
- Browser-level tests cover navigation, dashboard data loading, trace drilldown,
  Playground handoff, responsive layout, and offline asset assumptions.

## Module 17 Acceptance Criteria

- Backend read models expose dashboard summaries, eval-run rows, regression
  rows, trace links, scorer evidence, artifact references, Playground handoffs,
  and sandbox status.
- The local API exposes `/observability` over EvalRunPlan/EvalLog artifacts.
- No-build UI modes expose Dashboard, Evaluate, Observe, Improve, and Settings.
- Evaluate mode shows task/sample status, scorer outcomes, pass rates, score
  deltas, latency, trace links, and sandbox denial badges.
- Observe mode keeps trace/session drilldown available through the local trace
  visualizer.
- Improve mode can hand failed or errored samples to Playground review context.
- UI assets remain local-only with no external fonts, scripts, CDNs, Arize SDK,
  Phoenix dependency, or cloud telemetry.
- Module 17 tests cover backend read models, API payloads, static UI assets,
  local-only assumptions, and regression ordering.

## Module 18 Acceptance Criteria

- Regression review supports repeated-run and variant comparisons over EvalLog
  artifacts.
- Regression rows show previous score, current score, delta, trace link, sample
  metadata, solver, variant, and comparison kind.
- Failure taxonomy, current-status, and triage-status filters work without
  cloud graders.
- Saved triage notes are linked to EvalTask, EvalLog, sample, trace, failure
  taxonomy, status, and tags.
- Export links point to local JSON/CSV eval-log, aggregate, and scanner
  artifacts.
- Responsive table and note layouts remain usable on laptop and narrow screens.

## Module 19 Acceptance Criteria

- Selected regression and failed eval rows can seed Playground comparison
  context.
- Prompt/result comparison context is visible before candidate promotion.
- Candidate promotion writes reviewable local JSON artifacts rather than
  mutating source configs silently.
- Rerun queues can be seeded from selected regressions or failed eval rows.
- Saved improvement notes link EvalTask, EvalLog, trace, triage note, and
  Playground View IDs.
- Guardrail reminders remain visible for workflows that prepare future real
  adapter execution.

## Completed Post-MVP Criteria

- Repeated local runs can be grouped by task and variant.
- Comparison reports can be exported as JSON and CSV.
- CLI commands support comparison report export.
- Real OpenClaw execution remains blocked unless explicitly opted in.
- Execution-gate tests do not invoke a real desktop agent.
- Browser-level UI tests skip cleanly when Playwright is unavailable.
- PR and release workflow docs list required verification and risk review items.
- Windows/POSIX command and path edge cases are covered by tests.
- Real-adapter trace aliases normalize to typed workbench spans with redaction.

## Working Rules

- Keep the base install offline-first and small.
- Do not add cloud-only dependencies.
- Do not add real agent execution beyond deterministic mock behavior before adapter modules.
- Add tests for every new schema rule.
- Move durable passing tests into `tests/`; keep `tests_tdd/` for temporary red tests only.

## Next Sprint Candidate

Module 20: Guarded Eval Execution Harness. Bind EvalRunPlan samples to solver
execution through sandbox provider policy, starting with deterministic mock
execution and dry-run support while keeping real adapters explicitly gated.
