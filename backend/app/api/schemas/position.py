from datetime import datetime, timezone
from typing import Any
from uuid import UUID
from pydantic import BaseModel


class PositionOut(BaseModel):
    id: UUID
    symbol: str
    asset_class: str
    state: str
    entry_price: float | None = None
    current_price: float | None = None
    quantity: float | None = None
    entry_time: datetime | None = None
    entry_strategy: str | None = None
    exit_strategy: str | None = None
    initial_stop: float | None = None
    current_stop: float | None = None
    profit_target_1: float | None = None
    profit_target_2: float | None = None
    max_hold_hours: int | None = None
    hours_held: float | None = None
    hold_ratio: float | None = None
    time_risk_state: str | None = None
    protection_mode: str | None = None
    initial_risk_price: float | None = None
    tp1_price: float | None = None
    tp1_hit: bool | None = None
    break_even_floor: float | None = None
    promoted_floor: float | None = None
    highest_promoted_floor: float | None = None
    runner_phase: str | None = None
    milestone_version: str | None = None
    last_protection_update_at: datetime | None = None
    regime_at_entry: str | None = None
    watchlist_source_id: str | None = None
    management_policy_version: str | None = None
    frozen_policy: Any | None = None
    milestone_state: Any | None = None
    exit_price: float | None = None
    exit_time: datetime | None = None
    exit_reason: str | None = None
    pnl_realized: float | None = None
    pnl_unrealized: float | None = None
    fees_paid: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
