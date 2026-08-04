import asyncio
from loguru import logger
from app.core.database import init_db, AsyncSessionLocal
from app.services.glpi_client import GLPIClient
from app.repository.audit import AuditRepository
from app.services.sync_service import SyncService

async def main():
    logger.info("Starting manual batch sync test...")
    await init_db()
    
    async with AsyncSessionLocal() as db:
        glpi = GLPIClient()
        audit_repo = AuditRepository(db)
        service = SyncService(glpi, audit_repo)
        
        await service.run_batch_sync()
        
    logger.info("Manual batch sync test completed!")

if __name__ == "__main__":
    asyncio.run(main())
