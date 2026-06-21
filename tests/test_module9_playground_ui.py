from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_ab.server import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_PATH = "experiments/demo_openclaw_prompt_ab.yaml"


def test_playground_defaults_endpoint_returns_variant_prompt_and_controls(tmp_path: Path) -> None:
    client = TestClient(create_app(PROJECT_ROOT, runs_root=tmp_path / "runs"))

    response = client.get(
        "/playground/defaults",
        params={"experiment_path": EXPERIMENT_PATH, "variant_id": "B"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["variant_id"] == "B"
    assert body["variants"] == ["A", "B"]
    assert body["task_ids"] == ["rename_todo"]
    assert body["prompt"]["id"] == "openclaw_candidate_playground_prompt"
    assert body["prompt"]["model"]["name"] == "qwen2.5-coder:7b"
    assert body["capabilities"]["allow_prompt_editing"] is True
    assert "qwen2.5-coder:7b" in body["local_model_registry"]["models"]

    missing_variant = client.get(
        "/playground/defaults",
        params={"experiment_path": EXPERIMENT_PATH, "variant_id": "missing"},
    )
    assert missing_variant.status_code == 400
    assert "variant id not found" in missing_variant.json()["detail"]


def test_playground_ui_assets_include_module9_editor_controls(tmp_path: Path) -> None:
    client = TestClient(create_app(PROJECT_ROOT, runs_root=tmp_path / "runs"))

    html = client.get("/ui").text
    css = client.get("/ui/app.css").text
    js = client.get("/ui/app.js").text

    assert "Prompt editor" in html
    assert 'id="pgModelName"' in html
    assert 'id="pgAllowTools"' in html
    assert "Save candidate" in html
    assert "/playground/defaults" in js
    assert "collectPlaygroundOverrides" in js
    assert "renderPlaygroundResult" in js
    assert ".prompt-card" in css
    assert ".rendered-message" in css
    assert "font-size: clamp" not in css
    assert "letter-spacing: 0;" in css


def test_playground_ui_payload_shape_runs_and_saves_candidate(tmp_path: Path) -> None:
    client = TestClient(
        create_app(
            PROJECT_ROOT,
            runs_root=tmp_path / "runs",
            playground_root=tmp_path / "views",
        )
    )
    payload = {
        "experiment_path": EXPERIMENT_PATH,
        "variant_id": "B",
        "task_id": "rename_todo",
        "run_id": "playground.rename_todo.module9",
        "save_view": True,
        "view_id": "view.rename_todo.module9",
        "label": "Module 9 candidate",
        "prompt_variables": {},
        "overrides": {
            "messages": [
                {"role": "system", "content": "Stay inside {workspace_path}."},
                {"role": "user", "content": "Complete: {task_query}"},
            ],
            "variables": ["task_query", "workspace_path"],
            "model": {
                "provider": "ollama",
                "name": "qwen2.5-coder:7b",
                "endpoint": "http://localhost:11434",
            },
            "parameters": {
                "temperature": 0.05,
                "top_p": 0.8,
                "max_tokens": 1024,
            },
            "tool_policy": {
                "allow_tools": ["write_file"],
                "read_only_tools": ["read_file"],
                "require_confirmation": [],
                "block_tools": ["shell"],
            },
            "metadata": {"source": "module9_playground_ui"},
        },
    }

    response = client.post("/playground/runs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert body["view_id"] == "view.rename_todo.module9"
    assert body["effective_prompt"]["parameters"]["temperature"] == 0.05
    assert body["effective_prompt"]["metadata"]["playground_override_metadata"] == {
        "source": "module9_playground_ui"
    }
    assert "Rename notes/todo.txt" in body["rendered_messages"][1]["content"]
    assert (tmp_path / "views" / "view.rename_todo.module9.json").is_file()
