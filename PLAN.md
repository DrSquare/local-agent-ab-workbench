# Local Offline Agent Evaluation Workbench Product Plan

## Mission

Build a local, offline-first evaluation and debugging workbench for desktop AI
agents such as OpenClaw-style local assistants.

The workbench should adapt Inspect AI's evaluation pattern to local desktop
agents: datasets of deterministic samples, solver or agent adapters, scorers,
eval logs, analysis, and sandboxed execution. A/B comparison, trace debugging,
and Playground replay remain core workflows, but they sit on top of a reusable
evaluation model rather than defining the model themselves.

The future GUI should turn those contracts into a local Observe, Evaluate, and
Improve cockpit inspired by Arize's agent-engineering UX while preserving the
project's offline-first and user-controlled storage requirements.

## Planning Critique

The original plan had the right product loop, but it mixed long-term runtime and
UI deliverables into the current schema-only stage. That made the next step less
clear and risked adding agent execution before the repository has task, trace,
and result contracts.

Post-MVP review against Inspect AI shows a second gap: the current architecture
has experiments, taskpacks, validators, traces, and reports, but it does not yet
name the deeper reusable objects that Inspect makes explicit: task, dataset,
sample, solver, scorer, eval log, analysis, limits, and sandbox.

This revision keeps the local desktop-agent mission, but changes the next
milestone from "pick another product feature" to "add an Inspect-inspired eval
core." The workbench should not clone Inspect or depend on it by default; it
should adopt the component boundaries that make evaluations easier to compose,
resume, analyze, and extend.

The Arize reference adds a complementary product critique: the existing shell
has useful local screens, but the roadmap should name the full agent debugging
loop as a coherent GUI. Users should be able to observe traces, evaluate quality
and regressions, then improve prompts or harnesses without jumping between
unrelated views.

## Inspect AI Reference Takeaways

| Inspect idea | Workbench adaptation |
|---|---|
| Task combines dataset, solver, and scorer | `EvalTask` binds TaskPack samples, an adapter, scorer IDs, limits, and logging |
| Dataset/sample abstraction | TaskPack tasks become normalized local samples with workspace fixtures |
| Solver/agent abstraction | Mock, OpenClaw, generic CLI, and local HTTP become solver adapters |
| Scorers produce comparable outcomes | Validators, trace checks, and future model graders become scorer pipeline stages |
| Eval logs are first-class | Trace envelopes grow into eval logs with config, scores, artifacts, and transcript events |
| Eval sets support repeated runs | Multi-variant, multi-task run plans become resumable local eval sets |
| Sandboxes gate tools | Disposable workspaces plus path, command, endpoint, timeout, and redaction policy |
| Analysis scans logs | Reports, comparisons, and future scanners operate over local eval logs |

## Arize UX Reference Takeaways

Arize is a UX and workflow reference for the next GUI phase. The workbench
should adapt its observe/evaluate/improve loop locally without depending on
Arize-hosted products, Phoenix, or managed observability.

| Arize idea | Local workbench adaptation |
|---|---|
| Observe what the agent did | Trace/session explorer with span hierarchy, tool calls, artifacts, errors, timing, and local trace links |
| Evaluate whether quality changed | Eval dashboard with task/sample status, scorer results, pass rates, score deltas, and regression flags |
| Improve prompts and harnesses | Playground-linked prompt, parameter, and harness comparison before candidate promotion |
| Continual learning loop | Local run history, failure clusters, saved notes, and rerun prompts that guide the next eval design |
| Open standards | OpenInference/OpenTelemetry-compatible naming where useful, with no proprietary trace format requirement |

This is a design reference only. External cloud calls, managed telemetry
services, hosted assets, and Arize-specific dependencies remain out of scope for
the core offline workbench.

## Current State

Modules 1 through 19 plus post-MVP hardening are implemented with clear
local-first boundaries:

- Experiment config
- Prompt Object config
- TaskPack and TaskCase config
- Declarative task validator contracts
- Trace envelope and span schemas
- JSONL trace writer contract
- SQLite trace index contract
- Deterministic mock runner and local validator executor
- Localhost-only FastAPI backend for discovery and trace inspection
- Playground backend contracts, deterministic mock replay, and view persistence
- Local frontend shell served from the FastAPI app
- Trace visualizer UI with expandable spans, filters, details, and waterfall timing
- AgentEval-inspired metric registry
- Playground config contract
- Tracing config contract
- Mercor APEX-inspired expert seed TaskPack generation
- O*NET occupation/task IDs and NBER Appendix A.4-style IWA metadata on seed tasks
- EvalTask, EvalSample, solver reference, scorer reference, and EvalLog schemas
- EvalTask CLI validation over referenced TaskPacks and sample selections
- EvalSet schema, EvalRunPlan schema, deterministic non-executing run planning,
  resume/skip detection, and plan JSON export
