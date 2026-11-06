import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, JSON, String,
)
from sqlalchemy.orm import relationship

from .database import Base


class RFQStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    FORCE_CLOSED = "force_closed"


class RFQ(Base):
    __tablename__ = "rfqs"

    id = Column(Integer, primary_key=True)
    reference_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    pickup_date = Column(DateTime, nullable=False)

    bid_start = Column(DateTime, nullable=False)
    original_close = Column(DateTime, nullable=False)   # never mutates
    current_close = Column(DateTime, nullable=False)    # only moves forward
    forced_close = Column(DateTime, nullable=False)     # hard ceiling

    status = Column(Enum(RFQStatus), default=RFQStatus.ACTIVE, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    config = relationship("AuctionConfig", back_populates="rfq",
                          uselist=False, cascade="all, delete-orphan")
    bids = relationship("Bid", back_populates="rfq",
                        cascade="all, delete-orphan")
    logs = relationship("ActivityLog", back_populates="rfq",
                        cascade="all, delete-orphan")


class AuctionConfig(Base):
    __tablename__ = "auction_configs"

    id = Column(Integer, primary_key=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), unique=True, nullable=False)

    trigger_window_minutes = Column(Integer, nullable=False, default=10)   # X
    extension_minutes = Column(Integer, nullable=False, default=5)         # Y

    trigger_on_bid = Column(Boolean, default=True, nullable=False)
    trigger_on_any_rank_change = Column(Boolean, default=False, nullable=False)
    trigger_on_l1_change = Column(Boolean, default=True, nullable=False)

    rfq = relationship("RFQ", back_populates="config")


class Bid(Base):
    __tablename__ = "bids"

    id = Column(Integer, primary_key=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False, index=True)
    supplier_name = Column(String, nullable=False)

    freight_charge = Column(Float, nullable=False)
    origin_charge = Column(Float, nullable=False)
    destination_charge = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)  # freight + origin + destination

    transit_days = Column(Integer, nullable=False)
    quote_valid_until = Column(DateTime, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    rfq = relationship("RFQ", back_populates="bids")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True)
    rfq_id = Column(Integer, ForeignKey("rfqs.id"), nullable=False, index=True)

    event_type = Column(String, nullable=False)  # BID | EXTENSION | CLOSE | FORCE_CLOSE
    reason = Column(String, nullable=True)
    old_close = Column(DateTime, nullable=True)
    new_close = Column(DateTime, nullable=True)
    extra = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    rfq = relationship("RFQ", back_populates="logs")