import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone

from app.common.market_hours import is_near_eod as _is_near_eod
from app.services.runner_protection import get_effective_floor

logger = logging.getLogger(__name__)


@dataclass
class StockExitDecision:
    should_exit: bool
    reason: str
    partial: bool = False
    partial_pct: float = 0.0
    new_stop: Optional[float] = None
    trailing_active: bool = False
    tp1_hit: bool = False


def _atr_from_history(history: list[dict], period: int = 14) -> float:
    if len(history) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(history)):
        high = float(history[i].get("high", 0))
        low = float(history[i].get("low", 0))
        prev_close = float(history[i - 1].get("close", 0))
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs[-period:]) / period


def _tp1_atr_trail_decision(position, current_price: float, history: list[dict], atr_multiplier: float = 1.0) -> Optional[StockExitDecision]:
    milestone = position.milestone_state or {}
    if milestone.get("tp1_hit"):
        stop = milestone.get("highest_promoted_floor") or milestone.get("promoted_floor") or milestone.get("trailing_stop")
        if stop is None:
            stop = get_effective_floor(position)
    else:
        stop = get_effective_floor(position)
        if stop is None:
            stop = position.current_stop or position.initial_stop
    entry = position.entry_price
    atr = _atr_from_history(history)
    tp1 = position.profit_target_1
    tp1_hit = bool(milestone.get("tp1_hit") or getattr(position, "tp1_hit", False))

    if tp1_hit:
        trail = float(milestone.get("highest_promoted_floor") or milestone.get("promoted_floor") or milestone.get("trailing_stop", stop))
        if current_price <= trail:
            return StockExitDecision(True, f"Trail stop hit at {trail:.2f}")
        if atr:
            new_trail = max(trail, current_price - atr * atr_multiplier)
            if new_trail > trail:
                return StockExitDecision(False, "Trail updated", new_stop=new_trail, trailing_active=True)
        return None

    if tp1 and current_price >= tp1:
        floor = max(float(stop), float(entry)) if stop is not None and entry is not None else float(stop or entry or current_price)
        new_stop = max(floor, current_price - atr * atr_multiplier) if atr else floor
        return StockExitDecision(
            False,
            "TP1 reached — ATR trail activated",
            new_stop=new_stop,
            trailing_active=True,
            tp1_hit=True,
        )

    return None


class FixedRiskBreakEvenPromotion:
    name = "Fixed Risk then Break-Even Promotion"

    def evaluate(self, position, current_price: float, history: list[dict]) -> StockExitDecision:
        stop = position.current_stop or position.initial_stop
        entry = position.entry_price
        milestone = position.milestone_state or {}
        atr = _atr_from_history(history)
        tp1 = position.profit_target_1

        if current_price <= stop:
            return StockExitDecision(True, f"Stop hit at {stop:.2f}")

        if _is_near_eod():
            return StockExitDecision(True, "End-of-day exit — intraday position")

        tp1_decision = _tp1_atr_trail_decision(position, current_price, history)
        if tp1_decision:
            return tp1_decision

        if not milestone.get("be_promoted") and tp1 and entry and current_price >= entry + (tp1 - entry) * 0.5:
            new_stop = max(stop, entry)
            return StockExitDecision(False, "Stop promoted to break-even", new_stop=new_stop)

        return StockExitDecision(False, "Holding")


class PartialAtTP1TrailRemainder:
    name = "Partial at TP1, Trail Remainder"

    def evaluate(self, position, current_price: float, history: list[dict]) -> StockExitDecision:
        stop = position.current_stop or position.initial_stop
        entry = position.entry_price
        milestone = position.milestone_state or {}
        atr = _atr_from_history(history)
        tp1 = position.profit_target_1

        if current_price <= stop:
            return StockExitDecision(True, f"Stop hit at {stop:.2f}")

        if _is_near_eod():
            return StockExitDecision(True, "End-of-day exit")

        if not milestone.get("tp1_hit") and tp1 and current_price >= tp1:
            return StockExitDecision(
                False, "TP1 reached — partial exit",
                partial=True,
                partial_pct=0.50,
                new_stop=entry,
            )

        if milestone.get("tp1_hit"):
            trail = milestone.get("trailing_stop", stop)
            if current_price <= float(trail):
                return StockExitDecision(True, f"Trail stop hit at {trail:.2f}")
            if atr:
                new_trail = max(float(trail), current_price - atr * 1.0)
                if new_trail > float(trail):
                    return StockExitDecision(False, "Trail updated", new_stop=new_trail, trailing_active=True)

        return StockExitDecision(False, "Holding")


