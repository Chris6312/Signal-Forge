import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.common.redis_client import get_redis
from app.common.risk_config import get_default_risk_per_trade_pct

logger = logging.getLogger(__name__)

RUNTIME_KEY = "signal_forge:runtime"
HEARTBEAT_KEY = "signal_forge:heartbeat"


@dataclass
class _MonitoringReadinessRecord:
    trigger_close_ts: float
    execution_ready: bool
    block_reason: str | None
    confidence_cap: float
    reasoning: dict[str, Any]


class RuntimeState:
    def __init__(self):
        self._monitoring_readiness_memory: dict[tuple[str, str, str], _MonitoringReadinessRecord] = {}

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
            "risk_per_trade_pct":     json.dumps(get_default_risk_per_trade_pct("stock")),
            "risk_per_trade_pct_stocks": json.dumps(get_default_risk_per_trade_pct("stock")),
            "risk_per_trade_pct_crypto": json.dumps(get_default_risk_per_trade_pct("crypto")),
            "peak_equity_stock":     json.dumps(0.0),
            "peak_equity_crypto":    json.dumps(0.0),
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

    async def get_risk_per_trade_pct(self, asset_class: str | None = None) -> float:
        state = await self.get_state()
        if asset_class == "crypto":
            return float(
                state.get(
                    "risk_per_trade_pct_crypto",
                    state.get("risk_per_trade_pct", get_default_risk_per_trade_pct("crypto")),
                )
            )
        if asset_class == "stock":
            return float(
                state.get(
                    "risk_per_trade_pct_stocks",
                    state.get("risk_per_trade_pct", get_default_risk_per_trade_pct("stock")),
                )
            )

        value = state.get("risk_per_trade_pct", get_default_risk_per_trade_pct(asset_class))
        if isinstance(value, dict):
            normalized = (asset_class or "stock").strip().lower()
            if normalized in ("crypto", "cryptos", "digital"):
                return float(value.get("crypto", get_default_risk_per_trade_pct("crypto")))
            return float(value.get("stock", get_default_risk_per_trade_pct("stock")))
        return float(value)

    async def update_worker_status(self, worker: str, status: str):
        await self.set_value(worker, status)

    def clear_monitoring_readiness_memory(
        self,
        asset_class: str | None = None,
        symbol: str | None = None,
        strategy_key: str | None = None,
    ) -> None:
        if asset_class is None and symbol is None and strategy_key is None:
            self._monitoring_readiness_memory.clear()
            return

        keys_to_remove = [
            key for key in self._monitoring_readiness_memory
            if (asset_class is None or key[0] == asset_class)
            and (symbol is None or key[1] == symbol)
            and (strategy_key is None or key[2] == strategy_key)
        ]
        for key in keys_to_remove:
            del self._monitoring_readiness_memory[key]

    def stabilize_monitoring_readiness(
        self,
        asset_class: str,
        symbol: str,
        strategy_key: str | None,
        trigger_close_ts: float,
        readiness: dict,
        reasoning: dict[str, Any] | None = None,
    ) -> dict:
        if not strategy_key:
            return readiness

        normalized_key = strategy_key.strip().lower().replace(" ", "_")
        key = (asset_class, symbol, normalized_key)
        current_ready = bool(readiness.get("execution_ready", True))
        current_cap = float(readiness.get("confidence_cap", 1.0) or 1.0)
        current_reason = readiness.get("block_reason")
        current_reasoning = dict(reasoning or {})

        prev = self._monitoring_readiness_memory.get(key)
        current_record = _MonitoringReadinessRecord(
            trigger_close_ts=float(trigger_close_ts or 0.0),
            execution_ready=current_ready,
            block_reason=current_reason,
            confidence_cap=current_cap,
            reasoning=current_reasoning,
        )

        if prev and trigger_close_ts and prev.trigger_close_ts and float(trigger_close_ts) <= prev.trigger_close_ts:
            return readiness

        if not current_ready:
            self._monitoring_readiness_memory[key] = current_record
            return readiness

        if prev and not prev.execution_ready and not self._has_material_improvement(prev.block_reason, prev.reasoning, current_reasoning):
            blocked = dict(readiness)
            blocked["execution_ready"] = False
            blocked["confidence_cap"] = min(current_cap, prev.confidence_cap)
            blocked["block_reason"] = prev.block_reason or current_reason or "readiness_stabilization_pending"
            self._monitoring_readiness_memory[key] = _MonitoringReadinessRecord(
                trigger_close_ts=float(trigger_close_ts or prev.trigger_close_ts),
                execution_ready=False,
                block_reason=blocked["block_reason"],
                confidence_cap=float(blocked["confidence_cap"]),
                reasoning=current_reasoning,
            )
            return blocked

        self._monitoring_readiness_memory[key] = current_record
        return readiness

    def _has_material_improvement(self, previous_block_reason: str | None, previous_reasoning: dict[str, Any], current_reasoning: dict[str, Any]) -> bool:
        if not previous_block_reason:
            return True

        reason = previous_block_reason.lower()

        def _float(value) -> float | None:
            try:
                if value is None:
                    return None
                return float(value)
            except (TypeError, ValueError):
                return None

        def _close_improved(min_pct: float = 0.0025) -> bool:
            prev_close = _float(previous_reasoning.get("close"))
            current_close = _float(current_reasoning.get("close"))
            if prev_close is None or current_close is None or prev_close <= 0:
                return False
            return current_close >= prev_close * (1.0 + min_pct)

        def _extension_improved(metric_keys: tuple[str, ...], min_drop: float = 0.5) -> bool:
            for metric_key in metric_keys:
                prev_metric = _float(previous_reasoning.get(metric_key))
                current_metric = _float(current_reasoning.get(metric_key))
                if prev_metric is not None and current_metric is not None:
                    return current_metric <= prev_metric - min_drop
            return False

        if any(token in reason for token in ("acceptance", "not_confirmed", "reclaim")):
            acceptance_now = any(
                bool(current_reasoning.get(flag))
                for flag in (
                    "breakout_acceptance_confirmed",
                    "reclaim_confirmed",
                    "opening_range_acceptance_confirmed",
                    "compression_acceptance_confirmed",
                )
            )
            return acceptance_now and _close_improved()

        if any(token in reason for token in ("follow_through", "support_lost", "fast_support", "below_")):
            prev_support = _float(previous_reasoning.get("current_vs_ema20"))
            current_support = _float(current_reasoning.get("current_vs_ema20"))
            if prev_support is None or current_support is None:
                return False
            return current_support > 0.15 and current_support >= prev_support + 0.25 and _close_improved(0.002)

        if any(token in reason for token in ("extended", "mature", "too_extended")):
            return _extension_improved(("support_extension_pct", "breakout_extension_pct", "breakout_pct"))

        return False


runtime_state = RuntimeState()
