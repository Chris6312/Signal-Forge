import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.common.models.position import PositionState
from app.crypto.exit_worker import CryptoExitWorker
from app.crypto.strategies.exit_strategies import ExitDecision
from tests.conftest import trending_up_ohlcv


@pytest.mark.asyncio
async def test_crypto_exit_worker_live_stop_exits_immediately_before_tp1(monkeypatch):
    worker = CryptoExitWorker()
    db = AsyncMock()
    position = SimpleNamespace(
        id=uuid4(),
        symbol="BTC/USD",
        asset_class="crypto",
        state=PositionState.OPEN,
        entry_price=100.0,
        quantity=10.0,
        entry_time=None,
        initial_stop=93.0,
        current_stop=None,
        profit_target_1=108.0,
        profit_target_2=115.0,
        milestone_state={},
        frozen_policy={},
        max_hold_hours=None,
        exit_strategy="Partial at TP1, Dynamic Trail on Runner",
        pnl_realized=0.0,
        pnl_unrealized=0.0,
    )

    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()

    close_position = AsyncMock()
    monkeypatch.setattr(worker, "_close_position", close_position)
    monkeypatch.setattr("app.crypto.exit_worker.evaluate_exit", lambda *args, **kwargs: ExitDecision(False, "Holding"))
    monkeypatch.setattr("app.crypto.exit_worker.kraken_client.get_ticker", AsyncMock(return_value={"c": ["92.0"]}))
    monkeypatch.setattr("app.crypto.exit_worker.kraken_client.get_ohlcv", AsyncMock(side_effect=AssertionError("ohlcv should not be fetched before live stop exit")))

    await worker._evaluate_position(db, position)

    assert close_position.await_count == 1
    assert "Stop hit at 93.0000" in close_position.await_args.args[3]
    assert position.updated_at is not None


