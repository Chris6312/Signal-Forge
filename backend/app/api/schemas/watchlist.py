from datetime import datetime, timezone
from uuid import UUID
from pydantic import BaseModel, Field, model_validator
from typing import List, Optional


class WatchlistSymbolOut(BaseModel):
    id: UUID
    symbol: str
    asset_class: str
    state: str
    watchlist_source_id: str | None = None
    notes: str | None = None
    reason: str | None = None
    confidence: float | None = None
    tags: list[str] | None = None
    added_at: datetime | None = None
    removed_at: datetime | None = None
    managed_since: datetime | None = None

    model_config = {"from_attributes": True}


class WatchlistItemIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=50)
    asset_class: str = Field(...)
    reason: str | None = None
    confidence: float | None = None
    tags: list[str] | None = None
    notes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: object) -> object:
        # Accept either dicts or simple strings; normalise to dict
        if isinstance(data, str):
            return {"symbol": data}
        return data

    @model_validator(mode="after")
    def validate_asset_class(cls, model):
        ac = getattr(model, "asset_class", None)
        if ac is None:
            raise ValueError("asset_class is required and must be 'crypto' or 'stock'")
        if ac not in ("crypto", "stock"):
            raise ValueError("asset_class must be 'crypto' or 'stock'")
        return model


class WatchlistUpdateIn(BaseModel):
    watchlist: List[WatchlistItemIn]
    source_id: str = "manual"
    append: bool = False

    @model_validator(mode="before")
    @classmethod
    def _normalise_ai_schema(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if "watchlist" not in data and "symbols" in data:
            data = {**data, "watchlist": data["symbols"]}
        if "source_id" not in data and "source" in data:
            data = {**data, "source_id": data["source"]}
        return data


class WatchlistUpdateOut(BaseModel):
    added: list[str]
    removed: list[str]
    retained: list[str]
    promoted: list[str]
    total: int
    append: bool = False
