import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
from datetime import datetime, timezone

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


def _ema_value_at(ema_series: list[float], period: int, idx: int) -> Optional[float]:
    ema_idx = idx - (period - 1)
    if ema_idx < 0 or ema_idx >= len(ema_series):
        return None


def _extract_candle_features_from_primary(strategy_key: str, primary: list[dict]):
    """Build a synthetic signal from candles and return feature scores dict.

    This avoids depending on strategy.evaluate() to create a candidate — we
    derive normalized features directly from the primary timeframe candles
    and reuse existing compute_features_for_signal to ensure parity.
    """
    closes = _closes(primary)
    if not closes:
        # fallback neutral features
        class _S: pass
        s = _S()
        s.reasoning = {}
        s.regime = None
        s.entry_price = 0.0
        s.initial_stop = 0.0
        s.profit_target_1 = 0.0
        return compute_features_for_signal(strategy_key, s)

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    current = closes[-1]
    atr = _atr_from_history(primary)
    regime = _detect_regime(primary)

    reasoning = {}
    if ema20:
        reasoning["ema20"] = round(ema20[-1], 6)
        reasoning["current_vs_ema20"] = round(current - ema20[-1], 6)
    if ema50:
        reasoning["ema50"] = round(ema50[-1], 6)
    if atr:
        reasoning["atr"] = round(atr, 6)
    # best-effort simple breakout_pct using recent highs
    try:
        highs = _highs(primary)
        recent_high = max(highs[-20:-1]) if len(highs) >= 3 else highs[-1]
        reasoning["breakout_pct"] = round((current / max(recent_high, 1.0) - 1) * 100, 3)
    except Exception:
        pass

    class _FakeSig:
        pass

    s = _FakeSig()
    s.reasoning = reasoning
    s.regime = regime
    s.entry_price = current
    s.initial_stop = (min(_lows(primary)[-6:-1]) - atr * 0.3) if len(primary) >= 6 else current - atr * 0.5
    s.profit_target_1 = current + atr * 1.5
    return compute_features_for_signal(strategy_key, s)
    return ema_series[ema_idx]


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

# Scoring thresholds
MIN_SCORE_THRESHOLD = 0.35
STRONG_SIGNAL_THRESHOLD = 0.60


def _strategy_name_to_key(name: str) -> str | None:
    if "Pullback Reclaim" in name:
        return "pullback_reclaim"
    if "Trend Continuation" in name or "Momentum Breakout Continuation" in name:
        return "trend_continuation"
    if "Mean Reversion Bounce" in name:
        return "mean_reversion_bounce"
    if any(p in name for p in ("Opening Range Breakout", "Breakout Retest Hold", "Volatility Compression Breakout", "Range Rotation Reversal")):
        return "range_breakout"
    return None


