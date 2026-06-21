"""CLI for local schema validation and inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from agent_ab.adapters.openclaw import prepare_openclaw_run
from agent_ab.config import (
    ConfigLoadError,
    load_prompt_object,
    validate_experiment_bundle,
    validate_taskpack_with_fixtures,
)
from agent_ab.reporting import ReportFormat, export_run_report, run_local_demo
from agent_ab.runner import run_mock_task
from agent_ab.schemas.metrics import AGENTEVAL_METRIC_REGISTRY, MetricCategory, metric_names

app = typer.Typer(help="Local offline A/B workbench CLI.")
console = Console()
_LOCAL_SERVER_HOSTS = {"127.0.0.1", "localhost", "::1"}


@app.command("validate-experiment")
def validate_experiment_command(
    path: Annotated[Path, typer.Argument(help="Path to experiment YAML.")],
    include_prompts: Annotated[
        bool,
        typer.Option("--include-prompts/--no-include-prompts", help="Validate referenced PromptObjects too."),
    ] = True,
    include_taskpack: Annotated[
        bool,
        typer.Option("--include-taskpack/--no-include-taskpack", help="Validate the referenced TaskPack too."),
    ] = True,
) -> None:
    """Validate an experiment YAML file."""

    try:
        experiment, prompts, taskpack = validate_experiment_bundle(
            path,
            include_prompts=include_prompts,
            include_taskpack=include_taskpack,
        )
    except ConfigLoadError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] experiment={experiment.name}")
    console.print(f"variants: {', '.join(experiment.agents)}")
    if prompts:
        console.print(f"prompt objects: {', '.join(f'{k}:{v.id}@v{v.version}' for k, v in prompts.items())}")
    if taskpack:
        console.print(f"taskpack: {taskpack.id}@v{taskpack.version} ({len(taskpack.tasks)} tasks)")


@app.command("validate-prompt")
def validate_prompt_command(
    path: Annotated[Path, typer.Argument(help="Path to PromptObject YAML.")],
) -> None:
    """Validate a PromptObject YAML file."""

    try:
        prompt = load_prompt_object(path)
    except ConfigLoadError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] prompt={prompt.id}@v{prompt.version}")
    console.print(f"model: {prompt.model.provider}/{prompt.model.name}")
    console.print(f"variables: {', '.join(prompt.variables) or '(none)'}")
    console.print(f"enabled tools: {', '.join(prompt.enabled_tool_names()) or '(none)'}")


@app.command("validate-taskpack")
def validate_taskpack_command(
    path: Annotated[Path, typer.Argument(help="Path to TaskPack YAML.")],
) -> None:
    """Validate a TaskPack YAML file."""

    try:
        taskpack = validate_taskpack_with_fixtures(path)
    except ConfigLoadError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] taskpack={taskpack.id}@v{taskpack.version}")
    console.print(f"tasks: {len(taskpack.tasks)}")
    console.print(f"task ids: {', '.join(task.id for task in taskpack.tasks)}")


@app.command("run-mock-task")
def run_mock_task_command(
    taskpack: Annotated[Path, typer.Argument(help="Path to TaskPack YAML.")],
    task_id: Annotated[str, typer.Argument(help="Task ID to run.")],
    run_root: Annotated[Path, typer.Option(help="Directory for local run artifacts.")] = Path("runs/mock"),
    run_id: Annotated[str | None, typer.Option(help="Optional deterministic run ID.")] = None,
) -> None:
    """Run one task with the deterministic mock adapter."""

    try:
        result = run_mock_task(taskpack, task_id, run_root, run_id=run_id)
    except (ConfigLoadError, FileExistsError, ValueError) as exc:
        console.print(f"[red]Run failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] run={result.run_id} status={result.status}")
    console.print(f"workspace: {result.workspace_path}")
    console.print(f"trace: {result.trace_id}")
    for name, path in result.artifacts.items():
        console.print(f"{name}: {path}")


@app.command("prepare-openclaw-run")
def prepare_openclaw_run_command(
    experiment: Annotated[Path, typer.Argument(help="Path to experiment YAML.")],
    variant_id: Annotated[str, typer.Argument(help="OpenClaw variant ID to prepare.")],
    task_id: Annotated[str, typer.Argument(help="Task ID to prepare.")],
    run_root: Annotated[Path, typer.Option(help="Directory for local run artifacts.")] = Path("runs/openclaw"),
    run_id: Annotated[str | None, typer.Option(help="Optional deterministic run ID.")] = None,
) -> None:
    """Prepare an OpenClaw CLI run package without executing the agent."""

    try:
        prepared = prepare_openclaw_run(
            experiment,
            variant_id,
            task_id,
            run_root,
            run_id=run_id,
        )
    except (ConfigLoadError, FileExistsError, ValueError) as exc:
        console.print(f"[red]Prepare failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] run={prepared.run_id}")
    console.print(f"workspace: {prepared.workspace_path}")
    console.print(f"config: {prepared.config_path}")
    console.print(f"working_directory: {prepared.command_plan.working_directory}")
    console.print("command: " + " ".join(prepared.command_plan.command))


@app.command("export-runs")
def export_runs_command(
    runs_root: Annotated[Path, typer.Argument(help="Run artifact root to summarize.")],
    output: Annotated[Path, typer.Option(help="Output report path.")] = Path("reports/runs.json"),
    report_format: Annotated[ReportFormat, typer.Option("--format", help="Report format.")] = ReportFormat.JSON,
) -> None:
    """Export local run summaries to JSON or CSV."""

    if output == Path("reports/runs.json") and report_format == ReportFormat.CSV:
        output = Path("reports/runs.csv")
    report_path = export_run_report(runs_root, output, report_format)
    console.print(f"[green]OK[/green] report={report_path}")


@app.command("run-demo")
def run_demo_command(
    output_root: Annotated[Path, typer.Option(help="Output root for demo runs and reports.")] = Path("demo_output"),
    project_root: Annotated[Path, typer.Option(help="Project root containing demo taskpacks.")] = Path("."),
) -> None:
    """Run the deterministic local demo and export reports."""

    try:
        summary = run_local_demo(project_root, output_root)
    except (ConfigLoadError, FileExistsError, ValueError) as exc:
        console.print(f"[red]Demo failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] run={summary.run_id}")
    console.print(f"runs: {summary.runs_root}")
    console.print(f"json_report: {summary.json_report}")
    console.print(f"csv_report: {summary.csv_report}")


@app.command("serve")
def serve_command(
    host: Annotated[str, typer.Option(help="Local bind host.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535, help="Local bind port.")] = 8765,
    project_root: Annotated[Path, typer.Option(help="Project root for config discovery.")] = Path("."),
    runs_root: Annotated[
        Path | None,
        typer.Option(help="Run artifact root. Defaults to <project-root>/runs."),
    ] = None,
) -> None:
    """Serve the local read-only workbench API."""

    if host.strip().lower() not in _LOCAL_SERVER_HOSTS:
        console.print("[red]Serve failed:[/red] host must be localhost, 127.0.0.1, or ::1")
        raise typer.Exit(code=1)

    try:
        import uvicorn

        from agent_ab.server import create_app
    except ImportError as exc:
        console.print(
            "[red]Serve failed:[/red] install server dependencies with "
            "python -m pip install -e '.[server]'"
        )
        raise typer.Exit(code=1) from exc

    uvicorn.run(
        create_app(project_root=project_root, runs_root=runs_root),
        host=host,
        port=port,
    )


@app.command("metrics")
def metrics_command(
    category: Annotated[MetricCategory | None, typer.Option(help="Optional metric category filter.")] = None,
) -> None:
    """List built-in AgentEval-inspired metrics."""

    table = Table(title="Built-in metric registry")
    table.add_column("Name", style="cyan", overflow="fold")
    table.add_column("Category", overflow="fold")
    table.add_column("Direction", overflow="fold")
    table.add_column("Default", overflow="fold")
    table.add_column("Source", overflow="fold")
    table.add_column("Description", overflow="fold")

    for name in metric_names():
        metric = AGENTEVAL_METRIC_REGISTRY[name]
        if category and metric.category != category:
            continue
        table.add_row(
            metric.name,
            str(metric.category),
            str(metric.direction),
            "yes" if metric.enabled_by_default else "no",
            str(metric.source),
            metric.description,
        )
    console.print(table)


@app.command("render-prompt")
def render_prompt_command(
    path: Annotated[Path, typer.Argument(help="Path to PromptObject YAML.")],
    var: Annotated[
        list[str] | None,
        typer.Option("--var", help="Template variable as key=value. May be repeated."),
    ] = None,
) -> None:
    """Render prompt messages using key=value variables."""

    try:
        prompt = load_prompt_object(path)
    except ConfigLoadError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    variables: dict[str, str] = {}
    for item in var or []:
        if "=" not in item:
            console.print(f"[red]Invalid --var value:[/red] {item}. Expected key=value.")
            raise typer.Exit(code=1)
        key, value = item.split("=", 1)
        variables[key] = value

    try:
        messages = prompt.render_messages(variables)
    except ValueError as exc:
        console.print(f"[red]Render failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    for message in messages:
        console.rule(f"{message.role}")
        console.print(message.content)


if __name__ == "__main__":
    app()
