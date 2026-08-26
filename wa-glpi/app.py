import requests
import time
import urllib3
import json
import os

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
if AI_TRIAGE_ENABLED:
    from ai_client import call_triage

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
            verify=False,
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
            verify=False,
            timeout=(3.05, GLPI_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"\n⚠️ [GLPI SESSION CLEANUP]: {type(exc).__name__}")

# =========================================
# SAVE TICKET MAPPING
# =========================================

def save_mapping(ticket_id, chat_id):

    data = {}

    if os.path.exists(MAPPING_FILE):

        try:

            with open(MAPPING_FILE, "r") as f:
                data = json.load(f)

        except:
            data = {}

    data[str(ticket_id)] = chat_id

    mapping_dir = os.path.dirname(MAPPING_FILE)
    if mapping_dir:
        os.makedirs(mapping_dir, exist_ok=True)
    temporary_path = f"{MAPPING_FILE}.tmp"
    with open(temporary_path, "w") as f:
        json.dump(data, f, indent=4)
    os.replace(temporary_path, MAPPING_FILE)

    print(f"\nMAPPING SAVED:")
    print(f"TICKET {ticket_id} -> {chat_id}")

# =========================================
# FIND EXISTING TICKET
# =========================================

def find_existing_ticket(chat_id):

    if not os.path.exists(MAPPING_FILE):
        return None

    with open(MAPPING_FILE, "r") as f:

        data = json.load(f)

    for ticket_id, saved_chat_id in reversed(list(data.items())):

        if saved_chat_id == chat_id:

            return ticket_id

    return None

# =========================================
# FIND TICKET BY MARKER
# =========================================

def find_ticket_by_marker(session_token, marker):
    try:
        response = requests.get(
            f"{GLPI_URL}/search/Ticket",
            headers={
                "Session-Token": session_token,
                "App-Token": APP_TOKEN,
            },
            params={
                "criteria[0][field]": 21,
                "criteria[0][searchtype]": "contains",
                "criteria[0][value]": marker,
            },
            verify=False,
            timeout=(3.05, GLPI_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        data = response.json()
        rows = data.get("data", []) if isinstance(data, dict) else []
        if rows and isinstance(rows[0], dict):
            return str(rows[0].get("2", "")) or None
    except (requests.RequestException, ValueError, TypeError):
        return None
    return None

def find_followup_by_marker(session_token, ticket_id, marker):
    """Best-effort recovery for an ambiguous follow-up write."""
    try:
        response = requests.get(
            f"{GLPI_URL}/ITILFollowup",
            headers={
                "Session-Token": session_token,
                "App-Token": APP_TOKEN,
            },
            params={"range": "0-999"},
            verify=False,
            timeout=(3.05, GLPI_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        followups = response.json()
        if not isinstance(followups, list):
            return False
        marker_text = f"[WAHA_MSG_ID: {marker}]"
        return any(
            isinstance(item, dict)
            and str(item.get("items_id")) == str(ticket_id)
            and marker_text in str(item.get("content", ""))
            for item in followups
        )
    except (requests.RequestException, ValueError, TypeError):
        return False

# =========================================
# CREATE GLPI TICKET
# =========================================

def create_ticket(session_token, sender_name, sender_id, message, marker=None):

    ticket_title = f"[WhatsApp] {sender_name}"

    ticket_content = f"""
WhatsApp Helpdesk Ticket

Nama Pengirim:
{sender_name}

WhatsApp ID:
{sender_id}

Pesan:
{message}
"""
    if marker:
        ticket_content += f"\n\n[WAHA_MSG_ID: {marker}]"

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
                "content": ticket_content,
                "priority": 3,
                "urgency": 3,
                "impact": 3
            }
        },
        verify=False,
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

def create_followup(session_token, ticket_id, message, marker=None):

    content = message
    if marker:
        content += f"\n\n[WAHA_MSG_ID: {marker}]"

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
                "content": content
            }
        },
        verify=False,
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

