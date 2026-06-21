"""Prompt Object schema for Playground-editable agent configurations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator, model_validator

from agent_ab.schemas.common import (
    GenerationParameters,
    IdentifierMixin,
    ModelConfig,
    PromptMessage,
    PromptRole,
    ResponseFormat,
    ToolSpec,
)
from agent_ab.yaml_io import load_yaml_mapping


class PromptObject(IdentifierMixin):
    """A versioned prompt/model/tool bundle.

    This mirrors the practical UX idea used by prompt playgrounds: the editable
    unit is not just prompt text, but messages + model + parameters + tools +
    response format.
    """

    version: int = Field(default=1, ge=1)
    description: str | None = None
    messages: list[PromptMessage] = Field(min_length=1)
    model: ModelConfig
    parameters: GenerationParameters = Field(default_factory=GenerationParameters)
    tools: list[ToolSpec] = Field(default_factory=list)
    response_format: ResponseFormat = Field(default_factory=ResponseFormat)
    variables: list[str] = Field(
        default_factory=list,
        description="Declared template variables. If omitted, inferred from message templates.",
    )
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("variables")
    @classmethod
    def variable_names_are_identifiers(cls, value: list[str]) -> list[str]:
        duplicates = sorted({name for name in value if value.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate prompt variables: {duplicates}")
        for name in value:
            if not name.isidentifier():
                raise ValueError(f"prompt variable must be a valid identifier: {name}")
        return value

    @model_validator(mode="after")
    def validate_messages_and_variables(self) -> PromptObject:
        roles = [message.role for message in self.messages]
        if PromptRole.USER not in roles:
            raise ValueError("prompt object must include at least one user message")

        inferred = sorted(self.infer_variables())
        if not self.variables:
            self.variables = inferred
        else:
            missing_from_declared = sorted(set(inferred) - set(self.variables))
            if missing_from_declared:
                raise ValueError(
                    "messages reference variables that are not declared: "
                    f"{missing_from_declared}"
                )
        tool_names = [tool.name for tool in self.tools]
        duplicate_names = sorted({name for name in tool_names if tool_names.count(name) > 1})
        if duplicate_names:
            raise ValueError(f"duplicate tool names: {duplicate_names}")

        tool_ids = [tool.id for tool in self.tools if tool.id is not None]
        duplicate_ids = sorted({tool_id for tool_id in tool_ids if tool_ids.count(tool_id) > 1})
        if duplicate_ids:
            raise ValueError(f"duplicate tool ids: {duplicate_ids}")
        return self

    def infer_variables(self) -> set[str]:
        """Infer Python-format template variables from all prompt messages."""

        variables: set[str] = set()
        for message in self.messages:
            variables.update(message.template_variables())
        return variables

    def render_messages(self, variables: dict[str, Any]) -> list[PromptMessage]:
        """Render prompt messages for a concrete task/playground run."""

        missing = set(self.variables) - variables.keys()
        if missing:
            raise ValueError(f"missing prompt variables: {sorted(missing)}")
        return [message.render(variables) for message in self.messages]

    def enabled_tool_names(self) -> list[str]:
        """Return enabled tool names in declaration order."""

        return [tool.name for tool in self.tools if tool.enabled]

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> PromptObject:
        return cls.model_validate(load_yaml_mapping(path))

    def to_yaml_file(self, path: str | Path) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            yaml.safe_dump(
                self.model_dump(mode="json", by_alias=True, exclude_none=True),
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
