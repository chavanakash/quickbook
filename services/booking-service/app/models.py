from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

PENDING_PAYMENT = "PENDING_PAYMENT"
CONFIRMED = "CONFIRMED"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Booking(Base):
    """Trip details are copied in (a snapshot) so the booking never depends on
    inventory-service data changing later, and we never join across databases."""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    pnr: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(index=True)
    user_email: Mapped[str] = mapped_column(String(255))
    mode: Mapped[str] = mapped_column(String(10))
    schedule_id: Mapped[int]
    trip_code: Mapped[str] = mapped_column(String(20))
    operator: Mapped[str] = mapped_column(String(80))
    origin: Mapped[str] = mapped_column(String(60))
    destination: Mapped[str] = mapped_column(String(60))
    departure_at: Mapped[datetime] = mapped_column(DateTime)
    arrival_at: Mapped[datetime] = mapped_column(DateTime)
    passengers: Mapped[list] = mapped_column(JSON)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default=PENDING_PAYMENT)
    payment_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
