import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import DATASHEET_SCOPE_SELECTOR, settings
from app.schemas.asset import AssetSyncRequest, AssetSyncResponse
from app.services.datasheet_schema import REQUIRED_SHEET_HEADERS
from app.services.sync_service import PartialMutationError, SyncPlan, SyncService


def make_plan(qrcode="PC-001", *, row_number=2, action="UPDATE", write_cost=1):
    request = AssetSyncRequest(qrcode=qrcode, asset_type="Computer")
    return SyncPlan(
        row_number=row_number,
        request=request,
        action=action,
        expected_glpi_id=8 if action == "UPDATE" else None,
        asset_payload={"otherserial": qrcode},
        infocom_action=None,
        expected_infocom_id=None,
        infocom_payload=None,
        write_cost=write_cost,
    )


def prepare_service(*, dry_run):
    glpi = MagicMock()
    glpi.kill_session = AsyncMock()
    audit = MagicMock()
    audit.log_sync = AsyncMock()
    return SyncService(glpi, audit, dry_run=dry_run)


@pytest.mark.asyncio
async def test_computer_only_scope_excludes_monitor_before_glpi_preflight(
    monkeypatch, tmp_path
):
    rows = [
        {
            "QRCODE UNIT": "PC-SCOPE",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
        },
        {
            "QRCODE UNIT": "MON-SCOPE",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Monitor",
            "TAHUN PEROLEHAN": "INVALID-MONITOR-FINANCE",
            "NO. ASSET AKUNTANSI (DAT)": "DUPLICATE-MONITOR-DAT",
        },
        {
            "QRCODE UNIT": " mon-scope ",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Monitor",
            "NILAI RUPIAH": "INVALID-MONITOR-VALUE",
            "PENYUSUTAN": "INVALID-MONITOR-AMORTIZATION",
            "NO. ASSET AKUNTANSI (DAT)": "duplicate-monitor-dat",
        },
    ]

    class FakeSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return list(REQUIRED_SHEET_HEADERS), rows

    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(settings, "SYNC_FINANCE_ENABLED", True)
    monkeypatch.setattr(settings, "SYNC_MANIFEST_DIR", str(tmp_path / "manifests"))
    service = prepare_service(dry_run=True)
    service.preflight_sync = AsyncMock(
        return_value=SyncPlan(
            row_number=2,
            request=AssetSyncRequest(
                qrcode="PC-SCOPE",
                asset_type="Computer",
            ),
            action="UPDATE",
            expected_glpi_id=8,
            asset_payload={"name": "Laptop"},
            infocom_action=None,
            expected_infocom_id=None,
            infocom_payload=None,
            write_cost=1,
        )
    )

    summary = await service.run_batch_sync()

    assert summary["asset_types"] == ["Computer"]
    assert summary["eligible"] == 1
    assert summary["scope_skipped"] == 2
    assert summary["duplicate_groups"] == 0
    assert summary["duplicates_skipped"] == 0
    assert summary["duplicate_dat_groups"] == 0
    assert summary["duplicate_dat_rows"] == 0
    assert summary["preflight_errors"] == 0
    service.preflight_sync.assert_awaited_once()
    request = service.preflight_sync.await_args.args[0]
    assert request.qrcode == "PC-SCOPE"
    assert request.asset_type == "Computer"
    manifest = json.loads(Path(summary["manifest_path"]).read_text(encoding="utf-8"))
    material = manifest["material"]
    assert material["policy"]["asset_types"] == ["Computer"]
    assert material["policy"]["datasheet_scope_selector"] == DATASHEET_SCOPE_SELECTOR
    assert material["items"]
    assert {item["asset_type"] for item in material["items"]} == {"Computer"}
    assert {item["qrcode"] for item in material["items"]} == {"PC-SCOPE"}


