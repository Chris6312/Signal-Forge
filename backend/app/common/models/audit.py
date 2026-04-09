import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Text, JSON, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID

from app.common.models.base import Base


class AuditSource(str, enum.Enum):
    SYSTEM = "SYSTEM"
    DISCORD = "DISCORD"
    USER = "USER"
    BROKER = "BROKER"
    WORKER = "WORKER"


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(100), nullable=False, index=True)
    asset_class = Column(String(10), nullable=True)
    symbol = Column(String(20), nullable=True, index=True)
    position_id = Column(UUID(as_uuid=True), nullable=True)
    source = Column(SAEnum(AuditSource, native_enum=False), nullable=False, default=AuditSource.SYSTEM)
    event_data = Column(JSON, nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)
