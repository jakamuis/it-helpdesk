from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.config import settings
from app.services.glpi_client import GLPIClient
import time

router = APIRouter()

@router.get("/")
async def health_check(db: AsyncSession = Depends(get_db)):
    status = {
        "status": "ok",
        "version": "1.0.0",
        "database_connectivity": False,
        "glpi_connectivity": False
    }
    
    # Check DB
    try:
        await db.execute(text("SELECT 1"))
        status["database_connectivity"] = True
    except Exception:
        pass
        
    # Check GLPI
    try:
        client = GLPIClient()
        await client._init_session()
        status["glpi_connectivity"] = True
        await client.kill_session()
    except Exception:
        pass
        
    return status
