from types import SimpleNamespace
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.api.routes import monitoring as monitoring_route
from app.api.routes.monitoring import _select_top_signal, _strategy_key, get_monitoring_candidates
from app.crypto.monitoring import CryptoMonitor, _select_top_signal as crypto_select_top_signal
from app.stocks.monitoring import StockMonitor, _select_top_signal as stock_select_top_signal
from tests.conftest import make_bar, make_candle, trending_down_ohlcv, trending_up_history, trending_up_ohlcv


def test_strategy_key_normalizes_labels_and_keys():
    assert _strategy_key("Pullback Reclaim") == "pullback_reclaim"
    assert _strategy_key("trend_continuation") == "trend_continuation"


def test_select_top_signal_prefers_backend_top_strategy():
    first = SimpleNamespace(strategy="pullback_reclaim", strategy_key="pullback_reclaim", confidence=0.91)
    second = SimpleNamespace(strategy="trend_continuation", strategy_key="trend_continuation", confidence=0.73)

    selected = _select_top_signal([first, second], "trend_continuation")

    assert selected is second


def test_select_top_signal_falls_back_to_first_signal_when_backend_top_strategy_missing():
    first = SimpleNamespace(strategy="pullback_reclaim", strategy_key="pullback_reclaim", confidence=0.91)
    second = SimpleNamespace(strategy="trend_continuation", strategy_key="trend_continuation", confidence=0.73)

    selected = _select_top_signal([first, second], None)

    assert selected is first


def test_crypto_select_top_signal_prefers_backend_top_strategy():
    first = SimpleNamespace(strategy="pullback_reclaim", strategy_key="pullback_reclaim", confidence=0.91)
    second = SimpleNamespace(strategy="trend_continuation", strategy_key="trend_continuation", confidence=0.73)

    selected = crypto_select_top_signal({"signals": [first, second], "top_strategy": "trend_continuation"})

    assert selected is second


def test_stock_select_top_signal_prefers_backend_top_strategy():
    first = SimpleNamespace(strategy="pullback_reclaim", strategy_key="pullback_reclaim", confidence=0.91)
    second = SimpleNamespace(strategy="trend_continuation", strategy_key="trend_continuation", confidence=0.73)

    selected = stock_select_top_signal({"signals": [first, second], "top_strategy": "trend_continuation"})

    assert selected is second


def test_crypto_select_top_signal_falls_back_to_first_signal_when_backend_metadata_missing():
    first = SimpleNamespace(strategy="pullback_reclaim", strategy_key="pullback_reclaim", confidence=0.91)
    second = SimpleNamespace(strategy="trend_continuation", strategy_key="trend_continuation", confidence=0.73)

    selected = crypto_select_top_signal({"signals": [first, second]})

    assert selected is first


def test_stock_select_top_signal_falls_back_to_first_signal_when_backend_metadata_missing():
    first = SimpleNamespace(strategy="pullback_reclaim", strategy_key="pullback_reclaim", confidence=0.91)
    second = SimpleNamespace(strategy="trend_continuation", strategy_key="trend_continuation", confidence=0.73)

    selected = stock_select_top_signal({"signals": [first, second]})

    assert selected is first


@pytest.mark.asyncio
async def test_stock_monitor_uses_backend_top_strategy_for_execution(monkeypatch):
    monitor = StockMonitor()
    db = AsyncMock()
    ws = SimpleNamespace(symbol="AAPL", added_at=None)
    first = SimpleNamespace(strategy="pullback_reclaim", strategy_key="pullback_reclaim", confidence=0.91)
    second = SimpleNamespace(strategy="trend_continuation", strategy_key="trend_continuation", confidence=0.73)

    monkeypatch.setattr("app.stocks.monitoring.evaluate_all", lambda *args, **kwargs: {"signals": [first, second], "top_strategy": "trend_continuation", "top_confidence": 0.73})
    monkeypatch.setattr("app.stocks.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.stocks.monitoring.can_enter_trade", lambda: True)
    monkeypatch.setattr("app.stocks.monitoring.get_redis", AsyncMock(return_value=SimpleNamespace(exists=AsyncMock(return_value=False))))
    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    create_position = AsyncMock()
    monkeypatch.setattr(monitor, "_create_position", create_position)
    monkeypatch.setattr("app.stocks.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr(monitor._store, "latest_close_ts", lambda *args, **kwargs: 100.0)
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: {})
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: [])

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 1
    assert create_position.await_args.args[2] is second


