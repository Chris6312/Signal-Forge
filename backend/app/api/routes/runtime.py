import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin, get_db_session
from app.api.schemas.runtime import RuntimeStateOut, RuntimeUpdateIn
from app.common.runtime_state import runtime_state
from app.common.market_hours import market_status, is_trading_day
from app.common.audit_logger import log_event
from app.common.models.order import Order, OrderStatus
from app.common.models.position import Position, PositionState
from app.common.models.audit import AuditSource
from app.common.database import AsyncSessionLocal
from datetime import datetime, timezone
from fastapi import Header
import uuid

DELAY_SECONDS = 5

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
async def halt_trading(confirm_code: str | None = Query(None), x_admin_user: str | None = Header(None)):
    operator = x_admin_user or 'admin'

    # If no confirm_code provided, perform a soft halt
    if not confirm_code:
        await runtime_state.set_value("trading_enabled", False)
        await runtime_state.set_value("halt_mode", "soft")
        ts = datetime.now(timezone.utc).isoformat()
        await runtime_state.set_value("last_halt", {"at": ts, "by": operator, "mode": "soft"})
        # Audit
        async with AsyncSessionLocal() as db:
            await log_event(db, 'SYSTEM_SOFT_HALT', f'Soft halt initiated by {operator}', source=AuditSource.SYSTEM, event_data={'operator': operator})
            await db.commit()
        return {"message": "Soft halt executed"}

    # Hard halt path: validate confirm code against last_halt_request
    req = await runtime_state.get_value('last_halt_request', {})
    if not req or req.get('token') != confirm_code:
        raise HTTPException(status_code=400, detail='Invalid or missing confirm code')

    try:
        requested_at = datetime.fromisoformat(req.get('requested_at'))
    except Exception:
        raise HTTPException(status_code=400, detail='Malformed halt request')

    now = datetime.now(timezone.utc)
    if (now - requested_at).total_seconds() < DELAY_SECONDS:
        raise HTTPException(status_code=400, detail=f'Please wait at least {DELAY_SECONDS} seconds after requesting hard halt before confirming')

    # All validations passed: proceed with hard halt
    await runtime_state.set_value('trading_enabled', False)
    await runtime_state.set_value('halt_mode', 'hard')

    async with AsyncSessionLocal() as db:
        try:
            now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

            # Cancel pending/submitted/partially_filled orders and attempt broker-level cancellations
            pending_statuses = [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED]
            stmt_orders = select(Order).where(Order.status.in_(pending_statuses))
            res_orders = await db.execute(stmt_orders)
            orders = res_orders.scalars().all()
            orders_cancelled = 0
            from app.crypto.kraken_client import kraken_client
            from app.stocks.tradier_client import tradier_client

            for ord in orders:
                cancelled = False
                # Attempt broker-level cancel if broker_order_id present
                try:
                    if ord.asset_class == 'crypto' and ord.broker_order_id:
                        try:
                            await kraken_client.cancel_order(ord.broker_order_id)
                        except Exception as e:
                            # log and continue
                            await log_event(db, 'ORDER_BROKER_CANCEL_FAILED', f'Failed broker cancel for {ord.id}: {e}', asset_class=ord.asset_class, symbol=ord.symbol, position_id=str(ord.position_id) if ord.position_id else None, source=AuditSource.WORKER, event_data={'error': str(e)})
                    if ord.asset_class == 'stock' and ord.broker_order_id:
                        try:
                            await tradier_client.cancel_order(ord.broker_order_id)
                        except Exception as e:
                            await log_event(db, 'ORDER_BROKER_CANCEL_FAILED', f'Failed broker cancel for {ord.id}: {e}', asset_class=ord.asset_class, symbol=ord.symbol, position_id=str(ord.position_id) if ord.position_id else None, source=AuditSource.WORKER, event_data={'error': str(e)})
                except Exception:
                    pass

                # Mark DB order cancelled
                try:
                    ord.status = OrderStatus.CANCELLED
                    ord.notes = (ord.notes or '') + ' | Cancelled by HARD_KILL'
                    db.add(ord)
                    orders_cancelled += 1
                    await log_event(db, 'ORDER_CANCELLED', f'Order {ord.id} cancelled by hard kill', asset_class=ord.asset_class, symbol=ord.symbol, position_id=str(ord.position_id) if ord.position_id else None, source=AuditSource.WORKER)
                except Exception as exc:
                    await log_event(db, 'ORDER_CANCEL_FAILED', f'Failed to mark order {ord.id} cancelled: {exc}', asset_class=ord.asset_class, symbol=ord.symbol, source=AuditSource.WORKER, event_data={'error': str(exc)})

            # Close open positions and attempt broker-level market exits
            result = await db.execute(select(Position).where(Position.state == PositionState.OPEN))
            open_positions = result.scalars().all()
            closed_count = 0
            for pos in open_positions:
                try:
                    # Attempt broker-level exit
                    try:
                        if pos.asset_class == 'crypto':
                            # Sell via Kraken market order
                            try:
                                await kraken_client.add_order(pos.symbol, 'sell', 'market', float(pos.quantity))
                            except Exception as e:
                                await log_event(db, 'BROKER_EXIT_FAILED', f'Crypto broker exit failed for {pos.symbol}: {e}', asset_class=pos.asset_class, symbol=pos.symbol, position_id=str(pos.id), source=AuditSource.WORKER, event_data={'error': str(e)})
                        elif pos.asset_class == 'stock':
                            try:
                                await tradier_client.place_order(pos.symbol, 'sell', int(pos.quantity), 'market')
                            except Exception as e:
                                await log_event(db, 'BROKER_EXIT_FAILED', f'Stock broker exit failed for {pos.symbol}: {e}', asset_class=pos.asset_class, symbol=pos.symbol, position_id=str(pos.id), source=AuditSource.WORKER, event_data={'error': str(e)})
                    except Exception:
                        pass

                    pos.state = PositionState.CLOSED
                    pos.exit_time = now_naive
                    pos.exit_price = pos.current_price or pos.entry_price or 0.0
                    pos.exit_reason = 'HARD_KILL'
                    pos.pnl_realized = pos.pnl_unrealized or 0.0
                    pos.updated_at = now_naive
                    db.add(pos)
                    closed_count += 1

                    # Audit per-position
                    await log_event(
                        db,
                        'POSITION_FORCE_CLOSED',
                        f'Position {pos.symbol} force-closed by hard kill',
                        asset_class=pos.asset_class,
                        symbol=pos.symbol,
                        position_id=str(pos.id),
                        source=AuditSource.WORKER,
                        event_data={'exit_price': pos.exit_price, 'reason': 'HARD_KILL'},
                    )
                except Exception as exc:
                    await log_event(db, 'POSITION_FORCE_CLOSE_FAILED', f'Failed closing {pos.symbol}: {exc}', asset_class=pos.asset_class, symbol=pos.symbol, source=AuditSource.WORKER, event_data={'error': str(exc)})

            # Record summary audit
            await log_event(db, 'SYSTEM_HARD_HALT', f'Hard halt initiated by {operator}. Orders cancelled: {orders_cancelled}, positions closed: {closed_count}', source=AuditSource.SYSTEM, event_data={'orders_cancelled': orders_cancelled, 'positions_closed': closed_count, 'operator': operator})

            # Set last_halt runtime state
            await runtime_state.set_value('last_halt', {'at': now.isoformat(), 'by': operator, 'mode': 'hard'})

            await db.commit()
            return {'message': 'Hard halt executed', 'orders_cancelled': orders_cancelled, 'positions_closed': closed_count}
        except Exception as exc:
            try:
                await db.rollback()
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f'Hard halt failed: {exc}')


@router.post('/halt/request', dependencies=[Depends(require_admin)])
async def request_hard_halt(x_admin_user: str | None = Header(None)):
    """First step of two-step hard halt: generate a short-lived token and record request time."""
    token = str(uuid.uuid4())[:8]
    operator = x_admin_user or 'admin'
    now = datetime.now(timezone.utc).isoformat()
    await runtime_state.set_value('last_halt_request', {'token': token, 'requested_at': now, 'by': operator})
    return {'token': token, 'requested_at': now}


@router.get('/halt/last')
async def get_last_halt():
    val = await runtime_state.get_value('last_halt', {})
    return val


@router.post("/resume", dependencies=[Depends(require_admin)])
async def resume_trading(db: AsyncSession = Depends(get_db_session)):
    """Resume normal trading. Clears halt_mode and reenables trading_enabled."""
    await runtime_state.set_value("trading_enabled", True)
    await runtime_state.set_value("halt_mode", "none")
    # Log audit entry
    await log_event(db, 'SYSTEM_RESUME', 'Trading resumed by operator', source=AuditSource.SYSTEM)
    await db.commit()
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
        .values(state=SymbolState.INACTIVE, closed_at=datetime.now(timezone.utc).replace(tzinfo=None))
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
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
