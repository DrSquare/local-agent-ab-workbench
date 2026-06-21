"""Local demo and reporting helpers."""

from __future__ import annotations

import csv
import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import Field

from agent_ab.runner import run_mock_task
from agent_ab.schemas.common import StrictBaseModel
from agent_ab.schemas.trace import TraceEnvelope
from agent_ab.trace_store import read_trace_jsonl


class ReportFormat(str, Enum):
    JSON = "json"
    CSV = "csv"


class RunReportRow(StrictBaseModel):
    run_id: str
    trace_id: str | None = None
    taskpack_id: str | None = None
    task_id: str | None = None
    variant_id: str | None = None
    status: str = "unknown"
    span_count: int = 0
    duration_ms: int | None = None
    task_success: float | int | str | bool | None = None
    validator_pass_rate: float | int | str | bool | None = None
    step_count: float | int | str | bool | None = None
    trace_path: str | None = None
    trace_error: str | None = None
    artifacts: dict[str, bool] = Field(default_factory=dict)


class DemoRunSummary(StrictBaseModel):
    run_id: str
    runs_root: str
    json_report: str
    csv_report: str


def collect_run_reports(runs_root: str | Path) -> list[RunReportRow]:
    root = Path(runs_root)
    if not root.is_dir():
        return []
    return [
        _summarize_run_dir(path)
        for path in sorted(root.iterdir())
        if path.is_dir()
    ]


def write_run_report(rows: list[RunReportRow], output_path: str | Path, report_format: ReportFormat) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if report_format == ReportFormat.JSON:
        path.write_text(
            json.dumps({"runs": [row.model_dump(mode="json") for row in rows]}, indent=2),
            encoding="utf-8",
        )
        return path
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        fieldnames = list(RunReportRow.model_fields)
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            payload = row.model_dump(mode="json")
            payload["artifacts"] = json.dumps(payload["artifacts"], sort_keys=True)
            writer.writerow(payload)
    return path


def export_run_report(runs_root: str | Path, output_path: str | Path, report_format: ReportFormat) -> Path:
    return write_run_report(collect_run_reports(runs_root), output_path, report_format)


def run_local_demo(project_root: str | Path, output_root: str | Path) -> DemoRunSummary:
    root = Path(project_root)
    output = Path(output_root)
    runs_root = output / "runs"
    reports_root = output / "reports"
    run_id = _next_demo_run_id(runs_root)
    result = run_mock_task(
        root / "taskpacks" / "desktop_basics" / "tasks.yaml",
        "rename_todo",
        runs_root,
        run_id=run_id,
        variant_id="demo.mock",
    )
    rows = collect_run_reports(runs_root)
    json_report = write_run_report(rows, reports_root / "runs.json", ReportFormat.JSON)
    csv_report = write_run_report(rows, reports_root / "runs.csv", ReportFormat.CSV)
    return DemoRunSummary(
        run_id=result.run_id,
        runs_root=str(runs_root),
        json_report=str(json_report),
        csv_report=str(csv_report),
    )


def _summarize_run_dir(run_dir: Path) -> RunReportRow:
    trace_path = run_dir / "trace.jsonl"
    artifacts = {
        "trace_jsonl": trace_path.is_file(),
        "trace_sqlite": (run_dir / "trace.sqlite").is_file(),
        "workspace": (run_dir / "workspace").is_dir(),
    }
    if not trace_path.is_file():
        return RunReportRow(run_id=run_dir.name, artifacts=artifacts, trace_path=str(trace_path))
    try:
        traces = read_trace_jsonl(trace_path)
    except ValueError as exc:
        return RunReportRow(
            run_id=run_dir.name,
            artifacts=artifacts,
            trace_path=str(trace_path),
            trace_error=str(exc),
        )
    if not traces:
        return RunReportRow(run_id=run_dir.name, artifacts=artifacts, trace_path=str(trace_path))
    return _row_from_trace(run_dir.name, traces[0], trace_path, artifacts)


def _row_from_trace(run_id: str, trace: TraceEnvelope, trace_path: Path, artifacts: dict[str, bool]) -> RunReportRow:
    metrics = _trace_metrics(trace)
    root = trace.root_span()
    return RunReportRow(
        run_id=run_id,
        trace_id=trace.trace_id,
        taskpack_id=trace.taskpack_id,
        task_id=trace.task_id,
        variant_id=trace.variant_id,
        status=_status_from_metrics(metrics),
        span_count=len(trace.spans),
        duration_ms=root.duration_ms,
        task_success=metrics.get("task_success"),
        validator_pass_rate=metrics.get("validator_pass_rate"),
        step_count=metrics.get("step_count"),
        trace_path=str(trace_path),
        artifacts=artifacts,
    )


def _trace_metrics(trace: TraceEnvelope) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    for span in trace.spans:
        if span.scoring:
            metrics.update(span.scoring.metrics)
    return metrics


def _status_from_metrics(metrics: dict[str, Any]) -> str:
    task_success = metrics.get("task_success")
    if task_success == 1 or task_success == 1.0:
        return "passed"
    if task_success == 0 or task_success == 0.0:
        return "failed"
    return "unknown"


def _next_demo_run_id(runs_root: Path) -> str:
    base = "demo.rename_todo.mock"
    if not (runs_root / base).exists():
        return base
    index = 2
    while (runs_root / f"{base}.{index}").exists():
        index += 1
    return f"{base}.{index}"
