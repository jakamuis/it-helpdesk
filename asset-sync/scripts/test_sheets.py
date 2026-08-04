from google.oauth2 import service_account
from googleapiclient.discovery import build

try:
    credentials = service_account.Credentials.from_service_account_file("data/service_account.json", scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    service = build("sheets", "v4", credentials=credentials)
    sheet_metadata = service.spreadsheets().get(spreadsheetId="1PyLMINlMTow2wHkj8T7EkfuXDvN6GtFzlSCG7JX0bgg").execute()
    sheets = sheet_metadata.get('sheets', '')
    print("SUCCESS")
    for sheet in sheets:
        print(f"Found sheet: {sheet.get('properties', {}).get('title', '')}")
except Exception as e:
    print(f"FAILED: {e}")
