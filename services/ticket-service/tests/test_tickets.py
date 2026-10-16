from app.pdf import build_ticket_pdf
from tests.conftest import AUTH, CONFIRMED_BOOKING


def test_health_and_ready(client):
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_confirmed_booking_returns_pdf(client):
    resp = client.get("/api/tickets/1", headers=AUTH)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert 'filename="ticket-ABC234.pdf"' in resp.headers["content-disposition"]
    assert resp.content.startswith(b"%PDF")


def test_unpaid_booking_has_no_ticket(client):
    assert client.get("/api/tickets/2", headers=AUTH).status_code == 409


def test_auth_and_not_found(client):
    assert client.get("/api/tickets/1").status_code == 401
    assert client.get("/api/tickets/1", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert client.get("/api/tickets/99", headers=AUTH).status_code == 404


def test_pdf_builder_handles_markup_in_names():
    # A passenger name containing tags must not break PDF generation.
    assert build_ticket_pdf(CONFIRMED_BOOKING).startswith(b"%PDF")


def test_ticket_metric(client):
    client.get("/api/tickets/1", headers=AUTH)
    assert "quickbook_tickets_generated_total" in client.get("/metrics").text


def test_latency_buckets_cover_slow_requests(client):
    client.get("/health")
    body = client.get("/metrics").text
    assert 'http_request_duration_seconds_bucket{handler="/health",le="10.0"' in body
    assert 'le="0.01"' in body
