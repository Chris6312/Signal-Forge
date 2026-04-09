# AI Multi-Asset Trading Bot (Name: Signal Forge)

A modern **crypto + stock trading system** with AI-driven watchlists, asset-specific strategies, regime-aware exits, and internally controlled ledgers.

The system separates concerns cleanly across **crypto**, **stocks**, and **shared infrastructure**, ensuring maintainability, auditability, and consistent behavior across restarts, code updates, and watchlist changes.

---

# Core Concept

The bot operates like a disciplined trading desk:

AI produces trade ideas → posts watchlist to Discord → bot validates and activates watchlist → strategies evaluate → trades execute through live brokers → exits are managed by frozen policy → internal ledgers track financial truth → frontend provides full visibility.

---

# Key Capabilities

• Supports **crypto and stocks simultaneously**
• Uses **Kraken** for crypto execution
• Uses **Tradier** for stock execution
• Maintains internal ledgers for each asset class
• Uses **AI-generated watchlists delivered via Discord**
• Watchlist updates automatically replace previous symbols
• Symbols removed from watchlist remain **managed** if a position is open
• No watchlist expiry timer
• Entry and exit strategies are **asset-specific**
• Trailing stop or protective floor activates dynamically based on regime
• All live position policies remain **frozen at entry**
• Fully auditable order lifecycle
• Designed for Docker deployment

---

# Technology Stack

Backend

* Python
* FastAPI
* PostgreSQL
* Redis
* SQLAlchemy
* Alembic

Frontend

* React
* TypeScript
* Vite

Infrastructure

* Docker
* Docker Compose

Brokers

* Kraken (crypto)
* Tradier (stocks)

Messaging

* Discord (AI watchlist delivery)

---

# System Architecture

```
backend/
    common/
    crypto/
    stocks/

frontend/

postgresql
redis
```

The backend is intentionally split into domains to prevent strategy logic from bleeding across asset classes.

---

# Ports

This bot avoids ports used by other systems.

| Service     | Port |
| ----------- | ---- |
| Backend API | 8100 |
| Frontend    | 5180 |
| PostgreSQL  | 5442 |
| Redis       | 6389 |

Docker internal ports remain standard (5432, 6379).

---

# Environment Variables

Example root `.env`

```
APP_NAME=AI_MULTI_ASSET_BOT

APP_PORT=8100
FRONTEND_PORT=5180

DATABASE_URL=postgresql://bot_user:changeme@postgres:5432/ai_multiasset_bot
REDIS_URL=redis://redis:6379/0

POSTGRES_DB=ai_multiasset_bot
POSTGRES_USER=bot_user
POSTGRES_PASSWORD=changeme

TIMEZONE=America/New_York

DISCORD_BOT_TOKEN=
DISCORD_TRADING_CHANNEL_ID=0
DISCORD_USER_ID=0
DISCORD_ALLOWED_ROLE_IDS=
DISCORD_DECISION_MAX_AGE_SECONDS=900
DISCORD_REQUIRE_DECISION_TIMESTAMP=true

KRAKEN_API_KEY=
KRAKEN_API_SECRET=

TRADIER_ACCESS_TOKEN=
TRADIER_ACCOUNT_ID=

ADMIN_API_TOKEN=
```

---

# Watchlist Lifecycle

Watchlists originate from AI and are delivered via Discord as JSON.

There is no expiration timer for watchlists.

The latest valid watchlist replaces the previous one.

## Replacement Behavior

When a new watchlist arrives:

### symbols added

Begin monitoring for new entries.

### symbols still present

Continue monitoring normally.

### symbols removed

Removed from active watchlist.

If an open position exists:

symbol is moved to **managed state**

Managed symbols:

* continue exit monitoring
* preserve frozen strategy
* preserve milestone state
* remain visible in positions page
* are not eligible for new entries

Once position closes:
symbol is removed completely unless reintroduced in a future watchlist.

---

# Symbol States

ACTIVE
Symbol is present in latest watchlist.

Eligible for:

* entry evaluation
* strategy selection
* monitoring updates

MANAGED
Symbol removed from watchlist but still has open position.

Eligible for:

* exit monitoring
* milestone updates
* reconciliation

Not eligible for:

* new entries
* new strategy selection

INACTIVE
Symbol not present in watchlist and no open position.

---

# Strategy Framework

