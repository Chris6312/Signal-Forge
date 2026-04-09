import uuid
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.models.ledger import LedgerAccount, LedgerEntry, EntryType
from app.common.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

ASSET_CLASS = "crypto"


class CryptoLedger:
    async def get_account(self, db: AsyncSession) -> LedgerAccount:
        stmt = select(LedgerAccount).where(LedgerAccount.asset_class == ASSET_CLASS)
        result = await db.execute(stmt)
        account = result.scalar_one_or_none()
        if not account:
            account = LedgerAccount(
                id=uuid.uuid4(),
                asset_class=ASSET_CLASS,
                cash_balance=0.0,
                fees_total=0.0,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
            )
            db.add(account)
            await db.flush()
        return account

    async def record_fill(
        self,
        db: AsyncSession,
        symbol: str,
        amount: float,
        position_id=None,
        order_id=None,
        notes: str = "",
    ) -> LedgerEntry:
        account = await self.get_account(db)
        account.cash_balance += amount
        account.updated_at = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)

        entry = LedgerEntry(
            id=uuid.uuid4(),
            asset_class=ASSET_CLASS,
            entry_type=EntryType.FILL,
            symbol=symbol,
            amount=amount,
            balance_after=account.cash_balance,
            position_id=position_id,
            order_id=order_id,
            notes=notes,
        )
        db.add(entry)
        await db.flush()
        return entry

    async def record_fee(
        self,
        db: AsyncSession,
        symbol: str,
        fee: float,
        position_id=None,
        order_id=None,
    ) -> LedgerEntry:
        account = await self.get_account(db)
        account.cash_balance -= fee
        account.fees_total += fee
        account.updated_at = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)

        entry = LedgerEntry(
            id=uuid.uuid4(),
            asset_class=ASSET_CLASS,
            entry_type=EntryType.FEE,
            symbol=symbol,
            amount=-fee,
            balance_after=account.cash_balance,
            position_id=position_id,
            order_id=order_id,
        )
        db.add(entry)
        await db.flush()
        return entry

    async def record_pnl(
        self,
        db: AsyncSession,
        symbol: str,
        pnl: float,
        position_id=None,
        notes: str = "",
    ) -> LedgerEntry:
        account = await self.get_account(db)
        account.realized_pnl += pnl
        account.cash_balance += pnl
        account.updated_at = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)

        entry = LedgerEntry(
            id=uuid.uuid4(),
            asset_class=ASSET_CLASS,
            entry_type=EntryType.FILL,
            symbol=symbol,
            amount=pnl,
            balance_after=account.cash_balance,
            position_id=position_id,
            notes=notes or f"Realized PnL: {pnl:.4f}",
        )
        db.add(entry)
        await db.flush()
        return entry

    async def record_exit(
        self,
        db: AsyncSession,
        symbol: str,
        net_proceeds: float,
        pnl: float,
        position_id=None,
        notes: str = "",
    ) -> LedgerEntry:
        """Return net exit proceeds as a single FILL and credit realized PnL.

        *net_proceeds* = exit_price × quantity (what actually comes back).
        *pnl*          = unrealised P&L portion (updates realized_pnl only).
        """
        account = await self.get_account(db)
        account.cash_balance += net_proceeds
        account.realized_pnl += pnl
        account.updated_at = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)

        entry = LedgerEntry(
            id=uuid.uuid4(),
            asset_class=ASSET_CLASS,
            entry_type=EntryType.FILL,
            symbol=symbol,
            amount=net_proceeds,
            balance_after=account.cash_balance,
            position_id=position_id,
            notes=notes,
        )
        db.add(entry)
        await db.flush()
        return entry

    async def update_unrealized(self, db: AsyncSession, unrealized_pnl: float):
        account = await self.get_account(db)
        account.unrealized_pnl = unrealized_pnl
        account.updated_at = datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None)
        await db.flush()

    async def get_summary(self) -> dict:
        async with AsyncSessionLocal() as db:
            account = await self.get_account(db)
            await db.commit()
            return {
                "asset_class": ASSET_CLASS,
                "cash_balance": account.cash_balance,
                "fees_total": account.fees_total,
                "realized_pnl": account.realized_pnl,
                "unrealized_pnl": account.unrealized_pnl,
                "last_reconciled_at": (
                    account.last_reconciled_at.isoformat()
                    if account.last_reconciled_at else None
                ),
            }


crypto_ledger = CryptoLedger()
