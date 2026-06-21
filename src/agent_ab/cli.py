"""CLI for Module 1 schema validation and inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from agent_ab.config import (
    ConfigLoadError,
    load_experiment,
    load_prompt_object,
    validate_experiment_with_prompts,
)
from agent_ab.schemas.metrics import AGENTEVAL_METRIC_REGISTRY, MetricCategory, metric_names

app = typer.Typer(help="Local offline A/B workbench CLI.")
console = Console()


@app.command("validate-experiment")
def validate_experiment_command(
    path: Annotated[Path, typer.Argument(help="Path to experiment YAML.")],
    include_prompts: Annotated[
        bool,
        typer.Option("--include-prompts/--no-include-prompts", help="Validate referenced PromptObjects too."),
    ] = True,
) -> None:
    """Validate an experiment YAML file."""

    try:
        if include_prompts:
            experiment, prompts = validate_experiment_with_prompts(path)
        else:
            experiment = load_experiment(path)
            prompts = {}
    except ConfigLoadError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] experiment={experiment.name}")
    console.print(f"variants: {', '.join(experiment.agents)}")
    if prompts:
        console.print(f"prompt objects: {', '.join(f'{k}:{v.id}@v{v.version}' for k, v in prompts.items())}")


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
