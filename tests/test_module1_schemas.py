from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_ab.config import (
    ConfigLoadError,
    load_prompt_object,
    load_yaml,
    validate_experiment_with_prompts,
)
from agent_ab.schemas.common import ModelConfig, ToolPolicyOverride
from agent_ab.schemas.experiment import ExperimentConfig
from agent_ab.schemas.metrics import AGENTEVAL_METRIC_REGISTRY, MetricSelection, metric_names
from agent_ab.schemas.prompt_object import PromptObject

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_demo_experiment_validates_with_referenced_prompts() -> None:
    experiment, prompts = validate_experiment_with_prompts(
        PROJECT_ROOT / "experiments" / "demo_openclaw_prompt_ab.yaml"
    )

    assert experiment.name == "openclaw_prompt_ab_v1"
    assert set(experiment.agents) == {"A", "B"}
    assert prompts["A"].id == "openclaw_baseline_prompt"
    assert prompts["B"].id == "openclaw_candidate_playground_prompt"
    assert experiment.metrics.primary == "task_success"
    assert "root_cause_accuracy" in experiment.metrics.secondary


def test_prompt_object_renders_declared_variables() -> None:
    prompt = load_prompt_object(PROJECT_ROOT / "prompts" / "baseline_openclaw.yaml")

    rendered = prompt.render_messages(
        {
            "task_query": "Rename notes/todo.txt to notes/action-items.txt",
            "workspace_path": "/tmp/workspace",
        }
    )

    assert any("/tmp/workspace" in message.content for message in rendered)
    assert any("Rename notes/todo.txt" in message.content for message in rendered)
    assert prompt.enabled_tool_names() == ["list_files", "read_file", "write_file"]


def test_prompt_render_missing_variable_fails() -> None:
    prompt = load_prompt_object(PROJECT_ROOT / "prompts" / "baseline_openclaw.yaml")

    with pytest.raises(ValueError, match="missing prompt variables"):
        prompt.render_messages({"task_query": "Do the task"})


def test_prompt_object_infers_variables_when_not_declared() -> None:
    prompt = PromptObject.model_validate(
        {
            "id": "inferred_prompt",
            "messages": [
                {"role": "system", "content": "Use workspace {workspace_path}."},
                {"role": "user", "content": "Do {task_query}."},
            ],
            "model": {"provider": "mock", "name": "mock-model"},
        }
    )

    assert prompt.variables == ["task_query", "workspace_path"]


def test_prompt_template_supports_escaped_braces_and_format_specs() -> None:
    prompt = PromptObject.model_validate(
        {
            "id": "formatted_prompt",
            "messages": [
                {
                    "role": "system",
                    "content": "Literal {{task_query}} in {workspace_path!r}.",
                },
                {"role": "user", "content": "Task: {task_query:>{width}}"},
            ],
            "model": {"provider": "mock", "name": "mock-model"},
        }
    )

    assert prompt.variables == ["task_query", "width", "workspace_path"]
    rendered = prompt.render_messages(
        {"task_query": "rename", "workspace_path": "/tmp/workspace", "width": 10}
    )
    assert "{task_query}" in rendered[0].content
    assert "'/tmp/workspace'" in rendered[0].content
    assert "    rename" in rendered[1].content


def test_prompt_template_rejects_unescaped_literal_braces() -> None:
    with pytest.raises(ValidationError, match="simple identifiers"):
        PromptObject.model_validate(
            {
                "id": "bad_json_prompt",
                "messages": [
                    {"role": "user", "content": 'Return JSON like {"ok": true}.'},
                ],
                "model": {"provider": "mock", "name": "mock-model"},
            }
        )


def test_prompt_object_rejects_duplicate_tool_names_and_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate tool names"):
        PromptObject.model_validate(
            {
                "id": "duplicate_tools",
                "messages": [{"role": "user", "content": "Do {task_query}."}],
                "model": {"provider": "mock", "name": "mock-model"},
                "tools": [
                    {"name": "read_file", "kind": "filesystem"},
                    {"name": "read_file", "kind": "filesystem"},
                ],
            }
        )

    with pytest.raises(ValidationError, match="duplicate tool ids"):
        PromptObject.model_validate(
            {
                "id": "duplicate_tool_ids",
                "messages": [{"role": "user", "content": "Do {task_query}."}],
                "model": {"provider": "mock", "name": "mock-model"},
                "tools": [
                    {"id": "fs.read", "name": "read_file", "kind": "filesystem"},
                    {"id": "fs.read", "name": "read_again", "kind": "filesystem"},
                ],
            }
        )


