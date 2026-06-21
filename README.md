# Local Agent A/B Workbench

A local, offline-first A/B testing and debugging workbench for desktop AI agents such as OpenClaw-style local assistants.

This repository currently implements:

- **Module 1: Experiment + Prompt Object schema**
- **Module 2: TaskPack schema + validator contracts**
- **Module 3: Telemetry schema + trace store contracts**
- **Module 4: Runner core + deterministic mock adapter**

## What Module 1 includes

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
- CLI validation commands
- Example OpenClaw-style experiment and prompt configs
- Example desktop basics taskpack
- pytest coverage for schema validation and prompt rendering

## Install locally

```bash
cd local-agent-ab-workbench
python -m pip install -e '.[dev]'
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
    schemas/
      common.py
      experiment.py
      metrics.py
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
  tests_tdd/
    README.md
```

## Next module

Module 5 should add a local FastAPI backend for experiment, taskpack, run, trace, and artifact discovery.
