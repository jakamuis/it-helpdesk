import requests
import os
import json
from state_manager import get_active_conversation, _get_conn

AI_TRIAGE_URL = os.getenv("AI_TRIAGE_URL", "http://ai-triage:8000")
TIMEOUT_SECONDS = float(os.getenv("AI_TRIAGE_TIMEOUT_SECONDS", "30"))

_REQUIRED_RESPONSE_FIELDS = {
    "intent",
    "category",
    "subcategory",
    "priority",
    "status",
    "human_review_required",
    "fallback_used",
}

def call_triage(conversation_id: str, message: str):
    conn = _get_conn()
    try:
        active_conv = get_active_conversation(conn, conversation_id)
        state = {"questions_asked": []}

        if active_conv:
            state["intent"] = active_conv.get("intent")
            state["category"] = active_conv.get("ai_category")
            state["subcategory"] = active_conv.get("ai_subcategory")
            state["priority"] = active_conv.get("ai_priority")
            try:
                if active_conv.get("collected_fields"):
                    state.update(json.loads(active_conv["collected_fields"]))
                if active_conv.get("questions_asked"):
                    state["questions_asked"] = json.loads(active_conv["questions_asked"])
            except (TypeError, ValueError, json.JSONDecodeError):
                state["questions_asked"] = []

        payload = {
            "conversation_id": conversation_id,
            "message": message,
            "conversation_state": state,
        }

        response = requests.post(
            f"{AI_TRIAGE_URL}/api/v1/triage",
            json=payload,
            timeout=(3.05, TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or not _REQUIRED_RESPONSE_FIELDS.issubset(result):
            raise ValueError("AI triage returned an invalid response shape")
        return result
    except (requests.RequestException, ValueError, TypeError) as exc:
        print(f"\n⚠️ [AI TRIAGE EXCEPTION]: {type(exc).__name__}")
        return None
    finally:
        conn.close()
