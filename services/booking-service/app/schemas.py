from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class Passenger(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    age: int = Field(ge=0, le=120)


class BookingCreate(BaseModel):
    schedule_id: int
    travel_date: date
    passengers: list[Passenger] = Field(min_length=1, max_length=6)


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pnr: str
    user_email: str
    mode: str
    schedule_id: int
    trip_code: str
    operator: str
    origin: str
    destination: str
    departure_at: datetime
    arrival_at: datetime
    passengers: list[Passenger]
    amount: float
    status: str
    payment_ref: str | None
    created_at: datetime


class ConfirmRequest(BaseModel):
    payment_ref: str = Field(min_length=1, max_length=64)
