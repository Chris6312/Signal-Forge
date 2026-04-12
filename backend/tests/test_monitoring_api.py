from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

from app.api.routes.monitoring import _select_top_signal, _strategy_key
from app.crypto.monitoring import CryptoMonitor, _select_top_signal as crypto_select_top_signal
from app.stocks.monitoring import StockMonitor, _select_top_signal as stock_select_top_signal


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
