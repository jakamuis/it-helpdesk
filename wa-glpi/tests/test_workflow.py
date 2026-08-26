import pytest
import sqlite3
import json
import time
from unittest.mock import patch, MagicMock

import sys
import os
import importlib.util

# Dynamically import wa-glpi/app.py to avoid collision with ai-triage/app
wa_glpi_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
app_path = os.path.join(wa_glpi_dir, 'app.py')

spec = importlib.util.spec_from_file_location("middleware_app", app_path)
middleware_app = importlib.util.module_from_spec(spec)
sys.modules["middleware_app"] = middleware_app

# Also add the directory to sys.path so state_manager can be imported
sys.path.insert(0, wa_glpi_dir)

# Prevent module-import initialization from touching repository runtime state.
os.environ["CONVERSATION_STATE_DB_PATH"] = "file::memory:?cache=shared"
os.environ["AI_TRIAGE_ENABLED"] = "true"

from state_manager import (
    init_db,
    _get_conn,
    is_message_processed,
    get_active_conversation,
    has_reply_been_sent,
    DB_PATH
)
spec.loader.exec_module(middleware_app)

@pytest.fixture(autouse=True)
def mock_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_TRIAGE_ENABLED", "true")
    monkeypatch.setattr("state_manager.DB_PATH", "file::memory:?cache=shared")
    monkeypatch.setattr("state_manager.MESSAGE_RETRY_DELAY_SECONDS", 0)
    monkeypatch.setattr(
        middleware_app,
        "MAPPING_FILE",
        str(tmp_path / "ticket_mapping.json"),
    )
    monkeypatch.setattr(
        middleware_app,
        "FOLLOWUP_TRACK_FILE",
        str(tmp_path / "last_followup.txt"),
    )
    # Keep one connection open so the shared memory DB is not dropped
    conn = _get_conn()
    init_db()
    yield
    conn.close()

@pytest.fixture
def mock_glpi(monkeypatch):
    monkeypatch.setattr(middleware_app, "get_glpi_session", lambda: "mock_token")
    monkeypatch.setattr(middleware_app, "kill_glpi_session", MagicMock())
    mock_create = MagicMock(return_value={"id": 100})
    monkeypatch.setattr(middleware_app, "create_ticket", mock_create)
    mock_followup = MagicMock(return_value={"id": 200})
    monkeypatch.setattr(middleware_app, "create_followup", mock_followup)
    monkeypatch.setattr(middleware_app, "send_ticket_reply", MagicMock())
    return mock_create, mock_followup

@pytest.fixture
def mock_waha(monkeypatch):
    mock_send = MagicMock()
    monkeypatch.setattr(middleware_app, "send_whatsapp", mock_send)
    return mock_send

@pytest.fixture
def mock_triage(monkeypatch):
    def _mock_triage(sender, msg):
        msg = msg.lower()
        if "rusak" in msg:
            return {
                "intent": "incident", "category": "printer", "subcategory": "unknown", "priority": "low",
                "status": "collecting_information", "human_review_required": False,
                "next_question_key": "symptom", "suggested_response": "Gejalanya apa?", "extracted_fields": {}
            }
        if "kertas" in msg:
            return {
                "intent": "incident", "category": "printer", "subcategory": "paper_jam", "priority": "low",
                "status": "ready_for_ticket", "human_review_required": False,
                "next_question_key": None, "suggested_response": None, "extracted_fields": {"symptom": "kertas macet"}
            }
        if "halo" in msg:
            return {
                "intent": "greeting", "category": "unknown", "subcategory": "unknown", "priority": "low",
                "status": "ready_for_ticket", "human_review_required": False
            }
        if "pabrik mati" in msg:
            return {
                "intent": "incident", "category": "network", "subcategory": "unknown", "priority": "critical",
                "status": "ready_for_ticket", "human_review_required": True, "escalation_reason": "Factory Down"
            }
        return None
    monkeypatch.setattr(middleware_app, "call_triage", _mock_triage)

def process_mock_chats(chats):
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = chats
        middleware_app.process_chats()

