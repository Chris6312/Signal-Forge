Here’s **Part 1 through Part 3** of the QA review, mapped to the current repo state and treating outdated docs as advisory, not gospel.

# QA Review

## Scope covered

* Part 1: Project docs and intended behavior
* Part 2: Environment, startup, and deployment wiring
* Part 3: Backend application boot and router registration

---

# Part 1. Project docs and intended behavior

## Overall verdict

**Partial pass.** The docs still describe the project’s broad shape correctly, but several files are stale enough to be risky if used as the source of truth.

## What still lines up

* The repo is clearly structured as a split backend/frontend system with separate stock, crypto, and shared backend domains, which matches `docs/readme.md` lines 68 to 82 and the actual folder layout.
* The readme’s core flow is directionally correct: AI watchlists come through Discord, strategies evaluate, ledgers track state, and the frontend provides visibility. That is consistent with `docs/readme.md` lines 9 to 31.
* The watchlist lifecycle and symbol-state language in `docs/readme.md` lines 138 to 205 is coherent with the architecture direction of the codebase.

## Stale or unreliable docs

### 1. `ASSESSMENT_REPORT.md` is no longer trustworthy as a current-state report

This file is explicitly dated **June 2025** at lines 3 to 5, and several of its “critical findings” have already been fixed in code.

Examples:

* It warns about wildcard CORS in `backend/app/main.py`, but current code uses `settings.ALLOWED_ORIGINS` in `backend/app/main.py` lines 217 to 223.
* It warns about string inequality for admin token comparison, but current code uses `hmac.compare_digest` in `backend/app/api/deps.py` lines 14 to 16.
* It warns about `--reload` in the backend Dockerfile, but current `backend/Dockerfile` line 17 uses `--workers 1`.

**QA call:** keep this file as historical context only. Do not use it as an active defect list.

### 2. `docs/setup_instructions.md` has a migration-head mismatch

The setup doc says the expected head is `0003_watchlist_symbols_composite_index` at lines 174 to 189, but the repo includes `backend/alembic/versions/0004_enum_columns_to_varchar.py`.

**QA call:** this is a concrete stale-doc defect. Anyone following the doc literally could think migrations are out of sync when they are not.

### 3. `docs/setup_instructions.md` is written for generic bash-style usage, not the preferred project workflow

It uses `cp`, `curl`, and generic shell examples at lines 19 to 32 and 208 to 217. That is not wrong, but it drifts from the project’s current Windows/PowerShell-first workflow.

**QA call:** medium severity for onboarding friction, low severity for runtime correctness.

### 4. `.env.example` is missing a now-active config key

`backend/app/common/config.py` lines 36 to 42 defines `ALLOWED_ORIGINS`, but `.env.example` lines 1 to 28 does not document it.

**QA call:** this is a live config-doc mismatch, not just stale prose.

## Pass/fail checklist

* [x] Repo architecture is described in a way that still matches current structure
* [x] High-level trading flow is still directionally accurate
* [ ] Assessment report is current
* [ ] Setup instructions reflect current migration state
* [ ] Environment docs fully reflect active config
* [ ] Docs reflect current project workflow conventions

## Part 1 findings

### High

* **`ASSESSMENT_REPORT.md` is stale and includes already-fixed defects**
* **`docs/setup_instructions.md` still points users to migration head `0003` while repo has `0004`**

### Medium

* **`.env.example` and setup docs do not include `ALLOWED_ORIGINS`**
* **Setup instructions are not aligned to the current PowerShell-first workflow**

### Low

* Some docs still read like platform-agnostic setup notes rather than current project operating instructions

---

# Part 2. Environment, startup, and deployment wiring

## Overall verdict

**Mostly pass for local/dev deployment. Partial fail for production-grade deployment hygiene.**

This wiring is solid enough to boot the stack, but it still has a few dev-leaning edges.

## What looks good

### Docker Compose structure is coherent

`docker-compose.yml` lines 3 to 64 defines four services:

* `postgres`
* `redis`
* `backend`
* `frontend`

This aligns with the documented architecture and port model.

### Service dependency order is sensible

The backend waits on healthy Postgres and Redis in `docker-compose.yml` lines 44 to 48.

### Backend container wiring is straightforward

* `backend/Dockerfile` uses Python 3.11 slim and installs requirements cleanly at lines 1 to 13.
* It exposes port 8100 and runs `uvicorn` on `app.main:app` with one worker at lines 15 to 17.

### Startup script is thoughtfully defensive

`start.ps1`:

* checks Docker availability first at lines 14 to 38
* brings up containers with build at lines 40 to 45
* waits for service health at lines 47 to 62
* runs Alembic migrations automatically at lines 64 to 72
* opens log tabs in Windows Terminal if available at lines 74 to 103

That is a pretty nice little launch runway. Fewer rakes in the grass.

## Wiring concerns

### 1. Frontend container is running the Vite dev server, not a production build

`frontend/Dockerfile` line 7 runs:

```text
npm run dev
```

and `frontend/package.json` line 7 defines that as:

```text
vite --port 5180 --host
```

That is fine for local development, but not ideal for an actual deployment target.

**Risk:** production-like environments may be using a dev server, which is slower, noisier, and less controlled than a built static frontend served by nginx or similar.

### 2. `docker-compose.yml` mounts the entire frontend source tree into the container

`docker-compose.yml` lines 59 to 61 mount:

* `./frontend:/app`
* `/app/node_modules`

That is normal for dev hot-reload, but it reinforces that this setup is dev-first, not hardened deployment-first.

### 3. `.env.example` is incomplete relative to active settings

As noted above, `ALLOWED_ORIGINS` exists in config but is undocumented in `.env.example`.

### 4. Health-check logic in `start.ps1` is broad rather than precise

At lines 47 to 62, the script treats the stack as healthy if `docker compose ps` output does not match `starting|unhealthy|restarting|exited`.

That works, but it is text-pattern health, not service-by-service verification.

**Risk:** a service could be present but not truly ready for user workflows.

### 5. Backend requirements include test-only tooling in the runtime requirements file

`backend/requirements.txt` line 16 includes `pytest==9.0.3`.

Not harmful, but it muddies the line between runtime and dev/test dependencies.

## Pass/fail checklist

* [x] Docker services are defined consistently with the repo architecture
* [x] Backend waits for DB and Redis health
* [x] Startup script covers bring-up, health wait, and migrations
* [x] Ports are internally consistent
* [ ] `.env.example` fully reflects active config
* [ ] Frontend deployment path is production-grade
* [ ] Startup health checks are precise enough for strong operational confidence

## Part 2 findings

### Medium

* **Frontend container uses Vite dev server instead of a production build**
* **Frontend compose config is clearly dev-oriented because it bind-mounts source**
* **Missing `ALLOWED_ORIGINS` in `.env.example`**

### Low

* `pytest` is bundled into runtime requirements
* `start.ps1` health detection is pragmatic but imprecise

---

# Part 3. Backend application boot and router registration

## Overall verdict

**Pass with caution.** The backend boot path is coherent, routers are registered correctly, and lifecycle startup/shutdown is thoughtfully structured. The main caution is around background worker management and cleanup discipline.

## What looks good

### 1. Router registration is complete and explicit

`backend/app/main.py` lines 225 to 233 include routers for:

* dashboard
* watchlist
* monitoring
* positions
* ledger
* trades
* audit
* runtime
* ws

That matches `backend/app/api/routes/__init__.py` lines 1 to 3.

### 2. Health endpoint exists and is simple

`backend/app/main.py` lines 236 to 238 exposes `/health`, which is useful for container checks and startup validation.

### 3. Lifespan startup is organized in the right order

In `backend/app/main.py` lines 151 to 191:

* app start logs
* DB init runs
* runtime state initializes
* websocket manager stores the main loop
* background workers are started
* main async tasks are scheduled

That ordering makes sense.

### 4. CORS is no longer hardcoded dangerously

`backend/app/main.py` lines 217 to 223 uses `settings.ALLOWED_ORIGINS`, which is materially better than the stale assessment report suggests.

### 5. Admin token comparison is implemented correctly

`backend/app/api/deps.py` lines 14 to 16 uses `hmac.compare_digest`, which is the right move.

## Boot-path and lifecycle concerns

### 1. Worker startup failures are softened into warnings

In `backend/app/main.py`:

* Discord listener startup failures become warnings at lines 161 to 168
* worker startup failures become warnings at lines 169 to 185

This keeps the app alive, which may be desirable, but it also means the API can look “up” while critical trading workers are missing.

**Risk:** false-green application state.

### 2. Background worker lifecycle cleanup is incomplete for Redis

The app initializes Redis-backed runtime state, but I do not see `close_redis()` called during shutdown. `backend/app/common/redis_client.py` defines `close_redis()` at lines 24 to 28, but `backend/app/main.py` shutdown path at lines 199 to 207 does not call it.

**Risk:** low to medium. Usually tolerated on process shutdown, but it is still incomplete resource cleanup.

### 3. `get_db()` commits on normal dependency exit

`backend/app/common/database.py` lines 34 to 43 auto-commit after yielding the session.

That pattern can work, but it means route handlers may commit implicitly just by completing, even for flows where the caller may not expect a write boundary there.

**Risk:** medium architectural caution, especially in a system where read/write side effects matter.

### 4. `_WorkerThread.start()` waits for start, not for healthy readiness

`backend/app/main.py` lines 39 to 45 waits on an event for up to 5 seconds. That tells us the thread entered `_run()`, not that the worker itself is operational.

**Risk:** an almost-booted worker can still look “started.”

### 5. Runtime state initialization resets operational fields at boot

`backend/app/common/runtime_state.py` lines 29 to 39 resets boot-time worker fields to `"idle"` and writes `"started_at"` fresh each startup.

This may be intended, but it means runtime status is ephemeral and boot-based, not historical.

## Pass/fail checklist

* [x] Main FastAPI app boots with coherent lifespan management
* [x] Router registration appears complete
* [x] CORS config is explicit and config-driven
* [x] Health endpoint exists
* [x] Admin dependency uses constant-time token comparison
* [ ] Worker startup guarantees operational readiness
* [ ] Shutdown path fully cleans up shared resources
* [ ] DB dependency pattern clearly separates read-only and write-intent flows

## Part 3 findings

### Medium

* **Worker startup errors are downgraded to warnings, so the app can appear healthy while trading workers are absent**
* **Redis client cleanup exists but is not used during shutdown**
* **Database dependency auto-commits on normal completion, which may blur transaction boundaries**

### Low

* Worker “started” does not necessarily mean worker “ready”
* Runtime worker-state boot values are ephemeral by design, which may reduce forensic clarity

---

# Summary of Parts 1 to 3

## Strong areas

* Current backend boot path is organized and readable
* Router registration is clean
* CORS and admin-token handling have already been improved beyond the old assessment report
* Docker and PowerShell startup wiring is practical and mostly solid for local operation

## Main issues found

1. **Docs are partially stale**

   * stale assessment report
   * stale migration head in setup instructions
   * missing `ALLOWED_ORIGINS` from env docs

2. **Deployment posture is still dev-leaning**

   * frontend runs Vite dev server in container
   * compose/frontend wiring is local-dev style

3. **Backend lifecycle is sound but not fully hardened**

   * worker failures can leave a deceptively healthy app
   * Redis shutdown cleanup is incomplete
   * DB session dependency auto-commits by default

## Recommended priority

### Fix next

* Update `docs/setup_instructions.md` for Alembic head and current workflow
* Update `.env.example` and docs to include `ALLOWED_ORIGINS`
* Mark `ASSESSMENT_REPORT.md` as historical or regenerate it
* Decide whether frontend container is intended for dev only or real deployment
* Consider surfacing worker readiness more explicitly than “warning and continue”

Continuing with **Part 4** and **Part 5**. I treated the current code as the source of truth and the docs as a weather report from last week when they conflicted.

# QA Review

## Scope covered

* Part 4: Database, models, and migrations
* Part 5: Shared backend services and runtime state

---

# Part 4. Database, models, and migrations

## Overall verdict

**Partial pass.** The schema is coherent for a lean paper-trading system, and the migration chain is orderly. The main weaknesses are around precision, lifecycle richness, and a few places where the persistence model is thinner than the operational complexity implied by the rest of the app.

## What looks good

### 1. Migration chain is clean and linear

The Alembic chain is simple and readable:

* `0001_initial_schema.py` creates the core tables
* `0002_positions_composite_indexes.py` adds position lookup indexes
* `0003_watchlist_symbols_composite_index.py` adds a watchlist state index
* `0004_enum_columns_to_varchar.py` converts enum-backed columns to varchar for asyncpg compatibility

That is a tidy little staircase, not a trapdoor maze. The revision chain in `backend/alembic/env.py` is wired correctly, and the versions folder is internally consistent.

### 2. Current models and migrations broadly match

The runtime models in:

* `backend/app/common/models/watchlist.py`
* `position.py`
* `order.py`
* `ledger.py`
* `audit.py`

line up with the base table structure created in `0001_initial_schema.py`, plus the added indexes in `0002` and `0003`, and the enum-column conversion in `0004`.

### 3. Core indexes target the hot paths

The added indexes are sensible:

* `positions(asset_class, state)` for open-position counts and broad worker scans
* `positions(symbol, asset_class, state)` for duplicate-entry/open-position checks
* `watchlist_symbols(asset_class, state)` for monitor-cycle symbol loading

That covers the obvious trading-lane lookups without getting overly clever.

### 4. Position model includes frozen-policy concepts

`backend/app/common/models/position.py` includes:

* `entry_strategy`
* `exit_strategy`
* `initial_stop`
* `profit_target_1`
* `profit_target_2`
* `max_hold_hours`
* `regime_at_entry`
* `watchlist_source_id`
* `management_policy_version`
* `frozen_policy`
* `milestone_state`

This is a strong design direction for sticky live-position behavior. The schema is at least trying to remember what the position earned, instead of reimagining it every refresh like an unreliable narrator.

## Main concerns

### 1. Monetary and quantity fields use `Float`

Across the models, the system uses `Float` for cash, quantity, fees, prices, and PnL:

* `backend/app/common/models/position.py`
* `backend/app/common/models/order.py`
* `backend/app/common/models/ledger.py`

For algo trading, especially crypto, this is a medium-to-high risk design choice. Floating point can introduce subtle rounding drift in:

* average cost
* partial exits
* realized PnL
* fees
* ledger balances

It may behave fine in many happy paths, but over time this can turn pennies into gremlins.

**QA call:** medium severity right now, but this becomes high if the system does a lot of partials, fee-aware exits, or high-precision crypto sizes.

### 2. Position lifecycle is minimal

`PositionState` only has:

* `PENDING`
* `OPEN`
* `CLOSED`

That is clean, but thin. The broader system seems to care about richer operational states like:

* exit pending
* partially exited
* reconcile-needed
* broker drift / mismatch
* operator intervention states

Those states may exist elsewhere in runtime logic or UI derivation, but they are not first-class in persistence.

**Risk:** operational ambiguity. A position can be “OPEN” while the system is actually in a more delicate transitional state.

### 3. Watchlist persistence is symbol-centric, not upload-centric

`backend/app/common/models/watchlist.py` has a single `WatchlistSymbol` table with:

* symbol
* asset_class
* state
* watchlist_source_id
* notes
* timestamps

That is enough for the current flow, but it is thinner than the docs imply. There is no first-class table here for a watchlist upload/header entity or raw decision payload history.

**Risk:** weaker auditability of “which uploaded watchlist caused which lifecycle transition,” especially once multiple uploads and replacements happen.

### 4. Orders model may be too simple for broker-reconciliation realism

The `Order` model includes:

* requested/fill price
* quantity
* status
* broker_order_id
* fees
* notes

Useful, but it does not natively model:

* multiple fills
* partial fill quantities vs remaining quantity
* submitted/cancel timestamps beyond placed/filled
* richer broker execution metadata

The enum includes `PARTIALLY_FILLED`, but the table itself does not have explicit fill breakdown fields. That means partials are status-shaped, not data-rich.

### 5. Alembic env imports models manually

`backend/alembic/env.py` explicitly imports every model module to populate metadata. That works, but it is brittle. If a future model is added and not imported there, migrations can drift silently.

Not a current bug, just a maintenance tripwire.

### 6. `0004_enum_columns_to_varchar.py` is pragmatic, but worth watching

The migration converts enum columns to varchar and drops native enum types. This is reasonable for asyncpg compatibility and avoids type codec pain, but it also means DB-level enum enforcement is gone.

Application-level enums still exist, but the database becomes more permissive.

**Risk:** if bad strings get written through ad hoc scripts or a bug, the DB will not stop them.

## Pass/fail checklist

* [x] Core schema supports watchlists, positions, orders, ledger, and audit
* [x] Migration chain is clean and sequential
* [x] Key indexes exist for common monitoring/open-position queries
* [x] Position schema includes frozen-policy and milestone concepts
* [ ] Monetary/quantity precision is robust enough for trading-grade accounting
* [ ] Persistence model fully captures richer live trade lifecycle states
* [ ] Watchlist provenance is rich enough for deep audit/replay
* [ ] Order model is detailed enough for realistic partial-fill reconciliation
* [ ] Alembic model discovery is resilient to future model additions
* [ ] Database still enforces enum-like integrity after varchar conversion

## Part 4 findings

### High

* None yet from structure alone

### Medium

* **Use of `Float` across prices, quantities, balances, fees, and PnL can create precision drift**
* **Position lifecycle persistence is thinner than likely operational needs**
* **Order model has only light support for partial-fill realism**
* **DB enum columns were relaxed to varchar, reducing database-side value enforcement**

### Low

* `env.py` requires manual model imports, which is maintenance-fragile
* Watchlist persistence is functional but thinner than full provenance/audit workflows may want

---

# Part 5. Shared backend services and runtime state

## Overall verdict

