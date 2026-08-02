---
name: glpi-waha-local-setup
description: >
  Knowledge base for the local GLPI + WAHA + Middleware development environment on this MacBook.
  Covers architecture validation, Docker container setup, token configuration, middleware behavior,
  known issues, and compatibility rules with the Development Server (192.168.1.189).
  Trigger this skill whenever working on GLPI, WAHA, wa-glpi middleware, or sync service tasks.
---

# GLPI & WAHA Local Development Environment

## Architecture Validation (vs Diagram)

### ✅ What is Correctly Implemented
| Diagram Element | Actual Implementation | Status |
| :--- | :--- | :--- |
| GLPI at localhost:8080 | `glpi_app` container (elestio/glpi:latest) | ✅ Running |
| MariaDB 10.11, 447 tables | `glpi_db` container (mariadb:10.11) | ✅ Running |
| WAHA at localhost:3001 | `waha_local` container (devlikeapro/waha:latest) | ✅ Running |
| Middleware: wa-glpi/app.py | Python script, runs via `python wa-glpi/app.py` | ✅ Active |
| Volumes: glpi-data, waha-data | `glpi_glpi_data`, `glpi_glpi_db_data`, `./waha-data` | ✅ Mounted |
| Google Sheets Client | `sheets_client.py` + `main.py` | ✅ Exists (config needed) |
| AppSheet Client | `appsheet_client.py` + `main.py` | ✅ Exists (config needed) |
| No CCTV port conflicts | GLPI:8080, WAHA:3001 vs CCTV:80/5173/8000/5432 | ✅ Safe |

### ⚠️ Discrepancies Between Diagram and Current Code
| Diagram Shows | Actual Reality | Impact |
| :--- | :--- | :--- |
| "Webhook Listener" in middleware | Middleware **polls** WAHA API every 5 seconds (`time.sleep(5)`) — NOT webhook-based | Cosmetic only; works fine |
| Modular services: Ticket Service, WhatsApp Service, Notification Service | All logic is in **one file**: `wa-glpi/app.py` | Cosmetic only; works fine |
| Middleware as a Docker container | Middleware runs **directly** with `python wa-glpi/app.py` — NOT containerized | Cosmetic only; works fine |
| Cron/Systemd timer for sync | **Not yet configured locally** — sync runs manually on demand | Run manually when needed |

> The diagram represents a **target/future architecture**. Current implementation is simpler and working.

---

## Local Tokens (Laptop Only — Different from Server)

> ⚠️ These tokens are ONLY for the local GLPI instance (localhost:8080).
> The Development Server uses different tokens stored in `/home/glpiusr/wa-glpi/app.py`.

```
GLPI_URL       = http://localhost:8080/apirest.php
GLPI_APP_TOKEN = J9IMyiiYAOVBc8GNCiZrwKT4e67SRpA1iDuPnbKj
GLPI_USER_TOKEN= Revolus1!234
WAHA_URL       = http://localhost:3001
WAHA_API_KEY   = helpdesk123
```

---

## Container Reference

| Container | Image | Host Port | Network |
| :--- | :--- | :--- | :--- |
| `glpi_app` | `elestio/glpi:latest` (platform: linux/amd64) | `8080→80` | `glpi_default` |
| `glpi_db` | `mariadb:10.11` | Internal `3306` only | `glpi_default` |
| `waha_local` | `devlikeapro/waha:latest` (platform: linux/amd64) | `3001→3000` | `glpi_default` |

Both GLPI and WAHA require `platform: linux/amd64` in `docker-compose.yml` because
the images do not support `linux/arm64/v8` (Apple Silicon). OrbStack handles Rosetta translation.

---

## How to Run

### Start all containers
```bash
docker compose up -d
```

### Run WAHA ↔ GLPI Middleware
```bash
source venv/bin/activate
python wa-glpi/app.py
```

### Run GLPI → Sheets / AppSheet Sync
```bash
source venv/bin/activate
python main.py --dry-run
```

### Re-sync database from server
```bash
./sync_from_server.sh
```

---

## Known Issues & Fixes Applied

### 1. `'str' object has no attribute 'get'`
**Cause**: WAHA API or GLPI API returns a string/error instead of a dict.
**Fix applied in `wa-glpi/app.py`**:
- Added `isinstance(chats, list)` check before iterating.
- Added `isinstance(chat, dict)` and `isinstance(last_message, dict)` guards.
- Added `isinstance(followup, dict)` guard in `check_followups()`.
- Wrapped `get_glpi_session()` in try/except with readable error output.

### 2. `ERROR_WRONG_APP_TOKEN_PARAMETER`
**Cause**: GLPI 10+ encrypts API tokens in the database using a unique `glpi_crypto.key`.
Tokens from the server cannot be reused locally — they are tied to the server's encryption key.
**Fix**: Generate a fresh App-Token and User-Token from the local GLPI web UI (localhost:8080).

### 3. WAHA image not found for arm64
**Cause**: `devlikeapro/waha:latest` and `elestio/glpi:latest` do not publish `linux/arm64` images.
**Fix**: Add `platform: linux/amd64` to each service in `docker-compose.yml`.

---

## Compatibility Rules

1. `wa-glpi/` structure must remain identical to `/home/glpiusr/wa-glpi/` on the server.
2. Do NOT move or rename `wa-glpi/app.py`.
3. Local tokens differ from server tokens — never mix them.
4. Do NOT make massive refactors — the server is the source of truth layout.
5. New placeholder folders (`integrations/`, `tests/`, `scripts/`, `docs/`) are additive only.

---

## Server Reference (192.168.1.189)

- **GLPI**: Installed at `/var/www/glpi/` (Apache + PHP)
- **GLPI DB config**: `/var/www/glpi/config/config_db.php` (user: `glpiuser`, db: `glpidb`)
- **WAHA**: Docker container, port `3000`, Up for 2+ months
- **Middleware**: `/home/glpiusr/wa-glpi/app.py` (runs as a process)
- **Server tokens** (do NOT use locally):
  - `APP_TOKEN = YvnoAQqlpuDjAh6xplsZgLEtIfxHJfJWCtEIQq5S`
  - `USER_TOKEN = 502r4RHv89ZMj56ULaNMpJMSKHzxDPEQmpPWLNwM`
