from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.database import get_db
from app.core.config import DATASHEET_SCOPE_SELECTOR, settings
from app.services.glpi_client import GLPIClient
from app.version import __version__

router = APIRouter()

@router.get("")
async def health_check(db: AsyncSession = Depends(get_db)):
    status = {
        "status": "ok",
        "version": __version__,
        "database_connectivity": False,
        "glpi_connectivity": False,
        "sync_enabled": settings.SYNC_ENABLED,
        "sync_dry_run": settings.SYNC_DRY_RUN,
        "sync_asset_types": list(settings.SYNC_ASSET_TYPES),
        "sync_datasheet_scope_selector": DATASHEET_SCOPE_SELECTOR,
        "sync_finance_enabled": settings.SYNC_FINANCE_ENABLED,
        "sync_allow_create": settings.SYNC_ALLOW_CREATE,
        "sync_allow_infocom_create": settings.SYNC_ALLOW_INFOCOM_CREATE,
        "sync_allow_infocom_update": settings.SYNC_ALLOW_INFOCOM_UPDATE,
        "sync_max_glpi_mutations_per_run": settings.SYNC_MAX_GLPI_MUTATIONS_PER_RUN,
    }
    
    # Check DB
    try:
        await db.execute(text("SELECT 1"))
        status["database_connectivity"] = True
    except Exception:
        pass
        
    # Check GLPI
    client = GLPIClient()
    try:
        await client._init_session()
        status["glpi_connectivity"] = True
    except Exception:
        pass
    finally:
        try:
            await client.kill_session()
        except Exception:
            pass

    if not status["database_connectivity"] or not status["glpi_connectivity"]:
        status["status"] = "degraded"
        
    return status
