from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.sync import get_sync_service
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.schemas.asset import AssetSyncResponse


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_check_uses_canonical_path_and_app_version():
    database = MagicMock()
    database.execute = AsyncMock()

    async def override_db():
        yield database

    app.dependency_overrides[get_db] = override_db

    with patch("app.api.health.GLPIClient") as client_class:
        client_class.return_value._init_session = AsyncMock()
        client_class.return_value.kill_session = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == app.version
    assert body["sync_enabled"] is settings.SYNC_ENABLED
    assert body["sync_dry_run"] is settings.SYNC_DRY_RUN
    assert body["sync_asset_types"] == list(settings.SYNC_ASSET_TYPES)
    assert body["sync_datasheet_scope_selector"] == "electronics_cpu_laptop_v1"
    assert body["sync_finance_enabled"] is settings.SYNC_FINANCE_ENABLED
    assert body["sync_allow_create"] is settings.SYNC_ALLOW_CREATE
    assert body["sync_allow_infocom_create"] is settings.SYNC_ALLOW_INFOCOM_CREATE
    assert body["sync_allow_infocom_update"] is settings.SYNC_ALLOW_INFOCOM_UPDATE
    assert body["sync_max_glpi_mutations_per_run"] == settings.SYNC_MAX_GLPI_MUTATIONS_PER_RUN


@pytest.mark.asyncio
async def test_sync_unauthorized():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/sync",
            json={"qrcode": "TEST-001", "asset_type": "Computer"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service_response", "expected_status", "expected_id"),
    [
        (
            AssetSyncResponse(status="would_create", dry_run=True, message="Dry-run only"),
            "would_create",
            None,
        ),
        (
            AssetSyncResponse(status="would_update", glpi_id=200, dry_run=True),
            "would_update",
            200,
        ),
    ],
)
async def test_sync_returns_service_result(service_response, expected_status, expected_id):
    service = MagicMock()
    service.process_sync = AsyncMock(return_value=service_response)
    app.dependency_overrides[get_sync_service] = lambda: service

    payload = {
        "qrcode": "TEST-001",
        "name": "Test Laptop",
        "asset_type": "Computer",
    }
    headers = {"X-API-KEY": settings.API_KEY}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/sync", json=payload, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == expected_status
    assert body["glpi_id"] == expected_id
    called_request = service.process_sync.await_args.args[0]
    assert called_request.qrcode == "TEST-001"
    assert service.process_sync.await_args.kwargs == {"dry_run": True}


@pytest.mark.asyncio
async def test_sync_rejects_unsupported_asset_type():
    headers = {"X-API-KEY": settings.API_KEY}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/sync",
            json={"qrcode": "TEST-001", "asset_type": "Printer"},
            headers=headers,
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_sync_returns_conflict_when_write_is_blocked():
    service = MagicMock()
    service.process_sync = AsyncMock(
        return_value=AssetSyncResponse(status="blocked", message="Write gate is closed")
    )
    app.dependency_overrides[get_sync_service] = lambda: service

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/sync",
            json={"qrcode": "TEST-001", "asset_type": "Computer"},
            headers={"X-API-KEY": settings.API_KEY},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Write gate is closed"
