# Signal Forge — Setup Instructions

---

## Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Docker | 24.x | Required for all services |
| Docker Compose | 2.x (`docker compose` v2 plugin) | Bundled with Docker Desktop |
| Git | Any | Clone the repository |
| Python | 3.11 | Only needed to run Alembic outside Docker |
| Node.js | 18.x | Only needed for local frontend development |

---

## 1. Clone the repository

```bash
git clone <your-repo-url> Signal_Forge
cd Signal_Forge
```

---

## 2. Create the environment file

Copy the example file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` and populate every field:

```env
# ── Application ────────────────────────────────────────────────────────────────
APP_NAME=AI_MULTI_ASSET_BOT
APP_PORT=8100
FRONTEND_PORT=5180

# ── Database ───────────────────────────────────────────────────────────────────
# Docker internal URL — do not change unless running Postgres outside Docker
DATABASE_URL=postgresql://bot_user:changeme@postgres:5432/ai_multiasset_bot
REDIS_URL=redis://redis:6379/0

POSTGRES_DB=ai_multiasset_bot
POSTGRES_USER=bot_user
POSTGRES_PASSWORD=changeme          # Change in production

TIMEZONE=America/New_York

# ── Discord ────────────────────────────────────────────────────────────────────
DISCORD_BOT_TOKEN=                  # Bot token from Discord Developer Portal
DISCORD_TRADING_CHANNEL_ID=0        # ID of the channel the bot reads from
DISCORD_USER_ID=0                   # Discord user ID authorized to post signals (or 0 to disable)
DISCORD_ALLOWED_ROLE_IDS=           # Comma-separated role IDs that may post signals (optional)
DISCORD_DECISION_MAX_AGE_SECONDS=900
DISCORD_REQUIRE_DECISION_TIMESTAMP=true

# ── Kraken ─────────────────────────────────────────────────────────────────────
KRAKEN_API_KEY=
KRAKEN_API_SECRET=

# ── Tradier ────────────────────────────────────────────────────────────────────
TRADIER_ACCESS_TOKEN=
TRADIER_ACCOUNT_ID=

# ── Admin ──────────────────────────────────────────────────────────────────────
ADMIN_API_TOKEN=changeme_admin_token  # Change in production
```

### Authorization: user ID vs role IDs

The Discord listener accepts messages from **either** an authorized user or an authorized role.

- Set `DISCORD_USER_ID` to your Discord account's numeric ID to allow your own posts.
- Set `DISCORD_ALLOWED_ROLE_IDS` to a comma-separated list of server role IDs (e.g. `1234567890,9876543210`) to allow any member with one of those roles.
- Both can be set simultaneously — either match authorizes the message.
- If both are `0`/empty, all messages are rejected.

To find your user ID or a role ID: enable **Developer Mode** in Discord settings (`Settings → Advanced → Developer Mode`), then right-click your username or the role and select **Copy ID**.

---

## 3. Discord bot setup

### 3.1 Create the bot

1. Go to [https://discord.com/developers/applications](https://discord.com/developers/applications) and click **New Application**.
2. Name it (e.g. `SignalForge`), then navigate to **Bot** in the left sidebar.
3. Click **Add Bot**, then copy the **Token** → paste into `DISCORD_BOT_TOKEN`.

### 3.2 Enable required intents

Under **Bot → Privileged Gateway Intents**, enable:

| Intent | Required for |
|---|---|
| **Message Content Intent** | Reading message text |
| **Server Members Intent** | Checking author roles (`DISCORD_ALLOWED_ROLE_IDS`) |

> **Important:** if you only use `DISCORD_USER_ID` and never `DISCORD_ALLOWED_ROLE_IDS`, Server Members Intent is not strictly required but it is safe to enable.

### 3.3 Invite the bot to your server

Under **OAuth2 → URL Generator**, select:
- Scopes: `bot`
- Bot Permissions: `Read Messages/View Channels`, `Send Messages`, `Read Message History`, `Attach Files`

Copy the generated URL, paste it into a browser, and invite the bot to your server.

### 3.4 Get the channel ID

In your Discord server, right-click the trading channel and select **Copy Channel ID**. Paste into `DISCORD_TRADING_CHANNEL_ID`.

---

## 4. Broker credentials

### Tradier (stocks)

1. Sign up at [https://tradier.com](https://tradier.com) and create an account.
2. In the **Brokerage API** section, generate an **Access Token**.
3. Find your **Account ID** in the account dashboard.
4. Paste both into `TRADIER_ACCESS_TOKEN` and `TRADIER_ACCOUNT_ID`.

> Use the **Sandbox** environment (`https://sandbox.tradier.com`) for testing. The backend targets Tradier's live API — verify the base URL in `backend/app/stocks/` if you need sandbox.

### Kraken (crypto)

