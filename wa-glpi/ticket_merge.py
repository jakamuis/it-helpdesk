"""Keep WhatsApp subscribers and conversations attached after GLPI ticket merges."""
import json
import os

import requests


def recipients(value):
    values = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    return list(dict.fromkeys(v for v in values if isinstance(v, str) and v))


def read_mapping(path):
    try:
        with open(path) as source:
            value = json.load(source)
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Invalid ticket mapping")
    return value


def write_mapping(path, mapping):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path + '.tmp', 'w') as target:
        json.dump(mapping, target, indent=4)
    os.replace(path + '.tmp', path)


def sync_merges(path, conn, get, send, seen, mark):
    """Journal transfers before changing JSON, so interrupted transfers are replayable."""
    conn.execute('''CREATE TABLE IF NOT EXISTS ticket_merge_transfers (
        source TEXT PRIMARY KEY, target TEXT NOT NULL, recipients TEXT NOT NULL,
        applied INTEGER NOT NULL DEFAULT 0)''')
    conn.commit()
    mapping = read_mapping(path)

    def resolve(source):
        current, visited = source, set()
        while current not in visited:
            visited.add(current)
            ticket = get(f'Ticket/{current}')
            if not isinstance(ticket, dict):
                raise ValueError('Invalid ticket response')
            if str(ticket.get('is_deleted', 0)) != '1':
                return current
            links, start = [], 0
            while True:
                page = get(f'Ticket/{current}/Ticket_Ticket', {'range': f'{start}-{start + 99}'})
                if not isinstance(page, list):
                    raise ValueError('Invalid ticket links')
                links.extend(page)
                if len(page) < 100:
                    break
                start += len(page)
            targets = {str(link['tickets_id_2']) for link in links
                       if str(link.get('tickets_id_1')) == current
                       and str(link.get('link')) == '3'}
            if len(targets) != 1:
                raise ValueError('Deleted ticket has no unambiguous merge target')
            current = targets.pop()
            if not current.isdigit():
                raise ValueError('Invalid merge target')
        raise ValueError('Cyclic ticket merge')

    for source in list(mapping):
        if not str(source).isdigit():
            continue
        try:
            target = resolve(str(source))
            if source != target:
                conn.execute('INSERT OR IGNORE INTO ticket_merge_transfers '
                             '(source,target,recipients) VALUES (?,?,?)',
                             (source, target, json.dumps(recipients(mapping[source]))))
                conn.commit()
        except Exception as exc:
            print(f'[TICKET MERGE RETRY] #{source}: {type(exc).__name__}')

    for source, target, chats, applied in conn.execute(
            'SELECT source,target,recipients,applied FROM ticket_merge_transfers').fetchall():
        chats = json.loads(chats)
        if not applied:
            mapping = read_mapping(path)
            mapping[target] = recipients(mapping.get(target))
            mapping[target] = list(dict.fromkeys(mapping[target] + chats + recipients(mapping.get(source))))
            mapping.pop(source, None)
            write_mapping(path, mapping)
            conn.execute('UPDATE conversations SET glpi_ticket_id=? WHERE glpi_ticket_id=?', (target, source))
            conn.execute('UPDATE ticket_merge_transfers SET applied=1 WHERE source=?', (source,))
            conn.commit()
        message = (f'📌 Laporan #{source} digabung ke tiket gangguan #{target}.\n'
                   f'Pembaruan berikutnya menggunakan nomor #{target}.')
        for chat in chats:
            scope = f'ticket-merge:{source}:{target}'
            if not seen(conn, message, chat, scope):
                try:
                    send(chat, message)
                    mark(conn, message, chat, scope)
                    conn.commit()
                except Exception as exc:
                    print(f'[TICKET MERGE NOTICE RETRY] #{source}: {type(exc).__name__}')


def poll_merges(path, connect, get_session, kill_session, url, token, timeout, send, seen, mark):
    if not read_mapping(path):
        return
    session = get_session()
    if not session:
        raise RuntimeError('GLPI session unavailable for merge check')
    conn = None
    try:
        conn = connect()
        def get(endpoint, params=None):
            response = requests.get(f'{url}/{endpoint}', params=params,
                                    headers={'Session-Token': session, 'App-Token': token},
                                    verify=True, timeout=(3.05, timeout))
            if response.status_code == 416 and endpoint.endswith("/Ticket_Ticket"):
                return []
            response.raise_for_status()
            return response.json()
        sync_merges(path, conn, get, send, seen, mark)
    finally:
        if conn is not None:
            conn.close()
        kill_session(session)
