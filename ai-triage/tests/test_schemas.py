import pytest
from pydantic import ValidationError

from app.schemas import OllamaResponse, TriageRequest


def valid_ollama_payload():
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


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("intent", "delete_everything"),
        ("category", "database"),
        ("subcategory", "made_up"),
        ("priority", "urgent"),
        ("confidence", -0.01),
        ("confidence", 1.01),
        ("next_question_key", "model_generated_question"),
    ],
)
def test_ollama_response_rejects_invalid_enums_and_bounds(field, invalid_value):
    payload = valid_ollama_payload()
    payload[field] = invalid_value

    with pytest.raises(ValidationError):
        OllamaResponse.model_validate(payload)


def test_ollama_response_rejects_model_generated_question_text():
    payload = valid_ollama_payload()
    payload["suggested_response"] = "Teks buatan model tidak boleh diteruskan"

    with pytest.raises(ValidationError):
        OllamaResponse.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"conversation_id": "", "message": "printer rusak"},
        {"conversation_id": "123", "message": ""},
        {"conversation_id": "123", "message": "x" * 4097},
        {
            "conversation_id": "123",
            "message": "printer rusak",
            "unexpected": True,
        },
    ],
)
def test_triage_request_rejects_invalid_input(payload):
    with pytest.raises(ValidationError):
        TriageRequest.model_validate(payload)
