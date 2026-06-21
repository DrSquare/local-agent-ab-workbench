# Codex / Coding Agent Instructions

This repository is designed to be friendly for Codex-style coding agents.

## Project goal

Build a local offline A/B testing and debugging workbench for desktop AI agents.

## Current module

Modules 1 through 3 implement only schemas, validation, and local persistence contracts:

- Experiment config
- Prompt Object config
- TaskPack config
- TaskCase config
- Declarative task validator contracts
- Trace envelope and span schemas
- JSONL trace writer contract
- SQLite trace index contract
- AgentEval-inspired metric registry
- Playground config contract
- Tracing config contract
- CLI validators

Do not add real agent execution inside Modules 1, 2, or 3.

Module 4 adds only deterministic local mock execution:

- Run workspace copy lifecycle
- Local validator executor
- Deterministic mock adapter
- Trace artifact writing through Module 3 contracts

Do not add real OpenClaw, shell, browser, desktop, network, or model execution inside Module 4.

Module 5 adds only a local read-only FastAPI backend:

- Localhost-only `agent-ab serve` command
- Experiment discovery endpoint
- TaskPack discovery endpoint
- Run summary and artifact listing endpoints
- Trace JSONL retrieval endpoint

Do not add real agent execution, non-local binding, cloud service calls, or UI code inside Module 5.

Module 6 adds only Playground backend contracts and deterministic mock replay:

- Playground run request and response schemas
- Prompt, model, parameter, and tool-policy override validation
- One-off replay through the deterministic mock runner
- Local Playground View JSON persistence
- Playground API endpoints

Do not add real model calls, OpenClaw execution, shell/browser/desktop automation, or UI code inside Module 6.

Module 7 adds only the first local frontend shell:

- No-build static HTML/CSS/JS served by FastAPI at `/ui`
- Experiment, TaskPack, run, trace, and Playground navigation frame
- Local API fetches only; no external assets or cloud calls
- Basic empty, loading, and error states

Do not add real model calls, OpenClaw execution, shell/browser/desktop automation, external frontend services, or desktop packaging inside Module 7.

Module 8 expands only the trace visualizer UI:

- Expandable/collapsible trace tree
- Span detail pane for typed payloads
- Timing-oriented waterfall view
- Span kind/status filters
- Frontend tests for trace UI assets and local trace payloads

Do not add real model calls, OpenClaw execution, shell/browser/desktop automation, external frontend services, desktop packaging, or graph dependencies inside Module 8.

Module 9 expands only the Playground UI and local defaults loading:

- Read-only Playground defaults endpoint for selected experiment variants
- Prompt message editor
- Model and generation parameter controls
- Tool-policy override controls
- Replay and save-candidate actions
- Rendered replay result and saved candidate restore flow

Do not add real model calls, OpenClaw execution, shell/browser/desktop automation, external frontend services, desktop packaging, or frontend build tooling inside Module 9.

Module 10 adds OpenClaw adapter preparation only:

- OpenClaw CLI config translation
- OpenClaw command planning
- Isolated prepared-run workspace and config artifacts
- OpenClaw trace payload wrapping into workbench trace contracts
- Demo OpenClaw adapter experiment and taskpack

Do not execute the OpenClaw CLI, shell, browser, desktop automation, non-local network calls, or real model calls by default inside Module 10. Real execution must wait for Module 11 guardrails.

Module 11 adds guardrails and sandbox policy helpers:

- Allowed-path and blocked-path enforcement
- Blocked command enforcement
- Localhost-only endpoint checks when network is disabled
- Timeout checks against experiment limits
- Secret redaction for text and nested trace payloads
- OpenClaw command-plan guardrail checks

Do not enable unattended real desktop automation or non-local network execution inside Module 11. Use guardrail helpers before adding future execution paths.

Module 12 adds demo and reporting artifacts:

- Repeatable local deterministic demo helper and script
- JSON and CSV run report export
- Demo/reporting CLI commands
- Known limitations documentation

After Module 12, prefer post-MVP hardening, integration tests, and real-adapter execution only when explicitly safety-gated.

Post-MVP hardening adds:

- Aggregate task/variant comparison reports for repeated local runs
- Guarded OpenClaw execution helper requiring explicit `allow_execute=True`
- Optional Playwright browser tests for the local `/ui` flow
- PR/release workflow documentation in `docs/WORKFLOW.md`
- Windows/POSIX command/path edge-case coverage and real adapter trace alias handling

## Coding rules

- Use Python 3.11+.
- Use Pydantic v2 for schemas.
- Keep YAML configs human-readable.
- Reject unknown config keys with `extra="forbid"`.
- Keep the system offline-first.
- Do not add cloud-only dependencies.
- Write tests for every new schema rule.

## Commands

```bash
python -m pip install -e '.[dev]'
pytest
agent-ab validate-experiment experiments/demo_openclaw_prompt_ab.yaml
agent-ab validate-taskpack taskpacks/desktop_basics/tasks.yaml
agent-ab prepare-openclaw-run experiments/demo_openclaw_adapter.yaml B openclaw_rename_todo
agent-ab run-demo --output-root demo_output
agent-ab export-runs demo_output/runs --output demo_output/reports/runs.csv --format csv
agent-ab compare-runs demo_output/runs --output demo_output/reports/comparison.json
agent-ab serve --host 127.0.0.1 --port 8765
agent-ab metrics
```

## Next recommended task

Choose the next product milestone after reviewing `PLAN.md` and `sprint.md`.
