# Signal Forge — Entry Strategies

`evaluate_all` runs every registered strategy in sequence and returns results sorted
by confidence, descending. The highest-confidence signal opens the position.

---

## Regime Detection

Applied to the close price series for both asset classes.

| Result | Condition |
|--------|-----------|
| `trending_up` | EMA20 > EMA50 × 1.01 (stocks: × 1.005) |
| `trending_down` | EMA20 < EMA50 × 0.99 (stocks: × 0.995) |
| `ranging` | Neither threshold met |
| `unknown` | Fewer than 50 bars available |

## ATR

14-period average of `max(High − Low, |High − Prev Close|, |Low − Prev Close|)`.

---

## Stock Entry Strategies

**Source:** `backend/app/stocks/strategies/entry_strategies.py`
**Data:** Tradier — daily bars. Minimum 20 bars required.

---

### 1 — Opening Range Breakout

**Confidence:** 0.72 | **Max hold:** 8 h | **Paired exit:** End-of-Day Exit

| | |
|---|---|
| **Regime** | Any |
| **Entry condition** | Price breaks above the high of the last 5 bars by ≥ 0.1 %, and is above EMA20 |
| **Stop** | Entry − ATR(14) × 1.2 |
| **TP1** | Entry + ATR(14) × 1.5 |
| **TP2** | Entry + ATR(14) × 3.0 |

---

### 2 — Pullback Reclaim

**Confidence:** 0.68 | **Max hold:** 6 h | **Paired exit:** Fixed Risk then Break-Even Promotion

| | |
|---|---|
| **Regime** | `trending_up` |
| **Entry condition** | Price was below EMA20 at least once in the last 6 bars and has closed above it |
| **Stop** | Min of last 5 lows − ATR(14) × 0.2 |
| **TP1** | Entry + ATR(14) × 1.5 |
| **TP2** | Entry + ATR(14) × 2.5 |

---

### 3 — Trend Continuation Ladder

**Confidence:** 0.70 | **Max hold:** 8 h | **Paired exit:** Partial at TP1, Trail Remainder

| | |
|---|---|
| **Regime** | `trending_up` |
| **Entry condition** | 3 consecutive higher highs and higher lows; price ≥ EMA20 × 0.99 |
| **Stop** | Entry − ATR(14) × 1.5 |
| **TP1** | Entry + ATR(14) × 1.5 |
| **TP2** | Entry + ATR(14) × 3.0 |

---

### 4 — Mean Reversion Bounce

**Confidence:** 0.62 | **Max hold:** 4 h | **Paired exit:** First Failed Follow-Through Exit

| | |
|---|---|
| **Regime** | `ranging` |
| **Entry condition** | Price > 2.5 % below EMA50; current close above prior close |
| **Stop** | Entry − ATR(14) × 1.0 |
| **TP1** | EMA50 |
| **TP2** | EMA50 + ATR(14) × 0.8 |

---

### 5 — Failed Breakdown Reclaim

**Confidence:** 0.67 | **Max hold:** 6 h | **Paired exit:** Fixed Risk then Break-Even Promotion

| | |
|---|---|
| **Regime** | Any |
| **Entry condition** | A recent low (last 5 bars) broke below prior support (bars −20 to −5), and price has since reclaimed above it with a rising close |
| **Stop** | Recent low − ATR(14) × 0.3 |
| **TP1** | Entry + ATR(14) × 1.5 |
| **TP2** | Entry + ATR(14) × 3.0 |

---

### 6 — Volatility Compression Breakout

**Confidence:** 0.73 | **Max hold:** 8 h | **Paired exit:** Partial at TP1, Trail Remainder

| | |
|---|---|
| **Regime** | Any |
| **Entry condition** | Recent ATR (5-period, last 10 bars) < 60 % of prior ATR (14-period, bars −30 to −10); price breaks above the 10-bar high |
| **Stop** | Entry − recent ATR × 1.5 |
| **TP1** | Entry + prior ATR × 1.5 |
| **TP2** | Entry + prior ATR × 3.0 |

