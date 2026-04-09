# Signal Forge — Exit Strategies

Exit strategies are evaluated on every exit-worker cycle (default 30 s). Each strategy
receives the full position object, current market price, and recent OHLCV history, and
returns an `ExitDecision` that may trigger a full close, a partial exit, a stop update,
or no action.

---

## Stock Exit Strategies

**Source:** `backend/app/stocks/strategies/exit_strategies.py`
**Default:** Fixed Risk then Break-Even Promotion

### Exit Strategy Assignment

Frozen at position open based on the entry strategy name.

| Entry strategy | Assigned exit strategy |
|---|---|
| Opening Range Breakout | End-of-Day Exit |
| Trend Continuation Ladder | Partial at TP1, Trail Remainder |
| Volatility Compression Breakout | Partial at TP1, Trail Remainder |
| Mean Reversion Bounce | First Failed Follow-Through Exit |
| Pullback Reclaim | Fixed Risk then Break-Even Promotion |
| Failed Breakdown Reclaim | Fixed Risk then Break-Even Promotion |

### End-of-Day Guard

All stock strategies share an EOD guard. Once UTC time reaches **20:45**
(≈ 4:45 PM EDT / 3:45 PM EST), any open position is closed on the next cycle,
regardless of the assigned strategy.

---

### 1 — Fixed Risk then Break-Even Promotion *(default)*

| Condition | Action |
|---|---|
| Price ≤ current stop | Full exit — "Stop hit" |
| UTC ≥ 20:45 | Full exit — EOD |
| Price ≥ 50 % of TP1 and stop not yet at entry | Promote stop to entry |
| Otherwise | Hold |

---

### 2 — Partial at TP1, Trail Remainder

| Condition | Action |
|---|---|
| Price ≤ current stop | Full exit — "Stop hit" |
| UTC ≥ 20:45 | Full exit — EOD |
| Price ≥ TP1 (first time) | Partial exit 50 %; stop moved to entry |
| After TP1 — price ≤ trailing stop | Full exit — "Trail stop hit" |
| After TP1 — new trail (current − ATR × 1.0) > old trail | Update trailing stop |
| Otherwise | Hold |

---

### 3 — First Failed Follow-Through Exit

| Condition | Action |
|---|---|
| Price ≤ current stop | Full exit — "Stop hit" |
| UTC ≥ 20:45 | Full exit — EOD |
| Last 3 closes each lower than previous AND price < entry × 1.002 | Full exit — "Failed follow-through" |
| Otherwise | Hold |

---

### 4 — Time Stop Exit

| Condition | Action |
|---|---|
| Price ≤ current stop | Full exit — "Stop hit" |
| UTC ≥ 20:45 | Full exit — EOD |
| Hours held ≥ `max_hold_hours` AND price < entry × 1.003 | Full exit — "Time stop exceeded" |
| Otherwise | Hold |

---

### 5 — VWAP / Structure Loss Exit

| Condition | Action |
|---|---|
| Price ≤ current stop | Full exit — "Stop hit" |
| UTC ≥ 20:45 | Full exit — EOD |
| Price < min of last 10 lows (excl. current bar) × 0.998 | Full exit — "Structure support broken" |
| Otherwise | Hold |

---

### 6 — End-of-Day Exit

| Condition | Action |
|---|---|
| Price ≤ current stop | Full exit — "Stop hit" |
| UTC ≥ 20:45 | Full exit — "End-of-day exit — session closing" |
| Otherwise | Hold |

---

## Crypto Exit Strategies

**Source:** `backend/app/crypto/strategies/exit_strategies.py`
**Default:** Fixed Risk then Dynamic Protective Floor

### Exit Strategy Assignment

Frozen at position open based on the regime detected at entry time.

| Regime at entry | Assigned exit strategy |
|---|---|
| `trending_up` | Partial at TP1, Dynamic Trail on Runner |
| `ranging` | Range Failure Exit |
| `unknown` / other | Fixed Risk then Dynamic Protective Floor |

---

### 1 — Fixed Risk then Dynamic Protective Floor *(default)*

| Condition | Action |
|---|---|
| Price ≤ current stop | Full exit — "Stop hit" |
| Price ≥ TP1 (first time) | Promote stop to entry |
| After TP1 — price ≤ trailing floor | Full exit — "Trailing floor hit" |
| After TP1 — trending market — new floor (current − ATR × 1.5) > old floor | Raise floor |
| Otherwise | Hold |

---

### 2 — Partial at TP1, Dynamic Trail on Runner

| Condition | Action |
|---|---|
| Price ≤ current stop | Full exit — "Stop hit" |
| Price ≥ TP1 (first time) | Partial exit 50 %; stop moved to entry |
| After TP1 — price ≤ trailing stop | Full exit — "Trail stop hit" |
| After TP1 — trending market — new trail (current − ATR × 2.0) > old trail | Update trailing stop |
| Otherwise | Hold |

---

### 3 — Failed Follow-Through Exit

| Condition | Action |
|---|---|
| Price ≤ current stop | Full exit — "Stop hit" |
| Last 3 closes each lower than previous AND price < entry | Full exit — "Failed follow-through" |
| Otherwise | Hold |

---

### 4 — Range Failure Exit

| Condition | Action |
|---|---|
| Price ≤ current stop | Full exit — "Stop hit" |
| Price < min of last 10 lows (excl. current bar) × 0.995 | Full exit — "Range support failed" |
| Otherwise | Hold |

---

### 5 — Time Degradation Exit

| Condition | Action |
|---|---|
| Price ≤ current stop | Full exit — "Stop hit" |
| Hours held ≥ `max_hold_hours` AND price < entry × 1.005 | Full exit — "Max hold time exceeded" |
| Otherwise | Hold |

---

### 6 — Regime Breakdown Exit

| Condition | Action |
|---|---|
| Price ≤ current stop | Full exit — "Stop hit" |
| Entry regime was `trending_up` AND EMA20 < EMA50 × 0.99 (over 50 bars) | Full exit — "Regime flipped — trend broken" |
| Otherwise | Hold |

---

## Milestone State Reference

Both asset classes track intra-trade progress in `position.milestone_state` (JSON column).

| Key | Type | Set when |
|---|---|---|
| `tp1_hit` | `bool` | Price first reaches TP1 |
| `tp1_price` | `float` | Price recorded at TP1 touch |
| `be_promoted` | `bool` | Stop has been moved to break-even *(stocks only)* |
| `trailing_stop` | `float` | Current value of the active trailing stop or floor |