from dataclasses import dataclass


@dataclass(frozen=True)
class RegimePolicy:
    allow_new_entries: bool
    max_positions: int
    size_multiplier: float
    min_setup_score: float
    stop_loss_multiplier: float
    take_profit_aggression: float
    breakout_enabled: bool
    mean_reversion_enabled: bool
    promote_breakeven_r: float


STOCK_REGIME_POLICIES: dict[str, RegimePolicy] = {
    "RISK_ON": RegimePolicy(
        allow_new_entries=True,
        max_positions=6,
        size_multiplier=1.0,
        min_setup_score=0.65,
        stop_loss_multiplier=1.0,
        take_profit_aggression=0.8,
        breakout_enabled=True,
        mean_reversion_enabled=True,
        promote_breakeven_r=2.0,
    ),
    "NEUTRAL": RegimePolicy(
        allow_new_entries=True,
        max_positions=3,
        size_multiplier=0.7,
        min_setup_score=0.72,
        stop_loss_multiplier=0.9,
        take_profit_aggression=1.0,
        breakout_enabled=True,
        mean_reversion_enabled=True,
        promote_breakeven_r=1.5,
    ),
    "RISK_OFF": RegimePolicy(
        allow_new_entries=True,
        max_positions=1,
        size_multiplier=0.4,
        min_setup_score=0.82,
        stop_loss_multiplier=0.8,
        take_profit_aggression=1.2,
        breakout_enabled=False,
        mean_reversion_enabled=True,
        promote_breakeven_r=1.0,
    ),
}

CRYPTO_REGIME_POLICIES: dict[str, RegimePolicy] = {
    "RISK_ON": RegimePolicy(
        allow_new_entries=True,
        max_positions=5,
        size_multiplier=1.0,
        min_setup_score=0.65,
        stop_loss_multiplier=1.0,
        take_profit_aggression=0.8,
        breakout_enabled=True,
        mean_reversion_enabled=True,
        promote_breakeven_r=2.0,
    ),
    "NEUTRAL": RegimePolicy(
        allow_new_entries=True,
        max_positions=3,
        size_multiplier=0.65,
        min_setup_score=0.74,
        stop_loss_multiplier=0.9,
        take_profit_aggression=1.0,
        breakout_enabled=True,
        mean_reversion_enabled=True,
        promote_breakeven_r=1.5,
    ),
    "RISK_OFF": RegimePolicy(
        allow_new_entries=True,
        max_positions=1,
        size_multiplier=0.35,
        min_setup_score=0.84,
        stop_loss_multiplier=0.8,
        take_profit_aggression=1.3,
        breakout_enabled=False,
        mean_reversion_enabled=True,
        promote_breakeven_r=1.0,
    ),
}
