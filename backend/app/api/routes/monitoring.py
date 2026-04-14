import asyncio
import inspect
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.monitoring import EvaluateSymbolOut, MonitoringListOut
from app.common.candle_store import TF_MINUTES
from app.common.models.position import Position, PositionState
from app.common.models.watchlist import SymbolState, WatchlistSymbol
from app.common.redis_client import get_redis
from app.common.symbols import canonical_symbol
from app.common.watchlist_activation import activation_ready_at, is_watchlist_activation_ready
from app.regime import regime_engine
from app.stocks.candle_fetcher import StockCandleFetcher
from app.stocks.monitoring import STOCK_CANDLE_STORE, STOCK_CANDLE_FETCHER, _stock_candles_by_tf
from app.stocks.candle_fetcher import request_refresh as request_stock_refresh
from app.crypto.candle_fetcher import CryptoCandleFetcher
from app.crypto.monitoring import CRYPTO_CANDLE_STORE, CRYPTO_CANDLE_FETCHER, _crypto_candles_by_tf
from app.crypto.candle_fetcher import request_refresh as request_crypto_refresh

logger = logging.getLogger(__name__)
router = APIRouter()
_EVAL_CACHE: dict[tuple[str, ...], dict] = {}
_STOCK_CANDLE_STORE = STOCK_CANDLE_STORE
_CRYPTO_CANDLE_STORE = CRYPTO_CANDLE_STORE
_STOCK_FETCHER = STOCK_CANDLE_FETCHER
_CRYPTO_FETCHER = CRYPTO_CANDLE_FETCHER


