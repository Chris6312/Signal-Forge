import asyncio
import logging
from datetime import datetime, timezone
from collections.abc import Mapping, Sequence

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.monitoring import EvaluateSymbolOut, MonitoringListOut
from app.common.models.position import Position, PositionState
from app.common.models.watchlist import SymbolState, WatchlistSymbol
from app.common.redis_client import get_redis
from app.common.symbols import canonical_symbol
from app.common.watchlist_activation import activation_ready_at, is_watchlist_activation_ready
from app.regime import regime_engine

logger = logging.getLogger(__name__)
router = APIRouter()
_EVAL_CACHE: dict[tuple[str, str, float], dict] = {}


def _strategy_key(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower().replace(" ", "_")


def _signal_key(signal) -> str | None:
    return _strategy_key(getattr(signal, "strategy_key", None) or getattr(signal, "strategy", None))


def _latest_closed_ts(candles, interval_minutes: int) -> float:
    if not candles:
        return 0.0

    last_item = candles[-1]
    if isinstance(last_item, dict) and "time" in last_item:
        text = str(last_item.get("time") or "").strip().replace("Z", "+00:00")
        if " " in text and "T" not in text:
            text = text.replace(" ", "T", 1)
        try:
            dt = datetime.fromisoformat(text)
            if len(text) == 10 and interval_minutes >= 1440:
                dt = datetime.fromisoformat(text + "T00:00+00:00")
                return dt.astimezone(timezone.utc).timestamp() + (interval_minutes * 60)
            return dt.astimezone(timezone.utc).timestamp()
        except Exception:
            return 0.0

    if isinstance(last_item, (list, tuple)) and len(last_item) > 0:
        try:
            return float(last_item[0]) + (interval_minutes * 60)
        except Exception:
            return 0.0

    return 0.0


def _select_top_signal(signals, top_strategy: str | None):
    if not signals:
        return None

    top_key = _strategy_key(top_strategy)
    if top_key:
        for signal in signals:
            if _signal_key(signal) == top_key:
                return signal

    return signals[0]


def _normalize_eval_result(result) -> dict:
    if isinstance(result, Mapping):
        signals = result.get("signals", [])
        if not isinstance(signals, list):
            signals = []
        return {
            "signals": signals,
            "top_strategy": result.get("top_strategy"),
            "top_confidence": result.get("top_confidence"),
            "evaluated_strategy_scores": dict(result.get("evaluated_strategy_scores", {}) or {}),
            "evaluated_strategies": dict(result.get("evaluated_strategies", {}) or {}),
            "rejected_strategies": dict(result.get("rejected_strategies", {}) or {}),
            "feature_scores": dict(result.get("feature_scores", {}) or {}),
            "timestamp_evaluated": result.get("timestamp_evaluated"),
        }

    if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
        return {
            "signals": list(result),
            "top_strategy": None,
            "top_confidence": None,
            "evaluated_strategy_scores": {},
            "evaluated_strategies": {},
            "rejected_strategies": {},
            "feature_scores": {},
            "timestamp_evaluated": None,
        }

    return {
        "signals": [],
        "top_strategy": None,
        "top_confidence": None,
        "evaluated_strategy_scores": {},
        "evaluated_strategies": {},
        "rejected_strategies": {},
        "feature_scores": {},
        "timestamp_evaluated": None,
    }


def _serialize_signal(signal) -> dict:
    return {
        "strategy": signal.strategy,
        "entry_price": signal.entry_price,
        "stop": signal.initial_stop,
        "tp1": signal.profit_target_1,
        "tp2": signal.profit_target_2,
        "regime": signal.regime,
        "confidence": signal.confidence,
        "notes": signal.notes,
    }


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
            cache_key = None
            if ws.asset_class == "crypto":
                from app.crypto.kraken_client import kraken_client
                from app.crypto.strategies.entry_strategies import evaluate_all

                can = canonical_symbol(ws.symbol, asset_class=ws.asset_class)
                ohlcv_15m, ohlcv_1h, ohlcv_4h, ohlcv_daily = await asyncio.gather(
                    kraken_client.get_ohlcv(can, interval=15),
                    kraken_client.get_ohlcv(can, interval=60),
                    kraken_client.get_ohlcv(can, interval=240),
                    kraken_client.get_ohlcv(can, interval=1440),
                )
                trigger_ts = _latest_closed_ts(ohlcv_15m, 15)
                cache_key = (ws.asset_class, can, trigger_ts)
                if trigger_ts and cache_key in _EVAL_CACHE:
                    return _EVAL_CACHE[cache_key]
                raw_result = evaluate_all(
                    can,
                    {
                        "15m": ohlcv_15m,
                        "1H": ohlcv_1h,
                        "4H": ohlcv_4h,
                        "daily": ohlcv_daily,
                    },
                    include_diagnostics=True,
                )
            elif ws.asset_class == "stock":
                from app.stocks.strategies.entry_strategies import evaluate_all
                from app.stocks.tradier_client import tradier_client

                tf5m, tf15m, daily = await asyncio.gather(
                    tradier_client.get_timesales(ws.symbol, interval="5min"),
                    tradier_client.get_timesales(ws.symbol, interval="15min"),
                    tradier_client.get_history(ws.symbol),
                )
                trigger_ts = _latest_closed_ts(tf5m, 5)
                cache_key = (ws.asset_class, ws.symbol, trigger_ts)
                if trigger_ts and cache_key in _EVAL_CACHE:
                    return _EVAL_CACHE[cache_key]
                raw_result = evaluate_all(
                    ws.symbol,
                    {
                        "5m": tf5m,
                        "15m": tf15m,
                        "daily": daily,
                    },
                    include_diagnostics=True,
                )
            else:
                raw_result = []

            normalized = _normalize_eval_result(raw_result)
            signals = normalized["signals"]
            top_signal = _select_top_signal(signals, normalized["top_strategy"])
            evaluation = {
                "strategies": signals,
                "top_strategy": normalized["top_strategy"],
                "confidence": normalized["top_confidence"] if normalized["top_confidence"] is not None else (top_signal.confidence if top_signal else 0),
            }
            payload = {
                "top_signal": top_signal,
                "diagnostics": normalized,
                "evaluation": evaluation,
            }
            if cache_key and cache_key[2]:
                _EVAL_CACHE[cache_key] = payload
            return payload
        except Exception as exc:
            logger.warning("Top-signal evaluation failed for %s (%s): %s", ws.symbol, ws.asset_class, exc)
            return exc

    top_signals = await asyncio.gather(*[_top_signal(ws) for ws in symbols])

    candidates = []
    for ws, sig in zip(symbols, top_signals):
        display_symbol = canonical_symbol(ws.symbol, asset_class=ws.asset_class) if ws.asset_class == "crypto" else ws.symbol

        blocked_reason = None
        has_open_position = False
        cooldown_active = False
        regime_allowed = None
        evaluation_error = None
        evaluation = None
        top_notes = None
        position_or_order_status = None
        backend_top_strategy = None
        backend_top_confidence = None

        if isinstance(sig, Exception):
            evaluation_error = str(sig)
            sig_obj = None
            diagnostics = None
        else:
            sig_obj = sig.get("top_signal") if isinstance(sig, dict) else None
            diagnostics = sig.get("diagnostics") if isinstance(sig, dict) else None
            evaluation = sig.get("evaluation") if isinstance(sig, dict) else None
            backend_top_strategy = diagnostics.get("top_strategy") if isinstance(diagnostics, dict) else None
            backend_top_confidence = diagnostics.get("top_confidence") if isinstance(diagnostics, dict) else None
            if diagnostics and isinstance(diagnostics, dict):
                sig_obj = _select_top_signal(diagnostics.get("signals") or [], backend_top_strategy) or sig_obj

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

        try:
            redis = await get_redis()
            cooldown_key = f"cooldown:{ws.asset_class}:{canonical_symbol(ws.symbol, asset_class=ws.asset_class) if ws.asset_class == 'crypto' else ws.symbol}"
            cooldown_active = await redis.exists(cooldown_key) if redis else False
        except Exception as exc:
            logger.debug("Cooldown lookup failed for %s: %s", ws.symbol, exc)

        try:
            if not is_watchlist_activation_ready(ws.added_at):
                ready_at = activation_ready_at(ws.added_at)
                blocked_reason = f"awaiting_activation_candle_until:{ready_at.isoformat()}" if ready_at else "awaiting_activation_candle"

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
                    if not allowed and not blocked_reason:
                        blocked_reason = reason
                except Exception as exc:
                    logger.debug("Regime check failed for %s: %s", ws.symbol, exc)
        except Exception:
            pass

        if sig_obj:
            top_notes = getattr(sig_obj, "notes", None)

        candidates.append({
            "symbol": display_symbol,
            "asset_class": ws.asset_class,
            "state": ws.state,
            "added_at": ws.added_at.isoformat() if ws.added_at else None,
            "watchlist_source_id": ws.watchlist_source_id,
            "top_strategy": backend_top_strategy or (sig_obj.strategy if sig_obj else None),
            "top_confidence": backend_top_confidence if backend_top_confidence is not None else (sig_obj.confidence if sig_obj else None),
            "top_entry": sig_obj.entry_price if sig_obj else None,
            "evaluation": evaluation if isinstance(evaluation, dict) else ({
                "strategies": (diagnostics.get("signals") or []) if isinstance(diagnostics, dict) else [],
                "top_strategy": backend_top_strategy,
                "confidence": backend_top_confidence if backend_top_confidence is not None else (sig_obj.confidence if sig_obj else 0),
            } if diagnostics is not None or sig_obj is not None else None),
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
    result: dict = {
        "symbol": can,
        "asset_class": asset_class,
        "signals": [],
        "top_strategy": None,
        "top_confidence": None,
        "evaluated_strategy_scores": {},
        "evaluated_strategies": {},
        "rejected_strategies": {},
        "feature_scores": {},
        "timestamp_evaluated": None,
    }

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
            raw_result = evaluate_all(
                can,
                {
                    "15m": ohlcv_15m,
                    "1H": ohlcv_1h,
                    "4H": ohlcv_4h,
                    "daily": ohlcv_daily,
                },
                include_diagnostics=True,
            )
        elif asset_class == "stock":
            from app.stocks.strategies.entry_strategies import evaluate_all
            from app.stocks.tradier_client import tradier_client

            upper_symbol = symbol.upper()
            tf5m, tf15m, daily = await asyncio.gather(
                tradier_client.get_timesales(upper_symbol, interval="5min"),
                tradier_client.get_timesales(upper_symbol, interval="15min"),
                tradier_client.get_history(upper_symbol),
            )
            raw_result = evaluate_all(
                upper_symbol,
                {
                    "5m": tf5m,
                    "15m": tf15m,
                    "daily": daily,
                },
                include_diagnostics=True,
            )
        else:
            raw_result = []

        normalized = _normalize_eval_result(raw_result)
        result["signals"] = [_serialize_signal(signal) for signal in normalized["signals"]]
        result["top_strategy"] = normalized["top_strategy"]
        result["top_confidence"] = normalized["top_confidence"]
        result["evaluated_strategy_scores"] = normalized["evaluated_strategy_scores"]
        result["evaluated_strategies"] = normalized["evaluated_strategies"]
        result["rejected_strategies"] = normalized["rejected_strategies"]
        result["feature_scores"] = normalized["feature_scores"]
        result["timestamp_evaluated"] = normalized["timestamp_evaluated"]
    except Exception as exc:
        result["error"] = str(exc)

    return result
