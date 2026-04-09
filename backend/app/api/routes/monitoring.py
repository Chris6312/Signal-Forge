import asyncio
import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.monitoring import EvaluateSymbolOut, MonitoringListOut
from app.common.models.watchlist import WatchlistSymbol, SymbolState

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
                ohlcv_1h, ohlcv_4h = await asyncio.gather(
                    kraken_client.get_ohlcv(ws.symbol, interval=60),
                    kraken_client.get_ohlcv(ws.symbol, interval=240),
                )
                candles_by_tf = {
                    "15m": await kraken_client.get_ohlcv(ws.symbol, interval=15),
                    "1H":  ohlcv_1h,
                    "4H":  ohlcv_4h,
                    "daily": await kraken_client.get_ohlcv(ws.symbol, interval=1440),
                }
                signals = evaluate_all(ws.symbol, candles_by_tf)
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
            return None

    top_signals = await asyncio.gather(*[_top_signal(ws) for ws in symbols])

    candidates = []
    for ws, sig in zip(symbols, top_signals):
        candidates.append({
            "symbol": ws.symbol,
            "asset_class": ws.asset_class,
            "state": ws.state,
            "added_at": ws.added_at.isoformat() if ws.added_at else None,
            "watchlist_source_id": ws.watchlist_source_id,
            "top_strategy": sig.strategy if sig else None,
            "top_confidence": sig.confidence if sig else None,
            "top_entry": sig.entry_price if sig else None,
        })

    return {"candidates": candidates, "total": len(candidates)}


@router.get("/evaluate/{symbol:path}", response_model=EvaluateSymbolOut)
async def evaluate_symbol(symbol: str, asset_class: str = Query("crypto")):
    result: dict = {"symbol": symbol.upper(), "asset_class": asset_class, "signals": []}

    try:
        if asset_class == "crypto":
            from app.crypto.kraken_client import kraken_client
            from app.crypto.strategies.entry_strategies import evaluate_all
            ohlcv_15m, ohlcv_1h, ohlcv_4h, ohlcv_daily = await asyncio.gather(
                kraken_client.get_ohlcv(symbol.upper(), interval=15),
                kraken_client.get_ohlcv(symbol.upper(), interval=60),
                kraken_client.get_ohlcv(symbol.upper(), interval=240),
                kraken_client.get_ohlcv(symbol.upper(), interval=1440),
            )
            candles_by_tf = {
                "15m":   ohlcv_15m,
                "1H":    ohlcv_1h,
                "4H":    ohlcv_4h,
                "daily": ohlcv_daily,
            }
            signals = evaluate_all(symbol.upper(), candles_by_tf)
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