def ticket_reply_message(ticket_id):
    return f"""Halo 👋

Laporan Anda sudah berhasil diterima oleh IT Helpdesk.

Nomor Ticket: #{ticket_id}

Tim kami akan segera melakukan pengecekan dan tindak lanjut.

Terima kasih 😄"""

def send_ticket_reply(chat_id, ticket_id):
    send_whatsapp(chat_id, ticket_reply_message(ticket_id))

# =========================================
# MAIN POLLING LOOP
# =========================================

TRIAGE_QUESTION_TEMPLATES = {
    "asset_id": "Mohon informasikan nomor aset perangkat yang bermasalah.",
    "site": "Kendala ini terjadi di lokasi atau site mana?",
    "symptom": "Gejala atau pesan error apa yang terlihat?",
    "printer_symptom": (
        "Gejala pada printernya seperti apa, misalnya kertas macet, offline, "
        "atau hasil cetak bermasalah?"
    ),
    "connection_type": "Koneksi yang digunakan Wi-Fi, LAN, atau VPN?",
    "affected_scope": "Apakah kendala ini hanya dialami Anda atau juga pengguna lain?",
    "affected_service": "Layanan atau aplikasi apa yang terdampak?",
    "business_impact": "Apa dampak kendala ini terhadap pekerjaan atau operasional?",
}

_REMOTE_WRITE_STATUSES = {"ticket_created_or_updated", "reply_failed_retryable"}

def _json_dict(value):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}

def _json_list(value):
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    return []

def _middleware_fallback_response():
    return {
        "intent": "incident",
        "category": "unknown",
        "subcategory": "unknown",
        "priority": "medium",
        "confidence": 0.0,
        "status": "ready_for_ticket",
        "human_review_required": True,
        "escalation_reason": "AI triage service unavailable",
        "extracted_fields": {},
        "missing_fields": [],
        "next_question_key": None,
        "suggested_response": None,
        "fallback_used": True,
    }

def _triage_note(message_body, ai_response, heading):
    def safe_value(key, default="unknown"):
        value = str(ai_response.get(key) or default).replace("\n", " ").strip()
        return value[:200]

    lines = [
        message_body,
        "",
        f"--- {heading} ---",
        f"Intent: {safe_value('intent')}",
        f"Category: {safe_value('category')}",
        f"Subcategory: {safe_value('subcategory')}",
        f"Priority: {safe_value('priority', 'medium')}",
    ]
    if ai_response.get("human_review_required"):
        reason = safe_value("escalation_reason", "review requested")
        lines.append(f"⚠️ HUMAN ESCALATION REQUIRED: {reason}")
    return "\n".join(lines)

def _send_ticket_reply_once(conn, chat_id, ticket_id, scope):
    reply = ticket_reply_message(ticket_id)
    if has_reply_been_sent(conn, reply, chat_id, scope):
        return
    send_ticket_reply(chat_id, ticket_id)
    mark_reply_sent(conn, reply, chat_id, scope)
    conn.commit()

def _send_triage_question_once(
    conn,
    chat_id,
    conversation_id,
    ai_response,
    questions_asked,
):
    if ai_response.get("status") != "collecting_information":
        return questions_asked

    question_key = ai_response.get("next_question_key")
    reply = TRIAGE_QUESTION_TEMPLATES.get(question_key)
    if not reply or question_key in questions_asked:
        return questions_asked

    if not has_reply_been_sent(conn, reply, chat_id, conversation_id):
        send_whatsapp(chat_id, reply)
        mark_reply_sent(conn, reply, chat_id, conversation_id)

    questions_asked.append(question_key)
    update_conversation(
        conn,
        conversation_id,
        {"questions_asked": questions_asked},
    )
    conn.commit()
    return questions_asked