def evaluate_all(
    symbol: str,
    candles: "list[dict] | dict[str, list]",
    ai_hint: dict | None = None,
    payload_meta: dict | None = None,
) -> list[StockEntrySignal]:
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

    # Candidate extraction using continuous scoring rather than boolean evaluate()
    signals = []
    for strategy in STOCK_ENTRY_STRATEGIES:
        primary = candles_by_tf.get(strategy.primary_tf, [])
        if len(primary) < 20:
            continue
        try:
            key = _strategy_name_to_key(strategy.name) or ""
            feature_scores = _extract_candle_features_from_primary(key, primary)
            base_score = score_strategy_from_candles(key, feature_scores)
            if base_score >= MIN_SCORE_THRESHOLD:
                # Build a simplified signal record compatible with downstream code
                try:
                    sig_obj = strategy.evaluate(symbol, primary)
                except Exception:
                    sig_obj = None
                candidate = StockEntrySignal(
                    strategy=strategy.name,
                    symbol=symbol,
                    entry_price=getattr(sig_obj, "entry_price", 0.0) if sig_obj else feature_scores.get("entry_price", 0.0),
                    initial_stop=getattr(sig_obj, "initial_stop", 0.0) if sig_obj else 0.0,
                    profit_target_1=getattr(sig_obj, "profit_target_1", 0.0) if sig_obj else 0.0,
                    profit_target_2=getattr(sig_obj, "profit_target_2", 0.0) if sig_obj else 0.0,
                    regime=getattr(sig_obj, "regime", None) if sig_obj else None,
                    confidence=max(getattr(sig_obj, "confidence", 0.0) if sig_obj else 0.0, base_score),
                    max_hold_hours=getattr(sig_obj, "max_hold_hours", 8) if sig_obj else 8,
                    notes=getattr(sig_obj, "notes", "") if sig_obj else "",
                    reasoning=getattr(sig_obj, "reasoning", {}) if sig_obj else {},
                )
                signals.append(candidate)
        except Exception as exc:
            logger.error("Stock strategy %s error for %s: %s", strategy.name, symbol, exc)
    signals.sort(key=lambda s: s.confidence, reverse=True)

    # Build evaluated strategies map for required supported keys
    key_map = {
        "pullback_reclaim": ["Pullback Reclaim"],
        "trend_continuation": ["Trend Continuation", "Trend Continuation Ladder", "Momentum Breakout Continuation"],
        "mean_reversion_bounce": ["Mean Reversion Bounce"],
        "range_breakout": ["Opening Range Breakout", "Breakout Retest Hold", "Volatility Compression Breakout", "Range Rotation Reversal"],
    }

    evaluated: dict[str, dict] = {}
    rejected: dict[str, str] = {}

    for key, name_patterns in key_map.items():
        matched = None
        for s in signals:
            for pat in name_patterns:
                if pat in s.strategy:
                    if matched is None or s.confidence > matched.confidence:
                        matched = s
        if matched:
            # Compute feature-based scores from the actual signal reasoning
            feature_scores = compute_features_for_signal(key, matched, asset_class="stock")
            base_score = compute_strategy_score(key, feature_scores, regime=matched.regime if hasattr(matched, "regime") else None, asset_class="stock")
            bias = compute_hint_bias(ai_hint, key) if ai_hint else 0.0
            # Only apply bias to already-valid signals (do not rescue invalid setups)
            final_score = base_score + bias
            if final_score > 1.0:
                final_score = 1.0
            evaluated[key] = {
                "valid": True,
                "base_score": round(base_score, 6),
                "bias": round(bias, 6),
                "final_score": round(final_score, 6),
                "reason": None,
                "feature_scores": {k: round(v, 6) for k, v in feature_scores.items()},
            }
        else:
            # Differentiate reasons: if we had no candidate signals at all,
            # report that; otherwise indicate no matching signal for this key.
            reason = "no candidate signals" if not signals else "no matching signal"
            evaluated[key] = {
                "valid": False,
                "base_score": 0.0,
                "bias": 0.0,
                "final_score": 0.0,
                "reason": reason,
            }

    # Select best valid strategy deterministically
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
        bias_applied = evaluated[best_key]["bias"] > 0.0
        bias_amount = evaluated[best_key]["bias"]

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

    # Emit structured audit event via logs (and root logger for tests)
    # Debug info: candidate count, raw evaluated map, and selected strategy
    try:
        logger.debug("BOT_STRATEGY_DECISION debug | %s | candidate_signals=%d", symbol, len(signals))
        logger.debug("BOT_STRATEGY_DECISION debug | %s | evaluated_raw=%s", symbol, json.dumps(evaluated))
        logger.debug("BOT_STRATEGY_DECISION debug | %s | selected_strategy=%s", symbol, decision.selected_strategy)
    except Exception:
        # keep audit emission robust even if debugging serialization fails
        pass
    # Additional candle frame debug when available via payload_meta.store
    try:
        if payload_meta and payload_meta.get("store"):
            store = payload_meta.get("store")
            tf_info = {}
            for tf in ("1m", "5m", "15m", "1H", "4H", "daily"):
                try:
                    iv = {"1m":1, "5m":5, "15m":15, "1H":60, "4H":240, "daily":1440}[tf]
                    tf_info[tf] = store.frame_info(symbol, iv)
                except Exception:
                    tf_info[tf] = {"error": "frame_info failed"}
            logger.debug("BOT_STRATEGY_DECISION debug | %s | candle_frames=%s", symbol, json.dumps(tf_info))
    except Exception:
        pass

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
        # Preserve backward-compatible final-score map
        "evaluated_strategy_scores": decision.evaluated_strategies,
        # Provide full evaluated strategy map with detailed per-strategy fields
        "evaluated_strategies": evaluated,
        "rejected_strategies": {k: v["reason"] for k, v in evaluated.items() if not v["valid"]},
        "feature_scores": {k: v.get("feature_scores") for k, v in evaluated.items()},
        "timestamp_received": payload_meta.get("timestamp") if payload_meta else None,
        "timestamp_evaluated": datetime.now(timezone.utc).isoformat(),
    }
    # Single emission through module logger to avoid duplicate audit lines
    logger.info("[AUDIT] BOT_STRATEGY_DECISION | %s | %s", symbol, json.dumps(audit_payload))

    # Persist BotStrategyDecision row asynchronously if DB available
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
                    decision_context={
                        "payload_meta": payload_meta,
                    },
                )
                db.add(row)
                await db.commit()
        except Exception:
            logger.exception("Failed to persist BotStrategyDecision for %s", symbol)

    try:
        import asyncio

        asyncio.create_task(_persist_decision())
    except Exception:
        # If event loop not running (tests), run synchronously
        import asyncio

        try:
            asyncio.run(_persist_decision())
        except Exception:
            logger.exception("Failed to persist BotStrategyDecision synchronously for %s", symbol)

    return signals
