from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.position import PositionOut
from app.common.models.position import Position, PositionState

router = APIRouter()


@router.get("", response_model=list[PositionOut])
async def get_trade_history(
    asset_class: str | None = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = (
        select(Position)
        .where(Position.state == PositionState.CLOSED)
        .order_by(desc(Position.exit_time))
        .limit(limit)
    )
    if asset_class:
        stmt = stmt.where(Position.asset_class == asset_class)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/summary")
async def get_trade_summary(
    asset_class: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(Position).where(Position.state == PositionState.CLOSED)
    if asset_class:
        stmt = stmt.where(Position.asset_class == asset_class)
    result = await db.execute(stmt)
    trades = result.scalars().all()

    if not trades:
        return {"total_trades": 0, "winners": 0, "losers": 0, "win_rate": 0.0, "total_pnl": 0.0, "avg_pnl": 0.0}

    winners = [t for t in trades if (t.pnl_realized or 0) > 0]
    losers = [t for t in trades if (t.pnl_realized or 0) <= 0]
    total_pnl = sum(t.pnl_realized or 0 for t in trades)

    return {
        "total_trades": len(trades),
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": round(len(winners) / len(trades) * 100, 1),
        "total_pnl": round(total_pnl, 4),
        "avg_pnl": round(total_pnl / len(trades), 4),
    }
