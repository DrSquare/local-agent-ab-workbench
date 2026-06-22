from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest

from agent_ab.runner import run_mock_task
from agent_ab.server import create_app

playwright_sync = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright is optional for browser-level UI tests.",
)
uvicorn = pytest.importorskip("uvicorn", reason="uvicorn is required for browser-level UI tests.")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKPACK = PROJECT_ROOT / "taskpacks" / "desktop_basics" / "tasks.yaml"


@pytest.fixture()
def live_ui_server(tmp_path: Path) -> Iterator[str]:
    runs_root = tmp_path / "runs"
    run_mock_task(
        TASKPACK,
        "rename_todo",
        runs_root,
        run_id="mock.rename_todo.browser",
        variant_id="A",
    )
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(PROJECT_ROOT, runs_root=runs_root, playground_root=tmp_path / "views"),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_health(base_url)
    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_browser_ui_loads_inventory_and_trace(live_ui_server: str) -> None:
    with playwright_sync.sync_playwright() as playwright:
        browser = _launch_browser_or_skip(playwright)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(f"{live_ui_server}/ui")
            page.wait_for_selector("#apiDot.is-ok", timeout=5000)

            assert int(page.locator("#experimentCount").inner_text()) >= 2
            assert page.locator("#runCount").inner_text() == "1"

            page.click('[data-view="evaluate"]')
            page.click("tr.run-row")
            page.wait_for_selector(".span-node", timeout=5000)

            assert page.locator("#selectedRunLabel").inner_text() == "mock.rename_todo.browser"
            assert page.locator(".timeline-row").count() >= 1
            assert "validator" in page.locator("#traceKindFilter").inner_text()
        finally:
            browser.close()


def test_browser_playground_replay_roundtrip(live_ui_server: str) -> None:
    with playwright_sync.sync_playwright() as playwright:
        browser = _launch_browser_or_skip(playwright)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(f"{live_ui_server}/ui")
            page.wait_for_selector("#apiDot.is-ok", timeout=5000)

            page.click('[data-view="improve"]')
            page.fill("#pgRunId", "playground.rename_todo.browser")
            page.click('[data-action="replay"]')
            page.wait_for_function(
                "document.querySelector('#playgroundStatus').textContent.includes('passed:')",
                timeout=5000,
            )

            assert "playground.rename_todo.browser" in page.locator("#playgroundResult").inner_text()
            assert page.locator("#selectedRunLabel").inner_text() == "playground.rename_todo.browser"
            assert page.locator("#runCount").inner_text() == "2"
        finally:
            browser.close()


def _launch_browser_or_skip(playwright):
    try:
        return playwright.chromium.launch()
    except playwright_sync.Error as exc:
        pytest.skip(f"Playwright Chromium browser is not installed: {exc}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(base_url: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=0.2) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.05)
    raise RuntimeError(f"server did not become healthy: {base_url}")
