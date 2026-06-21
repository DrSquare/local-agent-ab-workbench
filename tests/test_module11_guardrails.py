from __future__ import annotations

from pathlib import Path

import pytest

from agent_ab.adapters.openclaw import openclaw_trace_to_envelope
from agent_ab.guardrails import (
    GuardrailViolation,
    enforce_command_policy,
    enforce_local_endpoint,
    enforce_path_policy,
    enforce_timeout_policy,
    redact_object,
    redact_text,
)
from agent_ab.schemas.experiment import RunLimits


def test_path_policy_allows_workspace_and_blocks_escapes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    limits = RunLimits(
        allowed_paths=["$RUN_WORKSPACE"],
        blocked_paths=["$RUN_WORKSPACE/secrets"],
    )

    allowed = enforce_path_policy("notes/todo.txt", workspace_path=workspace, limits=limits)

    assert allowed == workspace / "notes" / "todo.txt"
    with pytest.raises(GuardrailViolation, match="outside allowed paths"):
        enforce_path_policy("../outside.txt", workspace_path=workspace, limits=limits)
    with pytest.raises(GuardrailViolation, match="blocked by policy"):
        enforce_path_policy("secrets/token.txt", workspace_path=workspace, limits=limits)


def test_command_policy_rejects_blocked_executables_and_sequences() -> None:
    limits = RunLimits(blocked_commands=["curl", "rm -rf /"])

    assert enforce_command_policy(["openclaw", "run"], limits) == ["openclaw", "run"]
    with pytest.raises(GuardrailViolation, match="curl"):
        enforce_command_policy(["curl", "https://example.com"], limits)
    with pytest.raises(GuardrailViolation, match="rm -rf /"):
        enforce_command_policy("rm -rf /", limits)


def test_network_and_timeout_policies_enforce_local_limits() -> None:
    limits = RunLimits(max_seconds_per_task=30, allow_network=False)

    assert enforce_local_endpoint("http://localhost:11434", limits) == "http://localhost:11434"
    assert enforce_timeout_policy(30, limits) == 30
    with pytest.raises(GuardrailViolation, match="localhost"):
        enforce_local_endpoint("https://example.com", limits)
    with pytest.raises(GuardrailViolation, match="timeout exceeds"):
        enforce_timeout_policy(31, limits)


def test_secret_redaction_handles_text_and_nested_objects() -> None:
    assert redact_text("token=abc123") == "token=[REDACTED]"
    assert redact_text("Authorization: Bearer abc123") == "Authorization: Bearer [REDACTED]"
    assert redact_object({"api_key": "abc123", "nested": {"password": "pw"}}) == {
        "api_key": "[REDACTED]",
        "nested": {"password": "[REDACTED]"},
    }


def test_openclaw_trace_wrapping_redacts_sensitive_payloads() -> None:
    trace = openclaw_trace_to_envelope(
        [
            {
                "kind": "tool",
                "name": "call local tool",
                "tool_name": "write_file",
                "arguments": {"path": "notes/action-items.txt", "api_key": "abc123"},
                "result_preview": "token=abc123",
                "started_at_ms": 1,
                "ended_at_ms": 2,
            }
        ],
        trace_id="trace.openclaw.redaction",
        taskpack_id="openclaw_demo",
        task_id="openclaw_rename_todo",
        variant_id="B",
        run_id="openclaw.rename_todo.redaction",
    )

    tool_span = next(span for span in trace.spans if span.kind == "tool")
    assert tool_span.tool_call.arguments["api_key"] == "[REDACTED]"
    assert tool_span.tool_call.result_preview == "token=[REDACTED]"
