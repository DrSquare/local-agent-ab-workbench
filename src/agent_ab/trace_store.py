"""Local trace persistence helpers.

These helpers persist already-validated trace contracts. They do not run agents,
execute tools, or capture telemetry.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agent_ab.schemas.trace import TraceEnvelope


def write_trace_jsonl(path: str | Path, trace: TraceEnvelope) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as trace_file:
        trace_file.write(trace.model_dump_json(exclude_none=True))
        trace_file.write("\n")


def read_trace_jsonl(path: str | Path) -> list[TraceEnvelope]:
    input_path = Path(path)
    traces: list[TraceEnvelope] = []
    with input_path.open(encoding="utf-8") as trace_file:
        for line_number, line in enumerate(trace_file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                traces.append(TraceEnvelope.model_validate_json(stripped))
            except ValueError as exc:
                raise ValueError(f"invalid trace JSONL at line {line_number}: {exc}") from exc
    return traces


def initialize_trace_sqlite(path: str | Path) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                experiment_name TEXT,
                taskpack_id TEXT,
                task_id TEXT,
                variant_id TEXT,
                run_id TEXT,
                created_at_ms INTEGER NOT NULL,
                span_count INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS spans (
                span_id TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                parent_span_id TEXT,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at_ms INTEGER NOT NULL,
                ended_at_ms INTEGER,
                duration_ms INTEGER,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (trace_id, span_id),
                FOREIGN KEY (trace_id) REFERENCES traces(trace_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_spans_trace_parent
                ON spans(trace_id, parent_span_id);
            CREATE INDEX IF NOT EXISTS idx_spans_trace_kind
                ON spans(trace_id, kind);
            """
        )


def index_trace_sqlite(path: str | Path, trace: TraceEnvelope) -> None:
    initialize_trace_sqlite(path)
    with sqlite3.connect(Path(path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO traces (
                    trace_id,
                    schema_version,
                    experiment_name,
                    taskpack_id,
                    task_id,
                    variant_id,
                    run_id,
                    created_at_ms,
                    span_count,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace.trace_id,
                    trace.schema_version,
                    trace.experiment_name,
                    trace.taskpack_id,
                    trace.task_id,
                    trace.variant_id,
                    trace.run_id,
                    trace.created_at_ms,
                    len(trace.spans),
                    trace.model_dump_json(exclude_none=True),
                ),
            )
            connection.execute("DELETE FROM spans WHERE trace_id = ?", (trace.trace_id,))
            connection.executemany(
                """
                INSERT INTO spans (
                    span_id,
                    trace_id,
                    parent_span_id,
                    name,
                    kind,
                    status,
                    started_at_ms,
                    ended_at_ms,
                    duration_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        span.span_id,
                        span.trace_id,
                        span.parent_span_id,
                        span.name,
                        span.kind,
                        span.status,
                        span.started_at_ms,
                        span.ended_at_ms,
                        span.duration_ms,
                        span.model_dump_json(exclude_none=True),
                    )
                    for span in trace.spans
                ],
            )
