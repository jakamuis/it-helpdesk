from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.services.glpi_client import GLPIClient
from app.repository.audit import AuditRepository
from app.services.sync_service import SyncService

scheduler = AsyncIOScheduler(timezone=settings.SYNC_TIMEZONE)

async def scheduled_batch_sync():
    logger.info("Scheduler Triggered: scheduled_batch_sync")

    # We need a new DB session for the background task
    async with AsyncSessionLocal() as db:
        glpi_client = GLPIClient()
        audit_repo = AuditRepository(db)
        service = SyncService(glpi_client, audit_repo)

        await service.run_batch_sync()


def build_sync_trigger() -> CronTrigger:
    return CronTrigger(
        day_of_week=settings.SYNC_DAY_OF_WEEK,
        hour=settings.SYNC_HOUR,
        minute=settings.SYNC_MINUTE,
        timezone=settings.SYNC_TIMEZONE,
    )


def setup_scheduler():
    if not settings.SYNC_ENABLED:
        existing_job = scheduler.get_job("batch_sync_job")
        if existing_job:
            scheduler.remove_job("batch_sync_job")
        logger.warning("Weekly asset sync job not armed because SYNC_ENABLED=false.")
        return scheduler

    existing_job = scheduler.get_job("batch_sync_job")
    if existing_job:
        scheduler.remove_job("batch_sync_job")

    scheduler.add_job(
        scheduled_batch_sync,
        trigger=build_sync_trigger(),
        id="batch_sync_job",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    logger.info(
        "Weekly asset sync scheduled for {} {:02d}:{:02d} ({})",
        settings.SYNC_DAY_OF_WEEK,
        settings.SYNC_HOUR,
        settings.SYNC_MINUTE,
        settings.SYNC_TIMEZONE,
    )
    return scheduler
