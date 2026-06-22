# Local Offline Agent Evaluation Workbench Tech Stack

## Stack Critique

The previous stack document mixed current dependencies with later MVP choices.
That made FastAPI, React, SQLite, Tauri, and adapter work look equally current
when the repository was still in its schema-only stage.

Post-MVP review against Inspect AI adds a stronger architectural critique:
the stack needs a stable evaluation core, not just experiment/reporting
surfaces. Inspect's task/dataset/solver/scorer/log/sandbox pattern is the
reference shape for that core.

Review against Arize adds a GUI critique: once EvalTask and EvalLog contracts
exist, the frontend should be planned as a local observe/evaluate/improve
workbench rather than a set of unrelated utility pages.

This revision separates the stack into:

- Current core stack used by implemented modules.
- Implemented taskpack, backend, trace, Playground, reporting, and adapter
  choices.
- Deferred runtime, backend, and frontend choices.
- Dependency rules that preserve the offline-first goal.
- Planned evaluation-core and GUI components inspired by Inspect AI and Arize.

## Design Principles

- Local first: configs, traces, artifacts, and reports are stored on the user's
  machine.
- Offline by default: external network access is disabled unless explicitly
  allowed for a task or adapter.
- Contract first: schemas are stabilized before runner and UI code consumes
  them.
- Trace first: every real run should eventually produce hierarchical telemetry
  suitable for debugging and replay.
- Playground first: prompt/model/tool changes should be testable interactively
  before becoming experiment variants.
- Adapter based: OpenClaw is a target adapter, but the harness should support
  mock, generic CLI, local HTTP, and future desktop-agent adapters.
- Evaluation-component based: TaskPacks, solvers, scorers, logs, analysis, and
  sandboxes should have explicit contracts.
- Logs first: every run should produce a structured eval log that can be
  inspected, replayed, compared, and scanned.
- Observe/evaluate/improve first: the GUI should make trace inspection,
  regression review, and prompt/harness iteration feel like one local loop.

## Inspect-Inspired Architecture Map

| Evaluation layer | Local workbench object | Stack choice |
|---|---|---|
| Task | `EvalTask` schema | Pydantic v2 + YAML |
| Dataset | TaskPack plus normalized samples | Existing TaskPack YAML, expert seed generator, future sample selector |
| Sample | TaskCase + workspace fixture + metadata | Existing task schema plus planned `EvalSample` view |
| Solver/Agent | Adapter contract | Python protocol/class with mock, OpenClaw, generic CLI, local HTTP implementations |
| Scorer | Validator and trace scoring pipeline | Python scorer registry plus metric metadata |
| Eval log | Run config + trace + scores + artifacts | JSON/JSONL files with SQLite index |
| Eval set | Multi-task and multi-variant plan | YAML config plus resumable local state |
| Sandbox | Execution provider | Local workspace provider first, Docker/provider extras later |
| Analysis | Reports and scanner outputs | Built-in JSON/CSV first, optional dataframe extra later |

Do not add `inspect-ai` as a required dependency. The workbench adopts
compatible boundaries while preserving this project's local desktop-agent
contracts and YAML authoring model.

## Arize-Inspired GUI Stack Map

Arize is a product and UX reference, not a dependency. The local GUI should
borrow the observe/evaluate/improve organization while staying offline-first and
served from the local FastAPI app.

| GUI layer | Local stack choice | Notes |
|---|---|---|
| Workbench shell | Existing static HTML/CSS/JS | Keep no-build until the UI needs a framework |
| Observe | Trace/session explorer over local trace APIs | Span tree, status/kind filters, details, timing, artifacts |
| Evaluate | Eval dashboard over EvalTask/EvalLog APIs | Run status, scorer outcomes, pass rates, regressions, score deltas |
| Improve | Playground-linked comparison views | Prompt, params, tool policy, harness, and candidate promotion |
| Learn/review | Local notes and failure clusters | JSON/SQLite-backed initially; no cloud account needed |
| Visualization | CSS/SVG first, optional chart library later | Avoid chart dependencies until aggregate views require them |
| Standards | OpenInference/OpenTelemetry-compatible naming | Use familiar span/trace/session terms without proprietary formats |

