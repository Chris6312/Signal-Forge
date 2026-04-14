"""stocks/candle_fetcher.py — Fetch and normalise multi-timeframe OHLCV for stocks.

Tradier sources:
  1m / 5m / 15m  →  /v1/markets/timesales  (session_filter=open)
  daily          →  /v1/markets/history

All candles are normalised to a uniform dict schema so strategy code only
deals with one format:
  {"time": str, "open": float, "high": float, "low": float,
   "close": float, "volume": int}
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.stocks.tradier_client import tradier_client
from app.common.candle_store import CandleStore, TF_MINUTES

logger = logging.getLogger(__name__)

_PENDING_REFRESH_REQUESTS: dict[tuple[str, str], float] = {}

_ET = ZoneInfo("America/New_York")

# Calendar days to look back when backfilling each intraday timeframe.
# Sized to guarantee >= 60 bars even accounting for weekends and holidays.
_TF_LOOKBACK_DAYS: dict[str, int] = {
    "1m":  3,    # ~780 bars across 2 trading sessions
    "5m":  5,    # ~390 bars across ~5 sessions
    "15m": 10,   # ~260 bars across ~5 sessions
}
_DAILY_LOOKBACK_DAYS = 150   # well beyond the 55-bar max any strategy needs


def _parse_et_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T", 1)):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_ET)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _drop_incomplete_timesales(candles: list[dict], interval_minutes: int) -> list[dict]:
    if len(candles) < 2:
        return candles
    bar_time = _parse_et_timestamp(str(candles[-1].get("time", "")))
    if bar_time is None:
        return candles
    # Derive actual close time from last candle; if it's in the future we drop it
    if bar_time.timestamp() + interval_minutes * 60 > datetime.now(timezone.utc).timestamp():
        return candles[:-1]
    return candles


def _ts_start(calendar_days: int) -> str:
    """ISO datetime string N calendar days before now (ET), for timesales start."""
    d = datetime.now(_ET) - timedelta(days=calendar_days)
    return d.strftime("%Y-%m-%d %H:%M")


def _session_start() -> str:
    now_et = datetime.now(_ET)
    return now_et.replace(hour=8, minute=40, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M")


def _normalize_timesales(raw: list) -> list[dict]:
    out = []
    for c in raw:
        try:
            out.append({
                "time":   str(c.get("time",   "")),
                "open":   float(c.get("open",   0)),
                "high":   float(c.get("high",   0)),
                "low":    float(c.get("low",    0)),
                "close":  float(c.get("close",  0)),
                "volume": int(c.get("volume",  0)),
            })
        except (TypeError, ValueError):
            continue
    return out


def _normalize_history(raw: list) -> list[dict]:
    out = []
    for d in raw:
        try:
            out.append({
                "time":   str(d.get("date",   "")),
                "open":   float(d.get("open",   0)),
                "high":   float(d.get("high",   0)),
                "low":    float(d.get("low",    0)),
                "close":  float(d.get("close",  0)),
                "volume": int(d.get("volume",  0)),
            })
        except (TypeError, ValueError):
            continue
    return out


class StockCandleFetcher:
    """Fetches and stores multi-timeframe OHLCV candles for stock symbols."""

    TIMEFRAMES = ["1m", "5m", "15m", "daily"]

    # Pause between consecutive Tradier requests to respect rate limits
    _RATE_PAUSE = 0.4

    def __init__(self, store: CandleStore):
        self.store = store
        self._active_fetches: dict[tuple[str, str], asyncio.Lock] = {}
        self._last_fetch_close_ts: dict[tuple[str, str], float] = {}

    def _current_close_ts(self, interval_minutes: int) -> float:
        now_ts = datetime.now(timezone.utc).timestamp()
        iv_sec = interval_minutes * 60
        return (now_ts // iv_sec) * iv_sec

    async def _fetch_once(self, symbol: str, tf: str) -> list[dict]:
        key = (symbol, tf)
        interval_minutes = TF_MINUTES[tf]
        current_close_ts = self._current_close_ts(interval_minutes)

        if self._last_fetch_close_ts.get(key, 0.0) >= current_close_ts:
            return []

        lock = self._active_fetches.setdefault(key, asyncio.Lock())
        if lock.locked():
            return []

        async with lock:
            if self._last_fetch_close_ts.get(key, 0.0) >= current_close_ts:
                return []

            candles = await self._fetch(symbol, tf)
            if candles:
                await self.store.update(symbol, interval_minutes, candles)
            self._last_fetch_close_ts[key] = current_close_ts
            return candles

    async def backfill(self, symbol: str) -> None:
        """Fetch enough history on every timeframe.  Called once per symbol during pre-market."""
        self._backfill_mode = True
        try:
            for tf in self.TIMEFRAMES:
                try:
                    candles = await self._fetch_once(symbol, tf)
                    if candles:
                        logger.info("Backfill %s @%s: %d bars", symbol, tf, len(candles))
                    await asyncio.sleep(self._RATE_PAUSE)
                except Exception as exc:
                    logger.warning("Backfill failed %s @%s: %s", symbol, tf, exc)
        finally:
            self._backfill_mode = False

    async def refresh_if_needed(self, symbol: str) -> list[str]:
        """Refresh timeframes whose candle has just closed (20 s gate).  Returns refreshed TF list."""
        refreshed = []
        prioritized = [tf for tf in self.TIMEFRAMES if _has_pending_refresh(symbol, tf)]
        ordered = prioritized + [tf for tf in self.TIMEFRAMES if tf not in prioritized]
        for tf in ordered:
            iv = TF_MINUTES[tf]
            if not self.store.needs_refresh(symbol, iv):
                continue
            try:
                candles = await self._fetch_once(symbol, tf)
                if candles:
                    refreshed.append(tf)
                    _clear_pending_refresh(symbol, tf)
                await asyncio.sleep(self._RATE_PAUSE)
            except Exception as exc:
                logger.warning("Refresh failed %s @%s: %s", symbol, tf, exc)
        return refreshed

    async def _fetch(self, symbol: str, tf: str) -> list[dict]:
        if tf == "daily":
            start = (datetime.now(_ET) - timedelta(days=_DAILY_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
            raw = await tradier_client.get_history(symbol, interval="daily", start=start)
            return _normalize_history(raw)
        # Intraday: "1m" → "1min", "5m" → "5min", "15m" → "15min"
        ts_interval = tf[:-1] + "min"
        raw = await tradier_client.get_timesales(
            symbol,
            interval=ts_interval,
            start=_session_start() if getattr(self, "_backfill_mode", False) else _ts_start(_TF_LOOKBACK_DAYS[tf]),
        )
        candles = _normalize_timesales(raw)
        return _drop_incomplete_timesales(candles, TF_MINUTES[tf])


def request_refresh(symbol: str, timeframe: str) -> None:
    _PENDING_REFRESH_REQUESTS[(symbol, timeframe)] = datetime.now(timezone.utc).timestamp()


def _has_pending_refresh(symbol: str, timeframe: str) -> bool:
    return (symbol, timeframe) in _PENDING_REFRESH_REQUESTS


def _clear_pending_refresh(symbol: str, timeframe: str) -> None:
    _PENDING_REFRESH_REQUESTS.pop((symbol, timeframe), None)
