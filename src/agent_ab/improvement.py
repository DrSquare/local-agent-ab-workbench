"""Local improvement-loop artifacts for Playground-driven review."""

from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import Field, field_validator

from agent_ab.playground import load_playground_view
from agent_ab.schemas.common import StrictBaseModel, _non_blank, _normalized_non_blank_list
from agent_ab.schemas.playground import validate_playground_token
from agent_ab.schemas.trace import validate_trace_token

GUARDRAIL_REMINDERS = [
    "Candidate promotion writes review artifacts only; source configs are not mutated automatically.",
    "Real adapter execution remains behind explicit guardrail opt-in.",
    "Review tool policy, workspace paths, and non-local endpoints before rerunning a real adapter.",
]


class ImprovementNoteRequest(StrictBaseModel):
    id: str | None = None
    eval_task_id: str
    sample_id: str
    eval_run_id: str
    trace_id: str | None = None
    triage_note_id: str | None = None
    playground_view_id: str | None = None
    body: str
    status: str = "open"
    tags: list[str] = Field(default_factory=list)

    @field_validator("id", "eval_run_id", "trace_id", "triage_note_id")
    @classmethod
    def trace_tokens_are_valid(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return validate_trace_token(value, info.field_name)

    @field_validator("playground_view_id")
    @classmethod
    def playground_view_id_is_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_playground_token(value, "playground_view_id")

    @field_validator("eval_task_id", "sample_id", "body", "status")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _non_blank(value, "improvement note field")

    @field_validator("tags")
    @classmethod
    def tags_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "improvement note tag")


class ImprovementNote(ImprovementNoteRequest):
    id: str
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)


class RerunQueueRequest(StrictBaseModel):
    id: str | None = None
    eval_task_id: str
    sample_id: str
    task_id: str
    solver_id: str
    variant_id: str | None = None
    eval_run_id: str
    trace_id: str | None = None
    triage_note_id: str | None = None
    source: str = "regression_review"
    reason: str
    status: str = "queued"
    tags: list[str] = Field(default_factory=list)

    @field_validator("id", "eval_run_id", "trace_id", "triage_note_id")
    @classmethod
    def trace_tokens_are_valid(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return validate_trace_token(value, info.field_name)

    @field_validator("eval_task_id", "sample_id", "task_id", "solver_id", "source", "reason", "status")
    @classmethod
    def required_strings_not_blank(cls, value: str) -> str:
        return _non_blank(value, "rerun queue field")

    @field_validator("variant_id")
    @classmethod
    def optional_strings_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_blank(value, "rerun queue field")

    @field_validator("tags")
    @classmethod
    def tags_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalized_non_blank_list(value, "rerun queue tag")


class RerunQueueItem(RerunQueueRequest):
    id: str
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)


class CandidatePromotionRequest(StrictBaseModel):
    playground_view_id: str
    label: str
    source_eval_run_id: str | None = None
    source_trace_id: str | None = None
    source_triage_note_id: str | None = None
    notes: str | None = None

    @field_validator("playground_view_id")
    @classmethod
    def playground_view_id_is_valid(cls, value: str) -> str:
        return validate_playground_token(value, "playground_view_id")

    @field_validator("source_eval_run_id", "source_trace_id", "source_triage_note_id")
    @classmethod
    def trace_tokens_are_valid(cls, value: str | None, info) -> str | None:
        if value is None:
            return None
        return validate_trace_token(value, info.field_name)

    @field_validator("label")
    @classmethod
    def label_not_blank(cls, value: str) -> str:
        return _non_blank(value, "candidate promotion label")

    @field_validator("notes")
    @classmethod
    def notes_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _non_blank(value, "candidate promotion notes")


class CandidatePromotion(StrictBaseModel):
    id: str
    label: str
    created_at_ms: int = Field(ge=0)
    playground_view_id: str
    playground_run_id: str
    source_eval_run_id: str | None = None
    source_trace_id: str | None = None
    source_triage_note_id: str | None = None
    notes: str | None = None
    artifact_path: str
    prompt_snapshot_path: str
    run_request_path: str
    guardrail_reminders: list[str] = Field(default_factory=lambda: list(GUARDRAIL_REMINDERS))


class ImprovementReadModel(StrictBaseModel):
    notes: list[ImprovementNote] = Field(default_factory=list)
    rerun_queue: list[RerunQueueItem] = Field(default_factory=list)
    promotions: list[CandidatePromotion] = Field(default_factory=list)
    guardrail_reminders: list[str] = Field(default_factory=lambda: list(GUARDRAIL_REMINDERS))


def build_improvement_read_model(
    runs_root: str | Path,
    project_root: str | Path,
) -> ImprovementReadModel:
    return ImprovementReadModel(
        notes=load_improvement_notes(_improvement_notes_path(runs_root)),
        rerun_queue=load_rerun_queue(_rerun_queue_path(runs_root)),
        promotions=load_candidate_promotions(_promotion_root(runs_root), project_root),
    )


def load_improvement_notes(path: str | Path) -> list[ImprovementNote]:
    return [ImprovementNote.model_validate(item) for item in _load_items(path, "notes")]


def save_improvement_note(
    path: str | Path,
    request: ImprovementNoteRequest,
    *,
    now_ms: int | None = None,
) -> ImprovementNote:
    notes_path = Path(path)
    timestamp = _timestamp_ms(now_ms)
    notes = load_improvement_notes(notes_path)
    note_id = request.id or _next_id("improvement.note", [note.id for note in notes])
    existing = next((note for note in notes if note.id == note_id), None)
    note = ImprovementNote(
        **request.model_dump(exclude={"id"}),
        id=note_id,
        created_at_ms=existing.created_at_ms if existing else timestamp,
        updated_at_ms=timestamp,
    )
    _write_items(notes_path, "notes", _replace_item(notes, note))
    return note


