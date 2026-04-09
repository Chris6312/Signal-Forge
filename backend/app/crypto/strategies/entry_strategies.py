import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EntrySignal:
    strategy: str
    symbol: str
    entry_price: float
    initial_stop: float
    profit_target_1: float
    profit_target_2: float
    regime: str
    confidence: float
    max_hold_hours: int = 48
    notes: str = ""


def _ema(prices: list[float], period: int) -> list[float]:
    if len(prices) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema.append(p * k + ema[-1] * (1 - k))
    return ema


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


def _detect_regime(ohlcv: list) -> str:
    if len(ohlcv) < 50:
        return "unknown"
    closes = [float(c[4]) for c in ohlcv]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    if not ema20 or not ema50:
        return "unknown"
    if ema20[-1] > ema50[-1] * 1.01:
        return "trending_up"
    if ema20[-1] < ema50[-1] * 0.99:
        return "trending_down"
    return "ranging"


class MomentumBreakoutContinuation:
    name = "Momentum Breakout Continuation"
    primary_tf = "1H"

    def evaluate(self, symbol: str, ohlcv: list) -> Optional[EntrySignal]:
        if len(ohlcv) < 30:
            return None

        closes = [float(c[4]) for c in ohlcv]
        highs = [float(c[2]) for c in ohlcv]
        current = closes[-1]
        atr = _atr(ohlcv)
        regime = _detect_regime(ohlcv)

        if regime != "trending_up":
            return None

        recent_high = max(highs[-20:-1])
        if current <= recent_high * 1.002:
            return None

        ema20 = _ema(closes, 20)
        if not ema20 or current < ema20[-1]:
            return None

        stop = current - atr * 1.5
        tp1 = current + atr * 2.0
        tp2 = current + atr * 4.0

        return EntrySignal(
            strategy=self.name,
            symbol=symbol,
            entry_price=current,
            initial_stop=stop,
            profit_target_1=tp1,
            profit_target_2=tp2,
            regime=regime,
            confidence=0.70,
            max_hold_hours=48,
            notes=f"Breakout above {recent_high:.4f}",
        )


class PullbackReclaim:
    name = "Pullback Reclaim"
    primary_tf = "1H"

    def evaluate(self, symbol: str, ohlcv: list) -> Optional[EntrySignal]:
        if len(ohlcv) < 30:
            return None

        closes = [float(c[4]) for c in ohlcv]
        lows = [float(c[3]) for c in ohlcv]
        current = closes[-1]
        atr = _atr(ohlcv)
        regime = _detect_regime(ohlcv)

        if regime not in ("trending_up",):
            return None

        ema20 = _ema(closes, 20)
        if not ema20:
            return None

        ema_val = ema20[-1]
        prev_below = any(c < ema_val for c in closes[-6:-1])
        if not (prev_below and current > ema_val):
            return None

        stop = min(lows[-5:]) - atr * 0.3
        tp1 = current + atr * 1.5
        tp2 = current + atr * 3.0

        return EntrySignal(
            strategy=self.name,
            symbol=symbol,
            entry_price=current,
            initial_stop=stop,
            profit_target_1=tp1,
            profit_target_2=tp2,
            regime=regime,
            confidence=0.65,
            max_hold_hours=36,
            notes="Pullback reclaim of EMA20",
        )


class MeanReversionBounce:
    name = "Mean Reversion Bounce"
    primary_tf = "1H"

    def evaluate(self, symbol: str, ohlcv: list) -> Optional[EntrySignal]:
        if len(ohlcv) < 30:
            return None

        closes = [float(c[4]) for c in ohlcv]
        current = closes[-1]
        atr = _atr(ohlcv)
        regime = _detect_regime(ohlcv)

        if regime not in ("ranging", "unknown"):
            return None

        ema50 = _ema(closes, 50)
        if not ema50:
            return None

        mean = ema50[-1]
        pct_below = (mean - current) / mean
        if pct_below < 0.03:
            return None

        if closes[-1] > closes[-2]:
            stop = current - atr * 1.0
            tp1 = mean
            tp2 = mean + atr * 1.0

            return EntrySignal(
                strategy=self.name,
                symbol=symbol,
                entry_price=current,
                initial_stop=stop,
                profit_target_1=tp1,
                profit_target_2=tp2,
                regime=regime,
                confidence=0.60,
                max_hold_hours=24,
                notes=f"{pct_below*100:.1f}% below mean, bouncing",
            )
        return None


