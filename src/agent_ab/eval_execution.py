"""Guarded EvalRunPlan execution harness for deterministic local adapters."""

from __future__ import annotations

import json
from enum import Enum
from hashlib import sha1
from pathlib import Path
from typing import Any

from pydantic import Field

from agent_ab.analysis import load_eval_run_plan
from agent_ab.config import ConfigLoadError, load_eval_set, validate_eval_task_with_taskpack
from agent_ab.guardrails import GuardrailViolation
from agent_ab.runner import run_mock_task
from agent_ab.sandbox import (
    sandbox_approval_event,
    sandbox_denial_event_from_violation,
    sandbox_provider_from_run_limits,
)
from agent_ab.schemas.common import StrictBaseModel
from agent_ab.schemas.eval import (
    EvalArtifactRef,
    EvalLog,
    EvalRunPlan,
    EvalRunPlanStatus,
    EvalSampleRunPlan,
    EvalScorerRef,
    EvalScorerResult,
    EvalScorerType,
    EvalTask,
    EvalTraceReference,
)
from agent_ab.schemas.run import TaskRunResult
from agent_ab.schemas.sandbox import (
    SandboxEvent,
    SandboxPolicyArea,
    SandboxProvider,
    sandbox_events_metadata,
)


class EvalExecutionRowStatus(str, Enum):
    DRY_RUN = "dry_run"
    EXECUTED = "executed"
    SKIPPED_COMPLETED = "skipped_completed"
    BLOCKED = "blocked"
    ERROR = "error"
    STOPPED = "stopped"


class SolverDispatchMode(str, Enum):
    MOCK = "mock"
    BLOCKED = "blocked"


class SolverAdapterDispatch(StrictBaseModel):
    """Resolved adapter dispatch decision for one planned sample."""

    solver_id: str
    adapter: str
    mode: SolverDispatchMode
    reason: str


class EvalExecutionRow(StrictBaseModel):
    eval_run_id: str
    eval_task_id: str
    sample_id: str
    task_id: str
    solver_id: str
    variant_id: str | None = None
    adapter: str
    status: EvalExecutionRowStatus
    eval_log_path: str
    run_root: str
    sandbox_provider_id: str
    command_preview: list[str] = Field(default_factory=list)
    guardrail_decisions: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None


class EvalExecutionSummary(StrictBaseModel):
    plan_path: str
    dry_run: bool
    selected_count: int = 0
    dry_run_count: int = 0
    executed_count: int = 0
    skipped_count: int = 0
    blocked_count: int = 0
    error_count: int = 0
    stopped_count: int = 0
    rows: list[EvalExecutionRow] = Field(default_factory=list)


class _EvalTaskContext(StrictBaseModel):
    eval_task: EvalTask
    taskpack_path: Path


def execute_eval_run_plan(
    plan_path: str | Path,
    *,
    dry_run: bool = True,
    eval_task_ids: list[str] | None = None,
    sample_ids: list[str] | None = None,
    solver_ids: list[str] | None = None,
    variant_ids: list[str] | None = None,
    max_failures: int | None = None,
    resume: bool = True,
) -> EvalExecutionSummary:
    """Execute selected EvalRunPlan rows through guarded local adapter dispatch.

    The only adapter that runs in Module 20 is the deterministic mock adapter.
    Every other solver adapter is converted into an EvalLog-compatible sandbox
    denial record unless this function is extended by a future gated adapter.
    """

    plan_path = Path(plan_path)
    plan = load_eval_run_plan(plan_path)
    task_contexts = _load_eval_task_contexts(plan)
    effective_max_failures = plan.max_failures if max_failures is None else max_failures
    rows: list[EvalExecutionRow] = []
    failure_count = 0

    for index, sample_run in enumerate(plan.sample_runs, start=1):
        if not _matches_filters(sample_run, eval_task_ids, sample_ids, solver_ids, variant_ids):
            continue
        if _failure_limit_reached(failure_count, effective_max_failures):
            rows.append(_stopped_row(plan, sample_run, task_contexts, index, "max_failures reached"))
            continue

        row = _execute_sample_row(
            plan=plan,
            sample_run=sample_run,
            task_contexts=task_contexts,
            event_index=index,
            dry_run=dry_run,
            resume=resume,
        )
        rows.append(row)
        if row.status in {
            EvalExecutionRowStatus.BLOCKED,
            EvalExecutionRowStatus.ERROR,
        }:
            failure_count += 1

    return _summary(plan_path, dry_run, rows)


