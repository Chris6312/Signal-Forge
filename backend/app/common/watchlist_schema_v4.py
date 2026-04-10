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
    """Return a mapping of normalized component scores (0..1) for the given signal.

    `signal` is the strategy signal object produced by entry strategies and is
    expected to expose `.reasoning` dict, `.regime`, and pricing fields.
    """
    reasoning = getattr(signal, "reasoning", {}) or {}
    regime = getattr(signal, "regime", None)

    # Derive close price to normalize where available
    close = None
    try:
        close = float(getattr(signal, "entry_price", None) or reasoning.get("close") or reasoning.get("entry_price") or 0.0)
        if close == 0.0:
            close = None
    except Exception:
        close = None

    # Read common EMA / ATR values from reasoning if present
    ema9 = reasoning.get("ema9")
    ema20 = reasoning.get("ema20")
    ema50 = reasoning.get("ema50")
    ema200 = reasoning.get("ema200")
    atr = reasoning.get("atr")

    # trend_strength: normalized distance between EMA20 and EMA50 vs price
    try:
        if ema20 is not None and ema50 is not None and close:
            trend_strength = abs(float(ema20) - float(ema50)) / float(close)
        else:
            trend_strength = 0.0
    except Exception:
        trend_strength = 0.0

    # momentum_alignment: price-normalized EMA20 slope over 5 periods
    try:
        # Prefer an explicit past ema value if present (e.g., ema20_past)
        ema20_past = reasoning.get("ema20_past")
        if ema20 is not None and ema20_past is not None and close:
            momentum_alignment = (float(ema20) - float(ema20_past)) / float(close)
        elif ema20 is not None and close and reasoning.get("ema20_history"):
            hist = reasoning.get("ema20_history")
            if isinstance(hist, (list, tuple)) and len(hist) >= 5:
                momentum_alignment = (float(hist[-1]) - float(hist[-5])) / float(close)
            else:
                momentum_alignment = 0.0
        elif ema20 is not None and close:
            # best-effort: use current_vs_ema20 as proxy
            current_vs_ema20 = float(reasoning.get("current_vs_ema20", 0.0))
            momentum_alignment = current_vs_ema20 / float(close)
        else:
            momentum_alignment = 0.0
    except Exception:
        momentum_alignment = 0.0

    # MA structure: graded stacking of EMA9>EMA20, EMA20>EMA50, EMA50>EMA200
    ma_structure = 0.0
    has_any = False
    try:
        if ema9 is not None and ema20 is not None:
            has_any = True
            if float(ema9) > float(ema20):
                ma_structure += 0.33
        if ema20 is not None and ema50 is not None:
            has_any = True
            if float(ema20) > float(ema50):
                ma_structure += 0.33
        if ema50 is not None and ema200 is not None:
            has_any = True
            if float(ema50) > float(ema200):
                ma_structure += 0.34
    except Exception:
        ma_structure = 0.0

    if not has_any:
        # fallback to previous structure heuristic
        ma_structure = _structure_score_from_reasoning(reasoning)

    # volatility context: lower ATR relative to price -> higher score
    try:
        if atr is not None and close:
            volatility_context = 1.0 - (float(atr) / float(close))
        else:
            volatility_context = 0.5
    except Exception:
        volatility_context = 0.5

    # price location relative to EMA20 normalized by ATR (helps reclaim vs continuation)
    price_location = 0.0
    try:
        if ema20 is not None and atr is not None and atr != 0 and close is not None:
            price_location = (float(close) - float(ema20)) / float(atr)
            if price_location < -1.0:
                price_location = -1.0
            if price_location > 1.0:
                price_location = 1.0
        else:
            price_location = 0.0
    except Exception:
        price_location = 0.0

    features = {
        "structure": clamp01(ma_structure),
        "trend_alignment": clamp01(trend_strength),
        "momentum": clamp01(momentum_alignment),
        "reclaim_or_breakout": clamp01(abs(float(reasoning.get("breakout_pct", 0.0))) / 10.0 if reasoning.get("breakout_pct") is not None else clamp01(abs(price_location))),
        "volume": _volume_confirmation_from_reasoning(reasoning),
        "risk_reward": _risk_reward_from_signal(signal),
        "regime_fit": _regime_fit_from_regime_and_strategy(regime, strategy_key),
        # expose derived diagnostics for audits
        "_diagnostics": {
            "price_location": round(price_location, 6),
            "volatility_context": round(clamp01(volatility_context), 6),
        },
    }

    # Ensure clamped
    out = {k: clamp01(v) if k != "_diagnostics" else v for k, v in features.items()}
    return out


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
    # Choose weight profile
    profile = WEIGHTS_BY_REGIME.get((regime or "NEUTRAL"), WEIGHTS)

    # Weighted sum
    s = 0.0
    for k, w in profile.items():
        s += float(features.get(k, 0.0)) * float(w)
    s = max(0.0, min(1.0, s))

    # Strategy-specific calibration ranges
    CALIBRATION = {
        "trend_continuation": (0.1, 0.85),
        "pullback_reclaim": (0.05, 0.80),
        "mean_reversion_bounce": (0.05, 0.75),
        "range_breakout": (0.05, 0.80),
    }

    low, high = CALIBRATION.get(strategy_key, (0.0, 1.0))
    calibrated = low + s * (high - low)

    # Asset-class-specific volatility scaling for crypto (gentler penalties)
    if asset_class == "crypto":
        # gently boost moderate scores to account for higher baseline noise
        calibrated = calibrated * 0.95 + 0.05

    # Ensure in 0..1 after calibration
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
