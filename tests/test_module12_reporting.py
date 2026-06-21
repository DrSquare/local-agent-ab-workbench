from __future__ import annotations

import csv
import json
from pathlib import Path

from typer.testing import CliRunner

from agent_ab.cli import app
from agent_ab.reporting import ReportFormat, collect_run_reports, export_run_report, run_local_demo
from agent_ab.runner import run_mock_task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKPACK = PROJECT_ROOT / "taskpacks" / "desktop_basics" / "tasks.yaml"


def test_run_reporting_exports_json_and_csv(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_mock_task(TASKPACK, "rename_todo", runs_root, run_id="demo.report.test")

    rows = collect_run_reports(runs_root)
    json_path = export_run_report(runs_root, tmp_path / "reports" / "runs.json", ReportFormat.JSON)
    csv_path = export_run_report(runs_root, tmp_path / "reports" / "runs.csv", ReportFormat.CSV)

    assert len(rows) == 1
    assert rows[0].run_id == "demo.report.test"
    assert rows[0].status == "passed"
    assert rows[0].task_success == 1.0
    assert json.loads(json_path.read_text(encoding="utf-8"))["runs"][0]["run_id"] == "demo.report.test"
    with csv_path.open(encoding="utf-8", newline="") as csv_file:
        csv_rows = list(csv.DictReader(csv_file))
    assert csv_rows[0]["run_id"] == "demo.report.test"
    assert csv_rows[0]["status"] == "passed"


def test_run_local_demo_creates_repeatable_reports(tmp_path: Path) -> None:
    output_root = tmp_path / "demo"

    first = run_local_demo(PROJECT_ROOT, output_root)
    second = run_local_demo(PROJECT_ROOT, output_root)

    assert first.run_id == "demo.rename_todo.mock"
    assert second.run_id == "demo.rename_todo.mock.2"
    assert Path(first.json_report).is_file()
    assert Path(first.csv_report).is_file()
    report = json.loads(Path(second.json_report).read_text(encoding="utf-8"))
    assert [row["run_id"] for row in report["runs"]] == [
        "demo.rename_todo.mock",
        "demo.rename_todo.mock.2",
    ]


def test_reporting_cli_exports_and_runs_demo(tmp_path: Path) -> None:
    runner = CliRunner()
    runs_root = tmp_path / "runs"
    run_mock_task(TASKPACK, "rename_todo", runs_root, run_id="demo.report.cli")

    export_result = runner.invoke(
        app,
        [
            "export-runs",
            str(runs_root),
            "--output",
            str(tmp_path / "reports" / "runs.csv"),
            "--format",
            "csv",
        ],
    )
    demo_result = runner.invoke(
        app,
        [
            "run-demo",
            "--project-root",
            str(PROJECT_ROOT),
            "--output-root",
            str(tmp_path / "demo-output"),
        ],
    )

    assert export_result.exit_code == 0
    assert "report=" in export_result.output
    assert demo_result.exit_code == 0
    assert "json_report" in demo_result.output
    assert (tmp_path / "reports" / "runs.csv").is_file()