Strategies are defined separately for stocks and crypto.

No shared one-size-fits-all strategy logic.

---

# Stock Entry Strategies

Opening Range Breakout
Break above opening range high with confirmation.

Pullback Reclaim
Retracement into support followed by reclaim.

Trend Continuation Ladder
Continuation pattern within established trend.

Mean Reversion Bounce
Oversold bounce from extension.

Failed Breakdown Reclaim
False breakdown followed by strong reclaim.

Volatility Compression Breakout
Breakout from tightening range.

---

# Crypto Entry Strategies

Momentum Breakout Continuation
Break above resistance in trending market.

Pullback Reclaim
Trend pullback followed by reclaim.

Mean Reversion Bounce
Oversold bounce from extension.

Range Rotation Reversal
Reversal from established range support.

Breakout Retest Hold
Breakout followed by successful retest.

Failed Breakdown Reclaim
False breakdown followed by reclaim.

---

# Stock Exit Strategies

Fixed Risk then Break-Even Promotion
Stop moves to break-even after threshold achieved.

Partial at TP1, Trail Remainder
Take partial profit then trail runner.

First Failed Follow-Through Exit
Exit when expected continuation fails.

Time Stop Exit
Exit if trade fails to progress in expected time.

VWAP / Structure Loss Exit
Exit when support level breaks.

End-of-Day Exit
Exit intraday positions before session close.

---

# Crypto Exit Strategies

Fixed Risk then Dynamic Protective Floor
Protective floor rises as milestones are achieved.

Partial at TP1, Dynamic Trail on Runner
Partial profit then adaptive trailing.

Failed Follow-Through Exit
Exit when momentum fails.

Range Failure Exit
Exit when range support fails.

Time Degradation Exit
Exit when expected move does not begin.

Regime Breakdown Exit
Exit when trend regime weakens.

---

# Regime-Aware Trailing Logic

Trailing stops and protective floors activate dynamically.

Trailing is not always active.

### trailing activates when:

trend regime is strong
momentum persists
milestone state promoted

### trailing remains inactive when:

range regime active
mean reversion setup
low conviction environment

Crypto typically allows wider structural tolerance than stocks.

---

# Frozen Position Policy

Once a trade is entered, the following are persisted:

entry strategy
exit strategy
management policy version
initial stop
profit target
max hold hours
regime at entry
watchlist source id

Future watchlists cannot overwrite these values.

Milestones modify protection but never replace core policy.

---

# Internal Ledgers

Separate ledgers exist for:

crypto
stocks

Ledgers track:

cash balance
fills
fees
realized pnl
unrealized pnl
adjustments
reconciliation differences

Internal ledger is the operational financial truth.

Broker state is reconciled but does not override ledger logic silently.

---

# Backend Structure

```
backend/app/

common/
    config
    audit logging
    runtime state
    redis coordination
    shared models
    watchlist lifecycle engine

crypto/
    kraken integration
    crypto strategies
    crypto ledger
    crypto monitoring
    crypto exit worker

stocks/
    tradier integration
    stock strategies
    stock ledger
    stock monitoring
    stock exit worker
```

---

# Frontend Pages

Dashboard
System health, PnL summary, runtime state.

Watchlist
Active symbols, watchlist history, JSON viewer.

Monitoring
Strategy evaluation, candidate ranking, entry readiness.

Positions
Open positions, policy details, milestone state.

Paper Ledger
Internal ledger balances and adjustments.

Trade History
Closed trades and exports.

Audit Trail
System events and order lifecycle history.

Runtime & Risk
System controls and safety configuration.

---

# Runtime Workers

Watchlist listener
Stock monitoring loop
Crypto monitoring loop
Stock exit worker
Crypto exit worker
Broker reconciliation worker
Heartbeat worker

---

# Design Principles

Asset-specific strategy logic
Frozen live trade policy
Managed symbols persist until exit completes
No watchlist expiry
Internal ledger as primary financial truth
Reconciliation does not mutate state silently
Regime-aware exit logic
Clear audit trail for all decisions

---

# Intended Outcome

A system that:

adapts intelligently before entry
remains consistent after entry
maintains clear audit history
separates crypto and stock logic cleanly
supports AI-generated watchlists
survives restarts and code updates without losing trade context

---

If needed, the next document can define:

database schema
docker compose configuration
phase checklist
API contract definitions
