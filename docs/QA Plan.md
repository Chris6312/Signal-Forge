Here’s a practical QA review plan for this codebase, tuned to the project structure in your zip. Think of it like sweeping a trading floor from the breaker box outward: first confirm the building won’t catch fire, then inspect the strategy brains, then verify the operator glass cockpit.

## Review goal

Analyze the algo trading system section by section to answer four things:

1. Does each area do what its name and docs imply?
2. Are there logic flaws that could trigger bad trades, stale state, or false UI signals?
3. Are backend and frontend telling the same story?
4. Are tests actually guarding the important behaviors, or just wearing hard hats for decoration?

---

# Section-by-section review plan

## Phase 0. Establish the source of truth

### Files to review first

* `docs/readme.md`
* `docs/Entry Strategies.md`
* `docs/exit_strategies.md`
* `ASSESSMENT_REPORT.md`
* `docker-compose.yml`
* `backend/requirements.txt`
* `frontend/package.json`

### What to check

* Intended architecture and trade lifecycle
* Supported brokers/data sources
* Strategy definitions versus implementation targets
* Runtime services expected to be always-on
* Any mismatch between docs and actual code layout

### Output

* “Expected system behavior” summary
* “Potential stale docs” list

---

## Phase 1. Application boot and wiring

### Backend files

* `backend/app/main.py`
* `backend/app/api/routes/__init__.py`
* `backend/app/api/deps.py`
* `backend/app/common/config.py`
* `backend/app/common/database.py`
* `backend/app/common/runtime_state.py`
* `backend/app/common/redis_client.py`

### Review focus

* Startup/shutdown flow
* Dependency injection and config loading
* Router registration
* Whether critical services initialize safely
* Whether background workers can run twice, not run at all, or run with partial state

### Key QA questions

* Can the app boot with invalid or missing config without failing loudly?
* Are runtime flags and control states centralized or scattered?
* Are there hidden globals that could drift between requests or worker loops?

### Output

* Boot/wiring risk list
* Config and state-management concerns

---

## Phase 2. Data model, persistence, and migration safety

### Files

* `backend/app/common/models/*`
* `backend/alembic/env.py`
* `backend/alembic/versions/*`

### Review focus

* Position, order, watchlist, and audit schemas
* Whether models match API expectations
* Alembic safety and upgrade consistency
* Whether live trade state can survive restarts and reconciliation

### Key QA questions

* Are IDs, enums, timestamps, and status fields consistent?
* Can position state become ambiguous?
* Are migrations likely to break fresh installs or upgrades?

### Output

* Persistence integrity findings
* Migration-risk findings

---

## Phase 3. Market data and candle integrity

### Files

* `backend/app/common/candle_store.py`
* `backend/app/crypto/candle_fetcher.py`
* `backend/app/stocks/candle_fetcher.py`
* `backend/app/crypto/kraken_client.py`
* `backend/app/stocks/tradier_client.py`

### Review focus

* Candle sourcing and normalization
* Closed-candle versus live-candle handling
* Timeframe alignment
* Symbol mapping
* Missing/partial candle behavior

### Key QA questions

* Are strategies evaluating only closed candles where required?
* Are candles aligned correctly for 15m, 1h, 4h, daily?
* Can missing candles silently produce fake signals?

### Output

* Data quality and timing findings
* Symbol/timeframe consistency findings

---

## Phase 4. Strategy engine review: stocks and crypto entry logic

### Files

* `backend/app/stocks/strategies/entry_strategies.py`
* `backend/app/crypto/strategies/entry_strategies.py`
* `docs/Entry Strategies.md`

### Review focus

Review strategy by strategy, not just file by file.

For each strategy:

* Stated purpose
* Required inputs
* Actual trigger conditions
* Rejection conditions
* Use of candle close versus intrabar values
* Whether the strategy behavior matches its name

### Suggested method

For each strategy, create a mini QA card:

* **Strategy name**
* **Expected behavior**
* **Actual implemented behavior**
* **Mismatch**
* **Risk**
* **Recommended fix**

### Key QA questions

* Is “pullback reclaim” truly a reclaim, or just price-above-something theater?
* Are breakout strategies checking extension too late?
* Are mean-reversion signals based on real reversal structure or thin proxies?
* Are stock and crypto variants intentionally different, or accidentally inconsistent?

### Output

* Entry strategy audit matrix
* Severity-ranked strategy defects

---

## Phase 5. Exit logic and position management

### Files

* `backend/app/stocks/strategies/exit_strategies.py`
* `backend/app/crypto/strategies/exit_strategies.py`
* `backend/app/stocks/exit_worker.py`
* `backend/app/crypto/exit_worker.py`
* `docs/exit_strategies.md`

