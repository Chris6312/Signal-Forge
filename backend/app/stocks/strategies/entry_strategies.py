import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class StockEntrySignal:
    strategy: str
    symbol: str
    entry_price: float
    initial_stop: float
    profit_target_1: float
    profit_target_2: float
    regime: str
    confidence: float
    max_hold_hours: int = 8
    notes: str = ""
    reasoning: dict = field(default_factory=dict)


def _ema(prices: list[float], period: int) -> list[float]:
    if len(prices) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema.append(p * k + ema[-1] * (1 - k))
    return ema


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


def _closes(history: list[dict]) -> list[float]:
    return [float(d.get("close", 0)) for d in history]


def _highs(history: list[dict]) -> list[float]:
    return [float(d.get("high", 0)) for d in history]


def _lows(history: list[dict]) -> list[float]:
    return [float(d.get("low", 0)) for d in history]


def _detect_regime(history: list[dict]) -> str:
    if len(history) < 50:
        return "unknown"
    closes = _closes(history)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    if not ema20 or not ema50:
        return "unknown"
    if ema20[-1] > ema50[-1] * 1.005:
        return "trending_up"
    if ema20[-1] < ema50[-1] * 0.995:
        return "trending_down"
    return "ranging"


class OpeningRangeBreakout:
    name = "Opening Range Breakout"
    primary_tf = "5m"

    def evaluate(self, symbol: str, history: list[dict], intraday: list[dict] | None = None) -> Optional[StockEntrySignal]:
        if len(history) < 20:
            return None

        closes = _closes(history)
        highs = _highs(history)
        atr = _atr_from_history(history)
        regime = _detect_regime(history)
        current = closes[-1]

        if len(history) < 5:
            return None

        or_high = max(highs[-5:-1])
        if current <= or_high * 1.001:
            return None

        ema20 = _ema(closes, 20)
        if ema20 and current < ema20[-1]:
            return None

        stop = current - atr * 1.2
        tp1 = current + atr * 1.5
        tp2 = current + atr * 3.0

        return StockEntrySignal(
            strategy=self.name,
            symbol=symbol,
            entry_price=current,
            initial_stop=stop,
            profit_target_1=tp1,
            profit_target_2=tp2,
            regime=regime,
            confidence=0.72,
            max_hold_hours=8,
            notes=f"Breakout above OR high {or_high:.2f}",
            reasoning={
                "timeframe": self.primary_tf, "atr": round(atr, 6),
                "or_high_5": round(or_high, 6),
                "ema20": round(ema20[-1], 6) if ema20 else None,
                "breakout_pct": round((current / or_high - 1) * 100, 3),
            },
        )


class PullbackReclaim:
    name = "Pullback Reclaim"
    primary_tf = "15m"

    def evaluate(self, symbol: str, history: list[dict], intraday: list[dict] | None = None) -> Optional[StockEntrySignal]:
        if len(history) < 30:
            return None

        closes = _closes(history)
        lows = _lows(history)
        current = closes[-1]
        atr = _atr_from_history(history)
        regime = _detect_regime(history)

        if regime != "trending_up":
            return None

        ema20 = _ema(closes, 20)
        if not ema20:
            return None

        ema_val = ema20[-1]
        was_below = any(c < ema_val for c in closes[-6:-1])
        if not (was_below and current > ema_val):
            return None

        pullback_low = min(lows[-5:])
        stop = pullback_low - atr * 0.2
        tp1 = current + atr * 1.5
        tp2 = current + atr * 2.5
        return StockEntrySignal(
            strategy=self.name,
            symbol=symbol,
            entry_price=current,
            initial_stop=stop,
            profit_target_1=tp1,
            profit_target_2=tp2,
            regime=regime,
            confidence=0.68,
            max_hold_hours=6,
            notes="Pullback to EMA20 reclaimed",
            reasoning={
                "timeframe": self.primary_tf, "atr": round(atr, 6),
                "ema20": round(ema_val, 6),
                "pullback_low_5": round(pullback_low, 6),
                "current_vs_ema20": round(current - ema_val, 6),
                "dip_below_ema_confirmed": True,
            },
        )


