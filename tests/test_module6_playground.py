from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_ab.schemas.playground import PlaygroundRunRequest
from agent_ab.server import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_PATH = "experiments/demo_openclaw_prompt_ab.yaml"


def test_playground_request_rejects_unsafe_paths_and_ids() -> None:
    with pytest.raises(ValidationError, match="cannot contain '..'"):
        PlaygroundRunRequest(
            experiment_path="../experiments/demo.yaml",
            variant_id="A",
            task_id="rename_todo",
        )

    with pytest.raises(ValidationError, match="view_id"):
        PlaygroundRunRequest(
            experiment_path=EXPERIMENT_PATH,
            variant_id="A",
            task_id="rename_todo",
            view_id="1bad",
        )


def test_playground_request_validates_model_overrides_are_local() -> None:
    with pytest.raises(ValidationError, match="endpoint must use localhost"):
        PlaygroundRunRequest(
            experiment_path=EXPERIMENT_PATH,
            variant_id="A",
            task_id="rename_todo",
            overrides={
                "model": {
                    "provider": "ollama",
                    "name": "remote-model",
                    "endpoint": "https://example.com",
                }
            },
        )


def test_playground_api_runs_mock_replay_and_persists_view(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            PROJECT_ROOT,
            runs_root=tmp_path / "runs",
            playground_root=tmp_path / "views",
        )
    )
    payload = {
        "experiment_path": EXPERIMENT_PATH,
        "variant_id": "A",
        "task_id": "rename_todo",
        "run_id": "playground.rename_todo.api",
        "save_view": True,
        "view_id": "view.rename_todo.api",
        "label": "Rename todo replay",
        "overrides": {
            "messages": [
                {
                    "role": "system",
                    "content": "Stay inside {workspace_path}.",
                },
                {
                    "role": "user",
                    "content": "Replay this task: {task_query}",
                },
            ],
            "model": {
                "provider": "ollama",
                "name": "qwen2.5-coder:7b",
                "endpoint": "http://localhost:11434",
            },
            "parameters": {
                "temperature": 0.1,
                "top_p": 0.8,
                "max_tokens": 1024,
            },
            "tool_policy": {
                "read_only_tools": ["read_file"],
                "block_tools": ["shell"],
            },
            "metadata": {"reason": "api-test"},
        },
    }

    response = client.post("/playground/runs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "playground.rename_todo.api"
    assert body["variant_id"] == "playground.A"
    assert body["status"] == "passed"
    assert body["view_id"] == "view.rename_todo.api"
    assert body["effective_prompt"]["model"]["name"] == "qwen2.5-coder:7b"
    assert body["effective_prompt"]["parameters"]["temperature"] == 0.1
    assert body["effective_prompt"]["metadata"]["playground_tool_policy_override"] == {
        "block_tools": ["shell"],
        "read_only_tools": ["read_file"],
        "allow_tools": [],
        "require_confirmation": [],
    }
    assert "Rename notes/todo.txt" in body["rendered_messages"][1]["content"]
    assert (tmp_path / "runs" / "playground.rename_todo.api" / "trace.jsonl").is_file()
    assert (tmp_path / "views" / "view.rename_todo.api.json").is_file()

    runs = client.get("/runs")
    assert runs.status_code == 200
    assert any(item["run_id"] == "playground.rename_todo.api" for item in runs.json()["runs"])

    views = client.get("/playground/views")
    assert views.status_code == 200
    view_summary = views.json()["views"][0]
    assert view_summary["id"] == "view.rename_todo.api"
    assert view_summary["run_id"] == "playground.rename_todo.api"
    assert view_summary["status"] == "passed"

    view = client.get("/playground/views/view.rename_todo.api")
    assert view.status_code == 200
    view_body = view.json()
    assert view_body["label"] == "Rename todo replay"
    assert view_body["response"]["trace_id"] == body["trace_id"]

    duplicate_view_payload = {**payload, "run_id": "playground.duplicate_view"}
    duplicate_view = client.post("/playground/runs", json=duplicate_view_payload)
    assert duplicate_view.status_code == 409
    assert "playground view already exists" in duplicate_view.json()["detail"]
    assert not (tmp_path / "runs" / "playground.duplicate_view").exists()


def test_playground_api_rejects_missing_prompt_variables_before_run(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            PROJECT_ROOT,
            runs_root=tmp_path / "runs",
            playground_root=tmp_path / "views",
        )
    )
    payload = {
        "experiment_path": EXPERIMENT_PATH,
        "variant_id": "A",
        "task_id": "rename_todo",
        "run_id": "playground.missing_variable",
        "overrides": {
            "messages": [
                {
                    "role": "user",
                    "content": "Task: {task_query}. Missing: {custom_note}",
                }
            ]
        },
    }

    response = client.post("/playground/runs", json=payload)

    assert response.status_code == 400
    assert "missing prompt variables" in response.json()["detail"]
    assert not (tmp_path / "runs" / "playground.missing_variable").exists()