- EvalRunPlan/EvalLog analysis exports, aggregate summaries, and local
  rule-based scanner findings with failure taxonomy hooks
- Sandbox provider contracts for local workspace execution policy and optional
  Docker provider design without a Docker runtime dependency
- Guardrail mapping from sandbox provider policy into existing path, command,
  endpoint, and timeout checks
- EvalLog-compatible sandbox approval and denial events plus scanner
  classification for sandbox denial findings
- Observability read models for dashboard summaries, eval-run rows, regression
  rows, trace links, Playground handoffs, and sandbox status
- Local `/observability` API endpoint over EvalRunPlan/EvalLog artifacts
- Dashboard, Evaluate, Observe, Improve, and Settings routes in the existing
  no-build frontend shell
- Repeated-run and cross-variant regression review rows over EvalRunPlan and
  EvalLog artifacts
- Failure taxonomy, status, and triage filters in the Evaluate view
- Local triage note persistence linked to EvalTask, EvalLog, sample, and trace
  IDs
- Local JSON/CSV export links for eval logs, aggregates, and scanner findings
- Improve-view handoff from selected regressions and failed eval rows into
  Playground comparison context
- Local improvement notes, rerun queue entries, and candidate promotion
  artifacts
- Guardrail reminders before promoted candidates are used for real adapter
  execution
- CLI validators and local server command
- pytest coverage for schema, runner, persistence, and API contracts

Real OpenClaw execution is available only behind explicit opt-in and guardrail
checks. Additional real shell, browser, desktop, non-local network, and model
execution remain out of scope until future runner modules explicitly bind solver
and sandbox provider policy.

## Primary User Story

As a developer building a desktop AI agent, I want to compare agent variants,
inspect failed task traces, and replay those failures in a local Playground
where I can change prompts, models, parameters, and tool policies, so that I can
improve the agent safely before shipping it into real local workflows.

## Target Product Loop

```text
Run eval task or A/B experiment
  -> find failed or regressed task query
  -> open hierarchical trace
  -> inspect spans: planner -> model call -> tool call -> desktop action -> validator
  -> open the same task in Playground
  -> change model, prompt, parameters, or tool policy
  -> replay locally
  -> save as candidate variant
  -> run full A/B again
```

## Core Product Surfaces

### Experiments

Experiments compare two or more agent variants across deterministic local
taskpacks.

Examples:

| Variant A | Variant B | Question |
|---|---|---|
| Baseline prompt | Candidate prompt | Did the new prompt improve completion? |
| Llama local model | Qwen local model | Which local model performs better? |
| Full tool access | Restricted tool policy | Does restriction reduce safety failures? |
| Single planner | Planner plus critic | Does reflection help or add latency? |
| Current OpenClaw config | Candidate OpenClaw config | Is the new config safe enough to ship? |

### Eval Tasks

Eval tasks are the next core product object. They make a single reusable unit
out of sample selection, solver adapter, scorer set, limits, and logging.

Expected workflows:

| ID | Workflow | Result |
|---|---|---|
| ET-1 | Define eval task | TaskPack samples, solver, scorers, and limits are bound in one config |
| ET-2 | Run one eval task | Each sample produces an eval log with trace, scores, artifacts, and status |
| ET-3 | Run eval set | One or more eval tasks run across variants with resumable local state |
| ET-4 | Analyze eval logs | Per-sample and aggregate tables can be exported |
| ET-5 | Replay failed sample | Playground opens from an eval log, not only from raw run artifacts |

### Playground

The Playground is an interactive local lab for one selected task query or a
small task batch.

Expected workflows:

