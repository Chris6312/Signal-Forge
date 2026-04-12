from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone
from typing import Optional
from app.common.watchlist_schema_v4 import score_strategy_from_candles, compute_hint_bias, BotDecision, WEIGHTS, compute_features_for_signal, compute_strategy_score
import json

logger = logging.getLogger(__name__)


def _closes(ohlcv):
    return [float(c[4]) for c in ohlcv]


def _highs(ohlcv):
    return [float(c[2]) for c in ohlcv]


def _lows(ohlcv):
    return [float(c[3]) for c in ohlcv]


def _volumes(ohlcv):
    out = []
    for c in ohlcv:
        try:
            out.append(float(c[5]))
        except Exception:
            out.append(0.0)
    return out


def _build_signal_snapshot(strategy_name: str, strategy_key: str, symbol: str, ohlcv, tf_minutes: int) -> "EntrySignal":
    ohlcv = _closed_ohlcv(ohlcv, tf_minutes)
    closes = _closes(ohlcv)
    highs = _highs(ohlcv)
    lows = _lows(ohlcv)
    volumes = _volumes(ohlcv)
    current = closes[-1] if closes else 0.0
    atr = _atr(ohlcv) if len(ohlcv) >= 15 else 0.0
    regime = _detect_regime(ohlcv)

    ema9 = _ema(closes, 9)
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    recent_high = max(highs[-20:-1]) if len(highs) >= 21 else (max(highs[:-1]) if len(highs) > 1 else current)
    recent_low = min(lows[-20:-1]) if len(lows) >= 21 else (min(lows[:-1]) if len(lows) > 1 else current)
    volume_now = volumes[-1] if volumes else 0.0
    volume_base = (sum(volumes[-6:-1]) / max(1, len(volumes[-6:-1]))) if len(volumes) >= 6 else (sum(volumes[:-1]) / max(1, len(volumes[:-1])) if len(volumes) > 1 else 0.0)
    volume_ratio = (volume_now / volume_base) if volume_base else 1.0

    trigger_type = "continuation"
    if strategy_key == "pullback_reclaim":
        trigger_type = "reclaim"
    elif strategy_key == "mean_reversion_bounce":
        trigger_type = "mean_reversion"
    elif strategy_key == "range_rotation":
        trigger_type = "range_reversal"
    elif strategy_key == "breakout_retest":
        trigger_type = "breakout"
    elif strategy_key == "range_breakout":
        trigger_type = "breakout"

    dip_below_ema_confirmed = bool(
        ema20
        and len(closes) >= 6
        and any(
            closes[i] < _ema_value_at(ema20, 20, i)
            for i in range(max(1, len(closes) - 6), len(closes) - 1)
            if _ema_value_at(ema20, 20, i) is not None
        )
    )
    bounce_confirmed = bool(len(closes) >= 2 and closes[-1] > closes[-2])
    reclaim_confirmed = bool(
        ema20
        and current > ema20[-1]
        and (
            dip_below_ema_confirmed
            or (len(closes) >= 2 and closes[-2] <= ema20[-1] and current > closes[-2])
            or (bounce_confirmed and len(ema20) >= 2 and ema20[-1] >= ema20[-2])
        )
    )

    higher_highs_confirmed = bool(len(highs) >= 4 and highs[-4] < highs[-3] < highs[-2] < highs[-1])
    higher_lows_confirmed = bool(len(lows) >= 4 and lows[-4] < lows[-3] < lows[-2] < lows[-1])
    higher_closes_confirmed = bool(len(closes) >= 4 and closes[-4] < closes[-3] < closes[-2] < closes[-1])
    three_ascending_closes = bool(len(closes) >= 3 and closes[-3] < closes[-2] < closes[-1])

    # Shared defaults
    breakout_pct = round(((current / max(recent_high, 1e-6)) - 1.0) * 100.0, 3) if recent_high else 0.0
    price_in_retest_band = bool(recent_high and abs(current - recent_high) / max(abs(recent_high), 1.0) <= 0.015)
    fallback_stop = round((recent_low - atr * 0.5) if recent_low else current - atr * 0.5, 6)
    fallback_tp1 = round(current + atr * 1.5, 6)

    # Separate the 4H patterns so they do not share the same interpretation.
    if strategy_key == "range_rotation":
        range_lookback = 30 if len(highs) >= 31 else max(5, len(highs) - 1)
        range_high = max(highs[-range_lookback:-1]) if len(highs) > 1 else current
        range_low = min(lows[-range_lookback:-1]) if len(lows) > 1 else current
        range_mid = (range_high + range_low) / 2.0 if range_high and range_low else current
        range_width = max(range_high - range_low, 1e-6)
        distance_from_low_pct = ((current - range_low) / range_width) * 100.0 if range_width else 50.0

        breakout_pct = round(((current - range_mid) / max(abs(range_mid), 1e-6)) * 100.0, 3)
        price_in_retest_band = False
        fallback_stop = round(range_low - atr * 0.5, 6)
        fallback_tp1 = round(min(range_high, current + atr * 1.5), 6)

    elif strategy_key == "breakout_retest":
        lookback = 40 if len(highs) >= 41 else max(12, len(highs) - 1)
        prior_high = max(highs[-lookback:-10]) if len(highs) >= 12 else recent_high
        breakout_high = max(highs[-10:-1]) if len(highs) >= 11 else recent_high
        retest_low = min(lows[-4:-1]) if len(lows) >= 5 else recent_low

        breakout_anchor = prior_high if prior_high else recent_high
        breakout_pct = round(((current / max(breakout_anchor, 1e-6)) - 1.0) * 100.0, 3)
        price_in_retest_band = bool(
            breakout_anchor
            and retest_low
            and abs(retest_low - breakout_anchor) / max(abs(breakout_anchor), 1.0) <= 0.02
        )
        fallback_stop = round(min(retest_low, breakout_anchor) - atr * 0.5, 6)
        fallback_tp1 = round(current + atr * 2.0, 6)

    reasoning = {
        "signal_schema_version": "v2",
        "strategy_key": strategy_key,
        "timeframe": f"{tf_minutes}m",
        "close": round(current, 6),
        "atr": round(atr, 6),
        "ema9": round(ema9[-1], 6) if ema9 else None,
        "ema20": round(ema20[-1], 6) if ema20 else None,
        "ema50": round(ema50[-1], 6) if ema50 else None,
        "ema200": round(ema200[-1], 6) if ema200 else None,
        "ema20_past": round(ema20[-5], 6) if ema20 and len(ema20) >= 5 else None,
        "ema20_history": [round(v, 6) for v in ema20[-5:]] if ema20 else [],
        "current_vs_ema20": round(current - ema20[-1], 6) if ema20 else 0.0,
        "breakout_pct": breakout_pct,
        "volume_ratio": round(volume_ratio, 6),
        "higher_highs_confirmed": higher_highs_confirmed,
        "higher_lows_confirmed": higher_lows_confirmed,
        "higher_closes_confirmed": higher_closes_confirmed,
        "three_ascending_closes": three_ascending_closes,
        "dip_below_ema_confirmed": dip_below_ema_confirmed,
        "reclaim_confirmed": reclaim_confirmed,
        "price_in_retest_band": price_in_retest_band,
        "bounce_confirmed": bounce_confirmed,
        "trigger_type": trigger_type,
        "recent_high_20": round(recent_high, 6) if recent_high else None,
        "recent_low_20": round(recent_low, 6) if recent_low else None,
        "fallback_stop": fallback_stop,
        "fallback_tp1": fallback_tp1,
    }
    reasoning.update(_execution_readiness_metadata(strategy_key, reasoning))

    if strategy_key == "range_rotation":
        range_lookback = 30 if len(highs) >= 31 else max(5, len(highs) - 1)
        range_high = max(highs[-range_lookback:-1]) if len(highs) > 1 else current
        range_low = min(lows[-range_lookback:-1]) if len(lows) > 1 else current
        range_mid = (range_high + range_low) / 2.0 if range_high and range_low else current
        range_width = max(range_high - range_low, 1e-6)
        distance_from_low_pct = ((current - range_low) / range_width) * 100.0 if range_width else 50.0

        reasoning.update(
            {
                "range_low_30": round(range_low, 6) if range_low else None,
                "range_high_30": round(range_high, 6) if range_high else None,
                "range_mid_30": round(range_mid, 6) if range_mid else None,
                "distance_from_low_pct": round(distance_from_low_pct, 3),
            }
        )

    elif strategy_key == "breakout_retest":
        lookback = 40 if len(highs) >= 41 else max(12, len(highs) - 1)
        prior_high = max(highs[-lookback:-10]) if len(highs) >= 12 else recent_high
        breakout_high = max(highs[-10:-1]) if len(highs) >= 11 else recent_high
        retest_low = min(lows[-4:-1]) if len(lows) >= 5 else recent_low

        reasoning.update(
            {
                "prior_high_40": round(prior_high, 6) if prior_high else None,
                "breakout_high_10": round(breakout_high, 6) if breakout_high else None,
                "retest_low": round(retest_low, 6) if retest_low else None,
            }
        )
    return EntrySignal(
        strategy=strategy_name,
        symbol=symbol,
        entry_price=current,
        initial_stop=float(reasoning["fallback_stop"]),
        profit_target_1=float(reasoning["fallback_tp1"]),
        profit_target_2=round(current + atr * 3.0, 6),
        regime=regime,
        confidence=0.0,
        reasoning=reasoning,
    )


