from typing import Optional, Tuple

from .schemas import Category, Priority


BUSINESS_IMPACT_KEYWORDS = (
    "pabrik mati",
    "produksi berhenti",
    "distribusi mandek",
    "semua cabang",
    "seluruh cabang",
    "satu cabang mati",
)
SECURITY_KEYWORDS = (
    "ransomware",
    "malware",
    "phishing",
    "kena hack",
    "data bocor",
    "kebocoran data",
    "akun dibobol",
    "hacker",
)
HUMAN_REQUEST_KEYWORDS = (
    "bicara dengan admin",
    "hubungi manusia",
    "bicara dengan orang",
    "butuh bantuan agen",
)


def apply_deterministic_rules(
    message: str,
    intent: str,
    category: Category,
    priority: Priority,
    confidence: float,
    threshold: float,
) -> Tuple[bool, Optional[str], Category, Priority]:
    """
    Applies rules to override LLM behavior for critical/high-risk cases.
    Returns: (human_review_required, escalation_reason, new_category, new_priority)
    """
    msg_lower = message.lower()

    reasons = []
    new_cat = category
    new_prio = priority

    if any(keyword in msg_lower for keyword in BUSINESS_IMPACT_KEYWORDS):
        reasons.append("Critical business impact detected (factory/production/branch down)")
        new_prio = "critical"
        if new_cat == "unknown":
            new_cat = "network"

    security_keyword_detected = any(
        keyword in msg_lower for keyword in SECURITY_KEYWORDS
    )
    if security_keyword_detected:
        reasons.append("Security incident detected")
        new_prio = "critical"
        new_cat = "security"
    elif new_cat == "security":
        reasons.append("Security classification requires human review")
        if new_prio in {"low", "medium"}:
            new_prio = "high"

    if any(keyword in msg_lower for keyword in HUMAN_REQUEST_KEYWORDS):
        reasons.append("User explicitly requested human agent")

    if confidence < threshold:
        reasons.append(f"Model confidence ({confidence}) below threshold ({threshold})")

    reason = "; ".join(reasons) if reasons else None
    return bool(reasons), reason, new_cat, new_prio
