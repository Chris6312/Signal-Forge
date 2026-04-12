from __future__ import annotations

import os


DEFAULT_RISK_PER_TRADE_PCT: dict[str, float] = {
    "stock": 0.005,
    "crypto": 0.004,
}


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


def resolve_risk_per_trade_pct(asset_class: str | None = None, runtime_override=None) -> float:
    if isinstance(runtime_override, dict):
        asset = normalize_asset_class(asset_class)
        value = runtime_override.get(asset)
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