| ID | Workflow | Result |
|---|---|---|
| PG-1 | Replay failed task | Same task opens with original prompt/model/settings |
| PG-2 | Change model | Local provider/model can be switched |
| PG-3 | Change prompt | System, developer, and task messages can be edited |
| PG-4 | Change parameters | Temperature, top-p, max tokens, step budget, and timeout can be changed |
| PG-5 | Change tool policy | Filesystem, shell, browser, MCP, and desktop tools can be enabled or restricted |
| PG-6 | Run one-off replay | Edited config runs against the same task workspace |
| PG-7 | Compare outputs | Baseline and Playground results can be compared |
| PG-8 | Save candidate | Current Playground state becomes a new experiment variant |
| PG-9 | Save Playground View | Prompt, model, params, selected task, result, and trace snapshot are stored locally |

### Trace Visualizer

The trace visualizer lets the user click a task run and inspect hierarchical
telemetry.

Target trace shape:

```text
task_run
|-- setup_workspace
|-- agent_session
|   |-- planner_call
|   |   `-- llm_call
|   |-- tool_call: list_files
|   |-- tool_call: read_file
|   |-- desktop_action: open_app
|   |-- shell_action: mv todo.txt action-items.txt
|   |-- llm_call: summarize
|   `-- tool_call: write_file
|-- validators
|   |-- file_exists
|   |-- file_not_exists
|   `-- semantic_summary_check
`-- scoring
```

Expected workflows:

| ID | Workflow | Result |
|---|---|---|
| TR-1 | Inspect failed task | Failed task opens with trace context |
| TR-2 | See hierarchy | Parent and child spans are visible |
| TR-3 | Find slow step | Spans can be sorted or filtered by duration |
| TR-4 | Find tool misuse | Tool calls, unsafe actions, and path violations are filterable |
| TR-5 | Inspect model I/O | LLM spans expose captured messages, params, and response previews |
| TR-6 | Inspect desktop action | Desktop spans can show before/after screenshots when captured |
| TR-7 | Inspect validator | Validator spans show expected and observed state |
| TR-8 | Open in Playground | The selected task/span can be replayed with the same context |
| TR-9 | Compare traces | A and B trace trees can be compared side by side |
| TR-10 | Export trace | Trace JSON/JSONL can be exported locally |

### Arize-Inspired GUI/UX Direction

The next GUI implementation should organize the product around a compact
desktop-agent debugging cockpit:

| Surface | Local UX |
|---|---|
| Observe | Trace/session explorer showing what the agent did, including span hierarchy, tool calls, artifacts, errors, screenshots when available, and timing |
| Evaluate | Eval dashboard showing run status, pass rates, scorer results, regressions, score deltas, task metadata, and trace links |
| Improve | Playground-linked prompt and harness iteration with before/after comparison and candidate promotion |
| Learn | Local run history, failure clusters, saved review notes, and rerun queues for future eval design |

GUI implementation acceptance criteria:

- The first screen is the workbench dashboard, not a marketing or landing page.
- Navigation exposes Observe, Evaluate, and Improve as stable top-level modes.
- Eval views join EvalTask, EvalLog, trace, scorer, and artifact references.
- Trace/session drilldown supports span filters, status filters, details, and
  links back to eval samples.
- Regression review highlights changed outcomes, score deltas, and failing
  samples across variants or repeated runs.
- Improve workflows hand failed or regressed samples to the Playground with the
  original prompt, model, parameters, tool policy, trace, and scorer context.
- UI assets are served locally by the FastAPI app; no external fonts, scripts,
  CDNs, images, or cloud telemetry are required.

Implementation critique and revision:

- Avoid a surface-level clone of Arize marketing language. The local workbench
  should use a dense engineering dashboard with compact tables, trace drawers,
  filters, and side-by-side comparison panels.
- Do not start Module 17 by choosing a frontend framework. Start by defining
  stable backend read models over EvalTask, EvalLog, trace, scorer, and artifact
  data, then render them through the existing no-build shell.
- Keep Observe, Evaluate, and Improve connected by IDs. A failing row should
  carry enough references to open the trace, inspect scorer evidence, and launch
  Playground replay without manual lookup.
- Treat local privacy state as visible product state. Any workflow that would
  use a real adapter, external endpoint, or non-local artifact should show the
  relevant guardrail status before execution is prepared.

Module 17 information architecture:

| Route/mode | Primary content | Required data |
|---|---|---|
| Dashboard | Recent eval runs, health summary, regression count, slowest samples, and next rerun queue | Eval run summaries, aggregate scores, timestamps, run status |
| Evaluate | Dense eval-run table with task/sample, variant, solver, scorer status, score deltas, latency, artifacts, and trace links | EvalTask, EvalLog, scorer results, artifact index |
| Observe | Trace/session drilldown with span tree, filters, selected-span details, timing, artifacts, and scorer evidence | Trace envelope, span details, linked EvalLog IDs |
| Improve | Playground handoff and before/after comparison for prompt, parameters, tool policy, harness, and candidate variant metadata | Playground View, prompt object, eval sample, trace context |
| Settings | Local paths, privacy posture, adapter availability, and feature flags | Config discovery, guardrail status, optional dependency status |

## Module Roadmap

### Module 1: Schema and Validation Contracts

Status: implemented.

Scope:

- Experiment schema
- Prompt Object schema
- Metric registry
- Playground and tracing config contracts
- CLI validators

Non-goals:

- No task execution
- No agent process launching
- No trace capture
- No UI backend

### Module 2: Task Schema and Validators

Status: implemented.

Goal: define deterministic taskpacks that experiments can reference.

Deliverables:

- `TaskPack` schema
- `TaskCase` schema
- Workspace fixture references
- Declarative setup contract
- Declarative validator registry
- CLI validator for taskpacks
- Demo taskpack for desktop basics
- Tests for every new schema rule

Recommended files:

```text
src/agent_ab/schemas/task.py
taskpacks/desktop_basics/tasks.yaml
taskpacks/desktop_basics/workspaces/
tests/test_module2_tasks.py
```

Minimum taskpack shape:

```yaml
id: desktop_basics
version: 1
description: Deterministic local file tasks.
tasks:
  - id: rename_todo
    query: Rename notes/todo.txt to notes/action-items.txt.
    workspace:
      fixture: workspaces/rename_todo
    validators:
      - type: file_exists
        path: notes/action-items.txt
      - type: file_not_exists
        path: notes/todo.txt
```

Module 2 acceptance criteria:

- `agent-ab validate-taskpack taskpacks/desktop_basics/tasks.yaml` succeeds.
- Unknown taskpack keys fail with Pydantic `extra="forbid"`.
- Task IDs are stable identifiers and unique within a taskpack.
- Validator types are known or use a `custom.` prefix.
- Validator paths are relative to the task workspace unless explicitly modeled
  otherwise.
- Setup and validator contracts remain declarative; the CLI validates config,
  not task success.
- The demo experiment can reference the demo taskpack without requiring a
  runner.

### Module 3: Telemetry Schema and Trace Store

Status: implemented.

Goal: define typed spans and local trace persistence before implementing real
agent execution.

Deliverables:

- Trace envelope schema
- Span schema with parent/child relationships
- Typed detail payloads for model calls, tool calls, desktop actions, shell
  actions, validators, and scoring
- JSONL trace writer contract
- SQLite trace index contract
- Tests for trace shape and ID relationships

### Module 4: Runner Core and Mock Adapter

Status: implemented.

Goal: execute deterministic mock runs first, then add real adapters.

Deliverables:

- Runner interface
- Run workspace lifecycle
- Mock adapter that emits deterministic spans
- Validator executor for Module 2 contracts
- Metric result model
- Local artifact writer

Module 4 is the first module allowed to execute tasks.

### Module 5: Local Backend API

Status: implemented.

Goal: expose local experiment, taskpack, trace, and artifact data to a UI.

Deliverables:

- FastAPI app bound to localhost
- Experiment and taskpack discovery endpoints
- Run listing and result summary endpoints
- Trace retrieval endpoints
- API response model tests

### Module 6: Playground Backend

Status: implemented.

Goal: support one-off local replay and candidate variant creation.

Deliverables:

- Playground run request and response schemas
- Prompt/model/parameter override handling
- Tool policy override handling
- Playground View persistence
- Deterministic mock replay API endpoints
- Playground View listing and retrieval endpoints

### Module 7: Frontend Shell

Status: implemented.

Goal: provide the first local workbench UI.

Deliverables:

- Experiment list
- Task result table
- Run summary
- Trace and Playground navigation frame
- Basic local API loading, empty, and error states

### Module 8: Trace Visualizer UI

Status: implemented.

Goal: inspect hierarchical telemetry.

Deliverables:

- Trace tree
- Span detail panes
- Waterfall timing view
- Span kind/status filters
- Keyboard-selectable span rows

### Module 9: Playground UI

Status: implemented.

Goal: make prompt/model/tool iteration ergonomic.