@pytest.mark.asyncio
async def test_batch_uses_datasheet_only_and_skips_duplicate_qr(monkeypatch, tmp_path):
    rows = [
        {
            "QRCODE UNIT": "PC-001",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
            "MERK": "Dell",
            "TYPE": "OptiPlex",
        },
        {
            "QRCODE UNIT": " pc-001 ",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
        },
        {
            "QRCODE UNIT": "PC-002",
            "KATEGORI ASSET": "ELEKTRONIK",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
            "MERK": "Lenovo",
        },
        {
            "QRCODE UNIT": "CHAIR-001",
            "KATEGORI ASSET": "furniture",
            "SUB KATEGORI 1": "Kursi",
        },
    ]

    class FakeSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return list(REQUIRED_SHEET_HEADERS), rows

    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(settings, "SYNC_MANIFEST_DIR", str(tmp_path / "manifests"))

    service = prepare_service(dry_run=True)
    service.preflight_sync = AsyncMock(return_value=make_plan("PC-002", row_number=4))

    summary = await service.run_batch_sync()

    assert summary["fetched"] == 4
    assert summary["eligible"] == 3
    assert summary["unique_candidates"] == 1
    assert summary["processed"] == 1
    assert summary["would_update"] == 1
    assert summary["duplicates_skipped"] == 2
    assert summary["duplicate_groups"] == 1
    assert summary["ineligible_skipped"] == 1
    assert summary["selected_plans"] == 0
    assert summary["approval_status"] == "dry_run_blocked"
    assert summary["readiness_status"] == "source_duplicates"
    assert summary["dry_run_blocked_plans"] == 1
    assert service.audit.log_sync.await_args.kwargs["status"] == "BLOCKED"
    assert summary["manifest_sha256"]
    requests = [call.args[0] for call in service.preflight_sync.await_args_list]
    assert requests[0].qrcode == "PC-002"
    assert requests[0].asset_type == "Computer"
    assert "mac" not in requests[0].model_dump()


@pytest.mark.asyncio
async def test_batch_reports_sheet_read_failure_and_does_not_process(monkeypatch):
    class FailingSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            raise RuntimeError("unavailable")

    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FailingSheetsClient)
    service = prepare_service(dry_run=True)
    service.preflight_sync = AsyncMock()

    summary = await service.run_batch_sync()

    assert summary["errors"] == 1
    assert summary["processed"] == 0
    assert summary["approval_status"] == "source_schema_error"
    service.preflight_sync.assert_not_awaited()


@pytest.mark.asyncio
async def test_late_preflight_error_blocks_all_writes(monkeypatch, tmp_path):
    rows = [
        {
            "QRCODE UNIT": "PC-1",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
        },
        {
            "QRCODE UNIT": "PC-2",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
        },
    ]

    class FakeSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return list(REQUIRED_SHEET_HEADERS), rows

    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(settings, "SYNC_MANIFEST_DIR", str(tmp_path / "manifests"))
    monkeypatch.setattr(settings, "SYNC_MAX_GLPI_MUTATIONS_PER_RUN", 2)
    monkeypatch.setattr(settings, "SYNC_APPROVED_MANIFEST_SHA256", "a" * 64)

    service = prepare_service(dry_run=False)
    service.preflight_sync = AsyncMock(
        side_effect=[make_plan("PC-1", row_number=2), RuntimeError("late preflight failure")]
    )
    service._apply_plan = AsyncMock()

    summary = await service.run_batch_sync()

    assert summary["preflight_errors"] == 1
    assert summary["selected_plans"] == 0
    assert summary["approval_status"] == "preflight_errors"
    service._apply_plan.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_approval_blocks_before_write(monkeypatch, tmp_path):
    rows = [
        {
            "QRCODE UNIT": "PC-1",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
        }
    ]

    class FakeSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return list(REQUIRED_SHEET_HEADERS), rows

    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(settings, "SYNC_MANIFEST_DIR", str(tmp_path / "manifests"))
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "SYNC_MAX_GLPI_MUTATIONS_PER_RUN", 1)
    monkeypatch.setattr(settings, "SYNC_APPROVED_MANIFEST_SHA256", "")

    service = prepare_service(dry_run=False)
    service.preflight_sync = AsyncMock(return_value=make_plan("PC-1"))
    service._apply_plan = AsyncMock()

    summary = await service.run_batch_sync()

    assert summary["selected_mutations"] == 1
    assert summary["approval_status"] == "approval_missing"
    service._apply_plan.assert_not_awaited()


