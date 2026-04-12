from __future__ import annotations

from app.common.risk_config import _coerce_float


def compute_breakout_extension_pct(price: float, breakout_level: float) -> float:
    price_value = _coerce_float(price, finite_only=True)
    breakout_value = _coerce_float(breakout_level, finite_only=True)
    if price_value is None or breakout_value is None or breakout_value <= 0:
        return 0.0
    if price_value <= breakout_value:
        return 0.0
    return ((price_value - breakout_value) / breakout_value) * 100.0


def compute_support_distance_pct(price: float, support_level: float) -> float:
    price_value = _coerce_float(price, finite_only=True)
    support_value = _coerce_float(support_level, finite_only=True)
    if price_value is None or support_value is None or support_value <= 0 or price_value <= 0:
        return 0.0
    return abs(price_value - support_value) / support_value * 100.0


def classify_signal_maturity(
    breakout_extension_pct: float,
    support_distance_pct: float,
    has_acceptance: bool,
) -> str:
    breakout_value = _coerce_float(breakout_extension_pct, finite_only=True)
    support_value = _coerce_float(support_distance_pct, finite_only=True)
    if breakout_value is None or support_value is None:
        return "invalid"
    if breakout_value < 0 or support_value < 0:
        return "invalid"
    if not has_acceptance:
        return "early"
    if breakout_value > 3.0:
        return "extended"
    if support_value > 4.0:
        return "extended"
    return "confirmed"
