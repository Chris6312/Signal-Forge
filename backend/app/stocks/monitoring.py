import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func

from app.common.audit_logger import log_event
from app.common.candle_store import CandleStore, TF_MINUTES
from app.common.config import settings
from app.common.database import AsyncSessionLocal
from app.common.market_hours import can_enter_trade, can_pull_data, market_status
from app.common.models.audit import AuditSource
from app.common.models.order import Order, OrderType, OrderSide, OrderStatus
from app.common.models.position import Position, PositionState
from app.common.models.watchlist import WatchlistSymbol, SymbolState
from app.common.position_sizer import POSITION_SIZER_RETURNED_ZERO
from app.common.redis_client import get_redis
from app.common.runtime_state import runtime_state
from app.common.watchlist_activation import is_watchlist_activation_ready, activation_ready_at
from app.common.ws_manager import ws_manager
from app.regime import regime_engine
from app.regime.indicators import build_asset_indicators, build_vix_indicators
from app.stocks.candle_fetcher import StockCandleFetcher
from app.stocks.strategies.entry_strategies import evaluate_all, _execution_readiness_adjustment

logger = logging.getLogger(__name__)

ASSET_CLASS = "stock"
COOLDOWN_KEY_PREFIX = "cooldown:stock:"
INTENT_KEY_PREFIX = "intent:stock:"
INTENT_LOCK_TTL_SECONDS = 60
STOCK_CANDLE_STORE = CandleStore()
STOCK_CANDLE_FETCHER = StockCandleFetcher(STOCK_CANDLE_STORE)

STOCK_EXIT_STRATEGY_BY_KEY = {
    "opening_range_breakout": "End-of-Day Exit",
    "pullback_reclaim": "Fixed Risk then Break-Even Promotion",
    "trend_continuation": "Partial at TP1, Trail Remainder",
    "mean_reversion_bounce": "First Failed Follow-Through Exit",
    "failed_breakdown_reclaim": "Fixed Risk then Break-Even Promotion",
    "volatility_compression_breakout": "Partial at TP1, Trail Remainder",
}


