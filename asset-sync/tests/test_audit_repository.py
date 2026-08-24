import hashlib
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repository.audit import AuditRepository
from app.schemas.asset import AssetSyncRequest


def make_repository():
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return AuditRepository(session), session


@pytest.mark.asyncio
async def test_request_audit_is_deterministic_canonical_hash_and_field_presence_only():
    repository, _ = make_repository()
    first = {
        "user": "Alice",
        "nested": {"z": 2, "a": 1},
        "qrcode": "QR-100",
    }
    second = {
        "qrcode": "QR-100",
        "nested": {"a": 1, "z": 2},
        "user": "Alice",
    }

    first_record = await repository.log_sync(
        "QR-100", "DRY_RUN_UPDATE", "SUCCESS", 0.1, request_payload=first
    )
    second_record = await repository.log_sync(
        "QR-100", "DRY_RUN_UPDATE", "SUCCESS", 0.1, request_payload=second
    )

    canonical = json.dumps(
        first,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    expected = {
        "fields_present": ["nested", "qrcode", "user"],
        "sha256": hashlib.sha256(canonical).hexdigest(),
    }
    assert json.loads(first_record.request_payload) == expected
    assert first_record.request_payload == second_record.request_payload


@pytest.mark.asyncio
async def test_audit_serialization_excludes_asset_values_messages_and_response_bodies():
    repository, _ = make_repository()
    secrets = {
        "user": "PRIVATE-USER-ALICE-8371",
        "comment": "PRIVATE-COMMENT-REPAIR-9921",
        "location": "PRIVATE-LOCATION-FLOOR-7712",
        "value": "PRIVATE-VALUE-123456789-6622",
        "dat_number": "PRIVATE-DAT-00998877-4411",
        "app_token": "PRIVATE-TOKEN-XyZ987654321-5533",
    }
    raw_error_body = "PRIVATE-BODY-SECRET-1199"

    record = await repository.log_sync(
        qrcode="QR-PRIVACY-1",
        action="PREFLIGHT",
        status="ERROR",
        duration=0.2,
        request_payload=secrets,
        response_payload={
            "status": "error",
            "glpi_id": 42,
            "dry_run": True,
            "message": f"Failed for {secrets['dat_number']} using {secrets['app_token']}",
            "raw_response": raw_error_body,
        },
        error=(
            "HTTP status 400 ERROR_WRONG_APP_TOKEN_PARAMETER response body: "
            f"{raw_error_body} {secrets['app_token']}"
        ),
    )

    serialized_fields = "\n".join(
        (record.request_payload, record.response_payload, record.error)
    )
    for secret in (*secrets.values(), raw_error_body):
        assert secret not in serialized_fields

    assert json.loads(record.response_payload) == {
        "dry_run": True,
        "glpi_id": 42,
        "message_present": True,
        "status": "error",
    }
    error_metadata = json.loads(record.error)
    assert error_metadata["codes"] == ["ERROR_WRONG_APP_TOKEN_PARAMETER", "HTTP_400"]
    assert len(error_metadata["sha256"]) == 64
    assert len(record.error) <= 512


@pytest.mark.asyncio
async def test_unknown_response_values_are_not_persisted():
    repository, _ = make_repository()
    secret = "PRIVATE-STATUS-OR-ID-7755"

    record = await repository.log_sync(
        "QR-1",
        "PREFLIGHT",
        "ERROR",
        0.1,
        response_payload={
            "status": secret,
            "glpi_id": secret,
            "dry_run": secret,
            "message": secret,
        },
    )

    assert secret not in record.response_payload
    assert json.loads(record.response_payload) == {"message_present": True}


@pytest.mark.asyncio
async def test_pydantic_model_dump_is_hashed_and_unchanged_status_is_retained():
    repository, _ = make_repository()
    request = AssetSyncRequest(
        qrcode="QR-PYDANTIC-1",
        asset_type="Computer",
        user="PRIVATE-PYDANTIC-USER-4412",
        value="1250000",
    )

    record = await repository.log_sync(
        "QR-PYDANTIC-1",
        "DRY_RUN_NOOP",
        "SUCCESS",
        0.1,
        request_payload=request.model_dump(),
        response_payload={
            "status": "unchanged",
            "glpi_id": 17,
            "message": "Dry-run only",
            "dry_run": True,
        },
    )

    assert "PRIVATE-PYDANTIC-USER-4412" not in record.request_payload
    assert json.loads(record.request_payload)["fields_present"] == sorted(
        AssetSyncRequest.model_fields
    )
    assert json.loads(record.response_payload)["status"] == "unchanged"


@pytest.mark.asyncio
async def test_request_fingerprint_rejects_non_strict_json():
    repository, session = make_repository()

    with pytest.raises(ValueError, match="strict JSON"):
        await repository.log_sync(
            "QR-1",
            "PREFLIGHT",
            "ERROR",
            0.1,
            request_payload={"value": float("nan")},
        )

    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_error_metadata_is_bounded_for_oversized_response_body():
    repository, _ = make_repository()
    oversized_secret = "PRIVATE-OVERSIZED-BODY-" * 100_000

    record = await repository.log_sync(
        "QR-1",
        "PREFLIGHT",
        "ERROR",
        0.1,
        error=f"HTTP 503 ConnectError response body: {oversized_secret}",
    )

    assert oversized_secret[:100] not in record.error
    assert len(record.error.encode("utf-8")) <= 512
    assert json.loads(record.error)["codes"] == ["HTTP_503", "ConnectError"]