def load_rerun_queue(path: str | Path) -> list[RerunQueueItem]:
    return [RerunQueueItem.model_validate(item) for item in _load_items(path, "items")]


def save_rerun_queue_item(
    path: str | Path,
    request: RerunQueueRequest,
    *,
    now_ms: int | None = None,
) -> RerunQueueItem:
    queue_path = Path(path)
    timestamp = _timestamp_ms(now_ms)
    items = load_rerun_queue(queue_path)
    item_id = request.id or _next_id("rerun", [item.id for item in items])
    existing = next((item for item in items if item.id == item_id), None)
    item = RerunQueueItem(
        **request.model_dump(exclude={"id"}),
        id=item_id,
        created_at_ms=existing.created_at_ms if existing else timestamp,
        updated_at_ms=timestamp,
    )
    _write_items(queue_path, "items", _replace_item(items, item))
    return item


def load_candidate_promotions(
    promotions_root: str | Path,
    project_root: str | Path,
) -> list[CandidatePromotion]:
    root = Path(promotions_root)
    if not root.is_dir():
        return []
    promotions: list[CandidatePromotion] = []
    for path in sorted(root.glob("*/promotion.json")):
        promotion = CandidatePromotion.model_validate_json(path.read_text(encoding="utf-8"))
        promotions.append(
            promotion.model_copy(
                update={
                    "artifact_path": _path_for_response(root / promotion.id / "promotion.json", Path(project_root)),
                    "prompt_snapshot_path": _path_for_response(
                        root / promotion.id / "prompt_object.json",
                        Path(project_root),
                    ),
                    "run_request_path": _path_for_response(
                        root / promotion.id / "playground_request.json",
                        Path(project_root),
                    ),
                }
            )
        )
    return promotions


def save_candidate_promotion(
    project_root: str | Path,
    playground_root: str | Path,
    request: CandidatePromotionRequest,
    *,
    artifact_root: str | Path | None = None,
    now_ms: int | None = None,
) -> CandidatePromotion:
    root = Path(project_root).resolve()
    promotion_root = _promotion_root(artifact_root or root)
    timestamp = _timestamp_ms(now_ms)
    view = load_playground_view(playground_root, request.playground_view_id)
    existing_ids = [promotion.id for promotion in load_candidate_promotions(promotion_root, root)]
    promotion_id = _next_id("promotion", existing_ids)
    promotion_dir = promotion_root / promotion_id
    promotion_dir.mkdir(parents=True, exist_ok=False)

    prompt_snapshot_path = promotion_dir / "prompt_object.json"
    run_request_path = promotion_dir / "playground_request.json"
    promotion_path = promotion_dir / "promotion.json"
    prompt_snapshot_path.write_text(
        view.effective_prompt.model_dump_json(indent=2, by_alias=True),
        encoding="utf-8",
    )
    run_request_path.write_text(
        view.request.model_dump_json(indent=2, by_alias=True),
        encoding="utf-8",
    )
    promotion = CandidatePromotion(
        id=promotion_id,
        label=request.label,
        created_at_ms=timestamp,
        playground_view_id=view.id,
        playground_run_id=view.response.run_id,
        source_eval_run_id=request.source_eval_run_id,
        source_trace_id=request.source_trace_id,
        source_triage_note_id=request.source_triage_note_id,
        notes=request.notes,
        artifact_path=_path_for_response(promotion_path, root),
        prompt_snapshot_path=_path_for_response(prompt_snapshot_path, root),
        run_request_path=_path_for_response(run_request_path, root),
    )
    promotion_path.write_text(promotion.model_dump_json(indent=2), encoding="utf-8")
    return promotion


def _improvement_notes_path(runs_root: str | Path) -> Path:
    return Path(runs_root) / "improvement_notes.json"


def _rerun_queue_path(runs_root: str | Path) -> Path:
    return Path(runs_root) / "rerun_queue.json"


def _promotion_root(project_root: str | Path) -> Path:
    return Path(project_root) / "improvements" / "promotions"


def _load_items(path: str | Path, key: str) -> list[dict]:
    item_path = Path(path)
    if not item_path.is_file():
        return []
    payload = json.loads(item_path.read_text(encoding="utf-8"))
    items = payload.get(key) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError(f"{item_path} must contain a {key} list")
    return items


def _write_items(path: Path, key: str, items: list[StrictBaseModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(items, key=lambda item: (item.updated_at_ms, item.id))
    path.write_text(
        json.dumps({key: [item.model_dump(mode="json") for item in ordered]}, indent=2),
        encoding="utf-8",
    )


def _replace_item(items: list, item):
    return [existing for existing in items if existing.id != item.id] + [item]


def _next_id(prefix: str, existing_ids: list[str]) -> str:
    index = len(existing_ids) + 1
    existing = set(existing_ids)
    while f"{prefix}.{index}" in existing:
        index += 1
    return f"{prefix}.{index}"


def _timestamp_ms(now_ms: int | None) -> int:
    return now_ms if now_ms is not None else int(time.time() * 1000)


def _path_for_response(path: str | Path, project_root: Path) -> str:
    resolved = Path(path).resolve()
    root = project_root.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return str(resolved)