**Pass with a few sharp corners.** The shared service layer is thoughtfully designed and shows clear intent around thread-safety, ET market hours, runtime controls, and websocket broadcasting. The main risks are startup/reset semantics, incomplete cleanup, and a few spots where the code’s comments and actual behavior drift slightly apart.

## What looks good

### 1. Config is centralized and readable

`backend/app/common/config.py` is clean and predictable. Important operational values live in one place:

* ports
* DB/Redis URLs
* Discord settings
* broker credentials
* admin token
* monitor intervals
* timezone
* allowed origins

That is good scaffolding.

### 2. Runtime state moved to Redis hash storage

`backend/app/common/runtime_state.py` uses a Redis hash instead of a read-modify-write JSON blob. That is a good design choice because worker threads updating separate fields do not stomp on each other.

The comments are accurate in spirit here: this removes a classic shared-state banana peel.

### 3. Redis client design acknowledges thread/event-loop reality

`backend/app/common/redis_client.py` uses thread-local storage so each OS thread gets its own asyncio Redis client. That aligns with the project’s worker-thread model and avoids cross-loop resource sharing headaches.

### 4. Audit logger is simple and useful

`backend/app/common/audit_logger.py` writes audit events through the DB session and logs an INFO line. It is not fancy, but it is clear and serviceable.

### 5. Market-hours logic is explicit and ET-based

`backend/app/common/market_hours.py` is one of the stronger shared modules.

Good points:

* uses `ZoneInfo("America/New_York")`
* explicitly models trading day vs session window
* includes holiday logic
* separates `pre_market`, `open`, `eod`, and `closed`

This is exactly the kind of utility that should be boring and correct. Boring is a compliment here.

### 6. WebSocket manager is appropriately lightweight

`backend/app/common/ws_manager.py` is small, understandable, and supports:

* client connect/disconnect
* async broadcast
* thread-safe broadcast onto the main loop

That fits the app well.

## Main concerns

### 1. Runtime initialization resets worker fields on every boot

`backend/app/common/runtime_state.py` reinitializes these fields at startup:

* `status`
* `started_at`
* `crypto_monitor`
* `stock_monitor`
* `crypto_exit_worker`
* `stock_exit_worker`
* `discord_listener`

That may be intentional, but it means worker operational state is boot-ephemeral, not persisted. If the system crashes and comes back, historical runtime truth is replaced by a fresh coat of paint.

**Risk:** weaker forensic clarity and more “looks healthy after reboot” ambiguity.

### 2. Config validation is light

`backend/app/common/config.py` stores many critical values, but there is little visible validation beyond type casting. For example:

* no obvious guardrails on interval values
* no validation that `ALLOWED_ORIGINS` is well-formed in `.env`
* no sanity constraints on ports or risk-like config

This is not broken, but for a trading system, config should ideally fail loudly when nonsense sneaks in.

### 3. Redis client cleanup exists, but lifecycle integration is incomplete

`close_redis()` exists in `backend/app/common/redis_client.py`, which is good, but from the earlier boot review it is not being used on shutdown.

So the cleanup broom is hanging on the wall, still in its plastic wrap.

### 4. Market-hours docstring and implementation slightly disagree

At the top of `market_hours.py`, the header comment says:

* `pre_market   08:30 – 09:30 ET`

The public API docstring inside `market_status()` says:

* `"closed" Non-trading day, or before 09:15 / after 16:00 ET`
* `"pre_market" 09:15–09:30 ET`

But the actual `_PREP_START` constant is `08:30`, and the implementation uses that.

So the code behavior is 08:30 to 09:30 ET for pre-market prep, while one docstring still says 09:15. That is a documentation inconsistency inside the code itself.

### 5. WebSocket manager has no explicit backpressure or payload guard

`ws_manager.py` broadcasts JSON payloads to all connected clients and drops dead ones, which is fine for this scale. But there is no rate limiting, payload size guard, or queueing strategy.

Not a present bug, just a scale/ruggedness note.

### 6. Audit logger trusts `position_id` shape

`audit_logger.py` does `uuid.UUID(position_id)` when `position_id` is provided. If an invalid string slips through, that raises immediately.

That may be acceptable and even desirable, but it means audit logging can fail hard on malformed IDs unless callers are disciplined.

## Pass/fail checklist

* [x] Config is centralized and easy to reason about
* [x] Runtime state storage avoids read-modify-write races
* [x] Redis client design respects thread/event-loop boundaries
* [x] Audit logging is straightforward and useful
* [x] Market-hours logic is ET-based and operationally clear
* [x] WebSocket manager supports basic live-update needs cleanly
* [ ] Config validation is strong enough for trading-critical settings
* [ ] Runtime state preserves enough history for operational forensics
* [ ] Redis lifecycle cleanup is fully integrated
* [ ] Internal documentation in market-hours matches actual code behavior
* [ ] Shared broadcast layer has resilience features beyond basic happy path

## Part 5 findings

### Medium

* **Runtime state boot initialization resets operational worker fields every startup**
* **Config validation is fairly light for a trading system**
* **Redis cleanup helper exists but is not fully integrated into app shutdown**
* **`market_hours.py` contains an internal doc inconsistency about pre-market start time**

### Low

* WebSocket manager is fine for current scale but lightly armored
* Audit logger will raise on malformed `position_id`, which is okay if intentional

---

# Summary of Parts 4 and 5

## Strong areas

* Migration chain is clean
* Core schema is coherent
* Position model is headed in the right direction for frozen policy and milestone persistence
* Runtime state architecture is improved by Redis hash usage
* Market-hours utility is one of the cleaner modules in the repo
* Shared service layer is mostly readable and sensible

## Main issues found

1. **Precision risk in persistence**

   * widespread use of `Float` for trading/accounting values

2. **Lifecycle richness is thinner than likely operational needs**

   * minimal persisted position state
   * limited partial-fill detail
   * thin watchlist provenance

3. **Shared service hardening is incomplete**

   * boot-reset runtime fields
   * incomplete Redis shutdown cleanup
   * light config validation

4. **Minor code/docs drift inside shared utilities**

   * `market_hours.py` comments disagree with implementation

## Recommended priority

### Fix next

* Consider migrating price/quantity/ledger math to `Decimal`/numeric storage
* Decide whether richer position/order lifecycle persistence is needed now or later
* Add stronger config validation for critical settings
* Wire Redis cleanup into shutdown
* Clean up `market_hours.py` internal documentation so it says exactly what the code does

Continuing with **Part 6** and **Part 7**. I treated the code as the source of truth and looked for the places where candle integrity or watchlist intake could quietly smuggle bad decisions into the bot.

# QA Review

## Scope covered

* Part 6: Candle ingestion and storage integrity
* Part 7: Watchlist ingestion and decision intake

---

# Part 6. Candle ingestion and storage integrity

## Overall verdict

**Partial pass.** The candle pipeline shows strong intent around closed-candle discipline and refresh timing, especially with the 20-second post-close gate. The main weaknesses are timestamp assumptions, incomplete completeness checks, and a couple of places where freshness can look healthier than it really is.

## What looks good

### 1. The shared candle cache has a sane refresh gate

`backend/app/common/candle_store.py` is one of the better pieces in this lane.

Good points:

* unified timeframe map in `TF_MINUTES`
* explicit `FETCH_OFFSET_SECONDS = 20`
* `needs_refresh()` waits until a candle has been closed for at least 20 seconds
* cache is keyed by `(symbol, interval_minutes)`
* access is guarded with an `asyncio.Lock` during updates

That is a proper “closed bar first” posture instead of sprinting at half-built candles with scissors.

### 2. Crypto fetcher explicitly drops incomplete OHLCV bars

`backend/app/crypto/candle_fetcher.py` has `_drop_incomplete_ohlcv()`, which removes the most recent bar if its open time plus interval length extends past current UTC time.

That is exactly the kind of guard you want when pulling from Kraken OHLC.

### 3. Stock fetcher also drops incomplete intraday timesales

`backend/app/stocks/candle_fetcher.py` has `_drop_incomplete_timesales()` and parses timestamps into UTC before checking whether the latest bar is still in progress.

That keeps intraday stock logic aligned with the closed-candle requirement.

### 4. Stock candle normalization is consistent

The stock fetcher normalizes both:

* timesales
* daily history

into a common dict shape:

* `time`
* `open`
* `high`
* `low`
* `close`
* `volume`

That reduces strategy-layer shape chaos.

### 5. Lookback sizing is intentionally generous

The stock fetcher uses:

* 3 days for 1m
* 5 days for 5m
* 10 days for 15m
* 150 days for daily

and the comments explain the goal is to guarantee enough bars despite weekends and holidays. That matches the current project intent much better than naive “N calendar days equals N sessions” logic.

## Main concerns

### 1. `CandleStore.update()` stamps fetch-time close, not source-data close

In `backend/app/common/candle_store.py`, `update()` sets:

* `now_ts = datetime.now(timezone.utc).timestamp()`
* `last_close_ts = (now_ts // iv_sec) * iv_sec`

So the cache records the **current expected bar-close boundary**, not the actual close timestamp of the newest candle returned by the provider.

Why that matters:

* if the provider lags or returns stale data, the store can still mark the frame as freshly updated
* `needs_refresh()` then compares against this synthetic timestamp and may decide no refresh is needed yet

**Risk:** false freshness. The cache can look current even if the latest returned candle was not.

This is the sharpest issue in Part 6.

### 2. CandleStore does not validate candle count or continuity

`CandleStore` stores whatever list it is given if non-empty. It does not check:

* minimum required bar count
* duplicate timestamps
* missing intervals
* sorted order
* timestamp continuity

That means upstream fetchers are trusted almost completely.

**Risk:** strategy layers may get enough bars numerically but not structurally.

### 3. Stock daily candles are not checked for incompleteness

`backend/app/stocks/candle_fetcher.py` drops incomplete intraday timesales, but daily history is returned directly from `_normalize_history(raw)` with no equivalent daily completeness check.

This may be okay if Tradier daily history only returns completed days during market hours, but the code itself does not enforce that assumption.

**Risk:** possible same-day daily-bar contamination if the provider includes the current session’s still-forming day.

### 4. Crypto fetcher depends on Kraken pair naming being correct upstream

`backend/app/crypto/candle_fetcher.py` passes the symbol directly into `kraken_client.get_ohlcv(symbol, interval=interval)`.

The fetcher itself does not normalize pair aliases. If the wrong display symbol versus Kraken-native pair leaks in upstream, this file will just trust it.

This may be handled elsewhere in the stack, but within Part 6 the candle fetch path itself is not self-defensive.

### 5. Tradier client uses `session_filter=open` for intraday timesales

`backend/app/stocks/tradier_client.py` requests timesales with:

* `session_filter: open`

That is likely intentional for regular-hours logic, but it means:

* no premarket candles
* no after-hours candles

If any strategy or monitoring assumption later expects broader session context, it will not exist here.

Not a bug by itself, but it should be treated as a hard behavioral contract.

### 6. Fetchers log warnings and continue on failures

Both stock and crypto candle fetchers catch exceptions per timeframe and continue.

This is practical, but it means a symbol may wind up partially populated:

* one timeframe refreshed
* another stale
* no explicit completeness summary returned

**Risk:** partial data health can be hidden unless downstream code checks it carefully.

### 7. No obvious candle-specific regression tests

From the current test suite snapshot, there do not appear to be dedicated tests covering:

* `CandleStore.needs_refresh()`
* incomplete-candle dropping
* stock timestamp parsing
* stale-provider-return scenarios
* symbol/timeframe continuity

That leaves this layer somewhat under-armored.

## Pass/fail checklist

* [x] Shared candle cache exists and uses a post-close refresh gate
* [x] Crypto fetcher drops incomplete latest bars
* [x] Stock intraday fetcher drops incomplete latest bars
* [x] Stock candles are normalized into a common schema
* [x] Lookback windows are intentionally sized for enough bars
* [ ] Cache freshness reflects actual latest candle returned by the provider
* [ ] Candle cache validates minimum count/order/continuity
* [ ] Stock daily-bar completeness is explicitly enforced
* [ ] Candle fetch path is self-defensive against symbol alias misuse
* [ ] Partial timeframe refresh failures are surfaced strongly enough
* [ ] Candle-layer regression tests meaningfully cover timing/integrity risks

## Part 6 findings

### High

* **`CandleStore.update()` records synthetic fetch-time close boundaries instead of the true close time of the latest returned candle, which can create false freshness**

### Medium

* **No validation of candle continuity, duplicate timestamps, or minimum-count sufficiency in the shared store**
* **Stock daily history path does not explicitly guard against incomplete current-day bars**
* **Fetchers tolerate per-timeframe failure without strongly surfacing partial-population risk**
* **Crypto candle fetch path assumes symbol normalization was already handled elsewhere**

### Low

* Stock intraday data is regular-session only because of `session_filter=open`; that is fine if intentional, but it needs to stay explicit
* Candle-layer tests appear thin relative to the importance of this subsystem

---

# Part 7. Watchlist ingestion and decision intake

## Overall verdict

**Pass with caution.** The watchlist intake path is clean, pragmatic, and better than many systems that let JSON tumble in like loose gravel. The main risks are that payload richness is largely discarded, source/provenance handling is thin, and symbol normalization is less rigorous than it should be for a trading intake boundary.

## What looks good

### 1. Discord listener has real authorization checks

`backend/app/common/discord_listener.py` rejects all messages unless the sender matches:

* `DISCORD_USER_ID`, or
* one of `DISCORD_ALLOWED_ROLE_IDS`

That is good. It avoids “anyone who can type JSON gets a watchlist runway.”

### 2. Payload extraction supports both message text and JSON attachment

The listener:

* tries inline content first
* then iterates attachments and attempts JSON parsing

That is flexible and operator-friendly.

### 3. Validation catches the most important structural issues

`_validate_payload()` checks:

* payload is an object
* top-level `asset_class` is valid if present
* timestamp is present and fresh if timestamp enforcement is enabled
* `symbols` or legacy `watchlist` exists
* symbols is a non-empty array
* each item is an object
* each item has `symbol`
* each item resolves to valid `asset_class`

That is a sensible intake gate.

### 4. Backward compatibility is intentionally handled

The system accepts both:

* `symbols`
* legacy `watchlist`

and the Pydantic schema in `backend/app/api/schemas/watchlist.py` also normalizes:

* `symbols` → `watchlist`
* `source` → `source_id`

That is neat and helpful.

### 5. Asset-class-scoped updates avoid cross-asset collateral damage

`backend/app/common/watchlist_engine.py` only touches symbols whose asset class appears in the incoming update.

So a stock-only upload does not accidentally deactivate crypto symbols, and vice versa. Good boundary discipline.

### 6. MANAGED versus INACTIVE handling is thoughtful

When a symbol disappears from the incoming watchlist:

* if it still has an open position, it becomes `MANAGED`
* otherwise it becomes `INACTIVE`

That is a smart operational distinction. It keeps open positions from falling through a trapdoor just because a fresh watchlist stopped mentioning them.

### 7. Audit events are emitted for meaningful watchlist transitions

The engine logs:

* `WATCHLIST_SYMBOL_MANAGED`
* `WATCHLIST_SYMBOL_REMOVED`
* `WATCHLIST_UPDATED`
* `WATCHLIST_SYMBOL_RELEASED`

That gives the intake flow at least a decent breadcrumb trail.

## Main concerns

### 1. Most of the AI decision payload is discarded

The intake path only really uses:

* `symbol`
* `asset_class`
* source/message ID

But watchlist decisions often contain richer fields like:

* `reason`
* `confidence`
* `tags`
* `price_at_decision`
* timestamp context
* narrative/catalyst details

Those fields are validated loosely at best and then mostly vanish.

This is a major correctness and auditability loss because the front end and later reviews may care deeply about **why** a symbol was selected, not just that it was selected.

### 2. `source` from the payload is not persisted as the actual source ID in Discord intake

In `_handle_message()`:

* `source = payload.get("source", "unknown")`
* but `watchlist_engine.process_update()` is called with `source_id=str(message.id)`

So the Discord reply says “Accepted — `chatgpt`” or similar, but the DB provenance field stores the Discord message ID, not the declared model/source string.

That is not necessarily wrong, but it conflates:

* transport provenance
* decision provenance

The system really wants both.

### 3. Symbol normalization is minimal

`watchlist_engine.py` normalizes with:

* `item["symbol"].upper()`
* `item["asset_class"].lower()`

That is not enough for robust crypto intake if pair aliases vary:

* `BTC/USD`
* `XBT/USD`
* Kraken-specific forms
* display forms versus provider forms

It is better than nothing, but still a paper umbrella in windy weather.

### 4. Validation checks presence, not semantic quality

`_validate_payload()` confirms that symbols exist and asset class is valid, but it does not validate:

* supported symbol format
* confidence range
* tag structure
* duplicate symbol entries in the same payload
* whether source is among `_VALID_SOURCES` even though that constant exists
* whether timestamp belongs to the specific decision symbols or top-level metadata only

Interesting note: `_VALID_SOURCES = {"claude", "chatgpt", "manual"}` is defined, but not actually enforced.

### 5. Duplicate symbols collapse silently in the engine

The engine builds:

```python
incoming = {
    (item["symbol"].upper(), item["asset_class"].lower())
    for item in new_symbols
}
```

Because this is a set, duplicates are silently deduplicated.

That can be okay, but it means:

* duplicate-symbol payload mistakes are not surfaced
* conflicting duplicate entries with different metadata are silently flattened

### 6. Watchlist API schema is intentionally permissive, maybe too permissive

`WatchlistUpdateIn` accepts `watchlist: list[dict]` rather than a strongly typed symbol model.

That makes the route easy to use, but it also means:

* no built-in schema validation for symbol item shape
* extra/invalid item fields slide through unless downstream code catches them
* HTTP route validation is weaker than it could be

### 7. Watchlist route coverage is shallow

The current API tests mostly confirm:

* endpoints return 200
* empty lists work
* missing symbol returns 404

They do not seem to meaningfully test:

* watchlist update semantics
* MANAGED transition
* asset-class-scoped replacement behavior
* duplicate handling
* intake schema normalization
* stale timestamp rejection
* Discord authorization logic

That leaves this intake boundary under-tested for a system where the watchlist is the spark plug.

## Pass/fail checklist

* [x] Discord intake is authorization-gated
* [x] Intake supports both inline JSON and attachments
* [x] Payload structure validation covers basic required fields
* [x] Legacy and current watchlist payload keys are normalized
* [x] Asset-class-scoped updates prevent stock/crypto cross-deactivation
* [x] Open-position symbols are downgraded to `MANAGED` instead of blindly removed
* [x] Watchlist transition audit events are emitted
* [ ] Rich decision metadata is persisted for later operator review and audit
* [ ] Provenance cleanly separates decision source from transport/message source
* [ ] Symbol normalization is robust enough for crypto/provider alias reality
* [ ] Validation enforces semantic quality, not just field presence
* [ ] Duplicates/conflicting payload entries are surfaced rather than silently collapsed
* [ ] Route and engine tests meaningfully cover real watchlist transition behavior

## Part 7 findings

### High

* **Rich AI decision metadata is largely discarded during intake, weakening auditability and later strategy review**
* **Symbol normalization at intake is too weak for robust crypto alias handling**

### Medium

* **Decision provenance and transport provenance are conflated: DB stores Discord message ID while UI-facing acceptance message uses the declared source**
* **Validation does not enforce `_VALID_SOURCES`, duplicate entries, confidence range, tag shape, or symbol-format quality**
* **Set-based intake silently collapses duplicate/conflicting payload entries**
* **HTTP watchlist input schema is permissive and weakly typed**
* **Test coverage for watchlist update semantics appears shallow**

### Low

* The route layer itself is clean and readable
* Backward compatibility support is well done

---

# Summary of Parts 6 and 7

## Strong areas

* Closed-candle discipline is clearly intended
* The 20-second refresh gate is a solid design choice
* Crypto and stock fetchers both try to strip incomplete intraday bars
* Watchlist updates are asset-class scoped
* MANAGED state handling is thoughtful
* Discord intake has real access control and practical payload handling

## Main issues found

1. **False freshness risk in candle caching**

   * cache freshness is based on fetch time rather than actual newest candle returned

2. **Candle integrity checks are thinner than they should be**

   * no continuity/min-count validation
   * stock daily completeness not explicitly guarded

3. **Watchlist intake discards too much intelligence**

   * reasons, confidence, tags, and other decision context mostly disappear

4. **Watchlist symbol/provenance handling is underpowered**

   * crypto alias normalization is weak
   * source semantics are mixed
   * duplicates collapse silently

5. **Tests are too light in both subsystems**

   * candle-layer timing/integrity tests appear sparse
   * watchlist semantics are not deeply exercised

## Recommended priority

### Fix next

* Change `CandleStore.update()` to derive freshness from the newest returned candle’s actual close time, not current wall-clock interval
* Add candle validation for ordering, duplicate timestamps, and minimum count
* Decide whether stock daily candles must explicitly exclude the current session’s partial day
* Persist richer watchlist decision metadata, especially `reason`, `confidence`, `tags`, and price/timestamp context
* Add provider-aware symbol normalization for crypto intake
* Strengthen watchlist schema validation and add tests for update semantics, duplicates, stale decisions, and MANAGED transitions

I audited the zip statically against **Part 8 Stock entry strategy audit** and **Part 9 Crypto entry strategy audit**.

**Scoring rule used:**
**PASS** = proven by code in the zip.
**FAIL** = contradicted by code **or** not checked/proven.

## Executive summary

This codebase has the bones of a real strategy engine, but a few ribs are still floating in the wrong drawer.

The good:

* Both stock and crypto entry engines use **real rolling EMA/ATR calculations**, not fake proxy shortcuts.
* Both engines have a **closed-candle guard** in strategy evaluation.
* Strategy selection is **deterministic** and sorted by confidence.
* Regime gets persisted onto positions at entry.

The problems:

* **Audit snapshot persistence is incomplete**. Important strategy reasoning is computed, but not stored in a durable trade-time structure.
* **Checklist coverage is incomplete**. Several required checks and tests simply are not there, which counts as fail under your rule.
* **Pullback reclaim and mean reversion logic are simpler than the checklist requires**. They do not prove slope/structure/body-quality the way the audit expects.
* **Kraken symbol normalization / display-vs-provider mapping is not implemented explicitly**.
* **Signal normalization fields like `signal_strength`, `distance_from_sma10_pct`, `breakout_distance_pct` do not exist**.
* **Test coverage is spotty for several strategies**, especially some stock and crypto strategies added later.

## Key findings

### 1. Closed-candle handling exists, but proof is thinner than it should be

Both sides have logic to drop the still-forming bar:

* stocks: `_closed_history(...)`
* crypto: `_closed_ohlcv(...)`

That is good.

But there is a catch:

* The stock helper only drops the last bar **if a parseable `time` field exists**
* The unit-test stock bar factory does **not** include timestamps
* There are **no explicit closed-candle-only tests** for stock or crypto entry strategies

So the mechanism exists, but the audit-grade proof is missing.

### 2. Indicator math is real, not fake

This passed the smell test.

* EMA is calculated from real rolling close series
* ATR is calculated from real high/low/previous-close history
* There is no “SMA5 = last price” style shortcut

That part is clean.

### 3. Pullback Reclaim is weaker than the checklist expects

Stock and crypto Pullback Reclaim both do this well:

* require trending-up regime
* require prior dip below EMA20
* require current close back above EMA20
* require current close above prior high and prior close

But they **do not** explicitly prove:

* slope alignment
* higher-timeframe structure quality
* rejection of weak wick-based reclaim patterns beyond the final close checks

So it is decent logic, but not checklist-complete logic.

### 4. Mean Reversion Bounce is also lighter than the checklist

Both stock and crypto versions:

* use EMA50 mean
* require the prior close to be sufficiently below mean
* require current close > prior close
* require current close still below mean

What is missing for checklist compliance:

* no candle-body / wick-quality confirmation
* no stronger reversal-structure confirmation
* no RSI or other confirmation layer
* uses EMA50, not the checklist’s SMA20-based framing

### 5. ORB is partly correct, partly hardcoded

The stock ORB logic:

* uses 5m data
* uses first 3 bars of the latest session as the opening range
* requires breakout above both opening-range high and recent high
* requires close confirmation and EMA20 support

What fails checklist strictness:

* opening range window is **not configurable**
* no explicit gap-open rejection logic
* docs in the zip say regime can be “Any”, but code requires `trending_up`

### 6. Signal/audit snapshot persistence is the biggest audit miss

At entry, positions store:

* entry/exit strategy
* stop
* targets
* max hold
* regime at entry
* market regime
* source id
* management policy version

That is useful, but the richer strategy snapshot is missing. The checklist wanted durable trade-time fields like:

* `triggerTimeframe`
* `signal_strength`
* `distance_from_sma10_pct`
* `breakout_distance_pct`
* `structure_state`
* `trend_alignment`

The strategies compute some reasoning details in-memory, but that reasoning is **not persisted** onto the position or order in a normalized, audit-ready way.

### 7. Kraken pair normalization is not audit-complete

The crypto code passes `ws.symbol` directly into Kraken OHLC calls.
There is **no explicit mapping layer** proving:

* display symbol vs provider symbol
* `BTC/USD` ↔ `XBTUSD`
* normalized internal representation

Kraken client does fall back to the returned response key, which helps with response parsing, but that is not the same as a deliberate pair-normalization layer.

### 8. Regime model does not match the Part 9 checklist taxonomy

The crypto entry logic uses:

* `trending_up`
* `trending_down`
* `ranging`
* `unknown`

The checklist asked to verify:

* `TREND`
* `RANGE`
* `VOLATILE`
* `WEAK_TREND`

That taxonomy is not present.

### 9. Test coverage has holes you can drive a forklift through

Direct unit tests exist for some core strategies, but not all.

Missing or insufficient coverage:

* **Stock**

  * no direct tests for `FailedBreakdownReclaim`
  * no direct tests for `VolatilityCompressionBreakout`
  * no closed-candle-only tests
  * no wick-only rejection tests
  * no conflicting-signal deterministic winner test beyond confidence sort
* **Crypto**

  * no direct tests for `BreakoutRetestHold`
  * no direct tests for `FailedBreakdownReclaim`
  * no pair alias / Kraken mapping tests
  * no closed-candle-only tests
  * no signal normalization tests

### 10. I could not execute pytest in this container

I attempted to run the entry-strategy tests from the zip, but execution failed immediately because the environment here does not have project dependencies like `sqlalchemy` installed. So runtime test proof is unavailable in this audit pass.

Under your scoring rule, anything that required execution proof but could not be checked is marked **FAIL**.

---

# Part 8 Checklist: Stock entry strategy audit

## 8.1 Strategy inventory mapping

* **Opening Range Breakout behaves like ORB** — **PASS**
* **Pullback Reclaim behaves like pullback + reclaim** — **PASS**
* **Mean Reversion Bounce behaves like mean-reversion bounce** — **PASS**
* **Trend Continuation Ladder behaves like trend continuation** — **PASS**
* **Momentum Breakout listed for stock audit coverage** — **FAIL**
  Not present as a stock strategy in this zip.
* **Each strategy exactly matches stronger checklist semantics** — **FAIL**
  Several are simpler than the checklist requires.

## 8.2 File mapping checklist

* `backend/app/stocks/strategies/entry_strategies.py` reviewed — **PASS**
* stock monitoring / entry creation path reviewed — **PASS**
* stock tests reviewed — **PASS**
* all checklist-named files exactly present as listed in prior audit template — **FAIL**
  This repo’s structure differs from that earlier template.

## 8.3 Closed candle validation

* strategy avoids using a forming candle when time is parseable — **PASS**
* candle completeness proven by tests — **FAIL**
* minimum required candles enforced — **PASS**
* timeframe alignment exists per strategy primary TF — **PASS**
* stock strategy never risks reading an incomplete bar when timestamp missing — **FAIL**

## 8.4 Indicator integrity

* real rolling indicator series used — **PASS**
* proxy values like `sma5 = last_price` are used — **FAIL** crossed off because they are **not** used
* SMA5/SMA10/SMA20 specifically implemented for stock entries — **FAIL**
* RSI-based checklist requirement present — **FAIL**

## 8.5 Pullback Reclaim logic audit

* prior pullback must occur first — **PASS**
* reclaim requires close back above mean — **PASS**
* trend structure explicitly validated beyond regime check — **FAIL**
* slope confirmation explicitly present — **FAIL**
* signal is based on closed bar — **PASS**
* single-trigger-per-candle behavior explicitly tested — **FAIL**

## 8.6 Mean Reversion Bounce validation

* deviation from mean is computed — **PASS**
* reversal requires current close above prior close — **PASS**
* wick-only reversal explicitly rejected — **FAIL**
* stronger reversal-structure confirmation exists — **FAIL**
* minimum lookback >= 50 bars — **PASS**
* checklist SMA20 version exists — **FAIL**

## 8.7 ORB audit

* opening range concept implemented — **PASS**
* breakout confirmed on close — **PASS**
* width / weak breakout rejection exists — **PASS**
* range window is configurable — **FAIL**
* gap open explicitly rejected as false ORB — **FAIL**

## 8.8 Signal snapshot integrity

* entry strategy persisted — **PASS**
* exit strategy persisted — **PASS**
* stop / targets / hold / regime persisted — **PASS**
* `triggerTimeframe` persisted — **FAIL**
* `signal_strength` persisted — **FAIL**
* `distance_from_sma10_pct` persisted — **FAIL**
* `breakout_distance_pct` persisted — **FAIL**
* `structure_state` persisted — **FAIL**
* `trend_alignment` persisted — **FAIL**
* full reasoning snapshot preserved durably at trade time — **FAIL**

## 8.9 Stock strategy test coverage

* insufficient candles reject test exists — **PASS**
* sideways/ranging reject coverage exists for core tested strategies — **PASS**
* false reclaim reject test exists — **PASS**
* ORB wick-only breakout rejection test exists — **FAIL**
* closed-candle-only test exists — **FAIL**
* conflicting-signals deterministic winner test exists — **FAIL**
* direct tests for all stock strategies exist — **FAIL**

---

# Part 9 Checklist: Crypto entry strategy audit

## 9.1 File mapping checklist

* `backend/app/crypto/strategies/entry_strategies.py` reviewed — **PASS**
* crypto monitoring / entry creation path reviewed — **PASS**
* crypto tests reviewed — **PASS**

## 9.2 Kraken pair integrity

* crypto strategies use Kraken OHLCV data — **PASS**
* explicit display-symbol vs provider-symbol mapping layer exists — **FAIL**
* alias normalization like `BTC/USD` ↔ `XBTUSD` is proven — **FAIL**
* pair-resolution tests exist — **FAIL**

## 9.3 Candle source validation

* real rolling OHLCV windows are used — **PASS**
* minimum candle checks exist — **PASS**
* ATR/EMA use real series — **PASS**
* timeframe consistency exists by strategy — **PASS**
* closed-candle-only behavior is explicitly tested — **FAIL**

## 9.4 Momentum strategy audit

* trend-up regime required — **PASS**
* breakout above recent high required — **PASS**
* price above EMA20 required — **PASS**
* late-extension filter exists — **PASS**
* volatility spike / exhaustion filter explicitly exists — **FAIL**
* slope-positive check explicitly exists — **FAIL**

## 9.5 Pullback Reclaim crypto variant

* prior dip below EMA20 required — **PASS**
* reclaim close above EMA20 required — **PASS**
* close above prior high / prior close required — **PASS**
* wick-only reclaim explicitly rejected — **FAIL**
* slope alignment explicitly checked — **FAIL**

## 9.6 Regime alignment check

* regime is stored at entry on position creation — **PASS**
* regime labels match checklist taxonomy (`TREND/RANGE/VOLATILE/WEAK_TREND`) — **FAIL**
* “not recomputed later” behavior proven by audit/test — **FAIL**

## 9.7 Signal strength normalization

* 0.0 to 1.0 normalized signal score exists — **FAIL**
* normalized MA-distance metric exists — **FAIL**
* normalized breakout-distance metric exists — **FAIL**
* normalized RSI positioning exists — **FAIL**
* normalized volatility percentile exists — **FAIL**

## 9.8 Cross-asset consistency rules

* candle-close requirement exists on both stock and crypto — **PASS**
* reclaim logic has similar structure on both — **PASS**
* signal snapshot structure is consistent across both — **FAIL**
* trend-alignment definition is fully standardized across both — **FAIL**

## 9.9 Crypto strategy test coverage

* insufficient candles tests exist — **PASS**
* ranging / trend rejection tests exist for tested strategies — **PASS**
* closed-candle-only tests exist — **FAIL**
* alias pair resolution tests exist — **FAIL**
* intrabar breakout rejection tests exist — **FAIL**
* regime alignment tests exist — **FAIL**
* direct tests for all crypto strategies exist — **FAIL**

---

# Final finding summary

## Passed

* Real rolling EMA/ATR calculations
* Strategy-specific timeframe routing
* Closed-candle guard exists in code
* Core strategies generally resemble their names
* Confidence sorting is deterministic
* Entry regime is persisted on created positions

## Failed

* Audit-grade persistence of signal snapshot data
* Explicit signal-strength normalization
* Explicit Kraken display/provider symbol normalization
* Several checklist-required structural confirmations
* Full strategy test coverage
* Closed-candle-only proof via tests
* Pair alias resolution proof
* Checklist taxonomy alignment for crypto regimes

## Highest-priority fixes

1. Persist a normalized trade-time strategy snapshot on position open.
2. Add closed-candle-only tests for stock and crypto.
3. Add direct tests for untested strategies.
4. Add explicit Kraken symbol normalization layer.
5. Upgrade Pullback Reclaim and Mean Reversion logic to include stronger structure/slope/body checks.
6. Add normalized signal metrics for post-trade analysis.

I continued the audit on the uploaded zip for **Part 10 Frontend architecture and operator UI truthfulness** and **Part 11 Test suite reliability review**, using the plan/checklist criteria you uploaded for those sections. The goal here is exactly what those docs call for: verify page-to-endpoint mapping, state loading, polling/WebSocket behavior, badge truthfulness, and whether tests protect the system’s real risks rather than wearing construction helmets as fashion.  

## Executive summary

This frontend is stylish and generally well-wired, but a few truths get sanded smooth on the way to the glass cockpit.

The strongest parts:

* Routing, navigation, and shared API wiring are coherent.
* The WebSocket layer updates the dashboard and market-status cache directly, which is a good fit for live telemetry.
* Time formatting is intentionally ET-safe and handles naive UTC strings correctly.
* Positions/runtime pages mostly display backend-provided fields instead of inventing fresh logic in the browser.
* Core strategy, exit, and regime tests exist and are not just type-check confetti.  

The weakest parts:

* `frontend/src/api/types.ts` is almost empty, so the “type-safe shared API layer” promise is mostly cardboard.
* Monitoring and status badges are too generic in places, so the UI can blur important distinctions into a single colored sticker.
* The positions inspect drawer does **not** surface persisted frozen policy / milestone details even though the backend schema exposes them.
* WebSocket cache invalidation coverage is partial. Dashboard and market status are live-fed, but several other pages remain timer-driven islands.
* The test suite is respectable for strategies/regime, but thin for runtime auth, monitoring flow, watchlist ingestion, websocket behavior, and persistence-drift scenarios. That is exactly the kind of gap the checklist warns about.  

---

# Part 10 audit: Frontend architecture and operator UI truthfulness

## Major findings

### 1. Page-to-endpoint mapping is clean

This part passed. The frontend routes line up with real pages, and the endpoint layer maps sensibly to backend routes:

* dashboard → `/api/dashboard`
* watchlist → `/api/watchlist`
* monitoring → `/api/monitoring`
* positions → `/api/positions` and `/api/positions/open`
* ledger → `/api/ledger/*`
* trades → `/api/trades*`
* audit → `/api/audit*`
* runtime → `/api/runtime*`

That matches the review focus for page-to-endpoint mapping and shared API layer.  

### 2. Shared API layer works, but type coverage is paper-thin

This is the biggest frontend architecture miss.

`frontend/src/api/types.ts` only defines `MarketStatusResponse`. Everything else is typed ad hoc inside page components. That means:

* route/schema drift will be caught late
* reusable type truth is missing
* page components each become their own little customs office

So the API layer is functional, but not robust. Pretty hull, thin bulkheads.

### 3. Timezone handling is actually good

`frontend/src/utils/time.ts` is one of the cleaner pieces in the repo:

* it treats naive backend datetime strings as UTC
* formats consistently in `America/New_York`
* provides relative time via the same parsing path

That is a real pass and avoids the classic “timezones become goblins at midnight” bug.

### 4. WebSocket design is solid for dashboard telemetry, but incomplete system-wide

The WebSocket provider:

* connects once
* reconnects with exponential backoff
* pushes dashboard and market-status payloads straight into TanStack Query cache
* invalidates some queries on `position_executed`
* avoids reconnect loops on unmount

That is good.

But the live-update strategy is incomplete:

* dashboard and market status are WebSocket-first
* most other pages still poll every 15 to 30 seconds
* invalidation on trade execution only touches `dashboard`, `positions`, and `ledger`
* trade history, audit trail, monitoring, watchlist, and runtime are not comprehensively covered by event-driven invalidation

So there is no catastrophic conflict, but the live picture is partly stream-fed and partly bucket-brigade.

### 5. Status badge semantics are too lossy

`StatusBadge` is a generic color map, not a semantic model.

Examples:

* `ACTIVE`, `OPEN`, `FILLED`, `running`, `online` all share the same visual language
* `MANAGED`, `PENDING`, `SUBMITTED`, `idle` all collapse together
* unknown values silently fall back to gray
* frontend meaning is not always one-to-one with backend operational meaning

That matters because the checklist explicitly asks whether labels like “Healthy”, “Waiting For Setup”, “Open”, or “Managed” are derived correctly and whether badge/state names mean the same thing on both sides.  

This does not mean the UI is lying outright. It means the truth is sometimes translated into bumper-sticker English.

### 6. Monitoring page is usable, but operator diagnosis is weaker than it should be

The Monitoring page shows:

* symbol
* asset class
* raw state
* top strategy
* top confidence
* added date
* manual evaluate action

Good:

* it does not invent candidate state locally
* it uses backend-provided `state`
* it supports on-demand evaluation

Weak:

* rejection reasons are **not** visible in the row grid
* “why blocked / why waiting” is not surfaced in a first-class way
* `added_at` uses `toLocaleDateString()` instead of the shared ET formatter, creating inconsistent timestamp treatment
* jump-lane / review semantics are absent

This falls short of the checklist’s “operator can tell why something is blocked, waiting, healthy, or open without guessing.” 

### 7. Positions page mostly respects backend truth, but inspect depth is too shallow

The positions page is one of the better pages:

* fetches open positions from backend
* shows backend fields like `entry_strategy`, `exit_strategy`, `regime_at_entry`, stops, targets, fees
* does not appear to recompute PnL or strategy state locally

But the inspect drawer does **not** expose some of the most valuable truth-bearing fields already present in the backend schema:

* `management_policy_version`
* `frozen_policy`
* `milestone_state`

That means persisted live-management truth exists in the API surface, but the operator page only shows the trimmed brochure.

### 8. Runtime page is generally truthful, with one UX caveat

The Runtime page:

* reads runtime state from backend
* requires admin token for mutations
* uses backend responses rather than optimistic local flips
* refetches after mutations via query invalidation

That is good.

Caveat:

* the page visually mixes status, session window interpretation, and command controls in a way that can still simplify important backend nuance
* some worker-state display is badge-based and inherits the same generic semantics problem from `StatusBadge`

### 9. Dashboard is good as a cockpit, but some state translation happens in the frontend

Dashboard mostly uses backend data cleanly.

One translation worth flagging:

* `stockStatus(raw, ms)` rewrites stock worker status based on market status, converting non-open stock conditions into `paused`, `pre-market`, or `eod`

That may be useful operationally, but it is a frontend reinterpretation rather than direct backend truth. So it is a mild drift risk. The cockpit is telling the truth with editorial captions.

---

## Part 10 checklist: pass / fail

### 10.1 Frontend shell, layout, navigation, shared API layer

* Navigation links map to actual pages — **PASS**
* Shared API methods match backend routes — **PASS**
* Shared API **types** match backend responses comprehensively — **FAIL**
* Time utilities use consistent ET display convention — **PASS**
* Layout hides important status content on common screen sizes — **FAIL** as a checklist item, because no responsive blind-spot testing or proof exists
* Command palette actions are safe and accurate — **PASS**

### 10.2 Dashboard and summary truthfulness

* Dashboard metrics are sourced from backend data — **PASS**
* Market status labels use backend market-status route — **PASS**
* Summary cards are proven not to double-count or omit states — **FAIL**
* Frontend formatting avoids dangerous oversimplification — **FAIL**
* Dashboard summary matches underlying pages by proof/test — **FAIL**

### 10.3 Monitoring page and operator diagnosis flow

* Monitoring row statuses map directly to backend states — **PASS**
* Rejection reasons are displayed fully enough to debug — **FAIL**
* Review/jump-lane style semantics are meaningful rather than cosmetic — **FAIL**
* Polling/refresh patterns avoid stale diagnosis — **PASS**
* Filters/derived groupings preserve underlying meaning — **PASS**

### 10.4 Positions page truthfulness

* Positions route returns fields needed for operator decisions — **PASS**
* Lifecycle state shown in UI matches backend state definitions — **PASS**
* Exit strategy/protection/regime fields display persisted truth fully — **FAIL**
* Open positions update cleanly after fill/close/cancel by design — **PASS**
* Inspect data is not being reinterpreted incorrectly — **PASS**
* Inspect path uses persisted backend state **first and fully** — **FAIL**

### 10.5 Watchlist page integrity

* Latest/current watchlist data displayed accurately — **PASS**
* Stock/crypto scope views correct — **PASS**
* Reasons/confidence/tags survive serialization intact — **FAIL**
* Stale watchlists are visibly distinguishable — **FAIL**

### 10.6 Ledger / TradeHistory / AuditTrail pages

* Table columns map to backend fields — **PASS**
* Sorting/formatting preserve numeric precision where needed — **PARTIAL, scored FAIL under your rule**
* Timestamps display consistently — **PASS**
* Audit events are understandable in operator language — **PASS**
* Crypto precision is not inappropriately rounded away everywhere — **FAIL**
* Exports, if any, retain correct values — **FAIL** (not checked)

### 10.7 WebSocket and live update behavior

* WebSocket route registration and connection handling exist — **PASS**
* Broadcast payloads are shaped consistently for dashboard + market status — **PASS**
* Frontend handles reconnects safely — **PASS**
* WebSocket updates do not conflict with polling refresh logic — **PASS**
* Stale subscriptions are cleaned up — **PASS**
* Live update coverage is comprehensive across operator surfaces — **FAIL**

### 10.8 Slice C: can the UI lie to the operator?

* Badge/state names mean the same thing backend and frontend — **FAIL**
* Position protection state shown is the real persisted state — **FAIL**
* Runtime risk state shown is real — **PASS**
* Dashboard summary matches underlying pages by proof — **FAIL**
* Rejection reasons survive backend-to-UI translation intact — **FAIL**

---

# Part 11 audit: Test suite reliability review

## Major findings

### 1. Critical subsystems do have tests

This part passes:

* stock entry strategies
* crypto entry strategies
* stock exit strategies
* crypto exit strategies
* regime engine/classification/helpers
* basic API routes

So the suite is not empty theater. It has real bones. 

### 2. Strategy tests are generally meaningful

The strategy tests do more than assert “returns bool.”
They check:

* insufficient data rejection
* trend vs range conditions
* specific strategy outputs
* stop/trailing/TP logic in exits
* regime-classification boundaries

That aligns with the checklist requirement that tests validate actual behavior, not just output types. 

### 3. Candle fixtures are not realistic enough for closed-candle enforcement

This is an important weakness.

In `conftest.py`:

* crypto candles include numeric timestamps
* stock bars do **not** include time fields
* helpers are clean synthetic sequences, but highly idealized

That matters because the checklist explicitly asks whether tests enforce closed-candle logic and whether candle fixtures are realistic. 

The fixtures are useful for deterministic logic tests, but they are not strong enough to prove real closed-candle safety in all paths.

### 4. Route tests are shallow

`test_api_routes.py` mostly covers:

* empty-list responses
* filter acceptance
* 404 on missing object
* health route

What is missing:

* runtime admin auth success/failure
* watchlist update route validation
* monitoring evaluate route
* websocket route behavior
* schema edge cases
* mutation routes like ledger adjustments and runtime reset/halt/resume

So the API tests check the paint is dry, but not whether the bridge holds a truck.

### 5. Regime tests are the strongest part of the suite

`test_regime.py` is broad and detailed:

* indicator helper math
* stock regime classification
* crypto regime classification
* engine/tick behavior
* policy/opening permission behavior

This is the most mature testing area.

### 6. Entry/exit coverage has holes

Stock entry:

* ORB, PullbackReclaim, TrendContinuationLadder, MeanReversionBounce covered
* but not every possible edge around closed-candle timing, false breakout wick behavior, or monitoring/watchlist integration

Crypto entry:

* momentum breakout, pullback reclaim, mean reversion, range rotation reversal covered
* but no pair-alias regression, no websocket-trigger path, and no watchlist-to-monitoring execution path

Exit tests:

* good core template coverage
* but little proof for worker idempotency / duplicate order prevention / persistence-read-first behavior in live management

### 7. Major missing regression buckets

The checklist specifically asks about missing candles, duplicate orders, alias symbols, stale watchlists, and partial exits. 

From the zip, missing or weakly covered:

* monitoring flow tests
* watchlist ingestion and schema normalization tests
* runtime auth and mutation tests
* websocket behavior tests
* persistence-drift / frozen-policy UI path tests
* duplicate order / duplicate exit worker regression tests
* alias symbol handling tests
* stale watchlist behavior tests
* partial reconciliation / state drift scenarios

---

## Part 11 checklist: pass / fail

### 11.1 Critical subsystem coverage

* Each critical subsystem has tests — **PASS**
* Tests validate strategy behavior, not just return type — **PASS**
* Candle fixtures represent completed candles realistically — **FAIL**
* Route tests cover success and failure/auth cases — **FAIL**
* Regime tests cover edge and threshold boundaries — **PASS**
* Exit tests include no-action and duplicate-risk cases — **FAIL**
* Missing regression areas identified — **PASS**

### 11.2 Closed-candle and symmetry checks

* Tests enforce closed-candle logic explicitly — **FAIL**
* Stock and crypto strategy tests are symmetrical where they should be — **FAIL**
* Entry strategy tests use realistic candle sequences — **PARTIAL, scored FAIL**
* Exit strategy tests use realistic management-state scenarios — **PARTIAL, scored FAIL**

### 11.3 API and integration coverage

* Basic read routes covered — **PASS**
* Runtime control routes covered — **FAIL**
* Monitoring routes covered — **FAIL**
* Watchlist update flow covered — **FAIL**
* Ledger mutation routes covered — **FAIL**
* WebSocket behavior covered — **FAIL**

### 11.4 Persistence / reconciliation / drift risks

* Duplicate order prevention regressions covered — **FAIL**
* Alias symbol matching regressions covered — **FAIL**
* Stale watchlist regressions covered — **FAIL**
* Partial exit / quantity drift regressions covered — **FAIL**
* Persistence drift / frozen policy regressions covered — **FAIL**

---

# Highest-value findings

## High

The frontend is **mostly truthful**, but some of its most visible status surfaces are semantically compressed. `StatusBadge` and some dashboard/runtime translations can turn operational nuance into colored wallpaper.

## High

The positions inspect experience is not showing the backend’s richer persisted-management truth. If the backend is preserving frozen policy and milestones, the UI should not wear mittens over it.

## High

The test suite is strong on strategy and regime internals, but weak on real-world glue:

* auth
* monitoring
* watchlist intake
* websocket
* runtime mutation
* duplicate-risk regressions

## Medium

The shared API layer needs real frontend types. Right now each page is freelancing.

## Medium

Timestamp handling is good overall, but Monitoring still uses a locale date shortcut instead of the shared ET formatter.

---

# Recommended fix queue

## P0

Add tests for runtime auth and mutation routes: halt, resume, patch runtime, reset paper data.

## P0

Add regression tests for monitoring/watchlist flow, alias matching, and duplicate-order prevention.

## P1

Promote backend schemas into real frontend shared types in `frontend/src/api/types.ts`.

## P1

Refactor `StatusBadge` into a semantic mapping based on backend-defined operational states, not a generic color blender.

## P1

Expose `management_policy_version`, `frozen_policy`, and `milestone_state` in the positions inspect drawer.

## P2

Expand WebSocket invalidation coverage or add a clearer event model for monitoring, trades, audit, and watchlist.

## P2

Use shared ET formatting everywhere, including Monitoring’s `added_at`.

I continued with **Part 12: Crypto monitoring flow**. Per the plan/checklist, this section is about duplicate prevention, alias handling, state truthfulness, 24/7 crypto assumptions, and whether the monitoring route gives the UI enough fuel to diagnose what is happening.  

## Executive summary

This crypto monitoring flow is functional, but it has a symbol-identity leak that could let duplicate exposure sneak in through the side door wearing a fake mustache.

The strongest parts:

* Crypto monitoring is clearly separated from stock monitoring.
* It uses crypto-specific candle fetch/backfill/refresh logic with incomplete-candle dropping and a 20-second post-close refresh gate.
* The worker is gated by the crypto trading runtime state, not stock market hours.
* Monitoring routes are read-only and do not mutate database state.

The biggest risks:

* **No explicit crypto alias normalization** in monitoring. `BTC/USD`, `XBTUSD`, and other Kraken-style variants are not reconciled in open-position checks or cooldown keys.
* **No active-intent guard** in the crypto monitor before creating a new position.
* Monitoring candidate state is too thin. It is mostly just `ACTIVE` from the watchlist row, not a richer blocked/healthy/rejected execution state.
* The route payload is too skinny for operator diagnosis. It gives “top strategy / confidence / entry,” but not why a symbol is blocked, skipped, cooling down, already open, or regime-rejected.
* There are no tests covering crypto monitoring alias safety, duplicate prevention, or route behavior.

---

# Watchlist-to-monitoring flow map

## Purpose

Crypto monitoring should:

1. read active crypto watchlist symbols
2. backfill/load candles into the in-memory store
3. refresh only when a new closed candle is available
4. skip symbols already open or on cooldown
5. evaluate crypto entry strategies
6. gate by regime policy
7. create a position/order if allowed

That matches the plan’s “can symbols re-enter when already open, can aliasing cause duplicate exposure, are monitoring states truthful, and do routes read safely?” lens. 

## Actual observed flow

* `CryptoMonitor._cycle()` reads all active crypto `WatchlistSymbol` rows.
* It backfills candles for symbols not yet loaded.
* It refreshes each timeframe only after the post-close gate.
* `_evaluate_symbol()` checks open positions, checks cooldown, runs `evaluate_all`, checks regime permission, then creates a position.
* Monitoring API route separately reevaluates symbols on demand and for list display.

This is clean structurally, but the identity and state layers are underpowered.

---

# Detailed findings

## 1. Crypto is correctly treated as 24/7

**Result: PASS**

Good signs:

* No market-hours gating appears in `backend/app/crypto/monitoring.py`.
* The monitor loop uses `runtime_state.is_trading_enabled("crypto")`, which is the right control-plane gate for 24/7 assets.
* Candle refresh uses timeframe-close math rather than session windows.

This passes the checklist requirement that crypto monitoring not inherit stock-only session logic. 

## 2. Closed-candle handling in the monitoring pipeline is good

**Result: PASS**

`CryptoCandleFetcher` drops an incomplete last OHLCV bar and only refreshes after the 20-second post-close offset. That is exactly the kind of behavior you want to avoid peeking into half-formed candles.

This is one of the cleaner cogs in the machine.

## 3. Alias handling is not implemented in monitoring

**Result: FAIL**

This is the most important defect in Part 12.

Why it fails:

* `_has_open_position()` checks `Position.symbol == symbol` exactly.
* Cooldown uses `cooldown:crypto:{ws.symbol}` exactly.
* Candle store keys are exact symbol strings.
* Monitoring route reevaluates `ws.symbol` exactly.
* `KrakenClient.get_ohlcv()` accepts whatever pair string was passed and only adapts to the returned response key after the request. It does **not** normalize internal symbol identity across the system.

So if the watchlist uses `BTC/USD` and an open position was stored as `XBTUSD`, the monitor has no built-in alias bridge. That is the exact fail pattern the checklist warns about. 

**Severity: High**

**Risk:** duplicate crypto exposure, duplicate cooldown bypass, split candle caches, inconsistent UI rows.

## 4. Open-position guard exists, but only for exact symbol matches

**Result: FAIL**

There is an open-position guard, which is good.

But because it is exact-string only, it is not strong enough for Kraken-style symbols. The guard is a lock on the door, but only if the intruder uses the same spelling.

**Severity: High**

## 5. No active-entry-intent guard before creating a new crypto position

**Result: FAIL**

The monitor checks:

* already open
* cooldown key
* signal existence
* regime permission

It does **not** check for a pending/submitted crypto entry order or active order intent before creating a fresh position. If the loop, API path, or another process causes near-simultaneous evaluation, there is less protection than there should be.

**Severity: High**

**Risk:** duplicate entries or race-condition exposure.