@pytest.mark.asyncio
async def test_monitoring_route_reuses_cached_diagnostics_for_same_trigger_candle(monkeypatch):
    monitoring_route._EVAL_CACHE.clear()

    ws = SimpleNamespace(
        symbol="AAPL",
        asset_class="stock",
        state="active",
        added_at=None,
        watchlist_source_id=None,
    )
    def _db():
        symbols_result = MagicMock()
        symbols_result.scalars.return_value.all.return_value = [ws]
        open_position_result = MagicMock()
        open_position_result.first.return_value = None
        open_position_result.scalar_one.return_value = 0
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[symbols_result, open_position_result, open_position_result])
        return db

    signal = SimpleNamespace(
        strategy="pullback_reclaim",
        strategy_key="pullback_reclaim",
        confidence=0.88,
        entry_price=100.0,
        initial_stop=95.0,
        profit_target_1=105.0,
        profit_target_2=110.0,
        regime="neutral",
        notes="cached",
    )
    evaluate_all = MagicMock(return_value={"signals": [signal], "top_strategy": "pullback_reclaim", "top_confidence": 0.88})
    monkeypatch.setattr("app.stocks.strategies.entry_strategies.evaluate_all", evaluate_all)
    monkeypatch.setattr("app.stocks.tradier_client.tradier_client.get_timesales", AsyncMock(return_value=[
        {"time": datetime(2026, 4, 11, 9, 30, tzinfo=timezone.utc).isoformat(), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100},
        {"time": datetime(2026, 4, 11, 9, 35, tzinfo=timezone.utc).isoformat(), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100},
        {"time": datetime(2026, 4, 11, 9, 40, tzinfo=timezone.utc).isoformat(), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100},
    ]))
    monkeypatch.setattr("app.stocks.tradier_client.tradier_client.get_history", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.api.routes.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.api.routes.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr("app.api.routes.monitoring.get_redis", AsyncMock(return_value=SimpleNamespace(exists=AsyncMock(return_value=False))))

    first = await get_monitoring_candidates(asset_class="stock", db=_db())
    second = await get_monitoring_candidates(asset_class="stock", db=_db())

    assert first["total"] == 1
    assert second["total"] == 1
    assert evaluate_all.call_count == 1


@pytest.mark.asyncio
async def test_stock_monitor_evaluates_once_per_new_5m_trigger_candle(monkeypatch):
    monitor = StockMonitor()
    db = AsyncMock()
    ws = SimpleNamespace(symbol="AAPL", added_at=None)
    signal = SimpleNamespace(
        strategy="pullback_reclaim",
        strategy_key="pullback_reclaim",
        confidence=0.91,
        entry_price=100.0,
        initial_stop=95.0,
        profit_target_1=105.0,
        profit_target_2=110.0,
        max_hold_hours=24,
        regime="neutral",
    )

    current_ts = {"value": 100.0}
    evaluate_all = MagicMock(return_value={"signals": [signal], "top_strategy": "pullback_reclaim", "top_confidence": 0.91})
    monkeypatch.setattr("app.stocks.monitoring.evaluate_all", evaluate_all)
    monkeypatch.setattr("app.stocks.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.stocks.monitoring.can_enter_trade", lambda: True)
    monkeypatch.setattr("app.stocks.monitoring.get_redis", AsyncMock(return_value=SimpleNamespace(exists=AsyncMock(return_value=False))))
    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    monkeypatch.setattr(monitor, "_create_position", AsyncMock())
    monkeypatch.setattr("app.stocks.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr(monitor._store, "latest_close_ts", lambda *args, **kwargs: current_ts["value"])
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: {"last_close_ts": current_ts["value"]})
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: [])

    await monitor._evaluate_symbol(db, ws)
    await monitor._evaluate_symbol(db, ws)

    current_ts["value"] = 200.0
    await monitor._evaluate_symbol(db, ws)

    assert evaluate_all.call_count == 2
    assert monitor._create_position.await_count == 2


