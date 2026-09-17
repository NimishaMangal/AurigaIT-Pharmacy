"""SQLAlchemy ORM models for PharmaCare."""

from datetime import date, datetime
from sqlalchemy import (
    Column, Integer, String, Date, DateTime, ForeignKey,
    Boolean, Enum as SAEnum, Text, Float
)
from sqlalchemy.orm import relationship
import enum

from database import Base


class BatchStatus(str, enum.Enum):
    active = "active"
    expiring_soon = "expiring_soon"
    quarantined = "quarantined"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    unit = Column(String(50), default="units")          # tablets, ml, mg …
    reorder_threshold = Column(Integer, default=50)     # L3: alert below this
    created_at = Column(DateTime, default=datetime.utcnow)

    batches = relationship("Batch", back_populates="medicine", cascade="all, delete-orphan")
    outbox_items = relationship("Outbox", back_populates="medicine")


class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False)
    batch_number = Column(String(100), nullable=False)
    quantity_remaining = Column(Integer, nullable=False)
    expiry_date = Column(Date, nullable=False, index=True)
    status = Column(
        SAEnum(BatchStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=BatchStatus.active,
        nullable=False
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    medicine = relationship("Medicine", back_populates="batches")


class Outbox(Base):
    """Reorder alert queue (L3)."""
    __tablename__ = "outbox"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id", ondelete="CASCADE"), nullable=False)
    medicine_name = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    current_stock = Column(Integer, nullable=False)
    threshold = Column(Integer, nullable=False)
    delivered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    medicine = relationship("Medicine", back_populates="outbox_items")
