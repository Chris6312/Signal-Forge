from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Union
from typing import Optional
from app.common.watchlist_schema_v4 import (
    score_strategy_from_candles,
    compute_hint_bias,
    BotDecision,
    WEIGHTS,
    compute_features_for_signal,
)
from app.common.watchlist_schema_v4 import compute_strategy_score
from app.common.models.audit import AuditSource
import json
from app.common.models.bot_decision import BotStrategyDecision
from app.common.database import AsyncSessionLocal
import asyncio

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

    @property
    def strategy_key(self) -> str:
        mapping = {
            "Opening Range Breakout": "opening_range_breakout",
            "Pullback Reclaim": "pullback_reclaim",
            "Trend Continuation Ladder": "trend_continuation",
            "Trend Continuation": "trend_continuation",
            "Momentum Breakout Continuation": "trend_continuation",
            "Mean Reversion Bounce": "mean_reversion_bounce",
            "Failed Breakdown Reclaim": "failed_breakdown_reclaim",
            "Volatility Compression Breakout": "volatility_compression_breakout",
            "Breakout Retest Hold": "breakout_retest",
            "Range Rotation Reversal": "range_rotation",
        }
        return mapping.get(self.strategy, self.strategy.strip().lower().replace(" ", "_"))


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


def _ema_value_at(ema_series: list[float], period: int, idx: int) -> Optional[float]:
    ema_idx = idx - (period - 1)
    if ema_idx < 0 or ema_idx >= len(ema_series):
        return None
    return float(ema_series[ema_idx])


