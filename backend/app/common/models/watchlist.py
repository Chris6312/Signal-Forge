import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Index, String, DateTime, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID

from app.common.models.base import Base


class SymbolState(str, enum.Enum):
    ACTIVE = "ACTIVE"
    MANAGED = "MANAGED"
    INACTIVE = "INACTIVE"


class AssetClass(str, enum.Enum):
    CRYPTO = "crypto"
    STOCK = "stock"


class WatchlistSymbol(Base):
    __tablename__ = "watchlist_symbols"
    __table_args__ = (
        # Covers: WHERE asset_class = ? AND state = ?
        Index("ix_watchlist_symbols_asset_class_state", "asset_class", "state"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False, index=True)
    asset_class = Column(String(10), nullable=False)
    state = Column(SAEnum(SymbolState, native_enum=False), nullable=False, default=SymbolState.ACTIVE)
    watchlist_source_id = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    removed_at = Column(DateTime, nullable=True)
    managed_since = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