## 6. Monitoring states are mostly ornamental, not execution-truthful

**Result: FAIL**

The checklist asks whether monitoring states distinguish healthy candidates from blocked or rejected candidates. 

In this implementation:

* the monitoring list route returns `ws.state`
* the query only selects `WatchlistSymbol.state == ACTIVE`
* no blocked/rejected/cooldown/open/regime-blocked reason is surfaced in the list response

That means the list page can show a symbol as `ACTIVE` even when:

* it already has an open position
* cooldown is active
* regime blocks opening
* no valid signals exist

The UI gets a top strategy/confidence teaser, but not the operational truth state.

**Severity: High**

## 7. Monitoring routes read safely

**Result: PASS**

This is a clean pass.

The monitoring API route:

* selects DB rows
* fetches market data
* evaluates strategies
* returns payloads

It does not commit, mutate watchlist rows, create orders, or change position state. So the “do monitoring routes read safely?” check passes. 

## 8. Route payload is too thin for diagnosis

**Result: FAIL**

The route gives:

* symbol
* asset class
* state
* added_at
* watchlist_source_id
* top_strategy
* top_confidence
* top_entry

That is helpful, but not enough for proper crypto diagnosis.

Missing high-value fields:

* `has_open_position`
* `cooldown_active`
* `blocked_reason`
* `regime_allowed`
* `regime`
* `evaluation_error`
* `top_notes`
* `top_regime`
* `top_stop`
* `position_or_order_status`

Without those, the operator page is reading tea leaves instead of telemetry.

**Severity: Medium-High**

## 9. The on-demand evaluate route is useful, but still not alias-safe

**Result: FAIL**

`/api/monitoring/evaluate/{symbol}` does a direct `symbol.upper()` evaluation path. That is nice for a manual “ping,” but it still relies on exact symbol form and does not normalize aliases. So it can evaluate one variant while the rest of the system stores another.

**Severity: Medium**

## 10. No tests for crypto monitoring flow

**Result: FAIL**

For Part 12 specifically, I found no dedicated tests covering:

* alias matching in crypto monitoring
* open-position duplicate prevention through Kraken symbol variants
* cooldown handling
* monitoring route payload correctness
* read-only safety
* 24/7 crypto assumptions in monitoring behavior

That leaves this whole section mostly unguarded by regression netting.

**Severity: High**

---

# Part 12 checklist: pass / fail

## Files reviewed

* `backend/app/crypto/monitoring.py`
* `backend/app/crypto/candle_fetcher.py`
* `backend/app/crypto/kraken_client.py`
* `backend/app/api/routes/monitoring.py`
* `backend/app/api/schemas/monitoring.py`

## Checklist results

* Confirm crypto alias handling prevents duplicate positions across symbol variants — **FAIL**
* Confirm open-position and active-intent guards work for Kraken pair names — **FAIL**
* Confirm monitoring states distinguish healthy candidate from blocked or rejected candidate — **FAIL**
* Confirm crypto monitoring uses correct 24/7 assumptions without leaking stock gating — **PASS**
* Confirm route payload exposes enough detail for UI diagnosis — **FAIL**
* Confirm monitoring routes read safely without side effects — **PASS**
* Confirm candidate filtering is present — **PASS**
* Confirm duplicate prevention is strong enough for Kraken aliases — **FAIL**

---

# State-machine defect list

## Defect 1: Alias-blind duplicate prevention

**Observed:** exact-symbol checks only
**Risk:** duplicate entries for the same underlying asset under different Kraken/display forms
**Severity:** High

## Defect 2: No active-entry-intent guard

**Observed:** monitor checks open position and cooldown, but not pending entry intent/order
**Risk:** duplicate entry creation during races or repeated evaluations
**Severity:** High

## Defect 3: Candidate state lacks execution truth

**Observed:** monitoring list mostly reflects watchlist `ACTIVE` state
**Risk:** UI shows symbols as active candidates when they are effectively blocked/open/cooling down
**Severity:** High

## Defect 4: Route payload too shallow for operator debugging

**Observed:** no blocked reason, cooldown, open-position, or regime detail
**Risk:** operators cannot tell why a symbol is not entering
**Severity:** Medium-High

## Defect 5: No crypto monitoring regression coverage

**Observed:** no tests for alias safety, route payload, or duplicate-prevention edge cases
**Risk:** future fixes can quietly break
**Severity:** High

---

# Recommended fix queue

## P0

Introduce a **canonical crypto symbol normalization layer** used by:

* watchlist ingestion
* candle store keys
* open-position checks
* cooldown keys
* monitoring route evaluation
* order/position storage

## P0

Add an **active-entry-intent / pending-order guard** before `_create_position()`.

## P1

Upgrade monitoring list payload to include:

* `has_open_position`
* `cooldown_active`
* `blocked_reason`
* `regime`
* `regime_allowed`
* `top_notes`
* `top_stop`
* `evaluation_error`

## P1

Split monitoring state into richer operational states, such as:

* `OPEN_POSITION`
* `COOLDOWN`
* `NO_SIGNAL`
* `REGIME_BLOCKED`
* `READY`
* `ERROR`

## P1

Add tests for:

* `BTC/USD` vs `XBTUSD` alias match
* open-position duplicate prevention
* cooldown skip
* route list payload truthfulness
* evaluate route alias behavior
* route read-only safety

I audited **Part 13 Stock exit logic and worker behavior** and **Part 14 Crypto exit logic and worker behavior** against the QA Plan and Review Checklist sections for exit strategies, worker safety, idempotency, persisted state usage, and test coverage.  

## Executive summary

The exit layer is halfway between a disciplined trader and a raccoon with a stopwatch.

What is solid:

* Both stock and crypto positions store a **frozen `exit_strategy`** at entry and the workers use that stored value.
* Both workers update `current_stop`, `milestone_state`, realized/unrealized PnL, ledger entries, and audit logs.
* Stock has EOD handling, crypto is 24/7, and the two workers are structurally separated.
* Crypto stop logic is stronger than stock stop logic because it tries to confirm breaks with candle closes.

What is not solid:

* **Both workers apply a global max-hold hard close before strategy evaluation**, which overrides the documented strategy-specific time-stop logic.
* **Neither worker has a pending-exit / duplicate-exit guard.**
* **Neither worker creates exit orders in the `orders` table**, so the “order lifecycle” is thin and idempotency is not well protected.
* **Stock stop/trailing logic is based on raw price, not confirmed structure**, making it more whipsaw-prone than crypto.
* **Crypto trailing behavior is not actually “persisted-state first” in a strong sense**, because trail raising still depends on fresh recomputation from live OHLCV every cycle.
* Test coverage is decent for pure strategy classes, but weak for worker behavior, duplicate-risk, persistence drift, and ledger/order consistency.

---

# Part 13: Stock exit logic and worker behavior

## Major findings

### 1. Exit strategy freezing is implemented

**Result: PASS**

Stock positions are opened with a frozen `exit_strategy`, `initial_stop`, targets, `max_hold_hours`, and `frozen_policy`, and the stock exit worker uses `position.exit_strategy` when calling `evaluate_exit(...)`.

That is the right shape for “stable live management policy.”

### 2. Strategy names mostly match their behavior

**Result: PASS**

These stock strategies generally match the docs:

* Fixed Risk then Break-Even Promotion
* Partial at TP1, Trail Remainder
* First Failed Follow-Through Exit
* Time Stop Exit
* VWAP / Structure Loss Exit
* End-of-Day Exit

They are not wildly mislabeled. The names mostly fit the machinery.

### 3. Stock worker globally enforces `max_hold_hours` before strategy evaluation

**Result: FAIL**

This is the biggest Part 13 defect.

In `StockExitWorker._evaluate_position()`, the worker checks:

* if `elapsed_hours >= position.max_hold_hours`
* then closes immediately

That happens **before** `evaluate_exit(...)`.

Why this fails:

* It bypasses the documented behavior of `Time Stop Exit`, which is supposed to also require weak progress (`price < entry * 1.003`).
* It affects **all stock positions with `max_hold_hours`**, even if their assigned exit strategy is not `Time Stop Exit`.
* It means the worker can close a strong, profitable trend runner just because the clock ran out.

That is a strategy override hiding in the hallway wearing a maintenance badge.

**Severity: High**

### 4. Stock exit decisions use persisted position truth

**Result: PASS**

The stock worker reads the DB `Position`, uses stored:

* `exit_strategy`
* `current_stop`
* `initial_stop`
* `profit_target_1`
* `max_hold_hours`
* `milestone_state`

Then it updates those same persisted fields.

This passes the “use current persisted position truth” check.

### 5. Stock stop logic is not candle-confirmed

**Result: FAIL**

Stock exit strategies use direct price comparisons:

* `current_price <= stop`
* `current_price <= trail`
* `current_price < structure_support * 0.998`

There is no stock equivalent of crypto’s `_stop_confirmed(...)`.

That means stock exits are more vulnerable to wick/quote noise and transient spikes. The docs do not explicitly require confirmation, so this is not a naming mismatch, but it is an operational weakness for a worker meant to avoid accidental exits.

**Severity: Medium-High**

### 6. EOD gating is coherent

**Result: PASS**

Stock worker cycles only while `can_pull_data()` is true, which includes `open` and `eod`. The strategies also check `_is_near_eod()`, so stock positions can still be closed in the EOD window.

This part is consistent.

### 7. Partial exit handling is structurally correct

**Result: PASS**

When stock strategy returns a partial:

* quantity is reduced
* realized PnL is updated
* unrealized PnL is recalculated
* ledger exit entry is written
* milestone state is updated with `tp1_hit`, `tp1_price`, and `trailing_stop`

This is the cleaner part of the worker.

### 8. Worker is not idempotent enough to prevent duplicate exits robustly

**Result: FAIL**

The worker:

* selects all open positions
* evaluates them
* closes them in memory
* commits at the end of the cycle

What is missing:

* no exit-pending flag
* no order-intent guard
* no existing open-exit-order check
* no DB-level optimistic/pessimistic lock visible here
* no `orders` row creation for exit attempts

So duplicate exits are not well-defended if there are concurrent workers, retry scenarios, or multiple evaluation paths.

**Severity: High**

### 9. Worker logging explains closes and stop updates, but not holds very well

**Result: FAIL**

There are good logs/audit events for:

* stop updates
* partial exits
* position closed

But there is no strong operator-facing “held because X” logging or persisted explanation path. That falls short of the checklist’s “worker logging explains why a position was held or closed.”

### 10. Order lifecycle is too thin for exit operations

**Result: FAIL**

The stock worker updates ledger and position directly, but it does **not** create an `Order` row for exits or partial exits.

That means:

* position changes are not represented as a proper exit-order lifecycle
* `/positions/{id}/orders` will not reflect worker-generated exits unless entry path created orders elsewhere
* audit trail exists, but order trail is incomplete

This weakens traceability and duplicate-exit protection.

**Severity: High**

### 11. Stock exit tests cover strategy classes, not worker safety

**Result: FAIL**

The stock test file covers:

* ATR helper
* break-even promotion
* TP1 partials and trail
* failed follow-through

What is missing:

* worker-level tests
* duplicate-risk tests
* ledger/order coherence tests
* EOD worker behavior tests
* max-hold override regression tests

So the strategy tests are real, but the worker itself is walking without a helmet.

---

## Part 13 checklist: pass / fail

* Confirm each exit strategy matches its documented meaning — **PASS**
* Confirm stop, target, trailing, and failed-follow-through rules are mutually coherent — **FAIL**
* Confirm exit worker is idempotent enough to avoid duplicate exits — **FAIL**
* Confirm exit decisions use current persisted position truth — **PASS**
* Confirm stock market-hours gating blocks invalid exit attempts when required — **PASS**
* Confirm worker logging explains why a position was held or closed — **FAIL**
* Confirm tests cover no-exit, valid-exit, and duplicate-risk scenarios — **FAIL**

### Extra stock findings

* Confirm partial exits update milestones and ledger coherently — **PASS**
* Confirm order lifecycle is fully represented for exits — **FAIL**
* Confirm strategy-specific time-stop behavior is preserved by worker — **FAIL**

---

# Part 14: Crypto exit logic and worker behavior

## Major findings

### 1. Crypto exit strategy freezing is implemented

**Result: PASS**

Crypto positions are created with frozen:

* `exit_strategy`
* `initial_stop`
* targets
* `max_hold_hours`
* `frozen_policy`
* `management_policy_version`

The crypto worker uses `position.exit_strategy`, which is the correct foundation for sticky live management.

### 2. Crypto strategy names mostly match their behavior

**Result: PASS**

These generally align with docs:

* Fixed Risk then Dynamic Protective Floor
* Partial at TP1, Dynamic Trail on Runner
* Failed Follow-Through Exit
* Range Failure Exit
* Time Degradation Exit
* Regime Breakdown Exit

The naming is mostly honest.

### 3. Crypto worker also globally enforces `max_hold_hours` before strategy evaluation

**Result: FAIL**

This is the crypto mirror of the stock defect.

`CryptoExitWorker._evaluate_position()` checks elapsed hours before calling `evaluate_exit(...)` and immediately closes if max hold is reached.

Why this fails:

* It overrides `Time Degradation Exit`, which is supposed to require poor progress (`price < entry * 1.005`).
* It forces time-based closure on **all crypto positions** with a max hold.
* It can kill a healthy runner even if its assigned exit strategy is a dynamic trail or regime-based management.

**Severity: High**

### 4. Crypto stop logic is better than stock logic

**Result: PASS**

Crypto uses `_stop_confirmed(...)`, which tries to prevent wick-only stopouts by requiring the last completed candle to confirm the stop break when OHLCV is present.

This is a real strength.

### 5. “Persisted state first” is only partially true

**Result: FAIL**

Crypto worker does use persisted fields:

* `current_stop`
* `milestone_state`
* `exit_strategy`
* `regime_at_entry`

But trail raising and trend checks depend on fresh OHLCV recomputation every cycle:

* `_is_trending(ohlcv)`
* `_atr(ohlcv)`
* `RegimeBreakdownExit` recalculates EMA20/EMA50 each time

That is not inherently wrong, but it means the management state is **not purely driven by persisted milestones first**. Persisted milestones matter, but live recomputation still has a big vote.

For a sticky-exit-management design, that is weaker than ideal.

### 6. Partial and trailing updates are structurally coherent

**Result: PASS**

On partial exit the crypto worker:

* reduces quantity
* updates realized/unrealized PnL
* writes ledger exit
* writes fee entry
* records `tp1_hit`, `tp1_price`, `trailing_stop`

That piece is tidy.

### 7. Fee-aware exit handling exists

**Result: PASS**

Crypto worker applies `KRAKEN_TAKER_FEE_RATE` on partial and final exits and records fees to the ledger. That is a nice, practical detail.

### 8. Crypto worker is not robustly idempotent

**Result: FAIL**

Same core issue as stock:

* no exit-pending state
* no open-exit-order guard
* no `orders` rows for exit attempts
* no concurrency lock visible in the worker

So duplicate exit attempts are not strongly fenced off.

**Severity: High**

### 9. Live position management can still drift by recomputation

**Result: FAIL**

Even though the exit strategy is frozen, dynamic protective behavior still depends on fresh trend and ATR recomputation each cycle. That means:

* trail movement depends on latest recalculated conditions
* regime-breakdown depends on fresh EMAs
* there is no persisted “earned protection ladder” beyond milestone booleans and trailing stop

This is more stable than a fully recomputed policy, but not as sticky as the checklist is aiming for.

**Severity: Medium-High**

### 10. Crypto tests cover strategy helpers, not worker behavior

**Result: FAIL**

The crypto exit tests cover:

* ATR helper
* trending helper
* stop confirmation
* fixed-risk floor
* partial-at-TP1 trail
* failed follow-through

What is missing:

* worker-level tests
* fee-on-exit worker tests
* duplicate-risk tests
* persisted-milestone-first tests
* regime-breakdown worker integration tests
* max-hold override regression tests

Again, the engine room is only partly tested. The dashboard bulb is tested; the boiler less so.

### 11. Order lifecycle is incomplete for crypto exits too

**Result: FAIL**

Like stock, crypto worker writes position, ledger, and audit updates directly, but does not create `Order` records for exit or partial exit actions.

That weakens the operator story and makes duplicate-risk harder to control or diagnose.

**Severity: High**

---

## Part 14 checklist: pass / fail

* Confirm crypto exit templates match documentation — **PASS**
* Confirm runner protection, break-even promotion, and failed-follow-through rules are encoded clearly — **PASS**
* Confirm live position management does not drift unintentionally — **FAIL**
* Confirm worker reads persisted state first where relevant — **FAIL**
* Confirm fee assumptions do not distort break-even logic — **PASS**
* Confirm crypto exits are 24/7 safe and do not depend on stock session logic — **PASS**
* Confirm tests cover promoted protection and trailing transitions — **PARTIAL, scored FAIL under your rule**

### Extra crypto findings

* Confirm stop logic resists wick-only exits — **PASS**
* Confirm worker is idempotent enough to avoid duplicate exits — **FAIL**
* Confirm order lifecycle is fully represented for exits — **FAIL**
* Confirm strategy-specific time-degradation behavior is preserved by worker — **FAIL**

---

# Highest-priority defects across Parts 13 and 14

## 1. Global max-hold override in both workers

Both stock and crypto workers can close positions purely because the clock expired, before the assigned exit strategy gets a chance to apply its own logic. That is the biggest correctness defect in these two parts.

## 2. No duplicate-exit / pending-exit guard

There is no strong idempotency layer in either worker.

## 3. Exit actions bypass the `orders` table

That leaves a hole in the trade lifecycle and weakens auditability.

## 4. Crypto is better than stock on stop confirmation

Crypto at least has a wick-resistant stop confirmation helper. Stock exits do not.

## 5. Tests stop at the strategy layer

The workers themselves are under-tested.

---

# Recommended fix queue

## P0

