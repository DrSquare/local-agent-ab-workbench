from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from agent_ab.cli import app
from agent_ab.config import ConfigLoadError, validate_eval_task_with_taskpack
from agent_ab.schemas.eval import (
    EvalLog,
    EvalLogStatus,
    EvalScorerRef,
    EvalSolverRef,
    EvalTask,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_desktop_basics_eval_task_validates_and_normalizes_samples() -> None:
    eval_task, taskpack, samples = validate_eval_task_with_taskpack(
        PROJECT_ROOT / "evals" / "desktop_basics_eval.yaml"
    )

    assert eval_task.id == "desktop_basics_mock_eval"
    assert taskpack.id == "desktop_basics"
    assert [sample.id for sample in samples] == ["rename_todo"]
    assert samples[0].task_id == "rename_todo"
    assert samples[0].workspace_fixture == "workspaces/rename_todo"
    assert [validator.type for validator in samples[0].validators] == [
        "file_exists",
        "file_not_exists",
        "file_contains",
    ]
    assert eval_task.solver.adapter == "mock"
    assert [scorer.id for scorer in eval_task.scorers] == [
        "declared_validators",
        "task_success",
        "validator_pass_rate",
    ]


def test_expert_seed_eval_task_can_select_named_samples() -> None:
    eval_task, taskpack, samples = validate_eval_task_with_taskpack(
        PROJECT_ROOT / "evals" / "mercor_apex_seed_eval.yaml"
    )

    assert eval_task.id == "mercor_apex_expert_seed_eval"
    assert taskpack.id == "mercor_apex_expert_seeded"
    assert [sample.id for sample in samples] == [
        "investment_banking_merger_model",
        "management_consulting_market_score",
    ]
    assert samples[0].metadata["onet"]["task"]["task_id"] == 21590


def test_eval_task_rejects_unknown_keys_and_duplicate_scorer_ids() -> None:
    payload = {
        "id": "bad_eval",
        "taskpack": "taskpacks/desktop_basics/tasks.yaml",
        "solver": {"id": "mock_solver", "adapter": "mock"},
        "scorers": [{"id": "task_success", "type": "metric", "name": "task_success"}],
        "unexpected": True,
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EvalTask.model_validate(payload)

    payload.pop("unexpected")
    payload["scorers"] = [
        {"id": "same", "type": "metric", "name": "task_success"},
        {"id": "same", "type": "metric", "name": "validator_pass_rate"},
    ]
    with pytest.raises(ValidationError, match="duplicate scorer ids"):
        EvalTask.model_validate(payload)


def test_eval_task_sample_selection_rejects_unknown_ids(tmp_path: Path) -> None:
    eval_path = tmp_path / "bad_eval.yaml"
    eval_path.write_text(
        "\n".join(
            [
                "id: bad_sample_selection",
                f"taskpack: {PROJECT_ROOT / 'taskpacks' / 'desktop_basics' / 'tasks.yaml'}",
                "samples:",
                "  include:",
                "    - missing_task",
                "solver:",
                "  id: mock_solver",
                "  adapter: mock",
                "scorers:",
                "  - id: task_success",
                "    type: metric",
                "    name: task_success",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigLoadError, match="sample IDs not found"):
        validate_eval_task_with_taskpack(eval_path)


def test_eval_solver_references_registered_or_custom_adapters() -> None:
    assert EvalSolverRef(id="mock_solver", adapter="mock").adapter == "mock"
    assert EvalSolverRef(id="custom_solver", adapter="custom.local_agent").adapter == "custom.local_agent"

    with pytest.raises(ValidationError, match="unknown solver adapter"):
        EvalSolverRef(id="bad_solver", adapter="remote_cloud_agent")

    with pytest.raises(ValidationError, match="unknown solver adapter"):
        EvalSolverRef(id="bad_custom_solver", adapter="custom.")


def test_eval_scorer_references_validators_metrics_and_custom_names() -> None:
    assert EvalScorerRef(id="file_exists", type="validator", name="file_exists").name == "file_exists"
    assert EvalScorerRef(id="metric", type="metric", name="task_success").name == "task_success"
    assert EvalScorerRef(id="trace", type="trace", name="span_status").name == "span_status"
    assert EvalScorerRef(id="custom_scorer", type="custom", name="custom.domain_rubric").name == "custom.domain_rubric"

    with pytest.raises(ValidationError, match="unknown validator scorer"):
        EvalScorerRef(id="bad_validator", type="validator", name="made_up_validator")

    with pytest.raises(ValidationError, match="unknown metric scorer"):
        EvalScorerRef(id="bad_metric", type="metric", name="made_up_metric")

    with pytest.raises(ValidationError, match="custom scorers"):
        EvalScorerRef(id="bad_custom", type="custom", name="domain_rubric")


def test_eval_log_captures_sample_solver_scores_trace_artifacts_limits_and_errors() -> None:
    log = EvalLog(
        eval_task_id="desktop_basics_mock_eval",
        eval_run_id="eval.desktop_basics_mock_eval.1",
        sample_id="rename_todo",
        taskpack_id="desktop_basics",
        task_id="rename_todo",
        solver_id="mock_solver",
        variant_id="demo.mock",
        status=EvalLogStatus.PASSED,
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
            "trace_id": "trace.eval.desktop_basics_mock_eval.1",
            "run_id": "eval.desktop_basics_mock_eval.1",
            "path": "runs/eval.desktop_basics_mock_eval.1/trace.jsonl",
        },
        artifacts=[
            {
                "name": "trace_jsonl",
                "path": "runs/eval.desktop_basics_mock_eval.1/trace.jsonl",
                "kind": "trace",
            }
        ],
        metadata={"workflow": "ab_report_to_playground"},
    )

    assert log.sample_id == "rename_todo"
    assert log.solver_id == "mock_solver"
    assert log.scorer_results[0].score == 1.0
    assert log.trace is not None
    assert log.trace.trace_id == "trace.eval.desktop_basics_mock_eval.1"
    assert log.artifacts[0].name == "trace_jsonl"
    assert log.limits.allow_network is False
    assert log.errors == []


def test_eval_log_rejects_error_status_without_error_and_duplicate_scorer_results() -> None:
    base_payload = {
        "eval_task_id": "desktop_basics_mock_eval",
        "eval_run_id": "eval.desktop_basics_mock_eval.1",
        "sample_id": "rename_todo",
        "taskpack_id": "desktop_basics",
        "task_id": "rename_todo",
        "solver_id": "mock_solver",
        "status": "error",
    }

    with pytest.raises(ValidationError, match="status=error requires"):
        EvalLog.model_validate(base_payload)

    missing_results_payload = {
        **base_payload,
        "status": "failed",
    }
    with pytest.raises(ValidationError, match="require scorer_results"):
        EvalLog.model_validate(missing_results_payload)

    duplicate_results_payload = {
        **base_payload,
        "status": "failed",
        "scorer_results": [
            {"scorer_id": "same", "type": "metric", "name": "task_success", "score": 0},
            {"scorer_id": "same", "type": "metric", "name": "validator_pass_rate", "score": 0},
        ],
    }
    with pytest.raises(ValidationError, match="duplicate scorer result ids"):
        EvalLog.model_validate(duplicate_results_payload)

    bad_result_payload = {
        **base_payload,
        "status": "failed",
        "scorer_results": [
            {"scorer_id": "bad_metric", "type": "metric", "name": "made_up_metric", "score": 0},
        ],
    }
    with pytest.raises(ValidationError, match="unknown metric scorer"):
        EvalLog.model_validate(bad_result_payload)


def test_validate_eval_task_cli() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "validate-eval-task",
            str(PROJECT_ROOT / "evals" / "desktop_basics_eval.yaml"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "eval_task=desktop_basics_mock_eval@v1" in result.output
    assert "samples: 1 (rename_todo)" in result.output
    assert "solver: mock_solver/mock" in result.output
