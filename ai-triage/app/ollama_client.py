import json
import re
from typing import Optional

import httpx
from pydantic import ValidationError

from .config import settings
from .schemas import OllamaResponse


COMPACT_ROUTES = {
    "G": ("greeting", "unknown", "unknown", "low", []),
    "ST": ("status_inquiry", "other", "unknown", "low", ["asset_id"]),
    "R0": (
        "service_request",
        "application",
        "unknown",
        "low",
        ["affected_service", "site"],
    ),
    "N0": (
        "incident",
        "network",
        "no_connection",
        "medium",
        ["site", "affected_scope", "connection_type"],
    ),
    "N1": (
        "incident",
        "network",
        "slow_connection",
        "low",
        ["site", "affected_scope", "connection_type"],
    ),
    "N2": ("incident", "network", "wifi", "low", ["site", "affected_scope"]),
    "N3": ("incident", "network", "lan", "low", ["site", "affected_scope"]),
    "N4": ("incident", "network", "vpn", "medium", ["site", "affected_scope"]),
    "P0": (
        "incident",
        "printer",
        "cannot_print",
        "low",
        ["asset_id", "site", "symptom"],
    ),
    "P1": (
        "incident",
        "printer",
        "printer_offline",
        "low",
        ["asset_id", "site", "symptom"],
    ),
    "P2": (
        "incident",
        "printer",
        "paper_jam",
        "low",
        ["asset_id", "site", "symptom"],
    ),
    "P3": (
        "incident",
        "printer",
        "print_quality",
        "low",
        ["asset_id", "site", "symptom"],
    ),
    "C0": (
        "incident",
        "pc_laptop",
        "device_not_powering_on",
        "medium",
        ["asset_id", "site", "symptom"],
    ),
    "C1": (
        "incident",
        "pc_laptop",
        "device_slow",
        "low",
        ["asset_id", "site", "symptom"],
    ),
    "A0": (
        "incident",
        "application",
        "application_error",
        "medium",
        ["affected_service", "site", "affected_scope"],
    ),
    "A1": (
        "service_request",
        "account_access",
        "password_reset",
        "low",
        ["affected_service", "site"],
    ),
    "A2": (
        "incident",
        "account_access",
        "account_locked",
        "medium",
        ["affected_service", "site"],
    ),
    "S0": ("incident", "security", "phishing", "high", ["site"]),
    "S1": ("incident", "security", "malware", "critical", ["site"]),
    "V0": (
        "incident",
        "server_service",
        "service_down",
        "high",
        ["affected_service", "affected_scope", "business_impact"],
    ),
    "O": ("incident", "other", "unknown", "medium", ["site", "symptom"]),
    "U": ("unknown", "unknown", "unknown", "medium", ["site", "symptom"]),
}

COMPACT_SYSTEM_PROMPT = """Classify one Indonesian IT helpdesk message. Return exactly one code and no prose.
G=greeting only; ST=asks existing ticket status; R0=requests installation/access/service;
N0=no network/internet; N1=slow network; N2=Wi-Fi; N3=LAN; N4=VPN;
P0=cannot print; P1=printer offline; P2=paper jam; P3=bad print quality;
C0=PC/laptop will not power on; C1=PC/laptop slow; A0=application error;
A1=password reset; A2=account locked; S0=phishing; S1=malware;
V0=server/service outage; O=other IT incident; U=not enough information or not IT.
Any mention of printer, printing, print, cetak, or kertas must use P0-P3.
Use V0 only when a server, backend, or named shared service is down.
Use G only when the entire message is a greeting without an IT problem.
Choose the most specific code."""


def _clean_json_response(response_text: str) -> str:
    clean_text = re.sub(r"```json\n?", "", response_text)
    return re.sub(r"```\n?", "", clean_text).strip()


def _message_from_prompt(prompt: str) -> str:
    match = re.search(
        r"---BEGIN MESSAGE---\s*(.*?)\s*---END MESSAGE---",
        prompt,
        flags=re.DOTALL,
    )
    return (match.group(1) if match else prompt).strip()


def _compact_extracted_fields(message: str, category: str) -> dict:
    lowered = message.lower()
    fields = {}
    if category not in {"unknown"}:
        fields["symptom"] = message[:500]

    asset_match = re.search(
        r"(?i)\b(?:asset|aset|kode\s+aset|qr)\s*[:#-]?\s*([a-z0-9][a-z0-9-]{3,30})",
        message,
    )
    if asset_match:
        fields["asset_id"] = asset_match.group(1)

    for label in ("wifi", "wi-fi", "lan", "vpn"):
        if label in lowered:
            fields["connection_type"] = "wifi" if label == "wi-fi" else label
            break

    if any(term in lowered for term in ("semua", "seluruh", "banyak user")):
        fields["affected_scope"] = "banyak pengguna"
    elif any(term in lowered for term in ("saya saja", "hanya saya", "cuma saya")):
        fields["affected_scope"] = "satu pengguna"

    return fields


def _compact_response_for_code(
    code: str,
    message: str,
    confidence: float,
) -> OllamaResponse:
    intent, category, subcategory, priority, required_fields = COMPACT_ROUTES[code]
    extracted_fields = _compact_extracted_fields(message, category)
    missing_fields = [
        field for field in required_fields if not extracted_fields.get(field)
    ]
    question_key = missing_fields[0] if missing_fields else None
    return OllamaResponse(
        intent=intent,
        category=category,
        subcategory=subcategory,
        priority=priority,
        confidence=confidence,
        extracted_fields=extracted_fields,
        missing_fields=missing_fields,
        next_question_key=question_key,
    )


