from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class EntrySignal:
    """
    Canonical structured signal snapshot used for feature scoring.

    All strategies should return either:
        None
        OR
        EntrySignal(...)
    """

    symbol: str
    strategy_key: str
    timeframe_minutes: int

    # core structure
    trend_alignment: float = 0.0
    momentum: float = 0.0
    structure: float = 0.0

    # breakout / reclaim logic
    reclaim_or_breakout: float = 0.0

    # context
    volume_confirmation: float = 0.0
    volatility_context: float = 0.0
    regime_fit: float = 0.0

    # trade math
    risk_reward: float = 0.0

    # diagnostics
    price_location: float = 0.0

    # optional metadata
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None