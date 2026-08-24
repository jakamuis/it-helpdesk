from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.schemas.asset import AssetSyncRequest
from app.services.glpi_client import GLPIClientError
from app.services.qrcode_lock import (
    GlobalMutationLockBusyError,
    QRCodeLockBusyError,
    hold_global_mutation_lock,
    hold_qrcode_lock,
)
from app.services.sync_service import PartialMutationError, SyncPlan, SyncService


def make_dependencies():
    glpi = MagicMock()
    for method in (
        "resolve_asset_identity",
        "create_asset",
        "update_asset",
        "find_dropdown",
        "resolve_infocom",
        "resolve_infocom_by_dat",
        "search_infocom",
        "get_infocom",
        "create_infocom",
        "update_infocom",
        "kill_session",
    ):
        setattr(glpi, method, AsyncMock())
    glpi.find_dropdown.return_value = None
    glpi.resolve_infocom.return_value = None
    glpi.resolve_infocom_by_dat.return_value = None
    glpi.search_infocom.return_value = None

    audit = MagicMock()
    audit.log_sync = AsyncMock()
    return glpi, audit


@pytest.fixture(autouse=True)
def isolate_qrcode_locks(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SYNC_LOCK_DIR", str(tmp_path / "locks"))


@pytest.mark.asyncio
async def test_qr_miss_creates_without_name_fallback(monkeypatch):
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "SYNC_ALLOW_CREATE", True)
    glpi, audit = make_dependencies()
    glpi.resolve_asset_identity.return_value = None
    glpi.create_asset.return_value = 100
    service = SyncService(glpi, audit, dry_run=False)
    request = AssetSyncRequest(qrcode="QR-001", name="Generic Name", asset_type="Computer")

    plan = await service.preflight_sync(request)
    response = await service._apply_plan(plan)

    assert response.status == "created"
    assert response.glpi_id == 100
    assert glpi.resolve_asset_identity.await_count == 2
    glpi.resolve_asset_identity.assert_awaited_with(
        "QR-001",
        expected_itemtype="Computer",
        expected_entities_id=settings.GLPI_ENTITY,
    )
    glpi.create_asset.assert_awaited_once()
    payload = glpi.create_asset.await_args.args[0]
    assert payload["otherserial"] == "QR-001"
    assert payload["entities_id"] == settings.GLPI_ENTITY
    glpi.update_asset.assert_not_awaited()


@pytest.mark.asyncio
async def test_infocom_failure_after_asset_create_reports_partial_glpi_id(monkeypatch):
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "SYNC_FINANCE_ENABLED", True)
    monkeypatch.setattr(settings, "SYNC_ALLOW_CREATE", True)
    monkeypatch.setattr(settings, "SYNC_ALLOW_INFOCOM_CREATE", True)
    glpi, audit = make_dependencies()
    glpi.resolve_asset_identity.return_value = None
    glpi.create_asset.return_value = 123
    glpi.create_infocom.side_effect = GLPIClientError("upstream detail is not exposed")
    service = SyncService(glpi, audit, dry_run=False)
    plan = await service.preflight_sync(
        AssetSyncRequest(qrcode="QR-PARTIAL", asset_type="Computer", value="100")
    )

    with pytest.raises(PartialMutationError) as exc_info:
        await service._apply_plan(plan)

    assert exc_info.value.glpi_id == 123
    assert exc_info.value.stage == "infocom_mutation"
    assert exc_info.value.cause_type == "GLPIClientError"
    assert "upstream detail" not in str(exc_info.value)
    glpi.create_asset.assert_awaited_once()
    glpi.create_infocom.assert_awaited_once_with(
        {"itemtype": "Computer", "value": 100.0, "items_id": 123}
    )


