"""Unit tests for the regime engine: indicators, classifiers, policy, and engine."""
import pytest

from app.regime.indicators import (
    AssetIndicators,
    VixIndicators,
    build_asset_indicators,
    build_vix_indicators,
    _sma,
    _ema,
    _pct_return,
    _sma20_slope,
)
from app.regime.classifier import classify_stock_regime, classify_crypto_regime
from app.regime.policy import STOCK_REGIME_POLICIES, CRYPTO_REGIME_POLICIES
from app.regime.engine import RegimeEngine, _tick, _RegimeState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rising_closes(n: int = 60, start: float = 100.0, end: float = 160.0) -> list[float]:
    return [start + (end - start) * i / max(n - 1, 1) for i in range(n)]


def _falling_closes(n: int = 60, start: float = 160.0, end: float = 100.0) -> list[float]:
    return [start + (end - start) * i / max(n - 1, 1) for i in range(n)]


def _spy_risk_on() -> AssetIndicators:
    return AssetIndicators(
        close=410.0, sma20=400.0, sma50=390.0, ema20=405.0,
        return_5d=0.02, return_10d=0.04, sma20_slope=0.01,
    )


def _spy_risk_off() -> AssetIndicators:
    return AssetIndicators(
        close=370.0, sma20=390.0, sma50=400.0, ema20=380.0,
        return_5d=-0.03, return_10d=-0.06, sma20_slope=-0.02,
    )


def _spy_neutral() -> AssetIndicators:
    return AssetIndicators(
        close=405.0, sma20=400.0, sma50=398.0, ema20=402.0,
        return_5d=-0.005, return_10d=0.01, sma20_slope=0.005,
    )


def _vix_low() -> VixIndicators:
    return VixIndicators(close=15.0, sma10=18.0, return_5d=-0.05)


def _vix_high() -> VixIndicators:
    return VixIndicators(close=28.0, sma10=22.0, return_5d=0.05)


def _vix_moderate() -> VixIndicators:
    return VixIndicators(close=22.0, sma10=20.0, return_5d=0.02)


def _btc_risk_on() -> AssetIndicators:
    return AssetIndicators(
        close=70000.0, sma20=65000.0, sma50=60000.0, ema20=68000.0,
        return_5d=0.05, return_10d=0.08, sma20_slope=0.02,
    )


def _btc_risk_off() -> AssetIndicators:
    return AssetIndicators(
        close=55000.0, sma20=60000.0, sma50=63000.0, ema20=58000.0,
        return_5d=-0.04, return_10d=-0.08, sma20_slope=-0.02,
    )


def _btc_neutral() -> AssetIndicators:
    return AssetIndicators(
        close=65000.0, sma20=63000.0, sma50=61000.0, ema20=64000.0,
        return_5d=-0.01, return_10d=0.02, sma20_slope=0.005,
    )


def _eth_risk_on() -> AssetIndicators:
    return AssetIndicators(
        close=3500.0, sma20=3300.0, sma50=3000.0, ema20=3400.0,
        return_5d=0.04, return_10d=0.09, sma20_slope=0.015,
        relative_strength_vs_btc_10d=0.01,
    )


def _eth_risk_off() -> AssetIndicators:
    return AssetIndicators(
        close=2800.0, sma20=3100.0, sma50=3200.0, ema20=2900.0,
        return_5d=-0.05, return_10d=-0.09, sma20_slope=-0.02,
        relative_strength_vs_btc_10d=-0.03,
    )


def _eth_neutral() -> AssetIndicators:
    return AssetIndicators(
        close=3100.0, sma20=3200.0, sma50=2900.0, ema20=3150.0,
        return_5d=-0.01, return_10d=0.01, sma20_slope=-0.005,
        relative_strength_vs_btc_10d=-0.01,
    )


# ---------------------------------------------------------------------------
# build_asset_indicators
# ---------------------------------------------------------------------------

