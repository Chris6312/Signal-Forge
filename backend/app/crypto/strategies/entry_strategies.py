import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from app.common.watchlist_schema_v4 import score_strategy_from_candles, compute_hint_bias, BotDecision, WEIGHTS, compute_features_for_signal, compute_strategy_score
import json

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
    reasoning: dict = field(default_factory=dict)


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
MIN_SCORE_THRESHOLD = 0.35
STRONG_SIGNAL_THRESHOLD = 0.60


def _strategy_name_to_key(name: str) -> str | None:
    if "Pullback Reclaim" in name:
        return "pullback_reclaim"
    if "Momentum Breakout Continuation" in name:
        return "trend_continuation"
    if "Mean Reversion Bounce" in name:
        return "mean_reversion_bounce"
    if any(p in name for p in ("Range Rotation Reversal", "Breakout Retest Hold")):
        return "range_breakout"
    return None


def evaluate_all(symbol, candles_by_tf):
    if isinstance(candles_by_tf, list):
        candles_by_tf = {
            "15m": candles_by_tf,
            "1H": candles_by_tf,
            "4H": candles_by_tf,
            "daily": candles_by_tf,
        }
    signals = []
    for strat in ENTRY_STRATEGIES:
        ohlcv = candles_by_tf.get(strat.primary_tf, [])
        if len(ohlcv) < 20:
            continue
        try:
            key = _strategy_name_to_key(strat.name) or ""
            feature_scores = compute_features_for_signal(key, strat.evaluate(symbol, ohlcv) or None)
            base_score = score_strategy_from_candles(key, feature_scores)
            if base_score >= MIN_SCORE_THRESHOLD:
                try:
                    sig = strat.evaluate(symbol, ohlcv)
                except Exception:
                    sig = None
                if sig:
                    signals.append(sig)
                else:
                    # Build a minimal EntrySignal from features
                    s = EntrySignal(
                        strategy=strat.name,
                        symbol=symbol,
                        entry_price=0.0,
                        initial_stop=0.0,
                        profit_target_1=0.0,
                        profit_target_2=0.0,
                        regime=None,
                        confidence=base_score,
                    )
                    signals.append(s)
        except Exception as e:
            logger.error("Strategy %s failed for %s: %s", strat.name, symbol, e)
    signals.sort(key=lambda s: s.confidence, reverse=True)
    # Build evaluated strategies and apply hint bias if provided under payload_meta
    # Note: this function keeps original signature to avoid widespread changes;
    # consumers can pass ai_hint and payload_meta in the future by wrapping.

    # For parity with stocks, build a simplified evaluated map
    key_map = {
        "pullback_reclaim": ["Pullback Reclaim"],
        "trend_continuation": ["Momentum Breakout Continuation"],
        "mean_reversion_bounce": ["Mean Reversion Bounce"],
        "range_breakout": ["Range Rotation Reversal", "Breakout Retest Hold"],
    }

    evaluated = {}
    for key, patterns in key_map.items():
        matched = None
        for s in signals:
            for pat in patterns:
                if pat in s.strategy:
                    if matched is None or s.confidence > matched.confidence:
                        matched = s
        if matched:
            # derive features from matched signal when possible
            feature_scores = compute_features_for_signal(key, matched, asset_class="crypto")
            base_score = compute_strategy_score(key, feature_scores, regime=matched.regime if hasattr(matched, "regime") else None, asset_class="crypto")
            # No ai_hint passed into this function currently — bias 0.0
            bias = 0.0
            final_score = min(1.0, base_score + bias)
            evaluated[key] = {
                "valid": True,
                "base_score": round(base_score, 6),
                "bias": round(bias, 6),
                "final_score": round(final_score, 6),
                "reason": None,
            }
        else:
            reason = "no candidate signals" if not signals else "no matching signal"
            evaluated[key] = {
                "valid": False,
                "base_score": 0.0,
                "bias": 0.0,
                "final_score": 0.0,
                "reason": reason,
            }

    # Emit audit with evaluated strategy scores — AI hint not wired here yet
    # Debug: log candidate count and evaluated map before emission
    try:
        logger.debug("BOT_STRATEGY_DECISION debug | %s | candidate_signals=%d", symbol, len(signals))
        logger.debug("BOT_STRATEGY_DECISION debug | %s | evaluated_raw=%s", symbol, json.dumps(evaluated))
    except Exception:
        pass

    audit_payload = {
        "symbol": symbol,
        "asset_class": "crypto",
        "evaluated_strategy_scores": {k: v["final_score"] for k, v in evaluated.items()},
        "evaluated_strategies": evaluated,
        "rejected_strategies": {k: v["reason"] for k, v in evaluated.items() if not v["valid"]},
        "timestamp_evaluated": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("[AUDIT] BOT_STRATEGY_DECISION | %s | %s", symbol, json.dumps(audit_payload))

    return signals
