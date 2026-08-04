from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.audit import SyncHistory
import json

class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log_sync(self, qrcode: str, action: str, status: str, duration: float, 
                       glpi_id: int = None, request_payload: dict = None, 
                       response_payload: dict = None, error: str = None) -> SyncHistory:
        
        record = SyncHistory(
            qrcode=qrcode,
            action=action,
            status=status,
            duration=duration,
            glpi_id=glpi_id,
            request_payload=json.dumps(request_payload) if request_payload else None,
            response_payload=json.dumps(response_payload) if response_payload else None,
            error=error
        )
        
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record
