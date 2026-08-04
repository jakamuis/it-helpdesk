from google.oauth2 import service_account
from googleapiclient.discovery import build

try:
    credentials = service_account.Credentials.from_service_account_file("data/service_account.json", scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    service = build("sheets", "v4", credentials=credentials)
    result = service.spreadsheets().values().get(spreadsheetId="1PyLMINlMTow2wHkj8T7EkfuXDvN6GtFzlSCG7JX0bgg", range="DATABASE INVENTARIS!A1:Z1").execute()
    headers = result.get('values', [[]])[0]
    print("HEADERS:")
    for h in headers:
        print(f"- {h}")
except Exception as e:
    print(f"FAILED: {e}")