def _merge_signal_with_snapshot(signal: "EntrySignal | None", snapshot: "EntrySignal") -> "EntrySignal":
    if signal is None:
        snapshot.confidence = 0.0
        return snapshot
    merged_reasoning = dict(snapshot.reasoning)
    merged_reasoning.update(getattr(signal, "reasoning", {}) or {})
    signal.reasoning = merged_reasoning
    if getattr(signal, "entry_price", 0.0) <= 0:
        signal.entry_price = snapshot.entry_price
    if getattr(signal, "initial_stop", 0.0) <= 0:
        signal.initial_stop = snapshot.initial_stop
    if getattr(signal, "profit_target_1", 0.0) <= 0:
        signal.profit_target_1 = snapshot.profit_target_1
    if getattr(signal, "profit_target_2", 0.0) <= 0:
        signal.profit_target_2 = snapshot.profit_target_2
    if not getattr(signal, "regime", None):
        signal.regime = snapshot.regime
    return signal


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
    reasoning: dict = field(default_factory=dict)


def _execution_readiness_metadata(strategy_key: str, reasoning: dict) -> dict:
    reasoning = reasoning or {}
    current_vs_ema20 = reasoning.get("current_vs_ema20")
    ready = True
    confidence_cap = 1.0
    block_reason = None

    def _apply(cap: float, reason: str | None = None, block: bool = False):
        nonlocal confidence_cap, ready, block_reason
        confidence_cap = min(confidence_cap, cap)
        if reason:
            block_reason = reason
        if block:
            ready = False

    if strategy_key == "breakout_retest":
        if reasoning.get("reclaim_confirmed") is False:
            _apply(0.55, "retest_reclaim_unresolved")
        if current_vs_ema20 is not None and float(current_vs_ema20) <= 0:
            _apply(0.35, "below_fast_ema_support", block=True)
        if not reasoning.get("higher_closes_confirmed") and not reasoning.get("three_ascending_closes"):
            _apply(0.45, "weak_follow_through")

    elif strategy_key == "pullback_reclaim":
        if not reasoning.get("reclaim_confirmed"):
            _apply(0.50, "reclaim_not_confirmed")
        if current_vs_ema20 is not None and float(current_vs_ema20) <= 0:
            _apply(0.40, "below_reclaim_cluster", block=True)

    elif strategy_key == "trend_continuation":
        if current_vs_ema20 is not None and float(current_vs_ema20) <= 0:
            _apply(0.55, "fast_support_lost", block=True)
        if not reasoning.get("higher_highs_confirmed") or not reasoning.get("higher_lows_confirmed"):
            _apply(0.80, "follow_through_not_fully_confirmed")
        breakout_pct = reasoning.get("breakout_pct")
        if breakout_pct is not None and float(breakout_pct) < 0.5:
            _apply(0.70, "breakout_extension_unproven")

    return {
        "execution_ready": ready,
        "execution_confidence_cap": round(confidence_cap, 6),
        "execution_block_reason": block_reason,
    }


