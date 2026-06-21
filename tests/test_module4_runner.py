from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from agent_ab.cli import app
from agent_ab.runner import run_mock_task
from agent_ab.schemas.run import RunStatus
from agent_ab.schemas.task import TaskValidator
from agent_ab.trace_store import read_trace_jsonl
from agent_ab.validators import execute_task_validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKPACK = PROJECT_ROOT / "taskpacks" / "desktop_basics" / "tasks.yaml"


def test_validator_executor_checks_filesystem_contracts(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    notes = workspace / "notes"
    notes.mkdir(parents=True)
    (notes / "todo.txt").write_text("Review inbox items before standup.", encoding="utf-8")

    exists_result = execute_task_validator(
        TaskValidator(type="file_exists", path="notes/todo.txt"),
        workspace,
    )
    contains_result = execute_task_validator(
        TaskValidator(
            type="file_contains",
            path="notes/todo.txt",
            contains="Review inbox",
        ),
        workspace,
    )
    absent_result = execute_task_validator(
        TaskValidator(type="file_not_exists", path="notes/missing.txt"),
        workspace,
    )

    assert exists_result.passed
    assert contains_result.passed
    assert absent_result.passed


def test_mock_runner_executes_demo_task_and_writes_artifacts(tmp_path: Path) -> None:
    result = run_mock_task(
        TASKPACK,
        "rename_todo",
        tmp_path / "runs",
        run_id="mock.rename_todo.test",
    )

    assert result.status == RunStatus.PASSED
    assert (result.workspace_path / "notes" / "action-items.txt").is_file()
    assert not (result.workspace_path / "notes" / "todo.txt").exists()
    assert all(validator_result.passed for validator_result in result.validator_results)
    assert {metric.name: metric.value for metric in result.metrics}["task_success"] == 1.0
    assert result.artifacts["trace_jsonl"].is_file()
    assert result.artifacts["trace_sqlite"].is_file()

    traces = read_trace_jsonl(result.artifacts["trace_jsonl"])
    assert traces[0].trace_id == result.trace_id
    assert traces[0].task_id == "rename_todo"


def test_mock_runner_rejects_unknown_task_id(tmp_path: Path) -> None:
    try:
        run_mock_task(TASKPACK, "missing_task", tmp_path / "runs")
    except ValueError as exc:
        assert "task id not found" in str(exc)
    else:
        raise AssertionError("expected missing task to fail")


def test_mock_runner_rejects_existing_run_directory(tmp_path: Path) -> None:
    run_root = tmp_path / "runs"
    run_id = "mock.rename_todo.test"

    run_mock_task(TASKPACK, "rename_todo", run_root, run_id=run_id)

    try:
        run_mock_task(TASKPACK, "rename_todo", run_root, run_id=run_id)
    except FileExistsError as exc:
        assert run_id in str(exc)
    else:
        raise AssertionError("expected duplicate run id to fail")


def test_mock_runner_rejects_unsafe_run_id(tmp_path: Path) -> None:
    try:
        run_mock_task(TASKPACK, "rename_todo", tmp_path / "runs", run_id="../outside")
    except ValueError as exc:
        assert "run_id" in str(exc)
    else:
        raise AssertionError("expected unsafe run id to fail")


def test_run_mock_task_cli(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run-mock-task",
            str(TASKPACK),
            "rename_todo",
            "--run-root",
            str(tmp_path / "runs"),
            "--run-id",
            "mock.rename_todo.cli",
        ],
    )

    assert result.exit_code == 0
    assert "status=passed" in result.output