def _execute_sample_row(
    *,
    plan: EvalRunPlan,
    sample_run: EvalSampleRunPlan,
    task_contexts: dict[str, _EvalTaskContext],
    event_index: int,
    dry_run: bool,
    resume: bool,
) -> EvalExecutionRow:
    context = _context_for_sample(sample_run, task_contexts)
    provider = _sandbox_provider_for_sample(plan, sample_run)
    command_preview = _mock_command_preview(context.taskpack_path, sample_run)
    dispatch = _dispatch_for_solver(context.eval_task)
    eval_log_path = Path(sample_run.eval_log_path)
    run_root = eval_log_path.parent

    if resume and _has_completed_eval_log(eval_log_path):
        return _row(
            sample_run,
            context,
            provider,
            EvalExecutionRowStatus.SKIPPED_COMPLETED,
            command_preview,
            [],
            "completed EvalLog already exists",
        )

    if dispatch.mode == SolverDispatchMode.BLOCKED:
        denial = _adapter_denial_event(provider, dispatch, command_preview, event_index)
        if not dry_run:
            _write_blocked_eval_log(
                sample_run=sample_run,
                eval_task=context.eval_task,
                eval_log_path=eval_log_path,
                provider=provider,
                event=denial,
                reason=dispatch.reason,
            )
        return _row(
            sample_run,
            context,
            provider,
            EvalExecutionRowStatus.BLOCKED,
            command_preview,
            [denial],
            dispatch.reason,
        )

    approvals = _approval_events(provider, sample_run, run_root, command_preview, event_index)
    if dry_run or sample_run.status == EvalRunPlanStatus.SKIPPED_COMPLETED:
        return _row(
            sample_run,
            context,
            provider,
            EvalExecutionRowStatus.DRY_RUN,
            command_preview,
            approvals,
            "dry-run only; no adapter launched",
        )

    try:
        result = run_mock_task(
            context.taskpack_path,
            sample_run.task_id,
            run_root,
            run_id=_adapter_run_id(sample_run),
            variant_id=sample_run.variant_id or sample_run.solver_id,
        )
        _write_mock_eval_log(
            sample_run=sample_run,
            eval_task=context.eval_task,
            eval_log_path=eval_log_path,
            provider=provider,
            events=approvals,
            result=result,
        )
    except (ConfigLoadError, FileExistsError, OSError, ValueError) as exc:
        _write_error_eval_log(
            sample_run=sample_run,
            eval_log_path=eval_log_path,
            provider=provider,
            events=approvals,
            code="execution_error",
            message=str(exc),
        )
        return _row(
            sample_run,
            context,
            provider,
            EvalExecutionRowStatus.ERROR,
            command_preview,
            approvals,
            str(exc),
        )

    return _row(
        sample_run,
        context,
        provider,
        EvalExecutionRowStatus.EXECUTED,
        command_preview,
        approvals,
        "deterministic mock adapter completed",
    )


def _load_eval_task_contexts(plan: EvalRunPlan) -> dict[str, _EvalTaskContext]:
    source_eval_set = plan.metadata.get("source_eval_set")
    if not isinstance(source_eval_set, str) or not source_eval_set.strip():
        raise ValueError("EvalRunPlan.metadata.source_eval_set is required for guarded execution")

    eval_set_path = Path(source_eval_set)
    eval_set = load_eval_set(eval_set_path)
    contexts: dict[str, _EvalTaskContext] = {}
    for _ref_id, eval_task_path in eval_set.eval_task_paths(eval_set_path.parent).items():
        eval_task, _taskpack, _samples = validate_eval_task_with_taskpack(eval_task_path)
        if eval_task.id in contexts:
            raise ValueError(f"duplicate EvalTask id in source EvalSet: {eval_task.id}")
        contexts[eval_task.id] = _EvalTaskContext(
            eval_task=eval_task,
            taskpack_path=eval_task.taskpack_path(eval_task_path.parent),
        )
    return contexts


