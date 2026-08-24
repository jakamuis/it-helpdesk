import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.datasheet_report import DatasheetReportGenerator, build_datasheet_report
from app.services.datasheet_schema import (
    REQUIRED_SHEET_HEADERS,
    DatasheetHeaderError,
    validate_headers,
)
from app.services.sheets_client import SheetsClient, SheetsClientError
from app.services.sync_service import SyncService


FULL_HEADERS = [
    "QRCODE ROOM",
    "WILAYAH",
    "CABANG",
    "AREA",
    "QRCODE UNIT",
    "JENIS ASSET",
    "KATEGORI ASSET",
    "SUB KATEGORI 1",
    "SUB KATEGORI 2",
    "MERK",
    "TYPE",
    "WARNA",
    "KAPASITAS",
    "NAMA USER",
    "SERTIFIKAT/IMB",
    "KETERANGAN",
    "SATUAN",
    "NO. ASSET AKUNTANSI (DAT)",
    "TAHUN PEROLEHAN",
    "NILAI RUPIAH",
    "PENYUSUTAN",
    "KONDISI",
    "IMAGE1",
    "IMAGE2",
    "IMAGE3",
    "LOKASI",
    "DIREGISTRASI OLEH",
    "TANDA TANGAN",
    "TGL REGISTRASI",
    "DIUPDATE OLEH",
    "LAST UPDATE",
]


def sample_rows():
    return [
        {
            "QRCODE UNIT": "PC-001",
            "JENIS ASSET": "Desktop",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
            "NO. ASSET AKUNTANSI (DAT)": "DAT-OLD",
            "NAMA USER": "Sensitive Person One",
            "KETERANGAN": "private comment one",
        },
        {
            "QRCODE UNIT": "PC-001",
            "JENIS ASSET": "Desktop",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
            "NO. ASSET AKUNTANSI (DAT)": "DAT-NEW",
            "NAMA USER": "Sensitive Person Two",
            "KETERANGAN": "private comment two",
        },
        {
            "QRCODE UNIT": "MON-001",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Monitor",
        },
        {
            "QRCODE UNIT": "PRINT-001",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Printer",
            "SUB KATEGORI 2": "Tinta",
        },
        {
            "QRCODE UNIT": "CHAIR-001",
            "KATEGORI ASSET": "Furniture",
            "SUB KATEGORI 1": "Kursi",
        },
        {
            "QRCODE UNIT": "",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Monitor",
        },
    ]


def test_header_validation_is_exact_and_checks_a_to_z_boundary():
    validation = validate_headers(FULL_HEADERS)
    assert validation.is_valid is True
    assert set(REQUIRED_SHEET_HEADERS).issubset(FULL_HEADERS)

    missing = validate_headers([header for header in FULL_HEADERS if header != "QRCODE UNIT"])
    assert missing.is_valid is False
    assert missing.missing_headers == ("QRCODE UNIT",)

    duplicate = validate_headers(FULL_HEADERS + [" qrcode unit "])
    assert duplicate.is_valid is False
    assert "QRCODE UNIT" in duplicate.duplicate_headers

    shifted = [header for header in FULL_HEADERS if header != "AREA"]
    shifted.remove("QRCODE UNIT")
    shifted.append("QRCODE UNIT")
    assert "QRCODE UNIT" in validate_headers(shifted).required_headers_outside_data_range


