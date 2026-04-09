import uuid
import logging
from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.models.watchlist import WatchlistSymbol, SymbolState
from app.common.audit_logger import log_event
from app.common.models.audit import AuditSource
from app.common.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class WatchlistEngine:
    async def process_update(
        self,
        new_symbols: List[dict],
        source_id: str = "",
    ) -> dict:
        async with AsyncSessionLocal() as db:
            result = await self._process(db, new_symbols, source_id)
            await db.commit()
            return result

    async def _process(
        self,
        db: AsyncSession,
        new_symbols: List[dict],
        source_id: str,
    ) -> dict:
        incoming = {
            (item["symbol"].upper(), item["asset_class"].lower())
            for item in new_symbols
        }

        # Only touch symbols whose asset_class appears in this update.
        # A stock-only upload must never deactivate crypto symbols and vice versa.
        incoming_asset_classes = {ac for _, ac in incoming}

        stmt = select(WatchlistSymbol).where(
            WatchlistSymbol.state.in_([SymbolState.ACTIVE, SymbolState.MANAGED]),
            WatchlistSymbol.asset_class.in_(incoming_asset_classes),
        )
        result = await db.execute(stmt)
        existing = result.scalars().all()

        existing_active = {
            (ws.symbol, ws.asset_class): ws
            for ws in existing
            if ws.state == SymbolState.ACTIVE
        }
        existing_managed = {
            (ws.symbol, ws.asset_class): ws
            for ws in existing
            if ws.state == SymbolState.MANAGED
        }

        added, removed, retained, promoted = [], [], [], []
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        for symbol, asset_class in incoming:
            key = (symbol, asset_class)
            if key in existing_active:
                retained.append(symbol)
            elif key in existing_managed:
                ws = existing_managed[key]
                ws.state = SymbolState.ACTIVE
                ws.watchlist_source_id = source_id
                promoted.append(symbol)
            else:
                ws = WatchlistSymbol(
                    id=uuid.uuid4(),
                    symbol=symbol,
                    asset_class=asset_class,
                    state=SymbolState.ACTIVE,
                    watchlist_source_id=source_id,
                    added_at=now,
                )
                db.add(ws)
                added.append(symbol)

        to_remove = {key: ws for key, ws in existing_active.items() if key not in incoming}

        if to_remove:
            from app.common.models.position import Position, PositionState
            remove_symbols = [ws.symbol for ws in to_remove.values()]
            open_stmt = select(Position.symbol, Position.asset_class).where(
                Position.symbol.in_(remove_symbols),
                Position.state == PositionState.OPEN,
            )
            open_result = await db.execute(open_stmt)
            open_positions = {(row.symbol, row.asset_class) for row in open_result}
        else:
            open_positions = set()

        for key, ws in to_remove.items():
            has_open = (ws.symbol, ws.asset_class) in open_positions
            if has_open:
                ws.state = SymbolState.MANAGED
                ws.managed_since = now
                removed.append(f"{ws.symbol} -> MANAGED")
                await log_event(
                    db,
                    "WATCHLIST_SYMBOL_MANAGED",
                    f"{ws.symbol} moved to MANAGED (open position exists)",
                    asset_class=ws.asset_class,
                    symbol=ws.symbol,
                    source=AuditSource.DISCORD,
                )
            else:
                ws.state = SymbolState.INACTIVE
                ws.removed_at = now
                removed.append(f"{ws.symbol} -> INACTIVE")
                await log_event(
                    db,
                    "WATCHLIST_SYMBOL_REMOVED",
                    f"{ws.symbol} removed from watchlist",
                    asset_class=ws.asset_class,
                    symbol=ws.symbol,
                    source=AuditSource.DISCORD,
                )

        await log_event(
            db,
            "WATCHLIST_UPDATED",
            f"Watchlist updated: +{len(added)} added, {len(removed)} removed, {len(retained)} retained",
            source=AuditSource.DISCORD,
            event_data={
                "source_id": source_id,
                "added": added,
                "removed": removed,
                "retained": retained,
                "promoted": promoted,
                "total": len(incoming),
            },
        )

        logger.info(
            "Watchlist update: +%d added, %d removed, %d retained, %d promoted",
            len(added), len(removed), len(retained), len(promoted),
        )

        return {
            "added": added,
            "removed": removed,
            "retained": retained,
            "promoted": promoted,
            "total": len(incoming),
        }

    async def release_managed_symbol(
        self,
        db: AsyncSession,
        symbol: str,
        asset_class: str,
    ) -> bool:
        """
        If the symbol is MANAGED and no longer has any open positions, transition
        it to INACTIVE. Called by exit workers after closing a position.
        Returns True if the symbol was released.
        """
        result = await db.execute(
            select(WatchlistSymbol).where(
                WatchlistSymbol.symbol == symbol,
                WatchlistSymbol.asset_class == asset_class,
                WatchlistSymbol.state == SymbolState.MANAGED,
            )
        )
        ws = result.scalar_one_or_none()
        if not ws:
            return False

        has_open = await self._has_open_position(db, symbol, asset_class)
        if has_open:
            return False

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        ws.state = SymbolState.INACTIVE
        ws.closed_at = now
        await log_event(
            db,
            "WATCHLIST_SYMBOL_RELEASED",
            f"{symbol} released from MANAGED → INACTIVE (no open positions)",
            asset_class=asset_class,
            symbol=symbol,
            source=AuditSource.WORKER,
        )
        logger.info("Watchlist: %s (%s) MANAGED → INACTIVE", symbol, asset_class)
        return True

    async def _has_open_position(
        self,
        db: AsyncSession,
        symbol: str,
        asset_class: str,
    ) -> bool:
        from app.common.models.position import Position, PositionState
        stmt = select(Position.id).where(
            Position.symbol == symbol,
            Position.asset_class == asset_class,
            Position.state == PositionState.OPEN,
        ).limit(1)
        result = await db.execute(stmt)
        return result.first() is not None


watchlist_engine = WatchlistEngine()