Do not add Arize-hosted products, Phoenix, hosted scripts, telemetry SDKs,
external fonts, or CDN assets as required dependencies for the GUI.

## Module 17 Frontend Architecture

Module 17 should stay on the existing static frontend unless the implementation
proves the no-build shell is a bottleneck. The first goal is stable data flow,
not framework migration.

| Concern | Initial choice | Review checkpoint |
|---|---|---|
| Routing | Hash routes in `app.js` | Revisit only if nested route state becomes unmaintainable |
| Data access | Small typed fetch wrappers around local APIs | Backend responses should be fixture-testable without a browser |
| View models | Backend read models for dashboard, eval rows, trace links, and Playground handoff | Avoid rebuilding aggregate logic in browser state |
| Components | Plain HTML templates plus CSS utility classes | Split into `components/` only after duplication appears |
| Tables | Native tables with sticky headers, compact density, and filter controls | Consider TanStack only if sorting/filtering becomes too complex |
| Visualizations | CSS/SVG bars and badges | Add a chart library only for real aggregate visualization needs |
| Accessibility | Keyboard navigation, visible focus, semantic tables, status text | Playwright checks should cover keyboard-critical flows |
| Responsiveness | Laptop-first dense layout, then narrow responsive fallback | No overlapping controls or hidden action buttons |
| Offline proof | Tests assert local asset loading and no external network dependencies | Required before any GUI module is marked done |

## Current Core Stack

This is the base stack that remains active for config validation, CLI workflows,
local APIs, and docs-backed roadmap work.

| Layer | Choice | Status | Reason |
|---|---|---|---|
| Language | Python 3.11+ | Active | Modern typing, fast iteration, broad local automation ecosystem |
| Schemas | Pydantic v2 | Active | Strict validation for human-edited YAML contracts |
| Config files | YAML | Active | Easy to read, diff, review, and edit |
| YAML parser | PyYAML | Active | Small dependency already used by config loaders |
| CLI | Typer + Rich | Active | Local validation commands with readable output |
| Tests | pytest | Active dev dependency | Fast schema, runner, and API coverage |
| Lint target | Ruff | Active dev dependency | Simple formatting/lint baseline |

Current runtime dependencies should stay small:

```text
pydantic
PyYAML
typer
rich
```

Current development dependencies:

```text
pytest
ruff
fastapi
uvicorn
httpx
```

## Module 1 Implementation Scope

Implemented now:

```text
src/agent_ab/schemas/common.py
src/agent_ab/schemas/metrics.py
src/agent_ab/schemas/prompt_object.py
src/agent_ab/schemas/experiment.py
src/agent_ab/config.py
src/agent_ab/cli.py
experiments/demo_openclaw_prompt_ab.yaml
prompts/baseline_openclaw.yaml
prompts/candidate_playground.yaml
tests/test_module1_schemas.py
```

Module 1 does not execute agents. It validates contracts that later modules will
use.

## Module 2 Technical Direction

Module 2 adds only taskpack contracts and validators. It does not add a runner,
backend server, UI, database, or model provider integration.

Implemented additions:

| Need | Choice | Reason |
|---|---|---|
| Task schema | Pydantic v2 | Reuse strict schema pattern |
| Taskpack files | YAML | Human-readable deterministic task definitions |
| Validator registry | Enum plus `custom.` escape hatch | Mirrors metric registry behavior |
| Path handling | `pathlib.Path` plus relative path validation | Keeps workspace references portable |
| CLI | `agent-ab validate-taskpack` | Matches existing validation commands |
| Tests | pytest | One test per new schema rule |

Implemented files:

```text
src/agent_ab/schemas/task.py
taskpacks/desktop_basics/tasks.yaml
taskpacks/desktop_basics/workspaces/
tests/test_module2_tasks.py
```

Module 2 validates that:

- Unknown keys fail.
- Task IDs are valid and unique.
- Validator types are known or `custom.*`.
- Validator paths are relative to the task workspace.
- Workspace fixtures are declared in a portable way.
- The demo experiment can point to a taskpack without executing it.

## Module 5 Backend Stack

These choices are active for the local read-only backend.

| Layer | Choice | Earliest module | Reason |
|---|---|---|---|
| API | FastAPI | Module 5 | Local UI/backend API for experiments, taskpacks, runs, and traces |
| Local server | Uvicorn | Module 5 | FastAPI runtime, localhost-only CLI binding |
| Artifact store | Filesystem JSON/JSONL | Module 3 or 4 | Inspectable offline artifacts |
| Structured store | SQLite via stdlib or lightweight wrapper | Module 3 or 4 | Portable local run/query store |
| Analytics store | DuckDB optional | Later | Useful only if SQLite/query performance becomes limiting |
| Serialization | Pydantic JSON mode | Module 3+ | Keeps persisted contracts aligned with schemas |

The backend stack is exposed through the `server` extra and included in the
`dev` extra for API tests.

## Deferred Frontend Stack

These choices are for the UI phase, not the schema modules.

| Layer | Choice | Earliest module | Reason |
|---|---|---|---|
| App shell | No-build HTML/CSS/JS served by FastAPI | Module 7 | First local workbench shell without Node or registry setup |
| Components | Native HTML controls plus project CSS | Module 7 | Accessible baseline with no external assets |
| Tables | Native tables | Module 7 | Good enough for the first experiment/run/task views |
| State/query | Small browser state module | Module 7 | Local API cache and selected run/trace state without extra dependencies |
| Prompt editor | Native textareas and structured controls | Module 9 | No-build prompt editing without Node or external editor assets |
| Playground result view | Native detail lists and rendered-message panels | Module 9 | Replay feedback without adding chart/editor dependencies |
| Trace tree | Native expandable tree in the static shell | Module 8 | Hierarchical spans are tree-shaped initially |
| Timeline | CSS waterfall bars | Module 8 | Span duration visualization without canvas or graph dependencies |
| Eval dashboard | Static shell dashboard backed by local EvalLog APIs | Module 17 | Arize-inspired Evaluate view without a framework rewrite |
| Regression review | Native tables with sticky columns and dense filters | Module 18 | Prefer readable local data grids before adding table dependencies |
| Prompt/harness comparison | Playground-linked comparison panels | Module 19 | Improve loop over local configs and rerun queues |
| Packaging | Tauri | Later | Desktop packaging after local web UI is stable |

The first frontend should be a workbench, not a landing page.

React, Vite, and TanStack remain reasonable later choices if the frontend grows
past the no-build shell. A framework migration should happen only after the
EvalTask/EvalLog API shape is stable and the static shell becomes harder to
maintain than replace.

## Model and Agent Integration

| Need | MVP choice | Timing |
|---|---|---|
| Local models | Ollama-compatible registry contract | Already in schema |
| Mock testing | Deterministic mock adapter | Module 4 |
| First real agent target | OpenClaw CLI adapter preparation and trace wrapping | Module 10 |
| Generic support | CLI and local HTTP adapter interface | Module 4+ |
| Tool layer | MCP-aware tool specs and telemetry attributes | Contract now, runtime later |

Do not add model SDKs or agent SDKs to the core dependency set until a runner
module needs them. Prefer adapter-specific optional extras.

## Module 13 Evaluation Core Stack

These choices are active for the implemented Module 13 contract layer.

