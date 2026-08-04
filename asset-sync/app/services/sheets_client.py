import logging
from typing import List, Dict, Any
from google.oauth2 import service_account
from googleapiclient.discovery import build
from app.core.config import settings

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

    def read_all_assets(self, spreadsheet_id: str, sheet_name: str) -> List[Dict[str, Any]]:
        """Reads all rows from the specified sheet and maps headers to dictionaries."""
        try:
            sheet = self.service.spreadsheets()
            result = sheet.values().get(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A1:Z" # Assuming max Z columns
            ).execute()
            
            rows = result.get("values", [])
            if not rows:
                return []
                
            headers = rows[0]
            data = []
            
            for row in rows[1:]:
                # Zip headers with row values, filling missing values with empty string
                row_dict = dict(zip(headers, row + [""] * (len(headers) - len(row))))
                data.append(row_dict)
                
            return data
            
        except Exception as e:
            logger.error(f"Failed to read from Google Sheets: {e}")
            raise SheetsClientError(f"Read failed: {e}")
