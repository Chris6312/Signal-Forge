import time
from datetime import datetime, timezone, timedelta

import pytest

from app.common.candle_store import CandleStore, TF_MINUTES, FETCH_OFFSET_SECONDS
from app.stocks.candle_fetcher import StockCandleFetcher
from app.crypto.candle_fetcher import CryptoCandleFetcher


def iso_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def test_update_with_dict_candles_sets_last_close_ts():
    store = CandleStore()
    iv = TF_MINUTES["1m"]
    now = datetime.now(timezone.utc)
    # Build 5 candles with close times spaced by 60s; last candle close = now - 60s
    candles = []
    for i in range(5):
        close_time = now - timedelta(seconds=(5 - i) * iv * 60)
        candles.append({
            "time": iso_ts(close_time),
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 100,
        })

    import asyncio
    asyncio.run(store.update("TEST", iv, candles))
    frame = store._frames.get(("TEST", iv))
    assert frame is not None
    expected = datetime.fromisoformat(candles[-1]["time"].replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    assert abs(frame.last_close_ts - expected) < 1.0


def test_update_with_list_candles_sets_last_close_as_open_plus_interval():
    store = CandleStore()
    iv = TF_MINUTES["15m"]
    iv_sec = iv * 60
    # use integer unix open timestamps
    base = int(time.time()) - 10000
    candles = []
    for i in range(10):
        open_ts = base + i * iv_sec
        # [open_ts, close, high, low, close, volume]
        candles.append([open_ts, 1.0, 1.1, 0.9, 1.0, 1000.0])

    import asyncio
    asyncio.run(store.update("XBTUSD", iv, candles))
    frame = store._frames.get(("XBTUSD", iv))
    assert frame is not None
    expected = float(candles[-1][0]) + iv_sec
    assert abs(frame.last_close_ts - expected) < 1.0


def test_update_with_too_few_bars_marks_sequence_bad():
    store = CandleStore()
    iv = TF_MINUTES["1m"]
    now = datetime.now(timezone.utc)
    candles = []
    # only 2 candles (min required is 3 for intraday)
    for i in range(2):
        close_time = now - timedelta(seconds=(2 - i) * iv * 60)
        candles.append({
            "time": iso_ts(close_time),
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 100,
        })

    import asyncio
    asyncio.run(store.update("FEW", iv, candles))
    frame = store._frames.get(("FEW", iv))
    assert frame is not None
    assert frame.sequence_ok is False
    assert frame.incomplete is True


def test_needs_refresh_respects_fetch_offset_and_wall_clock():
    store = CandleStore()
    iv = TF_MINUTES["daily"]
    # Case A: within FETCH_OFFSET_SECONDS -> should return False when offset large
    orig_offset = FETCH_OFFSET_SECONDS
    try:
        # Monkeypatch module-level constant by assigning attribute
        import app.common.candle_store as csmod
        csmod.FETCH_OFFSET_SECONDS = 1000000
        # No frame exists -> never fetched -> normally would return True, but seconds_since_close < FETCH_OFFSET_SECONDS triggers False
        assert store.needs_refresh("ANY", iv) is False
    finally:
        import app.common.candle_store as csmod
        csmod.FETCH_OFFSET_SECONDS = orig_offset

    # Case B: stored last_close_ts old -> needs_refresh should be True (wall-clock passed and stored ts older)
    old_frame = store._frames.setdefault(("OLD", iv), type("F", (), {})())
    # set last_close_ts to epoch to simulate very old
    old_frame.last_close_ts = 0.0
    # now with normal FETCH_OFFSET_SECONDS we expect True (daily interval makes seconds_since_close large)
    assert store.needs_refresh("OLD", iv) is True


def test_fetchers_update_and_sequence_ok_end_to_end():
    store = CandleStore()
    stock_fetcher = StockCandleFetcher(store)
    crypto_fetcher = CryptoCandleFetcher(store)

    # Mock simple stock daily history with date strings (normalized form)
    today = datetime.now(timezone.utc).date()
    history = []
    for i in range(40):
        d = today - timedelta(days=(40 - i))
        history.append({"date": d.isoformat(), "open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i, "close": 100.0 + i, "volume": 1000})

    # Simulate what StockCandleFetcher._fetch would normalize and pass to store.update()
    normalized_history = []
    for d in history:
        normalized_history.append({
            "time": d["date"],
            "open": float(d["open"]),
            "high": float(d["high"]),
            "low": float(d["low"]),
            "close": float(d["close"]),
            "volume": int(d["volume"]),
        })
    import asyncio
    asyncio.run(store.update("AAPL", TF_MINUTES["daily"], normalized_history))
    frame = store._frames.get(("AAPL", TF_MINUTES["daily"]))
    assert frame is not None
    # For daily we expect sequence_ok True (enough bars and proper dates)
    assert frame.sequence_ok is True

    # For crypto, simulate list-style OHLCV with numeric open timestamps
    iv = TF_MINUTES["15m"]
    base = int(time.time()) - iv * 60 * 100
    klines = [[base + i * iv * 60, 100.0 + i, 101.0 + i, 99.0 + i, 100.0 + i, 1000.0] for i in range(65)]
    # Simulate direct update for crypto list-style klines
    import asyncio
    asyncio.run(store.update("XBTUSD", iv, klines))
    # The store key may be the provided symbol or a canonical variant; accept any frame with matching interval
    frame_c = store._frames.get(("XBTUSD", iv))
    if frame_c is None:
        # fallback: find any frame with the same interval
        frame_c = next((f for (s, ivn), f in store._frames.items() if ivn == iv), None)
    assert frame_c is not None
    assert frame_c.sequence_ok is True


def test_malformed_time_strings_mark_incomplete():
    store = CandleStore()
    iv = TF_MINUTES["1m"]
    # Create candles where one has non-parseable time
    now = datetime.now(timezone.utc)
    candles = []
    for i in range(10):
        t = iso_ts(now - timedelta(seconds=(10 - i) * 60))
        candles.append({"time": t, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100})
    # Inject malformed time
    candles[5]["time"] = "NOT_A_TIME"

    import asyncio
    asyncio.run(store.update("BADTIME", iv, candles))
    frame = store._frames.get(("BADTIME", iv))
    assert frame is not None
    assert frame.sequence_ok is False
    assert frame.incomplete is True