| Need | Choice | Reason |
|---|---|---|
| Expert seed generation | Pydantic v2 models + deterministic Python generator | Converts public expert-task seeds into normal TaskPack YAML without scraping |
| Source metadata | Mercor APEX public facts + O*NET Task IDs + NBER IWA mapping | Makes provenance and taxonomy review explicit |
| EvalTask schema | Pydantic v2 | Reuse strict config rules and `extra="forbid"` |
| EvalTask files | YAML | Reviewable configs for local eval authoring |
| Sample selection | TaskPack path plus explicit include/exclude lists | Keeps existing taskpacks reusable |
| Solver contract | Python adapter protocol plus registry | Separates run planning from adapter execution |
| Scorer contract | Python scorer registry | Separates validation/scoring from metrics aggregation |
| Eval logs | JSON/JSONL plus SQLite index | Human-inspectable logs with local query support |
| Analysis export | JSON/CSV initially | No new analytics dependency for Module 13 |
| Inspect compatibility | Conceptual only | Avoids pulling cloud/model-provider assumptions into core |

Implemented files:

```text
evals/desktop_basics_eval.yaml
evals/mercor_apex_seed_eval.yaml
src/agent_ab/schemas/eval.py
tests/test_module13_eval_core.py
```

Module 14 should consume these contracts for planning and resumable local state
rather than introducing new task, sample, solver, scorer, or log shapes.

## Safety and Sandbox Stack

The schema already models safety intent. Runtime enforcement comes later.

| Area | Contract now | Runtime later |
|---|---|---|
| Workspace isolation | `$RUN_WORKSPACE` allowed path | Disposable per-run workspace |
| Filesystem safety | Allowed and blocked path lists | Path resolution and enforcement |
| Shell safety | Blocked command list | Command parser and policy engine |
| Network safety | `allow_network` and localhost allowlist | Adapter-level network policy |
| Timeouts | Per-task and Playground timeout fields | Process and tool timeout enforcement |
| Artifacts | Local artifact root | JSONL/filesystem writers |
| Redaction | `redact_secrets` flag | Secret scanning and redacted previews |

Safety enforcement should be tested on Windows and POSIX path formats before
real desktop-agent runs are enabled.

## AgentEval-Inspired Metric Registry

The Python schema uses a built-in metric registry adapted from common
agent-evaluation patterns:

- Tool usage validation
- Workflow evaluation
- Stochastic pass rates
- Model comparison
- Performance SLAs
- Trace record/replay
- Red-team checks
- RAG metrics
- Memory metrics
- Responsible AI metrics
- DAG step-level root-cause analysis

Module 1 defines metric metadata only. Metric calculation should be added after
task validators and trace spans exist.

## Dependency Policy

- Keep the base install offline-friendly and small.
- Add runtime dependencies only when the module that needs them is implemented.
- Prefer optional extras for backend, frontend tooling, adapter SDKs, and
  analytics.
- Do not add cloud-only dependencies to core.
- Prefer local file formats that can be inspected without the app.
- Keep schema modules free of UI and runner imports.

Suggested future extras:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6", "fastapi>=0.115", "uvicorn>=0.30", "httpx>=0.27"]
server = ["fastapi>=0.115", "uvicorn>=0.30"]
analytics = ["duckdb"]
analysis = ["pandas>=2.0"]
```

Adapter extras should be introduced only when the corresponding adapter is
implemented.

## Testing Policy

For every new schema rule, add a focused pytest case.

Coverage expectations by phase:

| Phase | Test focus |
|---|---|
| Module 1 | Strict keys, prompt rendering, metric selection, experiment cross-field validation |
| Module 2 | Task ID uniqueness, validator type validation, workspace fixture validation, path rules |
| Module 3 | Span parent/child integrity, trace serialization, typed detail payloads, JSONL/SQLite persistence |
| Module 4 | Mock adapter determinism, validator execution, workspace lifecycle, artifact writing |
| Backend | API response models, local-only binding assumptions, error shapes |
| Module 6 | Playground request validation, mock replay output, view persistence |
| Module 7 | Frontend shell routes, local-only assets, API endpoint wiring |
| Module 8 | Trace filters, span detail rendering, timing waterfall, keyboard span selection |
| Module 9 | Playground defaults endpoint, editor controls, replay/save payloads, result rendering |
| Module 10 | OpenClaw config translation, command planning, trace wrapping, prepare CLI |
| Module 11 | Path policy, blocked command policy, endpoint checks, timeout bounds, secret redaction |
| Module 12 | Demo helper, JSON/CSV report export, reporting CLI, known limitations docs |
| Post-MVP | Aggregate comparison exports, explicit OpenClaw execution opt-in, optional Playwright browser tests, PR/release workflow docs, guardrail edge-case tests |
| Module 13 | Expert seed schema/generation, EvalTask strict schema, sample selection, solver/scorer references, eval-log contract |
| Module 17 | Observe/evaluate/improve navigation, eval dashboard summaries, trace/session drilldown, local-only assets, responsive dashboard layout |
| Module 18 | Regression tables, score deltas, failure filters, export links, saved triage notes |
| Module 19 | Prompt/harness comparison, Playground handoff, candidate promotion, rerun queue behavior |
| Frontend | Core flows with Playwright as the UI becomes interactive enough to need browser automation |

Module 17 fixture expectations:

- API tests cover dashboard summaries, eval-run rows, regression rows, trace
  links, and Playground handoff payloads.
- Browser tests cover Dashboard -> Evaluate -> Observe -> Improve navigation.
- Frontend tests use local fixture data; no test should require a live model,
  real OpenClaw run, external network call, or hosted asset.
- Screenshot checks should cover at least one desktop viewport and one narrow
  viewport once the Module 17 UI is implemented.

## File Layout Direction

Near-term target:

```text
agent-ab-workbench/
  docs/
    INSPECT_ALIGNMENT.md
    PLAN.md
    TECH_STACK.md
    WORKFLOW.md
  evals/
    desktop_basics_eval.yaml
    mercor_apex_seed_eval.yaml
  experiments/
    demo_openclaw_prompt_ab.yaml
  prompts/
    baseline_openclaw.yaml
    candidate_playground.yaml
  taskpacks/
    desktop_basics/
      tasks.yaml
      workspaces/
    mercor_apex_expert_seeded/
      tasks.yaml
      workspaces/
  src/agent_ab/
    cli.py
    config.py
    playground.py
    server.py
    static/
      ui/
        index.html
        app.css
        app.js
        components/
        views/
    schemas/
      common.py
      eval.py
      experiment.py
      metrics.py
      playground.py
      prompt_object.py
      run.py
      task.py
      trace.py
    runner.py
    task_seed_generation.py
    trace_store.py
    validators.py
    evals.py
  tests/
    test_module1_schemas.py
    test_module2_tasks.py
    test_module3_traces.py
    test_module4_runner.py
    test_module5_server.py
    test_module6_playground.py
    test_module7_frontend.py
    test_module13_seed_generation.py
    test_module13_eval_core.py
    test_module17_observability_gui.py
```

Later modules can add `runner/`, `tracing/`, `storage/`, `playground/`, and
`frontend/` directories when their contracts are ready.

## References

- Mercor APEX Agents leaderboard: https://www.mercor.com/apex/apex-agents-leaderboard/
- O*NET program: https://www.dol.gov/agencies/eta/onet
- O*NET Task Statements data dictionary: https://www.onetcenter.org/dictionary/30.3/text/task_statements.html
- NBER Working Paper 34255, Appendix A.4: https://www.nber.org/system/files/working_papers/w34255/w34255.pdf
- Arize homepage: https://arize.com/
- Arize Quickstart Guide: https://arize.com/resource/arize-quickstart-guide/
- AgentEval .NET toolkit: https://agenteval.dev/
- AgentEval DAG paper: https://arxiv.org/abs/2604.23581