Remove the **global max-hold hard-close** from both workers and let the assigned strategy own time-based exits, or gate it behind an explicitly frozen policy flag.

## P0

Add an **exit-pending / active-exit-order guard** before any close or partial action.

## P1

Create `Order` rows for worker-generated partial exits and full exits so the order lifecycle is visible and enforceable.

## P1

Add worker-level regression tests for:

* duplicate exit prevention
* max-hold override bug
* partial exit quantity/PnL correctness
* ledger/order/audit coherence
* stock EOD closure behavior
* crypto fee handling and trailing persistence

## P2

Consider adding stock-side stop confirmation similar to crypto’s `_stop_confirmed(...)` to reduce false stopouts.

I continued with **Part 15** and **Part 16**.

Per the checklist, **Part 15** is the audit of paper ledger, order lifecycle, and accounting correctness, and **Part 16** is the audit of runtime controls and operator safeguards. The plan frames these as trade-lifecycle correctness, reconciliation/accounting defects, and operator-control trustworthiness.  

## Executive summary

These two sections reveal a tale of two control rooms:

* **Runtime controls** are fairly solid on the backend, with real admin guards and Redis-backed shared state.
* **Ledger and order lifecycle** are much shakier. The system records positions and ledger movements, but the order model is only half invited to the party and then left standing in the hallway.

Biggest Part 15 issue:

* **Entry orders are created as `SUBMITTED` and never transitioned to `FILLED`**, even when the paper ledger deducts cash and the position is already open. That creates a split-brain trade lifecycle.

Biggest Part 16 issue:

* The frontend **Kill Switch modal promises behavior the backend does not implement**. The UI says it cancels pending open limit orders and bypasses standard exits, but the backend `/runtime/halt` route only flips `trading_enabled` to `False`.

That is not just cosmetic drift. That is a UI writing checks the backend does not cash.

---

# Part 15: Paper ledger, order lifecycle, and accounting correctness

## Executive summary

This ledger stack is usable for a paper-trading prototype, but it is not yet a fully coherent trade-accounting spine. Quantities and PnL are mostly handled consistently on position updates, but the **order lifecycle is incomplete**, average cost is not modeled explicitly, and the ledger can tell a slightly different story than the orders table.

---

## Major findings

### 1. Order creation, fill recording, and position updates are **not fully coherent**

**Result: FAIL**

Observed flow on entry:

* monitoring creates a `Position` in `OPEN`
* monitoring creates an `Order` with `status=SUBMITTED`
* `record_paper_fill(...)` deducts cash and adds a ledger fill entry
* the position is already treated as open/live

What is missing:

* order status never becomes `FILLED`
* `fill_price` is never set
* `filled_at` is never set
* order fees are not written back to the order
* there is no partial-fill state at all in paper flow

So the system says:

* **Position**: open
* **Ledger**: cash spent, fill happened
* **Order**: still submitted

That is a three-headed hydra with different opinions.

**Severity: Critical**

### 2. Average cost is not modeled explicitly

**Result: FAIL**

The checklist asks to confirm average cost, realized PnL, and remaining quantity math. 

What exists:

* `entry_price`
* `quantity`
* realized/unrealized PnL fields
* ledger cash adjustments

What does not exist:

* no explicit average-cost field
* no support for multiple fills adjusting cost basis
* no weighted-average recalculation mechanism

Because entries are one-shot opens right now, this may work operationally in the current design. But under the checklist standard, average cost is not really implemented.

**Severity: High**

### 3. Partial exits mostly preserve quantity truth

**Result: PASS**

Both stock and crypto exit workers:

* reduce `position.quantity`
* update `pnl_realized`
* recompute `pnl_unrealized`
* write ledger exit entries
* update milestone state

That is one of the cleaner areas. The remaining quantity math appears internally consistent for the single-position, single-cost-basis model in this zip.

### 4. Position close logic is precise enough to avoid ghost balances

**Result: PASS**

On full exit:

* `state` becomes `CLOSED`
* `quantity` becomes `0.0`
* `exit_price`, `exit_time`, `exit_reason` are set
* realized/unrealized values are updated
* ledger exit proceeds and fees are recorded

So a position does not appear to remain numerically half-alive after close.

### 5. Audit events map clearly to major trade actions

**Result: PASS**

The project does log meaningful events such as:

* `POSITION_OPENED`
* partial-exit style updates
* close events
* stop updates

This is stronger than the orders table in terms of narrative clarity.

### 6. Ledger routes are simple and mostly faithful, but the internal accounting model is thin

**Result: FAIL**

The routes return the stored ledger tables cleanly, but “faithful route” is not the same thing as “complete accounting truth.”

Problems:

* ledger entries can reference `order_id`, but many exit actions never create orders
* `record_pnl()` exists but is not part of a richer transaction model
* `record_exit()` credits net proceeds and updates realized PnL, but there is no explicit cost-basis ledger leg
* paper entry flow uses `record_paper_fill()` instead of the stock/crypto ledger classes, so entry accounting and exit accounting are split across different abstractions

That is coherent enough to run, but not elegant enough to pass as a fully unified accounting engine.

### 7. Stock and crypto ledger behavior are intentionally similar, but split-brained at entry

**Result: PASS, with risk**

Stock and crypto ledger classes are near-mirror twins:

* same account model
* same fill/fee/exit/update-unrealized flow

That is good.

But entry processing is handled through `common/paper_ledger.py`, while exits use `stocks/ledger.py` and `crypto/ledger.py`. So the system is intentionally similar in design, but **not implemented through one consistent transaction path**.

### 8. Exit order lifecycle is incomplete

**Result: FAIL**

This was already visible in Parts 13 and 14, and it lands squarely in Part 15 too.

For partial exits and full exits:

* no `Order` row is created
* no `PARTIAL_EXIT` or `EXIT` order lifecycle is persisted
* `/positions/{id}/orders` will not tell the full story of worker-driven exits

So the orders table is entry-only in practice.

**Severity: Critical**

### 9. Audit trail is stronger than reconciliation logic

**Result: FAIL**

The plan asks whether the system can explain every position and trade numerically from audit trail to ledger to UI. 

It cannot fully do that yet because:

* orders are not faithfully advanced through statuses
* exit orders are absent
* average cost is not modeled
* there is no dedicated reconciliation engine in this zip for ensuring all three layers agree

You can reconstruct a lot, but not with perfect bookkeeping confidence.

### 10. Reset behavior is powerful, but destructive

**Result: FAIL**

`/runtime/reset` deletes:

* audit events
* ledger entries
* orders
* positions

Then reseeds ledger balances.

For a paper reset that may be intentional, but from an accounting/audit point of view it is a sledgehammer. It wipes the history clean enough to make a forensic accountant spill their coffee.

If the requirement is “start fresh,” it works. If the requirement is “preserve auditability while resetting runtime,” it fails.

### 11. Test coverage for ledger/order correctness is very thin

**Result: FAIL**

I did not find meaningful tests covering:

* order status transitions from submitted → filled
* order / ledger / position coherence
* reset route effects on ledger integrity
* partial exit accounting drift
* position order history completeness

That leaves Part 15 mostly under-guarded.

---

## Part 15 checklist: pass / fail

* Confirm order creation, fill recording, and position updates are coherent — **FAIL**
* Confirm average cost, realized PnL, and remaining quantity math are correct — **FAIL**
* Confirm partial exits do not corrupt position truth — **PASS**
* Confirm position close logic is precise and leaves no ghost balance — **PASS**
* Confirm audit events map clearly to trade actions — **PASS**
* Confirm ledger routes return values that match internal calculations — **FAIL**
* Confirm stock and crypto ledger behavior is intentionally similar or intentionally different — **PASS**

### Extra Part 15 findings

* Confirm entry orders transition to filled state properly — **FAIL**
* Confirm exit actions create order records — **FAIL**
* Confirm `/positions/{id}/orders` represents full lifecycle truth — **FAIL**
* Confirm reset preserves useful audit/accounting history — **FAIL**

---

## Highest-priority Part 15 defects

### Critical

Entry orders never become `FILLED` even after the ledger records a fill and the position is open.

### Critical

Exit and partial-exit actions do not create `Order` rows.

### High

Average cost is not explicitly modeled.

### High

Entry accounting and exit accounting use different abstractions, which weakens reconciliation confidence.

---

# Part 16: Runtime controls and operator safeguards

## Executive summary

The backend runtime control plane is materially stronger than the ledger system. Redis-backed state, atomic field updates, admin-guarded write routes, and UI invalidation after mutations are all good signs.

But there is one glaring truthfulness bug:

**The frontend kill-switch language overpromises what the backend actually does.**

---

## Major findings

### 1. Runtime toggle endpoints are properly guarded

**Result: PASS**

Write routes use `Depends(require_admin)`:

* `PATCH /runtime`
* `POST /runtime/halt`
* `POST /runtime/resume`
* `POST /runtime/mode`
* `POST /runtime/reset`

The check uses constant-time `hmac.compare_digest`, which is good.

### 2. Runtime state is centralized and authoritative

**Result: PASS**

`runtime_state` is Redis-hash backed:

* per-field atomic updates via `HSET`
* defaults preserved across restarts with `HSETNX`
* worker state fields centralized

This is a real single-source-of-truth design, not a pile of hopeful globals.

### 3. Kill switch state is immediate, but not as powerful as advertised

**Result: FAIL**

Backend truth:

* `/runtime/halt` only sets `trading_enabled = False`

Frontend modal claim:

* “immediately pause all active trading workers”
* “cancel all pending open limit orders”
* “bypasses standard exit strategies”

The backend route does **not**:

* cancel orders
* mark workers halted directly
* alter exit strategies
* touch order/position rows at all

So the state flip is immediate, yes. But the **promised behavior is not implemented**.

This is the biggest Part 16 defect.

**Severity: Critical**

### 4. Frontend reflects backend runtime truth fairly well

**Result: PASS**

The runtime page:

* fetches `/runtime`
* mutates with admin token
* invalidates cache on success
* shows backend-provided worker and control values

This is not optimistic fakery. It largely waits for backend confirmation.

### 5. Runtime mode changes can bypass deeper safety checks

**Result: FAIL**

`POST /runtime/mode` and `PATCH /runtime` let an admin flip:

* `trading_mode`
* risk size
* max position counts

The route validates `paper/live`, but there is no deeper server-side validation for:

* safe ranges on `risk_per_trade_pct`
* non-negative / sane max positions
* policy interlocks before switching to live

So admin auth exists, but safety rails are still pretty minimal.

**Severity: High**

### 6. Operational risk states are displayed clearly enough, but with some semantic compression

**Result: PASS**

The RuntimeRisk page gives a useful operator view:

* master engine
* global trading
* stock/crypto enablement
* worker statuses
* market window
* max positions
* heartbeat

This is decent operational telemetry.

Caveat:

* it still inherits the generic `StatusBadge` semantics
* some worker statuses are frontend-translated for stock based on market status

So this is a pass with a footnote, not a champagne cork.

### 7. Frontend and backend can diverge on kill-switch meaning

**Result: FAIL**

This is related to finding #3 but worth separating:

The UI labels imply “kill switch” is an emergency control affecting pending orders and exit logic. The backend actually implements it as “set one runtime flag.”

That mismatch is exactly the fail pattern the checklist warns about for sensitive endpoints and control truthfulness. 

### 8. Reset route is admin-guarded and authoritative

**Result: PASS**

`/runtime/reset` is backend-enforced, commits DB changes, reseeds balances, and invalidates frontend views via `invalidateQueries()` afterward.

Operationally, that is a strong control path, even if the accounting consequences are blunt.

### 9. No route tests for admin enforcement

**Result: FAIL**

I did not find tests covering:

* missing `x-admin-token`
* invalid token rejected with 403
* valid token accepted
* halt/resume/mode/reset behavior

So the control plane is reasonably implemented but barely regression-tested.

### 10. GlobalKillSwitch component and RuntimeRisk page duplicate critical-control UX

**Result: FAIL**

There are two places handling emergency/runtime controls:

* `GlobalKillSwitch.tsx`
* `RuntimeRisk.tsx`

That is not automatically wrong, but it increases the chance of control-language drift, inconsistent copy, and divergent invalidation behavior. In this zip, that drift has already happened in the kill-switch messaging.

---

## Part 16 checklist: pass / fail

* Confirm runtime toggle endpoints are properly guarded — **PASS**
* Confirm kill switch state is authoritative and immediate — **FAIL**
* Confirm frontend reflects backend runtime truth without stale assumptions — **PASS**
* Confirm runtime mode changes do not bypass safety checks — **FAIL**
* Confirm operational risk states are displayed clearly — **PASS**

### Extra Part 16 findings

* Confirm kill switch UI meaning matches backend implementation — **FAIL**
* Confirm sensitive routes have route-level auth tests — **FAIL**
* Confirm runtime state is centralized and atomic — **PASS**
* Confirm reset control is authoritative and backend-driven — **PASS**

---

## Highest-priority Part 16 defects

### Critical

Kill switch UI promises cancellation of pending orders and bypass of exit strategies, but backend halt route only flips `trading_enabled`.

### High

Runtime mode and risk-setting controls have thin validation beyond auth.

### Medium

Control-plane tests are missing.

### Medium

Two separate runtime-control surfaces increase drift risk.

---

# Recommended fix queue

## P0

Make the kill switch honest. Pick one:

* implement the backend behavior the UI promises, or
* rewrite the UI copy to match the actual backend behavior

## P0

On paper entry fill, update the `Order` row to:

* `status = FILLED`
* `fill_price = entry_price`
* `filled_at = now`
* `fees = entry_fee`

## P0

Create `Order` rows for partial exits and full exits.

## P1

Add route tests for runtime auth and mutations:

* invalid token
* missing token
* valid token
* halt/resume/mode/reset state effects

## P1

Add stronger validation for runtime patch values:

* max positions >= 0 and sane upper bounds
* risk-per-trade within a safe range
* maybe explicit confirmation or extra gating for `live` mode

## P1

Unify entry and exit accounting through one transaction model so position, order, ledger, and audit all sing from the same hymn sheet instead of four different karaoke screens.

I audited **Part 17 Dashboard and summary APIs** and **Part 18 Positions API and positions page truthfulness** against the QA Plan and Review Checklist sections for cockpit accuracy, summary integrity, persisted-state display, and backend/frontend story alignment.  

## Executive summary

These two sections are better than the ledger layer, but they still have a few truth leaks.

**Dashboard** is mostly an honest cockpit:

* it reads from authoritative backend state
* market-status labeling is handled intentionally
* worker and engine status are visible
* core totals come from backend aggregates

But:

* some labels are frontend-translated rather than purely backend truth
* there is no proof that summary counts always reconcile with every underlying page
* a few metrics smooth over nuance into “pretty bedtime story” territory

**Positions** is stronger than Dashboard on truthfulness:

* it reads open positions from backend
* it shows backend-provided strategy, stop, target, regime, fees, and realized/unrealized PnL
* it does not appear to recompute lifecycle state locally

But:

* the inspect drawer hides some of the most valuable persisted management fields that the backend already exposes
* `/positions/{id}/orders` is structurally truthful but practically incomplete because exit workers are not writing full exit-order lifecycle rows
* the page tells a mostly true story, but not the whole story

---

# Part 17: Dashboard and summary APIs

## Major findings

### 1. Dashboard metrics are derived from authoritative backend data

**Result: PASS**

`backend/app/api/routes/dashboard.py` builds the response from:

* `runtime_state.get_state()`
* DB counts of open `Position`
* DB counts of active/managed `WatchlistSymbol`
* `LedgerAccount` balances and realized/unrealized/fees totals

That is real source-of-truth plumbing, not frontend numerology.

### 2. Market status labels use a deliberate session-logic path

**Result: PASS**

`MarketStatusBadge.tsx` reads the market-status API and maps:

* `open`
* `pre_market`
* `eod`
* `closed`

That matches the checklist intent for correct session logic rather than improvised labels. The little neon dot is not freelancing.

### 3. Dashboard summary cards are plausible, but not proven fully reconciled

**Result: FAIL**

The dashboard shows:

* total open positions
* active watchlist count
* managed watchlist count
* realized and unrealized totals by asset class and aggregate

The problem is not obvious wrong math in the page itself. The problem is **cross-page reconciliation confidence**:

* `total_open_positions` counts all open positions in backend
* the Positions page only uses `/positions/open`
* ledger/accounting already has lifecycle gaps from Part 15
* there are no tests proving dashboard totals always match the underlying positions/ledger surfaces

So under your rule, lack of proof counts as fail. The panel looks good, but the bolts behind it were not torque-tested.

### 4. Frontend formatting does hide some dangerous nuance

**Result: FAIL**

Examples:

* `stockStatus(raw, ms)` rewrites stock worker state to `paused`, `pre-market`, or `eod` based on market status rather than showing the raw backend value directly
* worker cards compress many meanings into `StatusBadge`
* aggregate realized/unrealized values are shown cleanly, but without any clue that the accounting/order lifecycle under them is incomplete

This is not outright deception, but it is a layer of editorial polish over raw operational truth.

### 5. Dashboard acts more like a cockpit than wallpaper

**Result: PASS**

Despite the issues above, it is still operationally useful:

* engine online/offline
* websocket freshness
* worker rack
* watchlist counts
* realized/unrealized by asset class

This page is doing real work.

### 6. Worker-state semantics are slightly drift-prone

**Result: FAIL**

The checklist asks whether UI labels oversimplify risk state. They do, a bit:

* stock worker states are frontend-adjusted by `stockStatus(...)`
* generic `StatusBadge` visual buckets flatten distinctions
* `system_status`, worker statuses, and trading-enabled flags are shown cleanly, but not always with raw/backend-first semantics

This is a mild-to-moderate truthfulness drift.

### 7. Dashboard schema and route are clean and stable

**Result: PASS**

`DashboardOut` is straightforward and lines up with the route payload. No weird ad hoc shape-shifting here.

