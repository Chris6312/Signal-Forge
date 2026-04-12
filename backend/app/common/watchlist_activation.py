from __future__ import annotations

from datetime import datetime, timedelta

ACTIVATION_TF_MINUTES = 15
ACTIVATION_BUFFER_SECONDS = 20


def activation_ready_at(added_at: datetime | None) -> datetime | None:
    if added_at is None:
        return None
    base = added_at.replace(second=0, microsecond=0)
    minute_bucket = (base.minute // ACTIVATION_TF_MINUTES) * ACTIVATION_TF_MINUTES
    boundary = base.replace(minute=minute_bucket)
    if boundary <= added_at:
        boundary += timedelta(minutes=ACTIVATION_TF_MINUTES)
    return boundary + timedelta(seconds=ACTIVATION_BUFFER_SECONDS)


def is_watchlist_activation_ready(added_at: datetime | None, now: datetime | None = None) -> bool:
    ready_at = activation_ready_at(added_at)
    if ready_at is None:
        return True
    current_time = now or datetime.utcnow()
    return current_time >= ready_at
