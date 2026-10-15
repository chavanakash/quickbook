import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["JWT_SECRET"] = "test-secret"

from datetime import datetime, timedelta, timezone  # noqa: E402

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import clients  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


def auth_header(user_id: int = 1) -> dict:
    token = jwt.encode(
        {"sub": str(user_id), "email": "asha@example.com", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class FakeBookingService:
    """In-memory stand-in for booking-service."""

    def __init__(self):
        self.bookings = {1: {"id": 1, "amount": 12280.0, "status": "PENDING_PAYMENT"}}
        self.fail_confirm = False

    def get_booking(self, booking_id, _token):
        if booking_id not in self.bookings:
            raise clients.BookingNotFound()
        return self.bookings[booking_id]

    def confirm_booking(self, booking_id, _ref):
        if self.fail_confirm:
            raise clients.UpstreamError("down")
        self.bookings[booking_id]["status"] = "CONFIRMED"


@pytest.fixture()
def fake_bookings(monkeypatch):
    fake = FakeBookingService()
    monkeypatch.setattr(clients, "get_booking", fake.get_booking)
    monkeypatch.setattr(clients, "confirm_booking", fake.confirm_booking)
    return fake


@pytest.fixture()
def client(fake_bookings):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
