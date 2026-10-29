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


@pytest.mark.parametrize("finished_status", [5, 6])
def test_finished_ticket_starts_fresh_before_ai_reads_context(
    mock_glpi, mock_waha, mock_triage, monkeypatch, finished_status,
):
    create, followup = mock_glpi
    sender = f"finished-{finished_status}@lid"
    middleware_app._process_chat_message("User", sender, "printer rusak", f"old-{finished_status}")
    create.return_value = {"id": 101}
    monkeypatch.setattr(middleware_app, "get_ticket_status", lambda *a: finished_status)
    def fresh_triage(phone, message):
        conn = _get_conn()
        try:
            assert get_active_conversation(conn, phone) is None
        finally:
            conn.close()
        return {
            "intent": "incident", "category": "network", "priority": "low",
            "status": "collecting_information", "human_review_required": False,
            "next_question_key": "site", "extracted_fields": {},
        }
    monkeypatch.setattr(middleware_app, "call_triage", fresh_triage)
    middleware_app._process_chat_message("User", sender, "internet lambat", f"new-{finished_status}")
    assert create.call_count == 2
    followup.assert_not_called()
    conn = _get_conn()
    try:
        assert get_active_conversation(conn, sender)["glpi_ticket_id"] == "101"
    finally:
        conn.close()


def test_ready_confirmation_retries_failed_send_and_is_not_repeated(mock_waha):
    conn = _get_conn()
    response = {"status": "ready_for_ticket", "human_review_required": False}
    mock_waha.side_effect = RuntimeError("temporary send failure")
    with pytest.raises(RuntimeError):
        middleware_app._send_triage_ready_once(conn, "ready@lid", "100", "ready-conv", response)
    mock_waha.side_effect = None
    middleware_app._send_triage_ready_once(conn, "ready@lid", "100", "ready-conv", response)
    middleware_app._send_triage_ready_once(conn, "ready@lid", "100", "ready-conv", response)
    assert mock_waha.call_count == 2
    assert "#100" in mock_waha.call_args.args[1]
    assert "sudah lengkap" in mock_waha.call_args.args[1]
    conn.close()


def test_followups_pagination_honors_actual_page_size(monkeypatch):
    first, second = MagicMock(), MagicMock()
    first.json.return_value = [{"id": 1}, {"id": 2}]
    first.headers = {"Content-Range": "0-1/3"}
    second.json.return_value = [{"id": 105}]
    second.headers = {"Content-Range": "2-2/3"}
    get = MagicMock(side_effect=[first, second])
    monkeypatch.setattr(middleware_app.requests, "get", get)
    assert [x["id"] for x in middleware_app.get_all_followups("session")] == [1, 2, 105]
    assert get.call_args_list[1].kwargs["params"]["range"] == "2-101"
    assert get.call_args.kwargs["verify"] is True


def test_followups_partial_send_failure_does_not_duplicate_success(
    mock_glpi, mock_waha, monkeypatch, tmp_path,
):
    (tmp_path / "ticket_mapping.json").write_text('{"18":"requester@lid"}')
    rows = [
        {"id": 103, "items_id": 18, "itemtype": "Ticket", "content": "<p>First &amp; reply</p>", "is_private": 0},
        {"id": 104, "items_id": 18, "itemtype": "Problem", "content": "Never send", "is_private": 0},
        {"id": 105, "items_id": 18, "itemtype": "Ticket", "content": "Second reply", "is_private": 0},
    ]
    monkeypatch.setattr(middleware_app, "get_all_followups", lambda *_: rows)
    mock_waha.side_effect = [None, RuntimeError("offline"), None]
    with pytest.raises(RuntimeError):
        middleware_app.check_followups()
    middleware_app.check_followups()
    middleware_app.check_followups()
    assert mock_waha.call_count == 3
    assert mock_waha.call_args_list[0].args[1] == "📌 Update Ticket #18\nFirst & reply"
    assert (tmp_path / "last_followup.txt").read_text() == "105"


