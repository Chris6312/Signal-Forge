from types import SimpleNamespace

import pytest

from app.services.runner_protection import (
    get_effective_floor,
    get_protection_snapshot,
    promote_follow_through,
    promote_tp1,
)
from tests.conftest import trending_up_ohlcv


def test_get_effective_floor_prefers_persisted_runner_state_over_legacy_stop():
    position = SimpleNamespace(
        symbol="BTC/USD",
        asset_class="crypto",
        entry_price=100.0,
        quantity=10.0,
        initial_stop=93.0,
        current_stop=96.0,
        initial_risk_price=94.0,
        break_even_floor=101.0,
        promoted_floor=103.0,
        highest_promoted_floor=106.0,
        milestone_state={"protected_floor": 96.0, "trailing_stop": 96.0},
    )

    snapshot = get_protection_snapshot(position)

    assert get_effective_floor(position) == pytest.approx(106.0)
    assert snapshot.final_floor == pytest.approx(106.0)
    assert snapshot.promoted_protective_floor == pytest.approx(106.0)


def test_promote_tp1_never_weakens_a_stronger_floor():
    position = SimpleNamespace(
        symbol="AAPL",
        asset_class="stock",
        entry_price=100.0,
        quantity=10.0,
        fees_paid=0.0,
        profit_target_1=108.0,
        tp1_price=None,
        tp1_hit=False,
        current_stop=105.0,
        initial_stop=93.0,
        initial_risk_price=None,
        break_even_floor=None,
        promoted_floor=None,
        highest_promoted_floor=None,
        milestone_state={},
    )

    promoted = promote_tp1(position, current_price=108.0)

    assert promoted is True
    assert get_effective_floor(position) == pytest.approx(105.0)
    assert position.current_stop == pytest.approx(105.0)
    assert position.break_even_floor == pytest.approx(100.0)
    assert position.highest_promoted_floor == pytest.approx(105.0)


def test_follow_through_promotion_ratchets_up_and_rejects_weaker_recalc():
    position = SimpleNamespace(
        symbol="BTC/USD",
        asset_class="crypto",
        entry_price=100.0,
        quantity=10.0,
        fees_paid=0.0,
        profit_target_1=108.0,
        tp1_price=108.0,
        tp1_hit=True,
        current_stop=100.0,
        initial_stop=93.0,
        break_even_floor=100.0,
        promoted_floor=100.0,
        highest_promoted_floor=100.0,
        milestone_state={"tp1_hit": True, "trailing_stop": 100.0, "protected_floor": 100.0},
    )

    assert promote_follow_through(position, current_price=112.0, ohlcv=trending_up_ohlcv(20, start=100.0, end=112.0)) is True
    first_floor = get_effective_floor(position)
    assert first_floor is not None and first_floor > 100.0

    assert promote_follow_through(position, current_price=103.0, ohlcv=trending_up_ohlcv(20, start=100.0, end=103.0)) is False
    assert get_effective_floor(position) == pytest.approx(first_floor)