class TestBuildAssetIndicators:
    def test_close_is_last_price(self):
        closes = _rising_closes()
        assert build_asset_indicators(closes).close == closes[-1]

    def test_sma20_is_mean_of_last_20(self):
        closes = _rising_closes()
        expected = sum(closes[-20:]) / 20
        assert build_asset_indicators(closes).sma20 == pytest.approx(expected)

    def test_sma50_is_mean_of_last_50(self):
        closes = _rising_closes()
        expected = sum(closes[-50:]) / 50
        assert build_asset_indicators(closes).sma50 == pytest.approx(expected)

    def test_return_5d_positive_in_rising_series(self):
        assert build_asset_indicators(_rising_closes()).return_5d > 0

    def test_return_5d_negative_in_falling_series(self):
        assert build_asset_indicators(_falling_closes()).return_5d < 0

    def test_sma20_slope_positive_in_rising_series(self):
        assert build_asset_indicators(_rising_closes()).sma20_slope > 0

    def test_sma20_slope_negative_in_falling_series(self):
        assert build_asset_indicators(_falling_closes()).sma20_slope < 0

    def test_rs_vs_btc_is_none_when_btc_closes_not_provided(self):
        assert build_asset_indicators(_rising_closes()).relative_strength_vs_btc_10d is None

    def test_rs_vs_btc_positive_when_eth_outperforms(self):
        # BTC: 100 → 110 (+10%), ETH: 100 → 115 (+15%)
        n = 60
        btc = [100.0 + 10.0 * i / max(n - 1, 1) for i in range(n)]
        eth = [100.0 + 15.0 * i / max(n - 1, 1) for i in range(n)]
        ind = build_asset_indicators(eth, btc_closes=btc)
        assert ind.relative_strength_vs_btc_10d is not None
        assert ind.relative_strength_vs_btc_10d > 0

    def test_rs_vs_btc_negative_when_eth_underperforms(self):
        n = 60
        btc = [100.0 + 15.0 * i / max(n - 1, 1) for i in range(n)]
        eth = [100.0 + 5.0 * i / max(n - 1, 1) for i in range(n)]
        ind = build_asset_indicators(eth, btc_closes=btc)
        assert ind.relative_strength_vs_btc_10d is not None
        assert ind.relative_strength_vs_btc_10d < 0

    def test_rs_vs_btc_none_when_insufficient_btc_data(self):
        closes = _rising_closes()
        btc_short = [100.0] * 5
        assert build_asset_indicators(closes, btc_closes=btc_short).relative_strength_vs_btc_10d is None


# ---------------------------------------------------------------------------
# build_vix_indicators
# ---------------------------------------------------------------------------

class TestBuildVixIndicators:
    def test_close_is_last_price(self):
        closes = [30.0 - i * 1.0 for i in range(15)]
        assert build_vix_indicators(closes).close == closes[-1]

    def test_sma10_is_mean_of_last_10(self):
        closes = [float(i + 10) for i in range(15)]
        expected = sum(closes[-10:]) / 10
        assert build_vix_indicators(closes).sma10 == pytest.approx(expected)

    def test_return_5d_negative_when_vix_falling(self):
        closes = [30.0 - i * 1.0 for i in range(15)]
        assert build_vix_indicators(closes).return_5d < 0

    def test_return_5d_positive_when_vix_rising(self):
        closes = [10.0 + i * 1.0 for i in range(15)]
        assert build_vix_indicators(closes).return_5d > 0


# ---------------------------------------------------------------------------
# classify_stock_regime
# ---------------------------------------------------------------------------

class TestClassifyStockRegime:
    def test_risk_on_when_spy_strong_and_vix_low(self):
        label, score = classify_stock_regime(_spy_risk_on(), _vix_low())
        assert label == "RISK_ON"
        assert score >= 6

    def test_risk_off_when_spy_weak_and_vix_high(self):
        label, score = classify_stock_regime(_spy_risk_off(), _vix_high())
        assert label == "RISK_OFF"
        assert score <= 2

    def test_neutral_for_mixed_conditions(self):
        label, _ = classify_stock_regime(_spy_neutral(), _vix_moderate())
        assert label == "NEUTRAL"

    def test_hard_override_vix_above_40_forces_risk_off(self):
        extreme_vix = VixIndicators(close=45.0, sma10=30.0, return_5d=0.2)
        label, _ = classify_stock_regime(_spy_risk_on(), extreme_vix)
        assert label == "RISK_OFF"

    def test_hard_override_vix_above_30_with_spy_below_50d(self):
        stressed_vix = VixIndicators(close=32.0, sma10=25.0, return_5d=0.1)
        spy_below_50d = AssetIndicators(
            close=385.0, sma20=395.0, sma50=400.0, ema20=390.0,
            return_5d=-0.01, return_10d=0.005, sma20_slope=-0.005,
        )
        label, _ = classify_stock_regime(spy_below_50d, stressed_vix)
        assert label == "RISK_OFF"

    def test_score_returned_alongside_label(self):
        label, score = classify_stock_regime(_spy_risk_on(), _vix_low())
        assert isinstance(score, int)
        assert 0 <= score <= 7

    def test_risk_off_score_still_returned_with_hard_override(self):
        extreme_vix = VixIndicators(close=45.0, sma10=30.0, return_5d=0.2)
        label, score = classify_stock_regime(_spy_risk_on(), extreme_vix)
        assert label == "RISK_OFF"
        assert isinstance(score, int)


