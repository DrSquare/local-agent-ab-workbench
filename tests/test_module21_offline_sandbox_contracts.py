from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from agent_ab.cli import app
from agent_ab.config import (
    load_yaml,
    validate_offline_docker_ab_run_plan,
    validate_offline_model_provider,
)
from agent_ab.schemas.offline import (
    DockerContainerPlan,
    DockerMount,
    DockerNetworkPolicy,
    OfflineDockerABRunPlan,
    OfflineModelProvider,
    ToolOrchestrationPolicy,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_offline_model_provider_examples_validate_without_endpoint_probes() -> None:
    ollama = validate_offline_model_provider(PROJECT_ROOT / "model_providers" / "local_ollama.yaml")
    docker_runner = validate_offline_model_provider(
        PROJECT_ROOT / "model_providers" / "docker_model_runner.yaml"
    )

    assert ollama.kind == "ollama"
    assert ollama.endpoint == "http://localhost:11434/v1"
    assert ollama.default_model == "llama3_8b"
    assert docker_runner.kind == "docker_model_runner"
    assert docker_runner.endpoint == "http://model-runner.docker.internal/engines/v1"
    assert docker_runner.require_preloaded_models is True
    assert docker_runner.allow_model_pull is False


def test_offline_model_provider_rejects_remote_or_pull_based_configs() -> None:
    with pytest.raises(ValidationError, match="offline endpoints"):
        OfflineModelProvider(
            id="remote_provider",
            kind="local_openai_compatible",
            endpoint="https://api.openai.com/v1",
            models=[{"id": "remote_model", "name": "gpt-4.1"}],
            default_model="remote_model",
        )

    with pytest.raises(ValidationError, match="allow_model_pull"):
        OfflineModelProvider(
            id="pulling_provider",
            kind="ollama",
            endpoint="http://localhost:11434/v1",
            models=[{"id": "llama3", "name": "llama3:8b"}],
            default_model="llama3",
            allow_model_pull=True,
        )

    with pytest.raises(ValidationError, match="default_model not found"):
        OfflineModelProvider(
            id="bad_default",
            kind="ollama",
            endpoint="http://llm-server:11434/v1",
            models=[{"id": "llama3", "name": "llama3:8b"}],
            default_model="missing",
        )


def test_offline_docker_ab_plan_example_validates_and_is_contract_only() -> None:
    plan = validate_offline_docker_ab_run_plan(
        PROJECT_ROOT / "sandbox_runs" / "offline_docker_ab_plan.yaml"
    )

    assert plan.id == "offline_docker_model_tool_ab"
    assert plan.offline is True
    assert plan.network.allow_external_network is False
    assert [variant.id for variant in plan.variants] == ["control", "variant"]
    assert plan.variants[0].tool_orchestration.mode == "sequential"
    assert plan.variants[1].tool_orchestration.mode == "native_parallel"
    assert all(mount.read_only for mount in plan.shared_mounts)
    assert plan.result_mount.read_only is False


def test_offline_docker_ab_plan_rejects_unresolved_variant_references() -> None:
    payload = load_yaml(PROJECT_ROOT / "sandbox_runs" / "offline_docker_ab_plan.yaml")
    payload["variants"][0]["model_id"] = "missing_model"

    with pytest.raises(ValidationError, match="references model_id"):
        OfflineDockerABRunPlan.model_validate(payload)

    payload = load_yaml(PROJECT_ROOT / "sandbox_runs" / "offline_docker_ab_plan.yaml")
    payload["variants"][0]["model_provider_id"] = "missing_provider"

    with pytest.raises(ValidationError, match="unknown model_provider_id"):
        OfflineDockerABRunPlan.model_validate(payload)


def test_offline_docker_ab_plan_rejects_unsafe_mounts_and_networks() -> None:
    payload = load_yaml(PROJECT_ROOT / "sandbox_runs" / "offline_docker_ab_plan.yaml")
    payload["shared_mounts"][0]["read_only"] = False

    with pytest.raises(ValidationError, match="shared mounts must be read-only"):
        OfflineDockerABRunPlan.model_validate(payload)

    with pytest.raises(ValidationError, match="Docker socket mounts"):
        DockerMount(source="/var/run/docker.sock", target="/var/run/docker.sock")

    with pytest.raises(ValidationError, match="allow_external_network"):
        DockerNetworkPolicy(allow_external_network=True)

    with pytest.raises(ValidationError, match="offline endpoints"):
        DockerNetworkPolicy(allowed_service_hosts=["api.openai.com"])


def test_container_and_tool_orchestration_policies_block_risky_configs() -> None:
    with pytest.raises(ValidationError, match="privileged containers"):
        DockerContainerPlan(image="agent:latest", privileged=True)

    with pytest.raises(ValidationError, match="secret-like environment"):
        DockerContainerPlan(image="agent:latest", env={"OPENCLAW_GATEWAY_TOKEN": "abc"})

    with pytest.raises(ValidationError, match="exactly one"):
        DockerContainerPlan(image="agent:latest", build_context="./agent")

    with pytest.raises(ValidationError, match="max_parallel_tools=1"):
        ToolOrchestrationPolicy(mode="sequential", max_parallel_tools=2)

    with pytest.raises(ValidationError, match="allow_native_parallel_calls"):
        ToolOrchestrationPolicy(mode="native_parallel", max_parallel_tools=2)


def test_offline_contract_cli_validators() -> None:
    runner = CliRunner()

    provider_result = runner.invoke(
        app,
        [
            "validate-offline-model-provider",
            str(PROJECT_ROOT / "model_providers" / "local_ollama.yaml"),
        ],
    )
    assert provider_result.exit_code == 0, provider_result.output
    assert "offline_model_provider=local_ollama@v1" in provider_result.output
    assert "default_model: llama3_8b" in provider_result.output

    plan_result = runner.invoke(
        app,
        [
            "validate-offline-ab-plan",
            str(PROJECT_ROOT / "sandbox_runs" / "offline_docker_ab_plan.yaml"),
        ],
    )
    assert plan_result.exit_code == 0, plan_result.output
    assert "offline_ab_plan=offline_docker_model_tool_ab@v1" in plan_result.output
    assert "variants: control, variant" in plan_result.output