### Review focus

* Stop logic
* Target logic
* Trailing logic
* Failed-follow-through logic
* Holding-period logic
* Whether live position rules remain stable after entry

### Key QA questions

* Can an exit policy drift after the trade opens?
* Are exits using stale or inconsistent state?
* Are worker decisions idempotent, or can duplicate exits occur?
* Does the UI show the same protection state the worker is using?

### Output

* Exit consistency report
* Live-position management risk report

---

## Phase 6. Regime engine and market-state classification

### Files

* `backend/app/regime/classifier.py`
* `backend/app/regime/engine.py`
* `backend/app/regime/indicators.py`
* `backend/app/regime/policy.py`

### Review focus

* Regime inputs and thresholds
* Whether regime is calculated deterministically
* Whether entry decisions and displayed regime align
* Whether regime affects both stocks and crypto correctly

### Key QA questions

* Is regime based on the same timeframe/data source the UI implies?
* Is the label stable or jittery because of noisy inputs?
* Can the system tag a trade with the wrong regime at entry?

### Output

* Regime accuracy assessment
* Entry-tagging consistency findings

---

## Phase 7. Watchlist intake and monitoring flow

### Files

* `backend/app/common/watchlist_engine.py`
* `backend/app/common/discord_listener.py`
* `backend/app/common/models/watchlist.py`
* `backend/app/api/routes/watchlist.py`
* `backend/app/api/routes/monitoring.py`
* `backend/app/stocks/monitoring.py`
* `backend/app/crypto/monitoring.py`

### Review focus

* Watchlist ingestion
* Monitoring lifecycle
* Candidate filtering
* Duplicate prevention
* Status transitions

### Key QA questions

* Can symbols re-enter when already open?
* Can aliasing cause duplicate crypto exposure?
* Are monitoring states truthy or ornamental?
* Do monitoring routes read safely, or do they trigger side effects?

### Output

* Watchlist-to-monitoring flow map
* State-machine defect list

---

## Phase 8. Ledger, orders, audit trail, and reconciliation

### Files

* `backend/app/common/paper_ledger.py`
* `backend/app/common/models/ledger.py`
* `backend/app/common/models/order.py`
* `backend/app/common/models/position.py`
* `backend/app/common/models/audit.py`
* `backend/app/api/routes/ledger.py`
* `backend/app/api/routes/audit.py`
* `backend/app/api/routes/positions.py`
* `backend/app/api/routes/trades.py`
* `backend/app/stocks/ledger.py`
* `backend/app/crypto/ledger.py`

### Review focus

* Order intent to fill to position lifecycle
* Quantity, average price, realized PnL, remaining quantity
* Paper ledger correctness
* Audit trail completeness
* Position reconciliation logic

### Key QA questions

* Can quantities drift after partial fills or multiple exits?
* Can a position appear open in one area and closed in another?
* Is the audit trail complete enough to explain why a trade happened?

### Output

* Trade lifecycle correctness report
* Reconciliation and accounting defects

---

## Phase 9. API contract validation

### Files

* `backend/app/api/routes/*`
* `backend/app/api/schemas/*`

### Review focus

* Route-to-schema consistency
* Error handling
* Null safety
* Field naming consistency
* Whether frontend assumptions match backend response shape

### Key QA questions

* Are schema fields optional because they truly are, or because things are leaking?
* Do route names and payloads stay consistent across pages?
* Are internal-only fields accidentally exposed?

### Output

* API mismatch list
* Frontend break-risk list

---

## Phase 10. Frontend architecture and operator UI truthfulness

### Files

* `frontend/src/App.tsx`
* `frontend/src/api/*`
* `frontend/src/pages/*`
* `frontend/src/components/*`
* `frontend/src/providers/WebSocketProvider.tsx`

### Review focus

* Page-to-endpoint mapping
* State loading patterns
* Polling/WebSocket updates
* Badge/status logic
* Whether the UI tells the operational truth or just a pretty bedtime story

### Suggested page order

1. `Dashboard.tsx`
2. `Monitoring.tsx`
3. `Positions.tsx`
4. `TradeHistory.tsx`
5. `Ledger.tsx`
6. `AuditTrail.tsx`
7. `RuntimeRisk.tsx`
8. `Watchlist.tsx`

### Key QA questions

* Are labels like “Healthy”, “Waiting For Setup”, “Open”, or “Managed” derived correctly?
* Does the inspect path use persisted backend state first?
* Are there duplicated calculations in frontend that should come from backend?

### Output

* UI truthfulness report
* Backend/frontend contract drift report