def _parse_compact_response(response_text: str, prompt: str) -> OllamaResponse:
    code = json.loads(_clean_json_response(response_text))
    if not isinstance(code, str) or code not in COMPACT_ROUTES:
        raise ValueError("Ollama returned an unknown compact route")
    # A tiny classifier cannot supply calibrated confidence. Keep model-only
    # routes below the default review threshold; deterministic matches below use
    # a higher confidence because their trigger is explicit and inspectable.
    return _compact_response_for_code(
        code,
        _message_from_prompt(prompt),
        0.45 if code == "U" else 0.70,
    )


def classify_known_message(message: str) -> Optional[OllamaResponse]:
    """Route explicit, common helpdesk phrases without waiting for the LLM."""
    lowered = " ".join(message.lower().split())

    if re.fullmatch(
        r"(?:halo|hai|hi|pagi|siang|sore|malam|selamat (?:pagi|siang|sore|malam)|assalamu'?alaikum)[!., ]*",
        lowered,
    ):
        route = "G"
    elif re.search(r"\b(?:status|cek|update)\b.*\b(?:tiket|ticket)\b", lowered):
        route = "ST"
    elif any(term in lowered for term in ("ransomware", "malware", "virus komputer")):
        route = "S1"
    elif any(
        term in lowered
        for term in ("phishing", "email mencurigakan", "link mencurigakan")
    ):
        route = "S0"
    elif re.search(r"\b(?:printer|printing|print|mencetak|cetak)\b", lowered):
        if any(term in lowered for term in ("kertas macet", "paper jam", "nyangkut")):
            route = "P2"
        elif any(
            term in lowered
            for term in ("hasil cetak", "buram", "bergaris", "tinta")
        ):
            route = "P3"
        elif "offline" in lowered:
            route = "P1"
        else:
            route = "P0"
    elif any(
        term in lowered
        for term in ("lupa password", "reset password", "reset kata sandi")
    ):
        route = "A1"
    elif re.search(r"\b(?:akun|account)\b.*\b(?:terkunci|locked|diblokir)\b", lowered):
        route = "A2"
    elif re.search(r"\b(?:install|instal|pasang|minta akses|buat akun)\b", lowered):
        route = "R0"
    elif re.search(r"\b(?:vpn)\b", lowered):
        route = "N4"
    elif re.search(r"\b(?:wi-fi|wifi)\b", lowered):
        route = "N2"
    elif re.search(r"\b(?:lan|ethernet)\b", lowered):
        route = "N3"
    elif re.search(r"\b(?:internet|jaringan|network|koneksi)\b", lowered):
        route = (
            "N1"
            if re.search(r"\b(?:lambat|lemot|slow)\b", lowered)
            else "N0"
        )
    elif re.search(r"\b(?:pc|komputer|laptop)\b", lowered) and re.search(
        r"\b(?:tidak menyala|tak menyala|mati total|tidak hidup)\b",
        lowered,
    ):
        route = "C0"
    elif re.search(r"\b(?:pc|komputer|laptop)\b", lowered) and re.search(
        r"\b(?:lambat|lemot|slow)\b",
        lowered,
    ):
        route = "C1"
    elif re.search(r"\b(?:server|backend|layanan|service)\b", lowered) and re.search(
        r"\b(?:down|mati|tidak bisa diakses|unavailable)\b",
        lowered,
    ):
        route = "V0"
    elif re.search(r"\b(?:aplikasi|application|sap|erp|outlook)\b", lowered) and re.search(
        r"\b(?:error|gagal|bermasalah|tidak bisa)\b",
        lowered,
    ):
        route = "A0"
    else:
        return None

    return _compact_response_for_code(route, message, 0.95)


async def call_ollama(
    prompt: str,
    system_prompt: str,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[OllamaResponse]:
    """
    Call Ollama and return only output that satisfies the strict triage schema.

    A client may be injected by tests. Production calls own and close their client.
    """
    url = f"{settings.ollama_base_url}/api/generate"
    compact_mode = settings.ollama_compact_mode
    payload = {
        "model": settings.ollama_model,
        "prompt": _message_from_prompt(prompt) if compact_mode else prompt,
        "system": COMPACT_SYSTEM_PROMPT if compact_mode else system_prompt,
        "stream": False,
        "format": (
            {"type": "string", "enum": list(COMPACT_ROUTES)}
            if compact_mode
            else OllamaResponse.model_json_schema()
        ),
        "think": settings.ollama_think,
        "options": {
            "temperature": settings.ollama_temperature,
            "num_predict": (
                min(settings.ollama_num_predict, 8)
                if compact_mode
                else settings.ollama_num_predict
            ),
        },
    }

    owns_client = client is None
    request_client = client or httpx.AsyncClient()
    try:
        response = await request_client.post(
            url,
            json=payload,
            timeout=settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Ollama response envelope must be a JSON object")

        response_text = data.get("response")
        if not isinstance(response_text, str) or not response_text.strip():
            raise ValueError("Ollama response envelope has no generated JSON")

        if compact_mode:
            return _parse_compact_response(response_text, prompt)
        return OllamaResponse.model_validate_json(_clean_json_response(response_text))
    except (httpx.HTTPError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        # Do not log generated text or prompts; either may contain user data.
        print(f"Ollama API Error: {type(exc).__name__}")
        return None
    finally:
        if owns_client:
            await request_client.aclose()
