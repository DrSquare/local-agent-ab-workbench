from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from agent_ab.adapters.openclaw import (
    execute_openclaw_plan,
    openclaw_trace_to_envelope,
    prepare_openclaw_run,
)
from agent_ab.cli import app
from agent_ab.guardrails import GuardrailViolation

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = PROJECT_ROOT / "experiments" / "demo_openclaw_adapter.yaml"


def test_prepare_openclaw_run_writes_config_and_command_plan(tmp_path: Path) -> None:
    prepared = prepare_openclaw_run(
        EXPERIMENT,
        "B",
        "openclaw_rename_todo",
        tmp_path / "runs",
        run_id="openclaw.rename_todo.test",
    )

    config_path = Path(prepared.config_path)
    workspace_path = Path(prepared.workspace_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert config_path.is_file()
    assert workspace_path.joinpath("notes", "todo.txt").is_file()
    assert config["adapter"] == "openclaw_cli"
    assert config["experiment"]["variant_id"] == "B"
    assert config["task"]["id"] == "openclaw_rename_todo"
    assert config["task"]["workspace_path"] == str(workspace_path)
    assert config["prompt"]["id"] == "openclaw_candidate_playground_prompt"
    assert config["model"]["name"] == "qwen2.5-coder:7b"
    assert prepared.command_plan.execute is False
    assert prepared.command_plan.command[:2] == ["openclaw", "run"]
    assert "--config" in prepared.command_plan.command
    assert prepared.command_plan.command[-1] == str(config_path.resolve())


def test_openclaw_trace_payload_wraps_to_workbench_trace() -> None:
    trace = openclaw_trace_to_envelope(
        [
            {
                "kind": "tool",
                "name": "write action-items",
                "tool_name": "write_file",
                "arguments": {"path": "notes/action-items.txt"},
                "started_at_ms": 10,
                "duration_ms": 5,
                "result_preview": "wrote file",
            },
            {
                "kind": "shell",
                "name": "blocked shell",
                "command": "curl https://example.com",
                "status": "error",
                "started_at_ms": 20,
                "ended_at_ms": 21,
                "stderr_preview": "blocked",
            },
        ],
        trace_id="trace.openclaw.demo",
        taskpack_id="openclaw_demo",
        task_id="openclaw_rename_todo",
        variant_id="B",
        run_id="openclaw.rename_todo.trace",
    )

    assert trace.root_span().kind == "task_run"
    assert trace.metadata["source"] == "openclaw_cli"
    tool_span = next(span for span in trace.spans if span.kind == "tool")
    shell_span = next(span for span in trace.spans if span.kind == "shell")
    assert tool_span.tool_call.tool_name == "write_file"
    assert tool_span.tool_call.arguments["path"] == "notes/action-items.txt"
    assert shell_span.status == "error"
    assert shell_span.shell_action.stderr_preview == "blocked"


def test_openclaw_execution_requires_explicit_opt_in(tmp_path: Path) -> None:
    prepared = prepare_openclaw_run(
        EXPERIMENT,
        "B",
        "openclaw_rename_todo",
        tmp_path / "runs",
        run_id="openclaw.rename_todo.gate",
    )

    with pytest.raises(GuardrailViolation, match="allow_execute=True"):
        execute_openclaw_plan(prepared)


def test_openclaw_execution_uses_injected_runner_when_allowed(tmp_path: Path) -> None:
    prepared = prepare_openclaw_run(
        EXPERIMENT,
        "B",
        "openclaw_rename_todo",
        tmp_path / "runs",
        run_id="openclaw.rename_todo.fake",
    )
    seen = {}

    def fake_runner(plan):
        seen["plan"] = plan
        return subprocess.CompletedProcess(plan.command, 0, stdout="ok token=secret", stderr="")

    result = execute_openclaw_plan(prepared, allow_execute=True, runner=fake_runner)

    assert seen["plan"].execute is True
    assert seen["plan"].command == prepared.command_plan.command
    assert prepared.command_plan.execute is False
    assert result.status == "passed"
    assert result.return_code == 0
    assert result.stdout_preview == "ok token=[REDACTED]"


def test_openclaw_execution_rejects_mutated_command_plan(tmp_path: Path) -> None:
    prepared = prepare_openclaw_run(
        EXPERIMENT,
        "B",
        "openclaw_rename_todo",
        tmp_path / "runs",
        run_id="openclaw.rename_todo.mutated",
    )
    mutated = prepared.model_copy(
        update={
            "command_plan": prepared.command_plan.model_copy(
                update={"command": ["powershell", "-Command", "Write-Host unsafe"]}
            )
        }
    )

    with pytest.raises(GuardrailViolation, match="openclaw executable"):
        execute_openclaw_plan(mutated, allow_execute=True, runner=lambda plan: None)


def test_prepare_openclaw_run_cli(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "prepare-openclaw-run",
            str(EXPERIMENT),
            "A",
            "openclaw_rename_todo",
            "--run-root",
            str(tmp_path / "runs"),
            "--run-id",
            "openclaw.rename_todo.cli",
        ],
    )

    assert result.exit_code == 0
    assert "run=openclaw.rename_todo.cli" in result.output
    assert "openclaw_config.yaml" in result.output
    assert "openclaw run --config" in result.output
