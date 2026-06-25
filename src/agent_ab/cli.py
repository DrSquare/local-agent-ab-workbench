"""CLI for local schema validation and inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from agent_ab.adapters.openclaw import prepare_openclaw_run
from agent_ab.analysis import (
    export_eval_aggregate_report,
    export_eval_log_report,
    export_eval_scan_report,
)
from agent_ab.config import (
    ConfigLoadError,
    load_prompt_object,
    validate_eval_set_with_tasks,
    validate_eval_task_with_taskpack,
    validate_experiment_bundle,
    validate_offline_docker_ab_run_plan,
    validate_offline_model_provider,
    validate_sandbox_provider,
    validate_taskpack_with_fixtures,
)
from agent_ab.eval_execution import execute_eval_run_plan
from agent_ab.eval_runner import build_eval_run_plan, write_eval_run_plan
from agent_ab.reporting import (
    ReportFormat,
    export_run_report,
    export_variant_comparison_report,
    run_local_demo,
)
from agent_ab.runner import run_mock_task
from agent_ab.schemas.metrics import AGENTEVAL_METRIC_REGISTRY, MetricCategory, metric_names
from agent_ab.task_seed_generation import (
    SeedTaskGenerationConfig,
    mercor_apex_public_seeds,
    write_seed_taskpack,
)

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


@app.command("validate-eval-task")
def validate_eval_task_command(
    path: Annotated[Path, typer.Argument(help="Path to EvalTask YAML.")],
) -> None:
    """Validate an EvalTask YAML file and referenced TaskPack samples."""

    try:
        eval_task, taskpack, samples = validate_eval_task_with_taskpack(path)
    except ConfigLoadError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] eval_task={eval_task.id}@v{eval_task.version}")
    console.print(f"taskpack: {taskpack.id}@v{taskpack.version}")
    console.print(f"samples: {len(samples)} ({', '.join(sample.id for sample in samples)})")
    console.print(f"solver: {eval_task.solver.id}/{eval_task.solver.adapter}")
    console.print(f"scorers: {', '.join(scorer.id for scorer in eval_task.scorers)}")


@app.command("validate-eval-set")
def validate_eval_set_command(
    path: Annotated[Path, typer.Argument(help="Path to EvalSet YAML.")],
) -> None:
    """Validate an EvalSet YAML file and every referenced EvalTask."""

    try:
        eval_set, resolved = validate_eval_set_with_tasks(path)
    except ConfigLoadError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    sample_count = sum(len(samples) for _, _, _, samples in resolved)
    console.print(f"[green]OK[/green] eval_set={eval_set.id}@v{eval_set.version}")
    console.print(f"eval tasks: {len(resolved)}")
    console.print(f"samples: {sample_count}")
    console.print(f"task refs: {', '.join(ref_id for ref_id, _, _, _ in resolved)}")


@app.command("validate-sandbox-provider")
def validate_sandbox_provider_command(
    path: Annotated[Path, typer.Argument(help="Path to SandboxProvider YAML.")],
) -> None:
    """Validate a sandbox provider policy without executing it."""

    try:
        provider = validate_sandbox_provider(path)
    except ConfigLoadError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] sandbox_provider={provider.id}@v{provider.version}")
    console.print(f"kind: {provider.kind}")
    console.print(f"allowed paths: {', '.join(provider.workspace.allowed_paths)}")
    console.print(f"network: {'allowed' if provider.network.allow_network else 'local-only'}")
    console.print(f"max seconds: {provider.timeout.max_seconds_per_task}")


@app.command("validate-offline-model-provider")
def validate_offline_model_provider_command(
    path: Annotated[Path, typer.Argument(help="Path to offline model provider YAML.")],
) -> None:
    """Validate an offline local model provider contract without network probes."""

    try:
        provider = validate_offline_model_provider(path)
    except ConfigLoadError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] offline_model_provider={provider.id}@v{provider.version}")
    console.print(f"kind: {provider.kind}")
    console.print(f"endpoint: {provider.endpoint or '(none)'}")
    console.print(f"models: {', '.join(model.id for model in provider.models)}")
    console.print(f"default_model: {provider.default_model}")


@app.command("validate-offline-ab-plan")
def validate_offline_ab_plan_command(
    path: Annotated[Path, typer.Argument(help="Path to offline Docker A/B run-plan YAML.")],
) -> None:
    """Validate an offline Docker A/B run plan without launching containers."""

    try:
        plan = validate_offline_docker_ab_run_plan(path)
    except ConfigLoadError as exc:
        console.print(f"[red]Validation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] offline_ab_plan={plan.id}@v{plan.version}")
    console.print(f"model providers: {', '.join(provider.id for provider in plan.model_providers)}")
    console.print(f"variants: {', '.join(variant.id for variant in plan.variants)}")
    console.print(f"network: {plan.network.mode}")
    console.print(f"external network: {'allowed' if plan.network.allow_external_network else 'blocked'}")


@app.command("plan-eval-set")
def plan_eval_set_command(
    path: Annotated[Path, typer.Argument(help="Path to EvalSet YAML.")],
    run_root: Annotated[Path, typer.Option(help="Directory for planned EvalLog artifacts.")] = Path("runs/evals"),
    output: Annotated[
        Path | None,
        typer.Option(help="Optional JSON output path for the EvalRunPlan artifact."),
    ] = None,
) -> None:
    """Build a non-executing EvalSet run plan."""

    try:
        plan = build_eval_run_plan(path, run_root)
    except (ConfigLoadError, ValueError) as exc:
        console.print(f"[red]Plan failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] eval_set={plan.eval_set_id}@v{plan.eval_set_version}")
    console.print(f"run_root: {plan.run_root}")
    console.print(f"samples: {plan.total_samples}")
    console.print(f"planned: {plan.planned_count}")
    console.print(f"skipped_completed: {plan.skipped_completed_count}")
    if output is not None:
        plan_path = write_eval_run_plan(plan, output)
        console.print(f"plan: {plan_path}")


@app.command("run-eval-plan")
def run_eval_plan_command(
    plan: Annotated[Path, typer.Argument(help="Path to EvalRunPlan JSON.")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--execute", help="Preview guarded work or execute allowed mock rows."),
    ] = True,
    eval_task_id: Annotated[
        list[str] | None,
        typer.Option("--eval-task-id", help="Limit execution to EvalTask ID. May be repeated."),
    ] = None,
    sample_id: Annotated[
        list[str] | None,
        typer.Option("--sample-id", help="Limit execution to sample ID. May be repeated."),
    ] = None,
    solver_id: Annotated[
        list[str] | None,
        typer.Option("--solver-id", help="Limit execution to solver ID. May be repeated."),
    ] = None,
    variant_id: Annotated[
        list[str] | None,
        typer.Option("--variant-id", help="Limit execution to variant ID. May be repeated."),
    ] = None,
    max_failures: Annotated[
        int | None,
        typer.Option(help="Override the EvalRunPlan max failure stop threshold.", min=0),
    ] = None,
    resume: Annotated[
        bool,
        typer.Option("--resume/--no-resume", help="Skip selected rows that already have a valid EvalLog."),
    ] = True,
) -> None:
    """Run selected EvalRunPlan samples through the guarded execution harness."""

    try:
        summary = execute_eval_run_plan(
            plan,
            dry_run=dry_run,
            eval_task_ids=eval_task_id,
            sample_ids=sample_id,
            solver_ids=solver_id,
            variant_ids=variant_id,
            max_failures=max_failures,
            resume=resume,
        )
    except (ConfigLoadError, OSError, ValueError) as exc:
        console.print(f"[red]Eval execution failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    mode = "dry-run" if summary.dry_run else "execute"
    console.print(f"[green]OK[/green] eval_plan={summary.plan_path} mode={mode}")
    console.print(f"selected: {summary.selected_count}")
    console.print(f"dry_run: {summary.dry_run_count}")
    console.print(f"executed: {summary.executed_count}")
    console.print(f"skipped_completed: {summary.skipped_count}")
    console.print(f"blocked: {summary.blocked_count}")
    console.print(f"errors: {summary.error_count}")
    console.print(f"stopped: {summary.stopped_count}")
    for row in summary.rows:
        row_status = row.status.value if hasattr(row.status, "value") else str(row.status)
        console.print(
            f"{row_status}: {row.eval_run_id} adapter={row.adapter} "
            f"log={row.eval_log_path}"
        )
        if row.reason:
            console.print(f"  reason: {row.reason}")


@app.command("generate-seed-taskpack")
def generate_seed_taskpack_command(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output TaskPack YAML path."),
    ] = Path("taskpacks/mercor_apex_expert_seeded/tasks.yaml"),
    taskpack_id: Annotated[
        str,
        typer.Option(help="Generated TaskPack ID."),
    ] = "mercor_apex_expert_seeded",
    workspace_fixture: Annotated[
        str,
        typer.Option(help="Relative workspace fixture path inside the TaskPack directory."),
    ] = "workspaces/expert_seed",
    variants_per_seed: Annotated[
        int,
        typer.Option(min=1, max=5, help="Deterministic variants to generate per built-in seed."),
    ] = 1,
) -> None:
    """Generate a Mercor APEX/O*NET expert-seeded TaskPack without network access."""

    try:
        config = SeedTaskGenerationConfig(
            taskpack_id=taskpack_id,
            workspace_fixture=workspace_fixture,
            variants_per_seed=variants_per_seed,
            seeds=mercor_apex_public_seeds(),
        )
        taskpack = write_seed_taskpack(output, config)
        validate_taskpack_with_fixtures(output)
    except (ConfigLoadError, OSError, ValidationError, ValueError) as exc:
        console.print(f"[red]Seed generation failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]OK[/green] taskpack={taskpack.id}@v{taskpack.version}")
    console.print(f"output: {output}")
    console.print(f"tasks: {len(taskpack.tasks)}")
    console.print(f"workspace fixture: {workspace_fixture}")


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


@app.command("compare-runs")
def compare_runs_command(
    runs_root: Annotated[Path, typer.Argument(help="Run artifact root to aggregate by task and variant.")],
    output: Annotated[Path, typer.Option(help="Output comparison report path.")] = Path("reports/comparison.json"),
    report_format: Annotated[ReportFormat, typer.Option("--format", help="Report format.")] = ReportFormat.JSON,
) -> None:
    """Export aggregate task/variant comparison summaries to JSON or CSV."""

    if output == Path("reports/comparison.json") and report_format == ReportFormat.CSV:
        output = Path("reports/comparison.csv")
    report_path = export_variant_comparison_report(runs_root, output, report_format)
    console.print(f"[green]OK[/green] comparison={report_path}")


@app.command("export-eval-logs")
def export_eval_logs_command(
    plan: Annotated[Path, typer.Argument(help="Path to EvalRunPlan JSON.")],
    output: Annotated[Path, typer.Option(help="Output report path.")] = Path("reports/eval_logs.json"),
    report_format: Annotated[ReportFormat, typer.Option("--format", help="Report format.")] = ReportFormat.JSON,
) -> None:
    """Export per-sample EvalLog rows from an EvalRunPlan."""

    if output == Path("reports/eval_logs.json") and report_format == ReportFormat.CSV:
        output = Path("reports/eval_logs.csv")
    try:
        report_path = export_eval_log_report(plan, output, report_format)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Eval log export failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]OK[/green] eval_logs={report_path}")


@app.command("export-eval-aggregates")
def export_eval_aggregates_command(
    plan: Annotated[Path, typer.Argument(help="Path to EvalRunPlan JSON.")],
    output: Annotated[Path, typer.Option(help="Output report path.")] = Path("reports/eval_aggregates.json"),
    report_format: Annotated[ReportFormat, typer.Option("--format", help="Report format.")] = ReportFormat.JSON,
) -> None:
    """Export aggregate EvalLog summaries from an EvalRunPlan."""

    if output == Path("reports/eval_aggregates.json") and report_format == ReportFormat.CSV:
        output = Path("reports/eval_aggregates.csv")
    try:
        report_path = export_eval_aggregate_report(plan, output, report_format)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Eval aggregate export failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]OK[/green] eval_aggregates={report_path}")


@app.command("scan-eval-logs")
def scan_eval_logs_command(
    plan: Annotated[Path, typer.Argument(help="Path to EvalRunPlan JSON.")],
    output: Annotated[Path, typer.Option(help="Output scanner report path.")] = Path("reports/eval_findings.json"),
    report_format: Annotated[ReportFormat, typer.Option("--format", help="Report format.")] = ReportFormat.JSON,
) -> None:
    """Run local rule-based scanner checks over EvalLogs from an EvalRunPlan."""

    if output == Path("reports/eval_findings.json") and report_format == ReportFormat.CSV:
        output = Path("reports/eval_findings.csv")
    try:
        report_path = export_eval_scan_report(plan, output, report_format)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Eval scan failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]OK[/green] eval_findings={report_path}")


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
    console.print(f"comparison_json_report: {summary.comparison_json_report}")
    console.print(f"comparison_csv_report: {summary.comparison_csv_report}")


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