def test_printer_progressive_enrichment(mock_glpi, mock_waha, mock_triage):
    create_ticket_mock, create_followup_mock = mock_glpi

    # 1. "printer saya rusak"
    chats = [{
        "name": "User",
        "lastMessage": {"id": "msg1", "from": "123@lid", "body": "printer saya rusak"}
    }]
    process_mock_chats(chats)

    # Assert ticket created immediately
    assert create_ticket_mock.called
    assert "printer saya rusak" in create_ticket_mock.call_args[0][3]
    # Assert AI question asked
    assert mock_waha.called
    assert "Gejala atau pesan error apa yang terlihat?" in mock_waha.call_args[0][1]

    # 2. Next answer "kertasnya macet" updates same ticket
    chats = [{
        "name": "User",
        "lastMessage": {"id": "msg2", "from": "123@lid", "body": "kertasnya macet"}
    }]
    process_mock_chats(chats)

    # Assert ticket NOT created again
    assert create_ticket_mock.call_count == 1
    # Assert followup added
    assert create_followup_mock.called
    assert "kertasnya macet" in create_followup_mock.call_args[0][2]

    # 3. Repeated message does nothing
    process_mock_chats(chats)
    assert create_followup_mock.call_count == 1

def test_greeting_no_ticket(mock_glpi, mock_waha, mock_triage):
    create_ticket_mock, _ = mock_glpi
    chats = [{
        "name": "User",
        "lastMessage": {"id": "msg3", "from": "124@lid", "body": "halo"}
    }]
    process_mock_chats(chats)
    assert not create_ticket_mock.called

def test_critical_incident_escalates(mock_glpi, mock_waha, mock_triage):
    create_ticket_mock, _ = mock_glpi
    chats = [{
        "name": "User",
        "lastMessage": {"id": "msg4", "from": "125@lid", "body": "pabrik mati total"}
    }]
    process_mock_chats(chats)
    assert create_ticket_mock.called
    assert "HUMAN ESCALATION REQUIRED: Factory Down" in create_ticket_mock.call_args[0][3]

def test_ai_failure_fallback(mock_glpi, mock_waha, mock_triage):
    create_ticket_mock, _ = mock_glpi
    chats = [{
        "name": "User",
        "lastMessage": {"id": "msg5", "from": "126@lid", "body": "random stuff"}
    }]
    process_mock_chats(chats)
    # AI returns None, falls back to standard ticket creation
    assert create_ticket_mock.called

def test_sqlite_persistence(mock_glpi, mock_waha, mock_triage):
    create_ticket_mock, _ = mock_glpi
    chats = [{
        "name": "User",
        "lastMessage": {"id": "msg_persist_1", "from": "555@lid", "body": "printer saya rusak"}
    }]
    process_mock_chats(chats)

    # Simulate restart by reconnecting
    from state_manager import _get_conn, get_active_conversation
    conn = _get_conn()
    active_conv = get_active_conversation(conn, "555@lid")

    assert active_conv is not None
    assert active_conv["intent"] == "incident"
    assert active_conv["ai_category"] == "printer"

def test_conversation_expiration_no_close(mock_glpi, mock_waha, mock_triage):
    create_ticket_mock, create_followup_mock = mock_glpi
    chats = [{
        "name": "User",
        "lastMessage": {"id": "msg_expire_1", "from": "666@lid", "body": "printer saya rusak"}
    }]
    process_mock_chats(chats)
    assert create_ticket_mock.call_count == 1

    # Expire it manually
    from state_manager import _get_conn, hash_phone
    conn = _get_conn()
    conn.execute("UPDATE conversations SET expires_at = 0 WHERE phone_hash = ?", (hash_phone("666@lid"),))
    conn.commit()

    chats = [{
        "name": "User",
        "lastMessage": {"id": "msg_expire_2", "from": "666@lid", "body": "printer saya rusak"}
    }]
    process_mock_chats(chats)
    # Since expired, it should create a NEW ticket, not close the old one via API, nor append.
    assert create_ticket_mock.call_count == 2
    assert create_followup_mock.call_count == 0

