from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_ab.cli import app
from agent_ab.runner import run_mock_task
from agent_ab.server import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKPACK = PROJECT_ROOT / "taskpacks" / "desktop_basics" / "tasks.yaml"


def test_api_health_and_config_discovery() -> None:
    client = TestClient(create_app(PROJECT_ROOT))

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    experiments = client.get("/experiments")
    assert experiments.status_code == 200
    experiment_payload = experiments.json()["experiments"]
    demo_experiment = next(
        item for item in experiment_payload if item["name"] == "openclaw_prompt_ab_v1"
    )
    assert demo_experiment["valid"] is True
    assert demo_experiment["agents"] == ["A", "B"]
    assert demo_experiment["taskpack"] == "../taskpacks/desktop_basics/tasks.yaml"

    taskpacks = client.get("/taskpacks")
    assert taskpacks.status_code == 200
    taskpack_payload = taskpacks.json()["taskpacks"]
    desktop_basics = next(item for item in taskpack_payload if item["id"] == "desktop_basics")
    assert desktop_basics["valid"] is True
    assert desktop_basics["task_count"] == 1
    assert desktop_basics["tasks"][0]["id"] == "rename_todo"


def test_api_lists_run_artifacts_and_returns_trace(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    result = run_mock_task(
        TASKPACK,
        "rename_todo",
        runs_root,
        run_id="mock.rename_todo.api",
    )
    client = TestClient(create_app(PROJECT_ROOT, runs_root=runs_root))

    runs = client.get("/runs")
    assert runs.status_code == 200
    run_summary = next(
        item for item in runs.json()["runs"] if item["run_id"] == "mock.rename_todo.api"
    )
    assert run_summary["trace_count"] == 1
    assert run_summary["trace_id"] == result.trace_id
    assert run_summary["task_id"] == "rename_todo"
    assert {artifact["name"]: artifact["exists"] for artifact in run_summary["artifacts"]} == {
        "trace_jsonl": True,
        "trace_sqlite": True,
        "workspace": True,
    }

    run_detail = client.get("/runs/mock.rename_todo.api")
    assert run_detail.status_code == 200
    assert run_detail.json()["variant_id"] == "mock"

    trace = client.get("/runs/mock.rename_todo.api/trace")
    assert trace.status_code == 200
    trace_payload = trace.json()
    assert trace_payload["run_id"] == "mock.rename_todo.api"
    assert trace_payload["traces"][0]["trace_id"] == result.trace_id
    assert trace_payload["traces"][0]["task_id"] == "rename_todo"


def test_api_rejects_unsafe_run_ids(tmp_path: Path) -> None:
    client = TestClient(create_app(PROJECT_ROOT, runs_root=tmp_path / "runs"))

    invalid_character = client.get("/runs/bad%5Crun/trace")
    assert invalid_character.status_code == 400
    assert "run_id" in invalid_character.json()["detail"]

    root_escape = client.get("/runs/%2E/trace")
    assert root_escape.status_code == 400
    assert "escapes runs root" in root_escape.json()["detail"]


def test_serve_cli_rejects_non_local_hosts() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["serve", "--host", "0.0.0.0"])

    assert result.exit_code == 1
    assert "host must be localhost" in result.output
