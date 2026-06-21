from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_ab.config import load_taskpack, validate_experiment_bundle
from agent_ab.schemas.task import TaskPack, TaskValidator, validate_relative_workspace_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_demo_taskpack_validates() -> None:
    taskpack = load_taskpack(PROJECT_ROOT / "taskpacks" / "desktop_basics" / "tasks.yaml")

    assert taskpack.id == "desktop_basics"
    assert taskpack.version == 1
    assert [task.id for task in taskpack.tasks] == ["rename_todo"]
    assert taskpack.tasks[0].workspace.fixture == "workspaces/rename_todo"
    assert [validator.type for validator in taskpack.tasks[0].validators] == [
        "file_exists",
        "file_not_exists",
        "file_contains",
    ]


def test_experiment_bundle_validates_referenced_prompts_and_taskpack() -> None:
    experiment, prompts, taskpack = validate_experiment_bundle(
        PROJECT_ROOT / "experiments" / "demo_openclaw_prompt_ab.yaml"
    )

    assert experiment.name == "openclaw_prompt_ab_v1"
    assert set(prompts) == {"A", "B"}
    assert taskpack is not None
    assert taskpack.id == "desktop_basics"


def test_taskpack_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TaskPack.model_validate(
            {
                "id": "bad_pack",
                "version": 1,
                "tasks": [
                    {
                        "id": "task_one",
                        "query": "Do the thing.",
                        "workspace": {"fixture": "workspaces/task_one"},
                        "validators": [{"type": "file_exists", "path": "done.txt"}],
                    }
                ],
                "unexpected": True,
            }
        )


def test_taskpack_rejects_duplicate_task_ids() -> None:
    payload = {
        "id": "duplicate_tasks",
        "tasks": [
            {
                "id": "same_task",
                "query": "Do the first thing.",
                "workspace": {"fixture": "workspaces/first"},
                "validators": [{"type": "file_exists", "path": "done.txt"}],
            },
            {
                "id": "same_task",
                "query": "Do the second thing.",
                "workspace": {"fixture": "workspaces/second"},
                "validators": [{"type": "file_exists", "path": "done.txt"}],
            },
        ],
    }

    with pytest.raises(ValidationError, match="duplicate task ids"):
        TaskPack.model_validate(payload)


def test_validator_type_must_be_known_or_custom_prefixed() -> None:
    with pytest.raises(ValidationError, match="unknown validator type"):
        TaskValidator(type="made_up_validator", path="done.txt")

    validator = TaskValidator(type="custom.desktop_state", metadata={"check": "fixture"})
    assert validator.type == "custom.desktop_state"

    with pytest.raises(ValidationError, match="unknown validator type"):
        TaskValidator(type="custom.", metadata={})


def test_validator_paths_must_be_relative_and_portable() -> None:
    assert validate_relative_workspace_path("notes/todo.txt") == "notes/todo.txt"

    for bad_path in ["/notes/todo.txt", "../todo.txt", "notes\\todo.txt", "C:/Users/todo.txt"]:
        with pytest.raises(ValueError):
            validate_relative_workspace_path(bad_path)


def test_known_validators_require_type_specific_fields() -> None:
    with pytest.raises(ValidationError, match="requires path"):
        TaskValidator(type="file_exists")

    with pytest.raises(ValidationError, match="requires contains"):
        TaskValidator(type="file_contains", path="notes/todo.txt")

    with pytest.raises(ValidationError, match="requires pattern"):
        TaskValidator(type="file_matches_regex", path="notes/todo.txt")

    with pytest.raises(ValidationError, match="invalid validator regex pattern"):
        TaskValidator(type="file_matches_regex", path="notes/todo.txt", pattern="[")
