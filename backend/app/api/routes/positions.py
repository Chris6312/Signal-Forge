from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_db_session
from app.api.schemas.position import PositionOut
from app.api.schemas.order import OrderOut
from app.common.models.position import Position, PositionState
from app.common.models.order import Order
from sqlalchemy.orm import selectinload

router = APIRouter()


@router.get("", response_model=list[PositionOut])
async def get_positions(
    state: str | None = Query(None),
    asset_class: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(Position).order_by(desc(Position.created_at))
    if state:
        stmt = stmt.where(Position.state == state)
    if asset_class:
        stmt = stmt.where(Position.asset_class == asset_class)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/open", response_model=list[PositionOut])
async def get_open_positions(db: AsyncSession = Depends(get_db_session)):
    stmt = select(Position).where(
        Position.state == PositionState.OPEN
    ).order_by(desc(Position.entry_time))
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{position_id}", response_model=PositionOut)
async def get_position(position_id: str, db: AsyncSession = Depends(get_db_session)):
    stmt = select(Position).where(Position.id == UUID(position_id)).options(selectinload(Position.orders))
    result = await db.execute(stmt)
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    return pos


@router.get("/{position_id}/orders", response_model=list[OrderOut])
async def get_position_orders(position_id: str, db: AsyncSession = Depends(get_db_session)):
    stmt = select(Order).where(Order.position_id == UUID(position_id)).order_by(Order.placed_at)
    result = await db.execute(stmt)
    return result.scalars().all()
