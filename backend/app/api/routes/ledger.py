import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from zoneinfo import ZoneInfo

from app.api.deps import get_db_session
from app.api.schemas.ledger import LedgerAccountOut, LedgerEntryOut, LedgerAdjustmentIn
from app.common.models.ledger import LedgerAccount, LedgerEntry, EntryType

router = APIRouter()


@router.get("/accounts", response_model=list[LedgerAccountOut])
async def get_ledger_accounts(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(select(LedgerAccount))
    return result.scalars().all()


@router.get("/entries", response_model=list[LedgerEntryOut])
async def get_ledger_entries(
    asset_class: str | None = Query(None),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(LedgerEntry).order_by(desc(LedgerEntry.created_at)).limit(limit)
    if asset_class:
        stmt = stmt.where(LedgerEntry.asset_class == asset_class)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/adjust", response_model=LedgerEntryOut)
async def create_adjustment(
    body: LedgerAdjustmentIn,
    db: AsyncSession = Depends(get_db_session),
):
    stmt = select(LedgerAccount).where(LedgerAccount.asset_class == body.asset_class)
    result = await db.execute(stmt)
    account = result.scalar_one_or_none()

    if not account:
        account = LedgerAccount(
            id=uuid.uuid4(),
            asset_class=body.asset_class,
            cash_balance=0.0,
            fees_total=0.0,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
        )
        db.add(account)
        await db.flush()

    account.cash_balance += body.amount
    account.updated_at = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)

    entry = LedgerEntry(
        id=uuid.uuid4(),
        asset_class=body.asset_class,
        entry_type=EntryType.ADJUSTMENT,
        amount=body.amount,
        balance_after=account.cash_balance,
        notes=body.notes,
        created_at=datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None),
    )
    db.add(entry)
    await db.flush()
    return entry