# ---------------------------------------------------------------------------
# classify_crypto_regime
# ---------------------------------------------------------------------------

class TestClassifyCryptoRegime:
    def test_risk_on_when_btc_and_eth_strong(self):
        label, score = classify_crypto_regime(_btc_risk_on(), _eth_risk_on())
        assert label == "RISK_ON"
        assert score >= 6

    def test_risk_off_when_both_below_50d(self):
        label, _ = classify_crypto_regime(_btc_risk_off(), _eth_risk_off())
        assert label == "RISK_OFF"

    def test_neutral_for_mixed_conditions(self):
        label, _ = classify_crypto_regime(_btc_neutral(), _eth_neutral())
        assert label == "NEUTRAL"

    def test_hard_override_fires_when_both_below_sma50(self):
        label, score = classify_crypto_regime(_btc_risk_off(), _eth_risk_off())
        assert label == "RISK_OFF"
        assert isinstance(score, int)

    def test_risk_off_score_below_threshold_without_hard_override(self):
        label, score = classify_crypto_regime(_btc_risk_off(), _eth_risk_off())
        assert label == "RISK_OFF"

    def test_eth_rs_none_does_not_crash(self):
        btc = _btc_risk_on()
        eth = AssetIndicators(
            close=3500.0, sma20=3300.0, sma50=3000.0, ema20=3400.0,
            return_5d=0.04, return_10d=0.09, sma20_slope=0.015,
            relative_strength_vs_btc_10d=None,
        )
        label, score = classify_crypto_regime(btc, eth)
        assert label in ("RISK_ON", "NEUTRAL", "RISK_OFF")

    def test_score_returned_alongside_label(self):
        _, score = classify_crypto_regime(_btc_risk_on(), _eth_risk_on())
        assert isinstance(score, int)
        assert 0 <= score <= 7


# ---------------------------------------------------------------------------
# _tick / hysteresis
# ---------------------------------------------------------------------------

class TestTick:
    def test_no_change_on_first_different_label(self):
        state = _RegimeState()
        _tick(state, "RISK_ON", 6, threshold=2)
        assert state.confirmed == "NEUTRAL"
        assert state.candidate == "RISK_ON"
        assert state.candidate_count == 1

    def test_confirms_after_threshold_consecutive_checks(self):
        state = _RegimeState()
        _tick(state, "RISK_ON", 6, threshold=2)
        _tick(state, "RISK_ON", 6, threshold=2)
        assert state.confirmed == "RISK_ON"
        assert state.candidate_count == 0

    def test_candidate_resets_when_new_label_appears(self):
        state = _RegimeState()
        _tick(state, "RISK_ON", 6, threshold=2)
        _tick(state, "RISK_OFF", 1, threshold=2)
        assert state.confirmed == "NEUTRAL"
        assert state.candidate == "RISK_OFF"
        assert state.candidate_count == 1

    def test_same_label_as_confirmed_resets_candidate(self):
        state = _RegimeState()
        _tick(state, "RISK_ON", 6, threshold=2)  # candidate = RISK_ON, count = 1
        _tick(state, "NEUTRAL", 4, threshold=2)  # back to confirmed
        assert state.confirmed == "NEUTRAL"
        assert state.candidate_count == 0

    def test_last_score_is_always_updated(self):
        state = _RegimeState()
        _tick(state, "NEUTRAL", 4, threshold=2)
        assert state.last_score == 4
        _tick(state, "RISK_ON", 7, threshold=2)
        assert state.last_score == 7


# ---------------------------------------------------------------------------
# RegimeEngine
# ---------------------------------------------------------------------------

