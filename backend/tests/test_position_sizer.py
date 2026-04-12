from app.common.position_sizer import compute_position_size


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