def _build_signal_snapshot(strategy_name: str, strategy_key: str, symbol: str, primary: list[dict], tf_minutes: int) -> StockEntrySignal:
    closes = _closes(primary)
    highs = _highs(primary)
    lows = _lows(primary)
    current = closes[-1]
    previous_close = closes[-2] if len(closes) >= 2 else current
    atr = _atr_from_history(primary)
    regime = _detect_regime(primary)

    ema9 = _ema(closes, 9)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)

    ema9_last = ema9[-1] if ema9 else None
    ema20_last = ema20[-1] if ema20 else None
    ema50_last = ema50[-1] if ema50 else None
    ema200_last = ema200[-1] if ema200 else None
    ema20_past = ema20[-5] if len(ema20) >= 5 else (ema20[0] if ema20 else None)

    volume_ratio = 1.0
    try:
        vols = [float(x.get("volume", 0) or 0) for x in primary[-20:]]
        if len(vols) >= 2:
            prev = max(sum(vols[:-1]) / max(len(vols) - 1, 1), 1.0)
            volume_ratio = vols[-1] / prev if vols[-1] > 0 else 1.0
    except Exception:
        volume_ratio = 1.0

    higher_highs = len(highs) >= 4 and highs[-4] < highs[-3] < highs[-2] < highs[-1]
    higher_lows = len(lows) >= 4 and lows[-4] < lows[-3] < lows[-2] < lows[-1]
    higher_closes = len(closes) >= 4 and closes[-4] < closes[-3] < closes[-2] < closes[-1]
    three_ascending = len(closes) >= 3 and closes[-3] < closes[-2] < closes[-1]

    recent_high_20 = max(highs[-20:]) if len(highs) >= 20 else max(highs)
    recent_low_20 = min(lows[-20:]) if len(lows) >= 20 else min(lows)

    trigger_type = "continuation"
    if strategy_key in {"pullback_reclaim", "failed_breakdown_reclaim"}:
        trigger_type = "reclaim"
    elif strategy_key == "mean_reversion_bounce":
        trigger_type = "mean_reversion"
    elif strategy_key in {"opening_range_breakout", "volatility_compression_breakout", "breakout_retest"}:
        trigger_type = "breakout"
    elif strategy_key == "range_rotation":
        trigger_type = "range_reversal"

    dip_below_ema = False
    reclaim_confirmed = False
    price_in_retest_band = False
    bounce_confirmed = False

    if ema20_last is not None:
        window_start = max(0, len(primary) - 7)
        for idx in range(window_start, len(primary) - 1):
            ema_at_idx = _ema_value_at(ema20, 20, idx) if ema20 else None
            if ema_at_idx is None:
                continue
            if closes[idx] < ema_at_idx or lows[idx] < ema_at_idx:
                dip_below_ema = True
        reclaim_confirmed = dip_below_ema and current > ema20_last
        price_in_retest_band = abs(current - ema20_last) / max(abs(current), 1.0) <= 0.02

    if strategy_key == "mean_reversion_bounce":
        bounce_confirmed = len(closes) >= 2 and closes[-1] > closes[-2]

    breakout_pct = 0.0
    if recent_high_20:
        breakout_pct = (current / max(recent_high_20, 1e-6) - 1.0) * 100.0

    fallback_stop = (min(lows[-6:]) - atr * 0.25) if atr else min(lows[-6:])
    fallback_tp1 = (current + atr * 1.5) if atr else current * 1.02

    extra_reasoning: dict[str, float | int | bool | None] = {}
    if strategy_key == "opening_range_breakout":
        session_bars = _latest_session_bars(primary)
        if len(session_bars) >= 4:
            opening_range = session_bars[:3]
        else:
            opening_range = primary[:3]
        if opening_range:
            opening_range_high = max(float(bar.get("high", 0) or 0) for bar in opening_range)
            opening_range_low = min(float(bar.get("low", 0) or 0) for bar in opening_range)
            breakout_acceptance_confirmed = bool(current > opening_range_high and (previous_close > opening_range_high or current > previous_close))
            extra_reasoning.update({
                "opening_range_high": round(opening_range_high, 6),
                "opening_range_low": round(opening_range_low, 6),
                "bars_in_session": len(session_bars),
                "opening_range_acceptance_confirmed": breakout_acceptance_confirmed,
            })
    elif strategy_key == "volatility_compression_breakout":
        recent_slice = primary[-10:]
        prior_slice = primary[-30:-10]
        if recent_slice and prior_slice:
            recent_atr_5 = _atr_from_history(recent_slice, period=min(5, max(1, len(recent_slice) - 1)))
            prior_atr_14 = _atr_from_history(prior_slice, period=min(14, max(1, len(prior_slice) - 1)))
            compression_high = max(float(x.get("high", 0) or 0) for x in recent_slice)
            compression_low = min(float(x.get("low", 0) or 0) for x in recent_slice)
            compression_acceptance_confirmed = bool(current > compression_high and (previous_close > compression_high or current > previous_close))
            extra_reasoning.update({
                "recent_atr_5": round(recent_atr_5, 6),
                "prior_atr_14": round(prior_atr_14, 6),
                "compression_high": round(compression_high, 6),
                "compression_low": round(compression_low, 6),
                "compression_acceptance_confirmed": compression_acceptance_confirmed,
            })

    return StockEntrySignal(
        strategy=strategy_name,
        symbol=symbol,
        entry_price=current,
        initial_stop=fallback_stop,
        profit_target_1=fallback_tp1,
        profit_target_2=(current + atr * 3.0) if atr else current * 1.04,
        regime=regime,
        confidence=0.0,
        max_hold_hours=8,
        notes="synthetic scoring snapshot",
        reasoning={
            "signal_schema_version": "v2",
            "strategy_key": strategy_key,
            "timeframe": f"{tf_minutes}m",
            "close": round(current, 6),
            "previous_close": round(previous_close, 6),
            "atr": round(atr, 6),
            "ema9": round(ema9_last, 6) if ema9_last is not None else None,
            "ema20": round(ema20_last, 6) if ema20_last is not None else None,
            "ema50": round(ema50_last, 6) if ema50_last is not None else None,
            "ema200": round(ema200_last, 6) if ema200_last is not None else None,
            "ema20_past": round(ema20_past, 6) if ema20_past is not None else None,
            "ema20_history": [round(x, 6) for x in ema20[-5:]] if len(ema20) >= 5 else [],
            "current_vs_ema20": round(current - ema20_last, 6) if ema20_last is not None else 0.0,
            "breakout_pct": round(breakout_pct, 6),
            "volume_ratio": round(volume_ratio, 6),
            "higher_highs_confirmed": higher_highs,
            "higher_lows_confirmed": higher_lows,
            "higher_closes_confirmed": higher_closes,
            "three_ascending_closes": three_ascending,
            "dip_below_ema_confirmed": dip_below_ema,
            "reclaim_confirmed": reclaim_confirmed,
            "price_in_retest_band": price_in_retest_band,
            "bounce_confirmed": bounce_confirmed,
            "trigger_type": trigger_type,
            "recent_high_20": round(recent_high_20, 6),
            "recent_low_20": round(recent_low_20, 6),
            "fallback_stop": round(fallback_stop, 6),
            "fallback_tp1": round(fallback_tp1, 6),
            **extra_reasoning,
        },
    )


def _merge_signal_with_snapshot(signal: StockEntrySignal | None, snapshot: StockEntrySignal) -> StockEntrySignal:
    if signal is None:
        return snapshot
    merged_reasoning = dict(snapshot.reasoning or {})
    merged_reasoning.update(signal.reasoning or {})
    signal.reasoning = merged_reasoning
    if not getattr(signal, "regime", None):
        signal.regime = snapshot.regime
    return signal


def _extract_candle_features_from_primary(strategy_key: str, strategy_name: str, symbol: str, primary: list[dict], tf_minutes: int):
    snapshot = _build_signal_snapshot(strategy_name, strategy_key, symbol, primary, tf_minutes)
    return compute_features_for_signal(strategy_key, snapshot, asset_class="stock")

def _parse_bar_time(value: str) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T", 1)):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


