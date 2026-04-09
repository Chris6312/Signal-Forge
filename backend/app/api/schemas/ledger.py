from datetime import datetime
from uuid import UUID
from pydantic import BaseModel


class LedgerAccountOut(BaseModel):
    id: UUID
    asset_class: str
    cash_balance: float
    fees_total: float
    realized_pnl: float
    unrealized_pnl: float
    last_reconciled_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class LedgerEntryOut(BaseModel):
    id: UUID
    asset_class: str
    entry_type: str
    symbol: str | None = None
    amount: float
    balance_after: float
    position_id: UUID | None = None
    order_id: UUID | None = None
    notes: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class LedgerAdjustmentIn(BaseModel):
    asset_class: str
    amount: float
    notes: str = ""
