# Local Agent Evaluation Workbench

A local, offline-first evaluation and debugging workbench for desktop AI agents such as OpenClaw-style local assistants.

The roadmap is now Inspect-inspired: TaskPacks become local datasets, agent adapters act as solvers, validators and scorers grade outcomes, trace artifacts become eval logs, and guardrails/sandboxes protect real execution. A/B comparison remains an important workflow, but it is treated as one evaluation mode rather than the whole product.

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
- **Module 13A: Expert seed TaskPack generation**
- **Module 13B: EvalTask core contracts**
- **Module 14: EvalSet planning**
- **Module 15: EvalLog analysis and scanner exports**
- **Module 16: Sandbox provider contracts**
- **Module 17: Observability and eval GUI read models**
- **Module 18: Eval analysis and regression review UI**
- **Module 19: Prompt and harness improvement loop UI**
- **Module 20: Guarded EvalRunPlan execution harness**

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
- Mercor APEX-inspired expert seed generation with O*NET and NBER Appendix A.4 metadata
- EvalTask, EvalSample, solver reference, scorer reference, and EvalLog schemas
- EvalTask validation against referenced TaskPacks and sample selections
- EvalSet validation, deterministic EvalRunPlan generation, resume/skip
  detection, and plan JSON export
- EvalRunPlan/EvalLog loading, per-sample reports, aggregate reports, and local
  scanner findings with failure taxonomy categories
- Sandbox provider schema for local workspace and optional Docker contract
  policies
- RunLimits-to-sandbox mapping over existing guardrail helpers
- EvalLog-compatible sandbox approval and denial events
- Scanner classification for sandbox denial events
- Observability read models for dashboard summaries, eval rows, regression
  rows, trace links, Playground handoffs, and sandbox status
- Local `/observability` API endpoint
- Dashboard, Evaluate, Observe, Improve, and Settings routes in the no-build UI
- Regression review rows for repeated-run and cross-variant eval comparisons
- Failure taxonomy, status, and triage filters in the Evaluate view
- Local triage notes linked to EvalTask, EvalLog, sample, and trace IDs
- Local JSON/CSV export links for eval logs, aggregates, and scanner findings
- Improve-view context handoff from selected regressions and failed eval rows
- Local improvement notes, rerun queue entries, and candidate promotion artifacts
- Guardrail reminders before promoted candidates are used for real adapter work
- Guarded EvalRunPlan dry-run and execution harness for deterministic mock rows
- Per-sample EvalLog writing with sandbox provider metadata and approval or
  denial events
- Unsupported adapter blocking for custom, OpenClaw, shell, browser, desktop,
  model, generic CLI, and non-local network execution paths
- CLI validation commands
- Example OpenClaw-style experiment and prompt configs
- Example desktop basics taskpack
- Example expert seed taskpack
- pytest coverage for schema validation and prompt rendering

## Product direction

The workbench evaluation core is modeled around reusable components:

- `EvalTask`: binds a TaskPack sample set to a solver/agent adapter and scorer set.
- `Dataset/Sample`: normalizes desktop tasks into repeatable local samples.
- `Solver/Agent`: references deterministic mock, OpenClaw, and future CLI/local HTTP agents behind one contract.
- `Scorer`: references validators, trace checks, metrics, and optional model-graded checks as comparable scores.
- `EvalLog`: makes run traces, scores, config, and artifacts queryable and replayable.
- `Sandbox`: keeps real tool and desktop execution behind explicit local policy.

This keeps the workbench compatible with Inspect-style evaluation thinking without making `inspect-ai` a core dependency.

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

## Validate an eval task

```bash
agent-ab validate-eval-task evals/desktop_basics_eval.yaml
agent-ab validate-eval-task evals/mercor_apex_seed_eval.yaml
```

## Validate and plan an eval set

```bash
agent-ab validate-eval-set evals/local_eval_set.yaml
agent-ab plan-eval-set evals/local_eval_set.yaml \
  --run-root runs/evals \
  --output runs/evals/local_module14_eval_set/plan.json
```