def test_metric_registry_includes_agenteval_inspired_metrics() -> None:
    names = set(metric_names())

    assert "tool_success" in names
    assert "tool_sequence_adherence" in names
    assert "stochastic_success_rate" in names
    assert "trace_replay_determinism" in names
    assert "rag_faithfulness" in names
    assert "memory_retention" in names
    assert "dag_node_quality" in names
    assert "root_cause_accuracy" in names
    assert AGENTEVAL_METRIC_REGISTRY["latency_ms"].direction == "minimize"


def test_unknown_metric_fails_unless_custom_prefixed() -> None:
    with pytest.raises(ValidationError, match="unknown metric"):
        MetricSelection(primary="made_up_metric")

    selection = MetricSelection(primary="custom.desktop_click_precision")
    assert selection.primary == "custom.desktop_click_precision"

    with pytest.raises(ValidationError, match="unknown metric"):
        MetricSelection(primary="custom.")


def test_model_endpoints_must_be_local() -> None:
    config = ModelConfig(provider="ollama", name="llama3.1:8b", endpoint=" http://localhost:11434 ")
    assert config.endpoint == "http://localhost:11434"

    with pytest.raises(ValidationError, match="endpoint must use localhost"):
        ModelConfig(provider="ollama", name="remote", endpoint="https://api.example.com/v1")


def test_tool_policy_overrides_reject_conflicts() -> None:
    with pytest.raises(ValidationError, match="conflicting tool policy overrides"):
        ToolPolicyOverride.model_validate(
            {
                "allow_tools": ["read_file"],
                "block_tools": ["read_file"],
            }
        )


def test_experiment_rejects_offline_network() -> None:
    payload = {
        "name": "bad_network_exp",
        "offline": True,
        "agents": {
            "A": {"label": "a", "adapter": "mock", "prompt_object": "a.yaml"},
            "B": {"label": "b", "adapter": "mock", "prompt_object": "b.yaml"},
        },
        "taskpack": "tasks.yaml",
        "limits": {"allow_network": True},
    }

    with pytest.raises(ValidationError, match="offline=true"):
        ExperimentConfig.model_validate(payload)


def test_cli_adapter_requires_command() -> None:
    payload = {
        "name": "bad_cli_exp",
        "agents": {
            "A": {"label": "a", "adapter": "openclaw_cli", "prompt_object": "a.yaml"},
            "B": {"label": "b", "adapter": "mock", "prompt_object": "b.yaml"},
        },
        "taskpack": "tasks.yaml",
    }

    with pytest.raises(ValidationError, match="requires command"):
        ExperimentConfig.model_validate(payload)


def test_experiment_rejects_invalid_baseline_variants() -> None:
    payload = {
        "name": "bad_baseline_exp",
        "agents": {
            "A": {"label": "a", "adapter": "mock", "prompt_object": "a.yaml"},
            "B": {"label": "b", "adapter": "mock", "prompt_object": "b.yaml"},
        },
        "baseline": {"primary_variant": "A", "candidate_variant": "A"},
        "taskpack": "tasks.yaml",
    }

    with pytest.raises(ValidationError, match="must be different"):
        ExperimentConfig.model_validate(payload)

    payload["baseline"] = {
        "primary_variant": "A",
        "candidate_variant": "B",
        "compare_against": "C",
    }
    with pytest.raises(ValidationError, match="baseline variant keys not found"):
        ExperimentConfig.model_validate(payload)


def test_yaml_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    config_path = tmp_path / "duplicate.yaml"
    config_path.write_text("name: first\nname: second\n", encoding="utf-8")

    with pytest.raises(ConfigLoadError, match="duplicate key: name"):
        load_yaml(config_path)
