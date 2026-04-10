"""Unit tests for stock entry strategies and their helper functions."""
import pytest

from app.stocks.strategies.entry_strategies import (
    _ema,
    _atr_from_history,
    _detect_regime,
    OpeningRangeBreakout,
    PullbackReclaim,
    TrendContinuationLadder,
    MeanReversionBounce,
    StockEntrySignal,
    evaluate_all,
)
from tests.conftest import (
    make_bar,
    trending_up_history,
    trending_down_history,
    ranging_history,
)


# ---------------------------------------------------------------------------
# _ema
# ---------------------------------------------------------------------------

class TestEma:
    def test_returns_empty_when_prices_below_period(self):
        assert _ema([1.0, 2.0], period=5) == []

    def test_seed_equals_mean_of_first_period(self):
        ema = _ema([1.0, 2.0, 3.0, 4.0, 5.0], period=3)
        assert ema[0] == pytest.approx(2.0)

    def test_ema_rises_with_increasing_prices(self):
        prices = [float(i) for i in range(1, 22)]
        ema = _ema(prices, period=5)
        assert ema[-1] > ema[0]


# ---------------------------------------------------------------------------
# _atr_from_history
# ---------------------------------------------------------------------------

class TestAtrFromHistory:
    def test_zero_when_insufficient_data(self):
        assert _atr_from_history([make_bar(100.0) for _ in range(5)], period=14) == 0.0

    def test_positive_for_valid_data(self):
        assert _atr_from_history(trending_up_history(30)) > 0.0

    def test_wider_spread_yields_higher_atr(self):
        tight = [make_bar(100.0, spread=0.001) for _ in range(30)]
        wide = [make_bar(100.0, spread=0.05) for _ in range(30)]
        assert _atr_from_history(wide) > _atr_from_history(tight)


# ---------------------------------------------------------------------------
# _detect_regime
# ---------------------------------------------------------------------------

class TestDetectRegime:
    def test_unknown_when_insufficient_data(self):
        assert _detect_regime([make_bar(100.0) for _ in range(30)]) == "unknown"

    def test_trending_up(self):
        assert _detect_regime(trending_up_history(65)) == "trending_up"

    def test_trending_down(self):
        assert _detect_regime(trending_down_history(65)) == "trending_down"

    def test_ranging(self):
        assert _detect_regime(ranging_history(65)) == "ranging"


# ---------------------------------------------------------------------------
# OpeningRangeBreakout
# ---------------------------------------------------------------------------

class TestOpeningRangeBreakout:
    def setup_method(self):
        self.strategy = OpeningRangeBreakout()

    def test_returns_none_with_insufficient_data(self):
        assert self.strategy.evaluate("AAPL", [make_bar(100.0) for _ in range(10)]) is None

    def test_returns_none_for_ranging_regime(self):
        assert self.strategy.evaluate("AAPL", ranging_history(65)) is None

    def test_returns_signal_on_clear_breakout(self):
        base = trending_up_history(64, start=100.0, end=199.0)
        base.append(make_bar(215.0, spread=0.002))

        signal = self.strategy.evaluate("AAPL", base)

        assert signal is not None
        assert isinstance(signal, StockEntrySignal)
        assert signal.symbol == "AAPL"
        assert signal.entry_price == pytest.approx(215.0)
        assert signal.initial_stop < 215.0
        assert signal.profit_target_1 > 215.0
        assert signal.profit_target_2 > signal.profit_target_1

    def test_returns_none_when_below_recent_high(self):
        history = trending_up_history(65, start=100.0, end=200.0)
        history[-1] = make_bar(190.0)
        assert self.strategy.evaluate("AAPL", history) is None


# ---------------------------------------------------------------------------
# PullbackReclaim
# ---------------------------------------------------------------------------

class TestPullbackReclaim:
    def setup_method(self):
        self.strategy = PullbackReclaim()

    def test_returns_none_with_insufficient_data(self):
        assert self.strategy.evaluate("AAPL", [make_bar(100.0) for _ in range(20)]) is None

    def test_returns_none_for_ranging_regime(self):
        assert self.strategy.evaluate("AAPL", ranging_history(65)) is None

    def test_returns_signal_after_pullback_and_ema_reclaim(self):
        base = trending_up_history(56, start=100.0, end=180.0)
        for _ in range(5):
            base.append(make_bar(155.0))
        base.append(make_bar(175.0))

        signal = self.strategy.evaluate("AAPL", base)

        assert signal is not None
        assert signal.entry_price == pytest.approx(175.0)
        assert signal.initial_stop < 175.0
        assert signal.profit_target_1 > 175.0

    def test_returns_none_when_no_prior_dip_below_ema(self):
        assert self.strategy.evaluate("AAPL", trending_up_history(65)) is None


# ---------------------------------------------------------------------------
# TrendContinuationLadder
# ---------------------------------------------------------------------------

class TestTrendContinuationLadder:
    def setup_method(self):
        self.strategy = TrendContinuationLadder()

    def test_returns_none_with_insufficient_data(self):
        assert self.strategy.evaluate("AAPL", [make_bar(100.0) for _ in range(30)]) is None

    def test_returns_none_for_ranging_regime(self):
        assert self.strategy.evaluate("AAPL", ranging_history(65)) is None

    def test_returns_signal_with_higher_highs_and_lows(self):
        # Linear uptrend guarantees higher highs and higher lows on every bar
        signal = self.strategy.evaluate("AAPL", trending_up_history(65))
        assert signal is not None
        assert isinstance(signal, StockEntrySignal)
        assert signal.entry_price > 0.0

    def test_returns_none_for_trending_down(self):
        assert self.strategy.evaluate("AAPL", trending_down_history(65)) is None