class TrendContinuationLadder:
    name = "Trend Continuation Ladder"
    primary_tf = "15m"

    def evaluate(self, symbol: str, history: list[dict], intraday: list[dict] | None = None) -> Optional[StockEntrySignal]:
        if len(history) < 40:
            return None

        closes = _closes(history)
        highs = _highs(history)
        lows = _lows(history)
        current = closes[-1]
        atr = _atr_from_history(history)
        regime = _detect_regime(history)

        if regime != "trending_up":
            return None

        higher_highs = all(highs[-i] > highs[-(i + 1)] for i in range(1, 4))
        higher_lows = all(lows[-i] > lows[-(i + 1)] for i in range(1, 4))
        if not (higher_highs and higher_lows):
            return None

        ema20 = _ema(closes, 20)
        if ema20 and current < ema20[-1] * 0.99:
            return None

        stop = current - atr * 1.5
        tp1 = current + atr * 1.5
        tp2 = current + atr * 3.0

        return StockEntrySignal(
            strategy=self.name,
            symbol=symbol,
            entry_price=current,
            initial_stop=stop,
            profit_target_1=tp1,
            profit_target_2=tp2,
            regime=regime,
            confidence=0.70,
            max_hold_hours=8,
            notes="Higher highs/lows ladder confirmed",
            reasoning={
                "timeframe": self.primary_tf, "atr": round(atr, 6),
                "ema20": round(ema20[-1], 6) if ema20 else None,
                "higher_highs_confirmed": True, "higher_lows_confirmed": True,
                "swing_high_1": round(highs[-1], 6), "swing_high_2": round(highs[-2], 6),
                "swing_low_1": round(lows[-1], 6), "swing_low_2": round(lows[-2], 6),
            },
        )


class MeanReversionBounce:
    name = "Mean Reversion Bounce"
    primary_tf = "5m"

    def evaluate(self, symbol: str, history: list[dict], intraday: list[dict] | None = None) -> Optional[StockEntrySignal]:
        if len(history) < 30:
            return None

        closes = _closes(history)
        current = closes[-1]
        atr = _atr_from_history(history)
        regime = _detect_regime(history)

        if regime not in ("ranging",):
            return None

        ema50 = _ema(closes, 50)
        if not ema50:
            return None

        mean = ema50[-1]
        pct_below = (mean - current) / mean
        if pct_below < 0.025:
            return None

        if closes[-1] > closes[-2]:
            stop = current - atr * 1.0
            tp1 = mean
            tp2 = mean + atr * 0.8

            return StockEntrySignal(
                strategy=self.name,
                symbol=symbol,
                entry_price=current,
                initial_stop=stop,
                profit_target_1=tp1,
                profit_target_2=tp2,
                regime=regime,
                confidence=0.62,
                max_hold_hours=4,
                notes=f"{pct_below*100:.1f}% below mean, bouncing",
                reasoning={
                    "timeframe": self.primary_tf, "atr": round(atr, 6),
                    "ema50_mean": round(mean, 6),
                    "pct_below_mean": round(pct_below * 100, 3),
                    "threshold_pct": 2.5, "bounce_confirmed": True,
                },
            )
        return None


class FailedBreakdownReclaim:
    name = "Failed Breakdown Reclaim"
    primary_tf = "5m"

    def evaluate(self, symbol: str, history: list[dict], intraday: list[dict] | None = None) -> Optional[StockEntrySignal]:
        if len(history) < 20:
            return None

        closes = _closes(history)
        lows = _lows(history)
        current = closes[-1]
        atr = _atr_from_history(history)
        regime = _detect_regime(history)

        support = min(lows[-20:-5])
        recent_min = min(lows[-5:])
        if recent_min >= support:
            return None

        if current > support and closes[-1] > closes[-2]:
            stop = recent_min - atr * 0.3
            tp1 = current + atr * 1.5
            tp2 = current + atr * 3.0

            return StockEntrySignal(
                strategy=self.name,
                symbol=symbol,
                entry_price=current,
                initial_stop=stop,
                profit_target_1=tp1,
                profit_target_2=tp2,
                regime=regime,
                confidence=0.67,
                max_hold_hours=6,
                notes=f"Failed breakdown below {support:.2f} reclaimed",
                reasoning={
                    "timeframe": self.primary_tf, "atr": round(atr, 6),
                    "support_level": round(support, 6),
                    "breakdown_low": round(recent_min, 6),
                    "breakdown_depth_atr": round((support - recent_min) / atr, 3) if atr else None,
                    "one_close_above_support": True,
                },
            )
        return None


