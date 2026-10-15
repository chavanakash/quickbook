import logging
import secrets
import string
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal

from fastapi import Depends, FastAPI, Header, HTTPException, status
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from . import clients
from .auth import CurrentUser, get_current_user
from .config import INTERNAL_API_TOKEN
from .db import get_db, init_db
from .logging_config import add_request_logging, setup_logging
from .models import CONFIRMED, PENDING_PAYMENT, Booking
from .schemas import BookingCreate, BookingOut, ConfirmRequest

SERVICE_NAME = "booking-service"
setup_logging(SERVICE_NAME)
logger = logging.getLogger(SERVICE_NAME)

PNR_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "O0I1")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info("service started")
    yield


app = FastAPI(title="Booking Service", lifespan=lifespan)
add_request_logging(app)
Instrumentator().instrument(app).expose(app, include_in_schema=False)


def generate_pnr(db: Session) -> str:
    while True:
        pnr = "".join(secrets.choice(PNR_ALPHABET) for _ in range(6))
        if not db.scalar(select(Booking.id).where(Booking.pnr == pnr)):
            return pnr


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


@app.post("/api/bookings", response_model=BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: BookingCreate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.travel_date < date.today():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Travel date cannot be in the past")

    # Price and trip details come from inventory-service, never from the browser.
    try:
        trip = clients.get_trip(payload.schedule_id, payload.travel_date)
    except clients.TripNotAvailable as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    except clients.UpstreamError:
        logger.exception("inventory lookup failed")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Inventory service unavailable, try again")

    booking = Booking(
        pnr=generate_pnr(db),
        user_id=user.id,
        user_email=user.email,
        mode=trip["mode"],
        schedule_id=trip["schedule_id"],
        trip_code=trip["code"],
        operator=trip["operator"],
        origin=trip["origin"],
        destination=trip["destination"],
        departure_at=datetime.fromisoformat(trip["departure_at"]),
        arrival_at=datetime.fromisoformat(trip["arrival_at"]),
        passengers=[p.model_dump() for p in payload.passengers],
        amount=Decimal(str(trip["price"])) * len(payload.passengers),
        status=PENDING_PAYMENT,
    )
    db.add(booking)
    db.commit()
    logger.info(
        "booking created",
        extra={"extra_fields": {"booking_id": booking.id, "pnr": booking.pnr, "user_id": user.id}},
    )
    return booking


@app.get("/api/bookings", response_model=list[BookingOut])
def list_bookings(user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Booking).where(Booking.user_id == user.id).order_by(Booking.created_at.desc(), Booking.id.desc())
    ).all()


@app.get("/api/bookings/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    # 404 (not 403) for other users' bookings so IDs can't be probed.
    if not booking or booking.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    return booking


@app.post("/internal/bookings/{booking_id}/confirm", response_model=BookingOut)
def confirm_booking(
    booking_id: int,
    payload: ConfirmRequest,
    x_internal_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Called only by payment-service. Not routed through the public gateway."""
    if not secrets.compare_digest(x_internal_token or "", INTERNAL_API_TOKEN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")

    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.status == CONFIRMED:
        return booking  # idempotent: safe to retry

    booking.status = CONFIRMED
    booking.payment_ref = payload.payment_ref
    db.commit()
    logger.info("booking confirmed", extra={"extra_fields": {"booking_id": booking.id, "pnr": booking.pnr}})
    return booking