Deliverables:

- Prompt editor
- Model and parameter controls
- Tool policy controls
- Replay action
- Candidate save action
- Local prompt/defaults loading
- Rendered result pane
- Saved candidate restore flow

### Module 10: OpenClaw Adapter

Status: implemented.

Goal: prepare a real OpenClaw-style desktop-agent run through the workbench contracts, with execution held behind later guardrails.

Deliverables:

- OpenClaw CLI adapter
- Adapter-specific config translation
- Trace ingestion or wrapping strategy
- Demo OpenClaw taskpack
- Prepared-run CLI command
- OpenClaw command plan with generated config path

### Module 11: Guardrails and Sandbox

Status: implemented.

Goal: enforce local safety boundaries during real runs.

Deliverables:

- Allowed-path enforcement
- Blocked command enforcement
- Localhost-only network policy
- Timeout enforcement
- Secret redaction checks
- OpenClaw command-plan guardrail integration

### Module 12: Demo and Reporting

Status: implemented.

Goal: provide an end-to-end local demo.

Deliverables:

- Demo script
- Demo data
- JSON and CSV export
- README update
- Known limitations
- Reporting CLI commands

### Module 13: Inspect-Inspired Eval Core

Status: implemented.

Goal: add explicit evaluation primitives underneath A/B comparison, reports, and
Playground replay.

Implemented seed-generation slice:

- Strict expert seed metadata models
- Built-in public Mercor APEX role/sample-task seeds
- O*NET occupation and Task ID metadata
- NBER Appendix A.4-style GWA/IWA/DWA classification metadata
- `agent-ab generate-seed-taskpack` command
- Example `taskpacks/mercor_apex_expert_seeded/tasks.yaml`
- Tests for schema strictness, deterministic generation, and CLI output

Implemented eval-core slice:

- `EvalTask` schema
- `EvalSample` normalization from TaskPack tasks
- Solver reference contract that validates registered or `custom.` adapters
- Scorer reference contract for validators, metrics, trace checks, and `custom.`
  scorers
- Eval log envelope that references run config, trace, scores, artifacts, and errors
- `agent-ab validate-eval-task` command
- Example `evals/desktop_basics_eval.yaml`
- Example `evals/mercor_apex_seed_eval.yaml`
- Focused tests for schema strictness, sample selection, scorer references, and log shape

Non-goals:

- No new real agent execution beyond existing explicit OpenClaw gate
- No cloud model grader dependency
- No frontend rewrite

### Module 14: Eval Runner and Eval Sets

Status: implemented.

Goal: plan one or more eval tasks across variants with local resumability before
adding broader execution paths.

Implemented deliverables:

- Eval run planner
- Eval set config
- Resume and skip-completed behavior over local logs
- Failure threshold and limit handling
- Aggregate status summaries
- `agent-ab validate-eval-set` command
- `agent-ab plan-eval-set` command with optional JSON plan output
- Example `evals/local_eval_set.yaml`
- Focused tests for EvalSet validation, deterministic planning, resume behavior,
  invalid completed-log handling, and CLI output

Non-goals:

- No new real agent execution path
- No model grader runtime
- No frontend changes

### Module 15: Analysis and Scanner Layer

Status: implemented.

Goal: make eval logs queryable for reports, comparisons, and qualitative review.

Implemented deliverables:

- Per-sample JSON/CSV export
- Per-eval aggregate export
- Trace and transcript scanner contract
- Failure taxonomy hooks
- Rule-based local scanner over EvalLog status, errors, scorer failures, and
  missing trace references
- `agent-ab export-eval-logs` command
- `agent-ab export-eval-aggregates` command
- `agent-ab scan-eval-logs` command
- Focused tests for EvalRunPlan loading, per-sample rows, aggregate rows,
  scanner findings, and CLI exports

Deferred:

- UI/API endpoints over eval logs move to Module 17 after read models stabilize.

### Module 16: Sandbox Provider Interface

Status: implemented.

Goal: separate safety policy from execution backend so real adapters can use
the same guardrail contract.

Implemented deliverables:

- Strict sandbox provider schema with separate workspace, command, network,
  timeout, artifact, and provider identity policy
- Local workspace provider example in `sandboxes/local_workspace.yaml`
- Optional Docker provider contract without adding Docker as a dependency or
  launching containers
- RunLimits-to-provider and provider-to-RunLimits mapping helpers over existing
  guardrails
