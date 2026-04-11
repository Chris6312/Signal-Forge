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
        if strat and strat not in ("pullback_reclaim", "trend_continuation", "mean_reversion_bounce", "range_breakout"):
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


def _regime_fit_from_regime_and_strategy(regime: Optional[str], strategy_key: str) -> float:
    if not regime:
        return 0.5
    if strategy_key == "trend_continuation":
        return 1.0 if regime == "trending_up" else 0.2
    if strategy_key == "pullback_reclaim":
        return 0.9 if regime == "trending_up" else 0.4
    if strategy_key == "mean_reversion_bounce":
        return 1.0 if regime == "ranging" else 0.1
    if strategy_key == "range_breakout":
        return 0.7 if regime in ("trending_up", "ranging") else 0.3
    return 0.5


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

    stack_score = 0.0
    stack_pairs = 0
    for a, b, weight in ((ema9, ema20, 0.34), (ema20, ema50, 0.33), (ema50, ema200, 0.33)):
        if a is None or b is None:
            continue
        stack_pairs += 1
        if a > b:
            stack_score += weight

    structure = stack_score if stack_pairs else _structure_score_from_reasoning(reasoning)
    if reasoning.get("higher_highs_confirmed"):
        structure += 0.12
    if reasoning.get("higher_lows_confirmed"):
        structure += 0.12
    if reasoning.get("higher_closes_confirmed"):
        structure += 0.08
    if reasoning.get("three_ascending_closes"):
        structure += 0.08
    if reasoning.get("dip_below_ema_confirmed") or reasoning.get("reclaim_confirmed"):
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
    breakout_up_pct = max(0.0, breakout_pct or 0.0)
    breakout_down_pct = max(0.0, -(breakout_pct or 0.0))
    if breakout_pct is not None:
        momentum += clamp01(breakout_up_pct / 2.0) * 0.35
        momentum -= clamp01(breakout_down_pct / 2.0) * 0.20
    if reasoning.get("higher_closes_confirmed"):
        momentum += 0.10
    if reasoning.get("three_ascending_closes"):
        momentum += 0.10
    if breakout_down_pct > 0 and not reasoning.get("higher_closes_confirmed"):
        momentum -= 0.08
    momentum = clamp01(momentum)

    reclaim_or_breakout = 0.0
    trigger_type = str(reasoning.get("trigger_type") or "").lower()
    if trigger_type in {"breakout", "continuation"}:
        reclaim_or_breakout += 0.35
    if trigger_type in {"reclaim", "pullback", "failed_breakdown_reclaim"}:
        reclaim_or_breakout += 0.35
    if trigger_type in {"mean_reversion", "range_reversal"}:
        reclaim_or_breakout += 0.25
    if breakout_pct is not None:
        reclaim_or_breakout += clamp01(breakout_up_pct / 1.5) * 0.35
        reclaim_or_breakout -= clamp01(breakout_down_pct / 1.5) * 0.15
    if reasoning.get("dip_below_ema_confirmed"):
        reclaim_or_breakout += 0.20
    if reasoning.get("reclaim_confirmed"):
        reclaim_or_breakout += 0.20
    if reasoning.get("price_in_retest_band"):
        reclaim_or_breakout += 0.15
    if reasoning.get("bounce_confirmed"):
        reclaim_or_breakout += 0.15
    if trigger_type in {"breakout", "continuation"} and breakout_up_pct <= 0.0:
        reclaim_or_breakout -= 0.12
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
            class _Tmp: pass
            tmp = _Tmp()
            tmp.entry_price = close
            tmp.initial_stop = fallback_stop
            tmp.profit_target_1 = fallback_tp
            risk_reward = _risk_reward_from_signal(tmp)

    extension_penalty = 0.0
    if close is not None and ema20 is not None:
        extension_penalty += clamp01(max(0.0, close - ema20) / max(abs(close), 1.0) * 10.0) * 0.40
    if close is not None and ema50 is not None:
        extension_penalty += clamp01(max(0.0, close - ema50) / max(abs(close), 1.0) * 6.0) * 0.20
    stall_penalty = 0.0
    if trigger_type in {"breakout", "continuation"} and breakout_up_pct < 0.2:
        stall_penalty += 0.20
    if not reasoning.get("higher_highs_confirmed") and not reasoning.get("higher_lows_confirmed"):
        stall_penalty += 0.15
    if breakout_down_pct > 0.0:
        stall_penalty += clamp01(breakout_down_pct / 2.5) * 0.30
    if current_vs_ema20 is not None and current_vs_ema20 < 0:
        stall_penalty += clamp01(abs(current_vs_ema20) / max(abs(close or 1.0), 1.0) * 18.0) * 0.20

    trend_maturity_penalty = clamp01(extension_penalty + stall_penalty)

    features = {
        "structure": structure,
        "trend_alignment": trend_alignment,
        "momentum": momentum,
        "reclaim_or_breakout": reclaim_or_breakout,
        "volume": clamp01(volume),
        "risk_reward": clamp01(risk_reward),
        "regime_fit": _regime_fit_from_regime_and_strategy(regime, strategy_key),
        "trend_maturity_penalty": trend_maturity_penalty,
        "_diagnostics": {
            "price_location": round(clamp01(((current_vs_ema20 or 0.0) / max(atr or 1.0, 1e-6)) * 0.5 + 0.5), 6) if atr else 0.5,
            "volatility_context": round(clamp01(1.0 - ((atr or 0.0) / max(abs(close or 1.0), 1.0))), 6),
            "signal_schema_version": reasoning.get("signal_schema_version", "v2"),
            "trigger_type": trigger_type or None,
            "breakout_up_pct": round(breakout_up_pct, 6),
            "breakout_down_pct": round(breakout_down_pct, 6),
            "trend_maturity_penalty": round(trend_maturity_penalty, 6),
        },
    }
    return {k: clamp01(v) if k != "_diagnostics" else v for k, v in features.items()}