---

## Crypto Entry Strategies

**Source:** `backend/app/crypto/strategies/entry_strategies.py`
**Data:** Kraken — 60-minute OHLCV. Minimum 30 bars required.

Exit strategy is assigned by the regime detected at signal time:

| Regime at entry | Assigned exit strategy |
|---|---|
| `trending_up` | Partial at TP1, Dynamic Trail on Runner |
| `ranging` | Range Failure Exit |
| `unknown` / other | Fixed Risk then Dynamic Protective Floor *(default)* |

---

### 1 — Momentum Breakout Continuation

**Confidence:** 0.70 | **Max hold:** 48 h | **Paired exit:** Partial at TP1, Dynamic Trail on Runner

| | |
|---|---|
| **Regime** | `trending_up` |
| **Entry condition** | Price exceeds the 20-bar high by > 0.2 %; price above EMA20 |
| **Stop** | Entry − ATR(14) × 1.5 |
| **TP1** | Entry + ATR(14) × 2.0 |
| **TP2** | Entry + ATR(14) × 4.0 |

---

### 2 — Pullback Reclaim

**Confidence:** 0.65 | **Max hold:** 36 h | **Paired exit:** Partial at TP1, Dynamic Trail on Runner

| | |
|---|---|
| **Regime** | `trending_up` |
| **Entry condition** | Price was below EMA20 at least once in the last 6 bars and has closed above it |
| **Stop** | Min of last 5 lows − ATR(14) × 0.3 |
| **TP1** | Entry + ATR(14) × 1.5 |
| **TP2** | Entry + ATR(14) × 3.0 |

---

### 3 — Mean Reversion Bounce

**Confidence:** 0.60 | **Max hold:** 24 h
**Paired exit:** Range Failure Exit *(ranging)* / Fixed Risk then Dynamic Protective Floor *(unknown)*

| | |
|---|---|
| **Regime** | `ranging` or `unknown` |
| **Entry condition** | Price > 3 % below EMA50; current close above prior close |
| **Stop** | Entry − ATR(14) × 1.0 |
| **TP1** | EMA50 |
| **TP2** | EMA50 + ATR(14) × 1.0 |

---

### 4 — Range Rotation Reversal

**Confidence:** 0.62 | **Max hold:** 24 h | **Paired exit:** Range Failure Exit

| | |
|---|---|
| **Regime** | `ranging` |
| **Entry condition** | Price within 2 % of the 30-bar range low; last 3 closes each higher than the previous |
| **Stop** | 30-bar range low − ATR(14) × 0.5 |
| **TP1** | Entry + ATR(14) × 2.0 |
| **TP2** | Entry + ATR(14) × 3.5 |

---

### 5 — Breakout Retest Hold

**Confidence:** 0.68 | **Max hold:** 36 h | **Paired exit:** Determined by regime at signal time

| | |
|---|---|
| **Regime** | Any |
| **Entry condition** | 10-bar high exceeded the 40-bar prior high (breakout confirmed); price has since pulled back to within 0.5 – 1.5 % of the prior resistance with a flat or rising close |
| **Stop** | Prior resistance − ATR(14) × 0.5 |
| **TP1** | Entry + ATR(14) × 2.0 |
| **TP2** | Entry + ATR(14) × 4.0 |

---

### 6 — Failed Breakdown Reclaim

**Confidence:** 0.67 | **Max hold:** 24 h | **Paired exit:** Determined by regime at signal time

| | |
|---|---|
| **Regime** | Any |
| **Entry condition** | A recent low (last 5 bars) broke below prior support (bars −20 to −5), and price has since reclaimed above it with a rising close |
| **Stop** | Recent low − ATR(14) × 0.3 |
| **TP1** | Entry + ATR(14) × 2.0 |
| **TP2** | Entry + ATR(14) × 3.5 |