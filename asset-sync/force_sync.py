import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from app.services.sync_service import SyncService
from app.services.glpi_client import GLPIClient
from app.repository.audit import AuditRepository
from app.core.database import AsyncSessionLocal, init_db

async def main():
    print("Initializing database...")
    await init_db()
    
    print("Setting up GLPI client...")
    glpi = GLPIClient()
    # Force localhost for local execution
    glpi.base_url = glpi.base_url.replace("host.docker.internal", "localhost")
    
    async with AsyncSessionLocal() as session:
        audit = AuditRepository(session)
        svc = SyncService(glpi, audit)
        
        print("Triggering batch sync...")
        await svc.run_batch_sync()
        
    print("Force sync completed!")
    
if __name__ == "__main__":
    asyncio.run(main())