class VolatilityCompressionBreakout:
    name = "Volatility Compression Breakout"
    primary_tf = "15m"

    def evaluate(self, symbol: str, history: list[dict], intraday: list[dict] | None = None) -> Optional[StockEntrySignal]:
        if len(history) < 30:
            return None

        closes = _closes(history)
        highs = _highs(history)
        lows = _lows(history)
        current = closes[-1]
        atr_recent = _atr_from_history(history[-10:], period=5) if len(history) >= 10 else 0
        atr_prior = _atr_from_history(history[-30:-10], period=14) if len(history) >= 30 else 0
        regime = _detect_regime(history)

        if atr_prior == 0 or atr_recent == 0:
            return None

        compressed = atr_recent < atr_prior * 0.6
        if not compressed:
            return None

        compression_high = max(highs[-10:])
        if current <= compression_high * 1.001:
            return None

        stop = current - atr_recent * 1.5
        tp1 = current + atr_prior * 1.5
        tp2 = current + atr_prior * 3.0

        return StockEntrySignal(
            strategy=self.name,
            symbol=symbol,
            entry_price=current,
            initial_stop=stop,
            profit_target_1=tp1,
            profit_target_2=tp2,
            regime=regime,
            confidence=0.73,
            max_hold_hours=8,
            notes=f"Volatility compressed, breakout above {compression_high:.2f}",
            reasoning={
                "timeframe": self.primary_tf,
                "atr_recent_10": round(atr_recent, 6),
                "atr_prior_20": round(atr_prior, 6),
                "compression_ratio": round(atr_recent / atr_prior, 3),
                "compression_threshold": 0.6,
                "compression_high_10": round(compression_high, 6),
                "breakout_pct": round((current / compression_high - 1) * 100, 3),
            },
        )


STOCK_ENTRY_STRATEGIES = [
    OpeningRangeBreakout(),
    PullbackReclaim(),
    TrendContinuationLadder(),
    MeanReversionBounce(),
    FailedBreakdownReclaim(),
    VolatilityCompressionBreakout(),
]


def evaluate_all(
    symbol: str,
    candles: "list[dict] | dict[str, list]",
) -> list[StockEntrySignal]:
    """
    Evaluate all stock entry strategies.

    *candles* may be:
      - A ``dict[str, list]`` mapping timeframe labels (``"5m"``, ``"15m"``,
        ``"daily"``, …) to OHLCV lists.  Each strategy uses its ``primary_tf``.
      - A plain ``list[dict]`` (backwards-compat / tests): the same list is
        broadcast to every strategy regardless of preferred timeframe.
    """
    if isinstance(candles, list):
        candles_by_tf: dict[str, list] = {
            tf: candles for tf in ("1m", "5m", "15m", "1H", "4H", "daily")
        }
    else:
        candles_by_tf = candles

    signals = []
    for strategy in STOCK_ENTRY_STRATEGIES:
        primary = candles_by_tf.get(strategy.primary_tf, [])
        if len(primary) < 20:
            continue
        try:
            sig = strategy.evaluate(symbol, primary)
            if sig:
                if sig.initial_stop >= sig.entry_price:
                    logger.warning(
                        "Skipping %s signal for %s: stop %.4f >= entry %.4f (near-zero ATR)",
                        sig.strategy, symbol, sig.initial_stop, sig.entry_price,
                    )
                else:
                    signals.append(sig)
        except Exception as exc:
            logger.error("Stock strategy %s error for %s: %s", strategy.name, symbol, exc)
    signals.sort(key=lambda s: s.confidence, reverse=True)
    return signals
