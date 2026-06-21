# Local Offline Agent A/B Workbench Product Plan

## Mission

Build a local, offline-first A/B testing and debugging workbench for desktop AI
agents such as OpenClaw-style local assistants.

The workbench should help a developer compare agent variants, inspect failed
task traces, replay failures in a local Playground, and save improved prompt,
model, and tool configurations as new candidates without sending private
desktop data to a cloud service.

## Planning Critique

The original plan had the right product loop, but it mixed long-term runtime and
UI deliverables into the current schema-only stage. That made the next step less
clear and risked adding agent execution before the repository has task, trace,
and result contracts.

This revision keeps the product vision, but makes module boundaries explicit:
Modules 1 and 2 define contracts only. Real agent execution starts later, after
taskpacks, validators, telemetry, and storage schemas are stable.

## Current State

Module 1 is implemented and intentionally limited to schemas and validation:

- Experiment config
- Prompt Object config
- AgentEval-inspired metric registry
- Playground config contract
- Tracing config contract
- CLI validators for experiments, prompts, prompt rendering, and metrics
- pytest coverage for schema validation rules

Module 1 must not grow real agent execution. Any execution-facing fields should
remain declarative contracts until the runner module is introduced.

## Primary User Story

As a developer building a desktop AI agent, I want to compare agent variants,
inspect failed task traces, and replay those failures in a local Playground
where I can change prompts, models, parameters, and tool policies, so that I can
improve the agent safely before shipping it into real local workflows.

## Target Product Loop

```text
Run A/B experiment
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

Status: next.

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

Goal: expose local experiment, taskpack, trace, and artifact data to a UI.

Deliverables:

- FastAPI app bound to localhost
- Experiment and taskpack discovery endpoints
- Run listing and result summary endpoints
- Trace retrieval endpoints
- Playground request/response contracts

### Module 6: Playground Backend

Goal: support one-off local replay and candidate variant creation.

Deliverables:

- Playground run request and response schemas
- Prompt/model/parameter override handling
- Tool policy override handling
- Playground View persistence
- Result diff model

### Module 7: Frontend Shell

Goal: provide the first local workbench UI.

Deliverables:

- Experiment list
- Task result table
- Run summary
- Trace and Playground navigation frame

### Module 8: Trace Visualizer UI

Goal: inspect hierarchical telemetry.

Deliverables:

- Trace tree
- Span detail panes
- Waterfall timing view
- A/B trace comparison
- Export action

### Module 9: Playground UI

Goal: make prompt/model/tool iteration ergonomic.

Deliverables:

- Prompt editor
- Model and parameter controls
- Tool policy controls
- Replay action
- Candidate save action

### Module 10: OpenClaw Adapter

Goal: run a real OpenClaw-style desktop agent through the workbench contracts.

Deliverables:

- OpenClaw CLI adapter
- Adapter-specific config translation
- Trace ingestion or wrapping strategy
- Demo OpenClaw taskpack

### Module 11: Guardrails and Sandbox

Goal: enforce local safety boundaries during real runs.

Deliverables:

- Allowed-path enforcement
- Blocked command enforcement
- Localhost-only network policy
- Timeout enforcement
- Secret redaction checks

### Module 12: Demo and Reporting

Goal: provide an end-to-end local demo.

Deliverables:

- Demo script
- Demo data
- JSON and CSV export
- README update
- Known limitations

## Metric Strategy

The metric registry is AgentEval-inspired and local-first. Module 1 defines
metric names and metadata only. Later modules compute metric results from
validators, trace spans, and artifacts.

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

The goal is not to clone AgentEval. The goal is to preserve useful evaluation
concepts while adapting them to offline desktop-agent traces.

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

## Immediate Next Work

1. Add `TaskPack`, `TaskCase`, and validator schemas.
2. Add a `validate-taskpack` CLI command.
3. Add `taskpacks/desktop_basics/tasks.yaml` with a small fixture.
4. Add Module 2 tests for strict keys, unique IDs, path rules, and validator
   type validation.
5. Update the demo experiment only as needed to point at the validated taskpack.

## References

- Arize Quickstart Guide: https://arize.com/resource/arize-quickstart-guide/
- AgentEval .NET toolkit: https://agenteval.dev/
- AgentEval DAG paper: https://arxiv.org/abs/2604.23581
