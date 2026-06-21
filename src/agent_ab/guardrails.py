"""Local safety guardrails for prepared and executed agent runs."""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agent_ab.schemas.experiment import RunLimits

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_SECRET_ASSIGNMENT_RE = re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\b(\s*[:=]\s*)([^\s,'\"]+)")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


class GuardrailViolation(ValueError):
    """Raised when a run violates local safety policy."""


def enforce_path_policy(
    path: str | Path,
    *,
    workspace_path: str | Path,
    limits: RunLimits,
    run_dir: str | Path | None = None,
    extra_allowed_paths: Sequence[str | Path] = (),
    label: str = "path",
) -> Path:
    """Resolve and validate a path against allowed and blocked path policy."""

    workspace_root = Path(workspace_path).resolve()
    candidate = _resolve_candidate_path(path, workspace_root)
    context = _path_context(workspace_root, run_dir)
    allowed_entries: list[str | Path] = [*limits.allowed_paths, *extra_allowed_paths]
    allowed_roots = [_expand_policy_path(entry, context) for entry in allowed_entries]
    matching_allowed_roots = [
        allowed_root
        for allowed_root in allowed_roots
        if _is_relative_to(candidate, allowed_root)
    ]
    if not matching_allowed_roots:
        raise GuardrailViolation(f"{label} is outside allowed paths: {candidate}")

    blocked_roots = [
        _expand_policy_path(entry, context)
        for entry in limits.blocked_paths
        if not _is_unsupported_posix_root_block(entry)
    ]
    for blocked_root in blocked_roots:
        if _is_relative_to(candidate, blocked_root):
            more_specific_allow = any(_is_relative_to(allowed_root, blocked_root) for allowed_root in matching_allowed_roots)
            if more_specific_allow:
                continue
            raise GuardrailViolation(f"{label} is blocked by policy: {candidate}")
    return candidate


def enforce_command_policy(command: str | Sequence[str], limits: RunLimits) -> list[str]:
    """Reject commands matching configured blocked command patterns."""

    parts = shlex.split(command) if isinstance(command, str) else [str(part) for part in command]
    if not parts:
        raise GuardrailViolation("command cannot be empty")
    executable = Path(parts[0]).name.lower()
    normalized = " ".join(parts).lower()
    for blocked in limits.blocked_commands:
        blocked_parts = shlex.split(blocked)
        if not blocked_parts:
            continue
        blocked_executable = Path(blocked_parts[0]).name.lower()
        blocked_normalized = " ".join(blocked_parts).lower()
        if executable == blocked_executable or normalized.startswith(blocked_normalized):
            raise GuardrailViolation(f"command is blocked by policy: {blocked}")
    return parts


def enforce_local_endpoint(endpoint: str | None, limits: RunLimits, *, label: str = "endpoint") -> str | None:
    """Validate endpoint host against offline/local network policy."""

    if endpoint is None:
        return None
    parsed = urlparse(endpoint)
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise GuardrailViolation(f"{label} must include a hostname")
    allowlist = {host.lower() for host in limits.network_allowlist}
    if not limits.allow_network and hostname not in _LOCAL_HOSTS:
        raise GuardrailViolation(f"{label} must be localhost when network is disabled: {endpoint}")
    if allowlist and hostname not in allowlist:
        raise GuardrailViolation(f"{label} host is not in network_allowlist: {hostname}")
    return endpoint


def enforce_timeout_policy(timeout_seconds: int, limits: RunLimits) -> int:
    if timeout_seconds < 1:
        raise GuardrailViolation("timeout must be at least one second")
    if timeout_seconds > limits.max_seconds_per_task:
        raise GuardrailViolation(
            f"timeout exceeds max_seconds_per_task: {timeout_seconds} > {limits.max_seconds_per_task}"
        )
    return timeout_seconds


def enforce_command_plan(
    *,
    command: Sequence[str],
    working_directory: str | Path,
    config_path: str | Path,
    timeout_seconds: int,
    workspace_path: str | Path,
    run_dir: str | Path,
    limits: RunLimits,
) -> None:
    """Validate a prepared command plan before it can be executed later."""

    enforce_command_policy(command, limits)
    enforce_timeout_policy(timeout_seconds, limits)
    enforce_path_policy(
        working_directory,
        workspace_path=workspace_path,
        run_dir=run_dir,
        limits=limits,
        extra_allowed_paths=["$RUN_DIR"],
        label="working_directory",
    )
    enforce_path_policy(
        config_path,
        workspace_path=workspace_path,
        run_dir=run_dir,
        limits=limits,
        extra_allowed_paths=["$RUN_DIR"],
        label="config_path",
    )


def redact_text(value: str | None) -> str | None:
    if value is None:
        return None
    redacted = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)
    return _BEARER_RE.sub("Bearer [REDACTED]", redacted)


def redact_object(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if _looks_secret_key(str(key)) else redact_object(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_object(item) for item in value]
    return value


def _resolve_candidate_path(path: str | Path, workspace_root: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    return candidate.resolve()


def _path_context(workspace_root: Path, run_dir: str | Path | None) -> dict[str, Path]:
    context = {"$RUN_WORKSPACE": workspace_root}
    if run_dir is not None:
        context["$RUN_DIR"] = Path(run_dir).resolve()
    return context


def _expand_policy_path(entry: str | Path, context: dict[str, Path]) -> Path:
    raw = str(entry)
    if raw == "$HOME":
        return Path.home().resolve()
    for token, replacement in context.items():
        if raw == token:
            return replacement
        if raw.startswith(f"{token}/") or raw.startswith(f"{token}\\"):
            suffix = raw[len(token) + 1 :]
            return (replacement / suffix).resolve()
    return Path(raw).resolve()


def _is_relative_to(candidate: Path, root: Path) -> bool:
    return candidate == root or root in candidate.parents


def _looks_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in ("api_key", "apikey", "token", "secret", "password", "authorization"))


def _is_unsupported_posix_root_block(entry: str | Path) -> bool:
    return str(entry) == "/" and bool(Path.cwd().drive)