def test_report_counts_duplicates_and_omits_raw_conflict_values_and_pii():
    generated_at = datetime(2026, 8, 24, 18, 30, tzinfo=timezone.utc)
    summary, details, markdown = build_datasheet_report(
        FULL_HEADERS,
        sample_rows(),
        sheet_name="DATABASE INVENTARIS",
        generated_at=generated_at,
    )

    assert summary["counts"] == {
        "fetched_rows": 6,
        "missing_qr_rows": 1,
        "electronic_rows": 5,
        "electronic_missing_qr_rows": 0,
        "non_electronic_rows": 1,
        "eligible_rows": 2,
        "eligible_computers": 2,
        "unsupported_electronic_rows": 1,
        "unsupported_electronic_combinations": 1,
        "scope_excluded_rows": 2,
        "scope_excluded_monitors": 2,
        "duplicate_groups": 1,
        "duplicate_rows": 2,
        "unique_candidates": 0,
        "duplicate_dat_groups": 0,
        "duplicate_dat_rows": 0,
        "finance_valid_rows": 2,
        "finance_valid_unique_candidates": 0,
        "mapping_error_rows": 0,
        "asset_mapping_error_rows": 0,
        "finance_mapping_error_rows": 0,
        "mapping_error_categories": 0,
    }
    assert summary["unsupported_electronics"] == [
        {"sub_category_1": "printer", "sub_category_2": "tinta", "count": 1}
    ]
    assert details["duplicate_groups"] == [
        {
            "qrcode": "PC-001",
            "row_numbers": [2, 3],
            "conflict_fields": ["comment", "dat_number", "user"],
        }
    ]

    serialized_outputs = json.dumps({"summary": summary, "details": details}) + markdown
    for unsafe_value in (
        "DAT-OLD",
        "DAT-NEW",
        "Sensitive Person One",
        "Sensitive Person Two",
        "private comment one",
        "private comment two",
    ):
        assert unsafe_value not in serialized_outputs


def test_report_collects_safe_finance_mapping_errors_and_keeps_invariants():
    rows = [
        {
            "QRCODE UNIT": "PC-BAD-DATE",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
            "TAHUN PEROLEHAN": "PRIVATE INVALID DATE",
        },
        {
            "QRCODE UNIT": "PC-BAD-VALUE",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
            "NILAI RUPIAH": "PRIVATE INVALID VALUE",
        },
        {
            "QRCODE UNIT": "PC-BAD-AMORTIZATION",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
            "PENYUSUTAN": "PRIVATE INVALID AMORTIZATION",
        },
        {
            "QRCODE UNIT": "PC-VALID",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
        },
    ]

    summary, details, markdown = build_datasheet_report(
        FULL_HEADERS,
        rows,
        sheet_name="DATABASE INVENTARIS",
        generated_at=datetime(2026, 8, 24, 18, 30, tzinfo=timezone.utc),
    )

    assert summary["counts"]["electronic_rows"] == 4
    assert summary["counts"]["eligible_rows"] == 4
    assert summary["counts"]["unique_candidates"] == 4
    assert summary["counts"]["finance_valid_rows"] == 1
    assert summary["counts"]["finance_valid_unique_candidates"] == 1
    assert summary["counts"]["mapping_error_rows"] == 3
    assert summary["counts"]["asset_mapping_error_rows"] == 0
    assert summary["counts"]["finance_mapping_error_rows"] == 3
    assert summary["counts"]["mapping_error_categories"] == 3
    assert summary["mapping_errors_by_code"] == {
        "invalid_amortization": 1,
        "invalid_buy_date": 1,
        "invalid_value": 1,
    }
    assert summary["gates"]["counts_consistent"] is True
    assert summary["gates"]["asset_mapping_errors_free"] is True
    assert summary["gates"]["asset_write_blocked"] is False
    assert summary["gates"]["finance_mapping_errors_free"] is False
    assert summary["gates"]["finance_write_blocked_by_mapping_errors"] is True
    assert summary["gates"]["finance_write_blocked"] is True
    assert details["mapping_errors"] == [
        {"row_number": 2, "error_code": "invalid_buy_date", "scope": "finance"},
        {"row_number": 3, "error_code": "invalid_value", "scope": "finance"},
        {
            "row_number": 4,
            "error_code": "invalid_amortization",
            "scope": "finance",
        },
    ]
    assert "Finance mapping gate: `FAIL`; finance writes are blocked" in markdown

    serialized_outputs = json.dumps({"summary": summary, "details": details}) + markdown
    for unsafe_value in (
        "PRIVATE INVALID DATE",
        "PRIVATE INVALID VALUE",
        "PRIVATE INVALID AMORTIZATION",
        "must be",
    ):
        assert unsafe_value not in serialized_outputs


