import requests
import time
import urllib3
import json
import os
import re
import html
import threading
from concurrent.futures import ThreadPoolExecutor
from intake import confirmation, extract, identity_only, title
from webhook import incoming_message, start_webhook
from status_notifier import StatusNotifier
from request_notifier import RequestNotifier
from ticket_merge import recipients, read_mapping, write_mapping, poll_merges

status_notifier = StatusNotifier()
request_notifier = RequestNotifier()

urllib3.disable_warnings()

from state_manager import (
    CONVERSATION_TTL_SECONDS,
    create_conversation,
    get_active_conversation,
    get_message_status,
    has_reply_been_sent,
    init_db,
    is_message_retry_due,
    mark_reply_sent,
    set_message_status,
    update_conversation,
    _get_conn,
)

# =========================================
# WAHA CONFIG
# =========================================

WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")
WAHA_URL = os.getenv("WAHA_URL", "http://localhost:3001")

# =========================================
# AI TRIAGE CONFIG
# =========================================

AI_TRIAGE_ENABLED = os.getenv("AI_TRIAGE_ENABLED", "false").lower() == "true"
from ai_client import call_triage

_intake_lock = threading.Lock()
_ai_pool = ThreadPoolExecutor(max_workers=2)

init_db()

# =========================================
# GLPI CONFIG
# =========================================

GLPI_URL = os.getenv("GLPI_URL", "http://localhost:8080/apirest.php")

APP_TOKEN = os.getenv("GLPI_APP_TOKEN", "")
USER_TOKEN = os.getenv("GLPI_USER_TOKEN", "")
GLPI_TIMEOUT_SECONDS = float(os.getenv("GLPI_TIMEOUT_SECONDS", "15"))
WAHA_TIMEOUT_SECONDS = float(os.getenv("WAHA_TIMEOUT_SECONDS", "10"))

# =========================================
# FILES
# =========================================

MAPPING_FILE = os.getenv("TICKET_MAPPING_FILE", "ticket_mapping.json")
FOLLOWUP_TRACK_FILE = os.getenv("FOLLOWUP_TRACK_FILE", "last_followup.txt")

# =========================================
# GET GLPI SESSION
# =========================================

def get_glpi_session():

    try:
        response = requests.get(
            f"{GLPI_URL}/initSession",
            headers={
                "Authorization": f"user_token {USER_TOKEN}",
                "App-Token": APP_TOKEN
            },
            verify=True,
            timeout=(3.05, GLPI_TIMEOUT_SECONDS),
        )
        response.raise_for_status()

        data = response.json()

        if isinstance(data, dict) and "session_token" in data:
            return data["session_token"]

        print(f"\n⚠️ [GLPI API TOKEN ERROR]: {data}")
        return None
    except (requests.RequestException, ValueError, TypeError) as exc:
        print(f"\n⚠️ [GLPI API EXCEPTION]: {type(exc).__name__}")
        return None

