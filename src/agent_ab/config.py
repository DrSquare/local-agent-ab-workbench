"""Config loading helpers for schema validation modules."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from agent_ab.schemas.eval import EvalSample, EvalSet, EvalTask
from agent_ab.schemas.experiment import ExperimentConfig
from agent_ab.schemas.offline import OfflineDockerABRunPlan, OfflineModelProvider
from agent_ab.schemas.prompt_object import PromptObject
from agent_ab.schemas.sandbox import SandboxProvider
from agent_ab.schemas.task import TaskPack
from agent_ab.yaml_io import YamlConfigError, load_yaml_mapping

T = TypeVar("T", bound=BaseModel)


class ConfigLoadError(ValueError):
    """Raised when a YAML config cannot be loaded or validated."""


def load_yaml(path: str | Path) -> dict:
    try:
        return load_yaml_mapping(path)
    except YamlConfigError as exc:
        raise ConfigLoadError(str(exc)) from exc


def load_model(path: str | Path, model_type: type[T]) -> T:
    payload = load_yaml(path)
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise ConfigLoadError(f"validation failed for {path}:\n{exc}") from exc


def load_experiment(path: str | Path) -> ExperimentConfig:
    return load_model(path, ExperimentConfig)


def load_prompt_object(path: str | Path) -> PromptObject:
    return load_model(path, PromptObject)


def load_taskpack(path: str | Path) -> TaskPack:
    return load_model(path, TaskPack)


def load_eval_task(path: str | Path) -> EvalTask:
    return load_model(path, EvalTask)


def load_eval_set(path: str | Path) -> EvalSet:
    return load_model(path, EvalSet)


def load_sandbox_provider(path: str | Path) -> SandboxProvider:
    return load_model(path, SandboxProvider)


def load_offline_model_provider(path: str | Path) -> OfflineModelProvider:
    return load_model(path, OfflineModelProvider)


def load_offline_docker_ab_run_plan(path: str | Path) -> OfflineDockerABRunPlan:
    return load_model(path, OfflineDockerABRunPlan)


def validate_sandbox_provider(path: str | Path) -> SandboxProvider:
    """Validate a sandbox provider config without executing the provider."""

    return load_sandbox_provider(path)


def validate_offline_model_provider(path: str | Path) -> OfflineModelProvider:
    """Validate an offline model provider config without probing endpoints."""

    return load_offline_model_provider(path)


def validate_offline_docker_ab_run_plan(path: str | Path) -> OfflineDockerABRunPlan:
    """Validate an offline Docker A/B run plan without launching containers."""

    return load_offline_docker_ab_run_plan(path)


def validate_taskpack_with_fixtures(path: str | Path) -> TaskPack:
    """Validate a taskpack YAML file and its declared workspace fixture directories."""

    taskpack_path = Path(path)
    taskpack = load_taskpack(taskpack_path)
    missing = [
        f"{task_id}: {fixture_path}"
        for task_id, fixture_path in taskpack.fixture_paths(taskpack_path.parent).items()
        if not fixture_path.is_dir()
    ]
    if missing:
        raise ConfigLoadError(f"task workspace fixture directories do not exist: {missing}")
    return taskpack


def validate_eval_task_with_taskpack(path: str | Path) -> tuple[EvalTask, TaskPack, list[EvalSample]]:
    """Validate an EvalTask YAML file and its referenced TaskPack/sample selection."""

    eval_task_path = Path(path)
    eval_task = load_eval_task(eval_task_path)
    taskpack = validate_taskpack_with_fixtures(eval_task.taskpack_path(eval_task_path.parent))
    try:
        samples = eval_task.selected_samples(taskpack)
    except ValueError as exc:
        raise ConfigLoadError(f"eval task sample selection failed for {path}: {exc}") from exc
    return eval_task, taskpack, samples


def validate_eval_set_with_tasks(
    path: str | Path,
) -> tuple[EvalSet, list[tuple[str, EvalTask, TaskPack, list[EvalSample]]]]:
    """Validate an EvalSet and every referenced EvalTask/TaskPack/sample selection."""

    eval_set_path = Path(path)
    eval_set = load_eval_set(eval_set_path)
    resolved: list[tuple[str, EvalTask, TaskPack, list[EvalSample]]] = []
    for ref_id, eval_task_path in eval_set.eval_task_paths(eval_set_path.parent).items():
        try:
            eval_task, taskpack, samples = validate_eval_task_with_taskpack(eval_task_path)
        except ConfigLoadError as exc:
            raise ConfigLoadError(f"eval task ref '{ref_id}' failed validation: {exc}") from exc
        resolved.append((ref_id, eval_task, taskpack, samples))
    return eval_set, resolved


def validate_experiment_with_prompts(path: str | Path) -> tuple[ExperimentConfig, dict[str, PromptObject]]:
    """Validate an experiment plus every referenced PromptObject file."""

    experiment_path = Path(path)
    experiment = load_experiment(experiment_path)
    prompts: dict[str, PromptObject] = {}
    for variant_id, prompt_path in experiment.prompt_paths(experiment_path.parent).items():
        prompts[variant_id] = load_prompt_object(prompt_path)
    return experiment, prompts


def validate_experiment_bundle(
    path: str | Path,
    *,
    include_prompts: bool = True,
    include_taskpack: bool = True,
) -> tuple[ExperimentConfig, dict[str, PromptObject], TaskPack | None]:
    """Validate an experiment and optionally its referenced prompt objects and taskpack."""

    experiment_path = Path(path)
    experiment = load_experiment(experiment_path)
    prompts: dict[str, PromptObject] = {}
    if include_prompts:
        for variant_id, prompt_path in experiment.prompt_paths(experiment_path.parent).items():
            prompts[variant_id] = load_prompt_object(prompt_path)

    taskpack = None
    if include_taskpack:
        taskpack = validate_taskpack_with_fixtures(experiment.taskpack_path(experiment_path.parent))
    return experiment, prompts, taskpack
