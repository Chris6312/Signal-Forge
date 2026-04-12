from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.common.models.position import PositionState
from app.stocks.exit_worker import StockExitWorker
from app.stocks.strategies.exit_strategies import StockExitDecision
from tests.conftest import trending_up_history


@pytest.mark.asyncio
async def test_stock_exit_worker_hard_max_hold_uses_shared_helper(monkeypatch):
    worker = StockExitWorker()
    db = AsyncMock()
    position = SimpleNamespace(
        id=uuid4(),
        symbol="AAPL",
        asset_class="stock",
        state=PositionState.OPEN,
        entry_price=100.0,
        quantity=10.0,
        entry_time=None,
        initial_stop=93.0,
        current_stop=None,
        profit_target_1=108.0,
        profit_target_2=115.0,
        milestone_state={},
        frozen_policy={"hard_max_hold": True},
        max_hold_hours=24,
        exit_strategy="Partial at TP1, Dynamic Trail on Runner",
        pnl_realized=0.0,
        pnl_unrealized=0.0,
    )

    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()

    close_position = AsyncMock()
    monkeypatch.setattr(worker, "_close_position", close_position)
    monkeypatch.setattr(
        "app.stocks.exit_worker.compute_position_hold_metrics",
        lambda *args, **kwargs: SimpleNamespace(
            hours_held=24.1,
            max_hold_hours=24,
            hold_ratio=1.0041666667,
            time_risk_state="red",
        ),
    )
    monkeypatch.setattr("app.stocks.exit_worker.tradier_client.get_quote", AsyncMock(return_value={"AAPL": {"last": 105.0}}))
    monkeypatch.setattr("app.stocks.exit_worker.tradier_client.get_history", AsyncMock(side_effect=AssertionError("history should not be fetched after hard max hold exit")))

    await worker._evaluate_position(db, position)

    assert close_position.await_count == 1
    assert "Hard max hold time exceeded (24h)" in close_position.await_args.args[3]
    assert position.updated_at is not None


@pytest.mark.asyncio
async def test_stock_exit_worker_tp1_partial_promotes_break_even_and_persists(monkeypatch):
    worker = StockExitWorker()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.flush = AsyncMock()

    position = SimpleNamespace(
        id=uuid4(),
        symbol="AAPL",
        asset_class="stock",
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
        exit_strategy="Partial at TP1, Trail Remainder",
        pnl_realized=0.0,
        pnl_unrealized=0.0,
        fees_paid=0.0,
    )

    redis = SimpleNamespace(set=AsyncMock(return_value=True), delete=AsyncMock())
    monkeypatch.setattr("app.stocks.exit_worker.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr("app.stocks.exit_worker.tradier_client.get_quote", AsyncMock(return_value={"AAPL": {"last": 108.0}}))
    monkeypatch.setattr("app.stocks.exit_worker.tradier_client.get_history", AsyncMock(return_value=trending_up_history(20, start=100.0, end=108.0)))
    monkeypatch.setattr("app.stocks.exit_worker.evaluate_exit", lambda *args, **kwargs: StockExitDecision(False, "TP1 reached — partial exit", partial=True, partial_pct=0.50, new_stop=100.0, trailing_active=True, tp1_hit=True))
    monkeypatch.setattr("app.stocks.exit_worker.log_event", AsyncMock())
    monkeypatch.setattr("app.stocks.exit_worker.stock_ledger.record_exit", AsyncMock(return_value=None))

    await worker._evaluate_position(db, position)

    assert position.quantity == pytest.approx(5.0)
    assert position.current_stop == pytest.approx(100.0)
    assert position.tp1_hit is True
    assert position.break_even_floor == pytest.approx(100.0)
    assert position.highest_promoted_floor == pytest.approx(100.0)
    assert position.runner_phase == "breakeven"
    assert position.milestone_state["tp1_hit"] is True
    assert position.milestone_state["trail_active"] is True
    assert position.updated_at is not None


@pytest.mark.asyncio
async def test_stock_exit_worker_promoted_floor_breach_exits_immediately(monkeypatch):
    worker = StockExitWorker()
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    position = SimpleNamespace(
        id=uuid4(),
        symbol="AAPL",
        asset_class="stock",
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
            "protected_floor": 104.0,
            "trailing_stop": 104.0,
            "trail_active": True,
        },
        frozen_policy={},
        max_hold_hours=None,
        exit_strategy="Partial at TP1, Trail Remainder",
        pnl_realized=0.0,
        pnl_unrealized=0.0,
        break_even_floor=100.0,
        promoted_floor=104.0,
        highest_promoted_floor=104.0,
        runner_phase="trail_active",
    )

    close_position = AsyncMock()
    monkeypatch.setattr(worker, "_close_position", close_position)
    monkeypatch.setattr("app.stocks.exit_worker.tradier_client.get_quote", AsyncMock(return_value={"AAPL": {"last": 103.5}}))
    monkeypatch.setattr("app.stocks.exit_worker.tradier_client.get_history", AsyncMock(side_effect=AssertionError("history should not be fetched when promoted floor is breached")))

    await worker._evaluate_position(db, position)

    assert close_position.await_count == 1
    assert "Stop hit at 104.0000" in close_position.await_args.args[3]
    assert position.updated_at is not None


