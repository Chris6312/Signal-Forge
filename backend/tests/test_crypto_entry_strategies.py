"""Unit tests for crypto entry strategies and their helper functions."""
import pytest

from app.crypto.strategies.entry_strategies import (
    _ema,
    _atr,
    _detect_regime,
    MomentumBreakoutContinuation,
    PullbackReclaim,
    MeanReversionBounce,
    RangeRotationReversal,
    EntrySignal,
    evaluate_all,
)
from tests.conftest import (
    make_candle,
    trending_up_ohlcv,
    trending_down_ohlcv,
    ranging_ohlcv,
)


# ---------------------------------------------------------------------------
# _ema
# ---------------------------------------------------------------------------

class TestEma:
    def test_returns_empty_when_prices_below_period(self):
        assert _ema([1.0, 2.0], period=5) == []

    def test_seed_equals_mean_of_first_period(self):
        ema = _ema([1.0, 2.0, 3.0, 4.0, 5.0], period=3)
        assert ema[0] == pytest.approx(2.0)  # mean(1, 2, 3)

    def test_ema_length_matches_prices_beyond_period(self):
        prices = [float(i) for i in range(1, 11)]
        ema = _ema(prices, period=3)
        assert len(ema) == len(prices) - 3 + 1  # seed + remaining bars

    def test_ema_rises_with_increasing_prices(self):
        prices = [float(i) for i in range(1, 22)]
        ema = _ema(prices, period=5)
        assert ema[-1] > ema[0]

    def test_exact_period_returns_single_seed(self):
        ema = _ema([10.0, 20.0, 30.0], period=3)
        assert len(ema) == 1
        assert ema[0] == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# _atr
# ---------------------------------------------------------------------------

class TestAtr:
    def test_returns_zero_when_insufficient_data(self):
        ohlcv = [make_candle(i, 100.0) for i in range(5)]
        assert _atr(ohlcv, period=14) == 0.0

    def test_returns_positive_for_valid_data(self):
        ohlcv = trending_up_ohlcv(30)
        assert _atr(ohlcv) > 0.0

    def test_wider_spread_yields_higher_atr(self):
        tight = [make_candle(i, 100.0, spread=0.001) for i in range(30)]
        wide = [make_candle(i, 100.0, spread=0.05) for i in range(30)]
        assert _atr(wide) > _atr(tight)


# ---------------------------------------------------------------------------
# _detect_regime
# ---------------------------------------------------------------------------

class TestDetectRegime:
    def test_unknown_when_insufficient_data(self):
        ohlcv = [make_candle(i, 100.0) for i in range(30)]
        assert _detect_regime(ohlcv) == "unknown"

    def test_trending_up(self):
        assert _detect_regime(trending_up_ohlcv(65)) == "trending_up"

    def test_trending_down(self):
        assert _detect_regime(trending_down_ohlcv(65)) == "trending_down"

    def test_ranging(self):
        assert _detect_regime(ranging_ohlcv(65)) == "ranging"


# ---------------------------------------------------------------------------
# MomentumBreakoutContinuation
# ---------------------------------------------------------------------------

class TestMomentumBreakoutContinuation:
    def setup_method(self):
        self.strategy = MomentumBreakoutContinuation()

    def test_returns_none_with_insufficient_data(self):
        assert self.strategy.evaluate("BTC/USD", [make_candle(i, 100.0) for i in range(20)]) is None

    def test_returns_none_for_ranging_regime(self):
        assert self.strategy.evaluate("BTC/USD", ranging_ohlcv(65)) is None

    def test_returns_none_for_trending_down(self):
        assert self.strategy.evaluate("BTC/USD", trending_down_ohlcv(65)) is None

    def test_returns_signal_on_clear_breakout(self):
        # 64 trending candles then a decisive breakout candle
        base = trending_up_ohlcv(64, start=100.0, end=199.0)
        base.append(make_candle(64, 215.0, spread=0.002))

        signal = self.strategy.evaluate("BTC/USD", base)

        assert signal is not None
        assert isinstance(signal, EntrySignal)
        assert signal.symbol == "BTC/USD"
        assert signal.entry_price == pytest.approx(215.0)
        assert signal.initial_stop < 215.0
        assert signal.profit_target_1 > 215.0
        assert signal.profit_target_2 > signal.profit_target_1
        assert signal.regime == "trending_up"

    def test_returns_none_when_current_below_recent_high(self):
        ohlcv = trending_up_ohlcv(65, start=100.0, end=200.0)
        # Replace last candle with one that does not break out
        ohlcv[-1] = make_candle(64, 190.0)
        assert self.strategy.evaluate("BTC/USD", ohlcv) is None


# ---------------------------------------------------------------------------
# PullbackReclaim
# ---------------------------------------------------------------------------

class TestPullbackReclaim:
    def setup_method(self):
        self.strategy = PullbackReclaim()

    def test_returns_none_with_insufficient_data(self):
        assert self.strategy.evaluate("BTC/USD", [make_candle(i, 100.0) for i in range(20)]) is None

    def test_returns_none_for_ranging_regime(self):
        assert self.strategy.evaluate("BTC/USD", ranging_ohlcv(65)) is None

    def test_returns_signal_after_pullback_and_ema_reclaim(self):
        # 56 trending candles, dip below EMA20 for 5 bars, then recover
        base = trending_up_ohlcv(56, start=100.0, end=180.0)
        for i in range(5):
            base.append(make_candle(56 + i, 155.0))
        base.append(make_candle(61, 175.0))

        signal = self.strategy.evaluate("BTC/USD", base)

        assert signal is not None
        assert signal.entry_price == pytest.approx(175.0)
        assert signal.initial_stop < 175.0
        assert signal.profit_target_1 > 175.0

    def test_returns_none_when_no_prior_dip_below_ema(self):
        # Pure uptrend — every close is above the trailing EMA20
        assert self.strategy.evaluate("BTC/USD", trending_up_ohlcv(65)) is None


