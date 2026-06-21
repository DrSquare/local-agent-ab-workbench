"""Common schema primitives used by experiment and prompt-object configs."""

from __future__ import annotations

import re
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from string import Formatter
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_LOCAL_ENDPOINT_HOSTS = {"localhost", "127.0.0.1", "::1"}
_FORMATTER = Formatter()


def is_identifier(value: str) -> bool:
    return bool(_IDENTIFIER_RE.match(value))


def _non_blank(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be blank")
    return value


def _non_blank_optional(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _non_blank(value, field_name)


def _normalized_non_blank_list(values: Iterable[str], field_name: str) -> list[str]:
    normalized: list[str] = []
    for value in values:
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} entries cannot be blank")
        normalized.append(stripped)
    duplicates = sorted({value for value in normalized if normalized.count(value) > 1})
    if duplicates:
        raise ValueError(f"duplicate {field_name} entries: {duplicates}")
    return normalized


def _validate_local_endpoint(value: str | None) -> str | None:
    if value is None:
        return None
    endpoint = value.strip()
    if not endpoint:
        raise ValueError("endpoint cannot be blank")
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("endpoint must be an http(s) URL with a local host")
    if parsed.hostname.lower() not in _LOCAL_ENDPOINT_HOSTS:
        raise ValueError("endpoint must use localhost, 127.0.0.1, or ::1")
    return endpoint


def prompt_template_variables(template: str) -> set[str]:
    """Return simple replacement fields used by a Python format template."""

    try:
        parts = list(_FORMATTER.parse(template))
    except ValueError as exc:
        raise ValueError(f"invalid prompt template: {exc}") from exc

    variables: set[str] = set()
    for _, field_name, format_spec, _ in parts:
        if field_name is None:
            continue
        root_name = field_name.split(".", 1)[0].split("[", 1)[0]
        if root_name != field_name or not field_name.isidentifier():
            raise ValueError(
                "prompt template variables must be simple identifiers: "
                f"{field_name}"
            )
        variables.add(field_name)
        if format_spec:
            variables.update(prompt_template_variables(format_spec))
    return variables


class StrictBaseModel(BaseModel):
    """Project-wide Pydantic defaults.

    Extra keys are rejected on purpose: these config files are meant to be edited
    by humans, and misspelled fields should fail fast.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        validate_assignment=True,
        use_enum_values=True,
    )


class AdapterKind(str, Enum):
    """Supported agent adapter families.

    Module 1 only defines the schema. The actual adapters are implemented later.
    """

    MOCK = "mock"
    OPENCLAW_CLI = "openclaw_cli"
    OPENCLAW_GATEWAY = "openclaw_gateway"
    GENERIC_CLI = "generic_cli"
    LOCAL_HTTP = "local_http"
    CUSTOM = "custom"


class ModelProvider(str, Enum):
    OLLAMA = "ollama"
    OPENCLAW = "openclaw"
    LOCAL_HTTP = "local_http"
    CUSTOM_CLI = "custom_cli"
    RECORDED_TRACE = "recorded_trace"
    MOCK = "mock"


class ToolKind(str, Enum):
    FILESYSTEM = "filesystem"
    SHELL = "shell"
    BROWSER = "browser"
    DESKTOP = "desktop"
    MCP = "mcp"
    RETRIEVAL = "retrieval"
    MEMORY = "memory"
    CUSTOM = "custom"


class ToolPolicy(str, Enum):
    ALLOW = "allow"
    READ_ONLY = "read_only"
    REQUIRE_CONFIRMATION = "require_confirmation"
    BLOCK = "block"


class ResponseFormatType(str, Enum):
    TEXT = "text"
    JSON = "json"
    JSON_SCHEMA = "json_schema"
    TOOL_CALL = "tool_call"


class PromptRole(str, Enum):
    SYSTEM = "system"
    DEVELOPER = "developer"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class TraceFormat(str, Enum):
    LOCAL_OPENINFERENCE_JSON = "local_openinference_json"
    OTEL_JSON = "otel_json"
    JSONL = "jsonl"


class IdentifierMixin(StrictBaseModel):
    id: str = Field(..., description="Stable identifier; letters, numbers, dash, dot, underscore.")

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not is_identifier(value):
            raise ValueError(
                "id must start with a letter and contain only letters, numbers, dash, dot, or underscore"
            )
        return value


class ModelConfig(StrictBaseModel):
    provider: ModelProvider = Field(default=ModelProvider.OLLAMA)
    name: str = Field(..., min_length=1, description="Provider-specific model name.")
    endpoint: str | None = Field(
        default=None,
        description="Optional local endpoint, e.g. http://localhost:11434 for Ollama-like APIs.",
    )
    context_window: int | None = Field(default=None, ge=1)
    timeout_seconds: int = Field(default=120, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        return _non_blank(value, "model name")

    @field_validator("endpoint")
    @classmethod
    def endpoint_is_local(cls, value: str | None) -> str | None:
        return _validate_local_endpoint(value)


class GenerationParameters(StrictBaseModel):
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1)
    max_tokens: int | None = Field(default=2048, ge=1)
    repeat_penalty: float | None = Field(default=None, ge=0.0)
    seed: int | None = Field(default=None)
    stop: list[str] = Field(default_factory=list)


class ToolSpec(StrictBaseModel):
    id: str | None = Field(default=None, description="Optional stable tool ID; defaults to name when omitted.")
    name: str = Field(..., min_length=1)
    kind: ToolKind = Field(default=ToolKind.CUSTOM)
    enabled: bool = True
    policy: ToolPolicy = Field(default=ToolPolicy.ALLOW)
    description: str | None = None
    input_schema: dict[str, Any] | None = None
    allowed_paths: list[str] = Field(default_factory=list)
    blocked_paths: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        return _non_blank(value, "tool name")

    @field_validator("allowed_paths", "blocked_paths")
    @classmethod
    def path_entries_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "path")

    @model_validator(mode="after")
    def normalize_and_validate_tool(self) -> ToolSpec:
        if self.id is None:
            self.id = self.name
        if not is_identifier(self.id):
            raise ValueError("tool id must start with a letter and contain only letters, numbers, dash, dot, or underscore")
        if self.policy == ToolPolicy.BLOCK and self.enabled:
            raise ValueError("blocked tools must also set enabled=false")
        return self


class ToolPolicyOverride(StrictBaseModel):
    allow_tools: list[str] = Field(default_factory=list)
    block_tools: list[str] = Field(default_factory=list)
    require_confirmation: list[str] = Field(default_factory=list)
    read_only_tools: list[str] = Field(default_factory=list)

    @field_validator("allow_tools", "block_tools", "require_confirmation", "read_only_tools")
    @classmethod
    def tool_names_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "tool override")

    @model_validator(mode="after")
    def tool_overrides_are_mutually_exclusive(self) -> ToolPolicyOverride:
        assignments: dict[str, str] = {}
        conflicts: list[str] = []
        for policy_name, tool_names in {
            "allow_tools": self.allow_tools,
            "block_tools": self.block_tools,
            "require_confirmation": self.require_confirmation,
            "read_only_tools": self.read_only_tools,
        }.items():
            for tool_name in tool_names:
                previous = assignments.setdefault(tool_name, policy_name)
                if previous != policy_name:
                    conflicts.append(f"{tool_name} in {previous} and {policy_name}")
        if conflicts:
            raise ValueError(f"conflicting tool policy overrides: {conflicts}")
        return self


class ResponseFormat(StrictBaseModel):
    type: ResponseFormatType = ResponseFormatType.TEXT
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    instructions: str | None = None

    @model_validator(mode="after")
    def schema_required_for_json_schema(self) -> ResponseFormat:
        if self.type == ResponseFormatType.JSON_SCHEMA and not self.schema_:
            raise ValueError("response_format.type=json_schema requires schema")
        return self


class PromptMessage(StrictBaseModel):
    role: PromptRole
    content: str = Field(..., min_length=1)
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        return _non_blank(value, "prompt message content")

    def template_variables(self) -> set[str]:
        return prompt_template_variables(self.content)

    def render(self, variables: dict[str, Any]) -> PromptMessage:
        missing = self.template_variables() - variables.keys()
        if missing:
            raise ValueError(f"missing template variables for prompt message: {sorted(missing)}")
        try:
            rendered = self.content.format(**variables)
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(f"failed to render prompt message: {exc}") from exc
        return self.model_copy(update={"content": rendered})


class FileRef(StrictBaseModel):
    path: Path
    description: str | None = None


class LocalModelRegistry(StrictBaseModel):
    provider: ModelProvider = ModelProvider.OLLAMA
    endpoint: str | None = None
    models: list[str] = Field(default_factory=list)

    @field_validator("endpoint")
    @classmethod
    def endpoint_is_local(cls, value: str | None) -> str | None:
        return _validate_local_endpoint(value)

    @field_validator("models")
    @classmethod
    def non_empty_model_names(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "model")
