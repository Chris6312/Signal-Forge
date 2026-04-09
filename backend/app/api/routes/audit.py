from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.audit import AuditEventOut
from app.common.models.audit import AuditEvent

router = APIRouter()


@router.get("", response_model=list[AuditEventOut])
async def get_audit_events(
    event_type: str | None = Query(None),
    symbol: str | None = Query(None),
    asset_class: str | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(limit)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if symbol:
        stmt = stmt.where(AuditEvent.symbol == symbol.upper())
    if asset_class:
        stmt = stmt.where(AuditEvent.asset_class == asset_class)
    if source:
        stmt = stmt.where(AuditEvent.source == source)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/event-types")
async def get_event_types(db: AsyncSession = Depends(get_db_session)):
    from sqlalchemy import distinct
    stmt = select(distinct(AuditEvent.event_type)).order_by(AuditEvent.event_type)
    result = await db.execute(stmt)
    return {"event_types": [row[0] for row in result.all()]}
