import logging
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, status
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import clients
from .auth import CurrentUser, get_current_user
from .cards import DECLINED_TEST_CARD, expiry_valid, luhn_valid
from .db import get_db, init_db
from .logging_config import add_request_logging, setup_logging
from .models import FAILED, SUCCESS, Payment
from .schemas import PaymentOut, PaymentRequest

SERVICE_NAME = "payment-service"
setup_logging(SERVICE_NAME)
logger = logging.getLogger(SERVICE_NAME)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info("service started")
    yield


app = FastAPI(title="Payment Service", lifespan=lifespan)
add_request_logging(app)
Instrumentator().instrument(app).expose(app, include_in_schema=False)


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


def record(db: Session, payment: Payment, new_status: str, reason: str | None = None) -> None:
    payment.status = new_status
    payment.failure_reason = reason
    db.add(payment)
    db.commit()
    logger.info(
        "payment recorded",
        extra={"extra_fields": {"booking_id": payment.booking_id, "status": new_status, "reason": reason}},
    )


@app.post("/api/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def pay(payload: PaymentRequest, user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if not luhn_valid(payload.card_number):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid card number")
    if not expiry_valid(payload.expiry):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Card has expired")

    try:
        booking = clients.get_booking(payload.booking_id, user.token)
    except clients.BookingNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    except clients.UpstreamError:
        logger.exception("booking lookup failed")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Booking service unavailable, try again")

    if booking["status"] == "CONFIRMED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Booking is already paid")

    payment = Payment(
        booking_id=payload.booking_id,
        user_id=user.id,
        amount=Decimal(str(booking["amount"])),  # amount comes from booking-service, not the browser
        card_last4=payload.card_number[-4:],
        transaction_ref=f"TXN{uuid.uuid4().hex[:12].upper()}",
    )

    if payload.card_number == DECLINED_TEST_CARD:
        record(db, payment, FAILED, "Card declined by issuer")
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "Payment declined by your bank. Try another card.")

    try:
        clients.confirm_booking(payload.booking_id, payment.transaction_ref)
    except clients.UpstreamError:
        logger.exception("booking confirmation failed")
        record(db, payment, FAILED, "Booking confirmation failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not confirm booking, you were not charged")

    record(db, payment, SUCCESS)
    return payment
