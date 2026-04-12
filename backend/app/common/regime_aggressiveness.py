from __future__ import annotations

_REGIME_AGGRESSIVENESS_MULTIPLIERS = {
    "risk_on": 1.15,
    "bull_trend": 1.10,
    "neutral": 1.00,
    "range_bound": 0.90,
    "risk_off": 0.75,
    "bear_trend": 0.65,
    "panic": 0.50,
}


def compute_regime_aggressiveness_multiplier(regime: str | None) -> float:
    if not isinstance(regime, str):
        return 1.0

    normalized_regime = regime.strip().lower()
    if not normalized_regime:
        return 1.0

    return _REGIME_AGGRESSIVENESS_MULTIPLIERS.get(normalized_regime, 1.0)