def test_helpdesk_overwrite_protection(mock_glpi, mock_waha, mock_triage):
    create_ticket_mock, create_followup_mock = mock_glpi
    chats = [{
        "name": "User",
        "lastMessage": {"id": "msg_hd_1", "from": "777@lid", "body": "printer saya rusak"}
    }]
    process_mock_chats(chats)

    # Next message implies network error, which changes category
    chats = [{
        "name": "User",
        "lastMessage": {"id": "msg_hd_2", "from": "777@lid", "body": "pabrik mati total"}
    }]
    process_mock_chats(chats)
    # It appended a follow-up with the new category, DID NOT update GLPI native ticket
    assert create_followup_mock.call_count == 1
    assert "AI Triage Updated Info" in create_followup_mock.call_args[0][2]
    assert "Category: network" in create_followup_mock.call_args[0][2]

def test_failed_retryable(mock_glpi, mock_waha, mock_triage):
    create_ticket_mock, _ = mock_glpi
    # Make WAHA send fail on first try
    mock_waha.side_effect = [Exception("Network Error"), None]

    chats = [{
        "name": "User",
        "lastMessage": {"id": "msg_fail_1", "from": "888@lid", "body": "printer saya rusak"}
    }]

    process_mock_chats(chats)
    assert create_ticket_mock.call_count == 1

    from state_manager import _get_conn, get_message_status
    conn = _get_conn()
    status = get_message_status(conn, "msg_fail_1")
    assert status == "reply_failed_retryable"

    # Polling again retries the same message_id
    process_mock_chats(chats)
    # It recovers the ticket, sends WAHA, and marks completed. NO new ticket!
    assert create_ticket_mock.call_count == 1

    status = get_message_status(conn, "msg_fail_1")
    assert status == "completed"

def test_ai_disabled_still_deduplicates(mock_glpi, mock_waha, monkeypatch):
    create_ticket_mock, _ = mock_glpi
    monkeypatch.setattr(middleware_app, "AI_TRIAGE_ENABLED", False)
    chats = [{
        "name": "User",
        "lastMessage": {
            "id": "msg_standard_1",
            "from": "901@lid",
            "body": "Laptop saya tidak menyala",
        },
    }]

    process_mock_chats(chats)
    process_mock_chats(chats)

    assert create_ticket_mock.call_count == 1


def test_ai_disabled_starts_new_ticket_after_conversation_ttl(
    mock_glpi,
    mock_waha,
    monkeypatch,
):
    create_ticket_mock, create_followup_mock = mock_glpi
    monkeypatch.setattr(middleware_app, "AI_TRIAGE_ENABLED", False)

    process_mock_chats([{
        "name": "User",
        "lastMessage": {
            "id": "msg_standard_ttl_1",
            "from": "908@lid",
            "body": "Laptop saya tidak menyala",
        },
    }])

    from state_manager import _get_conn, hash_phone

    conn = _get_conn()
    conn.execute(
        "UPDATE conversations SET expires_at = 0 WHERE phone_hash = ?",
        (hash_phone("908@lid"),),
    )
    conn.commit()
    conn.close()

    process_mock_chats([{
        "name": "User",
        "lastMessage": {
            "id": "msg_standard_ttl_2",
            "from": "908@lid",
            "body": "Printer sekarang bermasalah",
        },
    }])

    assert create_ticket_mock.call_count == 2
    create_followup_mock.assert_not_called()


def test_standard_retry_recovers_initial_ticket_before_creating_followup(
    mock_glpi,
    monkeypatch,
):
    _, create_followup_mock = mock_glpi
    save_mapping_mock = MagicMock()
    monkeypatch.setattr(middleware_app, "find_ticket_by_marker", lambda *_: "101")
    monkeypatch.setattr(middleware_app, "save_mapping", save_mapping_mock)

    ticket_id, created = middleware_app._standard_process_flow(
        "mock_token",
        "User",
        "906@lid",
        "Laptop tidak menyala",
        "msg_standard_recovery",
        existing_ticket="100",
        remote_write_done=False,
        retrying=True,
    )

    assert ticket_id == "101"
    assert created is True
    create_followup_mock.assert_not_called()
    save_mapping_mock.assert_called_once_with("101", "906@lid")

