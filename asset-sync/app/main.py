from fastapi import FastAPI
from fastapi.responses import JSONResponse
from loguru import logger
from app.core.config import settings
from app.api.v1 import sync
from app.api import health
from app.core.database import init_db
from app.core.scheduler import setup_scheduler, scheduler as apscheduler
from app.version import __version__
from contextlib import asynccontextmanager
import sys

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing database...")
    await init_db()
    
    if settings.SYNC_ENABLED:
        logger.info("Starting background scheduler...")
        setup_scheduler()
        apscheduler.start()
    else:
        logger.warning("Weekly asset sync scheduler is disabled (SYNC_ENABLED=false).")
    
    yield
    # Shutdown
    logger.info("Shutting down...")
    if apscheduler.running:
        apscheduler.shutdown()

app = FastAPI(title="Asset Management Sync Service", version=__version__, lifespan=lifespan)

# Configure logger
logger.remove()
logger.add(sys.stdout, level=settings.LOG_LEVEL)

# Include routers
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(sync.router, prefix="/api/v1", tags=["Sync"])

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"},
    )
