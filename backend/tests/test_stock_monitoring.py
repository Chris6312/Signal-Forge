from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.stocks.monitoring import StockMonitor


@pytest.mark.asyncio
async def test_stock_monitor_acquires_intent_lock_and_creates_position(monkeypatch):
    monitor = StockMonitor()
    ws = SimpleNamespace(symbol="AAPL", added_at=None, watchlist_source_id=None)
    db = AsyncMock()
    signal = SimpleNamespace(
        strategy="Opening Range Breakout",
        entry_price=100.0,
        initial_stop=95.0,
        profit_target_1=105.0,
        profit_target_2=110.0,
        max_hold_hours=4,
        regime="trending_up",
        confidence=0.8,
        notes={},
        reasoning={},
    )
    redis = SimpleNamespace(setnx=AsyncMock(return_value=True), expire=AsyncMock(), delete=AsyncMock())

    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_should_evaluate_trigger", lambda symbol: True)
    monkeypatch.setattr(monitor._store, "frame_info", MagicMock(return_value={}))
    monkeypatch.setattr(monitor._store, "latest_close_ts", MagicMock(return_value=1.0))
    monkeypatch.setattr(monitor._store, "get", MagicMock(return_value=[]))
    monkeypatch.setattr("app.stocks.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.stocks.monitoring.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr("app.stocks.monitoring.evaluate_all", lambda *args, **kwargs: [signal])
    monkeypatch.setattr("app.stocks.monitoring._select_top_signal", lambda result: result[0])
    monkeypatch.setattr("app.stocks.monitoring._execution_readiness_adjustment", lambda *args, **kwargs: {"execution_ready": True, "confidence_cap": 1.0, "block_reason": None})
    monkeypatch.setattr("app.stocks.monitoring.runtime_state.stabilize_monitoring_readiness", lambda *args, **kwargs: {"execution_ready": True, "confidence_cap": 1.0, "block_reason": None})
    monkeypatch.setattr("app.stocks.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, "ok"))
    monkeypatch.setattr("app.stocks.monitoring.can_enter_trade", lambda: True)
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    create_position = AsyncMock()
    monkeypatch.setattr(monitor, "_create_position", create_position)

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 1
    assert redis.setnx.await_args.args[0] == "intent:stock:AAPL"
    assert redis.expire.await_args.args == ("intent:stock:AAPL", 60)
    assert redis.delete.await_args.args == ("intent:stock:AAPL",)


@pytest.mark.asyncio
async def test_stock_monitor_skips_duplicate_when_intent_lock_is_held(monkeypatch):
    monitor = StockMonitor()
    ws = SimpleNamespace(symbol="AAPL", added_at=None, watchlist_source_id=None)
    db = AsyncMock()
    signal = SimpleNamespace(
        strategy="Opening Range Breakout",
        entry_price=100.0,
        initial_stop=95.0,
        profit_target_1=105.0,
        profit_target_2=110.0,
        max_hold_hours=4,
        regime="trending_up",
        confidence=0.8,
        notes={},
        reasoning={},
    )
    redis = SimpleNamespace(setnx=AsyncMock(return_value=False), expire=AsyncMock(), delete=AsyncMock())

    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_should_evaluate_trigger", lambda symbol: True)
    monkeypatch.setattr(monitor._store, "frame_info", MagicMock(return_value={}))
    monkeypatch.setattr(monitor._store, "latest_close_ts", MagicMock(return_value=1.0))
    monkeypatch.setattr(monitor._store, "get", MagicMock(return_value=[]))
    monkeypatch.setattr("app.stocks.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.stocks.monitoring.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr("app.stocks.monitoring.evaluate_all", lambda *args, **kwargs: [signal])
    monkeypatch.setattr("app.stocks.monitoring._select_top_signal", lambda result: result[0])
    monkeypatch.setattr("app.stocks.monitoring._execution_readiness_adjustment", lambda *args, **kwargs: {"execution_ready": True, "confidence_cap": 1.0, "block_reason": None})
    monkeypatch.setattr("app.stocks.monitoring.runtime_state.stabilize_monitoring_readiness", lambda *args, **kwargs: {"execution_ready": True, "confidence_cap": 1.0, "block_reason": None})
    monkeypatch.setattr("app.stocks.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, "ok"))
    monkeypatch.setattr("app.stocks.monitoring.can_enter_trade", lambda: True)
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    create_position = AsyncMock()
    monkeypatch.setattr(monitor, "_create_position", create_position)

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 0
    assert redis.setnx.await_args.args[0] == "intent:stock:AAPL"
    assert redis.delete.await_count == 0


@pytest.mark.asyncio
async def test_stock_monitor_different_symbols_use_separate_intent_locks(monkeypatch):
    monitor = StockMonitor()
    db = AsyncMock()
    signal = SimpleNamespace(
        strategy="Opening Range Breakout",
        entry_price=100.0,
        initial_stop=95.0,
        profit_target_1=105.0,
        profit_target_2=110.0,
        max_hold_hours=4,
        regime="trending_up",
        confidence=0.8,
        notes={},
        reasoning={},
    )
    redis = SimpleNamespace(setnx=AsyncMock(return_value=True), expire=AsyncMock(), delete=AsyncMock())

    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_should_evaluate_trigger", lambda symbol: True)
    monkeypatch.setattr(monitor._store, "frame_info", MagicMock(return_value={}))
    monkeypatch.setattr(monitor._store, "latest_close_ts", MagicMock(return_value=1.0))
    monkeypatch.setattr(monitor._store, "get", MagicMock(return_value=[]))
    monkeypatch.setattr("app.stocks.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.stocks.monitoring.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr("app.stocks.monitoring.evaluate_all", lambda *args, **kwargs: [signal])
    monkeypatch.setattr("app.stocks.monitoring._select_top_signal", lambda result: result[0])
    monkeypatch.setattr("app.stocks.monitoring._execution_readiness_adjustment", lambda *args, **kwargs: {"execution_ready": True, "confidence_cap": 1.0, "block_reason": None})
    monkeypatch.setattr("app.stocks.monitoring.runtime_state.stabilize_monitoring_readiness", lambda *args, **kwargs: {"execution_ready": True, "confidence_cap": 1.0, "block_reason": None})
    monkeypatch.setattr("app.stocks.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, "ok"))
    monkeypatch.setattr("app.stocks.monitoring.can_enter_trade", lambda: True)
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    create_position = AsyncMock()
    monkeypatch.setattr(monitor, "_create_position", create_position)

    await monitor._evaluate_symbol(db, SimpleNamespace(symbol="AAPL", added_at=None, watchlist_source_id=None))
    await monitor._evaluate_symbol(db, SimpleNamespace(symbol="MSFT", added_at=None, watchlist_source_id=None))

    assert create_position.await_count == 2
    assert redis.setnx.await_args_list[0].args[0] == "intent:stock:AAPL"
    assert redis.setnx.await_args_list[1].args[0] == "intent:stock:MSFT"


@pytest.mark.asyncio
async def test_stock_monitor_continues_normal_flow_without_overlap(monkeypatch):
    monitor = StockMonitor()
    ws = SimpleNamespace(symbol="AAPL", added_at=None, watchlist_source_id=None)
    db = AsyncMock()
    signal = SimpleNamespace(
        strategy="Opening Range Breakout",
        entry_price=100.0,
        initial_stop=95.0,
        profit_target_1=105.0,
        profit_target_2=110.0,
        max_hold_hours=4,
        regime="trending_up",
        confidence=0.8,
        notes={},
        reasoning={},
    )
    redis = SimpleNamespace(setnx=AsyncMock(return_value=True), expire=AsyncMock(), delete=AsyncMock())

    monkeypatch.setattr(monitor, "_has_open_position", AsyncMock(return_value=False))
    monkeypatch.setattr(monitor, "_should_evaluate_trigger", lambda symbol: True)
    monkeypatch.setattr(monitor._store, "frame_info", MagicMock(return_value={}))
    monkeypatch.setattr(monitor._store, "latest_close_ts", MagicMock(return_value=1.0))
    monkeypatch.setattr(monitor._store, "get", MagicMock(return_value=[]))
    monkeypatch.setattr("app.stocks.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.stocks.monitoring.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr("app.stocks.monitoring.evaluate_all", lambda *args, **kwargs: [signal])
    monkeypatch.setattr("app.stocks.monitoring._select_top_signal", lambda result: result[0])
    monkeypatch.setattr("app.stocks.monitoring._execution_readiness_adjustment", lambda *args, **kwargs: {"execution_ready": True, "confidence_cap": 1.0, "block_reason": None})
    monkeypatch.setattr("app.stocks.monitoring.runtime_state.stabilize_monitoring_readiness", lambda *args, **kwargs: {"execution_ready": True, "confidence_cap": 1.0, "block_reason": None})
    monkeypatch.setattr("app.stocks.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, "ok"))
    monkeypatch.setattr("app.stocks.monitoring.can_enter_trade", lambda: True)
    monkeypatch.setattr(monitor, "_count_open_positions", AsyncMock(return_value=0))
    create_position = AsyncMock()
    monkeypatch.setattr(monitor, "_create_position", create_position)

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 1
    assert redis.setnx.await_count == 1
    assert redis.delete.await_count == 1
