from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_ab.improvement import (
    CandidatePromotionRequest,
    ImprovementNoteRequest,
    RerunQueueRequest,
    build_improvement_read_model,
)
from agent_ab.server import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_PATH = "experiments/demo_openclaw_prompt_ab.yaml"


def test_improvement_requests_reject_unknown_keys_blank_text_and_duplicate_tags() -> None:
    note_payload = {
        "eval_task_id": "desktop_basics_eval",
        "sample_id": "rename_todo",
        "eval_run_id": "eval.module19.note",
        "body": "Compare the saved candidate before promotion.",
        "tags": ["prompt", "harness"],
    }

    ImprovementNoteRequest.model_validate(note_payload)

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        ImprovementNoteRequest.model_validate({**note_payload, "unexpected": True})

    with pytest.raises(ValueError, match="improvement note field"):
        ImprovementNoteRequest.model_validate({**note_payload, "body": " "})

    with pytest.raises(ValueError, match="duplicate"):
        ImprovementNoteRequest.model_validate({**note_payload, "tags": ["prompt", "prompt"]})

    with pytest.raises(ValueError, match="candidate promotion label"):
        CandidatePromotionRequest(playground_view_id="view.rename_todo.module19", label=" ")

    with pytest.raises(ValueError, match="rerun queue field"):
        RerunQueueRequest(
            eval_task_id="desktop_basics_eval",
            sample_id="rename_todo",
            task_id="rename_todo",
            solver_id="mock",
            eval_run_id="eval.module19.rerun",
            reason=" ",
        )


def test_improvement_api_persists_notes_rerun_queue_and_promotion_artifacts(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    views_root = tmp_path / "views"
    client = TestClient(
        create_app(
            PROJECT_ROOT,
            runs_root=runs_root,
            playground_root=views_root,
        )
    )

    view_response = client.post(
        "/playground/runs",
        json={
            "experiment_path": EXPERIMENT_PATH,
            "variant_id": "B",
            "task_id": "rename_todo",
            "run_id": "playground.rename_todo.module19",
            "save_view": True,
            "view_id": "view.rename_todo.module19",
            "label": "Module 19 candidate",
            "overrides": {
                "metadata": {"source": "module19_improvement_loop"},
            },
        },
    )
    assert view_response.status_code == 200

    note_response = client.post(
        "/improvements/notes",
        json={
            "eval_task_id": "desktop_basics_eval",
            "sample_id": "rename_todo",
            "eval_run_id": "eval.module19.source",
            "trace_id": "trace.module19.source",
            "triage_note_id": "triage.1",
            "playground_view_id": "view.rename_todo.module19",
            "body": "Candidate fixes the prompt but needs a rerun.",
            "status": "open",
            "tags": ["prompt"],
        },
    )
    assert note_response.status_code == 200
    assert note_response.json()["id"] == "improvement.note.1"

    rerun_response = client.post(
        "/improvements/rerun-queue",
        json={
            "eval_task_id": "desktop_basics_eval",
            "sample_id": "rename_todo",
            "task_id": "rename_todo",
            "solver_id": "mock",
            "variant_id": "B",
            "eval_run_id": "eval.module19.source",
            "trace_id": "trace.module19.source",
            "source": "regression_review",
            "reason": "Rerun after candidate promotion.",
            "tags": ["rerun"],
        },
    )
    assert rerun_response.status_code == 200
    assert rerun_response.json()["id"] == "rerun.1"

    promotion_response = client.post(
        "/improvements/promotions",
        json={
            "playground_view_id": "view.rename_todo.module19",
            "label": "Promote Module 19 candidate",
            "source_eval_run_id": "eval.module19.source",
            "source_trace_id": "trace.module19.source",
            "source_triage_note_id": "triage.1",
            "notes": "Write review artifacts only.",
        },
    )
    assert promotion_response.status_code == 200
    promotion = promotion_response.json()
    assert promotion["id"] == "promotion.1"
    assert promotion["playground_view_id"] == "view.rename_todo.module19"
    assert promotion["source_triage_note_id"] == "triage.1"
    assert "source configs are not mutated" in promotion["guardrail_reminders"][0]

    artifact_path = _response_path(promotion["artifact_path"])
    prompt_path = _response_path(promotion["prompt_snapshot_path"])
    request_path = _response_path(promotion["run_request_path"])
    assert artifact_path.is_file()
    assert prompt_path.is_file()
    assert request_path.is_file()
    assert json.loads(request_path.read_text(encoding="utf-8"))["view_id"] == "view.rename_todo.module19"

    model = build_improvement_read_model(runs_root, PROJECT_ROOT)
    assert len(model.notes) == 1
    assert len(model.rerun_queue) == 1
    assert any(item.id == "promotion.1" for item in model.promotions)

    read_response = client.get("/improvements")
    assert read_response.status_code == 200
    read_body = read_response.json()
    assert len(read_body["notes"]) == 1
    assert len(read_body["rerun_queue"]) == 1
    assert len(read_body["promotions"]) == 1
    assert read_body["guardrail_reminders"]


def test_module19_ui_assets_expose_improvement_loop_controls(tmp_path: Path) -> None:
    client = TestClient(create_app(PROJECT_ROOT, runs_root=tmp_path / "runs"))

    html = client.get("/ui").text
    css = client.get("/ui/app.css").text
    js = client.get("/ui/app.js").text

    assert 'id="openRegressionImproveButton"' in html
    assert 'id="improvementContext"' in html
    assert 'id="improvementDiff"' in html
    assert 'id="queueRerunButton"' in html
    assert 'id="promoteCandidateButton"' in html
    assert 'id="improvementNoteForm"' in html
    assert 'id="guardrailReminderList"' in html
    assert 'id="rerunQueueList"' in html
    assert 'id="promotionList"' in html
    assert "/improvements" in js
    assert "/improvements/notes" in js
    assert "/improvements/rerun-queue" in js
    assert "/improvements/promotions" in js
    assert "applyRegressionToImprove" in js
    assert ".improvement-panel" in css
    assert ".improvement-actions" in css
    assert ".compact-list" in css
    assert "https://" not in html + css + js
    assert "http://" not in html + css + js


def _response_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