def _update_conversation_from_triage(conn, conversation, ai_response):
    existing_fields = _json_dict(conversation.get("collected_fields"))
    new_fields = ai_response.get("extracted_fields")
    if isinstance(new_fields, dict):
        existing_fields.update(
            {key: value for key, value in new_fields.items() if value is not None}
        )

    questions_asked = _json_list(conversation.get("questions_asked"))
    conversation_status = (
        "ready_for_ticket"
        if ai_response.get("human_review_required")
        else ai_response.get("status", "collecting_information")
    )
    update_conversation(
        conn,
        conversation["conversation_id"],
        {
            "status": conversation_status,
            "intent": ai_response.get("intent", "unknown"),
            "ai_category": ai_response.get("category", "unknown"),
            "ai_subcategory": ai_response.get("subcategory", "unknown"),
            "ai_priority": ai_response.get("priority", "medium"),
            "collected_fields": existing_fields,
            "questions_asked": questions_asked,
            "expires_at": time.time() + CONVERSATION_TTL_SECONDS,
        },
    )
    conn.commit()
    return questions_asked

def _process_ai_message(
    conn,
    session_token,
    sender_name,
    sender_id,
    message_body,
    msg_id,
    status,
    retrying,
    ai_response,
):
    active_conv = get_active_conversation(conn, sender_id)
    ticket_id = active_conv.get("glpi_ticket_id") if active_conv else None
    remote_write_done = status in _REMOTE_WRITE_STATUSES
    recovered_ticket = False
    recovered_followup = False

    if retrying and not remote_write_done:
        if ticket_id:
            recovered_followup = find_followup_by_marker(
                session_token,
                ticket_id,
                msg_id,
            )
        else:
            ticket_id = find_ticket_by_marker(session_token, msg_id)
            recovered_ticket = bool(ticket_id)

    if not ticket_id:
        print("[AI TRIAGE] Actionable issue detected. Creating ticket immediately.")
        content = _triage_note(message_body, ai_response, "AI Triage Initial Info")
        ticket = create_ticket(
            session_token,
            sender_name,
            sender_id,
            content,
            marker=msg_id,
        )
        ticket_id = str(ticket["id"])
        remote_write_done = True
    elif active_conv and not remote_write_done and not recovered_followup:
        print(f"[AI TRIAGE] Appending to existing ticket: {ticket_id}")
        classification_changed = (
            ai_response.get("intent") != active_conv.get("intent")
            or ai_response.get("category") != active_conv.get("ai_category")
            or ai_response.get("priority") != active_conv.get("ai_priority")
        )
        followup_text = message_body
        if classification_changed or ai_response.get("human_review_required"):
            followup_text = _triage_note(
                message_body,
                ai_response,
                "AI Triage Updated Info",
            )
        create_followup(
            session_token,
            ticket_id,
            followup_text,
            marker=msg_id,
        )
        remote_write_done = True
    elif recovered_ticket or recovered_followup:
        print(f"[RECOVERY] Reused GLPI write for message {msg_id}")
        remote_write_done = True

    if not ticket_id or not remote_write_done:
        raise RuntimeError("GLPI write could not be confirmed")

    set_message_status(conn, msg_id, sender_id, "ticket_created_or_updated")

    if active_conv is None:
        conversation_status = (
            "ready_for_ticket"
            if ai_response.get("human_review_required")
            else ai_response.get("status", "collecting_information")
        )
        conversation_id = create_conversation(
            conn,
            sender_id,
            str(ticket_id),
            conversation_status,
        )
        active_conv = {
            "conversation_id": conversation_id,
            "glpi_ticket_id": str(ticket_id),
            "collected_fields": {},
            "questions_asked": [],
        }

    conn.commit()
    save_mapping(ticket_id, sender_id)

    questions_asked = _update_conversation_from_triage(
        conn,
        active_conv,
        ai_response,
    )

    # Safe on every turn: the conversation-scoped hash makes this an idempotent
    # no-op after the acknowledgement has been recorded.
    _send_ticket_reply_once(
        conn,
        sender_id,
        ticket_id,
        active_conv["conversation_id"],
    )

    _send_triage_question_once(
        conn,
        sender_id,
        active_conv["conversation_id"],
        ai_response,
        questions_asked,
    )

