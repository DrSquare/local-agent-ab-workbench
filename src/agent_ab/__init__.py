"""Local offline A/B testing workbench for desktop AI agents."""

from agent_ab.schemas.experiment import ExperimentConfig
from agent_ab.schemas.playground import PlaygroundRunRequest, PlaygroundRunResponse, PlaygroundView
from agent_ab.schemas.prompt_object import PromptObject
from agent_ab.schemas.run import TaskRunResult
from agent_ab.schemas.task import TaskPack
from agent_ab.schemas.trace import TraceEnvelope

__all__ = [
    "ExperimentConfig",
    "PlaygroundRunRequest",
    "PlaygroundRunResponse",
    "PlaygroundView",
    "PromptObject",
    "TaskPack",
    "TaskRunResult",
    "TraceEnvelope",
]

__version__ = "0.1.0"
