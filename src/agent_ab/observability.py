"""Read models for the local observe/evaluate/improve workbench UI."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pydantic import Field, field_validator

from agent_ab.analysis import LoadedEvalLog, build_eval_log_rows
from agent_ab.schemas.common import StrictBaseModel, _non_blank, _normalized_non_blank_list
from agent_ab.schemas.eval import EvalLog, EvalRunPlan, EvalSampleRunPlan
from agent_ab.schemas.trace import validate_trace_token


class DashboardSummary(StrictBaseModel):
    source_plan_path: str | None = None
    eval_set_id: str | None = None
    total_samples: int = 0
    loaded_log_count: int = 0
    planned_count: int = 0
    passed_count: int = 0
    failed_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    pass_rate: float | None = None
    regression_count: int = 0
    triage_note_count: int = 0
    sandbox_denial_count: int = 0
    trace_link_count: int = 0
    artifact_count: int = 0
    message: str | None = None


class ScorerReadModel(StrictBaseModel):
    scorer_id: str
    type: str
    name: str
    passed: bool | None = None
    score: float | int | str | bool | None = None
    message: str | None = None


class TraceLinkReadModel(StrictBaseModel):
    eval_run_id: str
    trace_id: str
    path: str | None = None
    available: bool = True


class ArtifactReadModel(StrictBaseModel):
    name: str
    path: str
    kind: str | None = None


class SandboxStatusReadModel(StrictBaseModel):
    approval_count: int = 0
    denial_count: int = 0
    denied_tools: list[str] = Field(default_factory=list)
    policy_areas: list[str] = Field(default_factory=list)
    latest_denial_reason: str | None = None


class TriageNoteRequest(StrictBaseModel):
    id: str | None = None
    eval_task_id: str
    sample_id: str
    eval_run_id: str
    eval_log_path: str
    trace_id: str | None = None
    failure_taxonomy: str | None = None
    body: str
    status: str = "open"
    tags: list[str] = Field(default_factory=list)

    @field_validator("id", "eval_run_id", "trace_id")
    @classmethod
    def trace_tokens_are_valid(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return validate_trace_token(value, info.field_name)

    @field_validator("eval_task_id", "sample_id", "eval_log_path", "body", "status")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _non_blank(value, "triage note field")

    @field_validator("failure_taxonomy")
    @classmethod
    def optional_strings_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_blank(value, "triage note field")

    @field_validator("tags")
    @classmethod
    def tags_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "triage note tag")


class TriageNote(TriageNoteRequest):
    id: str
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)


class TriageNoteListResponse(StrictBaseModel):
    notes: list[TriageNote] = Field(default_factory=list)


class PlaygroundHandoffReadModel(StrictBaseModel):
    sample_id: str
    task_id: str
    variant_id: str | None = None
    eval_run_id: str
    eval_log_path: str
    trace_id: str | None = None
    query: str | None = None
    failure_taxonomy: str | None = None


class EvalRunReadModel(StrictBaseModel):
    eval_task_id: str
    eval_run_id: str
    sample_id: str
    taskpack_id: str
    task_id: str
    solver_id: str
    variant_id: str | None = None
    status: str
    query: str | None = None
    started_at_ms: int | None = None
    ended_at_ms: int | None = None
    duration_ms: int | None = None
    scorer_count: int = 0
    failed_scorer_count: int = 0
    scorers: list[ScorerReadModel] = Field(default_factory=list)
    avg_numeric_score: float | None = None
    failure_taxonomy: str | None = None
    trace: TraceLinkReadModel | None = None
    artifacts: list[ArtifactReadModel] = Field(default_factory=list)
    sandbox: SandboxStatusReadModel = Field(default_factory=SandboxStatusReadModel)
    eval_log_path: str
    playground_handoff: PlaygroundHandoffReadModel


class RegressionReadModel(StrictBaseModel):
    key: str
    comparison_kind: str
    comparison_label: str
    eval_task_id: str
    taskpack_id: str
    sample_id: str
    task_id: str
    solver_id: str
    previous_variant_id: str | None = None
    variant_id: str | None = None
    query: str | None = None
    previous_eval_run_id: str
    current_eval_run_id: str
    current_eval_log_path: str
    previous_status: str
    current_status: str
    previous_score: float | None = None
    current_score: float | None = None
    delta: float | None = None
    trace_id: str | None = None
    trace_path: str | None = None
    failure_taxonomy: str | None = None
    sandbox_denial_count: int = 0
    triage_note_count: int = 0
    latest_triage_note: TriageNote | None = None


class ExportLinkReadModel(StrictBaseModel):
    label: str
    kind: str
    format: str
    path: str
    url: str


class RegressionReviewReadModel(StrictBaseModel):
    rows: list[RegressionReadModel] = Field(default_factory=list)
    failure_taxonomy_options: list[str] = Field(default_factory=list)
    solver_options: list[str] = Field(default_factory=list)
    variant_options: list[str] = Field(default_factory=list)
    status_options: list[str] = Field(default_factory=list)
    export_links: list[ExportLinkReadModel] = Field(default_factory=list)
    triage_notes: list[TriageNote] = Field(default_factory=list)


class ObservabilityReadModel(StrictBaseModel):
    dashboard: DashboardSummary
    eval_rows: list[EvalRunReadModel] = Field(default_factory=list)
    regression_rows: list[RegressionReadModel] = Field(default_factory=list)
    trace_links: list[TraceLinkReadModel] = Field(default_factory=list)
    playground_handoffs: list[PlaygroundHandoffReadModel] = Field(default_factory=list)
    sandbox: SandboxStatusReadModel = Field(default_factory=SandboxStatusReadModel)
    regression_review: RegressionReviewReadModel = Field(default_factory=RegressionReviewReadModel)


def empty_observability_read_model(message: str | None = None) -> ObservabilityReadModel:
    return ObservabilityReadModel(
        dashboard=DashboardSummary(message=message),
    )


def build_observability_read_model(
    plan_path: str | Path,
    *,
    project_root: str | Path | None = None,
    triage_notes: list[TriageNote] | None = None,
) -> ObservabilityReadModel:
    """Build UI-facing read models from an EvalRunPlan and available EvalLogs."""

    plan_file = Path(plan_path)
    root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
    plan = EvalRunPlan.model_validate(json.loads(plan_file.read_text(encoding="utf-8")))
    loaded_by_run_id = _load_logs_by_run_id(plan, plan_file, root)
    rows = [
        _eval_row_from_sample_run(
            sample_run,
            loaded_by_run_id.get(sample_run.eval_run_id),
            plan_file,
            root,
        )
        for sample_run in plan.sample_runs
    ]
    notes = triage_notes or []
    regression_rows = _build_regression_rows(rows, notes)
    regression_review = RegressionReviewReadModel(
        rows=regression_rows,
        failure_taxonomy_options=unique_sorted(row.failure_taxonomy for row in regression_rows),
        solver_options=unique_sorted(row.solver_id for row in regression_rows),
        variant_options=unique_sorted(row.variant_id for row in regression_rows),
        status_options=unique_sorted(row.current_status for row in regression_rows),
        export_links=_export_links(plan_file, root),
        triage_notes=notes,
    )
    trace_links = [row.trace for row in rows if row.trace is not None]
    handoffs = [row.playground_handoff for row in rows if row.status in {"failed", "error"}]
    sandbox = _combine_sandbox_status(row.sandbox for row in rows)
    completed_rows = [row for row in rows if row.status in {"passed", "failed", "error", "skipped"}]
    passed_count = sum(row.status == "passed" for row in rows)
    failed_count = sum(row.status == "failed" for row in rows)
    error_count = sum(row.status == "error" for row in rows)
    skipped_count = sum(row.status == "skipped" for row in rows)

    return ObservabilityReadModel(
        dashboard=DashboardSummary(
            source_plan_path=_path_for_response(plan_file, root),
            eval_set_id=plan.eval_set_id,
            total_samples=plan.total_samples,
            loaded_log_count=len(loaded_by_run_id),
            planned_count=sum(row.status in {"planned", "skipped_completed"} for row in rows),
            passed_count=passed_count,
            failed_count=failed_count,
            error_count=error_count,
            skipped_count=skipped_count,
            pass_rate=passed_count / len(completed_rows) if completed_rows else None,
            regression_count=len(regression_rows),
            triage_note_count=len(notes),
            sandbox_denial_count=sandbox.denial_count,
            trace_link_count=len(trace_links),
            artifact_count=sum(len(row.artifacts) for row in rows),
        ),
        eval_rows=rows,
        regression_rows=regression_rows,
        trace_links=trace_links,
        playground_handoffs=handoffs,
        sandbox=sandbox,
        regression_review=regression_review,
    )


def load_triage_notes(path: str | Path) -> list[TriageNote]:
    notes_path = Path(path)
    if not notes_path.is_file():
        return []
    payload = json.loads(notes_path.read_text(encoding="utf-8"))
    notes = payload.get("notes") if isinstance(payload, dict) else payload
    if not isinstance(notes, list):
        raise ValueError(f"triage note store must contain a notes list: {notes_path}")
    return [TriageNote.model_validate(note) for note in notes]


def save_triage_note(path: str | Path, request: TriageNoteRequest, *, now_ms: int | None = None) -> TriageNote:
    notes_path = Path(path)
    timestamp = now_ms if now_ms is not None else int(time.time() * 1000)
    notes = load_triage_notes(notes_path)
    note_id = request.id or _next_triage_note_id(notes)
    existing = next((note for note in notes if note.id == note_id), None)
    note = TriageNote(
        **request.model_dump(exclude={"id"}),
        id=note_id,
        created_at_ms=existing.created_at_ms if existing else timestamp,
        updated_at_ms=timestamp,
    )
    notes = [item for item in notes if item.id != note_id]
    notes.append(note)
    notes.sort(key=lambda item: (item.updated_at_ms, item.id))
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(
        json.dumps({"notes": [item.model_dump(mode="json") for item in notes]}, indent=2),
        encoding="utf-8",
    )
    return note


def unique_sorted(values: Iterable[str | None]) -> list[str]:
    return sorted({value for value in values if value})


def find_latest_eval_plan(project_root: str | Path, runs_root: str | Path | None = None) -> Path | None:
    """Find the newest local EvalRunPlan artifact, if one exists."""

    root = Path(project_root).resolve()
    search_roots = [Path(runs_root).resolve()] if runs_root else [(root / "runs").resolve()]
    candidates: list[Path] = []
    for search_root in search_roots:
        if search_root.is_dir():
            candidates.extend(path for path in search_root.rglob("*.json") if _looks_like_plan(path))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _load_logs_by_run_id(plan: EvalRunPlan, plan_file: Path, project_root: Path) -> dict[str, LoadedEvalLog]:
    loaded: dict[str, LoadedEvalLog] = {}
    for sample_run in plan.sample_runs:
        log_path = _resolve_path(sample_run.eval_log_path, base_dir=plan_file.parent, project_root=project_root)
        if not log_path.is_file():
            continue
        payload = json.loads(log_path.read_text(encoding="utf-8"))
        log = EvalLog.model_validate(payload)
        loaded[log.eval_run_id] = LoadedEvalLog(path=_path_for_response(log_path, project_root), log=log)
    return loaded


def _eval_row_from_sample_run(
    sample_run: EvalSampleRunPlan,
    loaded: LoadedEvalLog | None,
    plan_file: Path,
    project_root: Path,
) -> EvalRunReadModel:
    log = loaded.log if loaded else None
    eval_log_path = _path_for_response(
        _resolve_path(sample_run.eval_log_path, base_dir=plan_file.parent, project_root=project_root),
        project_root,
    )
    failure_taxonomy = _failure_taxonomy(loaded)
    trace = _trace_link(log) if log and log.trace else None
    artifacts = [
        ArtifactReadModel(name=artifact.name, path=artifact.path, kind=artifact.kind)
        for artifact in (log.artifacts if log else [])
    ]
    sandbox = _sandbox_status(log.metadata.get("sandbox_events", []) if log else [])
    handoff = PlaygroundHandoffReadModel(
        sample_id=sample_run.sample_id,
        task_id=sample_run.task_id,
        variant_id=sample_run.variant_id,
        eval_run_id=sample_run.eval_run_id,
        eval_log_path=eval_log_path,
        trace_id=log.trace.trace_id if log and log.trace else None,
        query=_metadata_string(sample_run.metadata.get("query")),
        failure_taxonomy=failure_taxonomy,
    )
    status = str(log.status) if log else str(sample_run.status)
    scorer_results = list(log.scorer_results) if log else []
    return EvalRunReadModel(
        eval_task_id=sample_run.eval_task_id,
        eval_run_id=sample_run.eval_run_id,
        sample_id=sample_run.sample_id,
        taskpack_id=sample_run.taskpack_id,
        task_id=sample_run.task_id,
        solver_id=sample_run.solver_id,
        variant_id=sample_run.variant_id,
        status=status,
        query=_metadata_string(sample_run.metadata.get("query")),
        started_at_ms=log.started_at_ms if log else None,
        ended_at_ms=log.ended_at_ms if log else None,
        duration_ms=_duration_ms(log),
        scorer_count=len(scorer_results),
        failed_scorer_count=sum(result.passed is False for result in scorer_results),
        scorers=[
            ScorerReadModel(
                scorer_id=result.scorer_id,
                type=str(result.type),
                name=result.name,
                passed=result.passed,
                score=result.score,
                message=result.message,
            )
            for result in scorer_results
        ],
        avg_numeric_score=_average_numeric_score(result.score for result in scorer_results),
        failure_taxonomy=failure_taxonomy,
        trace=trace,
        artifacts=artifacts,
        sandbox=sandbox,
        eval_log_path=eval_log_path,
        playground_handoff=handoff,
    )


def _failure_taxonomy(loaded: LoadedEvalLog | None) -> str | None:
    if loaded is None:
        return None
    rows = build_eval_log_rows([loaded])
    return rows[0].failure_taxonomy if rows else None


def _trace_link(log: EvalLog) -> TraceLinkReadModel | None:
    if log.trace is None:
        return None
    return TraceLinkReadModel(
        eval_run_id=log.eval_run_id,
        trace_id=log.trace.trace_id,
        path=log.trace.path,
        available=True,
    )


def _sandbox_status(events: Any) -> SandboxStatusReadModel:
    if not isinstance(events, list):
        return SandboxStatusReadModel()
    approvals = 0
    denials = 0
    denied_tools: list[str] = []
    policy_areas: list[str] = []
    latest_denial_reason = None
    for event in events:
        if not isinstance(event, dict):
            continue
        decision = event.get("decision")
        if decision == "approved" or event.get("event_type") == "tool_approval":
            approvals += 1
        if decision == "denied" or event.get("event_type") == "tool_denial":
            denials += 1
            latest_denial_reason = _metadata_string(event.get("reason")) or latest_denial_reason
            denied_tools.append(_metadata_string(event.get("tool_name")) or "unknown")
            policy_areas.append(_metadata_string(event.get("policy_area")) or "unknown")
    return SandboxStatusReadModel(
        approval_count=approvals,
        denial_count=denials,
        denied_tools=sorted(set(denied_tools)),
        policy_areas=sorted(set(policy_areas)),
        latest_denial_reason=latest_denial_reason,
    )


def _combine_sandbox_status(statuses: Iterable[SandboxStatusReadModel]) -> SandboxStatusReadModel:
    approvals = 0
    denials = 0
    denied_tools: list[str] = []
    policy_areas: list[str] = []
    latest_denial_reason = None
    for status in statuses:
        approvals += status.approval_count
        denials += status.denial_count
        denied_tools.extend(status.denied_tools)
        policy_areas.extend(status.policy_areas)
        latest_denial_reason = status.latest_denial_reason or latest_denial_reason
    return SandboxStatusReadModel(
        approval_count=approvals,
        denial_count=denials,
        denied_tools=sorted(set(denied_tools)),
        policy_areas=sorted(set(policy_areas)),
        latest_denial_reason=latest_denial_reason,
    )


def _build_regression_rows(rows: list[EvalRunReadModel], notes: list[TriageNote]) -> list[RegressionReadModel]:
    regressions = [
        *_build_repeated_run_regressions(rows, notes),
        *_build_variant_regressions(rows, notes),
    ]
    return sorted(
        regressions,
        key=lambda row: (
            row.eval_task_id,
            row.sample_id,
            row.solver_id,
            row.comparison_kind,
            row.variant_id or "",
            row.current_eval_run_id,
        ),
    )


def _build_repeated_run_regressions(rows: list[EvalRunReadModel], notes: list[TriageNote]) -> list[RegressionReadModel]:
    grouped: dict[tuple[str, str, str, str | None], list[EvalRunReadModel]] = {}
    for row in rows:
        grouped.setdefault((row.eval_task_id, row.sample_id, row.solver_id, row.variant_id), []).append(row)

    regressions: list[RegressionReadModel] = []
    for group in grouped.values():
        if len(group) < 2:
            continue
        sorted_group = sorted(
            group,
            key=lambda row: (
                row.started_at_ms is None,
                row.started_at_ms or 0,
                row.eval_run_id,
            ),
        )
        previous, current = sorted_group[-2], sorted_group[-1]
        if _row_regressed(previous, current):
            regressions.append(
                _regression_row(
                    previous,
                    current,
                    notes,
                    comparison_kind="repeated_run",
                    comparison_label="Repeated run",
                )
            )
    return regressions


def _build_variant_regressions(rows: list[EvalRunReadModel], notes: list[TriageNote]) -> list[RegressionReadModel]:
    grouped: dict[tuple[str, str, str], list[EvalRunReadModel]] = {}
    for row in rows:
        grouped.setdefault((row.eval_task_id, row.sample_id, row.solver_id), []).append(row)

    regressions: list[RegressionReadModel] = []
    for group in grouped.values():
        latest_by_variant: dict[str | None, EvalRunReadModel] = {}
        for row in sorted(
            group,
            key=lambda item: (
                item.started_at_ms is None,
                item.started_at_ms or 0,
                item.eval_run_id,
            ),
        ):
            latest_by_variant[row.variant_id] = row
        if len(latest_by_variant) < 2:
            continue
        ordered = sorted(latest_by_variant.values(), key=_comparison_sort_key)
        reference = ordered[0]
        for current in ordered[1:]:
            if _row_regressed(reference, current):
                regressions.append(
                    _regression_row(
                        reference,
                        current,
                        notes,
                        comparison_kind="variant",
                        comparison_label=f"{reference.variant_id or '-'} vs {current.variant_id or '-'}",
                    )
                )
    return regressions


def _regression_row(
    previous: EvalRunReadModel,
    current: EvalRunReadModel,
    notes: list[TriageNote],
    *,
    comparison_kind: str,
    comparison_label: str,
) -> RegressionReadModel:
    delta = None
    if previous.avg_numeric_score is not None and current.avg_numeric_score is not None:
        delta = current.avg_numeric_score - previous.avg_numeric_score
    matching_notes = _matching_triage_notes(notes, current)
    latest_note = max(matching_notes, key=lambda note: (note.updated_at_ms, note.id), default=None)
    return RegressionReadModel(
        key="|".join(
            [
                comparison_kind,
                current.eval_task_id,
                current.sample_id,
                current.solver_id,
                previous.variant_id or "-",
                current.variant_id or "-",
                previous.eval_run_id,
                current.eval_run_id,
            ]
        ),
        comparison_kind=comparison_kind,
        comparison_label=comparison_label,
        eval_task_id=current.eval_task_id,
        taskpack_id=current.taskpack_id,
        sample_id=current.sample_id,
        task_id=current.task_id,
        solver_id=current.solver_id,
        previous_variant_id=previous.variant_id,
        variant_id=current.variant_id,
        query=current.query,
        previous_eval_run_id=previous.eval_run_id,
        current_eval_run_id=current.eval_run_id,
        current_eval_log_path=current.eval_log_path,
        previous_status=previous.status,
        current_status=current.status,
        previous_score=previous.avg_numeric_score,
        current_score=current.avg_numeric_score,
        delta=delta,
        trace_id=current.trace.trace_id if current.trace else None,
        trace_path=current.trace.path if current.trace else None,
        failure_taxonomy=current.failure_taxonomy,
        sandbox_denial_count=current.sandbox.denial_count,
        triage_note_count=len(matching_notes),
        latest_triage_note=latest_note,
    )


def _row_regressed(previous: EvalRunReadModel, current: EvalRunReadModel) -> bool:
    status_regressed = _status_rank(current.status) > _status_rank(previous.status)
    score_regressed = (
        previous.avg_numeric_score is not None
        and current.avg_numeric_score is not None
        and current.avg_numeric_score < previous.avg_numeric_score
    )
    return status_regressed or score_regressed


def _comparison_sort_key(row: EvalRunReadModel) -> tuple[int, float, str, str]:
    score_rank = row.avg_numeric_score if row.avg_numeric_score is not None else -1.0
    return (
        _status_rank(row.status),
        -score_rank,
        row.variant_id or "",
        row.eval_run_id,
    )


def _matching_triage_notes(notes: list[TriageNote], row: EvalRunReadModel) -> list[TriageNote]:
    return [
        note
        for note in notes
        if note.eval_run_id == row.eval_run_id
        or (
            note.eval_task_id == row.eval_task_id
            and note.sample_id == row.sample_id
        )
    ]


def _export_links(plan_file: Path, project_root: Path) -> list[ExportLinkReadModel]:
    plan_path = _path_for_response(plan_file, project_root)
    plan_stem = plan_file.stem
    links: list[ExportLinkReadModel] = []
    for kind, label in {
        "eval_logs": "Eval logs",
        "eval_aggregates": "Eval aggregates",
        "eval_findings": "Eval findings",
    }.items():
        for report_format in ("json", "csv"):
            output_path = project_root / "reports" / "observability" / f"{plan_stem}_{kind}.{report_format}"
            query = urlencode({"kind": kind, "format": report_format, "plan_path": plan_path})
            links.append(
                ExportLinkReadModel(
                    label=f"{label} {report_format.upper()}",
                    kind=kind,
                    format=report_format,
                    path=_path_for_response(output_path, project_root),
                    url=f"/observability/export?{query}",
                )
            )
    return links


def _duration_ms(log: EvalLog | None) -> int | None:
    if log is None or log.started_at_ms is None or log.ended_at_ms is None:
        return None
    return log.ended_at_ms - log.started_at_ms


def _average_numeric_score(values: Iterable[float | int | str | bool | None]) -> float | None:
    numeric_values: list[float] = []
    for value in values:
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            numeric_values.append(float(value))
    if not numeric_values:
        return None
    return sum(numeric_values) / len(numeric_values)


def _status_rank(status: str) -> int:
    return {
        "passed": 0,
        "skipped": 1,
        "planned": 1,
        "skipped_completed": 1,
        "failed": 2,
        "error": 3,
    }.get(status, 1)


def _next_triage_note_id(notes: list[TriageNote]) -> str:
    index = len(notes) + 1
    existing_ids = {note.id for note in notes}
    while f"triage.{index}" in existing_ids:
        index += 1
    return f"triage.{index}"


def _metadata_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _resolve_path(path: str | Path, *, base_dir: Path, project_root: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    project_candidate = (project_root / candidate).resolve()
    if project_candidate.exists():
        return project_candidate
    return (base_dir / candidate).resolve()


def _path_for_response(path: str | Path, project_root: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(project_root).as_posix()
    except ValueError:
        return str(resolved)


def _looks_like_plan(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and "eval_set_id" in payload and "sample_runs" in payload
