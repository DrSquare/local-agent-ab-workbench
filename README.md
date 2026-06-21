# Local Agent A/B Workbench

A local, offline-first A/B testing and debugging workbench for desktop AI agents such as OpenClaw-style local assistants.

This repository currently implements:

- **Module 1: Experiment + Prompt Object schema**
- **Module 2: TaskPack schema + validator contracts**
- **Module 3: Telemetry schema + trace store contracts**
- **Module 4: Runner core + deterministic mock adapter**
- **Module 5: Local FastAPI backend**
- **Module 6: Playground backend**
- **Module 7: Frontend shell**
- **Module 8: Trace visualizer UI**
- **Module 9: Playground UI**
- **Module 10: OpenClaw adapter preparation**
- **Module 11: Guardrails and sandbox policy**
- **Module 12: Demo and reporting**

## What the implemented modules include

- Experiment YAML schema for A/B agent evaluations
- Prompt Object YAML schema for Playground-editable model/prompt/tool bundles
- AgentEval-inspired metric registry
- Playground and tracing config contracts
- TaskPack and TaskCase YAML schemas
- Declarative task validator contracts
- Trace envelope and span schemas
- Typed trace detail payloads for model, tool, desktop, shell, validator, and scoring spans
- Local JSONL trace writer and SQLite trace index helpers
- Local validator executor for TaskPack contracts
- Deterministic mock adapter and run workspace lifecycle
- Local read-only API for experiment, taskpack, run, and trace discovery
- Playground replay request/response contracts
- Deterministic one-off Playground replay through the mock runner
- Local Playground View persistence
- No-build local frontend shell served from `/ui`
- Expandable trace tree, span detail pane, filters, and timing waterfall
- Playground prompt editor, model/parameter controls, tool-policy controls, replay/save actions, and result pane
- OpenClaw CLI config translation, command planning, prepared-run artifacts, and trace wrapping
- Guardrail helpers for paths, commands, endpoints, timeouts, and secret redaction
- Local demo runner plus JSON and CSV run report exports
- Aggregate task/variant comparison reports across repeated local runs
- Safety-gated OpenClaw execution helper requiring explicit opt-in
- CLI validation commands
- Example OpenClaw-style experiment and prompt configs
- Example desktop basics taskpack
- pytest coverage for schema validation and prompt rendering

## Install locally

```bash
cd local-agent-ab-workbench
python -m pip install -e '.[dev]'
```

For the local API without dev tools:

```bash
python -m pip install -e '.[server]'
```

## Validate the demo experiment

```bash
agent-ab validate-experiment experiments/demo_openclaw_prompt_ab.yaml
```

## Validate a prompt object

```bash
agent-ab validate-prompt prompts/baseline_openclaw.yaml
```

## Validate a taskpack

```bash
agent-ab validate-taskpack taskpacks/desktop_basics/tasks.yaml
```

## Run a deterministic mock task

```bash
agent-ab run-mock-task taskpacks/desktop_basics/tasks.yaml rename_todo \
  --run-root runs/mock \
  --run-id mock.rename_todo.demo
```

## Prepare an OpenClaw adapter run

```bash
agent-ab prepare-openclaw-run experiments/demo_openclaw_adapter.yaml B openclaw_rename_todo \
  --run-root runs/openclaw \
  --run-id openclaw.rename_todo.demo
```

This writes an isolated workspace and `openclaw_config.yaml` plus a command plan. It does not execute the OpenClaw CLI by default.
Execution is available only through the guarded adapter helper with an explicit `allow_execute=True` opt-in.

## Run the local demo and export reports

```bash
agent-ab run-demo --output-root demo_output
agent-ab export-runs demo_output/runs --output demo_output/reports/runs.csv --format csv
agent-ab compare-runs demo_output/runs --output demo_output/reports/comparison.json
```

## Serve the local API

```bash
agent-ab serve --host 127.0.0.1 --port 8765
```

The server command rejects non-local bind hosts.

Useful local API paths include:

```text
GET  /ui
GET  /experiments
GET  /taskpacks
GET  /runs
GET  /playground/defaults
POST /playground/runs
GET  /playground/views
```

## Render a prompt

```bash
agent-ab render-prompt prompts/baseline_openclaw.yaml \
  --var task_query='Rename notes/todo.txt to notes/action-items.txt' \
  --var workspace_path=/tmp/agent-ab/workspace
```

## List built-in metrics

```bash
agent-ab metrics
agent-ab metrics --category tool
```

## Run tests

```bash
pytest
```

Browser-level UI tests are included as optional coverage and skip automatically unless Playwright and a Chromium browser are installed.

## TDD tests

Use `tests_tdd/` for tests that may be red while designing a new behavior. The
default `pytest` command runs only the stable suite in `tests/`.

```bash
pytest tests_tdd
```

Move durable passing tests into `tests/` when the behavior is implemented.

## Directory map

```text
agent-ab-workbench/
  docs/
    KNOWN_LIMITATIONS.md
    PLAN.md
    TECH_STACK.md
  experiments/
    demo_openclaw_adapter.yaml
    demo_openclaw_prompt_ab.yaml
  prompts/
    baseline_openclaw.yaml
    candidate_playground.yaml
  taskpacks/
    desktop_basics/
      tasks.yaml
      workspaces/
    openclaw_demo/
      tasks.yaml
      workspaces/
  src/agent_ab/
    adapters/
      openclaw.py
    cli.py
    config.py
    guardrails.py
    playground.py
    reporting.py
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
  scripts/
    run_local_demo.py
  tests/
    test_module1_schemas.py
    test_module2_tasks.py
    test_module3_traces.py
    test_module4_runner.py
    test_module5_server.py
    test_module6_playground.py
    test_module7_frontend.py
    test_module8_trace_ui.py
    test_module9_playground_ui.py
    test_module10_openclaw_adapter.py
    test_module11_guardrails.py
    test_module12_reporting.py
  tests_tdd/
    README.md
```

## Next module

All planned MVP modules are implemented. Next work should focus on post-MVP hardening, aggregate reporting, and safety-gated real adapter execution.