@pytest.mark.asyncio
async def test_qr_hit_updates_without_moving_entity(monkeypatch):
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    glpi, audit = make_dependencies()
    record = {
        "id": 200,
        "otherserial": "QR-002",
        "entities_id": settings.GLPI_ENTITY,
        "name": "Old name",
    }
    glpi.resolve_asset_identity.return_value = {
        "id": 200,
        "qrcode": "QR-002",
        "record": record,
    }
    service = SyncService(glpi, audit, dry_run=False)
    request = AssetSyncRequest(qrcode="QR-002", name="Laptop", asset_type="Computer")

    plan = await service.preflight_sync(request)
    response = await service._apply_plan(plan)

    assert response.status == "updated"
    glpi.update_asset.assert_awaited_once()
    payload = glpi.update_asset.await_args.args[1]
    assert payload == {"name": "Laptop"}
    assert "entities_id" not in payload
    glpi.create_asset.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_qr_fails_closed_without_mutation():
    glpi, audit = make_dependencies()
    glpi.resolve_asset_identity.side_effect = GLPIClientError("Duplicate QRCODE UNIT")
    service = SyncService(glpi, audit, dry_run=True)
    request = AssetSyncRequest(qrcode="QR-DUP", asset_type="Computer")

    response = await service.process_sync(request, dry_run=True)

    assert response.status == "error"
    glpi.create_asset.assert_not_awaited()
    glpi.update_asset.assert_not_awaited()
    assert audit.log_sync.await_args.kwargs["status"] == "ERROR"


@pytest.mark.asyncio
async def test_direct_process_write_is_permanently_blocked_without_glpi_reads():
    glpi, audit = make_dependencies()
    service = SyncService(glpi, audit, dry_run=False)

    response = await service.process_sync(
        AssetSyncRequest(qrcode="QR-BLOCKED", asset_type="Computer")
    )

    assert response.status == "blocked"
    assert "Datasheet batch manifest" in response.message
    glpi.resolve_asset_identity.assert_not_awaited()
    glpi.create_asset.assert_not_awaited()
    glpi.update_asset.assert_not_awaited()
    assert audit.log_sync.await_args.kwargs["status"] == "BLOCKED"


@pytest.mark.asyncio
async def test_toctou_change_aborts_before_mutation(monkeypatch):
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    glpi, audit = make_dependencies()
    glpi.resolve_asset_identity.side_effect = [
        {
            "id": 10,
            "qrcode": "QR-STALE",
            "record": {"id": 10, "otherserial": "QR-STALE", "entities_id": 0},
        },
        {
            "id": 11,
            "qrcode": "QR-STALE",
            "record": {"id": 11, "otherserial": "QR-STALE", "entities_id": 0},
        },
    ]
    service = SyncService(glpi, audit, dry_run=False)

    plan = await service.preflight_sync(
        AssetSyncRequest(qrcode="QR-STALE", asset_type="Computer")
    )

    with pytest.raises(GLPIClientError, match="stale"):
        await service._apply_plan(plan)
    glpi.create_asset.assert_not_awaited()
    glpi.update_asset.assert_not_awaited()


@pytest.mark.asyncio
async def test_busy_qrcode_lock_blocks_before_recheck_or_mutation(monkeypatch):
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "SYNC_ALLOW_CREATE", True)
    glpi, audit = make_dependencies()
    glpi.resolve_asset_identity.return_value = None
    service = SyncService(glpi, audit, dry_run=False)
    plan = await service.preflight_sync(
        AssetSyncRequest(qrcode="qr-busy", asset_type="Computer")
    )

    async with hold_qrcode_lock("QR-BUSY", directory=settings.SYNC_LOCK_DIR):
        with pytest.raises(QRCodeLockBusyError, match="already syncing"):
            await service._apply_plan(plan)

    assert glpi.resolve_asset_identity.await_count == 1
    glpi.create_asset.assert_not_awaited()
    glpi.update_asset.assert_not_awaited()