def kill_glpi_session(session_token):
    if not session_token:
        return
    try:
        response = requests.get(
            f"{GLPI_URL}/killSession",
            headers={
                "Session-Token": session_token,
                "App-Token": APP_TOKEN,
            },
            verify=True,
            timeout=(3.05, GLPI_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"\n⚠️ [GLPI SESSION CLEANUP]: {type(exc).__name__}")

# =========================================
# SAVE TICKET MAPPING
# =========================================

def save_mapping(ticket_id, chat_id):

    data = read_mapping(MAPPING_FILE)
    chats = recipients(data.get(str(ticket_id)))
    if chat_id not in chats:
        chats.append(chat_id)
    data[str(ticket_id)] = chats[0] if len(chats) == 1 else chats
    write_mapping(MAPPING_FILE, data)

# =========================================
# FIND TICKET BY MARKER
# =========================================

def find_ticket_by_marker(session_token, marker):
    response = requests.get(
        f"{GLPI_URL}/search/Ticket",
        headers={
            "Session-Token": session_token,
            "App-Token": APP_TOKEN,
        },
        params={
            "criteria[0][field]": 21,
            "criteria[0][searchtype]": "contains",
            "criteria[0][value]": f"[WAHA_MSG_ID: {marker}]",
            "forcedisplay[0]": 2,
        },
        verify=True,
        timeout=(3.05, GLPI_TIMEOUT_SECONDS),
    )
    response.raise_for_status()
    data = response.json()
    rows = data.get("data", []) if isinstance(data, dict) else []
    if rows and isinstance(rows[0], dict):
        return str(rows[0].get("2", "")) or None
    return None


def find_followup_by_marker(session_token, ticket_id, marker):
    marker_text = f"[WAHA_MSG_ID: {marker}]"
    return any(marker_text in str(row.get("content", ""))
               for row in get_all_followups(session_token, ticket_id=ticket_id))


# =========================================
# CREATE GLPI TICKET
# =========================================

def create_ticket(session_token, sender_name, sender_id, message, marker=None, fields=None):
    fields = fields or extract(message, sender_name)
    ticket_title = title(fields)

    ticket_content = f"""[HELPDESK_WHATSAPP_V1]
WhatsApp Helpdesk Ticket

Nama Pengirim:
{html.escape(fields["name"] or "Pelapor belum diketahui")}

WhatsApp ID:
{html.escape(sender_id)}

Pesan:
{html.escape(message)}
"""
    if marker:
        ticket_content += f"\n\n[WAHA_MSG_ID: {html.escape(marker)}]"

    response = requests.post(
        f"{GLPI_URL}/Ticket",
        headers={
            "Content-Type": "application/json",
            "Session-Token": session_token,
            "App-Token": APP_TOKEN
        },
        json={
            "input": {
                "name": ticket_title,
                **location_input(session_token, fields["site"]),
                "content": ticket_content,
                "priority": 3,
                "urgency": 3,
                "impact": 3
            }
        },
        verify=True,
        timeout=(3.05, GLPI_TIMEOUT_SECONDS),
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict) or not result.get("id"):
        raise ValueError("GLPI ticket response did not contain an id")
    return result

# =========================================
# CREATE GLPI FOLLOWUP
# =========================================

def create_followup(session_token, ticket_id, message, marker=None, private=False):

    content = html.escape(message)
    if marker:
        content = f"[WAHA_MSG_ID: {html.escape(marker)}]\n\n{content}"

    response = requests.post(
        f"{GLPI_URL}/ITILFollowup",
        headers={
            "Content-Type": "application/json",
            "Session-Token": session_token,
            "App-Token": APP_TOKEN
        },
        json={
            "input": {
                "items_id": int(ticket_id),
                "itemtype": "Ticket",
                "content": content,
                "is_private": int(private),
            }
        },
        verify=True,
        timeout=(3.05, GLPI_TIMEOUT_SECONDS),
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict) or not result.get("id"):
        raise ValueError("GLPI follow-up response did not contain an id")
    return result

# =========================================
# SEND WHATSAPP MESSAGE
# =========================================

def send_whatsapp(chat_id, message):

    response = requests.post(
        f"{WAHA_URL}/api/sendText",
        headers={
            "X-Api-Key": WAHA_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "chatId": chat_id,
            "text": message,
            "session": "default"
        },
        timeout=(3.05, WAHA_TIMEOUT_SECONDS),
    )
    response.raise_for_status()

# =========================================
# SEND NEW TICKET REPLY
# =========================================

_REMOTE_WRITE_STATUSES = {"ticket_created_or_updated", "reply_failed_retryable"}


def location_input(session_token, site):
    if not site:
        return {}
    response = requests.get(
        f"{GLPI_URL}/Location",
        headers={"Session-Token": session_token, "App-Token": APP_TOKEN},
        params={"searchText[name]": site, "range": "0-49"},
        timeout=(3.05, GLPI_TIMEOUT_SECONDS),
    )
    if response.status_code in {403, 404}:
        return {}
    response.raise_for_status()
    matches = [row["id"] for row in response.json()
               if str(row.get("name", "")).casefold() == site.casefold()]
    return {"locations_id": matches[0]} if len(matches) == 1 else {}


def update_ticket_fields(session_token, ticket_id, fields):
    response = requests.put(
        f"{GLPI_URL}/Ticket/{ticket_id}",
        headers={"Session-Token": session_token, "App-Token": APP_TOKEN},
        json={"input": {"id": int(ticket_id), "name": title(fields),
                        **location_input(session_token, fields["site"])}},
        timeout=(3.05, GLPI_TIMEOUT_SECONDS),
    )
    response.raise_for_status()


def _is_greeting(message):
    normalized = re.sub(r"[\W_]+", " ", message.casefold()).strip()
    return normalized in {
        "hi", "hai", "halo", "hallo", "hello", "helo", "hey", "hei",
        "pagi", "siang", "sore", "malam", "selamat pagi", "selamat siang",
        "selamat sore", "selamat malam", "assalamualaikum",
    }


def _send_welcome_once(conn, chat_id):
    if get_active_conversation(conn, chat_id):
        return
    reply = (
        "Halo 👋 Selamat datang di IT Helpdesk.\n\n"
        "Boleh sebutkan nama Anda, cabang atau lokasi, dan kendala atau bantuan IT yang dibutuhkan?\n\n"
        "Contoh: “Saya Jaka di SIG Bekasi. Printer tidak bisa mencetak.”\n\n"
        "Kami akan mencatat laporan Anda dan mengirimkan nomor tiketnya."
    )
    send_whatsapp(chat_id, reply)
    create_conversation(conn, chat_id, "", "welcomed")


def get_ticket_status(session_token, ticket_id):
    response = requests.get(
        f"{GLPI_URL}/Ticket/{int(ticket_id)}",
        headers={"Session-Token": session_token, "App-Token": APP_TOKEN},
        verify=True,
        timeout=(3.05, GLPI_TIMEOUT_SECONDS),
    )
    response.raise_for_status()
    ticket = response.json()
    if not isinstance(ticket, dict) or int(ticket.get("status", 0)) not in range(1, 7):
        raise ValueError("Invalid GLPI ticket status")
    if str(ticket.get("is_deleted", 0)) == "1":
        raise RuntimeError("Deleted ticket awaiting merge reconciliation")
    return int(ticket["status"])


def _classify(chat_id, message, conversation_id, ticket_id):
    try:
        result = call_triage(chat_id, message)
        if not result:
            return
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE conversations SET intent=?, ai_category=?, ai_subcategory=?, ai_priority=? "
                "WHERE conversation_id=?",
                (result.get("intent"), result.get("category"), result.get("subcategory"),
                 result.get("priority"), conversation_id),
            )
            conn.commit()
        finally:
            conn.close()
        if not result.get("fallback_used"):
            note = "\n".join(
                f"{label}: {result.get(key) or 'unknown'}"
                for key, label in (("intent", "Intent"), ("category", "Category"),
                                   ("subcategory", "Subcategory"), ("priority", "Priority"))
            )
            if result.get("human_review_required"):
                note += "\nHUMAN ESCALATION REQUIRED: " + str(result.get("escalation_reason") or "review requested")
            token = get_glpi_session()
            if token:
                try:
                    create_followup(token, ticket_id, note, private=True)
                finally:
                    kill_glpi_session(token)
    except Exception as exc:
        print(f"[AI TRIAGE] {type(exc).__name__}")


