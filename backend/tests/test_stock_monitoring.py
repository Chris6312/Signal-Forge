from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.stocks.monitoring import StockMonitor


def _signal(strategy: str, strategy_key: str | None = None):
    return SimpleNamespace(strategy=strategy, strategy_key=strategy_key)


@pytest.mark.parametrize(
    ("strategy_key", "strategy", "expected_exit_strategy"),
    [
        ("opening_range_breakout", "Opening Range Breakout", "End-of-Day Exit"),
        ("trend_continuation", "Trend Continuation", "Partial at TP1, Trail Remainder"),
        ("volatility_compression_breakout", "Volatility Compression Breakout", "Partial at TP1, Trail Remainder"),
        ("mean_reversion_bounce", "Mean Reversion Bounce", "First Failed Follow-Through Exit"),
        ("pullback_reclaim", "Pullback Reclaim", "Fixed Risk then Break-Even Promotion"),
        ("failed_breakdown_reclaim", "Failed Breakdown Reclaim", "Fixed Risk then Break-Even Promotion"),
    ],
)
def test_stock_exit_strategy_selection_uses_canonical_strategy_key(strategy_key, strategy, expected_exit_strategy):
    monitor = StockMonitor()
    assert monitor._select_exit_strategy(_signal(strategy, strategy_key)) == expected_exit_strategy


def test_stock_exit_strategy_selection_ignores_human_readable_label_changes_when_key_is_stable():
    monitor = StockMonitor()
    assert monitor._select_exit_strategy(_signal("Renamed breakout label", "opening_range_breakout")) == "End-of-Day Exit"


def test_stock_exit_strategy_selection_uses_safe_fallback_for_unknown_labels():
    monitor = StockMonitor()
    assert monitor._select_exit_strategy(_signal("Legacy Strategy Label", "legacy_label")) == "Fixed Risk then Break-Even Promotion"


@pytest.mark.asyncio
async def test_stock_monitor_skips_zero_sized_execution(monkeypatch):
    monitor = StockMonitor()
    db = AsyncMock()
    ws = SimpleNamespace(symbol="XAUT/USD", added_at=None, watchlist_source_id=None)
    signal = SimpleNamespace(
        symbol="XAUT/USD",
        strategy="Pullback Reclaim",
        strategy_key="pullback_reclaim",
        entry_price=4600.0,
        initial_stop=4550.0,
        profit_target_1=4700.0,
        profit_target_2=4800.0,
        max_hold_hours=6,
        regime="trending_up",
        confidence=0.82,
        notes={},
        reasoning={},
    )

    monkeypatch.setattr("app.stocks.monitoring.runtime_state.get_trading_mode", AsyncMock(return_value="paper"))
    monkeypatch.setattr("app.stocks.monitoring.runtime_state.get_risk_per_trade_pct", AsyncMock(return_value=0.005))
    monkeypatch.setattr("app.common.paper_ledger.size_paper_position", AsyncMock(return_value=0.0))

    await monitor._create_position(db, ws, signal)

    assert db.add.call_count == 0
    assert db.flush.await_count == 0


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
