import os
import time
from typing import Dict, List, Optional, Tuple

from .audit import log_prediction
from .config import settings
from .ollama_client import call_ollama, classify_known_message
from .questions import FALLBACK_QUESTION, render_question
from .redaction import redact_sensitive_data
from .rules import apply_deterministic_rules
from .schemas import (
    Category,
    ExtractedFields,
    Intent,
    OllamaResponse,
    Priority,
    QuestionKey,
    Subcategory,
    TriageRequest,
    TriageResponse,
)


_QUESTION_TO_FIELD = {"printer_symptom": "symptom"}
_CATEGORY_REQUIRED_FIELDS = {
    "network": ["site", "affected_scope", "connection_type"],
    "printer": ["asset_id", "site", "symptom"],
    "pc_laptop": ["asset_id", "site", "symptom"],
    "application": ["affected_service", "site", "affected_scope"],
    "account_access": ["affected_service", "site"],
    "security": ["site"],
    "server_service": ["affected_service", "affected_scope", "business_impact"],
    "other": ["site", "symptom"],
    "unknown": ["site", "symptom"],
}


def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "triage_system.txt")
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    return "You are an IT Helpdesk AI. Return only the requested JSON classification."


def _join_reasons(*reasons: Optional[str]) -> str:
    return "; ".join(reason for reason in reasons if reason)


def _question_for_field(field: str, category: Category) -> QuestionKey:
    if field == "symptom" and category == "printer":
        return "printer_symptom"
    return field  # type: ignore[return-value]


def _answer_from_message(field: str, message: str) -> str:
    """Treat the next message as the answer to the last server-owned question."""
    answer = message.strip()
    if field == "connection_type":
        lowered = answer.lower()
        for label in ("wifi", "wi-fi", "lan", "vpn"):
            if label in lowered:
                return "wifi" if label == "wi-fi" else label
    return answer[:500 if field in {"symptom", "business_impact"} else 200]


def _required_fields(intent: Intent, category: Category) -> List[str]:
    if intent == "status_inquiry":
        return ["asset_id"]
    if intent == "greeting":
        return []
    return _CATEGORY_REQUIRED_FIELDS[category]


def _classify_conversation_answer(
    request: TriageRequest,
    message: str,
) -> Optional[OllamaResponse]:
    """Bind a short reply to the last question using durable conversation state."""
    state = request.conversation_state
    if not state.category or not state.questions_asked:
        return None

    last_question = state.questions_asked[-1]
    answer_field = _QUESTION_TO_FIELD.get(last_question, last_question)
    if answer_field not in ExtractedFields.model_fields:
        return None
    if getattr(state, answer_field, None):
        return None

    extracted = {answer_field: _answer_from_message(answer_field, message)}
    known_fields = {
        field: getattr(state, field, None)
        for field in ExtractedFields.model_fields
    }
    known_fields.update(extracted)
    missing_fields = [
        field
        for field in _required_fields(state.intent or "incident", state.category)
        if not known_fields.get(field)
    ]
    question_key = (
        _question_for_field(missing_fields[0], state.category)
        if missing_fields
        else None
    )
    return OllamaResponse(
        intent=state.intent or "incident",
        category=state.category,
        subcategory=state.subcategory or "unknown",
        priority=state.priority or "medium",
        confidence=0.95,
        extracted_fields=extracted,
        missing_fields=missing_fields,
        next_question_key=question_key,
    )


def _merge_conversation_context(
    request: TriageRequest,
    message: str,
    result: OllamaResponse,
) -> Tuple[
    Intent,
    Category,
    Subcategory,
    ExtractedFields,
    List[str],
    Optional[QuestionKey],
]:
    """Merge a model turn with durable state and never repeat answered questions."""
    state = request.conversation_state
    field_names = set(ExtractedFields.model_fields)
    prior_fields: Dict[str, str] = {
        key: value
        for key, value in state.model_dump().items()
        if key in field_names and isinstance(value, str) and value
    }
    current_fields: Dict[str, str] = result.extracted_fields.model_dump(
        exclude_none=True
    )

    # The middleware records a question only after sending it. On the next turn,
    # a short answer such as "PRN-1042" or "Jakarta" can therefore be captured
    # without asking the small classifier to perform free-form extraction.
    if state.questions_asked:
        last_question = state.questions_asked[-1]
        answer_field = _QUESTION_TO_FIELD.get(last_question, last_question)
        if answer_field in field_names and not prior_fields.get(answer_field):
            current_fields.setdefault(
                answer_field,
                _answer_from_message(answer_field, message),
            )

    if result.subcategory in {"wifi", "lan", "vpn"}:
        current_fields.setdefault("connection_type", result.subcategory)

    merged_fields = {**prior_fields, **current_fields}
    extracted_fields = ExtractedFields.model_validate(merged_fields)

    intent = result.intent
    category = result.category
    subcategory = result.subcategory
    preserved_context = bool(state.category and category == "unknown")
    if preserved_context:
        category = state.category
        if intent == "unknown" and state.intent:
            intent = state.intent
        if subcategory == "unknown" and state.subcategory:
            subcategory = state.subcategory

    if preserved_context:
        required_fields = _required_fields(intent, category)
    else:
        required_fields = list(result.missing_fields)

    missing_fields = [
        field for field in required_fields if not merged_fields.get(field)
    ]
    asked = set(state.questions_asked)
    next_question_key = next(
        (
            _question_for_field(field, category)
            for field in missing_fields
            if _question_for_field(field, category) not in asked
        ),
        None,
    )
    return (
        intent,
        category,
        subcategory,
        extracted_fields,
        missing_fields,
        next_question_key,
    )


