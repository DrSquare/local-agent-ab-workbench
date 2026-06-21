"""Config loading helpers for Module 1."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from agent_ab.schemas.experiment import ExperimentConfig
from agent_ab.schemas.prompt_object import PromptObject
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
        taskpack = load_taskpack(experiment.taskpack_path(experiment_path.parent))
    return experiment, prompts, taskpack