## Run a guarded eval plan

```bash
agent-ab run-eval-plan runs/evals/local_module14_eval_set/plan.json
agent-ab run-eval-plan runs/evals/local_module14_eval_set/plan.json \
  --execute \
  --sample-id rename_todo
```

The command defaults to dry-run. `--execute` runs only deterministic mock solver
rows and writes EvalLogs. Unsupported adapters are blocked and recorded as
sandbox denial EvalLogs when execution is requested.

## Export eval analysis reports

```bash
agent-ab export-eval-logs runs/evals/local_module14_eval_set/plan.json
agent-ab export-eval-aggregates runs/evals/local_module14_eval_set/plan.json
agent-ab scan-eval-logs runs/evals/local_module14_eval_set/plan.json
```

## Validate a sandbox provider

```bash
agent-ab validate-sandbox-provider sandboxes/local_workspace.yaml
```

## Generate an expert seed taskpack

```bash
agent-ab generate-seed-taskpack \
  --output taskpacks/mercor_apex_expert_seeded/tasks.yaml
agent-ab validate-taskpack taskpacks/mercor_apex_expert_seeded/tasks.yaml
```

The built-in seeds use public Mercor APEX role/sample-task facts, O*NET occupation
and task IDs, and NBER Appendix A.4-style IWA classification metadata. The full
APEX-Agents dataset is gated, so the generator does not crawl it and marks the
generated tasks as requiring human review or licensed task artifacts before real
benchmark use.

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
GET  /observability
GET  /observability/export
GET  /triage-notes
POST /triage-notes
GET  /improvements
POST /improvements/notes
POST /improvements/rerun-queue
POST /improvements/promotions
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

## PR and release workflow

See [docs/WORKFLOW.md](docs/WORKFLOW.md) for the feature-branch, PR, verification, and release checklist.

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
  .github/
    PULL_REQUEST_TEMPLATE.md
  docs/
    INSPECT_ALIGNMENT.md
    KNOWN_LIMITATIONS.md
    PLAN.md
    TECH_STACK.md
    WORKFLOW.md
  evals/
    desktop_basics_eval.yaml
    local_eval_set.yaml
    mercor_apex_seed_eval.yaml
  experiments/
    demo_openclaw_adapter.yaml
    demo_openclaw_prompt_ab.yaml
  prompts/
    baseline_openclaw.yaml
    candidate_playground.yaml
  sandboxes/
    local_workspace.yaml
  taskpacks/
    desktop_basics/
      tasks.yaml
      workspaces/
    mercor_apex_expert_seeded/
      tasks.yaml
      workspaces/
    openclaw_demo/
      tasks.yaml
      workspaces/
  src/agent_ab/
    adapters/
      openclaw.py
    analysis.py
    cli.py
    config.py
    eval_runner.py
    eval_execution.py
    improvement.py
    guardrails.py
    observability.py
    playground.py
    reporting.py
    sandbox.py
    server.py
    task_seed_generation.py
    static/
      ui/
        index.html
        app.css
        app.js
    schemas/
      common.py
      eval.py
      experiment.py
      metrics.py
      playground.py
      prompt_object.py
      run.py
      sandbox.py
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
    test_module20_eval_execution.py
    test_module7_frontend.py
    test_module8_trace_ui.py
    test_module9_playground_ui.py
    test_module10_openclaw_adapter.py
    test_module11_guardrails.py
    test_module12_reporting.py
    test_module13_eval_core.py
    test_module13_seed_generation.py
    test_module14_eval_runner.py
    test_module15_analysis_scanner.py
    test_module16_sandbox_provider.py
    test_module17_observability_gui.py
    test_module18_regression_review_ui.py
    test_module19_improvement_loop_ui.py
  tests_tdd/
    README.md
```

## Next module

Proceed to Module 20 by binding EvalRunPlan samples to a guarded solver
execution harness while keeping real adapter execution explicit and policy-gated.
