"""Playground request, response, and persisted view schemas."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from pydantic import Field, field_validator

from agent_ab.schemas.common import (
    GenerationParameters,
    ModelConfig,
    PromptMessage,
    StrictBaseModel,
    ToolPolicyOverride,
    _non_blank,
)
from agent_ab.schemas.prompt_object import PromptObject
from agent_ab.schemas.run import MetricResult, RunStatus, ValidatorRunResult
from agent_ab.schemas.trace import validate_trace_token

_PLAYGROUND_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


def validate_playground_token(value: str, field_name: str) -> str:
    token = _non_blank(value, field_name).strip()
    if not _PLAYGROUND_TOKEN_RE.match(token):
        raise ValueError(
            f"{field_name} must start with a letter and contain only letters, numbers, dot, dash, underscore"
        )
    return token


def validate_project_relative_path(value: str, field_name: str) -> str:
    path_value = _non_blank(value, field_name).strip()
    if "\\" in path_value:
        raise ValueError(f"{field_name} must use forward slashes")
    path = PurePosixPath(path_value)
    if path.is_absolute():
        raise ValueError(f"{field_name} must be relative to the project root")
    if path.parts in {(), (".",)}:
        raise ValueError(f"{field_name} cannot be empty or current directory")
    if ".." in path.parts:
        raise ValueError(f"{field_name} cannot contain '..'")
    return path_value


class PlaygroundOverrides(StrictBaseModel):
    messages: list[PromptMessage] | None = Field(
        default=None,
        description="Optional replacement prompt messages for the replay.",
    )
    variables: list[str] | None = Field(
        default=None,
        description="Optional replacement prompt variable declaration.",
    )
    model: ModelConfig | None = None
    parameters: GenerationParameters | None = None
    tool_policy: ToolPolicyOverride | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("variables")
    @classmethod
    def variable_names_are_identifiers(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        duplicates = sorted({name for name in value if value.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate prompt variables: {duplicates}")
        for name in value:
            if not name.isidentifier():
                raise ValueError(f"prompt variable must be a valid identifier: {name}")
        return value


class PlaygroundRunRequest(StrictBaseModel):
    experiment_path: str = Field(..., description="Experiment YAML path relative to the project root.")
    variant_id: str = Field(..., description="Experiment variant to replay.")
    task_id: str = Field(..., description="Task ID to replay.")
    run_id: str | None = Field(default=None, description="Optional deterministic replay run ID.")
    prompt_variables: dict[str, Any] = Field(default_factory=dict)
    overrides: PlaygroundOverrides = Field(default_factory=PlaygroundOverrides)
    save_view: bool = False
    view_id: str | None = None
    label: str | None = None

    @field_validator("experiment_path")
    @classmethod
    def experiment_path_is_project_relative(cls, value: str) -> str:
        return validate_project_relative_path(value, "experiment_path")

    @field_validator("variant_id", "task_id")
    @classmethod
    def ids_are_trace_tokens(cls, value: str, info) -> str:
        return validate_trace_token(value, info.field_name)

    @field_validator("run_id")
    @classmethod
    def run_id_is_trace_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_trace_token(value, "run_id")

    @field_validator("view_id")
    @classmethod
    def view_id_is_playground_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_playground_token(value, "view_id")

    @field_validator("label")
    @classmethod
    def label_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_blank(value, "label")


class PlaygroundRunResponse(StrictBaseModel):
    run_id: str
    trace_id: str
    task_id: str
    variant_id: str
    status: RunStatus
    workspace_path: str
    artifacts: dict[str, str] = Field(default_factory=dict)
    metrics: list[MetricResult] = Field(default_factory=list)
    validator_results: list[ValidatorRunResult] = Field(default_factory=list)
    effective_prompt: PromptObject
    rendered_messages: list[PromptMessage] = Field(default_factory=list)
    view_id: str | None = None


class PlaygroundView(StrictBaseModel):
    id: str
    label: str | None = None
    created_at_ms: int = Field(..., ge=0)
    request: PlaygroundRunRequest
    response: PlaygroundRunResponse
    effective_prompt: PromptObject
    rendered_messages: list[PromptMessage] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def id_is_playground_token(cls, value: str) -> str:
        return validate_playground_token(value, "id")


class PlaygroundViewSummary(StrictBaseModel):
    id: str
    label: str | None = None
    created_at_ms: int
    experiment_path: str
    variant_id: str
    task_id: str
    run_id: str
    trace_id: str
    status: RunStatus


class PlaygroundViewListResponse(StrictBaseModel):
    views: list[PlaygroundViewSummary] = Field(default_factory=list)
