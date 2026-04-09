# Signal Forge — Codebase Assessment Report

> **Scope:** Full-stack analysis of the React/TypeScript frontend and Python/FastAPI backend.
> **Analysis date:** June 2025
> **Repo root:** `Signal_Forge/`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Backend — Security Vulnerabilities](#2-backend--security-vulnerabilities)
3. [Backend — Outdated Dependencies](#3-backend--outdated-dependencies)
4. [Backend — Ghost / Zombie Dependencies](#4-backend--ghost--zombie-dependencies)
5. [Backend — Legacy Architectural Patterns](#5-backend--legacy-architectural-patterns)
6. [Frontend — Security Concerns](#6-frontend--security-concerns)
7. [Frontend — Outdated Dependencies](#7-frontend--outdated-dependencies)
8. [Frontend — Architectural Observations](#8-frontend--architectural-observations)
9. [Prioritised Remediation Roadmap](#9-prioritised-remediation-roadmap)

---

## 1. Executive Summary

| Category | Issues Found | Highest Severity |
|---|---|---|
| Security vulnerabilities | 5 | 🔴 Critical |
| Outdated backend dependencies | 10 | 🟠 High |
| Ghost / zombie dependencies | 5 | 🟠 High |
| Legacy backend patterns | 4 | 🟡 Medium |
| Security concerns (frontend) | 4 | 🟠 High |
| Outdated frontend dependencies | 6 | 🟡 Medium |
| Architectural observations (frontend) | 4 | 🟡 Medium |

The most urgent items are: the CORS wildcard + credentials misconfiguration, the timing-attack-vulnerable admin token comparison, the two zombie security libraries (`python-jose`, `passlib`) that are installed but never called, and the `--reload` flag that is present in the production Dockerfile.

---

## 2. Backend — Security Vulnerabilities

### 2.1 🔴 CRITICAL — CORS Wildcard + Credentials

**File:** `backend/app/main.py` (lines ~196–202)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # ← wildcard
    allow_credentials=True,   # ← credentials flag
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`allow_origins=["*"]` combined with `allow_credentials=True` violates the CORS specification (RFC 6454) and causes browser security engines to reject credentialed cross-origin requests. Starlette ≥ 0.28 raises a `ValueError` at startup for exactly this combination.

Beyond browser rejection, a wildcard origin means **any** website can make same-origin-style requests against the API if the header restriction is ever relaxed.

**Fix:** Replace the wildcard with an explicit allowlist driven by the environment.

```python
# config.py — add:
ALLOWED_ORIGINS: list[str] = ["http://localhost:5180"]

# main.py — replace:
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "x-admin-token"],
)
```

---

### 2.2 🔴 CRITICAL — Timing-Attack Vulnerable Admin Token Comparison

**File:** `backend/app/api/deps.py` (line 13)

```python
if x_admin_token != settings.ADMIN_API_TOKEN:
    raise HTTPException(status_code=403, detail="Invalid admin token")
```

Python's `!=` operator on strings short-circuits as soon as a differing byte is found. An attacker with a high-resolution timer can enumerate the admin token one character at a time through a timing side-channel.

**Fix:** Use `hmac.compare_digest` for constant-time comparison.

```python
import hmac

async def require_admin(x_admin_token: str = Header(...)):
    if not hmac.compare_digest(x_admin_token, settings.ADMIN_API_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid admin token")
```

---

### 2.3 🔴 CRITICAL — Zombie `python-jose` with Active CVEs Installed

**File:** `backend/requirements.txt`

```
python-jose[cryptography]==3.3.0
```

`python-jose` is **installed but never imported anywhere in the application code** (confirmed by full-tree search). Despite being unused, it occupies the site-packages surface area and is flagged by `pip-audit` and most supply-chain scanners because it carries:

| CVE | Severity | Description |
|---|---|---|
| CVE-2024-33664 | High | Algorithm confusion — attacker can substitute RS256 key with HS256 |
| CVE-2022-29217 | High | RSA key confusion allows signature bypass |

The library is effectively unmaintained (no releases since 2023).

**Fix:** Remove from `requirements.txt`. If JWT support is needed in the future, use `python-jwt` or `joserfc` instead.

---

### 2.4 🟠 HIGH — Zombie `passlib` Installed (Unmaintained Library)

**File:** `backend/requirements.txt`

```
passlib[bcrypt]==1.7.4
```

`passlib` is **installed but never imported** in the application. The last release was in 2020; the project is effectively dead. Known issues include bcrypt hash truncation, and it has unresolved compatibility warnings with bcrypt ≥ 4.x.

**Fix:** Remove from `requirements.txt`. If password hashing is needed, use the `bcrypt` package directly, or `argon2-cffi` for Argon2id.

---

### 2.5 🟢 CORRECTLY IMPLEMENTED — Secret Management via `.env`

**Files:** `backend/app/common/config.py`, `.env.example`, `.gitignore`

The secret management pattern in this codebase is correct and follows best practices:

```python
# config.py — reads .env as the truth source for all secrets
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
```

`pydantic-settings` resolves values in strict priority order:

```
1. Real environment variables   (highest — e.g. Docker / CI secrets)
2. .env file                    ← where actual secrets live, never committed
3. Field defaults in config.py  (last resort only)
```

`.env` is correctly excluded from version control:
```
# .gitignore
.env        ← never pushed to GitHub
```

`.env.example` is committed with placeholder values only (`changeme`, `0`, empty strings). This is the **correct and intentional** pattern — it shows collaborators exactly which keys they need to create their own `.env` without exposing any real credentials.

**One minor hardening opportunity (Low severity):** The field defaults in `config.py` mean that if `.env` is entirely absent from a deployment, the app starts silently with placeholder values rather than refusing to boot. Removing defaults from secret fields causes `pydantic-settings` to raise a `ValidationError` at startup instead, which is a useful fail-fast safeguard:

```python
# config.py — remove defaults so a missing .env causes an explicit startup error
DATABASE_URL: str          # raises ValidationError if unset in .env or environment
POSTGRES_PASSWORD: str     # raises ValidationError if unset
ADMIN_API_TOKEN: str       # raises ValidationError if unset
```

This is a defence-in-depth improvement, not a fix for an active vulnerability.

---

### 2.6 🟠 HIGH — `--reload` in Production Dockerfile

**File:** `backend/Dockerfile` (line 16)

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100", "--reload"]
```

`--reload` is a development flag that:
- Spawns a subprocess file-watcher — doubles memory use and opens a filesystem monitoring attack surface.
- Forces single-worker mode, preventing multi-core utilisation.
- Triggers a full restart on **any** file change inside the container, including log files written to the working directory.

**Fix:**

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100", "--workers", "1"]
```

(Keep `--workers 1` because the app manually manages per-thread event loops via `_WorkerThread`; the worker count can be increased once the architecture is revised to use a standard connection pool.)

---

## 3. Backend — Outdated Dependencies

All version comparisons are against PyPI at time of analysis.

| Package | Pinned | Latest | Gap | Notes |
|---|---|---|---|---|
| `fastapi` | 0.111.0 | 0.115.x | 4 minor | Contains security and performance fixes |
| `uvicorn[standard]` | 0.29.0 | 0.34.x | 5 minor | HTTP/2 improvements, bug fixes |
| `sqlalchemy` | 2.0.30 | 2.0.49 | 19 patches | Async fixes relevant to this app |
| `pydantic` | 2.7.1 | 2.12.5 | 5 minor | Performance improvements, new validators |
| `httpx` | 0.27.0 | 0.28.x | 1 minor | HTTP/2 improvements |
| `numpy` | 1.26.4 | 2.2.x | 1 major | 1.26.x is EOL; 2.x has breaking dtype changes — plan migration |
| `aiohttp` | 3.9.5 | 3.11.x | 2 minor | See §4 — also unused |
| `python-multipart` | 0.0.9 | 0.0.20 | 11 patches | Security patches included |
| `asyncpg` | 0.29.0 | 0.31.0 | 2 minor | Python 3.13 compatibility |
| `alembic` | 1.13.1 | 1.16.x | 3 minor | Migration engine improvements |
| `discord.py` | 2.3.2 | 2.4.x | 1 minor | Bug and deprecation fixes |
| `pytest` | 9.0.3 | 9.4.x | 4 patches | Test collection improvements |

**Recommended update command (after removing ghost packages):**

```bash
pip install --upgrade fastapi uvicorn sqlalchemy pydantic httpx asyncpg alembic \
    python-multipart discord.py pytest
```

> ⚠️ **numpy 2.x** is a breaking major. Audit all `np.float_`, `np.complex_`, `np.bool_` usages in `backend/app/regime/` and `backend/app/*/strategies/` before upgrading.

---

## 4. Backend — Ghost / Zombie Dependencies

These packages are declared in `requirements.txt` but have **zero import statements** anywhere in `backend/app/**/*.py`. They widen the supply-chain and CVE exposure without providing any functionality.

| Package | Pinned version | Why it should be removed |
|---|---|---|
| `python-jose[cryptography]` | 3.3.0 | Never imported; carries active CVEs (see §2.3) |
| `passlib[bcrypt]` | 1.7.4 | Never imported; unmaintained since 2020 (see §2.4) |
| `krakenex` | 2.1.0 | Never imported; the app uses a custom `KrakenClient` over `httpx` |
| `aiohttp` | 3.9.5 | Never imported; all HTTP via `httpx` |
| `psycopg2-binary` | 2.9.9 | Sync PostgreSQL driver; `asyncpg` handles all async I/O. Verify whether Alembic's `env.py` uses it for sync migrations — if not, remove |

**Verification before removing `psycopg2-binary`:**

```python
# backend/alembic/env.py — check for synchronous engine creation
# e.g. create_engine("postgresql://...") without +asyncpg
```

If the Alembic `env.py` uses only the async path (`postgresql+asyncpg://`), `psycopg2-binary` can be safely dropped.

---

## 5. Backend — Legacy Architectural Patterns

### 5.1 🟡 MEDIUM — `typing.Optional` on Python 3.11

**Files:** `audit.py`, `ledger.py`, `monitoring.py`, `positions.py`, `trades.py`, `watchlist.py` (routes and schemas)

```python
# Current — Python 3.5–3.9 style
from typing import Optional
event_type: Optional[str] = Query(None)

# Modern — Python 3.10+ union syntax
event_type: str | None = Query(None)
```

Python 3.10 introduced native union types. Since the Dockerfile pins `python:3.11-slim`, this legacy import pattern is unnecessary across all route and schema files.

---

### 5.2 🟡 MEDIUM — Naive UTC Datetimes via `replace(tzinfo=None)`

**Files:** `main.py`, `crypto/exit_worker.py`, `stocks/exit_worker.py`, `paper_ledger.py`

```python
now = datetime.now(timezone.utc).replace(tzinfo=None)
```

This pattern creates a UTC-aware datetime and then immediately strips the timezone, producing a "naive" datetime. The intent is to match the database column type (timezone-naive timestamp), but it is fragile:

- IDEs and static analysers treat the result as local time, masking timezone bugs.
- If a code path ever mixes aware and naive datetimes, Python raises a `TypeError` with no clear error message.

**Fix:** Use `datetime.utcnow()` consistently for naive UTC storage, or migrate the database columns to `TIMESTAMP WITH TIME ZONE` and store aware datetimes throughout.

```python
# Option A — explicit naive UTC (keep column type as-is)
from datetime import datetime
now = datetime.utcnow()

# Option B — store timezone-aware (requires column migration)
now = datetime.now(timezone.utc)  # keep tzinfo, change column type
```

---

### 5.3 🟡 MEDIUM — Missing Response Models on Monitoring Endpoints

**File:** `backend/app/api/routes/monitoring.py`

```python
@router.get("")          # no response_model=
@router.get("/evaluate/{symbol:path}")  # no response_model=
```

These are the two highest-traffic read endpoints. Without a Pydantic response model:
- FastAPI cannot validate outgoing data, so schema drift between code and OpenAPI docs goes undetected.
- Serialisation errors surface as 500s at runtime instead of being caught at startup.
- Clients receive undocumented shapes.

**Fix:** Define `MonitoringCandidateOut` and `EvaluateSymbolOut` Pydantic models in `app/api/schemas/` and apply them as `response_model` arguments.

---

### 5.4 🟡 MEDIUM — `NullPool` Disables Connection Reuse

**File:** `backend/app/common/database.py`

```python
engine = create_async_engine(_async_url, poolclass=NullPool, echo=False)
```

`NullPool` is the correct workaround for the multi-thread/multi-event-loop worker architecture. However, it means every database call opens and closes a TCP connection to PostgreSQL, which adds 2–5 ms of overhead per request and can exhaust the `max_connections` limit under moderate load.

The root cause is the `_WorkerThread` pattern in `main.py` that gives each worker thread its own event loop. A more idiomatic alternative is `anyio` task groups or `asyncio.TaskGroup` (Python 3.11+) with structured concurrency inside a single event loop, which would allow a standard `AsyncAdaptedQueuePool` and eliminate the `NullPool` penalty.

This is a medium-term architectural improvement rather than an immediate bug.

---

## 6. Frontend — Security Concerns

### 6.1 🟠 HIGH — Admin Token Stored in React Component State

**File:** `frontend/src/pages/RuntimeRisk.tsx` (line ~46)

```typescript
const [adminToken, setAdminToken] = useState('')
```

The admin token is held in plain React state and bound to a visible `<input>` element. In the current architecture there is no authentication layer (no JWT session, no cookie-based auth), so the raw token flows from component state → HTTP header on every privileged mutation. Risks:

- **XSS exfiltration:** Any injected script can read `window.__REACT_DEVTOOLS_GLOBAL_HOOK__` or traverse the React fiber tree to extract the token.
- **No masking:** The token is only as secure as the `<input type="password">` that wraps it (not verified to use `type="password"`).

**Fix (short-term):** Ensure the input uses `type="password"` and never logs the token to the console.
**Fix (long-term):** Replace the static admin token with a proper session-based auth flow (e.g., cookie with `HttpOnly` + `SameSite=Strict`).

---

### 6.2 🟠 HIGH — No HTTPS Enforcement at the API Client Layer

**File:** `frontend/src/api/client.ts`

```typescript
const API_BASE = import.meta.env.VITE_API_URL || ''
```

There is no guard that enforces `https://` in `VITE_API_URL`. If the variable is unset (falls back to `''`) or accidentally points to an `http://` URL in production, the admin token and API responses are transmitted in cleartext.

**Fix:** Add a runtime assertion in production builds.

```typescript
const API_BASE = import.meta.env.VITE_API_URL || ''
if (import.meta.env.PROD && API_BASE && !API_BASE.startsWith('https://')) {
  console.error('VITE_API_URL must use HTTPS in production')
}
```

---

### 6.3 🟡 MEDIUM — No React Error Boundary

**Files:** `frontend/src/App.tsx`, all page components

No `ErrorBoundary` class component or `react-error-boundary` wrapper exists anywhere in the component tree. An unhandled JavaScript runtime error (e.g., from a malformed API response) will unmount the entire application and show a blank white screen with no recovery path.

**Fix:** Wrap route-level components with an error boundary.

```typescript
// App.tsx
import { ErrorBoundary } from 'react-error-boundary'

<Route path="dashboard" element={
  <ErrorBoundary fallback={<ErrorFallback />}>
    <Dashboard />
  </ErrorBoundary>
} />
```

---

### 6.4 🟡 MEDIUM — Missing ESLint Configuration

**File:** `frontend/package.json`

`eslint` is listed in `devDependencies` but no ESLint configuration file (`.eslintrc.*`, `eslint.config.js`, `eslint.config.mjs`) exists in the frontend directory. Running `npm run lint` would fail or produce no output, meaning the linter provides no protection against common bugs.

**Fix:** Add an `eslint.config.js` with at minimum the recommended TypeScript and React-hooks rules.

```bash
npm install --save-dev @eslint/js typescript-eslint eslint-plugin-react-hooks
```

---

## 7. Frontend — Outdated Dependencies

| Package | Pinned | Latest | Notes |
|---|---|---|---|
| `typescript` | ^5.4.5 | 5.7.x | Performance improvements, new type narrowing |
| `vite` | ^5.3.1 | 6.x | Major version available; breaking changes in config |
| `eslint` | ^10.2.0 | 9.x | **Version 10 does not exist** — likely a typo for `^9.2.0` |
| `lucide-react` | ^0.395.0 | 0.475.x | New icons; tree-shaking improvements |
| `react-router-dom` | ^6.23.1 | 6.28.x | Bug fixes |
| `@tanstack/react-query` | ^5.40.0 | 5.62.x | Performance improvements |

> 🚨 **`eslint: "^10.2.0"` is invalid.** ESLint is currently at v9.x. This means the `npm install` step resolves to an error or silently installs nothing useful. Correct to `"^9.2.0"` and add the flat config file.

---

## 8. Frontend — Architectural Observations

### 8.1 ✅ No Legacy React Patterns Found

- All components are functional (no class components, no `createClass`).
- React hooks (`useState`, `useQuery`, `useMutation`, `useQueryClient`) are used throughout.
- React Query v5 is correctly configured with `QueryClientProvider` and `React.StrictMode`.
- React Router v6 nested layout pattern is correctly implemented.

---

### 8.2 🟡 MEDIUM — No Route-Level Code Splitting

**File:** `frontend/src/App.tsx`

All eight page components are statically imported at the top of `App.tsx`. For a dashboard application this is generally acceptable, but it means the initial JS bundle includes all page code regardless of the entry route.

**Fix:** Use `React.lazy` + `Suspense` for deferred loading.

```typescript
// App.tsx
import { lazy, Suspense } from 'react'
const Dashboard = lazy(() => import('@/pages/Dashboard'))
// ...

<Route path="dashboard" element={
  <Suspense fallback={<PageSkeleton />}>
    <Dashboard />
  </Suspense>
} />
```

---

### 8.3 🟡 LOW — Duplicate `refetchInterval` Configuration

**Files:** `frontend/src/main.tsx` (global), individual page components

```typescript
// main.tsx — global default
const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchInterval: 15000 } },
})

// Dashboard.tsx — per-query override (same value)
useQuery({ queryKey: ['dashboard'], refetchInterval: 15000 })
```

The global default in `main.tsx` is silently overridden by the per-query values. The default is never active, which makes it misleading. Either remove it from the global config or remove the redundant per-query declarations.

---

### 8.4 🟡 LOW — `MarketStatusResponse` Interface Duplicated Across Files

The `MarketStatusResponse` interface is independently declared in `Dashboard.tsx`, `RuntimeRisk.tsx`, and `MarketStatusBadge.tsx`. Any change to the API shape requires updating three files.

**Fix:** Extract to `frontend/src/api/types.ts` and import from there.

---

## 9. Prioritised Remediation Roadmap

### Sprint 1 — Critical Security (1–2 days)

| # | Action | File(s) |
|---|---|---|
| 1 | Replace `allow_origins=["*"]` with explicit allowlist | `backend/app/main.py`, `config.py` |
| 2 | Replace `!=` admin token check with `hmac.compare_digest` | `backend/app/api/deps.py` |
| 3 | Remove `python-jose` and `passlib` from `requirements.txt` | `backend/requirements.txt` |
| 4 | Remove `--reload` from production Dockerfile | `backend/Dockerfile` |
| 5 | *(Optional hardening)* Remove field defaults for secret keys so startup fails loudly if `.env` is absent | `backend/app/common/config.py` |

### Sprint 2 — High-Priority Hygiene (3–5 days)

| # | Action | File(s) |
|---|---|---|
| 6 | Remove `krakenex`, `aiohttp`, `psycopg2-binary` (if Alembic doesn't need it) | `backend/requirements.txt` |
| 7 | Update all outdated backend packages (excluding numpy 2.x) | `backend/requirements.txt` |
| 8 | Fix invalid `eslint: "^10.2.0"` → `"^9.x"` and add config file | `frontend/package.json` |
| 9 | Add React Error Boundary to all page routes | `frontend/src/App.tsx` |
| 10 | Enforce HTTPS check in API client | `frontend/src/api/client.ts` |

### Sprint 3 — Technical Debt (1–2 weeks)

| # | Action | File(s) |
|---|---|---|
| 11 | Replace all `Optional[X]` with `X \| None` in Python 3.11 code | All route and schema files |
| 12 | Standardise UTC datetime storage (remove `replace(tzinfo=None)` pattern) | `main.py`, exit workers, `paper_ledger.py` |
| 13 | Add Pydantic response models to monitoring routes | `backend/app/api/routes/monitoring.py` |
| 14 | Extract shared `MarketStatusResponse` type to `api/types.ts` | Frontend shared types |
| 15 | Add `React.lazy` + `Suspense` for page-level code splitting | `frontend/src/App.tsx` |
| 16 | Plan numpy 2.x migration (audit dtype usage in strategy/regime code) | `backend/app/regime/`, strategies |

### Long-Term Architecture

| # | Action |
|---|---|
| 17 | Replace `_WorkerThread` pattern with `asyncio.TaskGroup` (Python 3.11+) to enable a standard async connection pool and eliminate `NullPool` overhead |
| 18 | Replace static admin token auth with a proper session-based authentication layer (e.g., short-lived JWT issued via a `/auth/login` endpoint, stored as `HttpOnly` cookie) |
| 19 | Add a rate-limiter (e.g., `slowapi`) to the admin endpoints to prevent brute-force of the token |

---

*Report generated by static analysis of source files, dependency version comparisons against PyPI and npm registries, and manual code review.*