def _standard_process_flow(
    session_token,
    sender_name,
    sender_id,
    message_body,
    msg_id,
    existing_ticket=None,
    remote_write_done=False,
    retrying=False,
    use_legacy_mapping=True,
):
    ticket_id = existing_ticket or (
        find_existing_ticket(sender_id) if use_legacy_mapping else None
    )
    created = False

    if ticket_id:
        recovered_ticket = (
            find_ticket_by_marker(session_token, msg_id)
            if retrying and not remote_write_done
            else None
        )
        if recovered_ticket:
            save_mapping(recovered_ticket, sender_id)
            return str(recovered_ticket), True

        recovered_followup = (
            retrying
            and not remote_write_done
            and find_followup_by_marker(session_token, ticket_id, msg_id)
        )
        if not remote_write_done and not recovered_followup:
            print(f"\nEXISTING TICKET FOUND: {ticket_id}")
            followup = create_followup(
                session_token,
                ticket_id,
                message_body,
                marker=msg_id,
            )
            print("\nFOLLOWUP CREATED:")
            print(followup)
        return str(ticket_id), created

    recovered_ticket = find_ticket_by_marker(session_token, msg_id) if retrying else None
    if recovered_ticket:
        save_mapping(recovered_ticket, sender_id)
        return str(recovered_ticket), True

    ticket = create_ticket(
        session_token,
        sender_name,
        sender_id,
        message_body,
        marker=msg_id,
    )
    print("\nGLPI RESPONSE:")
    print(ticket)
    ticket_id = str(ticket["id"])
    save_mapping(ticket_id, sender_id)
    print(f"\nTICKET CREATED: {ticket_id}")
    return ticket_id, True

def _process_chat_message(sender_name, sender_id, message_body, msg_id):
    conn = _get_conn()
    session_token = None
    try:
        status = get_message_status(conn, msg_id)
        if status == "completed":
            return
        if status and not is_message_retry_due(conn, msg_id):
            return

        retrying = status is not None
        if status is None:
            set_message_status(conn, msg_id, sender_id, "received")
            conn.commit()

        print("\n===================================")
        print(" NEW WHATSAPP MESSAGE")
        print("===================================")
        print("NAME    :", sender_name)
        print("SENDER  :", sender_id)
        print("MESSAGE :", message_body)

        ai_response = None
        if AI_TRIAGE_ENABLED:
            ai_response = call_triage(sender_id, message_body)
            if ai_response is None:
                print("\n[AI TRIAGE] Service unavailable; using safe fallback.")
                ai_response = _middleware_fallback_response()
            elif ai_response.get("fallback_used") and ai_response.get("intent") in {
                "greeting",
                "unknown",
            }:
                ai_response["intent"] = "incident"

            print(
                "[AI TRIAGE] "
                f"intent={ai_response.get('intent')} "
                f"category={ai_response.get('category')} "
                f"priority={ai_response.get('priority')} "
                f"review={bool(ai_response.get('human_review_required'))}"
            )

            remote_write_done = status in _REMOTE_WRITE_STATUSES
            if not remote_write_done:
                set_message_status(conn, msg_id, sender_id, "triaged")
                conn.commit()

            active_conv = get_active_conversation(conn, sender_id)
            if (
                active_conv is None
                and ai_response.get("intent") in {"greeting", "spam"}
                and not ai_response.get("human_review_required")
            ):
                print("[AI TRIAGE] Ignoring non-actionable greeting/spam.")
                set_message_status(conn, msg_id, sender_id, "completed")
                conn.commit()
                return

        session_token = get_glpi_session()
        if not session_token:
            raise RuntimeError("GLPI session unavailable")

        if AI_TRIAGE_ENABLED:
            _process_ai_message(
                conn,
                session_token,
                sender_name,
                sender_id,
                message_body,
                msg_id,
                status,
                retrying,
                ai_response,
            )
        else:
            active_conv = get_active_conversation(conn, sender_id)
            existing_ticket = active_conv.get("glpi_ticket_id") if active_conv else None
            ticket_id, created = _standard_process_flow(
                session_token,
                sender_name,
                sender_id,
                message_body,
                msg_id,
                existing_ticket=existing_ticket,
                remote_write_done=status in _REMOTE_WRITE_STATUSES,
                retrying=retrying,
                use_legacy_mapping=False,
            )
            set_message_status(conn, msg_id, sender_id, "ticket_created_or_updated")
            if active_conv is None:
                create_conversation(
                    conn,
                    sender_id,
                    str(ticket_id),
                    "ready_for_ticket",
                )
            else:
                update_conversation(
                    conn,
                    active_conv["conversation_id"],
                    {"expires_at": time.time() + CONVERSATION_TTL_SECONDS},
                )
            conn.commit()
            if created or status == "reply_failed_retryable":
                _send_ticket_reply_once(conn, sender_id, ticket_id, f"message:{msg_id}")

        set_message_status(conn, msg_id, sender_id, "completed")
        conn.commit()
    except Exception as exc:
        current_status = get_message_status(conn, msg_id)
        retry_status = (
            "reply_failed_retryable"
            if current_status in _REMOTE_WRITE_STATUSES
            else "failed_retryable"
        )
        set_message_status(conn, msg_id, sender_id, retry_status)
        conn.commit()
        print(f"[MESSAGE RETRY] {msg_id}: {type(exc).__name__}")
    finally:
        kill_glpi_session(session_token)
        conn.close()