@pytest.mark.asyncio
async def test_stock_monitor_blocks_overextended_opening_range_breakout(monkeypatch):
    monitor = StockMonitor()
    db = AsyncMock()
    ws = SimpleNamespace(symbol="AAPL", added_at=None)
    signal = SimpleNamespace(
        strategy="Opening Range Breakout",
        strategy_key="opening_range_breakout",
        confidence=0.92,
        reasoning={"opening_range_high": 110.0, "recent_high_20": 110.0},
    )

    monkeypatch.setattr(
        "app.stocks.monitoring.evaluate_all",
        lambda *args, **kwargs: {"signals": [signal], "top_strategy": "opening_range_breakout", "top_confidence": 0.92},
    )
    monkeypatch.setattr("app.stocks.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.stocks.monitoring.can_enter_trade", lambda: True)
    monkeypatch.setattr("app.stocks.monitoring.get_redis", AsyncMock(return_value=SimpleNamespace(exists=AsyncMock(return_value=False))))
    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    create_position = AsyncMock()
    monkeypatch.setattr(monitor, "_create_position", create_position)
    monkeypatch.setattr("app.stocks.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr(monitor._store, "latest_close_ts", lambda *args, **kwargs: 100.0)
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: {})
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: trending_up_history(20, start=100.0, end=140.0))

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 0


@pytest.mark.asyncio
async def test_stock_monitor_caps_volatility_compression_breakout_before_execution(monkeypatch):
    monitor = StockMonitor()
    db = AsyncMock()
    ws = SimpleNamespace(symbol="AAPL", added_at=None)
    signal = SimpleNamespace(
        strategy="Volatility Compression Breakout",
        strategy_key="volatility_compression_breakout",
        confidence=0.92,
        reasoning={"compression_high_10": 105.0, "compression_low_10": 98.0},
    )

    captured = {}

    monkeypatch.setattr(
        "app.stocks.monitoring.evaluate_all",
        lambda *args, **kwargs: {"signals": [signal], "top_strategy": "volatility_compression_breakout", "top_confidence": 0.92},
    )
    monkeypatch.setattr("app.stocks.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.stocks.monitoring.can_enter_trade", lambda: True)
    monkeypatch.setattr("app.stocks.monitoring.get_redis", AsyncMock(return_value=SimpleNamespace(exists=AsyncMock(return_value=False))))
    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    create_position = AsyncMock()
    monkeypatch.setattr(monitor, "_create_position", create_position)
    monkeypatch.setattr(
        "app.stocks.monitoring.regime_engine.can_open",
        lambda *args, **kwargs: (captured.setdefault("confidence", args[2]), (True, None))[1],
    )
    monkeypatch.setattr(monitor._store, "latest_close_ts", lambda *args, **kwargs: 100.0)
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: {})
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: trending_up_history(20, start=100.0, end=107.0))

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 1
    assert captured["confidence"] == pytest.approx(0.64)


@pytest.mark.asyncio
async def test_stock_monitor_blocks_trend_continuation_when_fast_support_fails(monkeypatch):
    monitor = StockMonitor()
    db = AsyncMock()
    ws = SimpleNamespace(symbol="AAPL", added_at=None)
    signal = SimpleNamespace(
        strategy="Trend Continuation Ladder",
        strategy_key="trend_continuation",
        confidence=0.92,
        reasoning={},
    )

    evaluate_all = MagicMock(return_value={"signals": [signal], "top_strategy": "trend_continuation", "top_confidence": 0.92})
    monkeypatch.setattr("app.stocks.monitoring.evaluate_all", evaluate_all)
    monkeypatch.setattr("app.stocks.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.stocks.monitoring.can_enter_trade", lambda: True)
    monkeypatch.setattr("app.stocks.monitoring.get_redis", AsyncMock(return_value=SimpleNamespace(exists=AsyncMock(return_value=False))))
    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    create_position = AsyncMock()
    monkeypatch.setattr(monitor, "_create_position", create_position)
    can_open = MagicMock(return_value=(True, None))
    monkeypatch.setattr("app.stocks.monitoring.regime_engine.can_open", can_open)
    monkeypatch.setattr(monitor._store, "latest_close_ts", lambda *args, **kwargs: 100.0)
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: {})
    candles = trending_up_history(20, start=100.0, end=110.0)
    candles[-1] = make_bar(100.0)
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: candles)

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 0
    assert can_open.call_count == 0


