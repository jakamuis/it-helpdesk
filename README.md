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

- **WhatsApp Integration (`wa-glpi/app.py`)**:
  - Acts as middleware between GLPI and WAHA (WhatsApp HTTP API).
  - Handles chat monitoring and ticket followup synchronization.

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
├── wa-glpi/             # WhatsApp to GLPI middleware integration
├── waha-data/           # WAHA (WhatsApp HTTP API) session data
├── asset-sync/          # Asset synchronization tools and scripts
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

---

## Local AI Triage (Phase 1)

This project includes local, advisory AI triage for incoming WhatsApp tickets. An actionable report creates a GLPI ticket immediately; AI classification and one-question-at-a-time clarification then enrich the same ticket. Helpdesk staff remain the final decision makers.

### Architecture

- `wa-glpi`: Durable message deduplication, retry/recovery, early ticket creation, conversation state, and safe WhatsApp replies.
- `ai-triage`: A FastAPI service that validates structured model output, applies deterministic safety rules, redacts sensitive data, and writes a metadata-only audit trail.
- `ollama`: A local Ollama instance running the lightweight classifier (default `qwen3:0.6b`). No external AI APIs are used.

### Setup and Configuration

1. **Enable AI**: In your `.env` file, set `AI_TRIAGE_ENABLED=true` (disabled by default for safety).
2. **Configure Ollama**: The CPU-friendly default is `qwen3:0.6b`. A larger model can be selected on an accelerated host.
3. **Build and Run**:
   ```bash
   docker compose up -d --build ollama ai-triage wa-glpi
   ```
4. **Pull Model**:
   ```bash
   docker compose exec ollama ollama pull qwen3:0.6b
   ```

### Features & Security

- **Deterministic Fallbacks**: Critical keywords (e.g., "ransomware", "pabrik mati") bypass the LLM and instantly flag for human escalation.
- **Redaction**: Passwords, OTPs, and API tokens are redacted before sending to the LLM.
- **Controlled Replies**: Model-generated prose is never sent to WhatsApp. Follow-up questions come from an allowlisted Indonesian template set.
- **Bounded Hybrid Inference**: Explicit common issues are routed instantly by inspectable local rules. Direct answers to clarification questions reuse durable conversation context without another model call. Other ambiguous messages use Ollama for one allowlisted route code and are marked for human review.
- **Helpdesk Workflow**: AI values are appended as advisory ticket notes; Phase 1 does not overwrite native GLPI category, priority, group, or assignee fields.
- **Idempotency**: Processed message IDs, conversation state, acknowledgements, and retry state persist in SQLite. GLPI writes carry a WAHA message marker for recovery.
- **Fallback Behavior**: If the AI service fails or times out, the system automatically falls back to standard helpdesk ticket creation without losing the message.

### Testing AI Triage API

The service stays internal to the Compose network because host port `8000` is already used by the CCTV project. Test it inside the container:

```bash
docker compose exec -T ai-triage python -c '
import json, urllib.request
payload = json.dumps({
    "conversation_id": "manual-test-1",
    "message": "printer saya rusak kertasnya macet",
    "conversation_state": {}
}).encode()
request = urllib.request.Request(
    "http://127.0.0.1:8000/api/v1/triage",
    data=payload,
    headers={"Content-Type": "application/json"},
)
print(urllib.request.urlopen(request, timeout=35).read().decode())
'
```

See `ai-triage/README.md` for more details.

### Phase 1 Limitations & Future Work

- **Current Limitations**: AI cannot automatically close tickets, resolve incidents, or route native GLPI fields. WAHA polling still reads one `lastMessage` per chat, so webhook/history ingestion is the next reliability milestone for burst traffic.
- **Future Phase 2**: Implementation of vector databases / RAG to provide knowledge-base answers to known issues.
