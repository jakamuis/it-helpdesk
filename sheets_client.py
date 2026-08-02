"""
Google Sheets API Client Module.

Handles authentication with Google Cloud Service Account JSON credentials and performs
reading, writing, updating, and appending rows in Google Sheets (AppSheet backend).
"""

import os
import logging
from typing import List, Dict, Any, Optional, Sequence
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class GoogleSheetsClientError(Exception):
    """Base exception for Google Sheets Client errors."""
    pass


class GoogleSheetsClient:
    """
    Client for interacting with Google Sheets API v4 using a Service Account.
    """

    def __init__(self, credentials_path: str):
        """
        Initialize Google Sheets client.

        :param credentials_path: Path to the Service Account JSON credentials file.
        """
        self.credentials_path = credentials_path
        self.service = self._authenticate()

    def _authenticate(self):
        """
        Authenticate using Google Service Account JSON file.

        :return: Google Sheets Resource object
        """
        if not os.path.exists(self.credentials_path):
            raise GoogleSheetsClientError(
                f"Service account credentials file not found at path: '{self.credentials_path}'"
            )

        try:
            logger.info(f"Authenticating with Google Sheets API using '{self.credentials_path}'...")
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=SCOPES
            )
            service = build("sheets", "v4", credentials=credentials)
            logger.info("Google Sheets API authentication successful.")
            return service
        except Exception as e:
            msg = f"Failed to authenticate with Google Sheets API: {e}"
            logger.error(msg)
            raise GoogleSheetsClientError(msg) from e

    def get_values(self, spreadsheet_id: str, range_name: str) -> List[List[Any]]:
        """
        Retrieve row values from a spreadsheet range.

        :param spreadsheet_id: The ID of the spreadsheet.
        :param range_name: The A1 notation or sheet name range (e.g. "Tickets!A1:Z100").
        :return: List of row lists.
        """
        try:
            logger.info(f"Reading data from Google Sheet '{spreadsheet_id}' range '{range_name}'...")
            sheet = self.service.spreadsheets()
            result = sheet.values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
            rows = result.get("values", [])
            logger.info(f"Retrieved {len(rows)} row(s) from sheet range '{range_name}'.")
            return rows
        except HttpError as e:
            msg = f"Google Sheets API error while reading range '{range_name}': {e}"
            logger.error(msg)
            raise GoogleSheetsClientError(msg) from e
        except Exception as e:
            msg = f"Unexpected error reading Google Sheets range '{range_name}': {e}"
            logger.error(msg)
            raise GoogleSheetsClientError(msg) from e

    def append_rows(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: List[List[Any]],
        value_input_option: str = "USER_ENTERED"
    ) -> Dict[str, Any]:
        """
        Append rows to a spreadsheet table.

        :param spreadsheet_id: The ID of the spreadsheet.
        :param range_name: Target sheet name or range (e.g. "Tickets!A1").
        :param values: 2D list of values to append [[val1, val2], [val3, val4]].
        :param value_input_option: How input data should be interpreted ('USER_ENTERED' or 'RAW').
        :return: Response dictionary from Google Sheets API.
        """
        if not values:
            logger.warning("No rows provided to append_rows. Skipping execution.")
            return {}

        try:
            logger.info(f"Appending {len(values)} row(s) to Google Sheet range '{range_name}'...")
            body = {
                "values": values
            }
            sheet = self.service.spreadsheets()
            result = sheet.values().append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                insertDataOption="INSERT_ROWS",
                body=body
            ).execute()

            updates = result.get("updates", {})
            updated_rows = updates.get("updatedRows", 0)
            logger.info(f"Successfully appended {updated_rows} row(s) to range '{range_name}'.")
            return result
        except HttpError as e:
            msg = f"Google Sheets API error while appending rows: {e}"
            logger.error(msg)
            raise GoogleSheetsClientError(msg) from e
        except Exception as e:
            msg = f"Unexpected error appending rows to Google Sheets: {e}"
            logger.error(msg)
            raise GoogleSheetsClientError(msg) from e

    def update_range(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: List[List[Any]],
        value_input_option: str = "USER_ENTERED"
    ) -> Dict[str, Any]:
        """
        Update specific range in a spreadsheet.

        :param spreadsheet_id: The ID of the spreadsheet.
        :param range_name: Target A1 range (e.g. "Tickets!A1:G100").
        :param values: 2D list of values to write.
        :param value_input_option: How input data should be interpreted.
        :return: Response dictionary from Google Sheets API.
        """
        try:
            logger.info(f"Updating Google Sheet range '{range_name}' with {len(values)} row(s)...")
            body = {
                "values": values
            }
            sheet = self.service.spreadsheets()
            result = sheet.values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                body=body
            ).execute()

            updated_cells = result.get("updatedCells", 0)
            logger.info(f"Successfully updated {updated_cells} cell(s) in range '{range_name}'.")
            return result
        except HttpError as e:
            msg = f"Google Sheets API error while updating range '{range_name}': {e}"
            logger.error(msg)
            raise GoogleSheetsClientError(msg) from e
        except Exception as e:
            msg = f"Unexpected error updating Google Sheets range '{range_name}': {e}"
            logger.error(msg)
            raise GoogleSheetsClientError(msg) from e

    def sync_records(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        headers: List[str],
        records: List[List[Any]],
        clear_existing: bool = False
    ) -> Dict[str, Any]:
        """
        Synchronize GLPI records to Google Sheets tab. Ensures headers exist on row 1.

        :param spreadsheet_id: The ID of the spreadsheet.
        :param sheet_name: Sheet tab name (e.g. "Tickets").
        :param headers: Header column names.
        :param records: Rows of records matching the headers.
        :param clear_existing: If True, clear sheet and overwrite with headers + records.
        :return: Result summary dict.
        """
        # Ensure sheet range
        range_full = f"{sheet_name}!A1"

        if clear_existing:
            logger.info(f"Clearing existing data in sheet '{sheet_name}'...")
            all_values = [headers] + records
            return self.update_range(spreadsheet_id, range_full, all_values)

        # Check existing content
        existing_rows = self.get_values(spreadsheet_id, f"{sheet_name}!A1:Z1")
        if not existing_rows or not existing_rows[0]:
            logger.info(f"Sheet '{sheet_name}' is empty. Writing headers first...")
            self.update_range(spreadsheet_id, f"{sheet_name}!A1", [headers])

        if records:
            return self.append_rows(spreadsheet_id, f"{sheet_name}!A1", records)

        return {"status": "no_records_to_sync"}
