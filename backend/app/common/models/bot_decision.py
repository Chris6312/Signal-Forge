import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Float, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.common.models.base import Base


class BotStrategyDecision(Base):
    __tablename__ = "bot_strategy_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    evaluated_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, nullable=True)

    symbol = Column(String(50), nullable=False, index=True)
    normalized_symbol = Column(String(50), nullable=True)
    asset_class = Column(String(10), nullable=False, index=True)
    source = Column(String(100), nullable=True)
    scan_id = Column(String(100), nullable=True)
    schema_version = Column(String(50), nullable=True)
    regime = Column(String(50), nullable=True)

    ai_hint_present = Column(Boolean, nullable=False, default=False)
    ai_hint_strategy = Column(String(50), nullable=True, index=True)
    ai_hint_confidence = Column(Float, nullable=True)
    ai_hint_bias_applied = Column(Boolean, nullable=False, default=False)
    ai_hint_bias_amount = Column(Float, nullable=False, default=0.0)

    bot_selected_strategy = Column(String(50), nullable=True, index=True)
    bot_selected_score = Column(Float, nullable=False, default=0.0)
    ai_hint_agreement = Column(Boolean, nullable=True)
    bias_changed_outcome = Column(Boolean, nullable=False, default=False)

    watchlist_symbol_id = Column(UUID(as_uuid=True), nullable=True)
    watchlist_upload_id = Column(UUID(as_uuid=True), nullable=True)
    trade_id = Column(UUID(as_uuid=True), nullable=True)
    position_id = Column(UUID(as_uuid=True), nullable=True)

    evaluated_strategy_scores = Column(JSONB, nullable=False, default=dict)
    rejected_strategies = Column(JSONB, nullable=False, default=dict)
    feature_scores = Column(JSONB, nullable=False, default=dict)
    decision_context = Column(JSONB, nullable=False, default=dict)
    regime_applied = Column(String(50), nullable=True)
    weight_profile = Column(JSONB, nullable=True)
