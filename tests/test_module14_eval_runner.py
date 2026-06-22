from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from agent_ab.cli import app
from agent_ab.config import ConfigLoadError, validate_eval_set_with_tasks
from agent_ab.eval_runner import build_eval_run_plan, write_eval_run_plan
from agent_ab.schemas.eval import EvalLog, EvalRunPlan, EvalSet

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_eval_set_validates_referenced_eval_tasks_and_samples() -> None:
    eval_set, resolved = validate_eval_set_with_tasks(
        PROJECT_ROOT / "evals" / "local_eval_set.yaml"
    )

    assert eval_set.id == "local_module14_eval_set"
    assert [ref_id for ref_id, _, _, _ in resolved] == ["desktop_basics", "mercor_apex_seeds"]
    assert [eval_task.id for _, eval_task, _, _ in resolved] == [
        "desktop_basics_mock_eval",
        "mercor_apex_expert_seed_eval",
    ]
    assert sum(len(samples) for _, _, _, samples in resolved) == 3


def test_eval_set_rejects_duplicate_task_refs() -> None:
    with pytest.raises(ValidationError, match="duplicate eval task ref ids"):
        EvalSet.model_validate(
            {
                "id": "bad_eval_set",
                "eval_tasks": [
                    {"id": "same", "path": "desktop_basics_eval.yaml"},
                    {"id": "same", "path": "mercor_apex_seed_eval.yaml"},
                ],
            }
        )


def test_eval_set_validation_reports_bad_referenced_eval_task(tmp_path: Path) -> None:
    eval_set_path = tmp_path / "bad_eval_set.yaml"
    eval_set_path.write_text(
        "\n".join(
            [
                "id: bad_eval_set",
                "eval_tasks:",
                "  - id: missing",
                "    path: missing_eval_task.yaml",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigLoadError, match="eval task ref 'missing' failed validation"):
        validate_eval_set_with_tasks(eval_set_path)


def test_eval_run_plan_expands_samples_without_execution(tmp_path: Path) -> None:
    plan = build_eval_run_plan(
        PROJECT_ROOT / "evals" / "local_eval_set.yaml",
        tmp_path / "eval_runs",
    )

    assert isinstance(plan, EvalRunPlan)
    assert plan.eval_set_id == "local_module14_eval_set"
    assert plan.total_samples == 3
    assert plan.planned_count == 3
    assert plan.skipped_completed_count == 0
    assert [run.eval_run_id for run in plan.sample_runs] == [
        "eval.local_module14_eval_set.desktop_basics_mock_eval.rename_todo",
        "eval.local_module14_eval_set.mercor_apex_expert_seed_eval.investment_banking_merger_model",
        "eval.local_module14_eval_set.mercor_apex_expert_seed_eval.management_consulting_market_score",
    ]
    assert all(run.status == "planned" for run in plan.sample_runs)
    assert not Path(plan.sample_runs[0].eval_log_path).exists()

    output = write_eval_run_plan(plan, tmp_path / "reports" / "eval_plan.json")
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["eval_set_id"] == "local_module14_eval_set"
    assert payload["planned_count"] == 3


def test_eval_run_plan_skips_completed_eval_logs_when_resume_enabled(tmp_path: Path) -> None:
    first_plan = build_eval_run_plan(
        PROJECT_ROOT / "evals" / "local_eval_set.yaml",
        tmp_path / "eval_runs",
    )
    first_run = first_plan.sample_runs[0]
    eval_log_path = Path(first_run.eval_log_path)
    eval_log_path.parent.mkdir(parents=True)
    eval_log_path.write_text(
        json.dumps(
            EvalLog(
                eval_task_id=first_run.eval_task_id,
                eval_task_version=first_run.eval_task_version,
                eval_run_id=first_run.eval_run_id,
                sample_id=first_run.sample_id,
                taskpack_id=first_run.taskpack_id,
                task_id=first_run.task_id,
                solver_id=first_run.solver_id,
                variant_id=first_run.variant_id,
                status="passed",
                scorer_results=[
                    {
                        "scorer_id": "task_success",
                        "type": "metric",
                        "name": "task_success",
                        "passed": True,
                        "score": 1.0,
                    }
                ],
            ).model_dump(mode="json"),
            indent=2,
        ),
        encoding="utf-8",
    )

    resumed_plan = build_eval_run_plan(
        PROJECT_ROOT / "evals" / "local_eval_set.yaml",
        tmp_path / "eval_runs",
    )

    assert resumed_plan.total_samples == 3
    assert resumed_plan.planned_count == 2
    assert resumed_plan.skipped_completed_count == 1
    assert resumed_plan.sample_runs[0].status == "skipped_completed"
    assert resumed_plan.sample_runs[0].metadata["completed_log_status"] == "passed"


def test_eval_run_plan_rejects_invalid_completed_eval_log(tmp_path: Path) -> None:
    plan = build_eval_run_plan(
        PROJECT_ROOT / "evals" / "local_eval_set.yaml",
        tmp_path / "eval_runs",
    )
    bad_log_path = Path(plan.sample_runs[0].eval_log_path)
    bad_log_path.parent.mkdir(parents=True)
    bad_log_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid eval log JSON"):
        build_eval_run_plan(PROJECT_ROOT / "evals" / "local_eval_set.yaml", tmp_path / "eval_runs")


def test_validate_and_plan_eval_set_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    eval_set_path = PROJECT_ROOT / "evals" / "local_eval_set.yaml"

    validate_result = runner.invoke(app, ["validate-eval-set", str(eval_set_path)])
    assert validate_result.exit_code == 0, validate_result.output
    assert "eval_set=local_module14_eval_set@v1" in validate_result.output
    assert "samples: 3" in validate_result.output

    plan_result = runner.invoke(
        app,
        [
            "plan-eval-set",
            str(eval_set_path),
            "--run-root",
            str(tmp_path / "eval_runs"),
            "--output",
            str(tmp_path / "eval_plan.json"),
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output
    assert "eval_set=local_module14_eval_set@v1" in plan_result.output
    assert "samples: 3" in plan_result.output
    assert "planned: 3" in plan_result.output
    assert "plan:" in plan_result.output
    assert (tmp_path / "eval_plan.json").is_file()
