"""Metric registry and experiment metric-selection schema.

The names intentionally map to common agent-evaluation concepts used by
AgentEval-style systems: tool-chain assertions, stochastic pass-rate checks,
model comparison, performance SLAs, trace replay, RAG metrics, memory metrics,
red-team/security checks, and DAG step-level root-cause analysis.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import Field, field_validator, model_validator

from agent_ab.schemas.common import StrictBaseModel

_CUSTOM_METRIC_RE = re.compile(r"^custom\.[A-Za-z][A-Za-z0-9_.-]*$")


class MetricCategory(str, Enum):
    OUTCOME = "outcome"
    REASONING = "reasoning"
    TOOL = "tool"
    WORKFLOW = "workflow"
    PERFORMANCE = "performance"
    COST = "cost"
    SAFETY = "safety"
    RAG = "rag"
    MEMORY = "memory"
    STOCHASTIC = "stochastic"
    TRACE = "trace"
    DAG = "dag"
    RESPONSIBLE_AI = "responsible_ai"


class MetricDirection(str, Enum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"
    OBSERVE = "observe"


class MetricSource(str, Enum):
    AGENTEVAL_DOTNET = "agenteval_dotnet"
    AGENTEVAL_DAG_PAPER = "agenteval_dag_paper"
    DESKTOP_AGENT_AB = "desktop_agent_ab"
    COMMON_AGENT_EVAL = "common_agent_eval"


class MetricDefinition(StrictBaseModel):
    name: str
    display_name: str
    category: MetricCategory
    direction: MetricDirection
    description: str
    unit: str | None = None
    source: MetricSource = MetricSource.COMMON_AGENT_EVAL
    enabled_by_default: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


# Metric registry. Keep this pure data so it can be rendered by CLIs/UIs later.
# Source notes:
# - AgentEval .NET concepts: tool usage validation, workflow evaluation,
#   stochastic evaluation, model comparison, performance SLAs, trace record/replay,
#   red-team security, RAG, responsible AI, memory.
# - AgentEval DAG paper concepts: evaluation DAG nodes, typed quality metrics,
#   hierarchical failure taxonomy, error propagation, root-cause attribution.
AGENTEVAL_METRIC_REGISTRY: dict[str, MetricDefinition] = {
    "task_success": MetricDefinition(
        name="task_success",
        display_name="Task Success",
        category=MetricCategory.OUTCOME,
        direction=MetricDirection.MAXIMIZE,
        description="Whether the task reached its deterministic desired end state.",
        unit="ratio",
        source=MetricSource.DESKTOP_AGENT_AB,
        enabled_by_default=True,
    ),
    "validator_pass_rate": MetricDefinition(
        name="validator_pass_rate",
        display_name="Validator Pass Rate",
        category=MetricCategory.OUTCOME,
        direction=MetricDirection.MAXIMIZE,
        description="Fraction of task validators that passed for a run.",
        unit="ratio",
        source=MetricSource.DESKTOP_AGENT_AB,
        enabled_by_default=True,
    ),
    "plan_quality": MetricDefinition(
        name="plan_quality",
        display_name="Plan Quality",
        category=MetricCategory.REASONING,
        direction=MetricDirection.MAXIMIZE,
        description="Quality of an explicit plan before execution; local judge or rubric-backed.",
        unit="score",
    ),
    "plan_adherence": MetricDefinition(
        name="plan_adherence",
        display_name="Plan Adherence",
        category=MetricCategory.REASONING,
        direction=MetricDirection.MAXIMIZE,
        description="How closely actions followed the agent's own plan.",
        unit="score",
    ),
    "step_efficiency": MetricDefinition(
        name="step_efficiency",
        display_name="Step Efficiency",
        category=MetricCategory.REASONING,
        direction=MetricDirection.MAXIMIZE,
        description="How efficiently the agent completed the task relative to an expected step budget.",
        unit="score",
        enabled_by_default=True,
    ),
    "tool_success": MetricDefinition(
        name="tool_success",
        display_name="Tool Success",
        category=MetricCategory.TOOL,
        direction=MetricDirection.MAXIMIZE,
        description="Whether required tools were called and completed without tool-level errors.",
        unit="ratio",
        source=MetricSource.AGENTEVAL_DOTNET,
        enabled_by_default=True,
    ),
    "tool_call_accuracy": MetricDefinition(
        name="tool_call_accuracy",
        display_name="Tool Call Accuracy",
        category=MetricCategory.TOOL,
        direction=MetricDirection.MAXIMIZE,
        description="Correctness of selected tools for each agent step.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "tool_argument_correctness": MetricDefinition(
        name="tool_argument_correctness",
        display_name="Tool Argument Correctness",
        category=MetricCategory.TOOL,
        direction=MetricDirection.MAXIMIZE,
        description="Correctness of tool-call arguments, including paths, filters, commands, and IDs.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "tool_sequence_adherence": MetricDefinition(
        name="tool_sequence_adherence",
        display_name="Tool Sequence Adherence",
        category=MetricCategory.TOOL,
        direction=MetricDirection.MAXIMIZE,
        description="Whether required tool calls occurred in the required order.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "forbidden_tool_calls": MetricDefinition(
        name="forbidden_tool_calls",
        display_name="Forbidden Tool Calls",
        category=MetricCategory.SAFETY,
        direction=MetricDirection.MINIMIZE,
        description="Count of blocked, disallowed, or policy-violating tool calls.",
        unit="count",
        source=MetricSource.AGENTEVAL_DOTNET,
        enabled_by_default=True,
    ),
    "workflow_executor_order": MetricDefinition(
        name="workflow_executor_order",
        display_name="Workflow Executor Order",
        category=MetricCategory.WORKFLOW,
        direction=MetricDirection.MAXIMIZE,
        description="Whether multi-agent or multi-executor workflows followed the expected execution order.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "workflow_edge_coverage": MetricDefinition(
        name="workflow_edge_coverage",
        display_name="Workflow Edge Coverage",
        category=MetricCategory.WORKFLOW,
        direction=MetricDirection.MAXIMIZE,
        description="Whether expected agent/workflow graph edges were traversed.",
        unit="ratio",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "latency_ms": MetricDefinition(
        name="latency_ms",
        display_name="Latency",
        category=MetricCategory.PERFORMANCE,
        direction=MetricDirection.MINIMIZE,
        description="Total task-run duration.",
        unit="ms",
        source=MetricSource.AGENTEVAL_DOTNET,
        enabled_by_default=True,
    ),
    "first_token_latency_ms": MetricDefinition(
        name="first_token_latency_ms",
        display_name="First Token Latency",
        category=MetricCategory.PERFORMANCE,
        direction=MetricDirection.MINIMIZE,
        description="Time until first model token or first agent-visible response.",
        unit="ms",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "step_count": MetricDefinition(
        name="step_count",
        display_name="Step Count",
        category=MetricCategory.PERFORMANCE,
        direction=MetricDirection.MINIMIZE,
        description="Number of agent steps, model calls, tool calls, or desktop actions.",
        unit="count",
        source=MetricSource.DESKTOP_AGENT_AB,
        enabled_by_default=True,
    ),
    "token_count": MetricDefinition(
        name="token_count",
        display_name="Token Count",
        category=MetricCategory.COST,
        direction=MetricDirection.MINIMIZE,
        description="Prompt plus completion tokens, when available from the local/model provider.",
        unit="tokens",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "estimated_cost": MetricDefinition(
        name="estimated_cost",
        display_name="Estimated Cost",
        category=MetricCategory.COST,
        direction=MetricDirection.MINIMIZE,
        description="Estimated provider/model cost; typically zero for fully local models but useful for adapters.",
        unit="currency",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "stochastic_success_rate": MetricDefinition(
        name="stochastic_success_rate",
        display_name="Stochastic Success Rate",
        category=MetricCategory.STOCHASTIC,
        direction=MetricDirection.MAXIMIZE,
        description="Success rate across repeated runs of the same task/variant.",
        unit="ratio",
        source=MetricSource.AGENTEVAL_DOTNET,
        enabled_by_default=True,
    ),
    "stochastic_stddev": MetricDefinition(
        name="stochastic_stddev",
        display_name="Stochastic Std Dev",
        category=MetricCategory.STOCHASTIC,
        direction=MetricDirection.MINIMIZE,
        description="Variability of repeated runs for the same task/variant.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "model_comparison_rank": MetricDefinition(
        name="model_comparison_rank",
        display_name="Model Comparison Rank",
        category=MetricCategory.STOCHASTIC,
        direction=MetricDirection.MINIMIZE,
        description="Ranked model/variant outcome after multi-run comparison.",
        unit="rank",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "trace_replay_determinism": MetricDefinition(
        name="trace_replay_determinism",
        display_name="Trace Replay Determinism",
        category=MetricCategory.TRACE,
        direction=MetricDirection.MAXIMIZE,
        description="Whether a recorded trace can be replayed deterministically without live model/tool calls.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "dag_node_quality": MetricDefinition(
        name="dag_node_quality",
        display_name="DAG Node Quality",
        category=MetricCategory.DAG,
        direction=MetricDirection.MAXIMIZE,
        description="Typed quality score assigned to a step/span node in the evaluation DAG.",
        unit="score",
        source=MetricSource.AGENTEVAL_DAG_PAPER,
    ),
    "error_propagation_depth": MetricDefinition(
        name="error_propagation_depth",
        display_name="Error Propagation Depth",
        category=MetricCategory.DAG,
        direction=MetricDirection.MINIMIZE,
        description="How many downstream nodes were affected by an upstream error.",
        unit="count",
        source=MetricSource.AGENTEVAL_DAG_PAPER,
    ),
    "root_cause_accuracy": MetricDefinition(
        name="root_cause_accuracy",
        display_name="Root Cause Accuracy",
        category=MetricCategory.DAG,
        direction=MetricDirection.MAXIMIZE,
        description="Accuracy of root-cause attribution for a failed task trace.",
        unit="score",
        source=MetricSource.AGENTEVAL_DAG_PAPER,
    ),
    "failure_taxonomy_label": MetricDefinition(
        name="failure_taxonomy_label",
        display_name="Failure Taxonomy Label",
        category=MetricCategory.DAG,
        direction=MetricDirection.OBSERVE,
        description="Hierarchical failure classification attached to failed spans or task runs.",
        source=MetricSource.AGENTEVAL_DAG_PAPER,
    ),
    "safety_violation_count": MetricDefinition(
        name="safety_violation_count",
        display_name="Safety Violation Count",
        category=MetricCategory.SAFETY,
        direction=MetricDirection.MINIMIZE,
        description="Count of path, command, network, data, or policy safety violations.",
        unit="count",
        source=MetricSource.DESKTOP_AGENT_AB,
        enabled_by_default=True,
    ),
    "red_team_security_score": MetricDefinition(
        name="red_team_security_score",
        display_name="Red-Team Security Score",
        category=MetricCategory.SAFETY,
        direction=MetricDirection.MAXIMIZE,
        description="Security robustness score for prompt injection, excessive agency, PII leakage, and related probes.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "rag_faithfulness": MetricDefinition(
        name="rag_faithfulness",
        display_name="RAG Faithfulness",
        category=MetricCategory.RAG,
        direction=MetricDirection.MAXIMIZE,
        description="Whether generated content is grounded in retrieved or provided context.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "rag_relevance": MetricDefinition(
        name="rag_relevance",
        display_name="RAG Relevance",
        category=MetricCategory.RAG,
        direction=MetricDirection.MAXIMIZE,
        description="Relevance of retrieved context or generated answer to the task query.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "rag_context_precision": MetricDefinition(
        name="rag_context_precision",
        display_name="RAG Context Precision",
        category=MetricCategory.RAG,
        direction=MetricDirection.MAXIMIZE,
        description="Precision of retrieved context used by the agent.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "rag_context_recall": MetricDefinition(
        name="rag_context_recall",
        display_name="RAG Context Recall",
        category=MetricCategory.RAG,
        direction=MetricDirection.MAXIMIZE,
        description="Recall of necessary context in retrieved material.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "memory_retention": MetricDefinition(
        name="memory_retention",
        display_name="Memory Retention",
        category=MetricCategory.MEMORY,
        direction=MetricDirection.MAXIMIZE,
        description="Whether the agent retains facts across turns or sessions.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "memory_reach_back": MetricDefinition(
        name="memory_reach_back",
        display_name="Memory Reach-Back",
        category=MetricCategory.MEMORY,
        direction=MetricDirection.MAXIMIZE,
        description="Ability to retrieve relevant older memories from long context/history.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "memory_temporal_reasoning": MetricDefinition(
        name="memory_temporal_reasoning",
        display_name="Memory Temporal Reasoning",
        category=MetricCategory.MEMORY,
        direction=MetricDirection.MAXIMIZE,
        description="Ability to reason about time, updates, recency, and changed facts in memory.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "memory_noise_resilience": MetricDefinition(
        name="memory_noise_resilience",
        display_name="Memory Noise Resilience",
        category=MetricCategory.MEMORY,
        direction=MetricDirection.MAXIMIZE,
        description="Resistance to irrelevant or distracting memory entries.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "memory_reducer_fidelity": MetricDefinition(
        name="memory_reducer_fidelity",
        display_name="Memory Reducer Fidelity",
        category=MetricCategory.MEMORY,
        direction=MetricDirection.MAXIMIZE,
        description="Faithfulness of compressed or summarized memory to the original context.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "toxicity": MetricDefinition(
        name="toxicity",
        display_name="Toxicity",
        category=MetricCategory.RESPONSIBLE_AI,
        direction=MetricDirection.MINIMIZE,
        description="Toxic or abusive content in agent output.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "bias": MetricDefinition(
        name="bias",
        display_name="Bias",
        category=MetricCategory.RESPONSIBLE_AI,
        direction=MetricDirection.MINIMIZE,
        description="Bias risk in agent outputs or decisions.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
    "misinformation_risk": MetricDefinition(
        name="misinformation_risk",
        display_name="Misinformation Risk",
        category=MetricCategory.RESPONSIBLE_AI,
        direction=MetricDirection.MINIMIZE,
        description="Risk that the agent produced false or misleading content.",
        unit="score",
        source=MetricSource.AGENTEVAL_DOTNET,
    ),
}


def metric_names() -> list[str]:
    """Return sorted known metric names."""

    return sorted(AGENTEVAL_METRIC_REGISTRY)


def get_metric_definition(name: str) -> MetricDefinition:
    """Return a metric definition by name.

    Custom metrics are allowed in configs only if they use the `custom.` prefix;
    those cannot be fetched from the built-in registry.
    """

    try:
        return AGENTEVAL_METRIC_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unknown built-in metric: {name}") from exc


def is_known_or_custom_metric(name: str) -> bool:
    return name in AGENTEVAL_METRIC_REGISTRY or bool(_CUSTOM_METRIC_RE.match(name))


class MetricSelection(StrictBaseModel):
    primary: str = Field(default="task_success")
    secondary: list[str] = Field(
        default_factory=lambda: [
            "validator_pass_rate",
            "latency_ms",
            "step_count",
            "tool_success",
            "safety_violation_count",
            "stochastic_success_rate",
        ]
    )
    required_gates: dict[str, float] = Field(
        default_factory=dict,
        description="Optional metric thresholds, e.g. task_success: 0.85.",
    )
    report_groups: list[MetricCategory] = Field(default_factory=list)

    @field_validator("primary")
    @classmethod
    def primary_metric_known(cls, value: str) -> str:
        if not is_known_or_custom_metric(value):
            raise ValueError(f"unknown metric '{value}'. Use a built-in name or custom.<name>.")
        return value

    @field_validator("secondary")
    @classmethod
    def secondary_metrics_known(cls, value: list[str]) -> list[str]:
        unknown = [name for name in value if not is_known_or_custom_metric(name)]
        if unknown:
            raise ValueError(f"unknown secondary metrics: {unknown}")
        duplicates = sorted({name for name in value if value.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate secondary metrics: {duplicates}")
        return value

    @model_validator(mode="after")
    def gates_reference_selected_metrics(self) -> MetricSelection:
        selected = {self.primary, *self.secondary}
        missing = sorted(set(self.required_gates) - selected)
        if missing:
            raise ValueError(f"required_gates reference metrics that are not selected: {missing}")
        return self
