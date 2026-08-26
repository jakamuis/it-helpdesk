import hashlib
import os
import sqlite3
import time
from typing import Optional

from .config import settings


AUDIT_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL,
        conversation_id_hash TEXT,
        message_hash TEXT,
        ai_intent TEXT,
        ai_category TEXT,
        ai_subcategory TEXT,
        ai_priority TEXT,
        ai_confidence REAL,
        human_review_required INTEGER,
        escalation_reason TEXT,
        model TEXT,
        fallback_used INTEGER,
        latency_ms INTEGER
    )
"""


def _prepare_db_path(db_path: str) -> None:
    if db_path != ":memory:":
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)


def _secure_db_file(db_path: str) -> None:
    if db_path == ":memory:":
        return
    try:
        os.chmod(db_path, 0o600)
    except OSError:
        pass


def init_db(db_path: Optional[str] = None) -> None:
    resolved_path = db_path or settings.ai_audit_db_path
    _prepare_db_path(resolved_path)
    with sqlite3.connect(resolved_path, timeout=5) as conn:
        conn.execute(AUDIT_TABLE_SQL)
    _secure_db_file(resolved_path)


def log_prediction(
    conversation_id: str,
    message: str,
    response: dict,
    latency_ms: int,
) -> bool:
    try:
        db_path = settings.ai_audit_db_path
        _prepare_db_path(db_path)
        conv_hash = hashlib.sha256(conversation_id.encode()).hexdigest()
        msg_hash = hashlib.sha256(message.encode()).hexdigest()

        with sqlite3.connect(db_path, timeout=5) as conn:
            # Keeping schema creation on the same connection makes even :memory:
            # safe and avoids import-time filesystem side effects.
            conn.execute(AUDIT_TABLE_SQL)
            conn.execute(
                """
                INSERT INTO audit_log (
                    timestamp, conversation_id_hash, message_hash, ai_intent,
                    ai_category, ai_subcategory, ai_priority, ai_confidence,
                    human_review_required, escalation_reason, model, fallback_used,
                    latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    conv_hash,
                    msg_hash,
                    response.get("intent"),
                    response.get("category"),
                    response.get("subcategory"),
                    response.get("priority"),
                    response.get("confidence"),
                    1 if response.get("human_review_required") else 0,
                    response.get("escalation_reason"),
                    response.get("model"),
                    1 if response.get("fallback_used") else 0,
                    latency_ms,
                ),
            )
        _secure_db_file(db_path)
        return True
    except (OSError, sqlite3.Error) as exc:
        print(f"Error logging to audit DB: {exc}")
        return False
