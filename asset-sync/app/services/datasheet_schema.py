from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Tuple


SHEET_DATA_COLUMN_LIMIT = 26
SHEET_DATA_RANGE = "A1:Z"
SHEET_HEADER_RANGE = "1:1"

# Keep this list aligned with SyncService.map_sheet_row. Header names are
# deliberately exact because Google Sheets keys are case- and space-sensitive.
REQUIRED_SHEET_HEADERS: Tuple[str, ...] = (
    "QRCODE UNIT",
    "JENIS ASSET",
    "KATEGORI ASSET",
    "SUB KATEGORI 1",
    "SUB KATEGORI 2",
    "MERK",
    "TYPE",
    "NAMA USER",
    "KETERANGAN",
    "NO. ASSET AKUNTANSI (DAT)",
    "TAHUN PEROLEHAN",
    "NILAI RUPIAH",
    "PENYUSUTAN",
    "KONDISI",
    "WILAYAH",
    "CABANG",
    "AREA",
    "LOKASI",
)


@dataclass(frozen=True)
class HeaderValidation:
    header_count: int
    observed_headers: Tuple[str, ...]
    missing_headers: Tuple[str, ...]
    duplicate_headers: Tuple[str, ...]
    blank_header_positions: Tuple[int, ...]
    required_headers_outside_data_range: Tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not any(
            (
                self.missing_headers,
                self.duplicate_headers,
                self.blank_header_positions,
                self.required_headers_outside_data_range,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "header_count": self.header_count,
            "observed_headers": list(self.observed_headers),
            "required_headers": list(REQUIRED_SHEET_HEADERS),
            "missing_headers": list(self.missing_headers),
            "duplicate_headers": list(self.duplicate_headers),
            "blank_header_positions": list(self.blank_header_positions),
            "required_headers_outside_data_range": list(self.required_headers_outside_data_range),
            "data_column_limit": SHEET_DATA_COLUMN_LIMIT,
        }


class DatasheetHeaderError(ValueError):
    def __init__(self, validation: HeaderValidation):
        problems = []
        if validation.missing_headers:
            problems.append(f"missing={','.join(validation.missing_headers)}")
        if validation.duplicate_headers:
            problems.append(f"duplicate={','.join(validation.duplicate_headers)}")
        if validation.blank_header_positions:
            positions = ",".join(str(position) for position in validation.blank_header_positions)
            problems.append(f"blank_positions={positions}")
        if validation.required_headers_outside_data_range:
            outside = ",".join(validation.required_headers_outside_data_range)
            problems.append(f"outside_A_to_Z={outside}")
        message = "; ".join(problems) or "unknown header validation error"
        super().__init__(f"Datasheet header validation failed: {message}")
        self.validation = validation


def validate_headers(headers: Iterable[Any]) -> HeaderValidation:
    observed_headers = tuple("" if header is None else str(header) for header in headers)
    exact_positions = {header: index for index, header in enumerate(observed_headers)}

    normalized_positions: dict[str, list[int]] = defaultdict(list)
    blank_header_positions = []
    for index, header in enumerate(observed_headers, start=1):
        normalized = header.strip().casefold()
        if not normalized:
            blank_header_positions.append(index)
            continue
        normalized_positions[normalized].append(index)

    duplicate_headers = tuple(
        sorted(
            observed_headers[positions[0] - 1].strip()
            for positions in normalized_positions.values()
            if len(positions) > 1
        )
    )
    missing_headers = tuple(header for header in REQUIRED_SHEET_HEADERS if header not in exact_positions)
    outside_data_range = tuple(
        header
        for header in REQUIRED_SHEET_HEADERS
        if header in exact_positions and exact_positions[header] >= SHEET_DATA_COLUMN_LIMIT
    )

    return HeaderValidation(
        header_count=len(observed_headers),
        observed_headers=observed_headers,
        missing_headers=missing_headers,
        duplicate_headers=duplicate_headers,
        blank_header_positions=tuple(blank_header_positions),
        required_headers_outside_data_range=outside_data_range,
    )


def require_valid_headers(headers: Iterable[Any]) -> HeaderValidation:
    validation = validate_headers(headers)
    if not validation.is_valid:
        raise DatasheetHeaderError(validation)
    return validation