@pytest.mark.asyncio
async def test_crypto_monitor_evaluates_once_per_new_15m_trigger_candle(monkeypatch):
    monitor = CryptoMonitor()
    db = AsyncMock()
    ws = SimpleNamespace(symbol="BTC/USD", added_at=None)
    signal = SimpleNamespace(
        strategy="trend_continuation",
        strategy_key="trend_continuation",
        confidence=0.91,
        reasoning={"execution_ready": True, "execution_confidence_cap": 0.91, "execution_block_reason": None},
    )

    current_ts = {"value": 100.0}
    evaluate_all = MagicMock(return_value={"signals": [signal], "top_strategy": "trend_continuation", "top_confidence": 0.91})
    monkeypatch.setattr("app.crypto.monitoring.evaluate_all", evaluate_all)
    monkeypatch.setattr("app.crypto.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "app.crypto.monitoring.get_redis",
        AsyncMock(return_value=SimpleNamespace(setnx=AsyncMock(return_value=True), expire=AsyncMock(), exists=AsyncMock(return_value=False), delete=AsyncMock())),
    )
    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    monkeypatch.setattr(monitor, "_create_position", AsyncMock())
    monkeypatch.setattr("app.crypto.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr(monitor._store, "latest_close_ts", lambda *args, **kwargs: current_ts["value"])
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: {"last_close_ts": current_ts["value"]})
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: trending_up_ohlcv(30, start=100.0, end=120.0))

    await monitor._evaluate_symbol(db, ws)
    await monitor._evaluate_symbol(db, ws)

    current_ts["value"] = 200.0
    await monitor._evaluate_symbol(db, ws)

    assert evaluate_all.call_count == 2
    assert monitor._create_position.await_count == 2


@pytest.mark.asyncio
async def test_crypto_monitor_blocks_breakout_retest_when_lower_timeframe_reclaim_is_unresolved(monkeypatch):
    monitor = CryptoMonitor()
    db = AsyncMock()
    ws = SimpleNamespace(symbol="BTC/USD", added_at=None)
    signal = SimpleNamespace(
        strategy="breakout_retest",
        strategy_key="breakout_retest",
        confidence=0.91,
        reasoning={"execution_ready": True, "execution_confidence_cap": 0.91, "execution_block_reason": None},
    )

    monkeypatch.setattr(
        "app.crypto.monitoring.evaluate_all",
        lambda *args, **kwargs: {"signals": [signal], "top_strategy": "breakout_retest", "top_confidence": 0.91},
    )
    monkeypatch.setattr("app.crypto.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "app.crypto.monitoring.get_redis",
        AsyncMock(return_value=SimpleNamespace(setnx=AsyncMock(return_value=True), expire=AsyncMock(), exists=AsyncMock(return_value=False), delete=AsyncMock())),
    )
    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    create_position = AsyncMock()
    monkeypatch.setattr(monitor, "_create_position", create_position)
    monkeypatch.setattr("app.crypto.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr(monitor._store, "latest_close_ts", lambda *args, **kwargs: 100.0)
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: {})
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: trending_down_ohlcv(30, start=120.0, end=90.0))

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 0


