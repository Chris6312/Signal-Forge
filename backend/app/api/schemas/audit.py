from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel


class AuditEventOut(BaseModel):
    id: UUID
    event_type: str
    asset_class: str | None = None
    symbol: str | None = None
    position_id: UUID | None = None
    source: str
    event_data: Any | None = None
    message: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
