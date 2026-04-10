Absolutely. Here’s the **review checklist mapped to the exact files in this repo**, organized in the order I’d use for a full QA sweep. Think of it as a wiring diagram with a flashlight: each stop tells you **what to inspect**, **which files own it**, and **what counts as pass/fail**.

# Signal Forge QA Review Checklist

## 1. Project docs and intended behavior

### Files

* `ASSESSMENT_REPORT.md`
* `docs/readme.md`
* `docs/setup_instructions.md`
* `docs/Entry Strategies.md`
* `docs/exit_strategies.md`
* `ai_scripts/chatgpt_kraken_crypto.md`
* `ai_scripts/claude_tradier_stocks.md`
* `ai_scripts/schemas/watchlist_decision.schema.json`

### Checklist

* [ ] Confirm the stated system architecture matches the actual code layout
* [ ] Confirm stock and crypto flows are both documented
* [ ] Confirm entry strategy names and descriptions are precise enough to validate implementation
* [ ] Confirm exit strategy names and descriptions are precise enough to validate implementation
* [ ] Confirm watchlist schema fields match backend expectations
* [ ] Flag any docs that appear stale or contradicted by code

### Pass criteria

* Docs describe the same components, strategy intent, and trade lifecycle the code actually uses

### Fail signals

* Strategy names in docs do not match real behavior
* Watchlist schema implies fields the backend ignores or does not validate
* Docs describe routes, workers, or states not present in code

---

## 2. Environment, startup, and deployment wiring

### Files

* `.env.example`
* `docker-compose.yml`
* `backend/Dockerfile`
* `frontend/Dockerfile`
* `backend/requirements.txt`
* `frontend/package.json`
* `frontend/package-lock.json`
* `start.ps1`
* `stop.ps1`
* `backup.ps1`

### Checklist

* [ ] Confirm all required backend env vars are represented in `.env.example`
* [ ] Confirm Docker services and ports align with backend/frontend expectations
* [ ] Confirm backend dependencies cover imported packages
* [ ] Confirm frontend dependencies cover React/router/chart/UI usage
* [ ] Confirm start/stop scripts target the correct services
* [ ] Confirm backup script does not miss critical project files

### Pass criteria

* A fresh environment could boot without hidden dependency or config surprises

### Fail signals

* Missing env keys
* Script assumptions that differ from Docker setup
* Dependency drift between imports and declared packages

---

## 3. Backend application boot and router registration

### Files

* `backend/app/main.py`
* `backend/app/api/__init__.py`
* `backend/app/api/routes/__init__.py`
* `backend/app/api/deps.py`

### Checklist

* [ ] Confirm all intended API routers are registered
* [ ] Confirm startup logic initializes runtime services exactly once
* [ ] Confirm shutdown logic cleans up background tasks or sockets
* [ ] Confirm dependency helpers enforce auth/admin checks consistently
* [ ] Confirm there is no accidental double-start worker behavior

### Pass criteria

* App boot is deterministic, route exposure is correct, and background services are not duplicated

### Fail signals

* Missing route registration
* Worker loops started from multiple places
* Auth dependency inconsistencies between sensitive endpoints

---

## 4. Database, models, and migrations

### Files

* `backend/app/common/database.py`
* `backend/app/common/models/__init__.py`
* `backend/app/common/models/base.py`
* `backend/app/common/models/audit.py`
* `backend/app/common/models/ledger.py`
* `backend/app/common/models/order.py`
* `backend/app/common/models/position.py`
* `backend/app/common/models/watchlist.py`
* `backend/alembic.ini`
* `backend/alembic/env.py`
* `backend/alembic/script.py.mako`
* `backend/alembic/versions/0001_initial_schema.py`
* `backend/alembic/versions/0002_positions_composite_indexes.py`
* `backend/alembic/versions/0003_watchlist_symbols_composite_index.py`
* `backend/alembic/versions/0004_enum_columns_to_varchar.py`

### Checklist

* [ ] Confirm model fields match the intended trade lifecycle
* [ ] Confirm enums/status values are represented consistently in DB and code
* [ ] Confirm timestamps and symbol fields are sufficient for auditability
* [ ] Confirm position model can support open, partial, and closed lifecycle correctly
* [ ] Confirm migration history is coherent for fresh install and upgrade path
* [ ] Confirm composite indexes support the common query patterns
* [ ] Confirm no migration leaves schema partially incompatible with current models

