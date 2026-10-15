import pytest
from fastapi.testclient import TestClient

from app import clients
from app.main import app

AUTH = {"Authorization": "Bearer test-token"}

CONFIRMED_BOOKING = {
    "id": 1,
    "pnr": "ABC234",
    "user_email": "asha@example.com",
    "mode": "train",
    "trip_code": "12200",
    "operator": "Delhi - Mumbai Express",
    "origin": "Delhi",
    "destination": "Mumbai",
    "departure_at": "2026-12-01T07:00:00",
    "arrival_at": "2026-12-02T06:15:00",
    "passengers": [{"name": "Asha Rao", "age": 30}, {"name": "Ravi <b>Rao</b>", "age": 33}],
    "amount": 3020.0,
    "status": "CONFIRMED",
    "payment_ref": "TXNABC123",
}


@pytest.fixture()
def bookings(monkeypatch):
    store = {1: dict(CONFIRMED_BOOKING), 2: {**CONFIRMED_BOOKING, "id": 2, "status": "PENDING_PAYMENT"}}

    def fake_get_booking(booking_id, authorization):
        if authorization != AUTH["Authorization"]:
            raise clients.Unauthorized()
        if booking_id not in store:
            raise clients.BookingNotFound()
        return store[booking_id]

    monkeypatch.setattr(clients, "get_booking", fake_get_booking)
    return store


@pytest.fixture()
def client(bookings):
    with TestClient(app) as test_client:
        yield test_client
