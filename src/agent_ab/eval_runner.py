"""EvalSet planning helpers for Module 14.

This module plans eval runs but does not execute agents. Execution remains
behind later runner/sandbox work.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_ab.config import validate_eval_set_with_tasks
from agent_ab.schemas.eval import (
    EvalLog,
    EvalRunPlan,
    EvalRunPlanStatus,
    EvalSample,
    EvalSampleRunPlan,
    EvalSet,
    EvalTask,
)


def build_eval_run_plan(eval_set_path: str | Path, run_root: str | Path) -> EvalRunPlan:
    """Build a deterministic, non-executing plan for an EvalSet."""

    eval_set, resolved_tasks = validate_eval_set_with_tasks(eval_set_path)
    root = Path(run_root)
    sample_runs: list[EvalSampleRunPlan] = []

    for ref_id, eval_task, _taskpack, samples in resolved_tasks:
        for sample in samples:
            if eval_set.max_samples is not None and len(sample_runs) >= eval_set.max_samples:
                break
            sample_runs.append(_sample_run_plan(eval_set, ref_id, eval_task, sample, root))
        if eval_set.max_samples is not None and len(sample_runs) >= eval_set.max_samples:
            break

    planned_count = sum(run.status == EvalRunPlanStatus.PLANNED for run in sample_runs)
    skipped_count = sum(run.status == EvalRunPlanStatus.SKIPPED_COMPLETED for run in sample_runs)
    return EvalRunPlan(
        eval_set_id=eval_set.id,
        eval_set_version=eval_set.version,
        run_root=str(root),
        total_samples=len(sample_runs),
        planned_count=planned_count,
        skipped_completed_count=skipped_count,
        max_failures=eval_set.max_failures,
        sample_runs=sample_runs,
        metadata={
            "resume": eval_set.resume,
            "source_eval_set": str(Path(eval_set_path)),
        },
    )


def write_eval_run_plan(plan: EvalRunPlan, output_path: str | Path) -> Path:
    """Write an EvalRunPlan JSON artifact."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(plan.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return path


def _sample_run_plan(
    eval_set: EvalSet,
    ref_id: str,
    eval_task: EvalTask,
    sample: EvalSample,
    run_root: Path,
) -> EvalSampleRunPlan:
    eval_run_id = f"eval.{eval_set.id}.{eval_task.id}.{sample.id}"
    eval_log_path = run_root / eval_set.id / eval_task.id / sample.id / "eval_log.json"
    status = EvalRunPlanStatus.PLANNED
    completed_log = _load_completed_eval_log(eval_log_path)
    if eval_set.resume and completed_log is not None:
        status = EvalRunPlanStatus.SKIPPED_COMPLETED

    return EvalSampleRunPlan(
        eval_task_id=eval_task.id,
        eval_task_version=eval_task.version,
        eval_task_ref_id=ref_id,
        sample_id=sample.id,
        taskpack_id=sample.taskpack_id,
        task_id=sample.task_id,
        solver_id=eval_task.solver.id,
        variant_id=eval_task.solver.variant_id,
        eval_run_id=eval_run_id,
        eval_log_path=str(eval_log_path),
        status=status,
        scorer_ids=[scorer.id for scorer in eval_task.scorers],
        limits=eval_task.limits,
        metadata={
            "query": sample.query,
            "workspace_fixture": sample.workspace_fixture,
            "completed_log_status": completed_log.status if completed_log else None,
        },
    )


def _load_completed_eval_log(path: Path) -> EvalLog | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid eval log JSON at {path}: {exc}") from exc
    return EvalLog.model_validate(payload)
