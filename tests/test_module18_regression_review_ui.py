from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_ab.eval_runner import build_eval_run_plan, write_eval_run_plan
from agent_ab.observability import (
    TriageNoteRequest,
    build_observability_read_model,
    load_triage_notes,
    save_triage_note,
)
from agent_ab.schemas.eval import EvalLog
from agent_ab.schemas.sandbox import (
    SandboxDecision,
    SandboxEvent,
    SandboxEventType,
    SandboxPolicyArea,
    sandbox_events_metadata,
)
from agent_ab.server import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_triage_note_request_rejects_unknown_keys_blank_body_and_duplicate_tags() -> None:
    valid_payload = {
        "eval_task_id": "desktop_basics_eval",
        "sample_id": "rename_todo",
        "eval_run_id": "eval.module18.note",
        "eval_log_path": "runs/evals/eval_log.json",
        "body": "Review the regression before rerun.",
        "tags": ["sandbox", "prompt"],
    }

    TriageNoteRequest.model_validate(valid_payload)

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        TriageNoteRequest.model_validate({**valid_payload, "unexpected": True})

    with pytest.raises(ValueError, match="triage note field"):
        TriageNoteRequest.model_validate({**valid_payload, "body": " "})

    with pytest.raises(ValueError, match="duplicate"):
        TriageNoteRequest.model_validate({**valid_payload, "tags": ["sandbox", "sandbox"]})


def test_regression_review_read_model_supports_run_variant_notes_and_exports(tmp_path: Path) -> None:
    plan_path, repeated_current, _variant_current = _write_module18_plan_and_logs(tmp_path)
    notes_path = tmp_path / "runs" / "triage_notes.json"
    save_triage_note(
        notes_path,
        TriageNoteRequest(
            eval_task_id=repeated_current.eval_task_id,
            sample_id=repeated_current.sample_id,
            eval_run_id=repeated_current.eval_run_id,
            eval_log_path=str(repeated_current.eval_log_path),
            trace_id="trace.eval.module18.repeat.current",
            failure_taxonomy="sandbox_denial",
            body="Blocked shell command needs a safer fixture setup.",
            status="watching",
            tags=["sandbox", "fixture"],
        ),
        now_ms=1000,
    )

    read_model = build_observability_read_model(
        plan_path,
        project_root=tmp_path,
        triage_notes=load_triage_notes(notes_path),
    )

    assert read_model.dashboard.regression_count == 2
    assert read_model.dashboard.triage_note_count == 1
    assert "sandbox_denial" in read_model.regression_review.failure_taxonomy_options
    assert "failed" in read_model.regression_review.status_options
    assert "error" in read_model.regression_review.status_options

    repeated_row = next(row for row in read_model.regression_review.rows if row.comparison_kind == "repeated_run")
    assert repeated_row.previous_status == "passed"
    assert repeated_row.current_status == "error"
    assert repeated_row.failure_taxonomy == "sandbox_denial"
    assert repeated_row.sandbox_denial_count == 1
    assert repeated_row.latest_triage_note is not None
    assert repeated_row.latest_triage_note.status == "watching"
    assert repeated_row.latest_triage_note.tags == ["sandbox", "fixture"]

    variant_row = next(row for row in read_model.regression_review.rows if row.comparison_kind == "variant")
    assert variant_row.previous_variant_id == "baseline"
    assert variant_row.variant_id == "candidate"
    assert variant_row.previous_score == pytest.approx(0.9)
    assert variant_row.current_score == pytest.approx(0.3)
    assert variant_row.delta == pytest.approx(-0.6)
    assert variant_row.failure_taxonomy == "scorer_failure"

    export_links = read_model.regression_review.export_links
    assert {link.kind for link in export_links} == {"eval_logs", "eval_aggregates", "eval_findings"}
    assert {link.format for link in export_links} == {"json", "csv"}
    assert all(link.url.startswith("/observability/export?") for link in export_links)


