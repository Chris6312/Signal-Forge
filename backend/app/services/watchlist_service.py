from typing import Any

from app.common.position_time import compute_position_hold_metrics
from app.services.runner_protection import get_protection_snapshot


def build_position_inspect_payload(position: Any) -> dict[str, Any]:
    snapshot = get_protection_snapshot(position)
    hold_metrics = compute_position_hold_metrics(
        getattr(position, "entry_time", None),
        getattr(position, "max_hold_hours", None),
    )
    milestone_state = getattr(position, "milestone_state", None)
    return {
        "id": getattr(position, "id", None),
        "symbol": getattr(position, "symbol", None),
        "asset_class": getattr(position, "asset_class", None),
        "state": getattr(position, "state", None),
        "entry_price": getattr(position, "entry_price", None),
        "current_price": getattr(position, "current_price", None),
        "quantity": getattr(position, "quantity", None),
        "entry_time": getattr(position, "entry_time", None),
        "entry_strategy": getattr(position, "entry_strategy", None),
        "exit_strategy": getattr(position, "exit_strategy", None),
        "initial_stop": getattr(position, "initial_stop", None),
        "current_stop": getattr(position, "current_stop", None),
        "profit_target_1": getattr(position, "profit_target_1", None),
        "profit_target_2": getattr(position, "profit_target_2", None),
        **hold_metrics.as_dict(),
        "regime_at_entry": getattr(position, "regime_at_entry", None),
        "watchlist_source_id": getattr(position, "watchlist_source_id", None),
        "management_policy_version": getattr(position, "management_policy_version", None),
        "frozen_policy": getattr(position, "frozen_policy", None),
        "milestone_state": milestone_state,
        "protection_mode": snapshot.protection_mode,
        "initial_risk_price": snapshot.initial_risk_price,
        "tp1_price": snapshot.tp1_price,
        "tp1_hit": snapshot.tp1_hit,
        "break_even_floor": snapshot.break_even_floor,
        "fee_adjusted_break_even": snapshot.fee_adjusted_break_even,
        "promoted_floor": snapshot.promoted_floor,
        "promoted_protective_floor": snapshot.promoted_protective_floor,
        "highest_promoted_floor": snapshot.highest_promoted_floor,
        "runner_phase": snapshot.runner_phase,
        "milestone_version": snapshot.milestone_version,
        "last_protection_update_at": snapshot.last_protection_update_at,
        "exit_price": getattr(position, "exit_price", None),
        "exit_time": getattr(position, "exit_time", None),
        "exit_reason": getattr(position, "exit_reason", None),
        "pnl_realized": getattr(position, "pnl_realized", None),
        "pnl_unrealized": getattr(position, "pnl_unrealized", None),
        "fees_paid": getattr(position, "fees_paid", None),
        "created_at": getattr(position, "created_at", None),
        "updated_at": getattr(position, "updated_at", None),
    }
