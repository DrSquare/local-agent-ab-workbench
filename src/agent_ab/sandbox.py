"""Sandbox provider helpers that reuse existing guardrail enforcement."""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from pathlib import Path

from agent_ab.guardrails import (
    GuardrailViolation,
    command_executable_name,
    enforce_command_policy,
    enforce_local_endpoint,
    enforce_path_policy,
    enforce_timeout_policy,
)
from agent_ab.schemas.experiment import RunLimits
from agent_ab.schemas.sandbox import (
    SandboxArtifactPolicy,
    SandboxCommandPolicy,
    SandboxDecision,
    SandboxEvent,
    SandboxEventType,
    SandboxNetworkPolicy,
    SandboxPolicyArea,
    SandboxProvider,
    SandboxProviderKind,
    SandboxTimeoutPolicy,
    SandboxWorkspacePolicy,
)


def sandbox_provider_from_run_limits(
    provider_id: str,
    limits: RunLimits,
    *,
    artifact_root: str = "runs",
    sqlite_path: str = "runs/agent_ab.sqlite",
    description: str | None = None,
) -> SandboxProvider:
    """Create a local workspace sandbox provider from existing run limits."""

    return SandboxProvider(
        id=provider_id,
        kind=SandboxProviderKind.LOCAL_WORKSPACE,
        description=description,
        workspace=SandboxWorkspacePolicy(
            allowed_paths=list(limits.allowed_paths),
            blocked_paths=list(limits.blocked_paths),
        ),
        command=SandboxCommandPolicy(blocked_commands=list(limits.blocked_commands)),
        network=SandboxNetworkPolicy(
            allow_network=limits.allow_network,
            network_allowlist=list(limits.network_allowlist),
        ),
        timeout=SandboxTimeoutPolicy(
            max_seconds_per_task=limits.max_seconds_per_task,
            max_steps_per_task=limits.max_steps_per_task,
            max_parallelism=limits.max_parallelism,
        ),
        artifacts=SandboxArtifactPolicy(root=artifact_root, sqlite_path=sqlite_path),
    )


def run_limits_from_sandbox_provider(provider: SandboxProvider) -> RunLimits:
    """Convert provider policy into the RunLimits shape consumed by guardrails."""

    return RunLimits(
        max_seconds_per_task=provider.timeout.max_seconds_per_task,
        max_steps_per_task=provider.timeout.max_steps_per_task,
        max_parallelism=provider.timeout.max_parallelism,
        allowed_paths=list(provider.workspace.allowed_paths),
        blocked_paths=list(provider.workspace.blocked_paths),
        blocked_commands=list(provider.command.blocked_commands),
        allow_network=provider.network.allow_network,
        network_allowlist=list(provider.network.network_allowlist),
    )


def enforce_provider_path_policy(
    path: str | Path,
    *,
    provider: SandboxProvider,
    workspace_path: str | Path,
    run_dir: str | Path | None = None,
    extra_allowed_paths: Sequence[str | Path] = (),
    label: str = "path",
) -> Path:
    """Validate a path through provider policy using existing guardrails."""

    return enforce_path_policy(
        path,
        workspace_path=workspace_path,
        run_dir=run_dir,
        limits=run_limits_from_sandbox_provider(provider),
        extra_allowed_paths=extra_allowed_paths,
        label=label,
    )


def enforce_provider_command_policy(command: str | Sequence[str], provider: SandboxProvider) -> list[str]:
    """Validate a command through provider policy using existing guardrails."""

    parts = enforce_command_policy(command, run_limits_from_sandbox_provider(provider))
    _enforce_allowed_commands(parts, provider)
    _enforce_confirmation_commands(parts, provider)
    return parts


def enforce_provider_endpoint(endpoint: str | None, provider: SandboxProvider, *, label: str = "endpoint") -> str | None:
    """Validate an endpoint through provider policy using existing guardrails."""

    return enforce_local_endpoint(endpoint, run_limits_from_sandbox_provider(provider), label=label)


def enforce_provider_timeout(timeout_seconds: int, provider: SandboxProvider) -> int:
    """Validate a timeout through provider policy using existing guardrails."""

    return enforce_timeout_policy(timeout_seconds, run_limits_from_sandbox_provider(provider))


def sandbox_denial_event_from_violation(
    *,
    event_id: str,
    provider_id: str,
    tool_name: str,
    policy_area: SandboxPolicyArea,
    violation: GuardrailViolation,
    requested_action: str | None = None,
    path: str | Path | None = None,
    command: Sequence[str] = (),
    endpoint: str | None = None,
) -> SandboxEvent:
    """Turn a guardrail violation into an EvalLog-compatible sandbox denial event."""

    return SandboxEvent(
        id=event_id,
        event_type=SandboxEventType.TOOL_DENIAL,
        decision=SandboxDecision.DENIED,
        provider_id=provider_id,
        tool_name=tool_name,
        policy_area=policy_area,
        reason=str(violation),
        requested_action=requested_action,
        path=str(path) if path is not None else None,
        command=[str(part) for part in command],
        endpoint=endpoint,
    )


def sandbox_approval_event(
    *,
    event_id: str,
    provider_id: str,
    tool_name: str,
    policy_area: SandboxPolicyArea,
    reason: str,
    requested_action: str | None = None,
    path: str | Path | None = None,
    command: Sequence[str] = (),
    endpoint: str | None = None,
) -> SandboxEvent:
    """Create an EvalLog-compatible sandbox approval event."""

    return SandboxEvent(
        id=event_id,
        event_type=SandboxEventType.TOOL_APPROVAL,
        decision=SandboxDecision.APPROVED,
        provider_id=provider_id,
        tool_name=tool_name,
        policy_area=policy_area,
        reason=reason,
        requested_action=requested_action,
        path=str(path) if path is not None else None,
        command=[str(part) for part in command],
        endpoint=endpoint,
    )


def _enforce_allowed_commands(parts: Sequence[str], provider: SandboxProvider) -> None:
    if not provider.command.allowed_commands:
        return
    normalized = " ".join(parts).lower()
    executable = command_executable_name(parts[0])
    for allowed in provider.command.allowed_commands:
        allowed_parts = shlex.split(allowed)
        if not allowed_parts:
            continue
        allowed_executable = command_executable_name(allowed_parts[0])
        allowed_normalized = " ".join(allowed_parts).lower()
        if executable == allowed_executable or normalized.startswith(allowed_normalized):
            return
    raise GuardrailViolation(f"command is not allowed by provider policy: {parts[0]}")


def _enforce_confirmation_commands(parts: Sequence[str], provider: SandboxProvider) -> None:
    normalized = " ".join(parts).lower()
    executable = command_executable_name(parts[0])
    for required in provider.command.require_confirmation:
        required_parts = shlex.split(required)
        if not required_parts:
            continue
        required_executable = command_executable_name(required_parts[0])
        required_normalized = " ".join(required_parts).lower()
        if executable == required_executable or normalized.startswith(required_normalized):
            raise GuardrailViolation(f"command requires explicit confirmation: {required}")