# Drop the still-forming bar when we can prove it is incomplete.
def _closed_history(history: list[dict], tf_minutes: int) -> list[dict]:
    if len(history) < 2:
        return history
    bar_time = _parse_bar_time(str(history[-1].get("time", "")))
    if bar_time is None:
        return history
    if bar_time.timestamp() + tf_minutes * 60 > datetime.now(timezone.utc).timestamp():
        return history[:-1]
    return history


# Use the latest session's first three 5m bars as the opening range.
def _latest_session_bars(history: list[dict]) -> list[dict]:
    dated: list[tuple[datetime, dict]] = []
    for bar in history:
        dt = _parse_bar_time(str(bar.get("time", "")))
        if dt is None:
            continue
        dated.append((dt, bar))

    if not dated:
        return history

    latest_date = dated[-1][0].date()
    return [bar for dt, bar in dated if dt.date() == latest_date]


class OpeningRangeBreakout:
    name = "Opening Range Breakout"
    primary_tf = "5m"

    def evaluate(self, symbol: str, history: list[dict], intraday: list[dict] | None = None) -> Optional[StockEntrySignal]:
        history = _closed_history(history, 5)
        if len(history) < 20:
            return None

        closes = _closes(history)
        atr = _atr_from_history(history)
        regime = _detect_regime(history)
        current = closes[-1]

        if regime != "trending_up":
            return None

        session_bars = _latest_session_bars(history)
        if len(session_bars) >= 4:
            opening_range = session_bars[:3]
            opening_range_high = max(float(bar.get("high", 0)) for bar in opening_range)
            opening_range_low = min(float(bar.get("low", 0)) for bar in opening_range)
            current_bar = session_bars[-1]
            current_low = float(current_bar.get("low", 0))
        else:
            opening_range = history[:3]
            opening_range_high = max(float(bar.get("high", 0)) for bar in opening_range)
            opening_range_low = min(float(bar.get("low", 0)) for bar in opening_range)
            current_bar = history[-1]
            current_low = float(current_bar.get("low", 0))

        recent_high = max(_highs(history)[-20:-1])

        # Breakout should clear both the session opening range and the recent swing high.
        if current <= opening_range_high * 1.001 or current <= recent_high * 1.001:
            return None

        ema20 = _ema(closes, 20)
        if not ema20 or current < ema20[-1]:
            return None

        breakout_range = max(current - opening_range_high, 0.0)
        if atr and breakout_range < atr * 0.15:
            return None

        stop = min(opening_range_low, current_low) - atr * 0.3
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
            notes=f"Breakout above opening range high {opening_range_high:.2f}",
            reasoning={
                "timeframe": self.primary_tf,
                "atr": round(atr, 6),
                "opening_range_high": round(opening_range_high, 6),
                "opening_range_low": round(opening_range_low, 6),
                "recent_high_20": round(recent_high, 6),
                "ema20": round(ema20[-1], 6),
                "breakout_pct": round((current / max(opening_range_high, recent_high) - 1) * 100, 3),
                "bars_in_session": len(session_bars),
            },
        )



class PullbackReclaim:
    name = "Pullback Reclaim"
    primary_tf = "15m"

    def evaluate(self, symbol: str, history: list[dict], intraday: list[dict] | None = None) -> Optional[StockEntrySignal]:
        history = _closed_history(history, 15)
        if len(history) < 30:
            return None

        closes = _closes(history)
        highs = _highs(history)
        lows = _lows(history)
        current = closes[-1]
        atr = _atr_from_history(history)
        regime = _detect_regime(history)

        if regime != "trending_up":
            return None

        ema20 = _ema(closes, 20)
        if not ema20:
            return None

        current_ema = ema20[-1]
        reclaim_window = range(max(1, len(history) - 7), len(history) - 1)
        dipped_below = False
        for idx in reclaim_window:
            ema_at_idx = _ema_value_at(ema20, 20, idx)
            if ema_at_idx is None:
                continue
            if closes[idx] < ema_at_idx or lows[idx] < ema_at_idx:
                dipped_below = True
                break

        if not dipped_below:
            return None

        prior_high = highs[-2]
        prior_close = closes[-2]
        if current <= current_ema or current <= prior_high or current <= prior_close:
            return None


        pullback_low = min(lows[-6:-1])
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
            notes="Bullish pullback reclaimed EMA20 with confirmation close",
            reasoning={
                "timeframe": self.primary_tf,
                "atr": round(atr, 6),
                "ema20": round(current_ema, 6),
                "pullback_low_5": round(pullback_low, 6),
                "current_vs_ema20": round(current - current_ema, 6),
                "prior_high": round(prior_high, 6),
                "dip_below_ema_confirmed": True,
            },
        )


