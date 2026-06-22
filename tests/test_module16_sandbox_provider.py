from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from agent_ab.analysis import (
    FailureTaxonomy,
    LoadedEvalLog,
    build_eval_log_rows,
    scan_eval_logs,
)
from agent_ab.cli import app
from agent_ab.config import validate_sandbox_provider
from agent_ab.guardrails import GuardrailViolation
from agent_ab.sandbox import (
    enforce_provider_command_policy,
    enforce_provider_endpoint,
    enforce_provider_path_policy,
    enforce_provider_timeout,
    run_limits_from_sandbox_provider,
    sandbox_denial_event_from_violation,
    sandbox_provider_from_run_limits,
)
from agent_ab.schemas.eval import EvalLog
from agent_ab.schemas.experiment import RunLimits
from agent_ab.schemas.sandbox import (
    SandboxDecision,
    SandboxEvent,
    SandboxEventType,
    SandboxNetworkPolicy,
    SandboxPolicyArea,
    SandboxProvider,
    sandbox_events_metadata,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_local_workspace_sandbox_provider_example_validates() -> None:
    provider = validate_sandbox_provider(PROJECT_ROOT / "sandboxes" / "local_workspace.yaml")

    assert provider.id == "local_workspace_default"
    assert provider.kind == "local_workspace"
    assert provider.workspace.allowed_paths == ["$RUN_WORKSPACE"]
    assert provider.network.allow_network is False
    assert provider.timeout.max_steps_per_task == 40
    assert provider.docker is None


def test_sandbox_provider_rejects_unknown_keys_and_invalid_network_allowlist() -> None:
    payload = {
        "id": "bad_provider",
        "kind": "local_workspace",
        "unexpected": True,
    }

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SandboxProvider.model_validate(payload)

    with pytest.raises(ValidationError, match="non-local hosts"):
        SandboxNetworkPolicy(allow_network=False, network_allowlist=["example.com"])


def test_docker_provider_is_contract_only_and_requires_docker_policy() -> None:
    provider = SandboxProvider(
        id="docker_contract",
        kind="docker",
        docker={
            "image": "local-agent-runner:latest",
            "working_directory": "/workspace",
            "network_mode": "none",
        },
    )

    assert provider.kind == "docker"
    assert provider.docker is not None
    assert provider.docker.image == "local-agent-runner:latest"

    with pytest.raises(ValidationError, match="kind=docker requires"):
        SandboxProvider(id="missing_docker_policy", kind="docker")

    with pytest.raises(ValidationError, match="only valid for kind=docker"):
        SandboxProvider(
            id="bad_local_policy",
            kind="local_workspace",
            docker={"image": "local-agent-runner:latest"},
        )


def test_sandbox_provider_maps_to_existing_guardrails(tmp_path: Path) -> None:
    limits = RunLimits(
        max_seconds_per_task=5,
        allowed_paths=["$RUN_WORKSPACE"],
        blocked_paths=["$RUN_WORKSPACE/secrets"],
        blocked_commands=["curl"],
        allow_network=False,
        network_allowlist=["localhost", "127.0.0.1"],
    )
    provider = sandbox_provider_from_run_limits("mapped_provider", limits)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    mapped = run_limits_from_sandbox_provider(provider)

    assert mapped.allowed_paths == limits.allowed_paths
    assert mapped.blocked_commands == ["curl"]
    assert enforce_provider_path_policy("notes/todo.txt", provider=provider, workspace_path=workspace) == (
        workspace / "notes" / "todo.txt"
    )
    assert enforce_provider_command_policy(["python", "-m", "agent_ab.cli"], provider) == [
        "python",
        "-m",
        "agent_ab.cli",
    ]
    assert enforce_provider_endpoint("http://localhost:8765", provider) == "http://localhost:8765"
    assert enforce_provider_timeout(5, provider) == 5
    with pytest.raises(GuardrailViolation, match="blocked by policy"):
        enforce_provider_path_policy("secrets/token.txt", provider=provider, workspace_path=workspace)
    with pytest.raises(GuardrailViolation, match="curl"):
        enforce_provider_command_policy(["curl", "https://example.com"], provider)
    with pytest.raises(GuardrailViolation, match="localhost"):
        enforce_provider_endpoint("https://example.com", provider)
    with pytest.raises(GuardrailViolation, match="timeout exceeds"):
        enforce_provider_timeout(6, provider)


def test_sandbox_provider_command_policy_enforces_allowlist_and_confirmation() -> None:
    provider = SandboxProvider(
        id="command_provider",
        command={
            "allowed_commands": ["python", "openclaw"],
            "blocked_commands": ["curl"],
            "require_confirmation": ["openclaw"],
        },
    )

    assert enforce_provider_command_policy(["python", "-m", "agent_ab.cli"], provider) == [
        "python",
        "-m",
        "agent_ab.cli",
    ]
    with pytest.raises(GuardrailViolation, match="not allowed"):
        enforce_provider_command_policy(["node", "--version"], provider)
    with pytest.raises(GuardrailViolation, match="curl"):
        enforce_provider_command_policy(["curl", "https://example.com"], provider)
    with pytest.raises(GuardrailViolation, match="requires explicit confirmation"):
        enforce_provider_command_policy(["openclaw", "run"], provider)


def test_sandbox_events_are_eval_log_metadata_compatible_and_scannable() -> None:
    event = sandbox_denial_event_from_violation(
        event_id="sandbox_denial_1",
        provider_id="local_workspace_default",
        tool_name="shell",
        policy_area=SandboxPolicyArea.COMMAND,
        violation=GuardrailViolation("command is blocked by policy: curl"),
        requested_action="shell.run",
        command=["curl", "https://example.com"],
    )
    log = EvalLog(
        eval_task_id="desktop_basics_mock_eval",
        eval_run_id="eval.desktop_basics_mock_eval.sandbox_denial",
        sample_id="rename_todo",
        taskpack_id="desktop_basics",
        task_id="rename_todo",
        solver_id="mock_solver",
        status="error",
        errors=[
            {
                "code": "sandbox_denial",
                "message": "Sandbox denied command.",
            }
        ],
        metadata=sandbox_events_metadata([event]),
    )

    loaded = LoadedEvalLog(path="runs/evals/denied/eval_log.json", log=log)
    rows = build_eval_log_rows([loaded])
    findings = scan_eval_logs([loaded])

    assert rows[0].failure_taxonomy == FailureTaxonomy.SANDBOX_DENIAL
    assert findings[0].category == FailureTaxonomy.SANDBOX_DENIAL
    assert findings[0].severity == "error"
    assert findings[0].evidence["tool_name"] == "shell"


def test_sandbox_event_rejects_conflicting_decision_shape() -> None:
    with pytest.raises(ValidationError, match="approved sandbox events"):
        SandboxEvent(
            id="bad_event",
            event_type=SandboxEventType.TOOL_DENIAL,
            decision=SandboxDecision.APPROVED,
            provider_id="local_workspace_default",
            tool_name="shell",
            policy_area=SandboxPolicyArea.COMMAND,
            reason="shape mismatch",
        )


def test_validate_sandbox_provider_cli() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "validate-sandbox-provider",
            str(PROJECT_ROOT / "sandboxes" / "local_workspace.yaml"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "sandbox_provider=local_workspace_default@v1" in result.output
    assert "kind: local_workspace" in result.output
    assert "network: local-only" in result.output
