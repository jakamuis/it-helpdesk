import importlib.util
import sqlite3
from pathlib import Path
from unittest.mock import Mock
import pytest

spec = importlib.util.spec_from_file_location('request_notifier', Path(__file__).parents[1] / 'request_notifier.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

@pytest.fixture
def bridge(tmp_path, monkeypatch):
    monkeypatch.setenv('ITREQUEST_FEED_URL', 'https://example.test/plugins/itrequest/front/wa-feed.php')
    monkeypatch.setenv('ITREQUEST_BRIDGE_TOKEN', 'a' * 32)
    notifier = mod.RequestNotifier()
    connect = lambda: sqlite3.connect(tmp_path / 'state.db')
    feed = Mock()
    monkeypatch.setattr(mod.requests, 'get', feed)
    return notifier, connect, feed

def event(n):
    return {'id': n, 'reference': 'REQ-2026-000001', 'action': 'finish', 'chat_id': '628123456789@c.us'}

def response(feed, events, cursor, more=False):
    feed.return_value.json.return_value = {'events': events, 'cursor': cursor, 'has_more': more}

def test_baseline_retry_and_no_replay(bridge):
    n, connect, feed = bridge
    send = Mock(return_value=None)  # Existing send_whatsapp returns None after HTTP success.
    response(feed, [event(1)], 1)
    n.poll(connect, send)
    send.assert_not_called()
    response(feed, [event(2), event(3)], 3)
    send.side_effect = [None, RuntimeError('offline')]
    with pytest.raises(RuntimeError): n.poll(connect, send)
    with connect() as db: assert db.execute('SELECT cursor FROM request_feed_cursor').fetchone()[0] == 2
    send.reset_mock(side_effect=True)
    response(feed, [event(3)], 3)
    n.poll(connect, send)
    send.assert_called_once()
    assert feed.call_args.kwargs['params'] == {'after': 2}

def test_full_page_baseline(bridge):
    n, connect, feed = bridge
    send = Mock()
    response(feed, [event(1)], 1, True)
    n.poll(connect, send)
    response(feed, [event(2)], 2)
    n.poll(connect, send)
    send.assert_not_called()

def test_invalid_recipient_stops_before_send(bridge):
    n, connect, feed = bridge
    response(feed, [], 0)
    n.poll(connect, Mock())
    bad = event(2); bad['chat_id'] = 'group@g.us'
    response(feed, [event(1), bad], 2)
    send = Mock()
    with pytest.raises(ValueError): n.poll(connect, send)
    send.assert_not_called()

def test_disabled_and_https(monkeypatch):
    monkeypatch.delenv('ITREQUEST_FEED_URL', raising=False)
    monkeypatch.delenv('ITREQUEST_BRIDGE_TOKEN', raising=False)
    mod.RequestNotifier().poll(Mock(side_effect=AssertionError), Mock())
    monkeypatch.setenv('ITREQUEST_FEED_URL', 'http://example.test')
    monkeypatch.setenv('ITREQUEST_BRIDGE_TOKEN', 'a' * 32)
    with pytest.raises(ValueError): mod.RequestNotifier().poll(Mock(), Mock())
