from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agent_ab.analysis import FailureTaxonomy, load_eval_logs_from_plan, scan_eval_logs
from agent_ab.cli import app
from agent_ab.eval_execution import execute_eval_run_plan
from agent_ab.eval_runner import build_eval_run_plan, write_eval_run_plan
from agent_ab.schemas.eval import EvalLog

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_eval_plan_dry_run_reports_guarded_work_without_writing_logs(tmp_path: Path) -> None:
    plan, plan_path = _write_plan(tmp_path)

    summary = execute_eval_run_plan(plan_path, dry_run=True)

    assert summary.selected_count == 3
    assert summary.dry_run_count == 1
    assert summary.blocked_count == 1
    assert summary.stopped_count == 1
    assert not any(Path(sample.eval_log_path).exists() for sample in plan.sample_runs)

    mock_row = next(row for row in summary.rows if row.sample_id == "rename_todo")
    assert mock_row.adapter == "mock"
    assert mock_row.status == "dry_run"
    assert "run-mock-task" in mock_row.command_preview
    assert {event["decision"] for event in mock_row.guardrail_decisions} == {"approved"}

    blocked_row = next(row for row in summary.rows if row.status == "blocked")
    assert blocked_row.adapter == "custom.human_review"
    assert blocked_row.guardrail_decisions[0]["decision"] == "denied"
    assert "only deterministic mock execution" in blocked_row.reason


def test_eval_plan_executes_mock_sample_and_writes_eval_log(tmp_path: Path) -> None:
    _plan, plan_path = _write_plan(tmp_path)

    summary = execute_eval_run_plan(
        plan_path,
        dry_run=False,
        sample_ids=["rename_todo"],
    )

    assert summary.selected_count == 1
    assert summary.executed_count == 1
    assert summary.blocked_count == 0

    row = summary.rows[0]
    log_path = Path(row.eval_log_path)
    log = EvalLog.model_validate(json.loads(log_path.read_text(encoding="utf-8")))
    assert log.status == "passed"
    assert log.trace is not None
    assert Path(log.trace.path).is_file()
    assert {result.scorer_id for result in log.scorer_results} == {
        "declared_validators",
        "task_success",
        "validator_pass_rate",
    }
    assert log.metadata["execution"]["adapter"] == "mock"
    assert log.metadata["sandbox_provider"]["id"] == row.sandbox_provider_id
    assert Path(log.metadata["sandbox_provider"]["artifacts"]["sqlite_path"]).is_file()
    assert {event["decision"] for event in log.metadata["sandbox_events"]} == {"approved"}

    loaded = load_eval_logs_from_plan(plan_path)
    assert len(loaded) == 1
    assert loaded[0].log.eval_run_id == row.eval_run_id


def test_eval_plan_blocks_non_mock_adapter_with_scannable_eval_log(tmp_path: Path) -> None:
    _plan, plan_path = _write_plan(tmp_path)

    summary = execute_eval_run_plan(
        plan_path,
        dry_run=False,
        sample_ids=["investment_banking_merger_model"],
    )

    assert summary.selected_count == 1
    assert summary.blocked_count == 1
    assert summary.rows[0].adapter == "custom.human_review"

    log = EvalLog.model_validate(json.loads(Path(summary.rows[0].eval_log_path).read_text(encoding="utf-8")))
    assert log.status == "error"
    assert log.errors[0].code == "adapter_blocked"
    assert log.metadata["sandbox_events"][0]["decision"] == "denied"

    findings = scan_eval_logs(load_eval_logs_from_plan(plan_path))
    assert findings[0].category == FailureTaxonomy.SANDBOX_DENIAL
    assert findings[0].evidence["tool_name"] == "custom.human_review"


def test_eval_plan_execution_resumes_completed_logs_and_stops_after_max_failures(tmp_path: Path) -> None:
    _plan, plan_path = _write_plan(tmp_path)

    first_summary = execute_eval_run_plan(plan_path, dry_run=False)
    assert first_summary.executed_count == 1
    assert first_summary.blocked_count == 1
    assert first_summary.stopped_count == 1

    resumed_summary = execute_eval_run_plan(
        plan_path,
        dry_run=False,
        sample_ids=["rename_todo"],
    )
    assert resumed_summary.executed_count == 0
    assert resumed_summary.skipped_count == 1
    assert resumed_summary.rows[0].status == "skipped_completed"


def test_run_eval_plan_cli_executes_filtered_mock_sample(tmp_path: Path) -> None:
    _plan, plan_path = _write_plan(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "run-eval-plan",
            str(plan_path),
            "--execute",
            "--sample-id",
            "rename_todo",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "mode=execute" in result.output
    assert "selected: 1" in result.output
    assert "executed: 1" in result.output


def _write_plan(tmp_path: Path):
    plan = build_eval_run_plan(
        PROJECT_ROOT / "evals" / "local_eval_set.yaml",
        tmp_path / "eval_runs",
    )
    plan_path = write_eval_run_plan(plan, tmp_path / "eval_plan.json")
    return plan, plan_path