@pytest.mark.asyncio
async def test_manifest_approval_is_exact_and_one_shot(monkeypatch, tmp_path):
    rows = [
        {
            "QRCODE UNIT": "PC-1",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
        }
    ]

    class FakeSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return list(REQUIRED_SHEET_HEADERS), rows

    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(settings, "SYNC_MANIFEST_DIR", str(tmp_path / "manifests"))
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "SYNC_MAX_GLPI_MUTATIONS_PER_RUN", 1)

    service = prepare_service(dry_run=True)
    service.preflight_sync = AsyncMock(side_effect=lambda request, row_number: make_plan(request.qrcode, row_number=row_number))
    dry_run_summary = await service.run_batch_sync()

    assert dry_run_summary["approval_status"] == "dry_run_ready"
    assert dry_run_summary["readiness_status"] == "ready_for_approval"
    assert dry_run_summary["dry_run_blocked_plans"] == 0

    monkeypatch.setattr(settings, "SYNC_APPROVED_MANIFEST_SHA256", dry_run_summary["manifest_sha256"])
    service.dry_run = False
    service._apply_plan = AsyncMock(return_value=AssetSyncResponse(status="updated", glpi_id=8))

    approved_summary = await service.run_batch_sync()
    consumed_summary = await service.run_batch_sync()

    assert approved_summary["approval_status"] == "completed"
    assert consumed_summary["approval_status"] == "approval_already_consumed"
    service._apply_plan.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_audits_created_asset_id_after_partial_finance_failure(
    monkeypatch, tmp_path
):
    rows = [
        {
            "QRCODE UNIT": "PC-PARTIAL",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
        }
    ]

    class FakeSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return list(REQUIRED_SHEET_HEADERS), rows

    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(settings, "SYNC_MANIFEST_DIR", str(tmp_path / "manifests"))
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "SYNC_ALLOW_CREATE", True)
    monkeypatch.setattr(settings, "SYNC_MAX_GLPI_MUTATIONS_PER_RUN", 1)

    service = prepare_service(dry_run=True)
    service.preflight_sync = AsyncMock(
        side_effect=lambda request, row_number: make_plan(
            request.qrcode,
            row_number=row_number,
            action="CREATE",
        )
    )
    dry_run_summary = await service.run_batch_sync()

    monkeypatch.setattr(
        settings,
        "SYNC_APPROVED_MANIFEST_SHA256",
        dry_run_summary["manifest_sha256"],
    )
    service.dry_run = False
    service._apply_plan = AsyncMock(
        side_effect=PartialMutationError(
            glpi_id=123,
            stage="infocom_mutation",
            cause_type="GLPIClientError",
        )
    )

    summary = await service.run_batch_sync()

    assert summary["approval_status"] == "partial_write_failed"
    assert summary["partial_mutations"] == 1
    assert summary["processed"] == 0
    assert service.audit.log_sync.await_args.kwargs["glpi_id"] == 123


@pytest.mark.asyncio
async def test_batch_write_is_blocked_on_unsafe_glpi_transport(monkeypatch, tmp_path):
    rows = [
        {
            "QRCODE UNIT": "PC-1",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
        }
    ]

    class FakeSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return list(REQUIRED_SHEET_HEADERS), rows

    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(settings, "SYNC_MANIFEST_DIR", str(tmp_path / "manifests"))
    monkeypatch.setattr(settings, "GLPI_URL", "http://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "SYNC_MAX_GLPI_MUTATIONS_PER_RUN", 1)
    monkeypatch.setattr(settings, "SYNC_APPROVED_MANIFEST_SHA256", "a" * 64)
    service = prepare_service(dry_run=False)
    service.preflight_sync = AsyncMock(return_value=make_plan("PC-1"))
    service._apply_plan = AsyncMock()

    summary = await service.run_batch_sync()

    assert summary["write_transport_safe"] is False
    assert summary["selected_plans"] == 0
    assert summary["approval_status"] == "unsafe_write_transport"
    service._apply_plan.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_dat_in_unique_qr_rows_blocks_entire_batch(monkeypatch, tmp_path):
    rows = [
        {
            "QRCODE UNIT": "PC-1",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
            "NO. ASSET AKUNTANSI (DAT)": " DAT-01 ",
        },
        {
            "QRCODE UNIT": "PC-2",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
            "NO. ASSET AKUNTANSI (DAT)": "dat-01",
        },
    ]

    class FakeSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return list(REQUIRED_SHEET_HEADERS), rows

    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(settings, "SYNC_MANIFEST_DIR", str(tmp_path / "manifests"))
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "SYNC_FINANCE_ENABLED", True)
    monkeypatch.setattr(settings, "SYNC_MAX_GLPI_MUTATIONS_PER_RUN", 2)
    service = prepare_service(dry_run=False)
    service.preflight_sync = AsyncMock(
        side_effect=lambda request, row_number: make_plan(request.qrcode, row_number=row_number)
    )
    service._apply_plan = AsyncMock()

    summary = await service.run_batch_sync()

    assert summary["duplicate_dat_groups"] == 1
    assert summary["duplicate_dat_rows"] == 2
    assert summary["approval_status"] == "source_dat_duplicates"
    service._apply_plan.assert_not_awaited()


