from datetime import datetime
from types import SimpleNamespace

from app.services.watchlist_service import build_position_inspect_payload


def test_monitoring_surface_preserves_frozen_policy_and_milestone_state(monkeypatch):
    frozen_policy = {"exit_template": "template-a", "max_hold_hours": 18}
    milestone_state = {"tp1_hit": False, "trail_active": False}

    position = SimpleNamespace(
        id="pos-monitor-1",
        symbol="SOL/USD",
        asset_class="crypto",
        state="OPEN",
        entry_price=100.0,
        current_price=112.0,
        quantity=10.0,
        entry_time=datetime(2026, 1, 1, 10, 0, 0),
        entry_strategy="breakout",
        exit_strategy="runner",
        initial_stop=95.0,
        current_stop=105.0,
        profit_target_1=110.0,
        profit_target_2=120.0,
        max_hold_hours=18,
        regime_at_entry="trend",
        watchlist_source_id="scan-1",
        management_policy_version="1.0",
        frozen_policy=frozen_policy,
        milestone_state=milestone_state,
        exit_price=None,
        exit_time=None,
        exit_reason=None,
        pnl_realized=0.0,
        pnl_unrealized=120.0,
        fees_paid=0.0,
        created_at=datetime(2026, 1, 1, 10, 0, 0),
        updated_at=datetime(2026, 1, 1, 10, 0, 0),
    )

    monkeypatch.setattr(
        "app.services.watchlist_service.compute_position_hold_metrics",
        lambda *args, **kwargs: SimpleNamespace(
            hours_held=3.0,
            max_hold_hours=18,
            hold_ratio=0.1666666667,
            time_risk_state="green",
            as_dict=lambda: {
                "hours_held": 3.0,
                "max_hold_hours": 18,
                "hold_ratio": 0.1666666667,
                "time_risk_state": "green",
            },
        ),
    )

    payload = build_position_inspect_payload(position)

    assert payload["frozen_policy"] == frozen_policy
    assert payload["milestone_state"] == milestone_state
    assert payload["max_hold_hours"] == 18