### Pass criteria

* Schema cleanly supports watchlists, orders, positions, ledger, and audit trail without ambiguity

### Fail signals

* Status fields with overlapping meanings
* Missing indexes on core monitoring/position lookups
* Migration order or definitions that would break deploys

---

## 5. Shared backend services and runtime state

### Files

* `backend/app/common/config.py`
* `backend/app/common/runtime_state.py`
* `backend/app/common/redis_client.py`
* `backend/app/common/audit_logger.py`
* `backend/app/common/market_hours.py`
* `backend/app/common/ws_manager.py`

### Checklist

* [ ] Confirm configuration parsing is strict enough for trading-critical settings
* [ ] Confirm runtime state is centralized and not duplicated in ad hoc globals
* [ ] Confirm Redis usage is optional/required exactly as intended
* [ ] Confirm market-hours gating logic is correct and timezone-safe
* [ ] Confirm audit logging captures enough detail for decisions and transitions
* [ ] Confirm websocket manager handles client lifecycle cleanly

### Pass criteria

* Shared services behave as a single source of truth and do not create hidden state drift

### Fail signals

* Same state represented in multiple inconsistent places
* Weak config validation for trading thresholds or modes
* Market-hours logic vulnerable to timezone/date mistakes

---

## 6. Candle ingestion and storage integrity

### Files

* `backend/app/common/candle_store.py`
* `backend/app/crypto/candle_fetcher.py`
* `backend/app/stocks/candle_fetcher.py`
* `backend/app/crypto/kraken_client.py`
* `backend/app/stocks/tradier_client.py`

### Checklist

* [ ] Confirm candle fetchers request the correct timeframes
* [ ] Confirm candle normalization is consistent across stock and crypto
* [ ] Confirm partial/in-progress candles are excluded from strategy logic where required
* [ ] Confirm missing candles are handled safely and visibly
* [ ] Confirm symbol mapping is correct, especially Kraken pair normalization
* [ ] Confirm candle store does not silently mix old and fresh data

### Pass criteria

* Strategies can rely on candles as clean, timeframe-aligned, and closed when needed

### Fail signals

* Strategies can accidentally consume live candles
* Symbol alias issues can produce wrong market data
* Missing candle behavior degrades into fake setups

---

## 7. Watchlist ingestion and decision intake

### Files

* `backend/app/common/discord_listener.py`
* `backend/app/common/watchlist_engine.py`
* `backend/app/common/models/watchlist.py`
* `backend/app/api/routes/watchlist.py`
* `backend/app/api/schemas/watchlist.py`

### Checklist

* [ ] Confirm watchlist payload validation matches schema
* [ ] Confirm stock and crypto scopes are separated correctly
* [ ] Confirm watchlist ingestion does not accept malformed or incomplete decisions without warning
* [ ] Confirm confidence, symbol, reason, and tag fields survive intake correctly
* [ ] Confirm duplicate symbols or stale uploads are handled intentionally
* [ ] Confirm watchlist route responses reflect current DB truth

### Pass criteria

* Watchlist input enters the system cleanly and predictably, with no silent mutation of meaning

### Fail signals

* Schema accepts values the engine cannot use
* Duplicate or stale watchlists can override active logic unpredictably
* UI payload and backend payload drift apart

---

## 8. Stock entry strategy audit

### Files

* `backend/app/stocks/strategies/__init__.py`
* `backend/app/stocks/strategies/entry_strategies.py`
* `docs/Entry Strategies.md`
* `backend/tests/test_stocks_entry_strategies.py`

### Checklist

For **each stock strategy in `entry_strategies.py`**:

* [ ] Identify the strategy name and expected behavior from docs
* [ ] Confirm inputs come from completed candles, not in-progress price action unless explicitly intended
* [ ] Confirm trigger conditions match the strategy’s name
* [ ] Confirm rejection conditions are present and meaningful
* [ ] Confirm thresholds are not so loose that the strategy becomes a costume
* [ ] Confirm comments/logging describe the real reason for acceptance or rejection
* [ ] Confirm tests cover both valid and invalid cases

### Pass criteria

* Each stock strategy behaves like its documented name, using proper candle confirmation and sensible guards

