# Sprint Tracker

## Current Sprint

Module 2: task schema and validators.

## Status

| Area | Status | Notes |
|---|---|---|
| Module 1 schemas | Done | Experiment, Prompt Object, metric registry, Playground config, tracing config, and CLI validators are committed. |
| Module 1 hardening | Done | Duplicate YAML keys, local endpoints, prompt templates, baseline variants, and tool policy conflicts are covered by tests. |
| TDD test folder | Done | `tests_tdd/` is available for opt-in red tests. |
| Module 2 task contracts | Done | Taskpack schema, task case schema, validator contracts, demo taskpack, CLI validation, and tests are implemented. |

## Module 2 Acceptance Criteria

- `agent-ab validate-taskpack taskpacks/desktop_basics/tasks.yaml` succeeds.
- Unknown taskpack keys fail with Pydantic `extra="forbid"`.
- Task IDs are stable identifiers and unique within a taskpack.
- Validator types are known or use a `custom.` prefix.
- Validator paths are portable relative workspace paths.
- Setup and validator contracts remain declarative; no task execution is added.
- The demo experiment references a validated taskpack without requiring a runner.

## Working Rules

- Keep the base install offline-first and small.
- Do not add cloud-only dependencies.
- Do not add real agent execution before the runner module.
- Add tests for every new schema rule.
- Move durable passing tests into `tests/`; keep `tests_tdd/` for temporary red tests only.

## Next Sprint Candidate

Module 3: telemetry schema and trace store.
