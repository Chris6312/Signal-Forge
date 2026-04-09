from pydantic import BaseModel


class MonitoringCandidateOut(BaseModel):
    symbol: str
    asset_class: str
    state: str
    added_at: str | None = None
    watchlist_source_id: str | None = None
    top_strategy: str | None = None
    top_confidence: float | None = None
    top_entry: float | None = None


class MonitoringListOut(BaseModel):
    candidates: list[MonitoringCandidateOut]
    total: int


class EntrySignalOut(BaseModel):
    strategy: str
    entry_price: float
    stop: float
    tp1: float
    tp2: float
    regime: str
    confidence: float
    notes: str


class EvaluateSymbolOut(BaseModel):
    symbol: str
    asset_class: str
    signals: list[EntrySignalOut]
    error: str | None = None
