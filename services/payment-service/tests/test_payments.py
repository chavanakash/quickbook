from datetime import date

from app.cards import expiry_valid, luhn_valid
from tests.conftest import auth_header

FUTURE_EXPIRY = f"12/{(date.today().year + 2) % 100:02d}"


def pay(client, **overrides):
    body = {
        "booking_id": 1,
        "card_holder": "Asha Rao",
        "card_number": "4111 1111 1111 1111",
        "expiry": FUTURE_EXPIRY,
        "cvv": "123",
        **overrides,
    }
    return client.post("/api/payments", json=body, headers=auth_header())


def test_luhn():
    assert luhn_valid("4111111111111111")
    assert luhn_valid("4000000000000002")
    assert not luhn_valid("4111111111111112")


def test_expiry():
    assert expiry_valid("10/26", today=date(2026, 10, 16))
    assert not expiry_valid("09/26", today=date(2026, 10, 16))


def test_successful_payment_confirms_booking(client, fake_bookings):
    resp = pay(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "SUCCESS"
    assert body["amount"] == 12280.0
    assert body["card_last4"] == "1111"
    assert body["transaction_ref"].startswith("TXN")
    assert fake_bookings.bookings[1]["status"] == "CONFIRMED"


def test_declined_card(client, fake_bookings):
    resp = pay(client, card_number="4000000000000002")
    assert resp.status_code == 402
    assert fake_bookings.bookings[1]["status"] == "PENDING_PAYMENT"


def test_card_validation(client):
    assert pay(client, card_number="4111111111111112").status_code == 400  # bad Luhn
    assert pay(client, expiry="01/20").status_code == 400  # expired
    assert pay(client, cvv="12").status_code == 422
    assert pay(client, expiry="13/30").status_code == 422


def test_cannot_pay_twice(client):
    assert pay(client).status_code == 201
    assert pay(client).status_code == 409


def test_unknown_booking(client):
    assert pay(client, booking_id=999).status_code == 404


def test_requires_auth(client):
    assert client.post("/api/payments", json={}).status_code == 401


def test_confirm_failure_returns_502(client, fake_bookings):
    fake_bookings.fail_confirm = True
    assert pay(client).status_code == 502
    assert fake_bookings.bookings[1]["status"] == "PENDING_PAYMENT"


def test_payment_metrics(client):
    pay(client)
    body = client.get("/metrics").text
    assert 'quickbook_payments_total{status="success"}' in body
    assert "quickbook_revenue_inr_total" in body


def test_latency_buckets_cover_slow_requests(client):
    client.get("/health")
    body = client.get("/metrics").text
    assert 'http_request_duration_seconds_bucket{handler="/health",le="10.0"' in body
    assert 'le="0.01"' in body
