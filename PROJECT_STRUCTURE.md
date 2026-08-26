# PROJECT STRUCTURE
# GLPI & WAHA Integration Stack

> **Note**: This laptop is a local mirror of the Development Server (`192.168.1.189`).
> The server layout is the source of truth. Do not restructure files in ways that break
> compatibility with the server.

---

## Current Structure

```
GLPI/
│
├── 📄 main.py                  # CLI entry point: syncs GLPI → Google Sheets / AppSheet
├── 📄 glpi_client.py           # GLPI REST API client (initSession, fetch, killSession)
├── 📄 sheets_client.py         # Google Sheets API v4 client (Service Account)
├── 📄 appsheet_client.py       # AppSheet Inbound REST API client (Add/Edit/Upsert)
│
├── 📄 docker-compose.yml       # Defines local GLPI, WAHA, Ollama, AI, and middleware containers
├── 📄 requirements.txt         # Python dependencies for the sync service
├── 📄 .env                     # Active local environment config (DO NOT COMMIT)
├── 📄 .env.example             # Template for environment variables
│
├── 📄 sync_from_server.sh      # One-shot script: pulls DB dump from server → imports locally
├── 📄 glpi_remote_dump.sql     # Latest DB snapshot pulled from server (DO NOT COMMIT)
│
├── 📄 README.md                # Setup and usage guide (original)
├── 📄 SETUP_SUMMARY.md         # Local environment summary & reference (this laptop)
├── 📄 PROJECT_STRUCTURE.md     # This file
│
├── 📁 wa-glpi/                 # WhatsApp ↔ GLPI Middleware Bridge (mirrors server)
│   ├── 📄 app.py               # Main loop: listens for WA messages → creates GLPI tickets
│   ├── 📄 ai_client.py         # Internal client for the AI triage sidecar
│   ├── 📄 state_manager.py     # SQLite conversation state, dedupe, and retry state
│   ├── 📄 poller.py            # (Placeholder) future polling extension
│   ├── 📄 ticket_mapping.json  # Maps GLPI Ticket IDs to WhatsApp chat IDs
│   ├── 📄 last_followup.txt    # Tracks last synced followup ID
│   ├── 📄 .env                 # wa-glpi specific env (currently unused, config in app.py)
│   ├── 📄 requirements.txt     # (Placeholder) wa-glpi specific deps
│   ├── 📁 logs/                # Runtime log files
│   ├── 📁 mappings/            # Additional mapping storage (future)
│   ├── 📁 sessions/            # WhatsApp session storage (legacy/openwa)
│   ├── 📁 openwa/              # Legacy openwa artifacts
│   ├── 📁 systemd/             # Systemd service unit files (for server deployment)
│   └── 📁 venv/                # wa-glpi Python virtual environment
│
├── 📁 ai-triage/               # Local advisory triage API (FastAPI + Ollama)
│   ├── 📁 app/                 # Strict schemas, rules, redaction, templates, audit
│   ├── 📁 tests/               # AI contract and failure-mode tests
│   ├── 📄 Dockerfile
│   └── 📄 requirements.txt
│
├── 📁 waha-data/               # Persistent WAHA session data (mounted into Docker)
│   └── 📁 webjs/               # WhatsApp Web JS session files
│
├── 📁 venv/                    # Main project Python virtual environment
│
│── FUTURE PLACEHOLDERS (empty, additive only) ─────────────────────────────────────────
│
├── 📁 integrations/            # Future: additional modular integration clients
│   ├── 📁 appsheet/            # Future: dedicated AppSheet integration module
│
├── 📁 tests/                   # Future: unit and integration tests
├── 📁 scripts/                 # Future: helper and automation scripts
└── 📁 docs/                    # Future: extended documentation, diagrams, API references
```

---

## Active Services Summary

| Service | Container | URL | Status |
| :--- | :--- | :--- | :--- |
| GLPI Web | `glpi_app` | [http://localhost:8080](http://localhost:8080) | ✅ Running |
| GLPI DB | `glpi_db` | Internal port 3306 | ✅ Running |
| WAHA | `waha_local` | [http://localhost:3001](http://localhost:3001) | ✅ Running |
| Ollama | `ollama` | Internal port `11434` | ✅ Local AI runtime |
| AI Triage | `ai_triage` | Internal port `8000` | ✅ Advisory API |
| WAHA ↔ GLPI Middleware | `wa_glpi` | Internal only | ✅ Feature-flagged |

---

## Current Working Features

| Feature | Location | Status |
| :--- | :--- | :--- |
| WhatsApp → GLPI Ticket | `wa-glpi/app.py` | ✅ Active |
| GLPI Followup → WhatsApp | `wa-glpi/app.py` | ✅ Active |
| AI-assisted ticket triage | `ai-triage/` + `wa-glpi/ai_client.py` | 🛡️ Default off |
| GLPI → Google Sheets Sync | `main.py` + `sheets_client.py` | ⚙️ Config needed |
| GLPI → AppSheet Sync | `main.py` + `appsheet_client.py` | ⚙️ Config needed |

---

## Future Expansion Areas

### `integrations/appsheet/`
Planned dedicated module to replace the current `appsheet_client.py` with a more
structured integration layer, including retry logic, batch processing, and schema mapping.

### `tests/`
Unit tests and integration tests for:
- GLPI REST API client behavior.
- Middleware message parsing logic.
- Sheets / AppSheet write operations.

### `scripts/`
Helper scripts for:
- Database backup automation.
- Server ↔ Local environment sync (`sync_from_server.sh` can be moved here later).
- Docker container health checks.

### `docs/`
Extended documentation:
- API authentication flow diagrams.
- GLPI + WAHA architecture overview.
- Deployment guide for the server.

---

## Compatibility Notes

> [!IMPORTANT]
> This laptop is a **local mirror** of the Development Server (`192.168.1.189`).
> - `wa-glpi/` structure must remain identical to `/home/glpiusr/wa-glpi/` on the server.
> - Do **not** move `wa-glpi/app.py` or rename its key functions.
> - New features should be developed here locally and then manually deployed to the server.
