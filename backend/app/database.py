"""SQLite-based persistent storage for conversations and messages."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, List, Optional
from uuid import uuid4

from .config import settings
from .models import ChatMessage, Draft, SkillEvaluation, SkillSpec

TITLE_MAX_LENGTH = 40


def _db_path() -> Path:
    path = Path(settings.storage_root) / "skill_factory.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(str(_db_path()))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    """Create tables if they don't already exist."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                spec        TEXT NOT NULL DEFAULT '{}',
                attachments TEXT NOT NULL DEFAULT '[]',
                history_summary TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS evaluations (
                id              TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                score           INTEGER NOT NULL DEFAULT 0,
                dimensions      TEXT NOT NULL DEFAULT '{}',
                feedback        TEXT NOT NULL DEFAULT '',
                suggestions     TEXT NOT NULL DEFAULT '[]',
                created_at      TEXT NOT NULL,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id) ON DELETE CASCADE
            );
        """)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _title_from_messages(messages: List[ChatMessage]) -> str:
    for m in messages:
        if m.role == "user":
            return m.content[:TITLE_MAX_LENGTH]
    return ""


# ──────────────────────────────────────────────
# CRUD helpers
# ──────────────────────────────────────────────

def db_create() -> Draft:
    cid = str(uuid4())
    now = _now()
    with _conn() as con:
        con.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?,?,?,?)",
            (cid, "", now, now),
        )
    return Draft(conversation_id=cid)


def db_get(conversation_id: str) -> Optional[Draft]:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if not row:
            return None
        msgs = con.execute(
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()

    messages = [ChatMessage(role=m["role"], content=m["content"]) for m in msgs]
    spec = SkillSpec(**json.loads(row["spec"]))
    attachments: List[str] = json.loads(row["attachments"])

    return Draft(
        conversation_id=conversation_id,
        messages=messages,
        spec=spec,
        attachments=attachments,
        history_summary=row["history_summary"],
    )


def db_save(draft: Draft) -> None:
    now = _now()
    title = _title_from_messages(draft.messages)
    spec_json = json.dumps(draft.spec.model_dump(), ensure_ascii=False)
    att_json = json.dumps(draft.attachments, ensure_ascii=False)

    with _conn() as con:
        existing = con.execute(
            "SELECT id FROM conversations WHERE id = ?", (draft.conversation_id,)
        ).fetchone()

        if existing:
            con.execute(
                "UPDATE conversations SET title=?, updated_at=?, spec=?, attachments=?, history_summary=? WHERE id=?",
                (title, now, spec_json, att_json, draft.history_summary, draft.conversation_id),
            )
            con.execute(
                "DELETE FROM messages WHERE conversation_id = ?", (draft.conversation_id,)
            )
        else:
            con.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at, spec, attachments, history_summary)"
                " VALUES (?,?,?,?,?,?,?)",
                (draft.conversation_id, title, now, now, spec_json, att_json, draft.history_summary),
            )

        for msg in draft.messages:
            con.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
                (draft.conversation_id, msg.role, msg.content, now),
            )


def db_list() -> List[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def db_delete(conversation_id: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    return cur.rowcount > 0


# ──────────────────────────────────────────────
# Evaluation CRUD
# ──────────────────────────────────────────────

def db_save_evaluation(evaluation: SkillEvaluation) -> SkillEvaluation:
    """Persist a SkillEvaluation and return it with generated id/created_at."""
    if not evaluation.evaluation_id:
        evaluation = evaluation.model_copy(update={"evaluation_id": str(uuid4())})
    if not evaluation.created_at:
        evaluation = evaluation.model_copy(update={"created_at": _now()})

    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO evaluations "
            "(id, conversation_id, score, dimensions, feedback, suggestions, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                evaluation.evaluation_id,
                evaluation.conversation_id,
                evaluation.score,
                json.dumps(evaluation.dimensions, ensure_ascii=False),
                evaluation.feedback,
                json.dumps(evaluation.suggestions, ensure_ascii=False),
                evaluation.created_at,
            ),
        )
    return evaluation


def db_get_evaluation(conversation_id: str) -> Optional[SkillEvaluation]:
    """Return the most recent evaluation for a conversation, or None."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM evaluations WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
    if not row:
        return None
    return SkillEvaluation(
        evaluation_id=row["id"],
        conversation_id=row["conversation_id"],
        score=row["score"],
        dimensions=json.loads(row["dimensions"]),
        feedback=row["feedback"],
        suggestions=json.loads(row["suggestions"]),
        created_at=row["created_at"],
    )


def db_list_evaluations() -> List[dict]:
    """Return all evaluations ordered by most recent first."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, conversation_id, score, feedback, created_at "
            "FROM evaluations ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]
