# Local Offline Agent A/B Workbench Tech Stack

## Stack Critique

The previous stack document mixed current dependencies with later MVP choices.
That made FastAPI, React, SQLite, Tauri, and adapter work look equally current
even though the repository is still in Module 1 schema validation.

This revision separates the stack into:

- Current core stack used by Module 1.
- Module 2 stack needed for taskpack contracts.
- Deferred runtime, backend, and frontend choices.
- Dependency rules that preserve the offline-first goal.

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

## Current Core Stack

This is the base stack that remains active through Module 5.

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
| Packaging | Tauri | Later | Desktop packaging after local web UI is stable |

The first frontend should be a workbench, not a landing page.

React, Vite, and TanStack remain reasonable later choices if the frontend grows
past the no-build shell.

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
| Post-MVP | Aggregate comparison exports, explicit OpenClaw execution opt-in, optional Playwright browser tests |
| Frontend | Core flows with Playwright as the UI becomes interactive enough to need browser automation |

## File Layout Direction

Near-term target:

```text
agent-ab-workbench/
  docs/
    PLAN.md
    TECH_STACK.md
  experiments/
    demo_openclaw_prompt_ab.yaml
  prompts/
    baseline_openclaw.yaml
    candidate_playground.yaml
  taskpacks/
    desktop_basics/
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
    schemas/
      common.py
      experiment.py
      metrics.py
      playground.py
      prompt_object.py
      run.py
      task.py
      trace.py
    runner.py
    trace_store.py
    validators.py
  tests/
    test_module1_schemas.py
    test_module2_tasks.py
    test_module3_traces.py
    test_module4_runner.py
    test_module5_server.py
    test_module6_playground.py
    test_module7_frontend.py
```

Later modules can add `runner/`, `tracing/`, `storage/`, `playground/`, and
`frontend/` directories when their contracts are ready.

## References

- Arize Quickstart Guide: https://arize.com/resource/arize-quickstart-guide/
- AgentEval .NET toolkit: https://agenteval.dev/
- AgentEval DAG paper: https://arxiv.org/abs/2604.23581