def _ema(prices, period):
    if len(prices) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema.append(p * k + ema[-1] * (1 - k))
    return ema


def _atr(ohlcv, period=14):
    if len(ohlcv) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(ohlcv)):
        high = float(ohlcv[i][2])
        low = float(ohlcv[i][3])
        prev_close = float(ohlcv[i - 1][4])
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs[-period:]) / period


def _detect_regime(ohlcv):
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


def _ema_value_at(ema_series, period, idx):
    ema_idx = idx - (period - 1)
    if ema_idx < 0 or ema_idx >= len(ema_series):
        return None
    return ema_series[ema_idx]


# Crypto OHLC arrays are [ts, open, high, low, close, volume].
def _closed_ohlcv(ohlcv, tf_minutes: int):
    if len(ohlcv) < 2:
        return ohlcv
    try:
        bar_open_ts = float(ohlcv[-1][0])
    except (TypeError, ValueError, IndexError):
        return ohlcv
    if bar_open_ts + tf_minutes * 60 > datetime.now(timezone.utc).timestamp():
        return ohlcv[:-1]
    return ohlcv


class MomentumBreakoutContinuation:
    name = "Momentum Breakout Continuation"
    primary_tf = "1H"

    def evaluate(self, symbol, ohlcv):
        ohlcv = _closed_ohlcv(ohlcv, 60)
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
        stop = recent_high - atr * 0.5
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
            notes=f"Breakout continuation above {recent_high:.4f}",
            reasoning={
                "timeframe": self.primary_tf,
                "atr": round(atr, 6),
                "ema20": round(ema20[-1], 6),
                "recent_high_20": round(recent_high, 6),
                "breakout_pct": round((current / recent_high - 1) * 100, 3),
                "current_vs_ema20": round(current - ema20[-1], 6),
            },
        )


