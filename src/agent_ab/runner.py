"""Deterministic local runner core and mock adapter."""

from __future__ import annotations

import shutil
from pathlib import Path

from agent_ab.config import validate_taskpack_with_fixtures
from agent_ab.schemas.run import MetricResult, RunStatus, TaskRunResult, ValidatorRunResult
from agent_ab.schemas.task import TaskCase, TaskValidator
from agent_ab.schemas.trace import (
    ScoringDetail,
    SpanKind,
    ToolCallDetail,
    TraceEnvelope,
    TraceSpan,
    ValidatorDetail,
    validate_trace_token,
)
from agent_ab.trace_store import index_trace_sqlite, write_trace_jsonl
from agent_ab.validators import execute_task_validator, resolve_workspace_path


class MockAdapter:
    """Deterministic adapter that mutates the workspace to satisfy simple validators."""

    name = "mock"

    def apply(self, task: TaskCase, workspace_path: Path) -> None:
        for validator in task.validators:
            self._apply_validator_goal(validator, workspace_path)

    def _apply_validator_goal(self, validator: TaskValidator, workspace_path: Path) -> None:
        if validator.path is None or validator.type.startswith("custom."):
            return

        target = resolve_workspace_path(workspace_path, validator.path)
        if validator.type in {"file_exists", "file_contains", "file_matches_regex"}:
            target.parent.mkdir(parents=True, exist_ok=True)
            if validator.type == "file_contains" and validator.contains is not None:
                target.write_text(validator.contains, encoding="utf-8")
            elif not target.exists():
                target.write_text("", encoding="utf-8")
            return

        if validator.type == "file_not_exists" and target.is_file():
            target.unlink()
            return

        if validator.type == "file_not_contains" and validator.contains is not None and target.exists():
            content = target.read_text(encoding="utf-8")
            target.write_text(content.replace(validator.contains, ""), encoding="utf-8")


def prepare_run_workspace(taskpack_path: str | Path, task: TaskCase, run_root: str | Path, run_id: str) -> Path:
    taskpack_root = Path(taskpack_path).parent
    source_fixture = (taskpack_root / task.workspace.fixture).resolve()
    safe_run_id = validate_trace_token(run_id, "run_id")
    run_root_path = Path(run_root).resolve()
    run_dir = (run_root_path / safe_run_id).resolve()
    if run_dir != run_root_path and run_root_path not in run_dir.parents:
        raise ValueError(f"run directory escapes run root: {run_id}")
    workspace_path = run_dir / "workspace"
    if run_dir.exists():
        raise FileExistsError(f"run directory already exists: {run_dir}")
    workspace_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_fixture, workspace_path)
    return workspace_path


def run_mock_task(
    taskpack_path: str | Path,
    task_id: str,
    run_root: str | Path,
    *,
    run_id: str | None = None,
    variant_id: str = "mock",
) -> TaskRunResult:
    taskpack = validate_taskpack_with_fixtures(taskpack_path)
    tasks = {task.id: task for task in taskpack.tasks}
    if task_id not in tasks:
        raise ValueError(f"task id not found in taskpack: {task_id}")

    task = tasks[task_id]
    effective_run_id = validate_trace_token(run_id or f"mock.{task.id}.1", "run_id")
    variant_id = validate_trace_token(variant_id, "variant_id")
    trace_id = f"trace.{effective_run_id}"
    workspace_path = prepare_run_workspace(taskpack_path, task, run_root, effective_run_id)

    adapter = MockAdapter()
    adapter.apply(task, workspace_path)
    validator_results = [
        execute_task_validator(validator, workspace_path)
        for validator in task.validators
    ]
    passed = all(result.passed for result in validator_results)
    status = RunStatus.PASSED if passed else RunStatus.FAILED
    metrics = [
        MetricResult(name="task_success", value=1.0 if passed else 0.0),
        MetricResult(
            name="validator_pass_rate",
            value=sum(result.passed for result in validator_results) / len(validator_results),
        ),
        MetricResult(name="step_count", value=1),
    ]

    trace = _build_mock_trace(
        trace_id=trace_id,
        taskpack_id=taskpack.id,
        task_id=task.id,
        variant_id=variant_id,
        run_id=effective_run_id,
        validator_results=validator_results,
        metrics=metrics,
    )
    run_dir = Path(run_root) / effective_run_id
    trace_jsonl = run_dir / "trace.jsonl"
    trace_sqlite = run_dir / "trace.sqlite"
    write_trace_jsonl(trace_jsonl, trace)
    index_trace_sqlite(trace_sqlite, trace)

    return TaskRunResult(
        run_id=effective_run_id,
        trace_id=trace.trace_id,
        task_id=task.id,
        variant_id=variant_id,
        status=status,
        workspace_path=workspace_path,
        validator_results=validator_results,
        metrics=metrics,
        trace=trace,
        artifacts={"trace_jsonl": trace_jsonl, "trace_sqlite": trace_sqlite},
    )


def _build_mock_trace(
    *,
    trace_id: str,
    taskpack_id: str,
    task_id: str,
    variant_id: str,
    run_id: str,
    validator_results: list[ValidatorRunResult],
    metrics: list[MetricResult],
) -> TraceEnvelope:
    validator_spans = [
        TraceSpan(
            trace_id=trace_id,
            span_id=f"span.validator.{index}",
            parent_span_id="span.validators",
            name=result.validator_type,
            kind=SpanKind.VALIDATOR,
            started_at_ms=300 + index,
            ended_at_ms=301 + index,
            validator=ValidatorDetail(
                validator_type=result.validator_type,
                path=result.path,
                passed=result.passed,
                expected=result.expected,
                observed=result.observed,
            ),
        )
        for index, result in enumerate(validator_results, start=1)
    ]
    return TraceEnvelope(
        trace_id=trace_id,
        taskpack_id=taskpack_id,
        task_id=task_id,
        variant_id=variant_id,
        run_id=run_id,
        created_at_ms=0,
        spans=[
            TraceSpan(
                trace_id=trace_id,
                span_id="span.root",
                name=task_id,
                kind=SpanKind.TASK_RUN,
                started_at_ms=0,
                ended_at_ms=500,
            ),
            TraceSpan(
                trace_id=trace_id,
                span_id="span.setup",
                parent_span_id="span.root",
                name="setup_workspace",
                kind=SpanKind.SETUP,
                started_at_ms=0,
                ended_at_ms=100,
            ),
            TraceSpan(
                trace_id=trace_id,
                span_id="span.mock",
                parent_span_id="span.root",
                name="mock_adapter",
                kind=SpanKind.TOOL,
                started_at_ms=100,
                ended_at_ms=250,
                tool_call=ToolCallDetail(
                    tool_name="mock_adapter",
                    arguments={"mode": "satisfy_declared_validators"},
                    result_preview="workspace mutated deterministically",
                ),
            ),
            TraceSpan(
                trace_id=trace_id,
                span_id="span.validators",
                parent_span_id="span.root",
                name="validators",
                kind=SpanKind.CUSTOM,
                started_at_ms=300,
                ended_at_ms=400,
            ),
            *validator_spans,
            TraceSpan(
                trace_id=trace_id,
                span_id="span.scoring",
                parent_span_id="span.root",
                name="scoring",
                kind=SpanKind.SCORING,
                started_at_ms=450,
                ended_at_ms=500,
                scoring=ScoringDetail(metrics={metric.name: metric.value for metric in metrics}),
            ),
        ],
    )