class TrendContinuationLadder:
    name = "Trend Continuation Ladder"
    primary_tf = "15m"

    def evaluate(self, symbol: str, history: list[dict], intraday: list[dict] | None = None) -> Optional[StockEntrySignal]:
        history = _closed_history(history, 15)
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

        # Require a staircase of strength over the last four completed bars.
        higher_highs = highs[-4] < highs[-3] < highs[-2] < highs[-1]
        higher_lows = lows[-4] < lows[-3] < lows[-2] < lows[-1]
        higher_closes = closes[-4] < closes[-3] < closes[-2] < closes[-1]
        if not (higher_highs and higher_lows and higher_closes):
            return None

        ema20 = _ema(closes, 20)
        if not ema20:
            return None
        if current < ema20[-1]:
            return None

        stop = lows[-2] - atr * 0.6
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
            notes="Higher highs, higher lows, and higher closes ladder confirmed",
            reasoning={
                "timeframe": self.primary_tf,
                "atr": round(atr, 6),
                "ema20": round(ema20[-1], 6),
                "higher_highs_confirmed": True,
                "higher_lows_confirmed": True,
                "higher_closes_confirmed": True,
                "swing_high_1": round(highs[-1], 6),
                "swing_high_2": round(highs[-2], 6),
                "swing_low_1": round(lows[-1], 6),
                "swing_low_2": round(lows[-2], 6),
            },
        )


class MeanReversionBounce:
    name = "Mean Reversion Bounce"
    primary_tf = "5m"

    def evaluate(self, symbol: str, history: list[dict], intraday: list[dict] | None = None) -> Optional[StockEntrySignal]:
        history = _closed_history(history, 5)
        if len(history) < 50:
            return None

        closes = _closes(history)
        current = closes[-1]
        prior_close = closes[-2]
        atr = _atr_from_history(history)
        regime = _detect_regime(history)

        if regime != "ranging":
            return None

        ema50 = _ema(closes, 50)
        if not ema50:
            return None

        mean = ema50[-1]
        prior_pct_below = (mean - prior_close) / mean
        current_pct_below = (mean - current) / mean
        if prior_pct_below < 0.025:
            return None
        if not (current > prior_close and current < mean):
            return None

        stop = min(prior_close, current) - atr * 1.0
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
            notes=f"{prior_pct_below*100:.1f}% below mean, now bouncing",
            reasoning={
                "timeframe": self.primary_tf,
                "atr": round(atr, 6),
                "ema50_mean": round(mean, 6),
                "prior_pct_below_mean": round(prior_pct_below * 100, 3),
                "current_pct_below_mean": round(current_pct_below * 100, 3),
                "threshold_pct": 2.5,
                "bounce_confirmed": True,
            },
        )


class FailedBreakdownReclaim:
    name = "Failed Breakdown Reclaim"
    primary_tf = "5m"

    def evaluate(self, symbol: str, history: list[dict], intraday: list[dict] | None = None) -> Optional[StockEntrySignal]:
        history = _closed_history(history, 5)
        if len(history) < 20:
            return None

        closes = _closes(history)
        lows = _lows(history)
        highs = _highs(history)
        current = closes[-1]
        atr = _atr_from_history(history)
        regime = _detect_regime(history)

        support = min(lows[-20:-5])
        recent_min = min(lows[-5:-1])
        if recent_min >= support:
            return None

        prior_close = closes[-2]
        if not (prior_close <= support and current > support and current > highs[-2]):
            return None

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
            notes=f"Failed breakdown below {support:.2f} reclaimed with close back above support",
            reasoning={
                "timeframe": self.primary_tf,
                "atr": round(atr, 6),
                "support_level": round(support, 6),
                "breakdown_low": round(recent_min, 6),
                "prior_close": round(prior_close, 6),
                "reclaim_confirmed": True,
            },
        )


