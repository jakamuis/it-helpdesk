from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import (
    COMPUTER_SYNC_ASSET_TYPES,
    DATASHEET_SCOPE_SELECTOR,
    Settings,
)
from app.schemas.asset import AssetSyncRequest


ASSET_SYNC_ROOT = Path(__file__).resolve().parents[1]


def test_safe_config_defaults_without_env_file():
    config = Settings(_env_file=None)

    assert config.GLPI_ENTITY == 0
    assert isinstance(config.GLPI_ENTITY, int)
    assert config.SHEET_NAME == "DATABASE INVENTARIS"
    assert config.SYNC_ASSET_TYPES == COMPUTER_SYNC_ASSET_TYPES == ("Computer",)
    assert DATASHEET_SCOPE_SELECTOR == "electronics_cpu_laptop_v1"
    assert config.SYNC_ENABLED is False
    assert config.SYNC_DRY_RUN is True
    assert config.SYNC_FINANCE_ENABLED is False
    assert config.SYNC_ALLOW_CREATE is False
    assert config.SYNC_ALLOW_INFOCOM_CREATE is False
    assert config.SYNC_ALLOW_INFOCOM_UPDATE is False
    assert config.SYNC_MAX_GLPI_MUTATIONS_PER_RUN == 0
    assert config.SYNC_APPROVED_MANIFEST_SHA256 == ""
    assert config.SYNC_LOCK_DIR == "./data/locks"
    assert config.GLPI_VERIFY_TLS is True
    assert config.ASSET_SYNC_IMAGE_TAG == "1.1.0-local"
    assert config.ASSET_SYNC_PLATFORM == "linux/amd64"
    assert config.ASSET_SYNC_BUILD_COMMIT == "unknown"


def test_deployment_metadata_is_accepted_but_strictly_validated():
    config = Settings(
        _env_file=None,
        ASSET_SYNC_IMAGE_TAG="1.1.0-deadbeef",
        ASSET_SYNC_PLATFORM="linux/amd64",
        ASSET_SYNC_BUILD_COMMIT="deadbeef-dirty",
    )
    assert config.ASSET_SYNC_IMAGE_TAG == "1.1.0-deadbeef"
    assert config.ASSET_SYNC_BUILD_COMMIT == "deadbeef-dirty"

    with pytest.raises(ValidationError):
        Settings(_env_file=None, ASSET_SYNC_IMAGE_TAG="latest:unsafe")

    with pytest.raises(ValidationError):
        Settings(_env_file=None, ASSET_SYNC_PLATFORM="linux/arm64")


def test_env_example_contains_only_supported_settings():
    config = Settings(_env_file=ASSET_SYNC_ROOT / ".env.example")
    assert config.ASSET_SYNC_IMAGE_TAG == "1.1.0-local"
    assert config.ASSET_SYNC_PLATFORM == "linux/amd64"
    assert config.ASSET_SYNC_BUILD_COMMIT == "unknown"
    assert config.SYNC_ASSET_TYPES == ("Computer",)


@pytest.mark.parametrize(
    "invalid_scope",
    [
        (),
        ("Monitor",),
        ("Computer", "Monitor"),
        ("Computer", "Computer"),
    ],
    ids=["empty", "monitor", "mixed", "duplicate-computer"],
)
def test_asset_scope_is_fixed_to_exactly_one_computer(invalid_scope):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SYNC_ASSET_TYPES=invalid_scope)

    config = Settings(_env_file=None, SYNC_ASSET_TYPES=("Computer",))
    assert config.SYNC_ASSET_TYPES == ("Computer",)


def test_entity_id_cannot_be_negative():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, GLPI_ENTITY=-1)


def test_manifest_gate_config_rejects_unsafe_values():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, SYNC_MAX_GLPI_MUTATIONS_PER_RUN=-1)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, SYNC_APPROVED_MANIFEST_SHA256="not-a-sha256")

    config = Settings(_env_file=None, SYNC_APPROVED_MANIFEST_SHA256="A" * 64)
    assert config.SYNC_APPROVED_MANIFEST_SHA256 == "A" * 64


def test_request_trims_qr_and_rejects_blank():
    request = AssetSyncRequest(qrcode=" QR-1 ", asset_type="Computer")
    assert request.qrcode == "QR-1"

    with pytest.raises(ValidationError):
        AssetSyncRequest(qrcode="   ", asset_type="Computer")


@pytest.mark.parametrize("field", ["cpu", "ram", "storage", "os", "mac", "monitor"])
def test_excel_only_spec_fields_are_rejected(field):
    with pytest.raises(ValidationError):
        AssetSyncRequest(qrcode="QR-1", asset_type="Computer", **{field: "value"})