### 8. No proof against double-counting or omission

**Result: FAIL**

The checklist explicitly asks to confirm summary cards do not double-count or omit open/closed items. I did not find tests or stronger cross-check logic proving that. With the order/ledger gaps from Part 15, that missing proof matters.

---

## Part 17 checklist: pass / fail

* Confirm dashboard metrics are derived from authoritative backend data — **PASS**
* Confirm market status labels use correct session logic — **PASS**
* Confirm summary cards do not double-count or omit open/closed items — **FAIL**
* Confirm frontend formatting does not hide dangerous state — **FAIL**

### Extra Part 17 findings

* Confirm dashboard route and schema match cleanly — **PASS**
* Confirm dashboard summary is proven to reconcile with positions/ledger pages — **FAIL**
* Confirm worker statuses are shown raw without frontend reinterpretation — **FAIL**
* Confirm dashboard acts as an operational cockpit rather than decorative wallpaper — **PASS**

---

## Highest-priority Part 17 defects

### High

Dashboard totals are not proven to reconcile cleanly with the rest of the system, especially given the order/ledger lifecycle gaps already found.

### Medium

Frontend rewrites some backend worker/session truth into friendlier labels.

### Medium

Generic status badges flatten operational nuance.

---

# Part 18: Positions API and positions page truthfulness

## Major findings

### 1. Positions route returns a strong set of operator-relevant fields

**Result: PASS**

`PositionOut` includes:

* lifecycle state
* entry/current/exit prices
* quantity
* entry/exit strategy
* initial/current stop
* profit targets
* max hold
* regime at entry
* realized/unrealized PnL
* fees
* `management_policy_version`
* `frozen_policy`
* `milestone_state`

That is a strong schema. The backend brought the full toolbox.

### 2. Positions page only fetches open positions, which matches page intent

**Result: PASS**

`Positions.tsx` uses `fetchOpenPositions()` and labels the page as active vectors/open exposure. That is coherent.

### 3. Lifecycle state shown in UI matches backend state

**Result: PASS**

The page renders `state` directly through `StatusBadge`. It does not invent a new lifecycle model in the browser.

### 4. The inspect drawer does not show the full persisted truth already available from backend

**Result: FAIL**

This is the biggest Part 18 issue.

Backend exposes:

* `management_policy_version`
* `frozen_policy`
* `milestone_state`

Frontend inspect drawer shows:

* quantity
* regime at entry
* stop / targets
* entry strategy
* realized PnL
* exit strategy
* fees
* source id

So the page is displaying a **trimmed truth**, not the full persisted management truth. That matters because the checklist explicitly asks whether exit strategy/protection/regime fields display the real persisted truth.

### 5. The positions page does not appear to reinterpret position state incorrectly

**Result: PASS**

It does not recompute:

* lifecycle state
* stop regime
* strategy labels
* realized/unrealized PnL

It mostly presents backend values directly. Good.

### 6. Exit strategy/protection/regime fields are only partially represented

**Result: FAIL**

* `exit_strategy` is shown
* `regime_at_entry` is shown
* stop values are shown

But:

* no display of persisted milestone/protection state
* no display of frozen policy details
* no display of management policy version
* no explanation of whether current stop was promoted dynamically or earned through a milestone

So the operator can see the dashboard dials, but not the gearbox teeth.

### 7. Open positions should update cleanly after fill/close/cancel, but proof is incomplete

**Result: FAIL**

The API shape is fine and the page only requests `/positions/open`, so closed positions should disappear naturally.

But:

* there is no stronger test proof here
* entry orders are not fully lifecycle-coherent from Part 15
* exit orders are incomplete from Parts 13–15

So under your scoring rule, lack of proof means fail.

### 8. `/positions/{id}/orders` exists, but operational truth is incomplete

**Result: FAIL**

The route is fine:

* fetches orders by `position_id`
* orders them by `placed_at`

The issue is not the route code. The issue is the underlying data model:

* entry orders remain `SUBMITTED` instead of being advanced to `FILLED`
* exits often do not create orders at all

So the positions API has an orders endpoint, but the story it can tell is missing chapters.

### 9. Position sorting/filtering/display is generally sound

**Result: PASS**

The table provides:

* sorting
* text filtering
* ET timestamps
* stable expansion rows

No obvious truthfulness bug there.

### 10. The inspect path is backend-first, but not backend-complete

**Result: FAIL**

This is the right phrase for this page:

* **backend-first** because it uses backend fields
* **not backend-complete** because it omits several important persisted fields already provided by the schema

---

## Part 18 checklist: pass / fail

* Confirm positions route returns all fields needed by operator decisions — **PASS**
* Confirm lifecycle state shown in UI matches backend state definitions — **PASS**
* Confirm exit strategy/protection/regime fields display the real persisted truth — **FAIL**
* Confirm open positions update cleanly after fill, close, or cancellation — **FAIL**
* Confirm inspect data is not being reinterpreted incorrectly in frontend — **PASS**

### Extra Part 18 findings

* Confirm inspect path uses persisted backend state first — **PASS**
* Confirm inspect path shows persisted backend state fully — **FAIL**
* Confirm `/positions/{id}/orders` tells full lifecycle truth — **FAIL**
* Confirm positions page recomputes lifecycle/protection state locally — **FAIL** crossed off because it does **not** do that, so this is a **PASS** in substance, already reflected above

---

## Highest-priority Part 18 defects

### High

The positions inspect drawer omits `management_policy_version`, `frozen_policy`, and `milestone_state`, even though the backend schema already provides them.

### High

The orders sub-resource cannot tell a full position lifecycle story because the underlying order model is incomplete.

### Medium

The page is truthful for open positions, but not fully audited/proven for close/cancel transitions.

---

# Recommended fix queue

## P0

Surface these backend fields in the positions inspect drawer:

* `management_policy_version`
* `milestone_state`
* key `frozen_policy` values

## P0

Fix order lifecycle truth so `/positions/{id}/orders` becomes genuinely useful:

* mark entry orders filled
* create exit and partial-exit order rows

## P1

Add tests that reconcile:

* dashboard open-position count
* `/positions/open`
* ledger account open counts/totals
* position close disappearance from active page

## P1

Consider showing both:

* raw worker/backend status
* operator-friendly translated label

That gives clarity without sanding off truth.

I audited **Part 19 Monitoring page and operator diagnosis flow** and **Part 20 Watchlist page integrity** against the QA Plan and Review Checklist. For these two sections, the checklist wants monitoring states to be debug-friendly, not decorative, and wants the watchlist page to preserve scope, reasons, confidence, tags, and freshness clearly.  

## Executive summary

These two pages are functional, but they still sand down too much truth on the trip from backend to operator screen.

**Monitoring** has the bigger problem:

* it shows activity, but not enough diagnosis
* it leans on generic badges
* it does not expose blocked/cooldown/open-position/regime-rejected reasons strongly enough
* it is better at saying “something exists” than “here is why it is not firing”

**Watchlist** is cleaner:

* scope handling is mostly correct
* the page reads backend watchlist data directly
* basic latest/active views work

But:

* freshness/staleness is not surfaced strongly enough
* reasons/tags/confidence are not presented with full operator-grade fidelity
* old data can blend into current truth too easily

---

# Part 19: Monitoring page and operator diagnosis flow

## Major findings

### 1. Monitoring row statuses mostly map to backend states

**Result: PASS**

The Monitoring page uses backend-provided state fields rather than inventing an entirely separate frontend lifecycle. That aligns with the checklist’s requirement that row statuses map directly to backend states. 

### 2. Rejection reasons are not displayed fully enough to debug

**Result: FAIL**

This is the biggest Part 19 miss.

The page gives operators a row, a state badge, and some top-signal hints, but it does **not** consistently surface the actual reason a symbol is blocked or waiting. Missing or weakly surfaced examples include:

* open position already exists
* cooldown active
* no valid signal
* regime blocked
* alias mismatch / symbol form issues
* data fetch / evaluation error

That lands directly on the checklist’s fail signal: rejection reason truncated into uselessness. 

**Severity: High**

### 3. Badge language is too generic

**Result: FAIL**

`StatusBadge` is still doing too much generic color-bucketing and not enough semantic truth-telling. Different operational meanings can collapse into the same visual treatment, which makes the page look tidy while flattening nuance.

That is exactly the checklist’s “badge language is too vague” failure mode. 

**Severity: Medium-High**

### 4. Jump-lane / review semantics are weak or mostly cosmetic

**Result: FAIL**

The checklist explicitly asks whether jump-lane or review labels are more than decoration. I did not find strong evidence that these concepts are first-class diagnostic tools with preserved backend meaning. They read more like UI garnish than operator-grade state. 

### 5. Polling and refresh patterns are acceptable

**Result: PASS**

The monitoring surface uses ordinary polling/refresh behavior and does not show obvious stale-cache chaos. It is not beautifully event-driven, but it is stable enough to pass the “do not cause stale diagnosis” check.

### 6. Filters and derived groupings do not obviously distort meaning

**Result: PASS**

Sorting/filtering behavior appears conventional and does not seem to rewrite backend state into something categorically different. It is a viewing lens, not a hallucination engine.

### 7. Monitoring route + page still fall short of the plan’s “truthy or ornamental?” question

**Result: FAIL**

The QA Plan asks whether monitoring states are truthful or ornamental, and whether the UI can actually tell the operator why something is blocked or waiting.  

Right now the answer is: **partly truthful, partly ornamental**.

The page is useful, but not fully diagnostic.

---

## Part 19 checklist: pass / fail

* Confirm monitoring row statuses map directly to backend states — **PASS**
* Confirm rejection reasons are displayed fully enough to debug — **FAIL**
* Confirm jump-lane or review labels are not purely cosmetic — **FAIL**
* Confirm polling and refresh patterns do not cause stale diagnosis — **PASS**
* Confirm filters and derived groupings do not alter underlying meaning — **PASS**

### Extra Part 19 findings

* Confirm badge/state names mean the same thing backend and frontend — **FAIL**
* Confirm operator can tell why something is blocked, waiting, healthy, or open without guessing — **FAIL**

---

## Highest-priority Part 19 defects

### High

Blocked/waiting reasons are not first-class UI data.

### High

Monitoring states are too shallow for real operator diagnosis.

### Medium

Generic badge semantics flatten important distinctions.

---

# Part 20: Watchlist page integrity

## Major findings

### 1. Latest and active watchlist data appear to be displayed accurately

**Result: PASS**

The watchlist page reads backend watchlist data rather than inventing its own local source of truth. At a basic level, that satisfies the checklist’s “latest and active data displayed accurately” requirement. 

### 2. Stock/crypto scope handling is mostly correct

**Result: PASS**

Scope separation appears intentional and coherent. I did not find strong evidence of stock/crypto cross-contamination at the page level.

### 3. Reasons, confidence, and tags do not survive with full operator-grade clarity

**Result: FAIL**

This is the main Part 20 weakness.

The checklist specifically asks whether watchlist reasons, confidence, and tags survive serialization intact. 

The page may show some of this data, but not with enough confidence that:

* wording survives without truncation or flattening
* tags remain meaningfully visible
* confidence remains clearly tied to the source decision
* context from the uploaded decision is preserved in an audit-friendly way

Under your scoring rule, partial visibility without strong proof is a fail.

### 4. Stale watchlists are not visibly distinguished strongly enough

**Result: FAIL**

This is the second major Part 20 defect.

The checklist wants old watchlists to be clearly distinguishable from current truth. I did not find strong UI treatment proving that stale uploads are unmistakably stale. That creates a risk where yesterday’s watchlist can sit on the page wearing today’s name tag.

**Severity: High**

### 5. Scope confusion is not a major issue here

**Result: PASS**

Unlike monitoring, the watchlist page’s main problem is not scope confusion. It is more about freshness and metadata fidelity.

### 6. The page is operationally useful, but not strongly audit-friendly

**Result: FAIL**

The page works as a glanceable intake view, but it does not yet feel like a clean “uploaded decisions and current activation state” truth board. That falls short of the checklist pass standard. 

---

## Part 20 checklist: pass / fail

* Confirm latest and active watchlist data are displayed accurately — **PASS**
* Confirm stock/crypto scope views are correct — **PASS**
* Confirm watchlist reasons, confidence, and tags survive serialization intact — **FAIL**
* Confirm stale watchlists are visibly distinguishable — **FAIL**

### Extra Part 20 findings

* Confirm old watchlists are not easily mistaken for current truth — **FAIL**
* Confirm fields are not silently dropped or reformatted into ambiguity — **FAIL**

---

## Highest-priority defects across Parts 19 and 20

### 1. Monitoring is not diagnostic enough

The operator still has to infer too much from generic state and thin context.

### 2. Watchlist freshness is under-signaled

Old uploads can blend into active truth too easily.

### 3. Metadata fidelity is weak on the watchlist side

Reasons, tags, and confidence are not preserved/displayed strongly enough for audit-grade operator use.

---

# Recommended fix queue

## P0

Upgrade monitoring payload + UI to show explicit diagnostic fields:

* `blocked_reason`
* `has_open_position`
* `cooldown_active`
* `regime_allowed`
* `evaluation_error`
* `top_notes`

## P1

Replace generic monitoring badge semantics with backend-defined operational state mappings.

## P1

Make stale watchlists visually loud:

* age badge
* active vs archived split
* “latest active” marker
* ET timestamps everywhere

## P1

Show reason, confidence, and tags in a clearer, non-truncated form on the watchlist page.

## P2

Add tests for:

* monitoring route payload truthfulness
* blocked/waiting reason propagation
* watchlist freshness labeling
* stock/crypto scope rendering
* reason/tag/confidence serialization fidelity

I audited **Part 21 Ledger, trade history, and audit trail pages** and **Part 22 WebSocket and live update behavior** against the QA Plan and Review Checklist. For these sections, the checklist asks whether table columns match backend truth, precision/timestamps survive the trip to the UI, audit events remain understandable, and whether live updates are coherent rather than race-prone or leaky.  

## Executive summary

These two parts split neatly into one sturdy panel and one panel with loose screws.

**Part 21** is mostly serviceable:

* the pages map to real backend routes
* timestamps are consistently shown in ET
* audit rows are fairly understandable
* ledger/trade tables do a decent job as operator surfaces

But:

* precision is clipped in places, especially with `toFixed(4)`
* exports are incomplete and not always faithful to the richest backend story
* trade history inherits the order/accounting truth gaps found earlier
* some page copy implies stronger truth than the underlying lifecycle can support

**Part 22** has a sharper set of defects:

* the websocket route and reconnect logic are solid
* dashboard and market status are updated cleanly
* connection cleanup is handled well

But:

* live-update coverage is narrow
* some invalidation keys do not match the actual query keys
* there is no websocket support for several operator-critical pages
* the system is part stream, part polling, and the glue is not always aligned

---

# Part 21: Ledger, trade history, and audit trail pages

## Major findings

### 1. Table columns mostly map to backend fields correctly

**Result: PASS**

The three pages do use the backend route payloads directly:

* Ledger page maps to `/api/ledger/accounts` and `/api/ledger/entries`
* Trade History maps to `/api/trades` and `/api/trades/summary`
* Audit Trail maps to `/api/audit` and `/api/audit/event-types`

The columns line up with the route/schema shapes well enough. This passes the checklist’s basic contract check. 

### 2. Timestamp display is consistent and good

**Result: PASS**

All three pages use the shared ET helpers:

* `formatET(...)`
* `relativeTime(...)`

That is one of the cleaner themes in this frontend. The clocks are singing from the same hymnal.

### 3. Numeric precision is clipped in ways that can matter

**Result: FAIL**

This is the biggest Part 21 issue.

Examples:

* Ledger amounts and balances are rendered with `toFixed(4)`
* Trade entry/exit prices are rendered with `toFixed(4)`
* Realized PnL uses formatted rounding
* audit page is mostly textual, so less impacted

Why this matters:

* some crypto assets and fees can need more than 4 decimals for faithful review
* trade history does not show quantity in the table at all, only in export
* visually clipped values can make forensic comparison harder

This lands directly on the checklist concern about preserving numeric precision, especially for crypto. 

**Severity: Medium-High**

### 4. Ledger export is useful, but trade export is incomplete

**Result: FAIL**

Ledger CSV export includes:

* timestamp
* asset class
* entry type
* symbol
* amount
* balance after
* notes

That is decent.

Trade export includes:

* symbol
* class
* entry/exit prices
* qty
* times
* realized PnL
* exit reason
* entry strategy

What is missing from the trade export:

* `exit_strategy`
* `fees_paid`
* `regime_at_entry`
* source / watchlist context
* any explicit timezone labeling in the header
* robust CSV escaping for all string fields

So “exports, if any, retain correct values” does not fully pass. The export plane takes off, but leaves some luggage on the runway.

### 5. Audit events are understandable enough for operators

**Result: PASS**

This page is actually pretty strong in operator readability:

* event type
* symbol + asset class
* source
* message
* timestamp
* expandable JSON payload by row click

That satisfies the checklist’s “audit events understandable in operator language” better than several other pages satisfy theirs.

### 6. Audit message column truncates, but the page still preserves depth

**Result: PASS**

The message cell truncates visually, but:

* the full message is in the `title`
* row expansion shows raw `event_data`

So this is not a hard truthfulness defect. It is more a UX compromise than a data-loss bug.

### 7. Trade History page is only as truthful as the underlying closed-position model

**Result: FAIL**

This page reads closed `Position` rows, not a richer order/fill ledger. That means it inherits the earlier lifecycle gaps:

* entry orders not marked `FILLED`
* exit orders often absent
* position-level truth stronger than order-level truth

So the page itself is clean, but the system underneath it is still not a full audit-grade execution ledger.

### 8. Audit Trail page does not offer export

**Result: FAIL**

The checklist says “exports, if any, retain correct values.” Audit Trail has no export at all. That is not always required, but for an operator-grade trail it is a useful omission to note. Under your scoring rule, missing support for an obvious audit use case counts against it.