@pytest.mark.asyncio
async def test_total_noop_is_never_selected_or_applied(monkeypatch, tmp_path):
    rows = [
        {
            "QRCODE UNIT": "PC-NOOP",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
        }
    ]

    class FakeSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return list(REQUIRED_SHEET_HEADERS), rows

    noop_plan = make_plan("PC-NOOP", action="NOOP", write_cost=0)
    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(settings, "SYNC_MANIFEST_DIR", str(tmp_path / "manifests"))
    monkeypatch.setattr(settings, "GLPI_URL", "https://glpi.example.test/apirest.php")
    monkeypatch.setattr(settings, "GLPI_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "SYNC_MAX_GLPI_MUTATIONS_PER_RUN", 10)
    service = prepare_service(dry_run=False)
    service.preflight_sync = AsyncMock(return_value=noop_plan)
    service._apply_plan = AsyncMock()

    summary = await service.run_batch_sync()

    assert summary["planned_noop"] == 1
    assert summary["planned_mutations"] == 0
    assert summary["selected_plans"] == 0
    assert noop_plan.selection_reason == "no_changes"
    assert summary["approval_status"] == "no_selected_mutations"
    service._apply_plan.assert_not_awaited()


@pytest.mark.asyncio
async def test_finance_disabled_batch_omits_invalid_finance_and_skips_all_infocom_reads(
    monkeypatch,
    tmp_path,
):
    rows = [
        {
            "QRCODE UNIT": "PC-ASSET-1",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
            "NO. ASSET AKUNTANSI (DAT)": "DUPLICATE-DAT",
            "TAHUN PEROLEHAN": "INVALID-DATE",
            "NILAI RUPIAH": "INVALID-VALUE",
            "PENYUSUTAN": "INVALID-AMORTIZATION",
        },
        {
            "QRCODE UNIT": "PC-ASSET-2",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
            "NO. ASSET AKUNTANSI (DAT)": "duplicate-dat",
            "TAHUN PEROLEHAN": "ANOTHER-INVALID-DATE",
            "PENYUSUTAN": "HASH-VALUE",
        },
    ]

    class FakeSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return list(REQUIRED_SHEET_HEADERS), rows

    glpi = MagicMock()
    glpi.resolve_asset_identity = AsyncMock(return_value=None)
    glpi.resolve_infocom = AsyncMock()
    glpi.resolve_infocom_by_dat = AsyncMock()
    glpi.kill_session = AsyncMock()
    audit = MagicMock()
    audit.log_sync = AsyncMock()

    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(settings, "SYNC_FINANCE_ENABLED", False)
    monkeypatch.setattr(settings, "SYNC_MANIFEST_DIR", str(tmp_path / "manifests"))
    service = SyncService(glpi, audit, dry_run=True)

    summary = await service.run_batch_sync()

    assert summary["finance_enabled"] is False
    assert summary["eligible"] == 2
    assert summary["preflight_errors"] == 0
    assert summary["duplicate_dat_groups"] == 0
    assert summary["planned_create"] == 2
    requests = [call.args[0] for call in glpi.resolve_asset_identity.await_args_list]
    assert [request for request in requests] == ["PC-ASSET-1", "PC-ASSET-2"]
    glpi.resolve_infocom.assert_not_awaited()
    glpi.resolve_infocom_by_dat.assert_not_awaited()


@pytest.mark.asyncio
async def test_finance_disabled_manifest_hash_still_covers_raw_a_to_z_finance_cells(
    monkeypatch,
    tmp_path,
):
    class FakeSheetsClient:
        finance_value = "RAW-FINANCE-A"

        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return list(REQUIRED_SHEET_HEADERS), [
                {
                    "QRCODE UNIT": "PC-HASH",
                    "KATEGORI ASSET": "elektronik",
                    "SUB KATEGORI 1": "Komputer",
                    "SUB KATEGORI 2": "Laptop",
                    "NILAI RUPIAH": self.finance_value,
                }
            ]

    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(settings, "SYNC_FINANCE_ENABLED", False)
    monkeypatch.setattr(settings, "SYNC_MANIFEST_DIR", str(tmp_path / "manifests"))

    first_service = prepare_service(dry_run=True)
    first_service.preflight_sync = AsyncMock(return_value=make_plan("PC-HASH"))
    first = await first_service.run_batch_sync()

    FakeSheetsClient.finance_value = "RAW-FINANCE-B"
    second_service = prepare_service(dry_run=True)
    second_service.preflight_sync = AsyncMock(return_value=make_plan("PC-HASH"))
    second = await second_service.run_batch_sync()

    assert first["manifest_sha256"] != second["manifest_sha256"]
    first_manifest = json.loads(Path(first["manifest_path"]).read_text(encoding="utf-8"))
    assert first_manifest["material"]["policy"]["finance_enabled"] is False
    assert first_manifest["material"]["policy"]["blank_field_policy"] == "preserve_glpi"


@pytest.mark.asyncio
async def test_manifest_digest_is_bound_to_canonical_glpi_target_and_hashed_sheet_source(
    monkeypatch,
    tmp_path,
):
    rows = [
        {
            "QRCODE UNIT": "PC-TARGET",
            "KATEGORI ASSET": "elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
        }
    ]

    class FakeSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return list(REQUIRED_SHEET_HEADERS), rows

    async def run_manifest(*, glpi_url, spreadsheet_id):
        monkeypatch.setattr(settings, "GLPI_URL", glpi_url)
        monkeypatch.setattr(settings, "SPREADSHEET_ID", spreadsheet_id)
        service = prepare_service(dry_run=True)
        service.preflight_sync = AsyncMock(return_value=make_plan("PC-TARGET"))
        return await service.run_batch_sync()

    monkeypatch.setattr("app.services.sheets_client.SheetsClient", FakeSheetsClient)
    monkeypatch.setattr(settings, "SYNC_FINANCE_ENABLED", False)
    monkeypatch.setattr(settings, "SYNC_MANIFEST_DIR", str(tmp_path / "manifests"))

    first = await run_manifest(
        glpi_url="HTTPS://GLPI.Example.Test:443/apirest.php/",
        spreadsheet_id="private-sheet-source-a",
    )
    canonical_equivalent = await run_manifest(
        glpi_url="https://glpi.example.test/apirest.php",
        spreadsheet_id="private-sheet-source-a",
    )
    changed_target = await run_manifest(
        glpi_url="https://prod.example.test/apirest.php",
        spreadsheet_id="private-sheet-source-a",
    )
    changed_source = await run_manifest(
        glpi_url="https://glpi.example.test/apirest.php",
        spreadsheet_id="private-sheet-source-b",
    )

    assert first["manifest_sha256"] == canonical_equivalent["manifest_sha256"]
    assert changed_target["manifest_sha256"] != first["manifest_sha256"]
    assert changed_source["manifest_sha256"] != first["manifest_sha256"]

    material = json.loads(Path(first["manifest_path"]).read_text(encoding="utf-8"))["material"]
    assert material["target_identity"]["glpi_url"] == (
        "https://glpi.example.test/apirest.php"
    )
    assert len(material["target_identity"]["spreadsheet_id_sha256"]) == 64
    assert "private-sheet-source-a" not in json.dumps(material)
