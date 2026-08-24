import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence, Union
from zoneinfo import ZoneInfo

from app.core.config import (
    COMPUTER_SYNC_ASSET_TYPES,
    DATASHEET_SCOPE_SELECTOR,
)
from app.services.datasheet_schema import (
    SHEET_DATA_RANGE,
    SHEET_HEADER_RANGE,
    HeaderValidation,
    require_valid_headers,
)
from app.services.sheets_client import SheetsClient
from app.services.sync_service import SyncService


REPORT_SCHEMA_VERSION = 4
DEFAULT_REPORT_ROOT = Path("./data/reports")


class DatasheetReportError(RuntimeError):
    pass


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _normalized_category(value: Any) -> str:
    return (_text(value) or "").casefold()


def _normalized_dat(value: Any) -> Optional[str]:
    cleaned = _text(value)
    if not cleaned:
        return None
    return " ".join(cleaned.split()).casefold()


def _mapping_error_code(exc: Exception) -> str:
    """Reduce an arbitrary mapping exception to a non-sensitive report code."""
    message = str(exc)
    if message.startswith("TAHUN PEROLEHAN "):
        return "invalid_buy_date"
    if message.startswith("NILAI RUPIAH "):
        return "invalid_value"
    if message.startswith("PENYUSUTAN "):
        return "invalid_amortization"
    return "mapping_error"


def _json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _conflict_fields(requests: Sequence[Any]) -> list[str]:
    payloads = [request.model_dump() for request in requests]
    if not payloads:
        return []

    return sorted(
        field
        for field in payloads[0]
        if len({_json_value(payload.get(field)) for payload in payloads}) > 1
    )


