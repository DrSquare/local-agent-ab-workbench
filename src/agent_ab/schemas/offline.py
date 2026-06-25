"""Offline model provider and isolated Docker A/B run-plan contracts."""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
from agent_ab.yaml_io import load_yaml_mapping

_LOCAL_ENDPOINT_HOSTS = {"localhost", "127.0.0.1", "::1"}
_DOCKER_INTERNAL_HOSTS = {
    "docker.internal",
    "host.docker.internal",
    "gateway.docker.internal",
    "model-runner.docker.internal",
}
_SINGLE_LABEL_HOST_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")
_SECRET_ENV_MARKERS = ("api_key", "apikey", "token", "secret", "password", "authorization")


class OfflineModelProviderKind(str, Enum):
    OLLAMA = "ollama"
    DOCKER_MODEL_RUNNER = "docker_model_runner"
    LOCAL_OPENAI_COMPATIBLE = "local_openai_compatible"
    MOCK = "mock"


class ToolOrchestrationMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    NATIVE_PARALLEL = "native_parallel"
    DISABLED = "disabled"


class DockerNetworkMode(str, Enum):
    NONE = "none"
    ISOLATED_BRIDGE = "isolated_bridge"


class DockerMountPurpose(str, Enum):
    INPUT = "input"
    OUTPUT = "output"
    WORKSPACE = "workspace"
    MODEL_CACHE = "model_cache"
    CONFIG = "config"
    ARTIFACT = "artifact"


class OfflineModelSpec(IdentifierMixin):
    """One locally available model name exposed by an offline provider."""

    name: str
    context_window: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        return _non_blank(value, "model name")

    @field_validator("tags")
    @classmethod
    def tags_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "model tag")