@pytest.mark.asyncio
async def test_different_qr_cannot_enter_concurrent_global_mutation_section():
    glpi, audit = make_dependencies()
    service = SyncService(glpi, audit, dry_run=False)
    second_plan = SyncPlan(
        row_number=3,
        request=AssetSyncRequest(qrcode="QR-SECOND", asset_type="Computer"),
        action="UPDATE",
        expected_glpi_id=2,
        asset_payload={"name": "Second"},
        infocom_action=None,
        expected_infocom_id=None,
        infocom_payload=None,
        write_cost=1,
    )

    async with hold_global_mutation_lock(directory=settings.SYNC_LOCK_DIR):
        with pytest.raises(GlobalMutationLockBusyError, match="Another local worker"):
            await service._apply_plan(second_plan)

    glpi.resolve_asset_identity.assert_not_awaited()
    glpi.update_asset.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("existing", "expected_status", "expected_action"),
    [
        (None, "would_create", "DRY_RUN_CREATE"),
        ({"id": 22, "qrcode": "QR-DRY"}, "would_update", "DRY_RUN_UPDATE"),
    ],
)
async def test_dry_run_performs_reads_only(existing, expected_status, expected_action):
    glpi, audit = make_dependencies()
    if existing is not None:
        existing = {
            **existing,
            "record": {
                "id": existing["id"],
                "otherserial": "QR-DRY",
                "entities_id": settings.GLPI_ENTITY,
                "name": "Laptop",
                "manufacturers_id": 1,
            },
        }
    glpi.resolve_asset_identity.return_value = existing
    glpi.find_dropdown.return_value = 1
    service = SyncService(glpi, audit, dry_run=True)
    request = AssetSyncRequest(
        qrcode="QR-DRY",
        name="Laptop",
        asset_type="Computer",
        brand="Brand",
        value="1.000.000",
    )

    response = await service.process_sync(request)

    assert response.status == expected_status
    assert response.dry_run is True
    glpi.create_asset.assert_not_awaited()
    glpi.update_asset.assert_not_awaited()
    if existing is None:
        glpi.resolve_infocom.assert_not_awaited()
    else:
        glpi.resolve_infocom.assert_awaited_once_with("Computer", 22)
    glpi.create_infocom.assert_not_awaited()
    glpi.update_infocom.assert_not_awaited()
    assert audit.log_sync.await_args.kwargs["action"] == expected_action


@pytest.mark.asyncio
async def test_monitor_infocom_uses_glpi_11_fields_and_itemtype(monkeypatch):
    glpi, audit = make_dependencies()
    service = SyncService(glpi, audit, dry_run=False)
    request = AssetSyncRequest(
        qrcode="MON-001",
        asset_type="Monitor",
        value="Rp 1.500.000,00",
        amortization="5 Tahun",
    )

    infocom_payload = service._build_infocom_payload(request, 42)
    assert infocom_payload is not None
    assert infocom_payload["value"] == 1_500_000.0
    assert infocom_payload["sink_type"] == 2
    assert infocom_payload["sink_time"] == 5
    assert "amortization_type" not in infocom_payload
    assert "amortization_time" not in infocom_payload


@pytest.mark.asyncio
async def test_update_only_policy_does_not_create_missing_infocom(monkeypatch):
    monkeypatch.setattr(settings, "SYNC_FINANCE_ENABLED", True)
    monkeypatch.setattr(settings, "SYNC_ALLOW_INFOCOM_CREATE", False)
    plan = SyncPlan(
        row_number=2,
        request=AssetSyncRequest(qrcode="MON-INFO", asset_type="Monitor"),
        action="UPDATE",
        expected_glpi_id=44,
        asset_payload={"otherserial": "MON-INFO"},
        infocom_action="CREATE",
        expected_infocom_id=None,
        infocom_payload={"itemtype": "Monitor", "value": 1_500_000.0},
        write_cost=2,
    )

    SyncService._select_plans([plan], fatal_reason=None)

    assert plan.selected is False
    assert plan.selection_reason == "infocom_create_disabled"


