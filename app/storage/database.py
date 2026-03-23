import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get("DB_PATH", "/data/operational_assistant.db")


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS operational_requests (
                request_id TEXT PRIMARY KEY,
                request_type TEXT NOT NULL,
                target_service TEXT NOT NULL,
                environment TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,
                error TEXT,
                parameters TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                duration_ms REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                event TEXT NOT NULL,
                details TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        conn.commit()


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def create_request(
    request_id: str,
    request_type: str,
    target_service: str,
    environment: str,
    parameters: dict,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO operational_requests
            (request_id, request_type, target_service, environment, status, parameters, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (request_id, request_type, target_service, environment, json.dumps(parameters), now, now),
        )
        conn.commit()
    return get_request(request_id)


def get_request(request_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM operational_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def update_request(
    request_id: str,
    status: str,
    result: Optional[dict] = None,
    error: Optional[str] = None,
    duration_ms: Optional[float] = None,
) -> Optional[dict]:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE operational_requests
            SET status = ?, result = ?, error = ?, duration_ms = ?, updated_at = ?
            WHERE request_id = ?
            """,
            (
                status,
                json.dumps(result) if result else None,
                error,
                duration_ms,
                now,
                request_id,
            ),
        )
        conn.commit()
    return get_request(request_id)


def write_audit_log(request_id: str, event: str, details: Optional[dict] = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO audit_log (request_id, event, details, timestamp) VALUES (?, ?, ?, ?)",
            (request_id, event, json.dumps(details) if details else None, now),
        )
        conn.commit()


def count_requests_by_type() -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT request_type, COUNT(*) as cnt FROM operational_requests GROUP BY request_type"
        ).fetchall()
    return {r["request_type"]: r["cnt"] for r in rows}


def count_requests_by_env() -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT environment, COUNT(*) as cnt FROM operational_requests GROUP BY environment"
        ).fetchall()
    return {r["environment"]: r["cnt"] for r in rows}


def get_avg_duration() -> float:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT AVG(duration_ms) as avg FROM operational_requests WHERE duration_ms IS NOT NULL"
        ).fetchone()
    return round(row["avg"] or 0.0, 2)


def count_by_status() -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM operational_requests GROUP BY status"
        ).fetchall()
    return {r["status"]: r["cnt"] for r in rows}
