import sqlite3
import json
import time
import os
import hashlib

DB_PATH = os.getenv("CONVERSATION_STATE_DB_PATH", "./data/conversation_state.db")
CONVERSATION_TTL_SECONDS = int(os.getenv("CONVERSATION_STATE_TTL_SECONDS", "86400"))
MESSAGE_RETRY_DELAY_SECONDS = int(os.getenv("MESSAGE_RETRY_DELAY_SECONDS", "30"))

_CONVERSATION_UPDATE_FIELDS = {
    "glpi_ticket_id",
    "status",
    "intent",
    "ai_category",
    "ai_subcategory",
    "ai_priority",
    "collected_fields",
    "questions_asked",
    "expires_at",
}

def _get_conn():
    global DB_PATH
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
        except OSError:
            db_dir = "./data"
            os.makedirs(db_dir, exist_ok=True)
            DB_PATH = os.path.join(db_dir, "conversation_state.db")

    conn = sqlite3.connect(
        DB_PATH,
        timeout=5,
        uri=DB_PATH.startswith("file:"),
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn

def init_db(memory_conn=None):
    if memory_conn:
        conn = memory_conn
    else:
        conn = _get_conn()

    with conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                phone_hash TEXT NOT NULL,
                glpi_ticket_id TEXT,
                status TEXT,
                intent TEXT,
                ai_category TEXT,
                ai_subcategory TEXT,
                ai_priority TEXT,
                collected_fields TEXT,
                questions_asked TEXT,
                created_at REAL,
                updated_at REAL,
                expires_at REAL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT PRIMARY KEY,
                phone_hash TEXT,
                status TEXT,
                processed_at REAL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS outbound_replies (
                reply_hash TEXT PRIMARY KEY,
                sent_at REAL
            )
        ''')
    if not memory_conn:
        conn.close()
        if DB_PATH not in {":memory:", ""} and not DB_PATH.startswith("file:"):
            try:
                os.chmod(DB_PATH, 0o600)
            except OSError:
                pass

def hash_phone(phone: str) -> str:
    return hashlib.sha256(phone.encode()).hexdigest()

def is_message_processed(conn, message_id: str) -> bool:
    cursor = conn.execute("SELECT status FROM processed_messages WHERE message_id = ?", (message_id,))
    row = cursor.fetchone()
    if row:
        return row[0] == "completed"
    return False

def get_message_status(conn, message_id: str) -> str:
    cursor = conn.execute("SELECT status FROM processed_messages WHERE message_id = ?", (message_id,))
    row = cursor.fetchone()
    return row[0] if row else None

def is_message_retry_due(conn, message_id: str, retry_delay: int = None) -> bool:
    """Return False while a failed message is inside its retry backoff window."""
    delay = MESSAGE_RETRY_DELAY_SECONDS if retry_delay is None else retry_delay
    cursor = conn.execute(
        "SELECT status, processed_at FROM processed_messages WHERE message_id = ?",
        (message_id,),
    )
    row = cursor.fetchone()
    if not row or not str(row[0]).endswith("failed_retryable"):
        return True
    return float(row[1] or 0) + max(delay, 0) <= time.time()

def set_message_status(conn, message_id: str, phone: str, status: str):
    conn.execute(
        "INSERT INTO processed_messages (message_id, phone_hash, status, processed_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(message_id) DO UPDATE SET status=excluded.status, processed_at=excluded.processed_at",
        (message_id, hash_phone(phone), status, time.time())
    )

def mark_message_processed(conn, message_id: str, phone: str):
    set_message_status(conn, message_id, phone, "completed")

def _reply_hash(reply_text: str, phone: str, scope: str = "") -> str:
    return hashlib.sha256(f"{scope}:{phone}:{reply_text}".encode()).hexdigest()

def has_reply_been_sent(conn, reply_text: str, phone: str, scope: str = "") -> bool:
    reply_hash = _reply_hash(reply_text, phone, scope)
    cursor = conn.execute("SELECT 1 FROM outbound_replies WHERE reply_hash = ?", (reply_hash,))
    return cursor.fetchone() is not None

def mark_reply_sent(conn, reply_text: str, phone: str, scope: str = ""):
    reply_hash = _reply_hash(reply_text, phone, scope)
    conn.execute(
        "INSERT OR IGNORE INTO outbound_replies (reply_hash, sent_at) VALUES (?, ?)",
        (reply_hash, time.time())
    )

def get_active_conversation(conn, phone: str):
    p_hash = hash_phone(phone)
    now = time.time()
    cursor = conn.execute(
        "SELECT * FROM conversations WHERE phone_hash = ? AND expires_at > ? ORDER BY updated_at DESC LIMIT 1",
        (p_hash, now)
    )
    row = cursor.fetchone()
    if not row:
        return None
    return dict(row)

def create_conversation(conn, phone: str, ticket_id: str, status: str, ttl: int = None):
    p_hash = hash_phone(phone)
    conv_id = f"conv_{time.time_ns()}_{p_hash[:8]}"
    now = time.time()
    effective_ttl = CONVERSATION_TTL_SECONDS if ttl is None else ttl
    conn.execute(
        '''INSERT INTO conversations
           (conversation_id, phone_hash, glpi_ticket_id, status, created_at, updated_at, expires_at, collected_fields, questions_asked)
           VALUES (?, ?, ?, ?, ?, ?, ?, '{}', '[]')''',
        (conv_id, p_hash, str(ticket_id), status, now, now, now + effective_ttl)
    )
    return conv_id

def update_conversation(conn, conv_id: str, updates: dict):
    unknown_fields = set(updates) - _CONVERSATION_UPDATE_FIELDS
    if unknown_fields:
        raise ValueError(f"Unsupported conversation fields: {sorted(unknown_fields)}")

    updates = dict(updates)
    for k in ["collected_fields", "questions_asked"]:
        if k in updates and not isinstance(updates[k], str):
            updates[k] = json.dumps(updates[k])

    updates["updated_at"] = time.time()

    set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [conv_id]

    conn.execute(f"UPDATE conversations SET {set_clause} WHERE conversation_id = ?", values)
