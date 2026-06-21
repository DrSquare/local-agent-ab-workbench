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
agent-ab metrics
```

## Next recommended task

Implement Module 5: local FastAPI backend.
