"""Optional Request IT feed -> existing WAHA sender. Disabled unless explicitly configured."""
import os
from urllib.parse import urlparse
import requests

MESSAGES = {
    'submit': 'Pengajuan diterima dan menunggu persetujuan.',
    'approve': 'Tahap persetujuan diperbarui.',
    'revise': 'Pengajuan memerlukan revisi. Buka form Request IT dengan akun Anda.',
    'reject': 'Pengajuan ditolak. Hubungi petugas untuk informasi lebih lanjut.',
    'assign': 'Pengajuan telah ditugaskan kepada tim IT.',
    'start': 'Tim IT mulai mengerjakan pengajuan Anda.',
    'ask': 'Tim IT membutuhkan kelengkapan. Buka form Request IT dengan akun Anda.',
    'answer': 'Kelengkapan pengajuan telah diterima.',
    'finish': 'Pengajuan selesai dikerjakan oleh tim IT.',
    'it_reject': 'Pengajuan tidak dapat dilanjutkan oleh IT.',
    'cancel': 'Pengajuan dibatalkan.',
    'change': 'Pengajuan dikembalikan untuk revisi dan persetujuan ulang.',
}

class RequestNotifier:
    def __init__(self):
        self.url = os.getenv('ITREQUEST_FEED_URL', '')
        self.token = os.getenv('ITREQUEST_BRIDGE_TOKEN', '')

    def poll(self, connect, send):
        if not self.url or not self.token:
            return
        if urlparse(self.url).scheme != 'https' or len(self.token) < 32:
            raise ValueError('Request feed requires HTTPS and a token of at least 32 characters')
        with connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS request_feed_cursor (url TEXT PRIMARY KEY, cursor INTEGER NOT NULL)')
            row = conn.execute('SELECT cursor FROM request_feed_cursor WHERE url=?', (self.url,)).fetchone()
            cursor = row[0] if row else 0
            # First activation drains history without sending; process one bounded page per loop.
            conn.execute('CREATE TABLE IF NOT EXISTS request_feed_ready (url TEXT PRIMARY KEY)')
            ready = conn.execute('SELECT 1 FROM request_feed_ready WHERE url=?', (self.url,)).fetchone()
            response = requests.get(self.url, params={'after': cursor}, headers={'Authorization': 'Bearer ' + self.token}, timeout=15)
            response.raise_for_status()
            data = response.json()
            events, next_cursor = data['events'], data['cursor']
            if not isinstance(events, list) or type(next_cursor) is not int or next_cursor < cursor or type(data.get('has_more')) is not bool:
                raise ValueError('Invalid Request feed')
            for event in events:
                if type(event.get('id')) is not int or not cursor < event['id'] <= next_cursor:
                    raise ValueError('Invalid Request event order')
                if event.get('action') not in MESSAGES:
                    raise ValueError('Unknown Request event')
                import re
                if not re.fullmatch(r'[1-9][0-9]{7,14}@c\.us', event.get('chat_id', '')) or not re.fullmatch(r'REQ-[0-9]{4}-[0-9]{6,}', event.get('reference', '')):
                    raise ValueError('Invalid Request recipient/reference')
                cursor = event['id']
            if ready:
                for event in events:
                    if send(event['chat_id'], '📌 ' + event['reference'] + '\n' + MESSAGES[event['action']]) is False:
                        raise RuntimeError('Request WhatsApp delivery failed')
                    # Commit after each successful send so a later failure does not replay earlier events.
                    conn.execute('INSERT OR REPLACE INTO request_feed_cursor VALUES (?,?)', (self.url, event['id']))
                    conn.commit()
            conn.execute('INSERT OR REPLACE INTO request_feed_cursor VALUES (?,?)', (self.url, next_cursor))
            if not data['has_more']:
                conn.execute('INSERT OR IGNORE INTO request_feed_ready VALUES (?)', (self.url,))
            conn.commit()
