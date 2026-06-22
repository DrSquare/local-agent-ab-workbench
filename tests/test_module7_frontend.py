from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_ab.server import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_frontend_shell_serves_local_assets(tmp_path: Path) -> None:
    client = TestClient(create_app(PROJECT_ROOT, runs_root=tmp_path / "runs"))

    html = client.get("/ui")
    css = client.get("/ui/app.css")
    js = client.get("/ui/app.js")

    assert html.status_code == 200
    assert css.status_code == 200
    assert js.status_code == 200
    assert "Workbench dashboard" in html.text
    assert "Run replay" in html.text
    assert "/experiments" in js.text
    assert "/runs" in js.text
    assert "/observability" in js.text
    assert "/playground/runs" in js.text
    assert "/playground/views" in js.text
    assert "https://" not in html.text + css.text + js.text
    assert "http://" not in html.text + css.text + js.text


def test_frontend_shell_root_redirects_to_ui(tmp_path: Path) -> None:
    client = TestClient(create_app(PROJECT_ROOT, runs_root=tmp_path / "runs"))

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/ui"


def test_frontend_shell_rejects_unknown_assets(tmp_path: Path) -> None:
    client = TestClient(create_app(PROJECT_ROOT, runs_root=tmp_path / "runs"))

    response = client.get("/ui/missing.js")

    assert response.status_code == 404
    assert "frontend asset not found" in response.json()["detail"]
