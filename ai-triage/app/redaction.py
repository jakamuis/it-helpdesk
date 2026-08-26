import re


_PASSWORD_PATTERN = re.compile(
    r"(?i)\b(password|pwd|sandi|kata\s+sandi)\b"
    r"(?:\s+(?:saya|aku|nya))?\s*(?::|=|adalah|yaitu)?\s+([^\s,;]+)"
)
_OTP_PATTERN = re.compile(
    r"(?i)\b(otp|pin|kode(?:\s+(?:otp|verifikasi))?)\b[\s:=]+(\d{4,8})"
)
_TOKEN_PATTERN = re.compile(
    r"(?i)\b(token|key|api[-_]?key|secret)\b[\s:=]+([a-zA-Z0-9_\-.]{15,})"
)

def redact_sensitive_data(text: str) -> str:
    """
    Redacts obvious sensitive information from text before sending to LLM.
    """
    if not text:
        return text

    text = _PASSWORD_PATTERN.sub(r"\1 [REDACTED_PASSWORD]", text)

    text = _OTP_PATTERN.sub(r"\1 [REDACTED_OTP]", text)

    text = _TOKEN_PATTERN.sub(r"\1 [REDACTED_TOKEN]", text)

    return text
