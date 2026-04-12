from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest


def _trade_row(**overrides):
    base = dict(
        id=uuid4(),
        symbol="BTC/USD",
        asset_class="crypto",
        state="CLOSED",
        entry_price=100.0,
        current_price=108.0,
        quantity=5.0,
        entry_time=datetime(2026, 1, 1, 10, 0, 0),
        entry_strategy="momentum",
        exit_strategy="Partial at TP1, Dynamic Trail on Runner",
        initial_stop=93.0,
        current_stop=100.0,
        profit_target_1=108.0,
        profit_target_2=115.0,
        max_hold_hours=24,
        regime_at_entry="trend",
        watchlist_source_id="manual",
        management_policy_version="1.0",
        frozen_policy=None,
        milestone_state={
            "tp1_hit": True,
            "tp1_price": 108.0,
            "protected_floor": 100.0,
            "trailing_stop": 100.0,
            "protection_mode": "break_even",
            "be_promoted": True,
            "trail_active": True,
        },
        protection_mode=None,
        initial_risk_price=None,
        tp1_price=None,
        tp1_hit=None,
        break_even_floor=None,
        promoted_floor=None,
        highest_promoted_floor=None,
        runner_phase=None,
        milestone_version=None,
        last_protection_update_at=None,
        exit_price=108.0,
        exit_time=datetime(2026, 1, 2, 10, 0, 0),
        exit_reason="TP1",
        pnl_realized=40.0,
        pnl_unrealized=0.0,
        fees_paid=0.0,
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        updated_at=datetime(2026, 1, 2, 10, 0, 0),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_trades_api_returns_closed_trades_with_null_runner_fields(api_client, mock_db):
    db, result = mock_db
    result.scalars.return_value.all.return_value = [_trade_row()]

    response = api_client.get("/api/trades")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["symbol"] == "BTC/USD"
    assert payload[0]["milestone_state"]["tp1_hit"] is True
    assert payload[0]["protection_mode"] is None
    assert payload[0]["tp1_price"] is None


@pytest.mark.parametrize("asset_class", [None, "crypto"])
def test_trades_summary_returns_success_for_legacy_rows(api_client, mock_db, asset_class):
    db, result = mock_db
    result.scalars.return_value.all.return_value = [_trade_row()]

    response = api_client.get("/api/trades/summary", params={"asset_class": asset_class} if asset_class else None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_trades"] == 1
    assert payload["winners"] == 1
    assert payload["losers"] == 0
    assert payload["win_rate"] == 100.0
