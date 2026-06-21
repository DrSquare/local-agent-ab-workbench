"""Local validator executor for Module 2 task contracts."""

from __future__ import annotations

import re
from pathlib import Path

from agent_ab.schemas.run import ValidatorRunResult
from agent_ab.schemas.task import TaskValidator


def resolve_workspace_path(workspace_path: str | Path, relative_path: str) -> Path:
    workspace_root = Path(workspace_path).resolve()
    candidate = (workspace_root / relative_path).resolve()
    if candidate != workspace_root and workspace_root not in candidate.parents:
        raise ValueError(f"validator path escapes workspace: {relative_path}")
    return candidate


def execute_task_validator(validator: TaskValidator, workspace_path: str | Path) -> ValidatorRunResult:
    if validator.type.startswith("custom."):
        return ValidatorRunResult(
            validator_type=validator.type,
            path=validator.path,
            passed=False,
            message="custom validators are declarative only in Module 4",
        )

    if validator.path is None:
        return ValidatorRunResult(
            validator_type=validator.type,
            passed=False,
            message="validator is missing path",
        )

    target = resolve_workspace_path(workspace_path, validator.path)
    if validator.type == "file_exists":
        passed = target.is_file()
        return ValidatorRunResult(
            validator_type=validator.type,
            path=validator.path,
            passed=passed,
            message="file exists" if passed else "file does not exist",
            expected=True,
            observed=passed,
        )

    if validator.type == "file_not_exists":
        passed = not target.exists()
        return ValidatorRunResult(
            validator_type=validator.type,
            path=validator.path,
            passed=passed,
            message="file absent" if passed else "file exists",
            expected=False,
            observed=target.exists(),
        )

    if not target.is_file():
        return ValidatorRunResult(
            validator_type=validator.type,
            path=validator.path,
            passed=False,
            message="file does not exist",
        )

    content = target.read_text(encoding="utf-8")
    if validator.type == "file_contains":
        passed = validator.contains in content if validator.contains is not None else False
        return ValidatorRunResult(
            validator_type=validator.type,
            path=validator.path,
            passed=passed,
            message="file contains expected text" if passed else "file does not contain expected text",
            expected=validator.contains,
            observed=content,
        )

    if validator.type == "file_not_contains":
        passed = validator.contains not in content if validator.contains is not None else False
        return ValidatorRunResult(
            validator_type=validator.type,
            path=validator.path,
            passed=passed,
            message="file omits forbidden text" if passed else "file contains forbidden text",
            expected=validator.contains,
            observed=content,
        )

    if validator.type == "file_matches_regex":
        passed = re.search(validator.pattern or "", content) is not None
        return ValidatorRunResult(
            validator_type=validator.type,
            path=validator.path,
            passed=passed,
            message="file matches regex" if passed else "file does not match regex",
            expected=validator.pattern,
            observed=content,
        )

    return ValidatorRunResult(
        validator_type=validator.type,
        path=validator.path,
        passed=False,
        message=f"unsupported validator type: {validator.type}",
    )
