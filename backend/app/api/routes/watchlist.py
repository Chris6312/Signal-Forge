from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.api.schemas.watchlist import WatchlistSymbolOut, WatchlistUpdateIn, WatchlistUpdateOut
from app.common.models.watchlist import WatchlistSymbol, SymbolState
from app.common.watchlist_engine import watchlist_engine

router = APIRouter()


@router.get("", response_model=list[WatchlistSymbolOut])
async def get_watchlist(
    state: str | None = Query(None),
    asset_class: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(WatchlistSymbol).order_by(desc(WatchlistSymbol.added_at))
    if state:
        stmt = stmt.where(WatchlistSymbol.state == state)
    else:
        stmt = stmt.where(WatchlistSymbol.state != SymbolState.INACTIVE)
    if asset_class:
        stmt = stmt.where(WatchlistSymbol.asset_class == asset_class)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/active", response_model=list[WatchlistSymbolOut])
async def get_active_symbols(db: AsyncSession = Depends(get_db_session)):
    stmt = select(WatchlistSymbol).where(
        WatchlistSymbol.state.in_([SymbolState.ACTIVE, SymbolState.MANAGED])
    ).order_by(WatchlistSymbol.symbol)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/update", response_model=WatchlistUpdateOut)
async def update_watchlist(body: WatchlistUpdateIn):
    result = await watchlist_engine.process_update(body.watchlist, source_id=body.source_id)
    return WatchlistUpdateOut(**result)


@router.get("/{symbol_id}", response_model=WatchlistSymbolOut)
async def get_symbol(symbol_id: str, db: AsyncSession = Depends(get_db_session)):
    from uuid import UUID
    from fastapi import HTTPException
    stmt = select(WatchlistSymbol).where(WatchlistSymbol.id == UUID(symbol_id))
    result = await db.execute(stmt)
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return ws