def _strategy_key(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower().replace(" ", "_")


def _signal_key(signal) -> str | None:
    return _strategy_key(getattr(signal, "strategy_key", None) or getattr(signal, "strategy", None))


def _extract_signals(result):
    if isinstance(result, dict):
        return result.get("signals") or []
    if isinstance(result, list):
        return result
    return []


def _readiness_metrics(signal) -> dict:
    return dict(getattr(signal, "reasoning", {}) or {})


def _stock_candles_by_tf(store: CandleStore, symbol: str) -> dict[str, list]:
    return {
        "1m": store.get(symbol, TF_MINUTES["1m"]),
        "5m": store.get(symbol, TF_MINUTES["5m"]),
        "15m": store.get(symbol, TF_MINUTES["15m"]),
        "daily": store.get(symbol, TF_MINUTES["daily"]),
    }


def _needs_insufficient_candle_recovery(result) -> bool:
    if not isinstance(result, dict):
        return False

    if result.get("signals"):
        return False

    rejected = result.get("rejected_strategies") or {}
    if not isinstance(rejected, dict) or not rejected:
        return False

    reasons = [str(reason) for reason in rejected.values() if reason]
    if not reasons:
        return False

    insufficient = sum(1 for reason in reasons if reason == "insufficient_candles")
    return insufficient >= max(1, len(reasons) // 2 + len(reasons) % 2)


def _select_top_signal(result):
    signals = _extract_signals(result)
    if not signals:
        return None

    top_strategy = result.get("top_strategy") if isinstance(result, dict) else None
    top_key = _strategy_key(top_strategy)
    if top_key:
        for signal in signals:
            if _signal_key(signal) == top_key:
                return signal

    return signals[0]


class StockMonitor:
    def __init__(self):
        self._store = STOCK_CANDLE_STORE
        self._fetcher = STOCK_CANDLE_FETCHER
        self._last_trigger_eval_close_ts: dict[str, float] = {}
        self._startup_backfill_pending = True

    async def run(self):
        await runtime_state.update_worker_status("stock_monitor", "running")
        logger.info("Stock monitor started")

        while True:
            try:
                if self._startup_backfill_pending and can_pull_data():
                    await self._warm_start_backfill()
                await self._cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Stock monitor error: %s", exc)

            await asyncio.sleep(settings.STOCK_MONITOR_INTERVAL)

        await runtime_state.update_worker_status("stock_monitor", "stopped")

    async def _warm_start_backfill(self):
        logger.info("Stock startup backfill starting")
        async with AsyncSessionLocal() as db:
            stmt = select(WatchlistSymbol).where(
                WatchlistSymbol.asset_class == ASSET_CLASS,
                WatchlistSymbol.state == SymbolState.ACTIVE,
            )
            result = await db.execute(stmt)
            symbols = result.scalars().all()

        if not symbols:
            self._startup_backfill_pending = False
            return

        for ws in symbols:
            if not all(
                self._store.is_loaded(ws.symbol, iv)
                for iv in (TF_MINUTES["1m"], TF_MINUTES["5m"], TF_MINUTES["15m"], TF_MINUTES["daily"])
            ):
                await self._fetcher.backfill(ws.symbol)

        self._startup_backfill_pending = not all(
            all(
                self._store.is_loaded(ws.symbol, iv)
                for iv in (TF_MINUTES["1m"], TF_MINUTES["5m"], TF_MINUTES["15m"], TF_MINUTES["daily"])
            )
            for ws in symbols
        )
        logger.info(
            "Stock startup backfill complete%s",
            "" if not self._startup_backfill_pending else " (more data still pending)",
        )

    async def _cycle(self):
        if not await runtime_state.is_trading_enabled(ASSET_CLASS):
            return

        status = market_status()
        if status == "closed":
            logger.debug("Stock monitor: market closed — skipping")
            return

        await self._refresh_regime()

        async with AsyncSessionLocal() as db:
            stmt = select(WatchlistSymbol).where(
                WatchlistSymbol.asset_class == ASSET_CLASS,
                WatchlistSymbol.state == SymbolState.ACTIVE,
            )
            result = await db.execute(stmt)
            symbols = result.scalars().all()

            if status not in ("pre_market", "open"):
                return

            for ws in symbols:
                try:
                    await self._evaluate_symbol(db, ws)
                except Exception as exc:
                    logger.error("Error evaluating stock %s: %s", ws.symbol, exc)

            await db.commit()

    async def _refresh_regime(self):
        logger.debug("Stock regime refresh skipped; candle workers own OHLCV ingestion")

    def _trigger_close_ts(self, symbol: str) -> float:
        return self._store.latest_close_ts(symbol, TF_MINUTES["5m"])

    def _should_evaluate_trigger(self, symbol: str) -> bool:
        trigger_close_ts = self._trigger_close_ts(symbol)
        if trigger_close_ts <= 0:
            return False
        return self._last_trigger_eval_close_ts.get(symbol) != trigger_close_ts

    def _mark_trigger_evaluated(self, symbol: str) -> None:
        trigger_close_ts = self._trigger_close_ts(symbol)
        if trigger_close_ts > 0:
            self._last_trigger_eval_close_ts[symbol] = trigger_close_ts

    async def _evaluate_symbol(self, db, ws: WatchlistSymbol):
        already_open = await self._has_open_position(db, ws.symbol)
        if already_open:
            return

        fast_frame_info = self._store.frame_info(ws.symbol, TF_MINUTES["5m"])
        if not self._should_evaluate_trigger(ws.symbol):
            return

        if not is_watchlist_activation_ready(
            ws.added_at,
            fast_tf_minutes=TF_MINUTES["5m"],
            frame_info=fast_frame_info,
        ):
            logger.debug(
                "%s added at %s is waiting for next 5m activation candle (ready at %s)",
                ws.symbol,
                ws.added_at,
                activation_ready_at(ws.added_at, fast_tf_minutes=TF_MINUTES["5m"]),
            )
            return

        try:
            redis = await get_redis()
            if await redis.exists(f"{COOLDOWN_KEY_PREFIX}{ws.symbol}"):
                logger.debug("Re-entry cooldown active for %s — skipping", ws.symbol)
                return
        except Exception as exc:
            logger.warning("Cooldown check failed for %s: %s", ws.symbol, exc)

        self._mark_trigger_evaluated(ws.symbol)

        candles_by_tf = _stock_candles_by_tf(self._store, ws.symbol)

        try:
            tf_info = {}
            for tf, iv in (
                ("1m", TF_MINUTES["1m"]),
                ("5m", TF_MINUTES["5m"]),
                ("15m", TF_MINUTES["15m"]),
                ("daily", TF_MINUTES["daily"]),
            ):
                try:
                    tf_info[tf] = self._store.frame_info(ws.symbol, iv)
                except Exception as e:
                    tf_info[tf] = {"error": str(e)}
            logger.debug("CANDLE_FRAMES | %s | %s", ws.symbol, tf_info)
        except Exception:
            pass

        eval_result = evaluate_all(ws.symbol, candles_by_tf, include_diagnostics=True)
        if not _extract_signals(eval_result):
            return

        best = _select_top_signal(eval_result)
        if not best:
            return

        readiness = _execution_readiness_adjustment(best, candles_by_tf)
        readiness = runtime_state.stabilize_monitoring_readiness(
            ASSET_CLASS,
            ws.symbol,
            _signal_key(best),
            self._trigger_close_ts(ws.symbol),
            readiness,
            _readiness_metrics(best),
        )

        if hasattr(best, "reasoning"):
            best.reasoning = dict(getattr(best, "reasoning", {}) or {})
            best.reasoning["execution_ready"] = readiness["execution_ready"]
            best.reasoning["execution_confidence_cap"] = readiness["confidence_cap"]
            best.reasoning["execution_block_reason"] = readiness["block_reason"]

        if not readiness["execution_ready"]:
            logger.info(
                "Entry blocked by execution readiness for %s: %s",
                ws.symbol,
                readiness["block_reason"],
            )
            return

        if readiness["confidence_cap"] < best.confidence:
            best.confidence = readiness["confidence_cap"]

        logger.info(
            "Stock entry signal: %s via %s (confidence=%.2f)",
            ws.symbol,
            best.strategy,
            best.confidence,
        )

        current_count = await self._count_open_positions(db)
        try:
            max_override = await runtime_state.get_value("max_stock_positions")
            if isinstance(max_override, str):
                max_override = int(max_override)
        except Exception:
            max_override = None

        allowed, reason = regime_engine.can_open(
            ASSET_CLASS,
            best.strategy,
            best.confidence,
            current_count,
            max_positions_override=max_override,
        )
        if not allowed:
            logger.info("Entry blocked by regime [%s]: %s", regime_engine.stock_regime, reason)
            return

        if not can_enter_trade():
            logger.debug("%s signal ready but market not in active trading window — holding off entry", ws.symbol)
            return

        intent_key = f"{INTENT_KEY_PREFIX}{ws.symbol}"
        redis = None
        locked = False
        try:
            redis = await get_redis()
            locked = await redis.setnx(intent_key, "1")
            if not locked:
                logger.debug("Entry intent already in progress for %s — skipping", ws.symbol)
                return
            await redis.expire(intent_key, INTENT_LOCK_TTL_SECONDS)
        except Exception as exc:
            logger.warning("Redis lock failed for %s: %s", ws.symbol, exc)

        try:
            await self._create_position(db, ws, best)
        finally:
            try:
                if redis and locked:
                    await redis.delete(intent_key)
            except Exception:
                pass

    async def _create_position(self, db, ws: WatchlistSymbol, signal):
        from app.common.paper_ledger import size_paper_position, record_paper_fill

        trading_mode = await runtime_state.get_trading_mode()
        risk_pct = await runtime_state.get_risk_per_trade_pct(ASSET_CLASS)
        is_paper = trading_mode == "paper"

        quantity = 0.0
        if is_paper:
            quantity = await size_paper_position(
                db,
                ASSET_CLASS,
                signal.entry_price,
                signal.initial_stop,
                risk_pct,
                signal=signal,
            )

        if quantity <= 0:
            logger.info(
                "Skipping stock position creation for %s because position sizer returned zero",
                signal.symbol,
                extra={"reason": POSITION_SIZER_RETURNED_ZERO},
            )
            return None

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        exit_strategy = self._select_exit_strategy(signal)

        frozen_policy = {
            "entry_strategy": signal.strategy,
            "exit_strategy": exit_strategy,
            "initial_stop": signal.initial_stop,
            "profit_target_1": signal.profit_target_1,
            "profit_target_2": signal.profit_target_2,
            "max_hold_hours": signal.max_hold_hours,
            "hard_max_hold": True,
            "regime_at_entry": signal.regime,
            "market_regime": regime_engine.stock_regime,
            "watchlist_source_id": ws.watchlist_source_id or "",
            "management_policy_version": "1.0",
        }

        position = Position(
            id=uuid.uuid4(),
            symbol=ws.symbol,
            asset_class=ASSET_CLASS,
            state=PositionState.OPEN,
            entry_price=signal.entry_price,
            quantity=quantity,
            entry_time=now,
            entry_strategy=signal.strategy,
            exit_strategy=exit_strategy,
            initial_stop=signal.initial_stop,
            current_stop=signal.initial_stop,
            profit_target_1=signal.profit_target_1,
            profit_target_2=signal.profit_target_2,
            max_hold_hours=signal.max_hold_hours,
            regime_at_entry=signal.regime,
            watchlist_source_id=ws.watchlist_source_id,
            management_policy_version="1.0",
            frozen_policy=frozen_policy,
            milestone_state={"tp1_hit": False, "be_promoted": False},
            current_price=signal.entry_price,
            created_at=now,
            updated_at=now,
        )
        db.add(position)
        await db.flush()

        order = Order(
            id=uuid.uuid4(),
            position_id=position.id,
            symbol=ws.symbol,
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
                db,
                ASSET_CLASS,
                ws.symbol,
                position.id,
                order.id,
                quantity,
                signal.entry_price,
            )

        await log_event(
            db,
            "POSITION_OPENED",
            f"New stock position: {ws.symbol} via {signal.strategy}",
            asset_class=ASSET_CLASS,
            symbol=ws.symbol,
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

        ws_manager.broadcast_from_thread(
            "position_executed",
            {
                "symbol": ws.symbol,
                "side": "BUY",
                "quantity": float(quantity),
                "price": signal.entry_price,
                "asset_class": ASSET_CLASS,
            },
        )

        return position

    def _select_exit_strategy(self, signal) -> str:
        strategy_key = _signal_key(signal)
        if strategy_key in STOCK_EXIT_STRATEGY_BY_KEY:
            return STOCK_EXIT_STRATEGY_BY_KEY[strategy_key]

        strategy_name = getattr(signal, "strategy", None)
        normalized_key = _strategy_key(strategy_name)
        if normalized_key in STOCK_EXIT_STRATEGY_BY_KEY:
            return STOCK_EXIT_STRATEGY_BY_KEY[normalized_key]

        return "Fixed Risk then Break-Even Promotion"

    async def _has_open_position(self, db, symbol: str) -> bool:
        stmt = (
            select(Position.id)
            .where(
                Position.symbol == symbol,
                Position.asset_class == ASSET_CLASS,
                Position.state == PositionState.OPEN,
            )
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.first() is not None

    async def _count_open_positions(self, db) -> int:
        stmt = select(func.count()).select_from(Position).where(
            Position.asset_class == ASSET_CLASS,
            Position.state == PositionState.OPEN,
        )
        result = await db.execute(stmt)
        return result.scalar_one()


stock_monitor = StockMonitor()