---

## Phase 11. Test suite reliability review

### Files

* `backend/tests/*`

### Review focus

* Coverage across strategies, exits, regime, API routes
* Whether tests use realistic candle sequences
* Whether important failure paths are missing
* Whether tests validate namesake strategy behavior rather than just any boolean result

### Key QA questions

* Do tests enforce closed-candle logic?
* Are stock and crypto strategy tests symmetrical where they should be?
* Are edge cases covered: missing candles, duplicate orders, alias symbols, stale watchlists, partial exits?

### Output

* Test adequacy report
* Missing regression tests list

---

# Recommended review order

Use this order so the puzzle pieces click instead of fighting each other:

1. Docs and architecture
2. App boot/config/runtime
3. Models and migrations
4. Candle/data pipeline
5. Entry strategies
6. Exit strategies
7. Regime logic
8. Monitoring and watchlist flow
9. Ledger/orders/audit/reconciliation
10. API schemas and routes
11. Frontend pages and state flow
12. Tests and coverage gaps

That order keeps you from judging a strategy before you know whether its candles are clean, which is how QA turns into interpretive dance.

---

# How to analyze each section

For every file or subsystem, use the same rubric:

## A. Purpose

What is this section supposed to do?

## B. Inputs

What data does it depend on?

## C. Outputs

What does it return, persist, emit, or display?

## D. Invariants

What must always remain true?

Examples:

* positions never go negative unless shorting exists
* entry logic must use closed candles only
* live position exit policy should not mutate unintentionally
* UI status must reflect backend truth

## E. Failure modes

What are the most likely ways this can break?

## F. Evidence

Which lines/files/tests prove the intended behavior?

## G. Severity

Classify findings as:

* Critical: can cause bad trades, duplicate orders, incorrect exits, or position corruption
* High: misleading UI, incorrect regime/strategy labeling, stale state
* Medium: maintainability, inconsistent naming, brittle branching
* Low: cleanup, readability, technical debt

---

# Deliverables to produce during the review

I’d structure findings into these buckets:

## 1. Architecture findings

* config/runtime/worker issues
* state ownership problems
* persistence/reconciliation risks

## 2. Strategy findings

* per-strategy mismatch vs description
* closed-candle violations
* bad threshold logic
* naming mismatch

## 3. API/UI findings

* mismatched fields
* misleading badges
* stale or recomputed status problems

## 4. Test findings

* missing tests
* unrealistic fixtures
* false-confidence tests

## 5. Recommended fixes

* immediate safety fixes
* next regression tests
* later refactors

---

# Best-practice review worksheet

For each strategy or subsystem, capture findings in this format:

**Section:** `crypto/strategies/entry_strategies.py`
**Component:** `pullback_reclaim`
**Expected:** Requires pullback into support, confirmed reclaim, trend alignment, closed candle confirmation
**Observed:** Logic only checks close above moving average and recent strength, no true reclaim sequence
**Risk:** False-positive momentum entries labeled as pullback reclaim
**Severity:** High
**Fix:** Require prior pullback, reclaim close above reference level, and invalidation floor from closed candles
**Tests needed:** one valid reclaim case, one momentum-only false-positive case, one intrabar-only fake reclaim case

---

# Time-saving review tactic

Don’t review linearly like a novel. Review in vertical slices for high-risk behavior:

## Slice 1: “Can it buy when it shouldn’t?”

Trace:

* watchlist input
* monitor state
* candle fetch
* strategy evaluation
* regime gate
* order creation
* position open

## Slice 2: “Can it fail to exit or exit twice?”

Trace:

* open position
* exit policy
* worker loop
* order intent
* ledger update
* UI display

## Slice 3: “Can the UI lie?”

Trace:

* backend model/state
* API schema
* route payload
* frontend type
* badge/label rendering

That gets you to the juicy defects sooner.

---

# Suggested final report structure

When you finish the review, organize it like this:

## Executive Summary

* overall system health
* biggest trading-risk issues
* biggest UI/operational-risk issues

## Detailed Findings

* Backend architecture
* Market data/candles
* Stocks entry strategies
* Crypto entry strategies
* Stocks exit logic
* Crypto exit logic
* Regime engine
* Watchlist/monitoring
* Ledger/audit/reconciliation
* API contracts
* Frontend/operator UI
* Tests

## Priority Fix Queue

* P0: safety-critical
* P1: correctness
* P2: resilience
* P3: cleanup

## Regression Test Additions

* exact new tests needed before sign-off

---

I can turn this into a concrete review checklist mapped to the exact files in this repo, with pass/fail criteria for each section.