### Fail signals

* Strategy label says one thing and code does another
* “Reclaim” without real reclaim structure
* “Breakout” with no extension or confirmation filter
* Tests only assert boolean output without validating the actual pattern logic

---

## 9. Crypto entry strategy audit

### Files

* `backend/app/crypto/strategies/__init__.py`
* `backend/app/crypto/strategies/entry_strategies.py`
* `docs/Entry Strategies.md`
* `backend/tests/test_crypto_entry_strategies.py`

### Checklist

For **each crypto strategy in `entry_strategies.py`**:

* [ ] Confirm strategy definition matches docs
* [ ] Confirm crypto-specific flexibility is intentional, not accidental looseness
* [ ] Confirm only closed candles are used where required
* [ ] Confirm momentum, pullback, reclaim, and mean-reversion logic are structurally valid
* [ ] Confirm support/resistance assumptions are actually encoded, not implied by naming
* [ ] Confirm rejection reasons are specific enough for operator debugging
* [ ] Confirm tests use realistic candle sequences

### Pass criteria

* Crypto strategy signals are consistent with their names and robust to noisy 24/7 data

### Fail signals

* Trend-only entries mislabeled as pullback reclaim
* Intrabar strength treated as closed-candle confirmation
* Overly permissive logic generating false positives

---

## 10. Regime classification and policy gating

### Files

* `backend/app/regime/__init__.py`
* `backend/app/regime/classifier.py`
* `backend/app/regime/engine.py`
* `backend/app/regime/indicators.py`
* `backend/app/regime/policy.py`
* `backend/tests/test_regime.py`

### Checklist

* [ ] Confirm regime inputs are derived consistently
* [ ] Confirm indicator calculations are stable and deterministic
* [ ] Confirm classification thresholds are sensible and documented
* [ ] Confirm policy layer correctly maps regimes to allowed/blocked behavior
* [ ] Confirm regime-at-entry tagging is based on the same logic shown elsewhere
* [ ] Confirm tests cover bull, neutral, bearish, and edge cases

### Pass criteria

* Regime labels are reproducible, meaningful, and used consistently across decision flow and display

### Fail signals

* Regime depends on mismatched timeframe/data
* Policy gates differ from displayed regime meaning
* Tests only cover happy-path examples

---

## 11. Stock monitoring flow

### Files

* `backend/app/stocks/monitoring.py`
* `backend/app/stocks/candle_fetcher.py`
* `backend/app/stocks/tradier_client.py`
* `backend/app/api/routes/monitoring.py`
* `backend/app/api/schemas/monitoring.py`

### Checklist

* [ ] Confirm monitoring state machine is explicit and understandable
* [ ] Confirm open-position guards prevent duplicate stock entries
* [ ] Confirm candidate review uses the right strategy and regime inputs
* [ ] Confirm readiness states shown to the UI map to actual execution readiness
* [ ] Confirm monitoring reads do not create write side effects unintentionally
* [ ] Confirm polling logic is safe for market-hours conditions

### Pass criteria

* Monitoring reflects actual stock entry readiness and never mutates state by accident during read operations

### Fail signals

* Read paths perform commits or broker sync unexpectedly
* Duplicate exposure possible
* UI badges simplify away important rejection reasons

---

## 12. Crypto monitoring flow

### Files

* `backend/app/crypto/monitoring.py`
* `backend/app/crypto/candle_fetcher.py`
* `backend/app/crypto/kraken_client.py`
* `backend/app/api/routes/monitoring.py`
* `backend/app/api/schemas/monitoring.py`

### Checklist

* [ ] Confirm crypto alias handling prevents duplicate positions across symbol variants
* [ ] Confirm open-position and active-intent guards work for Kraken pair names
* [ ] Confirm monitoring states distinguish healthy candidate from blocked or rejected candidate
* [ ] Confirm crypto monitoring uses correct 24/7 assumptions without leaking stock gating
* [ ] Confirm route payload exposes enough detail for UI diagnosis

### Pass criteria

* Crypto monitoring behaves consistently even with pair aliases and round-the-clock conditions

### Fail signals

* Alias mismatch allows duplicate entry
* Monitoring labels do not match real decision state
* Stock-only assumptions bleed into crypto flow

---

## 13. Stock exit logic and worker behavior

