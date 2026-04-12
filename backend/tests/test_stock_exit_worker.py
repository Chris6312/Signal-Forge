from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.common.models.position import PositionState
from app.stocks.exit_worker import StockExitWorker


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