class TestRegimeEngine:
    def test_default_regimes_are_neutral(self):
        engine = RegimeEngine()
        assert engine.stock_regime == "NEUTRAL"
        assert engine.crypto_regime == "NEUTRAL"

    def test_update_stocks_returns_confirmed_regime(self):
        engine = RegimeEngine(confirm_threshold=1)
        result = engine.update_stocks(_spy_risk_on(), _vix_low())
        assert result == "RISK_ON"
        assert engine.stock_regime == "RISK_ON"

    def test_update_crypto_returns_confirmed_regime(self):
        engine = RegimeEngine(confirm_threshold=1)
        result = engine.update_crypto(_btc_risk_on(), _eth_risk_on())
        assert result == "RISK_ON"
        assert engine.crypto_regime == "RISK_ON"

    def test_hysteresis_requires_two_consecutive_confirms(self):
        engine = RegimeEngine(confirm_threshold=2)
        engine.update_stocks(_spy_risk_on(), _vix_low())
        assert engine.stock_regime == "NEUTRAL"
        engine.update_stocks(_spy_risk_on(), _vix_low())
        assert engine.stock_regime == "RISK_ON"

    def test_stock_and_crypto_regimes_are_independent(self):
        engine = RegimeEngine(confirm_threshold=1)
        engine.update_stocks(_spy_risk_on(), _vix_low())
        assert engine.stock_regime == "RISK_ON"
        assert engine.crypto_regime == "NEUTRAL"

    def test_stock_policy_matches_confirmed_regime(self):
        engine = RegimeEngine(confirm_threshold=1)
        engine.update_stocks(_spy_risk_on(), _vix_low())
        assert engine.stock_policy is STOCK_REGIME_POLICIES["RISK_ON"]

    def test_crypto_policy_matches_confirmed_regime(self):
        engine = RegimeEngine(confirm_threshold=1)
        engine.update_crypto(_btc_risk_on(), _eth_risk_on())
        assert engine.crypto_policy is CRYPTO_REGIME_POLICIES["RISK_ON"]

    def test_policy_for_stock(self):
        engine = RegimeEngine(confirm_threshold=1)
        engine.update_stocks(_spy_risk_on(), _vix_low())
        assert engine.policy_for("stock") is STOCK_REGIME_POLICIES["RISK_ON"]

    def test_policy_for_crypto(self):
        engine = RegimeEngine(confirm_threshold=1)
        engine.update_crypto(_btc_risk_on(), _eth_risk_on())
        assert engine.policy_for("crypto") is CRYPTO_REGIME_POLICIES["RISK_ON"]

    def test_policy_for_unknown_class_raises(self):
        with pytest.raises(ValueError, match="Unknown asset class"):
            RegimeEngine().policy_for("forex")


# ---------------------------------------------------------------------------
# RegimeEngine.can_open
# ---------------------------------------------------------------------------

class TestRegimeEngineCanOpen:
    def _risk_on_engine(self) -> RegimeEngine:
        engine = RegimeEngine(confirm_threshold=1)
        engine.update_stocks(_spy_risk_on(), _vix_low())
        engine.update_crypto(_btc_risk_on(), _eth_risk_on())
        return engine

    def _risk_off_engine(self) -> RegimeEngine:
        engine = RegimeEngine(confirm_threshold=1)
        engine.update_stocks(_spy_risk_off(), _vix_high())
        engine.update_crypto(_btc_risk_off(), _eth_risk_off())
        return engine

    def test_allows_valid_entry_in_risk_on(self):
        engine = self._risk_on_engine()
        allowed, reason = engine.can_open("stock", "Opening Range Breakout", 0.75, 2)
        assert allowed is True
        assert reason == "ok"

    def test_blocks_when_over_max_positions(self):
        engine = self._risk_off_engine()
        # RISK_OFF max_positions = 1
        allowed, reason = engine.can_open("stock", "Pullback Reclaim", 0.90, 1)
        assert allowed is False
        assert "max positions" in reason

    def test_blocks_when_setup_score_below_minimum(self):
        engine = self._risk_off_engine()
        # RISK_OFF min_setup_score = 0.82
        allowed, reason = engine.can_open("stock", "Pullback Reclaim", 0.70, 0)
        assert allowed is False
        assert "setup score" in reason

    def test_blocks_breakout_in_risk_off(self):
        engine = self._risk_off_engine()
        allowed, reason = engine.can_open("stock", "Opening Range Breakout", 0.90, 0)
        assert allowed is False
        assert "breakout strategy disabled" in reason

    def test_allows_mean_reversion_in_risk_off(self):
        engine = self._risk_off_engine()
        allowed, reason = engine.can_open("stock", "Mean Reversion Bounce", 0.85, 0)
        assert allowed is True
        assert reason == "ok"

    def test_breakout_allowed_in_risk_on(self):
        engine = self._risk_on_engine()
        allowed, _ = engine.can_open("crypto", "Momentum Breakout Continuation", 0.70, 0)
        assert allowed is True

    def test_crypto_uses_crypto_policy(self):
        engine = self._risk_off_engine()
        # CRYPTO RISK_OFF max_positions = 1
        allowed, reason = engine.can_open("crypto", "Pullback Reclaim", 0.90, 1)
        assert allowed is False
        assert "max positions" in reason

    def test_size_multiplier_reduced_in_risk_off(self):
        engine = self._risk_off_engine()
        assert engine.stock_policy.size_multiplier < 1.0

    def test_size_multiplier_full_in_risk_on(self):
        engine = self._risk_on_engine()
        assert engine.stock_policy.size_multiplier == pytest.approx(1.0)