def _context_for_sample(
    sample_run: EvalSampleRunPlan,
    task_contexts: dict[str, _EvalTaskContext],
) -> _EvalTaskContext:
    try:
        return task_contexts[sample_run.eval_task_id]
    except KeyError as exc:
        raise ValueError(f"EvalRunPlan references unknown EvalTask: {sample_run.eval_task_id}") from exc


def _sandbox_provider_for_sample(plan: EvalRunPlan, sample_run: EvalSampleRunPlan) -> SandboxProvider:
    eval_log_path = Path(sample_run.eval_log_path)
    return sandbox_provider_from_run_limits(
        f"sandbox.{sample_run.eval_task_id}.{sample_run.sample_id}",
        sample_run.limits,
        artifact_root=str(eval_log_path.parent),
        sqlite_path=str(eval_log_path.parent / _adapter_run_id(sample_run) / "trace.sqlite"),
        description=f"Resolved from EvalRunPlan {plan.eval_set_id} sample {sample_run.sample_id}.",
    )


def _dispatch_for_solver(eval_task: EvalTask) -> SolverAdapterDispatch:
    if eval_task.solver.adapter == "mock":
        return SolverAdapterDispatch(
            solver_id=eval_task.solver.id,
            adapter=eval_task.solver.adapter,
            mode=SolverDispatchMode.MOCK,
            reason="deterministic mock adapter is allowed by the Module 20 harness",
        )
    return SolverAdapterDispatch(
        solver_id=eval_task.solver.id,
        adapter=eval_task.solver.adapter,
        mode=SolverDispatchMode.BLOCKED,
        reason=(
            f"adapter '{eval_task.solver.adapter}' is blocked by the guarded eval harness; "
            "only deterministic mock execution is enabled in Module 20"
        ),
    )


def _mock_command_preview(taskpack_path: Path, sample_run: EvalSampleRunPlan) -> list[str]:
    return [
        "agent-ab",
        "run-mock-task",
        str(taskpack_path),
        sample_run.task_id,
        "--run-root",
        str(Path(sample_run.eval_log_path).parent),
        "--run-id",
        _adapter_run_id(sample_run),
    ]


def _approval_events(
    provider: SandboxProvider,
    sample_run: EvalSampleRunPlan,
    run_root: Path,
    command_preview: list[str],
    event_index: int,
) -> list[SandboxEvent]:
    return [
        sandbox_approval_event(
            event_id=f"sandbox_approval.{event_index}.workspace",
            provider_id=provider.id,
            tool_name="eval_harness",
            policy_area=SandboxPolicyArea.WORKSPACE,
            reason="Sandbox provider resolved before sample execution.",
            requested_action="resolve_sample_workspace",
            path=run_root,
        ),
        sandbox_approval_event(
            event_id=f"sandbox_approval.{event_index}.mock",
            provider_id=provider.id,
            tool_name="mock_solver",
            policy_area=SandboxPolicyArea.COMMAND,
            reason="Deterministic mock adapter is allowed by the guarded harness.",
            requested_action="execute_mock_adapter",
            command=command_preview,
        ),
    ]


def _adapter_denial_event(
    provider: SandboxProvider,
    dispatch: SolverAdapterDispatch,
    command_preview: list[str],
    event_index: int,
) -> SandboxEvent:
    return sandbox_denial_event_from_violation(
        event_id=f"sandbox_denial.{event_index}.adapter",
        provider_id=provider.id,
        tool_name=dispatch.adapter,
        policy_area=SandboxPolicyArea.COMMAND,
        violation=GuardrailViolation(dispatch.reason),
        requested_action="execute_solver_adapter",
        command=command_preview,
    )