class PullbackReclaim:
    name = "Pullback Reclaim"
    primary_tf = "1H"

    def evaluate(self, symbol, ohlcv):
        ohlcv = _closed_ohlcv(ohlcv, 60)
        if len(ohlcv) < 30:
            return None
        closes = [float(c[4]) for c in ohlcv]
        highs = [float(c[2]) for c in ohlcv]
        lows = [float(c[3]) for c in ohlcv]
        current = closes[-1]
        atr = _atr(ohlcv)
        regime = _detect_regime(ohlcv)
        if regime != "trending_up":
            return None
        ema20 = _ema(closes, 20)
        if not ema20:
            return None
        current_ema = ema20[-1]
        dipped_below = False
        for idx in range(max(1, len(ohlcv) - 7), len(ohlcv) - 1):
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
        stop = pullback_low - atr * 0.3
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


class MeanReversionBounce:
    name = "Mean Reversion Bounce"
    primary_tf = "1H"

    def evaluate(self, symbol, ohlcv):
        ohlcv = _closed_ohlcv(ohlcv, 60)
        if len(ohlcv) < 50:
            return None
        closes = [float(c[4]) for c in ohlcv]
        current = closes[-1]
        prior_close = closes[-2]
        atr = _atr(ohlcv)
        regime = _detect_regime(ohlcv)
        if regime not in ("ranging", "unknown"):
            return None
        ema50 = _ema(closes, 50)
        if not ema50:
            return None
        mean = ema50[-1]
        prior_pct_below = (mean - prior_close) / mean
        current_pct_below = (mean - current) / mean
        if prior_pct_below < 0.03:
            return None
        if not (current > prior_close and current < mean):
            return None
        stop = min(prior_close, current) - atr * 1.0
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
            notes=f"{prior_pct_below*100:.1f}% below mean, now bouncing",
            reasoning={
                "timeframe": self.primary_tf,
                "atr": round(atr, 6),
                "ema50_mean": round(mean, 6),
                "prior_pct_below_mean": round(prior_pct_below * 100, 3),
                "current_pct_below_mean": round(current_pct_below * 100, 3),
                "threshold_pct": 3.0,
                "bounce_confirmed": True,
            },
        )


class RangeRotationReversal:
    name = "Range Rotation Reversal"
    primary_tf = "4H"

    def evaluate(self, symbol, ohlcv):
        ohlcv = _closed_ohlcv(ohlcv, 240)
        if len(ohlcv) < 40:
            return None
        closes = [float(c[4]) for c in ohlcv]
        highs = [float(c[2]) for c in ohlcv]
        lows = [float(c[3]) for c in ohlcv]
        current = closes[-1]
        atr = _atr(ohlcv)
        regime = _detect_regime(ohlcv)
        if regime != "ranging":
            return None
        range_low = min(lows[-30:-1])
        range_high = max(highs[-30:-1])
        if current > range_low * 1.02:
            return None
        if not (closes[-3] < closes[-2] < closes[-1]):
            return None
        stop = range_low - atr * 0.5
        tp1 = min(range_high, current + atr * 2.0)
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
            reasoning={
                "timeframe": self.primary_tf,
                "atr": round(atr, 6),
                "range_low_30": round(range_low, 6),
                "range_high_30": round(range_high, 6),
                "distance_from_low_pct": round((current / range_low - 1) * 100, 3),
                "threshold_pct": 2.0,
                "three_ascending_closes": True,
            },
        )


