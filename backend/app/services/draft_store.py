from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from app.core.config import settings
from app.schemas.task_draft_schema import TaskDraftRecord


class SQLiteDraftStore:
    """Small SQLite-backed store for task drafts.

    Drafts are still owned by DraftManager. This store persists the whole draft
    record as JSON columns so phase-one audit/recovery does not need a migration
    framework or ORM model dependency.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = Path(db_path or settings.sqlite_db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def load_all(self) -> list[TaskDraftRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT record_json
                FROM task_drafts
                ORDER BY updated_at ASC
                """
            ).fetchall()
        drafts: list[TaskDraftRecord] = []
        for row in rows:
            try:
                drafts.append(TaskDraftRecord.model_validate(json.loads(row["record_json"])))
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
        return drafts

    def save(self, draft: TaskDraftRecord) -> None:
        record_json = json.dumps(draft.model_dump(mode="json"), ensure_ascii=False)
        current_draft_json = json.dumps(draft.current_draft, ensure_ascii=False)
        proposal_intent_json = (
            json.dumps(draft.proposal_intent, ensure_ascii=False)
            if draft.proposal_intent is not None
            else None
        )
        events_json = json.dumps(
            [event.model_dump(mode="json") for event in draft.events],
            ensure_ascii=False,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_drafts (
                    draft_id,
                    session_id,
                    task_type,
                    status,
                    current_draft_json,
                    proposal_intent_json,
                    events_json,
                    record_json,
                    created_at,
                    updated_at,
                    cancelled_at,
                    confirmed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(draft_id) DO UPDATE SET
                    session_id = excluded.session_id,
                    task_type = excluded.task_type,
                    status = excluded.status,
                    current_draft_json = excluded.current_draft_json,
                    proposal_intent_json = excluded.proposal_intent_json,
                    events_json = excluded.events_json,
                    record_json = excluded.record_json,
                    updated_at = excluded.updated_at,
                    cancelled_at = excluded.cancelled_at,
                    confirmed_at = excluded.confirmed_at
                """,
                (
                    draft.draft_id,
                    draft.session_id,
                    draft.task_type.value,
                    draft.status.value,
                    current_draft_json,
                    proposal_intent_json,
                    events_json,
                    record_json,
                    draft.created_at.isoformat(),
                    draft.updated_at.isoformat(),
                    draft.cancelled_at.isoformat() if draft.cancelled_at else None,
                    draft.confirmed_at.isoformat() if draft.confirmed_at else None,
                ),
            )
            conn.commit()

    def save_many(self, drafts: Iterable[TaskDraftRecord]) -> None:
        for draft in drafts:
            self.save(draft)

    def delete(self, draft_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM task_drafts WHERE draft_id = ?", (draft_id,))
            conn.commit()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_drafts (
                    draft_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_draft_json TEXT NOT NULL,
                    proposal_intent_json TEXT,
                    events_json TEXT NOT NULL,
                    record_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    cancelled_at TEXT,
                    confirmed_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_drafts_session_status
                ON task_drafts(session_id, status)
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn
