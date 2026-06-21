# Sprint Tracker

## Current Sprint

Module 9: Playground UI.

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

## Module 9 Acceptance Criteria

- Playground loads local prompt/model/task defaults for a selected experiment variant.
- Prompt messages, declared variables, extra prompt variables, model settings, generation parameters, and tool-policy overrides are editable.
- Replay and save-candidate actions submit to the Module 6 local replay endpoint.
- Replay results show status, run, trace, model, metrics, and rendered messages.
- Saved candidates can be selected and restored into the editor.
- The UI remains no-build, local-only, and free of external editor/runtime dependencies.
- No real OpenClaw, shell, browser, desktop, non-local network, or model execution is added.

## Working Rules

- Keep the base install offline-first and small.
- Do not add cloud-only dependencies.
- Do not add real agent execution beyond deterministic mock behavior before adapter modules.
- Add tests for every new schema rule.
- Move durable passing tests into `tests/`; keep `tests_tdd/` for temporary red tests only.

## Next Sprint Candidate

Module 10: OpenClaw Adapter.
