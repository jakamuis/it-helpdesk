"""Optional WAHA message webhook using the same intake path as polling."""
import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def incoming_message(message, profile=None):
    if not isinstance(message, dict) or message.get("fromMe"):
        return None
    sender = message.get("from")
    if not isinstance(sender, str) or not sender.endswith(("@lid", "@c.us", "@s.whatsapp.net")):
        return None
    message_id = message.get("id")
    if isinstance(message_id, dict):
        message_id = message_id.get("_serialized")
    body = message.get("body")
    if not isinstance(message_id, str) or not message_id or not isinstance(body, str) or not body.strip():
        return None
    return (profile, sender, body.strip(), message_id)


def handle_event(event, process):
    if not isinstance(event, dict) or event.get("event") != "message" or event.get("session") != "default":
        return
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return
    raw = payload.get("_data")
    raw = raw if isinstance(raw, dict) else {}
    message = incoming_message(payload, payload.get("notifyName") or raw.get("notifyName"))
    if message:
        return process(*message)


def start_webhook(process):
    port = int(os.getenv("WAHA_WEBHOOK_PORT", "0"))
    if not port:
        return
    secret = os.getenv("WAHA_WEBHOOK_SECRET", "")
    if not secret:
        raise ValueError("WAHA_WEBHOOK_SECRET is required when WAHA_WEBHOOK_PORT is set")

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/waha":
                self.send_error(404)
                return
            key = self.headers.get("X-Helpdesk-Webhook", "")
            if not hmac.compare_digest(key.encode(), secret.encode()):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1024 * 1024:
                    raise ValueError("Invalid body length")
                self.connection.settimeout(5)
                event = json.loads(self.rfile.read(size))
            except (ValueError, OSError):
                self.send_error(400)
                return
            if handle_event(event, process) is False:
                self.send_error(503)
                return
            self.send_response(204)
            self.end_headers()

    server = ThreadingHTTPServer((os.getenv("WAHA_WEBHOOK_BIND", "127.0.0.1"), port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