1. Log in at [https://www.kraken.com](https://www.kraken.com).
2. Navigate to **Security → API** and create a new key.
3. Required permissions: **Query Funds**, **Query Open Orders & Trades**, **Create & Modify Orders**, **Cancel/Close Orders**.
4. Paste the key and secret into `KRAKEN_API_KEY` and `KRAKEN_API_SECRET`.

---

## 5. Start all services

```bash
docker compose up -d
```

This starts four containers:

| Container | Host port | Purpose |
|---|---|---|
| `postgres` | `5442` | Primary database |
| `redis` | `6389` | Runtime state + coordination |
| `backend` | `8100` | FastAPI app + background workers |
| `frontend` | `5180` | React dashboard |

> Docker Compose internal service-to-service communication uses standard ports (5432, 6379) — the non-standard host ports (5442, 6389) are only for local tooling access.

Check that all containers are healthy:

```bash
docker compose ps
```

All four services should show `healthy` or `running`.

---

## 6. Run database migrations

Migrations must be run once after first start (and again after any upgrade that ships new migration files).

```bash
docker compose exec backend alembic upgrade head
```

This applies all pending Alembic revisions in order:

| Revision | Description |
|---|---|
| `0001_initial_schema` | Full schema: positions, watchlist_symbols, orders, ledger, audit |
| `0002_positions_composite_indexes` | Composite indexes on `positions(asset_class, state)` and `positions(symbol, asset_class, state)` |
| `0003_watchlist_symbols_composite_index` | Composite index on `watchlist_symbols(asset_class, state)` |

Confirm the migration succeeded:

```bash
docker compose exec backend alembic current
```

Expected output: `0003_watchlist_symbols_composite_index (head)`

### Running Alembic from your local machine

If you prefer to run Alembic outside Docker, update `alembic.ini` to point at the host-mapped port:

```ini
sqlalchemy.url = postgresql://bot_user:changeme@localhost:5442/ai_multiasset_bot
```

Then:

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
```

---

## 7. Verify the backend is running

```bash
curl http://localhost:8100/health
```

Expected response: `{"status": "ok"}` (or similar health payload).

The interactive API docs are available at:
- Swagger UI: `http://localhost:8100/docs`
- ReDoc: `http://localhost:8100/redoc`

All admin endpoints require the `X-Admin-Token` header:

```bash
curl -H "X-Admin-Token: changeme_admin_token" http://localhost:8100/api/runtime
```

---

## 8. Open the frontend

Navigate to `http://localhost:5180` in your browser.

The frontend proxies all `/api` requests to `http://localhost:8100` via Vite's dev proxy (configured in `frontend/vite.config.ts`).

---

## 9. Send your first watchlist

Post a JSON payload to the configured Discord trading channel. The bot accepts:

1. **Inline JSON** (raw or in a ` ```json ``` ` code block)
2. **A `.json` file attachment**

Minimum valid payload:

```json
{
  "timestamp": "2024-01-15T14:30:00Z",
  "source": "manual",
  "symbols": [
    { "symbol": "AAPL", "asset_class": "stock" },
    { "symbol": "BTC/USD", "asset_class": "crypto" }
  ]
}
```

The full schema is defined in `ai_scripts/schemas/watchlist_decision.schema.json`.

The listener validates:
- The message author matches `DISCORD_USER_ID` or holds a role in `DISCORD_ALLOWED_ROLE_IDS`
- `timestamp` is present and not older than `DISCORD_DECISION_MAX_AGE_SECONDS` (default: 900 s)
- `symbols` is a non-empty array where each item has a valid `symbol` and `asset_class`

---

## 10. AI screener setup (optional)

Two automated AI screeners can generate and post watchlists on a schedule.

### Claude + Tradier MCP (stocks)

See `ai_scripts/claude_tradier_stocks.md` for the full system prompt, user prompt template, and Tradier MCP server configuration.

Quick-start MCP config (`~/.config/claude/claude_desktop_config.json` or equivalent):

```json
{
  "mcpServers": {
    "tradier": {
      "command": "npx",
      "args": ["-y", "@tradier/mcp-server"],
      "env": {
        "TRADIER_ACCESS_TOKEN": "<your_token>"
      }
    }
  }
}
```

Recommended schedule: **9:45 AM ET, Monday–Friday** (15 min after market open).

### ChatGPT + Kraken GPT (crypto)

See `ai_scripts/chatgpt_kraken_crypto.md` for the full system prompt, user prompt template, and Python scheduling example.

Enable the **Kraken GPT** app in your ChatGPT session or Custom GPT. No API key is required — the Kraken GPT uses Kraken's public REST API for screening.

Recommended schedule: **every 4 hours** (crypto trades 24/7).

---

## 11. Stopping and restarting

```bash
# Stop all containers (preserves data volumes)
docker compose down

# Stop and remove all data (full reset)
docker compose down -v

# Restart a single service (e.g. after a code change to backend)
docker compose restart backend

# View logs for a service
docker compose logs -f backend
docker compose logs -f frontend
```

---

## Troubleshooting

### Backend fails to start

Check logs:
```bash
docker compose logs backend
```

Common causes:
- `.env` file missing or `DATABASE_URL` / `REDIS_URL` wrong
- Postgres not yet healthy when backend starts (Docker Compose `depends_on` with health checks handles this, but a slow machine may need a longer grace period)

### Migrations fail

Ensure Postgres is fully started before running `alembic upgrade head`:
```bash
docker compose exec postgres pg_isready -U bot_user -d ai_multiasset_bot
```

### Discord bot not responding

- Confirm the bot is online in your Discord server (green dot on its profile)
- Confirm **Message Content Intent** and **Server Members Intent** are enabled in the Developer Portal
- Confirm `DISCORD_TRADING_CHANNEL_ID` is the numeric channel ID, not the channel name
- Confirm `DISCORD_USER_ID` or `DISCORD_ALLOWED_ROLE_IDS` matches the account posting the message

### Frontend shows no data

- Confirm the backend is healthy: `curl http://localhost:8100/health`
- Confirm the Vite proxy is active (only applies when running `npm run dev` locally; the Docker build serves a static bundle directly)

### Alembic `target database is not up to date`

Always run `alembic upgrade head` after pulling new code that includes new migration files.
