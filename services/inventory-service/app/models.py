from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Schedule(Base):
    """A recurring daily service, e.g. 'SkyJet SJ-1000, Delhi -> Mumbai, departs 06:15'.

    Storing schedules (not dated trips) means any future date can be searched
    and the seed data never goes stale.
    """

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(10), index=True)  # "flight" | "train"
    code: Mapped[str] = mapped_column(String(20), unique=True)
    operator: Mapped[str] = mapped_column(String(80))
    origin: Mapped[str] = mapped_column(String(60), index=True)
    destination: Mapped[str] = mapped_column(String(60), index=True)
    departure_time: Mapped[str] = mapped_column(String(5))  # "HH:MM"
    duration_minutes: Mapped[int]
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
