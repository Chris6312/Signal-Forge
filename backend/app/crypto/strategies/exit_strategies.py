import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ExitDecision:
    should_exit: bool
    reason: str
    partial: bool = False
    partial_pct: float = 0.0
    new_stop: Optional[float] = None
    trailing_active: bool = False
    tp1_hit: bool = False


def _atr(ohlcv: list, period: int = 14) -> float:
    if len(ohlcv) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(ohlcv)):
        high = float(ohlcv[i][2])
        low = float(ohlcv[i][3])
        prev_close = float(ohlcv[i - 1][4])
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs[-period:]) / period


def _is_trending(ohlcv: list) -> bool:
    if len(ohlcv) < 20:
        return False
    closes = [float(c[4]) for c in ohlcv[-20:]]
    k = 2 / 21
    ema = closes[0]
    for c in closes[1:]:
        ema = c * k + ema * (1 - k)
    return closes[-1] > ema


def _stop_confirmed(current_price: float, stop: float, ohlcv: list) -> bool:
    """Require the last completed candle to close at or below the stop level
    before triggering an exit. Prevents single-wick whipsaw exits.
    Falls back to trusting the ticker price when no prior candle is available."""
    if current_price > stop:
        return False
    if len(ohlcv) >= 2:
        last_close = float(ohlcv[-2][4])  # -2 = last completed candle; -1 is still forming
        return last_close <= stop
    return True  # no prior candle data — trust ticker


def _tp1_atr_trail_decision(position, current_price: float, ohlcv: list, atr_multiplier: float = 1.5) -> Optional[ExitDecision]:
    entry = position.entry_price
    stop = position.current_stop or position.initial_stop
    milestone = position.milestone_state or {}
    atr = _atr(ohlcv)
    tp1 = position.profit_target_1

    if milestone.get("tp1_hit"):
        trail = float(milestone.get("trailing_stop", stop))
        if _stop_confirmed(current_price, trail, ohlcv):
            return ExitDecision(True, f"Trail stop hit at {trail:.4f}")
        if atr:
            new_trail = max(trail, current_price - atr * atr_multiplier)
            if new_trail > trail:
                return ExitDecision(False, "Trail updated", new_stop=new_trail, trailing_active=True)
        return None

    if tp1 and current_price >= tp1:
        floor = max(float(stop), float(entry)) if stop is not None and entry is not None else float(stop or entry or current_price)
        new_stop = max(floor, current_price - atr * atr_multiplier) if atr else floor
        return ExitDecision(
            False,
            "TP1 reached — ATR trail activated",
            new_stop=new_stop,
            trailing_active=True,
            tp1_hit=True,
        )

    return None


class FixedRiskDynamicFloor:
    name = "Fixed Risk then Dynamic Protective Floor"

    def evaluate(self, position, current_price: float, ohlcv: list) -> ExitDecision:
        entry = position.entry_price
        stop = position.current_stop or position.initial_stop
        milestone = position.milestone_state or {}
        atr = _atr(ohlcv)
        tp1 = position.profit_target_1
        tp2 = position.profit_target_2

        if _stop_confirmed(current_price, stop, ohlcv):
            return ExitDecision(True, f"Stop hit at {stop:.4f}")

        tp1_decision = _tp1_atr_trail_decision(position, current_price, ohlcv, atr_multiplier=1.5)
        if tp1_decision:
            return tp1_decision

        return ExitDecision(False, "Holding")


class PartialAtTP1DynamicTrail:
    name = "Partial at TP1, Dynamic Trail on Runner"

    def evaluate(self, position, current_price: float, ohlcv: list) -> ExitDecision:
        entry = position.entry_price
        stop = position.current_stop or position.initial_stop
        milestone = position.milestone_state or {}
        atr = _atr(ohlcv)
        tp1 = position.profit_target_1
        tp2 = position.profit_target_2

        if _stop_confirmed(current_price, stop, ohlcv):
            return ExitDecision(True, f"Stop hit at {stop:.4f}")

        tp1_hit = milestone.get("tp1_hit", False)

        if not tp1_hit and tp1 and current_price >= tp1:
            return ExitDecision(
                False, "TP1 reached — partial exit signal",
                partial=True,
                partial_pct=0.50,
                new_stop=entry,
            )

        if tp1_hit:
            trail = milestone.get("trailing_stop", stop)
            if _stop_confirmed(current_price, float(trail), ohlcv):
                return ExitDecision(True, f"Trail stop hit at {trail:.4f}")
            if atr and _is_trending(ohlcv):
                new_trail = max(float(trail), current_price - atr * 2.0)
                if new_trail > float(trail):
                    return ExitDecision(
                        False, "Trail updated",
                        new_stop=new_trail,
                        trailing_active=True,
                    )

        return ExitDecision(False, "Holding")