@pytest.mark.asyncio
async def test_direct_dry_run_validates_finance_even_when_batch_finance_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "SYNC_FINANCE_ENABLED", False)
    glpi, audit = make_dependencies()
    glpi.resolve_asset_identity.return_value = None
    service = SyncService(glpi, audit, dry_run=True)
    request = AssetSyncRequest(
        qrcode="MON-002",
        asset_type="Monitor",
        value="not-a-number",
        amortization="unknown",
    )

    response = await service.process_sync(request, dry_run=True)

    assert response.status == "error"
    assert "NILAI RUPIAH" in response.message
    glpi.resolve_infocom.assert_not_awaited()
    glpi.create_infocom.assert_not_awaited()
    glpi.update_infocom.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_is_closed_even_when_audit_write_fails():
    glpi, audit = make_dependencies()
    glpi.resolve_asset_identity.return_value = None
    glpi.create_asset.return_value = 7
    audit.log_sync.side_effect = RuntimeError("audit unavailable")
    service = SyncService(glpi, audit, dry_run=False)

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.process_sync(AssetSyncRequest(qrcode="QR-007", asset_type="Computer"))

    glpi.kill_session.assert_awaited_once()


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (
            {
                "KATEGORI ASSET": "Elektronik",
                "SUB KATEGORI 1": "Komputer",
                "SUB KATEGORI 2": "CPU",
            },
            "Computer",
        ),
        (
            {
                "KATEGORI ASSET": "elektronik",
                "SUB KATEGORI 1": "Komputer",
                "SUB KATEGORI 2": "Laptop",
            },
            "Computer",
        ),
        (
            {
                "KATEGORI ASSET": "ELEKTRONIK",
                "SUB KATEGORI 1": "CPU",
            },
            "Computer",
        ),
        (
            {
                "KATEGORI ASSET": "Elektronik",
                "SUB KATEGORI 1": "Laptop",
            },
            "Computer",
        ),
        (
            {
                "KATEGORI ASSET": "Elektronik",
                "SUB KATEGORI 1": "Monitor",
            },
            "Monitor",
        ),
        (
            {
                "KATEGORI ASSET": "Elektronik",
                "SUB KATEGORI 1": "Printer",
            },
            None,
        ),
        (
            {
                "KATEGORI ASSET": "Furniture",
                "SUB KATEGORI 1": "CPU",
            },
            None,
        ),
        (
            {
                "KATEGORI ASSET": "Elektronik",
                "SUB KATEGORI 1": "CPU",
                "SUB KATEGORI 2": "Monitor",
            },
            "Monitor",
        ),
    ],
    ids=[
        "nested-cpu",
        "nested-laptop",
        "direct-cpu",
        "direct-laptop",
        "monitor",
        "unsupported-electronic",
        "non-electronic",
        "monitor-wins-conflict",
    ],
)
def test_classify_sheet_asset_type(row, expected):
    assert SyncService.classify_sheet_asset_type(row) == expected


def test_map_sheet_row_uses_only_datasheet_fields():
    request = SyncService.map_sheet_row(
        {
            "QRCODE UNIT": " QR-100 ",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
            "MERK": "Dell",
            "TYPE": "Latitude",
            "WILAYAH": "Barat",
            "CABANG": "Jakarta",
            "AREA": "HO",
            "TAHUN PEROLEHAN": "2025",
        }
    )

    assert request is not None
    assert request.qrcode == "QR-100"
    assert request.asset_type == "Computer"
    assert request.name == "Laptop Dell Latitude"
    assert request.location == "Barat > Jakarta > HO"
    assert request.buy_date == "2025-01-01"
    assert set(request.model_fields) == {
        "qrcode",
        "name",
        "dat_number",
        "asset_type",
        "brand",
        "model",
        "category",
        "location",
        "status",
        "user",
        "comment",
        "buy_date",
        "value",
        "amortization",
    }


def _eligible_sheet_row(**overrides):
    row = {
        "QRCODE UNIT": "QR-FINANCE",
        "KATEGORI ASSET": "Elektronik",
        "SUB KATEGORI 1": "Komputer",
        "SUB KATEGORI 2": "Laptop",
    }
    row.update(overrides)
    return row


def test_location_includes_lokasi_and_only_deduplicates_adjacent_levels():
    request = SyncService.map_sheet_row(
        _eligible_sheet_row(
            WILAYAH="Barat",
            CABANG="  barat  ",
            AREA="HO",
            LOKASI="Barat",
        )
    )

    assert request is not None
    assert request.location == "Barat > HO > Barat"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024", "2024-01-01"),
        ("2024-02-29", "2024-02-29"),
        ("6/8/2022", "2022-01-01"),
        ("30-Sep-2024", "2024-01-01"),
    ],
)
def test_acquisition_date_accepts_authoritative_sheet_formats(raw, expected):
    request = SyncService.map_sheet_row(
        _eligible_sheet_row(**{"TAHUN PEROLEHAN": raw})
    )

    assert request is not None
    assert request.buy_date == expected