def _process_chat_message(sender_name, sender_id, message_body, msg_id):
    # The polling and optional webhook entry points share a single writer.
    with _intake_lock:
        return _process_message(sender_name, sender_id, message_body, msg_id)


def _process_message(sender_name, sender_id, message, msg_id):
    conn = _get_conn()
    token = None
    try:
        status = get_message_status(conn, msg_id)
        if status == "completed":
            return True
        if not is_message_retry_due(conn, msg_id):
            return False
        if _is_greeting(message):
            _send_welcome_once(conn, sender_id)
        elif status not in _REMOTE_WRITE_STATUSES:
            set_message_status(conn, msg_id, sender_id, "received")
            conn.commit()
            active = get_active_conversation(conn, sender_id)
            opening = {}
            if active and active["status"] == "welcomed":
                opening = json.loads(active["collected_fields"] or "{}").get("opening", {})
                provided = identity_only(message)
                if provided:
                    update_conversation(conn, active["conversation_id"], {
                        "collected_fields": {"opening": {**opening, **provided}},
                    })
                    set_message_status(conn, msg_id, sender_id, "completed")
                    conn.commit()
                    return True

            token = get_glpi_session()
            if not token:
                raise RuntimeError("GLPI session unavailable")

            ticket_id = active["glpi_ticket_id"] if active and active["status"] != "welcomed" else None
            if ticket_id and status is None and get_ticket_status(token, ticket_id) in {5, 6}:
                update_conversation(conn, active["conversation_id"], {"expires_at": time.time() - 1})
                conn.commit()
                active = None
                ticket_id = None

            reply = None
            if ticket_id:
                stored = json.loads(active["collected_fields"] or "{}")
                previous = stored.get("intake")
                fields = extract(message, sender_name, previous) if previous else None
                if fields and fields != previous:
                    update_ticket_fields(token, ticket_id, fields)
                    stored["intake"] = fields
                if not status or not find_followup_by_marker(token, ticket_id, msg_id):
                    create_followup(token, ticket_id, message, marker=msg_id)
                update_conversation(conn, active["conversation_id"], {
                    "collected_fields": stored,
                    "expires_at": time.time() + CONVERSATION_TTL_SECONDS,
                })
            else:
                fields = extract(message, opening.get("name") or sender_name)
                fields["site"] = fields["site"] or opening.get("site", "")
                ticket_id = find_ticket_by_marker(token, msg_id) if status else None
                if not ticket_id:
                    ticket_id = str(create_ticket(
                        token, sender_name, sender_id, message, marker=msg_id, fields=fields,
                    )["id"])
                save_mapping(ticket_id, sender_id)
                if active:
                    update_conversation(conn, active["conversation_id"], {"expires_at": time.time() - 1})
                conversation_id = create_conversation(conn, sender_id, ticket_id, "ready_for_ticket")
                update_conversation(conn, conversation_id, {"collected_fields": {"intake": fields}})
                reply = confirmation(ticket_id, fields)
                conn.execute("INSERT INTO intake_replies VALUES (?, ?)", (msg_id, reply))
            set_message_status(conn, msg_id, sender_id, "ticket_created_or_updated")
            conn.commit()
            if reply and AI_TRIAGE_ENABLED:
                _ai_pool.submit(_classify, sender_id, message, conversation_id, ticket_id)

        pending = conn.execute("SELECT reply FROM intake_replies WHERE message_id=?", (msg_id,)).fetchone()
        if pending:
            send_whatsapp(sender_id, pending["reply"])
            conn.execute("DELETE FROM intake_replies WHERE message_id=?", (msg_id,))
        set_message_status(conn, msg_id, sender_id, "completed")
        conn.commit()
        return True
    except Exception as exc:
        conn.rollback()
        current = get_message_status(conn, msg_id)
        set_message_status(conn, msg_id, sender_id, (
            "reply_failed_retryable" if current in _REMOTE_WRITE_STATUSES else "failed_retryable"
        ))
        conn.commit()
        print(f"[MESSAGE RETRY] {type(exc).__name__}")
        return False
    finally:
        kill_glpi_session(token)
        conn.close()