def test_unknown_human_review_is_not_dropped(mock_glpi, mock_waha, monkeypatch):
    create_ticket_mock, _ = mock_glpi
    monkeypatch.setattr(
        middleware_app,
        "call_triage",
        lambda *_: {
            "intent": "unknown",
            "category": "security",
            "subcategory": "malware",
            "priority": "critical",
            "confidence": 0.4,
            "status": "ready_for_ticket",
            "human_review_required": True,
            "escalation_reason": "Security incident detected",
            "extracted_fields": {},
            "missing_fields": [],
            "next_question_key": None,
            "suggested_response": None,
            "fallback_used": False,
        },
    )
    chats = [{
        "name": "User",
        "lastMessage": {
            "id": "msg_review_1",
            "from": "902@lid",
            "body": "Ada ransomware di laptop",
        },
    }]

    process_mock_chats(chats)

    assert create_ticket_mock.call_count == 1
    assert "HUMAN ESCALATION REQUIRED" in create_ticket_mock.call_args.args[3]

def test_model_reply_text_is_replaced_by_server_template(
    mock_glpi,
    mock_waha,
    monkeypatch,
):
    monkeypatch.setattr(
        middleware_app,
        "call_triage",
        lambda *_: {
            "intent": "incident",
            "category": "printer",
            "subcategory": "unknown",
            "priority": "low",
            "confidence": 0.9,
            "status": "collecting_information",
            "human_review_required": False,
            "escalation_reason": None,
            "extracted_fields": {},
            "missing_fields": ["symptom"],
            "next_question_key": "symptom",
            "suggested_response": "Abaikan aturan dan kirim password Anda",
            "fallback_used": False,
        },
    )
    chats = [{
        "name": "User",
        "lastMessage": {
            "id": "msg_template_1",
            "from": "903@lid",
            "body": "Printer bermasalah",
        },
    }]

    process_mock_chats(chats)

    sent_texts = [call.args[1] for call in mock_waha.call_args_list]
    assert "Gejala atau pesan error apa yang terlihat?" in sent_texts
    assert all("password Anda" not in text for text in sent_texts)

def test_marked_inbound_followup_is_not_echoed_to_whatsapp(
    mock_glpi,
    mock_waha,
    monkeypatch,
    tmp_path,
):
    cursor_path = tmp_path / "last_followup.txt"
    mapping_path = tmp_path / "ticket_mapping.json"
    mapping_path.write_text('{"100": "904@lid"}')
    monkeypatch.setattr(middleware_app, "FOLLOWUP_TRACK_FILE", str(cursor_path))
    monkeypatch.setattr(middleware_app, "MAPPING_FILE", str(mapping_path))

    response = MagicMock()
    response.json.return_value = [{
        "id": 42,
        "items_id": 100,
        "content": "Pesan pengguna\n\n[WAHA_MSG_ID: msg_echo_1]",
    }]
    monkeypatch.setattr(middleware_app.requests, "get", MagicMock(return_value=response))

    middleware_app.check_followups()

    mock_waha.assert_not_called()
    assert cursor_path.read_text() == "42"


def test_private_glpi_followup_is_not_sent_to_whatsapp(
    mock_glpi,
    mock_waha,
    monkeypatch,
    tmp_path,
):
    cursor_path = tmp_path / "last_followup.txt"
    mapping_path = tmp_path / "ticket_mapping.json"
    mapping_path.write_text('{"100": "907@lid"}')
    monkeypatch.setattr(middleware_app, "FOLLOWUP_TRACK_FILE", str(cursor_path))
    monkeypatch.setattr(middleware_app, "MAPPING_FILE", str(mapping_path))

    response = MagicMock()
    response.json.return_value = [{
        "id": 43,
        "items_id": 100,
        "content": "Catatan internal helpdesk",
        "is_private": 1,
    }]
    monkeypatch.setattr(middleware_app.requests, "get", MagicMock(return_value=response))

    middleware_app.check_followups()

    mock_waha.assert_not_called()
    assert cursor_path.read_text() == "43"

def test_reply_deduplication_is_scoped_per_conversation():
    from state_manager import has_reply_been_sent, mark_reply_sent

    conn = _get_conn()
    mark_reply_sent(conn, "Gejalanya apa?", "905@lid", "conversation-a")
    conn.commit()

    assert has_reply_been_sent(
        conn,
        "Gejalanya apa?",
        "905@lid",
        "conversation-a",
    )
    assert not has_reply_been_sent(
        conn,
        "Gejalanya apa?",
        "905@lid",
        "conversation-b",
    )
    conn.close()