def score_strategy_from_candles(strategy: str, features: dict) -> float:
    """Compute a normalized 0..1-ish score from candle-derived features only.

    `features` is a pre-computed dict of normalized sub-scores (0..1)
    keyed by the same component names used in WEIGHTS.
    """
    s = 0.0
    for k, w in WEIGHTS.items():
        s += float(features.get(k, 0.0)) * float(w)
    # Ensure bounded between 0 and 1
    if s < 0:
        s = 0.0
    if s > 1.0:
        s = 1.0
    return s


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
    """Compute base score with regime-aware weights and per-strategy calibration.

    features: dict of component scores in 0..1 matching WEIGHTS keys
    """
    profile = WEIGHTS_BY_REGIME.get((regime or "NEUTRAL"), WEIGHTS)

    s = 0.0
    for k, w in profile.items():
        s += float(features.get(k, 0.0)) * float(w)
    s = max(0.0, min(1.0, s))

    # Penalize late / stalling trends so post-impulse chop does not
    # score like a fresh continuation or breakout.
    maturity_penalty = float(features.get("trend_maturity_penalty", 0.0) or 0.0)

    if strategy_key == "trend_continuation":
        s -= maturity_penalty * 0.35
    elif strategy_key == "range_breakout":
        s -= maturity_penalty * 0.28
    elif strategy_key == "pullback_reclaim":
        s -= maturity_penalty * 0.18
    elif strategy_key == "mean_reversion_bounce":
        s -= maturity_penalty * 0.10

    s = max(0.0, min(1.0, s))

    CALIBRATION = {
        "trend_continuation": (0.1, 0.85),
        "pullback_reclaim": (0.05, 0.80),
        "mean_reversion_bounce": (0.05, 0.75),
        "range_breakout": (0.05, 0.80),
    }

    low, high = CALIBRATION.get(strategy_key, (0.0, 1.0))
    calibrated = low + s * (high - low)

    if asset_class == "crypto":
        calibrated = calibrated * 0.95 + 0.05

    return max(0.0, min(1.0, calibrated))


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
