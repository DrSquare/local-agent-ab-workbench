"""Inspect-inspired eval task and eval log schemas."""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator, model_validator

from agent_ab.schemas.common import (
    AdapterKind,
    IdentifierMixin,
    StrictBaseModel,
    _non_blank,
    _normalized_non_blank_list,
    is_identifier,
)
from agent_ab.schemas.experiment import RunLimits
from agent_ab.schemas.metrics import is_known_or_custom_metric
from agent_ab.schemas.task import (
    TaskPack,
    TaskValidator,
    is_known_or_custom_validator_type,
)
from agent_ab.schemas.trace import validate_trace_token
from agent_ab.yaml_io import load_yaml_mapping

_CUSTOM_REF_RE = re.compile(r"^custom\.[A-Za-z][A-Za-z0-9_.-]*$")
_TRACE_SCORER_NAMES = {
    "span_status",
    "span_duration",
    "span_count",
    "artifact_present",
    "trace_replay_determinism",
}
REGISTERED_SOLVER_ADAPTERS = {
    adapter.value
    for adapter in AdapterKind
    if adapter is not AdapterKind.CUSTOM
}


def is_custom_reference(value: str) -> bool:
    return bool(_CUSTOM_REF_RE.match(value))


def is_registered_or_custom_solver_adapter(value: str) -> bool:
    return value in REGISTERED_SOLVER_ADAPTERS or is_custom_reference(value)


def _validate_identifier_list(values: list[str], field_name: str, *, allow_all: bool = False) -> list[str]:
    normalized = _normalized_non_blank_list(values, field_name)
    for value in normalized:
        if allow_all and value == "*":
            continue
        if not is_identifier(value):
            raise ValueError(
                f"{field_name} entries must be stable identifiers"
            )
    return normalized


class EvalScorerType(str, Enum):
    VALIDATOR = "validator"
    METRIC = "metric"
    TRACE = "trace"
    CUSTOM = "custom"


class EvalLogStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class EvalRunPlanStatus(str, Enum):
    PLANNED = "planned"
    SKIPPED_COMPLETED = "skipped_completed"


class EvalSampleSelection(StrictBaseModel):
    """Select TaskPack tasks for an EvalTask.

    `include: ["*"]` means every task in the referenced TaskPack. Exclusions can
    then remove known task IDs from that set.
    """

    include: list[str] = Field(default_factory=lambda: ["*"], min_length=1)
    exclude: list[str] = Field(default_factory=list)

    @field_validator("include")
    @classmethod
    def include_ids_are_valid(cls, value: list[str]) -> list[str]:
        return _validate_identifier_list(value, "sample include", allow_all=True)

    @field_validator("exclude")
    @classmethod
    def exclude_ids_are_valid(cls, value: list[str]) -> list[str]:
        return _validate_identifier_list(value, "sample exclude")

    @model_validator(mode="after")
    def include_shape_is_unambiguous(self) -> EvalSampleSelection:
        if "*" in self.include and len(self.include) > 1:
            raise ValueError("sample include '*' cannot be combined with explicit sample IDs")
        overlap = sorted(set(self.include) & set(self.exclude))
        if overlap:
            raise ValueError(f"sample include/exclude overlap: {overlap}")
        return self

    def select_task_ids(self, taskpack: TaskPack) -> list[str]:
        available = [task.id for task in taskpack.tasks]
        available_set = set(available)
        requested = available if self.include == ["*"] else self.include
        missing = sorted(set(requested) - available_set)
        if missing:
            raise ValueError(f"sample IDs not found in taskpack '{taskpack.id}': {missing}")
        missing_excludes = sorted(set(self.exclude) - available_set)
        if missing_excludes:
            raise ValueError(
                f"excluded sample IDs not found in taskpack '{taskpack.id}': {missing_excludes}"
            )
        selected = [task_id for task_id in requested if task_id not in set(self.exclude)]
        if not selected:
            raise ValueError("sample selection matched no tasks")
        return selected