def _write_mock_eval_log(
    *,
    sample_run: EvalSampleRunPlan,
    eval_task: EvalTask,
    eval_log_path: Path,
    provider: SandboxProvider,
    events: list[SandboxEvent],
    result: TaskRunResult,
) -> None:
    log = EvalLog(
        eval_task_id=sample_run.eval_task_id,
        eval_task_version=sample_run.eval_task_version,
        eval_run_id=sample_run.eval_run_id,
        sample_id=sample_run.sample_id,
        taskpack_id=sample_run.taskpack_id,
        task_id=sample_run.task_id,
        solver_id=sample_run.solver_id,
        variant_id=sample_run.variant_id,
        status=_status_value(result.status),
        started_at_ms=result.trace.created_at_ms,
        ended_at_ms=_trace_ended_at_ms(result),
        scorer_results=_scorer_results(eval_task.scorers, result),
        trace=EvalTraceReference(
            trace_id=result.trace_id,
            run_id=result.run_id,
            path=str(result.artifacts["trace_jsonl"]),
        ),
        artifacts=[
            EvalArtifactRef(name=name, path=str(path), kind=_artifact_kind(name))
            for name, path in result.artifacts.items()
        ],
        limits=sample_run.limits,
        metadata=_execution_metadata(provider, "mock", False, events),
    )
    _write_eval_log(eval_log_path, log)


def _write_blocked_eval_log(
    *,
    sample_run: EvalSampleRunPlan,
    eval_task: EvalTask,
    eval_log_path: Path,
    provider: SandboxProvider,
    event: SandboxEvent,
    reason: str,
) -> None:
    log = EvalLog(
        eval_task_id=sample_run.eval_task_id,
        eval_task_version=sample_run.eval_task_version,
        eval_run_id=sample_run.eval_run_id,
        sample_id=sample_run.sample_id,
        taskpack_id=sample_run.taskpack_id,
        task_id=sample_run.task_id,
        solver_id=sample_run.solver_id,
        variant_id=sample_run.variant_id,
        status="error",
        limits=sample_run.limits,
        errors=[
            {
                "code": "adapter_blocked",
                "message": reason,
            }
        ],
        metadata=_execution_metadata(provider, eval_task.solver.adapter, False, [event]),
    )
    _write_eval_log(eval_log_path, log)


def _write_error_eval_log(
    *,
    sample_run: EvalSampleRunPlan,
    eval_log_path: Path,
    provider: SandboxProvider,
    events: list[SandboxEvent],
    code: str,
    message: str,
) -> None:
    log = EvalLog(
        eval_task_id=sample_run.eval_task_id,
        eval_task_version=sample_run.eval_task_version,
        eval_run_id=sample_run.eval_run_id,
        sample_id=sample_run.sample_id,
        taskpack_id=sample_run.taskpack_id,
        task_id=sample_run.task_id,
        solver_id=sample_run.solver_id,
        variant_id=sample_run.variant_id,
        status="error",
        limits=sample_run.limits,
        errors=[
            {
                "code": code,
                "message": message,
            }
        ],
        metadata=_execution_metadata(provider, "mock", False, events),
    )
    _write_eval_log(eval_log_path, log)


def _write_eval_log(path: Path, log: EvalLog) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log.model_dump(mode="json"), indent=2), encoding="utf-8")


def _scorer_results(scorers: list[EvalScorerRef], result: TaskRunResult) -> list[EvalScorerResult]:
    metrics = {metric.name: metric.value for metric in result.metrics}
    validator_pass_rate = metrics.get("validator_pass_rate")
    validator_passed = all(validator.passed for validator in result.validator_results)
    rows: list[EvalScorerResult] = []
    for scorer in scorers:
        if scorer.type == EvalScorerType.VALIDATOR:
            score = validator_pass_rate
            passed = validator_passed
        elif scorer.type == EvalScorerType.METRIC:
            score = metrics.get(scorer.name)
            passed = _score_passes(score, scorer.threshold)
        else:
            score = None
            passed = None
        rows.append(
            EvalScorerResult(
                scorer_id=scorer.id,
                type=scorer.type,
                name=scorer.name,
                passed=passed,
                score=score,
                message=None if passed is not False else f"Scorer failed: {scorer.id}",
            )
        )
    return rows


def _score_passes(score: float | int | str | bool | None, threshold: float | int | None) -> bool | None:
    if isinstance(score, bool):
        return score
    if threshold is None:
        return None if score is None else bool(score)
    if isinstance(score, (int, float)):
        return float(score) >= float(threshold)
    return None


def _status_value(status: Any) -> str:
    value = getattr(status, "value", status)
    return str(value)


def _trace_ended_at_ms(result: TaskRunResult) -> int | None:
    ended_values = [span.ended_at_ms for span in result.trace.spans if span.ended_at_ms is not None]
    return max(ended_values) if ended_values else None


