"""Experiment schema for local offline A/B evaluation of desktop agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator, model_validator

from agent_ab.schemas.common import (
    AdapterKind,
    FileRef,
    LocalModelRegistry,
    ModelConfig,
    StrictBaseModel,
    ToolPolicyOverride,
    TraceFormat,
    _non_blank,
    _non_blank_optional,
    _normalized_non_blank_list,
)
from agent_ab.schemas.metrics import MetricSelection
from agent_ab.yaml_io import load_yaml_mapping


class RunLimits(StrictBaseModel):
    max_seconds_per_task: int = Field(default=180, ge=1)
    max_steps_per_task: int = Field(default=40, ge=1)
    max_parallelism: int = Field(default=1, ge=1)
    allowed_paths: list[str] = Field(default_factory=lambda: ["$RUN_WORKSPACE"])
    blocked_paths: list[str] = Field(default_factory=list)
    blocked_commands: list[str] = Field(default_factory=list)
    allow_network: bool = Field(default=False)
    network_allowlist: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])

    @field_validator("allowed_paths", "blocked_paths", "blocked_commands", "network_allowlist")
    @classmethod
    def list_entries_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "run limit")

    @model_validator(mode="after")
    def network_allowlist_requires_network_or_localhost(self) -> RunLimits:
        if not self.allow_network:
            non_local = [
                host
                for host in self.network_allowlist
                if host not in {"localhost", "127.0.0.1", "::1"}
            ]
            if non_local:
                raise ValueError(
                    "network_allowlist cannot include non-local hosts when allow_network=false: "
                    f"{non_local}"
                )
        return self


class AgentVariant(StrictBaseModel):
    label: str = Field(..., min_length=1)
    adapter: AdapterKind = Field(default=AdapterKind.MOCK)
    prompt_object: str = Field(
        ...,
        description="Relative or absolute path to a PromptObject YAML file.",
    )
    command: str | None = Field(
        default=None,
        description="Adapter-specific command, e.g. openclaw run --config ...",
    )
    env: dict[str, str] = Field(default_factory=dict)
    working_directory: str | None = None
    model_override: ModelConfig | None = None
    tool_policy_override: ToolPolicyOverride | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("label", "prompt_object")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _non_blank(value, "agent variant field")

    @field_validator("command", "working_directory")
    @classmethod
    def optional_strings_not_blank(cls, value: str | None) -> str | None:
        return _non_blank_optional(value, "agent variant field")

    @model_validator(mode="after")
    def command_required_for_cli_adapters(self) -> AgentVariant:
        if self.adapter in {AdapterKind.OPENCLAW_CLI, AdapterKind.GENERIC_CLI} and not self.command:
            raise ValueError(f"adapter {self.adapter} requires command")
        return self


class PlaygroundConfig(StrictBaseModel):
    enabled: bool = True
    allow_model_switching: bool = True
    allow_prompt_editing: bool = True
    allow_parameter_editing: bool = True
    allow_tool_policy_editing: bool = True
    save_views: bool = True
    max_replay_seconds: int = Field(default=180, ge=1)
    local_model_registry: LocalModelRegistry = Field(default_factory=LocalModelRegistry)


class TracingConfig(StrictBaseModel):
    enabled: bool = True
    capture_inputs: bool = True
    capture_outputs: bool = True
    capture_artifacts: bool = True
    capture_screenshots: bool = True
    capture_model_messages: bool = True
    redact_secrets: bool = True
    format: TraceFormat = TraceFormat.LOCAL_OPENINFERENCE_JSON
    include_span_events: bool = True
    include_timeline: bool = True
    max_preview_chars: int = Field(default=2000, ge=0)


class ArtifactConfig(StrictBaseModel):
    root: str = "runs"
    keep_success_artifacts: bool = True
    keep_failure_artifacts: bool = True
    write_jsonl: bool = True
    write_sqlite: bool = True
    sqlite_path: str = "runs/agent_ab.sqlite"

    @field_validator("root", "sqlite_path")
    @classmethod
    def paths_not_blank(cls, value: str) -> str:
        return _non_blank(value, "artifact path")


class BaselineConfig(StrictBaseModel):
    primary_variant: str = "A"
    candidate_variant: str = "B"
    compare_against: str | None = None


class ExperimentConfig(StrictBaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    offline: bool = True
    seed: int | None = 42
    repetitions: int = Field(default=1, ge=1)
    randomize_order: bool = True
    baseline: BaselineConfig = Field(default_factory=BaselineConfig)
    agents: dict[str, AgentVariant] = Field(min_length=2)
    taskpack: str = Field(..., description="Path to taskpack YAML or taskpack directory.")
    datasets: list[FileRef] = Field(default_factory=list)
    limits: RunLimits = Field(default_factory=RunLimits)
    metrics: MetricSelection = Field(default_factory=MetricSelection)
    playground: PlaygroundConfig = Field(default_factory=PlaygroundConfig)
    tracing: TracingConfig = Field(default_factory=TracingConfig)
    artifacts: ArtifactConfig = Field(default_factory=ArtifactConfig)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "taskpack")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _non_blank(value, "experiment field")

    @field_validator("agents")
    @classmethod
    def agent_keys_are_identifiers(cls, value: dict[str, AgentVariant]) -> dict[str, AgentVariant]:
        for key in value:
            if not key or not key.replace("_", "").replace("-", "").isalnum():
                raise ValueError(f"agent variant key must be alphanumeric/dash/underscore: {key}")
        return value

    @model_validator(mode="after")
    def validate_ab_baseline_keys(self) -> ExperimentConfig:
        missing = [
            key
            for key in (
                self.baseline.primary_variant,
                self.baseline.candidate_variant,
                self.baseline.compare_against,
            )
            if key is not None
            if key not in self.agents
        ]
        if missing:
            raise ValueError(f"baseline variant keys not found in agents: {missing}")
        if self.baseline.primary_variant == self.baseline.candidate_variant:
            raise ValueError("baseline primary_variant and candidate_variant must be different")

        if self.offline and self.limits.allow_network:
            raise ValueError("offline=true requires limits.allow_network=false")
        return self

    def variant_labels(self) -> dict[str, str]:
        return {variant_id: variant.label for variant_id, variant in self.agents.items()}

    def prompt_paths(self, base_dir: str | Path | None = None) -> dict[str, Path]:
        root = Path(base_dir) if base_dir else Path.cwd()
        paths: dict[str, Path] = {}
        for variant_id, variant in self.agents.items():
            prompt_path = Path(variant.prompt_object)
            if not prompt_path.is_absolute():
                prompt_path = root / prompt_path
            paths[variant_id] = prompt_path
        return paths

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> ExperimentConfig:
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