def _markdown_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def build_datasheet_report(
    headers: Iterable[Any],
    rows: Sequence[dict[str, Any]],
    *,
    sheet_name: str,
    generated_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    validation = require_valid_headers(headers)
    if generated_at.tzinfo is None:
        raise DatasheetReportError("generated_at must include a timezone")
    asset_types = COMPUTER_SYNC_ASSET_TYPES
    asset_type_scope = frozenset(asset_types)

    missing_qr_rows = 0
    electronic_rows = 0
    electronic_missing_qr_rows = 0
    non_electronic_rows = 0
    unsupported_electronics: Counter[tuple[str, str]] = Counter()
    scope_excluded_by_type: Counter[str] = Counter()
    eligible_requests = []
    finance_requests_by_row: dict[int, Any] = {}
    mapping_errors: list[dict[str, Any]] = []

    for row_number, row in enumerate(rows, start=2):
        qrcode = _text(row.get("QRCODE UNIT"))
        if not qrcode:
            missing_qr_rows += 1

        if _normalized_category(row.get("KATEGORI ASSET")) != "elektronik":
            non_electronic_rows += 1
            continue

        electronic_rows += 1

        asset_type = SyncService.classify_sheet_asset_type(row)
        if asset_type is None:
            subcategory_1 = _normalized_category(row.get("SUB KATEGORI 1")) or "(kosong)"
            subcategory_2 = _normalized_category(row.get("SUB KATEGORI 2")) or "(kosong)"
            unsupported_electronics[(subcategory_1, subcategory_2)] += 1
            continue

        if asset_type not in asset_type_scope:
            scope_excluded_by_type[asset_type] += 1
            continue

        if not qrcode:
            electronic_missing_qr_rows += 1
            continue

        try:
            request = SyncService.map_sheet_row(row, include_finance=False)
        except Exception as exc:
            mapping_errors.append(
                {
                    "row_number": row_number,
                    "error_code": _mapping_error_code(exc),
                    "scope": "asset",
                }
            )
            continue

        if request is None or request.asset_type != asset_type:
            mapping_errors.append(
                {
                    "row_number": row_number,
                    "error_code": "mapping_error",
                    "scope": "asset",
                }
            )
            continue

        eligible_requests.append((row_number, request))
        try:
            finance_request = SyncService.map_sheet_row(row, include_finance=True)
        except Exception as exc:
            mapping_errors.append(
                {
                    "row_number": row_number,
                    "error_code": _mapping_error_code(exc),
                    "scope": "finance",
                }
            )
        else:
            if finance_request is None:
                mapping_errors.append(
                    {
                        "row_number": row_number,
                        "error_code": "mapping_error",
                        "scope": "finance",
                    }
                )
            else:
                finance_requests_by_row[row_number] = finance_request

    qr_groups = defaultdict(list)
    for row_number, request in eligible_requests:
        qr_groups[request.qrcode.casefold()].append((row_number, request))

    duplicate_groups = []
    duplicate_rows = 0
    unique_candidates = 0
    unique_requests = []
    eligible_by_type: Counter[str] = Counter()
    for _, request in eligible_requests:
        eligible_by_type[request.asset_type] += 1

    for normalized_qrcode in sorted(qr_groups):
        occurrences = sorted(qr_groups[normalized_qrcode], key=lambda occurrence: occurrence[0])
        if len(occurrences) == 1:
            unique_candidates += 1
            unique_requests.append(occurrences[0])
            continue

        duplicate_rows += len(occurrences)
        requests = [
            finance_requests_by_row.get(row_number, request)
            for row_number, request in occurrences
        ]
        duplicate_groups.append(
            {
                "qrcode": requests[0].qrcode,
                "row_numbers": [row_number for row_number, _ in occurrences],
                "conflict_fields": _conflict_fields(requests),
            }
        )

    finance_unique_requests = [
        (row_number, finance_requests_by_row[row_number])
        for row_number, _ in unique_requests
        if row_number in finance_requests_by_row
    ]
    dat_counts = Counter(
        normalized_dat
        for _, request in finance_unique_requests
        if (normalized_dat := _normalized_dat(request.dat_number)) is not None
    )
    duplicate_dat_groups = sum(count > 1 for count in dat_counts.values())
    duplicate_dat_rows = sum(count for count in dat_counts.values() if count > 1)

    unsupported_items = [
        {
            "sub_category_1": subcategory_1,
            "sub_category_2": subcategory_2,
            "count": count,
        }
        for (subcategory_1, subcategory_2), count in sorted(
            unsupported_electronics.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        )
    ]

    fetched_rows = len(rows)
    eligible_rows = len(eligible_requests)
    unsupported_rows = sum(unsupported_electronics.values())
    scope_excluded_rows = sum(scope_excluded_by_type.values())
    mapping_error_counts = Counter(error["error_code"] for error in mapping_errors)
    asset_mapping_errors = [error for error in mapping_errors if error["scope"] == "asset"]
    finance_mapping_errors = [
        error for error in mapping_errors if error["scope"] == "finance"
    ]
    mapping_error_rows = len(mapping_errors)
    asset_mapping_error_rows = len(asset_mapping_errors)
    finance_mapping_error_rows = len(finance_mapping_errors)
    finance_valid_rows = len(finance_requests_by_row)
    invariants = {
        "fetched_partition": fetched_rows == electronic_rows + non_electronic_rows,
        "electronic_partition": electronic_rows
        == eligible_rows
        + unsupported_rows
        + scope_excluded_rows
        + electronic_missing_qr_rows
        + asset_mapping_error_rows,
        "eligible_partition": eligible_rows == duplicate_rows + unique_candidates,
        "finance_validation_partition": eligible_rows
        == finance_valid_rows + finance_mapping_error_rows,
    }

    asset_write_blocked = (
        not validation.is_valid
        or not all(invariants.values())
        or bool(duplicate_groups)
        or asset_mapping_error_rows > 0
    )
    finance_write_blocked = (
        asset_write_blocked
        or finance_mapping_error_rows > 0
        or duplicate_dat_groups > 0
    )

    generated_at_iso = generated_at.isoformat()
    summary = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": generated_at_iso,
        "mode": "google_sheets_read_only",
        "source": {
            "sheet_name": sheet_name,
            "header_range": SHEET_HEADER_RANGE,
            "data_range": SHEET_DATA_RANGE,
            "spreadsheet_id_included": False,
            "asset_types": list(asset_types),
            "datasheet_scope_selector": DATASHEET_SCOPE_SELECTOR,
        },
        "header_validation": validation.to_dict(),
        "counts": {
            "fetched_rows": fetched_rows,
            "missing_qr_rows": missing_qr_rows,
            "electronic_rows": electronic_rows,
            "electronic_missing_qr_rows": electronic_missing_qr_rows,
            "non_electronic_rows": non_electronic_rows,
            "eligible_rows": eligible_rows,
            "eligible_computers": eligible_by_type.get("Computer", 0),
            "unsupported_electronic_rows": unsupported_rows,
            "unsupported_electronic_combinations": len(unsupported_items),
            "scope_excluded_rows": scope_excluded_rows,
            "scope_excluded_monitors": scope_excluded_by_type.get("Monitor", 0),
            "duplicate_groups": len(duplicate_groups),
            "duplicate_rows": duplicate_rows,
            "unique_candidates": unique_candidates,
            "duplicate_dat_groups": duplicate_dat_groups,
            "duplicate_dat_rows": duplicate_dat_rows,
            "finance_valid_rows": finance_valid_rows,
            "finance_valid_unique_candidates": len(finance_unique_requests),
            "mapping_error_rows": mapping_error_rows,
            "asset_mapping_error_rows": asset_mapping_error_rows,
            "finance_mapping_error_rows": finance_mapping_error_rows,
            "mapping_error_categories": len(mapping_error_counts),
        },
        "unsupported_electronics": unsupported_items,
        "mapping_errors_by_code": dict(sorted(mapping_error_counts.items())),
        "gates": {
            "header_valid": validation.is_valid,
            "counts_consistent": all(invariants.values()),
            "duplicate_rows_excluded_from_unique_candidates": True,
            "duplicate_qr_free": len(duplicate_groups) == 0,
            "write_blocked_by_duplicate_qr": len(duplicate_groups) > 0,
            "asset_mapping_errors_free": asset_mapping_error_rows == 0,
            "asset_write_blocked_by_mapping_errors": asset_mapping_error_rows > 0,
            "asset_write_blocked": asset_write_blocked,
            "duplicate_dat_free": duplicate_dat_groups == 0,
            "finance_write_blocked_by_duplicate_dat": duplicate_dat_groups > 0,
            "finance_mapping_errors_free": finance_mapping_error_rows == 0,
            "finance_write_blocked_by_mapping_errors": finance_mapping_error_rows > 0,
            "finance_write_blocked": finance_write_blocked,
            "invariants": invariants,
        },
    }
    details = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": generated_at_iso,
        "source": {
            "sheet_name": sheet_name,
            "asset_types": list(asset_types),
            "datasheet_scope_selector": DATASHEET_SCOPE_SELECTOR,
        },
        "duplicate_groups": duplicate_groups,
        "mapping_errors": mapping_errors,
    }
    markdown = _render_summary_markdown(summary)
    return summary, details, markdown


