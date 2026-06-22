# Inspect AI Reference Review

## Reference Pattern

Inspect AI frames evaluations as composable tasks. A task combines a dataset of samples, a solver or agent that produces output, and a scorer that grades the output. Inspect also treats logs, analysis, sandboxing, limits, and extension points as first-class parts of the evaluation lifecycle.

This workbench should adopt that shape while staying local-first and desktop-agent-specific.

Reference material:

- Inspect AI repository: https://github.com/UKGovernmentBEIS/inspect_ai
- Inspect AI documentation: https://inspect.aisi.org.uk/
- LLM-friendly Inspect guide: https://inspect.aisi.org.uk/llms-guide.txt

## Current Approach Critique

The current workbench has strong local foundations:

- Strict YAML contracts for experiments, prompts, tasks, traces, guardrails, and reports.
- Deterministic TaskPack fixtures and validators.
- Local trace storage and UI inspection.
- Mock and OpenClaw adapter preparation.
- Offline-first defaults and explicit execution gates.
- EvalTask, EvalSet, EvalLog, analysis, and sandbox provider contracts.
- Local observability read models and UI routes over eval logs, traces, handoffs, and sandbox status.

The weak point is architectural vocabulary. The repo currently centers on A/B experiments and Playground replay, but those are workflows built on top of a deeper evaluation model. Without explicit `Dataset`, `Sample`, `Solver`, `Scorer`, and `EvalLog` concepts, future adapters and reports will keep growing around ad hoc run artifacts.

## Adopted Mapping

| Inspect concept | Workbench adaptation |
|---|---|
| Task | `EvalTask` binding samples, solver adapter, scorer set, limits, and log policy |
| Dataset | `TaskPack` plus normalized sample records |
| Sample | `TaskCase` with workspace fixture, input query, target expectations, and metadata |
| Solver/Agent | Adapter interface for mock, OpenClaw, generic CLI, local HTTP, and future desktop agents |
| Scorer | Validator and trace-aware scoring pipeline |
| Eval log | Trace envelope plus run config, scores, artifacts, and transcript-style events |
| Eval set | Multi-task, multi-variant run plan with resumable local state |
| Sandbox | Disposable workspace plus path, command, endpoint, timeout, and redaction policy |
| Analysis | Local reports, comparisons, scans, and data-frame-like exports |

## Deliberate Differences

- Do not add `inspect-ai` as a core dependency yet. The domain here is local desktop-agent debugging, not general LLM benchmark execution.
- Keep YAML configs human-readable for non-Python users.
- Keep the no-build UI until the interaction complexity justifies a frontend toolchain.
- Keep real execution opt-in and local-only by default.
- Prefer adapter compatibility over adopting Inspect's Python decorator authoring model immediately.

## Required Enhancements

1. Add an `EvalTask` schema that references a TaskPack or sample selection, a solver adapter, scorer IDs, limits, and logging options.
2. Normalize TaskPack tasks into sample records with stable IDs and metadata.
3. Rename or wrap validators as scorers so scoring is not tied only to filesystem checks.
4. Promote run artifacts into an eval log contract that includes config, transcript, trace, scores, artifacts, and errors.
5. Add analysis APIs that can produce per-sample and per-eval tables from local logs.
6. Define a sandbox provider contract before adding additional real adapters. Done in Module 16.

## Success Criteria

- A user can run an eval task across one or more variants and get per-sample scores plus aggregate metrics.
- Existing A/B comparison and Playground replay continue to work as workflows over eval logs.
- Real adapters cannot execute without an explicit solver and sandbox policy.
- Logs are sufficiently structured for UI inspection, CSV/JSON export, and future scanner workflows.
- Dashboard and eval GUI views consume read models derived from local logs rather than cloud telemetry.
