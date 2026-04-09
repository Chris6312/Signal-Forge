import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Index, String, DateTime, Float, Integer, Text, JSON, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.common.models.base import Base


class PositionState(str, enum.Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        # Covers: WHERE asset_class = ? AND state = ?
        Index("ix_positions_asset_class_state", "asset_class", "state"),
        # Covers: WHERE symbol = ? AND asset_class = ? AND state = ?
        Index("ix_positions_symbol_asset_class_state", "symbol", "asset_class", "state"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    asset_class = Column(String(10), nullable=False)
    state = Column(SAEnum(PositionState, native_enum=False), nullable=False, default=PositionState.PENDING)

    # Entry details
    entry_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)
    entry_time = Column(DateTime, nullable=True)

    # Frozen policy — set at entry, never overwritten
    entry_strategy = Column(String(100), nullable=True)
    exit_strategy = Column(String(100), nullable=True)
    initial_stop = Column(Float, nullable=True)
    profit_target_1 = Column(Float, nullable=True)
    profit_target_2 = Column(Float, nullable=True)
    max_hold_hours = Column(Integer, nullable=True)
    regime_at_entry = Column(String(50), nullable=True)
    watchlist_source_id = Column(String(100), nullable=True)
    management_policy_version = Column(String(20), nullable=True, default="1.0")
    frozen_policy = Column(JSON, nullable=True)

    # Mutable during trade
    current_stop = Column(Float, nullable=True)
    current_price = Column(Float, nullable=True)
    milestone_state = Column(JSON, nullable=True, default=dict)

    # Exit
    exit_price = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    exit_reason = Column(String(200), nullable=True)

    # PnL
    pnl_realized = Column(Float, nullable=True)
    pnl_unrealized = Column(Float, nullable=True)
    fees_paid = Column(Float, nullable=True, default=0.0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    orders = relationship("Order", back_populates="position", lazy="select")
