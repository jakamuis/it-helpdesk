import logging
from typing import Any, Dict, List, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.core.config import settings
from app.services.datasheet_schema import (
    SHEET_DATA_COLUMN_LIMIT,
    SHEET_DATA_RANGE,
    SHEET_HEADER_RANGE,
    require_valid_headers,
)

logger = logging.getLogger(__name__)

class SheetsClientError(Exception):
    pass

class SheetsClient:
    def __init__(self):
        self.credentials_path = settings.GOOGLE_CREDENTIALS_PATH
        self.scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        self.service = self._authenticate()

    def _authenticate(self):
        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=self.scopes
            )
            return build("sheets", "v4", credentials=credentials)
        except Exception as e:
            logger.error(f"Failed to authenticate Google Sheets: {e}")
            raise SheetsClientError(f"Auth failed: {e}")

    @staticmethod
    def _sheet_range(sheet_name: str, cell_range: str) -> str:
        escaped_name = sheet_name.replace("'", "''")
        return f"'{escaped_name}'!{cell_range}"

    def read_headers(self, spreadsheet_id: str, sheet_name: str) -> List[str]:
        """Read only row 1 across the whole tab for fail-closed schema validation."""
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=self._sheet_range(sheet_name, SHEET_HEADER_RANGE),
            ).execute()
            values = result.get("values", [])
            return values[0] if values else []
        except Exception as e:
            logger.error(f"Failed to read Google Sheets headers: {e}")
            raise SheetsClientError(f"Header read failed: {e}")

    def read_asset_snapshot(
        self,
        spreadsheet_id: str,
        sheet_name: str,
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        """Read and validate the full header plus A:Z rows in one API request.

        The full row-1 range detects required headers that were duplicated or
        moved beyond column Z. The A1:Z range supplies the row data. Fetching
        both ranges with ``values.batchGet`` also removes the earlier window in
        which the header could change between two independent requests.
        """
        try:
            sheet = self.service.spreadsheets()
            result = sheet.values().batchGet(
                spreadsheetId=spreadsheet_id,
                ranges=[
                    self._sheet_range(sheet_name, SHEET_HEADER_RANGE),
                    self._sheet_range(sheet_name, SHEET_DATA_RANGE),
                ],
                majorDimension="ROWS",
            ).execute()

            value_ranges = result.get("valueRanges")
            if not isinstance(value_ranges, list) or len(value_ranges) != 2:
                raise SheetsClientError(
                    "Snapshot response did not contain both requested ranges"
                )

            full_header_rows = value_ranges[0].get("values", [])
            data_rows = value_ranges[1].get("values", [])
            if not isinstance(full_header_rows, list) or not isinstance(data_rows, list):
                raise SheetsClientError("Snapshot response contained invalid row data")

            full_headers = full_header_rows[0] if full_header_rows else []
            require_valid_headers(full_headers)

            if not data_rows:
                raise SheetsClientError("A1:Z snapshot did not contain its header row")

            data_headers = data_rows[0]
            expected_header_count = min(len(full_headers), SHEET_DATA_COLUMN_LIMIT)
            expected_prefix = full_headers[:expected_header_count]
            if len(data_headers) != expected_header_count or tuple(data_headers) != tuple(
                expected_prefix
            ):
                raise SheetsClientError(
                    "Full header and A1:Z header prefix differ within the same snapshot"
                )

            data = []
            for row_number, row in enumerate(data_rows[1:], start=2):
                if len(row) > len(data_headers):
                    raise SheetsClientError(
                        f"Snapshot row {row_number} has values beyond its validated header"
                    )
                row_dict = dict(
                    zip(data_headers, row + [""] * (len(data_headers) - len(row)))
                )
                data.append(row_dict)

            return list(full_headers), data

        except SheetsClientError:
            raise
        except Exception as e:
            logger.error(f"Failed to read from Google Sheets: {e}")
            raise SheetsClientError(f"Read failed: {e}")

    def read_all_assets(self, spreadsheet_id: str, sheet_name: str) -> List[Dict[str, Any]]:
        """Compatibility wrapper returning rows from one validated snapshot."""
        _, rows = self.read_asset_snapshot(spreadsheet_id, sheet_name)
        return rows
