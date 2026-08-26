import httpx
from fastapi import FastAPI, HTTPException

from .config import settings
from .schemas import TriageRequest, TriageResponse
from .triage_service import process_triage

app = FastAPI(title="AI Triage Service")

@app.get("/health")
async def health_check():
    ollama_reachable = False
    model_available = False
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0)
            if res.status_code == 200:
                ollama_reachable = True
                data = res.json()
                models = data.get("models", []) if isinstance(data, dict) else []
                model_available = any(
                    isinstance(model, dict)
                    and model.get("name") == settings.ollama_model
                    for model in models
                )
    except (httpx.HTTPError, ValueError, TypeError):
        ollama_reachable = False

    return {
        "status": "ok",
        "service": "ai-triage",
        "ollama_reachable": ollama_reachable,
        "model_available": model_available,
        "model": settings.ollama_model,
        "fallback_ready": True,
    }

@app.post("/api/v1/triage", response_model=TriageResponse)
async def triage_endpoint(request: TriageRequest):
    try:
        response = await process_triage(request)
        return response
    except Exception as exc:
        print(f"Error processing triage: {type(exc).__name__}")
        raise HTTPException(status_code=500, detail="Internal server error") from exc
