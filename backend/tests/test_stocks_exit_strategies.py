"""Unit tests for stock exit strategies and their helper functions."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.stocks.strategies.exit_strategies import (
    _atr_from_history,
    EndOfDayExit,
    FixedRiskBreakEvenPromotion,
    FirstFailedFollowThroughExit,
    PartialAtTP1TrailRemainder,
    StockExitDecision,
)
from tests.conftest import make_bar, trending_up_history

_NOT_EOD = "app.stocks.strategies.exit_strategies._is_near_eod"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pos(**kwargs):
    defaults = dict(
        entry_price=100.0,
        initial_stop=93.0,
        current_stop=None,
        profit_target_1=108.0,
        profit_target_2=115.0,
        milestone_state={},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# _atr_from_history
# ---------------------------------------------------------------------------

class TestAtrFromHistory:
    def test_zero_when_insufficient_data(self):
        assert _atr_from_history([make_bar(100.0) for _ in range(5)], period=14) == 0.0

    def test_positive_for_valid_data(self):
        assert _atr_from_history(trending_up_history(30)) > 0.0


# ---------------------------------------------------------------------------
# FixedRiskBreakEvenPromotion
# ---------------------------------------------------------------------------

class TestFixedRiskBreakEvenPromotion:
    def setup_method(self):
        self.strategy = FixedRiskBreakEvenPromotion()

    def test_exit_when_stop_hit(self):
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(_pos(), 90.0, [make_bar(90.0)])
        assert decision.should_exit is True
        assert "Stop hit" in decision.reason

    def test_exit_at_end_of_day(self):
        with patch(_NOT_EOD, return_value=True):
            decision = self.strategy.evaluate(_pos(), 105.0, [make_bar(105.0)])
        assert decision.should_exit is True
        assert "End-of-day" in decision.reason

    def test_stop_promoted_to_break_even(self):
        # tp1 * 0.5 = 54 — any price above entry triggers promotion
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(_pos(), 104.0, trending_up_history(20))
        assert decision.should_exit is False
        assert decision.new_stop == pytest.approx(100.0)  # max(stop=93, entry=100)

    def test_holding_after_be_promotion(self):
        pos = _pos(milestone_state={"be_promoted": True})
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(pos, 102.0, trending_up_history(20))
        assert decision.should_exit is False
        assert decision.reason == "Holding"

    def test_tp1_activates_atr_trail(self):
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(_pos(current_stop=93.0), 108.0, trending_up_history(20))
        assert decision.should_exit is False
        assert decision.tp1_hit is True
        assert decision.trailing_active is True
        assert decision.new_stop is not None
        assert decision.new_stop >= 100.0


# ---------------------------------------------------------------------------
# PartialAtTP1TrailRemainder
# ---------------------------------------------------------------------------

class TestPartialAtTP1TrailRemainder:
    def setup_method(self):
        self.strategy = PartialAtTP1TrailRemainder()

    def test_exit_when_stop_hit(self):
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(_pos(), 90.0, [make_bar(90.0)])
        assert decision.should_exit is True

    def test_exit_at_end_of_day(self):
        with patch(_NOT_EOD, return_value=True):
            decision = self.strategy.evaluate(_pos(), 105.0, [make_bar(105.0)])
        assert decision.should_exit is True
        assert "End-of-day" in decision.reason

    def test_partial_exit_at_tp1(self):
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(_pos(), 108.0, trending_up_history(20))
        assert decision.should_exit is False
        assert decision.partial is True
        assert decision.partial_pct == pytest.approx(0.50)
        assert decision.new_stop == pytest.approx(100.0)

    def test_holding_before_tp1(self):
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(_pos(), 104.0, trending_up_history(20))
        assert decision.should_exit is False
        assert decision.partial is False

    def test_trail_stop_hit_after_tp1(self):
        pos = _pos(
            current_stop=100.0,
            milestone_state={"tp1_hit": True, "trailing_stop": 105.0},
        )
        history = [make_bar(104.0) for _ in range(5)]
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(pos, 104.0, history)
        assert decision.should_exit is True
        assert "Trail stop hit" in decision.reason

    def test_trail_raised_after_tp1(self):
        pos = _pos(
            current_stop=105.0,
            milestone_state={"tp1_hit": True, "trailing_stop": 105.0},
        )
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(pos, 120.0, trending_up_history(25))
        assert decision.should_exit is False
        assert decision.trailing_active is True
        assert decision.new_stop is not None
        assert decision.new_stop > 105.0


# ---------------------------------------------------------------------------
# FirstFailedFollowThroughExit
# ---------------------------------------------------------------------------

class TestFirstFailedFollowThroughExit:
    def setup_method(self):
        self.strategy = FirstFailedFollowThroughExit()

    def test_exit_when_stop_hit(self):
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(_pos(), 90.0, [make_bar(90.0)])
        assert decision.should_exit is True

    def test_exit_at_end_of_day(self):
        with patch(_NOT_EOD, return_value=True):
            decision = self.strategy.evaluate(_pos(), 105.0, [make_bar(105.0)])
        assert decision.should_exit is True

    def test_exit_on_three_declining_closes_below_entry(self):
        history = [make_bar(99.0), make_bar(97.0), make_bar(95.0)]
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(_pos(), 95.0, history)
        assert decision.should_exit is True
        assert "Failed follow-through" in decision.reason

    def test_holding_when_closes_are_rising(self):
        history = [make_bar(101.0), make_bar(103.0), make_bar(105.0)]
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(_pos(), 105.0, history)
        assert decision.should_exit is False

    def test_holding_with_insufficient_history(self):
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(_pos(), 98.0, [make_bar(98.0)])
        assert decision.should_exit is False


class TestEndOfDayExit:
    def setup_method(self):
        self.strategy = EndOfDayExit()

    def test_tp1_activates_atr_trail_before_eod(self):
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(_pos(current_stop=93.0), 108.0, trending_up_history(20))
        assert decision.should_exit is False
        assert decision.tp1_hit is True
        assert decision.trailing_active is True
        assert decision.new_stop is not None

    def test_trail_stop_hit_after_tp1(self):
        pos = _pos(current_stop=100.0, milestone_state={"tp1_hit": True, "trailing_stop": 105.0})
        with patch(_NOT_EOD, return_value=False):
            decision = self.strategy.evaluate(pos, 104.0, trending_up_history(20))
        assert decision.should_exit is True
        assert "Trail stop hit" in decision.reason
