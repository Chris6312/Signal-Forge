from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.api.routes import monitoring as monitoring_route
from app.api.routes.monitoring import _select_top_signal, _strategy_key, get_monitoring_candidates
from app.common.candle_store import CandleStore
from app.crypto.monitoring import CryptoMonitor, _select_top_signal as crypto_select_top_signal, _execution_readiness_adjustment as crypto_execution_readiness_adjustment
from app.stocks.monitoring import StockMonitor, _select_top_signal as stock_select_top_signal
from app.stocks.strategies.entry_strategies import _execution_readiness_adjustment as stock_execution_readiness_adjustment
from app.common.runtime_state import runtime_state
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


def _stock_candles(count: int, interval_minutes: int, start_price: float) -> list[dict]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    candles = []
    for index in range(count):
        ts = now - timedelta(minutes=interval_minutes * (count - index))
        candles.append({
            "time": ts.isoformat().replace("+00:00", "Z"),
            "open": start_price + index,
            "high": start_price + index + 1,
            "low": start_price + index - 1,
            "close": start_price + index + 0.5,
            "volume": 1000 + index,
        })
    return candles


@pytest.mark.asyncio
async def test_stock_monitoring_uses_candle_store_when_sufficient_bars_exist(monkeypatch):
    store = CandleStore()
    monkeypatch.setattr(monitoring_route, "_STOCK_CANDLE_STORE", store)
    monkeypatch.setattr(monitoring_route, "_STOCK_FETCHER", monitoring_route.StockCandleFetcher(store))

    ws = SimpleNamespace(
        symbol="AAPL",
        asset_class="stock",
        state=SimpleNamespace(name="ACTIVE"),
        added_at=datetime.now(timezone.utc) - timedelta(days=1),
        watchlist_source_id=None,
    )

    await store.update(ws.symbol, 5, _stock_candles(24, 5, 100.0))
    await store.update(ws.symbol, 15, _stock_candles(24, 15, 120.0))
    await store.update(ws.symbol, 1440, _stock_candles(24, 1440, 140.0))

    async def fake_evaluate_all(symbol, candles_by_tf, include_diagnostics=False, **kwargs):
        assert len(candles_by_tf["5m"]) >= 20
        assert len(candles_by_tf["15m"]) >= 20
        assert len(candles_by_tf["daily"]) >= 20
        signal = SimpleNamespace(
            strategy="pullback_reclaim",
            strategy_key="pullback_reclaim",
            entry_price=150.0,
            initial_stop=145.0,
            profit_target_1=155.0,
            profit_target_2=160.0,
            regime="bull",
            confidence=0.72,
            notes="ready",
        )
        return {
            "signals": [signal],
            "top_strategy": "pullback_reclaim",
            "top_confidence": 0.72,
            "evaluated_strategy_scores": {"pullback_reclaim": 0.72},
            "evaluated_strategies": {},
            "rejected_strategies": {},
            "feature_scores": {},
            "timestamp_evaluated": 1.0,
        }

    monkeypatch.setattr("app.stocks.strategies.entry_strategies.evaluate_all", fake_evaluate_all)
    monkeypatch.setattr(monitoring_route._STOCK_FETCHER, "backfill", AsyncMock(side_effect=AssertionError("backfill should not run when store already has enough candles")))
    monkeypatch.setattr(monitoring_route._STOCK_FETCHER, "refresh_if_needed", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.stocks.tradier_client.tradier_client.get_timesales", AsyncMock(side_effect=AssertionError("broker timesales should not be called")))
    monkeypatch.setattr("app.stocks.tradier_client.tradier_client.get_history", AsyncMock(side_effect=AssertionError("broker history should not be called")))

    watchlist_result = MagicMock()
    watchlist_result.scalars.return_value.all.return_value = [ws]
    position_result = MagicMock()
    position_result.first.return_value = None
    count_result = MagicMock()
    count_result.scalar_one.return_value = 0

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[watchlist_result, position_result, count_result])

    monkeypatch.setattr(monitoring_route, "get_redis", AsyncMock(return_value=SimpleNamespace(exists=AsyncMock(return_value=False))))
    monkeypatch.setattr(monitoring_route, "is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr(monitoring_route, "activation_ready_at", lambda *args, **kwargs: None)
    monkeypatch.setattr(monitoring_route.regime_engine, "can_open", lambda *args, **kwargs: (True, None))

    result = await get_monitoring_candidates(asset_class="stock", db=db)

    assert result["total"] == 1
    strategies = result["candidates"][0]["evaluation"]["strategies"]
    assert strategies[0]["confidence"] > 0
    assert result["candidates"][0]["top_confidence"] > 0


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


def _configure_crypto_monitor(monkeypatch, monitor, signals, top_strategy, top_confidence, *, latest_close_ts=100.0, frame_info=None, store_get_result=None):
    monkeypatch.setattr(
        "app.crypto.monitoring.evaluate_all",
        lambda *args, **kwargs: {"signals": signals, "top_strategy": top_strategy, "top_confidence": top_confidence},
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
    if latest_close_ts is not None:
        monkeypatch.setattr(monitor._store, "latest_close_ts", lambda *args, **kwargs: latest_close_ts)
    monkeypatch.setattr(monitor._store, "frame_info", lambda *args, **kwargs: frame_info or {})
    if store_get_result is not None:
        monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: store_get_result)
    return create_position


def test_readiness_memory_blocks_until_support_recovers_materially():
    runtime_state.clear_monitoring_readiness_memory()

    blocked = runtime_state.stabilize_monitoring_readiness(
        "stock",
        "AAPL",
        "trend_continuation",
        100.0,
        {"execution_ready": False, "confidence_cap": 0.5, "block_reason": "fast_support_lost_after_breakout"},
        {"close": 103.0, "current_vs_ema20": -1.5},
    )
    marginal = runtime_state.stabilize_monitoring_readiness(
        "stock",
        "AAPL",
        "trend_continuation",
        200.0,
        {"execution_ready": True, "confidence_cap": 0.9, "block_reason": None},
        {"close": 103.2, "current_vs_ema20": 0.1},
    )
    improved = runtime_state.stabilize_monitoring_readiness(
        "stock",
        "AAPL",
        "trend_continuation",
        300.0,
        {"execution_ready": True, "confidence_cap": 0.9, "block_reason": None},
        {"close": 106.0, "current_vs_ema20": 0.6},
    )

    assert blocked["execution_ready"] is False
    assert marginal["execution_ready"] is False
    assert marginal["block_reason"] == "fast_support_lost_after_breakout"
    assert improved["execution_ready"] is True


def test_readiness_memory_blocks_until_extension_contracts_enough():
    runtime_state.clear_monitoring_readiness_memory()

    blocked = runtime_state.stabilize_monitoring_readiness(
        "crypto",
        "BTC/USD",
        "trend_continuation",
        100.0,
        {"execution_ready": False, "confidence_cap": 0.6, "block_reason": "continuation_too_extended"},
        {"close": 120.0, "support_extension_pct": 5.0},
    )
    marginal = runtime_state.stabilize_monitoring_readiness(
        "crypto",
        "BTC/USD",
        "trend_continuation",
        200.0,
        {"execution_ready": True, "confidence_cap": 0.9, "block_reason": None},
        {"close": 118.5, "support_extension_pct": 4.7},
    )
    improved = runtime_state.stabilize_monitoring_readiness(
        "crypto",
        "BTC/USD",
        "trend_continuation",
        300.0,
        {"execution_ready": True, "confidence_cap": 0.9, "block_reason": None},
        {"close": 116.0, "support_extension_pct": 4.0},
    )

    assert blocked["execution_ready"] is False
    assert marginal["execution_ready"] is False
    assert marginal["block_reason"] == "continuation_too_extended"
    assert improved["execution_ready"] is True


def test_readiness_memory_resets_when_strategy_changes():
    runtime_state.clear_monitoring_readiness_memory()

    blocked = runtime_state.stabilize_monitoring_readiness(
        "stock",
        "AAPL",
        "trend_continuation",
        100.0,
        {"execution_ready": False, "confidence_cap": 0.5, "block_reason": "fast_support_lost_after_breakout"},
        {"close": 103.0, "current_vs_ema20": -1.0},
    )
    reset = runtime_state.stabilize_monitoring_readiness(
        "stock",
        "AAPL",
        "pullback_reclaim",
        200.0,
        {"execution_ready": True, "confidence_cap": 0.8, "block_reason": None},
        {"close": 104.5, "current_vs_ema20": 0.5, "reclaim_confirmed": True},
    )

    assert blocked["execution_ready"] is False
    assert reset["execution_ready"] is True


def test_readiness_memory_blocks_until_support_recovers_materially():
    runtime_state.clear_monitoring_readiness_memory()

    key = ("stock", "AAPL", "trend_continuation")
    blocked = runtime_state.stabilize_monitoring_readiness(
        key[0],
        key[1],
        key[2],
        100.0,
        {"execution_ready": False, "confidence_cap": 0.5, "block_reason": "fast_support_lost_after_breakout"},
        {"close": 103.0, "current_vs_ema20": -1.5},
    )
    marginal = runtime_state.stabilize_monitoring_readiness(
        key[0],
        key[1],
        key[2],
        200.0,
        {"execution_ready": True, "confidence_cap": 0.9, "block_reason": None},
        {"close": 103.2, "current_vs_ema20": 0.1},
    )
    improved = runtime_state.stabilize_monitoring_readiness(
        key[0],
        key[1],
        key[2],
        300.0,
        {"execution_ready": True, "confidence_cap": 0.9, "block_reason": None},
        {"close": 106.0, "current_vs_ema20": 0.6},
    )

    assert blocked["execution_ready"] is False
    assert marginal["execution_ready"] is False
    assert marginal["block_reason"] == "fast_support_lost_after_breakout"
    assert improved["execution_ready"] is True


def test_readiness_memory_blocks_until_extension_contracts_enough():
    runtime_state.clear_monitoring_readiness_memory()

    key = ("crypto", "BTC/USD", "trend_continuation")
    blocked = runtime_state.stabilize_monitoring_readiness(
        key[0],
        key[1],
        key[2],
        100.0,
        {"execution_ready": False, "confidence_cap": 0.6, "block_reason": "continuation_too_extended"},
        {"close": 120.0, "support_extension_pct": 5.0},
    )
    marginal = runtime_state.stabilize_monitoring_readiness(
        key[0],
        key[1],
        key[2],
        200.0,
        {"execution_ready": True, "confidence_cap": 0.9, "block_reason": None},
        {"close": 118.5, "support_extension_pct": 4.7},
    )
    improved = runtime_state.stabilize_monitoring_readiness(
        key[0],
        key[1],
        key[2],
        300.0,
        {"execution_ready": True, "confidence_cap": 0.9, "block_reason": None},
        {"close": 116.0, "support_extension_pct": 4.0},
    )

    assert blocked["execution_ready"] is False
    assert marginal["execution_ready"] is False
    assert marginal["block_reason"] == "continuation_too_extended"
    assert improved["execution_ready"] is True


def test_readiness_memory_resets_when_strategy_changes():
    runtime_state.clear_monitoring_readiness_memory()

    blocked = runtime_state.stabilize_monitoring_readiness(
        "stock",
        "AAPL",
        "trend_continuation",
        100.0,
        {"execution_ready": False, "confidence_cap": 0.5, "block_reason": "fast_support_lost_after_breakout"},
        {"close": 103.0, "current_vs_ema20": -1.0},
    )
    reset = runtime_state.stabilize_monitoring_readiness(
        "stock",
        "AAPL",
        "pullback_reclaim",
        200.0,
        {"execution_ready": True, "confidence_cap": 0.8, "block_reason": None},
        {"close": 104.5, "current_vs_ema20": 0.5, "reclaim_confirmed": True},
    )

    assert blocked["execution_ready"] is False
    assert reset["execution_ready"] is True


def test_stock_and_crypto_extension_handling_is_directionally_consistent():
    stock_signal = SimpleNamespace(
        strategy="Opening Range Breakout",
        strategy_key="opening_range_breakout",
        confidence=0.92,
        reasoning={"opening_range_high": 104.0, "opening_range_acceptance_confirmed": True},
    )
    crypto_signal = SimpleNamespace(
        strategy="breakout_retest",
        strategy_key="breakout_retest",
        confidence=0.91,
        reasoning={"prior_high_40": 104.0, "breakout_acceptance_confirmed": True, "reclaim_confirmed": True},
    )

    stock_moderate = stock_execution_readiness_adjustment(stock_signal, {"5m": trending_up_history(20, start=100.0, end=105.5)})
    stock_extended = stock_execution_readiness_adjustment(stock_signal, {"5m": trending_up_history(20, start=100.0, end=120.0)})

    crypto_moderate = crypto_execution_readiness_adjustment(crypto_signal, {"15m": trending_up_ohlcv(20, start=100.0, end=105.5)})
    crypto_extended = crypto_execution_readiness_adjustment(crypto_signal, {"15m": trending_up_ohlcv(20, start=100.0, end=120.0)})

    assert stock_moderate["execution_ready"] is True
    assert stock_extended["execution_ready"] is False
    assert crypto_moderate["execution_ready"] is True
    assert crypto_extended["execution_ready"] is False
    assert stock_moderate["confidence_cap"] < stock_signal.confidence
    assert crypto_moderate["confidence_cap"] < crypto_signal.confidence


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
async def test_monitoring_route_recovers_insufficient_candles_with_backfill(monkeypatch):
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

    insufficient = {
        "signals": [],
        "top_strategy": None,
        "top_confidence": 0.0,
        "evaluated_strategy_scores": {},
        "evaluated_strategies": {},
        "rejected_strategies": {
            "pullback_reclaim": "insufficient_candles",
            "trend_continuation": "insufficient_candles",
        },
        "feature_scores": {},
    }
    recovered_signal = SimpleNamespace(
        strategy="Pullback Reclaim",
        strategy_key="pullback_reclaim",
        confidence=0.63,
        entry_price=100.0,
        initial_stop=95.0,
        profit_target_1=105.0,
        profit_target_2=110.0,
        regime="neutral",
        notes="recovered",
    )
    recovered = {
        "signals": [recovered_signal],
        "top_strategy": "pullback_reclaim",
        "top_confidence": 0.63,
        "evaluated_strategy_scores": {"pullback_reclaim": 0.63},
        "evaluated_strategies": {"pullback_reclaim": {"valid": True, "base_score": 0.63, "bias": 0.0, "final_score": 0.63, "reason": None, "feature_scores": {}}},
        "rejected_strategies": {},
        "feature_scores": {},
    }

    evaluate_all = MagicMock(side_effect=[insufficient, recovered])
    monkeypatch.setattr("app.stocks.strategies.entry_strategies.evaluate_all", evaluate_all)
    monkeypatch.setattr("app.stocks.tradier_client.tradier_client.get_timesales", AsyncMock(return_value=[
        {"time": datetime(2026, 4, 11, 9, 30, tzinfo=timezone.utc).isoformat(), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100},
        {"time": datetime(2026, 4, 11, 9, 35, tzinfo=timezone.utc).isoformat(), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 100},
    ]))
    monkeypatch.setattr("app.stocks.tradier_client.tradier_client.get_history", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.stocks.candle_fetcher.StockCandleFetcher.backfill", AsyncMock())
    monkeypatch.setattr("app.api.routes.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.api.routes.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr("app.api.routes.monitoring.get_redis", AsyncMock(return_value=SimpleNamespace(exists=AsyncMock(return_value=False))))

    result = await get_monitoring_candidates(asset_class="stock", db=_db())

    assert result["total"] == 1
    assert result["candidates"][0]["top_strategy"] == "pullback_reclaim"
    assert result["candidates"][0]["top_confidence"] == 0.63
    assert result["candidates"][0]["evaluation"]["top_strategy"] == "pullback_reclaim"
    assert result["candidates"][0]["evaluation"]["confidence"] == 0.63
    assert evaluate_all.call_count == 2
    assert monitoring_route.StockCandleFetcher.backfill.await_count == 1


@pytest.mark.asyncio
async def test_monitoring_route_keeps_symbol_visible_when_recovery_still_fails(monkeypatch):
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
        db.execute = AsyncMock(side_effect=[symbols_result, open_position_result])
        return db

    insufficient = {
        "signals": [],
        "top_strategy": None,
        "top_confidence": 0.0,
        "evaluated_strategy_scores": {},
        "evaluated_strategies": {},
        "rejected_strategies": {
            "pullback_reclaim": "insufficient_candles",
        },
        "feature_scores": {},
    }

    evaluate_all = MagicMock(side_effect=[insufficient, insufficient])
    monkeypatch.setattr("app.stocks.strategies.entry_strategies.evaluate_all", evaluate_all)
    monkeypatch.setattr("app.stocks.tradier_client.tradier_client.get_timesales", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.stocks.tradier_client.tradier_client.get_history", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.stocks.candle_fetcher.StockCandleFetcher.backfill", AsyncMock(side_effect=RuntimeError("backfill failed")))
    monkeypatch.setattr("app.api.routes.monitoring.is_watchlist_activation_ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.api.routes.monitoring.regime_engine.can_open", lambda *args, **kwargs: (True, None))
    monkeypatch.setattr("app.api.routes.monitoring.get_redis", AsyncMock(return_value=SimpleNamespace(exists=AsyncMock(return_value=False))))

    result = await get_monitoring_candidates(asset_class="stock", db=_db())

    assert result["total"] == 1
    assert result["candidates"][0]["symbol"] == "AAPL"
    assert result["candidates"][0]["top_strategy"] is None
    assert result["candidates"][0]["evaluation"]["top_strategy"] is None


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
        reasoning={"compression_high_10": 105.0, "compression_low_10": 98.0, "compression_acceptance_confirmed": True},
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
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: trending_up_history(20, start=100.0, end=105.5))

    await monitor._evaluate_symbol(db, ws)

    assert create_position.await_count == 1
    assert captured["confidence"] < 0.92


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
    monkeypatch.setattr(monitor._store, "get", lambda *args, **kwargs: trending_up_ohlcv(30, start=100.0, end=112.0))

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

    create_position = _configure_crypto_monitor(
        monkeypatch,
        monitor,
        [signal],
        "breakout_retest",
        0.91,
        store_get_result=trending_down_ohlcv(30, start=120.0, end=90.0),
    )

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

    create_position = _configure_crypto_monitor(monkeypatch, monitor, [signal], "pullback_reclaim", 0.92)

    pullback = trending_up_ohlcv(30, start=100.0, end=108.0)
    pullback[-2] = make_candle(28, 103.0)
    pullback[-1] = make_candle(29, 107.0)
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

    failed_follow_through = trending_up_ohlcv(30, start=100.0, end=125.0)
    failed_follow_through[-2] = make_candle(28, 124.0)
    failed_follow_through[-1] = make_candle(29, 121.0)
    create_position = _configure_crypto_monitor(
        monkeypatch,
        monitor,
        [signal],
        "trend_continuation",
        0.94,
        frame_info={},
        store_get_result=failed_follow_through,
    )

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
