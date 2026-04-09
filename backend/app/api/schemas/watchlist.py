from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, model_validator


class WatchlistSymbolOut(BaseModel):
    id: UUID
    symbol: str
    asset_class: str
    state: str
    watchlist_source_id: str | None = None
    notes: str | None = None
    added_at: datetime | None = None
    removed_at: datetime | None = None
    managed_since: datetime | None = None

    model_config = {"from_attributes": True}


class WatchlistUpdateIn(BaseModel):
    watchlist: list[dict]
    source_id: str = "manual"

    # Accept the AI screener schema format where the list is called "symbols"
    # and the provenance field is called "source". Extra fields (timestamp,
    # notes, confidence, etc.) are silently ignored by Pydantic v2 by default.
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
