import hashlib
import sqlite3

import pytest

from app.audit import init_db
from app.config import settings
from app.questions import FALLBACK_QUESTION, QUESTION_TEMPLATES
from app.redaction import redact_sensitive_data
from app.rules import apply_deterministic_rules
from app.schemas import ConversationState, OllamaResponse, TriageRequest
from app.triage_service import process_triage


@pytest.fixture
def audit_db(monkeypatch, tmp_path):
    db_path = tmp_path / "ai_triage_audit.db"
    monkeypatch.setattr(settings, "ai_audit_db_path", str(db_path))
    init_db()
    return db_path


def test_redact_password():
    text = "password: my_super_secret"
    clean = redact_sensitive_data(text)
    assert "[REDACTED_PASSWORD]" in clean
    assert "my_super_secret" not in clean


def test_redact_indonesian_password_phrase():
    text = "password saya adalah Rahasia123"
    clean = redact_sensitive_data(text)
    assert "[REDACTED_PASSWORD]" in clean
    assert "Rahasia123" not in clean


def test_redact_otp():
    text = "kode 123456"
    clean = redact_sensitive_data(text)
    assert "[REDACTED_OTP]" in clean
    assert "123456" not in clean


def test_deterministic_rules_critical():
    human, reason, category, priority = apply_deterministic_rules(
        "pabrik mati total bos", "unknown", "unknown", "medium", 0.9, 0.75
    )
    assert human is True
    assert priority == "critical"
    assert category == "network"
    assert "business impact" in reason.lower()


def test_deterministic_rules_security():
    human, reason, category, priority = apply_deterministic_rules(
        "kena hack data bocor", "unknown", "unknown", "medium", 0.9, 0.75
    )
    assert human is True
    assert priority == "critical"
    assert category == "security"
    assert "security incident" in reason.lower()


def test_model_security_category_always_requires_human_review():
    human, reason, category, priority = apply_deterministic_rules(
        "Ada email yang sepertinya mencurigakan",
        "incident",
        "security",
        "medium",
        0.9,
        0.75,
    )
    assert human is True
    assert category == "security"
    assert priority == "high"
    assert "requires human review" in reason.lower()


def test_non_security_leak_word_does_not_trigger_security():
    human, reason, category, priority = apply_deterministic_rules(
        "atap ruang server bocor saat hujan",
        "incident",
        "other",
        "medium",
        0.9,
        0.75,
    )
    assert human is False
    assert reason is None
    assert category == "other"
    assert priority == "medium"


def test_deterministic_rules_preserve_multiple_reasons():
    human, reason, category, priority = apply_deterministic_rules(
        "pabrik mati dan saya ingin bicara dengan admin",
        "incident",
        "unknown",
        "medium",
        0.5,
        0.75,
    )
    assert human is True
    assert category == "network"
    assert priority == "critical"
    assert "business impact" in reason.lower()
    assert "requested human" in reason.lower()
    assert "below threshold" in reason.lower()


@pytest.mark.asyncio
async def test_triage_uses_server_owned_question_and_persists_audit(
    monkeypatch,
    audit_db,
):
    async def mock_call_ollama(prompt, system):
        return OllamaResponse(
            intent="incident",
            category="printer",
            subcategory="unknown",
            priority="low",
            confidence=0.9,
            extracted_fields={"symptom": None},
            missing_fields=["symptom"],
            next_question_key="printer_symptom",
        )

    monkeypatch.setattr("app.triage_service.call_ollama", mock_call_ollama)
    monkeypatch.setattr("app.triage_service.classify_known_message", lambda _: None)

    request = TriageRequest(
        conversation_id="123",
        message="printer rusak",
        conversation_state=ConversationState(),
    )
    response = await process_triage(request)

    assert response.category == "printer"
    assert response.status == "collecting_information"
    assert response.next_question_key == "printer_symptom"
    assert response.suggested_response == QUESTION_TEMPLATES["printer_symptom"]
    assert response.human_review_required is False

    with sqlite3.connect(audit_db) as conn:
        row = conn.execute(
            """
            SELECT conversation_id_hash, message_hash, ai_category, fallback_used
            FROM audit_log
            """
        ).fetchone()

    assert row == (
        hashlib.sha256(b"123").hexdigest(),
        hashlib.sha256(b"printer rusak").hexdigest(),
        "printer",
        0,
    )


