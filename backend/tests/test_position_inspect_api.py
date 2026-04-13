from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.conftest import make_hold_metrics


def test_position_api_returns_tp1_milestone_and_promoted_floor(api_client, mock_db, monkeypatch):
    db, result = mock_db
    position = SimpleNamespace(
        id=uuid4(),
        symbol="BTC/USD",
        asset_class="crypto",
        state="OPEN",
        entry_price=100.0,
        current_price=108.0,
        quantity=5.0,
        entry_time=datetime(2026, 1, 1, 10, 0, 0),
        initial_stop=93.0,
        current_stop=100.0,
        profit_target_1=108.0,
        profit_target_2=115.0,
        max_hold_hours=24,
        milestone_state={
            "tp1_hit": True,
            "tp1_price": 108.0,
            "protected_floor": 100.0,
            "trailing_stop": 100.0,
            "protection_mode": "break_even",
            "be_promoted": True,
            "trail_active": True,
        },
    )
    result.scalar_one_or_none.return_value = position
    monkeypatch.setattr(
        "app.services.watchlist_service.compute_position_hold_metrics",
        lambda *args, **kwargs: make_hold_metrics(6.2, 24, 0.2583333333, "green"),
    )

    response = api_client.get(f"/api/positions/{position.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["milestone_state"]["tp1_hit"] is True
    assert payload["milestone_state"]["protected_floor"] == 100.0
    assert payload["milestone_state"]["protection_mode"] == "break_even"
    assert payload["current_stop"] == 100.0
    assert payload["hours_held"] == pytest.approx(6.2)
    assert payload["hold_ratio"] == pytest.approx(0.2583333333)
    assert payload["time_risk_state"] == "green"


def test_open_positions_api_returns_hold_metrics(api_client, mock_db, monkeypatch):
    db, result = mock_db
    position = SimpleNamespace(
        id=uuid4(),
        symbol="BTC/USD",
        asset_class="crypto",
        state="OPEN",
        entry_price=100.0,
        current_price=108.0,
        quantity=5.0,
        entry_time=datetime(2026, 1, 1, 10, 0, 0),
        initial_stop=93.0,
        current_stop=100.0,
        profit_target_1=108.0,
        profit_target_2=115.0,
        max_hold_hours=24,
        milestone_state={},
        frozen_policy={},
        exit_strategy="Partial at TP1, Dynamic Trail on Runner",
        pnl_realized=0.0,
        pnl_unrealized=40.0,
        fees_paid=0.0,
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        updated_at=datetime(2026, 1, 1, 10, 0, 0),
    )
    result.scalars.return_value.all.return_value = [position]
    monkeypatch.setattr(
        "app.api.routes.positions.compute_position_hold_metrics",
        lambda *args, **kwargs: make_hold_metrics(6.2, 24, 0.2583333333, "green"),
    )

    response = api_client.get("/api/positions/open")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["hours_held"] == pytest.approx(6.2)
    assert payload[0]["hold_ratio"] == pytest.approx(0.2583333333)
    assert payload[0]["time_risk_state"] == "green"


def test_position_api_returns_persisted_stock_runner_floor_without_regression(api_client, mock_db, monkeypatch):
    db, result = mock_db
    last_update = datetime(2026, 1, 1, 12, 30, 0)
    position = SimpleNamespace(
        id=uuid4(),
        symbol="AAPL",
        asset_class="stock",
        state="OPEN",
        entry_price=100.0,
        current_price=112.0,
        quantity=5.0,
        entry_time=datetime(2026, 1, 1, 10, 0, 0),
        initial_stop=93.0,
        current_stop=100.0,
        profit_target_1=108.0,
        profit_target_2=115.0,
        max_hold_hours=24,
        break_even_floor=100.0,
        promoted_floor=106.0,
        highest_promoted_floor=108.0,
        runner_phase="trail_active",
        protection_mode="trail_active",
        last_protection_update_at=last_update,
        milestone_state={
            "tp1_hit": True,
            "tp1_price": 108.0,
            "protected_floor": 108.0,
            "trailing_stop": 100.0,
            "protection_mode": "breakeven",
            "be_promoted": True,
            "trail_active": True,
        },
    )
    result.scalar_one_or_none.return_value = position
    monkeypatch.setattr(
        "app.services.watchlist_service.compute_position_hold_metrics",
        lambda *args, **kwargs: make_hold_metrics(6.2, 24, 0.2583333333, "green"),
    )

    response = api_client.get(f"/api/positions/{position.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["break_even_floor"] == 100.0
    assert payload["promoted_floor"] == 106.0
    assert payload["highest_promoted_floor"] == 108.0
    assert payload["promoted_protective_floor"] == 108.0
    assert payload["runner_phase"] == "trail_active"
    assert payload["protection_mode"] == "trail_active"
    assert payload["last_protection_update_at"] == last_update.isoformat()
    assert payload["current_stop"] == 100.0
