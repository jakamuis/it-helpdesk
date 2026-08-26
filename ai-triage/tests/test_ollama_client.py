import json

import httpx
import pytest

from app.config import settings
from app.ollama_client import (
    COMPACT_ROUTES,
    COMPACT_SYSTEM_PROMPT,
    call_ollama,
    classify_known_message,
)


def valid_generated_response():
    return {
        "intent": "incident",
        "category": "printer",
        "subcategory": "paper_jam",
        "priority": "low",
        "confidence": 0.95,
        "extracted_fields": {"symptom": "kertas macet"},
        "missing_fields": [],
        "next_question_key": None,
    }


def compact_prompt(message):
    return f"""
    CONVERSATION STATE:
    {{}}

    USER MESSAGE:
    ---BEGIN MESSAGE---
    {message}
    ---END MESSAGE---
    """


@pytest.fixture
def full_schema_mode(monkeypatch):
    monkeypatch.setattr(settings, "ollama_compact_mode", False)


@pytest.fixture
def compact_mode(monkeypatch):
    monkeypatch.setattr(settings, "ollama_compact_mode", True)


@pytest.mark.asyncio
async def test_call_ollama_sends_schema_and_bounded_generation_options(
    monkeypatch,
    full_schema_mode,
):
    captured_payload = {}

    def handler(request):
        captured_payload.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={"response": json.dumps(valid_generated_response())},
        )

    monkeypatch.setattr(settings, "ollama_think", False)
    monkeypatch.setattr(settings, "ollama_num_predict", 256)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await call_ollama("prompt", "system", client=client)

    assert result is not None
    assert result.category == "printer"
    assert isinstance(captured_payload["format"], dict)
    assert "properties" in captured_payload["format"]
    assert captured_payload["think"] is False
    assert captured_payload["options"]["num_predict"] == 256


@pytest.mark.asyncio
async def test_call_ollama_handles_http_status_error():
    def handler(request):
        return httpx.Response(503, json={"error": "model unavailable"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await call_ollama("prompt", "system", client=client)

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "generated_response",
    [
        "not-json",
        json.dumps({**valid_generated_response(), "priority": "urgent"}),
        json.dumps(
            {
                **valid_generated_response(),
                "suggested_response": "Teks dari model",
            }
        ),
    ],
)
async def test_call_ollama_handles_invalid_generated_json(
    generated_response,
    full_schema_mode,
):
    def handler(request):
        return httpx.Response(200, json={"response": generated_response})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await call_ollama("prompt", "system", client=client)

    assert result is None


@pytest.mark.asyncio
async def test_call_ollama_handles_invalid_response_envelope():
    def handler(request):
        return httpx.Response(200, json=["unexpected"])

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await call_ollama("prompt", "system", client=client)

    assert result is None


@pytest.mark.asyncio
async def test_compact_mode_sends_route_enum_prompt_and_eight_token_cap(
    monkeypatch,
    compact_mode,
):
    captured_payload = {}

    def handler(request):
        captured_payload.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"response": json.dumps("G")})

    monkeypatch.setattr(settings, "ollama_num_predict", 256)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await call_ollama(
            compact_prompt("halo"),
            "full schema prompt must not be sent",
            client=client,
        )

    assert result is not None
    assert captured_payload["system"] == COMPACT_SYSTEM_PROMPT
    assert captured_payload["prompt"] == "halo"
    assert captured_payload["format"] == {
        "type": "string",
        "enum": list(COMPACT_ROUTES),
    }
    assert captured_payload["options"]["num_predict"] == 8


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "expected"),
    [
        (
            "P2",
            {
                "intent": "incident",
                "category": "printer",
                "subcategory": "paper_jam",
                "priority": "low",
                "confidence": 0.70,
            },
        ),
        (
            "U",
            {
                "intent": "unknown",
                "category": "unknown",
                "subcategory": "unknown",
                "priority": "medium",
                "confidence": 0.45,
            },
        ),
    ],
)
async def test_compact_response_maps_route_to_strict_response(
    route,
    expected,
    compact_mode,
):
    def handler(request):
        return httpx.Response(200, json={"response": json.dumps(route)})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await call_ollama(
            compact_prompt("printer bermasalah"),
            "unused full schema prompt",
            client=client,
        )

    assert result is not None
    for field, value in expected.items():
        assert getattr(result, field) == value


@pytest.mark.asyncio
async def test_compact_mode_extracts_local_fields_and_asks_first_missing_field(
    compact_mode,
):
    message = "Printer QR AST-1234 pakai Wi-Fi, cuma saya, kertas macet"

    def handler(request):
        return httpx.Response(200, json={"response": json.dumps("P2")})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await call_ollama(
            compact_prompt(message),
            "unused full schema prompt",
            client=client,
        )

    assert result is not None
    assert result.extracted_fields.asset_id == "AST-1234"
    assert result.extracted_fields.connection_type == "wifi"
    assert result.extracted_fields.affected_scope == "satu pengguna"
    assert result.extracted_fields.symptom == message
    assert result.missing_fields == ["site"]
    assert result.next_question_key == "site"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "generated_response",
    [
        json.dumps("NOT_A_ROUTE"),
        json.dumps({"route": "P2"}),
        "P2",
    ],
)
async def test_compact_mode_rejects_invalid_route_response(
    generated_response,
    compact_mode,
):
    def handler(request):
        return httpx.Response(200, json={"response": generated_response})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await call_ollama(
            compact_prompt("printer rusak"),
            "unused full schema prompt",
            client=client,
        )

    assert result is None


@pytest.mark.parametrize(
    ("message", "category", "subcategory"),
    [
        ("Printer tidak bisa mencetak kertas macet", "printer", "paper_jam"),
        ("Internet kantor sangat lemot", "network", "slow_connection"),
        ("Laptop saya tidak menyala", "pc_laptop", "device_not_powering_on"),
        ("Ada email phishing", "security", "phishing"),
        ("Halo!", "unknown", "unknown"),
    ],
)
def test_known_messages_are_routed_locally(message, category, subcategory):
    result = classify_known_message(message)

    assert result is not None
    assert result.category == category
    assert result.subcategory == subcategory
    assert result.confidence == 0.95


def test_ambiguous_message_is_left_for_ollama():
    assert classify_known_message("Tolong dibantu, pekerjaan saya terganggu") is None
