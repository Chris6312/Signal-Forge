from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.common.position_time import compute_position_hold_metrics
from app.services.watchlist_service import build_position_inspect_payload
from tests.conftest import make_hold_metrics


@pytest.mark.parametrize(
    "hours_held,max_hold_hours,expected_state,expected_ratio",
    [
        (6.2, 24, "green", 6.2 / 24),
        (16.8, 24, "yellow", 16.8 / 24),
        (22.8, 24, "red", 22.8 / 24),
    ],
)
def test_compute_position_hold_metrics_thresholds(hours_held, max_hold_hours, expected_state, expected_ratio):
    entry_time = datetime(2026, 1, 1, 10, 0, 0)
    now = datetime(2026, 1, 1, 10, 0, 0) + timedelta(hours=hours_held)

    metrics = compute_position_hold_metrics(entry_time, max_hold_hours, now=now)

    assert metrics.hours_held == pytest.approx(hours_held)
    assert metrics.max_hold_hours == max_hold_hours
    assert metrics.hold_ratio == pytest.approx(expected_ratio)
    assert metrics.time_risk_state == expected_state


def test_compute_position_hold_metrics_missing_entry_time():
    metrics = compute_position_hold_metrics(None, 24, now=datetime(2026, 1, 1, 10, 0, 0))

    assert metrics.hours_held == 0.0
    assert metrics.max_hold_hours == 24
    assert metrics.hold_ratio == pytest.approx(0.0)
    assert metrics.time_risk_state == "green"


def test_build_position_inspect_payload_includes_hold_metrics(monkeypatch):
    position = SimpleNamespace(
        id="pos-1",
        symbol="BTC/USD",
        asset_class="crypto",
        state="OPEN",
        entry_price=100.0,
        current_price=108.0,
        quantity=5.0,
        entry_time=datetime(2026, 1, 1, 10, 0, 0),
        entry_strategy="momentum",
        exit_strategy="partial",
        initial_stop=93.0,
        current_stop=100.0,
        profit_target_1=108.0,
        profit_target_2=115.0,
        max_hold_hours=24,
        regime_at_entry="trend",
        watchlist_source_id="manual",
        management_policy_version="1.0",
        frozen_policy={},
        milestone_state={},
        exit_price=None,
        exit_time=None,
        exit_reason=None,
        pnl_realized=0.0,
        pnl_unrealized=40.0,
        fees_paid=0.0,
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        updated_at=datetime(2026, 1, 1, 10, 0, 0),
    )

    monkeypatch.setattr(
        "app.services.watchlist_service.compute_position_hold_metrics",
        lambda *args, **kwargs: make_hold_metrics(6.2, 24, 0.2583333333, "green"),
    )

    payload = build_position_inspect_payload(position)

    assert payload["hours_held"] == pytest.approx(6.2)
    assert payload["max_hold_hours"] == 24
    assert payload["hold_ratio"] == pytest.approx(0.2583333333)
    assert payload["time_risk_state"] == "green"
