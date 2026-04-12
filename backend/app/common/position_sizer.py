from __future__ import annotations

import logging
import statistics

from app.common.account_state import compute_drawdown_pct, drawdown_multiplier, should_block_new_entries
from app.common.risk_config import normalize_asset_class, resolve_baseline_atr_percent, resolve_risk_per_trade_pct


logger = logging.getLogger(__name__)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def compute_volatility_multiplier(atr: float, price: float, baseline_atr_percent: float) -> float:
    try:
        atr_value = float(atr)
        price_value = float(price)
        baseline_value = float(baseline_atr_percent)
    except (TypeError, ValueError):
        return 1.0

    if atr_value <= 0 or price_value <= 0 or baseline_value <= 0:
        return 1.0

    atr_percent = atr_value / price_value
    vol_ratio = atr_percent / baseline_value
    if vol_ratio <= 0:
        return 1.0

    multiplier = 1.0 / vol_ratio
    return _clamp(multiplier, 0.5, 1.5)


def _volatility_multiplier(volatility_pct: float) -> float:
    if volatility_pct < 0.01:
        return 1.0
    if volatility_pct < 0.02:
        return 0.85
    if volatility_pct < 0.035:
        return 0.60
    return 0.35


def _extract_volatility_pct(entry_price: float, volatility_pct: float | None = None, signal=None, reasoning: dict | None = None) -> float:
    if volatility_pct is not None:
        try:
            return max(0.0, float(volatility_pct))
        except (TypeError, ValueError):
            return 0.0

    reasoning = reasoning or getattr(signal, "reasoning", None) or {}
    for key in ("volatility_pct", "atr_pct"):
        value = reasoning.get(key)
        if value is not None:
            try:
                return max(0.0, float(value))
            except (TypeError, ValueError):
                pass

    atr_value = reasoning.get("atr") or reasoning.get("atr_14") or reasoning.get("atr_recent")
    try:
        atr = float(atr_value) if atr_value is not None else 0.0
    except (TypeError, ValueError):
        atr = 0.0
    try:
        price = float(entry_price)
    except (TypeError, ValueError):
        price = 0.0
    if atr > 0 and price > 0:
        return atr / price

    closes = reasoning.get("recent_closes") or reasoning.get("close_history") or reasoning.get("closes")
    if isinstance(closes, (list, tuple)) and len(closes) >= 2:
        try:
            values = [float(value) for value in closes if value is not None]
        except (TypeError, ValueError):
            values = []
        if len(values) >= 2:
            mean_close = statistics.fmean(values)
            if mean_close > 0:
                return statistics.pstdev(values) / mean_close if len(values) > 1 else 0.0

    return 0.0


def compute_position_size(
    asset_class: str,
    equity: float,
    entry_price: float,
    stop_distance: float,
    risk_per_trade_pct: float | None = None,
    *,
    current_equity: float | None = None,
    peak_equity: float | None = None,
    volatility_pct: float | None = None,
    signal=None,
    reasoning: dict | None = None,
    max_notional_pct: float | None = None,
    min_notional: float = 1.0,
) -> float:
    asset = normalize_asset_class(asset_class)
    try:
        equity_value = float(equity)
        entry_value = float(entry_price)
        stop_value = float(stop_distance)
    except (TypeError, ValueError):
        return 0.0

    if equity_value <= 0 or entry_value <= 0 or stop_value <= 0:
        return 0.0

    risk_pct_value = resolve_risk_per_trade_pct(asset, risk_per_trade_pct)
    if risk_pct_value <= 0:
        return 0.0

    base_position_size = (equity_value * risk_pct_value) / stop_value
    volatility_value = _extract_volatility_pct(entry_value, volatility_pct=volatility_pct, signal=signal, reasoning=reasoning)
    reasoning_map = reasoning or getattr(signal, "reasoning", None) or {}
    atr_value = reasoning_map.get("atr") or reasoning_map.get("atr_14") or reasoning_map.get("atr_recent")
    if atr_value is not None:
        try:
            vol_multiplier = compute_volatility_multiplier(
                atr=float(atr_value),
                price=entry_value,
                baseline_atr_percent=resolve_baseline_atr_percent(),
            )
        except (TypeError, ValueError):
            vol_multiplier = _volatility_multiplier(volatility_value)
    else:
        vol_multiplier = _volatility_multiplier(volatility_value)
    peak_value = float(peak_equity if peak_equity is not None else current_equity if current_equity is not None else equity_value)
    current_value = float(current_equity if current_equity is not None else equity_value)
    drawdown_pct = compute_drawdown_pct(current_value, peak_value)
    if should_block_new_entries(drawdown_pct):
        debug_payload = {
            "equity": equity_value,
            "risk_pct": risk_pct_value,
            "stop_distance": stop_value,
            "volatility_pct": volatility_value,
            "vol_multiplier": vol_multiplier,
            "drawdown_pct": drawdown_pct,
            "dd_multiplier": 0.0,
            "final_size": 0.0,
        }
        logger.debug("position_sizer=%s", debug_payload)
        return 0.0

    dd_multiplier = drawdown_multiplier(drawdown_pct)
    final_size = max(0.0, base_position_size * vol_multiplier * dd_multiplier)

    if max_notional_pct is not None:
        try:
            max_notional = max(0.0, float(max_notional_pct))
            final_size = min(final_size, (equity_value * max_notional) / entry_value)
        except (TypeError, ValueError):
            pass

    if final_size * entry_value < float(min_notional):
        final_size = 0.0
    elif asset == "stock":
        final_size = float(int(final_size))
    else:
        final_size = round(final_size, 8)

    debug_payload = {
        "equity": equity_value,
        "risk_pct": risk_pct_value,
        "stop_distance": stop_value,
        "volatility_pct": volatility_value,
        "vol_multiplier": vol_multiplier,
        "drawdown_pct": drawdown_pct,
        "dd_multiplier": dd_multiplier,
        "final_size": final_size,
    }
    logger.debug("position_sizer=%s", debug_payload)
    return max(0.0, final_size)
