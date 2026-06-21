# Local Agent A/B Workbench

A local, offline-first A/B testing and debugging workbench for desktop AI agents such as OpenClaw-style local assistants.

This repository currently implements **Module 1: Experiment + Prompt Object schema**.

## What Module 1 includes

- Experiment YAML schema for A/B agent evaluations
- Prompt Object YAML schema for Playground-editable model/prompt/tool bundles
- AgentEval-inspired metric registry
- Playground and tracing config contracts
- CLI validation commands
- Example OpenClaw-style experiment and prompt configs
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
  src/agent_ab/
    cli.py
    config.py
    schemas/
      common.py
      experiment.py
      metrics.py
      prompt_object.py
  tests/
    test_module1_schemas.py
  tests_tdd/
    README.md
```

## Next module

Module 2 should add the task schema and validators so the experiment schema can point to real taskpacks.
