"""Trace schemas for local offline agent-run telemetry."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from agent_ab.schemas.common import StrictBaseModel, _non_blank
from agent_ab.schemas.metrics import is_known_or_custom_metric

_TRACE_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")


class SpanKind(str, Enum):
    TASK_RUN = "task_run"
    SETUP = "setup"
    AGENT_SESSION = "agent_session"
    PLANNER = "planner"
    LLM = "llm"
    TOOL = "tool"
    DESKTOP = "desktop"
    SHELL = "shell"
    VALIDATOR = "validator"
    SCORING = "scoring"
    CUSTOM = "custom"


class SpanStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    SKIPPED = "skipped"


def validate_trace_token(value: str, field_name: str) -> str:
    token = _non_blank(value, field_name).strip()
    if not _TRACE_TOKEN_RE.match(token):
        raise ValueError(
            f"{field_name} must contain only letters, numbers, dot, dash, underscore, colon"
        )
    return token


class SpanEvent(StrictBaseModel):
    name: str = Field(..., min_length=1)
    timestamp_ms: int = Field(..., ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        return _non_blank(value, "span event name")


class ModelCallDetail(StrictBaseModel):
    provider: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    input_preview: str | None = None
    output_preview: str | None = None
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)

    @field_validator("provider", "model")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _non_blank(value, "model call field")


class ToolCallDetail(StrictBaseModel):
    tool_name: str = Field(..., min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_preview: str | None = None
    error: str | None = None

    @field_validator("tool_name")
    @classmethod
    def tool_name_not_blank(cls, value: str) -> str:
        return _non_blank(value, "tool name")


class DesktopActionDetail(StrictBaseModel):
    action: str = Field(..., min_length=1)
    target: str | None = None
    screenshot_before: str | None = None
    screenshot_after: str | None = None

    @field_validator("action")
    @classmethod
    def action_not_blank(cls, value: str) -> str:
        return _non_blank(value, "desktop action")


class ShellActionDetail(StrictBaseModel):
    command: str = Field(..., min_length=1)
    exit_code: int | None = None
    stdout_preview: str | None = None
    stderr_preview: str | None = None

    @field_validator("command")
    @classmethod
    def command_not_blank(cls, value: str) -> str:
        return _non_blank(value, "shell command")


class ValidatorDetail(StrictBaseModel):
    validator_type: str = Field(..., min_length=1)
    path: str | None = None
    passed: bool | None = None
    expected: Any = None
    observed: Any = None

    @field_validator("validator_type")
    @classmethod
    def validator_type_not_blank(cls, value: str) -> str:
        return _non_blank(value, "validator type")


class ScoringDetail(StrictBaseModel):
    metrics: dict[str, float | int | str | bool | None] = Field(default_factory=dict)

    @field_validator("metrics")
    @classmethod
    def metrics_are_known_or_custom(cls, value: dict[str, float | int | str | bool | None]) -> dict[str, float | int | str | bool | None]:
        unknown = [name for name in value if not is_known_or_custom_metric(name)]
        if unknown:
            raise ValueError(f"unknown scoring metrics: {unknown}")
        return value


_DETAIL_FIELD_BY_KIND = {
    SpanKind.LLM: "model_call",
    SpanKind.TOOL: "tool_call",
    SpanKind.DESKTOP: "desktop_action",
    SpanKind.SHELL: "shell_action",
    SpanKind.VALIDATOR: "validator",
    SpanKind.SCORING: "scoring",
}


class TraceSpan(StrictBaseModel):
    span_id: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    parent_span_id: str | None = None
    name: str = Field(..., min_length=1)
    kind: SpanKind
    status: SpanStatus = SpanStatus.OK
    started_at_ms: int = Field(..., ge=0)
    ended_at_ms: int | None = Field(default=None, ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)
    events: list[SpanEvent] = Field(default_factory=list)
    model_call: ModelCallDetail | None = None
    tool_call: ToolCallDetail | None = None
    desktop_action: DesktopActionDetail | None = None
    shell_action: ShellActionDetail | None = None
    validator: ValidatorDetail | None = None
    scoring: ScoringDetail | None = None

    @field_validator("span_id", "trace_id", "parent_span_id")
    @classmethod
    def ids_are_trace_tokens(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return validate_trace_token(value, info.field_name)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        return _non_blank(value, "span name")

    @model_validator(mode="after")
    def validate_time_and_detail_shape(self) -> TraceSpan:
        if self.ended_at_ms is not None and self.ended_at_ms < self.started_at_ms:
            raise ValueError("ended_at_ms must be greater than or equal to started_at_ms")
        for event in self.events:
            if event.timestamp_ms < self.started_at_ms:
                raise ValueError("span event timestamp cannot be before span start")
            if self.ended_at_ms is not None and event.timestamp_ms > self.ended_at_ms:
                raise ValueError("span event timestamp cannot be after span end")

        provided = [
            field_name
            for field_name in _DETAIL_FIELD_BY_KIND.values()
            if getattr(self, field_name) is not None
        ]
        expected = _DETAIL_FIELD_BY_KIND.get(self.kind)
        if expected is None:
            if provided:
                raise ValueError(f"span kind '{self.kind}' does not allow typed details: {provided}")
        elif provided != [expected]:
            raise ValueError(f"span kind '{self.kind}' requires exactly {expected}")
        return self

    @property
    def duration_ms(self) -> int | None:
        if self.ended_at_ms is None:
            return None
        return self.ended_at_ms - self.started_at_ms


class TraceEnvelope(StrictBaseModel):
    trace_id: str = Field(..., min_length=1)
    schema_version: int = Field(default=1, ge=1)
    experiment_name: str | None = None
    taskpack_id: str | None = None
    task_id: str | None = None
    variant_id: str | None = None
    run_id: str | None = None
    created_at_ms: int = Field(..., ge=0)
    spans: list[TraceSpan] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("trace_id", "taskpack_id", "task_id", "variant_id", "run_id")
    @classmethod
    def ids_are_trace_tokens(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return validate_trace_token(value, info.field_name)

    @model_validator(mode="after")
    def spans_are_well_formed_tree(self) -> TraceEnvelope:
        span_ids = [span.span_id for span in self.spans]
        duplicates = sorted({span_id for span_id in span_ids if span_ids.count(span_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate span ids: {duplicates}")

        span_id_set = set(span_ids)
        roots = [span for span in self.spans if span.parent_span_id is None]
        if len(roots) != 1:
            raise ValueError("trace must contain exactly one root span")
        if roots[0].kind != SpanKind.TASK_RUN:
            raise ValueError("root span kind must be task_run")

        span_by_id = {span.span_id: span for span in self.spans}
        parent_by_span = {span.span_id: span.parent_span_id for span in self.spans}
        for span in self.spans:
            if span.trace_id != self.trace_id:
                raise ValueError(f"span trace_id does not match envelope trace_id: {span.span_id}")
            if span.parent_span_id == span.span_id:
                raise ValueError(f"span cannot be its own parent: {span.span_id}")
            if span.parent_span_id is not None and span.parent_span_id not in span_id_set:
                raise ValueError(f"span parent not found: {span.span_id} -> {span.parent_span_id}")
            if span.parent_span_id is not None:
                parent = span_by_id[span.parent_span_id]
                if span.started_at_ms < parent.started_at_ms:
                    raise ValueError(f"span starts before parent: {span.span_id}")
                if (
                    parent.ended_at_ms is not None
                    and span.ended_at_ms is not None
                    and span.ended_at_ms > parent.ended_at_ms
                ):
                    raise ValueError(f"span ends after parent: {span.span_id}")

        for span_id in span_ids:
            seen: set[str] = set()
            current = span_id
            while current is not None:
                if current in seen:
                    raise ValueError(f"cycle detected in span parent chain at: {span_id}")
                seen.add(current)
                current = parent_by_span[current]
        return self

    def root_span(self) -> TraceSpan:
        return next(span for span in self.spans if span.parent_span_id is None)

    def spans_by_parent(self) -> dict[str | None, list[TraceSpan]]:
        grouped: dict[str | None, list[TraceSpan]] = {}
        for span in self.spans:
            grouped.setdefault(span.parent_span_id, []).append(span)
        return grouped
