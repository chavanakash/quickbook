import logging

from fastapi import FastAPI, Header, HTTPException, Response, status
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

from . import clients
from .logging_config import add_request_logging, setup_logging
from .pdf import build_ticket_pdf

SERVICE_NAME = "ticket-service"
setup_logging(SERVICE_NAME)
logger = logging.getLogger(SERVICE_NAME)

TICKETS = Counter("quickbook_tickets_generated_total", "PDF tickets generated")

app = FastAPI(title="Ticket Service")
add_request_logging(app)
Instrumentator().instrument(app).expose(app, include_in_schema=False)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    # Stateless service: no database to check.
    return {"status": "ready"}


@app.get("/api/tickets/{booking_id}")
def download_ticket(booking_id: int, authorization: str | None = Header(default=None)):
    if not authorization:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    try:
        booking = clients.get_booking(booking_id, authorization)
    except clients.Unauthorized:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    except clients.BookingNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    except clients.UpstreamError:
        logger.exception("booking lookup failed")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Booking service unavailable, try again")

    if booking["status"] != "CONFIRMED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Ticket is available only after payment")

    pdf = build_ticket_pdf(booking)
    TICKETS.inc()
    logger.info("ticket generated", extra={"extra_fields": {"booking_id": booking_id, "pnr": booking["pnr"]}})
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="ticket-{booking["pnr"]}.pdf"'},
    )