- Tool approval and denial event schemas that serialize into
  `EvalLog.metadata["sandbox_events"]`
- Scanner taxonomy support for sandbox denial findings

### Module 17: Arize-Inspired Observability and Eval GUI

Status: implemented.

Goal: turn EvalTask and EvalLog data into a local observe/evaluate/improve
cockpit.

Implemented deliverables:

- Workbench dashboard with eval health summary, recent runs, pass-rate trends,
  and regression counts
- No-build UI modes for Dashboard, Evaluate, Observe, Improve, and
  Settings
- Evaluate mode with run tables, task/sample rows, scorer outcomes, status,
  latency, artifact links, trace links, and sandbox denial badges
- Observe mode with trace/session drilldown reusing the local trace visualizer
- Improve mode handoff from failed or errored samples into Playground replay
- Backend read models for dashboard summaries, eval-run rows, regression rows,
  trace links, Playground handoff payloads, artifact references, and sandbox status
- `/observability` API endpoint with optional EvalRunPlan path selection and
  newest-plan discovery under the runs root
- Local-only UI assets and API calls served from the existing FastAPI backend
- OpenInference/OpenTelemetry-compatible labels where they clarify spans and
  trace relationships

Non-goals:

- No managed observability dependency
- No external frontend assets or telemetry calls
- No frontend framework rewrite until EvalTask and EvalLog contracts stabilize

### Module 18: Eval Analysis and Regression Review UI

Status: implemented.

Goal: make repeated eval runs easier to compare, triage, and export from the
local GUI.

Implemented deliverables:

- Repeated-run regression rows over the latest two EvalLogs for the same
  EvalTask, sample, solver, and variant
- Cross-variant regression rows comparing each worse latest variant against the
  best latest variant for the same EvalTask, sample, and solver
- Regression table with previous score, current score, delta, trace link,
  sample metadata, solver, variant, and comparison kind
- Failure taxonomy, current-status, and triage-status filters
- Saved triage notes stored locally under the runs root and linked to EvalTask,
  EvalLog, sample, trace, failure taxonomy, status, and tags
- Backend export endpoint and UI links for local JSON/CSV eval logs,
  aggregates, and scanner findings
- Responsive review layout using the existing no-build frontend shell

### Module 19: Prompt and Harness Improvement Loop UI

Status: implemented.

Goal: close the local loop between eval failures, Playground experiments, and
candidate variants.

Implemented deliverables:

- Selected regression and failed-eval handoff into the Improve view and
  Playground form
- Prompt/result comparison context for selected regression, failure, or saved
  Playground View
- Local improvement notes linked to EvalTask, EvalLog, trace, triage note, and
  Playground View IDs
- Rerun queue entries seeded from selected regressions or failed eval rows
- Candidate promotion artifacts that snapshot Playground request and Prompt
  Object JSON without mutating source configs
- Guardrail reminders shown beside improvement actions before real adapter work
  is prepared

### Module 20: Guarded Eval Execution Harness

Status: planned.

Goal: bind EvalRunPlan samples to solver adapters through explicit sandbox
provider policy while preserving deterministic mock execution and keeping real
adapter execution opt-in.

Deliverables:

- EvalRunPlan execution command that can run selected samples through the
  deterministic mock solver first
- Solver adapter dispatch contract shared by mock, prepared OpenClaw, generic
  CLI, and future local HTTP adapters
- Sandbox provider resolution for each EvalTask or sample run
- Per-sample EvalLog writing compatible with Modules 15 through 19
- Resume, skip-completed, and max-failure handling during execution
- Dry-run and plan-only modes that show commands, workspaces, and guardrail
  decisions before any real adapter is invoked
- Tests proving real OpenClaw, shell, browser, desktop, model, and non-local
  network execution remain blocked unless explicitly policy-gated

## Metric Strategy

The metric registry is AgentEval-inspired and local-first, but Module 13 should
reshape metric calculation around Inspect-style scorers. Metrics remain the
aggregate names; scorers are the executable units that produce scores.

Metric groups:

- Outcome: `task_success`, `validator_pass_rate`
- Reasoning: `plan_quality`, `plan_adherence`, `step_efficiency`
- Tool use: `tool_success`, `tool_call_accuracy`, `tool_argument_correctness`,
  `tool_sequence_adherence`, `forbidden_tool_calls`
