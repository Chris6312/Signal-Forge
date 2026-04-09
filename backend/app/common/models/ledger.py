import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Float, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID

from app.common.models.base import Base


class EntryType(str, enum.Enum):
    FILL = "FILL"
    FEE = "FEE"
    ADJUSTMENT = "ADJUSTMENT"
    RECONCILIATION = "RECONCILIATION"
    INITIAL_DEPOSIT = "INITIAL_DEPOSIT"


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_class = Column(String(10), nullable=False, unique=True)
    cash_balance = Column(Float, nullable=False, default=0.0)
    fees_total = Column(Float, nullable=False, default=0.0)
    realized_pnl = Column(Float, nullable=False, default=0.0)
    unrealized_pnl = Column(Float, nullable=False, default=0.0)
    last_reconciled_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_class = Column(String(10), nullable=False, index=True)
    entry_type = Column(SAEnum(EntryType, native_enum=False), nullable=False)
    symbol = Column(String(20), nullable=True)
    amount = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    position_id = Column(UUID(as_uuid=True), ForeignKey("positions.id"), nullable=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
