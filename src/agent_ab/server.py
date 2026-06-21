"""Local FastAPI backend for workbench discovery and trace inspection."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import Field

from agent_ab.config import ConfigLoadError, load_experiment, validate_taskpack_with_fixtures
from agent_ab.playground import list_playground_views, load_playground_view, run_playground_task
from agent_ab.schemas.common import StrictBaseModel
from agent_ab.schemas.playground import (
    PlaygroundRunRequest,
    PlaygroundRunResponse,
    PlaygroundView,
    PlaygroundViewListResponse,
)
from agent_ab.schemas.trace import TraceEnvelope, validate_trace_token
from agent_ab.trace_store import read_trace_jsonl

LOCAL_SERVER_HOSTS = {"127.0.0.1", "localhost", "::1"}
_UI_ROOT = Path(__file__).parent / "static" / "ui"
_UI_ASSETS = {
    "app.css": "text/css",
    "app.js": "application/javascript",
}


class HealthResponse(StrictBaseModel):
    status: str
    project_root: str


class ExperimentSummary(StrictBaseModel):
    path: str
    name: str | None = None
    valid: bool
    agents: list[str] = Field(default_factory=list)
    taskpack: str | None = None
    error: str | None = None


class ExperimentListResponse(StrictBaseModel):
    experiments: list[ExperimentSummary] = Field(default_factory=list)


class TaskSummary(StrictBaseModel):
    id: str
    query: str
    validators: list[str]


class TaskPackSummary(StrictBaseModel):
    path: str
    id: str | None = None
    version: int | None = None
    valid: bool
    task_count: int = 0
    tasks: list[TaskSummary] = Field(default_factory=list)
    error: str | None = None


class TaskPackListResponse(StrictBaseModel):
    taskpacks: list[TaskPackSummary] = Field(default_factory=list)


class ArtifactSummary(StrictBaseModel):
    name: str
    path: str
    exists: bool


class RunSummary(StrictBaseModel):
    run_id: str
    path: str
    artifacts: list[ArtifactSummary] = Field(default_factory=list)
    trace_count: int = 0
    trace_id: str | None = None
    taskpack_id: str | None = None
    task_id: str | None = None
    variant_id: str | None = None
    trace_error: str | None = None


class RunListResponse(StrictBaseModel):
    runs: list[RunSummary] = Field(default_factory=list)


class TraceListResponse(StrictBaseModel):
    run_id: str
    trace_path: str
    traces: list[TraceEnvelope] = Field(default_factory=list)


def is_local_server_host(host: str) -> bool:
    return host.strip().lower() in LOCAL_SERVER_HOSTS


def create_app(
    project_root: str | Path | None = None,
    runs_root: str | Path | None = None,
    playground_root: str | Path | None = None,
) -> FastAPI:
    """Create the local API app.

    The app only reads local config and artifact files. Network binding is
    controlled by the CLI, which restricts serving to localhost addresses.
    """

    root = Path(project_root or Path.cwd()).resolve()
    runs = Path(runs_root).resolve() if runs_root else (root / "runs").resolve()
    playground_views = (
        Path(playground_root).resolve()
        if playground_root
        else (root / "playground_views").resolve()
    )

    app = FastAPI(
        title="Local Agent A/B Workbench",
        version="0.1.0",
        description="Local-only API for workbench config, run, and trace discovery.",
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", project_root=str(root))

    @app.get("/", include_in_schema=False)
    def redirect_to_ui() -> RedirectResponse:
        return RedirectResponse(url="/ui")

    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/", include_in_schema=False)
    def frontend_shell() -> FileResponse:
        return FileResponse(_UI_ROOT / "index.html")

    @app.get("/ui/{asset_name}", include_in_schema=False)
    def frontend_asset(asset_name: str) -> FileResponse:
        media_type = _UI_ASSETS.get(asset_name)
        if media_type is None:
            raise HTTPException(status_code=404, detail=f"frontend asset not found: {asset_name}")
        return FileResponse(_UI_ROOT / asset_name, media_type=media_type)

    @app.get("/experiments", response_model=ExperimentListResponse)
    def list_experiments() -> ExperimentListResponse:
        return ExperimentListResponse(
            experiments=[
                _summarize_experiment(path, root)
                for path in _discover_yaml_files(root / "experiments")
            ]
        )

    @app.get("/taskpacks", response_model=TaskPackListResponse)
    def list_taskpacks() -> TaskPackListResponse:
        return TaskPackListResponse(
            taskpacks=[
                _summarize_taskpack(path, root)
                for path in _discover_taskpack_files(root / "taskpacks")
            ]
        )

    @app.get("/runs", response_model=RunListResponse)
    def list_runs() -> RunListResponse:
        if not runs.is_dir():
            return RunListResponse(runs=[])
        return RunListResponse(
            runs=[
                _summarize_run_dir(path, root)
                for path in sorted(runs.iterdir())
                if path.is_dir()
            ]
        )

    @app.get("/runs/{run_id}", response_model=RunSummary)
    def get_run(run_id: str) -> RunSummary:
        run_dir = _safe_run_dir(runs, run_id)
        if not run_dir.is_dir():
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        return _summarize_run_dir(run_dir, root)

    @app.get("/runs/{run_id}/trace", response_model=TraceListResponse)
    def get_run_trace(run_id: str) -> TraceListResponse:
        run_dir = _safe_run_dir(runs, run_id)
        trace_path = run_dir / "trace.jsonl"
        if not trace_path.is_file():
            raise HTTPException(status_code=404, detail=f"trace not found for run: {run_id}")
        try:
            traces = read_trace_jsonl(trace_path)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return TraceListResponse(
            run_id=run_id,
            trace_path=_path_for_response(trace_path, root),
            traces=traces,
        )

    @app.post("/playground/runs", response_model=PlaygroundRunResponse)
    def create_playground_run(request: PlaygroundRunRequest) -> PlaygroundRunResponse:
        try:
            return run_playground_task(
                request,
                project_root=root,
                run_root=runs,
                views_root=playground_views,
            )
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ConfigLoadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/playground/views", response_model=PlaygroundViewListResponse)
    def list_views() -> PlaygroundViewListResponse:
        try:
            return list_playground_views(playground_views)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/playground/views/{view_id}", response_model=PlaygroundView)
    def get_view(view_id: str) -> PlaygroundView:
        try:
            return load_playground_view(playground_views, view_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


def _discover_yaml_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
    )


def _discover_taskpack_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        {
            *directory.glob("**/tasks.yaml"),
            *directory.glob("**/tasks.yml"),
        }
    )


def _summarize_experiment(path: Path, project_root: Path) -> ExperimentSummary:
    try:
        experiment = load_experiment(path)
    except ConfigLoadError as exc:
        return ExperimentSummary(
            path=_path_for_response(path, project_root),
            valid=False,
            error=str(exc),
        )
    return ExperimentSummary(
        path=_path_for_response(path, project_root),
        name=experiment.name,
        valid=True,
        agents=sorted(experiment.agents),
        taskpack=experiment.taskpack,
    )


def _summarize_taskpack(path: Path, project_root: Path) -> TaskPackSummary:
    try:
        taskpack = validate_taskpack_with_fixtures(path)
    except ConfigLoadError as exc:
        return TaskPackSummary(
            path=_path_for_response(path, project_root),
            valid=False,
            error=str(exc),
        )
    return TaskPackSummary(
        path=_path_for_response(path, project_root),
        id=taskpack.id,
        version=taskpack.version,
        valid=True,
        task_count=len(taskpack.tasks),
        tasks=[
            TaskSummary(
                id=task.id,
                query=task.query,
                validators=[validator.type for validator in task.validators],
            )
            for task in taskpack.tasks
        ],
    )


def _summarize_run_dir(run_dir: Path, project_root: Path) -> RunSummary:
    trace_jsonl = run_dir / "trace.jsonl"
    trace_sqlite = run_dir / "trace.sqlite"
    workspace = run_dir / "workspace"
    artifacts = [
        ArtifactSummary(
            name="trace_jsonl",
            path=_path_for_response(trace_jsonl, project_root),
            exists=trace_jsonl.is_file(),
        ),
        ArtifactSummary(
            name="trace_sqlite",
            path=_path_for_response(trace_sqlite, project_root),
            exists=trace_sqlite.is_file(),
        ),
        ArtifactSummary(
            name="workspace",
            path=_path_for_response(workspace, project_root),
            exists=workspace.is_dir(),
        ),
    ]

    trace_count = 0
    trace: TraceEnvelope | None = None
    trace_error = None
    if trace_jsonl.is_file():
        try:
            traces = read_trace_jsonl(trace_jsonl)
        except ValueError as exc:
            trace_error = str(exc)
        else:
            trace_count = len(traces)
            trace = traces[0] if traces else None

    return RunSummary(
        run_id=run_dir.name,
        path=_path_for_response(run_dir, project_root),
        artifacts=artifacts,
        trace_count=trace_count,
        trace_id=trace.trace_id if trace else None,
        taskpack_id=trace.taskpack_id if trace else None,
        task_id=trace.task_id if trace else None,
        variant_id=trace.variant_id if trace else None,
        trace_error=trace_error,
    )


def _safe_run_dir(runs_root: Path, run_id: str) -> Path:
    try:
        safe_run_id = validate_trace_token(run_id, "run_id")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    root = runs_root.resolve()
    candidate = (root / safe_run_id).resolve()
    if candidate == root or root not in candidate.parents:
        raise HTTPException(status_code=400, detail=f"run_id escapes runs root: {run_id}")
    return candidate


def _path_for_response(path: Path, project_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_root).as_posix()
    except ValueError:
        return str(resolved)
