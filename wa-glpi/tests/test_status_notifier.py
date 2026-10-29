import sqlite3
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from status_notifier import StatusNotifier


@pytest.fixture
def state():
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE ticket_status_notifications (
        ticket_id TEXT PRIMARY KEY, status INTEGER NOT NULL,
        revision INTEGER NOT NULL, pending_revision INTEGER)""")
    yield conn
    conn.close()


def test_only_solved_transition_notifies_once_and_survives_new_notifier(state):
    send = Mock()
    for status in [1, 2, 3, 4]:
        StatusNotifier.observe(state, "16", status, "requester@lid", send)
    send.assert_not_called()
    StatusNotifier.observe(state, "16", 5, "requester@lid", send)
    StatusNotifier().observe(state, "16", 5, "requester@lid", send)
    assert send.call_count == 1
    assert send.call_args.args[0] == "requester@lid"
    assert "#16" in send.call_args.args[1]
    assert "Solved" in send.call_args.args[1]
    StatusNotifier.observe(state, "16", 6, "requester@lid", send)
    assert send.call_count == 1


def test_historical_solved_ticket_is_baselined_without_notification(state):
    send = Mock()
    StatusNotifier.observe(state, "9", 5, "requester@lid", send)
    send.assert_not_called()


def test_failed_send_retries_and_reopened_ticket_can_be_solved_again(state):
    send = Mock(side_effect=[RuntimeError("WAHA unavailable"), None, None])
    StatusNotifier.observe(state, "16", 2, "requester@lid", send)
    with pytest.raises(RuntimeError):
        StatusNotifier.observe(state, "16", 5, "requester@lid", send)
    assert state.execute("SELECT pending_revision FROM ticket_status_notifications").fetchone()[0] == 1
    StatusNotifier.observe(state, "16", 5, "requester@lid", send)
    StatusNotifier.observe(state, "16", 5, "requester@lid", send)
    assert send.call_count == 2
    StatusNotifier.observe(state, "16", 2, "requester@lid", send)
    StatusNotifier.observe(state, "16", 5, "requester@lid", send)
    assert send.call_count == 3


def test_pending_solved_notification_cancels_when_ticket_reopens(state):
    send = Mock(side_effect=RuntimeError("offline"))
    StatusNotifier.observe(state, "16", 2, "requester@lid", send)
    with pytest.raises(RuntimeError):
        StatusNotifier.observe(state, "16", 5, "requester@lid", send)
    send.reset_mock(side_effect=True)
    StatusNotifier.observe(state, "16", 2, "requester@lid", send)
    send.assert_not_called()


def test_poll_isolates_ticket_failure_and_uses_verified_tls(tmp_path, monkeypatch):
    import status_notifier
    mapping = tmp_path / "mapping.json"
    mapping.write_text('{"16":"first@lid", "17":"second@lid"}')
    db = tmp_path / "state.db"
    connect = lambda: sqlite3.connect(db)
    response = Mock()
    response.json.return_value = {"status": 2}
    get = Mock(return_value=response)
    monkeypatch.setattr(status_notifier.requests, "get", get)
    notifier = StatusNotifier(interval=0)
    send, cleanup = Mock(), Mock()
    args = (str(mapping), connect, lambda: "session", cleanup,
            "https://glpi.example/apirest.php", "app", 15, send)
    notifier.poll(*args)
    response.json.return_value = {"status": 5}
    send.side_effect = [RuntimeError("temporary"), None, None]
    notifier.poll(*args)
    assert send.call_count == 2  # Failure for first requester does not block second.
    notifier.poll(*args)
    assert send.call_count == 3  # Only the failed notification is retried.
    assert get.call_args.kwargs["verify"] is True
    assert cleanup.call_count == 3