# ---------------------------------------------------------------------------
# MeanReversionBounce
# ---------------------------------------------------------------------------

class TestMeanReversionBounceStocks:
    def setup_method(self):
        self.strategy = MeanReversionBounce()

    def test_returns_none_with_insufficient_data(self):
        assert self.strategy.evaluate("AAPL", [make_bar(100.0) for _ in range(20)]) is None

    def test_returns_none_for_trending_up_regime(self):
        assert self.strategy.evaluate("AAPL", trending_up_history(65)) is None

    def test_returns_signal_deeply_below_mean_and_bouncing(self):
        # Use a calm baseline (amplitude=0.5) so two deep dip candles do not
        # push EMA20 below EMA50*0.995 and accidentally flip regime to trending_down.
        base = ranging_history(100, center=100.0, amplitude=0.5)
        base.append(make_bar(95.0))
        base.append(make_bar(97.0))  # bouncing: 97 > 95

        signal = self.strategy.evaluate("AAPL", base)

        assert signal is not None
        assert signal.entry_price == pytest.approx(97.0)
        assert signal.initial_stop < 97.0

    def test_returns_none_when_still_falling(self):
        base = ranging_history(100, center=100.0, amplitude=0.5)
        base.append(make_bar(97.0))
        base.append(make_bar(95.0))  # still falling: 95 < 97
        assert self.strategy.evaluate("AAPL", base) is None


# ---------------------------------------------------------------------------
# evaluate_all
# ---------------------------------------------------------------------------

class TestEvaluateAll:
    def test_returns_list_for_any_history(self):
        assert isinstance(evaluate_all("AAPL", trending_up_history(65)), list)

    def test_returns_empty_for_insufficient_data(self):
        assert evaluate_all("AAPL", [make_bar(100.0) for _ in range(5)]) == []

    def test_signals_sorted_by_confidence_descending(self):
        base = trending_up_history(64, start=100.0, end=199.0)
        base.append(make_bar(215.0, spread=0.002))
        result = evaluate_all("AAPL", base)
        if len(result) > 1:
            for a, b in zip(result, result[1:]):
                assert a.confidence >= b.confidence

    def test_does_not_raise_on_empty_history(self):
        assert evaluate_all("AAPL", []) == []


def test_ai_hint_bias_applied_and_capped(caplog):
    # Build a history that yields a PullbackReclaim signal
    base = trending_up_history(56, start=100.0, end=180.0)
    for _ in range(5):
        base.append(make_bar(155.0))
    base.append(make_bar(175.0))

    ai_hint = {"suggested_strategy": "pullback_reclaim", "confidence": 1.0}
    caplog.set_level("INFO")
    signals = evaluate_all("AAPL", base, ai_hint=ai_hint, payload_meta={"schema_version": "bot_watchlist_v4"})
    # Ensure at least one signal returned
    assert isinstance(signals, list)
    # Audit log should contain BOT_STRATEGY_DECISION JSON
    found = False
    for rec in caplog.records:
        if "BOT_STRATEGY_DECISION" in rec.getMessage():
            found = True
            msg = rec.getMessage()
            # JSON payload is after the second pipe
            parts = msg.split("|", 2)
            assert len(parts) == 3
            import json
            payload = json.loads(parts[2].strip())
            assert payload["ai_hint_strategy"] == "pullback_reclaim"
            assert payload["ai_hint_bias_amount"] == pytest.approx(0.03)
            assert payload["ai_hint_agreement"] is True
    assert found


def test_ai_hint_does_not_make_invalid_strategy_valid(caplog):
    # trending up history — mean reversion should be invalid
    base = trending_up_history(65)
    ai_hint = {"suggested_strategy": "mean_reversion_bounce", "confidence": 0.99}
    caplog.set_level("INFO")
    signals = evaluate_all("AAPL", base, ai_hint=ai_hint, payload_meta={"schema_version": "bot_watchlist_v4"})
    # Check audit payload shows mean_reversion_bounce rejected
    found = False
    for rec in caplog.records:
        if "BOT_STRATEGY_DECISION" in rec.getMessage():
            found = True
            import json
            parts = rec.getMessage().split("|", 2)
            payload = json.loads(parts[2].strip())
            assert payload["ai_hint_strategy"] == "mean_reversion_bounce"
            # bot should disagree (selected different strategy or none)
            assert payload.get("ai_hint_agreement") in (False, None)
            # bias amount must be zero for an invalid strategy
            assert payload["ai_hint_bias_amount"] == pytest.approx(0.0)
    assert found


def test_no_ai_hint_means_zero_bias(caplog):
    base = trending_up_history(56, start=100.0, end=180.0)
    for _ in range(5):
        base.append(make_bar(155.0))
    base.append(make_bar(175.0))
    caplog.set_level("INFO")
    signals = evaluate_all("AAPL", base, ai_hint=None, payload_meta={"schema_version": "bot_watchlist_v4"})
    found = False
    for rec in caplog.records:
        if "BOT_STRATEGY_DECISION" in rec.getMessage():
            found = True
            import json
            parts = rec.getMessage().split("|", 2)
            payload = json.loads(parts[2].strip())
            assert payload["ai_hint_bias_amount"] == pytest.approx(0.0)
            assert payload["ai_hint_strategy"] is None
    assert found
