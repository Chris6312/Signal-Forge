"""candle_store.py — Per-symbol, per-timeframe in-memory OHLCV cache.

Implements the "20 seconds after candle close" gate: a timeframe is only
considered stale (needs_refresh) once the previous candle has been closed for
at least FETCH_OFFSET_SECONDS, preventing partial-candle reads from the API.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Timeframe label → interval in minutes (shared across stock and crypto)
TF_MINUTES: dict[str, int] = {
    "1m":    1,
    "5m":    5,
    "15m":   15,
    "1H":    60,
    "4H":    240,
    "daily": 1440,
}

FETCH_OFFSET_SECONDS = 20   # wait this long after candle close before pulling


@dataclass
class _Frame:
    interval_minutes: int
    candles: list = field(default_factory=list)
    last_close_ts: float = 0.0   # Unix ts of the last complete candle's close


class CandleStore:
    """
    In-memory, asyncio-safe OHLCV cache keyed by (symbol, interval_minutes).
    One instance is created per asset-class monitor so workers are isolated.
    """

    def __init__(self):
        self._frames: dict[tuple[str, int], _Frame] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get(self, symbol: str, interval_minutes: int) -> list:
        """Return cached candles; empty list if not yet loaded."""
        frame = self._frames.get((symbol, interval_minutes))
        return frame.candles if frame else []

    async def update(self, symbol: str, interval_minutes: int, candles: list) -> None:
        """Replace cached candles and stamp the current candle-close timestamp."""
        if not candles:
            return
        now_ts = datetime.now(timezone.utc).timestamp()
        iv_sec = interval_minutes * 60
        last_close_ts = (now_ts // iv_sec) * iv_sec
        async with self._lock:
            key = (symbol, interval_minutes)
            frame = self._frames.get(key)
            if frame is None:
                frame = _Frame(interval_minutes=interval_minutes)
                self._frames[key] = frame
            frame.candles = candles
            frame.last_close_ts = last_close_ts

    def needs_refresh(self, symbol: str, interval_minutes: int) -> bool:
        """
        True when a new candle has closed at least FETCH_OFFSET_SECONDS ago
        and we haven't fetched it yet.
        """
        now_ts = datetime.now(timezone.utc).timestamp()
        iv_sec = interval_minutes * 60
        last_close_ts = (now_ts // iv_sec) * iv_sec   # close of last complete candle
        seconds_since_close = now_ts - last_close_ts

        if seconds_since_close < FETCH_OFFSET_SECONDS:
            return False

        frame = self._frames.get((symbol, interval_minutes))
        if frame is None or frame.last_close_ts == 0.0:
            return True   # never fetched

        return last_close_ts > frame.last_close_ts   # new candle closed since last fetch

    def is_loaded(self, symbol: str, interval_minutes: int) -> bool:
        """True if we have at least some candles cached for this (symbol, interval)."""
        frame = self._frames.get((symbol, interval_minutes))
        return bool(frame and frame.candles)

    def remove_symbol(self, symbol: str) -> None:
        """Drop all cached frames for a symbol (e.g. on watchlist removal)."""
        keys = [k for k in self._frames if k[0] == symbol]
        for k in keys:
            del self._frames[k]
