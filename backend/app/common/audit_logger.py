import uuid
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.models.audit import AuditEvent, AuditSource

logger = logging.getLogger(__name__)


async def log_event(
    db: AsyncSession,
    event_type: str,
    message: str = "",
    asset_class: str | None = None,
    symbol: str | None = None,
    position_id: str | None = None,
    source: AuditSource = AuditSource.SYSTEM,
    event_data: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        id=uuid.uuid4(),
        event_type=event_type,
        asset_class=asset_class,
        symbol=symbol,
        position_id=uuid.UUID(position_id) if position_id else None,
        source=source,
        event_data=event_data or {},
        message=message,
        created_at=datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None),
    )
    db.add(event)
    await db.flush()
    logger.info("[AUDIT] %s | %s | %s", event_type, symbol or "", message)
    return event
