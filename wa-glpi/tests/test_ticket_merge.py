import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ticket_merge import sync_merges
from status_notifier import StatusNotifier


@pytest.fixture
def setup(tmp_path):
    path = str(tmp_path / 'mapping.json')
    Path(path).write_text(json.dumps({'101': 'user-a', '100': 'user-b'}))
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE conversations (glpi_ticket_id TEXT)')
    conn.execute("INSERT INTO conversations VALUES ('101')")
    sent = set()
    seen = lambda conn, message, chat, scope: (chat, scope) in sent
    mark = lambda conn, message, chat, scope: sent.add((chat, scope))
    yield path, conn, seen, mark
    conn.close()


def api(endpoint, params=None):
    if endpoint.endswith('/Ticket_Ticket'):
        return ([{'tickets_id_1': 101, 'tickets_id_2': 100, 'link': 3}]
                if params['range'].startswith('0-') else [])
    return {'is_deleted': int(endpoint == 'Ticket/101')}


def test_merge_transfers_subscribers_conversation_and_retries_notice(setup):
    path, conn, seen, mark = setup
    send = Mock(side_effect=RuntimeError('offline'))
    sync_merges(path, conn, api, send, seen, mark)
    assert json.loads(Path(path).read_text()) == {'100': ['user-b', 'user-a']}
    assert conn.execute('SELECT glpi_ticket_id FROM conversations').fetchone()[0] == '100'
    send.side_effect = None
    sync_merges(path, conn, api, send, seen, mark)
    sync_merges(path, conn, api, send, seen, mark)
    assert send.call_count == 2
    assert '#101' in send.call_args.args[1] and '#100' in send.call_args.args[1]


@pytest.mark.parametrize('deleted,link', [(0, 3), (1, 1), (1, 2)])
def test_related_or_deleted_without_merge_is_not_redirected(setup, deleted, link):
    path, conn, seen, mark = setup
    def get(endpoint, params=None):
        if endpoint.endswith('/Ticket_Ticket'):
            return ([{'tickets_id_1': 101, 'tickets_id_2': 100, 'link': link}]
                    if params['range'].startswith('0-') else [])
        return {'is_deleted': deleted if endpoint == 'Ticket/101' else 0}
    send = Mock()
    sync_merges(path, conn, get, send, seen, mark)
    assert json.loads(Path(path).read_text())['101'] == 'user-a'
    send.assert_not_called()


def test_solved_fanout_retries_only_failed_recipient():
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE ticket_status_notifications (ticket_id TEXT PRIMARY KEY, '
                 'status INTEGER, revision INTEGER, pending_revision INTEGER)')
    send = Mock()
    StatusNotifier.observe(conn, '100', 2, ['user-a', 'user-b'], send)
    send.side_effect = [RuntimeError('offline'), None]
    with pytest.raises(RuntimeError):
        StatusNotifier.observe(conn, '100', 5, ['user-a', 'user-b'], send)
    send.side_effect = None
    StatusNotifier.observe(conn, '100', 5, ['user-a', 'user-b'], send)
    assert [call.args[0] for call in send.call_args_list] == ['user-a', 'user-b', 'user-a']
    conn.close()