def _render_summary_markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    validation = summary["header_validation"]
    gates = summary["gates"]
    lines = [
        "# Datasheet Asset Sync Preflight",
        "",
        f"Generated: `{_markdown_cell(summary['generated_at'])}`",
        f"Source tab: `{_markdown_cell(summary['source']['sheet_name'])}`",
        "Asset scope: `{}`".format(
            _markdown_cell(", ".join(summary["source"]["asset_types"]))
        ),
        "Datasheet selector: `{}`".format(
            _markdown_cell(summary["source"]["datasheet_scope_selector"])
        ),
        "Mode: Google Sheets read-only; GLPI and Registration Asset Excel were not accessed.",
        "",
        "## Header validation",
        "",
        f"- Result: `{'PASS' if validation['is_valid'] else 'FAIL'}`",
        f"- Observed headers: {validation['header_count']}",
        f"- Missing required headers: {len(validation['missing_headers'])}",
        f"- Duplicate headers: {len(validation['duplicate_headers'])}",
        f"- Required headers outside A:Z: {len(validation['required_headers_outside_data_range'])}",
        "",
        "## Counts",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
    ]
    count_labels = (
        ("Fetched rows", "fetched_rows"),
        ("Electronic rows", "electronic_rows"),
        ("Asset-eligible rows", "eligible_rows"),
        ("Eligible Computers", "eligible_computers"),
        ("Unsupported electronic rows", "unsupported_electronic_rows"),
        ("Unsupported electronic combinations", "unsupported_electronic_combinations"),
        ("Rows excluded by asset scope", "scope_excluded_rows"),
        ("Excluded Monitors", "scope_excluded_monitors"),
        ("Missing QR rows", "missing_qr_rows"),
        ("Duplicate QR groups", "duplicate_groups"),
        ("Duplicate rows excluded", "duplicate_rows"),
        ("Unique asset candidates", "unique_candidates"),
        ("Finance-valid rows", "finance_valid_rows"),
        ("Finance-valid unique candidates", "finance_valid_unique_candidates"),
        ("Duplicate DAT groups", "duplicate_dat_groups"),
        ("Duplicate DAT rows", "duplicate_dat_rows"),
        ("Mapping error rows", "mapping_error_rows"),
        ("Asset mapping error rows", "asset_mapping_error_rows"),
        ("Finance mapping error rows", "finance_mapping_error_rows"),
        ("Mapping error categories", "mapping_error_categories"),
    )
    lines.extend(f"| {label} | {counts[key]} |" for label, key in count_labels)
    lines.extend(
        [
            "",
            "## Unsupported electronics (aggregate only)",
            "",
            "| Sub-category 1 | Sub-category 2 | Count |",
            "| --- | --- | ---: |",
        ]
    )
    unsupported = summary["unsupported_electronics"]
    if unsupported:
        lines.extend(
            "| {} | {} | {} |".format(
                _markdown_cell(item["sub_category_1"]),
                _markdown_cell(item["sub_category_2"]),
                item["count"],
            )
            for item in unsupported
        )
    else:
        lines.append("| _(none)_ | _(none)_ | 0 |")

    lines.extend(
        [
            "",
            "## Mapping validation errors (aggregate only)",
            "",
            "| Error code | Count |",
            "| --- | ---: |",
        ]
    )
    mapping_errors_by_code = summary["mapping_errors_by_code"]
    if mapping_errors_by_code:
        lines.extend(
            f"| {_markdown_cell(error_code)} | {count} |"
            for error_code, count in mapping_errors_by_code.items()
        )
    else:
        lines.append("| _(none)_ | 0 |")

    lines.extend(
        [
            "",
            "## Safety gates",
            "",
            f"- Header gate: `{'PASS' if gates['header_valid'] else 'FAIL'}`",
            f"- Count invariants: `{'PASS' if gates['counts_consistent'] else 'FAIL'}`",
            "- Duplicate QR gate: `PASS`."
            if gates["duplicate_qr_free"]
            else "- Duplicate QR gate: `FAIL`; all asset and finance writes are blocked.",
            "- Every duplicate QR group is excluded from the unique candidate count.",
            "- Asset mapping gate: `PASS`."
            if gates["asset_mapping_errors_free"]
            else "- Asset mapping gate: `FAIL`; all asset and finance writes are blocked.",
            "- Finance mapping gate: `PASS`."
            if gates["finance_mapping_errors_free"]
            else "- Finance mapping gate: `FAIL`; finance writes are blocked, while asset-only planning remains available if its gates pass.",
            "- Duplicate DAT gate: `PASS`."
            if gates["duplicate_dat_free"]
            else "- Duplicate DAT gate: `FAIL`; finance writes are blocked, while asset-only planning remains available if its gates pass.",
            "- Duplicate DAT counts are aggregate only; DAT values are omitted from all report files.",
            "- Mapping error details contain row numbers and controlled error codes only; raw values, messages, and PII are omitted.",
            "- Duplicate QR and row numbers are stored only in `details.json`; conflict values and PII are omitted.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_exclusive(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(content)


class DatasheetReportGenerator:
    def __init__(
        self,
        sheets_client: Optional[SheetsClient] = None,
        now_factory: Optional[Callable[[], datetime]] = None,
    ):
        self.sheets = sheets_client if sheets_client is not None else SheetsClient()
        self.now_factory = now_factory

    def generate(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        *,
        output_root: Union[str, Path] = DEFAULT_REPORT_ROOT,
        timezone_name: str = "Asia/Jakarta",
    ) -> dict[str, Any]:
        # One batchGet snapshot contains both the full header row and A:Z data.
        headers, rows = self.sheets.read_asset_snapshot(spreadsheet_id, sheet_name)
        validation: HeaderValidation = require_valid_headers(headers)

        generated_at = self.now_factory() if self.now_factory else datetime.now(ZoneInfo(timezone_name))
        summary, details, markdown = build_datasheet_report(
            headers,
            rows,
            sheet_name=sheet_name,
            generated_at=generated_at,
        )
        if not validation.is_valid:  # Defensive; require_valid_headers already raises.
            raise DatasheetReportError("Refusing to write a report with invalid headers")

        report_root = Path(output_root)
        directory_name = generated_at.strftime("%Y%m%dT%H%M%S%f%z")
        report_directory = report_root / directory_name
        report_directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        os.chmod(report_directory, 0o700)

        summary_json_path = report_directory / "summary.json"
        details_json_path = report_directory / "details.json"
        summary_markdown_path = report_directory / "summary.md"
        _write_exclusive(
            summary_json_path,
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        _write_exclusive(
            details_json_path,
            json.dumps(details, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        _write_exclusive(summary_markdown_path, markdown)

        return {
            "report_directory": report_directory,
            "summary_json": summary_json_path,
            "details_json": details_json_path,
            "summary_markdown": summary_markdown_path,
            "summary": summary,
        }