class FirstFailedFollowThroughExit:
    name = "First Failed Follow-Through Exit"

    def evaluate(self, position, current_price: float, history: list[dict]) -> StockExitDecision:
        stop = position.current_stop or position.initial_stop
        entry = position.entry_price

        if current_price <= stop:
            return StockExitDecision(True, f"Stop hit at {stop:.2f}")

        if _is_near_eod():
            return StockExitDecision(True, "End-of-day exit")

        tp1_decision = _tp1_atr_trail_decision(position, current_price, history)
        if tp1_decision:
            return tp1_decision

        if len(history) >= 3:
            closes = [float(d.get("close", 0)) for d in history[-3:]]
            if closes[-1] < closes[-2] < closes[-3] and current_price < entry * 1.002:
                return StockExitDecision(True, "Failed follow-through — momentum lost")

        return StockExitDecision(False, "Holding")


class TimeStopExit:
    name = "Time Stop Exit"

    def evaluate(self, position, current_price: float, history: list[dict]) -> StockExitDecision:
        stop = position.current_stop or position.initial_stop
        entry = position.entry_price

        if current_price <= stop:
            return StockExitDecision(True, f"Stop hit at {stop:.2f}")

        if _is_near_eod():
            return StockExitDecision(True, "End-of-day exit")

        tp1_decision = _tp1_atr_trail_decision(position, current_price, history)
        if tp1_decision:
            return tp1_decision

        if position.entry_time and position.max_hold_hours:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            hours_held = (now - position.entry_time).total_seconds() / 3600
            if hours_held >= position.max_hold_hours and current_price < entry * 1.003:
                return StockExitDecision(True, f"Time stop — {position.max_hold_hours}h exceeded without progress")

        return StockExitDecision(False, "Holding")


class VWAPStructureLossExit:
    name = "VWAP / Structure Loss Exit"

    def evaluate(self, position, current_price: float, history: list[dict]) -> StockExitDecision:
        stop = position.current_stop or position.initial_stop

        if current_price <= stop:
            return StockExitDecision(True, f"Stop hit at {stop:.2f}")

        if _is_near_eod():
            return StockExitDecision(True, "End-of-day exit")

        tp1_decision = _tp1_atr_trail_decision(position, current_price, history)
        if tp1_decision:
            return tp1_decision

        if len(history) >= 10:
            lows = [float(d.get("low", 0)) for d in history[-10:]]
            structure_support = min(lows[:-1])
            if current_price < structure_support * 0.998:
                return StockExitDecision(True, f"Structure support broken at {structure_support:.2f}")

        return StockExitDecision(False, "Holding")


class EndOfDayExit:
    name = "End-of-Day Exit"

    def evaluate(self, position, current_price: float, history: list[dict]) -> StockExitDecision:
        stop = position.current_stop or position.initial_stop
        if current_price <= stop:
            return StockExitDecision(True, f"Stop hit at {stop:.2f}")

        if _is_near_eod():
            return StockExitDecision(True, "End-of-day exit — session closing")

        tp1_decision = _tp1_atr_trail_decision(position, current_price, history)
        if tp1_decision:
            return tp1_decision

        return StockExitDecision(False, "Holding")


STOCK_EXIT_STRATEGIES = {
    "Fixed Risk then Break-Even Promotion": FixedRiskBreakEvenPromotion(),
    "Partial at TP1, Trail Remainder": PartialAtTP1TrailRemainder(),
    "First Failed Follow-Through Exit": FirstFailedFollowThroughExit(),
    "Time Stop Exit": TimeStopExit(),
    "VWAP / Structure Loss Exit": VWAPStructureLossExit(),
    "End-of-Day Exit": EndOfDayExit(),
}

DEFAULT_EXIT_STRATEGY = "Fixed Risk then Break-Even Promotion"


def evaluate_exit(position, current_price: float, history: list[dict]) -> StockExitDecision:
    strategy_name = position.exit_strategy or DEFAULT_EXIT_STRATEGY
    strategy = STOCK_EXIT_STRATEGIES.get(strategy_name)
    if not strategy:
        logger.warning("Unknown stock exit strategy: %s", strategy_name)
        strategy = STOCK_EXIT_STRATEGIES[DEFAULT_EXIT_STRATEGY]
    try:
        return strategy.evaluate(position, current_price, history)
    except Exception as exc:
        logger.error("Stock exit strategy error: %s", exc)
        return StockExitDecision(False, "Error in exit evaluation")
