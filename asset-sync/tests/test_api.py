import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.config import settings
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data

@pytest.mark.asyncio
async def test_sync_unauthorized():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/sync", json={"qrcode": "123"})
    assert response.status_code == 401

@pytest.mark.asyncio
@patch('app.services.glpi_client.GLPIClient.search_asset', new_callable=AsyncMock)
@patch('app.services.glpi_client.GLPIClient.create_asset', new_callable=AsyncMock)
@patch('app.repository.audit.AuditRepository.log_sync', new_callable=AsyncMock)
async def test_sync_create_success(mock_log, mock_create, mock_search):
    # Mock search to return None (not found -> create)
    mock_search.return_value = None
    # Mock create to return a new ID
    mock_create.return_value = 100

    payload = {
        "qrcode": "TEST-001",
        "name": "Test Laptop"
    }
    
    headers = {"X-API-KEY": settings.API_KEY}
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/sync", json=payload, headers=headers)
        
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"
    assert data["glpi_id"] == 100
    mock_search.assert_called_once_with("TEST-001")
    mock_create.assert_called_once()
    mock_log.assert_called_once()

@pytest.mark.asyncio
@patch('app.services.glpi_client.GLPIClient.search_asset', new_callable=AsyncMock)
@patch('app.services.glpi_client.GLPIClient.update_asset', new_callable=AsyncMock)
@patch('app.repository.audit.AuditRepository.log_sync', new_callable=AsyncMock)
async def test_sync_update_success(mock_log, mock_update, mock_search):
    # Mock search to return existing asset
    mock_search.return_value = {"id": 200}
    mock_update.return_value = True

    payload = {
        "qrcode": "TEST-002",
        "name": "Updated Laptop"
    }
    
    headers = {"X-API-KEY": settings.API_KEY}
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/v1/sync", json=payload, headers=headers)
        
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "updated"
    assert data["glpi_id"] == 200
    mock_search.assert_called_once_with("TEST-002")
    mock_update.assert_called_once()
    mock_log.assert_called_once()
