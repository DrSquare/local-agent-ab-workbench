from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_ab.schemas.trace import (
    ModelCallDetail,
    ScoringDetail,
    SpanEvent,
    SpanKind,
    ToolCallDetail,
    TraceEnvelope,
    TraceSpan,
    ValidatorDetail,
)
from agent_ab.trace_store import index_trace_sqlite, read_trace_jsonl, write_trace_jsonl


def make_demo_trace() -> TraceEnvelope:
    trace_id = "trace.demo"
    return TraceEnvelope(
        trace_id=trace_id,
        experiment_name="openclaw_prompt_ab_v1",
        taskpack_id="desktop_basics",
        task_id="rename_todo",
        variant_id="A",
        run_id="run.demo",
        created_at_ms=1000,
        spans=[
            TraceSpan(
                trace_id=trace_id,
                span_id="span.root",
                name="rename_todo",
                kind=SpanKind.TASK_RUN,
                started_at_ms=1000,
                ended_at_ms=1800,
            ),
            TraceSpan(
                trace_id=trace_id,
                span_id="span.llm",
                parent_span_id="span.root",
                name="plan",
                kind=SpanKind.LLM,
                started_at_ms=1100,
                ended_at_ms=1200,
                model_call=ModelCallDetail(
                    provider="ollama",
                    model="llama3.1:8b",
                    parameters={"temperature": 0.2},
                    input_preview="Task query",
                    output_preview="Plan",
                    prompt_tokens=12,
                    completion_tokens=8,
                ),
            ),
            TraceSpan(
                trace_id=trace_id,
                span_id="span.tool",
                parent_span_id="span.root",
                name="write_file",
                kind=SpanKind.TOOL,
                started_at_ms=1250,
                ended_at_ms=1400,
                tool_call=ToolCallDetail(
                    tool_name="write_file",
                    arguments={"path": "notes/action-items.txt"},
                    result_preview="created",
                ),
            ),
            TraceSpan(
                trace_id=trace_id,
                span_id="span.validator",
                parent_span_id="span.root",
                name="file_exists",
                kind=SpanKind.VALIDATOR,
                started_at_ms=1500,
                ended_at_ms=1510,
                validator=ValidatorDetail(
                    validator_type="file_exists",
                    path="notes/action-items.txt",
                    passed=True,
                ),
            ),
            TraceSpan(
                trace_id=trace_id,
                span_id="span.scoring",
                parent_span_id="span.root",
                name="score",
                kind=SpanKind.SCORING,
                started_at_ms=1700,
                ended_at_ms=1800,
                scoring=ScoringDetail(metrics={"task_success": 1.0, "latency_ms": 800}),
            ),
        ],
    )


def test_trace_envelope_validates_parent_child_tree() -> None:
    trace = make_demo_trace()

    assert trace.root_span().span_id == "span.root"
    assert trace.spans[1].duration_ms == 100
    assert [span.span_id for span in trace.spans_by_parent()["span.root"]] == [
        "span.llm",
        "span.tool",
        "span.validator",
        "span.scoring",
    ]


def test_trace_rejects_duplicate_or_missing_parent_spans() -> None:
    trace = make_demo_trace()
    duplicate_payload = trace.model_dump()
    duplicate_payload["spans"][1]["span_id"] = "span.root"
    with pytest.raises(ValidationError, match="duplicate span ids"):
        TraceEnvelope.model_validate(duplicate_payload)

    missing_parent_payload = trace.model_dump()
    missing_parent_payload["spans"][1]["parent_span_id"] = "span.missing"
    with pytest.raises(ValidationError, match="span parent not found"):
        TraceEnvelope.model_validate(missing_parent_payload)


def test_trace_rejects_temporally_impossible_spans_and_events() -> None:
    trace = make_demo_trace()

    child_before_parent_payload = trace.model_dump()
    child_before_parent_payload["spans"][1]["started_at_ms"] = 999
    with pytest.raises(ValidationError, match="span starts before parent"):
        TraceEnvelope.model_validate(child_before_parent_payload)

    child_after_parent_payload = trace.model_dump()
    child_after_parent_payload["spans"][1]["ended_at_ms"] = 1801
    with pytest.raises(ValidationError, match="span ends after parent"):
        TraceEnvelope.model_validate(child_after_parent_payload)

    with pytest.raises(ValidationError, match="event timestamp cannot be after span end"):
        TraceSpan(
            trace_id="trace.bad",
            span_id="span.event",
            name="event",
            kind=SpanKind.TASK_RUN,
            started_at_ms=0,
            ended_at_ms=10,
            events=[SpanEvent(name="late", timestamp_ms=11)],
        )


def test_trace_rejects_wrong_or_missing_typed_detail() -> None:
    trace_id = "trace.bad"
    with pytest.raises(ValidationError, match="requires exactly model_call"):
        TraceSpan(
            trace_id=trace_id,
            span_id="span.llm",
            parent_span_id="span.root",
            name="llm",
            kind=SpanKind.LLM,
            started_at_ms=0,
        )

    with pytest.raises(ValidationError, match="does not allow typed details"):
        TraceSpan(
            trace_id=trace_id,
            span_id="span.setup",
            parent_span_id="span.root",
            name="setup",
            kind=SpanKind.SETUP,
            started_at_ms=0,
            tool_call=ToolCallDetail(tool_name="read_file"),
        )


def test_scoring_metrics_must_be_known_or_custom() -> None:
    ScoringDetail(metrics={"task_success": 1.0, "custom.local_score": 0.5})

    with pytest.raises(ValidationError, match="unknown scoring metrics"):
        ScoringDetail(metrics={"made_up_metric": 1.0})


def test_trace_jsonl_round_trip(tmp_path: Path) -> None:
    trace = make_demo_trace()
    trace_path = tmp_path / "traces.jsonl"

    write_trace_jsonl(trace_path, trace)
    loaded = read_trace_jsonl(trace_path)

    assert len(loaded) == 1
    assert loaded[0].trace_id == trace.trace_id
    assert loaded[0].spans[2].tool_call is not None
    assert loaded[0].spans[2].tool_call.tool_name == "write_file"


def test_trace_sqlite_index_contract(tmp_path: Path) -> None:
    trace = make_demo_trace()
    db_path = tmp_path / "trace.sqlite"

    index_trace_sqlite(db_path, trace)

    with sqlite3.connect(db_path) as connection:
        trace_count = connection.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
        span_count = connection.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
        llm_count = connection.execute(
            "SELECT COUNT(*) FROM spans WHERE kind = ?",
            (SpanKind.LLM.value,),
        ).fetchone()[0]

    assert trace_count == 1
    assert span_count == len(trace.spans)
    assert llm_count == 1
