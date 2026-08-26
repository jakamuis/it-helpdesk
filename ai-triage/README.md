# AI Triage Service

This service provides a local, FastAPI-based AI triage system for incoming WhatsApp helpdesk tickets. It uses Ollama with a local LLM to classify intent, category, and priority, and to suggest the next questions to ask users.

## Setup

1. Make sure you have Ollama running locally or via Docker.
2. Build the Docker container from the root directory: `docker compose build ai-triage`
3. Bring up the stack: `docker compose up -d ollama ai-triage`
4. Pull the model: `docker compose exec ollama ollama pull qwen3:0.6b`

## Endpoints

- `GET /health` : Service health status and Ollama connectivity.
- `POST /api/v1/triage` : Main triage endpoint. Takes user message and conversation state, returns structured classification.

## Security & Rules

- Sensitive data (passwords, OTPs, API keys) are redacted *before* hitting the LLM.
- Critical phrases (e.g. "pabrik mati", "ransomware") bypass the LLM and trigger immediate human escalation via a deterministic rules engine.
- The default hybrid mode handles explicit common issues with inspectable local routes. Ambiguous messages go to Ollama, which may return only one allowlisted route code; application code expands that code into the strict response schema and merges it with prior conversation state.
- Model-only compact routes use a conservative confidence below the default review threshold, so uncertain classifications stay advisory and require a person.
- Short answers to the most recent clarification question are attached to durable conversation state without another model call, preventing avoidable latency and category drift.
- User-facing questions come only from server-owned Indonesian templates; model-generated prose is never forwarded.

Optional Ollama generation settings are available through `OLLAMA_THINK` (default `false`),
`OLLAMA_NUM_PREDICT` (default `256`), `OLLAMA_COMPACT_MODE` (default `true`), and
`OLLAMA_TIMEOUT_SECONDS` (default `25`). Compact mode caps classifier output at eight
tokens so it remains usable on this CPU-only local stack. Set `OLLAMA_COMPACT_MODE=false`
only when using a model/host that can reliably return the full JSON schema within the timeout.
The calling middleware timeout must remain longer than the Ollama timeout.

The API is intentionally not published to a host port. From the repository root, inspect it with:

```bash
docker compose exec -T ai-triage python -c \
  'import json,urllib.request; print(json.load(urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=3)))'
```

## Development Server Deployment

The Development Server uses Apache GLPI, Docker WAHA, and a host systemd middleware. Do not run the repository root Compose stack there. Deploy this service with the dedicated [`compose.server.yml`](compose.server.yml) file instead.

The server Compose project:

- runs Ollama only on its private Docker network;
- binds AI Triage only to `127.0.0.1:18000`;
- persists the model and audit database in named volumes;
- limits CPU and memory usage to protect GLPI and WAHA;
- runs AI Triage read-only as a non-root user;
- reports the container healthy only when Ollama is reachable and `qwen3:0.6b` is installed.

Example release workflow from an immutable server release directory:

```bash
export AI_TRIAGE_IMAGE_TAG=<git-commit>
docker compose -p it-helpdesk-ai -f compose.server.yml config --quiet
docker compose -p it-helpdesk-ai -f compose.server.yml up -d ollama
docker compose -p it-helpdesk-ai -f compose.server.yml exec -T ollama ollama pull qwen3:0.6b
docker compose -p it-helpdesk-ai -f compose.server.yml up -d --build ai-triage
```

Before enabling middleware, verify that `/health` returns both `ollama_reachable=true` and `model_available=true`, then run deterministic and model-backed triage requests directly against `http://127.0.0.1:18000`. Only after those checks pass should the server middleware use:

```ini
AI_TRIAGE_ENABLED=true
AI_TRIAGE_URL=http://127.0.0.1:18000
AI_TRIAGE_TIMEOUT_SECONDS=30
```

Keep `/home/glpiusr/wa-glpi/.env` at mode `600`. The immediate rollback is to set `AI_TRIAGE_ENABLED=false` and restart `wa-glpi.service`; do not delete the persistent Docker volumes.

## Testing

Run tests locally:
```bash
pip install -r requirements-dev.txt
python -m pytest -p no:cacheprovider -q tests
```