class OfflineModelProvider(IdentifierMixin):
    """Offline local model provider contract.

    This schema validates configuration only. It does not download models,
    contact endpoints, or start provider processes.
    """

    version: int = Field(default=1, ge=1)
    kind: OfflineModelProviderKind
    endpoint: str | None = None
    openai_compatible: bool = True
    require_preloaded_models: bool = True
    allow_model_pull: bool = False
    disable_remote_tracking: bool = True
    models: list[OfflineModelSpec] = Field(min_length=1)
    default_model: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("endpoint")
    @classmethod
    def endpoint_is_offline(cls, value: str | None) -> str | None:
        return _validate_offline_endpoint(value)

    @field_validator("default_model")
    @classmethod
    def default_model_is_identifier(cls, value: str) -> str:
        if not is_identifier(value):
            raise ValueError("default_model must reference a stable model id")
        return value

    @field_validator("tags")
    @classmethod
    def tags_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "model provider tag")

    @model_validator(mode="after")
    def provider_shape_is_offline_safe(self) -> OfflineModelProvider:
        model_ids = [model.id for model in self.models]
        duplicates = sorted({model_id for model_id in model_ids if model_ids.count(model_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate model ids: {duplicates}")
        if self.default_model not in set(model_ids):
            raise ValueError(f"default_model not found in models: {self.default_model}")
        if self.kind != OfflineModelProviderKind.MOCK and self.endpoint is None:
            raise ValueError(f"kind={self.kind} requires an offline endpoint")
        if self.allow_model_pull:
            raise ValueError("allow_model_pull must remain false for offline eval runs")
        if not self.require_preloaded_models:
            raise ValueError("require_preloaded_models must remain true for offline eval runs")
        if not self.disable_remote_tracking:
            raise ValueError("disable_remote_tracking must remain true for offline eval runs")
        return self

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> OfflineModelProvider:
        return cls.model_validate(load_yaml_mapping(path))

    def to_yaml_file(self, path: str | Path) -> None:
        _write_yaml_model(path, self)


class ToolOrchestrationPolicy(StrictBaseModel):
    mode: ToolOrchestrationMode = ToolOrchestrationMode.SEQUENTIAL
    max_tool_calls: int = Field(default=20, ge=0)
    max_retries: int = Field(default=2, ge=0)
    max_parallel_tools: int = Field(default=1, ge=1)
    require_argument_schema: bool = True
    detect_tool_loops: bool = True
    allow_native_parallel_calls: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def orchestration_shape_matches_mode(self) -> ToolOrchestrationPolicy:
        if self.mode == ToolOrchestrationMode.SEQUENTIAL and self.max_parallel_tools != 1:
            raise ValueError("sequential tool orchestration requires max_parallel_tools=1")
        if self.mode in {
            ToolOrchestrationMode.PARALLEL,
            ToolOrchestrationMode.NATIVE_PARALLEL,
        } and self.max_parallel_tools < 2:
            raise ValueError("parallel tool orchestration requires max_parallel_tools>=2")
        if self.mode == ToolOrchestrationMode.NATIVE_PARALLEL and not self.allow_native_parallel_calls:
            raise ValueError("native_parallel mode requires allow_native_parallel_calls=true")
        if not self.require_argument_schema:
            raise ValueError("require_argument_schema must remain true for A/B tool-orchestration evals")
        if not self.detect_tool_loops:
            raise ValueError("detect_tool_loops must remain true for A/B tool-orchestration evals")
        return self


class DockerMount(StrictBaseModel):
    source: str
    target: str
    read_only: bool = True
    purpose: DockerMountPurpose = DockerMountPurpose.INPUT

    @field_validator("source", "target")
    @classmethod
    def paths_not_blank(cls, value: str) -> str:
        return _non_blank(value, "docker mount path")

    @model_validator(mode="after")
    def mount_must_not_expose_docker_socket(self) -> DockerMount:
        joined = f"{self.source} {self.target}".lower().replace("\\", "/")
        if "docker.sock" in joined:
            raise ValueError("Docker socket mounts are not allowed in offline sandbox plans")
        return self


class DockerContainerPlan(StrictBaseModel):
    image: str | None = None
    build_context: str | None = None
    working_directory: str = "/workspace"
    command: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    mounts: list[DockerMount] = Field(default_factory=list)
    network_mode: DockerNetworkMode = DockerNetworkMode.ISOLATED_BRIDGE
    privileged: bool = False
    allow_docker_socket: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("image", "build_context")
    @classmethod
    def optional_strings_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_blank(value, "container image/build_context")

    @field_validator("working_directory")
    @classmethod
    def working_directory_not_blank(cls, value: str) -> str:
        return _non_blank(value, "container working_directory")

    @field_validator("command")
    @classmethod
    def command_entries_not_blank(cls, value: list[str]) -> list[str]:
        return [_non_blank(entry, "container command") for entry in value]

    @field_validator("env")
    @classmethod
    def env_keys_and_values_not_blank_or_secret(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, item in value.items():
            key = _non_blank(key, "container env key")
            item = _non_blank(item, "container env value")
            lowered = key.lower()
            if any(marker in lowered for marker in _SECRET_ENV_MARKERS):
                raise ValueError(
                    "secret-like environment variables must be injected at runtime, "
                    f"not stored in offline run plans: {key}"
                )
            normalized[key] = item
        return normalized

    @model_validator(mode="after")
    def container_is_isolated(self) -> DockerContainerPlan:
        if (self.image is None) == (self.build_context is None):
            raise ValueError("Docker container plan requires exactly one of image or build_context")
        if self.privileged:
            raise ValueError("privileged containers are not allowed in offline sandbox plans")
        if self.allow_docker_socket:
            raise ValueError("allow_docker_socket must remain false in offline sandbox plans")
        return self


class OfflineABVariant(IdentifierMixin):
    label: str
    solver_adapter: AdapterKind = AdapterKind.OPENCLAW_CLI
    model_provider_id: str
    model_id: str
    prompt_variant_id: str | None = None
    container: DockerContainerPlan
    tool_orchestration: ToolOrchestrationPolicy = Field(default_factory=ToolOrchestrationPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("label")
    @classmethod
    def label_not_blank(cls, value: str) -> str:
        return _non_blank(value, "variant label")

    @field_validator("model_provider_id", "model_id", "prompt_variant_id")
    @classmethod
    def refs_are_identifiers(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        if not is_identifier(value):
            raise ValueError(f"{info.field_name} must be a stable identifier")
        return value


class DockerNetworkPolicy(StrictBaseModel):
    mode: DockerNetworkMode = DockerNetworkMode.ISOLATED_BRIDGE
    allow_external_network: bool = False
    allowed_service_hosts: list[str] = Field(default_factory=list)

    @field_validator("allowed_service_hosts")
    @classmethod
    def hosts_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "allowed service host")

    @model_validator(mode="after")
    def network_is_offline(self) -> DockerNetworkPolicy:
        if self.allow_external_network:
            raise ValueError("allow_external_network must remain false for offline sandbox plans")
        for host in self.allowed_service_hosts:
            _validate_offline_host(host)
        if self.mode == DockerNetworkMode.NONE and self.allowed_service_hosts:
            raise ValueError("network mode none cannot declare allowed_service_hosts")
        return self


class OfflineDockerABRunPlan(IdentifierMixin):
    """Reviewable Docker A/B plan for offline agent evaluation.

    This is a plan artifact only. It does not build images, pull models, create
    networks, or launch containers.
    """

    version: int = Field(default=1, ge=1)
    description: str | None = None
    offline: bool = True
    eval_run_plan: str | None = None
    model_providers: list[OfflineModelProvider] = Field(min_length=1)
    variants: list[OfflineABVariant] = Field(min_length=2)
    shared_mounts: list[DockerMount] = Field(default_factory=list)
    result_mount: DockerMount
    network: DockerNetworkPolicy = Field(default_factory=DockerNetworkPolicy)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("eval_run_plan")
    @classmethod
    def eval_run_plan_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_blank(value, "eval_run_plan")

    @field_validator("tags")
    @classmethod
    def tags_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "offline run-plan tag")

    @model_validator(mode="after")
    def run_plan_is_safe_and_resolvable(self) -> OfflineDockerABRunPlan:
        if not self.offline:
            raise ValueError("offline must remain true for offline Docker A/B run plans")

        provider_ids = [provider.id for provider in self.model_providers]
        duplicate_providers = sorted({
            provider_id for provider_id in provider_ids if provider_ids.count(provider_id) > 1
        })
        if duplicate_providers:
            raise ValueError(f"duplicate model provider ids: {duplicate_providers}")

        variant_ids = [variant.id for variant in self.variants]
        duplicate_variants = sorted({
            variant_id for variant_id in variant_ids if variant_ids.count(variant_id) > 1
        })
        if duplicate_variants:
            raise ValueError(f"duplicate variant ids: {duplicate_variants}")

        models_by_provider = {
            provider.id: {model.id for model in provider.models}
            for provider in self.model_providers
        }
        for variant in self.variants:
            if variant.model_provider_id not in models_by_provider:
                raise ValueError(
                    f"variant '{variant.id}' references unknown model_provider_id: "
                    f"{variant.model_provider_id}"
                )
            if variant.model_id not in models_by_provider[variant.model_provider_id]:
                raise ValueError(
                    f"variant '{variant.id}' references model_id '{variant.model_id}' "
                    f"not declared by provider '{variant.model_provider_id}'"
                )

        writable_shared = [mount.target for mount in self.shared_mounts if not mount.read_only]
        if writable_shared:
            raise ValueError(f"shared mounts must be read-only: {writable_shared}")
        if self.result_mount.read_only:
            raise ValueError("result_mount must be writable")
        return self

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> OfflineDockerABRunPlan:
        return cls.model_validate(load_yaml_mapping(path))

    def to_yaml_file(self, path: str | Path) -> None:
        _write_yaml_model(path, self)


def _validate_offline_endpoint(value: str | None) -> str | None:
    if value is None:
        return None
    endpoint = value.strip()
    if not endpoint:
        raise ValueError("endpoint cannot be blank")
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("endpoint must be an http(s) URL")
    _validate_offline_host(parsed.hostname)
    return endpoint


def _validate_offline_host(host: str) -> str:
    host = host.strip().lower()
    if host in _LOCAL_ENDPOINT_HOSTS or host in _DOCKER_INTERNAL_HOSTS:
        return host
    if _SINGLE_LABEL_HOST_RE.match(host):
        return host
    raise ValueError(
        "offline endpoints must use localhost, Docker internal hosts, "
        f"or single-label container service hosts: {host}"
    )


def _write_yaml_model(path: str | Path, model: StrictBaseModel) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(
            model.model_dump(mode="json", by_alias=True, exclude_none=True),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