class BreakoutRetestHold:
    name = "Breakout Retest Hold"
    primary_tf = "4H"

    def evaluate(self, symbol, ohlcv):
        ohlcv = _closed_ohlcv(ohlcv, 240)
        if len(ohlcv) < 40:
            return None
        closes = [float(c[4]) for c in ohlcv]
        highs = [float(c[2]) for c in ohlcv]
        lows = [float(c[3]) for c in ohlcv]
        current = closes[-1]
        atr = _atr(ohlcv)
        regime = _detect_regime(ohlcv)
        prior_high = max(highs[-40:-10])
        breakout_high = max(highs[-10:-1])
        if breakout_high <= prior_high:
            return None
        retest_low = min(lows[-4:-1])
        if retest_low > prior_high * 1.015 or retest_low < prior_high * 0.985:
            return None
        if current < prior_high or current < closes[-2]:
            return None
        stop = min(retest_low, prior_high) - atr * 0.5
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
            notes=f"Breakout level {prior_high:.4f} held on retest",
            reasoning={
                "timeframe": self.primary_tf,
                "atr": round(atr, 6),
                "prior_high_40": round(prior_high, 6),
                "breakout_high_10": round(breakout_high, 6),
                "retest_low": round(retest_low, 6),
                "price_in_retest_band": True,
            },
        )


class FailedBreakdownReclaim:
    name = "Failed Breakdown Reclaim"
    primary_tf = "1H"

    def evaluate(self, symbol, ohlcv):
        ohlcv = _closed_ohlcv(ohlcv, 60)
        if len(ohlcv) < 20:
            return None
        closes = [float(c[4]) for c in ohlcv]
        lows = [float(c[3]) for c in ohlcv]
        highs = [float(c[2]) for c in ohlcv]
        current = closes[-1]
        atr = _atr(ohlcv)
        regime = _detect_regime(ohlcv)
        support = min(lows[-20:-5])
        recent_min = min(lows[-5:-1])
        if recent_min >= support:
            return None
        prior_close = closes[-2]
        if not (prior_close <= support and current > support and current > highs[-2]):
            return None
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
            notes=f"Failed breakdown below {support:.4f} reclaimed with close back above support",
            reasoning={
                "timeframe": self.primary_tf,
                "atr": round(atr, 6),
                "support_level": round(support, 6),
                "breakdown_low": round(recent_min, 6),
                "prior_close": round(prior_close, 6),
                "reclaim_confirmed": True,
            },
        )


ENTRY_STRATEGIES = [
    MomentumBreakoutContinuation(),
    PullbackReclaim(),
    MeanReversionBounce(),
    RangeRotationReversal(),
    BreakoutRetestHold(),
    FailedBreakdownReclaim(),
]

# Scoring thresholds
MIN_SCORE_THRESHOLD = 0.20
STRONG_SIGNAL_THRESHOLD = 0.60


def _strategy_name_to_key(name: str) -> str | None:
    if "Pullback Reclaim" in name or "Failed Breakdown Reclaim" in name:
        return "pullback_reclaim"

    if "Momentum Breakout Continuation" in name:
        return "trend_continuation"

    if "Mean Reversion Bounce" in name:
        return "mean_reversion_bounce"

    # keep range patterns separated so strong trends do not get bucket-dominated
    if "Range Rotation Reversal" in name:
        return "range_rotation"

    if "Breakout Retest Hold" in name:
        return "breakout_retest"

    return None


