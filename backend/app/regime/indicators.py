from dataclasses import dataclass


@dataclass
class AssetIndicators:
    close: float
    sma20: float
    sma50: float
    ema20: float
    return_5d: float
    return_10d: float
    sma20_slope: float
    relative_strength_vs_btc_10d: float | None = None


@dataclass
class VixIndicators:
    close: float
    sma10: float
    return_5d: float


def _sma(prices: list[float], period: int) -> float:
    return sum(prices[-period:]) / period


def _ema(prices: list[float], period: int) -> float:
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema


def _sma20_slope(prices: list[float]) -> float:
    if len(prices) < 25:
        return 0.0
    current = _sma(prices, 20)
    prior = sum(prices[-25:-5]) / 20
    return (current - prior) / prior


def _pct_return(prices: list[float], period: int) -> float:
    return (prices[-1] - prices[-(period + 1)]) / prices[-(period + 1)]


def build_asset_indicators(
    closes: list[float],
    btc_closes: list[float] | None = None,
) -> AssetIndicators:
    rs_vs_btc: float | None = None
    if btc_closes is not None and len(btc_closes) >= 11 and len(closes) >= 11:
        rs_vs_btc = _pct_return(closes, 10) - _pct_return(btc_closes, 10)

    return AssetIndicators(
        close=closes[-1],
        sma20=_sma(closes, 20),
        sma50=_sma(closes, 50),
        ema20=_ema(closes, 20),
        return_5d=_pct_return(closes, 5),
        return_10d=_pct_return(closes, 10),
        sma20_slope=_sma20_slope(closes),
        relative_strength_vs_btc_10d=rs_vs_btc,
    )


def build_vix_indicators(closes: list[float]) -> VixIndicators:
    return VixIndicators(
        close=closes[-1],
        sma10=_sma(closes, 10),
        return_5d=_pct_return(closes, 5),
    )