@pytest.mark.asyncio
async def test_critical_rule_bypasses_ollama_outage(monkeypatch, audit_db):
    async def unavailable_ollama(prompt, system):
        raise AssertionError("critical incidents must not depend on Ollama")

    monkeypatch.setattr("app.triage_service.call_ollama", unavailable_ollama)
    monkeypatch.setattr("app.triage_service.classify_known_message", lambda _: None)

    response = await process_triage(
        TriageRequest(conversation_id="critical-1", message="pabrik mati total")
    )

    assert response.intent == "incident"
    assert response.category == "network"
    assert response.priority == "critical"
    assert response.status == "ready_for_ticket"
    assert response.human_review_required is True
    assert response.fallback_used is False
    assert "business impact" in response.escalation_reason.lower()


@pytest.mark.asyncio
async def test_human_request_survives_ollama_failure(monkeypatch, audit_db):
    async def unavailable_ollama(prompt, system):
        return None

    monkeypatch.setattr("app.triage_service.call_ollama", unavailable_ollama)

    response = await process_triage(
        TriageRequest(
            conversation_id="human-1",
            message="Saya ingin bicara dengan admin",
        )
    )

    assert response.status == "ready_for_ticket"
    assert response.human_review_required is True
    assert response.fallback_used is True
    assert response.suggested_response is None
    assert "requested human" in response.escalation_reason.lower()
    assert "service unavailable" in response.escalation_reason.lower()


@pytest.mark.asyncio
async def test_standard_outage_uses_server_owned_fallback(monkeypatch, audit_db):
    async def unavailable_ollama(prompt, system):
        return None

    monkeypatch.setattr("app.triage_service.call_ollama", unavailable_ollama)
    monkeypatch.setattr("app.triage_service.classify_known_message", lambda _: None)

    response = await process_triage(
        TriageRequest(conversation_id="fallback-1", message="printer bermasalah")
    )

    assert response.status == "collecting_information"
    assert response.human_review_required is True
    assert response.fallback_used is True
    assert response.suggested_response == FALLBACK_QUESTION


@pytest.mark.asyncio
async def test_explicit_printer_issue_uses_fast_local_route(monkeypatch, audit_db):
    async def ollama_must_not_run(prompt, system):
        raise AssertionError("known routes must not wait for Ollama")

    monkeypatch.setattr("app.triage_service.call_ollama", ollama_must_not_run)
    response = await process_triage(
        TriageRequest(
            conversation_id="local-printer-1",
            message="Printer QR AST-1042 tidak bisa mencetak kertas macet",
        )
    )

    assert response.category == "printer"
    assert response.subcategory == "paper_jam"
    assert response.extracted_fields.asset_id == "AST-1042"
    assert response.human_review_required is False
    assert response.model == "deterministic-routing-v1"


@pytest.mark.asyncio
async def test_short_followup_answer_preserves_context_and_advances_question(
    monkeypatch,
    audit_db,
):
    async def mock_call_ollama(prompt, system):
        raise AssertionError("a direct answer must not wait for Ollama")

    monkeypatch.setattr("app.triage_service.call_ollama", mock_call_ollama)
    response = await process_triage(
        TriageRequest(
            conversation_id="followup-1",
            message="AST-1042",
            conversation_state=ConversationState(
                intent="incident",
                category="printer",
                subcategory="paper_jam",
                symptom="kertas macet",
                questions_asked=["asset_id"],
            ),
        )
    )

    assert response.intent == "incident"
    assert response.category == "printer"
    assert response.subcategory == "paper_jam"
    assert response.extracted_fields.asset_id == "AST-1042"
    assert response.extracted_fields.symptom == "kertas macet"
    assert response.missing_fields == ["site"]
    assert response.next_question_key == "site"
    assert response.status == "collecting_information"
    assert response.model == "conversation-context-v1"


@pytest.mark.asyncio
async def test_last_followup_answer_completes_collection_without_repeat(
    monkeypatch,
    audit_db,
):
    async def mock_call_ollama(prompt, system):
        raise AssertionError("a direct answer must not wait for Ollama")

    monkeypatch.setattr("app.triage_service.call_ollama", mock_call_ollama)
    response = await process_triage(
        TriageRequest(
            conversation_id="followup-2",
            message="Jakarta",
            conversation_state=ConversationState(
                intent="incident",
                category="printer",
                subcategory="paper_jam",
                asset_id="AST-1042",
                symptom="kertas macet",
                questions_asked=["asset_id", "site"],
            ),
        )
    )

    assert response.extracted_fields.site == "Jakarta"
    assert response.missing_fields == []
    assert response.next_question_key is None
    assert response.suggested_response is None
    assert response.status == "ready_for_ticket"
