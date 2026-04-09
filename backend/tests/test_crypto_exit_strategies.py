"""Unit tests for crypto exit strategies and their helper functions."""
from types import SimpleNamespace

import pytest

from app.crypto.strategies.exit_strategies import (
    _atr,
    _is_trending,
    _stop_confirmed,
    ExitDecision,
    FailedFollowThroughExit,
    FixedRiskDynamicFloor,
    PartialAtTP1DynamicTrail,
)
from tests.conftest import make_candle, trending_up_ohlcv, trending_down_ohlcv


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


def _confirmed_stop_ohlcv(stop: float = 93.0) -> list:
    """Two candles that both close below *stop*, confirming the stop level."""
    return [make_candle(0, stop - 2.0), make_candle(1, stop - 1.0)]


# ---------------------------------------------------------------------------
# _atr
# ---------------------------------------------------------------------------

class TestAtr:
    def test_zero_when_insufficient_data(self):
        assert _atr([make_candle(i, 100.0) for i in range(5)], period=14) == 0.0

    def test_positive_for_valid_data(self):
        assert _atr(trending_up_ohlcv(30)) > 0.0


# ---------------------------------------------------------------------------
# _is_trending
# ---------------------------------------------------------------------------

class TestIsTrending:
    def test_false_when_insufficient_data(self):
        assert _is_trending([make_candle(i, 100.0) for i in range(10)]) is False

    def test_true_for_uptrend(self):
        assert _is_trending(trending_up_ohlcv(25)) is True

    def test_false_for_downtrend(self):
        assert _is_trending(trending_down_ohlcv(25)) is False


# ---------------------------------------------------------------------------
# _stop_confirmed
# ---------------------------------------------------------------------------

class TestStopConfirmed:
    def _two_candles(self, prev_close: float, curr_close: float) -> list:
        return [make_candle(0, prev_close), make_candle(1, curr_close)]

    def test_false_when_price_above_stop(self):
        assert _stop_confirmed(102.0, 95.0, self._two_candles(100.0, 102.0)) is False

    def test_false_when_wick_but_prev_close_above_stop(self):
        # Ticker dipped below stop but prior candle closed above it (wick whipsaw)
        assert _stop_confirmed(94.0, 95.0, self._two_candles(96.0, 94.0)) is False

    def test_true_when_confirmed_by_prior_close(self):
        # Prior candle also closed below stop — genuine break
        assert _stop_confirmed(92.0, 95.0, self._two_candles(94.0, 92.0)) is True

    def test_true_with_no_ohlcv_data(self):
        assert _stop_confirmed(90.0, 95.0, []) is True


# ---------------------------------------------------------------------------
# FixedRiskDynamicFloor
# ---------------------------------------------------------------------------

class TestFixedRiskDynamicFloor:
    def setup_method(self):
        self.strategy = FixedRiskDynamicFloor()

    def test_exit_on_confirmed_stop(self):
        decision = self.strategy.evaluate(_pos(), 91.0, _confirmed_stop_ohlcv())
        assert decision.should_exit is True
        assert "Stop hit" in decision.reason

    def test_holding_between_stop_and_tp1(self):
        decision = self.strategy.evaluate(_pos(), 102.0, trending_up_ohlcv(20))
        assert decision.should_exit is False
        assert decision.reason == "Holding"

    def test_tp1_promotes_stop_to_entry(self):
        decision = self.strategy.evaluate(_pos(), 108.0, trending_up_ohlcv(20))
        assert decision.should_exit is False
        assert decision.new_stop == pytest.approx(100.0)  # max(stop=93, entry=100)

    def test_trailing_floor_hit_after_tp1(self):
        pos = _pos(
            current_stop=100.0,
            milestone_state={"tp1_hit": True, "trailing_stop": 105.0},
        )
        # Both candles close below the trailing stop
        ohlcv = [make_candle(0, 103.0), make_candle(1, 104.0)]
        decision = self.strategy.evaluate(pos, 104.0, ohlcv)
        assert decision.should_exit is True
        assert "Trailing floor hit" in decision.reason

    def test_trailing_floor_raised_in_uptrend(self):
        pos = _pos(
            current_stop=105.0,
            milestone_state={"tp1_hit": True, "trailing_stop": 105.0},
        )
        decision = self.strategy.evaluate(pos, 125.0, trending_up_ohlcv(25))
        assert decision.should_exit is False
        assert decision.trailing_active is True
        assert decision.new_stop is not None
        assert decision.new_stop > 105.0


# ---------------------------------------------------------------------------
# PartialAtTP1DynamicTrail
# ---------------------------------------------------------------------------

class TestPartialAtTP1DynamicTrail:
    def setup_method(self):
        self.strategy = PartialAtTP1DynamicTrail()

    def test_exit_on_confirmed_stop(self):
        ohlcv = [make_candle(0, 91.0), make_candle(1, 90.0)]
        decision = self.strategy.evaluate(_pos(), 90.0, ohlcv)
        assert decision.should_exit is True

    def test_partial_exit_at_tp1(self):
        decision = self.strategy.evaluate(_pos(), 108.0, trending_up_ohlcv(20))
        assert decision.should_exit is False
        assert decision.partial is True
        assert decision.partial_pct == pytest.approx(0.50)
        assert decision.new_stop == pytest.approx(100.0)  # promoted to entry

    def test_holding_before_tp1(self):
        decision = self.strategy.evaluate(_pos(), 104.0, trending_up_ohlcv(20))
        assert decision.should_exit is False
        assert decision.partial is False

    def test_trail_stop_hit_after_tp1(self):
        pos = _pos(
            current_stop=100.0,
            milestone_state={"tp1_hit": True, "trailing_stop": 105.0},
        )
        ohlcv = [make_candle(0, 104.0), make_candle(1, 103.0)]
        decision = self.strategy.evaluate(pos, 103.0, ohlcv)
        assert decision.should_exit is True
        assert "Trail stop hit" in decision.reason


# ---------------------------------------------------------------------------
# FailedFollowThroughExit
# ---------------------------------------------------------------------------

class TestFailedFollowThroughExit:
    def setup_method(self):
        self.strategy = FailedFollowThroughExit()

    def test_exit_on_confirmed_stop(self):
        ohlcv = [make_candle(0, 91.0), make_candle(1, 90.0)]
        decision = self.strategy.evaluate(_pos(), 90.0, ohlcv)
        assert decision.should_exit is True

    def test_exit_on_three_declining_closes_below_entry(self):
        # Three consecutive lower closes, all below entry=100
        ohlcv = [make_candle(i, 99.0 - i * 2.0) for i in range(3)]  # 99, 97, 95
        decision = self.strategy.evaluate(_pos(), 95.0, ohlcv)
        assert decision.should_exit is True
        assert "Failed follow-through" in decision.reason

    def test_holding_when_closes_are_rising(self):
        ohlcv = [make_candle(i, 101.0 + i * 2.0) for i in range(3)]  # 101, 103, 105
        decision = self.strategy.evaluate(_pos(), 105.0, ohlcv)
        assert decision.should_exit is False

    def test_holding_when_insufficient_candles(self):
        decision = self.strategy.evaluate(_pos(), 98.0, [make_candle(0, 98.0)])
        assert decision.should_exit is False
