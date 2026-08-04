from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.glpi_client import GLPIClient
from app.repository.audit import AuditRepository
from app.services.sync_service import SyncService

scheduler = AsyncIOScheduler()

async def scheduled_batch_sync():
    logger.info("Scheduler Triggered: scheduled_batch_sync")
    
    # We need a new DB session for the background task
    async with AsyncSessionLocal() as db:
        glpi_client = GLPIClient()
        audit_repo = AuditRepository(db)
        service = SyncService(glpi_client, audit_repo)
        
        await service.run_batch_sync()

def setup_scheduler():
    interval = settings.SYNC_INTERVAL_MINUTES
    scheduler.add_job(scheduled_batch_sync, 'interval', minutes=interval, id='batch_sync_job')
    return scheduler
