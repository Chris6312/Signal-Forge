from app.common.portfolio_exposure import compute_portfolio_concentration_multiplier


def test_under_limit_returns_one():
    assert compute_portfolio_concentration_multiplier(
        total_open_risk_pct=0.04,
        max_total_risk_pct=0.06,
    ) == 1.0


def test_equal_limit_returns_zero():
    assert compute_portfolio_concentration_multiplier(
        total_open_risk_pct=0.06,
        max_total_risk_pct=0.06,
    ) == 0.0


def test_above_limit_returns_zero():
    assert compute_portfolio_concentration_multiplier(
        total_open_risk_pct=0.08,
        max_total_risk_pct=0.06,
    ) == 0.0


def test_none_input_safe():
    assert compute_portfolio_concentration_multiplier(
        total_open_risk_pct=None,
        max_total_risk_pct=0.06,
    ) == 1.0


def test_zero_limit_safe():
    assert compute_portfolio_concentration_multiplier(
        total_open_risk_pct=0.05,
        max_total_risk_pct=0.0,
    ) == 1.0