@pytest.mark.parametrize(
    "raw",
    ["0000", "2023-02-29", "2024-13-01", "31/31/2024", "31-Foo-2024", "########"],
)
def test_invalid_nonempty_acquisition_date_fails_mapping(raw):
    with pytest.raises(GLPIClientError, match="TAHUN PEROLEHAN"):
        SyncService.map_sheet_row(_eligible_sheet_row(**{"TAHUN PEROLEHAN": raw}))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, 0.0),
        ("1500000", 1_500_000.0),
        ("Rp 1.500.000,00", 1_500_000.0),
        ("IDR 1,500,000.00", 1_500_000.0),
        ("12,50", 12.5),
    ],
)
def test_currency_parser_accepts_strict_nonnegative_finite_formats(raw, expected):
    assert SyncService._parse_currency(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [-1, float("nan"), float("inf"), "Rp nope", "-1", "1.23.456", True],
)
def test_invalid_nonempty_currency_fails_mapping(raw):
    with pytest.raises(GLPIClientError, match="NILAI RUPIAH"):
        SyncService.map_sheet_row(_eligible_sheet_row(**{"NILAI RUPIAH": raw}))


@pytest.mark.parametrize("raw", ["0", "-1", "1.5", "five years"])
def test_invalid_nonempty_depreciation_fails_mapping(raw):
    with pytest.raises(GLPIClientError, match="PENYUSUTAN"):
        SyncService.map_sheet_row(_eligible_sheet_row(PENYUSUTAN=raw))


def test_asset_only_mapping_omits_all_finance_without_validating_quarantined_values():
    request = SyncService.map_sheet_row(
        _eligible_sheet_row(
            **{
                "NO. ASSET AKUNTANSI (DAT)": "DAT-QUARANTINED",
                "TAHUN PEROLEHAN": "INVALID-DATE",
                "NILAI RUPIAH": "INVALID-VALUE",
                "PENYUSUTAN": "INVALID-AMORTIZATION",
            }
        ),
        include_finance=False,
    )

    assert request is not None
    assert request.dat_number is None
    assert request.buy_date is None
    assert request.value is None
    assert request.amortization is None


def test_canonical_glpi_target_identity_omits_credentials_and_url_extras():
    assert SyncService._canonical_glpi_url_identity(
        "HTTPS://private-user:private-pass@GLPI.Example.Test:443/apirest.php/"
    ) == "https://glpi.example.test/apirest.php"

    with pytest.raises(GLPIClientError, match="query string or fragment"):
        SyncService._canonical_glpi_url_identity(
            "https://glpi.example.test/apirest.php?private=value"
        )


def test_spreadsheet_identity_hash_is_deterministic_without_returning_raw_id():
    first = SyncService._spreadsheet_id_sha256(" private-sheet-id ")
    second = SyncService._spreadsheet_id_sha256("private-sheet-id")

    assert first == second
    assert len(first) == 64
    assert "private-sheet-id" not in first


@pytest.mark.asyncio
async def test_dropdown_cache_normalizes_repeated_names_and_caches_misses():
    glpi, audit = make_dependencies()
    glpi.find_dropdown.return_value = 7
    service = SyncService(glpi, audit)

    assert await service._dropdown_id("Manufacturer", "Dell") == 7
    assert await service._dropdown_id("Manufacturer", "  DELL  ") == 7
    glpi.find_dropdown.assert_awaited_once_with("Manufacturer", "Dell")

    glpi.find_dropdown.reset_mock()
    glpi.find_dropdown.return_value = None
    for name in ("Unknown Model", " unknown   model "):
        with pytest.raises(GLPIClientError, match="not found"):
            await service._dropdown_id("ComputerModel", name)
    glpi.find_dropdown.assert_awaited_once_with("ComputerModel", "Unknown Model")


@pytest.mark.asyncio
async def test_same_asset_id_with_changed_relevant_field_invalidates_plan(monkeypatch):
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    glpi, audit = make_dependencies()
    glpi.resolve_asset_identity.side_effect = [
        {
            "id": 12,
            "qrcode": "QR-STATE",
            "record": {
                "id": 12,
                "otherserial": "QR-STATE",
                "entities_id": 0,
                "name": "Before",
            },
        },
        {
            "id": 12,
            "qrcode": "QR-STATE",
            "record": {
                "id": 12,
                "otherserial": "QR-STATE",
                "entities_id": 0,
                "name": "Changed elsewhere",
            },
        },
    ]
    service = SyncService(glpi, audit, dry_run=False)
    plan = await service.preflight_sync(
        AssetSyncRequest(qrcode="QR-STATE", asset_type="Computer", name="Target")
    )

    with pytest.raises(GLPIClientError, match="fields changed"):
        await service._apply_plan(plan)

    assert plan.asset_state_sha256
    assert plan.to_manifest_item()["asset_state_sha256"] == plan.asset_state_sha256
    glpi.update_asset.assert_not_awaited()