def test_monitor_rows_are_excluded_before_qr_duplicate_and_finance_gates():
    rows = [
        {
            "QRCODE UNIT": "MON-OUT-OF-SCOPE",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Monitor",
            "NO. ASSET AKUNTANSI (DAT)": "DUPLICATE-MONITOR-DAT",
            "TAHUN PEROLEHAN": "INVALID-MONITOR-DATE",
        },
        {
            "QRCODE UNIT": " mon-out-of-scope ",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Monitor",
            "NO. ASSET AKUNTANSI (DAT)": "duplicate-monitor-dat",
            "NILAI RUPIAH": "INVALID-MONITOR-VALUE",
        },
        {
            "QRCODE UNIT": "",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Monitor",
        },
    ]

    summary, details, markdown = build_datasheet_report(
        FULL_HEADERS,
        rows,
        sheet_name="DATABASE INVENTARIS",
        generated_at=datetime(2026, 8, 24, 18, 30, tzinfo=timezone.utc),
    )

    assert summary["counts"]["scope_excluded_rows"] == 3
    assert summary["counts"]["scope_excluded_monitors"] == 3
    assert summary["counts"]["electronic_missing_qr_rows"] == 0
    assert summary["counts"]["eligible_rows"] == 0
    assert summary["counts"]["duplicate_groups"] == 0
    assert summary["counts"]["duplicate_dat_groups"] == 0
    assert summary["counts"]["mapping_error_rows"] == 0
    assert summary["gates"]["asset_write_blocked"] is False
    assert summary["gates"]["finance_write_blocked"] is False
    assert details["duplicate_groups"] == []
    assert details["mapping_errors"] == []
    serialized_outputs = json.dumps({"summary": summary, "details": details}) + markdown
    assert "DUPLICATE-MONITOR-DAT" not in serialized_outputs
    assert "INVALID-MONITOR" not in serialized_outputs


def test_report_reduces_unexpected_mapper_exception_to_controlled_code(monkeypatch):
    original_mapper = SyncService.map_sheet_row

    def scoped_mapper(_row, *, include_finance):
        if include_finance:
            raise RuntimeError("PRIVATE USER VALUE AND INTERNAL MESSAGE")
        return original_mapper(_row, include_finance=False)

    monkeypatch.setattr(SyncService, "map_sheet_row", scoped_mapper)
    summary, details, markdown = build_datasheet_report(
        FULL_HEADERS,
        [
            {
                "QRCODE UNIT": "PC-ERROR",
                "KATEGORI ASSET": "Elektronik",
                "SUB KATEGORI 1": "Komputer",
                "SUB KATEGORI 2": "Laptop",
            }
        ],
        sheet_name="DATABASE INVENTARIS",
        generated_at=datetime(2026, 8, 24, 18, 30, tzinfo=timezone.utc),
    )

    assert summary["mapping_errors_by_code"] == {"mapping_error": 1}
    assert details["mapping_errors"] == [
        {"row_number": 2, "error_code": "mapping_error", "scope": "finance"}
    ]
    serialized_outputs = json.dumps({"summary": summary, "details": details}) + markdown
    assert "PRIVATE USER VALUE AND INTERNAL MESSAGE" not in serialized_outputs


