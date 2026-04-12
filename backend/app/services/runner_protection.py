import logging
from datetime import datetime, timezone
from typing import Any

from app.common.models.position_management_state import PositionManagementState

logger = logging.getLogger(__name__)

MILESTONE_VERSION = "runner_protection_v1"
FOLLOW_THROUGH_PCT = 0.01


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _getattr(position: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(position, name, default)
    except Exception:
        return default


def _milestone_state(position: Any) -> dict[str, Any]:
    state = _getattr(position, "milestone_state", None)
    return state if isinstance(state, dict) else {}


def _extract_low(candle: Any) -> float | None:
    if isinstance(candle, dict):
        return _float(candle.get("low"))
    if isinstance(candle, (list, tuple)) and len(candle) >= 4:
        return _float(candle[3])
    return None


def _recent_lows(ohlcv: Any) -> list[float]:
    if not isinstance(ohlcv, list):
        return []
    values: list[float] = []
    for candle in ohlcv:
        low = _extract_low(candle)
        if low is not None:
            values.append(low)
    return values


def _fees_per_unit(position: Any) -> float:
    fees_paid = _float(_getattr(position, "fees_paid", None)) or 0.0
    quantity = _float(_getattr(position, "quantity", None)) or 0.0
    if quantity > 0:
        return fees_paid / quantity
    return 0.0


def calculate_break_even_floor(position: Any, slippage_buffer: float = 0.0) -> float | None:
    entry = _float(_getattr(position, "entry_price", None))
    if entry is None:
        return None
    return round(entry + _fees_per_unit(position) + max(slippage_buffer, 0.0), 8)


def get_protection_snapshot(position: Any, ohlcv: Any | None = None) -> PositionManagementState:
    state = _milestone_state(position)
    initial_risk_price = _float(_getattr(position, "initial_risk_price", None))
    if initial_risk_price is None:
        initial_risk_price = _float(_getattr(position, "initial_stop", None))

    tp1_price = _float(_getattr(position, "tp1_price", None))
    if tp1_price is None:
        tp1_price = _float(_getattr(position, "profit_target_1", None))

    tp1_hit = bool(_getattr(position, "tp1_hit", False) or state.get("tp1_hit", False))
    break_even_floor = _float(_getattr(position, "break_even_floor", None))
    if break_even_floor is None:
        break_even_floor = _float(state.get("break_even_floor"))
    if break_even_floor is None:
        break_even_floor = _float(state.get("fee_adjusted_break_even"))

    promoted_floor = _float(_getattr(position, "promoted_floor", None))
    if promoted_floor is None:
        promoted_floor = _float(state.get("promoted_floor"))
    if promoted_floor is None:
        promoted_floor = _float(state.get("trailing_stop"))

    highest_promoted_floor = _float(_getattr(position, "highest_promoted_floor", None))
    if highest_promoted_floor is None:
        highest_promoted_floor = _float(state.get("highest_promoted_floor"))
    if highest_promoted_floor is None:
        highest_promoted_floor = _float(state.get("protected_floor"))
    if highest_promoted_floor is None:
        highest_promoted_floor = promoted_floor or break_even_floor

    current_stop = _float(_getattr(position, "current_stop", None))
    initial_stop = _float(_getattr(position, "initial_stop", None))
    entry_price = _float(_getattr(position, "entry_price", None))

    final_floor_candidates = [
        value for value in (
            initial_risk_price,
            initial_stop,
            current_stop,
            break_even_floor,
            promoted_floor,
            highest_promoted_floor,
            _float(state.get("protected_floor")),
            _float(state.get("trailing_stop")),
        ) if value is not None
    ]
    final_floor = max(final_floor_candidates) if final_floor_candidates else None

    runner_phase = _getattr(position, "runner_phase", None) or state.get("runner_phase")
    if runner_phase is None:
        if tp1_hit and highest_promoted_floor is not None and break_even_floor is not None and highest_promoted_floor > break_even_floor:
            runner_phase = "trail_active"
        elif tp1_hit:
            runner_phase = "breakeven"
        else:
            runner_phase = "initial_risk"

    protection_mode = _getattr(position, "protection_mode", None) or state.get("protection_mode")
    if protection_mode is None:
        protection_mode = runner_phase

    milestone_version = _getattr(position, "milestone_version", None) or state.get("milestone_version") or MILESTONE_VERSION
    last_protection_update_at = _getattr(position, "last_protection_update_at", None) or state.get("last_protection_update_at")

    if break_even_floor is None and tp1_hit and entry_price is not None:
        break_even_floor = calculate_break_even_floor(position)
    if promoted_floor is None:
        promoted_floor = highest_promoted_floor or break_even_floor

    return PositionManagementState(
        protection_mode=protection_mode,
        initial_risk_price=initial_risk_price,
        tp1_price=tp1_price,
        tp1_hit=tp1_hit,
        break_even_floor=break_even_floor,
        promoted_floor=promoted_floor,
        highest_promoted_floor=highest_promoted_floor,
        runner_phase=runner_phase,
        milestone_version=milestone_version,
        last_protection_update_at=last_protection_update_at,
        fee_adjusted_break_even=break_even_floor,
        promoted_protective_floor=promoted_floor,
        final_floor=final_floor,
    )


def get_effective_floor(position: Any, ohlcv: Any | None = None) -> float | None:
    return get_protection_snapshot(position, ohlcv=ohlcv).final_floor


def _sync_milestone_state(position: Any, snapshot: PositionManagementState) -> None:
    state = dict(_milestone_state(position))
    state.update({
        "tp1_hit": snapshot.tp1_hit,
        "tp1_price": snapshot.tp1_price,
        "protected_floor": snapshot.final_floor,
        "trailing_stop": snapshot.final_floor,
        "protection_mode": snapshot.protection_mode,
        "be_promoted": snapshot.tp1_hit,
        "trail_active": bool(snapshot.tp1_hit),
    })
    setattr(position, "milestone_state", state)


def _log_protection_event(symbol: str, old_floor: float | None, new_floor: float | None, runner_phase: str | None, reason: str) -> None:
    logger.debug(
        "runner_protection_event",
        extra={
            "symbol": symbol,
            "old_floor": old_floor,
            "new_floor": new_floor,
            "runner_phase": runner_phase,
            "reason": reason,
        },
    )


def promote_tp1(position: Any, current_price: float | None = None, now: datetime | None = None, slippage_buffer: float = 0.0) -> bool:
    snapshot = get_protection_snapshot(position)
    if snapshot.tp1_hit:
        return False

    tp1_price = snapshot.tp1_price or _float(_getattr(position, "profit_target_1", None))
    if tp1_price is None:
        return False
    if current_price is not None and current_price < tp1_price:
        return False

    be_floor = calculate_break_even_floor(position, slippage_buffer=slippage_buffer)
    if be_floor is None:
        return False

    old_floor = snapshot.final_floor
    new_floor = max([value for value in (snapshot.final_floor, be_floor) if value is not None])
    current_stop = _float(_getattr(position, "current_stop", None))
    if current_stop is None or new_floor > current_stop:
        setattr(position, "current_stop", new_floor)

    setattr(position, "tp1_hit", True)
    setattr(position, "tp1_price", tp1_price)
    setattr(position, "break_even_floor", max(snapshot.break_even_floor or be_floor, be_floor))
    setattr(position, "promoted_floor", max(snapshot.promoted_floor or be_floor, be_floor))
    setattr(position, "highest_promoted_floor", max(snapshot.highest_promoted_floor or be_floor, be_floor, new_floor))
    setattr(position, "protection_mode", "break_even")
    setattr(position, "runner_phase", "breakeven")
    setattr(position, "milestone_version", MILESTONE_VERSION)
    setattr(position, "last_protection_update_at", now or _now())
    _sync_milestone_state(position, get_protection_snapshot(position))
    _log_protection_event(_getattr(position, "symbol", ""), old_floor, get_effective_floor(position), "breakeven", "tp1_reached")
    return True


def promote_floor(position: Any, new_floor: float | None, runner_phase: str, reason: str, now: datetime | None = None, protection_mode: str | None = None) -> bool:
    if new_floor is None:
        return False

    snapshot = get_protection_snapshot(position)
    old_floor = snapshot.final_floor
    if old_floor is not None and new_floor <= old_floor:
        return False

    current_stop = _float(_getattr(position, "current_stop", None))
    if current_stop is None or new_floor > current_stop:
        setattr(position, "current_stop", new_floor)

    setattr(position, "promoted_floor", new_floor)
    setattr(position, "highest_promoted_floor", max(snapshot.highest_promoted_floor or new_floor, new_floor))
    setattr(position, "runner_phase", runner_phase)
    setattr(position, "protection_mode", protection_mode or runner_phase)
    setattr(position, "last_protection_update_at", now or _now())
    _sync_milestone_state(position, get_protection_snapshot(position))
    _log_protection_event(_getattr(position, "symbol", ""), old_floor, get_effective_floor(position), runner_phase, reason)
    return True


def promote_follow_through(position: Any, current_price: float | None, ohlcv: Any | None = None, now: datetime | None = None, reason: str = "follow_through") -> bool:
    snapshot = get_protection_snapshot(position, ohlcv=ohlcv)
    if not snapshot.tp1_hit or snapshot.tp1_price is None:
        return False
    if current_price is None or current_price < snapshot.tp1_price * (1 + FOLLOW_THROUGH_PCT):
        return False

    lows = _recent_lows(ohlcv)
    if len(lows) < 2:
        return False
    candidate = max(lows[-3:-1] or lows[-2:])
    if snapshot.highest_promoted_floor is not None and candidate <= snapshot.highest_promoted_floor:
        return False

    return promote_floor(position, candidate, "trail_active", reason, now=now, protection_mode="trail_active")
