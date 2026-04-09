from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.dashboard import DashboardOut, PnlSummary
from app.common.models.position import Position, PositionState
from app.common.models.watchlist import WatchlistSymbol, SymbolState
from app.common.models.ledger import LedgerAccount
from app.common.runtime_state import runtime_state

router = APIRouter()


@router.get("", response_model=DashboardOut)
async def get_dashboard(db: AsyncSession = Depends(get_db_session)):
    state = await runtime_state.get_state()

    open_q = await db.execute(
        select(func.count()).select_from(Position).where(Position.state == PositionState.OPEN)
    )
    total_open = open_q.scalar() or 0

    active_q = await db.execute(
        select(func.count()).select_from(WatchlistSymbol).where(WatchlistSymbol.state == SymbolState.ACTIVE)
    )
    active_count = active_q.scalar() or 0

    managed_q = await db.execute(
        select(func.count()).select_from(WatchlistSymbol).where(WatchlistSymbol.state == SymbolState.MANAGED)
    )
    managed_count = managed_q.scalar() or 0

    ledger_q = await db.execute(select(LedgerAccount))
    accounts = ledger_q.scalars().all()

    pnl_summaries = []
    for asset_class in ("crypto", "stock"):
        account = next((a for a in accounts if a.asset_class == asset_class), None)

        open_pos_q = await db.execute(
            select(func.count()).select_from(Position).where(
                Position.asset_class == asset_class,
                Position.state == PositionState.OPEN,
            )
        )
        open_count = open_pos_q.scalar() or 0

        pnl_summaries.append(PnlSummary(
            asset_class=asset_class,
            realized_pnl=account.realized_pnl if account else 0.0,
            unrealized_pnl=account.unrealized_pnl if account else 0.0,
            cash_balance=account.cash_balance if account else 0.0,
            fees_total=account.fees_total if account else 0.0,
            open_positions=open_count,
        ))

    return DashboardOut(
        system_status=state.get("status", "unknown"),
        trading_enabled=state.get("trading_enabled", True),
        crypto_trading_enabled=state.get("crypto_trading_enabled", True),
        stock_trading_enabled=state.get("stock_trading_enabled", True),
        crypto_monitor=state.get("crypto_monitor", "unknown"),
        stock_monitor=state.get("stock_monitor", "unknown"),
        crypto_exit_worker=state.get("crypto_exit_worker", "unknown"),
        stock_exit_worker=state.get("stock_exit_worker", "unknown"),
        discord_listener=state.get("discord_listener", "unknown"),
        last_heartbeat=state.get("last_heartbeat"),
        pnl=pnl_summaries,
        total_open_positions=total_open,
        active_watchlist_count=active_count,
        managed_watchlist_count=managed_count,
    )
