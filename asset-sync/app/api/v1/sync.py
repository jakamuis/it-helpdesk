from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.asset import AssetSyncRequest, AssetSyncResponse
from app.core.database import get_db
from app.core.security import get_api_key
from app.services.glpi_client import GLPIClient
from app.repository.audit import AuditRepository
from app.services.sync_service import SyncService

router = APIRouter()

def get_sync_service(db: AsyncSession = Depends(get_db)):
    glpi_client = GLPIClient()
    audit_repo = AuditRepository(db)
    return SyncService(glpi_client, audit_repo)

@router.post("/sync", response_model=AssetSyncResponse, dependencies=[Depends(get_api_key)])
async def sync_asset(
    request: AssetSyncRequest, 
    service: SyncService = Depends(get_sync_service)
):
    # This endpoint is intentionally read-only. Approved batch writes use the
    # manifest-gated path in SyncService.run_batch_sync instead.
    response = await service.process_sync(request, dry_run=True)
    
    if response.status == "blocked":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=response.message)

    if response.status == "error":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=response.message)
        
    return response