### Files

* `backend/app/stocks/strategies/exit_strategies.py`
* `backend/app/stocks/exit_worker.py`
* `backend/app/stocks/ledger.py`
* `docs/exit_strategies.md`
* `backend/tests/test_stocks_exit_strategies.py`

### Checklist

* [ ] Confirm each exit strategy matches its documented meaning
* [ ] Confirm stop, target, trailing, and failed-follow-through rules are mutually coherent
* [ ] Confirm exit worker is idempotent enough to avoid duplicate exits
* [ ] Confirm exit decisions use current persisted position truth
* [ ] Confirm stock market-hours gating blocks invalid exit attempts when required
* [ ] Confirm worker logging explains why a position was held or closed
* [ ] Confirm tests cover no-exit, valid-exit, and duplicate-risk scenarios

### Pass criteria

* Stock exits are deterministic, strategy-accurate, and operationally safe

### Fail signals

* Worker can submit duplicate sells
* Exit labels are vague while logic is complex
* Position state can be read differently by worker and UI

---

## 14. Crypto exit logic and worker behavior

### Files

* `backend/app/crypto/strategies/exit_strategies.py`
* `backend/app/crypto/exit_worker.py`
* `backend/app/crypto/ledger.py`
* `docs/exit_strategies.md`
* `backend/tests/test_crypto_exit_strategies.py`

### Checklist

* [ ] Confirm crypto exit templates match documentation
* [ ] Confirm runner protection, break-even promotion, and failed-follow-through rules are encoded clearly
* [ ] Confirm live position management does not drift unintentionally
* [ ] Confirm worker reads persisted state first where relevant
* [ ] Confirm fee assumptions do not distort break-even logic
* [ ] Confirm crypto exits are 24/7 safe and do not depend on stock session logic
* [ ] Confirm tests cover promoted protection and trailing transitions

### Pass criteria

* Crypto exits preserve earned protection correctly and behave consistently across restarts and re-evaluations

### Fail signals

* Exit management resets to initial risk
* Read-path recomputation overrides persisted progress
* UI and worker disagree on active protection mode

---

## 15. Paper ledger, order lifecycle, and accounting correctness

### Files

* `backend/app/common/paper_ledger.py`
* `backend/app/common/models/ledger.py`
* `backend/app/common/models/order.py`
* `backend/app/common/models/position.py`
* `backend/app/common/models/audit.py`
* `backend/app/stocks/ledger.py`
* `backend/app/crypto/ledger.py`
* `backend/app/api/routes/ledger.py`
* `backend/app/api/routes/trades.py`
* `backend/app/api/routes/positions.py`
* `backend/app/api/routes/audit.py`
* `backend/app/api/schemas/ledger.py`
* `backend/app/api/schemas/order.py`
* `backend/app/api/schemas/position.py`
* `backend/app/api/schemas/audit.py`

### Checklist

* [ ] Confirm order creation, fill recording, and position updates are coherent
* [ ] Confirm average cost, realized PnL, and remaining quantity math are correct
* [ ] Confirm partial exits do not corrupt position truth
* [ ] Confirm position close logic is precise and leaves no ghost balance
* [ ] Confirm audit events map clearly to trade actions
* [ ] Confirm ledger routes return values that match internal calculations
* [ ] Confirm stock and crypto ledger behavior is intentionally similar or intentionally different

### Pass criteria

* The system can explain every position and trade numerically from audit trail to ledger to UI

### Fail signals

* Quantity drift
* Position and ledger disagree
* Closed trade still appears operationally open
* PnL math differs between backend layers

---

## 16. Runtime controls and operator safeguards

### Files

* `backend/app/api/routes/runtime.py`
* `backend/app/api/schemas/runtime.py`
* `backend/app/common/runtime_state.py`
* `backend/app/api/deps.py`
* `frontend/src/components/GlobalKillSwitch.tsx`
* `frontend/src/pages/RuntimeRisk.tsx`

### Checklist

* [ ] Confirm runtime toggle endpoints are properly guarded
* [ ] Confirm kill switch state is authoritative and immediate
* [ ] Confirm frontend reflects backend runtime truth without stale assumptions
* [ ] Confirm runtime mode changes do not bypass safety checks
* [ ] Confirm operational risk states are displayed clearly