# ---------------------------------------------------------------------------
# MeanReversionBounce
# ---------------------------------------------------------------------------

class TestMeanReversionBounce:
    def setup_method(self):
        self.strategy = MeanReversionBounce()

    def test_returns_none_with_insufficient_data(self):
        assert self.strategy.evaluate("BTC/USD", [make_candle(i, 100.0) for i in range(20)]) is None

    def test_returns_none_for_trending_up_regime(self):
        assert self.strategy.evaluate("BTC/USD", trending_up_ohlcv(65)) is None

    def test_returns_signal_when_deeply_below_mean_and_bouncing(self):
        # 58 ranging candles, then drop deep below mean and bounce
        base = ranging_ohlcv(58, center=100.0, amplitude=1.5)
        base.append(make_candle(58, 93.0))
        base.append(make_candle(59, 95.0))

        signal = self.strategy.evaluate("BTC/USD", base)

        assert signal is not None
        assert signal.entry_price == pytest.approx(95.0)
        assert signal.initial_stop < 95.0
        assert signal.profit_target_1 > 95.0

    def test_returns_none_when_not_deep_enough_below_mean(self):
        # Only ~1 % below mean — below the 3 % threshold
        base = ranging_ohlcv(58, center=100.0, amplitude=1.5)
        base.append(make_candle(58, 98.5))
        base.append(make_candle(59, 99.0))
        assert self.strategy.evaluate("BTC/USD", base) is None

    def test_returns_none_when_price_still_falling(self):
        # Deep below mean but last close is lower than the prior close
        base = ranging_ohlcv(58, center=100.0, amplitude=1.5)
        base.append(make_candle(58, 95.0))
        base.append(make_candle(59, 93.0))
        assert self.strategy.evaluate("BTC/USD", base) is None


# ---------------------------------------------------------------------------
# RangeRotationReversal
# ---------------------------------------------------------------------------

class TestRangeRotationReversal:
    def setup_method(self):
        self.strategy = RangeRotationReversal()

    def test_returns_none_with_insufficient_data(self):
        assert self.strategy.evaluate("BTC/USD", [make_candle(i, 100.0) for i in range(30)]) is None

    def test_returns_none_for_trending_up_regime(self):
        assert self.strategy.evaluate("BTC/USD", trending_up_ohlcv(65)) is None

    def test_returns_signal_near_range_low_with_three_ascending_closes(self):
        # 57 ranging candles, then 3 ascending candles near the range low.
        # range_low = min(lows[-30:]) ≈ 96.5 * 0.99 = 95.54
        # threshold  = range_low * 1.02          ≈ 97.45
        # current (97.1) must be <= threshold (97.45)
        base = ranging_ohlcv(57, center=100.0, amplitude=2.0)
        base.append(make_candle(57, 96.5))
        base.append(make_candle(58, 97.0))
        base.append(make_candle(59, 97.1))

        signal = self.strategy.evaluate("BTC/USD", base)

        assert signal is not None
        assert signal.entry_price == pytest.approx(97.1)
        assert signal.initial_stop < 98.5

    def test_returns_none_when_price_above_range_low_threshold(self):
        # Mid-range price — not near the range low
        assert self.strategy.evaluate("BTC/USD", ranging_ohlcv(65)) is None


# ---------------------------------------------------------------------------
# evaluate_all
# ---------------------------------------------------------------------------

class TestEvaluateAll:
    def test_returns_list_for_any_ohlcv(self):
        result = evaluate_all("BTC/USD", trending_up_ohlcv(65))
        assert isinstance(result, list)

    def test_returns_empty_list_for_insufficient_data(self):
        result = evaluate_all("BTC/USD", [make_candle(i, 100.0) for i in range(10)])
        assert result == []

    def test_signals_sorted_by_confidence_descending(self):
        base = trending_up_ohlcv(64, start=100.0, end=199.0)
        base.append(make_candle(64, 215.0, spread=0.002))
        result = evaluate_all("BTC/USD", base)
        if len(result) > 1:
            for a, b in zip(result, result[1:]):
                assert a.confidence >= b.confidence

    def test_does_not_raise_on_empty_ohlcv(self):
        result = evaluate_all("BTC/USD", [])
        assert result == []


def test_include_diagnostics_top_strategy_matches_top_signal():
    base = trending_up_ohlcv(64, start=100.0, end=199.0)
    base.append(make_candle(64, 215.0, spread=0.002))
    result = evaluate_all("BTC/USD", base, include_diagnostics=True)
    assert result["top_strategy"] in result["evaluated_strategy_scores"]
    assert result["top_confidence"] == pytest.approx(result["evaluated_strategy_scores"][result["top_strategy"]])
    if result["signals"]:
        top_signal = result["signals"][0]
        assert top_signal.confidence == pytest.approx(result["top_confidence"])


def test_include_diagnostics_adds_crypto_execution_readiness_metadata():
    base = trending_up_ohlcv(64, start=100.0, end=199.0)
    base.append(make_candle(64, 215.0, spread=0.002))
    result = evaluate_all("BTC/USD", base, include_diagnostics=True)
    breakout = next(sig for sig in result["signals"] if sig.strategy == "Breakout Retest Hold")

    assert "execution_ready" in breakout.reasoning
    assert "execution_confidence_cap" in breakout.reasoning
    assert "execution_block_reason" in breakout.reasoning

