import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.common.config import settings
from app.common.database import AsyncSessionLocal
from app.common.models.position import Position, PositionState
from app.common.audit_logger import log_event
from app.common.models.audit import AuditSource
from app.common.runtime_state import runtime_state
from app.common.redis_client import get_redis
from app.common.watchlist_engine import watchlist_engine
from app.crypto.kraken_client import kraken_client
from app.crypto.strategies.exit_strategies import evaluate_exit
from app.crypto.ledger import crypto_ledger
from app.common.paper_ledger import KRAKEN_TAKER_FEE_RATE

logger = logging.getLogger(__name__)

ASSET_CLASS = "crypto"
REENTRY_COOLDOWN_SECONDS = 4 * 3600  # 4-hour cooldown after a stop-out
COOLDOWN_KEY_PREFIX = "cooldown:crypto:"


class CryptoExitWorker:
    async def run(self):
        await runtime_state.update_worker_status("crypto_exit_worker", "running")
        logger.info("Crypto exit worker started")

        while True:
            try:
                await self._cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Crypto exit worker error: %s", exc)
            await asyncio.sleep(settings.EXIT_WORKER_INTERVAL)

        await runtime_state.update_worker_status("crypto_exit_worker", "stopped")

    async def _cycle(self):
        async with AsyncSessionLocal() as db:
            stmt = select(Position).where(
                Position.asset_class == ASSET_CLASS,
                Position.state == PositionState.OPEN,
            )
            result = await db.execute(stmt)
            positions = result.scalars().all()

            for position in positions:
                try:
                    await self._evaluate_position(db, position)
                except Exception as exc:
                    logger.error("Exit eval error for %s: %s", position.symbol, exc)

            await db.commit()

    async def _evaluate_position(self, db, position: Position):
        try:
            ticker = await kraken_client.get_ticker(position.symbol)
            current_price = float(ticker.get("c", [position.entry_price])[0])
        except Exception as exc:
            logger.warning("Failed to fetch price for %s: %s", position.symbol, exc)
            return

        position.current_price = current_price
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if not position.quantity or position.quantity <= 0:
            await self._close_position(
                db, position, current_price,
                "Closed: zero quantity — no position held", now,
            )
            position.updated_at = now
            return

        if position.entry_price and position.quantity:
            position.pnl_unrealized = (
                (current_price - position.entry_price) * position.quantity
            )

        if position.max_hold_hours and position.entry_time:
            elapsed_hours = (now - position.entry_time).total_seconds() / 3600
            if elapsed_hours >= position.max_hold_hours:
                await self._close_position(
                    db, position, current_price,
                    f"Max hold time exceeded ({position.max_hold_hours}h)", now,
                )
                position.updated_at = now
                return

        try:
            ohlcv = await kraken_client.get_ohlcv(position.symbol, interval=60)
        except Exception:
            ohlcv = []

        decision = evaluate_exit(position, current_price, ohlcv)

        if decision.new_stop and decision.new_stop != position.current_stop:
            position.current_stop = decision.new_stop
            await log_event(
                db,
                "STOP_UPDATED",
                f"Stop updated to {decision.new_stop:.4f}",
                asset_class=ASSET_CLASS,
                symbol=position.symbol,
                position_id=str(position.id),
                source=AuditSource.WORKER,
                event_data={"new_stop": decision.new_stop, "reason": decision.reason},
            )

        if decision.trailing_active:
            milestone = {**(position.milestone_state or {})}
            milestone["trailing_stop"] = decision.new_stop
            position.milestone_state = milestone

        if decision.partial and not (position.milestone_state or {}).get("tp1_hit"):
            partial_qty = round((position.quantity or 0.0) * decision.partial_pct, 8)
            partial_pnl = 0.0
            if position.entry_price and partial_qty > 0:
                partial_proceeds = current_price * partial_qty
                partial_pnl = partial_proceeds - (position.entry_price * partial_qty)
                position.quantity = round((position.quantity or 0.0) - partial_qty, 8)
                position.pnl_realized = (position.pnl_realized or 0.0) + partial_pnl
                position.pnl_unrealized = (
                    (current_price - position.entry_price) * (position.quantity or 0.0)
                )
                if partial_proceeds > 0:
                    await crypto_ledger.record_exit(
                        db,
                        symbol=position.symbol,
                        net_proceeds=partial_proceeds,
                        pnl=partial_pnl,
                        position_id=position.id,
                        notes=f"Partial exit {int(decision.partial_pct * 100)}% at TP1 {current_price:.4f}",
                    )
                exit_fee = round(current_price * partial_qty * KRAKEN_TAKER_FEE_RATE, 8)
                if exit_fee > 0:
                    await crypto_ledger.record_fee(
                        db,
                        symbol=position.symbol,
                        fee=exit_fee,
                        position_id=position.id,
                    )

            milestone = {**(position.milestone_state or {})}
            milestone["tp1_hit"] = True
            milestone["tp1_price"] = current_price
            milestone["trailing_stop"] = position.current_stop
            position.milestone_state = milestone

            await log_event(
                db,
                "PARTIAL_EXIT",
                f"Partial exit {int(decision.partial_pct * 100)}% at TP1 {current_price:.4f} | PnL: {partial_pnl:.4f}",
                asset_class=ASSET_CLASS,
                symbol=position.symbol,
                position_id=str(position.id),
                source=AuditSource.WORKER,
                event_data={
                    "price": current_price,
                    "partial_pct": decision.partial_pct,
                    "partial_qty": partial_qty,
                    "partial_pnl": partial_pnl,
                    "remaining_qty": position.quantity,
                },
            )

        if decision.should_exit:
            await self._close_position(db, position, current_price, decision.reason, now)

        position.updated_at = now

    async def _set_reentry_cooldown(self, symbol: str):
        """Block re-entry on this symbol for REENTRY_COOLDOWN_SECONDS after a stop-out."""
        try:
            redis = await get_redis()
            await redis.set(
                f"{COOLDOWN_KEY_PREFIX}{symbol}",
                "1",
                ex=REENTRY_COOLDOWN_SECONDS,
            )
            logger.info("Re-entry cooldown set for %s (%dh)", symbol, REENTRY_COOLDOWN_SECONDS // 3600)
        except Exception as exc:
            logger.warning("Failed to set re-entry cooldown for %s: %s", symbol, exc)

    async def _close_position(self, db, position: Position, exit_price: float, reason: str, now):
        net_proceeds = 0.0
        pnl = 0.0
        if position.entry_price and position.quantity:
            net_proceeds = exit_price * position.quantity
            pnl = net_proceeds - (position.entry_price * position.quantity)

        position.state = PositionState.CLOSED
        position.exit_price = exit_price
        position.exit_time = now
        position.exit_reason = reason
        position.pnl_realized = (position.pnl_realized or 0.0) + pnl
        position.pnl_unrealized = 0.0

        if net_proceeds > 0 or pnl != 0.0:
            await crypto_ledger.record_exit(
                db,
                symbol=position.symbol,
                net_proceeds=net_proceeds,
                pnl=pnl,
                position_id=position.id,
                notes=f"Exit: {reason}",
            )

        if position.quantity:
            exit_fee = round(exit_price * position.quantity * KRAKEN_TAKER_FEE_RATE, 8)
            if exit_fee > 0:
                await crypto_ledger.record_fee(
                    db,
                    symbol=position.symbol,
                    fee=exit_fee,
                    position_id=position.id,
                )

        await log_event(
            db,
            "POSITION_CLOSED",
            f"{position.symbol} closed at {exit_price:.4f} — {reason}",
            asset_class=ASSET_CLASS,
            symbol=position.symbol,
            position_id=str(position.id),
            source=AuditSource.WORKER,
            event_data={
                "exit_price": exit_price,
                "reason": reason,
                "pnl": pnl,
                "entry_price": position.entry_price,
            },
        )
        await watchlist_engine.release_managed_symbol(db, position.symbol, ASSET_CLASS)
        logger.info("Position closed: %s | PnL: %.4f | Reason: %s", position.symbol, pnl, reason)

        stop_keywords = ("stop hit", "trailing floor", "trail stop", "range support failed")
        if any(kw in reason.lower() for kw in stop_keywords):
            await self._set_reentry_cooldown(position.symbol)


crypto_exit_worker = CryptoExitWorker()