def _artifact_kind(name: str) -> str:
    if name.endswith("jsonl"):
        return "trace"
    if name.endswith("sqlite"):
        return "index"
    return "artifact"


def _execution_metadata(
    provider: SandboxProvider,
    adapter: str,
    dry_run: bool,
    events: list[SandboxEvent],
) -> dict[str, Any]:
    metadata = {
        "execution": {
            "adapter": adapter,
            "dry_run": dry_run,
            "harness": "module20_guarded_eval_execution",
        },
        "sandbox_provider": provider.model_dump(mode="json"),
    }
    metadata.update(sandbox_events_metadata(events))
    return metadata


def _adapter_run_id(sample_run: EvalSampleRunPlan) -> str:
    digest = sha1(sample_run.eval_run_id.encode("utf-8")).hexdigest()[:12]
    return f"mock.{digest}"


def _has_completed_eval_log(path: Path) -> bool:
    if not path.is_file():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    EvalLog.model_validate(payload)
    return True


def _matches_filters(
    sample_run: EvalSampleRunPlan,
    eval_task_ids: list[str] | None,
    sample_ids: list[str] | None,
    solver_ids: list[str] | None,
    variant_ids: list[str] | None,
) -> bool:
    return (
        _matches(eval_task_ids, sample_run.eval_task_id)
        and _matches(sample_ids, sample_run.sample_id)
        and _matches(solver_ids, sample_run.solver_id)
        and _matches(variant_ids, sample_run.variant_id)
    )


def _matches(values: list[str] | None, candidate: str | None) -> bool:
    return not values or candidate in set(values)


def _failure_limit_reached(failure_count: int, max_failures: int | None) -> bool:
    return max_failures is not None and failure_count > 0 and failure_count >= max_failures


def _stopped_row(
    plan: EvalRunPlan,
    sample_run: EvalSampleRunPlan,
    task_contexts: dict[str, _EvalTaskContext],
    event_index: int,
    reason: str,
) -> EvalExecutionRow:
    context = _context_for_sample(sample_run, task_contexts)
    provider = _sandbox_provider_for_sample(plan, sample_run)
    return _row(
        sample_run,
        context,
        provider,
        EvalExecutionRowStatus.STOPPED,
        _mock_command_preview(context.taskpack_path, sample_run),
        [],
        reason,
    )


def _row(
    sample_run: EvalSampleRunPlan,
    context: _EvalTaskContext,
    provider: SandboxProvider,
    status: EvalExecutionRowStatus,
    command_preview: list[str],
    events: list[SandboxEvent],
    reason: str | None,
) -> EvalExecutionRow:
    return EvalExecutionRow(
        eval_run_id=sample_run.eval_run_id,
        eval_task_id=sample_run.eval_task_id,
        sample_id=sample_run.sample_id,
        task_id=sample_run.task_id,
        solver_id=sample_run.solver_id,
        variant_id=sample_run.variant_id,
        adapter=context.eval_task.solver.adapter,
        status=status,
        eval_log_path=sample_run.eval_log_path,
        run_root=str(Path(sample_run.eval_log_path).parent),
        sandbox_provider_id=provider.id,
        command_preview=command_preview,
        guardrail_decisions=[event.model_dump(mode="json") for event in events],
        reason=reason,
    )


def _summary(plan_path: Path, dry_run: bool, rows: list[EvalExecutionRow]) -> EvalExecutionSummary:
    return EvalExecutionSummary(
        plan_path=str(plan_path),
        dry_run=dry_run,
        selected_count=len(rows),
        dry_run_count=sum(row.status == EvalExecutionRowStatus.DRY_RUN for row in rows),
        executed_count=sum(row.status == EvalExecutionRowStatus.EXECUTED for row in rows),
        skipped_count=sum(row.status == EvalExecutionRowStatus.SKIPPED_COMPLETED for row in rows),
        blocked_count=sum(row.status == EvalExecutionRowStatus.BLOCKED for row in rows),
        error_count=sum(row.status == EvalExecutionRowStatus.ERROR for row in rows),
        stopped_count=sum(row.status == EvalExecutionRowStatus.STOPPED for row in rows),
        rows=rows,
    )
