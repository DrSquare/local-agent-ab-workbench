"""OpenClaw CLI adapter planning and trace wrapping.

Module 10 prepares local OpenClaw runs but does not execute the CLI by default.
Execution belongs behind the runtime guardrails added in later modules.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field

from agent_ab.config import (
    load_experiment,
    load_prompt_object,
    validate_taskpack_with_fixtures,
)
from agent_ab.guardrails import (
    GuardrailViolation,
    command_executable_name,
    enforce_command_plan,
    enforce_local_endpoint,
    redact_object,
    redact_text,
)
from agent_ab.runner import prepare_run_workspace
from agent_ab.schemas.common import AdapterKind, StrictBaseModel
from agent_ab.schemas.experiment import AgentVariant, ExperimentConfig
from agent_ab.schemas.prompt_object import PromptObject
from agent_ab.schemas.task import TaskCase
from agent_ab.schemas.trace import (
    DesktopActionDetail,
    ModelCallDetail,
    ShellActionDetail,
    SpanKind,
    SpanStatus,
    ToolCallDetail,
    TraceEnvelope,
    TraceSpan,
    validate_trace_token,
)

_TOKEN_SAFE_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


class OpenClawCommandPlan(StrictBaseModel):
    command: list[str] = Field(min_length=1)
    config_path: str
    working_directory: str
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int
    execute: bool = False


class OpenClawPreparedRun(StrictBaseModel):
    run_id: str
    trace_id: str
    task_id: str
    variant_id: str
    workspace_path: str
    run_dir: str
    config_path: str
    command_plan: OpenClawCommandPlan


class OpenClawExecutionResult(StrictBaseModel):
    run_id: str
    command: list[str]
    working_directory: str
    return_code: int
    status: str
    stdout_preview: str | None = None
    stderr_preview: str | None = None
    timed_out: bool = False


def prepare_openclaw_run(
    experiment_path: str | Path,
    variant_id: str,
    task_id: str,
    run_root: str | Path,
    *,
    run_id: str | None = None,
) -> OpenClawPreparedRun:
    """Prepare local workspace and config artifacts for an OpenClaw CLI run."""

    experiment_file = Path(experiment_path)
    experiment = load_experiment(experiment_file)
    safe_variant_id = validate_trace_token(variant_id, "variant_id")
    if safe_variant_id not in experiment.agents:
        raise ValueError(f"variant id not found in experiment: {safe_variant_id}")
    variant = experiment.agents[safe_variant_id]
    if variant.adapter != AdapterKind.OPENCLAW_CLI:
        raise ValueError(f"variant is not configured for openclaw_cli: {safe_variant_id}")

    taskpack_path = experiment.taskpack_path(experiment_file.parent)
    taskpack = validate_taskpack_with_fixtures(taskpack_path)
    tasks = {task.id: task for task in taskpack.tasks}
    if task_id not in tasks:
        raise ValueError(f"task id not found in taskpack: {task_id}")
    task = tasks[task_id]

    prompt = load_prompt_object(experiment.prompt_paths(experiment_file.parent)[safe_variant_id])
    effective_run_id = validate_trace_token(
        run_id or f"openclaw.{task.id}.{safe_variant_id}.1",
        "run_id",
    )
    workspace_path = prepare_run_workspace(taskpack_path, task, run_root, effective_run_id)
    run_dir = Path(run_root).resolve() / effective_run_id
    config_path = run_dir / "openclaw_config.yaml"
    write_openclaw_config(
        config_path,
        build_openclaw_config(
            experiment=experiment,
            variant_id=safe_variant_id,
            variant=variant,
            prompt=prompt,
            task=task,
            workspace_path=workspace_path,
        ),
    )
    command_plan = build_openclaw_command_plan(
        variant=variant,
        config_path=config_path,
        default_working_directory=run_dir,
        timeout_seconds=experiment.limits.max_seconds_per_task,
    )
    enforce_local_endpoint(prompt.model.endpoint, experiment.limits, label="prompt model endpoint")
    enforce_local_endpoint(
        experiment.playground.local_model_registry.endpoint,
        experiment.limits,
        label="playground model registry endpoint",
    )
    enforce_command_plan(
        command=command_plan.command,
        working_directory=command_plan.working_directory,
        config_path=command_plan.config_path,
        timeout_seconds=command_plan.timeout_seconds,
        workspace_path=workspace_path,
        run_dir=run_dir,
        limits=experiment.limits,
    )
    return OpenClawPreparedRun(
        run_id=effective_run_id,
        trace_id=f"trace.{effective_run_id}",
        task_id=task.id,
        variant_id=safe_variant_id,
        workspace_path=str(workspace_path),
        run_dir=str(run_dir),
        config_path=str(config_path),
        command_plan=command_plan,
    )


def execute_openclaw_plan(
    prepared: OpenClawPreparedRun,
    *,
    allow_execute: bool = False,
    runner: Callable[[OpenClawCommandPlan], Any] | None = None,
) -> OpenClawExecutionResult:
    """Execute a prepared OpenClaw command plan only after explicit opt-in."""

    if not allow_execute:
        raise GuardrailViolation("OpenClaw execution requires explicit allow_execute=True opt-in")

    plan = prepared.command_plan.model_copy(update={"execute": True})
    _validate_execution_plan(prepared, plan)
    completed = runner(plan) if runner is not None else _run_openclaw_subprocess(plan)
    return_code = int(_completed_field(completed, "returncode", -1))
    timed_out = bool(_completed_field(completed, "timed_out", False))
    return OpenClawExecutionResult(
        run_id=prepared.run_id,
        command=plan.command,
        working_directory=plan.working_directory,
        return_code=return_code,
        status=_execution_status(return_code, timed_out),
        stdout_preview=redact_text(_coerce_text(_completed_field(completed, "stdout", None))),
        stderr_preview=redact_text(_coerce_text(_completed_field(completed, "stderr", None))),
        timed_out=timed_out,
    )


def build_openclaw_config(
    *,
    experiment: ExperimentConfig,
    variant_id: str,
    variant: AgentVariant,
    prompt: PromptObject,
    task: TaskCase,
    workspace_path: Path,
) -> dict[str, Any]:
    """Translate workbench contracts to an OpenClaw-style local config payload."""

    return {
        "schema_version": 1,
        "adapter": "openclaw_cli",
        "experiment": {
            "name": experiment.name,
            "variant_id": variant_id,
            "variant_label": variant.label,
            "offline": experiment.offline,
        },
        "task": {
            "id": task.id,
            "query": task.query,
            "workspace_path": str(workspace_path),
        },
        "prompt": {
            "id": prompt.id,
            "version": prompt.version,
            "variables": prompt.variables,
            "messages": [
                message.model_dump(mode="json", by_alias=True, exclude_none=True)
                for message in prompt.messages
            ],
        },
        "model": prompt.model.model_dump(mode="json", by_alias=True, exclude_none=True),
        "parameters": prompt.parameters.model_dump(mode="json", by_alias=True, exclude_none=True),
        "tools": [
            tool.model_dump(mode="json", by_alias=True, exclude_none=True)
            for tool in prompt.tools
        ],
        "limits": experiment.limits.model_dump(mode="json", by_alias=True),
        "tracing": experiment.tracing.model_dump(mode="json", by_alias=True),
        "metadata": {
            "source": "local-agent-ab-workbench",
            "variant_metadata": variant.metadata,
        },
    }


def write_openclaw_config(path: str | Path, config: dict[str, Any]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return output_path


def build_openclaw_command_plan(
    *,
    variant: AgentVariant,
    config_path: str | Path,
    default_working_directory: str | Path,
    timeout_seconds: int,
) -> OpenClawCommandPlan:
    command = _command_with_config(variant.command or "", Path(config_path))
    executable = command_executable_name(command[0])
    if executable != "openclaw":
        raise ValueError("openclaw_cli variants must use the openclaw executable")
    default_working_path = Path(default_working_directory).resolve()
    if variant.working_directory:
        configured_working_path = Path(variant.working_directory)
        working_directory = (
            configured_working_path.resolve()
            if configured_working_path.is_absolute()
            else (default_working_path / configured_working_path).resolve()
        )
    else:
        working_directory = default_working_path
    return OpenClawCommandPlan(
        command=command,
        config_path=str(Path(config_path).resolve()),
        working_directory=str(working_directory),
        env=variant.env,
        timeout_seconds=timeout_seconds,
    )


def openclaw_trace_to_envelope(
    payload: dict[str, Any] | list[dict[str, Any]],
    *,
    trace_id: str,
    taskpack_id: str,
    task_id: str,
    variant_id: str,
    run_id: str,
) -> TraceEnvelope:
    """Wrap OpenClaw event/span payloads into the workbench trace contract."""

    safe_trace_id = validate_trace_token(trace_id, "trace_id")
    source_spans = payload.get("spans", []) if isinstance(payload, dict) else payload
    child_spans = [_openclaw_span_to_trace_span(item, index, safe_trace_id) for index, item in enumerate(source_spans, start=1)]
    max_end = max([span.ended_at_ms or span.started_at_ms for span in child_spans] or [1])
    root_id = "span.openclaw.root"
    spans = [
        TraceSpan(
            trace_id=safe_trace_id,
            span_id=root_id,
            name=task_id,
            kind=SpanKind.TASK_RUN,
            started_at_ms=0,
            ended_at_ms=max_end,
        )
    ]
    spans.extend(
        span.model_copy(update={"parent_span_id": span.parent_span_id or root_id})
        for span in child_spans
    )
    return TraceEnvelope(
        trace_id=safe_trace_id,
        taskpack_id=taskpack_id,
        task_id=task_id,
        variant_id=variant_id,
        run_id=run_id,
        created_at_ms=0,
        spans=spans,
        metadata={"source": "openclaw_cli"},
    )


def load_openclaw_trace(path: str | Path, **envelope_fields: str) -> TraceEnvelope:
    trace_path = Path(path)
    text = trace_path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"openclaw trace file is empty: {trace_path}")
    if trace_path.suffix.lower() == ".jsonl":
        payload: dict[str, Any] | list[dict[str, Any]] = [
            json.loads(line)
            for line in text.splitlines()
            if line.strip()
        ]
    else:
        payload = json.loads(text)
    return openclaw_trace_to_envelope(payload, **envelope_fields)


def _command_with_config(command: str, config_path: Path) -> list[str]:
    parts = shlex.split(command)
    if not parts:
        raise ValueError("openclaw command cannot be empty")
    config_value = str(config_path.resolve())
    if "--config" in parts:
        index = parts.index("--config")
        if index == len(parts) - 1:
            raise ValueError("openclaw command --config option must include a path")
        parts[index + 1] = config_value
    else:
        parts.extend(["--config", config_value])
    return parts


def _validate_execution_plan(prepared: OpenClawPreparedRun, plan: OpenClawCommandPlan) -> None:
    if not plan.command:
        raise GuardrailViolation("OpenClaw execution command cannot be empty")
    executable = command_executable_name(plan.command[0])
    if executable != "openclaw":
        raise GuardrailViolation("OpenClaw execution requires the openclaw executable")
    if plan.timeout_seconds < 1:
        raise GuardrailViolation("OpenClaw execution timeout must be at least one second")

    run_dir = Path(prepared.run_dir).resolve()
    config_path = Path(plan.config_path).resolve()
    working_directory = Path(plan.working_directory).resolve()
    if not _is_within(config_path, run_dir):
        raise GuardrailViolation("OpenClaw config_path must stay within the prepared run directory")
    if not _is_within(working_directory, run_dir):
        raise GuardrailViolation("OpenClaw working_directory must stay within the prepared run directory")
    if not config_path.is_file():
        raise GuardrailViolation(f"OpenClaw config_path does not exist: {config_path}")
    if not working_directory.is_dir():
        raise GuardrailViolation(f"OpenClaw working_directory does not exist: {working_directory}")


def _run_openclaw_subprocess(plan: OpenClawCommandPlan) -> Any:
    env = os.environ.copy()
    env.update(plan.env)
    try:
        return subprocess.run(
            plan.command,
            cwd=plan.working_directory,
            env=env,
            timeout=plan.timeout_seconds,
            capture_output=True,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": -1,
            "stdout": _coerce_text(exc.stdout),
            "stderr": _coerce_text(exc.stderr) or str(exc),
            "timed_out": True,
        }
    except OSError as exc:
        return {
            "returncode": -1,
            "stdout": None,
            "stderr": str(exc),
            "timed_out": False,
        }


def _completed_field(completed: Any, field: str, default: Any) -> Any:
    if isinstance(completed, dict):
        return completed.get(field, default)
    return getattr(completed, field, default)


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _execution_status(return_code: int, timed_out: bool) -> str:
    if timed_out:
        return "timeout"
    if return_code == 0:
        return "passed"
    return "failed"


def _is_within(candidate: Path, root: Path) -> bool:
    return candidate == root or root in candidate.parents


def _openclaw_span_to_trace_span(payload: dict[str, Any], index: int, trace_id: str) -> TraceSpan:
    name = str(payload.get("name") or payload.get("event") or f"openclaw_step_{index}")
    span_id = f"span.openclaw.{index}.{_safe_token(name)}"
    started_at_ms = int(payload.get("started_at_ms", payload.get("timestamp_ms", index)))
    ended_at_ms = payload.get("ended_at_ms")
    if ended_at_ms is None and payload.get("duration_ms") is not None:
        ended_at_ms = started_at_ms + int(payload["duration_ms"])

    kind, detail = _span_kind_and_detail(payload, name)
    return TraceSpan(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=None,
        name=name,
        kind=kind,
        status=_span_status(payload.get("status")),
        started_at_ms=started_at_ms,
        ended_at_ms=int(ended_at_ms) if ended_at_ms is not None else None,
        attributes=redact_object(dict(payload.get("attributes") or {})),
        **detail,
    )


def _span_kind_and_detail(payload: dict[str, Any], name: str) -> tuple[SpanKind, dict[str, Any]]:
    raw_kind = str(payload.get("kind") or payload.get("type") or "custom").strip().lower()
    if raw_kind in {"tool", "tool_call", "tool-call"}:
        return SpanKind.TOOL, {
            "tool_call": ToolCallDetail(
                tool_name=str(payload.get("tool_name") or name),
                arguments=redact_object(dict(payload.get("arguments") or {})),
                result_preview=redact_text(payload.get("result_preview")),
                error=redact_text(payload.get("error")),
            )
        }
    if raw_kind in {"shell", "shell_command", "shell-command", "command"}:
        return SpanKind.SHELL, {
            "shell_action": ShellActionDetail(
                command=str(payload.get("command") or name),
                exit_code=payload.get("exit_code"),
                stdout_preview=redact_text(payload.get("stdout_preview")),
                stderr_preview=redact_text(payload.get("stderr_preview")),
            )
        }
    if raw_kind in {"desktop", "desktop_action", "desktop-action"}:
        return SpanKind.DESKTOP, {
            "desktop_action": DesktopActionDetail(
                action=str(payload.get("action") or name),
                target=payload.get("target"),
                screenshot_before=payload.get("screenshot_before"),
                screenshot_after=payload.get("screenshot_after"),
            )
        }
    if raw_kind in {"llm", "llm_call", "llm-call", "model", "model_call", "model-call"}:
        return SpanKind.LLM, {
            "model_call": ModelCallDetail(
                provider=str(payload.get("provider") or "openclaw"),
                model=str(payload.get("model") or "unknown"),
                parameters=redact_object(dict(payload.get("parameters") or {})),
                input_preview=redact_text(payload.get("input_preview")),
                output_preview=redact_text(payload.get("output_preview")),
                prompt_tokens=payload.get("prompt_tokens"),
                completion_tokens=payload.get("completion_tokens"),
            )
        }
    return SpanKind.CUSTOM, {}


def _span_status(value: Any) -> SpanStatus:
    status = str(value or "").strip().lower()
    if status in {"error", "failed", "failure"}:
        return SpanStatus.ERROR
    if status in {"skipped", "skip"}:
        return SpanStatus.SKIPPED
    return SpanStatus.OK


def _safe_token(value: str) -> str:
    token = _TOKEN_SAFE_RE.sub("_", value).strip("._:-")
    return token or "span"
