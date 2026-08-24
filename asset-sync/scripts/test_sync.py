"""Quarantined manual sync bypass; production sync requires manifest approval."""

import sys


POLICY_MESSAGE = (
    "BLOCKED: the manual sync bypass is retired; use the authoritative "
    "Datasheet manifest workflow."
)
POLICY_EXIT_CODE = 78


def main() -> int:
    """Refuse the bypass before loading database or GLPI dependencies."""
    print(POLICY_MESSAGE, file=sys.stderr)
    return POLICY_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())


# Historical implementation below. Keep it unreachable and non-dispatchable.
import asyncio
from loguru import logger
from app.core.database import init_db, AsyncSessionLocal
from app.services.glpi_client import GLPIClient
from app.repository.audit import AuditRepository
from app.services.sync_service import SyncService

async def _historical_manual_sync_bypass_disabled():
    raise RuntimeError(POLICY_MESSAGE)

    logger.info("Starting manual batch sync test...")
    await init_db()
    
    async with AsyncSessionLocal() as db:
        glpi = GLPIClient()
        audit_repo = AuditRepository(db)
        service = SyncService(glpi, audit_repo)
        
        await service.run_batch_sync()
        
    logger.info("Manual batch sync test completed!")
