from fastapi import APIRouter, Depends, Query, HTTPException
from starlette import status
import logging
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
    logger = logging.getLogger(__name__)
    try:
        stmt = (
            select(Position)
            .where(Position.state == PositionState.CLOSED)
            .order_by(desc(Position.exit_time))
            .limit(limit)
        )
        if asset_class:
            stmt = stmt.where(Position.asset_class == asset_class)
        result = await db.execute(stmt)
        positions = result.scalars().all()

        # Explicitly map to plain dicts to ensure the API always exposes the
        # fields the frontend expects (including newly added trade fields).
        out = []
        for p in positions:
            try:
                out.append({
                    "id": p.id,
                    "symbol": p.symbol,
                    "asset_class": p.asset_class,
                    "state": p.state.value if hasattr(p.state, 'value') else p.state,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "quantity": p.quantity,
                    "entry_time": p.entry_time,
                    "entry_strategy": p.entry_strategy,
                    "exit_strategy": p.exit_strategy,
                    "initial_stop": p.initial_stop,
                    "current_stop": p.current_stop,
                    "profit_target_1": p.profit_target_1,
                    "profit_target_2": p.profit_target_2,
                    "max_hold_hours": p.max_hold_hours,
                    "regime_at_entry": p.regime_at_entry,
                    "watchlist_source_id": p.watchlist_source_id,
                    "management_policy_version": p.management_policy_version,
                    "frozen_policy": p.frozen_policy,
                    "milestone_state": p.milestone_state,
                    "exit_price": p.exit_price,
                    "exit_time": p.exit_time,
                    "exit_reason": p.exit_reason,
                    "pnl_realized": p.pnl_realized,
                    "pnl_unrealized": p.pnl_unrealized,
                    "fees_paid": p.fees_paid,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at,
                })
            except Exception:
                # If an individual position can't be serialized, log and continue
                logger.exception("Failed to serialize position %s", getattr(p, 'id', '<unknown>'))
        return out
    except Exception as exc:
        logging.getLogger(__name__).exception("Error fetching trade history: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch trade history")


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