@pytest.mark.asyncio
async def test_crypto_monitor_caps_pullback_reclaim_until_true_reclaim_confirmed(monkeypatch):
    monitor = CryptoMonitor()
    db = AsyncMock()
    ws = SimpleNamespace(symbol="ETH/USD", added_at=None)
    signal = SimpleNamespace(
        strategy="pullback_reclaim",
        strategy_key="pullback_reclaim",
        confidence=0.92,
        reasoning={"execution_ready": True, "execution_confidence_cap": 0.92, "execution_block_reason": None},
    )

    monkeypatch.setattr(
        "app.crypto.monitoring.evaluate_all",
        lambda *args, **kwargs: {"signals": [signal], "top_strategy": "pullback_reclaim", "top_confidence": 0.92},
    )
    monkeypatch.setattr("app.crypto.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "app.crypto.monitoring.get_redis",
        AsyncMock(return_value=SimpleNamespace(setnx=AsyncMock(return_value=True), expire=AsyncMock(), exists=AsyncMock(return_value=False), delete=AsyncMock())),
    )
    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    create_position = AsyncMock()
    monkeypatch.setattr(monitor, "_create_position", create_position)
    monkeypatch.setattr("app.crypto.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr(monitor._store, "latest_close_ts", lambda *args, **kwargs: 100.0)
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: {})

    pullback = trending_up_ohlcv(30, start=100.0, end=110.0)
    pullback[-2] = make_candle(28, 103.0)
    pullback[-1] = make_candle(29, 109.5)
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: pullback)

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 1
    assert create_position.await_args.args[2].confidence == pytest.approx(0.72)


@pytest.mark.asyncio
async def test_crypto_monitor_blocks_momentum_breakout_when_follow_through_fails(monkeypatch):
    monitor = CryptoMonitor()
    db = AsyncMock()
    ws = SimpleNamespace(symbol="SOL/USD", added_at=None)
    signal = SimpleNamespace(
        strategy="Momentum Breakout Continuation",
        strategy_key="trend_continuation",
        confidence=0.94,
        reasoning={"execution_ready": True, "execution_confidence_cap": 0.94, "execution_block_reason": None},
    )

    monkeypatch.setattr(
        "app.crypto.monitoring.evaluate_all",
        lambda *args, **kwargs: {"signals": [signal], "top_strategy": "trend_continuation", "top_confidence": 0.94},
    )
    monkeypatch.setattr("app.crypto.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "app.crypto.monitoring.get_redis",
        AsyncMock(return_value=SimpleNamespace(setnx=AsyncMock(return_value=True), expire=AsyncMock(), exists=AsyncMock(return_value=False), delete=AsyncMock())),
    )
    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    create_position = AsyncMock()
    monkeypatch.setattr(monitor, "_create_position", create_position)
    monkeypatch.setattr("app.crypto.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: {})

    failed_follow_through = trending_up_ohlcv(30, start=100.0, end=125.0)
    failed_follow_through[-2] = make_candle(28, 124.0)
    failed_follow_through[-1] = make_candle(29, 121.0)
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: failed_follow_through)

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 0


@pytest.mark.asyncio
async def test_crypto_monitor_uses_backend_top_strategy_for_execution(monkeypatch):
    monitor = CryptoMonitor()
    db = AsyncMock()
    ws = SimpleNamespace(symbol="BTC/USD", added_at=None)
    first = SimpleNamespace(strategy="pullback_reclaim", strategy_key="pullback_reclaim", confidence=0.91)
    second = SimpleNamespace(strategy="trend_continuation", strategy_key="trend_continuation", confidence=0.73)

    monkeypatch.setattr("app.crypto.monitoring.evaluate_all", lambda *args, **kwargs: {"signals": [first, second], "top_strategy": "trend_continuation", "top_confidence": 0.73})
    monkeypatch.setattr("app.crypto.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.crypto.monitoring.get_redis", AsyncMock(return_value=SimpleNamespace(setnx=AsyncMock(return_value=True), expire=AsyncMock(), exists=AsyncMock(return_value=False), delete=AsyncMock())))
    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    create_position = AsyncMock()
    monkeypatch.setattr(monitor, "_create_position", create_position)
    monkeypatch.setattr("app.crypto.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr(monitor._store, "latest_close_ts", lambda *args, **kwargs: 100.0)
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: {})
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: [])

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 1
    assert create_position.await_args.args[2] is second
