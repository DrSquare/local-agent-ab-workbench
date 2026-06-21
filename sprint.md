# Sprint Tracker

## Current Sprint

Module 10: OpenClaw Adapter.

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

## Module 10 Acceptance Criteria

- OpenClaw CLI variants can be prepared into isolated run workspaces.
- Prompt, model, parameter, tool, task, limit, and tracing contracts are translated to an OpenClaw-style YAML config.
- Command plans replace or append the generated config path and validate the `openclaw` executable.
- OpenClaw span/event payloads can be wrapped into the workbench trace contract.
- A demo OpenClaw adapter experiment and taskpack are available.
- Real CLI execution remains disabled by default until guardrails are implemented.

## Working Rules

- Keep the base install offline-first and small.
- Do not add cloud-only dependencies.
- Do not add real agent execution beyond deterministic mock behavior before adapter modules.
- Add tests for every new schema rule.
- Move durable passing tests into `tests/`; keep `tests_tdd/` for temporary red tests only.

## Next Sprint Candidate

Module 11: Guardrails and Sandbox.
