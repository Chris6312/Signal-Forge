from __future__ import annotations

"""Deterministic symbol-to-correlation-cluster helpers.

This module intentionally keeps the logic small, pure, and side-effect free.
"""

import math


_CRYPTO_L1 = {"BTC/USD", "XBT/USD", "XXBTZUSD", "ETH/USD", "XETHZUSD", "SOL/USD", "ADA/USD", "AVAX/USD"}
_CRYPTO_AI = {"TAO/USD", "FET/USD", "RNDR/USD"}
_CRYPTO_L2 = {"ARB/USD", "OP/USD", "STRK/USD"}

_STOCKS_AI = {"NVDA", "AMD", "SMCI"}
_STOCKS_MEGA_CAP = {"MSFT", "GOOGL", "META"}
_STOCKS_FINANCIALS = {"XLF", "JPM", "GS"}
_STOCKS_ENERGY = {"XLE", "CVX", "XOM"}

_CRYPTO_CLUSTER_MAP = {
    **{symbol: "crypto_l1" for symbol in _CRYPTO_L1},
    **{symbol: "crypto_ai" for symbol in _CRYPTO_AI},
    **{symbol: "crypto_l2" for symbol in _CRYPTO_L2},
}

_STOCK_CLUSTER_MAP = {
    **{symbol: "stocks_ai" for symbol in _STOCKS_AI},
    **{symbol: "stocks_mega_cap" for symbol in _STOCKS_MEGA_CAP},
    **{symbol: "stocks_financials" for symbol in _STOCKS_FINANCIALS},
    **{symbol: "stocks_energy" for symbol in _STOCKS_ENERGY},
}

_BTC_ALIASES = {"BTC/USD", "XBT/USD", "XXBTZUSD"}


def _normalize_asset_class(asset_class: str | None) -> str | None:
    if asset_class is None:
        return None
    normalized = asset_class.strip().lower()
    if normalized in {"crypto"}:
        return "crypto"
    if normalized in {"stock", "stocks"}:
        return "stock"
    return None


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def resolve_correlation_cluster(symbol: str, asset_class: str | None = None) -> str:
    normalized_asset_class = _normalize_asset_class(asset_class)
    normalized_symbol = _normalize_symbol(symbol or "")

    if not normalized_asset_class:
        return "other"

    if normalized_asset_class == "crypto":
        if normalized_symbol in _BTC_ALIASES:
            return "crypto_l1"
        return _CRYPTO_CLUSTER_MAP.get(normalized_symbol, "crypto_other")

    if normalized_asset_class == "stock":
        return _STOCK_CLUSTER_MAP.get(normalized_symbol, "stocks_other")

    return "other"


def compute_cluster_exposure_notional(positions: list[dict]) -> dict[str, float]:
    totals: dict[str, float] = {}

    for position in positions or []:
        if not isinstance(position, dict):
            continue

        symbol = position.get("symbol")
        if not symbol:
            continue

        market_value = position.get("market_value")
        try:
            notional = abs(float(market_value))
        except (TypeError, ValueError):
            continue

        if notional <= 0:
            continue

        cluster = resolve_correlation_cluster(
            symbol=str(symbol),
            asset_class=position.get("asset_class"),
        )
        totals[cluster] = totals.get(cluster, 0.0) + notional

    return totals


def compute_cluster_exposure_multiplier(
    symbol: str,
    asset_class: str | None,
    proposed_trade_notional: float,
    open_positions: list[dict],
    account_equity: float,
) -> float:
    try:
        proposed_value = abs(float(proposed_trade_notional))
        equity_value = float(account_equity)
    except (TypeError, ValueError):
        return 1.0

    if proposed_value <= 0 or equity_value <= 0:
        return 1.0

    cluster = resolve_correlation_cluster(symbol=symbol, asset_class=asset_class)
    cluster_totals = compute_cluster_exposure_notional(open_positions)
    cluster_total = cluster_totals.get(cluster, 0.0) + proposed_value
    exposure_ratio = cluster_total / equity_value

    if exposure_ratio < 0.20:
        return 1.0
    if exposure_ratio < 0.30:
        return 0.8
    if exposure_ratio < 0.40:
        return 0.6
    return 0.4


def compute_symbol_concentration_ratio(
    symbol: str,
    proposed_trade_notional: float,
    open_positions: list[dict],
    account_equity: float,
) -> float:
    normalized_symbol = _normalize_symbol(symbol or "")
    if not normalized_symbol:
        return 0.0

    try:
        proposed_value = abs(float(proposed_trade_notional))
        equity_value = float(account_equity)
    except (TypeError, ValueError):
        return 0.0

    if proposed_value <= 0 or equity_value <= 0:
        return 0.0

    total_notional = proposed_value

    for position in open_positions or []:
        if not isinstance(position, dict):
            continue

        position_symbol = position.get("symbol")
        if not position_symbol:
            continue

        try:
            normalized_position_symbol = _normalize_symbol(str(position_symbol))
        except (TypeError, ValueError, AttributeError):
            continue

        if normalized_position_symbol != normalized_symbol:
            continue

        market_value = position.get("market_value")
        try:
            position_notional = abs(float(market_value))
        except (TypeError, ValueError):
            continue

        if position_notional <= 0:
            continue

        total_notional += position_notional

    ratio = total_notional / equity_value
    return ratio if ratio >= 0 else 0.0


def compute_symbol_concentration_multiplier(concentration_ratio: float) -> float:
    try:
        ratio = float(concentration_ratio)
    except (TypeError, ValueError):
        return 1.0

    if not math.isfinite(ratio) or ratio < 0:
        return 1.0

    if ratio < 0.20:
        return 1.0
    if ratio < 0.25:
        return 0.75
    if ratio < 0.30:
        return 0.5
    return 0.0
