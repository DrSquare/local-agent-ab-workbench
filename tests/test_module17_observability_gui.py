from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from agent_ab.eval_runner import build_eval_run_plan, write_eval_run_plan
from agent_ab.observability import build_observability_read_model
from agent_ab.schemas.eval import EvalLog
from agent_ab.schemas.sandbox import (
    SandboxDecision,
    SandboxEvent,
    SandboxEventType,
    SandboxPolicyArea,
    sandbox_events_metadata,
)
from agent_ab.server import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_observability_read_model_builds_dashboard_eval_regression_and_handoff(tmp_path: Path) -> None:
    plan_path = _write_module17_plan_and_logs(tmp_path)

    read_model = build_observability_read_model(plan_path, project_root=tmp_path)

    assert read_model.dashboard.eval_set_id == "local_module14_eval_set"
    assert read_model.dashboard.total_samples == 3
    assert read_model.dashboard.loaded_log_count == 2
    assert read_model.dashboard.passed_count == 1
    assert read_model.dashboard.error_count == 1
    assert read_model.dashboard.pass_rate == 0.5
    assert read_model.dashboard.sandbox_denial_count == 1
    assert read_model.dashboard.regression_count == 1
    assert read_model.sandbox.denial_count == 1
    assert read_model.sandbox.denied_tools == ["shell"]

    error_row = next(row for row in read_model.eval_rows if row.status == "error")
    passed_row = next(row for row in read_model.eval_rows if row.status == "passed")
    assert passed_row.scorers[0].scorer_id == "task_success"
    assert passed_row.scorers[0].score == 1.0
    assert error_row.failure_taxonomy == "sandbox_denial"
    assert error_row.sandbox.denial_count == 1
    assert error_row.playground_handoff.sample_id == "rename_todo"
    assert read_model.playground_handoffs[0].eval_run_id == error_row.eval_run_id
    assert read_model.regression_rows[0].previous_status == "passed"
    assert read_model.regression_rows[0].current_status == "error"


def test_observability_endpoint_returns_read_models_and_empty_state(tmp_path: Path) -> None:
    plan_path = _write_module17_plan_and_logs(tmp_path)
    client = TestClient(create_app(tmp_path, runs_root=tmp_path / "runs"))

    response = client.get(
        "/observability",
        params={"plan_path": plan_path.relative_to(tmp_path).as_posix()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["dashboard"]["total_samples"] == 3
    assert body["dashboard"]["sandbox_denial_count"] == 1
    assert len(body["eval_rows"]) == 3
    assert len(body["regression_rows"]) == 1
    assert body["playground_handoffs"][0]["task_id"] == "rename_todo"

    empty_client = TestClient(create_app(tmp_path / "empty", runs_root=tmp_path / "empty" / "runs"))
    empty_response = empty_client.get("/observability")
    assert empty_response.status_code == 200
    assert empty_response.json()["dashboard"]["message"] == "No EvalRunPlan found under the runs root."


def test_module17_ui_assets_expose_observe_evaluate_improve_shell(tmp_path: Path) -> None:
    client = TestClient(create_app(PROJECT_ROOT, runs_root=tmp_path / "runs"))

    html = client.get("/ui").text
    css = client.get("/ui/app.css").text
    js = client.get("/ui/app.js").text

    assert "Workbench dashboard" in html
    assert 'data-view="dashboard"' in html
    assert 'data-view="evaluate"' in html
    assert 'data-view="observe"' in html
    assert 'data-view="improve"' in html
    assert 'data-view="settings"' in html
    assert 'id="evalRows"' in html
    assert 'id="regressionRows"' in html
    assert "/observability" in js
    assert "renderEvalRows" in js
    assert "applyPlaygroundHandoff" in js
    assert ".settings-grid" in css
    assert ".table-subtext" in css
    assert "https://" not in html + css + js
    assert "http://" not in html + css + js
    assert "font-size: clamp" not in css
    assert "letter-spacing: 0;" in css


def _write_module17_plan_and_logs(tmp_path: Path) -> Path:
    base_plan = build_eval_run_plan(
        PROJECT_ROOT / "evals" / "local_eval_set.yaml",
        tmp_path / "eval_runs",
    )
    previous = base_plan.sample_runs[0].model_copy(
        update={
            "eval_run_id": "eval.module17.rename_todo.previous",
            "eval_log_path": str(tmp_path / "eval_runs" / "previous" / "eval_log.json"),
        }
    )
    current = base_plan.sample_runs[0].model_copy(
        update={
            "eval_run_id": "eval.module17.rename_todo.current",
            "eval_log_path": str(tmp_path / "eval_runs" / "current" / "eval_log.json"),
        }
    )
    planned = base_plan.sample_runs[1].model_copy(
        update={
            "eval_run_id": "eval.module17.seed.planned",
            "eval_log_path": str(tmp_path / "eval_runs" / "planned" / "eval_log.json"),
        }
    )
    plan = base_plan.model_copy(
        update={
            "total_samples": 3,
            "planned_count": 3,
            "skipped_completed_count": 0,
            "sample_runs": [previous, current, planned],
        }
    )
    plan_path = write_eval_run_plan(plan, tmp_path / "runs" / "evals" / "module17_plan.json")
    _write_eval_log(
        Path(previous.eval_log_path),
        EvalLog(
            eval_task_id=previous.eval_task_id,
            eval_run_id=previous.eval_run_id,
            sample_id=previous.sample_id,
            taskpack_id=previous.taskpack_id,
            task_id=previous.task_id,
            solver_id=previous.solver_id,
            variant_id=previous.variant_id,
            status="passed",
            started_at_ms=10,
            ended_at_ms=20,
            scorer_results=[
                {
                    "scorer_id": "task_success",
                    "type": "metric",
                    "name": "task_success",
                    "passed": True,
                    "score": 1.0,
                }
            ],
            trace={
                "trace_id": "trace.eval.module17.rename_todo.previous",
                "run_id": previous.eval_run_id,
                "path": "trace.previous.jsonl",
            },
            artifacts=[
                {"name": "trace_jsonl", "path": "trace.previous.jsonl", "kind": "trace"},
            ],
        ),
    )
    denial = SandboxEvent(
        id="sandbox_denial_1",
        event_type=SandboxEventType.TOOL_DENIAL,
        decision=SandboxDecision.DENIED,
        provider_id="local_workspace_default",
        tool_name="shell",
        policy_area=SandboxPolicyArea.COMMAND,
        reason="command is blocked by policy: curl",
        command=["curl", "https://example.com"],
    )
    _write_eval_log(
        Path(current.eval_log_path),
        EvalLog(
            eval_task_id=current.eval_task_id,
            eval_run_id=current.eval_run_id,
            sample_id=current.sample_id,
            taskpack_id=current.taskpack_id,
            task_id=current.task_id,
            solver_id=current.solver_id,
            variant_id=current.variant_id,
            status="error",
            started_at_ms=30,
            ended_at_ms=45,
            errors=[
                {"code": "sandbox_denial", "message": "Sandbox denied command."},
            ],
            trace={
                "trace_id": "trace.eval.module17.rename_todo.current",
                "run_id": current.eval_run_id,
                "path": "trace.current.jsonl",
            },
            metadata=sandbox_events_metadata([denial]),
        ),
    )
    return plan_path


def _write_eval_log(path: Path, log: EvalLog) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log.model_dump(mode="json"), indent=2), encoding="utf-8")