### Pass criteria

* Operator controls are secure, trustworthy, and instantly reflected in backend and UI

### Fail signals

* Frontend optimistically displays control changes that backend did not persist
* Kill switch UI and backend state can diverge
* Sensitive endpoints lack consistent admin enforcement

---

## 17. Dashboard and summary APIs

### Files

* `backend/app/api/routes/dashboard.py`
* `backend/app/api/schemas/dashboard.py`
* `frontend/src/pages/Dashboard.tsx`
* `frontend/src/components/MetricCard.tsx`
* `frontend/src/components/MarketStatusBadge.tsx`

### Checklist

* [ ] Confirm dashboard metrics are derived from authoritative backend data
* [ ] Confirm market status labels use correct session logic
* [ ] Confirm summary cards do not double-count or omit open/closed items
* [ ] Confirm frontend formatting does not hide dangerous state

### Pass criteria

* Dashboard acts like an accurate cockpit, not decorative wallpaper

### Fail signals

* Summary numbers disagree with positions/ledger pages
* Market status badge misstates availability or session condition
* UI labels oversimplify risk state

---

## 18. Positions API and positions page truthfulness

### Files

* `backend/app/api/routes/positions.py`
* `backend/app/api/schemas/position.py`
* `frontend/src/pages/Positions.tsx`

### Checklist

* [ ] Confirm positions route returns all fields needed by operator decisions
* [ ] Confirm lifecycle state shown in UI matches backend state definitions
* [ ] Confirm exit strategy/protection/regime fields display the real persisted truth
* [ ] Confirm open positions update cleanly after fill, close, or cancellation
* [ ] Confirm inspect data is not being reinterpreted incorrectly in frontend

### Pass criteria

* The positions page tells the same story as the backend state and worker logic

### Fail signals

* Position page recomputes state differently than backend
* Exit management display lags or lies
* Closed/canceled positions linger incorrectly

---

## 19. Monitoring page and operator diagnosis flow

### Files

* `backend/app/api/routes/monitoring.py`
* `backend/app/api/schemas/monitoring.py`
* `frontend/src/pages/Monitoring.tsx`
* `frontend/src/components/StatusBadge.tsx`

### Checklist

* [ ] Confirm monitoring row statuses map directly to backend states
* [ ] Confirm rejection reasons are displayed fully enough to debug
* [ ] Confirm jump-lane or review labels are not purely cosmetic
* [ ] Confirm polling and refresh patterns do not cause stale diagnosis
* [ ] Confirm filters and derived groupings do not alter underlying meaning

### Pass criteria

* Operator can tell why something is blocked, waiting, healthy, or open without guessing

### Fail signals

* Badge language is too vague
* Rejection reason truncated into uselessness
* Monitoring state names differ between backend and frontend semantics

---

## 20. Watchlist page integrity

### Files

* `backend/app/api/routes/watchlist.py`
* `backend/app/api/schemas/watchlist.py`
* `frontend/src/pages/Watchlist.tsx`

### Checklist

* [ ] Confirm latest and active watchlist data are displayed accurately
* [ ] Confirm stock/crypto scope views are correct
* [ ] Confirm watchlist reasons, confidence, and tags survive serialization intact
* [ ] Confirm stale watchlists are visibly distinguishable

### Pass criteria

* Watchlist page faithfully reflects uploaded decisions and current activation state

### Fail signals

* Fields silently dropped or reformatted into ambiguity
* Scope confusion between stock and crypto
* Old watchlists presented as current truth

---

## 21. Ledger, trade history, and audit trail pages

### Files

* `frontend/src/pages/Ledger.tsx`
* `frontend/src/pages/TradeHistory.tsx`
* `frontend/src/pages/AuditTrail.tsx`
* `backend/app/api/routes/ledger.py`
* `backend/app/api/routes/trades.py`
* `backend/app/api/routes/audit.py`

### Checklist

* [ ] Confirm table columns map exactly to backend fields
* [ ] Confirm sorting and formatting preserve numeric precision where needed
* [ ] Confirm timestamps display consistently
* [ ] Confirm audit events are understandable in operator language
* [ ] Confirm crypto precision is not inappropriately rounded away
* [ ] Confirm exports, if any, retain correct values

### Pass criteria

* Ledger, trades, and audit pages are numerically faithful and explain system actions clearly