def get_fallback_response(
    preflight_human_review: bool = False,
    preflight_reason: Optional[str] = None,
    category: Category = "unknown",
    priority: Priority = "medium",
) -> TriageResponse:
    unavailable_reason = "AI service unavailable or returned invalid response"
    return TriageResponse(
        intent="unknown",
        category=category,
        subcategory="unknown",
        priority=priority,
        confidence=0.0,
        status="ready_for_ticket" if preflight_human_review else "collecting_information",
        human_review_required=True,
        escalation_reason=_join_reasons(preflight_reason, unavailable_reason),
        extracted_fields=ExtractedFields(),
        missing_fields=[],
        suggested_response=None if preflight_human_review else FALLBACK_QUESTION,
        model=settings.ollama_model,
        fallback_used=True,
    )


def get_critical_rule_response(
    reason: str,
    category: Category,
    priority: Priority,
) -> TriageResponse:
    return TriageResponse(
        intent="incident",
        category=category,
        subcategory="unknown",
        priority=priority,
        confidence=1.0,
        status="ready_for_ticket",
        human_review_required=True,
        escalation_reason=reason,
        extracted_fields=ExtractedFields(),
        missing_fields=[],
        next_question_key=None,
        suggested_response=None,
        model="deterministic-rules-v1",
        fallback_used=False,
    )


def _log_response(
    request: TriageRequest,
    clean_message: str,
    response: TriageResponse,
    start_time: float,
) -> None:
    latency_ms = int((time.monotonic() - start_time) * 1000)
    log_prediction(
        request.conversation_id,
        clean_message,
        response.model_dump(),
        latency_ms,
    )


async def process_triage(request: TriageRequest) -> TriageResponse:
    start_time = time.monotonic()
    clean_message = redact_sensitive_data(request.message)

    # Evaluate local safety rules before any model dependency. Critical business
    # and security incidents bypass Ollama so escalation cannot be delayed or lost.
    preflight_human, preflight_reason, preflight_category, preflight_priority = (
        apply_deterministic_rules(
            clean_message,
            "unknown",
            "unknown",
            "medium",
            1.0,
            0.0,
        )
    )
    if preflight_human and preflight_priority == "critical":
        response = get_critical_rule_response(
            preflight_reason or "Critical incident detected",
            preflight_category,
            preflight_priority,
        )
        _log_response(request, clean_message, response, start_time)
        return response

    system_prompt = get_system_prompt()
    user_prompt = f"""
    CONVERSATION STATE:
    {request.conversation_state.model_dump_json(indent=2)}

    USER MESSAGE:
    ---BEGIN MESSAGE---
    {clean_message}
    ---END MESSAGE---
    """

    known_route = (
        classify_known_message(clean_message) if settings.ollama_compact_mode else None
    )
    conversation_route = (
        _classify_conversation_answer(request, clean_message)
        if settings.ollama_compact_mode and known_route is None
        else None
    )
    local_route = known_route or conversation_route
    ollama_res = local_route or await call_ollama(user_prompt, system_prompt)

    if not ollama_res:
        response = get_fallback_response(
            preflight_human,
            preflight_reason,
            preflight_category,
            preflight_priority,
        )
        _log_response(request, clean_message, response, start_time)
        return response

    (
        intent,
        contextual_category,
        subcategory,
        extracted_fields,
        missing_fields,
        next_question_key,
    ) = _merge_conversation_context(request, clean_message, ollama_res)

    human_review, reason, new_cat, new_prio = apply_deterministic_rules(
        clean_message,
        intent,
        contextual_category,
        ollama_res.priority,
        ollama_res.confidence,
        settings.ai_confidence_threshold
    )

    status = "collecting_information"
    if human_review or not missing_fields or next_question_key is None:
        status = "ready_for_ticket"

    next_question_key = next_question_key if status == "collecting_information" else None
    response = TriageResponse(
        intent=intent,
        category=new_cat,
        subcategory=subcategory,
        priority=new_prio,
        confidence=ollama_res.confidence,
        status=status,
        human_review_required=human_review,
        escalation_reason=reason,
        extracted_fields=extracted_fields,
        missing_fields=missing_fields,
        next_question_key=next_question_key,
        suggested_response=render_question(next_question_key),
        model=(
            "deterministic-routing-v1"
            if known_route
            else "conversation-context-v1"
            if conversation_route
            else settings.ollama_model
        ),
        fallback_used=False,
    )

    _log_response(request, clean_message, response, start_time)
    return response