def test_report_counts_normalized_duplicate_dat_only_after_duplicate_qr_exclusion():
    rows = [
        {
            "QRCODE UNIT": "QR-DUP",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
            "NO. ASSET AKUNTANSI (DAT)": "EXCLUDED SECRET DAT",
        },
        {
            "QRCODE UNIT": " qr-dup ",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "CPU",
            "NO. ASSET AKUNTANSI (DAT)": "EXCLUDED SECRET DAT",
        },
        {
            "QRCODE UNIT": "PC-UNIQUE-1",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
            "NO. ASSET AKUNTANSI (DAT)": " Sensitive   DAT  42 ",
        },
        {
            "QRCODE UNIT": "PC-UNIQUE-2",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
            "NO. ASSET AKUNTANSI (DAT)": "sensitive\tDAT 42",
        },
        {
            "QRCODE UNIT": "PC-BLANK-DAT",
            "KATEGORI ASSET": "Elektronik",
            "SUB KATEGORI 1": "Komputer",
            "SUB KATEGORI 2": "Laptop",
            "NO. ASSET AKUNTANSI (DAT)": "  ",
        },
    ]

    summary, details, markdown = build_datasheet_report(
        FULL_HEADERS,
        rows,
        sheet_name="DATABASE INVENTARIS",
        generated_at=datetime(2026, 8, 24, 18, 30, tzinfo=timezone.utc),
    )

    assert summary["counts"]["duplicate_groups"] == 1
    assert summary["counts"]["duplicate_rows"] == 2
    assert summary["counts"]["unique_candidates"] == 3
    assert summary["counts"]["duplicate_dat_groups"] == 1
    assert summary["counts"]["duplicate_dat_rows"] == 2
    assert summary["gates"]["duplicate_dat_free"] is False
    assert summary["gates"]["finance_write_blocked_by_duplicate_dat"] is True
    assert summary["gates"]["asset_write_blocked"] is True
    assert summary["gates"]["finance_write_blocked"] is True
    assert "Duplicate QR gate: `FAIL`; all asset and finance writes are blocked." in markdown
    assert "Duplicate DAT gate: `FAIL`; finance writes are blocked" in markdown

    serialized_outputs = json.dumps({"summary": summary, "details": details}) + markdown
    for unsafe_value in (
        "EXCLUDED SECRET DAT",
        "Sensitive   DAT  42",
        "sensitive\tDAT 42",
        "sensitive dat 42",
    ):
        assert unsafe_value not in serialized_outputs


def test_generator_reads_one_validated_snapshot_and_writes_only_three_private_files(
    tmp_path: Path,
):
    calls = []

    class FakeSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            calls.append("snapshot")
            return FULL_HEADERS, sample_rows()

    fixed_time = datetime(2026, 8, 24, 18, 30, tzinfo=timezone.utc)
    result = DatasheetReportGenerator(
        FakeSheetsClient(),
        now_factory=lambda: fixed_time,
    ).generate(
        "secret-spreadsheet-id",
        "DATABASE INVENTARIS",
        output_root=tmp_path,
    )

    assert calls == ["snapshot"]
    report_directory = result["report_directory"]
    assert {path.name for path in report_directory.iterdir()} == {
        "summary.md",
        "summary.json",
        "details.json",
    }
    assert report_directory.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in report_directory.iterdir())
    summary_json = json.loads(result["summary_json"].read_text(encoding="utf-8"))
    assert "secret-spreadsheet-id" not in json.dumps(summary_json)
    assert summary_json["source"]["asset_types"] == ["Computer"]
    assert summary_json["source"]["datasheet_scope_selector"] == (
        "electronics_cpu_laptop_v1"
    )
    assert summary_json["counts"]["eligible_computers"] == 2
    assert summary_json["counts"]["scope_excluded_monitors"] == 2


def test_generator_writes_private_report_when_a_row_has_mapping_error(tmp_path: Path):
    unsafe_value = "PRIVATE INVALID ACQUISITION DATE"

    class InvalidRowSheetsClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return FULL_HEADERS, [
                {
                    "QRCODE UNIT": "PC-BAD-DATE",
                    "KATEGORI ASSET": "Elektronik",
                    "SUB KATEGORI 1": "Komputer",
                    "SUB KATEGORI 2": "Laptop",
                    "TAHUN PEROLEHAN": unsafe_value,
                }
            ]

    result = DatasheetReportGenerator(
        InvalidRowSheetsClient(),
        now_factory=lambda: datetime(2026, 8, 24, 18, 30, tzinfo=timezone.utc),
    ).generate(
        "secret-spreadsheet-id",
        "DATABASE INVENTARIS",
        output_root=tmp_path,
    )

    report_directory = result["report_directory"]
    assert {path.name for path in report_directory.iterdir()} == {
        "summary.md",
        "summary.json",
        "details.json",
    }
    assert report_directory.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in report_directory.iterdir())
    assert result["summary"]["gates"]["asset_write_blocked"] is False
    assert result["summary"]["gates"]["finance_write_blocked_by_mapping_errors"] is True
    details = json.loads(result["details_json"].read_text(encoding="utf-8"))
    assert details["mapping_errors"] == [
        {"row_number": 2, "error_code": "invalid_buy_date", "scope": "finance"}
    ]
    serialized_files = "".join(
        path.read_text(encoding="utf-8") for path in report_directory.iterdir()
    )
    assert unsafe_value not in serialized_files


