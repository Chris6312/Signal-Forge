from __future__ import annotations

import math


def _coerce_float(value) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def compute_breakout_extension_pct(price: float, breakout_level: float) -> float:
    price_value = _coerce_float(price)
    breakout_value = _coerce_float(breakout_level)
    if price_value is None or breakout_value is None or breakout_value <= 0:
        return 0.0
    if price_value <= breakout_value:
        return 0.0
    return ((price_value - breakout_value) / breakout_value) * 100.0


def compute_support_distance_pct(price: float, support_level: float) -> float:
    price_value = _coerce_float(price)
    support_value = _coerce_float(support_level)
    if price_value is None or support_value is None or support_value <= 0 or price_value <= 0:
        return 0.0
    return abs(price_value - support_value) / support_value * 100.0


def classify_signal_maturity(
    breakout_extension_pct: float,
    support_distance_pct: float,
    has_acceptance: bool,
) -> str:
    breakout_value = _coerce_float(breakout_extension_pct)
    support_value = _coerce_float(support_distance_pct)
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
