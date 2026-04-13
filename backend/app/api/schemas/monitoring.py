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
    evaluation: dict[str, object] | None = None

    # Diagnostic fields added in Phase 2A
    blocked_reason: str | None = None
    has_open_position: bool = False
    cooldown_active: bool = False
    regime_allowed: bool | None = None
    evaluation_error: str | None = None
    top_notes: str | None = None
    position_or_order_status: str | None = None


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
    top_strategy: str | None = None
    top_confidence: float | None = None
    evaluation: dict[str, object] | None = None
    evaluated_strategy_scores: dict[str, float] = {}
    evaluated_strategies: dict[str, dict] = {}
    rejected_strategies: dict[str, str] = {}
    feature_scores: dict[str, dict[str, float]] = {}
    timestamp_evaluated: str | None = None
    error: str | None = None
