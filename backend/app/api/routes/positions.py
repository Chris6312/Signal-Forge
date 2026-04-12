from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_db_session
from app.api.schemas.position import PositionOut
from app.api.schemas.position_inspect import PositionInspectOut
from app.api.schemas.order import OrderOut
from app.common.models.position import Position, PositionState
from app.common.models.order import Order
from sqlalchemy.orm import selectinload
from app.services.watchlist_service import build_position_inspect_payload
from app.common.position_time import compute_position_hold_metrics

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
    positions = result.scalars().all()
    return [
        {
            **{
                "id": getattr(pos, "id", None),
                "symbol": getattr(pos, "symbol", None),
                "asset_class": getattr(pos, "asset_class", None),
                "state": getattr(pos, "state", None),
                "entry_price": getattr(pos, "entry_price", None),
                "current_price": getattr(pos, "current_price", None),
                "quantity": getattr(pos, "quantity", None),
                "entry_time": getattr(pos, "entry_time", None),
                "entry_strategy": getattr(pos, "entry_strategy", None),
                "exit_strategy": getattr(pos, "exit_strategy", None),
                "initial_stop": getattr(pos, "initial_stop", None),
                "current_stop": getattr(pos, "current_stop", None),
                "profit_target_1": getattr(pos, "profit_target_1", None),
                "profit_target_2": getattr(pos, "profit_target_2", None),
                "regime_at_entry": getattr(pos, "regime_at_entry", None),
                "watchlist_source_id": getattr(pos, "watchlist_source_id", None),
                "management_policy_version": getattr(pos, "management_policy_version", None),
                "frozen_policy": getattr(pos, "frozen_policy", None),
                "milestone_state": getattr(pos, "milestone_state", None),
                "exit_price": getattr(pos, "exit_price", None),
                "exit_time": getattr(pos, "exit_time", None),
                "exit_reason": getattr(pos, "exit_reason", None),
                "pnl_realized": getattr(pos, "pnl_realized", None),
                "pnl_unrealized": getattr(pos, "pnl_unrealized", None),
                "fees_paid": getattr(pos, "fees_paid", None),
                "created_at": getattr(pos, "created_at", None),
                "updated_at": getattr(pos, "updated_at", None),
            },
            **compute_position_hold_metrics(pos.entry_time, pos.max_hold_hours).as_dict(),
        }
        for pos in positions
    ]


@router.get("/{position_id}", response_model=PositionInspectOut)
async def get_position(position_id: str, db: AsyncSession = Depends(get_db_session)):
    stmt = select(Position).where(Position.id == UUID(position_id)).options(selectinload(Position.orders))
    result = await db.execute(stmt)
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    return build_position_inspect_payload(pos)


@router.get("/{position_id}/orders", response_model=list[OrderOut])
async def get_position_orders(position_id: str, db: AsyncSession = Depends(get_db_session)):
    stmt = select(Order).where(Order.position_id == UUID(position_id)).order_by(Order.placed_at)
    result = await db.execute(stmt)
    return result.scalars().all()
