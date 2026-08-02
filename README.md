# GLPI to Google Sheets & AppSheet Sync Service

A production-ready Python synchronization service that integrates the **GLPI REST API** with **Google Sheets** (which serves as the backend data source for AppSheet applications) and supports **direct AppSheet Inbound REST API** calls.

---

## Features

- **GLPI Integration (`glpi_client.py`)**:
  - Full REST API authentication lifecycle (`initSession` / `killSession`).
  - Context manager support (`with GLPIClient(...) as client:`).
  - Fetches GLPI Tickets (`GET /Ticket`) and Assets (`GET /Computer`, `GET /Monitor`, etc.).
  - Automatic retry logic on transient HTTP errors (429, 5xx).

- **Google Sheets Integration (`sheets_client.py`)**:
  - Service Account authentication via Google Cloud credentials JSON.
  - Reads existing records, appends rows, updates ranges with `USER_ENTERED` formatting.
  - Automatic sheet header initialization.

- **AppSheet Direct REST API Integration (`appsheet_client.py`)**:
  - Direct integration via AppSheet Inbound REST API (`POST https://api.appsheet.com/api/v2/apps/{appId}/tables/{tableName}/Action`).
  - Supports `Add`, `Edit`, and `Upsert` table actions.
  - Custom header handling (`ApplicationAccessKey`).

- **CLI & Configuration (`main.py`)**:
  - Flexible environment variable configuration via `.env`.
  - Supports CLI flags (`--mode`, `--item-type`, `--limit`, `--dry-run`).
  - Structured logging.

---

## Project Structure

```
GLPI/
├── main.py              # Main CLI entry point orchestrating synchronization
├── glpi_client.py       # GLPI REST API client (initSession, fetch, killSession)
├── sheets_client.py     # Google Sheets API v4 client using Service Account
├── appsheet_client.py   # AppSheet Direct Inbound REST API client
├── requirements.txt     # Python dependencies
├── .env.example         # Template environment configuration
└── README.md            # Setup and usage guide
```

---

## Prerequisites

- **Python 3.8+**
- Access to a **GLPI instance** with REST API enabled.
- A **Google Cloud Project** with Google Sheets API enabled and a Service Account key (`credentials.json`).
- An **AppSheet Application** (if using AppSheet Direct API sync).

---

## Setup Guide

### 1. Clone & Environment Setup

```bash
# Navigate to project directory
cd /path/to/GLPI

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` with your actual API credentials:

```ini
# GLPI Configuration
GLPI_URL=https://glpi.your-domain.com/apirest.php
GLPI_APP_TOKEN=your_glpi_app_token
GLPI_USER_TOKEN=your_glpi_user_token

# Google Sheets Configuration
GOOGLE_SPREADSHEET_ID=1A2b3C4d5E6f7G8h9I0j
GOOGLE_SHEET_NAME=Tickets
GOOGLE_CREDENTIALS_FILE=credentials.json

# AppSheet Configuration
APPSHEET_APP_ID=5d5a71df-xxxx-xxxx-xxxx-xxxxxxxxxxxx
APPSHEET_ACCESS_KEY=V2-xxxx-xxxx-xxxx-xxxx
APPSHEET_TABLE_NAME=Tickets

# Sync Settings
SYNC_MODE=both
GLPI_ITEM_TYPE=Ticket
FETCH_LIMIT=100
LOG_LEVEL=INFO
```

---

## Integration Setup Details

### A. GLPI REST API Setup
1. In GLPI, navigate to **Setup > API**.
2. Enable HTTP API and API client access.
3. Generate an **App-Token** under API clients.
4. Under your GLPI user profile (top right corner > My settings > API token), generate a **User-Token**.
5. Set `GLPI_URL`, `GLPI_APP_TOKEN`, and `GLPI_USER_TOKEN` in `.env`.

### B. Google Sheets Service Account Setup
1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or select an existing one) and enable the **Google Sheets API**.
3. Go to **IAM & Admin > Service Accounts** and create a Service Account.
4. Create a key in **JSON** format and download it to your project folder as `credentials.json`.
5. Open your target Google Sheet and click **Share**. Share it with the Service Account email (found inside `credentials.json` under `client_email`), granting **Editor** access.
6. Copy the Spreadsheet ID from the URL (`https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit`) and set `GOOGLE_SPREADSHEET_ID` in `.env`.

### C. AppSheet Direct REST API Setup
1. Open your AppSheet editor at [appsheet.com](https://www.appsheet.com).
2. Navigate to **Manage > Integrations > INBOUND WEBHOOKS**.
3. Enable Application Access Key and copy your **ApplicationAccessKey**.
4. Retrieve your **App ID** (from the URL or under Info > Properties).
5. Set `APPSHEET_APP_ID`, `APPSHEET_ACCESS_KEY`, and `APPSHEET_TABLE_NAME` in `.env`.

---

## Usage Examples

### Run Default Synchronization
Runs sync according to `.env` settings (`SYNC_MODE=both` by default):

```bash
python main.py
```

### Dry Run (Test Data Processing Without Modifying Sheets or AppSheet)

```bash
python main.py --dry-run
```

### Sync Only to Google Sheets

```bash
python main.py --mode sheets
```

### Sync Only to AppSheet API

```bash
python main.py --mode appsheet
```

### Sync Asset Data (e.g. Computers) Instead of Tickets

```bash
python main.py --item-type Computer --limit 50
```

---

## Error Handling & Reliability

- **GLPI Session Safety**: Sessions are opened (`initSession`) and explicitly destroyed (`killSession`) using Python context managers, ensuring GLPI session limits are never exceeded.
- **HTTP Retries**: Automatic exponential backoff retries on HTTP `429` (Rate Limit) and `5xx` server errors using `urllib3.util.retry.Retry`.
- **Validation**: Environment variables and input files are validated before launching sync operations.
