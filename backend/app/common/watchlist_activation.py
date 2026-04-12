from __future__ import annotations

from datetime import datetime, timedelta, timezone

ACTIVATION_TF_MINUTES = 15
ACTIVATION_BUFFER_SECONDS = 20


def _utc_timestamp(value: datetime | None) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).timestamp()


def activation_candle_close_at(added_at: datetime | None, fast_tf_minutes: int = ACTIVATION_TF_MINUTES) -> datetime | None:
    if added_at is None:
        return None
    base = added_at.replace(second=0, microsecond=0)
    minute_bucket = (base.minute // fast_tf_minutes) * fast_tf_minutes
    boundary = base.replace(minute=minute_bucket)
    if boundary <= added_at:
        boundary += timedelta(minutes=fast_tf_minutes)
    return boundary


def activation_ready_at(added_at: datetime | None, fast_tf_minutes: int = ACTIVATION_TF_MINUTES) -> datetime | None:
    candle_close_at = activation_candle_close_at(added_at, fast_tf_minutes=fast_tf_minutes)
    if candle_close_at is None:
        return None
    return candle_close_at + timedelta(seconds=ACTIVATION_BUFFER_SECONDS)


def is_watchlist_activation_ready(
    added_at: datetime | None,
    now: datetime | None = None,
    fast_tf_minutes: int = ACTIVATION_TF_MINUTES,
    frame_info: dict | None = None,
) -> bool:
    ready_at = activation_ready_at(added_at, fast_tf_minutes=fast_tf_minutes)
    if ready_at is None:
        return True
    current_time = now or datetime.utcnow()
    if current_time < ready_at:
        return False

    if frame_info is None:
        return True

    added_ts = _utc_timestamp(added_at)
    if added_ts is None:
        return True

    last_close_ts = float(frame_info.get("last_close_ts") or 0.0)
    last_ingested_ts = float(frame_info.get("last_ingested_ts") or 0.0)
    return last_close_ts >= added_ts and last_ingested_ts >= added_ts