def evaluate_all(symbol, candles_by_tf, include_diagnostics: bool = False):
    if isinstance(candles_by_tf, list):
        candles_by_tf = {
            "15m": candles_by_tf,
            "1H": candles_by_tf,
            "4H": candles_by_tf,
            "daily": candles_by_tf,
        }

    signals = []
    strategy_summaries = {}
    for strat in ENTRY_STRATEGIES:
        ohlcv = candles_by_tf.get(strat.primary_tf, [])
        if len(ohlcv) < 20:
            continue
        try:
            key = _strategy_name_to_key(strat.name) or "range_breakout"
            tf_minutes = 240 if strat.primary_tf == "4H" else 60
            snapshot = _build_signal_snapshot(strat.name, key, symbol, ohlcv, tf_minutes)

            try:
                sig = strat.evaluate(symbol, ohlcv)
            except Exception:
                sig = None

            candidate = _merge_signal_with_snapshot(sig, snapshot)
            candidate.reasoning = dict(getattr(candidate, "reasoning", {}) or {})
            candidate.reasoning["raw_signal_present"] = sig is not None

            feature_scores = compute_features_for_signal(key, candidate, asset_class="crypto")
            base_score = score_strategy_from_candles(key, feature_scores, regime=getattr(candidate, "regime", None), asset_class="crypto")

            logger.debug(
                "CRYPTO_SCORE_DEBUG | %s | %s | feature_scores=%s | base_score_raw=%r | threshold_raw=%r | raw_signal_present=%s | passes=%s",
                symbol,
                key,
                json.dumps(feature_scores),
                base_score,
                MIN_SCORE_THRESHOLD,
                sig is not None,
                round(base_score, 6) >= round(MIN_SCORE_THRESHOLD, 6),
            )

            candidate.confidence = max(getattr(candidate, "confidence", 0.0) or 0.0, round(base_score, 6))

            strategy_summaries[strat.name] = {
                "key": key,
                "signal": candidate,
                "feature_scores": feature_scores,
                "base_score": round(base_score, 6),
                "passes_threshold": round(base_score, 6) >= round(MIN_SCORE_THRESHOLD, 6),
                "raw_signal_present": sig is not None,
            }

            if strategy_summaries[strat.name]["passes_threshold"]:
                signals.append(candidate)
        except Exception as e:
            logger.error("Strategy %s failed for %s: %s", strat.name, symbol, e)

    key_map = {
        "pullback_reclaim": ["Pullback Reclaim", "Failed Breakdown Reclaim"],
        "trend_continuation": ["Momentum Breakout Continuation"],
        "mean_reversion_bounce": ["Mean Reversion Bounce"],

        # separated buckets
        "range_rotation": ["Range Rotation Reversal"],
        "breakout_retest": ["Breakout Retest Hold"],
    }

    evaluated = {}
    for key, patterns in key_map.items():
        best = None
        for pattern in patterns:
            summary = strategy_summaries.get(pattern)
            if not summary:
                continue
            if best is None or summary["base_score"] > best["base_score"]:
                best = summary
        if best:
            signal = best["signal"]
            feature_scores = best["feature_scores"]
            base_score = compute_strategy_score(key, feature_scores, regime=getattr(signal, "regime", None), asset_class="crypto")
            evaluated[key] = {
                "valid": True,
                "base_score": round(base_score, 6),
                "bias": 0.0,
                "final_score": round(base_score, 6),
                "reason": None,
                "feature_scores": {k: round(v, 6) for k, v in feature_scores.items() if k != "_diagnostics"},
                "raw_signal_present": bool(best.get("raw_signal_present")),
            }
        else:
            evaluated[key] = {
                "valid": False,
                "base_score": 0.0,
                "bias": 0.0,
                "final_score": 0.0,
                "reason": "insufficient_candles",
                "feature_scores": {},
            }

    best_key = None
    for key, payload in evaluated.items():
        if not payload["valid"]:
            continue
        if best_key is None or payload["final_score"] > evaluated[best_key]["final_score"] or (
            payload["final_score"] == evaluated[best_key]["final_score"] and key < best_key
        ):
            best_key = key

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

    selected_score = float(evaluated[best_key]["final_score"]) if best_key else 0.0

    audit_payload = {
        "symbol": symbol,
        "asset_class": "crypto",
        "bot_selected_strategy": best_key,
        "bot_selected_score": selected_score,
        "evaluated_strategy_scores": {k: v["final_score"] for k, v in evaluated.items()},
        "evaluated_strategies": evaluated,
        "rejected_strategies": {k: v["reason"] for k, v in evaluated.items() if not v["valid"]},
        "feature_scores": {k: v.get("feature_scores") for k, v in evaluated.items()},
        "timestamp_evaluated": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("[AUDIT] BOT_STRATEGY_DECISION | %s | %s", symbol, json.dumps(audit_payload))

    if include_diagnostics:
        return {
            "signals": signals,
            "top_strategy": best_key,
            "top_confidence": selected_score,
            "evaluated_strategy_scores": audit_payload["evaluated_strategy_scores"],
            "evaluated_strategies": audit_payload["evaluated_strategies"],
            "rejected_strategies": audit_payload["rejected_strategies"],
            "feature_scores": audit_payload["feature_scores"],
            "timestamp_evaluated": audit_payload["timestamp_evaluated"],
        }

    return signals