def process_chats():
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

        if not isinstance(chat, dict):
            continue

        last_message = chat.get("lastMessage")

        if not isinstance(last_message, dict):
            continue

        msg_id_val = last_message.get("id")
        if isinstance(msg_id_val, dict):
            msg_id = msg_id_val.get("_serialized")
        else:
            msg_id = str(msg_id_val) if msg_id_val else None

        if not msg_id:
            continue

        from_me = last_message.get("fromMe")

        if from_me:
            continue

        sender_name = chat.get("name")
        if not sender_name:
            sender_name = "Unknown User"

        sender_id = last_message.get("from")
        if not isinstance(sender_id, str):
            continue

        if "@lid" not in sender_id:
            continue

        message_body = last_message.get("body", "").strip()
        if not message_body:
            continue

        _process_chat_message(sender_name, sender_id, message_body, msg_id)

# =========================================
# CHECK GLPI FOLLOWUPS
# =========================================

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
        response = requests.get(
            f"{GLPI_URL}/ITILFollowup",
            headers={
                "Session-Token": session_token,
                "App-Token": APP_TOKEN,
            },
            verify=False,
            timeout=(3.05, GLPI_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        followups = response.json()
        if not isinstance(followups, list):
            return

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
        for followup in sorted(followups, key=followup_id):
            current_id = followup_id(followup)
            if current_id <= last_followup_id:
                continue

            ticket_id = str(followup.get("items_id"))
            content = str(followup.get("content", ""))

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

            chat_id = mapping.get(ticket_id)
            if chat_id:
                clean_content = content.replace("<p>", "").replace("</p>", "")
                message = f"📌 Update Ticket #{ticket_id}\n{clean_content}"
                send_whatsapp(chat_id, message)
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
        kill_glpi_session(session_token)

# =========================================
# MAIN LOOP
# =========================================

if __name__ == "__main__":
    print("\n===================================")
    print(" WAHA ↔ GLPI BRIDGE STARTED")
    print("===================================\n")

    while True:

        try:

            process_chats()

            check_followups()

        except Exception as e:

            print("\nERROR:")
            print(e)

        time.sleep(5)
