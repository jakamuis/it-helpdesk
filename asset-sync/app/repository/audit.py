"""Privacy-preserving persistence for asset-sync audit records.

Audit rows are useful for proving which input was evaluated, but they must not
become a second copy of the Datasheet. Requests are therefore represented by a
deterministic digest and their top-level field names only. Response and error
details are reduced to bounded operational metadata.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import SyncHistory


_SAFE_RESPONSE_STATUSES = frozenset(
    {
        "blocked",
        "created",
        "error",
        "unchanged",
        "updated",
        "would_create",
        "would_update",
    }
)
_ERROR_CODE_PATTERN = re.compile(r"\bERROR_[A-Z0-9_]{1,58}\b")
_HTTP_STATUS_PATTERN = re.compile(
    r"\b(?:HTTP(?:\s+status)?|status(?:\s+code)?)\D{0,8}([1-5][0-9]{2})\b",
    re.IGNORECASE,
)
_EXCEPTION_CODE_PATTERN = re.compile(
    r"\b[A-Z][A-Za-z0-9]{0,54}(?:Error|Exception|Timeout)\b"
)
_MAX_ERROR_CODES = 4


def _canonical_request_bytes(payload: Mapping[str, Any]) -> bytes:
    """Return deterministic strict JSON bytes for request fingerprinting."""

    if not isinstance(payload, Mapping):
        raise TypeError("Audit request payload must be a mapping")
    if not all(isinstance(field, str) for field in payload):
        raise TypeError("Audit request payload field names must be strings")

    try:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Audit request payload is not strict JSON: {exc}") from exc
    return serialized.encode("utf-8")


def _request_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    canonical = _canonical_request_bytes(payload)
    return {
        "fields_present": sorted(payload.keys()),
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }


def _response_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only typed, operational response fields and never message text."""

    if not isinstance(payload, Mapping):
        raise TypeError("Audit response payload must be a mapping")

    metadata: dict[str, Any] = {}
    status = payload.get("status")
    if isinstance(status, str) and status in _SAFE_RESPONSE_STATUSES:
        metadata["status"] = status

    glpi_id = payload.get("glpi_id")
    if isinstance(glpi_id, int) and not isinstance(glpi_id, bool) and glpi_id >= 0:
        metadata["glpi_id"] = glpi_id

    dry_run = payload.get("dry_run")
    if isinstance(dry_run, bool):
        metadata["dry_run"] = dry_run

    # Presence is useful while free-form text may contain asset data, API
    # response bodies, or credentials.
    metadata["message_present"] = bool(payload.get("message"))
    return metadata


def _error_metadata(error: str) -> str:
    """Fingerprint an error while retaining bounded machine-readable codes."""

    normalized = str(error)
    codes = set(_ERROR_CODE_PATTERN.findall(normalized))
    codes.update(f"HTTP_{match}" for match in _HTTP_STATUS_PATTERN.findall(normalized))

    lowered = normalized.lower()
    if "timed out" in lowered or "timeout" in lowered:
        codes.add("TIMEOUT")
    if "connection refused" in lowered:
        codes.add("CONNECTION_REFUSED")
    if "certificate verify failed" in lowered:
        codes.add("TLS_VERIFY_FAILED")

    # Exception class names are less specific than GLPI, HTTP, and transport
    # codes, so add them only after collecting those higher-value signals.
    prioritized_codes = sorted(codes)
    prioritized_codes.extend(
        code
        for code in sorted(set(_EXCEPTION_CODE_PATTERN.findall(normalized)))
        if code not in codes
    )

    metadata = {
        "codes": prioritized_codes[:_MAX_ERROR_CODES],
        "length": len(normalized),
        "sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
    }
    # Compact JSON plus bounded code extraction keeps this below a fixed upper
    # bound regardless of an upstream response body's size.
    return json.dumps(metadata, separators=(",", ":"), sort_keys=True)


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_sync(
        self,
        qrcode: str,
        action: str,
        status: str,
        duration: float,
        glpi_id: int = None,
        request_payload: dict = None,
        response_payload: dict = None,
        error: str = None,
    ) -> SyncHistory:
        request_audit = (
            json.dumps(_request_metadata(request_payload), separators=(",", ":"), sort_keys=True)
            if request_payload is not None
            else None
        )
        response_audit = (
            json.dumps(_response_metadata(response_payload), separators=(",", ":"), sort_keys=True)
            if response_payload is not None
            else None
        )

        record = SyncHistory(
            qrcode=qrcode,
            action=action,
            status=status,
            duration=duration,
            glpi_id=glpi_id,
            request_payload=request_audit,
            response_payload=response_audit,
            error=_error_metadata(error) if error is not None else None,
        )

        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record
