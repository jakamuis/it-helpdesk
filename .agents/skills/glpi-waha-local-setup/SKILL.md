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
| GLPI at localhost:8080 | `glpi_app` container (`elestio/glpi:latest`) | ✅ Running |
| MariaDB 10.11 | `glpi_db` container (`mariadb:10.11`) | ✅ Running |
| WAHA at localhost:3001 | `waha_local` container (`devlikeapro/waha:latest`) | ✅ Running |
| Middleware | `wa-glpi/app.py` | ✅ Available |
| Volumes | GLPI database/data and WAHA session volumes | ✅ Mounted |
| Google Sheets Client | `sheets_client.py` + `main.py` | ✅ Exists; config required |
| AppSheet Client | `appsheet_client.py` + `main.py` | ✅ Exists; config required |
| No CCTV port conflicts | GLPI:8080, WAHA:3001 | ✅ Safe |

### ⚠️ Discrepancies Between Diagram and Current Code

| Diagram Shows | Actual Reality | Impact |
| :--- | :--- | :--- |
| Webhook Listener | Middleware polls WAHA every 5 seconds | Works, but burst messages remain a limitation |
| Modular middleware services | Main workflow remains in `wa-glpi/app.py` | Preserve for server compatibility |
| Middleware always containerized | Local can use Compose; server uses systemd | Use environment-specific deployment |
| Cron/Systemd timer for sync | Not configured locally | Run manually when needed |

> The diagram represents a target architecture. Preserve the simpler server-compatible layout until a controlled migration is approved.

## Credential Handling

- Local and Development Server credentials are different.
- Store local values only in the ignored root `.env` file.
- Store server middleware values only in `/home/glpiusr/wa-glpi/.env` with mode `600`.
- Never write tokens, passwords, API keys, private keys, or service-account contents into this skill, source files, Compose defaults, documentation, or Git history.
- `.env.example` must contain placeholders only.
- If a credential is found in Git history, sanitize the current tree and rotate the credential at its owning service.

Required local keys include:

```text
GLPI_URL
GLPI_APP_TOKEN
GLPI_USER_TOKEN
WAHA_API_KEY
GLPI_DB_ROOT_PASSWORD
GLPI_DB_PASSWORD
WAHA_DASHBOARD_PASSWORD
WHATSAPP_SWAGGER_PASSWORD
```

## Container Reference

| Container | Image | Host Port | Network |
| :--- | :--- | :--- | :--- |
| `glpi_app` | `elestio/glpi:latest` (`linux/amd64`) | `8080→80` | `glpi_default` |
| `glpi_db` | `mariadb:10.11` | Internal `3306` | `glpi_default` |
| `waha_local` | `devlikeapro/waha:latest` (`linux/amd64`) | `3001→3000` | `glpi_default` |

The GLPI and WAHA images require `platform: linux/amd64` on Apple Silicon. OrbStack handles the translation.

## How to Run Locally

### Start all containers

Populate the ignored `.env` first, then run:

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

Export the password variables required by `sync_from_server.sh`, then run:

```bash
./sync_from_server.sh
```

## Known Issues & Fixes Applied

### 1. `'str' object has no attribute 'get'`

Cause: WAHA or GLPI can return a string/error instead of a dictionary.

Mitigations in `wa-glpi/app.py`:

- Validate list/dictionary response shapes before iteration.
- Validate follow-up objects.
- Handle GLPI session errors without crashing the service.

### 2. `ERROR_WRONG_APP_TOKEN_PARAMETER`

GLPI encrypts API tokens using an instance-specific `glpi_crypto.key`. Server tokens cannot be reused locally. Generate separate tokens in each GLPI instance.

### 3. WAHA image unavailable for arm64

Use `platform: linux/amd64` for the local GLPI and WAHA services on Apple Silicon.

## Compatibility Rules

1. Keep `wa-glpi/` compatible with `/home/glpiusr/wa-glpi/` on the server.
2. Do not move or rename `wa-glpi/app.py`.
3. Never mix local and server credentials.
4. Avoid large server-layout refactors; prefer additive modules.
5. New folders such as `integrations/`, `tests/`, `scripts/`, and `docs/` must remain additive.
6. Do not run the root laptop Compose stack wholesale on the Development Server.
7. Back up and preserve server `.env`, ticket mapping, follow-up cursor, and SQLite state before deployment.

## Development Server Reference

- Host: `192.168.1.189`
- GLPI: Apache/PHP under `/var/www/glpi/`
- GLPI database configuration: `/var/www/glpi/config/config_db.php`
- WAHA: Docker container on host port `3000`
- Middleware: systemd service using `/home/glpiusr/wa-glpi/app.py`
- Middleware environment: `/home/glpiusr/wa-glpi/.env` (mode `600`)
- AI runtime: deploy as a separate Compose project; expose the API to loopback only and keep Ollama internal

Server secrets must be read from the server environment at runtime and must never be copied into the repository.
