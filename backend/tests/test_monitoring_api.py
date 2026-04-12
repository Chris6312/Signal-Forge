from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

from app.api.routes.monitoring import _select_top_signal, _strategy_key
from app.crypto.monitoring import CryptoMonitor, _select_top_signal as crypto_select_top_signal
from app.stocks.monitoring import StockMonitor, _select_top_signal as stock_select_top_signal
from tests.conftest import make_candle, trending_down_ohlcv, trending_up_ohlcv


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
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: {})
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: [])

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 1
    assert create_position.await_args.args[2] is second


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
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: {})
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: [])

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 1
    assert create_position.await_args.args[2] is second
