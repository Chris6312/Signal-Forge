import json
import logging
from datetime import datetime, timezone

from app.common.redis_client import get_redis

logger = logging.getLogger(__name__)

RUNTIME_KEY = "signal_forge:runtime"
HEARTBEAT_KEY = "signal_forge:heartbeat"


class RuntimeState:
    async def initialize(self):
        redis = await get_redis()
        # One-time migration: if the key still exists as a JSON string from the
        # old storage scheme, delete it so HSET can take over.
        key_type = await redis.type(RUNTIME_KEY)
        if key_type not in ("hash", "none"):
            logger.warning(
                "Runtime key is type '%s' — deleting stale key to migrate to Hash storage",
                key_type,
            )
            await redis.delete(RUNTIME_KEY)

        # Use a Redis Hash so every field is an independent, atomic value.
        # Concurrent HSET calls from parallel worker threads can never
        # overwrite each other — eliminates the read-modify-write race.
        now = datetime.now(timezone.utc).isoformat()
        # Boot-time fields are always reset on startup
        await redis.hset(RUNTIME_KEY, mapping={
            "status":             json.dumps("online"),
            "started_at":         json.dumps(now),
            "crypto_monitor":     json.dumps("idle"),
            "stock_monitor":      json.dumps("idle"),
            "crypto_exit_worker": json.dumps("idle"),
            "stock_exit_worker":  json.dumps("idle"),
            "discord_listener":   json.dumps("idle"),
        })
        # User-configurable settings survive restarts — only written when absent
        defaults = {
            "trading_enabled":        json.dumps(True),
            "crypto_trading_enabled": json.dumps(True),
            "stock_trading_enabled":  json.dumps(True),
            "trading_mode":           json.dumps("paper"),
            "risk_per_trade_pct":     json.dumps(0.02),
            "max_crypto_positions":   json.dumps(5),
            "max_stock_positions":    json.dumps(5),
        }
        for field, value in defaults.items():
            await redis.hsetnx(RUNTIME_KEY, field, value)
        logger.info("Runtime state initialized")

    async def get_state(self) -> dict:
        redis = await get_redis()
        raw = await redis.hgetall(RUNTIME_KEY)
        if not raw:
            return {}
        result = {}
        for k, v in raw.items():
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                result[k] = v
        return result

    async def set_status(self, status: str):
        await self.set_value("status", status)

    async def set_value(self, key: str, value):
        redis = await get_redis()
        # HSET is atomic per field — no read-modify-write race condition
        await redis.hset(RUNTIME_KEY, key, json.dumps(value))

    async def get_value(self, key: str, default=None):
        redis = await get_redis()
        raw = await redis.hget(RUNTIME_KEY, key)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def heartbeat(self):
        redis = await get_redis()
        ts = datetime.now(timezone.utc).isoformat()
        await redis.set(HEARTBEAT_KEY, ts, ex=120)
        await self.set_value("last_heartbeat", ts)

    async def is_trading_enabled(self, asset_class: str | None = None) -> bool:
        state = await self.get_state()
        if not state.get("trading_enabled", True):
            return False
        if asset_class == "crypto":
            return state.get("crypto_trading_enabled", True)
        if asset_class == "stock":
            return state.get("stock_trading_enabled", True)
        return True

    async def get_trading_mode(self) -> str:
        return await self.get_value("trading_mode", "paper")

    async def get_risk_per_trade_pct(self) -> float:
        return float(await self.get_value("risk_per_trade_pct", 0.02))

    async def update_worker_status(self, worker: str, status: str):
        await self.set_value(worker, status)


runtime_state = RuntimeState()