class EvalSolverRef(IdentifierMixin):
    """Reference to a solver/agent adapter without executing it."""

    adapter: str = Field(default="mock")
    variant_id: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("adapter")
    @classmethod
    def adapter_is_registered_or_custom(cls, value: str) -> str:
        adapter = _non_blank(value, "solver adapter")
        if not is_registered_or_custom_solver_adapter(adapter):
            raise ValueError(
                f"unknown solver adapter '{adapter}'. Use a registered adapter or custom.<name>."
            )
        return adapter

    @field_validator("variant_id")
    @classmethod
    def variant_id_is_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        variant_id = _non_blank(value, "solver variant_id")
        if not is_identifier(variant_id):
            raise ValueError("solver variant_id must be a stable identifier")
        return variant_id


class EvalScorerRef(IdentifierMixin):
    """Reference to a scorer contract.

    Module 13 validates references only. Execution and scoring pipelines come in
    later modules.
    """

    type: EvalScorerType
    name: str
    threshold: float | int | None = None
    required: bool = True
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        return _non_blank(value, "scorer name")

    @model_validator(mode="after")
    def scorer_name_matches_type(self) -> EvalScorerRef:
        _validate_scorer_name(self.type, self.name)
        return self


class EvalSample(StrictBaseModel):
    """Normalized task sample view used by EvalTask."""

    id: str
    taskpack_id: str
    task_id: str
    query: str
    workspace_fixture: str
    validators: list[TaskValidator] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "taskpack_id", "task_id")
    @classmethod
    def ids_are_identifiers(cls, value: str) -> str:
        if not is_identifier(value):
            raise ValueError("eval sample IDs must be stable identifiers")
        return value

    @field_validator("query", "workspace_fixture")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _non_blank(value, "eval sample field")


