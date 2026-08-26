from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


Intent = Literal[
    "incident",
    "service_request",
    "quick_troubleshooting",
    "status_inquiry",
    "greeting",
    "unknown",
]
Category = Literal[
    "network",
    "printer",
    "pc_laptop",
    "application",
    "account_access",
    "security",
    "server_service",
    "other",
    "unknown",
]
Subcategory = Literal[
    "slow_connection",
    "no_connection",
    "wifi",
    "lan",
    "vpn",
    "printer_offline",
    "paper_jam",
    "print_quality",
    "cannot_print",
    "device_not_powering_on",
    "device_slow",
    "application_error",
    "password_reset",
    "account_locked",
    "phishing",
    "malware",
    "service_down",
    "unknown",
]
Priority = Literal["low", "medium", "high", "critical"]
TriageStatus = Literal["collecting_information", "ready_for_ticket"]
MissingField = Literal[
    "asset_id",
    "site",
    "symptom",
    "connection_type",
    "affected_scope",
    "affected_service",
    "business_impact",
]
QuestionKey = Literal[
    "asset_id",
    "site",
    "symptom",
    "printer_symptom",
    "connection_type",
    "affected_scope",
    "affected_service",
    "business_impact",
]

ShortText = Annotated[str, Field(min_length=1, max_length=200)]
DetailText = Annotated[str, Field(min_length=1, max_length=500)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConversationState(StrictModel):
    user_name: Optional[ShortText] = None
    site: Optional[ShortText] = None
    asset_id: Optional[ShortText] = None
    intent: Optional[Intent] = None
    category: Optional[Category] = None
    subcategory: Optional[Subcategory] = None
    priority: Optional[Priority] = None
    symptom: Optional[DetailText] = None
    connection_type: Optional[ShortText] = None
    affected_scope: Optional[ShortText] = None
    affected_service: Optional[ShortText] = None
    business_impact: Optional[DetailText] = None
    questions_asked: List[QuestionKey] = Field(default_factory=list, max_length=16)


class TriageRequest(StrictModel):
    conversation_id: str = Field(min_length=1, max_length=256)
    message: str = Field(min_length=1, max_length=4096)
    conversation_state: ConversationState = Field(default_factory=ConversationState)


class ExtractedFields(StrictModel):
    asset_id: Optional[ShortText] = None
    site: Optional[ShortText] = None
    symptom: Optional[DetailText] = None
    connection_type: Optional[ShortText] = None
    affected_scope: Optional[ShortText] = None
    affected_service: Optional[ShortText] = None
    business_impact: Optional[DetailText] = None


class TriageResponse(StrictModel):
    intent: Intent
    category: Category
    subcategory: Subcategory
    priority: Priority
    confidence: float = Field(ge=0.0, le=1.0)
    status: TriageStatus
    human_review_required: bool
    escalation_reason: Optional[DetailText] = None
    extracted_fields: ExtractedFields
    missing_fields: List[MissingField] = Field(max_length=7)
    next_question_key: Optional[QuestionKey] = None
    suggested_response: Optional[DetailText] = None
    model: ShortText
    fallback_used: bool


class OllamaResponse(StrictModel):
    intent: Intent
    category: Category
    subcategory: Subcategory
    priority: Priority
    confidence: float = Field(ge=0.0, le=1.0)
    extracted_fields: ExtractedFields
    missing_fields: List[MissingField] = Field(max_length=7)
    next_question_key: Optional[QuestionKey] = None