class VolatilityCompressionBreakout:
    name = "Volatility Compression Breakout"
    primary_tf = "15m"

    def evaluate(self, symbol: str, history: list[dict], intraday: list[dict] | None = None) -> Optional[StockEntrySignal]:
        history = _closed_history(history, 15)
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

        compression_high = max(highs[-10:-1])
        compression_low = min(lows[-10:-1])
        if current <= compression_high * 1.001:
            return None

        breakout_width = compression_high - compression_low
        if atr_recent and breakout_width > atr_prior * 2.2:
            return None

        stop = compression_low - atr_recent * 0.5
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
            notes=f"Compressed range breakout above {compression_high:.2f}",
            reasoning={
                "timeframe": self.primary_tf,
                "atr_recent_10": round(atr_recent, 6),
                "atr_prior_20": round(atr_prior, 6),
                "compression_ratio": round(atr_recent / atr_prior, 3),
                "compression_threshold": 0.6,
                "compression_high_10": round(compression_high, 6),
                "compression_low_10": round(compression_low, 6),
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


def _execution_readiness_adjustment(signal, candles_by_tf):
    reasoning = dict(getattr(signal, "reasoning", {}) or {})
    strategy_key = (
        _strategy_name_to_key(getattr(signal, "strategy", "") or "")
        or _strategy_name_to_key(str(reasoning.get("strategy_key") or ""))
        or _strategy_name_to_key(str(getattr(signal, "strategy_key", "") or ""))
    )

    cap_value = reasoning.get("execution_confidence_cap")
    confidence_cap = float(cap_value if cap_value is not None else getattr(signal, "confidence", 1.0) or 1.0)
    execution_ready = bool(reasoning.get("execution_ready", True))
    block_reason = reasoning.get("execution_block_reason")

    trigger_history = _closed_history(candles_by_tf.get("5m", []), 5)
    if len(trigger_history) < 20:
        return {
            "execution_ready": execution_ready,
            "confidence_cap": confidence_cap,
            "block_reason": block_reason,
        }

    closes = _closes(trigger_history)
    ema9 = _ema(closes, 9)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)

    if not ema20:
        return {
            "execution_ready": execution_ready,
            "confidence_cap": confidence_cap,
            "block_reason": block_reason,
        }

    current = closes[-1]
    previous = closes[-2] if len(closes) >= 2 else current
    ema9_now = ema9[-1] if ema9 else None
    ema20_now = ema20[-1]
    ema50_now = ema50[-1] if ema50 else None
    current_vs_fast_support = (current - ema20_now) / max(ema20_now, 1e-6)
    weak_closes = sum(1 for close in closes[-4:-1] if close <= ema20_now)
    breakout_acceptance = bool(reasoning.get("opening_range_acceptance_confirmed") or reasoning.get("compression_acceptance_confirmed"))

    def _result(ready: bool, cap: float, reason: str | None):
        return {
            "execution_ready": ready,
            "confidence_cap": min(confidence_cap, cap),
            "block_reason": reason,
        }

    if strategy_key == "opening_range_breakout":
        breakout_level = float(reasoning.get("opening_range_high") or reasoning.get("recent_high_20") or 0.0)
        breakout_extension = (current - breakout_level) / max(breakout_level, 1e-6) if breakout_level else 0.0

        if (ema9_now is not None and current <= ema9_now) or current <= ema20_now:
            return _result(False, 0.45, "fast_support_lost_on_trigger_candle")
        if breakout_level and current <= breakout_level:
            return _result(False, 0.50, "breakout_acceptance_not_confirmed")
        if breakout_level and previous <= breakout_level and current <= previous:
            return _result(False, 0.50, "breakout_acceptance_not_confirmed")
        if current_vs_fast_support >= 0.045 or breakout_extension >= 0.03:
            return _result(False, 0.58, "opening_range_breakout_too_extended")
        if not breakout_acceptance:
            return _result(False, 0.60, "breakout_acceptance_not_confirmed")
        if current_vs_fast_support >= 0.03 or breakout_extension >= 0.02:
            return _result(True, 0.62, None)
        if current <= previous or weak_closes >= 2:
            return _result(True, 0.60, None)
        return _result(True, 0.72, None)

    if strategy_key == "volatility_compression_breakout":
        breakout_level = float(reasoning.get("compression_high_10") or reasoning.get("compression_high") or 0.0)
        breakout_extension = (current - breakout_level) / max(breakout_level, 1e-6) if breakout_level else 0.0

        if (ema9_now is not None and current <= ema9_now) or current <= ema20_now:
            return _result(False, 0.45, "fast_support_lost_on_trigger_candle")
        if breakout_level and current <= breakout_level:
            return _result(False, 0.50, "breakout_acceptance_not_confirmed")
        if breakout_level and previous <= breakout_level and current <= previous:
            return _result(False, 0.50, "breakout_acceptance_not_confirmed")
        if current_vs_fast_support >= 0.05 or breakout_extension >= 0.04:
            return _result(False, 0.60, "compression_breakout_too_extended")
        if not breakout_acceptance:
            return _result(False, 0.60, "breakout_acceptance_not_confirmed")
        if current_vs_fast_support >= 0.03 or breakout_extension >= 0.025:
            return _result(True, 0.64, None)
        if current <= previous or weak_closes >= 2:
            return _result(True, 0.60, None)
        return _result(True, 0.73, None)

    if strategy_key == "trend_continuation":
        if (ema9_now is not None and current <= ema9_now) or current <= ema20_now:
            return _result(False, 0.50, "fast_support_lost_after_continuation")
        if current_vs_fast_support >= 0.06:
            return _result(False, 0.60, "continuation_too_extended")
        if current_vs_fast_support >= 0.04:
            return _result(True, 0.78, None)
        if current <= previous and weak_closes >= 1:
            return _result(False, 0.58, "failed_follow_through")
        if current <= previous or weak_closes >= 2 or (ema50_now is not None and current <= ema50_now):
            return _result(True, 0.74, None)
        return _result(True, 0.88, None)

    return {
        "execution_ready": execution_ready,
        "confidence_cap": confidence_cap,
        "block_reason": block_reason,
    }

