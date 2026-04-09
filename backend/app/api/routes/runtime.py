import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin, get_db_session
from app.api.schemas.runtime import RuntimeStateOut, RuntimeUpdateIn
from app.common.runtime_state import runtime_state
from app.common.market_hours import market_status, is_trading_day

router = APIRouter()


@router.get("", response_model=RuntimeStateOut)
async def get_runtime():
    state = await runtime_state.get_state()
    return RuntimeStateOut(
        status=state.get("status", "unknown"),
        trading_enabled=state.get("trading_enabled", True),
        crypto_trading_enabled=state.get("crypto_trading_enabled", True),
        stock_trading_enabled=state.get("stock_trading_enabled", True),
        trading_mode=state.get("trading_mode", "paper"),
        risk_per_trade_pct=float(state.get("risk_per_trade_pct", 0.02)),
        max_crypto_positions=state.get("max_crypto_positions", 5),
        max_stock_positions=state.get("max_stock_positions", 5),
        crypto_monitor=state.get("crypto_monitor", "unknown"),
        stock_monitor=state.get("stock_monitor", "unknown"),
        crypto_exit_worker=state.get("crypto_exit_worker", "unknown"),
        stock_exit_worker=state.get("stock_exit_worker", "unknown"),
        discord_listener=state.get("discord_listener", "unknown"),
        last_heartbeat=state.get("last_heartbeat"),
        started_at=state.get("started_at"),
    )


@router.patch("", response_model=RuntimeStateOut, dependencies=[Depends(require_admin)])
async def update_runtime(body: RuntimeUpdateIn):
    updates = body.model_dump(exclude_none=True)
    if "trading_mode" in updates and updates["trading_mode"] not in ("paper", "live"):
        raise HTTPException(status_code=400, detail="trading_mode must be 'paper' or 'live'")
    for key, value in updates.items():
        await runtime_state.set_value(key, value)
    return await get_runtime()


@router.post("/halt", dependencies=[Depends(require_admin)])
async def halt_trading():
    await runtime_state.set_value("trading_enabled", False)
    return {"message": "Trading halted"}


@router.post("/resume", dependencies=[Depends(require_admin)])
async def resume_trading():
    await runtime_state.set_value("trading_enabled", True)
    return {"message": "Trading resumed"}


@router.post("/mode", response_model=RuntimeStateOut, dependencies=[Depends(require_admin)])
async def set_trading_mode(mode: str = Query(...)):
    if mode not in ("paper", "live"):
        raise HTTPException(status_code=400, detail="mode must be 'paper' or 'live'")
    await runtime_state.set_value("trading_mode", mode)
    return await get_runtime()


@router.post("/reset", dependencies=[Depends(require_admin)])
async def reset_paper_data(
    initial_crypto_balance: float = Query(default=0.0, ge=0),
    initial_stock_balance: float = Query(default=0.0, ge=0),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Wipe all paper-trading data: positions, orders, ledger entries, and audit
    events. Ledger accounts are reset to zero (or to the supplied seed balances).
    Watchlist entries are preserved.
    """
    from app.common.models.position import Position
    from app.common.models.order import Order
    from app.common.models.ledger import LedgerAccount, LedgerEntry, EntryType
    from app.common.models.audit import AuditEvent
    from app.common.models.watchlist import WatchlistSymbol, SymbolState

    # Delete in FK-safe order
    await db.execute(delete(AuditEvent))
    await db.execute(delete(LedgerEntry))
    await db.execute(delete(Order))
    await db.execute(delete(Position))

    # Release any MANAGED watchlist symbols — their positions no longer exist
    await db.execute(
        update(WatchlistSymbol)
        .where(WatchlistSymbol.state == SymbolState.MANAGED)
        .values(state=SymbolState.INACTIVE, closed_at=datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None))
    )

    now = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)
    for asset_class, seed in [
        ("crypto", initial_crypto_balance),
        ("stock",  initial_stock_balance),
    ]:
        result = await db.execute(
            select(LedgerAccount).where(LedgerAccount.asset_class == asset_class)
        )
        account = result.scalar_one_or_none()
        if account:
            account.cash_balance   = seed
            account.realized_pnl   = 0.0
            account.unrealized_pnl = 0.0
            account.fees_total     = 0.0
            account.updated_at     = now
        else:
            account = LedgerAccount(
                id=uuid.uuid4(),
                asset_class=asset_class,
                cash_balance=seed,
                fees_total=0.0,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
            )
            db.add(account)

        if seed > 0:
            db.add(LedgerEntry(
                id=uuid.uuid4(),
                asset_class=asset_class,
                entry_type=EntryType.INITIAL_DEPOSIT,
                amount=seed,
                balance_after=seed,
                notes="Paper trading reset — initial deposit",
                created_at=now,
            ))

    await db.commit()
    return {
        "message": "Paper trading data reset successfully",
        "crypto_balance": initial_crypto_balance,
        "stock_balance":  initial_stock_balance,
    }


@router.get("/market-status")
async def get_market_status():
    """
    Returns the current NYSE session window so the frontend can display
    a market-hours badge without needing its own holiday calendar.

    status values: "open" | "pre_market" | "eod" | "closed"
    """
    status = market_status()
    labels = {
        "open":       "Market Open",
        "pre_market": "Pre-Market",
        "eod":        "EOD Window",
        "closed":     "Market Closed",
    }
    return {
        "status":        status,
        "label":         labels.get(status, "Unknown"),
        "is_trading_day": is_trading_day(),
    }
