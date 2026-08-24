"""Deterministic, fail-closed helpers for asset-sync approval manifests.

The hash covers only the manifest schema version and its ``material`` payload.
Operational metadata such as generation time and approval notes deliberately
stays outside that payload so it cannot make an otherwise identical plan hash
differently.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


MANIFEST_SCHEMA_VERSION = 1
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class ManifestValidationError(ValueError):
    """Raised when a manifest or approval hash is invalid."""


class ManifestAlreadyClaimedError(ManifestValidationError):
    """Raised when a one-shot manifest approval has already been claimed."""


def _utc_timestamp(value: datetime | str | None = None) -> str:
    if value is None:
        value = datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ManifestValidationError("Manifest timestamp must be a datetime or non-empty string")


def normalize_manifest_hash(value: str) -> str:
    """Return one lowercase SHA-256 digest, accepting an optional prefix."""

    if not isinstance(value, str):
        raise ManifestValidationError("Manifest hash must be a string")

    normalized = value.strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized.removeprefix("sha256:").strip()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise ManifestValidationError("Manifest hash must contain exactly 64 hexadecimal characters")
    return normalized


def canonical_material_bytes(
    material: Mapping[str, Any],
    *,
    schema_version: int = MANIFEST_SCHEMA_VERSION,
) -> bytes:
    """Serialize hash material deterministically using strict canonical JSON."""

    if not isinstance(material, Mapping):
        raise ManifestValidationError("Manifest material must be a mapping")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version < 1:
        raise ManifestValidationError("Manifest schema version must be a positive integer")

    envelope = {
        "material": material,
        "schema_version": schema_version,
    }
    try:
        serialized = json.dumps(
            envelope,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ManifestValidationError(f"Manifest material is not strict JSON: {exc}") from exc
    return serialized.encode("utf-8")


def compute_manifest_hash(
    material: Mapping[str, Any],
    *,
    schema_version: int = MANIFEST_SCHEMA_VERSION,
) -> str:
    """Compute the SHA-256 digest for deterministic manifest material."""

    return hashlib.sha256(
        canonical_material_bytes(material, schema_version=schema_version)
    ).hexdigest()


def build_manifest(
    material: Mapping[str, Any],
    *,
    generated_at: datetime | str | None = None,
    approval: Any | None = None,
    schema_version: int = MANIFEST_SCHEMA_VERSION,
) -> dict[str, Any]:
    """Build a serializable manifest with non-material metadata at top level."""

    # JSON round-tripping both validates and detaches the manifest from mutable
    # caller-owned mappings.
    canonical = canonical_material_bytes(material, schema_version=schema_version)
    normalized_material = json.loads(canonical.decode("utf-8"))["material"]
    manifest: dict[str, Any] = {
        "schema_version": schema_version,
        "generated_at": _utc_timestamp(generated_at),
        "manifest_sha256": compute_manifest_hash(
            normalized_material,
            schema_version=schema_version,
        ),
        "material": normalized_material,
    }
    if approval is not None:
        manifest["approval"] = approval
    return manifest


def validate_manifest(manifest: Mapping[str, Any]) -> str:
    """Validate a manifest and return its normalized, verified digest."""

    if not isinstance(manifest, Mapping):
        raise ManifestValidationError("Manifest must be a mapping")

    schema_version = manifest.get("schema_version")
    material = manifest.get("material")
    stored_hash = normalize_manifest_hash(manifest.get("manifest_sha256"))
    expected_hash = compute_manifest_hash(material, schema_version=schema_version)
    if not hmac.compare_digest(stored_hash, expected_hash):
        raise ManifestValidationError("Manifest hash does not match its material payload")
    return stored_hash


def _ensure_private_directory(directory: str | os.PathLike[str]) -> Path:
    path = Path(directory)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir():
        raise ManifestValidationError(f"Manifest path is not a directory: {path}")
    return path


def _fsync_directory(directory: Path) -> None:
    """Best-effort durability for a newly replaced or created directory entry."""

    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def persist_manifest(
    manifest: Mapping[str, Any],
    directory: str | os.PathLike[str],
) -> Path:
    """Atomically persist one verified manifest as a private JSON file."""

    manifest_hash = validate_manifest(manifest)
    target_directory = _ensure_private_directory(directory)
    destination = target_directory / f"{manifest_hash}.json"

    try:
        payload = (
            json.dumps(
                manifest,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ManifestValidationError(f"Manifest is not strict JSON: {exc}") from exc

    descriptor, temporary_name = tempfile.mkstemp(
        dir=target_directory,
        prefix=f".{manifest_hash}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
        os.chmod(destination, 0o600)
        _fsync_directory(target_directory)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass
        raise

    return destination


def claim_manifest(
    manifest_hash: str,
    directory: str | os.PathLike[str],
    *,
    claimed_at: datetime | str | None = None,
) -> Path:
    """Atomically consume one approval hash using an exclusive marker file.

    The marker is intentionally retained if writing its metadata fails after
    creation. Treating an uncertain claim as consumed is the fail-closed choice.
    """

    normalized_hash = normalize_manifest_hash(manifest_hash)
    claims_directory = _ensure_private_directory(Path(directory) / ".claims")
    claim_path = claims_directory / f"{normalized_hash}.claimed"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    try:
        descriptor = os.open(claim_path, flags, 0o600)
    except FileExistsError as exc:
        raise ManifestAlreadyClaimedError(
            f"Manifest approval has already been claimed: {normalized_hash}"
        ) from exc

    try:
        os.fchmod(descriptor, 0o600)
        marker = {
            "claimed_at": _utc_timestamp(claimed_at),
            "manifest_sha256": normalized_hash,
        }
        payload = (json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(claims_directory)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        # Do not remove the marker: an incomplete claim is still consumed.
        raise

    return claim_path
