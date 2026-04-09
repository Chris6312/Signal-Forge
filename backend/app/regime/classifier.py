from .indicators import AssetIndicators, VixIndicators

RegimeLabel = str


def classify_stock_regime(spy: AssetIndicators, vix: VixIndicators) -> tuple[RegimeLabel, int]:
    score = 0

    if spy.close > spy.sma20:
        score += 1
    if spy.close > spy.sma50:
        score += 1
    if spy.sma20_slope > 0:
        score += 1
    if spy.return_5d > 0:
        score += 1
    if vix.close < 20:
        score += 1
    if vix.close <= vix.sma10:
        score += 1
    if vix.return_5d < 0:
        score += 1

    if vix.close > 40:
        return "RISK_OFF", score
    if vix.close > 30 and spy.close < spy.sma50:
        return "RISK_OFF", score

    if score >= 6:
        return "RISK_ON", score
    if score <= 2:
        return "RISK_OFF", score
    return "NEUTRAL", score


def classify_crypto_regime(btc: AssetIndicators, eth: AssetIndicators) -> tuple[RegimeLabel, int]:
    score = 0

    if btc.close > btc.ema20:
        score += 1
    if btc.close > btc.sma50:
        score += 1
    if btc.sma20_slope > 0:
        score += 1
    if btc.return_5d > 0:
        score += 1
    if eth.close > eth.ema20:
        score += 1
    if eth.relative_strength_vs_btc_10d is not None and eth.relative_strength_vs_btc_10d >= -0.02:
        score += 1
    if eth.return_5d > 0:
        score += 1

    if btc.close < btc.sma50 and eth.close < eth.sma50:
        return "RISK_OFF", score

    if score >= 6:
        return "RISK_ON", score
    if score <= 2:
        return "RISK_OFF", score
    return "NEUTRAL", score