@pytest.mark.asyncio
async def test_crypto_exit_worker_tp1_partial_promotes_and_persists_immediately(monkeypatch):
    worker = CryptoExitWorker()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    position = SimpleNamespace(
        id=uuid4(),
        symbol="BTC/USD",
        asset_class="crypto",
        state=PositionState.OPEN,
        entry_price=100.0,
        quantity=10.0,
        entry_time=None,
        initial_stop=93.0,
        current_stop=93.0,
        profit_target_1=108.0,
        profit_target_2=115.0,
        milestone_state={},
        frozen_policy={},
        max_hold_hours=None,
        exit_strategy="Partial at TP1, Dynamic Trail on Runner",
        pnl_realized=0.0,
        pnl_unrealized=0.0,
    )

    redis = SimpleNamespace(set=AsyncMock(return_value=True), delete=AsyncMock())
    monkeypatch.setattr("app.crypto.exit_worker.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr("app.crypto.exit_worker.kraken_client.get_ticker", AsyncMock(return_value={"c": ["108.0"]}))
    monkeypatch.setattr("app.crypto.exit_worker.kraken_client.get_ohlcv", AsyncMock(return_value=trending_up_ohlcv(20)))
    monkeypatch.setattr("app.crypto.exit_worker.log_event", AsyncMock())
    monkeypatch.setattr("app.crypto.exit_worker.crypto_ledger.record_exit", AsyncMock(return_value=None))
    monkeypatch.setattr("app.crypto.exit_worker.crypto_ledger.record_fee", AsyncMock(return_value=SimpleNamespace(order_id=None)))

    await worker._evaluate_position(db, position)

    assert position.quantity == pytest.approx(5.0)
    assert position.current_stop == pytest.approx(100.0)
    assert position.milestone_state == {
        "tp1_hit": True,
        "tp1_price": 108.0,
        "protected_floor": 100.0,
        "trailing_stop": 100.0,
        "protection_mode": "break_even",
        "be_promoted": True,
        "trail_active": True,
    }
    assert db.add.call_count >= 1
    assert position.updated_at is not None


@pytest.mark.asyncio
async def test_crypto_exit_worker_live_runner_floor_exits_without_candle_confirmation(monkeypatch):
    worker = CryptoExitWorker()
    db = AsyncMock()
    position = SimpleNamespace(
        id=uuid4(),
        symbol="BTC/USD",
        asset_class="crypto",
        state=PositionState.OPEN,
        entry_price=100.0,
        quantity=5.0,
        entry_time=None,
        initial_stop=93.0,
        current_stop=100.0,
        profit_target_1=108.0,
        profit_target_2=115.0,
        milestone_state={
            "tp1_hit": True,
            "tp1_price": 108.0,
            "protected_floor": 100.0,
            "trailing_stop": 100.0,
            "protection_mode": "break_even",
            "be_promoted": True,
            "trail_active": True,
        },
        frozen_policy={},
        max_hold_hours=None,
        exit_strategy="Partial at TP1, Dynamic Trail on Runner",
        pnl_realized=0.0,
        pnl_unrealized=0.0,
    )

    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()

    close_position = AsyncMock()
    monkeypatch.setattr(worker, "_close_position", close_position)
    monkeypatch.setattr("app.crypto.exit_worker.evaluate_exit", lambda *args, **kwargs: ExitDecision(False, "Holding"))
    monkeypatch.setattr("app.crypto.exit_worker.kraken_client.get_ticker", AsyncMock(return_value={"c": ["99.0"]}))
    monkeypatch.setattr("app.crypto.exit_worker.kraken_client.get_ohlcv", AsyncMock(side_effect=AssertionError("ohlcv should not be fetched when promoted floor is breached")))

    await worker._evaluate_position(db, position)

    assert close_position.await_count == 1
    assert "Stop hit at 100.0000" in close_position.await_args.args[3]
    assert position.updated_at is not None


@pytest.mark.asyncio
async def test_crypto_exit_worker_follow_through_promotion_raises_floor_after_tp1(monkeypatch):
    worker = CryptoExitWorker()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.flush = AsyncMock()

    position = SimpleNamespace(
        id=uuid4(),
        symbol="BTC/USD",
        asset_class="crypto",
        state=PositionState.OPEN,
        entry_price=100.0,
        quantity=5.0,
        entry_time=None,
        initial_stop=93.0,
        current_stop=100.0,
        profit_target_1=108.0,
        profit_target_2=115.0,
        milestone_state={
            "tp1_hit": True,
            "tp1_price": 108.0,
            "protected_floor": 100.0,
            "trailing_stop": 100.0,
            "protection_mode": "break_even",
            "be_promoted": True,
            "trail_active": True,
        },
        frozen_policy={},
        max_hold_hours=None,
        exit_strategy="Partial at TP1, Dynamic Trail on Runner",
        pnl_realized=0.0,
        pnl_unrealized=0.0,
        break_even_floor=100.0,
        promoted_floor=100.0,
        highest_promoted_floor=100.0,
        runner_phase="breakeven",
        protection_mode="breakeven",
        tp1_hit=True,
    )

    redis = SimpleNamespace(set=AsyncMock(return_value=True), delete=AsyncMock())
    monkeypatch.setattr("app.crypto.exit_worker.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr("app.crypto.exit_worker.kraken_client.get_ticker", AsyncMock(return_value={"c": ["112.0"]}))
    monkeypatch.setattr("app.crypto.exit_worker.kraken_client.get_ohlcv", AsyncMock(return_value=trending_up_ohlcv(20, start=100.0, end=112.0)))
    monkeypatch.setattr("app.crypto.exit_worker.evaluate_exit", lambda *args, **kwargs: ExitDecision(False, "Holding"))
    monkeypatch.setattr("app.crypto.exit_worker.log_event", AsyncMock())

    await worker._evaluate_position(db, position)

    assert position.promoted_floor is not None and position.promoted_floor > 100.0
    assert position.highest_promoted_floor == pytest.approx(position.promoted_floor)
    assert position.current_stop == pytest.approx(position.promoted_floor)
    assert position.runner_phase == "trail_active"
    assert position.protection_mode == "trail_active"
    assert position.updated_at is not None
