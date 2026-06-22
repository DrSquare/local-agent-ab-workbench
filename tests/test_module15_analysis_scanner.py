from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agent_ab.analysis import (
    FailureTaxonomy,
    build_eval_aggregate_rows,
    build_eval_log_rows,
    load_eval_logs_from_plan,
    scan_eval_logs,
)
from agent_ab.cli import app
from agent_ab.eval_runner import build_eval_run_plan, write_eval_run_plan
from agent_ab.schemas.eval import EvalLog

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_eval_analysis_loads_logs_from_plan_and_builds_rows(tmp_path: Path) -> None:
    plan_path = _write_plan_with_two_logs(tmp_path)

    logs = load_eval_logs_from_plan(plan_path)
    rows = build_eval_log_rows(logs)

    assert len(logs) == 2
    assert [row.status for row in rows] == ["passed", "failed"]
    assert rows[0].trace_id == "trace.eval.local_module14_eval_set.desktop_basics_mock_eval.rename_todo"
    assert rows[1].failed_scorers == 1
    assert rows[1].failure_taxonomy == FailureTaxonomy.SCORER_FAILURE


def test_eval_analysis_builds_aggregate_rows(tmp_path: Path) -> None:
    plan_path = _write_plan_with_two_logs(tmp_path)

    aggregates = build_eval_aggregate_rows(load_eval_logs_from_plan(plan_path))

    assert len(aggregates) == 2
    by_task = {row.eval_task_id: row for row in aggregates}
    assert by_task["desktop_basics_mock_eval"].passed_count == 1
    assert by_task["desktop_basics_mock_eval"].pass_rate == 1.0
    assert by_task["mercor_apex_expert_seed_eval"].failed_count == 1
    assert by_task["mercor_apex_expert_seed_eval"].avg_numeric_score == 0.0


def test_eval_scanner_finds_failures_and_missing_trace(tmp_path: Path) -> None:
    plan_path = _write_plan_with_two_logs(tmp_path)

    findings = scan_eval_logs(load_eval_logs_from_plan(plan_path))
    categories = [finding.category for finding in findings]

    assert FailureTaxonomy.SCORER_FAILURE in categories
    assert FailureTaxonomy.MISSING_TRACE in categories
    scorer_finding = next(finding for finding in findings if finding.category == FailureTaxonomy.SCORER_FAILURE)
    assert scorer_finding.severity == "warning"
    assert scorer_finding.evidence["scorer_id"] == "expert_rubric"


def test_eval_analysis_cli_exports_json_and_csv(tmp_path: Path) -> None:
    plan_path = _write_plan_with_two_logs(tmp_path)
    runner = CliRunner()

    logs_json = tmp_path / "reports" / "eval_logs.json"
    aggregates_csv = tmp_path / "reports" / "eval_aggregates.csv"
    findings_json = tmp_path / "reports" / "eval_findings.json"

    logs_result = runner.invoke(app, ["export-eval-logs", str(plan_path), "--output", str(logs_json)])
    assert logs_result.exit_code == 0, logs_result.output
    logs_payload = json.loads(logs_json.read_text(encoding="utf-8"))
    assert len(logs_payload["eval_logs"]) == 2

    aggregate_result = runner.invoke(
        app,
        [
            "export-eval-aggregates",
            str(plan_path),
            "--output",
            str(aggregates_csv),
            "--format",
            "csv",
        ],
    )
    assert aggregate_result.exit_code == 0, aggregate_result.output
    assert "eval_task_id,solver_id" in aggregates_csv.read_text(encoding="utf-8")

    findings_result = runner.invoke(app, ["scan-eval-logs", str(plan_path), "--output", str(findings_json)])
    assert findings_result.exit_code == 0, findings_result.output
    findings_payload = json.loads(findings_json.read_text(encoding="utf-8"))
    assert len(findings_payload["findings"]) == 2


def _write_plan_with_two_logs(tmp_path: Path) -> Path:
    plan = build_eval_run_plan(
        PROJECT_ROOT / "evals" / "local_eval_set.yaml",
        tmp_path / "eval_runs",
    )
    plan_path = write_eval_run_plan(plan, tmp_path / "eval_plan.json")

    first_run = plan.sample_runs[0]
    _write_eval_log(
        Path(first_run.eval_log_path),
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
            trace={
                "trace_id": f"trace.{first_run.eval_run_id}",
                "run_id": first_run.eval_run_id,
                "path": "trace.jsonl",
            },
            artifacts=[
                {"name": "trace_jsonl", "path": "trace.jsonl", "kind": "trace"},
            ],
        ),
    )

    second_run = plan.sample_runs[1]
    _write_eval_log(
        Path(second_run.eval_log_path),
        EvalLog(
            eval_task_id=second_run.eval_task_id,
            eval_task_version=second_run.eval_task_version,
            eval_run_id=second_run.eval_run_id,
            sample_id=second_run.sample_id,
            taskpack_id=second_run.taskpack_id,
            task_id=second_run.task_id,
            solver_id=second_run.solver_id,
            variant_id=second_run.variant_id,
            status="failed",
            scorer_results=[
                {
                    "scorer_id": "expert_rubric",
                    "type": "validator",
                    "name": "custom.human_expert_rubric",
                    "passed": False,
                    "score": 0.0,
                    "message": "Expert rubric did not pass.",
                }
            ],
        ),
    )
    return plan_path


def _write_eval_log(path: Path, log: EvalLog) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log.model_dump(mode="json"), indent=2), encoding="utf-8")
