"""Sandbox provider contracts for guarded local execution."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator, model_validator

from agent_ab.schemas.common import (
    IdentifierMixin,
    StrictBaseModel,
    _non_blank,
    _normalized_non_blank_list,
    is_identifier,
)
from agent_ab.yaml_io import load_yaml_mapping

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class SandboxProviderKind(str, Enum):
    LOCAL_WORKSPACE = "local_workspace"
    DOCKER = "docker"
    CUSTOM = "custom"


class SandboxPolicyArea(str, Enum):
    WORKSPACE = "workspace"
    COMMAND = "command"
    NETWORK = "network"
    TIMEOUT = "timeout"
    ARTIFACT = "artifact"
    CUSTOM = "custom"


class SandboxDecision(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"


class SandboxEventType(str, Enum):
    TOOL_APPROVAL = "tool_approval"
    TOOL_DENIAL = "tool_denial"


class SandboxWorkspacePolicy(StrictBaseModel):
    workspace_root: str = "$RUN_WORKSPACE"
    allowed_paths: list[str] = Field(default_factory=lambda: ["$RUN_WORKSPACE"])
    blocked_paths: list[str] = Field(default_factory=list)
    require_isolated_workspace: bool = True
    cleanup: bool = False

    @field_validator("workspace_root")
    @classmethod
    def workspace_root_not_blank(cls, value: str) -> str:
        return _non_blank(value, "workspace_root")

    @field_validator("allowed_paths", "blocked_paths")
    @classmethod
    def path_entries_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "sandbox path")


class SandboxCommandPolicy(StrictBaseModel):
    allow_shell: bool = False
    allowed_commands: list[str] = Field(default_factory=list)
    blocked_commands: list[str] = Field(default_factory=list)
    require_confirmation: list[str] = Field(default_factory=list)

    @field_validator("allowed_commands", "blocked_commands", "require_confirmation")
    @classmethod
    def command_entries_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "sandbox command")

    @model_validator(mode="after")
    def command_sets_do_not_conflict(self) -> SandboxCommandPolicy:
        allowed = set(self.allowed_commands)
        blocked = set(self.blocked_commands)
        confirmation = set(self.require_confirmation)
        conflicts = sorted((allowed & blocked) | (blocked & confirmation))
        if conflicts:
            raise ValueError(f"conflicting sandbox command policy entries: {conflicts}")
        return self


class SandboxNetworkPolicy(StrictBaseModel):
    allow_network: bool = False
    network_allowlist: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])

    @field_validator("network_allowlist")
    @classmethod
    def network_entries_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "sandbox network allowlist")

    @model_validator(mode="after")
    def non_local_hosts_require_network(self) -> SandboxNetworkPolicy:
        if not self.allow_network:
            non_local = [host for host in self.network_allowlist if host.lower() not in _LOCAL_HOSTS]
            if non_local:
                raise ValueError(
                    "network_allowlist cannot include non-local hosts when allow_network=false: "
                    f"{non_local}"
                )
        return self


class SandboxTimeoutPolicy(StrictBaseModel):
    max_seconds_per_task: int = Field(default=180, ge=1)
    max_steps_per_task: int = Field(default=40, ge=1)
    max_parallelism: int = Field(default=1, ge=1)


class SandboxArtifactPolicy(StrictBaseModel):
    root: str = "runs"
    keep_success_artifacts: bool = True
    keep_failure_artifacts: bool = True
    write_jsonl: bool = True
    write_sqlite: bool = True
    sqlite_path: str = "runs/agent_ab.sqlite"
    redact_secrets: bool = True

    @field_validator("root", "sqlite_path")
    @classmethod
    def paths_not_blank(cls, value: str) -> str:
        return _non_blank(value, "sandbox artifact path")


class DockerSandboxPolicy(StrictBaseModel):
    image: str
    working_directory: str = "/workspace"
    network_mode: str = "none"
    mount_workspace_read_write: bool = True

    @field_validator("image", "working_directory", "network_mode")
    @classmethod
    def fields_not_blank(cls, value: str) -> str:
        return _non_blank(value, "docker sandbox field")


class SandboxProvider(IdentifierMixin):
    """Execution provider policy without executing the provider."""

    version: int = Field(default=1, ge=1)
    kind: SandboxProviderKind = SandboxProviderKind.LOCAL_WORKSPACE
    description: str | None = None
    workspace: SandboxWorkspacePolicy = Field(default_factory=SandboxWorkspacePolicy)
    command: SandboxCommandPolicy = Field(default_factory=SandboxCommandPolicy)
    network: SandboxNetworkPolicy = Field(default_factory=SandboxNetworkPolicy)
    timeout: SandboxTimeoutPolicy = Field(default_factory=SandboxTimeoutPolicy)
    artifacts: SandboxArtifactPolicy = Field(default_factory=SandboxArtifactPolicy)
    docker: DockerSandboxPolicy | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def tags_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "sandbox tag")

    @model_validator(mode="after")
    def provider_kind_matches_optional_config(self) -> SandboxProvider:
        if self.kind == SandboxProviderKind.DOCKER and self.docker is None:
            raise ValueError("kind=docker requires docker policy")
        if self.kind != SandboxProviderKind.DOCKER and self.docker is not None:
            raise ValueError("docker policy is only valid for kind=docker")
        return self

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> SandboxProvider:
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


class SandboxEvent(IdentifierMixin):
    """Approval or denial event that can be embedded in EvalLog metadata."""

    event_type: SandboxEventType
    decision: SandboxDecision
    provider_id: str
    tool_name: str
    policy_area: SandboxPolicyArea
    reason: str
    requested_action: str | None = None
    path: str | None = None
    command: list[str] = Field(default_factory=list)
    endpoint: str | None = None
    created_at_ms: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider_id")
    @classmethod
    def provider_id_is_identifier(cls, value: str) -> str:
        if not is_identifier(value):
            raise ValueError("provider_id must be a stable identifier")
        return value

    @field_validator("tool_name", "reason")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _non_blank(value, "sandbox event field")

    @field_validator("requested_action", "path", "endpoint")
    @classmethod
    def optional_strings_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_blank(value, "sandbox event field")

    @field_validator("command")
    @classmethod
    def command_entries_not_blank(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for entry in value:
            normalized.append(_non_blank(entry, "sandbox event command"))
        return normalized

    @model_validator(mode="after")
    def event_type_matches_decision(self) -> SandboxEvent:
        if self.decision == SandboxDecision.APPROVED and self.event_type != SandboxEventType.TOOL_APPROVAL:
            raise ValueError("approved sandbox events must use event_type=tool_approval")
        if self.decision == SandboxDecision.DENIED and self.event_type != SandboxEventType.TOOL_DENIAL:
            raise ValueError("denied sandbox events must use event_type=tool_denial")
        return self


def sandbox_events_metadata(events: list[SandboxEvent]) -> dict[str, Any]:
    """Return an EvalLog.metadata-compatible sandbox event payload."""

    return {"sandbox_events": [event.model_dump(mode="json") for event in events]}