### Fail signals

* Precision clipping
* Timestamp inconsistency
* Audit rows too vague to reconstruct decisions

---

## 22. WebSocket and live update behavior

### Files

* `backend/app/api/routes/ws.py`
* `backend/app/common/ws_manager.py`
* `frontend/src/providers/WebSocketProvider.tsx`

### Checklist

* [ ] Confirm websocket route registration and connection handling work
* [ ] Confirm broadcast payloads are shaped consistently
* [ ] Confirm frontend handles reconnects safely
* [ ] Confirm websocket updates do not conflict with polling refresh logic
* [ ] Confirm stale subscriptions are cleaned up

### Pass criteria

* Live updates improve UI freshness without causing duplicate or contradictory state

### Fail signals

* Race between websocket and polling updates
* Connection leaks
* Frontend assumes payload shape not guaranteed by backend

---

## 23. Frontend shell, layout, navigation, and shared API layer

### Files

* `frontend/src/App.tsx`
* `frontend/src/main.tsx`
* `frontend/src/api/client.ts`
* `frontend/src/api/endpoints.ts`
* `frontend/src/api/types.ts`
* `frontend/src/components/Layout.tsx`
* `frontend/src/components/Sidebar.tsx`
* `frontend/src/components/CommandPalette.tsx`
* `frontend/src/utils/time.ts`
* `frontend/src/index.css`

### Checklist

* [ ] Confirm navigation links map to actual pages
* [ ] Confirm shared API methods and types match backend responses
* [ ] Confirm time utilities use a consistent timezone/display convention
* [ ] Confirm layout does not hide important status content on common screen sizes
* [ ] Confirm command palette actions are safe and accurate

### Pass criteria

* Frontend shell is type-safe, navigable, and consistent with backend contracts

### Fail signals

* Type layer too thin to catch payload drift
* Inconsistent time formatting across pages
* Layout or navigation causing operator blind spots

---

## 24. Backend API route coverage and schema consistency

### Files

* `backend/app/api/routes/audit.py`
* `backend/app/api/routes/dashboard.py`
* `backend/app/api/routes/ledger.py`
* `backend/app/api/routes/monitoring.py`
* `backend/app/api/routes/positions.py`
* `backend/app/api/routes/runtime.py`
* `backend/app/api/routes/trades.py`
* `backend/app/api/routes/watchlist.py`
* `backend/app/api/routes/ws.py`
* `backend/app/api/schemas/audit.py`
* `backend/app/api/schemas/dashboard.py`
* `backend/app/api/schemas/ledger.py`
* `backend/app/api/schemas/monitoring.py`
* `backend/app/api/schemas/order.py`
* `backend/app/api/schemas/position.py`
* `backend/app/api/schemas/runtime.py`
* `backend/app/api/schemas/watchlist.py`

### Checklist

* [ ] Confirm every route returns data consistent with its declared schema
* [ ] Confirm optional fields are genuinely optional
* [ ] Confirm naming conventions are consistent across schemas
* [ ] Confirm HTTP status and error behavior are sensible
* [ ] Confirm routes do not leak internals better kept server-side

### Pass criteria

* API contracts are stable enough that frontend logic can remain thin and trustworthy

### Fail signals

* Schemas lag behind actual responses
* Inconsistent field names for same concept
* Route returns `null` or ad hoc shapes outside schema intent

---

## 25. Automated test adequacy

### Files

* `backend/tests/__init__.py`
* `backend/tests/conftest.py`
* `backend/tests/test_api_routes.py`
* `backend/tests/test_crypto_entry_strategies.py`
* `backend/tests/test_crypto_exit_strategies.py`
* `backend/tests/test_regime.py`
* `backend/tests/test_stocks_entry_strategies.py`
* `backend/tests/test_stocks_exit_strategies.py`
* `backend/pytest.ini`

### Checklist

* [ ] Confirm each critical subsystem has tests
* [ ] Confirm tests validate strategy behavior, not just function return type
* [ ] Confirm candle fixtures represent completed candles realistically
* [ ] Confirm route tests cover success and failure/auth cases
* [ ] Confirm regime tests cover edge and threshold boundaries
* [ ] Confirm exit tests include no-action and duplicate-risk cases
* [ ] Identify missing tests for monitoring, watchlist ingestion, ledger, websocket, and persistence drift

