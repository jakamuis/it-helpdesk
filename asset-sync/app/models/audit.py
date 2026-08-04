from sqlalchemy import Column, Integer, String, DateTime, Float, Text
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()

class SyncHistory(Base):
    __tablename__ = "sync_history"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    qrcode = Column(String, index=True, nullable=False)
    action = Column(String, nullable=False) # CREATE, UPDATE, FAILED, DUPLICATE_PREVENTED
    status = Column(String, nullable=False) # SUCCESS, ERROR
    duration = Column(Float, nullable=False) # Duration in seconds
    glpi_id = Column(Integer, nullable=True)
    request_payload = Column(Text, nullable=True) # JSON string
    response_payload = Column(Text, nullable=True) # JSON string
    error = Column(Text, nullable=True)
