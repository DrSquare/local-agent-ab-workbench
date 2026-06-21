"""Local offline A/B testing workbench for desktop AI agents."""

from agent_ab.schemas.experiment import ExperimentConfig
from agent_ab.schemas.prompt_object import PromptObject
from agent_ab.schemas.task import TaskPack

__all__ = ["ExperimentConfig", "PromptObject", "TaskPack"]

__version__ = "0.1.0"
