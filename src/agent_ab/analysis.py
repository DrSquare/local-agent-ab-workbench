"""EvalLog analysis and scanner helpers for Module 15."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import Field

from agent_ab.reporting import ReportFormat
from agent_ab.schemas.common import StrictBaseModel
from agent_ab.schemas.eval import EvalLog, EvalRunPlan


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class FailureTaxonomy(str, Enum):
    SANDBOX_DENIAL = "sandbox_denial"
    EVAL_ERROR = "eval_error"
    SCORER_FAILURE = "scorer_failure"
    MISSING_TRACE = "missing_trace"
    UNKNOWN_FAILURE = "unknown_failure"


class LoadedEvalLog(StrictBaseModel):
    path: str
    log: EvalLog


class EvalLogReportRow(StrictBaseModel):
    eval_task_id: str
    eval_run_id: str
    sample_id: str
    taskpack_id: str
    task_id: str
    solver_id: str
    variant_id: str | None = None
    status: str
    scorer_count: int = 0
    passed_scorers: int = 0
    failed_scorers: int = 0
    trace_id: str | None = None
    artifact_count: int = 0
    error_count: int = 0
    eval_log_path: str
    failure_taxonomy: str | None = None


class EvalAggregateRow(StrictBaseModel):
    eval_task_id: str
    solver_id: str
    variant_id: str | None = None
    sample_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    pass_rate: float | None = None
    avg_numeric_score: float | None = None


class EvalScannerFinding(StrictBaseModel):
    eval_run_id: str
    sample_id: str
    eval_task_id: str
    severity: FindingSeverity
    category: FailureTaxonomy
    message: str
    eval_log_path: str
    evidence: dict[str, Any] = Field(default_factory=dict)


def load_eval_run_plan(path: str | Path) -> EvalRunPlan:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return EvalRunPlan.model_validate(payload)


def load_eval_logs_from_plan(plan: EvalRunPlan | str | Path) -> list[LoadedEvalLog]:
    eval_plan = load_eval_run_plan(plan) if isinstance(plan, (str, Path)) else plan
    loaded: list[LoadedEvalLog] = []
    for sample_run in eval_plan.sample_runs:
        path = Path(sample_run.eval_log_path)
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        loaded.append(LoadedEvalLog(path=str(path), log=EvalLog.model_validate(payload)))
    return loaded


def build_eval_log_rows(logs: Iterable[LoadedEvalLog]) -> list[EvalLogReportRow]:
    return [_row_from_loaded_log(loaded) for loaded in logs]


def build_eval_aggregate_rows(logs: Iterable[LoadedEvalLog]) -> list[EvalAggregateRow]:
    grouped: dict[tuple[str, str, str | None], list[EvalLog]] = {}
    for loaded in logs:
        log = loaded.log
        grouped.setdefault((log.eval_task_id, log.solver_id, log.variant_id), []).append(log)

    rows: list[EvalAggregateRow] = []
    for (eval_task_id, solver_id, variant_id), group in sorted(grouped.items()):
        passed_count = sum(log.status == "passed" for log in group)
        failed_count = sum(log.status == "failed" for log in group)
        error_count = sum(log.status == "error" for log in group)
        skipped_count = sum(log.status == "skipped" for log in group)
        rows.append(
            EvalAggregateRow(
                eval_task_id=eval_task_id,
                solver_id=solver_id,
                variant_id=variant_id,
                sample_count=len(group),
                passed_count=passed_count,
                failed_count=failed_count,
                error_count=error_count,
                skipped_count=skipped_count,
                pass_rate=passed_count / len(group) if group else None,
                avg_numeric_score=_average_numeric_score(group),
            )
        )
    return rows


def scan_eval_logs(logs: Iterable[LoadedEvalLog]) -> list[EvalScannerFinding]:
    findings: list[EvalScannerFinding] = []
    for loaded in logs:
        log = loaded.log
        findings.extend(_findings_for_log(loaded))
        if log.status == "failed" and not any(finding.eval_run_id == log.eval_run_id for finding in findings):
            findings.append(
                _finding(
                    loaded,
                    FindingSeverity.WARNING,
                    FailureTaxonomy.UNKNOWN_FAILURE,
                    "Eval failed without explicit scorer or error evidence.",
                    {},
                )
            )
    return findings


def export_eval_log_report(plan_path: str | Path, output_path: str | Path, report_format: ReportFormat) -> Path:
    return write_eval_log_report(build_eval_log_rows(load_eval_logs_from_plan(plan_path)), output_path, report_format)


def export_eval_aggregate_report(plan_path: str | Path, output_path: str | Path, report_format: ReportFormat) -> Path:
    return write_eval_aggregate_report(
        build_eval_aggregate_rows(load_eval_logs_from_plan(plan_path)),
        output_path,
        report_format,
    )


def export_eval_scan_report(plan_path: str | Path, output_path: str | Path, report_format: ReportFormat) -> Path:
    return write_eval_scan_report(scan_eval_logs(load_eval_logs_from_plan(plan_path)), output_path, report_format)


def write_eval_log_report(rows: list[EvalLogReportRow], output_path: str | Path, report_format: ReportFormat) -> Path:
    return _write_report("eval_logs", rows, output_path, report_format)


def write_eval_aggregate_report(rows: list[EvalAggregateRow], output_path: str | Path, report_format: ReportFormat) -> Path:
    return _write_report("aggregates", rows, output_path, report_format)


def write_eval_scan_report(rows: list[EvalScannerFinding], output_path: str | Path, report_format: ReportFormat) -> Path:
    return _write_report("findings", rows, output_path, report_format)


def _row_from_loaded_log(loaded: LoadedEvalLog) -> EvalLogReportRow:
    log = loaded.log
    failed_scorers = [
        result
        for result in log.scorer_results
        if result.passed is False
    ]
    passed_scorers = [
        result
        for result in log.scorer_results
        if result.passed is True
    ]
    return EvalLogReportRow(
        eval_task_id=log.eval_task_id,
        eval_run_id=log.eval_run_id,
        sample_id=log.sample_id,
        taskpack_id=log.taskpack_id,
        task_id=log.task_id,
        solver_id=log.solver_id,
        variant_id=log.variant_id,
        status=str(log.status),
        scorer_count=len(log.scorer_results),
        passed_scorers=len(passed_scorers),
        failed_scorers=len(failed_scorers),
        trace_id=log.trace.trace_id if log.trace else None,
        artifact_count=len(log.artifacts),
        error_count=len(log.errors),
        eval_log_path=loaded.path,
        failure_taxonomy=_taxonomy_for_log(log),
    )


def _findings_for_log(loaded: LoadedEvalLog) -> list[EvalScannerFinding]:
    log = loaded.log
    findings: list[EvalScannerFinding] = []
    for event in _sandbox_denial_events(log):
        findings.append(
            _finding(
                loaded,
                FindingSeverity.ERROR if log.status == "error" else FindingSeverity.WARNING,
                FailureTaxonomy.SANDBOX_DENIAL,
                str(event.get("reason") or "Sandbox denied a tool action."),
                {
                    "event_id": event.get("id"),
                    "provider_id": event.get("provider_id"),
                    "tool_name": event.get("tool_name"),
                    "policy_area": event.get("policy_area"),
                    "requested_action": event.get("requested_action"),
                },
            )
        )
    for error in log.errors:
        findings.append(
            _finding(
                loaded,
                FindingSeverity.ERROR if error.fatal else FindingSeverity.WARNING,
                FailureTaxonomy.EVAL_ERROR,
                error.message,
                {"code": error.code, "span_id": error.span_id, "fatal": error.fatal},
            )
        )
    for result in log.scorer_results:
        if result.passed is False:
            findings.append(
                _finding(
                    loaded,
                    FindingSeverity.WARNING,
                    FailureTaxonomy.SCORER_FAILURE,
                    result.message or f"Scorer failed: {result.scorer_id}",
                    {"scorer_id": result.scorer_id, "type": result.type, "score": result.score},
                )
            )
    if log.status in {"passed", "failed"} and log.trace is None:
        findings.append(
            _finding(
                loaded,
                FindingSeverity.WARNING,
                FailureTaxonomy.MISSING_TRACE,
                "Eval log has no trace reference.",
                {},
            )
        )
    return findings


def _finding(
    loaded: LoadedEvalLog,
    severity: FindingSeverity,
    category: FailureTaxonomy,
    message: str,
    evidence: dict[str, Any],
) -> EvalScannerFinding:
    log = loaded.log
    return EvalScannerFinding(
        eval_run_id=log.eval_run_id,
        sample_id=log.sample_id,
        eval_task_id=log.eval_task_id,
        severity=severity,
        category=category,
        message=message,
        eval_log_path=loaded.path,
        evidence=evidence,
    )


def _taxonomy_for_log(log: EvalLog) -> str | None:
    if _sandbox_denial_events(log):
        return FailureTaxonomy.SANDBOX_DENIAL.value
    if log.errors:
        return FailureTaxonomy.EVAL_ERROR.value
    if any(result.passed is False for result in log.scorer_results):
        return FailureTaxonomy.SCORER_FAILURE.value
    if log.status in {"passed", "failed"} and log.trace is None:
        return FailureTaxonomy.MISSING_TRACE.value
    if log.status == "failed":
        return FailureTaxonomy.UNKNOWN_FAILURE.value
    return None


def _sandbox_denial_events(log: EvalLog) -> list[dict[str, Any]]:
    events = log.metadata.get("sandbox_events")
    if not isinstance(events, list):
        return []
    denial_events: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("decision") == "denied" or event.get("event_type") == "tool_denial":
            denial_events.append(event)
    return denial_events


def _average_numeric_score(logs: Iterable[EvalLog]) -> float | None:
    values: list[float] = []
    for log in logs:
        for result in log.scorer_results:
            score = result.score
            if isinstance(score, bool) or score is None:
                continue
            if isinstance(score, (int, float)):
                values.append(float(score))
    if not values:
        return None
    return sum(values) / len(values)


def _write_report(
    root_key: str,
    rows: list[StrictBaseModel],
    output_path: str | Path,
    report_format: ReportFormat,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if report_format == ReportFormat.JSON:
        path.write_text(
            json.dumps({root_key: [row.model_dump(mode="json") for row in rows]}, indent=2),
            encoding="utf-8",
        )
        return path

    with path.open("w", encoding="utf-8", newline="") as csv_file:
        fieldnames = list(type(rows[0]).model_fields) if rows else []
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            for row in rows:
                writer.writerow(_csv_payload(row))
    return path


def _csv_payload(row: StrictBaseModel) -> dict[str, Any]:
    payload = row.model_dump(mode="json")
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            payload[key] = json.dumps(value, sort_keys=True)
    return payload
