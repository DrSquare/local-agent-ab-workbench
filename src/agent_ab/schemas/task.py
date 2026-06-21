"""Taskpack schema for deterministic local desktop-agent tasks."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from pydantic import Field, field_validator, model_validator

from agent_ab.schemas.common import IdentifierMixin, StrictBaseModel, _non_blank
from agent_ab.yaml_io import load_yaml_mapping

_CUSTOM_VALIDATOR_RE = re.compile(r"^custom\.[A-Za-z][A-Za-z0-9_.-]*$")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")

KNOWN_VALIDATOR_TYPES = {
    "file_exists",
    "file_not_exists",
    "file_contains",
    "file_not_contains",
    "file_matches_regex",
}


def is_known_or_custom_validator_type(value: str) -> bool:
    return value in KNOWN_VALIDATOR_TYPES or bool(_CUSTOM_VALIDATOR_RE.match(value))


def validate_relative_workspace_path(value: str, field_name: str = "path") -> str:
    """Validate a portable path relative to a task workspace or taskpack."""

    path_value = _non_blank(value, field_name).strip()
    if "\\" in path_value:
        raise ValueError(f"{field_name} must use forward slashes")
    if _WINDOWS_DRIVE_RE.match(path_value):
        raise ValueError(f"{field_name} must be relative, not a Windows absolute path")

    path = PurePosixPath(path_value)
    if path.is_absolute():
        raise ValueError(f"{field_name} must be relative")
    if path.parts in {(), (".",)}:
        raise ValueError(f"{field_name} cannot be empty or current directory")
    if ".." in path.parts:
        raise ValueError(f"{field_name} cannot contain '..'")
    if path.parts[0].startswith("~"):
        raise ValueError(f"{field_name} cannot start with '~'")
    return path_value


class TaskWorkspace(StrictBaseModel):
    """Declarative workspace fixture contract for a task."""

    fixture: str = Field(..., description="Relative path to the task workspace fixture.")

    @field_validator("fixture")
    @classmethod
    def fixture_path_is_relative(cls, value: str) -> str:
        return validate_relative_workspace_path(value, "workspace fixture")


class TaskValidator(StrictBaseModel):
    """Declarative validator contract.

    Module 2 validates the contract only. It does not execute validators.
    """

    type: str = Field(..., description="Known validator type or custom.<name>.")
    path: str | None = Field(default=None, description="Relative path inside the task workspace.")
    contains: str | None = Field(default=None, description="Literal text expected in a file.")
    pattern: str | None = Field(default=None, description="Regular expression expected to match a file.")
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def validator_type_known_or_custom(cls, value: str) -> str:
        validator_type = _non_blank(value, "validator type")
        if not is_known_or_custom_validator_type(validator_type):
            raise ValueError(
                f"unknown validator type '{validator_type}'. "
                "Use a built-in type or custom.<name>."
            )
        return validator_type

    @field_validator("path")
    @classmethod
    def validator_path_is_relative(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_relative_workspace_path(value, "validator path")

    @field_validator("contains", "pattern")
    @classmethod
    def optional_match_fields_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_blank(value, "validator match field")

    @model_validator(mode="after")
    def required_fields_match_validator_type(self) -> TaskValidator:
        if self.type in KNOWN_VALIDATOR_TYPES and self.path is None:
            raise ValueError(f"validator type '{self.type}' requires path")
        if self.type in {"file_exists", "file_not_exists"}:
            extras = []
            if self.contains is not None:
                extras.append("contains")
            if self.pattern is not None:
                extras.append("pattern")
            if extras:
                raise ValueError(f"validator type '{self.type}' does not allow {extras}")
        if self.type in {"file_contains", "file_not_contains"} and self.contains is None:
            raise ValueError(f"validator type '{self.type}' requires contains")
        if self.type in {"file_contains", "file_not_contains"} and self.pattern is not None:
            raise ValueError(f"validator type '{self.type}' does not allow pattern")
        if self.type == "file_matches_regex":
            if self.contains is not None:
                raise ValueError("validator type 'file_matches_regex' does not allow contains")
            if self.pattern is None:
                raise ValueError("validator type 'file_matches_regex' requires pattern")
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"invalid validator regex pattern: {exc}") from exc
        return self


class TaskCase(IdentifierMixin):
    """One deterministic task query and its declarative validation contract."""

    description: str | None = None
    query: str = Field(..., min_length=1)
    workspace: TaskWorkspace
    validators: list[TaskValidator] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, value: str) -> str:
        return _non_blank(value, "task query")


class TaskPack(IdentifierMixin):
    """A versioned collection of deterministic local tasks."""

    version: int = Field(default=1, ge=1)
    description: str | None = None
    tasks: list[TaskCase] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def task_ids_are_unique(self) -> TaskPack:
        task_ids = [task.id for task in self.tasks]
        duplicates = sorted({task_id for task_id in task_ids if task_ids.count(task_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate task ids: {duplicates}")
        return self

    def fixture_paths(self, base_dir: str | Path | None = None) -> dict[str, Path]:
        root = Path(base_dir) if base_dir else Path.cwd()
        return {task.id: root / task.workspace.fixture for task in self.tasks}

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> TaskPack:
        return cls.model_validate(load_yaml_mapping(path))

    def to_yaml_file(self, path: str | Path) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            yaml.safe_dump(
                self.model_dump(mode="json", by_alias=True, exclude_none=True),
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