@pytest.mark.asyncio
async def test_infocom_update_gate_blocks_before_asset_mutation(monkeypatch):
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "SYNC_FINANCE_ENABLED", True)
    monkeypatch.setattr(settings, "SYNC_ALLOW_INFOCOM_UPDATE", False)
    glpi, audit = make_dependencies()
    service = SyncService(glpi, audit, dry_run=False)
    plan = SyncPlan(
        row_number=2,
        request=AssetSyncRequest(qrcode="QR-INFO", asset_type="Computer"),
        action="UPDATE",
        expected_glpi_id=10,
        asset_payload={"otherserial": "QR-INFO"},
        infocom_action="UPDATE",
        expected_infocom_id=20,
        infocom_payload={"itemtype": "Computer", "items_id": 10, "value": 1.0},
        write_cost=2,
    )

    with pytest.raises(GLPIClientError, match="Infocom update is disabled"):
        await service._apply_plan(plan)

    glpi.resolve_asset_identity.assert_not_awaited()
    glpi.update_asset.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_plan_rejects_http_even_if_other_gates_are_open(monkeypatch):
    monkeypatch.setattr(settings, "GLPI_URL", "http://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    glpi, audit = make_dependencies()
    service = SyncService(glpi, audit, dry_run=False)
    plan = SyncPlan(
        row_number=2,
        request=AssetSyncRequest(qrcode="QR-TLS", asset_type="Computer"),
        action="UPDATE",
        expected_glpi_id=10,
        asset_payload={"otherserial": "QR-TLS"},
        infocom_action=None,
        expected_infocom_id=None,
        infocom_payload=None,
        write_cost=1,
    )

    with pytest.raises(GLPIClientError, match="HTTPS"):
        await service._apply_plan(plan)

    glpi.resolve_asset_identity.assert_not_awaited()
    glpi.update_asset.assert_not_awaited()


@pytest.mark.asyncio
async def test_preflight_blocks_dat_owned_by_a_different_asset():
    glpi, audit = make_dependencies()
    glpi.resolve_asset_identity.return_value = {
        "id": 10,
        "qrcode": "QR-DAT",
        "record": {"id": 10, "otherserial": "QR-DAT", "entities_id": 0},
    }
    glpi.resolve_infocom.return_value = None
    glpi.resolve_infocom_by_dat.return_value = {
        "id": 99,
        "itemtype": "Computer",
        "items_id": 11,
        "record": {"id": 99, "itemtype": "Computer", "items_id": 11},
    }
    service = SyncService(glpi, audit, dry_run=True)

    with pytest.raises(GLPIClientError, match="already owned"):
        await service.preflight_sync(
            AssetSyncRequest(
                qrcode="QR-DAT",
                asset_type="Computer",
                dat_number="DAT-01",
            )
        )

    glpi.create_asset.assert_not_awaited()
    glpi.update_asset.assert_not_awaited()


@pytest.mark.asyncio
async def test_dat_claimed_after_preflight_invalidates_create_plan(monkeypatch):
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "SYNC_FINANCE_ENABLED", True)
    monkeypatch.setattr(settings, "SYNC_ALLOW_CREATE", True)
    monkeypatch.setattr(settings, "SYNC_ALLOW_INFOCOM_CREATE", True)
    glpi, audit = make_dependencies()
    glpi.resolve_asset_identity.return_value = None
    glpi.resolve_infocom_by_dat.side_effect = [
        None,
        {
            "id": 88,
            "itemtype": "Computer",
            "items_id": 77,
            "record": {"id": 88, "itemtype": "Computer", "items_id": 77},
        },
    ]
    service = SyncService(glpi, audit, dry_run=False)
    plan = await service.preflight_sync(
        AssetSyncRequest(
            qrcode="QR-NEW-DAT",
            asset_type="Computer",
            dat_number="DAT-NEW",
        )
    )

    with pytest.raises(GLPIClientError, match="ownership changed"):
        await service._apply_plan(plan)

    glpi.create_asset.assert_not_awaited()
    glpi.create_infocom.assert_not_awaited()


