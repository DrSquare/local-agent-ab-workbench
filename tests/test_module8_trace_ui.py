from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_ab.runner import run_mock_task
from agent_ab.server import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKPACK = PROJECT_ROOT / "taskpacks" / "desktop_basics" / "tasks.yaml"


def test_trace_visualizer_ui_assets_include_module8_controls(tmp_path: Path) -> None:
    client = TestClient(create_app(PROJECT_ROOT, runs_root=tmp_path / "runs"))

    html = client.get("/ui").text
    css = client.get("/ui/app.css").text
    js = client.get("/ui/app.js").text

    assert 'id="traceKindFilter"' in html
    assert 'id="traceStatusFilter"' in html
    assert "Timing waterfall" in html
    assert "renderSpanDetail" in js
    assert "filterSpansWithAncestors" in js
    assert "renderTimeline" in js
    assert "aria-selected" in js
    assert ".timeline-row" in css
    assert ".span-node.is-selected" in css
    assert "font-size: clamp" not in css
    assert "letter-spacing: 0;" in css


def test_trace_visualizer_can_fetch_mock_trace_payload(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    result = run_mock_task(
        TASKPACK,
        "rename_todo",
        runs_root,
        run_id="mock.rename_todo.trace_ui",
    )
    client = TestClient(create_app(PROJECT_ROOT, runs_root=runs_root))

    trace = client.get(f"/runs/{result.run_id}/trace")

    assert trace.status_code == 200
    spans = trace.json()["traces"][0]["spans"]
    span_kinds = {span["kind"] for span in spans}
    assert {"task_run", "setup", "tool", "validator", "scoring"} <= span_kinds
    assert any(span["validator"] for span in spans if span["kind"] == "validator")
