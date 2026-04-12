"""Schema handling and scoring for bot_watchlist_v4 Discord payloads.

Implements a small scoring matrix, safe AI hint biasing, and audit payload
builders while keeping the bot as the source of truth for candle-derived
strategy selection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime, timezone

# Centralized weights for scoring components (bounded and explicit)
WEIGHTS = {
    "structure": 0.25,
    "trend_alignment": 0.20,
    "momentum": 0.15,
    "reclaim_or_breakout": 0.15,
    "volume": 0.10,
    "risk_reward": 0.10,
    "regime_fit": 0.05,
}

# Hint bias config
HINT_BIAS = {
    "bias_multiplier": 0.05,
    "max_bias": 0.03,
    "enabled": True,
}


@dataclass
class BotDecision:
    selected_strategy: Optional[str]
    selected_score: float
    evaluated_strategies: Dict[str, float]
    ai_hint_strategy: Optional[str]
    ai_hint_confidence: Optional[float]
    ai_hint_agreement: Optional[bool]
    ai_hint_bias_applied: bool
    ai_hint_bias_amount: float
    feature_scores: Optional[Dict[str, Dict[str, float]]] = None


def normalize_payload(payload: dict) -> dict:
    # Backward-compatibility: if schema_version missing, mark as legacy
    out = dict(payload)
    if "schema_version" not in out:
        out["schema_version"] = "legacy"
    return out


def validate_symbol_entry(item: dict) -> Optional[str]:
    # Minimal validation rules per requirements
    if "symbol" not in item:
        return "missing symbol"
    if "asset_class" not in item:
        return "missing asset_class"
    ac = item.get("asset_class")
    if ac not in ("stock", "crypto"):
        return f"unsupported asset_class: {ac}"
    if ac == "crypto":
        s = item.get("symbol")
        if "/" not in s:
            return "crypto symbol must be in BASE/QUOTE format like BTC/USD"
    if "ai_hint" in item and isinstance(item.get("ai_hint"), dict):
        strat = item["ai_hint"].get("suggested_strategy")
        supported_strategies = {
            "pullback_reclaim",
            "trend_continuation",
            "mean_reversion_bounce",
            "range_breakout",
            "range_rotation",
            "breakout_retest",
            "opening_range_breakout",
            "volatility_compression_breakout",
            "failed_breakdown_reclaim",
        }
        if strat and strat not in supported_strategies:
            return f"unsupported ai_hint.suggested_strategy: {strat}"
        conf = item["ai_hint"].get("confidence")
        if conf is not None and not (0.0 <= float(conf) <= 1.0):
            return "ai_hint.confidence must be between 0.0 and 1.0"
    return None


def compute_hint_bias(ai_hint: Optional[dict], current_strategy: str) -> float:
    if not HINT_BIAS["enabled"] or not ai_hint:
        return 0.0
    suggested = ai_hint.get("suggested_strategy")
    if suggested != current_strategy:
        return 0.0
    conf = float(ai_hint.get("confidence") or 0.0)
    bias = min(HINT_BIAS["max_bias"], conf * HINT_BIAS["bias_multiplier"])
    return bias


def clamp01(v: float) -> float:
    try:
        f = float(v)
    except Exception:
        return 0.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def _structure_score_from_reasoning(reasoning: dict) -> float:
    # Graded MA stacking score with fallbacks to older heuristics
    if not reasoning:
        return 0.5

    score = 0.0
    # Preferred stacking weights (sum to 1.0)
    w9_20 = 0.33
    w20_50 = 0.33
    w50_200 = 0.34

    has_any = False
    # ema9 > ema20
    if reasoning.get("ema9") is not None and reasoning.get("ema20") is not None:
        has_any = True
        if reasoning["ema9"] > reasoning["ema20"]:
            score += w9_20
    # ema20 > ema50
    if reasoning.get("ema20") is not None and reasoning.get("ema50") is not None:
        has_any = True
        if reasoning["ema20"] > reasoning["ema50"]:
            score += w20_50
    # ema50 > ema200
    if reasoning.get("ema50") is not None and reasoning.get("ema200") is not None:
        has_any = True
        if reasoning["ema50"] > reasoning["ema200"]:
            score += w50_200

    if has_any:
        return clamp01(score)

    # Fallback to previously used heuristic when EMA components not present
    score = 0.5
    if reasoning.get("higher_highs_confirmed") or reasoning.get("higher_lows_confirmed"):
        score += 0.3
    if reasoning.get("dip_below_ema_confirmed") or reasoning.get("reclaim_confirmed"):
        score += 0.15
    # small penalty for compression indicators that imply noise
    if reasoning.get("compression_ratio") and reasoning.get("compression_ratio") > 0.8:
        score -= 0.1
    return clamp01(score)


def _trend_alignment_score_from_regime(regime: Optional[str]) -> float:
    if not regime:
        return 0.5
    if regime == "trending_up":
        return 1.0
    if regime == "ranging":
        return 0.5
    if regime == "trending_down":
        return 0.0
    return 0.5


def _momentum_score_from_reasoning(reasoning: dict) -> float:
    # Use price-normalized EMA slope where possible to avoid ATR scaling collapse
    if not reasoning:
        return 0.4
    score = 0.4

    # Determine a close price to normalize against
    close = None
    # Many callers provide current close under "close" or "entry_price" in the signal reasoning
    if reasoning.get("close") is not None:
        try:
            close = float(reasoning.get("close"))
        except Exception:
            close = None

    # Favor EMA20 slope normalized by price: (ema20_now - ema20_past) / close
    # If only current_vs_ema20 is present, use it as a proxy normalized by price
    if reasoning.get("current_vs_ema20") is not None:
        try:
            diff = float(reasoning.get("current_vs_ema20"))
            denom = max(1.0, abs(close or reasoning.get("ema20") or 1.0))
            norm = diff / denom
            # scale to similar effect as prior multiplier but price-normalized
            score += min(0.4, max(-0.4, norm * 5.0))
        except Exception:
            pass

    # Small boost if higher closes explicitly confirmed
    if reasoning.get("higher_closes_confirmed"):
        score += 0.1

    # Price-location relative to EMA20 and ATR to help differentiate reclaim vs continuation
    try:
        if reasoning.get("ema20") is not None and reasoning.get("atr") is not None and (close is not None):
            atr = float(reasoning.get("atr") or 0.0)
            if atr and atr > 0:
                price_loc = (close - float(reasoning.get("ema20"))) / atr
                # clamp to -1..1 and add a small influence
                price_loc_clamped = max(-1.0, min(1.0, price_loc))
                score += price_loc_clamped * 0.05
    except Exception:
        pass

    return clamp01(score)


def _volume_confirmation_from_reasoning(reasoning: dict, asset_class: str = "stock") -> float:
    # Many stock signals include no volume in this pipeline; be conservative
    if not reasoning:
        return 0.5
    # If explicit bars_in_session present, treat as mild confirmation
    if reasoning.get("bars_in_session") and reasoning.get("breakout_pct"):
        return 0.7
    return 0.5


def _risk_reward_from_signal(signal) -> float:
    # signal is optionally a dataclass with entry_price, initial_stop, profit_target_1
    try:
        entry = float(getattr(signal, "entry_price", 0.0))
        stop = float(getattr(signal, "initial_stop", 0.0))
        tp = float(getattr(signal, "profit_target_1", 0.0))
    except Exception:
        return 0.5
    if stop <= 0 or entry <= 0:
        return 0.0
    risk = max(1e-6, entry - stop)
    reward = max(0.0, tp - entry)
    if reward <= 0:
        return 0.0
    rr = reward / risk
    # normalize rr into 0..1 range where 1 represents rr>=3
    return clamp01(min(1.0, rr / 3.0))


def _regime_fit_from_regime_and_strategy(regime: str | None, strategy_key: str) -> float:
    regime = (regime or "unknown").lower().strip()
    strategy_key = (strategy_key or "").lower().strip()

    # Uptrend-friendly strategies
    if strategy_key == "trend_continuation":
        if regime == "trending_up":
            return 1.0
        if regime == "ranging":
            return 0.35
        if regime == "trending_down":
            return 0.05
        return 0.20

    if strategy_key == "breakout_retest":
        if regime == "trending_up":
            return 0.80
        if regime == "ranging":
            return 0.45
        if regime == "trending_down":
            return 0.05
        return 0.20

    if strategy_key == "opening_range_breakout":
        if regime == "trending_up":
            return 1.0
        if regime == "ranging":
            return 0.40
        if regime == "trending_down":
            return 0.05
        return 0.20

    if strategy_key == "volatility_compression_breakout":
        if regime == "trending_up":
            return 0.95
        if regime == "ranging":
            return 0.35
        if regime == "trending_down":
            return 0.05
        return 0.20

    if strategy_key == "failed_breakdown_reclaim":
        if regime == "trending_down":
            return 0.90
        if regime == "ranging":
            return 0.70
        if regime == "trending_up":
            return 0.15
        return 0.30

    # Pullback / reclaim longs work best in healthy uptrends,
    # but can still function somewhat in ranges.
    if strategy_key == "pullback_reclaim":
        if regime == "trending_up":
            return 0.9
        if regime == "ranging":
            return 0.4
        if regime == "trending_down":
            return 0.05
        return 0.25

    # Mean reversion prefers range / neutral conditions.
    if strategy_key == "mean_reversion_bounce":
        if regime == "ranging":
            return 1.0
        if regime == "unknown":
            return 0.35
        if regime == "trending_up":
            return 0.1
        if regime == "trending_down":
            return 0.1
        return 0.2

    # Range rotation should prefer actual ranges, not intact uptrends.
    if strategy_key == "range_rotation":
        if regime == "ranging":
            return 1.0
        if regime == "unknown":
            return 0.35
        if regime == "trending_up":
            return 0.15
        if regime == "trending_down":
            return 0.1
        return 0.2

    # Backward compatibility with any older bucket name still present.
    if strategy_key == "range_breakout":
        if regime == "trending_up":
            return 0.7
        if regime == "ranging":
            return 0.45
        if regime == "trending_down":
            return 0.1
        return 0.25

    # Safe fallback
    if regime == "trending_up":
        return 0.5
    if regime == "ranging":
        return 0.5
    if regime == "trending_down":
        return 0.1
    return 0.2

def compute_features_for_signal(strategy_key: str, signal, asset_class: str = "stock") -> dict:
    """Return normalized component scores for a strategy signal.

    Expected signal schema:
      - strategy: human-readable strategy name
      - symbol: symbol string
      - entry_price: latest close / trigger price
      - initial_stop: stop price
      - profit_target_1: first target
      - regime: market regime string
      - reasoning: dict with optional fields such as:
          close, atr, ema9, ema20, ema50, ema200,
          ema20_past, ema20_history, breakout_pct, volume_ratio,
          higher_highs_confirmed, higher_lows_confirmed, higher_closes_confirmed,
          dip_below_ema_confirmed, reclaim_confirmed, price_in_retest_band,
          three_ascending_closes, trigger_type, setup_quality, timeframe.
    """
    reasoning = getattr(signal, "reasoning", {}) or {}
    regime = getattr(signal, "regime", None)

    def _float(value, default=None):
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    close = _float(getattr(signal, "entry_price", None), None)
    if close in (None, 0.0):
        close = _float(reasoning.get("close") or reasoning.get("entry_price"), None)

    ema9 = _float(reasoning.get("ema9"), None)
    ema20 = _float(reasoning.get("ema20"), None)
    ema50 = _float(reasoning.get("ema50"), None)
    ema200 = _float(reasoning.get("ema200"), None)
    atr = _float(reasoning.get("atr"), None)

    higher_highs = bool(reasoning.get("higher_highs_confirmed"))
    higher_lows = bool(reasoning.get("higher_lows_confirmed"))
    higher_closes = bool(reasoning.get("higher_closes_confirmed"))
    ascending_closes = bool(reasoning.get("three_ascending_closes"))
    dip_below_ema = bool(reasoning.get("dip_below_ema_confirmed"))
    reclaim_confirmed = bool(reasoning.get("reclaim_confirmed"))
    price_in_retest_band = bool(reasoning.get("price_in_retest_band"))
    bounce_confirmed = bool(reasoning.get("bounce_confirmed"))

    stack_score = 0.0
    stack_pairs = 0
    for a, b, weight in ((ema9, ema20, 0.34), (ema20, ema50, 0.33), (ema50, ema200, 0.33)):
        if a is None or b is None:
            continue
        stack_pairs += 1
        if a > b:
            stack_score += weight

    structure = stack_score if stack_pairs else _structure_score_from_reasoning(reasoning)
    if higher_highs:
        structure += 0.12
    if higher_lows:
        structure += 0.12
    if higher_closes:
        structure += 0.08
    if ascending_closes:
        structure += 0.08
    if dip_below_ema or reclaim_confirmed:
        structure += 0.05
    structure = clamp01(structure)

    trend_alignment = 0.0
    if regime == "trending_up":
        trend_alignment += 0.40
    elif regime == "ranging":
        trend_alignment += 0.15
    elif regime == "unknown":
        trend_alignment += 0.10

    if close is not None:
        if ema20 is not None and close >= ema20:
            trend_alignment += 0.25
        if ema50 is not None and close >= ema50:
            trend_alignment += 0.20
        if ema200 is not None and close >= ema200:
            trend_alignment += 0.15
    if ema20 is not None and ema50 is not None and close:
        trend_alignment += min(0.15, abs(ema20 - ema50) / max(abs(close), 1.0) * 8.0)
    trend_alignment = clamp01(trend_alignment)

    momentum = 0.0
    ema20_past = _float(reasoning.get("ema20_past"), None)
    if ema20 is not None and ema20_past is not None and close:
        momentum += clamp01(((ema20 - ema20_past) / max(abs(close), 1.0)) * 24.0)
    elif reasoning.get("ema20_history") and close:
        hist = reasoning.get("ema20_history")
        if isinstance(hist, (list, tuple)) and len(hist) >= 5:
            try:
                momentum += clamp01(((float(hist[-1]) - float(hist[-5])) / max(abs(close), 1.0)) * 24.0)
            except Exception:
                pass

    current_vs_ema20 = _float(reasoning.get("current_vs_ema20"), None)
    if current_vs_ema20 is not None and close:
        momentum += clamp01((current_vs_ema20 / max(abs(close), 1.0)) * 18.0)

    breakout_pct = _float(reasoning.get("breakout_pct"), None)
    positive_breakout = max(0.0, breakout_pct or 0.0)
    negative_breakout = max(0.0, -(breakout_pct or 0.0))
    if breakout_pct is not None:
        momentum += clamp01(positive_breakout / 2.0) * 0.35
        if negative_breakout > 0:
            momentum -= clamp01(negative_breakout / 2.5) * 0.10

    if higher_closes:
        momentum += 0.10
    if ascending_closes:
        momentum += 0.10
    momentum = clamp01(momentum)

    reclaim_or_breakout = 0.0
    trigger_type = str(reasoning.get("trigger_type") or "").lower()
    is_breakout_family = trigger_type in {"breakout", "continuation"}

    if is_breakout_family:
        reclaim_or_breakout += 0.35
    if trigger_type in {"reclaim", "pullback", "failed_breakdown_reclaim"}:
        reclaim_or_breakout += 0.35
    if trigger_type in {"mean_reversion", "range_reversal"}:
        reclaim_or_breakout += 0.25

    if breakout_pct is not None:
        reclaim_or_breakout += clamp01(positive_breakout / 1.5) * 0.35
        if negative_breakout > 0 and is_breakout_family:
            reclaim_or_breakout -= clamp01(negative_breakout / 2.0) * 0.12

    if dip_below_ema:
        reclaim_or_breakout += 0.20
    if reclaim_confirmed:
        reclaim_or_breakout += 0.20
    if price_in_retest_band:
        reclaim_or_breakout += 0.15
    if bounce_confirmed:
        reclaim_or_breakout += 0.15
    reclaim_or_breakout = clamp01(reclaim_or_breakout)

    volume = 0.5
    volume_ratio = _float(reasoning.get("volume_ratio"), None)
    if volume_ratio is not None:
        volume = clamp01((volume_ratio - 0.8) / 1.2)
    elif reasoning.get("bars_in_session") and breakout_pct:
        volume = 0.70
    elif reasoning.get("volume_expansion"):
        volume = clamp01(_float(reasoning.get("volume_expansion"), 0.5))

    risk_reward = _risk_reward_from_signal(signal)
    if risk_reward == 0.0 and atr and close:
        fallback_stop = _float(reasoning.get("fallback_stop"), None)
        fallback_tp = _float(reasoning.get("fallback_tp1"), None)
        if fallback_stop is not None and fallback_tp is not None:
            class _Tmp:
                pass

            tmp = _Tmp()
            tmp.entry_price = close
            tmp.initial_stop = fallback_stop
            tmp.profit_target_1 = fallback_tp
            risk_reward = _risk_reward_from_signal(tmp)

    # Trend persistence guardrail:
    # strong trends should not be mistaken for rotation just because
    # momentum is cooling or candles are compressing near highs.
    trend_stack_strong = bool(
        ema20 is not None
        and ema50 is not None
        and ema20 > ema50
        and (
            ema200 is None
            or ema50 > ema200
        )
    )
    price_above_trend_base = bool(
        close is not None
        and ema20 is not None
        and close >= ema20
        and (
            ema50 is None
            or close >= ema50
        )
    )
    trend_persistence = bool(
        regime == "trending_up"
        and trend_stack_strong
        and price_above_trend_base
        and higher_lows
    )
    strong_trend_persistence = bool(
        trend_persistence
        and higher_highs
        and trend_alignment >= 0.72
    )

    maturity_penalty = 0.0
    if close is not None and atr and atr > 0 and ema20 is not None:
        extension_atr = max(0.0, (close - ema20) / atr)
        maturity_penalty += clamp01((extension_atr - 1.0) / 2.5) * 0.40

    if is_breakout_family:
        if not higher_highs:
            maturity_penalty += 0.08
        if not higher_closes:
            maturity_penalty += 0.08
        if not ascending_closes:
            maturity_penalty += 0.06
        if price_in_retest_band and positive_breakout < 0.2:
            maturity_penalty += 0.06
        if regime != "trending_up":
            maturity_penalty += 0.05
    elif strategy_key == "pullback_reclaim":
        if close is not None and atr and atr > 0 and ema20 is not None and close > ema20:
            maturity_penalty += clamp01(((close - ema20) / atr - 1.5) / 2.0) * 0.15

    if breakout_pct is not None and positive_breakout < 0.1 and negative_breakout == 0 and is_breakout_family:
        maturity_penalty += 0.04

    # New micro-adjustment:
    # when the trend is obviously still intact, suppress reversal/range behavior a bit.
    # This keeps BTC/ETH/HYPE/ZEC from drifting into rotation labels during healthy pauses.
    if strong_trend_persistence:
        if strategy_key == "mean_reversion_bounce":
            maturity_penalty += 0.16
        elif strategy_key == "range_breakout":
            # only dampen the range bucket when it lacks real breakout/retest evidence
            if positive_breakout < 0.75 and not price_in_retest_band:
                maturity_penalty += 0.14
            if not dip_below_ema and not bounce_confirmed and not reclaim_confirmed:
                maturity_penalty += 0.10
        elif strategy_key == "pullback_reclaim":
            # keep pullback reclaim competitive in healthy trends, but soften it
            # slightly when there was no actual reclaim event.
            if not dip_below_ema and not reclaim_confirmed:
                maturity_penalty += 0.05

    maturity_penalty = clamp01(maturity_penalty)

    prior_high_40 = _float(reasoning.get("prior_high_40"), None)
    breakout_high_10 = _float(reasoning.get("breakout_high_10"), None)
    retest_low = _float(reasoning.get("retest_low"), None)
    range_low_30 = _float(reasoning.get("range_low_30"), None)
    range_high_30 = _float(reasoning.get("range_high_30"), None)
    distance_from_low_pct = _float(reasoning.get("distance_from_low_pct"), None)
    opening_range_high = _float(reasoning.get("opening_range_high"), None)
    recent_atr_5 = _float(reasoning.get("recent_atr_5"), None)
    prior_atr_14 = _float(reasoning.get("prior_atr_14"), None)

    breakout_strength = 0.0
    if breakout_pct is not None:
        breakout_strength = clamp01(max(0.0, breakout_pct) / 2.0)
    if prior_high_40 is not None and breakout_high_10 is not None:
        breakout_strength = max(
            breakout_strength,
            clamp01(max(0.0, (breakout_high_10 - prior_high_40) / max(abs(prior_high_40), 1.0)) * 40.0),
        )

    breakout_retest_quality = 0.0
    if prior_high_40 is not None and retest_low is not None:
        retest_distance_pct = abs(retest_low - prior_high_40) / max(abs(prior_high_40), 1.0) * 100.0
        breakout_retest_quality = clamp01(1.0 - (retest_distance_pct / 2.0))
        if not price_in_retest_band:
            breakout_retest_quality *= 0.35

    near_range_low_score = 0.0
    if distance_from_low_pct is not None:
        near_range_low_score = clamp01((35.0 - max(distance_from_low_pct, 0.0)) / 35.0)
    elif range_low_30 is not None and close is not None and range_high_30 is not None:
        width = max(range_high_30 - range_low_30, 1e-6)
        near_range_low_score = clamp01(1.0 - ((close - range_low_30) / width))

    compression_quality = 0.0
    if recent_atr_5 is not None and prior_atr_14 is not None and prior_atr_14 > 0:
        compression_quality = clamp01((0.60 - (recent_atr_5 / prior_atr_14)) / 0.60)

    if strategy_key == "trend_continuation":
        reclaim_or_breakout = clamp01(
            (0.30 if higher_highs else 0.0)
            + (0.30 if higher_lows else 0.0)
            + (0.18 if higher_closes else 0.0)
            + (0.12 if ascending_closes else 0.0)
            + (0.10 if close is not None and ema20 is not None and close >= ema20 else 0.0)
        )
        if price_in_retest_band:
            reclaim_or_breakout *= 0.92

    elif strategy_key == "breakout_retest":
        structure = clamp01(structure * 0.90 + breakout_retest_quality * 0.10)
        reclaim_or_breakout = clamp01(0.18 + breakout_strength * 0.32 + breakout_retest_quality * 0.35 + (0.15 if price_in_retest_band else 0.0))
        if not price_in_retest_band:
            structure *= 0.88
            trend_alignment *= 0.92
            risk_reward *= 0.92
            maturity_penalty = clamp01(maturity_penalty + 0.06)

    elif strategy_key == "range_rotation":
        structure = clamp01(structure * 0.55 + near_range_low_score * 0.25 + (0.20 if ascending_closes else 0.0))
        trend_alignment = clamp01(trend_alignment * 0.45)
        momentum = clamp01(momentum * 0.35 + (0.20 if ascending_closes else 0.0) + (0.15 if bounce_confirmed else 0.0))
        reclaim_or_breakout = clamp01(near_range_low_score * 0.55 + (0.20 if ascending_closes else 0.0) + (0.15 if bounce_confirmed else 0.0) + (0.10 if regime == "ranging" else 0.0))
        if strong_trend_persistence:
            structure *= 0.60
            momentum *= 0.45
            reclaim_or_breakout *= 0.35
            risk_reward *= 0.80
        if regime != "ranging":
            structure *= 0.75
            reclaim_or_breakout *= 0.60
        if breakout_strength > 0.35:
            reclaim_or_breakout *= 0.65
            maturity_penalty = clamp01(maturity_penalty + 0.05)

    elif strategy_key == "opening_range_breakout":
        breakout_gate = 0.0
        if opening_range_high is not None and close is not None:
            breakout_gate = clamp01(max(0.0, (close - opening_range_high) / max(abs(close), 1.0)) * 60.0)
        reclaim_or_breakout = clamp01(0.18 + breakout_strength * 0.40 + breakout_gate * 0.25 + (0.12 if volume > 0.55 else 0.0))

    elif strategy_key == "volatility_compression_breakout":
        reclaim_or_breakout = clamp01(0.15 + breakout_strength * 0.28 + compression_quality * 0.32 + (0.10 if volume > 0.50 else 0.0))
        momentum = clamp01(momentum * 0.85 + compression_quality * 0.15)

    elif strategy_key == "failed_breakdown_reclaim":
        reclaim_or_breakout = clamp01(0.20 + (0.25 if reclaim_confirmed else 0.0) + (0.20 if bounce_confirmed else 0.0) + (0.15 if ascending_closes else 0.0) + risk_reward * 0.20)

    features = {
        "structure": structure,
        "trend_alignment": trend_alignment,
        "momentum": momentum,
        "reclaim_or_breakout": reclaim_or_breakout,
        "volume": clamp01(volume),
        "risk_reward": clamp01(risk_reward),
        "regime_fit": _regime_fit_from_regime_and_strategy(regime, strategy_key),
        "trend_maturity_penalty": maturity_penalty,
        "_diagnostics": {
            "price_location": round(
                clamp01(((current_vs_ema20 or 0.0) / max(atr or 1.0, 1e-6)) * 0.5 + 0.5),
                6,
            ) if atr else 0.5,
            "volatility_context": round(
                clamp01(1.0 - ((atr or 0.0) / max(abs(close or 1.0), 1.0))),
                6,
            ),
            "signal_schema_version": reasoning.get("signal_schema_version", "v2"),
            "trigger_type": trigger_type or None,
            "trend_persistence": trend_persistence,
            "strong_trend_persistence": strong_trend_persistence,
            "raw_signal_present": bool(reasoning.get("raw_signal_present", False)),
            "price_in_retest_band": price_in_retest_band,
            "breakout_strength": breakout_strength,
            "breakout_retest_quality": breakout_retest_quality,
            "near_range_low_score": near_range_low_score,
            "compression_quality": compression_quality,
        },
    }
    return {k: clamp01(v) if k != "_diagnostics" else v for k, v in features.items()}

CRYPTO_STRATEGY_WEIGHTS = {
    "pullback_reclaim": {
        "structure": 0.22,
        "trend": 0.28,
        "momentum": 0.07,
        "trigger": 0.20,
        "volume": 0.06,
        "risk_reward": 0.05,
        "maturity": 0.12,
    },
    "trend_continuation": {
        "structure": 0.08,
        "trend": 0.24,
        "momentum": 0.32,
        "trigger": 0.08,
        "volume": 0.18,
        "risk_reward": 0.03,
        "maturity": 0.07,
    },
    "breakout_retest": {
        "structure": 0.24,
        "trend": 0.14,
        "momentum": 0.05,
        "trigger": 0.24,
        "volume": 0.15,
        "risk_reward": 0.10,
        "maturity": 0.08,
    },
    "mean_reversion_bounce": {
        "structure": 0.33,
        "trend": 0.04,
        "momentum": 0.24,
        "trigger": 0.12,
        "volume": 0.04,
        "risk_reward": 0.13,
        "maturity": 0.10,
    },
    "range_rotation": {
        "structure": 0.20,
        "trend": 0.02,
        "momentum": 0.08,
        "trigger": 0.24,
        "volume": 0.03,
        "risk_reward": 0.28,
        "maturity": 0.05,
    },
}

STOCK_STRATEGY_WEIGHTS = {
    "pullback_reclaim": {
        "structure": 0.22,
        "trend": 0.28,
        "momentum": 0.07,
        "trigger": 0.20,
        "volume": 0.05,
        "risk_reward": 0.05,
        "maturity": 0.13,
    },
    "failed_breakdown_reclaim": {
        "structure": 0.24,
        "trend": 0.05,
        "momentum": 0.16,
        "trigger": 0.21,
        "volume": 0.05,
        "risk_reward": 0.19,
        "maturity": 0.10,
    },
    "trend_continuation": {
        "structure": 0.10,
        "trend": 0.24,
        "momentum": 0.28,
        "trigger": 0.09,
        "volume": 0.17,
        "risk_reward": 0.04,
        "maturity": 0.08,
    },
    "mean_reversion_bounce": {
        "structure": 0.34,
        "trend": 0.04,
        "momentum": 0.24,
        "trigger": 0.11,
        "volume": 0.05,
        "risk_reward": 0.12,
        "maturity": 0.10,
    },
    "opening_range_breakout": {
        "structure": 0.15,
        "trend": 0.18,
        "momentum": 0.20,
        "trigger": 0.22,
        "volume": 0.15,
        "risk_reward": 0.05,
        "maturity": 0.05,
    },
    "volatility_compression_breakout": {
        "structure": 0.18,
        "trend": 0.18,
        "momentum": 0.17,
        "trigger": 0.20,
        "volume": 0.15,
        "risk_reward": 0.07,
        "maturity": 0.05,
    },
}


def _strategy_weight_matrix(strategy_key: str, asset_class: str) -> dict[str, float]:
    if asset_class == "crypto":
        return dict(CRYPTO_STRATEGY_WEIGHTS.get(strategy_key, WEIGHTS))
    return dict(STOCK_STRATEGY_WEIGHTS.get(strategy_key, WEIGHTS))


def _feature_component_map(features: dict) -> dict[str, float]:
    return {
        "structure": clamp01(float(features.get("structure", 0.0) or 0.0)),
        "trend": clamp01(float(features.get("trend_alignment", 0.0) or 0.0)),
        "momentum": clamp01(float(features.get("momentum", 0.0) or 0.0)),
        "trigger": clamp01(float(features.get("reclaim_or_breakout", 0.0) or 0.0)),
        "volume": clamp01(float(features.get("volume", 0.0) or 0.0)),
        "risk_reward": clamp01(float(features.get("risk_reward", 0.0) or 0.0)),
        "maturity": clamp01(1.0 - float(features.get("trend_maturity_penalty", 0.0) or 0.0)),
        "regime_fit": clamp01(float(features.get("regime_fit", 0.0) or 0.0)),
    }


def _regime_gate(strategy_key: str, regime_fit: float) -> float:
    if strategy_key in {"mean_reversion_bounce", "range_rotation"}:
        if regime_fit >= 0.90:
            return 1.0
        if regime_fit >= 0.60:
            return 0.70
        if regime_fit >= 0.30:
            return 0.20
        return 0.0

    if strategy_key in {"failed_breakdown_reclaim"}:
        if regime_fit >= 0.85:
            return 1.0
        if regime_fit >= 0.55:
            return 0.55
        if regime_fit >= 0.20:
            return 0.15
        return 0.0

    if regime_fit >= 0.80:
        return 1.0
    if regime_fit >= 0.50:
        return 0.60
    if regime_fit >= 0.20:
        return 0.12
    return 0.0


def _legacy_regime_profile(regime: str | None) -> dict[str, float] | None:
    return WEIGHTS_BY_REGIME.get((regime or "").upper())


def score_strategy_from_candles(strategy: str, features: dict, regime: str | None = None, asset_class: str = "stock") -> float:
    """Compute a normalized score from candle-derived features using an explicit matrix."""
    return compute_strategy_score(strategy, features, regime=regime, asset_class=asset_class)


# Regime-aware weight profiles
WEIGHTS_BY_REGIME = {
    "RISK_ON": {
        "structure": 0.20,
        "trend_alignment": 0.25,
        "momentum": 0.20,
        "reclaim_or_breakout": 0.18,
        "volume": 0.08,
        "risk_reward": 0.06,
        "regime_fit": 0.03,
    },
    "NEUTRAL": WEIGHTS,
    "RISK_OFF": {
        "structure": 0.30,
        "trend_alignment": 0.10,
        "momentum": 0.08,
        "reclaim_or_breakout": 0.12,
        "volume": 0.10,
        "risk_reward": 0.20,
        "regime_fit": 0.10,
    },
}


STRATEGY_WEIGHTS = {
    "trend_continuation": {
        "structure": 0.24,
        "trend_alignment": 0.24,
        "momentum": 0.22,
        "reclaim_or_breakout": 0.08,
        "volume": 0.08,
        "risk_reward": 0.09,
        "regime_fit": 0.05,
    },
    "breakout_retest": {
        "structure": 0.18,
        "trend_alignment": 0.16,
        "momentum": 0.11,
        "reclaim_or_breakout": 0.28,
        "volume": 0.10,
        "risk_reward": 0.09,
        "regime_fit": 0.08,
    },
    "range_rotation": {
        "structure": 0.12,
        "trend_alignment": 0.08,
        "momentum": 0.08,
        "reclaim_or_breakout": 0.24,
        "volume": 0.10,
        "risk_reward": 0.18,
        "regime_fit": 0.20,
    },
    "opening_range_breakout": {
        "structure": 0.16,
        "trend_alignment": 0.20,
        "momentum": 0.22,
        "reclaim_or_breakout": 0.20,
        "volume": 0.12,
        "risk_reward": 0.06,
        "regime_fit": 0.04,
    },
    "volatility_compression_breakout": {
        "structure": 0.16,
        "trend_alignment": 0.17,
        "momentum": 0.18,
        "reclaim_or_breakout": 0.22,
        "volume": 0.10,
        "risk_reward": 0.09,
        "regime_fit": 0.08,
    },
    "failed_breakdown_reclaim": {
        "structure": 0.18,
        "trend_alignment": 0.14,
        "momentum": 0.10,
        "reclaim_or_breakout": 0.24,
        "volume": 0.08,
        "risk_reward": 0.16,
        "regime_fit": 0.10,
    },
}


def _blend_weight_profile(strategy_key: str, regime: str | None) -> dict:
    profile = dict(STRATEGY_WEIGHTS.get(strategy_key, WEIGHTS))
    regime_profile = WEIGHTS_BY_REGIME.get((regime or "").upper())
    if not regime_profile:
        return profile
    blended = {}
    keys = set(profile) | set(regime_profile)
    for key in keys:
        blended[key] = float(profile.get(key, 0.0)) * 0.70 + float(regime_profile.get(key, 0.0)) * 0.30
    return blended


def clamp_01(v: float) -> float:
    return clamp01(v)


def normalize_percent_distance(a: float, b: float) -> float:
    try:
        return clamp01(abs(a - b) / max(abs(b), 1.0))
    except Exception:
        return 0.0


def normalize_slope(delta: float, price: float) -> float:
    try:
        return clamp01((delta / max(abs(price), 1.0)) * 5.0)
    except Exception:
        return 0.0


def normalize_rr(entry: float, stop: float, tp: float) -> float:
    try:
        risk = max(1e-6, entry - stop)
        reward = max(0.0, tp - entry)
        if reward <= 0:
            return 0.0
        rr = reward / risk
        return clamp01(min(1.0, rr / 3.0))
    except Exception:
        return 0.0


def normalize_volume_expansion(curr_vol: float, prior_vol: float) -> float:
    try:
        if prior_vol <= 0:
            return clamp01(curr_vol / max(1.0, curr_vol))
        return clamp01((curr_vol - prior_vol) / prior_vol)
    except Exception:
        return 0.0


def compute_strategy_score(strategy_key: str, features: dict, regime: str | None = None, asset_class: str = "stock") -> float:
    """Compute a normalized score using an explicit per-strategy matrix."""
    matrix = _strategy_weight_matrix(strategy_key, asset_class)
    components = _feature_component_map(features)

    score = 0.0
    for component, weight in matrix.items():
        score += components.get(component, 0.0) * float(weight)

    regime_fit = components.get("regime_fit", 0.0)
    gate = _regime_gate(strategy_key, regime_fit)
    score *= gate

    diagnostics = features.get("_diagnostics", {}) or {}
    if not bool(diagnostics.get("raw_signal_present", False)):
        score *= 0.92

    legacy_profile = _legacy_regime_profile(regime)
    if legacy_profile:
        legacy_score = 0.0
        for key, weight in legacy_profile.items():
            component_key = {
                "trend_alignment": "trend",
                "reclaim_or_breakout": "trigger",
                "regime_fit": "regime_fit",
            }.get(key, key)
            legacy_score += components.get(component_key, 0.0) * float(weight)
        score = (score * 0.85) + (legacy_score * 0.15)

    setup_bonus = 0.0
    trigger = components.get("trigger", 0.0)
    volume = components.get("volume", 0.0)
    structure = components.get("structure", 0.0)
    momentum = components.get("momentum", 0.0)
    risk_reward = components.get("risk_reward", 0.0)

    if strategy_key in {"opening_range_breakout", "volatility_compression_breakout"}:
        setup_bonus += trigger * 0.05 + volume * 0.03
        if strategy_key == "volatility_compression_breakout":
            setup_bonus += structure * 0.02
    elif strategy_key == "breakout_retest":
        setup_bonus += trigger * 0.04 + structure * 0.02
    elif strategy_key == "failed_breakdown_reclaim":
        setup_bonus += trigger * 0.05 + risk_reward * 0.03
    elif strategy_key == "mean_reversion_bounce":
        setup_bonus += structure * 0.03 + momentum * 0.03
    elif strategy_key == "range_rotation":
        setup_bonus += risk_reward * 0.03

    score += setup_bonus

    if asset_class == "crypto":
        score = min(1.0, score * 1.05 + 0.005)

    return max(0.0, min(1.0, score))

def build_bot_decision(evaluated: Dict[str, float], ai_hint: Optional[dict]) -> BotDecision:
    # Select best by score (deterministic tie-breaker by sorted strategy name)
    if not evaluated:
        return BotDecision(None, 0.0, {}, ai_hint.get("suggested_strategy") if ai_hint else None, ai_hint.get("confidence") if ai_hint else None, None, False, 0.0)

    # Determine best strategy
    sorted_items = sorted(evaluated.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    best_strategy, best_score = sorted_items[0]

    ai_strat = ai_hint.get("suggested_strategy") if ai_hint else None
    ai_conf = float(ai_hint.get("confidence")) if ai_hint and ai_hint.get("confidence") is not None else None

    agreement = (ai_strat == best_strategy) if ai_strat else None

    # For audit we record whether bias was applied — caller must record exact bias amounts
    return BotDecision(
        selected_strategy=best_strategy,
        selected_score=round(float(best_score), 6),
        evaluated_strategies={k: round(float(v), 6) for k, v in evaluated.items()},
        ai_hint_strategy=ai_strat,
        ai_hint_confidence=ai_conf,
        ai_hint_agreement=agreement,
        ai_hint_bias_applied=False,
        ai_hint_bias_amount=0.0,
    )
