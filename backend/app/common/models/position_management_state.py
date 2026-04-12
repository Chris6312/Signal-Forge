from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class PositionManagementState:
    protection_mode: str | None = None
    initial_risk_price: float | None = None
    tp1_price: float | None = None
    tp1_hit: bool = False
    break_even_floor: float | None = None
    promoted_floor: float | None = None
    highest_promoted_floor: float | None = None
    runner_phase: str | None = None
    milestone_version: str | None = None
    last_protection_update_at: datetime | None = None
    fee_adjusted_break_even: float | None = None
    promoted_protective_floor: float | None = None
    final_floor: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
