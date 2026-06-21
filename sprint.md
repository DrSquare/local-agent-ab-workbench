# Sprint Tracker

## Current Sprint

Post-MVP hardening: reporting aggregates and execution gates.

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

## Post-MVP Acceptance Criteria

- Repeated local runs can be grouped by task and variant.
- Comparison reports can be exported as JSON and CSV.
- CLI commands support comparison report export.
- Real OpenClaw execution remains blocked unless explicitly opted in.
- Execution-gate tests do not invoke a real desktop agent.
- Browser-level UI tests skip cleanly when Playwright is unavailable.
- PR and release workflow docs list required verification and risk review items.

## Working Rules

- Keep the base install offline-first and small.
- Do not add cloud-only dependencies.
- Do not add real agent execution beyond deterministic mock behavior before adapter modules.
- Add tests for every new schema rule.
- Move durable passing tests into `tests/`; keep `tests_tdd/` for temporary red tests only.

## Next Sprint Candidate

Real-adapter trace edge-case review.
