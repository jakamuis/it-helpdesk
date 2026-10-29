"""Persist ticket status transitions and retry requester notifications."""

import json
import time

import requests


class StatusNotifier:
    def __init__(self, interval=30):
        self.interval = interval
        self.next_poll = 0

    def poll(self, mapping_file, connect, get_session, kill_session,
             glpi_url, app_token, timeout, send):
        if time.monotonic() < self.next_poll:
            return
        self.next_poll = time.monotonic() + self.interval
        try:
            with open(mapping_file) as source:
                mapping = json.load(source)
        except FileNotFoundError:
            return
        if not isinstance(mapping, dict) or not mapping:
            return
        session = get_session()
        if not session:
            return
        conn = None
        try:
            conn = connect()
            conn.execute("""CREATE TABLE IF NOT EXISTS ticket_status_notifications (
                ticket_id TEXT PRIMARY KEY,
                status INTEGER NOT NULL,
                revision INTEGER NOT NULL,
                pending_revision INTEGER
            )""")
            conn.commit()
            for ticket_id, chat_id in mapping.items():
                if not str(ticket_id).isdigit() or not isinstance(chat_id, str) or not chat_id:
                    continue
                try:
                    response = requests.get(
                        f"{glpi_url}/Ticket/{ticket_id}",
                        headers={"Session-Token": session, "App-Token": app_token},
                        verify=True, timeout=(3.05, timeout),
                    )
                    response.raise_for_status()
                    ticket = response.json()
                    if not isinstance(ticket, dict):
                        raise ValueError("Invalid ticket response")
                    status = int(ticket["status"])
                    if status not in range(1, 7):
                        raise ValueError("Invalid ticket status")
                    self.observe(conn, str(ticket_id), status, chat_id, send)
                except Exception as exc:
                    # One inaccessible ticket or failed send must not block others.
                    print(f"[TICKET STATUS RETRY] #{ticket_id}: {type(exc).__name__}")
        finally:
            if conn is not None:
                conn.close()
            kill_session(session)

    @staticmethod
    def observe(conn, ticket_id, status, chat_id, send):
        row = conn.execute(
            "SELECT status, revision, pending_revision FROM ticket_status_notifications "
            "WHERE ticket_id = ?", (ticket_id,),
        ).fetchone()
        if row is None:
            # Establish a baseline; deploying must not notify historical solved tickets.
            conn.execute(
                "INSERT INTO ticket_status_notifications VALUES (?, ?, 0, NULL)",
                (ticket_id, status),
            )
            conn.commit()
            return
        previous, revision, pending = row
        if previous != status:
            revision += 1
            pending = revision if status == 5 else None
            conn.execute(
                "UPDATE ticket_status_notifications SET status=?, revision=?, "
                "pending_revision=? WHERE ticket_id=?",
                (status, revision, pending, ticket_id),
            )
            conn.commit()
        if pending is None:
            return
        message = (
            f"✅ Update Tiket #{ticket_id}\n\n"
            "Status laporan Anda sudah *Solved (Selesai)*.\n"
            "Tim IT telah menyelesaikan penanganan laporan Anda.\n\n"
            "Jika kendala masih terjadi, silakan balas pesan ini. Terima kasih."
        )
        send(chat_id, message)
        conn.execute(
            "UPDATE ticket_status_notifications SET pending_revision=NULL "
            "WHERE ticket_id=? AND pending_revision=?", (ticket_id, pending),
        )
        conn.commit()
        print(f"[TICKET STATUS] #{ticket_id}: Solved notification sent")
