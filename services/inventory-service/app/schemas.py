from datetime import datetime

from pydantic import BaseModel


class TripOut(BaseModel):
    """A schedule resolved to a concrete travel date."""

    schedule_id: int
    mode: str
    code: str
    operator: str
    origin: str
    destination: str
    departure_at: datetime
    arrival_at: datetime
    duration_minutes: int
    price: float