@pytest.mark.asyncio
async def test_fully_unchanged_asset_is_noop_with_zero_cost_and_no_mutator(monkeypatch):
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    glpi, audit = make_dependencies()
    identity = {
        "id": 21,
        "qrcode": "QR-NOOP",
        "record": {
            "id": 21,
            "otherserial": "QR-NOOP",
            "entities_id": settings.GLPI_ENTITY,
            "name": "Laptop",
            "comment": "same",
        },
    }
    glpi.resolve_asset_identity.return_value = identity
    service = SyncService(glpi, audit, dry_run=False)
    plan = await service.preflight_sync(
        AssetSyncRequest(
            qrcode="QR-NOOP",
            asset_type="Computer",
            name="Laptop",
            comment="same",
        )
    )

    assert plan.action == "NOOP"
    assert plan.asset_payload == {}
    assert plan.write_cost == 0
    SyncService._select_plans([plan], fatal_reason=None)
    assert plan.selected is False
    assert plan.selection_reason == "no_changes"

    response = await service._apply_plan(plan)
    assert response.status == "unchanged"
    glpi.create_asset.assert_not_awaited()
    glpi.update_asset.assert_not_awaited()
    glpi.create_infocom.assert_not_awaited()
    glpi.update_infocom.assert_not_awaited()


@pytest.mark.asyncio
async def test_asset_noop_can_apply_only_changed_infocom_field(monkeypatch):
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "SYNC_FINANCE_ENABLED", True)
    monkeypatch.setattr(settings, "SYNC_ALLOW_INFOCOM_UPDATE", True)
    glpi, audit = make_dependencies()
    identity = {
        "id": 31,
        "qrcode": "QR-FIN-DIFF",
        "record": {
            "id": 31,
            "otherserial": "QR-FIN-DIFF",
            "entities_id": settings.GLPI_ENTITY,
            "name": "QR-FIN-DIFF",
        },
    }
    infocom_identity = {
        "id": 41,
        "record": {
            "id": 41,
            "itemtype": "Computer",
            "items_id": 31,
            "value": "100.00",
        },
    }
    glpi.resolve_asset_identity.return_value = identity
    glpi.resolve_infocom.return_value = infocom_identity
    service = SyncService(glpi, audit, dry_run=False)
    plan = await service.preflight_sync(
        AssetSyncRequest(
            qrcode="QR-FIN-DIFF",
            asset_type="Computer",
            value="150.00",
        )
    )

    assert plan.action == "NOOP"
    assert plan.infocom_action == "UPDATE"
    assert plan.infocom_payload == {"value": 150.0}
    assert plan.write_cost == 1

    response = await service._apply_plan(plan)

    assert response.status == "updated"
    glpi.update_asset.assert_not_awaited()
    glpi.update_infocom.assert_awaited_once_with(41, {"value": 150.0})


@pytest.mark.asyncio
async def test_unchanged_infocom_is_noop_and_costs_zero():
    glpi, audit = make_dependencies()
    glpi.resolve_asset_identity.return_value = {
        "id": 32,
        "qrcode": "QR-FIN-NOOP",
        "record": {
            "id": 32,
            "otherserial": "QR-FIN-NOOP",
            "entities_id": settings.GLPI_ENTITY,
            "name": "QR-FIN-NOOP",
        },
    }
    glpi.resolve_infocom.return_value = {
        "id": 42,
        "record": {
            "id": 42,
            "itemtype": "Computer",
            "items_id": "32",
            "buy_date": "2024-01-01",
            "value": "150.0000",
            "sink_type": "2",
            "sink_time": "5",
        },
    }
    service = SyncService(glpi, audit, dry_run=True)

    plan = await service.preflight_sync(
        AssetSyncRequest(
            qrcode="QR-FIN-NOOP",
            asset_type="Computer",
            buy_date="2024",
            value="150",
            amortization="5 Tahun",
        )
    )

    assert plan.action == "NOOP"
    assert plan.infocom_action == "NOOP"
    assert plan.infocom_payload == {}
    assert plan.write_cost == 0
