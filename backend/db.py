"""
Lightweight SQLite persistence. This is a demo, not a production system —
one file, no migrations framework, no ORM. Good enough to let a viewer
come back and see past sessions (the "nice to have" persisted history).
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

_DEFAULT_DB_PATH = "/tmp/handoff_iq.db" if os.environ.get("VERCEL") else "./handoff_iq.db"
DB_PATH = os.environ.get("HANDOFF_IQ_DB_PATH", _DEFAULT_DB_PATH)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                scenario_id TEXT NOT NULL,
                scenario_title TEXT NOT NULL,
                mode TEXT NOT NULL,
                language TEXT NOT NULL,
                created_at TEXT NOT NULL,
                final_decision TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                caller_text TEXT NOT NULL,
                agent_reply TEXT NOT NULL,
                intent_confidence REAL,
                data_sufficiency REAL,
                sensitivity_flag INTEGER,
                sensitivity_reason TEXT,
                decision TEXT,
                reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS handoffs (
                session_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
            """
        )


def create_session(scenario_id: str, scenario_title: str, mode: str, language: str) -> str:
    session_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (id, scenario_id, scenario_title, mode, language, created_at, final_decision) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL)",
            (session_id, scenario_id, scenario_title, mode, language, datetime.now(timezone.utc).isoformat()),
        )
    return session_id


def add_turn(
    session_id: str,
    turn_index: int,
    caller_text: str,
    agent_reply: str,
    intent_confidence: float | None,
    data_sufficiency: float | None,
    sensitivity_flag: bool | None,
    sensitivity_reason: str | None,
    decision: str | None,
    reason: str | None,
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO turns (
                id, session_id, turn_index, caller_text, agent_reply,
                intent_confidence, data_sufficiency, sensitivity_flag,
                sensitivity_reason, decision, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                session_id,
                turn_index,
                caller_text,
                agent_reply,
                intent_confidence,
                data_sufficiency,
                int(bool(sensitivity_flag)) if sensitivity_flag is not None else None,
                sensitivity_reason,
                decision,
                reason,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        if decision:
            conn.execute(
                "UPDATE sessions SET final_decision = ? WHERE id = ?",
                (decision, session_id),
            )


def save_handoff(session_id: str, payload: dict):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO handoffs (session_id, payload_json, created_at) VALUES (?, ?, ?)",
            (session_id, json.dumps(payload), datetime.now(timezone.utc).isoformat()),
        )


def get_trace(session_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM turns WHERE session_id = ? ORDER BY turn_index ASC",
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_handoff(session_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT payload_json FROM handoffs WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None


def get_conversation(session_id: str) -> list[dict]:
    """Reconstruct the caller/agent turn list for feeding back into the LLM."""
    trace = get_trace(session_id)
    conversation = []
    for t in trace:
        conversation.append({"role": "caller", "text": t["caller_text"]})
        conversation.append({"role": "agent", "text": t["agent_reply"]})
    return conversation


def list_sessions(limit: int = 25) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, scenario_id, scenario_title, mode, language, created_at, final_decision "
            "FROM sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