def _strategy_key(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower().replace(" ", "_")


def _signal_key(signal) -> str | None:
    return _strategy_key(getattr(signal, "strategy_key", None) or getattr(signal, "strategy", None))


def _eval_timeseries_key(candles_by_tf: dict[str, list], ordered_frames: Sequence[str]) -> tuple[float, ...]:
    key = []
    for frame in ordered_frames:
        candles = candles_by_tf.get(frame) or []
        interval_minutes = 5 if frame == "5m" else 15 if frame == "15m" else 60 if frame == "1H" else 240 if frame == "4H" else 1440
        key.append(_latest_closed_ts(candles, interval_minutes))
    return tuple(key)


def _empty_evaluation(reason: str) -> dict:
    return {
        "signals": [],
        "top_strategy": None,
        "top_confidence": None,
        "evaluated_strategy_scores": {},
        "evaluated_strategies": {},
        "rejected_strategies": {reason: reason},
        "feature_scores": {},
        "timestamp_evaluated": None,
        "reason": reason,
    }


def _has_required_candles(candles_by_tf: dict[str, list], required_frames: Sequence[str]) -> bool:
    return all(bool(candles_by_tf.get(frame)) for frame in required_frames)


def _required_frames(asset_class: str) -> tuple[str, ...]:
    return ("15m", "1H", "4H", "daily") if asset_class == "crypto" else ("5m", "15m", "daily")


def _refresh_request(symbol: str, asset_class: str, frames: Sequence[str]) -> None:
    for frame in frames:
        if asset_class == "crypto":
            request_crypto_refresh(symbol, frame)
        else:
            request_stock_refresh(symbol, frame)


def _pending_eval_payload(asset_class: str, symbol: str, candles_by_tf: dict[str, list], store) -> dict:
    frames = _required_frames(asset_class)
    can = canonical_symbol(symbol, asset_class=asset_class)
    stale_or_missing = []
    for frame in frames:
        interval = TF_MINUTES[frame]
        if not candles_by_tf.get(frame) or store.needs_refresh(can if asset_class == "crypto" else symbol, interval):
            stale_or_missing.append(frame)

    if stale_or_missing:
        _refresh_request(symbol, asset_class, stale_or_missing)

    return {
        "top_signal": None,
        "diagnostics": {
            "signals": [],
            "top_strategy": "pending",
            "top_confidence": None,
            "evaluated_strategy_scores": {},
            "evaluated_strategies": {},
            "rejected_strategies": {},
            "feature_scores": {},
            "timestamp_evaluated": None,
            "lifecycle_state": "PENDING",
            "decision_state": "WAITING_FOR_DATA",
            "decision_reason": "pending_candle_refresh",
        },
        "evaluation": {
            "strategies": [],
            "top_strategy": "pending",
            "confidence": None,
            "lifecycle_state": "PENDING",
            "decision_state": "WAITING_FOR_DATA",
            "decision_reason": "pending_candle_refresh",
        },
        "pending_refresh": stale_or_missing,
    }


def _is_pending_eval(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    diagnostics = payload.get("diagnostics")
    return isinstance(diagnostics, dict) and diagnostics.get("decision_state") == "WAITING_FOR_DATA"


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


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _stock_eval_candles(symbol: str) -> dict[str, list]:
    return _stock_candles_by_tf(_STOCK_CANDLE_STORE, symbol)


def _stock_eval_cache_key(symbol: str, candles_by_tf: dict[str, list] | None = None) -> tuple[str, str, float, float, float, float]:
    candles_by_tf = candles_by_tf or _stock_candles_by_tf(_STOCK_CANDLE_STORE, symbol)
    return (
        "stock",
        symbol,
        *_eval_timeseries_key(candles_by_tf, ("1m", "5m", "15m", "daily")),
    )


def _crypto_eval_cache_key(symbol: str, candles_by_tf: dict[str, list] | None = None) -> tuple[str, str, float, float, float, float]:
    candles_by_tf = candles_by_tf or _crypto_candles_by_tf(_CRYPTO_CANDLE_STORE, symbol)
    can = canonical_symbol(symbol, asset_class="crypto")
    return (
        "crypto",
        can,
        *_eval_timeseries_key(candles_by_tf, ("15m", "1H", "4H", "daily")),
    )


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


def _build_evaluation_payload(normalized: dict, top_signal) -> dict:
    return {
        "strategies": [_serialize_signal(signal) for signal in normalized.get("signals") or []],
        "top_strategy": normalized.get("top_strategy"),
        "confidence": normalized.get("top_confidence") if normalized.get("top_confidence") is not None else (getattr(top_signal, "confidence", 0) if top_signal else 0),
    }


def _needs_retry_after_eval(normalized: dict) -> bool:
    if normalized.get("signals"):
        return False

    rejected = normalized.get("rejected_strategies") or {}
    if not isinstance(rejected, dict) or not rejected:
        return not bool(normalized.get("evaluated_strategy_scores"))

    reasons = [str(reason) for reason in rejected.values() if reason]
    return not bool(reasons) or all(reason == "insufficient_candles" for reason in reasons)


async def _evaluate_with_backfill(asset_class: str, symbol: str, candles_by_tf: dict[str, list], evaluate_all, fetcher, store):
    raw_result = await _maybe_await(evaluate_all(symbol, candles_by_tf, include_diagnostics=True))
    normalized = _normalize_eval_result(raw_result)

    if _needs_retry_after_eval(normalized):
        try:
            await fetcher.backfill(symbol)
        except Exception as exc:
            logger.warning("Backfill retry failed for %s (%s): %s", symbol, asset_class, exc)
        candles_by_tf = _crypto_candles_by_tf(store, symbol) if asset_class == "crypto" else _stock_candles_by_tf(store, symbol)
        raw_result = await _maybe_await(evaluate_all(symbol, candles_by_tf, include_diagnostics=True))
        normalized = _normalize_eval_result(raw_result)

    return normalized, candles_by_tf


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
            lookup_symbol = canonical_symbol(ws.symbol, asset_class=ws.asset_class) if ws.asset_class == "crypto" else ws.symbol.upper()
            if ws.asset_class == "crypto":
                from app.crypto.strategies.entry_strategies import evaluate_all

                can = lookup_symbol
                candles_by_tf = _crypto_candles_by_tf(_CRYPTO_CANDLE_STORE, can)
                cache_key = _crypto_eval_cache_key(can, candles_by_tf)
                if cache_key in _EVAL_CACHE:
                    return _EVAL_CACHE[cache_key]
                normalized, candles_by_tf = await _evaluate_with_backfill("crypto", can, candles_by_tf, evaluate_all, _CRYPTO_FETCHER, _CRYPTO_CANDLE_STORE)
            elif ws.asset_class == "stock":
                from app.stocks.strategies.entry_strategies import evaluate_all

                candles_by_tf = await _stock_eval_candles(ws.symbol)
                cache_key = _stock_eval_cache_key(ws.symbol, candles_by_tf)
                if cache_key in _EVAL_CACHE:
                    return _EVAL_CACHE[cache_key]
                normalized, candles_by_tf = await _evaluate_with_backfill("stock", ws.symbol, candles_by_tf, evaluate_all, _STOCK_FETCHER, _STOCK_CANDLE_STORE)
            else:
                normalized = _normalize_eval_result([])

            top_signal = _select_top_signal(normalized["signals"], normalized["top_strategy"])
            payload = {
                "top_signal": top_signal,
                "diagnostics": normalized,
                "evaluation": _build_evaluation_payload(normalized, top_signal),
            }
            if cache_key is not None:
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
            if isinstance(diagnostics, dict) and diagnostics.get("reason") == "insufficient_candles":
                evaluation_error = "insufficient_candles"
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
                "strategies": [_serialize_signal(signal) for signal in (diagnostics.get("signals") or [])] if isinstance(diagnostics, dict) else [],
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
            from app.crypto.strategies.entry_strategies import evaluate_all

            candles_by_tf = _crypto_candles_by_tf(_CRYPTO_CANDLE_STORE, can)
            normalized, candles_by_tf = await _evaluate_with_backfill("crypto", can, candles_by_tf, evaluate_all, _CRYPTO_FETCHER, _CRYPTO_CANDLE_STORE)
        elif asset_class == "stock":
            from app.stocks.strategies.entry_strategies import evaluate_all

            upper_symbol = symbol.upper()
            candles_by_tf = await _stock_eval_candles(upper_symbol)
            normalized, candles_by_tf = await _evaluate_with_backfill("stock", upper_symbol, candles_by_tf, evaluate_all, _STOCK_FETCHER, _STOCK_CANDLE_STORE)
        else:
            normalized = _normalize_eval_result([])

        result["signals"] = [_serialize_signal(signal) for signal in normalized["signals"]]
        result["top_strategy"] = normalized["top_strategy"]
        result["top_confidence"] = normalized["top_confidence"]
        result["evaluation"] = {
            "strategies": result["signals"],
            "top_strategy": normalized["top_strategy"],
            "confidence": normalized["top_confidence"] if normalized["top_confidence"] is not None else 0,
        }
        result["evaluated_strategy_scores"] = normalized["evaluated_strategy_scores"]
        result["evaluated_strategies"] = normalized["evaluated_strategies"]
        result["rejected_strategies"] = normalized["rejected_strategies"]
        result["feature_scores"] = normalized["feature_scores"]
        result["timestamp_evaluated"] = normalized["timestamp_evaluated"]
    except Exception as exc:
        result["error"] = str(exc)

    return result