class FailedFollowThroughExit:
    name = "Failed Follow-Through Exit"

    def evaluate(self, position, current_price: float, ohlcv: list) -> ExitDecision:
        stop = position.current_stop or position.initial_stop
        if _stop_confirmed(current_price, stop, ohlcv):
            return ExitDecision(True, f"Stop hit at {stop:.4f}")

        tp1_decision = _tp1_atr_trail_decision(position, current_price, ohlcv)
        if tp1_decision:
            return tp1_decision

        if len(ohlcv) < 3:
            return ExitDecision(False, "Holding")

        closes = [float(c[4]) for c in ohlcv[-3:]]
        entry = position.entry_price
        if closes[-1] < closes[-2] < closes[-3] and current_price < entry:
            return ExitDecision(True, "Failed follow-through — momentum lost")

        return ExitDecision(False, "Holding")


class RangeFailureExit:
    name = "Range Failure Exit"

    def evaluate(self, position, current_price: float, ohlcv: list) -> ExitDecision:
        stop = position.current_stop or position.initial_stop
        if _stop_confirmed(current_price, stop, ohlcv):
            return ExitDecision(True, f"Stop hit at {stop:.4f}")

        tp1_decision = _tp1_atr_trail_decision(position, current_price, ohlcv)
        if tp1_decision:
            return tp1_decision

        if len(ohlcv) < 10:
            return ExitDecision(False, "Holding")

        lows = [float(c[3]) for c in ohlcv[-10:]]
        range_support = min(lows[:-1])
        if _stop_confirmed(current_price, range_support * 0.995, ohlcv):
            return ExitDecision(True, f"Range support failed at {range_support:.4f}")

        return ExitDecision(False, "Holding")


class TimeDegradationExit:
    name = "Time Degradation Exit"

    def evaluate(self, position, current_price: float, ohlcv: list) -> ExitDecision:
        from datetime import datetime, timezone
        stop = position.current_stop or position.initial_stop
        if _stop_confirmed(current_price, stop, ohlcv):
            return ExitDecision(True, f"Stop hit at {stop:.4f}")

        tp1_decision = _tp1_atr_trail_decision(position, current_price, ohlcv)
        if tp1_decision:
            return tp1_decision

        if position.entry_time and position.max_hold_hours:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            hours_held = (now - position.entry_time).total_seconds() / 3600
            entry = position.entry_price
            if hours_held >= position.max_hold_hours and current_price < entry * 1.005:
                return ExitDecision(True, f"Max hold time {position.max_hold_hours}h exceeded without progress")

        return ExitDecision(False, "Holding")


class RegimeBreakdownExit:
    name = "Regime Breakdown Exit"

    def evaluate(self, position, current_price: float, ohlcv: list) -> ExitDecision:
        stop = position.current_stop or position.initial_stop
        if _stop_confirmed(current_price, stop, ohlcv):
            return ExitDecision(True, f"Stop hit at {stop:.4f}")

        tp1_decision = _tp1_atr_trail_decision(position, current_price, ohlcv)
        if tp1_decision:
            return tp1_decision

        regime_at_entry = position.regime_at_entry or ""
        if "trending_up" in regime_at_entry and len(ohlcv) >= 50:
            closes = [float(c[4]) for c in ohlcv]
            k20 = 2 / 21
            k50 = 2 / 51
            ema20 = closes[0]
            ema50 = closes[0]
            for c in closes[1:]:
                ema20 = c * k20 + ema20 * (1 - k20)
                ema50 = c * k50 + ema50 * (1 - k50)
            if ema20 < ema50 * 0.99:
                return ExitDecision(True, "Regime flipped — trend broken")

        return ExitDecision(False, "Holding")


CRYPTO_EXIT_STRATEGIES = {
    "Fixed Risk then Dynamic Protective Floor": FixedRiskDynamicFloor(),
    "Partial at TP1, Dynamic Trail on Runner": PartialAtTP1DynamicTrail(),
    "Failed Follow-Through Exit": FailedFollowThroughExit(),
    "Range Failure Exit": RangeFailureExit(),
    "Time Degradation Exit": TimeDegradationExit(),
    "Regime Breakdown Exit": RegimeBreakdownExit(),
}

DEFAULT_EXIT_STRATEGY = "Fixed Risk then Dynamic Protective Floor"


def evaluate_exit(position, current_price: float, ohlcv: list) -> ExitDecision:
    strategy_name = position.exit_strategy or DEFAULT_EXIT_STRATEGY
    strategy = CRYPTO_EXIT_STRATEGIES.get(strategy_name)
    if not strategy:
        logger.warning("Unknown exit strategy: %s, using default", strategy_name)
        strategy = CRYPTO_EXIT_STRATEGIES[DEFAULT_EXIT_STRATEGY]
    try:
        return strategy.evaluate(position, current_price, ohlcv)
    except Exception as exc:
        logger.error("Exit strategy error: %s", exc)
        return ExitDecision(False, "Error in exit evaluation")