"""crypto/candle_fetcher.py — Fetch multi-timeframe OHLCV from Kraken.

Kraken native intervals (minutes): 1, 5, 15, 30, 60, 240, 1440
Bot uses:                              15,     60, 240, 1440

Kraken's public REST API is rate-limited to roughly 1 request/second,
so a 1.1 s pause is inserted between consecutive calls.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.crypto.kraken_client import kraken_client
from app.common.candle_store import CandleStore, TF_MINUTES
from app.common.symbols import canonical_symbol

logger = logging.getLogger(__name__)


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

    async def backfill(self, symbol: str) -> None:
        """Fetch all timeframes for this symbol.  Called once per symbol at startup."""
        can = canonical_symbol(symbol, asset_class="crypto")
        for tf in self.TIMEFRAMES:
            try:
                interval = TF_MINUTES[tf]
                candles = await kraken_client.get_ohlcv(can, interval=interval)
                candles = _drop_incomplete_ohlcv(candles, interval)
                if candles:
                    await self.store.update(can, interval, candles)
                    logger.info("Backfill %s @%s: %d bars", can, tf, len(candles))
                await asyncio.sleep(self._RATE_PAUSE)
            except Exception as exc:
                logger.warning("Backfill failed %s @%s: %s", can, tf, exc)

    async def refresh_if_needed(self, symbol: str) -> list[str]:
        """Refresh any timeframe whose candle has just closed (20 s gate)."""
        refreshed = []
        can = canonical_symbol(symbol, asset_class="crypto")
        for tf in self.TIMEFRAMES:
            iv = TF_MINUTES[tf]
            if not self.store.needs_refresh(can, iv):
                continue
            try:
                candles = await kraken_client.get_ohlcv(can, interval=iv)
                candles = _drop_incomplete_ohlcv(candles, iv)
                if candles:
                    await self.store.update(can, iv, candles)
                    refreshed.append(tf)
                await asyncio.sleep(self._RATE_PAUSE)
            except Exception as exc:
                logger.warning("Refresh failed %s @%s: %s", can, tf, exc)
        return refreshed
