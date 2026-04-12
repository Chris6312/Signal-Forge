from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class PositionHoldMetrics:
    hours_held: float
    max_hold_hours: int | float | None
    hold_ratio: float | None
    time_risk_state: str | None

    def as_dict(self) -> dict[str, float | str | None]:
        return {
            "hours_held": self.hours_held,
            "max_hold_hours": self.max_hold_hours,
            "hold_ratio": self.hold_ratio,
            "time_risk_state": self.time_risk_state,
        }


def _to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def compute_position_hold_metrics(
    entry_time: datetime | None,
    max_hold_hours: int | float | None,
    now: datetime | None = None,
) -> PositionHoldMetrics:
    current_time = _to_naive_utc(now or datetime.now(timezone.utc))
    limit = float(max_hold_hours) if max_hold_hours is not None else None

    if entry_time is None:
        hours_held = 0.0
    else:
        elapsed = current_time - _to_naive_utc(entry_time)
        hours_held = max(0.0, elapsed.total_seconds() / 3600)

    if limit is None or limit <= 0:
        return PositionHoldMetrics(hours_held=hours_held, max_hold_hours=max_hold_hours if max_hold_hours and max_hold_hours > 0 else None, hold_ratio=None, time_risk_state=None)

    hold_ratio = hours_held / limit
    if hold_ratio < 0.7:
        time_risk_state = "green"
    elif hold_ratio < 0.9:
        time_risk_state = "yellow"
    else:
        time_risk_state = "red"

    return PositionHoldMetrics(
        hours_held=hours_held,
        max_hold_hours=max_hold_hours,
        hold_ratio=hold_ratio,
        time_risk_state=time_risk_state,
    )
