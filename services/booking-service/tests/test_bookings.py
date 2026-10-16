from app import clients
from tests.conftest import TRAVEL_DATE, auth_header

PASSENGERS = [{"name": "Asha Rao", "age": 30}, {"name": "Ravi Rao", "age": 33}]


def create(client, headers=None, **overrides):
    body = {"schedule_id": 7, "travel_date": TRAVEL_DATE.isoformat(), "passengers": PASSENGERS, **overrides}
    return client.post("/api/bookings", json=body, headers=headers or auth_header())


def test_health_and_ready(client):
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_create_booking_uses_server_side_price(client):
    resp = create(client)
    assert resp.status_code == 201
    booking = resp.json()
    assert booking["amount"] == 12280.0  # 6140 x 2 passengers
    assert booking["status"] == "PENDING_PAYMENT"
    assert len(booking["pnr"]) == 6
    assert booking["origin"] == "Delhi"


def test_create_requires_auth(client):
    body = {"schedule_id": 7, "travel_date": TRAVEL_DATE.isoformat(), "passengers": PASSENGERS}
    assert client.post("/api/bookings", json=body).status_code == 401


def test_create_validation(client):
    assert create(client, passengers=[]).status_code == 422
    assert create(client, travel_date="2000-01-01").status_code == 400
    assert create(client, schedule_id=404).status_code == 400


def test_inventory_down_returns_503(client, monkeypatch):
    def broken(*_args):
        raise clients.UpstreamError("down")

    monkeypatch.setattr(clients, "get_trip", broken)
    assert create(client).status_code == 503


def test_users_only_see_their_own_bookings(client):
    booking_id = create(client).json()["id"]
    create(client, headers=auth_header(user_id=2, email="other@example.com"))

    mine = client.get("/api/bookings", headers=auth_header()).json()
    assert [b["id"] for b in mine] == [booking_id]
    assert client.get(f"/api/bookings/{booking_id}", headers=auth_header()).status_code == 200
    assert client.get(f"/api/bookings/{booking_id}", headers=auth_header(user_id=2)).status_code == 404


def test_internal_confirm(client):
    booking_id = create(client).json()["id"]
    url = f"/internal/bookings/{booking_id}/confirm"

    assert client.post(url, json={"payment_ref": "TXN1"}).status_code == 403
    assert client.post(url, json={"payment_ref": "TXN1"}, headers={"X-Internal-Token": "wrong"}).status_code == 403

    good = {"X-Internal-Token": "test-internal-token"}
    resp = client.post(url, json={"payment_ref": "TXN1"}, headers=good)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CONFIRMED"
    # Idempotent: a retry succeeds and keeps the original reference.
    assert client.post(url, json={"payment_ref": "TXN2"}, headers=good).json()["payment_ref"] == "TXN1"


def test_booking_metrics(client):
    booking_id = create(client).json()["id"]
    client.post(f"/internal/bookings/{booking_id}/confirm", json={"payment_ref": "T"}, headers={"X-Internal-Token": "test-internal-token"})
    body = client.get("/metrics").text
    assert 'quickbook_bookings_created_total{mode="flight"}' in body
    assert 'quickbook_bookings_confirmed_total{mode="flight"}' in body
