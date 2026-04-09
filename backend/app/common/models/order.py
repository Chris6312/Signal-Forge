import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Float, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.common.models.base import Base


class OrderType(str, enum.Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    STOP = "STOP"
    LIMIT = "LIMIT"
    PARTIAL_EXIT = "PARTIAL_EXIT"


class OrderSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    position_id = Column(UUID(as_uuid=True), ForeignKey("positions.id"), nullable=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    asset_class = Column(String(10), nullable=False)
    order_type = Column(SAEnum(OrderType, native_enum=False), nullable=False)
    side = Column(SAEnum(OrderSide, native_enum=False), nullable=False)
    quantity = Column(Float, nullable=False)
    requested_price = Column(Float, nullable=True)
    fill_price = Column(Float, nullable=True)
    status = Column(SAEnum(OrderStatus, native_enum=False), nullable=False, default=OrderStatus.PENDING)
    broker_order_id = Column(String(100), nullable=True)
    placed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    filled_at = Column(DateTime, nullable=True)
    fees = Column(Float, nullable=True, default=0.0)
    notes = Column(Text, nullable=True)

    position = relationship("Position", back_populates="orders")