### Pass criteria

* Tests defend the system’s actual trading risks, not just surface syntax

### Fail signals

* Missing tests for watchlist-to-execution flow
* Weak strategy tests
* No regression tests around state drift, alias matching, or duplicate order prevention

---

# High-priority vertical review slices

These are the three “don’t get lost in the attic” walkthroughs I’d run first.

## Slice A: Can the bot enter when it should not?

### Files

* `backend/app/common/watchlist_engine.py`
* `backend/app/common/discord_listener.py`
* `backend/app/stocks/monitoring.py`
* `backend/app/crypto/monitoring.py`
* `backend/app/stocks/strategies/entry_strategies.py`
* `backend/app/crypto/strategies/entry_strategies.py`
* `backend/app/regime/engine.py`
* `backend/app/regime/policy.py`
* `backend/app/common/paper_ledger.py`
* `backend/app/common/models/order.py`
* `backend/app/common/models/position.py`

### Checks

* [ ] Watchlist input valid
* [ ] Candidate state valid
* [ ] Strategy valid
* [ ] Regime permission valid
* [ ] Duplicate position prevented
* [ ] Order/position creation correct

---

## Slice B: Can the bot fail to exit, or exit twice?

### Files

* `backend/app/stocks/exit_worker.py`
* `backend/app/crypto/exit_worker.py`
* `backend/app/stocks/strategies/exit_strategies.py`
* `backend/app/crypto/strategies/exit_strategies.py`
* `backend/app/stocks/ledger.py`
* `backend/app/crypto/ledger.py`
* `backend/app/common/models/order.py`
* `backend/app/common/models/position.py`
* `frontend/src/pages/Positions.tsx`

### Checks

* [ ] Open position read is authoritative
* [ ] Exit policy is stable
* [ ] Exit trigger evaluation is correct
* [ ] Duplicate exit blocked
* [ ] Position updates correctly after close
* [ ] UI reflects post-exit truth

---

## Slice C: Can the UI lie to the operator?

### Files

* `backend/app/api/routes/monitoring.py`
* `backend/app/api/routes/positions.py`
* `backend/app/api/routes/runtime.py`
* `backend/app/api/routes/dashboard.py`
* `frontend/src/api/endpoints.ts`
* `frontend/src/api/types.ts`
* `frontend/src/pages/Dashboard.tsx`
* `frontend/src/pages/Monitoring.tsx`
* `frontend/src/pages/Positions.tsx`
* `frontend/src/pages/RuntimeRisk.tsx`
* `frontend/src/components/StatusBadge.tsx`
* `frontend/src/components/MarketStatusBadge.tsx`

### Checks

* [ ] Badge/state names mean the same thing backend and frontend
* [ ] Position protection state shown is real
* [ ] Runtime risk state shown is real
* [ ] Dashboard summary matches underlying pages
* [ ] Rejection reasons survive backend-to-UI translation intact

---

# Suggested review worksheet format

Use this format for each file or subsystem you review:

**File:**
**Subsystem:**
**Expected role:**
**Actual role observed:**
**Key inputs:**
**Key outputs:**
**Invariants that must hold:**
**Pass/Fail:**
**Findings:**
**Severity:** Critical / High / Medium / Low
**Recommended fix:**
**Tests needed:**

---

# Fastest review order for this exact repo

1. `docs/Entry Strategies.md`
2. `docs/exit_strategies.md`
3. `backend/app/stocks/strategies/entry_strategies.py`
4. `backend/app/crypto/strategies/entry_strategies.py`
5. `backend/app/regime/*`
6. `backend/app/stocks/monitoring.py`
7. `backend/app/crypto/monitoring.py`
8. `backend/app/stocks/exit_worker.py`
9. `backend/app/crypto/exit_worker.py`
10. `backend/app/common/paper_ledger.py` and model files
11. `backend/app/api/routes/*` + schemas
12. `frontend/src/pages/Monitoring.tsx`
13. `frontend/src/pages/Positions.tsx`
14. `frontend/src/pages/Dashboard.tsx`
15. backend tests

That order gets you to the sharp edges first, where bugs usually wear expensive shoes.

If you want, I can next turn this into a **fillable pass/fail QA template** you can reuse during the actual review.