# Scoring thresholds
MIN_SCORE_THRESHOLD = 0.35
STRONG_SIGNAL_THRESHOLD = 0.60


def _strategy_name_to_key(name: str) -> str | None:
    if "Pullback Reclaim" in name:
        return "pullback_reclaim"
    if "Failed Breakdown Reclaim" in name:
        return "failed_breakdown_reclaim"
    if "Trend Continuation Ladder" in name:
        return "trend_continuation"
    if "Trend Continuation" in name or "Momentum Breakout Continuation" in name:
        return "trend_continuation"
    if "Mean Reversion Bounce" in name:
        return "mean_reversion_bounce"
    if "Opening Range Breakout" in name:
        return "opening_range_breakout"
    if "Volatility Compression Breakout" in name:
        return "volatility_compression_breakout"
    if "Breakout Retest Hold" in name:
        return "breakout_retest"
    if "Range Rotation Reversal" in name:
        return "range_rotation"
    return None



def _strategy_specific_bonus(strategy_key: str, signal: StockEntrySignal) -> float:
    reasoning = signal.reasoning or {}
    bonus = 0.0

    if strategy_key == "pullback_reclaim":
        if reasoning.get("dip_below_ema_confirmed"):
            bonus += 0.08
        if reasoning.get("reclaim_confirmed"):
            bonus += 0.04

    elif strategy_key in {"opening_range_breakout", "volatility_compression_breakout", "breakout_retest"}:
        breakout_pct = float(reasoning.get("breakout_pct") or 0.0)
        breakout_confirmed = bool(
            reasoning.get("higher_highs_confirmed")
            or reasoning.get("higher_closes_confirmed")
            or reasoning.get("price_in_retest_band")
        )
        if breakout_confirmed:
            if breakout_pct >= 5.0:
                bonus += 0.18
            elif breakout_pct >= 2.0:
                bonus += 0.12
            elif breakout_pct > 0.2:
                bonus += 0.06
        if strategy_key == "volatility_compression_breakout":
            recent_atr = float(reasoning.get("recent_atr_5") or 0.0)
            prior_atr = float(reasoning.get("prior_atr_14") or 0.0)
            compression_ratio = float(reasoning.get("compression_ratio") or 1.0)
            if recent_atr > 0 and prior_atr > 0 and recent_atr < prior_atr * 0.60:
                bonus += 0.08
            if compression_ratio <= 0.75:
                bonus += 0.35
            if compression_ratio <= 0.60:
                bonus += 0.15
            if reasoning.get("reclaim_confirmed") and not reasoning.get("higher_highs_confirmed") and not reasoning.get("higher_lows_confirmed"):
                bonus += 0.30
            if reasoning.get("compression_acceptance_confirmed"):
                bonus += 0.10
        if strategy_key == "opening_range_breakout" and reasoning.get("opening_range_high"):
            bonus += 0.04

    elif strategy_key == "failed_breakdown_reclaim":
        if reasoning.get("reclaim_confirmed"):
            bonus += 0.08

    elif strategy_key == "mean_reversion_bounce":
        if reasoning.get("bounce_confirmed"):
            bonus += 0.10
        if signal.regime == "ranging":
            bonus += 0.05

    elif strategy_key == "trend_continuation":
        if reasoning.get("higher_closes_confirmed"):
            bonus += 0.05
        if reasoning.get("higher_highs_confirmed") and reasoning.get("higher_lows_confirmed"):
            bonus += 0.05

    return round(bonus, 6)

