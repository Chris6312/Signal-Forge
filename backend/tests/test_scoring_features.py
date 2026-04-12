import json
import pytest

from app.stocks.strategies.entry_strategies import evaluate_all as evaluate_stocks
from app.crypto.strategies.entry_strategies import evaluate_all as evaluate_crypto
from app.common.watchlist_schema_v4 import compute_features_for_signal, compute_strategy_score
from tests.conftest import (
    trending_up_history,
    ranging_history,
    make_bar,
    trending_up_ohlcv,
    ranging_ohlcv,
    make_candle,
)


def _extract_audit_from_caplog(caplog):
    for rec in caplog.records:
        if "BOT_STRATEGY_DECISION" in rec.getMessage():
            parts = rec.getMessage().split("|", 2)
            return json.loads(parts[2].strip())
    return None


def test_non_zero_score_for_valid_trend_continuation(caplog):
    caplog.set_level("INFO")
    base = trending_up_history(65)
    evaluate_stocks("AAPL", base, ai_hint=None, payload_meta={"schema_version": "bot_watchlist_v4"})
    payload = _extract_audit_from_caplog(caplog)
    assert payload is not None
    scores = payload["evaluated_strategy_scores"]
    assert scores.get("trend_continuation", 0.0) > 0.0
    # Should outrank at least one other
    others = [v for k, v in scores.items() if k != "trend_continuation"]
    assert any(scores["trend_continuation"] > o for o in others)


def test_differentiated_scores_across_strategies(caplog):
    caplog.set_level("INFO")
    base = ranging_history(80)
    evaluate_stocks("AAPL", base, ai_hint=None, payload_meta={"schema_version": "bot_watchlist_v4"})
    payload = _extract_audit_from_caplog(caplog)
    assert payload is not None
    vals = list(payload["evaluated_strategy_scores"].values())
    # Not all four strategies should have identical scores
    assert not all(v == vals[0] for v in vals)


def test_pullback_reclaim_prefers_reclaim_chart(caplog):
    caplog.set_level("INFO")
    base = trending_up_history(56, start=100.0, end=180.0)
    for _ in range(5):
        base.append(make_bar(155.0))
    base.append(make_bar(175.0))
    evaluate_stocks("AAPL", base, ai_hint=None, payload_meta={"schema_version": "bot_watchlist_v4"})
    payload = _extract_audit_from_caplog(caplog)
    assert payload is not None
    scores = payload["evaluated_strategy_scores"]
    pr = scores.get("pullback_reclaim", 0.0)
    tc = scores.get("trend_continuation", 0.0)
    orb = scores.get("opening_range_breakout", 0.0)
    vcb = scores.get("volatility_compression_breakout", 0.0)
    assert pr >= tc and pr >= orb and pr >= vcb


def test_opening_range_breakout_prefers_breakout_chart(caplog):
    caplog.set_level("INFO")
    base = trending_up_history(64, start=100.0, end=199.0)
    base.append(make_bar(215.0, spread=0.01))
    evaluate_stocks("AAPL", base, ai_hint=None, payload_meta={"schema_version": "bot_watchlist_v4"})
    payload = _extract_audit_from_caplog(caplog)
    assert payload is not None
    scores = payload["evaluated_strategy_scores"]
    orb = scores.get("opening_range_breakout", 0.0)
    assert orb >= max(v for k, v in scores.items() if k != "opening_range_breakout")


def test_mean_reversion_bounce_prefers_stretch_reversal_chart(caplog):
    caplog.set_level("INFO")
    base = ranging_history(58, center=100.0, amplitude=1.5)
    base.append(make_bar(95.0))
    base.append(make_bar(97.0))
    evaluate_stocks("AAPL", base, ai_hint=None, payload_meta={"schema_version": "bot_watchlist_v4"})
    payload = _extract_audit_from_caplog(caplog)
    assert payload is not None
    scores = payload["evaluated_strategy_scores"]
    mrb = scores.get("mean_reversion_bounce", 0.0)
    assert mrb >= max(v for k, v in scores.items() if k != "mean_reversion_bounce")


def test_regime_weight_switch_changes_score_mix():
    # Build a generic feature vector and compare RISK_ON vs RISK_OFF
    class S: pass
    s = S()
    s.reasoning = {"ema20": 100.0, "ema50": 95.0, "current_vs_ema20": 1.0, "atr": 1.0}
    s.regime = "trending_up"
    features = compute_features_for_signal("trend_continuation", s)
    on_score = compute_strategy_score("trend_continuation", features, regime="RISK_ON", asset_class="stock")
    off_score = compute_strategy_score("trend_continuation", features, regime="RISK_OFF", asset_class="stock")
    assert on_score != off_score