- Workflow: `workflow_executor_order`, `workflow_edge_coverage`
- Performance/cost: `latency_ms`, `first_token_latency_ms`, `step_count`,
  `token_count`, `estimated_cost`
- Stochastic/model comparison: `stochastic_success_rate`,
  `stochastic_stddev`, `model_comparison_rank`
- Trace/replay: `trace_replay_determinism`
- DAG/root cause: `dag_node_quality`, `error_propagation_depth`,
  `root_cause_accuracy`, `failure_taxonomy_label`
- Safety/security: `safety_violation_count`, `red_team_security_score`
- RAG: `rag_faithfulness`, `rag_relevance`, `rag_context_precision`,
  `rag_context_recall`
- Memory: `memory_retention`, `memory_reach_back`,
  `memory_temporal_reasoning`, `memory_noise_resilience`,
  `memory_reducer_fidelity`
- Responsible AI: `toxicity`, `bias`, `misinformation_risk`

The goal is not to clone AgentEval or Inspect AI. The goal is to preserve useful
evaluation concepts while adapting them to offline desktop-agent traces.

## Offline and Privacy Requirements

- Configs, traces, artifacts, and reports stay on the local machine.
- Network access is disabled by default.
- Localhost model providers are allowed only when declared.
- Task workspaces must be isolated from the user's real files.
- Trace capture must support secret redaction.
- Cloud services may be supported later only as optional adapters, never as
  required infrastructure.

## Open Questions

- Should task validators support only static filesystem checks in Module 2, or
  should semantic validators be declared now and implemented later?
- Should task fixtures be copied from directories, generated from inline file
  declarations, or both?
- Should path policy be shared between experiment limits, prompt tools, and
  task validators through one common schema?
- Should metric results attach directly to spans, task runs, or both?
- Should EvalTask configs remain separate files long term, or should experiments
  later reference eval sets that point to them?
- Should scorer results be stored as span details, eval-log top-level scores, or both?
- Which Module 17 GUI data should be precomputed by the backend versus derived
  in the browser from EvalLog and trace API responses?

## Immediate Next Work

Proceed to Module 20: Guarded Eval Execution Harness. Module 19 now closes the
local review loop from selected regressions to Playground comparison, local
notes, rerun queues, and promotion artifacts. The next module should bind
EvalRunPlan samples to solver execution through sandbox provider policy, with
mock execution first and all real adapter execution staying explicitly gated.

Module 20 acceptance criteria:

- EvalRunPlan samples can execute through the deterministic mock solver and
  write EvalLogs without changing existing analysis contracts.
- Execution can be limited by eval task, sample ID, solver, variant, max
  failures, and resume state.
- Sandbox provider policy is resolved before each sample run and recorded in
  EvalLog metadata.
- Dry-run mode reports planned workspaces, commands, and guardrail decisions
  without launching adapters.
- Real OpenClaw, shell, browser, desktop, model, and non-local network paths
  remain blocked unless explicitly enabled by policy and call-site opt-in.
- Module 15 reports, Module 17 observability, Module 18 review, and Module 19
  improvement flows can consume the generated EvalLogs.

Completed post-MVP hardening:

- Aggregate A/B comparison reports across repeated variants.
- Safety-gated real OpenClaw execution behind explicit opt-in.
- Browser-level UI tests that run when Playwright is available.
- PR/release workflow documentation and PR template.
- Windows/POSIX command/path edge-case coverage and real-adapter trace alias handling.
- Expert seed TaskPack generation from public Mercor APEX, O*NET, and NBER
  Appendix A.4 metadata.

## References

- Mercor APEX Agents leaderboard: https://www.mercor.com/apex/apex-agents-leaderboard/
- O*NET program: https://www.dol.gov/agencies/eta/onet
- O*NET Task Statements data dictionary: https://www.onetcenter.org/dictionary/30.3/text/task_statements.html
- NBER Working Paper 34255, Appendix A.4: https://www.nber.org/system/files/working_papers/w34255/w34255.pdf
- Inspect AI repository: https://github.com/UKGovernmentBEIS/inspect_ai
- Inspect AI docs: https://inspect.aisi.org.uk/
- Arize homepage: https://arize.com/
- Arize Quickstart Guide: https://arize.com/resource/arize-quickstart-guide/
- AgentEval .NET toolkit: https://agenteval.dev/
- AgentEval DAG paper: https://arxiv.org/abs/2604.23581
