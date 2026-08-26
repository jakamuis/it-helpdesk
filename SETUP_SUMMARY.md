# GLPI & WAHA Integration Stack - Setup Summary & Reference Guide

## 📌 Executive Summary

Your local **GLPI** environment, **WAHA (WhatsApp API)** gateway, and **WAHA ↔ GLPI Middleware Bridge** have been fully containerized and configured on your macOS laptop (Apple Silicon compatible). It operates completely isolated from your existing **CCTV** project and other services.

---

## 🛠️ System Components & Architecture

### 1. Local Container Stack (`docker-compose.yml`)
- **GLPI Web Application**: `elestio/glpi:latest`
  - **URL**: [http://localhost:8080](http://localhost:8080)
  - **Database**: MariaDB 10.11 (`glpi_db`), **447 tables** restored from server `192.168.1.189`.
  - **Status**: Running (`Up`)

- **WAHA (WhatsApp HTTP API)**: `devlikeapro/waha:latest`
  - **URL & Dashboard**: [http://localhost:3001/dashboard](http://localhost:3001/dashboard)
  - **API Key and Dashboard Credentials**: configured in the ignored root `.env`
  - **Session Data**: Synced to `./waha-data` from server.
  - **Status**: Running (`Up`)

---

### 2. WAHA ↔ GLPI Middleware Bridge (`wa-glpi/`)

Located at: `wa-glpi/`

- **Main Script**: [`wa-glpi/app.py`](wa-glpi/app.py)
- **Runtime Configuration**:
  - `GLPI_URL`: `http://localhost:8080/apirest.php`
  - `WAHA_URL`: `http://localhost:3001`
  - `GLPI_APP_TOKEN`, `GLPI_USER_TOKEN`, and `WAHA_API_KEY`: configured in the ignored root `.env`
- **Feature Capabilities**:
  - Receives incoming WhatsApp messages from WAHA.
  - Automatically creates new **GLPI Tickets**.
  - Sends official GLPI Ticket ID confirmations back to the WhatsApp user.
  - Monitors GLPI ticket followups and relays agent updates back to WhatsApp.

---

### 3. GLPI to Google Sheets & AppSheet Sync Service
Located at root folder:
- **CLI Script**: [main.py](file:///Users/jaka/Documents/Project/GLPI/main.py)
- **GLPI REST Client**: [glpi_client.py](file:///Users/jaka/Documents/Project/GLPI/glpi_client.py)
- **Google Sheets Client**: [sheets_client.py](file:///Users/jaka/Documents/Project/GLPI/sheets_client.py)
- **AppSheet Client**: [appsheet_client.py](file:///Users/jaka/Documents/Project/GLPI/appsheet_client.py)

---

## 🔒 Safety & Resource Audit (Zero Conflict with CCTV Project)

| Service | Host Port | Container Name | CCTV Conflict? |
| :--- | :--- | :--- | :--- |
| **GLPI Web App** | **`8080`** | `glpi_app` | **None** (CCTV uses `80`, `5173`, `8000`, `1984`) |
| **GLPI Database** | *3306 (Internal)* | `glpi_db` | **None** (CCTV uses PostgreSQL `5432`) |
| **WAHA Gateway** | **`3001`** | `waha_local` | **None** (Mapped to 3001 to prevent port 3000 collision) |

---

## 🚀 How to Run Services

### A. Run WAHA ↔ GLPI Middleware Bridge
```bash
# Activate virtual environment
source venv/bin/activate

# Run middleware
python wa-glpi/app.py
```

### B. Run GLPI ↔ Google Sheets / AppSheet Sync
```bash
source venv/bin/activate
python main.py --dry-run
```

### C. Re-Sync Data from Remote Server (`192.168.1.189`)
If you ever need to re-fetch database dumps or files from the remote server:
```bash
./sync_from_server.sh
```

---

## 📁 Project Structure

| Path | Purpose |
| :--- | :--- |
| `wa-glpi/app.py` | WhatsApp ↔ GLPI middleware bridge (active, mirrors server) |
| `main.py` | GLPI → Sheets / AppSheet sync CLI |
| `docker-compose.yml` | GLPI + MariaDB + WAHA + Ollama + AI triage + middleware containers |
| `sync_from_server.sh` | Pull DB snapshot from server & restore locally |
| `integrations/appsheet/` | *(Placeholder)* Future dedicated AppSheet module |
| `ai-triage/` | Local advisory AI triage API and tests |
| `tests/` | *(Placeholder)* Future unit & integration tests |
| `scripts/` | *(Placeholder)* Future automation & helper scripts |
| `docs/` | *(Placeholder)* Future extended documentation |

> Full details: see [PROJECT_STRUCTURE.md](file:///Users/jaka/Documents/Project/GLPI/PROJECT_STRUCTURE.md)

---

## ⚠️ Compatibility Notes

> This laptop is a **local mirror** of Development Server `192.168.1.189`.
> - `wa-glpi/` must remain identical in structure to `/home/glpiusr/wa-glpi/` on the server.
> - Do **not** move or rename `wa-glpi/app.py` — it breaks server compatibility.
> - Tokens (`GLPI_APP_TOKEN`, `GLPI_USER_TOKEN`) are **local-only** and differ from the server.
> - Server credentials and services are **untouched** by this local setup.