def test_crypto_volatility_scaling_differs_from_stock_scaling():
    class S: pass
    s = S()
    s.reasoning = {"ema20": 100.0, "ema50": 95.0, "current_vs_ema20": 1.0, "atr": 2.0}
    s.regime = "trending_up"
    features = compute_features_for_signal("trend_continuation", s, asset_class="crypto")
    stock_score = compute_strategy_score("trend_continuation", features, regime="NEUTRAL", asset_class="stock")
    crypto_score = compute_strategy_score("trend_continuation", features, regime="NEUTRAL", asset_class="crypto")
    assert crypto_score >= stock_score


def test_invalid_strategy_does_not_receive_bias(caplog):
    caplog.set_level("INFO")
    base = trending_up_history(65)
    ai_hint = {"suggested_strategy": "mean_reversion_bounce", "confidence": 0.99}
    evaluate_stocks("AAPL", base, ai_hint=ai_hint, payload_meta={"schema_version": "bot_watchlist_v4"})
    payload = _extract_audit_from_caplog(caplog)
    assert payload is not None
    assert payload.get("ai_hint_bias_amount") == pytest.approx(0.0)


def test_botdecision_audit_contains_feature_scores(caplog):
    caplog.set_level("INFO")
    base = trending_up_history(65)
    evaluate_stocks("AAPL", base, payload_meta={"schema_version": "bot_watchlist_v4"})
    payload = _extract_audit_from_caplog(caplog)
    assert payload is not None
    assert "evaluated_strategies" in payload
    # Each strategy entry should include feature_scores (may be empty dict for invalid)
    for k, v in payload["evaluated_strategies"].items():
        assert "feature_scores" in v or v.get("reason") is not None


def test_no_identical_flat_scores_regression(caplog):
    caplog.set_level("INFO")
    base = trending_up_history(65)
    evaluate_stocks("AAPL", base, payload_meta={"schema_version": "bot_watchlist_v4"})
    payload = _extract_audit_from_caplog(caplog)
    assert payload is not None
    scores = list(payload["evaluated_strategy_scores"].values())
    # ensure not all four are identical
    assert len(set(scores)) > 1


def test_compute_features_activates_trend_and_momentum_for_rich_signal():
    class S: pass
    s = S()
    s.entry_price = 105.0
    s.initial_stop = 101.0
    s.profit_target_1 = 111.0
    s.regime = "trending_up"
    s.reasoning = {
        "signal_schema_version": "v2",
        "ema9": 104.8,
        "ema20": 104.0,
        "ema50": 102.5,
        "ema200": 98.0,
        "ema20_past": 102.9,
        "ema20_history": [102.8, 103.0, 103.3, 103.7, 104.0],
        "current_vs_ema20": 1.0,
        "breakout_pct": 1.8,
        "volume_ratio": 1.4,
        "higher_highs_confirmed": True,
        "higher_lows_confirmed": True,
        "higher_closes_confirmed": True,
        "trigger_type": "continuation",
        "atr": 1.2,
    }
    features = compute_features_for_signal("trend_continuation", s, asset_class="crypto")
    assert features["trend_alignment"] > 0.5
    assert features["momentum"] > 0.35
    assert features["reclaim_or_breakout"] > 0.35


def test_crypto_scores_are_not_flat_zero_with_trending_data(caplog):
    caplog.set_level("INFO")
    evaluate_crypto("SOL/USD", trending_up_ohlcv(80))
    payload = _extract_audit_from_caplog(caplog)
    assert payload is not None
    vals = list(payload["evaluated_strategy_scores"].values())
    assert any(v > 0.0 for v in vals)
    assert len(set(vals)) > 1


def test_crypto_range_rotation_is_suppressed_in_strong_trend(caplog):
    caplog.set_level("INFO")
    evaluate_crypto("SOL/USD", trending_up_ohlcv(80))
    payload = _extract_audit_from_caplog(caplog)
    assert payload is not None
    scores = payload["evaluated_strategy_scores"]
    assert scores.get("range_rotation", 0.0) < scores.get("breakout_retest", 0.0)
    assert scores.get("range_rotation", 0.0) < scores.get("trend_continuation", 0.0)


def test_crypto_breakout_retest_requires_real_retest_context():
    class S: pass
    s = S()
    s.entry_price = 105.0
    s.initial_stop = 101.0
    s.profit_target_1 = 111.0
    s.regime = "trending_up"
    s.reasoning = {
        "signal_schema_version": "v2",
        "ema9": 104.8,
        "ema20": 104.0,
        "ema50": 102.5,
        "ema200": 98.0,
        "ema20_past": 102.9,
        "ema20_history": [102.8, 103.0, 103.3, 103.7, 104.0],
        "current_vs_ema20": 1.0,
        "breakout_pct": 1.8,
        "volume_ratio": 1.4,
        "higher_highs_confirmed": True,
        "higher_lows_confirmed": True,
        "higher_closes_confirmed": True,
        "trigger_type": "breakout",
        "atr": 1.2,
        "prior_high_40": 103.5,
        "breakout_high_10": 106.0,
        "retest_low": 103.7,
        "price_in_retest_band": True,
        "raw_signal_present": True,
    }
    with_retest = compute_features_for_signal("breakout_retest", s, asset_class="crypto")
    score_with_retest = compute_strategy_score("breakout_retest", with_retest, regime="trending_up", asset_class="crypto")

    s2 = S()
    s2.entry_price = s.entry_price
    s2.initial_stop = s.initial_stop
    s2.profit_target_1 = s.profit_target_1
    s2.regime = s.regime
    s2.reasoning = dict(s.reasoning)
    s2.reasoning["retest_low"] = 100.0
    s2.reasoning["price_in_retest_band"] = False
    without_retest = compute_features_for_signal("breakout_retest", s2, asset_class="crypto")
    score_without_retest = compute_strategy_score("breakout_retest", without_retest, regime="trending_up", asset_class="crypto")

    assert score_with_retest > score_without_retest


