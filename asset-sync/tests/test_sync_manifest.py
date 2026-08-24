import json
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from app.services.sync_manifest import (
    ManifestAlreadyClaimedError,
    ManifestValidationError,
    build_manifest,
    canonical_material_bytes,
    claim_manifest,
    compute_manifest_hash,
    normalize_manifest_hash,
    persist_manifest,
    validate_manifest,
)


def test_material_hash_is_deterministic_and_strict_json():
    first = {"items": [{"qrcode": "QR-Ü", "payload": {"b": 2, "a": 1}}], "entity": 0}
    second = {"entity": 0, "items": [{"payload": {"a": 1, "b": 2}, "qrcode": "QR-Ü"}]}

    assert canonical_material_bytes(first) == canonical_material_bytes(second)
    assert compute_manifest_hash(first) == compute_manifest_hash(second)
    assert compute_manifest_hash(first) != compute_manifest_hash({**first, "entity": 1})

    with pytest.raises(ManifestValidationError, match="strict JSON"):
        compute_manifest_hash({"cost": float("nan")})


def test_timestamp_and_approval_are_not_hash_material():
    material = {"source_hash": "abc", "selected": [{"qrcode": "QR-1", "action": "UPDATE"}]}
    first = build_manifest(
        material,
        generated_at="2026-08-20T10:00:00Z",
        approval={"operator": "first"},
    )
    second = build_manifest(
        material,
        generated_at="2026-08-24T10:00:00Z",
        approval={"operator": "second"},
    )

    assert first["generated_at"] != second["generated_at"]
    assert first["approval"] != second["approval"]
    assert first["manifest_sha256"] == second["manifest_sha256"]
    assert validate_manifest(first) == validate_manifest(second)


def test_build_manifest_detaches_mutable_material():
    material = {"selected": [{"qrcode": "QR-1"}]}
    manifest = build_manifest(material, generated_at="2026-08-24T00:00:00Z")
    material["selected"][0]["qrcode"] = "CHANGED"

    assert manifest["material"]["selected"][0]["qrcode"] == "QR-1"
    assert validate_manifest(manifest) == manifest["manifest_sha256"]


@pytest.mark.parametrize(
    "value",
    [
        "",
        "abc",
        "g" * 64,
        "0" * 63,
        "0" * 65,
    ],
)
def test_invalid_manifest_hash_is_rejected(value):
    with pytest.raises(ManifestValidationError):
        normalize_manifest_hash(value)


def test_manifest_hash_is_normalized():
    digest = "AB" * 32

    assert normalize_manifest_hash(f"  sha256:{digest}  ") == digest.lower()


def test_tampered_manifest_is_rejected():
    manifest = build_manifest({"selected": [{"qrcode": "QR-1"}]})
    manifest["material"]["selected"][0]["qrcode"] = "QR-2"

    with pytest.raises(ManifestValidationError, match="does not match"):
        validate_manifest(manifest)


def test_persist_manifest_is_atomic_private_and_readable(tmp_path):
    manifest = build_manifest(
        {"entity": 0, "selected": [{"qrcode": "QR-1", "write_cost": 1}]},
        generated_at=datetime(2026, 8, 24, tzinfo=timezone.utc),
    )

    destination = persist_manifest(manifest, tmp_path / "manifests")

    assert destination.name == f"{manifest['manifest_sha256']}.json"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert json.loads(destination.read_text(encoding="utf-8")) == manifest
    assert list(destination.parent.glob("*.tmp")) == []


def test_persist_rejects_tampering_without_creating_output(tmp_path):
    manifest = build_manifest({"selected": []})
    manifest["material"]["selected"].append({"qrcode": "UNAPPROVED"})
    directory = tmp_path / "manifests"

    with pytest.raises(ManifestValidationError):
        persist_manifest(manifest, directory)

    assert not directory.exists()


def test_claim_is_private_and_can_only_succeed_once(tmp_path):
    digest = compute_manifest_hash({"selected": [{"qrcode": "QR-1"}]})

    marker = claim_manifest(
        digest.upper(),
        tmp_path,
        claimed_at="2026-08-24T12:00:00Z",
    )

    assert stat.S_IMODE(marker.stat().st_mode) == 0o600
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "claimed_at": "2026-08-24T12:00:00Z",
        "manifest_sha256": digest,
    }
    with pytest.raises(ManifestAlreadyClaimedError):
        claim_manifest(digest, tmp_path)


def test_concurrent_claim_has_exactly_one_winner(tmp_path):
    digest = compute_manifest_hash({"selected": [{"qrcode": "QR-1"}]})

    def attempt_claim():
        try:
            return claim_manifest(digest, tmp_path)
        except ManifestAlreadyClaimedError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: attempt_claim(), range(16)))

    assert sum(outcome is not None for outcome in outcomes) == 1
    assert len(list((tmp_path / ".claims").glob("*.claimed"))) == 1