def test_generator_fails_closed_before_file_write(tmp_path: Path):
    class InvalidHeaderClient:
        def read_asset_snapshot(self, spreadsheet_id, sheet_name):
            return [header for header in FULL_HEADERS if header != "QRCODE UNIT"], sample_rows()

    with pytest.raises(DatasheetHeaderError, match="QRCODE UNIT"):
        DatasheetReportGenerator(InvalidHeaderClient()).generate(
            "spreadsheet-id",
            "DATABASE INVENTARIS",
            output_root=tmp_path,
        )

    assert list(tmp_path.iterdir()) == []


def test_sheets_client_uses_header_only_query_and_quoted_sheet_name():
    client = SheetsClient.__new__(SheetsClient)
    client.service = MagicMock()
    request = client.service.spreadsheets.return_value.values.return_value.get.return_value
    request.execute.return_value = {"values": [["QRCODE UNIT"]]}

    assert client.read_headers("sheet-id", "DATABASE INVENTARIS") == ["QRCODE UNIT"]
    client.service.spreadsheets.return_value.values.return_value.get.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="'DATABASE INVENTARIS'!1:1",
    )


def test_sheets_client_returns_atomic_full_header_and_a_to_z_snapshot():
    client = SheetsClient.__new__(SheetsClient)
    client.service = MagicMock()
    request = client.service.spreadsheets.return_value.values.return_value.batchGet.return_value
    request.execute.return_value = {
        "valueRanges": [
            {"values": [FULL_HEADERS]},
            {
                "values": [
                    FULL_HEADERS[:26],
                    ["ROOM-1", "Barat", "Jakarta", "HO", "QR-1", "Laptop", "Elektronik"],
                ]
            },
        ]
    }

    headers, rows = client.read_asset_snapshot("sheet-id", "DATABASE INVENTARIS")

    assert headers == FULL_HEADERS
    assert rows[0]["QRCODE UNIT"] == "QR-1"
    assert rows[0]["KATEGORI ASSET"] == "Elektronik"
    assert rows[0]["LOKASI"] == ""
    client.service.spreadsheets.return_value.values.return_value.batchGet.assert_called_once_with(
        spreadsheetId="sheet-id",
        ranges=[
            "'DATABASE INVENTARIS'!1:1",
            "'DATABASE INVENTARIS'!A1:Z",
        ],
        majorDimension="ROWS",
    )


@pytest.mark.parametrize(
    "full_headers",
    [
        FULL_HEADERS + [" qrcode unit "],
        [header for header in FULL_HEADERS if header != "QRCODE UNIT"] + ["QRCODE UNIT"],
    ],
    ids=["duplicate-required-header-after-z", "required-header-moved-after-z"],
)
def test_sheets_client_rejects_required_header_drift_after_z(full_headers):
    client = SheetsClient.__new__(SheetsClient)
    client.service = MagicMock()
    request = client.service.spreadsheets.return_value.values.return_value.batchGet.return_value
    request.execute.return_value = {
        "valueRanges": [
            {"values": [full_headers]},
            {"values": [full_headers[:26]]},
        ]
    }

    with pytest.raises(SheetsClientError):
        client.read_asset_snapshot("sheet-id", "DATABASE INVENTARIS")


def test_sheets_client_rejects_full_header_and_data_prefix_drift():
    client = SheetsClient.__new__(SheetsClient)
    client.service = MagicMock()
    changed_prefix = list(FULL_HEADERS[:26])
    changed_prefix[4] = "QRCODE CHANGED"
    request = client.service.spreadsheets.return_value.values.return_value.batchGet.return_value
    request.execute.return_value = {
        "valueRanges": [
            {"values": [FULL_HEADERS]},
            {"values": [changed_prefix]},
        ]
    }

    with pytest.raises(SheetsClientError, match="header prefix differ"):
        client.read_asset_snapshot("sheet-id", "DATABASE INVENTARIS")
