"""Playground backend helpers for deterministic local replay and view persistence."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from agent_ab.config import load_experiment, load_prompt_object, validate_taskpack_with_fixtures
from agent_ab.runner import run_mock_task
from agent_ab.schemas.playground import (
    PlaygroundOverrides,
    PlaygroundRunRequest,
    PlaygroundRunResponse,
    PlaygroundView,
    PlaygroundViewListResponse,
    PlaygroundViewSummary,
    validate_playground_token,
)
from agent_ab.schemas.prompt_object import PromptObject
from agent_ab.schemas.task import TaskCase


def run_playground_task(
    request: PlaygroundRunRequest,
    *,
    project_root: str | Path,
    run_root: str | Path,
    views_root: str | Path | None = None,
) -> PlaygroundRunResponse:
    root = Path(project_root).resolve()
    experiment_path = _resolve_project_file(root, request.experiment_path)
    experiment = load_experiment(experiment_path)
    if not experiment.playground.enabled:
        raise ValueError("playground is disabled for this experiment")
    if request.save_view and not experiment.playground.save_views:
        raise ValueError("playground view saving is disabled for this experiment")
    if request.variant_id not in experiment.agents:
        raise ValueError(f"variant id not found in experiment: {request.variant_id}")

    taskpack_path = experiment.taskpack_path(experiment_path.parent)
    taskpack = validate_taskpack_with_fixtures(taskpack_path)
    tasks = {task.id: task for task in taskpack.tasks}
    if request.task_id not in tasks:
        raise ValueError(f"task id not found in taskpack: {request.task_id}")
    task = tasks[request.task_id]

    prompt = load_prompt_object(experiment.prompt_paths(experiment_path.parent)[request.variant_id])
    effective_prompt = apply_playground_overrides(
        prompt,
        request.overrides,
        allow_prompt_editing=experiment.playground.allow_prompt_editing,
        allow_model_switching=experiment.playground.allow_model_switching,
        allow_parameter_editing=experiment.playground.allow_parameter_editing,
        allow_tool_policy_editing=experiment.playground.allow_tool_policy_editing,
    )

    view_root = Path(views_root).resolve() if views_root else root / "playground_views"
    view_id = (request.view_id or _generate_view_id(task)) if request.save_view else None
    if view_id is not None and playground_view_exists(view_root, view_id):
        raise FileExistsError(f"playground view already exists: {view_id}")

    effective_run_id = request.run_id or _generate_run_id(task)
    replay_root = Path(run_root).resolve()
    workspace_path = replay_root / effective_run_id / "workspace"
    prompt_variables = {
        **request.prompt_variables,
        "task_query": task.query,
        "workspace_path": str(workspace_path),
    }
    rendered_messages = effective_prompt.render_messages(prompt_variables)

    result = run_mock_task(
        taskpack_path,
        request.task_id,
        replay_root,
        run_id=effective_run_id,
        variant_id=f"playground.{request.variant_id}",
    )
    response = PlaygroundRunResponse(
        run_id=result.run_id,
        trace_id=result.trace_id,
        task_id=result.task_id,
        variant_id=result.variant_id,
        status=result.status,
        workspace_path=str(result.workspace_path),
        artifacts={name: str(path) for name, path in result.artifacts.items()},
        metrics=result.metrics,
        validator_results=result.validator_results,
        effective_prompt=effective_prompt,
        rendered_messages=rendered_messages,
    )

    if request.save_view:
        assert view_id is not None
        response = response.model_copy(update={"view_id": view_id})
        save_playground_view(
            view_root,
            PlaygroundView(
                id=view_id,
                label=request.label,
                created_at_ms=int(time.time() * 1000),
                request=request,
                response=response,
                effective_prompt=effective_prompt,
                rendered_messages=rendered_messages,
            ),
        )

    return response


def apply_playground_overrides(
    prompt: PromptObject,
    overrides: PlaygroundOverrides,
    *,
    allow_prompt_editing: bool,
    allow_model_switching: bool,
    allow_parameter_editing: bool,
    allow_tool_policy_editing: bool,
) -> PromptObject:
    if (overrides.messages is not None or overrides.variables is not None) and not allow_prompt_editing:
        raise ValueError("prompt editing is disabled for this experiment")
    if overrides.model is not None and not allow_model_switching:
        raise ValueError("model switching is disabled for this experiment")
    if overrides.parameters is not None and not allow_parameter_editing:
        raise ValueError("parameter editing is disabled for this experiment")
    if overrides.tool_policy is not None and not allow_tool_policy_editing:
        raise ValueError("tool policy editing is disabled for this experiment")

    payload = prompt.model_dump(mode="python", by_alias=True)
    if overrides.messages is not None:
        payload["messages"] = [
            message.model_dump(mode="python", by_alias=True)
            for message in overrides.messages
        ]
        payload["variables"] = overrides.variables or []
    elif overrides.variables is not None:
        payload["variables"] = overrides.variables
    if overrides.model is not None:
        payload["model"] = overrides.model.model_dump(mode="python", by_alias=True)
    if overrides.parameters is not None:
        payload["parameters"] = overrides.parameters.model_dump(mode="python", by_alias=True)
    if overrides.tool_policy is not None:
        metadata = dict(payload.get("metadata") or {})
        metadata["playground_tool_policy_override"] = overrides.tool_policy.model_dump(mode="json")
        payload["metadata"] = metadata
    if overrides.metadata:
        metadata = dict(payload.get("metadata") or {})
        metadata["playground_override_metadata"] = overrides.metadata
        payload["metadata"] = metadata
    return PromptObject.model_validate(payload)


def save_playground_view(views_root: str | Path, view: PlaygroundView) -> Path:
    view_path = _view_path(views_root, view.id)
    if view_path.exists():
        raise FileExistsError(f"playground view already exists: {view.id}")
    view_path.parent.mkdir(parents=True, exist_ok=True)
    view_path.write_text(view.model_dump_json(indent=2, by_alias=True), encoding="utf-8")
    return view_path


def playground_view_exists(views_root: str | Path, view_id: str) -> bool:
    return _view_path(views_root, view_id).exists()


def load_playground_view(views_root: str | Path, view_id: str) -> PlaygroundView:
    view_path = _view_path(views_root, view_id)
    if not view_path.is_file():
        raise FileNotFoundError(f"playground view not found: {view_id}")
    return PlaygroundView.model_validate_json(view_path.read_text(encoding="utf-8"))


def list_playground_views(views_root: str | Path) -> PlaygroundViewListResponse:
    root = Path(views_root)
    if not root.is_dir():
        return PlaygroundViewListResponse()
    views = [load_playground_view(root, path.stem) for path in sorted(root.glob("*.json"))]
    return PlaygroundViewListResponse(
        views=[
            PlaygroundViewSummary(
                id=view.id,
                label=view.label,
                created_at_ms=view.created_at_ms,
                experiment_path=view.request.experiment_path,
                variant_id=view.request.variant_id,
                task_id=view.request.task_id,
                run_id=view.response.run_id,
                trace_id=view.response.trace_id,
                status=view.response.status,
            )
            for view in views
        ]
    )


def _resolve_project_file(project_root: Path, relative_path: str) -> Path:
    candidate = (project_root / relative_path).resolve()
    if project_root not in candidate.parents:
        raise ValueError(f"path escapes project root: {relative_path}")
    if not candidate.is_file():
        raise ValueError(f"file not found: {relative_path}")
    return candidate


def _view_path(views_root: str | Path, view_id: str) -> Path:
    safe_view_id = validate_playground_token(view_id, "view_id")
    return Path(views_root).resolve() / f"{safe_view_id}.json"


def _generate_run_id(task: TaskCase) -> str:
    return f"playground.{task.id}.{uuid.uuid4().hex[:12]}"


def _generate_view_id(task: TaskCase) -> str:
    return f"view.{task.id}.{uuid.uuid4().hex[:12]}"