def test_regression_review_api_persists_triage_notes_and_exports_reports(tmp_path: Path) -> None:
    plan_path, _repeated_current, _variant_current = _write_module18_plan_and_logs(tmp_path)
    plan_rel = plan_path.relative_to(tmp_path).as_posix()
    client = TestClient(create_app(tmp_path, runs_root=tmp_path / "runs"))

    before_response = client.get("/observability", params={"plan_path": plan_rel})
    assert before_response.status_code == 200
    repeated_row = next(
        row
        for row in before_response.json()["regression_review"]["rows"]
        if row["comparison_kind"] == "repeated_run"
    )
    assert repeated_row["latest_triage_note"] is None

    note_response = client.post(
        "/triage-notes",
        json={
            "eval_task_id": repeated_row["eval_task_id"],
            "sample_id": repeated_row["sample_id"],
            "eval_run_id": repeated_row["current_eval_run_id"],
            "eval_log_path": repeated_row["current_eval_log_path"],
            "trace_id": repeated_row["trace_id"],
            "failure_taxonomy": repeated_row["failure_taxonomy"],
            "body": "Investigate the sandbox denial before rerun.",
            "status": "open",
            "tags": ["sandbox"],
        },
    )
    assert note_response.status_code == 200
    assert note_response.json()["id"] == "triage.1"

    after_response = client.get("/observability", params={"plan_path": plan_rel})
    assert after_response.status_code == 200
    after_body = after_response.json()
    assert after_body["dashboard"]["triage_note_count"] == 1
    repeated_after = next(
        row
        for row in after_body["regression_review"]["rows"]
        if row["comparison_kind"] == "repeated_run"
    )
    assert repeated_after["latest_triage_note"]["body"] == "Investigate the sandbox denial before rerun."

    notes_response = client.get("/triage-notes")
    assert notes_response.status_code == 200
    assert len(notes_response.json()["notes"]) == 1

    json_export = client.get(
        "/observability/export",
        params={"plan_path": plan_rel, "kind": "eval_logs", "format": "json"},
    )
    assert json_export.status_code == 200
    assert len(json_export.json()["eval_logs"]) == 4

    csv_export = client.get(
        "/observability/export",
        params={"plan_path": plan_rel, "kind": "eval_findings", "format": "csv"},
    )
    assert csv_export.status_code == 200
    assert "sandbox_denial" in csv_export.text


def test_module18_ui_assets_expose_regression_review_controls(tmp_path: Path) -> None:
    client = TestClient(create_app(PROJECT_ROOT, runs_root=tmp_path / "runs"))

    html = client.get("/ui").text
    css = client.get("/ui/app.css").text
    js = client.get("/ui/app.js").text

    assert 'id="regressionTaxonomyFilter"' in html
    assert 'id="regressionStatusFilter"' in html
    assert 'id="triageStatusFilter"' in html
    assert 'id="regressionReviewRows"' in html
    assert 'id="triageForm"' in html
    assert 'id="exportLinks"' in html
    assert "renderRegressionReview" in js
    assert "renderExportLinks" in js
    assert "saveTriageNote" in js
    assert "/triage-notes" in js
    assert ".review-tools" in css
    assert ".review-layout" in css
    assert ".triage-form" in css
    assert ".export-link" in css
    assert ".regression-review-row" in css
    assert "https://" not in html + css + js
    assert "http://" not in html + css + js