class EvalTask(IdentifierMixin):
    """Reusable local evaluation task binding samples, solver, scorers, and limits."""

    version: int = Field(default=1, ge=1)
    description: str | None = None
    taskpack: str = Field(..., description="Path to a TaskPack YAML file.")
    samples: EvalSampleSelection = Field(default_factory=EvalSampleSelection)
    solver: EvalSolverRef
    scorers: list[EvalScorerRef] = Field(min_length=1)
    limits: RunLimits = Field(default_factory=RunLimits)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("taskpack")
    @classmethod
    def taskpack_path_not_blank(cls, value: str) -> str:
        return _non_blank(value, "eval task taskpack")

    @field_validator("tags")
    @classmethod
    def tags_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "tag")

    @model_validator(mode="after")
    def scorer_ids_are_unique(self) -> EvalTask:
        scorer_ids = [scorer.id for scorer in self.scorers]
        duplicates = sorted({scorer_id for scorer_id in scorer_ids if scorer_ids.count(scorer_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate scorer ids: {duplicates}")
        return self

    def taskpack_path(self, base_dir: str | Path | None = None) -> Path:
        root = Path(base_dir) if base_dir else Path.cwd()
        taskpack_path = Path(self.taskpack)
        if not taskpack_path.is_absolute():
            taskpack_path = root / taskpack_path
        return taskpack_path

    def selected_samples(self, taskpack: TaskPack) -> list[EvalSample]:
        task_by_id = {task.id: task for task in taskpack.tasks}
        return [
            EvalSample(
                id=task.id,
                taskpack_id=taskpack.id,
                task_id=task.id,
                query=task.query,
                workspace_fixture=task.workspace.fixture,
                validators=task.validators,
                tags=[*taskpack.tags, *task.tags],
                metadata=task.metadata,
            )
            for task_id in self.samples.select_task_ids(taskpack)
            for task in [task_by_id[task_id]]
        ]

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> EvalTask:
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


class EvalTaskRef(IdentifierMixin):
    """EvalTask reference inside an EvalSet."""

    path: str = Field(..., description="Relative or absolute path to an EvalTask YAML file.")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("path")
    @classmethod
    def path_not_blank(cls, value: str) -> str:
        return _non_blank(value, "eval task path")


class EvalSet(IdentifierMixin):
    """Collection of EvalTasks for resumable local planning."""

    version: int = Field(default=1, ge=1)
    description: str | None = None
    eval_tasks: list[EvalTaskRef] = Field(min_length=1)
    resume: bool = True
    max_samples: int | None = Field(default=None, ge=1)
    max_failures: int | None = Field(default=None, ge=0)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def tags_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "tag")

    @model_validator(mode="after")
    def eval_task_refs_are_unique(self) -> EvalSet:
        ref_ids = [ref.id for ref in self.eval_tasks]
        duplicates = sorted({ref_id for ref_id in ref_ids if ref_ids.count(ref_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate eval task ref ids: {duplicates}")
        return self

    def eval_task_paths(self, base_dir: str | Path | None = None) -> dict[str, Path]:
        root = Path(base_dir) if base_dir else Path.cwd()
        paths: dict[str, Path] = {}
        for ref in self.eval_tasks:
            ref_path = Path(ref.path)
            if not ref_path.is_absolute():
                ref_path = root / ref_path
            paths[ref.id] = ref_path
        return paths

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> EvalSet:
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


class EvalTraceReference(StrictBaseModel):
    trace_id: str
    run_id: str | None = None
    path: str | None = None

    @field_validator("trace_id", "run_id")
    @classmethod
    def ids_are_trace_tokens(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return validate_trace_token(value, info.field_name)

    @field_validator("path")
    @classmethod
    def path_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_blank(value, "trace path")


class EvalArtifactRef(StrictBaseModel):
    name: str
    path: str
    kind: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "path")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _non_blank(value, "artifact reference field")

    @field_validator("kind")
    @classmethod
    def kind_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_blank(value, "artifact kind")


class EvalScorerResult(StrictBaseModel):
    scorer_id: str
    type: EvalScorerType
    name: str
    passed: bool | None = None
    score: float | int | str | bool | None = None
    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scorer_id")
    @classmethod
    def scorer_id_is_identifier(cls, value: str) -> str:
        if not is_identifier(value):
            raise ValueError("scorer_id must be a stable identifier")
        return value

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        return _non_blank(value, "scorer result name")

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_blank(value, "scorer result message")

    @model_validator(mode="after")
    def result_name_matches_type(self) -> EvalScorerResult:
        _validate_scorer_name(self.type, self.name)
        return self


class EvalError(StrictBaseModel):
    code: str
    message: str
    fatal: bool = True
    span_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code", "message")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _non_blank(value, "eval error field")

    @field_validator("span_id")
    @classmethod
    def span_id_is_trace_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_trace_token(value, "span_id")


class EvalLog(StrictBaseModel):
    """Per-sample eval log envelope.

    The log references run artifacts and traces; it does not embed a live agent
    execution engine.
    """

    eval_task_id: str
    eval_task_version: int = Field(default=1, ge=1)
    eval_run_id: str
    sample_id: str
    taskpack_id: str
    task_id: str
    solver_id: str
    variant_id: str | None = None
    status: EvalLogStatus
    started_at_ms: int | None = Field(default=None, ge=0)
    ended_at_ms: int | None = Field(default=None, ge=0)
    scorer_results: list[EvalScorerResult] = Field(default_factory=list)
    trace: EvalTraceReference | None = None
    artifacts: list[EvalArtifactRef] = Field(default_factory=list)
    limits: RunLimits = Field(default_factory=RunLimits)
    errors: list[EvalError] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "eval_task_id",
        "sample_id",
        "taskpack_id",
        "task_id",
        "solver_id",
        "variant_id",
    )
    @classmethod
    def ids_are_identifiers(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        if not is_identifier(value):
            raise ValueError(f"{info.field_name} must be a stable identifier")
        return value

    @field_validator("eval_run_id")
    @classmethod
    def eval_run_id_is_trace_token(cls, value: str) -> str:
        return validate_trace_token(value, "eval_run_id")

    @model_validator(mode="after")
    def log_shape_is_consistent(self) -> EvalLog:
        if (
            self.ended_at_ms is not None
            and self.started_at_ms is not None
            and self.ended_at_ms < self.started_at_ms
        ):
            raise ValueError("ended_at_ms must be greater than or equal to started_at_ms")
        scorer_ids = [result.scorer_id for result in self.scorer_results]
        duplicates = sorted({scorer_id for scorer_id in scorer_ids if scorer_ids.count(scorer_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate scorer result ids: {duplicates}")
        if self.status == EvalLogStatus.ERROR and not self.errors:
            raise ValueError("status=error requires at least one error")
        if self.status in {EvalLogStatus.PASSED, EvalLogStatus.FAILED} and not self.scorer_results:
            raise ValueError("passed or failed eval logs require scorer_results")
        return self


class EvalSampleRunPlan(StrictBaseModel):
    eval_task_id: str
    eval_task_version: int = Field(default=1, ge=1)
    eval_task_ref_id: str
    sample_id: str
    taskpack_id: str
    task_id: str
    solver_id: str
    variant_id: str | None = None
    eval_run_id: str
    eval_log_path: str
    status: EvalRunPlanStatus = EvalRunPlanStatus.PLANNED
    scorer_ids: list[str] = Field(default_factory=list)
    limits: RunLimits = Field(default_factory=RunLimits)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "eval_task_id",
        "eval_task_ref_id",
        "sample_id",
        "taskpack_id",
        "task_id",
        "solver_id",
        "variant_id",
    )
    @classmethod
    def ids_are_identifiers(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        if not is_identifier(value):
            raise ValueError(f"{info.field_name} must be a stable identifier")
        return value

    @field_validator("eval_run_id")
    @classmethod
    def eval_run_id_is_trace_token(cls, value: str) -> str:
        return validate_trace_token(value, "eval_run_id")

    @field_validator("eval_log_path")
    @classmethod
    def eval_log_path_not_blank(cls, value: str) -> str:
        return _non_blank(value, "eval_log_path")

    @field_validator("scorer_ids")
    @classmethod
    def scorer_ids_are_identifiers(cls, value: list[str]) -> list[str]:
        return _validate_identifier_list(value, "scorer_id")


class EvalRunPlan(StrictBaseModel):
    eval_set_id: str
    eval_set_version: int = Field(default=1, ge=1)
    run_root: str
    total_samples: int = Field(ge=0)
    planned_count: int = Field(ge=0)
    skipped_completed_count: int = Field(ge=0)
    max_failures: int | None = Field(default=None, ge=0)
    sample_runs: list[EvalSampleRunPlan] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("eval_set_id")
    @classmethod
    def eval_set_id_is_identifier(cls, value: str) -> str:
        if not is_identifier(value):
            raise ValueError("eval_set_id must be a stable identifier")
        return value

    @field_validator("run_root")
    @classmethod
    def run_root_not_blank(cls, value: str) -> str:
        return _non_blank(value, "run_root")

    @model_validator(mode="after")
    def counts_match_sample_runs(self) -> EvalRunPlan:
        planned = sum(run.status == EvalRunPlanStatus.PLANNED for run in self.sample_runs)
        skipped = sum(run.status == EvalRunPlanStatus.SKIPPED_COMPLETED for run in self.sample_runs)
        if self.total_samples != len(self.sample_runs):
            raise ValueError("total_samples must equal sample_runs length")
        if self.planned_count != planned:
            raise ValueError("planned_count must match planned sample runs")
        if self.skipped_completed_count != skipped:
            raise ValueError("skipped_completed_count must match skipped sample runs")
        return self


def _validate_scorer_name(scorer_type: EvalScorerType, name: str) -> None:
    if scorer_type == EvalScorerType.VALIDATOR and not is_known_or_custom_validator_type(name):
        raise ValueError(f"unknown validator scorer '{name}'. Use a built-in validator or custom.<name>.")
    if scorer_type == EvalScorerType.METRIC and not is_known_or_custom_metric(name):
        raise ValueError(f"unknown metric scorer '{name}'. Use a built-in metric or custom.<name>.")
    if (
        scorer_type == EvalScorerType.TRACE
        and name not in _TRACE_SCORER_NAMES
        and not is_custom_reference(name)
    ):
        raise ValueError(f"unknown trace scorer '{name}'. Use a built-in trace scorer or custom.<name>.")
    if scorer_type == EvalScorerType.CUSTOM and not is_custom_reference(name):
        raise ValueError("custom scorers must use custom.<name>")