_last_waha_session_status = None


def process_chats():
    global _last_waha_session_status
    session_response = requests.get(
        f"{WAHA_URL}/api/sessions/default",
        headers={"X-Api-Key": WAHA_API_KEY},
        timeout=(3.05, WAHA_TIMEOUT_SECONDS),
    )
    session_response.raise_for_status()
    session = session_response.json()
    status = session.get("status") if isinstance(session, dict) else "INVALID_RESPONSE"
    if status != _last_waha_session_status:
        print(f"[WAHA SESSION] {status}; chat polling requires WORKING")
        _last_waha_session_status = status
    if status != "WORKING":
        return
    response = requests.get(
        f"{WAHA_URL}/api/default/chats",
        headers={
            "X-Api-Key": WAHA_API_KEY
        },
        timeout=(3.05, WAHA_TIMEOUT_SECONDS),
    )
    response.raise_for_status()

    chats = response.json()

    if not isinstance(chats, list):
        return

    for chat in chats:
        if isinstance(chat, dict):
            message = incoming_message(chat.get("lastMessage"), chat.get("name"))
            if message:
                _process_chat_message(*message)


# =========================================
# CHECK GLPI FOLLOWUPS
# =========================================

def get_all_followups(session_token, ticket_id=None):
    followups = []
    endpoint = f"Ticket/{int(ticket_id)}/ITILFollowup" if ticket_id else "ITILFollowup"
    start = 0
    while True:
        response = requests.get(
            f"{GLPI_URL}/{endpoint}",
            headers={"Session-Token": session_token, "App-Token": APP_TOKEN},
            params={"range": f"{start}-{start + 99}", "sort": "id", "order": "ASC"},
            verify=True,
            timeout=(3.05, GLPI_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise ValueError("Invalid GLPI follow-up page")
        followups.extend(page)
        content_range = response.headers.get("Content-Range", "")
        match = re.fullmatch(r"(?:\w+\s+)?(\d+)-(\d+)/(\d+)", content_range) if isinstance(content_range, str) else None
        if match:
            first, last, total = map(int, match.groups())
            if first != start or last < first or last - first + 1 != len(page):
                raise ValueError("Inconsistent GLPI follow-up pagination")
            if last + 1 >= total:
                break
            start = last + 1
        else:
            if len(page) < 100:
                break
            start += len(page)
    return followups


def followup_to_whatsapp_text(content):
    """Remove GLPI markup before decoding literal characters in the message."""
    # GLPI may entity-encode the entire rich-text document. Only unwrap a
    # recognizable document container, never arbitrary user text such as <abc>.
    if re.fullmatch(
        r"\s*&lt;(p|div)(?:\s[^\n]*?)?&gt;.*&lt;/\1&gt;\s*",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        content = html.unescape(content)
    content = re.sub(r"(?i)<br\s*/?>|</(?:p|div)>", "\n", content)
    content = re.sub(r"<[^>]+>", "", content)
    # Decode once, after stripping tags: &lt;...&gt; is message content.
    return html.unescape(content).strip()


def check_followups():
    last_followup_id = 0
    if os.path.exists(FOLLOWUP_TRACK_FILE):
        with open(FOLLOWUP_TRACK_FILE, "r") as f:
            try:
                last_followup_id = int(f.read().strip())
            except (TypeError, ValueError):
                last_followup_id = 0

    session_token = get_glpi_session()
    if not session_token:
        return

    try:
        followups = get_all_followups(session_token)

        mapping = {}
        if os.path.exists(MAPPING_FILE):
            try:
                with open(MAPPING_FILE, "r") as f:
                    loaded_mapping = json.load(f)
                    mapping = loaded_mapping if isinstance(loaded_mapping, dict) else {}
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                mapping = {}

        def followup_id(item):
            try:
                return int(item.get("id", 0)) if isinstance(item, dict) else 0
            except (TypeError, ValueError):
                return 0

        latest_handled_id = last_followup_id
        conn = _get_conn()
        for followup in sorted(followups, key=followup_id):
            current_id = followup_id(followup)
            if current_id <= last_followup_id:
                continue

            ticket_id = str(followup.get("items_id"))
            content = str(followup.get("content", ""))

            if followup.get("itemtype", "Ticket") != "Ticket":
                latest_handled_id = current_id
                continue

            # Inbound WhatsApp messages are stored as marked GLPI follow-ups.
            # They must never be echoed back to the same WhatsApp user.
            if "[WAHA_MSG_ID:" in content:
                latest_handled_id = current_id
                continue

            # GLPI private/internal notes are not requester-facing content.
            if str(followup.get("is_private", "0")).lower() in {
                "1",
                "true",
                "yes",
            }:
                latest_handled_id = current_id
                continue

            for chat_id in recipients(mapping.get(ticket_id)):
                clean_content = followup_to_whatsapp_text(content)
                message = f"📌 Update Ticket #{ticket_id}\n{clean_content}"
                scope = f"glpi-followup:{current_id}"
                if not has_reply_been_sent(conn, message, chat_id, scope):
                    send_whatsapp(chat_id, message)
                    mark_reply_sent(conn, message, chat_id, scope)
                    conn.commit()
                    print(f"FOLLOWUP {current_id} SENT TO WHATSAPP")

            latest_handled_id = current_id

        if latest_handled_id > last_followup_id:
            followup_dir = os.path.dirname(FOLLOWUP_TRACK_FILE)
            if followup_dir:
                os.makedirs(followup_dir, exist_ok=True)
            temporary_path = f"{FOLLOWUP_TRACK_FILE}.tmp"
            with open(temporary_path, "w") as f:
                f.write(str(latest_handled_id))
            os.replace(temporary_path, FOLLOWUP_TRACK_FILE)
    finally:
        if "conn" in locals():
            conn.close()
        kill_glpi_session(session_token)


# =========================================
# MAIN LOOP
# =========================================

if __name__ == "__main__":
    start_webhook(_process_chat_message)
    print("\n===================================")
    print(" WAHA ↔ GLPI BRIDGE STARTED")
    print("===================================\n")

    while True:

        try:

            with _intake_lock:
                poll_merges(
                    MAPPING_FILE, _get_conn, get_glpi_session, kill_glpi_session,
                    GLPI_URL, APP_TOKEN, GLPI_TIMEOUT_SECONDS, send_whatsapp,
                    has_reply_been_sent, mark_reply_sent,
                )

            status_notifier.poll(
                MAPPING_FILE, _get_conn, get_glpi_session, kill_glpi_session,
                GLPI_URL, APP_TOKEN, GLPI_TIMEOUT_SECONDS, send_whatsapp,
            )

            try:
                request_notifier.poll(_get_conn, send_whatsapp)
            except Exception as request_error:
                print("Request notification failed:", type(request_error).__name__)

            process_chats()

            check_followups()

        except Exception as e:

            print("\nERROR:")
            print(e)

        time.sleep(5)