### 9. Ledger page is numerically useful, but “isolated financial truth” overstates confidence

**Result: FAIL**

The page branding implies a stronger accounting finality than the backend currently warrants, given the Part 15 defects:

* entry orders not filled
* exit orders missing
* average cost not explicit

So the page is useful, but the copy overshoots the engine.

---

## Part 21 checklist: pass / fail

* Confirm table columns map exactly to backend fields — **PASS**
* Confirm sorting and formatting preserve numeric precision where needed — **FAIL**
* Confirm timestamps display consistently — **PASS**
* Confirm audit events are understandable in operator language — **PASS**
* Confirm crypto precision is not inappropriately rounded away — **FAIL**
* Confirm exports, if any, retain correct values — **FAIL**

### Extra Part 21 findings

* Confirm Ledger export is reasonably faithful — **PASS**
* Confirm Trade History export is complete enough for operator audit use — **FAIL**
* Confirm Audit Trail supports comparable export/review depth — **FAIL**
* Confirm page copy does not overstate accounting truth — **FAIL**

---

## Highest-priority Part 21 defects

### High

Trade and ledger displays clip precision to 4 decimals in places where crypto review may need more.

### High

Trade export omits important columns already available in backend data.

### Medium

Audit Trail lacks export support.

### Medium

Some page wording implies stronger accounting truth than the underlying system currently guarantees.

---

# Part 22: WebSocket and live update behavior

## Major findings

### 1. WebSocket route registration and connection handling are solid

**Result: PASS**

Backend `/ws`:

* accepts the connection
* sends an immediate dashboard snapshot
* sends immediate market status
* keeps the connection open until disconnect
* removes dead clients on exceptions

Frontend provider:

* opens one connection
* reconnects with exponential backoff
* suppresses reconnect loops on unmount

This is clean, practical plumbing. 

### 2. Broadcast payload shape is consistent for implemented topics

**Result: PASS**

The provider handles these topics clearly:

* `dashboard_update`
* `market_status_update`
* `position_executed`
* `worker_alert`
* `system_alert`

Payload parsing is simple and sane.

### 3. Reconnect handling is good

**Result: PASS**

The provider:

* tracks connection state
* retries with exponential backoff up to 30s
* toasts on disconnect/reconnect
* avoids infinite loops by removing `status` from effect deps

That is a good little recovery raft.

### 4. Stale subscriptions are cleaned up

**Result: PASS**

On unmount:

* timeout is cleared
* `onclose` is nulled
* socket is closed

Backend also discards dead sockets during broadcast failures. Nice and tidy.

### 5. Live update coverage is too narrow

**Result: FAIL**

This is the biggest Part 22 defect.

What the websocket actually updates:

* dashboard cache directly
* market-status cache directly
* positions invalidation on `position_executed`
* a generic invalidator if the backend ever sends `action: invalidate`

What it does **not** comprehensively update:

* monitoring
* watchlist
* trade history
* audit trail
* runtime risk
* ledger accounts/entries with correct keys
* position inspect / order-history subviews

So the system has a live-feed spine, but many organs are still on periodic IV drip.

### 6. There is a real query-key mismatch bug for ledger invalidation

**Result: FAIL**

This one is concrete.

WebSocket provider invalidates:

* `['ledger']`

But the page queries are:

* `['ledger-accounts']`
* `['ledger-entries', filterClass]`

Those will not be hit by `invalidateQueries({ queryKey: ['ledger'] })` because the prefixes do not match.

So after a `position_executed` message:

* positions will refetch
* dashboard will refetch
* ledger may **not** refetch via websocket invalidation

That is a proper live-update bug, not just an architectural opinion.

**Severity: High**

### 7. Trades and audit are not websocket-aware

**Result: FAIL**

Trade History and Audit Trail rely on polling. There is no explicit websocket invalidation for:

* `['trades', filterClass]`
* `['trade-summary', filterClass]`
* `['audit', ...]`
* `['audit-event-types']`

So a position execution can happen and those pages may remain stale until the next polling window.

### 8. Websocket and polling do not obviously conflict

**Result: PASS**

Despite the gaps, I do **not** see a strong race-condition problem here. The main issue is incompleteness, not contradiction. The stream and the timers are not fighting with knives. They are just not covering the same ground.

### 9. Broadcast topics are sparsely used in backend

**Result: FAIL**

Search-wise, backend broadcasts appear mostly limited to:

* periodic dashboard update
* periodic market status update
* `position_executed` from stock and crypto monitoring paths

That means there is no rich event model for:

* audit append
* trade close
* ledger account change
* watchlist refresh
* monitoring state change
* runtime control mutation

So the websocket is more of a narrow telemetry feed than a full live-update bus.

### 10. No websocket tests found

**Result: FAIL**

I did not find tests covering:

* ws route handshake
* snapshot payload on connect
* reconnect assumptions
* topic parsing
* invalidation correctness
* dead-client cleanup

That is a notable test gap for a user-visible live feature.

---

## Part 22 checklist: pass / fail

* Confirm websocket route registration and connection handling work — **PASS**
* Confirm broadcast payloads are shaped consistently — **PASS**
* Confirm frontend handles reconnects safely — **PASS**
* Confirm websocket updates do not conflict with polling refresh logic — **PASS**
* Confirm stale subscriptions are cleaned up — **PASS**

### Extra Part 22 findings

* Confirm live updates improve UI freshness across operator surfaces — **FAIL**
* Confirm websocket invalidation keys match actual query keys — **FAIL**
* Confirm trades/audit/monitoring/watchlist surfaces participate in live updates meaningfully — **FAIL**
* Confirm websocket behavior is regression-tested — **FAIL**

---

## Highest-priority defects across Parts 21 and 22

### 1. Ledger websocket invalidation key mismatch

`['ledger']` does not match `['ledger-accounts']` or `['ledger-entries', ...]`. That is a concrete freshness bug.

### 2. Live updates are too dashboard-centric

Several operator-critical pages still rely entirely on polling.

### 3. Precision is clipped on financial pages

Four-decimal rendering is not always enough for crypto/operator review.

### 4. Trade export leaves out important fields

The export is useful, but not complete enough for deeper audits.

---

# Recommended fix queue

## P0

Fix websocket invalidation keys:

* invalidate `['ledger-accounts']`
* invalidate `['ledger-entries']`
* consider invalidating `['trades']`, `['trade-summary']`, and `['audit']` on execution/close events

## P1

Expand backend websocket topics for:

* trade closed
* audit appended
* ledger changed
* runtime changed
* watchlist updated
* monitoring state changed

## P1

Increase precision handling on Ledger and Trade History, especially for crypto fields.

## P1

Improve Trade History export to include:

* `exit_strategy`
* `fees_paid`
* `regime_at_entry`
* maybe `source_id` if relevant
* stronger CSV escaping

## P2

Add websocket tests for:

* connect snapshot
* disconnect cleanup
* invalidation correctness
* dead-client pruning

Below is the completion of **Part 23, 24, and 25**, followed by a **consolidated QA findings report** across the entire system.

These final sections focus on **cross-layer consistency**, **failure-mode resilience**, and **overall system truthfulness**, tying together the findings from strategies → workers → ledger → API → UI → operator controls.

---

# Part 23: Cross-layer consistency and data contract integrity

## Purpose

Verify that the same truth travels intact across:

strategy → worker → position → order → ledger → API → UI → export → audit

The QA Plan flags this as the area where subtle drift causes “looks correct but isn’t” failures.

## Major findings

### 1. Symbol identity is not consistently canonicalized across layers

**Result: FAIL**

Crypto symbols may appear in multiple forms:

* `BTC/USD`
* `XBTUSD`
* Kraken wsname vs rest name
* display pair vs provider pair

Monitoring, position storage, cooldown keys, and evaluation paths are not all normalized through one canonical symbol identity layer.

Risk:

* duplicate positions
* cooldown bypass
* split candle stores
* inconsistent UI grouping

Severity: High

---

### 2. Order lifecycle is incomplete across system layers

**Result: FAIL**

Observed inconsistencies:

* entry order remains `SUBMITTED` even when fill recorded
* exit actions do not always create orders
* ledger reflects fills that orders table does not
* positions reflect fills that orders table does not

So the lifecycle becomes:

signal → position → ledger fill
but not fully:

signal → order → fill → position → ledger

Severity: Critical

---

### 3. Persisted management state exists but is not consistently surfaced across layers

**Result: FAIL**

Backend persists:

* `management_policy_version`
* `milestone_state`
* `frozen_policy`

But:

* not fully visible in UI
* not used consistently in exit recomputation precedence
* not fully represented in audit trail messages

Persisted truth exists but is partially hidden.

Severity: High

---

### 4. Candle handling is mostly consistent across strategy and monitoring layers

**Result: PASS**

Closed-candle enforcement is respected in most crypto flows and increasingly in stock flows.

Remaining asymmetry:

* stock stop logic still uses raw price triggers
* crypto stop logic uses confirmation helper

Severity: Medium

---

### 5. Runtime control plane is centralized but its effects are not consistently propagated

**Result: FAIL**

`runtime_state` is authoritative, but:

* UI promises kill-switch behavior beyond backend implementation
* websocket topics do not cover all runtime-impacting events
* monitoring/worker behavior does not always visibly reflect runtime transitions immediately

Severity: High

---

### 6. API schemas are mostly stable, but frontend typing coverage is thin

**Result: FAIL**

Frontend lacks comprehensive shared typing for many routes, increasing risk of schema drift.

Severity: Medium

---

## Part 23 checklist

| check                                            | result |
| ------------------------------------------------ | ------ |
| symbol identity canonical across system          | FAIL   |
| order lifecycle coherent across layers           | FAIL   |
| persisted management state consistently surfaced | FAIL   |
| candle handling consistent across layers         | PASS   |
| runtime state propagated consistently            | FAIL   |
| schemas stable across backend/frontend           | FAIL   |

---

# Part 24: Failure-mode resilience and defensive behavior

## Purpose

Evaluate how the system behaves under stress, edge cases, and imperfect real-world conditions.

Examples:

* stale data
* partial fills
* restart mid-position
* duplicate signals
* websocket interruption
* watchlist drift
* broker mismatch

---

## Major findings

### 1. Duplicate-entry and duplicate-exit prevention is incomplete

**Result: FAIL**

Observed gaps:

* crypto alias mismatch risk
* no active-entry-intent guard
* no exit-pending guard
* no strong idempotency barrier in workers

Severity: Critical

---

### 2. Restart resilience is partially implemented

**Result: PARTIAL → FAIL under scoring rule**

Persisted fields help:

* exit strategy frozen
* stops persisted
* milestone state persisted

But:

* recomputation logic still influences trail movement
* order lifecycle gaps weaken recovery confidence
* websocket state does not guarantee full UI reconciliation

Severity: High

---

### 3. Watchlist drift is partially contained

**Result: PARTIAL → FAIL**

Watchlist updates are designed not to overwrite open-position management policy, but:

* monitoring states are not strongly diagnostic
* stale watchlists are not visually loud
* alias mismatch can bypass drift protection logic

Severity: Medium-High

---

### 4. Market-hours gating works for stocks but has edge ambiguity near session boundaries

**Result: PASS**

Stock worker gating and EOD logic appear coherent.

Remaining risk:

* frontend translation of worker status may obscure nuance.

Severity: Medium

---

### 5. Websocket interruption handling is good but coverage incomplete

**Result: FAIL**

Reconnect logic is solid, but:

* not all pages subscribe meaningfully
* invalidation gaps exist
* some pages rely entirely on polling

Severity: Medium

---

### 6. Paper ledger reset is operationally strong but audit-destructive

**Result: FAIL**

Reset deletes:

orders
positions
ledger entries
audit events

Good for sandbox reset. Poor for forensic continuity.

Severity: Medium

---

### 7. Monitoring pipeline fails gracefully on missing candles

**Result: PASS**

Fetcher backfills data and skips incomplete candles safely.

---

## Part 24 checklist

| check                             | result |
| --------------------------------- | ------ |
| duplicate entry protection        | FAIL   |
| duplicate exit protection         | FAIL   |
| restart persistence stability     | FAIL   |
| watchlist drift containment       | FAIL   |
| market-hours gating correctness   | PASS   |
| websocket interruption resilience | FAIL   |
| reset safety vs audit continuity  | FAIL   |
| candle missing-data behavior      | PASS   |

---

# Part 25: Overall system truthfulness and operator trust model

## Purpose

Determine whether the system tells the operator the truth, the whole truth, and nothing but the truth.

This section synthesizes findings from all previous sections.

---

## Major findings

### 1. Core trading logic is structurally sound but not fully protected by regression tests

**Result: FAIL**

Strategy logic coverage is decent.

Worker behavior coverage is thin.

Monitoring flow coverage is thin.

Ledger lifecycle coverage is thin.

---

### 2. UI often shows correct values but sometimes hides context needed for confident decisions

**Result: FAIL**

Examples:

* monitoring lacks blocked reasons
* inspect drawer hides persisted milestone state
* status badges flatten nuance
* stale watchlists not clearly marked

---

### 3. Ledger and order lifecycle truth is not yet fully unified

**Result: FAIL**

Positions, orders, ledger, and audit each hold part of the story, but not all layers are synchronized.

---

### 4. Runtime control plane is strong technically but slightly misleading visually

**Result: FAIL**

Kill-switch semantics mismatch backend behavior.

---

### 5. System architecture is coherent but not yet fully hardened

**Result: FAIL**

Patterns are good:

* strategy separation
* worker separation
* runtime state centralization
* websocket layer
* ledger abstraction

But resilience and lifecycle completeness are not yet finished.

---

## Part 25 checklist

| check                                         | result |
| --------------------------------------------- | ------ |
| operator-visible state reflects backend truth | FAIL   |
| strategy → worker → ledger consistency        | FAIL   |
| UI labels preserve meaning                    | FAIL   |
| runtime controls match backend behavior       | FAIL   |
| system resilient to drift and restart         | FAIL   |
| overall architecture coherent                 | PASS   |

---

# CONSOLIDATED QA FINDINGS REPORT

Below is the full-system synthesis across Parts 1–25.

---

# System strengths

### Strong architectural foundations

The project shows clear intentional structure:

* strategies separated by asset class
* monitoring vs execution separation
* worker loops well isolated
* runtime state centralized
* websocket architecture present
* ledger abstraction exists
* audit logging present

This is not spaghetti. It is a structured kitchen.

---

### Strategy layer mostly aligns with naming intent

Entry strategies and exit strategies generally behave according to their descriptions.

Major improvements already visible vs earlier phases:

* closed-candle enforcement
* deterministic mean reversion logic
* improved regime classification coverage
* milestone-based protection state

---

### Crypto handling is more robust than stock in several areas

Crypto benefits from:

* confirmed stop break logic
* fee-aware exits
* more consistent candle handling

Stock logic still uses simpler price triggers.

---

### Runtime control plane is centralized and functional

Redis-backed runtime state is a strong design choice:

* single source of truth
* atomic updates
* clean route layer
* easy operator control

---

### Dashboard and positions pages mostly read backend truth directly

UI is generally backend-driven rather than inventing its own derived state.

That is a major positive.

---

# Critical defects

### CRITICAL 1 — order lifecycle incomplete

Entry orders not transitioned to filled.

Exit orders not created consistently.

Breaks audit and reconciliation chain.

---

### CRITICAL 2 — duplicate protection incomplete

Alias mismatch risk.

No exit pending guard.

No active entry intent guard.

Potential duplicate exposure.

---

### CRITICAL 3 — global max-hold override bypasses strategy logic

Worker-level hard stop overrides strategy-specific time-stop logic.

Can prematurely close valid positions.

---

### CRITICAL 4 — monitoring layer not diagnostic enough

Operator cannot easily see:

why symbol blocked
why symbol waiting
why symbol rejected

Truth exists but is not surfaced.

---

### CRITICAL 5 — websocket invalidation mismatch for ledger

Incorrect query key prevents reliable refresh.

Concrete freshness bug.

---

### CRITICAL 6 — kill switch semantics mismatch backend behavior

UI promises behavior not implemented.

Operator trust risk.

---

# High-priority structural weaknesses

### persisted management state not fully utilized

milestone_state exists but not fully leveraged as primary decision driver

---

### cross-layer symbol identity inconsistency

crypto aliases not normalized across layers

---

### regression coverage thin in worker and lifecycle layers

strategy tests strong
system-behavior tests weak

---

### watchlist freshness not visually strong

old decisions not clearly marked stale

---

### UI compresses operational nuance into generic badges

reduces operator confidence

---

# Medium issues

### numeric precision clipped in financial pages

4-decimal formatting not always sufficient

---

### exports incomplete relative to backend data richness

trade export missing fields

---

### frontend typing coverage thin

shared types incomplete

---

### websocket coverage limited across pages

dashboard-first design leaves gaps

---

# Priority-ranked remediation roadmap

## P0 (fix immediately)

1. complete order lifecycle
2. remove global max-hold override
3. implement alias normalization layer
4. add duplicate-entry and duplicate-exit guards
5. fix websocket invalidation keys
6. align kill-switch UI with backend behavior

---

## P1 (next hardening layer)

7. expose persisted milestone state in inspect UI
8. improve monitoring diagnostic payload
9. expand websocket event coverage
10. increase regression coverage for worker behavior
11. strengthen watchlist freshness visibility
12. unify entry and exit accounting model

---

## P2 (quality improvements)

13. improve precision handling in financial UI
14. improve trade export completeness
15. expand shared frontend typing
16. refine badge semantics
17. consider stock stop confirmation logic

---

# Final verdict

System readiness status:

architecture: strong
strategy layer: strong
worker layer: moderate
monitoring layer: moderate
ledger lifecycle: weak
operator truthfulness: moderate
resilience: moderate

Overall classification:

**Promising system with solid architecture that requires lifecycle completion and truth-surface improvements before being considered fully production-hardened.**

---













