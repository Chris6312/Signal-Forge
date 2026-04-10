import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func

from app.common.ws_manager import ws_manager
from app.common.database import AsyncSessionLocal
from app.common.models.position import Position, PositionState
from app.common.models.watchlist import WatchlistSymbol, SymbolState
from app.common.models.ledger import LedgerAccount
from app.common.runtime_state import runtime_state
from app.common.market_hours import market_status, is_trading_day

logger = logging.getLogger(__name__)
router = APIRouter()

_MARKET_LABELS = {
    "open":       "Market Open",
    "pre_market": "Pre-Market",
    "eod":        "EOD Window",
    "closed":     "Market Closed",
}


async def build_dashboard_payload() -> dict:
    async with AsyncSessionLocal() as db:
        state = await runtime_state.get_state()

        total_open = (await db.execute(
            select(func.count()).select_from(Position).where(Position.state == PositionState.OPEN)
        )).scalar() or 0

        active_count = (await db.execute(
            select(func.count()).select_from(WatchlistSymbol).where(WatchlistSymbol.state == SymbolState.ACTIVE)
        )).scalar() or 0

        managed_count = (await db.execute(
            select(func.count()).select_from(WatchlistSymbol).where(WatchlistSymbol.state == SymbolState.MANAGED)
        )).scalar() or 0

        accounts = (await db.execute(select(LedgerAccount))).scalars().all()

        pnl = []
        for asset_class in ("crypto", "stock"):
            account = next((a for a in accounts if a.asset_class == asset_class), None)
            open_count = (await db.execute(
                select(func.count()).select_from(Position).where(
                    Position.asset_class == asset_class,
                    Position.state == PositionState.OPEN,
                )
            )).scalar() or 0
            pnl.append({
                "asset_class":    asset_class,
                "realized_pnl":   account.realized_pnl   if account else 0.0,
                "unrealized_pnl": account.unrealized_pnl if account else 0.0,
                "cash_balance":   account.cash_balance   if account else 0.0,
                "fees_total":     account.fees_total     if account else 0.0,
                "open_positions": open_count,
            })

    return {
        "system_status":           state.get("status", "unknown"),
        "trading_enabled":         state.get("trading_enabled", True),
        "crypto_trading_enabled":  state.get("crypto_trading_enabled", True),
        "stock_trading_enabled":   state.get("stock_trading_enabled", True),
        "crypto_monitor":          state.get("crypto_monitor", "unknown"),
        "stock_monitor":           state.get("stock_monitor", "unknown"),
        "crypto_exit_worker":      state.get("crypto_exit_worker", "unknown"),
        "stock_exit_worker":       state.get("stock_exit_worker", "unknown"),
        "discord_listener":        state.get("discord_listener", "unknown"),
        "last_heartbeat":          state.get("last_heartbeat"),
        "pnl":                     pnl,
        "total_open_positions":    total_open,
        "active_watchlist_count":  active_count,
        "managed_watchlist_count": managed_count,
    }


def build_market_status_payload() -> dict:
    status = market_status()
    return {
        "status":         status,
        "label":          _MARKET_LABELS.get(status, "Unknown"),
        "is_trading_day": is_trading_day(),
    }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Push an immediate snapshot so the client has fresh data on connect
        await websocket.send_text(json.dumps({
            "topic": "dashboard_update",
            "data":  await build_dashboard_payload(),
        }))
        await websocket.send_text(json.dumps({
            "topic": "market_status_update",
            "data":  build_market_status_payload(),
        }))
        # Send ledger snapshots so ledger pages render without waiting for poll
        try:
            async with AsyncSessionLocal() as db:
                accounts = (await db.execute(select(LedgerAccount))).scalars().all()
                await websocket.send_text(json.dumps({
                    "topic": "ledger_accounts_update",
                    "data":  [
                        {
                            "id": str(a.id),
                            "asset_class": a.asset_class,
                            "cash_balance": a.cash_balance,
                            "fees_total": a.fees_total,
                            "realized_pnl": a.realized_pnl,
                            "unrealized_pnl": a.unrealized_pnl,
                            "last_reconciled_at": a.last_reconciled_at.isoformat() if a.last_reconciled_at else None,
                            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
                        }
                        for a in accounts
                    ],
                }))
                # Send a small recent entries snapshot (limit 100)
                entries_stmt = select(LedgerAccount)
                # note: ledger entries route handles entries; emit invalidation for entries
                await websocket.send_text(json.dumps({
                    "topic": "ledger_entries_update",
                    "data": None,
                    "action": "invalidate",
                    "queryKey": ["ledger-entries"],
                }))
        except Exception:
            # Non-critical: fail silently to avoid breaking WS connect
            pass

        # Keep the connection alive; receive_text() raises WebSocketDisconnect on close
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
