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
from app.common.symbols import canonical_symbol
from app.common.watchlist_schema_v4 import validate_symbol_entry

logger = logging.getLogger(__name__)


def _apply_watchlist_metadata(ws: WatchlistSymbol, meta: dict) -> None:
    if meta.get("reason"):
        ws.reason = meta["reason"]
    if meta.get("confidence") is not None:
        ws.confidence = meta["confidence"]
    if meta.get("tags") is not None:
        ws.tags = meta["tags"]
    if meta.get("notes"):
        ws.notes = meta["notes"]


class WatchlistEngine:
    async def process_update(
        self,
        new_symbols: List[dict],
        source_id: str = "",
        payload_meta: dict | None = None,
    ) -> dict:
        # AsyncSessionLocal may be an async context manager factory or an
        # async generator (FastAPI dependency override yields). Support both
        # shapes to make the engine robust to test monkeypatching and runtime
        # dependency injection patterns.
        session_ctx = AsyncSessionLocal()
        # If it implements the async context manager protocol, use it
        if hasattr(session_ctx, "__aenter__"):
            async with session_ctx as db:
                result = await self._process(db, new_symbols, source_id, payload_meta)
                await db.commit()
                return result
        # Otherwise assume it's an async generator that yields a session
        if hasattr(session_ctx, "__anext__"):
            db = None
            try:
                db = await session_ctx.__anext__()
                result = await self._process(db, new_symbols, source_id, payload_meta)
                try:
                    await db.commit()
                except Exception:
                    pass
                return result
            finally:
                try:
                    await session_ctx.aclose()
                except Exception:
                    pass
        # Fallback: call and await if it's a coroutine returning a session
        try:
            db = await session_ctx
            result = await self._process(db, new_symbols, source_id, payload_meta)
            await db.commit()
            return result
        except Exception:
            raise

    async def _process(
        self,
        db: AsyncSession,
        new_symbols: List[dict],
        source_id: str,
        payload_meta: dict | None = None,
    ) -> dict:
        # Normalize incoming items into tuples: (symbol, asset_class, metadata)
        incoming_items = []
        incoming_asset_classes: set[str] = set()
        # Collect any AI hint payloads per symbol for auditing
        ai_hints_seen: dict[str, dict] = {}
        validation_reasons: dict[str, str] = {}

        for item in new_symbols:
            try:
                ac = (item.get("asset_class") or "").lower()
                if ac not in ("crypto", "stock"):
                    # Skip invalid asset classes
                    continue
                # Only enforce strict v4 validation when the payload declares v4
                if payload_meta and payload_meta.get("schema_version") == "bot_watchlist_v4":
                    reason = validate_symbol_entry(item)
                    if reason:
                        validation_reasons[str(item.get("symbol") or "")] = reason
                        continue
                sym = canonical_symbol(item.get("symbol", ""), asset_class=ac)
                meta = {
                    "reason": item.get("reason"),
                    "confidence": float(item.get("confidence")) if item.get("confidence") is not None else None,
                    "tags": item.get("tags") if isinstance(item.get("tags"), (list, tuple)) else None,
                    "notes": item.get("notes"),
                    # Preserve raw AI hint if present for auditability
                    "ai_hint": item.get("ai_hint") if isinstance(item.get("ai_hint"), dict) else None,
                }
                incoming_items.append((sym, ac, meta))
                incoming_asset_classes.add(ac)
                if meta.get("ai_hint"):
                    ai_hints_seen[sym] = meta.get("ai_hint")
            except Exception:
                # Skip malformed entries but continue processing
                continue

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

        for symbol, asset_class, meta in incoming_items:
            key = (symbol, asset_class)
            if key in existing_active:
                ws = existing_active[key]
                _apply_watchlist_metadata(ws, meta)
                retained.append(symbol)
            elif key in existing_managed:
                ws = existing_managed[key]
                ws.state = SymbolState.ACTIVE
                ws.watchlist_source_id = source_id
                ws.added_at = now
                ws.removed_at = None
                ws.managed_since = None
                ws.closed_at = None
                _apply_watchlist_metadata(ws, meta)
                promoted.append(symbol)
            else:
                ws = WatchlistSymbol(
                    id=uuid.uuid4(),
                    symbol=symbol,
                    asset_class=asset_class,
                    state=SymbolState.ACTIVE,
                    watchlist_source_id=source_id,
                    notes=meta.get("notes"),
                    reason=meta.get("reason"),
                    confidence=meta.get("confidence"),
                    tags=meta.get("tags"),
                    added_at=now,
                )
                db.add(ws)
                added.append(symbol)

        to_remove = {key: ws for key, ws in existing_active.items() if key not in {(s, ac) for s, ac, _ in incoming_items}}

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
                "total": len(incoming_items),
                "schema_version": payload_meta.get("schema_version") if payload_meta else None,
                "scan_id": payload_meta.get("scan_id") if payload_meta else None,
                "timestamp_received": payload_meta.get("timestamp") if payload_meta else None,
                "ai_hints_seen": ai_hints_seen,
                "validation_reasons": validation_reasons,
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
            "total": len(incoming_items),
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
