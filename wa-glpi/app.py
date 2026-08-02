import requests
import time
import urllib3
import json
import os

urllib3.disable_warnings()

# =========================================
# WAHA CONFIG
# =========================================

WAHA_API_KEY = os.getenv("WAHA_API_KEY", "helpdesk123")
WAHA_URL = os.getenv("WAHA_URL", "http://localhost:3001")

# =========================================
# GLPI CONFIG
# =========================================

GLPI_URL = os.getenv("GLPI_URL", "http://localhost:8080/apirest.php")

APP_TOKEN = os.getenv("GLPI_APP_TOKEN", "J9IMyiiYAOVBc8GNCiZrwKT4e67SRpA1iDuPnbKj")
USER_TOKEN = os.getenv("GLPI_USER_TOKEN", "Revolus1!234")

# =========================================
# FILES
# =========================================

MAPPING_FILE = "ticket_mapping.json"
FOLLOWUP_TRACK_FILE = "last_followup.txt"

# =========================================
# GLOBAL
# =========================================

LAST_MESSAGE_ID = None

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
            verify=False
        )

        data = response.json()

        if isinstance(data, dict) and "session_token" in data:
            return data["session_token"]

        print(f"\n⚠️ [GLPI API TOKEN ERROR]: {data}")
        return None
    except Exception as e:
        print(f"\n⚠️ [GLPI API EXCEPTION]: {e}")
        return None

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

    with open(MAPPING_FILE, "w") as f:
        json.dump(data, f, indent=4)

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

    for ticket_id, saved_chat_id in data.items():

        if saved_chat_id == chat_id:

            return ticket_id

    return None

# =========================================
# CREATE GLPI TICKET
# =========================================

def create_ticket(session_token, sender_name, sender_id, message):

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
        verify=False
    )

    return response.json()

# =========================================
# CREATE GLPI FOLLOWUP
# =========================================

def create_followup(session_token, ticket_id, message):

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
                "content": message
            }
        },
        verify=False
    )

    return response.json()

# =========================================
# SEND WHATSAPP MESSAGE
# =========================================

def send_whatsapp(chat_id, message):

    requests.post(
        f"{WAHA_URL}/api/sendText",
        headers={
            "X-Api-Key": WAHA_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "chatId": chat_id,
            "text": message,
            "session": "default"
        }
    )

# =========================================
# SEND NEW TICKET REPLY
# =========================================

def send_ticket_reply(chat_id, ticket_id):

    message = f"""Halo 👋

Laporan Anda sudah berhasil diterima oleh IT Helpdesk.

Nomor Ticket: #{ticket_id}

Tim kami akan segera melakukan pengecekan dan tindak lanjut.

Terima kasih 😄"""

    send_whatsapp(chat_id, message)

# =========================================
# PROCESS WHATSAPP CHATS
# =========================================

def process_chats():

    global LAST_MESSAGE_ID

    response = requests.get(
        f"{WAHA_URL}/api/default/chats",
        headers={
            "X-Api-Key": WAHA_API_KEY
        }
    )

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

        if msg_id == LAST_MESSAGE_ID:
            continue

        LAST_MESSAGE_ID = msg_id

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

        message_body = last_message.get("body")

        print("\n===================================")
        print(" NEW WHATSAPP MESSAGE")
        print("===================================")
        print("NAME    :", sender_name)
        print("SENDER  :", sender_id)
        print("MESSAGE :", message_body)

        # =================================
        # CREATE GLPI SESSION
        # =================================

        session_token = get_glpi_session()

        # =================================
        # CHECK EXISTING TICKET
        # =================================

        existing_ticket = find_existing_ticket(sender_id)

        # =================================
        # EXISTING TICKET -> FOLLOWUP
        # =================================

        if existing_ticket:

            print(f"\nEXISTING TICKET FOUND: {existing_ticket}")

            followup = create_followup(
                session_token,
                existing_ticket,
                message_body
            )

            print("\nFOLLOWUP CREATED:")
            print(followup)

        # =================================
        # NEW TICKET
        # =================================

        else:

            ticket = create_ticket(
                session_token,
                sender_name,
                sender_id,
                message_body
            )

            print("\nGLPI RESPONSE:")
            print(ticket)

            ticket_id = ticket.get("id") if isinstance(ticket, dict) else None

            if ticket_id:

                save_mapping(
                    ticket_id,
                    sender_id
                )

                send_ticket_reply(
                    sender_id,
                    ticket_id
                )

                print(f"\nTICKET CREATED: {ticket_id}")

# =========================================
# CHECK GLPI FOLLOWUPS
# =========================================

def check_followups():

    last_followup_id = 0

    if os.path.exists(FOLLOWUP_TRACK_FILE):

        with open(FOLLOWUP_TRACK_FILE, "r") as f:

            try:
                last_followup_id = int(f.read().strip())
            except:
                last_followup_id = 0

    session_token = get_glpi_session()

    response = requests.get(
        f"{GLPI_URL}/ITILFollowup",
        headers={
            "Session-Token": session_token,
            "App-Token": APP_TOKEN
        },
        verify=False
    )

    followups = response.json()

    if not isinstance(followups, list):
        return

    for followup in followups:

        if not isinstance(followup, dict):
            continue

        followup_id = int(followup.get("id", 0))

        if followup_id <= last_followup_id:
            continue

        ticket_id = str(followup.get("items_id"))

        content = followup.get("content", "")

        content = content.replace("<p>", "")
        content = content.replace("</p>", "")

        print("\nNEW FOLLOWUP DETECTED")
        print("TICKET:", ticket_id)
        print("CONTENT:", content)

        if not os.path.exists(MAPPING_FILE):
            continue

        with open(MAPPING_FILE, "r") as f:

            mapping = json.load(f)

        chat_id = mapping.get(ticket_id)

        if not chat_id:
            continue

        message = f"📌 Update Ticket #{ticket_id}\n{content}"

        send_whatsapp(
            chat_id,
            message
        )

        print("FOLLOWUP SENT TO WHATSAPP")

        with open(FOLLOWUP_TRACK_FILE, "w") as f:
            f.write(str(followup_id))

# =========================================
# MAIN LOOP
# =========================================

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
