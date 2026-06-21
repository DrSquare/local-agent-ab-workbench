# Sprint Tracker

## Current Sprint

Module 3: telemetry schema and trace store.

## Status

| Area | Status | Notes |
|---|---|---|
| Module 1 schemas | Done | Experiment, Prompt Object, metric registry, Playground config, tracing config, and CLI validators are committed. |
| Module 1 hardening | Done | Duplicate YAML keys, local endpoints, prompt templates, baseline variants, and tool policy conflicts are covered by tests. |
| TDD test folder | Done | `tests_tdd/` is available for opt-in red tests. |
| Module 2 task contracts | Done | Taskpack schema, task case schema, validator contracts, demo taskpack, CLI validation, and tests are implemented. |
| Module 3 trace contracts | Done | Trace envelope, typed span details, JSONL writer, SQLite index, and tests are implemented. |

## Module 3 Acceptance Criteria

- Trace envelope and span schemas validate parent/child integrity.
- Typed details exist for model calls, tool calls, desktop actions, shell actions, validators, and scoring.
- Trace JSONL round trip is covered by tests.
- SQLite trace index is covered by tests.
- Trace contracts remain persistence-only; no agent execution is added.

## Working Rules

- Keep the base install offline-first and small.
- Do not add cloud-only dependencies.
- Do not add real agent execution before the runner module.
- Add tests for every new schema rule.
- Move durable passing tests into `tests/`; keep `tests_tdd/` for temporary red tests only.

## Next Sprint Candidate

Module 4: runner core and deterministic mock adapter.