def _write_module18_plan_and_logs(tmp_path: Path):
    base_plan = build_eval_run_plan(
        PROJECT_ROOT / "evals" / "local_eval_set.yaml",
        tmp_path / "eval_runs",
    )
    repeat_previous = base_plan.sample_runs[0].model_copy(
        update={
            "variant_id": "baseline",
            "eval_run_id": "eval.module18.repeat.previous",
            "eval_log_path": str(tmp_path / "eval_runs" / "repeat_previous" / "eval_log.json"),
        }
    )
    repeat_current = base_plan.sample_runs[0].model_copy(
        update={
            "variant_id": "baseline",
            "eval_run_id": "eval.module18.repeat.current",
            "eval_log_path": str(tmp_path / "eval_runs" / "repeat_current" / "eval_log.json"),
        }
    )
    variant_previous = base_plan.sample_runs[1].model_copy(
        update={
            "variant_id": "baseline",
            "eval_run_id": "eval.module18.variant.baseline",
            "eval_log_path": str(tmp_path / "eval_runs" / "variant_baseline" / "eval_log.json"),
        }
    )
    variant_current = base_plan.sample_runs[1].model_copy(
        update={
            "variant_id": "candidate",
            "eval_run_id": "eval.module18.variant.candidate",
            "eval_log_path": str(tmp_path / "eval_runs" / "variant_candidate" / "eval_log.json"),
        }
    )
    plan = base_plan.model_copy(
        update={
            "total_samples": 4,
            "planned_count": 4,
            "skipped_completed_count": 0,
            "sample_runs": [repeat_previous, repeat_current, variant_previous, variant_current],
        }
    )
    plan_path = write_eval_run_plan(plan, tmp_path / "runs" / "evals" / "module18_plan.json")
    _write_eval_log(
        Path(repeat_previous.eval_log_path),
        _eval_log(
            repeat_previous,
            status="passed",
            score=1.0,
            started_at_ms=10,
            trace_id="trace.eval.module18.repeat.previous",
        ),
    )
    denial = SandboxEvent(
        id="sandbox_denial_module18",
        event_type=SandboxEventType.TOOL_DENIAL,
        decision=SandboxDecision.DENIED,
        provider_id="local_workspace_default",
        tool_name="shell",
        policy_area=SandboxPolicyArea.COMMAND,
        reason="command is blocked by policy: curl",
        command=["curl", "example.invalid"],
    )
    _write_eval_log(
        Path(repeat_current.eval_log_path),
        EvalLog(
            eval_task_id=repeat_current.eval_task_id,
            eval_run_id=repeat_current.eval_run_id,
            sample_id=repeat_current.sample_id,
            taskpack_id=repeat_current.taskpack_id,
            task_id=repeat_current.task_id,
            solver_id=repeat_current.solver_id,
            variant_id=repeat_current.variant_id,
            status="error",
            started_at_ms=30,
            ended_at_ms=38,
            errors=[{"code": "sandbox_denial", "message": "Sandbox denied command."}],
            trace={
                "trace_id": "trace.eval.module18.repeat.current",
                "run_id": repeat_current.eval_run_id,
                "path": "trace.repeat.current.jsonl",
            },
            metadata=sandbox_events_metadata([denial]),
        ),
    )
    _write_eval_log(
        Path(variant_previous.eval_log_path),
        _eval_log(
            variant_previous,
            status="passed",
            score=0.9,
            started_at_ms=50,
            trace_id="trace.eval.module18.variant.baseline",
        ),
    )
    _write_eval_log(
        Path(variant_current.eval_log_path),
        _eval_log(
            variant_current,
            status="failed",
            score=0.3,
            started_at_ms=60,
            trace_id="trace.eval.module18.variant.candidate",
            passed=False,
        ),
    )
    return plan_path, repeat_current, variant_current


def _eval_log(sample_run, *, status: str, score: float, started_at_ms: int, trace_id: str, passed: bool = True) -> EvalLog:
    return EvalLog(
        eval_task_id=sample_run.eval_task_id,
        eval_run_id=sample_run.eval_run_id,
        sample_id=sample_run.sample_id,
        taskpack_id=sample_run.taskpack_id,
        task_id=sample_run.task_id,
        solver_id=sample_run.solver_id,
        variant_id=sample_run.variant_id,
        status=status,
        started_at_ms=started_at_ms,
        ended_at_ms=started_at_ms + 8,
        scorer_results=[
            {
                "scorer_id": "task_success",
                "type": "metric",
                "name": "task_success",
                "passed": passed,
                "score": score,
                "message": "Task failed validation." if not passed else None,
            }
        ],
        trace={
            "trace_id": trace_id,
            "run_id": sample_run.eval_run_id,
            "path": f"{trace_id}.jsonl",
        },
    )


def _write_eval_log(path: Path, log: EvalLog) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log.model_dump(mode="json"), indent=2), encoding="utf-8")
