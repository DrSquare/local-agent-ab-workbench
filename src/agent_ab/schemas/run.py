"""Run result schemas for local task execution."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from agent_ab.schemas.common import StrictBaseModel, _non_blank
from agent_ab.schemas.metrics import is_known_or_custom_metric
from agent_ab.schemas.trace import TraceEnvelope


class RunStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class ValidatorRunResult(StrictBaseModel):
    validator_type: str = Field(..., min_length=1)
    path: str | None = None
    passed: bool
    message: str
    expected: Any = None
    observed: Any = None

    @field_validator("validator_type", "message")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _non_blank(value, "validator result field")


class MetricResult(StrictBaseModel):
    name: str = Field(..., min_length=1)
    value: float | int | str | bool | None

    @field_validator("name")
    @classmethod
    def metric_name_known_or_custom(cls, value: str) -> str:
        metric_name = _non_blank(value, "metric name")
        if not is_known_or_custom_metric(metric_name):
            raise ValueError(f"unknown metric '{metric_name}'. Use a built-in name or custom.<name>.")
        return metric_name


class TaskRunResult(StrictBaseModel):
    run_id: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    task_id: str = Field(..., min_length=1)
    variant_id: str = Field(..., min_length=1)
    status: RunStatus
    workspace_path: Path
    validator_results: list[ValidatorRunResult]
    metrics: list[MetricResult]
    trace: TraceEnvelope
    artifacts: dict[str, Path] = Field(default_factory=dict)

    @field_validator("run_id", "trace_id", "task_id", "variant_id")
    @classmethod
    def ids_not_blank(cls, value: str) -> str:
        return _non_blank(value, "run result id")
