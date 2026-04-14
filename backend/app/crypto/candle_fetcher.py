"""crypto/candle_fetcher.py — Fetch multi-timeframe OHLCV from Kraken.

Kraken native intervals (minutes): 1, 5, 15, 30, 60, 240, 1440
Bot uses:                              15,     60, 240, 1440

Kraken's public REST API is rate-limited to roughly 1 request/second,
so a 1.1 s pause is inserted between consecutive calls.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from app.crypto.kraken_client import kraken_client
from app.common.candle_store import CandleStore, TF_MINUTES
from app.common.symbols import canonical_symbol

logger = logging.getLogger(__name__)

_PENDING_REFRESH_REQUESTS: dict[tuple[str, str], float] = {}


def _drop_incomplete_ohlcv(candles: list[list], interval_minutes: int) -> list[list]:
    if len(candles) < 2:
        return candles
    try:
        bar_open_ts = float(candles[-1][0])
    except (TypeError, ValueError, IndexError):
        return candles
    if bar_open_ts + interval_minutes * 60 > datetime.now(timezone.utc).timestamp():
        return candles[:-1]
    return candles


class CryptoCandleFetcher:
    """Fetches and stores multi-timeframe OHLCV candles for crypto pairs."""

    TIMEFRAMES = ["15m", "1H", "4H", "daily"]

    _RATE_PAUSE = 1.1   # Kraken public API: ~1 req/sec

    def __init__(self, store: CandleStore):
        self.store = store
        self._active_fetches: dict[tuple[str, str], asyncio.Lock] = {}
        self._last_fetch_close_ts: dict[tuple[str, str], float] = {}

    def _current_close_ts(self, interval_minutes: int) -> float:
        now_ts = datetime.now(timezone.utc).timestamp()
        iv_sec = interval_minutes * 60
        return (now_ts // iv_sec) * iv_sec

    async def _fetch_once(self, symbol: str, tf: str) -> list[list]:
        can = canonical_symbol(symbol, asset_class="crypto")
        key = (can, tf)
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

            candles = await self._fetch(can, tf)
            if candles:
                await self.store.update(can, interval_minutes, candles)
            self._last_fetch_close_ts[key] = current_close_ts
            return candles

    async def backfill(self, symbol: str) -> None:
        """Fetch all timeframes for this symbol.  Called once per symbol at startup."""
        for tf in self.TIMEFRAMES:
            try:
                candles = await self._fetch_once(symbol, tf)
                if candles:
                    logger.info("Backfill %s @%s: %d bars", canonical_symbol(symbol, asset_class="crypto"), tf, len(candles))
                await asyncio.sleep(self._RATE_PAUSE)
            except Exception as exc:
                logger.warning("Backfill failed %s @%s: %s", canonical_symbol(symbol, asset_class="crypto"), tf, exc)

    async def refresh_if_needed(self, symbol: str) -> list[str]:
        """Refresh any timeframe whose candle has just closed (20 s gate)."""
        refreshed = []
        can = canonical_symbol(symbol, asset_class="crypto")
        prioritized = [tf for tf in self.TIMEFRAMES if _has_pending_refresh(can, tf)]
        ordered = prioritized + [tf for tf in self.TIMEFRAMES if tf not in prioritized]
        for tf in ordered:
            iv = TF_MINUTES[tf]
            if not self.store.needs_refresh(can, iv):
                continue
            try:
                candles = await self._fetch_once(symbol, tf)
                if candles:
                    refreshed.append(tf)
                    _clear_pending_refresh(can, tf)
                await asyncio.sleep(self._RATE_PAUSE)
            except Exception as exc:
                logger.warning("Refresh failed %s @%s: %s", can, tf, exc)
        return refreshed

    async def _fetch(self, symbol: str, tf: str) -> list[list]:
        interval = TF_MINUTES[tf]
        candles = await kraken_client.get_ohlcv(symbol, interval=interval)
        return _drop_incomplete_ohlcv(candles, interval)


def request_refresh(symbol: str, timeframe: str) -> None:
    can = canonical_symbol(symbol, asset_class="crypto")
    _PENDING_REFRESH_REQUESTS[(can, timeframe)] = datetime.now(timezone.utc).timestamp()


def _has_pending_refresh(symbol: str, timeframe: str) -> bool:
    can = canonical_symbol(symbol, asset_class="crypto")
    return (can, timeframe) in _PENDING_REFRESH_REQUESTS


def _clear_pending_refresh(symbol: str, timeframe: str) -> None:
    can = canonical_symbol(symbol, asset_class="crypto")
    _PENDING_REFRESH_REQUESTS.pop((can, timeframe), None)
