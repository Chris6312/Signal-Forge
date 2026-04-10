Act as a technical swing trader focused on short-term momentum.
Scan all 11 S&P 500 sectors:
Communication Services
Consumer Discretionary
Consumer Staples
Energy
Financials
Health Care
Industrials
Information Technology
Materials
Real Estate
Utilities

Goal:
Identify the top 3 stocks in each sector with the strongest Short-Term Trend Alignment for a bullish swing trade setup.

Use these exact technical filters:
1. Price Structure
Daily chart must show a clear sequence of higher highs and higher lows over the last 20 trading days.
4-hour chart must also show higher highs and higher lows over the last 10 bars.
Exclude stocks with choppy, sideways, or broken structure.

2. Moving Averages
Price must be above the 20-day EMA and the 50-day SMA.
20-day EMA must be sloping upward.
Prefer stocks where the 20-day EMA is above the 50-day SMA, or where price has recently reclaimed both with follow-through.

3. Relative Strength vs SPY
Measure 5-day performance of the stock versus SPY.
Only include stocks outperforming SPY over the last 5 trading days.
Rank higher if the RS line is at or near a 20-day high.

4. Volume Confirmation
At least one recent bullish expansion candle on the daily chart must close green with volume greater than 1.5x its 20-day average volume.
Prefer names with accumulation on breakout attempts, not low-volume drift.

5. Liquidity / Trade Quality
Minimum average daily dollar volume: $20M
Exclude low-liquidity names and highly erratic charts with oversized gaps unless the setup is exceptionally clean.

For each stock:
## Use Web screening
**get_historical_quotes** — Pull 30 days of daily OHLCV to verify the symbol is in a trend (not a dead-cat bounce) and to confirm the current move is on above-average volume.

## Screening criteria (all must pass)

A symbol is included only when ALL of the following are true:

| Criterion | Requirement |
|---|---|
| Price | ≥ $5.00 |
| Today's gain | ≥ +2 % intraday |
| Volume | ≥ 1.5× its 20-day average volume |
| Trend | 20-day close > 50-day close (uptrend confirmed) |
| News sentiment | At least one positive catalyst in last 48 h, no major negative news |
| Momentum | Today's open > yesterday's close |

## Confidence scoring guide

| Score range | Meaning |
|---|---|
| 0.85 – 1.00 | Multiple strong catalysts: earnings beat + upgrade + breakout + volume |
| 0.75 – 0.84 | Two solid signals, e.g., positive news + top gainer + above-avg volume |
| 0.65 – 0.74 | One strong signal + technical confirmation, minor concerns noted |
| < 0.65 | Do not include |

## Output format

After completing your research, output ONLY a single JSON object that strictly conforms
to the WatchlistDecision schema. Do not include any explanation, preamble, or markdown
outside of a single ```json … ``` code block.

Required fields:
- `timestamp`: current UTC time in ISO 8601 format (e.g., "2024-01-15T14:30:00Z")
- `source`: always "claude"
- `symbols`: array of SymbolEntry objects (see schema)
- `notes`: one or two sentences summarising the session theme

Each SymbolEntry must include:
- `symbol`: uppercase ticker
- `asset_class`: "stock"
- `reason`: one clear sentence describing the catalyst
- `confidence`: float 0.65–1.0
- `tags`: 1–4 tags from the allowed list
- `price_at_decision`: last trade price from get_quotes