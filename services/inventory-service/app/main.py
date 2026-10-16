import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, status
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .db import SessionLocal, get_db, init_db
from .logging_config import add_request_logging, setup_logging
from .models import Schedule
from .schemas import TripOut
from .seed import seed_if_empty

SERVICE_NAME = "inventory-service"
setup_logging(SERVICE_NAME)
logger = logging.getLogger(SERVICE_NAME)

Mode = Literal["flight", "train"]

SEARCHES = Counter("quickbook_searches_total", "Trip searches", ["mode"])
for _mode in ("flight", "train"):
    SEARCHES.labels(mode=_mode)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed_if_empty(db)
    logger.info("service started")
    yield


app = FastAPI(title="Inventory Service", lifespan=lifespan)
add_request_logging(app)
Instrumentator().instrument(app).expose(app, include_in_schema=False)


def to_trip(schedule: Schedule, travel_date: date) -> TripOut:
    departure_at = datetime.combine(travel_date, time.fromisoformat(schedule.departure_time))
    return TripOut(
        schedule_id=schedule.id,
        mode=schedule.mode,
        code=schedule.code,
        operator=schedule.operator,
        origin=schedule.origin,
        destination=schedule.destination,
        departure_at=departure_at,
        arrival_at=departure_at + timedelta(minutes=schedule.duration_minutes),
        duration_minutes=schedule.duration_minutes,
        price=float(schedule.price),
    )


def ensure_not_past(travel_date: date) -> None:
    if travel_date < date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Travel date cannot be in the past")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable")
    return {"status": "ready"}


@app.get("/api/inventory/locations", response_model=list[str])
def locations(mode: Mode, db: Session = Depends(get_db)):
    return sorted(db.scalars(select(Schedule.origin).where(Schedule.mode == mode).distinct()))


@app.get("/api/inventory/search", response_model=list[TripOut])
def search(
    mode: Mode,
    origin: str,
    destination: str,
    travel_date: date = Query(alias="date"),
    db: Session = Depends(get_db),
):
    if origin.strip().lower() == destination.strip().lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Origin and destination must be different")
    ensure_not_past(travel_date)
    SEARCHES.labels(mode=mode).inc()

    schedules = db.scalars(
        select(Schedule)
        .where(
            Schedule.mode == mode,
            func.lower(Schedule.origin) == origin.strip().lower(),
            func.lower(Schedule.destination) == destination.strip().lower(),
        )
        .order_by(Schedule.departure_time)
    ).all()
    return [to_trip(s, travel_date) for s in schedules]


@app.get("/api/inventory/schedules/{schedule_id}", response_model=TripOut)
def get_schedule(schedule_id: int, travel_date: date = Query(alias="date"), db: Session = Depends(get_db)):
    ensure_not_past(travel_date)
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found")
    return to_trip(schedule, travel_date)
