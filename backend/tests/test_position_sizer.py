import pytest

from app.common.position_sizer import compute_position_size, compute_volatility_multiplier


def test_normal_volatility_returns_baseline_sizing():
    size = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=10000.0,
        peak_equity=10000.0,
    )

    assert size == 10.0


def test_high_volatility_reduces_size():
    base = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=10000.0,
        peak_equity=10000.0,
    )
    high_vol = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.03,
        current_equity=10000.0,
        peak_equity=10000.0,
    )

    assert high_vol < base


def test_drawdown_reduces_size():
    base = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=10000.0,
        peak_equity=10000.0,
    )
    dd = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=9400.0,
        peak_equity=10000.0,
    )

    assert dd < base


def test_combined_high_volatility_and_drawdown_produces_smallest_size():
    base = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=10000.0,
        peak_equity=10000.0,
    )
    high_vol = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.03,
        current_equity=10000.0,
        peak_equity=10000.0,
    )
    combined = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.03,
        current_equity=8800.0,
        peak_equity=10000.0,
    )

    assert combined < high_vol < base


def test_zero_stop_distance_returns_zero():
    assert compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=0.0,
        risk_per_trade_pct=0.005,
    ) == 0.0


def test_volatility_multiplier_neutral_when_atr_matches_baseline():
    assert compute_volatility_multiplier(atr=2.0, price=100.0, baseline_atr_percent=0.02) == pytest.approx(1.0)


def test_volatility_multiplier_reduces_size_when_atr_is_higher(monkeypatch):
    monkeypatch.setenv("BASELINE_ATR_PERCENT", "0.02")

    base = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        reasoning={"atr": 2.0},
        current_equity=10000.0,
        peak_equity=10000.0,
    )
    higher_vol = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        reasoning={"atr": 4.0},
        current_equity=10000.0,
        peak_equity=10000.0,
    )

    assert higher_vol < base
    assert compute_volatility_multiplier(atr=4.0, price=100.0, baseline_atr_percent=0.02) < 1.0


def test_volatility_multiplier_increases_size_when_atr_is_lower(monkeypatch):
    monkeypatch.setenv("BASELINE_ATR_PERCENT", "0.02")

    base = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        reasoning={"atr": 2.0},
        current_equity=10000.0,
        peak_equity=10000.0,
    )
    lower_vol = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        reasoning={"atr": 1.0},
        current_equity=10000.0,
        peak_equity=10000.0,
    )

    assert lower_vol > base
    assert compute_volatility_multiplier(atr=1.0, price=100.0, baseline_atr_percent=0.02) > 1.0


def test_volatility_multiplier_clamps_floor():
    assert compute_volatility_multiplier(atr=100.0, price=100.0, baseline_atr_percent=0.02) == pytest.approx(0.5)


def test_volatility_multiplier_clamps_ceiling():
    assert compute_volatility_multiplier(atr=0.1, price=100.0, baseline_atr_percent=0.02) == pytest.approx(1.5)


def test_volatility_multiplier_invalid_inputs_fall_back_to_one():
    assert compute_volatility_multiplier(atr=0.0, price=100.0, baseline_atr_percent=0.02) == pytest.approx(1.0)
    assert compute_volatility_multiplier(atr=2.0, price=0.0, baseline_atr_percent=0.02) == pytest.approx(1.0)
    assert compute_volatility_multiplier(atr=2.0, price=100.0, baseline_atr_percent=0.0) == pytest.approx(1.0)


def test_extremely_small_equity_returns_zero():
    assert compute_position_size(
        asset_class="crypto",
        equity=5.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=5.0,
        peak_equity=5.0,
    ) == 0.0