def evaluate_all(
    symbol: str,
    candles: "list[dict] | dict[str, list]",
    ai_hint: dict | None = None,
    payload_meta: dict | None = None,
    include_diagnostics: bool = False,
) -> list[StockEntrySignal] | dict:
    """
    Evaluate all stock entry strategies.

    *candles* may be:
      - A ``dict[str, list]`` mapping timeframe labels (``"5m"``, ``"15m"``,
        ``"daily"``, …) to OHLCV lists. Each strategy uses its ``primary_tf``.
      - A plain ``list[dict]`` (backwards-compat / tests): the same list is
        broadcast to every strategy regardless of preferred timeframe.
    """
    if isinstance(candles, list):
        candles_by_tf: dict[str, list] = {
            tf: candles for tf in ("1m", "5m", "15m", "1H", "4H", "daily")
        }
    else:
        candles_by_tf = candles

    tf_minutes_map = {"1m": 1, "5m": 5, "15m": 15, "1H": 60, "4H": 240, "daily": 1440}

    signals: list[StockEntrySignal] = []
    strategy_summaries: dict[str, dict] = {}

    for strategy in STOCK_ENTRY_STRATEGIES:
        primary = candles_by_tf.get(strategy.primary_tf, [])
        if len(primary) < 20:
            continue

        try:
            key = _strategy_name_to_key(strategy.name) or "opening_range_breakout"
            tf_minutes = tf_minutes_map.get(strategy.primary_tf, 15)

            snapshot = _build_signal_snapshot(strategy.name, key, symbol, primary, tf_minutes)

            raw_signal = None
            try:
                raw_signal = strategy.evaluate(symbol, primary)
            except Exception:
                raw_signal = None

            candidate = _merge_signal_with_snapshot(raw_signal, snapshot)
            candidate.reasoning = dict(getattr(candidate, "reasoning", {}) or {})
            candidate.reasoning["raw_signal_present"] = raw_signal is not None

            feature_scores = compute_features_for_signal(key, candidate, asset_class="stock")
            base_score = score_strategy_from_candles(key, feature_scores, regime=getattr(candidate, "regime", None), asset_class="stock")
            candidate.confidence = max(
                getattr(candidate, "confidence", 0.0) or 0.0,
                round(base_score, 6),
            )

            strategy_summaries[strategy.name] = {
                "key": key,
                "signal": candidate,
                "feature_scores": feature_scores,
                "base_score": round(base_score, 6),
                "raw_signal_present": raw_signal is not None,
            }

            if round(base_score, 6) >= round(MIN_SCORE_THRESHOLD, 6):
                signals.append(candidate)

        except Exception as exc:
            logger.error("Stock strategy %s error for %s: %s", strategy.name, symbol, exc)

    key_map = {
        "pullback_reclaim": ["Pullback Reclaim"],
        "failed_breakdown_reclaim": ["Failed Breakdown Reclaim"],
        "trend_continuation": ["Trend Continuation", "Trend Continuation Ladder", "Momentum Breakout Continuation"],
        "mean_reversion_bounce": ["Mean Reversion Bounce"],
        "opening_range_breakout": ["Opening Range Breakout"],
        "volatility_compression_breakout": ["Volatility Compression Breakout"],
    }

    evaluated: dict[str, dict] = {}

    for key, name_patterns in key_map.items():
        best = None
        for pat in name_patterns:
            summary = strategy_summaries.get(pat)
            if not summary:
                continue
            if best is None or summary["base_score"] > best["base_score"]:
                best = summary

        if best:
            matched = best["signal"]
            feature_scores = best["feature_scores"]

            base_score = compute_strategy_score(
                key,
                feature_scores,
                regime=getattr(matched, "regime", None),
                asset_class="stock",
            )
            base_score = min(1.0, base_score + _strategy_specific_bonus(key, matched))

            # AI hint bias must never rescue a structurally invalid setup.
            # Keep scores visible for diagnostics, but only allow bias when the
            # real strategy produced a concrete signal and the regime fit is not weak.
            regime_fit = float(feature_scores.get("regime_fit", 0.0) or 0.0)
            raw_signal_present = bool(best.get("raw_signal_present"))
            bias_allowed = raw_signal_present and regime_fit >= 0.5

            bias = compute_hint_bias(ai_hint, key) if (ai_hint and bias_allowed) else 0.0
            final_score = min(1.0, base_score + bias)

            evaluated[key] = {
                "valid": True,
                "base_score": round(base_score, 6),
                "bias": round(bias, 6),
                "final_score": round(final_score, 6),
                "reason": None,
                "feature_scores": {k2: round(v2, 6) for k2, v2 in feature_scores.items() if k2 != "_diagnostics"},
                "bias_allowed": bias_allowed,
            }
        else:
            evaluated[key] = {
                "valid": False,
                "base_score": 0.0,
                "bias": 0.0,
                "final_score": 0.0,
                "reason": "insufficient_candles",
                "feature_scores": {},
                "bias_allowed": False,
            }

    best_key = None
    for k, v in evaluated.items():
        if not v["valid"]:
            continue
        if best_key is None or v["final_score"] > evaluated[best_key]["final_score"] or (
            v["final_score"] == evaluated[best_key]["final_score"] and k < best_key
        ):
            best_key = k

    ai_strat = ai_hint.get("suggested_strategy") if ai_hint else None
    ai_conf = float(ai_hint.get("confidence")) if ai_hint and ai_hint.get("confidence") is not None else None

    ai_agreement = None
    bias_applied = False
    bias_amount = 0.0
    selected_score = 0.0

    if best_key:
        selected_score = evaluated[best_key]["final_score"]
        ai_agreement = (ai_strat == best_key) if ai_strat else None

    if ai_strat and ai_strat in evaluated:
        bias_applied = evaluated[ai_strat]["bias"] > 0.0
        bias_amount = evaluated[ai_strat]["bias"]

    decision = BotDecision(
        selected_strategy=best_key,
        selected_score=selected_score,
        evaluated_strategies={k: v["final_score"] for k, v in evaluated.items()},
        ai_hint_strategy=ai_strat,
        ai_hint_confidence=ai_conf,
        ai_hint_agreement=ai_agreement,
        ai_hint_bias_applied=bias_applied,
        ai_hint_bias_amount=bias_amount,
        feature_scores={k: v.get("feature_scores") for k, v in evaluated.items()},
    )

    for summary in strategy_summaries.values():
        strategy_key = summary["key"]
        signal = summary["signal"]
        selected_eval = evaluated.get(strategy_key)
        if not selected_eval or not selected_eval.get("valid"):
            continue
        signal.confidence = float(selected_eval["final_score"])

    signals = [
        summary["signal"]
        for summary in strategy_summaries.values()
        if evaluated.get(summary["key"], {}).get("valid")
        and float(evaluated[summary["key"]]["final_score"]) >= round(MIN_SCORE_THRESHOLD, 6)
    ]
    signals.sort(key=lambda s: s.confidence, reverse=True)

    audit_payload = {
        "schema_version": payload_meta.get("schema_version") if payload_meta else None,
        "source": payload_meta.get("source") if payload_meta else None,
        "scan_id": payload_meta.get("scan_id") if payload_meta else None,
        "symbol": symbol,
        "asset_class": "stock",
        "ai_hint_strategy": ai_strat,
        "ai_hint_confidence": ai_conf,
        "bot_selected_strategy": decision.selected_strategy,
        "bot_selected_score": decision.selected_score,
        "ai_hint_agreement": decision.ai_hint_agreement,
        "ai_hint_bias_applied": decision.ai_hint_bias_applied,
        "ai_hint_bias_amount": decision.ai_hint_bias_amount,
        "evaluated_strategy_scores": decision.evaluated_strategies,
        "evaluated_strategies": {
            k: {
                "valid": v["valid"],
                "base_score": v["base_score"],
                "bias": v["bias"],
                "final_score": v["final_score"],
                "reason": v["reason"],
                "feature_scores": v["feature_scores"],
            }
            for k, v in evaluated.items()
        },
        "rejected_strategies": {k: v["reason"] for k, v in evaluated.items() if not v["valid"]},
        "feature_scores": {k: v.get("feature_scores") for k, v in evaluated.items()},
        "timestamp_received": payload_meta.get("timestamp") if payload_meta else None,
        "timestamp_evaluated": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("[AUDIT] BOT_STRATEGY_DECISION | %s | %s", symbol, json.dumps(audit_payload))

    async def _persist_decision():
        try:
            async with AsyncSessionLocal() as db:
                row = BotStrategyDecision(
                    evaluated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    received_at=payload_meta.get("timestamp") if payload_meta else None,
                    symbol=symbol,
                    normalized_symbol=symbol,
                    asset_class="stock",
                    source=payload_meta.get("source") if payload_meta else None,
                    scan_id=payload_meta.get("scan_id") if payload_meta else None,
                    schema_version=payload_meta.get("schema_version") if payload_meta else None,
                    regime=signals[0].regime if signals else None,
                    ai_hint_present=bool(ai_hint),
                    ai_hint_strategy=ai_strat,
                    ai_hint_confidence=ai_conf,
                    ai_hint_bias_applied=decision.ai_hint_bias_applied,
                    ai_hint_bias_amount=decision.ai_hint_bias_amount,
                    bot_selected_strategy=decision.selected_strategy,
                    bot_selected_score=decision.selected_score or 0.0,
                    ai_hint_agreement=decision.ai_hint_agreement,
                    evaluated_strategy_scores=decision.evaluated_strategies,
                    rejected_strategies={k: v["reason"] for k, v in evaluated.items() if not v["valid"]},
                    feature_scores=decision.feature_scores or {},
                    decision_context={"payload_meta": payload_meta},
                )
                db.add(row)
                await db.commit()
        except Exception:
            logger.exception("Failed to persist BotStrategyDecision for %s", symbol)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_persist_decision())
    except RuntimeError:
        logger.debug("Skipping BotStrategyDecision persistence for %s outside a running event loop", symbol)
    except Exception:
        logger.exception("Failed to schedule BotStrategyDecision persistence for %s", symbol)

    if include_diagnostics:
        return {
            "signals": signals,
            "top_strategy": decision.selected_strategy,
            "top_confidence": decision.selected_score,
            "evaluated_strategy_scores": decision.evaluated_strategies,
            "evaluated_strategies": {
                k: {
                    "valid": v["valid"],
                    "base_score": v["base_score"],
                    "bias": v["bias"],
                    "final_score": v["final_score"],
                    "reason": v["reason"],
                    "feature_scores": v["feature_scores"],
                }
                for k, v in evaluated.items()
            },
            "rejected_strategies": {k: v["reason"] for k, v in evaluated.items() if not v["valid"]},
            "feature_scores": decision.feature_scores or {},
            "timestamp_evaluated": audit_payload["timestamp_evaluated"],
        }

    return signals
