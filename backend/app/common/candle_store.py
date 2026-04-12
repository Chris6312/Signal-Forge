"""candle_store.py — Per-symbol, per-timeframe in-memory OHLCV cache.

Implements the "20 seconds after candle close" gate: a timeframe is only
considered stale (needs_refresh) once the previous candle has been closed for
at least FETCH_OFFSET_SECONDS, preventing partial-candle reads from the API.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

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
    last_close_ts: float = 0.0   # Unix ts of the last complete candle's close (derived from data)
    last_ingested_ts: float = 0.0 # Unix ts when the frame was last refreshed by the bot
    sequence_ok: bool = True
    incomplete: bool = False
    last_time_raw: str | None = None


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
        # Normalize expectation
        iv_sec = interval_minutes * 60

        # Attempt to derive last close time from the provided candles.
        last_close_ts = 0.0
        last_time_raw = None
        try:
            last_item = candles[-1]
            # If candle is a dict with 'time' field (normalized form), parse it.
            if isinstance(last_item, dict) and 'time' in last_item:
                last_time_raw = str(last_item.get('time') or '')
                text = last_time_raw.strip().replace('Z', '+00:00')
                if ' ' in text and 'T' not in text:
                    text = text.replace(' ', 'T', 1)
                dt = datetime.fromisoformat(text)
                if len(text) == 10 and interval_minutes >= 1440:
                    dt = datetime.fromisoformat(text + 'T00:00+00:00')
                    last_close_ts = (dt + timedelta(seconds=iv_sec)).timestamp()
                else:
                    last_close_ts = dt.astimezone(timezone.utc).timestamp()
            # If candle is a list/tuple (exchange native), assume first element is open timestamp (unix or numeric string)
            elif isinstance(last_item, (list, tuple)) and len(last_item) > 0:
                try:
                    open_ts = float(last_item[0])
                    # close time = open + interval
                    last_close_ts = open_ts + iv_sec
                    last_time_raw = str(last_item[0])
                except Exception:
                    last_close_ts = 0.0
            else:
                last_close_ts = 0.0
        except Exception:
            last_close_ts = 0.0

        # Sequence and minimum-count validation
        sequence_ok = True
        min_count = 3 if interval_minutes < 1440 else 30
        try:
            if len(candles) < min_count:
                sequence_ok = False
            else:
                # Check monotonic increasing times and reasonable spacing
                prev_ts = None
                gaps = []
                for item in candles:
                    t = None
                    # dict-style candle with ISO `time`
                    if isinstance(item, dict) and 'time' in item:
                        text = str(item.get('time') or '').strip().replace('Z', '+00:00')
                        if ' ' in text and 'T' not in text:
                            text = text.replace(' ', 'T', 1)
                        try:
                            dt = datetime.fromisoformat(text)
                            t = dt.astimezone(timezone.utc).timestamp()
                        except Exception:
                            t = None
                    # list/tuple-style candle where index 0 is open timestamp
                    elif isinstance(item, (list, tuple)) and len(item) > 0:
                        try:
                            t = float(item[0])
                        except Exception:
                            t = None
                    if t is None:
                        sequence_ok = False
                        break
                    if prev_ts is not None:
                        gaps.append(t - prev_ts)
                    prev_ts = t
                if sequence_ok and gaps:
                    # Accept if median gap is within 25% of expected interval
                    gaps_sorted = sorted(gaps)
                    median_gap = gaps_sorted[len(gaps_sorted)//2]
                    if median_gap > iv_sec * 1.25 or median_gap < iv_sec * 0.75:
                        sequence_ok = False
        except Exception:
            sequence_ok = False

        async with self._lock:
            ingested_ts = datetime.now(timezone.utc).timestamp()
            key = (symbol, interval_minutes)
            frame = self._frames.get(key)
            if frame is None:
                frame = _Frame(interval_minutes=interval_minutes)
                self._frames[key] = frame
            frame.candles = candles
            frame.sequence_ok = sequence_ok
            frame.incomplete = not sequence_ok
            frame.last_time_raw = last_time_raw
            if last_close_ts:
                frame.last_close_ts = last_close_ts
            frame.last_ingested_ts = ingested_ts

    def needs_refresh(self, symbol: str, interval_minutes: int) -> bool:
        """
        True when a new candle has closed at least FETCH_OFFSET_SECONDS ago
        and we haven't fetched it yet.
        """
        now_ts = datetime.now(timezone.utc).timestamp()
        iv_sec = interval_minutes * 60

        # Compute the most recent closed candle boundary from wall-clock as a conservative gate
        last_wall_close = (now_ts // iv_sec) * iv_sec
        seconds_since_close = now_ts - last_wall_close
        if seconds_since_close < FETCH_OFFSET_SECONDS:
            return False

        frame = self._frames.get((symbol, interval_minutes))
        if frame is None or frame.last_close_ts == 0.0:
            return True   # never fetched

        # If our stored last_close_ts is older than the last_wall_close, signal refresh.
        # We rely on update() to stamp last_close_ts from actual returned candle close
        return last_wall_close > frame.last_close_ts

    def is_loaded(self, symbol: str, interval_minutes: int) -> bool:
        """True if we have at least some candles cached for this (symbol, interval)."""
        frame = self._frames.get((symbol, interval_minutes))
        return bool(frame and frame.candles)

    def remove_symbol(self, symbol: str) -> None:
        """Drop all cached frames for a symbol (e.g. on watchlist removal)."""
        keys = [k for k in self._frames if k[0] == symbol]
        for k in keys:
            del self._frames[k]

    def frame_info(self, symbol: str, interval_minutes: int) -> dict:
        """Return metadata about a cached frame for debugging/monitoring.

        Returns a dict with keys: count, sequence_ok, incomplete, last_time_raw,
        last_close_ts, last_ingested_ts.
        If no frame present, count==0 and incomplete==True.
        """
        frame = self._frames.get((symbol, interval_minutes))
        if not frame:
            return {
                "count": 0,
                "sequence_ok": False,
                "incomplete": True,
                "last_time_raw": None,
                "last_close_ts": 0.0,
                "last_ingested_ts": 0.0,
            }
        return {
            "count": len(frame.candles),
            "sequence_ok": bool(frame.sequence_ok),
            "incomplete": bool(frame.incomplete),
            "last_time_raw": frame.last_time_raw,
            "last_close_ts": frame.last_close_ts,
            "last_ingested_ts": frame.last_ingested_ts,
        }