class RangeRotationReversal:
    name = "Range Rotation Reversal"
    primary_tf = "4H"

    def evaluate(self, symbol: str, ohlcv: list) -> Optional[EntrySignal]:
        if len(ohlcv) < 40:
            return None

        closes = [float(c[4]) for c in ohlcv]
        lows = [float(c[3]) for c in ohlcv]
        current = closes[-1]
        atr = _atr(ohlcv)
        regime = _detect_regime(ohlcv)

        if regime != "ranging":
            return None

        range_low = min(lows[-30:])
        if current > range_low * 1.02:
            return None

        if closes[-1] > closes[-2] > closes[-3]:
            stop = range_low - atr * 0.5
            tp1 = current + atr * 2.0
            tp2 = current + atr * 3.5

            return EntrySignal(
                strategy=self.name,
                symbol=symbol,
                entry_price=current,
                initial_stop=stop,
                profit_target_1=tp1,
                profit_target_2=tp2,
                regime=regime,
                confidence=0.62,
                max_hold_hours=24,
                notes=f"Range support reversal near {range_low:.4f}",
            )
        return None


class BreakoutRetestHold:
    name = "Breakout Retest Hold"
    primary_tf = "4H"

    def evaluate(self, symbol: str, ohlcv: list) -> Optional[EntrySignal]:
        if len(ohlcv) < 40:
            return None

        closes = [float(c[4]) for c in ohlcv]
        highs = [float(c[2]) for c in ohlcv]
        current = closes[-1]
        atr = _atr(ohlcv)
        regime = _detect_regime(ohlcv)

        prior_high = max(highs[-40:-10])
        recent_high = max(highs[-10:-1])

        if recent_high <= prior_high:
            return None

        if not (prior_high * 0.995 <= current <= prior_high * 1.015):
            return None

        if closes[-1] >= closes[-2]:
            stop = prior_high - atr * 0.5
            tp1 = current + atr * 2.0
            tp2 = current + atr * 4.0

            return EntrySignal(
                strategy=self.name,
                symbol=symbol,
                entry_price=current,
                initial_stop=stop,
                profit_target_1=tp1,
                profit_target_2=tp2,
                regime=regime,
                confidence=0.68,
                max_hold_hours=36,
                notes=f"Retest of breakout level {prior_high:.4f}",
            )
        return None


class FailedBreakdownReclaim:
    name = "Failed Breakdown Reclaim"
    primary_tf = "1H"

    def evaluate(self, symbol: str, ohlcv: list) -> Optional[EntrySignal]:
        if len(ohlcv) < 20:
            return None

        closes = [float(c[4]) for c in ohlcv]
        lows = [float(c[3]) for c in ohlcv]
        current = closes[-1]
        atr = _atr(ohlcv)
        regime = _detect_regime(ohlcv)

        support = min(lows[-20:-5])
        recent_min = min(lows[-5:])
        if recent_min >= support:
            return None

        if current > support and closes[-1] > closes[-2]:
            stop = recent_min - atr * 0.3
            tp1 = current + atr * 2.0
            tp2 = current + atr * 3.5

            return EntrySignal(
                strategy=self.name,
                symbol=symbol,
                entry_price=current,
                initial_stop=stop,
                profit_target_1=tp1,
                profit_target_2=tp2,
                regime=regime,
                confidence=0.67,
                max_hold_hours=24,
                notes=f"Failed breakdown below {support:.4f}, reclaimed",
            )
        return None


CRYPTO_ENTRY_STRATEGIES = [
    MomentumBreakoutContinuation(),
    PullbackReclaim(),
    MeanReversionBounce(),
    RangeRotationReversal(),
    BreakoutRetestHold(),
    FailedBreakdownReclaim(),
]


def evaluate_all(
    symbol: str,
    candles: "list | dict[str, list]",
) -> list[EntrySignal]:
    """
    Evaluate all crypto entry strategies.

    *candles* may be:
      - A ``dict[str, list]`` mapping timeframe labels (``"1H"``, ``"4H"``,
        ``"daily"``, …) to Kraken OHLCV lists.  Each strategy uses its
        ``primary_tf``.
      - A plain ``list`` (backwards-compat / tests): broadcast to all TFs.
    """
    if isinstance(candles, list):
        candles_by_tf: dict[str, list] = {
            tf: candles for tf in ("15m", "1H", "4H", "daily")
        }
    else:
        candles_by_tf = candles

    signals = []
    for strategy in CRYPTO_ENTRY_STRATEGIES:
        primary = candles_by_tf.get(strategy.primary_tf, [])
        if len(primary) < 20:
            continue
        try:
            sig = strategy.evaluate(symbol, primary)
            if sig:
                signals.append(sig)
        except Exception as exc:
            logger.error("Strategy %s error for %s: %s", strategy.name, symbol, exc)
    signals.sort(key=lambda s: s.confidence, reverse=True)
    return signals
