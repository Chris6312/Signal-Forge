import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func

from app.common.config import settings
from app.common.database import AsyncSessionLocal
from app.common.models.watchlist import WatchlistSymbol, SymbolState
from app.common.models.position import Position, PositionState
from app.common.models.order import Order, OrderType, OrderSide, OrderStatus
from app.common.audit_logger import log_event
from app.common.models.audit import AuditSource
from app.common.runtime_state import runtime_state
from app.common.redis_client import get_redis
from app.common.ws_manager import ws_manager
from app.crypto.kraken_client import kraken_client
from app.crypto.strategies.entry_strategies import evaluate_all
from app.regime import regime_engine
from app.regime.indicators import build_asset_indicators
from app.common.candle_store import CandleStore, TF_MINUTES
from app.crypto.candle_fetcher import CryptoCandleFetcher
from app.common.symbols import canonical_symbol
from app.common.watchlist_activation import is_watchlist_activation_ready, activation_ready_at

logger = logging.getLogger(__name__)

ASSET_CLASS = "crypto"
COOLDOWN_KEY_PREFIX = "cooldown:crypto:"


def _extract_signals(result):
    if isinstance(result, dict):
        return result.get("signals") or []
    if isinstance(result, list):
        return result
    return []


class CryptoMonitor:
    def __init__(self):
        self._store = CandleStore()
        self._fetcher = CryptoCandleFetcher(self._store)

    async def run(self):
        await runtime_state.update_worker_status("crypto_monitor", "running")
        logger.info("Crypto monitor started")

        while True:
            try:
                await self._cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Crypto monitor error: %s", exc)
            await asyncio.sleep(settings.CRYPTO_MONITOR_INTERVAL)

        await runtime_state.update_worker_status("crypto_monitor", "stopped")

    async def _cycle(self):
        if not await runtime_state.is_trading_enabled(ASSET_CLASS):
            return

        await self._refresh_regime()

        async with AsyncSessionLocal() as db:
            stmt = select(WatchlistSymbol).where(
                WatchlistSymbol.asset_class == ASSET_CLASS,
                WatchlistSymbol.state == SymbolState.ACTIVE,
            )
            result = await db.execute(stmt)
            symbols = result.scalars().all()

            # Backfill any symbol not yet loaded into the candle store
            for ws in symbols:
                if not self._store.is_loaded(canonical_symbol(ws.symbol, asset_class=ASSET_CLASS), TF_MINUTES["1H"]):
                    logger.info("Backfilling candles for %s", ws.symbol)
                    await self._fetcher.backfill(ws.symbol)

            # Refresh timeframes whose candle has just closed (20 s gate)
            for ws in symbols:
                await self._fetcher.refresh_if_needed(ws.symbol)

            for ws in symbols:
                try:
                    await self._evaluate_symbol(db, ws)
                except Exception as exc:
                    logger.error("Error evaluating %s: %s", ws.symbol, exc)

            await db.commit()

    async def _refresh_regime(self):
        try:
            btc_ohlcv = await kraken_client.get_ohlcv("BTC/USD", interval=1440)
            eth_ohlcv = await kraken_client.get_ohlcv("ETH/USD", interval=1440)
            if len(btc_ohlcv) >= 55 and len(eth_ohlcv) >= 55:
                btc_closes = [float(c[4]) for c in btc_ohlcv]
                eth_closes = [float(c[4]) for c in eth_ohlcv]
                btc_ind = build_asset_indicators(btc_closes)
                eth_ind = build_asset_indicators(eth_closes, btc_closes=btc_closes)
                regime_engine.update_crypto(btc_ind, eth_ind)
        except Exception as exc:
            logger.warning("Regime refresh failed: %s", exc)

    async def _evaluate_symbol(self, db, ws: WatchlistSymbol):
        can = canonical_symbol(ws.symbol, asset_class=ASSET_CLASS)
        already_open = await self._has_open_position(db, can)
        if already_open:
            return

        fast_frame_info = self._store.frame_info(can, TF_MINUTES["15m"])
        if not is_watchlist_activation_ready(ws.added_at, fast_tf_minutes=TF_MINUTES["15m"], frame_info=fast_frame_info):
            logger.debug(
                "%s added at %s is waiting for next 15m activation candle (ready at %s)",
                can,
                ws.added_at,
                activation_ready_at(ws.added_at, fast_tf_minutes=TF_MINUTES["15m"]),
            )
            return

        # Prevent duplicate entry intents across concurrent monitor loops
        intent_key = f"intent:crypto:{can}"
        try:
            redis = await get_redis()
            locked = await redis.setnx(intent_key, "1")
            if not locked:
                logger.debug("Entry intent already in progress for %s — skipping", can)
                return
            # Set a short TTL to avoid stale locks
            await redis.expire(intent_key, 60)
        except Exception as exc:
            logger.warning("Redis lock failed for %s: %s", can, exc)

        try:
            redis = await get_redis()
            if await redis.exists(f"{COOLDOWN_KEY_PREFIX}{can}"):
                logger.debug("Re-entry cooldown active for %s — skipping", can)
                return
        except Exception as exc:
            logger.warning("Cooldown check failed for %s: %s", can, exc)

        candles_by_tf = {
            "15m":   self._store.get(can, TF_MINUTES["15m"]),
            "1H":    self._store.get(can, TF_MINUTES["1H"]),
            "4H":    self._store.get(can, TF_MINUTES["4H"]),
            "daily": self._store.get(can, TF_MINUTES["daily"]),
        }

        eval_result = evaluate_all(can, candles_by_tf)
        signals = _extract_signals(eval_result)
        if not signals:
            try:
                # release intent if no signal
                redis = await get_redis()
                await redis.delete(intent_key)
            except Exception:
                pass
            return

        best = signals[0]
        logger.info(
            "Entry signal for %s: %s (confidence=%.2f)",
            can, best.strategy, best.confidence
        )

        current_count = await self._count_open_positions(db)
        # Respect runtime overrides for max positions when evaluating regime limits
        try:
            max_override = await runtime_state.get_value("max_crypto_positions")
            if isinstance(max_override, str):
                max_override = int(max_override)
        except Exception:
            max_override = None
        allowed, reason = regime_engine.can_open(ASSET_CLASS, best.strategy, best.confidence, current_count, max_positions_override=max_override)
        if not allowed:
            logger.info("Entry blocked by regime [%s]: %s", regime_engine.crypto_regime, reason)
            return

        await self._create_position(db, ws, best, can)
        try:
            redis = await get_redis()
            await redis.delete(intent_key)
        except Exception:
            pass

    async def _create_position(self, db, ws: WatchlistSymbol, signal, canonical: str):
        from app.common.paper_ledger import size_paper_position, record_paper_fill

        trading_mode = await runtime_state.get_trading_mode()
        risk_pct = await runtime_state.get_risk_per_trade_pct()
        risk_pct *= regime_engine.crypto_policy.size_multiplier
        is_paper = trading_mode == "paper"

        quantity = 0.0
        if is_paper:
            quantity = await size_paper_position(
                db, ASSET_CLASS, signal.entry_price, signal.initial_stop, risk_pct
            )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        frozen_policy = {
            "entry_strategy": signal.strategy,
            "exit_strategy": self._select_exit_strategy(signal),
            "initial_stop": signal.initial_stop,
            "profit_target_1": signal.profit_target_1,
            "profit_target_2": signal.profit_target_2,
            "max_hold_hours": signal.max_hold_hours,
            "regime_at_entry": signal.regime,
            "market_regime": regime_engine.crypto_regime,
            "watchlist_source_id": ws.watchlist_source_id or "",
            "management_policy_version": "1.0",
        }

        position = Position(
            id=uuid.uuid4(),
            symbol=canonical,
            asset_class=ASSET_CLASS,
            state=PositionState.OPEN,
            entry_price=signal.entry_price,
            quantity=quantity,
            entry_time=now,
            entry_strategy=signal.strategy,
            exit_strategy=frozen_policy["exit_strategy"],
            initial_stop=signal.initial_stop,
            current_stop=signal.initial_stop,
            profit_target_1=signal.profit_target_1,
            profit_target_2=signal.profit_target_2,
            max_hold_hours=signal.max_hold_hours,
            regime_at_entry=signal.regime,
            watchlist_source_id=ws.watchlist_source_id,
            management_policy_version="1.0",
            frozen_policy=frozen_policy,
            milestone_state={"tp1_hit": False},
            current_price=signal.entry_price,
            created_at=now,
            updated_at=now,
        )
        db.add(position)
        await db.flush()

        order = Order(
            id=uuid.uuid4(),
            position_id=position.id,
            symbol=canonical,
            asset_class=ASSET_CLASS,
            order_type=OrderType.ENTRY,
            side=OrderSide.BUY,
            quantity=quantity,
            requested_price=signal.entry_price,
            status=OrderStatus.SUBMITTED,
            placed_at=now,
        )
        db.add(order)
        await db.flush()

        if is_paper and quantity > 0:
            await record_paper_fill(
                db, ASSET_CLASS, canonical, position.id, order.id, quantity, signal.entry_price
            )

        await log_event(
            db,
            "POSITION_OPENED",
            f"New {ASSET_CLASS} position: {canonical} via {signal.strategy}",
            asset_class=ASSET_CLASS,
            symbol=canonical,
            position_id=str(position.id),
            source=AuditSource.WORKER,
            event_data={
                "strategy": signal.strategy,
                "entry_price": signal.entry_price,
                "quantity": quantity,
                "stop": signal.initial_stop,
                "tp1": signal.profit_target_1,
                "confidence": signal.confidence,
                "mode": trading_mode,
                "regime": signal.regime,
                "notes": signal.notes,
                "reasoning": signal.reasoning,
            },
        )

        ws_manager.broadcast_from_thread("position_executed", {
            "symbol":      canonical,
            "side":        "BUY",
            "quantity":    float(quantity),
            "price":       signal.entry_price,
            "asset_class": ASSET_CLASS,
        })

    def _select_exit_strategy(self, signal) -> str:
        if signal.regime == "trending_up":
            return "Partial at TP1, Dynamic Trail on Runner"
        if signal.regime == "ranging":
            return "Range Failure Exit"
        return "Fixed Risk then Dynamic Protective Floor"

    async def _has_open_position(self, db, symbol: str) -> bool:
        stmt = select(Position.id).where(
            Position.symbol == symbol,
            Position.asset_class == ASSET_CLASS,
            Position.state == PositionState.OPEN,
        ).limit(1)
        result = await db.execute(stmt)
        return result.first() is not None

    async def _count_open_positions(self, db) -> int:
        stmt = select(func.count()).select_from(Position).where(
            Position.asset_class == ASSET_CLASS,
            Position.state == PositionState.OPEN,
        )
        result = await db.execute(stmt)
        return result.scalar_one()


crypto_monitor = CryptoMonitor()
