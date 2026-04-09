from datetime import datetime, timezone
from uuid import UUID
from pydantic import BaseModel


class OrderOut(BaseModel):
    id: UUID
    position_id: UUID | None = None
    symbol: str
    asset_class: str
    order_type: str
    side: str
    quantity: float
    requested_price: float | None = None
    fill_price: float | None = None
    status: str
    broker_order_id: str | None = None
    placed_at: datetime | None = None
    filled_at: datetime | None = None
    fees: float | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}
