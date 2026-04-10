import asyncio
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.monitoring import EvaluateSymbolOut, MonitoringListOut
from app.common.models.watchlist import WatchlistSymbol, SymbolState
from app.common.symbols import canonical_symbol
from app.common.redis_client import get_redis
from app.common.models.position import Position, PositionState
from app.regime import regime_engine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=MonitoringListOut)
async def get_monitoring_candidates(
    asset_class: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(WatchlistSymbol).where(WatchlistSymbol.state == SymbolState.ACTIVE)
    if asset_class:
        stmt = stmt.where(WatchlistSymbol.asset_class == asset_class)
    result = await db.execute(stmt)
    symbols = result.scalars().all()

    async def _top_signal(ws: WatchlistSymbol):
        try:
            if ws.asset_class == "crypto":
                from app.crypto.kraken_client import kraken_client
                from app.crypto.strategies.entry_strategies import evaluate_all
                can = canonical_symbol(ws.symbol, asset_class=ws.asset_class)
                ohlcv_1h, ohlcv_4h = await asyncio.gather(
                    kraken_client.get_ohlcv(can, interval=60),
                    kraken_client.get_ohlcv(can, interval=240),
                )
                candles_by_tf = {
                    "15m": await kraken_client.get_ohlcv(can, interval=15),
                    "1H":  ohlcv_1h,
                    "4H":  ohlcv_4h,
                    "daily": await kraken_client.get_ohlcv(can, interval=1440),
                }
                signals = evaluate_all(can, candles_by_tf)
            elif ws.asset_class == "stock":
                from app.stocks.tradier_client import tradier_client
                from app.stocks.strategies.entry_strategies import evaluate_all
                tf5m, tf15m, daily = await asyncio.gather(
                    tradier_client.get_timesales(ws.symbol, interval="5min"),
                    tradier_client.get_timesales(ws.symbol, interval="15min"),
                    tradier_client.get_history(ws.symbol),
                )
                candles_by_tf = {
                    "5m":    tf5m,
                    "15m":   tf15m,
                    "daily": daily,
                }
                signals = evaluate_all(ws.symbol, candles_by_tf)
            else:
                signals = []
            return signals[0] if signals else None
        except Exception as exc:
            logger.warning("Top-signal evaluation failed for %s (%s): %s", ws.symbol, ws.asset_class, exc)
            return exc

    top_signals = await asyncio.gather(*[_top_signal(ws) for ws in symbols])

    candidates = []
    for ws, sig in zip(symbols, top_signals):
        display_symbol = canonical_symbol(ws.symbol, asset_class=ws.asset_class) if ws.asset_class == "crypto" else ws.symbol

        # diagnostics defaults
        blocked_reason = None
        has_open_position = False
        cooldown_active = False
        regime_allowed = None
        evaluation_error = None
        top_notes = None
        position_or_order_status = None

        # If _top_signal returned an exception, surface it as evaluation_error
        if isinstance(sig, Exception):
            evaluation_error = str(sig)
            sig_obj = None
        else:
            sig_obj = sig

        # Check open positions
        try:
            stmt = select(Position).where(
                Position.symbol == canonical_symbol(ws.symbol, asset_class=ws.asset_class) if ws.asset_class == "crypto" else ws.symbol,
                Position.asset_class == ws.asset_class,
                Position.state == PositionState.OPEN,
            ).limit(1)
            res = await db.execute(stmt)
            has_open_position = res.first() is not None
        except Exception as exc:
            logger.debug("Open position check failed for %s: %s", ws.symbol, exc)

        # Check cooldown key in redis
        try:
            redis = await get_redis()
            cooldown_key = f"cooldown:{ws.asset_class}:{canonical_symbol(ws.symbol, asset_class=ws.asset_class) if ws.asset_class == 'crypto' else ws.symbol}"
            cooldown_active = await redis.exists(cooldown_key) if redis else False
        except Exception as exc:
            logger.debug("Cooldown lookup failed for %s: %s", ws.symbol, exc)

        # Regime allowance check: if we have a signal, ask regime engine
        try:
            if sig_obj:
                try:
                    stmt_count = select(func.count()).select_from(Position).where(
                        Position.asset_class == ws.asset_class,
                        Position.state == PositionState.OPEN,
                    )
                    res_count = await db.execute(stmt_count)
                    current_count = res_count.scalar_one()
                except Exception:
                    current_count = 0
                try:
                    allowed, reason = regime_engine.can_open(ws.asset_class, sig_obj.strategy, sig_obj.confidence, current_count)
                    regime_allowed = allowed
                    if not allowed:
                        blocked_reason = reason
                except Exception as exc:
                    logger.debug("Regime check failed for %s: %s", ws.symbol, exc)
        except Exception:
            pass

        if sig_obj:
            top_notes = getattr(sig_obj, 'notes', None)
            position_or_order_status = None

        candidates.append({
            "symbol": display_symbol,
            "asset_class": ws.asset_class,
            "state": ws.state,
            "added_at": ws.added_at.isoformat() if ws.added_at else None,
            "watchlist_source_id": ws.watchlist_source_id,
            "top_strategy": sig_obj.strategy if sig_obj else None,
            "top_confidence": sig_obj.confidence if sig_obj else None,
            "top_entry": sig_obj.entry_price if sig_obj else None,
            "blocked_reason": blocked_reason,
            "has_open_position": has_open_position,
            "cooldown_active": bool(cooldown_active),
            "regime_allowed": regime_allowed,
            "evaluation_error": evaluation_error,
            "top_notes": top_notes,
            "position_or_order_status": position_or_order_status,
        })

    return {"candidates": candidates, "total": len(candidates)}


@router.get("/evaluate/{symbol:path}", response_model=EvaluateSymbolOut)
async def evaluate_symbol(symbol: str, asset_class: str = Query("crypto")):
    can = canonical_symbol(symbol, asset_class=asset_class)
    result: dict = {"symbol": can, "asset_class": asset_class, "signals": []}

    try:
        if asset_class == "crypto":
            from app.crypto.kraken_client import kraken_client
            from app.crypto.strategies.entry_strategies import evaluate_all
            ohlcv_15m, ohlcv_1h, ohlcv_4h, ohlcv_daily = await asyncio.gather(
                kraken_client.get_ohlcv(can, interval=15),
                kraken_client.get_ohlcv(can, interval=60),
                kraken_client.get_ohlcv(can, interval=240),
                kraken_client.get_ohlcv(can, interval=1440),
            )
            candles_by_tf = {
                "15m":   ohlcv_15m,
                "1H":    ohlcv_1h,
                "4H":    ohlcv_4h,
                "daily": ohlcv_daily,
            }
            signals = evaluate_all(can, candles_by_tf)
        elif asset_class == "stock":
            from app.stocks.tradier_client import tradier_client
            from app.stocks.strategies.entry_strategies import evaluate_all
            tf5m, tf15m, daily = await asyncio.gather(
                tradier_client.get_timesales(symbol.upper(), interval="5min"),
                tradier_client.get_timesales(symbol.upper(), interval="15min"),
                tradier_client.get_history(symbol.upper()),
            )
            candles_by_tf = {
                "5m":    tf5m,
                "15m":   tf15m,
                "daily": daily,
            }
            signals = evaluate_all(symbol.upper(), candles_by_tf)
        else:
            signals = []
        result["signals"] = [
            {
                "strategy": s.strategy,
                "entry_price": s.entry_price,
                "stop": s.initial_stop,
                "tp1": s.profit_target_1,
                "tp2": s.profit_target_2,
                "regime": s.regime,
                "confidence": s.confidence,
                "notes": s.notes,
            }
            for s in signals
        ]
    except Exception as exc:
        result["error"] = str(exc)

    return result