@pytest.mark.asyncio
async def test_stock_exit_worker_follow_through_promotion_raises_floor_after_tp1(monkeypatch):
    worker = StockExitWorker()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.flush = AsyncMock()

    position = SimpleNamespace(
        id=uuid4(),
        symbol="AAPL",
        asset_class="stock",
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
            "trail_active": True,
        },
        frozen_policy={},
        max_hold_hours=None,
        exit_strategy="Partial at TP1, Trail Remainder",
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
    monkeypatch.setattr("app.stocks.exit_worker.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr("app.stocks.exit_worker.tradier_client.get_quote", AsyncMock(return_value={"AAPL": {"last": 112.0}}))
    monkeypatch.setattr("app.stocks.exit_worker.tradier_client.get_history", AsyncMock(return_value=trending_up_history(20, start=100.0, end=112.0)))
    monkeypatch.setattr("app.stocks.exit_worker.evaluate_exit", lambda *args, **kwargs: StockExitDecision(False, "Holding"))
    monkeypatch.setattr("app.stocks.exit_worker.log_event", AsyncMock())

    await worker._evaluate_position(db, position)

    assert position.promoted_floor is not None and position.promoted_floor > 100.0
    assert position.highest_promoted_floor == pytest.approx(position.promoted_floor)
    assert position.current_stop == pytest.approx(position.promoted_floor)
    assert position.runner_phase == "trail_active"
    assert position.protection_mode == "trail_active"
    assert position.updated_at is not None


@pytest.mark.asyncio
async def test_stock_exit_worker_recalc_does_not_weaken_promoted_floor(monkeypatch):
    worker = StockExitWorker()
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.flush = AsyncMock()

    position = SimpleNamespace(
        id=uuid4(),
        symbol="AAPL",
        asset_class="stock",
        state=PositionState.OPEN,
        entry_price=100.0,
        quantity=5.0,
        entry_time=None,
        initial_stop=93.0,
        current_stop=105.0,
        profit_target_1=108.0,
        profit_target_2=115.0,
        milestone_state={
            "tp1_hit": True,
            "tp1_price": 108.0,
            "protected_floor": 105.0,
            "trailing_stop": 105.0,
            "trail_active": True,
        },
        frozen_policy={},
        max_hold_hours=None,
        exit_strategy="Partial at TP1, Trail Remainder",
        pnl_realized=0.0,
        pnl_unrealized=0.0,
        break_even_floor=100.0,
        promoted_floor=105.0,
        highest_promoted_floor=105.0,
        runner_phase="trail_active",
        protection_mode="trail_active",
        tp1_hit=True,
    )

    redis = SimpleNamespace(set=AsyncMock(return_value=True), delete=AsyncMock())
    monkeypatch.setattr("app.stocks.exit_worker.get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr("app.stocks.exit_worker.tradier_client.get_quote", AsyncMock(return_value={"AAPL": {"last": 108.5}}))
    monkeypatch.setattr("app.stocks.exit_worker.tradier_client.get_history", AsyncMock(return_value=trending_up_history(20, start=105.0, end=108.5)))
    monkeypatch.setattr("app.stocks.exit_worker.evaluate_exit", lambda *args, **kwargs: StockExitDecision(False, "Trail updated", new_stop=101.0, trailing_active=True))
    monkeypatch.setattr("app.stocks.exit_worker.log_event", AsyncMock())

    await worker._evaluate_position(db, position)

    assert position.current_stop == pytest.approx(105.0)
    assert position.promoted_floor == pytest.approx(105.0)
    assert position.highest_promoted_floor == pytest.approx(105.0)
    assert position.updated_at is not None