def test_crypto_breakout_retest_outscores_range_rotation_on_retest_setup():
    class S: pass
    s = S()
    s.entry_price = 105.0
    s.initial_stop = 101.0
    s.profit_target_1 = 111.0
    s.regime = "trending_up"
    s.reasoning = {
        "signal_schema_version": "v2",
        "ema9": 104.8,
        "ema20": 104.0,
        "ema50": 102.5,
        "ema200": 98.0,
        "ema20_past": 102.9,
        "ema20_history": [102.8, 103.0, 103.3, 103.7, 104.0],
        "current_vs_ema20": 1.0,
        "breakout_pct": 1.8,
        "volume_ratio": 1.4,
        "higher_highs_confirmed": True,
        "higher_lows_confirmed": True,
        "higher_closes_confirmed": True,
        "trigger_type": "breakout",
        "atr": 1.2,
        "prior_high_40": 103.5,
        "breakout_high_10": 106.0,
        "retest_low": 103.7,
        "price_in_retest_band": True,
        "raw_signal_present": True,
    }
    features = compute_features_for_signal("breakout_retest", s, asset_class="crypto")
    breakout_retest = compute_strategy_score("breakout_retest", features, regime="trending_up", asset_class="crypto")
    range_rotation = compute_strategy_score("range_rotation", features, regime="trending_up", asset_class="crypto")
    assert breakout_retest > range_rotation


def test_stock_opening_range_breakout_scores_above_pullback_on_orb_setup():
    class S: pass
    s = S()
    s.entry_price = 108.0
    s.initial_stop = 104.0
    s.profit_target_1 = 114.0
    s.regime = "trending_up"
    s.reasoning = {
        "signal_schema_version": "v2",
        "ema9": 107.6,
        "ema20": 106.9,
        "ema50": 104.8,
        "ema200": 100.5,
        "ema20_past": 105.8,
        "ema20_history": [105.2, 105.5, 105.9, 106.4, 106.9],
        "current_vs_ema20": 1.1,
        "breakout_pct": 3.2,
        "volume_ratio": 1.7,
        "higher_highs_confirmed": True,
        "higher_lows_confirmed": True,
        "higher_closes_confirmed": True,
        "trigger_type": "breakout",
        "atr": 1.4,
        "opening_range_high": 104.5,
        "opening_range_low": 100.8,
        "bars_in_session": 5,
        "raw_signal_present": True,
    }
    features = compute_features_for_signal("opening_range_breakout", s, asset_class="stock")
    opening_range = compute_strategy_score("opening_range_breakout", features, regime="trending_up", asset_class="stock")
    pullback = compute_strategy_score("pullback_reclaim", features, regime="trending_up", asset_class="stock")
    assert opening_range > pullback


def test_wrong_regime_mean_reversion_is_suppressed():
    class S: pass
    s = S()
    s.entry_price = 95.0
    s.initial_stop = 92.0
    s.profit_target_1 = 99.0
    s.regime = "trending_up"
    s.reasoning = {
        "signal_schema_version": "v2",
        "ema9": 95.5,
        "ema20": 95.2,
        "ema50": 94.8,
        "ema200": 92.0,
        "ema20_past": 95.1,
        "ema20_history": [95.0, 95.1, 95.15, 95.18, 95.2],
        "current_vs_ema20": -0.2,
        "breakout_pct": -0.4,
        "volume_ratio": 0.9,
        "higher_highs_confirmed": False,
        "higher_lows_confirmed": False,
        "higher_closes_confirmed": False,
        "trigger_type": "mean_reversion",
        "atr": 1.0,
        "bounce_confirmed": True,
        "raw_signal_present": True,
    }
    features = compute_features_for_signal("mean_reversion_bounce", s, asset_class="stock")
    mean_reversion = compute_strategy_score("mean_reversion_bounce", features, regime="trending_up", asset_class="stock")
    trend_continuation = compute_strategy_score("trend_continuation", features, regime="trending_up", asset_class="stock")
    assert trend_continuation == pytest.approx(0.0)
    assert mean_reversion < 0.10