def test_followups_pagination_failure_keeps_cursor_and_sends_nothing(
    mock_glpi, mock_waha, monkeypatch, tmp_path,
):
    (tmp_path / "last_followup.txt").write_text("15")
    first = MagicMock()
    first.json.return_value = [{"id": 103, "items_id": 18, "content": "reply"}]
    first.headers = {"Content-Range": "0-0/2"}
    monkeypatch.setattr(middleware_app.requests, "get", MagicMock(side_effect=[first, RuntimeError("page failed")]))
    with pytest.raises(RuntimeError):
        middleware_app.check_followups()
    mock_waha.assert_not_called()
    assert (tmp_path / "last_followup.txt").read_text() == "15"


def test_welcome_is_fast_persistent_and_does_not_create_ticket(
    mock_glpi, mock_waha, monkeypatch,
):
    ai = MagicMock(side_effect=AssertionError("Greeting must not call AI"))
    glpi = MagicMock(side_effect=AssertionError("Greeting must not call GLPI"))
    monkeypatch.setattr(middleware_app, "call_triage", ai)
    monkeypatch.setattr(middleware_app, "get_glpi_session", glpi)
    middleware_app._process_chat_message("User", "welcome@lid", "HI 👋", "welcome-1")
    middleware_app._process_chat_message("User", "welcome@lid", "halo", "welcome-2")
    middleware_app._process_chat_message("User", "welcome@lid", "HI 👋", "welcome-1")
    assert mock_waha.call_count == 1
    assert "Selamat datang" in mock_waha.call_args.args[1]
    mock_glpi[0].assert_not_called()
    conn = _get_conn()
    try:
        conn.execute("UPDATE welcome_replies SET sent_at=sent_at-601")
        conn.commit()
    finally:
        conn.close()
    middleware_app._process_chat_message("User", "welcome@lid", "hello", "welcome-3")
    assert mock_waha.call_count == 2


def test_welcome_send_failure_retries_without_losing_message(
    mock_glpi, mock_waha, monkeypatch,
):
    monkeypatch.setattr("state_manager.MESSAGE_RETRY_DELAY_SECONDS", 0)
    mock_waha.side_effect = [RuntimeError("offline"), None]
    middleware_app._process_chat_message("User", "welcome-retry@lid", "hi", "welcome-retry")
    conn = _get_conn()
    assert middleware_app.get_message_status(conn, "welcome-retry") == "failed_retryable"
    middleware_app._process_chat_message("User", "welcome-retry@lid", "hi", "welcome-retry")
    assert middleware_app.get_message_status(conn, "welcome-retry") == "completed"
    assert mock_waha.call_count == 2
    conn.close()


def test_greeting_during_active_ticket_preserves_triage_context(
    mock_glpi, mock_waha, mock_triage,
):
    sender = "welcome-active@lid"
    middleware_app._process_chat_message("User", sender, "printer rusak", "before-hi")
    conn = _get_conn()
    before = get_active_conversation(conn, sender)
    middleware_app._process_chat_message("User", sender, "Hi", "active-hi")
    after = get_active_conversation(conn, sender)
    assert before == after
    assert mock_glpi[0].call_count == 1
    mock_glpi[1].assert_not_called()
    assert not middleware_app._is_greeting("halo printer rusak")
    conn.close()

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
    monkeypatch.setattr(middleware_app, "get_ticket_status", lambda *args: 2)
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
        session_response = MagicMock()
        session_response.json.return_value = {"status": "WORKING"}
        chats_response = MagicMock()
        chats_response.json.return_value = chats
        mock_get.side_effect = [session_response, chats_response]
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


@pytest.mark.parametrize("session_status", ["SCAN_QR_CODE", "STOPPED", "FAILED"])
def test_chat_polling_waits_for_working_waha_session(session_status):
    response = MagicMock()
    response.json.return_value = {"status": session_status}
    with patch("requests.get", return_value=response) as get:
        middleware_app.process_chats()
    assert get.call_count == 1
    assert get.call_args.args[0].endswith("/api/sessions/default")
