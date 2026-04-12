import pytest

from app.common.position_sizer import compute_drawdown_risk_multiplier, compute_position_size, compute_volatility_multiplier
from app.common.portfolio_exposure import compute_cluster_exposure_multiplier
from app.common.risk_config import resolve_baseline_atr_percent


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


@pytest.mark.parametrize(
    ("drawdown_pct", "expected"),
    [
        (0.0, 1.0),
        (2.99, 1.0),
        (3.0, 0.8),
        (5.99, 0.8),
        (6.0, 0.6),
        (9.99, 0.6),
        (10.0, 0.4),
        (25.0, 0.4),
    ],
)
def test_compute_drawdown_risk_multiplier_thresholds(drawdown_pct, expected):
    assert compute_drawdown_risk_multiplier(drawdown_pct) == pytest.approx(expected)


@pytest.mark.parametrize("invalid_drawdown", [None, -1.0, float("nan"), "bad"])
def test_compute_drawdown_risk_multiplier_invalid_inputs_are_neutral(invalid_drawdown):
    assert compute_drawdown_risk_multiplier(invalid_drawdown) == pytest.approx(1.0)


def test_missing_drawdown_context_keeps_sizing_neutral():
    with_drawdown_context = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=10000.0,
        peak_equity=10000.0,
    )
    without_drawdown_context = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
    )

    assert without_drawdown_context == pytest.approx(with_drawdown_context)


def test_deeper_drawdown_reduces_integrated_position_size():
    neutral = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=10000.0,
        peak_equity=10000.0,
    )
    mild = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=9700.0,
        peak_equity=10000.0,
    )
    severe = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=9000.0,
        peak_equity=10000.0,
    )

    assert neutral == pytest.approx(10.0)
    assert mild == pytest.approx(8.0)
    assert severe == pytest.approx(4.0)
    assert severe < mild < neutral


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


def test_atr_present_prefers_atr_based_path(monkeypatch):
    monkeypatch.delenv("BASELINE_ATR_PERCENT", raising=False)

    size = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.03,
        reasoning={"atr": 2.0},
        current_equity=10000.0,
        peak_equity=10000.0,
    )

    assert size == pytest.approx(15.0)


def test_atr_absent_uses_legacy_volatility_pct_fallback():
    size = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.03,
        current_equity=10000.0,
        peak_equity=10000.0,
    )

    assert size == pytest.approx(6.0)


def test_invalid_atr_falls_back_like_legacy_volatility_pct():
    invalid_atr_size = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.03,
        reasoning={"atr": "bad"},
        current_equity=10000.0,
        peak_equity=10000.0,
    )
    fallback_size = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.03,
        current_equity=10000.0,
        peak_equity=10000.0,
    )

    assert invalid_atr_size == pytest.approx(fallback_size)


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


@pytest.mark.parametrize(
    ("current_cluster_notional", "expected_multiplier"),
    [
        (999.0, 1.0),
        (1000.0, 0.8),
        (1999.0, 0.8),
        (2000.0, 0.6),
        (2999.0, 0.6),
        (3000.0, 0.4),
    ],
)
def test_compute_cluster_exposure_multiplier_threshold_boundaries(current_cluster_notional, expected_multiplier):
    multiplier = compute_cluster_exposure_multiplier(
        symbol="BTC/USD",
        asset_class="crypto",
        proposed_trade_notional=1000.0,
        open_positions=[{"symbol": "BTC/USD", "asset_class": "crypto", "market_value": current_cluster_notional}],
        account_equity=10000.0,
    )

    assert multiplier == pytest.approx(expected_multiplier)


@pytest.mark.parametrize(
    ("symbol", "open_positions", "account_equity"),
    [
        (None, [{"symbol": "BTC/USD", "asset_class": "crypto", "market_value": 3000.0}], 10000.0),
        ("BTC/USD", None, 10000.0),
        ("BTC/USD", [{"symbol": "BTC/USD", "asset_class": "crypto", "market_value": 3000.0}], None),
        ("BTC/USD", [{"symbol": "BTC/USD", "asset_class": "crypto", "market_value": 3000.0}], 0.0),
    ],
)
def test_cluster_exposure_multiplier_neutral_when_context_is_missing_or_invalid(symbol, open_positions, account_equity):
    assert compute_cluster_exposure_multiplier(
        symbol=symbol,
        asset_class="crypto",
        proposed_trade_notional=1000.0,
        open_positions=open_positions,
        account_equity=account_equity,
    ) == pytest.approx(1.0)


def test_integrated_cluster_concentration_reduces_position_size():
    no_concentration = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=10000.0,
        peak_equity=10000.0,
        symbol="BTC/USD",
        open_positions=[],
    )
    concentrated = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=10000.0,
        peak_equity=10000.0,
        symbol="BTC/USD",
        open_positions=[{"symbol": "BTC/USD", "asset_class": "crypto", "market_value": 3000.0}],
    )

    assert no_concentration == pytest.approx(10.0)
    assert concentrated == pytest.approx(4.0)
    assert concentrated < no_concentration


def test_missing_cluster_context_keeps_position_size_neutral():
    baseline = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=10000.0,
        peak_equity=10000.0,
    )

    missing_symbol = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=10000.0,
        peak_equity=10000.0,
        open_positions=[{"symbol": "BTC/USD", "asset_class": "crypto", "market_value": 3000.0}],
    )
    missing_open_positions = compute_position_size(
        asset_class="crypto",
        equity=10000.0,
        entry_price=100.0,
        stop_distance=5.0,
        risk_per_trade_pct=0.005,
        volatility_pct=0.005,
        current_equity=10000.0,
        peak_equity=10000.0,
        symbol="BTC/USD",
    )

    assert missing_symbol == pytest.approx(baseline)
    assert missing_open_positions == pytest.approx(baseline)


def test_unknown_symbol_uses_fallback_cluster_deterministically():
    with_open_positions = compute_cluster_exposure_multiplier(
        symbol="unknown-token/usd",
        asset_class="crypto",
        proposed_trade_notional=1000.0,
        open_positions=[{"symbol": "another-unknown/usd", "asset_class": "crypto", "market_value": 1000.0}],
        account_equity=10000.0,
    )
    repeated_call = compute_cluster_exposure_multiplier(
        symbol="unknown-token/usd",
        asset_class="crypto",
        proposed_trade_notional=1000.0,
        open_positions=[{"symbol": "another-unknown/usd", "asset_class": "crypto", "market_value": 1000.0}],
        account_equity=10000.0,
    )

    assert with_open_positions == pytest.approx(0.8)
    assert repeated_call == pytest.approx(with_open_positions)
