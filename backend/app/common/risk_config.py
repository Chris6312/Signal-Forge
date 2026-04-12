from __future__ import annotations

import os


DEFAULT_RISK_PER_TRADE_PCT: dict[str, float] = {
    "stock": 0.005,
    "crypto": 0.004,
}

DEFAULT_BASELINE_ATR_PERCENT_STOCK = 0.02
DEFAULT_BASELINE_ATR_PERCENT_CRYPTO = 0.04
DEFAULT_BASELINE_ATR_PERCENT = DEFAULT_BASELINE_ATR_PERCENT_STOCK


def _coerce_float(value, default: float) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def normalize_asset_class(asset_class: str | None) -> str:
    value = (asset_class or "").strip().lower()
    if value in ("stocks", "stock"):
        return "stock"
    if value in ("crypto", "cryptos", "digital"):
        return "crypto"
    return value or "stock"


def get_default_risk_per_trade_pct(asset_class: str | None = None) -> float:
    asset = normalize_asset_class(asset_class)
    global_override = os.getenv("RISK_PER_TRADE_PCT")
    asset_override = os.getenv(f"RISK_PER_TRADE_PCT_{asset.upper()}")
    if asset_override is not None:
        return _coerce_float(asset_override, DEFAULT_RISK_PER_TRADE_PCT.get(asset, 0.005))
    if global_override is not None:
        return _coerce_float(global_override, DEFAULT_RISK_PER_TRADE_PCT.get(asset, 0.005))
    return DEFAULT_RISK_PER_TRADE_PCT.get(asset, 0.005)


def get_default_baseline_atr_percent(asset_class: str | None = None) -> float:
    asset = normalize_asset_class(asset_class)
    if asset == "crypto":
        env_value = os.getenv("BASELINE_ATR_PERCENT_CRYPTO")
        default_value = DEFAULT_BASELINE_ATR_PERCENT_CRYPTO
    else:
        env_value = os.getenv("BASELINE_ATR_PERCENT_STOCK")
        default_value = DEFAULT_BASELINE_ATR_PERCENT_STOCK

    if env_value is not None:
        return _coerce_float(env_value, default_value)

    global_override = os.getenv("BASELINE_ATR_PERCENT")
    if global_override is not None:
        return _coerce_float(global_override, default_value)

    return default_value


def resolve_baseline_atr_percent(asset_class: str | None = None, runtime_override=None) -> float:
    asset = normalize_asset_class(asset_class)
    if isinstance(runtime_override, dict):
        value = runtime_override.get(f"baseline_atr_percent_{asset}")
        if value is None and asset != "stock":
            value = runtime_override.get("baseline_atr_percent_stock")
        if value is None:
            value = runtime_override.get("baseline_atr_percent")
        if value is not None:
            return _coerce_float(value, get_default_baseline_atr_percent(asset))
    if runtime_override is not None:
        return _coerce_float(runtime_override, get_default_baseline_atr_percent(asset))
    return get_default_baseline_atr_percent(asset)


def resolve_risk_per_trade_pct(asset_class: str | None = None, runtime_override=None) -> float:
    if isinstance(runtime_override, dict):
        asset = normalize_asset_class(asset_class)
        key = "risk_per_trade_pct_crypto" if asset == "crypto" else "risk_per_trade_pct_stocks"
        value = runtime_override.get(key)
        if value is None:
            value = runtime_override.get(f"risk_per_trade_pct_{asset}")
        if value is None:
            value = runtime_override.get("risk_per_trade_pct")
        if value is not None:
            return _coerce_float(value, get_default_risk_per_trade_pct(asset))
        return get_default_risk_per_trade_pct(asset)

    if runtime_override is not None:
        return _coerce_float(runtime_override, get_default_risk_per_trade_pct(asset_class))

    return get_default_risk_per_trade_pct(asset_class)
